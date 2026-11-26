# Từ JEP 463 trong Java 22 tới Compact Source Files chính thức từ JDK 25

## Mục tiêu của tính năng

Một chương trình Java nhỏ thường phải bắt đầu bằng khá nhiều cấu trúc mà người mới học chưa cần dùng ngay:

```java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
```

Để in một dòng chữ, người học đã phải làm quen với khai báo lớp, access modifier `public`, phương thức `static` và tham số `String[]`. Các cấu trúc này cần thiết trong nhiều chương trình thực tế, nhưng chúng có thể làm lu mờ những kiến thức đầu tiên như biến, biểu thức, điều kiện, vòng lặp và phương thức.

**Compact Source Files** cùng **Instance Main Methods** cho phép viết một chương trình nhỏ bằng các khai báo ở cấp cao nhất của file. Trình biên dịch vẫn tạo một lớp Java ở phía sau; người viết chỉ không phải khai báo lớp đó ngay từ đầu. Đây vẫn là Java, không phải một ngôn ngữ hay một dialect riêng.

Tính năng được thiết kế cho việc học và các chương trình nhỏ, độc lập. Khi chương trình cần API có thể tái sử dụng, package, nhiều lớp hoặc cấu trúc hướng đối tượng rõ ràng, ta có thể chuyển sang khai báo lớp tường minh.

## Quá trình từ preview đến tính năng chính thức

Tên gọi và một số chi tiết của tính năng đã thay đổi qua các bản preview. Mốc quan trọng là:

| Phiên bản | JEP | Trạng thái và điểm đáng chú ý |
|---|---|---|
| JDK 21 | [JEP 445](https://openjdk.org/jeps/445) | Bản preview đầu tiên, khi tính năng còn mang tên *Unnamed Classes and Instance Main Methods*. |
| JDK 22 | [JEP 463](https://openjdk.org/jeps/463) | Preview lần thứ hai với tên *Implicitly Declared Classes and Instance Main Methods*. File nguồn có thể ngầm khai báo một lớp; tên lớp do môi trường triển khai quyết định. Quy tắc chọn `main` cũng ưu tiên phương thức có tham số `String[]` nếu có. |
| JDK 23 | [JEP 477](https://openjdk.org/jeps/477) | Preview lần thứ ba. Bổ sung import tự động các kiểu công khai thuộc những package được `java.base` export và các phương thức I/O tĩnh của `java.io.IO`. |
| JDK 24 | [JEP 495](https://openjdk.org/jeps/495) | Preview lần thứ tư, đổi tên thành *Simple Source Files and Instance Main Methods*. Đây vẫn là giai đoạn preview. |
| JDK 25 | [JEP 512](https://openjdk.org/jeps/512) | Tính năng được hoàn thiện và trở thành một phần chính thức của Java. Tên cuối cùng là *Compact Source Files and Instance Main Methods*. API `IO` được chuyển sang `java.lang` và không còn tự động import các phương thức tĩnh. |

Vì vậy, JEP 463 là mốc quan trọng trong quá trình phát triển của tính năng, nhưng mã nguồn dùng hiện nay nên theo đặc tả ổn định từ JDK 25. Với JDK 25 trở lên, không cần bật preview để dùng compact source files hoặc instance `main` methods.

## Compact Source File được hiểu như thế nào?

Một source file trở thành **compact source file** khi có phương thức được khai báo bên ngoài một khai báo lớp tường minh. Các field, method và khai báo lớp thành viên ở cấp cao nhất của file được xem là thành viên của một lớp ngầm định.

Ví dụ, file `HelloWorld.java` có thể chỉ chứa:

```java
void main() {
    System.out.println("Hello, Java!");
}
```

Trình biên dịch ngầm khai báo một lớp cấp cao nhất để chứa phương thức `main`. Một số đặc điểm cần nhớ:

- Lớp ngầm định là `final`, có package access và thuộc unnamed package.
- Lớp kế thừa `java.lang.Object`, không triển khai interface trực tiếp nào.
- Lớp có constructor mặc định không tham số; không thể tự khai báo constructor khác cho lớp ngầm định.
- Những field và method viết bên ngoài lớp tường minh trở thành thành viên của lớp ngầm định. Theo quy tắc thành viên Java thông thường, chúng mặc định có package access và là thành viên instance nếu không ghi `static`.
- File phải có một `main` method có thể được Java launcher gọi.
- Mã nguồn không thể tham chiếu lớp ngầm định bằng tên. Tên file class được sinh ra là chi tiết triển khai, không phải tên lớp để code khác sử dụng.

Các khai báo `import` vẫn được đặt ở đầu file. Compact source file không khai báo `package`; lớp ngầm định thuộc unnamed package. Các lớp trong unnamed package không thể được tham chiếu trực tiếp từ package có tên.

## Instance Main Method và quy tắc khởi chạy

Trong Java truyền thống, entry point quen thuộc là `public static void main(String[] args)`. Từ JEP 463, Java launcher hỗ trợ thêm các dạng `main` có thể là phương thức instance, không bắt buộc `public` và có thể không nhận tham số.

Với compact source file trong JDK 25, các dạng cơ bản sau đều có thể được chọn làm entry point:

```java
// Instance main, không nhận tham số
void main() {
    IO.println("Xin chào!");
}
```

```java
// Instance main, nhận đối số dòng lệnh
void main(String[] args) {
    if (args.length == 0) {
        IO.println("Hãy truyền tên người dùng làm đối số.");
        return;
    }
    IO.println("Xin chào, " + args[0]);
}
```

Phương thức được chọn phải có kiểu trả về `void` và có mức truy cập mà launcher có thể gọi: `public`, `protected` hoặc package access. Phương thức có thể là `static` hoặc instance.

Khi có nhiều ứng viên, launcher áp dụng thứ tự sau:

1. Chọn `main(String[] args)` nếu có phương thức phù hợp và có thể truy cập.
2. Nếu không có, chọn `main()` nếu có phương thức phù hợp và có thể truy cập.
3. Nếu không có phương thức nào phù hợp, quá trình khởi chạy báo lỗi.

Nếu phương thức được chọn là `static`, launcher gọi trực tiếp phương thức đó. Nếu là instance method, launcher tạo một instance bằng constructor không tham số của lớp rồi gọi `main` trên instance vừa tạo. Với lớp ngầm định, constructor này là constructor mặc định do Java cung cấp.

Do các method và field trong compact source file mặc định là thành viên instance, chúng có thể gọi và sử dụng lẫn nhau mà không cần khai báo `static`:

```java
String greeting() {
    return "Chào mừng đến với Java";
}

void main() {
    IO.println(greeting());
}
```

## Import tự động từ module `java.base`

Trong compact source file, Java tự động import theo kiểu on-demand tất cả lớp và interface cấp cao nhất có thể truy cập công khai từ các package được module `java.base` export. Hiệu ứng tương đương với việc có khai báo `import module java.base;` ở đầu file.

Nhờ đó, có thể dùng nhiều kiểu phổ biến như `List`, `Map`, `ArrayList`, `Arrays`, `Stream`, `LocalDate` mà không cần viết import riêng, miễn là kiểu đó thuộc package được `java.base` export.

Ví dụ sau dùng `List` và `Map` mà không khai báo import:

```java
void main() {
    List<String> languages = List.of("Java", "Kotlin", "Scala");
    Map<String, Integer> lengths = new HashMap<>();

    for (String language : languages) {
        lengths.put(language, language.length());
    }

    lengths.forEach((language, length) ->
        IO.println(language + ": " + length));
}
```

Import tự động này chỉ áp dụng cho các package được `java.base` export. Nó không tự import các module khác như `java.sql` hoặc `java.desktop`; những kiểu thuộc module/package khác vẫn cần khai báo import phù hợp và cấu hình module tương ứng khi cần.

## I/O đơn giản với `java.lang.IO` trong JDK 25

JDK 25 cung cấp lớp `java.lang.IO` với các phương thức tĩnh phục vụ nhập và xuất văn bản theo dòng:

| Phương thức | Công dụng |
|---|---|
| `IO.print(value)` | Ghi biểu diễn dạng chuỗi của giá trị ra standard output, không tự thêm ký tự kết thúc dòng. |
| `IO.println(value)` | Ghi giá trị rồi thêm line separator. |
| `IO.println()` | Chỉ ghi line separator. |
| `IO.readln()` | Đọc một dòng từ standard input. |
| `IO.readln(prompt)` | Hiển thị lời nhắc rồi đọc một dòng từ standard input. |

Ví dụ nhập tên và in lời chào:

```java
void main() {
    String name = IO.readln("Tên của bạn: ");
    IO.println("Xin chào, " + name + "!");
}
```

`IO` thuộc package `java.lang`, nên tên lớp được tự động import như những kiểu khác trong package này. Tuy nhiên, các phương thức `static` của `IO` **không** được tự động static import trong JDK 25. Vì vậy, hãy gọi `IO.println(...)`, `IO.readln(...)` hoặc chủ động viết `import static java.lang.IO.*;` nếu muốn gọi phương thức không kèm tên lớp.

Điểm này khác với các bản preview trước JDK 25. JDK 23 và JDK 24 dùng `java.io.IO` và tự động static import các phương thức của lớp đó; mã nguồn preview viết `println(...)` hoặc `readln(...)` không có tiền tố lớp cần được cập nhật khi chuyển sang JDK 25. API `java.lang.IO` trong JDK 25 dựa trên `System.in` và `System.out`.

`IO` là tiện ích cho I/O cơ bản trong ví dụ nhỏ. Khi cần xử lý file, định dạng dữ liệu, encoding hoặc luồng I/O phức tạp, hãy chọn API phù hợp trong Java I/O thay vì cố dùng các phương thức đọc/ghi một dòng này cho mọi tình huống.

## Ví dụ hoàn chỉnh chạy với JDK 25 trở lên

Tạo file `CourseIntro.java` với nội dung:

```java
String course = "Java 25";
List<String> topics = List.of(
    "Compact Source Files",
    "Instance Main Methods",
    "java.lang.IO"
);

void main() {
    IO.println("Chủ đề: " + course);
    printTopics();

    String learner = IO.readln("Tên người học: ");
    IO.println("Xin chào, " + learner + "!");
}

void printTopics() {
    for (String topic : topics) {
        IO.println("- " + topic);
    }
}
```

Ví dụ này thể hiện các điểm chính:

- Không cần khai báo `class`, `package` hoặc `public static void main`.
- `List` và `String` có thể được dùng mà không cần import riêng.
- `course`, `topics`, `main` và `printTopics` là thành viên của lớp ngầm định.
- `main` và `printTopics` là instance method, nên có thể gọi trực tiếp lẫn nhau.
- I/O sử dụng `IO.println` và `IO.readln` theo API ổn định từ JDK 25.

Kiểm tra JDK đang dùng và chạy file từ thư mục chứa file:

```shell
java --version
java CourseIntro.java
```

Java launcher biên dịch source file rồi chạy chương trình. Nếu muốn tạo class file trước, có thể dùng:

```shell
javac CourseIntro.java
java CourseIntro
```

Hãy dùng JDK 25 trở lên để biên dịch cú pháp compact source file mà không bật preview. Lệnh `java CourseIntro.java` là chế độ chạy source file của Java launcher; bản thân chế độ chạy source file và cú pháp compact source file là hai khả năng riêng, có thể được dùng cùng nhau.

## Khi nào nên dùng và khi nào nên chuyển sang lớp tường minh?

Compact source file phù hợp khi chương trình có một điểm vào rõ ràng, ít thành phần và không cần công bố một lớp để code ở package khác tái sử dụng. Một số tình huống điển hình:

- Bài tập đầu tiên về biến, điều kiện, vòng lặp và phương thức.
- Ví dụ minh họa một API hoặc một thuật toán ngắn.
- Chương trình dòng lệnh nhỏ, độc lập.
- Thử nhanh một đoạn Java mà chưa cần thiết kế package và cấu trúc lớp.

Khi chương trình cần được tổ chức thành nhiều thành phần có thể tái sử dụng, nên khai báo lớp tường minh. Lớp ngầm định thuộc unnamed package, không thể được tham chiếu bằng tên từ mã nguồn khác và không thể định nghĩa constructor riêng. Công cụ `javadoc` cũng không thể tạo tài liệu API cho chính lớp ngầm định vì lớp này không cung cấp API có thể truy cập từ lớp khác.

Có thể chuyển các thành viên trong compact source file thành thành viên của một lớp thông thường bằng cách đặt chúng bên trong khai báo `class`. Khi chuyển đổi, hãy thêm các import cần thiết: import tự động từ `java.base` là quy tắc riêng của compact source file, không tự áp dụng cho một source file có lớp tường minh.

Ví dụ, chương trình nhỏ ở trên có thể phát triển thành:

```java
import java.util.List;

public class CourseIntro {
    private final String course = "Java 25";
    private final List<String> topics = List.of(
        "Compact Source Files",
        "Instance Main Methods",
        "java.lang.IO"
    );

    void main() {
        IO.println("Chủ đề: " + course);
        for (String topic : topics) {
            IO.println("- " + topic);
        }
    }
}
```

Đây là một lớp được khai báo tường minh, vì vậy nó có tên `CourseIntro` và có thể được tổ chức trong package như các lớp Java thông thường. Ví dụ vẫn dùng instance `main`, một khả năng đã trở thành tính năng chính thức từ JDK 25.

## Tài liệu tham khảo

- [JEP 463 — Implicitly Declared Classes and Instance Main Methods (JDK 22, Second Preview)](https://openjdk.org/jeps/463)
- [JEP 477 — Implicitly Declared Classes and Instance Main Methods (JDK 23, Third Preview)](https://openjdk.org/jeps/477)
- [JEP 495 — Simple Source Files and Instance Main Methods (JDK 24, Fourth Preview)](https://openjdk.org/jeps/495)
- [JEP 512 — Compact Source Files and Instance Main Methods (JDK 25)](https://openjdk.org/jeps/512)
- [Oracle Java 25 Language Guide: Compact Source Files and Instance `main` Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html)
- [Java SE 25 API: `java.lang.IO`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/IO.html)
