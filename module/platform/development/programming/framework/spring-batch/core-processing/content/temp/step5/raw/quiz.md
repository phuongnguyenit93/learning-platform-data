Câu 01. Trong Spring Batch, quan hệ đúng giữa Job và Step là gì?
A. Một Step dùng chung JobParameters cho nhiều Job khác
B. Một Step quản lý nhiều JobInstance ở cùng thời điểm
C. Một JobExecution tự tạo Step mà không cần cấu hình
D. Một Job tổ chức luồng thực thi của các Step
Đáp án đúng: D

Câu 02. Yếu tố nào nhận diện một `JobInstance` trong Spring Batch?
A. ID của JobExecution vừa chạy và thời gian kết thúc
B. Số lần retry và số record mà ItemReader đã đọc
C. Tên Step cùng thời gian khởi tạo của batch worker
D. Tên Job cùng các JobParameters được đánh dấu identifying
Đáp án đúng: D

Câu 03. Job thất bại rồi được restart với cùng tham số định danh; quan hệ các lần chạy thế nào?
A. Mỗi lần restart tạo JobInstance với tên khác nhau
B. Một JobInstance có thể có nhiều JobExecution
C. Một JobExecution cũ được tái sử dụng để ghi lại kết quả
D. Các StepExecution được nối sang JobInstance mới
Đáp án đúng: B

Câu 04. Một JobParameters được đánh dấu non-identifying có tác động gì tới danh tính JobInstance?
A. Nó khiến tất cả JobExecution dùng chung một transaction
B. Nó trở thành khóa nhận diện StepExecution trong Job
C. Nó được tự chuyển thành dữ liệu của ExecutionContext
D. Nó không tham gia xác định danh tính của JobInstance
Đáp án đúng: D

Câu 05. Vai trò quan trọng của `JobRepository` khi chạy Spring Batch là gì?
A. Duy trì kết nối tới ItemReader xuyên các lần chạy
B. Thực thi thao tác ghi dữ liệu thay cho ItemWriter
C. Lưu metadata các lần chạy và trạng thái để restart
D. Lưu payload nghiệp vụ thay cho các bảng của hệ thống
Đáp án đúng: C

Câu 06. Một bước chỉ gọi API dọn dữ liệu rồi kết thúc, không đọc từng item; kiểu Step nào phù hợp?
A. Chunk Step cần ItemReader để nhận từng record đầu vào
B. Tasklet Step thực thi công việc tùy biến theo lượt
C. Partition Step chia task thành các dải khóa theo offset
D. Flow Step cần ItemProcessor để điều hướng dữ liệu
Đáp án đúng: B

Câu 07. Trong chunk-oriented processing, thành phần nào xử lý biến đổi từng item trước khi ghi?
A. `ItemProcessor` biến đổi item sau khi Reader cung cấp
B. `JobLauncher` xác thực từng item trước khi commit
C. `ItemReader` thực hiện toàn bộ ghi batch khi đọc xong
D. `ItemWriter` lựa chọn chunk kế tiếp của JobRepository
Đáp án đúng: A

Câu 08. Một Step dùng chunk size 100; ý nghĩa gần đúng của thông số này là gì?
A. Xử lý rồi commit theo nhóm tối đa 100 item trong chunk
B. Quy định mỗi ItemReader trả về một List gồm 100 phần tử
C. Giới hạn JobRepository lưu tối đa 100 lần JobExecution
D. Đặt tổng số item của toàn Job bằng đúng 100 record
Đáp án đúng: A

Câu 09. Với `ItemReader<T>`, giá trị trả về nào thường báo nguồn đã hết dữ liệu?
A. Một item rỗng được truyền tới ItemProcessor tiếp theo
B. `null` từ `read()` biểu thị không còn item để đọc
C. Một `RepeatStatus.FINISHED` được trả từ `read()`
D. Một `Chunk.empty()` được ghi ngay vào ItemWriter
Đáp án đúng: B

Câu 10. Trong chunk step, `ItemProcessor` trả về `null` cho một item; điều gì diễn ra?
A. Item đó bị lọc khỏi dữ liệu đưa sang ItemWriter
B. Item đó được chuyển thành item null khi gọi ItemWriter
C. Item đó được tính là lỗi retry và đọc lại từ đầu
D. Item đó làm chunk rollback rồi kết thúc StepExecution
Đáp án đúng: A

Câu 11. Với Spring Batch phiên bản dùng `Chunk`, `ItemWriter.write` nhận đầu vào nào?
A. Một JobParameters chứa định danh lần chạy cần ghi
B. Một StepContribution chứa thông số cấu hình ItemReader
C. Một JobExecution để cập nhật metadata của JobRepository
D. Một `Chunk` chứa các item đầu ra cần được ghi
Đáp án đúng: D

Câu 12. Điều nào phân biệt item bị filter với item bị skip trong Spring Batch?
A. Filter là reader lỗi; skip là processor trả về null
B. Filter là writer rollback; skip là writer commit bù
C. Filter là processor trả null; skip đi qua cơ chế lỗi
D. Filter là commit lỗi; skip là reader kết thúc dữ liệu
Đáp án đúng: C

Câu 13. ItemWriter ghi dữ liệu DB trong transaction chunk rồi ném exception chưa xử lý; kết quả thông thường?
A. Writer commit phần đã ghi rồi chuyển sang chunk tiếp
B. Reader được coi đã hoàn tất và bỏ qua toàn bộ chunk
C. JobRepository đổi JobParameters để tạo JobInstance mới
D. Transaction chunk bị rollback nếu lỗi không được xử lý
Đáp án đúng: D

Câu 14. Gọi dịch vụ ngoài nhận HTTP 503 tạm thời khi xử lý item; chiến lược fault tolerance nào hợp lý?
A. Tăng chunk size để dịch vụ ngoài xử lý nhanh hơn
B. Retry có backoff và giới hạn lượt cho lỗi tạm thời
C. Chuyển lỗi 503 thành giá trị `null` trong ItemReader
D. Skip dữ liệu và ghi nhận là thành công ngay lần đầu
Đáp án đúng: B

Câu 15. Dữ liệu đầu vào sai định dạng cố hữu, retry không thể sửa được; xử lý nào hợp lý?
A. Skip item theo chính sách và ghi thông tin để rà soát
B. Retry item liên tục để chờ dữ liệu tự đổi định dạng
C. Tăng số partition để biến lỗi parse thành dữ liệu hợp lệ
D. Bật restart để lần chạy mới tự tạo schema khác
Đáp án đúng: A

Câu 16. `skipLimit` trong Step fault-tolerant được dùng để quản lý điều gì?
A. Giới hạn số Step được khởi động trong một JobInstance
B. Giới hạn số commit thành công của mỗi JobExecution
C. Giới hạn số lỗi item được phép skip trong Step
D. Giới hạn thời gian chờ xử lý lỗi của một ItemReader
Đáp án đúng: C

Câu 17. Một lỗi được cấu hình cả retry lẫn skip; khi các lượt retry đã cạn, điều gì có thể xảy ra?
A. JobRepository tự tạo JobInstance mới để thử lại item
B. ItemProcessor được bỏ qua cho các chunk còn lại
C. Item được commit thành công dù Writer vẫn báo lỗi
D. Item có thể được skip nếu còn trong chính sách skip
Đáp án đúng: D

Câu 18. Trong processor có lời gọi trừ tiền qua HTTP ngoài DB transaction; rủi ro khi rollback rồi retry?
A. Giao dịch HTTP được rollback cùng transaction JDBC
B. JobRepository sẽ tự hoàn tiền khi chunk thất bại
C. Spring Batch hủy HTTP request đã gửi trước lượt retry
D. Tác động ngoài DB có thể lặp và cần khóa idempotency
Đáp án đúng: D

Câu 19. Khi cần quyết định skip theo loại và nội dung exception, thành phần nào phù hợp?
A. `JobParameters` định nghĩa cách skip từng hàng lỗi
B. `RetryPolicy` tự ghi item hợp lệ khi Reader bị lỗi
C. `SkipPolicy` xác định có cho phép skip lỗi cụ thể
D. `ItemStream` chỉ định nhóm exception để rollback
Đáp án đúng: C

Câu 20. Một Step phải restart từ điểm đã checkpoint sau lỗi; ItemReader có state nên hỗ trợ gì?
A. Lưu vị trí đọc vào ExecutionContext ở checkpoint
B. Chỉ dựa vào bộ nhớ của ItemReader trong JVM trước
C. Đổi tên Job để dữ liệu bắt đầu từ offset mới
D. Đặt vị trí đọc trong ThreadLocal của worker đang chạy
Đáp án đúng: A

Câu 21. `ExecutionContext` của Spring Batch được sử dụng chủ yếu cho mục đích gì?
A. Lưu transaction đang mở giữa nhiều ItemWriter
B. Thay thế các tham số identifying của JobInstance
C. Lưu state dạng key-value phục vụ khôi phục tiến độ
D. Định nghĩa kiểu dữ liệu Java đầu vào của ItemReader
Đáp án đúng: C

Câu 22. Trong hợp đồng `ItemStream`, phương thức nào thường lưu checkpoint state khi xử lý chunk?
A. `read()` ghi trực tiếp trạng thái của JobRepository
B. `update(ExecutionContext)` cập nhật state cần lưu
C. `close()` chuyển offset vào JobParameters identifying
D. `open(ExecutionContext)` ghi các dữ liệu vừa commit
Đáp án đúng: B

Câu 23. Một Job đã `COMPLETED`; chạy lại tên Job và identifying parameters cũ bằng JobLauncher thường ra sao?
A. JobInstance hoàn tất nên launcher từ chối chạy lại
B. JobParameters cũ tự tăng một đơn vị ở mỗi lần launcher
C. JobExecution trước đó bị reset để chạy lại từ đầu
D. JobInstance cũ tạo StepExecution mới với status STARTED
Đáp án đúng: A

Câu 24. Muốn xử lý ngày mới như một JobInstance khác, cách dùng JobParameters nào đúng?
A. Giữ ngày cũ và đổi giá trị một tham số non-identifying
B. Truyền tham số ngày identifying với giá trị khác
C. Chỉ đổi tên ItemReader bên trong cấu hình Step
D. Chỉ chỉnh timeout của JobLauncher trước khi chạy
Đáp án đúng: B

Câu 25. Để lấy JobParameters vào cấu hình ItemReader theo từng lần chạy, bean nên dùng scope nào?
A. `@Prototype` để sao chép JobInstance khi mỗi item tới
B. `@Singleton` để giữ tham số của JobExecution đầu tiên
C. `@Configuration` để truyền tham số qua field static
D. `@StepScope` để late-bind giá trị tham số khi Step chạy
Đáp án đúng: D

Câu 26. Step đang restart và ItemReader cần đọc lại checkpoint đã lưu; bước nào thích hợp?
A. Dùng ExitStatus để suy ra offset từ tên Job
B. Khôi phục state từ ExecutionContext khi `open`
C. Tạo `JobInstance` mới để reset checkpoint
D. Đặt lại `readCount` về 0 trước khi chạy tiếp
Đáp án đúng: B

Câu 27. Trong `StepExecution`, thống kê nào phản ánh tiến độ xử lý item?
A. `gridSize`, `chunkSize` và tên JobParameters
B. `poolSize`, `threadPriority` và số consumer
C. `readCount`, `writeCount` và số lượng skip
D. `exitCode`, `cronExpression` và tên scheduler
Đáp án đúng: C

Câu 28. Sự khác biệt giữa `BatchStatus` và `ExitStatus` trong Spring Batch là gì?
A. BatchStatus mô tả trạng thái chạy; ExitStatus dùng cho flow
B. BatchStatus lưu checkpoint; ExitStatus quyết định số retry
C. BatchStatus chọn Reader; ExitStatus giữ tất cả JobParameters
D. BatchStatus xác định chunk size; ExitStatus là transaction ID
Đáp án đúng: A

Câu 29. Muốn chạy Step B chỉ khi Step A trả exit code `COMPLETED WITH SKIPS`, nên dựa vào gì?
A. Đổi JobParameters để mỗi Step tự khởi chạy Step B
B. Điều kiện chuyển luồng dựa trên ExitStatus của Step A
C. Chuyển flow theo tên ItemWriter đã chạy trong Step A
D. Kiểm giá trị chunkSize của Step A trước khi tạo Job
Đáp án đúng: B

Câu 30. Với Step A thành công rồi Step B thất bại, restart Job thường xử lý Step A thế nào?
A. Chạy lại Step A trong một JobInstance vừa tạo mới
B. Rollback các commit của Step A ở lần chạy trước
C. Bỏ qua Step A đã hoàn tất nếu không bật chạy lại
D. Đổi Step A thành Tasklet trước khi thực thi Step B
Đáp án đúng: C

Câu 31. Trong partitioned Step, `Partitioner` cung cấp gì cho các worker?
A. Một ItemWriter đồng bộ ghi cho tất cả partition từ xa
B. Một JobInstance mới cho từng record dữ liệu vừa nhận
C. Các ExecutionContext riêng mô tả phần dữ liệu mỗi partition
D. Một transaction dùng chung cho tất cả các StepExecution
Đáp án đúng: C

Câu 32. Chia xử lý theo `customerId` range, làm gì để tránh ghi/đọc trùng giữa partition?
A. Gán các dải dữ liệu không chồng nhau cho từng partition
B. Ghi trực tiếp chung vào cùng vùng file không có khóa
C. Đổi executionId sau mỗi chunk để bỏ kiểm tra dải
D. Để các partition đọc chung toàn bộ bảng rồi tự lọc sau
Đáp án đúng: A

Câu 33. Khi tăng xử lý song song bằng multi-threaded Step, rủi ro cần kiểm tra trước?
A. Reader và Writer chia sẻ state có thể không thread-safe
B. JobRepository sẽ mất khả năng tạo StepExecution mới
C. BatchStatus không còn được lưu sau Step hoàn tất
D. JobParameters identifying tự đổi giữa các thread
Đáp án đúng: A

Câu 34. So với partitioning, split flow chủ yếu song song ở cấp nào?
A. Chạy lại một ItemReader ở nhiều transaction lồng nhau
B. Chia bản ghi của một chunk theo khóa partition
C. Chạy đồng thời các nhánh flow/Step độc lập
D. Tạo lại metadata của mỗi JobInstance khi commit
Đáp án đúng: C

Câu 35. Khi Step ghi file và DB qua hai hệ tài nguyên không cùng transaction, cần lưu ý gì?
A. Writer file đồng bộ commit với transaction JDBC
B. JobRepository bảo đảm atomicity giữa file và DB
C. Transaction JDBC sẽ tự rollback nội dung đã ghi ra file
D. Rollback một bên không bảo đảm đảo ngược bên còn lại
Đáp án đúng: D

Câu 36. Khi cần dừng Job đang chạy qua `JobOperator.stop`, kỳ vọng hợp lý nào?
A. Yêu cầu dừng để job kết thúc ở điểm an toàn phù hợp
B. Buộc JVM dừng và hủy dữ liệu tại transaction hiện tại
C. Xóa metadata JobExecution ngay khi có lệnh dừng
D. Bắt đầu JobInstance mới rồi chuyển toàn bộ state sang
Đáp án đúng: A

Câu 37. Trong test Spring Batch, `@SpringBatchTest` hỗ trợ chủ yếu điều gì?
A. Chuyển các Step chunk thành Tasklet trước khi chạy
B. Thay tất cả ItemReader bằng một bộ dữ liệu ngẫu nhiên
C. Cung cấp tiện ích để chạy Job hoặc Step khi kiểm thử
D. Tạo fixture và reset DB ngay cả khi thiếu cấu hình
Đáp án đúng: C

Câu 38. Muốn kiểm riêng một Step của Job trong integration test, tiện ích nào có thể sử dụng?
A. `StepExecution.getStepName` để chạy Step đích
B. `JobLauncherTestUtils.launchStep` để chạy Step đích
C. `ItemWriter.writeStep` để chạy Step đích
D. `JobRepositoryTestUtils.launchStep` để chạy Step đích
Đáp án đúng: B

Câu 39. Một bài test restart cho Job cần chứng minh điều gì để bắt lỗi duplicate processing?
A. Chỉ số CPU của lần chạy lại thấp hơn lần chạy ban đầu
B. JobInstance mới được tạo sau mỗi lần fail của một Step
C. Chunk size thay đổi sau restart để tránh dữ liệu cũ
D. Dữ liệu cuối đúng và không bị ghi trùng sau lần chạy lại
Đáp án đúng: D

Câu 40. Theo dõi batch production nên kết hợp nhóm chỉ số nào để phát hiện suy giảm hiệu năng?
A. Số worker hiện có, heap và CPU nhưng thiếu tiến độ item
B. Throughput, read/write/skip, retry, lỗi và thời gian Step
C. Số JobInstance, số Step cấu hình và lịch chạy Job
D. Số commit dự kiến, số partition và kích thước chunk
Đáp án đúng: B
