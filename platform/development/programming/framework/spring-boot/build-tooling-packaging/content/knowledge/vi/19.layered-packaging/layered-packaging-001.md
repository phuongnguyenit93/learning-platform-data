# Mục đích của layered archive và quan hệ với cache lớp container

## 1. Vấn đề thực tế và mục tiêu học tập

Một Spring Boot executable JAR thường chứa cả mã ứng dụng và hàng chục hoặc hàng trăm thư viện. Khi bạn chỉ sửa một dòng trong Controller rồi đóng gói lại, **file JAR tổng thể sẽ thay đổi**. Nếu Dockerfile chỉ có `COPY app.jar app.jar`, bước COPY đó nhìn thấy một file mới và có thể tạo một **container image layer** mới chứa toàn bộ JAR. Điều này làm giảm khả năng tái sử dụng cache và khiến registry phải lưu/truyền một blob lớn dù phần thư viện hầu như không đổi.

**Layered archive** giải quyết phần bài toán này bằng cách ghi **metadata phân nhóm nội dung** của Spring Boot executable JAR/WAR thành các phần có mức độ thay đổi khác nhau. Công cụ tạo container image có thể dùng thông tin đó để đặt thư viện ổn định vào các image layers xuất hiện sớm, mã ứng dụng thường thay đổi vào image layer xuất hiện muộn.

Sau bài học, bạn có thể:

1. Giải thích layered archive của Spring Boot là gì, khác `BOOT-INF/lib` thông thường và khác Docker/OCI image layers như thế nào.
2. Mô tả vai trò của `BOOT-INF/layers.idx`, bốn lớp mặc định `dependencies`, `spring-boot-loader`, `snapshot-dependencies` và `application`.
3. Hiểu vì sao **thứ tự layer** và **tần suất thay đổi** quyết định khả năng reuse cache trong Docker build và container registry.
4. Cấu hình hoặc kiểm tra layered `bootJar` (Gradle) và `repackage` (Maven), dùng `spring-boot-jarmode-tools` ở Spring Boot 3.3 để liệt kê/giải nén các lớp.
5. Tạo một ví dụ Spring Boot Java 17+ chạy được, build executable JAR và một Dockerfile nhiều stage phân lớp hợp lý.
6. Kiểm chứng trước/sau khi sửa mã ứng dụng, quan sát cache hit của các bước `COPY` và phân biệt chúng với Gradle Build Cache hoặc Maven dependency cache.
7. Biết giới hạn của kỹ thuật: layer index không tự tối ưu một Dockerfile chỉ COPY nguyên JAR; cache không bảo đảm artifact an toàn hoặc image digest luôn giống.

**Phiên bản minh họa:** Spring Boot Gradle/Maven Plugin **3.3.5**, Java **17**, Gradle Wrapper/Maven Wrapper tương thích và Docker Engine/BuildKit có khả năng build Linux images. Spring Boot 3.3 có công cụ **`-Djarmode=tools`**; lệnh `layertools` cũ đã bị deprecate từ Spring Boot 3.3. Không suy luận các lệnh/launcher này áp dụng y nguyên cho mọi phiên bản Boot. Dùng version thực tế do project của bạn phê duyệt.

## 2. Hai nghĩa khác nhau của từ “layer”

Trước khi cấu hình, phải phân biệt rõ:

| Loại layer | Thuộc hệ thống nào? | Nó thực sự là gì? |
| --- | --- | --- |
| **Spring Boot archive layer** | Spring Boot packaging plugin | **Nhóm file** bên trong một executable JAR/WAR, được mô tả bởi `layers.idx`; chưa phải OCI image layer |
| **Docker/OCI image layer** | Container builder và image registry | Một tập thay đổi filesystem/metadata trong image; có content digest riêng và có thể được cache/chia sẻ |
| **Gradle Build Cache entry** | Gradle build tool | Kết quả của một task được cache theo inputs/implementation; không phải Docker image layer |
| **Docker build cache** | Docker BuildKit/legacy builder | Kết quả có thể tái sử dụng của một bước Dockerfile hay build graph |
| **Maven/Gradle dependency cache** | Build tool | Bản sao JAR/POM/metadata đã tải từ repositories; không tự tạo OCI layers |

Có thể coi Spring Boot `layers.idx` là **bản đồ hướng dẫn** công cụ tách tập file trong executable archive. Dockerfile hoặc Cloud Native Buildpacks phải **thực sự dùng bản đồ đó** để đưa từng nhóm vào các image layers. Nếu chỉ tạo `layers.idx` mà không dùng nó, container cache chưa được hưởng lợi ích đáng kể.

### Hình dung đường đi

~~~text
Maven package/repackage HOẶC Gradle bootJar
            |
            v
  Spring Boot executable JAR
  ├── BOOT-INF/classes/...
  ├── BOOT-INF/lib/...
  ├── Spring Boot launcher
  └── BOOT-INF/layers.idx   [metadata phân nhóm]
            |
            v
  java -Djarmode=tools -jar app.jar extract --layers
            |
            v
  extracted/
  ├── dependencies/
  ├── spring-boot-loader/
  ├── snapshot-dependencies/
  └── application/
            |
            v
  Dockerfile: COPY từng nhóm theo thứ tự
            |
            v
  Container image
  ├── base JRE layer(s)
  ├── dependencies layer
  ├── spring-boot-loader layer
  ├── snapshot-dependencies layer
  └── application layer
~~~

Đây là sơ đồ khái niệm: số lượng image layers thực tế còn tùy các bước Dockerfile khác, metadata, base image và khả năng tối ưu của builder. Bốn thư mục được tách ra là **nhóm Spring Boot**, còn Docker mới tạo các image filesystem layers.

## 3. Executable JAR thông thường trông như thế nào?

Một Spring Boot executable JAR có cấu trúc điển hình:

~~~text
layer-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...    (launcher)
└── BOOT-INF/
    ├── classes/
    │   └── com/example/layers/LayerDemoApplication.class
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-webmvc-*.jar
    │   └── ...                           (thư viện runtime)
    ├── classpath.idx                     (có thể có)
    └── layers.idx                        (metadata về các lớp)
~~~

**Các điểm cần nhớ:**

- `BOOT-INF/classes` chứa application classes/resources.
- `BOOT-INF/lib` chứa những dependency JAR được đóng gói (nested JAR).
- Spring Boot launcher giúp JVM có thể chạy `java -jar` với cấu trúc nested libraries.
- `BOOT-INF/layers.idx` liệt kê các **archive paths được gán vào các layer tên cụ thể** và thứ tự ưu tiên để đưa vào container image.
- `BOOT-INF/classpath.idx`, nếu tồn tại, phục vụ thứ tự classpath; **không phải cùng chức năng** với `layers.idx`.
- File `layers.idx` chỉ chứa metadata; nó **không tự di chuyển** các JAR khỏi `BOOT-INF/lib` hoặc biến một JAR thành nhiều artifact ở bước build.

**Layered JAR vẫn là một executable JAR hợp lệ.** Với Spring Boot 3.3.5 ví dụ, `java -jar layer-demo-0.0.1-SNAPSHOT.jar` vẫn hoạt động như trước; cách chia nhóm file phục vụ đóng gói container.

### Ví dụ ý nghĩa của layers.idx

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/spring-core-6.x.y.jar"
  - "BOOT-INF/lib/spring-boot-3.3.5.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/launch/JarLauncher.class"
- "snapshot-dependencies":
  - "BOOT-INF/lib/my-client-1.0-SNAPSHOT.jar"
- "application":
  - "BOOT-INF/classes/com/example/layers/LayerDemoApplication.class"
~~~

Đây là **minh họa cú pháp và đường dẫn**; `6.x.y` và `my-client` không phải danh sách file thực trong project mẫu. Trong JAR thực tế có nhiều entry hơn, và layer `snapshot-dependencies` có thể không có JAR nào nếu không dùng snapshot. Công cụ plugin tạo `layers.idx` chính xác theo nội dung archive và quy tắc version đang sử dụng.

## 4. Bốn layer mặc định của Spring Boot

Với Spring Boot 3.3, default layering cho executable JAR/WAR thường dùng bốn nhóm theo thứ tự:

| Thứ tự | Layer | Nội dung thường gặp | Tại sao đặt ở vị trí này? |
| --- | --- | --- | --- |
| 1 | `dependencies` | Các **non-project dependencies** có version không chứa `SNAPSHOT` | Thường ổn định nhất trong các lượt chỉnh mã |
| 2 | `spring-boot-loader` | Các lớp Boot launcher dưới `org/springframework/boot/loader` | Chỉ thay đổi khi Boot loader/plugin thay đổi |
| 3 | `snapshot-dependencies` | Các thư viện ngoài có version chứa `SNAPSHOT` | Có khả năng thay đổi thường xuyên mà vẫn cùng tọa độ |
| 4 | `application` | Application classes/resources và local project/module dependencies | Thay đổi nhiều nhất khi developer chỉnh source |

### 4.1. dependencies

Đây là những JAR ngoài không phải snapshot: Spring Framework, Spring Boot starters, logging libraries và các dependency runtime ổn định khác (tùy graph thật). Nếu sửa Controller mà không đổi version, dependencies thường **giữ nguyên bytes**. Đặt chúng sớm giúp cache Docker có khả năng tái sử dụng các layer tương ứng.

**Không có nghĩa dependency này “không bao giờ thay đổi”**. Nâng BOM, đổi Spring Boot version, thay driver hoặc dependency transitive sẽ thay file JAR ở `dependencies`; cache invalidation khi đó là **đúng**.

### 4.2. spring-boot-loader

Chứa mã launcher của Spring Boot, ví dụ `org.springframework.boot.loader.launch.JarLauncher`. Loader thường ổn định giữa các lần chỉnh business code. Việc tách loader ra giúp nó không phải bị copy lại mỗi khi lớp Controller thay đổi.

**Không nhầm Boot launcher với Spring MVC hay auto-configuration libraries.** Nhiều thư viện Spring Boot nằm trong `BOOT-INF/lib` và thuộc `dependencies`, không nằm trong layer `spring-boot-loader`.

### 4.3. snapshot-dependencies

Dành cho non-project dependencies mang version `SNAPSHOT`. Đây là tín hiệu phổ biến cho một artifact còn có thể thay đổi trước release; do đó lớp snapshot được đặt **sau** các lớp ổn định, tránh phá cache của chúng khi SNAPSHOT thay đổi.

Một SNAPSHOT từ repository có thể được publish lại với **cùng version string nhưng bytes khác**. Chính sách dependency resolution, checksum verification và caching vẫn phải đảm bảo dự án lấy đúng artifact; layered packaging không làm bản SNAPSHOT trở nên bất biến.

### 4.4. application

Gồm compiled classes, application resources và local module/project dependencies mà plugin phân loại vào application layer. Sửa `GreetingController.java`, thêm endpoint hoặc đổi `application.yml` thường ảnh hưởng lớp này. Vì được đặt **cuối**, thay đổi application không nhất thiết invalidates các image layers đã COPY ổn định trước đó.

**Lưu ý về multi-module:** trong Gradle, project dependencies được mặc định đưa vào `application`; trong Maven, các module thuộc cùng build/reactor có thể được xem là local module dependencies. Một module thư viện nội bộ đổi thường xuyên có thể tạo thay đổi trong application layer; mặc định này có chủ đích nhưng có thể được điều chỉnh khi thực sự cần.

## 5. Vì sao thứ tự layer tác động tới Docker cache?

Dockerfile thông thường được thực thi tuần tự. Builder tái sử dụng kết quả của một instruction nếu instruction và **các đầu vào liên quan** đủ điều kiện cache. Khi một bước mất cache, các bước phụ thuộc phía sau thường phải tạo kết quả mới, kể cả có bước COPY dữ liệu ít thay đổi.

Giả sử hai image lần lượt được build:

~~~text
Build A:
FROM JRE
COPY dependencies/         -> image layer D1
COPY spring-boot-loader/   -> image layer L1
COPY snapshot-dependencies/-> image layer S1
COPY application/          -> image layer A1

Build B: chỉ thay LayerDemoApplication.java
FROM JRE                   -> base layer reused
COPY dependencies/         -> D1 reused
COPY spring-boot-loader/   -> L1 reused
COPY snapshot-dependencies/-> S1 reused
COPY application/          -> layer mới A2
~~~

Sơ đồ là **dự kiến khi Docker cache hoạt động và các đầu vào của ba COPY đầu không thay đổi**. Output `CACHED` thực tế phụ thuộc builder, cache storage và cách pipeline chạy. Thứ tự từ ít thay đổi đến hay thay đổi **không phải quy tắc ngẫu nhiên**: nó bảo vệ những layer lớn/ổn định khỏi invalidation không cần thiết do application code đổi.

### So sánh hai Dockerfile

**Cách 1 – Copy nguyên JAR:**

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/layer-demo-0.0.1-SNAPSHOT.jar application.jar
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

Khi chỉnh một byte trong ứng dụng rồi build lại Boot JAR, **file JAR thay đổi toàn bộ dưới góc nhìn đầu vào COPY**. Docker không thể biết cần giữ riêng phần `BOOT-INF/lib` trong JAR. Nó sẽ tạo lại layer COPY chứa nguyên JAR (giả sử cache không còn phù hợp).

**Cách 2 – Tách theo layered archive:** một multi-stage Dockerfile trích xuất và COPY riêng từng nhóm sẽ được trình bày ở mục 9. Với cách ấy, Docker nhận được **bốn đầu vào độc lập** để tính cache cho từng bước.

**Điểm cốt lõi:** Boot `layers.idx` **không thể tự tăng Docker cache hit nếu Dockerfile vẫn COPY nguyên JAR vào một bước**. Người build image phải dùng `jarmode` hoặc tooling khác để tách/lập OCI layers theo metadata.

## 6. Không nhầm giữa cache build, cache image và image registry

| Công nghệ | Cái gì được cache | Khi nào có lợi? | Điều không thể kết luận |
| --- | --- | --- | --- |
| Gradle Build Cache | Đầu ra của `compileJava`, `test`, task cacheable khác | Lặp lại task cùng input | Không chứng minh Docker reuse layer |
| Maven local repository | JAR/POM đã resolve | Bớt tải dependencies | Không chứng minh Spring Boot layered archive đúng |
| Docker/BuildKit cache | Kết quả instruction/build graph, filesystem layer | Rebuild image nhanh hơn | Không chứng minh code đã được test |
| OCI registry blob deduplication | Layer blobs có digest giống nhau giữa image versions | Giảm dữ liệu cần upload/download và lưu trữ | Không nhất thiết giảm kích thước tổng của bản deploy |
| Spring Boot layers.idx | Metadata ánh xạ archive entries → logical layer | Hướng dẫn phân tách executable JAR/WAR | Không phải cache và không phải image layer |

**Ví dụ:** Gradle báo `:bootJar UP-TO-DATE` nhưng Docker COPY nguyên `application.jar`, thì Dockerfile vẫn chỉ có **một layer cho toàn JAR**. Ngược lại, Gradle có thể thực thi lại `bootJar` nhưng Docker vẫn reuse các Docker layers nếu nội dung các thư mục extracted tương ứng giống nhau.

Layer reuse còn chịu tác động của base image, build arguments, metadata, platform, Dockerfile command, cache backend và CI runner. Nếu CI luôn tạo builder mới, không nạp cache cũ, bạn có thể không thấy `CACHED` dù phân lớp đã đúng. Remote cache hoặc registry cache export/import cần được thiết lập riêng nếu môi trường đòi hỏi.

## 7. Ví dụ Spring Boot Java 17 có thể chạy

Ta tạo một Spring Boot Web MVC API nhỏ. Nó nhận request HTTP và trả string cố định, đủ để thay một dòng ở lớp ứng dụng mà không đổi dependencies.

### 7.1. Cấu trúc project

~~~text
layer-demo/
├── settings.gradle
├── build.gradle
├── gradlew, gradlew.bat, gradle/wrapper/
├── Dockerfile                 (mẫu layered ở mục 9)
├── .dockerignore
└── src/
    ├── main/java/com/example/layers/
    │   ├── LayerDemoApplication.java
    │   └── VersionController.java
    └── test/java/com/example/layers/
        └── VersionControllerTest.java
~~~

Sơ đồ giả định project đã có **Gradle Wrapper hợp lệ**. Nếu repository thật dùng Maven, xem POM ở mục 11 thay vì duy trì song song cả Maven và Gradle chỉ để làm bài tập.

### 7.2. File settings.gradle

~~~groovy
rootProject.name = 'layer-demo'
~~~

### 7.3. File build.gradle hoàn chỉnh — Gradle Groovy DSL

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

// Spring Boot 3.3 mặc định tạo index cho layered archive.
// Khai báo rõ trong demo để thấy chính xác ý định.
tasks.named('bootJar') {
    layered {
        enabled = true
    }
    includeTools = true
}

springBoot {
    mainClass = 'com.example.layers.LayerDemoApplication'
}
~~~

**Giải thích:**

1. `java` tạo main/test source sets, `compileJava` và task test.
2. `org.springframework.boot` tạo task `bootJar` và các integration để đóng gói executable JAR.
3. `io.spring.dependency-management` kết hợp Spring Boot plugin import BOM phù hợp, nên starter dependencies không cần version tường minh.
4. `testImplementation` chỉ thêm dependency test vào test classpath; không đi vào runtime image mặc định.
5. `layered { enabled = true }` tạo `BOOT-INF/layers.idx`. Với Spring Boot 3.3, layering **đã bật mặc định**, nhưng khai báo tường minh tiện kiểm tra/giảng dạy.
6. `includeTools = true` giữ `spring-boot-jarmode-tools` trong Boot JAR để dùng `-Djarmode=tools`. Nếu chọn `includeTools=false`, bạn không thể mặc nhiên thực hiện lệnh extract bằng tools từ chính artifact đó.
7. `springBoot.mainClass` bảo đảm launcher biết đúng application main class.
8. Java toolchain 17 đảm bảo biên dịch với JDK phù hợp; Gradle Wrapper còn phải tương thích với plugin Boot đã chọn.

Nếu repository quản lý dependency repositories tập trung trong `settings.gradle` với `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, hãy bỏ `repositories { mavenCentral() }` ở project và dùng repository được cấu hình trong settings. Đây là yêu cầu quản trị dependency, không phải cấu hình layered archive.

### 7.4. File LayerDemoApplication.java

Đường dẫn `src/main/java/com/example/layers/LayerDemoApplication.java`:

~~~java
package com.example.layers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LayerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LayerDemoApplication.class, args);
    }
}
~~~

Đây là class Java độc lập với Controller và biên dịch khi có Spring Boot dependencies trên classpath. Nó khởi chạy Spring MVC web application với embedded Tomcat; cổng mặc định thường là 8080 nếu chưa cấu hình khác.

### 7.5. File VersionController.java

Đường dẫn `src/main/java/com/example/layers/VersionController.java`:

~~~java
package com.example.layers;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {
    @GetMapping("/version")
    public String version() {
        return "layer-v1";
    }
}
~~~

Đây là class Java hoàn chỉnh với `@RestController`, được scan do nằm dưới `com.example.layers`. Khi ứng dụng đã chạy thành công, một HTTP GET tới `/version` sẽ trả body chính xác:

~~~text
layer-v1
~~~

### 7.6. File VersionControllerTest.java

Đường dẫn `src/test/java/com/example/layers/VersionControllerTest.java`:

~~~java
package com.example.layers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(VersionController.class)
class VersionControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void returnsVersion() throws Exception {
        mvc.perform(get("/version"))
                .andExpect(status().isOk())
                .andExpect(content().string("layer-v1"));
    }
}
~~~

Test này có thể chạy bằng Gradle `test { useJUnitPlatform() }` và Spring Boot Starter Test. Khi đổi response của Controller sang `layer-v2` trong bài tập, **đổi assertion của test tương ứng**, nếu không build fail ở bước test. Đó là hành vi đúng của test: layer optimization không được làm mất cổng kiểm soát chức năng.

## 8. Build layered JAR và kiểm chứng layers.idx

### 8.1. Linux/macOS

Từ root project:

~~~bash
./gradlew --version
./gradlew clean test bootJar

jar tf build/libs/layer-demo-0.0.1-SNAPSHOT.jar |
    grep -E 'BOOT-INF/(layers.idx|classes/|lib/)'
~~~

### 8.2. Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar

jar tf .\build\libs\layer-demo-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/(layers.idx|classes/|lib/)'
~~~

**Dấu hiệu cần xác nhận:**

- `BOOT-INF/layers.idx` tồn tại trong Boot executable JAR.
- `BOOT-INF/classes/com/example/layers/LayerDemoApplication.class` và `VersionController.class` tồn tại.
- Có các JAR runtime trong `BOOT-INF/lib`, gồm Spring Framework/Spring Boot/Tomcat được giải quyết theo BOM.
- `spring-boot-jarmode-tools` có mặt trong archive nếu `includeTools=true` và plugin phiên bản phù hợp.
- Chạy đúng file `layer-demo-0.0.1-SNAPSHOT.jar`, **không phải `-plain.jar`** nếu Gradle cũng sinh plain JAR.

Nếu `jar tf` không tìm thấy `BOOT-INF/layers.idx`, hãy kiểm tra task thực tế có phải `bootJar`, có bị đặt `layered.enabled=false` ở một cấu hình khác, hoặc bạn đang đọc plain/archive cũ không. **Đừng thêm file layers.idx viết tay** để giả vờ bật layering.

### 8.3. Liệt kê các layer bằng JAR tools của Spring Boot 3.3

Linux:

~~~bash
java -Djarmode=tools \
    -jar build/libs/layer-demo-0.0.1-SNAPSHOT.jar list-layers
~~~

Windows PowerShell, viết một dòng để tránh nhầm escape shell:

~~~powershell
java -Djarmode=tools -jar .\build\libs\layer-demo-0.0.1-SNAPSHOT.jar list-layers
~~~

Với cấu hình mặc định, các tên layer được liệt kê bao gồm:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

**Thứ tự và cách trình bày output có thể phụ thuộc phiên bản/định nghĩa custom layers**, và một layer có thể rỗng. Lệnh chỉ cung cấp thông tin, **không tạo Docker/OCI image**.

### 8.4. Giải nén thành các thư mục layer

Linux/macOS:

~~~bash
mkdir -p build/layer-inspection

java -Djarmode=tools \
    -jar build/libs/layer-demo-0.0.1-SNAPSHOT.jar \
    extract --layers --destination build/layer-inspection

find build/layer-inspection -maxdepth 2 -type d
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force .\build\layer-inspection | Out-Null

java -Djarmode=tools -jar .\build\libs\layer-demo-0.0.1-SNAPSHOT.jar extract --layers --destination .\build\layer-inspection

Get-ChildItem .\build\layer-inspection\
~~~

Kết quả kỳ vọng là các thư mục con tương ứng `dependencies`, `spring-boot-loader`, `snapshot-dependencies` và `application`. Chúng có cấu trúc tệp phù hợp để copy/chồng lên nhau trong final image.

**Chú ý version:** Spring Boot 3.3 dùng lệnh `java -Djarmode=tools -jar app.jar extract --layers --destination ...`. Các tài liệu cũ có `-Djarmode=layertools` và `spring-boot-jarmode-layertools`; đây là tên cơ chế cũ, **không phải lựa chọn nên ưu tiên trong ví dụ Boot 3.3**.

**Hạn chế:** Spring Boot tools mode không dùng được với một **fully executable archive có prepended launch script**. Nếu project gọi `launchScript()` để tạo JAR tự chạy như shell script, hãy tắt launch script cho artifact được dùng với jarmode tools, hoặc dùng một packaging flow khác đã được hỗ trợ. Đây là ranh giới thực tế quan trọng khi bạn vừa muốn kiểu launcher script vừa muốn extract theo lớp.

## 9. Dockerfile nhiều stage để tận dụng các lớp

File `Dockerfile` ở project root:

~~~dockerfile
# Stage 1: trích xuất nội dung theo Spring Boot layers.idx
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /workspace

COPY build/libs/layer-demo-0.0.1-SNAPSHOT.jar application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

# Stage 2: runtime chỉ cần JRE và các file đã trích xuất
FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**Đây là Dockerfile đầy đủ cho ví dụ Boot 3.3, theo cách Spring Boot 3.3 jarmode tools tạo layout extracted.** Nó được dùng sau khi đã chạy Gradle `bootJar`. `-Djarmode=tools` trong build stage làm việc ở chế độ công cụ, không khởi chạy HTTP server. Lệnh `extract --layers` tạo cấu trúc mà Boot hỗ trợ, trong đó phần `application` chứa JAR ứng dụng đã tách lớp và dùng được với các dependency được copy vào working directory; stage runtime chạy `java -jar application.jar`.

Giải thích từng bước:

1. **Extractor stage:** copy **nguyên Boot JAR** vào môi trường build có Java để gọi tools mode. Stage này **có thể phải chạy lại** khi một class ứng dụng đổi; đây là một chi phí xử lý chấp nhận được.
2. **Runtime stage:** bắt đầu từ JRE image. Chọn đúng Java major version tương thích với bytecode và dependencies.
3. **COPY dependencies:** tạo layer chứa phần lớn JAR thư viện phát hành ít thay đổi. Đây thường là layer lớn nhất trong nhóm app-specific layers.
4. **COPY spring-boot-loader:** copy launcher, thường ổn định nếu Spring Boot version giữ nguyên.
5. **COPY snapshot-dependencies:** copy dependency snapshot, có thể đổi thường xuyên hơn release dependencies.
6. **COPY application:** đưa compiled classes/resources và module nội bộ vào cuối, để thay đổi Controller thường chỉ ảnh hưởng lớp cuối này.
7. **ENTRYPOINT:** dùng `java -jar application.jar` cho layout extracted do Boot 3.3 tools tạo ra. **Không tự đổi thành `java -jar` nguyên fat JAR ở runtime stage**, vì fat JAR không được copy nguyên vào stage cuối theo Dockerfile này.
8. **EXPOSE 8080:** khai báo cổng dự kiến; bản thân `EXPOSE` không publish cổng ra host và không bảo đảm app đã chạy.
9. Không dùng wildcard `COPY build/libs/*.jar` trong demo: Gradle có thể tạo cả `-plain.jar`, dẫn tới COPY nhiều file hoặc chọn sai artifact.

### 9.1. File .dockerignore

Nên giới hạn Docker build context để không gửi nhầm cache, credentials và file tạm. Mẫu:

~~~dockerignore
.git
.gradle
.idea
.vscode
.repro-check
**/*.log
build/**
!build/libs/
!build/libs/layer-demo-0.0.1-SNAPSHOT.jar
~~~

**Lưu ý .dockerignore:** quy tắc cho phép lại build/libs phải được kiểm thử với Docker version/build context thực tế; Docker hỗ trợ các `!` exceptions nhưng thư mục cha bị exclude có thể ảnh hưởng việc duyệt. Đối với demo nhỏ, cách dễ hiểu hơn là **chỉ loại các thư mục bí mật/tạm** mà không exclude `build`, rồi xác nhận file `build/libs/layer-demo-0.0.1-SNAPSHOT.jar` có trong Docker context. Trong production, dùng context được dựng riêng từ artifact đã test hoặc Dockerfile-specific ignore policy để tránh kéo cả `build` không cần thiết.

**Đừng đưa secret** vào build context, `ARG`/`ENV` hoặc layer bằng cách copy file credentials. Docker image layers có lịch sử và có thể được phân tích, vì vậy “xóa file ở layer sau” không nhất thiết xóa được secret khỏi blob layer trước đó.

### 9.2. Build và chạy image

Linux/macOS:

~~~bash
./gradlew clean test bootJar
docker build --progress=plain -t layer-demo:one .
docker run --rm -p 8080:8080 layer-demo:one
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
docker build --progress=plain -t layer-demo:one .
docker run --rm -p 8080:8080 layer-demo:one
~~~

Khi container đã sẵn sàng, terminal khác:

~~~bash
curl -fsS http://localhost:8080/version
~~~

Kết quả HTTP body:

~~~text
layer-v1
~~~

Nếu dùng PowerShell:

~~~powershell
Invoke-RestMethod -Uri "http://localhost:8080/version"
~~~

Để chạy demo trên port khác nếu 8080 host bị chiếm, map cổng host 8081 đến container 8080: `docker run --rm -p 8081:8080 layer-demo:one` rồi gọi `http://localhost:8081/version`. Không cần đổi Spring Boot `server.port` chỉ để giải quyết host-port conflict.

## 10. Thí nghiệm hai lần build Docker để quan sát cache

Mục tiêu: thay đổi **chỉ một chuỗi trả về** của Controller và xác nhận các thư viện ổn định không bị coi là thay đổi ở các bước COPY tương ứng.

### Bước A — baseline

1. Đảm bảo `VersionController.version()` trả `"layer-v1"`; test kỳ vọng `layer-v1`.
2. Chạy Gradle `clean test bootJar`.
3. Chạy `docker build --progress=plain -t layer-demo:one .`.
4. Ghi build log, đặc biệt phần `COPY --from=extractor ...dependencies` và `application`.
5. Chạy image, xác nhận `GET /version` trả `layer-v1`.

### Bước B — chỉ sửa application

Trong `VersionController.java`, đổi:

~~~java
return "layer-v1";
~~~

thành:

~~~java
return "layer-v2";
~~~

Sau đó sửa assertion của `VersionControllerTest.java` từ `layer-v1` sang `layer-v2`; **không sửa `build.gradle` hay dependency versions**.

Chạy:

~~~bash
./gradlew clean test bootJar
docker build --progress=plain -t layer-demo:two .
~~~

Kiểm tra:

~~~bash
docker run --rm -p 8081:8080 layer-demo:two
~~~

Rồi gọi `http://localhost:8081/version` (nếu host 8081 đang trống); response body là:

~~~text
layer-v2
~~~

Trong môi trường có Docker build cache hợp lệ, **ba bước COPY ổn định** (`dependencies`, `spring-boot-loader`, `snapshot-dependencies`) có thể hiện `CACHED` hoặc cơ chế reuse tương tự, trong khi `application` tạo layer mới. **Không tự ghi “100% CACHED” nếu log chưa chứng minh**: build cache có thể bị xóa, builder instance thay đổi hoặc base image nhận digest mới.

### Bước C — đổi dependency

Thêm/sửa version một dependency runtime hoặc nâng Spring Boot BOM (trên branch thử nghiệm), build lại rồi quan sát log. Lần này `dependencies` hoặc `spring-boot-loader` có thể thay đổi; những layer đứng sau **cũng có thể mất cache** dù ứng dụng chỉ sửa ít. Đây là hệ quả hợp lý của Docker layer chain.

**Khôi phục** dependency/Controller/test về baseline sau thí nghiệm. Đừng thay một bản framework nhiều module chỉ để đo cache ở project thật mà không có kiểm thử tương thích.

### Cách đọc Docker log

Docker BuildKit có thể in `CACHED` cho bước được tái sử dụng. Nhiều bước thực thi có thời lượng rất ngắn mà không ghi “CACHED”; cần đọc log chi tiết thay vì suy đoán. Nếu `docker build` báo “failed to solve” hoặc không tìm thấy thư mục extractor output, xác minh `jarmode tools extract` đã tạo đúng thư mục và Docker COPY source path hợp lệ.

## 11. Maven cũng hỗ trợ layered executable archives

Đề bài tập trung khái niệm Spring Boot layered archive, nên cùng mô hình cũng áp dụng cho Maven. Khi dùng Spring Boot Starter Parent, Maven plugin `spring-boot:repackage` thường tạo `layers.idx` theo mặc định.

### POM đầy đủ cho ví dụ Maven tương đương

File `pom.xml` của **project Maven riêng**, dùng cùng hai Java classes ở mục 7:

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
    <artifactId>layer-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
                    <includeTools>true</includeTools>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đây là một POM riêng, thay thế project Gradle**, không khuyên duy trì cả hai build tools trong cùng ứng dụng. Với Spring Boot Parent, goal `repackage` đã được cấu hình; plugin tạo executable JAR và layers index. Hai cấu hình `enabled`/`includeTools` trong ví dụ chỉ ghi rõ ý định, tương ứng các defaults của Spring Boot 3.3 theo tài liệu phiên bản.

Chạy:

~~~bash
./mvnw clean verify
jar tf target/layer-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/layers.idx'
java -Djarmode=tools -jar target/layer-demo-0.0.1-SNAPSHOT.jar list-layers
~~~

Nếu chuyển Dockerfile ở mục 9 sang Maven, thay:

~~~dockerfile
COPY target/layer-demo-0.0.1-SNAPSHOT.jar application.jar
~~~

cho dòng COPY của extractor stage. Phần `extract --layers` và các `COPY --from=extractor` trong final stage giữ cùng ý nghĩa.

**Không nhầm Maven dependency management và Spring Boot plugin management.** Nếu project chỉ import `spring-boot-dependencies` BOM mà không kế thừa Parent, phải khai báo plugin version và execution `repackage` phù hợp; BOM một mình **không tự tạo executable JAR/layers.idx**.

## 12. Lớp và thứ tự lớp tùy biến: khi nào cần?

Cấu hình mặc định đã phù hợp với nhiều project. Khi module nội bộ chứa nhiều logic ít thay đổi hoặc có code generation thường xuyên thay đổi, có thể tạo layer riêng để tối ưu cache. Nhưng đổi layering quá sớm dễ tăng số layers và phức tạp vận hành.

### 12.1. Gradle DSL định nghĩa rõ mặc định

Đoạn sau là **trích đoạn thay thế cho cấu hình `tasks.named('bootJar')` ở mục 7**, mô tả rule mặc định của Spring Boot 3.3 bằng Groovy DSL:

~~~groovy
tasks.named('bootJar') {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include "org/springframework/boot/loader/**"
            }
            intoLayer("application")
        }
        dependencies {
            intoLayer("application") {
                includeProjectDependencies()
            }
            intoLayer("snapshot-dependencies") {
                include "*:*:*SNAPSHOT"
            }
            intoLayer("dependencies")
        }
        layerOrder = [
            "dependencies",
            "spring-boot-loader",
            "snapshot-dependencies",
            "application"
        ]
    }
}
~~~

**Giải thích:**

- `application { ... }` định nghĩa cách các class/resource và launcher files vào từng layer.
- `dependencies { ... }` phân loại nested dependency artifacts.
- `includeProjectDependencies()` đưa các module Gradle `project(':module')` vào `application`.
- `include "*:*:*SNAPSHOT"` là pattern `group:artifact:version` đối với dependency snapshot.
- `intoLayer("dependencies")` ở cuối nhận phần còn lại chưa được lớp trước nhận.
- `layerOrder` là thứ tự **ghi/copy layer**; nó có thể khác thứ tự bạn khai báo `intoLayer`.
- Các matcher được áp dụng **từ trên xuống**, nội dung đã được một layer nhận sẽ không tự được phân bổ lại ở layer sau.
- `layerOrder` phải bao phủ **mọi tên layer** được nhắc tới trong `intoLayer`.

**Rất quan trọng:** các `include`/`exclude` bên trong `layered` **chỉ quyết định file thuộc layer nào**, không có tác dụng loại một dependency khỏi executable JAR. Để loại module khỏi artifact, phải xử lý dependency graph hoặc `bootJar.classpath` theo API thích hợp, rồi kiểm tra executable JAR cuối.

### 12.2. Kotlin DSL tương đương

Trong `build.gradle.kts`, cùng logic:

~~~kotlin
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
~~~

Đây là fragment cấu hình cho project Kotlin Gradle DSL đã áp dụng Spring Boot plugin; đặt `import` ở đầu file. Không sao chép nguyên fragment vào project Maven hoặc project không có task `bootJar`.

### 12.3. Maven custom layers

Maven plugin cũng hỗ trợ một file `layers.xml` để định nghĩa `application`, `dependencies`, `layerOrder`. Cấu hình có cú pháp XML riêng và dùng `includeModuleDependencies` thay cho tên Gradle `includeProjectDependencies`. Đừng lấy DSL Groovy rồi đổi dấu ngoặc thành XML theo suy đoán. Dùng tài liệu `Spring Boot Maven Plugin – Layered Jar or War` để cấu hình đúng schema/XSD của phiên bản đang chạy.

### 12.4. Khi nào nên tránh tùy biến?

- Project chỉ có vài classes và dependencies ổn định: mặc định đủ.
- CI không có cache giữa các lượt build: tách thêm layer mà chưa triển khai cache store có thể không giúp nhiều.
- Layer nào cũng thay đổi cùng nhau vì dynamic dependencies/generator: cần sửa đầu vào không ổn định trước.
- Container image bị đổi base image mỗi lần: Docker invalidate các bước sau, bất kể custom layers.
- Team chưa có smoke test chạy **image thật**: thay cấu trúc image trước khi kiểm chứng runtime có thể gây rủi ro không cần thiết.

## 13. Layered archive có thể áp dụng cho WAR không?

Có. Spring Boot hỗ trợ layered executable WAR cùng `layers.idx`, nhưng WAR layout khác JAR:

~~~text
Spring Boot executable JAR:
  BOOT-INF/classes/
  BOOT-INF/lib/
  BOOT-INF/layers.idx

Spring Boot executable WAR:
  WEB-INF/classes/
  WEB-INF/lib/
  WEB-INF/lib-provided/
  WEB-INF/layers.idx
~~~

Trong WAR, `WEB-INF/lib-provided` thường dùng cho container libraries được đánh dấu `provided`/`providedRuntime`, hỗ trợ executable WAR không xung đột khi deploy lên external Servlet container. Khi đóng image từ WAR, cần theo **công cụ và layout WAR tương ứng**, không tự áp Dockerfile của JAR lên WAR vì cấu trúc artifact và launcher khác.

Gradle có task `bootWar` khi áp dụng `war` plugin; Maven có `<packaging>war</packaging>` và `spring-boot:repackage`. Cả hai cần kiểm tra `WEB-INF/layers.idx` trên artifact thực tế.

**Không thay đổi bài toán chính:** dù JAR hay WAR, metadata về layers chỉ hữu ích nếu image builder dùng nó để tách file thành những OCI image layers phù hợp.

## 14. Lợi ích thực tế và điều không được hứa quá mức

### 14.1. Lợi ích thường gặp

- **Build image nhanh hơn:** khi chỉ mã ứng dụng đổi, Docker có cơ hội reuse layers của dependencies và loader.
- **Giảm upload/pull lại:** registry có thể tái sử dụng blob cũ thay vì upload/download lại toàn bộ fat JAR.
- **Hợp lý hóa cache giữa releases:** tách phần thường thay đổi (application) khỏi phần ổn định (third-party libraries).
- **Dễ quan sát thành phần:** `layers.idx` và thư mục extracted giúp hiểu artifact chứa gì, phân chia theo mục tiêu nào.
- **Hỗ trợ buildpack/CI workflows:** các công cụ hiểu layered archive có thể tận dụng thông tin này khi tạo OCI images.
- **Giảm downstream invalidation:** chỉ thay phần cuối image build graph khi input các layer trước không đổi.

### 14.2. Điều layering không tự bảo đảm

- **Không tự làm JAR nhỏ hơn.** Các thư viện vẫn nằm trong executable archive; thêm metadata/công cụ còn có thể tăng nhẹ kích thước file.
- **Không bảo đảm JVM khởi động nhanh hơn.** Tốc độ startup phụ thuộc class loading, JIT, CDS, I/O, AOT, container và application, không chỉ cách chia layers.
- **Không xóa CVE hoặc thư viện không cần.** Muốn giảm attack surface phải đánh giá và loại dependency tại nguồn, scan image/SBOM.
- **Không ép mọi image digest giống nhau** khi chỉ đổi source. Image manifest/layer ứng dụng đổi là điều đúng.
- **Không bảo đảm cache hit nếu base image hoặc toolchain thay đổi.** Registry/cache backend, content digest, Dockerfile command và build context vẫn quyết định.
- **Không thay thế reproducible builds.** Volatile timestamps, generated files, SNAPSHOT artifacts hoặc dynamic versions có thể làm dependency/application layer đổi dù mã business không thay.
- **Không thay thế kiểm thử.** Một layer được cache từ lượt trước không chứng minh image mới có thể startup hoặc API chạy đúng.

## 15. Cloud Native Buildpacks và build-image

Ngoài Dockerfile thủ công, Spring Boot có tasks/goals để tạo OCI image qua **Cloud Native Buildpacks**, chẳng hạn `bootBuildImage` của Gradle hoặc `spring-boot:build-image` của Maven. Buildpacks có lifecycle/cache và quy tắc chia lớp riêng; với builder phù hợp chúng có thể tận dụng phân nhóm dependencies/application.

**Không mặc định đồng nhất ba việc:**

1. **`bootJar`** tạo executable JAR và `layers.idx`.
2. **Dockerfile nhiều stage** do bạn viết dùng `jarmode tools` để COPY từng layer.
3. **Cloud Native Buildpacks** xây image qua builder/lifecycle/cache theo cơ chế của buildpack.

Mỗi workflow có quyền kiểm soát Dockerfile, base image, build/run image và cache khác nhau. Khi sử dụng `bootBuildImage`, không cần tự viết Dockerfile ở mục 9, nhưng phải kiểm tra builder được lựa chọn, cache strategy, network, credentials, image tags và kết quả image thật. Đừng hứa Buildpacks luôn dùng **đúng bốn layer y hệt** Dockerfile thủ công trong mọi version.

Nếu project đã tiêu chuẩn hóa một trong hai luồng, ưu tiên đánh giá chính luồng đó thay vì thêm một Dockerfile thứ hai chỉ để có layering. Hai luồng đồng tồn tại có thể sinh image khác dependency/version và gây khó truy vết artifact được phát hành.

## 16. CI, Docker cache và quản trị artifact

### 16.1. Quy trình CI tối thiểu

1. **Pin source commit**: checkout đúng commit, không build từ working tree chưa xác định.
2. **Pin JDK/Wrapper/BOM**: dùng Java 17 và Gradle/Maven Wrapper/phụ thuộc theo chính sách.
3. **Chạy tests**: `./gradlew clean test bootJar` hoặc `./mvnw clean verify`.
4. **Xác minh archive**: `jar tf` thấy `layers.idx`, JAR tools có thể `list-layers` và extract thành công.
5. **Build OCI image từ đúng executable JAR** vừa test; không copy nhầm `-plain.jar`.
6. **Quan sát cache**: giữ logs của Docker build, ghi rõ những bước `COPY` có/không reuse.
7. **Smoke test image**: chạy container và gọi `GET /version`.
8. **Scan/SBOM**: kiểm tra vulnerabilities và licenses theo policy; layering không miễn bước này.
9. **Publish by immutable digest**: gắn tag có ý nghĩa, ghi digest, đẩy image lên registry có quyền.
10. **Deploy đúng digest đã test**, không rebuild lại với dependencies động vào phút cuối.

### 16.2. Lưu ý CI runner sạch

Trên một runner hoàn toàn mới, build cache Docker có thể trống; hai builds trên hai runner khác nhau có thể **không** reuse cache trừ khi cấu hình export/import tới registry/remote BuildKit cache hoặc sử dụng builder bền vững.

Ví dụ cơ chế BuildKit `buildx` hỗ trợ cache export/import thông qua registry, nhưng cú pháp/chính sách dùng phụ thuộc provider và quyền registry. Không nên đưa lệnh push cache chứa dữ liệu nhạy cảm vào pipeline chỉ vì muốn hiện chữ `CACHED`.

### 16.3. Base image cũng là một input

`FROM eclipse-temurin:17-jre` là một **tag di chuyển được**; khi tag trỏ tới image mới, parent image layers/digest có thể đổi, kéo theo invalidate cache. Với release reproducibility và security, cân nhắc pin image bằng **digest cụ thể** được tổ chức kiểm tra, và có quy trình cập nhật digest định kỳ để nhận bản vá.

**Đừng giữ base image mãi mãi chỉ để có cache hit.** Các bản vá hệ điều hành/JRE quan trọng hơn việc tránh rebuild; đo cache efficiency sau khi bạn đã có chính sách nâng base image phù hợp.

## 17. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Không thấy `BOOT-INF/layers.idx` | Build bằng plain `jar`, layering bị disable hoặc artifact cũ | Chạy `bootJar`; kiểm tra `layered.enabled` và đúng file |
| `java -Djarmode=tools` báo không có mode | Plugin/Boot version cũ, `includeTools=false` hoặc build sai JAR | Kiểm tra Spring Boot 3.3, `spring-boot-jarmode-tools` trong archive |
| `tools extract` không chạy trên JAR có launch script | Fully executable archive với prepended shell script | Tắt `launchScript()` cho artifact định extract |
| `layertools` có hướng dẫn khác `tools` | Tài liệu của Boot 2.x/đầu 3.x khác 3.3 | Dùng `-Djarmode=tools ... extract --layers` của Boot 3.3 |
| Docker COPY không tìm thấy extracted/dependencies | Extract chưa chạy, path stage sai hoặc layer name đã custom | Kiểm tra builder-stage filesystem và `list-layers` |
| Chỉ thấy một Docker layer cho app | Dockerfile `COPY` nguyên fat JAR | Dùng tools extract và các `COPY --from` tách biệt |
| Layer dependencies vẫn thay khi chỉ sửa Controller | Dynamic/SNAPSHOT dependency, generated metadata hoặc artifact rebuild không ổn định | So sánh extracted dependencies bytes/checksum và dependency graph |
| Docker không hiện `CACHED` sau rebuild | Builder/cache mới, `--no-cache`, base image mới, context/instruction đổi | Kiểm tra `docker build --progress=plain`, cache store, `FROM` digest |
| Final container không chạy được `application.jar` | COPY thiếu một nhóm, sai entrypoint/extracted layout | Đối chiếu Dockerfile với Boot 3.3 docs, chạy image và xem stack trace |
| Port không truy cập được | Container chưa startup, host port không map, app chỉ lắng nghe port khác | Kiểm tra log và `docker run -p HOST:8080` |
| Hash image đổi khi mã đổi | Layer application đổi là đúng; manifest/digest mới | So sánh riêng digest của layers ổn định, không yêu cầu cả image digest bất biến |
| Runtime lỗi ClassNotFound | Thiếu nested JAR khi extract/copy hoặc dependency đã bị loại khỏi artifact | Kiểm tra `BOOT-INF/lib`, extracted folders và dependency graph |
| Muốn loại JAR khỏi image nhưng chỉ cấu hình layer include/exclude | Layer DSL đổi phân nhóm chứ không nhất thiết loại artifact | Sửa dependency graph/bootJar classpath, scan artifact |
| Buildpacks image khác Dockerfile image | Hai builders có cách chia lớp/base image và launch khác nhau | Không so output như cùng pipeline; kiểm tra từng flow |
| Docker image size không giảm | Layering nhằm reuse/lưu truyền bytes, không xóa dependencies | Đánh giá module dependencies, image base và startup riêng |
| CI test pass nhưng runtime fail | CI test dùng classpath Gradle, chưa chạy container thật | Thêm container smoke test và giữ đúng image digest |
| Snapshot dependency khiến cache thường miss | `SNAPSHOT` có thể đổi trong repository | Dùng released/locked versions khi phù hợp và kiểm tra provenance |
| Lộ secret trong image | Credentials được COPY vào một layer hoặc build args chứa secret | Dùng secret mount/runtime secret manager, rà image history |

### Các bước điều tra có thứ tự

1. Đọc version `./gradlew --version` và Spring Boot plugin; xác nhận ví dụ đang dùng Boot 3.3 compatible.
2. Chạy `jar tf` và kiểm tra `BOOT-INF/layers.idx`, `BOOT-INF/lib`, Boot loader và tools dependency.
3. Chạy `java -Djarmode=tools -jar ... list-layers` để đọc đúng tên layer thực tế.
4. Extract ra thư mục mới, đối chiếu file trong từng layer và cấu trúc `application.jar`.
5. Kiểm tra Dockerfile có đúng `COPY --from=extractor` theo thứ tự không.
6. Chạy `docker build --progress=plain`, đọc bước nào reused/miss.
7. Nếu dependencies layer đổi, so sánh file/checksum ở extracted dependencies và dependency graph; không suy luận chỉ từ filename.
8. Chạy container và HTTP smoke test trước khi khẳng định tối ưu thành công.
9. Khi có lỗi, rollback về JAR/image đã test; không bỏ kiểm thử để ép container cache hit.

## 18. Kiểm chứng cache có bằng chứng thay vì chỉ đoán

**Bài thử nghiệm A/B** cần thu thập ít nhất:

| Quan sát | Build A (Controller v1) | Build B (Controller v2) | Ý nghĩa |
| --- | --- | --- | --- |
| Spring Boot `layers.idx` | Có 4 tên layer mặc định | Vẫn có 4 tên | Layer metadata được tạo |
| `dependencies` content | Hash/list baseline | Không đổi nếu dependencies giữ nguyên | Nhóm thư viện release ổn định |
| `spring-boot-loader` content | Hash/list baseline | Không đổi nếu Boot giữ nguyên | Launcher ổn định |
| `snapshot-dependencies` | Có thể trống | Thường không đổi trong demo | Chưa có SNAPSHOT mới |
| `application` content | Chứa `layer-v1` | Chứa `layer-v2` | Đúng lớp thay đổi |
| Docker build logs | Các COPY tạo output lần đầu | Ba COPY đầu có thể reused; application mới | Cache tác động tới image build |
| HTTP smoke test | `layer-v1` | `layer-v2` | Image cuối chạy đúng code |

Một phép đo tốt nên so sánh **digest các OCI layers** hoặc log Docker builder, không chỉ tổng thời gian build. Lần đầu có network/download, lần sau có cache và file hệ thống nóng sẽ làm thời gian khác nhau theo nhiều nguyên nhân.

**Tính chính xác của Docker cache** khác với performance: một bước COPY bị cache lại khi inputs giữ nguyên là hợp lệ; khi image code đổi, build phải có một **new application layer** hoặc kết quả tương đương cập nhật. Tối ưu thành công là **không tái tạo những layer ổn định không cần thiết**, đồng thời vẫn đưa đúng code và dependency vào image.

## 19. Checklist và bài thực hành

1. Xác nhận project là Spring Boot **3.3.x** với Java 17 và Wrapper đúng. Nếu dùng Boot khác, đọc tài liệu plugin đúng phiên bản.
2. Tạo `LayerDemoApplication`, `VersionController` và test như mục 7.
3. Khai báo `bootJar { layered { enabled = true }; includeTools = true }` khi muốn ý định rõ ràng; biết rằng 3.3 đã có default layering.
4. Chạy `clean test bootJar`; xác minh file `BOOT-INF/layers.idx` trong **đúng Boot JAR**.
5. Chạy `-Djarmode=tools ... list-layers` rồi `extract --layers --destination ...`; quan sát các thư mục.
6. Tạo Dockerfile multi-stage copy đúng bốn nhóm theo thứ tự mặc định.
7. Build image `layer-demo:one`, chạy container và xác nhận `GET /version` trả `layer-v1`.
8. Sửa Controller/test sang `layer-v2` mà không thay dependency; build image `layer-demo:two` và xác nhận response mới.
9. Đọc Docker build logs, xác nhận cache có cơ hội giữ `dependencies`/loader và chỉ thay application ở bước COPY cuối.
10. Thử sửa một dependency và ghi nhận vì sao cache layer sớm bị invalidated là đúng.
11. So sánh với Dockerfile copy nguyên JAR; giải thích vì sao nó không thấy các nhóm Spring Boot bên trong.
12. Phân biệt Gradle Build Cache, Docker Build Cache, image registry blob reuse và `layers.idx`.
13. Kiểm tra image theo policy tổ chức: base image digest, runtime user, vulnerability scan, secrets, test report và image digest.
14. Ghi lại artifact source commit, lệnh build, Boot/Gradle/JDK version, ảnh chụp/log cache và kết quả smoke tests.
15. Khôi phục code/test/dependencies của project thật trước khi kết thúc.

**Hoàn thành bài khi:** bạn tự trả lời được vì sao việc chỉ sửa Controller làm fat JAR thay đổi, `layers.idx` chứa thông tin gì, bốn layer mặc định được sắp xếp theo tiêu chí nào, **tại sao Dockerfile phải COPY các nhóm riêng**, và làm thế nào chứng minh Docker reuse dependencies layer nhưng image mới vẫn chạy đúng API.

## Tài liệu chính thức

- [Spring Boot 3.3 – Gradle Plugin: Packaging Layered Jar or War](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 – Maven Plugin: Layered Jar or War](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 – Efficient Container Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/efficient-images.html)
- [Spring Boot 3.3 – Dockerfiles with JAR Tools](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/oci-image.html)
- [Spring Boot 3.3 Release Notes – JAR Tools Mode](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes)
- [Docker Docs – Build Cache Overview](https://docs.docker.com/build/cache/)
- [Docker Docs – Build Cache Invalidation](https://docs.docker.com/build/cache/invalidation/)
- [Docker Docs – Optimize Build Cache](https://docs.docker.com/build/cache/optimize/)
- [OCI Image Format Specification](https://github.com/opencontainers/image-spec)
