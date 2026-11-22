# JAR thường, executable JAR và cấu hình launcher

Khi chuyển một ứng dụng Java từ JDK cũ lên JDK mới, việc biên dịch thành công không bảo đảm bản phát hành khởi động được. Có thể file JAR thiếu `Main-Class`, bộ thư viện lúc chạy khác với lúc compile, JVM được chọn sai phiên bản, classpath được thiết lập khác trong container, hoặc launcher truyền các tùy chọn `-D` và `-Xmx` không đúng vị trí. Một ứng dụng chạy tốt trong IDE vẫn có thể thất bại khi được triển khai dưới Linux systemd, Windows Service hay một container sạch.

Để xử lý vấn đề có hệ thống, cần phân biệt ba khái niệm:

- **JAR thường (library JAR):** archive chứa Java class và resource, được sử dụng như một thư viện hoặc thành phần của ứng dụng; không nhất thiết có entrypoint.
- **Executable JAR:** JAR có metadata entrypoint, phổ biến là `Main-Class` trong manifest, có thể khởi chạy bằng `java -jar` khi dependencies và runtime được cung cấp đủ.
- **Launcher:** lệnh, script hoặc chương trình chọn Java executable, classpath/module path, JVM options, working directory, environment và cách vận hành process.

Trong Java Advance Compatibility Migration, cả ba lớp đều có thể thay đổi khi nâng JDK, Maven/Gradle, framework hoặc hệ điều hành. Mục tiêu là tạo một artifact **có cấu trúc xác định, dependency rõ ràng, có thể chạy với runtime mục tiêu, được giám sát và rollback an toàn**.

## 1. JAR là gì?

JAR (Java Archive) là một archive dựa trên định dạng ZIP với các quy ước dành cho hệ sinh thái Java. Một JAR có thể chứa:

~~~text
catalog-api.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── services/
│       └── com.acme.spi.CatalogProvider
├── com/
│   └── acme/
│       └── catalog/
│           ├── CatalogClient.class
│           └── CatalogResult.class
└── com/acme/catalog/messages.properties
~~~

- `.class`: bytecode đã được biên dịch.
- `.properties`, XML, JSON, ảnh, schema: resource để ứng dụng đọc.
- `META-INF/MANIFEST.MF`: metadata mô tả archive.
- `META-INF/services`: thông tin service provider theo cơ chế classpath.
- `module-info.class`: module descriptor đối với explicit modular JAR.
- Một số entry chữ ký/metadata khác, tùy cách đóng gói.

**Đuôi `.jar` không nói JAR được tạo bởi JDK phiên bản nào, có class `main` hay không, hoặc đã gom mọi thư viện phụ thuộc vào trong.**

Có thể liệt kê nội dung JAR bằng:

~~~bash
jar --list --file dist/catalog-api.jar
~~~

Với công cụ JDK cũ, cú pháp truyền thống cũng thường dùng:

~~~bash
jar tf dist/catalog-api.jar
~~~

Đọc kết quả để xác nhận các class được đặt dưới đường dẫn tương ứng package, resource được đóng gói và manifest có thực sự nằm đúng vị trí.

## 2. JAR thường không cần có Main-Class

Một thư viện chứa lớp:

~~~java
package com.acme.catalog;

public final class CatalogClient {
    public String findName(String code) {
        return "Product " + code;
    }
}
~~~

không có lý do bắt buộc phải có `public static void main(String[] args)`. Nó được dự án khác sử dụng qua Maven/Gradle dependency hoặc classpath/module path.

Giả sử JAR có một lớp main nhưng manifest **không** khai báo entrypoint, có thể khởi chạy trực tiếp lớp đó qua classpath:

~~~bash
java -cp dist/app-plain.jar com.acme.app.Main
~~~

Ngược lại, lệnh:

~~~bash
java -jar dist/app-plain.jar
~~~

có thể báo:

~~~text
no main manifest attribute, in dist/app-plain.jar
~~~

Đây thường là lỗi chọn **chế độ launch**, không có nghĩa archive bị hỏng. Cần phân biệt *JAR có chứa main class* với *JAR khai báo main class trong manifest*.

## 3. Tạo JAR thường từ mã nguồn

Ví dụ mã nguồn:

~~~java
package com.acme.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
        System.out.println("Number of args = " + args.length);
    }
}
~~~

Với JDK hiện đại, có thể biên dịch và đóng gói trên shell Unix-like:

~~~bash
mkdir -p build/classes dist

javac -d build/classes \
  src/main/java/com/acme/app/Main.java

jar --create --file dist/app-plain.jar \
  -C build/classes .
~~~

Kiểm tra:

~~~bash
jar --list --file dist/app-plain.jar
java -cp dist/app-plain.jar com.acme.app.Main demo
~~~

`-C build/classes .` yêu cầu công cụ JAR lấy nội dung từ thư mục chứa các class đã biên dịch để root archive bắt đầu ở package path `com/acme/...`.

Cần chú ý:

- Compiler phải dùng classpath hoặc module path phù hợp nếu ứng dụng tham chiếu thư viện khác.
- Resource từ `src/main/resources` cũng phải được copy vào output trước khi đóng gói nếu không dùng build tool tự động.
- JDK mới có thể tạo classfile không chạy trên JVM cũ nếu không đặt target đúng.
- Ví dụ tập trung cách đóng gói, không thay thế Maven/Gradle trong một dự án lớn.

## 4. Executable JAR và Main-Class

Một executable JAR truyền thống có manifest khai báo:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.app.Main
~~~

Khi gọi:

~~~bash
java -jar dist/app.jar
~~~

Java launcher đọc `Main-Class` để chọn entrypoint và nạp các class liên quan. Có thể tạo archive bằng:

~~~bash
jar --create \
  --file dist/app.jar \
  --main-class com.acme.app.Main \
  -C build/classes .
~~~

Hoặc cú pháp truyền thống của công cụ `jar`:

~~~bash
jar cfe dist/app.jar com.acme.app.Main \
  -C build/classes .
~~~

Sau đó:

~~~bash
java -jar dist/app.jar first second
~~~

Đối với mô hình main truyền thống, class cần có entrypoint hợp lệ, thường là `public static void main(String[] args)`. Những khả năng launch mới ở một số phiên bản Java không nên được giả định nếu dự án còn hỗ trợ JDK cũ.

### 4.1. Main-Class là tên Java class, không phải đường dẫn

Đúng:

~~~text
Main-Class: com.acme.app.Main
~~~

Sai:

~~~text
Main-Class: com/acme/app/Main.class
Main-Class: Main.java
Main-Class: dist/app.jar
~~~

Nếu code đổi package nhưng manifest không đổi, có thể xuất hiện `Could not find or load main class`. Kiểm tra archive và tên class đã biên dịch, không chỉ tên file nguồn.

### 4.2. Main-Class không gom dependencies

Ngay cả khi `java -jar` tìm đúng class main, một lệnh gọi `new HttpClientImpl()` có thể thất bại vì JAR chứa ứng dụng không có thư viện HTTP client trong runtime. Lúc đó lỗi thuộc classpath/packaging, không phải manifest entrypoint.

## 5. Manifest metadata cần được hiểu đúng

Manifest thường nằm tại:

~~~text
META-INF/MANIFEST.MF
~~~

Một ví dụ:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.app.Main
Implementation-Title: Order Service
Implementation-Version: 2.0.0
Class-Path: lib/http-client.jar lib/json-codec.jar
~~~

| Attribute | Mục đích |
|---|---|
| `Manifest-Version` | Phiên bản định dạng manifest |
| `Main-Class` | Entrypoint của chế độ `-jar` |
| `Class-Path` | Khai báo các mục classpath bổ sung theo quy tắc JAR manifest |
| `Implementation-Version` | Metadata bản phát hành, không thay thế dependency versioning |
| `Implementation-Title` | Metadata tên thành phần |
| `Automatic-Module-Name` | Đặt tên ổn định cho automatic module trong tình huống áp dụng |
| `Multi-Release` | Đánh dấu multi-release JAR theo Java specification |

Một số framework có thêm attribute riêng, ví dụ Spring Boot sử dụng metadata về application start class. **Không phải mọi attribute có trong manifest đều được JVM launcher diễn giải trực tiếp**.

### 5.1. Định dạng manifest có quy tắc cụ thể

Manifest không phải file text tùy ý: syntax attribute, xuống dòng, continuation lines và encoding phải theo JAR file specification. Khi tự viết file manifest, nên để công cụ build/JAR tạo cấu trúc đúng, thay vì nối chuỗi một cách thủ công.

Ví dụ khi đã có custom manifest hợp lệ:

~~~bash
jar --create \
  --file dist/app.jar \
  --manifest custom-manifest.mf \
  -C build/classes .
~~~

Sau khi tạo, đọc **manifest trong JAR đầu ra**, vì file nguồn đúng chưa chứng minh bản đóng gói cuối có nội dung tương ứng.

## 6. Classpath của ứng dụng thường

Classpath là danh sách vị trí mà Java launcher và class loader sử dụng để tìm class/resource trong chế độ classpath.

Linux/macOS:

~~~bash
java -cp "dist/app.jar:dist/lib/*" \
  com.acme.app.Main
~~~

Windows PowerShell:

~~~powershell
java -cp "dist\app.jar;dist\lib\*" com.acme.app.Main
~~~

Lưu ý:

- Trên Unix, các mục classpath thường phân tách bằng `:`.
- Trên Windows, phân tách bằng `;`.
- Wildcard `lib/*` trong command-line classpath có thể bổ sung các JAR trực tiếp trong thư mục theo quy tắc Java launcher.
- Quoting giúp shell không tự xử lý dấu `*` và các đường dẫn có khoảng trắng sai cách.
- Không nên dựa vào thứ tự expansion wildcard để chọn dependency version khi có file trùng class.

### 6.1. Classpath root phải là thư mục đúng

Nếu class đã compile nằm tại:

~~~text
build/classes/com/acme/app/Main.class
~~~

thì lệnh đúng khi chạy từ thư mục dự án là:

~~~bash
java -cp build/classes com.acme.app.Main
~~~

Không đặt `build/classes/com/acme/app` làm root rồi chạy `Main` nếu class khai báo package `com.acme.app`.

### 6.2. Compile classpath không phải runtime classpath

Một thư viện có thể được cung cấp cho compiler nhưng không được đưa vào runtime vì dependency scope hoặc packaging option. Chẳng hạn Maven `provided` và Gradle `compileOnly` có ý nghĩa khác runtime dependency.

Nếu compile thành công nhưng Java launcher báo `NoClassDefFoundError`, cần xác minh các JAR thực sự có trong **runtime** và đúng class loader, thay vì chỉ kiểm tra IDE dependency list.

## 7. java -jar không hoạt động như java -cp

Hai chế độ điển hình:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

và:

~~~bash
java -jar app.jar
~~~

khác nhau ở cách xác định application classpath và entrypoint. Khi dùng `-jar`, không nên dựa vào option `-cp` hoặc biến môi trường `CLASSPATH` để bổ sung user classpath như chế độ chạy main class.

Ví dụ dễ gây hiểu nhầm:

~~~bash
java -cp "lib/*" -jar app.jar
~~~

Lệnh không phải cách đáng tin cậy để buộc executable JAR dùng mọi JAR trong `lib/`. Các lựa chọn thích hợp:

1. Chạy main class bằng `-cp` với danh sách runtime dependencies.
2. Khai báo `Class-Path` manifest trong thin executable JAR khi cấu trúc phù hợp.
3. Dùng generated launcher/distribution của Maven/Gradle hoặc framework.
4. Tạo shaded/uber JAR hoặc framework-specific executable archive có loader phù hợp.

## 8. Manifest Class-Path cho thin executable JAR

Giả sử bản phát hành:

~~~text
release/
├── app.jar
├── config/
│   └── application.properties
└── lib/
    ├── client-api.jar
    └── json-runtime.jar
~~~

Manifest của `app.jar` có thể chứa:

~~~text
Main-Class: com.acme.app.Main
Class-Path: lib/client-api.jar lib/json-runtime.jar
~~~

Những mục classpath trong manifest thường được resolve tương đối với **vị trí JAR chứa manifest** theo quy tắc JAR specification. Chúng không tự trở thành đường dẫn tương đối với current working directory của shell.

Ví dụ:

~~~bash
cd /tmp
java -jar /opt/myapp/release/app.jar
~~~

Các mục `lib/client-api.jar` được hiểu liên quan tới `/opt/myapp/release/app.jar`, không phải `/tmp/lib/client-api.jar`.

### 8.1. Điều mà manifest Class-Path không làm

- Không tự tải Maven dependencies từ internet.
- Không hỗ trợ wildcard classpath theo đúng cách `-cp lib/*`.
- Không biến một artifact thành fat JAR.
- Không giải quyết các xung đột classpath hoặc ClassLoader.
- Không bảo đảm resource path trong application là chính xác.
- Không thay thế module resolution nếu ứng dụng được khởi chạy ở chế độ JPMS.

Với hàng chục hoặc hàng trăm runtime JARs, một distribution có launcher script quản lý classpath có thể dễ duy trì hơn file manifest tự viết thủ công.

## 9. Thin JAR, fat JAR và distribution

| Dạng | Bố cục | Cách chạy thường gặp |
|---|---|---|
| Library JAR | Class/resource của thư viện | Đưa vào dependency của ứng dụng |
| Thin executable JAR | App classes + Main-Class; deps bên ngoài | `java -jar` có manifest Class-Path hoặc launcher phù hợp |
| Classpath distribution | `app.jar` và thư mục `lib/` riêng | Script chạy `java -cp ... Main` |
| Shaded/uber JAR | App classes và nhiều dependency classes cùng một archive | `java -jar` nếu manifest/merge đúng |
| Spring Boot executable JAR | App classes, nested dependencies và framework loader | `java -jar` theo Spring Boot launcher |
| Modular JAR | Module descriptor + classes | `java --module ...` khi chạy bằng module path |
| Runtime image | Java runtime và modules đã chọn | Launcher đi kèm image |

**Fat JAR không phải một chuẩn layout duy nhất**. Shaded JAR là dạng hợp nhất nội dung các JAR vào cùng root archive; nested JAR của framework là một cách khác với loader riêng.

## 10. Shading/uber JAR có lợi và có rủi ro

Một uber JAR có thể trông như:

~~~text
app-all.jar
├── META-INF/MANIFEST.MF
├── com/acme/app/Main.class
├── org/example/http/Client.class
├── com/fasterxml/.../ObjectMapper.class
└── META-INF/services/...
~~~

Ưu điểm: thường tiện vận chuyển khi không phải mang cả thư mục dependencies. Tuy nhiên, các bước merge có thể làm sai:

- **Duplicate classes:** hai JAR cùng chứa binary name.
- **Duplicate resources:** file cùng tên bị ghi đè.
- **ServiceLoader metadata:** `META-INF/services` mất provider.
- **Signed JAR metadata:** chữ ký của archive gốc không còn hợp lệ khi nội dung thay đổi.
- **Module descriptors:** không thể ghép nhiều `module-info.class` thành một module hợp lệ bằng cách copy ngẫu nhiên.
- **Multi-release entries:** phiên bản đặc thù JDK bị bỏ hoặc đè sai.
- **Framework discovery:** `spring.factories`, metadata annotation hoặc resource loaders bị mất.
- **License/NOTICE:** thông tin bản quyền của dependencies bị xử lý thiếu.
- **Native libraries:** extraction và naming xung đột.

### 10.1. META-INF/services phải được merge đúng

Giả sử hai dependencies chứa cùng file:

~~~text
META-INF/services/com.acme.spi.ReportFormatter
~~~

Dependency A khai báo:

~~~text
com.acme.format.CsvFormatter
~~~

Dependency B khai báo:

~~~text
com.acme.format.JsonFormatter
~~~

Nếu shaded output chỉ giữ một file, `ServiceLoader` có thể mất một formatter mà không báo lỗi ngay. Maven Shade Plugin có `ServicesResourceTransformer`; Gradle Shadow Plugin có cơ chế hợp nhất service files tương ứng. Dùng theo phiên bản plugin thực tế và xác nhận provider discovery ở runtime.

### 10.2. Relocation là thay đổi binary contract

Shading tools có thể relocate package để tránh conflict, nhưng những thành phần dùng reflection, resource paths, serialized class names hoặc JNI có thể phụ thuộc vào tên gốc. Không phải cứ relocate là an toàn.

Nếu có relocation, cần test dynamic class loading, service discovery và những dữ liệu serialized còn tồn tại từ bản trước.

### 10.3. Chữ ký JAR

Việc merge/sửa class files có thể làm metadata chữ ký từ JAR gốc không còn đúng. Không đưa nguyên chữ ký cũ vào artifact đã thay đổi rồi cho rằng nó vẫn được xác thực. Quy trình ký artifact phát hành và xác minh provenance phải được thiết kế phù hợp; không xử lý chữ ký bằng cách tắt kiểm tra bảo mật.

## 11. Maven: thêm Main-Class bằng Maven Jar Plugin

Một Maven project thường tạo JAR module bằng Maven Jar Plugin. Nếu cần executable manifest:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <version>VERSION_DA_CHON</version>
      <configuration>
        <archive>
          <manifest>
            <mainClass>com.acme.app.Main</mainClass>
          </manifest>
        </archive>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`VERSION_DA_CHON` là placeholder, cần thay bằng bản plugin phù hợp JDK/Maven của dự án. Ví dụ minh họa một đoạn `pom.xml`, không phải POM hoàn chỉnh.

~~~bash
./mvnw clean package
java -jar target/app.jar
~~~

Tên file `target/app.jar` chỉ là minh họa, phải đối chiếu `artifactId`, `version` và cấu hình build output thực tế.

**Quan trọng:** Maven Jar Plugin thông thường không gom tất cả dependencies vào JAR module. Nếu thiếu runtime dependency, thêm `Main-Class` vẫn không sửa được lỗi.

### 11.1. Maven Shade Plugin

Nếu muốn shaded JAR, cần cấu hình Maven Shade Plugin với transformer cho manifest và resource metadata. Một đoạn cấu hình điển hình:

~~~xml
<transformers>
  <transformer
    implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
    <mainClass>com.acme.app.Main</mainClass>
  </transformer>
  <transformer
    implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
~~~

Cấu hình phải được đặt trong plugin/execution và version hợp lệ. Cần rà soát duplicate resource handling, JAR signatures, relocation, dependency-reduced POM và tính tương thích của dependencies.

## 12. Gradle: jar và application distribution

Với Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

tasks.named('jar') {
    manifest {
        attributes('Main-Class': 'com.acme.app.Main')
    }
}
~~~

Cấu hình này tạo manifest entrypoint cho `jar` task, nhưng không tự nhét tất cả runtime dependencies vào trong archive. Đây là khác biệt giữa **manifest** và **packaging topology**.

### 12.1. Application Plugin

Gradle Application Plugin hỗ trợ running app và tạo distribution có launcher script cùng thư mục libraries:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.acme.app.Main'
}
~~~

Có thể chạy:

~~~bash
./gradlew run
./gradlew installDist
./gradlew distZip
~~~

Output distribution thường gồm thư mục `lib/` và script trong `bin/`. Cần kiểm tra output thật và cách plugin/version dự án xử lý các runtime dependencies.

Một distribution có launcher classpath rõ ràng thường phù hợp khi ứng dụng cần giữ các JAR riêng hoặc có plugin/module layer tùy chỉnh.

### 12.2. Gradle toolchain khác runtime của người dùng

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Cấu hình toolchain giúp Gradle chọn JDK cho các task hỗ trợ. Nó không tự đóng gói JDK 21 cùng bản phát hành. Máy đích cần runtime phù hợp hoặc một runtime image được bundle.

## 13. Spring Boot executable JAR có layout riêng

Một executable JAR của Spring Boot thường có bố cục tương tự:

~~~text
application.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   └── com/acme/app/Application.class
│   └── lib/
│       ├── spring-*.jar
│       └── other-dependency.jar
└── org/springframework/boot/loader/...
~~~

Các dependency là **nested JARs** chứ không phải mọi class được merge vào root. Spring Boot cung cấp launcher/loader để đọc layout này.

Manifest có thể chứa:

~~~text
Main-Class: <spring-boot-launcher-entrypoint>
Start-Class: com.acme.app.Application
~~~

Đây là mô hình, không phải manifest để copy nguyên. Tên loader class chính xác và metadata có thể thay đổi theo Spring Boot version.

### 13.1. Main-Class và Start-Class

- `Main-Class`: lớp được Java launcher khởi chạy theo manifest.
- `Start-Class`: metadata framework dùng để tìm entrypoint ứng dụng.
- `BOOT-INF/classes`: application classes trong layout điển hình.
- `BOOT-INF/lib`: nested runtime dependencies.

Nếu chạy:

~~~bash
java -cp application.jar com.acme.app.Application
~~~

classloader thông thường không tự coi `BOOT-INF/classes` như root classpath của một plain JAR. Cần dùng cơ chế launcher được Spring Boot version đó hỗ trợ.

### 13.2. bootJar khác jar

Trong Gradle/Spring Boot, `bootJar` và `jar` có thể tạo hai artifact khác nhau. Với Maven Spring Boot plugin, bước `repackage` có thể tạo executable artifact. Nếu CI publish nhầm plain JAR thay vì Boot executable JAR, runtime có thể thiếu dependency dù cả hai cùng mang đuôi `.jar`.

Khi nâng framework major, đừng hardcode class tên framework loader nội bộ trong Dockerfile hoặc service script nếu có cách launch chính thức ổn định hơn.

## 14. JPMS: modular JAR và chế độ khởi chạy module

Từ Java 9, JPMS cho phép explicit named module có descriptor:

~~~java
module com.acme.order.app {
    requires java.sql;
    requires com.acme.catalog.api;

    exports com.acme.order.api;
}
~~~

Nếu artifact được đặt trên module path và có main class phù hợp, có thể khởi chạy:

~~~bash
java --module-path "mods:lib" \
  --module com.acme.order.app/com.acme.order.app.Main
~~~

Ở đây `com.acme.order.app` là **module name**, còn `com.acme.order.app.Main` là **binary class name**.

### 14.1. -jar và --module khác nhau

| Chế độ | Cách tìm entrypoint | Môi trường |
|---|---|---|
| `java -jar app.jar` | `Main-Class` trong manifest | Chế độ executable JAR |
| `java -cp ... Main` | Tên main class chỉ định trực tiếp | Classpath |
| `java --module m/p.Main` | Module name và main class | JPMS module path |

Một modular JAR có thể cũng chứa main class metadata, nhưng cách khởi chạy quyết định cơ chế resolution. Đặt `module-info.class` trong JAR không có nghĩa nó hoạt động như named module khi JAR được đưa lên classpath.

### 14.2. Module path không phải classpath có cú pháp mới

Named modules có `requires`, `exports`, `opens`, `uses` và `provides`. Không chỉ chuyển toàn bộ JARs từ `-cp` sang `--module-path` rồi giả định mọi class sẽ nhìn thấy nhau.

Có thể gặp:

- Module name không khớp.
- Automatic modules từ JAR chưa modularize.
- Split packages.
- Package chưa được export.
- Deep reflection bị hạn chế.
- ServiceLoader provider nằm trong layer khác.
- Một module có mặt trên module path nhưng chưa được resolve.

Các cờ `--add-modules`, `--add-reads`, `--add-opens` chỉ nên được dùng theo nhu cầu cụ thể và có kế hoạch loại bỏ workaround.

## 15. Multi-release JAR

Multi-release JAR có thể cung cấp class implementations cho các Java runtime khác nhau:

~~~text
META-INF/MANIFEST.MF
com/acme/codec/Parser.class
META-INF/versions/11/com/acme/codec/Parser.class
META-INF/versions/17/com/acme/codec/Parser.class
~~~

Manifest khai báo:

~~~text
Multi-Release: true
~~~

Runtime tương thích có thể lựa chọn versioned entries theo quy tắc specification. Đặc điểm này hữu ích khi thư viện cần giữ Java baseline nhưng tối ưu cho JDK mới.

Rủi ro khi packaging:

- Base classfile vô tình được compile bằng JDK quá cao.
- Versioned entries đặt sai path.
- Manifest thiếu `Multi-Release: true`.
- Shading hoặc repackaging làm mất metadata.
- API/binary contract khác giữa các implementations.
- Không test trên mọi JDK được hỗ trợ.

Multi-release không tự biến mọi class Java 21 thành code chạy được trên Java 8.

## 16. Java bytecode và UnsupportedClassVersionError

Nếu build tạo bytecode quá mới cho runtime:

~~~text
java.lang.UnsupportedClassVersionError
~~~

Một số mốc classfile major:

| Java release | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ class major 65 yêu cầu runtime có khả năng hiểu định dạng classfile tương ứng; Java 17 không đọc được classfile Java 21 thông thường.

Có thể giới hạn compiler target:

~~~bash
javac --release 17 \
  -d build/classes \
  src/main/java/com/acme/app/Main.java
~~~

`--release` kiểm soát Java language/API/classfile target của source đang biên dịch. Nó **không tự kiểm soát classfile version của mọi dependency bên thứ ba**, không bundle JRE và không đảm bảo native libraries tương thích.

### 16.1. Kiểm tra classfile version

~~~bash
javap -verbose \
  -classpath dist/app.jar \
  com.acme.app.Main
~~~

Trong output có major version. Nếu lỗi chỉ xuất hiện khi một feature hiếm được gọi, cần kiểm tra class ở dependency đó chứ không chỉ main class.

## 17. Resource loading từ JAR

Trong project:

~~~text
src/main/
├── java/com/acme/app/Main.java
└── resources/com/acme/app/defaults.properties
~~~

Sau build, resource nên nằm trong JAR:

~~~text
com/acme/app/defaults.properties
~~~

Đọc bằng classpath resource API:

~~~java
try (InputStream in =
         Main.class.getResourceAsStream("defaults.properties")) {
    if (in == null) {
        throw new IllegalStateException("Missing defaults.properties");
    }

    Properties props = new Properties();
    props.load(in);
}
~~~

`Class.getResourceAsStream("defaults.properties")` tìm tương đối với package của class. Dạng có dấu `/` đầu, ví dụ `"/com/acme/app/defaults.properties"`, là absolute resource path theo API Class.

### 17.1. Không tự chuyển resource trong JAR thành File

Code tạo `java.io.File` từ `getResource(...).toURI()` có thể hoạt động khi resource còn ở output directory, nhưng thất bại khi resource được đóng vào JAR. Resource trong archive không nhất thiết có filesystem path độc lập.

Nếu chỉ cần đọc, dùng `getResourceAsStream` hoặc resource abstraction tương ứng. Nếu library thực sự cần file path, có thể phải sao chép stream ra file tạm với quyền truy cập và cleanup được quản lý.

### 17.2. Resource trong named module có thêm quy tắc

Nếu chuyển sang JPMS, cách `ClassLoader` và `Module` tìm một số resource trong named module có thể bị ảnh hưởng bởi encapsulation. Không chỉ nhìn JAR entry tồn tại rồi kết luận mọi caller bên ngoài module đều đọc được file.

## 18. Working directory không tự bằng thư mục chứa JAR

Code:

~~~java
Path path = Path.of("config/application.properties");
~~~

thường resolve theo current working directory của process. Nếu người dùng chạy:

~~~bash
cd /tmp
java -jar /opt/order/app.jar
~~~

thì đường dẫn tương đối trên không tự trở thành `/opt/order/config/application.properties`. Đây là nguồn lỗi rất phổ biến sau khi chuyển từ IDE sang systemd hoặc Docker.

Hướng xử lý:

- Quy định application configuration path tường minh.
- Truyền absolute path qua environment/argument khi phù hợp.
- Đặt working directory trong launcher/service configuration.
- Dùng classpath resource API cho resource đóng trong archive.
- Dùng filesystem API cho file cấu hình ngoài cần thay đổi sau deploy.

Không trộn khái niệm “resource đóng trong JAR” và “external configuration nằm bên cạnh JAR”.

## 19. JVM options phải đứng đúng vị trí

Cú pháp truyền thống:

~~~bash
java [JVM-options] -jar app.jar [application-arguments]
~~~

Ví dụ:

~~~bash
java -Xms256m -Xmx1g \
  -Dapp.env=production \
  -Duser.timezone=UTC \
  -jar app.jar \
  --http-port=8080 --worker-mode
~~~

- `-Xmx1g` là giới hạn Java heap do JVM diễn giải.
- `-Dapp.env=production` là Java system property.
- `--http-port=8080` và `--worker-mode` ở sau JAR là application arguments, do ứng dụng/framework quyết định ý nghĩa.

Nếu chạy:

~~~bash
java -jar app.jar -Xmx1g
~~~

thì chuỗi `-Xmx1g` ở sau JAR không còn là JVM option; nó được chuyển vào `main(String[] args)`.

### 19.1. JVM flags cũ có thể không hợp lệ ở JDK mới

Một script dành cho Java 8 có thể chứa các `-XX` options hoặc GC logging syntax đã thay đổi ở Java 17/21. Sau migration, lỗi có thể xuất hiện trước khi main class được nạp.

Kiểm tra bằng đúng JDK target:

~~~bash
java -version
java --help
java -X
~~~

Đối với advanced flags, theo tài liệu JDK vendor/version. Không thêm `--add-opens` diện rộng chỉ để tránh cảnh báo nếu chưa xác định library nào cần quyền đó.

## 20. Launcher script trên Linux/macOS

Ví dụ một script Bash tương đối đơn giản, trong đó distribution chứa `app.jar` và thư mục `config/`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if [ -n "$JAVA_HOME" ]; then
  JAVA_BIN="$JAVA_HOME/bin/java"
else
  JAVA_BIN="java"
fi

exec "$JAVA_BIN" \
  -Xms256m \
  -Xmx1g \
  -Dapp.config="$APP_DIR/config/application.properties" \
  -jar "$APP_DIR/app.jar" \
  "$@"
~~~

Ví dụ giả định `JAVA_HOME` được khai báo trong môi trường; với Bash bật `set -u`, nếu biến này hoàn toàn chưa được khai báo, phép kiểm tra trực tiếp có thể gây lỗi. Trong production, có thể yêu cầu `JAVA_HOME` bắt buộc, hoặc xử lý riêng biến chưa đặt bằng cách kiểm tra an toàn phù hợp shell. Mục tiêu là minh họa các bước: xác định app directory, chọn Java executable, đặt working directory và truyền arguments.

Các nguyên tắc:

- Quote paths có khoảng trắng.
- Sử dụng `exec` để process Java thay shell khi phù hợp; giúp signal forwarding.
- Giữ exit code thực của Java.
- Không đưa secrets vào script hoặc command line.
- Đảm bảo quyền execute cho script và quyền read cho JAR/config.
- Kiểm tra symbolic-link behavior nếu launcher được đặt qua symlink.

### 20.1. Không cần làm JAR có executable bit

Với:

~~~bash
java -jar app.jar
~~~

Java launcher mở file JAR; JAR không cần có executable bit theo cơ chế shell script. Một số framework hỗ trợ fully executable JAR có script prefix, nhưng đó là chế độ đóng gói riêng, không phải mọi JAR đều chạy như native executable.

## 21. PowerShell launcher trên Windows

Ví dụ:

~~~powershell
$ErrorActionPreference = 'Stop'

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$jar = Join-Path $appDir 'app.jar'

$javaExe = 'java'
if ($env:JAVA_HOME) {
    $javaExe = Join-Path $env:JAVA_HOME 'bin\java.exe'
}

Set-Location -LiteralPath $appDir

& $javaExe '-Xms256m' '-Xmx1g' '-jar' $jar @args
exit $LASTEXITCODE
~~~

Khi triển khai cần chú ý:

- Classpath separator trên Windows là dấu `;`.
- Đường dẫn JDK ở `Program Files` cần được quote đúng.
- Windows service account có environment khác interactive user.
- `WorkingDirectory` của service wrapper có thể khác terminal.
- Quyền file certificate, log và configuration phải được cấp riêng.
- Windows service manager cần biết exit code và recovery policy.

PowerShell script ví dụ không phải thay thế hoàn toàn service wrapper hoặc installer; nó chỉ minh họa cách cố định runtime và arguments.

## 22. systemd service trên Linux

Một unit file minh họa:

~~~ini
[Unit]
Description=Order Java Service
After=network.target

[Service]
Type=simple
User=ordersvc
WorkingDirectory=/opt/order
EnvironmentFile=/etc/order/order.env
ExecStart=/opt/order/runtime/bin/java -Xms256m -Xmx1g -jar /opt/order/app.jar
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

Cần điều chỉnh account, paths, permissions, exit status policy và timeout theo dự án. Không coi một service chạy được trong shell login của developer là bằng chứng nó hoạt động dưới `User=ordersvc`.

Kiểm tra:

- Java executable của đúng JDK.
- File JAR và thư viện ngoài có thể đọc được.
- Working directory và config paths.
- Log output.
- Graceful shutdown và signal handling.
- Network/database readiness.
- Service restart loops và cảnh báo khi startup fail.

Nếu JDK đã được đóng trong runtime image, `ExecStart` có thể trỏ đến Java binary trong image đó để tránh phụ thuộc vào Java toàn cục của host.

## 23. Container và Docker ENTRYPOINT

Một Dockerfile đơn giản cho executable JAR:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /opt/app
COPY build/libs/app.jar /opt/app/app.jar

ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
~~~

Tag image chỉ minh họa; trong production cần chọn version/digest và bản vá được tổ chức phê duyệt.

Các vấn đề thường gặp:

- Container có JDK/JRE version thấp hơn classfile target.
- Copy nhầm thin JAR vào image không có dependencies.
- Copy Spring Boot JAR nhưng dùng lệnh launch không theo Boot loader.
- `WORKDIR` khác môi trường local.
- Native libraries không phù hợp OS/CPU của image.
- Permissions của non-root user.
- Container memory limit không phù hợp `-Xmx`.
- Signal không tới Java do shell-wrapper không `exec`.

Exec-form `ENTRYPOINT` thường giúp process Java nhận tín hiệu trực tiếp hơn so với shell-form có process trung gian; ứng dụng vẫn cần graceful-shutdown logic.

### 23.1. Đừng giả định container có mọi runtime support

Một runtime image tối giản có thể thiếu font, CA certificate, locale/timezone data hoặc native libraries mà ứng dụng cần. Với desktop/media/JNI/TLS use cases, phải kiểm tra các phụ thuộc nền tảng tương ứng.

## 24. jlink và jpackage không chỉ là cách tạo JAR

`jlink` tạo runtime image từ tập named modules thích hợp. `jpackage` tạo application image hoặc installer theo nền tảng và chế độ application được hỗ trợ.

~~~text
Source + Dependencies
         |
         v
Compile/package artifacts
         |
         +--> JAR + java -jar / -cp
         |
         +--> Named modules -> jlink runtime image
         |
         +--> jpackage application image/installer
~~~

Các trường hợp đáng cân nhắc:

- Ứng dụng desktop cần cài đặt không đòi user tự cài JDK.
- Muốn bundle Java runtime với app để kiểm soát version.
- Có launcher, icon, file association, signing/notarization requirements.
- Muốn tạo runtime image theo module graph.

Không phải tất cả automatic modules đều có thể link trực tiếp bằng `jlink` như explicit named modules. Một legacy app với dependencies chưa modularize có thể phải chọn packaging khác hoặc xử lý modularization riêng.

## 25. Class loader và duplicate dependencies

Classpath có thể chứa cùng class name trong nhiều JAR. Thứ tự tìm kiếm, class loader delegation, module layers và framework custom loaders ảnh hưởng class thực sự được sử dụng.

Ví dụ các lỗi:

~~~text
java.lang.NoSuchMethodError
java.lang.ClassNotFoundException
java.lang.NoClassDefFoundError
java.lang.ClassCastException
~~~

Một `NoSuchMethodError` có thể có nghĩa app được compile với library mới nhưng runtime lại nạp library cũ có cùng class name. Không sửa bằng cách thêm một bản dependency thứ ba vào classpath; phải xác định nguồn nạp class.

### 25.1. Xem class được nạp từ đâu

Trên JDK hỗ trợ unified logging:

~~~bash
java -Xlog:class+load=info \
  -jar app.jar
~~~

Log có thể lớn; chỉ bật ở môi trường/phiên được phép và có giới hạn lưu trữ.

Trong mã debug:

~~~java
Class<?> type = com.acme.catalog.CatalogClient.class;

System.out.println(type.getClassLoader());
System.out.println(type.getProtectionDomain().getCodeSource());
~~~

Code source có thể không có URL hữu ích cho mọi loại class, nhưng là một tín hiệu để phân biệt JAR cũ và JAR mới.

### 25.2. ServiceLoader và plugin class loaders

Nếu app có plugin provider trong `META-INF/services`, custom loader hoặc JPMS module layer, cần test cách provider được tìm sau khi đổi packaging. Việc một class tồn tại trong archive không bảo đảm `ServiceLoader` dùng đúng class loader sẽ nhìn thấy provider đó.

## 26. Công cụ kiểm tra artifact và runtime

Một số lệnh hữu ích:

~~~bash
# Xác định Java runtime thật
java -version

# Liệt kê archive
jar --list --file dist/app.jar

# Đọc entrypoint và classfile info
javap -verbose -classpath dist/app.jar com.acme.app.Main

# Phân tích dependency trong bytecode
jdeps --summary dist/app.jar

# Với modular JAR:
jar --describe-module --file dist/app.jar
~~~

Có thể trích xuất `META-INF/MANIFEST.MF` vào thư mục kiểm tra riêng:

~~~bash
mkdir -p inspect
cd inspect
jar --extract --file ../dist/app.jar META-INF/MANIFEST.MF
~~~

Đường dẫn là ví dụ; đảm bảo `../dist/app.jar` thực sự tồn tại theo vị trí thư mục. Tránh extract vào production directory vì lệnh có thể tạo/ghi đè entry files.

`jdeps` phân tích dependency tĩnh; nó không tự phát hiện mọi class được nạp bằng reflection, SPI, JNI hoặc plugin configuration. Do đó phải kết hợp runtime tests.

## 27. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân cần xét | Kiểm tra đầu tiên |
|---|---|---|
| `no main manifest attribute` | Không có `Main-Class` | Manifest của đúng JAR |
| `Could not find or load main class` | Tên class hoặc classpath sai | Class entries và launch mode |
| `NoClassDefFoundError` | Dependency thiếu hoặc class init fail | Nested causes, runtime classpath |
| `UnsupportedClassVersionError` | JVM thấp hơn bytecode target | `java -version`, `javap` |
| `NoSuchMethodError` | Binary dependency mismatch | Class source và resolved versions |
| `ClassCastException` giữa kiểu cùng tên | Class loader identity khác | Defining loaders |
| `ServiceConfigurationError` | Provider metadata/load lỗi | `META-INF/services` và module graph |
| Invalid signature digest | Shading làm chữ ký cũ không phù hợp | Packaging/signing |
| `InaccessibleObjectException` | Reflection bị hạn chế | JDK/module access và library version |
| `FindException` / `ResolutionException` | Module graph lỗi | Module path, names, split packages |
| `FileNotFoundException` sau deploy | Working directory, resource path | `user.dir`, JAR contents, permissions |
| Native `UnsatisfiedLinkError` | Thiếu/sai OS-CPU library | Runtime image, native dependencies |
| App chạy local nhưng fail systemd | Service account/env/cwd khác | Unit, logs, permissions |
| App chạy IDE nhưng fail container | Image JDK/JAR variant khác | Dockerfile, checksums, classpath |
| JVM không khởi động | JVM flags cũ/sai syntax | Java options và target version |

Bảng trên chỉ định hướng. Một lỗi class loading có thể có nhiều nguyên nhân; cần đọc toàn bộ stack trace, root cause và xác định artifact thực sự được chạy.

## 28. Tách lỗi build, packaging, launcher và runtime

Để không sửa nhầm tầng, phân loại:

1. **Build:** mã có biên dịch dưới JDK/toolchain đang chọn không?
2. **Package:** output JAR có entrypoint, resources, metadata và deps đúng không?
3. **Launch:** đúng Java executable, launch mode, options, paths và arguments chưa?
4. **Runtime:** class loading, reflection, TLS, native libraries và config có đúng?
5. **Operation:** service account, health checks, logs, shutdown, restart và rollback có đúng?

Ví dụ:

- Build xanh, `java -jar` báo thiếu manifest: lỗi packaging/entrypoint.
- Manifest đúng nhưng thiếu client library: lỗi runtime distribution.
- Ở CI chạy được, systemd không thấy config file: lỗi working directory/config path.
- Java 17 chạy được, Java 11 báo classfile 61: lỗi runtime version.
- Chỉ Linux AArch64 gặp `UnsatisfiedLinkError`: cần xem native artifact/platform.

## 29. Security và artifact provenance

Packaging ảnh hưởng chuỗi cung ứng phần mềm:

- Runtime/JDK image có version hoặc digest được chọn rõ?
- Dependency và plugin versions có được quản lý?
- JAR output có checksum và nguồn commit tương ứng?
- Shading có xử lý đúng chữ ký và license metadata?
- Launcher có tải JAR ngoài từ nguồn chưa tin cậy?
- Secrets có bị đặt trên command line, script hoặc logs?
- File permissions có bảo vệ config, key/trust stores và logs?
- CI có chạy đúng artifact được publish, thay vì build một bản khác khi deploy?

Một file tên `app.jar` không chứng minh nó được build từ commit mong đợi. Với release pipeline nên lưu artifact SHA-256 và các thông tin JDK/Wrapper/build provenance phù hợp chính sách.

### 29.1. Reproducible build

JARs có thể khác byte-for-byte do timestamps, entry order, source encoding, JDK, plugin hoặc dependency khác. Maven/Gradle cung cấp các cơ chế hỗ trợ reproducible archive builds, nhưng phải cấu hình theo đúng version và kiểm chứng output.

Wrapper cố định build tool distribution; nó không tự cố định JDK, toàn bộ plugin hoặc OS, nên không phải điều kiện đủ cho build reproducibility.

## 30. Logging, process lifecycle và graceful shutdown

Một launcher production cần quan tâm nhiều hơn entrypoint:

- stdout/stderr được thu thập và rotation đúng.
- Exit code thực được trả về cho systemd/CI/container.
- Java process nhận SIGTERM và xử lý shutdown.
- Database connections và broker consumers được đóng có kiểm soát.
- Health/readiness không báo thành công quá sớm.
- Service account có đúng filesystem/network permissions.
- Không có restart loop bị che bởi monitoring thiếu.
- Heap và native memory không vượt container limits.

Trong Unix shell, dùng `exec java ...` có thể giúp shell không giữ vai trò process trung gian, nhưng ứng dụng vẫn phải thực hiện shutdown logic.

### 30.1. Java flags trong container

Đừng copy nguyên `-Xmx` từ máy bare-metal vào container có memory limit thấp hơn. Khi nâng JDK, cần kiểm tra defaults và ergonomics liên quan heap/GC. Một startup xanh nhưng bị OOM kill sau tải thực không phải kết quả migration thành công.

## 31. Lộ trình migration JAR và launcher

### Giai đoạn 1 — Baseline

Ghi:

- Source commit, artifact name và checksum.
- JDK vendor/version của build và runtime.
- Maven/Gradle Wrapper/plugins.
- Manifest và artifact layout.
- Runtime dependencies, agents, native libraries.
- Cách chạy thực tế trong IDE, terminal, service/container.
- JVM args, environment và external config paths.
- Logs, health, shutdown và test results.

### Giai đoạn 2 — Chọn artifact type

Quyết định một trong các mô hình:

- Plain library JAR.
- Thin executable JAR với `Class-Path` manifest.
- Distribution có thư mục `lib/` + launcher script.
- Uber/shaded JAR.
- Framework-specific executable JAR.
- Modular JAR và module-path launcher.
- Runtime image/installer.

Lựa chọn dựa trên dependencies, platform, tooling và vận hành, không phải vì “fat JAR luôn tốt nhất”.

### Giai đoạn 3 — Chuyển JDK/build tool

Nâng Maven/Gradle plugin và JDK target theo ma trận hỗ trợ. Kiểm tra bytecode target, runtime dependencies và các JVM flags cũ. Tránh đồng thời đổi framework major nếu có thể tách.

### Giai đoạn 4 — Đọc output thật

Kiểm tra manifest, class entries, resources, dependencies, service metadata và checksum. Không chỉ nhìn cấu hình dự kiến trong POM/Gradle.

### Giai đoạn 5 — Chạy production-like

Chạy trên máy/container sạch bằng đúng launcher, account, working directory và runtime version. Thử API/database/broker/TLS và graceful shutdown.

### Giai đoạn 6 — Rollout và rollback

Triển khai canary hoặc phân nhóm nhỏ. Khi rollback, khôi phục **đúng bộ artifact + dependencies + JDK runtime + config/launcher**. Nếu migration đã thay database/message/session format, cần rollback dữ liệu riêng.

## 32. Ví dụ tổng hợp: thin JAR Java 8 sang Java 21

Hệ thống cũ:

~~~text
/opt/legacy/
├── service.jar
├── lib/
│   ├── http-client.jar
│   └── json-codec.jar
├── config/
│   └── application.properties
└── start.sh
~~~

Cách chạy cũ:

~~~bash
java -Xmx512m -cp "service.jar:lib/*" \
  com.acme.service.Main
~~~

Đội dự án muốn tạo JAR có `Main-Class` và đổi thành:

~~~bash
java -jar service.jar
~~~

Nếu không có manifest `Class-Path` và không dùng packaging mới, JVM có thể không nạp `lib/http-client.jar` và `lib/json-codec.jar`. Kết quả là `NoClassDefFoundError` hoặc lỗi khi code gọi API của dependency.

Lộ trình có thể là:

1. Xác nhận JAR cũ là thin JAR, ghi đầy đủ runtime classpath.
2. Kiểm tra manifest, classfile target và JDK baseline.
3. Đối chiếu dependency/framework support với JDK 21.
4. Chọn giữ classpath distribution, tạo thin executable manifest có Class-Path, hoặc shaded/framework JAR đúng cách.
5. Đảm bảo build plugin thực sự tạo artifact type được chọn.
6. Test runtime ở thư mục khác `user.dir` của developer.
7. Test external configuration, service metadata và class loading.
8. Chạy trong container/systemd với runtime Java 21 thật.
9. Theo dõi startup, health, GC, DB/TLS, shutdown.
10. Chuẩn bị rollback gồm launcher, JAR, thư mục `lib` và JDK cũ.

**Không cần đổi sang fat JAR nếu classpath distribution được quản lý tốt.** Điều cốt yếu là artifact topology và launcher phải phù hợp với nhau.

## 33. Các nhận định dễ sai

**“Mọi JAR có thể chạy bằng `java -jar`.”** Không. JAR thường dùng làm dependency có thể không có entrypoint.

**“Có Main-Class nghĩa là JAR đã chứa dependencies.”** Sai. Manifest không tự đóng gói thư viện.

**“`java -cp lib/* -jar app.jar` sẽ thêm thư viện cho executable JAR.”** Không nên dựa vào giả định này; `-jar` có cơ chế user classpath riêng.

**“Manifest Class-Path dựa theo current working directory.”** Sai về nguyên tắc; relative URLs của manifest được resolve liên quan đến JAR.

**“Shaded JAR luôn tương đương mọi JAR gốc cộng lại.”** Sai. Cần merge SPI/metadata và xử lý chữ ký, duplicate resources, relocation.

**“Spring Boot executable JAR là plain JAR có dependency classes dưới root.”** Không. Nó thường có nested JARs và loader riêng.

**“Một JAR build bằng JDK 21 sẽ tự chạy được trên Java 17.”** Không nếu bytecode/API/dependencies yêu cầu runtime cao hơn.

**“Đổi executable path sang JDK mới là đủ để migrate.”** Không. JVM flags, TLS, classloading, agents và native dependencies cũng quan trọng.

**“Chạy trong IDE là bằng chứng deployment đúng.”** Không. IDE có thể cấu hình classpath/JDK/working directory mà bản phát hành không có.

**“Ứng dụng khởi động được nghĩa là production đã sẵn sàng.”** Chưa đủ nếu chưa test integrations, health, shutdown và rollback.

## 34. Checklist trước khi hoàn tất

- [ ] Đã xác định JAR là library, thin executable, shaded, Spring Boot nested hay modular.
- [ ] Đã kiểm tra manifest thực sự trong artifact đầu ra.
- [ ] Đã xác nhận `Main-Class` hoặc framework launcher hợp lệ.
- [ ] Đã phân biệt `Main-Class` và metadata riêng như `Start-Class`.
- [ ] Đã xác nhận bytecode và dependencies tương thích JDK runtime đích.
- [ ] Đã biết runtime classpath/module path thực tế.
- [ ] Đã kiểm tra `Class-Path` manifest và relative locations.
- [ ] Đã xử lý service provider metadata, duplicate classes/resources và chữ ký khi shading.
- [ ] Đã kiểm tra native libraries theo OS/CPU.
- [ ] Đã xác nhận resources được đóng gói và load đúng qua classloader/module.
- [ ] Đã phân biệt resource trong JAR và external config file.
- [ ] Đã kiểm tra working directory trong terminal, systemd và container.
- [ ] Đã đặt JVM options trước `-jar` và application arguments ở vị trí phù hợp.
- [ ] Đã rà soát flags cũ không được JDK đích hỗ trợ.
- [ ] Đã xác minh Java executable được launcher thực sự chọn.
- [ ] Đã kiểm tra Windows/Unix quoting, script permissions và service account.
- [ ] Đã kiểm tra Docker ENTRYPOINT, runtime image và non-root permissions.
- [ ] Đã kiểm tra classloader, SPI, JPMS nếu ứng dụng dùng.
- [ ] Đã chạy clean-machine/production-like smoke tests.
- [ ] Đã kiểm tra logs, health checks, graceful shutdown và exit codes.
- [ ] Đã lưu artifact digest và build/runtime metadata.
- [ ] Đã có kế hoạch rollout/rollback theo cả JAR và dependencies/runtime/config.
- [ ] Đã phân biệt lỗi build, package, launch và runtime khi điều tra.

## 35. Kết luận

**JAR thường, executable JAR và launcher là ba tầng không thể đồng nhất**. JAR thường là archive chứa class/resource; executable JAR khai báo entrypoint nhưng không đương nhiên gom dependencies; còn launcher xác định Java runtime, classpath/module path, JVM options, arguments, working directory và process lifecycle.

Trong Java Advance Compatibility Migration, phải kiểm chứng **artifact cuối cùng** và lệnh chạy thật. Thin JAR, shaded/uber JAR, Spring Boot nested archive và modular JAR có cơ chế nạp class khác nhau. Thay JDK hoặc build plugin mà không rà soát packaging dễ tạo lỗi chỉ xuất hiện ở production.

Một lần chuyển đổi thành công là khi cùng phiên bản ứng dụng được build có thể tái tạo, có dependencies/resources đúng, chạy trên runtime đã phê duyệt, có logging/health/shutdown phù hợp và có phương án rollback được kiểm thử. **Đích đến không chỉ là tạo được file `.jar`, mà là vận hành chính xác và an toàn toàn bộ bản phân phối Java.**
