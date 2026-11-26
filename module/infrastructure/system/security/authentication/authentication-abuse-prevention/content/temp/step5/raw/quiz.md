Brute force trong luồng đăng nhập mô tả hành vi nào?
A. Dùng cặp đăng nhập bị lộ để thử trên nhiều dịch vụ.
B. Thử ít mật khẩu phổ biến trên nhiều tài khoản khác nhau.
C. Dùng session token đánh cắp để vào tài khoản.
D. Thử nhiều mật khẩu để đoán một tài khoản.
Đáp án đúng: D

Credential stuffing khác brute force ở đặc điểm nào?
A. Thử một mật khẩu phổ biến trên nhiều tài khoản.
B. Chiếm quyền phiên bằng cookie đã bị đánh cắp.
C. Thử nhiều tổ hợp mật khẩu trên cùng một tài khoản.
D. Dùng lại cặp thông tin đăng nhập bị lộ.
Đáp án đúng: D

Password spraying thường được kẻ tấn công thực hiện như thế nào?
A. Thử ít mật khẩu phổ biến trên nhiều tài khoản.
B. Gửi lại mã khôi phục đã hết hạn nhiều lần.
C. Thử rất nhiều mật khẩu trên cùng một tài khoản.
D. Dùng cặp đăng nhập bị lộ để thử ở dịch vụ khác.
Đáp án đúng: A

Vì sao giới hạn số lần thử chỉ theo địa chỉ IP không đủ chống credential stuffing?
A. Phân tán request qua nhiều IP để né quota từng nguồn.
B. Đổi cổng nguồn TCP nhưng giữ nguyên IP cho mọi request.
C. Địa chỉ IP tự đổi sau mỗi lần đăng nhập thất bại.
D. Rate limit IP chỉ có tác dụng với kết nối HTTP.
Đáp án đúng: A

Dấu hiệu nào gợi ý credential stuffing hơn lỗi nhập mật khẩu thông thường?
A. Nhiều nhân viên đổi mật khẩu sau thông báo bảo trì nội bộ.
B. Các cặp email/mật khẩu đã lộ được thử trên dịch vụ này.
C. Tài khoản đăng nhập thành công từ thiết bị đã ghi nhớ lâu ngày.
D. Một tài khoản quen thuộc nhập sai vài lần từ thiết bị cũ.
Đáp án đúng: B

Một cơ chế rate limit đăng nhập vững chắc nên kết hợp chiều giới hạn nào?
A. Chỉ giới hạn số lần đổi mật khẩu của từng người dùng trong ngày.
B. Kết hợp giới hạn theo tài khoản, nguồn và toàn hệ thống.
C. Giới hạn tổng số request của toàn ứng dụng trong từng phút.
D. Chỉ giới hạn request từ một địa chỉ IP cố định theo từng giờ.
Đáp án đúng: B

Muốn giảm hiệu quả của việc xoay IP khi dò mật khẩu, nên bổ sung giới hạn nào?
A. Theo tài khoản chuẩn hóa, kết hợp giới hạn theo IP.
B. Theo số cổng TCP mà mỗi client dùng khi mở kết nối mới.
C. Theo kích thước body của request đăng nhập gửi lên server.
D. Theo số lần tải trang chủ trước khi mở form đăng nhập.
Đáp án đúng: A

Một dịch vụ xác thực cần ngăn cả tấn công tập trung và tấn công phân tán; cách thiết kế nào phù hợp?
A. Bộ đếm riêng theo IP và bỏ qua các chiều tín hiệu khác.
B. Chỉ tăng giới hạn khi số tài khoản đăng nhập đồng thời tăng.
C. Một bộ đếm toàn cục duy nhất cho mọi tài khoản trong hệ thống.
D. Quota theo tài khoản, nguồn, thiết bị và toàn cục.
Đáp án đúng: D

Progressive delay trong đăng nhập thường mang lại lợi ích nào?
A. Tự bỏ qua MFA sau một số lần đăng nhập thất bại.
B. Cho request tiếp tục không giới hạn nếu mật khẩu sai liên tiếp.
C. Tăng dần chi phí thử sai mà không khóa cứng tài khoản.
D. Khóa tài khoản vĩnh viễn ngay sau lần thử sai đầu tiên.
Đáp án đúng: C

Khóa tài khoản cứng sau vài lần nhập sai có thể tạo ra rủi ro nào?
A. Người dùng có thể đọc dữ liệu từ tài khoản khác sau đó.
B. Mật khẩu đã băm có thể khôi phục từ bộ đếm lỗi.
C. Kẻ tấn công cố ý khóa tài khoản của người dùng hợp lệ.
D. Hệ thống bỏ qua xác thực khi số tài khoản tăng cao.
Đáp án đúng: C

Khi API đăng nhập từ chối vì vượt ngưỡng rate limit, phản hồi nào thường phù hợp?
A. HTTP 401 kèm mật khẩu đúng để client đồng bộ trạng thái.
B. HTTP 429 và Retry-After nếu biết lúc thử lại.
C. HTTP 500 buộc client đổi endpoint xác thực ngay lập tức.
D. HTTP 200 cùng thông báo chung để client tiếp tục gửi request.
Đáp án đúng: B

Vì sao nên áp dụng cùng quy tắc chuẩn hóa username trước khi đếm rate limit và xác thực?
A. Bỏ qua phân biệt chữ hoa chữ thường ở mọi thành phần hệ thống.
B. Buộc mọi username phải chuyển thành email hợp lệ trước khi xử lý.
C. Dùng cùng quy tắc canonicalization với bước tra cứu danh tính.
D. Ẩn username khỏi log bằng cách mã hóa trước khi so sánh.
Đáp án đúng: C

Để giảm dò tìm tài khoản hợp lệ qua form đăng nhập, phản hồi lỗi nên được thiết kế ra sao?
A. Thông báo riêng khi tài khoản tồn tại nhưng mật khẩu không đúng.
B. Trả HTTP 404 khi username không có trong hệ thống.
C. Dùng thông báo và phản hồi tương đương khi xác thực sai.
D. Tăng thời gian phản hồi khi tài khoản đã bị khóa.
Đáp án đúng: C

Form yêu cầu đặt lại mật khẩu có thể bị dùng để dò tài khoản; biện pháp nào phù hợp?
A. Trả trạng thái tài khoản trực tiếp trong response cho client.
B. Hiển thị lần đăng nhập gần nhất để người gửi đối chiếu.
C. Chỉ gửi thư xác nhận khi địa chỉ đã đăng ký trong hệ thống.
D. Trả cùng phản hồi cho địa chỉ có hoặc không có tài khoản.
Đáp án đúng: D

CAPTCHA nên được áp dụng theo cách nào để hỗ trợ chống bot mà giảm ma sát?
A. Chỉ hiện CAPTCHA sau khi tài khoản bị khóa cứng.
B. Dùng CAPTCHA làm biện pháp duy nhất cho mọi lần đăng nhập.
C. Bỏ rate limit sau khi người dùng giải CAPTCHA thành công.
D. Kích hoạt theo rủi ro, kết hợp rate limit và giám sát.
Đáp án đúng: D

Nhiều người dùng hợp lệ truy cập từ cùng NAT doanh nghiệp; giới hạn theo IP quá thấp gây vấn đề gì?
A. Có thể chặn nhầm nhiều người dùng chung mạng doanh nghiệp.
B. Mọi request từ NAT được xem là đã xác thực sẵn.
C. Một tài khoản dùng chung phiên với toàn bộ mạng doanh nghiệp.
D. Browser không thể gửi cookie qua HTTPS sau khi dùng NAT.
Đáp án đúng: A

Token bucket thường phù hợp với mục tiêu rate limiting nào?
A. Đếm số tài khoản duy nhất mà một IP đã truy cập.
B. Tăng tốc độ request theo số lần đăng nhập thành công.
C. Cấm mọi request vượt lịch cố định và không cho phép burst.
D. Cho phép burst ngắn nhưng giới hạn tốc độ trung bình.
Đáp án đúng: D

Trong hệ thống xác thực chạy nhiều instance, bộ đếm rate limit nên cập nhật thế nào?
A. Đặt bộ đếm trong cookie client để các instance tự cộng.
B. Giữ bộ đếm trong bộ nhớ riêng của từng instance đang chạy.
C. Dùng cập nhật nguyên tử trên bộ đếm dùng chung.
D. Đồng bộ bộ đếm bằng log bất đồng bộ sau khi trả response.
Đáp án đúng: C

Ngoài IP, tín hiệu nào có thể giúp nhận diện tự động hóa đăng nhập?
A. Tên hiển thị và ảnh đại diện mà người dùng tự chọn trong hồ sơ.
B. Nhịp request, đặc trưng client và mẫu hành vi theo thời gian.
C. Ngôn ngữ giao diện duy nhất được chọn trong trang cài đặt.
D. Số lượng bài viết công khai mà tài khoản từng tạo trước đây.
Đáp án đúng: B

Một dịch vụ muốn kiểm tra mật khẩu mới có nằm trong tập mật khẩu bị lộ; cách nào giảm tiết lộ mật khẩu cho bên tra cứu?
A. Lưu mật khẩu mới vào log để đối chiếu định kỳ với danh sách.
B. Tra cứu theo prefix hash để giảm lộ mật khẩu.
C. Gửi username và mật khẩu rõ cho nhà cung cấp chống bot.
D. Gửi mật khẩu rõ đến dịch vụ tra cứu qua query string.
Đáp án đúng: B

Người dùng liên tục nhận push MFA mà không tự đăng nhập; biện pháp nào trực tiếp giảm MFA fatigue?
A. Giới hạn số push và dùng number matching.
B. Tắt thông báo MFA trong giờ ngoài hành chính của người dùng.
C. Tự động chấp thuận push sau vài lần người dùng từ chối.
D. Tăng thời hạn phiên để người dùng ít phải xác thực lại.
Đáp án đúng: A

Endpoint gửi lại OTP có thể bị lạm dụng để gây chi phí SMS; nên kiểm soát thế nào?
A. Cho phép gửi lại không giới hạn nếu OTP trước chưa được dùng.
B. Giới hạn theo tài khoản, đích nhận và challenge.
C. Chỉ giới hạn số lần nhập OTP, không giới hạn số lần gửi.
D. Tạo OTP mới mỗi khi trang đăng nhập được tải lại.
Đáp án đúng: B

Để giảm thử đoán OTP trong một challenge, hệ thống nên làm gì?
A. Giới hạn số lần thử và thời hạn của challenge.
B. Chấp nhận mọi mã trong cùng khoảng thời gian một ngày.
C. Chỉ kiểm tra OTP có đúng độ dài ký tự đã quy định.
D. Dùng OTP dài hạn cho đến khi người dùng đổi mật khẩu.
Đáp án đúng: A

Một mã TOTP hợp lệ đã được dùng thành công trong cửa sổ thời gian hiện tại; xử lý nào giúp ngăn phát lại?
A. Chấp nhận mã lặp nếu người dùng vượt qua CAPTCHA.
B. Cho phép mã dùng lại đến khi bước thời gian kế tiếp bắt đầu.
C. Gia hạn mã hiện tại nếu request đến từ cùng địa chỉ IP.
D. Ghi nhận time-step đã dùng và từ chối mã lặp.
Đáp án đúng: D

SMS OTP có rủi ro nào cần xét khi dùng làm yếu tố xác thực?
A. Mã SMS luôn bị lộ khi trình duyệt bật JavaScript.
B. SMS không thể được chuyển qua mạng di động mã hóa.
C. Số điện thoại tự xác minh thiết bị vật lý của người dùng.
D. SIM swap có thể chuyển quyền nhận mã sang kẻ khác.
Đáp án đúng: D

Recovery code nên được quản lý thế nào để hạn chế lạm dụng?
A. Sinh ngẫu nhiên, lưu hash và vô hiệu sau một lần dùng.
B. Lưu mã rõ để hỗ trợ viên có thể đọc lại khi cần.
C. Cho phép dùng lại mã đến khi mật khẩu được đổi hai lần.
D. Dùng một mã cố định cho mọi lần khôi phục tài khoản.
Đáp án đúng: A

Token đặt lại mật khẩu cần có thuộc tính nào?
A. Dùng chung cho các tài khoản cùng địa chỉ email.
B. Dự đoán được từ username và ngày tạo tài khoản.
C. Ngẫu nhiên, ngắn hạn, gắn tài khoản và dùng một lần.
D. Không hết hạn để người dùng khôi phục bất cứ lúc nào.
Đáp án đúng: C

Sau khi người dùng đặt lại mật khẩu thành công, hành động nào giảm nguy cơ phiên cũ bị chiếm dụng?
A. Giữ nguyên mọi phiên để tránh gián đoạn thiết bị khác.
B. Gia hạn refresh token cũ để đồng bộ trạng thái tài khoản.
C. Thu hồi hoặc yêu cầu xác thực lại các phiên đang mở.
D. Chỉ xóa cookie của tab vừa thực hiện đặt lại mật khẩu.
Đáp án đúng: C

Session fixation được giảm thiểu trực tiếp bằng biện pháp nào?
A. Đặt session ID theo username đã chuẩn hóa của người dùng.
B. Đổi session ID sau khi xác thực hoặc nâng quyền.
C. Mã hóa session ID bằng Base64 trước khi lưu cookie.
D. Giữ nguyên session ID để không mất dữ liệu trước đăng nhập.
Đáp án đúng: B

Khi nghi ngờ session token bị đánh cắp, phản ứng nào phù hợp?
A. Thu hồi phiên bị ảnh hưởng và yêu cầu xác thực lại.
B. Chỉ chặn IP hiện tại và giữ nguyên token đang hoạt động.
C. Chỉ đổi giao diện đăng nhập mà không thay đổi phiên hiện tại.
D. Gia hạn token để người dùng hợp lệ không bị đăng xuất.
Đáp án đúng: A

Refresh token rotation có thể phát hiện tình huống nào?
A. Người dùng đăng nhập thành công từ một trình duyệt mới.
B. Access token hết hạn đúng theo thời gian cấu hình ban đầu.
C. Token cũ bị dùng lại sau rotation, gợi ý bị sao chép.
D. Người dùng đổi mật khẩu nhưng vẫn dùng thiết bị quen thuộc.
Đáp án đúng: C

Một hệ thống dùng access token tự chứa và cần thu hồi nhanh sau sự cố; lựa chọn nào giúp giảm cửa sổ rủi ro?
A. Chỉ xóa cookie client và giữ nguyên token đã phát hành.
B. Tăng thời gian cache khóa ký để token được xác minh nhanh.
C. Token dài hạn để giảm số lần xác thực với máy chủ.
D. Token ngắn hạn cùng cơ chế thu hồi hoặc kiểm tra trạng thái.
Đáp án đúng: D

Đăng nhập từ vị trí địa lý mới nên được đánh giá như thế nào?
A. Bỏ qua tín hiệu khác nếu IP thuộc nhà mạng lớn.
B. Từ chối mọi lần đăng nhập ngoài quốc gia thường dùng.
C. Đánh giá cùng thiết bị, thời gian và hành vi.
D. Coi vị trí mới là bằng chứng chắc chắn tài khoản bị chiếm.
Đáp án đúng: C

Một tài khoản vừa đăng nhập thành công rồi đổi email khôi phục và thêm yếu tố MFA mới; tín hiệu nào đáng quan tâm?
A. Thay đổi nhạy cảm liên tiếp cần xác minh tăng cường.
B. Người dùng mở trang trợ giúp trước khi đăng nhập thành công.
C. Phiên đăng nhập có thời lượng ngắn hơn mức trung bình.
D. Tài khoản truy cập từ thiết bị đã ghi nhớ nhiều tháng.
Đáp án đúng: A

Khi ghi log để phát hiện credential stuffing, cách nào cân bằng điều tra và quyền riêng tư?
A. Chỉ ghi request thành công và bỏ qua mọi lần thất bại.
B. Ghi sự kiện với định danh giả danh, không ghi bí mật.
C. Lưu cookie phiên đầy đủ để có thể tái hiện đăng nhập.
D. Ghi toàn bộ password và OTP để nhóm điều tra đối chiếu.
Đáp án đúng: B

Phát hiện một đợt chiếm đoạt tài khoản đang diễn ra, bước ứng phó nào nên được ưu tiên?
A. Tăng ngưỡng rate limit để giảm số cảnh báo phát sinh trên toàn hệ thống.
B. Chặn mẫu tấn công, thu hồi phiên và bảo vệ tài khoản.
C. Tắt toàn bộ MFA để người dùng có thể đăng nhập trở lại.
D. Xóa log xác thực nhằm tránh lưu dữ liệu nhạy cảm.
Đáp án đúng: B
