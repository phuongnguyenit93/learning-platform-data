# Viết instance main không có tham số cho chương trình tối giản

Để in một dòng chữ bằng Java, trước đây người học thường phải viết một lớp, khai báo `public static void main(String[] args)` rồi mới bắt đầu phần xử lý. Trong **Java 25**, chương trình nhỏ có thể bắt đầu trực tiếp bằng một **instance main không có tham số**:

```java
// File: Hello.java
void main() {
    IO.println("Xin chào từ Java 25!");
}
```

Chạy:

```bash
java Hello.java
```

Đầu ra:

```text
Xin chào từ Java 25!
```

Đây không phải cú pháp thử nghiệm: **JEP 512 — Compact Source Files and Instance Main Methods đã được hoàn thiện (final) trong Java 25**. Mã này không yêu cầu `--enable-preview`. Đây là một cải tiến phù hợp để viết công cụ một tệp, bài tập thuật toán, chương trình console nhỏ và ví dụ học Java hiện đại mà không cần tạo lớp bao bên ngoài chỉ để có điểm bắt đầu.

Bài thuộc chương **Hàm main** của module **JAVA_VERSION_JAVA25**. Module tập trung vào những khả năng Java 25 vẫn có ích như chương trình nguồn gọn, module import, constructor linh hoạt, ScopedValue, KDF, AOT cache và JFR. Trong bài này, chúng ta chỉ đi sâu vào cách viết **`void main()` dạng instance, không nhận tham số**, cách Java launcher tìm entry point, cách mở rộng mã nhỏ và các giới hạn cần biết khi chuyển sang ứng dụng lớn. Các ví dụ tuân theo **cú pháp chính thức của JDK 25**, không sử dụng biến thể preview cũ đã thay đổi.

## 1. Kết quả học tập

Sau khi hoàn thành, bạn có thể:

1. Viết và chạy một tệp Java chỉ với `void main()`, không phải tự khai báo class.
2. Giải thích tại sao `main` đó là **instance method** dù không thấy từ khóa `new` trong mã nguồn.
3. Phân biệt `void main()` với `static void main()` và `public static void main(String[] args)`.
4. Hiểu điều kiện để một `main` được launcher chọn, kể cả khi có nhiều overload.
5. Sử dụng `IO.println(…)`, `IO.readln(…)` và các lớp của `java.base` trong compact source file đúng theo Java 25.
6. Viết chương trình console nhỏ có helper method, field, validation và vòng lặp.
7. Nhận biết thời điểm nên chuyển từ compact source file sang class có tên, package, kiểm thử và cấu trúc dự án.
8. Kiểm tra phiên bản JDK, compiler target và những lỗi thường gặp mà không nhầm với các cú pháp preview từ Java 21–24.

## 2. Điều kiện cần: Java 25 và trạng thái JEP 512

**JEP 512** hoàn thiện hai khả năng liên quan nhưng không đồng nhất:

- **Compact source files**: tệp nguồn có khai báo method/field nằm ngoài một class được đặt tên tường minh. Compiler tạo một **implicitly declared class** để chứa các member đó.
- **Instance main methods**: chương trình có thể có method `main` không phải `static`; method có thể không cần `public` và không cần tham số `String[]`.

Điều thứ nhất giúp bỏ phần class boilerplate. Điều thứ hai nới quy tắc entry point. Hai khả năng có thể kết hợp trong tệp `Hello.java`, nhưng **instance main không chỉ dành cho compact source file**: một class thông thường có tên cũng có thể khai báo `void main()`.

Trước khi thử, xác minh công cụ:

```bash
java -version
javac -version
```

Bảo đảm cả launcher và compiler được dùng đều tương thích với JDK 25. Nếu terminal có nhiều JDK được cài, lệnh `java` và `javac` có thể trỏ vào hai phiên bản khác nhau; hãy kiểm `JAVA_HOME`, `PATH` và cấu hình IDE.

| Vấn đề | Trên Java 25 |
|---|---|
| Trạng thái compact source files và instance main | **Final**, không phải preview |
| Cần `--enable-preview` để viết `void main()`? | **Không** |
| Có bắt buộc `public static`? | **Không** đối với launchable instance main |
| Có bắt buộc `String[] args`? | **Không** |
| Có thể chạy trực tiếp tệp nguồn? | **Có**, dùng `java File.java` |
| Có thể biên dịch trước rồi chạy? | **Có**, `javac File.java` rồi chạy class đã sinh |
| Có thể dùng Java 21 làm compiler target cho cú pháp này? | **Không**, vì JEP 512 được hoàn thiện trong Java 25 và không thuộc ngôn ngữ Java 21 ổn định |

**Lưu ý về tính hiện hành:** một số bài hướng dẫn cho bản preview Java 22–24 dùng `java.io.IO` và gọi `println(…)` trực tiếp. **Java 25 dùng `java.lang.IO` và không tự static-import các method của `IO`**. Trong mã mới, hãy viết `IO.println(…)`, `IO.readln(…)` hoặc import static một cách tường minh.

## 3. Chương trình tối giản đầu tiên: chỉ có `void main()`

Tạo tệp `Hello.java` với đúng nội dung:

```java
void main() {
    IO.println("Học Java 25 qua một chương trình nhỏ.");
}
```

Chạy trong thư mục chứa tệp:

```bash
java Hello.java
```

Kết quả:

```text
Học Java 25 qua một chương trình nhỏ.
```

Không cần viết:

- Khai báo `package`, vì đây là chương trình một tệp trong unnamed package.
- Khai báo `class Hello`, vì compiler tạo lớp ngầm định.
- Từ khóa `static`, vì `main` được phép là instance method.
- Tham số `String[] args`, vì chương trình không cần đọc command-line arguments.
- Từ khóa `public`, vì method với quyền truy cập package (như `void main()`) cũng có thể là entry point.

**Đơn giản không có nghĩa bỏ Java:** method, biến cục bộ, kiểu dữ liệu, biểu thức, `if`, `for`, exceptions và các API khác vẫn là Java thông thường.

### 3.1. Cấu trúc ngữ nghĩa phía sau

Compiler xử lý compact source file theo hướng tương đương về mặt khái niệm:

```java
// MÔ HÌNH MINH HỌA, không phải nội dung class do compiler xuất ra.
final class ImplicitClass {
    // Compiler cung cấp constructor không tham số.
    void main() {
        IO.println("Học Java 25 qua một chương trình nhỏ.");
    }
}
```

Java launcher tìm một `main` hợp lệ. Nếu method là instance, launcher **tạo instance bằng constructor không tham số**, sau đó gọi `main()` trên instance đó.

Đây chỉ là cách hình dung. **Không được giả định tên của lớp ngầm định là `ImplicitClass` hoặc truy cập lớp ngầm định qua tên trong mã Java.** Compiler có thể dùng tên dựa trên tên tệp trong bytecode, nhưng lớp ngầm định không có tên để source code tham chiếu trực tiếp.

## 4. Chạy trực tiếp và chạy sau khi biên dịch

Đối với tệp `Hello.java`, có hai quy trình hợp lệ.

### 4.1. Source-file mode: ngắn nhất

```bash
java Hello.java
```

Launcher thực hiện bước biên dịch cần thiết rồi chạy source file; bạn không phải tự gọi `javac`. Cách này tiện cho lab, script và chương trình nhỏ.

### 4.2. Biên dịch trước

```bash
javac Hello.java
java Hello
```

Theo cơ chế Java 25, compiler sinh class file cho lớp ngầm định, với tên class file dựa vào `Hello.java` trong ví dụ. Launcher có thể chạy class được biên dịch như trên. Tuy nhiên, **tên đó là chi tiết tạo class file, không phải tên lớp bạn được dùng trong source code để khai báo `new Hello()`**.

| Cách chạy | Khi nên chọn |
|---|---|
| `java Hello.java` | Viết nhanh một tệp, minh họa, kiểm tra thuật toán |
| `javac Hello.java` rồi `java Hello` | Học quy trình compiler/runtime hoặc cần tách compile khỏi run |
| Build qua Maven/Gradle + class có tên | Ứng dụng nhiều tệp, test, dependencies và đóng gói chính thức |

Có thể chạy compact source file với **JDK 25 không cần flag preview**. Nếu dùng IDE, cần chọn JDK 25 cho project và module language level phù hợp; không phải mọi run configuration cũ đều tự nhận biết tệp có lớp ngầm định.

## 5. Instance main nghĩa là gì?

Trong Java, **instance method** thuộc về một object; **static method** thuộc về class. Trước Java 25, entry point thường có dạng:

```java
public class HelloTraditional {
    public static void main(String[] args) {
        System.out.println("Xin chào");
    }
}
```

Trong Java 25, ngay cả một class có tên cũng có thể dùng:

```java
// File: HelloNamed.java
public class HelloNamed {

    void main() {
        IO.println("Xin chào từ instance main!");
    }
}
```

Chạy:

```bash
java HelloNamed.java
```

Khi launcher chọn method instance, nó tạo một đối tượng `HelloNamed` bằng constructor không tham số phù hợp rồi gọi method.

### 5.1. Phân biệt bốn hình thức hay gặp

| Cách khai báo | Là instance? | Có nhận args? | Có thể dùng làm main trong Java 25? |
|---|---|---|---|
| `void main()` | Có | Không | Có |
| `void main(String[] args)` | Có | Có | Có |
| `static void main()` | Không | Không | Có |
| `public static void main(String[] args)` | Không | Có | Có |

Để được launcher chọn, method còn phải **trả về `void`** và có mức truy cập thích hợp (`public`, `protected` hoặc package); `private void main()` không phải một launchable main theo quy tắc Java 25. Cú pháp `String... args` tương đương tham số mảng `String[]` trong trường hợp này.

**Kết luận:** từ khóa `static` và tham số mảng không còn là điều kiện bắt buộc của mọi Java entry point. Tuy nhiên, kiểu main truyền thống vẫn hợp lệ và hữu ích trong những ứng dụng có cấu trúc, đặc biệt khi toolchain hoặc framework kỳ vọng class entry point tường minh.

## 6. Vì sao một instance main có thể gọi helper method tự nhiên?

Tệp compact source có thể chứa những method/field ở cấp tệp. Chúng trở thành member của lớp ngầm định và mặc định **không phải static**, nên `main` instance gọi chúng trực tiếp.

```java
// File: Greeting.java
String greeting = "Xin chào";

String compose(String name) {
    return greeting + ", " + name + "!";
}

void main() {
    IO.println(compose("Minh"));
    IO.println(compose("Lan"));
}
```

Chạy:

```bash
java Greeting.java
```

Kết quả:

```text
Xin chào, Minh!
Xin chào, Lan!
```

Từ đây có thể dạy các khái niệm theo thứ tự hợp lý:

1. `main()` điều phối chương trình.
2. Helper method nhận tham số và trả giá trị.
3. Field giữ trạng thái của instance.
4. Khi cần mô hình hóa nhiều đối tượng hoặc nhiều thành phần, chuyển sang class/interface/package rõ ràng.

### 6.1. Không phải mọi thứ ở cấp tệp đều là biến toàn cục

Một field khai báo ngoài method là member của lớp ngầm định:

```java
int total = 0;

void add(int value) {
    total += value;
}

void main() {
    add(10);
    add(5);
    IO.println(total); // 15
}
```

Biến `total` là **instance field**, không phải biến toàn cục được chia sẻ giữa mọi process. Với chương trình tối giản, điều này dễ hiểu, nhưng nếu ứng dụng bắt đầu có nhiều trạng thái, việc để toàn bộ state trên entry-point class sẽ khó kiểm thử và khó bảo trì. Khi đó nên tách các class có trách nhiệm rõ.

## 7. Tại sao `IO.println(…)` mới là cú pháp đúng của Java 25?

Java 25 có `java.lang.IO` cung cấp các thao tác console đơn giản:

| Method | Vai trò |
|---|---|
| `IO.println(Object)` | In giá trị và xuống dòng |
| `IO.println()` | In dòng trống |
| `IO.print(Object)` | In không xuống dòng |
| `IO.readln()` | Đọc một dòng từ standard input |
| `IO.readln(String prompt)` | Hiện prompt rồi đọc một dòng |

Ví dụ:

```java
void main() {
    IO.println("Bắt đầu");
    IO.print("Giá trị: ");
    IO.println(25);
    IO.println();
    IO.println("Kết thúc");
}
```

**Vì `IO` thuộc package `java.lang`**, bạn không cần `import java.lang.IO;`. Nhưng các method `println` và `readln` là **static methods** của `IO`; bản final Java 25 **không tự import static** chúng vào mọi compact source file.

Viết như sau sẽ không hợp lệ nếu không khai báo import static hoặc một method cùng tên:

```java
void main() {
    println("Xin chào"); // Không có import static trong ví dụ này.
}
```

Có hai cách hiện hành:

```java
// Cách 1: rõ ràng, được khuyến nghị cho người mới
void main() {
    IO.println("Xin chào");
}
```

```java
// Cách 2: chỉ khi thật sự muốn dùng static import
import static java.lang.IO.println;

void main() {
    println("Xin chào");
}
```

**Tránh copy mã Java 24 preview** sử dụng `java.io.IO` hoặc giả định `println(…)` được tự import static. Bài học này sử dụng chuẩn Java 25 final.

### 7.1. Khi nào vẫn dùng `System.out.println(…)`?

`System.out.println(…)` vẫn là Java hợp lệ, không bị coi là legacy chỉ vì `IO.println(…)` xuất hiện. Có thể tiếp tục dùng khi cần `PrintStream`, redirect output, tích hợp công cụ đã có hoặc khi muốn giữ code tương thích JDK cũ hơn. `IO` tối ưu cho thao tác đơn giản, không phải thư viện logging/observability của ứng dụng doanh nghiệp.

## 8. Tự động import các package mà `java.base` export

Một **compact source file** trong Java 25 tự có hiệu ứng giống `import module java.base;` đối với những public top-level types trong package mà module `java.base` export. Vì vậy, nhiều kiểu dữ liệu quen thuộc có thể dùng mà không cần import riêng:

```java
// File: ScoreSummary.java
void main() {
    List<Integer> scores = List.of(7, 9, 10, 8);

    int sum = scores.stream()
            .mapToInt(Integer::intValue)
            .sum();

    IO.println("Tổng điểm: " + sum);
    IO.println("Trung bình: " + (sum / (double) scores.size()));
}
```

Các kiểu `List`, `Integer`, `Stream` hoặc `Map` được khai báo trong các package thuộc `java.base`, nên compact source thường không cần dòng import truyền thống cho chúng. Tuy nhiên:

- Không có nghĩa **mọi** class trong JDK đều được tự import. Những module khác, như `java.sql`, không tự động thuộc phạm vi này chỉ vì ứng dụng chạy Java 25.
- Không có nghĩa mọi Java source file đều auto-import toàn bộ `java.base`. Cơ chế này dành cho **compact source files**; các class được đặt tên tường minh vẫn cần import type từ `java.util`, `java.time`, v.v. theo quy tắc thông thường.
- Không mở quyền truy cập vào internal package; module import chỉ áp dụng cho những package được export.
- Khi tên type bị mơ hồ do import rộng, cần chỉ định import cụ thể hoặc fully qualified type.

**Liên hệ với module JAVA_VERSION_JAVA25:** JEP 511 đã chuẩn hóa module import declarations; JEP 512 tận dụng cơ chế này để giúp compact source ít boilerplate hơn. Đây là cú pháp chính thức, không yêu cầu preview trong Java 25.

## 9. Không có tham số nghĩa là gì với command-line arguments?

Một chương trình có `void main()` không nhận đối số từ launcher vào method. Bạn vẫn có thể chạy:

```bash
java Hello.java hello world
```

Nhưng nếu launcher chọn **`void main()`**, những command-line arguments đó **không được đưa vào tham số của method**, vì method không khai báo tham số nào. Không nên viết chương trình yêu cầu tên người dùng/đường dẫn file từ CLI mà chỉ dùng no-arg `main()` rồi kỳ vọng tự có biến `args`.

Ví dụ này sai:

```java
void main() {
    IO.println(args[0]); // Không tồn tại biến args trong scope.
}
```

Nếu muốn nhận arguments, có thể đổi sang instance main có tham số:

```java
// File: CliGreeting.java
void main(String[] args) {
    String name = args.length > 0 ? args[0] : "bạn";
    IO.println("Xin chào, " + name);
}
```

Và chạy:

```bash
java CliGreeting.java Phuong
```

Bài tập trung vào no-arg main, nên khi viết chương trình tương tác thay vì nhận CLI arguments, cách đơn giản là dùng `IO.readln(…)`.

**Quy tắc lựa chọn:** không có input CLI → `void main()` rất phù hợp; cần input CLI → `void main(String[] args)` hoặc main truyền thống tùy kiến trúc.

## 10. Quy tắc chọn entry point khi có nhiều overload của `main`

Java launcher của JDK 25 chọn trong các candidate method hợp lệ theo nguyên tắc:

1. Nếu có `main(String[] args)` (hoặc `main(String... args)`) với kết quả `void` và mức truy cập phù hợp, **chọn dạng có mảng String**.
2. Nếu không có dạng trên, chọn `main()` không tham số với kết quả `void`.
3. Nếu chọn **instance main**, tạo đối tượng bằng constructor không tham số phù hợp, sau đó gọi method đó. Nếu chọn `static main`, không cần tạo instance.
4. Nếu không tìm được candidate phù hợp hoặc không thể tạo instance khi cần, quá trình khởi chạy thất bại.

Chẳng hạn tệp compact sau khai báo hai `main` hợp lệ:

```java
// File: WhichMain.java
void main() {
    IO.println("main không có tham số");
}

void main(String[] args) {
    IO.println("main có args: " + args.length);
}
```

Chạy:

```bash
java WhichMain.java a b
```

Kết quả:

```text
main có args: 2
```

**Dạng có `String[]` được ưu tiên** không phụ thuộc vào việc bản no-arg được viết trước. Quy tắc này quan trọng nếu nhóm thêm overload để mở rộng chương trình nhỏ: đừng giả định launcher tự chọn overload “gần nhất” với số đối số dòng lệnh.

### 10.1. Những chữ ký không hợp lệ

```java
// Các ví dụ sau KHÔNG phải launchable main phù hợp:
int main() { return 0; }             // Sai kiểu kết quả: phải void.
void main(int count) {}               // Sai dạng tham số.
private void main() {}                // Private không đủ mức truy cập.
```

Đây là các ví dụ **riêng biệt** về chữ ký không được chọn, không phải một tệp bạn nên ghép và chạy. Trường hợp `void main(int)` có thể là method Java bình thường, nhưng launcher không dùng làm entry point.

## 11. Instance main trong class có tên và constructor không tham số

Compact source file có lớp ngầm định được tạo với constructor mặc định không tham số. Nhưng nếu đặt instance main trong **class tường minh**, cần bảo đảm launcher có thể tạo instance bằng một constructor không tham số phù hợp.

Ví dụ hợp lệ:

```java
// File: NamedProgram.java
public class NamedProgram {
    private final String label;

    NamedProgram() {
        label = "Java 25";
    }

    void main() {
        IO.println("Chạy " + label);
    }
}
```

Chạy:

```bash
java NamedProgram.java
```

Một chương trình có thể compile nhưng không launch được theo kiểu instance main nếu class chỉ có constructor yêu cầu tham số:

```java
// Ví dụ lớp cần sửa thiết kế entry point:
class NeedsParameter {
    NeedsParameter(String name) {}

    void main() {
        IO.println("Không có no-arg constructor phù hợp");
    }
}
```

Java launcher **không thể tự biết truyền gì vào constructor `NeedsParameter(String)`**. Nếu cần khởi tạo phức tạp, thường giữ một entry point tường minh có khả năng dựng dependencies một cách rõ ràng; không ép mọi ứng dụng vào no-arg instance main.

### 11.1. Instance main không thay thế dependency injection

Với một ứng dụng Spring Boot, method entry point truyền thống `SpringApplication.run(App.class, args)` vẫn hợp lý. JEP 512 không tự tạo `ApplicationContext`, không tạo Spring beans và không quản lý lifecycle.

```java
@SpringBootApplication
public class BusinessApplication {
    public static void main(String[] args) {
        SpringApplication.run(BusinessApplication.class, args);
    }
}
```

Đoạn trên còn thiếu imports Spring vì chỉ minh họa cấu trúc. **Không cần đổi entry point của ứng dụng doanh nghiệp chỉ vì Java 25 cho phép `void main()`.** Dùng tính năng mới khi nó làm chương trình ngắn và dễ hiểu hơn, không phải khi nó che giấu bootstrap/configuration cần thiết.

## 12. Bài thực hành: nhập liệu an toàn bằng `IO.readln(…)`

Tạo chương trình yêu cầu người dùng nhập một số nguyên không âm và hiển thị bình phương.

```java
// File: Square.java
void main() {
    String input = IO.readln("Nhập số nguyên không âm: ");

    if (input == null) {
        IO.println("Không có dữ liệu đầu vào.");
        return;
    }

    try {
        int number = Integer.parseInt(input.strip());

        if (number < 0) {
            IO.println("Cần nhập số không âm.");
            return;
        }

        long square = (long) number * number;
        IO.println("Bình phương: " + square);
    } catch (NumberFormatException ex) {
        IO.println("Giá trị không phải số nguyên hợp lệ.");
    }
}
```

Chạy:

```bash
java Square.java
```

Ví dụ tương tác:

```text
Nhập số nguyên không âm: 12
Bình phương: 144
```

Giải thích các chi tiết quan trọng:

- `IO.readln(…)` nhận một dòng input; nếu đầu vào kết thúc (EOF), cần xử lý thay vì giả định luôn có chuỗi.
- `strip()` loại bỏ whitespace đầu/cuối theo semantics Java.
- `Integer.parseInt(…)` có thể ném `NumberFormatException`; không để chương trình lab hiển thị stack trace khó hiểu cho lỗi nhập liệu bình thường.
- Dùng `(long) number * number` để tránh tràn số ở phép nhân `int` với nhiều giá trị lớn.
- No-arg `main()` hoàn toàn có thể dùng `if`, `return`, `try/catch` và các API Java thông thường.

### 12.1. Phiên bản có helper method

Khi logic tăng, tách parse/validate ra helper để tránh `main` quá dài:

```java
// File: AgeCheck.java
int parseAge(String text) {
    int age = Integer.parseInt(text.strip());

    if (age < 0 || age > 150) {
        throw new IllegalArgumentException("Tuổi ngoài phạm vi.");
    }

    return age;
}

void main() {
    String input = IO.readln("Tuổi của bạn: ");

    if (input == null) {
        IO.println("Không có dữ liệu.");
        return;
    }

    try {
        int age = parseAge(input);
        IO.println(age >= 18 ? "Đủ 18 tuổi" : "Chưa đủ 18 tuổi");
    } catch (IllegalArgumentException ex) {
        IO.println("Dữ liệu tuổi không hợp lệ.");
    }
}
```

**Ghi chú về Java:** `NumberFormatException` kế thừa `IllegalArgumentException`, nên một khối `catch (IllegalArgumentException ex)` đã xử lý được cả lỗi parse số lẫn lỗi tuổi ngoài phạm vi. Không viết multi-catch gồm hai kiểu có quan hệ kế thừa. Viết chương trình ngắn vẫn phải tuân thủ quy tắc kiểu dữ liệu của Java.

## 13. Mini-project: máy tính thống kê một tệp

Một use case vừa đủ để thấy lợi ích của no-arg instance main là **nhập nhiều số, tính tổng và trung bình**, có helper method, vòng lặp và collection.

```java
// File: NumberStats.java
List<Integer> numbers = new ArrayList<>();

void main() {
    IO.println("Nhập các số nguyên; để trống rồi Enter để kết thúc.");

    while (true) {
        String line = IO.readln("Số tiếp theo: ");

        if (line == null || line.isBlank()) {
            break;
        }

        try {
            numbers.add(Integer.parseInt(line.strip()));
        } catch (NumberFormatException ex) {
            IO.println("Bỏ qua giá trị không hợp lệ: " + line);
        }
    }

    showStatistics();
}

void showStatistics() {
    if (numbers.isEmpty()) {
        IO.println("Chưa có số liệu.");
        return;
    }

    long sum = numbers.stream()
            .mapToLong(Integer::longValue)
            .sum();

    double average = sum / (double) numbers.size();

    IO.println("Số lượng: " + numbers.size());
    IO.println("Tổng: " + sum);
    IO.println("Trung bình: " + "%.2f".formatted(average));
}
```

Chạy:

```bash
java NumberStats.java
```

Một phiên làm việc:

```text
Nhập các số nguyên; để trống rồi Enter để kết thúc.
Số tiếp theo: 10
Số tiếp theo: 20
Số tiếp theo: abc
Bỏ qua giá trị không hợp lệ: abc
Số tiếp theo: 30
Số tiếp theo:
Số lượng: 3
Tổng: 60
Trung bình: 20.00
```

Chương trình dùng `List` và `ArrayList` mà không cần import vì compact source được tự import các public types từ các package do `java.base` export. Trạng thái `numbers` là field của lớp ngầm định, nên helper `showStatistics()` truy cập được.

### 13.1. Những điều chương trình này cố ý chưa làm

- Không lưu dữ liệu xuống database.
- Không hỗ trợ file cấu hình, phân quyền hoặc validation dữ liệu phức tạp.
- Không phân tách domain model/service/repository thành các module.
- Không được thiết kế để nhiều người dùng truy cập đồng thời.

Các giới hạn đó **không phải lỗi**: compact source file phù hợp cho chương trình nhỏ. Khi yêu cầu đổi, cần đánh giá kiến trúc thay vì tiếp tục nhồi mọi trách nhiệm vào một tệp.

## 14. Chuyển từ compact source sang class có tên

Khi chương trình cần API ổn định, unit tests, nhiều file, dependency management hoặc entry point được đóng gói, chuyển dần sang class tường minh.

Ban đầu:

```java
// File: Welcome.java (compact source)
String format(String name) {
    return "Chào " + name;
}

void main() {
    IO.println(format("Java"));
}
```

Có thể chuyển thành:

```java
// File: WelcomeApp.java
public class WelcomeApp {

    String format(String name) {
        return "Chào " + name;
    }

    void main() {
        IO.println(format("Java"));
    }
}
```

Lúc này có thể biên dịch và chạy bằng class có tên:

```bash
javac WelcomeApp.java
java WelcomeApp
```

**Lợi ích:** class có tên có thể được tham chiếu trong những class khác, có thể gắn package, định nghĩa public API, tổ chức source set và kiểm thử. Method `main()` vẫn được giữ ở dạng instance trong Java 25 nếu đó là lựa chọn phù hợp.

Một bước tiếp theo là tách logic khỏi entry point:

```java
// File: GreetingFormatter.java
public class GreetingFormatter {
    public String format(String name) {
        return "Chào " + name;
    }
}
```

```java
// File: WelcomeApp.java
public class WelcomeApp {
    void main() {
        GreetingFormatter formatter = new GreetingFormatter();
        IO.println(formatter.format("Java"));
    }
}
```

Ở mức này, dự án có thể cần compile nhiều file và tổ chức package. JEP 512 giúp **đi từ chương trình nhỏ tới chương trình lớn**, không buộc mọi ứng dụng ở mã dạng một tệp.

## 15. Tương thích với Java versions và build tools

### 15.1. Java 25 runtime không đồng nghĩa source target 25

Một hệ thống có thể cài JDK 25 để chạy ứng dụng nhưng vẫn dùng `--release 21` khi build để giữ khả năng chạy trên các JVM cũ hơn. Khi đó, các tính năng nguồn Java 25 như compact source file và instance main kiểu mới **không thuộc tập cú pháp release 21**.

Ví dụ biên dịch cho Java 25:

```bash
javac --release 25 Hello.java
```

Nếu công cụ IDE/Maven/Gradle vẫn cấu hình source level Java 21, mã `void main()` cấp tệp sẽ không được compiler chấp nhận theo Java 21 final. Đừng dùng `--enable-preview` của JDK 25 như một cách “chạy ngược” tính năng mới trên runtime cũ.

### 15.2. Bảo trì code đa phiên bản

| Tình huống | Lựa chọn |
|---|---|
| Bài học/lab chạy JDK 25 | Compact source + `void main()` |
| CLI một file, chỉ hỗ trợ JDK 25+ | Compact source phù hợp |
| Thư viện phải chạy Java 17/21 | Dùng cú pháp/source target tương thích release đó |
| Dự án Spring Boot tổ chức nhiều module | Giữ entry point và build layout tường minh |
| Toolchain chưa hỗ trợ cú pháp Java 25 | Nâng compiler/IDE/plugin trước khi áp dụng |
| Script cần command-line arguments | `void main(String[] args)` hoặc main truyền thống |

**Nguyên tắc:** có thể nâng runtime để hưởng cải tiến JVM mà chưa phải viết lại source. Chỉ đổi language level sau khi toàn bộ pipeline build, CI, tests và các môi trường chạy đã hỗ trợ JDK thích hợp.

## 16. Đọc và sửa lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Compiler báo lỗi ở `void main()` ngoài class | Đang dùng JDK/source level cũ | Kiểm `java -version`, `javac -version`, `--release` |
| Dùng `println("x")` không compile | Không có import static như preview cũ | Dùng `IO.println("x")` |
| `import java.io.IO` không compile ở JDK 25 | Đọc bài hướng dẫn preview cũ | Dùng `java.lang.IO`, không cần import |
| `args` không xác định | No-arg main không khai báo args | Chuyển sang `void main(String[] args)` nếu cần |
| Chương trình có hai overload main và chạy “nhầm” | Launcher ưu tiên dạng `String[]` | Xem lại quy tắc chọn entry point |
| `private void main()` không launch | Mức truy cập không hợp lệ | Dùng package/protected/public phù hợp |
| Class có instance main nhưng không chạy | Không có accessible no-arg constructor | Thêm constructor phù hợp hoặc dùng static main |
| `List` trong class có tên không được nhận diện | Auto import `java.base` chỉ cho compact source | Thêm `import java.util.List;` hoặc `import module java.base;` |
| `IO.readln()` trả kết quả không như mong đợi | EOF, encoding hoặc input không hợp lệ | Kiểm null/blank và điều kiện terminal |
| IDE không cho Run tệp compact | SDK/lang level hoặc run configuration cũ | Chọn JDK 25, source file launcher phù hợp |
| Chạy class name từ source mode gặp lỗi | Dùng sai target lệnh | `java File.java` hoặc compile rồi `java ClassName` |
| Java 25 compile nhưng runtime 21 không chạy | Class file/source API mới hơn | Triển khai runtime JDK 25 hoặc dùng target cũ |

### 16.1. Checklist điều tra trong terminal

```bash
java -version
javac -version

# Chạy trực tiếp đúng tệp nguồn:
java Hello.java

# Hoặc biên dịch rồi chạy:
javac --release 25 Hello.java
java Hello
```

Không đồng nhất lệnh `java Hello.java` với `java Hello`. Lệnh thứ nhất chạy tệp nguồn, lệnh thứ hai chạy class đã được biên dịch hoặc có mặt trên classpath. Với tên package và module của ứng dụng lớn, cách launch còn phụ thuộc cấu hình runtime.

## 17. Khi nào nên dùng no-arg instance main?

| Nhu cầu | No-arg instance `main()` có phù hợp? | Lý do |
|---|---|---|
| In kết quả bài tập Java cơ bản | **Rất phù hợp** | Ít boilerplate, tập trung thuật toán |
| Chương trình hỏi người dùng một vài giá trị | **Phù hợp** | Dùng `IO.readln(…)`, `IO.println(…)` |
| Mini CLI không cần command-line options | **Phù hợp** | Không cần `String[] args` |
| CLI cần nhiều flags/positional arguments | **Cân nhắc** | Dạng có `String[] args` rõ ràng hơn |
| Tool thử một API Java 25 | **Phù hợp** | Một file, không phải tạo project |
| Thư viện có API công khai, nhiều class | **Không phải lựa chọn chính** | Cần class/package/module có tên rõ ràng |
| Spring Boot/service doanh nghiệp | **Thường không cần đổi** | Bootstrap, DI, config và build packaging |
| Chương trình yêu cầu tương thích Java 17/21 | **Không phù hợp với cú pháp final Java 25** | Source target cũ không hỗ trợ |
| Hệ thống cần logging, JFR, AOT, security nghiêm túc | **Tùy kiến trúc** | Main ngắn không thay các thành phần nền tảng |

**Nhấn mạnh:** No-arg instance main giúp khởi đầu đơn giản, không có nghĩa mọi ứng dụng Java hiện đại nên bỏ `public static void main(String[] args)`.

## 18. Bài thực hành củng cố

**Bài 1 — Hello Java 25:** Viết `Hello.java` chỉ có `void main()` và `IO.println(…)`. Chạy bằng source mode và bằng quy trình compile-then-run. Xác nhận không cần preview flag.

**Bài 2 — Helper method:** Tạo `formatPrice(long amount)` rồi gọi từ `main()`. Giải thích vì sao method không cần `static`.

**Bài 3 — Input validation:** Dùng `IO.readln(…)` để nhập bán kính không âm, tính diện tích hình tròn và bắt lỗi số không hợp lệ. Xử lý trường hợp EOF.

**Bài 4 — Command-line arguments:** Tạo `void main()` và `void main(String[] args)` trong cùng một compact source file. Gọi với hai đối số; dự đoán method nào chạy, rồi kiểm bằng output.

**Bài 5 — Named class:** Chuyển compact source thành `public class StudentTool { void main() { … } }`. Chạy bằng `java StudentTool.java` và giải thích instance được tạo ở đâu.

**Bài 6 — Auto import:** Viết compact source dùng `List`, `Map` và `Collectors` mà không khai báo import, rồi chuyển nội dung sang named class. Xác định import nào cần bổ sung.

**Bài 7 — Ưu tiên tương thích:** Một nhóm có runtime JDK 25 nhưng phải xuất thư viện chạy trên Java 21. Đề xuất nên giữ source target nào và vì sao không áp dụng cú pháp Java 25 cho module thư viện đó.

**Bài 8 — Sửa một ví dụ sai:** Xem source sau và sửa cả lỗi `IO` lẫn lỗi `args`:

```java
import java.io.IO;

void main() {
    println(args[0]);
}
```

Một phương án nếu **không cần** command-line argument:

```java
void main() {
    IO.println("Không cần args, không cần import IO.");
}
```

Một phương án nếu **cần** command-line argument:

```java
void main(String[] args) {
    IO.println(args.length > 0 ? args[0] : "Chưa có tham số");
}
```

## 19. Checklist hoàn thành

- [ ] Chạy được `java Hello.java` với JDK 25.
- [ ] Hiểu `void main()` là instance method không cần đối số.
- [ ] Phân biệt compact source file và class có tên chứa instance main.
- [ ] Biết launcher tạo instance khi chọn instance main.
- [ ] Hiểu quy tắc ưu tiên `main(String[] args)` so với `main()`.
- [ ] Không cố launch một `private main` hoặc một method trả `int`.
- [ ] Biết instance main trong named class cần no-arg constructor phù hợp.
- [ ] Dùng `IO.println(…)`/`IO.readln(…)` đúng với Java 25 final.
- [ ] Không copy cách tự import static method của `java.io.IO` từ preview cũ.
- [ ] Hiểu auto import `java.base` chỉ áp dụng theo quy tắc compact source.
- [ ] Xử lý null, dữ liệu không hợp lệ và số tràn trong các bài nhập liệu.
- [ ] Chọn đúng entry point nếu cần command-line arguments.
- [ ] Biết khi nào nên chuyển thành named class và cấu trúc dự án rõ ràng.
- [ ] Kiểm compiler JDK, runtime JDK, source/target release để tránh lỗi tương thích.
- [ ] Không dùng `--enable-preview` cho tính năng JEP 512 final trong JDK 25.

## Tài liệu tham khảo chính thức

- [JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512) — thiết kế và trạng thái final trong JDK 25.
- [Oracle Java 25 — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html) — tạo compact source, cơ chế main selection, chạy source và các ví dụ.
- [Java 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html) — thay đổi so với những bản preview trước.
- [Java SE 25 API — `java.lang.IO`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/IO.html) — các method console có hiệu lực trong bản final.
- [JEP 511 — Module Import Declarations](https://openjdk.org/jeps/511) — cách nhập các public types do module export.
- [Java SE 25 — `java` launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html) — source-file mode và tham số launcher.

## Kết luận

**Viết `void main()` không tham số là một khả năng chính thức, hữu dụng trong Java 25.** Nó giúp chương trình đơn giản tập trung vào logic thay vì boilerplate: chỉ cần một tệp `.java`, một instance main và các lời gọi `IO.println(…)` hoặc `IO.readln(…)` khi cần. Compiler tạo lớp ngầm định, launcher tạo instance và gọi main; khi chương trình lớn lên, có thể chuyển dần sang named class, package và công cụ build mà không bỏ các kiến thức Java đã học.

Khi áp dụng thực tế, hãy nhớ **quy tắc chọn main, giới hạn command-line arguments, import theo JDK 25 và tương thích source level**. Đừng chạy theo các ví dụ preview cũ hoặc thay entry point doanh nghiệp đang ổn định chỉ vì có cú pháp ngắn hơn. Lợi ích lớn nhất của no-arg instance main là giúp người học và người viết công cụ nhỏ đi thẳng vào vấn đề trong một ngôn ngữ Java hiện đại, đầy đủ và được hỗ trợ.
