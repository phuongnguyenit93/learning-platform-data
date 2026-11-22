# JShell là gì?

**JShell** là công cụ tương tác dòng lệnh của JDK, hoạt động theo mô hình REPL (*Read–Eval–Print Loop*): đọc một đoạn mã Java, đánh giá đoạn mã đó, hiển thị kết quả rồi chờ lệnh tiếp theo. JShell cho phép thử biểu thức, câu lệnh, khai báo biến, method và class ngay lập tức mà không cần tạo một dự án hoàn chỉnh hoặc viết phương thức `main` cho mỗi lần thử.

JShell được giới thiệu từ Java 9. Đây là công cụ phù hợp để học cú pháp Java, khám phá API, thử thuật toán nhỏ và kiểm tra nhanh một ý tưởng trước khi đưa vào mã nguồn dự án.

## 1. JShell giải quyết vấn đề gì?

Khi học Java hoặc thử một API, cách truyền thống thường là tạo tệp `.java`, khai báo lớp, viết `main()`, biên dịch bằng `javac`, rồi chạy bằng `java`. Quy trình đó cần thiết cho ứng dụng thật, nhưng có thể chậm khi chỉ muốn thử một vài dòng lệnh.

JShell rút ngắn vòng lặp này:

1. Nhập một biểu thức hoặc khai báo Java.
2. JShell phân tích và biên dịch snippet.
3. Snippet được thực thi trong phiên JShell.
4. Kết quả hoặc thông báo lỗi được hiển thị ngay.
5. Các khai báo hợp lệ vẫn có thể được sử dụng trong những snippet tiếp theo.

Ví dụ, bạn có thể nhập trực tiếp:

```java
2 + 3
```

JShell đánh giá biểu thức và hiển thị giá trị. Không cần tạo class chỉ để kiểm tra phép cộng.

JShell hữu ích khi:

- Học cú pháp, kiểu dữ liệu, collection, lambda và Stream API.
- Thử nhanh một phương thức trong thư viện Java.
- Kiểm tra định dạng ngày giờ, chuỗi, số hoặc biểu thức chính quy.
- Thử một đoạn thuật toán nhỏ trước khi viết unit test.
- Khám phá method và kiểu trả về của API.
- Minh họa Java trong buổi học hoặc buổi hướng dẫn kỹ thuật.

## 2. Kiểm tra và khởi động JShell

JShell đi kèm JDK từ Java 9. Mở Command Prompt, PowerShell hoặc terminal và kiểm tra:

```bash
java -version
javac -version
jshell --version
```

Các lệnh này giúp xác nhận Java runtime, compiler và JShell đang được tìm thấy qua môi trường hiện tại. JShell là công cụ của JDK; nếu máy chỉ có runtime mà không có JDK phù hợp, lệnh `jshell` có thể không tồn tại.

Khởi động JShell:

```bash
jshell
```

Khi công cụ mở thành công, bạn sẽ thấy dấu nhắc tương tự:

```text
|  Welcome to JShell -- Version 17
|  For an introduction type: /help intro

jshell>
```

Phiên bản và dòng giới thiệu thay đổi theo JDK được cài. Dấu nhắc `jshell>` cho biết công cụ đang chờ snippet hoặc lệnh JShell.

Thoát khỏi phiên:

```text
jshell> /exit
```

Có thể xem các tùy chọn khởi động:

```bash
jshell --help
```

## 3. Nhập biểu thức và câu lệnh Java

Trong JShell, có thể nhập trực tiếp các biểu thức và câu lệnh Java.

Ví dụ:

```text
jshell> 10 + 20
$1 ==> 30

jshell> String language = "Java";
language ==> "Java"

jshell> int major = 17;
major ==> 17

jshell> language + " " + major
$4 ==> "Java 17"
```

Đây là transcript minh họa theo feedback mode mặc định; tên biến tạm như `$1` hoặc số thứ tự có thể thay đổi tùy lịch sử phiên.

Một số điểm cần hiểu:

- Biểu thức có giá trị trả về có thể được JShell hiển thị dưới dạng biến tạm như `$1`.
- Khi khai báo biến có tên, có thể sử dụng biến đó trong những snippet tiếp theo.
- Câu lệnh như `System.out.println(...)` thực hiện hành động và in ra console.
- Các khai báo và biến hợp lệ được giữ trong trạng thái của phiên hiện tại.
- Mỗi lần nhập không nhất thiết phải nằm trong một class có `main()`.

Ví dụ in thông báo:

```text
jshell> System.out.println("Hello, JShell!");
Hello, JShell!
```

JShell vẫn dùng cú pháp Java. Các câu lệnh cần dấu chấm phẩy theo quy tắc Java; một biểu thức độc lập có thể được nhập trực tiếp để xem kết quả.

## 4. Khai báo method và class trong phiên

JShell cho phép khai báo method mà không cần tạo một lớp bao quanh trong mã nguồn.

Ví dụ nhập method:

```java
int square(int number) {
    return number * number;
}
```

Sau khi khai báo, gọi method ngay trong phiên:

```text
jshell> square(6)
$2 ==> 36
```

Có thể khai báo một class:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String greeting() {
        return "Xin chào, " + name;
    }
}
```

Tạo object và gọi method:

```text
jshell> Person person = new Person("Lan");
person ==> Person@...

jshell> person.greeting()
$4 ==> "Xin chào, Lan"
```

Phần địa chỉ hiển thị trong biểu diễn object có thể khác nhau. Giá trị của `greeting()` là kết quả cần quan tâm.

Nếu nhập một khối nhiều dòng, JShell hiển thị dấu nhắc tiếp dòng, thường là `...`, cho đến khi snippet hoàn chỉnh. Sau đó công cụ đánh giá toàn bộ khai báo.

## 5. Dùng import và khám phá Java API

Có thể nhập package hoặc lớp giống như trong tệp Java thông thường:

```java
import java.time.LocalDate;
import java.time.Period;
```

Sau đó dùng các lớp đã import:

```text
jshell> LocalDate start = LocalDate.of(2024, 1, 1);
start ==> 2024-01-01

jshell> LocalDate end = LocalDate.of(2024, 1, 10);
end ==> 2024-01-10

jshell> Period.between(start, end).getDays()
$3 ==> 9
```

Các import được giữ trong phiên. JShell cũng có một số import mặc định để thuận tiện khi thử nghiệm; dùng lệnh `/imports` để xem những import hiện đang có hiệu lực.

Ví dụ thử Stream API trên JDK 17:

```text
jshell> import java.util.List;

jshell> List<String> names = List.of("An", "Binh", "Chi");
names ==> [An, Binh, Chi]

jshell> names.stream().filter(name -> name.length() > 2).toList()
$3 ==> [Binh, Chi]
```

Phương thức `Stream.toList()` có từ Java 16, vì vậy ví dụ này phù hợp với JDK 17 trở lên.

## 6. Các loại snippet trong JShell

JShell gọi mỗi đơn vị mã được nhập là một *snippet*. Những loại snippet phổ biến gồm:

| Loại | Ví dụ |
| --- | --- |
| Expression | `1 + 2` |
| Variable declaration | `int count = 10;` |
| Method declaration | `int square(int x) { return x * x; }` |
| Class declaration | `class User { }` |
| Interface declaration | `interface Formatter { String format(String s); }` |
| Import declaration | `import java.time.LocalDate;` |
| Statement | `System.out.println("test");` |

Một snippet được đánh giá riêng, nhưng các khai báo thành công có thể tham chiếu lẫn nhau trong cùng phiên. Ví dụ, khai báo method có thể dùng biến hoặc class đã khai báo trước đó.

Nếu sửa lại một khai báo, JShell có thể cập nhật trạng thái và đánh giá lại những snippet phụ thuộc. Khi có lỗi cú pháp hoặc lỗi kiểu, thông báo được hiển thị để bạn sửa và nhập lại; phiên JShell vẫn tiếp tục hoạt động.

## 7. Các lệnh JShell quan trọng

Bên cạnh mã Java, JShell có các lệnh riêng bắt đầu bằng dấu gạch chéo `/`. Đây là lệnh điều khiển phiên, không phải cú pháp Java.

| Lệnh | Công dụng |
| --- | --- |
| `/help` | Hiển thị trợ giúp |
| `/help intro` | Giới thiệu cách sử dụng JShell |
| `/list` | Liệt kê các snippet trong phiên |
| `/vars` | Liệt kê biến đã khai báo |
| `/methods` | Liệt kê method đã khai báo |
| `/types` | Liệt kê class, interface, enum và kiểu đã khai báo |
| `/imports` | Liệt kê các import đang có |
| `/history` | Hiển thị lịch sử đầu vào của phiên |
| `/drop <id>` | Loại bỏ snippet theo ID |
| `/edit` | Mở snippet trong editor |
| `/save <file>` | Lưu các snippet của phiên vào tệp |
| `/open <file>` | Đọc và thực thi nội dung tệp trong phiên |
| `/reset` | Khởi tạo lại phiên, xóa trạng thái snippet hiện tại |
| `/reload` | Tải lại các snippet của phiên theo lịch sử |
| `/set feedback <mode>` | Thay đổi cách hiển thị phản hồi |
| `/exit` | Thoát JShell |

Có thể xem trợ giúp cho từng lệnh, ví dụ:

```text
jshell> /help /save
jshell> /help /open
```

Tên lệnh, tham số và cách hiển thị chi tiết có thể khác nhẹ theo phiên bản JDK. Khi cần cú pháp chính xác, hãy dùng `/help` ngay trong phiên đang chạy.

## 8. Quản lý biến, method và snippet

Khi thử nhiều ý tưởng, phiên JShell có thể chứa nhiều khai báo. Các lệnh liệt kê giúp quan sát trạng thái:

```text
jshell> /vars
jshell> /methods
jshell> /types
jshell> /imports
jshell> /list
```

Lệnh `/list` hiển thị các snippet cùng ID. Có thể dùng ID đó để xem hoặc loại bỏ một snippet.

Ví dụ:

```text
jshell> int temporary = 99;
temporary ==> 99

jshell> /vars
```

Nếu muốn bỏ khai báo `temporary`, trước hết xem ID của nó bằng `/list`, sau đó dùng:

```text
jshell> /drop <id>
```

Thay `<id>` bằng ID thực tế được hiển thị. Không nhập nguyên dấu ngoặc nhọn.

`/drop` loại bỏ snippet khỏi trạng thái JShell; nếu snippet khác phụ thuộc vào nó, trạng thái phụ thuộc có thể bị ảnh hưởng và cần được đánh giá lại.

## 9. Lưu và mở lại phiên làm việc

Các snippet trong phiên được giữ trong bộ nhớ. Nếu thoát JShell mà chưa lưu, bạn không nên giả định các khai báo sẽ tự động tồn tại ở lần mở tiếp theo.

Lưu snippet:

```text
jshell> /save experiment.jsh
```

Mở lại tệp trong phiên:

```text
jshell> /open experiment.jsh
```

Tệp có thể chứa các câu lệnh Java và nội dung phù hợp để JShell thực thi. Phần mở rộng `.jsh` thường được dùng cho script JShell, giúp phân biệt với mã nguồn Java thông thường.

Cũng có thể truyền tệp làm đầu vào khi khởi động:

```bash
jshell experiment.jsh
```

Một số tùy chọn lưu hữu ích:

- `/save <file>`: lưu các snippet hiện tại.
- `/save -history <file>`: lưu lịch sử đầu vào.
- `/save -all <file>`: lưu cả các snippet đã bị thay thế hoặc loại bỏ, theo khả năng của phiên bản JShell.

Nếu muốn kiểm tra chính xác các lựa chọn của phiên bản đang dùng, chạy `/help /save`.

Phân biệt `/history` và `/save`: history phản ánh các đầu vào đã thực hiện; save tạo tệp để có thể sử dụng lại nội dung trong phiên JShell khác.

## 10. Điều chỉnh feedback và editor

JShell hỗ trợ nhiều chế độ phản hồi để phù hợp với việc học hoặc trình diễn.

Ví dụ:

```text
jshell> /set feedback concise
```

Một số mode thường dùng:

- `normal`: phản hồi mặc định, cân bằng giữa thông tin và độ ngắn.
- `concise`: hiển thị ngắn gọn hơn.
- `verbose`: hiển thị chi tiết hơn.
- `silent`: hạn chế tối đa phản hồi.

Có thể xem thiết lập hiện tại bằng:

```text
jshell> /set
```

Để thay đổi editor dùng cho `/edit`, xem hướng dẫn:

```text
jshell> /help /set editor
```

Sau khi cấu hình editor, dùng `/edit` hoặc `/edit <id>` để chỉnh sửa snippet. Điều này hữu ích khi method hoặc class có nhiều dòng và việc sửa trực tiếp ở dấu nhắc trở nên bất tiện.

## 11. Sử dụng thư viện bên ngoài với classpath

JShell có thể sử dụng thư viện JAR bên ngoài. Khi khởi động, truyền đường dẫn thư viện bằng `--class-path`:

```bash
jshell --class-path lib/helper.jar
```

Sau đó import các lớp thuộc thư viện:

```java
import com.example.helper.TextHelper;
TextHelper.normalize("  Java  ")
```

Tên package và method ở ví dụ trên phụ thuộc thư viện thực tế. Hãy thay bằng API được cung cấp trong JAR của dự án.

Nếu cần nhiều JAR:

**Windows:**

```powershell
jshell --class-path "lib\helper.jar;lib\logging.jar"
```

**macOS/Linux:**

```bash
jshell --class-path "lib/helper.jar:lib/logging.jar"
```

Dấu phân cách classpath là dấu chấm phẩy trên Windows và dấu hai chấm trên macOS/Linux. Đặt giá trị trong dấu nháy khi có khoảng trắng hoặc ký tự có ý nghĩa đặc biệt với shell.

Có thể thay đổi môi trường classpath của phiên bằng lệnh `/env`; hãy xem `/help /env` để biết cú pháp của JDK đang dùng. Sau khi thay đổi môi trường, một số snippet có thể cần được đánh giá lại.

## 12. Sử dụng module path

Với thư viện được đóng gói thành named module, có thể truyền module path và module cần thêm khi khởi động JShell:

```bash
jshell --module-path mods --add-modules com.example.library
```

Trong đó:

- `--module-path mods`: chỉ nơi chứa các module.
- `--add-modules com.example.library`: yêu cầu module được thêm vào cấu hình module của phiên.

Sau đó có thể import các kiểu public được export từ module:

```java
import com.example.library.Utility;
```

Module phải được phân giải đúng và package cần được export theo quy tắc JPMS. Module path không thay thế classpath; hãy dùng đúng tùy chọn theo cách thư viện được đóng gói.

Nếu gặp lỗi không tìm thấy module hoặc package không được export, hãy kiểm tra tên module, module descriptor, đường dẫn và quan hệ `requires`/`exports`.

## 13. Ví dụ thực hành: thử một hàm xử lý chuỗi

Khởi động JShell:

```bash
jshell
```

Nhập từng snippet:

```java
import java.util.Locale;

String normalize(String text) {
    return text.trim().toLowerCase(Locale.ROOT);
}

normalize("  HELLO JAVA  ")
```

Kết quả biểu thức cuối:

```text
$3 ==> "hello java"
```

Số hiệu biến tạm có thể khác nếu phiên đã có các snippet trước đó.

Thử thêm nhiều dữ liệu:

```java
List<String> values = List.of(" Java ", " JSHELL ", " JDK ");

values.stream()
    .map(value -> normalize(value))
    .toList()
```

Các khai báo method ở top level của JShell được đưa vào ngữ cảnh static của snippet. Vì vậy không thể dùng this::normalize: không có instance this trong ngữ cảnh đó. Lambda gọi trực tiếp method top-level là cách viết phù hợp. Nếu normalize là một method static của một lớp đã biên dịch, có thể dùng ClassName::normalize; nếu là method instance, hãy tạo instance rõ ràng rồi tham chiếu instance đó:

```java
values.stream()
    .map(value -> normalize(value))
    .toList()
```

Kết quả:

```text
$5 ==> [java, jshell, jdk]
```

Ví dụ này cho thấy JShell phù hợp để thử từng bước: khai báo import, viết method, tạo dữ liệu và gọi Stream API mà không cần tạo một dự án riêng.

## 14. JShell xử lý lỗi như thế nào?

Khi snippet không hợp lệ, JShell hiển thị thông báo chẩn đoán và tiếp tục chờ đầu vào. Ví dụ:

```text
jshell> int total = "Java";
|  Error:
|  incompatible types: java.lang.String cannot be converted to int
|  int total = "Java";
|              ^----^
```

Có thể nhập lại bằng kiểu đúng:

```text
jshell> String total = "Java";
total ==> "Java"
```

Các lỗi thường gặp:

- **Sai cú pháp:** thiếu dấu ngoặc, dấu chấm phẩy hoặc dùng sai cấu trúc Java.
- **Sai kiểu dữ liệu:** gán một giá trị không tương thích với kiểu biến.
- **Không tìm thấy symbol:** chưa khai báo biến/method hoặc chưa import lớp.
- **Không tìm thấy package:** thiếu JAR trong classpath hoặc module trong module path.
- **Trùng tên khai báo:** đã có biến hoặc method cùng tên với chữ ký không phù hợp.
- **Lỗi khi thực thi:** snippet biên dịch được nhưng phát sinh exception trong lúc chạy.

Đọc phần vị trí lỗi và thông báo kiểu dữ liệu trước khi nhập lại. Nếu trạng thái phiên trở nên khó theo dõi, dùng `/list` để xem snippet hoặc `/reset` để bắt đầu phiên mới.

## 15. JShell khác javac và java như thế nào?

| Tiêu chí | JShell | javac | java |
| --- | --- | --- | --- |
| Vai trò | REPL để thử mã tương tác | Biên dịch mã nguồn | Khởi chạy ứng dụng/lớp Java |
| Đầu vào | Snippet hoặc script JShell | Tệp nguồn Java và tùy chọn compiler | Lớp, module hoặc JAR có entry point |
| Cần viết class/main cho thử nghiệm nhỏ | Không | Thông thường mã nguồn ứng dụng cần cấu trúc lớp hợp lệ | Ứng dụng cần entry point phù hợp |
| Trạng thái giữa các lần nhập | Giữ trong phiên hiện tại | Không có phiên tương tác | Mỗi tiến trình chạy có vòng đời riêng |
| Mục đích phù hợp | Học, thử API, kiểm tra ý tưởng | Build mã nguồn | Chạy ứng dụng đã biên dịch |

JShell không thay thế hoàn toàn Maven, Gradle, IDE, unit test hoặc quy trình build. Nó giúp thử nhanh một đoạn mã; dự án thực tế vẫn cần cấu trúc source, dependency, test, đóng gói và kiểm soát phiên bản.

## 16. Khi nào nên và không nên dùng JShell?

**Nên dùng khi:**

- Muốn thử một biểu thức hoặc API nhanh.
- Cần minh họa cú pháp Java trong lớp học.
- Muốn kiểm tra kết quả của một đoạn code ngắn.
- Đang khám phá thư viện hoặc kiểm tra kiểu trả về.
- Cần tái hiện một vấn đề nhỏ trước khi viết test.

**Không nên chỉ dựa vào JShell khi:**

- Phát triển ứng dụng nhiều module hoặc nhiều dependency.
- Cần kiểm tra build có thể tái lập trong CI.
- Cần quản lý cấu hình, tài nguyên, logging và packaging.
- Cần unit test hoặc integration test có thể chạy tự động.
- Cần kiểm tra hiệu năng nghiêm túc; benchmark cần quy trình riêng để tránh sai lệch do JIT và trạng thái runtime.

Khi thử nghiệm có giá trị, hãy lưu snippet bằng `/save`, chuyển phần mã ổn định vào source file và bổ sung test phù hợp.

## 17. Lỗi thường gặp khi khởi động và sử dụng

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `jshell` không được nhận diện | Chưa cài JDK 9+ hoặc `PATH` chưa trỏ đến JDK | Kiểm tra `JAVA_HOME`, cài JDK và cập nhật `PATH` |
| JShell dùng phiên bản Java khác dự kiến | Có nhiều JDK và thứ tự `PATH` không như mong đợi | Dùng `where.exe jshell` trên Windows hoặc `command -v jshell` trên macOS/Linux |
| Không import được lớp thư viện | Thiếu JAR hoặc sai package | Khởi động với `--class-path` và kiểm tra tên lớp |
| Không tìm thấy module | Module path sai hoặc module chưa được thêm | Kiểm tra `--module-path`, `--add-modules` và module descriptor |
| Biến hoặc method không còn tồn tại | Đã reset phiên hoặc snippet bị drop | Kiểm tra `/list`, mở lại script hoặc khai báo lại |
| Không thấy nội dung đã nhập ở phiên trước | Phiên cũ chưa được lưu | Dùng `/save` trước khi thoát và `/open` khi cần khôi phục |
| Kết quả hiển thị quá nhiều thông tin | Feedback mode đang ở mức verbose | Dùng `/set feedback concise` hoặc mode phù hợp |
| Lệnh `/edit` không mở editor như mong muốn | Chưa cấu hình editor hoặc lệnh editor không hợp lệ | Xem `/help /set editor` và cấu hình lại |

## 18. Quy trình học và thử nghiệm với JShell

Một quy trình đơn giản:

1. Chạy `jshell --version` để xác nhận đúng JDK.
2. Mở phiên bằng `jshell`.
3. Dùng `/help intro` để xem hướng dẫn nhanh.
4. Nhập import, biến và biểu thức cần thử.
5. Tách method hoặc class thành snippet để tái sử dụng.
6. Dùng `/vars`, `/methods`, `/types` và `/list` để xem trạng thái.
7. Khi có lỗi, đọc chẩn đoán và sửa snippet.
8. Lưu kết quả hữu ích bằng `/save`.
9. Thử mở lại bằng `/open` để xác nhận script có thể chạy lại.
10. Chuyển mã đã ổn định vào dự án và viết test nếu cần.

## 19. Ghi nhớ

- JShell là REPL đi kèm JDK, được giới thiệu từ Java 9.
- Có thể thử biểu thức, câu lệnh, biến, method, class và import mà không cần tạo class có `main()` cho mỗi lần thử.
- Snippet hợp lệ được giữ trong phiên hiện tại và có thể được sử dụng ở các snippet sau.
- Các lệnh bắt đầu bằng `/` như `/help`, `/list`, `/vars`, `/save`, `/open` và `/exit` dùng để quản lý phiên.
- Dùng `--class-path` cho thư viện JAR và `--module-path`/ `--add-modules` cho module.
- Lưu snippet trước khi thoát nếu muốn sử dụng lại.
- JShell phù hợp cho thử nghiệm nhanh; ứng dụng thực tế vẫn cần build và kiểm thử theo quy trình dự án.

JShell giúp rút ngắn khoảng cách giữa việc đọc tài liệu Java và thử trực tiếp API. Khi sử dụng thành thạo REPL, bạn có thể kiểm tra ý tưởng nhanh hơn, hiểu rõ kết quả từng biểu thức và chuyển những thử nghiệm hữu ích thành mã nguồn có cấu trúc.
