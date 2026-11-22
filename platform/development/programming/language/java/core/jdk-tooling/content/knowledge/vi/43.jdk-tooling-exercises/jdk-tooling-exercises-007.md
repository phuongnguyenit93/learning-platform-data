# Thử nghiệm bằng JShell

## 1. JShell là gì?

JShell (Java Shell) là công cụ REPL có trong JDK từ Java 9. REPL là viết tắt của Read–Eval–Print Loop: đọc một đoạn code, biên dịch và thực thi, sau đó hiển thị kết quả ngay trong cùng phiên làm việc.

Thay vì phải tạo một class có phương thức main, lưu file, chạy javac rồi mới chạy java cho từng thử nghiệm nhỏ, bạn có thể nhập trực tiếp biểu thức, câu lệnh và khai báo Java vào JShell.

JShell hữu ích khi cần:

- Thử một biểu thức, toán tử hoặc API Java trước khi đưa vào ứng dụng.
- Kiểm tra nhanh cách một collection, Stream, Date/Time API hoặc thư viện hoạt động.
- Viết thử method, class, record hoặc lambda.
- Đọc và thử một API chưa quen thuộc.
- Tạo ví dụ ngắn để học hoặc giải thích một tính năng Java.
- Kiểm tra nhanh kết quả của một phép biến đổi dữ liệu.
- Nạp lại một nhóm snippet để tiếp tục thử nghiệm.

JShell phù hợp cho khám phá và tạo prototype. Nó không thay thế cấu trúc project, unit test, integration test hoặc quy trình build của ứng dụng thật.

## 2. Kiểm tra JDK và khởi động JShell

JShell là công cụ của JDK. Nếu terminal không nhận diện lệnh `jshell`, hãy kiểm tra JDK đã cài và biến PATH.

Xem phiên bản Java và JShell:

```bash
java --version
javac --version
jshell --version
```

Khởi động phiên tương tác:

```bash
jshell
```

Có thể yêu cầu nhiều hoặc ít thông tin phản hồi ngay khi mở:

```bash
jshell --feedback verbose
jshell --feedback normal
jshell --feedback concise
jshell --feedback silent
```

`verbose` hữu ích khi mới học vì JShell giải thích snippet vừa tạo hoặc thay đổi. `concise` gọn hơn khi chạy ví dụ. `silent` hạn chế phản hồi thành công nhưng lỗi vẫn được hiển thị.

Khi khởi động, JShell hiển thị phiên bản JDK và gợi ý dùng `/help intro`. Nhập:

```text
/help intro
```

Để thoát:

```text
/exit
```

Có thể dùng `/exit 0` để kết thúc với mã thoát cụ thể. Khi làm việc trong terminal, mã thoát giúp script bên ngoài nhận biết kết quả của phiên JShell.

## 3. Hiểu snippet và vòng lặp REPL

Đơn vị code JShell tiếp nhận được gọi là **snippet**. Một snippet có thể là:

- Biểu thức, ví dụ `2 + 2`.
- Câu lệnh, ví dụ `System.out.println("Hello")`.
- Khai báo biến.
- Khai báo method.
- Khai báo class, interface, enum hoặc record.
- Câu lệnh import.

Mỗi snippet hoàn chỉnh được biên dịch và đánh giá ngay khi JShell nhận đủ nội dung. Khi một khai báo nhiều dòng chưa hoàn chỉnh, prompt chuyển sang `...>` để bạn tiếp tục nhập.

Ví dụ:

```text
jshell> 2 + 2
$1 ==> 4

jshell> System.out.println("Hello, JShell!")
Hello, JShell!
```

Với biểu thức không có tên biến, JShell tạo scratch variable như `$1`. Giá trị này có thể dùng lại trong phiên:

```text
jshell> $1 * 10
$2 ==> 40
```

Tên `$1`, `$2` do JShell sinh ra để tham chiếu kết quả tạm. Không dùng chúng làm tên biến ổn định trong code ứng dụng hoặc giả định số thứ tự giống nhau giữa các phiên.

JShell tự thêm dấu chấm phẩy vào cuối một snippet hoàn chỉnh nếu bạn bỏ dấu `;`. Tuy vậy, nên viết dấu chấm phẩy trong ví dụ nhiều câu lệnh để dễ chuyển code sang file Java thông thường.

## 4. Thử biểu thức, câu lệnh và biến

Bạn có thể nhập biểu thức Java trực tiếp:

```java
2 + 3
10 * 4
Math.sqrt(81)
"java".toUpperCase()
```

Kết quả tương ứng là `5`, `40`, `9.0` và `"JAVA"`.

Khai báo biến:

```java
int quantity = 3;
double price = 19.5;
double total = quantity * price;
total
```

JShell giữ biến trong session để dùng ở snippet tiếp theo:

```text
jshell> int quantity = 3
quantity ==> 3

jshell> double price = 19.5
price ==> 19.5

jshell> double total = quantity * price
total ==> 58.5

jshell> total
total ==> 58.5
```

Có thể dùng `var` để suy luận kiểu biến cục bộ:

```java
var language = "Java";
var majorVersion = 17;
```

Kiểu của `language` là `String`, còn `majorVersion` là `int`. JShell vẫn yêu cầu kiểu của biến có thể được suy luận tại thời điểm khai báo; `var` không có nghĩa là biến có thể đổi kiểu tùy ý.

Dùng `/vars` để xem các biến đang có:

```text
/vars
```

## 5. Import và khám phá Java API

JShell tự động import `java.lang` và một số package thường dùng thông qua startup script mặc định, chẳng hạn `java.util`, `java.io`, `java.math`, `java.nio.file` và `java.util.stream`.

Bạn vẫn có thể import rõ ràng:

```java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
```

Ví dụ thử Date/Time API:

```java
var today = LocalDate.now();
var nextWeek = today.plusDays(7);
nextWeek
```

Thử collection:

```java
var names = new ArrayList<String>();
names.add("An");
names.add("Binh");
names.add("Chi");
names
```

Xem import hiện tại:

```text
/imports
```

Để tìm hiểu method của một API, dùng Tab completion và `/help`. Ví dụ nhập `LocalDate.` rồi nhấn Tab trong phiên tương tác để xem các method có thể gọi. Tại vị trí tham số của method, Tab cũng có thể hiển thị overload và gợi ý kiểu tham số.

## 6. Khai báo và gọi method

JShell cho phép khai báo method mà không cần đặt nó trong một class do bạn tự tạo:

```java
int square(int value) {
    return value * value;
}
```

Gọi method ngay sau khi khai báo:

```java
square(7)
square(12)
```

Method có thể gọi method khác:

```java
int cube(int value) {
    return value * square(value);
}
cube(3)
```

Kết quả:

```text
$1 ==> 49
$2 ==> 144
$3 ==> 27
```

Có thể định nghĩa method tham chiếu đến method hoặc biến chưa khai báo. JShell chấp nhận forward reference trong quá trình khám phá, nhưng chưa thể gọi method cho tới khi các phần phụ thuộc được khai báo hợp lệ.

Ví dụ:

```java
double volume(double radius) {
    return 4.0 / 3.0 * Math.PI * cubeDouble(radius);
}
double cubeDouble(double value) {
    return value * value * value;
}
volume(2.0)
```

Nếu thay đổi chữ ký hoặc kiểu của khai báo đang được method khác sử dụng, những snippet phụ thuộc có thể không còn biên dịch được. Hãy chạy lại biểu thức liên quan và xem lỗi trước khi dùng kết quả.

## 7. Thử class, record và lambda

Bạn có thể tạo class ngay trong JShell:

```java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int current() {
        return value;
    }
}
```

Tạo đối tượng và gọi method:

```java
var counter = new Counter();
counter.increment();
counter.increment();
counter.current()
```

Java 17 hỗ trợ record, rất tiện khi thử kiểu dữ liệu chỉ chứa dữ liệu:

```java
record Student(String name, int score) {}
var student = new Student("Lan", 92);
student.name()
student.score()
```

Thử lambda và Stream:

```java
import java.util.List;
var scores = List.of(72, 85, 92, 68, 90);
var passed = scores.stream()
    .filter(score -> score >= 80)
    .toList();
passed
```

JShell rất hữu ích để so sánh các biểu thức Stream, kiểm tra method reference hoặc thử một thuật toán nhỏ trước khi viết test chính thức.

Lưu ý: JShell không phải một source file Java thông thường. Không khai báo `package` ở đầu phiên như trong file `.java`. Nếu cần thử class thuộc package thật, hãy biên dịch class đó thành file `.class` hoặc JAR rồi thêm vào classpath của JShell.


## 8. Sửa và thay thế snippet

Khi thử nghiệm, bạn có thể khai báo lại method hoặc class để sửa cách hoạt động. Khai báo mới cùng chữ ký sẽ thay thế định nghĩa cũ:

```java
String greet(String name) {
    return "Hello, " + name + "!";
}
greet("Java")
```

Sửa method:

```java
String greet(String name) {
    return "Welcome, " + name + "!";
}
greet("Java")
```

JShell thông báo method đã được sửa và các lần gọi tiếp theo dùng định nghĩa mới. Khi thay đổi không tương thích, ví dụ đổi kiểu hoặc xóa một method được sử dụng ở nơi khác, các snippet phụ thuộc có thể trở thành lỗi. Hãy kiểm tra lại chúng trước khi lưu hoặc dùng kết quả.

Các lệnh hữu ích:

- `/list`: liệt kê snippet đang hoạt động.
- `/list -all`: liệt kê cả snippet lỗi, bị thay thế, đã drop và startup.
- `/drop <id>`: loại một snippet khỏi trạng thái đang hoạt động.
- `/edit <id>`: mở snippet trong editor để sửa.
- `/vars`, `/methods`, `/types`: xem biến, method và kiểu đã khai báo.

ID snippet là số hiển thị trong `/list`. Dùng ID để chọn đúng phần code cần sửa hoặc xóa.

## 9. Các lệnh JShell thường dùng

Lệnh JShell bắt đầu bằng dấu `/`, khác với snippet Java. Bảng sau là nhóm lệnh nên biết khi thực hành:

| Lệnh | Công dụng |
|---|---|
| `/help` | Hiển thị danh sách lệnh và chủ đề trợ giúp |
| `/help intro` | Giới thiệu cách sử dụng JShell |
| `/list` | Liệt kê snippet đang hoạt động |
| `/list -all` | Liệt kê cả snippet không hoạt động và startup |
| `/vars` | Xem biến và giá trị |
| `/methods` | Xem method và chữ ký |
| `/types` | Xem class, interface, enum, record |
| `/imports` | Xem import |
| `/history` | Xem lịch sử nhập |
| `/edit` | Mở editor để sửa snippet |
| `/drop` | Bỏ một snippet |
| `/open` | Nạp snippet từ file hoặc startup script |
| `/save` | Lưu snippet hoặc lịch sử vào file |
| `/env` | Xem hoặc thay đổi classpath/module options |
| `/reset` | Xóa trạng thái phiên và khởi động lại |
| `/reload` | Khởi động lại và nạp lại snippet theo lịch sử |
| `/set feedback` | Đổi mức độ phản hồi |
| `/exit` | Thoát JShell |

Bạn có thể dùng `/help <command>` để xem cú pháp chi tiết, ví dụ:

```text
/help /save
/help /env
/help /edit
```

Các lệnh và tùy chọn có thể được hoàn thành bằng Tab. Có thể viết tắt lệnh nếu phần viết tắt là duy nhất, nhưng nên dùng tên đầy đủ trong script để người đọc dễ hiểu.

## 10. Chỉnh sửa, history và quản lý trạng thái

JShell hỗ trợ điều hướng lịch sử nhập bằng phím mũi tên lên/xuống và chỉnh sửa dòng hiện tại. Khi method hoặc class dài, `/edit` mở external editor phù hợp hơn sửa từng dòng trong prompt.

Có thể cấu hình editor qua:

```text
/set editor
```

JShell kiểm tra các biến môi trường `JSHELLEDITOR`, `VISUAL`, `EDITOR` trước khi dùng editor mặc định. Cú pháp cấu hình editor cụ thể xem bằng `/help /set editor`.

Trạng thái phiên có thể xóa bằng:

```text
/reset
```

`/reset` khởi tạo lại trạng thái thực thi và nạp startup script đã cấu hình. Các biến, method và class do bạn tạo trong phiên hiện tại không còn được giữ lại nếu chưa lưu.

Dùng `/history` để xem những gì đã nhập. History hữu ích khi muốn tìm lại lệnh, nhưng nó có thể chứa cả lệnh lỗi hoặc nội dung nhạy cảm đã nhập. Kiểm tra file trước khi chia sẻ.

## 11. Lưu snippet và tạo JShell script

Không cần nhập lại các thử nghiệm sau mỗi lần mở JShell. Có thể lưu các snippet đang hoạt động:

```text
/save experiments.jsh
```

Lưu lịch sử nhập:

```text
/save -history experiments-history.jsh
```

Lưu startup definitions:

```text
/save -start my-startup.jsh
```

Một JShell script là file chứa các snippet và lệnh JShell. Mỗi snippet hoặc lệnh là một đơn vị trong file. Có thể chạy script khi khởi động:

```bash
jshell experiments.jsh
```

Hoặc nạp từ một phiên đang mở:

```text
/open experiments.jsh
```

Ví dụ file `math-lab.jsh`:

```java
import java.util.List;

int square(int n) {
    return n * n;
}

var values = List.of(1, 2, 3, 4, 5);
var squared = values.stream().map(n -> square(n)).toList();
squared
```

Chạy:

```bash
jshell --feedback concise math-lab.jsh
```

Script giúp tái sử dụng các định nghĩa trong buổi học hoặc buổi khám phá API. Nó không phải project build: script không tự tạo JAR, không quản lý dependency như Gradle và không thay thế test suite.

## 12. Startup script và các script có sẵn

JShell có startup script mặc định tên `DEFAULT`, chứa các import thường dùng. Các startup script được nạp khi bắt đầu hoặc khi trạng thái được reset.

Một số script có sẵn:

| Tên | Nội dung |
|---|---|
| `DEFAULT` | Các import thường dùng |
| `PRINTING` | Các method tiện ích `print`, `println`, `printf` |
| `TOOLING` | Truy cập các JDK command-line tools như `javac`, `javadoc`, `javap` |

Nạp script `PRINTING` trong phiên:

```text
/open PRINTING
```

Sau đó có thể gọi `println("Hello")` mà không cần viết `System.out.println`.

Nạp script `TOOLING`:

```text
/open TOOLING
```

Script này cung cấp các method tiện ích để gọi công cụ JDK thông qua `ToolProvider`, ví dụ:

```java
tools()
javac("--version")
```

Có thể đặt startup script khi khởi động:

```bash
jshell --startup my-startup.jsh
```

Hoặc bỏ startup script mặc định:

```bash
jshell --no-startup
```

Dùng startup script riêng khi có nhóm import hoặc method tiện ích cần dùng thường xuyên. Đừng đưa logic ứng dụng lớn vào startup script vì nó làm trạng thái ban đầu khó hiểu và khó tái lập.

## 13. Chọn feedback mode phù hợp

Feedback mode quyết định mức thông tin JShell hiển thị khi snippet được nhập.

| Mode | Hành vi |
|---|---|
| `verbose` | Nhiều thông tin nhất, gồm mô tả khai báo và cập nhật |
| `normal` | Mức phản hồi mặc định |
| `concise` | Chỉ hiển thị kết quả cần thiết, ít thông tin phụ |
| `silent` | Không hiển thị phản hồi thành công; lỗi vẫn hiện |

Đổi trong phiên:

```text
/set feedback verbose
/set feedback concise
/set feedback silent
```

Hoặc đặt ngay khi khởi động:

```bash
jshell --feedback verbose
jshell --feedback concise
```

Khi học một API mới, `verbose` giúp thấy snippet nào vừa được tạo hoặc thay đổi. Khi chạy script hoặc demo ngắn, `concise` giúp output dễ đọc. Khi debug, không nên dùng `silent` nếu bạn cần nhìn thấy kết quả từng bước.

## 14. Dùng class bên ngoài qua classpath

JShell có thể dùng code đã biên dịch trong thư mục class hoặc JAR. Class đó phải thuộc package có tên; class trong unnamed package không thể được import từ JShell.

Ví dụ biên dịch thư viện vào thư mục `build/classes/java/main`, sau đó mở JShell:

```bash
jshell --class-path build/classes/java/main
```

Nếu cần nhiều thư mục/JAR, phân cách bằng dấu `;` trên Windows hoặc dấu `:` trên Linux/macOS.

Windows:

```powershell
jshell --class-path "build/classes/java/main;lib/greeter.jar"
```

Linux/macOS:

```bash
jshell --class-path 'build/classes/java/main:lib/greeter.jar'
```

Trong JShell, import package như bình thường:

```java
import com.example.greeter.Greeter;
Greeter.greet("Classpath")
```

Nếu phiên đã mở, có thể thay đổi classpath:

```text
/env --class-path build/classes/java/main
```

`/env` thay đổi evaluation context và khôi phục lại các snippet hiện tại với tùy chọn môi trường mới. Khi đổi classpath, JShell có thể reset engine để nạp lại trạng thái. Nếu snippet không thể biên dịch lại, cần sửa dependency hoặc khai báo tương ứng.

## 15. Dùng module path và module options

JShell cũng hỗ trợ module path. Có thể chỉ định module path và các module gốc cần resolve khi khởi động:

```bash
jshell --module-path mods --add-modules com.example.greeter
```

Trong đó:

- `--module-path` chỉ thư mục hoặc JAR chứa module.
- `--add-modules` yêu cầu resolve các module được nêu.
- `--add-exports` có thể mở package cụ thể cho module đích nếu cần tích hợp có chủ đích.

Trong JShell, xem và thay đổi evaluation context bằng `/env`:

```text
/env
/env --module-path mods --add-modules com.example.greeter
```

Module phải export package mà snippet muốn import. Code nhập trực tiếp trong JShell chạy trong unnamed module, vì vậy package chỉ export có giới hạn cho một module named cụ thể có thể không truy cập được từ JShell.

JShell phù hợp để thử API public của module. Để xác nhận toàn bộ module graph, launch configuration và encapsulation của ứng dụng, hãy build và chạy ứng dụng modular thực tế bằng `java --module-path ... -m ...` hoặc Gradle. Không coi một snippet chạy được trong JShell là bằng chứng đầy đủ rằng ứng dụng module path đã cấu hình đúng.


## 16. Truyền tùy chọn compiler và runtime

JShell cung cấp các nhóm tùy chọn khác nhau:

- `-C<flag>` truyền cờ cho compiler dùng để biên dịch snippet.
- `-R<flag>` truyền cờ cho runtime khi snippet được thực thi.
- `-J<flag>` truyền cờ cho JVM chạy chính công cụ JShell; cờ này không tự động áp dụng cho quá trình thực thi snippet.
- `--enable-preview` bật preview features của JDK hiện tại khi cần thử API/ngôn ngữ preview.

Ví dụ bật compiler warnings:

```bash
jshell -C-Xlint
```

Truyền property cho runtime của snippet:

```bash
jshell -R-Dapp.mode=demo
```

Trong phiên, thử:

```java
System.getProperty("app.mode")
```

Để thử preview feature, cần dùng JDK có hỗ trợ feature đó và bật preview tương ứng khi khởi động JShell. Preview API/ngôn ngữ gắn với đúng phiên bản JDK; không nên copy ví dụ preview sang JDK khác mà không kiểm tra lại.

## 17. Ví dụ thực hành: phân tích danh sách khóa học

Bài tập này dùng JShell để khai báo record, tạo collection, lọc dữ liệu và viết method tính trung bình. Chạy được trên Java 17+.

Mở JShell:

```bash
jshell --feedback concise
```

Import collection:

```java
import java.util.List;
```

Tạo kiểu dữ liệu:

```java
record Course(String title, int hours) {}
```

Tạo dữ liệu mẫu:

```java
var courses = List.of(
    new Course("Core Java", 24),
    new Course("Gradle", 12),
    new Course("Testing", 18)
);
```

Tính tổng số giờ:

```java
int totalHours = courses.stream()
    .mapToInt(Course::hours)
    .sum();
totalHours
```

Lọc khóa học có ít nhất 18 giờ:

```java
var intensive = courses.stream()
    .filter(course -> course.hours() >= 18)
    .map(Course::title)
    .toList();
intensive
```

Tạo method tính số giờ trung bình:

```java
double averageHours(List<Course> values) {
    return values.stream()
        .mapToInt(Course::hours)
        .average()
        .orElse(0.0);
}
```

Gọi method:

```java
averageHours(courses)
```

Kết quả quan trọng:

```text
totalHours ==> 54
intensive ==> [Core Java, Testing]
$... ==> 18.0
```

Tên scratch variable trong kết quả thực tế phụ thuộc số snippet đã chạy trước đó; giá trị trả về là `18.0`.

Có thể xem trạng thái:

```text
/vars
/methods
/types
/list
```

Thử đổi dữ liệu:

```java
var extendedCourses = List.of(
    new Course("Core Java", 24),
    new Course("Gradle", 12),
    new Course("Testing", 18),
    new Course("JVM", 30)
);
averageHours(extendedCourses)
```

Kết quả mới là `21.0`. Việc thay đổi dữ liệu và gọi lại method ngay trong cùng phiên giúp thử nhanh logic trước khi chuyển thành unit test.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jshell` không được nhận diện | JDK chưa cài hoặc PATH chưa trỏ đến JDK | Kiểm tra `java --version`, `javac --version`, `JAVA_HOME` và PATH |
| `illegal start of expression` với `package` | JShell nhận snippet trong môi trường không khai báo package | Bỏ package declaration; biên dịch class có package rồi thêm classpath |
| `cannot find symbol` | Chưa import, khai báo hoặc thêm dependency | Kiểm tra `/imports`, `/vars`, `/types`, classpath |
| `package ... does not exist` | Thiếu JAR/class hoặc package không được export | Kiểm tra `--class-path` hoặc module options |
| `ClassNotFoundException` | Class không có trong runtime classpath | Thêm đúng thư mục/JAR vào classpath |
| `NoClassDefFoundError` | Dependency cần lúc chạy không có | Kiểm tra dependency runtime |
| `module not found` | Module path thiếu module hoặc sai tên | Kiểm tra `--module-path`, `--add-modules` |
| `package ... is not visible` | Module chưa export package hoặc snippet không đọc module | Kiểm tra module descriptor và exports |
| `InaccessibleObjectException` | Framework cần deep reflection nhưng package chưa mở | Kiểm tra `opens` hoặc `--add-opens` |
| Method cũ không chạy sau khi sửa | Snippet phụ thuộc đã trở thành lỗi | Xem `/list -all`, sửa dependency và gọi lại |
| Script không nạp được | Sai đường dẫn hoặc file có cú pháp snippet không hợp lệ | Kiểm tra path và chạy thử từng snippet |
| Kết quả khác giữa các máy | JDK version, classpath, locale hoặc môi trường khác | Ghi lại JDK và tùy chọn khi chạy |
| Javadoc/API không tìm thấy | Import hoặc module chưa được resolve | Kiểm tra import và module path |

Khi có lỗi, đọc dòng thông báo đầu tiên và vị trí snippet. Dùng `/list` để tìm ID, sau đó `/edit <id>` để sửa. JShell thường cho phép tiếp tục nhập snippet khác sau khi một snippet lỗi, vì vậy không cần khởi động lại cho mọi lỗi cú pháp.

## 19. JShell phù hợp và không phù hợp với việc gì?

| Công việc | JShell | Công cụ phù hợp hơn |
|---|---|---|
| Thử một biểu thức Java | Rất phù hợp | — |
| Khám phá API | Rất phù hợp | IDE/Javadoc khi cần xem toàn bộ tài liệu |
| Thử method hoặc record ngắn | Phù hợp | File Java khi cần package hoặc nhiều class |
| Thử Stream/lambda | Rất phù hợp | Unit test để xác nhận lâu dài |
| Dùng thư viện đã biên dịch | Phù hợp | Gradle/Maven để quản lý dependency |
| Kiểm tra package/module của ứng dụng | Thử API từng phần | javac, java, Gradle và module tests |
| Kiểm thử hồi quy | Không phải test framework | JUnit hoặc framework test của project |
| Build và phát hành JAR | Không phù hợp | Gradle/Maven |
| Đánh giá hiệu năng đáng tin cậy | Không phù hợp để benchmark chính thức | JMH hoặc benchmark harness có kiểm soát |

JShell giúp rút ngắn vòng lặp thử nghiệm. Khi logic đã ổn, chuyển nó sang source file đúng package, viết test tự động và chạy bằng build tool của project.

## 20. Quy trình thực hành gợi ý

1. Kiểm tra `jshell --version` để biết JDK đang dùng.
2. Mở phiên với `jshell --feedback verbose` khi đang học.
3. Thử biểu thức nhỏ, biến và import.
4. Viết method hoặc record để kiểm tra logic.
5. Dùng `/vars`, `/methods`, `/types`, `/list` để quan sát trạng thái.
6. Sửa snippet và thử lại nhiều trường hợp đầu vào.
7. Nếu cần thư viện ngoài, biên dịch nó và thêm bằng `--class-path`.
8. Nếu cần module, cấu hình `--module-path` và `--add-modules`.
9. Lưu những snippet hữu ích bằng `/save` hoặc `/save -history`.
10. Chuyển code đã ổn sang project thật và viết unit test.
11. Chạy build/test bằng Gradle hoặc Maven trước khi phát hành.

## 21. Tổng kết

JShell là REPL của JDK giúp thử nghiệm Java nhanh trong một phiên tương tác. Bạn có thể nhập biểu thức, câu lệnh, biến, method, class, record, import và lambda; kết quả được hiển thị ngay mà không cần tạo class main cho mỗi thử nghiệm.

Những điểm cần nhớ:

- Dùng `jshell --version` để xác nhận JDK có JShell.
- Snippet được đánh giá ngay khi hoàn chỉnh; kết quả biểu thức có thể được lưu trong scratch variable.
- Khai báo lại method/class để thử phiên bản mới; dùng `/list` và `/drop` để quản lý snippet.
- Dùng `/vars`, `/methods`, `/types`, `/imports` để xem trạng thái.
- Dùng `/open` và `/save` để tái sử dụng script.
- Dùng `--class-path` cho class/JAR đã biên dịch và `--module-path` cho module.
- Dùng `/env` khi cần thay đổi evaluation context trong phiên.
- Chọn feedback mode phù hợp với học tập hoặc chạy script.
- JShell hỗ trợ khám phá; unit test và build tool vẫn là bước xác nhận cho project thật.

**Tài liệu tham khảo chính thức:**

- [Oracle Java SE 24 — Java Shell User's Guide](https://docs.oracle.com/en/java/javase/24/jshell/index.html)
- [Oracle Java SE 24 — Introduction to JShell](https://docs.oracle.com/en/java/javase/24/jshell/introduction-jshell.html)
- [Oracle Java SE 24 — Snippets](https://docs.oracle.com/en/java/javase/24/jshell/snippets.html)
- [Oracle Java SE 24 — Commands](https://docs.oracle.com/en/java/javase/24/jshell/commands.html)
- [Oracle Java SE 24 — Editing](https://docs.oracle.com/en/java/javase/24/jshell/editing.html)
- [Oracle Java SE 24 — External Code](https://docs.oracle.com/en/java/javase/24/jshell/external-code.html)
- [Oracle Java SE 24 — Scripts](https://docs.oracle.com/en/java/javase/24/jshell/scripts.html)
- [Oracle Java SE 24 — Feedback Modes](https://docs.oracle.com/en/java/javase/24/jshell/feedback-modes.html)
