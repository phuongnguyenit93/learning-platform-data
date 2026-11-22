# Tìm nguyên nhân tài nguyên có khi chạy IDE nhưng thiếu trong JAR

Một ứng dụng Spring Boot có thể chạy bình thường trong IntelliJ IDEA, Eclipse hoặc VS Code nhưng báo không tìm thấy file khi chạy bằng `java -jar app.jar`. Nguyên nhân thường nằm ở sự khác biệt giữa **classpath mà IDE tạo ra** và **những file thực sự được Gradle/Maven đóng gói vào JAR**.

Trong IDE, resource có thể được lấy trực tiếp từ thư mục source, thư mục generated hoặc một resource root được cấu hình riêng. Khi đóng gói, build tool chỉ đưa vào artifact những resource thuộc source set/resource directory và vượt qua các quy tắc include, exclude, filtering, copy và packaging của build.

Cách chẩn đoán hiệu quả là kiểm tra theo đúng đường đi:

~~~text
Resource trong project
       |
       v
Được khai báo trong main resource source set?
       |
       v
Gradle processResources / Maven process-resources
       |
       v
build/resources/main hoặc target/classes
       |
       v
bootJar / package
       |
       v
BOOT-INF/classes/ trong executable Spring Boot JAR
       |
       v
ClassLoader / Spring Resource API khi chạy java -jar
~~~

**Nguyên tắc quan trọng:** resource được tìm thấy trên filesystem trong IDE chưa chứng minh resource đã có trong JAR. Hãy kiểm tra artifact thật bằng `jar tf` và đọc resource qua classpath API, thay vì phụ thuộc đường dẫn source như `src/main/resources/...` lúc runtime.

## 1. Phân biệt resource, source code và classpath

### 1.1. Resource là dữ liệu được ứng dụng đọc lúc chạy

Resource có thể là:

- `application.properties` hoặc `application.yml`.
- JSON/XML/YAML dùng làm cấu hình hoặc dữ liệu mẫu.
- HTML template, email template và file localization.
- Ảnh, font, CSS, JavaScript, file schema hoặc certificate public.
- File SQL migration, message bundle hoặc dữ liệu khởi tạo.
- Metadata như `META-INF/services/...`.

Java source (`.java`) được compiler biến thành class files (`.class`). Resource không phải Java source; build tool copy/transform chúng vào output directory và đưa vào runtime classpath.

Ví dụ cấu trúc thông dụng:

~~~text
orders-api/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/orders/OrdersApplication.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── config/
│   │       │   └── pricing-rules.json
│   │       ├── templates/
│   │       │   └── receipt.html
│   │       └── static/
│   │           ├── app.css
│   │           └── logo.svg
│   └── test/
│       └── resources/
│           └── fixtures/orders.json
├── build.gradle
└── settings.gradle
~~~

`src/main/resources` là vị trí mặc định cho resources của production/main source set trong Gradle Java plugin và Maven project thông thường. `src/test/resources` dành cho test classpath; không mặc định được đưa vào executable production JAR.

### 1.2. IDE có thể đang thêm resource directory riêng

IDE thường import cấu hình Gradle/Maven và đánh dấu thư mục resource root. Nhưng project có thể còn cấu hình thủ công:

- Một thư mục ngoài project được đánh dấu là Resources Root.
- Một folder local không được commit hoặc đang bị Git ignore.
- Một thư mục generated được IDE tạo trước khi chạy.
- Một module khác được thêm vào IDE classpath.
- Một file có mặt trong output directory cũ còn sót từ lần build trước.

Vì vậy, chạy trong IDE thành công có thể chỉ chứng minh **IDE runtime classpath có file đó**. CI chạy clean build hoặc JAR đã đóng gói có thể không có file.

Hãy ưu tiên cấu hình resource trong Gradle/Maven để IDE import lại đúng source set. Không dựa vào một resource root chỉ tồn tại trong cấu hình cục bộ của IDE.

### 1.3. Classpath không đồng nghĩa thư mục làm việc

Classpath là tập các directory/JAR mà class loader tìm class và resource. Working directory là thư mục process đang chạy, thường được thể hiện bởi `user.dir`.

Ví dụ:

~~~text
Working directory: /srv/orders
Classpath:
  /srv/orders/app.jar
  (các nested dependencies của Spring Boot Loader)
~~~

Một file tương đối như `config/pricing-rules.json` được mở bằng `Files.readString(Path.of(...))` sẽ được tìm tương đối với working directory. Nó không tự động được tìm trong JAR.

Ngược lại, `ClassLoader.getResource("config/pricing-rules.json")` tìm resource trong classpath, bất kể JAR đang nằm ở thư mục nào. Hai cách truy cập này giải quyết hai loại resource khác nhau.

## 2. Spring Boot executable JAR đặt resource ở đâu?

Với Spring Boot executable JAR, application classes và resources được đặt trong `BOOT-INF/classes`; dependencies nằm trong `BOOT-INF/lib`.

~~~text
orders-api.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    │   ├── application.yml
    │   ├── config/pricing-rules.json
    │   ├── templates/receipt.html
    │   ├── static/app.css
    │   └── com/example/orders/OrdersApplication.class
    └── lib/
        ├── spring-boot-*.jar
        └── other-dependency.jar
~~~

Đây là layout minh họa. File thực tế phụ thuộc artifact, plugin version và nội dung project. Spring Boot Loader biết cách đưa `BOOT-INF/classes` và nested dependency JARs vào runtime classpath khi chạy executable archive. <Link ref="turn698805search1" title="Spring Boot: Nested JARs"/>.

**Không thêm prefix `BOOT-INF/classes/` vào resource lookup trong Java code.** Đây là vị trí vật lý bên trong executable archive. Ứng dụng vẫn yêu cầu resource theo classpath-relative name:

~~~java
Resource resource = new ClassPathResource("config/pricing-rules.json");
~~~

hoặc:

~~~java
InputStream input = getClass()
        .getClassLoader()
        .getResourceAsStream("config/pricing-rules.json");
~~~

### 2.1. JAR thường và executable Spring Boot JAR khác nhau

Một JAR Java thông thường có thể đặt classes/resources ở root:

~~~text
library.jar
├── com/example/SomeClass.class
└── config/library.properties
~~~

Executable Spring Boot JAR có application classes/resources dưới `BOOT-INF/classes` và nested dependencies dưới `BOOT-INF/lib`. Không dùng code tự mở outer JAR rồi tìm `config/...` ở root nếu resource thực tế ở `BOOT-INF/classes/config/...`.

Khi cần đọc resource, dùng classpath API để Spring Boot Loader xử lý layout. Khi cần kiểm tra vị trí đóng gói, dùng `jar tf` để xem archive entries.

### 2.2. Executable WAR

Với executable WAR, application classes/resources thường nằm dưới `WEB-INF/classes`; dependencies nằm trong `WEB-INF/lib` và có thể có `WEB-INF/lib-provided`. Nếu ứng dụng được triển khai vào servlet container, cách container xử lý WAR và classloader có thể khác chạy executable WAR độc lập. <Link ref="turn698805search1" title="Spring Boot executable JAR and WAR layout"/>.

## 3. Cách load resource đúng trong Java

### 3.1. Dùng `ClassLoader.getResourceAsStream`

Với resource ở classpath root:

~~~java
InputStream input = getClass()
        .getClassLoader()
        .getResourceAsStream("config/pricing-rules.json");
~~~

Tên truyền vào `ClassLoader`:

- Dùng dấu slash xuôi `/` làm separator.
- Không bắt đầu bằng slash.
- Được tính từ classpath root.
- Phải đúng chữ hoa/chữ thường với entry trong JAR.

Nếu resource không tồn tại, method trả về `null`. Luôn kiểm tra và báo lỗi có tên resource cụ thể.

### 3.2. Dùng `Class.getResourceAsStream`

Với `Class`, đường dẫn có hai kiểu:

~~~java
// Absolute từ classpath root:
InputStream rootResource =
        OrdersApplication.class.getResourceAsStream(
                "/config/pricing-rules.json");

// Relative với package của class:
InputStream packageResource =
        OrdersApplication.class.getResourceAsStream(
                "defaults.json");
~~~

Nếu class ở `com.example.orders` thì path tương đối `defaults.json` được tìm ở `com/example/orders/defaults.json`. Dấu slash đầu tiên khiến lookup bắt đầu từ root. Đây là một nguyên nhân hay gặp khi code đổi từ `ClassLoader` sang `Class` nhưng vẫn giữ nguyên path.

JDK mô tả resource name là đường dẫn phân tách bằng `/` và `getResourceAsStream` trả `null` nếu không tìm thấy hoặc không thể truy cập resource. <Link ref="turn698805search0" title="Java 17 ClassLoader API"/>.

### 3.3. Ví dụ đầy đủ: Java 17 resource probe

Chương trình này kiểm tra resource có mặt trong runtime classpath và đọc nội dung bằng stream. Nó chạy độc lập, không cần Spring.

Cấu trúc:

~~~text
resource-probe/
├── src/main/java/com/example/resourceprobe/ResourceProbe.java
└── src/main/resources/config/app.properties
~~~

File `src/main/resources/config/app.properties`:

~~~properties
app.name=resource-demo
app.mode=packaged
~~~

File `src/main/java/com/example/resourceprobe/ResourceProbe.java`:

~~~java
package com.example.resourceprobe;

import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class ResourceProbe {

    private static final String RESOURCE =
            "config/app.properties";

    private ResourceProbe() {
    }

    public static void main(String[] args) throws IOException {
        ClassLoader loader =
                ResourceProbe.class.getClassLoader();

        URL location = loader.getResource(RESOURCE);
        System.out.println("RESOURCE_URL_FOUND=" +
                (location != null));

        if (location == null) {
            System.err.println(
                    "RESOURCE_MISSING=" + RESOURCE);
            System.exit(1);
            return;
        }

        try (InputStream input =
                     loader.getResourceAsStream(RESOURCE)) {
            if (input == null) {
                System.err.println(
                        "RESOURCE_STREAM_MISSING=" + RESOURCE);
                System.exit(1);
                return;
            }

            String content = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);

            String normalized = content
                    .replace("\r\n", "\n")
                    .replace('\r', '\n')
                    .strip()
                    .replace("\n", ";");

            System.out.println(
                    "RESOURCE_CONTENT=" + normalized);
        }
    }
}
~~~

Biên dịch và chạy trực tiếp bằng JDK 17 trên Linux/macOS:

~~~bash
mkdir -p out
javac -d out src/main/java/com/example/resourceprobe/ResourceProbe.java
cp -R src/main/resources/. out/
java -cp out com.example.resourceprobe.ResourceProbe
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out .\src\main\java\com\example\resourceprobe\ResourceProbe.java
Copy-Item -Recurse .\src\main\resources\* .\out\
java -cp out com.example.resourceprobe.ResourceProbe
~~~

Stdout khi resource tồn tại:

~~~text
RESOURCE_URL_FOUND=true
RESOURCE_CONTENT=app.name=resource-demo;app.mode=packaged
~~~

Nếu thiếu file, chương trình in:

~~~text
RESOURCE_URL_FOUND=false
~~~

và thoát với exit code 1. Khi resource có mặt nhưng stream không mở được, chương trình báo `RESOURCE_STREAM_MISSING`. Ví dụ đọc bytes bằng `InputStream` nên không giả định resource là một file vật lý trên disk.

### 3.4. Dùng Spring `ClassPathResource`

Trong Spring application, có thể dùng:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;

public class PricingRulesReader {

    public String read() throws IOException {
        ClassPathResource resource =
                new ClassPathResource(
                        "config/pricing-rules.json");

        if (!resource.exists()) {
            throw new IllegalStateException(
                    "Missing classpath resource: " +
                    "config/pricing-rules.json");
        }

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
~~~

`ClassPathResource` dùng classloader hoặc class được chỉ định để tìm resource. Nó hỗ trợ stream và URL. Nhưng một resource nằm bên trong JAR chưa giải nén **không nhất thiết có thể chuyển thành `java.io.File`**. Spring docs nêu rõ `getFile()` chỉ phù hợp khi resource thực sự nằm trên filesystem; với resource trong JAR nên dùng `getInputStream()` hoặc URL. <Link ref="turn388927search0" title="Spring Framework Resource abstraction"/>.

### 3.5. Không dùng đường dẫn source trong production code

Đây là cách dễ chạy trong IDE nhưng thường sai khi chạy JAR:

~~~java
Path path = Path.of(
        "src/main/resources/config/app.properties");
String content = Files.readString(path);
~~~

Đường dẫn này chỉ trỏ tới file trong project working directory nếu folder đó có mặt. Sau khi chỉ giao JAR cho máy chủ, source tree không nhất thiết tồn tại.

Nếu dữ liệu phải là resource đóng gói, dùng classpath API. Nếu dữ liệu cần được quản trị bên ngoài (ví dụ file cấu hình thay đổi theo environment, upload hoặc dữ liệu lớn), dùng filesystem path được cấu hình rõ, mount volume hoặc external configuration.

## 4. Gradle: resource đi qua `processResources` như thế nào?

Gradle Java plugin tạo source set `main` và task `processResources`. Mặc định, task copy resources từ `src/main/resources` sang `build/resources/main`. Output được đưa vào main runtime classpath và JAR packaging. Với source set khác, task có tên `process<SourceSet>Resources`. <Link ref="turn698805search2" title="Gradle Java projects: Managing resources"/>.

~~~text
src/main/resources/
        |
        v
  processResources
        |
        v
build/resources/main/
        |
        +----> test/runtime classpath
        |
        +----> bootJar
                    |
                    v
          BOOT-INF/classes/
~~~

### 4.1. Xem resource output trước khi đóng gói

Linux/macOS:

~~~bash
./gradlew clean processResources
find build/resources/main -type f
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean processResources
Get-ChildItem -Recurse .\build\resources\main
~~~

Nếu resource không có trong `build/resources/main`, vấn đề nằm trước hoặc trong `processResources`: source directory, source set, include/exclude, generated resource hoặc task ordering.

Nếu file có trong output nhưng không có trong JAR, kiểm tra bước packaging, cấu hình `bootJar`/`jar`, task custom và file archive thực tế.

### 4.2. Khai báo resource directory bổ sung

Nếu resources nằm ở folder riêng, khai báo nó trong source set:

~~~groovy
sourceSets {
    main {
        resources {
            srcDir 'src/main/config-resources'
        }
    }
}
~~~

Giờ Gradle sẽ đưa cả resources từ directory mặc định và directory bổ sung vào main resource output. Tránh chỉ cấu hình folder trong IDE; Gradle build phải biết folder đó.

### 4.3. Include và exclude có thể loại resource

Ví dụ cấu hình:

~~~groovy
tasks.named('processResources') {
    exclude '**/*.bak'
    exclude 'local-only/**'
}
~~~

Nếu resource cần thiết vô tình khớp pattern exclude, nó sẽ không được copy. Khi có include patterns, chỉ các file khớp include mới được đưa vào output.

`ProcessResources` hỗ trợ các properties `includes` và `excludes`; kiểm tra toàn bộ cấu hình build script, convention plugins và parent build logic. <Link ref="turn388927search1" title="Gradle ProcessResources API"/>.

### 4.4. Resource được generate trong build

Nếu IDE tự tạo file trước khi chạy, nhưng Gradle không tạo file đó trong task graph, JAR sẽ thiếu resource. Hãy đăng ký output directory và task dependency rõ ràng.

Ví dụ minh họa:

~~~groovy
def generatedResourcesDir =
        layout.buildDirectory.dir(
                'generated/resources/main')

tasks.register('generateAppResources', Copy) {
    from 'src/resource-templates'
    into generatedResourcesDir
}

sourceSets {
    main {
        resources {
            srcDir generatedResourcesDir
        }
    }
}

tasks.named('processResources') {
    dependsOn tasks.named('generateAppResources')
}
~~~

Đây là ví dụ cho trường hợp template files được copy vào generated resources. Nếu nội dung cần được tạo động, thay `Copy` bằng task phù hợp và khai báo output bằng Gradle Provider để Gradle hiểu dependency graph. Không ghi file generated trực tiếp vào `src/main/resources` khi build.

### 4.5. Filtering trong Gradle

Gradle Copy/ProcessResources có thể biến đổi text resources bằng `expand` hoặc filters. Nếu build script thay placeholder theo project property, file đóng gói có thể khác file trong IDE.

Ví dụ:

~~~groovy
tasks.named('processResources') {
    filesMatching('build-info.properties') {
        expand(version: project.version)
    }
}
~~~

Chỉ dùng filtering cho các file text được thiết kế có placeholder. Không áp dụng filtering lên ảnh, font, PDF, binary hoặc file đã nén; nội dung có thể bị hỏng. Cẩn thận với placeholder dạng dollar-brace của Spring: nếu Gradle filtering cũng nhận delimiter đó, build có thể thay giá trị hoặc báo lỗi trước khi Spring runtime xử lý.

## 5. Maven: resource từ `src/main/resources` đến `target/classes`

Maven Resources Plugin chạy ở phase `process-resources` của default lifecycle. Theo cấu hình chuẩn, resources được copy từ `src/main/resources` sang `target/classes`; sau đó JAR/WAR packaging đưa chúng vào archive.

~~~text
src/main/resources/
        |
        v
maven-resources-plugin
        |
        v
target/classes/
        |
        v
maven-jar-plugin / spring-boot-maven-plugin
        |
        v
Executable Boot JAR
        |
        v
BOOT-INF/classes/
~~~

### 5.1. Kiểm tra output của Maven

~~~bash
mvn clean process-resources
find target/classes -type f
~~~

PowerShell:

~~~powershell
mvn clean process-resources
Get-ChildItem -Recurse .\target\classes
~~~

Nếu file không có ở `target/classes`, kiểm tra `<resources>`, resource directory, include/exclude, filtering và lifecycle executions.

### 5.2. Override `<resources>` có thể làm mất folder mặc định

Khi POM khai báo `<build><resources>`, danh sách đó quyết định các resource directories được dùng. Nếu chỉ khai báo một folder custom mà quên `src/main/resources`, các resource mặc định có thể biến mất khỏi output.

Ví dụ khai báo tường minh:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/config-resources</directory>
            <filtering>false</filtering>
        </resource>
    </resources>
</build>
~~~

Đây là cấu hình khi cả hai folder đều cần được đóng gói. Không thêm source directory chỉ để IDE nhìn thấy file; hãy xác định resource thực sự thuộc module/variant nào.

### 5.3. Include và exclude

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
            <excludes>
                <exclude>**/*.bak</exclude>
                <exclude>local-only/**</exclude>
            </excludes>
        </resource>
    </resources>
</build>
~~~

Kiểm tra `<includes>`, `<excludes>` và các execution của Maven Resources Plugin. Một file khớp exclude sẽ không có ở `target/classes`. Tài liệu Maven có ví dụ chính thức về include/exclude resource files. <Link ref="turn698805search4" title="Maven Resources Plugin: Include and Exclude"/>.

### 5.4. Filtering trong Maven

Maven resource filtering thay các placeholder dạng dollar-brace (ví dụ biến `name`) hoặc `@name@` bằng project/system/filter properties. Mặc định filtering của resource thường tắt; khi bật, file text đầu ra có thể khác file source. <Link ref="turn698805search6" title="Maven: Filtering Resources"/>.

Không filter binary files như ảnh, PDF hoặc font; Maven cảnh báo điều đó có thể làm hỏng nội dung. Nếu cần filter text, tách riêng folder filtered và non-filtered:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/resources-filtered</directory>
            <filtering>true</filtering>
            <includes>
                <include>**/*.properties</include>
                <include>**/*.yml</include>
            </includes>
        </resource>
    </resources>
</build>
~~~

Nếu `application.yml` có Spring placeholders (ví dụ biến môi trường `DATABASE_URL` theo cú pháp dollar-brace), kiểm tra delimiter filtering để chúng còn nguyên cho Spring xử lý lúc runtime. Không bake database URL/secret theo environment vào artifact.

## 6. Kiểm tra chính JAR, không chỉ build output

### 6.1. Liệt kê nội dung JAR

Với Gradle:

~~~bash
./gradlew clean bootJar
jar tf build/libs/orders-api.jar
~~~

Với Maven:

~~~bash
mvn clean package
jar tf target/orders-api.jar
~~~

Tên file có thể bao gồm version, ví dụ `orders-api-1.8.0.jar`; dùng đúng tên output thực tế.

Trong executable Spring Boot JAR, tìm:

~~~text
BOOT-INF/classes/application.yml
BOOT-INF/classes/config/pricing-rules.json
BOOT-INF/classes/static/app.css
BOOT-INF/classes/templates/receipt.html
~~~

Nếu resource không có trong `jar tf` output, classloader không thể tìm nó từ JAR đó. Quay lại kiểm tra source set/processResources hoặc packaging.

### 6.2. Tìm một resource cụ thể

Linux/macOS:

~~~bash
jar tf build/libs/orders-api.jar | grep 'pricing-rules.json'
~~~

Windows PowerShell:

~~~powershell
jar tf .\build\libs\orders-api.jar | Select-String 'pricing-rules.json'
~~~

Kết quả mong đợi cho Boot JAR:

~~~text
BOOT-INF/classes/config/pricing-rules.json
~~~

Nếu không có dòng nào, resource chưa được đóng gói. Nếu có nhiều dòng cùng tên, có thể tồn tại resource trùng ở application và dependency JAR; cần kiểm tra classloader resolution.

### 6.3. Đọc nội dung resource từ JAR để đối chiếu

Có thể dùng JDK tools hoặc công cụ ZIP phù hợp để kiểm tra. Với executable Boot JAR, resource application nằm dưới `BOOT-INF/classes`:

~~~bash
unzip -p build/libs/orders-api.jar BOOT-INF/classes/config/pricing-rules.json
~~~

Lệnh này chỉ đọc entry của outer archive. Không dùng `unzip -p` theo đường dẫn classpath root `config/...` nếu file thực tế nằm trong `BOOT-INF/classes/config/...`.

Nếu resource nằm trong một nested dependency JAR dưới `BOOT-INF/lib`, cần mở nested JAR tương ứng để kiểm tra entry. Đừng nhầm resource của application với resource được cung cấp bởi một library.

### 6.4. So sánh IDE, build output và JAR

| Điểm kiểm tra | Resource tồn tại? | Kết luận |
| --- | --- | --- |
| Project source directory | Có | File tồn tại trong workspace |
| IDE runtime classpath | Có | IDE biết resource root hoặc có file output |
| Gradle `build/resources/main` / Maven `target/classes` | Có | Resource processing đã copy file |
| `BOOT-INF/classes/` trong JAR | Có | Resource đã đóng gói trong application archive |
| Runtime `getResourceAsStream` | Có | Classloader tìm và mở được resource |

Cách xác định vùng lỗi:

- Có ở source nhưng không có ở IDE classpath: cấu hình IDE/module/source root.
- Có trong IDE nhưng không có ở Gradle/Maven output: build configuration, generated task, includes/excludes hoặc resource folder.
- Có ở build output nhưng thiếu trong JAR: packaging task hoặc custom archive configuration.
- Có trong JAR nhưng lookup trả null: sai resource path, sai chữ hoa/thường, classloader/module hoặc đang chạy nhầm JAR.
- Lookup được nhưng parse lỗi: encoding, nội dung filtering hoặc parser/configuration, không phải lỗi thiếu file.

## 7. Những nguyên nhân thường gặp khiến IDE chạy nhưng JAR thiếu resource

### 7.1. Resource nằm nhầm source set

`src/test/resources` chỉ dành cho test runtime classpath. Nếu code production đọc fixture ở đó, test có thể pass nhưng production JAR không có file.

**Cách sửa:** chuyển resource production sang `src/main/resources` hoặc khai báo source set phù hợp nếu đây là integration test/custom distribution.

### 7.2. Folder custom chỉ được cấu hình trong IDE

IDE có thể đánh dấu `config-data/` là Resources Root, nhưng Gradle/Maven không biết folder đó.

**Cách sửa:** thêm nó vào `sourceSets.main.resources` hoặc `<build><resources>`, rồi kiểm tra lại output directory.

### 7.3. File local không được commit hoặc bị ignore

Developer có file `local.properties` trên máy, IDE đọc được nhưng CI checkout sạch không có. Một trường hợp khác là file bị `.gitignore` loại.

Kiểm tra:

~~~bash
git status --short
git ls-files src/main/resources
git check-ignore -v src/main/resources/config/local.properties
~~~

`git check-ignore` hữu ích khi nghi file bị ignore. Không đưa secret local vào JAR để khắc phục lỗi; hãy cấp secret từ runtime secret store.

### 7.4. Include/exclude lọc nhầm

Pattern `**/*.json` hoặc `**/config/**` có thể bị loại bởi cấu hình ở parent Gradle convention plugin hoặc Maven POM. Đọc toàn bộ cấu hình áp dụng cho module, không chỉ file build ở root.

**Cách sửa:** thu hẹp exclude, bổ sung include chính xác hoặc tách folder cần filter khỏi folder cần giữ nguyên.

### 7.5. Generated resource không chạy trong CI

IDE plugin hoặc một thao tác thủ công đã tạo file, nhưng task generate không được nối vào `processResources`/Maven lifecycle.

**Cách sửa:** khai báo task output và dependency rõ ràng. Chạy clean build để xác nhận file được sinh lại từ source/input đã commit.

### 7.6. Sai chữ hoa/thường trong resource path

Windows filesystem thường không phân biệt chữ hoa/thường theo cách mặc định; Linux filesystem thường phân biệt. Ví dụ file thật là:

~~~text
config/PricingRules.json
~~~

nhưng code tìm:

~~~java
getResourceAsStream("config/pricingrules.json")
~~~

**Cách sửa:** chuẩn hóa tên file và resource string, kiểm tra bằng `jar tf` trong CI Linux.

### 7.7. Dùng filesystem path cho classpath resource

~~~java
new File("src/main/resources/config/app.properties")
~~~

Cách này phụ thuộc working directory và source tree. Khi chỉ giao JAR cho máy chủ, source tree không có.

**Cách sửa:** dùng `ClassLoader`/`ClassPathResource`. Nếu file cần nằm ngoài JAR để quản trị độc lập, cấu hình filesystem path rõ ràng và mount/copy file vào runtime environment.

### 7.8. Resource bị filtering hoặc encoding làm sai

Resource có thể tồn tại nhưng placeholder bị thay sai, file text bị đổi encoding, newline khác hoặc binary bị filter làm hỏng. Đặc biệt kiểm tra Maven `<filtering>true</filtering>`, Gradle `expand` và delimiter trùng với Spring placeholders.

**Cách sửa:** chỉ filter text cần thiết, giữ binary resources ở folder non-filtered, xác định charset rõ ràng và kiểm tra bytes/content sau package.

### 7.9. Chạy nhầm JAR cũ

IDE đang chạy classes/resources mới từ output directory, nhưng command line lại chạy một JAR cũ nằm ở thư mục khác.

Kiểm tra path tuyệt đối và timestamp/hash của file đang chạy. Build sạch rồi chạy đúng output vừa tạo:

~~~bash
./gradlew clean bootJar
java -jar build/libs/orders-api-1.8.0.jar
~~~

Không giả định file tên `app.jar` luôn là artifact mới nhất; kiểm tra đường dẫn chính xác.

### 7.10. Resource nằm trong module dependency khác

Một module library có thể chứa `config/defaults.json` trong JAR riêng. Resource đó sẽ được tìm qua dependency classpath nếu dependency có mặt và đúng version. Nhưng nó không nhất thiết được copy vào `BOOT-INF/classes` của application; nó có thể nằm bên trong nested dependency JAR ở `BOOT-INF/lib`.

**Cách sửa:** kiểm tra dependency có trong final archive và lookup theo classloader. Nếu nhiều JAR cùng chứa một resource name, kết quả có thể phụ thuộc classloader delegation/order; dùng tên resource có namespace rõ như `com/example/pricing/defaults.json`.

### 7.11. Nhầm resource file với Spring static content hoặc template

Spring Boot mặc định phục vụ static content từ những vị trí như `/static`, `/public`, `/resources` và `/META-INF/resources` trên classpath, tùy cấu hình/version. Đặt file vào một folder tùy ý không tự tạo HTTP route cho nó.

Template ở `templates/` chỉ được render nếu ứng dụng có template engine tương ứng và cấu hình phù hợp. File có thể đã ở trong JAR nhưng controller/view resolver không tìm hoặc không render được. Hãy tách câu hỏi **“resource có đóng gói không?”** khỏi **“framework có xử lý nó theo cách mong muốn không?”**.

### 7.12. Duplicate resources

Hai dependency có thể cùng chứa `META-INF/services/...` hoặc cùng một file config name. Với service provider, cơ chế `ServiceLoader` có thể đọc nhiều entries; với một resource lookup đơn lẻ, classloader trả về một resource theo delegation/search behavior.

Dùng `ClassLoader.getResources(name)` để liệt kê mọi resource trùng tên và xác định nguồn. Không dùng một resource name chung như `config.json` trong nhiều modules nếu nội dung có thể xung đột.

## 8. Multi-module và custom source sets

Trong Gradle multi-project:

~~~text
root/
├── settings.gradle
├── app/
│   └── src/main/resources/application.yml
└── pricing/
    └── src/main/resources/com/example/pricing/defaults.json
~~~

`app` có thể phụ thuộc `pricing`. Resource trong library module được đóng gói vào JAR của module đó, không tự chuyển thành file ở `app/build/resources/main`. Khi app dùng dependency JAR, classloader có thể tìm resource qua dependency classpath nếu dependency được đóng gói đúng.

Kiểm tra cả hai artifacts:

~~~bash
./gradlew :pricing:jar :app:bootJar
jar tf pricing/build/libs/pricing.jar
jar tf app/build/libs/app.jar
~~~

Trong executable Boot JAR, xem cả `BOOT-INF/classes` và `BOOT-INF/lib`. Dependency JAR nằm trong `BOOT-INF/lib` là một nested archive; cần kiểm tra nested entry riêng nếu resource ở đó.

### Custom source sets

Ví dụ `integrationTest` có resources riêng. Chúng thuộc classpath của integration tests, không mặc định thuộc production `main`. Đừng di chuyển test fixture sang production chỉ để làm lỗi lookup biến mất; xác định đúng consumer và source set.

## 9. Tự động phát hiện lỗi resource trong CI

Một lỗi chỉ xuất hiện khi chạy JAR có thể lọt qua unit tests nếu tests chạy trực tiếp từ build output directories. Vì vậy nên thêm kiểm tra sau package.

### 9.1. Smoke test artifact đã đóng gói

Quy trình tối thiểu:

1. Clean build.
2. Chạy unit/integration tests.
3. Tạo executable JAR.
4. Kiểm tra các resource bắt buộc trong JAR.
5. Chạy chính JAR trong smoke test.
6. Gửi request/đọc output và fail nếu resource thiếu.

Ví dụ shell kiểm tra entry:

~~~bash
set -eu

./gradlew clean test bootJar

JAR="build/libs/orders-api-1.8.0.jar"

jar tf "$JAR" | grep -Fx \
  "BOOT-INF/classes/config/pricing-rules.json"

java -jar "$JAR" --spring.main.web-application-type=none
~~~

Lệnh cuối chỉ là ví dụ cho ứng dụng có chế độ startup phù hợp; một web service thật có thể cần chạy background, readiness probe và endpoint smoke test thay vì thoát ngay. Đừng dùng command này như một test hoàn chỉnh nếu application cần database hoặc external services.

### 9.2. Test resource bằng Java

Có thể đưa `ResourceProbe` vào test hoặc một smoke-test module rồi chạy nó với **runtime classpath của artifact thực**. Với Spring Boot executable JAR, cách đơn giản nhất là khởi động ứng dụng và gọi một health/test endpoint có kiểm tra resource, hoặc viết test dùng `java -jar`/process container để mô phỏng môi trường deploy.

Nếu dùng JUnit test trên `build/classes/java/main` và `build/resources/main`, test đó hữu ích nhưng chưa đủ để chứng minh nested executable JAR có đúng layout. Cần ít nhất một kiểm tra trực tiếp artifact.

### 9.3. Kiểm tra bắt buộc với resource quan trọng

Với resource mà ứng dụng không thể hoạt động nếu thiếu (ví dụ schema, mapping hoặc certificate public), tạo một test có assertion:

~~~java
assertNotNull(
        getClass().getClassLoader()
                .getResource("config/pricing-rules.json"),
        "pricing-rules.json must be packaged");
~~~

Đây là **snippet trong test**, không phải chương trình độc lập. Nếu resource là private config/secret, không đóng gói nó; kiểm tra runtime secret mount/config riêng.

## 10. Quy trình chẩn đoán theo từng bước

Khi nhận lỗi `FileNotFoundException` hoặc `getResourceAsStream() returns null` sau khi đóng gói, làm theo trình tự:

### Bước 1 — ghi lại resource name chính xác

Ví dụ:

~~~text
config/pricing-rules.json
~~~

Xác định code dùng `ClassLoader` hay `Class`, có slash đầu hay không, có sai package-relative path không.

### Bước 2 — kiểm tra file nguồn và Git

~~~bash
git status --short
git ls-files src/main/resources
~~~

Xác minh file tồn tại trong clean checkout, đúng chữ hoa/thường và thuộc module cần build.

### Bước 3 — kiểm tra resource processing

Gradle:

~~~bash
./gradlew clean processResources
find build/resources/main -type f
~~~

Maven:

~~~bash
mvn clean process-resources
find target/classes -type f
~~~

Nếu thiếu ở đây, sửa source set/resources/includes/excludes/filtering/generated tasks trước.

### Bước 4 — kiểm tra JAR

~~~bash
jar tf build/libs/orders-api-1.8.0.jar
~~~

Tìm entry `BOOT-INF/classes/config/pricing-rules.json`. Nếu có file output nhưng JAR thiếu, kiểm tra packaging customization và archive task.

### Bước 5 — chạy chính artifact

~~~bash
java -jar build/libs/orders-api-1.8.0.jar
~~~

Không chạy từ IDE hoặc `bootRun` rồi coi đó là cùng môi trường. `java -jar` kiểm tra executable archive mà bạn định phát hành.

### Bước 6 — kiểm tra runtime configuration

Nếu resource được đọc từ filesystem/external config, in working directory, path đã resolve và kiểm tra volume/mount/permissions. Nếu là classpath resource, log resource URL (không log nội dung secret) và xác minh classloader.

### Bước 7 — kiểm tra environment khác biệt

So sánh IDE, local clean build, CI Linux, container filesystem, working directory, user permissions, case sensitivity, Java version và artifact digest. Chạy đúng cùng JAR đã kiểm thử để cô lập nguyên nhân.

## 11. Bảng triệu chứng và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| IDE chạy được, `java -jar` không tìm thấy resource | IDE có resource root riêng hoặc source path bị dùng trực tiếp | Đưa resource vào main source set và dùng classpath API |
| Không có file trong `build/resources/main` | Sai source directory, include/exclude, generate task | Sửa `sourceSets` và `processResources` |
| Có ở `build/resources/main` nhưng thiếu trong Boot JAR | Custom `bootJar`/packaging rule | Kiểm tra `jar tf` và archive task |
| Chỉ lỗi trên CI Linux | Sai chữ hoa/thường hoặc file local bị ignore | Kiểm tra Git tracked files và exact entry path |
| Resource ở `src/test/resources` | Chỉ thuộc test runtime classpath | Chuyển production resource sang main nếu đúng mục đích |
| `getResourceAsStream` trả null | Sai slash, sai path hoặc resource không nằm classpath | Phân biệt ClassLoader và Class lookup |
| `FileNotFoundException` với `new File` | Đường dẫn phụ thuộc working directory/source tree | Dùng classpath stream hoặc external path rõ ràng |
| `getFile()` lỗi khi chạy JAR | Resource nằm bên trong JAR, không phải filesystem File | Dùng `getInputStream()` hoặc URL |
| JSON/YAML bị lỗi parse | Filtering, encoding hoặc nội dung bị thay đổi | Đọc bytes từ JAR, so sánh source/output, đặt charset |
| Ảnh/font/PDF bị corrupt | Binary resource bị filtering | Tách binary khỏi filtered resources |
| File được tạo trong IDE nhưng thiếu CI | Generated resource task không chạy trong Gradle/Maven lifecycle | Đăng ký task dependency và output directory |
| Module app không thấy resource của library | Dependency không có trong runtime archive hoặc lookup sai | Kiểm tra `BOOT-INF/lib` và dependency graph |
| Resource trả về nội dung bất ngờ | Duplicate name trong nhiều JAR | Dùng `getResources()` và namespace resource |
| Static URL trả 404 dù file ở JAR | Đặt sai static location hoặc path mapping | Kiểm tra static resource locations và servlet mappings |
| Template không render | Thiếu template engine hoặc resolver/config sai | Kiểm tra dependency và view resolver |
| Local chạy được nhưng container không | JAR cũ, mount/permissions/working directory khác | Kiểm tra digest, image, mount và log runtime |

## 12. Checklist trước khi phát hành

- [ ] Resource production nằm trong `src/main/resources` hoặc source directory được khai báo rõ.
- [ ] Resource không chỉ tồn tại trên máy developer/IDE.
- [ ] File đã được commit hoặc được generate bằng task có dependency rõ.
- [ ] Resource không nằm nhầm trong `src/test/resources`.
- [ ] Gradle `processResources` hoặc Maven `process-resources` copy đúng file.
- [ ] Include/exclude patterns không loại nhầm resource.
- [ ] Filtering chỉ áp dụng cho text cần thiết, không filter binary.
- [ ] Placeholder của Spring runtime không bị build filtering thay ngoài ý muốn.
- [ ] Resource path đúng slash và case.
- [ ] Code dùng classpath API cho resource đóng gói.
- [ ] Code không giả định classpath resource luôn là `java.io.File`.
- [ ] `jar tf` xác nhận entry có trong executable archive.
- [ ] Smoke test chạy chính JAR sau clean build.
- [ ] CI chạy trên filesystem case-sensitive khi phù hợp.
- [ ] Artifact được kiểm thử là artifact sẽ publish/deploy, được nhận diện bằng checksum/digest.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao ứng dụng chạy trong IDE nhưng thiếu resource khi chạy JAR?

**Trả lời:** IDE có thể thêm resource root hoặc output directory mà Gradle/Maven không đóng gói. Cần kiểm tra main resource source set, processResources và nội dung JAR.

**Câu 2.** Gradle Java plugin copy resource mặc định từ đâu đến đâu?

**Trả lời:** Từ `src/main/resources` qua `processResources` đến `build/resources/main`, rồi output được đưa vào runtime classpath/JAR.

**Câu 3.** Maven mặc định xử lý resource production như thế nào?

**Trả lời:** Maven Resources Plugin copy `src/main/resources` sang `target/classes` trong phase `process-resources`; packaging đưa chúng vào JAR/WAR.

**Câu 4.** Resource application nằm ở đâu trong Spring Boot executable JAR?

**Trả lời:** Dưới `BOOT-INF/classes`; dependencies nằm trong `BOOT-INF/lib`.

**Câu 5.** `ClassLoader.getResourceAsStream("config/app.properties")` có cần slash đầu không?

**Trả lời:** Không. `ClassLoader` nhận path tính từ classpath root, không có slash đầu. `Class.getResourceAsStream("/config/app.properties")` dùng slash đầu để chỉ root.

**Câu 6.** Vì sao `new File("src/main/resources/app.properties")` thường sai trong production?

**Trả lời:** Nó phụ thuộc working directory và source tree. Khi chỉ deploy JAR, source folder có thể không tồn tại.

**Câu 7.** Có thể dùng `Resource.getFile()` cho mọi classpath resource không?

**Trả lời:** Không. Resource nằm bên trong JAR không nhất thiết là filesystem file. Dùng `getInputStream()` hoặc URL.

**Câu 8.** Tại sao không filter ảnh/font/PDF?

**Trả lời:** Filtering có thể biến đổi bytes và làm binary resource hỏng. Chỉ filter text files được thiết kế có placeholder.

**Câu 9.** Vì sao Windows chạy được nhưng CI Linux báo thiếu resource?

**Trả lời:** Có thể sai chữ hoa/thường trong path hoặc file chưa được commit/đang bị ignore. Kiểm tra exact entry bằng `jar tf`.

**Câu 10.** Chỉ chạy unit tests từ Gradle class directories có chứng minh executable JAR đủ resource không?

**Trả lời:** Chưa. Cần kiểm tra archive bằng `jar tf` và chạy smoke test với chính JAR sẽ phát hành.

## 14. Tài liệu chính thức

- Oracle Java 17 — [ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): resource lookup, `getResource`, `getResourceAsStream` và classloader behavior.
- Spring Boot — [Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html): layout executable JAR/WAR, `BOOT-INF/classes` và `BOOT-INF/lib`.
- Spring Framework — [Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): `Resource`, `ClassPathResource`, `FileSystemResource`, stream và URL access.
- Gradle — [Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): source sets, `processResources` và resource directories.
- Gradle — [ProcessResources API](https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html): include, exclude, filtering và copy behavior.
- Apache Maven — [Maven Resources Plugin: Include and Exclude](https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html): cấu hình chọn và loại resource.
- Apache Maven — [Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html): resource filtering, delimiters và cảnh báo binary resources.

**Ghi nhớ:** IDE runtime classpath không phải bằng chứng resource đã được đóng gói. Theo dõi file từ source directory qua `processResources`/`process-resources`, kiểm tra entry trong `BOOT-INF/classes` bằng `jar tf`, rồi đọc bằng classpath stream khi chạy executable JAR. Nếu file nằm trong JAR, hãy xử lý nó như **resource trên classpath**, không giả định nó là một đường dẫn file trên disk.
