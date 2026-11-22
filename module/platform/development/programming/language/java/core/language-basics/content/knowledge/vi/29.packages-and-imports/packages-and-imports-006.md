# `java.lang` được import ngầm định trong Java

## 1. Ý nghĩa của import ngầm định

Trong Java, mỗi đơn vị biên dịch (*compilation unit*, thông thường là một tệp `.java`) được ngôn ngữ cung cấp cơ chế **import theo yêu cầu** (*on-demand import*) các kiểu truy cập được từ package **`java.lang`**. Vì vậy, lập trình viên thường dùng các tên lớp quen thuộc như `String`, `Object`, `System`, `Math`, `Integer`, `Thread` mà **không cần tự viết** `import java.lang.String;` hay `import java.lang.*;`.

Ví dụ, chương trình sau không có khai báo `import` nào:

```java
public class Hello {
    public static void main(String[] args) {
        String message = "Hello, Java!";
        System.out.println(message);
        System.out.println(Math.max(7, 12));
    }
}
```

Lưu mã vào tệp **`Hello.java`** rồi chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 Hello.java
java Hello
```

Stdout chính xác:

```text
Hello, Java!
12
```

Cả `String`, `System`, `Math` đều thuộc `java.lang`. `javac` phân giải những tên đơn giản này thành các kiểu tương ứng khi không có tên nào khác che khuất hoặc gây xung đột theo quy tắc tra cứu tên của Java.

**Quan trọng:** "import ngầm định" là **quy tắc phân giải tên lúc biên dịch**, không có nghĩa JVM sẽ khởi tạo hoặc tải tất cả lớp trong `java.lang` ngay khi chương trình bắt đầu. Nó cũng không thêm bất kỳ thư viện bên ngoài nào vào classpath.

## 2. `java.lang` chứa những kiểu nào thường gặp?

Package này cung cấp nhiều kiểu cơ bản của ngôn ngữ và runtime Java.

| Kiểu (viết tên đơn giản) | Tên đầy đủ | Vai trò điển hình |
| --- | --- | --- |
| `Object` | `java.lang.Object` | Lớp gốc của các lớp thông thường; cung cấp `toString()`, `equals()`, `hashCode()` |
| `String` | `java.lang.String` | Chuỗi ký tự bất biến |
| `StringBuilder` | `java.lang.StringBuilder` | Xây dựng/chỉnh sửa nội dung chuỗi tuần tự |
| `System` | `java.lang.System` | `System.out`, `System.err`, `System.currentTimeMillis()` và các tiện ích hệ thống |
| `Math` | `java.lang.Math` | Các phép toán tĩnh như `max`, `abs`, `sqrt`, hằng `PI` |
| `Integer`, `Long`, `Double`, `Boolean`, ... | `java.lang.Integer`, ... | Lớp bao (*wrapper*) cho giá trị nguyên thủy; hỗ trợ chuyển đổi/boxing |
| `Throwable`, `Exception`, `RuntimeException`, `Error` | `java.lang.*` tương ứng | Cấu trúc cơ bản của exception và error |
| `Thread`, `Runnable` | `java.lang.Thread`, `java.lang.Runnable` | Khả năng chạy tác vụ/concurrent cơ bản |
| `Enum`, `Record` | `java.lang.Enum`, `java.lang.Record` | Các lớp nền trong hệ thống kiểu của enum và record |

Một số ví dụ cú pháp ngắn, đặt trong phương thức:

```java
String text = "java";
String upper = text.toUpperCase(); // "JAVA"

int max = Math.max(3, 8); // 8
double root = Math.sqrt(81); // 9.0

Integer number = Integer.valueOf("42"); // 42
StringBuilder builder = new StringBuilder("Java");
builder.append(" 17"); // "Java 17"
```

Tất cả tên kiểu ở trên đều có thể dùng trực tiếp. Tuy nhiên **phương thức và trường static** vẫn thường cần tên lớp phía trước, ví dụ `Math.sqrt(81)` hoặc `System.out.println(...)`. Import ngầm định của **kiểu `Math`** không tự đưa tên phương thức `sqrt` vào scope để gọi chỉ bằng `sqrt(81)`.

## 3. Phân biệt `java.lang` với các package khác

Các package khác trong thư viện tiêu chuẩn **không được import ngầm định chỉ vì thuộc JDK**. Ví dụ:

```java
// java.util.List: phải import khi cần dùng tên đơn giản List.
import java.util.List;
import java.util.ArrayList;
```

Sau khi import:

```java
List<String> names = new ArrayList<>();
names.add("An");
```

Hai dòng sau có cùng ý nghĩa kiểu mà không cần lệnh import:

```java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("An");
```

| Tên kiểu | Tự dùng tên đơn giản thông thường? | Cách xử lý |
| --- | --- | --- |
| `String` | Có, qua `java.lang` ngầm định | `String text = "hi";` |
| `Math` | Có, qua `java.lang` ngầm định | `Math.max(1, 2)` |
| `List`, `ArrayList` | Không do `java.lang` | `import java.util.List;`, `import java.util.ArrayList;` |
| `LocalDate` | Không do `java.lang` | `import java.time.LocalDate;` |
| `Files`, `Path` | Không do `java.lang` | `import java.nio.file.Files;`, `import java.nio.file.Path;` |
| `Method` (reflection) | Không do `java.lang` | `import java.lang.reflect.Method;` |
| `MethodHandles` | Không do `java.lang` | `import java.lang.invoke.MethodHandles;` |

**Package con không được import theo package cha.** `java.lang.reflect`, `java.lang.invoke`, `java.lang.management` là các package khác `java.lang`, mặc dù tên bắt đầu bằng `java.lang.`. Do đó:

```java
// Không tự có tên Method từ import ngầm java.lang:
java.lang.reflect.Method[] methods = String.class.getMethods();
System.out.println(methods.length > 0); // true
```

Nếu muốn gọi tên ngắn `Method`, cần `import java.lang.reflect.Method;`. Đoạn trên là ví dụ đặt bên trong một phương thức, không phải tệp chạy độc lập.

## 4. Viết tên đơn giản và tên đầy đủ cho cùng một kiểu

Do import ngầm định, hai khai báo sau thường cùng một kiểu:

```java
String left = "Java";
java.lang.String right = "Java";
System.out.println(left.equals(right)); // true
```

- `String` là **tên đơn giản** của `java.lang.String`.
- `java.lang.String` là **tên đầy đủ** (*fully qualified name*) của kiểu.
- Không có hai loại `String` khác nhau trong đoạn trên; import chỉ giúp tên ngắn được phân giải.
- Viết `import java.lang.String;` là hợp lệ trong tình huống thông thường nhưng **thừa**, vì Java đã cung cấp import theo yêu cầu cho package này.

**Phân giải tên không chỉ phụ thuộc import.** Kiểu được khai báo trong cùng package, kiểu lồng nhau trong scope, hoặc khai báo import cụ thể có thể ảnh hưởng đến ý nghĩa của một tên ngắn. Vì vậy, nếu một dự án tự định nghĩa kiểu `String` hoặc `System`, việc đọc tên không đủ để kết luận chúng là kiểu `java.lang`.

Ví dụ này minh họa một trường hợp **kiểu tự định nghĩa cùng tên** nằm trong package hiện tại:

```java
package demo;

class String {
    // Chỉ để minh họa xung đột tên; không nên dùng tên này trong dự án thực.
}

class Example {
    java.lang.String message = "Hello"; // Chỉ rõ String tiêu chuẩn
}
```

Đây là **một tệp minh họa riêng**, không ghép vào các chương trình bên dưới. Với tên cùng package, `String` không còn có thể mặc nhiên hiểu là `java.lang.String` tại những vị trí bị che khuất. Trong chương trình thực tế, đặt tên kiểu tự định nghĩa sao cho rõ nghĩa và tránh đụng tên các kiểu nền tảng.

Nếu cố import hai kiểu top-level cùng tên đơn giản bằng hai lệnh single-type import khác nhau, trình biên dịch có thể báo xung đột. Khi phải dùng cả hai kiểu cùng tên, dùng tên đầy đủ để làm rõ.

## 5. `import java.lang.*` không đồng nghĩa `import static java.lang.Math.*`

Đây là hai cơ chế khác nhau:

```java
import java.lang.*; // Thừa trong mã thông thường; import các kiểu từ package.
```

```java
import static java.lang.Math.max; // Cho phép gọi max(...) trực tiếp
```

Ví dụ tệp độc lập:

```java
import static java.lang.Math.max;

public class StaticImportDemo {
    public static void main(String[] args) {
        System.out.println(max(5, 9));      // Từ static import
        System.out.println(Math.min(5, 9)); // Math có sẵn qua java.lang
    }
}
```

Lưu thành **`StaticImportDemo.java`**, chạy:

```bash
javac -encoding UTF-8 StaticImportDemo.java
java StaticImportDemo
```

Kết quả:

```text
9
5
```

`import java.lang.*` **không phải** lệnh import mọi phương thức hay field của mọi lớp trong `java.lang`. `import static` làm cho các thành viên static đáp ứng điều kiện truy cập có thể được nhắc tên trực tiếp, nhưng vẫn phải tránh xung đột tên và lạm dụng làm giảm tính rõ ràng.

## 6. Chương trình Java 17+ trong package có tên

Tạo tệp **`src/lesson/LangAutoImportDemo.java`**:

```java
package lesson;

import java.util.ArrayList;
import java.util.List;

public class LangAutoImportDemo {
    public static void main(String[] args) {
        // java.lang: không cần import.
        String text = "Java";
        StringBuilder builder = new StringBuilder(text);
        builder.append(" 17");
        System.out.println("Text: " + builder);

        System.out.println("Max: " + Math.max(4, 9));
        System.out.println("Abs: " + Math.abs(-7));
        System.out.println("PI > 3: " + (Math.PI > 3.0));

        Integer value = Integer.valueOf("42");
        System.out.println("Parsed: " + value);

        Object marker = new Object();
        System.out.println("Object: " + marker.getClass().getSimpleName());

        // java.util: phải import để dùng tên ngắn trong file này.
        List<String> items = new ArrayList<>();
        items.add("One");
        items.add("Two");
        System.out.println("List: " + items);

        // Tên đầy đủ hoạt động mà không cần import kiểu.
        java.lang.String fullName = "ready";
        System.out.println("Full-name String: " + fullName);
        System.out.println("Runtime String: " + String.class.getName());
    }
}
```

Đứng tại thư mục gốc chứa `src`, dùng JDK 17 trở lên. **Tạo thư mục `out` nếu chưa tồn tại** trước khi dùng `-d out`: Bash/Linux/macOS chạy `mkdir -p out`; Windows PowerShell chạy `New-Item -ItemType Directory -Force out | Out-Null` (CMD: `if not exist out mkdir out`). Sau đó dùng lệnh biên dịch/chạy sau trên cả Windows và Linux/macOS:

```bash
javac -encoding UTF-8 -d out src/lesson/LangAutoImportDemo.java
java -cp out lesson.LangAutoImportDemo
```

`-d out` cho phép `javac` tạo cây thư mục theo tên package trong thư mục `out`. `lesson.LangAutoImportDemo` là tên đầy đủ của lớp có `main` khi gọi lệnh `java`.

**Stdout chính xác** (biên dịch thành công không in thông báo):

```text
Text: Java 17
Max: 9
Abs: 7
PI > 3: true
Parsed: 42
Object: Object
List: [One, Two]
Full-name String: ready
Runtime String: java.lang.String
```

Đoạn mã dùng tên đơn giản `String`, `StringBuilder`, `System`, `Math`, `Integer`, `Object` mà không có import riêng. Ngược lại, `List` và `ArrayList` thuộc `java.util`, nên tệp chủ động import các kiểu này.

## 7. Quan hệ với module `java.base`, classpath và biên dịch

Trong Java 9+ (bao gồm Java 17), package `java.lang` thuộc module nền tảng **`java.base`**. Mỗi module Java đều đọc `java.base` theo cơ chế **ngầm định** của hệ thống module. Đây là một cơ chế **khác** với việc import tên kiểu trong source:

- **Package import ngầm định:** cho phép viết `String` thay vì `java.lang.String`.
- **Khả năng đọc module `java.base`:** giúp mã module có thể sử dụng các API công khai được export từ module nền tảng mà không cần viết `requires java.base;` trong `module-info.java`.
- **Classpath/module path:** quyết định khả năng tìm thấy các lớp và module ngoài phạm vi nền tảng. `import` tự nó không tải về dependency hay chỉ đường cho trình biên dịch.
- **Runtime:** kiểu được nạp/khởi tạo theo các quy tắc runtime, không do một dòng import tự thực hiện sẵn.

Những chi tiết module không cần đưa vào mọi bài Java cơ bản, nhưng hữu ích để tránh nhầm `java.lang` tự động có mặt với các cơ chế tìm lớp/thực thi.

## 8. Những lỗi và ngộ nhận thường gặp

| Nhận định/lỗi | Giải thích đúng |
| --- | --- |
| “Phải viết `import java.lang.String;` trước khi dùng `String`.” | Không cần, `java.lang` được import theo yêu cầu ngầm định. |
| “Không cần import bất cứ kiểu nào vì chúng đều nằm trong JDK.” | Sai; `java.util.List`, `java.time.LocalDate`... cần import nếu dùng tên đơn giản (trừ ngữ cảnh đã có sẵn tên phù hợp). |
| “`java.lang.reflect.Method` tự thành `Method`.” | Sai; package con khác package cha, phải import riêng hoặc dùng tên đầy đủ. |
| “Nhờ import `Math`, gọi thẳng `sqrt(9)` được.” | Sai; thường dùng `Math.sqrt(9)` hoặc static import. |
| “`import java.lang.*;` làm JVM nạp hết các lớp.” | Sai; import chỉ ảnh hưởng cách phân giải tên lúc biên dịch. |
| “Tên `String` trong mọi file đều bắt buộc chỉ `java.lang.String`.” | Sai; tên đơn giản còn chịu quy tắc scope và xung đột/che khuất. |
| “`int` và `boolean` là lớp trong `java.lang`.” | Sai; chúng là **kiểu nguyên thủy** của ngôn ngữ, không phải lớp được import. |
| “`java.lang` được import vì chương trình luôn ở package mặc định.” | Sai; import ngầm định vẫn áp dụng cho tệp có `package lesson;` và cho các package được đặt tên khác. |

**Ghi nhớ:** Java tự cho phép dùng tên ngắn của các kiểu phù hợp trong **`java.lang`**, nhưng không import ngầm các package khác hoặc package con. `import` giải quyết **tên trong mã nguồn**; để hiểu chính xác lớp đang dùng, cần xét package, scope và kiểu được phân giải khi biên dịch.