# Dùng `javac` để kiểm tra syntax và lỗi compile-time của Java pattern matching

## 1. Vì sao `javac` là bước kiểm tra đầu tiên?

Khi viết code Java, đặc biệt với **type patterns**, **record patterns**, `switch expression` và `when`, lập trình viên dễ nhầm giữa ba loại vấn đề:

1. **Lỗi cú pháp (syntax/parsing)**: viết một cấu trúc Java không đúng ngữ pháp, chẳng hạn thiếu `;`, thiếu dấu `}`, viết sai nhãn `case` hoặc đặt `yield` sai vị trí.
2. **Lỗi ngữ nghĩa ở compile time**: code có thể được phân tích cú pháp, nhưng **không hợp lệ về kiểu, phạm vi hoặc quy tắc ngôn ngữ**; ví dụ record pattern sai số component, nhánh `case` bị dominance, hoặc `switch expression` không exhaustive.
3. **Lỗi ở runtime hoặc lỗi nghiệp vụ**: code biên dịch thành công nhưng lúc chạy ném `NullPointerException`, xử lý sai input, trả kết quả không mong muốn, hoặc vi phạm quy tắc domain.

**`javac`** (Java compiler) kiểm tra cả cú pháp **và** nhiều quy tắc compile-time khác, rồi tạo bytecode `.class` nếu thành công. Vì vậy nói “chạy `javac` để kiểm tra syntax” là cách nói ngắn; chính xác hơn, nó **biên dịch và kiểm tra tính hợp lệ ở compile time**, không chỉ chạy một bộ phân tích dấu ngoặc.

Một bài học quan trọng: **`javac` báo không có lỗi không chứng minh chương trình đúng khi chạy.** Compile và run/test là hai bước khác nhau:

~~~text
Mã nguồn .java
    |
    v
javac: phân tích cú pháp + kiểm tra kiểu/ngôn ngữ + xử lý phụ thuộc
    |
    +-- Có lỗi -> diagnostics, exit code khác 0
    |
    +-- Thành công -> bytecode .class
                         |
                         v
                    java: chạy chương trình
                         |
                         v
                    test hành vi/runtime
~~~

Phạm vi bài dùng **Java 21+**, vì record patterns và pattern matching for `switch` ổn định trong Java 21; trong Java 17, `instanceof` type pattern đã ổn định nhưng nhiều cú pháp `switch` pattern còn là preview hoặc chưa có dạng chính thức tương ứng.

## 2. Kiểm tra JDK và phiên bản compiler trước khi phân tích lỗi

Mở terminal hoặc PowerShell, kiểm tra:

~~~bash
java -version
javac -version
~~~

Hai lệnh có mục đích khác nhau:

- `java`: Java launcher/runtime để **chạy** class hoặc chương trình.
- `javac`: compiler thuộc **JDK** để biên dịch nguồn thành `.class`.

Nếu terminal báo `javac: command not found` hoặc PowerShell báo `javac is not recognized`, chưa thể kết luận file Java sai syntax: vấn đề có thể là **chưa cài JDK** hoặc `PATH` chưa trỏ đúng bộ công cụ. Dùng JDK 21 trở lên để biên dịch những ví dụ của bài.

Đặc biệt trên máy có nhiều JDK, `java -version` và `javac -version` có thể khác nhau do `PATH`/`JAVA_HOME`. Khi file dùng Java 21 nhưng compiler thực tế quá cũ, thông báo “source release ... not supported” hoặc “preview feature ...” có thể phản ánh **môi trường**, không phải code viết sai.

**Nguyên tắc:** kiểm tra **compiler version** trước, sau đó cố định source compatibility trong lệnh build. Đừng chỉ nhìn phiên bản JRE chạy ứng dụng.

## 3. Lệnh tối thiểu: biên dịch một file `.java`

Giả sử file có tên **`Hello.java`**:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello Java");
    }
}
~~~

Đứng tại thư mục chứa file rồi chạy:

~~~bash
javac Hello.java
java Hello
~~~

Đầu ra:

~~~text
Hello Java
~~~

Nếu biên dịch thành công, `javac` thường **không in thông báo thành công**; nó tạo `Hello.class`. Với lệnh trên, class file mặc định được đặt ở cạnh file nguồn. Nếu có lỗi, compiler in thông báo và lệnh kết thúc với **exit code khác 0**.

**Quy tắc file/class:** khi có **top-level public class `Hello`**, nguồn phải đặt trong file **`Hello.java`**. Lệnh `javac Hello.java` không giống với việc chạy Java source file trực tiếp bằng `java Hello.java`; khi kiểm tra compile-time nghiêm túc, hãy gọi `javac` để nhận diagnostics và kiểm soát output.

## 4. Lệnh khuyến nghị cho Java 21: release, encoding và thư mục đầu ra

Trong project nhỏ, nên tránh để file `.class` rải rác giữa mã nguồn:

~~~bash
mkdir out
javac --release 21 -encoding UTF-8 -d out JavacPatternSyntaxDemo.java
java -cp out JavacPatternSyntaxDemo
~~~

Ý nghĩa các thành phần:

| Thành phần | Tác dụng |
| --- | --- |
| `javac` | Dùng Java compiler thực sự |
| `--release 21` | Kiểm tra nguồn theo quy tắc Java 21, tạo bytecode mục tiêu Java 21 và giới hạn API JDK/Java SE được hỗ trợ trong release đó |
| `-encoding UTF-8` | Giải mã file `.java` bằng UTF-8, quan trọng với bình luận và chuỗi tiếng Việt |
| `-d out` | Đặt output class files dưới thư mục `out` |
| `JavacPatternSyntaxDemo.java` | Đường dẫn file nguồn cần biên dịch |
| `java -cp out JavacPatternSyntaxDemo` | Chạy class đã biên dịch; `-cp` là classpath dành cho runtime |

Tạo thư mục `out` trước bằng `mkdir out` giúp lệnh dùng nhất quán trong các môi trường và không phụ thuộc hành vi tạo thư mục của công cụ.

**Lưu ý về `--release`:**

- `--release 21` khác với chỉ dùng `-source 21 -target 21`. `--release` còn kiểm soát **bộ API platform** có thể sử dụng cho bản phát hành đích.
- Không phối hợp `--release` với `--source` hoặc `--target` trên cùng lệnh, vì các tùy chọn này xung đột theo tài liệu `javac`.
- JDK compiler phải hỗ trợ release được chọn; một JDK quá cũ **không thể** biên dịch code Java 21 chỉ bằng cách thêm `--release 21`.
- Record patterns và pattern matching for switch đã ổn định trong Java 21, nên **không cần `--enable-preview`** cho các ví dụ ở đây.
- `--release 17` không phải cách kiểm chứng mã Java 21; nó áp đặt cú pháp/kiểu và API của Java 17, vì thế nhiều cú pháp Java 21 sẽ bị từ chối.

Trong PowerShell, có thể kiểm tra mã thoát của lệnh gần nhất:

~~~powershell
javac --release 21 -encoding UTF-8 -d out JavacPatternSyntaxDemo.java
if ($LASTEXITCODE -ne 0) {
    throw "Compile failed (exit code $LASTEXITCODE)"
}
java -cp out JavacPatternSyntaxDemo
~~~

Đừng chạy lệnh `java` trên class output cũ nếu `javac` vừa thất bại: nó có thể tạo cảm giác code mới chạy đúng dù JVM đang chạy bytecode của lần biên dịch trước.

## 5. Bộ ví dụ đúng: record patterns và `switch` của Java 21

Tạo file **`JavacPatternSyntaxDemo.java`** với mã sau:

~~~java
public class JavacPatternSyntaxDemo {
    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}
    record Rectangle(int width, int height) implements Shape {}

    static String describe(Shape shape) {
        return switch (shape) {
            case null -> "Không có hình";

            case Circle(var r) when r <= 0 ->
                "Bán kính không hợp lệ";

            case Circle(var r) ->
                "Hình tròn r=" + r;

            case Rectangle(var w, var h)
                    when w <= 0 || h <= 0 ->
                "Kích thước không hợp lệ";

            case Rectangle(var w, var h) -> {
                int area = w * h;
                yield "Hình chữ nhật S=" + area;
            }
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Circle(3)));
        System.out.println(describe(new Circle(0)));
        System.out.println(describe(new Rectangle(2, 5)));
        System.out.println(describe(new Rectangle(0, 7)));
        System.out.println(describe(null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
mkdir out
javac --release 21 -encoding UTF-8 -d out JavacPatternSyntaxDemo.java
java -cp out JavacPatternSyntaxDemo
~~~

**Đầu ra:**

~~~text
Hình tròn r=3
Bán kính không hợp lệ
Hình chữ nhật S=10
Kích thước không hợp lệ
Không có hình
~~~

Những điểm compiler kiểm tra được:

1. `Shape` là sealed interface và chỉ cho phép `Circle`, `Rectangle`.
2. `Circle(var r)` có đúng một component; `Rectangle(var w, var h)` có đúng hai.
3. `var r`, `var w`, `var h` được suy luận theo kiểu component của record (ở đây đều là `int`).
4. Các biến pattern chỉ dùng ở vị trí đã khớp, gồm guard và thân case tương ứng.
5. Case có guard đặc biệt đứng trước case tổng quát của cùng record, tránh dominance.
6. `switch expression` bao quát cả hai subtype của `Shape`, và xử lý selector null bằng `case null`.
7. Nhánh có block `{ ... }` dùng `yield` để tạo giá trị của switch expression.

**Điểm `javac` không thể kết luận:** trong hệ thống nghiệp vụ thực tế, bán kính âm có nên ném exception thay vì trả thông điệp hay không; diện tích `int` có thể overflow không; cách hiển thị tiếng Việt có đáp ứng yêu cầu hay không. Những phần này cần test và lựa chọn thiết kế.

## 6. Chẩn đoán lỗi syntax: thiếu dấu câu hoặc viết sai cấu trúc

Ví dụ **cố ý không biên dịch**:

~~~java
public class SyntaxError {
    static int calculate() {
        int n = 1
        return n;
    }
}
~~~

Compiler thường chỉ vào vùng gần cuối dòng thiếu dấu `;` với thông báo:

~~~text
error: ';' expected
~~~

Cách sửa:

~~~java
public class SyntaxError {
    static int calculate() {
        int n = 1;
        return n;
    }
}
~~~

Một số lỗi syntax thường gặp:

- Thiếu `;` ở cuối khai báo biến hoặc câu lệnh hợp lệ cần dấu chấm phẩy.
- Thiếu dấu `}` khiến parser báo lỗi gần cuối file (ví dụ `reached end of file while parsing`).
- Dùng nhãn `case` sai cấu trúc; ví dụ `case String s when ...` nhưng đặt sai vị trí `->`.
- Viết `yield` trực tiếp sau mũi tên như `case 1 -> yield 10;`; trong switch expression nên dùng `case 1 -> 10;` hoặc `case 1 -> { yield 10; }`.
- Quên `;` **sau toàn bộ switch expression** khi dùng làm initializer hoặc `return` expression statement.

Hãy sửa từ **lỗi đầu tiên** trước. Một dấu ngoặc hoặc dấu chấm phẩy thiếu có thể khiến parser mất đồng bộ và báo nhiều lỗi theo sau không phải nguyên nhân gốc.

Thông báo cụ thể và vị trí dòng/cột có thể khác giữa các phiên bản JDK; nên xem **mã nguồn gần ký hiệu `^` và vài dòng ngay trước nó**, không chỉ đọc câu thông báo.

## 7. Lỗi compile-time không phải syntax thuần: record pattern sai cấu trúc

Compiler hiểu cú pháp `Point(...)` là record pattern, nhưng còn phải kiểm tra **số component và kiểu tương thích**.

### 7.1. Sai số component

~~~java
record Pair(int left, int right) {}

// CỐ Ý SAI: Pair có 2 component, pattern chỉ có 1.
// if (value instanceof Pair(var a)) {
//     System.out.println(a);
// }
~~~

Một diagnostic có thể là:

~~~text
incorrect number of nested patterns
required: int,int
found:    int
~~~

Cách sửa:

~~~java
if (value instanceof Pair(var a, var b)) {
    System.out.println(a + b);
}
~~~

Cùng một pattern không thể bỏ bớt component chỉ vì không cần dùng nó. Có thể đặt tên bỏ qua như `ignored` ở vị trí tương ứng: `Pair(var a, var ignored)`.

### 7.2. Sai kiểu component

~~~java
// CỐ Ý SAI: component đầu của Pair là int.
// if (value instanceof Pair(String a, int b)) { ... }
~~~

Diagnostic có thể là:

~~~text
incompatible types: int cannot be converted to java.lang.String
~~~

Không được đồng nhất kiểu `int` với `String` chỉ vì cả hai có thể hiển thị thành text. Sửa bằng `Pair(int a, int b)` hoặc `Pair(var a, var b)`.

**Bài học:** các lỗi trong mục này thuộc **kiểm tra kiểu và tính hợp lệ của pattern**, không nhất thiết là lỗi parser. Chạy `javac` là cách xác nhận cả hai nhóm lỗi trong cùng một quy trình.

## 8. Lỗi compile-time khác: switch không exhaustive

Switch **expression** cần bao quát đầy đủ các giá trị theo luật ngôn ngữ. Ví dụ:

~~~java
// CỐ Ý SAI; Object có thể là nhiều kiểu khác String.
static String onlyString(Object value) {
    return switch (value) {
        case String s -> s;
    };
}
~~~

Compiler có thể báo:

~~~text
the switch expression does not cover all possible input values
~~~

Bổ sung nhánh phù hợp:

~~~java
static String className(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "String: " + s;
        default -> "Loại khác";
    };
}
~~~

**Tại sao không có `default` trong chương trình chính ở mục 5?** Vì selector `Shape` là sealed hierarchy với hai subtype được phép, và switch xử lý cả hai; compiler có thể chứng minh exhaustive. Trong ví dụ `Object` rộng ở trên, chỉ có `String` thì chưa đủ.

**Không nhầm exhaustiveness với null-safety:** đối với reference selector, một switch exhaustive nhưng thiếu `case null` vẫn có thể ném `NullPointerException` khi nhận null. Việc kiểm tra loại lỗi này phải có runtime test, không thể suy ra an toàn chỉ từ thành công của `javac`.

## 9. Lỗi dominance: nhánh chung che nhánh có guard

Code có thể đúng cấu trúc token nhưng sai thứ tự case:

~~~java
// CỐ Ý SAI: case String tổng quát đứng trước case có guard.
static String classify(Object value) {
    return switch (value) {
        case String s -> s;
        case String s when s.isBlank() -> "blank";
        default -> "other";
    };
}
~~~

Compiler có thể báo:

~~~text
this case label is dominated by a preceding case label
~~~

Vì `case String s` đầu tiên đã nhận mọi String không null, nhánh `String` có guard ở sau không còn cơ hội được chọn. Sửa:

~~~java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s -> s;
        default -> "other";
    };
}
~~~

Lưu ý rằng `String s when s.isBlank()` chỉ áp dụng khi type pattern đã khớp và biến `s` tồn tại trong guard. Nếu đặt điều kiện sử dụng biến trước nơi khai báo pattern, compiler báo lỗi phạm vi/không tìm thấy symbol.

**Đọc thông điệp theo nguyên nhân:** `dominated case`, `non-exhaustive switch` và `incompatible types` đều là vấn đề compile-time, nhưng mỗi loại có cách sửa **khác nhau**. Không xử lý tất cả bằng cách thêm một `default` cho có.

## 10. `--release` và lỗi do dùng syntax không đúng phiên bản

Mã có `record pattern` và `switch` pattern Java 21 cần compiler hiểu ngôn ngữ Java 21. Ví dụ:

~~~bash
javac --release 21 -encoding UTF-8 -d out JavacPatternSyntaxDemo.java
~~~

Nếu thay thành:

~~~bash
javac --release 17 -encoding UTF-8 -d out JavacPatternSyntaxDemo.java
~~~

bạn đang yêu cầu **cú pháp và API của Java 17**, vốn không có các record/switch patterns theo dạng Java 21 đã chuẩn hóa. Compiler sẽ từ chối các tính năng chưa tương thích với release đó; đây là lỗi **configuration/language level**, không phải do dữ liệu của record.

Cần phân biệt các tùy chọn:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--release 21` | Source rules, target bytecode và API platform theo Java 21 |
| `-source 21` | Quy tắc ngôn ngữ Java 21 (không tự ràng buộc API platform giống `--release`) |
| `-target 21` | Target class file version, không tự kiểm tra API cho Java 21 |
| `--enable-preview` | Bật tính năng preview **của phiên bản compiler/release phù hợp**, không cần cho record patterns/pattern switch đã chuẩn trong Java 21 |
| `-encoding UTF-8` | Cách đọc ký tự trong file nguồn, không ảnh hưởng language level |

Không dùng `--enable-preview` như “cách sửa chung” cho mọi syntax error. Nó chỉ liên quan các tính năng **đang ở trạng thái preview trong release tương ứng** và có quy tắc version riêng; không thể biến một compiler cũ thành compiler hỗ trợ mọi cú pháp mới.

Nếu một module phải hỗ trợ Java 17, **viết lại mã** theo các tính năng Java 17 hỗ trợ hoặc thay đổi yêu cầu sản phẩm/runtime một cách có chủ đích; không chỉ thay cờ trên command line.

## 11. Dùng diagnostics của `javac` hiệu quả

Khi cần thông báo chi tiết:

~~~bash
javac --release 21 -encoding UTF-8 -d out \
  -Xdiags:verbose -Xmaxerrs 50 JavacPatternSyntaxDemo.java
~~~

Lệnh trên dùng dấu nối dòng `\` của shell Bash. Trên **Windows PowerShell**, viết cùng lệnh thành một dòng:

~~~powershell
javac --release 21 -encoding UTF-8 -d out -Xdiags:verbose -Xmaxerrs 50 JavacPatternSyntaxDemo.java
~~~

Ý nghĩa:

- `-Xdiags:verbose`: yêu cầu định dạng diagnostic **chi tiết hơn** khi compiler có thêm thông tin.
- `-Xmaxerrs 50`: đặt số lỗi tối đa được hiển thị; có thể hữu ích khi nhiều file cùng lỗi, nhưng cần đọc lỗi đầu trước.
- `-Xlint:all`: bật nhiều cảnh báo lint liên quan đến Java; giúp phát hiện nguy cơ như unchecked/deprecation, nhưng **không biến cú pháp hợp lệ thành lỗi syntax**.
- `-Werror`: coi warning là lỗi, hữu ích nếu policy CI yêu cầu không có warning; không tự động giúp code đúng nghiệp vụ.

Ví dụ chạy lint riêng:

~~~bash
javac --release 21 -encoding UTF-8 -Xlint:all -d out JavacPatternSyntaxDemo.java
~~~

Đừng chạy `-Werror` trước khi hiểu warning nào xuất hiện, vì project có annotation processors, thư viện phụ thuộc hoặc code legacy có thể có nhiều cảnh báo cần kế hoạch xử lý riêng.

**Quan trọng:** `-proc:none` chỉ **tắt annotation processing**, không phải “parse-only”. `-proc:only` chỉ chạy annotation processors mà không biên dịch đầy đủ class; nó cũng **không phải tùy chọn bảo đảm kiểm tra mọi semantic error rồi dừng**. `javac` CLI không có một cờ chuẩn duy nhất biến quá trình compile đầy đủ thành “chỉ parse syntax và chắc chắn không tạo output”. Nếu cần kiểm tra syntax đơn thuần cho editor/tooling, xem Compiler API/IDE parser phù hợp; nếu cần xác nhận mã build được, hãy biên dịch thật.

## 12. Khi thiếu classpath: lỗi phụ thuộc không phải lỗi cú pháp

Ví dụ:

~~~java
import com.example.library.Widget;

public class UsesWidget {
    Widget widget;
}
~~~

Nếu thư viện chứa `Widget` không nằm trong classpath, `javac` có thể báo:

~~~text
package com.example.library does not exist
cannot find symbol
~~~

Đây là lỗi **không resolve được dependency**, không nhất thiết file Java sai syntax.

Với project Java thông thường (không dùng module), truyền classpath:

~~~bash
javac --release 21 -cp "lib/*" -d out src/UsesWidget.java
~~~

Trên Windows, nếu cần nhiều entry riêng trong classpath, ký tự phân tách mặc định là **`;`**; trên Linux/macOS là **`:`**. Dùng ký tự phù hợp OS, ví dụ:

~~~powershell
javac --release 21 -cp "lib/*;out" -d out src/UsesWidget.java
~~~

Với named modules, có thể cần `--module-path` thay vì hoặc cùng với classpath theo module graph. Không nên sửa các import đúng thành code giả chỉ để compiler ngừng báo lỗi; hãy kiểm tra **dependency, phiên bản, package name, classpath/modulepath và source path**.

Nếu project có Gradle/Maven, một lệnh build chính thức (ví dụ `mvn compile` hoặc `gradle compileJava`) thường thiết lập các phần phụ thuộc tự động. Tuy nhiên lệnh `javac` trực tiếp vẫn hữu ích để cô lập một ví dụ tối giản không có dependency phức tạp.

## 13. Compile mã nhiều file và kiểm tra cấu trúc package

Ví dụ project:

~~~text
src/
  demo/
    Point.java
    Main.java
out/
~~~

Trong `Point.java` và `Main.java`, nếu khai báo `package demo;`, các file nguồn cần khớp package và các public top-level types phải nằm trong file cùng tên:

~~~java
// src/demo/Point.java
package demo;

public record Point(int x, int y) {}
~~~

~~~java
// src/demo/Main.java
package demo;

public class Main {
    public static void main(String[] args) {
        Point p = new Point(2, 3);
        System.out.println(p);
    }
}
~~~

Lệnh:

~~~bash
mkdir out
javac --release 21 -encoding UTF-8 -d out src/demo/Point.java src/demo/Main.java
java -cp out demo.Main
~~~

Đầu ra:

~~~text
Point[x=2, y=3]
~~~

`-d out` đặt `demo/Point.class` và `demo/Main.class` ở dưới cây output. Khi chạy, dùng **tên class đầy đủ** `demo.Main` chứ không dùng `Main` nếu class đã có package.

Nếu chỉ compile một file nhưng nó dùng type ở file khác, compiler có thể tự tìm source theo source path/classpath trong một số trường hợp; để giảm bất ngờ, khi tạo ví dụ độc lập hãy liệt kê đủ file nguồn hoặc dùng hệ thống build dự án.

## 14. Lỗi ở runtime không thể được loại bỏ chỉ bằng `javac`

Mã hợp lệ:

~~~java
Object input = null;

String result = switch (input) {
    case String s -> "Text: " + s;
    default -> "Other";
};
~~~

Trong Java 21, đoạn code trên **có thể biên dịch**, vì xét theo source rules, switch expression đã exhaustive với `default`. Nhưng khi chạy, selector null và **không có `case null`**, kết quả là **`NullPointerException`**, không phải `"Other"`.

Sửa nếu null là đầu vào hợp lệ:

~~~java
String result = switch (input) {
    case null -> "No input";
    case String s -> "Text: " + s;
    default -> "Other";
};
~~~

Ngoài NPE, compiler cũng không xác nhận được:

- Phép nhân `width * height` có tràn `int` hay không với các giá trị lớn.
- Một chuỗi tiếng Việt đang hiển thị đúng theo kỳ vọng của người dùng hay không.
- Hàm đã xử lý đủ boundary cases và trạng thái domain hay chưa.
- Performance/latency có đáp ứng yêu cầu không.
- Luồng đa luồng có race condition hay không.

Vì vậy nên **biên dịch + unit tests + runtime checks**. Với record patterns và `when`, viết test cho pattern match, guard true/false, null selector, nested component null, và đường error path.

## 15. Quy trình 8 bước debug lỗi từ compiler

1. **Xác minh toolchain**: chạy `javac -version`, `java -version`; xác nhận JDK hỗ trợ language level.
2. **Xác định file nguồn và compile command**: đúng tên public class/record, đúng package, đường dẫn, classpath.
3. **Cố định release**: dùng `--release 21` cho ví dụ Java 21, không nhầm với `-target` đơn lẻ.
4. **Đọc lỗi đầu tiên**: tìm `file:line:column`/dấu `^` và xem ngữ cảnh vài dòng trước đó.
5. **Phân loại lỗi**: parsing, type/flow scoping, record pattern arity, dominance/exhaustiveness, missing dependency, preview/release.
6. **Sửa nguyên nhân nhỏ nhất**: thiếu `;` → thêm `;`; sai component → đối chiếu khai báo record; case dominance → sắp xếp case; không exhaustive → thêm nhánh hợp lý.
7. **Chạy lại `javac`**: không dựa vào số lượng lỗi cũ sau khi nguồn đã đổi; nếu cần mở `-Xdiags:verbose`.
8. **Chạy chương trình/test**: kiểm tra stdout, exception, các nhánh guard và dữ liệu cạnh biên; thành công compile chỉ là cổng đầu tiên.

Một bảng phân loại nhanh:

| Diagnostic/trạng thái | Nhóm lỗi | Điều nên kiểm tra |
| --- | --- | --- |
| `';' expected` | Parsing/syntax | Thiếu dấu kết thúc câu lệnh, cấu trúc trước dòng lỗi |
| `reached end of file while parsing` | Parsing/syntax | Thiếu `}`/`)` hoặc đoạn code chưa hoàn chỉnh |
| `incorrect number of nested patterns` | Record pattern structure | Số record components và vị trí pattern |
| `incompatible types` | Type checking | Kiểu component/static expression |
| `cannot find symbol` | Name resolution/dependency | Tên biến, import, scope, classpath |
| `switch expression does not cover ...` | Exhaustiveness | Những kiểu/giá trị còn thiếu |
| `case label is dominated` | Dominance | Thứ tự các type pattern, case tổng quát và guard |
| `source release ... not supported` | Toolchain | `javac -version` và language level |
| `package ... does not exist` | Classpath/modulepath | Dependency, đường dẫn, module |
| Không có compile error nhưng runtime NPE | Runtime | Selector null, component null, code branch |

Thông báo trên là **ví dụ dạng lỗi**, không phải cam kết từng chữ của mọi bản JDK. Việc thêm `-Xdiags:verbose` và đọc cả vị trí nguồn sẽ cho thông tin phù hợp với compiler bạn đang dùng.

## 16. Những hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `javac` chỉ kiểm tra syntax | Nó còn kiểm tra kiểu, scope, exhaustiveness, API/dependency | Phân loại lỗi compile-time theo bản chất |
| `javac` thành công nghĩa là không còn bug | Runtime/logic/concurrency vẫn có thể sai | Chạy unit/integration tests |
| Không thấy output từ `javac` nghĩa là nó chưa chạy | Compile thành công thường im lặng | Kiểm tra exit code và class output |
| `--target 21` đủ để dùng Java 21 syntax/API | `--target` chỉ điều khiển class file target | Ưu tiên `--release 21` |
| JDK 17 + `--release 21` sẽ tự hỗ trợ Java 21 | Compiler cũ không biết release mới | Cài và chọn JDK 21+ |
| Bật `--enable-preview` sửa mọi lỗi pattern | Preview chỉ phù hợp phiên bản/tính năng cụ thể | Dùng Java 21 stable features, không bật preview khi không cần |
| `-proc:none` là chỉ kiểm tra syntax | Nó chỉ tắt annotation processing, vẫn compile | Dùng `javac` để xác nhận build; chọn parser API nếu thật sự chỉ cần parse |
| Nhánh có `default` luôn an toàn null | Switch reference selector null vẫn có thể NPE | `case null` hoặc kiểm tra trước switch |
| Thêm `default` luôn là cách sửa switch không exhaustive tốt nhất | Có thể che việc thêm subtype sealed mới | Thêm case đúng domain, tận dụng exhaustive checking |
| Thấy `cannot find symbol` là sai cú pháp | Có thể là thiếu dependency/biến ngoài scope | Kiểm tra import, classpath, name resolution |
| Chỉ chạy `java` sau khi chỉnh nguồn | Có thể chạy bytecode cũ | Recompile, kiểm tra exit code trước khi run |
| Dùng một file JDK 21 code với `--release 17` để “test compatibility” mà không điều chỉnh | Java 17 chưa hỗ trợ nhiều cú pháp Java 21 | Dùng source code phù hợp release cần hỗ trợ |

## 17. Bài tập thực hành

**Bài 1 — Lỗi syntax thực sự.** Đoạn sau thiếu gì? Dự đoán loại diagnostic và sửa lại.

~~~java
static int answer() {
    int x = 40
    return x + 2;
}
~~~

**Bài 2 — Record pattern arity.** Với `record RGB(int r, int g, int b) {}`, tại sao `obj instanceof RGB(var r, var g)` không biên dịch? Nếu không cần dùng `b`, có thể viết gì?

**Bài 3 — Dominance.** Với hai nhánh `case String s` và `case String s when s.isBlank()`, nên đặt nhánh nào trước? Có thay đổi thứ tự là đủ hay cần sửa cả selector null?

**Bài 4 — Switch exhaustive.** Cho `sealed interface Task permits Print, Save {}` và hai record triển khai nó. Viết switch expression trả chuỗi cho cả hai subtype. Giải thích vì sao compiler có thể không cần `default` và vì sao vẫn nên quyết định chính sách null.

**Bài 5 — Tooling.** Một máy có `java -version` là 21 nhưng `javac -version` là 17. Bạn sẽ kiểm tra gì trước khi biên dịch chương trình dùng record patterns? Có nên dùng `--enable-preview` để sửa không?

**Bài 6 — Compiler không bắt bug runtime.** Một method nhận `Object` và dùng `switch` có `default` nhưng không có `case null`. Compiler chấp nhận. Với input null, runtime xảy ra gì? Viết một test xác nhận chính sách mới sau khi thêm `case null`.

**Đáp án gợi ý:**

~~~java
// 1
static int answer() {
    int x = 40;
    return x + 2;
}

// 2: đủ cả ba component patterns
if (obj instanceof RGB(var r, var g, var ignoredB)) {
    System.out.println(r + g);
}

// 3: nhánh có guard đứng trước nhánh String tổng quát
case String s when s.isBlank() -> "blank";
case String s -> s;
~~~

- Bài 4: sealed hierarchy được compiler biết tập subtype hợp lệ; khi xử lý đủ, switch expression có thể exhaustive. Null reference vẫn cần chính sách riêng.
- Bài 5: xem `PATH`/`JAVA_HOME`, chọn JDK 21+ cho compiler; Java 21 record patterns/switch patterns đã ổn định nên không cần `--enable-preview`.
- Bài 6: thiếu `case null` có thể gây `NullPointerException` runtime. Thêm xử lý null rõ ràng và test `classify(null)` bằng assertion.

## 18. Tóm tắt ghi nhớ

- **`javac` là phép thử compile-time**: kiểm tra syntax, kiểu, scope, cấu trúc pattern, dominance/exhaustiveness và khả năng resolve API/dependency; không đảm bảo correctness runtime.
- **Bắt đầu bằng `javac -version`**, dùng `--release 21` để biên dịch Java 21, `-encoding UTF-8` cho Unicode và `-d out` để tách class output.
- **Đọc lỗi đầu tiên** và phân loại đúng: thiếu dấu câu ≠ kiểu component sai ≠ thiếu dependency ≠ switch không exhaustive.
- **Dùng diagnostic flags khi cần** (`-Xdiags:verbose`, `-Xlint:all`, `-Xmaxerrs`) nhưng đừng xem chúng là thay thế cho tests.
- **Biên dịch thành công rồi mới chạy** code bằng `java`, kiểm tra cả kết quả, exception và edge cases.
- Với pattern matching Java 21, **case order, record component arity, flow scoping, null và exhaustive switch** là những nguồn lỗi quan trọng mà compiler hoặc test có thể giúp phát hiện.

### Nguồn tham khảo

- [Oracle Java SE 21 — The javac Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): cú pháp lệnh `javac`, `--release`, `-d`, `-cp`, `-proc` và diagnostic options.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): case patterns, `when`, dominance và exhaustiveness.
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440): deconstruction và component patterns trong Java 21.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
