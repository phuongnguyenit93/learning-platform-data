Câu 01. Mục tiêu chính của data masking trong giao diện là gì?
A. Xóa bản ghi khỏi hệ thống nguồn và mọi bản sao lưu.
B. Che bớt giá trị khi người xem không cần toàn bộ.
C. Thay giá trị bằng token có thể tra cứu trong vault.
D. Biến dữ liệu thành thống kê không còn liên hệ cá nhân.
Đáp án đúng: B

Câu 02. Một báo cáo cần che số điện thoại nhưng vẫn giữ bốn số cuối. Cách phù hợp là gì?
A. Giữ nguyên số điện thoại và chỉ ẩn nhãn trường dữ liệu.
B. Xóa số điện thoại khỏi bản ghi trước khi tạo báo cáo.
C. Áp dụng quy tắc hiển thị chỉ giữ lại phần đuôi được phép.
D. Thay số điện thoại bằng mã ngẫu nhiên trong toàn bộ cơ sở dữ liệu.
Đáp án đúng: C

Câu 03. Khi phát hành bản PDF ra bên ngoài, redaction cần bảo đảm điều gì?
A. Đặt hình chữ nhật đen lên chữ nhưng giữ nguyên lớp văn bản.
B. Ẩn lớp hiển thị trong trình đọc nhưng giữ nội dung gốc.
C. Đổi tên tệp và metadata mà không sửa phần nội dung.
D. Loại nội dung nhạy cảm khỏi phần dữ liệu PDF phát hành.
Đáp án đúng: D

Câu 04. Tokenization khác masking thông thường ở điểm nào?
A. Thay giá trị bằng token có ánh xạ được bảo vệ.
B. Xóa dữ liệu gốc và không giữ bất kỳ ánh xạ nào.
C. Mã hóa dữ liệu bằng khóa có thể giải mã trực tiếp.
D. Chỉ che ký tự trên màn hình trong lúc hiển thị dữ liệu.
Đáp án đúng: A

Câu 05. Kho token vault cần được bảo vệ chủ yếu vì lý do nào?
A. Nó tự động ẩn mọi trường dữ liệu trong API response.
B. Nó chỉ chứa token ngẫu nhiên nên không có dữ liệu nhạy cảm.
C. Nó lưu ánh xạ cho phép liên kết token về dữ liệu gốc.
D. Nó thay thế hoàn toàn kiểm soát truy cập ở hệ thống nguồn.
Đáp án đúng: C

Câu 06. Hai hệ thống cần tạo cùng token cho một khách hàng để đối soát. Thiết kế nào phù hợp?
A. Giữ nguyên dữ liệu gốc và chỉ đổi tên trường khi trao đổi.
B. Dùng token nhất quán theo phạm vi, có kiểm soát quyền.
C. Dùng số thứ tự bản ghi làm token chung cho mọi tenant.
D. Tạo token ngẫu nhiên độc lập ở mỗi hệ thống rồi so sánh trực tiếp.
Đáp án đúng: B

Câu 07. Format-preserving tokenization có rủi ro cần đánh giá nào?
A. Giữ định dạng khiến token không thể dùng trong hệ thống cũ.
B. Định dạng giữ lại có thể làm lộ đặc điểm của giá trị gốc.
C. Token có định dạng tương tự thì không cần kiểm soát truy cập.
D. Token luôn dài hơn dữ liệu gốc nên chi phí lưu trữ tăng.
Đáp án đúng: B

Câu 08. Pseudonymization khác anonymization ở điểm quan trọng nào?
A. Hai kỹ thuật chỉ khác nhau ở cách hiển thị trên giao diện.
B. Giả danh luôn loại bỏ vĩnh viễn mọi khả năng nhận diện.
C. Giả danh vẫn có thể liên kết lại bằng dữ liệu bổ sung.
D. Khử định danh luôn giữ bảng ánh xạ riêng để phục hồi.
Đáp án đúng: C

Câu 09. Một bộ dữ liệu bỏ tên và email nhưng giữ ngày sinh, mã bưu chính. Rủi ro nào còn lại?
A. Rủi ro chỉ xuất hiện khi bộ dữ liệu có trường mật khẩu.
B. Nhiều thuộc tính kết hợp vẫn có thể nhận diện cá nhân.
C. Không còn rủi ro vì tên và email đã được loại bỏ.
D. Chỉ còn rủi ro nếu dữ liệu được lưu dưới dạng plaintext.
Đáp án đúng: B

Câu 10. k-anonymity được dùng để đánh giá điều gì?
A. Mỗi tổ hợp quasi-identifier lặp lại ít nhất k lần.
B. Mỗi bản ghi được truy cập bởi ít nhất k người dùng.
C. Mỗi trường nhạy cảm có k giá trị token khác nhau.
D. Mỗi cá nhân có ít nhất k thuộc tính được mã hóa.
Đáp án đúng: A

Câu 11. Một tập dữ liệu đạt k-anonymity nhưng một nhóm có cùng bệnh lý. Hạn chế nào được minh họa?
A. Thuộc tính nhạy cảm vẫn có thể bị suy luận qua đồng nhất nhóm.
B. k-anonymity bảo đảm mọi thuộc tính nhạy cảm đều đa dạng.
C. Việc ẩn tên khiến thông tin bệnh lý không còn liên quan cá nhân.
D. Thêm bản ghi trùng lặp sẽ tự động giải quyết rủi ro.
Đáp án đúng: A

Câu 12. Khi đánh giá khả năng tái nhận diện, nên xem xét yếu tố nào?
A. Chỉ số lượng cột đã bị xóa khỏi bảng dữ liệu.
B. Chỉ việc dữ liệu đã được nén trước khi chia sẻ.
C. Chỉ số người có quyền truy cập hệ thống lưu trữ.
D. Xét khả năng ghép nguồn ngoài và thuộc tính phụ.
Đáp án đúng: D

Câu 13. Một API trả hồ sơ cho nhân viên hỗ trợ. Cách áp dụng masking phù hợp là gì?
A. Trả toàn bộ dữ liệu rồi yêu cầu giao diện tự che bằng CSS.
B. Xóa vĩnh viễn dữ liệu nhạy cảm ngay khi có request đọc.
C. Trả dữ liệu gốc cho mọi nhân viên đã đăng nhập hợp lệ.
D. Trả trường cần thiết, che trường nhạy cảm theo vai trò.
Đáp án đúng: D

Câu 14. Một endpoint GraphQL cho phép chọn field tùy ý. Rủi ro masking nằm ở đâu?
A. GraphQL tự động áp dụng masking cho mọi field trong schema.
B. Resolver có thể bỏ qua quy tắc che field nhạy cảm.
C. Chỉ tên field được ẩn nên giá trị không thể bị lộ.
D. Masking ở gateway luôn bao phủ mọi truy vấn lồng nhau.
Đáp án đúng: B

Câu 15. Log ứng dụng chứa email và số thẻ thanh toán. Điểm áp dụng redaction tốt là khi nào?
A. Sau khi tạo bản sao lưu để không ảnh hưởng pipeline chính.
B. Chỉ khi nhân viên mở dashboard để xem sự kiện log.
C. Sau khi log đã được gửi tới mọi hệ thống lưu trữ và tìm kiếm.
D. Redact trước khi log rời khỏi thành phần tạo sự kiện.
Đáp án đúng: D

Câu 16. Một pipeline log dùng regex che số thẻ nhưng định dạng có dấu cách hoặc gạch ngang. Cần làm gì?
A. Chuẩn hóa và kiểm thử dạng có dấu cách, gạch nối.
B. Xóa mọi dòng log có dấu cách để tránh xử lý phức tạp.
C. Chỉ tìm chuỗi chữ số liền nhau theo một mẫu duy nhất.
D. Giữ nguyên log và dựa vào quyền truy cập dashboard.
Đáp án đúng: A

Câu 17. Ứng dụng log toàn bộ request body để điều tra lỗi. Biện pháp bền vững hơn là gì?
A. Chuyển log sang tệp nén để giảm khả năng đọc dữ liệu.
B. Chỉ che body ở giao diện tìm kiếm của hệ thống log.
C. Allowlist trường log, bỏ dữ liệu nhạy cảm tại nguồn.
D. Log nguyên body rồi mã hóa toàn bộ kho log bằng TLS.
Đáp án đúng: C

Câu 18. Một thông điệp lỗi chứa access token trong stack trace. Nên xử lý thế nào?
A. Che token trước khi ghi log, giữ dấu tra cứu an toàn.
B. Chỉ xóa token khỏi log sau khi hoàn tất điều tra.
C. Giữ token trong log nhưng chỉ cho nhóm phát triển đọc.
D. Chuyển token sang chữ thường để giảm khả năng sử dụng.
Đáp án đúng: A

Câu 19. Masking dữ liệu trong metrics label cần cân nhắc điều gì?
A. Giữ mọi định danh vì metrics luôn có thời gian lưu ngắn.
B. Tránh định danh cá nhân trong label, giới hạn cardinality.
C. Hash định danh rồi dùng làm label mà không cần giới hạn.
D. Đổi tên label để giá trị cá nhân không còn nhạy cảm.
Đáp án đúng: B

Câu 20. Một giao diện cần hiển thị số thẻ thanh toán cho nhân viên tổng đài. Cách nào hợp lý?
A. Hiển thị toàn bộ số thẻ cho mọi nhân viên đã đăng nhập.
B. Ẩn số thẻ bằng CSS nhưng giữ nguyên trong thuộc tính DOM.
C. Chỉ che số thẻ khi người dùng chụp màn hình.
D. Che mặc định, chỉ mở phần cần theo quyền và mục đích.
Đáp án đúng: D

Câu 21. Một người dùng có quyền xem bản ghi nhưng không cần xem dữ liệu định danh đầy đủ. Chính sách nào phù hợp?
A. Ẩn nút giao diện nhưng giữ API trả dữ liệu không che.
B. Chuyển mọi trường sang token và cấp vault cho tất cả người dùng.
C. Tách quyền đọc bản ghi khỏi quyền xem trường dữ liệu nhạy cảm.
D. Cho phép đọc toàn bộ trường vì quyền xem bản ghi đã đủ.
Đáp án đúng: C

Câu 22. Dynamic data masking trong database thường có đặc điểm nào?
A. Xóa dữ liệu gốc sau mỗi lần truy vấn hoàn tất.
B. Thay khóa mã hóa dữ liệu sau mỗi lần người dùng đọc.
C. Tạo bộ dữ liệu giả mới và ghi đè các giá trị trong bảng.
D. Điều chỉnh cách hiển thị giá trị theo quyền truy cập.
Đáp án đúng: D

Câu 23. Static data masking thường phù hợp với trường hợp nào?
A. Giải mã dữ liệu đã token hóa khi hệ thống cần xử lý giao dịch.
B. Giữ nguyên dữ liệu gốc và chỉ thay đổi quyền xem theo vai trò.
C. Tạo bản sao dữ liệu đã che để dùng ở môi trường phi production.
D. Ẩn giá trị tạm thời cho người dùng trong một truy vấn trực tuyến.
Đáp án đúng: C

Câu 24. Khi tạo dữ liệu thử nghiệm từ production, lựa chọn nào giảm rủi ro tốt?
A. Copy production nguyên trạng rồi giới hạn thời gian truy cập.
B. Ẩn tên cột nhưng giữ nguyên mọi giá trị cá nhân.
C. Tạo bản sao đã che để dùng ở môi trường phi production.
D. Chỉ thay email, còn định danh và dữ liệu liên hệ được giữ.
Đáp án đúng: C

Câu 25. Một bộ dữ liệu thử nghiệm cần giữ quan hệ khóa ngoại giữa nhiều bảng. Cách masking nào phù hợp?
A. Xóa toàn bộ khóa ngoại trước khi sao chép bảng dữ liệu.
B. Giữ ánh xạ để cùng giá trị nguồn nhận cùng giá trị mới.
C. Giữ nguyên ID thật và chỉ che các trường mô tả.
D. Tạo giá trị ngẫu nhiên riêng cho mỗi ô để tránh trùng lặp.
Đáp án đúng: B

Câu 26. Dữ liệu đã masking nhưng cần giữ phân bố thống kê gần dữ liệu thật. Cần cân nhắc gì?
A. Chỉ thay tên và email vì các trường khác không ảnh hưởng phân bố.
B. Xáo trộn ngẫu nhiên mọi ô mà không cần kiểm tra quan hệ.
C. Bảo toàn đặc tính cần thiết và đo rủi ro liên kết lại.
D. Giữ nguyên mọi giá trị để phân bố thống kê không thay đổi.
Đáp án đúng: C

Câu 27. Một tổ chức dùng token ổn định giữa các tập dữ liệu. Rủi ro nào cần quản lý?
A. Token chung có thể liên kết bản ghi qua nhiều nguồn.
B. Token ổn định làm dữ liệu không còn khả năng phân tích.
C. Giữ token ổn định khiến kho ánh xạ không cần bảo vệ.
D. Token ổn định luôn ngăn việc so khớp giữa hai nguồn.
Đáp án đúng: A

Câu 28. Vì sao hash thông thường không phải lúc nào cũng đủ để khử định danh?
A. Hash tự động loại bỏ mọi thuộc tính có thể liên kết cá nhân.
B. Miền đầu vào nhỏ dễ bị dò từ điển rồi so khớp lại.
C. Hash làm mất tính toàn vẹn nên dữ liệu không còn sử dụng được.
D. Hash luôn có thể giải mã trực tiếp nếu biết thuật toán.
Đáp án đúng: B

Câu 29. Một tổ chức cần chia sẻ dữ liệu cho đối tác nghiên cứu. Bước nào nên làm trước?
A. Chia sẻ toàn bộ dữ liệu nếu đối tác đã ký thỏa thuận bảo mật.
B. Chỉ xóa tên rồi gửi ngay để đối tác tự đánh giá rủi ro.
C. Chuyển tệp sang định dạng khác để dữ liệu khó đọc hơn.
D. Đánh giá mục đích, trường dữ liệu và khả năng liên kết lại.
Đáp án đúng: D

Câu 30. Redaction tài liệu scan khác redaction PDF có lớp text như thế nào?
A. PDF có lớp text chỉ cần che pixel hiển thị trên trang.
B. Chỉ cần đổi metadata là nội dung scan không thể phục hồi.
C. Ảnh scan cần xử lý pixel và kiểm tra dữ liệu OCR.
D. Ảnh scan không chứa dữ liệu nên không cần redaction.
Đáp án đúng: C

Câu 31. Một file XLSX đã che dữ liệu nhưng bản export còn chứa dữ liệu trong sheet ẩn hoặc metadata. Cần kiểm tra gì?
A. Chỉ kiểm tra dữ liệu đang hiển thị trong ứng dụng bảng tính.
B. Chỉ mở sheet đầu tiên để xác nhận các ô đã bị che.
C. Đổi tên tệp và xóa phần mở rộng trước khi gửi.
D. Rà toàn bộ cấu trúc tệp, sheet ẩn, metadata và bản nhúng.
Đáp án đúng: D

Câu 32. Masking dữ liệu trong bản backup cần được quản lý ra sao?
A. Áp dụng masking cho bản sao, snapshot và khôi phục.
B. Xóa log backup để không còn dấu vết dữ liệu gốc.
C. Chỉ che dữ liệu sau khi đã phục hồi vào môi trường thử nghiệm.
D. Chỉ che bản production vì backup luôn nằm trong vùng an toàn.
Đáp án đúng: A

Câu 33. Một hệ thống cần giải mã token cho yêu cầu hỗ trợ đặc biệt. Kiểm soát nào phù hợp?
A. Chỉ ghi log khi việc reveal thất bại để tránh lưu quá nhiều.
B. Ẩn giao diện vault nhưng cho phép gọi API không xác thực.
C. Cho mọi nhân viên hỗ trợ quyền tra cứu token để xử lý nhanh.
D. Chỉ cho reveal theo mục đích, quyền và audit trail rõ ràng.
Đáp án đúng: D

Câu 34. Bảng ánh xạ token bị xóa nhưng bản backup vẫn còn. Ý nghĩa bảo mật nào cần lưu ý?
A. Khả năng liên kết lại có thể tồn tại trong bản backup chưa xử lý.
B. Xóa bảng chính chứng minh dữ liệu đã được khử định danh hoàn toàn.
C. Backup chỉ chứa ciphertext nên không thể khôi phục ánh xạ.
D. Token tự mất hiệu lực ở mọi hệ thống ngay khi xóa bảng chính.
Đáp án đúng: A

Câu 35. Một quy tắc masking dùng chung cho API, log và database. Vấn đề nào có thể phát sinh?
A. Log và giao diện có cùng ngữ cảnh nên không cần kiểm thử riêng.
B. Mỗi kênh có mục đích, định dạng và ranh giới tin cậy riêng.
C. Một quy tắc chung luôn bảo đảm che đúng mọi kiểu dữ liệu.
D. Database không cần masking nếu API đã áp dụng một lần.
Đáp án đúng: B

Câu 36. Một collector redaction không xử lý được một loại payload mới. Hành vi an toàn nên là gì?
A. Chuyển payload nguyên vẹn tiếp tục pipeline để không mất log.
B. Tự suy đoán vị trí dữ liệu nhạy cảm rồi xóa một phần.
C. Cách ly hoặc từ chối payload khi chưa thể xử lý an toàn.
D. Tắt redaction cho mọi nguồn đến khi parser được cập nhật.
Đáp án đúng: C

Câu 37. Sau khi đổi quy tắc masking, một số báo cáo không còn so sánh được với dữ liệu lịch sử. Cần quản lý thế nào?
A. Khôi phục dữ liệu gốc cho mọi báo cáo để giữ tính nhất quán.
B. Trộn dữ liệu cũ và mới mà không ghi nhận phiên bản masking.
C. Giữ quy tắc mới nhưng bỏ qua mọi khác biệt trong báo cáo.
D. Version hóa quy tắc, xác định cách chuyển dữ liệu lịch sử.
Đáp án đúng: D

Câu 38. Một dịch vụ tokenization tăng độ trễ khi tải cao. Cách tối ưu nào vẫn giữ kiểm soát?
A. Đo điểm nghẽn, tối ưu truy vấn và cache có TTL, phân quyền.
B. Cho phép ứng dụng tự đọc vault trực tiếp để bỏ qua dịch vụ.
C. Chuyển token thành ID tuần tự để tăng tốc mọi thao tác.
D. Cache toàn bộ dữ liệu gốc và bỏ qua kiểm tra quyền truy cập.
Đáp án đúng: A

Câu 39. Làm thế nào kiểm chứng một bộ dữ liệu đã khử định danh đủ tốt?
A. Đếm số dòng sau xử lý và so sánh với dữ liệu ban đầu.
B. Thử ghép với nguồn ngoài, đo rủi ro trên dữ liệu thật.
C. Xác nhận mọi cột đều đã được đổi tên trước khi chia sẻ.
D. Chỉ kiểm tra tên và email không còn xuất hiện trong tệp.
Đáp án đúng: B

Câu 40. Một chính sách masking cần cân bằng riêng tư và khả năng sử dụng dữ liệu. Cách tiếp cận nào phù hợp?
A. Xác định mục đích, độ nhạy và mức chi tiết cần thiết.
B. Giữ nguyên dữ liệu gốc và chỉ yêu cầu người dùng cẩn trọng.
C. Chọn một thuật toán masking duy nhất cho toàn tổ chức.
D. Che tối đa mọi trường trong mọi hệ thống bất kể nghiệp vụ.
Đáp án đúng: A
