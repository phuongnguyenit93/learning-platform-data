# Tệp nguồn, lớp và phương thức trong chương trình Java tối thiểu

> **Java core — language-basics / Cấu trúc chương trình**  
> **Mốc thực hành:** JDK 17 trở lên, sử dụng cú pháp chương trình truyền thống tương thích Java 17.  
> **Sau bài học, bạn có thể:** tạo tệp `.java` đúng tên, phân biệt tệp nguồn với lớp và phương thức, viết `main`, tự biên dịch bằng `javac`, chạy bằng `java`, đọc kết quả và nhận diện những lỗi cấu trúc thường gặp.

## 1. Một chương trình Java tối thiểu có những gì?

Trước khi học các phần phức tạp, hãy quan sát một tệp duy nhất tên **HelloWorld.java**:

~~~java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Xin chào, Java 17!");
    }
}
~~~

Đây là một chương trình **hoàn chỉnh** dùng cú pháp Java 17. Nó có ba tầng dễ nhận ra:

| Thành phần | Trong ví dụ | Vai trò |
| --- | --- | --- |
| **Tệp nguồn (source file)** | `HelloWorld.java` | Văn bản chứa mã nguồn Java để compiler đọc |
| **Lớp (class)** | `public class HelloWorld` | Nhóm khai báo dữ liệu và hành vi có tên; đây là lớp chứa chương trình |
| **Phương thức (method)** | `main(String[] args)` | Nhóm câu lệnh có tên; trong ví dụ là điểm bắt đầu thực thi |
| **Câu lệnh (statement)** | `System.out.println(...);` | Chỉ thị thực hiện một thao tác, ở đây in một dòng |

Java không chạy “tệp văn bản” giống một bản ghi chú. Trong quy trình quen thuộc, **compiler biên dịch** `.java` thành bytecode `.class`; **Java launcher/JVM** nạp lớp có điểm vào và thực thi các câu lệnh trong phương thức `main`.

~~~mermaid
flowchart LR
    S["HelloWorld.java: mã nguồn"] --> C["javac: biên dịch"]
    C --> B["HelloWorld.class: bytecode"]
    B --> J["java: khởi chạy lớp"]
    J --> M["main(): thực thi câu lệnh"]
    M --> O["Console: Xin chào, Java 17!"]
~~~

**Một tệp không đồng nghĩa một lớp trong mọi trường hợp.** Một tệp `.java` có thể khai báo nhiều top-level class với giới hạn quyền truy cập và tên tệp; ví dụ nhập môn này cố ý chỉ có **một `public` class** để người học tập trung vào cấu trúc cơ bản.

## 2. Tạo tệp, biên dịch và chạy bằng JDK 17+

### Bước 1 — Tạo tệp nguồn

Dùng trình soạn thảo văn bản hoặc IDE tạo file **HelloWorld.java**, dán nguyên đoạn mã ở mục 1, lưu dưới dạng UTF-8. Chú ý:

- Tên `HelloWorld.java` khớp đúng chữ hoa/chữ thường với `public class HelloWorld`.
- Tệp không phải `HelloWorld.java.txt` (một số hệ điều hành ẩn phần mở rộng).
- Không thêm ký hiệu Markdown như `~~~java` vào **nội dung file**: chỉ chép mã nằm giữa hai hàng rào code.

### Bước 2 — Xác minh công cụ

Trong terminal, vào thư mục chứa file rồi kiểm tra:

~~~bash
java -version
javac -version
~~~

Bạn cần một **JDK** để có compiler `javac`. Các bản JDK tương thích Java 17 hoặc mới hơn có thể thực hành bài này; nếu cả hai lệnh không được tìm thấy, cần kiểm tra cài đặt JDK và cấu hình đường dẫn trước khi chạy tiếp.

### Bước 3 — Biên dịch

Trong thư mục chứa `HelloWorld.java`:

~~~bash
javac -encoding UTF-8 HelloWorld.java
~~~

Nếu mã hợp lệ, lệnh thường **không in thông báo thành công** và tạo tệp `HelloWorld.class` cạnh mã nguồn (với ví dụ không có `package` và không chỉ định `-d`).

### Bước 4 — Chạy lớp

~~~bash
java HelloWorld
~~~

Đầu ra chính xác:

~~~text
Xin chào, Java 17!
~~~

Sau `java` là **tên lớp** `HelloWorld`, **không** phải `HelloWorld.class`. Tên file `.class` chỉ giúp bạn quan sát sản phẩm compiler; cú pháp của launcher khi chạy class là tên lớp.

### Cách khác: chạy thẳng tệp nguồn

Java launcher từ **JDK 11** hỗ trợ source-file mode:

~~~bash
java HelloWorld.java
~~~

Với ví dụ này, kết quả vẫn là:

~~~text
Xin chào, Java 17!
~~~

Launcher thực hiện công đoạn biên dịch cần thiết rồi chạy chương trình; không cần bạn gọi `javac` riêng. Đừng suy luận rằng JVM trực tiếp thực thi từng dòng mã nguồn. Hai lệnh `java HelloWorld` và `java HelloWorld.java` có **chế độ xử lý khác nhau**: một bên khởi chạy class đã biên dịch, một bên nhận đường dẫn file nguồn.

## 3. Đọc cú pháp từng dòng

Hãy chia mã ví dụ thành những lớp ý nghĩa:

~~~java
public class HelloWorld {                 // Khai báo lớp
    public static void main(String[] args) {  // Khai báo phương thức
        System.out.println("Xin chào, Java 17!"); // Câu lệnh
    }                                       // Hết thân phương thức
}                                           // Hết thân lớp
~~~

### `public class HelloWorld`

- `class`: khai báo một lớp.
- `HelloWorld`: tên lớp, phân biệt chữ hoa/chữ thường.
- `public`: lớp công khai; trong ví dụ top-level public class, tên file nguồn phải là `HelloWorld.java`.
- `{ ... }`: thân lớp. Trong thân có thể khai báo **field**, **constructor**, **method** và những thành phần khác; ví dụ này chỉ cần một method.

### `public static void main(String[] args)`

Ở cú pháp điểm vào thông dụng của **Java 17**:

| Thành phần | Ý nghĩa trong phương thức `main` |
| --- | --- |
| `public` | Launcher có thể truy cập điểm vào công khai |
| `static` | Gọi method qua lớp; không cần tạo đối tượng `HelloWorld` trước |
| `void` | Phương thức không trả về một giá trị |
| `main` | Tên phương thức điểm vào được Java launcher nhận biết |
| `String[] args` | Mảng các đối số dạng chuỗi được truyền từ dòng lệnh |
| `{ ... }` | Các câu lệnh chạy khi `main` được gọi |

Tên biến `args` có thể đổi thành tên khác; quan trọng là **chữ ký/phạm vi phù hợp** với cách launcher Java 17 tìm entry point. Dạng `String... args` cũng tương đương với một tham số mảng khi khai báo phương thức Java, nhưng người mới nên bắt đầu bằng `String[] args`.

**`main` không phải “lệnh đặc biệt đặt ở bất cứ đâu”.** Nó là một phương thức Java phải nằm trong một lớp theo cấu trúc chương trình truyền thống của Java 17. Các JDK mới hơn có thể hỗ trợ dạng chương trình đơn giản hóa khác; đừng nhầm những tính năng đó với quy tắc thực hành Java 17 của bài này.

### `System.out.println("...");`

- `System`: lớp API chuẩn Java.
- `out`: luồng xuất chuẩn để in kết quả.
- `println(...)`: method được gọi; trong ví dụ nó in chuỗi và xuống dòng.
- Dấu `;`: kết thúc câu lệnh.
- Chuỗi Java dùng dấu nháy kép `"..."`; dấu nháy đơn thường dành cho một ký tự `char`.

Trong Java, **chữ hoa/chữ thường có ý nghĩa**: `System` không phải `system`; `println` không phải `printLn`; `HelloWorld` không phải `Helloworld`.

## 4. Lớp là gì, phương thức là gì?

Một **lớp** mô tả một loại đối tượng hoặc gom các khả năng liên quan. Một **phương thức** là một hành vi có tên, có thể nhận tham số, thực hiện công việc và trả kết quả. Không phải mỗi phương thức đều phải in ra màn hình.

Ví dụ hình dung:

~~~java
class Calculator {
    static int add(int left, int right) {
        return left + right;
    }
}
~~~

- `Calculator` là lớp.
- `add` là phương thức.
- `int left` và `int right` là hai **tham số** đầu vào.
- `return left + right;` trả về giá trị kiểu `int`.
- `static` cho phép gọi `Calculator.add(2, 3)` mà không cần tạo đối tượng.

Đây là đoạn **minh họa thành phần**, chưa phải chương trình tự khởi chạy vì nó không khai báo điểm vào `main`. Để biên dịch/chạy thành chương trình hoàn chỉnh, hãy xem ví dụ tiếp theo.

### Phân biệt các thuật ngữ gần nhau

| Thuật ngữ | Ví dụ | Ghi nhớ |
| --- | --- | --- |
| Khai báo method | `static int add(int a, int b) { ... }` | Xác định tên, tham số, kiểu trả về và thân |
| Gọi method | `add(2, 3)` | Yêu cầu thực thi method với các đối số cụ thể |
| Tham số (parameter) | `a`, `b` trong khai báo | Biến cục bộ nhận dữ liệu khi method được gọi |
| Đối số (argument) | `2`, `3` khi gọi | Giá trị truyền vào method |
| Kiểu trả về | `int` hoặc `void` | Có trả giá trị thuộc kiểu ấy hay không |
| Method `static` | `Calculator.add(2, 3)` | Gắn với lớp, không bắt buộc có object |
| Method instance | `lamp.turnOn()` | Gọi thông qua một đối tượng cụ thể |

Đừng nhầm `return` với `System.out.println`: `return` đưa giá trị **về nơi gọi**, còn `println` tạo **đầu ra console**. Bạn có thể tính toán và trả kết quả mà không in gì.

## 5. Ví dụ chạy được: một lớp chứa nhiều phương thức

Tạo file **MethodDemo.java**:

~~~java
public class MethodDemo {

    private static String makeGreeting(String name) {
        if (name == null || name.isBlank()) {
            return "Xin chào, khách!";
        }
        return "Xin chào, " + name.strip() + "!";
    }

    private static int add(int left, int right) {
        return Math.addExact(left, right);
    }

    public static void main(String[] args) {
        String guest = args.length == 0 ? "bạn" : args[0];

        String greeting = makeGreeting(guest);
        int total = add(7, 5);

        System.out.println(greeting);
        System.out.println("7 + 5 = " + total);
        System.out.println("Số đối số: " + args.length);
    }
}
~~~

Biên dịch, chạy không có đối số:

~~~bash
javac -encoding UTF-8 MethodDemo.java
java MethodDemo
~~~

Kết quả:

~~~text
Xin chào, bạn!
7 + 5 = 12
Số đối số: 0
~~~

Chạy với một đối số chứa khoảng trắng (trong Bash hoặc PowerShell):

~~~bash
java MethodDemo "Lan Anh"
~~~

Kết quả:

~~~text
Xin chào, Lan Anh!
7 + 5 = 12
Số đối số: 1
~~~

**Luồng thực thi:**

1. Launcher gọi `main`.
2. `main` xem có đối số dòng lệnh không. Nếu không, dùng chuỗi mặc định `"bạn"`.
3. `main` gọi `makeGreeting(guest)`. Method này kiểm tra tên và **trả một chuỗi**, chứ không in.
4. `main` gọi `add(7, 5)`. Method tính rồi **trả 12**.
5. Chỉ `main` gọi `println` để in ba dòng ra console.

`private` ở hai method phụ nghĩa là chỉ code trong chính lớp `MethodDemo` gọi được chúng trực tiếp. Cả hai đều `static` để `main` (cũng `static`) có thể gọi mà không tạo một `MethodDemo`.

### Điều gì xảy ra với đối số đặc biệt?

| Cách chạy | Kết quả đáng chú ý | Vì sao |
| --- | --- | --- |
| `java MethodDemo` | `Xin chào, bạn!` | `args.length == 0` |
| `java MethodDemo "Lan Anh"` | `Xin chào, Lan Anh!` | Một đối số có dấu cách nhờ quote |
| `java MethodDemo ""` | `Xin chào, khách!` | `args[0]` là chuỗi rỗng; `isBlank()` đúng |
| `java MethodDemo An Bình` | Chào `An`; số đối số là 2 | Shell tách thành hai đối số; ví dụ chỉ dùng `args[0]` |

Bài này chỉ xử lý đối số **đầu tiên** làm tên; đó là hợp đồng của ví dụ, không có nghĩa Java tự bỏ mọi đối số khác. Luôn kiểm tra `args.length` trước khi truy cập `args[0]` để tránh `ArrayIndexOutOfBoundsException`.

### Vì sao dùng `Math.addExact`?

Trong ví dụ, `7 + 5` không tràn số. Tuy nhiên, phép cộng `int` thông thường có thể tràn miền số mà không cảnh báo. `Math.addExact(left, right)` ném `ArithmeticException` khi tràn số. Chọn hàm này nhằm minh họa rằng **hành vi method** không chỉ là phép tính: nó có thể có hợp đồng lỗi. Với chương trình thực, cần kiểm thử ca biên nếu dữ liệu đến từ người dùng.

## 6. Phương thức `static` và phương thức của đối tượng

Ở `MethodDemo`, các method đều `static`. Một lớp cũng có thể tạo đối tượng mang trạng thái riêng và có method **không static**. Tạo file **LampDemo.java**:

~~~java
public class LampDemo {
    private boolean on;

    public void turnOn() {
        on = true;
    }

    public String status() {
        return on ? "BẬT" : "TẮT";
    }

    public static void main(String[] args) {
        LampDemo lamp = new LampDemo();

        System.out.println(lamp.status());
        lamp.turnOn();
        System.out.println(lamp.status());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LampDemo.java
java LampDemo
~~~

Kết quả:

~~~text
TẮT
BẬT
~~~

- `LampDemo lamp = new LampDemo();` tạo một **đối tượng**.
- `lamp.status()` và `lamp.turnOn()` là lời gọi method **instance** thông qua object `lamp`.
- `on` là **field** của đối tượng, có giá trị mặc định `false` đối với kiểu `boolean` khi tạo object.
- `main` là `static` để launcher khởi chạy; bên trong `main`, ta chủ động tạo object để gọi các method không static.
- `turnOn()` có kiểu trả về `void`: nó thay đổi trạng thái của `lamp`, không trả một giá trị.

**Sai lầm thường gặp:**

~~~java
// Trong một phương thức static của LampDemo, lệnh sau không hợp lệ:
turnOn(); // Không có object nào được chỉ ra để gọi method instance.
~~~

Trong `main` của ví dụ, bạn phải có đối tượng thích hợp rồi gọi `lamp.turnOn()`. Đây là khác biệt cơ bản giữa **hành vi của lớp** và **hành vi trên một đối tượng**, không phải lý do để biến mọi method thành `static`.

## 7. Tệp nguồn có thể chứa bao nhiêu lớp?

Một tệp nguồn có thể có nhiều **top-level class**, nhưng thông thường chỉ được có **tối đa một top-level public class**. Nếu có top-level public class, tên tệp phải khớp tên class ấy.

Ví dụ lưu trong **MainWithHelper.java**:

~~~java
public class MainWithHelper {
    public static void main(String[] args) {
        Helper.sayHello();
    }
}

class Helper {
    static void sayHello() {
        System.out.println("Helper đã chạy!");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MainWithHelper.java
java MainWithHelper
~~~

Kết quả:

~~~text
Helper đã chạy!
~~~

Compiler thông thường tạo **`MainWithHelper.class`** và **`Helper.class`**. Hai lớp nằm trong **một tệp nguồn** vì `Helper` không phải top-level public class. Tuy vậy, khi project lớn lên, thường nên tách những lớp có trách nhiệm riêng ra các file phù hợp để dễ tìm, kiểm thử và bảo trì; đây là **quy ước tổ chức có ích**, không phải luật “mỗi tệp Java chỉ được chứa một class”.

Nếu tạo hai **top-level public class** khác tên trong cùng `MainWithHelper.java`, compiler sẽ báo lỗi về yêu cầu tên tệp của public class. Đừng nhầm với **lớp lồng nhau** (nested class), vốn là một trường hợp cú pháp khác.

## 8. Khi có `package`, tên lớp chạy sẽ thay đổi

Các ví dụ trước không khai báo `package` để bước đầu ngắn gọn. Ở một project thật, các lớp thường được đặt trong một package có tên, ví dụ `demo`.

Cây project tối thiểu:

~~~text
project/
└── src/
    └── demo/
        └── PackageHello.java
~~~

Nội dung `src/demo/PackageHello.java`:

~~~java
package demo;

public class PackageHello {
    public static void main(String[] args) {
        System.out.println("Xin chào từ package demo!");
    }
}
~~~

Từ thư mục `project`, biên dịch và chạy:

**Bash (macOS/Linux):**

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out src/demo/PackageHello.java
java -cp out demo.PackageHello
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac -encoding UTF-8 -d out src/demo/PackageHello.java
java -cp out demo.PackageHello
~~~

Đầu ra:

~~~text
Xin chào từ package demo!
~~~

Compiler tạo `out/demo/PackageHello.class`. Khi chạy, bạn truyền **tên lớp đầy đủ** `demo.PackageHello` và **gốc classpath** `out`. Không chạy `java PackageHello` ở đây vì class thực sự thuộc package `demo`.

**Đây là ví dụ phụ để giải thích cấu trúc tệp/lớp, không phải hướng dẫn cấu hình project nhiều module.** Bạn không cần Maven hay Gradle để hiểu một chương trình tối thiểu; các build tool đó hữu ích khi project có nhiều file và phụ thuộc hơn.

## 9. Những lỗi thường gặp khi viết chương trình đầu tiên

| Triệu chứng/lỗi | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `class HelloWorld is public, should be declared in a file named HelloWorld.java` | Tên file không khớp top-level public class | Đặt đúng `HelloWorld.java` |
| `cannot find symbol` với `System`, `String` hoặc tên method | Viết sai hoa/thường hoặc định danh | So lại `System`, `String`, `println` và tên method |
| `';' expected` | Thiếu dấu chấm phẩy sau statement cần có `;` | Kiểm tra dòng gọi `println`/gán biến |
| `reached end of file while parsing` | Thiếu dấu `}` hoặc cú pháp chưa hoàn chỉnh | Đối chiếu dấu ngoặc mở/đóng của class và method |
| `non-static method ... cannot be referenced from a static context` | Gọi instance method trong `main` mà không có object | Tạo object rồi gọi `object.method()` |
| `Main method not found in class ...` | Không có entry point Java 17 phù hợp | Kiểm tra `public static void main(String[] args)` |
| `Could not find or load main class` | Sai tên lớp/package hoặc classpath | Kiểm tra `.class`, tên đầy đủ và `-cp` |
| `ArrayIndexOutOfBoundsException` với `args[0]` | Không truyền đối số mà vẫn đọc phần tử đầu | Kiểm tra `args.length` |
| `java HelloWorld.class` thất bại | Truyền tên file thay vì tên lớp | Dùng `java HelloWorld` khi chạy bytecode |

**Biên dịch và chạy là hai giai đoạn khác nhau.** Nếu `javac` báo lỗi cú pháp, chương trình chưa tạo được bytecode mới hợp lệ. Nếu `javac` thành công nhưng `java` báo không tìm thấy main class, hãy kiểm tra **tên lớp và classpath**, không nhất thiết sửa logic in ra màn hình.

### Ba kiểm tra nhanh

1. **Tên file:** top-level `public class Example` phải nằm trong `Example.java`.
2. **Chữ ký entry point:** với cấu trúc tiêu chuẩn Java 17, dùng `public static void main(String[] args)`.
3. **Lệnh chạy:** không có package thì `java Example`; có `package demo;` và classpath `out` thì `java -cp out demo.Example`.

## 10. Bài tập thực hành

**Bài 1 — Đổi nội dung in:** Trong `HelloWorld.java`, sửa chuỗi thành `"Tôi đang học Java!"` rồi biên dịch và chạy lại. Quan sát vì sao chỉ sửa tệp `.java` mà chạy tệp `.class` cũ **chưa chắc** đã hiển thị nội dung mới, nếu không biên dịch lại.

**Bài 2 — Viết method trả kết quả:** Trong `MethodDemo`, thêm method `private static int square(int number)`, trả về bình phương. Gọi từ `main` với `4`, kỳ vọng in `16`. Thử suy nghĩ về tràn `int` với đầu vào rất lớn.

**Bài 3 — Hiểu tham số:** Chạy `java MethodDemo "Ngọc Lan"` và `java MethodDemo Ngọc Lan`. So sánh `args.length` và chuỗi chào để thấy dấu nháy ở **shell** ảnh hưởng cách truyền đối số thế nào.

**Bài 4 — Instance method:** Thêm method `turnOff()` vào `LampDemo`, gọi theo thứ tự: `turnOn()`, `turnOff()` và in trạng thái sau mỗi lượt. Kết quả nên phản ánh thay đổi trạng thái trên **cùng một object**.

**Bài 5 — Tìm lỗi cấu trúc:** Đoạn sau không tạo được chương trình chạy chuẩn trong Java 17. Hãy chỉ ra lý do và sửa:

~~~java
public class Sample {
    public void main(String[] args) {
        System.out.println("Hello");
    }
}
~~~

*Gợi ý:* Trong cấu trúc đang học, `main` phải là `static` để launcher gọi được mà không cần tạo object; đổi thành `public static void main(String[] args)`.

## 11. Tự kiểm tra kiến thức

Bạn đã nắm bài nếu trả lời được:

1. `HelloWorld.java` khác `HelloWorld.class` như thế nào?
2. Vì sao file chứa `public class HelloWorld` cần tên `HelloWorld.java`?
3. `main` là class hay method? Vì sao `main` trong Java 17 thường có `static`?
4. `return` và `System.out.println` khác nhau thế nào?
5. Method `static` và instance method được gọi theo hai cách nào?
6. Vì sao `java -cp out demo.PackageHello` khác `java PackageHello`?
7. Với input không có đối số, vì sao nên kiểm tra `args.length` trước `args[0]`?

**Ghi nhớ:** **Tệp nguồn** là nơi viết mã; **lớp** tổ chức các thành phần của chương trình; **phương thức** định nghĩa hành vi; **`main`** là điểm khởi chạy truyền thống của chương trình Java 17. Từ một file `.java` và vài dòng `javac`/`java`, bạn đã có thể tạo, chạy và giải thích cấu trúc chương trình Java cơ bản.
