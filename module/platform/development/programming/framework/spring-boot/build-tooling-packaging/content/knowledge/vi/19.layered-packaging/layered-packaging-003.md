# Phân chia dependencies, spring-boot-loader, snapshot-dependencies và application

Một **Spring Boot executable JAR** thường chứa hàng chục thư viện runtime, class ứng dụng, tài nguyên và các lớp khởi động của Spring Boot. Nếu đưa nguyên file JAR vào một Docker image bằng một lệnh `COPY` duy nhất, **thay đổi rất nhỏ trong mã ứng dụng** cũng có thể làm bước copy lại JAR và các image layers tương ứng mất lợi thế tái sử dụng. **Layered JAR** giải quyết vấn đề bằng cách mô tả phần nào thuộc nhóm ít thay đổi (dependency release, Boot loader) và phần nào thường thay đổi (SNAPSHOT, application code).

Trong Spring Boot 3.3, bốn layer mặc định là **`dependencies`, `spring-boot-loader`, `snapshot-dependencies` và `application`**, theo thứ tự đó. Bài học này giải thích **quy tắc phân loại thật sự**, cách đọc `BOOT-INF/layers.idx`, sử dụng công cụ `jarmode=tools` để liệt kê và giải nén, đóng gói từ Maven/Gradle, thiết kế Dockerfile với các lệnh `COPY` riêng và tùy biến khi dự án có nhiều module hoặc thư viện nội bộ.

Ví dụ dùng **Spring Boot 3.3.13, Java 17, Maven 3.9.x hoặc Gradle 8.x** để nhất quán cú pháp. Đây là phiên bản minh họa, không phải khẳng định phiên bản đang mới nhất. Các chế độ jar tool thay đổi theo thế hệ: **Spring Boot 3.3 dùng `-Djarmode=tools`**, không sao chép máy móc lệnh `-Djarmode=layertools` từ các bài hướng dẫn đời cũ.

## 1. Layered JAR là gì, và khác gì Docker image layer?

Có hai khái niệm liên quan nhưng không phải một:

1. **Layer trong Spring Boot executable archive** là **phân nhóm logic các entry của JAR**, được mô tả trong một file index. JAR vẫn chứa `BOOT-INF/classes`, `BOOT-INF/lib`, Boot loader và manifest như executable archive bình thường.
2. **Layer trong Docker/OCI image** là đơn vị lưu trữ được tạo bởi từng thao tác trong Dockerfile/build system, có thể **tái sử dụng giữa các image builds** khi bước tương ứng không đổi.

`BOOT-INF/layers.idx` **không tự biến một JAR thành bốn OCI layers** khi chỉ chạy `docker build` trên một Dockerfile bất kỳ. Để tận dụng phân nhóm, công cụ tạo image phải **đọc index, trích xuất/ghép tương ứng và tạo các image layers phù hợp**. Ví dụ, một Dockerfile có bốn lệnh `COPY` riêng cho bốn thư mục sau khi giải nén là một cách làm rõ ràng.

```text
Spring Boot build output
        |
        v
executable app.jar
  |-- BOOT-INF/classes/        (mã + resource ứng dụng)
  |-- BOOT-INF/lib/            (nested runtime JARs)
  |-- org/springframework/boot/loader/
  |-- BOOT-INF/layers.idx      (bản đồ phân lớp logic)
        |
        | java -Djarmode=tools ... extract --layers
        v
extracted/
  |-- dependencies/
  |-- spring-boot-loader/
  |-- snapshot-dependencies/
  |-- application/
        |
        | Dockerfile COPY mỗi thư mục theo thứ tự
        v
OCI image layers có thể tái sử dụng khi input tương ứng không đổi
```

**Ghi nhớ:** `layers.idx` là **metadata của archive**, còn `COPY` / image builder mới là bước xây **các lớp OCI thực**. Lợi ích chính của việc phân lớp là giảm lượng bytes phải rebuild/upload/download khi chỉ thay phần thường xuyên thay đổi; không tự làm JVM chạy nhanh hơn hoặc dependency trở nên immutable.

## 2. Bốn lớp mặc định và ý nghĩa chính xác

| Layer mặc định | Nội dung chủ yếu | Tần suất thay đổi kỳ vọng | Vị trí liên quan trong Boot JAR |
| --- | --- | --- | --- |
| **`dependencies`** | Dependency ngoài project, có version **không chứa `SNAPSHOT`** | Ít thay đổi khi mã ứng dụng được chỉnh hằng ngày | Các nested JAR dưới `BOOT-INF/lib` |
| **`spring-boot-loader`** | Các lớp Boot launcher/loader của executable archive | Thường chỉ đổi khi đổi phiên bản/cấu hình Boot loader | `org/springframework/boot/loader/**` |
| **`snapshot-dependencies`** | Dependency **không phải module cùng build** và có version chứa `SNAPSHOT` | Có thể thay đổi thường xuyên ở dev/integration | Các nested JAR dưới `BOOT-INF/lib` |
| **`application`** | Class và resource chính của app **và project/local module dependencies** | Thường thay đổi nhất | `BOOT-INF/classes/**` và một số nested module JAR trong `BOOT-INF/lib` |

**Thứ tự mặc định**:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

Spring Boot đặt nhóm dự kiến **ít đổi trước, dễ đổi sau** để các bước dựng OCI image có thể tận dụng cache của các layer nền. Cả tên và thứ tự trên là quy ước mặc định của Boot 3.3; nếu project có custom layer configuration, cần tin vào **index đã đóng gói thực tế**, không dự đoán theo bảng này.

### 2.1. `dependencies` không đồng nghĩa tất cả file trong `BOOT-INF/lib`

Phần `BOOT-INF/lib` có thể chứa release libraries, SNAPSHOT libraries, module JAR cùng reactor/project và jarmode tools. Do đó, **không phải cứ nằm trong `BOOT-INF/lib` thì sẽ thuộc `dependencies`**.

Một dependency trực tiếp khai báo `org.apache.commons:commons-lang3:3.14.0` thường vào `dependencies` nếu nó là external release dependency. Một dependency `com.example:shared:1.0.0-SNAPSHOT` **cùng build multi-module** có thể vào `application` vì quy tắc nhận diện project/module được xét trước. Ngược lại, một external SNAPSHOT kéo từ repository thường vào `snapshot-dependencies`.

### 2.2. `spring-boot-loader` khác thư viện `spring-boot-*.jar`

Spring Boot launcher classes được lưu như các entry `org/springframework/boot/loader/**` trong outer executable JAR. Đó là phần `spring-boot-loader`. Nhưng `BOOT-INF/lib/spring-boot-3.3.13.jar` là **thư viện Spring Boot runtime** dạng nested JAR, thường thuộc **`dependencies`**.

Nếu nhìn `jar tf` thấy cả hai và cho rằng cùng phải nằm trong loader layer là nhầm:
- `org/springframework/boot/loader/launch/JarLauncher.class` → **`spring-boot-loader`**.
- `BOOT-INF/lib/spring-boot-3.3.13.jar` → **`dependencies`** khi là external release dependency.

Phân loại dựa trên **vai trò và các rule**, không chỉ vì tên file có chữ `spring-boot`.

## 3. Vì sao `snapshot-dependencies` được tách riêng?

Một release dependency như `com.acme:payment-api:2.3.1` thường không đổi nội dung sau khi phát hành nếu repository áp dụng chính sách immutable. Ngược lại, `com.acme:payment-api:2.4.0-SNAPSHOT` có thể được publish nhiều lần dưới cùng base version trong giai đoạn tích hợp. Nếu trộn cả hai vào `dependencies`, một SNAPSHOT thay đổi có thể làm **layer chứa toàn bộ thư viện release** bị thay theo.

Tách SNAPSHOT ra `snapshot-dependencies` giúp:
- Giữ layer `dependencies` ổn định khi chỉ snapshot library cập nhật.
- Tạo lớp có thể thay riêng khi snapshot JAR đổi.
- Làm review artifact dễ hiểu: những thành phần thường thay đổi được nhìn thấy riêng.

Nhưng đây **không phải hệ thống dependency locking**:
- Một SNAPSHOT có thể có **cùng version string nhưng byte thay đổi**.
- Cache Docker có thể giúp image build nhanh hơn, **không đảm bảo build hôm nay/tomorrow lấy cùng snapshot**.
- Khi release production cần tái lập, nên pin immutable release artifacts, quản lý dependency graph và checksum/provenance theo chính sách.

Trong project không có external SNAPSHOT, layer `snapshot-dependencies` **có thể rỗng hoặc không có file thư viện nào để chứa**. Điều đó không phải lỗi.

## 4. Project dependencies và Maven reactor modules được xử lý thế nào?

Đây là một khác biệt quan trọng so với việc chỉ dựa vào hậu tố version.

### Gradle

Ví dụ Gradle multi-project:

```groovy
dependencies {
    implementation project(':shared')
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

- `project(':shared')` là **project dependency** nên theo phân lớp mặc định thuộc **`application`**, dù project `:shared` đang có version `1.0.0-SNAPSHOT`.
- `commons-lang3:3.14.0` là **non-project released dependency** nên vào `dependencies`.
- Một external `com.acme:lib:1.0.0-SNAPSHOT` tải từ repository mới có khả năng vào `snapshot-dependencies`.

### Maven

Nếu `shared` và `boot-app` cùng xuất hiện trong **Maven reactor đang build**, dependency `com.example:shared:1.0.0-SNAPSHOT` được nhận dạng là **local module dependency** và mặc định thuộc **`application`**.

Nếu `shared` chỉ tồn tại như JAR trong `~/.m2/repository` vì đã install từ trước nhưng **không thuộc reactor hiện tại**, Spring Boot Maven plugin có thể coi nó là **dependency thông thường**. Khi version chứa `SNAPSHOT`, nó có thể thuộc **`snapshot-dependencies`**.

| Trường hợp | Nhận diện theo mặc định | Layer thường gặp |
| --- | --- | --- |
| Gradle `implementation project(':shared')` | Project dependency | `application` |
| Maven `shared` là module trong cùng reactor | Local module dependency | `application` |
| Maven dependency được lấy từ local cache nhưng không thuộc reactor | Regular dependency | `dependencies` hoặc `snapshot-dependencies` theo version |
| External released JAR | Non-project release | `dependencies` |
| External SNAPSHOT JAR | Non-project SNAPSHOT | `snapshot-dependencies` |

**Kết luận:** “module của công ty tôi” không tự động đồng nghĩa “application layer”. Công cụ cần biết dependency đó là **module của build hiện tại** chứ không chỉ có groupId nội bộ. Khi nghi layer bị phân loại sai, đối chiếu project dependency/reactor graph trước khi chỉnh tên layer.

## 5. `BOOT-INF/layers.idx` ghi lại phân lớp gì?

Một layered executable JAR có **layer index** ở `BOOT-INF/layers.idx`. Đây là văn bản có cấu trúc thể hiện tên layer và những entry/path thuộc layer đó.

Ví dụ **rút gọn, chỉ minh họa hình dạng** (nội dung thật thay đổi theo các JAR đã resolve và thứ tự do plugin tạo):

```yaml
- "dependencies":
  - "BOOT-INF/lib/spring-boot-3.3.13.jar"
  - "BOOT-INF/lib/commons-lang3-3.14.0.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/launch/JarLauncher.class"
- "snapshot-dependencies":
  - "BOOT-INF/lib/remote-client-1.2.0-SNAPSHOT.jar"
- "application":
  - "META-INF/MANIFEST.MF"
  - "BOOT-INF/classes/"
  - "BOOT-INF/lib/shared-1.0.0-SNAPSHOT.jar"
```

Những tên `remote-client`, `shared` là ví dụ giả định có trong trường hợp multi-module/external SNAPSHOT; project runnable của bài sau **không khai báo** các thư viện ấy. Index thực tế có thể ghi đường dẫn tổng quát thay vì từng file hoặc có thêm entries index/metadata. **Không dùng bản minh họa này để đối chiếu từng dòng của archive thật**.

Có thể liệt kê JAR và tìm index:

```bash
jar tf target/layer-demo-1.0.0.jar | grep '^BOOT-INF/layers.idx$'
```

Với Gradle, dùng đường dẫn `build/libs/layer-demo-1.0.0.jar` thay vì `target/...`. Nếu trên Windows PowerShell:

```powershell
jar tf .\target\layer-demo-1.0.0.jar | Select-String '^BOOT-INF/layers.idx$'
```

**`jar tf` chỉ liệt kê tên entry.** Để đọc nội dung `layers.idx` mà không giải nén, khi có `unzip`:

```bash
unzip -p target/layer-demo-1.0.0.jar BOOT-INF/layers.idx
```

Nếu máy không có `unzip`, tạo thư mục tạm, chạy `jar xf ../target/layer-demo-1.0.0.jar BOOT-INF/layers.idx` rồi đọc file text. Không giải nén cả JAR vào thư mục có dữ liệu quan trọng.

## 6. Phân lớp để tối ưu cache Docker/OCI hoạt động ra sao?

Dockerfile không dùng layers:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/layer-demo-1.0.0.jar application.jar
ENTRYPOINT ["java", "-jar", "application.jar"]
```

Lệnh `COPY` đưa **toàn bộ JAR** vào một lớp image. Thay đổi một class trong `BOOT-INF/classes` thường thay byte của JAR nên lớp chứa JAR cũng thay đổi, dù phần lớn dependencies vẫn giữ nguyên.

Dockerfile có phân lớp:
- Copy `dependencies` trước.
- Copy `spring-boot-loader` kế tiếp.
- Copy `snapshot-dependencies` tiếp.
- Copy `application` cuối.

Khi chỉ app code thay đổi, những lớp ít đổi **có cơ hội dùng lại cache/image blobs**. Khi Boot plugin version đổi, lớp loader và có thể dependency runtime thay; khi SNAPSHOT library đổi, snapshot layer thay. Đây là **lợi ích kỳ vọng phụ thuộc hash/content và cách Docker/BuildKit/buildpack xây image**, không phải lời hứa rằng mọi build luôn chỉ thay đúng một layer hoặc có tốc độ cụ thể.

**Thứ tự layer là thứ tự ưu tiên cache, không phải thứ tự Spring Boot load bean hoặc class.** Classpath order là vấn đề khác, có thể chịu ảnh hưởng bởi `BOOT-INF/classpath.idx`. Không dùng `layerOrder` để xử lý xung đột bean/resource runtime.

## 7. Dự án mẫu Spring Boot Java 17 để tạo layered JAR

Cấu trúc dùng chung cho Maven hoặc Gradle:

```text
layer-demo/
├── pom.xml                   (nếu chọn Maven)
├── settings.gradle           (nếu chọn Gradle)
├── build.gradle              (nếu chọn Gradle)
└── src/
    └── main/
        ├── java/com/example/layers/
        │   └── LayerDemoApplication.java
        └── resources/demo/
            └── build-marker.txt
```

Ví dụ không dùng database, broker, HTTP server hay external SNAPSHOT. Như vậy có thể xem **layer mặc định** và kiểm chứng resource đọc được sau khi đóng gói; không cần một private repository để thực hành.

### 7.1. Mã nguồn ứng dụng

Tạo `src/main/java/com/example/layers/LayerDemoApplication.java`:

```java
package com.example.layers;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class LayerDemoApplication {

    public static void main(String[] args) throws IOException {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(LayerDemoApplication.class, args)) {
            try (InputStream in = LayerDemoApplication.class
                    .getClassLoader()
                    .getResourceAsStream("demo/build-marker.txt")) {
                if (in == null) {
                    throw new IOException("Missing resource demo/build-marker.txt");
                }
                String marker = new String(in.readAllBytes(), StandardCharsets.UTF_8);
                System.out.println("layer-demo=" + marker.strip());
            }
        }
    }
}
```

Tạo `src/main/resources/demo/build-marker.txt` chứa **một dòng**:

```text
layered-jar-ok
```

Khi chạy đúng executable JAR, chương trình in:

```text
layer-demo=layered-jar-ok
```

Spring Boot có thể in thêm log startup; dòng trên là **stdout của mã ứng dụng**, không phải toàn bộ output. `spring-boot-starter` không đưa web server vào ứng dụng này, và `ConfigurableApplicationContext` được đóng sau khi đọc resource nên Java process kết thúc.

Nếu resource không vào archive, chương trình ném `IOException` với lý do dễ nhận biết. Điều này giúp test việc **layer extraction và classpath runtime vẫn giữ đúng nội dung**.

## 8. Maven POM đầy đủ: phân lớp theo mặc định

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>layer-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven Spring Boot parent quản lý version của plugin và execution `repackage`, nên `mvn package` chuyển JAR thành **Spring Boot executable JAR**. Theo Spring Boot 3.3, layered archives và `layers.idx` **được bật mặc định**; không phải thêm một plugin ngoài để tự gắn bốn tên layer.

Từ root project:

```bash
./mvnw clean package
jar tf target/layer-demo-1.0.0.jar
java -jar target/layer-demo-1.0.0.jar
```

Nếu không có Maven Wrapper dùng `mvn` tương thích; trên Windows PowerShell dùng `.\mvnw.cmd`. Dòng chương trình kỳ vọng là `layer-demo=layered-jar-ok`. Trong thư mục `target`, file `*.jar.original` nếu có là bản plain JAR trước `repackage`; **không dùng nó làm đối tượng kiểm tra layered executable archive**.

**Nếu chỉ import Spring Boot BOM mà không kế thừa starter parent:** BOM quản lý dependency versions **không tự tạo plugin execution `repackage`**. Cần khai báo plugin version và execution riêng. Khi không thấy `BOOT-INF/layers.idx`, trước tiên kiểm tra artifact đã thực sự được repackage chưa.

## 9. Gradle Groovy DSL đầy đủ: phân lớp theo mặc định

Tạo `settings.gradle`:

```groovy
rootProject.name = 'layer-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}

springBoot {
    mainClass = 'com.example.layers.LayerDemoApplication'
}
```

Spring Boot Gradle plugin áp dụng các conventions để task `bootJar` tạo layered executable JAR, khi kết hợp Java plugin. Không cần khai báo `layered { enabled = true }` để nhận bốn layer mặc định, trừ khi dự án đã override quy tắc này.

Chạy:

```bash
./gradlew clean bootJar
jar tf build/libs/layer-demo-1.0.0.jar
java -jar build/libs/layer-demo-1.0.0.jar
```

Nếu không có Gradle Wrapper, dùng `gradle` tương thích; PowerShell dùng `.\gradlew.bat`. Khi Gradle cùng tạo `layer-demo-1.0.0-plain.jar`, hãy kiểm tra **`layer-demo-1.0.0.jar` từ `bootJar`**, không phải `-plain.jar` từ `jar`. Plain JAR không có Boot loader/nested dependency layout nên không đủ để kiểm thử bốn layer.

### 9.1. Kotlin DSL tương đương (nếu dùng `build.gradle.kts`)

Một project có thể thay file Groovy bằng Kotlin DSL. Đoạn cấu hình tương ứng:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.apache.commons:commons-lang3:3.14.0")
}

springBoot {
    mainClass.set("com.example.layers.LayerDemoApplication")
}
```

Đây là một **`build.gradle.kts` thay thế**, không phải đoạn trộn vào `build.gradle` Groovy. Giữ file `settings.gradle.kts` tương ứng với `rootProject.name = "layer-demo"`. Mọi cơ chế phân lớp mặc định vẫn như nhau.

## 10. Kiểm tra `layers.idx` và đúng bốn tên layer

Sau khi chạy một trong hai lệnh build, đặt đường dẫn artifact vào biến shell cho dễ quan sát.

**Linux/macOS dùng Maven artifact:**

```bash
JAR=target/layer-demo-1.0.0.jar
jar tf "$JAR" | grep -E '^(BOOT-INF/layers[.]idx|BOOT-INF/classes/|BOOT-INF/lib/|org/springframework/boot/loader/)'
unzip -p "$JAR" BOOT-INF/layers.idx
```

**Linux/macOS dùng Gradle artifact:**

```bash
JAR=build/libs/layer-demo-1.0.0.jar
jar tf "$JAR" | grep 'BOOT-INF/layers.idx'
unzip -p "$JAR" BOOT-INF/layers.idx
```

**Windows PowerShell:**

```powershell
$jar = '.\build\libs\layer-demo-1.0.0.jar'
jar tf $jar | Select-String '^BOOT-INF/layers.idx$'
```

PowerShell không nhất thiết có `unzip`. Khi cần đọc index, tạo một thư mục tạm trống, chuyển vào đó, dùng `jar xf ..\build\libs\layer-demo-1.0.0.jar BOOT-INF/layers.idx` rồi `Get-Content .\BOOT-INF\layers.idx`. Nếu dùng Maven thay thư mục `build\libs` bằng `target`.

Với project mẫu:
- `dependencies` được mong đợi có các JAR Spring Boot/Commons Lang release.
- `spring-boot-loader` được mong đợi có loader classes.
- `application` được mong đợi có `LayerDemoApplication.class`, resource `demo/build-marker.txt` và manifest/metadata thuộc app.
- `snapshot-dependencies` không cần có JAR nào vì project mẫu **không khai báo external SNAPSHOT**.

**Không so khớp nội dung index theo tên dependency cố định của một máy khác**; các transitive libraries có thể khác nếu bạn thay BOM/plugin. Xác minh **logic**, tên layer, đúng app class/resource và những libs thật được đóng gói.

## 11. `jarmode=tools`: liệt kê và giải nén đúng cho Spring Boot 3.3

Spring Boot 3.3 cung cấp `spring-boot-jarmode-tools` trong layered archive (theo mặc định của plugin). Nó hỗ trợ chạy JAR ở chế độ công cụ, **không khởi động Spring application**.

Xem danh sách lệnh:

```bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar
```

Các lệnh quan trọng của Boot 3.3 là:
- `list-layers`: liệt kê tên layers có thể extract.
- `extract`: trích xuất archive thành các file/thư mục; với `--layers` sẽ tách theo layers.
- `help`: trợ giúp.

Liệt kê layer:

```bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar list-layers
```

Những tên bạn kỳ vọng thấy ở cấu hình mặc định:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

Đây là **các tên logic cần đối chiếu**; không khẳng định tool luôn in đúng bốn dòng và không có thông tin nào khác.

Giải nén có chỉ định thư mục đích:

```bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar extract --layers --destination extracted
```

Tool tạo cấu trúc thư mục phù hợp để dựng container image theo layers. Tùy tool mode/extraction layout, có thể có thêm file `application.jar` dùng để chạy sau khi ghép các thư mục; Dockerfile chính thức của Boot 3.3 sử dụng file này. Dùng `list-layers`/`help` và kiểm tra thư mục được tạo thay vì đoán tất cả filenames.

**Nếu không dùng Maven** thì thay `target/layer-demo-1.0.0.jar` bằng `build/libs/layer-demo-1.0.0.jar`. **Đừng dùng**:
- `-Djarmode=layertools` (phổ biến ở Spring Boot 2.x/3.2) cho ví dụ Boot 3.3 này.
- `java -jar app.jar extract` mà thiếu `-Djarmode=tools`; khi đó JVM có thể khởi động app và truyền `extract` như một application argument.
- Cú pháp `extract --layers` trên JAR không có tool phù hợp hoặc có script launch làm ảnh hưởng tool mode.

## 12. Tại sao Dockerfile `COPY` theo thứ tự bốn layer?

Sau khi giải nén bằng `tools`, Dockerfile lý tưởng tách mỗi nhóm thành một lệnh `COPY`:

```dockerfile
# Dockerfile cho project Maven demo Spring Boot 3.3.13
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /workspace

COPY target/layer-demo-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
```

Đây là **Dockerfile multi-stage đầy đủ** minh họa Boot 3.3 và Java 17. Nó giả định file `target/layer-demo-1.0.0.jar` đã được build **trước** khi gọi Docker. Với Gradle đổi dòng `COPY target/...` thành `COPY build/libs/layer-demo-1.0.0.jar application.jar`. Không dùng glob `*.jar` khi cùng thư mục còn `*-plain.jar` hoặc artifact có classifier khác.

Thử:

```bash
./mvnw clean package
docker build -t layer-demo:1.0.0 .
docker run --rm layer-demo:1.0.0
```

Dòng do Java application in ra:

```text
layer-demo=layered-jar-ok
```

Dockerfile tạo OCI image bằng bốn `COPY` ứng với thứ tự mặc định. Lúc thay đổi chỉ app class/resource mà không đổi release libraries:
- `dependencies` có cơ hội tái dùng.
- `spring-boot-loader` có cơ hội tái dùng.
- `snapshot-dependencies` có cơ hội tái dùng nếu không đổi.
- `application` phản ánh thay đổi mới.

Không thể đảm bảo **thời gian build giảm chính xác bao nhiêu**: phụ thuộc Docker/BuildKit cache có sẵn, môi trường CI, byte thực, metadata của artifact và network. Dù extractor stage có thể phải chạy lại vì outer JAR đổi, các lớp copy trong runtime stage vẫn có thể được reuse dựa trên nội dung.

### 12.1. `application.jar` trong image không phải outer uber JAR nguyên vẹn

Sau `extract --layers` ở chế độ `tools`, Spring Boot cung cấp một cấu trúc phù hợp để chạy app từ các lớp đã copy. File `application.jar` trong image cuối **không cần là bản outer JAR có tất cả nested libraries như input build stage**. Nó có thể là launcher JAR tham chiếu các tệp đã được tách. **Đừng đổi ENTRYPOINT thành `java -jar target/layer-demo-1.0.0.jar`** trong image đã extract nếu không copy file đó vào đúng nơi.

Dùng chính Dockerfile với `ENTRYPOINT ["java", "-jar", "application.jar"]` của Boot 3.3, rồi smoke-test trên image thật. Không tự copy riêng `BOOT-INF/classes` và bỏ loader/manifest/classpath structure.

## 13. Maven `repackage`: bật/tắt layer và tùy chọn tools

Maven Spring Boot plugin 3.3 có `<layers>` để điều khiển layer index. Cấu hình mặc định đã bật; để **tắt** khi có lý do:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layers>
            <enabled>false</enabled>
        </layers>
    </configuration>
</plugin>
```

Đây là **đoạn plugin thay thế** ở `<build><plugins>` của POM, không phải một POM hoàn chỉnh. Khi đã tắt `layers.idx`, đừng dùng Dockerfile mong `extract --layers` ra đủ bốn nhóm.

Nếu muốn giữ `layers.idx` nhưng **không kèm jarmode tools** để giảm phần code phụ trong archive, Spring Boot 3.3 hỗ trợ `includeTools`:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <includeTools>false</includeTools>
    </configuration>
</plugin>
```

**Hệ quả:** lệnh `java -Djarmode=tools -jar ...` không thể dựa vào tool đã bị loại. Chỉ dùng `includeTools=false` khi image builder của bạn có phương pháp extract khác hoặc buildpacks/tooling phù hợp. Đừng tắt công cụ rồi sử dụng Dockerfile ở mục 12.

`spring-boot-maven-plugin` phải thật sự chạy goal `repackage`. Nếu project không kế thừa starter parent, cần khai báo version plugin và execution rõ ràng. Một main JAR thường do `maven-jar-plugin` tạo trước `repackage`.

## 14. Gradle `bootJar`: bật/tắt layer và công cụ extract

Với Gradle Groovy DSL, tắt layer index:

```groovy
tasks.named('bootJar') {
    layered {
        enabled = false
    }
}
```

Đây là đoạn **bổ sung hoặc thay thế configuration của task `bootJar`** trong `build.gradle` đã có. Tắt tools nhưng giữ layer index:

```groovy
tasks.named('bootJar') {
    includeTools = false
}
```

Với Gradle Kotlin DSL:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    includeTools.set(false)
}
```

Trong Spring Boot 3.3, `includeTools` là property của task `bootJar`; đừng sao chép `layered { includeLayerTools = false }` từ Spring Boot đời cũ rồi kỳ vọng cú pháp giữ nguyên. **Mọi đoạn trong mục này là lựa chọn cấu hình**, không nên vừa tắt tools vừa chạy extraction Dockerfile đang phụ thuộc tools.

Nếu project dùng `bootWar`, nguyên lý layer tương tự nhưng layout archive là `WEB-INF/classes` và `WEB-INF/lib`/`WEB-INF/lib-provided`, không phải `BOOT-INF/classes`/`BOOT-INF/lib` như JAR. Chỉ áp dụng lệnh Dockerfile/JAR example khi artifact là Boot JAR.

## 15. Gradle tùy biến quy tắc bốn layer theo thứ tự claim

Nếu muốn hiểu cách Spring Boot quyết định nội dung từng layer, có thể **khai báo lại quy tắc mặc định**. Đoạn Groovy DSL sau đặt trong `build.gradle` có Spring Boot plugin:

```groovy
tasks.named('bootJar') {
    layered {
        application {
            intoLayer('spring-boot-loader') {
                include 'org/springframework/boot/loader/**'
            }
            intoLayer('application')
        }
        dependencies {
            intoLayer('application') {
                includeProjectDependencies()
            }
            intoLayer('snapshot-dependencies') {
                include '*:*:*SNAPSHOT'
            }
            intoLayer('dependencies')
        }
        layerOrder = [
            'dependencies',
            'spring-boot-loader',
            'snapshot-dependencies',
            'application'
        ]
    }
}
```

**Hai thứ tự khác nhau:**

1. **Thứ tự `intoLayer` (claim)**: khi plugin xét một phần của archive, rule xuất hiện **trước** được cơ hội nhận trước. `includeProjectDependencies()` cần đặt trước matcher SNAPSHOT để local project dependencies được giữ trong `application`. Sau đó matcher `*:*:*SNAPSHOT` nhận external snapshot, cuối cùng fallback nhận remaining external releases.
2. **Thứ tự `layerOrder` (output)**: quyết định thứ tự các layer được ghi vào index/dùng khi dựng image, tối ưu cache. Nó là `dependencies → spring-boot-loader → snapshot-dependencies → application`.

**Không lấy thứ tự `intoLayer` và ghép luôn vào `layerOrder`.** Nếu làm vậy, bạn dễ vô tình đưa `application` vào lớp sớm, làm mất hiệu quả cache, hoặc rule bắt rộng ở đầu “nuốt” mọi dependency trước khi snapshot matcher được xét.

Matcher trong `application` dùng Ant-style path `org/springframework/boot/loader/**`. Matcher của `dependencies` dùng coordinate-style pattern `group:artifact[:version]`; `*:*:*SNAPSHOT` nhằm nhận các version chứa `SNAPSHOT`. `includeProjectDependencies()` là rule dành cho **project dependencies**, không phải một string match tên thư viện.

## 16. Gradle Kotlin DSL: quy tắc bốn layer tương đương

Nếu project dùng `build.gradle.kts`, đoạn Kotlin DSL tương đương (đặt bên dưới khối `plugins` của file đã có):

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include("org/springframework/boot/loader/**")
            }
            intoLayer("application")
        }
        dependencies {
            intoLayer("application") {
                includeProjectDependencies()
            }
            intoLayer("snapshot-dependencies") {
                include("*:*:*SNAPSHOT")
            }
            intoLayer("dependencies")
        }
        layerOrder.set(
            listOf(
                "dependencies",
                "spring-boot-loader",
                "snapshot-dependencies",
                "application"
            )
        )
    }
}
```

Đây là **đoạn cấu hình thêm cho Gradle Kotlin DSL**, không phải file `build.gradle.kts` đầy đủ; áp dụng plugin `java` và `org.springframework.boot` ở khối `plugins` như mục 9. Cần import `BootJar` phù hợp; với một số Gradle scripts và môi trường IDE, có thể dùng `tasks.named<BootJar>` sau khi plugin đã được apply.

Nếu không cần điều chỉnh layer, **giữ mặc định của Spring Boot** là cách ít lỗi hơn. Đừng chỉ copy đoạn custom rules để chứng minh đang “tối ưu”; bài học này dùng nó nhằm giải thích cách các nhóm được phân loại.

## 17. Maven tùy biến phân lớp bằng `layers.xml`

Với Maven, cấu hình layer phức tạp nằm trong một **file XML độc lập**, chẳng hạn `src/layers.xml`, được Spring Boot Maven plugin đọc khi `repackage`.

Thêm phần cấu hình bên trong declaration `spring-boot-maven-plugin` ở POM mẫu (không khai báo plugin hai lần):

```xml
<configuration>
    <layers>
        <enabled>true</enabled>
        <configuration>${project.basedir}/src/layers.xml</configuration>
    </layers>
</configuration>
```

File `src/layers.xml` mô tả **bốn layer mặc định một cách tường minh**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<layers xmlns="http://www.springframework.org/schema/boot/layers"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.springframework.org/schema/boot/layers
                            https://www.springframework.org/schema/boot/layers/layers-3.3.xsd">

    <application>
        <into layer="spring-boot-loader">
            <include>org/springframework/boot/loader/**</include>
        </into>
        <into layer="application"/>
    </application>

    <dependencies>
        <into layer="application">
            <includeModuleDependencies/>
        </into>
        <into layer="snapshot-dependencies">
            <include>*:*:*SNAPSHOT</include>
        </into>
        <into layer="dependencies"/>
    </dependencies>

    <layerOrder>
        <layer>dependencies</layer>
        <layer>spring-boot-loader</layer>
        <layer>snapshot-dependencies</layer>
        <layer>application</layer>
    </layerOrder>
</layers>
```

Điểm cần chú ý:
- File XML **không phải `pom.xml`**; nó chứa root `<layers>` và schema ứng với Spring Boot 3.3.
- `<application>` phân loại Boot loader classes và app classes/resources.
- `<dependencies>` phân loại local reactor modules, external SNAPSHOT và external released dependencies.
- `<includeModuleDependencies/>` là cơ chế Maven tương ứng ý tưởng `includeProjectDependencies()` ở Gradle.
- `<layerOrder>` phải liệt kê **tất cả layer** đã được `<into>` sử dụng.
- Thứ tự các phần tử `<into>` ảnh hưởng **quy tắc nhận trước**, còn `layerOrder` ảnh hưởng **thứ tự layer trong index/image**.

Khi thay đổi file custom, chạy `./mvnw clean package` và đọc lại `BOOT-INF/layers.idx`. Nếu XML sai schema, layer name typo hoặc một nội dung bị bỏ sót, **đừng tự đoán archive vẫn hợp lệ**; phải xem build error và index thật.

## 18. Tách thêm thư viện nội bộ thành layer riêng khi nào?

Với dự án lớn, có thể có một tập thư viện do công ty phát hành thường xuyên hơn Spring Boot dependencies nhưng ít đổi hơn mã của từng service. Khi ấy, một layer `company-dependencies` có thể có ích.

**Lưu ý:** đây là **tùy biến bổ sung**, không còn đúng bốn layer mặc định mà B209 muốn bạn hiểu. Chỉ cân nhắc sau khi đã xác định chính xác bốn layer gốc và đo được hành vi cache.

### Gradle ví dụ

Đoạn Groovy thay thế phần `dependencies` và `layerOrder` trong cấu hình `layered` ở mục 15:

```groovy
dependencies {
    intoLayer('application') {
        includeProjectDependencies()
    }
    intoLayer('snapshot-dependencies') {
        include '*:*:*SNAPSHOT'
    }
    intoLayer('company-dependencies') {
        include 'com.acme:*'
    }
    intoLayer('dependencies')
}

layerOrder = [
    'dependencies',
    'spring-boot-loader',
    'company-dependencies',
    'snapshot-dependencies',
    'application'
]
```

Đây là **đoạn cấu hình bổ sung bên trong `layered { ... }`**, không phải Gradle `dependencies { implementation ... }` ở cấp project. Cần giữ phần `application { ... }` ở mục 15. Matcher `com.acme:*` là ví dụ với group của một công ty giả định, không phải một external repository mặc định tồn tại.

### Maven ví dụ

Trong `src/layers.xml` thay phần `<dependencies>` và `<layerOrder>` ở mục 17 bằng:

```xml
<dependencies>
    <into layer="application">
        <includeModuleDependencies/>
    </into>
    <into layer="snapshot-dependencies">
        <include>*:*:*SNAPSHOT</include>
    </into>
    <into layer="company-dependencies">
        <include>com.acme:*</include>
    </into>
    <into layer="dependencies"/>
</dependencies>

<layerOrder>
    <layer>dependencies</layer>
    <layer>spring-boot-loader</layer>
    <layer>company-dependencies</layer>
    <layer>snapshot-dependencies</layer>
    <layer>application</layer>
</layerOrder>
```

Đoạn trên là **hai phần XML để thay bên trong `<layers>`**, không phải một file `layers.xml` độc lập. Khi thêm layer mới vào index, **Dockerfile cũng phải thêm `COPY` tương ứng** theo cùng thứ tự, nếu không sẽ mất thư viện hoặc chạy sai classpath.

**Quy tắc ưu tiên quan trọng:** nếu muốn internal SNAPSHOT đi vào `snapshot-dependencies` thay vì `company-dependencies`, đặt matcher SNAPSHOT **trước** matcher company. Nếu muốn internal module cùng reactor vào `application`, đặt `includeModuleDependencies` **trước** các matcher khác.

## 19. Khi nào `layers.idx` có mà cache vẫn không hiệu quả?

Các nguyên nhân thường gặp:

1. Dockerfile vẫn dùng một `COPY app.jar` duy nhất thay vì extract rồi `COPY` theo layers.
2. Dùng `COPY . .` quá sớm, thay mã nguồn khiến mọi bước sau bị ảnh hưởng hoặc vô tình copy `target`/`build` cũ.
3. JAR chứa generated resources có timestamp mỗi lần build khiến `application` luôn đổi (điều này có thể được chấp nhận nếu chỉ layer application thay).
4. Dynamic/changing/SNAPSHOT dependencies bị cập nhật ngoài dự kiến; `snapshot-dependencies` hoặc thậm chí `dependencies` thay.
5. Khóa Gradle/Maven/BOM chưa ổn định, dependency version khác giữa CI runners.
6. Docker build cache trên CI bị xóa, builder khác hoặc base image được cập nhật, nên cache kỳ vọng không còn.
7. Đưa internal modules luôn thay đổi vào layer `dependencies` và khiến nhóm thư viện “ít đổi” phải rebuild.
8. Tùy chỉnh `layerOrder` đưa `application` lên trước, khiến những layer sau dễ bị invalidated theo cache chain.
9. Thay Spring Boot plugin/runtime JDK khiến nhiều layer cùng khác.
10. Build image qua một công cụ có cơ chế cache/layer riêng, nhưng bạn đang đo theo kỳ vọng của Dockerfile custom.

**`layers.idx` là công cụ phân loại, không phải công cụ khóa phiên bản hoặc tăng tốc mọi quy trình build.** Khi benchmark, so sánh hai lần build có **cùng môi trường và cache state được kiểm soát**, xem `docker history`/logs và kích thước blobs được thay, không tuyên bố cache hit chỉ vì thấy bốn tên layer.

## 20. So sánh thay đổi ứng dụng, dependency và Boot version

| Thao tác | Layer có khả năng thay đổi | Layer có cơ hội giữ cache |
| --- | --- | --- |
| Sửa `LayerDemoApplication.java` | `application` | `dependencies`, `spring-boot-loader`, `snapshot-dependencies` |
| Sửa `demo/build-marker.txt` | `application` | Ba layer còn lại nếu inputs không đổi |
| Nâng `commons-lang3` release từ `3.14.0` lên bản khác | `dependencies` | Loader có thể không đổi; những layer sau còn tùy cache chain |
| External SNAPSHOT JAR publish lại | `snapshot-dependencies` | `dependencies` và loader nếu không đổi |
| Sửa một Gradle project dependency cùng build | `application` | `dependencies` và loader nếu không đổi |
| Thay Spring Boot plugin/loader version | `spring-boot-loader`, thường thêm `dependencies` | Không bảo đảm giữ cache của lớp khác |
| Thêm external library release mới | `dependencies` | Loader chỉ giữ nếu implementation không đổi |
| Đổi custom layer rules/index | Có thể ảnh hưởng **nhiều layer và cách image được ghép** | Phải đánh giá lại vì mapping thay |
| Chỉ đổi Docker base image | Base layers thay; các lớp kế tiếp có thể bị rebuild | Không giả định cache giữ nguyên |

Bảng là **phân tích kỳ vọng**, không phải mô phỏng đã chạy. Khi layer đứng trước trong Dockerfile đổi, các bước đứng sau có thể bị ảnh hưởng đến cache hiệu dụng ngay cả khi source directory riêng không thay. Cách xử lý là đo thực tế và ưu tiên đặt các phần ổn định trước.

## 21. `bootBuildImage`, buildpacks và Dockerfile custom có giống nhau?

Spring Boot Maven/Gradle có các goal/task dựng OCI image như `spring-boot:build-image` và `bootBuildImage` với **Cloud Native Buildpacks**. Chúng có thể tối ưu classpath và image layers theo cách riêng, không nhất thiết thực hiện **đúng bốn lệnh `COPY`** của Dockerfile ở mục 12.

Sự khác biệt:
- **`bootJar`/`repackage`**: tạo executable JAR và `layers.idx`.
- **`jarmode=tools`**: hiển thị/trích xuất archive theo layers.
- **Dockerfile custom**: bạn quyết định `COPY`, base image, ENTRYPOINT, users và cache strategy.
- **Buildpacks**: builder/lifecycle/cache/OCI layers được buildpack quản lý; cần xem tài liệu và output của buildpack để biết layout thực.

Không so sánh một image từ buildpacks với Dockerfile custom rồi kết luận một bên “mất lớp `spring-boot-loader`” chỉ vì `docker history` hiển thị khác. Lợi ích là **isolate những đầu vào thay đổi theo cadence**, không phải tạo đúng bốn layer bằng mọi giá.

Nếu mục tiêu là một ứng dụng chạy trực tiếp bằng `java -jar` trên VM/bare metal, layered metadata có thể không mang lợi ích container cache rõ ràng; vẫn có thể giữ mặc định vì không ảnh hưởng chức năng khởi chạy thông thường.

## 22. Cách kiểm tra đúng tên, thứ tự và nội dung layer trong CI

Một bước CI tối thiểu sau khi package:

1. Xác định **đúng file executable JAR**, không lấy plain `-plain.jar`.
2. Kiểm tra `jar tf` có `BOOT-INF/layers.idx` và Boot loader.
3. Dùng `jarmode=tools list-layers`; xác nhận có bốn tên layer mặc định theo thứ tự mong đợi.
4. Dùng `extract --layers --destination ...` để kiểm tra các thư mục.
5. Kiểm tra class/resource ứng dụng có mặt sau extraction.
6. Kiểm tra release dependencies nằm trong nhóm ổn định; SNAPSHOT nếu có phải vào nhóm thích hợp.
7. Dựng Docker image và chạy smoke test ứng dụng.
8. Lưu build logs, container image digest, kiểm tra SBOM/versions nếu policy yêu cầu.

**Bash (Maven demo; cần JDK 17, `grep` và lệnh `jar`):**

```bash
#!/usr/bin/env bash
set -euo pipefail

JAR=target/layer-demo-1.0.0.jar

test -s "$JAR"
jar tf "$JAR" > jar-entries.txt

grep -Fx 'BOOT-INF/layers.idx' jar-entries.txt
grep -Fx 'BOOT-INF/classes/com/example/layers/LayerDemoApplication.class' jar-entries.txt
grep -Fx 'BOOT-INF/classes/demo/build-marker.txt' jar-entries.txt
grep -E '^BOOT-INF/lib/.*[.]jar$' jar-entries.txt

java -Djarmode=tools -jar "$JAR" list-layers > layers-list.txt
grep -Fx 'dependencies' layers-list.txt
grep -Fx 'spring-boot-loader' layers-list.txt
grep -Fx 'snapshot-dependencies' layers-list.txt
grep -Fx 'application' layers-list.txt

java -Djarmode=tools -jar "$JAR" extract --layers --destination extracted

test -f extracted/application/BOOT-INF/classes/com/example/layers/LayerDemoApplication.class
test -f extracted/application/BOOT-INF/classes/demo/build-marker.txt
test -d extracted/dependencies
test -d extracted/spring-boot-loader

java -jar "$JAR" > app-smoke.log
grep -Fx 'layer-demo=layered-jar-ok' app-smoke.log
```

Đoạn script dùng **đúng project mẫu** và `list-layers` có tên layer in riêng từng dòng theo Boot 3.3. Khi custom layer, sửa assertions/đường dẫn tương ứng. Không chạy script từ một thư mục khác nếu đường dẫn artifact không phù hợp. Với Windows, dùng PowerShell và `jar tf` / `Select-String`, hoặc thực hiện kiểm tra trong CI Linux.

**Không dùng `grep` tên thư mục thay cho kiểm tra nội dung**: `layers.idx` có thể khai báo group nhưng library vẫn không vào archive vì dependency scope/configuration sai. Khi cần độ tin cậy cao, kiểm tra cụ thể external JAR và project JAR theo graph. Đối với Boot 3.3 extraction output, kiểm tra đường dẫn class/resource thực tế dưới `extracted/application/BOOT-INF/classes`.

## 23. Lỗi thường gặp khi tạo và dùng bốn layer

| Triệu chứng | Nguyên nhân khả dĩ | Cách giải quyết |
| --- | --- | --- |
| JAR không có `BOOT-INF/layers.idx` | Build tạo plain JAR, plugin chưa repackage hoặc đã tắt layered | Kiểm tra Maven `repackage` / Gradle `bootJar`, `<layers><enabled>` hoặc `layered.enabled` |
| `java -Djarmode=tools` không nhận lệnh | Tools bị loại, sai Boot version hoặc JAR có embedded launch script | Xem `includeTools`, Boot version, không dùng fully executable launch script |
| Script dùng `-Djarmode=layertools` bị lỗi | Nhầm cú pháp của Boot đời cũ | Với Boot 3.3 dùng `-Djarmode=tools` và `list-layers`/`extract --layers` |
| `snapshot-dependencies` rỗng | Không có external SNAPSHOT | Đây có thể là trạng thái đúng, không tự thêm SNAPSHOT để “đủ lớp” |
| Internal SNAPSHOT JAR nằm trong `application` | Nó là Gradle project dependency hoặc Maven reactor local module | Đây thường là phân loại mặc định đúng |
| Internal dependency qua Maven local cache vào snapshot layer | Không nằm trong reactor đang build | Kiểm tra reactor modules, dùng multi-module build nếu muốn nhận diện local module |
| `spring-boot-3.3.13.jar` ở dependencies chứ không phải loader | Đây là runtime lib, không phải Boot loader classes | Phân biệt `BOOT-INF/lib` và `org/springframework/boot/loader/**` |
| Layer index có bốn tên nhưng Docker image chỉ một app copy layer | Dockerfile `COPY outer.jar` một lần | Dùng tools extract và `COPY` riêng các thư mục |
| Docker build cache vẫn miss | Base image/dependency/plugin đổi, CI cache bị mất, file metadata biến động | So sánh content, lock dependency và xem Docker/BuildKit logs |
| Container image chạy lỗi `ClassNotFoundException` | Thiếu một nhóm thư mục extracted hoặc custom layer không được `COPY` | So sánh `layers.idx` với mọi `COPY` trong Dockerfile |
| App resource bị mất sau extract | Copy sai path, custom rule không nhận resource | Xem `BOOT-INF/classes/demo/build-marker.txt` trong index/extraction |
| Maven custom `layers.xml` không load | Sai path/schema XML, plugin config sai chỗ | Kiểm tra `layers.configuration` và log plugin `repackage` |
| Gradle custom layers bị xếp sai | Confuse thứ tự `intoLayer` với `layerOrder` | Rule claim trước, output order riêng, bao gồm mọi layer |
| JAR vẫn chạy `java -jar` nhưng cache không tốt | Runtime đúng, nhưng extraction/COPY/cache chưa tối ưu | Đánh giá Dockerfile và layer reuse, không coi runnable là đủ |
| Plain JAR không đọc được Boot layer tools | Không phải Spring Boot executable JAR | Chạy đúng `bootJar` hoặc `repackage` artifact |
| Custom `company-dependencies` bị thiếu trong final image | Dockerfile vẫn copy bốn layer mặc định | Bổ sung thư mục/`COPY` tương ứng và smoke-test |
| Thay version SNAPSHOT nhưng hash layer release đổi | Có thể graph/transitive dependencies cũng đổi | Kiểm tra resolved graph, BOM, repository và archive metadata |
| Build khác nhau khi chạy từ IDE và Docker | Toolchain, dependency resolution, packaging/runtime khác | Pin Java 17, plugin versions, dùng đúng packaged artifact |

## 24. Checklist hiểu đúng và vận dụng bốn layer

- [ ] Đã phân biệt **Spring Boot archive layers** với **Docker/OCI image layers**.
- [ ] Nắm đúng **thứ tự mặc định**: `dependencies → spring-boot-loader → snapshot-dependencies → application`.
- [ ] Biết `dependencies` chứa external non-SNAPSHOT release dependencies, **không** phải toàn bộ `BOOT-INF/lib`.
- [ ] Biết `spring-boot-loader` chứa các class launcher/loader ở outer archive, **khác** nested `spring-boot-*.jar`.
- [ ] Biết `snapshot-dependencies` chứa external SNAPSHOT, có thể rỗng khi không có SNAPSHOT.
- [ ] Biết `application` chứa class/resource app và local Gradle project/Maven reactor module dependencies.
- [ ] Không nhầm “group nội bộ” với “module nằm trong reactor/project”.
- [ ] `jar tf` có `BOOT-INF/layers.idx`, và index phản ánh tên/thứ tự/nội dung chính xác.
- [ ] Dùng **`-Djarmode=tools` của Spring Boot 3.3**, không trộn lệnh của phiên bản cũ.
- [ ] Biết `list-layers` và `extract --layers --destination`, cùng đường dẫn lớp sau giải nén.
- [ ] Maven `spring-boot-maven-plugin` đã thực thi `repackage`, Gradle dùng `bootJar`; không chọn plain JAR.
- [ ] Nếu custom Gradle, `intoLayer` xét **claim order** và `layerOrder` xét **output order**.
- [ ] Nếu custom Maven, `layers.xml` có đầy đủ `application`, `dependencies`, `layerOrder` đúng schema.
- [ ] Mọi custom layer xuất hiện trong index đều được image builder xử lý/copy đủ.
- [ ] Dockerfile phân lớp thật sự bằng các thao tác `COPY`, không chỉ copy nguyên outer JAR.
- [ ] Không coi lớp SNAPSHOT là cơ chế khóa version/bytes; release vẫn cần immutable artifact policy.
- [ ] Đã test `java -jar` trên packaged archive **và** smoke-test OCI image sau extraction.
- [ ] CI kiểm tra lớp bằng file thực, dependency graph và image provenance, không suy luận từ filename.

**Ghi nhớ:** `dependencies` là external release libraries, `spring-boot-loader` là loader classes, `snapshot-dependencies` là external SNAPSHOT libraries và `application` chứa application code/resources cùng local project/module dependencies. **Rule claim** quyết định một entry thuộc lớp nào, **layer order** quyết định thứ tự đặt các lớp để tối ưu cache, còn **Dockerfile/buildpack** quyết định cách những nhóm ấy trở thành các OCI layers thật. Kiểm chứng bằng **`layers.idx → jarmode tools → extracted directories → image COPY → smoke test`**.

## Tài liệu tham khảo chính thức (đúng nhánh Spring Boot 3.3)

- [Spring Boot 3.3 — Gradle Plugin: Packaging Layered Jar or War](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 — Maven Plugin: Layered Jar or War / Custom Layers](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Efficient Container Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/efficient-images.html)
- [Spring Boot 3.3 — Dockerfiles and jarmode tools](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot — Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Gradle — Dependencies and Project Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html)
- [Docker — Optimizing Builds with Cache](https://docs.docker.com/build/cache/optimize/)