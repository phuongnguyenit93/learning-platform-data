Một tổ chức đang xây dựng nền tảng đăng nhập và cấp quyền cho nhiều ứng dụng; làm thế nào phân biệt trách nhiệm của OAuth 2.0 với OpenID Connect trong kiến trúc đó?
Trong một luồng OAuth 2.0, resource owner, client, authorization server và resource server tương tác với nhau như thế nào?
Vì sao access token trong OAuth 2.0 biểu diễn quyền truy cập được cấp mà không tự nó chứng minh danh tính người dùng đã đăng nhập?
OpenID Connect bổ sung những thành phần và quy ước nào để biến một luồng OAuth 2.0 thành cơ chế xác thực người dùng?
Khi một API nhận access token, làm thế nào xác định token được phát hành cho đúng resource server và có quyền gọi operation đang yêu cầu?
Làm thế nào phân biệt vai trò của authorization code, access token, refresh token và ID token trong một phiên OIDC?
Những loại client nào được xem là public client hoặc confidential client, và khả năng bảo vệ credential ảnh hưởng phân loại đó ra sao?
Vì sao ứng dụng chạy trong trình duyệt hoặc trên thiết bị người dùng không thể giữ client secret như một bí mật đáng tin cậy?
Trong Authorization Code Flow, các bước từ chuyển hướng người dùng tới authorization endpoint đến khi client đổi code lấy token diễn ra như thế nào?
Vì sao Authorization Code Flow phù hợp hơn các luồng đưa access token trực tiếp qua front channel?
PKCE giải quyết rủi ro nào trong Authorization Code Flow, và code verifier được liên kết với authorization request bằng cách nào?
Sự khác biệt về bảo vệ giữa PKCE với method S256 và method plain là gì, và khi nào cần từ chối plain?
Làm thế nào client tạo, lưu và kiểm tra state để chống request forgery hoặc ghép nhầm phản hồi authorization vào phiên người dùng?
OIDC nonce bảo vệ phần nào của luồng xác thực, và client cần đối chiếu nonce trong ID token với giá trị đã gửi nếu request có nonce như thế nào?
Redirect URI cần được đăng ký và so khớp ra sao để ngăn authorization server chuyển code hoặc token tới endpoint do attacker kiểm soát?
Vì sao wildcard hoặc kiểm tra redirect URI theo tiền tố có thể tạo lỗ hổng open redirect và đánh cắp authorization code?
Một ứng dụng có nhiều callback URL cho môi trường và tenant khác nhau; làm thế nào quản lý danh sách redirect URI mà vẫn giữ kiểm soát chặt chẽ?
Khi authorization response có error hoặc state không khớp, client cần xử lý phiên hiện tại và dữ liệu tạm như thế nào?
Vì sao ứng dụng native nên mở authorization request trong external user-agent thay vì webview do ứng dụng tự nhúng?
Các lựa chọn redirect URI cho ứng dụng mobile như claimed HTTPS link và loopback redirect có ưu nhược điểm gì?
Một ứng dụng SPA chạy trong browser cần lưu token và quản lý callback; những rủi ro nào phát sinh từ XSS, browser storage và nhiều tab?
Khi client cần xác thực với token endpoint, làm thế nào lựa chọn phương thức client authentication phù hợp với loại client và khả năng bảo vệ khóa?
Vì sao client secret nhúng trong mobile app hoặc distributed desktop software không thể được xem là credential bí mật?
Private key JWT hoặc mutual TLS có thể tăng cường xác thực client theo những cách nào so với shared client secret?
Scope biểu diễn phạm vi quyền được yêu cầu và cấp như thế nào, và vì sao scope không nên bị coi là danh sách role nội bộ một cách máy móc?
Làm thế nào thiết kế scope đủ hẹp để giới hạn quyền, nhưng vẫn ổn định và dễ quản lý khi API phát triển?
Authorization server nên quyết định cấp scope nào khi request yêu cầu nhiều quyền hơn consent hoặc policy cho phép?
Incremental authorization có thể cải thiện trải nghiệm người dùng và giảm quyền cấp dư thừa như thế nào?
Consent screen nên trình bày thông tin nào để người dùng hiểu client, mục đích, dữ liệu và quyền đang được yêu cầu?
Trong trường hợp nào có thể dựa vào authorization policy hoặc quan hệ tin cậy đã thiết lập thay vì hiển thị consent tương tác mỗi lần?
Làm thế nào ghi nhận, xem lại và thu hồi consent khi người dùng thay đổi lựa chọn hoặc client không còn cần quyền đã cấp?
Access token và ID token khác nhau về audience, mục đích sử dụng và bên tiêu thụ như thế nào?
Vì sao resource server không nên chấp nhận ID token làm bearer credential cho API chỉ vì chữ ký của token hợp lệ?
Những claim cốt lõi nào trong ID token giúp client xác minh issuer, subject, audience và thời hạn của phiên xác thực?
Client cần kiểm tra issuer, audience, expiration, signature và nonce của ID token theo quy trình nào trước khi tạo phiên đăng nhập?
Khi ID token có nhiều audience, vai trò của azp và quy tắc kiểm tra authorized party cần được áp dụng như thế nào?
Claim sub có ý nghĩa gì trong OIDC, và vì sao client không nên giả định sub luôn giống nhau giữa các client khác nhau?
UserInfo endpoint bổ sung thông tin nào ngoài ID token, và client cần bảo đảm access token gửi tới endpoint có đúng đích sử dụng và scope phù hợp ra sao?
Khi cần chia sẻ dữ liệu người dùng tối thiểu, làm thế nào chọn giữa ID token claims, UserInfo claims và scope được yêu cầu?
Một access token là JWT; resource server cần xác minh những thuộc tính nào ngoài việc kiểm tra chữ ký?
Làm thế nào giới hạn thuật toán ký được chấp nhận để ngăn algorithm confusion hoặc việc token bị xác minh bằng thuật toán ngoài policy?
Resource server nhận JWT có kid; làm thế nào chọn khóa từ JWKS đúng cách và xử lý kid không tồn tại?
JWKS endpoint thay đổi khóa khi nhà cung cấp xoay signing key; client và resource server nên cache, refresh và loại bỏ khóa cũ như thế nào?
Vì sao cần xác minh iss, aud, exp và nbf thay vì chỉ xác nhận JWT có chữ ký hợp lệ?
Opaque access token khác JWT access token về khả năng tự xác minh, phụ thuộc mạng và cách kiểm soát thu hồi ra sao?
Introspection endpoint được dùng trong trường hợp nào, và resource server cần xác minh trạng thái active cùng metadata token như thế nào?
Làm thế nào tránh nhầm lẫn giữa ID token, access token và các JWT khác khi chúng dùng chung định dạng và cùng một issuer?
Khi một token hợp lệ về chữ ký nhưng được phát hành cho API khác, resource server cần phản hồi và ghi nhận sự kiện như thế nào?
DPoP ràng buộc access token với khóa của client ra sao, và proof cần được kiểm tra những thành phần nào để chống replay?
Mutual TLS certificate-bound access token giảm nguy cơ token bị đánh cắp và dùng lại như thế nào?
Khi nào nên chọn bearer token, DPoP hoặc mutual TLS để cân bằng khả năng tương thích, triển khai và bảo vệ token?
Refresh token được sử dụng để lấy access token mới như thế nào, và vì sao nó cần được bảo vệ chặt hơn access token ngắn hạn?
Refresh token rotation hoạt động ra sao, và authorization server có thể phát hiện reuse của token cũ bằng cách nào?
Khi phát hiện refresh token đã bị sử dụng lại sau rotation, hệ thống nên thu hồi token family và xử lý phiên liên quan như thế nào?
Làm thế nào lựa chọn thời hạn access token, refresh token và phiên đăng nhập dựa trên rủi ro, trải nghiệm và khả năng thu hồi?
Revocation endpoint hỗ trợ thu hồi token như thế nào, và client cần hiểu giới hạn của việc thu hồi trong hệ thống phân tán ra sao?
Khi resource server cache kết quả introspection hoặc trạng thái token, độ trễ cache ảnh hưởng việc thực thi revocation như thế nào?
OIDC logout khác với việc xóa cookie cục bộ của một ứng dụng ra sao khi người dùng có phiên SSO tại nhiều client?
RP-Initiated Logout, Front-Channel Logout và Back-Channel Logout giải quyết những tình huống nào và có giới hạn gì?
Làm thế nào đồng bộ trạng thái đăng xuất giữa identity provider, browser và nhiều relying party mà không tạo vòng lặp redirect?
Một ứng dụng dùng authorization code nhưng thiếu state hoặc kiểm tra state sai; attacker có thể khai thác login CSRF hoặc account confusion như thế nào?
Authorization server và client có thể bị tấn công authorization code interception hoặc injection ra sao, và PKCE giảm thiểu nguy cơ ở điểm nào?
OAuth mix-up attack xảy ra trong bối cảnh nhiều authorization server như thế nào, và client có thể ràng buộc phản hồi với đúng issuer bằng cách nào?
Làm thế nào phòng vệ trước open redirect, redirect URI manipulation và leakage của code hoặc token qua browser history, Referer hay log?
Khi access token bị lộ trong URL, telemetry hoặc báo cáo lỗi, tổ chức cần giảm thiểu và xử lý sự cố theo quy trình nào?
Những rủi ro nào phát sinh khi lưu bearer token lâu dài trong local storage, session storage, cookie hoặc secure device storage?
Làm thế nào giảm nguy cơ token bị lấy qua XSS, malware, backup thiết bị hoặc đồng bộ dữ liệu trình duyệt?
Authorization server nên giới hạn tốc độ, phát hiện bất thường và bảo vệ credential endpoint trước brute force hoặc credential stuffing như thế nào?
Client cần xử lý clock skew, token hết hạn và lỗi invalid_grant khi refresh ra sao để tránh vòng lặp retry hoặc gián đoạn phiên?
Làm thế nào quản lý key rotation, signing key compromise và khẩn cấp loại bỏ một khóa đang được dùng để ký token?
Khi discovery metadata hoặc JWKS endpoint không khả dụng, client và resource server nên fail closed hay dùng cache theo chính sách nào?
Authorization Code Flow với PKCE được áp dụng cho confidential web client và public native client khác nhau ở những điểm nào?
Một ứng dụng web server-side cần giữ access token và refresh token; làm thế nào thiết kế server-side session, cookie và CSRF protection?
Một SPA không thể giữ client secret; làm thế nào lựa chọn giữa public client với PKCE và kiến trúc backend-for-frontend?
Một ứng dụng mobile cần hỗ trợ đăng nhập, deep link và refresh token; làm thế nào giảm nguy cơ custom scheme bị ứng dụng khác chiếm callback?
Client Credentials Grant phù hợp với service-to-service authorization trong trường hợp nào, và vì sao nó không đại diện cho danh tính người dùng?
Làm thế nào cấp scope và audience riêng cho từng workload để một service không thể dùng token truy cập mọi API?
Token Exchange có thể hỗ trợ chuyển đổi token theo audience hoặc delegation giữa các dịch vụ như thế nào, và cần giới hạn chuỗi tin cậy ra sao?
Resource server nên phân biệt scope, role, entitlement và policy khi quyết định quyền trên một tài nguyên cụ thể như thế nào?
Làm thế nào xử lý quyền truy cập theo tenant hoặc đối tượng để một access token có scope rộng không tự động cho phép đọc mọi bản ghi?
Khi người dùng được cấp quyền mới hoặc bị thu hồi quyền trong lúc access token cũ vẫn còn hiệu lực, kiến trúc cần phản ánh thay đổi đó như thế nào?
Một tổ chức hỗ trợ nhiều identity provider; làm thế nào quản lý issuer, discovery, client registration và chính sách tin cậy mà tránh nhầm lẫn giữa các nhà cung cấp?
Làm thế nào kiểm thử interoperability giữa authorization server, client và resource server bằng test vector cho redirect, PKCE, token validation, refresh và revocation?
Những log và audit event nào cần được lưu để điều tra sự cố OAuth/OIDC mà không ghi lộ authorization code, access token, refresh token hoặc secret?
Làm thế nào đánh giá định kỳ cấu hình OAuth/OIDC theo threat model, security best current practice và thay đổi của hệ sinh thái?
Device Authorization Grant phù hợp với thiết bị hạn chế nhập liệu như TV trong trường hợp nào, và authorization server cần kiểm soát user code, polling cùng slow_down ra sao?
Pushed Authorization Requests giúp bảo vệ authorization request khỏi sửa đổi ở front channel như thế nào, và client cần xác thực ra sao khi đẩy request tới authorization server?
Vì sao các flow legacy như Implicit Grant và Resource Owner Password Credentials không còn phù hợp cho triển khai mới, và lộ trình chuyển sang Authorization Code với PKCE nên được thiết kế thế nào?
