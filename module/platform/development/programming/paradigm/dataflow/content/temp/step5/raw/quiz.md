Câu 1. Trong dataflow graph, khi nào một tác vụ sẵn sàng chạy?
A. Khi một worker bất kỳ trở nên rảnh trong pool.
B. Khi các tác vụ không phụ thuộc nó cũng đã kết thúc.
C. Khi các đầu vào cần thiết của tác vụ đã sẵn sàng.
D. Khi tác vụ đứng đầu danh sách trong file cấu hình.
Đáp án đúng: C

Câu 2. Trong đồ thị phụ thuộc có cạnh hướng A → B, cạnh đó thường mang ý nghĩa gì?
A. A cần dữ liệu B sinh ra trước khi có thể chạy.
B. B cần dữ liệu hoặc kết quả do A cung cấp.
C. A và B được gán vào chung worker để xử lý.
D. B phải được đặt trước A trong thứ tự topo.
Đáp án đúng: B

Câu 3. Với DAG, điều kiện nào phải đúng trong mọi thứ tự topo đối với cạnh A → B?
A. Nút B phải nằm trước nút A trong thứ tự topo.
B. Hai nút A và B phải khởi chạy đúng cùng thời điểm.
C. Nút A phải nằm trước nút B trong thứ tự topo.
D. Hai nút A và B cần nằm liền kề trong danh sách.
Đáp án đúng: C

Câu 4. Vì sao một chu trình phụ thuộc không thể có thứ tự topo đầy đủ?
A. Có vòng phụ thuộc nên không thể sắp xếp topo.
B. Chu trình khiến mọi nút phải có ít nhất hai đầu ra.
C. Chu trình buộc scheduler chuyển sang worker đơn lẻ.
D. Chu trình biến cạnh có hướng thành cạnh vô hướng.
Đáp án đúng: A

Câu 5. Trong đồ thị A → B và A → C, B và C không phụ thuộc nhau; sau khi A hoàn tất có thể làm gì?
A. B và C có thể chạy cùng lúc nếu đủ tài nguyên.
B. Cho B hoàn thành rồi mới có thể khởi động C.
C. Cho A chạy lại để phát tín hiệu cho nhánh C.
D. Cho C hoàn thành rồi mới có thể khởi động B.
Đáp án đúng: A

Câu 6. Nút D bắt buộc nhận cả đầu ra của B và C; B đã xong còn C chưa xong thì sao?
A. D chạy với dữ liệu B và bỏ trống đầu vào C.
B. D chạy lại B để tạo dữ liệu thay thế cho C.
C. D phải đợi dữ liệu C trước khi được kích hoạt.
D. D được đánh dấu hoàn tất ngay khi B đã xong.
Đáp án đúng: C

Câu 7. Trong DAG có đủ worker và mỗi task có thời lượng cố định, yếu tố nào giới hạn thấp nhất thời gian hoàn thành?
A. Số nút trong đồ thị bất kể quan hệ phụ thuộc.
B. Độ dài thời gian của đường phụ thuộc trọng yếu.
C. Thời lượng của nút đầu tiên theo thứ tự khai báo.
D. Số lượng cạnh nhân với số worker được cấp.
Đáp án đúng: B

Câu 8. Tại nút join cần kết quả của hai nhánh, một nhánh đã thất bại; xử lý nào tránh việc đợi vô hạn?
A. Chuyển trạng thái lỗi tới join và áp dụng chính sách hủy.
B. Tăng worker cho join nhưng bỏ qua tín hiệu nhánh lỗi.
C. Giữ join chờ hai kết quả thành công mà không báo lỗi.
D. Phát kết quả mặc định mà không xác nhận lỗi đầu vào.
Đáp án đúng: A

Câu 9. Pipeline nhiều giai đoạn đạt pipeline parallelism theo cách nào?
A. Một item có thể bỏ qua các stage ở giữa pipeline.
B. Các stage phải xử lý cùng một item đúng đồng thời.
C. Các stage xử lý những item khác nhau cùng lúc.
D. Stage cuối có thể sửa dữ liệu đầu vào của stage đầu.
Đáp án đúng: C

Câu 10. Khi stage B chậm hơn A nhiều và mỗi stage có một worker, thông lượng bền vững bị giới hạn chủ yếu bởi đâu?
A. Stage A quyết định tốc độ vì nó là bước đầu.
B. Số lượng biến local trong cả hai stage xử lý.
C. Thứ tự hai stage được viết trong file cấu hình.
D. Stage B chậm là nút thắt của cả pipeline.
Đáp án đúng: D

Câu 11. Trong hệ thống streaming, latency của một item khác throughput ở điểm nào?
A. Latency và throughput biến đổi cùng tỷ lệ khi tăng buffer.
B. Latency đo worker rảnh; throughput đo kích thước heap.
C. Latency đo thời gian/item, throughput đo số item/giây.
D. Latency đo tổng số item; throughput đo thời gian một item.
Đáp án đúng: C

Câu 12. Nếu producer nhanh hơn consumer trong thời gian dài và buffer không giới hạn, rủi ro chính là gì?
A. Producer tự giảm số lượng item đầu vào theo thời gian.
B. Consumer tự tăng tốc cho khớp tốc độ của producer.
C. Tồn đọng dữ liệu kéo dài có thể làm cạn bộ nhớ hệ thống.
D. Các item cũ tự bị hủy trước khi producer ghi item mới.
Đáp án đúng: C

Câu 13. Trong pipeline dùng queue có dung lượng hữu hạn, cách nào thể hiện backpressure?
A. Producer tiếp tục ghi không giới hạn vào queue đó.
B. Consumer tạm dừng đọc để tăng tồn đọng dữ liệu.
C. Scheduler tăng kích thước mỗi message khi queue đầy.
D. Producer phải chờ hoặc giảm tốc khi downstream đầy.
Đáp án đúng: D

Câu 14. Với chính sách drop-oldest khi queue đầy, ảnh hưởng cần tính đến là gì?
A. Item cũ có thể bị mất trước khi được xử lý.
B. Producer nhận lại item cũ như một giao dịch mới.
C. Queue tự mở rộng để giữ lại toàn bộ item.
D. Consumer sẽ xử lý mỗi item bị loại hai lần.
Đáp án đúng: A

Câu 15. Hai nhánh fan-out chạy song song và cùng nhận object mutable; nguy cơ là gì?
A. Hai nhánh phải chạy nối tiếp trên cùng một thread.
B. Có thể xảy ra data race khi hai nhánh cùng sửa object.
C. Nút fan-out tự đặt lock quanh các field của object.
D. JVM tự sao chép object trước khi chuyển đến từng nhánh.
Đáp án đúng: B

Câu 16. Khi merge hai luồng bất đồng bộ mà không sắp xếp lại, kết quả cần lưu ý điều gì?
A. Thứ tự liên luồng luôn theo lúc các item được tạo ra.
B. Thứ tự item từ hai luồng có thể phụ thuộc lịch phát.
C. Merge tự dùng một khóa mặc định để sắp xếp mọi item.
D. Luồng thứ nhất được phát hết rồi mới tới luồng thứ hai.
Đáp án đúng: B

Câu 17. Trong Reactive Streams, callback nào cấp Subscription cho Subscriber?
A. `onNext(subscription)` được gọi khi đăng ký.
B. `onComplete(subscription)` được gọi khi đăng ký.
C. `onError(subscription)` được gọi khi đăng ký.
D. `onSubscribe(subscription)` cung cấp Subscription.
Đáp án đúng: D

Câu 18. Theo Reactive Streams, giá trị n hợp lệ cho `Subscription.request(n)` là gì?
A. Số long dương biểu thị số item cần yêu cầu.
B. Số âm biểu thị số item phải được phát lại.
C. Số 0 biểu thị yêu cầu nhận item tiếp theo.
D. Giá trị null biểu thị demand không giới hạn.
Đáp án đúng: A

Câu 19. Khi Subscriber gọi `request(0)` trong Reactive Streams, Publisher phải xử lý thế nào?
A. Coi là yêu cầu một item để tiếp tục hoạt động.
B. Báo onError vì giá trị yêu cầu không dương.
C. Phát onComplete ngay dù nguồn còn dữ liệu.
D. Nâng demand lên vô hạn để tránh phải chờ.
Đáp án đúng: B

Câu 20. Subscriber mới yêu cầu 5 item; nếu chưa request thêm, Publisher được phát tối đa bao nhiêu onNext?
A. Không giới hạn do request là tín hiệu gợi ý.
B. Tối thiểu 5 lần kể cả khi nguồn chỉ có 2.
C. Đúng 6 lần để đánh dấu đã hết một lô.
D. Tối đa 5 lần onNext theo demand hiện có.
Đáp án đúng: D

Câu 21. Sau tín hiệu `onComplete`, Publisher được gửi gì tiếp cho cùng Subscriber?
A. Sau onComplete không còn onNext hay terminal signal.
B. Gửi tiếp onNext khi có các item mới đến.
C. Gửi thêm onComplete sau từng batch dữ liệu.
D. Gửi onError nếu xử lý muộn phát sinh lỗi.
Đáp án đúng: A

Câu 22. Một Reactive Streams `Processor` đảm nhiệm vai trò nào trong pipeline?
A. Chỉ lưu message xuống database trước khi trả.
B. Vừa nhận như Subscriber vừa phát như Publisher.
C. Vừa là Subscription vừa là Executor để lập lịch.
D. Chỉ tạo thread để chạy các callback Subscriber.
Đáp án đúng: B

Câu 23. Trong hệ thống phân tán bảo đảm at-least-once, retry có thể dẫn tới tình huống nào?
A. Một message lỗi sẽ không còn được gửi lại.
B. Mỗi message được giao đúng một lần dù có retry.
C. Consumer tự bỏ dữ liệu trùng khi không cấu hình.
D. Một message có thể được giao và xử lý lặp.
Đáp án đúng: D

Câu 24. Để consumer không ghi đơn hàng hai lần khi nhận message lặp, cần tính chất nào?
A. Xử lý idempotent theo ID của giao dịch.
B. Tạo riêng một thread cho mỗi message đến.
C. Ghi một bản ghi mới mỗi lần nhận message.
D. Rút ngắn timeout để retry được kích hoạt sớm.
Đáp án đúng: A

Câu 25. Để phục hồi dataflow worker sau khi crash, checkpoint nên lưu dữ liệu gì?
A. Địa chỉ bộ nhớ của mỗi object trước lỗi.
B. Số lượng thread từng khởi tạo trên worker.
C. Tên method của từng class đã được nạp.
D. Lưu state và tiến độ để có thể khôi phục.
Đáp án đúng: D

Câu 26. Với stateful pipeline ghi cả dữ liệu bên ngoài, exactly-once cần điều gì ngoài retry thông thường?
A. Retry vô hạn mọi message chưa được xác nhận.
B. Chỉ dùng một consumer là có exactly-once.
C. Phối hợp commit hoặc bảo đảm idempotency khi ghi.
D. Tăng số worker để tránh các message trùng.
Đáp án đúng: C

Câu 27. Khi các sự kiện cùng khóa tài khoản vào một partition được xử lý tuần tự, lợi ích gì đạt được?
A. Không cần checkpoint vì đã nhóm theo cùng khóa.
B. Có thể giữ thứ tự tổng giữa tất cả partition.
C. Không thể xảy ra replay sau khi worker bị lỗi.
D. Giữ thứ tự nhận sự kiện của từng tài khoản.
Đáp án đúng: D

Câu 28. Với callback trả `CompletableFuture<U>`, thao tác nào nối kết quả mà không tạo Future lồng nhau?
A. `thenAccept` trả Future<U> từ mọi callback dạng Consumer.
B. `thenApply` giữ Future<U> thành kết quả Future ngoài.
C. `whenComplete` chuyển Future<U> thành giá trị U trực tiếp.
D. `thenCompose` ghép giai đoạn async và làm phẳng kết quả.
Đáp án đúng: D

Câu 29. Hai `CompletableFuture` độc lập tạo hai dữ liệu cho phép tổng hợp; thao tác nào kết hợp khi cả hai xong?
A. `applyToEither` chờ cả hai rồi lấy kết quả cuối.
B. `thenCompose` kết hợp hai nguồn độc lập thành một cặp.
C. `thenCombine` gộp hai kết quả khi đã sẵn sàng.
D. `completeOnTimeout` gộp hai kết quả sau timeout.
Đáp án đúng: C

Câu 30. `CompletableFuture.allOf(a, b)` hoàn tất với loại kết quả nào?
A. `CompletableFuture<List<T>>` chứa các giá trị a và b.
B. `CompletableFuture<Void>`, không gộp đầu ra a và b.
C. `CompletableFuture<T[]>` trả mảng của hai giá trị.
D. `CompletableFuture<T>` trả trực tiếp giá trị cuối b.
Đáp án đúng: B

Câu 31. Khi một `CompletableFuture<T>` hoàn tất ngoại lệ, `exceptionally(fn)` dùng làm gì?
A. Chuyển lỗi thành một giá trị dự phòng kiểu T.
B. Phát lại exception sang mọi thread đang chạy.
C. Giữ Future chưa hoàn tất để chờ lần xử lý tiếp.
D. Tự chạy lại task nguồn từ đầu khi phát lỗi.
Đáp án đúng: A

Câu 32. Trong test dataflow bất đồng bộ, cách nào tái hiện lịch thực thi và race ổn định hơn?
A. Chèn sleep ngẫu nhiên giữa stage rồi đo kết quả.
B. Dùng executor có thể điều khiển và mốc đồng bộ.
C. Lấy thứ tự ghi log console làm điều kiện chính.
D. Giữ cùng số thread nhưng không kiểm tra lịch chạy.
Đáp án đúng: B
