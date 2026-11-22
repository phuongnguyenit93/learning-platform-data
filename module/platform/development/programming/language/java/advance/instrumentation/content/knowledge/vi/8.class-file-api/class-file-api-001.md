# java.lang.classfile là API chính thức từ JDK 24 và yêu cầu tương thích phiên bản

## 1. Mục tiêu và vấn đề cần giải quyết

Từ **JDK 24**, `java.lang.classfile` là **Class-File API chính thức (standard API)** của nền tảng Java, phục vụ **đọc, phân tích, tạo và biến đổi bytecode `.class`**. Với instrumentation, API này có thể làm phần việc **xử lý bytecode** mà trước đây nhiều dự án phải dùng thư viện như ASM/Byte Buddy hoặc các API nội bộ JDK.

Tuy nhiên, “API chính thức từ JDK 24” **không có nghĩa** mã sử dụng nó chạy được trên JVM 17/21, cũng không có nghĩa bất cứ bytecode nào nó tạo ra đều chạy trên các JVM cũ. Để chọn đúng công nghệ, cần tách ba câu hỏi:

1. **JDK nào biên dịch và chạy mã công cụ/agent?** Mã `import java.lang.classfile.*` cần **API tồn tại khi biên dịch và lúc chạy**: với API đã chính thức, mục tiêu tối thiểu là JDK 24.
2. **`.class` đang đọc hoặc tạo có định dạng phiên bản nào?** Class file có `major_version` và `minor_version` riêng, độc lập với phiên bản của tool đang chạy.
3. **JVM đích sẽ chạy bytecode nào?** JVM phải hỗ trợ class-file version và các tính năng/đường phụ thuộc thực sự dùng trong bytecode đó.

Sau bài, bạn sẽ biết mốc preview và chính thức, phân biệt **JDK API compatibility** với **class-file format compatibility**, tự chạy một ví dụ **tool JDK 24 đọc class Java 17**, kiểm tra version bằng `javap` và chọn chiến lược phát hành agent/tool cho nhiều phiên bản JVM.

## 2. Mốc phát triển: preview trước, chính thức từ JDK 24

| Phiên bản JDK | Trạng thái Class-File API | Điều cần nhớ |
|---|---|---|
| **17 và 21** | Chưa có `java.lang.classfile` như standard API | Không thể biên dịch source dùng package này với `--release 17` hoặc `--release 21` |
| **22** | **Preview lần 1**, JEP 457 | API trong giai đoạn thử nghiệm; cần chú ý cấu hình preview và sự thay đổi hợp đồng |
| **23** | **Preview lần 2**, JEP 466 | Tiếp tục thử nghiệm, có thay đổi so với 22; không coi source preview tương thích tuyệt đối |
| **24** | **Final/standard**, JEP 484 | `java.lang.classfile` thuộc API Java SE 24, không cần `--enable-preview` cho riêng API này |
| **25 và các JDK mới hơn có cung cấp API** | Tiếp tục là API nền tảng | Kiểm tra Javadoc và runtime của phiên bản thực tế khi dùng tính năng/phương thức mới |

**“Được final ở 24” không có nghĩa một mã dựa vào preview 22/23 có thể được giữ nguyên và chạy trên 24.** Khi nâng phiên bản, phải biên dịch lại và kiểm tra những tên lớp, chữ ký, behavior đã thay đổi. Ngoài ra, **preview API** và **preview language feature** là hai khái niệm khác nhau: không nên dựa vào ký hiệu phiên bản `.class` để tự suy ra rằng tool có đang sử dụng Class-File API preview hay không.

API chính thức được công bố tại **JEP 484**. Nó gồm các package:

- `java.lang.classfile`: cấu trúc, model, builder, transformation, verification;
- `java.lang.classfile.attribute`: các cấu trúc attribute của class/method/field;
- `java.lang.classfile.constantpool`: constant-pool entries và builder;
- `java.lang.classfile.instruction`: mô hình instruction/bytecode.

Chúng nằm trong module **`java.base`**. Trên JDK 24, không cần thêm một dependency Maven riêng, không cần `--add-exports` để truy cập API công khai, và không cần `--enable-preview` chỉ vì import `java.lang.classfile`. Một ứng dụng Java modular cũng không cần ghi `requires java.base` vì `java.base` là dependency ngầm định.

## 3. Class-File API làm gì trong instrumentation?

Phân biệt **xử lý bytecode** và **gắn vào JVM**:

~~~text
                           Java agent / instrumentation
                        -----------------------------------
JVM gặp class khi load  ---> ClassFileTransformer.transform(...)
                                      |
                                      v
                              byte[] classfileBuffer
                                      |
                           +----------+----------+
                           | Class-File API (24+) |
                           | parse -> model       |
                           | transform / build    |
                           | verify -> byte[]     |
                           +----------+----------+
                                      |
                   return transformed bytes, hoặc null nếu bỏ qua
                                      |
                                      v
                         JVM kiểm tra và định nghĩa lớp
~~~

**Class-File API không tự đóng vai trò Attach API hoặc Instrumentation API.** Nó không tự nạp class vào JVM, không cung cấp `premain/agentmain`, và không tự đăng ký transformer. Agent vẫn cần module `java.instrument` và `Instrumentation.addTransformer`/`retransformClasses` hoặc cơ chế thay thế phù hợp.

Các thành phần quan trọng:

| API | Vai trò |
|---|---|
| `ClassFile.of()` | Tạo context mặc định để đọc/ghi/biến đổi class file |
| `ClassFile.parse(byte[])` hoặc `parse(Path)` | Đọc class bytes thành `ClassModel` |
| `ClassModel` | Mô hình class: tên, version, fields, methods, attributes, constant pool |
| `ClassFile.build(...)` | Sinh class bytes từ builder |
| `ClassFile.transformClass(ClassModel, ClassTransform)` | Tạo class bytes mới bằng cách xử lý các `ClassElement` của model |
| `ClassTransform.ACCEPT_ALL` | Chuyển tất cả elements theo pipeline, **không chèn probe mới** |
| `ClassFile.verify(...)` | Trả về danh sách lỗi kiểm tra class-file theo API |
| `ClassFile.latestMajorVersion()` | Major class-file cao nhất được runtime đang dùng hỗ trợ |

**`ClassModel` là mô hình bất biến và phân tích lười (lazy).** Gọi `parse` thành công không có nghĩa mọi attribute/instruction trong file đã được kiểm tra. Một accessor gọi sau vẫn có thể ném `IllegalArgumentException` khi gặp cấu trúc sai hoặc không được hỗ trợ. Khi dùng song song, đừng tự giả định mọi model lazy đều an toàn để chia sẻ đồng thời.

### Vì sao hữu ích cho instrumentation?

Khi cần ghi thời gian thực thi một method, một tool thường phải phân tích phần `Code`, tạo instruction gọi probe, điều chỉnh luồng exception, frame, constant pool rồi sinh class mới. API chuẩn giúp biểu diễn những cấu trúc đó thành model/builder có kiểu rõ ràng. Dù vậy, **tạo được bytes không tự bảo đảm chúng hợp lệ cho mọi JVM**; vẫn phải xác nhận version, bytecode verification, hạn chế redefinition/retransformation và các ràng buộc module/class loader.

## 4. Tách ba phiên bản để tránh kết luận sai

Hãy xem ba đối tượng trong cùng một dự án:

~~~text
(1) Tool biên dịch bằng JDK 24
    ClassFileApiDemo.class ------ major 68, tham chiếu java.lang.classfile
                                      |
                                      | đọc / biến đổi
                                      v
(2) Class ứng dụng biên dịch --release 17
    demo/Greeter.class ---------- major 61
                                      |
                                      | chạy trên JVM tương thích
                                      v
(3) Runtime đích Java 17 ------ hỗ trợ class-file major 61
~~~

**Tool chạy trên JDK 24 vẫn có thể phân tích và tạo bytecode tương thích Java 17.** Ngược lại, **tool đó không tự chạy trên Java 17** vì class tool được biên dịch cho Java 24 và phụ thuộc `java.lang.classfile` vốn không có trong Java 17.

Bảng major class-file thường gặp:

| Java release | Major version của class file |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| **Java 24** | **68** |
| Java 25 | 69 |

Thông thường, Java release mới đọc/chạy classfile của release cũ hơn trong phạm vi JVM hỗ trợ, còn JVM cũ **không thể nạp classfile có major cao hơn mức nó hiểu**. Ví dụ Java 17 không thể nạp class major 68, thường báo `UnsupportedClassVersionError`.

Đây mới là **class-file format compatibility**. Ngoài major version, phải tính đến:

- **APIs được mã Java tham chiếu:** class major 61 có thể vẫn không chạy Java 17 nếu bị biên dịch với cờ không kiểm soát và tham chiếu API chỉ tồn tại từ Java 24; lỗi có thể là `NoClassDefFoundError`, `ClassNotFoundException` hoặc `NoSuchMethodError`.
- **Preview classfile:** từ các release hỗ trợ preview, minor version `65535` gắn với class dùng preview và có quy tắc riêng; nó không đơn giản là classfile cũ được phép chạy trên mọi JDK mới.
- **Class loader, module access và bytecode verifier:** class có major được hỗ trợ vẫn có thể không chạy nếu cấu trúc, liên kết hoặc quyền truy cập không hợp lệ.
- **Agent cùng JVM:** agent dùng Class-File API standard phải có runtime Java 24+, cho dù **ứng dụng mà nó nhắm tới** chỉ dùng source/bytecode Java 17.

## 5. Ví dụ Java 24 phân tích một class được biên dịch cho Java 17

Ví dụ này tách **class cần phân tích** và **tool phân tích** thành hai output. Đây là cách kiểm chứng đúng nhất cho thông điệp của bài: **JDK chạy API có thể mới hơn classfile được xử lý**.

### 5.1. Cây thư mục

~~~text
classfile-version-lab/
├── src/
│   ├── demo/
│   │   └── Greeter.java
│   └── ClassFileApiDemo.java
├── out17/                    # Sinh khi build: class Java 17
├── out24/                    # Sinh khi build: class tool Java 24
└── outCopy/                  # Sinh khi chạy tool: class được viết lại
~~~

Các thư mục `out*` chứa kết quả build/thử nghiệm. Hai file `.java` bên dưới là **chương trình Java đầy đủ**, có thể biên dịch và chạy độc lập theo các lệnh sẽ nêu.

### 5.2. Class ứng dụng: Greeter.java

Lưu tại **`src/demo/Greeter.java`**:

~~~java
package demo;

public final class Greeter {
    public static void main(String[] args) {
        System.out.println("Hello from Java 17 bytecode");
    }
}
~~~

Mã cố ý chỉ dùng tính năng Java 17 (thực tế còn đơn giản hơn) để khi biên dịch với `--release 17`, ta có class version **61** và không phụ thuộc API Java 24.

### 5.3. Tool dùng Java Class-File API

Lưu tại **`src/ClassFileApiDemo.java`**:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.nio.file.Files;
import java.nio.file.Path;

public class ClassFileApiDemo {
    public static void main(String[] args) throws Exception {
        ClassFile api = ClassFile.of();
        ClassModel model = api.parse(Path.of(args[0]));

        System.out.println(
                "name=" + model.thisClass().name().stringValue());
        System.out.println("class-major=" + model.majorVersion());
        System.out.println("class-minor=" + model.minorVersion());
        System.out.println(
                "jdk-major=" + ClassFile.latestMajorVersion());
        System.out.println(
                "methods=" + model.methods().stream()
                        .map(m -> m.methodName().stringValue())
                        .sorted()
                        .toList());

        // Đi qua pipeline transform mà không thêm probe/sửa logic.
        byte[] copy = api.transformClass(
                model, ClassTransform.ACCEPT_ALL);

        System.out.println(
                "transformed-major=" + api.parse(copy).majorVersion());
        System.out.println(
                "verify-errors=" + api.verify(copy).size());

        Path output = Path.of("outCopy", "demo", "Greeter.class");
        Files.createDirectories(output.getParent());
        Files.write(output, copy);
    }
}
~~~

**Giải thích API và ý nghĩa số liệu:**

- `api.parse(Path.of(args[0]))` mở file `.class` và tạo `ClassModel`; không chạy method trong class đó.
- `model.thisClass().name().stringValue()` đọc tên JVM nội bộ như `demo/Greeter`.
- `majorVersion()`/`minorVersion()` là **version của file đang phân tích**, không phải version của JDK chạy tool.
- `ClassFile.latestMajorVersion()` là version cao nhất của class file mà **JDK tool đang chạy** nhận biết; trên **JDK 24 là 68**.
- `model.methods()` liệt kê cả constructor `<init>` ở dạng method trong class file và `main`; `sorted()` giữ output ổn định.
- `ClassTransform.ACCEPT_ALL` chuyển các phần tử class qua pipeline, **không làm chức năng instrumentation**. Byte array tạo ra có thể khác ở mức byte vì quá trình ghi/attribute xử lý; không giả định bằng bit với input.
- `api.verify(copy).size()` đếm vấn đề được Class-File API phát hiện. **Zero không chứng minh một class chắc chắn link/run được trên mọi JVM**, nhưng là một kiểm tra cấu trúc hữu ích.
- `Files.write` tạo một classfile đầu ra theo đúng đường dẫn package; câu lệnh không làm JVM đích tự cập nhật class đã load.

### 5.4. Biên dịch

Kiểm tra terminal trỏ tới JDK 24:

~~~bash
java -version
javac -version
~~~

Trong Bash (Linux/macOS), tạo thư mục:

~~~bash
mkdir -p out17 out24 outCopy
~~~

Trong PowerShell (Windows):

~~~powershell
New-Item -ItemType Directory -Force out17, out24, outCopy
~~~

Sau đó các lệnh sau tương thích Bash và PowerShell. **Chạy bằng bộ công cụ JDK 24** từ thư mục gốc bài:

~~~bash
javac --release 17 -d out17 src/demo/Greeter.java
javac --release 24 -d out24 src/ClassFileApiDemo.java
~~~

Tại đây có **hai mục tiêu biên dịch**:

- `Greeter.java` chọn `--release 17`: classfile và API target Java 17; không cần JDK 17 riêng khi compiler hiện tại là JDK 24.
- `ClassFileApiDemo.java` chọn `--release 24`: compiler cho phép import Class-File API chính thức và tạo tool có class-file major 68; **runtime chạy tool phải tương thích JDK 24**.

### 5.5. Chạy tool phân tích và class được tạo ra

~~~bash
java -cp out24 ClassFileApiDemo out17/demo/Greeter.class
~~~

**Stdout dự kiến trên JDK 24** với đúng hai source ở trên:

~~~text
name=demo/Greeter
class-major=61
class-minor=0
jdk-major=68
methods=[<init>, main]
transformed-major=61
verify-errors=0
~~~

Dòng `class-major=61` và `transformed-major=61` quan trọng hơn con số “tool chạy JDK 24”: **class được xử lý vẫn là classfile Java 17**. Không thêm bất kỳ instruction Java 24 nào vào output.

Chạy class đầu ra:

~~~bash
java -cp outCopy demo.Greeter
~~~

Stdout:

~~~text
Hello from Java 17 bytecode
~~~

Điều này kiểm tra semantic behavior của phép transform “accept all” đối với class ví dụ. Tool phân tích chạy trên JDK 24, còn **class đầu ra mang major 61**. Nếu thực sự cần chứng minh chạy trên JVM 17, dùng thêm **`java` của JDK 17** để chạy `outCopy` trong môi trường kiểm thử; kiểm tra trên JDK 24 một mình không thay thế thử nghiệm tương thích runtime cũ.

## 6. Đối chứng: tool không thể vừa dùng API JDK 24 vừa compile cho Java 17

Hãy thử (không cần sửa source):

~~~bash
javac --release 17 -d out24 src/ClassFileApiDemo.java
~~~

Kết quả **không biên dịch thành công** vì API `java.lang.classfile` không tồn tại trong API của Java 17. Thông báo thường bao gồm:

~~~text
error: package java.lang.classfile does not exist
~~~

Đây là kiểm tra **source/API compatibility**, không liên quan việc `ClassFileApiDemo` có đang phân tích một class Java 17 hay không.

### 6.1. Vì sao nên dùng --release?

Với compiler JDK 24:

- `--release 17` áp dụng đồng thời quy tắc ngôn ngữ, target classfile và **API hệ thống được phép tham chiếu** theo Java 17.
- Chỉ dùng `-source 17 -target 17` đặt mức ngôn ngữ và classfile target, **không bảo đảm chặn mọi API của JDK hiện tại**. Có thể tạo một classfile mang major 61 nhưng tham chiếu class/method JDK 24 và gây lỗi lúc chạy trên JDK 17.
- `--release 24` cho phép dùng `java.lang.classfile` với bộ công cụ JDK 24; artifact sử dụng API này phải chạy trên runtime có API tương ứng.

**Không thể dùng `--release 17` làm “hạ cấp” package Java 24 thành package có sẵn trên Java 17.** Tương thích bytecode format và tính sẵn có của API là hai hợp đồng riêng.

### 6.2. Kiểm tra major của file thật

Chạy với bộ công cụ JDK:

~~~bash
javap -verbose -classpath out17 demo.Greeter
javap -verbose -classpath out24 ClassFileApiDemo
~~~

Trong output của lệnh thứ nhất, tìm:

~~~text
major version: 61
~~~

Trong output của lệnh thứ hai, tìm:

~~~text
major version: 68
~~~

`javap` đọc file thực tế, không chỉ đọc cấu hình build. Đây là kiểm tra hữu ích nếu repository có nhiều toolchain và máy build có nhiều JDK.

## 7. Khi ứng dụng và agent cần chạy trên những JDK khác nhau

Đây là rủi ro lớn nhất trong module instrumentation: **agent được nạp vào chính JVM đích**. Nếu JVM đích là Java 17 thì mọi class agent cần nạp phải tương thích với nó; agent không thể dùng Class-File API chuẩn của Java 24 ngay trong process Java 17.

| Kịch bản | Có thể dùng trực tiếp `java.lang.classfile` trong process đó? | Cách xử lý |
|---|---|---|
| Tool CLI chạy riêng trên **JDK 24**, phân tích class Java 17 | **Có** | Tool biên dịch `--release 24`; input/output class giữ target phù hợp |
| Startup Java agent chạy bên trong **JVM 24** | **Có** | Agent dùng Java 24 API, vẫn kiểm tra bytecode biến đổi, manifest và transformer |
| Attach agent vào **JVM 24** | **Có**, nếu attach được hỗ trợ | Mã agent nạp trong JVM 24, kiểm tra quyền dynamic loading/retransform |
| Agent nạp vào **JVM 17 hoặc 21** | **Không** với API standard này | Dùng parser/rewriter tương thích JDK đích, hoặc nâng runtime đích |
| App Java 17 nhưng chạy trên **JVM 24** | **Có**, vì JVM đang chạy là 24 | Chọn classfile target của app/agent đúng; kiểm tra framework và instrumentation |
| Biên dịch tool bằng JDK 24 với `--release 17` | **Không** | Tách tool Java 24 khỏi module Java 17 hoặc bỏ phụ thuộc API này |

**Mấu chốt:** “Ứng dụng viết bằng Java 17” chưa nói đủ. Cần hỏi nó thực tế **chạy trong JVM 17 hay JVM 24**. Một ứng dụng có source Java 17 chạy trong JVM 24 có thể được agent JDK 24 instrument; một ứng dụng Java 17 chạy trong JVM 17 thì agent tham chiếu `java.lang.classfile` không thể được nạp.

### 7.1. Những chiến lược tương thích thực tế

**Chiến lược A — công cụ offline JDK 24:** Chạy một tool JDK 24 riêng trong pipeline build, dùng Class-File API phân tích/transform class target Java 17 và kiểm tra output major 61. Đưa **class output**, không đưa **tool Java 24**, vào artifact chạy JVM 17. Phải bảo đảm class output không tham chiếu API hoặc bytecode chỉ hỗ trợ trên Java 24.

**Chiến lược B — agent phải chạy JVM 17:** Biên dịch agent với `--release 17` và chọn bộ thư viện bytecode có hỗ trợ Java 17. ASM/Byte Buddy là các lựa chọn phổ biến; phiên bản thư viện cũng phải hỗ trợ classfile được yêu cầu. Không import `java.lang.classfile` trong phần agent sẽ nạp trên JVM 17.

**Chiến lược C — yêu cầu runtime từ JDK 24:** Nếu hệ thống có thể nâng cấp, công bố **minimum runtime JDK 24** cho agent và ứng dụng liên quan, build/test đầy đủ. Đừng đưa cấu hình đó vào môi trường chỉ có JDK 17/21.

**Chiến lược D — nhiều hiện vật/nhánh triển khai:** Cung cấp agent/tool riêng theo dải JDK hoặc dùng *multi-release JAR* đúng cấu trúc nếu thật sự cần. Với multi-release JAR, entry base phải chạy được trên JDK cũ, entry `META-INF/versions/24` chỉ được dùng trên JDK tương ứng, manifest có `Multi-Release: true` và phải tránh mọi liên kết sớm từ nhánh cũ tới `java.lang.classfile`. Multi-release JAR **không biến API 24 thành API của JVM 17**.

Đối với một thư viện/agent nhiều khách hàng, cách phát hành nhiều artifact theo phiên bản có thể đơn giản và dễ kiểm thử hơn logic điều kiện JDK phức tạp trong cùng một JAR.

## 8. Sử dụng Class-File API bên trong ClassFileTransformer

Một `ClassFileTransformer` có callback:

~~~java
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
~~~

**Chữ ký trên là trích đoạn minh họa**, không phải lớp hoàn chỉnh; trong thực tế cần triển khai interface và các import phù hợp.

Trên **JVM 24+**, callback có thể dùng `ClassFile.of().parse(classfileBuffer)`, đọc `ClassModel`, biến đổi qua `ClassTransform` rồi trả `byte[]` mới. Tuy nhiên:

1. Chỉ xử lý class thuộc phạm vi cần instrument; phân biệt `className` dạng nội bộ như `demo/Greeter` và tên Java dạng `demo.Greeter`.
2. API có thể phát hiện input classfile sai hoặc **classfile version mới hơn runtime/tool**; `parse` hoặc model accessor có thể ném `IllegalArgumentException`. Đừng trả bytes không hợp lệ.
3. Nếu không cần thay đổi, theo hợp đồng transformer hãy trả **`null`**. Chỉ trả output của `transformClass` khi có chủ ý phát hành bytes đã được xác nhận.
4. Không sửa trực tiếp mảng `classfileBuffer`; nếu cần thay đổi phải tạo bytes mới hợp lệ.
5. Khi inject method call/field access, bảo đảm helper class thực sự tồn tại và JVM có thể nạp qua class loader/module phù hợp.
6. Với retransformation, các hạn chế đổi schema và bytecode đang thực thi vẫn có hiệu lực; API chuẩn không xóa các giới hạn của `Instrumentation`.
7. Thử nghiệm trên đúng JVM đích với class loader, framework và mô-đun thực tế, vì việc `verify` của API trả ít lỗi không thay thế được linkage/runtime tests.

### 8.1. Ví dụ logic điều kiện (không phải transformer độc lập)

~~~java
if (!"demo/Greeter".equals(className)) {
    return null;
}

try {
    ClassFile api = ClassFile.of();
    ClassModel model = api.parse(classfileBuffer);

    // Phân tích model để quyết định có thực sự cần chèn probe.
    // Nếu chưa có một phép transform hợp lệ thì bỏ qua.
    return null;
} catch (IllegalArgumentException badClass) {
    // Ghi lỗi có giới hạn và không trả mảng classfile hỏng.
    return null;
}
~~~

Đoạn này cần nằm trong method transformer có sẵn, với biến `className` và `classfileBuffer` trong scope, và import `java.lang.classfile.*`. **Nó không chèn bất kỳ probe nào.** Việc cố ý trả `null` thể hiện ranh giới giữa *phân tích class* và *instrument class*.

Nếu code dựa trên JDK 24 phải chạy trong agent thật, hãy kiểm tra runtime JVM đích **trước khi chọn cách biên dịch/phát hành**. Đừng cố sửa lỗi thiếu API bằng cách thêm `--add-exports`: package public `java.lang.classfile` **đơn giản không tồn tại trên Java 17/21**.

## 9. Đọc class file và xác định version trước khi xử lý

Ở đầu mọi classfile có magic number `CAFEBABE`, tiếp đến `minor_version` rồi `major_version`. Vì vậy, một công cụ có thể đọc header để biết version **trước khi** đưa bytes vào parser phiên bản nhất định:

~~~text
Offset (byte)   Nội dung
0..3            0xCAFEBABE  (magic)
4..5            minor_version (u2, big-endian)
6..7            major_version (u2, big-endian)
8..             constant_pool_count và nội dung còn lại
~~~

Ví dụ Java 17 thường có major `61`, minor `0`; Java 24 thường có major `68`, minor `0` nếu không dùng preview feature. **Đừng suy rằng mọi minor khác 0 đều lỗi:** preview classfile có quy tắc đặc biệt, đặc biệt `65535`.

Trong tool Java 24, dùng `ClassFile.latestMajorVersion()` để biết phiên bản tối đa mà runtime hỗ trợ. Đối với file có major lớn hơn, đừng ép parse rồi kỳ vọng công cụ sẽ hiểu các instruction/attribute tương lai. `ClassFile.parse` có thể ném `IllegalArgumentException` nếu classfile sai định dạng hoặc dùng version không hỗ trợ. Vì model lazy, lỗi có thể xảy ra cả ở accessor gọi sau.

**Đọc và biến đổi class cũ không tự động làm nó thành class mới.** Lệnh `transformClass` có thể giữ major của model đầu vào. Nếu chủ động tạo class mới bằng `build` hoặc sử dụng tính năng mới, **phải xác minh output major** và bytecode instruction/attribute trước khi phát hành. Không sửa hai byte version trong header để “hạ cấp” class file: bytecode có thể sử dụng cấu trúc mà JVM cũ không hỗ trợ.

## 10. Tích hợp build và kiểm thử trong dự án thực

### 10.1. Java toolchain trong Gradle

Với một **project riêng** dành cho tool/agent chạy JDK 24, ví dụ Groovy DSL `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 24
}
~~~

Đoạn này lựa chọn compiler Java 24 cho source của project đó. Nó **không tự làm các module Java 17 khác chuyển lên 24**; với repository nhiều module, cấu hình toolchain/release theo từng module đúng chủ đích.

Sử dụng Gradle Wrapper phiên bản có khả năng chạy/quản lý toolchain JDK 24 phù hợp. **Gradle runtime compatibility** và **Java toolchain support** là hai khái niệm khác nhau; kiểm tra [Gradle Java compatibility](https://docs.gradle.org/current/userguide/compatibility.html) theo **phiên bản wrapper thực tế** trước khi nâng. Java 24 tool có thể tồn tại song song với app Java 17 nhưng cần tách artifact và môi trường kiểm thử.

### 10.2. Ma trận kiểm thử nên có

| Lớp kiểm thử | Bài kiểm tra | Ý nghĩa |
|---|---|---|
| Compiler/API | Build tool với JDK 24, `--release 24` | API public `java.lang.classfile` được nhìn thấy |
| Negative compile | Thử build cùng source tool với `--release 17` | Chứng minh Java 17 API surface không chứa package |
| Class file input | `javap -verbose` trên app Java 17 | Xác nhận input major 61 |
| Model/parser | `ClassFile.of().parse` và đọc fields/methods | Kiểm tra parser đủ hiểu format đầu vào |
| Transformation | `transformClass` + `verify` | Kiểm tra output không vi phạm những quy tắc API phát hiện |
| Runtime target | Chạy class output bằng JVM 17 nếu yêu cầu hỗ trợ 17 | Kiểm chứng định dạng và dependencies thực sự tương thích |
| Agent target | Nạp agent trên từng JVM đã công bố hỗ trợ | Kiểm chứng agent class, thư viện, loader và hooks |
| Regression | Biên dịch lại trên JDK mới hơn và kiểm tra output | Phát hiện khác biệt API/format khi nâng JDK |

Không nên chỉ chạy test trên máy phát triển JDK 24 rồi công bố tương thích Java 17. Việc tool phân tích được class 17 **không chứng minh** agent dùng chính tool đó sẽ chạy trên JVM 17.

## 11. Lỗi thường gặp và cách giải quyết

| Hiện tượng | Nguyên nhân điển hình | Hướng xử lý |
|---|---|---|
| `package java.lang.classfile does not exist` | Compiler/JDK hoặc `--release` nhỏ hơn 24 | Dùng JDK 24+ cho tool và `--release 24`, hoặc bỏ API nếu target JVM cũ |
| `UnsupportedClassVersionError` khi chạy tool | Tool classfile major 68 nhưng JVM đang là 17/21 | Chạy tool bằng JDK 24+ hoặc phát hành tool khác cho runtime cũ |
| `NoClassDefFoundError: java/lang/classfile/...` | Class mang major thấp nhưng vẫn tham chiếu API Java 24, runtime cũ thiếu package | Tách runtime tool, dùng `--release` đúng, loại bỏ tham chiếu từ artifact cũ |
| `ClassFile.parse` ném `IllegalArgumentException` | Input hỏng hoặc classfile version không được parser hỗ trợ | Kiểm tra magic/version, class bytes và JDK tool; không sửa header bừa |
| `ClassFile.verify` trả danh sách lỗi | Bytes tạo ra không đáp ứng quy tắc mà API kiểm tra | Kiểm tra transform, stack map, constant pool, descriptors, attributes |
| Tool chạy được nhưng agent không tạo telemetry | Class-File API chỉ đọc/viết bytes, chưa đăng ký `ClassFileTransformer` hoặc chưa chèn probe | Kiểm tra điểm gọi `addTransformer`, bytecode output, class loader và quyền instrumentation |
| Agent JDK 24 attach không được vào JVM 17 | Runtime đích thiếu API/class version cần cho agent | Dùng agent tương thích Java 17 hoặc nâng JVM đích |
| Classfile major 61 nhưng vẫn lỗi trên JDK 17 | Mã phụ thuộc API/runtime mới hoặc có bytecode/attribute không tương thích | Sử dụng `--release 17` cho target, kiểm tra phụ thuộc và test trên JVM 17 |
| Compile được trong IDE nhưng CI thất bại | IDE/JDK/Gradle toolchain khác nhau | Ghi rõ toolchain, compiler release, `JAVA_HOME` và pipeline kiểm chứng |
| Source preview JDK 22/23 không compile trên 24 | Preview API thay đổi trước lúc final | Di chuyển sang Javadocs Java 24 và biên dịch lại |

**Đặc biệt:** `--enable-preview` trên Java 17/21 **không tạo ra** `java.lang.classfile` đã final của Java 24. Cờ preview chỉ mở các preview feature **có sẵn trong chính release đó**.

## 12. Bài tập áp dụng và câu hỏi tự kiểm tra

### Bài tập A — quan sát ba version

Chạy lệnh ở mục 5. Ghi lại `javac -version`, `model.majorVersion()` và `ClassFile.latestMajorVersion()`. Giải thích tại sao **tool=24** nhưng **target class=17** không mâu thuẫn.

### Bài tập B — thử biên dịch source API theo release cũ

Đổi `javac --release 24` của tool thành `--release 17`. Dự đoán lỗi compile rồi chạy thực tế. Phân biệt lỗi do **thiếu API** với lỗi do **input classfile hỏng**.

### Bài tập C — thay phiên bản class đầu vào

Biên dịch `Greeter.java` bằng `--release 21` rồi cho tool JDK 24 đọc lại. Major dự kiến là **65**. Tool vẫn cần JDK 24 nhưng target bytecode đã đổi thành 21. Dùng `javap -verbose` để xác minh.

### Bài tập D — chuẩn bị triển khai cho hai runtime

Yêu cầu sản phẩm: có hai nhóm khách hàng chạy JVM 17 và JVM 24, đều cần quan sát cùng một method. Hãy đề xuất cách chia tool offline hoặc agent artifacts để **không nạp mã gọi `java.lang.classfile` vào JVM 17**. Nêu rõ ma trận CI cần thiết.

### Bài tập E — phân biệt output class và tool

Trong ví dụ, tạo `outCopy/demo/Greeter.class` bằng JDK 24 và thử chạy bằng JVM 17 nếu có. Vì sao có cơ sở kỳ vọng class này chạy được, trong khi `out24/ClassFileApiDemo.class` lại không chạy trên JVM 17? Trả lời dựa trên **major version + API references**, không chỉ dựa vào máy build.

### Câu hỏi tự đánh giá

1. **`java.lang.classfile` trở thành standard API ở JDK nào?** — **JDK 24, JEP 484**; JDK 22/23 là các preview.
2. **Package thuộc module nào?** — **`java.base`**.
3. **Dùng API trên JDK 24 có cần `--enable-preview` không?** — **Không**, đối với Class-File API đã final.
4. **Tool JDK 24 có đọc class Java 17 được không?** — **Có**, với classfile hợp lệ và format mà parser hỗ trợ.
5. **Agent biên dịch JDK 24 dùng API này có chạy trong JVM 17 không?** — **Không**, vì JVM 17 thiếu API và không hỗ trợ class major 68.
6. **`--release 17` có cho phép import package Java 24 không?** — **Không**.
7. **`ClassTransform.ACCEPT_ALL` có tự chèn probe không?** — **Không**, nó chuyển các elements qua pipeline.
8. **`verify` trả zero có thay thế runtime test không?** — **Không**, còn linkage, class loader, module và runtime behavior.
9. **Vì sao không sửa major trong class header để hỗ trợ JVM cũ?** — Vì format, instructions, attributes và API dependencies có thể không tương thích.
10. **Khi nào nên chọn thư viện bytecode hỗ trợ Java 17 thay vì Class-File API?** — Khi chính **tool/agent phải chạy trên JVM 17**, không chỉ phân tích bytecode Java 17.

## 13. Ghi nhớ và tài liệu chính thức

**Class-File API là API chuẩn từ JDK 24 cho parse/build/transform class files**, nhưng **phiên bản của công cụ**, **phiên bản của classfile** và **phiên bản JVM đích** cần được quyết định độc lập. Tool JDK 24 có thể tạo class Java 17 hợp lệ, còn agent dùng API JDK 24 **phải chạy trong JVM có API tương ứng**. Khi phát hành cho nhiều JDK, nên xác nhận cả **`--release`, major_version, liên kết API và chạy thử trên JVM đích**.

Tài liệu chuẩn:

- [JEP 484 — Class-File API (final)](https://openjdk.org/jeps/484): mốc final của JDK 24.
- [JEP 457 — Class-File API (Preview)](https://openjdk.org/jeps/457): preview JDK 22.
- [JEP 466 — Class-File API (Second Preview)](https://openjdk.org/jeps/466): preview JDK 23.
- [Java SE 24 — java.lang.classfile package](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html): model, element, constant pool và API xử lý class.
- [Java SE 24 — ClassFile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `parse`, `build`, `transformClass`, `verify` và version.
- [Java SE 24 — ClassTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): `ACCEPT_ALL` và các kiểu transform.
- [Java VM Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html): `major_version`, `minor_version`, verifier và cấu trúc classfile.
