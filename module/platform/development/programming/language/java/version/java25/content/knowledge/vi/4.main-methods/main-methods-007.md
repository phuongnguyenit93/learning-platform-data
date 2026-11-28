# Áp dụng instance main trong lớp tường minh và tệp nguồn gọn

> **Chương:** Hàm main
> **Phạm vi:** Java 25, JEP 512 — *Compact Source Files and Instance Main Methods*. Bài học tập trung vào cú pháp và hành vi đã **chính thức** trong Java 25, không áp dụng các quy tắc từ bản preview cũ nếu chúng đã thay đổi.
> **Mục tiêu thực tế:** Chọn giữa instance `main` trong một class khai báo tường minh và `main` trong compact source file; chạy, kiểm thử, mở rộng chương trình và tránh lỗi launch.

## 1. Vấn đề: cùng là điểm bắt đầu, nhưng không cùng cấu trúc chương trình

Trước Java 25, nhiều ví dụ Java bắt đầu bằng:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello!");
    }
}
~~~

Mẫu này **vẫn hợp lệ, vẫn được hỗ trợ và vẫn thích hợp** cho ứng dụng, thư viện hoặc framework cần một entry point thông thường. Nó không phải cú pháp lỗi thời cần loại bỏ.

Java 25 chính thức hóa **JEP 512**: `main` không còn bắt buộc phải là `public static` hoặc nhận `String[]`. Ngoài ra, một file có thể chứa trực tiếp method và field mà không khai báo lớp bao ngoài; compiler sẽ tạo **implicitly declared class** cho file đó.

Hai khả năng này **độc lập**:

1. **Instance `main` trong lớp tường minh:** lớp vẫn có tên, có thể có package, constructor, field và các method; chỉ điểm vào chương trình là instance method.
2. **Compact source file:** bỏ khai báo class; các thành viên ở cấp file thuộc một lớp ngầm định. File thường chứa `void main()` hoặc `void main(String[] args)` để có thể khởi chạy.

Chúng giải quyết hai nhu cầu khác nhau: giữ cấu trúc rõ ràng nhưng giảm `static` ở ví dụ/công cụ nhỏ; hoặc viết chương trình một file thật ngắn mà chưa cần dựng class.

### Kết quả học tập

Sau bài này, bạn có thể:

- Viết và chạy `void main()` hoặc `void main(String[] args)` trong **lớp khai báo tường minh**.
- Viết và chạy **compact source file** có field, method, tham số dòng lệnh và `java.lang.IO`.
- Giải thích cách Java 25 chọn giữa `main(String[])` và `main()`, cũng như yêu cầu constructor cho instance `main`.
- Phân biệt khả năng import, tên lớp, package, khả năng tái sử dụng và phát hành.
- Chuyển chương trình compact thành explicit class khi mã bắt đầu lớn.
- Nhận diện những ví dụ Java 21–24 ở trạng thái preview không còn phản ánh chính xác Java 25.

## 2. Quy tắc cốt lõi của JEP 512 trong Java 25

| Khía cạnh | Java 25 cho phép | Giới hạn cần nhớ |
| --- | --- | --- |
| Kiểu kết quả | `void` | `int main()` không phải launchable main. |
| Tham số | Không có tham số, hoặc một `String[]`; `String...` tương đương `String[]` | Không có overload launcher cho `List<String>` hoặc hai tham số tùy ý. |
| Modifier | `static` **hoặc** instance | Với instance main, launcher phải tạo được object hợp lệ. |
| Quyền truy cập | `public`, `protected` hoặc package-private | `private main` không phải launchable method. |
| Nơi khai báo | Class tường minh hoặc lớp ngầm định từ compact source file | Compact class không phải public API có thể import theo tên. |
| Thứ tự ưu tiên | `main(String[])` trước `main()` | Không ưu tiên `static` trước instance theo cách một số bài cũ mô tả. |
| Phiên bản | **Final ở Java 25** | Không cần `--enable-preview` cho các ví dụ trong bài. |

Các phương thức đủ điều kiện còn có thể có `throws` và có thể được kế thừa theo quy tắc Java. Trong phần thực hành, ta cố ý khai báo trực tiếp một `main` duy nhất ở mỗi file để code dễ dự đoán.

**Quy tắc chọn entry point:** trước hết tìm `main(String[])` hợp lệ (có thể viết `String...`). Chỉ khi không có mới tìm `main()` hợp lệ. Nếu phương thức được chọn là instance, launcher tạo đối tượng của lớp khởi chạy bằng **constructor không tham số có quyền truy cập phù hợp** trước khi gọi `main`.

~~~mermaid
flowchart TD
    A["java launcher chọn class khởi chạy"] --> B{"Có main(String[]) hợp lệ?"}
    B -->|"Có"| C["Chọn main(String[])"]
    B -->|"Không"| D{"Có main() hợp lệ?"}
    D -->|"Có"| E["Chọn main()"]
    D -->|"Không"| F["Báo lỗi thiếu launchable main"]
    C --> G{"Phương thức được chọn là static?"}
    E --> G
    G -->|"Có"| H["Gọi trực tiếp"]
    G -->|"Không"| I["Tạo instance bằng constructor 0 tham số hợp lệ"]
    I --> J["Gọi instance main"]
~~~

Đây là **launch protocol**, không phải thay đổi ngữ nghĩa toàn bộ method Java. Các overload mang tên `main` vẫn tuân thủ quy tắc Java về method signature, inheritance và access.

## 3. Cách 1: instance main trong lớp tường minh

### 3.1. Ví dụ nhỏ nhất có class

Lưu file `Greeter.java`:

~~~java
// Greeter.java — Java 25
public class Greeter {
    void main() {
        IO.println("Xin chào Java 25!");
    }
}
~~~

Chạy trực tiếp từ source file:

~~~bash
java Greeter.java
~~~

Hoặc biên dịch rồi chạy class:

~~~bash
javac Greeter.java
java Greeter
~~~

Trong Java 25, `void main()` ở đây là **instance method**: không có `static`, không có `String[] args`, không cần modifier `public`. Class vẫn được khai báo tường minh bằng `public class Greeter`.

Nếu cần đặt package, source file vẫn dùng cú pháp chuẩn:

~~~java
// src/main/java/com/example/tool/Greeter.java
package com.example.tool;

public class Greeter {
    void main() {
        IO.println("Chạy trong package com.example.tool");
    }
}
~~~

~~~bash
javac -d out src/main/java/com/example/tool/Greeter.java
java -cp out com.example.tool.Greeter
~~~

Một class có tên phù hợp khi chương trình cần package, kiểm thử từng lớp, tái sử dụng từ code khác hoặc tích hợp vào cấu trúc dự án đã có.

### 3.2. Dùng field và instance helper tự nhiên

~~~java
// ReportCli.java
public class ReportCli {

    private final String prefix = "[REPORT]";
    private int processed;

    void main(String[] args) {
        if (args.length == 0) {
            IO.println("Usage: java ReportCli.java <item>...");
            return;
        }

        for (String item : args) {
            emit(item);
        }
        IO.println("Đã xử lý: " + processed);
    }

    private void emit(String item) {
        IO.println(prefix + " " + item);
        processed++;
    }
}
~~~

Chạy:

~~~bash
java ReportCli.java apple banana
~~~

Kết quả dự kiến:

~~~text
[REPORT] apple
[REPORT] banana
Đã xử lý: 2
~~~

Instance `main` gọi trực tiếp `emit` và truy cập `prefix`, `processed` mà không biến mọi helper/field thành `static`. Class vẫn có tên, nên sau này có thể chuyển logic vào một service riêng để test; **không** vì có instance main mà xem launcher là dependency injection container.

### 3.3. Constructor: điểm khác biệt quan trọng với static main

Để khởi chạy instance method, Java phải tạo được instance đầu tiên. Ví dụ:

~~~java
// LaunchWithConstructor.java
public class LaunchWithConstructor {

    private final String greeting;

    public LaunchWithConstructor() {
        this.greeting = "Xin chào!";
    }

    void main() {
        IO.println(greeting);
    }
}
~~~

~~~bash
javac LaunchWithConstructor.java
java LaunchWithConstructor
~~~

Đây là trường hợp hợp lệ vì có constructor **không tham số, có thể truy cập**. Nếu class chỉ có `LaunchWithConstructor(String greeting)`, thì launcher không thể tự cung cấp tham số và invocation của instance `main` thất bại. Điều này **khác** `static main`: gọi một static method không yêu cầu tạo instance.

Một kiểu phản ví dụ chỉ nhằm giải thích lỗi:

~~~java
// Chỉ để nhận diện lỗi runtime khi launch, KHÔNG phải mẫu nên dùng.
class WrongConstructor {
    WrongConstructor(String name) {}

    void main() {
        IO.println("Sẽ không được chạy qua instance launch thông thường");
    }
}
~~~

Không nên thêm constructor rỗng giả tạo rồi khởi tạo trạng thái không hợp lệ chỉ để “qua được launcher”. Với chương trình có dependency phức tạp, dùng `public static void main(String[] args)` làm composition root và khởi tạo object/service qua constructor có tham số vẫn là thiết kế hoàn toàn phù hợp.

## 4. Cách 2: compact source file không khai báo class

### 4.1. Ví dụ tối giản

Lưu nguyên nội dung sau vào `HelloCompact.java`:

~~~java
// HelloCompact.java — không có class declaration
void main() {
    IO.println("Xin chào từ compact source file!");
}
~~~

Chạy:

~~~bash
java HelloCompact.java
~~~

Đây là **compact source file**, chứa method không nằm trong class được khai báo tường minh. Trình biên dịch sẽ coi các member ở cấp file là thành viên của một **implicitly declared class**.

### 4.2. Compact source vẫn có instance state và helper

~~~java
// DailyChecklist.java
int done;

void mark(String task) {
    done++;
    IO.println(done + ". " + task);
}

void main() {
    mark("Kiểm tra cấu hình");
    mark("Chạy smoke test");
    mark("Xác minh đầu ra");
    IO.println("Tổng cộng: " + done);
}
~~~

~~~bash
java DailyChecklist.java
~~~

Một compact source file không phải “Java script” với biến toàn cục không có class. Dưới hood, `done` là **instance field**, `mark` và `main` là **instance methods** của lớp ngầm định. Code vẫn tuân thủ kiểu dữ liệu, access modifier và các quy tắc của Java.

### 4.3. Các thuộc tính của implicitly declared class

Theo Java SE 25:

- Là **final top-level class** trong **unnamed package**, thuộc **unnamed module**.
- Kế thừa `java.lang.Object` và không khai báo thực thi interface.
- Có constructor mặc định **không tham số**, không có các constructor khác.
- Chứa các field, method và nested type khai báo trực tiếp trong compact source file.
- Bắt buộc có một `main` hợp lệ để chạy chương trình.
- Không thể được **gọi tên từ Java source code** để dùng như kiểu API thông thường; không dùng `new HelloCompact()` trong source khác như một hợp đồng thư viện.

JDK có thể tạo file `HelloCompact.class` khi biên dịch trực tiếp; tên class được compiler chọn là chi tiết triển khai, **không phải một tên public API để các package khác phụ thuộc**. Ưu tiên `java HelloCompact.java` khi muốn chia sẻ một chương trình dạng source file.

**Không áp dụng `package com.example;` trực tiếp để biến implicitly declared class thành class thuộc named package.** Khi cần package/constructor rõ ràng hoặc tái sử dụng từ module khác, chuyển sang explicit class như phần 10.

## 5. So sánh nhanh hai cách viết

| Tiêu chí | **Explicit class + instance main** | **Compact source file + instance main** |
| --- | --- | --- |
| File tiêu biểu | `Greeter.java` chứa `class Greeter { void main() {...} }` | `HelloCompact.java` chứa trực tiếp `void main() {...}` |
| Có tên class trong mã nguồn | Có, do lập trình viên đặt | Không; compiler sinh lớp ngầm định |
| Package | Có thể thuộc named package | Unnamed package |
| Constructor | Có thể viết constructor như class Java bình thường; instance launch cần no-arg phù hợp | Lớp ngầm định chỉ có constructor mặc định không tham số |
| Kế thừa/interface | Theo quy tắc class Java thông thường | Không thể `extends`/`implements` cho lớp ngầm định |
| Import mặc định | `java.lang` (và những import Java thông thường), **không** tự import toàn bộ `java.base` | Ngầm có import theo module `java.base`, dùng trực tiếp nhiều public types |
| Kiểm thử/tái sử dụng | Có tên class và package; dễ tổ chức unit test | Thích hợp điểm vào của utility một file; tách logic riêng khi lớn |
| Khởi chạy | `java Greeter.java` hoặc `javac` rồi `java Greeter` | `java HelloCompact.java`; cũng có thể biên dịch trực tiếp |
| Khuyến nghị | Khi muốn cấu trúc rõ ràng mà không cần static helpers | Demo, bài tập, tiện ích nhỏ, proof of concept |

Một điểm thường nhầm: **instance main không đồng nghĩa compact source**, và **compact source không bắt buộc dùng instance main** nếu nó khai báo static launchable main phù hợp. Đây là hai thay đổi độc lập trong cùng JEP.

## 6. Quy tắc chọn main khi có nhiều overload

Java 25 cho phép cùng class có `main()` và `main(String[] args)`, nếu hai phương thức khác signature. Launcher chọn **biến thể có `String[]` trước**, không xét static/instance để đảo thứ tự đó.

~~~java
// WhichMain.java
class WhichMain {

    static void main() {
        IO.println("static main()");
    }

    void main(String[] args) {
        IO.println("instance main(String[])");
        IO.println("Số đối số: " + args.length);
    }
}
~~~

~~~bash
javac WhichMain.java
java WhichMain x y
~~~

Kết quả Java 25:

~~~text
instance main(String[])
Số đối số: 2
~~~

Nếu đổi code chỉ còn `static void main()` thì launcher gọi method đó. Nếu chỉ có `void main()`, launcher tạo instance rồi gọi method instance. Cả `void main(String[] args)` và `void main(String... args)` đều là một kiểu tham số `String[]`; không thể đồng thời khai báo hai method đó như hai overload khác nhau.

**Không dựa vào “static luôn được chọn trước”** từ các bài diễn giải preview cũ; hãy theo Java SE 25/JEP 512. Trong ứng dụng chuyên nghiệp, nên có **một entry point rõ ràng** để người đọc và build tool không phải suy luận.

### 6.1. Các mẫu main hiện đại và hợp lệ

| Cách khai báo bên trong class | Launcher Java 25 có thể dùng? | Khi nào hữu ích |
| --- | --- | --- |
| `public static void main(String[] args)` | Có | Phổ biến, tương thích lâu dài với nhiều toolchain |
| `static void main()` | Có | Chương trình không cần đối số |
| `void main()` | Có, cần instance hợp lệ | Utility/testbed có helper instance |
| `protected void main(String[] args)` | Có, cần instance hợp lệ | Trường hợp đặc biệt theo access rules |
| `void main(String... args)` | Có, cần instance hợp lệ | Tương đương tham số `String[]` |
| `private void main()` | **Không** | Không đủ quyền truy cập để launcher chọn |
| `int main(String[] args)` | **Không** | Sai kiểu trả về |
| `void main(List<String> args)` | **Không** | Sai loại tham số launcher hỗ trợ |

Các biến thể được phép không có nghĩa tất cả IDE, build plugin hoặc công cụ đóng gói cũ đều xử lý chúng giống nhau. Luôn thử **lệnh khởi chạy thật** của artifact, nhất là khi chuyển từ source launcher sang executable JAR, native image hoặc framework bootstrap.

## 7. Tham số dòng lệnh với instance main

Chỉ `main(String[] args)` (hoặc `String... args`) nhận được tham số do launcher chuyển vào. Nếu chỉ khai báo `main()`, đối số dòng lệnh không được cấp cho method đó.

Ví dụ compact source đọc các đầu vào:

~~~java
// ValidateFiles.java
void main(String[] args) {
    if (args.length == 0) {
        IO.println("Cách dùng: java ValidateFiles.java <file>...");
        return;
    }

    for (String name : args) {
        Path file = Path.of(name);
        if (Files.isRegularFile(file)) {
            IO.println("OK: " + file.getFileName());
        } else {
            IO.println("Không tìm thấy file: " + file.getFileName());
        }
    }
}
~~~

~~~bash
java ValidateFiles.java config.yaml settings.properties
~~~

`Path` và `Files` thuộc `java.nio.file`; chúng được truy cập không cần import thông thường **vì file compact được tự động import các exported public types của `java.base`**. Cùng đoạn code trong explicit class thường cần:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
~~~

Hoặc trong Java 25 có thể dùng `import module java.base;` nếu điều đó làm source dễ đọc hơn.

**Bảo vệ đầu vào:** luôn kiểm tra `args.length` trước khi lấy `args[0]`, không giả định người dùng có quyền đọc đường dẫn, không ghi secrets hoặc nội dung cấu hình nhạy cảm ra console. Ví dụ trên chỉ in tên file, không đọc hay hiển thị dữ liệu.

## 8. java.lang.IO và import trong Java 25

Java 25 bổ sung lớp **`java.lang.IO`** với các method tĩnh:

| API | Chức năng |
| --- | --- |
| `IO.println(Object)` | In giá trị kèm xuống dòng |
| `IO.println()` | Xuống dòng |
| `IO.print(Object)` | In giá trị không tự xuống dòng |
| `IO.readln()` | Đọc một dòng từ standard input |
| `IO.readln(String prompt)` | In lời nhắc và đọc một dòng |

Ví dụ một compact source file tương tác:

~~~java
// AskName.java
void main() {
    String name = IO.readln("Tên của bạn: ");

    if (name == null || name.isBlank()) {
        IO.println("Không có tên hợp lệ.");
        return;
    }

    IO.println("Xin chào, " + name.strip() + "!");
}
~~~

~~~bash
java AskName.java
~~~

`IO` thuộc `java.lang` nên có thể dùng **trong explicit class và compact source file** mà không cần import class. Nhưng **`println(...)` không được tự động static-import** trong Java 25. Viết bare `println("hi")` sẽ không tự hoạt động, trừ khi bạn chủ động thêm:

~~~java
import static java.lang.IO.println;

void main() {
    println("Hợp lệ vì đã import static method.");
}
~~~

Lưu ý khi đọc input: `IO.readln` có thể trả về `null` tại EOF, nên cần kiểm tra. Theo Javadoc Java 25, `IO` dùng `System.in/System.out`; không nên trộn `IO.readln` với các cơ chế đọc `System.in` khác trong cùng một tiến trình mà không kiểm soát buffering, vì hành vi sau khi `readln` đọc dữ liệu có thể không xác định.

### 8.1. Import tự động khác với module declaration

Compact source file ngầm có hiệu quả tương tự:

~~~java
import module java.base;
~~~

Điều đó cho phép sử dụng `List`, `Map`, `LocalDate`, `Path`, `Files`, `Stream`, v.v. mà không cần import tường minh. Nhưng **không** tự import mọi dependency bên ngoài `java.base` và **không** biến file thành một Java module có `module-info.java`. Các class trong `java.sql`, thư viện bên thứ ba hoặc API công ty vẫn cần dependency và cấu hình thích hợp.

Đối với explicit class, `import module java.base;` là tính năng **JEP 511 final trong Java 25**, nhưng không tự có nếu bạn không viết nó. Với mã thư viện dài hạn, nhập type cụ thể đôi khi làm code rõ ý hơn so với import toàn module.

## 9. Ví dụ đối chiếu một công cụ thực tế theo hai phong cách

Mục tiêu: một CLI nhận danh sách tên môi trường (chỉ dữ liệu giả), chuẩn hóa chữ thường và in tên đã xử lý. Không cần truy cập filesystem, network hoặc cấu hình bí mật.

### 9.1. Phiên bản compact source file

~~~java
// NormalizeEnv.java
int total;

void printNormalized(String value) {
    String normalized = value.strip().toLowerCase(Locale.ROOT);
    total++;
    IO.println(total + ": " + normalized);
}

void main(String[] args) {
    if (args.length == 0) {
        IO.println("Usage: java NormalizeEnv.java DEV STAGING ...");
        return;
    }

    for (String environment : args) {
        printNormalized(environment);
    }
}
~~~

~~~bash
java NormalizeEnv.java DEV STAGING Production
~~~

Kết quả:

~~~text
1: dev
2: staging
3: production
~~~

`Locale` thuộc `java.util`, tự có vì compact file ngầm import `java.base`. `total` là instance field của implicitly declared class.

### 9.2. Phiên bản explicit class với instance main

~~~java
// NormalizeEnvApp.java
import java.util.Locale;

public class NormalizeEnvApp {

    private int total;

    void main(String[] args) {
        if (args.length == 0) {
            IO.println("Usage: java NormalizeEnvApp.java DEV STAGING ...");
            return;
        }

        for (String environment : args) {
            printNormalized(environment);
        }
    }

    private void printNormalized(String value) {
        String normalized = value.strip().toLowerCase(Locale.ROOT);
        total++;
        IO.println(total + ": " + normalized);
    }
}
~~~

~~~bash
java NormalizeEnvApp.java DEV STAGING Production
~~~

Chức năng giống nhau, nhưng explicit class có thể được đặt vào named package, có thể được tham chiếu từ các class khác và dễ tổ chức logic thành nhiều file. Khi CLI phát triển thành công cụ có thư viện, xử lý nhiều loại input hoặc kiểm thử phức tạp, đây là hướng mở rộng phù hợp.

## 10. Chuyển dần từ compact source sang explicit class

Không cần viết lại toàn bộ logic khi chương trình lớn dần. Giả sử ban đầu có:

~~~java
// Welcome.java — compact source
String greeting(String name) {
    return "Xin chào, " + name;
}

void main(String[] args) {
    String name = args.length == 0 ? "bạn" : args[0];
    IO.println(greeting(name));
}
~~~

Để chuyển thành explicit class, đặt các member vào một lớp có tên:

~~~java
// Welcome.java — explicit class
public class Welcome {

    String greeting(String name) {
        return "Xin chào, " + name;
    }

    void main(String[] args) {
        String name = args.length == 0 ? "bạn" : args[0];
        IO.println(greeting(name));
    }
}
~~~

Những phần còn giữ được:

- `main(String[] args)` vẫn là instance method.
- `greeting` vẫn là helper instance, không cần chuyển thành static.
- `IO.println` vẫn hoạt động vì `java.lang` được implicit import trong cả hai dạng.
- Source launcher `java Welcome.java` vẫn là cách chạy đơn giản.

Những phần cần xem xét:

1. Tên class và package trở thành quyết định kiến trúc; nếu đưa vào `com.example`, cập nhật đường dẫn nguồn và lệnh launch.
2. Các type `java.base` ngoài `java.lang` từng được import tự động ở compact file **phải được import rõ ràng** hoặc dùng `import module java.base;`.
3. Không tạo constructor bắt buộc có tham số nếu vẫn muốn launcher gọi instance `main` bằng cách tự tạo object.
4. Khi tách logic nghiệp vụ khỏi CLI, có thể dùng object thuần có constructor injection và giữ một entry point nhỏ. Với framework như Spring Boot, không bỏ entry point hiện có chỉ để dùng instance `main`.

~~~mermaid
flowchart LR
    A["Compact source: một file, một nhiệm vụ"] --> B["Cần tái sử dụng / package / unit test?"]
    B -->|"Có"| C["Explicit class + instance main"]
    C --> D["Tách service / domain logic thành lớp có API rõ ràng"]
    B -->|"Không"| E["Giữ compact source, đơn giản hóa"]
~~~

## 11. Source launcher, class launcher và đóng gói

Ba cách thường gặp:

~~~bash
# 1. Source-file mode: biên dịch/nghiệm thu trong lần launch.
java Greeter.java

# 2. Biên dịch rồi chạy class trên classpath.
javac Greeter.java
java Greeter

# 3. Ứng dụng được đóng gói: cách chạy thực tế do build/manifest/framework xác định.
java -jar app.jar
~~~

JDK 25 định nghĩa launch protocol mới, nhưng một số **plugin, ứng dụng đóng gói và công cụ quét main** có thể chưa hỗ trợ mọi biến thể instance main. Hãy kiểm tra command thực tế của CI/CD, IDE và framework (đặc biệt lúc chọn main class của executable JAR), thay vì suy luận từ việc `java Tool.java` chạy thành công.

| Dự án | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| Bài tập Java 25 | Compact source `void main()` | Giảm boilerplate, tập trung vào lệnh Java. |
| Script vận hành nhỏ một file | Compact source `void main(String[] args)` | Nhận tham số, dễ thử trực tiếp bằng `java File.java`. |
| CLI nhỏ cần class/package | Explicit class + instance `main` | Có thể tổ chức thêm helper và test. |
| CLI với thư viện, DI, nhiều lệnh | Class tường minh, entry point theo framework hoặc static `main` nếu thuận tiện | Rõ dependency và đóng gói. |
| Spring Boot service / ứng dụng lớn | Giữ bootstrap do framework hỗ trợ | Không có lợi ích tự động khi đổi static main sang instance main. |
| Thư viện phát hành | Không xem `main` là API thư viện | Ưu tiên public API, compatibility và test. |

Nếu build phải hỗ trợ JDK thấp hơn Java 25, tiếp tục sử dụng entry point cũ theo mức tương thích đã công bố. Không biên dịch `void main()` kiểu Java 25 rồi tuyên bố chạy trên Java 21 mà không có lựa chọn source/bytecode tương ứng.

## 12. Cách kiểm thử và đo hiệu quả cải tiến

Với `main`, mục tiêu kiểm thử chính là **hành vi chương trình**, không phải chứng minh “ít dòng code hơn là chạy nhanh hơn”.

### 12.1. Kiểm thử đầu vào

Đối với `ReportCli` hoặc `NormalizeEnvApp`, hãy kiểm tra:

1. Không có args: in hướng dẫn, không truy cập `args[0]`.
2. Một arg: in kết quả đúng.
3. Nhiều args: duy trì thứ tự, đếm chính xác.
4. Dữ liệu chứa khoảng trắng: xử lý đúng sau `strip()` nếu nghiệp vụ yêu cầu.
5. Lỗi nghiệp vụ: trả thông báo có ích, không in secret.

### 12.2. Kiểm thử launch protocol

Thử cả hai lệnh trên JDK 25:

~~~bash
java -version
javac ReportCli.java
java ReportCli alpha beta
java ReportCli.java alpha beta
~~~

So output của hai đường chạy. Không cần `--enable-preview` cho JEP 512 trong Java 25. Với explicit class trong package, chạy bằng tên đầy đủ và classpath đúng; không lấy đường dẫn file `.class` làm tên main class.

### 12.3. Kiểm thử khả năng mở rộng

Nếu chương trình bắt đầu thêm nhiều hàm tính toán, tách logic thành class có method dễ test. Ví dụ:

~~~java
// NameFormatter.java — class logic độc lập, có thể unit test
import java.util.Locale;

public final class NameFormatter {
    public String normalize(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input required");
        }
        return input.strip().toLowerCase(Locale.ROOT);
    }
}
~~~

Entry point chỉ điều phối input/output; class logic nhận dependency và dữ liệu rõ ràng. Đây là thay đổi thiết kế có ích hơn việc biến tất cả code thành một `main` dài chỉ vì compact file có thể chứa mọi member.

## 13. Các lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân | Cách sửa theo Java 25 |
| --- | --- | --- |
| `main method not found` hoặc launch thất bại | `private main()`, sai return type, sai params hoặc không có launchable method | Dùng `void main()` / `void main(String[])` với quyền truy cập hợp lệ. |
| Có `main` instance nhưng launcher không tạo được object | Chỉ có constructor bắt buộc tham số hoặc constructor không tham số không thể truy cập | Cung cấp constructor không tham số hợp lệ, hoặc chuyển bootstrap thành static `main`. |
| Thêm `static main()` nhưng chương trình vẫn chạy `main(String[])` | Launcher ưu tiên phương thức có `String[]`, kể cả instance | Giữ một entry point duy nhất, hoặc áp dụng đúng quy tắc chọn. |
| `cannot find symbol: println` | Nhầm với preview cũ có implicit static import | Dùng `IO.println(...)` hoặc `import static java.lang.IO.println;`. |
| `cannot find symbol: List/Path` sau khi bọc class | Explicit class không tự import mọi exported type của `java.base` | Dùng import riêng hoặc `import module java.base;` trong JDK 25. |
| Không import được lớp compact từ package khác | Implicitly declared class không có API tên được tham chiếu từ Java source | Chuyển thành explicit class có package và public API. |
| `java Tool` chạy sai/mất class | Biên dịch vào directory khác, sai package hoặc nhầm launcher với source file | Kiểm tra `javac -d out` và dùng `java -cp out package.Tool`; hoặc `java Tool.java`. |
| `IO.readln()` gây lỗi null sau EOF | Không kiểm tra kết quả `null` | Xử lý EOF trước khi gọi `strip()`, `isBlank()`. |
| Mã chạy Java 25 nhưng fail Java 21 | Feature final chỉ từ 25; bytecode cao hơn hoặc Java cũ không hiểu launch protocol | Chọn đúng minimum JDK, `--release` và CI matrix; không công bố tương thích sai. |
| Code chạy trong terminal nhưng IDE/build plugin báo thiếu main | Công cụ chưa hiểu JEP 512 hoặc cấu hình launch khác | Nâng toolchain tương thích, kiểm tra launcher thực tế; tạm giữ static main khi phù hợp. |

**Không nên “sửa” bằng cách thêm `--enable-preview`** vào một dự án Java 25 chỉ để chạy instance `main` hoặc compact source file. Chúng đã final. Cờ đó phục vụ các tính năng khác vẫn preview trong đúng release và có thể làm pipeline phức tạp không cần thiết.

## 14. Lựa chọn an toàn cho phát triển Java hiện đại

Những thực hành nên giữ:

- **Dùng cú pháp mới khi nó giảm độ phức tạp thật:** `void main()` hữu ích cho bài học, ví dụ, utility; chương trình sản xuất lớn có thể tiếp tục dùng entry point tường minh.
- **Không đồng nhất tên class với tên file compact:** lớp ngầm định là chi tiết compiler, không phải hợp đồng thư viện.
- **Không giả định source launcher quản lý dependencies:** Maven/Gradle, module path, classpath, class loader và runtime packaging vẫn cần được thiết kế nếu có thư viện ngoài JDK.
- **Giữ input/output an toàn:** không in token hoặc secret; xử lý EOF, đường dẫn và tham số dòng lệnh có kiểm soát.
- **Ưu tiên code dễ test:** logic nghiệp vụ tách khỏi main khi đã vượt phạm vi một utility rất nhỏ.
- **Nêu rõ minimum Java:** nếu tài liệu hoặc artifact yêu cầu `instance main`/`IO` theo Java 25, ghi Java 25 trong hướng dẫn chạy.
- **Đừng gọi static main là “legacy phải bỏ”:** cách viết đó vẫn hữu ích và thường là lựa chọn tương thích tốt nhất trong framework/toolchain đa dạng.
- **Tránh dùng cú pháp của Java 21–24 preview như tài liệu chuẩn cho 25:** đặc biệt với `java.lang.IO` và static import behavior đã thay đổi.

### Bảng quyết định ngắn

| Câu hỏi | Nếu câu trả lời là… | Chọn |
| --- | --- | --- |
| Chương trình một file, ít dependency, chủ yếu học tập/tiện ích? | Có | **Compact source + instance main** |
| Cần package rõ ràng, tên class và unit test? | Có | **Explicit class + instance main** |
| Cần constructor injection/phụ thuộc runtime phức tạp? | Có | **Explicit class + static bootstrap hoặc framework entry point** |
| Có nhiều consumer ở JDK cũ hơn 25? | Có | **Cú pháp/target tương thích với JDK tối thiểu** |
| Muốn dùng kiểu `List`, `Path` trong explicit class? | Có | **Import tường minh hoặc JEP 511 module import** |

## 15. Bài tập thực hành tự đánh giá

### Bài A — Instance main trong class tường minh

Tạo `WelcomeApp.java` với `public class WelcomeApp`, field `prefix`, helper `format(String name)` và `void main(String[] args)`.

**Yêu cầu:** chạy `java WelcomeApp.java Lan`, xử lý trường hợp không có args và tạo kết quả `Xin chào, Lan`. Sau đó dùng `javac WelcomeApp.java` và `java WelcomeApp Lan`; hai đường chạy cần cùng kết quả.

### Bài B — Compact source và java.base import

Tạo `DateSummary.java` không có class declaration. Dùng `LocalDate` và `List` để in ngày hôm nay cùng hai ngày kế tiếp. Không viết import riêng.

**Gợi ý:**

~~~java
// DateSummary.java
void main() {
    LocalDate today = LocalDate.now();
    List<LocalDate> days =
            List.of(today, today.plusDays(1), today.plusDays(2));
    days.forEach(IO::println);
}
~~~

Giải thích vì sao `List`/`LocalDate` có thể dùng trực tiếp. Sau đó bọc code vào explicit class và thêm import phù hợp.

### Bài C — Thứ tự chọn main

Viết một explicit class có `static void main()` và `void main(String[] args)`. Dự đoán method được chạy với lệnh `java ClassName x`, sau đó kiểm chứng bằng cách in thông báo khác nhau ở mỗi method. Giải thích vì sao lựa chọn không phụ thuộc việc method nào là static.

### Bài D — Biến tiện ích thành chương trình có thể bảo trì

Bắt đầu từ compact file `NormalizeEnv.java` ở mục 9. Khi yêu cầu xuất hiện nhiều hơn (kiểm tra tên hợp lệ, đọc file, lỗi cấu hình), hãy:

1. Chuyển thành explicit class có package.
2. Tách logic chuẩn hóa sang `EnvironmentNormalizer` có method độc lập.
3. Viết test cho input rỗng, chữ hoa, khoảng trắng và ký tự không hợp lệ.
4. Giữ `main` chỉ xử lý args và in kết quả.

**Tiêu chí hoàn thành:** cú pháp Java 25 hợp lệ, hiểu đúng class ngầm định/explicit, launch protocol, import, không thêm preview flags và vẫn có cấu trúc phù hợp khi chương trình lớn lên.

## 16. Checklist và tài liệu chính thức

Trước khi chọn cách viết `main` cho một dự án:

- [ ] Xác nhận **JDK thực tế là Java 25 hoặc mới hơn có hỗ trợ tính năng tương ứng**, không suy từ `JAVA_HOME` trong tài liệu.
- [ ] Chọn **explicit class** khi cần tên class, package và cấu trúc mở rộng; chọn **compact source** khi thật sự muốn một utility một file.
- [ ] Dùng `void main()` hoặc `void main(String[] args)` đúng quy tắc; không để `private`.
- [ ] Với instance main trong class, constructor không tham số có thể truy cập và thiết kế trạng thái hợp lệ.
- [ ] Nhớ `main(String[])` được ưu tiên trước `main()`, kể cả khi một method là static.
- [ ] Trong compact file, hiểu automatic `java.base` import và unnamed package; không xây public API dựa vào tên class ngầm định.
- [ ] Dùng `IO.println` hoặc static import tường minh, không dựa vào hành vi preview cũ.
- [ ] Thử cả source launcher và đường chạy thực của build/CI; không giả định mọi plugin hỗ trợ instance main.
- [ ] Đưa logic có thể kiểm thử vào method/class riêng khi quy mô vượt một script nhỏ.

### Tài liệu tham khảo đáng tin cậy

1. [OpenJDK — JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512): mục tiêu và trạng thái final trong JDK 25.
2. [Oracle Java SE 25 — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): cấu trúc compact source, `IO`, automatic import, launch protocol và mở rộng sang class.
3. [Java SE 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): những thay đổi của bản final, bao gồm vị trí `java.lang.IO` và quy tắc import.
4. [Java SE 25 — JLS, Implicitly Declared Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html): ngữ nghĩa implicitly declared class.
5. [Java SE 25 — JLS, Execution](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html): quy tắc chọn launchable `main`.
6. [Java SE 25 — java.lang.IO API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/IO.html): `print`, `println`, `readln` và lưu ý về standard input.
7. [Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): source-file mode, classpath và cách gọi launcher.
8. [OpenJDK — JEP 511: Module Import Declarations](https://openjdk.org/jeps/511): cách dùng `import module java.base;` trong source file có class tường minh.

**Kết luận:** Với Java 25, lựa chọn đúng không phải “đổi mọi `main` thành instance”, mà là biết khi nào cần một **class có tên** và khi nào chỉ cần một **compact source file**. Cả hai có thể dùng instance `main` đã final; điểm khác biệt nằm ở tổ chức chương trình, khả năng tái sử dụng, import, constructor và đường phát hành. Hãy ưu tiên cách đơn giản nhất **vẫn dễ kiểm thử và bảo trì** cho nhu cầu thực tế.
