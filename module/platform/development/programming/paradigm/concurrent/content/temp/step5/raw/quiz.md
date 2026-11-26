Câu 1. Trên máy chỉ có một lõi CPU, ứng dụng vẫn có concurrency khi nào?
A. Các tác vụ phải cùng thực thi tại một thời điểm.
B. Xen kẽ lịch chạy để các tác vụ cùng tiến triển.
C. Mỗi tác vụ được gắn riêng một lõi CPU vật lý.
D. Chương trình chỉ có thể xử lý một tác vụ đến hết.
Đáp án đúng: B

Câu 2. Điều nào mô tả đúng parallelism trong một ứng dụng nhiều tác vụ?
A. Các tác vụ chỉ cần bắt đầu vào những thời điểm khác nhau.
B. Các tác vụ buộc phải sử dụng hàng đợi để trao đổi dữ liệu.
C. Có tác vụ chạy đồng thời trên các lõi xử lý khác nhau.
D. Các tác vụ phải cùng ghi một biến chia sẻ trong bộ nhớ.
Đáp án đúng: C

Câu 3. Hai thread cùng đọc counter bằng 5 rồi mỗi thread ghi lại 6; giá trị cuối có thể là bao nhiêu?
A. Có thể là 6 do hai phép ghi cùng dựa trên giá trị cũ.
B. Giá trị 5 vì thao tác tăng không ghi ngược vào biến.
C. Giá trị 7 vì hai phép tăng đều được ghi nhận riêng.
D. Giá trị 10 vì hai thread cộng dồn giá trị đã đọc.
Đáp án đúng: A

Câu 4. Trong Java Memory Model, trường hợp nào minh họa data race trên một field?
A. Hai thread truy cập field xung đột mà thiếu happens-before.
B. Hai thread chỉnh các biến local độc lập của từng thread.
C. Hai thread đọc và ghi nhưng đã đồng bộ bằng cùng monitor.
D. Hai thread chỉ đọc cùng một field final đã khởi tạo hợp lệ.
Đáp án đúng: A

Câu 5. Khi các worker chỉ cần đọc chung cấu hình, cách nào giảm rủi ro chia sẻ trạng thái?
A. Đổi biến cấu hình thành static để các thread thấy nhau.
B. Cho các worker cùng cập nhật HashMap không đồng bộ.
C. Chia sẻ snapshot bất biến thay cho object mutable.
D. Truyền cùng ArrayList mutable rồi tránh tạo bản sao.
Đáp án đúng: C

Câu 6. Khi một thread ghi `volatile boolean stopped = true`, điều gì được bảo đảm cho lần đọc volatile theo sau?
A. Thread đọc phải chạy trên cùng CPU core với thread ghi.
B. Ghi volatile happens-before lần đọc volatile sau đó.
C. Volatile khóa monitor bao quanh toàn bộ method.
D. Phép ghi biến mọi thao tác trên object thành transaction.
Đáp án đúng: B

Câu 7. Vì sao `volatile int count` không làm cho biểu thức `count++` trở thành atomic?
A. Toán tử ++ trên volatile bị compiler bỏ đi lúc tối ưu.
B. Phép tăng là chuỗi đọc, tính và ghi có thể bị xen kẽ.
C. Volatile chỉ được khai báo cho kiểu tham chiếu object.
D. Phép tăng tự khóa biến nhưng không khóa phần đọc.
Đáp án đúng: B

Câu 8. Với hai critical section dùng cùng monitor, quan hệ happens-before nào đúng?
A. Lần unlock trước happens-before lần lock sau trên monitor đó.
B. Unlock chỉ đồng bộ các biến final và bỏ qua biến mutable.
C. Thread không giữ monitor vẫn thấy các ghi trong critical section.
D. Hai lần lock trên hai monitor khác nhau có thứ tự cố định.
Đáp án đúng: A

Câu 9. Khi thread cha gọi `Thread.start()` sau khi cập nhật dữ liệu, quan hệ nào giúp thread con thấy dữ liệu?
A. Start buộc thread cha hoàn thành hết công việc trước thread con.
B. Start làm các biến mutable của cha trở thành biến local của con.
C. Thread con chỉ thấy giá trị mới nếu gọi thêm Thread.sleep.
D. Các ghi trước `start()` happens-before hành động thread con.
Đáp án đúng: D

Câu 10. Sau khi `worker.join()` trả về bình thường, Java Memory Model bảo đảm điều gì?
A. Worker vẫn được phép chạy tiếp cùng phần code trước join.
B. Hành động của worker happens-before đoạn sau `join()`.
C. Join xóa mọi ghi trên heap của worker khỏi cache CPU.
D. Join tự tạo monitor dùng chung cho các object do worker ghi.
Đáp án đúng: B

Câu 11. Với `ReentrantLock lock`, cách nào bảo đảm nhả lock khi code trong critical section ném lỗi?
A. Chờ garbage collector tự nhả lock sau khi method kết thúc.
B. Gọi `unlock()` trong `finally` sau khi đã lock thành công.
C. Gọi `unlock()` trước code cần bảo vệ để tránh khóa kéo dài.
D. Gọi `unlock()` trong `catch` chỉ khi exception xuất hiện.
Đáp án đúng: B

Câu 12. Khi lock đang bị thread khác giữ, `ReentrantLock.tryLock()` không tham số sẽ làm gì?
A. Đợi theo timeout mặc định rồi hủy task đang giữ lock.
B. Ném IllegalMonitorStateException để báo lock đang bận.
C. Trả false ngay nếu thread khác đang giữ lock.
D. Chờ đến khi lock rảnh rồi mới trả về false.
Đáp án đúng: C

Câu 13. Hai tác vụ đôi lúc deadlock do lấy lock A và B theo thứ tự đảo nhau; biện pháp nào phù hợp?
A. Tăng mức ưu tiên của thread đang giữ lock B.
B. Thêm thời gian sleep vào giữa các lần lấy lock.
C. Đổi tên của hai lock để tránh truy cập đồng thời.
D. Quy định cùng một thứ tự lấy lock ở hai tác vụ.
Đáp án đúng: D

Câu 14. Khi thread gọi `condition.await()` trong lúc đang giữ ReentrantLock tương ứng, điều gì xảy ra?
A. Thread thoát khỏi method và không thể lấy lại lock.
B. Thread chuyển sang đợi trên monitor của object Condition.
C. Tạm nhả lock để chờ rồi lấy lại trước khi trở về.
D. Thread giữ lock liên tục suốt thời gian đợi signal.
Đáp án đúng: C

Câu 15. Với `AtomicInteger counter`, kết quả của `counter.getAndIncrement()` là gì?
A. Trả giá trị cũ nhưng yêu cầu lock ngoài khi tăng.
B. Trả giá trị mới bằng cách tạo một AtomicInteger khác.
C. Trả giá trị cũ và tăng counter bằng thao tác atomic.
D. Trả giá trị mới và tăng counter bằng thao tác atomic.
Đáp án đúng: C

Câu 16. Với `AtomicInteger a`, `a.compareAndSet(4, 7)` trả true khi nào?
A. Giá trị đang có khác 4 nên không cần ghi vẫn trả true.
B. Khi giá trị đang là 4 và cập nhật thành 7 thành công.
C. Giá trị đang có lớn hơn 4 và được thay bằng 7.
D. Giá trị đang có là 7 và phép cập nhật thành 4 thành công.
Đáp án đúng: B

Câu 17. Trong một thuật toán CAS, hiện tượng ABA có ý nghĩa nào?
A. Trạng thái A đổi sang B rồi về A, CAS vẫn có thể thành công.
B. CAS báo thất bại nếu trước đó trạng thái từng là B.
C. AtomicInteger tăng số phiên bản ngầm khi đổi A sang B.
D. CAS nhận ra lần đổi A-B-A nhờ timestamp được lưu nội bộ.
Đáp án đúng: A

Câu 18. Với `LongAdder` đang bị nhiều thread cập nhật, `sum()` có giới hạn nào cần nhớ?
A. Tổng luôn khóa các ô đếm trước khi trả về cho caller.
B. Tổng được tính bằng cách ngừng các thread cập nhật trước.
C. Tổng chỉ phản ánh số lần tăng từ một thread hiện tại.
D. Tổng không bảo đảm snapshot nguyên tử khi đang cập nhật.
Đáp án đúng: D

Câu 19. `Callable<T>` khác `Runnable` theo đặc điểm nào của hợp đồng tác vụ?
A. `call()` không thể phát ra kết quả cho thread gọi.
B. `call()` trả T và được khai báo ném checked exception.
C. `run()` buộc phải được khai báo throws Exception.
D. `run()` trả T và có thể khai báo checked exception.
Đáp án đúng: B

Câu 20. Với `Future<Integer> f` có task thất bại, `f.get()` thường biểu hiện lỗi ra sao?
A. Trả null và bỏ qua exception đã phát sinh ở task.
B. Ném ExecutionException chứa nguyên nhân từ task.
C. Trả một Future mới chứa lỗi để xử lý sau.
D. Chạy lại task trên thread đang gọi get rồi trả kết quả.
Đáp án đúng: B

Câu 21. Khi gọi `future.cancel(true)` trên task đang chạy, kết luận nào phù hợp?
A. Task phải dừng ngay cả khi code không kiểm tra interrupt.
B. Future tự khởi chạy lại task nếu interrupt thất bại.
C. Có thể yêu cầu interrupt nhưng task chưa chắc dừng kịp.
D. Task hoàn thành xong rồi mới nhận yêu cầu hủy từ Future.
Đáp án đúng: C

Câu 22. `ExecutorService.shutdown()` tác động đến các task đã submit như thế nào?
A. Ngừng nhận task mới, cho task cũ tiếp tục chạy.
B. Xóa mọi kết quả Future của các task đã hoàn tất.
C. Hủy tức thì tất cả task đã gửi dù đang thực thi.
D. Tiếp tục nhận task mới đến khi số thread về không.
Đáp án đúng: A

Câu 23. Khi một callback trả `CompletableFuture<T>`, phép nào giúp tránh Future lồng nhau trong chuỗi bước async?
A. Dùng `whenComplete` để thay giá trị bằng null.
B. Dùng `thenApply` để giữ nguyên Future trong Future.
C. Dùng `thenCompose` để ghép các giai đoạn async.
D. Dùng `join` để biến pipeline thành một luồng mới.
Đáp án đúng: C

Câu 24. Với `ExecutorCompletionService<T>`, `take()` nhận kết quả theo nguyên tắc nào?
A. Lấy Future của task có mức ưu tiên thread cao nhất.
B. Lấy Future theo thứ tự ban đầu mà task được submit.
C. Lấy Future của task chưa chạy để kích hoạt nó.
D. Nhận Future đã hoàn thành từ hàng đợi kết quả.
Đáp án đúng: D

Câu 25. Virtual threads trên Java hiện đại đặc biệt hữu ích cho kiểu tác vụ nào?
A. Nhiều request chờ I/O blocking và cần khả năng mở rộng số task.
B. Một vòng lặp mã hóa chiếm CPU liên tục và không chờ I/O.
C. Một kernel SIMD cần dành riêng carrier thread theo mỗi phần tử.
D. Một task CPU-bound đơn lẻ cần tính toán nhanh hơn trên một core.
Đáp án đúng: A

Câu 26. `Executors.newVirtualThreadPerTaskExecutor()` tổ chức việc chạy task ra sao?
A. Mỗi task được thực thi bằng một virtual thread riêng.
B. Mỗi task giữ riêng một OS thread đến khi hoàn tất.
C. Các task chia sẻ đúng một virtual thread xuyên suốt.
D. Các task chuyển thành callback không chạy trên thread.
Đáp án đúng: A

Câu 27. Khi virtual threads tạo hàng nghìn truy vấn đồng thời vào DB có pool kết nối nhỏ, nên điều tiết thế nào?
A. Dùng Thread.stop để loại request khi hết kết nối.
B. Pool virtual threads theo kích thước bằng số CPU core.
C. Tăng số virtual threads đến khi mỗi truy vấn có kết nối.
D. Dùng semaphore hoặc connection pool để giới hạn tải.
Đáp án đúng: D

Câu 28. Khi kiểm thử thứ tự tương tác giữa hai thread, cơ chế nào đáng tin hơn việc chèn `Thread.sleep` tùy ý?
A. Tăng mức ưu tiên của thread rồi giả định lịch chạy ổn định.
B. Dùng vòng lặp bận để giữ hai thread trên cùng CPU core.
C. Đếm số log được in ra mà không có tín hiệu đồng bộ.
D. Dùng CountDownLatch để phối hợp các mốc trong test.
Đáp án đúng: D

Câu 29. Trong thiết kế structured concurrency, ý nghĩa chính của việc ràng buộc child task vào scope cha là gì?
A. Child task gắn vòng đời với scope của tác vụ cha.
B. Child task tồn tại độc lập kể cả khi scope của cha đã đóng.
C. Child task được chạy nối tiếp để không thể có race condition.
D. Child task tự động nhận quyền ghi mọi biến của thread cha.
Đáp án đúng: A

Câu 30. Khi nhiều child task cùng phục vụ một request, structured concurrency giúp xử lý thất bại ở cấp scope như thế nào?
A. Các nhánh thất bại được retry vô điều kiện trước khi kết thúc.
B. Các lỗi child task được âm thầm bỏ qua để request thành công.
C. Mọi child task phải hoàn thành trước khi scope báo lỗi.
D. Scope có thể quản lý lỗi và hủy nhánh theo chính sách.
Đáp án đúng: D

Câu 31. Trong hệ thống actor dùng message passing, cách nào giảm rủi ro race trên trạng thái nghiệp vụ?
A. Các actor cùng sửa một HashMap mutable mà không có khóa.
B. Các actor chia sẻ trực tiếp field mutable để giảm số message.
C. Mỗi actor giữ trạng thái riêng và nhận message bất biến.
D. Mỗi message được phép thay đổi nội dung sau khi đã gửi đi.
Đáp án đúng: C

Câu 32. Một producer gửi nhanh hơn consumer xử lý qua queue có dung lượng giới hạn; cơ chế nào thể hiện backpressure?
A. Queue tự tăng bộ nhớ không giới hạn để producer không chờ.
B. Producer tạo thread mới cho mỗi message bất kể queue đầy.
C. Consumer bỏ cơ chế xác nhận để luôn nhận nhanh hơn producer.
D. Queue đầy khiến producer chờ hoặc bị từ chối gửi.
Đáp án đúng: D
