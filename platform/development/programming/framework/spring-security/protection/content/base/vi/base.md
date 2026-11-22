# Spring Security Protection

Spring Security Protection tập trung vào những cơ chế bảo vệ ứng dụng Web trước các kiểu khai thác phổ biến ở tầng HTTP và trình duyệt. Bên cạnh xác thực và phân quyền, Spring Security cung cấp các lớp phòng vệ như chống Cross-Site Request Forgery (CSRF), security headers, hỗ trợ HTTPS, kiểm soát request qua HTTP firewall và bảo vệ phiên đăng nhập.

Module phù hợp với lập trình viên Java/Spring đã hiểu request/response, Spring MVC và kiến thức cơ bản về Spring Security. Lộ trình bắt đầu từ cách các cơ chế phòng vệ tham gia SecurityFilterChain, tiếp đến CSRF, CORS, HTTP response headers, HTTPS/HSTS, bảo vệ session và phát hiện request bất thường. Mỗi phần nhấn mạnh việc lựa chọn cấu hình phù hợp với kiểu ứng dụng, đặc biệt khi làm việc với trình duyệt, cookie và reverse proxy.

Sau khi hoàn thành, người học có thể giải thích rủi ro mà từng lớp bảo vệ xử lý, cấu hình các cơ chế cần thiết và viết kiểm thử xác nhận hành vi an toàn. Việc kiểm tra cấu hình và những trường hợp lỗi giúp giảm nguy cơ vô hiệu hóa biện pháp phòng vệ hoặc làm hỏng luồng sử dụng hợp lệ.