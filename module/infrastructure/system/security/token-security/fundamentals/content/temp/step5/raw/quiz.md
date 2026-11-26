Một API nhận bearer token trong header Authorization. Giả định tin cậy cốt lõi nào cần được hiểu đúng?
A. Token tự chứng minh người gửi là người dùng đã đăng nhập ban đầu.
B. Token chỉ có giá trị khi request xuất phát từ mạng nội bộ của tổ chức.
C. Ai nắm bearer token có thể dùng trong phạm vi quyền được cấp.
D. Token được gửi qua HTTPS thì không cần kiểm tra quyền ở API.
Đáp án đúng: C

Một hệ thống phát hành token sau khi xác thực người dùng. Mô hình vòng đời nào mô tả đúng các bước quản trị token?
A. Tạo token một lần, dùng vô thời hạn rồi xóa khi người dùng đăng xuất.
B. Phát hành, lưu giữ, sử dụng, gia hạn hoặc thay thế, thu hồi và hết hạn.
C. Phát hành token, lưu cùng mật khẩu và chỉ thay khi người dùng đổi mật khẩu.
D. Mã hóa token, gửi cho mọi dịch vụ rồi coi việc xóa cookie là thu hồi.
Đáp án đúng: B

Một đội phát triển cân nhắc JWT và opaque token cho access token. Nhận định nào chính xác?
A. JWT luôn được mã hóa nên chỉ resource server mới đọc được payload.
B. Opaque token chứa claim có thể xác minh độc lập mà không cần issuer.
C. JWT tự chứa claim; opaque token cần tra cứu trạng thái phía server.
D. Hai dạng token có cùng cách xác minh và khác nhau chủ yếu ở độ dài.
Đáp án đúng: C

Một ứng dụng cần gọi API đơn hàng sau khi người dùng cấp quyền. Token nào nên được gửi tới resource server?
A. Access token được cấp cho API với audience và scope phù hợp.
B. Refresh token được cấp cho client để duy trì phiên đăng nhập.
C. ID token dùng để chứng minh người dùng đã xác thực với client.
D. Authorization code nhận qua redirect để API tự đổi lấy quyền.
Đáp án đúng: A

Một client OIDC nhận ID token sau khi người dùng đăng nhập. Mục đích chính của token này là gì?
A. Cho resource server quyền đọc hoặc sửa tài nguyên theo scope.
B. Cho client thay thế refresh token khi access token hết hạn.
C. Cho client biết thông tin xác thực về người dùng và phiên đăng nhập.
D. Cho mọi API chấp nhận token như bearer credential không cần kiểm tra.
Đáp án đúng: C

Một resource server nhận JWT có claim iss. Cách kiểm tra nào phù hợp?
A. So khớp iss với issuer tin cậy đã cấu hình.
B. Tin issuer bất kỳ nếu JWT có chữ ký hợp lệ về mặt toán học.
C. Dùng iss làm audience để quyết định API nào được gọi token.
D. Bỏ qua iss khi subject là người dùng đã tồn tại trong database.
Đáp án đúng: A

Một hệ thống dùng claim sub để nhận diện chủ thể của token. Nhận định nào cần được lưu ý khi lưu liên kết người dùng?
A. sub luôn là email và có thể dùng làm định danh toàn cục giữa issuer.
B. sub giống nhau giữa mọi client nên có thể bỏ qua claim iss.
C. sub được hiểu trong phạm vi issuer, không phải định danh toàn cục.
D. sub chỉ có ý nghĩa khi token là opaque và không áp dụng cho JWT.
Đáp án đúng: C

Một API nhận token có aud chứa định danh của dịch vụ thanh toán, trong khi request đang tới API hồ sơ. API hồ sơ nên làm gì?
A. Chấp nhận nếu token có scope read và chữ ký đã được xác minh.
B. Chấp nhận nếu client_id là ứng dụng nội bộ cùng tổ chức.
C. Chuyển tiếp token tới API thanh toán để API đó xác nhận thay.
D. Từ chối nếu aud không bao gồm API đang xử lý.
Đáp án đúng: D

Một JWT có exp và nbf. Cách diễn giải nào đúng?
A. exp hết hạn; nbf là thời điểm bắt đầu có hiệu lực.
B. exp là thời điểm phát hành; nbf là thời điểm token phải được thu hồi.
C. exp giới hạn phiên người dùng; nbf giới hạn thời gian refresh token.
D. exp và nbf đều là thời điểm tùy chọn để hiển thị trong giao diện.
Đáp án đúng: A

Một hệ thống kiểm tra claim iat của JWT. Claim này biểu thị điều gì?
A. Thời điểm token được thu hồi tại authorization server.
B. Thời điểm token bắt đầu có hiệu lực giống claim nbf.
C. Thời điểm người dùng xác nhận consent cho scope được cấp.
D. iat cho biết thời điểm token được phát hành.
Đáp án đúng: D

Một API ghi nhận jti trong JWT và muốn chống việc bearer token bị phát lại. Kết luận nào đúng?
A. Sự hiện diện của jti tự động khiến JWT chỉ được dùng đúng một lần.
B. jti định danh token; replay cần thêm trạng thái kiểm soát.
C. jti thay thế exp và làm token hết hạn ngay sau request đầu tiên.
D. jti là chữ ký của issuer nên API có thể bỏ qua kiểm tra signature.
Đáp án đúng: B

Một resource server xác minh JWT ký bằng khóa bất đối xứng. Bộ kiểm tra nào phù hợp?
A. Xác minh chữ ký, thuật toán cho phép, iss, aud và thời hạn.
B. Giải mã Base64, đọc claim rồi tin nội dung nếu JSON đúng định dạng.
C. Chỉ kiểm tra chữ ký vì claim issuer và audience do client tự chọn.
D. Chấp nhận thuật toán ghi trong header mà không giới hạn danh sách cho phép.
Đáp án đúng: A

Một nhóm cho rằng payload JWT không cần bảo vệ vì token đã được ký. Nhận định nào chính xác?
A. Chữ ký JWT mã hóa payload nên người giữ token không thể đọc claim.
B. JWS bảo vệ tính toàn vẹn; payload thường đọc được và không được mã hóa.
C. Base64URL che giấu nội dung tương đương mã hóa bằng khóa bí mật.
D. Chỉ refresh token mới cần mã hóa; access token luôn chứa dữ liệu bí mật an toàn.
Đáp án đúng: B

Một JWT có kid trỏ tới khóa không nằm trong JWKS đã cache. Resource server nên xử lý ra sao?
A. Tải khóa từ URL tùy ý do token header cung cấp và tin kết quả.
B. Dùng khóa bất kỳ trong cache để tránh làm mới JWKS khi tải cao.
C. Bỏ qua chữ ký và chấp nhận token nếu kid có định dạng hợp lệ.
D. Làm mới JWKS từ issuer tin cậy rồi chọn khóa theo kid.
Đáp án đúng: D

Một issuer chuẩn bị xoay khóa ký JWT. Trình tự triển khai nào giảm lỗi xác minh?
A. Xóa khóa cũ khỏi JWKS rồi mới phát hành token bằng khóa mới.
B. Công bố khóa mới trước khi dùng và giữ khóa cũ tới khi token hết hạn.
C. Ký token mới bằng khóa chưa công bố và công bố JWKS sau khi phát hành.
D. Thay kid trong header token cũ mà không tạo chữ ký mới.
Đáp án đúng: B

Một authorization server phát hành opaque access token. API muốn biết token còn hoạt động và quyền hiện tại. Cơ chế nào phù hợp?
A. Giải mã opaque token bằng Base64 để lấy claim và thời hạn.
B. Dùng introspection để kiểm tra trạng thái opaque token.
C. Dùng UserInfo endpoint để thay mọi kiểm tra trạng thái token.
D. Tải JWKS rồi xác minh chữ ký dù token không phải JWT.
Đáp án đúng: B

Một access token có scope invoices.read hợp lệ nhưng người dùng yêu cầu đọc hóa đơn của tenant khác. API cần làm gì?
A. Chấp nhận vì scope read cho phép đọc mọi hóa đơn trong hệ thống.
B. Tin tenant ID do client gửi vì token đã có chữ ký hợp lệ.
C. Kiểm tra quyền đối tượng và tenant ngoài scope.
D. Chỉ kiểm tra sub và bỏ qua quan hệ sở hữu của hóa đơn.
Đáp án đúng: C

Một client web dùng OAuth authorization code flow để xin access token. Biện pháp nào bảo vệ code khỏi bị chặn và đổi bởi client khác?
A. Đặt refresh token vào redirect URI để chỉ client gốc nhận được code.
B. Dùng PKCE để ràng buộc code với verifier mà client ban đầu giữ.
C. Dùng ID token làm client secret khi gọi token endpoint.
D. Gửi access token trước rồi dùng state để đổi ngược thành authorization code.
Đáp án đúng: B

Một relying party OIDC gửi nonce trong authentication request. Client nên làm gì khi nhận ID token?
A. Dùng nonce làm audience và so với định danh resource server.
B. Chuyển nonce tới UserInfo để server tự xác minh access token.
C. Bỏ qua nonce khi chữ ký ID token hợp lệ và phiên vẫn còn hoạt động.
D. So khớp nonce với giá trị đã lưu cho yêu cầu đăng nhập.
Đáp án đúng: D

Một client nhận refresh token cùng access token. Refresh token nên được gửi tới đâu?
A. Resource server trong mỗi API request để xác thực quyền truy cập.
B. UserInfo endpoint để lấy lại hồ sơ người dùng sau mỗi phiên.
C. Redirect URI để client nhận access token mới qua trình duyệt.
D. Gửi tới token endpoint của authorization server để xin token mới.
Đáp án đúng: D

Một authorization server áp dụng refresh token rotation. Điều gì xảy ra khi client dùng refresh token mới?
A. Server cấp token thay thế và vô hiệu hóa refresh token đã dùng.
B. Server giữ token cũ hoạt động để mọi thiết bị có thể dùng song song.
C. Server chuyển refresh token thành ID token và giữ access token cũ.
D. Server chỉ đổi thời hạn của token cũ mà không phát hành token mới.
Đáp án đúng: A

Một refresh token cũ bị sử dụng lại sau khi đã được rotate. Phản ứng nào giúp hạn chế replay?
A. Phát hiện reuse và thu hồi token family hoặc phiên liên quan.
B. Cấp token mới cho request thứ hai vì cùng client ID chứng minh hợp lệ.
C. Chấp nhận token cũ nếu địa chỉ IP không thay đổi so với lần trước.
D. Chỉ ghi log sự kiện vì rotation đã bảo đảm token cũ không có quyền.
Đáp án đúng: A

Một resource server chấp nhận JWT tự chứa và không gọi issuer mỗi request. Hạn chế nào cần tính đến khi thu hồi token?
A. JWT tự kiểm tra trạng thái thu hồi trực tuyến mỗi lần chữ ký được xác minh.
B. Thu hồi refresh token làm mọi access token JWT lập tức mất hiệu lực ở mọi API.
C. JWT có thể còn được chấp nhận tới exp nếu chưa đồng bộ trạng thái thu hồi.
D. Xóa cookie client khiến mọi resource server tự nhận biết token đã bị thu hồi.
Đáp án đúng: C

Một ứng dụng cần ràng buộc access token với khóa do client nắm giữ để giảm giá trị của token bị đánh cắp. Cơ chế nào phù hợp?
A. DPoP yêu cầu proof có chữ ký gắn với khóa client cho từng request.
B. Nonce trong ID token mã hóa access token bằng khóa của authorization server.
C. jti làm access token chỉ hợp lệ trên địa chỉ IP đã cấp token.
D. Refresh token rotation ràng buộc mọi access token với chứng thư thiết bị.
Đáp án đúng: A

Một API dùng certificate-bound access token qua mutual TLS. Điều gì được xác minh khi nhận request?
A. Chứng thư server phải có cùng subject với claim sub của người dùng.
B. Chứng thư client thay thế hoàn toàn việc kiểm tra audience và scope.
C. Chỉ cần kết nối TLS thành công; API không cần kiểm tra binding của token.
D. Chứng thư TLS client phải khớp binding được ghi trong token.
Đáp án đúng: D

Một SPA lưu access token lâu dài trong localStorage. Rủi ro nổi bật nào cần xử lý?
A. CSRF tự động đọc localStorage vì trình duyệt gửi nó như cookie.
B. HTTPS khiến token trong localStorage không thể bị truy cập bởi script.
C. SameSite cookie tự động bảo vệ token localStorage khỏi mọi XSS.
D. JavaScript chạy do XSS có thể đọc và lấy token khỏi storage.
Đáp án đúng: D

Một web app dùng cookie phiên HttpOnly để trình duyệt gửi credential tới backend. Biện pháp nào vẫn cần cân nhắc?
A. Áp dụng SameSite phù hợp và token chống CSRF khi cần.
B. HttpOnly tự chặn request giả mạo vì trình duyệt không gửi cookie tự động.
C. Chỉ cần Secure flag vì nó xác minh nguồn gốc của mọi form submission.
D. Đổi cookie sang localStorage để trình duyệt không tự đính kèm credential.
Đáp án đúng: A

Một client đưa access token vào query string để gọi API. Rủi ro rò rỉ nào có thể xảy ra?
A. Token tự bị xóa khỏi URL trước khi proxy và trình duyệt ghi log.
B. Token có thể xuất hiện trong lịch sử, log, analytics hoặc Referer.
C. Query string được TLS mã hóa nên không thể lộ ở các thành phần đầu cuối.
D. Token trong URL chỉ có thể bị lộ nếu chữ ký JWT không hợp lệ.
Đáp án đúng: B

Một hệ thống ghi toàn bộ Authorization header vào log để tiện điều tra. Cách xử lý phù hợp là gì?
A. Giữ nguyên token nhưng mã hóa file log bằng khóa lưu cạnh log.
B. Redact token và ghi metadata tối thiểu để tương quan sự kiện.
C. Chỉ che ba ký tự cuối để vẫn có thể khôi phục token khi cần.
D. Chuyển token sang query string để log header không chứa credential.
Đáp án đúng: B

Một ứng dụng dùng cookie HttpOnly để giữ phiên nhưng bị XSS trong trang. Nhận định nào chính xác?
A. HttpOnly ngăn JavaScript gửi request có cookie nên XSS không còn tác động.
B. XSS chỉ có thể đọc localStorage và không thể tương tác với phiên cookie.
C. Secure flag bảo đảm script cùng origin không thể gọi endpoint nhạy cảm.
D. XSS vẫn có thể thực hiện hành động thay người dùng qua phiên cookie.
Đáp án đúng: D

Một hệ thống đa tenant nhận JWT có issuer và audience hợp lệ nhưng claim tenant_id do issuer cấp. Kiểm soát nào cần thêm?
A. Chấp nhận tenant_id nếu client gửi cùng giá trị trong request body.
B. Dùng sub làm tenant ID vì mọi subject thuộc duy nhất một tenant.
C. Ràng buộc tenant với tài nguyên và membership phía server.
D. Bỏ kiểm tra tenant khi token được ký bằng khóa của issuer tin cậy.
Đáp án đúng: C

Một JWT được ký đúng nhưng được phát hành cho client khác. Client hiện tại nên xử lý thế nào?
A. Chấp nhận nếu sub là người dùng đã đăng nhập trên client hiện tại.
B. Xác minh aud chứa client ID; kiểm tra azp khi áp dụng.
C. Chấp nhận nếu exp còn hiệu lực và thuật toán ký được cho phép.
D. Chỉ kiểm tra issuer vì audience không ảnh hưởng việc xác thực client.
Đáp án đúng: B

Một bearer access token bị lộ trong log và có thể đang bị sử dụng. Ứng phó nào phù hợp nhất?
A. Chỉ xóa dòng log vì token sẽ tự vô hiệu ngay khi bị sao chép.
B. Đổi tên client để token cũ không còn khớp với ứng dụng.
C. Thu hồi phiên, chặn token bằng denylist hoặc introspection và điều tra.
D. Gia hạn token hiện tại để giảm lỗi khi người dùng đang hoạt động.
Đáp án đúng: C

Một private signing key của issuer bị xâm phạm. Biện pháp nào xử lý đúng mức độ sự cố?
A. Chỉ thu hồi refresh token của người dùng, giữ nguyên khóa ký bị lộ.
B. Đổi tên kid trong JWKS nhưng tiếp tục dùng cùng private key.
C. Ngừng ký, loại bỏ trust theo kid và đánh giá token đã phát hành.
D. Chỉ giảm exp của token mới mà không xử lý khóa hoặc verifier.
Đáp án đúng: C

Một SOC muốn phát hiện token bị sử dụng bất thường. Tập tín hiệu nào hữu ích?
A. Theo dõi reuse, vị trí, client, scope và tần suất request.
B. Chỉ đếm tổng token được phát hành mỗi ngày và bỏ qua request API.
C. Theo dõi độ dài JWT và cảnh báo khi payload có nhiều claim.
D. Chỉ cảnh báo token gần hết hạn vì replay thường xảy ra sau exp.
Đáp án đúng: A

Một API nhận token có exp hợp lệ nhưng nbf ở tương lai vài phút do lệch đồng hồ. Cách xử lý nào hợp lý?
A. Bỏ qua nbf nếu exp còn hạn và chữ ký đã xác minh thành công.
B. Kéo dài exp để token có thể sử dụng trước thời điểm nbf.
C. Dùng iat thay nbf vì hai claim luôn có cùng ý nghĩa.
D. Tôn trọng nbf, áp dụng clock skew nhỏ và đồng bộ đồng hồ.
Đáp án đúng: D
