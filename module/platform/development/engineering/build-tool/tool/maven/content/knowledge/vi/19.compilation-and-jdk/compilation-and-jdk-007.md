# Encoding, tham số javac và chính sách cảnh báo biên dịch trong Maven

## 1. Tại sao một dự án Java cần ba nhóm cấu hình này?

Khi Maven chạy `compile` hoặc `test-compile`, Maven Compiler Plugin gọi bộ biên dịch Java (thường là `javac` của JDK đang chạy Maven, hoặc JDK được chọn qua toolchain). Compiler phải biết **cách đọc tệp nguồn**, **phiên bản ngôn ngữ/API và các tùy chọn biên dịch**, đồng thời **phải xử lý cảnh báo như thế nào**.

Ba nhóm trách nhiệm khác nhau:

1. **Encoding**: byte trong `.java` và các tài nguyên văn bản được diễn giải thành ký tự như thế nào; UTF-8 là lựa chọn phổ biến để mã có tiếng Việt, ký hiệu quốc tế và dấu câu đặc biệt không phụ thuộc máy phát triển.
2. **Tham số `javac`**: `--release`, `-Xlint`, `-parameters`, `-g`, giới hạn cảnh báo và những cờ đặc thù JDK. Maven Compiler Plugin cung cấp các tham số chuyên dụng và `<compilerArgs>` để truyền thêm tùy chọn.
3. **Chính sách cảnh báo**: cảnh báo chỉ được ghi ra log, hay một warning phải làm pipeline thất bại? Có dùng `-Werror` hay `failOnWarning` không? Cảnh báo nào thực sự có ý nghĩa đối với dự án?

Đây **không phải một nút bật/tắt duy nhất**. Một dự án có thể dùng `UTF-8` đúng nhưng chọn sai API Java; hoặc có `--release 17` chính xác nhưng quên bật cảnh báo về API deprecated; hoặc báo `BUILD SUCCESS` dù compiler đã phát hiện unsafe generic conversions.

```text
pom.xml + src/main/java + src/test/java + resources
                    |
                    v
       maven-compiler-plugin
          |          |           |
          v          v           v
       encoding    --release    -Xlint / -Werror
       UTF-8          17        showWarnings, failOnWarning
          |          |           |
          +----------+-----------+
                     |
              javac / JDK
                     |
             .class + diagnostics
                     |
             build success/failure
```

**Mục tiêu của bài:** sau khi học, bạn có thể cấu hình Maven Compiler Plugin 3.14.1 cho Java 17, kiểm chứng UTF-8 bằng chương trình và resource tiếng Việt, chuyển cảnh báo thành lỗi build có chủ đích, phân biệt `--release` với `-source/-target` và thiết kế chính sách warnings hợp lý cho CI.

## 2. Encoding thực sự quyết định điều gì?

Một tệp văn bản trên đĩa là chuỗi byte. **Character encoding** quyết định cách giải mã byte thành ký tự. Cùng byte mà đọc với UTF-8 và một encoding khác có thể tạo ra ký tự sai, ví dụ những chữ có dấu như “Tiếng Việt”, “Hà Nội”, “café” hoặc ký tự Nhật.

Trong dự án Maven cần phân biệt ít nhất bốn tầng:

| Tầng | Ví dụ | Ai kiểm soát? |
| --- | --- | --- |
| Tệp nguồn Java | `src/main/java/.../Greeting.java` chứa `"Xin chào"` | Editor lưu tệp; `javac -encoding` lúc đọc |
| Tài nguyên văn bản | `src/main/resources/motto.txt` | Cách lưu tệp, Maven Resources Plugin khi filtering, cách chương trình đọc |
| Báo cáo/tài liệu | Javadoc, reports được tạo | Plugin reporting/Javadoc liên quan, encoding do chúng hỗ trợ |
| Console/runtime I/O | `System.out`, file ngoài, HTTP payload | JVM, terminal và API đọc/ghi thực tế |

Vì vậy đặt `<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>` là một nền tảng tốt, **nhưng không tự quyết định encoding cho mọi luồng I/O lúc ứng dụng chạy**. Chẳng hạn:

- Chương trình đọc `.txt` bằng `Files.readString(path, StandardCharsets.UTF_8)` sẽ dùng UTF-8 tường minh, độc lập với cấu hình compiler.
- Nếu dùng API có charset mặc định hoặc console chạy dưới encoding khác, đầu ra có thể bị hiển thị sai dù mã nguồn đã được compile đúng.
- `Properties.load(InputStream)` có quy tắc encoding riêng, không giống việc đọc văn bản thông thường bằng UTF-8; với `.properties` chứa ký tự quốc tế nên chọn API/định dạng phù hợp.
- Tệp nhị phân như ảnh, font hay ZIP không nên bị “lọc ký tự” chỉ vì resource plugin được cấu hình UTF-8.

## 3. Thiết lập UTF-8 ở POM: một nguồn cấu hình thống nhất

Cách thông dụng là khai báo trong `<properties>` của `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
```

Đây là **đoạn con của POM**, không phải tệp POM độc lập.

- `project.build.sourceEncoding`: property mà Maven Compiler Plugin và các plugin khác thường dùng để chọn encoding cho mã nguồn hoặc resource text.
- `project.reporting.outputEncoding`: giá trị quy ước cho các plugin sinh báo cáo hỗ trợ property đó; **không phải cờ `javac`**.
- `maven.compiler.release`: đặt target Java Platform của việc biên dịch, không liên quan cách byte UTF-8 được giải mã.

Với Maven Compiler Plugin 3.14.1, tham số `<encoding>` có default là `${project.build.sourceEncoding}`. Để dễ kiểm chứng khi đọc POM, có thể viết tường minh:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <encoding>${project.build.sourceEncoding}</encoding>
        <release>${maven.compiler.release}</release>
    </configuration>
</plugin>
```

Đây là **đoạn plugin đặt trong `<build><plugins>`**. Khi thực thi compiler goal tương ứng, Maven ánh xạ `encoding` thành tùy chọn `javac -encoding UTF-8`.

**Bắt buộc nhất quán với editor:** hãy lưu các file `.java` thực sự bằng UTF-8, tốt nhất không kèm UTF-8 BOM nếu công cụ compile không chấp nhận byte BOM ở đầu source. Chỉ ghi property UTF-8 trong POM không “chuyển đổi” mọi file đã được lưu ở encoding khác. Nếu nguồn cũ là Windows-1252 hoặc một encoding nội bộ, cần **chuyển đổi byte đúng cách** chứ không chỉ sửa một dòng XML.

### 3.1. UTF-8 và Java 18+ có tự động xử lý hết không?

Một số JDK hiện đại (từ JDK 18, theo JEP 400) dùng UTF-8 làm default charset cho nhiều API theo thiết kế. Tuy nhiên:

- JDK 17 có thể phụ thuộc default charset môi trường.
- Không phải mọi tool, terminal hoặc thư viện xử lý encoding giống nhau.
- Maven vẫn cần những cấu hình rõ ràng để build tái lập giữa các hệ điều hành, JDK và runner.
- Đặt `-Dfile.encoding=UTF-8` cho JVM không phải giải pháp chung thay cho việc định nghĩa encoding của source, resources và các API I/O.

Vì vậy **vẫn nên khai báo encoding trong POM và truyền UTF-8 tường minh khi chương trình xử lý file văn bản cần chuẩn đó**.

## 4. Source encoding và Resources Plugin: cùng một giá trị, hai nhiệm vụ khác nhau

Maven Compiler Plugin đọc `.java`. Maven Resources Plugin xử lý những tài nguyên trong `src/main/resources` hoặc `src/test/resources`.

Với Resources Plugin 3.3.1, tham số `encoding` thường mặc định dựa trên `${project.build.sourceEncoding}`, hữu ích khi **filtering** nội dung văn bản (thay placeholder trong resource).

Ví dụ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <encoding>${project.build.sourceEncoding}</encoding>
    </configuration>
</plugin>
```

Khi một resource được **copy không filtering**, plugin thường giữ nguyên byte; điều này khác với việc đọc rồi tái mã hóa văn bản. Nếu filtering bật, encoding ảnh hưởng tới việc plugin đọc/ghi phần văn bản.

Đừng bật filtering bừa trên mọi loại file. Ví dụ PNG và ZIP không phải văn bản để thay placeholder. Nếu dùng `.properties` có tiếng Việt và filtering, cần kiểm tra `propertiesEncoding` và cách ứng dụng nạp `.properties`; API `Properties.load(InputStream)` có quy ước ISO-8859-1, còn `Properties.load(Reader)` dùng charset của Reader do bạn chỉ định.

**Nguyên tắc:** source Java, filtered resources và runtime file I/O là các bề mặt riêng; nhất quán UTF-8 ở từng bề mặt mới giảm lỗi encoding.

## 5. Chọn Java release: vì sao dùng --release 17?

Trong Maven Compiler Plugin 3.14.1, cấu hình thường dùng cho dự án Java 17 là:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Tham số tương ứng của `javac` là **`--release 17`**.

So với hai tùy chọn cũ:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `--release 17` | Biên dịch theo Java 17, gồm quy tắc ngôn ngữ, class-file target và những API Java Platform được phép cho release 17 |
| `-source 17` | Chọn quy tắc cú pháp Java 17 |
| `-target 17` | Chọn định dạng class file cho Java 17 |
| `-source 17 -target 17` | Không bảo đảm tự động ngăn việc tham chiếu API Java Platform chỉ có trong JDK mới hơn |
| `-encoding UTF-8` | Chỉ cách javac đọc byte của file source; không chọn Java release |

Đối với code Java 17 chạy trên Java 17, `--release 17` thường là lựa chọn rõ ràng hơn. **Đừng đặt `--release` và `-source/-target` mâu thuẫn nhau**; `javac` có thể từ chối những tổ hợp đó.

Một lưu ý quan trọng: `--release 17` **không đổi JDK đang chạy Maven**. Nếu Maven chạy trên JDK quá cũ để hỗ trợ release 17, compiler sẽ báo release không được hỗ trợ. Nếu runtime chỉ có Java 11, class file của Java 17 cũng không chạy được ở đó.

Kiểm tra trên terminal:

```bash
mvn -version
java -version
javac -version
```

Maven thường dùng compiler của JDK chạy Maven, nhưng khi dự án dùng Maven Toolchains hoặc cấu hình compiler khác, compiler JDK có thể khác runtime của lệnh `mvn -version`. Khi đó cần kiểm tra toolchain thật được chọn, không dựa duy nhất vào `JAVA_HOME`.

## 6. Truyền tham số javac qua Maven Compiler Plugin

Maven Compiler Plugin có các **tham số chuyên dụng** như `encoding`, `release`, `parameters`, `showWarnings`, `showDeprecation`, `failOnWarning`. Với các cờ compiler khác, dùng `<compilerArgs>`.

Ví dụ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
        <parameters>true</parameters>
        <showWarnings>true</showWarnings>
        <showDeprecation>true</showDeprecation>
        <compilerArgs>
            <arg>-Xlint:deprecation,unchecked,rawtypes</arg>
            <arg>-Xmaxwarns</arg>
            <arg>100</arg>
        </compilerArgs>
    </configuration>
</plugin>
```

Phần tử `<compilerArgs>` chứa **danh sách các đối số** gửi tới compiler. Trong ví dụ:

- `-Xlint:deprecation,unchecked,rawtypes` là **một đối số**, bật các nhóm kiểm tra deprecation, unchecked và raw types của `javac`.
- `-Xmaxwarns` và `100` là **hai đối số riêng biệt**, yêu cầu giới hạn số diagnostics warnings mà compiler trình bày.
- `<parameters>true</parameters>` là cách plugin yêu cầu compiler lưu tên parameter thực trong bytecode; tương ứng với tùy chọn `-parameters` của `javac`.
- `<showWarnings>true</showWarnings>` cho phép hiển thị cảnh báo thay vì cố tình tắt chúng.
- `<showDeprecation>true</showDeprecation>` giúp có thông tin vị trí sử dụng API deprecated.

Không cần ghi đồng thời `<parameters>true</parameters>` **và** thêm `<arg>-parameters</arg>`: hai cách cùng nhằm một mục đích. Ưu tiên tham số plugin có tên rõ ràng khi plugin đã hỗ trợ; giữ `compilerArgs` cho các cờ chưa có tham số riêng hoặc cần cấu hình đặc biệt.

### 6.1. compilerArgs khác compilerArgument

`<compilerArgs>` là một list đối số, thuận tiện cho tùy chọn cần nhiều token. `<compilerArgument>` là một chuỗi tham số đơn và dễ bị nhầm khi chứa khoảng trắng; dùng list cho độ rõ ràng cao hơn.

Ví dụ về hai token:

```xml
<compilerArgs>
    <arg>-Xmaxwarns</arg>
    <arg>100</arg>
</compilerArgs>
```

Không viết `<arg>-Xmaxwarns 100</arg>` rồi giả định mọi compiler/JDK sẽ tách chuỗi đó thành hai đối số. Với một compiler arg mà giá trị phải tách riêng, khai báo từng `arg` là cách dễ kiểm soát.

### 6.2. Cẩn trọng với tùy chọn đặc thù JDK

`-Xlint` và các cờ của `javac` phụ thuộc compiler thực tế. Một số tham số thay đổi giữa JDK hoặc giữa các compiler khác `javac`.

Ví dụ:

- `--add-exports` liên quan mô hình module Java và có giới hạn khi dùng cùng `--release`; không nên thêm bừa.
- `-J-Xmx...` điều khiển JVM chạy compiler **khi compiler được fork**; trong Maven Compiler Plugin, `-J` chỉ được chuyển tiếp phù hợp nếu `<fork>true</fork>`.
- `-Akey=value` thường dành cho annotation processor, không giống property `-Dkey=value` truyền cho Maven.
- `-Xlint:all` có thể bật thêm cảnh báo mà codebase trước đây không thấy; kiểm tra trên JDK/CI thật trước khi đặt `-Werror`.

Nên dùng `javac --help` và `javac -X`, đồng thời tra tài liệu của đúng JDK mà dự án đã chọn.

## 7. Cảnh báo biên dịch là gì?

Cảnh báo (warning) không luôn là lỗi cú pháp. Ví dụ compiler có thể thông báo về:

- **deprecation**: code sử dụng API đánh dấu không nên dùng tiếp.
- **unchecked**: thao tác generic không được compiler kiểm chứng an toàn kiểu tại compile time.
- **rawtypes**: sử dụng generic type không có type argument, ví dụ `List` thay vì `List<String>`.
- **serial**: một số class serializable thiếu `serialVersionUID` hoặc có vấn đề liên quan serialization.
- **fallthrough**: switch branch có khả năng rơi tiếp sang nhánh khác.
- **removal**: API được đánh dấu dự kiến loại bỏ.
- **processing**: vấn đề liên quan annotation processing, tùy JDK và cấu hình.

Một warning có thể chỉ là dấu hiệu cần review, nhưng cũng có thể cảnh báo nguy cơ lỗi runtime hoặc khó nâng cấp thư viện.

Ví dụ một khai báo raw type **cố ý chưa tốt**:

```java
// Đoạn minh họa cảnh báo, KHÔNG đặt vào project sạch của mục 9:
java.util.List names = new java.util.ArrayList();
names.add("Hà Nội");
java.util.List<String> checked = names;
```

Code minh họa này thiếu ngữ cảnh method/class, không phải tệp Java độc lập. Với `-Xlint:rawtypes,unchecked`, `javac` có thể báo raw type và unchecked conversion. Cách sửa thường là khai báo generic ngay từ đầu:

```java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("Hà Nội");
java.util.List<String> checked = names;
```

Cảnh báo là tín hiệu để sửa thiết kế; **không tự dùng `@SuppressWarnings("unchecked")` trên diện rộng** chỉ để log sạch. Chỉ suppress khi chứng minh được type safety và giới hạn phạm vi thật nhỏ.

## 8. Ba mức chính sách cảnh báo

Maven Compiler Plugin 3.14.1 hỗ trợ các lựa chọn sau:

| Chính sách | Cấu hình/cờ | Tác dụng |
| --- | --- | --- |
| Cho phép compiler hiển thị cảnh báo | `<showWarnings>true</showWarnings>` | Không tắt warnings trong compile output |
| Báo chi tiết API deprecated | `<showDeprecation>true</showDeprecation>` hoặc `-Xlint:deprecation` | Cho biết nơi dùng API deprecated |
| Chọn nhóm lint cần quan sát | `-Xlint:deprecation,unchecked,rawtypes` | Tập trung cảnh báo trên những loại được chọn |
| Bật phạm vi lint rộng | `-Xlint:all` | Kiểm tra nhiều nhóm hơn; có thể gây nhiều cảnh báo cần xử lý |
| Dùng cảnh báo làm build thất bại | `<failOnWarning>true</failOnWarning>` hoặc user property `maven.compiler.failOnWarning=true` | Nâng chính sách nghiêm ngặt |
| Cơ chế javac tương tự | `-Werror` | Khi javac gặp warning, biên dịch không được coi là thành công |
| Tắt warnings (không khuyến nghị để sửa lỗi) | `<showWarnings>false</showWarnings>` hoặc cờ tương đương | Giảm hiển thị; **không sửa nguồn gây warning** |

**Phân biệt hai công tắc quan trọng:**

- **`showWarnings`** quyết định có cố tình che các warnings hay không.
- **`failOnWarning`** quyết định warnings có làm build thất bại không.

Chỉ bật `showWarnings=true` **không có nghĩa warnings trở thành errors**. Chỉ bật `failOnWarning=true` mà một số warnings không được phát hiện hoặc bị tắt thì cũng không tạo ra chính sách toàn diện.

Trong plugin 3.14.1, `failOnWarning` có user property `maven.compiler.failOnWarning`; giá trị mặc định là `false`. Với POM **không đặt cứng** phần tử `<failOnWarning>`, có thể thử strict mode bằng:

```bash
mvn -Dmaven.compiler.failOnWarning=true clean verify
```

Nếu POM viết cứng `<failOnWarning>false</failOnWarning>`, **đừng mặc định một user property CLI có thể ghi đè XML đó**. Muốn CLI điều khiển có chủ đích, hãy dùng property do POM tham chiếu hoặc một Maven profile dành cho strict builds.

### 8.1. -Werror so với failOnWarning

Dùng `<arg>-Werror</arg>` trong `<compilerArgs>` là một cách yêu cầu `javac` coi warning như lỗi. `<failOnWarning>true</failOnWarning>` là cấu hình ở tầng Maven Compiler Plugin và thường là lựa chọn rõ ràng hơn nếu tổ chức muốn một quy tắc đồng nhất cho project.

Không cần đồng thời đặt cả hai cơ chế nếu chỉ cần mục tiêu “có cảnh báo thì compile fail”; lựa chọn một cách được review và kiểm chứng trên compiler đang dùng.

### 8.2. Những warnings nào nên bắt đầu bằng chế độ strict?

Trong một codebase đã tồn tại lâu, có thể đi theo trình tự:

1. Bật hiển thị warnings và `-Xlint` theo nhóm có liên quan.
2. Phân loại warnings theo mức rủi ro: unchecked casts, API deprecated for removal, raw types, lỗi annotation processing.
3. Sửa warning trong code mới hoặc trong phạm vi đang sửa.
4. Sau khi xác minh không còn warnings chưa xử lý, bật `failOnWarning=true` trên CI cho module/goal phù hợp.
5. Khi nâng JDK hoặc plugin, review các nhóm cảnh báo mới thay vì âm thầm tắt toàn bộ.

Chính sách strict cần có chủ sở hữu và quy trình cải thiện; không nên coi số lượng cảnh báo thấp hơn luôn đồng nghĩa code tốt hơn.

## 9. Dự án Java 17 chạy được: kiểm chứng UTF-8, -parameters và warnings

Ta tạo một Maven project nhỏ có **mã Java chứa chữ tiếng Việt**, một **resource UTF-8** và **ba bài kiểm thử JUnit Jupiter**. Cấu hình ban đầu **không tạo warnings cố ý**, vì vậy có thể build cả trong strict mode.

### 9.1. Cấu trúc thư mục

```text
encoding-javac-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/learn/
    │   │   ├── Greeting.java
    │   │   └── App.java
    │   └── resources/
    │       └── motto.txt
    └── test/
        └── java/dev/learn/
            └── GreetingTest.java
```

Tạo chính xác thư mục và tên file như trên. Khi lưu các file `.java`, `pom.xml` và `motto.txt` trong editor, hãy chọn **UTF-8**. Nếu dùng Windows, tránh copy text qua một công cụ tự chuyển mã không được kiểm soát.

### 9.2. pom.xml hoàn chỉnh

Tạo tệp `encoding-javac-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learn</groupId>
    <artifactId>encoding-javac-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
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
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <encoding>${project.build.sourceEncoding}</encoding>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                    <encoding>${project.build.sourceEncoding}</encoding>
                    <parameters>true</parameters>
                    <showWarnings>true</showWarnings>
                    <showDeprecation>true</showDeprecation>
                    <compilerArgs>
                        <arg>-Xlint:deprecation,unchecked,rawtypes</arg>
                        <arg>-Xmaxwarns</arg>
                        <arg>100</arg>
                    </compilerArgs>
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
            </plugin>
        </plugins>
    </build>
</project>
```

POM **không cố ý khai báo `<failOnWarning>`**: ta sẽ bật chính sách strict bằng user property của plugin khi cần. Một lệnh `-Dmaven.compiler.failOnWarning=true` có thể cấu hình plugin 3.14.1 qua property được tài liệu hóa, miễn là không bị POM/profile ghi đè bằng XML tường minh.

Lưu ý POM đã khai báo `resources/filtering=false`: resource text được copy từ `src/main/resources` sang `target/classes` theo byte; cấu hình encoding của Resources Plugin hữu ích nếu về sau bạn chủ động bật filtering cho tài nguyên văn bản.

### 9.3. Java source có Unicode

Tạo `src/main/java/dev/learn/Greeting.java`:

```java
package dev.learn;

public final class Greeting {
    private Greeting() {
    }

    public static String greet(String place) {
        if (place == null || place.isBlank()) {
            throw new IllegalArgumentException("Địa điểm không được trống");
        }
        return "Xin chào, " + place.strip() + "!";
    }
}
```

Trong mã có chữ `Địa điểm` và `Xin chào`. File cần được lưu bằng UTF-8; compiler đọc nó nhờ cấu hình POM. `greet(String place)` sẽ được biên dịch với tên parameter thật vì ta đã bật `<parameters>true</parameters>`.

Tạo `src/main/java/dev/learn/App.java`:

```java
package dev.learn;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public final class App {
    private App() {
    }

    public static String loadMotto() throws IOException {
        try (InputStream stream =
                     App.class.getResourceAsStream("/motto.txt")) {
            if (stream == null) {
                throw new IOException("Không tìm thấy /motto.txt");
            }
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                return reader.readLine();
            }
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println(Greeting.greet(" Hà Nội "));
        System.out.println(loadMotto());
    }
}
```

Điểm quan trọng: `InputStreamReader(stream, StandardCharsets.UTF_8)` chọn encoding **tại runtime** cho tệp tài nguyên. Nếu chỉ khai báo encoding trong POM mà code đọc văn bản bằng một charset khác, chương trình vẫn có thể in sai ký tự.

### 9.4. Tệp tài nguyên UTF-8

Tạo tệp `src/main/resources/motto.txt` chứa **đúng một dòng**:

```text
Café ở Hà Nội — 東京.
```

Tệp được lưu bằng UTF-8. Khi Maven xử lý resources, nó xuất hiện ở `target/classes/motto.txt`. Bài thực hành không dùng filtering nên không có placeholder nào cần được thay.

Dòng trên chứa tiếng Việt, ký tự é, dấu gạch dài và ký tự Nhật, thuận lợi để quan sát encoding. Nếu editor tự lưu file bằng một bảng mã khác, `App.loadMotto()` hoặc bài test ở mục tiếp theo sẽ không trả chuỗi mong đợi.

### 9.5. Unit test kiểm tra cả nội dung và tham số compiler

Tạo `src/test/java/dev/learn/GreetingTest.java`:

```java
package dev.learn;

import java.lang.reflect.Method;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GreetingTest {
    @Test
    void greetsUnicodeName() {
        assertEquals("Xin chào, Hà Nội!",
                Greeting.greet(" Hà Nội "));
    }

    @Test
    void readsUtf8Resource() throws Exception {
        assertEquals("Café ở Hà Nội — 東京.",
                App.loadMotto());
    }

    @Test
    void retainsParameterNameForReflection() throws Exception {
        Method method = Greeting.class.getMethod(
                "greet", String.class);
        assertTrue(method.getParameters()[0].isNamePresent());
        assertEquals("place",
                method.getParameters()[0].getName());
    }

    @Test
    void rejectsBlankPlace() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeting.greet("  "));
    }
}
```

**Có 4 tests** trong lớp này:

1. Xác nhận source UTF-8 với tên “Hà Nội”.
2. Xác nhận resource UTF-8 đọc được ở runtime.
3. Xác nhận tên parameter `place` được giữ trong bytecode theo `-parameters`.
4. Xác nhận input validation của mã Java.

Bài kiểm thử thứ ba là bằng chứng rằng tham số compiler **có tác dụng thực sự**, không chỉ xuất hiện dưới dạng XML trong POM.

### 9.6. Chạy build và chương trình

Ở thư mục `encoding-javac-lab`:

```bash
mvn -version
mvn clean verify
java -cp target/classes dev.learn.App
```

Điều kiện: JDK 17+ tương thích, Maven có thể phân giải các plugin/JUnit đã ghim version. `mvn clean verify` biên dịch, xử lý resources, biên dịch test, chạy **4 JUnit tests** và đóng gói JAR chính.

Khi build thành công, các file đáng chú ý gồm:

```text
target/classes/dev/learn/Greeting.class
target/classes/dev/learn/App.class
target/classes/motto.txt
target/test-classes/dev/learn/GreetingTest.class
target/surefire-reports/
target/encoding-javac-lab-1.0.0-SNAPSHOT.jar
```

Với terminal hiển thị UTF-8 đúng, stdout **do chương trình Java tạo** sẽ là:

```text
Xin chào, Hà Nội!
Café ở Hà Nội — 東京.
```

Khác với chương trình phụ thuộc JAR runtime bên ngoài, ứng dụng này chỉ dùng JDK và resource trong `target/classes`; vì vậy lệnh `java -cp target/classes` là đủ để chạy App. Không chạy `java -jar target/encoding-javac-lab-1.0.0-SNAPSHOT.jar` trong bài này rồi kỳ vọng tự chạy được: POM chưa khai báo `Main-Class` trong manifest.

**Giới hạn khi quan sát:** nếu test pass nhưng console Windows cũ hiển thị chữ méo, cần kiểm tra encoding terminal/console. Điều đó không nhất thiết chứng minh source encoding sai, vì test đã so sánh Unicode trong JVM thành công.

## 10. Thử một warning deprecated và bật chế độ strict

Phần này là **một thí nghiệm riêng, thực hiện sau khi ví dụ cơ bản đã chạy sạch**. Ta cố ý tạo một API deprecated và một lớp gọi tới API đó để quan sát warning. Không đưa hai file này vào dự án sạch nếu không thực hiện thí nghiệm.

### 10.1. Thêm API cũ

Tạo `src/main/java/dev/learn/LegacyMethods.java`:

```java
package dev.learn;

public final class LegacyMethods {
    private LegacyMethods() {
    }

    @Deprecated(since = "1.0", forRemoval = false)
    public static String oldGreeting() {
        return "Lời chào cũ";
    }
}
```

### 10.2. Một lớp khác gọi API deprecated

Tạo `src/main/java/dev/learn/WarningDemo.java`:

```java
package dev.learn;

public final class WarningDemo {
    private WarningDemo() {
    }

    public static String message() {
        return LegacyMethods.oldGreeting();
    }
}
```

Mã trên **hợp lệ về cú pháp** nhưng sử dụng một API đánh dấu `@Deprecated` từ lớp khác. Với `showDeprecation=true` và `-Xlint:deprecation` trong POM, compiler sẽ có cơ sở báo warning về lời gọi `oldGreeting()`. Văn bản cụ thể của warning và số dòng phụ thuộc phiên bản JDK.

### 10.3. Mức 1: warnings chỉ được hiển thị

Chạy lại:

```bash
mvn clean verify
```

Trong ví dụ này, warning deprecated thường được hiển thị, nhưng vì chưa bật `failOnWarning`, build vẫn có thể **BUILD SUCCESS** nếu không có compilation errors hay failures khác. Đây là chính sách **“cảnh báo để developer review”**.

Không coi thành công này là “không có vấn đề”: warning đã cho biết code đang dùng API có dấu hiệu nên thay thế.

### 10.4. Mức 2: warnings làm build thất bại

Chạy:

```bash
mvn -Dmaven.compiler.failOnWarning=true clean verify
```

Trong Maven Compiler Plugin 3.14.1, user property `maven.compiler.failOnWarning` bật chế độ thất bại khi compiler phát hiện warning. Với `WarningDemo` còn gọi API deprecated và javac báo warning, mục tiêu biên dịch sẽ **thất bại theo chính sách**; không được diễn giải đó là chương trình Java có lỗi cú pháp.

Một cách tường minh khác, nếu nhóm muốn strict mode luôn có hiệu lực ở POM:

```xml
<configuration>
    <showWarnings>true</showWarnings>
    <failOnWarning>true</failOnWarning>
    <compilerArgs>
        <arg>-Xlint:deprecation,unchecked,rawtypes</arg>
    </compilerArgs>
</configuration>
```

Đây là **đoạn cấu hình dành cho Maven Compiler Plugin**, không phải POM độc lập. Nếu áp dụng, hãy đặt trong `build/plugins/plugin/configuration` hoặc một execution/profile thích hợp và review tác động tới cả compile/testCompile.

Một cách ở tầng `javac` là thêm `<arg>-Werror</arg>` vào `compilerArgs`. Tuy nhiên, **không cần bật đồng thời mọi cơ chế strict**; hãy chọn một chính sách chính thức, đọc log và kiểm tra trên JDK được hỗ trợ.

### 10.5. Sửa đúng nguyên nhân và kiểm chứng lại

Trong `WarningDemo`, thay lời gọi API deprecated bằng API hiện tại:

```java
package dev.learn;

public final class WarningDemo {
    private WarningDemo() {
    }

    public static String message() {
        return Greeting.greet("Hà Nội");
    }
}
```

Sau khi sửa:

```bash
mvn -Dmaven.compiler.failOnWarning=true clean verify
```

Nếu không còn warnings phát sinh trong project và môi trường, build có thể PASS với strict mode. Hãy giữ lại log hoặc kết quả CI cho đợt kiểm tra.

**Không dùng `@SuppressWarnings("deprecation")` chỉ để đạt PASS khi API cũ vẫn gây rủi ro**. Nếu việc dùng API cũ là chủ đích bất khả kháng, document lý do và giới hạn suppression vào đoạn cần thiết sau khi review.

## 11. Dùng các lệnh javac trực tiếp để hiểu Maven đang cấu hình gì

Maven Compiler Plugin ánh xạ nhiều tham số sang `javac`. Không cần chạy javac bằng tay trong quy trình Maven thông thường, nhưng biết những lệnh tương đương giúp chẩn đoán.

Ví dụ trên Bash/zsh, sau khi tạo thư mục output riêng, có thể thử compile **chỉ một lớp Java độc lập về dependency**:

```bash
mkdir -p target/manual-classes
javac -encoding UTF-8 --release 17 -parameters \
  -Xlint:deprecation,unchecked,rawtypes \
  -d target/manual-classes src/main/java/dev/learn/Greeting.java
```

Lệnh này chỉ biên dịch `Greeting.java`, không chạy JUnit hay copy resources. Nó dùng `-encoding`, `--release`, `-parameters` và `-Xlint` ở đúng tầng `javac`. Không trộn kết quả manual compile với kết quả của Maven khi báo cáo CI.

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force target/manual-classes | Out-Null
javac -encoding UTF-8 --release 17 -parameters "-Xlint:deprecation,unchecked,rawtypes" -d target/manual-classes src/main/java/dev/learn/Greeting.java
```

Các file từ lệnh manual nằm ở `target/manual-classes`, không phải output chính của Maven. Khi chạy `mvn clean`, thư mục `target/` có thể bị xóa, đúng với mục đích dọn build artifacts.

### 11.1. Vì sao đôi khi javac và Maven phát warnings khác nhau?

Các lý do thường gặp:

- Lệnh javac manual chỉ biên dịch một file, Maven biên dịch cả project và test sources.
- Maven có dependency classpath và annotation processors khác lệnh manual.
- Maven dùng JDK/compiler khác qua toolchain hoặc cấu hình plugin.
- POM có profile/parent bổ sung compiler args và encoding.
- Build tăng dần không biên dịch lại mọi file đã có class output; `mvn clean compile` giúp quan sát đầy đủ hơn.
- Một plugin khác phát warnings; đó không nhất thiết là cảnh báo của `javac`.

Vì vậy khi so sánh, phải đối chiếu **nguồn file, phiên bản JDK, classpath, tham số compiler và phase đang chạy**, chứ không chỉ nhìn câu lệnh `mvn compile`.

## 12. Cấu hình cho cả compile và testCompile

Maven Compiler Plugin có hai goal chính:

- **`compiler:compile`**: biên dịch `src/main/java`.
- **`compiler:testCompile`**: biên dịch `src/test/java`.

Khi đặt `<configuration>` ở cấp plugin như POM bài thực hành, các tham số phù hợp thường được dùng cho cả hai goal. Do đó test code cũng được compile theo Java 17, UTF-8 và chính sách warnings đã định.

Đây là điều mong muốn trong phần lớn dự án: không nên cho mã kiểm thử dùng cú pháp Java mới hơn mà JDK CI không hỗ trợ chỉ vì nhóm quên cấu hình `testCompile`.

Tuy nhiên, các build phức tạp có thể cần cấu hình khác:

- Main code dùng `--release 17`, test code dùng một release tương thích khác theo chính sách công ty.
- Main compiler bật xử lý annotation, test compiler không cần.
- Một module lớn đang dọn warnings trong test riêng, còn main compilation đã áp dụng strict mode.

Khi đó hãy xem các tham số riêng cho `compiler:testCompile` (ví dụ `testRelease` của phiên bản plugin hỗ trợ) hoặc cấu hình **execution cụ thể** theo ID mặc định `default-compile`/`default-testCompile` trong default lifecycle. Cần kiểm tra cách Maven ghép cấu hình của plugin-level và execution-level để không vô tình truyền thêm compiler args ngoài ý muốn.

**Không mặc định mọi compiler parameter có tên giống nhau ở cả compile/testCompile.** Xem tài liệu goal phù hợp hoặc lệnh:

```bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=testCompile -Ddetail
```

## 13. Chính sách warnings cho CI nên chọn như thế nào?

Chính sách tốt thường gồm **các mức đã định nghĩa và kiểm chứng**, không chỉ một cờ `-Werror` được copy từ dự án khác.

### 13.1. Mức học tập/phát triển

- Luôn định nghĩa UTF-8 và Java release rõ ràng.
- Bật `showWarnings=true`.
- Chọn một số lint có giá trị cao: `deprecation`, `unchecked`, `rawtypes`.
- Cho developer quan sát warnings nhưng chưa bắt buộc build fail khi đang xử lý nợ kỹ thuật.

Với POM mẫu, đó là hành vi khi chạy `mvn clean verify` mà không có `failOnWarning=true`.

### 13.2. Mức CI nghiêm ngặt

- Dùng cùng JDK và plugin versions được ghim.
- Bật `maven.compiler.failOnWarning=true` hoặc `-Werror` có kiểm soát.
- Không bỏ qua test chỉ để build không có warnings.
- Khi JDK/plugin update làm xuất hiện lint mới, review nguyên nhân và cập nhật chính sách có chủ đích.
- Nếu trong quá trình chuyển đổi, tạm áp dụng strict cho module đã sạch và có kế hoạch nâng độ phủ cho phần còn lại.

Một lệnh CI minh họa:

```bash
mvn -B -ntp -Dmaven.compiler.failOnWarning=true clean verify
```

Đây là một CLI policy cho Compiler Plugin. Nó **không làm warnings của mọi plugin khác** (test runner, resources, checkstyle, dependency analyzer, linter) tự trở thành compilation errors. Nếu muốn CI kiểm soát cả các tầng đó, cần công cụ/goal và ngưỡng chất lượng riêng.

### 13.3. Định nghĩa strict mode thành Maven profile

Nếu tổ chức cần tùy chọn lặp lại có tên, có thể bổ sung profile **tùy chọn** sau vào `pom.xml` cùng cấp với `build` (không có trong POM chạy được ở mục 9):

```xml
<profiles>
    <profile>
        <id>strict-compiler</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <configuration>
                        <showWarnings>true</showWarnings>
                        <failOnWarning>true</failOnWarning>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

Đoạn này **không phải POM độc lập**. Khi được thêm vào POM mẫu và profile active, Maven ghép cấu hình plugin theo luật model. Chạy:

```bash
mvn -Pstrict-compiler clean verify
```

Đây là cách chính sách trở nên rõ ràng trong mã nguồn, tránh lệ thuộc vào việc nhớ một cờ CLI ở từng máy. Nếu dùng parent POM, có thể quản lý chung plugin version và chính sách rồi cho module tiêu thụ kích hoạt một cách phù hợp.

## 14. Annotation processors, compiler options và những giới hạn nâng cao

Nhiều dự án sử dụng annotation processing (ví dụ sinh mã hoặc metadata). Những công cụ này làm cho quá trình compile có thêm một tập đầu vào và warnings riêng.

Điểm cần phân biệt:

- Một thư viện annotation trong `dependencies` không luôn đồng nghĩa annotation processor được cấu hình đúng.
- Tham số `-Akey=value` truyền option cho processor có hỗ trợ; không phải property Maven và không tự có tác dụng nếu processor không đọc nó.
- Processor có thể sinh source ở `target/generated-sources/annotations`; nếu file sinh ra dùng encoding hoặc JDK API khác, cần kiểm tra toolchain/processor.
- JDK và Maven Compiler Plugin phiên bản khác nhau có thể thay đổi mặc định processor discovery hoặc cách bật processing.
- Nếu dự án dùng `--release 17`, annotation processor thường chạy bằng compiler JDK thực tế; không nên nhầm processor runtime với version của source output.

Đối với những vấn đề này, đọc tài liệu của **đúng phiên bản Maven Compiler Plugin và JDK đang dùng**. Không copy các cờ annotation processing từ JDK 23 hoặc mới hơn sang JDK 17 rồi giả định tương thích.

### 14.1. Khi nào cần fork compiler?

Maven Compiler Plugin thường dùng compiler API của JDK. `<fork>true</fork>` yêu cầu chạy compiler theo kiểu process riêng; khi đó có thể cấu hình đường dẫn `<executable>` hoặc những `-J` options phù hợp.

Ví dụ **chỉ minh họa**, không cần thêm vào POM lab:

```xml
<configuration>
    <fork>true</fork>
    <executable>/opt/jdks/jdk-17/bin/javac</executable>
    <compilerArgs>
        <arg>-Xlint:deprecation</arg>
    </compilerArgs>
</configuration>
```

Đường dẫn `/opt/jdks/jdk-17/bin/javac` **không phải đường dẫn có trên mọi máy**. Đừng viết cứng nó trong POM dùng chung nếu tổ chức chưa chuẩn hóa môi trường. Maven Toolchains thường phù hợp hơn khi cần chọn JDK nhất quán giữa developer và CI.

Một cờ liên quan JVM như `-J-Xmx...` chỉ có tác dụng trong ngữ cảnh compiler fork được hỗ trợ; không dùng nó như cách thay `MAVEN_OPTS` hoặc cấu hình memory của ứng dụng runtime.

## 15. Cảnh báo của javac và thông tin debug khác nhau

Một số tùy chọn thường được xem cùng nhau nhưng không cùng chức năng:

| Tùy chọn | Ý nghĩa | Không nên nhầm với |
| --- | --- | --- |
| `-Xlint:deprecation` | Cảnh báo chi tiết sử dụng API deprecated | Nâng tất cả warnings thành lỗi |
| `-Xlint:unchecked` | Kiểm tra thao tác generic unchecked | Static analysis toàn diện |
| `-Xlint:rawtypes` | Phát hiện raw generic types | Lỗi cú pháp bắt buộc |
| `-Werror` | Compiler fail khi có warning | Tự sửa code gây warning |
| `-parameters` | Lưu tên parameter của method/constructor cho reflection | `-g` debug symbol |
| `-g` | Sinh thông tin debug (theo các tùy chọn tương ứng) | Giữ mọi tên parameter cho reflection |
| `-encoding UTF-8` | Cách đọc file source | Cách ghi `System.out` ở mọi terminal |
| `--release 17` | Java language/API/class-file target | Tự đổi JVM runtime hoặc download JDK |
| `-Xmaxwarns 100` | Giới hạn số warning được trình bày | Giải quyết warning bị ẩn |
| `-Xlint:all` | Bật tập lint rộng trên compiler hiện tại | Kiểm soát mọi vấn đề code quality |

Một compiler warning có thể được chuyển thành build failure nhưng **không phải mọi code smell đều tạo compiler warning**. Các nhóm có thể cần thêm Checkstyle, SpotBugs, Error Prone hoặc công cụ tương đương, với policy riêng tùy dự án. Tránh nói rằng `-Werror` sẽ phát hiện mọi lỗi logic hoặc lỗ hổng bảo mật.

## 16. Gỡ lỗi encoding: từ byte nguồn tới console

Khi gặp triệu chứng chữ tiếng Việt sai, hãy xác định **chỗ nào sai trước tiên**:

### 16.1. Source Java không compile

Ví dụ compiler báo illegal character hoặc unmappable character khi đọc `.java`. Kiểm tra:

1. Editor thật sự lưu file ở encoding nào?
2. POM có `project.build.sourceEncoding=UTF-8` không?
3. Maven Compiler Plugin có nhận `encoding=UTF-8` không?
4. File có BOM hoặc byte không hợp lệ đối với compiler/encoding không?
5. Đã thử `mvn clean compile` để buộc biên dịch lại chưa?

Nếu nguồn được lưu bằng encoding khác, chuyển mã bằng công cụ đáng tin rồi lưu lại; không thay vì đổi POM sang encoding cũ cho cả dự án một cách vội vàng.

### 16.2. Source compile đúng, resource đọc sai

Nếu `Greeting.greet("Hà Nội")` pass nhưng `App.loadMotto()` không đúng:

- Kiểm tra byte của `src/main/resources/motto.txt`.
- Kiểm tra `target/classes/motto.txt` có tồn tại không.
- Xác định resources đang được copy hay filtering.
- Xác định chương trình đọc bằng UTF-8 hay charset mặc định/ISO-8859-1.
- Nếu dùng `.properties`, kiểm tra API load cụ thể thay vì giả định giống file `.txt`.

Đừng cố sửa `javac -encoding` khi lỗi thực ra nằm ở cách ứng dụng nạp resource.

### 16.3. Tests đúng, console hiển thị sai

Nếu toàn bộ assertions về Unicode PASS nhưng terminal in ký tự méo:

- Kiểm tra terminal hỗ trợ Unicode và font cần thiết không.
- Trên Windows, kiểm tra cấu hình console/terminal và những quy ước encoding đang dùng.
- Nếu output được redirect vào file/log, kiểm tra encoding mà hệ thống logging hoặc lệnh đọc file sử dụng.
- Không thay source/encoding đúng chỉ vì một console cụ thể không hiển thị được ký tự Nhật.

Kết luận phải dựa vào **Unicode string/test** và **byte thực tế ở đầu ra** khi cần, không chỉ dựa vào ảnh chụp terminal.

## 17. Gỡ lỗi tham số javac và cảnh báo

Những lệnh chẩn đoán có ích:

```bash
mvn -version
mvn help:effective-pom
mvn help:active-profiles
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail
mvn -X clean compile
```

Cách đọc:

- `mvn -version`: JDK/Maven đang chạy.
- `help:effective-pom`: config sau khi kết hợp parent, profiles, pluginManagement và cấu hình hiện tại.
- `help:active-profiles`: profile nào đang thực sự tham gia build.
- `help:describe`: tham số goal, kiểu dữ liệu, user properties.
- `mvn -X clean compile`: log chi tiết để xác nhận configuration/compiler mode; không nên gửi công khai nếu có đường dẫn, biến môi trường hoặc thông tin nhạy cảm.

**Tại sao cần `clean` khi debug warnings?** Build tăng dần có thể bỏ qua biên dịch lại file không đổi, khiến warning đã có không xuất hiện trong lần chạy. `clean compile` giúp kiểm tra có chủ đích, nhưng không nên dùng xóa cache Maven `~/.m2/repository` để “buộc warnings xuất hiện”.

### Bảng lỗi nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `error: unmappable character for encoding ...` | Source file được lưu theo mã khác với compiler | Chuyển file sang UTF-8 đúng, đồng bộ POM/editor |
| `release version 17 not supported` | Compiler JDK quá cũ | Chọn JDK hỗ trợ release 17, kiểm tra toolchains |
| `invalid flag: -Xlint:...` | Cờ không phù hợp compiler/JDK hoặc truyền token sai | Tra tài liệu javac thật, sửa `compilerArgs` |
| `invalid target release` | Compiler không hỗ trợ target yêu cầu | Kiểm tra JDK và `--release` |
| Chữ tiếng Việt trong resource sai | File/resource encoding hoặc runtime Reader không khớp | Kiểm tra resources plugin, file bytes, `StandardCharsets.UTF_8` |
| Test PASS nhưng console méo chữ | Terminal/console encoding hoặc font | Kiểm tra cấu hình terminal, đừng đổi source encoding bừa |
| `@Deprecated` không tạo warning | Chưa bật lint tương ứng, không compile lại hoặc warning bị suppress | Bật `-Xlint:deprecation`, chạy `mvn clean compile` |
| Có warning nhưng `BUILD SUCCESS` | Chưa có strict policy | Cân nhắc `failOnWarning=true` |
| Bật `-Werror` rồi build fail trên JDK mới | Lint mới hoặc dependency/JDK thay đổi | Phân loại và sửa warnings, khóa toolchain |
| `-Dmaven.compiler.failOnWarning=true` không như mong đợi | POM/profile có cấu hình tường minh hoặc goal khác | Kiểm tra effective POM, user property và plugin goal |
| `-parameters` không hiện trong reflection | Config không áp dụng execution thực tế hoặc class chưa build lại | `mvn clean verify`, kiểm tra class và compiler options |
| Compiler warnings khác giữa main/test | Hai executions/configurations hoặc bộ nguồn khác nhau | Xem `compile` so với `testCompile`, effective POM |
| Test warnings bị “mất” sau khi dùng skip | Lệnh skip có thể không compile/run test theo chính sách | Đừng dùng skip thay cho QA, xem goal vẫn được thực thi không |
| Dự án cũ có rất nhiều raw/unchecked warnings | Nợ kỹ thuật, API legacy hoặc generics chưa đầy đủ | Lập kế hoạch sửa, suppress hạn chế khi chứng minh an toàn |
| `BUILD SUCCESS` dù có vấn đề logic | Compiler không phải static analyzer toàn năng | Thêm tests và công cụ quality phù hợp |

## 18. Checklist trước khi đưa cấu hình compiler vào CI

Một bộ tiêu chí review rõ ràng:

1. Các file `.java`, POM và tài nguyên văn bản được lưu bằng encoding đã chọn, thông thường UTF-8.
2. POM khai báo `project.build.sourceEncoding=UTF-8` và những plugin đọc/ghi text có cấu hình phù hợp.
3. Java release được ghim bằng `--release` hoặc property `maven.compiler.release`.
4. JDK compiler thực tế đáp ứng release; toolchains và runner được quản lý rõ ràng.
5. Maven Compiler Plugin có version cố định và `compilerArgs` chỉ chứa cờ được hỗ trợ trên JDK mục tiêu.
6. Không truyền trùng những tham số đã có cấu hình plugin nếu không có lý do cụ thể.
7. Chính sách `showWarnings`, `showDeprecation`, `-Xlint` và `failOnWarning` được hiểu đúng, không mâu thuẫn.
8. Build sạch `mvn clean verify` chạy đầy đủ test, không skip ngầm.
9. Nếu strict mode được bật, các warning phát sinh đã được sửa hoặc có ngoại lệ được review chứ không chỉ che log.
10. Bài kiểm chứng UTF-8 kiểm tra cả source Java và resource bytes qua runtime Reader.
11. Kết quả output được thử trên môi trường thật, phân biệt lỗi console với lỗi compiler.
12. Sau khi nâng JDK/Compiler Plugin, CI lặp lại QA và review những loại diagnostics mới.

Đối với nhóm nhiều module, có thể để policy chung ở parent POM qua `pluginManagement` rồi đảm bảo những modules cần thiết sử dụng đúng plugin configuration. Nhưng phải kiểm tra **effective POM tại module** vì chỉ khai báo plugin trong pluginManagement không tự tạo execution tùy ý cho mọi project.

## 19. Bài tập tự kiểm tra

1. Vì sao `project.build.sourceEncoding=UTF-8` không tự sửa một file Java đã được editor lưu sai encoding? Bạn sẽ kiểm tra byte và chuyển mã bằng cách nào?
2. So sánh chức năng của `project.build.sourceEncoding` và `project.reporting.outputEncoding`. Tham số nào thật sự truyền cho `javac`?
3. Chạy `mvn clean verify` trong dự án lab, xác nhận **4 test** pass và chạy `java -cp target/classes dev.learn.App`; ghi chính xác hai dòng stdout.
4. Vì sao `GreetingTest.retainsParameterNameForReflection` cần compiler flag tương ứng với `-parameters`?
5. Bỏ `<parameters>true</parameters>` khỏi POM, chạy `mvn clean test` và giải thích vì sao bài test dùng reflection có thể thất bại. Khôi phục cấu hình.
6. Phân biệt `--release 17` với `-source 17 -target 17` khi dùng JDK mới hơn để compile cho runtime Java 17.
7. Trong `compilerArgs`, tại sao `-Xmaxwarns` và `100` nên là hai `<arg>`? Lựa chọn nào phù hợp khi muốn bật warnings về deprecation?
8. Thêm `LegacyMethods` và `WarningDemo` theo mục 10. So sánh `mvn clean verify` với `mvn -Dmaven.compiler.failOnWarning=true clean verify`. Vì sao build strict fail dù code Java vẫn đúng cú pháp?
9. Nếu codebase xuất hiện 300 warnings, liệu `-Xmaxwarns 100` có “sửa” được 200 warnings còn lại không? Trình bày cách quản lý nợ kỹ thuật.
10. Một developer dùng `@SuppressWarnings("unchecked")` trên cả package để đạt strict build. Bạn sẽ yêu cầu chứng minh điều gì trước khi chấp nhận?
11. Nếu `mvn compile` pass trên laptop nhưng báo `release version 17 not supported` ở CI, hãy nêu những câu lệnh và cấu hình cần đối chiếu.
12. Vì sao `-Dfile.encoding=UTF-8` không thể thay tất cả cấu hình `encoding` của source, resources và runtime I/O?
13. Một build dùng `-Werror` nhưng có warning của Checkstyle Plugin. Maven Compiler Plugin có tự biến tất cả những cảnh báo của plugin khác thành lỗi không? Cần cấu hình điều gì thêm?
14. Khi dùng Compiler Plugin trong parent POM, làm sao kiểm chứng options cuối cùng cho module con và cho cả compile/testCompile?
15. Khi terminal không hiển thị được chữ Nhật nhưng `GreetingTest.readsUtf8Resource` pass, bạn sẽ kiểm tra tầng nào trước?

## 20. Tóm tắt

**Encoding, tham số javac và chính sách warnings là ba nhiệm vụ liên quan nhưng phải quản lý riêng.**

- **UTF-8** trong POM giúp Maven Compiler Plugin đọc Java source nhất quán; các resources và runtime I/O vẫn cần đúng charset ở tầng của chúng.
- **`--release 17`** quy định phiên bản Java Platform mục tiêu, không tự cài/đổi JDK của máy.
- **`compilerArgs`** chuyển các options cụ thể cho javac; không nên dùng để lặp lại tất cả tham số plugin đã hỗ trợ.
- **`-Xlint`** bật nhóm cảnh báo quan tâm; **`showWarnings`** quyết định hiển thị; **`failOnWarning` hoặc `-Werror`** có thể buộc build thất bại khi có warning.
- **CI strict** chỉ có ích khi có nền tảng JDK/plugin được ghim và một quy trình xử lý warnings thật sự.
- **Kiểm chứng** bằng `mvn clean verify`, unit tests Unicode, reflection về tên parameter, đọc resource UTF-8 và thử một warning deprecated có kiểm soát.

## 21. Nguồn tham khảo chính thức

- [Apache Maven Compiler Plugin 3.14.1 — compiler:compile và danh sách tham số](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.1/compile-mojo.html)
- [Apache Maven Compiler Plugin — Pass Compiler Arguments](https://maven.apache.org/plugins/maven-compiler-plugin/examples/pass-compiler-arguments.html)
- [Apache Maven Compiler Plugin — Setting the --release Option](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Apache Maven Compiler Plugin — compiler:testCompile](https://maven.apache.org/plugins/maven-compiler-plugin/testCompile-mojo.html)
- [Apache Maven Resources Plugin 3.3.1 — Character Encoding](https://maven.apache.org/plugins-archives/maven-resources-plugin-3.3.1/examples/encoding.html)
- [Apache Maven Resources Plugin — Filtering Properties Files](https://maven.apache.org/plugins/maven-resources-plugin/examples/filtering-properties-files.html)
- [Oracle Java 17 — javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
