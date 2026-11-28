# Giới hạn tương thích class file và vòng đời tính năng preview trong Java 27

**Tính năng preview** cho phép nhà phát triển thử một thiết kế Java đã được mô tả và triển khai tương đối hoàn chỉnh nhưng **chưa trở thành phần vĩnh viễn của nền tảng**. Đổi lại, chương trình sử dụng preview phải chấp nhận **ràng buộc tương thích nghiêm ngặt với một bản phát hành Java cụ thể**, rủi ro thay đổi API/cú pháp và trách nhiệm cấu hình build/runtime rõ ràng.

Trong **Java 27** (phát hành ngày 15/09/2026), nguyên tắc đáng nhớ nhất là:

- Class file thông thường biên dịch cho Java 27 có phiên bản **`71.0`** (*major.minor*).
- Class file phụ thuộc tính năng preview **của Java 27** có phiên bản **`71.65535`**.
- Một JVM Java 27 chỉ nạp class file `71.65535` khi **`--enable-preview` được bật**.
- Class file preview của **Java 26 (`70.65535`)** không thể nạp bằng JVM Java 27, ngay cả khi bật `--enable-preview`.
- Bật preview ở compiler **không đồng nghĩa** mọi class file trong bản build tự động mang minor version `65535`; cần kiểm tra **class thực sự phụ thuộc preview** và artifact cuối cùng.
- Preview, incubator, experimental và final **là những trạng thái khác nhau** với cơ chế truy cập, vòng đời và rủi ro khác nhau.

Bài thuộc chương **Tính năng thử nghiệm có kiểm soát**, trong module **JAVA_VERSION_JAVA27 — Java 27 và các kiến thức liên quan**. Nội dung dùng quy tắc của đặc tả **Java SE 27** và các công cụ JDK vẫn được hỗ trợ. Ví dụ có sử dụng **JEP 532** như một trường hợp preview đang tồn tại trong Java 27; **không** áp dụng cú pháp preview đã lỗi thời từ những bản Java trước như thể nó vẫn là cú pháp hiện tại.

## 1. Trước tiên: Java “preview” nghĩa là gì?

Một preview feature là tính năng có **thiết kế, đặc tả và triển khai hoàn chỉnh cho giai đoạn thử nghiệm công khai**, nhưng **chưa có cam kết duy trì nguyên dạng trong các bản phát hành tương lai**.

Mục đích của vòng preview:

1. Thu nhận phản hồi từ ứng dụng thật, không chỉ từ prototype.
2. Phát hiện lỗi về tính nhất quán ngôn ngữ, type system hoặc khả năng sử dụng API.
3. Cho framework, IDE, analyzer và build tool có thời gian thích nghi.
4. Điều chỉnh đặc tả trước khi quyết định trở thành tính năng ổn định.
5. Có khả năng **tiếp tục preview, chuyển final hoặc bị loại bỏ** nếu không phù hợp.

Tính năng preview **không mặc định bật** khi build/chạy. Người dùng chấp nhận rủi ro qua cấu hình tường minh.

Điều này không có nghĩa “preview chỉ là mã thử chưa chạy được”: nó được đưa vào **feature release** để thử nghiệm thực tế. Tuy nhiên, không nên đưa vào core API của thư viện lâu dài mà không công bố rõ **JDK yêu cầu và kế hoạch nâng cấp**.

## 2. Phân loại: preview, incubator, experimental và final

| Trạng thái | Đặc điểm | Cách bật thường gặp | Rủi ro cần nhận diện |
| --- | --- | --- | --- |
| **Preview language/VM feature** | Tính năng ngôn ngữ/VM chưa vĩnh viễn; được đặc tả cho release | `--enable-preview` khi biên dịch và chạy | Cú pháp/semantics có thể đổi; class file preview phụ thuộc release |
| **Preview API** | API thư viện được cung cấp để thử nghiệm trước khi final | `--enable-preview` khi dùng preview API, theo contract JDK | API có thể đổi tên, hành vi, chữ ký |
| **Incubator module** | Module chứa API chưa final, được phân phối để lấy phản hồi | Thường cần thêm module qua `--add-modules` | Module/API có thể thay đổi, thay thế, bị loại |
| **Experimental VM feature** | Tùy chọn/runtime capability còn thử nghiệm ở mức JVM | Cấu hình tùy chọn VM tương ứng, đôi khi cần mở khóa experimental options | Hành vi/performance/flag có thể thay đổi theo JVM |
| **Final/standard** | Được đưa vào chuẩn/API chính thức | Thường không cần preview flag | Vẫn phải xét release tối thiểu, API/dependency compatibility |

**Không đồng nhất** các cờ sau:

- `--enable-preview`: chấp nhận các preview features của **release hiện hành**.
- `--add-modules jdk.incubator.vector`: yêu cầu module incubator cụ thể được resolve nếu có mặt trong JDK đang chạy.
- `-XX:+UnlockExperimentalVMOptions`: cho phép cấu hình một số tùy chọn VM mang trạng thái experimental; **không bật preview language feature**.
- `--enable-native-access`: cấp quyền thực hiện native access cho các module chỉ định; **không phải cờ preview**.

Với tính năng đã final, không nên tiếp tục hướng dẫn người học luôn bật `--enable-preview` theo thói quen của bản cũ.

## 3. Những tính năng vẫn ở giai đoạn thử nghiệm trong Java 27

Theo thông tin phát hành JDK 27 ngày **15/09/2026**, các JEP liên quan gồm:

| JEP | Tính năng | Trạng thái trong JDK 27 |
| --- | --- | --- |
| **JEP 532** | Primitive Types in Patterns, `instanceof`, and `switch` | **Fifth Preview** — tính năng ngôn ngữ |
| **JEP 531** | Lazy Constants | **Third Preview** — API thư viện |
| **JEP 533** | Structured Concurrency | **Seventh Preview** — API thư viện |
| **JEP 538** | PEM Encodings of Cryptographic Objects | **Third Preview** — API thư viện |
| **JEP 537** | Vector API | **Twelfth Incubator** — module `jdk.incubator.vector` |

Đây là **tình trạng của riêng JDK 27**. Số vòng “Third/Fifth/Seventh/Twelfth” không phải số version của JAR, không bảo đảm release tiếp theo sẽ final và không có nghĩa người dùng cần cài nhiều bản API song song.

Hai JEP khác của JDK 27 như **G1 là collector mặc định trong mọi môi trường (JEP 523)** và **Compact Object Headers by Default (JEP 534)** không được liệt kê như preview trong bảng này; không tự đánh dấu mọi tính năng mới là preview.

**Phạm vi bài học:** chúng ta sử dụng JEP 532 để chứng minh **class file version và cờ preview**. Các API preview/incubator ở các JEP khác chỉ được nêu để phân loại trạng thái, không cố tái hiện cú pháp chưa final hoặc dùng chúng như phương án thiết kế ổn định.

## 4. Cấu trúc phần đầu của một .class file

Theo Java Virtual Machine Specification (JVMS), một class file bắt đầu bằng các trường:

```text
Byte offset   Kích thước   Trường                Ví dụ Java 27
0             4 byte       magic                 0xCAFEBABE
4             2 byte       minor_version         0 hoặc 65535
6             2 byte       major_version         71
8             2 byte       constant_pool_count   Phụ thuộc class
...           ...          phần còn lại           metadata, bytecode...
```

Các số nhiều byte trong class file được lưu ở dạng **big-endian**. Cặp `major_version` và `minor_version` quyết định phiên bản định dạng class file:

```text
version = major_version.minor_version
        = 71.0       (class Java 27 thông thường)
        = 71.65535   (class phụ thuộc preview Java 27)
```

**Major version không phải phiên bản Maven/Gradle hoặc JAR manifest.** Nó thuộc từng class file riêng lẻ. Một JAR có thể chứa nhiều class file được biên dịch cho các release khác nhau, vì thế chỉ nhìn một class chưa bảo đảm cả JAR đều an toàn cho target runtime.

### 4.1. Không nhầm “class file version” với “Java version”

| Java SE release | Class file major thông thường | Preview class file |
| --- | ---: | --- |
| Java 17 | 61 | 61.65535 khi có preview của Java 17 |
| Java 21 | 65 | 65.65535 khi có preview của Java 21 |
| Java 23 | 67 | 67.65535 khi có preview của Java 23 |
| Java 24 | 68 | 68.65535 khi có preview của Java 24 |
| Java 25 | 69 | 69.65535 khi có preview của Java 25 |
| Java 26 | 70 | 70.65535 khi có preview của Java 26 |
| **Java 27** | **71** | **71.65535** |

Với class file từ Java 12 trở về sau (major từ 56), JVMS quy định minor chỉ được là **0 hoặc 65535**. Các bản Java trước đó có lịch sử sử dụng minor khác, nhưng không phải kiểu class file cần tạo khi biên dịch ứng dụng Java 27 hiện đại.

### 4.2. Phiên bản cho biết định dạng, không nói toàn bộ yêu cầu runtime

Class file `65.0` thường có thể được nạp trên JVM 27 vì JVM hiện hành hỗ trợ định dạng cũ; nhưng chương trình vẫn có thể thất bại nếu:

- API cần dùng đã vắng mặt hoặc bị loại khỏi runtime.
- Một dependency đi kèm chỉ hỗ trợ JDK mới hơn.
- Module/service configuration sai.
- Mã native hoặc OS dependency không tương thích.
- Quy tắc bảo mật hoặc quyền truy cập thay đổi.

Do đó **major/minor là điều kiện cần cho khả năng nạp class**, không phải chứng nhận mọi hành vi/ABI/API đều tương thích.

## 5. Quy tắc đặc biệt của minor version 65535

JVMS Java 27 xác định:

1. `71.0`: class file thông thường của Java 27.
2. `71.65535`: class file phụ thuộc preview của **Java 27**; JVM 27 chỉ nạp khi bật `--enable-preview`.
3. `70.65535`, `69.65535`, ...: class file preview **của những release cũ**; JVM 27 **không** nạp, ngay cả khi bật preview.
4. `72.0` hoặc cao hơn: class file của một release mới hơn khả năng hỗ trợ của JVM 27; JVM 27 không nạp.
5. Một class `71.0` không cần `--enable-preview` chỉ để vượt qua kiểm tra **class file version** (nhưng còn phải xét dependency/API mà nó sử dụng).

Trong đó, 65535 = `0xFFFF` — một giá trị đặc biệt của trường `minor_version` dạng 16-bit unsigned. Nó không phải “số patch” và không có nghĩa “preview number 65535”.

### 5.1. Vì sao preview bị khóa cứng theo release?

Giả sử một class được biên dịch bằng JDK 26 và sử dụng cú pháp preview của Java 26. Khi JDK 27 được phát hành, cú pháp đó có thể:

- Tiếp tục preview nhưng **được điều chỉnh**.
- Được chuyển thành cú pháp ổn định có khác biệt.
- Không còn được hỗ trợ.
- Giữ nguyên cú pháp nhưng thay quy tắc runtime/metadata liên quan.

Cho phép Java 27 chạy class preview từ Java 26 theo cơ chế tương thích nhị phân thông thường có thể **âm thầm áp dụng ngữ nghĩa sai**. Quy tắc major/minor ép người duy trì phải **biên dịch lại và kiểm chứng** với Java 27.

## 6. Bảng tương thích khi nạp class file

Bảng tập trung vào **quy tắc class file version**, giả định class hợp lệ và các dependency cần thiết khác sẵn có:

| Artifact/class file | JVM 26, preview tắt | JVM 27, preview tắt | JVM 27, preview bật |
| --- | --- | --- | --- |
| `70.0` (ổn định Java 26) | Được về format | Được về format | Được về format |
| `70.65535` (preview Java 26) | Không | **Không** | **Không** |
| `71.0` (ổn định Java 27) | **Không**, major quá mới | Được về format | Được về format |
| `71.65535` (preview Java 27) | **Không**, major quá mới | **Không** | **Được về format** |
| `72.0` (biên dịch cho release sau 27) | Không | Không | Không |

Với một JVM **sau Java 27**, class `71.0` nhìn chung thuộc nhóm format đời trước và có thể được hỗ trợ. Nhưng **`71.65535` không tự trở nên hợp lệ trên release sau** dù runtime mới có `--enable-preview`: preview minor gắn với đúng Java 27.

### 6.1. Bật preview không nâng cấp JVM

`java --enable-preview` chỉ bật preview features của **JDK đang chạy**. Nó **không**:

- Cho JVM 26 hiểu class file `71.0`.
- Cho JVM 27 hiểu class file `72.0`.
- Cho JVM 27 chạy class preview `70.65535` của Java 26.
- Kích hoạt incubator module khi module chưa được resolve.
- Sửa bytecode lỗi hoặc dependency thiếu.

Đây là sự khác biệt quan trọng giữa **quyền sử dụng preview** và **khả năng đọc một định dạng class file**.

## 7. Biên dịch mã preview trong JDK 27

Để biên dịch **preview language feature của Java 27**, sử dụng compiler JDK 27 cùng:

```bash
javac --enable-preview --release 27 -d out PreviewLongSwitch.java
```

Hoặc:

```bash
javac --enable-preview -source 27 -d out PreviewLongSwitch.java
```

Trong hai dạng, **`--enable-preview` phải đi cùng `--release 27` hoặc `-source 27`**. Khi cần giới hạn cả mức ngôn ngữ, API chuẩn và class-file target, `--release` thường thích hợp hơn.

Không thể dùng JDK 27 để bật **preview language features của một release cũ** bằng lệnh:

```bash
# Không phải quy trình hợp lệ để biên dịch preview của Java 26:
javac --enable-preview --release 26 PreviewLongSwitch.java
```

Quy tắc là **preview của bản JDK hiện tại**, không phải cơ chế “chọn mọi preview từ lịch sử”.

### 7.1. Biên dịch không đồng nghĩa chạy được

Sau khi tạo class phụ thuộc preview, runtime cũng cần:

```bash
java --enable-preview -cp out PreviewLongSwitch
```

Nếu bỏ `--enable-preview`, JVM 27 từ chối class preview; lỗi phát sinh ở khâu nạp class, không phải “chạy được nhưng tính năng tự tắt”.

**Cờ compile và cờ runtime là hai việc tách biệt.** Maven/Gradle compile thành công với preview không đảm bảo JUnit, IDE launcher, ứng dụng trong Docker hay JavaExec cũng tự bật cờ này.

## 8. Ví dụ Java 27 thật: long trong switch (JEP 532)

JEP 532 của Java 27 cho phép dùng các **primitive types** theo cách mới trong `switch` và pattern matching. Đoạn dưới dùng `long` làm selector của switch expression, là tình huống cần preview trong Java 27.

Tạo file `PreviewLongSwitch.java`:

```java
public final class PreviewLongSwitch {

    private PreviewLongSwitch() {}

    static String classify(long value) {
        return switch (value) {
            case 0L -> "zero";
            case long n when n < 0L -> "negative";
            default -> "positive";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(-7L));
        System.out.println(classify(0L));
        System.out.println(classify(27L));
    }
}
```

Biên dịch/running bằng **JDK 27**:

```bash
javac --enable-preview --release 27 -d out PreviewLongSwitch.java
java --enable-preview -cp out PreviewLongSwitch
```

Kết quả:

```text
negative
zero
positive
```

Phân tích:

- `switch (value)` có selector là `long`, chứ không phải `int`.
- `case long n when n < 0L` tạo type pattern có guard.
- `case 0L` xử lý chính xác trường hợp 0.
- `default` trả về các giá trị dương.
- Bài học ở đây là **vòng đời preview và class-file boundary**, không khuyến nghị dùng cú pháp này trong public library cần tương thích nhiều JDK.

### 8.1. Cảnh báo compiler là tín hiệu review

Khi dùng preview, `javac` có thể phát thông báo/cảnh báo để nhắc rằng mã dùng tính năng chưa final. Hướng dẫn JDK mô tả việc kiểm tra chi tiết thông báo bằng `-Xlint:preview` khi cần.

Không nên mặc định **ẩn mọi warning preview** trong pipeline. Việc bật preview phải là quyết định rõ của nhóm, kèm tests và ghi nhận release support; nếu muốn áp `-Werror`, hãy thử trên đúng compiler Java 27 để hiểu warning nào được phân loại và cách toolchain tương tác.

## 9. Đọc class-file major/minor bằng javap

JDK cung cấp `javap -verbose` để xem metadata của class đã biên dịch:

```bash
javap -verbose -classpath out PreviewLongSwitch
```

Trong output, tìm:

```text
minor version: 65535
major version: 71
```

Đây là hai dòng minh họa giá trị dự kiến của class dùng preview Java 27; `javap -verbose` còn có nhiều metadata khác như constant pool, flags và bytecode.

Một ví dụ **không sử dụng preview**:

```java
public final class StableGreeting {
    public static void main(String[] args) {
        System.out.println("Java 27 stable class");
    }
}
```

Biên dịch bằng:

```bash
javac --release 27 -d out StableGreeting.java
javap -verbose -classpath out StableGreeting
```

Trường phiên bản dự kiến:

```text
minor version: 0
major version: 71
```

**Quan trọng:** hai class có thể cùng target Java 27 nhưng **chỉ class phụ thuộc preview** mới cần phiên bản preview. Không được suy ra cả output folder hoặc cả JAR là preview chỉ vì một compiler invocation có `--enable-preview`.

### 9.1. Kiểm tra file .class cụ thể

```bash
javap -verbose out/PreviewLongSwitch.class
```

Cú pháp file path trực tiếp giúp phân tích artifact không nằm trong classpath runtime. Với multi-release JAR, cần chọn **đúng entry** theo version trước khi kết luận; `javap` khi truyền JAR qua classpath có thể chỉ lấy entry ở base version.

## 10. Đọc chính xác header class file bằng API chuẩn

Nếu muốn tự viết một công cụ quét class files, chỉ cần đọc 8 byte đầu để nhận diện magic/major/minor. Dùng `DataInputStream` là đủ cho mục đích này và **không phải tải class bằng JVM**.

Tạo file `ClassFileHeader.java`:

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ClassFileHeader {

    private static final int CLASS_MAGIC = 0xCAFEBABE;

    private ClassFileHeader() {}

    public static void main(String[] args) throws IOException {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "Usage: ClassFileHeader <file.class> ...");
        }

        for (String name : args) {
            inspect(Path.of(name));
        }
    }

    private static void inspect(Path classFile) throws IOException {
        try (DataInputStream input =
                     new DataInputStream(Files.newInputStream(classFile))) {

            int magic = input.readInt();
            if (magic != CLASS_MAGIC) {
                throw new IOException("Không phải .class: " + classFile);
            }

            int minor = input.readUnsignedShort();
            int major = input.readUnsignedShort();

            boolean preview = minor == 65535;
            System.out.printf("%s: %d.%d%s%n",
                    classFile, major, minor,
                    preview ? " (preview)" : "");
        }
    }
}
```

Lệnh minh họa:

```bash
javac --release 27 -d out ClassFileHeader.java
java -cp out ClassFileHeader \
  out/StableGreeting.class \
  out/PreviewLongSwitch.class
```

Kết quả (đường dẫn tùy OS):

```text
out/StableGreeting.class: 71.0
out/PreviewLongSwitch.class: 71.65535 (preview)
```

Ưu điểm: chương trình **đọc header như dữ liệu**, nên không cần bật preview để **kiểm tra file đã có**. Nó không gọi `Class.forName` và không thực thi bytecode của class đang quét.

Giới hạn: ví dụ chỉ đọc 8 byte đầu, **không kiểm tra toàn bộ class format** và chưa xử lý quét JAR, ZIP entry, multi-release JAR hoặc xác minh chữ ký artifact. Khi xây scanner thật, cần giải nén/đọc từng class entry theo định dạng và kiểm tra input độc hại.

### 10.1. Class-File API là lựa chọn hiện đại cho công cụ chuyên sâu

Java 27 còn cung cấp **`java.lang.classfile`** (*Class-File API*, đã trở thành API chuẩn trong JDK 24). Nó hỗ trợ parse và transform class files có cấu trúc, tiện hơn việc tự đọc constant pool và attributes nếu bạn cần phân tích ngoài header.

Ví dụ fragment trong công cụ Java 27:

```java
import java.lang.classfile.ClassFile;
import java.nio.file.Path;

var model = ClassFile.of().parse(Path.of("out/StableGreeting.class"));
System.out.println(model.majorVersion()); // 71
System.out.println(model.minorVersion()); // 0

int previewMarker = ClassFile.PREVIEW_MINOR_VERSION; // 65535
```

Đây là **fragment bên trong phương thức có xử lý IOException**, không phải file độc lập. Mục đích là chỉ ra API Java SE hiện hành, **không sử dụng API nội bộ `com.sun.tools.classfile`**.

## 11. “UnsupportedClassVersionError” không phải lúc nào cũng do preview

Khi JVM không thể nạp class file có version không hỗ trợ, bạn có thể thấy `UnsupportedClassVersionError`. Phải phân biệt:

| Tình huống | Bản chất | Hướng xử lý |
| --- | --- | --- |
| JVM 26 nạp class `71.0` | Major quá mới | Dùng runtime 27 hoặc biên dịch về release được hỗ trợ nếu code/API cho phép |
| JVM 27 nạp `71.65535` khi preview tắt | Class preview của đúng JDK nhưng chưa bật | Bật `--enable-preview` **theo policy** hoặc loại preview khỏi artifact |
| JVM 27 nạp `70.65535` | Preview class của **JDK 26** | Biên dịch lại theo JDK 27, cập nhật cú pháp/API |
| JVM 27 nạp `71.0` nhưng thư viện thiếu | Version class hợp lệ, dependency lỗi | Kiểm tra module path/classpath và thư viện |
| JVM 27 không load class do bytecode malformed | Không phải chỉ vấn đề preview | Kiểm tra generator/bytecode transformer, build cache |

Thông báo lỗi chính xác có thể khác theo JVM và điểm thất bại. Không sửa bằng cách thêm `--enable-preview` vào mọi command line khi **major quá mới** hoặc **preview major thuộc release khác**.

## 12. --release và khả năng tương thích với JDK thấp hơn

`javac --release N` giúp biên dịch source theo **ngôn ngữ, class-file format và API công khai của release N** được compiler hỗ trợ.

Ví dụ thư viện cần chạy trên Java 21 nhưng build bằng JDK 27:

```bash
javac --release 21 -d out StableGreeting.java
javap -verbose -classpath out StableGreeting
```

Kết quả class file của bài ví dụ:

```text
minor version: 0
major version: 65
```

Việc chọn `--release 21` không làm tất cả runtime dependencies tương thích với Java 21. Mỗi JAR, annotation-generated class, plugin và native dependency vẫn phải được kiểm tra riêng.

**Không có chế độ hợp lệ “`--release 21 --enable-preview` trên JDK 27 để lấy preview Java 21”.** Preview language features được mở cho **JDK release đang chạy**, còn source cần biên dịch cho release cũ phải dùng giải pháp đã final trong release cũ.

### 12.1. -source/-target không phải công cụ thay thế đầy đủ

`-source` đặt quy tắc ngôn ngữ; `-target` kiểm soát version class-file. Khi cần bảo đảm code không tham chiếu **API Java SE xuất hiện sau target release**, nên ưu tiên `--release` theo hợp đồng compiler.

Không tự sửa `major_version` bằng hex editor hoặc bytecode transformer chỉ để chạy class ở JDK cũ. Những instruction, constant pool entries, API hoặc semantics mới có thể không tương thích dù bạn đổi hai byte trong header.

## 13. Preview language và preview API không nhất thiết có cùng dấu vết

Phải phân biệt **cú pháp nguồn**, **tham chiếu API** và **class-file version**:

- Dùng một **preview language feature** khiến compiler có thể phải đánh dấu class file phụ thuộc preview của release đó.
- Dùng một **preview API** có thể cần cấu hình compiler/runtime và version API tương ứng, dù source nhìn giống một lời gọi phương thức bình thường.
- Không phải mọi call site liên quan preview đều có cùng kiểu metadata hay đường dẫn tải class; cần kiểm tra **artifact thực tế**, JEP và Javadoc.
- Một class file `71.0` không tự chứng minh dự án hoàn toàn không phụ thuộc **preview API**, incubator module, library chưa final hoặc đặc quyền runtime. Vì vậy scanner header chỉ là **một quality gate**, không phải kiểm thử tương thích toàn diện.

Ví dụ tên API preview của JDK 27 cần được kiểm tra qua JEP/Javadoc: **Structured Concurrency (JEP 533)** và **Lazy Constants (JEP 531)**. Bài không viết code gọi các API đó vì chúng vẫn thuộc preview; sử dụng chúng trong sản phẩm thật phải đánh giá riêng chính sách nâng cấp.

## 14. Vòng đời một tính năng preview: không có “tự động final”

Một tính năng có thể đi qua nhiều vòng:

```text
Đề xuất JEP
    │
    ▼
Preview lần 1 (JDK N)
    │
    ├──► Preview lần 2 (JDK N+1)
    │           │
    │           ├──► Preview lần 3, ... (có thể thay đổi)
    │           │
    │           └──► Final
    │
    ├──► Final (nếu thiết kế đủ chín)
    │
    └──► Removed/Withdrawn/Thay thiết kế (nếu không phù hợp)
```

Mỗi vòng preview là một **cam kết theo release hiện tại**, không phải một lời hứa rằng preview của JDK N sẽ giữ nguyên ở JDK N+1.

| Trạng thái | Điều người dùng cần làm |
| --- | --- |
| Một JEP mới ở vòng preview đầu | Đọc JEP/đặc tả, thử trong nhánh thí nghiệm và ghi feedback |
| JEP được preview lần tiếp theo | So sánh JEP mới với vòng trước, cập nhật source và test |
| JEP được final | Chuyển sang API/cú pháp chuẩn của bản final, loại flag preview nếu không còn cần |
| JEP bị loại hoặc thay thế | Viết lại phần phụ thuộc, loại import/cú pháp/tùy chọn không còn |
| JDK ứng dụng đổi nhưng JEP vẫn preview | **Recompile** với release mới, không dùng class file preview cũ |

**Đừng đoán vòng đời bằng số phiên bản preview:** “Seventh Preview” không có nghĩa là chắc chắn sẽ final ở vòng tám. JDK 27 có các API preview đã qua nhiều vòng, nhưng tình trạng vẫn là preview ở đúng release này.

### 14.1. JEP, đặc tả và release notes đóng vai trò khác nhau

- **JEP:** mục tiêu, động cơ, lịch sử thay đổi, trạng thái và lý do thiết kế.
- **Java Language Specification / JVM Specification:** quy tắc ngôn ngữ hoặc class-file semantics có hiệu lực cho release.
- **Javadoc Java SE:** API, exception, annotation và quyền sử dụng cụ thể.
- **JDK release notes:** thay đổi khi phát hành, cảnh báo compatibility và những phần bị loại bỏ.
- **Migration guide:** ảnh hưởng lên code cũ và các bước nâng cấp thực tế.

Một hướng dẫn trên blog từ năm trước có thể dùng đúng cú pháp của **vòng preview trước** nhưng không còn đúng trong Java 27. Với mục tiêu “chỉ kiến thức vẫn áp dụng hiện giờ”, phải tra JEP/JLS của đúng phiên bản, không sao chép đoạn code cũ vô điều kiện.

## 15. Nâng cấp mã preview từ Java 26 lên Java 27

Giả sử một ứng dụng dùng JEP ở trạng thái preview khi chạy Java 26, và nhóm muốn chuyển sang Java 27.

**Không** chỉ thay image từ JDK 26 lên 27:

```text
Artifact cũ:
  class file 70.65535
          │
          ▼
  JVM 27 --enable-preview
          │
          └──► Không nạp: preview của release cũ
```

Quy trình thích hợp:

1. Xác định tính năng preview được dùng và **JEP tương ứng của Java 27**.
2. So sánh thay đổi API, type rules, cú pháp, module và phạm vi feature.
3. Kiểm tra build tool, IDE, formatter và static analyzer hỗ trợ Java 27.
4. Biên dịch lại **từ source** bằng JDK 27 với `--enable-preview --release 27` nếu feature còn preview.
5. Kiểm tra class files của artifact mới: phần phụ thuộc preview phải tương ứng **71.65535**.
6. Chạy test, integration test và workload trên **JDK 27** cùng cờ runtime.
7. Chạy canary/staging trước khi thay rollout production (nếu chính sách tổ chức cho phép preview).
8. Cập nhật compatibility matrix và ghi rõ yêu cầu JDK 27 khi phát hành artifact.

Nếu cú pháp hoặc API thay đổi, cần **sửa source**, không thể mong recompile sẽ luôn thành công.

### 15.1. Nếu tính năng đã final ở release mới thì sao?

Khi một tính năng chuyển final:

- Tìm **cú pháp/API final thực tế**, không mặc nhiên giữ nguyên đoạn preview.
- Sửa và biên dịch dưới release final **không cần `--enable-preview`** nếu code không dùng preview nào khác.
- Xem lại bytecode/JAR, và thêm test so sánh semantics quan trọng.
- Không kỳ vọng class file `70.65535` đã tạo trước đó tự tương thích với JVM 27 chỉ vì một đặc trưng có vẻ giống nay đã final.

**Tương thích nguồn** và **tương thích class file** là hai vấn đề khác nhau. Việc feature trở thành final không làm các class preview của bản cũ tự đổi minor version về 0.

## 16. Nâng từ Java 27 lên release tương lai

Giả sử sau này hệ thống chuyển từ Java 27 sang Java 28:

| Artifact | Kiểu compatibility nên kỳ vọng |
| --- | --- |
| Class `71.0`, chỉ dùng API ổn định | Có thể vẫn tương thích ở mức class-file format, nhưng cần kiểm thử dependencies |
| Class `71.65535` | **Không** thể nạp trực tiếp trên JVM phát hành sau Java 27 |
| Source dùng JEP 532/JEP 531/JEP 533/JEP 538 | Cần kiểm tra trạng thái và thay đổi của từng JEP ở release mới |
| Artifact chỉ chứa class ổn định nhưng runtime flags vẫn có `--enable-preview` | Không phải bằng chứng có preview dependency; có thể loại flag sau khi kiểm toán |

Không viết trước rằng Java 28 **chắc chắn** final hoặc giữ nguyên API nào: khi chuẩn bị nâng cấp, phải tra tài liệu Java 28 đã phát hành. Điều có thể khẳng định từ JVMS là **preview class file gắn với đúng release**.

## 17. API boundary: vì sao preview nguy hiểm hơn khi xuất bản thư viện?

Với ứng dụng nội bộ, nhóm có thể khóa **source, compiler, container image và runtime** cùng JDK 27. Với **thư viện public**, consumer có thể dùng:

- Java 21 hoặc 25 (không hiểu class-file major 71).
- Java 27 nhưng không cho phép `--enable-preview`.
- Một JDK sau Java 27, nơi preview class `71.65535` bị từ chối.
- Một build tool hoặc analyzer chưa hỗ trợ cú pháp preview.

Nếu public API của thư viện mang type hoặc contract của preview API, sự phụ thuộc có thể **lan sang mã nguồn consumer**, ngay cả khi consumer không trực tiếp dùng cú pháp preview.

### 17.1. Phương án cô lập preview

```text
            Ứng dụng/lõi ổn định
                    │
        API ổn định, contract rõ
                    │
                    ▼
          preview-adapter module
                    │
           JDK 27 + preview flags
                    │
                    ▼
             Preview feature
```

Nguyên tắc:

1. Tách preview khỏi public API lâu dài nếu có thể.
2. Dùng interface ổn định cho ranh giới; giảm việc lộ preview types.
3. Ghi rõ artifact nào chỉ dành cho **JDK 27 với preview bật**.
4. Duy trì test của adapter theo đúng JDK và vòng preview hiện tại.
5. Có đường fallback dựa trên API chuẩn khi preview bị loại/thay.
6. Không vô tình kéo preview feature vào dependency graph chung của mọi consumer.

Cách cô lập này không xóa giới hạn preview; nó **giới hạn phạm vi phải sửa** khi nâng JDK.

### 17.2. Tài liệu phụ thuộc cần ghi rõ

Nếu phải phân phối preview artifact, thông tin tối thiểu gồm:

- **JDK/Java SE release chính xác** (Java 27), không chỉ “Java 17+”.
- Cờ compile/runtime cần thiết.
- JEP và vòng preview đang dùng.
- Module/JAR nào chứa class phụ thuộc preview.
- Các tổ hợp JDK và ứng dụng đã kiểm thử.
- Kế hoạch support/migration khi release Java tiếp theo xuất hiện.
- Chính sách security updates và triển khai môi trường thử nghiệm.

## 18. Multi-release JAR không xóa ràng buộc preview

Một multi-release JAR có thể chứa các class cho nhiều bản Java:

```text
library.jar
  ├── META-INF/MANIFEST.MF
  ├── com/example/Api.class                    (base)
  └── META-INF/versions/27/com/example/Api.class
```

Khi được khai báo và đóng gói đúng theo **multi-release JAR specification**, runtime lựa chọn class phù hợp với phiên bản Java đang chạy. Nhưng:

- Nếu entry `META-INF/versions/27/...` chứa **`71.65535`**, nó chỉ phù hợp với **JVM 27 có bật preview**.
- Ở JVM sau 27, thuật toán multi-release có thể **vẫn chọn version 27** nếu không có override thích hợp, rồi gặp class preview của release cũ và bị từ chối.
- Một base entry `65.0` không cứu được runtime nếu entry version cao hơn đã được chọn và không nạp được.
- JAR manifest và đường dẫn entry không tự chuyển một class preview thành class stable.

Vì vậy không coi multi-release JAR là phương pháp đóng gói **preview API phổ quát cho mọi JDK**. Nếu cần cung cấp nhiều runtime, ưu tiên tách artifact hoặc đảm bảo các entry lựa chọn thực tế không mang preview class files ngoài môi trường thử nghiệm được kiểm soát.

### 18.1. jdeps/javap và entry multi-release

Công cụ kiểm tra phải phân biệt **base version** và **versioned entries**. Dùng:

```bash
jar --list --file library.jar
javap -verbose -classpath library.jar com.example.Api
```

Các lệnh trên giúp kiểm kê nhưng **chỉ xem một kết quả class từ classpath chưa đủ** cho multi-release JAR. Với `javap`, có thể sử dụng `--multi-release 27` hoặc trỏ trực tiếp tới entry theo dạng URL được tài liệu `javap` hỗ trợ để kiểm tra đúng version. Với quá trình quét toàn diện, nên mở JAR như ZIP và xem **tất cả các .class entries**, kể cả bên dưới `META-INF/versions/`.

## 19. Gradle: bật preview có kiểm soát

Với Gradle Kotlin DSL, ví dụ fragment trong `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(27)
    options.compilerArgs.add("--enable-preview")
}

tasks.withType<Test>().configureEach {
    jvmArgs("--enable-preview")
}

tasks.withType<JavaExec>().configureEach {
    jvmArgs("--enable-preview")
}
```

Ý nghĩa:

1. Java toolchain chọn compiler JDK 27.
2. `options.release.set(27)` kiểm soát source/API/bytecode target.
3. `compilerArgs` bật preview cho các Java compile tasks trong phạm vi cấu hình.
4. Test JVMs cần `--enable-preview` khi nạp class preview.
5. Các `JavaExec` tasks cần cờ runtime tương ứng.

**Đây là đoạn cấu hình để áp dụng có chủ đích**, không phải lời khuyên bật preview cho mọi project. Trong thực tế còn phải:

- Xác nhận Gradle wrapper **hỗ trợ JDK 27** ở chế độ chạy và toolchain provisioning.
- Xác nhận JUnit engine, formatter, annotation processors và analyzer hỗ trợ source/class file Java 27.
- Kiểm tra các task khác ngoài JavaCompile/Test/JavaExec (integrationTest custom tasks, shadow JAR, native image, IDE run configurations...).
- Kiểm soát cờ ở **container launcher** nếu artifact được deploy.
- Tách module preview khỏi những source sets/artifacts ổn định nếu có thể.

### 19.1. Bật ở đúng module cần thử nghiệm

Với monorepo có nhiều module, không áp dụng toàn bộ build `subprojects { ... --enable-preview ... }` nếu chỉ một module dùng preview. Giữ module production ổn định càng độc lập càng tốt, với quality gate chặn class `71.65535` trong artifact không được phép.

Nếu một source set có code ổn định và preview lẫn nhau, compiler có thể vẫn tạo class `71.0` cho những file không phụ thuộc preview; nhưng việc **chia module rõ ràng** vẫn giúp phạm vi dependency và runtime flags dễ kiểm soát hơn.

## 20. Maven: cấu hình compiler và test runtime cùng release

Trong Maven, một ví dụ cấu hình **rút gọn**:

```xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <compilerArgs>
                    <arg>--enable-preview</arg>
                </compilerArgs>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.4</version>
            <configuration>
                <argLine>--enable-preview</argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây chỉ là **phần tử bên trong POM**; một file `pom.xml` thực tế cần đầy đủ cấu trúc, dependency/test engine và bản plugin đã được xác minh trên dự án. Các version plugin được ghi **tường minh làm ví dụ cấu hình**, không phải khẳng định đó là version mới nhất hoặc mặc nhiên tương thích với mọi tính năng Java 27.

Những điểm phải xác minh:

- Maven thực sự chạy bằng JDK/toolchain phù hợp.
- Compiler plugin truyền `--enable-preview` tới đúng `javac 27`.
- Surefire truyền cờ vào **test JVM được fork**.
- Nếu dùng Failsafe, cần cấu hình riêng cho integration tests của plugin đó.
- `exec:java`, IDE launcher, Docker `java -jar` hoặc framework run plugin có thể cần cách truyền preview flag **khác**.
- Nếu JaCoCo hoặc bytecode analyzer báo lỗi class version, kiểm tra version hỗ trợ JDK 27; không tắt bytecode verification để che vấn đề.

### 20.1. Tách thử nghiệm khỏi build release

Một chính sách an toàn hơn khi công ty phát hành thư viện phổ biến:

- Module chính: build không preview, dùng API ổn định.
- Module thử nghiệm: cấu hình preview có điều kiện qua profile/project riêng.
- Test của module thử nghiệm: chạy trên **đúng JDK 27**.
- Publish: chặn hoặc phân loại rõ artifact preview; không vô tình đưa vào repository dùng chung.
- CI: có job test chuyển từ Java 26 preview sang Java 27 preview khi được phân công nâng JDK.

## 21. Các công cụ khác: java, jshell, javadoc, IDE và container

| Công cụ/bối cảnh | Cấu hình cần cân nhắc |
| --- | --- |
| `javac` | `--enable-preview --release 27` |
| `java` classpath | `java --enable-preview -cp out Main` |
| `java` JAR | `java --enable-preview -jar app.jar` |
| `java` module | `java --enable-preview --module-path mods -m module/main.Class` |
| `jshell` | `jshell --enable-preview` |
| `javadoc` | `javadoc --enable-preview --source 27 ...` nếu tài liệu bao gồm preview constructs |
| Unit/integration test | Cờ preview phải có trên **JVM test** nạp class preview |
| IDE | Chọn JDK/language level phù hợp, bật preview trong compiler **và run configuration** |
| Docker/Kubernetes | Image/runtime JDK 27 và java command line bật preview nếu artifact yêu cầu |

**Không có bảo đảm** IDE tự truyền flags của Gradle cho mọi kiểu run configuration riêng, hoặc container dùng cùng Java runtime như máy phát triển.

### 21.1. Ví dụ Docker entrypoint

```dockerfile
# Bản minh họa: dùng base image JDK 27 đã được kiểm chứng của tổ chức.
# FROM <trusted-java27-runtime-image>

COPY app.jar /app/app.jar
ENTRYPOINT ["java", "--enable-preview", "-jar", "/app/app.jar"]
```

Đây là fragment về **lệnh khởi chạy**, không phải Dockerfile build được ngay vì dòng `FROM` thực đã bị để ở dạng comment. Hệ thống thật phải chọn runtime image tin cậy, cập nhật security patches và kiểm tra cả dependency compatibility.

Nếu production không được phép dùng preview, phải **loại preview code khỏi artifact** và **loại cờ khỏi ENTRYPOINT**, không chỉ xóa `--enable-preview` và chờ JVM tự xử lý.

## 22. Quality gate: phát hiện class file preview trước khi phát hành

Một pipeline phát hành nên biết **release target và preview policy**.

Ví dụ quy trình:

```text
Source + JDK 27 toolchain
       │
       ├─► javac (stable/preview policy)
       │
       ▼
Generated .class / packaged .jar
       │
       ▼
Scan major/minor version của TẤT CẢ .class entries
       │
       ├─ major > supported target  ──► FAIL
       ├─ minor = 65535, policy cấm ──► FAIL
       ├─ minor = 65535, policy cho phép
       │      ├─ major == target's class major? ──► continue
       │      └─ khác? ───────────────────────────► FAIL
       └─ class thường ────────────────────────────► continue
                          │
                          ▼
                 Integration tests
                          │
                          ▼
                     Release/canary
```

Khi xây scanner, lưu ý:

1. Quét **mọi JAR/class thuộc dependency runtime cuối cùng**, không chỉ class của source module.
2. Quét cả multi-release entries.
3. Phân biệt class files do annotation processors và bytecode generators tạo ra.
4. Đọc đúng `u2 minor_version` ở offset 4 và `u2 major_version` ở offset 6; verify `CAFEBABE`.
5. Kiểm tra policy của mỗi artifact; preview có thể được phép trong một test fixture nhưng cấm trong public library.
6. Tách **class-file gate** khỏi **dependency/API gate**: không thể tìm mọi preview API chỉ bằng minor bit.

### 22.1. Mẫu báo cáo CI

```text
Target runtime: Java 27
Preview policy: forbidden for public-library artifacts

artifact: core-api.jar
  class files scanned: 164
  max major: 71
  preview marker (minor=65535): 0
  decision: PASS

artifact: preview-adapter.jar
  class files scanned: 13
  preview marker (minor=65535): 2
  preview release: Java 27
  decision: ISOLATED / NOT PUBLISHED TO STABLE REPOSITORY
```

Đây là **dữ liệu báo cáo minh họa**, không phải kết quả chạy thực tế trên một repository. CI cần tạo báo cáo từ bytecode thật và lưu policy của release tương ứng.

## 23. Kiểm thử thực tế ở ranh giới phiên bản

Một test matrix hữu ích:

| Test | Kỳ vọng |
| --- | --- |
| Biên dịch `StableGreeting.java` với `--release 27` | Thành công, `71.0` |
| Biên dịch `PreviewLongSwitch.java` không có `--enable-preview` | Compiler từ chối cú pháp preview |
| Biên dịch PreviewLongSwitch bằng `--enable-preview --release 27` | Thành công, `71.65535` |
| Chạy PreviewLongSwitch trên JVM 27, preview tắt | JVM từ chối nạp preview class |
| Chạy PreviewLongSwitch trên JVM 27, preview bật | Chạy và in ba dòng như ví dụ |
| Chạy class `71.0` trên JVM 26 | Class version quá mới |
| Đưa class `70.65535` vào JVM 27, preview bật | Không được nạp |
| Biên dịch source ổn định với `--release 21` (nếu toolchain hỗ trợ) | Class `65.0` |
| Test code preview trong Gradle/Maven | JVM test cũng nhận flag preview |
| Scanner quét packaged JAR | Không bỏ sót generated/MR-JAR entries |
| Nâng JDK 27 lên bản sau | Preview code được recompile và test lại, không dùng artifact cũ |

Không cần **cố tình sửa bytecode** để tạo class sai version cho test. Có thể dùng artifact hợp lệ được biên dịch bởi JDK tương ứng trong một môi trường thử nghiệm có kiểm soát.

## 24. Các lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
| --- | --- | --- |
| “Java 27 nghĩa là class version 27” | Java 27 dùng major **71** | Kiểm tra JVMS/Javap |
| “`--enable-preview` làm JVM đọc mọi class mới” | JVM 27 vẫn giới hạn major tối đa 71 | Dùng đúng runtime release |
| “Java 27 có thể chạy preview Java 26” | `70.65535` bị từ chối ở Java 27 | Recompile/migrate source |
| “Preview bật một lần thì không cần bật ở runtime” | Compile và run là hai quy trình | Cấu hình cả compiler lẫn launcher |
| “`--release 21 --enable-preview` dùng preview cũ” | Preview chỉ dành cho JDK release hiện tại | Dùng API final của target cũ |
| “Cả JAR là preview nếu compiler có flag” | Marker nằm **trên từng class file** | Scan artifact thực tế |
| “Một class `71.0` không thể liên quan preview” | Có thể có dependency/API bất ổn ở runtime | Bổ sung dependency/API checks |
| “Class `71.65535` dùng Java 28 nếu bật preview” | Preview gắn chặt với Java 27 | Recompile theo release mới |
| “Final feature cho phép chạy preview bytecode cũ” | Old preview marker vẫn bị khóa version | Recompile theo cú pháp/API final |
| “Incubator module cần `--enable-preview`” | Incubator có cơ chế module riêng | Dùng module path và add-modules đúng |
| “Experimental VM option giống preview JEP” | Cờ experimental ở tầng VM khác preview class-file contract | Theo dõi tài liệu JVM flag |
| “Thay header .class cho major thấp hơn là tương thích” | Bytecode, constant pool và API vẫn có thể mới | Build bằng `--release` hợp lệ |
| “Multi-release JAR tự giải quyết preview” | JVM sau 27 vẫn có thể chọn class `71.65535` | Audit từng versioned entry |
| “Chỉ cần compile thành công để publish library” | Consumer có thể dùng JDK khác/không bật preview | Khai báo compatibility matrix và CI |
| “Mọi tính năng JDK 27 đều preview” | Có cả final/VM changes và incubator | Đọc JEP/release notes đúng từng tính năng |
| “Preview thứ bảy tức sắp final chắc chắn” | Không có bảo đảm lịch chuyển final | Theo dõi JEP từng release |
| “Các source trước đây chạy thì không cần đổi khi nâng JDK” | Preview language/API có thể thay đổi | Compile lại và chạy full tests |
| “Chỉ JVM production cần cùng release, build tool có thể cũ tùy ý” | Compiler/build/analyzer cũng có compatibility constraints | Pin và kiểm tra toolchain |

## 25. Chính sách nên dùng preview trong dự án nào?

**Không nên cấm tuyệt đối mọi thử nghiệm**; Java cần phản hồi từ ứng dụng thực tế để hoàn thiện tính năng. Nhưng mức độ chấp nhận cần khác nhau:

| Bối cảnh | Hướng tiếp cận |
| --- | --- |
| Học tập/thử nghiệm một JEP Java 27 | Dùng nhánh/module riêng, ghi rõ JDK 27 và bật preview |
| Prototype nội bộ có thể tái build thường xuyên | Cho phép có kiểm soát, ràng buộc toolchain/runtime và test |
| Ứng dụng production nội bộ, nhóm chấp nhận upgrade | Phải có owner, test matrix, rollback và migration plan |
| Public library hoặc SDK dùng cho nhiều JDK | Ưu tiên API final, **tránh public preview dependency** |
| Runtime image không kiểm soát được (khách hàng tự chọn JDK) | Không phân phối class file preview như lựa chọn mặc định |
| Plugin/framework ecosystem lớn | Đánh giá tooling, analyzer, bytecode transformer và dependency matrix |
| Công việc cần bảo đảm vận hành dài hạn ít nâng JDK | Ưu tiên tính năng đã final trong release hỗ trợ |

### 25.1. Tiêu chí “cho phép dùng preview” nên có bằng chứng

Một feature preview nên chỉ được chấp nhận khi đã xác định:

1. **Lợi ích cụ thể** so với API chuẩn hiện tại.
2. **JEP/vòng preview** đúng với JDK đang triển khai.
3. **Owner của migration** khi release sau xuất hiện.
4. **Phạm vi cô lập** (source set/module/artifact).
5. **Bộ test có thể chạy lại** trên JDK mới.
6. **Quy tắc CI/class file gate** rõ ràng.
7. **Trách nhiệm cập nhật compiler, runtime, plugins và container image**.
8. **Kế hoạch dừng dùng** nếu JEP đổi hoặc bị loại.
9. **Cách thông báo cho consumer** nếu artifact phải publish.
10. **Thời điểm review lại quyết định** ở mỗi lần nâng JDK.

## 26. Checklist trước khi build hoặc phát hành

1. Đang dùng **JDK 27 thật** hay chỉ khai báo target release 27?
2. Feature là **preview language**, **preview API**, **incubator**, **experimental VM**, hay đã final?
3. JEP cụ thể và vòng preview trong Java 27 đã được đối chiếu chưa?
4. Cờ compiler `--enable-preview --release 27` chỉ được bật ở nơi cần?
5. Runtime/test launcher có `--enable-preview` nếu phải nạp class preview không?
6. JDK 27 build có tạo đúng class `71.0` hoặc `71.65535` như mong đợi không?
7. Artifact có class mang **minor 65535 từ Java 26 hoặc cũ hơn** không?
8. Các JAR trong runtime classpath/module path đã được quét phiên bản chưa?
9. Multi-release JAR có versioned entries chứa preview class không?
10. Annotation processor, code generator, instrumenter và formatter hỗ trợ Java 27 chưa?
11. Nếu dùng incubator module, module đó được thêm đúng cách và còn tồn tại trên JDK 27 chưa?
12. IDE, Gradle/Maven, JUnit, integration tests và container launcher dùng JDK tương thích chưa?
13. Có preview types trong public API hoặc thư viện chia sẻ nhiều dự án không?
14. Có test migration khi chuyển JDK 26 → 27 hoặc 27 → release tiếp theo không?
15. Có sử dụng `--release` đúng mục tiêu tương thích cho code ổn định không?
16. Có policy loại `--enable-preview` khỏi production image nếu không sử dụng preview không?
17. Consumer đã được thông báo yêu cầu exact JDK/preview flags nếu cần chưa?
18. Có kế hoạch sửa source/rebuild khi JEP final, thay đổi hoặc bị loại không?
19. Đã phân biệt **class format compatibility** với **API/runtime behavior compatibility** chưa?
20. Quality gate có tránh việc sửa header bytecode giả tạo hoặc tắt verifier để qua build không?

**Ghi nhớ:** `71.0` biểu thị class file thông thường Java 27; **`71.65535` biểu thị phụ thuộc preview Java 27**. Compiler và runtime đều phải bật preview **của đúng Java 27**, còn class file preview từ release trước **không được tương thích ngược tự động**. Quy trình đúng là **đọc JEP → thử ở phạm vi cô lập → pin JDK/build/runtime → quét artifact → kiểm thử → chủ động migration mỗi release**.

## 27. Nguồn tham khảo chính thức Java 27

### 27.1. Đặc tả và JDK tools

- [Java Virtual Machine Specification, Java SE 27 — §1.5 Preview Features](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/jvms-1.html#jvms-1.5): định nghĩa, cách bật và ràng buộc preview theo release.
- [Java Virtual Machine Specification, Java SE 27 — §4.1 ClassFile](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/jvms-4.html#jvms-4.1): magic, major/minor, `71.0` và `71.65535`.
- [Java SE 27 — Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html): cú pháp bật preview bằng `javac`/`java` và vòng đời của tính năng.
- [The javac Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--enable-preview`, `--release`, `-source` và `-Xlint`.
- [The java Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `--enable-preview` khi khởi chạy class, JAR và module.
- [The javap Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html): `-verbose`, `--multi-release`, đọc class version.
- [java.lang.classfile.ClassFile — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html): `JAVA_27_VERSION`, `PREVIEW_MINOR_VERSION` và Class-File API.
- [java.lang.classfile.ClassFileVersion — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFileVersion.html): major/minor và khả năng nạp preview class.

### 27.2. JEP và trạng thái tính năng Java 27

- [JEP 12 — Preview Features](https://openjdk.org/jeps/12): mục đích, thiết kế và vòng đời feature preview.
- [JEP 532 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://openjdk.org/jeps/532): ví dụ preview language feature của JDK 27.
- [JEP 531 — Lazy Constants (Third Preview)](https://openjdk.org/jeps/531): preview API.
- [JEP 533 — Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533): preview API.
- [JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538): preview API.
- [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537): ví dụ về API incubator, không phải preview language feature.
- [Oracle — The Arrival of Java 27 (15 September 2026)](https://blogs.oracle.com/java/the-arrival-of-java-27): danh sách JEP và phân biệt preview/incubator/experimental.
- [Java SE 27 — Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html): quy tắc ngôn ngữ preview hiện hành.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): thay đổi phát hành và kiểm tra compatibility.

### 27.3. Đóng gói và công cụ build

- [JAR File Specification](https://docs.oracle.com/en/java/javase/27/docs/specs/jar/jar.html): cấu trúc JAR/multi-release JAR.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): chọn compiler/runtime và kiểm tra tương thích.
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): `release` và `compilerArgs`.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): JVM arguments cho test forks.
