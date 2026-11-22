# Đánh đổi giữa mức độ làm nóng, thời gian dựng ảnh và kích thước ảnh

Khi dùng CRaC (Coordinated Restore at Checkpoint), ứng dụng Java thường được khởi động và làm nóng trước khi tạo checkpoint. Mục tiêu là đưa JVM và ứng dụng đến trạng thái gần với lúc phục vụ thật: class cần thiết đã được nạp, framework đã khởi tạo, các đường code thường dùng đã được thực thi, JIT compiler có cơ hội tối ưu và cache cần thiết đã được chuẩn bị.

Làm nóng nhiều hơn có thể giúp instance sau restore sẵn sàng nhanh hơn và giảm độ trễ của các request đầu tiên. Tuy nhiên, warm-up cũng tiêu tốn CPU và thời gian trước checkpoint, có thể làm tăng heap đang sống, code cache, dữ liệu cache và số trang bộ nhớ được lưu. Vì vậy, mức làm nóng cần được chọn dựa trên phép đo giữa ba yếu tố: **thời gian chuẩn bị**, **thời gian tạo checkpoint** và **kích thước checkpoint**.

Không có một mức warm-up tối ưu cho mọi ứng dụng. Một API service, một batch worker và một ứng dụng Spring Boot có thể có đường khởi động, cache và workload rất khác nhau. Cần làm nóng đúng những đường xử lý quan trọng, đo lợi ích sau restore và dừng khi chi phí tăng thêm không còn tương xứng.

## 1. Warm-up trong JVM là gì?

Warm-up là quá trình chạy ứng dụng với một workload có chủ đích trước khi tạo checkpoint. Nó giúp JVM và ứng dụng thực hiện trước một số công việc thường chỉ xảy ra khi instance bắt đầu nhận request thật.

Các hoạt động thường được làm nóng gồm:

- Nạp class và khởi tạo class cần thiết.
- Khởi tạo framework, dependency injection container và cấu hình.
- Chạy các đường code thường dùng để JVM thu thập profile.
- Cho JIT compiler biên dịch những method đủ nóng.
- Nạp metadata, schema và dữ liệu tham chiếu.
- Chuẩn bị một số cache ứng dụng có thể giữ lại an toàn.
- Khởi tạo cấu trúc dữ liệu và đường xử lý lazy initialization.

Warm-up không phải chỉ là gọi một endpoint nhiều lần. Một workload tốt cần phản ánh các đường xử lý thật, nhưng phải được thiết kế để không tạo side effect nghiệp vụ không mong muốn.

### 1.1. Các giai đoạn thực thi và tối ưu hóa của JVM

HotSpot JVM thường bắt đầu thực thi bytecode bằng interpreter. Khi một method hoặc loop được gọi đủ nhiều, JVM có thể biên dịch code thành mã máy. Với tiered compilation, JVM có thể đi qua các mức biên dịch khác nhau, chẳng hạn biên dịch nhanh để giảm chi phí ban đầu rồi tối ưu sâu hơn khi có đủ profile.

Một mô hình khái quát:

~~~mermaid
flowchart TD
    A["Ứng dụng khởi động"] --> B["Class loading và initialization"]
    B --> C["Interpreter thực thi"]
    C --> D["Thu thập invocation và branch profile"]
    D --> E["JIT biên dịch mức thấp"]
    E --> F["Tiếp tục thu thập profile"]
    F --> G["JIT tối ưu sâu hơn khi phù hợp"]
    G --> H["Checkpoint"]
    H --> I["Restore"]
    I --> J["Ứng dụng tiếp tục với trạng thái đã chuẩn bị"]
~~~

Sơ đồ chỉ mô tả ý tưởng. Các tier, ngưỡng biên dịch và hành vi lưu trạng thái phụ thuộc JDK, cấu hình JVM và workload. Không phải mọi method đều được biên dịch tối ưu chỉ vì ứng dụng đã chạy một khoảng thời gian.

### 1.2. Warm-up có thể chuẩn bị nhiều hơn JIT

Một ứng dụng có thể chậm ở request đầu tiên vì nhiều nguyên nhân khác nhau:

| Nguồn chi phí | Ví dụ | Warm-up có thể giúp gì? |
|---|---|---|
| Class loading | Nạp class của controller hoặc serializer | Nạp trước class cần thiết |
| Class initialization | Static initializer, đăng ký metadata | Thực hiện khởi tạo trước |
| Framework initialization | Tạo bean, route, mapper | Chuẩn bị container và cấu trúc |
| JIT compilation | Method thường gọi chưa được tối ưu | Cung cấp profile và cơ hội biên dịch |
| Cache miss | Thiếu dữ liệu tham chiếu | Nạp trước key quan trọng |
| Lazy initialization | Tạo client hoặc parser ở lần dùng đầu | Kích hoạt trước nếu an toàn |
| Connection setup | DNS, TCP, TLS, authentication | Có thể thiết lập trước, nhưng phải quản lý lại sau restore |

Không nên gom tất cả các chi phí này thành “JIT warm-up”. Một ứng dụng có thể đã JIT tốt nhưng vẫn chậm vì cache miss hoặc kết nối database. Ngược lại, cache có thể đã nóng trong khi những method quan trọng vẫn chưa được tối ưu.

## 2. Warm-up ảnh hưởng thế nào đến checkpoint?

Checkpoint lưu trạng thái tiến trình ở một thời điểm. Trạng thái đó có thể bao gồm heap, thread state, metadata JVM, code đã biên dịch và các vùng nhớ khác tùy JDK, hệ điều hành và cơ chế checkpoint/restore.

Warm-up có thể làm thay đổi những vùng nhớ này:

- Class và metadata được nạp làm tăng trạng thái runtime cần duy trì.
- Object cache còn sống làm tăng live heap.
- JIT compiler có thể tạo mã máy trong code cache.
- Profile và runtime metadata có thể tăng.
- Thread được tạo để warm-up có thể làm tăng số thread và stack nếu không được dừng.
- Buffer và native resource có thể tăng lượng bộ nhớ tiến trình sử dụng.

Một số dữ liệu tạm thời do warm-up tạo ra có thể được garbage collector thu hồi trước checkpoint. Do đó, số byte đã cấp phát trong toàn bộ warm-up không đồng nghĩa với số byte sẽ nằm trong ảnh cuối cùng. Điều cần quan tâm là trạng thái còn sống và các trang bộ nhớ mà cơ chế checkpoint phải lưu.

### 2.1. Warm-up có thể cải thiện thời gian sau restore

Nếu một số class đã được nạp, cấu trúc ứng dụng đã được tạo và các method nóng đã được JIT biên dịch, instance sau restore có thể tránh thực hiện lại một phần công việc khởi tạo và tối ưu hóa.

Lợi ích có thể thể hiện ở:

- Giảm thời gian từ lúc restore đến readiness.
- Giảm latency của các request đầu tiên.
- Giảm số cache miss trong giai đoạn đầu.
- Giảm số lần biên dịch JIT sau khi nhận traffic.
- Giảm dao động hiệu năng giữa cold request và steady-state request.

Mức cải thiện thực tế phụ thuộc vào việc runtime giữ và sử dụng lại trạng thái nào sau restore. Cần đo bằng đúng JDK CRaC và môi trường triển khai đang dùng.

### 2.2. Warm-up có thể làm tăng thời gian dựng ảnh

Warm-up kéo dài làm tăng thời gian chuẩn bị trước khi checkpoint. Ngoài thời gian chạy workload, JVM có thể cần thực hiện compilation, GC hoặc các thao tác đồng bộ.

Nếu warm-up tạo nhiều trang bộ nhớ đang hoạt động hoặc nhiều trạng thái cần lưu, checkpoint có thể cần thêm thời gian để dump. Trong một số hệ thống, checkpoint còn có thể làm tiến trình tạm dừng trong khi trạng thái được ghi ra storage.

Cần phân biệt:

- **Warm-up duration:** thời gian chạy ứng dụng và workload trước checkpoint.
- **Checkpoint duration:** thời gian từ lúc bắt đầu yêu cầu checkpoint đến khi ảnh được tạo xong.
- **Preparation duration:** thời gian drain task, đóng resource và chuẩn bị trạng thái an toàn.
- **Restore duration:** thời gian dựng lại tiến trình từ ảnh.
- **Time to ready:** tổng thời gian từ khi bắt đầu restore đến khi ứng dụng có thể nhận traffic.

Một warm-up lâu hơn không nhất thiết làm checkpoint dump lâu hơn theo cùng tỷ lệ. Nó có thể tăng thời gian chuẩn bị, làm tăng live memory hoặc chỉ làm tăng rất ít kích thước ảnh nếu phần lớn allocation đã được thu hồi.

### 2.3. Warm-up có thể làm tăng kích thước ảnh

Kích thước checkpoint chịu ảnh hưởng bởi nhiều thành phần:

- Heap pages còn được giữ.
- Class metadata và runtime metadata.
- JIT code cache.
- Thread stacks và trạng thái thread.
- Native memory và direct buffers.
- Các vùng nhớ được map hoặc tài nguyên mà cơ chế checkpoint phải lưu.
- Mức độ nén, deduplication và cách công cụ lưu các page.

Nếu warm-up nạp thêm cache với nhiều object còn sống, live heap có thể tăng. Nếu warm-up làm nhiều method được biên dịch, code cache có thể tăng. Nếu warm-up tạo nhiều thread và không dừng chúng, thread state và stack cũng có thể làm ảnh lớn hơn.

Tuy nhiên, kích thước heap tối đa được cấu hình không đồng nghĩa với kích thước checkpoint. Một heap có capacity lớn nhưng ít object còn sống có thể có footprint khác với heap nhỏ nhưng chứa nhiều object và trang bộ nhớ đang hoạt động. Cần đo kích thước artifact thực tế do công cụ checkpoint tạo ra.

## 3. Ba đại lượng cần cân bằng

Khi chọn warm-up level, nên theo dõi ít nhất ba đại lượng:

1. **Chi phí chuẩn bị:** thời gian và CPU để chạy warm-up, chuẩn bị resource và tạo checkpoint.
2. **Lợi ích sau restore:** thời gian restore, time to ready, latency và throughput trong giai đoạn đầu.
3. **Chi phí lưu trữ và vận hành:** kích thước ảnh, thời gian upload/download, số ảnh cần lưu và dung lượng storage.

~~~mermaid
flowchart TD
    A["Chọn warm-up workload"] --> B["Thời gian warm-up tăng"]
    B --> C["Nhiều class, profile, code và cache được chuẩn bị"]
    C --> D["Hiệu năng ban đầu sau restore có thể tốt hơn"]
    C --> E["Live memory và checkpoint footprint có thể tăng"]
    E --> F["Checkpoint, lưu trữ và phân phối có thể tốn hơn"]
    D --> G["Đo lợi ích thực tế"]
    F --> G
    G --> H["Chọn mức warm-up phù hợp"]
~~~

Mục tiêu không phải tối đa hóa số method đã chạy hoặc kích thước cache. Mục tiêu là đạt mức hiệu năng sau restore đáp ứng yêu cầu trong giới hạn thời gian và tài nguyên cho phép.

### 3.1. Chi phí chuẩn bị

Chi phí chuẩn bị gồm:

- Thời gian khởi động ứng dụng.
- Thời gian chạy warm-up request hoặc job.
- CPU dành cho JIT compilation.
- GC phát sinh khi warm-up tạo nhiều object.
- Thời gian drain và đóng tài nguyên trước checkpoint.
- Thời gian thực hiện checkpoint.

Với hệ thống tạo checkpoint một lần rồi restore hàng trăm instance, chi phí warm-up và tạo ảnh có thể được phân bổ trên nhiều lần restore. Với hệ thống tạo ảnh liên tục theo từng instance, chi phí này có thể trở thành phần đáng kể trong tổng thời gian vận hành.

### 3.2. Lợi ích sau restore

Không chỉ đo thời gian restore. Một ứng dụng có thể restore rất nhanh nhưng vẫn cần nhiều giây để cache warm-up hoặc JIT lại trước khi đạt hiệu năng mong muốn.

Nên đo:

- Restore-to-process-ready.
- Restore-to-application-ready.
- Restore-to-first-successful-request.
- Latency p50, p95 và p99 trong giai đoạn đầu.
- Throughput trong các request đầu tiên.
- Số lần JIT compilation sau restore.
- Cache hit rate và miss rate.
- Số lỗi kết nối hoặc refresh trong giai đoạn đầu.

### 3.3. Kích thước ảnh và chi phí lưu trữ

Kích thước ảnh ảnh hưởng đến:

- Dung lượng storage.
- Thời gian ghi checkpoint.
- Thời gian tải ảnh đến host restore.
- Băng thông khi scale out nhiều instance.
- Chi phí lưu nhiều version checkpoint.
- Thời gian sao lưu và vòng đời artifact.

Một ảnh lớn hơn có thể vẫn là lựa chọn tốt nếu giảm đáng kể time to ready cho một workload quan trọng. Ngược lại, ảnh lớn hơn nhưng không cải thiện latency có thể là chi phí không cần thiết.

## 4. Các mức warm-up thường dùng

Có thể tổ chức warm-up thành ba mức để so sánh. Đây là cách phân loại phục vụ thiết kế, không phải các chế độ chính thức của CRaC hoặc JVM.

### 4.1. Mức cơ bản: khởi tạo cấu trúc

Mức này tập trung vào công việc cần thiết để ứng dụng có thể bắt đầu nhận request:

- Khởi tạo framework và dependency injection.
- Nạp class và route phổ biến.
- Đọc cấu hình.
- Khởi tạo serializer, mapper và metadata.
- Chuẩn bị các cấu trúc dữ liệu nhỏ.
- Xác nhận những dependency thiết yếu.

Ưu điểm:

- Thời gian warm-up ngắn.
- Ít tạo thêm cache và live heap.
- Ảnh thường có footprint nhỏ hơn.
- Phù hợp với ứng dụng ưu tiên tốc độ tạo checkpoint và dung lượng lưu trữ.

Giới hạn:

- Nhiều method có thể vẫn chạy ở interpreter hoặc tier biên dịch thấp.
- JIT profile chưa phản ánh workload thật.
- Request đầu tiên có thể tiếp tục gặp lazy initialization và cache miss.

### 4.2. Mức mục tiêu: làm nóng đường xử lý phổ biến

Mức này chạy một tập workload đại diện cho những request quan trọng và thường xuyên:

- Gọi các endpoint phổ biến.
- Thực thi các nhánh xử lý thường gặp.
- Chạy serializer/deserializer với dữ liệu đại diện.
- Nạp cache thiết yếu.
- Cho JVM có thời gian thu thập profile và biên dịch method nóng.
- Kiểm tra những đường truy cập database hoặc dịch vụ bên ngoài cần thiết.

Ưu điểm:

- Cân bằng giữa hiệu năng sau restore và chi phí checkpoint.
- Có cơ hội chuẩn bị các method và cache được dùng nhiều.
- Tránh phải chạy toàn bộ chức năng hiếm gặp.

Giới hạn:

- Cần biết workload thực tế.
- Có thể bỏ sót nhánh quan trọng nếu tập warm-up không đại diện.
- Kích thước ảnh và thời gian chuẩn bị có thể tăng.

### 4.3. Mức sâu: chạy workload gần steady state

Mức này chạy workload dài hơn, có phân bố request gần với production và có thể làm nóng nhiều đường code, cache và method.

Ưu điểm:

- Có cơ hội đạt mức tối ưu JIT cao hơn cho các đường nóng.
- Có thể giảm đáng kể latency ở giai đoạn đầu sau restore.
- Có thể nạp trước nhiều cache phục vụ workload thực tế.

Giới hạn:

- Tốn nhiều CPU và thời gian chuẩn bị.
- Tăng khả năng tạo cache và live heap lớn.
- Ảnh checkpoint có thể lớn hơn.
- Có nguy cơ làm nóng những dữ liệu không cần thiết hoặc tạo profile lệch.
- Dễ phát sinh side effect nếu workload không được kiểm soát.

Mức sâu chỉ nên dùng khi số đo cho thấy lợi ích sau restore đủ lớn để bù chi phí.

## 5. Warm-up quá ít và warm-up quá nhiều

### 5.1. Warm-up quá ít

Nếu checkpoint được tạo ngay sau khi ứng dụng khởi động, nhiều class và đường code có thể chưa được thực thi. Sau restore, ứng dụng vẫn phải:

- Nạp class lazy.
- Khởi tạo object và framework component.
- Tạo cache lần đầu.
- Thực hiện JIT compilation khi method trở nên nóng.
- Thiết lập các cấu trúc runtime chưa được chuẩn bị.

Kết quả là checkpoint có thể nhỏ và nhanh tạo, nhưng lợi ích giảm thời gian khởi động chưa đạt kỳ vọng.

### 5.2. Warm-up quá nhiều

Warm-up kéo dài không bảo đảm hiệu năng tiếp tục cải thiện tương ứng. Sau khi các đường code quan trọng đã được thực thi và tối ưu, những vòng warm-up tiếp theo có thể đem lại lợi ích giảm dần.

Trong khi đó, chi phí vẫn có thể tăng:

- Thêm thời gian và CPU.
- Cache tiếp tục nạp dữ liệu ít dùng.
- Heap có thêm object còn sống.
- Code cache và metadata có thể tăng.
- Các scheduled task hoặc background thread có thể được khởi động.
- Warm-up có thể kích hoạt những thao tác nghiệp vụ không nên chạy trong môi trường tạo ảnh.

Một ví dụ về xu hướng diminishing returns:

~~~text
Lợi ích hiệu năng sau restore
^
|                  _________
|              ___/
|           __/
|        __/
|     __/
|  __/
|_/
+--------------------------------> Thời gian warm-up

Chi phí chuẩn bị và footprint
^
|                          /
|                      ___/
|                  ___/
|              ___/
|          ___/
|      ___/
|_____/
+--------------------------------> Thời gian warm-up
~~~

Đường cong chỉ mang tính minh họa. Hình dạng thực tế phải được đo trên ứng dụng và môi trường của bạn.

## 6. Những thành phần có thể làm tăng footprint

### 6.1. Live heap và cache ứng dụng

Cache chứa object còn sống có thể làm tăng live heap. Ví dụ, warm-up hàng triệu sản phẩm hoặc toàn bộ metadata có thể giúp giảm cache miss, nhưng cũng làm tăng lượng object cần lưu trong checkpoint.

Cần cân nhắc:

- Nạp key thường xuyên được dùng thay vì toàn bộ dữ liệu.
- Đặt maximum size và eviction policy.
- Dùng TTL phù hợp.
- Không giữ object request hoặc entity không cần thiết.
- Không cache connection, transaction hoặc native handle như dữ liệu thông thường.

Một warm-up tạo nhiều allocation tạm thời nhưng không giữ reference có thể không làm live heap tăng tương ứng. Vì vậy, hãy phân biệt allocation volume với retained heap.

### 6.2. JIT code cache

JIT compiler tạo mã máy cho những method được xem là đủ nóng. Mã đã biên dịch có thể nằm trong code cache và là một phần trạng thái runtime cần xem xét khi checkpoint.

Làm nóng thêm các đường code có thể tăng lượng mã đã biên dịch. Tuy nhiên, không nên cố làm nóng mọi method. Các method ít dùng có thể không đem lại lợi ích đáng kể sau restore.

JVM cũng có thể deoptimize hoặc biên dịch lại khi các giả định tối ưu không còn phù hợp. Ví dụ, profile warm-up quá lệch với workload thật có thể khiến một số tối ưu hóa không còn hiệu quả.

### 6.3. Class metadata và class initialization

Nạp thêm class và khởi tạo class có thể tăng metadata và trạng thái static trong tiến trình.

Khởi tạo class trong Java thường chỉ diễn ra một lần trong vòng đời class loader. Nếu class đã initialized trước checkpoint, trạng thái đó có thể được giữ trong tiến trình restore. Tuy nhiên, static field có thể chứa cấu hình hoặc dữ liệu phụ thuộc môi trường đã cũ.

Không nên kích hoạt mọi class chỉ để tăng số lượng class đã nạp. Hãy tập trung vào class của những đường xử lý quan trọng và kiểm tra static state có phụ thuộc thời gian, secret hoặc endpoint hay không.

### 6.4. Thread và stack

Warm-up có thể vô tình tạo nhiều worker, scheduler, connection monitor hoặc background thread. Nếu chúng còn hoạt động tại checkpoint, trạng thái thread và stack có thể làm phức tạp quá trình restore.

Trước checkpoint, cần:

- Dừng các tác vụ warm-up.
- Drain worker.
- Dừng scheduler không cần thiết.
- Đóng hoặc chuẩn bị lại executor theo vòng đời.
- Chỉ giữ những thread mà runtime và ứng dụng chủ động hỗ trợ.

Không nên tạo hàng nghìn thread chỉ để “làm nóng” hệ thống. Warm-up nên tập trung vào đường code và dữ liệu, không phải giữ lại nhiều hoạt động nền không cần thiết.

### 6.5. Native memory và direct buffer

Một số thư viện sử dụng direct ByteBuffer, native library, compression context hoặc cấu trúc ngoài heap. Warm-up có thể tạo hoặc giữ những vùng nhớ này.

Không phải mọi native resource đều có cùng khả năng checkpoint/restore. Hãy kiểm tra tài liệu của thư viện và xử lý vòng đời qua integration hoặc Resource callback phù hợp.

### 6.6. Garbage collection trước checkpoint

Warm-up có thể tạo nhiều object tạm thời. Nếu những object này không còn được tham chiếu, GC có thể thu hồi chúng trước checkpoint.

Không nên coi việc gọi System.gc() là cách bảo đảm ảnh nhỏ hơn. GC behavior phụ thuộc collector và cấu hình, và full GC có thể làm tăng thời gian chuẩn bị. Hãy đo live heap và checkpoint footprint trước khi thêm một bước GC cưỡng bức.

## 7. Thiết kế workload warm-up đại diện

Một warm-up tốt cần trả lời: những đường code nào thực sự cần nhanh ngay sau restore?

### 7.1. Chọn theo tỷ trọng traffic

Có thể dùng thống kê production để xác định:

- Endpoint có tỷ lệ request cao.
- Các thao tác có latency p95/p99 lớn.
- Những method tốn CPU.
- Các serializer và parser được dùng nhiều.
- Các truy vấn và cache key phổ biến.
- Các nhánh logic có tần suất cao.

Không nhất thiết warm-up mọi endpoint theo tỷ lệ traffic. Một endpoint ít dùng nhưng ảnh hưởng lớn đến nghiệp vụ có thể cần được chuẩn bị riêng.

### 7.2. Chọn theo đường code, không chỉ theo URL

Một endpoint có thể đi qua nhiều nhánh logic tùy loại input. Gọi một URL duy nhất với một payload có thể chỉ làm nóng một phần code.

Ví dụ, API tìm kiếm có thể có các nhánh:

- Tìm kiếm theo tên.
- Lọc theo danh mục.
- Sắp xếp theo giá.
- Phân trang.
- Xử lý kết quả rỗng.
- Xử lý dữ liệu lớn.

Hãy chọn payload đại diện cho các đường phổ biến và quan trọng. Tránh tạo workload quá rộng khiến warm-up kéo dài mà không tăng giá trị.

### 7.3. Dữ liệu warm-up cần an toàn

Không nên chạy warm-up bằng dữ liệu production có thể gây side effect thật:

- Không gửi email hoặc SMS đến khách hàng.
- Không tạo giao dịch thanh toán.
- Không phát hành hóa đơn.
- Không thay đổi tồn kho.
- Không tạo message nghiệp vụ thật.
- Không kích hoạt workflow có tác động bên ngoài.

Có thể dùng mock, sandbox, test tenant, read-only request hoặc các endpoint warm-up chuyên biệt. Nếu cần kiểm tra write path, phải có dữ liệu và môi trường được thiết kế để rollback hoặc loại bỏ an toàn.

### 7.4. Tránh profile lệch

JIT sử dụng profile thu thập từ quá trình thực thi để quyết định tối ưu hóa. Nếu warm-up chỉ dùng một kiểu input hoặc một nhánh duy nhất, profile có thể không đại diện cho workload production.

Ví dụ, một method xử lý danh sách có thể thường nhận 10 phần tử trong production, nhưng warm-up chỉ chạy với danh sách rỗng. JIT profile thu được có thể không phản ánh đường xử lý phổ biến.

Dùng nhiều input đại diện nhưng có kiểm soát. Không cần chạy mọi tổ hợp dữ liệu; ưu tiên phân bố thực tế và các nhánh có ý nghĩa.

## 8. Quy trình warm-up theo giai đoạn

Một quy trình có thể chia thành các giai đoạn sau:

~~~mermaid
flowchart TD
    A["Khởi động JVM"] --> B["Khởi tạo framework và cấu hình"]
    B --> C["Warm-up class và đường code thiết yếu"]
    C --> D["Warm-up workload đại diện"]
    D --> E["Nạp cache quan trọng"]
    E --> F["Đo JIT, heap và cache"]
    F --> G{"Đã đạt mục tiêu?"}
    G -->|Chưa| D
    G -->|Rồi| H["Dừng warm-up và background task"]
    H --> I["Chuẩn bị Resource cho CRaC"]
    I --> J["Tạo checkpoint"]
    J --> K["Restore trong môi trường mục tiêu"]
    K --> L["Đo time to ready và latency"]
~~~

### Giai đoạn 1: Khởi tạo cấu trúc

Khởi động ứng dụng, tạo framework container, đọc cấu hình và khởi tạo những component cần thiết. Xác định các resource bên ngoài sẽ phải đóng hoặc làm mới.

### Giai đoạn 2: Làm nóng class và đường xử lý

Gọi các endpoint hoặc service method quan trọng bằng dữ liệu đại diện. Theo dõi JIT compilation nếu cần để xác định các method nóng đã được biên dịch ở mức phù hợp.

Không nên chỉ dùng một thời gian cố định như “warm-up 60 giây” mà không quan sát kết quả. Hai workload khác nhau có thể cần thời gian rất khác nhau.

### Giai đoạn 3: Nạp cache thiết yếu

Nạp cấu hình, metadata và cache key phổ biến. Không nạp toàn bộ dữ liệu nếu phần lớn không được dùng. Đặt TTL và version để cache có thể được đánh giá lại sau restore.

### Giai đoạn 4: Dừng hoạt động nền

Trước checkpoint, dừng warm-up generator, scheduler và task không cần thiết. Drain các request và task đang chạy. Đóng connection hoặc resource phụ thuộc môi trường theo callback CRaC.

### Giai đoạn 5: Tạo checkpoint và đo

Ghi lại thời gian chuẩn bị, thời gian dump và kích thước artifact. Sau đó restore ảnh trong môi trường gần với production và đo time to ready cùng hiệu năng request ban đầu.

### Giai đoạn 6: Điều chỉnh mức warm-up

So sánh các mức warm-up. Nếu tăng warm-up thêm 30% chỉ giảm rất ít latency nhưng làm ảnh tăng mạnh, hãy cân nhắc dừng ở mức trước đó.

## 9. Ví dụ Java: chạy workload warm-up có giới hạn

Ví dụ sau minh họa một coordinator chạy các request warm-up theo số vòng xác định. Các service là abstraction do ứng dụng định nghĩa.

~~~java
import java.util.List;

public final class ApplicationWarmup {

    private final List<WarmupScenario> scenarios;

    public ApplicationWarmup(List<WarmupScenario> scenarios) {
        this.scenarios = List.copyOf(scenarios);
    }

    public void run(int rounds) throws Exception {
        if (rounds <= 0) {
            throw new IllegalArgumentException(
                "rounds must be greater than zero"
            );
        }

        for (int round = 0; round < rounds; round++) {
            for (WarmupScenario scenario : scenarios) {
                scenario.execute();
            }
        }
    }
}
~~~

Một scenario có thể đại diện cho một đường code:

~~~java
public interface WarmupScenario {
    String name();

    void execute() throws Exception;
}
~~~

Khi khởi tạo, ứng dụng có thể cung cấp các scenario chỉ đọc hoặc chạy trên dữ liệu sandbox:

~~~java
List<WarmupScenario> scenarios = List.of(
    new ProductSearchWarmup(searchService, warmupTenant),
    new CatalogWarmup(catalogService),
    new JsonSerializationWarmup(objectMapper)
);

ApplicationWarmup warmup = new ApplicationWarmup(scenarios);
warmup.run(20);
~~~

Ví dụ này chỉ mô tả cách tổ chức workload. Số vòng 20 không phải con số khuyến nghị chung. Cần chọn số vòng dựa trên JIT profile, thời gian chuẩn bị và kết quả đo sau restore.

Một warm-up coordinator production nên bổ sung:

- Timeout tổng và timeout cho từng scenario.
- Log thời gian từng scenario.
- Giới hạn concurrency.
- Dừng an toàn khi có lỗi.
- Không thực hiện side effect nghiệp vụ.
- Không để thread warm-up còn chạy khi checkpoint bắt đầu.

## 10. Đo lường JVM trước checkpoint

Không nên quyết định warm-up chỉ bằng thời gian chạy. Hãy thu thập các số liệu có thể giải thích vì sao hiệu năng thay đổi.

### 10.1. Thời gian biên dịch JIT

JVM cung cấp CompilationMXBean trong Management API. Có thể đọc tổng thời gian biên dịch nếu implementation hỗ trợ:

~~~java
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;

public final class JitMetrics {

    public static void printCompilationTime() {
        CompilationMXBean bean =
                ManagementFactory.getCompilationMXBean();

        if (bean != null && bean.isCompilationTimeMonitoringSupported()) {
            System.out.println(
                "JIT compilation time: "
                + bean.getTotalCompilationTime()
                + " ms"
            );
        }
    }
}
~~~

Tổng thời gian compilation tăng không nhất thiết là xấu. Nó cho biết JVM đã dành thời gian biên dịch. Cần kết hợp với latency và số method compilation để đánh giá warm-up có đem lại lợi ích hay không.

### 10.2. Theo dõi memory pool và code cache

Có thể xem các memory pool mà JVM công bố:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;

public final class MemoryMetrics {

    public static void printPools() {
        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {

            System.out.println(
                pool.getName()
                + " used="
                + (pool.getUsage() == null
                    ? "unknown"
                    : pool.getUsage().getUsed())
            );
        }
    }
}
~~~

Tên memory pool phụ thuộc JVM và phiên bản. Một số HotSpot build công bố các pool có tên liên quan đến Code Cache. Hãy đọc tên và usage thực tế thay vì giả định một tên cố định.

### 10.3. Theo dõi heap

Có thể lấy thông tin heap cơ bản:

~~~java
Runtime runtime = Runtime.getRuntime();

long usedHeap = runtime.totalMemory() - runtime.freeMemory();
long committedHeap = runtime.totalMemory();
long maxHeap = runtime.maxMemory();
~~~

Các giá trị này giúp quan sát heap đã commit và lượng heap đang sử dụng tại thời điểm đo. Chúng không trực tiếp cho biết kích thước checkpoint. Hãy đo cả artifact checkpoint và memory footprint của tiến trình.

### 10.4. Theo dõi JIT và GC bằng công cụ runtime

Tùy JDK, có thể sử dụng Java Flight Recorder, compilation logging, GC logging và các công cụ quan sát JVM để xác định:

- Method nào được biên dịch trong warm-up.
- Có deoptimization hoặc compilation lại hay không.
- GC diễn ra bao nhiêu lần.
- Heap sau warm-up còn bao nhiêu object sống.
- Có thread hoặc background activity nào không cần thiết.
- Code cache có tăng nhanh hay không.

Các flag và event có thể khác giữa các phiên bản JDK. Hãy dùng tài liệu của bản JDK CRaC thực tế.

## 11. Ma trận thử nghiệm các mức warm-up

Để chọn mức phù hợp, nên tạo ít nhất ba profile:

| Profile | Workload | Mục tiêu |
|---|---|---|
| A - Basic | Khởi tạo framework và class thiết yếu | Baseline nhỏ và nhanh |
| B - Targeted | Đường request phổ biến và cache critical | Cân bằng latency và footprint |
| C - Deep | Workload gần steady state | Đo lợi ích tối đa có thể đạt |

Với mỗi profile, ghi lại:

| Nhóm đo | Chỉ số |
|---|---|
| Preparation | Thời gian khởi động, warm-up, drain và checkpoint |
| JVM | JIT compilation time, code cache usage, GC count |
| Memory | Heap used/committed, live set, native memory nếu đo được |
| Artifact | Kích thước checkpoint directory/artifact |
| Restore | Thời gian restore và time to ready |
| Request | p50/p95/p99 latency, throughput, error rate |
| Stability | Cache miss, reconnect, deoptimization và compilation sau restore |

Ví dụ bảng kết quả minh họa, không phải số liệu benchmark:

| Chỉ số | Basic | Targeted | Deep |
|---|---:|---:|---:|
| Warm-up duration | 10 s | 45 s | 180 s |
| Checkpoint duration | 4 s | 5 s | 8 s |
| Image size | 100 MB | 125 MB | 175 MB |
| Restore-to-ready | 2.8 s | 1.9 s | 1.7 s |
| First-request p95 | 420 ms | 180 ms | 155 ms |

Trong ví dụ, chuyển từ Basic sang Targeted cải thiện rõ rệt. Chuyển từ Targeted sang Deep chỉ cải thiện thêm ít nhưng tăng đáng kể thời gian warm-up và kích thước ảnh. Khi đó, Targeted có thể là lựa chọn cân bằng hơn.

Các con số trong bảng chỉ để minh họa cách so sánh. Không dùng chúng làm mục tiêu hiệu năng cho ứng dụng thực tế.

## 12. Đo kích thước ảnh và thời gian tạo checkpoint

Checkpoint có thể được lưu thành một tập hợp file hoặc directory tùy công cụ. Không nên chỉ đo một file đại diện nếu ảnh gồm nhiều thành phần.

Nên ghi nhận:

- Tổng kích thước tất cả file thuộc checkpoint.
- Số lượng file.
- Thời gian từ lúc bắt đầu checkpoint đến khi hoàn tất.
- Thời gian tiến trình bị freeze nếu công cụ cung cấp.
- Dung lượng sau nén hoặc đóng gói nếu deployment lưu artifact dạng archive.
- Thời gian upload/download checkpoint.
- Dung lượng lưu nhiều phiên bản.

Cần phân biệt kích thước ảnh raw với kích thước archive đã nén. Compression có thể làm thay đổi dung lượng lưu trữ nhưng cũng tiêu tốn CPU và thời gian đóng gói/giải nén.

Một profile warm-up có thể làm tăng live heap nhưng các trang nhớ có khả năng nén tốt. Profile khác có thể tạo nhiều dữ liệu có entropy cao và khó nén. Vì vậy, chỉ nhìn vào heap usage không đủ để dự đoán artifact size.

## 13. Những yếu tố khiến kết quả warm-up khác nhau giữa môi trường

### 13.1. Khác JDK hoặc JVM flags

JIT compiler, GC, tiered compilation và code cache có thể thay đổi theo bản JDK, nhà cung cấp, kiến trúc và JVM flags.

Checkpoint được tạo với một cấu hình JVM rồi restore ở cấu hình khác có thể không được hỗ trợ hoặc không cho kết quả tương đương. Hãy tuân theo yêu cầu tương thích của JDK CRaC và tạo ảnh trong môi trường phù hợp với nơi restore.

### 13.2. Khác CPU và kiến trúc

JIT biên dịch thành mã máy phù hợp với CPU. Khác biệt về kiến trúc hoặc feature CPU có thể ảnh hưởng khả năng tương thích và hiệu năng.

Không nên giả định checkpoint có thể được phân phối tùy ý giữa các host khác kiến trúc. Hãy xác nhận giới hạn của runtime và deployment platform.

### 13.3. Khác workload thực tế

Nếu warm-up chỉ đại diện cho traffic đọc nhưng production có nhiều thao tác ghi, profile JIT và cache có thể không phù hợp. Tương tự, workload test với payload nhỏ có thể không làm nóng code path xử lý dữ liệu lớn.

Nên cập nhật warm-up profile khi phân bố traffic hoặc phiên bản ứng dụng thay đổi.

### 13.4. Dữ liệu và cấu hình thay đổi

Warm-up có thể nạp cache hoặc static state phụ thuộc môi trường tạo ảnh. Nếu restore ở môi trường khác, các giá trị này có thể không còn đúng.

Không nên đóng gói endpoint, credential hoặc feature flag thay đổi thường xuyên vào trạng thái được giữ lại mà không có bước kiểm tra sau restore. Cần làm mới những cấu hình phụ thuộc môi trường trước khi mở readiness.

## 14. Những rủi ro khi warm-up quá sâu

### 14.1. Profile không đại diện

Warm-up dùng dữ liệu đơn giản hoặc một nhánh duy nhất có thể khiến JIT tối ưu theo giả định không phù hợp với traffic thật. Một số giả định có thể bị invalidated và dẫn đến deoptimization.

Hãy dùng dữ liệu đại diện và quan sát hành vi sau restore. Đừng tối ưu cho một microbenchmark không phản ánh workload production.

### 14.2. Cache dữ liệu quá cũ

Nếu checkpoint được giữ lâu trước khi restore, cache được nạp trong warm-up có thể stale. Cần TTL, version và refresh policy.

### 14.3. Side effect nghiệp vụ

Warm-up gọi code path thật có thể tạo dữ liệu, gửi event hoặc thay đổi hệ thống. Dùng sandbox hoặc warm-up mode chuyên biệt và xác nhận không có side effect ngoài dự kiến.

### 14.4. Background task tiếp tục hoạt động

Scheduler, executor và refresh thread có thể còn chạy tại thời điểm checkpoint. Chúng có thể giữ lock, connection hoặc trạng thái không an toàn. Hãy dừng và drain chúng qua lifecycle resource phù hợp.

### 14.5. Thời gian chuẩn bị vượt lợi ích

Nếu mỗi lần build checkpoint tốn nhiều phút nhưng restore chỉ cải thiện vài trăm millisecond, tổng chi phí có thể không hợp lý. Cần đánh giá số lần restore mà mỗi ảnh phục vụ và chi phí scale-out thực tế.

## 15. Chiến lược chọn warm-up level theo workload

| Kiểu ứng dụng | Mức thường nên thử trước | Lý do |
|---|---|---|
| API service có một số endpoint nóng | Targeted | Tập trung vào đường xử lý thường dùng |
| Spring Boot service nhiều bean | Basic rồi Targeted | Khởi tạo framework có thể chiếm phần lớn startup |
| CPU-bound service | Targeted hoặc Deep | JIT profile có thể đem lại lợi ích rõ |
| Read-heavy service có cache lớn | Targeted | Warm-up key phổ biến, tránh nạp toàn bộ cache |
| Batch worker | Targeted theo loại job | Làm nóng parser, mapper và đường xử lý chính |
| Service có nhiều plugin hoặc endpoint hiếm | Basic và lazy initialization | Tránh làm nóng mọi plugin không được dùng |
| Instance sống rất ngắn và scale liên tục | Đo kỹ Targeted | Cân bằng chi phí tạo ảnh với số lần restore |

Đây chỉ là điểm bắt đầu để thiết kế thử nghiệm. Kết quả benchmark của chính ứng dụng mới là căn cứ lựa chọn.

## 16. Quy tắc ra quyết định

Có thể dùng các câu hỏi sau để quyết định có nên tăng warm-up level:

1. Request đầu tiên sau restore có chậm hơn đáng kể so với steady state không?
2. Độ trễ đó đến từ JIT, class initialization, cache miss hay kết nối?
3. Warm-up hiện tại đã thực thi các đường code quan trọng chưa?
4. Tăng warm-up có làm giảm p95/p99 sau restore không?
5. Mức cải thiện có đủ lớn so với thời gian chuẩn bị tăng thêm không?
6. Kích thước ảnh tăng bao nhiêu và ảnh hưởng đến thời gian phân phối thế nào?
7. Có dữ liệu cache hoặc thread nào được giữ lại nhưng không cần thiết không?
8. Profile warm-up có phản ánh workload production không?
9. Ảnh được restore trên môi trường tương thích không?
10. Có thể warm-up một tập nhỏ hơn mà vẫn giữ phần lớn lợi ích không?

Một quy tắc thực dụng là chọn mức warm-up thấp nhất vẫn đạt mục tiêu latency và readiness. Nếu tăng mức warm-up không cải thiện chỉ số quan trọng hoặc làm footprint vượt giới hạn, hãy giữ mức thấp hơn.

## 17. Checklist chuẩn bị checkpoint sau warm-up

### Workload và JIT

- [ ] Warm-up bao phủ các đường code quan trọng.
- [ ] Payload và tần suất gọi đại diện cho workload.
- [ ] Không tạo side effect nghiệp vụ ngoài dự kiến.
- [ ] Đã quan sát JIT compilation và latency sau restore.
- [ ] Không cố làm nóng các đường code hiếm mà không có lý do.

### Heap và cache

- [ ] Cache được giới hạn kích thước.
- [ ] Dữ liệu stale có TTL hoặc version.
- [ ] Object tạm thời không còn reference được phép thu hồi.
- [ ] Không giữ transaction hoặc connection ngắn hạn trong cache.
- [ ] Cache thiết yếu được refresh theo chính sách sau restore.

### Thread và resource

- [ ] Warm-up generator đã dừng.
- [ ] Background task đã drain hoặc pause.
- [ ] Executor có lifecycle rõ ràng.
- [ ] Kết nối mạng được đóng hoặc chuẩn bị lại theo CRaC Resource.
- [ ] Không còn thread warm-up không cần thiết.

### Checkpoint và đo lường

- [ ] Đã đo warm-up duration và checkpoint duration riêng biệt.
- [ ] Đã đo kích thước toàn bộ checkpoint artifact.
- [ ] Đã đo restore-to-ready và first-request latency.
- [ ] Đã thử ít nhất Basic, Targeted và Deep.
- [ ] Đã kiểm tra ảnh trong môi trường restore mục tiêu.
- [ ] Đã chọn mức warm-up dựa trên số liệu và giới hạn vận hành.

## 18. Câu hỏi thường gặp

### Warm-up càng lâu thì ứng dụng sau restore càng nhanh phải không?

Không. Lợi ích thường giảm dần khi các đường code quan trọng đã được làm nóng. Warm-up thêm có thể chủ yếu làm tăng thời gian chuẩn bị, CPU, cache và kích thước ảnh mà không cải thiện đáng kể latency.

### Warm-up có làm tăng kích thước checkpoint không?

Có thể. Cache còn sống, code cache, metadata, thread state và native memory có thể làm tăng footprint. Tuy nhiên, allocation tạm thời đã được GC thu hồi không nhất thiết làm ảnh tăng tương ứng. Hãy đo artifact thực tế.

### Có cần chạy mọi endpoint trước checkpoint không?

Không. Nên ưu tiên endpoint và đường code quan trọng theo traffic và yêu cầu nghiệp vụ. Những chức năng hiếm có thể được lazy initialize sau restore nếu chấp nhận được.

### JIT có giữ nguyên toàn bộ mã đã biên dịch sau restore không?

Không nên giả định mọi trạng thái biên dịch luôn được giữ và tiếp tục tối ưu giống hệt. Hành vi phụ thuộc JDK, CRaC implementation và điều kiện restore. Hãy quan sát compilation và latency sau restore trên đúng runtime mục tiêu.

### Có nên gọi System.gc() trước checkpoint để giảm ảnh không?

Không nên xem đó là bước bắt buộc. GC có thể thu hồi object không còn sống, nhưng gọi cưỡng bức có thể làm tăng thời gian chuẩn bị và không bảo đảm giảm artifact theo tỷ lệ mong muốn. Hãy đo live heap và kích thước ảnh trước khi quyết định.

### Có thể warm-up bằng traffic production thật không?

Chỉ khi hệ thống được thiết kế để bảo đảm không phát sinh side effect ngoài ý muốn và dữ liệu không làm thay đổi trạng thái nghiệp vụ. Thông thường, nên dùng warm-up mode, test tenant, request read-only hoặc dữ liệu sandbox.

### Vì sao ảnh lớn hơn nhưng restore không nhanh hơn?

Warm-up có thể đã làm tăng cache và memory footprint mà không làm nóng thêm đường code có ý nghĩa. Cũng có thể chi phí sau restore đến từ dependency bên ngoài, DNS, authentication hoặc cache cần refresh. Hãy phân tích latency theo từng giai đoạn thay vì chỉ tăng thời gian warm-up.

### Có nên tạo một checkpoint cho mỗi mức warm-up không?

Trong giai đoạn thử nghiệm, nên tạo các profile có thể so sánh được. Mỗi profile cần cùng JDK, JVM flags, cấu hình và workload đo. Khi đã chọn được mức phù hợp, có thể đưa profile đó vào quy trình tạo checkpoint chuẩn.

## Kết luận

Warm-up giúp chuẩn bị class, framework, JIT profile, code cache và dữ liệu cache trước khi CRaC lưu trạng thái tiến trình. Làm nóng sâu hơn có thể giảm latency sau restore, nhưng cũng làm tăng thời gian chuẩn bị, CPU và footprint của checkpoint. Lợi ích thường giảm dần sau khi các đường code quan trọng đã được thực thi và tối ưu.

Hãy bắt đầu bằng warm-up cơ bản, sau đó thêm workload đại diện cho các đường xử lý phổ biến. Đo riêng warm-up duration, checkpoint duration, image size, restore-to-ready, first-request latency và hiệu năng trong giai đoạn đầu. Chọn mức thấp nhất đáp ứng mục tiêu vận hành, đồng thời kiểm soát cache, thread, connection và side effect trước khi tạo ảnh.
