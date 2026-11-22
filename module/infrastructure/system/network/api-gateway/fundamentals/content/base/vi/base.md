# Network API Gateway Fundamentals

API Gateway là điểm vào tập trung cho các yêu cầu từ client tới một hoặc nhiều dịch vụ backend. Gateway nhận và chuyển tiếp request theo quy tắc định tuyến, đồng thời có thể xử lý những mối quan tâm chung như bảo mật kết nối, xác thực, giới hạn lưu lượng và giám sát. Hiểu đúng vai trò của gateway giúp giảm sự phụ thuộc của client vào cấu trúc dịch vụ và nhận diện các chi phí, điểm lỗi có thể phát sinh.

Module này dành cho người phát triển backend và vận hành hệ thống muốn nắm nền tảng API Gateway trước khi học một sản phẩm cụ thể. Lộ trình đi từ luồng request, routing và upstream, HTTP/TLS, chính sách truy cập đến rate limiting, timeout, retry và các mẫu gateway routing, aggregation, offloading hay Backend for Frontend. Phần cuối giới thiệu các chỉ số vận hành, tính sẵn sàng và kiểm thử gateway.

Sau khi học, bạn có thể phác họa kiến trúc gateway cho vài API, chọn vị trí áp dụng chính sách, mô tả cách xử lý các phản hồi lỗi và kiểm tra những kịch bản thường gặp. Gateway giúp tập trung các chức năng chung, nhưng việc phân quyền gắn với dữ liệu nghiệp vụ vẫn phải được thực thi đúng ở backend.