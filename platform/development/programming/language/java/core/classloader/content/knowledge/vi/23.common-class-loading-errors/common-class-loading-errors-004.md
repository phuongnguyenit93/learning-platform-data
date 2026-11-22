# UnsupportedClassVersionError và phiên bản bytecode Java

> **Java Core → ClassLoader → Lỗi thường gặp.** `UnsupportedClassVersionError` xuất hiện khi JVM cố đọc một class file có **major/minor version** mà JVM hiện tại không hỗ trợ. Tình huống phổ biến nhất là **biên dịch bằng JDK mới hơn rồi chạy bằng Java runtime cũ hơn**. Ngoài ra, lỗi cũng liên quan **preview features**, dependency/JAR chứa bytecode khác phiên bản, hoặc class được tạo/biến đổi bởi công cụ. Bài học tập trung vào cách hiểu header `.class`, xác định JDK thực sự đang chạy, sửa đúng ở build/deploy và phòng tránh tái diễn.

## 1. Nhận diện lỗi qua một thông báo thực tế

Một lỗi tiêu biểu khi chạy class được biên dịch nhắm Java 21 trên Java 17:

```text
java.lang.UnsupportedClassVersionError: com/example/App
has been compiled by a more recent version of the Java Runtime
(class file version 65.0), this version of the Java Runtime only
recognizes class file versions up to 61.0
```

Thông báo trên là **ví dụ mô tả dạng lỗi**; JVM có thể in tên class với dấu `.` hoặc `/`, chi tiết và stack trace khác nhau tùy JDK. Dữ liệu cần đọc là:

- `com/example/App`: class JVM đang cố đọc, **không nhất thiết là class có `main`**.
- `class file version 65.0`: class file yêu cầu phiên bản format tương ứng Java 21.
- `up to 61.0`: runtime ở ví dụ hỗ trợ tối đa major 61, tương ứng Java 17.
- JVM từ chối đọc **định dạng class file** trước khi chạy được bytecode của class đó.

Giải pháp trực tiếp có hai hướng **tùy ràng buộc dự án**:

1. Chạy trên **runtime đủ mới** để hỗ trợ class version đã biên dịch (Java 21+ đối với major 65.0, với lưu ý preview).
2. Nếu production phải dùng **Java 17**, biên dịch **toàn bộ code và dependency có thể tương thích** nhắm Java 17 bằng `javac --release 17` hoặc cấu hình build tool tương đương.

**Không** sửa bằng cách đổi tên JAR, thay classpath tùy tiện, đổi TCCL, ép `URLClassLoader` hoặc sửa số version trong header `.class`. Các thao tác đó không làm JVM cũ có thêm bytecode instructions, constant pool tags và JDK APIs của phiên bản mới.

## 2. UnsupportedClassVersionError nằm ở đâu trong họ lỗi JVM?

Quan hệ kế thừa theo API Java:

```text
java.lang.Object
  └── java.lang.Throwable
        └── java.lang.Error
              └── java.lang.LinkageError
                    └── java.lang.ClassFormatError
                          └── java.lang.UnsupportedClassVersionError
```

`UnsupportedClassVersionError` được ném khi JVM **đọc class file** và nhận thấy tổ hợp major/minor version không được hỗ trợ. Đây là một `Error`, **không phải checked exception** và không thuộc `ClassNotFoundException`.

Các lỗi dễ nhầm:

| Lỗi | Tình huống thường gặp | Có phải cùng nguyên nhân? |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JVM không hỗ trợ `major_version`/`minor_version` của class file được load. | **Đúng chủ đề.** |
| `ClassNotFoundException` | Một API tìm class theo tên (`Class.forName`, `ClassLoader.loadClass`) không tìm thấy định nghĩa phù hợp. | Không; class có thể không có trên đường tìm. |
| `NoClassDefFoundError` | JVM cần class khi linking/execution nhưng không có định nghĩa phù hợp, hoặc class trước đó initialization thất bại. | Không mặc định; xem cause và chi tiết. |
| `ClassFormatError` | Bytecode/constant pool/header/classfile không hợp lệ. | Họ lỗi cha; version mismatch là một nhánh con. |
| `VerifyError` | Bytecode không thỏa quy tắc verifier. | Khác format version, dù có thể gặp sau bước đọc class. |
| `NoSuchMethodError` | Runtime method/signature không tương thích với class đã compile. | Có thể do trộn Java APIs/versions; không chữa bằng sửa major. |
| `UnsupportedOperationException` | Một operation hợp lệ về class loading nhưng API ứng dụng không hỗ trợ. | Khác hoàn toàn. |
| `IllegalAccessError` | Runtime access/linkage checks thất bại. | Thường do module, class/member access. |

Một `ClassLoader` có thể tìm **đúng file**, đọc bytes thành công, nhưng `defineClass` vẫn ném `UnsupportedClassVersionError`. Vì vậy đừng đánh đồng “không tìm thấy class” với “JVM không hiểu phiên bản class file”.

## 3. Class-file header: CAFEBABE, minor và major

Tệp `.class` mở đầu bằng header theo JVM Specification `4.1`:

```text
Offset (byte)    Kích thước   Ý nghĩa
0..3             u4           magic = 0xCAFEBABE
4..5             u2           minor_version
6..7             u2           major_version
8..               ...          constant_pool_count và phần còn lại
```

Các số nguyên này dùng **big-endian**. Ví dụ class biên dịch bằng `javac --release 17` thường bắt đầu bằng:

```text
CA FE BA BE 00 00 00 3D ...
| magic   |minor|major|
                 0x003D = 61 (Java 17)
```

Đừng nhầm số version trong `MANIFEST.MF` (`Implementation-Version`, `Bundle-Version`, v.v.) với `major_version` nằm ở **từng entry `.class`**. Một JAR có thể chứa nhiều class files không cùng major version; một dependency lồng trong classpath thậm chí có version khác class `Main`.

### Bảng quy đổi major version

Theo bảng phiên bản trong Java Virtual Machine Specification Java SE 26:

| Java release | Major của class file thông thường |
| --- | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |

Với **Java 5 trở lên**, quy tắc tra nhanh cho release `N` là `major = N + 44` (và `N = major - 44` trong phạm vi này). **Không áp dụng máy móc công thức cho các bản cổ 1.0–1.4**: Java 1.0/1.1 dùng major 45 và Java 1.2–1.4 có 46–48.

Theo Java SE 26, một JVM tương thích hỗ trợ major trong phạm vi 45–70; các JVM Java 17 hay 21 có **giới hạn trên thấp hơn**. JVM mới có xu hướng hỗ trợ format cũ, **nhưng không có nghĩa mọi ứng dụng cũ luôn chạy y nguyên trên JDK mới** vì còn runtime APIs, modules, native libraries và các thay đổi khác.

### Version trong thông báo đọc thế nào?

`65.0` nghĩa là **major=65, minor=0**, tương ứng định dạng thường của Java 21. Không phải “Java 65” hoặc JDK 6.5. `61.0` nghĩa Java 17 class-file format. Đọc hai số này trước sẽ tránh mất thời gian sửa sai library.

## 4. Minor version và preview features: ngoại lệ quan trọng

Một lớp dùng preview features có thể mang **minor version 65535**. Quy tắc từ Java 12 trở đi trong JVM Specification:

- Với class-file major từ 56 trở lên, minor hợp lệ thường là **0 hoặc 65535**.
- `M.65535` biểu thị class **phụ thuộc preview features** của đúng release tương ứng major `M`.
- Class preview của release `N` chỉ được load trên JVM **đúng release `N`**, khi preview được bật cho runtime (thường `java --enable-preview ...`).
- JVM phiên bản **mới hơn** không tự chấp nhận preview class file của phiên bản **cũ hơn**, ngay cả khi bật `--enable-preview`.
- Không nên lấy `--enable-preview` làm cách sửa mọi `UnsupportedClassVersionError`; lỗi major quá mới và lỗi preview minor khác nhau.

Ví dụ:

```text
61.0      = class-file thường nhắm Java 17
61.65535  = preview class-file của Java 17
65.0      = class-file thường nhắm Java 21
65.65535  = preview class-file của Java 21
70.0      = class-file thường nhắm Java 26
70.65535  = preview class-file của Java 26
```

Một `61.65535` có thể dùng trên đúng Java 17 với preview enabled, nhưng **không dùng trên Java 21/24/26** chỉ bằng cách bật flag. Cách xử lý bền vững là **biên dịch lại source preview theo Java release đích**, sửa code để dùng stable features nếu có thể.

### Biên dịch và chạy preview trên cùng release

Cú pháp tổng quát (ví dụ cho một JDK đang dùng preview):

```bash
javac --enable-preview --release 26 Demo.java
java --enable-preview Demo
```

Đây là **ví dụ cú pháp cho JDK 26**, giả định source có preview features được JDK đó hỗ trợ; nó **không chạy nguyên trên JDK 17/21/24** và không thay test độc lập của bài ở mục 8. Compiler chỉ hỗ trợ `--enable-preview` kết hợp source/release của **phiên bản compiler hiện tại**; không dùng JDK 26 để phát hành preview class của Java 17 bằng `--release 17`.

Đối với class files cũ trước Java 12, quy tắc minor có lịch sử khác; khi chẩn đoán ứng dụng Java hiện đại, hãy tập trung vào các cặp major/minor được nêu trong thông báo.

## 5. Vì sao biên dịch bằng JDK mới rồi chạy JVM cũ thất bại?

Giả sử:

```text
Developer machine / CI:
    javac 21 -> App.class major=65

Production server:
    java 17 -> supports max major=61

ClassLoader reads App.class
    -> JVM rejects version 65
    -> UnsupportedClassVersionError
```

Compiler mặc định thường tạo class files theo Java release của **chính compiler** nếu không được cấu hình target. Vì vậy, nếu team có người dùng JDK 21 còn runtime production Java 17, chỉ chạy `javac App.java` hoặc cấu hình mặc định có thể tạo artifact không tương thích.

Tình huống lỗi phổ biến:

1. **JDK nâng trên máy build nhưng production chưa nâng.** Docker image base hoặc VM JRE vẫn Java 17.
2. **Maven/Gradle toolchain không thống nhất.** Java compiler dùng phiên bản mới nhưng launcher runtime dùng phiên bản cũ.
3. **Thư viện bên thứ ba nâng major.** Source của ứng dụng vẫn build target cũ nhưng dependency release mới chỉ hỗ trợ JVM mới.
4. **IDE biên dịch bằng Project SDK khác runtime.** IntelliJ/Eclipse có project language level, compiler SDK và run configuration khác nhau.
5. **Plugin loader nạp JAR của plugin mới.** Host runtime cũ không đọc được class của plugin, dù host chính chạy thành công.
6. **Framework sinh hoặc instrument bytecode.** Byte Buddy, ASM, proxy generator hoặc build plugin có thể tạo class-file major ngoài khả năng JVM hiện tại.
7. **Multi-release JAR đóng gói/đọc sai.** Class theo thư mục `META-INF/versions` cần được runtime chọn theo quy tắc Multi-Release JAR; tool custom lấy nhầm entry tương ứng JDK mới.
8. **Lẫn PATH, JAVA_HOME và toolchain.** `javac` và `java` thực sự được gọi có thể đến từ hai JDK khác nhau.

Một class `Main` có major 61 không đảm bảo tất cả `.class` trong classpath đều major 61. JVM chỉ kiểm tra khi từng class được load; vì vậy app có thể khởi động, chạy vài tính năng rồi lỗi khi truy cập một class mới trong dependency/plugin.

## 6. Kiểm tra phiên bản compiler và runtime thật đang dùng

### Phân biệt java, javac và process đang chạy

Các lệnh:

```bash
java -version
javac -version
java --version
javac --version
```

Thường `java -version` in thông tin runtime và `javac -version` in compiler. **Không kết luận chúng trỏ cùng installation** chỉ vì các lệnh không báo lỗi.

Nếu cần kiểm tra đường executable:

```bash
# Linux/macOS:
command -v java
command -v javac
echo "$JAVA_HOME"

# PowerShell:
Get-Command java
Get-Command javac
$env:JAVA_HOME
```

Đây là lệnh shell phụ thuộc môi trường; không có stdout cố định vì path khác nhau. `JAVA_HOME` là biến cấu hình, **không bắt buộc trùng** executable được PATH hoặc IDE/Gradle daemon/container chọn.

Với container hoặc production process, hãy chạy lệnh bên **chính môi trường đang chạy ứng dụng** thay vì chỉ từ terminal máy developer. Kiểm tra JVM của service bằng startup logs/`jcmd` nếu có quyền; `java -version` từ một terminal host không chứng minh JVM chạy trong container là cùng bản.

### Kiểm tra class file thật

Lệnh JDK:

```bash
javap -verbose path/to/App.class
```

Trong phần đầu sẽ thấy:

```text
minor version: 0
major version: 65
```

Đây là **output minh họa** của class major 65, không phải kết quả khi chạy trên artifact trong mục 8 (artifact ví dụ mục 8 là major 61). Nếu `javap` là phiên bản cũ hơn class file, công cụ có thể không phân tích hết cấu trúc mới; đọc trực tiếp 8 bytes header vẫn giúp xác định version.

Với class nằm trong JAR:

```bash
jar tf my-library.jar
javap -verbose -classpath my-library.jar com.example.Widget
```

`my-library.jar` và `com.example.Widget` là placeholders. `javap` phải chọn đúng JAR và class để kết quả có ý nghĩa. `jar tf` cho thấy entries nhưng **không tự liệt kê major** của từng `.class`. Nếu có nhiều JAR cùng class, kiểm tra đúng archive runtime đã chọn; riêng `javap -classpath ...` không chứng minh chính class đó được loader đang chạy lấy từ JAR ấy.

## 7. Cách sửa đúng: nâng runtime hay build xuống?

### Lựa chọn A — nâng JVM runtime

Khi cần APIs/language features/bytecode của Java 21:

```text
Compile target: Java 21
Runtime:        Java 21 hoặc cao hơn với điều kiện tương thích phù hợp
```

Với major 65.0, nâng từ Java 17 lên Java 21 sẽ giải quyết **giới hạn class-file major**. Tuy nhiên vẫn cần kiểm thử dependencies, JPMS encapsulation, native code, JVM flags và behavioral changes. Chỉ nâng JDK nếu được dự án và vận hành chấp nhận, cập nhật cả Docker image/VM/container/service config.

Nếu class là preview `65.65535`, chạy trên Java 21 với preview enabled mới là điều kiện phù hợp; **Java 25 không tự dùng được** class preview từ Java 21.

### Lựa chọn B — biên dịch để hỗ trợ Java cũ

Khi production phải chạy Java 17, nên dùng:

```bash
javac --release 17 -d out src/com/example/App.java
```

Snippet lệnh giả định file Java đúng vị trí. `--release 17` giúp đồng thời:

- Sử dụng cú pháp và tính năng ngôn ngữ theo **release 17**.
- Phát sinh class files tương ứng với **target Java 17** (major 61).
- Kiểm tra các public documented Java SE/JDK APIs khả dụng ở release 17, tránh vô tình gọi JDK API chỉ có ở release mới.

So với cách chỉ sử dụng `--target 17`, `--release 17` an toàn hơn cho cross-compilation bởi nó đồng bộ **source, target và platform APIs**.

Ví dụ một chương trình dùng API được bổ sung sau Java 17 sẽ không thể “chạy Java 17” chỉ nhờ ép major 61. Compiler `--release 17` sẽ từ chối API không có trong release đích khi nhận diện qua symbols tương ứng.

### Vì sao --source và --target riêng chưa đủ?

`--source 17` chọn language syntax. `--target 17` chỉ định class-file output target. Nếu compile trên JDK mới với **các API của JDK mới** đang hiển thị, một source vẫn có thể compile và tạo major 61 nhưng thất bại ở runtime Java 17 vì thiếu class/method (ví dụ `NoSuchMethodError`), tùy chương trình.

```bash
# Thường NÊN dùng:
javac --release 17 -d out src/com/example/App.java

# Không tương đương hoàn toàn về ràng buộc platform APIs:
javac --source 17 --target 17 -d out src/com/example/App.java
```

Hai lệnh là mẫu áp dụng cho cấu trúc dự án phù hợp, không phải copy-run khi file `src/com/example/App.java` chưa tồn tại. `--release` không thể kết hợp cùng `--source` hoặc `--target` trong một invocation.

Quan trọng: `--release 17` ở **module ứng dụng** không tự ép **dependency JAR đã biên dịch sẵn** về major 61. Nếu dependency chứa major 65, bạn phải chọn **dependency version hỗ trợ Java 17**, tự build dependency đúng release từ source hợp lệ, hoặc nâng runtime.

### Chọn phiên bản compile có hỗ trợ

Không phải JDK nào cũng cho `--release` về mọi phiên bản quá cũ. Kiểm tra:

```bash
javac --help
```

Tài liệu `javac` nêu mỗi JDK chỉ hỗ trợ tập release hiện tại và một số release trước. Cần chọn compiler/toolchain phù hợp thay vì tùy tiện nhập `--release 1.4` trên JDK 26.

## 8. Thực hành chạy được: đọc major/minor và tái hiện UnsupportedClassVersionError

Để không cần cài song song hai phiên bản JDK, thí nghiệm dưới đây:

1. Biên dịch class `demo.Greeting` bằng `--release 17`, tạo class header **major 61, minor 0**.
2. Dùng custom loader nạp bytes gốc thành công.
3. Tạo **bản sao trong bộ nhớ** của bytes rồi cố tình sửa **hai byte major thành 32767**, vượt xa Java releases đang được hỗ trợ, để kiểm tra `UnsupportedClassVersionError`.
4. Tạo bản sao khác giữ major 61 nhưng đặt **minor thành 65535**, tương đương header preview class của Java 17, rồi thử nạp trên runtime **khác release** hoặc không bật preview; nó bị từ chối theo quy tắc preview.
5. Không ghi đè class file gốc trên disk. Việc sửa header ở đây **chỉ là thí nghiệm minh họa điều kiện JVM kiểm tra**, **không phải cách chữa lỗi**.

Thí nghiệm tương thích Java 17+; kết quả dưới được kiểm chứng trên OpenJDK 24 với preview không bật. Nếu chạy đúng JDK 17 **và bật** `--enable-preview`, kịch bản minor 61.65535 có thể khác, như mục 4.

### Cấu trúc thư mục

```text
src/
  demo/
    Greeting.java
  app/
    VersionProbe.java
out/
  plugin/     (javac tạo)
  app/        (javac tạo)
```

**File `src/demo/Greeting.java`:**

```java
package demo;

public class Greeting {
    public String say() {
        return "hello";
    }
}
```

**File `src/app/VersionProbe.java`:**

```java
import java.nio.file.Files;
import java.nio.file.Path;

public class VersionProbe {
    static final class DemoLoader extends ClassLoader {
        DemoLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> define(byte[] bytes) {
            return defineClass(
                    "demo.Greeting", bytes, 0, bytes.length);
        }
    }

    static int u2(byte[] b, int offset) {
        return ((b[offset] & 0xff) << 8)
                | (b[offset + 1] & 0xff);
    }

    public static void main(String[] args) throws Exception {
        byte[] original = Files.readAllBytes(
                Path.of("out/plugin/demo/Greeting.class"));

        System.out.println("magic: "
                + String.format("%02X%02X%02X%02X",
                        original[0], original[1],
                        original[2], original[3]));
        System.out.println("minor: " + u2(original, 4));
        System.out.println("major: " + u2(original, 6));
        System.out.println("normal load: "
                + new DemoLoader().define(original).getName());

        byte[] future = original.clone();
        future[6] = (byte) 0x7F;
        future[7] = (byte) 0xFF;  // major = 32767

        try {
            new DemoLoader().define(future);
            System.out.println("future-major rejected: false");
        } catch (UnsupportedClassVersionError expected) {
            System.out.println("future-major rejected: true");
        }

        byte[] oldPreview = original.clone();
        oldPreview[4] = (byte) 0xFF;
        oldPreview[5] = (byte) 0xFF; // minor = 65535

        try {
            new DemoLoader().define(oldPreview);
            System.out.println("old-preview rejected: false");
        } catch (UnsupportedClassVersionError expected) {
            System.out.println("old-preview rejected: true");
        }
    }
}
```

**Lệnh biên dịch** (từ thư mục chứa `src`):

```bash
javac --release 17 -d out/plugin src/demo/Greeting.java
javac --release 17 -d out/app src/app/VersionProbe.java
javap -verbose out/plugin/demo/Greeting.class
java -cp out/app VersionProbe
```

Ở Windows PowerShell/CMD, có thể chạy các lệnh một dòng tương tự nếu thư mục hiện hành đúng. `javap -verbose` sẽ in nhiều thông tin; phần liên quan:

```text
minor version: 0
major version: 61
```

**Stdout chính xác của `java -cp out/app VersionProbe` trên OpenJDK 24:**

```text
magic: CAFEBABE
minor: 0
major: 61
normal load: demo.Greeting
future-major rejected: true
old-preview rejected: true
```

### Vì sao hai lần define hỏng?

- `future[6]` và `future[7]` là byte vị trí **major_version**, big-endian. `0x7FFF = 32767` không được JVM đang dùng hỗ trợ.
- `oldPreview[4]` và `oldPreview[5]` là **minor_version**. Với major 61, minor `65535` biểu thị preview class theo Java 17; JVM OpenJDK 24 chạy bài thử không thể nạp preview class của Java 17.
- `DemoLoader` mỗi lần là instance khác nhau, để tránh lỗi định nghĩa trùng cùng binary name và đảm bảo quan sát đúng lỗi **version**. Class `demo.Greeting` không có trong `out/app` và parent platform loader không nhìn thấy `out/plugin`.
- JVM phát hiện và ném `UnsupportedClassVersionError` tại `defineClass`; code chủ động catch để demo tiếp tục. **Ứng dụng sản xuất không nên catch rồi im lặng**, bởi đó là dấu hiệu artifact không tương thích.
- `byte[]` gốc vẫn giữ header `61.0` và có thể nạp. Không có tệp `.class` nào bị vá trên disk.

**Không lấy số 32767 để định danh một bản Java thật**. Nó chỉ đóng vai trò một major không được hỗ trợ trong thí nghiệm, không phải version mà bạn nên đưa vào artifact.

## 9. Tại sao lỗi có thể đến từ dependency, plugin hoặc bytecode sinh ra?

Một stack trace có thể nêu:

```text
com/vendor/library/SomeHelper
```

dù class có `main` của bạn đã chạy xong giai đoạn startup. Lý do JVM thực hiện **loading và resolution theo nhu cầu**: chỉ đến khi chương trình chạm một class mới thì JVM mới cần đọc class-file bytes của nó.

### Dependency biên dịch mới hơn

Ví dụ:

```text
application.jar          (major 61, Java 17)
  -> logging-core.jar    (major 61)
  -> new-feature.jar     (major 65, Java 21)
runtime: Java 17
```

`new-feature.jar` chứa class major 65 nhưng Java 17 chỉ hỗ trợ tối đa major 61; lỗi xuất hiện khi JVM cần class của thư viện đó. Hạ target của **application** không tự biên dịch lại `new-feature.jar`.

Cách xử lý:

- Tìm class đúng tên trong stack trace và artifact chứa nó.
- Kiểm tra dependency tree (Maven/Gradle) và bản phát hành hỗ trợ Java tối thiểu.
- Chọn version dependency còn hỗ trợ Java 17 hoặc nâng runtime.
- Nếu tự build dependency, biên dịch lại toàn bộ với `--release 17` và xác minh không gọi API mới.

### Plugin loader tùy chỉnh

Một `URLClassLoader` có thể tìm class thành công nhưng `defineClass` ném `UnsupportedClassVersionError`. Một custom loader không thể hỗ trợ major 65 trên Java 17 bằng cách tự đặt `getClassLoadingLock`, đổi parent, thêm URL hoặc chạy `definePackage`: định dạng class là giới hạn **của JVM đang nhận bytecode**, không phải của đường tìm kiếm.

Với hệ plugin nhiều phiên bản, quy định **minimum supported Java runtime** trong plugin metadata và xác minh artifact trước khi kích hoạt để báo lỗi sớm với thông điệp dễ hiểu.

### Bytecode generator/transformer

Các công cụ như ASM/Byte Buddy hoặc runtime proxy generator cần tạo class-file version mà JVM chạy hỗ trợ, đồng thời phải hiểu các tính năng mới của JDK. Nếu library tạo bytes major quá mới hoặc không hợp lệ, lỗi có thể nằm trong class sinh động (không có `.class` sẵn trên filesystem). Kiểm tra version của generator, target, JDK runtime và configuration, không giả định sửa `javac --release` sẽ tác động lên bytecode do thư viện sinh tại runtime.

## 10. Multi-release JAR: nhiều bản classfile trong cùng một archive

Một **multi-release JAR** có thể có các lớp gốc và các bản thay thế cho Java release khác nhau:

```text
library.jar
├── META-INF/MANIFEST.MF
├── com/example/Feature.class
├── META-INF/versions/17/com/example/Feature.class
└── META-INF/versions/21/com/example/Feature.class
```

Manifest có thuộc tính:

```text
Multi-Release: true
```

Với cơ chế chọn version hợp lệ, runtime sẽ chọn entry version-specific có release phù hợp, thông thường là **cao nhất không vượt quá runtime feature version**, và fallback về base entry nếu cần. Do đó **chỉ thấy `META-INF/versions/21` không có nghĩa Java 17 sẽ cố load class Java 21**.

Nhưng có thể gặp lỗi khi:

- Công cụ đóng gói/shading làm mất hoặc sửa sai thuộc tính `Multi-Release`.
- Base classes của JAR cũng biên dịch ở major quá cao so với runtime cần hỗ trợ.
- Custom loader tự lấy raw entry `META-INF/versions/21/...` thay vì dùng semantics multi-release JAR.
- Framework đọc class bytes từ archive bằng ZIP API và áp dụng thay thế không đúng.
- Dependency JAR không hỗ trợ runtime dù có folder `META-INF/versions`.

Đừng vá bằng cách xóa bừa các thư mục versioned. Kiểm tra cách artifact được đóng gói và cách **loader thực tế** chọn entry.

Lệnh hỗ trợ:

```bash
jar tf library.jar
jar xf library.jar META-INF/MANIFEST.MF
```

`jar xf` giải nén một entry vào thư mục hiện tại, vì vậy chỉ chạy khi biết mục tiêu/thư mục làm việc phù hợp. Nếu chỉ muốn xem nội dung manifest mà không làm thay đổi workspace, có thể dùng công cụ ZIP/JAR viewer thích hợp. Các lệnh không tự kết luận class version nào được chọn; cần xác minh runtime behavior.

## 11. Cấu hình Maven/Gradle và CI để không tái diễn

### Maven: thiết lập release thống nhất

Trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Property này được Maven Compiler Plugin sử dụng ở phiên bản/configuration hỗ trợ. Với dự án phức tạp, nên chỉ định phiên bản compiler plugin được hỗ trợ và dùng toolchains nếu build machine có nhiều JDK. **Java đang chạy Maven** có thể khác **JDK dùng để compile** theo toolchains; kiểm tra cả hai.

Các lệnh quan sát:

```bash
mvn -version
mvn dependency:tree
```

Cần Maven và plugin/dependencies tương ứng. `mvn -version` chủ yếu mô tả JDK chạy Maven process, **không luôn là bằng chứng compiler toolchain được chọn**.

### Gradle: Java toolchain và release

Một cấu hình Gradle Groovy DSL minh họa:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Toolchain giúp định rõ compiler/JDK mà Gradle dùng cho Java work; `options.release` yêu cầu class files và API compatibility theo release đích khi compiler hỗ trợ. Không nên chỉ đặt `sourceCompatibility` rồi nghĩ production JDK tự phù hợp. Bản Gradle/plugin đang dùng phải hỗ trợ target JDK; cập nhật tooling nếu cần.

### CI: build và test trên bản Java nhỏ nhất cần hỗ trợ

Checklist CI:

1. **Định nghĩa baseline runtime** (ví dụ Java 17) trong build configuration.
2. Biên dịch bằng `--release 17` hoặc tùy chọn tương đương.
3. **Chạy integration tests bằng Java 17**, không chỉ dùng JDK 21 và hy vọng backward compatibility.
4. Kiểm tra major version của **mọi artifacts phát hành và dependency quan trọng**, không chỉ main class.
5. Trên matrix nếu hỗ trợ nhiều bản, test Java 17/21/25... theo support policy.
6. Nếu có preview code, gắn Java release chính xác và kế hoạch migration; đừng phát hành preview class mập mờ với runtime khác.
7. Kiểm tra Docker base image và deployment JVM thực tế, vì build JDK không quyết định JVM của production.
8. Ghi rõ minimum Java version trong tài liệu/plugin manifest để host phát hiện mismatch sớm.

Một JAR có base class major 61 nhưng dùng native code, JNI hoặc API hành vi khác vẫn cần runtime test thật; quét major **không phải toàn bộ compatibility test**.

## 12. Cây quyết định sửa lỗi theo thông báo

```text
Thấy java.lang.UnsupportedClassVersionError
         |
         v
1. Lấy tên class và cặp class-file M.m
         |
         v
2. Xác định JVM đang chạy thật: java -version / runtime logs
         |
         +--> M > max major runtime?
         |       |
         |       +-- YES:
         |           Chọn:
         |            - nâng runtime lên release hỗ trợ
         |            - HOẶC build lại toàn bộ code/dependency
         |              cho release cũ với --release
         |
         +--> M <= max major runtime?
                 |
                 v
3. Kiểm tra minor:
      - m = 65535? preview đúng cùng release + enabled?
      - m bất thường/không hợp lệ? kiểm tra generator/transformer
                 |
                 v
4. Xác minh JAR/class cụ thể và classloader thực tế
                 |
                 v
5. Rebuild/redeploy + test trên JVM baseline thực tế
```

**Nếu runtime Java 17 mà thấy class file 65.0:** Không có flag classloader nào giải quyết format mismatch. Chọn nâng Java runtime lên mức phù hợp (Java 21+) hoặc hạ target/rebuild dependency xuống Java 17.

**Nếu runtime Java 24 mà thấy class file 61.65535:** Đây không phải lỗi do major quá cao; nguyên nhân nằm ở **preview class file từ Java 17**, vốn không thể dùng trên Java 24 theo JVM Specification. Cần rebuild từ source theo release muốn chạy, hoặc chạy đúng Java 17 với preview enabled nếu được hỗ trợ và chấp nhận.

**Nếu runtime Java 21 mà thấy class file 65.0 nhưng vẫn lỗi khác:** Kiểm tra đúng JVM thực chạy, class source thực được chọn, rồi xem exception **chính xác** là gì. Nếu `NoSuchMethodError` hoặc `IllegalAccessError`, đừng gọi đó là `UnsupportedClassVersionError`.

## 13. Những sai lầm thường gặp

| Sai lầm | Vì sao không hiệu quả | Hướng đúng |
| --- | --- | --- |
| Sửa `JAVA_HOME` rồi kết luận production đã đổi JVM | PATH, service wrapper, Docker image hoặc Gradle daemon có thể dùng Java khác. | Xác định runtime executable/process thực. |
| Chỉ sửa `javac --source 17` | Không đảm bảo class target/platform APIs đều đúng. | Dùng `--release 17` và test JVM17. |
| Chỉ sửa `javac --target 17` | Có thể vẫn compile chống API mới từ JDK đang chạy. | Dùng `--release` hoặc toolchain/API matching. |
| Chỉ build lại app nhưng giữ dependency major 65 | JVM17 vẫn không đọc được class major 65. | Đổi dependency/build source hoặc nâng runtime. |
| Đổi số byte major 65→61 bằng hex editor | Bytecode mới có thể dùng instructions/features/constant pool không hỗ trợ; class có thể hỏng. | Recompile source cho target; không vá header như workaround. |
| Bắt `ClassNotFoundException` để xử lý lỗi version | `UnsupportedClassVersionError` là `Error` khác. | Sửa artifact/JVM mismatch; log version. |
| Thêm URLClassLoader vào classpath | Class có thể được tìm nhưng JVM vẫn không hỗ trợ version. | Xác định JVM major support. |
| Bật `--enable-preview` cho class major mới hơn runtime | Preview flag không làm runtime hiểu format release mới. | Dùng đúng runtime, rebuild thích hợp. |
| Dùng JDK mới chạy preview class từ JDK cũ | Preview class gắn chặt với đúng release. | Recompile source theo release mới. |
| Tin rằng `jar tf` hiển thị class version | Nó chỉ liệt kê entry names. | Dùng `javap -verbose` hoặc đọc header. |
| Nhìn `Main.class` major 61 rồi kết luận mọi plugin tương thích Java17 | Dependency/plugin/generated bytes có thể cao hơn. | Kiểm tra artifacts thật được JVM nạp. |
| Tin build CI xanh trên JDK25 nghĩa chạy được Java17 | Test chạy trên JVM mới không chứng minh tương thích JVM cũ. | Test matrix có runtime baseline. |
| Gặp bất kỳ `LinkageError` đều sửa bằng nâng JDK | LinkageError còn nhiều nguyên nhân khác. | Phân tích exception subtype và message. |

## 14. Tự kiểm tra kiến thức

1. **Thông báo “class file version 65.0, runtime up to 61.0” nghĩa gì?**  
   Class file định dạng Java 21 nhưng runtime chỉ hỗ trợ tối đa Java 17.

2. **`UnsupportedClassVersionError` có phải một checked exception?**  
   Không. Nó kế thừa `ClassFormatError → LinkageError → Error`.

3. **Hai byte nào trong class file ghi major?**  
   Offset 6 và 7, theo big-endian; offsets 4 và 5 chứa minor.

4. **Java 17 và Java 21 thường có major gì?**  
   Tương ứng 61 và 65.

5. **`--release 17` bảo đảm điều gì khác `--target 17` đơn lẻ?**  
   Nó phối hợp source rules, class format và các platform APIs của Java 17.

6. **Một app main major 61 có thể bị lỗi do dependency major 65?**  
   Có, khi runtime cần load class thuộc dependency mới hơn.

7. **`61.65535` có giống `61.0`?**  
   Không. Minor 65535 đánh dấu preview class của Java 17; có yêu cầu runtime đặc biệt.

8. **Java 24 có chạy preview `61.65535` chỉ bằng `--enable-preview`?**  
   Không. Preview class từ Java 17 không được load trên Java 24.

9. **`jar tf library.jar` có báo major tất cả classes không?**  
   Không. Dùng `javap -verbose` cho class cụ thể hoặc công cụ scan class headers.

10. **Vì sao bắt `ClassNotFoundException` không xử lý được version mismatch?**  
    JVM đã tìm/đọc bytes nhưng không hỗ trợ version; nó ném `UnsupportedClassVersionError`.

11. **Có nên sửa byte header 65 thành 61 để chạy trên Java17?**  
    Không. Nó không chuyển ngữ nghĩa bytecode/API mới thành tương thích Java17.

12. **Một multi-release JAR chứa `META-INF/versions/21` có mặc nhiên lỗi trên Java17?**  
    Không, nếu archive và loader tuân thủ multi-release selection và base class hỗ trợ Java17.

13. **Vì sao test trên Java mới không chứng minh app chạy được Java cũ?**  
    Runtime mới thường hiểu format cũ, còn runtime cũ không hiểu format mới; API và dependency cũng khác.

14. **Khi production chạy trong container, nên xem Java version ở đâu?**  
    Trong container/process thực đang chạy ứng dụng, không chỉ trên máy developer.

## 15. Tài liệu chính thức

- [Java SE 26 — JVMS `1.2, bảng class-file major versions](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-1.html#jvms-1.2): mapping Java 1.0–26 và tính tương thích format.
- [Java SE 26 — JVMS `4.1, class file structure](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html#jvms-4.1): magic, minor/major version, preview rules và định dạng.
- [Java SE 26 — UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/UnsupportedClassVersionError.html): mô tả class error chính thức.
- [Java SE 25 — javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release`, `--source`, `--target` và điều kiện cross-compilation.
- [Java SE 26 — ClassFileVersion](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/ClassFileVersion.html): major/minor và preview interpretation.
- [Java SE 21 — ClassLoader.defineClass](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): lúc loader chuyển bytes thành runtime class.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): multi-release JAR, manifest và versioned entries.
- [Java SE 21 — javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): dùng `-verbose` để đọc major/minor.
