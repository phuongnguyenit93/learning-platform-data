1. Trong quy trình nạp lớp JVM, bước nào kiểm tra bytecode có tuân thủ các ràng buộc an toàn của máy ảo?
A. Verification kiểm tra bytecode trước khi cho phép thực thi.
B. Preparation cấp phát vùng nhớ cho các biến instance của từng object.
C. Initialization thực thi mọi phương thức của class trước khi tạo object.
D. Unloading xóa class khỏi Metaspace ngay sau lần gọi đầu tiên.
Đáp án đúng: A

2. Cơ chế parent delegation của ClassLoader thường có mục đích gì?
A. Để mọi class ứng dụng luôn được nạp bởi system class loader duy nhất.
B. Ưu tiên hỏi parent trước để tránh nạp trùng các class nền tảng trong runtime.
C. Cho phép child loader ghi đè mọi class thuộc bootstrap loader.
D. Đảm bảo class cùng tên luôn chia sẻ static state giữa mọi loader.
Đáp án đúng: B

3. Một class gặp lỗi trong static initializer ở lần khởi tạo đầu tiên. Biểu hiện nào có thể xuất hiện ở lần active use sau?
A. Lần dùng sau có thể báo NoClassDefFoundError.
B. JVM tự chạy lại initializer cho tới khi static field được gán đủ.
C. JVM tạo defining classloader mới cho mọi lần gọi phương thức.
D. JVM chuyển lỗi khởi tạo thành OutOfMemoryError để dừng tiến trình.
Đáp án đúng: A

4. Khi nào hai class có cùng binary name vẫn được JVM xem là hai kiểu khác nhau?
A. Khi hai file class được biên dịch từ hai thư mục source khác nhau.
B. Khi hai class có cùng tên nhưng khai báo các method theo thứ tự khác.
C. Khi chúng được định nghĩa bởi hai defining classloader độc lập khác nhau.
D. Khi chúng được nạp ở hai thời điểm khác nhau bởi cùng loader.
Đáp án đúng: C

5. Vai trò của bytecode verifier là gì?
A. Chọn method nào cần biên dịch native dựa trên số lần gọi.
B. Tối ưu các vòng lặp bằng cách loại bỏ phép tính lặp lại.
C. Phát hiện bytecode sai trước khi chạy.
D. Thu hồi object không còn tham chiếu trong heap của JVM.
Đáp án đúng: C

6. Thread context class loader thường hữu ích trong tình huống nào?
A. Để mỗi thread có một heap riêng khi nạp plugin.
B. Cho phép thư viện nền tìm implementation của ứng dụng qua TCCL.
C. Để thay thế hoàn toàn cơ chế parent delegation của JVM.
D. Để buộc mọi class được nạp lại mỗi lần thread chạy.
Đáp án đúng: B

7. JIT compiler thường chọn method để biên dịch dựa trên yếu tố nào?
A. Profiling nhận diện method nóng cần được biên dịch.
B. Kích thước file JAR chứa method lớn hơn một ngưỡng cố định.
C. Tên method có tiền tố get hoặc set theo quy ước JavaBean.
D. Method được khai báo public và gọi từ nhiều class khác nhau.
Đáp án đúng: A

8. Khi một giả định tối ưu của JIT không còn đúng, deoptimization có thể làm gì?
A. Xóa toàn bộ heap để method được chạy lại từ đầu.
B. Khôi phục trạng thái và tiếp tục ở mức ít tối ưu hơn.
C. Thay defining classloader để method được nạp từ bytecode khác.
D. Dừng mọi thread cho tới khi Code Cache được ghi xuống đĩa.
Đáp án đúng: B

9. Code Cache trong HotSpot chủ yếu lưu trữ dữ liệu nào?
A. Object Java còn sống sau lần young collection gần nhất.
B. Metadata của class và thông tin reflection trong runtime.
C. Bytecode gốc được tải từ mọi JAR trên classpath.
D. Mã máy đã được JIT compiler tạo ra để thực thi.
Đáp án đúng: D

10. Tiered compilation kết hợp những hoạt động nào?
A. Nạp class và giải phóng Metaspace theo tuổi thọ của object.
B. Dùng GC song song ở young generation và old generation.
C. Phân bổ heap theo từng thread để giảm tranh chấp bộ nhớ.
D. Kết hợp profiling với nhiều mức biên dịch tăng dần khi method nóng lên.
Đáp án đúng: D

11. Vì sao latency của ứng dụng Java thường cao hơn trong giai đoạn warmup?
A. JVM chưa cấp phát heap cho các object của ứng dụng.
B. Garbage collector chưa được phép thu gom object nào.
C. Class loading và JIT compilation vẫn đang diễn ra.
D. Các thread ứng dụng chưa được scheduler hệ điều hành nhìn thấy.
Đáp án đúng: C

12. Vùng heap của JVM thường chứa loại dữ liệu nào?
A. Stack frame và biến local riêng của từng thread.
B. Object và array được tạo trong quá trình thực thi.
C. Mã máy do JIT compiler sinh ra cho các method nóng.
D. Native stack dùng khi thread gọi hàm của hệ điều hành.
Đáp án đúng: B

13. Java stack của mỗi thread chủ yếu lưu trữ gì?
A. Object được chia sẻ giữa các thread trong cùng process.
B. Stack frame chứa local variables và operand stack.
C. Các vùng nhớ trực tiếp được cấp phát bởi NIO.
D. Class metadata và constant pool của class đã nạp.
Đáp án đúng: B

14. Trong HotSpot hiện đại, Metaspace chủ yếu được dùng cho mục đích nào?
A. Lưu toàn bộ object Java thuộc old generation.
B. Lưu native code đã biên dịch cho các method nóng.
C. Cấp phát stack riêng cho từng platform thread.
D. Lưu metadata của các class đã được nạp trong vùng native memory.
Đáp án đúng: D

15. OutOfMemoryError: Direct buffer memory thường gợi ý vấn đề nào?
A. Direct buffer đã vượt giới hạn cấp phát cho phép.
B. Số lượng class đã nạp vượt giới hạn của Metaspace.
C. Heap không đủ chỗ cho object được tạo từ Java code.
D. Stack của thread hiện tại không đủ cho lời gọi đệ quy.
Đáp án đúng: A

16. JVM báo Unable to create new native thread dù heap còn dung lượng. Nguyên nhân nào cần kiểm tra?
A. Số object còn sống trong old generation tăng quá nhanh.
B. Code Cache đã hết vùng nhớ dành cho compiled method.
C. Đã chạm giới hạn thread hoặc native resource.
D. Classpath chứa nhiều phiên bản trùng tên của cùng một class.
Đáp án đúng: C

17. StackOverflowError thường liên quan trực tiếp tới tình huống nào?
A. Nhiều object được giữ lại bởi static reference trong heap.
B. Metaspace hết chỗ khi ứng dụng nạp thêm class động.
C. Direct memory bị dùng hết bởi các network buffer.
D. Stack frame quá sâu, thường do đệ quy không dừng.
Đáp án đúng: D

18. Vì sao không nên đặt -Xmx bằng toàn bộ memory limit của container?
A. -Xmx giới hạn tổng RSS, bao gồm cả mọi vùng native của JVM.
B. Cần chừa bộ nhớ cho Metaspace, thread stack, direct buffer và native memory.
C. -Xmx chỉ có tác dụng khi tiến trình chạy ngoài container.
D. Garbage collector luôn nhân đôi heap khi bắt đầu một chu kỳ.
Đáp án đúng: B

19. Trong G1 GC, một object thường được xem là humongous khi kích thước của nó đạt mức nào?
A. Vượt kích thước tối đa của một Java array theo đặc tả.
B. Lớn hơn tổng dung lượng heap đã được cấp cho JVM.
C. Bằng hoặc lớn hơn một nửa kích thước của một G1 region.
D. Lớn hơn dung lượng Eden space còn trống tại thời điểm cấp phát.
Đáp án đúng: C

20. Trong quá trình young collection, điều gì có thể xảy ra với object sống đủ lâu?
A. Object sống lâu có thể được promote sang old generation.
B. Object được chuyển khỏi heap sang Java stack của thread tạo ra nó.
C. Object được biên dịch thành native code bởi JIT compiler.
D. Object được chuyển thành class metadata trong Metaspace.
Đáp án đúng: A

21. GC root có vai trò gì khi JVM xác định object còn reachable?
A. Ghi lại thời điểm object được tạo để tính tuổi thọ chính xác.
B. Đánh dấu các object có kích thước lớn hơn một G1 region.
C. Lưu mọi object đã bị thu gom để phục vụ heap dump sau này.
D. GC roots là điểm bắt đầu để lần theo các object còn reachable.
Đáp án đúng: D

22. Retained size khác shallow size của object như thế nào?
A. Shallow size tính cả mọi object được tham chiếu gián tiếp.
B. Bộ nhớ có thể được giải phóng khi object mất reachability.
C. Shallow size chỉ đo kích thước object trong Java stack.
D. Retained size luôn bằng dung lượng của class trong Metaspace.
Đáp án đúng: B

23. Một heap dump cho thấy dominator tree có một cache giữ nhiều object. Phân tích nào phù hợp?
A. Đếm số thread RUNNABLE để suy ra cache đang bị truy cập.
B. Chỉ so sánh shallow size của các class trong histogram.
C. Lần theo GC roots và tìm dominator giữ retained set lớn nhất.
D. Đổi collector sang ZGC rồi chụp dump mới để xóa tham chiếu.
Đáp án đúng: C

24. Đặc điểm nào mô tả đúng mục tiêu thiết kế của ZGC?
A. Tối đa hóa throughput bằng cách dừng mọi application thread trong phần lớn chu kỳ.
B. Thu gom đồng thời để hướng tới pause time thấp trên heap lớn.
C. Chỉ thu gom young generation và không quản lý object sống lâu.
D. Loại bỏ nhu cầu cấp phát headroom khi ứng dụng tăng tải.
Đáp án đúng: B

25. Khi phân tích GC log để tìm nguyên nhân pause tăng, nên xem xét nhóm dữ liệu nào?
A. Xem loại collection, pause time, heap occupancy và allocation rate.
B. Chỉ tổng số class đã nạp và số lần gọi constructor.
C. Chỉ số thread RUNNABLE và số file descriptor của process.
D. Tên các method trong classpath và thứ tự JAR được nạp.
Đáp án đúng: A

26. Thread dump có thread ở trạng thái BLOCKED thường cho biết điều gì?
A. Thread đang chạy bytecode trên CPU tại thời điểm chụp.
B. Thread đã kết thúc nhưng chưa được process cha thu hồi.
C. Thread đang chờ một socket đọc dữ liệu từ network.
D. Thread chờ lấy monitor đang bị thread khác giữ.
Đáp án đúng: D

27. Dấu hiệu nào trong thread dump hỗ trợ xác định deadlock?
A. Nhiều thread WAITING trên cùng một executor queue.
B. Một thread RUNNABLE có stack trace dài hơn các thread khác.
C. Nhiều thread cùng gọi một method đã được JIT biên dịch.
D. Các thread giữ monitor và chờ khóa do nhau nắm giữ.
Đáp án đúng: D

28. Khi nhiều thread BLOCKED trên cùng một monitor nhưng không tạo chu trình deadlock, vấn đề có thể là gì?
A. Lock contention khiến nhiều thread phải chờ cùng một monitor.
B. Young generation không còn region trống để cấp phát object.
C. Classloader của ứng dụng không thể unload class đã nạp.
D. Code Cache đã hết chỗ lưu compiled method.
Đáp án đúng: A

29. Vì sao ThreadLocal trong thread pool cần được dọn sau mỗi request?
A. ThreadLocal tự động xóa mọi giá trị khi task kết thúc.
B. ThreadLocal lưu object trong Metaspace thay vì heap.
C. Worker tái sử dụng có thể giữ giá trị ThreadLocal.
D. ThreadLocal buộc JVM tạo thread hệ điều hành mới sau mỗi lần get().
Đáp án đúng: C

30. Tác vụ blocking I/O chạy trong ForkJoinPool.commonPool có thể gây rủi ro gì?
A. Làm class metadata bị chuyển khỏi Metaspace trong lúc chờ I/O.
B. Blocking có thể chiếm worker và làm cạn pool.
C. Buộc GC chuyển mọi object sang old generation ngay lập tức.
D. Tự động tạo một platform thread cho mỗi lần gọi blocking.
Đáp án đúng: B

31. Đặc điểm nào phân biệt virtual thread với platform thread?
A. JVM multiplex virtual threads trên carrier threads.
B. Virtual thread không có stack frame và không thể chờ I/O.
C. Platform thread được lập lịch bởi JVM; virtual thread do kernel quản lý.
D. Mỗi virtual thread luôn được ánh xạ cố định tới một native thread.
Đáp án đúng: A

32. Với tài nguyên native như socket hoặc file handle, cách quản lý nào đáng tin cậy?
A. Dùng try-with-resources để đóng tài nguyên có thể đóng tường minh.
B. Chờ Full GC để JVM chắc chắn thu hồi mọi tài nguyên ngoài heap.
C. Giữ reference trong static field để Cleaner không chạy quá sớm.
D. Dựa vào finalize() để đóng tài nguyên ngay sau khi scope kết thúc.
Đáp án đúng: A

33. Java Flight Recorder (JFR) phù hợp nhất cho mục đích nào?
A. Đo chính xác mọi network packet đi qua card mạng của host.
B. Thay thế heap dump bằng bản sao đầy đủ mọi object trong JVM.
C. JFR ghi sự kiện runtime như CPU, allocation và lock.
D. Ghi toàn bộ bytecode trước khi classloader thực hiện verification.
Đáp án đúng: C

34. Khi bật JFR liên tục trên production, điều gì cần cân nhắc?
A. JFR luôn dừng các thread ứng dụng khi ghi.
B. Mọi event JFR đều có chi phí bằng nhau bất kể cấu hình.
C. Chọn event phù hợp để kiểm soát overhead.
D. JFR chỉ có thể ghi dữ liệu khi JVM khởi động với debug mode.
Đáp án đúng: C

35. Vì sao nên tương quan GC log, thread dump và JFR khi điều tra latency spike?
A. Mỗi nguồn dữ liệu chứa cùng một loại thông tin và có thể thay thế nhau.
B. JFR chỉ dùng khi heap dump không thể tạo được trên production.
C. GC log cho biết mọi lock; thread dump cho biết mọi allocation event.
D. Kết hợp pause time, trạng thái thread và runtime event theo thời gian.
Đáp án đúng: D

36. Một JVM có thời gian dừng dài nhưng GC log không ghi nhận GC pause tương ứng. Nên điều tra thêm gì?
A. Số lượng object trong Eden để suy ra mọi safepoint đều do GC.
B. Số JAR trên classpath để tính thời gian dừng của scheduler.
C. Heap dump để xác định trực tiếp thời lượng mọi VM operation.
D. Kiểm tra safepoint log và VM operation ngoài GC.
Đáp án đúng: D
