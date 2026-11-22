# Java 10: Nhóm thay đổi ngôn ngữ, API và vận hành JVM

> Phạm vi: Những điểm được đưa vào JDK 10 (2018) và **vẫn hữu ích, còn được hỗ trợ trong Java hiện đại**. Các ví dụ sử dụng Java 17+ và cũng áp dụng với những JDK mới hơn. Với tùy chọn JVM, cần kiểm tra tài liệu của đúng bản phân phối và phiên bản đang chạy vì chúng thuộc HotSpot, không phải cú pháp ngôn ngữ Java.

## 1. Bức tranh tổng thể

Java 10 không chỉ bổ sung cú pháp `var`. Phiên bản này cũng giúp tạo collection không thể chỉnh sửa qua API công khai, làm rõ thao tác `Optional` và I/O, bổ sung cách xử lý locale, đồng thời cải thiện bộ gom rác, khởi động JVM và nhận biết tài nguyên container.

| Nhóm | Điểm thay đổi từ Java 10 | Giá trị còn dùng |
| --- | --- | --- |
| Ngôn ngữ | Suy luận kiểu biến cục bộ bằng `var` (JEP 286) | Giảm lặp kiểu khi khai báo, vẫn kiểm tra kiểu tĩnh |
| Collections | `List.copyOf`, `Set.copyOf`, `Map.copyOf`; `Collectors.toUnmodifiable...` | Tạo bản chụp cấu trúc collection, hạn chế sửa ngoài ý muốn |
| API thường dùng | `Optional.orElseThrow()`, `Reader.transferTo(Writer)`, `ByteArrayOutputStream.toString(Charset)` | Code ngắn, rõ ý và tránh lỗi charset |
| Quốc tế hóa | Các Unicode locale extension `cu`, `fw`, `rg`, `tz` (JEP 314) | Quy định tiền tệ, ngày bắt đầu tuần, vùng và múi giờ theo locale |
| HotSpot | G1 parallel Full GC, GC interface, thread-local handshakes (JEP 307/304/312) | Nền tảng cải thiện hiệu năng và quản lý tạm dừng JVM |
| Triển khai | Application CDS (JEP 310), container awareness, heap sizing | Cải thiện khởi động và cấp tài nguyên cho dịch vụ |
| Hệ sinh thái | Root CA certificates (JEP 319), đánh số phiên bản theo thời gian (JEP 322) | Vận hành TLS và kiểm tra phiên bản có hệ thống |

## 2. Ngôn ngữ: Local-variable type inference với `var` (JEP 286)

### 2.1. Cơ chế

`var` cho phép trình biên dịch suy ra **kiểu tĩnh** của một biến cục bộ từ biểu thức khởi tạo:

~~~java
var count = 3;                           // int
var title = "Java";                      // String
var names = java.util.List.of("An", "Binh"); // List<String>
~~~

Sau khi suy luận, kiểu được cố định tại **thời điểm biên dịch**. `var` không phải kiểu `Object` mặc định, không phải biến động và không làm Java trở thành ngôn ngữ dynamic typing. Ví dụ `var count = 3; count = "ba";` là lỗi biên dịch vì `count` có kiểu `int`.

`var` sử dụng được ở khai báo biến cục bộ có giá trị khởi tạo, biến vòng `for`, biến vòng for-each và biến tài nguyên trong `try-with-resources`:

~~~java
for (var i = 0; i < 3; i++) {
    System.out.println(i);
}
for (var name : java.util.List.of("An", "Binh")) {
    System.out.println(name);
}
try (var reader = new java.io.StringReader("abc")) {
    System.out.println(reader.read());
}
~~~

### 2.2. Giới hạn phải nhớ

- Không dùng `var` làm kiểu trường của lớp, kiểu trả về của phương thức hoặc kiểu tham số phương thức thông thường.
- Phải có biểu thức khởi tạo có thể suy ra kiểu: `var value;` và `var value = null;` đều không hợp lệ.
- Lambda hoặc method reference đứng một mình cần kiểu đích, nên `var operation = x -> x + 1;` không biên dịch. Có thể khai báo `IntUnaryOperator operation = x -> x + 1;`.
- `var array = {1, 2, 3};` không hợp lệ; dùng `var array = new int[] {1, 2, 3};`.
- Không khai báo nhiều biến trong cùng một câu lệnh `var a = 1, b = 2;`.
- Tránh `var list = new ArrayList<>();` khi kiểu phần tử không rõ: Java có thể suy luận `ArrayList<Object>`. Ưu tiên `var list = new ArrayList<String>();` hoặc `List<String> list = new ArrayList<>();`.

### 2.3. Cách dùng tốt

Dùng `var` khi kiểu nhìn ngay ra từ bên phải, đặc biệt với phép khởi tạo hay vòng lặp ngắn. Dùng kiểu tường minh khi kiểu là một phần quan trọng của ý nghĩa, cần biểu diễn abstraction (ví dụ `List` thay cho `ArrayList`), hoặc khi biểu thức khởi tạo quá dài khiến người đọc phải dò định nghĩa mới hiểu biến. `var` giúp giảm lặp cú pháp, không thay thế tên biến rõ nghĩa.

## 3. API collection không thể chỉnh sửa

### 3.1. `copyOf` và sự khác nhau giữa snapshot với view

Java 10 bổ sung `List.copyOf(Collection)`, `Set.copyOf(Collection)`, `Map.copyOf(Map)`. Với nguồn có thể chỉnh sửa, kết quả là một collection **không cho thêm, bớt hoặc thay phần tử qua API collection**, và thay đổi về sau của collection nguồn không được phản ánh sang bản sao.

~~~java
var original = new java.util.ArrayList<>(java.util.List.of("A", "B"));
var snapshot = java.util.List.copyOf(original);
original.add("C");

System.out.println(original); // [A, B, C]
System.out.println(snapshot); // [A, B]
~~~

Khác với `Collections.unmodifiableList(original)`: đây là **view không thể chỉnh sửa trực tiếp**, nhưng nếu `original` thay đổi thì nội dung quan sát qua view cũng thay đổi. `List.copyOf(original)` phù hợp để chốt danh sách cấu hình, kết quả xử lý hoặc dữ liệu đầu vào tại một thời điểm.

Các ràng buộc quan trọng:

- `copyOf` không nhận nguồn `null`; phần tử `null` trong List/Set, hoặc khóa/giá trị `null` trong Map, đều bị từ chối bằng `NullPointerException`.
- `List.copyOf` giữ thứ tự và cho phép phần tử trùng nhau. `Set.copyOf` loại trùng; nếu nguồn có phần tử trùng, không ném lỗi chỉ vì trùng. Không dựa vào thứ tự duyệt của Set/Map loại này.
- Nếu nguồn vốn đã là một collection không thể chỉnh sửa thích hợp, `copyOf` có thể dùng lại đối tượng; không giả định nó luôn tạo instance mới.
- Đây là **bất biến ở cấp cấu trúc collection**, không phải deep immutability. Nếu phần tử là object có trạng thái thay đổi được, việc sửa object đó vẫn có thể làm dữ liệu được quan sát thay đổi.
- `List.of`, `Set.of` và `Map.of` là các factory đã có từ Java 9; bổ sung riêng của Java 10 là nhóm `copyOf` và collector mới.

### 3.2. Collector `toUnmodifiable...`

Java 10 thêm các terminal collector:

- `Collectors.toUnmodifiableList()`: giữ thứ tự encounter của stream có thứ tự, không cho chỉnh sửa kết quả.
- `Collectors.toUnmodifiableSet()`: loại phần tử trùng; thứ tự duyệt không được bảo đảm.
- `Collectors.toUnmodifiableMap(keyMapper, valueMapper)`: ánh xạ khóa/giá trị; nếu nhiều phần tử tạo cùng khóa thì ném `IllegalStateException`.
- `Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)`: cung cấp quy tắc gộp khi trùng khóa.

~~~java
var words = java.util.List.of("java", "jvm", "api");
var upper = words.stream()
        .map(String::toUpperCase)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
System.out.println(upper); // [JAVA, JVM, API]
~~~

Những collector này từ chối giá trị `null`. Với `Map`, hãy thiết kế khóa duy nhất hoặc hàm merge rõ ràng; không phụ thuộc thứ tự hiển thị ngẫu nhiên của một Map không có cam kết thứ tự. `Collectors.toList()` không có hợp đồng bảo đảm kết quả có thể hay không thể chỉnh sửa; chọn collector phù hợp theo hợp đồng mong muốn.

## 4. API Java 10 khác vẫn hữu ích

### 4.1. `Optional.orElseThrow()` không tham số

`Optional.orElseThrow()` trả về giá trị nếu có; nếu rỗng, ném `NoSuchElementException`. Nó truyền đạt ý định rõ hơn `Optional.get()` khi đã xác định đây là trường hợp bắt buộc có giá trị.

~~~java
String value = java.util.Optional.of("ready").orElseThrow();
System.out.println(value); // ready
~~~

Với tình huống cần thông báo lỗi nghiệp vụ, dùng biến thể nhận supplier ngoại lệ, ví dụ `optional.orElseThrow(() -> new IllegalArgumentException("missing id"))`. Tránh gọi `orElseThrow()` tùy tiện cho kết quả có thể vắng mặt trong luồng xử lý bình thường; khi đó có thể dùng `map`, `ifPresent` hoặc `orElse` phù hợp hơn.

### 4.2. `Reader.transferTo(Writer)`

`Reader.transferTo` chuyển toàn bộ **ký tự** còn lại từ `Reader` sang `Writer`, trả về số ký tự đã chuyển (`long`). Phương thức không tự đóng hai stream; hãy dùng `try-with-resources` khi sở hữu tài nguyên. Khác với `InputStream.transferTo(OutputStream)` dành cho byte.

~~~java
try (var reader = new java.io.StringReader("Hello");
     var writer = new java.io.StringWriter()) {
    long count = reader.transferTo(writer);
    System.out.println(count + ":" + writer); // 5:Hello
}
~~~

Dùng khi cần copy text giữa hai stream mà không tự quản vòng lặp buffer. Với input rất lớn, cần cân nhắc I/O blocking và xử lý lỗi; thao tác có thể đã copy một phần trước khi ném `IOException`.

### 4.3. `ByteArrayOutputStream.toString(Charset)`

Java 10 có overload nhận `Charset`, giúp chỉ định cách **giải mã byte thành text** thay vì phụ thuộc charset mặc định của môi trường.

~~~java
var bytes = new java.io.ByteArrayOutputStream();
bytes.write("Xin chao".getBytes(java.nio.charset.StandardCharsets.UTF_8));
String decoded = bytes.toString(java.nio.charset.StandardCharsets.UTF_8);
System.out.println(decoded); // Xin chao
~~~

Dùng `StandardCharsets.UTF_8` khi dữ liệu được mã hóa bằng UTF-8. Không dùng phương thức giải mã text để xử lý dữ liệu nhị phân thuần túy; nội dung không hợp lệ với charset có thể được thay thế theo quy tắc decoder.

### 4.4. Locale và Unicode language-tag extensions (JEP 314)

Java 10 mở rộng cách các API quốc tế hóa xử lý Unicode extension trong BCP 47:

| Key | Ý nghĩa | API điển hình |
| --- | --- | --- |
| `cu` | Loại tiền tệ | `Currency.getInstance(locale)` |
| `fw` | Ngày đầu tuần | `WeekFields.of(locale)` |
| `rg` | Ghi đè vùng áp dụng dữ liệu locale | `NumberFormat`, `DateFormat` và một số API liên quan |
| `tz` | Tùy chọn múi giờ | Một số API định dạng ngày giờ dựa trên locale |

~~~java
var locale = java.util.Locale.forLanguageTag("en-US-u-cu-jpy");
System.out.println(java.util.Currency.getInstance(locale).getCurrencyCode()); // JPY
~~~

Cần phân biệt `Locale` với `ZoneId` của một sự kiện cụ thể. Trong nghiệp vụ có múi giờ rõ ràng (lưu hẹn giờ, timestamp), sử dụng `ZoneId`/`ZonedDateTime` tường minh; không suy luận timezone nghiệp vụ chỉ từ ngôn ngữ giao diện. Dữ liệu locale và provider có thể khác giữa JDK, nên kiểm thử định dạng theo locale thực tế.

## 5. Ví dụ hoàn chỉnh: ngôn ngữ và API kết hợp

Lưu nguyên đoạn sau trong tệp `Java10Everyday.java`. Chương trình dùng các tính năng được đưa vào Java 10 và chạy với Java 17+.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Currency;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.stream.Collectors;

public class Java10Everyday {
    public static void main(String[] args) throws Exception {
        var source = new ArrayList<>(List.of("Java", "API"));
        var snapshot = List.copyOf(source);
        source.add("GC");
        System.out.println("snapshot=" + snapshot);

        var transformed = source.stream()
                .map(String::toLowerCase)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("transformed=" + transformed);

        System.out.println("optional=" + Optional.of("ready").orElseThrow());

        try (var reader = new StringReader("abc")) {
            var writer = new StringWriter();
            long copied = reader.transferTo(writer);
            System.out.println("reader=" + copied + ":" + writer);
        }

        var output = new ByteArrayOutputStream();
        output.write("UTF-8".getBytes(StandardCharsets.UTF_8));
        System.out.println("bytes=" + output.toString(StandardCharsets.UTF_8));

        var locale = Locale.forLanguageTag("en-US-u-cu-jpy");
        System.out.println("currency=" + Currency.getInstance(locale).getCurrencyCode());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac --release 17 Java10Everyday.java
java Java10Everyday
~~~

Output chính xác:

~~~text
snapshot=[Java, API]
transformed=[java, api, gc]
optional=ready
reader=3:abc
bytes=UTF-8
currency=JPY
~~~

Giải thích: `snapshot` giữ hai phần tử lúc chụp; `transformed` xử lý nguồn đã thêm `GC` nhưng không cho sửa danh sách kết quả; `Optional` trả giá trị có sẵn; `Reader.transferTo` chuyển ba ký tự; decode UTF-8 khôi phục chuỗi; locale extension `cu-jpy` chọn đồng JPY. Ví dụ không phụ thuộc vào thứ tự duyệt của Set/Map.

## 6. HotSpot/JVM: điều Java 10 thay đổi và cách hiểu ngày nay

### 6.1. G1 Parallel Full GC (JEP 307)

G1 phân vùng heap thành nhiều region và cố gắng đáp ứng mục tiêu thời gian tạm dừng, nhưng vẫn có trường hợp phải thực hiện **Full GC**. Từ Java 10, pha Full GC của G1 sử dụng nhiều worker song song thay vì thiết kế đơn luồng trước đó. Ý nghĩa là giảm thời gian xử lý của một đợt Full GC trong các điều kiện phù hợp.

Không kết luận rằng Full GC đã trở thành concurrent hoặc không còn pause: Full GC vẫn có thể là **stop-the-world** và gây độ trễ lớn. `-XX:MaxGCPauseMillis` là mục tiêu điều chỉnh, không phải cam kết tuyệt đối. Trên HotSpot hiện đại, G1 thường là collector mặc định, nhưng hãy kiểm tra cấu hình thực tế của runtime.

Quan sát thay vì suy đoán:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=info -version
~~~

Khi vận hành ứng dụng thực, thu thập GC log theo thời gian, pause percentile, heap usage, allocation rate và tác động đến latency/tải. Nếu Full GC xảy ra nhiều, kiểm tra memory pressure, leak, kích thước heap, giới hạn container và workload trước khi thay đổi flag.

### 6.2. Garbage-Collector Interface (JEP 304)

JDK 10 tổ chức lại ranh giới nội bộ giữa HotSpot VM và các GC implementation. Việc này giúp HotSpot bảo trì và phát triển nhiều collector rõ ràng hơn. Đây **không phải API Java công khai** để ứng dụng tự cắm một thuật toán GC tùy ý; ứng dụng vẫn dùng các cơ chế tiêu chuẩn để phân bổ object, theo dõi memory và lựa chọn collector được runtime hỗ trợ.

### 6.3. Thread-Local Handshakes (JEP 312)

Một số tác vụ của JVM cần phối hợp với thread Java. Thread-local handshakes cho phép thực hiện **một số** thao tác với từng thread thay vì luôn đòi hỏi toàn bộ thread tới một global safepoint. Đây là khả năng nội bộ của VM góp phần giảm chi phí điều phối ở những tình huống áp dụng được.

Không đồng nhất nó với lock, `synchronized`, `wait/notify` hay virtual thread trong code ứng dụng; cũng không suy ra tất cả global safepoint bị loại bỏ. Khi phân tích độ trễ, có thể đối chiếu GC log và safepoint log trên runtime đang dùng.

### 6.4. Application Class-Data Sharing – AppCDS (JEP 310)

CDS lưu một phần metadata của class ở định dạng đã chuẩn bị để JVM có thể nạp nhanh hơn, và cho phép chia sẻ trang bộ nhớ phù hợp giữa các process. Java 10 mở rộng ý tưởng này tới **class của ứng dụng** (AppCDS), ngoài các class nền tảng. Cơ chế này vẫn tồn tại trong các JDK hiện đại, với phương thức tạo và dùng archive được tiếp tục cải tiến qua các phiên bản.

Tình huống hữu ích: ứng dụng khởi động nhiều lần, nhiều process dùng cùng cấu hình classpath, dịch vụ ngắn hạn cần giảm startup time. CDS không lưu dữ liệu nghiệp vụ, không thay thế cache ứng dụng và không bảo đảm mọi ứng dụng đều nhanh hơn.

Để quan sát CDS trên HotSpot hỗ trợ unified logging:

~~~bash
java -Xlog:cds=info -version
~~~

Trước khi dùng archive ứng dụng trong production, đọc tài liệu CDS của đúng JDK: tính hợp lệ của archive phụ thuộc runtime, classpath, class loader và một số tùy chọn JVM. Benchmark cold start, startup memory và tổng chi phí tạo archive với workload thật.

### 6.5. Nhận biết container và giới hạn tài nguyên

Java 10 cải thiện HotSpot trên **Linux container** để nhận biết giới hạn CPU và memory do container cấp, thay vì luôn đọc toàn bộ tài nguyên host. Cơ chế này là nền tảng quan trọng cho dịch vụ container hiện nay; hỗ trợ cgroup và chi tiết báo cáo phụ thuộc phiên bản/bản phân phối JDK.

Các tùy chọn còn hữu ích:

| Tùy chọn | Vai trò |
| --- | --- |
| `-XX:+UseContainerSupport` | Bật nhận biết tài nguyên container (thường được bật sẵn ở HotSpot phù hợp) |
| `-XX:MaxRAMPercentage=p` | Cân đối giới hạn tối đa **Java heap** theo tỷ lệ memory JVM nhìn thấy |
| `-XX:InitialRAMPercentage=p` | Điều chỉnh mức heap ban đầu theo tỷ lệ memory |
| `-XX:ActiveProcessorCount=n` | Ghi đè số CPU mà JVM xem là đang hoạt động để tính thread pool và một số heuristic |

Ví dụ kiểm tra cú pháp flag không cần ứng dụng riêng:

~~~bash
java -XX:MaxRAMPercentage=60.0 -XX:ActiveProcessorCount=2 -version
~~~

Khi chạy trên Linux/container, có thể dùng `java -XshowSettings:system -version` để xem môi trường hệ thống mà JVM nhận diện (mức chi tiết phụ thuộc JDK). **Heap không phải toàn bộ bộ nhớ process**: metaspace, thread stacks, direct buffers, JIT code và native allocations còn dùng memory. Vì vậy không tùy tiện đặt MaxRAMPercentage gần 100%; phải để phần dự phòng và đo RSS/working set thực tế. `ActiveProcessorCount` cũng nên chỉ ghi đè khi có lý do vận hành rõ ràng.

### 6.6. Bộ nhớ chuyên biệt: `-XX:AllocateHeapAt` (JEP 316)

HotSpot còn hỗ trợ tùy chọn cấp phát object heap trên thiết bị bộ nhớ thay thế được hệ điều hành biểu diễn qua filesystem có memory mapping phù hợp. Đây là chức năng chuyên dụng cho hạ tầng tương thích; các vùng như metaspace và thread stacks vẫn có thể ở DRAM. Chỉ áp dụng sau khi xác minh hỗ trợ phần cứng, hệ điều hành, JDK và đặc tính hiệu năng; ứng dụng Java thông thường không cần cấu hình này.

### 6.7. Root CA certificates trong JDK (JEP 319)

Việc cung cấp tập root CA đáng tin cậy trong OpenJDK tạo nền tảng để nhiều kết nối TLS có thể xác minh chứng chỉ theo cấu hình truststore mặc định. Tập CA cụ thể phụ thuộc bản phân phối và các lần cập nhật bảo mật, nên **không** coi mọi runtime có danh sách CA hoàn toàn giống nhau.

Trong ứng dụng thực tế, để kết nối TLS tới dịch vụ dùng CA nội bộ, quản lý truststore của ứng dụng theo quy trình bảo mật và cấp đúng CA tin cậy. Không tắt bước xác minh chứng chỉ/hostname để che lỗi cấu hình truststore. Có thể dùng `keytool -list -cacerts` để kiểm tra truststore mặc định trên JDK hỗ trợ lệnh này.

### 6.8. Đánh số phiên bản theo chu kỳ (JEP 322)

Từ Java 10, version scheme được mô tả theo `FEATURE.INTERIM.UPDATE.PATCH` và phù hợp với mô hình phát hành định kỳ. Đối với việc vận hành, cần phân biệt **feature version** với **bản cập nhật bảo mật** và chính sách hỗ trợ của nhà cung cấp. Không nên suy ra hai runtime tương thích tuyệt đối chỉ vì có cùng feature version nhưng khác patch/update.

~~~java
int feature = Runtime.version().feature();
System.out.println("Running Java feature " + feature);
~~~

Đoạn trên in ra feature number **của JDK đang chạy**, không cố định là 10. Khi build để tương thích với nền tảng đích, ưu tiên `javac --release N` thích hợp và chạy test trên chính runtime đích, thay vì kiểm tra version string thủ công rồi tin rằng mọi API đều hiện diện.

## 7. Chọn cách áp dụng trong dự án

| Nhu cầu | Nên chọn | Tránh hiểu nhầm |
| --- | --- | --- |
| Viết biến cục bộ kiểu rõ từ initializer | `var` | `var` không đổi kiểu tại runtime |
| Chốt danh sách có thể bị sửa từ bên ngoài | `List.copyOf(source)` | View `unmodifiableList` vẫn phản ánh thay đổi của source |
| Thu thập kết quả stream không cho sửa | `toUnmodifiableList/Set/Map` | Xử lý null, khóa trùng và thứ tự trước |
| Optional bắt buộc có giá trị | `orElseThrow()` | Optional rỗng có thể ném exception |
| Copy luồng ký tự | `Reader.transferTo(Writer)` | Tài nguyên không tự đóng |
| Byte sang String với encoding xác định | `toString(StandardCharsets.UTF_8)` | Không dùng charset mặc định một cách vô thức |
| Dịch vụ chạy trong container | Quan sát memory/CPU limits, rồi tinh chỉnh JVM khi cần | Heap chỉ là một phần tổng memory |
| Tối ưu startup | Đo CDS/AppCDS với workload thật | Archive không phải cache dữ liệu |
| Phân tích GC pause | Xem GC và safepoint logs | Parallel Full GC không loại bỏ STW |

## 8. Lỗi thường gặp và bài tập tự kiểm tra

**Lỗi 1 – Nhầm bản sao không thể sửa với dữ liệu bất biến sâu.** Một `List.copyOf` chứa đối tượng mutable vẫn quan sát được thay đổi nội bộ của các đối tượng đó. Dùng immutable data types hoặc defensive copy ở cấp phần tử nếu yêu cầu bất biến sâu.

**Lỗi 2 – Sử dụng `var` che mất ý nghĩa kiểu.** Khi biểu thức bên phải là factory phức tạp hoặc API tổng quát, khai báo kiểu tường minh giúp bảo vệ hợp đồng của biến và dễ review hơn.

**Lỗi 3 – Cho rằng collection Java 10 chấp nhận null.** `copyOf` và `toUnmodifiable...` từ chối null; hãy xác thực hoặc làm sạch dữ liệu đầu vào trước.

**Lỗi 4 – Hiểu sai GC và bộ nhớ container.** Parallel Full GC vẫn có pause; `MaxRAMPercentage` chỉ giới hạn cách tính Java heap, chưa kiểm soát toàn bộ native memory.

**Lỗi 5 – Phụ thuộc môi trường.** Thứ tự Set/Map, charset mặc định, locale provider, archive CDS và container metrics có thể phụ thuộc cấu hình; kiểm thử các giả định này rõ ràng.

Tự kiểm tra:

1. Một `ArrayList<String>` có hai phần tử được truyền vào `List.copyOf`, sau đó source thêm phần tử thứ ba. Snapshot có thêm phần tử không? **Không**; phần tử mới chỉ xuất hiện ở source.
2. `var x = 10; x = "ten";` có chạy được không? **Không**, `x` được suy luận là `int` lúc biên dịch.
3. Stream có hai bản ghi tạo cùng khóa khi dùng `Collectors.toUnmodifiableMap(key, value)` sẽ làm gì? **Ném `IllegalStateException`**; cần ràng buộc khóa duy nhất hoặc dùng overload nhận merge function.
4. Đặt `-XX:MaxRAMPercentage=80` trong container giới hạn 512 MiB có đảm bảo RSS không vượt 512 MiB không? **Không**; heap chỉ là một phần bộ nhớ của JVM process.
5. AppCDS có giữ sẵn trạng thái phiên đăng nhập của ứng dụng để lần khởi động sau dùng lại không? **Không**; CDS chia sẻ metadata class theo cơ chế VM.

## 9. Tài liệu chính thức để tra cứu

- [JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286)
- [JDK 10 consolidated release notes – Oracle](https://www.oracle.com/java/technologies/javase/10all-relnotes.html)
- [Creating Unmodifiable Lists, Sets, and Maps – Oracle Java 25](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html)
- [JEP 314 – Additional Unicode Language-Tag Extensions](https://openjdk.org/jeps/314)
- [Class Data Sharing – Oracle Java 25](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html)
- [The java Command – Oracle Java 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [JEP 322 – Time-Based Release Versioning](https://openjdk.org/jeps/322)

Khi thực hành trên JDK mới, đối chiếu Java SE API (cú pháp, kiểu và ngoại lệ) với tài liệu đúng feature version; với GC, CDS, container và JVM flags, đối chiếu thêm HotSpot/nhà phân phối đang dùng.
