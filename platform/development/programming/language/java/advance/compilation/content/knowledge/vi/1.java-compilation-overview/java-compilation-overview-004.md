# Phân biệt biên dịch, đóng gói, nạp lớp và thực thi trong Java

Bốn khái niệm này mô tả **bốn công việc khác nhau** trên hành trình từ mã nguồn Java đến hành vi của chương trình. Khi gặp lỗi, cần xác định nó xuất hiện tại công việc nào: trình biên dịch chưa tạo được bytecode, công cụ đóng gói thiếu tệp, JVM không tìm/nạp/liên kết/khởi tạo được lớp, hay mã đã bắt đầu chạy rồi mới thất bại.

## 1. Bức tranh tổng thể

~~~text
Mã nguồn .java
    │
    │ javac: phân tích cú pháp, kiểm tra kiểu, sinh bytecode
    ▼
Tệp .class
    │
    │ jar: gom tệp, tài nguyên và metadata (bước tùy chọn)
    ▼
Thư mục classes / JAR / module / nguồn lớp khác
    │
    │ ClassLoader + JVM: nạp lớp, liên kết, khởi tạo khi cần
    ▼
Lớp đã sẵn sàng để sử dụng
    │
    │ JVM thực hiện bytecode: thông dịch và có thể JIT tối ưu
    ▼
Hành vi lúc chạy: kết quả, I/O, thread, exception, ...
~~~

| Giai đoạn | Đầu vào chính | Thành phần phụ trách | Kết quả | Ví dụ lỗi |
| --- | --- | --- | --- | --- |
| **Biên dịch (compilation)** | `.java`, classpath/module path để tra cứu kiểu | `javac` hoặc compiler tương ứng | Bytecode `.class` | `cannot find symbol`, `incompatible types` |
| **Đóng gói (packaging)** | `.class`, tài nguyên, manifest, metadata | `jar`, Gradle, Maven... | `.jar` hoặc loại artifact khác | Thiếu `Main-Class`, bỏ sót dependency |
| **Nạp lớp (class loading)** | Tên lớp và nguồn bytecode khả dụng | Class loader kết hợp cơ chế liên kết/khởi tạo của JVM | Định nghĩa `Class<?>` và lớp sẵn sàng dùng khi cần | `ClassNotFoundException`, `NoClassDefFoundError` |
| **Thực thi (execution)** | Lớp đã sử dụng được, bytecode, dữ liệu đầu vào | JVM, interpreter, JIT, thư viện/runtime | Kết quả và tác dụng phụ lúc chạy | `NullPointerException`, sai kết quả, I/O error |

Sơ đồ là **luồng khái niệm**, không phải quy tắc bắt buộc lúc nào cũng chạy trọn từng bước. Java có thể chạy trực tiếp các `.class` trong thư mục mà **không tạo JAR**; class loader có thể tiếp tục nạp lớp động sau khi `main` đã chạy; và `java File.java` (source-file mode) thực hiện biên dịch trong quá trình khởi chạy, không có nghĩa là bỏ qua biên dịch.

## 2. Biên dịch: từ mã nguồn sang bytecode

### `javac` thực hiện gì?

Với một chương trình Java thông thường, trình biên dịch:

1. Đọc mã nguồn, phân tích cú pháp, tên khai báo, phạm vi truy cập và quan hệ kiểu.
2. Kiểm tra các quy tắc ngôn ngữ như kiểu đối số, kiểu trả về, checked exception, tính khả dụng của method/field và một phần các ràng buộc generic.
3. Sinh các tệp `.class` mang bytecode JVM, constant pool, thông tin kiểu/phương thức và metadata cần thiết; một nguồn có thể sinh nhiều `.class` (ví dụ lớp lồng, lớp ẩn danh).

Ví dụ:

~~~java
// src/demo/Greeter.java
package demo;

public final class Greeter {
    public static String greet(String name) {
        return "Xin chào, " + name;
    }
}
~~~

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/demo/Greeter.java
javap -classpath out -c demo.Greeter
~~~

Sau lệnh biên dịch, tệp `out/demo/Greeter.class` tồn tại. `javap -c` cho phép quan sát chỉ dẫn bytecode đã sinh; đây là **xem kết quả biên dịch**, chưa phải chạy method `greet`. Lệnh `mkdir out` chỉ cần làm một lần; thư mục đích của `-d` phải tồn tại. Tất cả lệnh minh họa dùng cú pháp công cụ của JDK 17+.

### Điều gì được quyết định ở thời điểm biên dịch?

- Một tên biến/method có được nhận diện, kiểu có tương thích, truy cập có hợp lệ theo thông tin compiler thấy hay không.
- Tham chiếu tới lớp/method/field có thể được ghi **theo tên ký hiệu** trong constant pool của `.class`; compiler không biến mọi tham chiếu thành địa chỉ bộ nhớ cuối cùng.
- `import` hỗ trợ phân giải tên ở mức mã nguồn; nó **không ra lệnh JVM nạp lớp** và không tự đưa dependency vào JAR.
- Generic Java phần lớn được kiểm tra rồi **xóa kiểu (type erasure)** khi biên dịch; điều này khác cơ chế class loader.

Biên dịch thành công **không bảo đảm** lớp cần thiết sẽ có mặt khi chạy, không bảo đảm kết nối mạng/đọc tệp thành công và không bảo đảm chương trình không gặp exception. Compiler kiểm tra thông tin sẵn có tại thời điểm build; runtime còn phụ thuộc phiên bản bytecode, môi trường, dữ liệu và dependency thực tế.

### Compile-time dependency và runtime dependency

Nếu mã gọi `lib.Api.run()`, `javac` cần tìm được định nghĩa phù hợp của `lib.Api` để kiểm tra kiểu. Khi chạy, JVM cũng phải tìm được lớp và method tương thích trong môi trường runtime. Vì thế một ứng dụng có thể **compile được** nhờ thư viện A nhưng **chạy lỗi** nếu thư viện A không được mang theo, thiếu dependency phụ hoặc bị thay bằng phiên bản không tương thích.

`classpath` dùng để tìm kiểu/tệp lớp trong môi trường classpath; `module path` phục vụ mô hình module của JPMS. Hai đường dẫn này là cấu hình **khác nhau**. Cùng một thư viện cũng có thể được cấu hình khác nhau cho compiler và Java launcher.

## 3. Đóng gói: gom artifact, không đồng nghĩa biên dịch

JAR là một dạng ZIP có cấu trúc quy ước để chứa `.class`, tài nguyên (ví dụ `.properties`), thư mục `META-INF/` và manifest. Công cụ `jar` **không tự chuyển `.java` thành `.class`**: thông thường ta biên dịch trước rồi gom sản phẩm, dù Gradle/Maven có thể tự gọi các task biên dịch làm dependency của task đóng gói.

Có ba cách phân phối cần phân biệt:

- **Thư mục class:** `java -cp out demo.Main`. Không có JAR nhưng vẫn cần JVM nạp lớp và thực thi.
- **Library JAR:** cung cấp lớp/tài nguyên cho chương trình khác; có thể không có entry point. Thư viện không nhất thiết chạy được với `java -jar`.
- **Executable JAR:** có thông tin entry point như `Main-Class: demo.Main` trong `META-INF/MANIFEST.MF`; `java -jar app.jar` dùng thông tin đó để tìm method `main`. Tên gọi “executable” không biến JAR thành tệp máy chạy độc lập với JVM.

**JAR không mặc nhiên chứa dependency**: một JAR “thin” thường chỉ chứa code/tài nguyên của ứng dụng. Muốn mang dependency cần cách đóng gói tương ứng (fat/uber JAR, layout riêng như Spring Boot executable JAR, hoặc phân phối nhiều JAR với classpath phù hợp). Một số công cụ đóng gói còn biến đổi hoặc ghép nội dung class; không thể kết luận mọi quy trình packaging chỉ là nén nguyên trạng.

Lưu ý: khi dùng `java -jar app.jar`, tùy chọn `-cp` / `-classpath` của Java launcher không được dùng làm user classpath cho lần chạy đó. Thư viện cần có trong cách đóng gói, trong cơ chế loader riêng hoặc trong `Class-Path` của manifest được cấu hình phù hợp. Ngược lại, `java -cp "app.jar;lib/*" demo.Main` trên Windows (dấu `:` trên Linux/macOS) dùng classpath rõ ràng và tên lớp chính, không dựa vào `Main-Class`.

## 4. Nạp lớp: đưa định nghĩa lớp vào JVM khi cần

**Class loading** không đơn giản là “mở file JAR”. JVM có thể đọc bytecode từ thư mục class, JAR, module runtime hoặc nguồn được class loader hỗ trợ. JAR là nơi lưu trữ; class loader chịu trách nhiệm tìm/định nghĩa lớp theo cơ chế của nó.

Vòng đời theo đặc tả JVM gồm ba nhóm hành vi, trong đó thời điểm chính xác có thể khác nhau giữa các JVM:

1. **Loading:** tìm biểu diễn nhị phân của lớp và tạo biểu diễn `Class` tương ứng trong JVM. JVM có bootstrap loader cho lớp nền tảng; trong các JVM Java hiện đại còn có platform và application class loaders. Class loader tùy biến có thể cung cấp nguồn bytecode khác.
2. **Linking:** gồm **verification** (kiểm tra bytecode và tính hợp lệ cấu trúc), **preparation** (cấp phát và đặt giá trị mặc định ban đầu cho static fields), và **resolution** (chuyển tham chiếu ký hiệu thành tham chiếu trực tiếp khi thích hợp). Resolution có thể thực hiện lười tại lần sử dụng, nên không phải mọi dependency đều được phân giải toàn bộ ngay lúc nạp lớp.
3. **Initialization:** chạy logic khởi tạo static của lớp (thường do compiler tổng hợp vào `<clinit>`) khi có yêu cầu khởi tạo. Ví dụ thường gặp: `new` đối tượng của lớp, gọi static method của lớp, truy cập/ghi static field không thuộc trường hợp hằng compile-time được inline, hoặc `Class.forName(name)` dạng mặc định.

**Nạp lớp ≠ khởi tạo lớp**. Chẳng hạn `Class.forName(name, false, loader)` yêu cầu tải và liên kết lớp mà không yêu cầu khởi tạo. `Class.forName(name, true, loader)` yêu cầu khởi tạo. JVM có thể nạp/liên kết sớm theo quyền triển khai nhưng phải giữ đúng hành vi khởi tạo quan sát được theo đặc tả.

Một lớp được định danh bằng **tên nhị phân cùng class loader định nghĩa nó**. Hai loader khác nhau có thể định nghĩa hai lớp trùng tên nhưng không phải cùng một kiểu trong JVM; ép kiểu giữa chúng có thể thất bại. Cơ chế ủy quyền cho parent loader giúp tái sử dụng các lớp nền tảng và giảm trùng lặp, nhưng loader tùy biến có thể có quy tắc riêng.

### Tách lỗi nạp lớp khỏi lỗi khởi tạo

| Triệu chứng | Thời điểm/ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` | API tìm lớp bằng tên (chẳng hạn `Class.forName`) không tìm được định nghĩa | Tên đầy đủ, classpath/module path, class loader được chọn |
| `NoClassDefFoundError` | JVM cần định nghĩa lớp nhưng không thể có định nghĩa khả dụng lúc đó; cũng có thể liên quan lớp khởi tạo thất bại trước đó | Dependency runtime, tên/phiên bản JAR, lỗi `Caused by` trước đó |
| `UnsupportedClassVersionError` | Bytecode có phiên bản cao hơn runtime hỗ trợ | So sánh JDK dùng để compile và Java runtime thực tế |
| `VerifyError` / `LinkageError` | Bytecode không hợp lệ hoặc có vấn đề liên kết/tương thích nhị phân | Artifact bị hỏng, thư viện không tương thích, trùng lớp |
| `ExceptionInInitializerError` | Static initialization ném exception không được xử lý | Khối `static`, static field initializer và nguyên nhân gốc |

Không đồng nhất `ClassNotFoundException` (checked exception từ một số API tìm lớp) với `NoClassDefFoundError` (một `Error` của JVM). Một lỗi runtime có thể phát sinh **trước khi dòng code mong đợi được thực thi**, vì JVM còn phải liên kết/khởi tạo lớp cần thiết.

## 5. Thực thi: chạy bytecode và thực hiện nghiệp vụ

Java launcher tạo môi trường JVM, chọn lớp/chương trình khởi đầu và gọi điểm vào phù hợp. Với chương trình classpath truyền thống, đó thường là `public static void main(String[] args)`. Trong quá trình hoạt động, JVM thực thi bytecode; một JVM như HotSpot có thể **thông dịch** và sau đó **JIT compile** những đoạn code đủ “nóng” thành mã máy để tăng hiệu năng.

**JIT compilation không phải `javac`**:

- `javac` chạy trong bước build, chuyển **mã nguồn Java → bytecode** và tạo `.class`.
- JIT chạy trong JVM khi chương trình hoạt động, có thể chuyển **bytecode → mã máy đã tối ưu** theo thông tin runtime; không có cam kết rằng một method cụ thể sẽ được JIT trong một lần chạy ngắn.
- Chương trình vẫn có thể thực thi đúng dù không được JIT. Kết quả nghiệp vụ không được phụ thuộc vào việc có JIT hay không.

Lúc chạy có thể phát sinh I/O, tạo thread, cấp phát đối tượng, gọi thư viện, truy cập database, ném exception hoặc sai logic. Những hiện tượng này thường không thể suy ra chỉ từ việc compile/package thành công.

## 6. Thí nghiệm trọn quy trình (JDK 17+)

Ví dụ sau phân biệt **nạp/lấy metadata của lớp** với **khởi tạo static**, sau đó cho thấy cùng một bytecode có thể chạy từ thư mục `out` hoặc từ JAR. Tạo đúng hai tệp mã nguồn:

**Tệp `src/demo/Main.java`**

~~~java
package demo;

public final class Main {
    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("1. main()");

        ClassLoader loader = Main.class.getClassLoader();
        Class<?> type = Class.forName("demo.Marker", false, loader);
        System.out.println("2. loaded: " + type.getSimpleName());

        Class.forName("demo.Marker", true, loader);
        System.out.println("4. initialized");

        Marker.run();
    }
}
~~~

**Tệp `src/demo/Marker.java`**

~~~java
package demo;

public final class Marker {
    static {
        System.out.println("3. Marker.<clinit>");
    }

    public static void run() {
        System.out.println("5. Marker.run()");
    }
}
~~~

### Bước A — Biên dịch

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/demo/Main.java src/demo/Marker.java
~~~

Kết quả là `out/demo/Main.class` và `out/demo/Marker.class`. **Chưa có lệnh chạy chương trình**, vì thế chưa in năm dòng từ `System.out.println`. Nếu `javac` báo lỗi, sửa lỗi mã nguồn trước khi nghĩ đến JAR hoặc class loader.

### Bước B — Chạy trực tiếp từ thư mục class

~~~bash
java -cp out demo.Main
~~~

**Stdout dự kiến, theo đúng thứ tự:**

~~~text
1. main()
2. loaded: Marker
3. Marker.<clinit>
4. initialized
5. Marker.run()
~~~

Giải thích từng dòng:

1. JVM đã có thể khởi chạy `demo.Main.main`; đây là code đang **thực thi**.
2. `Class.forName("demo.Marker", false, loader)` trả về đối tượng `Class` mà không yêu cầu chạy static initializer của `Marker`. Cụm “loaded” là nhãn minh họa: lớp được yêu cầu tải và liên kết, chứ không chứng minh toàn bộ hệ thống chỉ bắt đầu loading tại dòng này.
3. Lời gọi `Class.forName(..., true, ...)` yêu cầu khởi tạo `Marker`, nên khối `static` in `3. Marker.<clinit>` **trước khi** lời gọi trả về.
4. Sau khi khởi tạo xong, `Main` in `4. initialized`.
5. Lời gọi `Marker.run()` in dòng cuối. Gọi static method cũng là một kiểu active use có thể kích hoạt khởi tạo nếu lớp chưa được khởi tạo trước đó.

### Bước C — Đóng gói và chạy lại

~~~bash
jar --create --file app.jar --main-class demo.Main -C out .
jar --list --file app.jar
java -jar app.jar
~~~

Lệnh `jar --create` lấy các file đã compile từ `out` và tạo `app.jar` với entry point `demo.Main` trong manifest. `jar --list` cho phép kiểm tra các entry như `demo/Main.class`, `demo/Marker.class` và `META-INF/MANIFEST.MF`. Lệnh `java -jar app.jar` cho **cùng năm dòng stdout** ở bước B. Sự giống nhau của kết quả minh họa: **packaging thay đổi cách phân phối/khởi chạy artifact, không tự thay đổi chức năng Java** trong ví dụ này.

**Đối chiếu artifact:**

| Sau lệnh | Quan sát cần kiểm chứng | Điều chưa được chứng minh |
| --- | --- | --- |
| `javac ...` | Có `Main.class` và `Marker.class` | Chưa chứng minh ứng dụng chạy đúng |
| `jar --create ...` | Có `app.jar`, class và manifest | Chưa chứng minh mọi runtime dependency đều đủ |
| `java -cp out demo.Main` | In đủ năm dòng | Không cần JAR |
| `java -jar app.jar` | In đủ năm dòng | JAR vẫn cần Java runtime để thực thi |

**Lưu ý về terminal:** `mkdir out` và các lệnh `javac`/`jar`/`java` đều có thể dùng trong PowerShell hoặc shell Unix khi chạy tại thư mục gốc chứa `src/demo/`. Nếu `out` đã tồn tại, bỏ qua bước `mkdir`. Dấu phân cách danh sách classpath khác nhau theo hệ điều hành chỉ trở thành vấn đề khi dùng **nhiều** thư mục/JAR; ví dụ này dùng một `out` duy nhất.

## 7. Cách xác định lỗi thuộc giai đoạn nào

Khi điều tra, hãy đọc **lệnh đang thất bại và stack trace thực tế**, không suy đoán từ từ “Java error”.

| Hiện tượng | Kiểm tra đầu tiên | Giai đoạn gần nhất |
| --- | --- | --- |
| `javac`: `';' expected`, `cannot find symbol`, `incompatible types` | Cú pháp, tên, kiểu, `-cp` của compiler | Biên dịch |
| Build tạo JAR nhưng `java -jar` báo `no main manifest attribute` | Có entry `Main-Class` đúng chưa | Đóng gói/cấu hình entry point |
| `java -jar` không tìm thấy dependency lúc chạy | Đã đóng kèm/phân phối dependency và cấu hình loader/classpath phù hợp chưa | Nạp lớp/liên kết |
| `UnsupportedClassVersionError` | JDK compiler phát ra class-file version nào, JVM chạy phiên bản nào | Nạp/liên kết |
| `ExceptionInInitializerError` | Logic static initializer và `Caused by` | Khởi tạo lớp |
| `NullPointerException` bên trong `main`, sai giá trị tính toán, timeout | Call stack, dữ liệu, nhánh code, tài nguyên runtime | Thực thi |

**Quy trình chẩn đoán ngắn:**

1. Ghi lại lệnh đang chạy (`javac`, `jar`, `java` hoặc task build) cùng lỗi **đầu tiên có ý nghĩa**.
2. Nếu lỗi biên dịch, xử lý thông báo `javac` và classpath/module path của compiler.
3. Nếu đã có JAR, kiểm tra nội dung/manifest bằng `jar --list --file app.jar`; có thể xem manifest bằng công cụ ZIP khi cần.
4. Nếu lỗi xuất hiện khi khởi chạy hoặc gọi một lớp, kiểm tra Java runtime thực tế bằng `java -version`, classpath/module path và chuỗi nguyên nhân `Caused by`.
5. Nếu chương trình đã vào nghiệp vụ, debug call stack, trạng thái và dữ liệu; không mặc định đổi cấu hình đóng gói để “chữa” mọi lỗi runtime.

Một số lỗi **không gói gọn trong một ranh giới tuyệt đối**: ví dụ thiếu thư viện có thể được phát hiện ngay khi khởi động hoặc mãi khi một đường chạy lần đầu sử dụng lớp đó; nhiều lỗi liên kết chỉ lộ ra theo thời điểm JVM resolve tham chiếu.

## 8. Những nhầm lẫn cần tránh

- **“Compile xong là chạy được.”** Sai: cần runtime tương thích, các lớp/tài nguyên thích hợp và dữ liệu hợp lệ.
- **“Có JAR là có đầy đủ dependency.”** Sai: cần kiểm tra cách đóng gói và môi trường triển khai.
- **“Load class nghĩa là đã chạy khối static.”** Sai: loading, linking và initialization là các bước phân biệt; ví dụ `Class.forName` với tham số `initialize=false` minh họa rõ điều này.
- **“JAR là mã máy.”** Sai: JAR Java thông thường chứa bytecode và tài nguyên; JVM thực thi bytecode, có thể dùng JIT. Native image là một kiểu sản phẩm khác, với quy trình build khác.
- **“JIT chính là javac.”** Sai: chúng khác đầu vào, thời điểm, mục đích và nơi hoạt động.
- **“Không có `import` thì JVM không tìm được lớp.”** Sai: `import` chỉ là quy tắc đặt tên trong source; runtime dựa vào class loader, classpath/module path, tên nhị phân và dependency thực tế.
- **“JVM tải tất cả lớp trong JAR trước khi gọi main.”** Sai: lớp có thể được nạp, liên kết, khởi tạo theo nhu cầu; thời điểm chi tiết phụ thuộc các yêu cầu hợp lệ và triển khai.

## 9. Tự kiểm tra

1. **Có thể chạy chương trình Java mà không đóng JAR không?** Có. Nếu `out` chứa lớp phù hợp và dependency khả dụng, dùng `java -cp out demo.Main`.
2. **Tạo JAR có tự sửa lỗi `cannot find symbol` không?** Không. Đây là lỗi biên dịch; cần sửa source/cấu hình dependency cho compiler.
3. **Vì sao `Class.forName(name, false, loader)` chưa in dòng trong khối `static`?** Vì yêu cầu load/link không đồng nghĩa yêu cầu initialization.
4. **Ứng dụng compile thành công nhưng chạy báo `NoClassDefFoundError` thì nhìn đâu?** Kiểm tra lớp/dependency ở runtime, class loader, phiên bản artifact và nguyên nhân gốc; không kết luận mã nguồn sai cú pháp.
5. **Cùng một JAR có thể chạy khác nhau giữa hai môi trường không?** Có: khác JVM, cấu hình dependency, system properties, biến môi trường, tài nguyên, dữ liệu, OS, permission và điều kiện runtime.
6. **Khi nào JIT chạy?** Do JVM quyết định dựa trên chính sách tối ưu và hoạt động khi runtime; không phải điều kiện bắt buộc để code có thể chạy đúng.

**Ghi nhớ một câu:** `javac` **tạo bytecode**; `jar` **đóng gói artifact**; class loader cùng JVM **định nghĩa, liên kết và khởi tạo lớp khi cần**; JVM **thực thi bytecode** để tạo ra hành vi quan sát được.
