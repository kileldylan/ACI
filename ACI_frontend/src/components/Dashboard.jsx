import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Activity, 
  CheckCircle, 
  AlertTriangle, 
  XCircle, 
  Clock,
  GitPullRequest,
  Sparkles,
  TrendingUp,
  Shield,
  BarChart3,
  Zap,
} from 'lucide-react';
import { aciApi } from '../api/aci';
import StatusBadge from './StatusBadge';
import StatsCard from './StatsCard';
import toast from 'react-hot-toast';

const responseItems = (response) => {
  const payload = response?.data;
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload?.results)) {
    return payload.results;
  }
  return [];
};

export const Dashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    total: 0,
    verified: 0,
    partial: 0,
    unverified: 0,
    pending: 0,
    requirements: 0,
    pullRequests: 0,
  });
  const [recentVerifications, setRecentVerifications] = useState([]);
  const [recentPRs, setRecentPRs] = useState([]);

  async function fetchData() {
    try {
      setLoading(true);
      
      // Fetch verifications
      const verRes = await aciApi.getVerifications({ limit: 10 });
      const verifications = responseItems(verRes);
      setRecentVerifications(verifications.slice(0, 5));

      // Calculate stats
      const total = verifications.length;
      const verified = verifications.filter(v => v.status === 'verified').length;
      const partial = verifications.filter(v => v.status === 'partial').length;
      const unverified = verifications.filter(v => v.status === 'unverified').length;
      const pending = verifications.filter(v => v.status === 'pending').length;

      setStats({
        total,
        verified,
        partial,
        unverified,
        pending,
        requirements: total,
        pullRequests: verifications.filter(v => v.pull_request).length,
      });

      // Fetch recent PRs
      const prRes = await aciApi.getPullRequests({ limit: 5 });
      setRecentPRs(responseItems(prRes));

    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      toast.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }

  // Remote data loading is intentionally triggered on mount.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchData();
  }, []);

  const handleVerificationClick = (id) => {
    navigate(`/verifications/${id}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center space-y-4">
          <div className="w-16 h-16 border-4 border-accent-middle border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="text-dark-muted">Loading verification data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-slide-up">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Shield className="w-8 h-8 text-accent-middle" />
            <span className="gradient-text">ACI Dashboard</span>
          </h1>
          <p className="text-dark-muted mt-1">
            Automated Compliance Intelligence — Verification Overview
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm text-dark-muted bg-dark-card/50 px-4 py-2 rounded-xl border border-dark-border">
          <Zap className="w-4 h-4 text-accent-middle" />
          <span>Live monitoring</span>
          <span className="w-1.5 h-1.5 rounded-full bg-verified animate-pulse"></span>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Total Verifications"
          value={stats.total}
          icon={Activity}
          color="text-accent-middle"
          trend={12}
          onClick={() => navigate('/verifications')}
        />
        <StatsCard
          title="Verified"
          value={stats.verified}
          icon={CheckCircle}
          color="text-verified"
          trend={8}
          onClick={() => navigate('/verifications?status=verified')}
        />
        <StatsCard
          title="Partial"
          value={stats.partial}
          icon={AlertTriangle}
          color="text-partial"
          trend={-3}
          onClick={() => navigate('/verifications?status=partial')}
        />
        <StatsCard
          title="Unverified"
          value={stats.unverified}
          icon={XCircle}
          color="text-unverified"
          trend={-5}
          onClick={() => navigate('/verifications?status=unverified')}
        />
      </div>

      {/* Quick Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-4 flex items-center gap-4">
          <div className="p-3 rounded-xl bg-accent-start/10">
            <GitPullRequest className="w-5 h-5 text-accent-middle" />
          </div>
          <div>
            <p className="text-sm text-dark-muted">Pull Requests</p>
            <p className="text-xl font-bold">{stats.pullRequests}</p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-4">
          <div className="p-3 rounded-xl bg-accent-start/10">
            <BarChart3 className="w-5 h-5 text-accent-middle" />
          </div>
          <div>
            <p className="text-sm text-dark-muted">Requirements</p>
            <p className="text-xl font-bold">{stats.requirements}</p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-4">
          <div className="p-3 rounded-xl bg-accent-start/10">
            <TrendingUp className="w-5 h-5 text-verified" />
          </div>
          <div>
            <p className="text-sm text-dark-muted">Pass Rate</p>
            <p className="text-xl font-bold">
              {stats.total > 0 ? Math.round((stats.verified / stats.total) * 100) : 0}%
            </p>
          </div>
        </div>
      </div>

      {/* Recent Verifications */}
      <div className="card">
        <div className="p-6 border-b border-dark-border">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Clock className="w-5 h-5 text-accent-middle" />
              Recent Verifications
            </h2>
            <button 
              onClick={() => navigate('/verifications')}
              className="text-sm text-accent-middle hover:text-accent-end transition-colors"
            >
              View all →
            </button>
          </div>
        </div>
        <div className="divide-y divide-dark-border">
          {recentVerifications.length === 0 ? (
            <div className="p-8 text-center text-dark-muted">
              <p>No verifications found</p>
              <p className="text-sm mt-1">Create a PR with a Jira key to get started</p>
            </div>
          ) : (
            recentVerifications.map((ver) => (
              <div
                key={ver.id}
                onClick={() => handleVerificationClick(ver.id)}
                className="p-4 hover:bg-dark-hover transition-colors cursor-pointer"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className="mt-1">
                      <StatusBadge status={ver.status} size="sm" />
                    </div>
                    <div>
                      <p className="font-medium">
                        {ver.requirement?.external_id || 'Unknown'}
                      </p>
                      <p className="text-sm text-dark-muted">
                        {ver.requirement?.title?.substring(0, 60) || 'No title'}...
                      </p>
                      {ver.pull_request && (
                        <p className="text-xs text-dark-muted mt-1">
                          PR #{ver.pull_request.number} · {ver.pull_request.repository}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-dark-muted">
                    {ver.confidence && (
                      <span>Confidence: {Math.round(ver.confidence * 100)}%</span>
                    )}
                    {ver.verification_timestamp && (
                      <span>
                        {new Date(ver.verification_timestamp).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Recent PRs */}
      {recentPRs.length > 0 && (
        <div className="card">
          <div className="p-6 border-b border-dark-border">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <GitPullRequest className="w-5 h-5 text-accent-middle" />
              Recent Pull Requests
            </h2>
          </div>
          <div className="divide-y divide-dark-border">
            {recentPRs.map((pr) => (
              <div key={pr.id} className="p-4 flex items-center justify-between">
                <div>
                  <p className="font-medium">#{pr.number} {pr.title}</p>
                  <p className="text-sm text-dark-muted">{pr.repository}</p>
                </div>
                <span className="text-sm text-dark-muted">
                  {pr.created_at ? new Date(pr.created_at).toLocaleDateString() : 'N/A'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Footer Info */}
      <div className="flex items-center justify-between text-xs text-dark-muted/60 border-t border-dark-border pt-6">
        <div className="flex items-center gap-2">
          <Sparkles className="w-3 h-3" />
          <span>ACI v1.0 · Automated Compliance Intelligence</span>
        </div>
        <div className="flex items-center gap-4">
          <span>Last updated: {new Date().toLocaleString()}</span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-verified animate-pulse"></span>
            Online
          </span>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;