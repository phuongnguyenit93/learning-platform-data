# Bỏ qua đối tượng ngoại lệ trong `catch` khi thông tin ngoại lệ không cần thiết

Trong Java, một nhánh `catch` thường khai báo tham số để nhận đối tượng ngoại lệ:

```java
try {
    loadOptionalFeature();
} catch (ClassNotFoundException exception) {
    // Chỉ cần chuyển sang chế độ không có tính năng tùy chọn.
    useBasicMode();
}
```

Nếu thân `catch` chỉ cần biết loại ngoại lệ để chọn cách xử lý, nhưng không đọc đối tượng ngoại lệ, tên `exception` trở thành một biến không được sử dụng. Từ Java 22, có thể thay tên biến đó bằng `_`:

```java
try {
    loadOptionalFeature();
} catch (ClassNotFoundException _) {
    useBasicMode();
}
```

Đây là một trường hợp sử dụng **biến không tên (unnamed variable)** được chuẩn hóa qua JEP 456 trong JDK 22. Cú pháp này vẫn dùng được trong các phiên bản Java hiện đại. Không cần bật preview hoặc thêm thư viện để sử dụng tính năng này.

## 1. Vì sao cần tham số `catch` không tên?

Tham số của `catch` cho biết loại ngoại lệ mà nhánh đó xử lý và, trong cú pháp thông thường, cung cấp một biến để truy cập đối tượng ngoại lệ. Tuy nhiên, có những tình huống chương trình chỉ cần phản ứng theo loại lỗi:

- Một tệp cấu hình tùy chọn không tồn tại nên chương trình dùng cấu hình mặc định.
- Một lớp của phần tích hợp tùy chọn không có trên classpath nên chương trình chuyển sang chức năng cơ bản.
- Dữ liệu đầu vào không chuyển được sang kiểu mong muốn nên hàm trả về một kết quả biểu thị dữ liệu không hợp lệ.
- Một thao tác bị gián đoạn và phương thức xử lý bằng cách khôi phục trạng thái interrupt rồi kết thúc.

Trong những trường hợp này, nội dung như thông điệp, stack trace hoặc cause của ngoại lệ không tham gia vào quyết định xử lý. Khai báo `_` thể hiện rõ rằng chương trình cố ý không giữ tham chiếu tới đối tượng ngoại lệ.

## 2. Cú pháp và cách hoạt động

Cú pháp cơ bản:

```java
try {
    // Thao tác có thể ném ngoại lệ.
} catch (Exception _) {
    // Xử lý dựa trên loại ngoại lệ.
}
```

`_` là ký hiệu dành cho biến không tên. Nó được khai báo ở vị trí vốn cần tên biến, nhưng không tạo ra một tên có thể dùng trong thân khối lệnh. Vì vậy, không thể đọc đối tượng ngoại lệ thông qua `_`, gọi `_ .getMessage()` hoặc dùng `_` để ném lại chính đối tượng đó.

Tham số không tên vẫn có đầy đủ vai trò của tham số `catch` về mặt điều khiển luồng:

1. JVM và cơ chế xử lý ngoại lệ xác định nhánh `catch` phù hợp theo kiểu ngoại lệ.
2. Khi ngoại lệ khớp kiểu, thân nhánh `catch` được thực thi.
3. Chương trình có thể trả về, tiếp tục với giá trị thay thế, thực hiện hành động phục hồi hoặc ném một ngoại lệ khác.

Việc đặt tên tham số thành `_` **không tự động bỏ qua hoặc nuốt ngoại lệ**. Hành vi xử lý được quyết định bởi các câu lệnh trong thân `catch`.

### Ví dụ tối giản

```java
static int parseOrDefault(String text, int defaultValue) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException _) {
        return defaultValue;
    }
}
```

Khi `text` không biểu diễn được một số nguyên, `Integer.parseInt` ném `NumberFormatException`. Phương thức trả về giá trị mặc định và không cần đọc thông điệp lỗi hay stack trace. Tên `_` truyền đạt đúng ý định đó.

## 3. Ví dụ thực tế: đọc tệp cấu hình tùy chọn

Giả sử ứng dụng có một tệp cấu hình bổ sung. Nếu tệp không tồn tại, ứng dụng có thể tiếp tục bằng cách dùng cấu hình mặc định. Các lỗi đọc tệp khác vẫn cần được chuyển cho bên gọi xử lý.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.Optional;

public class OptionalConfig {
    static Optional<String> readConfig(Path path) throws IOException {
        try {
            return Optional.of(Files.readString(path));
        } catch (NoSuchFileException _) {
            return Optional.empty();
        }
    }
}
```

Ở đây, chương trình chỉ quan tâm rằng tệp không tồn tại. `NoSuchFileException` được xử lý bằng `Optional.empty()`. Các lỗi I/O khác vẫn được khai báo qua `throws IOException` và truyền cho bên gọi. Cách viết này giúp phạm vi xử lý ngoại lệ rõ ràng: chỉ trường hợp thiếu tệp mới được xem là không có cấu hình.

Nếu cần ghi log đường dẫn, thông điệp hệ điều hành hoặc nguyên nhân chi tiết, hãy đặt tên cho tham số:

```java
try {
    return Optional.of(Files.readString(path));
} catch (NoSuchFileException exception) {
    logger.debug("Optional config file is missing: {}", exception.getFile());
    return Optional.empty();
}
```

Hai cách viết phục vụ hai nhu cầu khác nhau. Dùng `_` khi đối tượng ngoại lệ thực sự không được sử dụng; dùng tên như `exception` khi cần truy cập thông tin của nó.

## 4. Ví dụ thực tế: chuyển đầu vào không hợp lệ thành kết quả mặc định

Một hàm phân tích cổng mạng có thể trả về `OptionalInt.empty()` khi chuỗi không phải số hoặc giá trị nằm ngoài khoảng cổng hợp lệ:

```java
import java.util.OptionalInt;

public class PortParser {
    static OptionalInt parsePort(String text) {
        try {
            int port = Integer.parseInt(text);
            if (port < 1 || port > 65_535) {
                return OptionalInt.empty();
            }
            return OptionalInt.of(port);
        } catch (NumberFormatException _) {
            return OptionalInt.empty();
        }
    }
}
```

Phương thức không cần thông tin cụ thể về chuỗi sai định dạng. Nó chỉ chuyển trường hợp không phân tích được thành kết quả không có giá trị. Việc kiểm tra khoảng `1..65_535` vẫn được thực hiện riêng sau khi chuyển đổi thành công.

Không nên áp dụng cách này nếu người gọi cần phân biệt các nguyên nhân như chuỗi rỗng, ký tự không hợp lệ hoặc giá trị vượt giới hạn. Khi cần phân loại chi tiết, hãy trả về kiểu kết quả phù hợp hoặc giữ tham số ngoại lệ để đọc thông tin cần thiết.

## 5. Kết hợp nhiều loại ngoại lệ

Tham số không tên cũng có thể được dùng trong `catch` đa ngoại lệ (multi-catch):

```java
try {
    performOptionalOperation();
} catch (IOException | ReflectiveOperationException _) {
    useFallback();
}
```

Ví dụ trên gom hai loại lỗi có cùng cách phục hồi vào một nhánh. Các quy tắc multi-catch vẫn được áp dụng: những kiểu ngoại lệ trong danh sách phải thỏa điều kiện của Java và không được có quan hệ kế thừa khiến một kiểu bao hàm kiểu còn lại. Nếu hai loại ngoại lệ cần cách xử lý khác nhau, nên tách thành các nhánh `catch` riêng.

## 6. Trường hợp cần đặc biệt cẩn thận: `InterruptedException`

Không phải ngoại lệ nào không cần đọc thông điệp cũng có thể bỏ qua tác động của nó. `InterruptedException` biểu thị một thao tác đang chờ đã bị yêu cầu gián đoạn. Khi một số phương thức chờ như `Thread.sleep` ném ngoại lệ này, trạng thái interrupt của thread bị xóa trước khi ngoại lệ được ném.

Nếu phương thức không truyền `InterruptedException` lên cho bên gọi mà tự kết thúc, thông thường cần khôi phục trạng thái interrupt:

```java
static boolean waitBriefly() {
    try {
        Thread.sleep(1_000);
        return true;
    } catch (InterruptedException _) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

Ở ví dụ này, không cần đối tượng ngoại lệ để phục hồi trạng thái. Tuy vậy, chương trình vẫn xử lý tín hiệu gián đoạn bằng `Thread.currentThread().interrupt()` và thông báo kết quả cho bên gọi.

Nếu chữ ký phương thức cho phép truyền tín hiệu gián đoạn lên trên, cách đơn giản hơn có thể là khai báo `throws InterruptedException` và không bắt ngoại lệ tại đây:

```java
static void waitForWork() throws InterruptedException {
    Thread.sleep(1_000);
}
```

Không viết một nhánh `catch (InterruptedException _)` rỗng chỉ để chương trình tiếp tục chạy. Làm như vậy có thể khiến thành phần gọi không còn nhận biết yêu cầu dừng hoặc hủy tác vụ.

## 7. Khi nào nên dùng và khi nào nên giữ tên biến?

| Tình huống | Cách viết phù hợp | Lý do |
| --- | --- | --- |
| Chỉ cần xử lý theo loại ngoại lệ và trả về giá trị thay thế | `catch (NumberFormatException _)` | Không cần thông tin của đối tượng. |
| Tệp tùy chọn không tồn tại, dùng cấu hình mặc định | `catch (NoSuchFileException _)` | Chỉ cần nhận diện loại lỗi cụ thể. |
| Cần ghi thông điệp, stack trace hoặc cause | `catch (IOException exception)` | Cần truy cập đối tượng ngoại lệ. |
| Cần ném lại chính ngoại lệ hoặc bọc ngoại lệ làm cause | `catch (Exception exception)` | Cần tham chiếu tới đối tượng để truyền tiếp. |
| Cần khôi phục interrupt nhưng không cần thông tin lỗi | `catch (InterruptedException _)` và gọi `interrupt()` | Có thể xử lý đúng tín hiệu mà không giữ tham chiếu. |
| Chưa biết cách xử lý, định bắt mọi lỗi để bỏ qua | Không dùng `catch (Exception _)` một cách tùy tiện | Có thể che giấu lỗi lập trình hoặc lỗi hệ thống. |

Một nguyên tắc hữu ích là: chỉ dùng biến không tên sau khi đã xác định rằng đối tượng ngoại lệ không tham gia vào log, chẩn đoán, quyết định phục hồi, chuyển tiếp hoặc kiểm thử. Nếu còn bất kỳ nhu cầu nào trong số đó, hãy giữ tên biến.

## 8. Những quy tắc cần nhớ

### `_` không phải tên biến thông thường

Ký hiệu `_` đã được dành riêng trong Java từ Java 9, nên không thể dùng nó làm tên biến thông thường như `String _ = "value";`. Java 22 cho phép `_` trong những vị trí khai báo biến không tên được ngôn ngữ quy định, trong đó có tham số của `catch`.

Ví dụ hợp lệ trong Java 22 trở lên:

```java
try {
    connect();
} catch (IOException _) {
    reconnectWithDefaultEndpoint();
}
```

Không thể tham chiếu đến `_` trong thân khối lệnh. Nếu cần gọi `exception.getMessage()`, đọc `exception.getCause()` hoặc ném lại đối tượng đó, phải khai báo một tên biến bình thường.

### Kiểu ngoại lệ vẫn quan trọng

Tham số không tên không thay đổi các quy tắc chọn nhánh `catch`. Java vẫn xét kiểu ngoại lệ, quan hệ kế thừa và thứ tự các nhánh. Hãy bắt kiểu cụ thể mà phương thức có thể xử lý có chủ đích; tránh bắt `Exception` hoặc `Throwable` chỉ để bỏ qua mọi lỗi.

### Không biến nhánh `catch` thành khối rỗng thiếu chủ đích

`catch (SomeException _) { }` vẫn là một cách xử lý ngoại lệ, nhưng thân khối rỗng có thể làm lỗi biến mất mà không để lại dấu vết. Chỉ dùng khi việc bỏ qua đã được xác định rõ bởi hợp đồng của tính năng và có giải thích phù hợp. Trong các hệ thống cần quan sát vận hành, nên ghi log hoặc cung cấp số liệu theo cách phù hợp thay vì âm thầm bỏ qua lỗi.

### Không dùng `_` khi cần phân biệt nguyên nhân

Nếu logic cần kiểm tra message, mã lỗi, đường dẫn, nguyên nhân gốc hoặc dữ liệu đính kèm trong ngoại lệ, tham số phải có tên. Việc dùng `_` sẽ làm mất khả năng truy cập trực tiếp đối tượng trong thân `catch`.

## 9. Phiên bản Java và khả năng áp dụng hiện nay

Unnamed Variables & Patterns được giới thiệu lần đầu dưới dạng preview trong JDK 21 qua JEP 443. JEP 456 hoàn thiện tính năng và đưa nó thành tính năng chính thức trong JDK 22. Vì vậy, khi sử dụng cú pháp `catch (SomeException _)` trong mã Java hiện đại, hãy lấy JDK 22 trở lên làm baseline.

Ví dụ có thể biên dịch với JDK 22 trở lên mà không cần bật preview:

```bash
javac --release 22 -d out src/PortParser.java
```

Nếu dự án đặt source/release thấp hơn 22, cú pháp biến không tên này không thuộc ngôn ngữ của baseline đó. Hãy kiểm tra cấu hình compiler của dự án trước khi áp dụng. Không cần thêm dependency bên ngoài vì đây là tính năng của ngôn ngữ Java.

## 10. Tóm tắt

- Dùng `catch (SomeException _)` khi cần xử lý theo loại ngoại lệ nhưng không cần tham chiếu tới đối tượng ngoại lệ.
- `_` làm rõ rằng việc không dùng đối tượng là có chủ đích; thân `catch` vẫn phải thực hiện cách xử lý phù hợp.
- Nếu cần log chi tiết, đọc cause, phân loại theo dữ liệu ngoại lệ hoặc ném lại chính đối tượng, hãy giữ tên tham số.
- Không bỏ qua `InterruptedException` một cách im lặng; truyền tiếp ngoại lệ hoặc khôi phục trạng thái interrupt khi tự xử lý.
- Cú pháp này là tính năng chính thức từ Java 22 theo JEP 456 và vẫn áp dụng trong Java hiện đại.

## Tài liệu tham khảo

- [JEP 456: Unnamed Variables & Patterns](https://openjdk.org/jeps/456) — đặc tả tính năng chính thức trong JDK 22, bao gồm việc dùng biến không tên trong các vị trí khai báo được hỗ trợ.
- [JEP 443: Unnamed Patterns and Variables (Preview)](https://openjdk.org/jeps/443) — mốc preview ban đầu trong JDK 21, dùng để tham khảo lịch sử phát triển.
- [Java Language Specification, Java SE 22 — The `try` statement](https://docs.oracle.com/javase/specs/jls/se22/html/jls-14.html#jls-14.20) — quy tắc của câu lệnh `try`, `catch` và tham số ngoại lệ.
