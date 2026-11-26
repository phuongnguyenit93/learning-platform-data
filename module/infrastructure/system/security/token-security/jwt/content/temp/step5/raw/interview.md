JWT giải quyết bài toán truyền tải claims giữa các thành phần như thế nào, và những giới hạn nào khiến nó không nên được xem là cơ chế bảo mật hoàn chỉnh?
JWT khác OAuth 2.0 và OpenID Connect ở vai trò nào, và vì sao việc dùng JWT không tự tạo ra một giao thức đăng nhập?
Ba phần của compact JWS gồm những gì, và mỗi phần tham gia vào dữ liệu được xác minh chữ ký như thế nào?
Base64url trong JWT có đặc điểm gì so với Base64 thông thường, và vì sao việc encode không bảo vệ bí mật nội dung?
Chữ ký JWS cung cấp những bảo đảm nào về tính toàn vẹn và nguồn phát hành, đồng thời không cung cấp bảo đảm nào về tính bí mật?
Khi nào nên dùng JWE thay vì JWS, và cần đánh giá thêm những rủi ro nào khi mã hóa claims?
Nested JWT kết hợp JWS và JWE theo những thứ tự nào, và thứ tự ký rồi mã hóa có ý nghĩa gì đối với bên nhận?
JOSE header và JWT payload có trách nhiệm khác nhau ra sao, và vì sao không nên đặt dữ liệu nhạy cảm vào header?
Registered claims, public claims và private claims khác nhau như thế nào trong hợp đồng token?
Làm thế nào đặt tên custom claim để tránh xung đột giữa các issuer hoặc giữa các miền nghiệp vụ?
Bạn sẽ quản trị issuer identifier như thế nào để resource server biết chính xác nguồn phát hành token nào được tin cậy?
Subject claim nên đại diện cho loại định danh nào, và làm thế nào bảo đảm subject ổn định trong phạm vi một issuer?
Khi aud là một chuỗi hoặc một mảng audience, resource server nên xác định token có được phát hành cho mình như thế nào?
Bạn sẽ diễn giải exp và thời điểm hết hạn ra sao để tránh chấp nhận token đã hết hạn ở ranh giới thời gian?
nbf và clock skew ảnh hưởng thế nào đến quyết định chấp nhận token, và làm sao đặt dung sai thời gian có giới hạn?
iat có thể hỗ trợ phát hiện token phát hành trong tương lai hoặc quá cũ như thế nào, và những giả định nào cần được xác minh?
jti có thể được dùng để định danh một token ra sao, và trong điều kiện nào nó giúp phát hiện phát lại?
Bạn sẽ chọn claims nào đưa vào access token để cân bằng giữa nhu cầu xử lý của resource server, kích thước token và tối thiểu hóa dữ liệu?
Làm thế nào phân biệt claim do issuer xác minh với dữ liệu do client tự gửi, và tránh dùng claim không đáng tin để ra quyết định quyền?
Trong hệ thống đa tenant, bạn sẽ ràng buộc tenant claim với issuer, audience và tài nguyên như thế nào để tránh truy cập chéo tenant?
Khi quyền của người dùng thay đổi nhưng JWT cũ vẫn còn hạn, bạn sẽ xử lý nguy cơ role hoặc permission claim bị lỗi thời ra sao?
ID Token và access token khác nhau về mục đích, audience và cách consumer sử dụng như thế nào trong OpenID Connect?
Bạn sẽ so sánh JWT access token với opaque access token theo khả năng xác minh cục bộ, thu hồi, quan sát và vận hành như thế nào?
Refresh token cần có vòng đời và biện pháp bảo vệ khác access token ra sao, và khi nào nên chọn refresh token dạng opaque?
Vì sao hợp đồng token nên xác định typ hoặc loại token rõ ràng, và cách này giúp ngăn token substitution giữa các ngữ cảnh như thế nào?
Trong môi trường production, vì sao nên từ chối JWT dùng thuật toán none, kể cả khi thư viện có hỗ trợ định dạng unsecured JWT?
Bạn sẽ thiết kế allowlist thuật toán ký theo issuer và loại khóa như thế nào để không phụ thuộc mù quáng vào alg do token gửi lên?
Thuật toán confusion giữa HMAC và RSA có thể xảy ra như thế nào, và cách ràng buộc thuật toán với loại khóa ngăn được lỗi đó ra sao?
Việc dùng HMAC cho JWS tạo ra những yêu cầu gì về chia sẻ secret, phân phối khóa và quyền của các bên xác minh?
Bạn sẽ đánh giá entropy, độ dài và cách lưu trữ HMAC secret như thế nào để chống dò đoán và giảm tác động khi lộ khóa?
Khi lựa chọn RSA, RSA-PSS, ECDSA hoặc EdDSA cho JWS, bạn sẽ cân nhắc khả năng tương thích, hiệu năng và yêu cầu bảo mật nào?
Đường cong elliptic và kích thước khóa ảnh hưởng thế nào đến mức an toàn, hiệu năng và khả năng hỗ trợ của các bên tham gia?
kid trong JOSE header được dùng để chọn khóa xác minh như thế nào, và vì sao nó chỉ nên là gợi ý tra cứu trong tập khóa đã tin cậy?
Bạn sẽ phòng ngừa path traversal, injection hoặc truy vấn ngoài ý muốn khi xử lý kid do token không đáng tin gửi lên như thế nào?
Các trường kty, use, key_ops, alg và crv trong JWK giúp xác định điều gì, và cần kiểm tra tính nhất quán giữa chúng ra sao?
Resource server nên xác định JWKS endpoint từ nguồn cấu hình hoặc metadata tin cậy như thế nào để tránh SSRF qua jku hoặc x5u do token điều khiển?
Bạn sẽ thiết kế cache JWKS theo TTL, refresh khi gặp kid chưa biết và xử lý stale key như thế nào để cân bằng an toàn với tính sẵn sàng?
Quy trình xoay vòng signing key nên công bố khóa mới, phát hành token và giữ khóa cũ trong khoảng chồng lấn như thế nào?
Nếu private signing key bị lộ, bạn sẽ phối hợp thu hồi khóa, cập nhật JWKS, vô hiệu token và điều tra token đã phát hành ra sao?
Khi một resource server chấp nhận nhiều issuer, bạn sẽ cô lập trust store, thuật toán, audience và chính sách claims giữa các issuer như thế nào?
Vì sao JWS xác minh trên signing input chính xác của thông điệp, và điều gì có thể sai nếu ứng dụng parse rồi serialize lại JSON trước khi kiểm tra chữ ký?
Header cần được đọc một phần để chọn khóa trước khi xác minh; bạn sẽ giới hạn việc sử dụng dữ liệu header chưa được xác thực như thế nào?
JSON object trong JWT có thể chứa tên member trùng lặp; parser nên xử lý trường hợp này ra sao để tránh khác biệt giữa các thành phần?
JOSE header parameter crit có ý nghĩa gì, và consumer nên phản ứng thế nào khi gặp extension bắt buộc mà nó không hiểu?
Trong trường hợp dùng detached payload hoặc b64=false của JWS, hợp đồng ký và cách xác minh cần quy định thêm những gì?
Trong JWE, tham số alg và enc đại diện cho hai lớp thuật toán nào, và vì sao không được nhầm lẫn vai trò của chúng?
Authentication tag của JWE bảo vệ điều gì, và ứng dụng nên xử lý ra sao khi giải mã hoặc xác minh tag thất bại?
JWE mã hóa cho người nhận có tự chứng minh danh tính người gửi hay không, và khi cần xác thực issuer bạn sẽ kết hợp cơ chế nào?
Việc nén plaintext trước khi mã hóa token có thể tạo ra rủi ro rò rỉ qua side channel nào, và khi nào nên tránh bật compression?
Bạn sẽ lựa chọn direct encryption, key wrapping hoặc key agreement trong JWE theo mô hình khóa và số lượng người nhận như thế nào?
Private signing key và decryption key cần được bảo vệ, phân quyền, backup và kiểm soát truy cập như thế nào trong suốt vòng đời?
Bạn sẽ thiết kế chuỗi xác minh token từ kiểm tra định dạng, chọn issuer/key, xác minh chữ ký đến kiểm tra claims theo thứ tự nào?
Đồng hồ giữa issuer và resource server lệch nhau có thể gây lỗi gì cho exp, nbf và iat, và cần giám sát đồng bộ thời gian ra sao?
Chữ ký hợp lệ có đủ để cho phép một hành động nghiệp vụ hay không, và bạn sẽ tách xác thực token khỏi quyết định authorization như thế nào?
Resource server nên kiểm tra audience, scope hoặc quyền được cấp cho chính tài nguyên của mình như thế nào trước khi xử lý request?
Token substitution giữa ID Token, access token, token reset mật khẩu hoặc token cho mục đích khác có thể xảy ra ra sao, và cách ngăn chặn là gì?
Bearer JWT có thể bị phát lại trong những tình huống nào, và chữ ký hợp lệ không giải quyết được rủi ro replay ra sao?
Bạn sẽ thiết kế one-time use bằng jti, nonce hoặc trạng thái phía server như thế nào mà không tạo ra điểm nghẽn không cần thiết?
Những biện pháp nào bảo vệ bearer token khi truyền qua mạng, qua proxy và qua các dịch vụ trung gian?
DPoP hoặc mutual TLS có thể ràng buộc token với client hay khóa của người gửi như thế nào, và chúng giải quyết giới hạn nào của bearer token?
Bạn sẽ đánh giá việc lưu token trong cookie, memory hoặc browser storage theo nguy cơ XSS, CSRF và khả năng khôi phục phiên ra sao?
Khi token được lưu trong cookie tự động gửi kèm request, bạn sẽ thiết kế SameSite, Secure, HttpOnly và CSRF protection như thế nào?
XSS có thể đánh cắp hoặc sử dụng token trong ngữ cảnh người dùng như thế nào, và những lớp phòng vệ nào giúp giảm thiểu tác động?
Bạn sẽ chọn thời hạn access token dựa trên độ nhạy cảm, mức độ phơi nhiễm, khả năng refresh và yêu cầu trải nghiệm như thế nào?
Vì sao JWT thường khó thu hồi tức thời hơn opaque token, và các chiến lược thu hồi nào phù hợp với từng yêu cầu?
Bạn sẽ triển khai denylist theo jti hoặc token hash như thế nào để hỗ trợ thu hồi mà không lưu trữ nguyên token?
Token introspection và kiểm tra JWT cục bộ khác nhau ra sao về độ trễ, tính cập nhật trạng thái, khả năng sẵn sàng và phụ thuộc mạng?
Token exchange hoặc delegation nên giới hạn audience, scope, actor và thời hạn như thế nào để tránh quyền lan truyền quá mức?
Khi một service gọi service khác, bạn sẽ quyết định chuyển tiếp access token hiện tại hay đổi lấy token mới theo nguyên tắc nào?
Log và trace nên ghi những metadata nào để điều tra sự cố JWT mà không làm lộ toàn bộ token hoặc claims nhạy cảm?
Bạn sẽ thiết kế lỗi xác minh token sao cho có thể quan sát và chẩn đoán nhưng không tiết lộ thông tin giúp kẻ tấn công dò cấu hình?
Bạn sẽ xây dựng bộ negative test cho sai chữ ký, sai thuật toán, issuer/audience không khớp, token hết hạn và claim thiếu như thế nào?
Những kiểm thử nào giúp phát hiện algorithm confusion, kid injection, JWKS trust lỗi và token substitution trước khi triển khai?
Bạn sẽ fuzz JOSE header, JSON claims và các trường hợp serialization bất thường như thế nào để kiểm tra parser và verifier?
Khi access token bị lộ trong log hoặc public repository, các bước containment, revoke, rotation và điều tra nào cần thực hiện theo thứ tự?
Bạn sẽ phát hiện việc sử dụng JWT bất thường dựa trên issuer, subject, audience, jti, vị trí, tần suất và mẫu truy cập như thế nào?
Làm thế nào giảm dữ liệu cá nhân trong claims, và khi nào JWE thực sự cần thiết thay vì loại bỏ dữ liệu nhạy cảm khỏi token?
Bạn sẽ kiểm chứng hợp đồng JWT giữa issuer và nhiều resource server qua versioning, backward compatibility và thay đổi claim như thế nào?
