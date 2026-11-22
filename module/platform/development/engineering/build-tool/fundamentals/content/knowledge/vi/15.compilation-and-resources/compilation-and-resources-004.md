# Encoding và các lựa chọn biên dịch ảnh hưởng đến kết quả

Một dự án Java có thể biên dịch thành công trên máy này nhưng tạo ra kết quả khác trên máy khác. Nguyên nhân không chỉ nằm ở mã nguồn: compiler có thể đọc file bằng encoding khác nhau, chọn mức Java khác nhau, dùng annotation processor khác phiên bản hoặc ghi metadata khác vào bytecode. Các tài nguyên đi kèm như YAML, properties, XML, template và file văn bản cũng có thể bị đọc hoặc xử lý bằng charset không thống nhất.

Để build ổn định, cần kiểm soát hai nhóm yếu tố. **Encoding** quyết định cách byte trong file được diễn giải thành ký tự và cách ký tự được ghi trở lại thành byte. **Compiler options** quyết định ngôn ngữ Java, API nền tảng, bytecode, metadata và các kiểm tra được áp dụng trong quá trình biên dịch. Những lựa chọn này nên được khai báo trong build để terminal, IDE và CI dùng cùng một quy tắc.

## 1. Encoding là gì?

Máy tính lưu file dưới dạng byte. Một file văn bản cần một quy ước để ánh xạ các byte đó thành ký tự. Quy ước này gọi là **character encoding** hoặc **charset**.

Ví dụ, cùng một ký tự có dấu có thể được biểu diễn bằng các chuỗi byte khác nhau tùy encoding. Nếu file được lưu bằng UTF-8 nhưng compiler đọc như Windows-1252 hoặc một charset khác, chuỗi byte có thể bị diễn giải sai. Kết quả thường là ký tự bị biến thành dấu hỏi, ký tự lạ hoặc lỗi biên dịch do một phần mã nguồn không còn hợp lệ.

### 1.1. Phân biệt character set và encoding

- **Character set** mô tả tập ký tự và các mã số tương ứng.
- **Encoding** mô tả cách mã hóa các ký tự đó thành byte và giải mã byte thành ký tự.

Trong thực tế, các tên như UTF-8, UTF-16 và Windows-1252 thường được gọi chung là encoding/charset. Khi cấu hình Java, ta thường truyền tên charset mà JVM hoặc compiler hỗ trợ.

### 1.2. UTF-8

UTF-8 là encoding Unicode có độ dài biến đổi: một ký tự được mã hóa bằng một đến bốn byte. UTF-8 tương thích với ASCII ở vùng ký tự ASCII, được sử dụng rộng rãi trong source code, tài liệu, API và repository hiện đại.

Với dự án Java mới, UTF-8 thường là lựa chọn mặc định hợp lý cho source và resource văn bản. Tuy vậy, không nên dựa vào mặc định của máy hoặc JDK. Hãy khai báo rõ encoding trong build và dùng API Java nhận charset tường minh khi đọc/ghi file.

### 1.3. Vì sao encoding không thống nhất gây lỗi?

Giả sử file `Greeting.java` được lưu dưới dạng UTF-8 và chứa:

```java
public class Greeting {
    public static void main(String[] args) {
        System.out.println("Xin chào, thế giới!");
    }
}
```

Nếu compiler đọc file bằng UTF-8, các ký tự tiếng Việt được giải mã đúng. Nếu compiler đọc cùng byte bằng một encoding khác, phần literal có thể bị sai. Mã nguồn ASCII thuần có thể vẫn biên dịch bình thường, nên lỗi đôi khi chỉ xuất hiện sau khi thêm comment, string literal hoặc identifier có ký tự ngoài ASCII.

Encoding sai cũng có thể không gây lỗi compile. Compiler có thể đọc ra các ký tự sai nhưng vẫn hợp lệ về cú pháp, khiến chuỗi được ghi vào class file đã sai ngay từ đầu. Vì thế, “build xanh” không đủ chứng minh nội dung văn bản đã được xử lý đúng.

## 2. Encoding của source code, resource và dữ liệu runtime là ba việc riêng

Một dự án Java có nhiều điểm đọc/ghi văn bản. Cần xác định encoding ở từng điểm thay vì giả định một thiết lập duy nhất tự động áp dụng cho tất cả.

| Thành phần | Ví dụ | Encoding cần quan tâm |
|---|---|---|
| Java source | `src/main/java/*.java` | Charset compiler dùng để đọc file source |
| Generated source | Java file do generator/annotation processor tạo | Encoding khi generator ghi file và compiler đọc file |
| Resource | YAML, XML, JSON, template, SQL, `.properties` | Encoding của bước copy/filter và cách ứng dụng đọc resource |
| File cấu hình bên ngoài | `config/application.yml` | Charset được API hoặc framework dùng khi đọc file |
| Standard input/output | Terminal log, console | Encoding của tiến trình, terminal và hệ điều hành |
| HTTP/message payload | JSON, XML, CSV | Charset trong protocol/header và cách client/server decode |
| Database | Text column | Encoding của database, connection và driver |

Ví dụ, cấu hình `javac -encoding UTF-8` chỉ nói cho compiler cách đọc Java source. Nó không tự chuyển một file `application.yml` sang UTF-8, không thay đổi encoding của database và không quyết định cách một ứng dụng khác đọc file cấu hình ở runtime.

## 3. Encoding khi biên dịch Java source

Java compiler `javac` có tùy chọn `-encoding` để chỉ định charset dùng khi đọc file nguồn.

```bash
javac -encoding UTF-8 Greeting.java
```

Nếu không chỉ định `-encoding`, compiler dùng charset mặc định của môi trường theo hành vi của JDK. Từ JDK 18, JEP 400 chuẩn hóa default charset của Java thành UTF-8 trên hầu hết môi trường, trừ khi có cấu hình tương thích đặc biệt. Dự án vẫn nên khai báo encoding tường minh để thể hiện ý định và tránh phụ thuộc vào JDK hoặc thiết lập cũ.

### 3.1. Encoding trong Gradle

Với Gradle Java plugin, cấu hình `options.encoding` cho các task `JavaCompile`:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Nếu dùng Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

Thiết lập này áp dụng cho các task biên dịch Java phù hợp với cấu hình. Trong build nhiều module, có thể đặt cấu hình trong convention plugin hoặc build logic dùng chung để tránh mỗi module tự khai báo khác nhau.

### 3.2. Encoding trong Maven

Maven thường dùng property `project.build.sourceEncoding` làm encoding chuẩn của project. Maven Compiler Plugin có tham số `encoding`; khi không cấu hình riêng, các phiên bản plugin phổ biến sử dụng property này làm giá trị mặc định.

Ví dụ:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Có thể cấu hình rõ trong Maven Compiler Plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <encoding>${project.build.sourceEncoding}</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Version plugin ở ví dụ là minh họa; dự án nên dùng phiên bản đã được kiểm thử và quản lý tập trung. Việc pin plugin version cũng quan trọng vì hành vi và tùy chọn có thể khác giữa các phiên bản.

### 3.3. Kiểm tra encoding thực tế

Khi nghi ngờ compiler đang đọc source sai, hãy kiểm tra:

- Encoding mà editor dùng để mở và lưu file.
- Encoding khai báo trong Gradle/Maven build.
- Phiên bản JDK và charset mặc định của tiến trình.
- File có BOM hoặc byte không hợp lệ hay không.
- Generated source có được ghi cùng encoding với compiler không.

Trong Java, có thể in charset mặc định để chẩn đoán:

```java
import java.nio.charset.Charset;

public class CharsetInfo {
    public static void main(String[] args) {
        System.out.println(Charset.defaultCharset());
    }
}
```

Đây là thông tin môi trường runtime. Nó không thay thế việc xem `options.encoding` hoặc compiler argument được truyền trong build.

## 4. Encoding của resource và quá trình filtering

Java plugin thường copy resource từ `src/main/resources` vào output của source set, sau đó đưa chúng vào JAR. Việc copy file nhị phân như ảnh, font hoặc PDF khác với việc đọc và thay thế placeholder trong file văn bản.

### 4.1. Gradle `processResources`

Nếu chỉ copy resource mà không biến đổi nội dung, Gradle có thể giữ nguyên byte của file. Nếu sử dụng filtering hoặc token expansion, task cần biết charset để decode văn bản trước khi thay thế rồi encode lại.

Ví dụ:

```groovy
tasks.withType(ProcessResources).configureEach {
    filteringCharset = 'UTF-8'
}
```

`filteringCharset` có ý nghĩa khi resource được xử lý bằng filter/expansion. Nó không phải một lệnh chuyển đổi mọi file trong thư mục resource. Nếu project dùng `expand(...)`, `filter(...)` hoặc một filter tùy chỉnh, hãy cấu hình encoding tương ứng và kiểm tra output thực tế.

Ví dụ một resource được lọc:

```groovy
tasks.named('processResources') {
    filesMatching('application.properties') {
        expand(version: project.version)
    }
}
```

Nếu file có ký tự ngoài ASCII, hãy đảm bảo `filteringCharset` được đặt đúng. Không áp dụng text filtering lên file nhị phân như `.png`, `.jpg`, `.woff` hoặc `.pdf`; thao tác decode/encode có thể làm hỏng nội dung.

### 4.2. Maven Resources Plugin

Maven Resources Plugin xử lý việc copy resource và có thể filtering placeholder. Property `project.build.sourceEncoding` thường được dùng làm encoding của resource; có thể cấu hình rõ trong plugin:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-resources-plugin</artifactId>
            <version>3.3.1</version>
            <configuration>
                <encoding>${project.build.sourceEncoding}</encoding>
                <nonFilteredFileExtensions>
                    <nonFilteredFileExtension>png</nonFilteredFileExtension>
                    <nonFilteredFileExtension>jpg</nonFilteredFileExtension>
                    <nonFilteredFileExtension>pdf</nonFilteredFileExtension>
                </nonFilteredFileExtensions>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Danh sách extension cần điều chỉnh theo tài nguyên thực tế. Những file nhị phân nên được loại khỏi filtering. Nếu không cần thay placeholder trong resource, có thể tắt filtering để giữ nguyên byte.

### 4.3. `.properties` và quy tắc Unicode

File Java properties có lịch sử encoding đặc biệt. API `Properties.load(InputStream)` diễn giải byte theo ISO-8859-1 và dùng escape Unicode cho các ký tự ngoài phạm vi đó. Trong khi đó, `Properties.load(Reader)` dùng ký tự mà Reader đã giải mã, vì vậy ứng dụng có thể chủ động đọc UTF-8:

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class ReadProperties {
    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();
        try (Reader reader = Files.newBufferedReader(
                Path.of("messages.properties"), StandardCharsets.UTF_8)) {
            properties.load(reader);
        }
        System.out.println(properties.getProperty("greeting"));
    }
}
```

Không nên giả định mọi thư viện hoặc framework đều dùng cùng cách đọc properties. Kiểm tra API cụ thể và phiên bản framework. Với file properties truyền thống cần tương thích với `load(InputStream)`, có thể dùng escape Unicode theo quy tắc của Java properties.

## 5. Encoding khi đọc và ghi file ở runtime

Ngay cả khi source và resource được biên dịch đúng, ứng dụng vẫn có thể đọc sai file bên ngoài nếu dùng API phụ thuộc charset mặc định.

Nên chỉ định charset tường minh với Java NIO:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path input = Path.of("data", "customers.txt");
String content = Files.readString(input, StandardCharsets.UTF_8);

Path output = Path.of("build", "customers-copy.txt");
Files.writeString(output, content, StandardCharsets.UTF_8);
```

Khi dùng `InputStreamReader` hoặc `OutputStreamWriter`, truyền charset rõ ràng:

```java
try (var reader = new java.io.InputStreamReader(
        Files.newInputStream(input), StandardCharsets.UTF_8)) {
    // Đọc văn bản đã giải mã.
}
```

Điều này giúp kết quả nhất quán giữa các hệ điều hành và cấu hình locale. Nếu dữ liệu đến từ HTTP, CSV hoặc hệ thống bên ngoài, cần tuân theo charset được quy định bởi format/protocol thay vì mặc định ép mọi dữ liệu thành UTF-8.

### 5.1. Default charset và JDK

Từ JDK 18, default charset của Java được chuẩn hóa thành UTF-8 theo JEP 400 trong hầu hết trường hợp. Điều này giảm khác biệt giữa các hệ điều hành so với các JDK cũ, nhưng không làm cho mọi API tự động biết encoding của file bên ngoài.

Một số API có overload nhận charset, một số API cũ dùng default charset hoặc có quy tắc riêng. Hãy ưu tiên overload nhận `Charset`/`CharsetDecoder`/`CharsetEncoder` khi làm việc với file hoặc stream văn bản. Đối với API không hỗ trợ charset, cần hiểu chính xác contract của nó.

### 5.2. Unicode normalization

Unicode cho phép một số ký tự hiển thị giống nhau được biểu diễn bằng các chuỗi code point khác nhau. Ví dụ, một ký tự có dấu có thể được mã hóa thành một code point dựng sẵn hoặc một chữ cái cộng dấu kết hợp. Hai chuỗi có thể trông giống nhau nhưng không bằng nhau khi so sánh trực tiếp.

Nếu dữ liệu cần so sánh/đối chiếu ổn định, có thể chuẩn hóa bằng `java.text.Normalizer` theo quy tắc nghiệp vụ:

```java
import java.text.Normalizer;

String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
```

Không nên tự ý normalize mọi dữ liệu mà không hiểu yêu cầu. Việc này có thể ảnh hưởng identifier, chữ ký số, checksum hoặc dữ liệu cần giữ nguyên byte. Encoding chuyển byte thành ký tự; normalization thay đổi dạng biểu diễn Unicode ở mức ký tự. Đây là hai thao tác khác nhau.

## 6. Các lựa chọn biên dịch cơ bản: `source`, `target` và `release`

Compiler options có thể thay đổi ngôn ngữ được chấp nhận, bytecode được tạo và API Java mà mã nguồn có thể sử dụng.

### 6.1. `-source`

`-source` chỉ định phiên bản cú pháp/ngôn ngữ Java mà compiler chấp nhận. Ví dụ, nếu đặt source level thấp hơn, compiler có thể từ chối cú pháp mới được thêm vào các phiên bản Java sau.

### 6.2. `-target`

`-target` chỉ định mức phiên bản class file/bytecode mà compiler tạo. Tuy nhiên, chỉ đặt `-source` và `-target` không tự giới hạn đầy đủ Java API mà source có thể gọi. Một mã nguồn có thể dùng API chỉ tồn tại ở JDK mới nhưng vẫn được biên dịch với target thấp hơn, dẫn đến lỗi `NoSuchMethodError` hoặc `ClassNotFoundException` khi chạy trên runtime cũ.

### 6.3. `--release`

Từ JDK 9, `javac --release N` là cách được khuyến nghị để biên dịch hướng đến một Java release cụ thể. Nó kết hợp:

- Mức ngôn ngữ Java được chấp nhận.
- Mức bytecode/class file được tạo.
- Tập API Java SE được phép sử dụng cho release mục tiêu.

Ví dụ:

```bash
javac --release 17 -encoding UTF-8 Greeting.java
```

Nếu build dùng JDK 21 nhưng đặt `--release 17`, compiler kiểm tra source theo Java 17 và API Java 17, đồng thời tạo class file tương thích với release đó. Đây là cách phù hợp khi muốn dùng JDK mới để build nhưng cần sản phẩm chạy trên Java 17.

`--release` không thể dùng để biên dịch nhắm tới release cao hơn JDK compiler đang chạy. Ví dụ, JDK 17 không thể dùng `--release 21`.

### 6.4. Khi nào còn dùng `source` và `target`?

Các dự án cũ hoặc toolchain cũ có thể vẫn dùng `sourceCompatibility`/`targetCompatibility` của Gradle hoặc `maven.compiler.source`/`maven.compiler.target` của Maven. Nếu JDK/compiler hỗ trợ, nên ưu tiên cấu hình release để kiểm soát API nền tảng. Khi phải hỗ trợ JDK cũ không có `--release`, cần có cách kiểm tra API tương thích riêng và tài liệu hóa giới hạn.

## 7. Cấu hình release trong Gradle

Gradle Java plugin cho phép cấu hình Java toolchain và release level. Ví dụ Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
```

Trong ví dụ, Gradle dùng compiler toolchain Java 21 nhưng tạo output hướng tới Java 17. JDK 21 cần có sẵn hoặc được provision theo chính sách toolchain của dự án.

Nếu mục tiêu của dự án là chạy trên Java 21, đặt toolchain và release tương ứng. Không sao chép version từ ví dụ mà không xét runtime baseline thực tế.

Kotlin DSL:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}
```

### 7.1. Source/target compatibility trong Gradle

Gradle cũng có các thuộc tính:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
```

Các thuộc tính này biểu diễn source/target compatibility cho Java compilation. Với JDK hiện đại, `options.release` thường là cách rõ hơn để giới hạn cả API nền tảng. Tránh đặt release và source/target theo các giá trị mâu thuẫn.

### 7.2. Dùng cùng toolchain cho compile và test

Java Toolchains giúp Gradle chọn JDK phù hợp cho các task Java được hỗ trợ, bao gồm compile và test launcher theo cấu hình. Cần phân biệt JVM chạy Gradle daemon với toolchain được chọn cho từng task. Nếu build script hoặc plugin dùng một compiler/launcher tùy chỉnh, hãy xác nhận cấu hình đó cũng tuân theo baseline dự án.

## 8. Cấu hình release trong Maven

Với Maven Compiler Plugin hiện đại, có thể khai báo `maven.compiler.release`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Hoặc cấu hình rõ trong plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>${maven.compiler.release}</release>
                <encoding>${project.build.sourceEncoding}</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Maven Compiler Plugin cần chạy bằng JDK hỗ trợ release mục tiêu. Nếu dự án cần dùng JDK khác với JDK đang chạy Maven, có thể cấu hình Maven Toolchains để chọn compiler toolchain phù hợp.

### 8.1. Vì sao cần pin plugin version?

Nếu không pin plugin version, Maven có thể chọn phiên bản plugin theo cơ chế mặc định hoặc super POM/metadata, khiến kết quả khác giữa môi trường hoặc thay đổi khi plugin resolution thay đổi. Khai báo plugin version rõ ràng giúp nhóm kiểm soát hành vi compiler, tham số được hỗ trợ và cách tích hợp với JDK.

### 8.2. Không trộn release với source/target tùy tiện

Nếu đã dùng `<release>17</release>`, không cần đặt source/target thành các mức khác nhau. Cấu hình mâu thuẫn có thể khiến plugin báo lỗi hoặc tạo kết quả không đúng ý định. Hãy chọn một baseline và dùng nó nhất quán cho mọi module.

## 9. Các compiler options ảnh hưởng đến bytecode hoặc hành vi build

Ngoài encoding và release, một số tùy chọn có thể làm thay đổi nội dung class file, khả năng reflection, debug hoặc việc build có thành công hay không.

### 9.1. `-parameters`

Mặc định, tên tham số method không nhất thiết được lưu trong class file theo dạng reflection có thể đọc. Tùy chọn `-parameters` yêu cầu compiler lưu metadata tên tham số.

Ví dụ:

```java
public class UserService {
    public void createUser(String email, int age) {
    }
}
```

Khi biên dịch có `-parameters`, reflection có thể đọc tên `email` và `age` qua `Parameter.getName()` (và `isNamePresent()` trả về true). Một số framework dùng metadata này để ánh xạ tham số controller, dependency injection hoặc binding.

Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
```

Maven:

```xml
<configuration>
    <parameters>true</parameters>
</configuration>
```

Thêm tùy chọn này có thể làm metadata trong class file khác đi. Nếu framework phụ thuộc tên tham số, hãy cấu hình nhất quán cho các module tạo class được framework đọc.

### 9.2. Debug information: `-g`

Debug information giúp debugger liên hệ bytecode với source code, dòng lệnh và biến cục bộ. `javac -g` yêu cầu tạo debug information; `-g:none` loại bỏ thông tin debug. Mức mặc định của compiler thường tạo một số debug metadata, nhưng build có thể thay đổi tùy chọn này.

Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.debug = true
}
```

Maven Compiler Plugin có cấu hình `<debug>true</debug>`. Việc bật/tắt debug information có thể thay đổi kích thước và nội dung class file, đồng thời ảnh hưởng khả năng debug production. Nó không thay đổi logic Java thông thường, nhưng là một phần của artifact được tạo.

### 9.3. `-Xlint` và `-Werror`

`-Xlint` bật các nhóm cảnh báo compiler chi tiết hơn, ví dụ deprecation, unchecked operations hoặc raw types. `-Werror` yêu cầu compiler coi warning là lỗi và làm build thất bại khi có cảnh báo thuộc phạm vi được bật.

Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll(['-Xlint:deprecation', '-Xlint:unchecked'])
}
```

Nếu muốn coi warning là lỗi:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-Werror')
}
```

Maven:

```xml
<configuration>
    <showWarnings>true</showWarnings>
    <compilerArgs>
        <arg>-Xlint:deprecation</arg>
        <arg>-Xlint:unchecked</arg>
    </compilerArgs>
</configuration>
```

`-Xlint` chủ yếu ảnh hưởng diagnostics. `-Werror` ảnh hưởng điều kiện thành công của build. Khi bật trên codebase lớn, nên xử lý warning theo lộ trình hoặc giới hạn nhóm warning để tránh biến mọi build thành một đợt sửa lỗi không kiểm soát.

### 9.4. Annotation processing

Annotation processor có thể sinh source code hoặc resource trong lúc compile. Ví dụ, processor có thể đọc annotation rồi tạo mapper, metamodel hoặc class hỗ trợ.

Compiler options và processor path ảnh hưởng kết quả sinh mã. Nếu local và CI dùng processor khác version, source được sinh ra có thể khác dù source code ban đầu giống nhau.

Với Gradle, processor nên được khai báo trong configuration `annotationProcessor`:

```groovy
dependencies {
    annotationProcessor 'com.example:code-generator:1.2.0'
    compileOnly 'com.example:code-generator-annotations:1.2.0'
}
```

Với Maven, cấu hình processor trong Maven Compiler Plugin, thường qua `annotationProcessorPaths` khi cần kiểm soát rõ processor path. Không nên để processor vô tình được tìm thấy từ classpath runtime hoặc một thư viện cục bộ không được khai báo.

Tùy chọn `-proc:none` tắt annotation processing. Nếu dự án cần processor để tạo source, bật tùy chọn này có thể làm thiếu class được sinh hoặc khiến compile thất bại. Chỉ dùng khi biết rõ module/task không cần annotation processing.

### 9.5. Preview features

Một số phiên bản Java cung cấp preview language/runtime features. Để sử dụng, compiler và JVM thường cần được chạy với tùy chọn preview tương ứng, ví dụ `--enable-preview`, gắn với release/JDK cụ thể.

Gradle cần cấu hình compiler args cho `JavaCompile` và JVM args cho test/application tương ứng. Maven cần truyền compiler args và cấu hình JVM chạy test. Preview feature không phải target Java ổn định để chạy trên bất kỳ JDK mới hơn nào; artifact phụ thuộc vào runtime có hỗ trợ preview của đúng release đó.

### 9.6. Annotation, parameter metadata và debug có thể thay đổi artifact

Hai lần compile cùng source có thể tạo class file khác nhau nếu một lần bật `-parameters`, lần kia tắt; nếu debug info khác; hoặc processor tạo metadata/source khác. Vì vậy, khi cần reproducible build hoặc so sánh checksum artifact, cần kiểm soát toàn bộ compiler options và phiên bản processor/plugin.

## 10. Compiler toolchain, JDK và compiler implementation

Kết quả compile phụ thuộc compiler thực tế được gọi. Dự án có thể dùng `javac` đi cùng JDK, hoặc một compiler implementation khác như Eclipse Compiler for Java (ECJ) thông qua plugin/cấu hình phù hợp.

Những yếu tố cần kiểm soát:

- Phiên bản JDK chạy Gradle/Maven.
- JDK toolchain dùng cho JavaCompile.
- Compiler implementation và version.
- Plugin build và phiên bản plugin.
- Annotation processor và version.
- Compiler options truyền trực tiếp hoặc được plugin thêm vào.

Gradle Java Toolchains giúp chọn JDK theo version/vendor/implementation khi cần. Maven Toolchains cho phép Maven plugin dùng toolchain được khai báo thay vì mặc định lấy JDK đang chạy Maven. Nếu chỉ kiểm tra `java -version` trong terminal, bạn mới biết một phần môi trường; hãy xem toolchain và cấu hình plugin để biết compiler thực tế.

### 10.1. `JAVA_HOME` và JDK chạy build

`JAVA_HOME` thường được dùng để xác định JDK khởi chạy Gradle/Maven. IDE có thể dùng một JDK riêng cho Gradle JVM hoặc Maven runner. CI runner cũng có thể chọn JDK bằng action/setup hoặc image.

Hãy phân biệt JDK chạy build với JDK toolchain dùng compile. Một build có thể chạy Gradle bằng JDK 21 nhưng dùng toolchain JDK 17 để compile. Điều này hợp lệ nếu phiên bản Gradle/plugin hỗ trợ JDK chạy build và toolchain mục tiêu có sẵn.

### 10.2. Toolchain giúp loại bỏ phụ thuộc vào cài đặt cục bộ

Khai báo toolchain trong build script là cách công bố yêu cầu JDK cho toàn nhóm. Mỗi máy không cần cài JDK ở cùng một đường dẫn; Gradle/Maven có thể tìm toolchain đã cài hoặc provision theo cấu hình/chính sách. Tuy nhiên, việc tự tải JDK phụ thuộc cấu hình resolver, mạng và quyền truy cập; không nên mặc định rằng mọi máy sẽ tự tải được.

## 11. Compiler options trong IDE, terminal và CI

IDE có thể cung cấp compiler settings riêng, chẳng hạn language level, annotation processing, encoding, debug hoặc compiler implementation. Nếu IDE dùng compiler nội bộ để build, các tùy chọn đó có thể không giống task Gradle/Maven.

Để giữ nhất quán:

- Đặt encoding và release trong build script/POM.
- Dùng Gradle/Maven Wrapper trong terminal và CI.
- Cấu hình IDE import build tool và delegate build/test cho Gradle/Maven khi cần xác nhận kết quả chuẩn.
- Nếu IDE có thiết lập language level hoặc compiler riêng, bảo đảm nó không mâu thuẫn với build configuration.
- Kiểm tra annotation processing và generated source trong cả IDE lẫn build tool.
- Tránh chỉ lưu compiler option quan trọng trong một Run Configuration cá nhân.

Một IDE có thể vẫn dùng compiler nội bộ cho phản hồi nhanh khi gõ code. Nhưng artifact được phát hành nên được tạo bởi quy trình build đã khai báo trong repository và được CI xác minh.

## 12. Ví dụ cấu hình Gradle đầy đủ

Ví dụ sau minh họa một dự án dùng JDK 21 để chạy build, biên dịch theo Java 17, đọc source UTF-8, lưu parameter names và bật một số warning:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
    options.compilerArgs.addAll([
        '-parameters',
        '-Xlint:deprecation',
        '-Xlint:unchecked'
    ])
}

tasks.withType(ProcessResources).configureEach {
    filteringCharset = 'UTF-8'
}
```

Trong ví dụ này:

1. Java toolchain chọn compiler JDK 21.
2. `options.release = 17` giới hạn language/API/bytecode ở Java 17.
3. `options.encoding` quy định cách compiler giải mã source file.
4. `-parameters` lưu tên tham số trong class file.
5. `-Xlint` bật các cảnh báo được chọn.
6. `filteringCharset` quy định charset cho resource filtering khi task thực sự lọc nội dung.

Nếu project không filtering resource, dòng `filteringCharset` có thể không cần thiết. Nếu dùng generated source, hãy bảo đảm generator ghi UTF-8 và được nối vào `compileJava` đúng cách.

## 13. Ví dụ cấu hình Maven đầy đủ

Ví dụ sau minh họa cấu hình Maven Compiler Plugin và Resources Plugin:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>${maven.compiler.release}</release>
                <encoding>${project.build.sourceEncoding}</encoding>
                <parameters>true</parameters>
                <debug>true</debug>
                <showWarnings>true</showWarnings>
                <compilerArgs>
                    <arg>-Xlint:deprecation</arg>
                    <arg>-Xlint:unchecked</arg>
                </compilerArgs>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-resources-plugin</artifactId>
            <version>3.3.1</version>
            <configuration>
                <encoding>${project.build.sourceEncoding}</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Ở đây `release` kiểm soát mức Java mục tiêu; `encoding` áp dụng cho compiler source; `parameters` yêu cầu lưu tên tham số; `debug` bật debug information; `showWarnings` hiển thị warning; `compilerArgs` truyền thêm javac options. Resources Plugin dùng cùng property encoding khi xử lý resource văn bản.

Khi dùng resource filtering, cần khai báo rõ resource nào được filter và loại file nhị phân nào không được filter. Không bật filtering cho toàn bộ thư mục nếu có ảnh, font, archive hoặc file binary.

## 14. Các lựa chọn khác có thể ảnh hưởng kết quả build

### 14.1. Annotation processor và generated source

Processor version thay đổi có thể sinh code khác nhau. Hãy pin version, khai báo processor path riêng và kiểm soát các option truyền vào processor. Nếu processor đọc file schema/config, khai báo chúng là input để build incremental có thể phát hiện thay đổi.

### 14.2. Compiler arguments theo môi trường

Không nên để local bật một compiler argument mà CI không bật nếu argument đó ảnh hưởng source compatibility, preview features, warning policy hoặc output. Nếu một option chỉ dành cho debug, cần đặt ở cấu hình task/profile có chủ đích và ghi rõ phạm vi.

### 14.3. Incremental compilation

Gradle có thể biên dịch tăng dần bằng cách chỉ compile phần source bị ảnh hưởng. Cơ chế này dựa trên quan hệ input/output và khả năng phân tích thay đổi. Nếu task tùy chỉnh sửa source ngoài luồng hoặc generator không khai báo output/input chính xác, incremental compile có thể không phản ánh đầy đủ thay đổi.

Khi nghi ngờ output cũ, có thể chạy `clean` để xác nhận liệu build sạch có cho kết quả khác. Tuy nhiên, `clean` không phải giải pháp lâu dài cho một task khai báo input/output sai.

### 14.4. File line ending và byte order mark

Line ending (`LF` hoặc `CRLF`) không phải encoding, nhưng có thể ảnh hưởng script, parser hoặc công cụ xử lý văn bản. BOM (Byte Order Mark) là dấu hiệu byte đầu file có thể được dùng để nhận diện encoding hoặc byte order; không phải mọi compiler/plugin đều xử lý BOM giống nhau.

Nên thống nhất line ending bằng `.gitattributes` nếu repository cần, và kiểm tra BOM khi một file văn bản không được parse như mong đợi. Đừng thay đổi byte đầu file bằng tay nếu chưa xác định format và công cụ đọc file.

### 14.5. Compiler version và reproducible output

Cùng source và cùng release level chưa chắc tạo class file byte-for-byte giống nhau nếu compiler version, processor, debug options hoặc metadata khác nhau. Nếu dự án cần so sánh checksum hoặc reproducible artifact, cần pin compiler/toolchain, plugin, processor và toàn bộ option có ảnh hưởng output. Một số thông tin build timestamp hoặc archive metadata cũng có thể làm gói cuối khác checksum dù bytecode tương đương.

## 15. Chẩn đoán lỗi encoding và compiler option

| Triệu chứng | Nguyên nhân có thể | Nơi cần kiểm tra |
|---|---|---|
| Ký tự tiếng Việt thành `?` hoặc ký tự lạ | Source/resource được decode bằng charset sai | Editor encoding, `options.encoding`, Maven source encoding, resource filtering |
| Compile báo unmappable character | Compiler không giải mã được byte theo charset đã chọn | `javac -encoding`, file encoding thực tế, generated source |
| Local compile được nhưng CI lỗi ký tự | Encoding hoặc toolchain khác nhau | Wrapper, JDK, build config, file encoding trong Git |
| Chạy trên JDK mới được nhưng JDK cũ lỗi API | Chỉ đặt source/target mà không giới hạn platform API | `--release`, toolchain và runtime baseline |
| Framework không đọc được tên tham số | Class file không có parameter metadata | `-parameters`, Maven `<parameters>` |
| Debugger không hiện local variable/line | Debug information bị tắt hoặc thiếu | `-g`, Gradle debug options, Maven `<debug>` |
| Build fail khi bật warning policy | `-Werror` hoặc warning mới từ compiler/plugin | `-Xlint`, `-Werror`, compiler version |
| Generated class khác giữa máy | Annotation processor hoặc option khác version | Processor path/version, compiler args, generated source |
| Resource trong JAR sai dấu | Resource filtering/copy dùng encoding khác | Resources Plugin, `filteringCharset`, runtime loader |
| Test chỉ lỗi trên một máy | Default charset, locale, timezone hoặc file system khác | JDK, API đọc file, environment và test data |

### 15.1. Kiểm tra byte và charset của file

Khi editor hiển thị sai, hãy xác nhận encoding thực tế của file bằng chức năng status/encoding của editor hoặc công cụ kiểm tra byte. Không đổi encoding hàng loạt chỉ dựa trên việc ký tự đang hiển thị sai; có thể editor đang decode sai một file vốn đã đúng.

Với Java, đọc file theo charset đã biết và in code point khi cần:

```java
String text = Files.readString(path, StandardCharsets.UTF_8);
text.codePoints().forEach(codePoint ->
        System.out.printf("U+%04X%n", codePoint));
```

Điều này giúp phân biệt ký tự Unicode thực tế trong chuỗi với cách terminal đang hiển thị nó.

### 15.2. Xác nhận compiler command line

Khi Gradle/Maven gọi compiler, hãy bật log đủ chi tiết hoặc kiểm tra compiler options của task để xác nhận `-encoding`, `--release`, processor path và các argument thực sự được truyền. Không chỉ nhìn file build: plugin hoặc convention plugin có thể bổ sung hoặc ghi đè tùy chọn.

Trong Gradle có thể in thông tin cấu hình task trong một task chẩn đoán hoặc xem log compile với mức chi tiết phù hợp. Với Maven, dùng `mvn -X` khi cần xem cấu hình plugin và command line; cần chú ý log debug có thể chứa đường dẫn hoặc thông tin môi trường nhạy cảm.

### 15.3. So sánh artifact sau clean build

Nếu nghi ngờ incremental output hoặc cache, chạy clean build trong cùng toolchain và so sánh class/resource trong JAR. Có thể dùng `jar tf` để xem nội dung archive và giải nén file resource để kiểm tra byte. Nếu cần so sánh checksum, bảo đảm cùng compiler, plugin, processor, debug settings và metadata đầu ra.

## 16. Nguyên tắc cấu hình cho dự án

- Chọn UTF-8 cho source và resource văn bản nếu format/hệ thống không yêu cầu charset khác.
- Khai báo encoding rõ trong Gradle/Maven; không dựa vào default charset của máy.
- Dùng API đọc/ghi file có charset tường minh.
- Tách encoding source, encoding resource và encoding dữ liệu runtime.
- Dùng `--release` hoặc cấu hình tương đương để kiểm soát ngôn ngữ, bytecode và API mục tiêu.
- Pin JDK toolchain, build plugin và annotation processor version.
- Chỉ bật compiler option khi hiểu tác động đến bytecode, metadata hoặc build outcome.
- Cấu hình IDE để đồng bộ encoding/language level và dùng build tool của project khi xác nhận build.
- Chạy cùng Wrapper và cùng lệnh build trên terminal, IDE và CI.
- Kiểm tra output thực tế khi thay đổi encoding, release hoặc compiler options.

Encoding và compiler options là một phần của đầu vào build. Encoding quyết định cách source/resource được giải mã và xử lý; release level quyết định ngôn ngữ, bytecode và API Java được phép sử dụng; các tùy chọn như `-parameters`, debug info, lint và annotation processing có thể thay đổi metadata, output hoặc điều kiện thành công. Khi những thiết lập này được khai báo rõ và dùng thống nhất trong mọi môi trường, dự án sẽ giảm lỗi ký tự, tránh vô tình dùng API vượt runtime baseline và tạo artifact dễ tái lập hơn.
