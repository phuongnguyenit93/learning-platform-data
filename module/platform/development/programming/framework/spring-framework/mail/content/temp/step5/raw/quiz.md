Câu 01. Trong Spring Mail, interface nào trực tiếp khai báo thao tác `send(SimpleMailMessage...)`?
A. `MimeMessageHelper` định nghĩa API gửi thư văn bản
B. `MimeMessagePreparator` định nghĩa API gửi thư văn bản
C. `MailSender` định nghĩa API gửi thư văn bản đơn giản
D. `MailMessage` định nghĩa API gửi thư văn bản đơn giản
Đáp án đúng: C

Câu 02. Để tạo email văn bản thuần với `SimpleMailMessage`, bộ lệnh nào phù hợp?
A. Gọi `addInline`, `setEncoding` và `setMultipart` trên message
B. Gọi `setTo`, `setSubject` và `setText` trên message
C. Gọi `addTo`, `setHtml` và `addAttachment` trên message
D. Gọi `setRecipient`, `setBody` và `setMimeType` trên message
Đáp án đúng: B

Câu 03. Khi chuẩn bị email MIME trong Spring, method nào tạo `MimeMessage` mới?
A. `JavaMailSender.createMimeMessage()` tạo MIME message mới
B. `MailSender.createMimeMessage()` trả Jakarta MIME message
C. `MimeMessageHelper.createMimeMessage()` tạo Jakarta message
D. `SimpleMailMessage.createMimeMessage()` tạo Jakarta message
Đáp án đúng: A

Câu 04. Implementation Spring Mail nào thường thiết lập máy chủ SMTP và gửi qua Jakarta Mail?
A. `MimeMessageHelper` dùng cấu hình host/port để gửi thư
B. `MailMessage` dùng cấu hình host/port để gửi thư
C. `SimpleMailMessage` dùng cấu hình host/port để gửi thư
D. `JavaMailSenderImpl` cấu hình host/port và gửi SMTP
Đáp án đúng: D

Câu 05. Với `MimeMessageHelper`, thao tác nào đánh dấu nội dung là HTML?
A. Chọn `helper.addInline(html, true)` khi soạn body
B. Chọn `helper.setText(html, false)` khi soạn body
C. Chọn `helper.setText(html, true)` khi soạn body
D. Chọn `helper.setSubject(html, true)` khi soạn body
Đáp án đúng: C

Câu 06. Khi email cần cả text thuần và bản HTML thay thế, gọi API nào?
A. `helper.setText(htmlText, true)` tạo hai bản body
B. `helper.addAttachment(plainText, htmlText)` tạo hai bản
C. `helper.setText(plainText, htmlText)` tạo hai bản body
D. `helper.addInline(plainText, htmlText)` tạo hai bản body
Đáp án đúng: C

Câu 07. Constructor nào của `MimeMessageHelper` cho phép multipart và chỉ định UTF-8?
A. `new MimeMessageHelper(message, true, "ASCII")`
B. `new MimeMessageHelper(message, false, "ASCII")`
C. `new MimeMessageHelper(message, false, "UTF-8")`
D. `new MimeMessageHelper(message, true, "UTF-8")`
Đáp án đúng: D

Câu 08. Để gửi file PDF như một attachment, method helper nào phù hợp?
A. `helper.addAttachment("report.pdf", resource)` thêm PDF
B. `helper.setReplyTo("report.pdf", resource)` gắn tệp
C. `helper.addInline("report.pdf", resource)` gắn tệp
D. `helper.setText("report.pdf", resource)` gắn tệp
Đáp án đúng: A

Câu 09. Khi muốn ảnh logo hiển thị bên trong HTML email theo Content-ID, API nào phù hợp?
A. `helper.addAttachment("logo", resource)` tạo nội dung inline
B. `helper.addInline("logo", resource)` thêm nội dung inline
C. `helper.setFrom("logo", resource)` thêm nội dung inline
D. `helper.setTo("logo", resource)` thêm nội dung inline
Đáp án đúng: B

Câu 10. Để HTML email tham chiếu ảnh đã gắn Content-ID `logo`, dùng gì trong thuộc tính `src`?
A. Giá trị `http:logo` khớp Content-ID của phần inline
B. Giá trị `classpath:logo` khớp Content-ID phần inline
C. Giá trị `file:logo` khớp Content-ID của phần inline
D. Giá trị `cid:logo` khớp Content-ID của phần inline
Đáp án đúng: D

Câu 11. Với `MimeMessageHelper.addInline`, thứ tự thao tác nào thường được khuyến nghị?
A. Gọi `saveChanges` trước `setText` để cấu trúc MIME đúng
B. Gọi `addInline` trước `setText` để cấu trúc MIME đúng
C. Gọi `send` trước `addInline` để cấu trúc MIME đúng
D. Gọi `setText` trước `addInline` để cấu trúc MIME đúng
Đáp án đúng: D

Câu 12. Với `JavaMailSender.send(MimeMessagePreparator)`, callback cần triển khai method nào?
A. `createMimeMessage(MimeMessage)` thiết lập nội dung
B. `prepare(MimeMessage)` thiết lập nội dung lên message
C. `afterPropertiesSet(MimeMessage)` thiết lập nội dung
D. `send(MimeMessage)` thiết lập nội dung cho message
Đáp án đúng: B

Câu 13. Khi bắt lỗi mail tổng quát của Spring, kiểu exception gốc phù hợp là gì?
A. `IOException` là exception unchecked của Spring Mail
B. `MailException` là exception unchecked của Spring Mail
C. `ParseException` là exception unchecked Spring Mail
D. `MessagingException` là exception unchecked Spring Mail
Đáp án đúng: B

Câu 14. Đăng nhập SMTP bị máy chủ từ chối, subtype Spring Mail nào liên quan nhất?
A. `MailAuthenticationException` biểu thị sự cố xác thực
B. `MailParseException` biểu thị sự cố xác thực
C. `MailPreparationException` biểu thị sự cố xác thực
D. `MailSendException` biểu thị sự cố soạn định dạng
Đáp án đúng: A

Câu 15. Máy chủ SMTP không thể nhận thư trong quá trình gửi, exception Spring Mail nào đáng kiểm tra?
A. `MailPreparationException` phản ánh vấn đề kết nối
B. `MailAuthenticationException` phản ánh lỗi soạn MIME
C. `MailSendException` phản ánh vấn đề ở bước gửi
D. `MailParseException` phản ánh lỗi giao thư qua SMTP
Đáp án đúng: C

Câu 16. Khi `MimeMessagePreparator` ném lỗi trong lúc tạo nội dung, exception nào có thể bọc lỗi?
A. `MailSendException` báo lỗi cấu hình template MIME
B. `MailPreparationException` báo lỗi chuẩn bị thư MIME
C. `MailParseException` báo lỗi tạo body trong callback
D. `MailAuthenticationException` báo lỗi chuẩn bị thư MIME
Đáp án đúng: B

Câu 17. Để đặt địa chỉ SMTP server trên `JavaMailSenderImpl`, setter nào phù hợp?
A. `setDefaultEncoding("smtp.example.org")` chọn máy chủ
B. `setFrom("smtp.example.org")` chọn máy chủ gửi SMTP
C. `setProtocol("smtp.example.org")` chọn máy chủ gửi
D. `setHost("smtp.example.org")` chọn máy chủ gửi SMTP
Đáp án đúng: D

Câu 18. Khi SMTP server yêu cầu đăng nhập, thuộc tính Jakarta Mail nào thường cần bật?
A. `mail.smtp.starttls.enable=true` bật SMTP authentication
B. `mail.smtp.ssl.enable=true` bật SMTP authentication
C. `mail.smtp.quitwait=true` bật SMTP authentication
D. `mail.smtp.auth=true` bật SMTP authentication
Đáp án đúng: D

Câu 19. Khi SMTP dùng STARTTLS để nâng cấp kết nối, property nào bật yêu cầu nâng cấp nếu server hỗ trợ?
A. `mail.smtp.auth=true` bật STARTTLS
B. `mail.smtp.localhost=true` bật STARTTLS
C. `mail.smtp.starttls.enable=true` bật STARTTLS
D. `mail.smtp.ssl.enable=true` bật STARTTLS
Đáp án đúng: C

Câu 20. Muốn không gửi mail nếu máy chủ không cho STARTTLS, property nào phù hợp?
A. `mail.smtp.auth=false` yêu cầu STARTTLS
B. `mail.smtp.starttls.enable=false` yêu cầu STARTTLS
C. `mail.smtp.ssl.checkserveridentity=false` yêu cầu STARTTLS
D. `mail.smtp.starttls.required=true` yêu cầu STARTTLS
Đáp án đúng: D

Câu 21. Nếu endpoint SMTP yêu cầu TLS ngay khi kết nối (implicit TLS), property nào phù hợp?
A. `mail.smtp.starttls.enable=true` khởi tạo TLS trực tiếp
B. `mail.smtp.ssl.enable=true` khởi tạo kết nối TLS
C. `mail.smtp.auth=true` khởi tạo kết nối TLS trực tiếp
D. `mail.smtp.connectiontimeout=0` khởi tạo kết nối TLS
Đáp án đúng: B

Câu 22. Để giới hạn thời gian mở TCP connection tới SMTP server, property nào phù hợp?
A. `mail.smtp.connectiontimeout` giới hạn lúc kết nối
B. `mail.smtp.writetimeout` giới hạn lúc kết nối
C. `mail.smtp.quitwait` giới hạn lúc kết nối
D. `mail.smtp.timeout` giới hạn lúc kết nối
Đáp án đúng: A

Câu 23. Để giới hạn thời gian đọc phản hồi từ SMTP server đang kết nối, property nào phù hợp?
A. `mail.smtp.timeout` giới hạn thời gian đọc socket
B. `mail.smtp.ssl.enable` giới hạn thời gian đọc socket
C. `mail.smtp.connectiontimeout` giới hạn thời gian đọc
D. `mail.smtp.writetimeout` giới hạn thời gian đọc socket
Đáp án đúng: A

Câu 24. Để tránh treo ở thao tác ghi dữ liệu ra socket SMTP, property nào phù hợp?
A. `mail.smtp.timeout` giới hạn thời gian ghi socket
B. `mail.smtp.connectiontimeout` giới hạn thời gian ghi
C. `mail.smtp.starttls.required` giới hạn lúc ghi socket
D. `mail.smtp.writetimeout` giới hạn thời gian ghi
Đáp án đúng: D

Câu 25. Với SMTP cổng 587 được cấu hình STARTTLS, lựa chọn kết nối nào phù hợp?
A. Cấu hình cổng 587 và tắt hỗ trợ STARTTLS
B. Cấu hình cổng 587 và `smtp.auth=false` là đủ
C. Cấu hình cổng 587 và `ssl.enable=true`
D. Cấu hình cổng 587 và `starttls.enable=true`
Đáp án đúng: D

Câu 26. Khi địa chỉ người nhận phản hồi khác địa chỉ From, helper cần cấu hình gì?
A. `setReplyTo` chỉ định nơi nhận thư phản hồi
B. `setSubject` chỉ định nơi nhận thư phản hồi
C. `setFrom` chỉ định nơi nhận thư phản hồi
D. `setTo` chỉ định nơi nhận thư phản hồi
Đáp án đúng: A

Câu 27. Muốn gửi bản sao mà người nhận khác không thấy địa chỉ, dùng loại recipient nào?
A. Thêm địa chỉ với `addBcc` để ẩn khỏi danh sách hiển thị
B. Thêm địa chỉ với `addCc` để ẩn khỏi danh sách hiển thị
C. Thêm địa chỉ với `addTo` để ẩn khỏi danh sách hiển thị
D. Thêm địa chỉ với `setReplyTo` để ẩn khỏi danh sách
Đáp án đúng: A

Câu 28. Trong quy trình mail có template, vai trò đúng của Thymeleaf hay công cụ tương tự là gì?
A. Tự xác nhận delivery khi template được render xong
B. Render HTML từ template và model trước khi gán MIME body
C. Tự mở phiên Jakarta Mail khi render các placeholder
D. Thay SMTP transport để chuyển HTML trực tiếp tới relay
Đáp án đúng: B

Câu 29. Khi chèn tên người dùng chưa tin cậy vào template HTML email, cần ưu tiên gì?
A. Đưa dữ liệu vào JavaScript trong HTML và bỏ escape
B. Escape nội dung theo ngữ cảnh HTML khi render template
C. Chèn nội dung vào HTML thô bằng nối chuỗi không lọc
D. Đánh dấu nội dung đầu vào là safe HTML khi render
Đáp án đúng: B

Câu 30. Với nguồn dữ liệu attachment dạng stream, yêu cầu quan trọng trong JavaMailSender là gì?
A. InputStreamSource phải cấp stream mới khi được đọc lại
B. InputStreamSource chỉ đọc một lần và tái dùng stream đã hết
C. InputStreamSource giữ kết nối HTTP mở trong cả transaction
D. InputStreamSource chuyển tệp thành văn bản trước khi gửi
Đáp án đúng: A

Câu 31. Sau khi SMTP server trả mã thành công chấp nhận message, kết luận nào chính xác?
A. Thư đã vượt qua các bộ lọc spam tại mailbox cuối
B. SMTP đã xác nhận đầy đủ việc đọc thư ở phía người nhận
C. Relay đã nhận trách nhiệm xử lý, chưa bảo đảm vào inbox
D. Người nhận đã mở thư và email có thể đánh dấu hoàn tất
Đáp án đúng: C

Câu 32. SMTP relay đã chấp nhận thư nhưng sau đó không giao được; tín hiệu nào có thể đến muộn?
A. Bounce hoặc delivery status notification có thể đến sau
B. Callback trên `SimpleMailMessage` khi mailbox đóng
C. `MailSendException` đồng bộ ngay sau SMTP 250
D. JavaMailSender tự rút lại email từ hộp thư nhận
Đáp án đúng: A

Câu 33. Khi SMTP trả 4xx transient failure, chiến lược ứng dụng nào hợp lý?
A. Dừng retry rồi đánh dấu địa chỉ gửi là sai vĩnh viễn
B. Gửi lại ngay không giới hạn để tăng tốc phục hồi
C. Đổi From header trước khi đánh giá mã SMTP lỗi
D. Retry có giới hạn sau khoảng chờ phù hợp với lỗi tạm
Đáp án đúng: D

Câu 34. Khi SMTP trả mã 5xx permanent failure, cách xử lý nào phù hợp?
A. Xem 5xx là xác nhận giao thành công tới người nhận
B. Chỉ tăng timeout TCP mà không cần phân tích lỗi
C. Ghi nhận lỗi lâu dài, tránh retry lặp vô hạn cùng dữ liệu
D. Retry không giới hạn trong vòng lặp để giảm số lần báo
Đáp án đúng: C

Câu 35. Vì sao retry sau network timeout có thể gây gửi trùng email?
A. SMTP đảm bảo mỗi lần retry được khử trùng bằng Message-ID
B. Server có thể đã nhận thư trước khi client thấy timeout
C. Relay loại bỏ message khỏi hàng đợi khi socket ngắt
D. Spring xóa bản thư đã gửi khi gặp lỗi network timeout
Đáp án đúng: B

Câu 36. Để thực thi gửi email ở worker thay vì thread HTTP request qua `@Async`, cần gì?
A. Đặt `@Scheduled` để `@Async` thành task định kỳ
B. Gọi private method trong cùng bean để bật async
C. Bật `@EnableAsync` và gọi qua proxy-managed bean
D. Tăng timeout HTTP để chuyển việc gửi sang worker
Đáp án đúng: C

Câu 37. Vì sao gọi `this.sendMailAsync()` trong cùng bean có thể vẫn chạy đồng bộ?
A. Lời gọi nội bộ bỏ qua Spring proxy thực thi `@Async`
B. Spring thay executor bằng scheduler theo method name
C. SMTP relay chờ context refresh mới xử lý request
D. JavaMailSender chuyển sang SMTP polling mode
Đáp án đúng: A

Câu 38. Muốn lưu yêu cầu gửi mail bền vững cùng giao dịch tạo đơn hàng, thiết kế nào phù hợp?
A. Giữ HTTP request đến khi email delivery thành công
B. Ghi outbox record trong transaction rồi worker gửi mail
C. Phát SMTP trong transaction và coi send là commit hai pha
D. Chỉ dùng `@Async` sau khi save mà không lưu yêu cầu mail
Đáp án đúng: B

Câu 39. Trong kiểm thử tích hợp gửi HTML và attachment, cách nào kiểm MIME mà không phát mail thật?
A. Chỉ mock thư viện logger rồi khẳng định SMTP hoạt động
B. Chỉ kiểm DTO mà bỏ phần MIME và mail transport
C. Dùng fake SMTP server để nhận và kiểm tra MimeMessage
D. Gửi mail đến địa chỉ cá nhân để kiểm bằng mắt thường
Đáp án đúng: C

Câu 40. Để quan sát vận hành gửi mail, bộ chỉ số nào hữu ích nhất?
A. Chỉ đếm số template HTML đã render trong tuần
B. Chỉ theo dõi tổng số thread sống của server JVM
C. Đếm send attempts, accepted, failures và độ trễ SMTP
D. Chỉ đếm số bean Spring được khởi tạo khi ứng dụng chạy
Đáp án đúng: C
