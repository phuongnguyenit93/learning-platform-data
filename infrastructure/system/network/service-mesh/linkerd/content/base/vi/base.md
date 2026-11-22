# Network Service Mesh Linkerd

Linkerd là một service mesh dành cho Kubernetes, hỗ trợ quan sát, bảo mật và tăng độ tin cậy khi các dịch vụ giao tiếp với nhau. Thay vì để mỗi ứng dụng tự xử lý toàn bộ vấn đề mạng, Linkerd đặt proxy bên cạnh workload và sử dụng control plane để cung cấp thông tin cần thiết. Module này phù hợp với lập trình viên, kỹ sư nền tảng và người mới tiếp cận vận hành microservices trên Kubernetes.

Lộ trình đi từ vai trò của Linkerd, kiến trúc control plane và data plane đến cài đặt, kiểm tra hệ thống và đưa dịch vụ vào mesh. Bạn sẽ học cách đọc telemetry với Linkerd Viz, hiểu cơ chế mTLS giữa các workload đã tham gia mesh, cũng như cách chính sách truy cập, retry và timeout ảnh hưởng đến lưu lượng giữa các dịch vụ.

Cuối module, bạn thực hành quan sát giao tiếp giữa hai dịch vụ mẫu, kiểm tra proxy và kết nối bảo mật, đồng thời dùng dữ liệu và các lệnh kiểm tra để khoanh vùng lỗi. Mục tiêu là xây dựng tư duy vận hành Linkerd có kiểm chứng, làm nền tảng cho các cấu hình nâng cao về routing, bảo mật và độ tin cậy.