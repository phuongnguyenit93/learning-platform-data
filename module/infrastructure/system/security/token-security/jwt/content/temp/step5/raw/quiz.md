Một JWT compact có ba phần được ngăn bởi dấu chấm thường biểu diễn cấu trúc nào?
A. JWE gồm header, IV, ciphertext, tag và encrypted key.
B. JWS gồm protected header, payload và chữ ký.
C. JWT chỉ có header và payload, chữ ký nằm ngoài token.
D. JWE gồm header, encrypted key và ciphertext.
Đáp án đúng: B

Ứng dụng đọc payload JWT bằng Base64URL decode; kết luận nào đúng về tính bí mật?
A. Base64URL bảo vệ payload bằng khóa công khai của issuer.
B. Payload được ẩn nội dung cho đến khi chữ ký được xác minh.
C. Base64URL chỉ đổi cách biểu diễn, không che nội dung.
D. Base64URL tự mã hóa claims và chỉ API đích giải mã được.
Đáp án đúng: C

Claim `iss` trong một JWT thường xác định thông tin nào?
A. Định danh người dùng hoặc chủ thể được token mô tả.
B. Danh sách resource server được phép nhận và xử lý token này.
C. Thời điểm token bắt đầu có hiệu lực trên mọi hệ thống.
D. Định danh bên phát hành token theo hợp đồng đã tin cậy.
Đáp án đúng: D

Một hệ thống đa tenant dùng JWT; cách diễn giải `sub` nào phù hợp?
A. Mã tenant toàn cục, luôn duy nhất giữa mọi issuer và hệ thống.
B. Chủ thể của token, cần ánh xạ đúng trong phạm vi issuer và tenant.
C. Tên client đã yêu cầu token trong authorization request, không phải người dùng cuối.
D. Danh sách quyền truy cập được cấp cho principal trong token.
Đáp án đúng: B

Resource server kiểm tra `exp`, `nbf` và `iat`; cách áp dụng nào đúng?
A. Chỉ kiểm tra `iat` vì claim này thay thế cả `exp` lẫn `nbf`.
B. Chấp nhận token trước `nbf` nếu chữ ký và issuer đều hợp lệ.
C. Kiểm tra hết hạn, thời điểm bắt đầu và chính sách tuổi token.
D. Dùng `exp` làm thời điểm phát hành và `iat` làm thời điểm hết hạn.
Đáp án đúng: C

Claim `jti` hữu ích nhất cho mục đích nào trong vòng đời token?
A. Mã hóa payload để chỉ chủ thể có khóa riêng mới đọc được claims.
B. Chứng minh chữ ký hợp lệ mà không cần kiểm tra khóa công khai.
C. Mã định danh token để đối chiếu trạng thái.
D. Xác định audience mặc định khi token không chứa claim `aud`.
Đáp án đúng: C

JWS verifier cần tái tạo signing input theo quy tắc nào?
A. Giải mã JSON rồi serialize lại header và payload theo thứ tự bất kỳ.
B. Băm riêng payload đã decode rồi nối với chữ ký nhận được.
C. Nối header, payload và chữ ký rồi mã hóa toàn bộ bằng Base64URL.
D. Dùng Base64URL(header) nối dấu chấm với Base64URL(payload).
Đáp án đúng: D

Một JWE compact theo dạng chuẩn có bao nhiêu phần được phân tách bằng dấu chấm?
A. Ba phần gồm header, plaintext và chữ ký xác minh nội dung.
B. Bốn phần gồm header, IV, ciphertext và chữ ký của issuer.
C. Hai phần gồm protected header và ciphertext đã mã hóa.
D. Năm phần: header, encrypted key, IV, ciphertext và tag.
Đáp án đúng: D

Khi chọn giữa JWS và JWE, khác biệt bảo mật cốt lõi nào cần nhớ?
A. JWS mã hóa payload; JWE chỉ thêm chữ ký cho payload đó.
B. JWS xác thực người dùng; JWE thiết lập phiên đăng nhập OAuth.
C. JWS ký nội dung; JWE mã hóa và bảo vệ nội dung.
D. Hai định dạng có cùng bảo đảm, chỉ khác cách biểu diễn JSON.
Đáp án đúng: C

Verifier nên quyết định thuật toán xác minh chữ ký JWT bằng cách nào?
A. Chấp nhận mọi giá trị `alg` vì header đã nằm trong token được ký.
B. Chọn thuật toán có trong header rồi tải khóa tương ứng từ URL bất kỳ.
C. Thử lần lượt mọi thuật toán thư viện hỗ trợ đến khi chữ ký khớp.
D. Áp dụng allowlist theo hợp đồng và loại khóa được cấu hình tin cậy.
Đáp án đúng: D

Một API nhận JWT có `alg=none`; cách xử lý an toàn nào phù hợp?
A. Chấp nhận token nếu `iss` và `aud` khớp cấu hình của API.
B. Từ chối token vì API yêu cầu chữ ký được xác minh.
C. Chấp nhận token khi payload có `exp` ngắn và `jti` duy nhất.
D. Bổ sung HMAC mặc định cho token vì header không nêu thuật toán.
Đáp án đúng: B

Lỗi algorithm confusion giữa RS256 và HS256 thường xảy ra khi nào?
A. Issuer ký RS256 nhưng verifier chỉ hỗ trợ giải mã JWE bằng RSA.
B. Verifier dùng RSA public key như HMAC secret theo `alg` từ token.
C. Verifier dùng RSA private key để xác minh chữ ký HMAC của issuer.
D. JWKS công bố nhiều khóa RSA nhưng không có trường `kid` tương ứng.
Đáp án đúng: B

Khi ràng buộc thuật toán với khóa xác minh, quy tắc nào an toàn?
A. Cho phép cùng một khóa dùng RSA, HMAC và ECDSA để dễ xoay vòng.
B. Chọn loại khóa theo dữ liệu do client gửi trong phần payload.
C. Dùng bất kỳ khóa JWKS nào nếu thư viện báo chữ ký hợp lệ.
D. Chỉ dùng khóa đúng loại, mục đích và thuật toán đã được cấu hình.
Đáp án đúng: D

Một hệ thống ký HMAC JWT bằng secret dễ đoán; rủi ro chính là gì?
A. Kẻ tấn công có thể đọc payload dù token chỉ dùng JWS.
B. Verifier không thể kiểm tra `aud` khi secret có entropy thấp.
C. Kẻ tấn công có thể đoán secret và tự tạo token có chữ ký hợp lệ.
D. Secret yếu chỉ làm lộ payload, không thể tạo chữ ký giả.
Đáp án đúng: C

Header `kid` được dùng để chọn khóa; cách triển khai nào tránh lỗi tra cứu khóa?
A. Ghép `kid` vào đường dẫn tệp rồi đọc khóa theo chuỗi nhận được.
B. Dùng `kid` làm URL tải khóa mà không kiểm tra nguồn phát hành.
C. Tra `kid` trong key set tin cậy, không dùng làm path.
D. Bỏ qua `kid` và dùng khóa mới nhất trong mọi trường hợp.
Đáp án đúng: C

Verifier cần lấy JWKS của issuer; nguồn nào nên được tin cậy?
A. Trường `jku` trong mỗi token vì nó chỉ định nơi có khóa phù hợp.
B. URL `x5u` trong header vì certificate luôn xác minh được issuer.
C. Bất kỳ URL nào trả JSON có cấu trúc JWKS hợp lệ.
D. Dùng JWKS URI đã cấu hình cho issuer tin cậy.
Đáp án đúng: D

Issuer xoay signing key; cách triển khai nào giảm lỗi xác minh trong thời gian chuyển đổi?
A. Xóa khóa cũ ngay khi tạo khóa mới rồi cập nhật verifier sau đó.
B. Công bố khóa mới trước khi ký, giữ khóa cũ đến khi token cũ hết hạn.
C. Chỉ thay `kid` trong token mà không thay khóa ký thực tế.
D. Giữ một khóa duy nhất và đổi nội dung JWKS sau mỗi request.
Đáp án đúng: B

Private signing key bị nghi lộ; hành động nào cần ưu tiên?
A. Chỉ xóa khóa khỏi JWKS công khai rồi tiếp tục ký bằng khóa hiện tại.
B. Tăng thời hạn token đã phát hành để tránh gián đoạn người dùng.
C. Chỉ xóa cache JWKS phía client mà không thay khóa ký của issuer.
D. Ngừng ký bằng khóa đó, xoay khóa và xử lý token còn được tin cậy.
Đáp án đúng: D

Vì sao resource server phải kiểm tra claim `iss`?
A. Đảm bảo token được gửi bởi đúng trình duyệt đã đăng nhập.
B. Đảm bảo token đến từ đúng issuer được cấu hình tin cậy.
C. Xác định API đích dựa trên hostname của máy chủ phát hành.
D. Kiểm tra token chưa bị phát lại bằng cách so sánh thời điểm phát hành.
Đáp án đúng: B

Một JWT có chữ ký hợp lệ nhưng `aud` không chứa API đang gọi; API nên làm gì?
A. Từ chối vì token không được cấp cho resource server này.
B. Chấp nhận vì chữ ký hợp lệ chứng minh mọi API đều có thể dùng.
C. Chấp nhận nếu `sub` thuộc tenant đang đăng nhập trên hệ thống.
D. Đổi `aud` thành API hiện tại sau khi xác minh chữ ký thành công.
Đáp án đúng: A

Các node xác minh JWT có đồng hồ lệch nhau; cách xử lý nào hợp lý?
A. Đồng bộ thời gian và áp dụng clock skew nhỏ, có giới hạn.
B. Bỏ qua `exp` và `nbf` để tránh lỗi giữa các node khác giờ.
C. Tăng TTL cho mọi token bằng độ lệch lớn nhất đã quan sát.
D. Dùng `iat` làm nguồn thời gian duy nhất thay cho đồng hồ hệ thống.
Đáp án đúng: A

Một API nhận nhiều loại JWT từ cùng issuer; claim nào giúp phân biệt loại token?
A. Dùng `sub` vì ID token và access token luôn có chủ thể khác nhau.
B. Dùng `typ` hoặc hợp đồng token riêng và kiểm tra theo mục đích.
C. Dùng `jti` vì mỗi loại token có một dải định danh riêng.
D. Dùng `kid` vì issuer phải tạo một khóa khác cho từng loại token.
Đáp án đúng: B

Resource server nhận ID token từ OIDC client như bearer access token; vấn đề là gì?
A. ID token luôn được mã hóa nên resource server không đọc được claims.
B. ID token dành cho client; audience và mục đích không khớp API.
C. ID token không có chữ ký nên không thể xác minh nguồn phát hành.
D. ID token không có `sub` nên không thể gắn với người dùng đăng nhập.
Đáp án đúng: B

Mối quan hệ nào giữa JWT và OAuth 2.0 là chính xác?
A. JWT là giao thức cấp quyền; OAuth 2.0 là định dạng payload thay thế.
B. OAuth 2.0 yêu cầu mọi access token phải có cấu trúc JWT compact.
C. JWT tự định nghĩa authorization code, redirect và consent flow.
D. JWT là định dạng token; OAuth 2.0 là framework ủy quyền.
Đáp án đúng: D

OIDC client nhận ID token; claim `nonce` cần được kiểm tra thế nào?
A. Chấp nhận mọi nonce nếu chữ ký token và `iss` đều hợp lệ.
B. Dùng nonce làm audience để kiểm tra API đích của access token.
C. Tạo nonce sau khi nhận token rồi ghi vào session của người dùng.
D. So nonce nhận được với nonce đã gửi trong request.
Đáp án đúng: D

Trong OAuth authorization code flow, `state` và PKCE giúp bảo vệ điều gì?
A. State liên kết phản hồi; PKCE giảm nguy cơ code bị chặn và dùng lại.
B. State mã hóa access token; PKCE xác minh chữ ký của ID token.
C. State thay thế `nonce`; PKCE xác định issuer của authorization server.
D. State cấp quyền API; PKCE thay thế TLS giữa client và server.
Đáp án đúng: A

Một JWT lồng JWE bên ngoài và JWS bên trong; verifier cần làm gì?
A. Chỉ giải mã JWE vì lớp ngoài đã bảo đảm nguồn gốc payload.
B. Chỉ xác minh JWS trước khi giải mã lớp JWE bên ngoài.
C. Giải mã lớp JWE rồi xác minh chữ ký JWS bên trong.
D. Chọn một lớp để xử lý vì hai lớp cung cấp bảo đảm tương đương.
Đáp án đúng: C

Khi xác minh JWE, chính sách thuật toán nên kiểm tra điều gì?
A. Chỉ kiểm tra `alg` vì `enc` được suy ra từ độ dài ciphertext.
B. Chỉ kiểm tra `enc` vì `alg` không ảnh hưởng cách giải mã khóa.
C. Allowlist riêng `alg` quản lý khóa và `enc` mã hóa nội dung.
D. Chấp nhận cặp `alg` và `enc` do token chọn nếu giải mã thành công.
Đáp án đúng: C

Với JWE dùng chế độ mã hóa yêu cầu nonce duy nhất, điều gì phải được bảo đảm?
A. Không tái sử dụng IV với cùng khóa theo yêu cầu thuật toán.
B. Giữ IV bí mật như private key và không gửi trong compact token.
C. Dùng cùng IV cho các token cùng issuer để hỗ trợ cache kết quả.
D. Tạo IV từ `sub` để cùng người dùng luôn nhận cùng ciphertext.
Đáp án đúng: A

Một bearer JWT bị sao chép có thể dùng lại; `jti` giúp chống replay khi nào?
A. Khi verifier lưu và từ chối `jti` đã dùng trong cửa sổ phù hợp.
B. Khi chỉ kiểm tra claim `jti` có mặt và chữ ký token hợp lệ.
C. Khi `jti` được mã hóa trong payload để người dùng không đọc được.
D. Khi issuer tạo `jti` ngẫu nhiên nhưng resource server không lưu trạng thái.
Đáp án đúng: A

Hệ thống cần giảm thời gian token còn hiệu lực sau khi thu hồi quyền; lựa chọn nào phù hợp?
A. TTL dài kết hợp cache JWKS để mọi verifier tự nhận quyền mới.
B. Chỉ xóa token khỏi trình duyệt vì bearer token không thể sao chép.
C. TTL ngắn kết hợp denylist khi cần thu hồi sớm.
D. Tăng thời hạn access token và chỉ thu hồi refresh token phía client.
Đáp án đúng: C

Refresh token rotation phát hiện token cũ bị dùng lại; phản ứng nào phù hợp?
A. Thu hồi token family và yêu cầu xác thực lại.
B. Cấp refresh token mới cho request cũ rồi giữ nguyên token family.
C. Bỏ qua reuse nếu access token hiện tại vẫn chưa hết hạn.
D. Chỉ ghi log sự kiện và tiếp tục chấp nhận refresh token đã dùng.
Đáp án đúng: A

DPoP-bound access token cần được xác minh với proof như thế nào?
A. Kiểm tra proof key, `htm`, `htu`, `iat`, `jti`, `ath` và key binding.
B. Chỉ kiểm tra chữ ký proof vì nó tự ràng buộc mọi request HTTP.
C. So sánh `jti` proof với `sub` rồi bỏ qua URL và method của request.
D. Kiểm tra access token bằng TLS server certificate của resource server.
Đáp án đúng: A

Với mTLS-bound access token, resource server cần kiểm tra điều gì?
A. Chỉ xác minh certificate của resource server vì TLS đã mã hóa kênh.
B. Đối chiếu certificate thumbprint của client với ràng buộc trong token.
C. Chấp nhận mọi certificate do CA công khai cấp mà không đối chiếu token.
D. Dùng `kid` của JWT làm thumbprint certificate để nhận diện client.
Đáp án đúng: B

Ứng dụng trình duyệt lưu bearer token và dùng cookie cho request; biện pháp nào phù hợp?
A. Tránh URL/log; giảm XSS và bảo vệ CSRF khi dùng cookie.
B. Chỉ dùng HttpOnly vì thuộc tính này cũng chặn mọi request CSRF.
C. Chỉ bật CORS vì CORS ngăn script độc hại đọc token trong cùng origin.
D. Lưu access token trong localStorage và dựa vào TTL ngắn để hạn chế lộ.
Đáp án đúng: A

Khi kiểm thử JWT verifier đa tenant, tập negative test nào có giá trị nhất?
A. Thử sai chữ ký, claims, tenant, hạn dùng và key rotation.
B. Chỉ kiểm tra token hợp lệ của tenant chính và thời gian phản hồi API.
C. Chỉ kiểm tra payload thiếu trường tùy chọn và JSON có khoảng trắng.
D. Chỉ thử token hết hạn vì các claim khác đã được issuer bảo đảm.
Đáp án đúng: A
