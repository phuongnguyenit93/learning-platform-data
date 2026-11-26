Một ứng dụng đặt hàng sử dụng MailSender gửi SimpleMailMessage xác nhận đơn; khi thêm yêu cầu gửi ảnh hóa đơn, nhóm phát triển vẫn dùng API thư văn bản và không tạo được nội dung MIME mong muốn.
Nhóm CRM cấu hình JavaMailSender cho email đăng ký tài khoản; một môi trường chỉ khởi tạo bean MailSender nên service yêu cầu JavaMailSender không thể khởi động cùng phần còn lại của ứng dụng.
Một hệ thống bán vé tạo SimpleMailMessage làm bản mẫu chung cho nhiều request; các thread thay đổi người nhận trên cùng object khiến khách đôi lúc nhận thông tin đặt vé của người khác.
Đội vận hành dùng SimpleMailMessage để gửi thông báo nhiều dòng tiếng Việt; một số ký tự có dấu bị hiển thị sai khi chuyển qua máy chủ SMTP có thiết lập encoding khác.
Một dịch vụ quản lý học viên thiết lập người nhận To, Cc và Bcc cho cùng chiến dịch; email phản hồi từ khách làm lộ danh sách người nhận do ứng dụng chọn sai trường địa chỉ.
Nhóm phát triển xây subject email bằng cách nối tên khách và mã đơn; tên người dùng chứa dấu xuống dòng khiến tiêu đề hoặc header bị xử lý khác dự kiến.
Ứng dụng phục hồi mật khẩu tạo nội dung email ngay sau khi người dùng yêu cầu; trường email bị bỏ trống và JavaMailSender phát lỗi trước khi SMTP chấp nhận thư.
Đội gửi hóa đơn lưu địa chỉ người nhận có dấu cách ở cuối; dữ liệu qua validation nhưng Jakarta Mail từ chối cú pháp địa chỉ tại thời điểm gửi.
Một hệ thống tích điểm dùng danh sách người nhận được nạp từ database; một email sai định dạng trong batch làm luồng gửi dừng và những người còn lại không nhận thông báo.
Nhóm quản trị truyền địa chỉ From khác tài khoản SMTP đã xác thực; relay của nhà cung cấp từ chối thư vì chính sách không cho dùng danh tính gửi này.
Ứng dụng gửi xác thực tài khoản đặt Reply-To bằng email hỗ trợ; khách bấm trả lời nhưng thư đi tới hộp thư không còn hoạt động và bộ phận hỗ trợ không biết.
Đội marketing xây thư có địa chỉ hiển thị tên thương hiệu chứa ký tự Unicode; một số client hiển thị sai tên người gửi dù nội dung body vẫn đọc được.
Một dịch vụ gửi thông báo sử dụng MailSender với nhiều người nhận trên một SimpleMailMessage; nhóm nghiệp vụ muốn cá nhân hóa từng thư nhưng mọi người đều thấy cùng mã giao dịch.
Nhóm phát triển gọi JavaMailSender.send trong vòng lặp request HTTP; khi gửi tới 50 người, một lỗi SMTP giữa vòng lặp làm số thư đã nhận khác trạng thái API trả về.
Ứng dụng dùng một địa chỉ Bcc để lưu bản sao audit của mọi email; khi mailbox audit bị đầy, một số yêu cầu gửi bị từ chối dù người nhận chính có địa chỉ hợp lệ.
Đội quản lý sự kiện đặt email người tham gia vào trường Reply-To thay vì To; SMTP chấp nhận thư nhưng người tham gia không nhận được thông báo đăng ký.
Một hệ thống phát thư hai ngôn ngữ dựa vào LocaleContext của request; mail gửi từ job nền không có locale nên template sử dụng ngôn ngữ mặc định.
Nhóm lưu subject và body vào database để gửi lại khi thất bại; các trường trạng thái đơn thay đổi giữa hai lần gửi khiến nội dung thư không còn phản ánh cùng một thời điểm nghiệp vụ.
Ứng dụng tạo thư xác nhận trước khi entity Order nhận ID từ database; tiêu đề và đường dẫn theo mã đơn bị rỗng ở một số giao dịch.
Đội chạy chiến dịch gửi thư có danh sách địa chỉ trùng nhau ở nhiều phân khúc; cùng khách hàng nhận nhiều thư giống nhau trong một buổi mà hệ thống báo số người nhận cao hơn thực tế.
Một dịch vụ dùng MimeMessageHelper để gửi HTML; nội dung được đặt vào phần plain text nên khách thấy nguyên thẻ markup trong ứng dụng email.
Nhóm chuyển email thông báo từ plain text sang HTML; thư bị chặn ở một số bộ lọc vì không có phiên bản nội dung thay thế phù hợp với client chỉ hỗ trợ văn bản.
Ứng dụng gửi hóa đơn bằng MimeMessage multipart/alternative; thứ tự và content type của các phần không phù hợp khiến một số client chỉ hiển thị bản văn bản cũ.
Đội phát triển dùng MimeMessageHelper với nội dung UTF-8 nhưng template được lưu bằng charset khác; khách nhìn tên sản phẩm tiếng Việt thành ký tự lỗi.
Một nền tảng thương mại gửi bảng thông tin sản phẩm qua HTML email; client chặn stylesheet ngoài và bảng giá không còn dễ đọc trên thiết bị di động.
Nhóm thiết kế template email chứa đường dẫn đến ảnh thương hiệu; người nhận mở thư offline nên ảnh từ server ngoài không hiển thị và thông tin hóa đơn bị thiếu.
Ứng dụng gắn ảnh logo nội tuyến bằng content ID; template tham chiếu ID khác phần MIME đã thêm khiến logo hiện biểu tượng ảnh vỡ.
Đội gửi email marketing với các ảnh inline và tệp PDF; khi thêm phần theo thứ tự khác, một số client coi ảnh nội tuyến thành attachment tải xuống.
Nhóm dùng MimeMessageHelper để gửi HTML và bản text riêng; một trường giảm giá chỉ được cập nhật trong HTML khiến hai nhóm người dùng đọc thông tin khác nhau.
Ứng dụng xác nhận thanh toán gửi thư HTML với màu chữ nhạt; client bật dark mode tự đổi màu nền và thông tin giao dịch trở nên khó đọc.
Đội thử render template trong trình duyệt trước khi gửi; các CSS và font được client email hỗ trợ hạn chế nên nội dung nhận được khác bản xem trước.
Một hệ thống thông báo dùng biểu thức template để chèn tên khách; tên chứa dấu nhỏ hơn và ký tự HTML khiến thư hiển thị sai hoặc có nội dung ngoài dự kiến.
Nhóm đưa ghi chú đơn hàng từ người dùng vào HTML email; dữ liệu không tin cậy được đưa trực tiếp vào markup làm template không còn an toàn khi hiển thị.
Ứng dụng sử dụng Thymeleaf template cho mail xác nhận; view resolver lấy nhầm template từ thư mục web và gửi nội dung dành cho giao diện trình duyệt.
Đội biên tập cập nhật tên biến trong template hóa đơn; Java service vẫn cung cấp tên biến cũ nên nhiều thư gửi thành công nhưng có chỗ trống.
Một hệ thống dùng FreeMarker template trong worker gửi mail; bản production thiếu resource template dù unit test chạy đúng trên classpath máy phát triển.
Nhóm tạo template email đa ngôn ngữ từ message bundle; một locale mới thiếu key khiến thư lẫn tiếng Việt và tiếng Anh ở phần quan trọng.
Ứng dụng render template hóa đơn ngay trước khi gửi; bảng giá vừa cập nhật trong database nên số tiền trong mail khác số tiền đã thanh toán tại thời điểm chốt đơn.
Đội gửi nội dung HTML có đường dẫn đổi mật khẩu; cách encode tham số URL không phù hợp khiến token chứa ký tự đặc biệt không mở được khi khách bấm.
Một dịch vụ phát thư có nút hành động ở nhiều nơi; link ở bản text và bản HTML trỏ tới hai môi trường khác nhau sau khi đổi tên miền production.
Nhóm chèn thời điểm giao hàng vào template theo múi giờ của máy chủ; khách ở vùng khác nhận giờ hẹn sai với giao diện đặt hàng.
Ứng dụng dùng template cache để giảm CPU; bản template đã chỉnh sửa không được áp dụng ở một số replica khiến khách nhận nội dung cũ.
Đội marketing cho phép sửa template tại CMS; template có biểu thức gọi bean hoặc method ngoài phạm vi hiển thị và tạo rủi ro khi render trên server.
Một hệ thống dùng QR code nội tuyến trong email; ảnh được tạo dưới định dạng không tương thích content type khai báo khiến nhiều client không đọc được QR.
Nhóm tạo mail có cả bản HTML và plain text từ hai nguồn dữ liệu; khi dịch vụ tính thuế tạm lỗi, hai phần nội dung có tổng thanh toán khác nhau.
Ứng dụng xuất bảng điểm thành email HTML dài; một nhà cung cấp cắt bớt nội dung vượt giới hạn hiển thị làm học viên không thấy điểm cuối kỳ.
Đội viết CSS responsive trong template nhưng chưa kiểm tra trên Outlook; các cột hóa đơn bị lệch và số tiền không thẳng với sản phẩm tương ứng.
Một hệ thống thông báo yêu cầu accessibility cho người khiếm thị; email chỉ chứa ảnh thông tin giao dịch mà không có mô tả thay thế dễ hiểu.
Nhóm dùng nội dung email theo giới tính và danh xưng trong hồ sơ; một thuộc tính không có giá trị làm template hiển thị lời chào không phù hợp với người nhận.
Ứng dụng tạo MIME message bằng Jakarta Mail trực tiếp; đội phát triển vô tình đặt charset khác cho subject và body khiến chỉ một phần thư hiển thị sai dấu.
Một dịch vụ đính kèm hóa đơn PDF qua MimeMessageHelper; file đã được xóa bởi job dọn rác trước lúc gửi khiến việc tạo message thất bại sau khi đơn đã hoàn tất.
Nhóm đính kèm ảnh sản phẩm từ InputStreamSource; cùng stream được đọc nhiều lần trong lúc JavaMailSender xử lý khiến attachment của một số thư rỗng.
Ứng dụng tạo file CSV trong bộ nhớ rồi gửi qua attachment; khi danh sách đơn lên hàng triệu dòng, heap tăng mạnh trước khi gửi mail.
Đội gửi báo cáo zip cỡ lớn qua SMTP; máy chủ nhận giới hạn kích thước message và từ chối sau khi app đã mất thời gian tạo file.
Một hệ thống tạo PDF 18 MB và cho rằng dưới mức gửi 20 MB; mã hóa MIME/Base64 làm kích thước truyền vượt hạn mức relay.
Nhóm gửi nhiều attachment cùng tên report.pdf cho từng vùng; khách nhận thư thấy các tệp trùng tên và khó phân biệt dữ liệu của từng bộ phận.
Ứng dụng gửi bản sao hợp đồng Word có tên file tiếng Việt; một số client hiển thị filename bị lỗi vì cách encode MIME header không tương thích.
Đội lấy attachment filename từ request người dùng; tên chứa ký tự xuống dòng hoặc đường dẫn không phù hợp dẫn tới header MIME bất thường.
Một dịch vụ gửi email tài liệu nhạy cảm đọc tệp trên ổ đĩa tạm; tác vụ nền chạy sau khi request dọn thư mục nên attachment không còn tồn tại.
Nhóm tạo attachment bằng ByteArrayResource từ một ảnh lớn; hàng trăm email đồng thời giữ bản sao dữ liệu trong heap và pod bị OOM.
Ứng dụng gửi hóa đơn có file PDF theo orderId; một tác vụ retry sử dụng cùng đường dẫn khi file đã bị thay thế và khách nhận hóa đơn của lần thanh toán khác.
Đội gửi nhiều hóa đơn trong một MIME message; một attachment bị thiếu nhưng thư vẫn có các tệp còn lại và trạng thái nghiệp vụ đang báo tất cả đã đầy đủ.
Nhóm dùng MimeMessageHelper addAttachment với content type không đúng; phần mềm email tải file về nhưng không mở bằng ứng dụng tương ứng.
Ứng dụng gửi file Excel chứa dữ liệu cá nhân cho quản lý; danh sách người nhận được lấy từ cache quyền cũ nên báo cáo đi tới người đã chuyển bộ phận.
Đội phát triển quét virus cho attachment sau khi đã đưa tác vụ gửi vào queue; thư có thể được gửi trước khi kết quả quét an toàn hoàn tất.
Một hệ thống tự tạo tài liệu theo tenant rồi gửi email; job dùng đường dẫn lưu trữ chung khiến tài liệu của tenant A có thể bị đính kèm vào thư tenant B.
Nhóm gửi hình ảnh inline từ URL ngoài trong lúc render; nguồn ảnh trả chậm khiến thread tạo MIME message giữ tài nguyên quá thời hạn request.
Ứng dụng dùng MimeMessageHelper với multipart mode không phù hợp cho cả ảnh inline và PDF; nội dung mở đúng trên một mail client nhưng sai bố cục trên client khác.
Đội thử thêm attachment sau khi message đã được chuyển sang dạng kết thúc; thao tác sửa cấu trúc multipart làm thư gửi đi khác preview đã phê duyệt.
Một dịch vụ in hóa đơn qua email dùng tên file ghép mã khách; mã chứa ký tự không hợp lệ trên hệ điều hành làm bước tạo file tạm thất bại ở một pod.
Nhóm dùng template email kèm biểu đồ PNG tạo bởi thư viện đồ họa; service gửi lại dùng image CID cũ không có trong bản MIME mới.
Ứng dụng lập báo cáo đính kèm bản dữ liệu được nén; bộ phận nhận thư chỉ thấy tệp bị chặn vì chính sách lọc loại attachment của nhà cung cấp.
Đội quản lý tài liệu gửi cùng file đính kèm đến 300 người; việc tái sử dụng một MimeMessage mutable giữa các request khiến một số người nhận thêm nội dung không đúng.
Một hệ thống lưu bản copy email đã gửi gồm attachment lớn vào database; dung lượng lưu trữ tăng đột biến và thao tác truy vấn lịch sử bị chậm.
Nhóm phát hiện cần ghi dấu hash attachment để audit; các lần retry được tạo file lại với nội dung biến đổi nên khó xác định khách đã nhận phiên bản nào.
Ứng dụng cấu hình JavaMailSenderImpl tới SMTP port 587; nhóm bật SSL ngay từ đầu thay vì cơ chế thương lượng thích hợp nên kết nối không thực hiện được.
Đội triển khai máy chủ SMTPS trên port 465 nhưng client được cấu hình STARTTLS như port submission; quá trình bắt tay không diễn ra và mọi email bị timeout.
Một dịch vụ hoạt động ở môi trường dev qua SMTP không mã hóa; khi chuyển production relay bắt buộc TLS, kết nối thất bại trong khi tài khoản và password vẫn đúng.
Nhóm cấu hình thuộc tính mail.smtp.starttls.enable cho JavaMailSenderImpl; relay hỗ trợ nhưng không bắt buộc TLS và thư có thể gửi qua kết nối không đáp ứng chính sách nội bộ.
Ứng dụng kết nối relay yêu cầu STARTTLS nhưng thiết lập certificate hostname không khớp miền cấu hình; bản staging bỏ qua kiểm tra nên chỉ production thất bại.
Đội bảo mật thay CA cho SMTP relay; các node chạy JDK truststore cũ không thiết lập được TLS và một phần email bị tồn trong queue.
Một hệ thống email dùng TLS 1.2 theo cấu hình cũ; sau khi relay yêu cầu giao thức mới, một nhóm JVM không thể thương lượng phiên mã hóa phù hợp.
Nhóm kết nối SMTP qua load balancer; một node relay có chứng chỉ hết hạn làm tỷ lệ gửi thư thất bại ngẫu nhiên theo backend được chọn.
Ứng dụng dùng host SMTP trỏ tới IP cố định; nhà cung cấp đổi địa chỉ và kết nối đứt dù bản ghi DNS đã cập nhật đúng.
Đội cấu hình JavaMailSender dùng hostname trong vùng mạng chỉ truy cập từ staging; production bị network policy chặn port outbound và mọi yêu cầu gửi timeout.
Nhóm nhập sai cổng SMTP trong cấu hình; kết nối tới dịch vụ khác trên cùng máy và đội hỗ trợ nhầm lỗi bắt tay giao thức thành lỗi mật khẩu.
Ứng dụng dùng SMTP AUTH với username đăng nhập khác địa chỉ From; sau khi nhà cung cấp cập nhật chính sách gửi thay mặt, máy chủ từ chối thư dù xác thực thành công.
Đội xoay vòng SMTP password trong Kubernetes Secret; các pod giữ cấu hình cũ đến khi restart khiến một phần thư gửi được và phần còn lại báo 535 authentication failed.
Một hệ thống sử dụng OAuth2 token cho relay; token hết hạn khi job gửi lâu và cơ chế làm mới không hoạt động ở các worker nền.
Nhóm cấu hình thông tin SMTP trực tiếp trong application.properties được commit; một nhân viên không thuộc nhóm vận hành có thể xem credential production.
Ứng dụng đặt thời gian connection timeout rất dài; khi relay ngừng, hàng trăm HTTP request bị chặn chờ socket và hết worker.
Đội đặt mail.smtp.timeout ngắn nhưng không đặt thời gian thiết lập kết nối; một lỗi DNS hoặc bắt tay TCP vẫn giữ request lâu hơn SLA.
Nhóm cấu hình mail.smtp.writetimeout không đồng nhất với thời gian gửi attachment lớn; truyền thư bị cắt giữa chừng và trạng thái cuối không xác định.
Ứng dụng sử dụng JavaMailSenderImpl với session cấu hình riêng; các thuộc tính timeout và TLS được đặt trong một JavaMail Session khác nên không có hiệu lực thực tế.
Đội chỉnh sửa JavaMailSenderImpl host và port trong runtime khi có hai relay; nhiều thread đang gửi dùng chung sender mutable và kết nối tới máy chủ không mong muốn.
Nhóm dùng một JavaMailSender bean chung cho nhiều tenant có SMTP credentials riêng; request đồng thời thay username/password trên cùng object làm thư đi bằng tài khoản của tenant khác.
Ứng dụng kiểm tra JavaMailSender.testConnection khi startup; database chưa có tác vụ gửi nào nhưng ứng dụng không ready vì relay tạm thời bảo trì.
Đội vận hành coi kết quả testConnection thành bảo đảm gửi thư được; relay vẫn chặn địa chỉ From hay người nhận cụ thể tại thời điểm SMTP transaction.
Một hệ thống gửi thư qua SMTP relay nội bộ có giới hạn 20 kết nối; ứng dụng tăng số worker gửi bất đồng bộ và bị từ chối do vượt connection concurrency.
Nhóm retry đăng nhập SMTP sau lỗi xác thực cố định; tài khoản bị nhà cung cấp khóa vì quá nhiều lần đăng nhập thất bại.
Ứng dụng cố gửi tới địa chỉ ngoài miền được cho phép trên SMTP nội bộ; relay trả lỗi không cho chuyển tiếp dù kết nối và TLS đều thành công.
Đội sử dụng SMTP service chỉ chấp nhận thư từ địa chỉ IP đã whitelist; sau khi rollout Kubernetes NAT thay đổi, các node mới bị từ chối còn node cũ vẫn gửi được.
Nhóm gửi thư thương hiệu từ domain chưa thiết lập SPF phù hợp; nhiều bên nhận phân loại spam dù SMTP relay đã chấp nhận message.
Ứng dụng sử dụng From domain không tương ứng cấu hình DKIM của nhà cung cấp; những email giao dịch bị hệ thống nhận đánh dấu nghi ngờ hoặc đưa vào mục rác.
Đội bảo mật nâng chính sách DMARC lên mức nghiêm ngặt; các mail gửi qua nhà cung cấp thứ hai không còn vượt kiểm tra alignment và tỷ lệ giao thư giảm.
Một dịch vụ gửi mail sau thay đổi DNS MX hoặc routing của khách; relay chấp nhận thư nhưng việc chuyển tới server đích bị trễ hoặc trả bounce.
Nhóm đổi email trả lời sang domain chưa được xác minh; thư phản hồi của khách không đến hệ thống hỗ trợ dù thông báo gốc được gửi thành công.
Ứng dụng ghi log đầy đủ SMTP protocol để chẩn đoán; thông tin recipient, subject và token reset password có nguy cơ xuất hiện ở hệ thống log tập trung.
Đội bật JavaMail debug ở production trong thời gian dài; log lớn làm ổ đĩa đầy và thông tin giao dịch bị lộ cho nhóm không có quyền đọc.
Nhóm gửi thư định kỳ tới khách chưa xác nhận opt-in; tỷ lệ complaint tăng làm uy tín domain giảm và ảnh hưởng email xác thực quan trọng.
Ứng dụng dùng cùng một địa chỉ From cho cả thông báo tài khoản và chiến dịch marketing; nhà cung cấp hạn chế traffic marketing khiến thư bảo mật bị trễ theo.
Đội vận hành không theo dõi rate limit SMTP theo tài khoản; job gửi thư tháng mới bắt đầu liền bị 421 tạm hoãn do vượt quota trong ngày.
Nhóm lọc địa chỉ hỏng dựa trên lỗi SMTP đầu tiên; một số domain nhận mọi địa chỉ ở bước SMTP rồi gửi bounce sau nên danh sách vẫn chứa nhiều email không tồn tại.
Ứng dụng chứa link token xác nhận không có hạn dùng; người nhận chuyển tiếp email nhiều tháng sau và liên kết cũ vẫn có hiệu lực ngoài yêu cầu bảo mật.
Đội gửi mã OTP qua email và dùng lại mã khi request mới được tạo; các thư đến trễ có cùng mã hoặc mã cũ khiến người dùng khó xác định mã còn hợp lệ.
Một dịch vụ gửi email khôi phục tài khoản với thông tin người dùng trong subject; subject được chuyển tiếp qua nhiều server và tạo rủi ro tiết lộ dữ liệu cá nhân.
Nhóm quản trị tạo footer và link hủy đăng ký cho thư marketing; một template thiếu link ở bản plain text khiến hành vi client và chính sách nội bộ không thống nhất.
Ứng dụng lưu địa chỉ email và nội dung thông báo vô thời hạn để retry; chính sách xóa thông tin khách hàng chưa được áp lên các bảng chờ gửi.
Đội hỗ trợ cần xác định thư nào đã được gửi cho khách; hệ thống ghi mỗi email dưới một userId nhưng không có messageId hoặc correlation ID để truy nguyên.
Nhóm cho phép người dùng nhập Reply-To tùy ý; địa chỉ có cú pháp bất thường làm MIME header không hợp lệ hoặc gửi phản hồi sang miền không được phê duyệt.
Ứng dụng xử lý unsubscribe bằng cách tắt toàn bộ email khách; thư bảo mật xác nhận đăng nhập cũng bị dừng dù có tính chất khác email marketing.
Một nền tảng y tế gửi thông báo có attachment thông tin riêng tư; email người nhận được cập nhật sau khi job tạo nhưng trước khi gửi nên dữ liệu đi tới địa chỉ cũ.
Đội phát triển đưa địa chỉ Bcc của quản trị viên vào log lỗi gửi; email nội bộ của nhóm vận hành bị hiển thị cho những người chỉ được quyền xem incident.
Nhóm cấu hình danh sách người nhận từ tenant settings; quyền xác thực tenant ở endpoint gửi không đủ chặt khiến yêu cầu của tenant A dùng danh sách của tenant B.
Ứng dụng gửi email ngay bên trong @Transactional tạo đơn; SMTP đã chấp nhận thư nhưng transaction bị rollback và khách nhận thông báo về đơn không tồn tại.
Đội đặt lời gọi JavaMailSender.send trước khi commit thanh toán; người dùng nhận email thành công dù bước cập nhật số dư sau đó vi phạm constraint.
Nhóm chuyển gửi email sang @TransactionalEventListener(AFTER_COMMIT); khi luồng gọi không có transaction, listener mặc định không chạy và khách không nhận thư.
Ứng dụng gửi mail từ listener AFTER_COMMIT rồi ghi đánh dấu đã gửi vào database; thao tác ghi thêm không có transaction mới và trạng thái lưu khác kết quả gửi thực tế.
Đội triển khai @Async cho listener gửi thư; controller trả 200 trước khi worker bắt đầu, nhưng sản phẩm lại báo email đã được gửi thành công.
Một hệ thống tuyển dụng gửi hàng nghìn thư trong ThreadPoolTaskExecutor; queue không giới hạn phình to trong đợt SMTP downtime và service bị cạn heap.
Nhóm cấu hình maxPoolSize lớn cho email worker; SMTP relay có giới hạn kết nối nhỏ khiến phần lớn task nhận lỗi quá tải thay vì gửi nhanh hơn.
Ứng dụng dùng executor chung cho gửi email và job thanh toán; attachment lớn làm pool nghẽn và tác vụ tài chính quan trọng bị trễ.
Đội bật CallerRunsPolicy cho executor gửi mail; khi queue đầy, request đăng ký tài khoản thực hiện SMTP đồng bộ và thời gian phản hồi tăng mạnh.
Nhóm dùng DiscardPolicy khi queue email quá tải; hệ thống vẫn ghi yêu cầu gửi đã tiếp nhận trong khi một số thư không được thực hiện.
Ứng dụng gửi email từ @Async method trả void; exception SMTP xảy ra trong worker nhưng request gốc không có thông tin để hiển thị hoặc phục hồi.
Đội phát triển dùng CompletableFuture cho gửi email nhưng không theo dõi kết quả; các lỗi SMTP được lưu trong future mà không có log hoặc cảnh báo tương ứng.
Một hệ thống báo cáo gọi JavaMailSender.send trong CompletableFuture rồi gọi join ngay trên request; endpoint vẫn chờ hết thời gian SMTP dù nhóm kỳ vọng phản hồi tức thì.
Nhóm đặt timeout cho CompletableFuture gửi thư; future hoàn tất với lỗi timeout nhưng socket SMTP bên dưới vẫn có thể tiếp tục truyền message.
Ứng dụng dùng cancel(true) để hủy tác vụ email khi client đóng kết nối; thư đã được relay chấp nhận nhưng hệ thống ghi nhận bị hủy và người dùng yêu cầu gửi lại.
Đội triển khai scheduled task quét email chưa gửi trong database; nhiều replica cùng chọn một record và tạo hai thư cho cùng một giao dịch.
Nhóm dùng @Scheduled để phát các thư nhắc thanh toán; hai pod cùng chạy lịch lúc nửa đêm và khách nhận thông báo lặp.
Ứng dụng lưu trạng thái email pending trong RAM trước khi submit; khi pod nhận SIGTERM, các yêu cầu còn trong queue mất nhưng database vẫn ghi giao dịch đã tạo.
Đội triển khai graceful shutdown cho mail executor; terminationGracePeriodSeconds ngắn hơn thời gian truyền MIME lớn khiến một số thư ở trạng thái không xác định.
Nhóm lưu event email vào outbox cùng transaction tạo hóa đơn; worker gửi thành công rồi crash trước khi đánh dấu outbox đã hoàn tất và phát lại một thư trùng.
Ứng dụng áp dụng idempotency theo message ID nhưng lại tạo ID mới mỗi lần retry email; khách nhận hai bản xác nhận và hệ thống hỗ trợ không thể đối chiếu đó là cùng yêu cầu.
Đội phát triển retry mọi MailException với cùng chính sách; lỗi SMTP 535 do credentials sai vẫn bị thử liên tục và làm tài khoản bị khóa.
Nhóm thử lại ngay khi relay trả lỗi 421 tạm thời; hàng nghìn job cùng retry tạo làn sóng quá tải lặp lại khi SMTP hồi phục.
Ứng dụng coi MailSendException là chắc chắn chưa gửi; kết nối mất sau lệnh dữ liệu khiến relay có thể đã nhận thư và lần retry tạo bản thứ hai.
Đội phân biệt lỗi recipient vĩnh viễn và lỗi server tạm thời chưa đầy đủ; các địa chỉ không tồn tại vẫn bị retry nhiều ngày còn thư lỗi mạng bị bỏ.
Nhóm dùng exponential backoff để gửi lại; một bản ghi bị lỗi liên tục chiếm worker và làm những thư mới đúng hạn không có cơ hội xử lý.
Ứng dụng có giới hạn số lần thử và chuyển thư vào danh sách failed; dashboard chỉ nhìn queue pending nên bộ phận CSKH không biết có thư cần xử lý thủ công.
Đội phát triển retry từ bản nội dung được render lại; giá sản phẩm và địa chỉ nhận đã thay đổi giữa hai lần khiến thư thứ hai không giống bản đầu.
Nhóm tạo một thư batch nhiều người nhận trong cùng SMTP transaction; một số địa chỉ bị từ chối ở giai đoạn RCPT và trạng thái từng người nhận không được lưu riêng.
Ứng dụng nhận MailSendException với danh sách message lỗi; logic ghi trạng thái đánh dấu toàn batch failed dù một số MimeMessage đã được gửi thành công.
Đội vận hành chỉ đếm số lần gọi JavaMailSender.send không ném exception; số liệu được báo là đã giao thư trong khi đó mới phản ánh chặng giao nhận SMTP của ứng dụng.
Một email được relay trả 250 accepted sau DATA; vài phút sau máy chủ đích gửi bounce do hộp thư người nhận đầy và dashboard vẫn đánh dấu delivered.
Nhóm hỗ trợ giải thích SMTP accepted là thư đã vào inbox; khách không thấy email vì thư vào spam hoặc bị bộ lọc phía nhận giữ lại.
Ứng dụng ghi nhận success ngay sau khi relay nhận message; email đến chậm hàng giờ do queue của nhà cung cấp mà SLA gửi thư chưa tách chấp nhận với giao thực.
Đội vận hành nhận webhook delivered từ email provider nhưng không gắn được với message được gửi qua SMTP; trạng thái từng giao dịch vẫn không biết thư đã đến hay chưa.
Nhóm xử lý bounce qua một mailbox riêng; thông báo trả về không có khóa đối chiếu ổn định nên không xác định được khách và loại email bị từ chối.
Ứng dụng chỉ theo dõi hard bounce mà bỏ qua soft bounce; người dùng có mailbox đầy nhiều ngày vẫn liên tục nhận lượt gửi thử mới.
Đội tích hợp nhận thông báo complaint từ nhà cung cấp; hệ thống không cập nhật suppression list và tiếp tục gửi email gây ảnh hưởng uy tín miền.
Nhóm gửi OTP rồi tính thời gian hiệu lực từ lúc nhấn nút; SMTP queue bị chậm khiến OTP đến sau khi đã hết hạn và khách liên tục yêu cầu gửi lại.
Ứng dụng phân biệt sent, accepted, delivered và bounced trong mô hình dữ liệu chưa rõ; cùng một email chuyển trạng thái ngược khi webhook đến không theo thứ tự.
Đội xây dashboard số mail delivered dựa trên log HTTP của endpoint gửi; các message không được relay chấp nhận vẫn được tính vào báo cáo giao thành công.
Nhóm dùng SMTP relay không cung cấp webhook trạng thái giao cuối; sản phẩm muốn hiển thị chắc chắn khách đã đọc email nhưng hệ thống không có bằng chứng tương ứng.
Ứng dụng nhận provider event delivered rồi tiếp tục nhận deferred sau đó; việc cập nhật trạng thái thiếu thứ tự thời gian khiến báo cáo cuối ngày sai lệch.
Đội xây báo cáo thời gian gửi trung bình chỉ đo đến 250 accepted; người dùng than email đến chậm nhưng metric SMTP của ứng dụng vẫn tốt.
Nhóm đổi DNS và DKIM của miền gửi; tỷ lệ accepted không đổi trong khi open rate và spam complaint xấu đi, báo hiệu vấn đề phía nhận.
Ứng dụng retry email khi không nhận open tracking pixel; khách tắt tải ảnh nên thư đã được giao vẫn bị gửi lặp ngoài ý muốn.
Đội đánh dấu delivered theo sự kiện click vào liên kết; thư thông báo không có link nên trạng thái giao thư của phân khúc đó không bao giờ cập nhật.
Nhóm tiếp nhận bounce sau nhiều ngày từ một nhà cung cấp; bản ghi email đã bị xóa theo TTL nên event không còn đối tượng đối chiếu.
Ứng dụng gửi thư marketing quy mô lớn qua một tài khoản SMTP; nhà cung cấp điều tiết lưu lượng làm thư xác nhận giao dịch dùng cùng tài khoản bị trì hoãn.
Đội cấu hình cảnh báo chỉ dựa trên exceptions; relay vẫn trả accepted nhưng tỷ lệ bounce tăng mạnh mà hệ thống không phát cảnh báo.
Nhóm đo số lượng retry theo mã SMTP lỗi; log mất enhanced status code nên không phân biệt nguyên nhân hạ tầng, quota hay địa chỉ không hợp lệ.
Ứng dụng chạy gửi mail ở nhiều region; cùng lỗi được ghi theo múi giờ khác nhau khiến việc đối chiếu thứ tự gửi và bounce khó thực hiện.
Đội phát triển unit test MailSender bằng mock; thử nghiệm chỉ xác minh method send được gọi mà không kiểm địa chỉ, subject, charset và nội dung thật.
Nhóm kiểm thử MimeMessageHelper chỉ bằng một mail client; email có HTML, ảnh inline và attachment đúng ở Gmail nhưng bị tách phần MIME sai trên client khác.
Ứng dụng dùng GreenMail trong integration test JavaMailSender; bộ test chưa kiểm cấu hình TLS và SMTP AUTH giống production nên lỗi bắt tay không được phát hiện.
Đội kiểm thử bằng MailHog bắt SMTP local; cấu hình relay staging yêu cầu chính sách domain và rate limit khác nên thử nghiệm thành công không phản ánh deployment thật.
Nhóm tạo fake SMTP server chỉ trả 250 cho mọi lệnh; test không mô phỏng lỗi 4xx/5xx và luồng retry trên production chưa được kiểm chứng.
Ứng dụng có testcase gửi email HTML với tên tiếng Anh; trường hợp tên khách và filename có dấu tiếng Việt không được đưa vào test nên lỗi encoding chỉ xuất hiện sau release.
Đội kiểm thử thư có attachment PDF rất nhỏ; file production vượt giới hạn SMTP sau mã hóa và toàn bộ batch báo cáo bị từ chối.
Nhóm dùng @SpringBootTest với SMTP credentials test nhưng bean JavaMailSenderImpl vẫn lấy host production từ biến môi trường; một bài test vô tình gửi thư tới khách thật.
Ứng dụng test listener @Async bằng cách gọi method trực tiếp; bài kiểm thử không phản ánh executor, timeout và thời điểm exception được ghi trong production.
Đội kiểm thử @TransactionalEventListener bằng transaction mặc định rollback; listener AFTER_COMMIT không chạy nên bộ test kết luận sai rằng mail sender bị hỏng.
Nhóm QA gọi gửi email rồi assert ngay số bản ghi audit; worker async chưa hoàn thành và test flaky theo tốc độ máy CI.
Ứng dụng có test retry trên lỗi socket được mock trước khi gửi; tình huống relay chấp nhận thư rồi mất connection không được mô phỏng và duplicate không bị phát hiện.
Đội triển khai test tải với 20 email; production phát 20.000 email cùng lúc nên giới hạn concurrency và memory MIME chỉ lộ ở giờ cao điểm.
Nhóm viết test dữ liệu người nhận có nhiều địa chỉ; test không kiểm Bcc và quyền tenant nên không phát hiện email nhạy cảm gửi sang danh sách không liên quan.
Ứng dụng giả lập lỗi DNS trong kiểm thử nhưng không giả lập relay trả mã 535; cấu hình credential sai khiến hệ thống retry vô hạn khi release.
Đội tích hợp webhook bounce với provider qua test có event đúng thứ tự; production giao event trùng hoặc đến muộn làm trạng thái gửi bị ghi đè.
Nhóm kiểm thử email được render bằng HTML đơn giản; template thực tế có inline image, link có token và CSS nên nội dung hỏng chỉ xuất hiện trên một số client.
Ứng dụng nâng Spring Framework và Jakarta Mail cùng lúc; code tạo MimeMessage cũ vẫn biên dịch ở một module nhưng production thiếu class hoặc provider tương thích.
Đội vận hành rollback cấu hình SMTP sau khi chuyển nhà cung cấp; các thư pending vẫn giữ From domain của relay mới và bị relay cũ từ chối.
Nhóm có một bean JavaMailSenderImpl dùng chung với các service notification; thay đổi global timeout cho chức năng gửi báo cáo làm OTP bị timeout nhiều hơn.
Ứng dụng cập nhật cấu hình giới hạn kích thước attachment nhưng queue còn mail được tạo trước đó; một số bản ghi pending vẫn lớn hơn mức relay mới cho phép.
Đội vận hành thêm tracing xuyên suốt tạo hóa đơn, render template và gửi SMTP; khi tác vụ chuyển sang @Async, trace context không được truyền và không thể tìm nguyên nhân delay.
Nhóm tạo correlation ID cho từng yêu cầu gửi nhưng không liên kết với provider message ID; sau khi nhận bounce, bộ phận hỗ trợ không tìm ra đơn hàng gốc.
Ứng dụng lưu trạng thái gửi theo email address thay vì message ID; hai thông báo khác nhau cho cùng khách ghi đè lịch sử lỗi của nhau.
Đội thay đổi retention của bảng mail queue để tiết kiệm dung lượng; email lỗi bị xóa trước khi support có thể kiểm tra hoặc cho phát lại.
Nhóm bật health indicator kiểm kết nối SMTP trực tiếp; relay bảo trì ngắn khiến toàn bộ service báo không ready dù API đọc dữ liệu vẫn phục vụ được.
Ứng dụng khởi chạy hàng trăm mail worker sau deploy; SMTP relay phục hồi sau outage và bị quá tải ngay do các tác vụ chờ đồng loạt kết nối.
Đội áp quota gửi email theo tenant nhưng đếm từng batch là một thư; tenant gửi batch hàng nghìn người vẫn vượt giới hạn mà hệ thống không ngăn được.
Nhóm lập lịch gửi email nhắc lịch khám theo timezone từng khách; cron chạy ở UTC làm thông báo đến lúc đêm khuya đối với một số khu vực.
Ứng dụng tạo email từ sự kiện OrderPaid trong cả controller và event listener; khách nhận hai thư xác nhận dù transaction chỉ thanh toán một lần.
Đội bảo trì thay template email mà không có version gắn với outbox; khi retry sau lỗi hạ tầng, khách nhận thư mang nội dung chính sách mới cho một giao dịch cũ.
Nhóm muốn đối soát số email đã giao theo ngày; dữ liệu SMTP accepted, provider delivered và người dùng open được trộn thành một chỉ số nên báo cáo không thể kiểm toán.
