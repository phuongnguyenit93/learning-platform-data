Trong một hệ thống token-based authentication, những thành phần nào tham gia vào quá trình phát hành, truyền nhận và xác minh token?
Làm thế nào phân biệt token dùng để chứng minh danh tính với token dùng để cấp quyền truy cập tài nguyên?
Bearer token và proof-of-possession token khác nhau như thế nào về cách ràng buộc người sử dụng token?
Trong những tình huống nào opaque token phù hợp hơn token tự chứa thông tin như JWT?
JWT gồm những thành phần nào và mỗi thành phần đóng vai trò gì trong quá trình xác minh?
JWS và JWE giải quyết những nhu cầu bảo vệ token khác nhau như thế nào?
Khi nào nên ký token, khi nào cần mã hóa token, và vì sao hai cơ chế này không thể thay thế cho nhau?
Access token, refresh token và ID token có mục đích và đối tượng sử dụng khác nhau ra sao?
API key khác access token như thế nào về danh tính, phạm vi quyền và vòng đời quản lý?
Những đặc tính nào giúp một token có entropy đủ cao để chống đoán và dò tìm?
Một tổ chức nên lựa chọn token opaque, JWT hay định dạng khác dựa trên các tiêu chí kiến trúc nào?
Quy trình phát hành token nên xác minh danh tính người dùng hoặc workload ở những bước nào?
Các vai trò client, authorization server, resource owner và resource server phối hợp với nhau ra sao trong OAuth 2.0?
OpenID Connect bổ sung lớp xác thực danh tính cho OAuth 2.0 như thế nào?
Vì sao ID token không nên được dùng thay access token khi gọi API?
Một authorization server cần xác thực client như thế nào trước khi phát hành token cho ứng dụng hoặc workload?
Làm thế nào xác định audience chính xác để token chỉ có thể được dùng tại resource server dự kiến?
Scope, role và permission khác nhau như thế nào khi biểu diễn quyền truy cập trong token?
Làm thế nào thiết kế claim để hỗ trợ quyết định phân quyền mà không đưa quá nhiều dữ liệu cá nhân vào token?
Những rủi ro nào xuất hiện khi resource server tin cậy trực tiếp các custom claim do issuer bên ngoài phát hành?
Khi hệ thống có nhiều tenant, làm thế nào ràng buộc tenant context trong token với danh tính đã được xác thực?
Token được ủy quyền thay mặt người dùng nên thể hiện subject, client và actor như thế nào để tránh nhầm lẫn danh tính?
Token exchange có thể giải quyết những bài toán delegation giữa nhiều dịch vụ như thế nào?
Làm thế nào cấp token cho workload hoặc service account mà không nhúng secret dài hạn vào mã nguồn hay image triển khai?
Những thông tin nào resource server phải kiểm tra trước khi chấp nhận một JWT đã nhận?
Vì sao cần giới hạn thuật toán ký được chấp nhận thay vì tin giá trị alg do token tự khai báo?
Những rủi ro nào liên quan đến việc chấp nhận thuật toán none hoặc nhầm lẫn giữa thuật toán đối xứng và bất đối xứng?
Issuer, audience, expiration, not-before và issued-at hỗ trợ xác minh token như thế nào?
Làm thế nào xử lý clock skew giữa authorization server và resource server mà không kéo dài thời gian token có hiệu lực quá mức?
JWKS và trường kid hỗ trợ chọn khóa xác minh ra sao, và cần xử lý thế nào khi khóa chưa có trong cache?
Vì sao resource server không nên tải khóa xác minh từ URL tùy ý được khai báo bên trong token?
Làm thế nào ngăn việc dùng một loại JWT hợp lệ trong sai ngữ cảnh hoặc sai mục đích?
Khi sử dụng opaque token, introspection endpoint cung cấp thông tin gì cho resource server?
Cache kết quả introspection có thể cải thiện hiệu năng và đồng thời tạo ra rủi ro thu hồi chậm như thế nào?
Những trường hợp nào cần kiểm tra token trực tuyến với issuer thay vì chỉ xác minh chữ ký cục bộ?
HTTPS bảo vệ token trong quá trình truyền như thế nào và những rủi ro nào vẫn tồn tại ở endpoint?
Vì sao bearer token nên được truyền qua Authorization header thay vì query string hoặc URL?
Nếu token được lưu trong cookie trình duyệt, cần cân nhắc Secure, HttpOnly, SameSite và CSRF như thế nào?
Những đánh đổi bảo mật và trải nghiệm nào cần xem xét khi lưu token trong cookie, bộ nhớ ứng dụng hoặc secure storage của thiết bị?
Làm thế nào giảm nguy cơ token xuất hiện trong access log, URL, browser history, crash report hoặc telemetry?
Một ứng dụng web cần bảo vệ token trước XSS và CSRF như thế nào trong cùng một thiết kế?
Ứng dụng di động nên lưu refresh token và access token ra sao để hạn chế truy cập trái phép từ thiết bị?
Vì sao access token thường nên có thời hạn ngắn hơn refresh token, và thời hạn nên được lựa chọn theo yếu tố nào?
Refresh token rotation hoạt động ra sao và hệ thống có thể phát hiện việc sử dụng lại refresh token cũ như thế nào?
Khi người dùng đăng xuất, hệ thống cần xử lý access token, refresh token và phiên đăng nhập ở các thành phần nào?
Những chiến lược thu hồi token nào có thể áp dụng cho JWT tự chứa và opaque token?
Làm thế nào cân bằng giữa xác minh JWT không trạng thái, khả năng thu hồi tức thời và độ sẵn sàng khi issuer gặp sự cố?
Khi khóa ký token cần được xoay vòng, quy trình phát hành khóa mới, công bố khóa và ngừng tin khóa cũ nên diễn ra thế nào?
Nếu private signing key bị lộ, tổ chức cần ứng phó ra sao để giới hạn token giả mạo và khôi phục niềm tin?
KMS hoặc HSM có thể hỗ trợ bảo vệ và kiểm soát việc sử dụng khóa ký token như thế nào?
Làm thế nào quản lý secret của client, chứng thư và khóa ký qua các môi trường phát triển, kiểm thử và production?
Những cách tấn công nào có thể khiến token bị đánh cắp từ trình duyệt, thiết bị, log hoặc kênh trao đổi?
Token replay xảy ra trong những điều kiện nào và có thể phát hiện hoặc giảm thiểu bằng biện pháp gì?
DPoP ràng buộc access token với khóa của client như thế nào và resource server cần xác minh proof ra sao?
mTLS-bound access token giúp hạn chế việc sử dụng token bị đánh cắp như thế nào?
Trong tình huống nào sender-constrained token đáng được ưu tiên hơn bearer token thông thường?
Nonce, jti, timestamp và cơ chế chống trùng lặp có thể hỗ trợ phòng chống replay ra sao?
Làm thế nào phát hiện token bị sử dụng đồng thời từ nhiều vị trí hoặc thiết bị bất thường mà vẫn hạn chế cảnh báo giả?
Những lỗi thiết kế nào có thể khiến token hợp lệ bị nâng quyền ngoài dự kiến?
Làm thế nào ngăn confused deputy khi một dịch vụ dùng token của mình để truy cập tài nguyên thay mặt người dùng?
Việc cấp scope quá rộng ảnh hưởng thế nào đến blast radius khi token bị lộ?
Làm thế nào bảo đảm resource server chỉ cho phép đúng hành động trên đúng tài nguyên, thay vì coi token hợp lệ là đủ?
Khi token mang quyền truy cập nhiều API, làm thế nào tách audience và scope để giảm khả năng token bị dùng sai nơi?
Những dấu hiệu nào trong audit log có thể cho thấy token bị lạm dụng, chia sẻ hoặc phát lại?
Làm thế nào ghi nhận sự kiện phát hành, refresh, introspection, thu hồi và từ chối token mà không ghi lộ credential?
Một thiết kế token-based authentication nên được threat-model theo tài sản, ranh giới tin cậy, tác nhân và luồng dữ liệu như thế nào?
Những ca kiểm thử nào cần có để xác minh token hết hạn, sai issuer, sai audience, sai chữ ký và chưa đến thời điểm hiệu lực đều bị từ chối?
Làm thế nào kiểm thử hành vi của hệ thống khi khóa ký bị xoay vòng, cache JWKS cũ hoặc issuer tạm thời không khả dụng?
Những kiểm thử nào giúp phát hiện lỗi refresh-token rotation, reuse detection và race condition giữa các yêu cầu làm mới?
Làm thế nào kiểm tra rằng việc thu hồi token có hiệu lực trên tất cả gateway, resource server và vùng triển khai?
Khi thiết kế lại một hệ thống dùng token lâu năm, cần đánh giá những luồng tin cậy và phụ thuộc nào trước khi thay đổi định dạng hoặc issuer?
