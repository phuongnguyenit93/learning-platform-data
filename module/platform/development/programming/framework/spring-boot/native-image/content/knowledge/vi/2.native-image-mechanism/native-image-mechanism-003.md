# Reachability và việc loại bỏ mã không cần thiết

Trong ứng dụng Spring Boot chạy trên JVM, một dependency có thể chứa hàng trăm lớp dù ứng dụng chỉ sử dụng vài API của nó. JVM nạp lớp và thực thi mã khi cần, đồng thời có thể tối ưu mã lúc chạy. Khi biên dịch thành **GraalVM Native Image**, công cụ phải xác định trước những phần chương trình *có khả năng được thực thi* để tạo executable native. Công đoạn đó được gọi là **reachability analysis** (phân tích khả năng truy cập).

Reachability là nền tảng của cơ chế loại bỏ mã không cần thiết (dead code elimination) và mô hình **closed-world assumption** của Native Image. Hiểu đúng cơ chế này giúp giải thích vì sao một bản native có thể khởi động nhanh, vì sao một lớp có trong dependency vẫn “biến mất” khi chạy, và vì sao một số tính năng dùng reflection hoặc tên lớp động cần khai báo bổ sung.

## 1. Reachability là gì?

Một thành phần được coi là **reachable** khi quá trình phân tích xác định rằng có ít nhất một đường thực thi hợp lệ dẫn tới nó, bắt đầu từ các điểm vào được biết ở thời điểm build. Thành phần có thể là phương thức, constructor, trường dữ liệu, kiểu đối tượng hoặc đoạn mã liên quan.

Các điểm bắt đầu và nguồn thông tin điển hình gồm:

- Phương thức `main` cùng phần khởi động ứng dụng và các điểm vào do hệ thống Native Image thiết lập.
- Những lời gọi trực tiếp được phát hiện từ bytecode, cùng các đích gọi *có thể xảy ra* của interface, phương thức ảo, lambda và callback.
- Những thành phần mà framework hoặc thư viện đăng ký thông qua metadata, chẳng hạn constructor dùng reflection, proxy động hoặc JNI.
- Các quyết định mà trình phân tích có thể suy ra tại build time, ví dụ nhánh với giá trị đã được xác định.

Hình dung chương trình là một đồ thị: mỗi nút biểu diễn một phần mã, các cạnh biểu diễn khả năng một phần mã dẫn đến phần khác. Trình phân tích bắt đầu từ tập nút gốc, liên tục mở rộng các cạnh có thể đi tới và tạo thành tập reachable. Phần mã nằm ngoài tập này có thể được loại khỏi native executable.

~~~mermaid
flowchart TD
    A["Điểm vào: main, khởi động ứng dụng"] --> B["Phân tích lời gọi và luồng kiểu"]
    B --> C["Mở rộng tập mã có thể được thực thi"]
    M["Metadata cho reflection, proxy, JNI…"] --> C
    C --> D{"Đã xét hết đường đi khả dĩ?"}
    D -->|Chưa| B
    D -->|Rồi| E["Sinh mã máy cho phần reachable"]
    B -. "Không tìm được đường đi" .-> F["Mã không được đưa vào image"]
    R["Cấu hình tài nguyên"] --> G["Đóng gói resource cần dùng"]
~~~

**Reachable không có nghĩa là chắc chắn sẽ chạy.** Ví dụ, hai nhánh của một lệnh `if` phụ thuộc vào cấu hình lúc chạy đều có thể được giữ lại. Native Image phải bảo toàn những hành vi có khả năng xuất hiện, vì vậy không thể kết luận rằng mọi đoạn mã “chưa từng chạy trong bài test” sẽ bị xóa.

Ngược lại, **không reachable không có nghĩa là source code hoặc file JAR đã bị xóa**. Kết quả phân tích quyết định phần nào được đưa vào executable được sinh ra; mã nguồn và các dependency đầu vào vẫn tồn tại trong dự án.

## 2. Từ lời gọi tĩnh đến tập mã cần giữ

Xét một ứng dụng trả về hóa đơn bằng CSV:

~~~java
interface ReceiptFormatter {
    String format(String receiptId);
}

final class CsvFormatter implements ReceiptFormatter {
    @Override
    public String format(String receiptId) {
        return "receipt_id," + receiptId;
    }
}

final class XmlFormatter implements ReceiptFormatter {
    @Override
    public String format(String receiptId) {
        return "<receipt id=\"" + receiptId + "\"/>";
    }
}

@RestController
class ReceiptController {
    private final ReceiptFormatter formatter = new CsvFormatter();

    @GetMapping("/receipts/{id}")
    String getReceipt(@PathVariable String id) {
        return formatter.format(id);
    }
}
~~~

Trong đoạn mã này, đường đi bắt đầu từ xử lý HTTP có thể dẫn tới `ReceiptController.getReceipt`, `CsvFormatter.format` và các phần mã hỗ trợ chúng. Nếu ứng dụng không có bất kỳ lời gọi, cấu hình hay cơ chế nào khác dẫn tới `XmlFormatter`, phần triển khai XML có thể không được đưa vào image.

Một vài điểm cần phân biệt:

| Tình huống | Hệ quả với reachability |
|---|---|
| Gọi `new CsvFormatter()` trực tiếp | Constructor và những mã được gọi từ đó có đường đi tĩnh rõ ràng. |
| Gọi qua `ReceiptFormatter` | Phân tích phải xét những kiểu triển khai có thể xuất hiện tại vị trí gọi; không phải chỉ xét tên interface. |
| Nhánh phụ thuộc request, môi trường hoặc dữ liệu lúc chạy | Các nhánh khả thi thường phải được giữ. |
| Nhánh hoặc giá trị được chứng minh là bất biến tại build time | Trình tối ưu có thể rút gọn nhánh và mã liên quan. |
| Lớp chỉ xuất hiện trong JAR nhưng không có đường đi sử dụng | Không nhất thiết được đưa vào executable. |
| Lớp chỉ được nhắc tới bằng tên chuỗi từ cấu hình động | Phân tích tĩnh có thể không suy ra lớp đích; cần cơ chế hỗ trợ động phù hợp. |

Reachability analysis là phép phân tích **bảo thủ**: khi không chứng minh được một đường đi là bất khả thi, công cụ có thể phải giữ nhiều mã hơn để đảm bảo tính đúng đắn. Kích thước executable vì vậy không tỷ lệ tuyến tính với số lớp nguồn hay số dependency.

## 3. Closed-world assumption và giới hạn của phân tích tĩnh

**Closed-world assumption** nghĩa là Native Image xây dựng một “thế giới chương trình” đã được mô tả đủ tại thời điểm build: những loại đối tượng, đường gọi và khả năng truy cập động cần thiết phải được trình phân tích nhận diện. Ứng dụng native không có cùng mô hình tải và biên dịch bytecode Java tùy ý trong lúc chạy như JVM thông thường.

Vấn đề xuất hiện khi hành vi phụ thuộc vào thông tin chỉ biết sau khi executable được tạo. Ví dụ:

~~~java
@Service
class FormatterFactory {
    ReceiptFormatter create(String configuredClassName)
            throws ReflectiveOperationException {
        Class<?> type = Class.forName(configuredClassName);
        return (ReceiptFormatter) type.getDeclaredConstructor().newInstance();
    }
}
~~~

Tên lớp ở đây đến từ cấu hình runtime, chẳng hạn `com.example.receipt.XmlFormatter`. Trình biên dịch không thể chỉ nhìn vào `Class.forName(configuredClassName)` rồi biết chắc tất cả tên lớp có thể được truyền vào. Nếu lớp hoặc constructor đích chưa được làm reachable và chưa được cấu hình đúng, phiên bản native có thể thất bại dù cùng đường đi hoạt động trên JVM.

Điều này **không có nghĩa mọi lệnh `Class.forName` đều lỗi**. GraalVM có thể suy luận một số mẫu reflection với đối số hằng hoặc đủ rõ ràng. Metadata cần được bổ sung khi hành vi động thực tế không được phân tích tự động, và phải được xác minh bằng bài test native.

## 4. Vai trò của Spring AOT trong Spring Boot

Spring Boot dùng **Spring AOT (Ahead-of-Time processing)** để chuyển nhiều thao tác khởi động vốn mang tính động thành thông tin và mã được tạo ra khi build. Quá trình này giúp GraalVM thấy rõ hơn cấu trúc ứng dụng Spring trước khi phân tích reachability.

Ví dụ, Spring AOT có thể:

1. Phân tích cấu hình ứng dụng và các bean đã xác định được trong giai đoạn AOT.
2. Tạo mã khởi tạo bean hoặc đăng ký bean thay cho một phần thao tác dò tìm và suy luận cấu hình lúc chạy.
3. Đóng góp runtime hints cần thiết cho reflection, resource, proxy hoặc những cơ chế động mà Spring quản lý.
4. Đưa kết quả AOT vào đầu vào của Native Image để trình phân tích tiếp tục xác định mã cần giữ.

Luồng khái quát:

~~~text
Source Spring Boot + dependencies
           |
           v
   Xử lý Spring AOT
   - Phân tích bean/configuration
   - Sinh mã hỗ trợ khởi động
   - Thu thập runtime hints
           |
           v
   GraalVM Native Image
   - Phân tích reachability
   - Sinh mã máy và dữ liệu image
           |
           v
      Native executable
~~~

Spring AOT làm giảm nhu cầu khám phá ứng dụng tại runtime nhưng **không tự động hiểu mọi cơ chế tùy biến**. Những thư viện tự tải tên lớp từ database, plugin từ thư mục ngoài, hoặc tự tạo reflection bằng chuỗi có thể vẫn cần metadata do lập trình viên cung cấp.

Cần nhớ rằng lựa chọn cấu hình chỉ được quyết định ở build time khi công cụ có đủ dữ liệu để quyết định. Đừng mặc định mọi `@Conditional...`, profile hay giá trị cấu hình đều được cố định ở thời điểm build; phải kiểm tra hành vi của tình huống cụ thể.

## 5. Reflection, proxy, resource: những thứ dễ bị bỏ sót

**Reflection.** Truy cập constructor, phương thức hoặc field bằng `Class`, `Method`, `Field` có thể cần reflection metadata để Native Image chuẩn bị thành phần tương ứng. Việc khai báo quá rộng cũng có thể giữ thêm metadata và mã không cần thiết.

**Dynamic proxy.** Thư viện có thể tạo proxy theo một tập interface trong runtime. Các tập interface cần thiết phải có khả năng được nhận diện hoặc đăng ký để có proxy tương ứng trong image.

**Resource.** File JSON, template, chứng chỉ, schema, ảnh hoặc file cấu hình trong `src/main/resources` không phải là nút phương thức trong đồ thị gọi Java. Việc đóng gói chúng được quản lý qua cơ chế resource inclusion/configuration riêng. Một file có trong JAR đầu vào chưa đảm bảo file ấy có sẵn để đọc từ classpath của image.

**Serialization và data binding.** Jackson hoặc các thư viện mapping có thể tìm constructor, getter/setter, record component hay field bằng reflection. Spring AOT và thư viện có hỗ trợ native thường tự đóng góp nhiều hint, nhưng kiểu dữ liệu được phát hiện hoàn toàn động có thể cần khai báo thêm.

**JNI và các thư viện native.** Tương tác JNI đòi hỏi cấu hình thích hợp cho thành phần Java được truy cập từ native code; đồng thời phải kiểm tra các binary native phụ thuộc vào nền tảng triển khai.

Điểm chung là: **metadata mở rộng những khả năng mà phép phân tích cần biết**. Khai báo hint không đồng nghĩa với “giữ toàn bộ dependency”, và một loại hint không thay thế được loại khác. Ví dụ, reflection hint cho một lớp không tự làm một template bất kỳ xuất hiện trong classpath.

## 6. Bổ sung runtime hints có kiểm soát

Giả sử ứng dụng cho phép chọn `CsvFormatter` hoặc `XmlFormatter` theo cấu hình lúc chạy và dùng thêm template `templates/receipts/summary.txt`. Khi Spring AOT và thư viện chưa tự cung cấp thông tin đó, có thể đăng ký theo API `RuntimeHints` của Spring:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

final class ReceiptHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            CsvFormatter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
        hints.reflection().registerType(
            XmlFormatter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
        hints.resources().registerPattern("templates/receipts/*.txt");
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ReceiptHints.class)
class ReceiptNativeConfiguration {
}
~~~

Đây là ví dụ cho các lớp cùng package với cấu hình. Hai formatter phải có constructor phù hợp với cách tạo đối tượng bằng reflection. Mẫu tài nguyên chỉ có tác dụng với các file thực sự tồn tại trong nguồn tài nguyên khi build, ví dụ `src/main/resources/templates/receipts/summary.txt`.

Một đoạn mã đọc tài nguyên có thể như sau:

~~~java
Resource template =
    new ClassPathResource("templates/receipts/summary.txt");

try (InputStream input = template.getInputStream()) {
    // Đọc template và xử lý nội dung.
}
~~~

Spring hỗ trợ các cách đăng ký khác tùy trường hợp, ví dụ `@RegisterReflectionForBinding` cho kiểu dữ liệu cần binding. Ngoài ra, GraalVM có cơ chế reachability metadata cho thư viện và cấu hình native riêng. **Chọn mức đăng ký hẹp nhất đáp ứng đường đi thật sự dùng**, vì đăng ký reflection cho mọi thành viên hoặc mọi lớp trong một package dễ làm image lớn và che giấu vấn đề thiết kế.

Nếu có thể, hãy thay việc lấy tên lớp tùy ý bằng một tập chiến lược được khai báo rõ qua Spring bean hoặc enum cấu hình. Cách đó giúp logic dễ kiểm soát, dễ test, và để Spring AOT thấy các kiểu triển khai.

## 7. Những gì thực sự bị loại bỏ

Khi phân tích hoàn tất, Native Image có thể bỏ các đoạn mã không reachable khỏi phần mã máy cuối cùng, nhưng có vài giới hạn quan trọng:

- **Mã thực thi và metadata là hai khái niệm khác nhau.** Một kiểu có thể được giữ để phục vụ thao tác reflective cụ thể; phạm vi metadata được khai báo ảnh hưởng những gì runtime có thể truy cập.
- **Tài nguyên có quy tắc đóng gói riêng.** Loại bỏ một method không tự chứng minh một file resource có thể bị bỏ, và việc giữ một class cũng không mặc nhiên giữ mọi file đi kèm.
- **Build-time initialization khác reachability.** Một lớp có thể được khởi tạo trong lúc build và một số đối tượng được lưu vào image heap. Quyết định thời điểm khởi tạo lớp và quyết định mã có reachable hay không là hai vấn đề liên quan nhưng khác nhau.
- **Lời gọi gián tiếp làm tập reachable lớn hơn.** Gọi interface, dispatch ảo, callback và metadata rộng khiến trình phân tích phải cân nhắc nhiều đích có thể xảy ra.
- **Runtime cần mã nền tảng.** Image vẫn chứa thành phần của hệ thống chạy native và các thư viện cần thiết. Không nên suy kích thước file chỉ từ số lớp ứng dụng.

Một dependency nặng về kích thước JAR chưa chắc tăng kích thước image tương ứng nếu phần lớn mã không reachable. Ngược lại, một cơ chế đăng ký hàng loạt class qua reflection có thể khiến image chứa nhiều thành phần hơn dự kiến.

## 8. Cách kiểm chứng trên dự án Spring Boot

Các bước dưới đây áp dụng khi dự án đã cấu hình Spring Boot AOT, GraalVM và plugin build native tương ứng. Lệnh cụ thể có thể thay đổi theo cấu hình build của dự án.

**Bước 1 — Xác định đường đi động.** Tìm các chỗ dùng `Class.forName`, `getDeclaredConstructor`, `getMethod`, `ServiceLoader`, proxy động, deserialize kiểu không cố định hoặc đọc resource bằng tên do cấu hình cung cấp. Đặc biệt chú ý các nhánh chỉ xuất hiện với profile hoặc dữ liệu production.

**Bước 2 — Xây dựng bản native.** Với cấu hình build phổ biến:

~~~bash
# Maven (khi native profile và plugin đã được cấu hình)
./mvnw -Pnative native:compile

# Gradle (khi plugin GraalVM Native Build Tools đã được cấu hình)
./gradlew nativeCompile
~~~

Với Windows, sử dụng script wrapper tương ứng như `mvnw.cmd` hoặc `gradlew.bat`. Build thành công chỉ chứng minh quá trình phân tích và sinh executable hoàn tất, **chưa chứng minh mọi tính năng runtime đều tương thích**.

**Bước 3 — Chạy đúng executable sinh ra.** Gọi các endpoint và luồng nghiệp vụ có reflection, serialization, proxy hoặc resource. Ví dụ, kiểm tra cả hai giá trị cấu hình chọn CSV/XML và các nhánh đọc template. Chạy trên JVM và trên native với cùng bộ tình huống để phát hiện chênh lệch.

**Bước 4 — Khoanh vùng lỗi từ dấu hiệu cụ thể.**

| Dấu hiệu khi chạy native | Giả thuyết cần kiểm tra |
|---|---|
| Không tìm thấy lớp khi cấu hình chọn implementation động | Lớp đích chưa được nhận diện/đăng ký; xem đường gọi và reflection metadata. |
| Không tạo được object, thiếu constructor hoặc truy cập thành viên thất bại | Hint không đủ chính xác cho constructor/method/field được gọi qua reflection. |
| Jackson deserialize sai hoặc thất bại chỉ với một DTO | Khả năng truy cập constructor, thuộc tính hoặc runtime hints cho data binding. |
| `getResourceAsStream` trả về `null` | Tài nguyên hoặc pattern inclusion chưa đúng. |
| Lỗi khi tạo proxy cho tập interface nhất định | Thông tin proxy tương ứng chưa được đưa vào native image. |

Các dấu hiệu trên gợi ý hướng điều tra, không phải kết luận duy nhất. Đọc exception và build log trước khi thêm metadata. Nếu cần, dùng chế độ chẩn đoán của GraalVM hoặc công cụ theo dõi hành vi động của thư viện để xác định chính xác thành phần thiếu; tránh sao chép toàn bộ metadata thu thập được mà chưa xem lại phạm vi.

**Bước 5 — Đo lợi ích bằng cùng workload.** Đánh giá thời gian khởi động lạnh, thời gian phản hồi request đầu tiên, RSS hoặc working set của tiến trình, throughput và latency dưới tải. So sánh cùng chức năng, cùng cấu hình môi trường và cùng cách đo. Tập mã nhỏ hơn thường có lợi cho footprint, nhưng không tự bảo đảm mọi ứng dụng native sẽ dùng ít bộ nhớ hơn hoặc có throughput cao hơn bản JVM trong mọi điều kiện.

## 9. Tình huống thực tế: cấu hình mở rộng làm mất tính đóng

Một dịch vụ xử lý báo cáo có endpoint `/reports/export`. Ban đầu nó chỉ hỗ trợ CSV và code gọi trực tiếp `CsvExporter`. Sau đó nhóm phát triển thêm tùy chọn `export.class` chứa tên lớp Java để cài plugin theo khách hàng. Trong môi trường JVM, một plugin có mặt trên classpath có thể được tải động khi request đến. Với bản Native Image được build trước, việc thêm file JAR hoặc cấu hình tên implementation mới ở runtime không mặc nhiên làm lớp mới xuất hiện trong executable.

Có ba hướng xử lý phổ biến:

1. **Danh sách implementation cố định tại build time:** đóng gói các exporter cần hỗ trợ, khai báo bean hoặc registry rõ ràng và chọn theo khóa cấu hình; thường dễ tương thích native nhất.
2. **Tập đích động hữu hạn:** duy trì cơ chế reflection nhưng cung cấp metadata cho đúng các loại có thể xuất hiện và kiểm thử tất cả cấu hình được hỗ trợ.
3. **Plugin không biết trước tại build time:** xem lại kiến trúc, chẳng hạn tách plugin thành tiến trình/dịch vụ ngoài; không dựa vào khả năng tải bytecode tùy ý của JVM trong một executable Native Image.

Bài học ở đây không phải “cấm reflection” mà là **phải mô tả được tập hành vi runtime khi build**. Spring AOT giải quyết tốt phần cấu trúc Spring nhận biết được; mã tùy biến của ứng dụng vẫn cần thiết kế và kiểm chứng tương ứng.

## 10. Tổng kết nguyên lý

Có thể dùng bốn câu hỏi để phân tích một tính năng trước khi chuyển ứng dụng Spring Boot sang native:

1. **Đường đi nào làm mã được gọi tới?** Nếu đường đi rõ qua bytecode hoặc mã AOT, GraalVM có cơ sở để phân tích.
2. **Có loại đích nào chỉ biết lúc chạy?** Nếu có, xác định nó thuộc reflection, proxy, JNI, serialization hay dạng khác.
3. **Metadata và resource đã bao phủ đúng hành vi đó chưa?** Kiểm tra những gì Spring AOT hoặc thư viện cung cấp trước khi tự thêm hint.
4. **Đã chạy đường đi đó trên native executable chưa?** Test JVM và một lần build thành công không thay thế được kiểm thử runtime native.

Reachability quyết định phần chương trình có khả năng cần thiết; dead code elimination tận dụng kết quả đó để giảm phần mã đưa vào executable. **Spring AOT là cầu nối** giúp những cấu trúc Spring Boot vốn động trở nên nhìn thấy được với GraalVM, còn runtime hints hoàn thiện thông tin cho các trường hợp không thể suy luận an toàn bằng phân tích tĩnh.
