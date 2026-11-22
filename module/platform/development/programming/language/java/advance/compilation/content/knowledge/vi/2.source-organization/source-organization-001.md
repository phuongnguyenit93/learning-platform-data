# Tệp nguồn, khai báo kiểu và quy tắc tên lớp `public» trong Java

Một chương trình Java thường được viết trong các tệp `.java». Để tổ chức mã nguồn và biên dịch đúng, cần phân biệt **tệp nguồn**, **đơn vị biên dịch (compilation unit)**, **khai báo kiểu top-level**, **kiểu lồng (nested type)** và **tệp bytecode `.class»**. Quy tắc tên tệp gắn với kiểu `public» ở cấp cao nhất là một trong những quy tắc dễ gây lỗi `javac» nhất.

## 1. Tệp `.java» chứa những gì?

Một tệp nguồn thông thường (`ordinary compilation unit») có cấu trúc tổng quát:

```java
// Chú thích (nếu có)
package com.example.compilation; // Tối đa một khai báo package, nếu có

import java.util.List;         // Các import, nếu có
import static java.lang.Math.max;

// Các khai báo kiểu top-level
public class App {
    // Thành viên và các kiểu lồng nằm bên trong App
}

class Helper {
    // Kiểu top-level không public
}
```

Đây là **mẫu cấu trúc**, không phải chương trình độc lập để chạy. Các điểm cần nhớ:

- Khai báo `package» đứng trước `import» và các khai báo kiểu (không tính chú thích và annotation áp dụng cho package). Nếu không có `package», tệp thuộc **unnamed package**.
- Các `import» đứng sau `package» (nếu có) và trước mọi khai báo kiểu top-level. `import» giúp dùng tên đơn của kiểu/thành viên; nó không chép mã vào tệp và không tạo quan hệ kế thừa.
- Một compilation unit có thể chứa **nhiều kiểu top-level**. Với tệp nguồn trên hệ tệp dùng bởi `javac», nhiều nhất **một kiểu top-level có modifier `public»** và tên tệp phải khớp với kiểu đó.
- Kiểu top-level gồm `class», `interface», `enum», `record» (Java 16+) và annotation interface `@interface». Kiểu khai báo **bên trong** một kiểu khác là nested type và tuân theo quy tắc khác.
- Một tệp `.java» có thể sinh ra **nhiều tệp `.class»**. Tên tệp nguồn và số lượng tệp bytecode không có quan hệ một-một.

Trong Java, thuật ngữ **top-level** mô tả vị trí khai báo trực tiếp trong compilation unit, bên ngoài mọi class/interface/enum/record khác. `public» trên một phương thức hoặc lớp lồng không biến nó thành kiểu top-level.

## 2. Quy tắc tên tệp của kiểu `public» top-level

Với cách biên dịch Java thông dụng bằng `javac», nếu một tệp có kiểu top-level `public» tên `X», tệp nguồn phải tên chính xác `X.java». Điều này áp dụng cho mọi dạng kiểu top-level:

| Khai báo | Tên tệp nguồn |
| --- | --- |
| `public class App» | `App.java» |
| `public interface Service» | `Service.java» |
| `public enum Status» | `Status.java» |
| `public record Point(int x, int y)» | `Point.java» |
| `public @interface Audited» | `Audited.java» |

Ví dụ hợp lệ — tệp `Greeting.java»:

```java
public class Greeting {
    public static void main(String[] args) {
        System.out.println("Xin chao Java");
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 Greeting.java
java Greeting
```

Đầu ra:

```text
Xin chao Java
```

Nếu giữ nguyên nội dung nhưng lưu trong `Hello.java», `javac Hello.java» báo lỗi đại ý: `class Greeting is public, should be declared in a file named Greeting.java». Trên các hệ tệp phân biệt chữ hoa/chữ thường, `Greeting.java» và `greeting.java» là hai tên khác nhau. Hãy luôn dùng tên khớp **đúng chữ hoa, chữ thường**.

Hai kiểu top-level `public» trong cùng một tệp không hợp lệ với tổ chức tệp thông thường:

```java
// Sai nếu đặt cả hai trong Application.java
public class Application {
}

public interface Command {
}
```

Tách thành `Application.java» và `Command.java». Không thể sửa lỗi bằng cách đặt tên tệp `ApplicationCommand.java», vì mỗi kiểu `public» vẫn đòi hỏi tên tệp riêng.

**Không có kiểu top-level `public» thì sao?** Java cho phép tệp tên khác với các kiểu package-private trong đó. Ví dụ, `Utilities.java» có thể chứa `class Parser» và `class Formatter» (đều không `public»). Tuy nhiên, đặt mỗi kiểu top-level vào tệp cùng tên vẫn là lựa chọn thực tế giúp IDE, người đọc và cơ chế tìm tệp nguồn của trình biên dịch làm việc dễ hơn.

## 3. Phân biệt modifier ở cấp top-level và bên trong kiểu

Một kiểu top-level thông thường có thể khai báo `public» hoặc không có modifier truy cập (gọi là **package-private**). Không được khai báo kiểu top-level bằng `private», `protected» hay `static».

```java
// Sai ở cấp top-level:
private class InternalOnly {
}
```

Lưu ý: `final», `abstract», `sealed» và các modifier phù hợp khác là chuyện riêng với **access modifier**; việc có thể dùng modifier nào còn phụ thuộc loại kiểu và quan hệ kế thừa.

Ví dụ hợp lệ — tệp `Main.java» có hai kiểu top-level, nhưng chỉ một kiểu `public»:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("Ket qua: " + Calculator.twice(21));
    }
}

class Calculator {
    static int twice(int value) {
        return value * 2;
    }
}
```

Lệnh chạy:

```bash
javac Main.java
java Main
```

Đầu ra:

```text
Ket qua: 42
```

`javac» tạo `Main.class» và `Calculator.class» dù nguồn chỉ có `Main.java». `Calculator» có thể được mã ở cùng package truy cập theo quy tắc package-private; nó không trở thành `public» chỉ vì cùng tệp với `Main».

Trái lại, kiểu lồng được khai báo **bên trong** kiểu khác và có thể có các modifier truy cập phù hợp:

```java
// Tệp Outer.java
public class Outer {
    public static class Nested {
        public String message() {
            return "nested";
        }
    }

    public static void main(String[] args) {
        System.out.println(new Outer.Nested().message());
    }
}
```

```bash
javac Outer.java
java Outer
```

Đầu ra:

```text
nested
```

Không cần tạo `Nested.java» cho `public static class Nested»: tên tệp bắt buộc chỉ là `Outer.java» do `Outer» mới là kiểu top-level `public». Thông thường compiler tạo `Outer.class» và `Outer$Nested.class». Trong mã Java, tham chiếu đến kiểu lồng bằng `Outer.Nested»; ký tự `$» là một phần cách biểu diễn tên nhị phân của kiểu lồng.

## 4. `package» và đường dẫn nguồn: quy tắc ngôn ngữ so với thông lệ công cụ

Giả sử dự án có:

```text
project/
└── src/
    └── com/
        └── example/
            └── compilation/
                └── App.java
```

Nội dung `src/com/example/compilation/App.java»:

```java
package com.example.compilation;

public class App {
    public static void main(String[] args) {
        System.out.println("Goi tu package");
    }
}
```

Tên đầy đủ của kiểu là `com.example.compilation.App». Khai báo `package» quyết định package logic của kiểu; cấu trúc thư mục `com/example/compilation/» là **quy ước rất quan trọng của Java toolchain** để tìm mã nguồn nhất quán. Nó không phải là một câu lệnh Java tự tạo package bằng cách di chuyển tệp trên đĩa.

Từ thư mục `project», tạo thư mục `out» trước, rồi chạy:

```bash
mkdir out
javac -encoding UTF-8 -d out src/com/example/compilation/App.java
java -cp out com.example.compilation.App
```

Đầu ra:

```text
Goi tu package
```

Sau biên dịch, vị trí tệp được tạo:

```text
out/
└── com/
    └── example/
        └── compilation/
            └── App.class
```

Ở đây:

- `-d out» là thư mục gốc chứa bytecode đầu ra; `javac» tạo các thư mục con tương ứng với package, nhưng thư mục `out» cần tồn tại trước.
- `-cp out» đưa **gốc classpath** vào lệnh chạy; không truyền đường dẫn tới `App.class».
- `java com.example.compilation.App» (với classpath đúng) yêu cầu tên lớp đầy đủ có package. `java App» sẽ không tìm thấy kiểu vừa biên dịch trong package này.
- Không nên suy đoán package từ đường dẫn tệp hoặc ngược lại; đọc câu lệnh `package» rồi kiểm tra đường dẫn nguồn và cấu hình build cho nhất quán.

Trong dự án dùng Maven/Gradle, mã production thường ở `src/main/java/» và mã test ở `src/test/java/»; build tool sẽ cấu hình đường dẫn nguồn, classpath và thư mục đầu ra. Ví dụ `src/com/example/.../» ở trên cố ý là ví dụ `javac» tối giản độc lập.

## 5. Nhiều khai báo kiểu trong một tệp: hợp lệ nhưng có đánh đổi

Ví dụ `Names.java» không có kiểu `public»:

```java
class FirstName {
    static String value() {
        return "An";
    }
}

class LastName {
    static String value() {
        return "Nguyen";
    }
}
```

Biên dịch `javac Names.java» tạo `FirstName.class» và `LastName.class»; **không** tạo `Names.class» vì không hề có khai báo kiểu `Names». Có thể có nhiều kiểu top-level không `public» trong một tệp, miễn không trùng tên kiểu trong cùng package.

Tuy nhiên, khi tệp `App.java» chỉ tham chiếu `FirstName» mà `Names.java» chưa được biên dịch, việc `javac» tự tìm nguồn theo tên kiểu có thể không phát hiện một kiểu nằm trong tệp khác tên. Có thể chỉ rõ cả hai tệp nguồn, cấu hình source path đúng, hoặc tổ chức `FirstName.java» chứa `class FirstName». Với mã dự án, **một kiểu top-level chính trên một tệp cùng tên** giúp việc tìm kiếm, điều hướng và biên dịch tăng dần dễ dự đoán hơn.

```bash
javac Names.java
```

Đừng nhầm **một kiểu top-level chính mỗi tệp** (quy ước thiết kế) với **tối đa một kiểu top-level `public» mỗi tệp** (quy tắc biên dịch thông thường).

## 6. Cách công cụ tìm nguồn và xuất bytecode

Ba khái niệm thường dễ bị trộn lẫn:

| Khái niệm | Dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| Tệp nguồn | Cung cấp declaration và thân mã Java | `src/com/example/compilation/App.java» |
| Tên kiểu đầy đủ | Xác định kiểu theo package và tên đơn | `com.example.compilation.App» |
| Tệp lớp đầu ra | Lưu bytecode cho JVM và class loader | `out/com/example/compilation/App.class» |

Với trình biên dịch `javac», tham số `-sourcepath» (nếu dùng) chỉ nơi tìm các tệp nguồn phụ thuộc; `-classpath» / `-cp» chỉ nơi tìm các class và thư viện đã biên dịch. Khi biên dịch một tập tệp nguồn được chỉ rõ trực tiếp, `javac» có thể biên dịch các kiểu mà những tệp đó khai báo. Cách trình biên dịch tìm kiếm nguồn phụ thuộc vào đường dẫn được cấu hình, vì vậy **tên file khớp tên kiểu top-level** là quy tắc tổ chức đặc biệt hữu ích.

Tệp `.class» không tương đương một-một với tệp `.java»: kiểu top-level bổ sung, nested type, anonymous class hoặc các cấu trúc tạo lớp khi biên dịch có thể sinh nhiều tệp `.class». Hãy phân biệt lỗi **tên tệp nguồn** lúc biên dịch với lỗi **classpath/tên đầy đủ** lúc chạy.

## 7. Các tệp nguồn có vai trò đặc biệt

Ngoài compilation unit thông thường, hệ sinh thái Java còn có hai tên tệp quy ước quan trọng:

- `package-info.java»: thường dùng cho Javadoc và các annotation áp dụng ở mức package. Có thể chứa khai báo `package» (và annotation package); không phải nơi đặt lớp `public class PackageInfo».
- `module-info.java»: mô tả một named module của Java Platform Module System, dùng cú pháp `module», `requires», `exports», ... thay cho khai báo lớp Java thông thường.

Ví dụ về nội dung `module-info.java»:

```java
module com.example.demo {
    exports com.example.demo.api;
}
```

Đây là **một đoạn mô tả module**, chỉ biên dịch được trong dự án có package `com.example.demo.api» tương ứng; nó không phải chương trình độc lập với `main». Hai tên tệp đặc biệt này không thay thế quy tắc đặt tên tệp theo kiểu top-level `public» trong các tệp nguồn thông thường.

Java từ 11 cũng hỗ trợ chạy một tệp nguồn đơn giản bằng `java Greeting.java» (source-file mode). Chế độ chạy này biên dịch mã nguồn trong bộ nhớ và chạy lớp phù hợp; nó **không thay đổi** quy tắc đặt tên kiểu `public» khi tổ chức và biên dịch dự án thông thường bằng `javac». Ví dụ, các lệnh `javac Greeting.java» rồi `java Greeting» ở mục 2 giúp quan sát rõ hai giai đoạn biên dịch và chạy.

## 8. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân điển hình | Cách sửa |
| --- | --- | --- |
| `class X is public, should be declared in a file named X.java» | Tệp không khớp kiểu top-level `public» | Đổi tệp thành `X.java», hoặc đổi tên/thiết kế kiểu có chủ đích |
| Tệp chứa hai kiểu top-level `public» | Hai kiểu cùng đòi tên tệp riêng | Tách thành hai tệp đúng tên |
| `modifier private/protected/static not allowed here» | Gắn modifier của member/nested type lên top-level type | Dùng `public» hoặc package-private ở top-level; hoặc chuyển kiểu thành nested thật sự |
| `class, interface, enum, or record expected» gần `import» | Đặt `import» sau khai báo kiểu hoặc sai cấu trúc compilation unit | Chuyển mọi `import» lên trước các kiểu top-level |
| `duplicate class: p.X» | Có nhiều khai báo cùng tên đầy đủ trong một lượt biên dịch | Kiểm tra package và tên kiểu trùng giữa các tệp |
| `Could not find or load main class ...» | Sai classpath hoặc truyền tên đơn thay tên đầy đủ | Xác nhận `-d»/`-cp», package và tên lớp chứa `main» |

Một lỗi như `cannot find symbol» **không nhất thiết** do thiếu `import»: hãy kiểm tra lần lượt tên kiểu, package, tệp nguồn đã được biên dịch, source path và classpath. `import com.example.*» chỉ import các kiểu trực tiếp trong package đó; nó không tự import kiểu nằm trong subpackage.

## 9. Thực hành tự kiểm chứng

**Bài 1 — dự đoán file output.** Tệp `Example.java» chứa `public class Example» và `class Support», cả hai ở unnamed package. Khi `javac Example.java» thành công, tối thiểu các kiểu này sinh `Example.class» và `Support.class». Điều này cho thấy số kiểu khai báo khác với số tệp nguồn.

**Bài 2 — phân loại sai đúng.** Đánh giá từng trường hợp:

1. `Thing.java» chứa `public interface Thing»: **hợp lệ**.
2. `Thing.java» chứa `public record Thing(int n) {}»: **hợp lệ** với Java 17+.
3. `Thing.java» chứa `public class Other {}»: **không hợp lệ** khi biên dịch bằng `javac» vì tên không khớp.
4. `Toolset.java» chứa `class Parser {}» và `class Printer {}»: **hợp lệ**, tuy có thể tách tệp để dễ bảo trì.
5. `Outer.java» chứa `public class Outer { public static class Inner {} }»: **hợp lệ**; `Inner» là nested type.

**Bài 3 — tự tổ chức một package.** Tạo `src/com/example/compilation/Runner.java» với `package com.example.compilation;», một `public class Runner» có `main», và một helper package-private cùng tệp. Biên dịch bằng `javac -d out» (sau khi tạo `out»), chạy bằng `java -cp out com.example.compilation.Runner», rồi quan sát các tệp `.class» trong thư mục package ở `out».

## 10. Checklist khi tạo hoặc sửa tệp Java

- Xác định đúng kiểu **top-level** và **nested** trước khi áp quy tắc tên tệp.
- Nếu có kiểu top-level `public», tên tệp phải bằng **tên kiểu + `.java»**, khớp chữ hoa/chữ thường; tối đa một kiểu như vậy trong một tệp.
- Các kiểu top-level không `public» có phạm vi package-private; `private», `protected», `static» không phải modifier top-level hợp lệ.
- Đặt `package», rồi `import», rồi các khai báo kiểu theo đúng thứ tự. Giữ package và cây thư mục nguồn nhất quán với build tool.
- Hiểu rằng compiler có thể tạo nhiều `.class» từ một `.java»; gọi chương trình bằng classpath đúng và tên lớp đầy đủ khi có package.
- Khi mã lớn dần, ưu tiên mỗi kiểu top-level chính nằm trong một tệp cùng tên để người đọc và công cụ tìm nguồn ổn định.

**Ghi nhớ:** Quy tắc tên file `X.java» áp dụng trực tiếp cho **kiểu top-level `public X»** trong tổ chức nguồn Java thông thường. Còn kiểu package-private và kiểu lồng có quy tắc riêng. Đọc đúng vị trí khai báo sẽ giúp giải thích phần lớn lỗi liên quan đến tên tệp, `package» và file `.class».