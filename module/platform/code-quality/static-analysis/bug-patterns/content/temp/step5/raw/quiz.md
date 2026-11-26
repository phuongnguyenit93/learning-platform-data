Câu 1. Biến user có thể null sau truy vấn; cần làm gì trước khi gọi user.getName()?
A. Kiểm tra null trước khi đọc thuộc tính
B. Thêm synchronized quanh mọi lần gọi method
C. Chuyển các thuộc tính sang kiểu primitive
D. Ép kiểu user trước khi gọi phương thức
Đáp án đúng: A

Câu 2. Cảnh báo null dereference từ SpotBugs thường nói lên nguy cơ nào?
A. Chuỗi ký tự chưa được chuẩn hóa về UTF-8
B. Tệp tài nguyên chưa được đóng đúng thời điểm
C. Có nhánh dẫn tới dùng một tham chiếu null
D. Thread có thể chờ khóa theo thứ tự xung đột
Đáp án đúng: C

Câu 3. Gọi Optional.get() khi chưa biết có giá trị dễ tạo lỗi gì và nên xử lý ra sao?
A. Tràn bộ nhớ; nên tăng giới hạn heap JVM
B. Ném exception; xử lý Optional rỗng
C. Kẹt luồng; cần đồng bộ truy cập Optional
D. Mất dữ liệu; nên ghi Optional xuống tệp
Đáp án đúng: B

Câu 4. API hứa trả về giá trị non-null nhưng một nhánh lại return null, cách sửa phù hợp là gì?
A. Ẩn cảnh báo nullability ở toàn bộ module
B. Đưa lệnh return null vào khối try-catch
C. Sửa các nhánh để giữ hợp đồng non-null
D. Chỉ chuyển method sang private trong lớp
Đáp án đúng: C

Câu 5. Đọc tệp bằng Files.lines() nhưng không đóng Stream có thể gây gì và sửa thế nào?
A. Mất thứ tự dòng; chuyển sang parallelStream
B. Sai encoding; đổi toàn bộ tệp sang UTF-16
C. Thiếu tối ưu; chỉ thêm một biến final
D. Rò tài nguyên; dùng try-with-resources
Đáp án đúng: D

Câu 6. Hàm nhận InputStream thuộc quyền sở hữu của caller. Cách xử lý đóng tài nguyên hợp lý?
A. Tuân thỏa thuận sở hữu trước khi đóng stream
B. Luôn đóng stream ngay khi hàm được gọi
C. Đóng stream ở từng lần đọc một byte
D. Bỏ mọi kiểm soát vòng đời của stream
Đáp án đúng: A

Câu 7. Lớp Java override equals() nhưng không override hashCode() có nguy cơ gì?
A. Compiler luôn chặn mọi lời gọi equals
B. HashMap tự so sánh mọi khóa bằng toString
C. Collection tự bỏ qua giá trị hashCode
D. Hai đối tượng bằng nhau có hash khác
Đáp án đúng: D

Câu 8. Khi so sánh nội dung hai đối tượng String, điều gì thường đúng?
A. Dùng == để kiểm tra ký tự ở mọi trường hợp
B. Dùng equals để so nội dung chuỗi Java
C. Dùng hashCode thay cho phép so sánh chuỗi
D. Dùng compareTo chỉ để so địa chỉ đối tượng
Đáp án đúng: B

Câu 9. Với long total = quantity * price và hai toán hạng đều int, cách nào tránh overflow?
A. Ép long sau khi phép nhân int đã hoàn tất
B. Chỉ đổi kiểu của biến total thành long
C. Ép một toán hạng sang long rồi nhân
D. Gọi Math.abs cho kết quả sau phép nhân
Đáp án đúng: C

Câu 10. Nếu mẫu số được lấy từ request có thể bằng 0, cách xử lý đúng là gì?
A. Chuyển phép chia số nguyên thành phép trừ
B. Chỉ bắt NullPointerException quanh phép chia
C. Giấu cảnh báo bằng annotation ở phương thức
D. Kiểm tra mẫu số và xử lý trường hợp bằng 0
Đáp án đúng: D

Câu 11. Nhiều thread đồng thời tăng một biến đếm dùng chung; giải pháp nào tránh lost update?
A. Dùng AtomicInteger hoặc khóa cho phép tăng
B. Chỉ khai báo biến đếm là static trong class
C. Chuyển toàn bộ biến đếm sang kiểu String
D. Đọc biến đếm trong một khối if riêng
Đáp án đúng: A

Câu 12. Vì sao volatile int count vẫn không làm cho count++ trở thành phép tăng nguyên tử?
A. Volatile chỉ dùng được cho các kiểu tham chiếu
B. Volatile bắt buộc chạy trong synchronized block
C. Volatile làm compiler bỏ qua phép tăng count
D. Volatile bảo đảm visibility, không gộp đọc-ghi
Đáp án đúng: D

Câu 13. Xóa phần tử trực tiếp từ ArrayList trong vòng for-each có nguy cơ nào và nên sửa gì?
A. Tràn stack; đổi vòng lặp sang recursion
B. ConcurrentModification; dùng Iterator.remove
C. Đua dữ liệu; chỉ thêm khóa vào biến lặp
D. Mất encoding; đọc collection bằng UTF-8
Đáp án đúng: B

Câu 14. Hai thread giữ khóa A và B theo thứ tự ngược nhau có nguy cơ deadlock. Cách giảm nguy cơ?
A. Tăng độ ưu tiên của cả hai thread
B. Đưa mọi phép truy cập vào biến volatile
C. Quy định thứ tự lấy khóa giống nhau
D. Gọi Thread.sleep ngay sau khi lấy khóa
Đáp án đúng: C

Câu 15. Truy vấn SQL ghép trực tiếp input người dùng vào câu lệnh nên được sửa thế nào?
A. Escape mọi ký tự bằng thay thế chuỗi tùy ý
B. Dùng câu lệnh tham số hóa qua PreparedStatement
C. Chỉ kiểm tra input trên giao diện trình duyệt
D. Ghi input ra log trước khi thực hiện truy vấn
Đáp án đúng: B

Câu 16. Đường dẫn tệp ghép từ input có thể chứa ../. Biện pháp phòng path traversal phù hợp?
A. Chuẩn hóa và ràng buộc đường dẫn trong thư mục gốc
B. Loại tất cả dấu chấm khỏi tên tệp được cung cấp
C. Chỉ ghi log đường dẫn rồi mở tệp như yêu cầu
D. Đổi tên biến path thành sanitizedPath để theo dõi
Đáp án đúng: A

Câu 17. Khi input không tin cậy được ghép vào chuỗi lệnh shell, cách phòng command injection là gì?
A. Chuyển input về chữ thường trước khi nối lệnh
B. Chỉ kiểm tra độ dài đầu vào sau khi chạy lệnh
C. Bỏ mọi dấu cách rồi thực thi một chuỗi duy nhất
D. Tránh ghép shell, dùng API truyền đối số tách biệt
Đáp án đúng: D

Câu 18. Tool báo null dereference nhưng nhánh đó có invariant đảm bảo non-null. Nên làm gì?
A. Xóa toàn bộ phân tích tĩnh khỏi quy trình build
B. Xem đường đi, chứng minh invariant bằng kiểm thử
C. Ẩn mọi cảnh báo thuộc nhóm nullability
D. Chấp nhận cảnh báo mà không đối chiếu logic
Đáp án đúng: B

Câu 19. Khi xác minh cảnh báo là false positive, cách suppression phù hợp nhất là gì?
A. Tắt toàn bộ nhóm rule cho tất cả module
B. Sửa mã để che lỗi mà không lưu lý do
C. Giới hạn chỗ bỏ qua, ghi lý do và bằng chứng
D. Chuyển tất cả cảnh báo thành mức độ thấp nhất
Đáp án đúng: C

Câu 20. Khi phối hợp SpotBugs, Error Prone và PMD, nhận định nào chính xác?
A. Mọi công cụ luôn dùng đúng một tập quy tắc
B. Mỗi công cụ có thế mạnh và phạm vi cảnh báo riêng
C. Chỉ cần một công cụ sẽ loại hết lỗi runtime
D. Cảnh báo của công cụ luôn là lỗi đã xảy ra
Đáp án đúng: B

Câu 21. Error Prone thường nổi bật ở vị trí tích hợp nào trong quá trình Java build?
A. Phân tích trong bước biên dịch với javac
B. Phân tích sau khi ứng dụng chạy production
C. Phân tích dựa trên báo cáo load testing
D. Phân tích từ log truy cập của web server
Đáp án đúng: A

Câu 22. Nhận định nào mô tả đúng cách SpotBugs phân tích mã?
A. SpotBugs chỉ kiểm tra từ log ứng dụng
B. SpotBugs đòi chương trình phải chạy production
C. SpotBugs chỉ kiểm tra dependency pom.xml
D. SpotBugs đọc bytecode Java đã biên dịch
Đáp án đúng: D

Câu 23. Dự án cũ đã có cảnh báo tĩnh; đưa tool vào CI nên ưu tiên cách nào?
A. Tắt CI cho đến khi xóa hết cảnh báo cũ
B. Tăng độ nghiêm trọng của tất cả cảnh báo
C. Baseline cảnh báo cũ, chặn lỗi mới nghiêm trọng
D. Bỏ qua mọi báo cáo cho đến đợt release
Đáp án đúng: C

Câu 24. Sau khi sửa mã theo một cảnh báo bug pattern, cách kiểm chứng tốt nhất?
A. Tái hiện đường lỗi, chạy test và phân tích lại
B. Xóa rule để báo cáo phân tích không còn lỗi
C. Chỉ so số dòng code trước và sau khi chỉnh
D. Chỉ xác nhận chương trình compile thành công
Đáp án đúng: A
