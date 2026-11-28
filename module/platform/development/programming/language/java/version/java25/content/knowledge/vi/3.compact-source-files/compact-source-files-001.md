# Mục đích và trạng thái chính thức của compact source files trong Java 25

## 1. Compact source files giải quyết vấn đề gì?

**Compact source files** (tệp nguồn gọn) là cách viết một chương trình Java nhỏ trong tệp `.java` mà không phải mở đầu bằng khai báo `class`. Thay vì yêu cầu người học hiểu ngay `public`, `static`, `String[] args`, class và package, Java cho phép tập trung vào các cấu trúc nền tảng như biến, biểu thức, phương thức, điều kiện và vòng lặp.

Ví dụ chương trình Java 25 có thể chỉ gồm:

```java
// Hello.java — Java 25
void main() {
    IO.println("Xin chào, Java 25!");
}
```

Chạy ngay bằng JDK 25:

```bash
java Hello.java
```

Kết quả:

```text
Xin chào, Java 25!
```

Đây vẫn là **Java**, không phải một ngôn ngữ kịch bản riêng hoặc một chế độ bỏ qua quy tắc kiểu dữ liệu. Trình biên dịch tạo một **class được khai báo ngầm** để chứa phương thức `main`. Chương trình vẫn được biên dịch thành bytecode và chạy trên JVM.

Trong module học **JAVA_VERSION_JAVA25**, mục tiêu là nhận biết những đặc điểm Java 25 đang có giá trị thực tế khi viết chương trình nhỏ, thí nghiệm API và đánh giá khả năng nâng cấp JDK. Đặc biệt, bài này chỉ dùng **cú pháp và quy tắc đã chính thức trong Java 25**, tránh sử dụng cách viết thuộc những bản preview cũ.

### 1.1. Vì sao Java cần một hình thức nguồn ngắn hơn?

Ở các phiên bản trước, bài “Hello World” thường bắt đầu với:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Xin chào!");
    }
}
```

Cấu trúc này vẫn **hợp lệ và phù hợp** khi viết chương trình lớn. Nhưng với người mới hoặc một thí nghiệm vài dòng, nó đưa ra nhiều khái niệm chưa liên quan trực tiếp đến công việc cần làm:

| Thành phần truyền thống | Ý nghĩa trong ứng dụng lớn | Vì sao có thể hoãn ở chương trình nhỏ |
| --- | --- | --- |
| `class Hello` | Định nghĩa kiểu và không gian chứa thành viên | Chưa cần xây dựng một API hay phân lớp |
| `public` | Quy tắc truy cập của class/phương thức | Chưa cần xuất bản API |
| `static` | Thành viên của class thay vì đối tượng | Chưa cần học mô hình đối tượng trước vòng lặp và hàm |
| `String[] args` | Nhận tham số dòng lệnh | Chưa cần khi không đọc argument |
| `package`/`module-info.java` | Tổ chức tên, khả năng tái sử dụng và đóng gói | Chưa cần cho một chương trình độc lập |

Compact source files cho phép **bắt đầu đơn giản rồi tăng dần cấu trúc khi nhu cầu xuất hiện**. Đây là mục đích chính của tính năng: cải thiện trải nghiệm *programming in the small*, không thay thế class, package hoặc Java Platform Module System (JPMS) cho hệ thống lớn.

### 1.2. Những tình huống đáng dùng

- Bài thực hành nhập môn về biến, biểu thức, điều kiện, hàm và vòng lặp.
- Mã chạy thử một API JDK 25, ví dụ `List`, `Map`, `LocalDate`, `Files` hay `Stream`.
- Một tiện ích độc lập để xử lý dữ liệu thử nghiệm, xuất báo cáo ngắn hoặc kiểm tra giả thuyết kỹ thuật.
- Ví dụ trong tài liệu, workshop hoặc phần minh họa không cần bố trí một dự án Maven/Gradle đầy đủ.

**Không có lợi ích mặc định** khi chuyển hàng loạt một codebase Spring Boot, thư viện công khai hoặc ứng dụng chia nhiều package sang compact source files. Những hệ thống đó cần API rõ, namespace và cấu trúc build/test thông thường.

## 2. Trạng thái chính thức trong Java 25

Tính năng được chuẩn hóa bởi **JEP 512 — Compact Source Files and Instance Main Methods** và **trở thành tính năng chính thức (permanent/final) trong Java 25**. Đây là điểm quan trọng nhất khi đánh giá mã có còn áp dụng hiện nay hay không.

| Nội dung | Trạng thái áp dụng với JDK 25 |
| --- | --- |
| Compact source files | **Chính thức**, là cú pháp ngôn ngữ Java |
| Class được khai báo ngầm (implicitly declared class) | **Chính thức**, do trình biên dịch suy ra từ tệp nguồn gọn |
| `void main()` dạng instance | **Chính thức**, là một phương thức `main` có thể được launcher gọi |
| `void main(String[] args)` dạng instance | **Chính thức** |
| Tự import các kiểu public trong package được `java.base` export | **Chính thức** cho compact source file |
| `java.lang.IO` cho nhập/xuất console đơn giản | **Có sẵn trong Java 25** |
| `--enable-preview` chỉ để chạy các ví dụ JEP 512 | **Không cần** với `--release`/JDK 25 |
| Dùng các dạng `java.io.IO` và lời gọi `println(...)` tự động từ bản preview cũ | **Không phải cú pháp/hành vi khuyến nghị của Java 25** |

Tính năng này từng trải qua nhiều bản thử nghiệm, nhưng bài học thực hành Java 25 chỉ dựa trên **hình thức hoàn thiện**. Một thay đổi đáng lưu ý: ở Java 25, lớp tiện ích console là `java.lang.IO`; các phương thức static của nó **không được tự động static-import** vào compact source files. Vì thế ví dụ mới viết `IO.println(...)` hoặc tự `import static java.lang.IO.println;`.

### 2.1. JEP 512 gồm hai khả năng có liên quan nhưng không đồng nhất

1. **Compact source file:** cho phép khai báo phương thức/trường bên ngoài một khai báo `class` tường minh. Trình biên dịch bao chúng trong một class ngầm định.
2. **Instance `main` method:** cho phép dùng `main` không `static`, không bắt buộc `public` và có thể không có tham số `String[]`. Quy tắc launcher về `main` cũng có ích đối với các class khai báo tường minh khi thỏa điều kiện của Java 25.

Không nên hiểu rằng **mọi file có `void main()` đều là compact source file**. Ví dụ sau có class tường minh nên vẫn là nguồn Java thông thường:

```java
// ExplicitApp.java — không phải compact source file
class ExplicitApp {
    void main() {
        IO.println("Đây là một class khai báo tường minh.");
    }
}
```

Ngược lại, trong ví dụ `Hello.java` đầu bài, `main` nằm trực tiếp ở cấp tệp nguồn nên tạo một compact compilation unit.

### 2.2. Java 25 không đòi hỏi cờ preview cho JEP 512

Với JDK 25 được chọn đúng qua `java -version`, các ví dụ trên chạy trực tiếp:

```bash
java --version
java Hello.java
```

Bạn cũng có thể biên dịch rõ ràng bằng `javac`:

```bash
javac Hello.java
java Hello
```

Trong ví dụ đơn giản này, `javac` có thể tạo `Hello.class` và `java Hello` chạy được. Tên class ở bytecode được chọn từ tên tệp bởi công cụ triển khai; **đó không phải tên kiểu mà mã nguồn được phép tham chiếu trực tiếp**. Đối với mục tiêu học tập hoặc tiện ích một tệp, dùng `java Hello.java` là cách rõ ràng, ít phụ thuộc vào chi tiết class ngầm định.

**Phân biệt hai cơ chế:** khả năng chạy trực tiếp tệp `.java` qua launcher là cơ chế *source-file mode*; JEP 512 bổ sung hình thức tệp nguồn gọn và lựa chọn `main` dạng instance. Một chương trình có class tường minh cũng có thể chạy từ nguồn, còn compact source file cũng có thể được biên dịch trước. Đây là các khả năng bổ trợ nhau.

## 3. Bản chất của một compact source file

Khi gặp một phương thức khai báo trực tiếp ở cấp tệp nguồn, `javac` diễn giải các phương thức, trường và khai báo kiểu thành viên ở tệp đó như **thành viên của một class được khai báo ngầm**.

Một ví dụ có thêm phương thức:

```java
// Greeting.java
String greeting(String name) {
    return "Xin chào, " + name + "!";
}

void main() {
    IO.println(greeting("An"));
    IO.println(greeting("Bình"));
}
```

Về mặt ý tưởng, có thể tưởng tượng một class chứa hai phương thức instance này. Đây chỉ là cách giải thích mô hình; **không có yêu cầu lập trình viên tự viết khai báo class đó**.

### 3.1. Đặc điểm của class ngầm định

Theo đặc tả Java 25, class ngầm định được tạo từ compact source file có các đặc điểm:

- Là một **top-level class `final`**, thuộc **unnamed package** và nằm trong **unnamed module**.
- Kế thừa trực tiếp `java.lang.Object`; **không triển khai interface nào** ở khai báo class ngầm định.
- Có một **default constructor không tham số** được khai báo ngầm; không khai báo constructor riêng cho nó.
- Chứa các trường, phương thức, khai báo class/interface thành viên được viết ở cấp tệp.
- Phải có ít nhất một `main` phù hợp với quy tắc khởi chạy của Java; điều kiện này được kiểm tra lúc biên dịch.
- Có tên do môi trường biên dịch xác định, nhưng **không thể dùng tên ấy trong mã nguồn** để tạo đối tượng hoặc khai báo một kiểu khác tham chiếu đến nó.

Class này không phải “vô hình” ở thời gian chạy: JVM vẫn thực thi bytecode của một class. Chỉ là việc khai báo và đặt tên class không xuất hiện trong chương trình nguồn.

### 3.2. Có thể đặt gì ở cấp tệp?

Các khai báo thành viên hợp lệ, chẳng hạn:

```java
// CounterDemo.java
int start = 10;                    // Trường instance

int nextValue() {                  // Phương thức instance
    return start + 1;
}

record Pair(int left, int right) { // Kiểu thành viên
    int sum() {
        return left + right;
    }
}

void main() {
    var pair = new Pair(start, nextValue());
    IO.println(pair.sum());        // 21
}
```

Cách viết này vẫn áp dụng quy tắc kiểu, phạm vi, truy cập và khởi tạo của class Java. `record Pair` là **kiểu thành viên có tên**, được khai báo tường minh bên trong lớp ngầm định. Còn class bao ngoài vẫn không có tên có thể sử dụng trong mã nguồn.

Compact source file **không phải** dạng “câu lệnh nằm tự do ở cấp tệp”. Ví dụ sau không đúng:

```java
// Không hợp lệ: câu lệnh thực thi trực tiếp ở cấp tệp
IO.println("Sai vị trí");
int x = 1;
void main() { }
```

Để chạy một câu lệnh, đặt nó vào `main` hoặc một phương thức/khối khởi tạo thích hợp của một class thông thường. Trong compact source file, các khai báo thành viên ở cấp tệp không cho phép chèn một `if`/`for`/gọi hàm như câu lệnh top-level.

### 3.3. Những giới hạn có chủ đích

| Giới hạn | Hệ quả thực tế |
| --- | --- |
| Không khai báo `package` cho compact source file | Chương trình thuộc unnamed package; bất tiện khi đóng gói thư viện/ứng dụng nhiều package |
| Không thể tham chiếu class ngầm định bằng tên trong Java source | Không dùng nó làm kiểu API, `new Hello()` hoặc kế thừa từ nó |
| Không khai báo constructor hoặc initializer của class bao ở cấp file | Khi cần vòng đời/phân lớp tùy biến, khai báo class tường minh |
| Không tự động trở thành một `module` Java có tên | Không có cơ chế `exports`/`requires` của named module chỉ nhờ tệp gọn |
| Phải có phương thức `main` có thể launch | Tệp này dùng để biểu diễn chương trình độc lập hoặc entry point |
| Không thay thế hoàn toàn tổ chức class/package của codebase | Nên chuyển về cấu trúc class thông thường khi tăng độ phức tạp |

Nếu dự án dựa vào Spring Boot component scanning, package conventions, API công khai, reflection hoặc công cụ build/test giả định tên class, hãy cân nhắc dùng class tường minh. Không nên lấy tính ngắn gọn vài dòng làm mục tiêu vượt lên trên khả năng bảo trì và tính rõ ràng của hệ thống.

## 4. Quy tắc `main` trong Java 25

### 4.1. `main` không còn bắt buộc có hình thức truyền thống

Với chương trình nhỏ, những khai báo sau có thể là entry point hợp lệ khi đáp ứng điều kiện của launcher:

```java
// Lựa chọn A: chương trình không cần command-line arguments
void main() {
    IO.println("Chạy không có tham số.");
}
```

```java
// Lựa chọn B: chương trình cần command-line arguments
void main(String[] args) {
    String name = args.length == 0 ? "bạn" : args[0];
    IO.println("Xin chào, " + name);
}
```

Ngoài phương thức instance, Java 25 vẫn hỗ trợ `static void main(...)`. Và kiểu truyền thống `public static void main(String[] args)` hoàn toàn hợp lệ, **không bị thay thế hay deprecated bởi JEP 512**.

Tệp chứa các phương thức ví dụ trên là **hai tệp độc lập** nếu bạn muốn chạy cả hai; không đặt nhiều đoạn minh họa vào một `.java` rồi kỳ vọng mỗi đoạn tự là một chương trình. Khi muốn thử chọn `main` theo priority, có thể định nghĩa nhiều candidate trong một tệp như ở phần sau.

### 4.2. Launcher lựa chọn phương thức nào?

Với compact source file:

1. Nếu có phương thức `main(String[] args)` hợp lệ, trả về `void` và có thể truy cập, launcher ưu tiên phương thức này.
2. Nếu không có dạng trên, launcher tìm `main()` hợp lệ, trả về `void`.
3. Nếu không có candidate phù hợp, không thể khởi chạy.
4. Với `static main`, launcher gọi trực tiếp; với `instance main`, launcher tạo instance từ default constructor của class ngầm định rồi mới gọi.

Ví dụ kiểm tra thứ tự:

```java
// ChooseMain.java
void main() {
    IO.println("main không tham số");
}

void main(String[] args) {
    IO.println("main có String[] args: " + args.length);
}
```

Khi chạy:

```bash
java ChooseMain.java A B
```

Dòng in ra từ `main(String[] args)`:

```text
main có String[] args: 2
```

Không nên phụ thuộc vào phiên bản preview hay suy đoán rằng mọi `main` ở bất kỳ phạm vi truy cập nào cũng được launcher nhận. Tài liệu tập trung vào các khai báo thông thường có package access và `void` return, đủ để sử dụng trong bài thực hành.

### 4.3. Instance method tương tác với các thành viên như thế nào?

Vì `main` có thể là instance method, nó truy cập trực tiếp trường và helper instance:

```java
// GreetingState.java
String prefix = "Xin chào";

String format(String name) {
    return prefix + ", " + name + "!";
}

void main(String[] args) {
    String target = args.length > 0 ? args[0] : "Java 25";
    IO.println(format(target));
}
```

Trên source code, bạn không phải viết `new GreetingState()`. Launcher chịu trách nhiệm tạo instance của class ngầm định. Sự thuận tiện này **không có nghĩa Java không còn đối tượng**: bên dưới vẫn là một object có trường `prefix`, phương thức `format` và `main`.

## 5. Import tự động từ `java.base` và `java.lang.IO`

### 5.1. Tệp gọn có import `java.base` ngầm định

Ở Java 25, compact source file tự động nhập các **public top-level types** trong những package do module `java.base` export, tương tự như có:

```java
import module java.base;
```

Điều này được hỗ trợ bởi tính năng **module import declarations** (JEP 511), vốn cũng đã chính thức trong Java 25. Với compact source file, bạn **không cần tự khai báo** dòng đó.

Ví dụ sử dụng trực tiếp `List`, `LocalDate`, `Comparator` và `Collectors` mà không cần các import `java.util.*` hoặc `java.time.*`:

```java
// Names.java — compact source file Java 25
void main() {
    List<String> names = List.of("Lan", "Bình", "An");

    var sorted = names.stream()
            .sorted(Comparator.naturalOrder())
            .collect(Collectors.toList());

    IO.println("Ngày chạy: " + LocalDate.now());
    IO.println("Tên theo thứ tự: " + sorted);
}
```

Chạy:

```bash
java Names.java
```

**Giới hạn của import tự động:** chỉ áp dụng các kiểu `public` ở package được `java.base` export. Nó **không** tự import mọi kiểu của mọi module JDK hoặc thư viện ngoài. Ví dụ `HttpClient` thuộc `java.net.http`, vì vậy cần import theo quy tắc thông thường:

```java
// HttpTypeDemo.java
import java.net.http.HttpClient;

void main() {
    HttpClient client = HttpClient.newHttpClient();
    IO.println(client.version());
}
```

Ví dụ này chỉ tạo một HTTP client trong bộ nhớ, **không thực hiện request mạng**.

Ở source file có `class` tường minh, không được mặc định tự có import `java.base` theo cơ chế compact source file. Bạn vẫn có thể chủ động viết `import module java.base;` (JEP 511) hoặc `import java.util.List;` tùy tiêu chuẩn dự án.

### 5.2. `IO` ở đúng package của Java 25

`java.lang.IO` cung cấp các hàm nhập/xuất dòng đơn giản, giúp chương trình nhỏ dễ đọc:

| Hàm | Công dụng |
| --- | --- |
| `IO.println(value)` | In giá trị với kết thúc dòng |
| `IO.print(value)` | Hiển thị giá trị/prompt |
| `IO.readln(prompt)` | Hiển thị prompt rồi đọc một dòng từ console |
| `IO.readln()` | Đọc một dòng từ console |

Ví dụ người dùng nhập tên:

```java
// AskName.java
void main() {
    String name = IO.readln("Tên của bạn: ");

    if (name == null || name.isBlank()) {
        IO.println("Chưa nhập tên.");
        return;
    }

    IO.println("Xin chào, " + name.trim() + "!");
}
```

Khi input đã đến cuối luồng (EOF), `readln` có thể không có giá trị hợp lệ; ví dụ kiểm tra `null` trước khi xử lý. Với chương trình sản xuất cần quản lý encoding, stream, lỗi I/O và test tự động ở mức chi tiết hơn, `BufferedReader`, `PrintStream`, `Files` và các API I/O chuyên dụng vẫn quan trọng.

**Quy tắc hiện hành:** mặc dù `IO` nằm trong `java.lang` (được nhập như các kiểu phổ biến trong `java.lang`), **phương thức static của `IO` không được nhập tự động**. Cách gọi chuẩn trong Java 25 là:

```java
void main() {
    IO.println("Đúng với Java 25.");
}
```

Nếu muốn gọi trực tiếp `println(...)` thì tự import tường minh:

```java
import static java.lang.IO.println;

void main() {
    println("Có thể dùng khi đã explicit static import.");
}
```

Tránh chép nguyên ví dụ preview cũ dùng `java.io.IO` hoặc gọi `println(...)` mà không có static import. Các ví dụ đó không phản ánh quy tắc Java 25 đã được hoàn thiện.

### 5.3. Import ngầm không thay quy tắc xử lý tên

Nhiều package có thể chứa kiểu cùng tên. Khi viết mã có import module và gặp tên mơ hồ, hãy dùng **fully qualified name** hoặc import kiểu tường minh để làm rõ. Đừng hiểu import ngầm là trình biên dịch tự biết người dùng muốn kiểu nào khi có xung đột.

Ví dụ chủ động nêu rõ kiểu trong chương trình nhỏ:

```java
void main() {
    java.util.List<String> values = java.util.List.of("A", "B");
    IO.println(values.size());
}
```

Nếu mã bắt đầu dùng nhiều thư viện, phụ thuộc third-party và namespace phức tạp, cấu trúc class/package tường minh thường dễ review hơn cách tối ưu số dòng import.

## 6. Hướng dẫn thực hành với một tệp Java 25

### 6.1. Kiểm tra đúng JDK

Yêu cầu **JDK 25** hoặc bản JDK mới tương thích với những tính năng đã được chuẩn hóa trong Java 25. Lệnh `java` và `javac` phải trỏ đến toolchain tương ứng.

```bash
java --version
javac --version
```

Khi dòng đầu cho thấy Java 25 nhưng `javac` là bản cũ, việc chạy mã có thể thành công mà biên dịch trong IDE/CI lại lỗi. Hãy cấu hình thống nhất JDK của terminal, IDE và build system.

### 6.2. Viết tiện ích đếm dòng văn bản

Mã sau dùng `Path`, `Files` và `List` — các kiểu thuộc `java.base` — để đọc một tệp UTF-8 và đếm số dòng chứa nội dung. Nó sử dụng `main(String[] args)` vì cần tên tệp từ dòng lệnh.

```java
// CountLines.java
void main(String[] args) throws Exception {
    if (args.length != 1) {
        IO.println("Cách dùng: java CountLines.java <duong-dan-tep>");
        return;
    }

    Path path = Path.of(args[0]);

    if (!Files.isRegularFile(path)) {
        IO.println("Không tìm thấy tệp hợp lệ: " + path);
        return;
    }

    long count;
    try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
        count = lines.filter(line -> !line.isBlank()).count();
    }

    IO.println("Số dòng có nội dung: " + count);
}
```

Cách dùng:

```bash
java CountLines.java notes.txt
```

Các kiểu `Path`, `Files`, `StandardCharsets` và `Stream` đều thuộc package export bởi `java.base`, vì vậy không phải viết `import` riêng trong **compact source file**.

Đoạn mã này là bài thực hành phù hợp cho tệp thử nghiệm nhỏ. Với tệp rất lớn, cách xử lý streaming như `Files.lines(...)` tránh tải mọi dòng vào một `List`, và `try-with-resources` bảo đảm đóng luồng. Khi đưa thành tiện ích vận hành chính thức, cần thêm xử lý `IOException` cụ thể, logging, chính sách đường dẫn và kiểm thử trên dữ liệu không tin cậy.

### 6.3. Biên dịch riêng khi cần

Không nhất thiết phải dùng `java File.java`; bạn vẫn có thể chạy quy trình biên dịch:

```bash
javac CountLines.java
java CountLines notes.txt
```

Nhưng đừng gắn tên class ngầm định vào một API hoặc plugin contract. Với công cụ cần main class có tên rõ ràng, package namespace, hoặc framework phát hiện entry point bằng reflection, cách tốt hơn là **khai báo class tường minh**.

### 6.4. Những dấu hiệu cho thấy nên chuyển sang class thông thường

Khi ứng dụng bắt đầu có nhiều nhiệm vụ hoặc cần tái sử dụng, cân nhắc chuyển:

- Muốn xuất bản API có tên class/package ổn định cho các module khác.
- Có nhiều entity/value object, dependency injection, kiểm thử chuyên biệt và lớp adapter.
- Cần build artifact, lifecycle hooks, logging và packaging rõ ràng.
- Tổ chức nhiều source files dưới các named packages để quản lý quyền truy cập và trách nhiệm.
- Muốn integration với Spring Boot, annotation scanning hoặc build plugin yêu cầu class có tên.

Chuyển dần không đòi hỏi viết lại logic. Giả sử mã nguồn gọn:

```java
// Greeter.java
String message(String name) {
    return "Xin chào, " + name;
}

void main() {
    IO.println(message("Java"));
}
```

Bạn có thể khai báo class và package tường minh:

```java
// src/main/java/com/example/tools/Greeter.java
package com.example.tools;

public final class Greeter {
    private String message(String name) {
        return "Xin chào, " + name;
    }

    public static void main(String[] args) {
        var app = new Greeter();
        IO.println(app.message("Java"));
    }
}
```

Phương thức `main` truyền thống trong ví dụ cuối là lựa chọn tổ chức quen thuộc cho tooling; **Java 25 vẫn cho phép instance main trong class tường minh theo quy tắc launcher**. Mục đích ở đây là minh họa ranh giới giữa một chương trình học độc lập và một class có namespace rõ ràng.

## 7. Những hiểu nhầm cần tránh khi nâng cấp lên Java 25

### 7.1. Compact source file không phải JavaScript hay JShell

Đừng coi tệp nguồn gọn là một “script mode” có thể đặt câu lệnh tùy ý ở cấp file. Mọi phương thức/trường vẫn là thành viên của class ngầm định, chương trình phải tuân thủ kiểm tra kiểu Java và có `main` hợp lệ.

| Đặc tính | Compact source file Java 25 | JShell | Class Java tường minh |
| --- | --- | --- | --- |
| Dạng sử dụng thường gặp | Tệp `.java` chạy được bằng `java File.java` | Phiên làm việc REPL tương tác | File class trong ứng dụng |
| Phải viết class bao ngoài | Không | Không bắt buộc trong snippet | Có |
| `main` launchable | Cần cho tệp compact | Không cần để nhập từng snippet | Cần nếu đây là entry point |
| Có thể chứa lệnh tùy ý ở cấp tệp | Không | Snippet hỗ trợ biểu thức/câu lệnh | Không |
| Phù hợp làm API công khai có package | Không | Không | Có |
| Tự import exported public types của `java.base` | Có | Có quy tắc import riêng của JShell | Không tự động chỉ vì có `class` |

Nếu chỉ muốn gõ vài biểu thức rồi quan sát kết quả tức thời, JShell có thể phù hợp. Nếu muốn lưu bài tập, commit vào Git và chạy lại bằng CLI, compact source file thường dễ chia sẻ hơn. Với hệ thống có cấu trúc, class và package tường minh vẫn là lựa chọn thích hợp.

### 7.2. Đừng chép hành vi của preview cũ

| Dễ gặp khi đọc tài liệu cũ | Cách hiểu phù hợp với Java 25 |
| --- | --- |
| Gọi tính năng là “Unnamed Classes and Instance Main Methods” như trạng thái chưa hoàn thiện | Tên chuẩn trong Java 25 là **Compact Source Files and Instance Main Methods**, JEP 512 |
| Yêu cầu `--enable-preview` cho tính năng này | **Không cần** trên JDK 25 khi sử dụng JEP 512 |
| Nhắc đến `java.io.IO` | Dùng `java.lang.IO` |
| Dùng `println("...")` trần mà không import | Dùng `IO.println("...")` hoặc explicit static import |
| Cho rằng `void main()` chỉ dùng trong bản demo thử nghiệm | Dạng `main` này đã chính thức |
| Cho rằng viết tệp gọn làm Java không tạo class | Trình biên dịch tạo class ngầm định; vẫn là JVM bytecode |
| Cho rằng mọi package/module đều được auto-import | Chỉ `java.base` với các kiểu public trong package được export |

Các JEP preview trước đây có giá trị **lịch sử thiết kế**, nhưng không phải chuẩn để dạy API/cú pháp của Java 25. Khi sao chép ví dụ, luôn ưu tiên đặc tả Java SE 25 hoặc phiên bản JDK đang dùng, nhất là nơi dùng `IO` và import.

### 7.3. Phân biệt lỗi cú pháp với lỗi toolchain

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `javac` báo không nhận `void main()` ở cấp file | Compiler cũ hoặc `--release` thấp hơn 25 | Dùng toolchain JDK 25 cho bài này |
| `cannot find symbol: IO` | Đang dùng source/JDK trước Java 25 hoặc cấu hình compiler khác | Kiểm tra `java --version`, `javac --version` và target release |
| Gọi `println("...")` không có import báo lỗi | Java 25 không auto static-import `IO` | Đổi thành `IO.println(...)` |
| `cannot find symbol: List` trong class thông thường | Import `java.base` ngầm chỉ dành cho compact file | Thêm `import java.util.List;` hoặc `import module java.base;` |
| Tệp chỉ chứa `int x = 3;` nhưng không có `main` | Không có launchable `main` trong compact class | Định nghĩa `void main()` |
| Viết `IO.println(...)` trực tiếp ngoài method | Đặt một câu lệnh ở cấp file | Chuyển lời gọi vào `main` |
| Có `package com.example;` trong file gọn | Compact compilation unit không có package declaration | Chuyển thành class tường minh nếu cần package |
| `new Hello()` trong mã nguồn báo lỗi dù có `Hello.class` | Tên implicit class là chi tiết của công cụ, không tham chiếu được trong source | Dùng class tường minh khi cần new/inherit/reuse |
| Lỗi module/classpath khi import thư viện ngoài | Import ngầm `java.base` không tải dependency hay resolve mọi module khác | Cấu hình classpath/module path và import đúng |
| IDE đánh dấu đỏ nhưng CLI JDK25 chạy được | IDE language level/compiler khác JDK terminal | Chỉnh Project SDK, language level và build toolchain |

**Lưu ý khi dùng `--release`:** JDK 25 vẫn có thể biên dịch cho release cũ, nhưng cú pháp mới của Java 25 không tự trở thành hợp lệ với `--release 17` hoặc `--release 21`. Sử dụng đúng target tùy thư viện/ứng dụng cần hỗ trợ JVM nào; không vô tình đưa Java 25 syntax vào module vẫn phải biên dịch cho Java 17.

### 7.4. Khi nào không nên dùng?

Cân nhắc **class tường minh** cho:

- Ứng dụng Spring Boot có `@SpringBootApplication`, controllers, services, repositories và component scanning.
- Thư viện xuất bản những kiểu public cho người dùng khác.
- Dự án JPMS có module descriptor và các package được xuất bản có chủ đích.
- Nhiều chương trình chung một workspace cần conventions, test fixtures và các extension points cụ thể.
- Hệ thống mà build plugin, reflection hoặc deployment descriptor phải tham chiếu main class bằng tên ổn định.

Điểm này không phủ nhận Java 25 hiện đại: **tính năng mới đem lại một lựa chọn ngắn gọn**, còn class/package/module vẫn là cách tổ chức chính của ứng dụng lớn. Không nên đề xuất chuyển mã nguồn đang vận hành ổn định sang compact file chỉ để giảm số dòng.

## 8. Bài thực hành: chọn đúng hình thức nguồn

### 8.1. Bài 1 — Chương trình nhập môn

Viết `Welcome.java` có một `void main()`, nhập tên người dùng bằng `IO.readln(...)`, kiểm tra đầu vào rỗng và in lời chào bằng `IO.println(...)`. Chạy bằng `java Welcome.java`.

**Tiêu chí hoàn thành:** không cần `class`, không cần `--enable-preview`, xử lý trường hợp chưa nhập tên mà không ném `NullPointerException`.

### 8.2. Bài 2 — Đọc đối số dòng lệnh

Tạo `Sum.java` đọc hai số nguyên từ `String[] args` và in tổng. Kiểm tra số lượng đối số, báo lỗi có ý nghĩa khi `Integer.parseInt` ném `NumberFormatException`.

Gợi ý khung chương trình:

```java
// Sum.java
void main(String[] args) {
    if (args.length != 2) {
        IO.println("Cách dùng: java Sum.java <a> <b>");
        return;
    }

    try {
        int left = Integer.parseInt(args[0]);
        int right = Integer.parseInt(args[1]);
        IO.println("Tổng: " + Math.addExact(left, right));
    } catch (NumberFormatException ex) {
        IO.println("Hai đối số phải là số nguyên hợp lệ.");
    } catch (ArithmeticException ex) {
        IO.println("Tổng vượt phạm vi int.");
    }
}
```

Chạy:

```bash
java Sum.java 7 35
```

Kết quả dự kiến:

```text
Tổng: 42
```

Bài này xác nhận `main(String[] args)` có thể là **instance method**, không cần viết `public static`.

### 8.3. Bài 3 — Import tự động và import có chủ đích

Tạo compact `Today.java` để in `LocalDate.now()` và danh sách `List.of("A", "B")`, không viết `import`. Sau đó thử dùng `HttpClient` từ `java.net.http`: thêm `import java.net.http.HttpClient;`. Giải thích vì sao JDK có lớp `HttpClient` nhưng nó không xuất hiện nhờ import ngầm `java.base`.

**Tiêu chí hoàn thành:** phân biệt `java.base` (tự import trong tệp gọn) với một module JDK khác (phải import và cần môi trường module/classpath phù hợp).

### 8.4. Bài 4 — Chuyển thành chương trình có cấu trúc

Bắt đầu với `Greeter.java` chỉ có `String message(String)` và `void main()`. Sau đó chuyển sang `package com.example.tools`, khai báo `class Greeter`, tách logic vào phương thức có phạm vi truy cập phù hợp và kiểm tra build/entry point.

So sánh:

- Compact file giúp giảm phần khai báo ban đầu.
- Class tường minh làm tên API và package rõ ràng.
- Cả hai là Java 25 hợp lệ; ưu tiên tùy quy mô và mục đích.

### 8.5. Câu hỏi tự kiểm tra

1. Từ Java 25, JEP nào hoàn thiện compact source files và instance `main`?
2. Một file `void main() { IO.println("Hi"); }` có cần `--enable-preview` trên JDK25 không?
3. Chương trình không viết `class` thì có thật sự không có class khi chạy trên JVM không?
4. Một compact source file thuộc package/module nào?
5. Có thể tạo một instance của implicit class bằng `new Hello()` ngay trong source không?
6. Tại sao `List` có thể dùng không cần import nhưng `java.net.http.HttpClient` cần import?
7. Trong Java 25, khác biệt giữa `IO.println("A")` và `println("A")` khi chưa explicit static import là gì?
8. Khi đồng thời có `void main()` và `void main(String[] args)` hợp lệ, launcher chọn phương thức nào?
9. Chạy `java Hello.java` khác thế nào về mục đích với viết `void main()`?
10. Khi cần đưa code vào Spring Boot application hoặc publish một thư viện nhiều package, nên chọn tệp nguồn gọn hay class tường minh, và vì sao?

## 9. Tài liệu chính thức và phạm vi áp dụng

Bài học sử dụng quy tắc **chính thức của Java 25**. Để đối chiếu khi nâng cấp toolchain hoặc làm code review, đọc trực tiếp:

- **JEP 512 — Compact Source Files and Instance Main Methods:** https://openjdk.org/jeps/512
- **Oracle Java SE 25 Language Guide — Compact Source Files and Instance Main Methods:** https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html
- **Java SE 25 Language Changes by Release:** https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html
- **Java Language Specification, Java SE 25 — `7.3 Compilation Units:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3
- **Java Language Specification, Java SE 25 — `8.1.8 Implicitly Declared Classes:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.8

Các quy tắc cốt lõi cần giữ khi viết mã Java 25 là: **compact source file có class ngầm định và `main` hợp lệ; class đó nằm trong unnamed package; `java.base` được import tự động theo quy tắc module import; và I/O đơn giản dùng `java.lang.IO` với tên lớp rõ ràng hoặc static import tường minh**. Đây là những khả năng đã hoàn thiện, phù hợp để dạy và ứng dụng trong các chương trình Java nhỏ hiện đại.

Không cần học lại cú pháp preview đã bị thay đổi để viết Java 25. Khi hệ thống phát triển thành một ứng dụng nhiều module hoặc API có tên công khai, tiếp tục sử dụng class, package và module theo thiết kế thông thường, đồng thời giữ các kiến thức Java 25 còn phù hợp ở những chương trình nhỏ và công cụ thực hành.


