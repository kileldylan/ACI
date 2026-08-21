import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { aciApi } from '../api/aci';
import StatusBadge from './StatusBadge';

export const VerificationDetail = () => {
  const { id } = useParams();
  const [verification, setVerification] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function fetchVerificationDetail() {
    try {
      setLoading(true);
      const verRes = await aciApi.getVerification(id);
      setVerification(verRes.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // Remote data loading is intentionally triggered when the route changes.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchVerificationDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-4 border-accent-middle border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="text-dark-muted">Loading verification...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-unverified/10 border border-unverified/20 text-unverified px-4 py-3 rounded-xl">
        Error: {error}
      </div>
    );
  }

  if (!verification) {
    return (
      <div className="text-center py-12 text-dark-muted">
        <p className="text-lg">Verification not found</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Verification #{verification.id}</h1>
          <p className="text-dark-muted mt-1">
            {verification.requirement?.title || 'No title'}
          </p>
        </div>
        <StatusBadge status={verification.status} size="lg" />
      </div>

      <div className="card p-6">
        <h2 className="text-lg font-semibold mb-4">Details</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-dark-muted">Requirement</p>
            <p className="font-medium">{verification.requirement?.external_id || 'N/A'}</p>
          </div>
          <div>
            <p className="text-sm text-dark-muted">Pull Request</p>
            <p className="font-medium">#{verification.pull_request?.number || 'N/A'}</p>
          </div>
          <div>
            <p className="text-sm text-dark-muted">Confidence</p>
            <p className="font-medium">{verification.confidence ? `${Math.round(verification.confidence * 100)}%` : 'N/A'}</p>
          </div>
          <div>
            <p className="text-sm text-dark-muted">Updated</p>
            <p className="font-medium">{verification.verification_timestamp ? new Date(verification.verification_timestamp).toLocaleString() : 'N/A'}</p>
          </div>
        </div>
        {verification.summary && (
          <div className="mt-4 p-4 bg-dark-hover rounded-xl">
            <p className="text-sm text-dark-muted">Summary</p>
            <p className="mt-1">{verification.summary}</p>
          </div>
        )}
      </div>

      {verification.criteria_evaluations && verification.criteria_evaluations.length > 0 && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold mb-4">Acceptance Criteria</h2>
          <div className="space-y-3">
            {verification.criteria_evaluations.map((criterion, index) => (
              <div key={index} className="flex items-center justify-between p-3 bg-dark-hover rounded-xl">
                <div className="flex-1">
                  <p className="text-sm">
                    <span className="text-dark-muted">Criterion {index + 1}:</span> {criterion.description}
                  </p>
                </div>
                <StatusBadge status={criterion.status} size="sm" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default VerificationDetail;
