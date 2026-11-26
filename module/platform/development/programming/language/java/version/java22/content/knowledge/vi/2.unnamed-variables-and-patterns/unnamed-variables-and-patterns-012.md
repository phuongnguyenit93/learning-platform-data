# Refactor mã bằng biến không tên mà vẫn giữ rõ ý định và xử lý lỗi có ích

Biến không tên (*unnamed variable*) và mẫu không tên (*unnamed pattern*) dùng ký tự gạch dưới `_` để thể hiện rằng một giá trị được khai báo hoặc được kiểm tra nhưng chương trình không cần giữ tên để sử dụng nó về sau. Tính năng này giúp mã nguồn bớt những tên giả như `ignored`, `unused` hoặc `unusedColor`, đồng thời cho người đọc biết rõ phần dữ liệu nào không tham gia vào logic.

Tính năng được chuẩn hóa trong Java 22 theo JEP 456. Nó đã là một phần chính thức của ngôn ngữ từ Java 22, không phải preview feature; các ví dụ trong bài không cần `--enable-preview`. Tính năng vẫn có trong tài liệu ngôn ngữ Java SE 27 tại thời điểm 24/11/2026.

Sau bài học, bạn có thể:

- Chọn đúng vị trí dùng `_` cho biến cục bộ, vòng lặp, tài nguyên, ngoại lệ và tham số lambda.
- Phân biệt biến không tên với mẫu không tên trong record pattern và type pattern.
- Refactor mã mà không làm thay đổi hành vi của biểu thức khởi tạo hoặc logic xử lý lỗi.
- Nhận biết trường hợp vẫn cần một tên biến để ghi log, phân tích nguyên nhân hoặc sử dụng giá trị.

## 1. Vì sao nên dùng biến không tên?

Trong mã cũ, một biến thường được đặt tên `ignored` dù không bao giờ được đọc:

```java
int total = 0;
for (Order ignored : orders) {
    total++;
}
```

Tên `ignored` cho biết biến không được dùng, nhưng vẫn tạo ra một định danh mà người đọc có thể tưởng rằng nó có vai trò trong logic. Với Java 22, có thể viết:

```java
int total = 0;
for (Order _ : orders) {
    total++;
}
```

Vòng lặp vẫn duyệt từng phần tử và tăng `total` đúng một lần cho mỗi phần tử. Biến `_` thể hiện rằng giá trị của phần tử hiện tại không cần thiết.

Biến không tên vẫn được khởi tạo như biến thông thường. Biểu thức khởi tạo vẫn được đánh giá, các lời gọi phương thức và tác dụng phụ vẫn xảy ra, và ngoại lệ vẫn được ném nếu biểu thức thất bại. Điểm khác biệt là chương trình không có tên để đọc giá trị đó.

Ví dụ, lời gọi `queue.remove()` vẫn lấy và loại bỏ phần tử khỏi hàng đợi khi viết `Order _ = queue.remove();`. `_` không làm cho lời gọi bị bỏ qua và cũng không tự xử lý ngoại lệ do `remove()` có thể ném.

## 2. Những vị trí có thể khai báo biến không tên

Java 22 cho phép `_` trong một số ngữ cảnh khai báo cụ thể. Bảng dưới đây tóm tắt các vị trí thường gặp.

| Vị trí | Ví dụ | Ý nghĩa |
|---|---|---|
| Biến cục bộ trong block | `int _ = validateAndGetVersion(config);` | Đánh giá biểu thức nhưng không giữ tên để dùng kết quả. |
| Phần khởi tạo của `for` cơ bản | `for (int i = 0, _ = startTimer(); i < limit; i++)` | Chạy biểu thức khởi tạo một lần, bỏ qua giá trị trả về. |
| Enhanced `for` | `for (Order _ : orders)` | Duyệt các phần tử nhưng không đọc phần tử hiện tại. |
| Tài nguyên của try-with-resources | `try (FileLock _ = channel.lock())` | Chỉ cần vòng đời của tài nguyên để tự động đóng hoặc giải phóng. |
| Tham số `catch` | `catch (FileAlreadyExistsException _)` | Xử lý loại ngoại lệ đã biết mà không cần đọc đối tượng ngoại lệ. |
| Tham số lambda | `(sku, _) -> refreshCatalogEntry(sku)` | Lambda chỉ cần một trong các đối số. |

### Biến cục bộ và `var`

Biến không tên trong một khai báo cục bộ phải có biểu thức khởi tạo:

```java
int _ = validateAndGetVersion(config); // Hợp lệ
var _ = loadAndValidate(config);        // Hợp lệ

// int _; // Lỗi: biến không tên trong block cần initializer.
```

Khi dùng `var`, khai báo vẫn phải tuân thủ quy tắc suy luận kiểu: cần initializer và chỉ có một declarator. Không thể khai báo nhiều biến bằng `var` trong cùng một câu lệnh như `var first = ..., second = ...`.

Không nên tạo một biến không tên chỉ để thay thế một lời gọi phương thức vốn có thể đứng độc lập thành expression statement. Chẳng hạn, nếu chỉ cần gọi `refreshCache()`, hãy viết `refreshCache();`. Dùng `_` khi cấu trúc khai báo thực sự cần một biến hoặc khi cách viết đó giúp diễn đạt rõ rằng giá trị trả về được cố ý bỏ qua.

### Enhanced `for`

Đây là trường hợp dễ áp dụng nhất khi vòng lặp chỉ quan tâm đến số lần duyệt hoặc tác dụng phụ của mỗi lượt:

```java
static int countOrders(List<Order> orders) {
    int total = 0;
    for (Order _ : orders) {
        total++;
    }
    return total;
}
```

Mỗi phần tử vẫn được lấy từ `Iterable` hoặc mảng và gán vào biến không tên ở lượt tương ứng. Nếu thân vòng lặp cần đọc `order.id()`, `order.amount()` hoặc bất kỳ thuộc tính nào của phần tử, hãy dùng một tên có ý nghĩa thay cho `_`.

### Tài nguyên try-with-resources

Một số tài nguyên chỉ cần tồn tại trong một phạm vi để `close()` được gọi tự động. Ví dụ, `FileLock` được giải phóng khi khối `try` kết thúc:

```java
try (FileLock _ = channel.lock()) {
    writeIndex(channel);
}
```

Không cần đặt tên cho đối tượng khóa nếu thân khối chỉ cần bảo đảm khóa được giữ trong thời gian ghi index. Tài nguyên vẫn được khởi tạo và đóng theo quy tắc try-with-resources; nếu việc lấy khóa hoặc đóng tài nguyên phát sinh lỗi, quy tắc xử lý ngoại lệ của Java vẫn được áp dụng.

Một khai báo tài nguyên không tên vẫn phải có initializer và kiểu của tài nguyên phải triển khai `AutoCloseable`. Một resource specification có thể chứa nhiều tài nguyên không tên nếu mỗi tài nguyên có khai báo riêng.

### Tham số lambda

Khi lambda nhận nhiều đối số nhưng chỉ sử dụng một số đối số, `_` làm rõ phần nào được bỏ qua:

```java
Map<String, BigDecimal> priceBySku = loadPrices();

priceBySku.forEach((sku, _) -> refreshCatalogEntry(sku));
```

`Map.forEach` truyền cả key và value cho lambda. Đoạn mã chỉ dùng `sku`, vì vậy tham số thứ hai không cần tên. Các tham số trong ví dụ đều dùng kiểu suy luận; không trộn cú pháp khai báo kiểu tường minh với kiểu suy luận trong cùng danh sách tham số.

`_` chỉ được hỗ trợ cho tham số lambda, không phải tham số của phương thức hay constructor. Nếu cần bỏ qua tham số trong một method declaration, Java không cho viết `void process(String _)`; hãy giữ một tên có ý nghĩa hoặc thiết kế lại API nếu việc đó phù hợp.

## 3. Dùng `_` trong `catch` mà vẫn xử lý lỗi đúng cách

Tham số `catch` không tên hữu ích khi loại ngoại lệ đã nói đủ thông tin để quyết định cách xử lý. Ví dụ, khi tạo file cấu hình mặc định, file đã tồn tại có thể là trạng thái bình thường: ứng dụng nên giữ cấu hình hiện có và chỉ tạo file khi chưa có.

```java
import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

class ConfigFiles {
    private static final String DEFAULT_CONFIG = "mode=safe\n";

    static void createDefaultIfMissing(Path path) throws IOException {
        try {
            Files.writeString(
                    path,
                    DEFAULT_CONFIG,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
        } catch (FileAlreadyExistsException _) {
            // File đã tồn tại: giữ nguyên cấu hình hiện có.
        }
    }
}
```

`CREATE_NEW` yêu cầu tạo file mới và báo `FileAlreadyExistsException` nếu đường dẫn đã tồn tại. Ứng dụng xử lý riêng tình huống đã biết này bằng cách giữ file hiện tại. Những lỗi `IOException` khác vẫn truyền lên caller vì phương thức khai báo `throws IOException`.

Đây là điểm quan trọng khi refactor: `_` chỉ bỏ tên của đối tượng ngoại lệ, không bỏ nhánh xử lý. Thân `catch` vẫn phải thể hiện hành vi đúng với nghiệp vụ. Trong ví dụ trên, hành vi là giữ cấu hình hiện có; trong trường hợp khác, hành vi có thể là trả về giá trị dự phòng, thử lại theo chính sách hoặc chuyển sang một luồng xử lý khác.

Nếu cần ghi log, giữ nguyên nguyên nhân, phân biệt mã lỗi hoặc đưa ngoại lệ vào thông báo cho người dùng, hãy tiếp tục dùng một tên:

```java
catch (IOException ex) {
    logger.error("Cannot create configuration file: " + path, ex);
    throw ex;
}
```

Không đổi `catch (Exception ex)` thành `catch (Exception _)` chỉ để làm mất cảnh báo biến không dùng. Bắt một loại ngoại lệ quá rộng rồi bỏ qua có thể che giấu lỗi quyền truy cập, lỗi thiết bị lưu trữ hoặc lỗi lập trình. Chỉ dùng tham số không tên khi loại ngoại lệ đã được chọn có chủ đích và hành động xử lý không cần nội dung của đối tượng ngoại lệ.

## 4. Mẫu không tên trong record pattern

Mẫu không tên xuất hiện trong danh sách thành phần của một record pattern. Nó khớp với thành phần tương ứng nhưng không tạo biến để chương trình sử dụng.

```java
record Point(double x, double y) {}
enum Color { RED, GREEN, BLUE }
record ColoredPoint(Point point, Color color) {}

static double distanceFromOrigin(Object value) {
    if (value instanceof ColoredPoint(Point point, _)) {
        return Math.hypot(point.x(), point.y());
    }
    throw new IllegalArgumentException("Expected a ColoredPoint");
}
```

Logic chỉ cần `point` để tính khoảng cách. Thành phần `color` vẫn thuộc record và vẫn được xét trong quá trình khớp record pattern, nhưng không cần khai báo một biến như `Color color` nếu giá trị đó không được sử dụng.

Có hai cách viết khi cần bỏ tên biến nhưng vẫn muốn nêu rõ kiểu của thành phần:

```java
if (value instanceof ColoredPoint(Point point, Color _)) {
    System.out.println(point.x());
}
```

`Color _` vẫn là một type pattern: nó giữ điều kiện kiểm tra kiểu `Color` nhưng không cung cấp tên để đọc giá trị. Trong khi đó, dấu `_` đứng riêng trong danh sách thành phần là unnamed pattern, khớp với thành phần tương ứng mà không nêu kiểu hay tên.

Mẫu không tên chỉ được dùng làm thành phần của record pattern. Viết `value instanceof _` là không hợp lệ vì `_` không phải mẫu cấp cao nhất. Nếu muốn kiểm tra một giá trị thuộc một kiểu mà không cần giữ biến, dùng type pattern như `value instanceof String _` hoặc dùng phép kiểm tra kiểu thông thường khi không cần pattern matching.

Một chi tiết cần nhớ: record pattern vẫn lấy các thành phần thông qua accessor tương ứng của record. `_` bỏ việc ràng buộc giá trị vào biến, chứ không bảo đảm accessor của thành phần đó không được gọi. Nếu accessor được tùy biến và ném ngoại lệ, quá trình khớp mẫu có thể thất bại bằng `MatchException`. Record accessor nên có hành vi đơn giản, ổn định và tránh tác dụng phụ.

## 5. Kết hợp mẫu không tên với `switch`

Pattern matching for `switch` và record patterns đã trở thành tính năng chính thức trước Java 22. JEP 456 bổ sung khả năng bỏ tên biến trong các pattern này.

```java
sealed interface Employee permits Salaried, Freelancer, Intern {}

record Salaried(String name, long salary) implements Employee {}
record Freelancer(String name) implements Employee {}
record Intern(String name) implements Employee {}

static String describe(Employee employee) {
    return switch (employee) {
        case Salaried salaried -> "Salary: " + salaried.salary();
        case Freelancer _, Intern _ -> "Other employee";
    };
}
```

Hai nhánh `Freelancer` và `Intern` không cần đọc thành phần nào, vì vậy mỗi type pattern dùng `_`. Java cho phép gộp nhiều pattern vào cùng một nhãn `case` khi chúng không khai báo pattern variable. Điều này hữu ích khi nhiều loại dữ liệu có cùng hành vi xử lý.

Với record pattern, có thể lấy đúng thành phần cần dùng và bỏ các thành phần còn lại:

```java
record Order(String id, Customer customer, BigDecimal total) {}
record Customer(String name, String tier) {}

static String orderLabel(Object value) {
    return switch (value) {
        case Order(String id, _, _) -> "Order " + id;
        case null -> "No order";
        default -> "Unsupported value";
    };
}
```

Ở đây, chương trình chỉ lấy `id`; `customer` và `total` không cần biến. `case null` được viết rõ vì `switch` trên một giá trị `null` sẽ ném `NullPointerException` nếu không có nhãn xử lý `null`.

Phân biệt hai hình thức sau:

```java
case String _       -> "A string"; // Type pattern: kiểm tra kiểu String.
case Order(String id, _, _) -> id;  // Record pattern: bỏ qua hai thành phần.
```

`String _` là type pattern có pattern variable không tên. Hai dấu `_` trong `Order(...)` là unnamed patterns dành cho các thành phần record. Cả hai đều không cung cấp giá trị để tham chiếu trong thân nhánh `case`.

## 6. Cách refactor an toàn

Khi gặp biến có tên `ignored`, `unused`, `unusedValue` hoặc tên tương tự, hãy kiểm tra vì sao nó được khai báo trước khi thay bằng `_`.

1. **Xác định mục đích của khai báo.** Nếu biến chỉ tồn tại vì cú pháp cần một binding, hoặc giá trị trả về được cố ý bỏ qua, `_` có thể thể hiện ý định rõ hơn.
2. **Giữ nguyên biểu thức khởi tạo.** Không xóa lời gọi phương thức, phép lấy phần tử hoặc thao tác mở tài nguyên chỉ vì biến không được sử dụng. Các biểu thức đó có thể có tác dụng phụ hoặc ném ngoại lệ.
3. **Giữ nguyên điều kiện khớp mẫu.** Với `Color _`, điều kiện kiểm tra kiểu `Color` vẫn còn. Với `_` trong record component list, thành phần được chấp nhận mà không cần nêu kiểu hay tên.
4. **Giữ hành vi của `catch`.** Chỉ bỏ tên ngoại lệ khi thân `catch` không cần thông tin của nó. Không biến một nhánh xử lý có log, phân loại lỗi hoặc rethrow thành một nhánh rỗng.
5. **Đọc lại toàn bộ biểu thức xung quanh.** Nếu giá trị thật sự cần cho logic, giữ một tên mô tả. Nếu chỉ cần kiểm tra kiểu, dùng type pattern không tên. Nếu không cần ràng buộc thành phần record, dùng unnamed pattern.

Ví dụ, thay đổi sau là tương đương về mục đích nếu biến `ignored` thực sự không được đọc:

```java
// Trước
for (Order ignored : orders) {
    processed++;
}

// Sau
for (Order _ : orders) {
    processed++;
}
```

Ngược lại, không được đổi đoạn mã sau nếu logic cần `ex` để ghi log:

```java
catch (IOException ex) {
    logger.error("Import failed", ex);
    throw ex;
}
```

Ở đây, biến có tên là cần thiết để truyền đối tượng ngoại lệ vào logger và ném lại đúng đối tượng. Thay bằng `_` sẽ làm mất khả năng truy cập đó và khiến mã không biên dịch.

## 7. Những giới hạn và lỗi thường gặp

| Trường hợp | Kết quả |
|---|---|
| Đọc `_` như một biểu thức, ví dụ `System.out.println(_)` | Không hợp lệ: `_` không phải tên biến có thể tham chiếu. |
| Khai báo `int _;` trong block | Không hợp lệ: biến cục bộ không tên cần initializer. |
| Dùng `_` làm tên field, record component hoặc tham số method/constructor | Không hợp lệ: các vị trí này không nằm trong danh sách được hỗ trợ. |
| Viết `value instanceof _` hoặc `case _ ->` | Không hợp lệ như một pattern cấp cao nhất. Dùng type pattern có kiểu hoặc `default` tùy mục đích. |
| Dùng `catch (Exception _)` rồi bỏ qua mọi lỗi | Có thể che giấu lỗi nghiêm trọng; hãy bắt loại ngoại lệ cụ thể và xử lý theo nghiệp vụ. |
| Dùng `_` cho giá trị cần log, trả về hoặc dùng ở bước tiếp theo | Không phù hợp: hãy giữ tên mô tả. |

Ký tự `_` đã là keyword từ Java 9 nên không thể dùng như tên biến thông thường. Java 22 mở ra các vị trí khai báo đặc biệt cho unnamed variables và unnamed patterns; nó không biến `_` thành identifier có thể đọc hoặc ghi như một biến bình thường.

Không cần bật preview để dùng JEP 456. Tuy nhiên, cần phân biệt tính năng này với primitive type patterns như `case int _`: primitive types trong `instanceof` và `switch` là một hướng phát triển riêng, được đưa vào dưới dạng preview từ Java 23 và vẫn ở trạng thái preview trong Java 27. Các ví dụ của bài dùng cú pháp ổn định có trong Java 22.

## 8. Kết luận

`_` là cách thể hiện có chủ đích rằng một binding hoặc một thành phần dữ liệu không cần tên để dùng về sau. Biến không tên phù hợp với local variable, enhanced `for`, try-with-resources, `catch` và tham số lambda. Mẫu không tên giúp record pattern và pattern matching trong `switch` chỉ tập trung vào các thành phần có ý nghĩa với logic.

Khi refactor, hãy giữ nguyên việc đánh giá biểu thức, điều kiện khớp mẫu và hành vi xử lý ngoại lệ. Dùng `_` khi giá trị thực sự không cần được tham chiếu; giữ tên khi cần log, phân tích lỗi hoặc sử dụng dữ liệu. JEP 456 là tính năng chính thức từ Java 22 và vẫn là cú pháp Java hiện hành.

## Tài liệu tham khảo

- [JEP 456: Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [Oracle Java SE 22: Unnamed Variables and Patterns](https://docs.oracle.com/en/java/javase/22/language/unnamed-variables-and-patterns.html)
- [Oracle Java SE 22: Unnamed Variables and Patterns — JLS changes](https://docs.oracle.com/en/java/javase/22/docs/specs/unnamed-jls.html)
- [Oracle Java SE 27: Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
- [Oracle JDK 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html)
