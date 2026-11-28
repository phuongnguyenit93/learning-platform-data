# Cấu trúc tệp nguồn gọn, lớp được khai báo ngầm và phạm vi sử dụng

## Mục tiêu học tập

**Compact source file** (tệp nguồn gọn) là cách viết một chương trình Java mà không phải tự khai báo lớp bao ngoài. Trong Java 25, trình biên dịch sẽ tạo **lớp được khai báo ngầm** (*implicitly declared class*) để chứa các phương thức, trường và kiểu thành viên xuất hiện trong tệp. Cách viết này giúp lập trình viên tập trung vào thuật toán và các ví dụ nhỏ, trong khi chương trình vẫn dùng mô hình lớp, phương thức và JVM của Java.

Đây là tính năng **chính thức từ Java 25**, theo **JEP 512 — Compact Source Files and Instance Main Methods**, không còn là preview và không cần `--enable-preview`. Bài thuộc chương **Tệp nguồn gọn** của module **JAVA_VERSION_JAVA25**. Nội dung chỉ sử dụng những đặc tính còn áp dụng trong Java hiện đại, đặc biệt là quy tắc đã chốt trong Java 25; không dùng cú pháp từ các bản preview cũ.

Sau bài học, bạn có thể:

1. Nhận diện cấu trúc một compact source file và phân biệt với tệp Java thông thường.
2. Giải thích lớp ngầm được tạo ra có thuộc tính gì, thành viên nào được phép khai báo và vì sao không thể tham chiếu tên lớp đó trong mã nguồn.
3. Viết và chạy chương trình bằng `void main()`, `void main(String[] args)` và các hình thức `main` hợp lệ trong Java 25.
4. Sử dụng những kiểu từ module `java.base` được tự động import và lớp `java.lang.IO` đúng cú pháp Java 25.
5. Biết khi nào nên dùng tệp nguồn gọn, khi nào cần chuyển thành lớp/package/module được khai báo tường minh.
6. Tránh các lỗi thường gặp về phạm vi tên, constructor, import, phiên bản JDK và build.

> **Điều kiện thực hành:** sử dụng **JDK 25 trở lên** hỗ trợ JEP 512. Để kiểm chứng đúng môi trường Java 25, dùng cả `java -version` và `javac -version`. Các ví dụ là chương trình độc lập; không cần thư viện bên thứ ba.

## 1. Vấn đề mà tệp nguồn gọn giải quyết

Một chương trình Java nhỏ theo cấu trúc thông thường:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Xin chào Java!");
    }
}
~~~

Khi mới học, người viết phải tiếp xúc ngay với `public`, `class`, `static` và `String[] args`, dù mục đích chỉ là in một dòng chữ. Java 25 hỗ trợ cách viết:

~~~java
// Hello.java — compact source file của Java 25
void main() {
    IO.println("Xin chào Java!");
}
~~~

Chạy trực tiếp trong thư mục chứa tệp:

~~~bash
java -version
java Hello.java
~~~

Kết quả:

~~~text
Xin chào Java!
~~~

Không có từ khóa `class`, nhưng đây **vẫn là chương trình Java có lớp**. Trình biên dịch dùng các thành viên trong tệp làm thân của một lớp được khai báo ngầm. Java không chuyển sang cơ chế thực thi “hàm nằm ngoài lớp” như một số ngôn ngữ khác.

Cú pháp này phù hợp với ví dụ học tập, script nhỏ, thử thuật toán, kiểm tra API và các công cụ dòng lệnh đơn giản. Nó không thay thế các kỹ thuật thiết kế phần mềm như package, module, lớp công khai, kiểm soát phụ thuộc hoặc kiểm thử khi hệ thống phát triển.

## 2. Cấu trúc của một compact source file

Một tệp nguồn gọn thường có dạng:

~~~text
[import ...;]                       (không bắt buộc)

[trường / phương thức phụ / kiểu thành viên]
phương thức main có thể khởi chạy
[trường / phương thức phụ / kiểu thành viên]
~~~

Theo Java Language Specification (JLS) của Java 25, một **compact compilation unit** có các đặc điểm:

- Có thể bắt đầu bằng các lệnh `import`.
- Phần còn lại gồm các **khai báo thành viên của lớp** (*class member declarations*): trường (*field*), phương thức (*method*), lớp hoặc interface thành viên.
- Phải có **ít nhất một phương thức được khai báo**, và lớp ngầm phải có **ít nhất một `main` đủ điều kiện để khởi chạy**.
- Không có khai báo `package` đặt tên cho tệp này; lớp ngầm thuộc **unnamed package**.
- Không có cú pháp khai báo lớp bao ngoài `class X { ... }`.

Ví dụ tệp `Greeting.java`:

~~~java
// Greeting.java
String prefix = "Xin chào";

String greet(String name) {
    return prefix + ", " + name + "!";
}

void main(String[] args) {
    String name = args.length == 0 ? "Java 25" : args[0];
    IO.println(greet(name));
}
~~~

Chạy:

~~~bash
java Greeting.java
java Greeting.java Minh
~~~

Kết quả lần lượt:

~~~text
Xin chào, Java 25!
Xin chào, Minh!
~~~

Ở ví dụ này, `prefix` là **instance field** của lớp ngầm, `greet` là **instance method** và `main` cũng là một **instance method**. Chúng cùng thuộc một đối tượng do launcher tạo ra khi chạy chương trình.

### 2.1. Hình dung lớp ngầm

Về tư duy, ví dụ vừa rồi gần giống với cấu trúc sau:

~~~java
final class Greeting {
    String prefix = "Xin chào";

    String greet(String name) {
        return prefix + ", " + name + "!";
    }

    void main(String[] args) {
        String name = args.length == 0 ? "Java 25" : args[0];
        IO.println(greet(name));
    }
}
~~~

**Đây chỉ là mô hình giải thích.** Trong compact source file, mã nguồn không khai báo tên `Greeting`. Host system lựa chọn tên lớp được sinh ra, thường theo tên tệp khi dùng JDK trên hệ thống tệp; tên này **không trở thành một định danh có thể tham chiếu trong mã nguồn Java** của tệp.

Ngoài ra, `void main(String[] args)` của lớp có tên cũng là một hình thức `main` có thể khởi chạy trong Java 25. Tính năng **instance main methods** áp dụng cho chương trình Java nói chung, còn **compact source files** là cơ chế bỏ phần khai báo lớp bao ngoài.

### 2.2. Khai báo kiểu thành viên

Một tệp nguồn gọn vẫn có thể có các **member types**:

~~~java
// Cart.java
record Item(String name, int quantity) {}

int totalQuantity(List<Item> items) {
    return items.stream()
            .mapToInt(Item::quantity)
            .sum();
}

void main() {
    List<Item> cart = List.of(
        new Item("Bút", 2),
        new Item("Sổ", 3)
    );
    IO.println("Tổng số lượng: " + totalQuantity(cart));
}
~~~

Ở đây `Item` là **member record** của lớp ngầm, không phải một record top-level độc lập. `List` và `Stream`/API liên quan thuộc `java.base`, nên có thể dùng các tên phù hợp mà không cần import thông thường trong compact source file (xem mục 5).

Những kiểu thành viên giúp tổ chức ví dụ nhỏ. Khi một kiểu cần được nhiều package/module khác dùng như API ổn định, hãy tách thành kiểu được khai báo tường minh tại package phù hợp.

## 3. Đặc điểm thật của lớp được khai báo ngầm

Khi gặp compact source file, Java 25 khai báo ngầm một **top-level class** với các quy tắc được JLS xác định.

| Thuộc tính | Quy tắc Java 25 | Ý nghĩa khi viết chương trình |
|---|---|---|
| Loại | Lớp top-level được khai báo ngầm | Phương thức/trường vẫn thuộc một lớp |
| Khả năng kế thừa | Lớp là **`final`** | Không thể thiết kế lớp con kế thừa từ nó |
| Lớp cha | `java.lang.Object` | Có ngữ nghĩa đối tượng Java thông thường |
| Interface được implement | Không có direct superinterfaces | Không thể đặt `implements` lên lớp ngầm |
| Package | **Unnamed package** | Không dùng làm kiểu công khai cho các named package |
| Mức truy cập lớp | Package access | Lớp không được khai báo `public` |
| Tên lớp | Do host system xác định | Không dùng tên này để tham chiếu trong Java source |
| Constructor | Một **default constructor không tham số** | Không được tự khai báo constructor cho lớp ngầm |
| Thành viên | Field, method, member class/interface | Có thể dùng cả `static`, `private`, v.v. ở thành viên nếu hợp lệ |
| Điểm vào | Phải khai báo candidate `main` | Không thể có compact source file chỉ chứa các hàm tiện ích |

Một khác biệt quan trọng là **phạm vi của tên lớp ngầm rỗng** (*the implicit class declaration is never in scope*). Dù compiler tạo ra một class file, mã nguồn không thể viết kiểu:

~~~java
// Ví dụ không hợp lệ trong compact source file:
// Không thể dựa vào tên file để sử dụng tên của lớp ngầm.
void main() {
    Greeting instance = new Greeting();  // LỖI
}
~~~

Điều này lý giải vì sao không nên xem compact source file là cách khai báo một lớp tiện ích để các lớp khác `new`, `extends` hoặc import. Nó được thiết kế chủ yếu cho **chương trình độc lập hoặc entry point**, không phải một API kiểu dữ liệu để tái sử dụng.

Ngược lại, vì bên trong lớp ngầm vẫn tồn tại một instance, có thể dùng `this` và member method references:

~~~java
String format(String text) {
    return "[" + text.trim() + "]";
}

void main() {
    List<String> values = List.of("  A ", " B  ");
    values.stream()
            .map(this::format)
            .forEach(IO::println);
}
~~~

`this::format` hợp lệ vì trỏ đến phương thức instance của đối tượng lớp ngầm. Không cần biết tên lớp đó.

## 4. Những gì được phép đặt trong tệp

Một compact source file nhận **class members**, không nhận các câu lệnh thực thi tùy ý đặt trực tiếp ngoài phương thức.

| Nội dung ở ngoài `main` | Có hợp lệ không? | Giải thích |
|---|---|---|
| `int count = 0;` | Có | Instance field |
| `static final int LIMIT = 10;` | Có | Static field |
| `String format(String s) { ... }` | Có | Instance method |
| `static int square(int x) { ... }` | Có | Static method |
| `record Point(int x, int y) {}` | Có | Member record |
| `class Helper { ... }` | Có | Member class của lớp ngầm |
| `IO.println("Hello");` đứng riêng | **Không** | Statement phải ở trong phương thức hoặc block hợp lệ |
| `package com.example;` | **Không** | Compact compilation unit không nhận package declaration |
| Constructor của chính lớp ngầm | **Không** | Không có tên lớp để khai báo constructor |
| Initializer block độc lập `{ ... }` | **Không** | Compact unit không cho phép instance initializer của lớp ngầm |
| Static initializer `static { ... }` | **Không** | Compact unit không cho phép static initializer của lớp ngầm |

Ví dụ sai vì đặt statement ở cấp tệp:

~~~java
// Invalid.java — KHÔNG HỢP LỆ
IO.println("Chạy ngay");  // Không thể đặt statement tại đây

void main() {}
~~~

Cách đúng:

~~~java
void main() {
    IO.println("Chạy ngay");
}
~~~

Nếu cần khởi tạo trạng thái, có thể dùng **field initializer**:

~~~java
int initial = 10;
int twice(int value) {
    return value * 2;
}

void main() {
    IO.println(twice(initial));  // 20
}
~~~

Đối với chương trình phức tạp cần constructors, lifecycle, inheritance hoặc lớp top-level có tên rõ ràng, **lớp thông thường** là công cụ phù hợp hơn.

## 5. Import tự động từ `java.base` trong Java 25

Mỗi compact source file ngầm có hiệu lực tương đương:

~~~java
import module java.base;
~~~

Đây là cơ chế import on demand những **public top-level classes/interfaces** trong các package được module `java.base` export. Nhờ đó, ngoài `String` trong `java.lang`, bạn có thể dùng trực tiếp nhiều kiểu như:

- `List`, `Map`, `Set`, `ArrayList`, `HashMap` từ `java.util`.
- `Stream`, `Collectors` từ `java.util.stream`.
- `Path`, `Files` từ `java.nio.file`.
- `LocalDate`, `Instant`, `Duration` từ `java.time`.

Ví dụ `Inventory.java`:

~~~java
void main() {
    Map<String, Integer> quantities = Map.of(
        "bút", 4,
        "sổ", 2
    );

    int total = quantities.values().stream()
            .mapToInt(Integer::intValue)
            .sum();

    IO.println("Các mặt hàng: " + quantities.keySet());
    IO.println("Tổng số lượng: " + total);
}
~~~

Không có import `Map` hoặc `Stream` trong tệp, nhưng Java 25 vẫn hiểu vì chúng được export từ `java.base`.

**Điểm giới hạn:** auto-import **không có nghĩa là toàn bộ JDK hoặc mọi thư viện trên classpath đều được import**. Ví dụ `java.net.http.HttpClient` thuộc module `java.net.http`, không thuộc `java.base`, nên cần import riêng khi sử dụng.

~~~java
import java.net.http.HttpClient;

void main() {
    HttpClient client = HttpClient.newHttpClient();
    IO.println("HTTP client đã được tạo: " + client);
}
~~~

Nếu cần dùng nhiều loại có tên đơn giản trùng nhau, hãy import tường minh hoặc ghi **fully qualified name** để tránh xung đột. Việc import tự động không làm thay đổi visibility hoặc quyền truy cập của các kiểu thuộc module khác.

### 5.1. Phân biệt compact source file và ordinary source file

| Đặc tính | Compact source file | Ordinary source file |
|---|---|---|
| Khai báo lớp bao ngoài | Được bỏ | Cần khai báo các kiểu top-level tương ứng |
| `package` đặt tên | Không được đặt | Được đặt |
| Import `java.lang.*` | Có mặc định | Có mặc định |
| Import mọi package được export từ `java.base` | **Tự động** | Không tự động; có thể dùng `import module java.base;` trong Java 25 |
| Tên lớp chính | Do host chọn, không tham chiếu được trong source | Do người viết khai báo |
| Dùng làm public library API | Không phù hợp | Phù hợp khi thiết kế đúng package/module |

**Module import declarations** là một tính năng riêng (**JEP 511**, chính thức trong Java 25). Nó có thể được viết tường minh trong ordinary source file khi phù hợp; với compact source file, phần `java.base` đã được nhập tự động, nên không phải lặp lại chỉ để dùng `List` hay `LocalDate`.

## 6. `java.lang.IO` là API hiện hành; không dùng cú pháp preview cũ

Java 25 cung cấp lớp **`java.lang.IO`** để thao tác console đơn giản. Một số phương thức:

| Phương thức | Công dụng |
|---|---|
| `IO.println(value)` | In giá trị và xuống dòng |
| `IO.print(value)` | In giá trị ra console |
| `IO.readln(prompt)` | Hiển thị lời nhắc và đọc một dòng từ console |

Ví dụ tương tác:

~~~java
void main() {
    String name = IO.readln("Tên của bạn: ");
    IO.println("Xin chào, " + name + "!");
}
~~~

**Quy tắc quan trọng của Java 25:** `java.lang.IO` tự được thấy vì nằm trong `java.lang`, nhưng **các phương thức static của IO không được import static tự động**. Hãy dùng `IO.println(...)`, `IO.readln(...)`, hoặc thêm explicit static import:

~~~java
import static java.lang.IO.println;

void main() {
    println("Đã import static rõ ràng");
}
~~~

Các tài liệu preview trước đây từng dùng những cách viết khác cho IO. Đối với **Java 25 đã hoàn thiện**, hãy dùng `java.lang.IO` và thêm `IO.` trước tên phương thức nếu không có explicit static import.

`System.out.println` vẫn là Java API hợp lệ. `IO` là lựa chọn thuận tiện cho những thao tác nhập/xuất console đơn giản, không thay cho hệ thống logging, buffered I/O hay xử lý lỗi của một ứng dụng lớn.

## 7. Quy tắc lựa chọn `main` trong Java 25

Từ Java 25, phương thức `main` có thể là **static** hoặc **instance**, có tham số `String[]`/`String...` hoặc không tham số, và không bắt buộc `public`. Phương thức được chọn phải trả về `void` và đủ điều kiện truy cập để launcher gọi.

Các hình thức có thể khởi chạy:

~~~java
// Ví dụ thay thế nhau, KHÔNG đặt toàn bộ trong cùng một file:
void main() { /* ... */ }
~~~

~~~java
void main(String[] args) { /* ... */ }
~~~

~~~java
static void main() { /* ... */ }
~~~

~~~java
public static void main(String[] args) { /* ... */ }
~~~

Không dùng `private void main()` làm điểm vào: phương thức private không phải candidate launchable main. Một compact source file không có candidate `main` sẽ không đạt yêu cầu biên dịch.

### 7.1. Nếu có cả hai dạng `main` thì sao?

Java 25 chọn `main` có **một tham số `String[]`** trước. Nếu không có ứng viên dạng đó mới chọn `main()`. Ví dụ:

~~~java
void main() {
    IO.println("Không tham số");
}

void main(String[] args) {
    IO.println("Số đối số: " + args.length);
}
~~~

Khi chạy `java ChooseMain.java A B`, chương trình chọn `main(String[] args)` và in:

~~~text
Số đối số: 2
~~~

Việc có hai phương thức cùng tên ở đây là **overloading**, không phải hai entry point được chạy tuần tự. Không dựa vào thứ tự khai báo các phương thức để quyết định phương thức nào được gọi.

### 7.2. `main` instance được chạy ra sao?

Khi launcher chọn một **instance main**, runtime tạo instance của lớp tương ứng bằng constructor không tham số trước khi gọi phương thức. Với compact source file, constructor mặc định này được khai báo ngầm.

~~~java
int times = 0;

void main() {
    times++;
    IO.println("Lần gọi trên instance: " + times);
}
~~~

Một lần khởi chạy thông thường cho ra:

~~~text
Lần gọi trên instance: 1
~~~

Đừng hiểu `times` là biến top-level toàn cục: nó là **field của đối tượng**. Cũng đừng suy diễn từ ví dụ này rằng mọi phương thức `main` đều là instance; chương trình vẫn có thể khai báo static main.

## 8. Từ tệp nguồn gọn sang tệp có lớp tường minh

Sự giản lược cú pháp không đồng nghĩa chương trình phải mãi nằm trong một file. Khi cần package, unit test chuyên biệt, public API hoặc nhiều kiểu dùng chung, bạn có thể chuyển chương trình sang lớp tường minh.

**Ban đầu — `Report.java` dạng compact:**

~~~java
String summary(List<Integer> values) {
    int sum = values.stream().mapToInt(Integer::intValue).sum();
    return "Tổng: " + sum;
}

void main() {
    IO.println(summary(List.of(3, 5, 7)));
}
~~~

**Sau đó — khai báo lớp và package:**

~~~java
package com.example.report;

import java.util.List;

public final class Report {
    String summary(List<Integer> values) {
        int sum = values.stream().mapToInt(Integer::intValue).sum();
        return "Tổng: " + sum;
    }

    public static void main(String[] args) {
        Report report = new Report();
        IO.println(report.summary(List.of(3, 5, 7)));
    }
}
~~~

Ở bản thứ hai:

- Có **package được đặt tên**, nên có thể tổ chức và phân phối lớp rõ ràng.
- `List` được import tường minh; ordinary source file không tự import tất cả package từ `java.base`.
- Main dùng dạng static quen thuộc, thuận tiện khi tích hợp launcher/build truyền thống; **không phải bắt buộc** theo Java 25.
- Các thành phần tái sử dụng như domain model, service hoặc thư viện có thể tách thành lớp/interface và kiểm thử độc lập.

Quá trình phát triển từ compact sang ordinary source không làm thay đổi các nguyên tắc Java cơ bản như type checking, visibility, exception handling hay quản lý tài nguyên.

## 9. Khi nào nên và không nên dùng tệp nguồn gọn?

| Tình huống | Đánh giá | Vì sao |
|---|---|---|
| Học biến, điều kiện, vòng lặp, collection | **Rất phù hợp** | Loại bỏ cú pháp lớp không liên quan bài học |
| Ví dụ ngắn để giải thích Java 25 API | **Phù hợp** | Chạy trực tiếp, ít boilerplate |
| Công cụ CLI một tệp, không cần API công khai | **Có thể phù hợp** | Entry point đơn giản, dùng `args` dễ dàng |
| Thử thuật toán hoặc thao tác file cục bộ | **Có thể phù hợp** | Có thể dùng `Path`, `Files` từ `java.base` |
| Thư viện dùng bởi nhiều package/module | **Không phù hợp** | Lớp ngầm không có tên tham chiếu được, không tạo public API |
| Ứng dụng nhiều module có ranh giới rõ | **Ưu tiên lớp/package/module tường minh** | Cần namespace, dependency management và API ổn định |
| Framework dựa vào class naming, annotations và code generation | **Cân nhắc kỹ** | Thiếu lớp có tên tường minh làm cấu trúc tích hợp khó kiểm soát |
| Lớp cần kế thừa hoặc khai báo constructor riêng | **Không phù hợp** | Lớp ngầm là final và không có constructor tự khai báo |

Compact source files là công cụ cho **programming in the small**. Khi một chương trình trở thành thành phần được nhiều nhóm dùng và cần lifecycle/namespace rõ ràng, thiết kế bằng lớp tường minh thường dễ bảo trì hơn.

### 9.1. Không nên đồng nhất với các cơ chế khác

- **Single-file source-code launcher** là cơ chế chạy trực tiếp một tệp `*.java` bằng `java File.java`; nó có thể chạy cả ordinary source file và compact source file. Đây là **cách khởi chạy**, không phải định nghĩa của compact syntax.
- **JShell** là công cụ tương tác nhập các đoạn Java, với quy tắc session riêng; nó không đồng nghĩa với một compact compilation unit trong file.
- **Local variables** ở trong phương thức vẫn có phạm vi khối như Java thông thường; các field ngoài `main` thuộc lớp ngầm và không phải biến toàn cục.
- **Unnamed package** là package không được đặt tên, khác với một **named package** được khai báo bằng `package ...;`. Không dùng tệp nguồn gọn để thay cho mô hình JPMS của ứng dụng lớn.
- **Compact constructor** của `record` là một khái niệm khác hẳn; nó không liên quan đến từ “compact” trong tên compact source file.

## 10. Những lỗi điển hình và cách sửa

| Dấu hiệu | Nguyên nhân | Hướng sửa |
|---|---|---|
| `javac` báo cú pháp không hợp lệ ở `void main()` | Đang dùng JDK quá cũ hoặc compiler không hỗ trợ | Kiểm tra `javac -version`, chạy JDK 25+ |
| `cannot find symbol: println` | Dùng lời gọi trần từ preview cũ | Đổi thành `IO.println(...)` hoặc explicit static import |
| `cannot find symbol: IO` | Không dùng JDK 25+ hoặc cấu hình API/toolchain sai | Kiểm tra Java home, version và compile options |
| Code đặt `IO.println(...)` ngoài phương thức không compile | Compact unit nhận class members, không nhận top-level statements | Đưa statement vào `main` hoặc phương thức |
| Đặt `package x.y;` trước `void main()` lỗi | Compact unit thuộc unnamed package | Chuyển thành ordinary class nếu cần named package |
| Không thể dùng tên lớp sinh ra trong Java source | Phạm vi của implicit class name rỗng | Khai báo lớp tường minh nếu cần type reference |
| Không thể khai báo constructor hoặc `extends` | Lớp ngầm được tạo theo quy tắc cố định | Chuyển sang ordinary class |
| Có phương thức nhưng chương trình không launch được | Không có candidate `main` hợp lệ | Khai báo `void main()` hoặc `void main(String[] args)` |
| Dùng kiểu ngoài `java.base` nhưng không resolve | Auto-import chỉ bao phủ `java.base` | Import đúng kiểu/module và cấu hình module path |
| `java File.java` và `javac File.java` cho kết quả khác kỳ vọng | Đang chạy JDK/toolchain khác nhau | Kiểm tra `java -version`, `javac -version`, đường dẫn thực thi |

Khi một ví dụ từ tài liệu cũ yêu cầu `--enable-preview` cho compact source file hoặc dùng `java.io.IO`, hãy cập nhật sang **quy tắc Java 25 đã chính thức hóa**, tránh giữ lại cú pháp preview đã thay đổi.

## 11. Bài thực hành tổng hợp

### Bài A — Phân tích cấu trúc

Với tệp `Sales.java`:

~~~java
List<Integer> prices = List.of(100, 200, 50);

int sum() {
    return prices.stream().mapToInt(Integer::intValue).sum();
}

void main() {
    IO.println("Doanh thu: " + sum());
}
~~~

Hãy giải thích:

1. Tại sao `prices` không phải local variable mà là instance field?
2. Vì sao `List` có thể dùng không cần `import java.util.List;`?
3. Constructor của implicit class đến từ đâu?
4. Vì sao không thể gọi `new Sales()` trong mã nguồn này để tạo một instance theo tên tệp?
5. Nếu cần export `sum()` như API cho module khác thì nên đổi cấu trúc ra sao?

### Bài B — Chương trình đọc tham số

Tạo tệp `Discount.java` chỉ bằng compact syntax:

~~~java
int percent = 10;

int discounted(int price) {
    return price * (100 - percent) / 100;
}

void main(String[] args) {
    if (args.length != 1) {
        IO.println("Cách dùng: java Discount.java <gia>");
        return;
    }

    int price = Integer.parseInt(args[0]);
    IO.println("Giá sau giảm: " + discounted(price));
}
~~~

Chạy:

~~~bash
java Discount.java 200
~~~

Kết quả mong đợi:

~~~text
Giá sau giảm: 180
~~~

Bài tập mở rộng: xử lý `NumberFormatException`, từ chối giá âm và chuyển `Discount` thành ordinary class có package. Đầu ra của bản ordinary class phải tương đương với bản compact cho dữ liệu hợp lệ.

### Bài C — Kiểm chứng `main` overload

Trong tệp `Launch.java`, khai báo cả `void main()` và `void main(String[] args)`. Chạy với hoặc không có đối số rồi giải thích tại sao Java 25 luôn ưu tiên phương thức có `String[]` nếu tồn tại candidate đó.

Thử thay `main(String[] args)` thành `private void main(String[] args)` và quan sát cách launcher chọn candidate còn lại. Nếu chỉ còn phương thức private, lớp ngầm không có candidate main hợp lệ.

### Bài D — Xác nhận giới hạn về package

Thử thêm `package training;` vào một compact source file. Ghi lại lỗi compile rồi refactor thành ordinary class có `package training;` và `import` thích hợp. Nêu rõ lợi ích của ranh giới package và lý do compact source file không thay thế toàn bộ cấu trúc ứng dụng Java.

## 12. Checklist áp dụng trong dự án hiện đại

Khi quyết định dùng compact source file, kiểm tra:

- **Version:** JDK/toolchain đặt ở Java 25+; tính năng đã chính thức nên không cần preview flag.
- **Mục đích:** chủ yếu là entry point độc lập, bài học hoặc công cụ nhỏ.
- **Cấu trúc:** không có package statement, có candidate `main` hợp lệ, chỉ khai báo class members.
- **API:** nếu cần kiểu công khai, inheritance, constructor hoặc package named thì dùng ordinary class.
- **Console I/O:** dùng `IO.println`/`IO.readln` đúng namespace `java.lang.IO`.
- **Imports:** tự động có `java.base` trong compact file; các module khác vẫn phải import và cấu hình cho phù hợp.
- **Testing:** kiểm tra chạy trực tiếp bằng `java File.java` và kết quả của tham số đầu vào; nếu cần thư viện lâu dài, tách logic ra lớp có tên để unit test.
- **Khả năng bảo trì:** không phụ thuộc tên class file do implementation sinh ra như một public API.
- **Nội dung hiện hành:** tránh sao chép cú pháp của các bản preview trước Java 25 mà chưa điều chỉnh.

## Tài liệu tham khảo chính thức

- [JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512): đề xuất đã được hoàn thiện trong Java 25, mục tiêu và cấu trúc ngôn ngữ.
- [Oracle Java SE 25 — Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): hướng dẫn viết, chạy tệp nguồn gọn và `java.lang.IO`.
- [Java Language Specification SE 25 §7.3 — Compilation Units](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3): cú pháp của compact compilation unit và import `java.base`.
- [Java Language Specification SE 25 §8.1.8 — Implicitly Declared Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.8): thuộc tính và giới hạn lớp ngầm.
- [Java Language Specification SE 25 §12.1.4 — Invoke a main Method](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1.4): candidate main và quy tắc lựa chọn điểm vào.
- [Oracle Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): đối chiếu JEP 512 và các tính năng chính thức của Java 25.
