# Xử lý manifest, tài nguyên trùng và chữ ký từ JAR nguồn bằng Maven Shade và Assembly

> **Build Tool Maven · Shade và Assembly**  
> Môi trường minh họa: **Maven 3.9.x**, **Java 17**, **Maven Shade Plugin 3.6.2**, **Maven Assembly Plugin 3.8.0**, **Maven Compiler Plugin 3.14.1**. Bài hướng dẫn tập trung vào những vấn đề **thật sự xảy ra khi gộp nhiều JAR vào một uber/fat JAR** và cách kiểm chứng artifact được tạo.

## 1. Vì sao việc gộp JAR không đơn giản như copy file?

Một chương trình Java bình thường có thể chạy với nhiều JAR trên classpath:

```text
app.jar
lib/provider-alpha.jar
lib/provider-beta.jar
```

Mỗi dependency JAR sở hữu namespace ZIP entries riêng. Hai JAR có thể cùng chứa `META-INF/services/org.example.spi.GreetingProvider`, `META-INF/MANIFEST.MF`, `META-INF/NOTICE`, `reference.conf` hoặc một file `config/settings.properties`, mà không có xung đột **đường dẫn trong cùng archive**.

Khi gộp dependencies vào **một file JAR**, các entry paths đụng nhau. Một consumer tài nguyên thông thường chỉ nhận một hoặc một tập entry phụ thuộc vào cách plugin xử lý duplicate. **Giữ ngẫu nhiên một bản** có thể phá ứng dụng dù mọi `.class` đã được đóng gói.

Ví dụ:

```text
provider-alpha.jar
  META-INF/services/org.example.spi.GreetingProvider
      org.example.alpha.AlphaGreeting

provider-beta.jar
  META-INF/services/org.example.spi.GreetingProvider
      org.example.beta.BetaGreeting
```

Nếu shaded JAR chỉ còn một descriptor, `ServiceLoader` có thể tìm **một** implementation thay vì hai. Đối với một file **danh sách từng dòng**, merge nội dung có thể hợp lý; nhưng đối với `config/settings.json` hoặc XML không thể cứ nối hai documents rồi coi là hợp lệ. Đối với chữ ký JAR, **giữ byte ký nguồn** sau khi đổi manifest và contents có thể làm xác thực sai.

Ba nhóm vấn đề cần xử lý rõ ràng:

1. **Manifest**: ai quyết định `Main-Class` và metadata cuối cùng, đặc biệt khi mỗi dependency đều có manifest riêng?
2. **Tài nguyên trùng**: resource nào cần merge, giữ một bản, đổi path hoặc tách thành JAR khác?
3. **Chữ ký từ JAR nguồn**: bỏ metadata chữ ký không còn đúng với JAR đã biến đổi thế nào và khi nào phải ký lại?

Một file có thể **build thành công** mà **runtime sai**: ví dụ `java -jar` chạy được nhưng chỉ tải một trong hai service providers. Do đó phải test **artifact cuối**, không chỉ test sources trong `target/classes`.

## 2. Shade và Assembly giải quyết hai nhu cầu khác nhau

| Tiêu chí | Maven Shade Plugin | Maven Assembly Plugin |
| --- | --- | --- |
| Goal thường dùng | `shade:shade` | `assembly:single` |
| Mục tiêu chính | Tạo uber JAR, hỗ trợ đổi namespace, gộp resources có chọn lọc | Tạo gói phân phối ZIP/TAR/JAR theo descriptor |
| Gộp classes/dependencies | Có | Có, ví dụ `jar-with-dependencies` |
| Sửa manifest | `ManifestResourceTransformer` | `<archive><manifest>` qua Maven Archiver |
| Gộp `META-INF/services` | `ServicesResourceTransformer` | Descriptor built-in không cung cấp transformer tương đương |
| Gộp tài nguyên theo format | `AppendingTransformer`, `ComponentsXmlResourceTransformer`, các transformers khác | Dựa trên descriptor/processing cơ bản, không cùng bộ Shade transformers |
| Relocation package | Có | Không phải thế mạnh của Assembly |
| Bảo toàn nguyên vẹn signed dependency JARs | Không nếu unpack và shade | Có thể dùng Assembly ZIP/TAR chứa JAR gốc **không unpack** |
| Khi phù hợp | Executable fat JAR có nhiều resource/metadata phức tạp | Distribution gồm app.jar, lib, scripts và cấu hình |

Tài liệu chính thức của Apache Maven Assembly mô tả **`jar-with-dependencies` chỉ hỗ trợ uber JAR ở mức cơ bản**; khi cần nhiều kiểm soát với tài nguyên trùng, tài liệu khuyên chọn **Shade**.

Một quy trình cũng có thể dùng **cả hai ở hai mục đích tách biệt**: Shade xây `app-all.jar`, Assembly đóng một ZIP/TAR gồm `app-all.jar`, scripts, cấu hình và license files. Không nên để Shade và Assembly cùng sửa một output JAR mà không có sơ đồ artifacts rõ ràng.

## 3. Manifest: quyết định lại ý nghĩa của JAR cuối

### 3.1. Những headers quan trọng

Một manifest hợp lệ dưới `META-INF/MANIFEST.MF` có thể có:

```text
Manifest-Version: 1.0
Main-Class: org.example.app.Main
Implementation-Title: Example CLI
Implementation-Version: 1.0.0
```

Các entries cần hiểu:

- `Manifest-Version` nói về định dạng manifest, thường `1.0`.
- `Main-Class` là **fully qualified binary class name** để `java -jar` chạy. Không thêm `.java`, `.class` hay dấu `/` trong tên class.
- `Class-Path` là danh sách URL/path tương đối tới những JAR ngoài. Với **fat JAR** gộp dependencies, các entries cũ của JAR nguồn có thể thừa hoặc sai.
- `Implementation-Title`, `Implementation-Version` là metadata của package/implementation; version từ source dependency không nhất thiết là version ứng dụng.
- `Automatic-Module-Name`, `Multi-Release`, `Sealed`, các **named sections** có thể tác động module behavior, class loading hoặc signed metadata.

Nếu gộp nhiều JAR, bạn **không thể gộp mù quáng tất cả `Main-Class`**: chương trình cần một entry point rõ ràng.

### 3.2. Shade: `ManifestResourceTransformer`

Cấu hình nằm trong `<transformers>` của `maven-shade-plugin`:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
    <mainClass>org.example.app.Main</mainClass>
    <manifestEntries>
        <Implementation-Title>Example CLI</Implementation-Title>
        <Implementation-Version>${project.version}</Implementation-Version>
        <Build-Channel>training</Build-Channel>
    </manifestEntries>
</transformer>
```

**Đây là fragment**, chưa đủ để tạo JAR. Transformer này có thể cập nhật headers manifest hoặc tạo manifest của shaded output. Việc chỉ định `mainClass` rõ ràng tránh phụ thuộc thứ tự các source JARs khi chúng cũng chứa `Main-Class`.

Đối với **Maven JAR Plugin/Assembly Plugin**, cú pháp lại khác:

```xml
<archive>
    <manifest>
        <mainClass>org.example.app.Main</mainClass>
    </manifest>
</archive>
```

Cấu hình `<archive>` là **Maven Archiver** nằm dưới plugin tạo archive, không phải thay thế trực tiếp cho Shade transformer.

### 3.3. Khi nào manifest từ nguồn gây hỏng?

Một thư viện có thể chứa manifest với:

```text
Class-Path: ../lib/vendor-runtime.jar
Implementation-Version: 9.1.0
```

Khi gộp nó vào app fat JAR, directory `../lib/` có thể **không còn tồn tại**. `Implementation-Version` của vendor library cũng không tự đại diện cho app. Tương tự, Java modules/OSGi bundles có metadata cần class loader/layout khác và không tự an toàn sau fat-JAR merge.

Chính vì vậy phải kiểm tra **manifest từ artifact cuối**, không chỉ xem POM. Đối với signed source JARs cần xem cả **named manifest sections** có digest entries.

### 3.4. Chuẩn định dạng manifest

Java JAR File Specification quy định:

- Header dạng `Name: value`, sau dấu `:` có khoảng trắng.
- **Main section** đứng đầu; named sections có `Name:` và phân cách bằng dòng trống.
- Mỗi dòng vật lý không được quá **72 bytes UTF-8**, không phải 72 ký tự.
- Dòng tiếp theo của một header dài bắt đầu bằng **một dấu cách**.
- Không lặp header name trong cùng một section; thứ tự các non-version headers thường không mang ý nghĩa ưu tiên.

Vì thế, nếu `Class-Path` dài bị xuống dòng khi giải nén `MANIFEST.MF`, đừng coi các dòng continuation là paths riêng. Dùng **`java.util.jar.Manifest` hoặc `JarFile`** để đọc giá trị logic.

## 4. Tài nguyên trùng: mỗi loại cần một chiến lược

| Nhóm | Ví dụ | Cách xử lý phù hợp |
| --- | --- | --- |
| Java SPI descriptors | `META-INF/services/org.example.spi.GreetingProvider` | **ServicesResourceTransformer** |
| Danh sách từng dòng | `META-INF/demo/providers.list` | **AppendingTransformer** nếu định dạng cho phép |
| Spring metadata | `META-INF/spring.handlers`, `META-INF/spring.schemas` | AppendingTransformer/giải pháp tương ứng framework |
| Plexus metadata | `META-INF/plexus/components.xml` | **ComponentsXmlResourceTransformer** |
| ResourceBundle | `Messages.properties` và các locale variants | **ResourceBundleAppendingTransformer** |
| XML/JSON/properties khác | `settings.xml`, `app.json` | Hợp nhất theo **schema và consumer semantics**, không nối mù |
| Java classes cùng FQCN | `org/example/Util.class` | Giải quyết dependency/versions/relocation, không append bytecode |
| LICENSE/NOTICE | `META-INF/LICENSE`, `META-INF/NOTICE` | Giữ thông tin pháp lý theo license |
| Chữ ký JAR | `META-INF/*.SF`, `.RSA`, `.DSA`, `.EC`, `SIG-*` | Không giữ chữ ký nguồn như chữ ký JAR mới |

### 4.1. Java `ServiceLoader` cần merge service files

Java SPI sử dụng file có **đường dẫn đúng tên interface**:

```text
META-INF/services/org.example.spi.GreetingProvider
```

Mỗi dòng liệt kê **fully qualified provider class name**, ví dụ:

```text
org.example.alpha.AlphaGreeting
```

Khi dependency khác cùng khai báo file đó nhưng chứa:

```text
org.example.beta.BetaGreeting
```

Shade cần:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
```

Transformer này gộp các service configurations và còn có khả năng sửa class names theo **relocation** khi cần. Nếu không gộp, classes có thể nằm đủ trong JAR nhưng ServiceLoader vẫn chỉ thấy một implementation.

### 4.2. `AppendingTransformer` cho file có thể nối

Nếu format là một **danh sách từng dòng**:

```text
alpha
```

và:

```text
beta
```

trong cùng logical resource path, có thể:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/demo/providers.list</resource>
</transformer>
```

Tạo một resource chứa cả hai dòng. **Không hứa thứ tự dòng** vì thứ tự nguồn có thể khác; nếu ứng dụng cần kết quả ổn định, sắp xếp khi đọc hoặc dùng format có quy tắc ưu tiên.

**Không áp dụng** AppendingTransformer cho hai JSON objects hoặc hai XML documents khi nối hai documents tạo dữ liệu không hợp lệ. Một file properties có duplicate keys cũng có thể được parser xử lý theo precedence riêng; đừng nối mà không hiểu chính sách.

### 4.3. Các transformers khác

Theo tài liệu Shade:

- `ComponentsXmlResourceTransformer` xử lý Plexus `components.xml`.
- `XmlAppendingTransformer` dành cho một số XML resources có semantics phù hợp.
- `ResourceBundleAppendingTransformer` phục vụ resource bundles với locale.
- `ApacheLicenseResourceTransformer` và `ApacheNoticeResourceTransformer` xử lý một số trường hợp license/NOTICE, nhưng **không loại bỏ nghĩa vụ giữ attribution hợp lệ**.
- Một số bản plugin có transformers riêng cho MicroProfile, OpenWebBeans hoặc framework-specific metadata.

Tùy thư viện/framework, có thể cần packager chuyên dụng. Không thể xem một transformer giải quyết **mọi file trùng**.

### 4.4. Trùng `.class` khác trùng `.properties`

Nếu Shade in:

```text
... have some overlapping classes
```

phải xác định **các artifacts** sở hữu cùng binary class name. Có thể do hai versions cùng tồn tại trong graph, forked library, package relocation chưa đúng hoặc build không `clean` chứa artifact cũ. Tìm bằng:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Với reactor:

```bash
mvn -pl :app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Nếu thật sự cần hai libraries có classes cùng tên, cân nhắc **Shade relocations** và tests cho reflection/service files. **Không dùng AppendingTransformer để ghép hai `.class`**.

## 5. Chữ ký từ JAR nguồn: vì sao chữ ký không chuyển sang JAR mới?

Một JAR được ký có thể có:

```text
META-INF/MANIFEST.MF
META-INF/VENDOR.SF
META-INF/VENDOR.RSA
```

Các dạng chữ ký khác gồm `.DSA`, `.EC` và `SIG-*` trong `META-INF`, theo Java JAR File Specification.

Khi repackaging, các entries có thể bị đổi nội dung, tên, path hoặc manifest; dữ liệu signature/digest đã ký **không còn đại diện cho bytes của uber JAR mới**. Nếu signature metadata nguồn còn lại, runtime hoặc `jarsigner` có thể báo:

```text
java.lang.SecurityException:
Invalid signature file digest for Manifest main attributes
```

Đây là **một kiểu lỗi minh họa**, không cam kết stacktrace đúng từng chữ cho mọi JDK/JAR.

### 5.1. Lọc signature-related files trong Shade

Cấu hình theo scope artifacts được Shade xử lý:

```xml
<filters>
    <filter>
        <artifact>*:*</artifact>
        <excludes>
            <exclude>META-INF/*.SF</exclude>
            <exclude>META-INF/*.DSA</exclude>
            <exclude>META-INF/*.RSA</exclude>
            <exclude>META-INF/*.EC</exclude>
            <exclude>META-INF/SIG-*</exclude>
        </excludes>
    </filter>
</filters>
```

Ba patterns `.SF`, `.DSA`, `.RSA` xuất hiện trong ví dụ chính thức của Shade; `.EC` và `SIG-*` bổ sung từ Java JAR File Specification. Filter này **loại các file chữ ký nguồn không còn hợp lệ trong JAR mới**.

**Phân biệt cực kỳ quan trọng:** **lọc signature files không phải xác minh chữ ký; cũng không phải ký lại JAR đầu ra**. Nếu cần bảo đảm tính toàn vẹn/provenance, xác minh **source artifacts trước khi biến đổi**, rồi ký chính **artifact cuối** nếu release policy yêu cầu.

### 5.2. Tại sao không filter toàn bộ `META-INF`?

Không dùng một rule quá rộng để xóa mọi thứ dưới `META-INF`, bởi vì có thể xóa luôn:

- `META-INF/services/...` phục vụ Java SPI.
- `META-INF/LICENSE` và `META-INF/NOTICE` cần giữ theo license.
- Framework descriptors, module metadata và other runtime indexes.
- Manifest được đóng gói sau cùng.

Mục tiêu filter là **đúng các tệp không còn phù hợp**, không phải “xóa hết warnings”.

### 5.3. Digest trong manifest có thể còn sót

Signed JAR có thể chứa **named sections**:

```text
Name: org/example/SomeClass.class
SHA-256-Digest: ...
```

Sau shade, các hashes ấy có thể không còn phản ánh bytes cuối cùng. Không khẳng định filter `.SF`/`.RSA` giải quyết **toàn bộ signed-source manifest metadata**. Phải **kiểm tra manifest cuối**, đặc biệt nếu source JAR từng được ký và có digest entries. Nếu cần archive hoàn toàn mới, tạo manifest sạch/chính xác theo workflow packaging và test verification.

Nếu signed vendor JAR **bắt buộc giữ nguyên chữ ký**, thường nên **giữ nguyên JAR đó dưới `lib/`** trong một distribution ZIP/TAR thay vì unpack nó.

### 5.4. Xác minh và ký theo thứ tự đúng

Quy trình có trách nhiệm:

1. Resolve source dependencies từ repository tin cậy, pin versions.
2. Khi chính sách yêu cầu, xác minh checksums/signatures **source JAR nguyên bản**.
3. Shade/Assembly theo kế hoạch, lọc signature metadata nguồn không còn đúng.
4. Kiểm tra manifest, service descriptors, resources, classes và chạy smoke tests.
5. **Ký JAR cuối cùng** khi cần, sau bước packaging/merge cuối.
6. Dùng `jarsigner -verify` để xác minh signed artifact **cuối**, không sửa JAR sau ký.

Dùng công cụ JDK:

```bash
jarsigner -verify -verbose -certs path/to/signed.jar
```

Với JAR demo **chưa ký**, công cụ có thể báo `jar is unsigned`. Đây **không phải** kiểm chứng chữ ký PASS; cũng không tự làm demo sai nếu lab không yêu cầu signed output. Tránh cất private keys, keystore passwords trong POM hoặc source control.

## 6. Bài thực hành Java 17: hai JAR cùng khai báo service và resource

Để minh họa resource collision thực, tạo reactor **5 Maven projects**: root parent, một SPI, hai provider modules và một app:

```text
shade-overlap-demo/
├── pom.xml
├── spi/
│   ├── pom.xml
│   └── src/main/java/org/example/spi/GreetingProvider.java
├── provider-alpha/
│   ├── pom.xml
│   └── src/main/
│       ├── java/org/example/alpha/AlphaGreeting.java
│       └── resources/
│           ├── META-INF/services/org.example.spi.GreetingProvider
│           └── META-INF/demo/providers.list
├── provider-beta/
│   ├── pom.xml
│   └── src/main/
│       ├── java/org/example/beta/BetaGreeting.java
│       └── resources/
│           ├── META-INF/services/org.example.spi.GreetingProvider
│           └── META-INF/demo/providers.list
└── app/
    ├── pom.xml
    └── src/main/java/org/example/app/Main.java
```

Hai providers mỗi cái nằm trong **một JAR riêng** với resource path **giống hệt nhau** nhưng nội dung khác nhau. Vì vậy Shade phải merge chứ không đơn giản copy một file tùy ý.

Dependency graph:

```text
spi ---> provider-alpha --\
  \                         > app
   ---> provider-beta  ----/
```

`app` còn khai báo dependency trực tiếp vào `spi`. Maven reactor sẽ build các prerequisites trước app, nên từ root chỉ cần một lần `mvn clean package`.

### 6.1. Root `pom.xml` hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>shade-overlap-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>spi</module>
        <module>provider-alpha</module>
        <module>provider-beta</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.5.1</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Root vừa **aggregator** vì có `<modules>` vừa **parent** vì children khai báo `<parent>`. `pluginManagement` cố định các compiler/JAR plugin versions. Shade **chỉ được cấu hình trong app**, không ở parent `<build><plugins>` để mọi provider module vô tình shade artifacts của chính mình.

### 6.2. `spi/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.example</groupId>
        <artifactId>shade-overlap-demo</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>spi</artifactId>
    <packaging>jar</packaging>
</project>
```

### 6.3. `spi/src/main/java/org/example/spi/GreetingProvider.java`

```java
package org.example.spi;

public interface GreetingProvider {
    String id();
    String message();
}
```

Interface được chia sẻ bởi providers và consumer app; không có framework ngoài JDK. Các provider classes phải implement hai methods.

### 6.4. `provider-alpha/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.example</groupId>
        <artifactId>shade-overlap-demo</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>provider-alpha</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>spi</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

### 6.5. `provider-alpha/src/main/java/org/example/alpha/AlphaGreeting.java`

```java
package org.example.alpha;

import org.example.spi.GreetingProvider;

public final class AlphaGreeting implements GreetingProvider {
    public AlphaGreeting() {
    }

    @Override
    public String id() {
        return "alpha";
    }

    @Override
    public String message() {
        return "Hello from Alpha";
    }
}
```

Constructor public/no-arg để classpath-based Java ServiceLoader có thể khởi tạo provider đúng contract.

Hai resource files **của provider-alpha**:

`provider-alpha/src/main/resources/META-INF/services/org.example.spi.GreetingProvider`

```text
org.example.alpha.AlphaGreeting
```

`provider-alpha/src/main/resources/META-INF/demo/providers.list`

```text
alpha
```

File resource nên là UTF-8, **có newline cuối file**. Dòng service descriptor là class binary name, không phải Maven GAV hoặc đường dẫn `.class`.

### 6.6. `provider-beta/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.example</groupId>
        <artifactId>shade-overlap-demo</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>provider-beta</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>spi</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

### 6.7. `provider-beta/src/main/java/org/example/beta/BetaGreeting.java`

```java
package org.example.beta;

import org.example.spi.GreetingProvider;

public final class BetaGreeting implements GreetingProvider {
    public BetaGreeting() {
    }

    @Override
    public String id() {
        return "beta";
    }

    @Override
    public String message() {
        return "Hello from Beta";
    }
}
```

Hai resource files của **provider-beta**:

`provider-beta/src/main/resources/META-INF/services/org.example.spi.GreetingProvider`

```text
org.example.beta.BetaGreeting
```

`provider-beta/src/main/resources/META-INF/demo/providers.list`

```text
beta
```

**Chúng cố ý trùng tên file** với provider-alpha, nhưng Java classes không trùng FQCN. Đó là va chạm tài nguyên hợp lệ cần merge.

### 6.8. `app/pom.xml` đầy đủ: ba transformers và signature filters

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.example</groupId>
        <artifactId>shade-overlap-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>spi</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>provider-alpha</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>provider-beta</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>create-executable-uber-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <shadedArtifactAttached>true</shadedArtifactAttached>
                            <shadedClassifierName>all</shadedClassifierName>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <minimizeJar>false</minimizeJar>
                            <filters>
                                <filter>
                                    <artifact>*:*</artifact>
                                    <excludes>
                                        <exclude>META-INF/*.SF</exclude>
                                        <exclude>META-INF/*.DSA</exclude>
                                        <exclude>META-INF/*.RSA</exclude>
                                        <exclude>META-INF/*.EC</exclude>
                                        <exclude>META-INF/SIG-*</exclude>
                                    </excludes>
                                </filter>
                            </filters>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>org.example.app.Main</mainClass>
                                    <manifestEntries>
                                        <Implementation-Title>Shade Overlap Demo</Implementation-Title>
                                        <Build-Channel>training</Build-Channel>
                                    </manifestEntries>
                                </transformer>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                                    <resource>META-INF/demo/providers.list</resource>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Cấu hình này là chủ thể của bài:**

1. Shade chạy tại **`package`**, sau JAR packaging của app trong default lifecycle.
2. `shadedArtifactAttached=true` tạo **classifier `all`** thay vì thay main artifact.
3. `createDependencyReducedPom=false` giúp demo không tạo reduced POM; trong library production cần quyết định khác tùy artifact publication.
4. `minimizeJar=false` để không loại providers được nạp qua ServiceLoader mà static analysis có thể không nhìn ra.
5. `<filters>` loại source signature files không còn thích hợp với archive mới.
6. `ManifestResourceTransformer` chọn `org.example.app.Main` cho JAR cuối.
7. `ServicesResourceTransformer` merge hai Java SPI service descriptors.
8. `AppendingTransformer` gộp line-list resource cùng tên từ hai provider JARs.

**Không đặt Shade plugin ở root parent** vì mọi child JAR có thể bị ảnh hưởng do inheritance. Root chỉ quản lý compiler/JAR plugin versions.

### 6.9. `app/src/main/java/org/example/app/Main.java`

```java
package org.example.app;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.ServiceLoader;
import org.example.spi.GreetingProvider;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        List<GreetingProvider> providers = new ArrayList<>();
        ServiceLoader.load(GreetingProvider.class).forEach(providers::add);
        providers.sort(Comparator.comparing(GreetingProvider::id));

        System.out.println("providers=" + providers.size());
        for (GreetingProvider provider : providers) {
            System.out.println(provider.id() + "=" + provider.message());
        }

        String path = "META-INF/demo/providers.list";
        InputStream input = Main.class.getClassLoader()
                .getResourceAsStream(path);
        if (input == null) {
            throw new IllegalStateException("Missing " + path);
        }

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8))) {
            List<String> lines = reader.lines()
                    .map(String::trim)
                    .filter(line -> !line.isEmpty())
                    .sorted()
                    .toList();
            System.out.println("resources=" + String.join(",", lines));
        }
    }
}
```

Java 17 có `ServiceLoader` và `Stream.toList()`. Code dùng `sorted()` để không phụ thuộc input order của Shade, vì **trình tự providers/resources không nhất thiết là một API contract**. `Main` đọc cả SPI providers lẫn line-list resource, nên kiểm tra hai transformers độc lập.

### 6.10. Chạy build và quan sát đầu ra chính xác

Từ thư mục `shade-overlap-demo/`:

```bash
java -version
javac -version
mvn -version
mvn -B clean package
```

Maven reactor build các JAR modules theo dependencies. Nếu plugins/dependencies được resolve thành công, output:

```text
spi/target/spi-1.0.0.jar
provider-alpha/target/provider-alpha-1.0.0.jar
provider-beta/target/provider-beta-1.0.0.jar
app/target/app-1.0.0.jar
app/target/app-1.0.0-all.jar
```

**Chạy đúng shaded artifact:**

```bash
java -jar app/target/app-1.0.0-all.jar
```

**Stdout chính xác mong đợi:**

```text
providers=2
alpha=Hello from Alpha
beta=Hello from Beta
resources=alpha,beta
```

Giải thích output:

- `providers=2`: cả hai `META-INF/services` contributions có mặt sau merge.
- `alpha=...` và `beta=...`: cả hai classes được đóng gói và ServiceLoader khởi tạo được.
- `resources=alpha,beta`: `META-INF/demo/providers.list` đã được nối, chương trình sort và join bằng dấu phẩy.

Đây là **stdout của ứng dụng**, không phải toàn bộ Maven logs.

**Cảnh báo về file JAR:** `app/target/app-1.0.0.jar` là **JAR thường** vì Shade được cấu hình với `shadedArtifactAttached=true`. Nó không phải executable fat JAR trong ví dụ; phải chạy `app-1.0.0-all.jar`.

### 6.11. Kiểm tra entries trong shaded JAR

```bash
jar tf app/target/app-1.0.0-all.jar
```

Các entries quan trọng cần có:

```text
META-INF/MANIFEST.MF
META-INF/services/org.example.spi.GreetingProvider
META-INF/demo/providers.list
org/example/spi/GreetingProvider.class
org/example/alpha/AlphaGreeting.class
org/example/beta/BetaGreeting.class
org/example/app/Main.class
```

`jar tf` chỉ liệt kê **tên entries**, không xác nhận nội dung resource merged. Muốn kiểm tra content và manifest, có thể dùng `java.util.jar.JarFile` (mục tiếp theo) hoặc giải nén **vào thư mục kiểm tra riêng**, tránh tạo file rác trong repository.

### 6.12. Java utility đọc manifest và merged resources

Tạo một file **độc lập** `JarInspector.java` để kiểm tra archive, không cần đưa nó vào reactor demo:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class JarInspector {
    private JarInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected JAR path");
        }
        try (JarFile jar = new JarFile(args[0])) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("Manifest missing");
            }
            System.out.println("Main-Class=" + manifest
                    .getMainAttributes().getValue("Main-Class"));

            for (String name : new String[] {
                    "META-INF/services/org.example.spi.GreetingProvider",
                    "META-INF/demo/providers.list"}) {
                JarEntry entry = jar.getJarEntry(name);
                if (entry == null) {
                    throw new IllegalStateException("Missing " + name);
                }
                try (InputStream input = jar.getInputStream(entry)) {
                    String content = new String(input.readAllBytes(),
                            StandardCharsets.UTF_8);
                    System.out.println("resource=" + name);
                    System.out.print(content);
                }
            }
        }
    }
}
```

Cách chạy **khi đặt utility cạnh thư mục `shade-overlap-demo/`**:

```bash
javac JarInspector.java
java JarInspector shade-overlap-demo/app/target/app-1.0.0-all.jar
```

Nếu đứng trong root `shade-overlap-demo/`, thay đối số JAR path bằng `app/target/app-1.0.0-all.jar`.

**Không cam kết thứ tự provider lines trong stdout của utility** vì nó in raw merged contents. Tiêu chí QA là `Main-Class=org.example.app.Main`, **cả hai class names xuất hiện** trong SPI descriptor, và file list chứa đủ `alpha`, `beta`. Để có stdout chính xác và ổn định, dùng chương trình `Main` có `sorted()` ở mục 6.10.

## 7. Thí nghiệm cố ý bỏ transformers

### 7.1. Bỏ ServicesResourceTransformer

Trong app POM, tạm bỏ dòng:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
```

Sau đó chạy:

```bash
mvn -B clean package
java -jar app/target/app-1.0.0-all.jar
```

Khi hai dependencies đều có một file `META-INF/services/org.example.spi.GreetingProvider`, không có merge rule thích hợp, descriptor có thể chỉ còn một contribution. Chương trình có thể in `providers=1`, hoặc gặp triệu chứng khác phụ thuộc hành vi packaging. **Không dựa vào việc alpha hay beta được chọn trước**: điều ấy không phải hợp đồng ổn định. Hãy khôi phục transformer sau thí nghiệm.

### 7.2. Bỏ AppendingTransformer

Tạm bỏ fragment:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/demo/providers.list</resource>
</transformer>
```

Khi ấy resource line-list có thể chỉ giữ một bản, và output `resources=` không còn đủ `alpha,beta`. Chỉ nhìn `jar tf` thấy file `META-INF/demo/providers.list` **vẫn có** là chưa đủ: phải kiểm tra **nội dung**.

Sau khi quan sát, khôi phục cả hai transformers rồi chạy lại `mvn clean package`.

### 7.3. Đừng sửa bài bằng cách hardcode providers

Nếu bỏ transformer khiến ServiceLoader thiếu một implementation, đừng sửa `Main` bằng cách gọi trực tiếp `new AlphaGreeting()` và `new BetaGreeting()`. Điều đó che lỗi **metadata SPI packaging**. Trong hệ thống plugin thực, source code consumer không biết trước danh sách providers; đúng cách là **bảo toàn service registrations**.

## 8. Assembly `jar-with-dependencies` và giới hạn resource merging

Maven Assembly Plugin có descriptor **`jar-with-dependencies`**. Nó unpack project + runtime dependency JARs vào một JAR và có thể đặt `Main-Class` bằng Maven Archiver. Tuy nhiên đây là **basic uber-JAR support**, không tương đương transformer của Shade khi hai JAR có cùng SPI/resource path.

Nếu muốn so sánh, thay **riêng cấu hình Shade ở `app/pom.xml`** bằng plugin fragment:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>3.8.0</version>
    <configuration>
        <descriptorRefs>
            <descriptorRef>jar-with-dependencies</descriptorRef>
        </descriptorRefs>
        <archive>
            <manifest>
                <mainClass>org.example.app.Main</mainClass>
            </manifest>
        </archive>
    </configuration>
    <executions>
        <execution>
            <id>create-basic-fat-jar</id>
            <phase>package</phase>
            <goals>
                <goal>single</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

**Đây là cấu hình thay thế để thử**, không phải thành phần của POM runnable ở mục 6. Output theo built-in descriptor thường là:

```text
app/target/app-1.0.0-jar-with-dependencies.jar
```

Dùng `java -jar` có thể chạy Main, nhưng **không nên kỳ vọng hai service files và line-list resources được merge đầy đủ**. Kết quả phụ thuộc vào logic unpack/duplicate handling của Assembly. Với trường hợp này, **Shade + transformers** là lựa chọn phù hợp hơn.

### 8.1. Assembly ZIP/TAR có thể tốt hơn fat JAR

Một distribution layout như sau có giá trị thực tế:

```text
release/
├── app.jar
├── lib/
│   ├── spi-1.0.0.jar
│   ├── provider-alpha-1.0.0.jar
│   └── provider-beta-1.0.0.jar
├── bin/
│   └── run.sh
└── config/
```

Ở đây các JARs được giữ **nguyên file** (không unpack), nên source manifests, service descriptors và signatures nếu có **không bị ghi đè do trùng ZIP path**. Cần cấu hình classpath/run script đúng; Java `ServiceLoader` sẽ đọc service descriptors từ từng JAR theo classloader.

Đây đặc biệt hữu ích khi vendor artifacts phải giữ chữ ký gốc, khi chạy trên module path hoặc khi framework dựa vào layout dependency JAR riêng.

### 8.2. Khi nào phối hợp Shade và Assembly?

Một pipeline có thể làm:

```text
compile/test
    |
Shade -> app-all.jar
    |
Assembly -> distribution.zip (app-all.jar + scripts + config)
```

Mỗi plugin có **một trách nhiệm riêng**, không hai plugin tranh nhau sửa cùng artifact. Nếu `app-all.jar` đã chứa dependencies, đừng tiếp tục giải nén/tái gộp lại bằng `jar-with-dependencies` vô ý.

## 9. Relocation, minimization và dynamic loading

### 9.1. Relocation không phải tên mới cho exclusion

Shade hỗ trợ đổi package:

```xml
<relocations>
    <relocation>
        <pattern>org.example.alpha</pattern>
        <shadedPattern>org.example.internal.alpha</shadedPattern>
    </relocation>
</relocations>
```

**Fragment nâng cao** dưới cấu hình Shade; không có trong demo chính. Nếu relocate `AlphaGreeting`, class binary name thay đổi. `ServicesResourceTransformer` hỗ trợ cập nhật service descriptor names tương ứng.

Tuy nhiên, relocation không thể tự đoán mọi chuỗi reflection, serialized names, JNI registrations, OSGi/module metadata hoặc configuration do framework riêng parse. Cần tests thật cho đường dynamic loading.

### 9.2. Vì sao demo không bật `minimizeJar`?

Những classes như `AlphaGreeting` và `BetaGreeting` được dùng **gián tiếp qua ServiceLoader**, không phải luôn được `Main` import/gọi tường minh. Static-analysis-based minimization có thể loại classes tưởng là không dùng.

Vì vậy demo chọn:

```xml
<minimizeJar>false</minimizeJar>
```

Đây là lựa chọn giữ source artifacts đầy đủ để dạy resource merging. Nếu muốn dùng minimize trong production, hãy có **runtime integration tests** cho SPI, reflection, serialization và framework-specific registrations, đồng thời kiểm tra các includes/entryPoints của Shade.

### 9.3. `dependency-reduced-pom.xml` không nên bị bỏ qua trong library phát hành

Shade có thể tạo **dependency-reduced-pom.xml** phản ánh dependencies đã gộp. Demo đặt:

```xml
<createDependencyReducedPom>false</createDependencyReducedPom>
```

để không tạo file giảm dependency trong bài lab nơi shaded JAR là **classifier** tách biệt và project không deploy như một thư viện cho consumers. Trong production, đặc biệt khi shaded output **thay thế main artifact** và được publish lên Maven repository, reduced POM có thể cần được xem xét nghiêm túc để không kéo dependencies đã gộp thêm một lần nữa. Không copy tùy tiện một setting của demo.

## 10. Chẩn đoán duplicate warnings và lỗi runtime

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `no main manifest attribute` | Chạy JAR thường hoặc thiếu Main-Class | Kiểm tra shaded artifact và ManifestResourceTransformer |
| `ClassNotFoundException`/`NoClassDefFoundError` | Dependency class bị thiếu/exclude/minimize | `jar tf`, `dependency:tree`, tắt minimization thử |
| `ServiceConfigurationError` | Descriptor trỏ class không có hoặc đã relocated | ServicesResourceTransformer, xem service path/content |
| Chỉ tìm được một provider | Trùng service file không merge | Dùng ServicesResourceTransformer |
| `resources=alpha` thiếu beta | Trùng line-list file không append | AppendingTransformer cho đúng resource |
| JSON hoặc XML không parse | Nối sai định dạng | Transformer phù hợp hoặc custom merge strategy |
| `Invalid signature file digest` | Signature source JAR không còn hợp lệ | Filter metadata chữ ký không phù hợp, ký lại nếu cần |
| `jarsigner` báo unsigned | JAR chưa được ký | Không coi là verified; ký nếu release policy yêu cầu |
| `META-INF/*.SF` còn trong output | Filter thiếu hoặc pattern/scope sai | Kiểm tra filters và actual entries |
| Xóa hết `META-INF` làm ứng dụng hỏng | Filter quá rộng | Chỉ exclude signature files cần thiết |
| Thiếu LICENSE/NOTICE | Loại/ghi đè nhầm legal metadata | Xem license policy, giữ attribution |
| Nhiều `com/example/Util.class` | Duplicate class definitions | Kiểm tra graph, versions, relocation |
| Shade warnings tăng khi build lại không `clean` | Có thể shade artifact đã được shade ở lần trước | Dùng `mvn clean package`, xem input |
| Bật minimize làm provider biến mất | Static reachability không thấy dynamic SPI | Tắt minimize, kiểm thử và khai báo entry points |
| Relocate xong ServiceLoader lỗi | Descriptor không cập nhật theo class names mới | Merge + relocation support, test runtime |
| `Class-Path` manifest trỏ JAR không có | Source manifest có path không còn tồn tại | Chỉnh manifest cuối, test `java -jar` |
| JAR có `module-info.class` gây lỗi | Uber JAR không giữ toàn bộ module identity | Xem chiến lược module path/distribution |
| Output không nằm ở tên mong đợi | Attached classifier/finalName/outputFile | Xác định Shade goal options và target |
| Lỗi chỉ trong CI | JDK/version/caches/source artifact khác | Ghim versions, build sạch, kiểm tra dependency tree |

### 10.1. Cách điều tra step-by-step

1. Chạy từ root:

   ```bash
   mvn -B -V clean verify
   ```

2. Xác định đúng **shaded artifact cuối**, không xem main JAR thường như fat JAR.
3. Liệt kê archive entries bằng `jar tf`.
4. Kiểm tra logical `Main-Class` của `META-INF/MANIFEST.MF`.
5. Xem nội dung `META-INF/services`, resource lists, configs trùng.
6. Chạy `java -jar` và đối chiếu **cả providers count và resources content**.
7. Nếu có duplicate classes, điều tra `dependency:tree`/artifact sources.
8. Nếu có signed JARs, xác minh source signature policy, inspect final signature paths/named manifest digests, và ký lại nếu cần.
9. Thử **clean build** trước khi đổi filters vì cached output có thể gây cảnh báo nhiễu.
10. Chạy CI/runtime smoke tests trong môi trường không có dependency classpath từ máy developer.

## 11. Kiểm tra resource paths và chữ ký trong CI

Các lệnh hữu ích:

```bash
mvn -B clean verify
java -jar app/target/app-1.0.0-all.jar
jar tf app/target/app-1.0.0-all.jar
jarsigner -verify -verbose -certs app/target/app-1.0.0-all.jar
```

**Phân biệt rõ mục đích**: `java -jar` kiểm tra runtime; `jar tf` kiểm tra entries; `jarsigner` kiểm tra chữ ký khi có signed archive. **Với demo unsigned, output unsigned là điều bình thường và không phải chữ ký PASS.**

Trên Unix có thể lọc `META-INF`:

```bash
jar tf app/target/app-1.0.0-all.jar | grep 'META-INF/'
```

Trên PowerShell:

```powershell
jar tf app/target/app-1.0.0-all.jar | Select-String 'META-INF/'
```

Lệnh trên chỉ hiển thị **tên**, không đánh giá named manifest sections, nội dung service descriptors, licenses hay trust policy.

### 11.1. Assertion tốt hơn việc chỉ xem `BUILD SUCCESS`

Với demo, một test chất lượng nên xác nhận:

```text
Main-Class = org.example.app.Main
Service providers count = 2
Provider IDs = alpha, beta
Merged resource lines = alpha, beta
Required classes all present
Unexpected signature-related files absent
```

Nếu app có framework plugin metadata, thêm tests tương ứng. Nếu legal/security policy yêu cầu signed artifact, cần test signature verification **sau ký**, không chỉ kiểm tra không còn file `.SF`.

### 11.2. Metadata pháp lý không phải cảnh báo có thể bỏ qua

Khi Shade gặp nhiều files `LICENSE`, `LICENSE.txt`, `NOTICE` hoặc resource metadata khác, có thể dùng transformers chuyên biệt để hợp nhất/hạn chế trùng về mặt kỹ thuật. Nhưng giấy phép của từng dependency có thể đòi hỏi giữ bản quyền, NOTICE hoặc license text đi kèm khi phân phối.

Không dùng filter broad chỉ để “làm sạch archive”. Kiểm tra điều kiện license của các artifacts thật và thiết kế quy trình release phù hợp.

### 11.3. Reproducibility

Root POM mẫu có:

```xml
<project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
```

Nó giúp các archive plugins hỗ trợ timestamp ổn định. Tuy nhiên reproducible build còn phụ thuộc plugin versions, input JAR bytes, code generation, resource merging order, environment và metadata. Không khẳng định cùng outputTimestamp **bảo đảm** hash JAR giống nhau ở mọi máy.

## 12. Câu hỏi tự kiểm tra

**1.** Hai dependencies có cùng path `META-INF/services/org.example.spi.GreetingProvider`. Vì sao cần transformer?  
**Đáp án:** Để merge provider declarations, tránh mất một implementation khi gộp paths.

**2.** Transformer nào dùng cho Java SPI?  
**Đáp án:** `ServicesResourceTransformer`.

**3.** Transformer nào gán `Main-Class` trong Shade?  
**Đáp án:** `ManifestResourceTransformer`.

**4.** `AppendingTransformer` có thể dùng để nối hai JSON objects độc lập không?  
**Đáp án:** Không nếu nối làm JSON không hợp lệ; phải merge đúng schema.

**5.** Vì sao không nên giữ chữ ký `.SF`/`.RSA` nguyên vẹn trong JAR đã shade?  
**Đáp án:** Chữ ký bảo vệ source JAR bytes, không tự đại diện cho archive mới đã đổi nội dung/manifest.

**6.** Filter chữ ký có nghĩa shaded JAR được ký mới chưa?  
**Đáp án:** Chưa. Phải có bước ký và verify riêng nếu cần.

**7.** Vì sao không exclude toàn bộ `META-INF`?  
**Đáp án:** Vì có SPI descriptors, legal metadata, framework registries và manifest cần thiết.

**8.** `jar-with-dependencies` của Assembly có đảm bảo merge services như Shade không?  
**Đáp án:** Không. Nó hỗ trợ basic uber JAR; nên dùng Shade cho merging phức tạp.

**9.** Vì sao demo tạo `app-1.0.0.jar` và `app-1.0.0-all.jar`?  
**Đáp án:** Vì `shadedArtifactAttached=true` và classifier name `all`.

**10.** `jar tf` thấy service resource có nghĩa có đủ hai provider chưa?  
**Đáp án:** Chưa. Phải kiểm tra nội dung merged file hoặc chạy ServiceLoader thực tế.

**11.** Tại sao demo đặt `minimizeJar=false`?  
**Đáp án:** Các providers được dùng gián tiếp nên minimizer có thể bỏ nhầm nếu không suy ra dynamic references.

**12.** Relocation có thể ảnh hưởng gì tới SPI?  
**Đáp án:** Tên provider/interface thay đổi; service descriptor phải cập nhật.

**13.** Hai JAR đều có `org/example/Foo.class`. AppendingTransformer có sửa được không?  
**Đáp án:** Không. Cần giải quyết dependencies/version conflicts hoặc relocation.

**14.** Muốn giữ vendor signatures nguyên trạng thì nên dùng gì?  
**Đáp án:** Distribution ZIP/TAR chứa original JARs không unpack thay vì shade các JAR đó.

**15.** Vì sao `BUILD SUCCESS` chưa chứng minh resource merging đúng?  
**Đáp án:** Vì class compilation/package có thể thành công dù file SPI hoặc config bị ghi đè và runtime sai.

**16.** Khi `jarsigner` báo `jar is unsigned`, có nên báo “signature verified”?  
**Đáp án:** Không. Unsigned khác với signature verification PASS.

**17.** Các digest entries trong named manifest sections từ signed source JAR có thể xử lý thế nào?  
**Đáp án:** Phải kiểm tra tính phù hợp với JAR mới và tạo manifest sạch/chính xác khi cần; không coi filter `.SF` đơn lẻ là bảo đảm.

**18.** Khi Shade overlap warnings quá nhiều sau build không `clean`, nên làm gì đầu tiên?  
**Đáp án:** Thử `mvn clean package`, xem input artifacts và warnings trước khi thêm exclusions.

## 13. Checklist trước khi phát hành

- [ ] Chọn rõ loại output: shaded JAR, assembled JAR hay ZIP/TAR.
- [ ] `Main-Class` trỏ đúng class có Java entry point.
- [ ] Không kế thừa mù quáng manifest của source dependencies.
- [ ] Khi có signed source JARs, đã kiểm tra manifest named sections/digests.
- [ ] `META-INF/services` cần merge đã dùng ServicesResourceTransformer.
- [ ] Resource lists trùng có rules hợp định dạng.
- [ ] Không nối bừa XML/JSON/properties với duplicate keys.
- [ ] Duplicate `.class` được xử lý theo dependency graph/version/relocation, không che warnings.
- [ ] Nếu relocate classes, có tests cho reflection/SPI/framework metadata.
- [ ] Nếu dùng minimization, có tests cho dynamic providers.
- [ ] Không xóa broad `META-INF` chỉ vì chữ ký cũ.
- [ ] Source signatures được verify trước biến đổi khi policy yêu cầu.
- [ ] Final archive được ký **sau đóng gói** và verify khi chính sách yêu cầu.
- [ ] LICENSE/NOTICE và các nghĩa vụ pháp lý được giữ.
- [ ] Có runtime smoke tests trên **chính artifact cuối**.
- [ ] Artifact name/classifier được xác định rõ khi deploy.
- [ ] CI dùng JDK/Maven/plugin versions được kiểm soát.
- [ ] Không coi `BUILD SUCCESS` là bằng chứng về license, signature hoặc runtime semantics.

## 14. Nguồn tham khảo chính thức

1. [Apache Maven Shade Plugin — Usage](https://maven.apache.org/components/plugins/maven-shade-plugin/usage.html)
2. [Apache Maven Shade Plugin — Resource Transformers](https://maven.apache.org/components/plugins/maven-shade-plugin/examples/resource-transformers.html)
3. [Apache Maven Shade Plugin — Selecting Contents for Uber JAR](https://maven.apache.org/components/plugins/maven-shade-plugin/examples/includes-excludes.html)
4. [Apache Maven Shade Plugin — shade:shade](https://maven.apache.org/components/plugins/maven-shade-plugin/shade-mojo.html)
5. [Apache Maven Shade Plugin — Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html)
6. [Apache Maven Assembly Plugin — Predefined Assembly Descriptors](https://maven.apache.org/plugins/maven-assembly-plugin/descriptor-refs.html)
7. [Apache Maven Assembly Plugin — Usage and Executable JAR](https://maven.apache.org/plugins/maven-assembly-plugin/usage.html)
8. [Java SE 17 — JAR File Specification / signed JAR](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html)
9. [Oracle Java — Verifying Signed JAR Files](https://docs.oracle.com/javase/tutorial/deployment/jar/verify.html)
10. [Java SE 17 API — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
11. [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)

**Ghi nhớ:** **Shade không tự biết resource nào phải gộp theo semantics; hãy cấu hình manifest, service/resource transformers và signature filters có chọn lọc. Assembly `jar-with-dependencies` chỉ hỗ trợ fat JAR cơ bản. Chữ ký của JAR nguồn không được chuyển nguyên vẹn thành chữ ký của JAR đã được đóng gói lại.** Chỉ kết luận build đúng sau khi kiểm tra manifest, merged files, ServiceLoader và security policy trên **chính artifact cuối**.
