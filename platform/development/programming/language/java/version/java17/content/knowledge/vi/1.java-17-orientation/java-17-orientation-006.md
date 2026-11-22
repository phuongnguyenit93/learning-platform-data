# Phạm vi ví dụ Java 17: API chính thức còn áp dụng, không dùng API thử nghiệm cũ

> **Ngữ cảnh:** Java 17 → Định hướng Java 17. Các ví dụ trong tài liệu và trong quá trình học ưu tiên những tính năng ngôn ngữ đã chính thức phát hành, API Java SE được tài liệu hóa và cách viết còn phù hợp cho mã nguồn mới. **Mốc tương thích của ví dụ là Java 17**, dù một số tính năng có thể đã được hoàn thiện hoặc bổ sung ở những phiên bản Java mới hơn.

## 1. Vì sao cần xác định phạm vi?

Khi đọc tài liệu về Java, ta dễ gặp những đoạn mã thuộc nhiều thời kỳ: API cũ vẫn còn để tương thích, tính năng từng ở trạng thái *preview*, module *incubator*, API nội bộ của một bản JDK, và API chỉ xuất hiện từ Java 21 hoặc các phiên bản sau. Các đoạn mã ấy không có cùng mức độ phù hợp để làm ví dụ cho một khóa học Java 17.

Phạm vi dùng ở đây có ba mục tiêu:

1. **Chạy với JDK 17 theo cấu hình thông thường:** ví dụ không cần bật preview, thêm module incubator hoặc truy cập package nội bộ.
2. **Dùng kiến thức còn hữu ích hiện nay:** ưu tiên API hiện đại, chính thức và các thực hành có thể tiếp tục áp dụng trong dự án thực tế.
3. **Phân biệt rõ phiên bản và trạng thái:** một API đã ổn định trong Java mới hơn không mặc nhiên tồn tại trong Java 17; một API cũ còn biên dịch được cũng chưa chắc là lựa chọn nên dùng cho mã mới.

Ở đây, **API** là lớp, interface, phương thức, package và module mà chương trình sử dụng. **Tính năng ngôn ngữ** là cú pháp hoặc quy tắc của Java, chẳng hạn `record`, `sealed` hay `switch` expression. Cả hai đều phải được kiểm tra theo phiên bản Java 17.

## 2. Quy tắc chọn API và tính năng

| Nhóm | Có dùng trong ví dụ Java 17? | Cách quyết định |
| --- | --- | --- |
| API tiêu chuẩn Java SE 17, được tài liệu hóa và còn phù hợp | **Có** | Kiểm tra package, lớp, phương thức trong [Java SE 17 API Specification](https://docs.oracle.com/en/java/javase/17/docs/api/index.html). |
| Tính năng ngôn ngữ đã hoàn tất (*final*) trước hoặc trong Java 17 | **Có** | Biên dịch bằng Java 17 mà không cần `--enable-preview`. |
| API cũ vẫn được hỗ trợ nhưng đã có lựa chọn tốt hơn cho mã mới | **Chỉ khi cần giải thích tương thích/migration** | Nêu lý do tồn tại và ưu tiên API thay thế trong ví dụ chính. |
| Tính năng *preview* trong Java 17 | **Không** | Chưa là tính năng ngôn ngữ chính thức của mốc Java 17; không bật `--enable-preview` để sử dụng. |
| Module/API *incubator* hoặc API nội bộ JDK | **Không** | Có thể đổi tên, đổi hành vi hoặc biến mất; không coi là Java SE API ổn định. |
| API chỉ được bổ sung ở Java 18+ | **Không** | Dù đã ổn định ở bản mới, vẫn nằm ngoài phạm vi chạy với Java 17. |
| Thư viện bên thứ ba | **Không mặc định** | Chỉ đưa vào khi bài học có yêu cầu rõ và phải nói đó là dependency bên ngoài, không thuộc JDK. |

### 2.1. Những API tiêu chuẩn nên ưu tiên

| Nhu cầu | API phù hợp trong Java 17 | Ghi chú sử dụng |
| --- | --- | --- |
| Ngày giờ, múi giờ | `java.time.LocalDate`, `Instant`, `ZonedDateTime`, `DateTimeFormatter` | Phân biệt thời điểm tuyệt đối, ngày theo lịch và ngày giờ có múi giờ. |
| Tệp và đường dẫn | `java.nio.file.Path`, `Files` | Dùng `Path.of(...)`, `Files.readString(...)`, `Files.writeString(...)`; chọn charset rõ ràng khi cần. |
| Danh sách, map, tập hợp | `List`, `Map`, `Set`, `List.of(...)`, `Map.of(...)` | Các factory `of` tạo collection không thể sửa trực tiếp. |
| Xử lý dữ liệu theo chuỗi thao tác | `java.util.stream.Stream`, `Collectors` | `Stream.toList()` có trong Java 17 và cho danh sách không thể sửa trực tiếp. |
| Giá trị có thể vắng mặt | `java.util.Optional` | Hữu ích cho kiểu trả về; không biến mọi field thành `Optional` theo thói quen. |
| HTTP client | `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse` | API tiêu chuẩn đã ổn định từ Java 11. |
| Xử lý bất đồng bộ, chạy đồng thời | `ExecutorService`, `CompletableFuture`, `BlockingQueue` | Dùng mô hình thread truyền thống; không giả định Java 17 đã có virtual threads. |
| Kiểu dữ liệu chính xác cho số tiền | `java.math.BigDecimal` | Không dùng `double` để biểu diễn số tiền cần độ chính xác thập phân. |
| JDBC, bảo mật, mã hóa | `java.sql`, `javax.sql`, `java.security`, `javax.crypto` | Các namespace `javax.*` này vẫn là một phần của Java SE; không đánh đồng mọi `javax.*` với legacy. |

Những API trên không phải tất cả đều được **giới thiệu** ở Java 17. Tiêu chí là chúng **có sẵn, được hỗ trợ chính thức và dùng tốt khi viết mã chạy trên Java 17**.

### 2.2. Những tính năng ngôn ngữ đã chính thức có ở Java 17

- **Switch expressions:** trả về giá trị bằng `switch`, dùng mũi tên `->` và `yield` nếu một nhánh cần khối lệnh.
- **Text blocks:** chuỗi nhiều dòng bằng dấu `"""`, hữu ích khi viết dữ liệu mẫu hoặc nội dung nhiều dòng.
- **Records:** định nghĩa các đối tượng mang dữ liệu gọn và có ngữ nghĩa giá trị.
- **Pattern matching cho `instanceof`:** kiểm tra kiểu và khai báo biến đã được ép kiểu ngay trong điều kiện.
- **Sealed classes/interfaces:** giới hạn những kiểu được phép kế thừa hoặc triển khai, với `sealed`, `permits`, `final`, `sealed`, `non-sealed`.

Đây đều là dạng đã hoàn tất ở hoặc trước Java 17. Riêng **pattern matching trong `switch`** vẫn là preview ở Java 17, nên không đưa vào ví dụ theo mốc này. Cùng mang tên “pattern matching” không có nghĩa chúng có cùng trạng thái.

## 3. Ví dụ hoàn chỉnh: chỉ dùng Java 17 tiêu chuẩn

Ví dụ sau kết hợp `record`, `java.time`, `List.of`, `Stream.toList`, `Path` và `Files`. Chương trình tạo tệp tạm, ghi và đọc văn bản UTF-8, sau đó xóa tệp tạm khi hoàn thành. Nó không yêu cầu framework hay dependency ngoài JDK.

**Tệp `Java17Example.java`:**

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;

public class Java17Example {
    record Lesson(String title, LocalDate publishedOn) {
        Lesson {
            Objects.requireNonNull(title, "title");
            Objects.requireNonNull(publishedOn, "publishedOn");
            if (title.isBlank()) {
                throw new IllegalArgumentException("Title must not be blank");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        List<Lesson> lessons = List.of(
            new Lesson("Java 17", LocalDate.of(2024, 1, 1)),
            new Lesson("Standard API", LocalDate.of(2024, 1, 2))
        );

        List<String> titles = lessons.stream()
            .map(Lesson::title)
            .filter(title -> title.length() >= 7)
            .toList();

        Path file = Files.createTempFile("java17-api-", ".txt");
        try {
            Files.writeString(
                file,
                String.join(System.lineSeparator(), titles),
                StandardCharsets.UTF_8
            );
            String savedText = Files.readString(file, StandardCharsets.UTF_8);
            System.out.println(savedText);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17:

~~~shell
java -version
javac -version
javac --release 17 Java17Example.java
java Java17Example
~~~

Kết quả in ra:

~~~text
Java 17
Standard API
~~~

Tại sao ví dụ này thuộc phạm vi?

1. `record` là tính năng ngôn ngữ đã chính thức từ Java 16, nên Java 17 dùng được mà không cần preview.
2. `LocalDate` tránh cách biểu diễn ngày tháng kiểu cũ; `Objects.requireNonNull` và điều kiện `isBlank()` xác nhận dữ liệu đầu vào.
3. `List.of` và `Stream.toList` là API chính thức trong Java 17. Hai danh sách tương ứng không cho phép thêm/xóa phần tử; đây là đặc tính cần nắm khi lựa chọn API.
4. `Files.createTempFile`, `writeString`, `readString` và `deleteIfExists` giúp quản lý tệp mà không phải tự ghép đường dẫn hoặc phụ thuộc vào thư viện ngoài.
5. `finally` cố gắng xóa tệp ngay cả khi việc ghi/đọc phát sinh lỗi. Nếu xóa thất bại, ngoại lệ I/O vẫn có thể được ném ra; ví dụ không ngầm đảm bảo thao tác hệ thống tệp luôn thành công.

> **Lưu ý:** `--release 17` giới hạn mức ngôn ngữ, bytecode và các API nền tảng theo Java 17 khi biên dịch bằng JDK hỗ trợ tùy chọn này. Nó không tự động kiểm chứng mọi dependency ngoài JDK hoặc hành vi lúc chạy. Để chạy, môi trường cần phiên bản Java tương thích với class file đã tạo.

## 4. Ví dụ: kết hợp tính năng ngôn ngữ đã ổn định

Ví dụ dưới dùng sealed interface và pattern matching của `instanceof`. Mã không dùng `switch` pattern matching preview.

**Tệp `Java17Language.java`:**

~~~java
public class Java17Language {
    sealed interface Result permits Success, Failure {
    }

    record Success(String value) implements Result {
    }

    record Failure(String message) implements Result {
    }

    static String describe(Result result) {
        if (result instanceof Success success) {
            return "Thành công: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "Thất bại: " + failure.message();
        }
        throw new IllegalStateException("Loại kết quả chưa được xử lý");
    }

    static String levelName(int level) {
        return switch (level) {
            case 1 -> "Cơ bản";
            case 2 -> "Nâng cao";
            default -> "Chưa xác định";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("Java 17")));
        System.out.println(levelName(2));
    }
}
~~~

~~~shell
javac --release 17 Java17Language.java
java Java17Language
~~~

Trong ví dụ này, `sealed` kiểm soát những kiểu có thể triển khai `Result`; `record` hiện thực các kiểu dữ liệu cụ thể; `instanceof Success success` thực hiện so khớp kiểu và tạo biến `success`; còn `switch` là một **biểu thức trả về giá trị**, không phải switch pattern matching. Các cú pháp này đều dùng được trong Java 17 chính thức.

## 5. Ví dụ API nền tảng cho HTTP

Khi cần gửi HTTP request đơn giản, hãy giới thiệu `java.net.http.HttpClient` của Java SE trước khi chọn thư viện HTTP bên ngoài cho các nhu cầu đặc thù.

**Tệp `Java17Http.java`:**

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class Java17Http {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://example.com/"))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());

        System.out.println("HTTP status: " + response.statusCode());
    }
}
~~~

~~~shell
javac --release 17 Java17Http.java
java Java17Http
~~~

Ví dụ này cần kết nối mạng để chạy thành công; mã trạng thái, tốc độ và khả năng kết nối phụ thuộc môi trường. Các lớp HTTP được dùng đều thuộc Java SE 17 và không yêu cầu thư viện như OkHttp hay Apache HttpClient. Trong ứng dụng thực tế cần xử lý I/O exception, timeout, trạng thái HTTP ngoài nhóm thành công và chính sách bảo mật theo ngữ cảnh.

## 6. Các API, cú pháp và kỹ thuật ngoài phạm vi

### 6.1. Preview trong Java 17

*Preview feature* là tính năng được đưa ra để lập trình viên thử nghiệm trước khi trở thành một phần chính thức của ngôn ngữ hoặc nền tảng. Thiết kế và cú pháp của nó có thể thay đổi qua các phiên bản. Java 17 yêu cầu cách bật riêng cho những tính năng thuộc loại này.

Ví dụ nổi bật là **pattern matching for switch**, được giới thiệu dưới dạng preview trong Java 17 (JEP 406). Không dùng đoạn sau làm ví dụ chuẩn Java 17:

~~~java
// Không dùng trong bài Java 17: switch pattern matching là preview ở JDK 17.
// static String inspect(Object value) {
//     return switch (value) {
//         case String text -> text;
//         case Integer number -> number.toString();
//         default -> "Khác";
//     };
// }
~~~

Thay vào đó, với Java 17 hãy dùng `instanceof` pattern matching đã chính thức, hoặc switch expression chỉ với các nhánh mà Java 17 ổn định hỗ trợ. Việc switch pattern matching trở thành tính năng chính thức ở một Java mới hơn không làm thay đổi trạng thái của nó **trong bản Java 17**.

### 6.2. Incubator và JDK internal APIs

Các module *incubator* đưa API ra để thử nghiệm và thu nhận phản hồi; chúng chưa có cam kết tương thích tương tự Java SE API ổn định. Những ví dụ cần loại khỏi bài học cơ bản:

- `jdk.incubator.vector`: Vector API còn ở giai đoạn incubator trong Java 17 (JEP 414).
- `jdk.incubator.foreign`: Foreign Function & Memory API ở dạng incubator trong Java 17 (JEP 412). Các cách dùng cũ của module này không phải mẫu chuẩn nên sao chép cho dự án Java 17.
- Các package nội bộ như `jdk.internal.*` và `sun.misc.Unsafe`: không coi là nền tảng ứng dụng thông thường; việc buộc truy cập bằng `--add-exports` hoặc `--add-opens` là tín hiệu cần xem lại thiết kế.

Không mặc định cho rằng mọi API có tiền tố `jdk.*` hoặc `com.sun.*` đều thuộc Java SE, cũng không kết luận tình trạng hỗ trợ chỉ từ tên package. Hãy tra đúng tài liệu của API, module và phiên bản dự định dùng.

### 6.3. API thuộc bản Java mới hơn

Những ví dụ sau nằm ngoài mốc Java 17 dù hữu ích ở các phiên bản Java khác:

| API/tính năng | Mốc chính thức tương ứng | Vì sao không đưa vào ví dụ Java 17? |
| --- | --- | --- |
| Virtual threads, `Thread.ofVirtual()` | Java 21 | Chưa có trong API chuẩn của Java 17. |
| `SequencedCollection` | Java 21 | Interface này chưa tồn tại ở Java 17. |
| API FFM chuẩn trong `java.lang.foreign` | Java 22 | Khác với module incubator cũ; không thuộc Java SE 17. |
| Pattern matching cho `switch` (dạng chính thức) | Java 21 | Dạng có ở Java 17 vẫn là preview. |

Nếu muốn viết ví dụ riêng cho Java 21/22+, phải **ghi rõ mốc Java mới** và cập nhật công cụ, dependency, hướng dẫn chạy; không trộn thẳng vào bài dạy có mục tiêu tương thích Java 17.

### 6.4. API cũ, deprecated và phần mềm bên thứ ba

Không phải API cũ nào cũng đã bị loại khỏi JDK; và **deprecated** khác với **preview**:

- `java.util.Date` và `Calendar` vẫn có thể gặp trong hệ thống cũ, nhưng với nghiệp vụ ngày giờ mới nên bắt đầu từ `java.time`. Trường hợp kết nối mã cũ có thể trình bày cách chuyển đổi rõ ràng.
- `Thread.stop()` và các cách dừng luồng cưỡng bức không phải mẫu lập trình đồng thời an toàn. Dùng cơ chế hủy có hợp tác như `interrupt()` và xử lý đúng giao thức hủy.
- Các ứng dụng applet, API đã bị loại khỏi nền tảng, hoặc hướng dẫn phụ thuộc vào môi trường Java cổ điển không phải ví dụ mở đầu phù hợp cho Java 17.
- Spring, Jackson, Guava, Lombok, JUnit và thư viện tương tự là thành phần bên ngoài. Chúng có thể hữu ích nhưng cần được giới thiệu với dependency, phiên bản và mục đích rõ ràng; không nói rằng chúng đi kèm Java SE 17.
- Không xếp mọi namespace `javax.*` vào nhóm đã lỗi thời: chẳng hạn `javax.crypto` và `javax.sql` vẫn có API tiêu chuẩn trong Java 17. Tình trạng phải được kiểm tra ở **từng API cụ thể**.

## 7. Cách nhận diện một ví dụ đáng dùng

Khi đọc một đoạn mã trên blog, diễn đàn hoặc câu trả lời cũ, hãy tự hỏi theo thứ tự:

1. **Phiên bản:** tác giả đang dùng Java mấy? Đoạn mã có được giới thiệu hoặc thay đổi ở Java 18+ không?
2. **Nguồn chính thức:** lớp hoặc cú pháp được mô tả trong tài liệu Java SE 17 hoặc tài liệu tính năng đã hoàn tất chưa?
3. **Trạng thái:** có chữ *preview*, *incubator*, *experimental*, *internal* hoặc yêu cầu `--enable-preview`, `--add-modules jdk.incubator.*` không?
4. **Mức độ hiện đại:** API vẫn phù hợp cho mã mới hay chỉ tồn tại vì tương thích với chương trình cũ?
5. **Khả năng tái lập:** đã nói rõ JDK, cách biên dịch, điều kiện mạng/tệp, dependency và hành vi cần quan sát chưa?

Ví dụ đạt phạm vi thường có cấu trúc dễ đọc, ít phụ thuộc, không yêu cầu cờ kích hoạt đặc biệt và thể hiện được lý do chọn API. Với mã dùng mạng, cơ sở dữ liệu hoặc hệ thống tệp, phải nêu các điều kiện môi trường ảnh hưởng đến kết quả.

**Dùng `--release 17` khi biên dịch** là một cách hữu ích để phát hiện việc vô tình sử dụng ngôn ngữ hoặc API nền tảng vượt quá mốc Java 17. Với project có dependency, công cụ build còn cần cấu hình phiên bản Java, tương thích của các thư viện và kiểm thử trên runtime dự định triển khai.

## 8. Một số câu hỏi dễ nhầm

**Java 17 là LTS, vậy mọi thứ có trong JDK 17 đều đã ổn định?** Không. Java 17 là bản LTS, nhưng bản phát hành này vẫn có thể chứa tính năng preview, module incubator và API nội bộ. LTS không phải nhãn ổn định cho từng API riêng lẻ.

**Tính năng đã trở thành chính thức ở Java 21/22 thì có được dùng trong bài Java 17?** Không, nếu yêu cầu là chạy trên Java 17. Hãy xét trạng thái và sự tồn tại của API tại chính mốc Java 17.

**Có phải chỉ được học những API ra mắt năm Java 17 phát hành?** Không. Phần lớn nền tảng tiêu chuẩn của Java 17 kế thừa nhiều API ổn định từ các bản trước. API cũ nhưng còn phù hợp vẫn là đối tượng học tốt.

**Nếu đoạn code biên dịch được khi bật `--enable-preview` thì đã đáp ứng yêu cầu chưa?** Chưa. Mục tiêu là ví dụ dựa trên tính năng chính thức, chạy theo cấu hình Java 17 thông thường.

**Có nên cấm dùng mọi thư viện ngoài JDK?** Không cần cấm. Tài liệu nền tảng nên bắt đầu với API chuẩn để người học nhận biết Java cung cấp những gì. Khi một bài cần framework hoặc thư viện, hãy công khai dependency và giải thích vì sao cần đến nó.

## 9. Tài liệu đối chiếu

- [Java SE 17 API Specification — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/index.html): tra cứu lớp, interface, package và module của phiên bản 17.
- [Java 17 Language Updates — Oracle](https://docs.oracle.com/en/java/javase/17/language/index.html): kiểm tra những cập nhật về ngôn ngữ.
- [JEP 12 — Preview Language and VM Features](https://openjdk.org/jeps/12): giải thích vòng đời của preview.
- [JEP 11 — Incubator Modules](https://openjdk.org/jeps/11): giải thích mục đích và đặc tính của module incubator.
- [JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): ví dụ về tính năng chưa chính thức ở Java 17.
- [JEP 412 — Foreign Function & Memory API (Incubator)](https://openjdk.org/jeps/412) và [JEP 414 — Vector API (Second Incubator)](https://openjdk.org/jeps/414): hai trường hợp API incubator liên quan Java 17.

**Nguyên tắc áp dụng xuyên suốt:** lấy Java SE 17 và cú pháp đã hoàn tất làm đường chuẩn; dùng API được tài liệu hóa, còn phù hợp cho mã mới; với công nghệ khác mốc phiên bản hoặc trạng thái thử nghiệm, giới thiệu riêng với nhãn và điều kiện tương ứng.
