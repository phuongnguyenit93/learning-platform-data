# Network Service Mesh Istio

Istio là nền tảng service mesh giúp quản lý giao tiếp giữa các dịch vụ trong hệ thống phân tán. Thông qua proxy và cấu hình tập trung, Istio hỗ trợ điều hướng lưu lượng, xác thực và phân quyền giữa workload, đồng thời tạo dữ liệu quan sát như metrics, logs và traces. Module này cung cấp lộ trình ngắn gọn để hiểu và vận hành các khả năng cốt lõi của Istio trên Kubernetes.

Bạn sẽ bắt đầu từ kiến trúc control plane/data plane và hai mô hình sidecar, ambient; sau đó cài đặt, kết nạp workload và thực hành routing theo phiên bản, timeout, retry, circuit breaking. Phần tiếp theo tập trung vào ingress/egress, mTLS, AuthorizationPolicy và cách dùng telemetry cùng công cụ istioctl để xác minh cấu hình. Với ambient mode, các tính năng lớp 7 cần được xem xét cùng waypoint proxy.

Nội dung phù hợp với lập trình viên và kỹ sư nền tảng đã biết Kubernetes Service, Pod và cơ chế giao tiếp HTTP cơ bản. Sau khi học, bạn có thể đọc sơ đồ traffic trong mesh, lựa chọn chế độ data plane, cấu hình chính sách thiết yếu và chẩn đoán các lỗi mạng hoặc chính sách dựa trên bằng chứng quan sát.