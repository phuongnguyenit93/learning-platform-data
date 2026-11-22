# project.build.outputTimestamp và metadata thời gian trong archive Maven

## 1. Vấn đề: cùng source code nhưng JAR khác checksum

Trong chủ đề **Build tái lập (reproducible builds)** của Maven, một tình huống thường gặp là cùng commit Git, cùng lệnh `mvn clean package`, cùng ứng dụng Java nhưng hai file `.jar` lại có **SHA-256 khác nhau**.

Không phải lúc nào bytecode hay logic cũng thay đổi. JAR là một **ZIP archive**, trong đó mỗi entry có thông tin như tên, nội dung, kích thước, thời gian sửa đổi và các thuộc tính định dạng. Nếu plugin đóng gói lấy **thời điểm hiện tại** làm timestamp cho các entry, hai archive được tạo cách nhau vài phút có thể khác **ở bytes metadata** dù file `App.class` bên trong giống hệt.

Maven cung cấp thuộc tính:

```xml
<project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
```

Những packaging plugins hỗ trợ reproducible archives, như Maven JAR Plugin phiên bản phù hợp, dùng giá trị này để **ổn định timestamp của entries trong archive** thay vì đóng dấu thời điểm build ngẫu nhiên.

Đây là **một phần** của reproducible build, không phải phép màu khiến mọi sản phẩm Java luôn giống nhau. Nếu source, dependencies, compiler, encoding, generated resources hoặc manifest khác nhau, cùng `outputTimestamp` vẫn có thể cho ra JAR khác checksum.

### Mục tiêu của bài

Sau khi học, bạn có thể:

1. Phân biệt **thời gian trên ổ đĩa** của file JAR với **timestamp của từng ZIP/JAR entry** và **chuỗi thời gian nhúng trong nội dung file**.
2. Hiểu chính xác `project.build.outputTimestamp`, các định dạng ISO 8601 và Unix epoch.
3. Cấu hình Maven JAR Plugin để tạo archive ổn định về metadata thời gian.
4. Chạy dự án Java 17 + JUnit 5 có code, resource, test và công cụ kiểm tra ZIP entries.
5. Build lại hai lần rồi so sánh SHA-256/byte-for-byte, không chỉ nhìn `BUILD SUCCESS`.
6. Biết vì sao timestamp cố định là **điều kiện cần nhưng chưa đủ** và cách xử lý các nguồn nondeterminism khác.
7. Thiết kế phép kiểm tra reproducibility cho CI, Maven đa module và quy trình release.

## 2. “Build tái lập” được định nghĩa như thế nào?

Một build được gọi là **reproducible** khi cùng source, cùng điều kiện/toolchain và cùng build instructions có thể tạo ra **artifacts giống nhau từng byte**, cho phép một bên khác độc lập kiểm chứng.

Cần phân biệt ba mức độ:

| Mức độ | Kiểm tra được gì? | Đã chứng minh reproducible chưa? |
| --- | --- | --- |
| **Compile/test pass** | Code hoạt động với môi trường hiện tại | **Chưa** |
| **Hai JAR cùng tên/size** | Filename và kích thước không đổi | **Chưa** |
| **Hai JAR cùng SHA-256** | Hai output files có xác suất áp đảo giống bytes; dùng `cmp` để xác nhận chính xác | Có bằng chứng về **hai lần build đã thử** |
| **Rebuild độc lập trên môi trường khác và bytes trùng** | Reproducibility có thể kiểm chứng độc lập | Bằng chứng mạnh hơn |

**Một SHA-256 bằng nhau trong hai build trên cùng máy chưa chứng minh mọi môi trường đều cho ra bytes giống nhau.** Có thể tồn tại phụ thuộc vào username, đường dẫn workspace, vùng giờ, JDK vendor/version hoặc OS mà phép thử cùng máy không phát hiện.

Reproducibility hữu ích vì giúp:

- Kiểm chứng artifact được phát hành có đúng từ source được công bố.
- Phát hiện tác động của toolchain, cache hoặc generated files không kiểm soát.
- Tăng độ tin cậy của software supply chain và incident investigation.
- So sánh artifacts giữa CI runners hoặc giữa bản do nhà phát triển và bên kiểm định build.
- Tránh binary khác chỉ vì ngày giờ đóng gói.

**Không đồng nhất reproducibility với bảo mật tuyệt đối.** Hai artifacts giống bytes vẫn có thể cùng chứa lỗi hoặc lỗ hổng. Cần testing, dependency/SBOM scanning, provenance và code review bên cạnh phép so sánh.

## 3. Có nhiều loại “timestamp” trong cùng một build

Đây là kiến thức trọng tâm của Menu này. Xem sơ đồ:

```text
source file App.java
  |  filesystem mtime (lúc lưu/checkout)
  v
javac -> target/classes/dev/course/App.class
  |  filesystem mtime của .class (thường là khi compile)
  v
Maven JAR Plugin
  |  đọc project.build.outputTimestamp
  |  đóng gói các ZIP entries:
  |    META-INF/MANIFEST.MF          -> ZIP entry timestamp
  |    dev/course/App.class         -> ZIP entry timestamp
  |    banner.txt                   -> ZIP entry timestamp
  v
target/repro-archive-lab-1.0.0.jar
  |
  +-- filesystem mtime của file JAR trên ổ đĩa
  +-- ZIP entry timestamps bên trong JAR
  +-- manifest/resource contents (có thể chứa text ngày giờ)
```

**Ba lớp cần tách riêng:**

### 3.1. Filesystem modification time (mtime)

Là metadata hệ điều hành cho **file JAR ở ngoài archive** hoặc files dưới `src/` và `target/classes/`. Khi Maven tạo lại JAR, `ls -l`, `stat`, File Explorer hoặc PowerShell có thể cho thấy mtime mới. Điều đó **không chứng minh JAR bytes khác nhau**.

Một build có thể tạo hai file JAR với:
- SHA-256 **giống nhau**.
- Thời điểm file JAR được ghi xuống ổ đĩa **khác nhau**.

Mtime của file bao ngoài **không nhất thiết được lưu bên trong chính nội dung JAR**.

### 3.2. Timestamp của ZIP/JAR entry

JAR là ZIP container. Mỗi entry (tệp hoặc thư mục trong ZIP) có metadata, trong đó có modification timestamp. Maven JAR Plugin hỗ trợ `outputTimestamp` để điều khiển **thời gian của archive entries**.

Ví dụ:

```text
META-INF/
META-INF/MANIFEST.MF
dev/course/App.class
dev/course/Greeting.class
banner.txt
```

Khi thay đổi một byte metadata của entry, **checksum của toàn bộ JAR có thể thay đổi** dù nội dung code không đổi. Đây là lý do hai JAR tạo ở hai thời điểm khác nhau thường khác nhau nếu packaging không chuẩn hóa timestamps.

### 3.3. Ngày giờ nằm ngay trong nội dung

Một resource hoặc manifest có thể chứa text:

```properties
build.time=2026-11-10T09:15:00Z
build.user=builder-123
```

Nếu chúng được generated theo `Instant.now()`, môi trường hoặc ngày hiện tại, **outputTimestamp không tự thay nội dung text này**. Nó chỉ kiểm soát metadata archive đối với những plugins đã hỗ trợ.

Nếu `banner.txt` được resource filtering để chứa ngày giờ mỗi lần chạy, những bytes **bên trong entry** vẫn khác, dù metadata timestamp cố định. Cần sửa generator/filtering hoặc dùng giá trị reproducible từ source/release metadata.

## 4. Cú pháp và ý nghĩa của project.build.outputTimestamp

Maven/packaging plugin hiện đại chấp nhận những dạng timestamp như sau:

### 4.1. ISO 8601 có vùng giờ rõ

```xml
<properties>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

`Z` biểu thị UTC. Có thể dùng ISO 8601 với offset hợp lệ, nhưng UTC giúp giảm nhầm lẫn khi developers ở nhiều vùng giờ.

**Không chọn thời gian của từng lần CI run** nếu mục tiêu là build cùng source tạo bytes giống nhau. Hãy dùng một mốc **ổn định gắn với source/release**.

### 4.2. Số giây Unix epoch

Cùng mốc trên cũng có thể viết:

```xml
<properties>
    <project.build.outputTimestamp>1735689600</project.build.outputTimestamp>
</properties>
```

Giá trị **1735689600** là số **giây** từ `1970-01-01T00:00:00Z` tới `2025-01-01T00:00:00Z`.

**Giây, không phải milliseconds.** Không thay bằng `1735689600000` mà vẫn nghĩ đó là timestamp cùng mốc; số này là milliseconds và không đúng định dạng epoch giây được yêu cầu.

### 4.3. Các định dạng cần tránh

```text
Không nên:
  2025-01-01                (chỉ có ngày, không đủ offset-time)
  01/01/2025                (phụ thuộc locale, không đúng ISO offset)
  now                       (không phải timestamp ổn định)
  1735689600000             (milliseconds thay vì epoch seconds)
  2025-01-01T00:00:00       (không có UTC offset)
```

Maven plugins/Archiver có thể báo lỗi parse khi giá trị không hợp lệ. **Không biến một lỗi parse timestamp thành “0 violations” hay build pass giả**. Sửa cấu hình đúng.

### 4.4. SOURCE_DATE_EPOCH và nguồn timestamp

Dự án Reproducible Builds đề xuất biến môi trường `SOURCE_DATE_EPOCH`, một số nguyên giây Unix UTC gắn với source. Nếu hệ thống CI có mốc ổn định, có thể ánh xạ:

```xml
<properties>
    <project.build.outputTimestamp>${env.SOURCE_DATE_EPOCH}</project.build.outputTimestamp>
</properties>
```

**Điều kiện:** CI phải thiết lập biến này trước khi Maven chạy. Nếu biến vắng mặt hoặc giá trị không phải số nguyên hợp lệ, kết quả phụ thuộc interpolation/plugin và có thể lỗi.

Cách dễ thử nhất trong bài là dùng **timestamp cố định trực tiếp trong POM**. Khi đưa vào production, chọn mốc source commit/release có thể tái lập, không tự lấy `date +%s` của **mỗi build**.

Một số phiên bản Maven Archiver có cơ chế fallback từ `SOURCE_DATE_EPOCH` khi property chưa được cấu hình. Đó là **hành vi theo phiên bản archiver**, không lý do để bỏ kiểm tra effective property và plugin version của dự án.

## 5. Maven core và plugin version: cấu hình theo môi trường

**Maven core không phải thành phần duy nhất quyết định reproducible archive.** Nhiều bước đóng gói diễn ra trong Maven plugins. Theo hướng dẫn chính thức Maven, một project trên Maven 3.9.x có thể bật bằng `project.build.outputTimestamp` và dùng những plugin versions đã hỗ trợ.

Cần lưu ý một thay đổi theo thời gian:

- **Maven 3.9.x:** nên khai báo property tường minh trong POM/parent để rõ mục đích và không phụ thuộc mặc định.
- **Maven 3.10.0 trở lên:** Maven Super POM cung cấp default `project.build.outputTimestamp`, nên chế độ reproducible-build được bật mặc định ở core.
- **Maven 4.0.0-beta-5 trở lên** cũng có mặc định tương ứng theo hướng dẫn Maven.
- **Dù core bật mặc định, plugin lỗi thời hoặc nội dung được sinh không ổn định vẫn làm artifact khác bytes.**

Nói cách khác: **“Maven mới” không đồng nghĩa “mọi artifact luôn tái lập được”**. Maven JAR Plugin, Source Plugin, WAR Plugin, Shade Plugin, Assembly Plugin, Spring Boot Maven Plugin hoặc custom packaging plugins phải được xét riêng theo versions/cấu hình.

Trong ví dụ dưới đây, ghim **maven-jar-plugin:3.4.2**, một bản hỗ trợ tham số `outputTimestamp` (feature xuất hiện từ JAR Plugin 3.2.0).

## 6. Ví dụ runnable: dự án Java 17 tạo JAR có timestamp cố định

Bài thực hành tự chứa đầy đủ POM, Java source, resource, JUnit tests và một công cụ Java kiểm tra entry timestamps.

### 6.1. Cây thư mục

```text
repro-archive-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/dev/course/
│   │   │   ├── Greeting.java
│   │   │   ├── App.java
│   │   │   └── ArchiveInspector.java
│   │   └── resources/
│   │       └── banner.txt
│   └── test/
│       └── java/dev/course/
│           └── GreetingTest.java
└── target/                 (Maven tạo sau build)
```

Điều kiện: JDK **17+**, Maven 3.9.x hoặc Maven mới hơn, khả năng tải plugins/JUnit từ repository (nếu local cache chưa có).

### 6.2. pom.xml hoàn chỉnh

Tạo `repro-archive-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>repro-archive-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
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
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

**Vì sao POM này phù hợp?**

- `project.build.outputTimestamp` được khai báo rõ ràng và cố định.
- Maven JAR Plugin 3.4.2 mặc định đọc `${project.build.outputTimestamp}` cho tham số `outputTimestamp`. **Không cần một execution custom để “bật” lại goal jar**: lifecycle của `packaging=jar` đã gọi `jar:jar`.
- Compiler ghim Java release 17, Resources Plugin 3.3.1 và Surefire/JAR Plugin có versions rõ.
- `project.build.sourceEncoding=UTF-8` tránh lệch decoding với các resource/source Unicode.
- JUnit Jupiter chỉ ở `test` scope; main app không có dependency runtime ngoài JDK.
- POM không tạo executable fat JAR và chưa đặt `Main-Class`; chạy bằng `java -cp target/classes`.
- Có **3 unit tests** để xác nhận logic, độc lập với phép đo reproducibility.

Nếu muốn viết tường minh rằng JAR plugin dùng property, đoạn **tùy chọn** sau nằm trong thẻ plugin `maven-jar-plugin`:

```xml
<configuration>
    <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
</configuration>
```

Với plugin 3.4.2, cấu hình này có cùng ý đồ với mặc định. **Không nhân đôi `maven-jar-plugin` thành hai thẻ riêng trong `<plugins>`** chỉ để thêm `configuration`; hãy bổ sung vào thẻ plugin đã tồn tại.

### 6.3. Greeting.java

Tạo `src/main/java/dev/course/Greeting.java`:

```java
package dev.course;

public final class Greeting {
    private Greeting() {
    }

    public static String say(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên không hợp lệ");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

Lớp này không đọc clock, process environment, filesystem hoặc random state. Cùng input cho cùng output, một thuận lợi khi minh họa build reproducibility.

### 6.4. App.java

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("APP: " + Greeting.say(" Maven "));
    }
}
```

Dòng stdout **chính xác**:

```text
APP: Xin chào, Maven!
```

### 6.5. ArchiveInspector.java — xem thời gian của entries

Tạo `src/main/java/dev/course/ArchiveInspector.java`:

```java
package dev.course;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public final class ArchiveInspector {
    private ArchiveInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ArchiveInspector <path-to-jar>");
        }

        Path jarPath = Path.of(args[0]);

        try (ZipFile zip = new ZipFile(jarPath.toFile())) {
            zip.stream()
                .filter(entry ->
                    entry.getName().equals("META-INF/MANIFEST.MF") ||
                    entry.getName().equals("dev/course/App.class") ||
                    entry.getName().equals("banner.txt"))
                .sorted(Comparator.comparing(ZipEntry::getName))
                .forEach(entry -> {
                    var time = entry.getLastModifiedTime();
                    String printed = time == null
                            ? "(không có time field)"
                            : time.toString();
                    System.out.println(
                            entry.getName() + " => " + printed);
                });
        }
    }
}
```

Ý nghĩa:

- `java.util.zip.ZipFile` đọc **entries bên trong archive** mà không thực thi code trong JAR.
- `ZipEntry.getLastModifiedTime()` trả về metadata modification time của từng entry dưới dạng `FileTime`.
- `getName()` chỉ tên entry; `getLastModifiedTime()` **không phải mtime của file JAR bao ngoài**.
- Code chỉ in ba entries quan trọng theo thứ tự tên để không gây noise.
- Timestamp được JVM giải mã từ ZIP metadata; cách hiển thị bằng một số chương trình bên ngoài có thể sử dụng vùng giờ/local formatting khác. Vì thế **hash của artifact mới là tiêu chí byte-for-byte**.

Không nói chương trình này “kiểm chứng toàn bộ archive reproducible” chỉ vì ba dòng timestamp giống nhau; nó là **công cụ chẩn đoán metadata**, còn các bytes khác phải so sánh riêng.

### 6.6. banner.txt

Tạo `src/main/resources/banner.txt` chứa đúng nội dung sau và kết thúc bằng một newline:

```text
Maven reproducible archive lab
```

Resource bình thường này được Maven Resources Plugin copy vào `target/classes/banner.txt`, rồi đóng vào JAR.

**Không bật resource filtering dùng ngày hiện tại** trong ví dụ; nếu thêm `build.timestamp=...` sinh từ system clock, hash có thể khác dù ZIP entry times đã ổn định.

### 6.7. GreetingTest.java

Tạo `src/test/java/dev/course/GreetingTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTest {
    @Test
    void trimsWhitespace() {
        assertEquals("Xin chào, Maven!",
                Greeting.say(" Maven "));
    }

    @Test
    void rejectsBlank() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeting.say("   "));
    }

    @Test
    void rejectsNull() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeting.say(null));
    }
}
```

Có **3 JUnit Jupiter tests**: chuẩn hóa whitespace, từ chối chuỗi blank, từ chối null. Chúng không viết files hoặc sinh dữ liệu random nên ít thêm biến số ngoài ý muốn cho lab.

## 7. Build lần đầu: xác nhận chức năng và ZIP entries

Đứng ở thư mục `repro-archive-lab`, chạy:

```bash
mvn -version
mvn -B -ntp clean verify
java -cp target/classes dev.course.App
```

Khi JDK/Maven/dependencies hợp lệ, Maven compile Java 17, chạy 3 tests, tạo JAR và báo build success.

Mốc log rút gọn:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là dấu hiệu trong output Maven, **không phải bản chép nguyên văn** của log.

Stdout của ứng dụng:

```text
APP: Xin chào, Maven!
```

JAR được tạo tại:

```text
target/repro-archive-lab-1.0.0.jar
```

Kiểm tra các entry names:

```bash
jar tf target/repro-archive-lab-1.0.0.jar
```

Trong danh sách cần thấy `META-INF/MANIFEST.MF`, `dev/course/Greeting.class`, `dev/course/App.class`, `dev/course/ArchiveInspector.class`, `banner.txt` cùng Maven metadata có thể được sinh thêm.

**Chú ý:** `jar tf` chỉ liệt kê entry names, **không phải** công cụ so sánh entry timestamps. Dùng `jar tvf` hoặc `ArchiveInspector` để kiểm tra thời gian:

```bash
jar tvf target/repro-archive-lab-1.0.0.jar
java -cp target/classes dev.course.ArchiveInspector target/repro-archive-lab-1.0.0.jar
```

Ba entry được inspector in theo thứ tự tên:

```text
META-INF/MANIFEST.MF => <timestamp hiển thị bởi JVM>
banner.txt => <timestamp hiển thị bởi JVM>
dev/course/App.class => <timestamp hiển thị bởi JVM>
```

Các chuỗi `<timestamp hiển thị bởi JVM>` **là chú thích**, không phải stdout literal của chương trình. Người học phải quan sát output thật và xem các timestamps có ổn định qua hai build.

**Đừng nhầm time zone:** `jar tvf` có thể format giá trị ngày giờ theo time zone local. Một entry có cùng instant chuẩn hóa vẫn hiển thị khác giữa hai máy khi xem bằng công cụ khác nhau. Hash mới xác nhận bytes archive.

## 8. Build hai lần: kiểm tra SHA-256 và byte-for-byte

Đây là phép thử quan trọng nhất.

### 8.1. Trên Bash/zsh (Linux/macOS)

Từ `repro-archive-lab`:

```bash
mvn -B -ntp clean package
cp target/repro-archive-lab-1.0.0.jar ../reference.jar
sha256sum ../reference.jar

sleep 3

mvn -B -ntp clean package
sha256sum ../reference.jar target/repro-archive-lab-1.0.0.jar
cmp ../reference.jar target/repro-archive-lab-1.0.0.jar
```

Cách diễn giải:

- Lần build đầu tạo JAR rồi copy ra ngoài `target/` để `clean` không xóa.
- `sleep 3` chỉ làm hai lần build cách nhau về wall-clock time, không ảnh hưởng `outputTimestamp` cố định.
- Lần thứ hai `clean package` tạo JAR mới.
- `sha256sum` liệt kê hai hash. **Nếu cả hai giống nhau**, hai artifacts có cùng hash.
- `cmp` không in gì khi hai files giống nhau và trả exit code 0; nếu khác, nó báo vị trí/khác biệt và trả non-zero.

**Bash/macOS lưu ý:** một số macOS cài `shasum -a 256` thay vì `sha256sum`. Khi đó dùng:

```bash
shasum -a 256 ../reference.jar target/repro-archive-lab-1.0.0.jar
```

Không in ra một hash “dự kiến cố định” trong tài liệu: SHA-256 thực tế phụ thuộc bytes của plugins, bytecode, versions và file contents, phải tính từ artifact vừa build.

### 8.2. Trên Windows PowerShell

Chạy từ `repro-archive-lab`:

```powershell
mvn -B -ntp clean package
Copy-Item target\repro-archive-lab-1.0.0.jar ..\reference.jar

Start-Sleep -Seconds 3

mvn -B -ntp clean package
Get-FileHash ..\reference.jar -Algorithm SHA256
Get-FileHash target\repro-archive-lab-1.0.0.jar -Algorithm SHA256
```

Hai `Hash` trong PowerShell nên giống nhau nếu artifacts tái lập trên môi trường hiện tại. Để so bytes chính xác qua .NET:

```powershell
$first = [System.IO.File]::ReadAllBytes((Resolve-Path ..\reference.jar))
$second = [System.IO.File]::ReadAllBytes((Resolve-Path target\repro-archive-lab-1.0.0.jar))
[System.Linq.Enumerable]::SequenceEqual[byte]($first, $second)
```

Kỳ vọng in `True` khi các files có cùng bytes. Với JAR khổng lồ, cách đọc cả files vào RAM này không tối ưu; SHA-256 đủ hữu ích cho lab, hoặc dùng công cụ diff stream-based phù hợp.

### 8.3. Tại sao cần clean?

Nếu chỉ gọi `mvn package` nhiều lần, JAR plugin hoặc các plugins khác có thể **bỏ qua tạo lại artifact** khi input không đổi. Hai hash giống nhau khi plugin không thật sự chạy lại **không chứng minh timestamp được chuẩn hóa**. Chạy `mvn clean package` khiến `target/` được xóa trước lần build mới, tạo phép thử đáng tin hơn.

Tuy vậy, **clean không tự xóa cache Maven local repository**. Cùng máy có thể dùng cùng dependencies và toolchain. Để kiểm tra độc lập mạnh hơn, chạy trên workspace/container/runner riêng được quản lý rõ.

## 9. Thử nghiệm thay outputTimestamp có chủ đích

Giữ nguyên source, nhưng override property trên Maven CLI để thay chính **archive entry timestamp**.

### 9.1. Thực hiện từ POM gốc với mốc A

```bash
mvn -B -ntp clean package "-Dproject.build.outputTimestamp=2025-01-01T00:00:00Z"
```

Lưu kết quả lại ở vị trí ngoài `target/`:

```bash
cp target/repro-archive-lab-1.0.0.jar ../timestamp-A.jar
```

### 9.2. Build với mốc B

```bash
mvn -B -ntp clean package "-Dproject.build.outputTimestamp=2025-01-02T00:00:00Z"
```

Lưu:

```bash
cp target/repro-archive-lab-1.0.0.jar ../timestamp-B.jar
sha256sum ../timestamp-A.jar ../timestamp-B.jar
```

Nếu không có phần build nào khác ghi đè timestamp policy, **hai ZIP archives thường khác bytes** do timestamps bên trong thay đổi; kiểm tra bằng `jar tvf` hoặc `ArchiveInspector`.

Không thể cam kết chính xác hash hoặc rằng mọi entry luôn có timestamp mới ở mọi plugin/format. Mục tiêu thí nghiệm là làm rõ **một input timestamp có thể ảnh hưởng bytes dù code giống nhau**.

### 9.3. Build lại với mốc A

```bash
mvn -B -ntp clean package "-Dproject.build.outputTimestamp=2025-01-01T00:00:00Z"
sha256sum ../timestamp-A.jar target/repro-archive-lab-1.0.0.jar
```

Kỳ vọng hash quay về giá trị của mốc A khi build còn lại deterministic. **Cần cùng một JDK/compiler/plugin/config**; nếu môi trường khác hoặc source đã sửa, không suy luận lỗi thuộc timestamp.

Bên Windows, PowerShell sử dụng cùng argument string `"-Dproject.build.outputTimestamp=..."` nhưng thay `cp` bằng `Copy-Item` và `sha256sum` bằng `Get-FileHash` như mục trước.

## 10. ZIP metadata: chi tiết mà timestamp property xử lý

Một ZIP entry có thể có:

- Tên entry, ví dụ `dev/course/App.class`.
- Dữ liệu nội dung đã nén.
- Compression method và compressed/uncompressed size.
- CRC của dữ liệu entry.
- Thời gian sửa đổi theo ZIP header.
- Extra fields (có thể chứa metadata thời gian mở rộng).
- External attributes/mode, permission bits.
- Thứ tự entries trong central directory.
- Các trường và metadata riêng của tool đóng gói.

**`project.build.outputTimestamp` chủ yếu nhắm vào timestamp archive entries được plugin hỗ trợ**. Nó không có nghĩa mọi field ZIP đều sẽ giống nhau giữa các tools khác versions.

### 10.1. Giới hạn định dạng ZIP

ZIP truyền thống có các trường thời gian kiểu MS-DOS; chúng có giới hạn về khoảng thời gian và **độ chính xác thường tới 2 giây**, không phải milliseconds chính xác. Một số implementations dùng ZIP extra fields với timestamps mở rộng.

Hệ quả:

- Tránh chọn timestamp quá xa ngoài khoảng thời gian hợp lệ của format/plugin.
- Nếu cần so kết quả giữa các chương trình ZIP khác nhau, xem cả fields mở rộng, timezone interpretation và entry ordering.
- Một giá trị ISO 8601 có giây lẻ có thể được biểu diễn/làm tròn khác giữa các công cụ; khi hướng dẫn cơ bản, chọn mốc UTC rõ ràng có giây chẵn như `2025-01-01T00:00:00Z`.
- Đừng kết luận byte-level reproducibility chỉ dựa vào date string hiển thị trong Explorer/unzip listing.

### 10.2. Directories cũng là ZIP entries

Một JAR có thể chứa entries cho thư mục như `META-INF/` và `dev/course/`. Nếu plugin chỉ cố định timestamps cho files nhưng không chuẩn hóa directory entries, JAR vẫn có nguy cơ khác checksum.

Maven Archiver và những plugins có chế độ reproducible được thiết kế để xử lý archive metadata có liên quan; nhưng khi dùng **custom ZIP tasks hoặc plugins cũ**, cần kiểm tra cả entries directories, manifest và plugin-generated files.

### 10.3. Vì sao chênh lệch vài giây có thể thay checksum?

Một trong các ZIP headers có thể lưu timestamp encoded trong bit fields. Chỉ một byte thay đổi sẽ làm SHA-256 của toàn archive khác, dù CRC và payload contents của từng entry vẫn giống nhau.

Đây là khác biệt giữa:

- **Same program behavior** (console output giống).
- **Same class bytecode** (có thể giống).
- **Same full JAR bytes** (đòi archive metadata và contents đều giống).

Để release có thể xác minh độc lập, phải quan tâm **mức thứ ba**.

## 11. Manifest, pom.properties và metadata do plugin sinh

JAR thường có:

```text
META-INF/
META-INF/MANIFEST.MF
META-INF/maven/dev.course/repro-archive-lab/pom.xml
META-INF/maven/dev.course/repro-archive-lab/pom.properties
dev/course/App.class
dev/course/Greeting.class
dev/course/ArchiveInspector.class
banner.txt
```

Các thành phần có hai lớp thời gian:

1. **ZIP entry timestamp** của chính `META-INF/MANIFEST.MF` hoặc `pom.properties`.
2. **Nội dung text/bytes** của manifest hoặc generated metadata.

`outputTimestamp` có thể giúp ổn định lớp thứ nhất. Nó **không tự xóa các trường** như `Build-Time: 2026-...`, timestamp generated resource, hoặc thông tin compiler/vendor trong manifest nếu plugin khác chèn vào **nội dung**.

### 11.1. Xem manifest

```bash
unzip -p target/repro-archive-lab-1.0.0.jar META-INF/MANIFEST.MF
```

Nếu hệ thống không có `unzip`, có thể dùng JDK:

```bash
jar xf target/repro-archive-lab-1.0.0.jar META-INF/MANIFEST.MF
```

Lệnh `jar xf` giải nén ra working directory hiện tại, có **side effect tạo file META-INF/MANIFEST.MF**. Chỉ chạy trong thư mục lab/trống thích hợp để không ghi đè tệp ngoài ý muốn. Khi chỉ muốn đọc trong CI, ưu tiên tool ZIP read-only hoặc Java JarFile API.

### 11.2. Manifest fields có thể khác giữa JDK versions

Một số phiên bản Maven Archiver có thể ghi các trường như `Build-Jdk-Spec` hoặc `Created-By`. Nếu build với JDK 17 và JDK 21, nội dung manifest hoặc bytecode `.class` có thể khác, dù `maven.compiler.release` được đặt là 17.

**`--release 17` không có nghĩa JDK 21 tạo ra đúng cùng bytes như JDK 17.** Flag này giới hạn API/language target, không cam kết byte-for-byte across compiler versions.

Cách kiểm tra: in `mvn -version` và `java -version` ở cả hai môi trường, so manifest contents và class bytes trước khi quy mọi chênh lệch cho ZIP timestamps.

### 11.3. Maven metadata không phải build timestamp

Maven repository `maven-metadata.xml` là metadata của repository versioning/snapshots. Nó không đồng nhất với `META-INF/MANIFEST.MF` trong JAR và không tự được cố định chỉ bởi `project.build.outputTimestamp`.

Nếu repo xuất bản timestamped snapshots, **timestamp/build number trong repository filename/metadata** có thể thay đổi theo lần deploy dù bên trong JAR được đóng gói reproducibly. Phân biệt:

- **Artifact payload bytes** (JAR ZIP).
- **Repository object key/filename/version metadata**.
- **Thời điểm server nhận upload**.
- **Filesystem mtime của downloaded file**.

Một release artifact reproducible không đòi repository server phải ghi cùng upload time ở mọi lần thử.

## 12. Những nguồn không tái lập mà outputTimestamp không sửa

Một số nguyên nhân rất phổ biến:

| Nguồn thay đổi | Ví dụ | Cách kiểm tra/giảm thiểu |
| --- | --- | --- |
| **Nội dung generated code** | Tạo class có `Instant.now()` mỗi build | Thay bằng stable version/SCM revision |
| **Resource filtering** | `build.time=${maven.build.timestamp}` | Bỏ thời gian hiện tại; dùng source date ổn định |
| **JDK/compiler khác** | JDK 17 vs JDK 21, vendor/version khác | Ghim JDK/toolchain, so class/manifest |
| **Maven plugin version khác** | Jar 3.x vs bản cũ | Ghim versions, audit buildplan |
| **Dependency range/SNAPSHOT** | Thư viện được cập nhật giữa builds | Dùng fixed released versions; quản lý checksum |
| **OS newline** | CRLF trên Windows vs LF trên Unix | Cấu hình encoding/line endings, .gitattributes |
| **Locale/timezone** | Generator format ngày theo locale mặc định | Dùng UTC/Locale.ROOT khi sinh nội dung |
| **Filesystem paths** | Embed `/home/user/project` vào generated source | Dùng relative paths hoặc bỏ absolute path |
| **Username/hostname** | Manifest `Built-By: alice` | Loại bỏ hoặc chuẩn hóa field |
| **Random IDs** | Sinh UUID trong source/resources | Dùng stable, deterministic identifiers |
| **Archive entry ordering** | Iteration HashMap/Set nondeterministic | Plugin chuẩn hóa ordering hoặc sort inputs |
| **Permissions/external attrs** | ZIP entry mode khác trên Windows/Linux | Dùng plugin hỗ trợ metadata ổn định |
| **Nén/ZIP implementation** | Khác compression library/level | Ghim plugin+archiver implementations |
| **Generated source timestamps** | Annotation processor ghi giờ hiện tại | Cấu hình processor hoặc patch generator |
| **SCM checkout semantics** | Dirty working tree/untracked files khác nhau | Build từ clean commit/tag với exclusions |
| **Multi-module outputs** | Module A bị build từ cache khác nội dung | Build reactor đồng nhất, version đồng bộ |
| **Profile/environment** | `-Pprod` vs `-Pdev` | Ghim profiles, CLI args, env |
| **Secrets injection** | Copy token/key vào resources | Không đóng secrets vào binary; dùng runtime secret store |
| **Native binaries** | JNI/graal/native compiler sinh metadata | Kiểm tra riêng toolchain native |
| **Source/javadoc artifacts** | Sources JAR vẫn dùng timestamp hiện tại | Upgrade source/javadoc/assembly plugins hỗ trợ outputTimestamp |

Điểm quan trọng: **cùng source theo tên commit chưa đủ nếu build dependencies/plugin binaries được resolve khác nhau**. Một dependency version range hoặc SNAPSHOT có thể thay đổi nội dung mà POM vẫn không đổi.

Theo hướng dẫn Maven, chạy `artifact:check-buildplan` để rà build plugins với danh sách vấn đề reproducibility đã biết. Đây là một bước audit, **không chứng minh artifact bytes giống**.

## 13. Source JAR, Javadoc JAR, WAR, EAR, Shade và Spring Boot

Bài lab tạo **ordinary JAR**, nhưng trong dự án thật còn có nhiều archive types.

### 13.1. Source JAR

Maven Source Plugin hỗ trợ tham số `outputTimestamp` và lấy mặc định từ `project.build.outputTimestamp` trong những versions phù hợp. Khi project attach `-sources.jar`, nó cũng là ZIP archive và cần timestamp entries ổn định.

Snippet plugin (đặt trong `<build><plugins>`, đây **không phải POM độc lập**):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <phase>package</phase>
            <goals>
                <goal>jar-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Kiểm tra riêng hashes của `target/repro-archive-lab-1.0.0-sources.jar` nếu thêm snippet. **Một main JAR tái lập được không chứng minh sources JAR cũng tái lập**.

### 13.2. Javadoc JAR

Javadoc tools có thể tạo HTML với metadata/format phụ thuộc JDK và các option. Packaging Javadoc JAR vẫn cần chuẩn hóa archive timestamps, đồng thời **nội dung HTML phải deterministic**. Ghim JDK và Maven Javadoc Plugin versions, kiểm tra các option liên quan timestamp trong toolchain thực dùng.

### 13.3. WAR, EAR, Assembly ZIP và shaded/fat JAR

Các plugins này có thể đóng nhiều files, phụ thuộc third-party archives và tạo resource/manifest/index đặc biệt. Cần xác định:
- Plugin version hỗ trợ reproducible output.
- Nó dùng `project.build.outputTimestamp` trực tiếp hay qua cấu hình riêng.
- Thứ tự entries có ổn định không.
- Có nhúng thông tin build time hoặc filesystem metadata hay không.
- Có unpack/repack dependencies với timestamps riêng không.
- Main archive và các attached artifacts có khớp giữa hai builds không.

**Đừng áp dụng một cách máy móc Maven JAR Plugin config sang Spring Boot `repackage` hoặc Shade Plugin rồi mặc định chắc chắn hiệu quả**. Mỗi plugin có parameters/version policy riêng; xem tài liệu plugin tương ứng.

### 13.4. Maven Release Plugin và timestamp

Theo hướng dẫn Reproducible Builds chính thức, Maven Release Plugin bản hỗ trợ từ **3.0.0-M1** có thể **tự cập nhật `project.build.outputTimestamp` trong release commit** cùng lúc chuyển version.

Vì vậy có một chiến lược:
- SNAPSHOT build dùng timestamp theo policy của nhánh/source.
- Khi chuẩn bị release, release plugin cập nhật một timestamp ổn định vào POM của commit được tag.
- Bên kiểm chứng checkout **chính tag** và dùng timestamp trong POM, không lấy thời điểm rebuild thực tế.

Đây là cơ chế **chốt mốc cố định tại release source**, không phải cập nhật timestamp liên tục mỗi lần CI chạy. Nếu dùng release tooling tùy chỉnh, phải thiết kế phần cập nhật property tương đương hoặc dùng mốc source commit ổn định.

## 14. Dùng Maven Artifact Plugin để so sánh artifacts

Kiểm tra SHA-256 thủ công hữu ích, nhưng Maven cũng có goal dành riêng cho reproducible builds.

### 14.1. Kiểm tra plugin buildplan

```bash
mvn org.apache.maven.plugins:maven-artifact-plugin:3.7.0:check-buildplan
```

Goal này phân tích buildplan để phát hiện plugins/versions có vấn đề reproducible builds đã biết. Nó là **static check của cấu hình build**, không phải phép so sánh hai file JAR vừa build.

### 14.2. So artifact hiện tại với bản đã install

Từ dự án lab:

```bash
mvn -B -ntp clean install
mvn -B -ntp clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

Ý nghĩa:

1. `clean install` tạo artifact và cài vào local repository làm reference.
2. Lần thứ hai `clean verify` build output mới từ cùng source.
3. `artifact:compare` so output với reference đã install (hoặc repository tham chiếu theo cấu hình), tạo summary/diagnostics.

**Lưu ý:** so với một artifact đã cài trong cùng local repository là phép thử **tại chỗ**, chưa phải independent rebuild bởi một bên thứ ba. Maven Artifact Plugin có parameters như `referenceRepo` hoặc `-Dreference.repo=...` để so với repository tham chiếu phù hợp.

Có thể chạy:

```bash
mvn -B -ntp clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare -Dreference.repo=central
```

chỉ khi **GAV đó thực sự tồn tại trên Central**; project lab `dev.course:repro-archive-lab:1.0.0` không được publish nên sẽ không tìm được reference. Đừng dùng Central làm reference cho artifact chưa hề được upload.

### 14.3. Khi checksum không khớp

Các bước điều tra có hệ thống:

1. Kiểm tra file reference và file hiện tại có **cùng GAV và đúng bytes phiên bản**.
2. Chạy `mvn -version`/`java -version`, so JDK/Maven/plugins, OS và profiles.
3. Dùng `jar tf` để so entry names/order.
4. Dùng `jar tvf` hoặc `ArchiveInspector` để xem entry timestamps.
5. So `META-INF/MANIFEST.MF` và `pom.properties`.
6. Extract hai JAR vào **hai thư mục trống riêng**, so các entry payload contents và file lists.
7. Nếu còn khác, dùng `diffoscope` hay công cụ binary/archive diff tương đương để tìm byte-level differences.
8. Xác định **plugin/generator nào tạo file khác**; sửa tại nguồn, rồi chạy lại hai fresh builds.

Ví dụ với diffoscope đã cài:

```bash
diffoscope ../reference.jar target/repro-archive-lab-1.0.0.jar
```

Công cụ này không phải Maven plugin bắt buộc; nó chỉ giúp xem sự khác biệt. Không cần install diffoscope để hoàn thành ví dụ SHA-256 cơ bản.

## 15. So sánh metadata thời gian và nội dung thực

Để tránh suy luận sai, xem một số tình huống:

| Tình huống | ZIP entry timestamp | File payload content | SHA-256 JAR |
| --- | --- | --- | --- |
| Cùng source, cùng outputTimestamp, cùng toolchain | Dự kiến giống | Dự kiến giống | **Có thể giống**, cần đo |
| Cùng source, khác outputTimestamp | Có thể khác | Có thể giống | Thường khác |
| Cùng outputTimestamp, generated resource dùng `Instant.now()` | Có thể giống | Khác | Khác |
| Cùng outputTimestamp, JDK compiler major khác | Có thể giống | Bytecode/manifest có thể khác | Có thể khác |
| Cùng ZIP bytes, file JAR trên filesystem có mtime khác | Giống | Giống | **Giống** |
| Same file size và filenames, timestamps khác | Khác | Có thể giống | Khác |
| Hai JAR cùng SHA-256 nhưng `ls -l` cho mtime khác | Giống | Giống | Giống |

**Không dùng file size hay Maven `BUILD SUCCESS` thay cho SHA-256/byte comparison.** Ngay cả khi timestamps hiển thị giống, differences ở manifest, file order hoặc class bytes vẫn có thể làm checksum khác.

## 16. CI/CD: kiểm tra reproducibility một cách có bằng chứng

Một CI gate đơn giản có thể build hai lần cùng checkout và so hash, nhưng phải bảo đảm **cả hai lần thực sự tạo artifacts mới**.

Luồng đề xuất:

```text
checkout commit/tag cố định
          |
          +-- verify JDK, Maven, plugins, sources, dependencies
          |
          +-- Build A: mvn clean package
          |      save JAR A outside target
          |
          +-- Build B: mvn clean package
          |      save JAR B
          |
          +-- compare SHA-256 and/or byte-for-byte
          |
          +-- match -> evidence for this CI environment
          |
          +-- mismatch -> inspect archive metadata and contents
```

Ví dụ Bash dùng trên một CI runner (học thuật, chạy trong repo dự án này):

```bash
set -eu

mvn -B -ntp clean verify
cp target/repro-archive-lab-1.0.0.jar ../ci-reference.jar

mvn -B -ntp clean verify
cmp ../ci-reference.jar target/repro-archive-lab-1.0.0.jar

sha256sum ../ci-reference.jar target/repro-archive-lab-1.0.0.jar
```

Như vậy, nếu bytes khác, `cmp` trả non-zero, `set -e` khiến shell step thất bại. Đừng thêm `|| true` để che mismatch khi yêu cầu kiểm tra bắt buộc.

### 16.1. Kịch bản mạnh hơn: hai environments độc lập

Để chứng minh external reproducibility:

- Checkout cùng source commit/tag vào **hai thư mục/workspaces riêng**.
- Dùng Maven Wrapper hoặc version Maven được kiểm soát, JDK toolchain được kiểm soát.
- Dùng dependency versions cố định, tránh mutable SNAPSHOT và version ranges.
- Có thể dùng isolated Maven local repos để giảm nguy cơ artifact cũ.
- Thiết lập locale/timezone/line endings theo policy và ghi lại environment info.
- Build trên runners/containers độc lập.
- So hashes của **tất cả các deliverable artifacts** (JAR, sources JAR, WAR, attached artifacts), không chỉ một file.
- Phân tích mismatches và cập nhật policy/tooling.

**Một container không mặc nhiên biến build thành reproducible**. Container còn phụ thuộc image digest, build tools, downloaded dependencies và input files. Ghim image theo digest và cung cấp artifact checksums/provenance giúp giảm bất định.

### 16.2. Không dùng wall-clock timestamp làm mốc release

Một chiến lược tệ:

```xml
<project.build.outputTimestamp>${maven.build.timestamp}</project.build.outputTimestamp>
```

nếu `maven.build.timestamp` được tính từ **thời điểm chạy Maven mới**. Cùng source mà timestamp mới mỗi lần build sẽ phá mục tiêu.

Chiến lược tốt hơn:
- Giá trị cố định trong tagged release POM.
- Commit timestamp ổn định từ SCM (đúng commit đang build), được chuẩn hóa UTC.
- `SOURCE_DATE_EPOCH` do CI cấp từ source/release metadata ổn định.
- Có cơ chế release chính thức cập nhật POM timestamp **một lần khi chốt source**, không mỗi lần rebuild.

## 17. Câu hỏi thường gặp

**Q1. Có phải outputTimestamp đổi thời gian file JAR trong File Explorer?**

Không. Nó chủ yếu điều khiển timestamps của ZIP entries mà packaging plugin hỗ trợ. Filesystem mtime của JAR bao ngoài có thể là thời gian lần build cuối.

**Q2. Cùng outputTimestamp là chắc chắn SHA-256 giống nhau?**

Không. File contents, manifest, plugin versions, JDK, paths, locale, source archive và entry ordering đều có thể khác.

**Q3. Tại sao `jar tf` không cho thấy timestamp?**

Vì `jar tf` liệt kê tên files/entries. Dùng `jar tvf`, `ArchiveInspector` hoặc ZIP inspector phù hợp để xem metadata thời gian.

**Q4. Tại sao cần mốc UTC?**

Vì tránh diễn giải offset nhập nhằng. Các công cụ có thể hiển thị local timezone dù cùng instant, nên so bytes/hashes vẫn quan trọng hơn hình thức ngày giờ.

**Q5. ISO 8601 và Unix epoch seconds có thể thay thế nhau không?**

Có, nếu đại diện cùng instant và plugin version hỗ trợ. Ví dụ `2025-01-01T00:00:00Z` bằng `1735689600` giây. Không dùng milliseconds.

**Q6. Nếu dùng Maven 3.10.0 còn cần khai báo property trong POM?**

Core 3.10.0 cung cấp default reproducible outputTimestamp; vẫn có thể khai báo tường minh nếu muốn **mốc cố định theo source/release** hoặc để tương thích với môi trường Maven 3.9.x. Kiểm tra effective POM và plugin versions.

**Q7. Có phải Maven Jar Plugin 3.4.2 đã hỗ trợ outputTimestamp?**

Có. Tham số `outputTimestamp` được JAR Plugin hỗ trợ từ 3.2.0, mặc định sử dụng `${project.build.outputTimestamp}`.

**Q8. Vì sao build cùng source trên Windows và Linux khác?**

Nguồn khác thường là line endings, paths, file permissions, toolchain/environment. Timestamp cố định không thay thế việc chuẩn hóa các yếu tố này.

**Q9. Có cần xóa ~/.m2/repository trước mỗi lần kiểm thử không?**

Không nhất thiết, và không nên làm mù. Trước hết chạy `clean` để rebuild output; khi nghi cache/dependency mismatch, dùng isolated local repo có kiểm soát.

**Q10. Tại sao archive entry date giống mà JAR bytes vẫn khác?**

Vì nhiều trường khác ngoài date: manifest content, bytecode, ordering, compressed data, generated resources, file attrs.

**Q11. Filetime do Java Inspector in có luôn trùng chuỗi ISO trong POM không?**

Không nên khẳng định tuyệt đối trên mọi ZIP encoder/JVM/timezone toolchain. Nó cho biết metadata được Java giải mã; hash check mới xác nhận bit-for-bit output.

**Q12. Nếu release Maven có timestamp tự động thì có tái lập được không?**

Nếu timestamp được chốt vào **release tag POM** một lần, rebuild từ đúng tag có thể dùng lại mốc đó. Nếu timestamp thay theo **mỗi lần Maven chạy**, thì không đạt mục tiêu.

## 18. Bài tập

1. Vẽ sơ đồ ba lớp thời gian: source/output filesystem mtime, ZIP entry timestamp, text timestamp trong manifest/resource.
2. Tạo POM/Java source/resource/tests đầy đủ trong bài, chạy `mvn clean verify`.
3. Chạy `java -cp target/classes dev.course.App` và xác nhận stdout chính xác.
4. Xem nội dung `META-INF/MANIFEST.MF` và `banner.txt`; giải thích ZIP metadata khác file contents.
5. Dùng `jar tf` và `jar tvf`; chỉ ra vì sao hai lệnh thể hiện thông tin khác nhau.
6. Chạy `ArchiveInspector`, ghi lại timestamps của ba ZIP entries.
7. Rebuild bằng `mvn clean package` sau vài giây; so SHA-256 và bytes với JAR đã copy.
8. Dùng epoch seconds `1735689600` thay ISO; vì sao cùng instant được mô tả?
9. Override timestamp thành `2025-01-02T00:00:00Z`; quan sát entry timestamps và SHA-256.
10. Override quay lại `2025-01-01T00:00:00Z`; so với reference A.
11. Vì sao `mvn package` lần thứ hai không `clean` có thể gây false confidence khi JAR Plugin skip rebuild?
12. Đổi nguồn `Greeting.java` để in thông báo khác nhưng giữ timestamp; checksum có còn giống không?
13. Nếu một resource chứa `Instant.now()` được sinh lúc build, timestamp property có tự sửa bytes đó không?
14. JDK 17 và JDK 21 cùng `--release 17` có chắc tạo bytecode/manifest giống nhau không?
15. Vì sao source JAR và Javadoc JAR cần kiểm tra reproducibility riêng?
16. Dùng Maven Artifact Plugin `check-buildplan` và giải thích nó kiểm tra gì, không kiểm tra gì.
17. Dùng `artifact:compare` với reference đã install; vì sao đây chưa phải independent rebuild?
18. Viết một CI step với `cmp` fail build khi artifacts khác nhau.
19. Tại sao metadata timestamps của repository snapshot khác metadata bên trong JAR?
20. Khi Maven 3.10+ mặc định đặt outputTimestamp, những nguyên nhân nào vẫn có thể làm artifacts không tái lập?

## 19. Checklist trước khi tuyên bố archive reproducible

- [ ] Source commit/tag xác định rõ và working tree sạch.
- [ ] `project.build.outputTimestamp` là ISO offset-time hoặc epoch **giây** ổn định.
- [ ] Giá trị timestamp không lấy `Instant.now()` tại mỗi build.
- [ ] Maven version và JDK/toolchain được kiểm soát.
- [ ] Maven build plugins ghim versions; JAR Plugin đủ mới hỗ trợ outputTimestamp.
- [ ] Resource/source encoding và line endings được chuẩn hóa.
- [ ] Không nhúng username, local paths, random IDs hoặc dynamic build time vào bytecode/resources/manifest.
- [ ] Không dùng dependency version ranges/mutable snapshots không kiểm soát.
- [ ] JAR entries gồm files/directories/manifest có timestamps ổn định.
- [ ] Đã dùng `mvn clean package` thực sự build mới **hai lần**.
- [ ] SHA-256 hai artifacts đã tính; kiểm tra bytes khi cần.
- [ ] Không đánh đồng filesystem mtime với archive entry timestamps.
- [ ] Đã xem ZIP entry names/order và payload nếu checksum không khớp.
- [ ] Main JAR và attached artifacts (sources/javadoc/war/zip) đã được kiểm tra riêng.
- [ ] Nếu muốn reproducibility độc lập, đã thử rebuild khác workspace/toolchain với policy rõ.
- [ ] Kết quả compare, tool versions và artifact checksums được ghi nhận để audit.

## 20. Tổng kết

**`project.build.outputTimestamp` là một input có thể cố định metadata thời gian của các file/directory entries trong archive do Maven plugins hỗ trợ tạo ra.** Nó không đổi trực tiếp thời gian file JAR được ghi ra ổ đĩa, không tự thay các chuỗi ngày giờ được nhúng trong manifest/resources và không đảm bảo mọi plugin/toolchain deterministic.

Với Maven JAR Plugin 3.4.2, cấu hình:

```xml
<project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
```

giúp bình ổn timestamps của ZIP entries trong JAR. Ví dụ Java 17 có **3 unit tests**, chương trình in **`APP: Xin chào, Maven!`**, một resource file và `ArchiveInspector` để xem thời gian archive entries. Build hai lần với `clean` và đối chiếu SHA-256/bytes mới là phép xác minh thực chất.

Tư duy cần nhớ:

> **Build reproducible = đầu vào/source/toolchain được kiểm soát + công cụ đóng gói tạo metadata ổn định + kiểm chứng artifacts giống từng byte.** Cố định outputTimestamp chỉ giải quyết một trong nhiều nguyên nhân gây sai khác.

## 21. Tài liệu tham khảo chính thức

- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven JAR Plugin — jar:jar parameters, outputTimestamp](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Apache Maven — Maven 3.10.0 Release Notes](https://maven.apache.org/docs/3.10.0/release-notes.html)
- [Apache Maven Artifact Plugin — artifact:compare](https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html)
- [Apache Maven Artifact Plugin — Plugin Goals](https://maven.apache.org/plugins/maven-artifact-plugin/plugin-info.html)
- [Apache Maven Source Plugin — source:jar-no-fork](https://maven.apache.org/plugins/maven-source-plugin/jar-no-fork-mojo.html)
- [Apache Maven — Configuring Build Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Reproducible Builds — SOURCE_DATE_EPOCH specification](https://reproducible-builds.org/specs/source-date-epoch/)
- [Reproducible Builds — Timestamps](https://reproducible-builds.org/docs/timestamps/)
