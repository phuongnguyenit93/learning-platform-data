# Khám phá biểu thức và API bằng JShell

JShell là công cụ tương tác đi kèm JDK, cho phép nhập từng đoạn mã Java, biên dịch và thực thi ngay trong một phiên làm việc. Thay vì tạo lớp chứa phương thức `main`, biên dịch cả chương trình rồi chạy lại sau mỗi thay đổi, bạn có thể thử một biểu thức, gọi một phương thức API, xem kết quả và điều chỉnh ngay tại dấu nhắc.

Với Java 27, JShell hữu ích khi học cú pháp, kiểm tra cách một API hoạt động, thử nhanh một thuật toán nhỏ hoặc tạo mẫu cho một đoạn mã trước khi đưa vào dự án. Công cụ này phù hợp với việc khám phá và thử nghiệm có kiểm soát; việc xác nhận hành vi của ứng dụng vẫn cần được thực hiện trong dự án thật bằng build, kiểm thử và các cấu hình chạy tương ứng.

## 1. Chuẩn bị và khởi chạy JShell

JShell được phân phối cùng JDK. Hãy cài JDK 27 và bảo đảm thư mục `bin` của JDK nằm trong `PATH`, sau đó kiểm tra phiên bản:

```shell
java --version
jshell --version
```

Nếu lệnh `jshell` không được nhận diện, hãy kiểm tra lại JDK đang được cài đặt và biến môi trường `PATH`. Chỉ cài một runtime Java riêng sẽ không cung cấp đầy đủ các công cụ phát triển của JDK.

Khởi chạy một phiên tương tác:

```shell
jshell
```

Bạn sẽ thấy dấu nhắc `jshell>`. Nhập một biểu thức Java để thử ngay:

```text
jshell> 2 + 3
$1 ==> 5

jshell> "Java " + 27
$2 ==> "Java 27"

jshell> Math.max(12, 19)
$3 ==> 19
```

Khi một biểu thức tạo ra giá trị mà bạn không gán vào biến có tên, JShell lưu kết quả trong một biến tạm có tên như `$1`, `$2`. Số thứ tự cụ thể phụ thuộc vào các snippet đã chạy trong phiên. Bạn có thể sử dụng kết quả đó trong biểu thức tiếp theo, nhưng với đoạn thử nghiệm dài hơn nên đặt tên biến rõ ràng.

Để xem phần giới thiệu và danh sách lệnh ngay trong phiên:

```text
jshell> /help intro
jshell> /help
```

Kết thúc phiên bằng:

```text
jshell> /exit
```

JShell phân biệt hai loại đầu vào:

- **Snippet** là mã Java như biểu thức, câu lệnh, khai báo biến, phương thức, lớp và câu lệnh import.
- **Lệnh JShell** bắt đầu bằng dấu gạch chéo `/`, dùng để quản lý phiên hoặc xem thông tin. Ví dụ: `/vars`, `/list`, `/reset`.

Khi một snippet chưa hoàn chỉnh, JShell chuyển sang dấu nhắc tiếp dòng `...>`. Hãy hoàn tất khối mã, chẳng hạn đóng dấu ngoặc nhọn của phương thức hoặc lớp, rồi JShell mới đánh giá snippet.

## 2. Thử biểu thức, biến và câu lệnh

Biểu thức là cách nhanh nhất để kiểm tra một phép tính hoặc một lời gọi API. Bạn có thể thử các phép toán, phép so sánh, toán tử logic, thao tác chuỗi và lời gọi phương thức:

```text
jshell> 8 * (12 + 3)
$1 ==> 120

jshell> "  Java 27 và JShell  ".strip()
$2 ==> "Java 27 và JShell"

jshell> "Java".toLowerCase()
$3 ==> "java"
```

Một snippet có thể khai báo biến rồi dùng biến đó ở các snippet tiếp theo:

```text
jshell> int quantity = 3;
quantity ==> 3

jshell> double unitPrice = 125_000;
unitPrice ==> 125000.0

jshell> quantity * unitPrice
$1 ==> 375000.0
```

JShell cũng hỗ trợ `var` để suy luận kiểu từ giá trị khởi tạo:

```java
var language = "Java";
var numbers = java.util.List.of(10, 20, 30);
numbers.stream().mapToInt(Integer::intValue).sum();
```

Kết quả của biểu thức cuối là tổng các phần tử. Khi cần kiểm tra kiểu, bạn có thể gọi `getClass()` trên một đối tượng:

```java
language.getClass().getName();
numbers.getClass().getName();
```

Tên lớp cụ thể của một đối tượng được tạo bởi thư viện có thể là chi tiết triển khai. Khi viết ứng dụng, hãy dựa vào kiểu và hợp đồng API được công bố, không phụ thuộc vào tên lớp nội bộ mà phép kiểm tra trên tình cờ hiển thị.

JShell chấp nhận câu lệnh, khai báo và biểu thức Java. Dấu chấm phẩy kết thúc snippet thường được JShell tự bổ sung khi xác định được đầu vào đã hoàn chỉnh, nhưng nên viết dấu chấm phẩy trong ví dụ và đoạn mã được lưu để mã dễ đọc và nhất quán với mã nguồn dự án.

## 3. Khai báo phương thức và kiểu dữ liệu để thử nghiệm

Bạn có thể khai báo một phương thức ở cấp cao nhất mà không cần tạo lớp tiện ích:

```java
int calculateTotal(int unitPrice, int quantity) {
    return unitPrice * quantity;
}

calculateTotal(125_000, 3);
```

JShell ghi nhận phương thức sau khi khai báo thành công. Bạn có thể gọi lại phương thức nhiều lần với các đầu vào khác nhau:

```java
calculateTotal(80_000, 2);
calculateTotal(150_000, 4);
```

Điều này hữu ích khi muốn thử nhanh các trường hợp biên, chẳng hạn số lượng bằng 0 hoặc một giá trị lớn. Nếu muốn kiểm tra điều kiện đầu vào, hãy thêm kiểm tra ngay trong phương thức:

```java
int calculateTotalChecked(int unitPrice, int quantity) {
    if (unitPrice < 0 || quantity < 0) {
        throw new IllegalArgumentException("Giá và số lượng phải không âm");
    }
    return Math.multiplyExact(unitPrice, quantity);
}
```

JShell cũng cho phép khai báo lớp và record. Ví dụ sau tạo một kiểu dữ liệu nhỏ để khám phá cách truy cập thành phần:

```java
record Product(String name, int price) {}

var product = new Product("Keyboard", 1_200_000);
product.name();
product.price();
```

Với record, các thành phần được truy cập bằng accessor cùng tên, chẳng hạn `name()` và `price()`. Đây là cách thuận tiện để thử API của một kiểu dữ liệu bất biến mà không cần dựng cả dự án.

Bạn có thể xem các khai báo đang tồn tại bằng những lệnh sau:

```text
jshell> /vars
jshell> /methods
jshell> /types
jshell> /imports
```

Các lệnh này giúp xác định biến, phương thức, kiểu và import đã được tạo trong phiên. Dùng `/list` để xem các snippet đã nhập; dùng `/list -all` khi cần xem cả snippet bị thay thế, bị loại bỏ hoặc được nạp lúc khởi động.

## 4. Khám phá Java API bằng import và Tab completion

Một cách trực tiếp để tìm hiểu API là import kiểu cần dùng, tạo một giá trị và gọi từng phương thức. Ví dụ với API ngày giờ hiện hành trong `java.time`:

```java
import java.time.LocalDate;

var today = LocalDate.now();
today.plusDays(7);
today.getDayOfWeek();
today.isAfter(LocalDate.of(2020, 1, 1));
```

Bạn có thể thay đổi biểu thức để xem kết quả của từng phương thức, so sánh các giá trị hoặc kết hợp chúng thành một biểu thức mới. Thử nghiệm như vậy giúp hiểu kiểu trả về và cách các API phối hợp với nhau trước khi viết mã hoàn chỉnh.

JShell hỗ trợ hoàn thành đầu vào bằng phím **Tab**. Hãy nhập tên biến hoặc kiểu rồi dấu chấm, sau đó nhấn Tab để xem những thành viên có thể truy cập. Ví dụ, sau khi tạo biến `today`, nhập `today.` rồi nhấn Tab. Tính năng hoàn thành cũng áp dụng cho tên lệnh, tùy chọn lệnh và tên file khi dùng `/open`.

Để xem các import đã được nạp, dùng:

```text
jshell> /imports
```

Theo mặc định, JShell nạp một startup script với một số import thường dùng, bao gồm các package như `java.util`, `java.util.concurrent`, `java.util.function` và `java.util.stream`. Package `java.lang` luôn được ngôn ngữ Java tự động import. Dùng `/list -start` để xem các snippet khởi động và `/imports` để kiểm tra import đang có trong phiên. Khi chia sẻ một ví dụ hoặc lưu script cần chạy ổn định trong nhiều môi trường, hãy khai báo rõ các import mà ví dụ phụ thuộc vào.

### Xem chữ ký phương thức bằng Reflection

Tab completion hữu ích khi khám phá tương tác. Khi cần lọc danh sách phương thức theo tên hoặc xem chữ ký, bạn có thể sử dụng Reflection API:

```java
import java.util.Arrays;

Arrays.stream(String.class.getMethods())
    .filter(method -> method.getName().startsWith("strip"))
    .map(method -> method.toGenericString())
    .sorted()
    .toList();
```

Đoạn mã trên lấy các phương thức public có tên bắt đầu bằng `strip` của `String`, chuyển chúng thành chuỗi chữ ký, sắp xếp rồi hiển thị dưới dạng danh sách. Đây là cách kiểm tra nhanh tên phương thức, kiểu trả về và tham số mà không phải đoán từ tên API.

Hai phương thức Reflection thường gặp có phạm vi khác nhau:

- `getMethods()` trả về các phương thức public của kiểu và những phương thức public được kế thừa.
- `getDeclaredMethods()` trả về các phương thức được khai báo trực tiếp trong kiểu, bao gồm cả phương thức không public.

Nếu mục tiêu là tìm hiểu API công khai mà mã ứng dụng có thể gọi, hãy bắt đầu với `getMethods()`. Reflection hiển thị thông tin cấu trúc tại runtime; nó không thay thế tài liệu giải thích ý nghĩa, điều kiện sử dụng, ngoại lệ và bảo đảm hành vi của API.

### Tra cứu tài liệu API chính thức

Kết hợp JShell với Java API Specification của đúng phiên bản JDK. Khi tìm thấy một lớp hoặc phương thức cần dùng, hãy mở tài liệu Javadoc để đọc mô tả, tham số, giá trị trả về, ngoại lệ và ghi chú tương thích. Có thể dùng tên kiểu và package để xác định đúng trang tài liệu, ví dụ `java.time.LocalDate`, `java.util.List` hoặc `java.lang.String`.

JShell giúp trả lời câu hỏi “đoạn mã này chạy ra sao với dữ liệu thử nghiệm?”, còn Javadoc giúp trả lời “API cam kết hành vi gì và được dùng như thế nào?”. Nên dùng cả hai trước khi quyết định đưa một lời gọi API vào mã nguồn.

## 5. Làm việc với collection và Stream API

Collection và Stream là nhóm API thích hợp để thực hành biểu thức, lambda và tham chiếu phương thức. Ví dụ, tạo một danh sách và lọc các phần tử theo điều kiện:

```java
import java.util.List;

var scores = List.of(6, 8, 9, 5, 10);

scores.stream()
    .filter(score -> score >= 8)
    .toList();
```

Bạn có thể chuyển đổi từng phần tử hoặc tính toán trên luồng:

```java
scores.stream()
    .mapToInt(Integer::intValue)
    .average()
    .orElse(0.0);
```

Các biểu thức này cho phép thử từng bước: thay điều kiện trong `filter`, đổi phép biến đổi trong `map`, hoặc kiểm tra kiểu kết quả của thao tác kết thúc. `Stream.toList()` trả về danh sách không thể sửa đổi; nếu cần một collection có thể thay đổi, hãy chọn cách thu thập phù hợp với yêu cầu đó thay vì giả định mọi kết quả stream đều có thể thêm hoặc xóa phần tử.

Bạn cũng có thể khám phá API của một đối tượng theo từng bước:

```java
var selectedScores = scores.stream().filter(score -> score >= 8).toList();
selectedScores.size();
selectedScores.contains(10);
selectedScores.get(0);
```

Cách làm này giúp kiểm tra cả giá trị trả về lẫn những phương thức có sẵn trên kiểu kết quả.

## 6. Thực hành: tạo và khám phá một API nhỏ

Bài thực hành sau kết hợp record, collection, Stream và Reflection. Nhập từng đoạn theo thứ tự trong cùng một phiên JShell.

**Bước 1: Khai báo kiểu dữ liệu**

```java
import java.util.List;
import java.util.Arrays;

record Task(String title, int estimateMinutes, boolean done) {}
```

**Bước 2: Tạo dữ liệu thử nghiệm**

```java
var tasks = List.of(
    new Task("Read API documentation", 30, false),
    new Task("Try JShell expressions", 20, true),
    new Task("Write unit tests", 45, false)
);
```

**Bước 3: Lọc các công việc chưa hoàn thành**

```java
var pendingTasks = tasks.stream()
    .filter(task -> !task.done())
    .toList();

pendingTasks;
```

**Bước 4: Tính tổng thời gian ước lượng**

```java
var remainingMinutes = pendingTasks.stream()
    .mapToInt(Task::estimateMinutes)
    .sum();

remainingMinutes;
```

Kết quả là `75`, tương ứng với 30 + 45 phút của hai công việc chưa hoàn thành.

**Bước 5: Khám phá cấu trúc của record**

```java
Arrays.stream(Task.class.getRecordComponents())
    .map(component ->
        component.getName() + ": " + component.getType().getSimpleName())
    .toList();
```

Kết quả cho biết tên và kiểu của từng thành phần record. Hãy thử thay đổi kiểu dữ liệu, thêm một thành phần hoặc thay điều kiện lọc rồi quan sát ảnh hưởng đến các snippet phụ thuộc.

**Bước 6: Kiểm tra các phương thức của kiểu**

```java
Arrays.stream(Task.class.getMethods())
    .filter(method -> method.getDeclaringClass() == Task.class)
    .map(method -> method.toGenericString())
    .sorted()
    .toList();
```

Bạn sẽ thấy các accessor do record cung cấp cùng những phương thức được khai báo trên record. Khi cần hiểu sâu hơn về một phương thức, hãy đối chiếu chữ ký này với tài liệu Java API tương ứng.

## 7. Sử dụng thư viện và lớp của dự án

JShell có thể truy cập các lớp đã biên dịch và thư viện JAR thông qua class path. Ví dụ, nếu dự án đã tạo lớp trong thư mục `build/classes/java/main` và có thư viện trong thư mục `libs`, có thể khởi chạy JShell với class path:

**Windows:**

```powershell
jshell --class-path "build/classes/java/main;libs/example.jar"
```

**Linux hoặc macOS:**

```shell
jshell --class-path "build/classes/java/main:libs/example.jar"
```

Sau khi khởi chạy, import package của lớp cần thử như khi viết mã Java:

```java
import com.example.service.PriceCalculator;
var calculator = new PriceCalculator();
```

Đường dẫn class path phải trỏ đến thư mục chứa các file class đã biên dịch hoặc đến file JAR có các package cần truy cập. Mã nằm trong unnamed package (không khai báo package) không thể được truy cập từ JShell; hãy tổ chức lớp trong package có tên để dùng từ công cụ này.

Có thể thay đổi class path trong một phiên bằng lệnh `/env`:

```text
jshell> /env --class-path "build/classes/java/main;libs/example.jar"
jshell> /env
```

Lệnh `/env` hiển thị cấu hình môi trường hiện tại. Khi thay đổi tùy chọn môi trường, JShell thiết lập lại trạng thái thực thi và nạp lại các snippet đang hoạt động. Vì vậy, hãy lưu những snippet cần giữ trước khi thay đổi môi trường; các trạng thái runtime được tạo thủ công trong phiên không nên được xem là dữ liệu bền vững.

Với ứng dụng dạng module, có thể thiết lập module path và chỉ định module cần resolve:

```shell
jshell --module-path mods --add-modules com.example.app
```

Tên module phải khớp với module thực tế. Trong JShell, dùng `/env` để xem cấu hình hoặc `/help context` để tra cứu hướng dẫn tùy chọn môi trường.

## 8. Quản lý, lưu và nạp lại snippet

Một phiên JShell thường chứa nhiều snippet. Các lệnh sau giúp theo dõi và quản lý chúng:

| Lệnh | Công dụng |
|---|---|
| `/vars` | Liệt kê các biến đang hoạt động và giá trị của chúng |
| `/methods` | Liệt kê các phương thức đã khai báo trong phiên |
| `/types` | Liệt kê các kiểu đã khai báo |
| `/imports` | Liệt kê các import hiện tại |
| `/list` | Liệt kê các snippet đang hoạt động |
| `/list -all` | Liệt kê cả snippet khởi động, lỗi, bị thay thế hoặc bị loại bỏ |
| `/drop <id>` | Loại bỏ snippet theo ID |
| `/edit` | Mở trình soạn thảo để sửa các snippet |
| `/save <file>` | Lưu các snippet vào file |
| `/open <file>` | Nạp snippet từ file vào phiên hiện tại |
| `/env` | Xem cấu hình môi trường của phiên |
| `/reset` | Xóa các snippet đã nhập và khởi động lại phiên |
| `/exit` | Thoát JShell |

Ví dụ lưu các đoạn mã đã thử:

```text
jshell> /save api-exploration.jsh
```

Ở một phiên khác, nạp lại file bằng:

```text
jshell> /open api-exploration.jsh
```

File script có thể chứa các snippet Java và lệnh JShell. Bạn cũng có thể truyền file khi khởi động công cụ. Với những ví dụ cần chia sẻ, hãy lưu các import và khai báo phụ thuộc cùng với phần biểu thức để người khác có thể tái hiện kết quả.

Khi muốn xem thông tin chi tiết hơn sau mỗi lần nhập, khởi chạy với chế độ verbose:

```shell
jshell -v
```

Hoặc đổi chế độ phản hồi ngay trong phiên:

```text
jshell> /set feedback verbose
```

Nếu cần bắt đầu lại từ đầu, dùng `/reset`. Lệnh này loại bỏ các snippet đã nhập và chạy lại startup script; hãy lưu nội dung cần giữ trước khi reset.

## 9. Xử lý lỗi trong quá trình khám phá

JShell hiển thị lỗi biên dịch khi snippet không hợp lệ và hiển thị ngoại lệ khi mã đã biên dịch nhưng gặp lỗi lúc chạy. Hai loại lỗi này giúp xác định vấn đề ở cú pháp, kiểu dữ liệu, tham số hoặc dữ liệu đầu vào.

Ví dụ, lời gọi sau phát sinh `NumberFormatException` vì chuỗi không biểu diễn một số nguyên hợp lệ:

```java
Integer.parseInt("Java");
```

Có thể thử cách xử lý ngoại lệ ngay trong phiên:

```java
try {
    Integer.parseInt("Java");
} catch (NumberFormatException exception) {
    System.out.println(exception.getMessage());
}
```

Nếu JShell chuyển sang dấu nhắc `...>`, đầu vào hiện tại vẫn chưa hoàn chỉnh. Kiểm tra dấu ngoặc tròn, ngoặc nhọn và dấu ngoặc kép trước khi nhập tiếp. Nếu một biểu thức phụ thuộc vào biến hoặc kiểu chưa được khai báo, hãy tạo snippet khai báo trước rồi thực hiện lại biểu thức.

Một số giới hạn cần ghi nhớ:

- JShell đánh giá snippet theo JDK đang chạy. Hãy xác nhận `jshell --version` nếu kết quả khác với môi trường dự án.
- Thư viện bên ngoài cần có trên class path hoặc module path; JShell không tự suy ra toàn bộ dependency và cấu hình build của dự án.
- `/env` có thể thiết lập lại trạng thái thực thi khi thay đổi môi trường. Lưu snippet trước khi đổi cấu hình.
- Kết quả thử nghiệm trong REPL không thay thế kiểm thử tự động, kiểm tra tích hợp, đánh giá hiệu năng hoặc xác minh hành vi trong cấu hình triển khai thật.
- Khi xem thông tin bằng Reflection, hãy ưu tiên API công khai và tài liệu Javadoc; không dựa vào lớp triển khai nội bộ của thư viện.

## 10. Quy trình khám phá API đề xuất

Khi tiếp cận một API chưa quen thuộc, có thể thực hiện theo trình tự sau:

1. Xác định đúng JDK và khởi chạy JShell bằng phiên bản đó.
2. Import lớp hoặc package cần tìm hiểu.
3. Tạo một giá trị nhỏ bằng constructor hoặc factory method được tài liệu mô tả.
4. Gọi từng phương thức với dữ liệu dễ kiểm tra; quan sát kiểu và giá trị trả về.
5. Dùng Tab completion để khám phá thành viên có thể truy cập; dùng `/vars`, `/methods`, `/types` để xem trạng thái phiên.
6. Khi cần chữ ký phương thức, dùng Reflection có chọn lọc và đối chiếu với Javadoc của JDK 27.
7. Lưu các snippet có ích bằng `/save`, sau đó chuyển phần mã đã ổn định vào dự án và viết kiểm thử phù hợp.

## Tài liệu tham khảo

- [Java Shell User’s Guide — Release 27](https://docs.oracle.com/en/java/javase/27/jshell/index.html): hướng dẫn chính thức về JShell.
- [JShell Commands](https://docs.oracle.com/en/java/javase/27/jshell/commands.html): lệnh quản lý phiên, Tab completion và cách xem snippet.
- [JShell External Code](https://docs.oracle.com/en/java/javase/27/jshell/external-code.html): cấu hình class path và module path để truy cập mã bên ngoài.
- [Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/): tài liệu Javadoc chính thức cho API Java SE và JDK.
- [The jshell Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jshell.html): cú pháp khởi chạy và các tùy chọn của công cụ.
