import axios from 'axios';
import toast from 'react-hot-toast';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      toast.error(error.response.data?.detail || 'An error occurred');
    } else if (error.request) {
      toast.error('No response from server');
    } else {
      toast.error('Request failed');
    }
    return Promise.reject(error);
  }
);

export const aciApi = {
  // Dashboard
  getDashboardStats: () => api.get('/dashboard/stats/'),
  
  // Requirements
  getRequirements: (params = {}) => api.get('/requirements/', { params }),
  getRequirement: (id) => api.get(`/requirements/${id}/`),
  getRequirementByKey: (key) => api.get(`/requirements/?external_id=${key}`),

  // Verifications
  getVerifications: (params = {}) => api.get('/verifications/', { params }),
  getVerification: (id) => api.get(`/verifications/${id}/`),
  
  // Delivery Decisions
  getDeliveryDecisions: (params = {}) => api.get('/delivery-decisions/', { params }),
  getDeliveryDecision: (id) => api.get(`/delivery-decisions/${id}/`),

  // Pull Requests
  getPullRequests: (params = {}) => api.get('/pull-requests/', { params }),
  getPullRequest: (id) => api.get(`/pull-requests/${id}/`),

  // Evidence
  getEvidence: (params = {}) => api.get('/evidence/', { params }),

  // Repositories
  getRepositories: () => api.get('/repositories/'),

  // Start verification
  startVerification: (data) => api.post('/start-verification/', data),
};

export default aciApi;