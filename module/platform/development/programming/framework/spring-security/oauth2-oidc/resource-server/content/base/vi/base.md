# Spring Security OAuth 2.0 OIDC Resource Server

Module này hướng dẫn cách bảo vệ API Spring bằng OAuth 2.0 Resource Server của Spring Security trong hệ sinh thái có OpenID Connect (OIDC). Resource Server nhận Bearer access token do Authorization Server phát hành, xác thực token và quyết định quyền truy cập vào tài nguyên. Cần phân biệt access token dành cho API với OIDC ID token dùng để truyền thông tin về phiên xác thực của người dùng cho client.

Lộ trình bắt đầu từ mô hình OAuth2/OIDC và cấu hình SecurityFilterChain, sau đó thực hành xác minh JWT bằng issuer và JWKS hoặc kiểm tra opaque token qua introspection. Người học tiếp tục ánh xạ scopes và claims thành authorities, bảo vệ endpoint và service, tìm hiểu discovery, nhiều issuer, xử lý lỗi 401/403 và các nguyên tắc bảo vệ Bearer token.

Module dành cho developer Java/Spring đã biết HTTP, REST API và kiến thức Spring Security cơ bản. Sau khi hoàn thành, bạn có thể cấu hình Resource Server phù hợp với nhà cung cấp danh tính, kiểm thử các trường hợp token hợp lệ và không hợp lệ, áp dụng phân quyền theo scope và theo dõi vấn đề xác thực khi triển khai.