# Nâng cấp JDK 17 lên 21: hành vi mặc định và khả năng tương thích thư viện

Nâng cấp từ JDK 17 lên JDK 21 là một bước chuyển có nhiều lợi ích: nhận các bản cập nhật nền tảng, cải thiện hiệu năng và bảo mật, dùng các API Java mới, đồng thời có thể áp dụng virtual threads cho hệ thống I/O đồng thời cao. Tuy nhiên, việc đổi JDK chạy ứng dụng không chỉ là đổi một giá trị trong `JAVA_HOME`. Hành vi mặc định của một số API đã thay đổi trong các bản JDK 18–21; thư viện, framework, plugin build, annotation processor và công cụ kiểm thử cũng phải tương thích với JDK mới.

Đặc biệt, một dự án có thể biên dịch thành công nhưng vẫn lỗi khi khởi động, khi tạo proxy bằng reflection, khi chạy agent kiểm thử hoặc khi đọc file văn bản có encoding phụ thuộc hệ điều hành. Một dependency có thể hỗ trợ JDK 21 về mặt bytecode nhưng chưa hỗ trợ phiên bản framework đang dùng. Một plugin có thể không chạy trên JDK 21 dù ứng dụng được cấu hình biên dịch về Java 17.

Để migration có thể kiểm soát, cần xác định rõ mục tiêu tương thích, nhận diện thay đổi từ JDK 17 đến 21, kiểm kê thư viện theo đúng classpath, nâng build tool và plugin theo ma trận hỗ trợ, sau đó kiểm chứng artifact trên runtime đích. Bài này tập trung vào những khác biệt thực tế của JDK 17 → 21 và cách đánh giá khả năng tương thích của toàn bộ hệ sinh thái thư viện.

## 1. Xác định chính xác mục tiêu nâng cấp

Trước khi thay đổi, hãy phân biệt các khái niệm thường bị gọi chung là “phiên bản Java”:

| Thành phần | Vai trò | Điều cần xác nhận |
|---|---|---|
| JDK chạy Gradle/Maven | JVM khởi chạy tiến trình build và plugin build | Wrapper, plugin và build logic có chạy trên JDK 21 không? |
| JDK compiler/toolchain | Compiler dùng để biên dịch source | Compiler có hiểu ngôn ngữ và API mục tiêu không? |
| Source/API target | Mức ngôn ngữ, bytecode và API Java mà artifact cam kết hỗ trợ | Artifact có cần tiếp tục chạy trên Java 17 không? |
| JDK runtime | JVM thực tế khởi chạy ứng dụng | Container, máy chủ, CI và môi trường production có dùng đúng JDK 21 không? |
| Framework/dependency | Thư viện và nền tảng mà ứng dụng nạp | Các phiên bản có hỗ trợ JDK 21 và tương thích với nhau không? |

Hai hướng migration có mục tiêu khác nhau:

**Hướng A — chuyển runtime lên Java 21:** ứng dụng sẽ chạy trên JDK 21 và có thể sử dụng API Java 21. Khi đó compiler có thể đặt `--release 21`, nếu không cần duy trì khả năng chạy trên Java 17.

**Hướng B — dùng JDK 21 để build nhưng vẫn hỗ trợ runtime Java 17:** compiler chạy bằng JDK 21 nhưng source/API target giữ ở Java 17, thường qua toolchain và `--release 17`. Cách này hữu ích cho thư viện hoặc sản phẩm cần phát hành artifact dùng được trên cả runtime 17. Tuy nhiên, processor, plugin và công cụ build vẫn phải chạy được trên JDK 21; đồng thời cần test artifact trên cả runtime 17 và 21.

Không nên kết luận một dự án đã “lên Java 21” chỉ vì `java -version` hiển thị 21. Hãy ghi riêng JDK chạy build, JDK compiler, mức API/bytecode và JDK runtime của artifact.

## 2. Những thay đổi đáng chú ý từ JDK 17 đến JDK 21

JDK 21 tích lũy thay đổi từ các bản phát hành 18, 19, 20 và 21. Không phải tất cả đều làm thay đổi hành vi của ứng dụng đang chạy. Cần phân loại thành thay đổi mặc định, API mới, tính năng tùy chọn, tính năng preview và thay đổi công cụ.

### 2.1. Charset mặc định chuyển sang UTF-8

**Điểm cần chú ý:** cần kiểm tra toàn bộ luồng văn bản.

Thay đổi có phạm vi ảnh hưởng rộng nhất trong nhóm hành vi mặc định là JEP 400, được áp dụng từ JDK 18. Trên JDK 17, charset mặc định của JVM thường phụ thuộc locale và cấu hình của hệ điều hành. Ví dụ, máy Windows có thể dùng một code page cục bộ, trong khi máy Linux thường dùng UTF-8. Trên JDK 18 trở đi, UTF-8 trở thành charset mặc định của các API Java sử dụng default charset, trừ khi có cơ chế tương thích được cấu hình theo quy định của JDK.

Điều này có thể làm thay đổi cách đọc hoặc ghi dữ liệu của mã nguồn đang dựa vào charset mặc định. Các API cần rà soát gồm:

- `new String(byte[])` và `String.getBytes()` không truyền charset.
- `FileReader` và `FileWriter` dùng constructor không chỉ định charset.
- `InputStreamReader` và `OutputStreamWriter` không truyền charset.
- `Scanner` hoặc `Formatter` khi dùng overload phụ thuộc default charset.
- Các thư viện đọc/ghi file text mà tài liệu cho biết chúng dùng default charset.
- Script, file cấu hình, CSV, log, dữ liệu import/export và file trao đổi với hệ thống cũ.

Ví dụ dễ gặp:

```java
// Phụ thuộc default charset của JVM.
String content = new String(bytes);
byte[] output = content.getBytes();

// Xác định rõ encoding của giao thức/file.
String utf8Content = new String(bytes, StandardCharsets.UTF_8);
byte[] utf8Output = content.getBytes(StandardCharsets.UTF_8);
```

Với file, nên chỉ định charset ngay tại API đọc/ghi:

```java
Path path = Path.of("data", "customers.csv");

String content = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, content, StandardCharsets.UTF_8);

try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    // Đọc từng dòng và xử lý dữ liệu.
}
```

`Files.readString(Path)` và `Files.writeString(Path, ...)` đã mặc định dùng UTF-8 từ khi được bổ sung trong JDK 11. Không được giả định mọi API cũ đều có cùng quy tắc. Cần đọc Javadoc của overload đang sử dụng.

Một số API có quy tắc riêng, không dùng default charset. Ví dụ, `Properties.load(InputStream)` diễn giải byte theo ISO-8859-1 theo hợp đồng API; `Properties.load(Reader)` phụ thuộc cách tạo Reader. Vì vậy, không nên sửa hàng loạt chỉ dựa trên tên lớp. Hãy xác định encoding thực tế của dữ liệu và hợp đồng của API.

Console cũng cần được xem riêng: charset của console có thể phụ thuộc môi trường terminal và không nhất thiết giống default charset dùng cho file. Trên các JDK hỗ trợ, `Console.charset()` cho biết charset của console. Khi trao đổi dữ liệu qua giao thức, file hoặc message, hãy dùng encoding được quy định bởi hợp đồng, thường là UTF-8, thay vì lấy charset console hoặc default charset làm chuẩn.

Khi kiểm thử, nên dùng dữ liệu có dấu tiếng Việt, ký tự ngoài ASCII, emoji nếu nghiệp vụ cho phép, và dữ liệu có byte không hợp lệ. Kiểm tra cả chiều đọc, chiều ghi, round-trip và hệ thống nhận dữ liệu. Một file có thể hiển thị đúng trên máy phát hành nhưng sai khi được mở ở máy khác.

JDK 18+ có thuộc tính `native.encoding` để phản ánh encoding gốc của môi trường trong các triển khai hỗ trợ. Một số cấu hình JDK cung cấp chế độ tương thích `file.encoding=COMPAT`; đây chỉ nên là biện pháp chuyển tiếp sau khi đã xác minh với vendor/JDK cụ thể. Giải pháp bền vững là chỉ định charset rõ ràng tại ranh giới dữ liệu.

### 2.2. Virtual threads trở thành tính năng chính thức

JDK 21 hoàn tất virtual threads qua JEP 444. Virtual thread là thread nhẹ do JVM quản lý, phù hợp với mô hình mỗi tác vụ I/O có một thread riêng. Ứng dụng có thể tạo số lượng lớn tác vụ đồng thời mà không cần duy trì số lượng platform thread tương ứng.

Ví dụ sử dụng executor tạo virtual thread cho từng task:

```java
try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> response = executor.submit(() -> callRemoteService());
    System.out.println(response.get());
}
```

Đây là API chính thức trong JDK 21. Tuy vậy, việc chuyển sang virtual threads là thay đổi kiến trúc thực thi, không phải thao tác tự động làm mọi ứng dụng nhanh hơn.

Những điểm cần đánh giá:

- Virtual threads phù hợp với workload có nhiều thao tác chờ I/O; chúng không làm tăng tốc tính toán CPU-bound.
- Không nên tạo pool virtual thread nhỏ để giới hạn số lượng virtual thread như cách pool platform thread. Thay vào đó, giới hạn tài nguyên thực sự như connection pool, remote concurrency hoặc semaphore.
- Virtual thread không nên bị giữ trong cấu trúc đồng bộ dài hạn khi đang chờ I/O.
- Trong JDK 21, virtual thread có thể bị pin vào carrier thread khi blocking bên trong `synchronized` hoặc khi thực thi native/foreign call. Cần xem xét các vùng này nếu áp dụng virtual threads trên tải cao.
- Theo dõi sự kiện `jdk.VirtualThreadPinned` bằng Java Flight Recorder khi cần điều tra pinning.
- `ThreadLocal` vẫn có ngữ nghĩa theo từng thread. Nếu tạo rất nhiều virtual thread, dữ liệu lớn trong ThreadLocal có thể làm tăng bộ nhớ đáng kể.
- Virtual threads là daemon threads; ứng dụng cần quản lý vòng đời task/executor và shutdown rõ ràng, không dựa vào việc một virtual thread giữ JVM sống.

Nếu ứng dụng hiện dùng thread pool để bảo vệ một tài nguyên giới hạn, hãy giữ cơ chế giới hạn tài nguyên ở đúng nơi. Không chuyển toàn bộ pool sang virtual thread rồi vô tình cho phép hàng nghìn request đồng thời gọi cùng một database hoặc dịch vụ ngoài.

Các framework web, JDBC driver, HTTP client, logging context, tracing agent và thư viện dùng ThreadLocal cần được xác minh khi ứng dụng chuyển sang mô hình virtual thread. Một thư viện tương thích JDK 21 không đồng nghĩa với việc nó đã tối ưu hoặc an toàn cho mô hình virtual thread.

### 2.3. Dynamic agent loading phát ra cảnh báo mới

JEP 451 trong JDK 21 đưa ra cảnh báo khi Java agent được nạp động vào một JVM đang chạy thông qua cơ chế attach. Điều này ảnh hưởng đến một số công cụ kiểm thử, mock, profiler, debugger hoặc công cụ quan sát dùng Byte Buddy/Instrumentation để gắn agent sau khi JVM khởi động.

Ví dụ, test suite có thể chạy bình thường trên JDK 17 nhưng bắt đầu hiển thị cảnh báo khi một thư viện tự attach agent trên JDK 21. Cảnh báo không nhất thiết có nghĩa test đã thất bại, nhưng cho biết cách nạp agent này có thể bị hạn chế trong các JDK tương lai.

Hướng xử lý nên theo thứ tự:

1. Xác định chính xác thư viện hoặc plugin nào đang attach agent.
2. Kiểm tra version mới có hỗ trợ cơ chế nạp agent lúc JVM khởi động không.
3. Ưu tiên cấu hình agent bằng tùy chọn JVM `-javaagent` từ đầu tiến trình nếu công cụ hỗ trợ.
4. Nếu có lý do hợp lệ phải cho phép dynamic attach, đánh giá tùy chọn `-XX:+EnableDynamicAgentLoading` trong đúng phạm vi test/tooling và ghi lại quyết định.
5. Không thêm tùy chọn cho phép toàn cục chỉ để che cảnh báo khi chưa xác định nguồn gốc.

Kiểm tra các thành phần như Mockito, Byte Buddy, profiler, coverage agent, APM agent, test framework và plugin chạy test. Không phải mọi agent đều bị ảnh hưởng giống nhau: agent truyền qua `-javaagent` khi khởi động khác với agent được attach động sau đó.

### 2.4. Strong encapsulation của JDK đã được áp dụng từ JDK 17

JEP 403 đã hoàn tất việc đóng gói mạnh các thành phần nội bộ của JDK từ JDK 17. Vì vậy, khi di chuyển từ 17 lên 21, đây không phải thay đổi hoàn toàn mới. Tuy nhiên, thư viện cũ có thể vẫn đang dựa vào package nội bộ hoặc cơ chế reflection không được hỗ trợ, và JDK 21 có thể làm lộ thêm những điểm phụ thuộc mới.

Các dấu hiệu thường gặp:

- `InaccessibleObjectException` khi thư viện gọi `setAccessible(true)` trên thành phần không được mở.
- `IllegalAccessError` hoặc `IllegalAccessException` khi truy cập class/member không được export/open.
- Cảnh báo hoặc lỗi liên quan tới package `sun.*`, `com.sun.*` hay API nội bộ khác.
- Proxy/bytecode library thất bại khi tạo class hoặc truy cập constructor/method bằng reflection.

Tùy chọn `--illegal-access` đã không còn là giải pháp mở rộng quyền truy cập đáng tin cậy từ JDK 17; không nên dùng nó như cách sửa lỗi migration. `--add-opens` có thể mở một package cụ thể cho một module cụ thể, nhưng đó là biện pháp tương thích có phạm vi và cần được ghi nhận. Ưu tiên nâng thư viện, dùng API công khai hoặc thay đổi cách tích hợp.

Khi phải dùng `--add-opens`, hãy ghi rõ package nào, module nào cần quyền truy cập, lỗi gốc là gì, phạm vi môi trường và thời hạn gỡ bỏ. Tránh mở hàng loạt package của JDK trong production chỉ để làm ứng dụng khởi động được.

### 2.5. API và ngôn ngữ mới được hoàn tất trong JDK 21

JDK 21 đưa một số tính năng từ preview ở các bản trước thành tính năng chính thức:

| Tính năng | JEP | Ý nghĩa đối với migration |
|---|---:|---|
| Record Patterns | 440 | Có thể phân rã record trong pattern matching; kiểm tra compiler và thư viện phân tích source nếu dùng |
| Pattern Matching for switch | 441 | Mở rộng switch với pattern; cần chú ý source level và công cụ phân tích/format mã |
| Virtual Threads | 444 | API thread nhẹ chính thức; có thể thay đổi mô hình concurrency khi chủ động áp dụng |
| Sequenced Collections | 431 | Bổ sung các interface và thao tác truy cập phần tử đầu/cuối, đảo thứ tự cho collection có thứ tự |
| Generational ZGC | 439 | Cải tiến ZGC có thể bật để thử nghiệm; không phải mặc định bắt buộc của mọi ứng dụng |
| Key Encapsulation Mechanism API | 452 | Bổ sung API mật mã; cần kiểm tra provider và use case nếu ứng dụng sử dụng |

Các tính năng mới không tự động làm mã nguồn cũ thay đổi hành vi. Rủi ro thường xuất hiện khi dự án bắt đầu sử dụng API mới, nâng compiler/source level, hoặc thư viện được cập nhật để tận dụng API mới.

JDK 21 cũng có một số tính năng preview/incubator như String Templates, Structured Concurrency, Scoped Values, Unnamed Patterns and Variables, Unnamed Classes and Instance Main Methods và Vector API ở các mức preview/incubator tương ứng. Chúng không có cùng cam kết ổn định như API chính thức. Không nên đưa tính năng preview vào đường phát hành production nếu chưa chấp nhận rõ ràng yêu cầu bật preview, phụ thuộc phiên bản và rủi ro thay đổi ở JDK tiếp theo.

### 2.6. Sequenced Collections và mã collection tự viết

JEP 431 bổ sung `SequencedCollection`, `SequencedSet` và `SequencedMap`, đồng thời thêm các phương thức như `getFirst()`, `getLast()` và `reversed()` cho các kiểu collection có thứ tự phù hợp.

Đối với ứng dụng thông thường, đây là API bổ sung. Nhưng thư viện tự định nghĩa collection hoặc class triển khai các interface mở rộng từ `List`, `Deque`, `SortedSet`, `Map` có thể gặp vấn đề source compatibility nếu đã tự khai báo phương thức cùng tên hoặc có quan hệ kiểu phức tạp.

Khi nâng compiler lên Java 21, cần biên dịch lại các implementation collection tùy chỉnh và kiểm tra:

- Method trùng tên/chữ ký với phương thức mới.
- Default method và xung đột khi nhiều interface cung cấp cùng phương thức.
- Hợp đồng thứ tự phần tử của collection tự viết.
- Ý nghĩa của view đảo thứ tự và thao tác mutation qua view.
- Các thư viện collection, ORM hoặc framework cung cấp wrapper/proxy cho collection.

Nếu một thư viện được biên dịch trước đó nhưng chạy trên JDK 21, cần kiểm tra binary compatibility và hành vi runtime. Nếu source được biên dịch lại, cần kiểm tra cả source compatibility.

### 2.7. Locale, timezone, Unicode và dữ liệu môi trường

JDK chứa dữ liệu locale, Unicode, timezone và danh sách chứng thư/thuật toán bảo mật được cập nhật theo các bản phát hành. Không nên giả định mọi kết quả định dạng chuỗi, ngày giờ hoặc dữ liệu locale sẽ giống tuyệt đối giữa hai vendor hoặc hai bản update JDK.

Các vùng cần kiểm tra:

- `DateTimeFormatter`, `NumberFormat`, `DecimalFormat`, `DateFormat` và dữ liệu locale.
- Định dạng số thập phân, dấu phân cách hàng nghìn, ký hiệu tiền tệ và tên tháng/ngày.
- `ZoneId`, quy tắc DST và dữ liệu timezone của các khu vực.
- Unicode normalization, case conversion, collation và xử lý ký tự mở rộng.
- Dữ liệu chứng thư CA, TLS protocol, cipher suite và thuật toán mật mã bị vô hiệu hóa.

Không nên so sánh chuỗi định dạng locale như thể đó là giao thức ổn định. Nếu dữ liệu được lưu trữ hoặc trao đổi giữa các hệ thống, hãy dùng format xác định như ISO-8601 cho ngày giờ và quy định locale/charset rõ ràng. Với timezone, lưu thời điểm theo `Instant` hoặc timestamp có offset khi phù hợp, và chỉ chuyển sang múi giờ hiển thị ở lớp giao diện.

Các bản cập nhật JDK 17 và 21 của từng vendor có thể mang dữ liệu timezone/CA khác nhau. Hãy ghi vendor, build number và patch level, không chỉ ghi “Java 21”.

### 2.8. Garbage collector và hành vi hiệu năng

G1 vẫn là garbage collector mặc định phổ biến của HotSpot ở cả JDK 17 và 21. ZGC generational được bổ sung trong JDK 21 nhưng là lựa chọn cần chủ động bật và kiểm thử, không phải điều kiện bắt buộc khi nâng JDK.

Không nên kết luận hiệu năng sẽ tốt hơn chỉ vì runtime mới. Hiệu năng phụ thuộc workload, heap sizing, container limit, CPU, allocation rate, GC, JIT profile, thư viện và cách khởi động ứng dụng. JDK 21 có thể thay đổi tối ưu hóa JIT và runtime nội bộ; một số luồng có thể nhanh hơn, một số khác có thể thay đổi latency hoặc mức sử dụng bộ nhớ.

Trước và sau migration, so sánh trên cùng workload:

- Thời gian khởi động và thời gian warm-up.
- Throughput và latency percentile (p50, p95, p99).
- CPU, heap, non-heap, allocation rate và số lần/độ dài GC pause.
- Số thread, connection pool, queue depth và timeout.
- Tỷ lệ lỗi, retry và mức sử dụng tài nguyên trong tải kéo dài.

Nếu đổi GC hoặc JVM flags cùng lúc với đổi JDK, hãy ghi thành thay đổi riêng. Không trộn nhiều biến số rồi quy toàn bộ kết quả cho JDK.

### 2.9. API bị deprecated hoặc thành phần đã bị loại bỏ trước Java 17

Một số thành phần thường bị nhầm là bị loại bỏ khi nâng 17 lên 21, nhưng thực tế đã bị loại bỏ ở các phiên bản cũ hơn:

| Thành phần | Mốc thay đổi | Ý nghĩa khi nâng từ 17 lên 21 |
|---|---|---|
| Nashorn JavaScript Engine | Được deprecate JDK 11, loại bỏ JDK 15 | Đã không còn trong JDK 17; nếu ứng dụng vẫn cần JS engine phải dùng giải pháp riêng |
| Java EE/CORBA modules | Loại bỏ JDK 11 | Không phải thay đổi mới của JDK 21 |
| Pack200 | Loại bỏ JDK 14 | Không phải thay đổi mới của JDK 21 |
| RMI Activation | Loại bỏ JDK 17 | Đã không còn khi chạy trên JDK 17 |
| Applet API | Deprecated for removal từ JDK 17 | Cần lập kế hoạch loại bỏ nếu còn phụ thuộc |
| Security Manager | Deprecated for removal từ JDK 17 | JDK 21 vẫn có trạng thái deprecated; không nên xây tính năng mới dựa trên nó |
| Finalization | Deprecated for removal từ JDK 18 | Rà soát `finalize()` và chuyển sang quản lý tài nguyên tường minh |

Việc phân biệt mốc thay đổi giúp tránh quy lỗi sai cho JDK 21. Nếu một ứng dụng đã chạy ổn trên JDK 17, thành phần bị loại bỏ từ JDK 11/15/17 có thể đã được xử lý hoặc không nằm trên đường chạy đó. Tuy vậy, một thư viện mới hoặc một profile build khác có thể vô tình kích hoạt lại dependency cũ.

## 3. Các lớp tương thích của thư viện

Một thư viện “hỗ trợ Java 21” có thể mang nhiều ý nghĩa. Cần kiểm tra từng lớp sau.

### 3.1. Bytecode compatibility

Mỗi phiên bản Java có class file major version. Java 17 dùng major version 61; Java 21 dùng major version 65. JVM cũ không thể nạp class file được biên dịch cho major version cao hơn mà nó hỗ trợ.

| Java release | Class file major version |
|---|---:|
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |

Nếu ứng dụng được biên dịch bằng JDK 21 với target 21, artifact không thể chạy trên JDK 17. Nếu cần giữ runtime 17, phải biên dịch theo mức release 17 và tránh API chỉ có từ 18 trở đi.

Với `javac`, `--release` ràng buộc mức ngôn ngữ, bytecode và API nền tảng:

```bash
# Biên dịch bằng JDK 21 nhưng tạo artifact hướng tới Java 17.
javac --release 17 -d build/classes src/main/java/example/App.java

# Biên dịch và sử dụng API Java 21.
javac --release 21 -d build/classes src/main/java/example/App.java
```

Chỉ đặt `sourceCompatibility` và `targetCompatibility` có thể không đủ để ngăn việc sử dụng API mới hơn trong JDK đang chạy compiler. Hãy cấu hình toolchain và `--release` đúng theo mục tiêu hỗ trợ.

Với thư viện bên thứ ba, kiểm tra class file version của artifact khi nghi ngờ. Có thể dùng `javap -verbose` trên class cụ thể hoặc `jdeps` để hỗ trợ phân tích phụ thuộc. Tuy nhiên, bytecode version hợp lệ chỉ chứng minh JVM có thể đọc định dạng class ở mức đó; nó không chứng minh thư viện tương thích với API, module, reflection hay hành vi runtime.

### 3.2. Source compatibility và API compatibility

Source compatibility trả lời câu hỏi: source hiện tại có biên dịch được với compiler mới hay không? API compatibility trả lời: class/method/field mà ứng dụng đang gọi có còn tồn tại và giữ hợp đồng tương thích không?

Các vấn đề thường gặp:

- API deprecated bị loại bỏ hoặc thay đổi chữ ký.
- Overload mới làm lời gọi trước đây trở nên mơ hồ khi biên dịch lại.
- Default method mới gây xung đột với interface/class tự viết.
- Generic signature hoặc annotation processing thay đổi cách suy luận kiểu.
- Thư viện tự triển khai interface JDK và bị ảnh hưởng khi interface bổ sung method.
- Framework thay đổi package, module, lifecycle hoặc contract cấu hình.

Nếu một dependency chỉ được dùng dưới dạng binary và không compile lại, source compatibility của dependency không phải yếu tố duy nhất. Nhưng binary compatibility, linkage và hành vi runtime vẫn cần kiểm chứng trên JDK 21.

### 3.3. Runtime behavior compatibility

Thư viện có thể biên dịch và nạp thành công nhưng hoạt động khác vì phụ thuộc default charset, locale, timezone, TLS, reflection, thread scheduling, GC hoặc JVM options. Đây là lý do phải có integration/regression test trên runtime đích.

Hãy đọc release notes của thư viện qua các phiên bản từ baseline đến phiên bản dự kiến. Tập trung vào các mục:

- Java version support và minimum runtime.
- Breaking changes, behavior changes và deprecated API.
- Reflection, proxy, bytecode generation và JPMS.
- Threading, executor, ThreadLocal và virtual thread support.
- Charset, locale, date/time, serialization và protocol.
- TLS, cryptography, native library và OS support.
- Thay đổi dependency bắc cầu hoặc phiên bản framework được hỗ trợ.

Không chỉ đọc release notes của phiên bản cuối. Nếu nâng qua nhiều major version, cần đọc migration guide cho các major version trung gian để phát hiện bước chuyển bắt buộc.

### 3.4. Framework compatibility

Framework thường có ma trận tương thích riêng với JDK, build tool và thư viện nền tảng. Ví dụ, framework web có thể yêu cầu một phiên bản Spring Framework mới hơn; ORM có thể thay đổi bytecode enhancement; framework test có thể cần Mockito/Byte Buddy mới; plugin framework có thể yêu cầu Gradle/Maven mới.

Với mỗi framework quan trọng, xác minh:

- Phiên bản framework có công bố hỗ trợ Java 21 không.
- Phiên bản framework đó có tương thích với các thư viện hiện có không.
- Framework có yêu cầu nâng đồng bộ BOM, plugin hoặc driver không.
- Có thay đổi package/API/cấu hình buộc phải sửa source không.
- Có giới hạn với virtual threads, native image, reflection hoặc module system không.
- Phiên bản framework được hỗ trợ còn nằm trong thời hạn bảo trì của nhà cung cấp không.

Không lấy một câu “Java 21 compatible” trên trang sản phẩm làm bằng chứng cho toàn bộ stack. Cần đối chiếu chính xác version của framework, JDK, build plugin và dependency được quản lý.

### 3.5. Thư viện bytecode, reflection và proxy

Nhóm thư viện này thường nhạy với thay đổi compiler/JDK:

- ASM và các thư viện đọc/ghi bytecode.
- Byte Buddy và công cụ tạo subclass/proxy động.
- CGLIB và các thư viện proxy.
- Javassist hoặc thư viện instrument class.
- ORM enhancement và dependency injection framework.
- Coverage agent, mocking framework, APM và profiler.

Một thư viện bytecode cũ có thể không hiểu class file mới hoặc cấu trúc bytecode mới được compiler tạo ra. Một thư viện proxy có thể dùng reflection sâu vào JDK hoặc class framework. Khi nâng JDK, cần kiểm tra version tối thiểu của thư viện bytecode và các thành phần kéo nó vào.

Nếu lỗi chỉ xuất hiện khi test, hãy phân biệt thư viện runtime của ứng dụng với thư viện mocking/coverage/agent chỉ dùng trong test. Không nhất thiết phải thay đổi dependency production để xử lý một test agent cũ.

### 3.6. Annotation processor và compiler plugin

Annotation processor chạy trong compiler và có thể dùng compiler API hoặc API nội bộ. Các processor như Lombok, MapStruct, QueryDSL, Hibernate metamodel generator và processor tự viết cần được kiểm tra riêng.

Các câu hỏi cần trả lời:

- Processor có hỗ trợ JDK 21 và compiler API tương ứng không?
- Phiên bản processor có đồng bộ với thư viện runtime/API của nó không?
- Compiler plugin có chạy trên JDK 21 không?
- Generated source có compile theo source/API target của dự án không?
- Processor có xử lý record, sealed type, generic và annotation mới đúng không?
- Output có ổn định và tái tạo được trên build sạch không?

Đừng chỉ nâng dependency runtime. Nếu lỗi phát sinh trong annotation processing, thành phần cần nâng có thể là processor path hoặc compiler plugin.

### 3.7. JDBC driver, client và thư viện tích hợp

JDBC driver, HTTP client, messaging client và SDK của nhà cung cấp cần được kiểm tra trên cả JDK lẫn server/service version thực tế. Những thư viện này thường dùng TLS, socket, thread, native library hoặc serialization.

Kiểm tra:

- Driver có hỗ trợ Java 21 và phiên bản database đang chạy không.
- TLS/cipher/protocol và truststore có còn tương thích không.
- Connection pool có hoạt động đúng khi ứng dụng thay đổi mô hình thread không.
- Timeout, retry, interruption và cancellation có hành vi đúng không.
- SDK có dependency bắc cầu hoặc logging API gây xung đột không.
- Native/JNI library có binary phù hợp với OS/architecture/container không.

Không nâng driver hoặc SDK chỉ vì version mới hơn hỗ trợ JDK 21. Phải kiểm tra compatibility với server version, schema, protocol và các thành phần khác của stack.

### 3.8. Serialization và hợp đồng dữ liệu

Thư viện JSON/XML/serialization có thể thay đổi cách xử lý record, constructor, reflection, module access, enum, date/time và unknown field. Một thay đổi nhỏ có thể làm payload khác đi dù code vẫn compile.

Tạo bộ dữ liệu kiểm thử đại diện gồm:

- Payload cũ đã được lưu hoặc gửi từ các phiên bản trước.
- Dữ liệu null, thiếu field, field mới và field không biết.
- Ngày giờ, timezone, số thập phân và ký tự Unicode.
- Enum, polymorphic type, generic collection và nested object.
- Dữ liệu có format legacy cần duy trì tương thích ngược.

So sánh JSON/XML theo cấu trúc và hợp đồng, không chỉ so sánh chuỗi nếu thứ tự field hoặc whitespace không thuộc contract. Kiểm tra cả chiều serialize và deserialize.

## 4. Kiểm kê thư viện và xác định phiên bản mục tiêu

### 4.1. Lập danh mục theo classpath

Không gộp mọi dependency thành một danh sách. Với mỗi module, thu thập ít nhất:

| Classpath/configuration | Nội dung | Ví dụ |
|---|---|---|
| Compile | Thư viện cần để biên dịch mã chính | `compileClasspath` |
| Runtime | Thư viện được nạp khi chạy ứng dụng | `runtimeClasspath` |
| Test compile/runtime | Framework test, mock, test container và dependency kiểm thử | `testCompileClasspath`, `testRuntimeClasspath` |
| Annotation processor | Processor sinh source hoặc resource | `annotationProcessor`, `kapt`, KSP |
| Build/plugin | Plugin, buildscript và dependency của plugin | Gradle plugin DSL, `buildEnvironment`, Maven plugin realm |
| Generator task | Generator chạy như task/goal riêng | OpenAPI, Protobuf, Avro, jOOQ |

Một thư viện có thể xuất hiện ở nhiều classpath với version khác nhau. Ghi rõ version được yêu cầu và version được chọn sau conflict resolution, BOM, constraint hoặc dependency management.

### 4.2. Đối chiếu nguồn hỗ trợ chính thức

Với từng dependency quan trọng, tra cứu:

- Ma trận Java/JDK support của nhà cung cấp.
- Release notes và migration guide của version mục tiêu.
- Minimum supported Java version.
- Phiên bản Gradle/Maven hoặc framework plugin yêu cầu.
- Dependency bắc cầu quan trọng và version bị nâng kèm.
- Chính sách bảo trì và bảo mật của nhánh version.

Phân biệt rõ ba trạng thái:

- **Vendor-supported:** nhà cung cấp công bố hỗ trợ tổ hợp version đó.
- **Project-verified:** dự án đã chạy test/build trên tổ hợp đích và lưu bằng chứng.
- **Unknown:** chưa có tài liệu hoặc chưa có môi trường để xác minh.

Không gộp “vendor-supported” và “project-verified” thành một trạng thái. Một thư viện được nhà cung cấp hỗ trợ vẫn có thể xung đột với cấu hình hoặc dependency khác trong ứng dụng.

### 4.3. Ưu tiên dependency cần kiểm tra trước

Những thành phần nên được rà soát sớm:

1. Framework nền tảng và BOM quản lý dependency.
2. Build tool, compiler plugin, plugin đóng gói và plugin nội bộ.
3. Thư viện bytecode, reflection, proxy, instrumentation và agent.
4. Annotation processor và generator.
5. ORM, JDBC driver, connection pool và database migration tool.
6. JSON/XML, date/time, logging và security library.
7. Test framework, mocking, coverage và test container.
8. Native/JNI library, client hệ thống ngoài và SDK của nhà cung cấp.

Đây là thứ tự ưu tiên khảo sát, không phải thứ tự nâng cấp bắt buộc. Quan hệ phụ thuộc thực tế có thể yêu cầu thay đổi thứ tự.

## 5. Nâng cấp build tool và plugin cùng với JDK

### 5.1. Gradle

Gradle Wrapper cần tương thích với JDK chạy Gradle. Khả năng dùng JDK làm toolchain để biên dịch có thể khác với khả năng chạy chính Gradle trên JDK đó. Vì vậy, khi chuyển sang JDK 21, phải đối chiếu compatibility matrix chính thức của Gradle cho cả hai mục đích.

Kiểm tra:

- `gradle-wrapper.properties` và phiên bản Gradle Wrapper.
- `plugins {}` ở root và subproject.
- `pluginManagement` trong settings.
- `buildscript` classpath.
- `gradle/libs.versions.toml` nếu dùng version catalog.
- `buildSrc` và included build/convention plugin.
- Compiler toolchain và `options.release`.
- Test JVM, forked Java process và task dùng JDK riêng.

Các lệnh khảo sát hữu ích:

```bash
./gradlew --version
./gradlew projects
./gradlew buildEnvironment
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency <artifact> --configuration runtimeClasspath
```

`buildEnvironment` không thể hiện đầy đủ plugin DSL. Cần đọc khai báo plugin và plugin resolution riêng.

### 5.2. Maven

Maven Wrapper và Maven plugin phải chạy được trên JDK 21. Kiểm tra version Maven, Compiler Plugin, Surefire/Failsafe, Enforcer, JaCoCo, Spring Boot plugin, shade/assembly, code generation và plugin nội bộ.

Các lệnh khảo sát:

```bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree -Dverbose
./mvnw dependency:resolve-plugins
```

Trong multi-module Maven, xem cả parent POM, profile và plugin management. Version plugin được kế thừa có thể không nằm trong POM của module đang build.

### 5.3. Compiler và test JVM

JDK chạy Gradle/Maven không nhất thiết là JDK dùng cho compile/test. Cần xác minh riêng:

- JDK của daemon/tiến trình build.
- JDK toolchain dùng để compile.
- JDK dùng để chạy unit/integration test.
- JDK dùng để chạy application trong container.
- JDK dùng cho generator hoặc tiến trình fork riêng.

Nếu test chạy trên JDK 17 trong khi production chạy JDK 21, test pass chưa chứng minh runtime 21 tương thích. Nếu build chạy trên JDK 21 nhưng test vẫn chạy bằng 17, lỗi do agent hoặc test framework chỉ xuất hiện trên JDK 21 sẽ bị bỏ sót.

## 6. Quy trình migration từ JDK 17 lên JDK 21

### Bước 1: Chụp baseline trên JDK 17

Chốt commit, phiên bản JDK vendor/build, Wrapper, framework, dependency graph và kết quả build/test hiện tại. Lưu các cảnh báo và lỗi đã có trước migration để phân biệt với regression mới.

### Bước 2: Chọn chính sách tương thích

Quyết định sản phẩm sẽ chạy trên Java 21 hay vẫn phải hỗ trợ Java 17. Nếu giữ Java 17, xác định rõ compiler `--release 17`, runtime test matrix và giới hạn API được phép dùng. Nếu chuyển hẳn sang 21, xác định thời điểm artifact không còn hỗ trợ runtime 17.

### Bước 3: Kiểm tra build tool và JDK 21

Chọn phiên bản Gradle/Maven và plugin có hỗ trợ chạy trên JDK 21. Cập nhật Wrapper riêng, chạy task cấu hình nhẹ và build cơ bản. Không nâng framework/dependency cùng lúc nếu chưa xác định được build tool hoạt động.

### Bước 4: Cập nhật framework và dependency nền tảng

Đối chiếu BOM/framework matrix, xác định các phiên bản tương thích. Nâng dependency theo nhóm có quan hệ rõ ràng, ghi lại graph trước/sau và không tự ý override version do BOM quản lý nếu chưa đánh giá.

### Bước 5: Cập nhật compiler plugin, processor và generator

Nâng annotation processor, bytecode library, generator và compiler plugin theo yêu cầu JDK 21. Chạy lại generate trên build sạch, kiểm tra diff output và biên dịch toàn bộ generated source.

### Bước 6: Xử lý thay đổi hành vi mặc định

Rà soát charset mặc định, reflection/JPMS, dynamic agent loading, locale/timezone, TLS và JVM options. Sửa mã nguồn để dùng charset và format tường minh. Với agent, xác định công cụ attach và chuyển sang cấu hình startup agent khi có thể.

### Bước 7: Chạy test trên đúng JDK 21

Chạy compile, unit, integration, contract, smoke và test đóng gói trên JDK 21. Test phải sử dụng artifact và runtime gần với production, không chỉ chạy từ IDE hoặc classpath phát triển.

### Bước 8: Đánh giá hiệu năng và phát hành thử

So sánh hiệu năng với baseline, chạy soak test khi cần, đưa artifact vào môi trường đại diện và rollout theo từng bước. Chuẩn bị rollback trước khi chuyển lưu lượng production.

## 7. Ma trận kiểm chứng thư viện

Một bảng kiểm chứng nên thể hiện rõ nguồn bằng chứng và phạm vi test:

| Thành phần | Version hiện tại | Version mục tiêu | Hỗ trợ JDK 21 | Đã test trên JDK 21 | Rủi ro/ghi chú |
|---|---|---|---|---|---|
| Framework chính | ... | ... | Có/Không/Chưa rõ | Pass/Fail/Chưa chạy | BOM, migration guide |
| ORM | ... | ... | Có/Không/Chưa rõ | Pass/Fail/Chưa chạy | Reflection, proxy, JDBC |
| JDBC driver | ... | ... | Có/Không/Chưa rõ | Pass/Fail/Chưa chạy | DB/server version, TLS |
| JSON/XML | ... | ... | Có/Không/Chưa rõ | Pass/Fail/Chưa chạy | Record, reflection, format |
| Bytecode/proxy | ... | ... | Có/Không/Chưa rõ | Pass/Fail/Chưa chạy | ASM, Byte Buddy, JPMS |
| Test/mock/agent | ... | ... | Có/Không/Chưa rõ | Pass/Fail/Chưa chạy | Dynamic attach, `-javaagent` |
| Annotation processor | ... | ... | Có/Không/Chưa rõ | Pass/Fail/Chưa chạy | Compiler API, generated source |
| Build plugin | ... | ... | Có/Không/Chưa rõ | Pass/Fail/Chưa chạy | Gradle/Maven compatibility |
| Native/JNI | ... | ... | Có/Không/Chưa rõ | Pass/Fail/Chưa chạy | OS, architecture, binary |

Không để dấu `...` trong báo cáo chính thức. Nếu chưa có dữ liệu, ghi “chưa xác định” và gán người phụ trách. Một trạng thái “Có” ở cột hỗ trợ cần kèm URL/tài liệu hoặc release note; một trạng thái “Pass” cần kèm build/test run, commit và môi trường.

## 8. Bộ kiểm thử trọng yếu cho JDK 17 → 21

### 8.1. Charset và dữ liệu văn bản

- Đọc/ghi file UTF-8 có tiếng Việt và ký tự ngoài ASCII.
- Import/export CSV, JSON, XML, properties và file cấu hình legacy.
- Gửi/nhận message và HTTP payload có encoding rõ ràng.
- Kiểm tra dữ liệu được tạo bởi JDK 17 và đọc bởi JDK 21, cùng chiều ngược lại nếu cần hỗ trợ rollback.
- Kiểm tra API còn dựa vào default charset.

### 8.2. Reflection, proxy và bytecode

- Khởi động framework và tạo proxy/bean.
- ORM enhancement, lazy loading, entity proxy và serialization.
- Mocking framework, coverage agent, profiler và instrumentation.
- Chạy test với các module/package có giới hạn truy cập.
- Kiểm tra warning/lỗi `InaccessibleObjectException`, `IllegalAccessError` và class loading.

### 8.3. Agent và test infrastructure

- Chạy test suite với JDK 21 và quan sát cảnh báo dynamic agent loading.
- Xác định agent được nạp qua `-javaagent` hay attach động.
- Kiểm tra version Surefire/Failsafe, Gradle test worker và test launcher.
- Chạy test song song và kiểm tra cleanup, thread leak, file/socket leak.

### 8.4. Threading và virtual threads

Nếu ứng dụng chưa dùng virtual threads, kiểm tra các thư viện có giả định về platform thread hoặc ThreadLocal. Nếu chủ động áp dụng virtual threads, kiểm tra tải I/O, giới hạn connection, synchronized blocking, native call và JFR pinning event.

### 8.5. TLS, locale và thời gian

- Kết nối TLS đến database, broker, HTTP service và identity provider.
- Xác minh truststore, CA, cipher/protocol và chứng thư hết hạn.
- Kiểm tra định dạng số/ngày giờ theo locale nghiệp vụ.
- Kiểm tra timezone và DST tại khu vực có thay đổi quy tắc.
- So sánh serialization contract và timestamp qua các hệ thống.

### 8.6. Hiệu năng và vận hành

- So sánh startup, throughput, p95/p99, CPU, heap, GC và số thread.
- Kiểm tra container memory/CPU limit và JVM ergonomics.
- Chạy tải kéo dài để phát hiện memory leak hoặc cạn connection.
- Xác minh log, metric, trace, health check và graceful shutdown.

## 9. Những lỗi thường gặp và cách truy nguyên

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Tiếng Việt trong file bị lỗi sau migration | API dùng default charset; JDK 17 và 21 có default khác nhau | Tìm overload không chỉ định charset; kiểm tra byte input/output |
| Test xuất hiện cảnh báo agent | Test tool attach agent động | Nâng tool; xem cấu hình startup `-javaagent` và JEP 451 |
| `InaccessibleObjectException` | Thư viện reflection vào package JDK/module chưa mở | Truy stack trace; nâng thư viện hoặc thay API; chỉ dùng `--add-opens` có giới hạn |
| Compile lỗi trong processor | Annotation processor/compiler plugin cũ | Xem processor path, compiler JDK và version hỗ trợ |
| `UnsupportedClassVersionError` | Artifact hoặc dependency có bytecode mới hơn runtime | Kiểm tra class file version và JDK thực sự khởi chạy |
| Build hỏng trước khi compile | Gradle/Maven/plugin không chạy trên JDK 21 | Xác minh Wrapper, plugin và JDK của tiến trình build |
| Ứng dụng khởi động nhưng API sai | Runtime behavior, locale, charset, TLS hoặc framework behavior thay đổi | Chạy integration/contract test và so sánh baseline |
| Hiệu năng giảm | JIT/GC, heap sizing, container, workload hoặc dependency mới | So sánh profile và số liệu trong cùng điều kiện |
| Test pass nhưng production fail | Test chạy trên JDK hoặc image khác production | Chạy artifact cuối trên runtime/container đích |

Khi điều tra, hãy xác định lỗi thuộc tầng nào: build tool, compiler, processor, dependency runtime, JVM, container hay hệ thống ngoài. Lỗi xuất hiện trong Gradle task chưa chắc là lỗi của mã ứng dụng; lỗi xuất hiện trong unit test cũng có thể do test agent chứ không phải thư viện production.

## 10. Ví dụ: xử lý lỗi charset khi chuyển sang JDK 21

Giả sử một batch job đọc file CSV do hệ thống Windows cũ tạo ra. Trên JDK 17, máy chạy batch có default charset trùng với encoding của file nên dữ liệu tiếng Việt hiển thị đúng. Sau khi chuyển sang JDK 21, default charset là UTF-8; nếu file thực tế vẫn dùng Windows-1258 hoặc một code page khác, nội dung có thể bị lỗi hoặc phát sinh ký tự thay thế.

Quy trình xử lý:

1. Lưu một file đầu vào đại diện và xác định encoding thực tế từ hợp đồng với hệ thống gửi file hoặc bằng công cụ kiểm tra byte.
2. Xác định API đọc file đang dùng: `FileReader`, `InputStreamReader`, thư viện CSV hay một wrapper khác.
3. Kiểm tra API đó có dùng default charset không; không suy đoán từ tên thư viện.
4. Quy định charset của file trong hợp đồng tích hợp. Nếu nguồn gửi có thể chuyển UTF-8, thống nhất thời điểm và cách chuyển đổi.
5. Nếu phải tiếp tục nhận encoding legacy, chỉ định đúng charset cho luồng đọc đó; không đổi default charset toàn JVM để xử lý riêng một file.
6. Tạo test với tiếng Việt, ký tự đặc biệt, byte không hợp lệ và file lớn.
7. Kiểm tra file xuất ra, dữ liệu database và payload chuyển tiếp tới hệ thống khác.
8. Phát hành thử trên JDK 21 và xác nhận không làm thay đổi các luồng văn bản khác.

Ví dụ đọc file legacy khi đã xác định encoding:

```java
Charset sourceCharset = Charset.forName("windows-1258");
try (BufferedReader reader = Files.newBufferedReader(path, sourceCharset)) {
    // Parse CSV theo encoding đã được hợp đồng dữ liệu xác định.
}
```

Tên charset ở ví dụ chỉ minh họa. Phải xác nhận đúng encoding của nguồn thực tế. Không dùng một code page mặc định cho mọi file nếu các nguồn có hợp đồng khác nhau.

## 11. Ví dụ: test lỗi do dynamic agent loading

Giả sử unit test chạy với JDK 17 không có cảnh báo, nhưng trên JDK 21 log xuất hiện cảnh báo về việc một agent được attach động. Test vẫn có thể pass, tuy nhiên nhóm cần biết công cụ nào thực hiện thao tác này.

Các bước truy nguyên:

1. Kiểm tra log test, dependency test runtime và plugin chạy test.
2. Xác định mocking/coverage/profiling library nào dùng Instrumentation hoặc Byte Buddy.
3. Đọc tài liệu của version hiện tại và version mới về cách nạp agent.
4. Cấu hình agent khi khởi động JVM bằng `-javaagent` nếu công cụ hỗ trợ và cách này phù hợp.
5. Chỉ cân nhắc `-XX:+EnableDynamicAgentLoading` khi đã hiểu lý do cần dynamic attach và giới hạn phạm vi.
6. Chạy test suite trên JDK 21, xác nhận warning đã được xử lý theo chủ đích và test behavior vẫn đúng.

Không nên xóa test hoặc bỏ coverage chỉ để loại cảnh báo. Cũng không nên thêm một tùy chọn toàn cục mà không ghi nhận vì nó làm giảm khả năng nhận biết công cụ cũ trong các lần nâng cấp sau.

## 12. Quyết định phát hành và rollback

Trước khi phát hành production, phải xác định artifact nào đã được test, commit nào tạo ra artifact, JDK runtime và container image nào được sử dụng. Lưu checksum và kết quả test để có thể truy nguyên.

Nên phát hành theo canary, rolling hoặc blue-green tùy kiến trúc. Theo dõi tỷ lệ lỗi, latency, CPU, memory, GC, restart, connection pool và lỗi tích hợp. Đặt ngưỡng dừng trước khi rollout. Nếu vượt ngưỡng, dừng tăng lưu lượng và thực hiện phương án rollback đã chuẩn bị.

Rollback JDK cũng cần xét compatibility của artifact và dữ liệu. Artifact biên dịch target 21 không thể chạy lại trên JDK 17. Nếu cần rollback về runtime 17, phải giữ artifact được biên dịch target 17 hoặc có bản phát hành cũ tương ứng. Thay đổi schema/database cần tương thích giữa ứng dụng cũ và mới; không thể giả định chỉ đổi container image là đủ.

Nếu mục tiêu cuối cùng là Java 21, có thể giữ lại một release artifact JDK 17 để phục hồi nhanh trong thời gian rollout. Sau khi migration ổn định, cập nhật runbook, dependency matrix, cấu hình CI, image runtime và chính sách hỗ trợ phiên bản.

## 13. Hồ sơ hoàn thành migration JDK 17 → 21

Một đợt migration chỉ nên được đóng khi có thể bàn giao các bằng chứng sau:

1. **Mục tiêu phiên bản:** JDK chạy build, compiler/toolchain, source/API target và runtime đích.
2. **Baseline:** commit JDK 17, build log, dependency graph, plugin/generator inventory và kết quả test ban đầu.
3. **Compatibility matrix:** framework, thư viện, plugin, processor, agent, driver và native library; có nguồn hỗ trợ chính thức và trạng thái kiểm chứng.
4. **Behavior change register:** charset, dynamic agent loading, reflection/JPMS, virtual thread nếu áp dụng, locale/timezone, TLS và JVM flags.
5. **Migration change record:** các version/configuration đã nâng, lý do, commit và owner.
6. **Verification report:** compile, unit, integration, contract, smoke, performance, security và test trên artifact/container cuối.
7. **Release record:** artifact checksum, JDK vendor/build, container image, rollout và ngưỡng dừng.
8. **Recovery plan:** artifact cũ, runtime cũ, tương thích dữ liệu và cách xác nhận phục hồi.
9. **Follow-up:** deprecated API, workaround, rủi ro còn lại và thời hạn xử lý.

### Checklist trước khi đóng

- [ ] Đã xác định dự án chuyển runtime sang 21 hay vẫn hỗ trợ runtime 17.
- [ ] Đã cấu hình riêng JDK chạy build, compiler/toolchain và runtime.
- [ ] Build tool và toàn bộ plugin chạy được trên JDK 21.
- [ ] Dependency graph đã được kiểm tra trên compile/runtime/test/processor classpath.
- [ ] Framework và dependency quan trọng có nguồn hỗ trợ Java 21.
- [ ] Bytecode/proxy/reflection/agent và annotation processor đã được xác minh.
- [ ] Các API dùng default charset đã được rà soát và có encoding tường minh.
- [ ] Test có dữ liệu văn bản đa ngôn ngữ, locale, timezone và TLS phù hợp nghiệp vụ.
- [ ] Cảnh báo dynamic agent loading đã được truy nguyên và xử lý có chủ đích.
- [ ] Nếu dùng virtual threads, đã kiểm tra pinning, ThreadLocal và giới hạn tài nguyên.
- [ ] Artifact cuối đã chạy trên đúng JDK/container mục tiêu.
- [ ] Hiệu năng đã được so sánh với baseline trong cùng điều kiện.
- [ ] Có artifact rollback tương thích với runtime trước và phương án phục hồi dữ liệu.
- [ ] Compatibility matrix, runbook và tài liệu vận hành đã được cập nhật.

Nâng cấp JDK 17 lên 21 thành công khi toàn bộ tổ hợp build tool, compiler, framework, dependency, agent và runtime hoạt động đúng theo mục tiêu hỗ trợ đã chọn. Kiểm tra các thay đổi mặc định như UTF-8, nhận diện ràng buộc của thư viện và xác minh trên artifact cuối giúp migration tránh được những lỗi chỉ xuất hiện khi chạy thật. Bằng chứng tương thích và kế hoạch rollback là điều kiện để đưa JDK 21 vào production một cách có kiểm soát.
