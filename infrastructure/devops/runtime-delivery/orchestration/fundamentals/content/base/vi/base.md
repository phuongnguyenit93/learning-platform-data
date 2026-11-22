# DevOps Runtime Delivery Orchestration Fundamentals

Container orchestration là cách tự động triển khai, phân phối, kết nối và duy trì các workload container trên một cụm máy chủ. Thay vì tự tạo, khởi động lại và cân bằng tải cho từng container, nhóm vận hành khai báo trạng thái mong muốn để nền tảng điều phối liên tục đối chiếu và điều chỉnh trạng thái thực tế. Kubernetes là hệ thống tiêu biểu giúp minh họa tư duy này.

Module dành cho người đã biết Docker, Linux, mạng căn bản và cú pháp YAML. Lộ trình bắt đầu bằng nhu cầu orchestration, kiến trúc cluster và scheduling; tiếp theo là Pod, các loại workload, khai báo desired state và quy trình rollout. Bạn sẽ làm quen Service discovery, cấu hình bằng ConfigMap/Secret, lưu trữ bền vững, health probes, self-healing, scaling và cách đọc logs/metrics khi xảy ra lỗi.

Sau khi hoàn thành, bạn có thể giải thích một workload được triển khai và vận hành trên cluster như thế nào, thử các thao tác triển khai hoặc mở rộng ở môi trường thực hành, kiểm tra ứng dụng có sẵn sàng nhận lưu lượng hay không và nhận diện nguyên nhân sự cố cơ bản. Đây là nền tảng trước khi học sâu Kubernetes, Helm và các chiến lược deployment.