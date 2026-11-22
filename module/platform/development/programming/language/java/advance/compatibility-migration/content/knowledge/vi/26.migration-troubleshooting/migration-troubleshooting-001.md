# UnsupportedClassVersionError và mức bytecode của từng dependency

Khi nâng cấp hoặc chuyển môi trường Java, một trong những lỗi dễ gây nhầm lẫn nhất là **`java.lang.UnsupportedClassVersionError`**. Ứng dụng có thể biên dịch thành công trên máy phát triển, nhưng không khởi động được ở production; hoặc ứng dụng chính đã dùng `--release 17`, song một dependency bắc cầu lại chứa class được tạo cho Java 21. Có trường hợp service chạy được hàng giờ rồi mới lỗi khi một plugin, JDBC driver, serializer hoặc một class hiếm gặp được nạp. Có trường hợp thông báo “Unsupported class file major version 65” đến từ ASM/Gradle chứ không phải JVM.

Điểm mấu chốt của chẩn đoán là **mức bytecode là thuộc tính của từng file `.class`, không phải thuộc tính duy nhất của cả dự án**. Một classpath có thể chứa hàng nghìn class từ nhiều JAR với các class-file major versions khác nhau. Runtime JVM phải hỗ trợ class cụ thể mà nó đang nạp; compiler, bytecode transformer hoặc build plugin còn phải hiểu class format mà chúng phân tích.

Bài học trong chương **Chẩn đoán lỗi** của *Java Advance Compatibility Migration* này trình bày ý nghĩa lỗi, cách đọc major/minor version, tìm chính xác class và artifact gây lỗi — kể cả transitive dependency, nested JAR, shaded class, multi-release JAR, test/agent/plugin classpath — và cách sửa đúng tầng bằng JDK runtime, dependency version hoặc compiler target, thay vì hạ version tùy tiện.

## 1. UnsupportedClassVersionError thực sự có nghĩa gì?

### 1.1. Một thông báo điển hình

Giả sử application được chạy trên JDK 17, nhưng class cần nạp được biên dịch cho JDK 21:

```text
Exception in thread "main" java.lang.UnsupportedClassVersionError:
  com/example/payment/PaymentClient has been compiled by a more recent
  version of the Java Runtime (class file version 65.0),
  this version of the Java Runtime only recognizes
  class file versions up to 61.0
```

Phân tích:

| Thành phần | Ý nghĩa |
|---|---|
| `com/example/payment/PaymentClient` | Binary name của class JVM đang cố định nghĩa |
| `class file version 65.0` | File `.class` được ghi theo class-file major 65, minor 0 |
| `recognizes ... up to 61.0` | Runtime hiện tại hỗ trợ class-file major tối đa 61 |
| `UnsupportedClassVersionError` | JVM từ chối class format/version, thường ngay trong class loading/definition |

Ở đây **65 tương ứng Java 21; 61 tương ứng Java 17**. Đổi `JAVA_HOME` của trình biên dịch ở developer machine không làm production JVM 17 tự hiểu class Java 21.

### 1.2. Lỗi có thể phát sinh từ dependency, không phải mã ứng dụng

Vấn đề không nhất thiết ở `Main.class`. Ví dụ:

```text
order-service (classes target 17)
├── payment-sdk 4.2       (classes target 17)
│   └── payment-crypto 3.1 (classes target 21)
├── json-library 2.0      (classes target 11)
└── logging-api 1.4       (classes target 8)
```

Trong sơ đồ giả định, JDK 17 nạp được phần lớn class. Khi đường xử lý thanh toán chạm tới `payment-crypto`, JVM từ chối class major 65. Không nên kết luận toàn bộ `payment-sdk` đã được compile cho Java 21 nếu thực tế chỉ một transitive artifact có bytecode này.

### 1.3. Runtime có thể khởi động trước khi lỗi xuất hiện

Class loading thường diễn ra theo nhu cầu. Vì vậy:

- `Main` đã chạy không có nghĩa mọi dependency load được.
- `GET /health` trả 200 không bảo đảm JPA provider hay mã mã hóa load được.
- Một optional module có thể chỉ được nạp khi bật feature flag.
- Reflection, ServiceLoader, plugin discovery hoặc dynamic classloading có thể làm class chỉ xuất hiện khi chạy một workflow.
- Một multi-release JAR có thể chọn implementation khác khi runtime JDK đổi.

**Startup pass không đủ** để khẳng định bytecode compatibility của toàn bộ application artifact.

## 2. Class-file format: major và minor version

### 2.1. Header của một file .class

Theo định dạng class file, phần đầu chứa:

```text
Offset   Size (bytes)   Nội dung
0        4              Magic number: CA FE BA BE
4        2              minor_version
6        2              major_version
8        ...            Constant pool và phần còn lại
```

`major_version` và `minor_version` là các số nguyên không dấu 16 bit theo **big-endian**. JVM đọc các trường này trước khi có thể hiểu đầy đủ phần còn lại của class.

Ví dụ:

```text
CA FE BA BE 00 00 00 41 ...
            ----- -----
            minor major
              0    65
```

`0x0041` trong hệ thập phân là 65. Không nhầm 65 với “Java 65”; đó là *class-file major version* tương ứng Java 21.

### 2.2. Bảng mức bytecode thường gặp

| Java release | Class-file major | Ví dụ |
|---|---:|---|
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

Bảng phản ánh class-file version theo các release được nêu, không phải danh sách mọi runtime vendor/update. Một runtime JDK hiện đại thường hỗ trợ định dạng class cũ tương ứng, nhưng **không hỗ trợ class-file major của release tương lai**.

### 2.3. Minor version và preview features

Từ các Java release hỗ trợ preview, class sử dụng preview language feature thường được đánh dấu bằng **minor version 65535 (0xFFFF)**, thay vì 0.

Ví dụ một class:

```text
major version: 65
minor version: 65535
```

khác với `65.0` thông thường. Class preview của Java 21 phải được xử lý theo quy tắc preview của **chính Java 21**, bao gồm tùy chọn `--enable-preview` khi cần. Không thể chỉ đổi runtime lên Java 22 rồi mặc định preview bytecode Java 21 được chấp nhận; preview class mang ràng buộc release cụ thể.

Quy tắc thực hành:

- Phải đọc **cả major lẫn minor**, không chỉ major.
- Phân biệt “runtime quá cũ” với “preview class chưa được bật/hỗ trợ”.
- Không khuyên dùng `--enable-preview` như một cách sửa tùy ý cho class major cao hơn JDK.
- Không công bố artifact preview là một thư viện Java 21/22 portable thông thường mà không ghi điều kiện runtime.

### 2.4. Java source version không đủ để suy ra bytecode của dependency

Một project dùng Java 17 source syntax có thể vẫn được build bởi JDK 21 và một số task sinh class major 65 nếu compiler configuration không được áp dụng nhất quán. Ngược lại, source viết bằng cú pháp tương thích 17 có thể được compile bằng JDK 21 với `--release 17` để tạo bytecode 61.

Ngoài ra, **mỗi thư viện được tải từ repository đã được biên dịch sẵn**. Compiler của project không biên dịch lại các class đó chỉ vì project đặt release 17.

## 3. Phân biệt lỗi JVM với lỗi bytecode tooling

Không phải mọi log có chữ “unsupported class file major version” đều là `java.lang.UnsupportedClassVersionError` từ JVM.

### 3.1. JVM loader từ chối class

Ví dụ:

```text
java.lang.UnsupportedClassVersionError:
  com/example/Foo has been compiled by a more recent version...
```

Đây là lỗi ở tầng class definition/loading: runtime JVM không hỗ trợ class format/version được yêu cầu.

### 3.2. ASM hoặc bytecode parser không hiểu class

Một lỗi khác có thể là:

```text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
    at org.objectweb.asm.ClassReader...
```

JVM đang chạy có thể **đã là JDK 21**, nhưng thư viện ASM được Gradle plugin, code coverage agent, serializer hoặc bytecode transformer sử dụng chưa hỗ trợ class-file major 65.

Sửa đúng tầng là kiểm tra **ASM/Byte Buddy/Groovy/Kotlin compiler/coverage/build plugin version** và môi trường chạy công cụ. Không có bằng chứng rằng cần đổi source của ứng dụng.

### 3.3. Build tool không khởi động trên JDK mới

Ví dụ lỗi xảy ra khi Gradle tải build logic hoặc Kotlin DSL, trước khi task `compileJava` chạy. Khi đó cần kiểm tra:

- Gradle Wrapper version có hỗ trợ **chạy Gradle Daemon** trên JDK đích không.
- Plugin binary có được compile cho JVM đang chạy Daemon không.
- Groovy/Kotlin embedded/compiler hoặc ASM version trong tool có nhận class format mới không.
- Internal plugin có gọi API đã bị thay đổi không.

Đừng đánh đồng “Gradle không chạy trên JDK 21” với “JAR ứng dụng không chạy trên JDK 21”.

### 3.4. Bảng phân loại nhanh

| Dòng lỗi hoặc thời điểm | Thành phần đáng kiểm tra trước |
|---|---|
| JVM báo `UnsupportedClassVersionError` khi `java -jar` | Runtime Java version và class bị nạp |
| ASM `ClassReader` báo major không hỗ trợ | Bytecode parser version trong công cụ |
| Gradle fail trong configuration phase | Gradle Wrapper, plugin API, build logic JVM |
| Maven Mojo fail trước khi compile | Maven JVM và plugin/plugin dependencies |
| JUnit discovery/coverage fail | Test engine, Byte Buddy, ASM, JaCoCo hoặc agent |
| Native-image build fail khi phân tích class | AOT toolchain/JDK compatibility |
| Reflection nạp class lần đầu lúc request | Lazy-loaded dependency hoặc generated class |

**Đọc exception type và stack trace đầy đủ trước khi chọn phương án sửa.** Một log chỉ có một dòng “major version 65” chưa đủ để xác định lỗi thuộc JVM, Gradle, ASM hay test framework.

## 4. Vì sao mức bytecode của từng dependency mới là câu trả lời?

### 4.1. Dependency graph là một tập binary khác nhau

Một ứng dụng có thể chứa:

- Main project classes.
- Module nội bộ được publish trước đó.
- Direct dependencies.
- Transitive dependencies.
- Runtime-only providers.
- Test dependencies và test engines.
- Annotation processors và code generators.
- Build plugins với classpath riêng.
- Java agents, instrumentation libraries.
- JAR do application server hoặc plugin container cung cấp.
- Classes được shaded/relocated vào fat JAR.
- Multi-release JAR entries.

Mỗi nguồn có thể chứa class-file major/minor khác nhau. Một project đặt:

```xml
<maven.compiler.release>17</maven.compiler.release>
```

**không** chuyển class file major 65 đã nằm trong thư viện tải từ Maven Central thành 61.

Tương tự trong Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

chỉ giới hạn các Java compile tasks mà cấu hình đó áp dụng, không tự sửa bytecode của mọi dependency hoặc Gradle plugin.

### 4.2. Direct dependency chưa chắc chứa class gây lỗi

Ví dụ:

```text
api-service
└── com.example:search-client:5.0   [declared]
    └── com.example:search-core:7.2
        └── com.example:vector-bridge:3.0
            └── com.example:simd-helper:2.0 [bytecode 65]
```

Source của `api-service` có thể không import `simd-helper`. Runtime vẫn có thể nạp class của nó khi search client sử dụng một optimization path.

Vì vậy, yêu cầu “giảm sourceCompatibility về 17” là **sai tầng** nếu lỗi nằm trong artifact transitive đã được biên dịch cho 21.

### 4.3. Một JAR có thể chứa nhiều major versions

Không có quy tắc bắt buộc tất cả class trong một JAR có cùng major. Một build có thể vô tình đóng chung generated classes từ JDK mới, class từ tool khác hoặc relocated code.

Ngoài ra, multi-release JAR cố ý chứa implementation khác nhau theo Java release. Vì thế nên ghi cả:

- **Minimum/maximum major** tìm được.
- **Đường dẫn class cụ thể**.
- **Vị trí archive và nested archive**.
- **Effective major được chọn theo runtime**, nếu dùng multi-release JAR.
- **Module/artifact owner và dependency path**.

Một báo cáo chỉ ghi “JAR X compiled for Java 21” có thể quá thô nếu lỗi thực sự đến từ một class không được chọn khi chạy JDK 17.

## 5. Diagnostic workflow từ stack trace đến artifact

### Bước 1 — Lưu đầy đủ lỗi

Ghi:

- Exact exception type và message.
- Class bị từ chối.
- Major/minor version được báo.
- Maximum class-file version runtime nhận diện.
- Full `Caused by` chain.
- Thread/tác vụ/endpoint làm phát sinh lỗi.
- Timestamp và môi trường.

Không chỉ copy dòng cuối `Application failed to start`.

### Bước 2 — Xác minh JVM thực sự chạy

```bash
java -version
```

chỉ cho biết Java trên shell hiện tại. Ứng dụng do service manager, Gradle daemon, Maven Surefire fork hoặc container entrypoint khởi chạy có thể dùng JVM khác.

Ví dụ chạy với đường dẫn cụ thể:

```bash
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/java" -jar app.jar
```

Trên PowerShell:

```powershell
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\java.exe" -jar .\app.jar
```

Cần kiểm tra cả `JAVA_HOME`, `PATH`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, image digest và runtime process command line.

### Bước 3 — Đọc major version của class lỗi

Nếu class nằm trong một JAR thông thường:

```bash
javap -verbose -classpath lib/problem-library.jar \
  com.example.payment.PaymentClient
```

Tìm:

```text
minor version: 0
major version: 65
```

Dùng `javap` từ JDK đủ mới để phân tích class-file format được dùng. Nếu class nằm trong nested JAR, WAR hoặc nonstandard launcher, phải trỏ đúng file/class hoặc trích xuất có kiểm soát.

### Bước 4 — Xác định artifact chính xác

Dùng dependency graph của Maven/Gradle, danh sách file trong artifact, class-loading logs và repository metadata để xác định JAR chứa class.

Đừng giả định group/artifact version từ stack trace: tên package có thể được relocate, bundle hoặc shaded.

### Bước 5 — Xem nơi class được nạp

Nếu có nhiều bản cùng class trên runtime classpath, nguồn class tại thời điểm chạy có thể khác file đang được `javap` kiểm tra.

Trên HotSpot có thể dùng logging:

```bash
java -Xlog:class+load=info -jar app.jar
```

Log rất lớn, chỉ nên dùng trong môi trường chẩn đoán thích hợp. Nếu chính class bị JVM từ chối trước khi định nghĩa, log có thể không có dòng “loaded successfully” cho class đó; cần kết hợp exception và classpath/archive inspection.

### Bước 6 — Quyết định sửa ở tầng nào

Có ba hướng chính:

1. **Nâng JVM runtime** lên release hỗ trợ major version của binary, nếu được phép và toàn stack tương thích.
2. **Chọn dependency release phù hợp với minimum runtime JDK**, ưu tiên version được vendor hỗ trợ.
3. **Biên dịch lại source của artifact gây lỗi** với compiler target phù hợp, nếu sở hữu source và APIs/dependencies cho phép.

Không chọn bằng cách đổi bừa `sourceCompatibility` của main project hoặc chỉnh vài byte header trong class file.

## 6. Công cụ javap: xác minh class cụ thể

### 6.1. Kiểm tra một class từ thư mục build

```bash
javap -verbose -classpath build/classes/java/main \
  com.example.Main
```

hoặc với Maven:

```bash
javap -verbose -classpath target/classes \
  com.example.Main
```

Output thường có `minor version` và `major version` gần đầu. Nếu compiled class không tồn tại tại path này, kiểm tra cấu hình task/source set/module thực tế thay vì tự tạo output khác.

### 6.2. Kiểm tra một class trong dependency JAR

```bash
javap -verbose -classpath libs/payment-client.jar \
  com.example.payment.PaymentClient
```

Dùng đúng JAR đã được resolve hoặc deploy. Một JAR được tải tay từ internet với cùng tên nhưng khác checksum không phải bằng chứng cho artifact production.

### 6.3. Kiểm tra class không có tên package đơn giản

Ví dụ class `com/example/PaymentClient.class`:

```bash
jar tf libs/payment-client.jar
```

sẽ giúp xác nhận entry path. `javap` thường nhận binary name dạng `com.example.PaymentClient`, không phải path của file zip.

### 6.4. Nếu javap bị lỗi vì format quá mới

Một JDK tool cũ cũng có thể chưa hiểu classfile version cao hơn nó. Hãy dùng JDK đủ mới để phân tích hoặc đọc 8 byte class-file header bằng công cụ nhị phân. **Không cần nạp class bằng runtime cũ để đọc major version của file**.

## 7. Xem toàn bộ class-file versions, không chỉ một class

### 7.1. Vì sao cần quét?

Một dependency có thể chứa 2.000 classes nhưng chỉ vài class là major 65. Một JAR lớn có thể dùng toolchain tạo ra source sets khác nhau. Nếu muốn biết minimum JDK thực tế của cả bundle, nên quan sát mức bytecode **theo class**, bao gồm transitive/nested JAR phù hợp.

### 7.2. Ví dụ script Python quét các .class trong archive

Một công cụ nhỏ có thể đọc class header trực tiếp mà không cần khởi chạy JVM hoặc biên dịch application. Ví dụ dưới đây dùng Python standard library, quét JAR/WAR/EAR/ZIP và tối đa hai cấp nested archives:

```python
import io
import struct
import sys
import zipfile
from collections import Counter

MAJOR_LABELS = {
    52: "Java 8",
    55: "Java 11",
    61: "Java 17",
    65: "Java 21",
    66: "Java 22",
    69: "Java 25",
}

ARCHIVE_EXTENSIONS = (".jar", ".war", ".ear", ".zip")
MAX_NESTING = 2
rows = []


def scan_archive(archive, origin, depth=0):
    for entry in archive.infolist():
        if entry.is_dir():
            continue

        path = entry.filename
        full_name = f"{origin}!/{path}"

        if path.endswith(".class"):
            with archive.open(entry) as stream:
                header = stream.read(8)

            if len(header) != 8:
                print("TRUNCATED", full_name)
                continue

            magic, minor, major = struct.unpack(">IHH", header)
            if magic != 0xCAFEBABE:
                print("NOT_CLASS", full_name)
                continue

            rows.append((major, minor, full_name))
            continue

        if depth < MAX_NESTING and path.lower().endswith(
            ARCHIVE_EXTENSIONS
        ):
            # Ví dụ; chỉ dùng với archive có nguồn tin cậy.
            # Thực tế nên giới hạn kích thước và số file giải nén.
            with archive.open(entry) as stream:
                nested_bytes = stream.read()

            try:
                with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
                    scan_archive(nested, full_name, depth + 1)
            except zipfile.BadZipFile:
                print("BAD_NESTED_ARCHIVE", full_name)


if len(sys.argv) != 2:
    raise SystemExit("Usage: python scan_versions.py app.jar")

with zipfile.ZipFile(sys.argv[1]) as archive:
    scan_archive(archive, sys.argv[1])

counts = Counter((major, minor) for major, minor, _ in rows)

print("Scanned classes:", len(rows))
for (major, minor), count in sorted(counts.items()):
    label = MAJOR_LABELS.get(major, "unknown release")
    print(f"major={major}, minor={minor}, {label}: {count}")

print("Top class-file versions:")
for major, minor, path in sorted(rows, reverse=True)[:30]:
    print(f"  {major}.{minor}  {path}")
```

Chạy tham khảo:

```bash
python scan_versions.py application.jar
```

Script chỉ minh họa thao tác đọc header và thống kê; không phải công cụ kiểm toán production hoàn chỉnh. Với archive không tin cậy, cần giới hạn decompressed size, số entries, recursion và tài nguyên để tránh ZIP bomb hoặc file quá lớn. Độ sâu hai cấp có thể bỏ sót những archive lồng sâu; các artifact ngoài archive như thư mục `lib/` phải được quét riêng.

### 7.3. Cách đọc kết quả

Ví dụ giả định:

```text
Scanned classes: 7421
major=52, minor=0, Java 8: 1002
major=55, minor=0, Java 11: 3311
major=61, minor=0, Java 17: 3006
major=65, minor=0, Java 21: 102

Top class-file versions:
  65.0  app.jar!/BOOT-INF/lib/crypto-lib.jar!/com/example/crypto/...
  65.0  app.jar!/BOOT-INF/lib/crypto-lib.jar!/com/example/crypto/...
```

Có 102 class major 65 cần điều tra khi target runtime Java 17. Tuy nhiên, kết quả “highest major 65” **không tự động chứng minh Java 17 chắc chắn sẽ nạp những class đó** — ví dụ version-specific classes bên trong một multi-release JAR có thể không được chọn. Cần xem vị trí entry và loader semantics.

### 7.4. Phân biệt detection và runtime selection

Scanner đọc tất cả class bytes, còn runtime classloader chỉ nạp class theo lookup path, điều kiện môi trường và multi-release rules.

Vì vậy có hai câu hỏi:

1. **Inventory:** artifact chứa class-file major nào?
2. **Effective runtime:** trên JDK và classloader cụ thể, class nào sẽ được chọn/nạp?

Báo cáo cần trả lời cả hai khi triage một lỗi thực tế.

## 8. Multi-release JAR: một JAR, nhiều mức bytecode có chủ đích

### 8.1. Cấu trúc

Một multi-release JAR có thể chứa:

```text
library.jar
├── META-INF/MANIFEST.MF
├── com/example/Feature.class
├── META-INF/versions/9/com/example/Feature.class
├── META-INF/versions/17/com/example/Feature.class
└── META-INF/versions/21/com/example/Feature.class
```

Manifest có thể bao gồm:

```text
Multi-Release: true
```

Khi chạy ở runtime hỗ trợ multi-release JAR, classloader tiêu chuẩn có thể chọn bản class version-specific cao nhất không vượt runtime feature version cho những lookup phù hợp.

### 8.2. Tại sao scanner có thể “báo động giả”?

Giả sử:

- Root `Feature.class` major 52.
- `META-INF/versions/17/Feature.class` major 61.
- `META-INF/versions/21/Feature.class` major 65.

Một scanner tất cả classes sẽ báo major 65. Nhưng trên Java 17, bản trong directory 21 thường không được lựa chọn; JVM có thể dùng version 17. Không phải cứ có class major 65 trong MR-JAR thì Java 17 luôn không chạy được.

Mặt khác, nếu **root entry** hoặc **entry được chọn cho JDK 17** có major 65, lỗi là thực.

### 8.3. Kiểm tra manifest và entry names

```bash
jar tf library.jar
jar --describe-module --file library.jar
```

Lệnh thứ hai xem module metadata, không thay thế kiểm tra manifest. Với archive cụ thể, có thể dùng công cụ ZIP hoặc giải nén manifest để xác nhận `Multi-Release: true`.

### 8.4. Framework launcher có thể có classloading riêng

Spring Boot executable JAR, OSGi bundles, application server và classloaders tùy biến có thể nạp class qua logic riêng. Phải xác minh **loader thực sự xử lý multi-release entries theo cách nào**. Không mặc định mọi nested archive được mọi công cụ đọc giống Java standard `JarFile`.

### 8.5. Preview classes nằm trong MR-JAR

Nếu version-specific class dùng preview bytecode, các quy tắc preview vẫn áp dụng. Một entry major 65 minor 65535 dành cho Java 21 có thể yêu cầu `--enable-preview` khi được chọn trên JDK 21; không nên dùng nó làm implementation mặc định cho nhiều release.

## 9. Maven: tìm dependency thực sự bị chọn

### 9.1. Dependency tree theo module và scope

Các lệnh tham khảo:

```bash
./mvnw -version
./mvnw dependency:tree
./mvnw dependency:tree -Dscope=runtime
./mvnw dependency:tree -Dverbose
```

Trong multi-module project, cần chạy trên module ứng dụng hoặc reactor selection phù hợp. Lưu version Maven Dependency Plugin để biết cách thể hiện omitted/conflicts.

Tìm:

- Direct dependency đã nâng version chưa?
- Transitive artifact nào thay đổi theo BOM?
- Runtime scope có khác compile scope không?
- Một version cao được chọn vì dependency management hay direct declaration?
- Có optional/provider dependency được nạp động không?
- Có profile hoặc plugin tạo một graph khác giữa local và CI không?

### 9.2. Version đang resolve không nói bytecode major

Ví dụ:

```text
com.example:crypto-core:jar:3.0.0:runtime
```

Chỉ nhìn version string 3.0.0 không thể suy ra nó yêu cầu Java 17 hay 21. Phải kiểm tra release notes/minimum Java version hoặc **class-file headers của artifact thực tế**.

Một library version “mới hơn” không mặc nhiên có target bytecode cao hơn; nhiều dự án giữ Java 8/11 target qua nhiều release. Ngược lại, một release minor có thể nâng minimum JDK theo chính sách vendor.

### 9.3. Effective POM và dependency management

```bash
./mvnw help:effective-pom
```

BOM và parent POM có thể quản lý version khác giá trị bạn tưởng đã khai báo. Khi nhiều BOM cùng quản lý một artifact, cần xác minh management entry thắng theo quy tắc Maven.

Không sửa version trực tiếp tại một child module rồi bỏ qua BOM/framework alignment. Điều này có thể tạo binary/API mismatch dù giải quyết được `UnsupportedClassVersionError`.

### 9.4. Plugin classpath độc lập với app classpath

Maven plugin được nạp vào plugin realm của JVM đang chạy Maven. Nếu một Mojo nội bộ hoặc Maven plugin được compile Java 21 nhưng Maven đang chạy Java 17, lỗi có thể xảy ra **khi plugin được thực thi**, dù application code target 17.

Khi đó cần:

- Xem `./mvnw -version` để biết Maven JVM.
- Tìm plugin goal và group/artifact/version.
- Kiểm tra plugin artifact class-file major.
- Chọn Maven JVM hoặc plugin release hỗ trợ phù hợp.
- Tránh thêm plugin library vào application `<dependencies>` như cách “sửa” plugin realm.

## 10. Gradle: kiểm tra graph theo configuration

### 10.1. Đừng chỉ xem một dependency report chung

Với Gradle, có nhiều classpath/configuration:

```bash
./gradlew --version
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
```

Những tên `:app` là ví dụ; thay bằng module thực. Nếu ứng dụng dùng custom configurations, Android/Kotlin plugins hoặc build logic riêng, cần kiểm tra các graph tương ứng.

### 10.2. dependencyInsight

```bash
./gradlew :app:dependencyInsight \
  --dependency crypto-core \
  --configuration runtimeClasspath
```

Output có thể cho biết vì sao version được chọn và đường dependency liên quan. Điều này giúp điều tra trường hợp một transitive dependency có bytecode vượt minimum runtime.

Nhưng `dependencyInsight` **không tự đọc major của từng class**. Nó giải thích version resolution; công việc bytecode inspection là bước riêng.

### 10.3. Java toolchains tách compiler khỏi Gradle Daemon

Ví dụ:

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

Trong một Gradle release hỗ trợ cấu hình này, compiler JDK 21 có thể tạo application classes target Java 17. Nhưng:

- Gradle Daemon chạy trên JDK nào vẫn là câu hỏi riêng.
- Build plugins có thể yêu cầu JVM khác.
- Annotation processors có runtime/bytecode constraints riêng.
- Kotlin/Scala/Groovy compiler tasks không nhất thiết bị điều chỉnh bởi JavaCompile config.
- Dependencies tải từ repository vẫn giữ bytecode gốc.
- Test JVM có thể khác toolchain nếu tasks không được cấu hình/được plugin kiểm soát khác.

Một lỗi class major 65 trong plugin khi Gradle Daemon chạy JDK 17 không được sửa bằng `options.release=17` ở application module.

### 10.4. Source compatibility cũng chưa đủ

```groovy
sourceCompatibility = JavaVersion.VERSION_17
targetCompatibility = JavaVersion.VERSION_17
```

có thể ảnh hưởng language/bytecode target cho Java compilation, nhưng không cung cấp đầy đủ sự hạn chế Java platform APIs như `--release 17`. Khi cần hỗ trợ runtime 17, ưu tiên toolchain/`options.release` phù hợp và kiểm tra dependency bytecode riêng.

### 10.5. Nếu Gradle không khởi động được

Đừng cố chạy mọi `dependencies` task với Gradle Wrapper không hỗ trợ JDK bạn đang dùng. Trước hết kiểm tra wrapper/JDK compatibility và có thể dùng JDK build tương thích để chạy dependency-reporting tasks, trong khi target runtime kiểm chứng vẫn là JDK khác.

**JDK chạy Gradle không nhất thiết phải giống JDK chạy application.**

## 11. Annotation processor và generated classes

### 11.1. Processor là một binary thực thi trong build

Lombok, MapStruct, QueryDSL, Dagger và nhiều annotation processors khác được nạp trong compiler process. Nếu processor JAR chứa class major 65 nhưng compiler process đang chạy bằng Java 17, có thể gặp class loading/version error trong quá trình compile.

Việc source ứng dụng target 17 không sửa được bytecode của processor.

### 11.2. Generated source không đồng nghĩa generated bytecode

Một processor có thể:

- Sinh `.java` rồi compiler chính tạo bytecode theo target.
- Sinh `.class` trực tiếp.
- Sinh resources/metadata dùng trong runtime.
- Kích hoạt code generation plugin/chương trình khác.

Nếu task sinh class trực tiếp bằng toolchain JDK 21 và đóng vào artifact target 17, output có thể có major 65 dù JavaCompile chính tạo major 61.

Do đó, khi debug cần scan **artifact đã đóng gói**, không chỉ `build/classes/java/main`.

### 11.3. Các compilation pipelines cần thống nhất

| Pipeline | Điều cần xác minh |
|---|---|
| JavaCompile main | `--release`/toolchain/bytecode target |
| JavaCompile test | Test target và test runtime JDK |
| Kotlin compilation | Kotlin JVM target/JDK, compatibility với Java classes |
| Groovy/Scala compilation | Compiler target và JVM requirements |
| Annotation processor | Processor bytecode và JDK chạy compiler |
| Codegen/bytecode enhancement | Tool version, emitted class-file version |
| Test agent/instrumentation | Parser/ASM/Byte Buddy hỗ trợ major version |
| Shadow/shade/repackage | Không vô tình nhúng class version mới |

Khi nhiều module và ngôn ngữ phối hợp, một cấu hình `--release` ở module root không đảm bảo mọi output được tạo đúng mức.

## 12. Runtime-only, compile-only và plugin classpath có thể khác nhau

Một dự án có thể có những tầng:

```text
BUILD JVM (Gradle/Maven):
  - build plugins
  - convention plugins
  - annotation processors / generators

COMPILER TARGET:
  - application classes
  - generated classes

TEST JVM:
  - application/test classes
  - JUnit engine + mocking/coverage agents

PRODUCTION JVM:
  - application JAR/WAR
  - runtime dependencies
  - application server/shared libs
  - javaagent/native integration
```

Mỗi JVM có version cụ thể và mỗi classpath có thể chứa các bytecode majors khác nhau.

### 12.1. Ví dụ lệch giữa test và production

- Developer chạy tests với Java 21, mọi dependency major 65 đều load được.
- Application class output được compile target 17.
- Production container dùng Java 17.
- Một runtime-only dependency major 65 được nạp khi xử lý message thực.
- Production gặp `UnsupportedClassVersionError`.

Nếu chỉ kiểm tra `javap` trên `Main.class` sẽ thấy major 61 và bỏ sót lỗi. Cần kiểm tra **runtime graph** và chạy packaged artifact trên minimum supported JDK.

### 12.2. Ví dụ lệch giữa Maven JVM và Surefire fork

Maven có thể chạy bằng JDK 17 trong khi test JVM được cấu hình dùng JDK 21 (hoặc ngược lại). Một plugin phải load được trên **Maven JVM**, còn test classes phải load được trên **test JVM**.

Khi lỗi xuất hiện trong plugin realm hoặc forked test process, ghi rõ process nào ném exception. Không sử dụng `mvn -version` làm bằng chứng duy nhất về test runtime nếu có toolchains/fork overrides.

### 12.3. Application server

WAR có thể biên dịch major 61 nhưng server shared library/provider có class major 65. Nếu container/app server chạy Java 17, lỗi có thể đến từ server module chứ không từ `WEB-INF/lib`.

Đọc server logs, inspect classloader sources và đối chiếu server/JDK support matrix. Chỉ scan WAR không đủ.

## 13. Thin JAR, fat JAR, shaded JAR và nested dependencies

### 13.1. Thin JAR

Ví dụ:

```text
distribution/
├── app.jar
└── lib/
    ├── http-client.jar
    ├── serializer.jar
    └── native-bridge.jar
```

Cần quét **tất cả JAR thực sự nằm trong launcher classpath**. Một scan chỉ trên `app.jar` sẽ bỏ lỡ major 65 trong `lib/serializer.jar`.

### 13.2. Executable Spring Boot JAR

Một layout thường gặp:

```text
app.jar
├── BOOT-INF/classes/
├── BOOT-INF/lib/
│   ├── payment-client.jar
│   └── crypto-core.jar
└── org/springframework/boot/loader/...
```

Mỗi nested JAR chứa các class được biên dịch trước. Việc Spring Boot launcher có major 61 không chứng minh `BOOT-INF/lib/crypto-core.jar` cũng major 61.

Dùng archive scanner hỗ trợ nested JAR, hoặc trích xuất một bản kiểm tra sang thư mục tạm tin cậy rồi chạy `javap` trên dependency cần xem.

### 13.3. Shaded/relocated classes

Một fat JAR có thể chứa class thư viện dưới package đã đổi, ví dụ:

```text
com/example/app/shaded/crypto/NativeBridge.class
```

Stack trace lúc này không phản ánh groupId ban đầu. Cần dùng build configuration/relocation report, dependency lock/graph và class fingerprint để xác định nguồn.

Việc library ban đầu target Java 17 nhưng một plugin shading nâng bytes không có nghĩa mọi class có cùng version. Chỉ class header và thực tế đóng gói mới trả lời chính xác.

### 13.4. Assembly/resource transforms

Một số packaging plugin có thể:

- Nhúng JAR mới hơn dự kiến.
- Đóng duplicate versions.
- Loại bỏ một số class/resources.
- Tái tạo class hoặc bytecode qua instrumentation.
- Làm mất `META-INF/services` dẫn đến provider khác được nạp.

Phép thử đúng là inspect **artifact cuối được deploy**, không chỉ các output trước khi `jar`/`shadowJar`/`repackage`.

## 14. Class loading log và classpath source

### 14.1. Khi có nhiều bản của cùng class

Ví dụ:

```text
app.jar!/BOOT-INF/lib/crypto-3.1.jar
server/lib/crypto-2.4.jar
plugins/crypto-2.8.jar
```

Nếu binary name trùng, class được nạp tùy classloader và delegation policy. Một bản `crypto-3.1` major 65 có thể không được chọn, hoặc có thể được chọn ở một application classloader dù đã có bản cũ ở server.

Để điều tra:

1. Xác định class gây `UnsupportedClassVersionError`.
2. Liệt kê tất cả JAR/paths chứa binary name đó.
3. Xác định classloader đang định nghĩa class.
4. Quan sát classloading/logs nếu phù hợp.
5. So sánh với launcher, application server và shading configuration.
6. Kiểm tra version/bytecode của bản thực sự được chọn.

### 14.2. Java agents cũng có thể tạo/load classes

Agent có thể instrument code và tải helper classes vào bootstrap/system/application classloader. Nếu agent version mới đưa class major 65 vào runtime Java 17, exception có thể xuất hiện trước business application.

Kiểm tra `-javaagent`, agent JAR manifest và vendor JDK compatibility. Không xóa agent khỏi production như fix mặc định; cần version được hỗ trợ hoặc kế hoạch vận hành thay thế.

### 14.3. Plugin systems và ServiceLoader

Một plugin JAR chỉ được nạp khi tính năng cụ thể được bật có thể mang bytecode version cao. Nếu kiểm thử chỉ start application mà không activate plugin, lỗi sẽ bị bỏ sót.

Cần chạy plugin discovery, provider creation và workflows thực sự dùng plugin trên minimum supported JDK.

## 15. Preview features: lỗi không giống runtime thấp hơn

### 15.1. Biên dịch preview

Ở Java release hỗ trợ preview feature, một ví dụ lệnh compile có thể là:

```bash
javac --enable-preview --release 21 PreviewExample.java
```

Nếu compiler phát sinh class file đánh dấu minor 65535 cho preview, JVM sẽ áp dụng quy tắc preview của release tương ứng.

### 15.2. Runtime cùng release

```bash
java --enable-preview PreviewExample
```

Nhưng `--enable-preview` không phải “được phép chạy mọi bytecode tương lai”.

Ví dụ:

- JDK 17 không đọc được class major 65 chỉ vì bật preview.
- Một class Java 21 preview không tự được phép chạy trên Java 22 như một ordinary class Java 21.
- Một dependency sử dụng preview public API có thể áp điều kiện preview lên consumer và publication policy.

### 15.3. Quyết định khi dependency chứa preview class

1. Xác định major/minor của class thực tế.
2. Kiểm tra dependency release có cố ý dùng preview không.
3. Đọc vendor policy và yêu cầu runtime.
4. Nếu production không chấp nhận preview, chọn release stable khác.
5. Nếu preview được phép, test đúng JDK release, flags và workload.
6. Không hạ minor trong class header bằng hex editor; class semantics/API có thể thật sự phụ thuộc preview.

## 16. Sửa đúng tầng: nâng JDK runtime

### 16.1. Khi nào nên nâng runtime?

Nếu dependency cần Java 21 nhưng môi trường đang chạy Java 17, và application/framework/OS/vendor policy đã hỗ trợ Java 21, nâng production JDK có thể là hướng phù hợp.

Lộ trình:

1. Xác nhận min JDK của dependency và các thành phần khác.
2. Chạy **artifact hiện tại** trên JDK target khi có thể.
3. Kiểm tra framework/native/agent compatibility.
4. Chạy integration/contract tests.
5. Đo startup, warm-up, p95/p99, CPU/GC/memory.
6. Rollout có kiểm soát với rollback.

Đổi runtime không có nghĩa mọi code phải compile target 21. Các class major 61 vẫn có thể được nạp trên JDK 21.

### 16.2. Không nâng JDK chỉ vì một optional dependency không cần thiết

Nếu dependency major 65 chỉ được kéo vào do một feature không sử dụng, có thể:

- Loại bỏ dependency theo kiến trúc được hỗ trợ.
- Chọn phiên bản library hỗ trợ minimum JDK.
- Tách module/feature theo runtime requirement.
- Dùng server/client API thích hợp thay library đó.

Nâng toàn bộ production runtime vẫn cần đánh giá support và vận hành; không luôn là phương án có chi phí thấp nhất.

### 16.3. Production image phải dùng đúng JDK

Một CI build dùng Java 21 có thể phát hành lên Docker image Java 17 do Dockerfile chưa đổi. Khi lỗi xuất hiện, kiểm tra:

- Runtime base image và image digest.
- Entrypoint.
- JVM process `java -version`.
- Helm/manifest environment overrides.
- Service manager.
- Rollout có thực sự kéo image mới không.

Không sửa application source nếu nguyên nhân là image runtime đang cũ.

## 17. Sửa đúng tầng: chọn dependency tương thích minimum JDK

### 17.1. Khi không thể nâng runtime

Có thể production buộc dùng JDK 17 do hỗ trợ vendor, compliance, application server hoặc rollout constraints. Khi một library mới yêu cầu Java 21, cần chọn một **release được vendor hỗ trợ trên Java 17**.

Ví dụ giả định:

```text
crypto-lib 3.0  -> minimum Java 17
crypto-lib 4.0  -> minimum Java 21
application target/runtime -> Java 17
```

Không nên chỉ nhìn semver; kiểm tra release notes, minimum supported Java và binary contents của release cụ thể.

### 17.2. Downgrade có thể gây linkage errors

Nếu application hoặc thư viện khác được compile với `crypto-lib 4.0` nhưng runtime thay thành 3.0, có thể gặp:

```text
NoSuchMethodError
NoSuchFieldError
AbstractMethodError
ClassCastException
```

Do đó, sửa `UnsupportedClassVersionError` bằng downgrade không chứng minh toàn stack tương thích.

Cần:

1. Xem framework/BOM compatibility matrix.
2. Xác định API differences giữa hai library releases.
3. Kiểm tra binary compatibility của callers.
4. Chạy source compile khi cần.
5. Chạy runtime integration tests.
6. Đối chiếu security support và CVEs.

### 17.3. Một BOM có thể nâng minimum JDK theo cả bộ

Nâng Spring Boot/framework/BOM có thể thay hàng chục transitive versions. Nếu một dependency chuyển min JDK, nó có thể là biểu hiện của **whole-stack minimum JDK requirement**, không phải lỗi riêng của một JAR.

Cố giữ một version cũ bằng override có thể phá compatibility. Ưu tiên chọn BOM/framework line hỗ trợ runtime mục tiêu, sau đó dùng exceptions có lý do và test.

### 17.4. Không rewrite bytecode bằng chỉnh header

Đổi bytes `00 41` (65) thành `00 3D` (61) trong header không tự làm class Java 21 thành Java 17 bytecode. Class có thể dùng instructions, constant-pool structures, attributes, APIs hoặc semantics mới.

Không xem việc patch header, tải JAR đã chỉnh từ nguồn không rõ hoặc chạy bytecode transformer tùy tiện là giải pháp hỗ trợ chính thức. Nếu cần backport, thực hiện bằng source/compiler/toolchain phù hợp và regression tests.

## 18. Sửa đúng tầng: biên dịch artifact do mình sở hữu

### 18.1. --release giải quyết điều gì?

Với JDK compiler đủ mới, `javac --release N` hướng tới:

- Language level của Java release N.
- Class-file target tương ứng.
- Các Java SE platform APIs được phép sử dụng ở release N.

Ví dụ ứng dụng phải chạy Java 17 nhưng build trên JDK 21:

```bash
javac --release 17 -d out src/com/example/Main.java
```

Class output thông thường sẽ có major 61, không phải 65. Tuy nhiên, nếu source thực sự dùng Java 21 API, compiler phải báo lỗi vì API không thuộc release 17.

### 18.2. Maven Compiler Plugin

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Cần chọn version Maven Compiler Plugin, Maven core và JDK build tương thích. Nếu cấu hình đặt tại parent, kiểm tra effective POM và module overrides.

Maven compiler release **không biên dịch lại** third-party dependencies. Nếu có generated class/other language task, kiểm tra output riêng.

### 18.3. Gradle JavaCompile

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

Cấu hình minh họa: dùng compiler Java 21, tạo output Java 17 cho JavaCompile tasks được điều chỉnh. Cần Gradle version hỗ trợ toolchain JDK 21.

Không nhầm JDK chạy Gradle Daemon với JDK compiler/toolchain. Một plugin binary major 65 sẽ vẫn không nạp trên Daemon JDK 17.

### 18.4. Recompile có thể không đủ

Ngay cả sau khi compile application classes major 61:

- Dependency JAR có class 65.
- Generated bytecode có 65.
- Test fixtures có 65.
- Kotlin/Scala/Groovy modules có target khác.
- Runtime app server/agent còn nạp class 65.

Vì thế cần quét **artifact cuối và các dependency JAR thực sự được triển khai**.

## 19. Build JDK và runtime JDK: case thường gặp

### 19.1. JDK 21 build, JDK 17 deploy

```text
CI Java:
  java -version -> 21

Compiler:
  release -> 21 (implicit/default)

Container:
  java -version -> 17

Result:
  application classes -> major 65
  production runtime -> supports up to major 61
```

Fix có thể là:

- Nếu policy runtime phải 17: cấu hình `--release 17` và kiểm tra APIs/dependencies.
- Nếu application cần Java 21 features: nâng runtime container lên 21.
- Nếu CI vô tình đổi JDK: pin toolchain và runtime matrix.

### 19.2. Application target 17, transitive dependency target 21

```text
Application .class: 61
Dependency A .class: 61
Dependency B .class: 65
Runtime: Java 17
```

Fix không nằm ở compiler target ứng dụng. Cần nâng runtime hoặc thay dependency B (có kiểm tra API/compatibility).

### 19.3. Build plugin target 21, Gradle Daemon Java 17

```text
Gradle Daemon: Java 17
Convention plugin: major 65
Java compiler toolchain: Java 21
Application target: Java 17
```

Plugin được nạp trong Gradle Daemon trước khi Java compiler toolchain giúp được điều gì. Fix là đảm bảo Daemon đủ mới cho plugin hoặc rebuild/chọn plugin compatible với JVM chạy Gradle — đồng thời kiểm tra Gradle API compatibility.

### 19.4. Tests Java 21, runtime production Java 17

Một JUnit test suite chạy trên JDK 21 có thể load dependency major 65 thành công. Production Java 17 fail. Do đó, CI nên có bước kiểm thử **trên runtime tối thiểu được công bố**, không chỉ trên JDK mới nhất dùng compile.

## 20. Phân biệt với các lỗi linkage khác

| Lỗi | Ý nghĩa điển hình | Khác gì với UnsupportedClassVersionError? |
|---|---|---|
| `UnsupportedClassVersionError` | Class-file format/version không được runtime chấp nhận | JVM từ chối class version |
| `NoClassDefFoundError` | Class không có/không định nghĩa được theo yêu cầu runtime | Có thể do thiếu class hoặc lỗi khởi tạo, không nhất thiết major |
| `ClassNotFoundException` | Dynamic class lookup thất bại | Đường lookup/classloader không tìm được class |
| `NoSuchMethodError` | Method descriptor caller yêu cầu không tồn tại | Caller/callee ABI mismatch |
| `NoSuchFieldError` | Field descriptor không tồn tại | Field API binary mismatch |
| `AbstractMethodError` | Dispatch tới implementation không đáp ứng method | Interface/class ABI mismatch |
| `IllegalAccessError` | Truy cập class/member không hợp lệ ở runtime | Access rules/linkage, không phải class major |
| `ClassFormatError` | File class vi phạm cấu trúc class-file format | Không nhất thiết là version quá cao |
| `VerifyError` | Bytecode không vượt verification | Không nhất thiết cần JVM mới |
| `InaccessibleObjectException` | Reflection vào module/package bị chặn | JPMS/reflective access |
| `NoSuchElementException` ở ServiceLoader | Provider/config không phù hợp | SPI/runtime configuration |
| `UnsatisfiedLinkError` | Native library/symbol load fail | OS/ABI/JNI, không phải class-file major |

`UnsupportedClassVersionError` là một nhánh của các lỗi liên quan class loading/linkage, nhưng cách sửa phải dựa trên exception cụ thể. Nếu JVM báo class major 65 trên runtime 17, nâng một JSON parser không liên quan không giải quyết root cause.

## 21. Dependency bytecode policy trong multi-module system

### 21.1. Định nghĩa minimum runtime ở cấp sản phẩm

Ví dụ:

```text
Product: payment-service
Minimum supported Java runtime: 17
Maximum accepted class-file major for ordinary classes: 61
Preview classes: not allowed
Deployment: Linux x86-64 JDK 17 + JDK 21 matrix
```

Đây là policy minh họa; cần điều chỉnh nếu có multi-release JAR, modules sử dụng API đặc thù hoặc plugin/test-only graphs.

### 21.2. Mỗi module nên công bố rõ yêu cầu

Một reusable library có thể khai báo:

- Minimum Java runtime.
- Compiler target.
- Framework/Jakarta API versions.
- Required native libraries hoặc agents.
- Preview feature usage.
- Multi-release JAR behavior.
- Supported Gradle/Maven plugin/JDK combinations nếu nó là build plugin.

Không chỉ viết “Java compatible”; cần biết Java 8, 11, 17 hay 21.

### 21.3. Library API vs runtime dependency

Một thư viện được compile major 61 nhưng runtime-only provider major 65 không thể được coi là hoàn toàn hỗ trợ Java 17. Nếu provider bắt buộc cho chức năng chính, **effective minimum runtime** có thể là Java 21.

Ngược lại, một optional provider major 65 không được nạp trên Java 17 có thể vẫn cho phép một số chức năng chạy trên Java 17, nhưng contract phải công bố rõ feature/version boundary và có test.

### 21.4. Nên đặt guardrail trong CI

Nếu sản phẩm hỗ trợ Java 17:

- Compile Java source với `--release 17` khi phù hợp.
- Kiểm tra bytecode của produced classes.
- Quét third-party runtime dependencies.
- Phân biệt multi-release entries không được chọn.
- Chạy tests trên minimum JDK.
- Test packaged artifact, không chỉ source-set output.
- Gắn issue owner khi một dependency nâng minimum JDK.
- Ghi artifact checksum để chống “local pass, CI fail”.

Đừng chỉ kiểm tra `java -version` của build runner rồi mặc định runtime/dependencies đúng.

## 22. Kiểm tra theo artifact graph thay vì tên version

### 22.1. Inventory dữ liệu hữu ích

Một báo cáo có thể ghi:

| Artifact | Nguồn | Major cao nhất được quét | Major được chọn trên JDK 17 | Yêu cầu JDK theo vendor |
|---|---|---:|---|---|
| `app.jar` | Application | 61 | 61 | 17 |
| `crypto-core.jar` | Runtime direct | 65 | 65 | 21 |
| `json-core.jar` | Transitive | 55 | 55 | 11 |
| `multi-lib.jar` | Runtime transitive | 65 | 61 (MR-JAR) | 17+ |
| `build-plugin.jar` | Gradle plugin | 65 | Không thuộc app runtime | Gradle Daemon JDK 21 |

Các dòng chỉ là ví dụ giả định. Trong báo cáo thật, nếu classpath có nhiều classloaders, hoặc MR-JAR được xử lý riêng, cột “major được chọn” phải có bằng chứng cụ thể.

### 22.2. Tại sao cần vendor support và class scan cùng lúc?

- Vendor documentation nói library hỗ trợ Java 17 nhưng artifact bị publish nhầm class major 65.
- Artifact scan thấy chỉ major 61, nhưng library dùng JDK 21 API qua reflection có điều kiện hoặc native binding.
- MR-JAR chứa class 65 ở version 21, nhưng vendor hỗ trợ Java 17 bằng root/17 implementation.
- Một provider bị thiếu trên runtime Java 17 dù tất cả class major đều <=61.

Class scan phát hiện **một nhóm rủi ro rất cụ thể**, không thay thế full compatibility testing.

## 23. Runtime dependency mismatch sau nâng framework/BOM

### 23.1. Kịch bản

Trước migration:

```text
framework-bom vA
  -> library-x 2.x (minimum Java 17)
```

Sau khi nâng:

```text
framework-bom vB
  -> library-x 3.x (minimum Java 21)
```

Ứng dụng vẫn đặt `--release 17`. Build có thể thành công trên JDK 21 tùy API usage/compile graph, nhưng chạy trên Java 17 thì nạp `library-x 3.x` sẽ lỗi.

### 23.2. Không tự override một module rồi bỏ qua cả stack

Một framework có thể được kiểm thử với các versions phối hợp. Nếu downgrade `library-x` về 2.x, framework mới có thể gọi method chỉ xuất hiện ở 3.x.

Do đó:

1. Xác minh JDK requirement của framework release line.
2. Chọn BOM/platform phù hợp minimum runtime.
3. Nếu cần override, ghi rủi ro và test API/binary compatibility.
4. Không cho phép cùng họ library có nhiều versions không kiểm soát.
5. Quét output packaging và chạy application trên JDK tối thiểu.

### 23.3. Toolchain JDK mới là điều kiện build, không phải điều kiện deploy

Một tổ chức có thể dùng JDK 21 để build nhưng vẫn phát hành Java 17-compatible binaries. Điều đó hợp lệ nếu source/platform APIs/dependencies và generated code đều đáp ứng.

Ngược lại, chỉ vì Gradle Wrapper dùng JDK 21 không có nghĩa artifact tự động phải deploy trên Java 21.

## 24. Test trên minimum supported JDK

### 24.1. Khung kiểm chứng

Nếu library/app công bố hỗ trợ Java 17 và Java 21, có thể có matrix:

| Stage | JDK | Mục tiêu |
|---|---|---|
| Compile | 21 với `--release 17` | Giới hạn source/platform target |
| Bytecode scan | Tool đọc class-file | Xác nhận class major của artifact/deps |
| Unit/integration | 17 | Minimum runtime compatibility |
| Unit/integration | 21 | Target/new runtime compatibility |
| Packaged artifact smoke | 17 và 21 | Xác minh launcher, JAR/WAR và runtime libs |
| Production canary | Runtime mục tiêu | SLO, agent/native/security compatibility |

Không nhất thiết mỗi library đều test mọi JDK release. Nhưng **minimum supported runtime** là test quan trọng để bắt class-file major drift.

### 24.2. Test startup và tính năng lazy-loaded

Một service có thể nạp thư viện lỗi chỉ khi có request đặc biệt. Test cần kích hoạt:

- Endpoint nghiệp vụ chính.
- Background jobs và message consumers.
- Driver/provider discovery.
- Serialization formats.
- Plugin loading.
- Optional features có hỗ trợ trên minimum JDK.
- Failure/retry paths.
- Application startup/restart.

### 24.3. Đừng bỏ test runtime thấp nhất chỉ vì compiler đã dùng --release

`--release` hạn chế Java standard APIs và class-file target của source được compile, **không** hạ bytecode của JAR phụ thuộc. Runtime test trên minimum JDK vẫn là bằng chứng cần thiết.

## 25. Bảo mật và supply-chain khi chọn phương án sửa

### 25.1. Downgrade có thể bỏ bản vá bảo mật

Nếu một dependency release mới yêu cầu Java 21 do nâng platform, việc quay về release cũ có thể kéo theo CVEs hoặc hết support. Không downgrade chỉ để hết exception mà không xem security/vulnerability history.

Ưu tiên:

- Chọn release line còn được bảo trì trên JDK hiện tại.
- Nâng runtime có kiểm soát nếu business/support policy cho phép.
- Tách module cũ/feature theo boundary nếu cần.
- Có kế hoạch loại bỏ workaround và technical debt.

### 25.2. Không lấy JAR “đã hạ bytecode” không rõ nguồn

Các công cụ bytecode transformation/backport có thể có use case cụ thể, nhưng không có gì bảo đảm hạ class-file major là đủ để hỗ trợ runtime cũ, đặc biệt nếu code gọi API không có trong Java cũ.

Nếu sử dụng một phương án backport chính thức, cần:

- Nguồn tool/artifact đáng tin cậy.
- Compatibility contract được công bố.
- Security review và checksum.
- Integration tests trên runtime mục tiêu.
- Vendor/support stance.
- Release provenance rõ ràng.

### 25.3. Runtime image và JDK updates

Một container image tag có thể thay JDK update hoặc vendor. Ghi digest và xác nhận binary thực tế, tránh tình trạng dự án nói chạy Java 17 nhưng image mới đã nâng Java 21 hoặc vẫn dùng runtime cũ.

## 26. Kịch bản thực tế A: Application Java 17, dependency Java 21

Giả định:

```text
Application: invoice-service
Main source target: Java 17
Compile JDK: 21
Production JDK: 17
Dependency: report-engine 5.0
  -> render-core 3.0 (class major 65)
```

Khi application bắt đầu tạo báo cáo:

```text
UnsupportedClassVersionError: com/vendor/render/Renderer
class file version 65.0, runtime recognizes up to 61.0
```

### 26.1. Triaging

1. Xác minh production Java thật là 17.
2. Xác định `Renderer` nằm trong `render-core-3.0.jar`.
3. Dùng `javap` hoặc scanner xác nhận class major 65.
4. Kiểm tra đường transitive từ `report-engine`.
5. Đọc minimum Java requirement của vendor.
6. Xác minh framework/support matrix.

### 26.2. Hai nhánh có thể hợp lệ

**Nhánh 1:** Nâng runtime service lên JDK 21, giữ dependency 3.0, kiểm thử toàn bộ chức năng và vận hành.

**Nhánh 2:** Dùng release `render-core`/`report-engine` còn hỗ trợ Java 17, có compatibility test và security review.

**Không phải giải pháp:** sửa `sourceCompatibility=17` của app một lần nữa hoặc patch class header từ 65 xuống 61.

## 27. Kịch bản thực tế B: Gradle plugin lỗi, ứng dụng chưa từng chạy

Giả sử:

```text
Gradle Daemon: Java 17
Java toolchain: Java 21
Custom convention plugin: compiled for Java 21 (major 65)
Application release target: Java 17
```

Build fail khi apply plugin, trước khi `compileJava` thực thi.

### 27.1. Root cause

Plugin là binary chạy trong **Gradle Daemon JVM Java 17**. Nó không được nạp chỉ vì Java toolchain compiler là Java 21.

### 27.2. Hướng sửa

- Nếu Gradle distribution/plugin support cho phép, chạy Daemon trên JDK 21.
- Hoặc biên dịch/publish plugin nội bộ target thấp hơn, với public Gradle APIs phù hợp.
- Test plugin consumer fixtures trên các Gradle/JDK combinations được cam kết.
- Giữ application target/release policy riêng.

Không tự nâng application bytecode target 21 nếu sản phẩm vẫn cần chạy Java 17.

## 28. Kịch bản thực tế C: Multi-release JAR báo major 65 nhưng JDK 17 vẫn chạy

Giả sử một JAR chứa:

```text
com/example/Codec.class                     -> major 52
META-INF/versions/17/com/example/Codec.class -> major 61
META-INF/versions/21/com/example/Codec.class -> major 65
```

Manifest có `Multi-Release: true`. Scanner inventory thấy major 65. Khi chạy trên JDK 17 với loader hỗ trợ MR-JAR, class version 17 được chọn và có thể load bình thường.

Trong trường hợp này, policy scanner cần phân biệt:

- High-major class ở versioned directory dành cho runtime cao.
- High-major class trong root hoặc effective path của minimum runtime.
- Preview/minor restrictions.
- Có hay không loader xử lý MR-JAR đúng contract.

Không loại bỏ một thư viện tốt chỉ vì scanner đọc tổng mức major mà không hiểu multi-release semantics.

## 29. Kịch bản thực tế D: ASM không hỗ trợ classfile mới

Giả sử build trên Java 21:

```text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
    at org.objectweb.asm.ClassReader...
    at some.coverage.Plugin...
```

JVM có thể vẫn hỗ trợ class 65. Vấn đề nằm ở version thư viện **đọc hoặc transform bytecode**.

Các bước:

1. Xác định plugin/agent/classloader chứa ASM thực tế.
2. Kiểm tra support matrix của plugin với classfile Java 21.
3. Nâng công cụ được hỗ trợ (coverage, instrumentation, Groovy/compiler hoặc framework plugin).
4. Kiểm tra transitive ASM conflicts.
5. Chạy lại build/test trên JDK đích.
6. Không ép hạ target source tùy tiện nếu application cần Java 21 features.

Nếu cần dùng `-Xlog:class+load` hoặc plugin dependency inspection, làm có kiểm soát. Một bản ASM mới hơn không nhất thiết sửa lỗi nếu plugin vẫn dùng internal API khác không còn tương thích.

## 30. Kịch bản thực tế E: Preview class có minor 65535

Một library được build với Java 21 preview nhưng được triển khai trên Java 21 không bật preview. Class mang:

```text
major: 65
minor: 65535
```

Khi nạp, runtime có thể từ chối vì preview feature chưa được bật. Tùy chính sách sản phẩm:

- Bật preview trên đúng JDK release nếu được phép.
- Chọn stable release của library không dùng preview.
- Rebuild source không dùng preview feature nếu có thể.
- Tránh công bố release Java21-preview là Java17-compatible.

Không dùng `--enable-preview` để “cho phép” JDK 17 chạy bytecode major 65 hoặc để chạy preview class Java21 trên runtime Java22.

## 31. Bộ câu hỏi điều tra nhanh

Khi nhận ticket lỗi, có thể bắt đầu bằng chuỗi câu hỏi:

1. Exception type chính xác là `UnsupportedClassVersionError` hay exception từ ASM/Gradle?
2. Runtime/process nào ném lỗi — application JVM, Maven, Gradle Daemon, JUnit fork hay agent?
3. JVM đó dùng Java release và vendor/build nào?
4. Class được báo tên gì?
5. Class có major/minor bao nhiêu?
6. Nó nằm trong JAR nào, lồng dưới archive nào?
7. JAR này thuộc direct/transitive/runtime/plugin/processor/test dependency?
8. Tại sao dependency version đó được chọn?
9. Có duplicate JAR hoặc classloader riêng không?
10. Đây có phải multi-release entry hoặc preview class không?
11. Minimum supported JDK của product/framework là gì?
12. Có thể nâng runtime, chọn dependency release khác hoặc rebuild đúng artifact không?
13. Phương án có phá ABI, security support hoặc framework BOM alignment không?
14. Đã test packaged artifact trên minimum JDK thật chưa?

Mỗi câu nên có bằng chứng: log, bytecode scan, dependency graph, JDK metadata hoặc vendor documentation.

## 32. Hồ sơ bàn giao một lỗi bytecode compatibility

Một bản điều tra hữu ích có thể ghi:

```yaml
incident:
  error_type: "java.lang.UnsupportedClassVersionError"
  class_name: "com.example.crypto.NativeBridge"
  class_file:
    major: 65
    minor: 0
    required_java: 21
runtime:
  java_version: 17
  max_supported_major: 61
  image_digest: "<digest>"
artifact:
  name: "crypto-core.jar"
  sha256: "<sha256>"
  location: "app.jar!/BOOT-INF/lib/crypto-core.jar"
dependency:
  kind: "transitive-runtime"
  path: "app -> sdk -> crypto-core"
build:
  compile_jdk: 21
  application_release_target: 17
  runtime_dependency_scan: "completed"
decision:
  action: "<upgrade-runtime-or-select-compatible-library>"
  owner: "<owner>"
verification:
  minimum_jdk_test: "PENDING"
  packaged_smoke: "PENDING"
```

Đây là dữ liệu ví dụ, không phải một incident có thật. Nếu source application major 61 nhưng transitive library major 65, ghi rõ cả hai: đó là bằng chứng vì sao chỉnh application compiler target **không giải quyết được root cause**.

## 33. Checklist chẩn đoán và phát hành

### Xác định lỗi

- [ ] Đã xác nhận exception thực sự đến từ JVM hay bytecode parser/tooling.
- [ ] Đã lưu full stack trace và `Caused by`.
- [ ] Đã xác minh đúng process/JVM version gây lỗi.
- [ ] Đã ghi class name, major và minor version.
- [ ] Đã phân biệt ordinary class và preview class.
- [ ] Đã xác định thời điểm lỗi: startup, test, build plugin hay lazy runtime path.

### Tìm đúng artifact

- [ ] Đã xác minh JAR/class chứa class gây lỗi bằng checksum.
- [ ] Đã kiểm tra direct/transitive dependency path.
- [ ] Đã kiểm tra compile/runtime/test/processor/plugin configurations liên quan.
- [ ] Đã kiểm tra nested JAR, fat/shaded JAR hoặc server shared libraries.
- [ ] Đã kiểm tra multi-release JAR và effective entry theo runtime.
- [ ] Đã kiểm tra duplicate classes/classloader khi có dấu hiệu.
- [ ] Đã quan sát artifact **được deploy**, không chỉ output trước packaging.

### Chọn giải pháp

- [ ] Đã đối chiếu minimum supported JDK của sản phẩm và dependency.
- [ ] Đã phân biệt nâng runtime, đổi dependency và recompile artifact sở hữu source.
- [ ] Đã kiểm tra Maven/Gradle BOM/platform alignment.
- [ ] Không downgrade library mà chưa review ABI và CVE.
- [ ] Không sửa thủ công class-file header để “hạ bytecode”.
- [ ] Đã cấu hình `--release`/compiler toolchain cho generated/application classes phù hợp.
- [ ] Đã kiểm tra plugin/JUnit/agent ASM parser support nếu lỗi thuộc tooling.
- [ ] Đã kiểm tra preview flags theo đúng release, không dùng để vượt major mismatch.

### Kiểm chứng

- [ ] Đã quét class-file headers của artifact và dependencies thực sự deploy.
- [ ] Đã test trên minimum runtime JDK.
- [ ] Đã chạy các code paths nạp optional/lazy/plugin providers.
- [ ] Đã chạy unit, integration, contract và packaged smoke tests.
- [ ] Đã kiểm tra Java agents, native libraries và application server khi liên quan.
- [ ] Đã xác nhận security/support policy và vendor compatibility.
- [ ] Đã ghi checksum, selected version, root cause và rollback.
- [ ] Đã lưu CI guardrail để phát hiện bytecode drift về sau.

**Kết luận:** `UnsupportedClassVersionError` là dấu hiệu rất cụ thể: một JVM không chấp nhận class-file version mà nó phải nạp. Nhưng đối tượng bị từ chối có thể là **bất kỳ class nào trong runtime/build/test graph**, không nhất thiết là code do project vừa compile. Chẩn đoán hiệu quả bắt đầu bằng **đọc major/minor, xác minh đúng JVM, định vị đúng class và artifact, phân biệt JVM loader với ASM/tooling parser, rồi kiểm tra dependency graph và classloader**. Chỉ sau đó mới chọn nâng JDK runtime, chuyển sang dependency release được hỗ trợ hoặc compile lại artifact thực sự cần sửa. Cách tiếp cận này giảm nguy cơ sửa sai tầng và tạo được bằng chứng rõ ràng cho từng bước Java compatibility migration.
