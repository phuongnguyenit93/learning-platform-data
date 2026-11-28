# Quan hệ giữa thu gom rác, khởi động và bộ đệm AOT

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt thời gian khởi động (startup) với thời gian làm nóng (warmup) của ứng dụng Java.
- Giải thích vì sao cách một garbage collector (GC) biểu diễn đối tượng trên heap ảnh hưởng đến việc tái sử dụng object trong AOT cache.
- Mô tả thay đổi của JDK 26 trong JEP 516 và lợi ích của định dạng object cache độc lập với GC.
- Phân biệt AOT cache với native image và với hoạt động thu gom rác thông thường.
- Tạo, sử dụng, kiểm tra AOT cache và đo hiệu quả trên đúng môi trường triển khai.

## 1. Startup, warmup và garbage collection liên quan với nhau thế nào?

Khi khởi chạy một ứng dụng Java trên HotSpot, JVM phải khởi tạo môi trường chạy, nạp và liên kết các lớp, chạy các bộ khởi tạo tĩnh, tạo những đối tượng cần thiết rồi gọi điểm vào của ứng dụng. Sau khi ứng dụng bắt đầu nhận công việc, JIT tiếp tục thu thập dữ liệu thực thi và biên dịch các phương thức thường được gọi thành mã máy tối ưu hơn.

Hai khoảng thời gian cần phân biệt:

- **Startup** là khoảng thời gian từ lúc tiến trình JVM bắt đầu cho đến khi ứng dụng sẵn sàng phục vụ công việc. Với dịch vụ web, mốc kết thúc nên là lúc health check hoặc endpoint readiness báo sẵn sàng, không chỉ là lúc hàm main trả về.
- **Warmup** là khoảng thời gian sau khi ứng dụng đã chạy nhưng hiệu năng vẫn đang thay đổi do JIT thu thập profile, biên dịch và tối ưu các đường chạy thường gặp.

GC có liên quan ngay từ lúc JVM khởi động vì JVM phải thiết lập heap và cơ chế quản lý đối tượng. Trong quá trình chạy, ứng dụng tiếp tục cấp phát đối tượng; GC xác định đối tượng còn được tham chiếu, thu hồi vùng nhớ không còn cần thiết và thực hiện các công việc phụ thuộc vào thuật toán thu gom rác. Những công việc này có thể tiêu tốn CPU, ảnh hưởng độ trễ và thông lượng.

AOT cache tác động vào một phần công việc phải lặp lại ở các lần khởi chạy sau. Nó có thể giúp JVM tái sử dụng thông tin về lớp đã nạp/liên kết, các đối tượng được lưu trong cache và dữ liệu profile phương thức. Vì cache có thể chứa đối tượng heap, cách GC biểu diễn đối tượng và tham chiếu trở thành yếu tố quan trọng.

## 2. AOT cache giúp giảm startup và warmup ra sao?

AOT là viết tắt của Ahead-of-Time. Với HotSpot, AOT cache lưu các kết quả tối ưu hóa được chuẩn bị trước khi chạy ứng dụng. Đây là cơ chế của JVM thuộc Project Leyden; nó không biến ứng dụng thành một tệp thực thi native độc lập và ứng dụng vẫn chạy trên JVM.

Các mốc phát triển liên quan:

| JDK | JEP | Vai trò |
|---|---|---|
| JDK 24 | JEP 483 – Ahead-of-Time Class Loading & Linking | Đặt nền tảng AOT cache, giúp tái sử dụng công việc nạp và liên kết lớp. |
| JDK 25 | JEP 515 – Ahead-of-Time Method Profiling | Ghi profile thực thi phương thức trong lần chạy huấn luyện để JIT có dữ liệu tối ưu sớm hơn ở lần chạy sau. |
| JDK 26 | JEP 516 – Ahead-of-Time Object Caching with Any GC | Mở rộng object caching để dùng được với mọi GC được HotSpot hỗ trợ, bao gồm ZGC. |

AOT cache được tạo và sử dụng qua ba giai đoạn:

1. **Training:** chạy ứng dụng với workload đại diện. JVM ghi lại thông tin về lớp, liên kết và hành vi thực thi cần cho tối ưu hóa.
2. **Assembly:** JVM đọc cấu hình thu được và tạo tệp cache có phần mở rộng thường dùng là .aot.
3. **Production:** JVM nạp cache khi chạy ứng dụng để giảm công việc phải lặp lại, từ đó cải thiện startup và warmup.

Cache có thể chứa các lớp Java, đối tượng heap được chuẩn bị sẵn (chẳng hạn đối tượng Class và một số đối tượng mà chúng tham chiếu), cùng dữ liệu profile phục vụ JIT. Không nên hiểu nó là ảnh chụp toàn bộ heap của ứng dụng hoặc nơi lưu trạng thái nghiệp vụ để khôi phục sau khi khởi động.

JEP 515 giúp JIT có profile phương thức từ lần huấn luyện, nhờ đó có thể bắt đầu biên dịch tối ưu sớm hơn. JIT vẫn tiếp tục hoạt động trong runtime và vẫn có thể cập nhật profile theo hành vi thực tế. Vì vậy AOT cache hỗ trợ quá trình khởi động và làm nóng; nó không loại bỏ JIT.

## 3. Vì sao garbage collector ảnh hưởng đến object cache?

Một đối tượng Java không chỉ gồm các trường dữ liệu mà còn có header, cách biểu diễn tham chiếu và những quy tắc bố trí trong heap. Các GC có thể sử dụng cách biểu diễn tham chiếu, bố trí vùng nhớ và quy tắc quản lý đối tượng khác nhau. Ví dụ, cách dùng compressed references, cách đặt đối tượng trong các vùng heap và cách xử lý vùng nhớ lớn có thể khác giữa các cấu hình GC.

Điều này tạo ra một vấn đề khi JVM muốn nạp trực tiếp object đã lưu trong tệp cache:

- Nếu định dạng trong cache khớp với cách GC đang dùng, JVM có thể memory-map dữ liệu vào heap. Cách này tránh phải tạo lại từng đối tượng và thường rất nhanh khi các trang của tệp cache đã có trong filesystem page cache.
- Nếu định dạng đối tượng hoặc tham chiếu trong cache không khớp với GC đích, các bit đã lưu không thể được dùng trực tiếp như một đối tượng hợp lệ trong heap đó.

Trước JEP 516, object caching của AOT bị giới hạn bởi sự khác biệt về định dạng heap. Một số tối ưu hóa cần object cache không dùng được với ZGC vì bố trí đối tượng của ZGC không tương thích với định dạng memory-map được dùng bởi các GC khác.

Vì vậy, khả năng tương thích với GC không chỉ là lựa chọn thuật toán thu gom rác. Nó còn quyết định JVM có thể tái sử dụng object cache trực tiếp hay phải chuyển đổi cách biểu diễn đối tượng.

## 4. JDK 26 và JEP 516: object cache độc lập với GC

JEP 516 bổ sung định dạng object cache trung lập với GC, thường được gọi là định dạng streamable hoặc GC-agnostic. Thay vì yêu cầu bố trí đối tượng trên đĩa phải giống hệt bố trí heap của GC đích, JVM đọc dữ liệu theo thứ tự và tạo các đối tượng theo quy tắc của GC đang được chọn.

Trong JDK 26, có hai cách nạp object cache cần phân biệt:

| Cách nạp | Cơ chế | Điểm mạnh | Đánh đổi |
|---|---|---|---|
| GC-specific / mappable | Ánh xạ trực tiếp dữ liệu cache vào heap khi định dạng tương thích với GC. | Rất nhanh ở lần khởi động ấm, đặc biệt khi tệp cache đã nằm trong filesystem page cache. | Phụ thuộc định dạng heap và GC tương thích. |
| GC-agnostic / streamable | Đọc object tuần tự, cấp phát và liên kết chúng theo định dạng của GC đang chạy. | Dùng được với mọi GC được HotSpot hỗ trợ, bao gồm ZGC. | Cần thêm CPU để xử lý object; đổi lại công việc này có thể chạy nền và chồng lấp với quá trình khởi động ứng dụng. |

Với định dạng streamable, JVM có thể nạp object trong nền trong khi ứng dụng tiếp tục khởi động. Nhờ vậy, chi phí đọc và dựng lại object có cơ hội được che khuất bởi các công việc khởi tạo khác. Trên máy khởi động lạnh, đọc tuần tự và xử lý song song cũng có thể tận dụng CPU tốt hơn việc chờ toàn bộ dữ liệu được đọc theo kiểu memory-map. Trên máy khởi động ấm, memory-map trực tiếp vẫn có thể có lợi thế.

JDK 26 vì thế cho phép ứng dụng cân nhắc ZGC vì mục tiêu độ trễ thấp mà vẫn sử dụng được các tối ưu hóa AOT object caching. Không cần đổi sang G1 hoặc Parallel GC chỉ vì muốn dùng AOT cache. JVM có thể sử dụng định dạng GC-neutral để tạo object theo cách phù hợp với GC đang chạy.

Một số bản HotSpot JDK 26 cung cấp tùy chọn nâng cao **-XX:+AOTStreamableObjects** để yêu cầu định dạng streamable. Đây là tùy chọn triển khai HotSpot, không phải API Java SE; hãy kiểm tra tùy chọn có được bản JDK của nhà cung cấp hỗ trợ hay không và chỉ ép định dạng sau khi đo đạc. Trước tiên nên thử hành vi mặc định của JVM.

### Luồng hoạt động

~~~mermaid
flowchart TD
    A[Training run với workload đại diện] --> B[AOT configuration]
    B --> C[Assembly tạo tệp .aot]
    C --> D[JVM khởi động ở production]
    D --> E{Định dạng object cache}
    E -->|GC-specific và tương thích| F[Memory-map object vào heap]
    E -->|GC-agnostic| G[Stream object và dựng theo GC đích]
    F --> H[Ứng dụng tiếp tục chạy]
    G --> H
    H --> I[JIT tiếp tục tối ưu]
    H --> J[GC đang chọn quản lý heap trong runtime]
~~~

AOT cache không thay thế GC. Sau khi JVM nạp các object và ứng dụng tiếp tục chạy, GC được chọn vẫn thực hiện công việc quản lý heap trong runtime. AOT cache cũng không tự sửa memory leak, không bảo đảm giảm thời gian pause và không đồng nghĩa heap sẽ nhỏ hơn. Cần đo riêng startup, warmup, mức sử dụng heap, CPU dành cho GC và độ trễ ứng dụng.

## 5. Các cải tiến GC khác trong JDK 26

JEP 516 và JEP 522 đều liên quan đến hiệu năng, nhưng giải quyết hai vấn đề khác nhau.

### JEP 522: G1 GC giảm đồng bộ để tăng throughput

G1 theo dõi các cập nhật tham chiếu giữa các vùng heap bằng card table và write barrier. Trước thay đổi của JEP 522, luồng ứng dụng và các luồng nền tối ưu card table có nhiều điểm phải đồng bộ với nhau. Khi ứng dụng cập nhật trường tham chiếu thường xuyên, chi phí này có thể làm giảm throughput.

JDK 26 bổ sung card table thứ hai. Luồng ứng dụng ghi vào bảng đang hoạt động, trong khi các luồng nền xử lý bảng còn lại. Khi cần, G1 hoán đổi hai bảng một cách nguyên tử. Thiết kế này giảm đồng bộ giữa luồng ứng dụng và luồng GC, giúp giảm chi phí write barrier và cải thiện throughput, đặc biệt với workload cập nhật nhiều tham chiếu.

JEP 522 là cải tiến riêng của G1. Nó không phải cơ chế tạo hoặc nạp AOT cache và không thay đổi định dạng object cache. Kết quả thực tế phụ thuộc workload; không nên coi một con số benchmark công bố là mức tăng được bảo đảm cho mọi ứng dụng.

### Kích thước heap ban đầu mặc định

JDK 26 cũng thay đổi cách chọn heap ban đầu khi người dùng không đặt **-Xms** hoặc **-XX:InitialHeapSize**. JVM dùng **MinHeapSize** làm heap ban đầu thay vì suy ra giá trị mặc định từ **InitialRAMPercentage** như trước. Điều này có thể giảm lượng heap cần chuẩn bị lúc khởi động, nhất là trên máy có RAM lớn; heap vẫn có thể tăng khi ứng dụng cần thêm bộ nhớ.

Đây là thay đổi về cấu hình heap mặc định, độc lập với AOT cache và JEP 522. Khi so sánh startup giữa các phiên bản JDK, cần ghi lại việc có đặt **-Xms** hay không để tránh quy nhầm cải thiện cho AOT.

## 6. Tạo và sử dụng AOT cache trên JDK 26

Ví dụ dưới đây giả định ứng dụng được đóng gói trong app.jar và chạy bằng HotSpot JDK 26.

### Tạo cache

~~~bash
java -XX:AOTCacheOutput=app.aot -jar app.jar
~~~

Ở chế độ mặc định **AOTMode=auto**, việc chỉ định **AOTCacheOutput** khiến JVM thực hiện training; sau đó JVM khởi chạy tiến trình thứ hai để assembly và ghi tệp app.aot. Trong lần training, hãy chạy workload đại diện cho cách ứng dụng thực sự được sử dụng. Với dịch vụ web, cần đưa vào các luồng khởi tạo và request quan trọng thay vì chỉ khởi động rồi kết thúc ngay.

Nên training trong môi trường kiểm thử hoặc môi trường có thể kiểm soát side effect. Không để một lần training vô tình gửi email, tạo giao dịch, ghi dữ liệu nghiệp vụ hoặc gọi dịch vụ bên ngoài theo cách không an toàn.

### Dùng cache khi chạy ứng dụng

~~~bash
java -XX:AOTCache=app.aot -jar app.jar
~~~

Có thể ghi rõ chế độ mặc định và bật log để xác nhận JVM có dùng cache:

~~~bash
java -XX:AOTMode=auto -XX:AOTCache=app.aot -Xlog:aot -Xlog:gc*,safepoint -jar app.jar
~~~

Ở chế độ **auto**, nếu cache không tồn tại hoặc không tương thích, JVM tiếp tục chạy ứng dụng mà không dùng cache. Đây là hành vi phù hợp cho môi trường production vì cache chỉ là tối ưu hóa. Dùng **-XX:AOTMode=on** khi cần kiểm tra fail-fast: JVM sẽ báo lỗi và dừng nếu không thể nạp cache. Không nên dùng chế độ nghiêm ngặt này một cách vô thức trong production.

### Điều kiện tương thích và tái tạo cache

AOT cache gắn với các yếu tố chính:

- Ứng dụng và cách khai báo class path, JAR hoặc module path.
- JDK release dùng để tạo cache.
- Hệ điều hành và kiến trúc CPU.
- Các tùy chọn JVM có ảnh hưởng đến khả năng tương thích, chẳng hạn một số JVMTI agent hoặc cơ chế biến đổi bytecode.

Nếu thay đổi một trong các yếu tố trên, hãy tạo lại cache. Đặc biệt, khi thay JDK release, cập nhật artifact ứng dụng hoặc chuyển sang hệ điều hành/kiến trúc khác, không nên mặc định tệp cache cũ vẫn dùng được. Nếu cache không tương thích, hãy đọc log AOT để tìm nguyên nhân thay vì giả định JVM đang tận dụng cache.

## 7. Cách đánh giá hiệu quả đúng

Một lần khởi động nhanh hơn chưa đủ để kết luận cấu hình tốt hơn. Nên so sánh ít nhất các tình huống sau:

1. Không dùng AOT cache.
2. Dùng cache ở lần khởi động lạnh, khi tệp cache chưa có sẵn trong filesystem page cache.
3. Dùng cache ở lần khởi động ấm, khi dữ liệu cache đã được hệ điều hành giữ trong bộ nhớ.

Giữ cùng JDK build, artifact, cấu hình JVM, giới hạn CPU/RAM và workload. Đo thời gian từ lúc tiến trình bắt đầu đến khi ứng dụng thực sự sẵn sàng nhận việc; sau đó đo riêng thời gian warmup và thời điểm latency/throughput ổn định.

Theo dõi thêm:

- **AOT:** dùng **-Xlog:aot** để xác nhận cache được nạp hay bị bỏ qua và xem lý do.
- **GC và safepoint:** dùng **-Xlog:gc*,safepoint** hoặc JFR để quan sát thời gian GC, pause, CPU và tần suất cấp phát.
- **Ứng dụng:** đo readiness, latency theo percentile, throughput, CPU, heap và resident memory.
- **Tính đại diện:** workload training cần bao phủ các luồng khởi tạo và phương thức quan trọng. Cache được huấn luyện bằng workload không đại diện có thể đem lại lợi ích thấp hoặc không phản ánh hành vi production.

Khi lựa chọn GC, hãy dựa trên yêu cầu độ trễ, throughput, kích thước heap và đặc điểm workload. JEP 516 loại bỏ giới hạn tương thích object cache từng khiến ZGC không sử dụng được một số tối ưu hóa AOT; nó không biến một GC thành lựa chọn tốt nhất cho mọi ứng dụng. Với G1, có thể hưởng lợi thêm từ JEP 522 nếu workload chịu ảnh hưởng bởi chi phí cập nhật tham chiếu. Hãy đo riêng từng thay đổi để biết phần cải thiện đến từ đâu.

## 8. Những hiểu nhầm cần tránh

- **AOT cache không phải native image.** Ứng dụng vẫn cần JVM và vẫn chạy qua runtime của HotSpot.
- **AOT cache không thay thế GC.** GC vẫn quản lý heap trong suốt thời gian chạy.
- **AOT cache không phải snapshot toàn bộ trạng thái ứng dụng.** Không dùng nó để lưu phiên người dùng, giao dịch hoặc dữ liệu nghiệp vụ.
- **GC-neutral không có nghĩa không tốn chi phí.** Stream object cần CPU và công việc dựng object; lợi ích đến từ khả năng tương thích và việc chồng lấp công việc với startup.
- **AOT không bảo đảm mọi ứng dụng khởi động nhanh hơn cùng một tỷ lệ.** Kết quả phụ thuộc số lớp cần nạp, object được cache, workload training, filesystem page cache, CPU, I/O và cấu hình JVM.
- **JEP 516 và JEP 522 là tính năng đã được đưa vào JDK 26.** Không cần bật preview bằng **--enable-preview** để dùng hai cải tiến này. Các tùy chọn **-XX** là tùy chọn của HotSpot, không phải cam kết tương thích của Java SE cho mọi JVM.

## Kết luận

GC ảnh hưởng đến AOT object cache vì mỗi collector có thể yêu cầu cách bố trí đối tượng và tham chiếu khác nhau trong heap. JEP 516 của JDK 26 bổ sung cách lưu và nạp object theo định dạng độc lập với GC, cho phép HotSpot dùng AOT object caching với cả ZGC. Cơ chế này giúp giảm công việc lặp lại lúc startup và hỗ trợ warmup; GC và JIT vẫn tiếp tục làm việc bình thường sau đó. JEP 522 cải thiện riêng throughput của G1 bằng cách giảm đồng bộ trên card table. Muốn nhận biết lợi ích thực tế, hãy tạo cache bằng workload đại diện, kiểm tra log và đo startup, warmup, GC cùng tài nguyên trên đúng môi trường triển khai.

## Tài liệu tham khảo

- [JEP 516: Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516)
- [JEP 483: Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483)
- [JEP 515: Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515)
- [JEP 522: G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522)
- [The java Command – JDK 26, mục Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Significant Changes in JDK 26 Release](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
- [Performance Improvements in JDK 26 – Inside.java](https://inside.java/2026/06/09/jdk-26-performance-improvements/)
