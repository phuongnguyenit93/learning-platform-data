# Lớp cấp cao nhất và nhiều lớp trong một tệp nguồn Java

Một tệp nguồn Java (`.java`) **có thể khai báo nhiều lớp cấp cao nhất (top-level classes)**. Tuy nhiên, với dự án Java thông thường biên dịch bằng `javac`, **tối đa một kiểu cấp cao nhất trong mỗi tệp được khai báo `public`**, và nếu có, **tên tệp phải trùng chính xác tên kiểu `public` đó** (phân biệt chữ hoa/thường). Những lớp còn lại có thể cùng tồn tại trong tệp nếu được khai báo với phạm vi truy cập mặc định của package.

Đây là kiến thức cốt lõi khi đọc mã có nhiều khai báo `class` trong một file, khi tổ chức package hoặc khi thấy trình biên dịch tạo ra nhiều `.class` dù chỉ biên dịch một `.java`.

## 1. Thế nào là lớp cấp cao nhất (top-level class)?

**Lớp cấp cao nhất** là lớp được khai báo **trực tiếp trong đơn vị biên dịch Java** (`compilation unit`), tức không nằm trong thân một lớp/interface/record khác và cũng không nằm trong một phương thức hoặc khối lệnh.

Ví dụ minh họa:

```java
package demo;

public class Main {       // Lớp cấp cao nhất #1
    public static void main(String[] args) {
        Helper.greet();
    }
}

class Helper {            // Lớp cấp cao nhất #2
    static void greet() {
        System.out.println("Xin chào Java");
    }
}
```

Cả `Main` và `Helper` đều là lớp cấp cao nhất. `Helper` không trở thành lớp lồng nhau chỉ vì được viết dưới `Main`. Hai lớp ở **cùng package `demo`**, có tên kiểu và danh tính riêng: `demo.Main` và `demo.Helper`.

Ví dụ trên là một tệp nguồn hợp lệ nếu lưu thành `Main.java` theo cấu trúc package phù hợp. Nó sẽ được kiểm tra và chạy đầy đủ ở phần tiếp theo.

Một tệp nguồn Java thông thường có bố cục:

```text
package ...;             // tùy chọn, tối đa một khai báo
import ...;              // không hoặc nhiều khai báo import
                          // các khai báo top-level:
public class X { ... }
class Y { ... }
class Z { ... }
```

Từng khai báo top-level cũng có thể là `interface`, `enum`, `record` hoặc annotation type (`@interface`), ngoài `class` thông thường. Quy tắc tên tệp và một khai báo top-level `public` áp dụng tương tự cho các loại kiểu cấp cao nhất này khi biên dịch theo mô hình tệp nguồn phổ biến của `javac`.

**Phân biệt phạm vi:** “cấp cao nhất” nói về **vị trí khai báo**, còn `public` nói về **khả năng truy cập**. Một lớp cấp cao nhất có thể `public` hoặc không `public`; nó không tự động có `public` vì đứng ngoài các lớp khác.

## 2. Quy tắc một kiểu `public` cấp cao nhất cho một tệp

Ví dụ hợp lệ, tệp `Main.java`:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("Main chạy");
    }
}

class FirstHelper {
}

class SecondHelper {
}
```

Có ba lớp cấp cao nhất nhưng chỉ `Main` là `public`. Đây là một đơn vị biên dịch Java hợp lệ.

Ví dụ **không hợp lệ**, dù hai lớp đều có mã riêng:

```java
// File: Main.java — SAI
public class Main {
}

public class Helper {
}
```

Trình biên dịch `javac` từ chối vì `Helper` là kiểu `public` cấp cao nhất nhưng không ở trong tệp tên `Helper.java`. Không thể khắc phục bằng cách đổi `Main.java` thành `Helper.java`: khi đó lớp `Main` lại không khớp tên tệp. Cách sửa là **tách thành `Main.java` và `Helper.java`**, hoặc bỏ `public` của một lớp nếu chỉ cần truy cập trong cùng package.

Tên của kiểu `public` phải khớp tên tệp:

| Tên tệp | Khai báo cấp cao nhất | Kết quả |
| --- | --- | --- |
| `Main.java` | `public class Main { }` | Hợp lệ |
| `Main.java` | `class Main { } class Helper { }` | Hợp lệ |
| `Utilities.java` | `class Launcher { } class Helper { }` | Hợp lệ (không có kiểu `public`) |
| `Main.java` | `public class Launcher { }` | Lỗi: tên tệp không khớp `Launcher` |
| `Main.java` | `public class Main { } public class Helper { }` | Lỗi: nhiều kiểu `public` cấp cao nhất trong tệp |
| `Main.java` | `public interface Main { } class Helper { }` | Hợp lệ, nếu `Main` là tên interface mong muốn |

Các ví dụ trên xét quy tắc khai báo và đặt tên; muốn chạy bằng `java` còn phải có phương thức điểm vào `main` phù hợp hoặc cách khởi chạy khác được hỗ trợ.

**Lưu ý về tên:** Java phân biệt chữ hoa và chữ thường; nên dùng tên tệp và tên kiểu khớp từng ký tự, kể cả trên hệ điều hành có hệ thống tệp không phân biệt hoa/thường.

## 3. Ví dụ chạy được: một tệp có ba lớp cấp cao nhất

Tạo tệp **`src/demo/catalog/CatalogApp.java`** với *toàn bộ* nội dung sau:

```java
package demo.catalog;

import java.util.List;

public class CatalogApp {
    public static void main(String[] args) {
        List<Book> books = List.of(
                new Book("Java 17"),
                new Book("Clean Code")
        );

        for (Book book : books) {
            CatalogPrinter.print(book);
        }
        System.out.println("Tổng: " + books.size());
    }
}

class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    String getTitle() {
        return title;
    }
}

final class CatalogPrinter {
    private CatalogPrinter() {
        // Lớp tiện ích: không cho tạo thể hiện từ bên ngoài.
    }

    static void print(Book book) {
        System.out.println("Sách: " + book.getTitle());
    }
}
```

Biên dịch và chạy với JDK 17+ từ thư mục chứa `src`:

```bash
javac -encoding UTF-8 -d out src/demo/catalog/CatalogApp.java
java -cp out demo.catalog.CatalogApp
```

**Kết quả stdout chính xác:**

```text
Sách: Java 17
Sách: Clean Code
Tổng: 2
```

Đọc ví dụ:

- `CatalogApp`, `Book`, `CatalogPrinter` là **ba lớp cấp cao nhất** cùng được khai báo trong **một tệp `CatalogApp.java`**.
- `CatalogApp` là lớp `public` duy nhất, vì vậy tên tệp phải là `CatalogApp.java`.
- `Book` và `CatalogPrinter` không có `public` trước `class` nên có **quyền truy cập package-private**. Các kiểu trong cùng package `demo.catalog` có thể dùng chúng, kể cả khi được khai báo ở tệp khác.
- `Book.title` là `private` và chỉ truy cập trực tiếp từ chính `Book`; `CatalogPrinter` dùng phương thức `getTitle()` thay vì truy cập `title`.
- Constructor `Book(String title)` và phương thức `getTitle()` không viết access modifier nên cũng có quyền truy cập package-private. Điều đó phù hợp vì những lời gọi trong ví dụ đều ở cùng package.
- `CatalogPrinter` có `final`, nghĩa là lớp không thể được kế thừa; `final` **không** thay đổi phạm vi truy cập package-private của lớp.
- `List` là kiểu thư viện chuẩn nhập bằng `import java.util.List;`. Lệnh `import` tạo thuận tiện cho việc viết tên kiểu, không chuyển `List` vào package hiện tại.

Sau lệnh `javac -d out`, kết quả biên dịch gồm các tệp tương ứng với những lớp cấp cao nhất:

```text
out/
└── demo/
    └── catalog/
        ├── CatalogApp.class
        ├── Book.class
        └── CatalogPrinter.class
```

Đây là ba tệp bytecode riêng biệt. **Một tệp `.java` không đồng nghĩa một tệp `.class`.** Trong ví dụ trên `javac` biên dịch cả ba lớp top-level có trong tệp nguồn, và `-d out` yêu cầu đặt bytecode trong thư mục `out` theo package. Trên Windows, dấu phân tách đường dẫn thực tế thường là `\`; sơ đồ dùng `/` để dễ đọc.

Khi chạy, tên `demo.catalog.CatalogApp` là **tên đầy đủ** của lớp có `main`; `java` không chạy dựa vào tên tệp nguồn `CatalogApp.java` đã được biên dịch, mà nạp lớp được chỉ định trong classpath và gọi điểm vào thích hợp.

## 4. Lớp top-level không `public` có phạm vi truy cập nào?

Nếu bỏ access modifier `public` của một lớp top-level, lớp có **package access** (thường gọi là **package-private**, hoặc *default/package-level access*). Đây không phải một từ khóa `default` viết trước `class`.

```java
package demo.catalog;

class Book {
    // Các kiểu thuộc package demo.catalog có thể tham chiếu tới Book.
}
```

Tác động thực tế:

- `Book` dùng được ở **các lớp khác trong cùng package `demo.catalog`**, dù được khai báo trong file `.java` khác.
- Mã nguồn ở package khác **không thể tham chiếu trực tiếp tới `demo.catalog.Book`** dưới tư cách một kiểu có thể truy cập. Thêm `import demo.catalog.Book;` không làm thay đổi quyền truy cập.
- Package được xác định bởi **khai báo `package`**, không phải bởi việc có chung tệp `.java`. Việc đặt thư mục theo tên package là quy ước bố trí nguồn quan trọng và phù hợp với công cụ build/biên dịch.
- Một lớp top-level `public` có thể được dùng từ package khác nếu kiểu và các thành phần cần thiết cũng có quyền truy cập phù hợp và được đưa vào classpath/module path đúng cách. `public` của lớp không tự biến mọi constructor/field/method bên trong thành `public`.

Ví dụ cùng package nhưng hai tệp riêng biệt:

**`src/lesson/App.java`**

```java
package lesson;

public class App {
    public static void main(String[] args) {
        Message message = new Message();
        System.out.println(message.text());
    }
}
```

**`src/lesson/Message.java`**

```java
package lesson;

class Message {
    String text() {
        return "Cùng package";
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 -d out src/lesson/App.java src/lesson/Message.java
java -cp out lesson.App
```

Stdout:

```text
Cùng package
```

`App` và `Message` có thể tương tác vì đều thuộc `lesson`, **không phải vì ở cùng tệp** (chúng ở hai tệp khác nhau). Giữ `Message` không `public` khi đó là chi tiết triển khai chỉ cần dùng trong package.

## 5. Nếu tệp không có kiểu top-level `public` thì sao?

**Vẫn hợp lệ.** Lúc này tên tệp `.java` không bắt buộc trùng tên của lớp nào trong tệp. Tất cả lớp cấp cao nhất có thể mang phạm vi package-private.

Tạo tệp **`Utilities.java`** trong thư mục làm việc, không có khai báo `package`:

```java
class Launcher {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}

class Greeter {
    static String message() {
        return "Chào Java";
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 Utilities.java
java Launcher
```

Stdout:

```text
Chào Java
```

Sau biên dịch có `Launcher.class` và `Greeter.class`. **Không có `Utilities.class`** chỉ vì tệp nguồn tên `Utilities.java`: tệp `.class` mang tên theo lớp đã khai báo. Chạy `java Launcher` vì **`Launcher`** là lớp chứa phương thức `public static void main(String[] args)`, không phải vì tên tệp `Utilities.java`.

Ví dụ không khai báo `package` dùng **unnamed package**. Đây là cách thuận tiện cho bài học nhỏ; đối với dự án nhiều tệp nên khai báo package rõ ràng và bố trí thư mục tương ứng.

Lưu ý: các công cụ build, IDE và quy ước dự án thường mong mỗi kiểu top-level quan trọng có tệp tên trùng kiểu, kể cả kiểu không `public`. Điều này là **quy ước tổ chức mã**, khác với quy tắc cú pháp Java cho tệp không có `public`.

## 6. Top-level class khác nested class như thế nào?

Đặt hai khai báo cạnh nhau ở cấp tệp tạo ra **hai lớp top-level độc lập**:

```java
class Outer {
}

class Neighbor {
}
```

Trái lại, đặt khai báo vào **bên trong thân lớp** tạo **member class (lớp thành viên/lớp lồng nhau)**:

```java
class Outer {
    static class Nested {
    }

    private static class HiddenNested {
    }
}
```

So sánh:

| Đặc điểm | Top-level class | Member/nested class |
| --- | --- | --- |
| Vị trí | Trực tiếp trong tệp/đơn vị biên dịch | Bên trong thân một kiểu khác |
| Ví dụ tên nguồn | `Neighbor` | `Outer.Nested` |
| `private`, `protected` | **Không được phép** làm access modifier của top-level class | Có thể dùng với member class theo ngữ cảnh |
| `static` | **Không được phép** cho top-level class | Có thể dùng cho static nested class |
| Dạng tên bytecode thông thường | `Neighbor.class` | `Outer$Nested.class` |
| Quan hệ | Không là thành viên của lớp đứng trước nó | Là thành viên của kiểu bao ngoài |

Một top-level class có thể sử dụng các modifier hợp lệ như `public`, `abstract`, `final` hoặc `sealed` (theo các ràng buộc tương ứng), nhưng **không được khai báo trực tiếp là `private`, `protected` hay `static`**.

Các ví dụ sai ở cấp tệp:

```java
private class Secret { }      // SAI: top-level không thể private
protected class Child { }     // SAI: top-level không thể protected
static class Tool { }         // SAI: top-level không thể static
```

Nếu thật sự cần một lớp triển khai `private` hoặc `static`, hãy xem xét đưa nó thành lớp lồng nhau trong kiểu bao ngoài, hoặc dùng lớp top-level package-private khi mục đích chỉ là ẩn khỏi các package khác. Không tự động biến các lớp top-level trong cùng tệp thành nested class.

**Sự khác biệt giữa các loại lớp lồng nhau:** member class không `static` gắn với một thể hiện lớp bao ngoài; static nested class không cần một thể hiện bao ngoài để khởi tạo theo cách của member class. Local class (khai báo trong khối/phương thức) và anonymous class cũng khác với top-level class. Việc có nhiều khai báo trong tệp **không tự quyết định** loại lớp; vị trí khai báo mới quyết định.

## 7. Một file có nhiều lớp sẽ được biên dịch thế nào?

Đối với chương trình `CatalogApp.java` ở mục 3:

1. `javac` đọc đơn vị biên dịch chứa `package`, `import` và ba khai báo top-level.
2. Trình biên dịch kiểm tra cú pháp, định nghĩa kiểu, quyền truy cập và các phụ thuộc của những khai báo này.
3. Nó tạo bytecode phù hợp cho từng lớp (`CatalogApp.class`, `Book.class`, `CatalogPrinter.class`).
4. Khi chạy `java -cp out demo.catalog.CatalogApp`, JVM nạp lớp và các phụ thuộc khi cần; phương thức `main` trong `CatalogApp` tạo đối tượng `Book` và gọi `CatalogPrinter`.

Các tệp `.class` là **đầu ra biên dịch của các kiểu**, không tương ứng từng dòng `new` (tạo đối tượng). Một lớp có thể được dùng để tạo rất nhiều đối tượng khi chạy mà vẫn có một định nghĩa kiểu.

Khi có nested/local/anonymous class, trình biên dịch thường tạo thêm tệp `.class` có tên dạng `Outer$Nested.class` hoặc các hậu tố nội bộ khác. Do đó không nên dự đoán số tệp `.class` chỉ từ số lượng tệp `.java`. Với ví dụ ba **top-level class** đơn giản, sơ đồ ba tệp `.class` ở mục 3 là đủ.

Một chi tiết về thứ tự: các khai báo top-level cùng tệp **không bắt buộc được viết theo thứ tự sử dụng**. Trong mã `CatalogApp`, `CatalogApp` gọi `Book` trước khi phần `class Book` xuất hiện trong văn bản, nhưng `javac` vẫn phân tích được toàn bộ đơn vị biên dịch. Không cần di chuyển `Book` lên trước `CatalogApp` để biên dịch.

## 8. Khi nào nên viết nhiều lớp trong một tệp?

Việc đặt nhiều lớp cấp cao nhất trong một tệp **được ngôn ngữ cho phép**, song nên dựa vào mục đích và khả năng bảo trì:

- **Hợp lý:** ví dụ học tập ngắn, chương trình mẫu nhỏ, hoặc một kiểu `public` cùng một vài helper package-private ngắn chỉ liên quan trực tiếp đến kiểu đó.
- **Nên cân nhắc tách tệp:** lớp dài, có trách nhiệm riêng, được dùng rộng trong package, được kiểm thử/duy trì độc lập, hoặc khiến tệp khó điều hướng.
- **Thường dùng trong dự án lớn:** mỗi kiểu top-level đáng kể một tệp tương ứng; lớp trợ giúp chỉ gắn chặt với một lớp có thể trở thành member class nếu thực sự cần quan hệ bao đóng.
- **Giữ API rõ ràng:** chỉ khai báo `public` cho các kiểu thực sự là API cần truy cập từ bên ngoài phạm vi package; dùng package-private cho các chi tiết triển khai nội bộ khi phù hợp.

Giả sử ban đầu `App.java` chứa:

```java
package example;

public class App {
    public static void main(String[] args) {
        Helper.sayHello();
    }
}

class Helper {
    static void sayHello() {
        System.out.println("Hello");
    }
}
```

Khi `Helper` lớn dần, có thể tách thành **hai tệp trong cùng package**, giữ nguyên hành vi:

**`src/example/App.java`**

```java
package example;

public class App {
    public static void main(String[] args) {
        Helper.sayHello();
    }
}
```

**`src/example/Helper.java`**

```java
package example;

class Helper {
    static void sayHello() {
        System.out.println("Hello");
    }
}
```

Biên dịch hai tệp sau khi đã xóa phần `class Helper` khỏi `App.java`:

```bash
javac -encoding UTF-8 -d out src/example/App.java src/example/Helper.java
java -cp out example.App
```

Stdout:

```text
Hello
```

`Helper` không cần chuyển thành `public` để dùng từ `App` bởi hai lớp vẫn thuộc package `example`. **Không để lại hai bản khai báo `example.Helper`** (một ở `App.java` và một ở `Helper.java`) trong cùng tập nguồn biên dịch, vì chúng trùng tên kiểu đầy đủ và gây lỗi định nghĩa trùng.

## 9. Lỗi phổ biến và cách tự kiểm tra

| Hiện tượng / suy nghĩ sai | Nguyên nhân thực tế | Cách xử lý |
| --- | --- | --- |
| “Một `.java` bắt buộc chỉ chứa một `class`.” | Nhầm tệp nguồn với khai báo lớp. | Có thể khai báo nhiều top-level class; tuân thủ quy tắc `public`. |
| Biên dịch `Main.java` nhưng báo `Helper` phải ở `Helper.java`. | `Helper` khai báo `public` trong sai tên tệp. | Tách `Helper.java` hoặc bỏ `public` nếu chỉ dùng trong package. |
| Có `public class Main` và `public class Helper` trong một tệp. | Cả hai top-level đều `public`. | Tách tệp nguồn hoặc giảm quyền truy cập phù hợp. |
| Viết `private class Helper` ngoài mọi lớp. | Top-level class không nhận modifier `private`. | Dùng `class Helper` (package-private), hoặc thiết kế nested class. |
| Viết `static class Helper` ngoài mọi lớp. | `static` chỉ thích hợp với nested member class, không phải top-level. | Bỏ `static` hoặc chuyển khai báo vào trong kiểu bao ngoài. |
| `java Utilities` không chạy dù biên dịch `Utilities.java` thành công. | Tên tệp nguồn không nhất thiết là tên lớp chứa `main`. | Chạy đúng tên lớp, chẳng hạn `java Launcher`. |
| Mã ở package khác không truy cập được `Helper`. | `Helper` là top-level package-private. | Thiết kế API `public` nếu cần; đặt ở tệp `Helper.java` phù hợp. |
| Có nhiều `.class` sau khi biên dịch một `.java`. | Một đơn vị biên dịch chứa nhiều kiểu hoặc kiểu lồng nhau. | Đây là đầu ra bình thường. |
| `duplicate class` sau khi tách helper thành tệp riêng. | Vẫn còn khai báo cũ cùng tên đầy đủ trong tập nguồn. | Chỉ giữ một định nghĩa của kiểu trong package. |
| Chạy `java CatalogApp` với lớp ở `package demo.catalog;`. | Thiếu tên đầy đủ của lớp trong câu lệnh chạy. | Dùng `java -cp out demo.catalog.CatalogApp`. |

Các lỗi trên là loại lỗi thường được `javac` phát hiện ở thời điểm biên dịch; thông báo chi tiết có thể khác theo phiên bản JDK và cách chạy.

## 10. Câu hỏi luyện tập

**Câu 1.** Nội dung `Main.java`:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("OK");
    }
}

class Tool {
}

class Storage {
}
```

Có hợp lệ không, bao nhiêu top-level class? **Hợp lệ.** Có ba top-level class, chỉ `Main` là `public`. Nếu biên dịch thành công, `javac Main.java` tạo `Main.class`, `Tool.class`, `Storage.class`; `java Main` in `OK`.

**Câu 2.** Tệp `Helpers.java` chứa `class A { } class B { }`, không có `public`. Tên tệp có bắt buộc đổi thành `A.java` không? **Không.** Tệp không có kiểu top-level `public` nên tên `Helpers.java` hợp lệ với `javac` trong mô hình thông thường.

**Câu 3.** `Outer.java` chứa `public class Outer { static class Inner { } } class Helper { }`. `Inner` có phải là top-level class không? **Không.** `Inner` là static nested class vì nằm trong `Outer`; `Helper` mới là top-level class cùng `Outer`.

**Câu 4.** Khi chuyển `class Helper` từ cuối `App.java` sang `Helper.java` nhưng vẫn dùng `package example;` trong cả hai, có cần thêm `public` cho `Helper` không? **Không**, nếu chỉ những lớp trong `example` sử dụng `Helper`. Hai lớp cùng package vẫn truy cập được kiểu package-private dù ở khác tệp.

**Câu 5.** Điều nào quyết định lệnh `java` phải chạy lớp nào: tên tệp `.java` hay tên lớp có phương thức `main`? **Tên lớp cần khởi chạy**, cùng tên package đầy đủ nếu có package; classpath/module path phải chứa bytecode tương ứng.

## Ghi nhớ

- **Top-level class** nằm trực tiếp trong đơn vị biên dịch, không nằm bên trong một kiểu/phương thức khác.
- **Một tệp `.java` có thể chứa nhiều top-level class**, nhưng với cách biên dịch Java thông dụng, chỉ **tối đa một kiểu top-level `public`** và tên tệp phải trùng với kiểu `public` đó.
- Lớp top-level **không `public` là package-private**, dùng được từ các kiểu cùng package kể cả nằm ở tệp nguồn khác.
- Lớp top-level **không thể là `private`, `protected` hoặc `static`**; các modifier ấy cần được hiểu theo ngữ cảnh member/nested class khi hợp lệ.
- **Tệp nguồn, lớp và tệp bytecode là các khái niệm khác nhau:** một `.java` có thể chứa nhiều lớp; biên dịch có thể tạo nhiều `.class`; chạy chương trình dùng tên lớp chứa điểm vào.
