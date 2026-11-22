# Kiểm soát thứ tự lớp và vị trí của thư viện nội bộ trong Spring Boot

## 1. Mục tiêu và kết quả cần đạt

Khi đóng gói ứng dụng Spring Boot thành executable JAR, các dependency được đưa vào archive để ứng dụng chạy độc lập. Nếu tạo container image bằng cách copy **nguyên JAR**, một thay đổi nhỏ trong mã ứng dụng cũng có thể khiến layer chứa JAR thay đổi. **Layered archives** giải quyết vấn đề tổ chức nội dung thành các lớp có tần suất thay đổi khác nhau, giúp công cụ xây image có cơ hội tái sử dụng cache tốt hơn.

Trong dự án đa mô-đun, câu hỏi khó không phải chỉ là “bật layers”, mà là:

- Thư viện nội bộ `core` đang được tiêu thụ bằng **Maven reactor module**, **Gradle project dependency** hay bằng **tọa độ GAV đã publish**?
- Khi thư viện core thay đổi, muốn phần nào của image bị invalidated?
- Cần phân biệt thư viện công ty dạng **release**, **SNAPSHOT** và module đang được build trong cùng repository như thế nào?
- Các **matcher** nào nhận đúng library vào layer mong muốn, và thứ tự **layerOrder** nào phù hợp với mục tiêu cache?
- Làm sao xác minh `BOOT-INF/layers.idx` của **JAR cuối cùng**, thay vì chỉ tin vào cấu hình XML/Groovy?
- Làm sao tạo image từ các layer và chạy được ứng dụng sau khi extract?

Bài học này thuộc nhóm **Đóng gói theo lớp** của Spring Boot Build Tooling Packaging. Ta sẽ dùng cùng một ứng dụng Java 17 trong cả Maven và Gradle, có module thư viện nội bộ `core` và module executable `app`. Sau khi xây xong, người học có thể kiểm tra chính xác **thứ tự layer và vị trí của core-1.0.0.jar**, chạy một Java verifier, rồi xây Docker image qua `jarmode=tools`.

**Bộ phiên bản minh họa:** Java 17, Spring Boot 3.3.5, Maven 3.9.x hoặc Gradle 8.5. Các phiên bản là lựa chọn cho bài thực hành, không đại diện cho phiên bản mới nhất. Cấu hình Spring Boot 3.3 được dùng thống nhất với câu lệnh `jarmode=tools`; phiên bản cũ hơn có thể dùng `layertools` và command khác.

## 2. Layer là gì, và không phải là gì?

Executable Spring Boot JAR giữ ứng dụng cùng dependency trong một archive. Ví dụ:

~~~text
app-1.0.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/app/LayeredApplication.class
    ├── lib/
    │   ├── core-1.0.0.jar
    │   ├── spring-boot-3.3.5.jar
    │   └── ...
    └── layers.idx
~~~

File **BOOT-INF/layers.idx** là metadata chỉ ra các đường dẫn của archive thuộc layer nào. Một đoạn minh họa (không phải toàn bộ nội dung thực tế):

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/spring-boot-3.3.5.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "internal-modules":
  - "BOOT-INF/lib/core-1.0.0.jar"
- "application":
  - "BOOT-INF/classes/"
~~~

Ở đây **internal-modules** là layer tùy chỉnh của bài; Spring Boot không tự sinh tên này trong mặc định.

Phải phân biệt ba vị trí:

1. **Vị trí vật lý trong JAR:** thư viện core vẫn nằm dưới `BOOT-INF/lib/core-1.0.0.jar` (trong executable JAR). Đổi layer không biến nó thành `BOOT-INF/internal-modules/core.jar`.
2. **Layer assignment trong layers.idx:** core-1.0.0.jar thuộc `internal-modules`, `application` hoặc layer khác theo rules.
3. **Thư mục sau khi extract với jarmode tools:** công cụ tạo các nhóm thư mục theo layer để Dockerfile COPY. Spring Boot 3.3 có layout extraction phục vụ khởi động nhanh và có thể tạo một JAR launcher mỏng cùng thư viện dưới các đường dẫn tối ưu; không đoán rằng đường dẫn tương đối sau extract giống y hệt `BOOT-INF/lib` trước extract.

**Layer trong bài không phải Java JPMS layer, Spring service/controller/repository layer hoặc thứ tự nạp Bean.** Layer order phục vụ **đóng gói và hiệu quả cache**; nó không thay dependency resolution, classpath precedence, transaction ordering hay application lifecycle.

### 2.1. Layering có thay đổi hành vi chạy không?

Với cấu hình hợp lệ, executable Boot JAR vẫn có thể chạy:

~~~bash
java -jar app-1.0.0.jar
~~~

Boot loader vẫn tìm application classes và runtime dependencies theo archive layout. Việc thêm/đổi **layers.idx** không phải cách sửa `ClassNotFoundException` do một library bị đóng gói sai. Hãy kiểm chứng riêng: **(1) core có mặt trên runtime classpath và (2) core được gán đúng layer**.

### 2.2. Vì sao Docker cache hưởng lợi?

Giả sử image có sáu lệnh COPY, từ ít thay đổi đến thường thay đổi:

~~~text
Layer 1: dependencies
Layer 2: spring-boot-loader
Layer 3: internal-releases
Layer 4: snapshot-dependencies
Layer 5: internal-modules
Layer 6: application
~~~

Nếu chỉ class ứng dụng đổi, các bước COPY của dependency libraries trước đó có cơ hội cache hit. Nếu core đổi, những layer trước `internal-modules` có thể giữ cache. Đây là lợi ích chính của layered build.

**Layering không tự làm tổng số byte dependency nhỏ đi.** Một image có nhiều layer hơn cũng có overhead. Có lợi hay không phải đo bằng image layers, cache hit rate, tốc độ rebuild/pull và đặc điểm thay đổi thực tế.

## 3. Bốn layer mặc định và thứ tự mặc định trong Spring Boot 3.3

Khi tạo layered executable JAR với Spring Boot Maven/Gradle Plugin 3.3, cấu hình mặc định chia như sau:

| Layer mặc định | Đối tượng điển hình | Lý do tách |
| --- | --- | --- |
| `dependencies` | Dependency release không chứa SNAPSHOT trong version | Thường thay đổi ít |
| `spring-boot-loader` | Spring Boot loader classes | Thay khi nâng loader/plugin |
| `snapshot-dependencies` | Dependency ngoài có version chứa SNAPSHOT | Thay đổi thường xuyên hơn |
| `application` | Application classes/resources và local module/project dependencies | Đổi theo mã nguồn của build |

**Thứ tự layer mặc định** được Spring Boot 3.3 mô tả:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Thứ tự này nhằm đặt phần ít đổi **trước**, phần hay đổi **sau** để hỗ trợ cache. Đây là chính sách mặc định, không bắt buộc mọi ứng dụng phải giữ nguyên.

### 3.1. Local Maven module và Gradle project dependency

Câu “thư viện nội bộ thuộc layer application mặc định” có một điều kiện quan trọng:

- **Maven:** Spring Boot phát hiện **module dependency thuộc reactor/current build**. Library chỉ resolve từ `~/.m2/repository`, không thuộc current reactor, có thể được coi như dependency thông thường.
- **Gradle:** Spring Boot phát hiện **project dependency** như `implementation project(':core')`. Nếu thay bằng tọa độ repository `implementation 'com.example:core:1.0.0'`, đó không còn mặc nhiên là một project dependency.

Đây là khác biệt giữa **nguồn gốc nghiệp vụ** (“do công ty tự viết”) và **cách resolver biểu diễn module** (“thuộc build hiện tại hay tải qua repository”). Không thể đoán layer từ prefix `com.example` khi chưa xem matcher và cách build đang resolve dependency.

### 3.2. Dependency SNAPSHOT có thể thuộc nhiều nhóm

Xét ba library:

~~~text
com.example:core:1.0.0                   # local module/project trong build hiện tại
com.example:company-utils:2.0.0          # đã publish
com.example:company-utils:2.1.0-SNAPSHOT # đã publish nhưng mutable
~~~

Theo layer mặc định, core local thường thuộc `application`; company-utils release thuộc `dependencies`; company-utils SNAPSHOT thuộc `snapshot-dependencies`. Nếu muốn nhóm internal library riêng, cần custom rules.

Một module core local có version **1.0.0-SNAPSHOT** sẽ chịu ảnh hưởng thứ tự matcher: muốn nó ở layer local riêng thì matcher local phải **nhận trước** matcher SNAPSHOT.

## 4. Thiết kế sáu layer cho dự án đa-mô-đun

Bài sẽ định nghĩa thêm hai layer:

- **internal-modules:** core và các library build từ module/project hiện tại.
- **internal-releases:** dependency công ty đã publish dưới group `com.example`, không bị một matcher trước đó nhận.

Kết quả mong muốn:

| Thư viện hoặc entry | Kiểu dependency | Layer mong muốn |
| --- | --- | --- |
| Commons Lang release | External release | `dependencies` |
| Spring Boot loader | Loader classes | `spring-boot-loader` |
| `com.example:company-utils:2.0.0` | Published internal release | `internal-releases` |
| `com.example:company-utils:2.1.0-SNAPSHOT` | Published SNAPSHOT | `snapshot-dependencies` |
| `com.example:core:1.0.0` | Maven reactor module / Gradle project | `internal-modules` |
| `LayeredApplication.class` và resources | App code | `application` |

**Thứ tự quyết định membership (matcher order):**

~~~text
1. Is local Maven module / Gradle project?  -> internal-modules
2. Has a SNAPSHOT version?                  -> snapshot-dependencies
3. Group matches com.example?              -> internal-releases
4. Everything else                         -> dependencies
~~~

**Thứ tự xuất layer (layerOrder):**

~~~text
dependencies
spring-boot-loader
internal-releases
snapshot-dependencies
internal-modules
application
~~~

Hai thứ tự **không giống nhau, và phải kiểm soát độc lập**. Matcher order được đánh giá **từ trên xuống**, mỗi entry đã được rule trước nhận sẽ không còn cho rule sau. `layerOrder` xác định thứ tự viết/trích xuất layer, phục vụ thứ tự các bước COPY trong Dockerfile.

### 4.1. Nếu đổi ưu tiên SNAPSHOT và internal group?

Giả sử có một dependency `com.example:company-utils:2.1.0-SNAPSHOT`: nó match cả **`*:*:*SNAPSHOT`** lẫn **`com.example:*`**. Theo thiết kế ở trên, nó vào **snapshot-dependencies** vì matcher SNAPSHOT đi trước group.

Nếu muốn tất cả thư viện công ty đã publish — kể cả SNAPSHOT — vào `internal-releases`, nên đổi tên layer thành `internal-published` cho chính xác, đặt group matcher trước SNAPSHOT và chấp nhận layer đó thay đổi thường xuyên hơn. Không có một thứ tự hoàn hảo cho mọi đội ngũ; phải thể hiện policy rồi viết kiểm thử.

### 4.2. Catch-all phải ở cuối

Một `into` hoặc `intoLayer` **không có matcher** nhận mọi entry chưa được rule trước claim. Nếu đặt catch-all đầu danh sách dependencies thì các rule sau không còn gì để nhận.

Sai mục tiêu:

~~~groovy
dependencies {
    intoLayer('dependencies')
    intoLayer('internal-modules') {
        includeProjectDependencies()
    }
}
~~~

Đây là **fragment lỗi**, không phải file Gradle hoàn chỉnh. Đúng là đặt internal-modules trước, catch-all dependencies cuối cùng.

## 5. Mã Java 17 dùng chung cho cả Maven và Gradle

Ta tạo hai module: một library nhỏ và một Spring Boot application phụ thuộc library đó.

### 5.1. Cấu trúc project

~~~text
layered-demo/
├── pom.xml                       # root nếu dùng Maven
├── settings.gradle               # root nếu dùng Gradle
├── core/
│   ├── pom.xml                   # Maven core
│   ├── build.gradle              # Gradle core
│   └── src/main/java/com/example/core/SkuFormatter.java
└── app/
    ├── pom.xml                   # Maven app
    ├── build.gradle              # Gradle app
    ├── src/layers.xml            # Maven custom layering
    └── src/main/java/com/example/app/LayeredApplication.java
~~~

**Chọn Maven hoặc Gradle** khi thực hành; các bộ file build là phương án thay thế. Toàn bộ Java source bên dưới dùng được với cả hai.

### 5.2. Module thư viện core

File `core/src/main/java/com/example/core/SkuFormatter.java`:

~~~java
package com.example.core;

import java.util.Locale;

public final class SkuFormatter {

    private SkuFormatter() {
    }

    public static String normalize(String input) {
        return "SKU-" + input.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

Đây là **một file Java 17 hoàn chỉnh**. `String.strip()` có từ Java 11; `Locale.ROOT` giúp quy tắc upper-case ổn định giữa các máy. Với input `" 42 "`, method trả về **SKU-42**.

Chúng ta **không áp Spring Boot Plugin lên core**. Core cần tạo library JAR có `com/example/core/SkuFormatter.class` ngay dưới package path chuẩn. Nếu core bị repackaged thành Boot executable archive (class dưới BOOT-INF/classes) thì nó không còn phù hợp làm dependency library thông thường.

### 5.3. Module ứng dụng app

File `app/src/main/java/com/example/app/LayeredApplication.java`:

~~~java
package com.example.app;

import com.example.core.SkuFormatter;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LayeredApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayeredApplication.class, args);
    }

    @Bean
    CommandLineRunner proof() {
        return args -> System.out.println(
                "LAYERING_OK:" + SkuFormatter.normalize(" 42 "));
    }
}
~~~

Đây cũng là **một file Java 17 hoàn chỉnh**. Ứng dụng sử dụng `spring-boot-starter` cơ bản, không cần server HTTP/database. Khi chạy đúng executable JAR, nó in dòng được xác định bởi chính mã nguồn:

~~~text
LAYERING_OK:SKU-42
~~~

Spring Boot còn có thể in banner và logs. Đoạn trên không phải toàn bộ terminal output.

## 6. Maven: root POM đa-mô-đun

Tạo file `layered-demo/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>layered-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
    </properties>
</project>
~~~

Root POM đồng thời làm **aggregator** qua `modules` và **parent** để các POM con kế thừa group/version. Nó không sinh executable JAR vì `packaging=pom`.

### 6.1. core/pom.xml hoàn chỉnh

File `layered-demo/core/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>layered-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>
</project>
~~~

Core tạo plain library JAR với tọa độ `com.example:core:1.0.0`. Nó **không** áp dụng `spring-boot-maven-plugin`. Module này được nhận diện là local module khi có mặt trong **reactor đang chạy**.

### 6.2. app/pom.xml hoàn chỉnh

File `layered-demo/app/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>layered-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                        <configuration>${project.basedir}/src/layers.xml</configuration>
                    </layers>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Điểm trọng tâm:**

- Spring Boot Maven Plugin được khai báo **chỉ tại app** để chạy goal `repackage`.
- Khi dùng `spring-boot-starter-parent`, execution repackage đã được quản lý trong cấu hình kế thừa; không tự khai báo một execution trùng lặp.
- `layers.enabled=true` giữ metadata layer trong executable JAR.
- `layers.configuration` trỏ tới file XML thực sự ở `app/src/layers.xml`, được plugin đọc lúc build.
- Dependency `core` phải xuất hiện trong runtime graph; bỏ dependency để ép core ra khỏi layer nào đó sẽ làm ứng dụng lỗi.
- Artifact Boot JAR mặc định có tên `app-1.0.0.jar` dưới `app/target/`.

### 6.3. app/src/layers.xml đầy đủ và có thứ tự rõ ràng

Tạo file `layered-demo/app/src/layers.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<layers xmlns="http://www.springframework.org/schema/boot/layers"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.springframework.org/schema/boot/layers
                            https://www.springframework.org/schema/boot/layers/layers-3.3.xsd">

    <application>
        <into layer="spring-boot-loader">
            <include>org/springframework/boot/loader/**</include>
        </into>
        <into layer="application" />
    </application>

    <dependencies>
        <into layer="internal-modules">
            <includeModuleDependencies />
        </into>
        <into layer="snapshot-dependencies">
            <include>*:*:*SNAPSHOT</include>
        </into>
        <into layer="internal-releases">
            <include>com.example:*</include>
        </into>
        <into layer="dependencies" />
    </dependencies>

    <layerOrder>
        <layer>dependencies</layer>
        <layer>spring-boot-loader</layer>
        <layer>internal-releases</layer>
        <layer>snapshot-dependencies</layer>
        <layer>internal-modules</layer>
        <layer>application</layer>
    </layerOrder>
</layers>
~~~

**Đây là file layers.xml hoàn chỉnh**, sử dụng schema 3.3 của Spring Boot và thứ tự layer tùy chỉnh. Phân tích:

- `application`: matcher `org/springframework/boot/loader/**` nhận loader classes; catch-all kế tiếp nhận class/resource còn lại của app.
- `dependencies` thứ nhất: `includeModuleDependencies` nhận **module dependencies thuộc current Maven build** vào **internal-modules**.
- `dependencies` thứ hai: `*:*:*SNAPSHOT` nhận external snapshots còn lại.
- `dependencies` thứ ba: `com.example:*` nhận dependencies đã publish thuộc nhóm nội bộ và chưa bị hai rule trước nhận.
- `dependencies` cuối cùng: bắt tất cả phần còn lại vào **dependencies**.
- `layerOrder` liệt kê đủ sáu layer. **Không nhầm** thứ tự đó với thứ tự `into` phía trên.

Với ví dụ chỉ có core và Spring Boot starter, có thể **chưa có thư viện nào trong internal-releases hoặc snapshot-dependencies**; đây không phải lỗi. Rule tồn tại để đáp ứng tương lai nếu dự án thêm những dependency phù hợp.

### 6.4. Maven build từ reactor root

Tại thư mục `layered-demo/`, chạy:

~~~bash
mvn -pl app -am clean package
~~~

Nếu repository có Maven Wrapper:

~~~bash
./mvnw -pl app -am clean package
~~~

`-pl app` chỉ định module cần build, `-am` xây các reactor modules mà app phụ thuộc, gồm core. **Chính việc core thuộc reactor hiện tại** giúp `includeModuleDependencies` nhận nó là local module. Nếu chạy app riêng lẻ sau khi core chỉ được install vào local Maven repository, kết quả matcher có thể khác.

Sau khi build thành công:

~~~text
app/target/app-1.0.0.jar
~~~

Chạy ứng dụng:

~~~bash
java -jar app/target/app-1.0.0.jar
~~~

Dòng stdout do app in:

~~~text
LAYERING_OK:SKU-42
~~~

Nếu lệnh Maven chạy bằng `mvn`, máy phải cài Maven phù hợp. Trên Windows dùng `mvnw.cmd` thay `./mvnw` khi dùng wrapper. Wrapper không tự xuất hiện chỉ từ việc tạo POM.

## 7. Gradle multi-project: settings.gradle và java-library core

Với Gradle, thay các POM và layers.xml bằng các file Groovy DSL sau.

### 7.1. Root settings.gradle

~~~groovy
rootProject.name = 'layered-demo'
include 'core', 'app'
~~~

Đây là một file settings.gradle hoàn chỉnh. Nó đưa **:core** và **:app** vào cùng Gradle build. Không cần áp dụng Spring Boot Plugin cho root.

### 7.2. core/build.gradle

~~~groovy
plugins {
    id 'java-library'
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
~~~

Đây là file Gradle hoàn chỉnh cho core. Java Library Plugin tạo `jar` thuần, class library nằm tại đường dẫn classpath thông thường. Core không cần Spring Boot plugin hay `bootJar`.

### 7.3. app/build.gradle hoàn chỉnh

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter'
}

tasks.named('bootJar') {
    layered {
        application {
            intoLayer('spring-boot-loader') {
                include 'org/springframework/boot/loader/**'
            }
            intoLayer('application')
        }

        dependencies {
            intoLayer('internal-modules') {
                includeProjectDependencies()
            }
            intoLayer('snapshot-dependencies') {
                include '*:*:*SNAPSHOT'
            }
            intoLayer('internal-releases') {
                include 'com.example:*'
            }
            intoLayer('dependencies')
        }

        layerOrder = [
            'dependencies',
            'spring-boot-loader',
            'internal-releases',
            'snapshot-dependencies',
            'internal-modules',
            'application'
        ]
    }
}
~~~

**Các điểm cần nhớ về Gradle:**

1. `implementation project(':core')` là dependency thuộc build hiện tại, không phải `com.example:core:1.0.0` tải từ Maven repository.
2. `tasks.named('bootJar')` cấu hình **executable Spring Boot JAR**; chỉ chỉnh `tasks.named('jar')` sẽ không kiểm soát đầy đủ output cần triển khai.
3. `includeProjectDependencies()` nhận core trước khi các matcher SNAPSHOT và `com.example:*` chạy.
4. `include 'com.example:*'` là dependency coordinate pattern trong phần `dependencies`; nó **không phải** glob tên file.
5. `include 'org/springframework/boot/loader/**'` nằm trong phần `application`, dùng path matching để nhận loader classes.
6. `layerOrder` liệt kê đủ những layer được các rule tạo ra.
7. Các source classes và dependency library **không bị di chuyển khỏi BOOT-INF** trong executable JAR chỉ vì đặt tên layer.
8. `java.toolchain` yêu cầu toolchain Java 17; Gradle runtime cũng phải tương thích với Spring Boot Gradle Plugin và Gradle version.

### 7.4. Chạy Gradle build

Từ root `layered-demo/`, khi có Gradle Wrapper phù hợp:

~~~bash
./gradlew :app:clean :app:bootJar
~~~

Hoặc nếu muốn chạy lifecycle kiểm thử:

~~~bash
./gradlew clean build
~~~

File executable dự kiến:

~~~text
app/build/libs/app-1.0.0.jar
~~~

Chạy:

~~~bash
java -jar app/build/libs/app-1.0.0.jar
~~~

Dòng stdout từ ứng dụng:

~~~text
LAYERING_OK:SKU-42
~~~

Bản Gradle có thể tạo thêm `app-1.0.0-plain.jar` khi chạy `build`. **Không dùng plain JAR** để thử `jarmode=tools` hoặc kiểm tra Spring Boot layer index.

## 8. Tách local project khỏi published internal library

Một library do tổ chức tự viết có thể được app tiêu thụ theo hai cách.

**Cách A: project dependency (local build)**

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

**Cách B: published dependency**

~~~groovy
dependencies {
    implementation 'com.example:core:1.0.0'
}
~~~

Đây là **hai fragment thay thế** cho nhau; không khai báo cả hai chỉ để giải thích layered packaging. Cách B cần `repositories` có thể resolve được tọa độ đó.

Với **Cách A**, matcher `includeProjectDependencies()` nhận core vào `internal-modules`.

Với **Cách B**, `includeProjectDependencies()` không tự nhận core nữa. Nếu version là 1.0.0 và matcher `com.example:*` được áp dụng sau SNAPSHOT rule, core vào `internal-releases`. Nếu version chứa SNAPSHOT, nó có thể vào `snapshot-dependencies`. Nếu không có matcher nhóm công ty, nó có thể vào `dependencies` như một external release.

Maven có tình huống tương tự:

- `mvn -pl app -am ...` từ reactor root: core thuộc modules của build và được matcher `includeModuleDependencies` nhận.
- `mvn -f app/pom.xml ...` khi core chỉ được resolve qua local/remote repository: core có thể bị xem là dependency thường. Nó có thể vào internal-releases nhờ matcher nhóm `com.example:*`.

**Một tên `core-1.0.0.jar` xuất hiện giống nhau không chứng minh hai bản build có layer assignment giống nhau.** Kiểm tra `layers.idx` của artifact cuối cùng từ chính build command đang dùng.

### 8.1. Composite build và substitutions

Gradle included/composite builds có cơ chế dependency substitution, vì vậy resolved component có thể là project component thay vì external module. Nếu app dùng composite build, đừng đoán layer membership từ dòng `implementation 'com.example:core:1.0.0'` duy nhất. Hãy xem resolved dependency graph và `layers.idx` thực tế.

### 8.2. Nội bộ không luôn đồng nghĩa ổn định

Một thư viện công ty có version release cố định và rất ít thay đổi có thể được đặt sớm để cache. Nhưng một thư viện nội bộ thường xuyên được publish **SNAPSHOT** cần policy khác. `internal-releases` trong bài đại diện cho **thư viện release có version được kiểm soát**, không bảo đảm mọi artifact với group `com.example` đều immutable. Hãy dùng repository release immutable và dependency locking/verification khi cần.

## 9. Kiểm tra JAR và đọc BOOT-INF/layers.idx

**Bước quan trọng nhất của QA** là đọc output thực tế.

Maven:

~~~bash
jar tf app/target/app-1.0.0.jar
~~~

Gradle:

~~~bash
jar tf app/build/libs/app-1.0.0.jar
~~~

Trong danh sách entry phải có ít nhất những đường dẫn phù hợp:

~~~text
BOOT-INF/layers.idx
BOOT-INF/lib/core-1.0.0.jar
BOOT-INF/classes/com/example/app/LayeredApplication.class
~~~

Có nhiều JAR và resource khác. Sự hiện diện của `BOOT-INF/layers.idx` chưa chứng minh core đã ở layer mong muốn.

Nếu hệ thống có `unzip`, đọc trực tiếp nội dung entry:

~~~bash
unzip -p app/target/app-1.0.0.jar BOOT-INF/layers.idx
~~~

Hoặc với Gradle:

~~~bash
unzip -p app/build/libs/app-1.0.0.jar BOOT-INF/layers.idx
~~~

Hãy nhìn `internal-modules` chứa **BOOT-INF/lib/core-1.0.0.jar**. Với ví dụ chỉ dùng một core và Spring Boot starter, `internal-releases` có thể rỗng. Điều này **không phải fail**: không được giả định archive chứa một dependency công ty đã publish khi POM/Gradle build chưa khai báo nó.

### 9.1. Hai loại kiểm tra độc lập

Để đạt kết quả đúng cần cả hai:

1. **Runtime membership:** `jar tf` cho thấy core-1.0.0.jar thực sự nằm dưới BOOT-INF/lib.
2. **Layer membership:** `layers.idx` gán đường dẫn đó vào **internal-modules**, không chỉ có một header layer trùng tên.

Nếu core thiếu vật lý, sửa dependency declarations/runtimeClasspath. Nếu core có mặt nhưng layer sai, sửa **matchers**, **thứ tự matcher** hoặc loại resolution (local project vs repository).

### 9.2. Đừng đọc layers.idx của JAR sai

Khi Gradle tạo cả app-1.0.0.jar và app-1.0.0-plain.jar, hãy chọn đúng **bootJar**. Với Maven, bản JAR gốc trước repackage có thể được lưu với đuôi **.original**; không kiểm tra file đó như executable artifact. Một pipeline dùng glob **build/libs/*.jar** hoặc **target/*.jar** có thể chọn nhầm khi output chứa nhiều file.

## 10. Spring Boot 3.3 tools mode và extraction

Spring Boot 3.3 tích hợp **spring-boot-jarmode-tools** khi layered JAR được xây theo cấu hình mặc định. Tools mode hỗ trợ liệt kê layer và extract thành cấu trúc thuận tiện cho container image.

### 10.1. Liệt kê layer

Maven:

~~~bash
java -Djarmode=tools -jar app/target/app-1.0.0.jar list-layers
~~~

Gradle:

~~~bash
java -Djarmode=tools -jar app/build/libs/app-1.0.0.jar list-layers
~~~

Output thực tế tùy file archive. Danh sách các layer được ghi theo cấu hình và có thể bị ảnh hưởng bởi việc layer không có nội dung. **Đọc thêm layers.idx để xác nhận core membership**; chỉ gọi list-layers không đủ.

### 10.2. Extract theo layer

Maven:

~~~bash
java -Djarmode=tools -jar app/target/app-1.0.0.jar extract --layers --destination extracted
~~~

Gradle:

~~~bash
java -Djarmode=tools -jar app/build/libs/app-1.0.0.jar extract --layers --destination extracted
~~~

Các lệnh này tạo thư mục `extracted` để dùng trong container build. Trong Spring Boot 3.3, tools mode được thiết kế để có thể tạo **launcher JAR nhỏ `application.jar`** tham chiếu đến dependencies được extract, cùng các thư mục layer. Không tự giả định cấu trúc nội bộ của `extracted/internal-modules` giống đường dẫn `BOOT-INF/lib` trước extract; hãy xem output thực tế, nhất là khi nâng version.

**Về phiên bản:** Tài liệu cũ dùng `-Djarmode=layertools` với cú pháp khác; ví dụ này dành cho Spring Boot 3.3 nên dùng `-Djarmode=tools`, `list-layers` và `extract --layers`.

**Giới hạn:** Tools mode không dùng được với archive dạng **fully executable** có launch script ở đầu. Nếu plugin cấu hình `includeTools=false` hoặc Gradle `includeTools=false`, tools mode cũng không có mặt theo mặc định. Khi đó cần đổi cấu hình packaging hoặc dùng cách extract khác.

### 10.3. An toàn về thư mục output

Chạy extract trong một thư mục/CI workspace thích hợp; đừng để nó ghi đè những thư mục quan trọng của project. Khi build lại trong cùng nơi, xóa **chính thư mục `extracted` mà job vừa tạo** bằng công cụ phù hợp, không dùng lệnh xóa đệ quy trên một đường dẫn được tính không kiểm chứng.

## 11. Java 17 verifier kiểm tra layer order và core membership

Để CI không chỉ đọc thủ công, dùng một chương trình Java 17 độc lập. Chương trình mở file executable JAR bằng **JarFile**, lấy `BOOT-INF/layers.idx`, đọc các mục layer theo định dạng do Spring Boot 3.3 sinh, kiểm tra tên/thứ tự và xác nhận `core-1.0.0.jar` thuộc **internal-modules**.

Tạo file `LayerIndexVerifier.java` ở **root layered-demo**, không đưa vào source chính của app hoặc core.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.jar.JarFile;
import java.util.zip.ZipEntry;

public class LayerIndexVerifier {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java LayerIndexVerifier.java <app-jar>");
        }

        List<String> expectedOrder = List.of(
                "dependencies",
                "spring-boot-loader",
                "internal-releases",
                "snapshot-dependencies",
                "internal-modules",
                "application");

        try (JarFile jar = new JarFile(args[0])) {
            ZipEntry entry = jar.getEntry("BOOT-INF/layers.idx");
            if (entry == null) {
                throw new IllegalStateException("Missing layers.idx");
            }

            String content = new String(
                    jar.getInputStream(entry).readAllBytes(),
                    StandardCharsets.UTF_8);

            Map<String, List<String>> layers =
                    new LinkedHashMap<>();
            String currentLayer = null;

            for (String line : content.split("\\R")) {
                if (line.startsWith("- \"")
                        && line.endsWith("\":")) {
                    currentLayer =
                            line.substring(3, line.length() - 2);
                    if (layers.putIfAbsent(
                            currentLayer, new ArrayList<>()) != null) {
                        throw new IllegalStateException(
                                "Duplicate layer: " + currentLayer);
                    }
                } else if (line.startsWith("  - \"")
                        && line.endsWith("\"")) {
                    if (currentLayer == null) {
                        throw new IllegalStateException(
                                "Entry without layer");
                    }
                    layers.get(currentLayer).add(
                            line.substring(5, line.length() - 1));
                }
            }

            int previous = -1;
            for (String layerName : layers.keySet()) {
                int index = expectedOrder.indexOf(layerName);
                if (index < 0 || index <= previous) {
                    throw new IllegalStateException(
                            "Unexpected order: " + layerName);
                }
                previous = index;
            }

            if (!layers.containsKey("internal-modules")
                    || !layers.containsKey("application")) {
                throw new IllegalStateException(
                        "Missing required custom layers");
            }

            String corePath = "BOOT-INF/lib/core-1.0.0.jar";
            if (!layers.get("internal-modules")
                    .contains(corePath)) {
                throw new IllegalStateException(
                        "core not assigned to internal-modules");
            }

            if (jar.getEntry(corePath) == null) {
                throw new IllegalStateException(
                        "core JAR missing from BOOT-INF/lib");
            }

            String appClass =
                    "BOOT-INF/classes/com/example/app/"
                    + "LayeredApplication.class";
            if (jar.getEntry(appClass) == null) {
                throw new IllegalStateException(
                        "Application class missing");
            }
        }

        System.out.println("LAYER_INDEX_OK");
    }
}
~~~

Đây là **file Java 17 hoàn chỉnh**, sử dụng các API chuẩn và **Java source-file launcher**. Nó không phụ thuộc một YAML parser bên ngoài; vì vậy nó chỉ xử lý đúng định dạng `layers.idx` mà Spring Boot sinh trong ví dụ, **không phải YAML parser tổng quát**.

**Điểm kiểm chứng:**

- Có `BOOT-INF/layers.idx`.
- Thứ tự những layer hiện diện phù hợp với `expectedOrder`.
- Có `internal-modules` và `application`.
- `internal-modules` chứa chính xác **BOOT-INF/lib/core-1.0.0.jar**.
- Archive thực sự có JAR core ở đường dẫn đó.
- Archive thực sự có application main class.

**Không yêu cầu `internal-releases` phải chứa dependency**, vì ví dụ chưa khai báo library công ty đã publish. Nếu thay version của core hoặc base name, cần cập nhật tên `core-1.0.0.jar` trong verifier cho khớp artifact được build. Trong môi trường production có thể tham số hóa tên group/module/version.

### 11.1. Chạy với Maven

~~~bash
mvn -pl app -am clean package
java LayerIndexVerifier.java app/target/app-1.0.0.jar
~~~

### 11.2. Chạy với Gradle

~~~bash
./gradlew :app:bootJar
java LayerIndexVerifier.java app/build/libs/app-1.0.0.jar
~~~

Khi mọi điều kiện pass, chương trình chỉ in:

~~~text
LAYER_INDEX_OK
~~~

Nếu có lỗi, nó ném `IllegalStateException` hoặc exception tương ứng, và trả exit code khác 0. Không đánh dấu PASS khi chỉ kiểm tra code compile mà chưa đọc archive cuối.

### 11.3. Kiểm tra runtime riêng

Sau verifier, chạy:

~~~bash
java -jar app/target/app-1.0.0.jar
~~~

hoặc bản Gradle:

~~~bash
java -jar app/build/libs/app-1.0.0.jar
~~~

Dòng nghiệp vụ dự kiến:

~~~text
LAYERING_OK:SKU-42
~~~

**LAYER_INDEX_OK và LAYERING_OK:SKU-42 là hai kiểm tra khác nhau.** Một archive có layer metadata hợp lệ nhưng thiếu runtime dependency khác vẫn có thể khởi động lỗi; ngược lại, app có thể chạy mà layer index sai chính sách.

## 12. Dockerfile nhiều tầng: copy các layer theo thứ tự cache

Đặt `Dockerfile` tại root `layered-demo/`. Ví dụ này sử dụng **artifact do Maven tạo**. Đầu vào phải là file **app/target/app-1.0.0.jar** đã xây thành công. Spring Boot 3.3 `jarmode=tools extract --layers` tạo các thư mục layer cùng **application.jar** tối ưu để chạy từ extracted layout.

~~~dockerfile
FROM eclipse-temurin:17-jre AS extract
WORKDIR /workspace

COPY app/target/app-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract \
        --layers --destination extracted

# Cho phép COPY những layer tùy chọn chưa có dependency.
RUN mkdir -p extracted/internal-releases \
             extracted/snapshot-dependencies

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extract /workspace/extracted/dependencies/ ./
COPY --from=extract /workspace/extracted/spring-boot-loader/ ./
COPY --from=extract /workspace/extracted/internal-releases/ ./
COPY --from=extract /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extract /workspace/extracted/internal-modules/ ./
COPY --from=extract /workspace/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**Đây là Dockerfile minh họa theo layout tools mode Spring Boot 3.3.** Vì `COPY --from=extract` từ từng extracted layer, final stage có thể reuse cache của các layer ổn định; `application.jar` là JAR launcher được tạo trong extracted layout, **không phải toàn bộ uber JAR đã copy ở builder stage**.

Cách chạy:

~~~bash
mvn -pl app -am clean package
docker build -t layered-demo:1.0.0 .
docker run --rm layered-demo:1.0.0
~~~

Dòng output từ app trong container:

~~~text
LAYERING_OK:SKU-42
~~~

**Nếu chọn Gradle:** trong Dockerfile thay dòng COPY đầu thành:

~~~dockerfile
COPY app/build/libs/app-1.0.0.jar application.jar
~~~

Đây là **fragment thay thế một dòng**, không thêm cả hai vào cùng Dockerfile. Build Gradle trước bằng `./gradlew :app:bootJar`.

**Các điều kiện để Dockerfile chạy được:**

- Artifact đúng là Spring Boot 3.3 executable JAR có tools mode; không phải Gradle `-plain.jar`.
- Builder đã tải được runtime image và JDK/JRE phù hợp.
- `extract --layers` đã tạo launcher và các nhóm thư mục mà COPY tham chiếu.
- Layer `internal-modules` thực sự có nội dung do core được nhận.
- Tất cả runtime dependencies được copy đủ; khi mở rộng layer names phải cập nhật Dockerfile.
- Không bật fully executable launch script; tools mode không hỗ trợ trường hợp đó.
- CI/pipeline có `docker` và quyền build/run image tương ứng.

**Lưu ý Dockerfile COPY dùng thư mục đã extract, không dùng trực tiếp đường dẫn `BOOT-INF/lib/core-1.0.0.jar` trong JAR ban đầu.** Các tools extraction layouts có thể thay đổi theo Boot version; khi nâng version, đọc tài liệu version mới và kiểm tra nội dung `extracted/`.

### 12.1. Vì sao COPY order cần giống layerOrder?

Tại JAR, `layerOrder` quyết định thứ tự viết các lớp. Tại Dockerfile, **các lệnh COPY quyết định thứ tự image filesystem layers**. Để tối ưu cache theo policy dự kiến, ta duy trì cùng thứ tự:

~~~text
dependencies → spring-boot-loader → internal-releases
             → snapshot-dependencies → internal-modules
             → application
~~~

Nếu core đổi, các lệnh COPY phía trước internal-modules có thể được reuse. Nếu app đổi, ưu tiên chỉ những lớp cuối. Tuy nhiên, Docker cache còn phụ thuộc build context, base image digest, Dockerfile và build engine. **Không cam kết tỷ lệ cache hit cụ thể khi chưa đo**.

### 12.2. Layer rỗng và Docker COPY

Trong ví dụ chỉ có core và Boot starter, `internal-releases`/ `snapshot-dependencies` có thể chưa có entries. Dockerfile tạo hai thư mục rỗng ở builder để câu lệnh COPY không lỗi vì source path chưa tồn tại. **Đó là thao tác ở Docker build stage**, không làm thay đổi manifest/layers.idx của JAR và không tạo dependency mới.

Nếu một custom layer khác hoàn toàn trống và chưa tồn tại trong extracted output, cần xử lý tương tự hoặc dùng Dockerfile điều kiện phù hợp, thay vì copy path không tồn tại.

### 12.3. Docker image và Buildpacks không cùng chiến lược

Spring Boot còn có `spring-boot:build-image` (Maven) và `bootBuildImage` (Gradle), dùng Cloud Native Buildpacks. Buildpacks có cơ chế phân tách và cache riêng. **Không mặc định** rằng Dockerfile sáu COPY ở bài sẽ được Buildpacks áp dụng y hệt. Khi cần tối ưu Buildpacks image, kiểm tra layer metadata/image output thực tế của builder.

## 13. Đo hiệu quả của thiết kế layer

Một thử nghiệm thực tế có thể làm theo ba phiên bản Git:

**A — Không đổi code:** build lại từ cùng nguồn, cùng dependency versions, cùng toolchain. Nếu artifact bytes ổn định, những layer đã copy có cơ hội cache hit.

**B — Chỉ đổi app:** sửa thông báo trong LayeredApplication nhưng không đổi SkuFormatter hoặc dependency graph. Kỳ vọng layer application đổi; dependencies, loader và internal-modules có thể giữ nguyên nếu artifacts reproducible.

**C — Chỉ đổi core:** thay logic SkuFormatter nhưng giữ app và external libraries. Kỳ vọng internal-modules đổi; dependencies và loader có thể được reuse. Các Docker steps **sau** internal-modules có thể bị ảnh hưởng bởi chain cache, dù byte application class chưa thay đổi.

Đo bằng build logs (cache hit/miss), Docker history, image layer digests, build duration và remote cache behavior. Không chỉ nhìn file `layers.idx` rồi kết luận image pull nhanh hơn.

### 13.1. Layering và reproducible builds bổ trợ nhau

Nếu `core-1.0.0.jar` thay ZIP timestamps mỗi lần build dù không đổi source, layer internal-modules vẫn có thể mất cache. Cần pin toolchain/dependencies và cấu hình reproducible archives khi thực sự cần stable bytes.

**Đúng layer != cùng byte != cache hit.** Ba mệnh đề này phải được kiểm tra riêng.

### 13.2. Không tạo quá nhiều layer nhỏ

Một layer cho mỗi library có thể không có lợi: metadata overhead, số lệnh COPY và complexity tăng. Gộp những dependencies có cùng tần suất đổi là giải pháp cân bằng. Bốn layer mặc định của Spring Boot đã hợp lý cho nhiều ứng dụng nhỏ; chỉ thêm internal-modules/internal-releases khi có bài toán caching thật.

## 14. Những trường hợp nâng cao cần cân nhắc

### 14.1. Library nội bộ ở nhiều groupId

Nếu doanh nghiệp dùng `com.example` và `io.example.platform`, pattern `com.example:*` không match nhóm thứ hai. Có thể thêm một matcher/intoLayer riêng hoặc đưa cả hai pattern vào cùng layer theo chính sách. Phải kiểm tra **dependency coordinates thực tế**, không dùng filename substring.

### 14.2. Module internal SNAPSHOT

Local core phiên bản `1.0.0-SNAPSHOT` nên vẫn vào `internal-modules` nếu matcher module/project đứng trước matcher SNAPSHOT. Nếu đổi thứ tự ưu tiên, membership có thể thay. Viết regression test khi team thay Maven/Gradle scripts.

### 14.3. Multi-project lớn hoặc composite build

Nếu core là library dùng cho nhiều app, group theo module có tần suất đổi. Composite build và dependency substitution có thể làm một external coordinate resolve thành project component. Cần kiểm tra resolved dependency type và archive thực tế trước khi nói chắc nó thuộc layer nào.

### 14.4. Thư viện đã publish nhưng vừa đổi version

Nếu app đổi `company-utils` từ 2.0.0 sang 2.1.0, layer `internal-releases` thay; dependencies/loader trước đó có thể reuse. Đừng cố giữ cùng filename JAR cũ nhưng đổi bytes: immutable artifact coordinates và cache policy cần nhất quán.

### 14.5. Spring Boot plugin gắn nhầm vào core

Nếu module thư viện được đóng gói thành executable Boot JAR, lớp Java của core có thể không ở classpath root. Layer matching không chữa được vấn đề này. Xử lý đúng là **plain java-library/standard JAR cho core** và **bootJar/repackage cho app**.

### 14.6. Dependency cần ở runtime nhưng bị loại

Không dùng exclusions hoặc `compileOnly` để “đẩy một library khỏi layer”. Một thư viện runtime bị thiếu có thể làm app hỏng. Chỉ thay **layer assignment**, giữ dependency graph đúng.

## 15. Danh sách lỗi phổ biến và cách xử lý

**1. Catch-all đứng trước matcher cụ thể.** Matcher đầu đã nhận mọi dependency. Đặt catch-all cuối cùng và đọc lại layers.idx.

**2. Nhầm matching order với layerOrder.** Matcher quyết định membership; layerOrder quyết định thứ tự viết. Chỉnh đúng phần muốn thay đổi.

**3. Library nội bộ đã publish bị coi là local module.** Nó không thuộc current reactor/project build. Dùng matcher theo GAV và xác định resolver context.

**4. Maven build app đơn lẻ nhưng kỳ vọng core vào internal-modules.** `-f app/pom.xml` có thể resolve core từ local repo; dùng `-pl app -am` ở root hoặc chấp nhận policy published internal.

**5. Gradle dùng tọa độ com.example:core:1.0.0 mà kỳ vọng includeProjectDependencies nhận.** Tọa độ external không phải project(':core'). Sửa dependency hoặc matcher.

**6. Local module SNAPSHOT bị matcher SNAPSHOT nhận trước.** Đổi thứ tự claim nếu chính sách cần tách local modules.

**7. Matcher group quá rộng.** Pattern như `*:* ` hoặc một catch-all sớm có thể hút toàn bộ dependencies. Dùng group cụ thể và kiểm tra từng artifact.

**8. Dùng path pattern trong dependencies matcher.** `BOOT-INF/lib/core*.jar` không phải GAV pattern của phần dependencies. Dùng `com.example:*` hoặc module/project matcher.

**9. Dùng GAV pattern trong application matcher.** Application section dùng Ant-style paths. Loader matcher phải như `org/springframework/boot/loader/**`.

**10. Thiếu layerOrder hoặc ghi tên layer sai.** Cấu hình custom cần liệt kê đầy đủ các layer. Kiểm tra spelling/case.

**11. Chỉ cấu hình Gradle jar.** Executable được tạo bằng bootJar; hãy đặt layered DSL trên đúng task.

**12. Maven không chạy repackage.** Có thể tạo plain JAR thiếu index. Kiểm tra Boot Maven Plugin và execution của Spring Boot parent.

**13. Đường dẫn XML hoặc namespace schema sai.** Đặt `app/src/layers.xml` và dùng schema `layers-3.3.xsd` của Boot 3.3.

**14. Không thấy BOOT-INF/layers.idx.** Kiểm tra đã chọn đúng executable JAR, layers có bật không và plugin có chạy không.

**15. Core không có trong BOOT-INF/lib.** Sửa Maven/Gradle dependency graph trước; layering không tự đưa một library chưa khai báo vào runtime.

**16. Đọc layers.idx thấy internal-modules nhưng không thấy core.** Layer name tồn tại không đồng nghĩa mọi library đã được claim đúng. Dùng verifier/membership check.

**17. Dùng layertools cũ cho Boot 3.3.** Boot 3.3 hỗ trợ tools mode với `list-layers` và `extract --layers`. Đồng bộ cú pháp với version.

**18. Tools mode không chạy trên fully executable archive.** Không prepend launch script khi cần tools extraction; kiểm tra includeTools và build plugin.

**19. Chỉ kiểm tra file app-1.0.0-plain.jar.** Plain JAR không phải artifact Boot đang triển khai. Chọn app-1.0.0.jar.

**20. Dockerfile chỉ COPY vài layer.** Bỏ sót internal-modules làm thiếu core runtime. COPY đầy đủ và smoke test container.

**21. Dockerfile COPY theo thứ tự khác policy.** Không tận dụng tốt cache. Đồng bộ với layerOrder.

**22. Dockerfile dùng command launcher của phiên bản khác.** Spring Boot 3.3 tools extraction tạo launcher phù hợp với `java -jar application.jar`; xác minh bằng image smoke test khi nâng version.

**23. Giả định extracted/internal-modules có BOOT-INF/lib y như JAR gốc.** Extraction layout khác; quan sát kết quả thực và dùng toàn bộ thư mục layer trong Docker COPY.

**24. Quy tắc internal-releases không nhận group mới.** Cập nhật patterns khi thư viện công ty có groupId khác.

**25. Dùng SNAPSHOT mutable nhưng mong cache ổn định.** Pin và quản lý artifact versions/checksums phù hợp với release policy.

**26. Tưởng layers.idx đổi Java classpath priority.** Đây là metadata cho layer packaging; dependency conflicts phải xử lý ở build graph.

**27. Nhiều layer được tạo nhưng image không nhỏ đi.** Layering tối ưu cache/reuse, không tự giảm code/dependencies. Đo size và cache riêng.

**28. CI chỉ check build success.** Cần kiểm tra index, core membership và chạy JAR/container thật.

**29. Tạo core thành executable Boot JAR.** Plain library mới phù hợp khi app cần import class core.

**30. Đo cache ở hai lần build dùng toolchain/dependencies khác nhau.** Khác input nên số liệu không phản ánh chính sách layer; chuẩn hóa trước khi so.

## 16. Quy trình QA để đưa vào CI

### Maven

~~~bash
mvn -pl app -am clean package
java LayerIndexVerifier.java app/target/app-1.0.0.jar
java -jar app/target/app-1.0.0.jar
java -Djarmode=tools -jar app/target/app-1.0.0.jar list-layers
~~~

### Gradle

~~~bash
./gradlew :app:clean :app:bootJar
java LayerIndexVerifier.java app/build/libs/app-1.0.0.jar
java -jar app/build/libs/app-1.0.0.jar
java -Djarmode=tools -jar app/build/libs/app-1.0.0.jar list-layers
~~~

Đây là hai phương án thay thế tùy hệ thống build. **Không cần chạy cả Maven và Gradle trong cùng project**.

Một gate có thể yêu cầu:

- Build task trả exit code thành công.
- `BOOT-INF/layers.idx` tồn tại.
- Layer names/order phù hợp chiến lược.
- `BOOT-INF/lib/core-1.0.0.jar` tồn tại.
- `core-1.0.0.jar` nằm trong `internal-modules`.
- `LayerIndexVerifier.java` in `LAYER_INDEX_OK`.
- `java -jar` in `LAYERING_OK:SKU-42`.
- Docker image smoke test pass khi pipeline dùng custom Dockerfile.
- Các lần nâng Boot/Gradle/Maven phải chạy lại test vì DSL, schema và tools mode có thể thay đổi.

Không đánh dấu pass khi chỉ thấy một dòng `BUILD SUCCESSFUL`; đó chưa chứng minh custom layer đúng.

## 17. Checklist triển khai production

- [ ] Phân biệt **local module/project dependency** và **published internal dependency**.
- [ ] Ghi rõ chính sách cho library dạng release/SNAPSHOT và nhóm groupId nội bộ.
- [ ] Đặt matcher local modules trước các matcher broad hơn khi muốn ưu tiên internal-modules.
- [ ] Đặt catch-all dependencies cuối cùng.
- [ ] Liệt kê đúng tất cả layer names trong layerOrder.
- [ ] Dùng `layers.xml` hợp lệ với Maven hoặc `bootJar.layered` đúng trong Gradle.
- [ ] Không áp Boot plugin lên library core chỉ để build JAR.
- [ ] Chạy build ở đúng reactor/project context như CI.
- [ ] Dùng executable Boot JAR, không dùng plain JAR.
- [ ] Đọc layers.idx của archive cuối.
- [ ] Kiểm tra core membership, không chỉ layer name.
- [ ] Thử tools mode/list-layers/extract trên chính artifact phát hành.
- [ ] Dockerfile COPY đủ mọi extracted layer, đúng cache order.
- [ ] Chạy app/container smoke test với Java runtime tương thích.
- [ ] Pin dependencies và toolchain; dùng reproducible builds khi cần ổn định layer bytes.
- [ ] Đo cache hit/layer digest thực tế, không tuyên bố mức cải thiện trước khi đo.
- [ ] Giữ quy tắc và verification đồng bộ khi đổi GAV, module name, version hoặc Boot release.

## 18. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Maven Plugin, Layered Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Layered JAR/War: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Dockerfiles, `jarmode=tools` extraction: https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.3 — Efficient Deployments: https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html
- Apache Maven — Multi-module Reactor Guide: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Gradle 8.5 — Multi-project Builds: https://docs.gradle.org/8.5/userguide/multi_project_builds.html
- Docker — Build Cache: https://docs.docker.com/build/cache/
- Java 17 — JarFile API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html

**Kết luận:** Trong Spring Boot layered archives, **matcher order xác định thư viện thuộc layer nào**, còn **layerOrder xác định trình tự layer phục vụ image/cache**. Maven nhận local module từ **current reactor**, Gradle nhận local module từ **project dependency**; thư viện nội bộ đã publish cần matcher GAV riêng nếu muốn phân lớp theo nguồn gốc. Khi dùng **internal-modules** và **internal-releases**, phải xác minh **BOOT-INF/layers.idx**, đường dẫn thực của core, tools mode extraction và ứng dụng/container chạy được. Chỉ cấu hình XML/Groovy mà không kiểm tra artifact cuối chưa đủ.