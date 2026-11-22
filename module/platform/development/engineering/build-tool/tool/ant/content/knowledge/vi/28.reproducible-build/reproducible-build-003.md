# Cố định encoding, locale, múi giờ và xuống dòng trong Apache Ant

## 1. Vì sao bốn yếu tố này quyết định tính tái lập?

Một build được gọi là **tái lập (reproducible)** khi cùng một đầu vào, cùng bộ công cụ và cùng cấu hình tạo ra đầu ra giống nhau, bất kể ai chạy hay chạy ở máy nào. Với Apache Ant, kết quả không chỉ phụ thuộc vào nội dung `build.xml`. Những mặc định lấy từ hệ điều hành và JVM cũng có thể tác động trực tiếp đến byte của file được biên dịch, sao chép hoặc sinh ra.

Ví dụ, hai lập trình viên có cùng mã nguồn nhưng:

- Một máy đọc file theo UTF-8, máy khác dùng encoding mặc định khác: ký tự tiếng Việt có thể bị sai hoặc quá trình biên dịch thất bại.
- Một JVM dùng locale `vi-VN`, JVM khác dùng `en-US`: số `12345.67` có thể được biểu diễn thành `12.345,67` hoặc `12,345.67`.
- Một máy dùng múi giờ `Asia/Ho_Chi_Minh`, máy khác dùng `UTC`: cùng một thời điểm được ghi thành giờ hiển thị khác nhau.
- Một môi trường ghi xuống dòng LF (`\n`), môi trường khác ghi CRLF (`\r\n`): nội dung nhìn giống nhau trong trình soạn thảo nhưng hash của file khác nhau.

| Yếu tố | Mặc định dễ gây khác biệt | Quy ước nên công bố |
|---|---|---|
| Encoding | Charset của trình biên dịch, API đọc/ghi file hoặc công cụ xử lý text | UTF-8 và charset được truyền tường minh tại từng điểm xử lý |
| Locale | Ngôn ngữ, quốc gia hoặc quy tắc định dạng theo máy chạy | Locale cụ thể, ví dụ `vi-VN`; dùng `Locale.ROOT` cho dữ liệu máy đọc |
| Múi giờ | Múi giờ mặc định của JVM/hệ điều hành | UTC cho dữ liệu thời gian và build; múi giờ nghiệp vụ phải được khai báo rõ |
| Xuống dòng | LF trên nhiều môi trường Unix, CRLF trên Windows | LF cho text được phát hành, trừ file có yêu cầu nền tảng riêng |

**Cố định bốn yếu tố trên là điều kiện quan trọng, nhưng chưa đủ để khẳng định toàn bộ JAR/ZIP có byte giống nhau.** Phiên bản JDK, phiên bản Ant, dependency, thứ tự đóng gói, timestamp của entry và dữ liệu biến đổi theo thời gian cũng phải được kiểm soát. Bài này tập trung vào nguồn sai khác đến từ text, định dạng và thời gian.

## 2. Phân biệt ba môi trường thực thi trong Ant

Trước khi cấu hình, cần xác định thao tác được chạy ở đâu:

1. **JVM chạy Ant** thực thi các task như `loadfile`, `copy`, `tstamp` và nhiều tác vụ tiện ích. Mặc định của JVM này đến từ môi trường khởi động Ant.
2. **Trình biên dịch Java** được gọi bởi `<javac>`. Tùy cấu hình, compiler có thể chạy trong JVM của Ant hoặc được fork ra một tiến trình khác. Thuộc tính `encoding` của `<javac>` áp dụng trực tiếp cho cách đọc mã nguồn.
3. **Ứng dụng hoặc test được Ant chạy** qua `<java>`, `<junit>` hay `<exec>`. Khi `fork="true"`, tiến trình con có môi trường riêng; nên truyền các lựa chọn JVM hoặc tham số tương ứng vào chính tiến trình đó.

Hai loại cú pháp dễ bị nhầm:

- `ant -Dbuild.timezone=UTC` đặt **Ant property** tên `build.timezone`; bản thân lệnh này không đổi múi giờ mặc định của mọi JVM.
- `-Duser.timezone=UTC` là **JVM system property**. Nó chỉ có tác dụng đối với JVM thực sự nhận tùy chọn đó, chẳng hạn khi được truyền qua `<jvmarg>` của một task `<java fork="true">`.

Các `<property>` của Ant thường được thiết lập một lần và không bị `<property>` sau đó ghi đè. Tuy nhiên, giá trị truyền trên dòng lệnh bằng `-D...` có thể ưu tiên hơn mặc định trong `build.xml`. Muốn so sánh hai lần build, phải dùng cùng bộ property đầu vào.

## 3. Cố định encoding: UTF-8 ở cả đầu vào và đầu ra

### 3.1. Khai báo encoding cho mã nguồn Java

Với Ant, cách trực tiếp là đặt `encoding` trên task `<javac>`:

```xml
<property name="text.encoding" value="UTF-8"/>

<javac srcdir="src/main/java"
       destdir="build/classes"
       encoding="${text.encoding}"
       release="17"
       includeantruntime="false"/>
```

Ở đây:

- `encoding="UTF-8"` yêu cầu compiler đọc file `.java` theo UTF-8, kể cả khi máy chạy có mặc định khác.
- `release="17"` minh họa cách khóa API/bytecode mục tiêu ở Java 17, với JDK hỗ trợ tùy chọn đó.
- `includeantruntime="false"` ngăn các thư viện thuộc runtime của Ant tự động chen vào classpath biên dịch. Đây là một nguồn khác có thể gây khác biệt giữa các máy.

Khai báo `<?xml version="1.0" encoding="UTF-8"?>` ở đầu `build.xml` cũng là thói quen tốt, nhưng **encoding của file XML không thay thế `encoding` của `<javac>`**. Hai thiết lập giải quyết hai điểm đọc dữ liệu riêng biệt.

### 3.2. Đọc và ghi file text phải truyền charset

Với Java, ưu tiên những API nhận charset rõ ràng:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("input.txt");
String content = Files.readString(source, StandardCharsets.UTF_8);

Path target = Path.of("output.txt");
Files.writeString(target, content, StandardCharsets.UTF_8);
```

Tránh các API phụ thuộc charset mặc định khi kết quả byte là một phần của artifact, ví dụ khởi tạo `InputStreamReader` hoặc `OutputStreamWriter` mà không truyền `Charset`. Từ Java 18, UTF-8 là charset mặc định trong đa số tình huống theo JEP 400; dù vậy, truyền tường minh `StandardCharsets.UTF_8` giúp hợp đồng của chương trình rõ ràng và ít phụ thuộc môi trường hơn.

Với dữ liệu nạp bằng Ant, có thể đặt encoding cho `<loadfile>`:

```xml
<loadfile property="readme.text"
          srcFile="src/main/resources/intro.txt"
          encoding="UTF-8"/>
```

Nếu thực hiện **sao chép có lọc hoặc chuyển đổi nội dung text** bằng `<copy>`, cần quan tâm cả encoding đầu vào và đầu ra:

```xml
<copy todir="build/resources"
      filtering="true"
      encoding="UTF-8"
      outputencoding="UTF-8">
    <fileset dir="src/main/resources" includes="**/*.txt"/>
</copy>
```

Chỉ dùng cách xử lý text cho tài nguyên text thực sự. Ảnh, font, JAR và các file nhị phân cần được sao chép nguyên byte, không đi qua filter hoặc chuyển đổi encoding.

### 3.3. Lưu ý riêng với file `.properties`

Không thể suy ra rằng mọi API đọc `.properties` đều hiểu UTF-8 chỉ vì dự án đã chọn UTF-8. Ví dụ, `java.util.Properties.load(InputStream)` sử dụng quy tắc ISO-8859-1 truyền thống, còn overload `load(Reader)` sử dụng charset mà `Reader` cung cấp:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Properties settings = new Properties();
try (var reader = Files.newBufferedReader(
        Path.of("src/main/resources/app.properties"),
        StandardCharsets.UTF_8)) {
    settings.load(reader);
}
```

Cơ chế `ResourceBundle` trong các JDK hiện đại có quy tắc riêng cho properties; không nên áp dụng máy móc giả định của `Properties.load(InputStream)` lên mọi thư viện. Tương tự, khi Ant nạp file properties qua task `<property file="...">`, cần xem quy ước encoding của task/định dạng đó. Nếu chứa ký tự ngoài ASCII, có thể dùng Unicode escape theo quy ước properties truyền thống hoặc chọn cơ chế đọc UTF-8 tường minh.

Đặt UTF-8 **không có BOM** là quy ước dễ quản lý cho mã nguồn và tài nguyên text thông thường, nhất là khi kết hợp nhiều parser và công cụ.

## 4. Cố định locale: không để dữ liệu phụ thuộc ngôn ngữ của máy

Locale ảnh hưởng đến cách chương trình biểu diễn số, ngày giờ, tên tháng, so khớp/chuyển đổi chữ hoa chữ thường và thông điệp một số thư viện.

Ví dụ với Java:

```java
import java.text.NumberFormat;
import java.util.Locale;

double value = 12345.67;

System.out.println(
    NumberFormat.getNumberInstance(Locale.US).format(value)
);
System.out.println(
    NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN")).format(value)
);
```

Giá trị số không thay đổi; chuỗi biểu diễn của nó thì có thể khác. Điều này đặc biệt nguy hiểm khi chương trình ghi số vào CSV, JSON tự tạo, file báo cáo hoặc dữ liệu được hash.

### 4.1. Khóa locale cho tiến trình Java do Ant chạy

```xml
<java classname="org.example.ReportApp"
      fork="true"
      failonerror="true">
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>

    <jvmarg value="-Duser.language=vi"/>
    <jvmarg value="-Duser.country=VN"/>
</java>
```

Đặt `fork="true"` để các JVM argument được truyền tới một JVM mới. Tham số `user.language` và `user.country` chi phối locale mặc định mà JVM khởi tạo; nếu ứng dụng tự gọi `Locale.setDefault(...)`, ứng dụng có thể thay đổi mặc định này trong quá trình chạy.

Đối với test, áp dụng cấu hình tương tự cho **tiến trình test thật sự**. Nếu dùng task `<junit>` có fork, cấu hình các `<jvmarg>` tương ứng; nếu test chạy ngay trong JVM Ant, môi trường khởi động Ant và cơ chế test runner cần được kiểm soát.

### 4.2. Khi nào nên dùng `Locale.ROOT`?

Với đầu ra phục vụ **máy xử lý** như ID, tên khóa, định dạng số bất biến hoặc log có cấu trúc, truyền locale trực tiếp thường an toàn hơn so với trông chờ mặc định hệ thống:

```java
import java.util.Locale;

String machineValue = String.format(Locale.ROOT, "%.2f", 12345.67);
// machineValue: "12345.67"

String stableKey = "TITLE".toLowerCase(Locale.ROOT);
```

Với nội dung phục vụ người đọc tại Việt Nam, có thể dùng `Locale.forLanguageTag("vi-VN")`. Chọn locale theo **ý nghĩa của dữ liệu**, rồi cố định lựa chọn đó trong mã hoặc trong tham số đầu vào đã kiểm soát.

Lưu ý: Cùng một locale vẫn có thể có khác biệt nhỏ về dữ liệu định dạng giữa các phiên bản JDK/CLDR. Nếu yêu cầu so sánh byte tuyệt đối, cần cố định phiên bản runtime và bộ dữ liệu định dạng được dùng.

## 5. Cố định múi giờ: phân biệt thời điểm với giờ hiển thị

`Instant` biểu diễn một thời điểm tuyệt đối; `LocalDateTime` không có thông tin múi giờ; `ZonedDateTime` chứa quy tắc vùng thời gian. Kết quả khác nhau thường xuất hiện khi một `Instant` bị chuyển thành chuỗi sử dụng `ZoneId.systemDefault()`.

Ví dụ, cùng thời điểm `2024-01-02T03:04:05Z` sẽ có giờ hiển thị khác nhau khi trình bày theo UTC và theo `Asia/Ho_Chi_Minh`.

### 5.1. Khóa múi giờ cho chương trình fork từ Ant

```xml
<java classname="org.example.ReportApp"
      fork="true"
      failonerror="true">
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>

    <jvmarg value="-Duser.timezone=UTC"/>
</java>
```

Tham số `-Duser.timezone=UTC` tác động tới múi giờ mặc định của JVM mới. Với tác vụ `<exec>` gọi lệnh ngoài, biến môi trường `TZ` có thể hữu ích trên những nền tảng và chương trình hỗ trợ nó; không nên giả định mọi công cụ hoặc Windows sẽ diễn giải `TZ` giống nhau.

### 5.2. Ưu tiên chỉ định vùng thời gian trực tiếp trong Java

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Instant snapshot = Instant.parse("2024-01-02T03:04:05Z");

String iso = DateTimeFormatter.ISO_INSTANT.format(snapshot);
// "2024-01-02T03:04:05Z"

String display = DateTimeFormatter
        .ofPattern("yyyy-MM-dd HH:mm:ss", Locale.ROOT)
        .withZone(ZoneOffset.UTC)
        .format(snapshot);
// "2024-01-02 03:04:05"
```

Không nên đưa `Instant.now()`, `new Date()` hay thời gian build thực tế vào artifact nếu mục tiêu là đầu ra byte giống nhau giữa các lần chạy. Khóa múi giờ chỉ khiến cách *diễn giải* thời gian nhất quán; nó không khiến **thời điểm hiện tại** trở thành một đầu vào cố định. Với build cần timestamp, hãy đưa timestamp vào như một đầu vào đã xác định trước (chẳng hạn mốc phát hành/commit được hệ thống cung cấp và ghi nhận), rồi format bằng vùng thời gian được chọn.

## 6. Cố định ký tự xuống dòng: LF, CRLF và file nhị phân

Một dòng text có thể kết thúc bằng:

| Kiểu | Byte thường gặp | Chú thích |
|---|---|---|
| LF | `0A` | Quy ước phổ biến trong môi trường Unix và nhiều repository |
| CRLF | `0D 0A` | Quy ước phổ biến với file text trên Windows |
| CR | `0D` | Kiểu cũ, ít gặp |

Đối với nội dung UTF-8, ký tự xuống dòng này có cách mã hóa như bảng trên. Hai file có cùng chữ nhưng khác LF/CRLF sẽ có SHA-256 khác nhau.

**Chọn một chính sách theo loại file.** Ví dụ: Java, XML, YAML, Markdown, TXT và tài nguyên text phát hành dùng LF; script `.bat` có thể giữ CRLF nếu cần tương thích công cụ trên Windows.

### 6.1. Chuẩn hóa tài nguyên text bằng `<fixcrlf>`

Ant có task `<fixcrlf>` để xử lý xuống dòng và một số chi tiết văn bản. Thực hiện trên thư mục staging giúp bảo toàn mã nguồn gốc:

```xml
<mkdir dir="build/normalized-resources"/>

<fixcrlf srcdir="src/main/resources"
         destdir="build/normalized-resources"
         includes="**/*.txt,**/*.xml,**/*.properties"
         eol="lf"
         tab="asis"
         eof="remove"
         fixlast="true"
         encoding="UTF-8"
         outputencoding="UTF-8"/>
```

Ý nghĩa các lựa chọn:

- `eol="lf"`: thống nhất dòng mới thành LF.
- `tab="asis"`: không tự đổi tab thành dấu cách hoặc ngược lại.
- `eof="remove"`: loại bỏ dấu EOF kiểu DOS khi có.
- `fixlast="true"`: bảo đảm dòng cuối có dấu kết thúc dòng phù hợp nếu đang thiếu.
- `encoding` và `outputencoding`: đọc và ghi theo UTF-8, tránh việc chuyển đổi dòng làm biến dạng ký tự.

Chỉ chọn mẫu file đã xác định là text. Không dùng `<fixcrlf>` cho `.png`, `.jpg`, `.zip`, `.jar` hoặc dữ liệu nhị phân khác.

### 6.2. Cố định dòng mới trong mã sinh file

Trong Java:

```java
String report = "first\nsecond\n"; // LF cố định

// Dễ phụ thuộc hệ điều hành nếu dùng cho artifact tái lập:
String platformDependent = "first" + System.lineSeparator() + "second";
```

Dùng `\n` khi định dạng đầu ra yêu cầu LF. Với định dạng có quy tắc riêng (ví dụ giao thức mạng yêu cầu CRLF), phải theo **đặc tả của định dạng** thay vì áp dụng LF cho mọi thứ.

Có thể phối hợp thêm `.gitattributes` để Git thống nhất file text được checkout:

```gitattributes
*.java       text eol=lf
*.xml        text eol=lf
*.properties text eol=lf
*.md         text eol=lf
*.txt        text eol=lf
*.bat        text eol=crlf
*.png        binary
*.jar        binary
```

Quy định Git giúp tránh thay đổi xuống dòng ngoài ý muốn khi người dùng checkout trên Windows hoặc Linux. Task Ant vẫn có trách nhiệm chuẩn hóa tài nguyên text phát hành từ những nguồn đầu vào mà nó xử lý.

## 7. Ví dụ hoàn chỉnh: một build Ant sinh báo cáo text nhất quán

Giả sử muốn tạo `build/reports/report.txt` với tiếng Việt, số, thời gian và dấu xuống dòng xác định. Cấu trúc dự án:

```text
ant-reproducible-demo/
├── build.xml
└── src/
    └── main/
        ├── java/
        │   └── org/example/ReportApp.java
        └── resources/
            └── labels.txt
```

Nội dung `src/main/resources/labels.txt` được lưu UTF-8:

```text
Xin chào
```

### 7.1. File `build.xml`

Ví dụ dùng Ant 1.10.x và JDK 17 trở lên. Tất cả property liên quan đến văn bản và tiến trình chạy được khai báo tại một nơi:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-reproducible-demo" default="run" basedir=".">

    <!-- Các đầu vào cấu hình được quản lý cùng build -->
    <property name="src.dir" location="src/main/java"/>
    <property name="resources.dir" location="src/main/resources"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="normalized.dir" location="${build.dir}/normalized-resources"/>
    <property name="report.dir" location="${build.dir}/reports"/>

    <property name="text.encoding" value="UTF-8"/>
    <property name="java.release" value="17"/>
    <property name="run.language" value="vi"/>
    <property name="run.country" value="VN"/>
    <property name="run.timezone" value="UTC"/>
    <property name="report.instant" value="2024-01-02T03:04:05Z"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

    <target name="init">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${normalized.dir}"/>
        <mkdir dir="${report.dir}"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="${text.encoding}"
               release="${java.release}"
               includeantruntime="false"/>
    </target>

    <!-- Text được xử lý trong staging, không sửa tài nguyên gốc. -->
    <target name="normalize-resources" depends="init">
        <fixcrlf srcdir="${resources.dir}"
                 destdir="${normalized.dir}"
                 includes="**/*.txt,**/*.properties,**/*.xml"
                 eol="lf"
                 tab="asis"
                 eof="remove"
                 fixlast="true"
                 encoding="${text.encoding}"
                 outputencoding="${text.encoding}"/>

        <copy todir="${classes.dir}">
            <fileset dir="${normalized.dir}"/>
        </copy>
    </target>

    <!-- JVM được fork nên locale/timezone của ứng dụng có phạm vi rõ. -->
    <target name="run" depends="compile,normalize-resources">
        <java classname="org.example.ReportApp"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
            </classpath>

            <jvmarg value="-Duser.language=${run.language}"/>
            <jvmarg value="-Duser.country=${run.country}"/>
            <jvmarg value="-Duser.timezone=${run.timezone}"/>

            <sysproperty key="report.instant"
                         value="${report.instant}"/>
            <arg file="${report.dir}/report.txt"/>
        </java>
    </target>

</project>
```

Có ba luồng độc lập trong ví dụ:

1. `compile` buộc trình biên dịch đọc Java source bằng UTF-8.
2. `normalize-resources` đưa text từ tài nguyên vào staging với LF rồi sao chép sang classpath.
3. `run` khởi chạy JVM mới có locale `vi-VN`, múi giờ `UTC` và thời điểm báo cáo được truyền làm đầu vào.

Task `<copy>` ở đây sao chép **những file đã chuẩn hóa**; nó không cần filter và không thực hiện chuyển đổi charset lần thứ hai.

### 7.2. File `src/main/java/org/example/ReportApp.java`

```java
package org.example;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Objects;

public final class ReportApp {

    private ReportApp() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected output file path");
        }

        String label;
        try (InputStream stream = Objects.requireNonNull(
                ReportApp.class.getResourceAsStream("/labels.txt"),
                "Missing /labels.txt")) {
            label = new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8
            ).strip();
        }

        Locale locale = Locale.getDefault();
        ZoneId zone = ZoneId.systemDefault();
        Instant snapshot = Instant.parse(
                System.getProperty("report.instant")
        );

        String number = NumberFormat
                .getNumberInstance(locale)
                .format(12345.67);

        String timestamp = DateTimeFormatter
                .ofPattern("dd/MM/yyyy HH:mm:ss", locale)
                .withZone(zone)
                .format(snapshot);

        // Dòng mới LF và charset UTF-8 không phụ thuộc hệ điều hành.
        String report = "Nhãn: " + label + "\n"
                + "Ngôn ngữ: " + locale.toLanguageTag() + "\n"
                + "Múi giờ: " + zone.getId() + "\n"
                + "Số: " + number + "\n"
                + "Thời điểm: " + timestamp + "\n";

        Path output = Path.of(args[0]);
        Files.createDirectories(output.toAbsolutePath().getParent());
        Files.writeString(output, report, StandardCharsets.UTF_8);
    }
}
```

Code đọc tài nguyên bằng UTF-8, format dựa trên locale/timezone của JVM đã được Ant kiểm soát, dùng một `Instant` cố định và ghi UTF-8 với LF. Nếu muốn ứng dụng độc lập hoàn toàn khỏi cấu hình mặc định của JVM, có thể thay `Locale.getDefault()` và `ZoneId.systemDefault()` bằng `Locale.forLanguageTag("vi-VN")` và `ZoneOffset.UTC`. Lựa chọn đầu tiên trong ví dụ giúp quan sát được tác dụng của các tham số fork trong Ant.

### 7.3. Chạy trên máy phát triển hoặc CI

Ở thư mục chứa `build.xml`:

```bash
ant -version
java -version
ant clean run
```

File `build/reports/report.txt` sẽ có cấu trúc tương tự:

```text
Nhãn: Xin chào
Ngôn ngữ: vi-VN
Múi giờ: UTC
Số: 12.345,67
Thời điểm: 02/01/2024 03:04:05
```

Dấu phân tách số minh họa cách định dạng của locale `vi-VN`; chi tiết dữ liệu locale có thể phụ thuộc phiên bản JDK, vì vậy build cần ghim cùng bản JDK để so sánh byte tuyệt đối.

Nếu lưu lại SHA-256 của `build/reports/report.txt` rồi chạy lại cùng đầu vào, phiên bản công cụ và cấu hình, hash cần giống nhau. Một số cách xem hash:

```bash
# Linux/macOS khi có sha256sum
sha256sum build/reports/report.txt
```

```powershell
# Windows PowerShell
Get-FileHash -Algorithm SHA256 -Path .\build\reports\report.txt
```

Không nên lấy hash của file log console làm bằng chứng tương đương: log có thể chứa đường dẫn tuyệt đối, thời điểm chạy hoặc thông tin từ Ant/JVM khác với nội dung báo cáo đã được kiểm soát.

## 8. Kiểm soát chính JVM chạy Ant

Cấu hình ở `<java fork="true">` giải quyết tiến trình ứng dụng, nhưng **không tự động đổi locale hay timezone của JVM Ant**. Nếu các task Ant khác lấy locale hoặc timezone mặc định, có thể khởi động Ant bằng `ANT_OPTS`:

```bash
# Bash / shell tương thích POSIX
ANT_OPTS="-Duser.language=vi -Duser.country=VN -Duser.timezone=UTC" ant clean run
```

```powershell
# PowerShell
$env:ANT_OPTS = "-Duser.language=vi -Duser.country=VN -Duser.timezone=UTC"
ant clean run
```

Cách dùng `ANT_OPTS` phụ thuộc script launcher của Ant; kiểm tra launcher thực tế trong môi trường CI. Biến môi trường này cấu hình JVM đang **chạy Ant**, còn `<jvmarg>` cấu hình JVM **do Ant fork ra**. Có trường hợp cần cả hai.

Đừng dựa duy nhất vào `-Dfile.encoding=UTF-8` làm chiến lược chuẩn hóa. Giá trị này có lịch sử xử lý khác nhau theo JDK và không thay thế được encoding được truyền trực tiếp vào `<javac>`, `<loadfile>` hoặc các API đọc/ghi file. Các phiên bản JDK mới đã ưu tiên UTF-8, nhưng hợp đồng rõ ràng tại điểm đọc/ghi vẫn dễ kiểm chứng hơn.

Nếu Ant chạy một chương trình ngoài bằng `<exec>`, cần kiểm soát riêng chương trình đó: tham số charset/locale của công cụ, mã trang terminal khi thật sự liên quan, biến môi trường được hỗ trợ và quy ước dòng mới ở đầu ra. Chỉ đặt locale cho JVM Ant không bảo đảm một tiện ích bên ngoài viết cùng byte trên mọi hệ điều hành.

## 9. Khi đầu ra vẫn khác: xác định đúng phạm vi sai khác

| Biểu hiện | Nguồn cần xem xét | Hướng xử lý |
|---|---|---|
| Ký tự tiếng Việt lỗi ở `.class`, báo cáo hoặc tài nguyên | Charset đọc source, resource, properties và charset khi ghi | Khai báo UTF-8 tại từng task/API; xem riêng cơ chế đọc `.properties` |
| Số hoặc tên tháng khác nhau | Locale của tiến trình format, phiên bản JDK/CLDR | Truyền `Locale` rõ ràng, cố định runtime |
| Báo cáo lệch giờ | JVM/process dùng zone mặc định khác hoặc thời điểm khác | Dùng UTC/zone chỉ định và timestamp đầu vào cố định |
| Nội dung nhìn giống nhưng SHA-256 khác | LF/CRLF, BOM, khoảng trắng, dấu dòng cuối | So sánh byte; chuẩn hóa text trong staging bằng `<fixcrlf>` |
| `report.txt` giống nhưng JAR khác | Timestamp của ZIP entry, manifest, thứ tự entry, nội dung sinh khác | Áp dụng thêm chính sách đóng gói tái lập, đồng bộ công cụ/dependency |
| Chỉ CI khác máy cá nhân | JDK/Ant khác phiên bản, môi trường khởi chạy khác, property override | Ghim phiên bản, ghi nhận lệnh và cấu hình khởi chạy |

**Quy tắc thực hành:** Mỗi phép đọc text phải biết charset; mỗi phép định dạng cho dữ liệu phải biết locale; mỗi phép chuyển đổi thời gian phải biết zone và nguồn timestamp; mỗi file text phát hành phải có chính sách xuống dòng. Trong Ant, các quyết định đó cần được áp dụng đúng nơi công việc diễn ra: task Ant, compiler, JVM fork hoặc công cụ ngoài.

Khi các đầu vào này được cố định, sự khác biệt còn lại có thể được truy ngược đến những yếu tố khác như phiên bản toolchain, metadata hoặc logic sinh artifact. Đây là nền tảng thiết thực để xây dựng pipeline Ant có kết quả ổn định trên máy lập trình viên và CI.

