# Thứ tự tệp, encoding, locale và đường dẫn ảnh hưởng đến đầu ra Maven như thế nào?

> **Chủ đề: Build tái lập — Build Tool Maven.** Bài học phân tích những biến đầu vào dễ bị bỏ qua khiến hai lần build **cùng source và POM** tạo ra JAR khác byte, đồng thời hướng dẫn cố định thứ tự tệp, UTF-8, locale, đường dẫn, timestamp và toolchain để có thể kiểm tra tính tái lập.

## 1. “Build thành công” khác “build tái lập”

**Reproducible build (build tái lập)** nghĩa là khi dùng cùng mã nguồn, hướng dẫn build và môi trường đã được xác định/chuẩn hóa, những người build độc lập có thể tạo ra các **artifact giống nhau từng byte**. Hai JAR cùng chạy cho cùng kết quả không nhất thiết giống nhau ở cấp byte.

Ví dụ:

```text
Cùng Git commit và POM
    |
    +-- Máy A: Linux, UTF-8, en_US, /build/project
    |       |
    |       v
    |   target/app.jar -> SHA-256 AAA...
    |
    +-- Máy B: Windows, charset/locale khác, C:\work\project
            |
            v
        target/app.jar -> SHA-256 BBB...

Nếu AAA != BBB: build chưa tái lập bit-for-bit trong hai môi trường đó.
Nếu AAA == BBB: bằng chứng tốt cho hai lần build, chưa tự chứng minh mọi môi trường.
```

Mục tiêu không phải “mọi file tạm trong `target` đều giống nhau”. Phải **xác định đối tượng so sánh**: JAR chính, JAR sources, POM publish, distribution ZIP/TAR, OCI image hoặc SBOM. Đối với một Java library, thường trước hết là **JAR được phát hành** và những attached artifacts bắt buộc.

### Các mức độ kiểm tra

| Phép thử | Nó chứng minh điều gì? | Chưa chứng minh điều gì? |
| --- | --- | --- |
| Hai lần `mvn package` đều `BUILD SUCCESS` | Compilation/tests/package không báo lỗi | Hai artifacts có cùng byte |
| Hai JAR trả cùng stdout | Một hành vi quan sát được giống nhau | Timestamps, entry order, manifest, metadata giống nhau |
| Hai SHA-256 JAR bằng nhau | Hai tệp được so sánh trùng byte với xác suất va chạm hash cực nhỏ | Mọi môi trường độc lập đều sẽ cho cùng output |
| `artifact:compare` pass so với reference | Artifact Plugin xác nhận nội dung output so sánh khớp reference theo phạm vi của goal | Bảo đảm mọi phiên bản toolchain/OS/supply chain đều tái lập |
| Rebuild độc lập từ source tại môi trường khác và kiểm tra hash | Bằng chứng mạnh hơn về reproducibility | Không tự chứng minh source không chứa mã độc hay nghiệp vụ đúng |

**Build tái lập không đồng nghĩa build an toàn, build không có bug, hoặc chỉ là cache hit.** Nó tạo khả năng độc lập xác minh rằng binary tương ứng với một nguồn và môi trường được công bố.

## 2. Bốn nhóm biến mà bài này tập trung

| Nhóm | Đầu vào dễ biến động | Tác động lên output |
| --- | --- | --- |
| **Thứ tự tệp** | `File.listFiles()`, `Files.walk()`, HashMap/HashSet, filesystem directory enumeration | Thứ tự dòng báo cáo, JSON/XML, file list, classpath index, ZIP/JAR entries |
| **Encoding và xuống dòng** | Default charset, UTF-8/Windows-1252, CRLF/LF, BOM, Maven resource filtering | Nội dung resources, source literals, generated text, checksum của archive |
| **Locale, timezone** | `Locale.getDefault()`, `String.format`, `Collator`, `toLowerCase`, `ZoneId.systemDefault()` | Dấu thập phân, tháng/ngày, thứ tự sắp xếp, chữ hoa/thường, timestamp biểu diễn |
| **Đường dẫn và filesystem** | `user.dir`, absolute build path, separator `/` vs `\`, symlink, case sensitivity, Unicode path normalization | Nội dung generated files, debug metadata, manifest, cấu trúc archive, lỗi tìm input |

Những nguyên nhân khác thường xuất hiện cùng: **thời gian hiện tại**, JDK/compiler/vendor version, plugin versions, environment variables, username/hostname, dependency ranges/SNAPSHOT, thứ tự chạy không ổn định của parallel build và annotation processors không deterministic.

Bốn nhóm trên quan trọng vì không cần đổi một dòng Java business code nào, bạn vẫn có thể làm JAR thay hash.

## 3. Thứ tự tệp: filesystem không hứa trả về thứ tự bạn mong đợi

Giả sử có:

```text
assets/
├── a.txt
├── b.txt
└── c.txt
```

Một chương trình tạo `index.txt` bằng cách duyệt thư mục:

```java
// PHẢN VÍ DỤ: thứ tự phần tử không được bảo đảm.
try (var stream = java.nio.file.Files.list(root)) {
    stream.forEach(path -> output.append(path.getFileName()).append('\n'));
}
```

`Files.list` không bảo đảm thứ tự nhất quán. `File.listFiles()`, `Files.walk()` hoặc duyệt `HashMap` cũng không nên được xem là một thứ tự nghiệp vụ có bảo đảm.

Trên một máy, vài lần chạy có thể tình cờ trả cùng thứ tự. **Đó không phải hợp đồng API**, nên không thể dùng làm cơ sở cho reproducibility.

### Cách đúng: định nghĩa thứ tự rõ ràng

```java
try (var stream = java.nio.file.Files.list(root)) {
    stream
        .map(path -> path.getFileName().toString())
        .sorted()
        .forEach(name -> output.append(name).append('\n'));
}
```

`sorted()` ở đây dùng thứ tự tự nhiên của Java `String`, **không dựa vào default locale**. Nếu đặc tả yêu cầu thứ tự văn bản theo tiếng Việt/tiếng Đức, hãy chọn một Collator/locale và chính sách so sánh ổn định có kiểm soát; đừng tự dùng locale máy.

### “Sorted” phải áp dụng trên đúng key

Sắp xếp theo absolute path có thể tạo hai output khác nhau giữa `/home/ci/project` và `C:\runner\project`. Với một archive/report, thông thường nên tạo **relative paths**, chuẩn hóa separator thành `/`, rồi sort theo những tên tương đối đó.

Ví dụ:

```text
Không nên:
C:\agent\workspace\project\assets\a.txt
/home/runner/work/project/assets/a.txt

Nên (tên logic trong archive):
assets/a.txt
```

Cũng cần xác định cách xử lý chữ hoa/chữ thường và Unicode: `A.txt` khác `a.txt` trên một số filesystem, nhưng có thể đụng tên trên hệ thống không phân biệt chữ hoa/thường. Tên có dấu có thể có các cách chuẩn hóa Unicode NFC/NFD; “cùng nhìn bằng mắt” chưa chắc là cùng chuỗi byte.

## 4. Thứ tự entry trong JAR/ZIP cũng ảnh hưởng checksum

JAR là một dạng ZIP. Hai archive có cùng danh sách tệp và cùng nội dung tệp vẫn có thể **khác byte** do:

- Thứ tự các ZIP entries khác nhau.
- Timestamp/extended timestamp trong local header và central directory khác.
- ZIP metadata, permissions, platform flags khác.
- Compression mode/level hoặc ZIP implementation khác.
- `META-INF/MANIFEST.MF` có thứ tự attributes, giá trị hoặc newline khác.
- Metadata sinh ra từ plugin chứa thời gian, tên máy, đường dẫn hoặc user.
- Một tệp generated trong archive có nội dung khác dù source inputs giống nhau.

Không nên “giải quyết” bằng cách lấy hai archive, unzip rồi so sánh **chỉ tên tệp**: như vậy bỏ qua trường hợp archive metadata khác và trường hợp nội dung tệp khác.

### Kiểm tra sơ bộ thứ tự entry

```bash
jar tf target/repro-path-demo-1.0.0.jar
```

Lệnh này liệt kê archive entries; nó hữu ích để nhận diện thành phần bất thường, **không đủ xác minh bit-for-bit**. Để kết luận, so SHA-256 của chính tệp JAR.

### Các plugin Maven hiện đại hỗ trợ tính tái lập

Maven JAR Plugin từ **3.2.0** hỗ trợ `outputTimestamp`; ở đây dùng **3.4.2**. Khi `project.build.outputTimestamp` có giá trị cố định, plugin có thể chuẩn hóa timestamps của archive entries thay vì để wall-clock time đi vào ZIP.

Các plugin khác như Source, Javadoc, Assembly, Shade, WAR hoặc Spring Boot repackage có thể tạo những artifact bổ sung. **Mỗi plugin cần kiểm tra version và khả năng reproducible output của chính nó**. Đổi timestamp trong JAR Plugin **không thể sửa một tệp JSON được ứng dụng sinh bằng HashMap không sorted**.

## 5. Encoding: một file có dấu có thể đổi byte mà không đổi ý nghĩa

Một file `messages/greeting.txt` chứa:

```text
Chào Maven
```

Nếu lưu bằng **UTF-8**, các ký tự tiếng Việt có một chuỗi bytes. Nếu ai đó lưu theo một code page cục bộ, hoặc tool đọc/ghi bằng default charset khác, output có thể bị **mojibake**, lỗi parse, thay ký tự hoặc ít nhất khác checksum.

### Điều phải cố định

- Encoding của **Java source**.
- Encoding của **resource files** khi đọc/ghi/filter.
- Encoding của **report/documentation/generated text**.
- Encoding khi **Java application đọc resource**.
- Encoding khi **ứng dụng ghi kết quả**.
- Encoding **console output** nếu stdout bytes cũng là artifact được kiểm chứng.

Trong Maven POM, các properties hữu ích:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
```

Maven Compiler Plugin đọc `project.build.sourceEncoding` làm mặc định cho tham số `encoding`. Maven Resources Plugin cũng dùng property này mặc định cho **filtered resources**, nếu chưa override.

**Đừng nhầm:** `project.build.sourceEncoding` không cưỡng chế mọi tool và mọi file trong source tree tự đổi sang UTF-8. Nó là cấu hình được các plugin **có hỗ trợ** sử dụng. Một custom annotation processor hoặc shell script vẫn có thể dùng system default encoding nếu viết thiếu rõ ràng.

### Java 17: đọc và ghi rõ UTF-8

```java
String text = java.nio.file.Files.readString(
        path, java.nio.charset.StandardCharsets.UTF_8);

java.nio.file.Files.writeString(
        outputPath, text, java.nio.charset.StandardCharsets.UTF_8);
```

Đối với classpath resource:

```java
try (var in = MyClass.class.getResourceAsStream("/messages/greeting.txt")) {
    if (in == null) {
        throw new java.io.IOException("Missing greeting resource");
    }
    String text = new String(
        in.readAllBytes(),
        java.nio.charset.StandardCharsets.UTF_8);
}
```

Đoạn classpath mẫu này **là code fragment**, không phải class độc lập. Project runnable đầy đủ nằm ở mục 10.

### Một bẫy riêng của `.properties`

API Java `Properties.load(InputStream)` truyền thống hiểu bytes theo **ISO-8859-1**, không tự suy UTF-8. Nếu file properties thực tế là UTF-8, dùng `Properties.load(Reader)` với `InputStreamReader(..., StandardCharsets.UTF_8)`, hoặc escape đúng format áp dụng.

Trong Maven resource filtering, `maven-resources-plugin` có cả `encoding` và `propertiesEncoding` (từ bản 3.2.0) để xử lý file properties khi cần. **Không áp dụng filtering cho ảnh, ZIP hoặc tệp nhị phân**; một biến đổi text giả định trên binary có thể làm hỏng nội dung.

## 6. Xuống dòng và BOM: LF khác CRLF ở cấp byte

Nhiều file text có thể biểu diễn newline bằng:

- **LF**: byte `0A`, thường thấy trên Linux/macOS.
- **CRLF**: bytes `0D 0A`, thường thấy trên Windows.

Hai phiên bản hiển thị cùng ba dòng chữ có thể khác hash:

```text
LF:   61 0A 62 0A         (a\nb\n)
CRLF: 61 0D 0A 62 0D 0A   (a\r\nb\r\n)
```

Cả hai có thể được ứng dụng xử lý đúng; nhưng nếu chúng được đưa nguyên vào JAR, file `.properties`, generated README hoặc manifest, JAR có thể khác byte.

### Cách kiểm soát

1. Chọn một EOL chuẩn cho **source text/resources**; thường LF trong repository đa nền tảng.
2. Dùng `.gitattributes` để đảm bảo Git checkout theo quy ước.
3. Với **generated text**, dùng `"\n"` tường minh khi contract yêu cầu LF, không dùng `System.lineSeparator()` hoặc `%n` nếu muốn byte output giống nhau trên Windows/Unix.
4. Khi đọc input từ bên ngoài có EOL khác, chỉ normalize ở **ranh giới dữ liệu được phép**, không tự biến đổi binary hoặc dữ liệu cần giữ nguyên chữ ký.

Một `.gitattributes` minh họa:

```gitattributes
*.java text eol=lf
*.xml text eol=lf
*.md text eol=lf
*.txt text eol=lf
*.properties text eol=lf
*.csv text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
```

Đây là **tệp Git config**, không phải lệnh shell. Khi bổ sung file vào một repository có sẵn, cần review việc Git renormalize và commit lại changes phù hợp; không thực hiện `git add --renormalize .` vào repository người khác ngoài phạm vi được giao.

**BOM** (Byte Order Mark, ví dụ `EF BB BF` của UTF-8) là một khác biệt byte khác. Nếu repo quy định UTF-8 không BOM, phải kiểm tra editor/tool chain không tự thêm BOM.

## 7. Locale: văn bản giống về ý nhưng biểu diễn khác

Java có **default locale** lấy từ environment. Nếu bạn format số hoặc ngày mà không chỉ định locale, hai môi trường có thể ra các chuỗi khác nhau.

```java
double amount = 1234.5;

// PHẢN VÍ DỤ: phụ thuộc default locale của JVM.
String unstable = String.format("%.2f", amount);

// ỔN ĐỊNH hơn: cố định locale cho định dạng machine-readable.
String stable = String.format(java.util.Locale.ROOT, "%.2f", amount);
```

Với `Locale.ROOT`, kết quả định dạng số trong ví dụ là:

```text
1234.50
```

Với một default locale dùng dấu phẩy làm dấu thập phân, `String.format("%.2f", amount)` có thể xuất ra `1234,50`. Không thể dùng hai dạng thay nhau nếu chúng là nội dung file được hash/ký.

### Thứ tự sort theo ngôn ngữ

`Collator.getInstance()` không cố định locale khi không truyền tham số; quy tắc so sánh `ä`, `a`, `z` có thể khác giữa các ngôn ngữ/phiên bản dữ liệu Unicode. Hãy xác định:

- **Machine-readable order:** thứ tự natural Java String, hoặc comparator rõ ràng từ spec.
- **Human-facing linguistic order:** chọn `Locale` cụ thể, `Collator` strength/decomposition và test theo phiên bản JDK/Unicode/cấu hình.

Không nhất thiết mọi danh sách đều phải sắp xếp theo alphabet tiếng Anh; cái quan trọng là **thứ tự đã được định nghĩa và kiểm soát**.

### Chữ hoa/thường và Turkish I

`String.toLowerCase()` không truyền locale có thể phụ thuộc `Locale.getDefault()`. Đối với protocol identifiers hoặc keys không mang ý nghĩa ngôn ngữ, thường dùng:

```java
String key = input.toLowerCase(java.util.Locale.ROOT);
```

Nhưng **Locale.ROOT không phải phép chuẩn hóa identifier an toàn tuyệt đối trong mọi giao thức**. Phải làm đúng rules của từng loại dữ liệu; với filename/path, case-sensitivity của filesystem còn là một yếu tố khác.

## 8. Timezone và timestamp: hai lớp cần cố định

**Thứ nhất, timestamp trong archive:** JAR Plugin cần một đầu vào ổn định cho ZIP entry times; đó là vai trò `project.build.outputTimestamp`.

**Thứ hai, text timestamp trong nội dung:** Nếu code sinh `report.json` bằng `LocalDateTime.now()`, hoặc dùng timezone mặc định để hiển thị `Instant`, nội dung file vẫn thay đổi theo thời gian/múi giờ dù ZIP entry timestamp đã được cố định.

### Cấu hình Maven output timestamp

```xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Đây là một **giá trị ví dụ cố định** cho bài thực hành, không phải khuyến cáo dùng mốc 2024 cho mọi release. Đối với release thật, có thể dùng timestamp của commit release đã được xác nhận, hoặc cơ chế update timestamp có kiểm soát khi phát hành. **Không dùng wall-clock now ngẫu nhiên ở mỗi build**.

Maven Reproducible Builds Guide giải thích cách Release Plugin cập nhật `project.build.outputTimestamp` khi release trên các version có hỗ trợ. Dự án dùng CI-friendly versioning, timestamp lấy từ Git hay custom script phải tránh circular inputs (ví dụ commit thay timestamp làm chính commit timestamp đổi).

### Timestamp trong Java output

Phản ví dụ:

```java
String report = "builtAt=" + java.time.ZonedDateTime.now();
```

Cách ổn định khi cần hiển thị một thời điểm **đã được cung cấp từ input**:

```java
java.time.Instant sourceTime =
        java.time.Instant.parse("2024-01-01T00:00:00Z");
String report = "builtAt=" + sourceTime.toString();
```

`Instant` trong ví dụ là dữ liệu đã cố định, không dựa vào `ZoneId.systemDefault()`. Trong phần lớn JSON/machine-readable reports, nên chọn UTC theo hợp đồng cụ thể.

Không ghi `user.name`, hostname, `user.home` hoặc path CI agent vào manifest nếu không có lý do nghiệp vụ thực sự. Các giá trị đó làm binary phụ thuộc môi trường.

## 9. Đường dẫn: relative, absolute và separator

Hai runner có thể build cùng commit dưới:

```text
/home/runner/work/product
C:\agent\_work\product
```

Nếu một code generator viết:

```java
// PHẢN VÍ DỤ: rò rỉ absolute path của người build.
String root = java.nio.file.Path.of(".").toAbsolutePath().toString();
java.nio.file.Files.writeString(outputFile, "buildRoot=" + root);
```

thì file tạo ra khác dù source giống nhau. Nếu file này được đóng vào JAR, checksum khác.

### Bốn quy tắc

1. **Không nhúng absolute workspace path** vào artifacts, trừ khi spec yêu cầu và đường dẫn đã được chuẩn hóa.
2. Khi report tên file, lấy `root.relativize(path)` chứ không lấy `path.toAbsolutePath()`.
3. Trong archive logical path, dùng separator `/` thống nhất, không copy platform-specific `File.separator` vào metadata.
4. Phân biệt filesystem path và **URL/URI**. Không tạo URL bằng cách nối string với `File.separator`; URI có conventions riêng.

### Filesystem khác nhau còn ở điều gì?

- Windows có ổ đĩa và dấu `\`; Unix dùng `/`. Java `Path` xử lý path theo filesystem provider.
- Windows/macOS có thể không phân biệt case mặc định; Linux thường phân biệt case.
- Symlink và quyền executable có metadata khác; Git checkout có thể xử lý khác.
- File timestamps và granularity filesystem không giống nhau.
- Unicode filenames có thể được lưu theo dạng chuẩn hóa khác nhau.
- Path length, reserved filenames và reserved device names có thể gây build fail trên một hệ thống.
- ZIP/JAR entry names là đường dẫn **logic** trong archive, không phải native `Path` string của OS.

**Không sửa mọi path bằng một `replace("\\", "/")` rồi cho rằng đã an toàn:** trước đó vẫn phải xác định đúng root, chống path traversal `..` nếu input không tin cậy và xử lý symlink theo chính sách.

## 10. Demo Java 17 hoàn chỉnh: input UTF-8, thứ tự xác định, locale độc lập

Ta xây một Maven project nhỏ **`repro-path-demo`** với Java 17, một resource tiếng Việt, một ứng dụng in báo cáo UTF-8 theo thứ tự rõ ràng và một utility liệt kê **relative filenames đã sắp xếp**.

POM pin các plugins liên quan và đặt `project.build.outputTimestamp`. Mục tiêu là **có đầu ra kiểm chứng được**, không phải tuyên bố cấu hình này tự giải quyết mọi yếu tố môi trường của một ứng dụng lớn.

### 10.1. Yêu cầu

- Maven 3.9.x và JDK 17 (nên dùng **cùng JDK distribution/build** trong lần thử đầu).
- Maven Central hoặc mirror có thể tải JUnit 5.11.4 và Maven plugins.
- Terminal có thể chạy `java`/`javac`/`jar`. Để tính SHA-256 trên Linux/macOS, dùng `sha256sum` hoặc `shasum -a 256`; trên Windows PowerShell dùng `Get-FileHash`.
- Hai lần build đầu nên cùng OS/JDK/Maven và cùng source bytes. Sau đó mới thử cross-platform để phân tích sự khác biệt.

### 10.2. Cây project

```text
repro-path-demo/
├── pom.xml
├── .gitattributes
└── src/
    ├── main/
    │   ├── java/dev/lesson/repro/
    │   │   ├── DeterministicApp.java
    │   │   └── FileOrder.java
    │   └── resources/messages/greeting.txt
    └── test/java/dev/lesson/repro/
        ├── DeterministicAppTest.java
        └── FileOrderTest.java
```

**Không tạo thư mục `target` thủ công**; Maven sinh nó khi chạy. Resource `greeting.txt` phải được lưu dưới UTF-8, tốt nhất với newline LF đã thống nhất.

### 10.3. `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>repro-path-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
            </resource>
        </resources>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.lesson.repro.DeterministicApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-artifact-plugin</artifactId>
                <version>3.7.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Ý nghĩa quan trọng:**

1. `maven.compiler.release=17` giữ target Java 17; Compiler Plugin dùng `encoding=UTF-8` cho Java source.
2. Resources Plugin copy tệp `greeting.txt` dưới `src/main/resources` vào `target/classes/messages/greeting.txt`. Ở đây **`filtering=false`** để tránh nội dung bị thay thế ngoài ý muốn; dữ liệu UTF-8 source vẫn phải đồng nhất byte.
3. `project.build.outputTimestamp=2024-01-01T00:00:00Z` đưa **timestamp cố định** cho plugin đóng archive, thay vì lấy current build time. Nó không thay byte của generated report nếu report tự dùng `now()`.
4. `maven-jar-plugin:3.4.2` hỗ trợ `outputTimestamp`; manifest trỏ đúng main class, JAR chạy được bằng `java -jar`.
5. `maven-artifact-plugin:3.7.0` cung cấp `artifact:check-buildplan` và `artifact:compare` để đánh giá kế hoạch plugins và so output với reference. **Không có execution tự động**: các goals này được gọi riêng khi cần.
6. JUnit Jupiter chỉ là test dependency; không được đóng vào JAR runtime.
7. Plugin versions được pin để tránh một build lấy implementation plugin khác ngoài ý muốn. Tính tái lập trong project thật còn yêu cầu pin Maven/JDK, generated sources, dependency graph và repo metadata.
8. Plugin Artifact 3.7.0 đã được tài liệu chính thức nêu là chạy trên Maven >=3.6.3, JDK >=8; ví dụ dùng Maven 3.9/JDK17 phù hợp.

### 10.4. Resource UTF-8 — `src/main/resources/messages/greeting.txt`

```text
Chào Maven
```

Lưu đúng UTF-8 (nên không BOM). Thêm newline LF cuối file nếu theo convention repo. Ứng dụng gọi `.strip()` khi đọc nên cả có hoặc không có newline cuối đều cho cùng **giá trị chuỗi**; nhưng **byte resource trong JAR vẫn khác** nếu hai checkout giữ EOL khác nhau. Đó là lý do cần `.gitattributes` và so byte của resource, không chỉ so stdout.

### 10.5. `src/main/java/dev/lesson/repro/DeterministicApp.java`

```java
package dev.lesson.repro;

import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Map;

public final class DeterministicApp {

    private DeterministicApp() {
    }

    static String loadGreeting() throws IOException {
        try (InputStream input = DeterministicApp.class
                .getResourceAsStream("/messages/greeting.txt")) {
            if (input == null) {
                throw new IOException("Missing messages/greeting.txt");
            }
            return new String(input.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }
    }

    public static String render(Map<String, Integer> values, String greeting) {
        StringBuilder out = new StringBuilder();
        out.append("MESSAGE=").append(greeting).append('\n');

        values.entrySet()
                .stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> out.append(entry.getKey())
                        .append('=')
                        .append(entry.getValue())
                        .append('\n'));

        out.append("PRICE=")
                .append(String.format(
                        Locale.ROOT, "%.2f", new BigDecimal("1234.5")))
                .append('\n');

        return out.toString();
    }

    public static void main(String[] args) throws IOException {
        String greeting = loadGreeting();

        String report = render(
                Map.of("beta", 2, "alpha", 1, "gamma", 3),
                greeting
        );

        // Xác định cả byte encoding của stdout, không dùng charset console.
        System.out.write(report.getBytes(StandardCharsets.UTF_8));
        System.out.flush();
    }
}
```

**Giải thích từng quyết định:**

- `loadGreeting()` lấy resource từ **classpath**, không dựa vào `user.dir` hay absolute path của workspace.
- `StandardCharsets.UTF_8` đảm bảo tệp tài nguyên được đọc rõ encoding; `.strip()` chỉ chuẩn hóa whitespace biên **cho mục đích hiển thị trong demo**, không ghi lại tệp nguồn.
- `Map.of(...)` không hứa thứ tự iteration; code **không dựa** vào thứ tự đó.
- `sorted(Map.Entry.comparingByKey())` đưa các keys về thứ tự natural String cố định, không phụ thuộc filesystem/locale.
- `append('\n')` cho LF cụ thể, không phụ thuộc `System.lineSeparator()`.
- `String.format(Locale.ROOT, ...)` không phụ thuộc default locale khi render decimal.
- `System.out.write(...UTF_8)` giữ **stdout bytes** ổn định ngay cả khi terminal mặc định có charset khác. Terminal cần hỗ trợ UTF-8 để hiển thị dấu đúng.
- Không ghi current time, hostname, username hoặc build directory vào stdout.

**Nội dung stdout chính xác (UTF-8, LF):**

```text
MESSAGE=Chào Maven
alpha=1
beta=2
gamma=3
PRICE=1234.50
```

Có một ký tự LF cuối dòng `PRICE`. Nếu console của hệ điều hành không render UTF-8, ký tự có dấu có thể hiển thị sai dù **bytes do app tạo vẫn là UTF-8 đúng**.

### 10.6. `src/main/java/dev/lesson/repro/FileOrder.java`

```java
package dev.lesson.repro;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public final class FileOrder {

    private FileOrder() {
    }

    public static List<String> relativeFiles(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            return paths
                    .filter(Files::isRegularFile)
                    .map(root::relativize)
                    .map(path -> path.toString()
                            .replace(File.separatorChar, '/'))
                    .sorted()
                    .toList();
        }
    }
}
```

Hàm này:

- Duyệt các tệp con bằng `Files.walk` nhưng **không tin thứ tự ban đầu**.
- Lấy đường dẫn tương đối với `root`, không đưa absolute workspace root vào output.
- Chuẩn hóa `File.separatorChar` thành `/` cho tên logic trong report/archive.
- Sort theo tên tương đối cuối cùng, không phụ thuộc thứ tự enumeration của filesystem.
- Trả list mới ổn định với **cùng bộ file và cùng tên logic**.

**Giới hạn đã nêu:** ví dụ không theo symbolic links mặc định, và không chuẩn hóa NFC/NFD/case. Với repository có symlink hoặc tên có dấu phức tạp, cần chính sách riêng để tránh khác biệt giữa filesystem providers. Nếu input root tới directory không tồn tại, phương thức ném `IOException` thay vì âm thầm trả list rỗng.

### 10.7. `src/test/java/dev/lesson/repro/DeterministicAppTest.java`

```java
package dev.lesson.repro;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.util.Map;

import org.junit.jupiter.api.Test;

class DeterministicAppTest {

    @Test
    void rendersStableOrderAndFormatting() {
        String actual = DeterministicApp.render(
                Map.of("gamma", 3, "alpha", 1, "beta", 2),
                "Chào Maven"
        );

        assertEquals(
                "MESSAGE=Chào Maven\n"
                        + "alpha=1\n"
                        + "beta=2\n"
                        + "gamma=3\n"
                        + "PRICE=1234.50\n",
                actual
        );
    }

    @Test
    void readsUtf8ClasspathResource() throws IOException {
        assertEquals("Chào Maven", DeterministicApp.loadGreeting());
    }
}
```

Test cố ý khai `Map.of` theo thứ tự khác với tên alphabet. Nó sẽ phát hiện nếu code bị sửa bỏ `sorted()` trong môi trường có iteration order không trùng expected; tuy vậy một input/order cụ thể không thể chứng minh mọi biến thể JDK, nên vẫn cần cross-environment artifact comparison.

### 10.8. `src/test/java/dev/lesson/repro/FileOrderTest.java`

```java
package dev.lesson.repro;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FileOrderTest {

    @TempDir
    Path tempDir;

    @Test
    void sortsPortableRelativeFileNames() throws IOException {
        Files.writeString(
                tempDir.resolve("z.txt"), "z\n", StandardCharsets.UTF_8);

        Path nested = Files.createDirectory(tempDir.resolve("data"));
        Files.writeString(
                nested.resolve("a.txt"), "a\n", StandardCharsets.UTF_8);

        assertEquals(
                List.of("data/a.txt", "z.txt"),
                FileOrder.relativeFiles(tempDir)
        );
    }
}
```

`@TempDir` tạo directory riêng cho test, không hardcode `/tmp` hoặc `C:\Temp`. Ở cả Linux lẫn Windows, expected strings trong test dùng `/` làm separator logic.

### 10.9. File `.gitattributes` của demo

```gitattributes
*.java text eol=lf
*.xml text eol=lf
*.txt text eol=lf
*.md text eol=lf
*.properties text eol=lf
```

Nếu source được quản lý bởi Git, file này giúp nhất quán text EOL trong checkout. Nó không thay byte của những files đã được sinh ngoài Git, và không giải quyết tất cả metadata như executable flag/symlink.

## 11. Chạy build demo và xem stdout chính xác

Đứng ở project root:

```bash
mvn -version
java -version
mvn -B -ntp clean package
```

Nếu toolchain, dependencies và JUnit tests phù hợp, đầu ra mong đợi:

```text
target/classes/dev/lesson/repro/DeterministicApp.class
target/classes/dev/lesson/repro/FileOrder.class
target/classes/messages/greeting.txt
target/repro-path-demo-1.0.0.jar
target/surefire-reports/
```

Các paths trên là **vị trí outputs dự kiến**, không phải stdout Maven nguyên văn.

Chạy Java executable JAR:

```bash
java -jar target/repro-path-demo-1.0.0.jar
```

**Stdout chính xác của chương trình**:

```text
MESSAGE=Chào Maven
alpha=1
beta=2
gamma=3
PRICE=1234.50
```

JAR Plugin đã đặt `Main-Class`, resources đã được đưa vào JAR. Lệnh trên không cần classpath của JUnit vì test dependency có scope `test`.

### Kiểm tra archive entries

```bash
jar tf target/repro-path-demo-1.0.0.jar
```

Tìm những entries sau, trong danh sách có thể có thêm `META-INF` và Maven metadata:

```text
dev/lesson/repro/DeterministicApp.class
dev/lesson/repro/FileOrder.class
messages/greeting.txt
META-INF/MANIFEST.MF
```

Không đặt kỳ vọng các dòng `jar tf` **phải xuất hiện theo đúng thứ tự liệt kê ở đây**; mục tiêu là xác minh các entries tồn tại, rồi dùng SHA-256 để xác định archive bytes có đồng nhất trong hai build hay không.

## 12. So sánh SHA-256 sau hai lần clean build trong cùng thư mục

Bước đầu đơn giản:

Linux:

```bash
mvn -B -ntp clean package
sha256sum target/repro-path-demo-1.0.0.jar
mvn -B -ntp clean package
sha256sum target/repro-path-demo-1.0.0.jar
```

macOS (nếu không có `sha256sum`):

```bash
mvn -B -ntp clean package
shasum -a 256 target/repro-path-demo-1.0.0.jar
mvn -B -ntp clean package
shasum -a 256 target/repro-path-demo-1.0.0.jar
```

Windows PowerShell:

```powershell
mvn -B -ntp clean package
Get-FileHash -Algorithm SHA256 target\repro-path-demo-1.0.0.jar
mvn -B -ntp clean package
Get-FileHash -Algorithm SHA256 target\repro-path-demo-1.0.0.jar
```

**Kỳ vọng** trong môi trường ổn định: hai hashes của JAR trùng nhau. Không ghi một hash mẫu như thể nó là giá trị bảo đảm, vì các byte thực phụ thuộc vào JDK/Maven/plugin versions và chi tiết checkout.

**Đây mới là phép kiểm lặp trên cùng máy**, chưa bắt được rò rỉ `user.dir` hoặc OS-specific behavior nếu hai lần đều dùng đúng cùng directory.

## 13. So sánh hai build ở hai đường dẫn khác nhau

Để tìm lỗi nhúng **absolute path**, cần build từ **hai project directories khác nhau**.

Ví dụ Linux/macOS với source demo đã được tạo trong current directory:

```bash
SOURCE_DIR="$(pwd)"
mkdir -p /tmp/repro-build-A /tmp/repro-build-B
cp -R "$SOURCE_DIR/pom.xml" "$SOURCE_DIR/src" /tmp/repro-build-A/
cp -R "$SOURCE_DIR/pom.xml" "$SOURCE_DIR/src" /tmp/repro-build-B/

(
  cd /tmp/repro-build-A
  mvn -B -ntp clean package
)

(
  cd /tmp/repro-build-B
  mvn -B -ntp clean package
)

sha256sum /tmp/repro-build-A/target/repro-path-demo-1.0.0.jar
sha256sum /tmp/repro-build-B/target/repro-path-demo-1.0.0.jar
```

Chỉ dùng các thư mục sandbox **được phép tạo hoặc đã xác nhận không có tài liệu của người khác**. Không dùng lệnh này để dọn/ghi đè tùy tiện một `/tmp/repro-build-A` có sẵn quan trọng. Với macOS dùng `shasum -a 256` thay `sha256sum` nếu cần.

Nếu hashes **trùng**, ví dụ đã có bằng chứng không rò rỉ path vào **JAR chính** giữa hai đường dẫn trên cùng môi trường. Nếu hashes **khác**, cần phân tích nơi bị thay, không lập tức kết luận do Maven bug.

### Cách tương đương trên Windows PowerShell

```powershell
$source = (Get-Location).Path
$a = Join-Path $env:TEMP "repro-build-A"
$b = Join-Path $env:TEMP "repro-build-B"
New-Item -ItemType Directory -Force -Path $a, $b | Out-Null

Copy-Item -LiteralPath (Join-Path $source "pom.xml") -Destination $a
Copy-Item -LiteralPath (Join-Path $source "src") -Destination $a -Recurse
Copy-Item -LiteralPath (Join-Path $source "pom.xml") -Destination $b
Copy-Item -LiteralPath (Join-Path $source "src") -Destination $b -Recurse

Push-Location $a
mvn -B -ntp clean package
Pop-Location

Push-Location $b
mvn -B -ntp clean package
Pop-Location

Get-FileHash -Algorithm SHA256 (Join-Path $a "target\repro-path-demo-1.0.0.jar")
Get-FileHash -Algorithm SHA256 (Join-Path $b "target\repro-path-demo-1.0.0.jar")
```

Lệnh PowerShell tạo hai test directories trong hệ thống temp. **Nếu chúng đã có `src`/`target` từ lượt khác**, phải kiểm tra hoặc chọn đường dẫn mới để tránh build artifacts lẫn nhau; ví dụ này không chủ động delete một filesystem path bất kỳ.

Để có một phép kiểm chặt hơn, tạo hai clean checkouts của **cùng Git commit** vào hai workspace riêng, pin cùng toolchain/dependencies và so full output. Việc copy thủ công từ một working tree chưa commit có thể mang theo tệp không được version-control.

## 14. Dùng Maven Artifact Plugin để kiểm tra toàn bộ output phát hành

Tài liệu Maven Reproducible Builds đề xuất:

```bash
mvn -B -ntp clean install
mvn -B -ntp clean verify artifact:compare
```

Trong ví dụ, `maven-artifact-plugin` đã pin `3.7.0` nên tiền tố `artifact:compare` có thể resolve theo plugin khai báo. Lần đầu install tạo reference artifact ở **Maven local repository**. Lần hai rebuild rồi `artifact:compare` đối chiếu output với reference trong phạm vi plugin.

Nếu muốn tường minh plugin/version:

```bash
mvn -B -ntp clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

Với môi trường được thiết kế tốt, `artifact:compare` sẽ xác nhận output match. Goal **mặc định fail build nếu có differences** theo docs 3.7.0. Nó có thể tạo `.buildcompare`/`.buildinfo` reports phục vụ chẩn đoán. Cần kiểm tra report thực tế; không suy rằng mọi tệp ngoài artifact đã được so sánh.

### Kiểm tra plugin build plan

```bash
mvn -B -ntp artifact:check-buildplan
```

Goal này kiểm tra plan có plugins thuộc danh sách đã biết gây vấn đề reproducibility, đưa ra hướng nâng cấp khi cần. **Nó không thay thế phép so hash**: plugin version “được hỗ trợ” vẫn có thể bị app code, locale, encoding hoặc path rò rỉ vào artifact.

### Lưu ý với Maven phiên bản mới

Theo Maven Reproducible Builds Guide hiện hành, từ **Maven 3.10.0** và **4.0.0-beta-5** reproducibility mode được bật mặc định trong một số điều kiện. Bài demo vẫn khai `project.build.outputTimestamp` tường minh để dễ hiểu và không phụ thuộc implicit behavior của Maven version. **Không xem đó là bảo đảm toàn bộ plugins tùy chỉnh tự nhiên đã deterministic.**

### Reference ở local chưa đủ

Hai lần build trong một workspace chung có thể vô tình dùng:

- Cùng username/hostname.
- Cùng absolute path và timezone.
- Cùng local repository cache hoặc generated files.
- Cùng JDK vendor/build và shell.
- Cùng filesystem behavior.

Do đó để khẳng định **independently reproducible**, xây lại từ clean source ở môi trường khác, ghi lại JDK/Maven/plugins/dependency versions và đối chiếu artifacts hash. Một khi hash khác, dùng công cụ diff sâu hơn (chẳng hạn `diffoscope`) để xem file/metadata gây sai lệch.

## 15. Tìm chính xác byte nào thay đổi khi hashes khác nhau

Một trình tự chẩn đoán hiệu quả:

### Bước 1 — xác nhận cùng inputs

- `git rev-parse HEAD` của hai checkouts có cùng commit?
- `git status --porcelain` có tệp chưa commit/thay đổi không?
- `mvn -version` có cùng Maven/JDK?
- Effective POM và active profiles có giống?
- Build command có cùng flags `-D` và environment không?
- Dependencies/plugin versions đã pin chưa? Có dynamic versions/SNAPSHOT bị cập nhật?

### Bước 2 — so hash artifact chính

```bash
sha256sum first.jar second.jar
```

Nếu giống nhau, chưa cần diff binary JAR đó. Nếu khác, tiếp tục.

### Bước 3 — so entries và timestamps

```bash
jar tf first.jar
jar tf second.jar
```

Nếu có `zipinfo`:

```bash
zipinfo -v first.jar
zipinfo -v second.jar
```

Tìm entry khác tên/thứ tự, extra timestamps, compression method, file mode/flags. Đừng chỉ so **tổng dung lượng ZIP**: cùng kích thước chưa chắc cùng bytes.

### Bước 4 — so các tệp bên trong

Giải nén vào **hai thư mục riêng mới** rồi so file names, bytes, EOL và metadata. Không giải nén archive không tin cậy vào root quan trọng do nguy cơ path traversal/symlink. Trong repo chuẩn/CI, có thể dùng `diffoscope first.jar second.jar` để xem hierarchy differences; đây là công cụ bên ngoài Maven và cần cài sẵn.

### Bước 5 — ghép vị trí khác biệt với nguyên nhân

| Khác biệt | Nguồn có thể | Bước kiểm tra |
| --- | --- | --- |
| ZIP entry timestamp khác | Build time/`outputTimestamp` chưa áp dụng | Jar Plugin version, effective timestamp, ZIP headers |
| Same files, khác entry order | Filesystem enumeration/archiver không deterministic | Xem `jar tf`, plugin version, sorting |
| `messages/greeting.txt` khác byte | UTF-8/EOL/BOM/checkout conversion | Hex diff bytes, `.gitattributes` |
| Generated `report.csv` khác thứ tự | HashMap/Files.walk/parallel iteration | Sort deterministic key trước serialize |
| `report.json` dùng `,` thay `.` | Default locale | `Locale.ROOT`/JSON serializer deterministic |
| Text time lệch múi giờ | `ZoneId.systemDefault()` hoặc `now()` | Đưa fixed Instant/UTC input |
| Absolute path xuất hiện trong file | `user.dir`/Build directory leak | Dùng relative root/path normalization |
| `MANIFEST.MF` khác | Attributes/timestamp/user/JDK metadata | Maven Archiver config/version |
| `*.class` khác | JDK/compiler/annotation processor/version | Pin JDK major/vendor và processor |
| `pom.properties` khác | Plugin-generated metadata, EOL | Cập nhật plugin; kiểm tra Maven guide |
| Contents giống nhưng ZIP metadata khác | Permissions/extra fields/archiver | Cập nhật archiver/plugin và normalize |
| Mỗi lần chạy file order đổi | Parallel/chạy tác vụ nondeterministic | Serialize/sort; bỏ racing writes |

**Nguyên tắc:** sửa nguyên nhân ở **nguồn sinh dữ liệu**. Một bước “sửa JAR sau package” có thể che lỗi upstream hoặc phá chữ ký/checksum. Nếu dùng normalization plugin sau build, phải kiểm tra nó xử lý đúng và vẫn giữ khả năng trace source-to-binary.

## 16. Môi trường Java/Maven nào cần khóa phiên bản?

### JDK: `--release 17` không đồng nghĩa compiler binary tuyệt đối giống nhau

`<maven.compiler.release>17</...>` chọn Java API level và classfile target theo compiler. **JDK 17 từ vendor/build khác hoặc JDK 21 compile `--release 17`** có thể tạo .class bytes khác do compiler implementation/optimization/metadata. Kết quả chạy tương đương chưa chứng minh bytecode trùng.

Đối với kiểm chứng nghiêm ngặt, ghi/pin:

- JDK vendor và exact build/distribution khi cần.
- Maven distribution (có thể dùng Maven Wrapper).
- OS/container base image và architecture.
- Maven plugins, annotation processors, compiler options.
- Dependencies (tránh version ranges, mutable SNAPSHOT khi publish release).
- Environment vars ảnh hưởng build: timezone, locale, native tools, timestamps.
- Git checkout behavior, working-directory policy, symlink/permissions.

### Maven Wrapper

Repository có thể commit `mvnw`, `mvnw.cmd` và `.mvn/wrapper/...` để CI/dev sử dụng cùng Maven distribution. Đây là khuyến nghị về project setup; **demo không tạo Maven Wrapper files**, nên chạy `mvn` đã cài.

### Thư viện external và version ranges

Nếu dependency dùng:

```xml
<!-- Phản ví dụ cho reproducible release: dynamic dependency range -->
<version>[1.0,2.0)</version>
```

repository metadata thay đổi có thể làm hai build resolve phiên bản khác. Cần pin explicit versions, kiểm tra dependency tree và BOM/parent versions. Với `-SNAPSHOT`, cùng version string vẫn có thể trỏ artifact có nội dung mới nếu repository cho cập nhật; không nên dùng mutable snapshot dependencies trong release reproducibility tests mà không lock/resolve.

## 17. Locale và timezone trong unit tests: tránh test giả ổn định

Một test viết:

```java
assertEquals("1234.50", String.format("%.2f", 1234.5));
```

có thể pass trên một runner default English và fail trên một runner khác. Điều đó cho thấy implementation đã không khai locale theo contract, chứ không có nghĩa JUnit/Surefire không ổn định.

**Sửa production code** thành `String.format(Locale.ROOT, "%.2f", ...)` nếu output cần machine-readable decimal `.`, và test giá trị kết quả mong đợi. Không nên chỉ force locale trong CI rồi bỏ qua việc code runtime có thể dùng locale khác.

Với test xử lý ngày giờ, inject `Clock` thay vì gọi `Instant.now()` ở nơi sinh metadata deterministic:

```java
java.time.Clock fixed = java.time.Clock.fixed(
        java.time.Instant.parse("2024-01-01T00:00:00Z"),
        java.time.ZoneOffset.UTC);
java.time.Instant at = java.time.Instant.now(fixed);
```

Đoạn này là fragment minh họa Java 17, không phải một test class độc lập. Nó cho thấy cách **tách nguồn thời gian thành input**; trong production real-time feature, bạn vẫn có thể dùng clock thực nhưng build artifact không nên nhúng value hiện tại tùy tiện.

## 18. CI: chuẩn bị phép kiểm tái lập có ý nghĩa

Một pipeline có thể chia làm hai bước kiểm chứng:

```text
Checkout commit/tag cụ thể
        |
        v
Record Maven/JDK/OS/toolchains/dependency versions
        |
        v
Build A: clean package ở workspace A
        |
        v
Store artifact A + SHA-256 + source commit
        |
        v
Build B: clean package ở workspace B / runner khác
        |
        v
Store artifact B + SHA-256
        |
        v
Compare artifact bytes/hashes
        |
        +--> Match: ghi nhận reproducibility evidence
        |
        +--> Mismatch: inspect JAR entries, text files, locale, paths,
                      timestamps, plugin/compiler/environment
```

### Khuyến nghị triển khai

1. Bắt đầu với **cùng môi trường, hai thư mục** để loại lỗi clock/path và file order.
2. Sau đó thay **đường dẫn workspace, locale, timezone** có kiểm soát.
3. Tiếp theo thử **OS/JDK vendor/version** theo matrix mục tiêu; đừng hứa cross-platform identity khi input EOL/native tool chưa được kiểm soát.
4. Lưu SHA-256, artifact GAV, commit SHA, build command, Maven/JDK versions và diff report để debug được.
5. Khi có mismatch, phân loại là **reproducibility gate failure**, không nhất thiết test nghiệp vụ fail.
6. Khi cần public verification, người build độc lập phải nhận đủ source tag, hướng dẫn build và toolchain/policy tương ứng.
7. Nếu release artifact đã được ký, kiểm tra unsigned content phù hợp và xem chữ ký/timestamps cũng là artifact cần chính sách tái lập riêng.

**Đừng xóa biến động bằng cách không so artifacts quan trọng.** Ví dụ bỏ qua toàn bộ `META-INF` có thể làm QA pass giả trong khi manifest thay đổi. Giới hạn so sánh phải được ghi rõ.

## 19. Lỗi và phản ví dụ thường gặp

### 19.1. Dùng `System.lineSeparator()` trong tệp được publish

```java
String body = "a" + System.lineSeparator() + "b";
```

Dòng trên phù hợp với một số giao diện người dùng OS-specific, nhưng không phù hợp nếu contract yêu cầu **LF byte-for-byte**. Với artifact text output, chọn `"a\nb"` hoặc newline policy được quy định.

### 19.2. In default-locale number

```java
String report = String.format("%,.2f", 1234.5);
```

Kết quả có thể là `1,234.50` hoặc `1.234,50` tùy locale. Nếu output là protocol/CSV/JSON, chọn locale/serializer và format cụ thể.

### 19.3. Dùng unordered collection khi serialize

```java
for (String key : map.keySet()) {
    writer.write(key);
}
```

Với `HashMap`, đừng xem traversal order là contract. Sort keys hoặc dùng cấu trúc có comparator/iteration order được quy định.

### 19.4. Đưa absolute path vào generated metadata

```java
String debugInfo = Path.of(".").toAbsolutePath().toString();
```

Có thể hữu ích để log diagnostic, nhưng không nên đưa vào file được publish nếu muốn independent reproducibility. Nếu cần lưu build environment, hãy đưa vào **build attestation riêng**, không nhúng tùy tiện vào JAR chính.

### 19.5. Chỉ đặt `outputTimestamp` rồi tuyên bố mọi thứ tái lập

`project.build.outputTimestamp` giải quyết một thành phần rất quan trọng: timestamps của archive entries trong plugin hỗ trợ. Nó **không sort dữ liệu do Java generator xuất ngẫu nhiên**, không ép mọi tool dùng UTF-8, không khóa JDK/locale và không sửa unstable third-party plugins.

### 19.6. So hashes của hai files có tên giống nhưng khác inputs

`app-1.0.0.jar` từ hai source commits khác nhau có thể khác byte hoàn toàn hợp lý. Trước khi báo lỗi, kiểm tra SHA commit, POM effective, dependencies, build flags và environment. **Tên version artifact không phải chứng cứ cùng source**.

## 20. Hỏi đáp nhanh

**Câu 1:** Hai JAR chạy trả cùng kết quả nhưng SHA-256 khác; có phải chắc chắn có bug nghiệp vụ?

**Trả lời:** Không. Có thể khác timestamps, archive entry order, metadata, encoding/EOL hoặc JDK compiler. Reproducibility khác functional correctness.

**Câu 2:** Có thể tin thứ tự `Files.list` hay `HashMap.keySet` khi generate report không?

**Trả lời:** Không. Sort theo key/relative path đã định nghĩa trước khi ghi output.

**Câu 3:** `project.build.sourceEncoding=UTF-8` có tự đổi mọi resource và stdout thành UTF-8 không?

**Trả lời:** Không. Plugin/Java code phải đọc/ghi với encoding đúng; unfiltered resources giữ byte source, stdout cần xác định charset khi so byte.

**Câu 4:** Vì sao `.gitattributes` quan trọng khi build trên Windows và Linux?

**Trả lời:** Nó giúp Git checkout text EOL có quy ước; CRLF/LF khác bytes dù nhìn như cùng nội dung.

**Câu 5:** Dùng `Locale.ROOT` giúp điều gì?

**Trả lời:** Cố định locale cho các thao tác được truyền nó, như `String.format` và `toLowerCase`; không tự cố định timezone, filesystem hoặc mọi formatting API khác.

**Câu 6:** Đặt `project.build.outputTimestamp` có giải quyết đường dẫn `/home/runner` xuất hiện trong file generated không?

**Trả lời:** Không. Đường dẫn vẫn là input của code generator; cần bỏ hoặc chuyển sang relative/path normalization.

**Câu 7:** Hai lần build cùng đường dẫn và cùng máy có cùng hash. Đã chứng minh độc lập trên máy khác chưa?

**Trả lời:** Chưa. Phải thử clean checkout và môi trường khác để tìm environment leaks.

**Câu 8:** `mvn artifact:check-buildplan` khác `artifact:compare` như thế nào?

**Trả lời:** `check-buildplan` tìm known plugin reproducibility issues; `compare` so output hiện tại với reference. Cả hai bổ trợ chứ không thay thế nhau.

**Câu 9:** Vì sao một project `--release 17` vẫn có thể khác bytecode nếu compile bằng JDK khác nhau?

**Trả lời:** `--release` ràng buộc language/API/classfile target, không khóa compiler implementation/vendor/version và annotation processors.

**Câu 10:** Nếu SHA-256 JAR khác, bước tiếp theo là gì?

**Trả lời:** Kiểm tra cùng source/environment, sau đó liệt kê archive entries, so timestamps/manifest/nội dung và dùng diffoscope để xác định file/byte khác.

**Câu 11:** Cách tạo danh sách path portable?

**Trả lời:** Lấy relative path so với một root cố định, chuẩn hóa separator `/` cho tên logic, rồi sort theo comparator đã quy định.

**Câu 12:** `mvn clean verify` pass đồng nghĩa build tái lập?

**Trả lời:** Không. Build thành công và test pass là quality signals; reproducibility cần so sánh artifacts giữa các lần build độc lập.

## 21. Checklist áp dụng vào dự án thật

- [ ] Xác định rõ artifact nào phải tái lập byte-for-byte: JAR, sources, POM, ZIP, image...
- [ ] Pin Git commit/tag và xác minh source bytes sạch.
- [ ] Pin Maven distribution, JDK vendor/build hoặc mô tả matrix được hỗ trợ.
- [ ] Pin plugin versions, annotation processors và dependencies phù hợp.
- [ ] Không dùng dynamic dependency versions/mutable SNAPSHOT ngoài chính sách.
- [ ] Khai `project.build.sourceEncoding=UTF-8` và cấu hình plugins liên quan.
- [ ] Thiết lập text EOL/BOM policy bằng `.gitattributes` và editor settings.
- [ ] Không filter binary resources như text.
- [ ] Chọn `propertiesEncoding` nếu lọc Java properties có encoding riêng.
- [ ] Đặt `project.build.outputTimestamp` hoặc cơ chế reproducible timestamp được hỗ trợ.
- [ ] Không nhúng `now()`, username, hostname hoặc path tuyệt đối vào published outputs.
- [ ] Sort directory entries, collections và generated maps trước khi ghi nội dung.
- [ ] Sort theo **relative path portable**, không theo absolute path.
- [ ] Chuẩn hóa path separator và tên files theo filesystem constraints.
- [ ] Dùng `Locale.ROOT`/locale cụ thể cho machine-readable formatting.
- [ ] Dùng UTC/fixed time input cho metadata cần deterministic.
- [ ] Dùng explicit UTF-8 khi Java đọc/ghi resource/output.
- [ ] Dùng LF cố định nếu serialized format yêu cầu bytes đồng nhất.
- [ ] Chạy `artifact:check-buildplan` để phát hiện plugin versions có vấn đề đã biết.
- [ ] So SHA-256 JAR sau hai lần `clean package`, rồi thử hai đường dẫn khác nhau.
- [ ] Chạy `artifact:compare` với reference artifact khi phù hợp.
- [ ] Với mismatch, dùng `jar tf`/`zipinfo`/diffoscope để tìm root cause.
- [ ] Chạy rebuild trên runner độc lập nếu cần chứng minh reproducibility thực sự.
- [ ] Lưu source commit, toolchain, build command, environment và hashes như release evidence.
- [ ] Không lấy build reproducibility làm bằng chứng thay thế cho test/security scan.

**Kết luận:** Tính tái lập Maven không chỉ phụ thuộc timestamps trong JAR. **Thứ tự tệp** quyết định thứ tự bytes khi serialize/archive; **encoding và EOL** quyết định bytes của text; **locale/timezone** quyết định cách format; **đường dẫn** và filesystem có thể rò rỉ tên workspace, separator và metadata vào artifact. Cần cố định/chuẩn hóa tất cả các đầu vào có ảnh hưởng, pin toolchain/plugins, và **so artifacts thực tế qua SHA-256 hoặc Maven Artifact Plugin**, chứ không suy ra reproducibility từ `BUILD SUCCESS`.

## Tài liệu tham khảo chính thức

- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven — Reproducible/Verifiable Builds](https://cwiki.apache.org/confluence/spaces/MAVEN/pages/74682318/Reproducible+Verifiable+Builds)
- [Maven JAR Plugin — jar:jar outputTimestamp](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Maven Compiler Plugin — compiler:compile encoding](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Maven Resources Plugin — resources:resources](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html)
- [Maven Resources Plugin — Character Encoding](https://maven.apache.org/plugins/maven-resources-plugin/examples/encoding.html)
- [Maven — Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Maven Artifact Plugin 3.7.0 — artifact:compare](https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html)
- [Maven Artifact Plugin 3.7.0 — artifact:check-buildplan](https://maven.apache.org/plugins/maven-artifact-plugin/check-buildplan-mojo.html)
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Reproducible Builds — SOURCE_DATE_EPOCH](https://reproducible-builds.org/docs/source-date-epoch/)

*Bài thực hành sử dụng Java 17, Maven 3.9.x, Maven JAR Plugin 3.4.2, Resources Plugin 3.5.0, Compiler Plugin 3.13.0, Artifact Plugin 3.7.0 và JUnit Jupiter 5.11.4. Hash SHA-256 cụ thể phụ thuộc binary thật nên không được bịa giá trị cố định. Các ví dụ được thiết kế để học viên tạo và kiểm tra độc lập, không tuyên bố đã chạy build/so hash trong môi trường ngoài.*
