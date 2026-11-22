# Đặt tên lớp, tên tệp và quy tắc của lớp public trong Java

Khi khai báo một lớp Java, **tên lớp** là định danh của kiểu, **tên tệp nguồn** là nơi lưu mã `.java`, còn modifier `public` biểu thị khả năng truy cập kiểu đó từ bên ngoài package. Ba yếu tố này liên quan nhưng khác nhau: không phải class nào cũng phải trùng tên tệp, và `public` không tự động khiến một class truy cập được từ mọi module.

Bài này giải thích cú pháp và quy ước đặt tên, mối quan hệ giữa top-level class và tệp nguồn, cách kết hợp class với `package`, sự khác biệt giữa top-level và nested class, cùng các ví dụ Java 17+ có thể biên dịch và chạy.

## 1. Một class có nhiều cách định danh

Xét tệp **`src/com/example/school/Student.java`**:

~~~java
package com.example.school;

public class Student {
    private final String name;

    public Student(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Đây là **đoạn khai báo class**, không phải chương trình có `main` để chạy độc lập.

| Thành phần | Giá trị trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tên đơn (*simple name*) | `Student` | Tên kiểu khi không ghi package |
| Tên đầy đủ (*fully qualified name*) | `com.example.school.Student` | Tên kiểu bao gồm package |
| Package | `com.example.school` | Phạm vi tổ chức class và kiểm soát quyền package-private |
| Tệp nguồn | `Student.java` | Tệp chứa khai báo class |
| Đường dẫn source thông dụng | `src/com/example/school/Student.java` | Phản ánh package từ thư mục gốc nguồn |

`Student` và `student` là hai tên khác nhau vì Java **phân biệt chữ hoa/chữ thường**. Hai class cùng tên đơn `Student` có thể tồn tại trong hai package khác nhau, chẳng hạn `com.example.school.Student` và `com.example.sports.Student`; hai kiểu có tên đầy đủ khác nhau.

Từ góc nhìn JVM, tên class có package quan trọng khi nạp/chạy chương trình. Từ góc nhìn compiler `javac`, tên tệp đặc biệt quan trọng nếu class top-level là `public`.

## 2. Quy tắc cú pháp của tên class

Tên class phải là một **Java identifier** hợp lệ. Với Java 17:

- Tên có thể gồm các chữ cái và nhiều ký tự Unicode được Java công nhận, chữ số ở vị trí không phải ký tự đầu, cùng một số ký tự như `_` và `$`.
- Không thể bắt đầu bằng chữ số: `Customer2` hợp lệ, `2Customer` không hợp lệ.
- Không dùng từ khóa Java như `class`, `public`, `int` làm tên class. Một số tên như `record` và `var` có quy tắc hạn chế sử dụng làm tên kiểu.
- Một ký tự gạch dưới **`_`** đứng riêng không còn là identifier hợp lệ kể từ Java 9; `_Customer` vẫn hợp lệ về cú pháp.
- Java phân biệt `User`, `user` và `USER`; tuy có thể cùng tồn tại nếu không xung đột tên, cách đặt tên như vậy rất khó bảo trì.

Ví dụ hợp lệ (các dòng sai đã được comment):

~~~java
class Customer { }
class Customer2 { }
class _Customer { }
class customer { }     // hợp lệ, không theo convention class

// class 2Customer { } // sai: bắt đầu bằng chữ số
// class class { }     // sai: trùng từ khóa
// class _ { }         // sai với Java 17
// class record { }    // sai: record không dùng làm tên kiểu
~~~

Đoạn này không có `main`, dùng để minh họa **tên identifier**. `$` hay các chữ Unicode đặc biệt có thể hợp lệ nhưng không nên tùy tiện sử dụng vì giảm khả năng đọc và dễ nhầm lẫn khi tìm kiếm hoặc làm việc giữa các hệ điều hành.

### 2.1. Convention: UpperCamelCase

Java thường đặt tên class, interface, enum, record bằng **UpperCamelCase**: mỗi từ viết hoa chữ cái đầu, không có dấu cách hoặc dấu gạch nối.

| Tên | Đánh giá | Lý do |
| --- | --- | --- |
| `Student` | Nên dùng | Danh từ chỉ kiểu |
| `BankAccount` | Nên dùng | Nêu rõ đối tượng và phạm vi |
| `PaymentRequest` | Nên dùng | Dễ suy ra trách nhiệm |
| `HttpClient` | Nên dùng | Cách ghép từ dễ đọc |
| `student` | Biên dịch được | Nhưng không theo convention class |
| `bank_account` | Biên dịch được | Không theo UpperCamelCase |
| `Bank-Account` | Không biên dịch | Ký tự `-` không thuộc identifier |
| `Data` | Mơ hồ | Không mô tả đối tượng cụ thể |
| `String` | Dễ gây nhầm | Có thể che khuất tên kiểu chuẩn `java.lang.String` |

Tên khác trong Java có convention riêng: method/field thường là `lowerCamelCase` như `getName`, `totalPrice`; hằng số thường là `UPPER_SNAKE_CASE` như `MAX_SIZE`; package thường dùng chữ thường như `com.example.school`.

**Compiler chỉ thực thi quy tắc cú pháp**; nó không bắt buộc bạn viết UpperCamelCase. Tuy nhiên, nên chọn tên gắn với khái niệm miền nghiệp vụ và tránh viết tắt khó hiểu hoặc những tên chỉ khác nhau ở một chữ hoa.

## 3. Top-level class public phải trùng tên tệp khi dùng javac

**Top-level class** là class được khai báo trực tiếp trong một compilation unit, bên ngoài mọi class khác. Trong workflow mã nguồn `.java` với compiler `javac`, nếu một top-level class có modifier `public` thì **tệp nguồn phải mang đúng tên class, thêm hậu tố `.java`**.

**Tệp `Customer.java`:**

~~~java
public class Customer {
}
~~~

Đây là khai báo hợp lệ. Nhưng nếu lưu cùng nội dung trên dưới tên **`Order.java`** và chạy:

~~~bash
javac Order.java
~~~

thì lỗi biên dịch điển hình là:

~~~text
Order.java:1: error: class Customer is public, should be declared in a file named Customer.java
~~~

Số dòng, phần hiển thị và wording có thể khác tùy JDK. Sửa bằng cách đổi tên tệp thành `Customer.java` hoặc đổi tên class thành `Order`, tùy mục đích. Nếu đổi tên class, phải sửa cả constructor, tham chiếu và import liên quan.

**Phân biệt kỹ thuật:** đặc tả Java mô tả các cơ chế tổ chức compilation unit phụ thuộc host system; quy tắc tệp mang tên public type là hành vi chuẩn trong thực hành với **`javac`** và công cụ build Java thông thường. Câu “mọi class bắt buộc có tệp trùng tên” là không chính xác vì class package-private và nested class có các trường hợp khác.

### 3.1. Không có hai top-level public type khác tên trong cùng tệp

**Tệp `First.java`, ví dụ không hợp lệ:**

~~~java
public class First {
}

public class Second {
}
~~~

Compiler yêu cầu kiểu `Second` phải được khai báo trong `Second.java`. Tách thành hai tệp:

~~~text
First.java    -> public class First
Second.java   -> public class Second
~~~

Nguyên tắc trên cũng áp dụng trong thực hành với top-level `public interface`, `public enum`, `public record` và `public @interface`: tên tệp ứng với tên kiểu public. Ví dụ `public enum OrderStatus { NEW, PAID }` nên lưu ở `OrderStatus.java`.

**Không nhầm với Java modifier:** top-level class chỉ có thể có mức truy cập `public` hoặc mặc định (không ghi modifier, gọi là *package-private*). Không thể khai báo `private class X` hoặc `protected class X` ở mức top-level.

### 3.2. Ngoại lệ: lớp không `public` không buộc trùng tên tệp

Một top-level class `package-private` (không ghi `public`) **không phải mang cùng tên tệp**. Ví dụ trong **`Shapes.java`**:

~~~java
class Circle {
    double radius;
}

class Rectangle {
    double width;
}
~~~

Lệnh `javac Shapes.java` tạo `Circle.class` và `Rectangle.class`. Nếu tệp có một top-level `public class Cart` và helper không public, tên tệp phải là `Cart.java`; helper không cần tệp riêng.

Đây là **ngoại lệ đặt tên tệp** cần nhớ khi đặt tên class. Bài về *nhiều lớp cấp cao nhất trong cùng tệp* sẽ làm rõ cách nhiều class được biên dịch, lợi ích của package-private helpers và trường hợp compiler không tự tìm một helper nằm trong tệp có tên khác. Với mã nguồn chia nhiều tệp, thông thường mỗi kiểu top-level độc lập ở tệp riêng vẫn thuận tiện cho IDE, source search và build tools.


## 4. Public nested class không cần tệp riêng

**Nested class** được khai báo bên trong class khác. Nó có thể `public` mà không chịu quy tắc tên tệp dành cho top-level public type.

**Tệp `Library.java`:**

~~~java
public class Library {
    public static class Book {
        private final String title;

        public Book(String title) {
            this.title = title;
        }

        public String getTitle() {
            return title;
        }
    }
}
~~~

Đây là đoạn khai báo lớp hợp lệ, không có `main`. `Library` là top-level class nên tên tệp **`Library.java`**. `Book` là **static nested class** và truy cập bằng tên `Library.Book`; không cần tạo `Book.java`.

Tương tự:

~~~java
class Outer {
    public class Inner {
    }
}
~~~

`Inner` ở đây là **non-static inner class**, gắn với instance của `Outer`. Nó cũng không phải top-level class. Nếu compiler tạo file bytecode có tên như `Library$Book.class`, đây là tên file **`.class`** do compiler sinh, không phải yêu cầu tên file nguồn `Book.java`.

Nên kiểm tra vị trí khai báo trước khi áp dụng quy tắc “`public` phải trùng tên file”: **`public` của top-level type** khác **`public` của member nested type**.

## 5. Public và package: phạm vi truy cập của class

Top-level type `public` có thể được sử dụng từ package khác nếu các điều kiện truy cập còn lại cho phép. Top-level type không có `public` chỉ được truy cập trực tiếp trong cùng package, thường gọi **package-private**.

**Tệp `src/com/example/school/StudentRules.java`:**

~~~java
package com.example.school;

class StudentRules {
    static boolean validId(String id) {
        return id != null && !id.isBlank();
    }
}
~~~

`StudentRules` package-private, nên class ở `com.example.school` dùng được, còn một class ở `com.example.billing` không thể tham chiếu trực tiếp theo cơ chế truy cập thông thường. Hai package không tự coi là một vì cùng dự án hoặc cùng thư mục gốc.

Với public type, bạn có thể viết tên đầy đủ `com.example.school.Student` hoặc `import com.example.school.Student;` nếu compiler nhìn thấy class trên classpath/module path và quyền truy cập cho phép.

**Named modules:** khi có `module-info.java`, `public` chưa đủ để mã ở module khác truy cập class. Package chứa public class còn cần được module khai báo `exports` thích hợp; module bên sử dụng phải có quan hệ `requires` thích hợp. Quy tắc tên tệp public class vẫn áp dụng khi biên dịch nguồn với `javac`.

Từ góc nhìn thiết kế, `public` phù hợp với API dự định dùng từ package khác. Helper chỉ phục vụ cài đặt nội bộ thường nên để package-private, giảm sự phụ thuộc của mã bên ngoài.

## 6. Ví dụ runnable: hai public class, hai tệp, một package

Tạo cấu trúc thư mục sau:

~~~text
project/
└── src/
    └── com/
        └── example/
            └── academy/
                ├── StudentCard.java
                └── App.java
~~~

**Tệp `src/com/example/academy/StudentCard.java`:**

~~~java
package com.example.academy;

public class StudentCard {
    private final String studentId;
    private final String studentName;

    public StudentCard(String studentId, String studentName) {
        this.studentId = studentId;
        this.studentName = studentName;
    }

    public String label() {
        return studentId + " - " + studentName;
    }
}
~~~

**Tệp `src/com/example/academy/App.java`:**

~~~java
package com.example.academy;

public class App {
    public static void main(String[] args) {
        StudentCard card = new StudentCard("SV-17", "Lan");

        System.out.println("Student: " + card.label());
        System.out.println("Class: " + card.getClass().getSimpleName());
    }
}
~~~

Mở terminal tại thư mục `project`. Dùng JDK 17+ và thực hiện:

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/com/example/academy/StudentCard.java src/com/example/academy/App.java
java -cp out com.example.academy.App
~~~

Bỏ qua `mkdir out` nếu đã tạo thư mục trước đó. `javac -d out` tạo các thư mục package bên dưới output root `out`. Cặp lệnh cuối hoạt động từ thư mục `project`; các đường dẫn được truyền rõ ràng nên không phụ thuộc việc shell mở rộng wildcard.

**Stdout chính xác:**

~~~text
Student: SV-17 - Lan
Class: StudentCard
~~~

Bytecode sau khi biên dịch có vị trí:

~~~text
out/
└── com/
    └── example/
        └── academy/
            ├── StudentCard.class
            └── App.class
~~~

Giải thích:

1. Hai top-level public class nằm trong hai tệp tên khớp: `StudentCard.java` và `App.java`.
2. Cả hai khai báo `package com.example.academy;` nên `App` gọi `StudentCard` bằng tên đơn mà không cần `import`.
3. `main` của `App` gọi constructor `StudentCard(...)` rồi in nhãn từ method `label()`.
4. `card.getClass().getSimpleName()` trả `"StudentCard"` với class được tạo trong ví dụ.
5. `java -cp out com.example.academy.App` là cách chạy bằng **tên đầy đủ** của class chính; `java App` không tìm đúng class này khi nó nằm trong named package.

`-encoding UTF-8` dùng để đọc mã nguồn; `-d out` xác định gốc lưu file `.class`; `-cp out` đặt classpath root khi chạy. Đây là các lựa chọn command line, không làm thay đổi cú pháp tên class.

## 7. Package và cấu trúc thư mục

Thực hành chuẩn thường tổ chức nguồn theo:

~~~text
src/main/java/com/example/shop/Product.java
~~~

và khai báo đầu tệp:

~~~java
package com.example.shop;

public class Product {
}
~~~

`src/main/java` là source root phổ biến trong Maven/Gradle, còn `com/example/shop` phản ánh package. **Khai báo `package` trong mã nguồn mới quyết định class thuộc package nào**; bản thân tên thư mục không sửa được khai báo package. Khi biên dịch nguồn bằng `javac` với đường dẫn tường minh, compiler có thể nhận một bố cục mã nguồn khác convention, nhưng bố cục khớp package giúp IDE, build tool, source path, lớp sau biên dịch và con người làm việc ổn định hơn.

### 7.1. Unnamed package khi không khai báo package

**Tệp `Hello.java`:**

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Đây là chương trình đầy đủ không có khai báo `package`, nên thuộc **unnamed package**. Chạy:

~~~bash
javac Hello.java
java Hello
~~~

Stdout:

~~~text
Hello, Java!
~~~

Ví dụ này phù hợp khi bắt đầu học Java. Dự án nhiều class nên dùng package có tên; mã thuộc named package không thể import trực tiếp class của unnamed package.

### 7.2. Hai class cùng simple name ở hai package

Có thể có `com.example.shop.User` và `com.example.admin.User`. Khi cần tham chiếu cả hai trong cùng tệp, dùng tên đầy đủ để tránh xung đột. Java không cung cấp import alias theo cú pháp đặt bí danh kiểu ở một số ngôn ngữ khác.

~~~java
// Minh họa khai báo biến, giả sử hai kiểu User đã tồn tại:
com.example.shop.User customer;
com.example.admin.User administrator;
~~~

Ngược lại, hai top-level class cùng tên đơn trong **cùng package** sẽ xung đột dù đặt chúng ở hai thư mục mã nguồn khác nhau.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Tình huống | Vì sao sai hoặc dễ lỗi | Cách sửa |
| --- | --- | --- |
| `public class Payment` lưu trong `Invoice.java` | Public top-level type và filename không trùng | Lưu là `Payment.java` hoặc đổi tên class |
| Hai top-level `public` class trong `Main.java` | Không thể đồng thời thỏa quy tắc tên tệp | Tách mỗi public type một tệp |
| `private class Helper` ở top-level | `private` không áp dụng cho top-level class | Bỏ modifier hoặc chuyển thành nested member class |
| `public class account` trong `Account.java` | Java phân biệt chữ hoa/thường | Đổi thành `Account` và đồng bộ tham chiếu |
| `public class Order` đổi thành `Purchase` nhưng constructor vẫn `Order(...)` | Constructor phải trùng tên class | Refactor đổi tên class và constructor đồng bộ |
| `class InternalTool` từ package khác không gọi được | Package-private chỉ trong cùng package | Giữ nội bộ hoặc mở public nếu API cần |
| Source đặt đúng nhưng chạy `java Main` trong khi class thuộc `com.example.Main` | Sai tên đầy đủ/classpath khi chạy | Chạy `java -cp out com.example.Main` |
| Class đặt tên `String` hoặc `Object` | Dễ gây xung đột hoặc che khuất tên chuẩn | Chọn tên nghiệp vụ cụ thể |
| Chỉ khác chữ hoa trong tên tệp giữa Windows/Linux | Cách phân biệt case của filesystem có thể khác | Giữ đúng case trong mã và tên tệp |

Một lỗi *compile time* như `class Customer is public, should be declared in a file named Customer.java` khác với lỗi *runtime* như `Could not find or load main class`. Lỗi đầu liên quan tổ chức mã nguồn; lỗi sau liên quan tên lớp khi chạy, classpath, bytecode hoặc cấu hình module.

Không nên chỉnh bừa `public` để khắc phục lỗi classpath, bởi modifier này điều khiển truy cập của API, không điều khiển nơi JVM tìm bytecode.

## 9. Ví dụ thiết kế API: public và package-private chung tệp

**Tệp `InvoiceService.java`:**

~~~java
package com.example.billing;

public class InvoiceService {
    public long total(long base, long tax) {
        return InvoiceMath.sum(base, tax);
    }
}

class InvoiceMath {
    static long sum(long first, long second) {
        return Math.addExact(first, second);
    }
}
~~~

Đây là đoạn minh họa, không có `main`. `InvoiceService` là API cấp package khác có thể dùng khi mọi điều kiện truy cập khác thỏa. `InvoiceMath` chỉ phục vụ triển khai trong `com.example.billing` nên không cần `public`. Một public top-level class và một class package-private trong cùng file hợp lệ. Khi helper đủ lớn hoặc cần kiểm thử độc lập, có thể tách `InvoiceMath` thành `InvoiceMath.java`; việc tách không buộc phải thêm `public`.

## 10. Tự kiểm tra

**Câu 1.** Tệp `Shop.java` khai báo `public class Store`. Lệnh `javac Shop.java` có hợp lệ không?

**Đáp án:** Không. Public top-level class `Store` phải nằm trong `Store.java` đối với `javac`.

**Câu 2.** `class A` và `class B` (không public) có thể cùng nằm trong `Helpers.java` không?

**Đáp án:** Có. Chúng là hai top-level package-private class; không phải tên nào cũng cần khớp tên tệp.

**Câu 3.** `public class Outer` có `public static class Nested`. Có phải tạo `Nested.java` không?

**Đáp án:** Không. `Nested` là nested class, còn `Outer` là top-level public class quyết định tên tệp `Outer.java`.

**Câu 4.** `public class User` có thể khai báo trong package `com.example.api` và một `public class User` khác trong `com.example.domain` không?

**Đáp án:** Có. Hai fully qualified names là `com.example.api.User` và `com.example.domain.User`, nên là hai kiểu khác nhau.

**Câu 5.** Class `App` thuộc `package com.example.app;` được biên dịch vào `out/com/example/app/App.class`. Lệnh chạy với gốc classpath `out` là gì?

**Đáp án:** `java -cp out com.example.app.App` nếu `App` có entry point `main` phù hợp.

Khi tạo class mới, kiểm tra năm điểm: **tên kiểu hợp lệ và rõ nghĩa**, **package khai báo đúng**, **top-level `public` trùng chính xác tên tệp**, **mỗi tệp chỉ một top-level `public` type**, và **cấu trúc source/classpath nhất quán khi build hoặc chạy**. Những điều này giúp tổ chức Java source rõ ràng và tránh phần lớn lỗi cơ bản liên quan đến tên lớp và tên tệp.
