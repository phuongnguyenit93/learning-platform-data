Khi tiếp nhận tệp upload, cách xác định định dạng nào đáng tin cậy nhất?
A. Kết hợp allowlist, chữ ký tệp và kết quả parse an toàn.
B. Chọn parser theo phần mở rộng do trình duyệt gửi lên.
C. Dựa vào Content-Type trong multipart request của client.
D. Dùng tên tệp và kích thước để suy ra loại dữ liệu.
Đáp án đúng: A

Vì sao kiểm tra magic bytes chưa đủ để kết luận một tệp an toàn?
A. Chữ ký tệp luôn bị mất khi truyền qua HTTP multipart.
B. Tệp có thể giả dạng hoặc lỗi cấu trúc dù chữ ký khớp.
C. Magic bytes chỉ có thể được đọc sau khi parser chạy xong.
D. Chữ ký tệp không thể phân biệt dữ liệu nhị phân và văn bản.
Đáp án đúng: B

Ứng dụng cần lưu tệp upload trên filesystem; cách đặt tên nào an toàn hơn?
A. Sinh tên nội bộ ngẫu nhiên và lưu tên gốc như metadata.
B. Giữ nguyên tên gốc sau khi thay dấu gạch chéo.
C. Dùng đường dẫn client gửi nhưng chuẩn hóa dấu phân cách.
D. Ghép username với tên tệp để tránh trùng trong thư mục.
Đáp án đúng: A

Client gửi Content-Type là image/png nhưng nội dung thực tế là HTML; server nên làm gì?
A. Kiểm tra theo allowlist và parser phù hợp.
B. Đổi phần mở rộng thành .png rồi lưu tệp như ảnh.
C. Tin Content-Type nếu request được gửi qua HTTPS.
D. Chỉ kiểm tra kích thước vì HTML thường nhỏ hơn ảnh.
Đáp án đúng: A

Khi giải nén archive, biện pháp nào ngăn Zip Slip hiệu quả?
A. Loại bỏ mọi dấu chấm khỏi tên entry trước khi ghi.
B. Chuẩn hóa path và kiểm tra containment.
C. Chỉ cho phép archive có phần mở rộng .zip hoặc .tar.
D. Ghép tên entry vào thư mục tạm bằng chuỗi tương đối.
Đáp án đúng: B

Để hạn chế zip bomb, bộ giải nén nên áp dụng kiểm soát nào?
A. Chỉ kiểm tra kích thước archive nén trước khi giải nén.
B. Tin trường uncompressed size được khai báo trong central directory.
C. Giới hạn bytes thực tế, số entry, tỷ lệ và thời gian xử lý.
D. Tăng dung lượng ổ đĩa tạm theo kích thước archive nhận được.
Đáp án đúng: C

Vì sao cần đếm bytes thực tế trong lúc giải nén thay vì chỉ tin metadata?
A. Metadata archive thường được mã hóa bằng khóa riêng của parser.
B. Bộ giải nén không thể đọc kích thước của entry trước khi mở.
C. Kích thước khai báo có thể sai hoặc bị làm giả.
D. Filesystem tự động nén lại dữ liệu sau khi ghi xong.
Đáp án đúng: C

Archive có thể chứa archive lồng nhau nhiều tầng; giới hạn nào cần thiết?
A. Chỉ giới hạn tổng dung lượng file archive ngoài cùng.
B. Giới hạn độ sâu và ngân sách giải nén chung.
C. Cho phép đệ quy không giới hạn nếu mỗi archive nhỏ.
D. Chỉ kiểm tra số tầng sau khi giải nén toàn bộ nội dung.
Đáp án đúng: B

Khi archive chứa symbolic link trỏ ra ngoài thư mục giải nén, nên xử lý thế nào?
A. Tạo link rồi kiểm tra đích sau khi toàn bộ archive hoàn tất.
B. Chuyển symbolic link thành hard link tới đường dẫn tương ứng.
C. Từ chối entry symlink trong quá trình giải nén.
D. Cho phép link nếu tên entry ban đầu nằm trong thư mục gốc.
Đáp án đúng: C

Nơi lưu tệp upload trước khi kiểm duyệt nên được cấu hình ra sao?
A. Trong web root để ứng dụng có thể phục vụ ngay bằng URL.
B. Trong thư mục tạm dùng chung với quyền ghi cho mọi user.
C. Trong thư mục static public nhưng đổi tên thành UUID.
D. Lưu quarantine riêng với quyền tối thiểu.
Đáp án đúng: D

Để giới hạn upload lớn và nhiều phần, cách triển khai nào phù hợp?
A. Chỉ giới hạn kích thước cuối cùng sau khi lưu vào object storage.
B. Dùng Content-Length do client gửi để bỏ qua kiểm tra streaming.
C. Tăng timeout proxy để mọi request upload có thể hoàn tất.
D. Áp dụng giới hạn ở proxy và ứng dụng khi đọc luồng dữ liệu.
Đáp án đúng: D

Một parser xử lý tài liệu phức tạp nên được cô lập theo cách nào?
A. Chạy cùng process web với quyền filesystem của ứng dụng.
B. Chạy process riêng, quyền thấp và filesystem được giới hạn.
C. Chạy bằng tài khoản quản trị để tránh lỗi quyền khi parse.
D. Chạy trong thread riêng nhưng dùng chung mọi quyền của server.
Đáp án đúng: B

Những giới hạn nào hữu ích khi chạy parser trong sandbox?
A. Chỉ đặt giới hạn số request đồng thời tại load balancer.
B. Chỉ giới hạn heap của process web gọi parser.
C. Chỉ đặt timeout ở giao diện người dùng khi upload.
D. Giới hạn CPU, RAM, thời gian và file descriptor.
Đáp án đúng: D

Quy trình antivirus scan bất đồng bộ nên phục vụ tệp cho người dùng lúc nào?
A. Ngay khi upload xong nếu magic bytes khớp allowlist.
B. Sau khi tệp được ghi vào thư mục public với tên ngẫu nhiên.
C. Sau khi client nhận HTTP 202 và bắt đầu tải lại tệp.
D. Chỉ mở quyền phục vụ sau verdict cho phép.
Đáp án đúng: D

Content Disarm and Reconstruction (CDR) phù hợp với mục tiêu nào?
A. Loại bỏ nội dung chủ động rồi tạo bản mới.
B. Chứng minh tệp gốc không có lỗ hổng trong mọi parser.
C. Thay thế hoàn toàn việc kiểm tra malware và kiểm soát truy cập.
D. Khôi phục mọi macro và script để tài liệu giữ nguyên chức năng.
Đáp án đúng: A

Làm thế nào tránh scan một phiên bản tệp rồi lại phục vụ bytes khác?
A. Quét tên tệp trước rồi cho phép ghi đè nội dung sau đó.
B. Dùng đường dẫn cố định để mọi worker cùng mở một tệp.
C. Gắn verdict với object version hoặc content hash bất biến.
D. Chỉ lưu thời điểm scan và bỏ qua kiểm tra nội dung sau này.
Đáp án đúng: C

Để giảm nguy cơ XXE khi parse XML không đáng tin cậy, nên cấu hình gì?
A. Tắt DTD và external entity resolution trong parser.
B. Cho phép external DTD nhưng giới hạn số kết nối mạng.
C. Bật XInclude để parser tự chuẩn hóa tham chiếu ngoài.
D. Chỉ kiểm tra XML well-formed trước khi xử lý entity.
Đáp án đúng: A

XML có thể bị tấn công entity expansion gây tiêu thụ tài nguyên; cách phòng vệ nào phù hợp?
A. Tăng heap để parser có thể xử lý document lớn hơn.
B. Tắt entity expansion và giới hạn parse.
C. Cho phép entity lồng nhau nhưng giảm timeout HTTP.
D. Chuyển XML sang UTF-8 trước khi phân tích nội dung.
Đáp án đúng: B

Schema validation hoặc XInclude có thể tạo thêm rủi ro nào khi xử lý XML?
A. Làm mất magic bytes của file trước khi parser đọc.
B. Kích hoạt truy cập tài nguyên ngoài nếu không giới hạn.
C. Tự động cấp quyền ghi cho thư mục chứa schema.
D. Thay đổi checksum của tài liệu ngay khi parse thành công.
Đáp án đúng: B

Khi parse JSON không đáng tin cậy, giới hạn nào giúp tránh cạn tài nguyên?
A. Chỉ giới hạn số ký tự trong từng tên thuộc tính.
B. Cho phép độ sâu tùy ý nếu tổng body dưới giới hạn.
C. Chỉ kiểm tra Content-Type trước khi tạo object graph.
D. Giới hạn kích thước, độ sâu và số token.
Đáp án đúng: D

Vì sao Java native object deserialization từ dữ liệu không tin cậy nguy hiểm?
A. Nó chỉ hỗ trợ primitive nên không thể kiểm tra schema.
B. Object graph có thể kích hoạt gadget chain.
C. Nó luôn bỏ qua mọi kiểm tra kiểu dữ liệu của JVM.
D. Nó tự động thực thi mọi file class nằm cạnh dữ liệu đầu vào.
Đáp án đúng: B

Ứng dụng buộc phải nhận dữ liệu tuần tự hóa từ bên ngoài; cách giảm rủi ro nào tốt hơn?
A. Dùng format data-only, schema và allowlist rõ ràng.
B. Cho phép mọi class trong classpath để tránh lỗi tương thích.
C. Chỉ kiểm tra độ dài byte stream trước khi deserialize.
D. Chạy deserialize bằng tài khoản root trong process riêng.
Đáp án đúng: A

YAML parser được cấu hình unsafe object constructor có thể gây hậu quả nào?
A. Tự động sửa đường dẫn tệp thành đường dẫn tương đối.
B. Bỏ qua mọi ký tự Unicode trong nội dung tài liệu.
C. Unsafe constructor có thể tạo object ngoài ý muốn.
D. Giới hạn kích thước tài liệu về mức tối đa của filesystem.
Đáp án đúng: C

JSON polymorphic type handling an toàn nên dựa trên nguyên tắc nào?
A. Chấp nhận tên class đầy đủ do client gửi để mở rộng linh hoạt.
B. Tự động nạp class mới khi discriminator chưa được nhận diện.
C. Cho phép mọi subtype kế thừa base type đã khai báo.
D. Ánh xạ discriminator vào tập subtype được phép.
Đáp án đúng: D

Khi parse PDF không đáng tin cậy, kiểm soát nào cần cân nhắc?
A. Chỉ đổi tên phần mở rộng để trình duyệt không nhận diện PDF.
B. Cho phép JavaScript nhúng chạy để kiểm tra tài liệu đầy đủ.
C. Kiểm tra active content và cô lập parser.
D. Tin metadata Author và Producer để xác định nguồn tài liệu.
Đáp án đúng: C

Một ảnh có kích thước file nhỏ nhưng khai báo chiều rộng và chiều cao rất lớn; cần làm gì?
A. Tăng memory limit để decoder có thể cấp phát đủ pixel.
B. Chỉ kiểm tra phần mở rộng và magic bytes trước khi decode.
C. Từ chối mọi ảnh có kích thước pixel lớn hơn ảnh mẫu.
D. Giới hạn tổng pixel trước khi giải mã ảnh.
Đáp án đúng: D

Vì sao parser nên được cập nhật và chạy với quyền tối thiểu?
A. Để tránh mọi lỗi định dạng phát sinh từ file đầu vào.
B. Giảm tác động khi parser bị khai thác.
C. Để không cần kiểm tra loại file trước khi parse nữa.
D. Để parser có thể truy cập mọi file hệ thống khi cần.
Đáp án đúng: B

Thông báo lỗi parse trả về cho người dùng nên được thiết kế thế nào?
A. Trả stack trace và đường dẫn tệp nội bộ để dễ hỗ trợ.
B. Trả nguyên thông điệp lỗi từ thư viện parser bên thứ ba.
C. Lỗi chung cho client, chi tiết ghi log nội bộ.
D. Trả nội dung byte quanh vị trí lỗi để người dùng tự sửa.
Đáp án đúng: C

Fuzz testing parser nên tập trung vào loại đầu vào nào?
A. Chỉ các file mẫu hợp lệ do nhà cung cấp thư viện phát hành.
B. Dữ liệu ngẫu nhiên không giới hạn tài nguyên để tăng áp lực.
C. Chỉ các file đã qua antivirus scan và xác nhận sạch.
D. Corpus hợp lệ và lỗi, mutation có kiểm soát cùng sanitizer.
Đáp án đúng: D

Khi giải nén archive có tên entry khác nhau chỉ bởi Unicode normalization hoặc chữ hoa thường, cần làm gì?
A. Chuẩn hóa tên và phát hiện va chạm trước khi tạo file.
B. Ghi mọi entry theo thứ tự trong archive để giữ nguyên tên.
C. Chuyển tất cả tên sang dạng ngẫu nhiên sau khi ghi xong.
D. Cho phép ghi đè vì filesystem sẽ tự phân biệt mọi trường hợp.
Đáp án đúng: A

Sau khi lưu file upload đã được kiểm duyệt, cách phục vụ nào an toàn hơn?
A. Phục vụ inline với Content-Type do client gửi trong request.
B. Lưu trong web root và dựa vào tên ngẫu nhiên để bảo vệ.
C. Dùng MIME đã xác thực, nosniff và download policy.
D. Cho phép trình duyệt tự suy đoán nội dung theo bytes đầu tiên.
Đáp án đúng: C

Với object storage chứa tệp upload, cấu hình nào nên được ưu tiên?
A. Bucket private, quyền truy cập tối thiểu và URL có thời hạn.
B. Bucket public và URL khó đoán để giảm yêu cầu xác thực.
C. Dùng tên object do client gửi để dễ đối chiếu khi hỗ trợ.
D. Cho phép mọi service trong tài khoản cloud đọc và ghi object.
Đáp án đúng: A

Một dịch vụ parse file bất đồng bộ nhận burst upload lớn; cách bảo vệ queue nào phù hợp?
A. Dùng queue không giới hạn để không từ chối upload hợp lệ.
B. Tăng số parser worker theo số message chờ hiện tại.
C. Giới hạn queue và áp dụng backpressure.
D. Xóa message cũ khi queue đầy mà không ghi nhận kết quả.
Đáp án đúng: C

Checksum của file upload có thể chứng minh điều gì?
A. Tệp không chứa malware hoặc nội dung thực thi nguy hiểm.
B. Tệp được tạo bởi người gửi có danh tính đã xác thực.
C. Tệp an toàn với mọi parser và phiên bản thư viện.
D. Đối chiếu checksum tin cậy giúp phát hiện bytes bị đổi.
Đáp án đúng: D

Khi hai thư viện parse cùng định dạng nhưng diễn giải file khác nhau, kiểm thử nào hữu ích?
A. Chỉ kiểm thử định dạng phổ biến nhất trên máy developer.
B. Differential test và regression trên mẫu biên.
C. Chỉ chạy fuzzing khi có báo cáo crash từ production.
D. Bỏ qua khác biệt parser nếu cùng phần mở rộng tệp.
Đáp án đúng: B

Một tệp được antivirus đánh dấu sạch nhưng parser chưa được vá lỗ hổng; điều gì cần làm?
A. Vẫn vá parser và cô lập quá trình xử lý định dạng.
B. Tin verdict antivirus vì nó đã kiểm tra toàn bộ nội dung.
C. Cho phép parser chạy với quyền cao để hoàn tất xử lý.
D. Chỉ đổi tên file để tránh kích hoạt lỗ hổng đã biết.
Đáp án đúng: A
