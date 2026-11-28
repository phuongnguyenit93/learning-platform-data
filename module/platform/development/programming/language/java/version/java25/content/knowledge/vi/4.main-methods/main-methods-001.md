# Những dạng phương thức main được chấp nhận trong Java 25

## 1. Bối cảnh: main không còn chỉ có một cách viết

Bài thuộc chương **Hàm main** của module **JAVA_VERSION_JAVA25**. Java 25 mở rộng cách bắt đầu một chương trình Java theo **JEP 512 — Compact Source Files and Instance Main Methods**, đã trở thành tính năng **chính thức** của Java SE 25. Điều này phù hợp với định hướng học Java 25 trong phát triển hiện đại: có thể viết các chương trình nguồn gọn, dùng module import, phương thức khởi tạo linh hoạt, `ScopedValue` và các API mới mà vẫn giữ khả năng chuyển dần sang cấu trúc ứng dụng lớn.

Trong nhiều năm, một chương trình được giới thiệu như sau:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Đây **vẫn là cách viết hợp lệ và phù hợp** trong Java 25, đặc biệt với ứng dụng hoặc framework cần điểm khởi động rõ ràng. Nhưng kể từ JDK 25, chương trình nhỏ còn có thể viết:

~~~java
// Hello.java — compact source file, không khai báo class tường minh
void main() {
    IO.println("Hello, Java 25!");
}
~~~

Chạy:

~~~bash
java Hello.java
~~~

Cả hai là Java 25 chuẩn. **Không thêm `--enable-preview`:** JEP 512 đã hoàn tất quá trình preview ở Java 25. Những bài viết nói `void main()` hoặc compact source file “chỉ chạy khi bật preview” phản ánh các bản Java trước và không còn đúng với JDK 25.

### Mục tiêu học tập

Sau bài này, bạn sẽ biết cách:

1. Nhận diện chính xác một **candidate main method** theo Java Language Specification 25.
2. Liệt kê 12 dạng `main` hợp lệ theo ba chiều: access modifier, `static`/instance và danh sách tham số.
3. Hiểu rằng `String[]` và `String...` là cùng một kiểu tham số trong chữ ký phương thức.
4. Dự đoán `main` nào được launcher chọn khi một class có nhiều overload.
5. Biết khi nào JVM cần tạo object, và vì sao instance `main` phụ thuộc constructor không tham số có thể truy cập.
6. Phân biệt một class tường minh và compact source file; chạy thử hai hình thức mà không dùng preview.
7. Tránh các lỗi về kiểu trả về, `private`, constructor, compiler/runtime version và công cụ build.

Tài liệu học thuật chính: **Java Language Specification (JLS) 25, `12.1.4** và **JEP 512**.

## 2. Quy tắc chính thức: thế nào là một candidate main?

Theo JLS 25 `12.1.4, một phương thức được khai báo hoặc kế thừa trong class được khởi chạy là **candidate `main`** khi thỏa tất cả điều kiện sau:

- Tên phương thức là **`main`** (phân biệt chữ hoa và chữ thường).
- Kiểu trả về là **`void`**.
- Quyền truy cập là **`public`**, **`protected`** hoặc **package-private** (không ghi modifier). **`private` không được chấp nhận** làm entry point.
- Có **không tham số**, hoặc có **đúng một tham số kiểu `String[]`**; dạng `String...` tương đương `String[]`.
- Có thể là phương thức **`static`** hoặc **instance**, tức không có `static`.
- Có thể khai báo `throws` như một phương thức Java thông thường.

Những điều kiện này mô tả **candidate**. Để một **instance main** thực sự khởi chạy được, JVM còn phải tạo được instance của class ban đầu. Nếu class không thể được khởi tạo bằng constructor không tham số phù hợp, việc khởi động sẽ thất bại dù chữ ký phương thức đúng.

**Bảng quyết định:**

| Yếu tố | Được chấp nhận trong Java 25 | Không hợp lệ làm entry point |
| --- | --- | --- |
| Tên | `main` | `Main`, `MAIN`, `start` |
| Kiểu trả về | `void` | `int`, `String`, `boolean`, `void[]` |
| Access | `public`, `protected`, không ghi modifier | `private` |
| Kiểu phương thức | `static` hoặc instance | Không có `main` thực thi phù hợp |
| Tham số | Không tham số, `String[]`, `String...` | `String`, `Object[]`, `int[]`, hai tham số |
| Exception | Có hoặc không có `throws` | Không có giới hạn đặc biệt chỉ vì `throws` |
| Chạy instance `main` | Class tạo được bằng no-arg constructor phù hợp | Chỉ có constructor nhận tham số hoặc constructor không tham số không thể truy cập |

**Không nhầm:** phương thức `private void main()` vẫn có thể biên dịch như một phương thức thành viên thông thường, nhưng **không được launcher chọn** làm điểm bắt đầu nếu không còn candidate phù hợp.

## 3. Mười hai dạng chính của main

Có ba mức access được launcher chấp nhận, hai lựa chọn `static`/instance và hai dạng tham số (một `String[]` hoặc không tham số):

\[
3 \times 2 \times 2 = 12
\]

| # | Khai báo `main` | Access | Static/instance | Tham số |
| ---: | --- | --- | --- | --- |
| 1 | `public static void main(String[] args)` | public | static | mảng String |
| 2 | `protected static void main(String[] args)` | protected | static | mảng String |
| 3 | `static void main(String[] args)` | package-private | static | mảng String |
| 4 | `public void main(String[] args)` | public | instance | mảng String |
| 5 | `protected void main(String[] args)` | protected | instance | mảng String |
| 6 | `void main(String[] args)` | package-private | instance | mảng String |
| 7 | `public static void main()` | public | static | không |
| 8 | `protected static void main()` | protected | static | không |
| 9 | `static void main()` | package-private | static | không |
| 10 | `public void main()` | public | instance | không |
| 11 | `protected void main()` | protected | instance | không |
| 12 | `void main()` | package-private | instance | không |

Các hàng là **những ví dụ riêng biệt**, không phải 12 phương thức cần viết đồng thời trong một class.

Khi thay `String[]` bằng `String...` cho 6 hàng có tham số, có **18 dạng viết** nếu tách hai cú pháp tham số ra để đếm. Nhưng số chữ ký Java độc lập vẫn là 12, bởi mảng `String[]` và varargs `String...` được biên dịch về cùng kiểu tham số. JLS 25 cũng ghi rõ cách đếm này.

### 3.1. String[] và String... có quan hệ gì?

Đây là hai cách viết cùng một chữ ký:

~~~java
public static void main(String[] args) {
    System.out.println(args.length);
}
~~~

~~~java
public static void main(String... args) {
    System.out.println(args.length);
}
~~~

Mỗi đoạn trên hợp lệ **khi dùng riêng**. Đặt cả hai trong cùng một class sẽ bị lỗi trùng chữ ký:

~~~java
// Không biên dịch: main(String[]) và main(String...) cùng chữ ký.
class DuplicateSignature {
    static void main(String[] args) { }
    static void main(String... args) { }
}
~~~

Bất kể dùng `String[]` hay `String...`, tham số mà launcher truyền vào là một **mảng String** chứa đối số dòng lệnh.

### 3.2. Không có main với một String đơn lẻ

`main(String value)` **không** nhận được một chuỗi do launcher tự nối đối số. Launcher chỉ nhận dạng một tham số kiểu **mảng String** hoặc không có tham số:

~~~java
// Biên dịch được, nhưng KHÔNG đủ điều kiện làm entry point:
class WrongParameter {
    static void main(String name) {
        System.out.println(name);
    }
}
~~~

Nếu chạy class trên như ứng dụng, launcher sẽ báo không tìm thấy phương thức `main` phù hợp. Mã đó vẫn có thể được gọi bằng một phương thức Java khác, nhưng không phải entry point theo launch protocol.

## 4. Ví dụ chạy được: static main với và không có args

### 4.1. Dạng truyền thống vẫn là lựa chọn tốt

Tạo file `GreetingApp.java`:

~~~java
public class GreetingApp {

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "mọi người";
        System.out.println("Xin chào " + name);
    }
}
~~~

Biên dịch/chạy bằng JDK 25:

~~~bash
javac --release 25 GreetingApp.java
java GreetingApp Mai
~~~

Kết quả:

~~~text
Xin chào Mai
~~~

`public static void main(String[] args)` tiếp tục phù hợp với các ứng dụng lớn, ví dụ lớp bootstrap của Spring Boot và các công cụ cần giao diện entry point rõ ràng. **Không coi cách viết này là legacy hoặc đã lỗi thời.**

### 4.2. Static main không tham số

Tạo file `StaticNoArgs.java`:

~~~java
class StaticNoArgs {

    static void main() {
        IO.println("Static main không có tham số");
    }
}
~~~

Chạy:

~~~bash
javac --release 25 StaticNoArgs.java
java StaticNoArgs
~~~

Không cần `public`, không cần `String[] args` và không cần `--enable-preview`. Đây là **class có khai báo tường minh**, khác với compact source file.

Nếu chạy `java StaticNoArgs mot hai`, launcher chọn `main()` và không chuyển các đối số đó thành tham số của phương thức vì chữ ký không khai báo tham số. Nếu chương trình cần đọc các đối số dòng lệnh, hãy dùng dạng `main(String[] args)`.

### 4.3. Protected static main và varargs

Tạo `ProtectedArgs.java`:

~~~java
class ProtectedArgs {

    protected static void main(String... names) {
        for (String name : names) {
            IO.println("Hello " + name);
        }
    }
}
~~~

~~~bash
javac --release 25 ProtectedArgs.java
java ProtectedArgs An Binh
~~~

Kết quả:

~~~text
Hello An
Hello Binh
~~~

Từ `protected` vẫn hợp lệ; varargs là cách viết khác của `String[]`. Không cần đặt class thành `public` để launcher của Java 25 có thể khởi chạy nó bằng tên.

## 5. Ví dụ chạy được: instance main

Instance `main` không có `static`, nên có thể dùng trực tiếp **instance field** và **instance method**. Khi chọn dạng này, launcher tạo một object trước rồi gọi `main` trên object.

### 5.1. Instance main không tham số

Tạo `InstanceHello.java`:

~~~java
class InstanceHello {
    private final String greeting = "Chào từ object";

    void main() {
        IO.println(greeting);
        printStatus();
    }

    void printStatus() {
        IO.println("main() đang chạy trên một instance");
    }
}
~~~

~~~bash
javac --release 25 InstanceHello.java
java InstanceHello
~~~

Kết quả:

~~~text
Chào từ object
main() đang chạy trên một instance
~~~

Với phương thức instance, bạn không phải biến tất cả helper thành `static` chỉ vì chúng được gọi từ `main`. Đây là lợi ích dễ thấy khi viết chương trình nhỏ hoặc demo hướng đối tượng.

### 5.2. Instance main có String[] và constructor

Tạo `InstanceArgs.java`:

~~~java
class InstanceArgs {
    private final String prefix;

    // Constructor không tham số, không private.
    InstanceArgs() {
        this.prefix = "Đối số: ";
    }

    void main(String[] args) {
        for (String arg : args) {
            IO.println(prefix + arg);
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 25 InstanceArgs.java
java InstanceArgs one two
~~~

Kết quả:

~~~text
Đối số: one
Đối số: two
~~~

Trình tự ở mức khái niệm:

~~~mermaid
sequenceDiagram
    participant U as Người chạy lệnh
    participant L as java launcher / JVM
    participant C as Class InstanceArgs
    participant O as InstanceArgs object

    U->>L: java InstanceArgs one two
    L->>C: Tìm candidate main(String[])
    L->>O: Gọi constructor không tham số
    L->>O: main(new String[]{"one", "two"})
    O-->>U: In đối số
~~~

Lưu ý đây là sơ đồ diễn giải; việc nạp, liên kết và khởi tạo class xảy ra theo quy tắc JVM/JLS.

### 5.3. Constructor ảnh hưởng thế nào?

Một candidate **static `main`** không cần tạo object. Candidate **instance `main`** yêu cầu JVM tạo instance của initial class bằng constructor không tham số có khả năng truy cập theo giao thức khởi chạy của Java 25.

Ví dụ không chạy được dưới dạng entry point:

~~~java
class MissingNoArgs {
    private final String name;

    MissingNoArgs(String name) {
        this.name = name;
    }

    void main() {
        IO.println(name);
    }
}
~~~

Class này biên dịch được, nhưng khi khởi chạy bằng `java MissingNoArgs` sẽ thất bại vì **không có constructor không tham số** để tạo object trước khi gọi `main`. Sửa bằng cách bổ sung constructor không tham số phù hợp, hoặc chuyển sang một phương thức static `main` hợp lệ nếu việc tạo object không cần thiết.

Tương tự, một constructor không tham số **private** không phải một lựa chọn an toàn cho launch protocol của Java 25. Sử dụng `public`, `protected` hoặc package-private cho constructor của instance-entry-point class.

## 6. Launcher chọn phương thức nào khi có nhiều main?

Đây là điểm dễ hiểu sai nhất khi học cú pháp Java 25.

Theo **JLS 25 `12.1.4**, launcher xét ứng viên theo **số tham số và kiểu tham số** trước:

1. Nếu có candidate `main(String[] args)` — bao gồm `main(String... args)` — chọn **dạng có một mảng String**.
2. Nếu không có dạng trên, tìm candidate `main()` **không có tham số**.
3. **Sau khi chọn**, nếu phương thức là static thì gọi trực tiếp; nếu là instance thì tạo object rồi gọi.

**Không có quy tắc “static luôn ưu tiên hơn instance”.** Ví dụ: khi class có `static main()` và `instance main(String[])`, launcher chọn **instance main(String[])` vì dạng có tham số được ưu tiên.

### 6.1. Ví dụ phân biệt thứ tự ưu tiên

Tạo `Priority.java`:

~~~java
class Priority {

    static void main() {
        IO.println("STATIC_NO_ARGS");
    }

    void main(String[] args) {
        IO.println("INSTANCE_WITH_ARGS");
        IO.println("Số đối số = " + args.length);
    }
}
~~~

Chạy:

~~~bash
javac --release 25 Priority.java
java Priority red blue
~~~

Kết quả:

~~~text
INSTANCE_WITH_ARGS
Số đối số = 2
~~~

Nếu bạn nhầm rằng launcher luôn ưu tiên phương thức static, sẽ dự đoán sai. Ví dụ trên là phép kiểm tra trực tiếp cách chọn method mới ở Java 25.

### 6.2. Hai overload static

~~~java
class BothStatic {

    static void main() {
        IO.println("Không args");
    }

    static void main(String[] args) {
        IO.println("Có args: " + args.length);
    }
}
~~~

`java BothStatic` gọi `main(String[])` và in `Có args: 0`. Sự hiện diện của hai overload không phải lỗi compile. Việc có **ít nhất một candidate** là điều kiện tìm entry point; nếu có cả hai, launcher ưu tiên `String[]`.

### 6.3. Hai overload instance

~~~java
class BothInstance {

    void main() {
        IO.println("Không args");
    }

    void main(String[] args) {
        IO.println("Có args: " + args.length);
    }
}
~~~

`java BothInstance xanh` gọi `main(String[])`, kết quả `Có args: 1`.

### 6.4. Vì sao không có static và instance main cùng chữ ký?

Java không cho phép một class khai báo hai phương thức có **cùng tên và cùng kiểu tham số** mà chỉ khác `static` hoặc kiểu trả về:

~~~java
// Không biên dịch:
class IllegalOverload {
    static void main(String[] args) { }
    void main(String[] args) { }
}
~~~

Tương tự, `String[]` và `String...` tạo cùng chữ ký. Sự lựa chọn giữa static và instance áp dụng **sau khi đã tìm được một candidate theo chữ ký**; không tồn tại hai phương thức với cùng chữ ký chỉ để launcher phân vân.

### 6.5. Bảng dự đoán hành vi

| Các phương thức có trong class | Launcher chọn | Ghi chú |
| --- | --- | --- |
| Chỉ `public static void main(String[] a)` | Chính phương thức đó | Dạng truyền thống |
| Chỉ `static void main()` | Static không tham số | Java 25 chấp nhận |
| Chỉ `void main(String[] a)` | Instance có tham số | Cần constructor không tham số |
| Chỉ `void main()` | Instance không tham số | Cần constructor không tham số |
| `static main()` + `void main(String[] a)` | **Instance có tham số** | `String[]` được ưu tiên hơn `()` |
| `static main(String[] a)` + `void main()` | **Static có tham số** | `String[]` được ưu tiên |
| `static main(String[] a)` + `static main()` | **Static có tham số** | Hai overload hợp lệ |
| `void main(String[] a)` + `void main()` | **Instance có tham số** | Hai overload hợp lệ |
| Chỉ `private static void main(String[] a)` | Không có candidate | Private bị loại |
| Chỉ `static int main(String[] a)` | Không có candidate | Sai kiểu trả về |

## 7. Compact source file và instance main là hai khái niệm riêng

Java 25 cho phép viết **compact source file**: mã nguồn gồm các khai báo field/method không nằm trong một khai báo `class` tường minh. Compiler sẽ tạo một **implicitly declared class** cho file đó.

Tạo `Welcome.java`:

~~~java
String greeting = "Xin chào";

void main(String[] args) {
    String name = args.length > 0 ? args[0] : "Java 25";
    IO.println(greeting + ", " + name + "!");
}
~~~

Chạy trực tiếp:

~~~bash
java Welcome.java Lan
~~~

Kết quả:

~~~text
Xin chào, Lan!
~~~

Hoặc biên dịch rồi chạy:

~~~bash
javac --release 25 Welcome.java
java Welcome Lan
~~~

**Đây vẫn là Java 25 chính thức, không phải script language hay dialect riêng.** Điểm khác là class được khai báo **ngầm** thay vì bạn viết `class Welcome`.

### 7.1. Những đặc điểm cần ghi nhớ

- Implicitly declared class là **final top-level class** trong **unnamed package**, thuộc unnamed module.
- Nó mặc nhiên kế thừa `Object`, không implement interface, có một constructor mặc định không tham số và không thể khai báo constructor khác theo cách bình thường.
- Các field/method viết ở cấp file trở thành thành viên của implicit class; phương thức không ghi `static` là instance method.
- Một compact source file phải có một candidate `main` có thể khởi chạy; điều này được compiler kiểm tra.
- Kiểu implicit class không có tên để tham chiếu tường minh từ mã Java khác. Tên class file do compiler lựa chọn có thể dựa vào tên file để launcher chạy, nhưng không trở thành một API để module khác import.
- Compact source file **tự động** nhập các kiểu public trong các package được `java.base` export, tương đương `import module java.base;`. Đây là đặc điểm tiện lợi, không có nghĩa mọi module JDK bên ngoài `java.base` đều được import.
- Các static method của `java.lang.IO` **không được static-import ngầm**. Viết `IO.println(...)` hoặc import static một cách tường minh.

**Không nhầm:** instance `main` cũng có thể nằm trong một **class tường minh** như `InstanceHello` ở mục 5. Muốn dùng instance `main` thì không cần chuyển file thành compact source file.

### 7.2. Dùng java.lang.IO đúng trong Java 25

`java.lang.IO` cung cấp hàm I/O cơ bản, ví dụ:

~~~java
void main() {
    String name = IO.readln("Tên của bạn: ");
    IO.println("Xin chào, " + name);
}
~~~

`java.lang.IO` có thể dùng cả trong class tường minh vì `java.lang` là package tự động import; **phương thức** `println` thì không tự động import. Vì vậy ví dụ cũ viết trần `println("Hello")` trong compact source file có thể không còn đúng ở Java 25 trừ khi có khai báo `import static` phù hợp.

### 7.3. Chuyển từ compact sang class tường minh

Khi chương trình lớn hơn, bạn có thể thêm class để biểu diễn cấu trúc rõ ràng:

Từ `Tiny.java`:

~~~java
String message = "Hello";
void main() {
    IO.println(message);
}
~~~

Chuyển sang `Tiny.java`:

~~~java
class Tiny {

    private final String message = "Hello";

    void main() {
        IO.println(message);
    }
}
~~~

Hành vi giống nhau; cách tổ chức mã rõ hơn. Khi bắt đầu dùng `package`, làm ứng dụng đa module, framework quét class và build artifact phức tạp, **class tường minh với entry point rõ ràng** thường dễ quản lý hơn.

## 8. Main được kế thừa có được chấp nhận không?

JLS 25 cho phép candidate `main` được **khai báo hoặc kế thừa** bởi initial class. Đây là chi tiết hữu ích để đọc hiểu mã, nhưng không cần cố tình dùng kế thừa như thiết kế entry point chính.

Ví dụ:

~~~java
class Parent {
    public static void main(String[] args) {
        IO.println("Được kế thừa từ Parent");
    }
}

class Child extends Parent {
}
~~~

Khi đã biên dịch, `java Child` có thể gọi candidate `main(String[])` được kế thừa từ `Parent`.

Một **default method `main()`** trong interface cũng có thể được class triển khai kế thừa:

~~~java
interface Entry {
    default void main() {
        IO.println("Default main trong interface");
    }
}

class DefaultEntry implements Entry {
}
~~~

`java DefaultEntry` có thể chạy qua instance `main()` kế thừa, miễn class khởi chạy có constructor không tham số phù hợp. Interface tự nó không thể được khởi tạo như class instance, nên cần phân biệt **candidate method** với khả năng thực thi cụ thể.

**Khuyến nghị thiết kế:** trong chương trình lớn, khai báo entry point rõ ràng trong lớp launcher dễ đọc và ít bất ngờ hơn là phụ thuộc vào `main` kế thừa từ superclass/interface.

## 9. Các trường hợp sai hoặc dễ nhầm

Một class Java có thể biên dịch dù không có entry point. **Compile thành công không đồng nghĩa launcher sẽ tìm được `main` hợp lệ**.

| Mã trong class | Compile? | Chạy làm entry point? | Lý do |
| --- | --- | --- | --- |
| `private static void main(String[] a) {}` | Có | Không | `private` không phải candidate |
| `static int main(String[] a) { return 0; }` | Có | Không | Kiểu trả về không phải `void` |
| `static void Main(String[] a) {}` | Có | Không | Java phân biệt hoa/thường |
| `static void main(String a) {}` | Có | Không | `String` không phải `String[]` |
| `void main(int[] numbers) {}` | Có | Không | Sai kiểu tham số |
| `void main(String[] a, int n) {}` | Có | Không | Có hai tham số |
| `static void main(String... a) {}` | Có | Có | Varargs là `String[]` |
| `protected void main() {}` | Có | Có, nếu tạo instance được | Access hợp lệ |
| `void main() throws Exception {}` | Có | Có, nếu tạo instance được | `throws` không loại candidate |
| `void main() {}` trong class chỉ có constructor một tham số | Có | Không | Không tạo được instance bằng no-arg constructor |
| `static main(String[])` và `instance main(String[])` trong cùng class | Không | Không | Trùng chữ ký Java |

Không nên lấy những cảnh báo “Java yêu cầu **bắt buộc** `public static void main(String[] args)`” trong tài liệu trước JDK 25 làm quy tắc hiện hành cho Java 25. Tuy vậy, chữ ký truyền thống vẫn hoàn toàn hợp lệ, hữu dụng và được nhiều build tool/framework nhận diện tốt.

## 10. Chạy chương trình với JDK 25 một cách nhất quán

Bài này dùng tính năng đã final; việc xác minh phiên bản **quan trọng hơn việc thêm preview flag**.

### 10.1. Kiểm tra JDK compiler và launcher

Linux/macOS:

~~~bash
java -version
javac -version
command -v java
command -v javac
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
Get-Command java
Get-Command javac
$env:JAVA_HOME
~~~

Dùng `java` và `javac` của **JDK 25** cho các ví dụ trong bài. Nếu CI dùng JDK 21 hoặc 17, code instance `main` hoặc compact source file chưa phải một contract có thể dùng nguyên vẹn trên những runtime đó.

### 10.2. Biên dịch và chạy một class explicit

~~~bash
javac --release 25 -d out GreetingApp.java
java -cp out GreetingApp Mai
~~~

Nếu dùng file compact:

~~~bash
java Welcome.java Lan
~~~

Hoặc:

~~~bash
javac --release 25 -d out Welcome.java
java -cp out Welcome Lan
~~~

Trong các lệnh trên:

- `--release 25` yêu cầu compiler tạo class theo ngôn ngữ và API của Java 25.
- `-d out` đặt class file vào thư mục output; thư mục đầu ra phải tồn tại hoặc được tạo theo công cụ build.
- `-cp out` tìm class đã compile ở thư mục out.
- `java Welcome.java` dùng chế độ chạy source file, compiler thực thi công đoạn biên dịch trong bộ nhớ rồi khởi chạy.
- Không cần `--enable-preview`; cũng không cần mở incubator module hoặc HotSpot experimental flag chỉ để dùng JEP 512.

### 10.3. Khi dùng Gradle, Maven, IDE

Với ứng dụng có cấu trúc tiêu chuẩn:

- Cấu hình Java toolchain hoặc JDK compiler tương ứng **25**.
- Đảm bảo runner/test JVM dùng JDK tương thích (hoặc dùng container image đúng).
- Nếu có nhiều overload `main`, không dựa vào IDE chỉ nhìn thấy ký hiệu màu xanh để đoán lựa chọn; dùng quy tắc JLS và chạy kiểm tra.
- Với các chương trình nhỏ, chạy source file trực tiếp rất thuận tiện. Với ứng dụng Spring Boot hoặc đa module, giữ class launcher rõ ràng giúp đóng gói và vận hành ổn định.
- Để hỗ trợ nhiều JDK cũ, không dùng instance `main` hoặc compact source file như một API đã tồn tại từ Java 17; chọn release target thấp hơn và cú pháp phù hợp khi đó.

**Không tự thêm `--enable-preview`** vào Maven/Gradle cho bài này: JEP 512 đã final trong Java 25. Chỉ bật preview cho các tính năng khác vẫn thực sự ở trạng thái preview trong JDK đang dùng.

## 11. Ví dụ ứng dụng CLI: từ đơn giản tới có tham số

Tình huống: viết một ứng dụng quy đổi tiền tệ minh họa **luồng command-line args**, không gọi API bên ngoài.

### 11.1. Bản một: compact source file không tham số

~~~java
// QuickCalc.java
void main() {
    double price = 120_000;
    double taxRate = 0.08;
    IO.println("Tổng = " + (price * (1 + taxRate)));
}
~~~

~~~bash
java QuickCalc.java
~~~

Ứng dụng có thể chạy ngay mà không cần một class explicit. Đây là cách tốt để làm thử một ý tưởng hoặc bài thực hành nhỏ.

### 11.2. Bản hai: instance main có String[] args

~~~java
// PriceWithTax.java
import java.util.Locale;

class PriceWithTax {

    private final double taxRate = 0.08;

    void main(String[] args) {
        if (args.length != 1) {
            IO.println("Sử dụng: java PriceWithTax <price>");
            return;
        }

        try {
            double price = Double.parseDouble(args[0]);
            if (!Double.isFinite(price) || price < 0) {
                throw new NumberFormatException("Giá trị không hợp lệ");
            }

            double total = price * (1.0 + taxRate);
            IO.println("Tổng = " + String.format(Locale.ROOT, "%.2f", total));
        } catch (NumberFormatException ex) {
            IO.println("Giá phải là số hữu hạn không âm.");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 25 PriceWithTax.java
java PriceWithTax 120000
~~~

Kết quả:

~~~text
Tổng = 129600.00
~~~

Ví dụ này cố ý không dùng preview API, incubator module, thư viện ngoài hay I/O phức tạp. Khi cần đọc tham số dòng lệnh, dạng `main(String[])` là lựa chọn tự nhiên dù là static hay instance.

### 11.3. Chuyển thành entry point theo lối ứng dụng lớn

Nếu ứng dụng phát triển thành nhiều module hoặc cần tích hợp DI/framework:

~~~java
// Application.java
public class Application {

    public static void main(String[] args) {
        // Bootstrap hệ thống ở đây.
        PriceService service = new PriceService();
        service.run(args);
    }
}
~~~

Trong ví dụ khung này, `PriceService` là lớp nghiệp vụ **tự triển khai**. Kiến trúc tách entry point khỏi nghiệp vụ vẫn hữu ích; việc Java 25 cho phép instance `main` không có nghĩa mọi ứng dụng bắt buộc chuyển sang instance entry point.

## 12. Kiểm tra lựa chọn main bằng một ma trận nhỏ

Có thể tổ chức bài thực hành thành các file Java riêng; không cố đặt tất cả class vào cùng một file public.

| Bài thử | Khai báo | Lệnh gọi | Kết quả cần quan sát |
| --- | --- | --- | --- |
| A | `public static void main(String[] args)` | `java A x y` | Nhận hai đối số |
| B | `static void main()` | `java B` | Chạy không cần args |
| C | `void main()` | `java C` | JVM tạo instance |
| D | `void main(String[] args)` | `java D x` | Instance nhận một đối số |
| E | `protected static void main(String... args)` | `java E x y` | Varargs nhận mảng String |
| F | `static main()` cùng `void main(String[])` | `java F x` | Chọn instance có String[] |
| G | `static main(String[])` cùng `void main()` | `java G` | Chọn static có String[] |
| H | `private static void main(String[])` duy nhất | `java H` | Launcher báo không có candidate |
| I | `void main()` nhưng thiếu no-arg constructor | `java I` | Khởi chạy instance thất bại |
| J | Compact file chỉ có `void main()` | `java J.java` | Chạy trực tiếp source file |

Với mỗi bài thử, ghi:

1. Mã nguồn ngắn đủ tái hiện.
2. `java -version` và `javac -version`.
3. Kết quả biên dịch, status chạy và output chính xác.
4. Lý do lựa chọn phương thức dựa trên JLS 25.
5. Khác biệt giữa lỗi compiler và lỗi launcher/runtime.

Không cần bật cờ preview cho bất kỳ bài thử nào ở đây.

## 13. Các giới hạn và quyết định thiết kế cần hiểu

### 13.1. Đây là mở rộng giao thức khởi chạy, không phải loại bỏ main cổ điển

`public static void main(String[] args)` vẫn được hỗ trợ. Các bản Java hiện đại tiếp tục sử dụng rất nhiều ứng dụng có entry point static. JEP 512 làm cho những ví dụ nhỏ dễ đọc hơn và cho phép một class chứa logic instance được khởi chạy gọn hơn.

### 13.2. Không nhầm 'candidate' với 'chạy thành công'

Một phương thức có chữ ký hợp lệ không đảm bảo chương trình chạy:

- Chọn instance method nhưng không tạo được object.
- Class không nằm trên classpath/module path.
- Java launcher dùng JDK không hỗ trợ class file đã biên dịch.
- Static initializer, constructor hoặc code trong `main` ném exception.
- Runtime thiếu dependency dù compiler đã biên dịch thành công.

Vì thế cần kiểm tra cả **compile** và **run**. Khi dùng instance main, thêm case constructor vào bộ test của ứng dụng.

### 13.3. Không nhầm class explicit và compact source file

Compact source file không khai báo tên class tường minh và không phù hợp làm API xuất khẩu giữa các package/module. Khi ứng dụng có những ranh giới package rõ ràng, nên dùng class explicit. Tuy nhiên **instance `main` trong class explicit** vẫn hoàn toàn hợp lệ và không yêu cầu dùng compact source.

### 13.4. Tính năng nào ở Java 25 cần preview?

Bản thân JEP 512 là **final**. Những khả năng khác của Java 25 có thể vẫn preview, chẳng hạn `StructuredTaskScope` hoặc primitive patterns trong `switch` (JEP 507); chúng có quy định `--enable-preview` riêng. Đừng suy từ tên “mới” rằng mọi tính năng đều yêu cầu preview.

Các tính năng final khác như `ScopedValue`, module import declarations (JEP 511), flexible constructor bodies (JEP 513), Key Derivation Function API (JEP 510) có trạng thái riêng. Khi chương trình đồng thời dùng một feature preview **khác**, phải bật preview vì feature đó, không phải vì kiểu `main` đã final.

### 13.5. Giới hạn khả năng tương thích với JDK cũ

Nếu ứng dụng cần hỗ trợ JDK cũ, hãy chọn `--release` phù hợp và tránh cú pháp chưa tồn tại trên version đó. Java 25 là môi trường tối thiểu cho JEP 512 ở trạng thái final. Khi nâng lên JDK mới hơn, kiểm tra Java Language Specification tương ứng để xác nhận giao thức khởi chạy không bị ảnh hưởng bởi các thay đổi khác; không dùng hướng dẫn từ các vòng preview trước 25 để đánh giá Java 25.

## 14. Câu hỏi tự đánh giá

1. Trong Java 25, `main` bắt buộc phải có `public` và `static` hay không? Vì sao?
2. Vì sao số dạng `main` cơ bản là 12? Nếu tách `String[]` và `String...` để đếm kiểu viết, con số là bao nhiêu?
3. `private void main()` biên dịch được nhưng vì sao không phải candidate entry point?
4. `main(String name)` khác `main(String[] names)` như thế nào trong launch protocol?
5. Nếu class có `static main()` và `void main(String[] args)`, phương thức nào được chạy?
6. Vì sao không được khai báo đồng thời `static main(String[])` và `void main(String[])` trong cùng class?
7. Khi launcher chọn instance `main`, điều kiện gì phải được đáp ứng ở constructor?
8. Compact source file có bắt buộc phải khai báo `class` không? Compiler xử lý thế nào?
9. Tại sao phải viết `IO.println(...)` thay vì `println(...)` trần trong ví dụ Java 25?
10. Instance `main` chỉ dùng được trong compact source file hay cả class tường minh?
11. Java 25 có cần `--enable-preview` để dùng `void main()` và compact source files không?
12. Vì sao `public static void main(String[] args)` vẫn hữu ích trong ứng dụng Spring Boot hoặc CLI lớn?
13. `String... args` và `String[] args` có thể overload lẫn nhau không?
14. Một method `main` được kế thừa có thể được launcher nhận dạng không? Trường hợp instance cần thêm điều kiện gì?
15. Cần xác minh những thông tin nào khi local chạy được nhưng CI báo không có `main` phù hợp?

## Tài liệu tham khảo

- [Java SE 25 JLS — `12.1.4 Invoke a main Method](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html): định nghĩa candidate, thứ tự lựa chọn, tạo instance và kế thừa main.
- [Oracle Java 25 — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): ví dụ chương trình, `IO`, chạy file Java nguồn và cách phát triển thành class tường minh.
- [OpenJDK JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512): đặc tả mục tiêu và trạng thái final trong Java 25.
- [Oracle Java 25 — Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): xác nhận JEP 512 final và những thay đổi đối với `java.lang.IO`.
- [Oracle JDK 25 — java Launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp chạy class/module/source file.
- [Oracle JDK 25 — javac Compiler](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): tùy chọn `--release` và biên dịch source Java 25.

