# Vai trò của layers.idx và phân biệt với classpath.idx

## 1. Mục tiêu bài học

Trong Spring Boot, một executable JAR có thể mang theo hai file ở thư mục `BOOT-INF`: **`classpath.idx`** và **`layers.idx`**. Chúng đều có định dạng văn bản đơn giản, thường được Spring Boot Maven/Gradle Plugin tạo ra lúc đóng gói, nhưng trả lời **hai câu hỏi hoàn toàn khác nhau**:

- **`classpath.idx`:** Khi chạy executable archive bằng `java -jar`, Spring Boot Loader phải thêm **các JAR lồng bên trong** vào classpath **theo thứ tự nào**?
- **`layers.idx`:** Khi một công cụ tạo image muốn trích nội dung archive, **file/thư mục nào thuộc lớp nào**, và các lớp ấy nên được **sắp theo thứ tự nào trong Docker/OCI image**?

Một index phục vụ **thứ tự classloading**, index còn lại phục vụ **chiến lược phân lớp và cache của container image**. Cùng được đặt trong `BOOT-INF` không có nghĩa chúng có cùng tác dụng. Đặc biệt, chỉ cần một JAR có `layers.idx` **không làm Docker tự chia bốn image layers** khi Dockerfile chỉ `COPY app.jar`.

Sau bài này, bạn sẽ biết:

1. Đọc cấu trúc Spring Boot nested executable JAR.
2. Xác định vị trí, cú pháp và thời điểm sử dụng của từng index.
3. Phân biệt classpath ordering với dependency version resolution và image layer ordering.
4. Giải thích bốn lớp mặc định `dependencies`, `spring-boot-loader`, `snapshot-dependencies`, `application`.
5. Tạo và chạy một JAR Spring Boot có hai chỉ mục bằng Maven hoặc Gradle.
6. Kiểm tra nội dung qua `jar tf`, `unzip -p`, công cụ JDK, `jarmode=tools list-layers` và `extract --layers`.
7. Dùng layered extraction trong một Dockerfile nhiều giai đoạn với các lệnh `COPY` theo đúng thứ tự.
8. Cấu hình bật/tắt hoặc custom layers bằng Maven XML hay Gradle DSL; không sửa raw index bằng tay.
9. Chẩn đoán lỗi thiếu tệp, chạy IDE khác packaged JAR, dependencies trùng, Docker cache không như kỳ vọng.
10. Xác định giới hạn của hai index đối với WAR, thin JAR, shaded JAR và reproducible builds.

**Ngữ cảnh ví dụ:** Spring Boot **3.5.16**, Java **17+**, Maven/Gradle tương thích, packaging executable JAR. Java 17, Spring Boot 3.5.x chỉ là phạm vi thực hành có tên API và công cụ rõ ràng; không có nghĩa mọi dự án phải dùng đúng version này.

## 2. Cấu trúc một executable Spring Boot JAR

Spring Boot đóng gói dependencies dưới dạng **nested JARs** (mỗi dependency vẫn là một file JAR bên trong outer JAR), thay vì giải nén mọi `.class` và gộp phẳng theo kiểu Maven Shade/Gradle Shadow.

~~~text
layer-index-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/indexdemo/
    │   │   └── LayerIndexApplication.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-3.5.16.jar
    │   ├── commons-lang3-3.17.0.jar
    │   └── ... các JAR runtime khác ...
    ├── classpath.idx
    └── layers.idx
~~~

Cây trên là **mô hình**; các dependencies ngoài hai tên minh họa phụ thuộc resolved graph. Muốn biết nội dung thật, dùng `jar tf` trên file thật. Tệp `spring-boot-3.5.16.jar` là dependency JAR, còn `JarLauncher.class` ở root là class của Boot Loader được đóng vào executable archive.

| Vị trí | Chức năng |
| --- | --- |
| `META-INF/MANIFEST.MF` | Khai báo `Main-Class` là Spring Boot `JarLauncher`, `Start-Class` là class `main` của ứng dụng |
| `org/springframework/boot/loader/**` | Loader classes giúp chạy với nested libraries |
| `BOOT-INF/classes/` | Application classes, resources và file cấu hình của project |
| `BOOT-INF/lib/*.jar` | Runtime dependencies giữ nguyên ranh giới JAR |
| `BOOT-INF/classpath.idx` | Danh sách path và thứ tự nạp dependency JARs |
| `BOOT-INF/layers.idx` | Mapping các archive entries vào logical image layers |

Vì JVM Java launcher bình thường không tự duyệt mọi file JAR lồng trong `BOOT-INF/lib` để thêm chúng vào classpath, Spring Boot Loader là thành phần khởi động phù hợp với layout này.

### 2.1. Hai luồng khác nhau

~~~text
LUỒNG A: Khởi động ứng dụng
java -jar app.jar
  -> META-INF/MANIFEST.MF
  -> Boot JarLauncher
  -> BOOT-INF/classes và BOOT-INF/lib
  -> BOOT-INF/classpath.idx: thứ tự nested dependency JARs
  -> Start-Class.main(args)
  -> SpringApplication.run(...)

LUỒNG B: Tạo Docker/OCI image theo lớp
mvn package / gradle bootJar
  -> executable app.jar chứa BOOT-INF/layers.idx
  -> jarmode tools / image build tooling
  -> trích dependencies, loader, snapshot deps, app
  -> Dockerfile COPY từng lớp theo thứ tự
  -> Image filesystem layers + container cache
~~~

**Không có bước “layers.idx quyết định class nào được load trước”.** Ngược lại, `classpath.idx` không quy định Docker layer `dependencies` được copy trước hay sau `application`.

## 3. classpath.idx: thứ tự thư viện trên classpath

### 3.1. File và cú pháp

`BOOT-INF/classpath.idx` là một danh sách **các tên JAR path kèm thư mục**, theo đúng thứ tự mà loader cần thêm vào application classpath.

Ví dụ hợp lệ khi archive thực sự có `alpha-1.0.jar` và `beta-2.0.jar`:

~~~text
- "BOOT-INF/lib/beta-2.0.jar"
- "BOOT-INF/lib/alpha-1.0.jar"
~~~

Mỗi dòng có dạng `- "BOOT-INF/lib/<dependency>.jar"`, cụ thể:

- Bắt đầu bằng **dash + một khoảng trắng** (`- `).
- Đường dẫn nội bộ archive được đặt trong **dấu nháy kép**.
- Danh sách chỉ gồm các JAR paths theo thứ tự; **không có tên layer**.
- Dùng dấu `/` cho path trong ZIP/JAR, kể cả trên Windows.
- Một tệp được mô tả là ở `BOOT-INF/lib/foo.jar` thì phải thực sự có entry tương ứng trong archive.

Đây là syntax **tương thích YAML** nhưng Boot **không parse như một tài liệu YAML tùy ý**. Không tự thêm anchors/tags/comments/map keys chỉ vì YAML parser khác chấp nhận được.

### 3.2. Vì sao cần xác định thứ tự?

Thứ tự classpath có thể ảnh hưởng lookup khi hai JAR có:

- Cùng fully-qualified Java class name do phụ thuộc phiên bản xung đột.
- Resource trùng tên, ví dụ `META-INF/services/...`, một file properties hay XML.
- Library gọi `ClassLoader.getResource(...)` và nhận resource đầu tiên thay vì đọc mọi resource bằng `getResources(...)`.

Spring Boot build plugins thường sinh classpath index để launcher biết thứ tự dependency JARs tương ứng với build system. Nhưng **index không phải công cụ sửa dependency conflict**: nếu có hai JAR cùng chứa class xung đột, nên sửa BOM/constraints/exclusions trong Maven/Gradle rồi rebuild, không sửa thứ tự index để “cho bản đúng thắng”.

### 3.3. Chỉ dùng trong packaged run

Tài liệu Spring Boot 3.5 nêu rõ `classpath.idx` được Boot dùng khi executable JAR/WAR chạy với **`java -jar`**.

| Cách chạy | Có dùng packaged classpath.idx? |
| --- | --- |
| `java -jar target/app.jar` | Có thể có, khi index tồn tại và Boot Loader đọc archive |
| `java -jar build/libs/app.jar` | Có thể có |
| Nhấn Run main class từ IDE | **Không** |
| `mvn spring-boot:run` | **Không** |
| `./gradlew bootRun` | **Không** |
| JUnit chạy trong project classpath | **Không** |
| Plain Java JAR chạy qua `java -cp ...` | **Không tự dùng Boot index** |

Đây là lý do cần test **chính executable archive** bên cạnh việc run trong IDE. Nếu lỗi chỉ xảy ra khi `java -jar`, hãy so cả runtime dependencies và index với classpath của IDE. Đừng mặc định index là thủ phạm duy nhất: exclusion, profiles, file location và classloader behavior cũng có thể khác.

### 3.4. classpath.idx không phải dependency lockfile

`classpath.idx` chỉ ghi **đường dẫn các JAR đã được đóng gói**. Nó không:

- Tải dependency thiếu từ Maven Central/Gradle repository.
- Chọn phiên bản mới của library.
- Thực hiện dependency conflict resolution thay cho Maven/Gradle.
- Khóa transitive dependency graph như `gradle.lockfile`.
- Kéo thêm JAR nếu chỉ có một dòng index mà không có bytes trong `BOOT-INF/lib`.

Để đổi dependency version, sửa source build configuration và rebuild executable JAR.

### 3.5. Reproducible builds ảnh hưởng thứ tự

Spring Boot ghi nhận khi bật reproducible build behavior, các entry trong `classpath.idx` có thể được **sắp alphabetically**. Vì vậy đừng hứa rằng dòng đầu index luôn phản ánh thứ tự dependency declaration trong `pom.xml` hoặc `build.gradle.kts`.

Khi cần kiểm hành vi cụ thể, đọc trực tiếp file trong output và so với `mvn dependency:tree`/Gradle `dependencyInsight`. Tránh phụ thuộc vào hành vi “first JAR wins” cho logic ứng dụng.

## 4. layers.idx: bản đồ các lớp dùng cho Docker/OCI

### 4.1. Cú pháp layers.idx

`BOOT-INF/layers.idx` gồm **layer names**, mỗi layer có danh sách paths thuộc nó. Ví dụ **minh họa**, không phải dump chính xác của một bản build:

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/spring-boot-3.5.16.jar"
  - "BOOT-INF/lib/commons-lang3-3.17.0.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "snapshot-dependencies":
  - "BOOT-INF/lib/my-lib-1.0-SNAPSHOT.jar"
- "application":
  - "BOOT-INF/classes/"
  - "META-INF/"
~~~

Mỗi layer name được viết `- "layer-name":`. Các entry của layer thụt hai dấu cách rồi bắt đầu `- "path"`. **Đường dẫn thư mục** kết thúc bằng `/`, còn đường dẫn file thì không. Khi chỉ một directory, nội dung phía dưới directory đó thuộc cùng layer.

**Đừng chép nguyên ví dụ này vào JAR thật**: khi project không có `my-lib-1.0-SNAPSHOT.jar`, dòng đó không phù hợp artifact. Plugin tạo index dựa trên dependencies và files thực tế.

### 4.2. Bốn layer mặc định

Spring Boot Maven và Gradle plugins mặc định dùng:

| Layer | Nội dung mặc định chính | Đặc điểm thay đổi |
| --- | --- | --- |
| `dependencies` | Libraries release thường gặp | Thường thay ít lần |
| `spring-boot-loader` | Boot Loader classes ở `org/springframework/boot/loader/**` | Thay khi đổi Boot Loader |
| `snapshot-dependencies` | External SNAPSHOT libraries | Có thể thay thường xuyên |
| `application` | App classes/resources và local module/project dependencies | Thường thay theo commit |

Thứ tự mặc định:

~~~text
1. dependencies
2. spring-boot-loader
3. snapshot-dependencies
4. application
~~~

Lý do là **cache locality**: những phần ít thay đổi được đưa vào các lớp sớm; code ứng dụng hay đổi được đặt ở các lớp sau. Khi source thay đổi mà dependencies không đổi, Docker/OCI builder có thể tái dùng layer trước đó và chỉ build/push/pull phần bị thay đổi theo cơ chế cache thực tế.

**Không có lời hứa hiệu năng tuyệt đối:** Nếu library versions thay mỗi build, `dependencies` cũng invalidated; nếu base image digest đổi, cache behavior lại khác. Việc có layer names không tự chứng minh image startup nhanh hơn theo một tỷ lệ nhất định.

### 4.3. Local module dependencies: khác external dependencies

Trong Maven multi-module reactor, Boot plugin có thể xếp các dependencies tương ứng với modules **thuộc current build** vào `application`, không coi chúng là các release external dependencies. Nếu dependency nội bộ chỉ được resolve từ local Maven cache vì không nằm trong current reactor, nó có thể được phân như regular dependency.

Gradle mặc định nhận diện `project(":shared")` dependencies để xếp chúng vào `application`. Những libraries đến từ external repositories được xét theo quy tắc release/SNAPSHOT.

**Không suy đoán dựa trên groupId:** Một dependency `com.example:shared` nằm ở `application` hay `dependencies` còn tùy nó là module dependency của build hiện tại hay JAR đã publish/được resolve độc lập. Muốn chắc, đọc `layers.idx` của artifact thật.

### 4.4. layers.idx không can thiệp runtime classpath

Trong index này, một library có thể ở layer `dependencies`, nhưng chưa biết nó đứng trước hay sau library khác trên runtime classpath. Để biết thứ tự loader, hãy đọc **`classpath.idx`**. Thêm một layer “business-libs” không tự tạo một classloader Java mới, không bật/tắt Spring profiles và không thay version được resolver chọn.

## 5. Bảng đối chiếu: hai index không thay thế được nhau

| Đặc trưng | classpath.idx | layers.idx |
| --- | --- | --- |
| Câu hỏi | “Những nested JAR nào được load theo thứ tự nào?” | “Archive entries thuộc image layer nào?” |
| File ở JAR | `BOOT-INF/classpath.idx` | `BOOT-INF/layers.idx` |
| Cấu trúc dữ liệu | Một danh sách JAR paths | Danh sách layer names và nested path lists |
| Loại thứ tự | Classpath loading order | Docker/OCI layer order |
| Thành phần dùng | Spring Boot Loader khi `java -jar` | Jarmode tools/image tooling/buildpacks |
| Công việc chính | Hỗ trợ runtime classloading | Tách image contents để reuse cache |
| Đề cập app classes? | Không, chủ yếu library paths | Có, ví dụ `BOOT-INF/classes/` |
| Đề cập Boot Loader classes? | Không | Có, layer `spring-boot-loader` |
| Dùng lúc IDE `main` run? | Không | Không |
| Khóa versions? | Không | Không |
| Tự tạo Docker image? | Không | Không |
| Chỉnh sửa thủ công? | Không nên; build lại từ dependency graph | Không nên; chỉnh layer policy trong plugin |
| Không tồn tại? | Packaged app có thể vẫn chạy nhưng không có order hints | App có thể vẫn chạy, image layering tools thiếu metadata |

**Ghi nhớ:** `classpath.idx = thứ tự classpath`; `layers.idx = nhóm cache layer`.

## 6. Maven Spring Boot project hoàn chỉnh để thực hành

Ví dụ Java 17 dùng `spring-boot-starter`, **không cần web server, database hoặc Docker để chạy bước Maven đầu tiên**. Một dependency Commons Lang được khai báo để nhìn thấy một nested library rõ ràng.

### 6.1. Cây project

~~~text
layer-index-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/indexdemo/LayerIndexApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/indexdemo/LayerIndexApplicationTest.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>layer-index-demo</artifactId>
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
            <version>3.17.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <layers>
                        <enabled>true</enabled>
                    </layers>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot starter parent đã thiết lập `repackage` execution; khai báo plugin như trên khiến `mvn package` tạo **executable Boot JAR**. Trong Boot 3.5, layered packaging thường đã bật theo mặc định, nên `enabled=true` là dòng chủ ý để bài học dễ kiểm chứng, không phải một điều kiện bắt buộc của mọi project.

Không thêm Maven Shade Plugin cho project này. Shade thường gộp thư viện theo layout khác Boot nested JAR.

### 6.3. Java source có thể chạy

Tạo `src/main/java/com/example/indexdemo/LayerIndexApplication.java`:

~~~java
package com.example.indexdemo;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LayerIndexApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayerIndexApplication.class, args);
    }

    public static String outputMessage() {
        return "LAYERS_OK " + StringUtils.capitalize("hello");
    }

    @Bean
    ApplicationRunner printMessage() {
        return args -> System.out.println(outputMessage());
    }
}
~~~

`StringUtils.capitalize("hello")` trả `Hello`. Dòng **do ApplicationRunner tự in sau khi context khởi tạo** là chính xác:

~~~text
LAYERS_OK Hello
~~~

Spring Boot còn log khởi động tùy môi trường, vì vậy không khẳng định toàn bộ stdout chỉ chứa một dòng trên.

### 6.4. application.properties

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=layer-index-demo
~~~

Sau package, resource này nằm trong `BOOT-INF/classes/application.properties`, thông thường thuộc `application` layer. File này không phải index file; nó là Spring Boot config data.

### 6.5. JUnit test

Tạo `src/test/java/com/example/indexdemo/LayerIndexApplicationTest.java`:

~~~java
package com.example.indexdemo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LayerIndexApplicationTest {

    @Test
    void outputIsDeterministic() {
        assertEquals("LAYERS_OK Hello",
                LayerIndexApplication.outputMessage());
    }
}
~~~

Test tự chạy với JUnit Jupiter từ `spring-boot-starter-test`. Nó **không tự in stdout** và không cần external service, phù hợp kiểm tra logic độc lập với Docker pipeline.

### 6.6. Build, run, inspect

Linux/macOS có Maven cài sẵn:

~~~bash
java -version
mvn -version
mvn clean package
java -jar target/layer-index-demo-1.0.0.jar
jar tf target/layer-index-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
java -version
mvn -version
mvn clean package
java -jar .\target\layer-index-demo-1.0.0.jar
jar tf .\target\layer-index-demo-1.0.0.jar
~~~

Nếu tạo project bằng Spring Initializr và **thật sự có Maven Wrapper**, thay `mvn` bằng `./mvnw` (Linux/macOS) hoặc `.\mvnw.cmd` (Windows). Không giả định project tự tạo từ cây file có wrapper scripts.

Trong output `jar tf` tìm:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/indexdemo/LayerIndexApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/commons-lang3-3.17.0.jar
BOOT-INF/classpath.idx
BOOT-INF/layers.idx
~~~

Nếu phiên bản, packaging configuration hoặc repository resolutions khác ví dụ, tên dependencies có thể thay. Chỉ có `jar tf` trên artifact thật mới xác nhận được nội dung thực.

## 7. Đọc nội dung hai index

### 7.1. Linux/macOS có unzip

~~~bash
unzip -p target/layer-index-demo-1.0.0.jar BOOT-INF/classpath.idx
unzip -p target/layer-index-demo-1.0.0.jar BOOT-INF/layers.idx
~~~

`unzip -p` in nội dung entry lên stdout mà không giải nén hay chỉnh JAR. File `classpath.idx` sẽ có các dòng dạng `- "BOOT-INF/lib/foo.jar"`; file `layers.idx` có các nhóm dạng `- "application":` rồi các file paths.

Chỉ kiểm vị trí index trong archive:

~~~bash
jar tf target/layer-index-demo-1.0.0.jar |
  grep -E '^BOOT-INF/(classpath|layers)\.idx$'
~~~

Nếu có cả hai, output từ `grep` có thể là:

~~~text
BOOT-INF/classpath.idx
BOOT-INF/layers.idx
~~~

### 7.2. Windows PowerShell với JDK

JDK `jar` có thể extract **chỉ những entries chỉ định**. Để tránh đụng file có sẵn, tạo thư mục kiểm tra riêng:

~~~powershell
$archive = (Resolve-Path .\target\layer-index-demo-1.0.0.jar).Path
New-Item -ItemType Directory -Force .\inspect-index | Out-Null
Push-Location .\inspect-index

jar xf $archive BOOT-INF/classpath.idx BOOT-INF/layers.idx
Get-Content .\BOOT-INF\classpath.idx
Get-Content .\BOOT-INF\layers.idx

Pop-Location
~~~

Đoạn này giả định `inspect-index` là directory kiểm tra mới và bạn có quyền ghi. Trong project chung, chọn một thư mục trống không chứa dữ liệu quan trọng trước khi `jar xf`. Không nén lại JAR sản phẩm sau khi đọc index.

### 7.3. Phân tích ví dụ một dependency

Giả sử cả hai tệp có thông tin về Commons Lang.

Ở `classpath.idx`:

~~~text
- "BOOT-INF/lib/commons-lang3-3.17.0.jar"
~~~

Nó cho biết **vị trí Commons Lang JAR trong thứ tự runtime classpath** khi archive chạy qua launcher.

Ở `layers.idx`:

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/commons-lang3-3.17.0.jar"
~~~

Nó cho biết **đường dẫn này được xếp vào layer dependencies** cho image tooling.

**Không thể suy thứ tự classpath từ layer membership, cũng không suy layer membership từ một dòng classpath index.**

## 8. Jarmode tools của Spring Boot 3.5

### 8.1. Lệnh đúng theo Boot 3.5

Layered executable Boot 3.5 JAR thường mang dependency **`spring-boot-jarmode-tools`**. Công cụ cung cấp chế độ `-Djarmode=tools` để xem hoặc trích archive mà **không khởi động application logic**.

~~~bash
java -Djarmode=tools -jar target/layer-index-demo-1.0.0.jar
~~~

Công cụ hiển thị thông tin usage, với các subcommands như `extract`, `list-layers` và `help`.

Liệt kê layer names:

~~~bash
java -Djarmode=tools \
  -jar target/layer-index-demo-1.0.0.jar \
  list-layers
~~~

Đối với default layering, bạn nên nhận thấy các tên:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Đây là **dạng output minh họa về tên layer**, không yêu cầu mọi chi tiết usage/log phải đúng nguyên văn. Nếu project có custom layers, tên sẽ thay đổi.

**Cảnh báo khác phiên bản:** một số hướng dẫn Spring Boot 2.x/3.x cũ dùng `-Djarmode=layertools` và `spring-boot-jarmode-layertools`. Với **Spring Boot 3.5**, dùng **`-Djarmode=tools`** và `spring-boot-jarmode-tools`. Đừng sao chép lệnh từ tài liệu không cùng major/minor version.

### 8.2. Trích layers

~~~bash
java -Djarmode=tools \
  -jar target/layer-index-demo-1.0.0.jar \
  extract --layers --destination extracted
~~~

Windows PowerShell:

~~~powershell
java "-Djarmode=tools" -jar .\target\layer-index-demo-1.0.0.jar extract --layers --destination extracted
~~~

Với default layers, công cụ tạo output được tách theo layer names, ví dụ:

~~~text
extracted/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
~~~

Một layer có thể rỗng nếu project không có dependency thuộc nhóm đó. Sử dụng một directory do bạn kiểm soát; nếu đã có files từ lần trích cũ, dùng destination khác hoặc chủ động kiểm tra để không trộn nội dung giữa các build.

Xem flags hiện có:

~~~bash
java -Djarmode=tools -jar target/layer-index-demo-1.0.0.jar extract --help
~~~

### 8.3. Vì sao không chỉ unzip outer JAR?

Tools mode hiểu **layer metadata và launcher layout**. Chỉ dùng `unzip app.jar` giải nén toàn bộ files vào một directory không tự tạo các thư mục `dependencies`, `application` theo đúng cache policy.

Đặc biệt, extracted layout có thể tạo **`application.jar` dùng với launcher mode**, khác outer Uber JAR mà builder nhận trước khi extract. Vì vậy khi làm Dockerfile theo Spring Boot docs, phải dùng đúng `extract --layers` rồi dùng entrypoint tương ứng, không tùy tiện chỉ copy raw files và tự đoán classpath.

### 8.4. Khi tools mode không chạy được

Hãy kiểm các điều kiện:

- Đây là **Boot executable archive**, không phải thin JAR hoặc shaded JAR thông thường.
- Plugin thật sự tạo layered archive.
- `spring-boot-jarmode-tools` không bị loại qua `includeTools=false`.
- JDK/JRE tương thích release Boot và application classes.
- Archive không bị prepend **fully executable launch script** làm tools mode không còn hỗ trợ.
- Lệnh thật sự đặt `-Djarmode=tools` **trước** `-jar`; nó là JVM system property.

Nếu thiếu tool do cấu hình, muốn trích layers phải dùng công cụ khác hoặc điều chỉnh packaging. Không sửa ngẫu nhiên raw JAR index như một cách chữa lỗi.

## 9. Từ layers.idx đến một Docker image chia lớp

### 9.1. Dockerfile đơn giản chưa tiêu thụ layers.idx

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/layer-index-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Dockerfile này có thể chạy được Spring Boot application. Nhưng bước `COPY` đưa **cả file JAR** vào một image filesystem layer. Khi chỉ đổi một Java class, outer JAR bytes đổi và layer `COPY` phải được cập nhật. **Docker không tự parse `BOOT-INF/layers.idx`** chỉ vì file JAR có nó.

### 9.2. Dockerfile multi-stage theo Boot 3.5

Đặt Dockerfile tại Maven project root, sau khi đã chạy `mvn clean package`. Ví dụ dưới dùng image Java 17 minh họa:

~~~dockerfile
FROM eclipse-temurin:17-jre AS builder
WORKDIR /builder
COPY target/layer-index-demo-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=builder /builder/extracted/dependencies/ ./
COPY --from=builder /builder/extracted/spring-boot-loader/ ./
COPY --from=builder /builder/extracted/snapshot-dependencies/ ./
COPY --from=builder /builder/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**Các bước hoạt động:**

1. Builder nhận đúng outer Boot JAR có tools mode.
2. `extract --layers` trích contents thành bốn logical directories theo `layers.idx`.
3. Runtime stage `COPY` các thư mục theo thứ tự: dependencies, loader, snapshot-dependencies, application.
4. Mỗi `COPY` tạo một cache boundary/filesystem layer phù hợp với cách Docker image build hoạt động.
5. Entry point gọi `application.jar` được tạo trong **extracted launcher layout**, **không phải** outer `/builder/application.jar` đã copy ban đầu.

Sau khi build file JAR, chạy:

~~~bash
docker build -t layer-index-demo:local .
docker run --rm layer-index-demo:local
~~~

Ứng dụng mẫu không có HTTP server nên không cần map port. Dòng business output vẫn là:

~~~text
LAYERS_OK Hello
~~~

### 9.3. Cơ hội reuse cache

Nếu source `LayerIndexApplication.java` đổi nhưng dependencies vẫn giống nhau, layer `application` đổi trong khi `dependencies` có thể reuse. Nếu bạn nâng một library release, `dependencies` đổi; nếu `spring-boot-loader` đổi do nâng Boot, layer loader cũng đổi.

Đây là **cơ chế tăng hiệu quả cache**, không phải cam kết “mỗi build chỉ upload lớp cuối”: cache phụ thuộc Docker builder, registry state, base image, archive metadata, timestamps và build inputs.

**Thứ tự `COPY` là thiết kế có ý nghĩa.** Nếu copy app thay đổi thường xuyên ở trước dependencies, nhiều builder sẽ invalidate các bước sau và làm mất lợi thế caching.

### 9.4. Lưu ý supply chain

`eclipse-temurin:17-jre` là tag dễ đọc cho ví dụ; tag có thể trỏ sang bytes mới khi nhà cung cấp cập nhật. Trong CI/release đòi hỏi reproducibility, dùng image **digest đã được xác minh thật** thay vì tự bịa hash. Đừng lưu credentials trong Dockerfile hoặc file `application.properties` đóng trong artifact.

Nếu dùng Cloud Native Buildpacks (`spring-boot:build-image` hoặc Gradle `bootBuildImage`), image builder có chiến lược phân lớp riêng; không cần sao chép Dockerfile jarmode nếu buildpacks đã thỏa mãn yêu cầu.

## 10. Cấu hình layer metadata trong Maven

### 10.1. Bật/tắt layers

Spring Boot 3.5 Maven Plugin mặc định hỗ trợ layered archive. Nếu không cần layer metadata, có thể cấu hình:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layers>
            <enabled>false</enabled>
        </layers>
    </configuration>
</plugin>
~~~

Đây là **snippet bên trong `<build><plugins>`**, không phải POM độc lập. Khi tắt layers, `layers.idx` có thể không được tạo; **`java -jar` không cần index này để khởi động Spring ApplicationContext**. Đừng nhầm tùy chọn layer metadata với việc vô hiệu hóa `classpath.idx` hay Boot Loader.

### 10.2. Custom layers.xml là INPUT, layers.idx là OUTPUT

Để thay policy, trỏ plugin tới file cấu hình:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layers>
            <enabled>true</enabled>
            <configuration>${project.basedir}/src/layers.xml</configuration>
        </layers>
    </configuration>
</plugin>
~~~

Tạo `src/layers.xml` với một cấu hình đầy đủ minh họa **default behavior** của Spring Boot 3.5:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<layers xmlns="http://www.springframework.org/schema/boot/layers"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.springframework.org/schema/boot/layers
            https://www.springframework.org/schema/boot/layers/layers-3.5.xsd">
    <application>
        <into layer="spring-boot-loader">
            <include>org/springframework/boot/loader/**</include>
        </into>
        <into layer="application" />
    </application>
    <dependencies>
        <into layer="application">
            <includeModuleDependencies />
        </into>
        <into layer="snapshot-dependencies">
            <include>*:*:*SNAPSHOT</include>
        </into>
        <into layer="dependencies" />
    </dependencies>
    <layerOrder>
        <layer>dependencies</layer>
        <layer>spring-boot-loader</layer>
        <layer>snapshot-dependencies</layer>
        <layer>application</layer>
    </layerOrder>
</layers>
~~~

**Đây là cấu hình XML cho build plugin**, không phải nội dung tệp `layers.idx`. Maven đọc XML khi package, quyết định membership, rồi sinh raw index tương ứng trong executable archive.

### 10.3. Cơ chế claim và layerOrder

- `<application>` định nghĩa cách phân application classes/resources và Boot Loader entries.
- `<dependencies>` định nghĩa cách phân dependency artifacts.
- `<into>` được đánh giá **từ trên xuống**, nội dung đã được block trước claim không còn cho block sau.
- Rule `<includeModuleDependencies />` claim local modules vào `application`.
- Rule `<include>*:*:*SNAPSHOT</include>` claim phù hợp SNAPSHOT dependencies.
- Rule `<into layer="dependencies" />` không có include hoạt động như catch-all cho các dependencies còn lại.
- `<layerOrder>` quy định **thứ tự ghi layers**, có thể khác thứ tự các rule `<into>` xét files. Phải khai báo mọi layer tham gia.

Muốn tách thêm layer theo group/artifact, dùng include patterns đúng syntax trong `<dependencies>` và thêm layer mới vào `<layerOrder>`. Không sửa raw `layers.idx` sau package.

### 10.4. Ví dụ thêm một layer nội bộ

Bên trong `<dependencies>` của file custom XML, trước catch-all:

~~~xml
<into layer="internal-libraries">
    <include>com.acme:*:*</include>
</into>
~~~

Đây là **đoạn cấu hình**, không phải file XML đầy đủ. Cần thêm `<layer>internal-libraries</layer>` vào `layerOrder` và để rule ở vị trí có thể claim artifacts mong muốn. Nếu một local module đã được rule `includeModuleDependencies` claim vào `application`, rule sau không thể nhận nó lần hai. Chỉ thay layer policy khi có dữ liệu cho thấy việc tách library này cải thiện cache/deploy.

## 11. Dự án Gradle Kotlin DSL tương đương

### 11.1. Cấu trúc và source

Dùng **hai Java files** `LayerIndexApplication.java` và `LayerIndexApplicationTest.java` ở mục 6 trong một project Gradle riêng, cùng `application.properties`. Cây ví dụ:

~~~text
layer-index-gradle/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/java/com/example/indexdemo/LayerIndexApplication.java
    ├── main/resources/application.properties
    └── test/java/com/example/indexdemo/LayerIndexApplicationTest.java
~~~

Wrapper `gradlew`/`gradlew.bat` chỉ có nếu project thực sự đã tạo/commit nó.

### 11.2. settings.gradle.kts

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "layer-index-gradle"
~~~

### 11.3. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.tasks.testing.Test
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
    testImplementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.apache.commons:commons-lang3:3.17.0")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

tasks.named<BootJar>("bootJar") {
    layered {
        enabled.set(true)
    }
}
~~~

Ở Gradle, `bootJar` tạo executable Boot JAR. Spring Boot Gradle Plugin cần được phối hợp với cơ chế quản lý dependency versions (ví dụ native `platform` như trên hoặc `io.spring.dependency-management`); chỉ áp dụng Boot plugin không tự đưa mọi starter vào classpath với một version thích hợp.

`layered { enabled.set(true) }` là cấu hình tường minh; thông thường Boot layering bật mặc định.

### 11.4. Build và kiểm tệp

Nếu có Gradle Wrapper:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/layer-index-gradle-1.0.0.jar
jar tf build/libs/layer-index-gradle-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
java -jar .\build\libs\layer-index-gradle-1.0.0.jar
jar tf .\build\libs\layer-index-gradle-1.0.0.jar
~~~

Nếu project chưa có wrapper, dùng Gradle cài sẵn tương thích và sinh Wrapper đúng cách cho team. Output filename phụ thuộc `version`/`archiveBaseName`/classifier thật; đừng lấy nhầm `*-plain.jar` từ task `jar` thay vì `bootJar`.

### 11.5. Tắt layer metadata bằng Gradle

Trong `build.gradle.kts`, đoạn cấu hình:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    layered {
        enabled.set(false)
    }
}
~~~

Trong `build.gradle` Groovy DSL:

~~~groovy
tasks.named("bootJar") {
    layered {
        enabled = false
    }
}
~~~

Đây chỉ là snippets ở build scripts thích hợp, **không phải file độc lập**. Tắt layer metadata không làm `bootJar` tự biến thành Maven Shade-style flat JAR; Boot Loader và nested deps vẫn là cơ chế packaging.

### 11.6. Custom layers trong Gradle

Ví dụ Kotlin DSL thuộc `build.gradle.kts` có Spring Boot plugin:

~~~kotlin
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
        layerOrder.set(listOf(
            "dependencies",
            "spring-boot-loader",
            "snapshot-dependencies",
            "application"
        ))
    }
}
~~~

Đây là **mẫu diễn giải default policy**. `intoLayer` được xét theo thứ tự rule, còn `layerOrder` quy định thứ tự lớp khi image tools extract/copy. Hãy tùy biến qua DSL rồi rebuild, không chỉnh raw `layers.idx`.

## 12. Maven reactor, Gradle project dependencies và cache

Một repository nhiều module có:

~~~text
root
├── shared   (Java library)
└── service  (Spring Boot executable JAR phụ thuộc shared)
~~~

Maven `service` khai báo dependency vào `shared` và parent aggregator có `<modules>`; Gradle `service` dùng `implementation(project(":shared"))`. Boot default layering thường xếp **current-build module dependency** ở `application`.

Tại sao? Module nội bộ có thể đổi theo từng commit giống application source, trong khi external stable libraries ít đổi hơn. Tách chúng khỏi `dependencies` giúp giảm khả năng sửa code nội bộ làm invalidated layer chứa third-party libs.

**Cần phân biệt:** Maven module chỉ được coi là local module dependency khi nó là **một phần của current build/reactor**; một thư viện có tọa độ nội bộ nhưng chỉ lấy từ `~/.m2` có thể bị phân loại như ordinary dependency. Vì thế hai lệnh build khác nhau có thể tạo `layers.idx` khác dù cùng GAV. Để kiểm, dùng reactor build thích hợp (`mvn -pl service -am package`) và đọc index.

Một lợi ích khác của `layers.idx` là giúp triển khai theo **change frequency**, không phải theo Java package structure. Một layer có thể chứa nhiều JAR; một Java classpath vẫn gồm tất cả dependencies khi app chạy, bất kể chúng nằm trong image layers nào.

## 13. Các nguồn nhầm lẫn thường gặp

### 13.1. “layers.idx làm JVM nạp dependencies trước code ứng dụng”

Sai. Layer order là order để image builder xếp filesystem layers/cache. Java classloading do Boot Loader và classpath policy chịu trách nhiệm. `layers.idx` không bắt JVM tạo một classloader cho mỗi Docker layer.

### 13.2. “classpath.idx là bản đồ Docker layers”

Sai. Tệp này chỉ cho biết thứ tự dependency JAR entries. Nó không gán `BOOT-INF/classes` vào layer `application` hay `spring-boot-loader` vào layer tương ứng.

### 13.3. “Một ứng dụng có layers.idx thì Docker tự optimize”

Sai. Dockerfile `COPY app.jar` vẫn copy file nguyên khối. Cần jarmode extraction hoặc image tooling hiểu layered metadata.

### 13.4. “Trong IDE đã chạy được nên java -jar cũng chắc chắn giống”

Không chắc chắn. IDE có classpath khác Boot Loader packaged classpath; `classpath.idx` không được dùng trong IDE/`spring-boot:run`/`bootRun`. Test trực tiếp executable artifact và container image.

### 13.5. “Tắt layers.idx sẽ tắt Boot Loader”

Sai. `layers.idx` phục vụ phân phối OCI image. Tắt layered metadata không có nghĩa đổi loại Boot executable archive thành plain JAR.

### 13.6. “Sửa classpath.idx là cách tốt để fix dependency collision”

Không nên. Đó là cách che conflict. Sửa source dependency graph, exclusion/BOM/Gradle constraints và rebuild từ toolchain được quản lý.

### 13.7. “Không có classpath.idx thì JAR chắc chắn không chạy”

Không nhất thiết. Index là metadata tùy chọn. Boot Loader-compatible executable archive có thể chạy không có nó, nhưng thứ tự classpath kỳ vọng cần được xác minh.

### 13.8. “Không có snapshot-dependencies là lỗi”

Không. Project hoàn toàn có thể không sử dụng SNAPSHOT dependency; layer trống hoặc không có members là hợp lý. Tên mặc định có thể hiện trong danh sách layers khi plugin sinh metadata.

### 13.9. “Một JAR có META-INF/MANIFEST.MF thì phải có hai index”

Không. Thin JAR, shaded JAR, plain `jar` task và một số Boot archives tùy cấu hình không mặc định có cả hai. Cần kiểm loại artifact và packaging plugin.

## 14. Chú ý WAR và sự khác biệt so với JAR

Executable Spring Boot WAR có thư mục:

~~~text
WEB-INF/classes/
WEB-INF/lib/
WEB-INF/lib-provided/
~~~

khác với executable JAR (`BOOT-INF/classes` và `BOOT-INF/lib`). Spring Boot 3.5 packaging documentation đề cập **layered JAR hoặc WAR**, trong khi trang đặc tả `Nested JARs / Layer Index` diễn giải cú pháp `BOOT-INF/layers.idx` cho trường hợp executable JAR.

**Đừng sao chép đường dẫn JAR của bài này thành giả định về mọi WAR**. Với WAR, dùng `jar tf actual.war` xác định vị trí index và dependencies do plugin phiên bản thực tế tạo. Khi deploy WAR vào **external servlet container**, container sử dụng web application classloader của nó; đừng kỳ vọng nó dùng `classpath.idx` theo đúng cách Boot `java -jar`.

Đối với app chủ yếu chạy trong container image, hãy xem xét executable JAR nếu không cần external servlet container. Nếu bắt buộc WAR, kiểm cả đường chạy `java -jar` và external deployment theo contract riêng.

## 15. Reproducibility, correctness và bảo mật

### 15.1. Một file index không thay bản dựng tái lập

Khi Maven/Gradle dependency graph hoặc plugin/JDK version thay đổi, hai index có thể thay đổi. Muốn tạo cùng artifact từ cùng source cần quản lý:

- JDK, Maven/Gradle Wrapper và Spring Boot Plugin versions.
- Dependency versions/BOM/Gradle dependency locks.
- Reproducible archive settings: timestamps, file order và generated resources.
- Repositories, artifacts checksums và source revision.
- Container base image digest khi so sánh OCI image output.

Tài liệu Spring Boot lưu ý `classpath.idx` có thể được sắp alphabetically khi bật reproducible builds. **Không** dùng file này để ép version graph hoặc làm security scanner.

### 15.2. Image layering không phải security boundary của application

Một Docker/OCI layer là filesystem changeset và cache unit, **không phải cơ chế bảo mật giúp che secrets**. Dù app/resources được đặt ở layer riêng, secrets hard-code trong `application.properties` vẫn có thể bị đọc từ artifact/image.

Không đưa secret vào source resources, Dockerfile hoặc index custom metadata. Sử dụng môi trường/secret manager và các quyền filesystem phù hợp. Đối với JARs, quét dependencies/SBOM dựa trên graph build và artifact thực, không chỉ dựa vào tên `dependencies` layer.

## 16. Troubleshooting: gặp vấn đề thì kiểm ở tầng nào?

| Dấu hiệu | Khả năng thường gặp | Hành động nên làm |
| --- | --- | --- |
| Không có `BOOT-INF/layers.idx` | Đang đọc plain JAR, layers disabled, plugin chưa repackage | Kiểm output artifact, `spring-boot:repackage`/`bootJar`, plugin config |
| Không có `BOOT-INF/classpath.idx` | Plugin/packaging khác, tệp tùy chọn không sinh | Kiểm manifest, Boot Loader, runtime graph; không tự ghép text |
| `java -jar` chạy được nhưng image cache luôn thay | Dockerfile chỉ `COPY` nguyên JAR | Dùng tools mode extraction và `COPY` mỗi layer |
| `list-layers` không chạy | Không có tools, sai `jarmode`, fully executable script | Kiểm Boot 3.5 `-Djarmode=tools`, `includeTools`, log |
| `extract --layers` báo lỗi | JAR không layered, tools bị exclude hoặc sai flags | Kiểm `jar tf`, `help` và plugin configuration |
| Docker không tìm thấy `extracted/snapshot-dependencies/` | Extract custom layer names hoặc thiếu output directory | `list-layers` và kiểm extraction tree, sửa Dockerfile |
| Chạy IDE được, packaged JAR thiếu class | Dependency scope/exclusion, runtime vs test classpath khác | `jar tf BOOT-INF/lib`, `classpath.idx`, dependency graph |
| JAR packaged chọn resource khác IDE | Classpath order/duplicate resources/profiles | Loại conflict, so classpath, không sửa index như fix chính |
| Custom layer không xuất hiện | `intoLayer`/`layerOrder` sai hoặc content bị rule trước claim | Sửa XML/DSL, rebuild rồi kiểm index |
| Local module nằm trong `dependencies` | Không thuộc current Maven reactor/project dependency | Kiểm `-am`/module graph, custom layer nếu cần |
| `layers.idx` có path không tồn tại | Artifact bị sửa thủ công hoặc tool tùy biến sai | Rebuild từ source và inspect outer archive |
| `jar tf` không thấy class trong commons-lang3 | Class nằm trong nested `BOOT-INF/lib/commons-lang3-...jar` | Xem nested JAR entry, không tìm class ở root |
| Maven thiếu Boot loader/index | Quên Boot plugin `repackage` khi dùng parent khác | Khai báo plugin/execution phù hợp |
| Gradle tạo `*-plain.jar` thiếu indices | Đang xem task `jar` thay `bootJar` | Chạy `bootJar` và kiểm đúng file name |
| Layer `application` đổi dù Java source không đổi | Generated files/timestamps/resources thay | Kiểm reproducible archive inputs, Gradle/Maven plugin flags |
| Container start không tìm `application.jar` | Extract kiểu khác, Dockerfile COPY không đúng | Dùng Boot 3.5 tools example, kiểm file tree thực |

### 16.1. Quy trình năm bước

1. **Chọn đúng artifact:** không nhầm executable JAR với thin/shaded/plain JAR hoặc file `.original`.
2. **Đọc cả hai index:** kiểm syntax và những paths đang có trong archive.
3. **Tách triệu chứng:** lỗi class/resource loader thì xem `classpath.idx` và dependency resolution; lỗi Docker cache thì xem `layers.idx` và `COPY` order.
4. **Chạy tool đúng chế độ:** `java -jar` cho runtime, `-Djarmode=tools` cho list/extract; IDE/bootRun không sử dụng packaged classpath index.
5. **Sửa build config rồi rebuild:** không edit raw JAR bytes thủ công.

## 17. Bài tập và đáp án

### Bài 1. Phân loại hai file

~~~text
File A:
- "BOOT-INF/lib/a.jar"
- "BOOT-INF/lib/b.jar"

File B:
- "dependencies":
  - "BOOT-INF/lib/a.jar"
  - "BOOT-INF/lib/b.jar"
- "application":
  - "BOOT-INF/classes/"
~~~

**Đáp án:** File A là `classpath.idx`; File B là `layers.idx`. Cả hai có tên JAR giống nhau nhưng mục đích khác.

### Bài 2. Thứ tự trong classpath so với layer

`classpath.idx` liệt kê `b.jar` trước `a.jar`; `layers.idx` đặt cả hai vào `dependencies`.

**Đáp án:** Runtime classpath order do `classpath.idx` mô tả, còn Dockerfile copy **layer dependencies** ở vị trí quy định bởi layer order. Không phải Docker tạo một layer cho `a.jar` rồi một layer cho `b.jar` nếu chúng cùng group.

### Bài 3. Chỉ đổi Java source

Khi sửa `LayerIndexApplication.outputMessage()`, layer nào có khả năng thay?

**Đáp án:** `application` vì `BOOT-INF/classes` thay. Những dependencies không đổi có khả năng reuse cache nếu các inputs khác ổn định.

### Bài 4. IDE không nhìn thấy classpath.idx

Run trực tiếp main class trong IntelliJ/Eclipse/VS Code. Nó có đọc packaged index không?

**Đáp án:** Không. IDE dùng module classpath khi chạy. Muốn test packaged behavior, chạy `java -jar` của artifact đã tạo.

### Bài 5. Chỉ COPY JAR

Dockerfile có `COPY target/app.jar app.jar` và JAR chứa `layers.idx`. Image đã tự chia `dependencies`/`application` chưa?

**Đáp án:** Chưa. Cần layer-aware extraction và `COPY` tương ứng hoặc buildpacks/image tooling khác.

### Bài 6. Dòng output Java

Ứng dụng ở mục 6 chạy thành công bằng `java -jar` sẽ in dòng nào do `ApplicationRunner`?

**Đáp án:** `LAYERS_OK Hello`, ngoài các dòng log khởi động khác của Spring Boot.

### Bài 7. Maven custom rule

Làm sao nhận diện local reactor modules, snapshot libraries và release libraries?

**Đáp án:** Dùng `includeModuleDependencies` ở rule `application`, rule `*:*:*SNAPSHOT` ở `snapshot-dependencies` và catch-all `dependencies`. `layerOrder` phải bao phủ toàn bộ layer names.

### Bài 8. Không có classpath.idx

JAR vẫn chạy nhưng thiếu index. Có phải chắc chắn là lỗi packaging?

**Đáp án:** Không. Classpath index là tùy chọn. Tuy nhiên nếu dự án yêu cầu deterministic runtime classpath ordering thì phải kiểm plugin behavior và artifact.

### Bài 9. Đổi tên layer

Team đổi `snapshot-dependencies` thành `internal-changing` nhưng Dockerfile vẫn copy đường dẫn cũ.

**Đáp án:** Lệnh `COPY` có thể fail hoặc image thiếu files. Phải đồng bộ layer names giữa custom configuration, extracted output và Dockerfile.

### Bài 10. Phiên bản dependency thay

Đổi commons-lang3 từ 3.17.0 sang release khác. Index nào có thể thay?

**Đáp án:** Cả `classpath.idx` (filename/path version thay) và `layers.idx` (entry cùng dependency thay). Layer `dependencies` mất cache là hợp lý; đó không tự nghĩa thứ tự loader hoặc code logic sai.

## 18. Checklist trước khi phát hành

- [ ] Artifact đúng là executable Boot JAR từ Maven `repackage` hoặc Gradle `bootJar`.
- [ ] `BOOT-INF/classes`, `BOOT-INF/lib` và Boot Loader được đóng gói đúng.
- [ ] `classpath.idx` (nếu có) có đúng nested JAR paths, không dùng để chữa dependency conflict.
- [ ] Biết `classpath.idx` chỉ áp dụng khi chạy packaged `java -jar`, không phải IDE/`spring-boot:run`/`bootRun`.
- [ ] `layers.idx` (nếu có) có đúng layer names và assigned archive paths.
- [ ] Hiểu default order dependencies → spring-boot-loader → snapshot-dependencies → application.
- [ ] Không nhầm layer order với classpath order, JVM classloader hoặc dependency resolution.
- [ ] Đã chạy `jarmode=tools list-layers` và kiểm extracted layout khi cần Docker layers.
- [ ] Dockerfile `COPY` từ từng extracted layer, có entrypoint phù hợp.
- [ ] Đã kiểm Maven/Gradle custom layer config, rule ordering và layerOrder.
- [ ] Không sửa tệp index/ZIP entries của JAR sản phẩm sau khi đóng gói.
- [ ] Không vô hiệu hóa jarmode tools khi pipeline còn cần tools mode.
- [ ] Đã smoke-test `java -jar` và image sẽ deploy, không chỉ IDE.
- [ ] Cache hiệu quả được đánh giá từ build logs/artifact hashes, không dựa vào số tên lớp.
- [ ] Không nhúng secrets vào app resources/container image và có quản trị dependencies/SBOM thích hợp.

## 19. Tài liệu chính thức

- Spring Boot 3.5 — Nested JARs, classpath index, layer index: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html
- Spring Boot 3.5 — Maven Packaging Executable Archives / Layered Jar or War: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — Efficient Container Images: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/efficient-images.html
- Spring Boot 3.5 — Dockerfiles, jarmode tools: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.5 — Cloud Native Buildpacks: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/cloud-native-buildpacks.html
- Spring Boot 3.5 — Gradle Dependency Management: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html
- Docker — Build cache optimization: https://docs.docker.com/build/cache/optimize/
- Open Container Initiative — Image Specification: https://github.com/opencontainers/image-spec

**Kết luận:** `classpath.idx` là **danh sách thứ tự các nested JAR được Boot Loader nạp khi chạy executable archive**; `layers.idx` là **bản đồ file/thư mục cho image tooling để tách những lớp cache Docker/OCI**. Hai chỉ mục cùng xuất hiện trong `BOOT-INF` nhưng không thay thế, không tự sinh hành vi của nhau. Muốn xác nhận một hệ thống cụ thể, hãy kiểm **đúng JAR được build**, đọc cả hai file, chạy `java -jar`, rồi quan sát `jarmode extraction` và các bước `COPY` của container pipeline.