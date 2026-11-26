Câu 1. Khai báo nào định nghĩa đúng một sealed interface Java 17 và các subtype được phép triển khai?
A. `sealed interface Shape implements Circle, Square { }`.
B. `final interface Shape permits Circle, Square { }`.
C. `sealed interface Shape permits Circle, Square { }`.
D. `interface Shape extends Circle, Square { }`.
Đáp án đúng: C

Câu 2. Một class trực tiếp kế thừa sealed class phải khai báo modifier nào phù hợp?
A. Chọn một trong `native`, `strictfp` hoặc `synchronized`.
B. Chọn một trong `public`, `private` hoặc `protected`.
C. Chọn một trong `static`, `volatile` hoặc `transient`.
D. Chọn một trong `final`, `sealed` hoặc `non-sealed`.
Đáp án đúng: D

Câu 3. Điều gì xảy ra khi `class Rogue extends Base` nhưng `Rogue` không nằm trong `permits` của sealed `Base`?
A. Base được đổi thành non-sealed khi Rogue được nạp lần đầu.
B. Compiler từ chối vì Rogue không được phép kế thừa trực tiếp.
C. Rogue trở thành permitted subclass nhờ public constructor.
D. JVM sẽ cho phép Rogue chạy nếu class nằm trên classpath.
Đáp án đúng: B

Câu 4. Trong một named module JPMS, các subtype trực tiếp được `permits` của sealed type phải nằm ở đâu?
A. Trong cùng file `.java` với sealed type tại mọi thời điểm.
B. Trong cùng named module với sealed type được khai báo.
C. Trong module `java.base` để JVM xác minh quan hệ thừa kế.
D. Trong cùng package kể cả khi thuộc named module khác.
Đáp án đúng: B

Câu 5. Với `sealed interface Event permits Click {}`, `record Click(int x) implements Event {}` có thể hợp lệ vì sao?
A. Record là final ngầm định nên thỏa ràng buộc subtype trực tiếp.
B. Record tự động có modifier non-sealed khi implements interface.
C. Record có thể extends mọi sealed class nếu có canonical constructor.
D. Record không cần được liệt kê trong permits của sealed interface.
Đáp án đúng: A

Câu 6. Nếu `non-sealed class Plugin extends Base` được Base cho phép, các subclass của Plugin sẽ thế nào?
A. Phải là final dù Plugin đã được khai báo non-sealed.
B. Phải xuất hiện thêm trong danh sách permits của sealed Base.
C. Không thể extends Plugin vì non-sealed chặn các subtype mới.
D. Có thể tiếp tục extends Plugin theo luật kế thừa thông thường.
Đáp án đúng: D

Câu 7. Khi muốn kiểm tra một Class có biểu diễn sealed type hay không, reflection API nào phù hợp?
A. `clazz.isSynthetic()` cho biết Class có sealed modifier.
B. `clazz.isInterface()` cho biết Class có sealed modifier.
C. `clazz.isRecord()` cho biết Class có sealed modifier.
D. `clazz.isSealed()` cho biết Class có sealed modifier.
Đáp án đúng: D

Câu 8. Khi cần liệt kê các subtype trực tiếp được phép của sealed class bằng reflection, API nào phù hợp?
A. `clazz.getDeclaredClasses()` trả các subclass kế thừa trực tiếp.
B. `clazz.getNestMembers()` trả danh sách type trong permits.
C. `clazz.getPermittedSubclasses()` trả các Class được khai báo cho phép.
D. `clazz.getInterfaces()` trả danh sách tất cả permitted subclasses.
Đáp án đúng: C

Câu 9. Khác biệt giữa `final class` và `sealed class` trong Java là gì?
A. Final chỉ hạn chế override; sealed cho phép mọi subtype.
B. Final chặn kế thừa; sealed giới hạn subtype trực tiếp.
C. Final cho phép extends trong package; sealed chặn toàn bộ extends.
D. Final và sealed đều cho phép kế thừa tự do khi class public.
Đáp án đúng: B

Câu 10. Trong Java 21 trở lên, sealed hierarchy giúp kiểm tra switch pattern theo cách nào?
A. JVM tự biến mọi nhánh sealed thành enum trước khi switch.
B. Compiler có thể chứng minh đủ case dựa trên permitted subclasses.
C. Compiler cần default dù đã bao phủ toàn bộ sealed hierarchy.
D. Compiler chỉ hỗ trợ sealed hierarchy với switch kiểu String.
Đáp án đúng: B

Câu 11. Một `sealed class Base` có bắt buộc được khai báo `abstract` trong Java 17 không?
A. Không; sealed class luôn được compiler đổi thành final.
B. Có; Java 17 chỉ cho phép sealed modifier trên interface.
C. Có; sealed class được xem là abstract ngay khi khai báo.
D. Không; sealed class có thể là concrete và tạo instance.
Đáp án đúng: D

Câu 12. Khi `Child extends Base` nhưng Base không sealed, việc ghi `non-sealed class Child` thường gây gì?
A. Child sẽ tự động được thêm vào danh sách permitted types.
B. Child sẽ trở thành final và không còn cho phép extends.
C. JVM tự bỏ modifier non-sealed khi Child được load.
D. Lỗi compile vì non-sealed đòi direct supertype sealed.
Đáp án đúng: D

Câu 13. API được Java 17 bổ sung để trừu tượng hóa nhiều bộ sinh số giả ngẫu nhiên là gì?
A. `java.security.SecureRandom` là interface của các bộ LXM.
B. `java.util.stream.Collector` là giao diện bộ sinh ngẫu nhiên.
C. `java.util.random.RandomGenerator` là giao diện chung.
D. `java.util.concurrent.Future` là giao diện generator chung.
Đáp án đúng: C

Câu 14. Muốn chọn thuật toán LXM cụ thể khi tạo generator cho mô phỏng, cách nào phù hợp?
A. `RandomGeneratorFactory.of("L64X128MixRandom")`.
B. `RandomGeneratorFactory.of("java.util.UUID")`.
C. `RandomGeneratorFactory.of("SecureRandom")`.
D. `RandomGeneratorFactory.of("ThreadLocalRandom")`.
Đáp án đúng: A

Câu 15. Khi cần tái lập một phép thử giả ngẫu nhiên, cách cấu hình nào hữu ích?
A. Gọi `RandomGenerator.getDefault()` và bỏ qua seed.
B. Đổi seed ở mỗi lần chạy để giữ nguyên dãy kết quả.
C. Tạo cùng thuật toán generator với cùng seed ở mỗi lần chạy.
D. Dùng `SecureRandom` mặc định rồi so sánh mọi giá trị sinh ra.
Đáp án đúng: C

Câu 16. Với `RandomGenerator g`, lời gọi `g.nextInt(3, 8)` sinh giá trị trong khoảng nào?
A. Từ 4 đến 8, loại cận dưới nhưng gồm cận trên.
B. Từ 3 đến 8, gồm cận dưới và cả cận trên.
C. Từ 3 đến 7, gồm cận dưới và loại cận trên.
D. Từ 4 đến 7, loại cả hai cận của khoảng.
Đáp án đúng: C

Câu 17. Để sinh token bí mật không thể dự đoán từ seed mô phỏng, lớp nào là lựa chọn phù hợp?
A. Dùng `SecureRandom` thay vì generator thống kê thông thường.
B. Dùng `SplittableRandom` vì tính năng split mã hóa token.
C. Dùng `Random` với seed cố định để dễ xác minh token.
D. Dùng `RandomGenerator.getDefault()` vì đạt chuẩn mật mã.
Đáp án đúng: A

Câu 18. Khi chia nhiều nhánh mô phỏng song song, interface Java 17 nào hỗ trợ tạo nhánh generator?
A. `RandomGenerator.LeapableGenerator` cung cấp phương thức fork().
B. `RandomGenerator.ArbitrarilyJumpableGenerator` chỉ hỗ trợ seed.
C. `RandomGenerator.SplittableGenerator` hỗ trợ `split()`.
D. `RandomGenerator.StreamableGenerator` cung cấp copy().
Đáp án đúng: C

Câu 19. Cách nào liệt kê các thuật toán generator có thể dùng thông qua API Java 17?
A. Gọi `RandomGenerator.getDefault().values()` để lấy tên thuật toán.
B. Gọi `RandomGenerator.class.getEnumConstants()` để lấy thuật toán.
C. Gọi `SecureRandom.listEngines()` để lấy tên mọi generator.
D. Gọi `RandomGeneratorFactory.all()` để lấy stream factory.
Đáp án đúng: D

Câu 20. Điều gì cần tránh khi dùng `RandomGenerator.getDefault()` để tái lập benchmark giữa các JDK?
A. Generator mặc định được bảo đảm tương đương SecureRandom.
B. Không dựa vào giả định thuật toán mặc định bất biến theo JDK.
C. Có thể bỏ seed mà vẫn giữ cùng dãy ở mọi lần chạy.
D. Tất cả factory sẽ trả chính xác cùng dãy nếu cùng seed.
Đáp án đúng: B

Câu 21. Thay đổi nào của Java 17 khiến nhiều thư viện cũ phản chiếu API nội bộ JDK gặp lỗi?
A. JVM bỏ mọi kiểm tra module đối với field private.
B. Strong encapsulation chặn truy cập nội bộ chưa được export/open.
C. Java 17 loại bỏ reflection public API khỏi `java.lang.reflect`.
D. Java 17 tự động export tất cả package nội bộ cho classpath.
Đáp án đúng: B

Câu 22. Khi reflection gọi `setAccessible(true)` vào member thuộc JDK package chưa mở, lỗi nào có thể xuất hiện?
A. `InaccessibleObjectException` vì module chưa cho deep reflection.
B. `ArrayStoreException` vì đối tượng reflection sai thành phần.
C. `CloneNotSupportedException` vì module không implement Cloneable.
D. `ClassNotFoundException` vì class đã bị GC dỡ khỏi JVM.
Đáp án đúng: A

Câu 23. Với mã classpath cần deep-reflect vào `java.lang`, JVM flag nào mở đúng package cho unnamed modules?
A. `--add-reads java.base/java.lang=ALL-UNNAMED`.
B. `--add-modules java.base/java.lang=ALL-UNNAMED`.
C. `--add-opens java.base/java.lang=ALL-UNNAMED`.
D. `--patch-module java.base/java.lang=ALL-UNNAMED`.
Đáp án đúng: C

Câu 24. Khi cần truy cập public type thuộc package chưa export tới module client, cờ dòng lệnh nào liên quan?
A. `--add-exports java.base/jdk.internal.misc=app.client`.
B. `--add-modules java.base/jdk.internal.misc=app.client`.
C. `--add-reads java.base/jdk.internal.misc=app.client`.
D. `--add-opens java.base/jdk.internal.misc=app.client`.
Đáp án đúng: A

Câu 25. Đối với `--illegal-access=permit` của các JDK cũ, điều nào đúng trên Java 17?
A. Cờ này không còn mở lại strong encapsulation như trước.
B. Cờ này được đề xuất để cho phép deep reflection dài hạn.
C. Cờ này thay cho tất cả cấu hình `--add-opens` trong JPMS.
D. Cờ này tự chuyển thư viện cũ sang dùng JDK public APIs.
Đáp án đúng: A

Câu 26. Để phát hiện dependency dùng API JDK nội bộ trước khi nâng cấp, lệnh nào hữu ích?
A. Dùng `javap --sealed-classes` trên JAR cần phân tích.
B. Dùng `jdeps --jdk-internals` trên JAR cần phân tích.
C. Dùng `jlink --java-internals` trên JAR cần phân tích.
D. Dùng `jar --open-internals` trên JAR cần phân tích.
Đáp án đúng: B

Câu 27. Cách xử lý lâu dài nào tốt hơn việc mở rộng quyền reflection của JDK trong production?
A. Đổi sang API được hỗ trợ hoặc nâng phiên bản thư viện.
B. Gắn `--add-opens` cho toàn bộ module dù không có nhu cầu.
C. Tắt xác minh bytecode trước khi class loader nạp mã.
D. Chuyển ứng dụng thành unnamed module để bỏ mọi kiểm tra.
Đáp án đúng: A

Câu 28. Khi chẩn đoán CPU và allocation trên JVM Java 17 đang chạy, công cụ nào lấy bản ghi sự kiện JVM?
A. Dùng `jcmd <pid> JFR.start` để khởi tạo JFR recording.
B. Dùng `jar <pid> JFR.start` để trích JFR recording.
C. Dùng `javadoc <pid> JFR.start` để lưu JFR recording.
D. Dùng `javac <pid> JFR.start` để mở JFR recording.
Đáp án đúng: A

Câu 29. Với Java serialization, thành phần nào cho phép lọc object trước khi chấp nhận giải tuần tự?
A. `ObjectStreamField` luôn ngăn object graph quá sâu khi đọc.
B. `ObjectInputFilter` có thể chấp nhận, từ chối hay chưa quyết định.
C. `ObjectOutputStream` tự giới hạn class nhận qua module-info.
D. `Serializable` buộc mỗi class phải khai báo whitelist mặc định.
Đáp án đúng: B

Câu 30. Khi muốn áp dụng filter riêng cho một `ObjectInputStream` trước khi đọc object, API nào phù hợp?
A. `stream.setExternalizableFilter(filter)` đặt filter cho stream.
B. `stream.setDefaultReadObject(filter)` đặt filter cho stream.
C. `stream.setObjectOutputFilter(filter)` đặt filter cho stream.
D. `stream.setObjectInputFilter(filter)` đặt filter cho stream.
Đáp án đúng: D

Câu 31. `ObjectInputFilter.FilterInfo` cung cấp dữ liệu gì để áp chính sách giới hạn payload?
A. Đường dẫn classpath và các exports từ module-info.java.
B. HTTP header, token bảo mật và địa chỉ IP từ socket.
C. Độ sâu object graph, số tham chiếu và kích thước mảng.
D. Phần trăm CPU, số thread và thời gian GC của JVM.
Đáp án đúng: C

Câu 32. Java 17 bổ sung khả năng lọc deserialization theo ngữ cảnh qua API nào?
A. `ObjectInputFilter.Config.setModuleReflectionFactory(...)`.
B. `ObjectInputFilter.Config.setNetworkPacketFilter(...)`.
C. `ObjectInputFilter.Config.setInputClassLoaderFactory(...)`.
D. `ObjectInputFilter.Config.setSerialFilterFactory(...)`.
Đáp án đúng: D
