Một API nhận JWT từ ứng dụng di động và giải mã Base64 phần payload để đọc claims; nhóm phát triển cho rằng dữ liệu đã được mã hóa nên đưa số định danh cá nhân vào token mà không dùng JWE.
Đội sản phẩm gọi JWT là cơ chế đăng nhập hoàn chỉnh và bỏ qua việc xác định ai phát hành token, client nào yêu cầu token và API nào được phép chấp nhận token.
Một dịch vụ xác minh chữ ký JWT nhưng chấp nhận header alg=none; kẻ gửi có thể thay đổi claims mà không cần khóa ký hợp lệ.
Thư viện xác minh token hỗ trợ cả RS256 và HS256; cấu hình lấy public key RSA làm HMAC secret khi header yêu cầu HS256 nên token giả mạo được chấp nhận.
Nhóm tích hợp chọn HMAC secret ngắn và dễ nhớ để nhiều dịch vụ cùng ký JWT; một bản token mẫu bị lộ khiến kẻ tấn công có thể thử đoán khóa ngoại tuyến.
API lấy thuật toán xác minh trực tiếp từ trường alg trong header mà không áp dụng allowlist theo hợp đồng token; một thay đổi header làm đường xác minh chuyển sang thuật toán không được dự kiến.
Một hệ thống dùng khóa RSA cho chữ ký bất đối xứng nhưng thư viện cho phép diễn giải cùng vật liệu khóa theo nhiều loại thuật toán; nhóm chưa ràng buộc thuật toán với loại khóa.
JWT header chứa kid do client kiểm soát; dịch vụ nối giá trị này vào đường dẫn tệp khóa và một giá trị đặc biệt làm bộ nạp khóa đọc tệp ngoài thư mục dự kiến.
Một dịch vụ tra cứu khóa theo kid bằng cách ghép trực tiếp chuỗi vào truy vấn cơ sở dữ liệu; header được tạo thủ công có thể làm thay đổi điều kiện tìm khóa.
JWT header có trường jku trỏ đến URL do người gửi cung cấp; máy chủ xác minh tự tải JWKS từ URL đó và có thể bị hướng đến địa chỉ mạng nội bộ.
Header x5u trong token được dùng để tải certificate chain từ máy chủ tùy ý; việc tải tài nguyên không giới hạn khiến endpoint xác minh có nguy cơ SSRF và cạn tài nguyên.
Nhà phát hành xoay signing key và công bố hai khóa trong JWKS; API chỉ chọn khóa đầu tiên thay vì tìm đúng kid nên một số token hợp lệ bị từ chối.
Nhà phát hành đã bỏ khóa cũ khỏi JWKS nhưng các verifier cache JWKS quá lâu; token ký bằng khóa cũ tiếp tục được chấp nhận sau thời điểm tổ chức muốn ngừng tin cậy.
Trong đợt xoay khóa, issuer chuyển sang khóa mới trước khi mọi verifier nhận JWKS cập nhật; một phần request hợp lệ bị lỗi xác minh do triển khai không có giai đoạn overlap.
Private signing key bị nghi lộ; nhóm chỉ xóa khóa khỏi JWKS công khai nhưng không thu hồi hoặc thay khóa tại nơi ký, khiến token mới vẫn được ký bằng khóa bị xâm phạm.
Một API xác minh chữ ký và thời hạn JWT nhưng không kiểm tra iss; token từ một issuer khác có khóa hợp lệ được chấp nhận trong cùng hệ thống.
Token có chữ ký hợp lệ và issuer đúng nhưng aud trỏ đến API khác; dịch vụ đích vẫn chấp nhận token vì chỉ kiểm tra chữ ký và exp.
Một access token được cấp cho nhiều audience để thuận tiện tích hợp; dịch vụ nội bộ nhận token dành cho hệ thống bên ngoài và cho phép sử dụng ngoài mục đích dự kiến.
OIDC client nhận ID token có nhiều audience nhưng không kiểm tra azp có khớp client_id của mình hay không; token có thể được chấp nhận sai client.
Verifier không kiểm tra exp vì cho rằng token đã được API gateway xác minh; một token cũ bị sao chép tiếp tục được sử dụng sau khi phiên đáng lẽ hết hạn.
Verifier kiểm tra exp nhưng không áp dụng chính sách cho nbf và iat; token có nbf trong tương lai hoặc iat quá cũ vẫn được chấp nhận ngoài cửa sổ cho phép.
Các node xác minh JWT lệch đồng hồ nhiều phút; token mới phát hành bị từ chối ở một số node trong khi token hết hạn vẫn được chấp nhận ở node khác.
Parser JSON của hai dịch vụ xử lý header có tên trường trùng lặp theo quy tắc khác nhau; cùng một JWT được diễn giải với thuật toán hoặc key ID khác nhau.
Một claim roles được gửi dưới dạng chuỗi ở token cũ và mảng ở token mới; verifier ép kiểu không nhất quán khiến một số quyền bị cấp hoặc bị mất ngoài dự kiến.
API chỉ kiểm tra chữ ký mà không kiểm tra typ; JWT dùng cho mục đích khác được chấp nhận như access token vì cả hai cùng dùng chung khóa ký.
Một backend chấp nhận OIDC ID token làm bearer token truy cập API; token được tạo để xác nhận đăng nhập của client nhưng không có audience phù hợp cho resource server.
Client kiểm tra chữ ký ID token nhưng không so sánh nonce với giá trị đã gửi trong authentication request; token cũ có thể bị phát lại trong một phiên đăng nhập mới.
Ứng dụng dùng JWT trong OAuth authorization flow nhưng không kiểm tra state hoặc PKCE; việc có chữ ký token không ngăn được CSRF hay authorization code interception.
Access token chứa role quản trị được giữ hiệu lực lâu sau khi người dùng bị hạ quyền; API dựa hoàn toàn vào claim cũ mà không có cơ chế cập nhật hoặc giới hạn thời gian.
Một token chứa scope write:all được cấp cho ứng dụng chỉ cần đọc hồ sơ; API không đối chiếu scope với từng thao tác nên quyền vượt quá nhu cầu.
API xác minh chữ ký JWT và tenant claim nhưng không kiểm tra quyền trên object; người dùng cùng tenant có thể thay ID trong URL để truy cập bản ghi không thuộc phạm vi của họ.
Hai tổ chức dùng chung hệ thống xác minh với nhiều issuer; cấu hình ánh xạ issuer sang tenant sai khiến token hợp lệ của tenant này được xử lý trong ngữ cảnh tenant khác.
JWT access token được lưu trong localStorage của trình duyệt; một lỗ hổng XSS cho phép script độc hại đọc và gửi token đến máy chủ bên ngoài.
Ứng dụng truyền JWT qua query string để tiện liên kết; token xuất hiện trong browser history, access log, analytics và Referer khi trang tải tài nguyên bên thứ ba.
JWT được đặt trong cookie tự động gửi kèm request; endpoint thay đổi trạng thái không có CSRF protection và cookie SameSite được cấu hình quá rộng.
Ứng dụng đặt access token vào cookie HttpOnly để giảm nguy cơ đọc qua JavaScript nhưng nhóm cho rằng HttpOnly tự động ngăn CSRF nên không kiểm tra nguồn request.
Bearer JWT bị sao chép từ log và dùng lại từ thiết bị khác; hệ thống không ràng buộc token với client hoặc có cơ chế phát hiện replay.
Ứng dụng triển khai DPoP nhưng không kiểm tra jti đã dùng, htm và htu của proof; cùng một proof có thể được phát lại cho request khác.
Resource server nhận certificate-bound access token qua reverse proxy; proxy không xác thực client certificate đúng cách và header định danh certificate có thể bị client giả mạo.
JWT chứa email, địa chỉ và thông tin định danh; nhóm ký JWS rồi cho rằng chữ ký bảo vệ tính bí mật nên không giới hạn người có thể đọc payload.
Một luồng cần bảo mật nội dung token giữa các bên trung gian nhưng chỉ dùng JWS; mọi thành phần nhìn thấy token đều đọc được claims dù không thể sửa chữ ký.
Verifier JWE chỉ kiểm tra khả năng giải mã mà không kiểm tra chính sách alg và enc được phép; token dùng thuật toán yếu hoặc cấu hình mã hóa ngoài chuẩn nội bộ vẫn được xử lý.
Một hệ thống tạo nhiều JWE bằng cùng key và IV trong một chế độ mã hóa yêu cầu nonce duy nhất; nhóm không có cơ chế bảo đảm IV không lặp.
JWT lồng nhau dùng JWE bên ngoài và JWS bên trong; verifier giải mã payload nhưng bỏ qua bước xác minh chữ ký lớp trong trước khi tin claims.
Header JWT có trường crit chỉ đến extension mà verifier không hỗ trợ; thư viện bỏ qua trường này và tiếp tục xử lý token như thể đã hiểu toàn bộ ngữ nghĩa.
Một hệ thống dùng detached payload hoặc b64=false trong JWS nhưng verifier không kiểm tra quy tắc critical header; các thành phần ký và xác minh tạo ra cách diễn giải khác nhau.
Ứng dụng giải mã rồi serialize lại JSON header và payload trước khi kiểm tra chữ ký; thứ tự trường hoặc cách biểu diễn byte thay đổi làm đầu vào ký không còn đúng với token ban đầu.
Parser chấp nhận nhiều biến thể Base64URL, padding và ký tự không chuẩn; các thành phần gateway và backend chuẩn hóa khác nhau nên cùng một token có thể qua kiểm tra khác nhau.
API nhận JWT có header và payload kích thước rất lớn; quá trình parse, tra cứu khóa và xác minh chữ ký có thể bị lạm dụng để tiêu tốn CPU và bộ nhớ.
JWKS endpoint vô tình công bố cả private key parameter do quy trình export nhầm key set; các verifier bên ngoài có thể lấy vật liệu dùng để ký token.
Nhiều dịch vụ dùng chung một HMAC secret để xác minh token; bất kỳ dịch vụ nào bị xâm nhập cũng có thể tự tạo JWT được các dịch vụ còn lại tin cậy.
Signing key được lưu trong file cấu hình của container image; image được chia sẻ rộng và lịch sử registry vẫn chứa khóa sau khi bản mới đã xóa file.
Nhóm ký JWT bằng ECDSA nhưng thư viện tự sinh nonce không an toàn; các chữ ký có nonce yếu hoặc lặp có thể làm lộ private signing key.
JWT không có cơ chế thu hồi tức thời; khi người dùng bị khóa tài khoản, token tự chứa vẫn được chấp nhận cho đến exp vì resource server không kiểm tra trạng thái bổ sung.
Người dùng đăng xuất trên một thiết bị nhưng JWT đã phát hành vẫn dùng được trên thiết bị khác; hệ thống chỉ xóa token khỏi client mà không xử lý phiên phía server.
Refresh token dạng JWT được dùng lại sau khi rotation đã cấp token mới; hệ thống không phát hiện reuse nên không thu hồi token family bị sao chép.
Hai request đồng thời dùng cùng refresh token; rotation xử lý request đầu thành công nhưng request thứ hai bị xem như replay và làm thu hồi nhầm phiên hợp lệ.
Mật khẩu người dùng bị reset sau sự cố; access token JWT hiện tại không chứa session version hoặc cơ chế kiểm tra trạng thái nên tiếp tục hoạt động đến khi hết hạn.
JWT chứa dữ liệu cá nhân và được lưu trong hệ thống log để điều tra; quyền truy cập log rộng hơn quyền xem hồ sơ gốc và thời hạn lưu giữ không phù hợp.
Một dịch vụ nhận JWT từ nhiều nguồn nhưng không có hợp đồng thống nhất về claim bắt buộc, kiểu dữ liệu, audience và thời hạn; mỗi verifier tự diễn giải theo cách riêng.
Ứng dụng cần trao đổi quyền giữa hai dịch vụ bằng token exchange; token mới giữ nguyên audience và scope của token gốc thay vì giới hạn theo dịch vụ đích.
API dùng JWT để xác thực request nhưng dựa vào CORS như biện pháp bảo vệ token; một client ngoài browser có thể gọi endpoint trực tiếp bằng token đã lấy được.
