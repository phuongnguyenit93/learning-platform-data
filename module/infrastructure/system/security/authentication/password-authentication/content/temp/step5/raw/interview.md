Bạn giải thích vai trò của mật khẩu trong xác thực danh tính và những giới hạn của việc chỉ dựa vào một bí mật do người dùng biết như thế nào?
Bạn phân biệt xác thực bằng mật khẩu với việc lưu trữ, quản lý và khôi phục thông tin xác thực trong toàn bộ vòng đời tài khoản như thế nào?
Bạn xây dựng threat model cho luồng đăng ký, đăng nhập, đổi mật khẩu, đặt lại mật khẩu và khôi phục tài khoản như thế nào?
Bạn phân biệt password authentication với passwordless authentication và xác định khi nào mật khẩu vẫn là một yếu tố cần được hỗ trợ như thế nào?
Bạn đánh giá rủi ro khi người dùng tái sử dụng cùng một mật khẩu trên nhiều dịch vụ và cách giảm thiểu credential stuffing như thế nào?
Bạn lựa chọn chính sách mật khẩu dựa trên mức độ nhạy cảm của tài khoản, nguy cơ bị tấn công và trải nghiệm người dùng như thế nào?
Bạn xác định độ dài tối thiểu và tối đa của mật khẩu dựa trên khả năng chống đoán và giới hạn kỹ thuật của hệ thống như thế nào?
Bạn so sánh hiệu quả của mật khẩu dài, khó đoán với các quy tắc bắt buộc phối hợp chữ hoa, chữ số và ký tự đặc biệt như thế nào?
Bạn thiết kế chính sách cho phép passphrase dài, khoảng trắng và ký tự Unicode mà vẫn bảo đảm các hệ thống xử lý nhất quán như thế nào?
Bạn xử lý chuẩn hóa Unicode và quy tắc so sánh mật khẩu để cùng một mật khẩu không bị diễn giải khác nhau giữa các thành phần như thế nào?
Bạn lựa chọn giới hạn kích thước đầu vào mật khẩu để tránh từ chối mật khẩu hợp lệ nhưng vẫn ngăn request tiêu tốn tài nguyên quá mức như thế nào?
Bạn giải thích vì sao không nên âm thầm cắt ngắn mật khẩu trước khi xác minh hoặc băm như thế nào?
Bạn thiết kế chính sách chặn mật khẩu phổ biến, dễ đoán hoặc đã xuất hiện trong các bộ dữ liệu rò rỉ như thế nào?
Bạn đánh giá việc kiểm tra mật khẩu bị lộ qua dịch vụ bên ngoài và bảo vệ quyền riêng tư của người dùng trong quá trình kiểm tra như thế nào?
Bạn xác định khi nào nên yêu cầu người dùng đổi mật khẩu và vì sao không nên bắt buộc đổi định kỳ nếu không có dấu hiệu rủi ro như thế nào?
Bạn cho phép password manager, autofill và paste mật khẩu trong biểu mẫu xác thực mà vẫn duy trì bảo vệ chống tấn công như thế nào?
Bạn thiết kế phản hồi về độ mạnh mật khẩu để hướng dẫn người dùng mà không tiết lộ quá nhiều chi tiết cho kẻ tấn công như thế nào?
Bạn xử lý việc người dùng chọn lại mật khẩu cũ hoặc mật khẩu đã bị lộ bằng chính sách nào?
Bạn phân biệt mật khẩu người dùng tự chọn với mật khẩu tạm thời do hệ thống cấp và kiểm soát việc sử dụng lần đầu như thế nào?
Bạn giải thích vì sao mật khẩu phải được băm bằng password hashing function chuyên dụng thay vì lưu plaintext hoặc mã hóa có thể giải ngược như thế nào?
Bạn phân biệt hash mật khẩu với hash thông thường dùng cho checksum hoặc kiểm tra toàn vẹn dữ liệu như thế nào?
Bạn so sánh Argon2id, scrypt, bcrypt và PBKDF2 theo khả năng chống tấn công offline, yêu cầu tài nguyên và mức độ hỗ trợ triển khai như thế nào?
Bạn lựa chọn tham số memory cost, time cost và parallelism cho Argon2id dựa trên phần cứng, tải xác thực và ngân sách độ trễ như thế nào?
Bạn xác định work factor phù hợp cho password hashing bằng benchmark trên môi trường triển khai thực tế như thế nào?
Bạn cân bằng chi phí tính toán và bộ nhớ của password hashing để làm chậm tấn công offline mà không gây quá tải dịch vụ xác thực như thế nào?
Bạn tạo salt ngẫu nhiên, duy nhất cho từng mật khẩu bằng nguồn sinh số ngẫu nhiên an toàn và quản lý salt cùng hash như thế nào?
Bạn giải thích vì sao salt không cần giữ bí mật nhưng vẫn phải độc lập và đủ ngẫu nhiên cho từng bản ghi mật khẩu như thế nào?
Bạn phân biệt salt với pepper và xác định khi nào hệ thống cần thêm pepper để tăng lớp bảo vệ như thế nào?
Bạn lưu trữ và bảo vệ pepper tách khỏi cơ sở dữ liệu mật khẩu bằng secret manager hoặc HSM như thế nào?
Bạn thiết kế quy trình luân chuyển pepper khi thay đổi khóa mà không làm mất khả năng xác minh các mật khẩu đã lưu như thế nào?
Bạn lựa chọn định dạng lưu password hash có chứa thuật toán, salt và tham số để hỗ trợ nâng cấp thuật toán về sau như thế nào?
Bạn thiết kế cơ chế algorithm agility để nâng cấp password hashing khi tiêu chuẩn hoặc năng lực phần cứng thay đổi như thế nào?
Bạn triển khai rehash-on-login để nâng cấp hash cũ sau khi người dùng xác thực thành công mà không cần đặt lại toàn bộ mật khẩu như thế nào?
Bạn xử lý tài khoản có hash theo thuật toán yếu hoặc tham số cũ nhưng người dùng chưa đăng nhập lại trong thời gian dài như thế nào?
Bạn đánh giá rủi ro khi dùng cùng salt cho nhiều tài khoản hoặc dùng salt cố định trong toàn hệ thống như thế nào?
Vì sao MD5, SHA-1 hoặc SHA-256 đơn lẻ không phù hợp để lưu mật khẩu dù chúng hữu ích cho checksum và kiểm tra tính toàn vẹn?
Bạn sử dụng thư viện password hashing đã được kiểm chứng và tránh tự triển khai thuật toán băm mật khẩu như thế nào?
Bạn thiết kế quy trình xác minh hash để so sánh an toàn, hạn chế rò rỉ thông tin qua timing và xử lý lỗi định dạng như thế nào?
Bạn kiểm soát tài nguyên CPU và bộ nhớ của password hashing để chống việc endpoint đăng nhập bị lợi dụng gây từ chối dịch vụ như thế nào?
Bạn bảo vệ password hash trong cơ sở dữ liệu, backup, bản sao phân tích và môi trường staging khỏi truy cập không cần thiết như thế nào?
Bạn xác định những dữ liệu xác thực nào tuyệt đối không được ghi vào application log, audit log, trace hoặc error report như thế nào?
Bạn mô tả trình tự xử lý một lần đăng nhập từ nhận identifier và password đến kiểm tra hash, phát hành session hoặc token như thế nào?
Bạn thiết kế thông báo lỗi đăng nhập thống nhất để tránh tiết lộ tài khoản có tồn tại, đang bị khóa hoặc có mật khẩu sai như thế nào?
Bạn ngăn username hoặc email enumeration qua nội dung response, status code, thời gian phản hồi và luồng đăng nhập như thế nào?
Bạn đánh giá side channel timing có thể tiết lộ trạng thái tài khoản hoặc kết quả xác minh mật khẩu, đồng thời dùng dummy hash hoặc kỹ thuật phù hợp để giảm thiểu như thế nào?
Bạn thiết kế rate limiting theo tài khoản, địa chỉ nguồn, thiết bị hoặc tín hiệu rủi ro để hạn chế brute force như thế nào?
Bạn phân biệt rate limiting, progressive delay, temporary lockout và permanent lockout về hiệu quả bảo vệ và nguy cơ gây DoS như thế nào?
Bạn lựa chọn ngưỡng và thời gian khóa tài khoản sao cho hạn chế password guessing mà không để kẻ tấn công khóa tài khoản người dùng hợp lệ như thế nào?
Bạn xử lý tấn công phân tán dùng nhiều địa chỉ IP hoặc nhiều tài khoản để né giới hạn đăng nhập như thế nào?
Bạn phát hiện credential stuffing bằng cách kết hợp tỷ lệ thất bại, thiết bị, nguồn truy cập và mẫu hành vi đăng nhập như thế nào?
Bạn phân biệt password spraying với brute force nhắm vào một tài khoản và thiết kế cơ chế phát hiện phù hợp như thế nào?
Bạn sử dụng CAPTCHA hoặc challenge bổ sung trong luồng đăng nhập theo tín hiệu rủi ro mà không biến chúng thành lớp bảo vệ duy nhất như thế nào?
Bạn bảo vệ endpoint đăng nhập trước request flooding và chi phí tính toán lớn từ password hashing như thế nào?
Bạn tổ chức thứ tự kiểm tra input, tra cứu tài khoản và xác minh hash để giảm lãng phí tài nguyên mà vẫn hạn chế account enumeration như thế nào?
Bạn bảo đảm mật khẩu được truyền an toàn qua mạng bằng TLS và xử lý rủi ro khi TLS kết thúc tại reverse proxy như thế nào?
Bạn thiết kế session sau khi xác thực thành công để chống session fixation, session hijacking và tái sử dụng phiên cũ như thế nào?
Bạn xác định khi nào cần thu hồi session hoặc token hiện tại sau khi người dùng đổi mật khẩu hoặc phát hiện tài khoản bị xâm nhập như thế nào?
Bạn phân biệt xác thực thành công bằng mật khẩu với việc duy trì trạng thái đăng nhập an toàn trong suốt vòng đời session như thế nào?
Bạn thiết kế xác minh lại mật khẩu trước thao tác nhạy cảm như đổi email, thay yếu tố xác thực hoặc thay đổi thông tin thanh toán như thế nào?
Bạn xây dựng quy trình đổi mật khẩu khi người dùng còn đăng nhập và xác minh mật khẩu hiện tại để ngăn thay đổi trái phép như thế nào?
Bạn xử lý việc người dùng quên mật khẩu bằng reset token hoặc mã xác minh có entropy cao, thời hạn ngắn và chỉ dùng một lần như thế nào?
Bạn lưu trữ reset token theo dạng hash và xác minh token mà không để giá trị dùng được bị lộ qua cơ sở dữ liệu như thế nào?
Bạn ràng buộc reset token với đúng tài khoản, mục đích và phiên yêu cầu để ngăn token bị dùng sai ngữ cảnh như thế nào?
Bạn ngăn reset token bị rò rỉ qua URL referrer, access log, analytics hoặc lịch sử trình duyệt như thế nào?
Bạn thiết kế phản hồi yêu cầu đặt lại mật khẩu để không tiết lộ email hoặc username có tồn tại trong hệ thống như thế nào?
Bạn giới hạn số lần gửi email hoặc SMS reset để tránh bị lạm dụng gửi spam và gây phiền nhiễu cho người dùng như thế nào?
Bạn xác định thời điểm reset token phải bị vô hiệu hóa sau khi dùng, hết hạn, yêu cầu mới hoặc thay đổi thông tin tài khoản như thế nào?
Bạn thông báo cho người dùng qua kênh tin cậy khi mật khẩu được đổi hoặc đặt lại và cung cấp cách phản ứng khi họ không thực hiện thao tác như thế nào?
Bạn thiết kế quy trình khôi phục tài khoản khi người dùng mất quyền truy cập email hoặc số điện thoại đã đăng ký như thế nào?
Bạn đánh giá rủi ro của help desk, câu hỏi bảo mật và xác minh thủ công trong quá trình khôi phục mật khẩu như thế nào?
Bạn ngăn account recovery trở thành đường vòng yếu hơn cơ chế đăng nhập và các yếu tố bảo vệ hiện có như thế nào?
Bạn xác minh yêu cầu đổi mật khẩu đến từ người dùng hợp lệ khi tài khoản đang có dấu hiệu bị chiếm quyền như thế nào?
Bạn thiết kế lưu giữ password history bằng hash riêng biệt và kiểm tra tái sử dụng mật khẩu mà không lưu plaintext như thế nào?
Bạn phối hợp password authentication với MFA để tăng mức đảm bảo mà không làm luồng khôi phục mật khẩu vô tình bỏ qua MFA như thế nào?
Bạn xác định khi nào nên yêu cầu step-up authentication hoặc xác minh lại trước khi cho phép thay đổi mật khẩu như thế nào?
Bạn xử lý tình huống kẻ tấn công đã đổi mật khẩu và thu hồi email khôi phục để ngăn chủ tài khoản lấy lại quyền kiểm soát như thế nào?
Bạn thiết kế giám sát cho đăng nhập thành công, thất bại, khóa tài khoản, đổi mật khẩu và reset để phát hiện hành vi bất thường như thế nào?
Bạn lựa chọn các trường cần ghi trong audit event về password authentication mà không lưu mật khẩu, hash hoặc reset token như thế nào?
Bạn xác định các chỉ số như login failure rate, reset rate, lockout rate và password hash latency để theo dõi sức khỏe hệ thống như thế nào?
Bạn phân biệt lỗi xác thực do người dùng nhập sai với lỗi hệ thống do database, hash verifier hoặc dịch vụ gửi reset message như thế nào?
Bạn xây dựng quy trình ứng phó khi cơ sở dữ liệu password hash bị rò rỉ, bao gồm đánh giá thuật toán, tham số, salt và nguy cơ crack offline như thế nào?
Bạn quyết định khi nào cần buộc reset mật khẩu hàng loạt, thu hồi session hoặc tăng cường MFA sau một sự cố rò rỉ credential như thế nào?
Bạn kiểm tra xem mật khẩu hoặc reset token có xuất hiện trong log, crash dump, telemetry, backup hoặc hệ thống hỗ trợ hay không bằng cách nào?
Bạn thiết kế kiểm thử cho brute force, enumeration, credential stuffing, replay reset token và timing differences trong luồng password authentication như thế nào?
Bạn xây dựng kiểm thử cho password hashing để xác minh salt riêng, tham số đúng, thuật toán có thể nâng cấp và xác minh không bị suy giảm như thế nào?
Bạn kiểm thử các trường hợp mật khẩu dài, Unicode, khoảng trắng, ký tự đặc biệt và đầu vào vượt giới hạn để phát hiện truncation hoặc xử lý không nhất quán như thế nào?
Bạn xác lập tiêu chí nghiệm thu end-to-end để chứng minh hệ thống lưu mật khẩu an toàn, chống dò đoán tài khoản và hỗ trợ đổi hoặc khôi phục mật khẩu đáng tin cậy như thế nào?
