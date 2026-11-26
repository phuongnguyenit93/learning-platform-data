Bạn sẽ mô tả mô hình tin cậy của một hệ thống dùng access token như thế nào, từ nơi phát hành đến nơi tiêu thụ token?
Những khác biệt cốt lõi giữa JWT và opaque token ảnh hưởng ra sao đến kiến trúc Resource Server?
Trong tình huống nào opaque token phù hợp hơn JWT, và những chi phí vận hành nào cần được tính đến?
JWT tự chứa claims đem lại lợi ích gì và tạo ra những giới hạn nào đối với thu hồi quyền tức thời?
Bạn phân biệt access token, refresh token và ID Token theo mục đích, nơi sử dụng và mức độ nhạy cảm như thế nào?
Vòng đời đầy đủ của một access token trong OAuth 2.0 gồm những bước nào và các bên nào chịu trách nhiệm ở từng bước?
Authorization Server cần xác định những yếu tố nào trước khi phát hành token cho một client?
Bạn sẽ thiết kế chính sách thời hạn access token và refresh token dựa trên rủi ro, trải nghiệm người dùng và khả năng thu hồi ra sao?
Những thông tin nào nên và không nên được đưa vào JWT claims, và bạn sẽ đánh giá nguy cơ riêng tư như thế nào?
Bạn giải thích vai trò của `iss`, `sub`, `aud`, `exp`, `nbf`, `iat` và `jti` trong việc xác minh token như thế nào?
Vì sao Resource Server phải kiểm tra audience thay vì chỉ xác minh chữ ký và thời hạn của token?
Bạn sẽ xử lý trường hợp `aud` chứa nhiều giá trị và API chỉ được phép nhận một audience cụ thể như thế nào?
Những rủi ro nào xuất hiện khi Resource Server không kiểm tra issuer hoặc chấp nhận nhiều issuer mà không phân tách policy?
Bạn sẽ thiết kế kiểm tra `exp`, `nbf`, `iat` và clock skew thế nào để tránh cả việc từ chối nhầm lẫn lẫn chấp nhận token quá hạn?
Bạn sẽ chọn và áp dụng allowlist thuật toán ký JWT ra sao để tránh algorithm confusion hoặc thuật toán yếu?
Những bước nào cần được thực hiện khi xác minh chữ ký JWT bằng khóa lấy từ JWKS endpoint?
Bạn sẽ xử lý `kid` không tồn tại, trùng lặp hoặc có định dạng bất thường trong JWT header như thế nào?
Quy trình rotation signing key nên phối hợp issuer, JWKS cache và Resource Server ra sao để không gián đoạn dịch vụ?
Khi signing key bị lộ, bạn sẽ xác định phạm vi ảnh hưởng và thu hồi niềm tin vào khóa đó như thế nào?
Bạn phân biệt JWS và JWE ra sao, và vì sao việc ký JWT không đồng nghĩa với mã hóa claims?
Opaque token được Resource Server xác minh qua introspection endpoint theo luồng nào?
Resource Server nên diễn giải trường `active` trong introspection response như thế nào và cần kiểm tra thêm những trường nào?
Bạn sẽ xử lý một introspection response thiếu trường bắt buộc, sai kiểu dữ liệu hoặc đến từ issuer không mong đợi ra sao?
Những thông tin nào trong introspection response cần được kiểm tra trước khi cho phép một thao tác API cụ thể?
Bạn sẽ thiết kế client authentication cho introspection endpoint như thế nào để chỉ Resource Server được ủy quyền mới có thể truy vấn token?
Những trade-off nào cần cân nhắc khi Resource Server cache kết quả introspection để giảm độ trễ và tải cho Authorization Server?
Bạn sẽ chọn TTL cho positive cache và negative cache dựa trên thời hạn token, yêu cầu thu hồi và mức độ nhạy cảm của API như thế nào?
Khi token bị thu hồi, cơ chế nào giúp invalidation cache lan tới tất cả Resource Server và region?
Bạn sẽ cân bằng fail-open và fail-closed khi Authorization Server hoặc introspection endpoint mất kết nối ra sao?
Những biện pháp timeout, retry, circuit breaker và rate limit nào giúp introspection không tạo retry storm khi phụ thuộc gặp sự cố?
Bạn sẽ phân biệt token inactive với lỗi mạng, lỗi xác thực client và lỗi nội bộ của Authorization Server như thế nào trong logic ứng dụng?
Scope và audience khác nhau ra sao, và chúng phối hợp thế nào để giới hạn quyền truy cập resource?
Bạn sẽ thiết kế scope theo tài nguyên và hành động như thế nào để tránh cấp quyền quá rộng cho client?
Vì sao scope hợp lệ vẫn chưa đủ để bảo đảm người dùng được phép truy cập một object cụ thể?
Bạn sẽ kết hợp scope, subject, tenant và quyền sở hữu object ở Resource Server như thế nào để ngăn truy cập chéo tenant?
Những rủi ro nào phát sinh khi Resource Server dùng substring hoặc so khớp lỏng lẻo để kiểm tra scope?
Bạn sẽ xử lý claims về role hoặc group khi quyền người dùng thay đổi trong lúc access token cũ vẫn còn hiệu lực ra sao?
Authorization Code Flow với PKCE bảo vệ public client khỏi những kiểu tấn công nào?
Bạn giải thích vai trò của `state` và `nonce` trong OIDC authorization flow, và cách kiểm tra chúng ở callback như thế nào?
Bạn sẽ ràng buộc redirect URI ra sao để tránh open redirect và đánh cắp authorization code?
Những rủi ro nào xuất hiện khi một client kết nối nhiều Authorization Server mà không ràng buộc response với issuer đã khởi tạo luồng?
Vì sao không nên nhúng client secret cố định trong ứng dụng mobile hoặc ứng dụng chạy trong trình duyệt?
Bạn sẽ lựa chọn giữa Authorization Code, Client Credentials và các grant phù hợp khác theo loại client và principal như thế nào?
Token exchange giải quyết nhu cầu chuyển đổi audience hoặc delegation nào, và cần giới hạn trust chain ra sao?
Refresh token rotation hoạt động như thế nào và reuse detection giúp phát hiện tình huống đánh cắp ra sao?
Bạn sẽ xử lý hai request refresh đồng thời từ nhiều tab hoặc nhiều instance client như thế nào để tránh false-positive reuse?
Khi refresh token bị phát hiện tái sử dụng, những token hoặc phiên nào cần bị thu hồi và cần điều tra điều gì?
Đăng xuất khỏi một ứng dụng nên tác động tới access token, refresh token, phiên cục bộ và các phiên SSO khác như thế nào?
Bạn sẽ thiết kế thu hồi token cho JWT tự xác minh cục bộ khi cần chặn quyền truy cập trước thời điểm `exp` như thế nào?
Những giới hạn của denylist, token introspection và short-lived token cần được cân nhắc khi thiết kế revocation?
Bạn sẽ bảo vệ bearer token khỏi replay nếu token bị sao chép sang một thiết bị khác như thế nào?
DPoP ràng buộc access token với khóa của client ra sao, và Resource Server cần xác minh proof những gì?
Bạn sẽ ngăn DPoP proof bị replay bằng `jti`, timestamp và cơ chế lưu dấu đã dùng như thế nào?
mTLS certificate-bound access token khác bearer token thông thường ở điểm nào và proxy termination làm phức tạp việc xác minh ra sao?
Bạn sẽ lựa chọn DPoP hay mTLS cho từng loại client và môi trường triển khai dựa trên những tiêu chí nào?
Những rủi ro nào xuất hiện khi access token hoặc refresh token được lưu trong localStorage, sessionStorage hay cookie?
Bạn sẽ giảm nguy cơ token bị đánh cắp qua XSS, CSRF, URL, Referer, browser history và crash dump như thế nào?
Những quy tắc nào nên áp dụng để log và trace request mà không làm lộ token hoặc claims nhạy cảm?
Bạn sẽ thiết kế kho lưu trữ token phía server để giới hạn quyền đọc, mã hóa dữ liệu và hỗ trợ thu hồi như thế nào?
Workload sử dụng client credentials nên nhận diện và bảo vệ token ra sao để tránh chia sẻ credential giữa nhiều dịch vụ?
Bạn sẽ quản lý token trong môi trường nhiều tenant để tránh cache key, introspection context hoặc policy bị dùng chéo tenant như thế nào?
Những rủi ro nào xuất hiện khi một Resource Server dùng chung cache introspection cho nhiều issuer hoặc nhiều audience?
Bạn sẽ thiết kế rate limit và chống dò token để endpoint introspection không trở thành điểm DoS hoặc kênh xác nhận token hợp lệ như thế nào?
Những chỉ số và sự kiện nào giúp phát hiện token bị sử dụng bất thường, chẳng hạn cùng token xuất hiện ở nhiều vị trí hoặc thiết bị?
Khi phát hiện bearer token bị lộ trong log, bạn sẽ khoanh vùng, thu hồi, đánh giá dữ liệu bị truy cập và bảo toàn bằng chứng ra sao?
Bạn sẽ xây dựng inventory token hoặc token reference như thế nào để liên kết subject, client, audience, scope, thời điểm phát hành và trạng thái thu hồi mà không lưu token thô?
Những kiểm thử bảo mật nào cần có cho JWT validation, introspection, cache invalidation, refresh rotation và revocation?
Bạn sẽ kiểm chứng hành vi của Resource Server khi Authorization Server chậm, mất kết nối, trả response sai hoặc phục hồi sau outage như thế nào?
Những quyết định thiết kế nào giúp hệ thống thay đổi signing key, issuer hoặc chính sách token mà không làm suy giảm khả năng tương thích và an toàn?
Bạn sẽ đánh giá tổng thể trade-off giữa khả năng thu hồi tức thời, tính sẵn sàng, độ trễ và khả năng mở rộng trong kiến trúc token như thế nào?
Khi bearer token hoặc signing key bị compromise, bạn sẽ tổ chức ứng phó sự cố, thu hồi quyền, xoay khóa, bảo toàn bằng chứng và kiểm chứng biện pháp khắc phục như thế nào?
