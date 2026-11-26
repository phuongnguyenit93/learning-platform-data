Access token được dùng chủ yếu để làm gì trong một hệ thống API?
A. Lấy access token mới sau mỗi lần token hiện tại hết hạn
B. Kiểm tra quyền gọi API theo phạm vi và thời hạn token đã cấp
C. Khôi phục phiên đăng nhập sau khi người dùng đã đăng xuất
D. Thay khóa xác minh của API khi mỗi yêu cầu được gửi
Đáp án đúng: B

Refresh token nên được gửi đến thành phần nào trong luồng cấp lại token?
A. Ứng dụng khác của người dùng nhưng sai audience
B. Máy chủ ủy quyền để phát hành access token mới
C. API tài nguyên có endpoint đọc dữ liệu của người dùng
D. Proxy trung gian có nhiệm vụ chuyển tiếp mọi yêu cầu API
Đáp án đúng: B

Trong OpenID Connect, ID token thích hợp nhất cho mục đích nào?
A. Đổi lấy khóa ký mới khi access token bị hết hạn
B. Thay thế token thu hồi trên mọi thiết bị đã đăng nhập
C. Cung cấp thông tin xác thực cho ứng dụng khách
D. Cấp quyền trực tiếp vào các API tài nguyên độc lập
Đáp án đúng: C

Một JWT được ký nhưng không mã hóa cung cấp bảo đảm nào?
A. Cho phép thu hồi tức thời mà không lưu trạng thái phiên
B. Che giấu các claim khi token đi qua hệ thống trung gian
C. Phát hiện sửa đổi nội dung nhờ xác minh chữ ký
D. Token không thể dùng lại trong yêu cầu khác
Đáp án đúng: C

API thường xác định quyền của opaque token bằng cách nào?
A. Giải mã claim từ payload JWT đã đính kèm trong token
B. Tra cứu token tại kho hoặc endpoint introspection
C. Phân tích scope từ tiền tố và độ dài của chuỗi token
D. Đối chiếu quyền từ tham số do trình duyệt tự khai báo
Đáp án đúng: B

Nguồn nào phù hợp nhất để tạo token có độ khó dự đoán cao?
A. Bộ đếm tăng dần kết hợp với định danh của tài khoản
B. Nguồn ngẫu nhiên mật mã của hệ điều hành
C. Dấu thời gian chính xác cao kết hợp với tên ứng dụng
D. Giá trị hash của địa chỉ mạng và thời gian đăng nhập
Đáp án đúng: B

Thời hạn của access token nên được quyết định chủ yếu theo yếu tố nào?
A. Kích thước payload và số lượng claim được truyền đi
B. Độ dài khóa ký và tốc độ xử lý chữ ký của máy chủ
C. Số lượng API nằm phía sau bộ cân bằng tải hiện tại
D. Rủi ro bị lộ và khả năng làm mới token an toàn
Đáp án đúng: D

Khi cấp access token, scope nên được thiết kế thế nào?
A. Giới hạn ở quyền cần thiết cho hành động được duyệt
B. Dùng scope chung cho mọi ứng dụng khách
C. Xác định quyền truy cập dựa riêng vào loại thiết bị gọi
D. Chứa mọi quyền mà tài khoản từng được gán trong hệ thống
Đáp án đúng: A

Kiểm tra claim audience của token nhằm phòng tránh điều gì?
A. Token được làm mới quá sớm so với thời gian hết hạn
B. Ngăn dùng token cấp cho dịch vụ khác tại API này
C. Token đi qua mạng riêng mà thiếu chứng thư của máy chủ
D. Token bị rút ngắn do giới hạn kích thước của header
Đáp án đúng: B

Một API nhận JWT từ nhiều nhà phát hành nên xác minh issuer thế nào?
A. Đối chiếu issuer với danh sách tin cậy đã cấu hình
B. Chấp nhận mọi issuer dùng cùng thuật toán ký với API
C. Dùng issuer đầu tiên tìm thấy trong mọi request đầu vào
D. Tin issuer bên trong payload của mọi JWT
Đáp án đúng: A

Sai lệch đồng hồ giữa các máy ảnh hưởng đến kiểm tra token ra sao?
A. Cần bỏ qua exp nếu độ trễ mạng vượt mức thông thường
B. Dùng dung sai thời gian nhỏ cho exp và nbf
C. Cần tăng iat của mọi token bằng thời gian xử lý ở API
D. Chỉ kiểm tra nbf khi token không được ký
Đáp án đúng: B

Tại sao JWT có chữ ký hợp lệ vẫn chưa đủ để cho phép một thao tác?
A. Chữ ký không thể xác minh danh tính của máy chủ phát hành
B. Chữ ký chỉ hợp lệ nếu token được lưu trong cookie bảo mật
C. Chữ ký không tương thích với claim scope
D. Kiểm tra quyền trên tài nguyên và trạng thái hiện tại
Đáp án đúng: D

Đâu là biện pháp phù hợp để ngăn lỗi nhầm lẫn thuật toán JWT?
A. Chuyển sang thuật toán yếu hơn nếu khóa hiện tại không khớp
B. Thử nhiều thuật toán đến khi xác minh được
C. Chỉ dùng thuật toán được cho phép trong cấu hình
D. Tin thuật toán do header token yêu cầu nếu có chữ ký
Đáp án đúng: C

Khi xác minh JWT qua bộ khóa công khai, nguồn JWKS nên được chọn thế nào?
A. Lấy bộ khóa mới từ một nguồn bất kỳ khi gặp kid lạ
B. Tin khóa công khai được nhúng trực tiếp trong request
C. Dùng endpoint khóa đã cấu hình cho issuer được tin cậy
D. Đọc URL khóa tùy ý từ header do token gửi đến
Đáp án đúng: C

Khi xoay vòng khóa ký JWT, cách chuyển tiếp nào phù hợp nhất?
A. Phát hành bằng khóa mới, giữ khóa cũ để xác minh
B. Bỏ xác minh chữ ký trong khoảng chuyển đổi khóa ký
C. Xóa khóa cũ ngay khi bắt đầu phát hành bằng khóa mới
D. Phát hành token với nhiều thuật toán ký
Đáp án đúng: A

Vì sao nên hạn chế dữ liệu cá nhân nhạy cảm trong JWT đã ký?
A. Token có dữ liệu cá nhân không thể lưu trong header HTTP
B. Chữ ký JWT thường không thể áp dụng cho kiểu dữ liệu cá nhân
C. Nội dung token có thể bị đọc dù chữ ký vẫn hoàn toàn hợp lệ
D. Mọi claim cá nhân đều làm token không thể kiểm tra thời hạn
Đáp án đúng: C

Trong hệ thống đa tenant, điều gì cần được kiểm tra ở mỗi yêu cầu?
A. Tenant chỉ cần trùng với tiền tố trong tên miền của trình duyệt
B. Ràng buộc tenant của token với tài nguyên truy cập
C. Tenant có thể được chọn tự do từ query string của request
D. Tenant theo lần tham gia đầu của tài khoản
Đáp án đúng: B

Lợi ích chính của ký token bằng khóa bất đối xứng trong hệ thống nhiều API là gì?
A. Khóa công khai làm các claim trở thành bí mật trước bên thứ ba
B. Bất kỳ API nào có khóa công khai đều thu hồi được token lập tức
C. API dùng khóa công khai để xác minh mà không giữ khóa ký
D. Mọi API dùng khóa công khai để phát hành token
Đáp án đúng: C

Khi một dịch vụ gọi API khác thay mặt người dùng, cách nào giảm lan truyền quyền?
A. Trao đổi lấy token có audience, scope và thời hạn riêng cho API đích
B. Dùng lại access token có audience của dịch vụ gọi ban đầu
C. Gắn toàn bộ quyền người dùng vào header riêng của request
D. Chuyển nguyên refresh token của người dùng cho API đích
Đáp án đúng: A

Vì sao hệ thống có thể lưu bản băm của refresh token ở phía máy chủ?
A. Giảm tác hại nếu kho lưu refresh token bị rò rỉ
B. Thay thế hoàn toàn yêu cầu tạo token bằng bộ sinh an toàn
C. API tài nguyên tự giải mã các claim token
D. Tăng thời hạn tồn tại của token mà không cần làm mới
Đáp án đúng: A

Biện pháp cơ bản nào giúp bảo vệ bearer token khi truyền qua mạng?
A. Mã hóa Base64 token trước khi gửi qua kết nối HTTP thường
B. Dùng TLS xác thực trên mọi đoạn mạng có truyền bearer token
C. Rút ngắn tên header chứa token để giảm cơ hội bị đọc
D. Thêm mã tài khoản vào query string để kiểm tra phía nhận
Đáp án đúng: B

Vì sao tránh đặt access token trong tham số URL?
A. URL dễ bị ghi vào lịch sử, log hoặc referrer
B. URL tự động gia hạn mọi token khi trình duyệt điều hướng
C. URL làm sai chữ ký token qua cân bằng tải
D. URL khiến API không thể kiểm tra claim expiration của JWT
Đáp án đúng: A

Bearer token gửi đến API thường phù hợp với cách truyền nào?
A. Đặt trong mã trạng thái HTTP phản hồi
B. Qua header Authorization của yêu cầu dùng HTTPS
C. Đặt trong đường dẫn tĩnh được cache ở hệ thống CDN
D. Đặt trong query string của liên kết đến API tài nguyên
Đáp án đúng: B

Thuộc tính HttpOnly trên cookie chứa token hỗ trợ kiểm soát gì?
A. Ngăn trình duyệt tự gửi cookie đến đường dẫn hợp lệ
B. Tự động ngăn mọi hành vi CSRF khi cookie được đính kèm
C. Chỉ gửi cookie qua HTTPS theo mặc định
D. Ngăn JavaScript đọc trực tiếp giá trị cookie
Đáp án đúng: D

Tại sao HttpOnly không đủ để loại bỏ rủi ro từ XSS?
A. Script độc hại vẫn đọc được cookie HttpOnly từ document.cookie
B. Script độc hại tự tạo được chữ ký JWT nếu không có khóa ký
C. Script độc hại buộc trình duyệt bỏ qua xác minh TLS mặc định
D. Script độc hại vẫn gửi được yêu cầu hợp lệ bằng phiên đang mở
Đáp án đúng: D

Với phiên dựa trên cookie, cơ chế nào giúp giảm rủi ro CSRF?
A. Để client tự gửi scope thay token ở API
B. Dùng SameSite và kiểm tra CSRF ở thao tác nhạy cảm
C. Chuyển token từ cookie sang URL để dễ phân biệt nguồn gọi
D. Chỉ mã hóa Base64 nội dung cookie trước mỗi yêu cầu mới
Đáp án đúng: B

Khi lưu token ở trình duyệt, nguyên tắc đánh giá nào phù hợp?
A. Ưu tiên localStorage vì các script được cô lập
B. Ưu tiên URL vì lịch sử trình duyệt tự động mã hóa mọi token
C. Dùng một vị trí lưu trữ giống nhau cho mọi loại token và ứng dụng
D. Đánh giá rủi ro XSS, CSRF và quyền truy cập của từng cơ chế
Đáp án đúng: D

Trên thiết bị di động, refresh token nên được lưu ở đâu nếu có thể?
A. Kho bảo mật của hệ điều hành có kiểm soát truy cập và mã hóa
B. Tệp cấu hình thông thường có thể sao chép khi sao lưu thiết bị
C. Bộ nhớ đệm dạng văn bản mà mọi ứng dụng đều có thể truy cập
D. Nhật ký ứng dụng để phục hồi token sau khi thiết bị khởi động
Đáp án đúng: A

Hệ thống logging nên xử lý header chứa bearer token thế nào?
A. Băm token bằng hàm bất kỳ rồi ghi kèm chuỗi token gốc
B. Ghi token nguyên vẹn để so sánh giữa các dịch vụ xử lý
C. Chỉ ẩn chữ ký, giữ nguyên payload JWT
D. Ẩn token nhạy cảm khỏi mọi bản ghi nhật ký
Đáp án đúng: D

Vì sao cần kiểm tra audience khi token đi qua nhiều dịch vụ nội bộ?
A. Giảm chi phí TLS bằng cách chấp nhận token ở mọi dịch vụ
B. Cho phép dịch vụ tự tăng scope nếu token có chữ ký hợp lệ
C. Ngăn dùng token dành cho API này ở API khác
D. Tránh phải xác minh issuer ở những dịch vụ nằm trong mạng riêng
Đáp án đúng: C

Refresh token rotation có đặc điểm nào khi làm mới thành công?
A. Token cũ tiếp tục hợp lệ đến hết hạn của token kế nhiệm
B. Vô hiệu token cũ và phát token kế nhiệm mới
C. Mọi thiết bị của người dùng nhận cùng một refresh token mới
D. Dùng access token làm khóa ký refresh mới
Đáp án đúng: B

Việc sử dụng lại refresh token đã bị thay thế thường gợi ý điều gì?
A. Có thể trình duyệt tự xóa cookie trước khi gửi request
B. Có thể API tài nguyên đang thiếu claim audience hợp lệ
C. Có thể bị sao chép token hoặc race khi làm mới
D. Chữ ký token dùng thuật toán không hợp lệ
Đáp án đúng: C

Để tránh phát hành hai token kế nhiệm khi refresh đồng thời, cần gì?
A. Thêm bộ đếm vào payload của access token đang được sử dụng
B. Cập nhật trạng thái token bằng thao tác nguyên tử
C. Giảm số claim của refresh token khi xác minh
D. Kiểm tra dấu thời gian tại ứng dụng khách trước khi gửi request
Đáp án đúng: B

Với phiên dài ngày, cách giới hạn thời gian nào ngăn gia hạn vô hạn?
A. Có giới hạn không hoạt động và thời hạn tuyệt đối
B. Chỉ tăng thời gian sống của refresh token theo số lần đăng nhập
C. Chỉ gia hạn thời hạn tuyệt đối sau mỗi lần dùng access token
D. Chỉ kiểm tra ngày hết hạn của khóa công khai dùng xác minh
Đáp án đúng: A

Khi logout, giải pháp nào hỗ trợ chặn JWT chưa hết hạn?
A. Tăng thời hạn của token đã phát hành để đồng bộ các máy chủ
B. Đổi định dạng JWT nhưng tiếp tục chấp nhận chữ ký token cũ
C. Kiểm tra thu hồi hoặc trạng thái phiên khi cấp quyền
D. Chỉ xóa token ở trình duyệt rồi tin ở API
Đáp án đúng: C

Khi quyền của người dùng bị thu hẹp, điều gì giúp hạn chế access token cũ?
A. Kiểm tra lại quyền hiện hành hoặc thu hồi token ngay theo chính sách
B. Dựa vào thông tin quyền cũ trong token đến hết phiên tuyệt đối
C. Tăng số lần refresh để token cũ vẫn được sử dụng tại API
D. Chờ đổi khóa ký theo lịch thay vì cập nhật quyền truy cập
Đáp án đúng: A

Làm thế nào để token đặt lại mật khẩu thực sự chỉ dùng một lần?
A. Xóa cookie của trình duyệt sau khi biểu mẫu đã được gửi
B. Đặt token ngắn hơn địa chỉ email của tài khoản người dùng
C. Chỉ đặt thời hạn, không ghi token đã dùng
D. Ghi nhận token đã dùng bằng thao tác nguyên tử
Đáp án đúng: D

Điều gì giúp tránh việc bộ quét email vô tình kích hoạt liên kết nhạy cảm?
A. Đưa token vào tiêu đề email, tránh liên kết
B. Tự động hoàn tất thao tác khi nhận GET đầu tiên có token hợp lệ
C. Yêu cầu xác nhận có chủ đích trước khi thực hiện
D. Kéo dài thời hạn token để bộ quét có thể truy cập nhiều lần
Đáp án đúng: C

Khi có hiện tượng thử đoán token, biện pháp nào phù hợp?
A. Giới hạn tần suất xác minh và cảnh báo khi lỗi tăng bất thường
B. Tăng thời gian sống của token để giảm số yêu cầu cấp lại
C. Bỏ kiểm tra chữ ký cho các địa chỉ IP đã từng đăng nhập
D. Trả chi tiết trạng thái từng tài khoản khi token không hợp lệ
Đáp án đúng: A

DPoP hỗ trợ hạn chế việc dùng lại access token bị đánh cắp bằng cách nào?
A. Yêu cầu bằng chứng ký từ khóa ràng buộc với token
B. Thay trường audience bằng địa chỉ IP hiện tại của máy khách
C. Chỉ rút ngắn hạn token mà không yêu cầu bất kỳ bằng chứng bổ sung
D. Mã hóa token bằng khóa chia sẻ được cấp từ máy chủ
Đáp án đúng: A

Nonce dùng cho yêu cầu nhạy cảm có vai trò chính nào?
A. Tự động gia hạn thời gian sống của token sau mỗi lần xác minh
B. Thay thế việc kiểm tra chữ ký khi token đã có claim expiration
C. Giảm số lượng quyền truy cập cần lưu trong payload của token
D. Phát hiện yêu cầu phát lại khi lưu và xác minh trạng thái của nonce
Đáp án đúng: D

Khi endpoint introspection không phản hồi, lựa chọn nào an toàn mặc định?
A. Cho phép request đến khi dịch vụ hồi phục
B. Tự giảm scope xuống mặc định rồi cho phép thực hiện giao dịch
C. Từ chối khi chưa xác minh được token theo chính sách
D. Tạm coi token hợp lệ dựa trên hình thức chuỗi do khách gửi
Đáp án đúng: C

Điều gì cần cân nhắc khi cache kết quả introspection của token?
A. Cache vô hạn mọi token đã hợp lệ để tránh gọi dịch vụ nữa
B. Bỏ qua trạng thái thu hồi khi request đến từ cùng địa chỉ IP
C. Chỉ cache token hết hạn để phục vụ lịch sử
D. Giới hạn TTL cache theo độ trễ thu hồi cho phép
Đáp án đúng: D

Một JWT thiếu claim bắt buộc hoặc có claim sai kiểu cần được xử lý ra sao?
A. Chuyển token thành opaque token trước khi cấp quyền
B. Từ chối token có claim không đạt schema và chính sách xác minh
C. Thay claim lỗi bằng giá trị do ứng dụng khách gửi thêm
D. Bỏ qua claim sai kiểu nếu phần chữ ký vẫn hợp lệ
Đáp án đúng: B

Khi xử lý lỗi HTTP, trường hợp nào phù hợp với phản hồi 403?
A. Yêu cầu không gửi bất kỳ thông tin xác thực nào đến API
B. JWT sai chữ ký dù scope được khai báo đúng
C. Access token hết hạn và cần được làm mới qua máy chủ cấp
D. Đã xác thực nhưng chưa được cấp quyền vào tài nguyên
Đáp án đúng: D

Những thông tin nào phù hợp trong audit log của vòng đời token?
A. Refresh token hiện tại kèm access token đã thu hồi gần nhất
B. Giá trị nguyên vẹn của token và bí mật ký để phục vụ truy vết
C. Ghi sự kiện, thời gian, định danh tham chiếu và kết quả xử lý
D. Tất cả claim nhạy cảm cùng toàn bộ header xác thực đầu vào
Đáp án đúng: C

Khi phát hiện refresh token bị đẩy lên kho mã nguồn, cần làm gì trước?
A. Chuyển repo thành riêng tư và tắt toàn bộ log
B. Chỉ xóa dòng mã chứa token và giữ token hiện hành đến khi hết hạn
C. Đợi token tự hết hạn rồi thay đổi quy trình bảo mật vào đợt sau
D. Thu hồi token và điều tra phạm vi, dấu vết sử dụng
Đáp án đúng: D

Khi khóa riêng ký JWT bị lộ, tác động lớn nhất cần xử lý là gì?
A. Chỉ những token đặt trong cookie mới bị ảnh hưởng trực tiếp
B. Opaque token ở mọi hệ thống sẽ tự thay đổi cấu trúc xác minh
C. Kẻ tấn công có thể giả mạo token được API tin cậy
D. JWT cũ tự hủy mà không cần thao tác khác
Đáp án đúng: C

Nếu refresh token bị đánh cắp nhưng access token vẫn còn hiệu lực, nên làm gì?
A. Chỉ rút ngắn thời hạn cho các access token phát hành sau sự cố
B. Cho phép token bị lộ tiếp tục refresh để thu thập thêm dấu hiệu
C. Chỉ rút ngắn thời hạn các token mới sau sự cố
D. Thu hồi refresh chain và xử lý access theo mức rủi ro
Đáp án đúng: D

Vì sao hệ thống xác minh token cần đồng bộ đồng hồ đáng tin cậy?
A. Để mọi token có cùng thời hạn với chứng thư TLS máy chủ
B. Để tránh phải xác minh chữ ký trên mọi request đến API
C. Để tăng độ khó dự đoán token được sinh từ bộ đếm tăng dần
D. Xác minh nhất quán mốc iat, nbf và exp
Đáp án đúng: D

Claim jti có thể hỗ trợ thu hồi hoặc chống phát lại bằng điều kiện nào?
A. Cần lưu trạng thái các định danh token đã sử dụng
B. Chỉ cần jti khác nhau ở các token được phát hành cùng giây
C. Chỉ cần jti xuất hiện trong payload mà không kiểm tra bổ sung
D. Yêu cầu jti trùng với audience của mọi dịch vụ
Đáp án đúng: A

Để tránh token thử nghiệm được chấp nhận ở production, cần kiểm soát gì?
A. Tách issuer, audience hoặc khóa theo từng môi trường
B. Cho production tin mọi issuer nếu token có expiration hợp lệ
C. Để ứng dụng khách tự khai báo môi trường trong query string
D. Cho hai môi trường chia sẻ toàn bộ khóa để dễ triển khai dịch vụ
Đáp án đúng: A
