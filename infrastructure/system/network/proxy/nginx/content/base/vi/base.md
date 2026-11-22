# Network Proxy Nginx

Nginx là web server và reverse proxy thường được đặt trước các ứng dụng để tiếp nhận kết nối, định tuyến HTTP request, phân phối tải và cung cấp HTTPS. Khi cấu hình đúng, Nginx giúp các dịch vụ phía sau được truy cập ổn định, dễ mở rộng và có một điểm kiểm soát chung cho lưu lượng vào.

Module này dành cho lập trình viên backend, DevOps và kỹ sư vận hành đã biết kiến thức HTTP/TCP cơ bản. Bạn sẽ tìm hiểu mô hình master/worker, cách tổ chức cấu hình `http`, `server`, `location`, rồi thực hành reverse proxy với `proxy_pass`, chuyển tiếp header, cấu hình upstream, cân bằng tải và TLS. Các chủ đề tiếp theo giới thiệu response cache, gzip và giới hạn tốc độ request để kiểm soát hiệu năng và rủi ro.

Lộ trình kết thúc bằng log, kiểm tra cú pháp cấu hình và reload an toàn. Sau khi học, bạn có thể xây một cấu hình Nginx cơ bản trước nhiều backend, kiểm chứng đường đi của request và chẩn đoán các lỗi phổ biến về routing, HTTPS hoặc upstream.