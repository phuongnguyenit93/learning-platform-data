# Các import ngầm định và sử dụng lớp java.lang.IO trên JDK hỗ trợ bản chính thức

## Trạng thái tính năng trên JDK hiện hành

Trong module `JAVA_VERSION_JAVA22`, nội dung này tập trung vào cách viết chương trình Java nhỏ gọn nhưng vẫn phù hợp với JDK hiện đại. Compact Source Files và Instance Main Methods được hoàn thiện theo JEP 512 và trở thành tính năng ngôn ngữ chính thức từ JDK 25. Tại thời điểm hiện tại, JDK 27 là feature release mới nhất và JDK 25 là LTS mới nhất; cú pháp trong bài dùng phiên bản stable từ JDK 25 trở lên, không cần bật `--enable-preview`.

JEP 512 không chỉ cho phép bỏ phần khai báo lớp bao quanh các thành viên của một chương trình nhỏ. Tính năng còn bổ sung cơ chế tự động import các kiểu trong module `java.base` cho compact source files và giới thiệu lớp `java.lang.IO` để đọc, ghi console theo dòng.

## 1. Compact source file là gì?

Compact source file là tệp Java có các khai báo thành viên như field, method, class hoặc interface ở cấp cao nhất của tệp, không đặt bên trong một khai báo `class` tường minh. Compiler ngầm khai báo một lớp top-level để chứa những thành viên đó.

Ví dụ chương trình Java truyền thống:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
```

Với compact source file, có thể viết:

```java
void main() {
    IO.println("Hello, Java!");
}
```

Lớp được khai báo ngầm là lớp `final`, thuộc unnamed package, kế thừa `Object`, có constructor mặc định không tham số và chứa các field/method viết trực tiếp trong tệp. Lớp này phải có một launchable `main` method. Trong ví dụ, `main` là instance method; Java launcher tạo instance của lớp ngầm định rồi gọi method đó.

Có thể chạy trực tiếp tệp nguồn bằng JDK 25 trở lên:

```bash
java Hello.java
```

Compact source file phù hợp với bài học, script nhỏ, ví dụ minh họa và tiện ích đơn giản. Khi chương trình cần API công khai, package rõ ràng, nhiều lớp được tái sử dụng hoặc kiến trúc module, hãy chuyển sang khai báo lớp và package tường minh.

## 2. Hai cơ chế import ngầm định cần phân biệt

Java có hai cơ chế khác nhau:

1. **Import ngầm định package `java.lang`:** source file thông thường có sẵn các kiểu trong `java.lang` bằng tên đơn giản. Vì vậy, những kiểu như `String`, `Math`, `System`, `Object` và `IO` không cần import tường minh.
2. **Import ngầm định module `java.base`:** compact source file tự động import theo nhu cầu tất cả public top-level class và interface trong các package được `java.base` export, như thể có `import module java.base;`. Cơ chế này cũng làm cho các kiểu trong `java.lang` có thể được dùng bằng tên đơn giản trong compact source file.

Ví dụ, compact source file sau không cần viết import cho `List`, `Map`, `Stream`, `Collectors` hoặc `Function`:

```java
List<String> languages = List.of("Java", "Kotlin", "Scala");

void main() {
    Map<String, Integer> lengths = languages.stream()
        .collect(Collectors.toMap(
            Function.identity(),
            String::length
        ));

    IO.println(lengths);
}
```

Các kiểu `List`, `Map`, `Collectors` và `Function` nằm trong các package được `java.base` export. `String` và `IO` thuộc `java.lang`. Đây là các import theo nhu cầu (on-demand): compiler cho phép dùng tên đơn giản của các kiểu phù hợp, không chèn một khai báo import riêng cho từng class.

### Những package nào được tự động import?

`java.base` là module nền tảng được mọi chương trình Java sử dụng. Nó export nhiều package thường gặp như:

| Package | Một số kiểu có thể dùng trực tiếp trong compact source file |
| --- | --- |
| `java.lang` | `String`, `Math`, `System`, `IO`, `Object`, `RuntimeException` |
| `java.util` | `List`, `Map`, `Set`, `Optional`, `UUID`, `Scanner` |
| `java.util.function` | `Function`, `Predicate`, `Consumer`, `Supplier` |
| `java.util.stream` | `Stream`, `Collectors`, `IntStream`, `LongStream` |
| `java.nio.file` | `Path`, `Files`, `FileSystem`, `StandardWatchEventKinds` |
| `java.time` | `LocalDate`, `LocalDateTime`, `Instant`, `Duration` |
| `java.math` | `BigDecimal`, `BigInteger`, `RoundingMode` |

Danh sách trên chỉ là ví dụ, không phải toàn bộ `java.base`. Điều kiện là kiểu phải là public top-level class hoặc interface nằm trong package được module export.

### Những package không được tự động import

Compact source file không tự động import mọi module của JDK. Các package thuộc module khác như `java.sql`, `java.desktop` hoặc module thư viện bên ngoài vẫn cần import tường minh và module tương ứng phải được đọc bởi chương trình.

Ví dụ, nếu cần `Connection` từ JDBC, có thể import kiểu cụ thể:

```java
import java.sql.Connection;
import java.sql.DriverManager;

void main() throws Exception {
    try (Connection connection = DriverManager.getConnection(
            "jdbc:your-driver:your-database")) {
        IO.println(connection.getMetaData().getDatabaseProductName());
    }
}
```

Hoặc trên JDK 25 trở lên, có thể dùng module import declaration nếu muốn import các package được module export:

```java
import module java.sql;

void main() {
    // Có thể dùng tên đơn giản của các kiểu public được module java.sql
    // và các module mà nó đọc gián tiếp export.
}
```

Module import declaration là tính năng riêng theo JEP 511, đã stable từ JDK 25. Trong compact source file, `java.base` đã được import tự động nên không cần viết thêm `import module java.base;`.

## 3. Lớp java.lang.IO

`java.lang.IO` là lớp `public final` cung cấp các phương thức static đơn giản để đọc và ghi console theo dòng. Lớp này được bổ sung trong JDK 25 theo JEP 512 và thuộc module `java.base`.

Vì `IO` thuộc package `java.lang`, tên lớp `IO` có sẵn bằng tên đơn giản trong mọi source file: source file thông thường có import ngầm định `java.lang`, còn compact source file tự động import module `java.base`. Không cần viết:

```java
import java.lang.IO; // Không cần thiết
```

Điểm cần nhớ: **lớp `IO` được import ngầm định, nhưng các phương thức static của nó không được import ngầm định.** Vì vậy, cú pháp hiện hành là `IO.println(...)`, `IO.print(...)` hoặc `IO.readln(...)`.

### Các phương thức chính

| Phương thức | Chức năng |
| --- | --- |
| `IO.print(Object)` | Ghi biểu diễn chuỗi của đối tượng ra standard output, không thêm ký tự xuống dòng. |
| `IO.println(Object)` | Ghi biểu diễn chuỗi của đối tượng và thêm line separator. |
| `IO.println()` | Chỉ ghi line separator. |
| `IO.readln()` | Đọc một dòng từ standard input. |
| `IO.readln(String prompt)` | Ghi lời nhắc, sau đó đọc một dòng từ standard input. |

Các phương thức đọc trả về `String`. Nếu đã đến cuối luồng trước khi đọc được ký tự nào, `readln()` trả về `null`. Khi có lỗi I/O, phương thức có thể ném `IOError`.

### Ví dụ đọc tên người dùng

Tệp `Greeting.java`:

```java
void main() {
    String name = IO.readln("Tên của bạn: ");

    if (name == null) {
        IO.println("Không còn dữ liệu đầu vào.");
        return;
    }

    name = name.strip();
    if (name.isEmpty()) {
        IO.println("Bạn chưa nhập tên.");
        return;
    }

    IO.println("Xin chào, " + name + "!");
}
```

Chạy:

```bash
java Greeting.java
```

`IO.readln("Tên của bạn: ")` hiển thị prompt rồi chờ một dòng. Sau khi đọc, chương trình kiểm tra EOF và chuỗi rỗng trước khi tạo lời chào.

### Ví dụ nhập nhiều giá trị

```java
void main() {
    String first = IO.readln("Số thứ nhất: ");
    String second = IO.readln("Số thứ hai: ");

    if (first == null || second == null) {
        IO.println("Thiếu dữ liệu đầu vào.");
        return;
    }

    try {
        int a = Integer.parseInt(first.strip());
        int b = Integer.parseInt(second.strip());
        IO.println("Tổng = " + (a + b));
    } catch (NumberFormatException e) {
        IO.println("Vui lòng nhập số nguyên hợp lệ.");
    }
}
```

`Integer` thuộc `java.lang`, vì vậy không cần import. Ví dụ cũng dùng `IO.println` để hiển thị cả kết quả và thông báo lỗi.

## 4. Sử dụng IO trong source file thông thường

`IO` không phải tính năng chỉ dành cho compact source file. Vì `java.lang.*` được import ngầm định trong mọi source file, một class thông thường cũng có thể gọi `IO.println` mà không cần import `java.lang.IO`.

```java
import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi");
        IO.println(names);
    }
}
```

Trong ví dụ này, `List` vẫn cần import vì source file thông thường không tự động import toàn bộ `java.base`. `IO` dùng được trực tiếp vì nó thuộc `java.lang`.

Nếu dùng JDK 25 trở lên, source file thông thường có thể khai báo module import một cách tường minh:

```java
import module java.base;

public class Main {
    public static void main(String[] args) {
        IO.println(List.of("An", "Bình", "Chi"));
    }
}
```

Đây là import được viết rõ trong source file thông thường. Compact source file đã có hiệu ứng tương đương cho `java.base` mà không cần khai báo này.

## 5. Có thể import static các phương thức của IO không?

Có. Mặc dù các phương thức static không được tự động import, Java vẫn cho phép static import tường minh:

```java
import static java.lang.IO.println;

void main() {
    println("Hello from static import");
}
```

Hoặc import tất cả static member:

```java
import static java.lang.IO.*;

void main() {
    println("Hello");
    print("Nhập tên: ");
    String name = readln();
    println("Xin chào " + name);
}
```

Static import là lựa chọn tường minh do lập trình viên viết. Trong tài liệu hướng dẫn và chương trình có nhiều API, cách gọi `IO.println(...)` thường dễ đọc hơn vì người xem nhận ra ngay nguồn của phương thức.

## 6. Lưu ý về encoding và việc đọc System.in

Các phương thức `IO.readln` đọc byte từ `System.in` và giải mã thành ký tự. Charset được chọn theo system property `stdin.encoding`; nếu property không tồn tại hoặc charset chỉ định không tải được, UTF-8 được dùng làm mặc định.

Việc thiết lập bộ giải mã diễn ra ở lần gọi `readln` đầu tiên. Quá trình đọc có thể buffer thêm byte ngoài phần đã chuyển thành chuỗi trả về. Do đó, sau khi đã gọi `IO.readln`, việc tiếp tục đọc `System.in` bằng cách khác có hành vi không được đặc tả.

Ví dụ, tránh trộn hai cách đọc sau trong cùng một luồng nhập:

```java
void main() {
    String name = IO.readln("Tên: ");
    Scanner scanner = new Scanner(System.in); // Không nên trộn cách đọc này
}
```

Hãy chọn một cơ chế đọc cho standard input. `IO.readln` phù hợp với chương trình nhỏ cần đọc từng dòng; với parser phức tạp, đọc token, đọc dữ liệu nhị phân hoặc quản lý encoding chi tiết, dùng API I/O phù hợp như `BufferedReader`, `Scanner` hoặc `InputStream` từ đầu chương trình.

## 7. Những thay đổi quan trọng so với các bản preview

Compact Source Files và Instance Main Methods từng được preview nhiều lần trước khi hoàn thiện. Một số cú pháp trong ví dụ preview cũ không còn là cách dùng mặc định trên JDK hiện hành.

| Phiên bản | Trạng thái |
| --- | --- |
| JDK 21 | Preview đầu tiên: JEP 445. |
| JDK 22 | Preview tiếp theo: JEP 463. |
| JDK 23 | Preview tiếp theo: JEP 477. |
| JDK 24 | Preview tiếp theo: JEP 495. |
| JDK 25 | Stable: JEP 512; `IO` chuyển sang package `java.lang`, static methods không còn được import ngầm định. |
| JDK 26 và 27 | Tiếp tục dùng tính năng stable của JDK 25. |

Trong các bản preview trước JDK 25, lớp I/O từng nằm trong package `java.io` và các static method được import ngầm định trong compact source file. Từ JDK 25, lớp chính thức là `java.lang.IO`, implementation dựa trên `System.in` và `System.out`, và lời gọi phương thức phải ghi rõ tên lớp hoặc có static import tường minh.

Mã preview cũ dạng:

```java
void main() {
    println("Hello");
}
```

nên được chuyển thành dạng hiện hành:

```java
void main() {
    IO.println("Hello");
}
```

Không dùng `java.io.IO` hoặc dựa vào static import ngầm định của preview cũ trong mã mới.

## 8. Xử lý tên kiểu bị trùng khi import nhiều module

Import ngầm định `java.base` giúp giảm số dòng import, nhưng nếu compact source file còn import thêm module khác thì hai module có thể export các kiểu trùng tên đơn giản.

Ví dụ, `java.util.List` trong `java.base` và `java.awt.List` trong `java.desktop` cùng có tên đơn giản `List`. Nếu viết:

```java
import module java.desktop;

void main() {
    List<String> names = List.of("Java"); // Có thể mơ hồ với java.awt.List
}
```

compiler có thể báo tên `List` mơ hồ. Hãy import tường minh kiểu cần dùng để giải quyết:

```java
import module java.desktop;
import java.util.List;

void main() {
    List<String> names = List.of("Java");
    IO.println(names);
}
```

Single-type import có thể shadow tên kiểu được đưa vào bằng module import. Khi có nhiều module, không nên import toàn bộ nếu chỉ cần một vài class; import tường minh giúp code dễ đọc và tránh xung đột tên.

## 9. Khi nào nên dùng java.lang.IO?

| Nhu cầu | Lựa chọn |
| --- | --- |
| In một dòng kết quả hoặc thông báo đơn giản | `IO.println(...)` |
| In prompt không xuống dòng | `IO.print(...)` hoặc `IO.readln(prompt)` |
| Đọc một dòng từ bàn phím trong ví dụ nhỏ | `IO.readln()` hoặc `IO.readln(prompt)` |
| Đọc dữ liệu có cấu trúc, token hoặc cần tùy chỉnh encoding | `BufferedReader`, `Scanner` hoặc API I/O chuyên dụng |
| Dùng `List`, `Map`, `Stream` trong compact source file | Không cần import riêng vì compact source file tự động import `java.base` |
| Dùng package từ module khác | Import tường minh hoặc dùng module import declaration phù hợp |

`java.lang.IO` hướng đến console I/O cơ bản theo dòng. Nó giúp ví dụ học tập ngắn gọn, nhưng không thay thế các API I/O đầy đủ khi chương trình cần kiểm soát buffering, encoding, tokenization, file hoặc luồng nhị phân.

## Kết luận

Trên JDK 25 trở lên, Compact Source Files và Instance Main Methods đã là tính năng stable theo JEP 512. Compact source file tự động import các public top-level type thuộc package được `java.base` export; mọi source file đều có `java.lang.*` ngầm định. Vì `IO` nằm trong `java.lang`, có thể gọi `IO.println`, `IO.print` và `IO.readln` mà không cần import class. Các static method của `IO` không được import ngầm định, nên phải ghi `IO.` hoặc dùng static import tường minh. Hãy phân biệt cơ chế này với các bản preview JDK 21–24 để tránh mang cú pháp cũ sang ứng dụng hiện hành.

## Tài liệu tham khảo

- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)
- [Java SE 27 — Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/27/language/compact-source-files-instance-main-methods.html)
- [Java SE 27 — Module Import Declarations](https://docs.oracle.com/en/java/javase/27/language/module-import-declarations.html)
- [Java SE 27 — java.lang.IO API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/IO.html)
- [Java SE 27 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
- [JEP 511: Module Import Declarations](https://openjdk.org/jeps/511)
