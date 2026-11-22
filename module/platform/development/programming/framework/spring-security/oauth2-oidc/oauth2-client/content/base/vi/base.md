# Spring Security OAuth 2.0 & OIDC Client

Module này hướng dẫn cách ứng dụng Spring đóng vai trò **OAuth 2.0 Client** để xin quyền truy cập tài nguyên và sử dụng **OpenID Connect (OIDC)** để đăng nhập người dùng qua nhà cung cấp danh tính. Trọng tâm là cấu hình ứng dụng khách, xử lý luồng ủy quyền và sử dụng token đúng ngữ cảnh trong Spring Security.

Bạn sẽ bắt đầu từ các vai trò OAuth2/OIDC và cấu hình Client Registration, tiếp đến Authorization Code với PKCE, OAuth2 Login, OIDC ID Token/UserInfo, Authorized Client và vòng đời token. Các phần tiếp theo tập trung vào tích hợp RestClient/WebClient để gọi API được bảo vệ, quản lý phiên/đăng xuất OIDC và kiểm thử các luồng thành công hoặc thất bại trên Servlet hay Reactive.

Nội dung phù hợp với lập trình viên Java/Spring đã biết HTTP, Spring Security cơ bản và cơ chế xác thực web. Sau khi học, bạn có thể cấu hình ứng dụng đăng nhập qua Identity Provider, quản lý token cho luồng người dùng hoặc service-to-service, và chẩn đoán lỗi thường gặp khi tích hợp OAuth2/OIDC Client.