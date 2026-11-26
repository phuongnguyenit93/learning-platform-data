Câu 1. Với ứng dụng Spring Boot có package gốc `com.acme`, Spring Modulith mặc định nhận diện application module nào?
A. Mỗi bảng dữ liệu của repository được xem là một module.
B. Các package con trực tiếp của `com.acme` tạo thành module.
C. Các dependency Maven được ánh xạ thành application module.
D. Mỗi bean `@Service` bên dưới `com.acme` được xem là module.
Đáp án đúng: B

Câu 2. Lời gọi `ApplicationModules.of(ShopApplication.class)` chủ yếu dùng để làm gì?
A. Chạy tất cả integration test nằm trong từng package module.
B. Đăng ký từng module thành một HTTP service trên mạng.
C. Xây mô hình các application module dựa trên lớp ứng dụng.
D. Khởi động riêng từng module thành một tiến trình Spring Boot.
Đáp án đúng: C

Câu 3. Khi chạy `ApplicationModules.of(ShopApplication.class).verify()`, loại lỗi nào được phát hiện?
A. Phụ thuộc vòng và truy cập module API nội bộ trái phép.
B. Listener xử lý event lâu hơn giới hạn timeout vận hành.
C. Service thiếu transaction khi update nhiều bảng dữ liệu.
D. Controller trả status HTTP sai cho dữ liệu request.
Đáp án đúng: A

Câu 4. Module `orders` phụ thuộc `billing`, còn `billing` lại phụ thuộc `orders`; điều gì xảy ra khi verify?
A. Spring Modulith tự đổi chiều phụ thuộc để tạo đồ thị hợp lệ.
B. Hệ thống tự gom hai module thành một module để chạy tiếp.
C. Module được đổi thành async event nên hết phụ thuộc vòng.
D. Verify báo lỗi chu trình giữa `orders` và `billing`.
Đáp án đúng: D

Câu 5. Một class trong `orders` import class ở subpackage nội bộ của `inventory`; mặc định verify xử lý thế nào?
A. Báo lỗi khi class đích là interface chứ không phải class.
B. Cho phép nếu class đích có annotation `@Component`.
C. Báo vi phạm nếu class không được công bố qua module API.
D. Cho phép vì cả hai package đều nằm trong Spring context.
Đáp án đúng: C

Câu 6. Theo quy ước mặc định, thành phần nào thường thuộc API công khai của application module?
A. Các repository trong package internal vì được Spring tạo proxy.
B. Các kiểu Java trong test package vì có cùng tên module.
C. Các kiểu Java ở mọi subpackage được quét bởi ComponentScan.
D. Các kiểu Java nằm trực tiếp trong base package của module.
Đáp án đúng: D

Câu 7. Muốn công bố một package con làm API có tên của module, Spring Modulith hỗ trợ annotation nào?
A. Gắn `@Import` lên repository nội bộ thuộc package đó.
B. Gắn `@SpringBootApplication` vào một lớp của package đó.
C. Gắn `@ComponentScan` lên `package-info.java` của package đó.
D. Đặt `@NamedInterface` trong `package-info.java` của package.
Đáp án đúng: D

Câu 8. Module `orders` cần phụ thuộc API tên `spi` của `inventory`; ký pháp allowed dependency nào phù hợp?
A. Dùng `allowedDependencies = {"inventory.spi"}`.
B. Dùng `allowedDependencies = {"inventory::spi"}`.
C. Dùng `allowedDependencies = {"spi::inventory"}`.
D. Dùng `allowedDependencies = {"inventory#spi"}`.
Đáp án đúng: B

Câu 9. Mục đích của `@ApplicationModule(allowedDependencies=...)` là gì?
A. Giới hạn những module và named interface được phụ thuộc.
B. Chọn những module tự động khởi động khi API nhận request.
C. Đăng ký những bean repository được phép ghi dữ liệu trong module.
D. Chỉ định các Kafka topic mà module được phép publish event.
Đáp án đúng: A

Câu 10. Module cần bổ sung cấu hình kiến trúc ở cấp package thay vì bean; nơi nào phù hợp?
A. Đặt `@ApplicationModule` trong `package-info.java`.
B. Đặt `@ApplicationModule` trên mỗi field của mọi domain event.
C. Đặt `@ApplicationModule` trong file `application.properties`.
D. Đặt `@ApplicationModule` vào từng method handler trong module.
Đáp án đúng: A

Câu 11. Code biên dịch Java thành công nhưng import API nội bộ từ module khác; nhận định nào đúng?
A. Spring context sẽ tự loại bean vi phạm trước khi test chạy.
B. Compile có thể qua, nhưng `verify()` phát hiện vi phạm.
C. Java compiler tự thực thi verify() và từ chối class internal.
D. Modulith sẽ đổi import thành event để hợp thức phụ thuộc.
Đáp án đúng: B

Câu 12. Muốn CI chặn một commit tạo phụ thuộc vòng, bài test tối thiểu nào phù hợp?
A. Chạy `MockMvc` với một endpoint health và không verify module.
B. Chạy `ApplicationModules.of(App.class).toString()` trong JUnit test.
C. Chạy `@ApplicationModuleTest` mà bỏ kiểm tra phụ thuộc tĩnh.
D. Chạy `ApplicationModules.of(App.class).verify()` trong JUnit test.
Đáp án đúng: D

Câu 13. Tại sao không nên coi riêng `@ApplicationModuleTest` là thay thế cho `ApplicationModules.verify()`?
A. Verify yêu cầu HTTP server thật còn module test kiểm tra graph.
B. Module test kiểm tra runtime, còn `verify()` kiểm tra cấu trúc.
C. Verify chỉ kiểm thử database nên cần module test cho import Java.
D. Module test luôn phát hiện mọi dependency vi phạm dù test không gọi.
Đáp án đúng: B

Câu 14. Để integration test tập trung vào một module Spring Modulith, annotation nào thích hợp?
A. Dùng `@ApplicationModuleTest` cho class test trong module.
B. Dùng `@SpringBootTest` ở mọi class test và bỏ module boundary.
C. Dùng `@DataJpaTest` cho cả gateway, service và event publisher.
D. Dùng `@WebMvcTest` để khởi tạo toàn bộ listener và repository.
Đáp án đúng: A

Câu 15. `@ApplicationModuleTest` thường suy ra module đang được test từ đâu?
A. Từ package của class test thuộc module cần kiểm thử.
B. Từ groupId của message listener đang chạy trong test.
C. Từ tên bean repository được inject vào `ApplicationContext`.
D. Từ tên method test đầu tiên có annotation `@Test`.
Đáp án đúng: A

Câu 16. Bootstrap mode mặc định `STANDALONE` của `@ApplicationModuleTest` có ý nghĩa gì?
A. Khởi động toàn bộ application module và mọi dependency gián tiếp.
B. `STANDALONE` nạp module cần test mà không nạp module khác.
C. Khởi động module được test cùng toàn bộ dependency trực tiếp.
D. Khởi động ứng dụng thành tiến trình khác cho từng module.
Đáp án đúng: B

Câu 17. Khi module cần bean của module phụ thuộc trực tiếp trong test, chọn bootstrap mode nào?
A. Chọn `ALL_DEPENDENCIES` vì nó loại trừ dependency trực tiếp.
B. Chọn `STANDALONE` để tự nạp tất cả dependency bên ngoài.
C. Dùng `DIRECT_DEPENDENCIES` cho module và dependency trực tiếp.
D. Chọn `NONE` để khởi động module mà không tạo Spring context.
Đáp án đúng: C

Câu 18. Bootstrap mode `ALL_DEPENDENCIES` hữu ích trong tình huống nào?
A. Test cần thay mọi bean được inject thành Mockito mock tự động.
B. Test cần chạy tất cả module không phụ thuộc vào module đang test.
C. Test cần module cùng toàn bộ chuỗi dependency được phép của nó.
D. Test cần tắt component scanning và chỉ đọc metadata package.
Đáp án đúng: C

Câu 19. Một module test ở chế độ `STANDALONE` thiếu bean thuộc module khác; hướng xử lý phù hợp là gì?
A. Đổi `ApplicationModules.verify()` thành no-op để bean được tạo.
B. Mock cổng phụ thuộc hoặc chọn bootstrap mode phù hợp.
C. Sửa tên test class để Spring tự sinh bean dependency còn thiếu.
D. Thêm quét toàn ứng dụng để vô hiệu hóa giới hạn module test.
Đáp án đúng: B

Câu 20. Muốn xác minh service phát sự kiện `InvoiceIssued` khi gọi nghiệp vụ, công cụ Modulith nào phù hợp?
A. Inject `PublishedEvents` rồi lọc loại event cần kiểm tra.
B. Inject `ApplicationModules` để lấy danh sách event runtime.
C. Inject `BootstrapMode` để đọc event đã phát trong test.
D. Inject `Documenter` để đợi listener xử lý event runtime.
Đáp án đúng: A

Câu 21. Với `PublishedEvents`, làm sao kiểm tra event đúng `invoiceId` thay vì chỉ kiểm tra kiểu?
A. Dùng annotation `@NamedInterface` để so khớp payload event.
B. Dùng `BootstrapMode.ALL_DEPENDENCIES` để tự assert invoiceId.
C. Dùng lựa chọn event theo type kết hợp predicate trên nội dung.
D. Dùng `ApplicationModules.verify()` để truy vấn invoiceId từ event.
Đáp án đúng: C

Câu 22. Listener xử lý event bất đồng bộ; test muốn đợi kết quả thay vì `Thread.sleep`; dùng gì?
A. Dùng `@Transactional` trên test để mọi listener chuyển sang sync.
B. Dùng `@Order` trên method test để chờ thread async chạy xong.
C. Dùng `PublishedEvents` rồi coi việc publish là listener đã hoàn tất.
D. Dùng `Scenario` của Modulith để chờ event hoặc thay đổi trạng thái.
Đáp án đúng: D

Câu 23. Khi dùng `Scenario` để kiểm thử một nghiệp vụ phát event, bước khởi đầu nào phù hợp?
A. Gọi `Scenario.stimulate(...)` để kích hoạt nghiệp vụ.
B. Gọi `PublishedEvents.ofType(...)` để kích hoạt nghiệp vụ.
C. Gọi `@ApplicationModuleTest` bằng reflection để phát event.
D. Gọi `ApplicationModules.verify()` để tự sinh event runtime.
Đáp án đúng: A

Câu 24. Muốn kiểm thử listener nhận event và cập nhật trạng thái đơn hàng trong DB, nên assert điều gì?
A. Số lần gọi `publishEvent()` mà không đọc dữ liệu sau xử lý.
B. Tên event class trong log thay vì kết quả nghiệp vụ được lưu.
C. Số bean `@EventListener` đã được quét trong ApplicationContext.
D. Trạng thái lưu trong repository sau khi listener xử lý xong.
Đáp án đúng: D

Câu 25. Khi kiểm thử `@TransactionalEventListener` pha `AFTER_COMMIT`, test `@Transactional` rollback mặc định gây gì?
A. Listener chạy trước rollback vì test đã phát event thành công.
B. Listener tự chuyển sang BEFORE_COMMIT để tránh rollback test.
C. Transaction test được commit trước khi mỗi assertion thực hiện.
D. Không có commit thực nên listener AFTER_COMMIT có thể không chạy.
Đáp án đúng: D

Câu 26. Để kiểm chứng listener `AFTER_COMMIT` trong integration test, cách nào phù hợp?
A. Commit giao dịch thật, đợi listener rồi assert dữ liệu.
B. Đọc annotation listener rồi bỏ qua việc ghi database.
C. Bọc toàn bộ test trong transaction rollback mặc định rồi assert.
D. Mock publisher và coi như listener đã xử lý thành công.
Đáp án đúng: A

Câu 27. Tại sao dùng database cùng loại production qua Testcontainers có giá trị trong module test?
A. Giúp thay unit test bằng kiểm thử HTTP mà không tạo repository.
B. Giúp mọi listener thành synchronous ngay sau khi tạo container.
C. Dùng Testcontainers chạy đúng loại database như production.
D. Giúp Modulith tự sửa dependency vòng khi chạy với DB thật.
Đáp án đúng: C

Câu 28. Module có repository và business transaction; integration test nên tập trung xác minh điều gì?
A. Xác minh repository proxy được Spring tạo trong context.
B. Xác minh tên bảng và entity theo convention của package.
C. Kiểm tra Java compiler chấp nhận annotation JPA.
D. Assert dữ liệu commit/rollback và hành vi repository.
Đáp án đúng: D

Câu 29. Nếu module test dùng nhiều phụ thuộc không cần thiết, rủi ro đáng chú ý nhất là gì?
A. Module test tự chuyển thành unit test không dùng Spring context.
B. Java compiler tách test thành nhiều JPMS module khi build.
C. Nhiều phụ thuộc che vi phạm module và làm test chậm, giòn.
D. Mọi dependency được khởi tạo lại dưới scope prototype.
Đáp án đúng: C

Câu 30. Để làm quality gate CI cho kiến trúc module, pipeline nên làm gì?
A. Chạy build thành công rồi bỏ qua test vì compiler đã kiểm module.
B. Chạy generate diagrams rồi bỏ qua các vi phạm phụ thuộc module.
C. Chạy `verify()` và module integration tests làm quality gate.
D. Chạy smoke test HTTP rồi coi đã kiểm tra mọi dependency nội bộ.
Đáp án đúng: C

Câu 31. Khi thay package API một module, bước hồi quy nào quan trọng nhất?
A. Chạy test giao diện của module không liên quan tới thay đổi.
B. Chạy verify và test các consumer sử dụng API bị đổi.
C. Đổi tên module trong hình kiến trúc cho đúng tài liệu.
D. Kiểm tra startup log mà không chạy verify hoặc test module.
Đáp án đúng: B

Câu 32. Sau khi verify kiến trúc PASS, điều gì vẫn cần kiểm chứng bằng test chạy thật?
A. Việc truy cập package internal vì verify bỏ qua dependency.
B. Hành vi event, dữ liệu và transaction của module khi tích hợp.
C. Việc có chu trình Java package do trình biên dịch đã phát hiện.
D. Việc tên Java class có trùng package của module khác hay không.
Đáp án đúng: B
