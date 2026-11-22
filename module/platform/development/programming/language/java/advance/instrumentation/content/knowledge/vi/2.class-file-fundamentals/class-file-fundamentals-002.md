# Major version, minor version và tương thích của class file với JVM đích

## 1. Vì sao phải quan tâm đến phiên bản class file?

Một tệp `.class` chứa bytecode và metadata theo định dạng **Java Virtual Machine class file**. Khi biên dịch, `javac` (hoặc công cụ sinh bytecode) ghi cặp **`major_version.minor_version`** vào đầu tệp. Cặp số này giúp JVM và các công cụ đọc bytecode biết định dạng nào được sử dụng, từ đó quyết định có thể tiếp nhận class file hay không.

Ba phiên bản cần phân biệt:

- **Phiên bản JDK biên dịch**: JDK chạy `javac`, ví dụ JDK 21.
- **Phiên bản class file**: kết quả biên dịch, ví dụ `61.0` tương ứng định dạng Java 17 thông thường.
- **Phiên bản JVM đích**: JVM thực tế sẽ tải/chạy class, ví dụ runtime Java 17 trên máy chủ.

Các số đó **không nhất thiết giống nhau**: JDK 21 có thể dùng `javac --release 17` để tạo class file `61.0` cho JVM Java 17. Ngược lại, biên dịch mặc định trên JDK 21 thường tạo `65.0` và không chạy được trên JVM Java 17.

Quy tắc cốt lõi: **class file phải nằm trong tập phiên bản mà JVM đích hỗ trợ**, đồng thời thỏa điều kiện preview (nếu có), định dạng bytecode hợp lệ và các phụ thuộc/API khi liên kết, thực thi. Chỉ so sánh số major là bước sàng lọc đầu tiên, chưa phải bảo đảm tương thích hoàn toàn.

## 2. Cặp version nằm ở đâu trong tệp `.class`?

Theo JVMS `4.1, cấu trúc bắt đầu như sau:

```text
ClassFile {
    u4 magic;                 // 4 byte: 0xCAFEBABE
    u2 minor_version;         // 2 byte không dấu
    u2 major_version;         // 2 byte không dấu
    u2 constant_pool_count;   // bắt đầu từ offset 8
    ...
}
```

| Byte offset (tính từ 0) | Độ dài | Trường | Ý nghĩa |
| --- | ---: | --- | --- |
| `0..3` | 4 byte | `magic` | Bốn byte `CA FE BA BE` xác nhận dấu hiệu class file |
| `4..5` | 2 byte | `minor_version` | Phiên bản phụ, lưu **trước** major |
| `6..7` | 2 byte | `major_version` | Phiên bản chính |
| `8..9` | 2 byte | `constant_pool_count` | Số entry danh nghĩa của constant pool, không thuộc version |

`u2` là số nguyên **không dấu 16 bit** và được lưu theo thứ tự **big-endian**. Không đọc nhầm minor/major hoặc diễn giải hai byte theo little-endian.

Ví dụ tám byte đầu:

```text
CA FE BA BE  00 00  00 3D
| magic    |  minor  | major |
```

`0x003D = 61` nên đây là class file **`61.0`**, thường được sinh khi nhắm tới Java 17. Ví dụ khác, `CA FE BA BE 00 00 00 41` có major `0x41 = 65`, tức `65.0` (Java 21). Hai byte version chỉ là một phần của định dạng: sửa thủ công `00 41` thành `00 3D` không chuyển được các lệnh, constant-pool entries, attributes hay API mới thành phiên bản Java 17.

## 3. Ánh xạ major version sang bản phát hành Java

Bảng dưới thể hiện **major mới nhất gắn với mỗi bản Java**, không có nghĩa JVM của bản đó chỉ đọc được đúng một major. Đối với các release từ Java 5, quy tắc nhớ nhanh là **`major = 44 + số phiên bản Java`**; các bản Java 1.x đời đầu là ngoại lệ về cách đánh số release.

| Java/JDK release | Major | Class file thông thường |
| --- | ---: | --- |
| JDK 1.0, 1.1 | 45 | `45.x` (minor lịch sử thay đổi) |
| Java 1.2 | 46 | `46.0` |
| Java 1.3 | 47 | `47.0` |
| Java 1.4 | 48 | `48.0` |
| Java 5 | 49 | `49.0` |
| Java 6 | 50 | `50.0` |
| Java 7 | 51 | `51.0` |
| Java 8 | 52 | `52.0` |
| Java 9 | 53 | `53.0` |
| Java 10 | 54 | `54.0` |
| Java 11 | 55 | `55.0` |
| Java 12 | 56 | `56.0` |
| Java 13 | 57 | `57.0` |
| Java 14 | 58 | `58.0` |
| Java 15 | 59 | `59.0` |
| Java 16 | 60 | `60.0` |
| Java 17 | 61 | `61.0` |
| Java 18 | 62 | `62.0` |
| Java 19 | 63 | `63.0` |
| Java 20 | 64 | `64.0` |
| Java 21 | 65 | `65.0` |
| Java 22 | 66 | `66.0` |
| Java 23 | 67 | `67.0` |
| Java 24 | 68 | `68.0` |
| Java 25 | 69 | `69.0` |
| Java 26 | 70 | `70.0` |
| Java 27 | 71 | `71.0` |

Theo JVMS Java SE 27, JVM tuân thủ đặc tả đó hỗ trợ major **45 đến 71** (còn phải áp dụng quy tắc minor/preview). Vì vậy:

- `61.0` thường qua được kiểm tra **phiên bản class file** trên Java 17, 21 và 27; nó vẫn có thể hỏng ở bước khác.
- `65.0` bị JVM Java 17 từ chối vì major 65 cao hơn mức Java 17 hỗ trợ là 61.
- `71.0` cần JVM Java 27 trở lên có hỗ trợ định dạng đó; một JVM Java 21 không thể nạp class file 71.

Lưu ý: số `17` trong `--release 17` là **phiên bản Java**, còn số `61` đọc bằng `javap` là **major của class file**. Không dùng `major = 17` khi muốn nhắm Java 17.

## 4. Minor version và class file dùng preview

### 4.1. Trước và sau Java 12

- Với **major 45..55**, đặc tả cho phép trường minor nằm trong khoảng số `u2` (0..65535); các JVM/JDK lịch sử từng có tập minor được hỗ trợ khác nhau. Trong thực tế, các bản Java hiện đại trước Java 12 thường sinh `minor = 0` cho major mới của chúng.
- Từ **major 56** (Java 12) trở đi, `minor` hợp lệ chỉ có **`0` hoặc `65535`** (`0xFFFF`). Không hiểu minor theo kiểu “phiên bản vá” như `17.0.8` của JDK.
- `M.0` thể hiện class file không phụ thuộc preview theo cơ chế đánh dấu version này.
- `M.65535` (với `M >= 56`) đánh dấu **phụ thuộc preview của chính release đã sinh ra major M**; compiler có thể đánh dấu như vậy do tính năng preview của ngôn ngữ dù không có opcode preview riêng.

### 4.2. Preview ràng buộc chính xác vào release

Ví dụ với Java 21, major là 65:

| Class file | JVM Java 21 | JVM Java 22 hoặc mới hơn |
| --- | --- | --- |
| `65.0` | Qua kiểm tra version | Có thể qua kiểm tra version |
| `65.65535` | Chỉ được tải khi **bật preview** | **Bị từ chối**, dù có bật preview |

JVM Java 21 cần được chạy với `--enable-preview` để tải `65.65535`. Khi lên JVM Java 22, class preview của Java 21 **không** trở thành class Java 22 có thể sử dụng bằng cách bật lại cờ; phải biên dịch lại cho release phù hợp. Quy tắc này cũng áp dụng cho các major preview từ Java 12 trở đi (chẳng hạn `71.65535` gắn với Java 27).

Cú pháp minh họa **trên đúng JDK 21**, với mã nguồn thực sự dùng preview Java 21:

```bash
javac --enable-preview --release 21 PreviewExample.java
java --enable-preview PreviewExample
```

Đây là mẫu câu lệnh, không phải chương trình độc lập: `PreviewExample.java` phải tồn tại và chứa mã preview hợp lệ cho Java 21. `javac --enable-preview` chỉ dùng với source/release tương ứng **phiên bản JDK compiler hiện hành**, không thể lấy JDK 27 để biên dịch preview ngôn ngữ của Java 21 bằng `--release 21`.

**Hệ quả cho instrumentation:** nếu agent biến đổi class phụ thuộc preview, class đầu ra vẫn phải phù hợp đúng major/minor và runtime đó. Việc hạ minor từ `65535` xuống `0` không tự làm các construct preview trở thành tính năng ổn định.

## 5. JVM đích quyết định nạp class như thế nào?

Hình dung trình tự kiểm tra (đã giản lược; thứ tự chi tiết của JVM có thể khác):

1. Đọc magic, major/minor và cấu trúc class file.
2. Kiểm tra major/minor có nằm trong tập JVM hỗ trợ không.
3. Nếu `minor = 65535` từ Java 12 trở đi, yêu cầu **major thuộc đúng release JVM** và preview đã được bật.
4. Kiểm tra định dạng, constant pool, access flags, attributes, bytecode và các ràng buộc verification.
5. Khi liên kết hoặc sử dụng class, giải quyết symbol, lớp phụ thuộc, phương thức, field, module/package access, API và thư viện native nếu có.

Các tình huống điển hình:

- **Biên dịch JDK 21 mặc định, chạy JVM 17**: class `65.0` → thường nhận `UnsupportedClassVersionError`, vì JVM 17 tối đa `61`.
- **Biên dịch JDK 21 với `--release 17`, chạy JVM 17**: class `61.0` → qua cửa kiểm tra version; còn cần kiểm tra dependencies, API và bytecode do công cụ khác biến đổi.
- **Class `65.65535` trên JVM 21 không bật preview**: lỗi vì preview chưa bật.
- **Class `65.65535` trên JVM 22 có bật preview**: vẫn lỗi vì đây là preview của release cũ.
- **Class `61.0` dùng API chỉ tồn tại từ Java 21**: JVM 17 có thể qua kiểm tra major nhưng thất bại ở khâu liên kết/thực thi, thường là `NoSuchMethodError` hoặc lỗi liên kết liên quan.

Chiều **“mới chạy class cũ”** thường được hỗ trợ về định dạng nhưng **không bảo đảm 100% hành vi ứng dụng** khi API bị loại bỏ, phụ thuộc bị thiếu, chính sách truy cập module thay đổi hoặc bytecode không hợp lệ. Chiều **“JVM cũ chạy class có major mới”** bị chặn ngay ở mức class file.

## 6. Thực hành đọc và xác minh version bằng Java 17+

Tạo hai tệp cùng một thư mục. Chương trình đầu tiên là class cần kiểm tra.

**Tệp `VersionHello.java`:**

```java
public class VersionHello {
    public static void main(String[] args) {
        System.out.println("Hello, JVM 17");
    }
}
```

**Tệp `ClassVersionReader.java`:** đọc trực tiếp tám byte đầu; `DataInputStream` dùng big-endian và `readUnsignedShort()` tránh nhận sai `65535` thành số âm.

```java
import java.io.DataInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class ClassVersionReader {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java ClassVersionReader file.class");
        }

        try (DataInputStream in =
                     new DataInputStream(Files.newInputStream(Path.of(args[0])))) {
            int magic = in.readInt();
            if (magic != 0xCAFEBABE) {
                throw new IllegalArgumentException("Not a Java class file");
            }

            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();
            System.out.printf("magic=%08X; major=%d; minor=%d%n",
                    magic, major, minor);
        }
    }
}
```

Trên JDK **17 trở lên còn hỗ trợ target 17**, chạy:

```bash
java -version
javac -version
javac --release 17 VersionHello.java ClassVersionReader.java
java VersionHello
java ClassVersionReader VersionHello.class
javap -verbose VersionHello
```

Các dòng stdout chính xác từ hai lệnh `java` chạy class trong ví dụ:

```text
Hello, JVM 17
magic=CAFEBABE; major=61; minor=0
```

Đầu ra `javap -verbose VersionHello` khá dài; phần liên quan sẽ có:

```text
  minor version: 0
  major version: 61
```

`java -version` và `javac -version` hiển thị phiên bản thực tế của máy nên không có một stdout cố định. Nếu muốn xem raw header bằng công cụ hex, tám byte đầu của `VersionHello.class` sẽ có dạng `CA FE BA BE 00 00 00 3D`.

Giới hạn của `ClassVersionReader`: nó **chỉ đọc header**, chưa kiểm tra constant pool, methods, attributes, độ dài toàn file, bytecode hay khả năng JVM nạp thành công. Một file giả có đúng tám byte đầu vẫn có thể bị `ClassFormatError` khi tải.

### Một thí nghiệm về “major phù hợp nhưng API không phù hợp”

Trên **JDK 21 trở lên**, xét tệp `ApiTrap.java`:

```java
import java.util.List;

public class ApiTrap {
    public static void main(String[] args) {
        System.out.println(List.of("alpha", "beta").getFirst());
    }
}
```

`List.getFirst()` có từ Java 21. Nếu dùng compiler JDK 21+ với `--source 17 --target 17`, mã có thể được biên dịch thành **`61.0`** trong khi vẫn tham chiếu API Java 21 hiện diện trên máy build:

```bash
javac --source 17 --target 17 ApiTrap.java
javap -verbose ApiTrap
```

Khi đem class đó sang JVM Java 17, phiên bản `61.0` là hợp lệ nhưng lời gọi `List.getFirst()` không tồn tại trong Java 17 → có thể phát sinh `NoSuchMethodError` khi chạy. Nếu thay bằng:

```bash
javac --release 17 ApiTrap.java
```

compiler sẽ **báo lỗi biên dịch** vì `getFirst()` không thuộc API Java 17. Câu chữ chi tiết của thông báo lỗi và warning tùy JDK. Đây là lý do chỉ đặt `-target` chưa đủ để cam kết khả năng chạy trên JVM cũ.

## 7. Chọn phiên bản biên dịch đúng cho môi trường triển khai

| Tùy chọn | Điều nó kiểm soát | Giới hạn cần nhớ |
| --- | --- | --- |
| `--source N` | Cú pháp/ngữ nghĩa ngôn ngữ Java N mà compiler chấp nhận | Không tự hạ version bytecode hay ràng buộc API |
| `--target N` | Major/class file format đích mà compiler sinh ra | Một mình nó không chặn việc gọi API chỉ có ở JDK mới |
| `--release N` | Kết hợp mức ngôn ngữ, class file và **API nền tảng được hỗ trợ ở Java N** | Không kiểm tra toàn bộ thư viện bên thứ ba, reflection, native, hành vi chạy hay agent biến đổi |
| Java toolchain | Chọn JDK thực sự chạy compiler/tooling | Chọn toolchain JDK 21 **không tự động** có nghĩa output là `61.0`; vẫn cần target/release |

Ưu tiên `javac --release N` nếu mục tiêu là chạy trên release Java N và compiler hỗ trợ release đó. Tránh đồng thời chỉ định `--release` với `--source`/`--target`: `javac` không cho kết hợp như vậy. Kiểm tra các release được compiler hỗ trợ bằng `javac --help`; JDK mới không buộc phải hỗ trợ mọi target đời rất cũ.

Ví dụ Gradle Groovy DSL, dùng compiler từ JDK 21 nhưng sinh class file cho Java 17:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Sau build, **kiểm tra artifact thực sự** bằng `javap -verbose`/đọc header; đừng chỉ dựa vào phiên bản của Gradle daemon hay `JAVA_HOME`. Nếu có Kotlin/Scala, annotation processor, compiler plugin hoặc công cụ weaving/sinh bytecode riêng, mỗi pipeline có thể có target và cơ chế xử lý class file khác nhau. Kiểm thử trên **JVM thấp nhất được hỗ trợ** trước khi phát hành.

## 8. Khi class file nằm trong JAR và được instrumentation biến đổi

### 8.1. Dependency và multi-release JAR

Một ứng dụng có thể được biên dịch thành `61.0` nhưng chứa thư viện Java 21 `65.0`. JVM 17 vẫn có thể thất bại khi tải class thuộc thư viện đó. Vì thế phải kiểm tra **mọi class thực sự được tải**, không chỉ class chính hoặc một dòng trong `build.gradle`.

JAR thông thường chứa các class như `com/example/Service.class`. Với **multi-release JAR** (manifest có `Multi-Release: true`), có thể có biến thể tại `META-INF/versions/9/...`, `META-INF/versions/17/...`, v.v. Runtime chọn phiên bản phù hợp theo quy tắc multi-release; phải kiểm tra **biến thể mà JVM đích thực sự chọn**, thay vì kết luận chỉ từ một class bất kỳ trong archive.

Các lệnh hỗ trợ:

```bash
jar tf library.jar
javap -verbose -classpath library.jar com.example.Service
```

`jar tf` liệt kê entry, còn `javap` kiểm tra class được chỉ định. Với multi-release JAR, các công cụ có tùy chọn liên quan đến multi-release; cần xác minh entry đúng cho từng runtime thay vì giả định output mặc định đã chọn cùng một biến thể như JVM sản xuất.

### 8.2. Java agent, ASM, Byte Buddy và việc sửa class

Trong module instrumentation, Java agent có thể nhận bytecode trong `ClassFileTransformer.transform(...)` và trả về mảng byte mới. Các byte đó phải hợp lệ đối với JVM **đang định nghĩa hoặc biến đổi class**.

- **Đọc được input**: thư viện ASM/Byte Buddy/bytecode parser phải hiểu major mới nhất mà application sử dụng. Thông báo kiểu “Unsupported class file major version 71” có thể đến từ **parser của agent**, chứ không phải từ JVM; cần xác định stack trace bắt nguồn ở đâu.
- **Viết output hợp lệ**: class sau biến đổi phải có major/minor tương thích, constant pool, frames, attributes, flags và bytecode nhất quán. Công cụ cần hỗ trợ các đặc trưng class file tương ứng; không giảm major bằng cách thay hai byte header.
- **Lưu ý retransform/redefine**: JVM có các hạn chế về thay đổi cấu trúc class đã tải; ngay cả class file có version được hỗ trợ vẫn có thể bị từ chối nếu phép biến đổi vi phạm những hạn chế đó.
- **Không bỏ qua preview**: agent chạy trên JVM Java 21 không thể “cứu” class `65.65535` trên JVM Java 22 bằng cách bật preview. Cần tạo bytecode tương thích với release thực sự được triển khai.

Nếu transformer sinh class trên JVM Java 17, hãy xác minh **output** là phiên bản thích hợp cho Java 17 (thường `61.0` hoặc thấp hơn), không dùng định dạng/construct chỉ có từ Java 21 trở đi, và kiểm tra `VerifyError`/`ClassFormatError` sau biến đổi.

## 9. Chẩn đoán lỗi theo đúng tầng

| Triệu chứng | Tầng có khả năng gặp vấn đề | Hướng kiểm tra |
| --- | --- | --- |
| `UnsupportedClassVersionError`; log nói class version `65.0`, runtime hỗ trợ tối đa `61.0` | JVM từ chối version class file | Đối chiếu `java -version`, `javap -verbose`; dùng JVM mới hơn hoặc biên dịch lại bằng `--release 17` |
| Lỗi tải `M.65535` liên quan đến preview | Minor/preview không phù hợp release hoặc chưa bật flag | Kiểm tra đúng JDK/release sinh class và `--enable-preview` trên JVM **cùng release** |
| “Unsupported class file major version 71” trong stack trace ASM/Byte Buddy | Thư viện đọc/sinh bytecode chưa hiểu định dạng mới | Nâng cấp phiên bản bytecode library/agent tương thích; kiểm tra chỗ báo lỗi |
| `ClassFormatError` hoặc `VerifyError` sau transform | Cấu trúc class hoặc bytecode/frames không hợp lệ | So sánh bytecode trước-sau, cấu hình writer và verifier; không chỉ sửa version |
| `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi module access | API, dependency, classpath/module path hay liên kết | Kiểm tra `--release`, tập dependency runtime, classloader và môi trường đích |

Không suy ra nguyên nhân chỉ từ dòng chữ “Unsupported class file”: tìm **exception type, nguồn stack trace và class nào đang được đọc**. Kiểm tra riêng phiên bản JDK dùng cho build, JVM chạy ứng dụng, runtime của test, bytecode agent và dependencies.

## 10. Checklist triển khai an toàn

1. Xác định **JVM thấp nhất phải hỗ trợ** (ví dụ Java 17) và chính sách có dùng preview hay không.
2. Đặt `--release 17` cho mã Java chính, cùng chiến lược target tương đương cho mọi ngôn ngữ/công cụ sinh class.
3. Dùng `javap -verbose` hoặc chương trình đọc header để xác nhận major/minor của **artifact sau build, sau weaving/transform**.
4. Kiểm tra các class thực sự được tải từ JAR, multi-release JAR và dependencies; nâng cấp agent/ASM/Byte Buddy khi bổ sung JDK mới.
5. Chạy kiểm thử tích hợp trên JVM Java 17 thực tế (nếu đó là minimum), thử đường đi tải class động/instrumentation, và chỉ bật preview khi có chủ đích với đúng release.

**Ghi nhớ:** `major` cho biết thế hệ định dạng class file; `minor` từ Java 12 trở đi phân biệt class thông thường với class phụ thuộc preview; `--release` giúp nhắm tới ngôn ngữ, class file **và API nền tảng** phù hợp. Khả năng chạy thực tế còn phụ thuộc bytecode hợp lệ, thư viện và môi trường JVM.

## Tài liệu chuẩn để đối chiếu

- [JVMS Java SE 27 `4.1 — The ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html): vị trí trường `major_version`/`minor_version`, giới hạn phiên bản và quy tắc preview.
- [JVMS Java SE 27 `1.2 — Java SE releases & class file major versions](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-1.html): bảng ánh xạ release/major.
- [JDK 27 `javac` documentation](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): ý nghĩa `--release`, `--source`, `--target` và compiler preview.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/27/docs/specs/jar/jar.html): quy tắc multi-release JAR.
