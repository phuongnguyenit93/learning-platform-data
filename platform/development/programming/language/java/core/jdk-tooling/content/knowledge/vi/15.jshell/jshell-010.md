# Thử nghiệm API bằng JShell

**JShell** là môi trường tương tác REPL đi kèm JDK, cho phép nhập và chạy biểu thức, câu lệnh, biến, lớp và method Java ngay trong Terminal. Đây là cách nhanh để khám phá API, kiểm tra chữ ký method, thử giá trị đầu vào, quan sát kết quả và tái hiện lỗi nhỏ trước khi đưa code vào dự án.

Khi thử nghiệm API, hãy xem JShell như một bàn thử có trạng thái: khai báo import hoặc biến một lần, sau đó gọi nhiều method trên cùng đối tượng. Bạn có thể thử trường hợp thông thường, giá trị biên, đầu vào không hợp lệ và ngoại lệ mà không cần tạo một project hoàn chỉnh.

JShell phù hợp cho việc khám phá tương tác. Với logic cần kiểm thử tự động, chạy lặp lại trong CI hoặc kiểm tra nhiều trường hợp, hãy chuyển các ví dụ đã ổn định thành unit test bằng framework như JUnit.

## 1. Khởi động JShell

JShell có trong JDK từ Java 9. Kiểm tra phiên bản và khởi động:

```sh
jshell --version
jshell
```

Bạn sẽ thấy prompt:

```text
jshell>
```

Thử một biểu thức:

```java
jshell> 2 + 3
$1 ==> 5
```

JShell tự lưu kết quả biểu thức vào biến tạm có tên như `$1`. Số thứ tự phụ thuộc lịch sử phiên, vì vậy không nên dựa vào số này trong tài liệu hoặc script.

Có thể chọn chế độ hiển thị ngắn gọn khi khởi động:

```sh
jshell --feedback concise
```

Trong phiên đang chạy, đổi chế độ bằng:

```text
jshell> /set feedback concise
```

Xem trợ giúp và thoát:

```text
jshell> /help
jshell> /help intro
jshell> /exit
```

## 2. Quy trình thử nghiệm một API

Một quy trình đơn giản:

1. Xác định lớp hoặc interface cần khám phá và package của nó.
2. Import kiểu cần dùng hoặc gọi bằng tên đầy đủ.
3. Tạo đối tượng với dữ liệu nhỏ, dễ kiểm soát.
4. Gọi method và quan sát giá trị trả về hoặc tác động phụ.
5. Thử nhiều kiểu đối số để hiểu overload.
6. Kiểm tra trường hợp biên và đầu vào không hợp lệ.
7. Quan sát ngoại lệ và điều kiện phát sinh.
8. Ghi lại kết quả đã xác nhận rồi chuyển thành unit test nếu cần.

Ví dụ khám phá `String`:

```java
jshell> import java.util.Locale;
jshell> String message = "  Java API  ";
jshell> message.strip()
$1 ==> "Java API"

jshell> message.toUpperCase(Locale.ROOT)
$2 ==> "  JAVA API  "

jshell> message.substring(2, 6)
$3 ==> "Java"
```

`strip()` loại bỏ khoảng trắng ở hai đầu, `toUpperCase()` tạo chuỗi chữ hoa và `substring(begin, end)` lấy đoạn bắt đầu tại chỉ số `begin`, kết thúc trước chỉ số `end`. String là immutable: các method này trả về chuỗi mới, không sửa đối tượng `message` ban đầu.

## 3. Import package và dùng tên đầy đủ

Import giúp sử dụng tên lớp ngắn:

```java
jshell> import java.time.LocalDate;
jshell> import java.time.format.DateTimeFormatter;
jshell> LocalDate today = LocalDate.of(2026, 11, 10);
jshell> today.plusDays(7)
$1 ==> 2026-11-17
```

Nếu không import, có thể dùng tên đầy đủ:

```java
jshell> java.time.LocalDate.of(2026, 11, 10)
$2 ==> 2026-11-10
```

Một số package cơ bản được JShell import sẵn, nhưng nên import tường minh trong ví dụ dài để người đọc hiểu nguồn gốc kiểu dữ liệu. Xem các import hiện tại:

```text
jshell> /imports
```

Nếu hai package có lớp trùng tên, import cụ thể hoặc dùng tên đầy đủ để tránh nhầm lẫn.

## 4. Khám phá method và overload

Một API có thể có nhiều method cùng tên nhưng khác danh sách tham số. Đó là method overloading. Khi thử API, hãy kiểm tra tên, kiểu tham số, kiểu trả về và điều kiện áp dụng.

Ví dụ với `String.substring`:

```java
jshell> "OpenJDK".substring(4)
$1 ==> "JDK"

jshell> "OpenJDK".substring(0, 4)
$2 ==> "Open"
```

- `substring(int beginIndex)` lấy từ chỉ số bắt đầu đến hết chuỗi.
- `substring(int beginIndex, int endIndex)` lấy đoạn từ `beginIndex` đến trước `endIndex`.

Có thể dùng reflection để xem các method khai báo trong lớp:

```java
jshell> import java.lang.reflect.Method;
jshell> import java.util.Arrays;
jshell> Arrays.stream(String.class.getDeclaredMethods()).filter(m -> m.getName().equals("substring")).map(Method::toGenericString).sorted().forEach(System.out::println);
```

Kết quả có các chữ ký tương ứng với `substring(int)` và `substring(int, int)`. Thứ tự method reflection không được bảo đảm; `sorted()` sắp xếp văn bản kết quả để dễ đọc.

Phân biệt:

- `getMethods()` trả về method public, gồm cả method kế thừa.
- `getDeclaredMethods()` trả về method được khai báo trực tiếp trong lớp, kể cả method không public, nhưng không gồm method kế thừa.

Reflection hữu ích để quan sát API lúc chạy, nhưng không thay thế Javadoc. Nó không mô tả đầy đủ hợp đồng hành vi, thread-safety, hiệu năng hoặc các điều kiện sử dụng.

## 5. Tab completion và trợ giúp

Trong JShell, nhấn Tab để hoàn thành tên lớp, biến, method hoặc xem gợi ý tại vị trí con trỏ. Ví dụ:

```java
jshell> var text = "Java";
```

Nhập `text.` rồi nhấn Tab để xem các thành viên có thể gọi. Hoàn thành tên giúp khám phá API nhanh, nhưng không phải tài liệu đầy đủ. Để hiểu chính xác tham số, giá trị trả về, ngoại lệ và ghi chú sử dụng, hãy đọc Javadoc.

Có thể xem trợ giúp cho lệnh JShell:

```text
jshell> /help /list
jshell> /help /save
```

Lệnh JShell bắt đầu bằng dấu `/`; biểu thức, khai báo và câu lệnh Java thông thường không có dấu này.

## 6. Thử nghiệm Collection API

Collection API thường được dùng để kiểm tra cách tạo danh sách, thêm phần tử, truy vấn, lọc và biến đổi dữ liệu.

```java
jshell> import java.util.ArrayList;
jshell> import java.util.List;
jshell> var names = new ArrayList<String>();
jshell> names.add("An")
$1 ==> true

jshell> names.add("Binh")
$2 ==> true

jshell> names
names ==> [An, Binh]
```

Thử truy cập và cập nhật:

```java
jshell> names.get(0)
$3 ==> "An"

jshell> names.set(1, "Chi")
$4 ==> "Binh"

jshell> names
names ==> [An, Chi]
```

`set(index, value)` trả về phần tử cũ tại vị trí đó. `get(index)` đọc phần tử theo chỉ số bắt đầu từ 0.

Gọi `names.get(10)` phát sinh `IndexOutOfBoundsException` vì danh sách không có phần tử tại chỉ số 10.

### 6.1. List.of và tính bất biến

`List.of(...)` tạo danh sách không thể sửa đổi:

```java
jshell> var fixedNames = List.of("An", "Binh");
jshell> fixedNames
fixedNames ==> [An, Binh]
```

Nếu gọi `fixedNames.add("Chi")`, API ném `UnsupportedOperationException`. Danh sách này cũng không chấp nhận phần tử `null`. Khi thử API, cần phân biệt danh sách có thể thay đổi như `ArrayList` với danh sách không thể thay đổi như danh sách tạo bởi `List.of`.

## 7. Thử nghiệm Map API

Map lưu các cặp khóa/giá trị. Dùng `HashMap` để thử thao tác cập nhật và truy vấn:

```java
jshell> import java.util.HashMap;
jshell> var prices = new HashMap<String, Integer>();
jshell> prices.put("book", 120)
$1 ==> null

jshell> prices.put("pen", 15)
$2 ==> null

jshell> prices.get("book")
$3 ==> 120

jshell> prices.containsKey("pen")
$4 ==> true
```

Thử cập nhật cùng một khóa:

```java
jshell> prices.put("book", 130)
$5 ==> 120

jshell> prices.get("book")
$6 ==> 130
```

`put` trả về giá trị cũ nếu khóa đã tồn tại; nếu chưa có, nó trả về `null`. Khi kiểm tra API Map, cần chú ý sự khác nhau giữa khóa không tồn tại và khóa có giá trị `null` nếu loại Map cho phép null.

Thử `getOrDefault`:

```java
jshell> prices.getOrDefault("not-found", 0)
$7 ==> 0
```

Các API như `putIfAbsent`, `computeIfAbsent` và `merge` cũng có thể được thử tương tự. Hãy đọc hợp đồng của từng method trước khi dùng với logic cập nhật phức tạp.

## 8. Thử nghiệm Stream API

Stream API hỗ trợ xử lý chuỗi dữ liệu theo các bước như lọc, biến đổi và tổng hợp:

```java
jshell> import java.util.stream.Stream;
jshell> var result = Stream.of("java", "", "jshell", "api").filter(s -> !s.isBlank()).map(String::toUpperCase).toList();
jshell> result
result ==> [JAVA, JSHELL, API]
```

- `Stream.of(...)` tạo stream từ các phần tử.
- `filter(...)` giữ phần tử thỏa điều kiện.
- `map(...)` biến đổi từng phần tử.
- `toList()` thu kết quả thành danh sách không thể sửa đổi.

Thử tổng hợp số:

```java
jshell> var total = List.of(10, 20, 30).stream().mapToInt(Integer::intValue).sum();
jshell> total
total ==> 60
```

Stream thường chỉ được tiêu thụ một lần. Nếu gọi terminal operation lần thứ hai trên cùng stream đã dùng, có thể nhận `IllegalStateException`. Khi cần chạy lại pipeline, tạo stream mới từ nguồn dữ liệu.

## 9. Thử nghiệm Date and Time API

Các lớp trong `java.time` là immutable và phù hợp để thử logic ngày giờ mà không cần phụ thuộc đồng hồ hệ thống.

```java
jshell> import java.time.LocalDate;
jshell> import java.time.format.DateTimeFormatter;
jshell> var start = LocalDate.of(2026, 11, 10);
jshell> start.plusDays(5)
$1 ==> 2026-11-15

jshell> start.withDayOfMonth(1)
$2 ==> 2026-11-01
```

Định dạng ngày:

```java
jshell> var formatter = DateTimeFormatter.ofPattern("dd/MM/uuuu");
jshell> formatter.format(start)
$3 ==> "10/11/2026"
```

`uuuu` thường phù hợp hơn `yyyy` khi muốn biểu diễn năm theo lịch proleptic year, đặc biệt trong các thao tác phân tích ngày. Với định dạng giao diện thông thường, chọn pattern theo yêu cầu nghiệp vụ.

Thử trường hợp không hợp lệ:

```java
jshell> LocalDate.of(2026, 2, 30)
```

Lời gọi phát sinh `DateTimeException` vì tháng 2 năm 2026 không có ngày 30. Đây là cách kiểm tra xem API xác thực dữ liệu đầu vào như thế nào.

## 10. Thử nghiệm Optional

`Optional` biểu diễn một kết quả có thể có hoặc không có giá trị:

```java
jshell> import java.util.Optional;
jshell> var found = Optional.of("Java");
jshell> found.isPresent()
$1 ==> true

jshell> found.orElse("unknown")
$2 ==> "Java"
```

Với kết quả rỗng:

```java
jshell> var missing = Optional.<String>empty();
jshell> missing.orElse("unknown")
$3 ==> "unknown"

jshell> missing.map(String::toUpperCase)
$4 ==> Optional.empty
```

Khi thử API trả về Optional, hãy kiểm tra cả nhánh có giá trị và nhánh rỗng. Không gọi `get()` mà không kiểm tra trạng thái; nếu Optional rỗng, `get()` ném `NoSuchElementException`.

## 11. Thử nghiệm Files API với tệp tạm

NIO.2 cung cấp API thao tác đường dẫn và tệp. Có thể dùng tệp tạm để thử đọc/ghi mà không tác động đến tệp dự án hiện tại.

```java
jshell> import java.nio.file.Files;
jshell> import java.nio.file.Path;
jshell> import java.io.IOException;
jshell> import java.io.UncheckedIOException;
```

Tạo, ghi, đọc và xóa tệp tạm:

```java
jshell> try {
   ...>     Path file = Files.createTempFile("jshell-api-", ".txt");
   ...>     try {
   ...>         Files.writeString(file, "API test");
   ...>         System.out.println(Files.readString(file));
   ...>     } finally {
   ...>         Files.deleteIfExists(file);
   ...>     }
   ...> } catch (IOException e) {
   ...>     throw new UncheckedIOException(e);
   ...> }
API test
```

Ví dụ sử dụng `Files.createTempFile`, `writeString`, `readString` và `deleteIfExists`. Khối `finally` bảo đảm cố gắng xóa tệp ngay cả khi thao tác đọc/ghi gặp lỗi. Ngoại lệ I/O được chuyển thành `UncheckedIOException` để hiển thị lỗi trong phiên thử nghiệm.

Khi thử API làm việc với tài nguyên, hãy chú ý vòng đời tài nguyên, quyền truy cập và dọn dẹp dữ liệu tạm. Với stream hoặc reader/writer, dùng try-with-resources để đóng tài nguyên đúng cách.

## 12. Thử nghiệm HTTP Client mà không gửi request

Java 11 trở lên có HTTP Client trong module `java.net.http`. Bạn có thể thử cách xây dựng request trước mà không thực hiện kết nối mạng.

```java
jshell> import java.net.URI;
jshell> import java.net.http.HttpRequest;
jshell> var request = HttpRequest.newBuilder(URI.create("https://api.example.test/items")).header("Accept", "application/json").GET().build();
jshell> request.method()
$1 ==> "GET"

jshell> request.uri()
$2 ==> https://api.example.test/items
```

Ví dụ kiểm tra cách tạo URI, thêm header, chọn HTTP method và giá trị được lưu trong request. Tên miền `api.example.test` là địa chỉ minh họa; đoạn code chỉ tạo đối tượng request, không gửi dữ liệu ra mạng. Request chỉ được gửi khi gọi API như `HttpClient.send(...)` hoặc `sendAsync(...)`.

Khi cần gửi request thật, hãy dùng endpoint được phép truy cập, đặt timeout, xử lý status code và lỗi mạng. Không gửi dữ liệu bí mật hoặc dữ liệu cá nhân đến endpoint thử nghiệm không đáng tin cậy.

## 13. Kiểm tra ngoại lệ và điều kiện biên

API không chỉ được hiểu qua kết quả thành công. Hãy chủ động thử các đầu vào có thể thất bại.

Ví dụ với `Integer.parseInt`:

```java
jshell> Integer.parseInt("123")
$1 ==> 123

jshell> try {
   ...>     Integer.parseInt("12x");
   ...> } catch (NumberFormatException e) {
   ...>     System.out.println(e.getClass().getSimpleName());
   ...> }
NumberFormatException
```

Một checklist thử nghiệm:

| Nhóm kiểm tra | Ví dụ | Điều cần quan sát |
|---|---|---|
| Giá trị thông thường | Chuỗi hợp lệ, số dương | Kết quả đúng theo hợp đồng |
| Giá trị rỗng | Chuỗi rỗng, collection rỗng | API trả kết quả rỗng hay ném lỗi |
| Giá trị biên | 0, số âm, chỉ số cuối | Quy tắc biên có đúng mong đợi |
| Null | Truyền `null` khi API cho phép hoặc từ chối | NPE hay hành vi được tài liệu quy định |
| Kiểu không hợp lệ | Chuỗi không parse được | Loại exception và thời điểm phát sinh |
| Tác động phụ | Thêm/xóa phần tử, ghi tệp | Trạng thái trước và sau lời gọi |
| Tính bất biến | Gọi mutator trên collection immutable | API có ném UnsupportedOperationException |
| Tài nguyên | Đóng stream, xóa tệp tạm | Tài nguyên có được giải phóng |

Không nên dựa vào một lần gọi thành công để kết luận API phù hợp cho mọi trường hợp. Hãy đối chiếu kết quả với Javadoc, nhất là khi method có thể ném checked exception, thay đổi trạng thái hoặc phụ thuộc môi trường.

## 14. Tạo helper để kiểm tra kết quả nhanh

Có thể định nghĩa một method kiểm tra trong JShell để giảm thao tác lặp:

```java
jshell> import java.util.Objects;
jshell> void checkEquals(Object expected, Object actual) {
   ...>     if (!Objects.equals(expected, actual)) {
   ...>         throw new AssertionError("Expected " + expected + " but got " + actual);
   ...>     }
   ...> }
```

Thử API:

```java
jshell> checkEquals("JAVA", "java".toUpperCase(Locale.ROOT));
```

Nếu kết quả đúng, method không in gì và phiên tiếp tục bình thường. Nếu khác, nó ném `AssertionError` cùng thông tin expected/actual.

Helper này chỉ là tiện ích khám phá thủ công. Nó không có khả năng tổ chức test, setup/teardown, báo cáo nhiều trường hợp hoặc chạy tự động như JUnit. Với kiểm thử chính thức, hãy chuyển các trường hợp đã xác nhận thành test riêng biệt.

## 15. Thử API từ thư viện bên thứ ba

Nếu API nằm trong JAR bên ngoài, hãy cung cấp JAR cho JShell khi khởi động:

```sh
jshell --class-path "lib/example-library.jar"
```

Sau đó import lớp của thư viện và thử gọi method:

```java
jshell> import com.example.library.Client;
jshell> var client = new Client();
```

Tên package, lớp và constructor ở trên chỉ minh họa; thay bằng API thực tế của thư viện đang dùng.

Nếu thư viện có dependency khác, cần đưa cả dependency cần thiết vào classpath. Ký tự phân tách nhiều mục classpath:

| Hệ điều hành | Ký tự phân tách |
|---|---|
| Windows | `;` |
| Linux/macOS | `:` |

Ví dụ trên Linux/macOS:

```sh
jshell --class-path "lib/client.jar:lib/common.jar"
```

Ví dụ trên Windows PowerShell:

```powershell
jshell --class-path "lib/client.jar;lib/common.jar"
```

Với thư viện modular, có thể cần module path và tùy chọn module phù hợp thay vì chỉ classpath. Xem `jshell --help` để biết các tùy chọn của JDK đang dùng.

Khi thử thư viện bên thứ ba, hãy kiểm tra phiên bản JAR, dependency bắc cầu, yêu cầu Java tối thiểu và license. JShell chỉ giúp gọi API; nó không tự giải quyết dependency hoặc bảo đảm các phiên bản thư viện tương thích.

## 16. Quản lý snippet trong phiên

Mỗi khai báo hoặc câu lệnh được JShell quản lý như một snippet. Các lệnh hữu ích:

| Lệnh | Công dụng |
|---|---|
| `/list` | Liệt kê snippet trong lịch sử phiên |
| `/list -all` | Hiển thị cả snippet đã bị loại bỏ |
| `/vars` | Liệt kê biến đã khai báo |
| `/methods` | Liệt kê method đang có |
| `/types` | Liệt kê kiểu đã khai báo |
| `/imports` | Liệt kê import hiện tại |
| `/drop <id>` | Loại bỏ snippet theo ID |
| `/reset` | Reset trạng thái JShell |
| `/save <file>` | Lưu snippet vào tệp |
| `/open <file>` | Nạp và thực thi snippet từ tệp |
| `/exit` | Thoát JShell |

Ví dụ:

```text
jshell> /methods
jshell> /vars
jshell> /list
```

Nếu cần loại một khai báo, tìm ID bằng `/list` rồi dùng `/drop <id>`, thay `<id>` bằng ID thực tế. `/reset` xóa trạng thái phiên, bao gồm biến, method, lớp và import đã khai báo; hãy dùng khi muốn bắt đầu lại.

Lưu các snippet đã thử và mở lại trong phiên sau:

```text
jshell> /save api-experiments.jsh
jshell> /open api-experiments.jsh
```

Tệp lưu có thể chứa cả biểu thức và khai báo. Trước khi chia sẻ, hãy xem lại tệp để bảo đảm không có dữ liệu nhạy cảm hoặc lệnh không mong muốn.

## 17. Từ khám phá API đến unit test

JShell giúp tìm hiểu nhanh, nhưng kết quả khám phá cần được chuyển thành test có thể lặp lại nếu API là một phần quan trọng của ứng dụng.

Ví dụ, sau khi xác nhận `String.strip()` loại bỏ khoảng trắng ở hai đầu, có thể viết unit test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class StringApiTest {
    @Test
    void stripRemovesLeadingAndTrailingWhitespace() {
        assertEquals("Java", "  Java  ".strip());
    }
}
```

Đây là ví dụ dùng JUnit Jupiter; cần cấu hình dependency JUnit trong build tool để chạy. JShell không tự cung cấp framework test hoặc runner cho annotation `@Test`.

Nên chuyển các trường hợp sau thành test tự động: hành vi cần được bảo đảm qua nhiều lần build; giá trị biên và ngoại lệ quan trọng; tương thích với phiên bản thư viện cụ thể; hành vi có thể thay đổi khi nâng JDK hoặc dependency; logic liên quan dữ liệu, bảo mật, thời gian hoặc concurrency.

## 18. Lỗi thường gặp khi thử nghiệm API

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `cannot find symbol` | Chưa import lớp, sai tên method hoặc thiếu dependency | Kiểm tra package, import và classpath |
| `package ... does not exist` | JAR không có trong classpath hoặc tên package sai | Thêm đúng JAR và kiểm tra nội dung thư viện |
| `method ... cannot be applied to given types` | Kiểu hoặc số lượng đối số không phù hợp | Xem chữ ký method và thử kiểu đối số đúng |
| Lời gọi overload bị mơ hồ | Có nhiều overload cùng phù hợp | Khai báo kiểu biến rõ ràng hoặc ép kiểu có chủ đích |
| `NullPointerException` | API không chấp nhận null hoặc code dùng giá trị null | Kiểm tra hợp đồng và xác thực đầu vào |
| `IndexOutOfBoundsException` | Chỉ số ngoài phạm vi collection/string | Kiểm tra size và quy tắc chỉ số bắt đầu từ 0 |
| `UnsupportedOperationException` | Gọi thao tác thay đổi trên collection không thể sửa đổi | Dùng implementation mutable nếu cần thay đổi |
| `NoSuchMethodError` | Runtime nạp phiên bản thư viện khác với phiên bản compile | Kiểm tra dependency tree và classpath thực tế |
| JShell không tìm thấy lớp của JAR | Thiếu JAR hoặc dependency bắc cầu | Bổ sung dependency vào classpath/module path |
| Kết quả khác giữa hai lần thử | Dữ liệu, locale, timezone hoặc trạng thái phiên khác nhau | Dùng đầu vào cố định và đặt cấu hình môi trường rõ ràng |
| Snippet lỗi sau khi thay đổi khai báo | Snippet phụ thuộc vào một khai báo đã bị thay thế hoặc drop | Dùng `/list`, `/methods` và khai báo lại dependency cần thiết |

Khi gặp lỗi, hãy tách lỗi biên dịch snippet khỏi exception lúc chạy. Lỗi biên dịch thường liên quan tên lớp, import, kiểu tham số hoặc chữ ký method. Exception lúc chạy xảy ra sau khi lời gọi đã được biên dịch và bắt nguồn từ dữ liệu, trạng thái hoặc điều kiện thực thi.

## 19. Nguyên tắc thử nghiệm API an toàn và có thể lặp lại

- Dùng dữ liệu giả lập hoặc dữ liệu nhỏ, không dùng dữ liệu production nhạy cảm.
- Bắt đầu với API không có side effect trước khi thử thao tác ghi, xóa hoặc gửi request.
- Với API mạng, chỉ gửi request tới endpoint được phép và hiểu rõ dữ liệu sẽ truyền đi.
- Với file/database, dùng tài nguyên thử nghiệm riêng và dọn dẹp sau khi thử.
- Đặt timeout khi thử tác vụ có thể chờ mạng hoặc I/O.
- Kiểm tra ngoại lệ và đóng tài nguyên đúng cách.
- Ghi lại JDK, phiên bản thư viện, classpath và đầu vào khi kết quả phụ thuộc môi trường.
- Không coi một kết quả REPL là bằng chứng đầy đủ cho hiệu năng, thread-safety hoặc tính ổn định.
- Chuyển những kiểm tra quan trọng thành unit/integration test trong dự án.

## 20. Checklist

- [ ] Đã khởi động JShell bằng JDK tương thích.
- [ ] Đã import đúng package hoặc dùng tên đầy đủ.
- [ ] Đã tạo đối tượng với dữ liệu thử có thể kiểm soát.
- [ ] Đã gọi method và xác định kiểu trả về.
- [ ] Đã kiểm tra overload và chữ ký khi cần.
- [ ] Đã thử trường hợp thông thường, rỗng, biên và không hợp lệ.
- [ ] Đã quan sát ngoại lệ và tác động phụ.
- [ ] Đã kiểm tra mutability và vòng đời tài nguyên.
- [ ] Đã thêm dependency đúng classpath/module path nếu dùng thư viện ngoài.
- [ ] Đã dùng `/list`, `/vars`, `/methods` hoặc `/imports` để kiểm tra trạng thái phiên.
- [ ] Đã lưu snippet nếu cần tái sử dụng.
- [ ] Đã chuyển hành vi quan trọng thành unit test có thể chạy tự động.

JShell giúp biến việc đọc API thành một quá trình thử nghiệm trực tiếp: tạo dữ liệu, gọi method, quan sát kết quả và kiểm tra lỗi ngay tại prompt. Khi kết hợp khám phá tương tác với Javadoc và unit test, bạn có thể hiểu hợp đồng API nhanh hơn và đưa các kết quả đã xác nhận vào ứng dụng Java một cách có kiểm soát.