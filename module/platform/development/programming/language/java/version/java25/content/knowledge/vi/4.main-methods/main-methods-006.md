# Điều kiện khởi tạo đối tượng khi trình chạy gọi instance main

> **Chương:** Hàm main  
> **Học phần:** `JAVA_VERSION_JAVA25` — tìm hiểu các tính năng Java 25 còn áp dụng trong Java hiện đại, bao gồm compact source files, module import, flexible constructor bodies và ScopedValue; học phần cũng đề cập KDF API, AOT cache, JFR và đánh giá nâng cấp JDK.  
> **Trọng tâm bài:** Trình chạy Java 25 tạo đối tượng như thế nào khi chọn một `main` **không `static`**, điều kiện của lớp và constructor, thứ tự khởi tạo, lỗi trước khi vào `main` và cách kiểm chứng chính xác.

## 1. Từ static main sang instance main trong Java 25

Trước đây, mẫu đầu vào quen thuộc của ứng dụng Java là `public static void main(String[] args)`. Từ **Java 25**, JEP 512 (*Compact Source Files and Instance Main Methods*) trở thành tính năng chính thức; bạn có thể viết `void main()` hoặc `void main(String[] args)` mà **không cần `static`**. Điều này áp dụng cho cả một lớp khai báo tường minh lẫn compact source file. Những cú pháp này **không còn là preview** và không cần `--enable-preview` với JDK 25.

Ví dụ lớp thường (`Welcome.java`):

```java
class Welcome {
    private final String greeting = "Xin chào từ Java 25";

    void main() {
        System.out.println(greeting);
    }
}
```

Chạy:

```bash
java --version
java Welcome.java
```

Kết quả mong đợi:

```text
Xin chào từ Java 25
```

Bạn không thấy `new Welcome()` trong code, nhưng trình chạy phải có đối tượng `Welcome` để gọi phương thức `main()` **không `static`** và truy cập `greeting`. Nếu dùng `static main`, bước tạo đối tượng này không cần thực hiện.

**Câu hỏi trọng tâm:** chương trình sẽ ra sao nếu lớp chỉ có constructor nhận tham số, constructor ném ngoại lệ, lớp `abstract`, hoặc cả `static main(String[])` lẫn instance `main()`? Trả lời các câu hỏi đó đòi hỏi hiểu **quy tắc chọn phương thức trước, khởi tạo đối tượng sau**.

### Phân biệt ba khái niệm dễ nhầm

| Khái niệm | Khi xảy ra | Có phải `new` một đối tượng? |
|---|---|---|
| **Nạp/liên kết lớp** (*loading/linking*) | Đưa class vào JVM, xác minh và chuẩn bị metadata/bytecode | Không nhất thiết |
| **Khởi tạo lớp** (*class initialization*) | Chạy static field initializers, `static { ... }`, khởi tạo lớp cha theo quy tắc JVM | Không phải tạo instance của lớp đích |
| **Khởi tạo đối tượng** (*instance creation/initialization*) | Cấp phát instance, gọi constructor cùng phần khởi tạo instance tương ứng | Có |

Với instance `main`, cả **khởi tạo lớp** và **tạo instance** đều có thể diễn ra trước khi thân `main` chạy. Với `static main`, JVM vẫn khởi tạo lớp trước khi gọi phương thức `static`, nhưng không phải tạo một instance của lớp khởi chạy.

## 2. Java 25 nhận diện phương thức main nào?

Theo **Java Language Specification (JLS) Java SE 25, §12.1.4**, một phương thức `main` của lớp khởi chạy là ứng viên nếu:

- Tên là `main`, kiểu trả về là **`void`**.
- Có **không tham số** hoặc đúng **một tham số kiểu `String[]`** (`String...` tương đương với `String[]`).
- Có mức truy cập `public`, `protected` hoặc package-private (không ghi modifier truy cập).
- Có thể là **`static`** hoặc **instance**; được khai báo trong lớp khởi chạy hoặc được kế thừa theo quy tắc thành viên Java.

`private void main()` **không** phải ứng viên khởi chạy. `int main()`, `void main(int)` hoặc `void main(Object[])` không phải ứng viên hợp lệ. `main` có thể khai báo `throws` như phương thức Java thông thường.

| Khai báo phương thức trong Java 25 | Là main ứng viên? | Cần tạo instance nếu được chọn? |
|---|---|---|
| `public static void main(String[] args)` | Có | Không |
| `static void main()` | Có | Không |
| `void main()` | Có | **Có** |
| `protected void main(String... args)` | Có | **Có** |
| `public void main(String[] args)` | Có | **Có** |
| `private static void main(String[] args)` | **Không** | Không áp dụng |
| `private void main()` | **Không** | Không áp dụng |
| `static int main()` | **Không** | Không áp dụng |
| `void main(Object[] args)` | **Không** | Không áp dụng |

Việc một lớp có **nhiều ứng viên** không tự gây lỗi biên dịch. Java 25 có quy tắc chọn cụ thể, không chọn ngẫu nhiên và cũng không tự ưu tiên `static` hơn instance.

### Quy tắc ưu tiên của launcher

**Ưu tiên một:** chọn `main(String[] args)` hoặc `main(String... args)` nếu có ứng viên.

**Ưu tiên hai:** nếu không có ứng viên nhận `String[]`, chọn `main()` không tham số.

Trong mỗi nhóm, ứng viên có thể là `static` hoặc instance; kiểu này quyết định có tạo đối tượng hay không.

Ví dụ (`PickMain.java`):

```java
class PickMain {
    PickMain() {
        System.out.println("Đã gọi constructor");
    }

    // Instance, nhưng không được chọn vì có ứng viên String[].
    void main() {
        System.out.println("Instance main()");
    }

    // Static có String[]: được chọn trước.
    static void main(String[] args) {
        System.out.println("Static main(String[])");
    }
}
```

Chạy `java PickMain.java` sẽ in:

```text
Static main(String[])
```

**Constructor không chạy** vì phương thức được chọn là `static`. Đây là ví dụ quan trọng: chỉ nhìn thấy một instance `main()` trong source **không đủ** để kết luận launcher sẽ tạo đối tượng.

Ngược lại:

```java
class SelectInstance {
    static void main() {
        System.out.println("Static no-arg main");
    }

    void main(String[] args) {
        System.out.println("Instance main(String[]): " + args.length);
    }
}
```

Chạy `java SelectInstance.java a b` chọn **instance** `main(String[])`, vì **chữ ký có `String[]` ưu tiên hơn `main()`**, dù cái sau là `static`.

## 3. Điều kiện cốt lõi: tạo được instance của lớp khởi chạy

Sau khi chọn **instance main**, JLS mô tả việc tạo instance **như khi đánh giá biểu thức tạo đối tượng không đủ định danh với không tham số**, về mặt logic tương đương:

```java
new TenLopKhoiChay();
```

Sau đó gọi phương thức `main` trên instance vừa tạo. Đây là cách diễn đạt về **ngữ nghĩa**, không khẳng định launcher sinh đúng dòng mã Java như ví dụ hoặc sử dụng một API reflection cụ thể.

Từ đó rút ra các điều kiện thực tế:

1. **Lớp khởi chạy phải tạo được instance.** Lớp `abstract` không thể trực tiếp được khởi tạo; interface không phải một lớp có thể gọi `new` theo cách này.
2. **Phải có đường xây dựng không tham số có thể dùng.** Có thể là **default constructor** do trình biên dịch sinh (khi lớp không khai báo constructor), hoặc constructor không tham số được khai báo tường minh. Constructor chỉ nhận tham số không phù hợp vì launcher không có cách tự truyền dependency/giá trị tùy ý.
3. **Các bước khởi tạo phải hoàn tất bình thường.** Nếu static initializer, instance field initializer, superclass constructor hoặc constructor của lớp đích ném lỗi, `main` không được thực thi.
4. **Việc tạo đối tượng phải hợp lệ với quy tắc Java.** Trường hợp inner class không `static` cần enclosing instance, lớp không thể xây dựng, hoặc cấu hình truy cập/binary không hợp lệ có thể khiến việc khởi chạy thất bại.
5. **Phương thức được chọn thật sự là instance.** Nếu có ứng viên static `main(String[])` được ưu tiên, có thể không cần constructor của lớp khởi chạy.

**Khuyến nghị về khả năng chuyển phiên bản:** với **lớp khai báo tường minh**, hãy có constructor không tham số **không `private`** và một lớp top-level hoặc nested `static` có thể khởi tạo khi thiết kế instance main. Tránh dựa vào chi tiết xử lý `private` constructor riêng của một JDK hoặc launcher vì các bản JDK sau có thể hành xử khác. Mục tiêu là chương trình ổn định, dễ đọc, dễ kiểm thử.

### Bảng quyết định

| Đặc điểm của lớp khởi chạy | Khởi chạy instance `main` | Giải thích |
|---|---|---|
| Lớp thường, không khai báo constructor | Thông thường **thành công** | Java sinh default constructor không tham số nếu hợp lệ |
| Lớp thường có `public App()` | **Thành công** nếu constructor hoàn tất | Launcher có đường tạo instance không tham số |
| Lớp thường có `App(String name)` nhưng không có `App()` | **Thất bại khi khởi chạy instance main** | Không có constructor phù hợp để gọi với 0 đối số |
| Lớp thường có `App()` nhưng constructor `throw` | **Thất bại trước khi vào main** | Constructor không hoàn thành |
| Lớp `abstract` chỉ có instance `main` | **Thất bại nếu chọn lớp đó làm initial class** | Không tạo trực tiếp được abstract class |
| `static main(String[])` được chọn | Không cần tạo instance | Có thể chạy dù không có constructor không tham số |
| Compact source file với instance `void main()` | **Có constructor mặc định** | Compiler tạo implicitly declared class có default no-arg constructor |
| `private void main()` là phương thức duy nhất | **Không có main ứng viên** | Không vượt qua bước lựa chọn phương thức |

Một số ví dụ lỗi trình chạy có thể báo các thông điệp khác nhau theo vendor/patch version hoặc cách chạy source/class. **Đặc tả Java 25 quy định kết quả khởi chạy thất bại khi không tạo được instance, nhưng không chuẩn hóa từng chuỗi thông báo lỗi của launcher.**

## 4. Lớp thường không khai báo constructor: điều gì xảy ra?

Tạo file `SimpleEntry.java`:

```java
class SimpleEntry {
    String prefix = "Khởi tạo xong";

    void main() {
        System.out.println(prefix);
    }
}
```

Không có constructor do lập trình viên viết. Compiler sinh một **default constructor** không tham số theo quy tắc Java, nên launcher có thể tạo instance của `SimpleEntry` rồi gọi `main`.

Thử:

```bash
java SimpleEntry.java
```

Kỳ vọng:

```text
Khởi tạo xong
```

Nếu biên dịch riêng:

```bash
javac --release 25 SimpleEntry.java
java SimpleEntry
javap -p SimpleEntry
```

Trong kết quả `javap` thường có một constructor dạng `SimpleEntry();`, do Java sinh để tạo instance. `javap` giúp kiểm chứng bytecode; nó không thay thế phân tích quy tắc mặc định của JLS. Không cần `public` cho constructor của ví dụ trong unnamed package khi chạy bằng launcher phù hợp.

### Khi superclass không có constructor không tham số

**Default constructor của lớp con không bảo đảm luôn biên dịch được.** Nếu superclass chỉ có constructor bắt buộc tham số, một lớp con không khai báo constructor hợp lệ có thể bị lỗi ngay lúc biên dịch:

```java
class BaseService {
    BaseService(String serviceName) {}
}

class NeedsBase extends BaseService {
    // Không khai báo constructor; default constructor cố gọi super()
    void main() {
        System.out.println("Không thể biên dịch như hiện tại");
    }
}
```

Ở đây lỗi xảy ra tại **compile time**, vì không có `BaseService()` để default constructor gọi. Muốn dùng instance main, bạn cần một constructor của lớp đích tự gọi `super(...)` với dữ liệu hợp lệ, đồng thời bảo đảm **constructor lớp đích không tham số** có thể được launcher sử dụng:

```java
class BaseService {
    BaseService(String serviceName) {
        System.out.println("BaseService: " + serviceName);
    }
}

class ValidEntry extends BaseService {
    ValidEntry() {
        super("inventory");
    }

    void main() {
        System.out.println("Đã vào main");
    }
}
```

Biên dịch rồi chạy **lớp đích** (vì file ví dụ chứa cả `BaseService` và `ValidEntry`):

```bash
javac --release 25 ValidEntry.java
java ValidEntry
```

Kết quả mong đợi:

```text
BaseService: inventory
Đã vào main
```

Ví dụ dùng hai file riêng hoặc đoạn mã trình bày độc lập; **không** đặt hai lần định nghĩa `BaseService` trong cùng một source file của bài thực hành.

## 5. Vì sao constructor chỉ nhận tham số không dùng được?

Ví dụ `RequiresConfiguration.java`:

```java
class RequiresConfiguration {
    private final String configuration;

    RequiresConfiguration(String configuration) {
        this.configuration = configuration;
    }

    void main() {
        System.out.println(configuration);
    }
}
```

Class này **biên dịch được** theo ngôn ngữ Java 25:

```bash
javac --release 25 RequiresConfiguration.java
```

Nhưng chạy:

```bash
java RequiresConfiguration
```

sẽ thất bại khi launcher tìm cách tạo instance để gọi `void main()`: constructor của lớp đòi `String`, trong khi quy tắc khởi chạy không truyền tham số nào vào constructor. **Đối số command line** (nếu có) dành cho `main(String[])`, không được tự động sử dụng để gọi constructor của lớp khởi chạy.

### Cách sửa đúng mục đích

Nếu cấu hình có mặc định hợp lệ, thêm constructor không tham số và chuyển tiếp:

```java
class RequiresConfiguration {
    private final String configuration;

    RequiresConfiguration() {
        this("default-profile");
    }

    RequiresConfiguration(String configuration) {
        this.configuration = configuration;
    }

    void main() {
        System.out.println(configuration);
    }
}
```

Chạy `java RequiresConfiguration` sẽ in `default-profile`.

Nếu cấu hình **bắt buộc phải nhận từ command line**, hãy nhận nó trong `main(String[])`, sau đó tạo **đối tượng nghiệp vụ khác** qua constructor có tham số:

```java
class CliEntry {
    void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Cần truyền tên môi trường: dev hoặc production");
        }

        ServiceRunner runner = new ServiceRunner(args[0]);
        runner.start();
    }
}

class ServiceRunner {
    private final String profile;

    ServiceRunner(String profile) {
        this.profile = profile;
    }

    void start() {
        System.out.println("Khởi chạy profile: " + profile);
    }
}
```

Đoạn này dùng `CliEntry` có **default constructor** để launcher tạo entry-point; `ServiceRunner` dùng constructor một tham số do `main` chủ động gọi. Compile và chạy dạng class để không phụ thuộc quy tắc chọn lớp đầu tiên của source-file launcher:

```bash
javac --release 25 CliEntry.java
java CliEntry production
```

Kỳ vọng: `Khởi chạy profile: production`.

**Không tự xây framework dependency injection bên trong constructor của class entry-point** chỉ để thỏa điều kiện launcher. Với ứng dụng lớn, entry-point có thể nhỏ gọn, còn cấu hình/kiểm tra/khởi tạo service được đặt ở lớp nghiệp vụ thích hợp.

## 6. Thứ tự khởi tạo: static initializer → instance initializer → constructor → main

Lớp khởi chạy phải được **khởi tạo** trước khi invocation `main` xảy ra. Khi cần một instance, Java còn thực hiện initialization của object theo quy tắc thừa kế/constructor. Bằng ví dụ sau, có thể quan sát thứ tự mà không cần công cụ đặc biệt.

File `InitializationOrder.java`:

```java
class InitializationOrder {
    static {
        System.out.println("1. static initializer");
    }

    private final String text = initializeField();

    {
        System.out.println("3. instance initializer");
    }

    InitializationOrder() {
        System.out.println("4. constructor");
    }

    private String initializeField() {
        System.out.println("2. instance field initializer");
        return "ready";
    }

    void main() {
        System.out.println("5. instance main: " + text);
    }
}
```

Lệnh:

```bash
java InitializationOrder.java
```

Kết quả dự kiến:

```text
1. static initializer
2. instance field initializer
3. instance initializer
4. constructor
5. instance main: ready
```

Đây là thứ tự trong ví dụ có **superclass trực tiếp là `Object`** và các bước khởi tạo được viết theo thứ tự như trên. Với lớp có superclass tùy chỉnh, `super(...)` và các bước khởi tạo superclass diễn ra trước khi phần khởi tạo instance của lớp con hoàn tất; thứ tự cụ thể giữa các field/initializer blocks tuân theo source code và quy tắc JLS.

### So sánh trường hợp static main

File `StaticEntry.java`:

```java
class StaticEntry {
    static {
        System.out.println("1. static initializer");
    }

    {
        System.out.println("KHÔNG chạy instance initializer");
    }

    StaticEntry() {
        System.out.println("KHÔNG gọi constructor");
    }

    static void main() {
        System.out.println("2. static main");
    }
}
```

Kết quả `java StaticEntry.java`:

```text
1. static initializer
2. static main
```

Dấu hiệu dễ kiểm tra: `static main()` đã được Java 25 chấp nhận **không cần tham số**. Đừng lẫn “`main()` không có đối số” với “`main()` là instance”: chỉ khi **không có từ khóa `static`** thì phương thức mới cần receiver.

### Ngoại lệ ở constructor và initializer

```java
class BrokenConstructor {
    BrokenConstructor() {
        throw new IllegalStateException("Không kết nối được cấu hình");
    }

    void main() {
        System.out.println("Dòng này không được in");
    }
}
```

`javac --release 25 BrokenConstructor.java` có thể thành công; khởi chạy `java BrokenConstructor` thất bại vì **constructor ném exception**, nên Java chưa bao giờ gọi thân instance `main`. Ngược lại, nếu static initializer ném lỗi thì lỗi có thể xuất hiện **trước cả bước tạo instance**.

Phân biệt khi chẩn đoán:

| Giai đoạn lỗi | Triệu chứng thường thấy | Cần kiểm tra |
|---|---|---|
| Class loading/linking | Class không tìm thấy hoặc lỗi liên kết bytecode | Classpath/module-path, dependency, classfile target |
| Class initialization | `ExceptionInInitializerError` hoặc lỗi khởi tạo kiểu liên quan | Static field initializer, `static {}`, superclass |
| Instance creation | Không có no-arg constructor, không thể instantiate | Khai báo class, constructors và superclass |
| Instance initialization / constructor | Exception từ initializer, `super(...)`, constructor | Stack trace từ đường tạo instance |
| Method execution | Exception trong chính `main` | Logic bên trong main và các hàm được gọi |

Tên và định dạng lỗi launcher in ra có thể khác nhau giữa các bản JDK; phân biệt **giai đoạn thất bại** dựa trên stack trace/vị trí throw sẽ chính xác hơn việc phụ thuộc một chuỗi thông báo cụ thể.

## 7. Compact source file: tại sao không cần tự viết constructor?

Một **compact source file** chứa các thành viên ở cấp file mà không khai báo `class`. Java 25 ngầm tạo một lớp top-level, `final`, thuộc **unnamed package**, kế thừa `Object`, có **default constructor không tham số** và có các thành viên được viết trong file.

File `Greeting.java`:

```java
String greeting = "Xin chào";

void main() {
    IO.println(greeting);
}
```

Chạy:

```bash
java Greeting.java
```

Kết quả:

```text
Xin chào
```

Mặc dù không viết `class Greeting`, trường `greeting` và `void main()` vẫn là **thành viên của lớp được khai báo ngầm**. Launcher tạo đối tượng thuộc lớp đó bằng default constructor rồi gọi instance main.

Có thể biên dịch trước:

```bash
javac --release 25 Greeting.java
javap -p Greeting
java Greeting
```

Trong bản JDK 25 thông thường, `javap` hiển thị một class tương ứng với file `Greeting.java`, constructor không tham số và `void main();`. **Tên lớp trong bytecode do host/compiler xác định**; không dùng nó như một public API mà code ở package có tên cố gắng import hay tham chiếu trực tiếp.

### Giới hạn đặc biệt của lớp khai báo ngầm

- **Không được tự khai báo constructor.** Lớp từ compact source file có đúng default constructor, không có constructor tùy biến.
- **Không được viết `extends`/`implements` cho lớp ngầm.** Lớp ngầm `final`, extends `Object` và không có direct superinterfaces.
- **Không được tham chiếu lớp ngầm theo tên từ code nguồn thông thường.** Dùng `this`, các instance fields/methods và các nested classes khi cần; không giả định tên file là tên kiểu có thể dùng trong source.
- **Phải có main ứng viên hợp lệ.** Nếu chỉ khai báo helper methods và không có launchable `main`, compact compilation unit bị lỗi theo quy tắc Java 25.
- **Không được khai báo instance initializer, static initializer hoặc constructor trực tiếp ở cấp file** như thể đó là thân lớp thường; hãy chuyển sang lớp tường minh nếu cần các cấu trúc này.
- **Được dùng tham số String[]** nếu muốn nhận đối số CLI:

```java
// File ArgsDemo.java
void main(String[] args) {
    IO.println("Số đối số: " + args.length);
}
```

Chạy:

```bash
java ArgsDemo.java alpha beta
```

Kỳ vọng: `Số đối số: 2`.

`java.lang.IO` cung cấp `IO.println(...)`; với Java 25 bạn **phải viết `IO.println`** hoặc tự nhập tĩnh hàm thích hợp. Một số ví dụ preview Java 21–24 dùng `println(...)` không định danh nhờ cơ chế import cũ **không còn là cách viết đúng để dạy Java 25 final**. Đây là ví dụ về việc loại bỏ hướng dẫn lỗi thời.

### Lựa chọn compact hay lớp thường?

Compact source file hữu ích cho học tập, script nhỏ, ví dụ CLI độc lập và thử API. Nếu cần constructor tùy biến, package đặt tên, dependency injection, API có thể tái sử dụng, class hierarchy hoặc cấu trúc module của sản phẩm, hãy dùng **lớp tường minh**. Việc giữ cấu trúc application rõ ràng quan trọng hơn số dòng ít đi.

## 8. Kế thừa main: đối tượng được tạo thuộc lớp nào?

JLS Java 25 cho phép một lớp khởi chạy có **candidate main được kế thừa**. Điều đó **không** có nghĩa launcher tạo đối tượng của lớp khai báo method; nếu main được chọn là instance, launcher tạo đối tượng của **lớp khởi chạy**.

Ví dụ `InheritedEntry.java`:

```java
class BaseEntry {
    BaseEntry() {
        System.out.println("BaseEntry constructor");
    }

    void main() {
        System.out.println("main được kế thừa");
        System.out.println("Runtime class: " + getClass().getSimpleName());
    }
}

class InheritedEntry extends BaseEntry {
    // Không khai báo main: kế thừa BaseEntry.main().
}
```

Biên dịch và chạy rõ tên lớp:

```bash
javac --release 25 InheritedEntry.java
java InheritedEntry
```

Kỳ vọng:

```text
BaseEntry constructor
main được kế thừa
Runtime class: InheritedEntry
```

Launcher tạo **`InheritedEntry`** (theo `new InheritedEntry()` về ngữ nghĩa); việc thực thi constructor lớp cha là một phần của quá trình tạo đối tượng lớp con. Vì vậy nếu lớp con chỉ có constructor nhận tham số, hoặc abstract, việc khởi chạy instance main vẫn có thể thất bại **dù method nằm ở superclass và superclass có constructor rỗng**.

### Instance main kế thừa từ interface default method

Một interface có thể khai báo `default void main()` làm ứng viên main mà class triển khai được kế thừa:

```java
interface GreeterEntry {
    default void main() {
        System.out.println("Hello from default main");
    }
}

class DefaultMainApp implements GreeterEntry {
}
```

Dùng class launch:

```bash
javac --release 25 DefaultMainApp.java
java DefaultMainApp
```

Kỳ vọng: `Hello from default main`.

Đây là một khả năng của Java 25, nhưng **không bắt buộc** chọn thiết kế này trong mọi sản phẩm. Nó có thể gây khó đọc nếu điểm bắt đầu ứng dụng “ẩn” trong nhiều tầng kế thừa; đối với dự án lớn, entry-point tường minh thường dễ bảo trì hơn.

## 9. Các trường hợp không nên dựa vào launcher để khởi tạo

Một số lớp có đặc điểm khiến `new InitialClass()` không phù hợp:

| Trường hợp | Vì sao không dùng làm instance entry-point mặc định? | Cách phù hợp |
|---|---|---|
| `abstract class` có `void main()` | Không thể tạo trực tiếp instance của abstract class | Dùng lớp concrete có constructor không tham số hợp lệ |
| Non-static inner class | Cần enclosing instance (`outer.new Inner()`), không khớp lời gọi tạo không tham số, không đủ định danh | Đặt entry-point ở top-level hoặc `static` nested class |
| Constructor bắt buộc tham số | Launcher không tự resolve dependency | Dùng no-arg entry-point rồi khởi tạo service đúng dữ liệu trong main |
| Constructor có side effect thất bại | Main chưa chạy mà khởi tạo đã hỏng | Giảm tác dụng phụ trong constructor, tách I/O/khởi động trong service phù hợp |
| Chỉ có private `main()` | Không phải candidate main | Dùng package-private/protected/public theo quy tắc Java 25 |
| Class có static `main(String[])` ưu tiên | Không vào instance main còn lại | Kiểm tra ứng viên được chọn, dùng tên khác cho helper |
| Record/enum với mô hình khởi tạo đặc biệt | Không thiết kế để launcher tự cung cấp giá trị constructor tùy ý | Dùng lớp entry-point riêng để tạo giá trị record/enum và chạy nghiệp vụ |
| Ứng dụng Spring/DI lớn | Lifecycle và dependency graph do framework kiểm soát | Giữ entry-point nhỏ, để framework tạo bean và quản lý lifecycle |

**Không mặc định sửa class bằng cách thêm constructor rỗng rồi để object ở trạng thái thiếu dữ liệu hợp lệ.** Nếu lớp cần `repository`, `credentials` hoặc config bắt buộc, một no-arg constructor “trống” có thể chỉ đẩy lỗi từ startup sang runtime. Hãy tách lớp khởi chạy khỏi đối tượng nghiệp vụ cần dependency injection.

### Cẩn trọng với private constructor

Java 25/JEP 512 đặc tả việc tạo một instance qua ngữ nghĩa biểu thức tạo lớp không tham số. Với **lớp có constructor riêng tư**, hành vi chi tiết giữa các launcher/JDK patch và các bản Java sau có thể khác; đã có ví dụ thực nghiệm về sự khác nhau giữa JDK 25 và JDK 27. Để giữ tài liệu và source code có tính áp dụng lâu dài, **không dựa vào khả năng gọi constructor `private` của launcher**. Dùng lớp thường với constructor không tham số có quyền phù hợp hoặc `static main` khi không cần instance.

Việc thay `private` constructor thành `public` chỉ để “khởi chạy được” có thể phá ràng buộc thiết kế của singleton/factory; hãy cân nhắc dùng một entry-point riêng.

## 10. Kiểm chứng bằng `java`, `javac` và `javap` trên JDK 25

Bài thực hành tập trung vào Java 25 **final**, nên bạn chỉ cần JDK 25 đầy đủ. Đầu tiên xác nhận công cụ thực sự dùng cùng version:

```bash
java --version
javac --version
javap --version
```

Đầu ra phải cho thấy Java 25 và `javac` 25. Khi có nhiều JDK, IDE và CLI có thể dùng bản khác nhau; kết quả dưới đây chỉ đáng tin nếu source launcher, compiler và JVM chạy class đều là JDK 25.

### 10.1. Thử hai cách chạy độc lập

Với `SimpleEntry.java` là lớp thường có instance main:

```bash
# Cách A: source-file launch (biên dịch trong quá trình chạy)
java SimpleEntry.java

# Cách B: compile trước, launch class
javac --release 25 SimpleEntry.java
java SimpleEntry

# Kiểm tra constructor mà compiler tạo
javap -p SimpleEntry
```

Với file compact source `Greeting.java`, cũng chạy được theo hai cách:

```bash
java Greeting.java
javac --release 25 Greeting.java
java Greeting
javap -p Greeting
```

Trong project có nhiều class/package, ưu tiên `javac`/Maven/Gradle rồi chạy **tên fully qualified class** được chọn làm entry-point. Source-file launcher có quy tắc lựa chọn lớp khởi chạy riêng; đừng nhầm tên file nguồn với khả năng tự động gọi một class khác bất kỳ bên trong file.

### 10.2. Bài test xác nhận constructor chỉ khi chọn instance main

File `ConstructorProbe.java`:

```java
class ConstructorProbe {
    static int instances;

    ConstructorProbe() {
        instances++;
        System.out.println("constructing instance " + instances);
    }

    void main(String[] args) {
        System.out.println("instance main, args=" + args.length);
    }

    static void main() {
        System.out.println("static no-arg main");
    }
}
```

Lệnh `java ConstructorProbe.java first second` mong đợi:

```text
constructing instance 1
instance main, args=2
```

Dù có `static main()` không tham số, Java 25 vẫn chọn instance `main(String[])` và do đó khởi tạo đối tượng. Có thể sửa chữ ký `void main(String[] args)` thành `void main(int number)` (không còn ứng viên) để quan sát chương trình chuyển sang chọn **`static main()`** và không gọi constructor.

Ví dụ khác (`StaticPreferred.java`):

```java
class StaticPreferred {
    StaticPreferred(String required) {
        throw new AssertionError("Không được tạo đối tượng");
    }

    static void main(String[] args) {
        System.out.println("static main selected");
    }

    void main() {
        System.out.println("instance main not selected");
    }
}
```

Chạy `java StaticPreferred.java` vẫn thành công, dù **không có constructor không tham số**: launcher chọn static `main(String[])`, nên không tạo instance. Đó là lý do cần kiểm tra **phương thức được chọn trước** khi kết luận thiếu constructor sẽ khiến chương trình lỗi.

### 10.3. Lệnh nào không cần `--enable-preview`?

```bash
javac --release 25 SimpleEntry.java
java SimpleEntry

javac --release 25 Greeting.java
java Greeting
```

Cả compact source file và instance main được **final** trong Java 25. Không cần thêm `--enable-preview` để kích hoạt JEP 512. Nếu IDE yêu cầu preview mới hiểu `void main()` trong Java 25, hãy kiểm tra parser/compiler settings và phiên bản IDE; không thiết lập preview một cách mặc định chỉ để khắc phục editor cũ.

## 11. Chẩn đoán lỗi: nguồn sai nằm ở đâu?

Một lớp có thể không chạy vì **main không hợp lệ**, **main hợp lệ nhưng không thể tạo instance**, hoặc **khởi tạo thành công nhưng logic main lỗi**. Đừng gộp chúng thành “Java không tìm thấy main”.

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Launcher báo không tìm được `main` hợp lệ | Chỉ có `private main`, sai kiểu trả về, tham số không đúng | Dùng `void main()` hoặc `void main(String[])`, access hợp lệ |
| Compile thành công nhưng launcher báo không có constructor không tham số | Có instance main và class chỉ có constructor nhận đối số | Bổ sung no-arg entry-point hợp lệ hoặc dùng static main |
| `ExceptionInInitializerError` | Static initializer hoặc một phần class initialization thất bại | Xem nguyên nhân gốc của static initialization |
| Exception trước dòng đầu tiên trong `main` | Instance initializer, superclass constructor hoặc constructor throw | Đặt log/breakpoint tại constructor; xem stack trace |
| Class `abstract` được chọn làm entry-point instance main | Không thể tạo instance của initial class | Chọn lớp concrete có constructor phù hợp |
| Class inner không `static` được đưa làm entry-point | Không có enclosing instance phù hợp với cách launcher tạo object | Dùng top-level hoặc nested `static` class |
| Có `void main()` nhưng không thấy constructor chạy | Launcher chọn một static `main(String[])` khác | Đối chiếu các candidate theo thứ tự chọn của JLS |
| Có `static main()` và `void main(String[])` | Launcher chọn instance method có tham số | Kiểm tra constructor, không dựa vào ưu tiên static |
| `UnsupportedClassVersionError` | JVM thực chạy thấp hơn target bytecode | Kiểm tra `java --version`, bytecode, runtime image |
| IDE chạy được nhưng Gradle/Maven không | JVM/toolchain, plugin hoặc IDE launcher khác nhau | Chọn JDK, toolchain và release rõ ràng |
| Cần truyền config vào constructor của entry-point | Launcher không tự truyền CLI args vào constructor | Nhận args trong main và khởi tạo service riêng |

### Thao tác phân biệt ba giai đoạn

1. **Compile:** chạy `javac --release 25 File.java`. Nếu lỗi constructor/default superclass xảy ra ở đây, sửa lỗi khai báo/chuỗi constructor trước.
2. **Launch:** chạy `java TenLop` sau khi compile. Nếu lỗi **không tạo được instance**, kiểm tra signature main thực được chọn và no-arg constructor.
3. **Execute:** khi đã in được dòng đầu main, lỗi còn lại thuộc logic main hoặc code nó gọi. Dùng debugger, stack trace và test cụ thể.

Không cần bật reflection access với `--add-opens` hoặc dùng `Unsafe.allocateInstance()` để “vượt qua” điều kiện entry-point. Những cách đó không phải giao thức khởi chạy thông thường của Java 25, có thể phá invariant constructor và làm khó bảo trì.

### Mối liên hệ với flexible constructor bodies

Java 25 cũng hoàn tất **Flexible Constructor Bodies** (JEP 513). Tính năng này cho phép một số câu lệnh kiểm tra trước khi gọi `super(...)` hoặc `this(...)` theo các ràng buộc ngôn ngữ, nhưng **không** thay đổi quy tắc launcher của instance main: vẫn cần tạo được lớp khởi chạy bằng con đường constructor không tham số.

Ví dụ:

```java
class CheckedEntry {
    CheckedEntry() {
        String value = System.getProperty("app.mode", "demo");
        if (value.isBlank()) {
            throw new IllegalArgumentException("app.mode không hợp lệ");
        }
        super();
        System.out.println("constructor: " + value);
    }

    void main() {
        System.out.println("instance main");
    }
}
```

Ở Java 25, khối kiểm tra trước `super()` có thể hợp lệ theo JEP 513 vì chưa truy cập `this`/instance ở pha chưa được khởi tạo. Nếu điều kiện ném lỗi, `main` không được gọi. **Flexible constructor bodies** chỉ làm code constructor linh hoạt hơn; nó không cho launcher truyền dependency vào constructor một tham số.

## 12. Thiết kế điểm vào chương trình cho ứng dụng thực

Instance `main` giúp chương trình nhỏ dễ đọc, nhưng không nhất thiết thay thế mọi entry-point công nghiệp. Quyết định nên dựa vào lifecycle và cơ chế cấu hình:

| Trường hợp | Thiết kế nên cân nhắc | Lý do |
|---|---|---|
| Bài học Java đầu tiên, ví dụ CLI một file | Compact `void main()` | Constructor mặc định, code ngắn, final trong Java 25 |
| Công cụ CLI nhỏ có trạng thái instance | Lớp tường minh + no-arg instance main | Có field/helper instance và rõ quá trình khởi tạo |
| Ứng dụng cần nhận CLI args | `void main(String[])` hoặc `static void main(String[])` | Lấy dữ liệu ở main, validate rồi chuyển vào service |
| Ứng dụng framework lớn (Spring Boot, Jakarta, Quarkus...) | Entry-point theo cơ chế framework/tài liệu version | Framework quản lý bean, DI, lifecycle và startup failure |
| Thư viện cần API công khai | Lớp khai báo tường minh, không phụ thuộc compact class | API/package/module rõ ràng |
| Class bất biến cần constructor tham số | Không ép no-arg constructor chỉ vì muốn instance main | Giữ invariant, dùng entry-point riêng |
| Luồng khởi động có resource I/O và cấu hình phức tạp | Entry-point nhẹ và service được quản lý riêng | Dễ test, trả lỗi rõ, không làm constructor chứa side effect lớn |

Ví dụ entry-point kết hợp instance main với service có dependency:

```java
class ApplicationEntry {
    void main(String[] args) {
        String mode = args.length == 0 ? "demo" : args[0];
        ApplicationService service = new ApplicationService(mode);
        service.start();
    }
}

final class ApplicationService {
    private final String mode;

    ApplicationService(String mode) {
        if (mode.isBlank()) {
            throw new IllegalArgumentException("mode rỗng");
        }
        this.mode = mode;
    }

    void start() {
        System.out.println("Start mode: " + mode);
    }
}
```

`ApplicationEntry` có default no-arg constructor; `ApplicationService` vẫn được bảo đảm cấu hình trước khi sử dụng. Đây là cách tiếp cận tốt hơn so với thêm constructor rỗng vào `ApplicationService` rồi phải chấp nhận trường `mode == null`.

### Tác động đến nâng cấp JDK và công cụ xây dựng

- Khi **biên dịch bằng Java 25** cho các nguồn sử dụng instance main/compact source, đặt language level/release phù hợp (`--release 25`) và chọn compiler JDK 25.
- Khi **sản phẩm vẫn phải chạy Java 21**, phải giữ source/API phù hợp mục tiêu đó; không đưa cú pháp Java 25 vào artifact nhắm target cũ.
- Maven/Gradle/IDE đã hỗ trợ Java 25 phải được cấu hình nhất quán. Một source file chạy qua `java File.java` chưa chứng minh rằng mọi task packaging/analysis/test của project đã chạy đúng.
- Test cả class launch, source-file launch nếu dự án dùng, và một số chương trình dùng kế thừa hoặc constructor tùy biến để phát hiện lỗi do build/launcher.
- Không giả định build tool sẽ tự chọn entry-point khi đóng gói nhiều class có `main`; hãy khai báo **main class** hoặc launcher/task rõ ràng theo plugin/framework đang dùng.

## 13. Bài tập thực hành: đoán đúng khi nào tạo instance

### Bài tập 1 — Có hai ứng viên main

```java
class QuizOne {
    QuizOne() {
        System.out.println("constructor");
    }

    void main() {
        System.out.println("instance main");
    }

    static void main(String[] args) {
        System.out.println("static main");
    }
}
```

Hỏi: chạy `java QuizOne.java` in gì, constructor có chạy không, tại sao?

**Gợi ý:** xét ưu tiên **chữ ký `String[]`** trước khi xét static/instance.

### Bài tập 2 — Chỉ có constructor nhận tham số

```java
class QuizTwo {
    QuizTwo(int port) {}

    void main(String[] args) {
        System.out.println("Server ready");
    }
}
```

Hỏi: `javac --release 25 QuizTwo.java` có thể thành công không? `java QuizTwo` thì sao? Có thể dùng `java QuizTwo 8080` để làm launcher tự gọi `QuizTwo(8080)` không?

### Bài tập 3 — Khởi tạo thất bại

```java
class QuizThree {
    static {
        System.out.println("static ready");
    }

    QuizThree() {
        throw new IllegalStateException("constructor failed");
    }

    void main() {
        System.out.println("main ready");
    }
}
```

Hỏi: dòng nào có thể in trước khi chương trình lỗi? Trường hợp thất bại xuất hiện trước hay sau lúc chọn `main`?

### Bài tập 4 — Compact source file

```java
// File: QuizFour.java
String name = "Java 25";

void main() {
    IO.println(name);
}
```

Hỏi: ai tạo constructor? Có thể thêm `QuizFour(String name)` trực tiếp ở cấp file không? Vì sao `this` dùng được dù không khai báo class?

### Bài tập 5 — Kế thừa

```java
class ParentEntry {
    void main() {
        System.out.println(getClass().getSimpleName());
    }
}

class ChildEntry extends ParentEntry {
    ChildEntry(String name) {}
}
```

Hỏi: sau khi biên dịch thành công, chạy `java ChildEntry` có vào `ParentEntry.main()` không? Nếu thêm `ChildEntry()` hợp lệ thì kết quả dự đoán là gì?

### Đáp án tóm tắt

1. **QuizOne:** in `static main`, không in `constructor`; `main(String[])` được ưu tiên và là static.
2. **QuizTwo:** biên dịch được, nhưng launch instance main không tạo được object do không có no-arg constructor. Đối số CLI không tự gán cho constructor.
3. **QuizThree:** có thể in `static ready`, rồi lỗi khi gọi constructor; không in `main ready`.
4. **QuizFour:** trình biên dịch cấp default constructor của implicitly declared class. Compact source file không được khai báo constructor tùy biến; instance main và field nằm trong lớp ngầm, nên `this` có nghĩa.
5. **ChildEntry:** main được kế thừa nhưng launcher không thể khởi tạo `ChildEntry` chỉ với constructor tham số; thêm constructor rỗng hợp lệ thì chương trình in `ChildEntry`.

## 14. Kiểm chứng tự động và tiêu chí hoàn thành

Trong một thư mục thực hành dùng **JDK 25**, tạo các file nhỏ từ bài này và ghi lại kết quả compile/launch. Mục tiêu của kiểm thử không phải kiểm tra chuỗi lỗi launcher từng ký tự, mà là kiểm tra **thành công hay thất bại ở đúng giai đoạn**.

| Ca kiểm thử | Compile | Launch | Bằng chứng |
|---|---|---|---|
| Class không khai báo constructor, `void main()` | Pass | Pass | In thông báo trong main |
| Class có no-arg constructor, instance `main(String[])` | Pass | Pass | Constructor trước main, args được truyền đúng |
| Class chỉ có constructor nhận tham số, instance main | Pass | **Fail** | Không tìm được đường tạo instance không tham số |
| Class có constructor throw, instance main | Pass | **Fail** | Constructor throw trước khi in dòng đầu main |
| Class có static `main(String[])` và instance `main()` | Pass | Pass | Không tạo instance, chọn static main |
| Class có static `main()` và instance `main(String[])` | Pass | Pass | Có tạo instance, chọn instance main có tham số |
| Compact source `void main()` | Pass | Pass | Default no-arg constructor của lớp ngầm |
| Class kế thừa instance main, có no-arg constructor hợp lệ | Pass | Pass | `getClass()` cho tên lớp khởi chạy |
| Abstract class làm initial class với instance main | Có thể pass | **Fail** | Không instantiate abstract initial class |
| Lớp con default constructor nhưng superclass thiếu no-arg | **Fail** | Không chạy | Lỗi constructor chain lúc biên dịch |
| Chỉ có `private void main()` | Source có thể pass | **Fail** | Không có main ứng viên hợp lệ |

Có thể xây kiểm thử smoke qua một script CI chạy `javac --release 25` và `java -cp ...` trong môi trường có JDK 25. Với **case mong đợi thất bại**, kiểm tra exit code khác 0 và có thông tin về giai đoạn tương ứng thay vì coi mọi lỗi là pass. Không dùng JDK 21 với `--enable-preview` để giả lập Java 25; ngữ nghĩa JEP 512 của bản preview trước đó không hoàn toàn giống Java 25 final.

### Checklist kết thúc bài học

- Giải thích chính xác Java 25 xác định **candidate main** và chọn ưu tiên `main(String[])` hơn `main()`.
- Chỉ ra được khi nào launcher cần tạo instance và khi nào static main không cần.
- Phân biệt implicit default constructor của lớp thường với **default constructor bắt buộc có** ở compact source file.
- Giải thích được vì sao constructor chỉ có tham số khiến instance main không launch được dù source có thể compile.
- Biết thứ tự class initialization, instance initialization, constructor và thân main; hiểu lỗi tại bước nào.
- Dự đoán được hành vi main kế thừa, abstract class, inner class và class có nhiều main ứng viên.
- Dùng `java`, `javac --release 25`, `javap` để xác minh; không dựa vào preview/legacy examples.

## 15. Tài liệu tham khảo và quy tắc dùng kiến thức hiện hành

1. [JLS Java SE 25 — §12.1.4 Invoke a `main` Method](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1.4): danh sách candidate, thứ tự chọn `String[]`/no-arg và ngữ nghĩa tạo instance của initial class.
2. [JLS Java SE 25 — §12.5 Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.5): cách tạo và khởi tạo đối tượng.
3. [JLS Java SE 25 — §8.8.9 Default Constructor](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.9): constructor mặc định và quy tắc kế thừa.
4. [JLS Java SE 25 — §8.1.8 Implicitly Declared Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.8): lớp của compact compilation unit, tính `final` và constructor mặc định.
5. [Oracle Java 25 — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): cú pháp, lớp ngầm, giao thức khởi chạy và `java.lang.IO`.
6. [JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512): tính năng được final trong Java 25.
7. [Oracle Java 25 — Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): phân biệt Java 25 final với preview của các bản cũ.
8. [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513): thay đổi khả năng đặt statement trước `super()`/`this()`; không làm đổi hợp đồng chọn instance main.
9. [Oracle JDK 25 — `java` launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html) và [`javac`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): cách chạy source/class và compile.

**Nguyên tắc cập nhật:** Bài này mô tả **Java 25 đã phát hành chính thức**; các ví dụ preview của Java 21–24 về unnamed classes, implicit static import hoặc launcher có thể khác. Khi chuyển sang JDK mới hơn, hãy đối chiếu JLS của version đó trước khi dựa vào chi tiết constructor hoặc error message; với phần cơ bản, hãy ưu tiên no-arg constructor rõ ràng và entry-point dễ kiểm thử.
