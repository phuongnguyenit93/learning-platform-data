# Spring Security - Reactive

Spring Security cho ứng dụng phản ứng (reactive) giúp xác thực danh tính, kiểm soát quyền truy cập và bảo vệ ứng dụng Spring WebFlux. Module này hướng đến người đã biết Java, Spring cơ bản, HTTP và cách sử dụng Mono/Flux, muốn hiểu cách xây dựng bảo mật phù hợp với mô hình xử lý không chặn.

Tư duy nền tảng là theo dõi một yêu cầu đi qua chuỗi lọc bảo mật, được xác thực rồi được kiểm tra quyền trước khi truy cập tài nguyên. Authentication biểu diễn danh tính và quyền hạn; SecurityContext giữ thông tin xác thực, còn Reactor Context giúp truyền ngữ cảnh trong luồng xử lý. Cần phân biệt việc truyền ngữ cảnh này với việc lưu danh tính giữa nhiều yêu cầu qua phiên WebSession, đồng thời tránh đưa thao tác chặn vào luồng phản ứng.

Lộ trình bắt đầu từ các khái niệm và chuỗi lọc, tiếp đến xác thực, ngữ cảnh và phiên, rồi phân quyền ở lớp HTTP và phương thức. Người học sau đó thực hành CSRF, CORS, các HTTP header bảo mật, tích hợp OAuth2/OIDC theo vai trò ứng dụng và kiểm thử bằng WebTestClient. Trọng tâm là cấu hình, quan sát và kiểm chứng bảo mật trong WebFlux; phần OAuth2/OIDC tập trung tích hợp với hệ thống có sẵn, không xây dựng máy chủ cấp quyền.