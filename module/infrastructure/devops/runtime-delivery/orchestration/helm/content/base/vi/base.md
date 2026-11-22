# DevOps Runtime Delivery Orchestration Helm

**Helm** là công cụ quản lý gói và bản phát hành ứng dụng trên Kubernetes. Một Helm chart mô tả các tài nguyên Kubernetes bằng template cùng cấu hình có thể thay đổi theo môi trường; Helm giúp cài đặt, nâng cấp và quản lý lịch sử release mà không phải sao chép thủ công nhiều manifest YAML. Học phần tập trung vào cách phát triển chart có thể tái sử dụng và triển khai một cách kiểm chứng được.

Lộ trình gồm **8 mốc**: làm quen chart và release; cấu trúc chart; cấu hình values và ghi đè; Go templates; dependencies và hooks; cài đặt, nâng cấp và rollback; lint cùng release tests; cuối cùng là đóng gói và phân phối chart. Người học sẽ tạo chart cho ứng dụng mẫu, render manifest để kiểm tra, triển khai trên cluster thử nghiệm và quan sát quá trình thay đổi revision.

Học phần phù hợp với developer và DevOps engineer đã biết container, Kubernetes Deployment/Service, YAML và dòng lệnh cơ bản. Sau khi hoàn thành, bạn có thể viết, kiểm thử và đóng gói Helm chart, sử dụng cấu hình theo môi trường, theo dõi và phục hồi release, đồng thời tránh đưa secrets hoặc thay đổi không được kiểm tra vào quy trình triển khai.