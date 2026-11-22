# Những năng lực Java 15 còn được dùng trong Java hiện đại

> **Mục tiêu:** Nhận diện những năng lực xuất hiện, được hoàn thiện hoặc đạt mốc quan trọng ở JDK 15 (09/2020) mà lập trình viên vẫn nên hiểu và áp dụng trên JDK hiện đại. Trọng tâm là **cách dùng đã ổn định ngày nay**, không học lại cú pháp thử nghiệm hoặc API đã bị thay thế.

## 1. Đặt Java 15 vào đúng vị trí

Java 15 là một bản phát hành sáu tháng, không phải bản LTS để chọn triển khai dự án mới. Giá trị của nó là những thay đổi đã trở thành nền tảng cho Java 17, Java 21, Java 25 và các phiên bản mới hơn. Cần phân biệt **đã có ở Java 15** với **đã là tính năng chính thức trong Java 15**.

| Năng lực vẫn hữu ích | Trạng thái ở Java 15 | Cách tiếp cận hiện đại |
| --- | --- | --- |
| Text blocks (`"""`) | Chính thức từ JDK 15 (JEP 378) | Dùng trực tiếp để biểu diễn chuỗi nhiều dòng |
| Records | Bản preview thứ hai ở JDK 15 | Chính thức từ JDK 16; dùng cho dữ liệu có cấu trúc |
| Pattern matching cho `instanceof` | Bản preview thứ hai ở JDK 15 | Chính thức từ JDK 16; kiểm tra kiểu và lấy biến cùng lúc |
| Sealed classes/interfaces | Preview lần đầu ở JDK 15 | Chính thức từ JDK 17; giới hạn tập kiểu con |
| ZGC và Shenandoah | Đạt mốc sử dụng production ở JDK 15 | Các lựa chọn GC độ trễ thấp, phải đo thực tế và kiểm tra JDK đang dùng |
| EdDSA (`Ed25519`, `Ed448`) | Hỗ trợ chuẩn hóa trong JDK 15 (JEP 339) | Ký/xác minh chữ ký số qua Java Cryptography Architecture |
| Hidden classes | API nền tảng trong JDK 15 (JEP 371) | Phục vụ framework sinh bytecode khi chạy |
| Truy cập bộ nhớ ngoài heap | API đang incubate ở JDK 15 | Học **Foreign Function & Memory API** chính thức từ JDK 22, gói `java.lang.foreign` |

**Định hướng học:** Bắt đầu với text blocks, records, `instanceof` pattern và sealed types vì trực tiếp tác động đến code ứng dụng. Tiếp theo học lựa chọn garbage collector và chữ ký số theo nhu cầu hệ thống. Hidden classes và FFM dành cho tình huống chuyên sâu. Mọi ví dụ Java 17+ bên dưới dùng **cú pháp đã chính thức**, không yêu cầu bật preview.

## 2. Text blocks: chuỗi nhiều dòng dễ đọc

Text block dùng dấu phân cách ba dấu nháy kép. Nó hữu ích với JSON, SQL, HTML, thông báo nhiều dòng và dữ liệu kiểm thử. Nội dung vẫn là một đối tượng `String` thông thường, vì vậy có thể kết hợp với `formatted`, `strip` hoặc các API xử lý chuỗi khác.

~~~java
String json = """
        {
          "name": "Java",
          "release": 15,
          "stable": true
        }
        """;
System.out.print(json);
~~~

Giá trị của `json` gồm các dòng được thể hiện trong ví dụ và có ký tự xuống dòng ở cuối. Trình biên dịch loại bỏ **khoảng thụt lề chung** theo quy tắc text block; việc đặt vị trí dấu `"""` đóng ảnh hưởng đến khoảng thụt lề còn lại. Nếu không muốn ký tự xuống dòng cuối, có thể gọi `stripTrailing()` (đồng thời xóa whitespace ở cuối) hoặc chủ động xử lý chuỗi theo yêu cầu dữ liệu.

Đặc biệt, **text block không tự biến SQL thành truy vấn an toàn**. Giá trị đến từ người dùng vẫn phải được truyền qua tham số của `PreparedStatement`. Text block chỉ giúp câu SQL tĩnh dễ đọc:

~~~java
String sql = """
        SELECT id, full_name
        FROM customers
        WHERE email = ?
        ORDER BY id
        """;
~~~

**Khi nên dùng:** nội dung nhiều dòng có bố cục rõ. **Khi không nên dùng:** chuỗi một dòng ngắn hoặc nội dung cần tạo động bằng logic phức tạp; khi đó hãy dùng công cụ sinh JSON/HTML/SQL thích hợp.

## 3. Records: mô hình dữ liệu ít mã lặp

`record` tự sinh constructor, các phương thức truy cập thành phần (`name()` thay vì bắt buộc phải là `getName()`), `equals`, `hashCode` và `toString`. Nó biểu diễn **giá trị dữ liệu** rõ ràng, thường phù hợp với DTO, kết quả xử lý và thông điệp bất biến ở mức cấu trúc.

~~~java
record Point(int x, int y) {}

Point point = new Point(3, 4);
System.out.println(point.x());  // 3
System.out.println(point);      // Point[x=3, y=4]
~~~

Records **không bảo đảm bất biến sâu**: nếu một thành phần chứa danh sách có thể thay đổi, dữ liệu bên trong danh sách vẫn có thể bị sửa ở nơi khác. Có thể bảo vệ dữ liệu khi khởi tạo bằng compact constructor:

~~~java
import java.util.List;

record Course(String name, List<String> topics) {
    Course {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        topics = List.copyOf(topics);
    }
}
~~~

Đoạn `Course` minh họa một khai báo record độc lập trong tệp có import tương ứng. `List.copyOf` tạo danh sách không cho phép sửa qua tham chiếu trả về; đây vẫn là **bất biến nông** nếu các phần tử tự chúng là đối tượng có thể thay đổi. `List.copyOf` cũng từ chối phần tử `null`.

**Phân biệt:** record là một kiểu class `final`, không kế thừa class khác và không thích hợp khi đối tượng có danh tính thay đổi, vòng đời phức tạp hoặc cần kế thừa từ lớp cha nghiệp vụ. Đừng chuyển mọi entity/database model sang record chỉ vì cú pháp ngắn.

## 4. Pattern matching cho `instanceof`: kiểm tra và lấy kiểu an toàn

Trước đây, kiểm tra kiểu thường đi kèm một lần ép kiểu lặp lại. Cú pháp ổn định hiện nay giúp tạo biến có đúng kiểu ngay khi điều kiện thành công:

~~~java
static int lengthIfText(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return text.length();
    }
    return 0;
}
~~~

Biến `text` chỉ dùng được tại những nhánh mà trình biên dịch chứng minh phép kiểm tra kiểu thành công (*flow scoping*). Khi `value` là `null`, điều kiện `instanceof` trả về `false`; không cần ép kiểu thủ công. Kết hợp điều kiện bằng `&&` như trên là an toàn vì vế phải chỉ chạy nếu đã khớp kiểu.

**Ứng dụng:** xử lý đầu vào có nhiều kiểu, tích hợp API cũ trả về `Object`, hoặc phân nhánh theo kiểu trong một hệ phân cấp. Không thay thế thiết kế đa hình tốt bằng chuỗi `instanceof` rất dài nếu mỗi kiểu có thể tự triển khai hành vi của nó.

## 5. Sealed types: kiểm soát tập kiểu được phép mở rộng

Một `sealed interface` hoặc `sealed class` liệt kê rõ các kiểu con trực tiếp được phép. Điều này hữu ích với mô hình có **tập trường hợp hữu hạn**: thành công/thất bại, trạng thái nghiệp vụ, biến thể lệnh, cây biểu thức. Java 17 đã chuẩn hóa tính năng này.

~~~java
sealed interface PaymentResult permits Paid, Declined {}

record Paid(String transactionId) implements PaymentResult {}
record Declined(String reason) implements PaymentResult {}
~~~

Các kiểu con trực tiếp phải xác định được cách tiếp tục mở rộng: `final`, `sealed` hoặc `non-sealed`. Record vốn là `final` nên `Paid` và `Declined` đáp ứng hợp đồng đó.

**Nên dùng:** domain đóng mà mọi biến thể thuộc quyền kiểm soát của cùng API. **Không nên dùng:** điểm mở rộng plugin mà ứng dụng bên ngoài phải tự thêm implementation mới, vì `sealed` sẽ cố ý ngăn việc đó. Đừng xem `sealed` là cơ chế bảo mật hoặc xác thực dữ liệu; nó chỉ ràng buộc cấu trúc kế thừa tại compile time và runtime.

## 6. Ví dụ chạy hoàn chỉnh: bốn năng lực ngôn ngữ phối hợp

Tạo file **Java15Today.java** với nội dung sau. Chương trình dùng text block, record, `instanceof` pattern và sealed interface theo cú pháp **Java 17+**:

~~~java
public class Java15Today {
    sealed interface Result permits Success, Failure {}
    record Success(String message) implements Result {}
    record Failure(String reason) implements Result {}

    static String describe(Object value) {
        if (value instanceof Success success) {
            return """
                    Trạng thái: thành công
                    Chi tiết: %s
                    """.formatted(success.message()).strip();
        }
        if (value instanceof Failure failure) {
            return "Lỗi: " + failure.reason();
        }
        return "Không xác định";
    }

    public static void main(String[] args) {
        Result result = new Success("đã lưu");
        System.out.println(describe(result));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 Java15Today.java
java Java15Today
~~~

Kết quả chuẩn:

~~~text
Trạng thái: thành công
Chi tiết: đã lưu
~~~

**Đọc luồng:** `Result` định nghĩa tập kết quả; `Success` và `Failure` là các record mang dữ liệu. `describe` dùng pattern matching để lấy đúng kiểu của dữ liệu đầu vào, rồi text block để định dạng đầu ra. `formatted` thay dấu `%s` bằng thông điệp, còn `strip` bỏ khoảng trắng đầu/cuối, bao gồm xuống dòng cuối của text block. Mỗi thành phần có nhiệm vụ riêng; không cần cờ preview.

**Thử mở rộng:** thay `new Success("đã lưu")` bằng `new Failure("không có quyền")`; chương trình sẽ in `Lỗi: không có quyền`. Sau đó thử thêm một kiểu con hợp lệ vào `permits` và quyết định cách xử lý trong `describe`.

## 7. Garbage collector độ trễ thấp: ZGC và Shenandoah

JDK 15 đánh dấu việc ZGC (JEP 377) và Shenandoah (JEP 379) sẵn sàng cho production. Năng lực cần nắm ngày nay là **lựa chọn GC theo đặc tính ứng dụng**, không ghi nhớ các cờ thử nghiệm của thời kỳ cũ.

- **ZGC:** thực hiện phần lớn công việc đồng thời với luồng ứng dụng để giảm thời gian dừng (*pause*). Trên JDK hiện đại, ZGC là collector theo thế hệ (*generational*); cờ kích hoạt vẫn là `-XX:+UseZGC`.
- **Shenandoah:** cũng tập trung giảm pause bằng cơ chế thu gom đồng thời; mức hỗ trợ phụ thuộc bản phân phối JDK, nền tảng và phiên bản triển khai.
- **GC mặc định:** vẫn là điểm xuất phát hợp lý nếu ứng dụng chưa có yêu cầu độ trễ đặc biệt; collector độ trễ thấp có thể đánh đổi throughput, CPU hoặc tài nguyên khác.

Ví dụ chạy ứng dụng thực với ZGC và bật log GC:

~~~bash
java -XX:+UseZGC -Xmx2g -Xlog:gc -jar app.jar
~~~

Nếu bản JDK có hỗ trợ Shenandoah, có thể đánh giá riêng:

~~~bash
java -XX:+UseShenandoahGC -Xmx2g -Xlog:gc -jar app.jar
~~~

`app.jar` là tên ví dụ của một file JAR thực tế. Chỉ sử dụng cờ được JDK đang chạy chấp nhận; không sao chép các cờ GC cũ giữa phiên bản một cách máy móc.

**Phương pháp chọn:** (1) chạy tải đại diện với cấu hình mặc định, (2) đo p95/p99 latency, throughput, thời gian GC, CPU và bộ nhớ, (3) thử ZGC/Shenandoah khi có vấn đề về pause, (4) so sánh trong cùng điều kiện tải và giới hạn heap. `-Xmx` phải đủ cho dữ liệu đang sống và không gian phân bổ trong lúc collector hoạt động. Không có collector nào luôn tối ưu cho mọi ứng dụng; giảm GC pause cũng không đồng nghĩa toàn bộ request latency tự động giảm.

## 8. EdDSA: ký và xác minh chữ ký số

Java 15 bổ sung hỗ trợ chuẩn cho **EdDSA**, thường dùng thuật toán **Ed25519** hoặc **Ed448**, qua Java Cryptography Architecture (JCA). Đây là chữ ký số bất đối xứng: khóa riêng ký dữ liệu, khóa công khai xác minh chữ ký. Nó giúp phát hiện nội dung bị thay đổi và xác nhận chữ ký đến từ bên sở hữu khóa riêng; **không dùng để mã hóa dữ liệu**.

Tạo file **EdDsaDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class EdDsaDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair keys = generator.generateKeyPair();
        byte[] message = "Java hiện đại".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(keys.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(keys.getPublic());
        verifier.update(message);
        System.out.println(verifier.verify(signature));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EdDsaDemo.java
java EdDsaDemo
~~~

Kết quả:

~~~text
true
~~~

Trong hệ thống thật, bên xác minh phải lấy khóa công khai qua kênh đáng tin cậy; chữ ký hợp lệ với một khóa công khai tùy ý **không tự chứng minh danh tính**. Khóa riêng cần được bảo vệ và xoay vòng theo chính sách; cùng một bộ byte và đúng thuật toán phải được sử dụng khi xác minh. Trước khi áp dụng, kiểm tra sự hỗ trợ của provider JCA và định dạng khóa trong hệ sinh thái tích hợp.

## 9. Hidden classes: hiểu năng lực nền tảng, không lạm dụng

JEP 371 đưa vào khái niệm *hidden class*: class được định nghĩa động tại runtime, không được thiết kế để code thông thường tham chiếu bằng tên nhị phân như class ứng dụng. API nền tảng liên quan là `MethodHandles.Lookup#defineHiddenClass`.

Điều này hữu ích khi **framework** cần sinh bytecode hoặc cấu trúc thực thi động, chẳng hạn cơ chế triển khai lambda, proxy hay công cụ ngôn ngữ. Người viết code nghiệp vụ thường **không cần tự tạo hidden class**. Nếu cần mô hình hóa dữ liệu, hành vi hoặc điểm mở rộng, hãy ưu tiên class/interface/record bình thường. Hidden classes không thay thế cơ chế quản lý quyền, không biến code tải động trở nên đáng tin và không có nghĩa một class sẽ được giải phóng bộ nhớ ngay lập tức.

## 10. Foreign Function & Memory API: chỉ dùng dạng chuẩn hiện đại

Ở JDK 15, truy cập bộ nhớ bên ngoài Java heap vẫn là hướng phát triển theo cơ chế incubator. Khái niệm còn hữu ích ngày nay là **quản lý vùng nhớ ngoài heap có phạm vi sống rõ ràng và tương tác với mã native**. API đã chính thức từ **JDK 22 (JEP 454)** với gói `java.lang.foreign`; hãy học API này khi thực sự cần làm việc với native library hay dữ liệu ngoài heap.

Ví dụ **chỉ chạy trên JDK 22+**, file **ForeignMemoryDemo.java**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ForeignMemoryDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 42);
            System.out.println(segment.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForeignMemoryDemo.java
java ForeignMemoryDemo
~~~

Kết quả:

~~~text
42
~~~

`Arena` quản lý vòng đời cấp phát, `MemorySegment` biểu diễn vùng nhớ và `ValueLayout` mô tả cách đọc/ghi dữ liệu. Sau khi `arena` đóng, không tiếp tục truy cập segment do arena đó quản lý. Với chương trình chỉ xử lý object Java thông thường, không cần dùng FFM; heap, collections và API chuẩn sẽ đơn giản hơn. Khi gọi hàm native thực, còn phải hiểu ABI, bố cục bộ nhớ, quyền truy cập và chính sách native access của JDK đang sử dụng.

## 11. Chọn năng lực theo bài toán thực tế

| Nhu cầu | Ưu tiên học và áp dụng | Câu hỏi tự kiểm tra |
| --- | --- | --- |
| JSON/SQL/mẫu nhiều dòng | Text blocks | Có giữ đúng newline, indentation và tách dữ liệu đầu vào khỏi câu SQL tĩnh không? |
| DTO/response/value object | Records | Dữ liệu có thực sự mang ngữ nghĩa giá trị và đã xử lý bất biến nông chưa? |
| Phân nhánh theo kiểu | `instanceof` pattern | Scope của biến pattern có được trình biên dịch chứng minh an toàn không? |
| Domain có biến thể hữu hạn | Sealed interfaces/classes kết hợp records | Tập kiểu con có thực sự đóng và thuộc quyền kiểm soát của API không? |
| Service nhạy với pause | ZGC hoặc Shenandoah khi được hỗ trợ | Có số đo latency, throughput, CPU và heap để so sánh chưa? |
| Chữ ký cho thông điệp/artifact | Ed25519/Ed448 qua JCA | Khóa công khai có được xác thực nguồn gốc và khóa riêng có được bảo vệ không? |
| Framework sinh bytecode | Hidden classes | Có nhu cầu runtime code generation thật sự không? |
| Tích hợp native/bộ nhớ ngoài heap | FFM chuẩn trên JDK 22+ | Có kiểm soát vòng đời bộ nhớ và ranh giới native an toàn không? |

## 12. Lỗi hiểu sai dễ gặp

1. **Thấy một feature ở JDK 15 và cho rằng phải bật preview hôm nay.** Records, `instanceof` pattern và sealed types đã được chuẩn hóa ở các bản sau; khi dùng Java 17+ hãy viết cú pháp ổn định.
2. **Cho rằng record bất biến sâu.** Component reference là final nhưng phần tử của collection hoặc đối tượng được tham chiếu vẫn có thể thay đổi nếu không thiết kế phòng vệ.
3. **Dùng sealed types cho API cần mở rộng tự do.** Bộ kiểu con bị giới hạn là một cam kết thiết kế, không phù hợp mọi plugin.
4. **Dùng text block rồi ghép trực tiếp input vào SQL.** Dù chuỗi dễ đọc, nguy cơ SQL injection vẫn tồn tại; dùng tham số truy vấn.
5. **Mặc định ZGC/Shenandoah luôn nhanh hơn.** Chúng tối ưu mục tiêu pause trong những điều kiện nhất định; phải đo trên workload thật.
6. **Nhầm EdDSA với mã hóa hoặc tin chữ ký chỉ vì xác minh ra `true`.** Cần quản lý và xác thực khóa công khai.
7. **Dùng API incubator lịch sử cho code mới.** Với bộ nhớ ngoài heap, dùng gói `java.lang.foreign` đã chuẩn hóa và đúng mức JDK hiện hành.
8. **Cố sử dụng hidden classes trong mô hình domain.** Đây là công cụ hạ tầng, không phải kiểu dữ liệu thay thế class thường.

## 13. Bài tự luyện và tiêu chí đạt

- **Bài 1 (Java 17+):** Viết record `OrderItem(String sku, int quantity)`, từ chối `quantity <= 0`, sau đó in một danh sách item dưới dạng text block hoặc chuỗi được format. Đạt khi giá trị không hợp lệ bị chặn ở constructor và code chạy không cần preview.
- **Bài 2 (Java 17+):** Mô hình hóa `sealed interface ApiResult` gồm `Ok` và `Error` (dùng records), viết hàm nhận `Object` và xử lý bằng `instanceof` pattern. Đạt khi mọi nhánh trả về thông tin đúng và không có cast thủ công.
- **Bài 3 (JDK hiện đại):** Chạy cùng một ứng dụng dưới GC mặc định và ZGC, lưu p95/p99, throughput, CPU, heap và GC log. Đạt khi đưa ra lựa chọn dựa trên số liệu, kể cả trường hợp giữ nguyên GC mặc định.
- **Bài 4 (Java 17+):** Sửa một byte của thông điệp ở ví dụ Ed25519 sau bước ký rồi xác minh lại. Kết quả kỳ vọng là `false`; nêu lý do chữ ký không còn khớp.

**Kết quả học tập mong đợi:** Có thể phân loại chính xác trạng thái của từng năng lực ở JDK 15 và hiện tại; áp dụng bốn công cụ ngôn ngữ đã ổn định; biết khi nào cần GC độ trễ thấp, chữ ký số, hidden classes hoặc FFM; tránh phụ thuộc vào cơ chế thử nghiệm đã thay đổi theo thời gian.

## Nguồn chính thống để tra cứu tiếp

- [Oracle: Java SE 15 Language Changes](https://docs.oracle.com/en/java/javase/15/language/java-language-changes.html) — trạng thái tính năng ở JDK 15.
- [Oracle: Java SE 17 Language Changes](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html) — mốc chuẩn hóa records, `instanceof` pattern và sealed types.
- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378); [JEP 395 — Records](https://openjdk.org/jeps/395); [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394); [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [JEP 377 — ZGC Production](https://openjdk.org/jeps/377); [JEP 379 — Shenandoah Production](https://openjdk.org/jeps/379); [Oracle: Garbage Collection Tuning Guide, JDK 25](https://docs.oracle.com/en/java/javase/25/gctuning/index.html).
- [JEP 339 — Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339); [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371); [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454).