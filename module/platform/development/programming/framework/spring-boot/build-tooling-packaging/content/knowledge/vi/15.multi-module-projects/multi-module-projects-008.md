# Đóng gói phụ thuộc nội bộ cùng các thư viện bắc cầu cần thiết trong dự án Spring Boot đa mô-đun

## 1. Bài toán: ứng dụng chạy được phải mang theo toàn bộ chuỗi phụ thuộc runtime

Một repository Spring Boot thường gồm nhiều module: một module `app` chịu trách nhiệm khởi động HTTP server hoặc batch job, một hoặc nhiều module `core`, `domain`, `persistence`, `adapter` chứa nghiệp vụ hoặc mã dùng chung. Mỗi module lại có thể phụ thuộc vào thư viện bên ngoài. **Khi xuất bản executable JAR**, ứng dụng không chỉ cần mã của chính `app` mà còn phải có **các module nội bộ và các thư viện bắc cầu cần ở runtime**.

Xét đồ thị tối thiểu:

~~~text
multi-module-demo
├── core                  (Java library nội bộ)
│   └── commons-lang3     (thư viện ngoài, core gọi trực tiếp)
└── app                   (Spring Boot application)
    ├── core              (app gọi public API của core)
    │   └── commons-lang3 (phụ thuộc bắc cầu cần khi core thực thi)
    └── spring-boot-starter-web
        └── Spring MVC / embedded server / logging / ...
~~~

Nếu `app` chỉ đóng `app` classes mà **bỏ `core.jar`**, JVM không tìm được `com.example.core.GreetingComposer`. Nếu có `core.jar` nhưng **bỏ `commons-lang3.jar`**, ứng dụng có thể nạp lớp `GreetingComposer` nhưng lỗi khi chạy method thực sự dùng `org.apache.commons.lang3.StringUtils`. Cả hai đều là lỗi **runtime classpath**, không nhất thiết lộ ra ở bước biên dịch hoặc một bài test không đi qua code path đó.

**Mục tiêu của bài:** từ một nguồn project đa mô-đun, xác định đúng **phụ thuộc trực tiếp nội bộ** (`app → core`), **phụ thuộc bắc cầu** (`core → commons-lang3`), đưa chúng vào executable JAR của module app, và chứng minh cả **cấu trúc archive lẫn hành vi thực** đều đúng.

Các ví dụ dùng **Java 17, Spring Boot 3.3.13, Maven hoặc Gradle** với bộ cấu hình có chủ đích cho mục đích học tập; đây không phải tuyên bố phiên bản mới nhất. Lệnh và file cần được người học chạy ở môi trường có JDK/Wrapper, truy cập repository và các điều kiện phù hợp. Không coi output dự kiến là log đã đo sẵn.

### Kết quả học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **multi-module build graph**, **dependency graph** và **runtime archive classpath**.
2. Để module library sinh **plain JAR**, còn chỉ module app sinh **Spring Boot executable JAR**.
3. Cấu hình Maven reactor `<modules>`, dependency tới `core` và Spring Boot `repackage` mà không repackage nhầm library.
4. Cấu hình Gradle `include('core', 'app')`, `implementation project(':core')`, `java-library` và `bootJar`.
5. Giải thích Maven transitive dependency/scopes và Gradle `api` versus `implementation` cho library consumers.
6. Dùng `dependency:tree`, `dependencies`, `dependencyInsight` và `jar tf` để đối chiếu graph thực tế với file ở `BOOT-INF/lib`.
7. Kiểm tra `java -jar` và endpoint có chạy qua code của `core`, không chỉ thử một endpoint không dùng dependency.
8. Chẩn đoán thiếu artifact nội bộ, thiếu transitive library, lệch version, `compileOnly`/`test`/`optional` và nhầm executable/plain JAR.

## 2. Ba đồ thị liên quan nhưng không đồng nhất

### 2.1. Đồ thị module của build

**Maven** biết các module nào cùng reactor qua `<modules>` ở aggregator POM. **Gradle** biết subprojects qua `include(...)` ở `settings.gradle`. Cấu trúc này giúp build tool lựa chọn và sắp xếp việc build các module, nhưng **không tự định nghĩa dependency từ `app` tới `core`**.

Ví dụ Maven root có:

~~~xml
<modules>
    <module>core</module>
    <module>app</module>
</modules>
~~~

hoặc Gradle settings:

~~~groovy
include('core', 'app')
~~~

Tự riêng hai đoạn đó **chưa khiến `app` dùng được `core`**. Module app vẫn phải **khai báo dependency** bằng đúng tọa độ Maven hoặc Gradle project dependency.

### 2.2. Đồ thị dependency

Sau khi khai báo `app → core` và `core → commons-lang3`, build tool giải quyết **toàn bộ đường đi** theo metadata, scope/configuration, constraints, BOM, exclusions, version conflict và project variants.

~~~mermaid
flowchart LR
    A["app (Spring Boot)"] --> C["core (internal library)"]
    C --> L["commons-lang3 (external library)"]
    A --> W["spring-boot-starter-web"]
    W --> S["Spring MVC + embedded Tomcat + other runtime deps"]
~~~

- **Direct dependency của app:** `core` và `spring-boot-starter-web`.
- **Transitive dependency qua core:** `commons-lang3`.
- **Resolved version:** là version cuối được chọn bởi build tool, có thể khác requested version nếu graph có BOM/constraints/conflict resolution.
- **Được đóng vào executable JAR hay không:** còn phụ thuộc scope, runtime configuration và bước đóng gói của Spring Boot plugin.

Một entry trong Maven `dependencyManagement` hoặc Gradle version catalog chỉ quản lý cách khai báo/version, **không tự thêm một dependency mới vào graph**.

### 2.3. Đồ thị runtime classpath của sản phẩm

Một executable Spring Boot JAR thường có layout:

~~~text
app-1.0.0-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...    (Boot Loader)
└── BOOT-INF/
    ├── classes/
    │   └── com/example/app/MultiModuleApplication.class
    └── lib/
        ├── core-1.0.0-SNAPSHOT.jar
        ├── commons-lang3-<resolved-version>.jar
        ├── spring-boot-<resolved-version>.jar
        ├── spring-webmvc-<resolved-version>.jar
        └── ... (các thư viện runtime khác)
~~~

**Hai sự thật quan trọng:**

- Mã `app` nằm dưới `BOOT-INF/classes`; module nội bộ `core` thường nằm như **một nested `core.jar` trong `BOOT-INF/lib`**, không bị gộp trực tiếp vào `BOOT-INF/classes`.
- `commons-lang3` nằm ở `BOOT-INF/lib` **dù app không khai báo nó trực tiếp**, miễn là transitive dependency đó được giữ trong resolved runtime graph của app và không bị loại bởi packaging rules.

Java không tự động coi `BOOT-INF/lib/*.jar` của một ZIP ngoài là classpath. Spring Boot Loader khởi động qua manifest (`Main-Class`) và dựng classpath gồm app classes + nested libraries trước khi gọi `Start-Class`. Đây là điểm khác biệt so với plain JAR.

**Không nhầm “có dependency trong build cache” với “có trong archive”.** Maven local repository/Gradle cache chỉ giữ các file phục vụ build; cuối cùng phải kiểm tra **chính file app JAR** được bàn giao.

## 3. Thiết kế module: chỉ ứng dụng mới có Boot entrypoint

Trong demo có hai modules:

| Module | Kiểu build | Cung cấp | Nên tạo sản phẩm nào? |
| --- | --- | --- | --- |
| `core` | Maven `jar` hoặc Gradle `java-library` | `GreetingComposer` và dependency xử lý chuỗi | **Plain library JAR** để app và project khác tiêu thụ. |
| `app` | Spring Boot application | `@SpringBootApplication`, REST `/ping`, dependency tới core | **Spring Boot executable JAR** có `BOOT-INF/classes` và `BOOT-INF/lib`. |
| Root | Maven aggregator `pom` / Gradle settings + root build | Quản lý module/plugin/version/repositories | Không phải ứng dụng, không cần executable JAR. |

**Phản ví dụ:** áp `spring-boot-maven-plugin` cùng goal `repackage` hoặc Gradle `org.springframework.boot` lên **mọi library module**, rồi dùng boot-repackaged `core.jar` như dependency của app. Một Boot executable JAR đặt classes ở `BOOT-INF/classes` thay vì package paths root như library JAR chuẩn; consumer Java/Maven/Gradle không tự coi layout đó là library classpath thông thường. Hậu quả có thể là `package com.example.core does not exist` dù bạn nhìn thấy `GreetingComposer.class` bên trong file.

Quy tắc thực hành: **core tạo plain JAR; app tạo Boot JAR**. Nếu một module phải vừa publish thư viện vừa có executable variant riêng, phải tách rõ **classifier/variant/artifact** để người tiêu thụ lấy đúng plain library artifact; không biến artifact library mặc định thành Boot JAR mà không kiểm tra consumer metadata.

### 3.1. Bao giờ nên có module riêng?

Một library đáng tách khi nó có trách nhiệm ổn định, API công khai rõ ràng, có thể test độc lập và tái sử dụng hợp lý. Không cần tách mỗi class thành một module. Quá nhiều module làm dependency graph, build configuration và release governance phức tạp hơn.

### 3.2. Không coi root aggregator là dependency của mọi module

Maven `<parent>` giúp kế thừa settings/plugin/dependency management; `<modules>` quyết định aggregation; `<dependencies>` mới thêm thư viện. Gradle `include(...)` quyết định project membership; `implementation(project(':core'))` mới thêm dependency. **Parent và aggregator không thay thế khai báo dependency.**

## 4. Ví dụ Java 17 dùng cùng source cho Maven và Gradle

Cây thư mục:

~~~text
multi-module-demo/
├── pom.xml                          # Maven root aggregator, nếu chọn Maven
├── settings.gradle                  # Gradle root, nếu chọn Gradle
├── build.gradle                     # Gradle root, nếu chọn Gradle
├── core/
│   ├── pom.xml                      # Maven, nếu chọn Maven
│   ├── build.gradle                 # Gradle, nếu chọn Gradle
│   └── src/main/java/com/example/core/GreetingComposer.java
└── app/
    ├── pom.xml                      # Maven, nếu chọn Maven
    ├── build.gradle                 # Gradle, nếu chọn Gradle
    ├── src/main/java/com/example/app/MultiModuleApplication.java
    └── src/test/java/com/example/app/MultiModuleApplicationTest.java
~~~

**Chọn một build tool cho lần thực hành:** Maven cần Maven Wrapper (`mvnw`, `mvnw.cmd`, `.mvn/wrapper`); Gradle cần Gradle Wrapper (`gradlew`, `gradlew.bat`, `gradle/wrapper`). Bài trình bày hai cấu hình song song để so sánh, không yêu cầu project thực tế duy trì hai build pipelines.

### 4.1. Module core gọi thư viện ngoài

`core/src/main/java/com/example/core/GreetingComposer.java`:

~~~java
package com.example.core;

import org.apache.commons.lang3.StringUtils;

public final class GreetingComposer {

    private GreetingComposer() {
    }

    public static String message() {
        return StringUtils.capitalize("from core");
    }
}
~~~

Giải thích:

- API public của `core` là `String message()`, trả **chuỗi Java tiêu chuẩn**.
- Việc dùng `StringUtils.capitalize` của **Apache Commons Lang 3** là **chi tiết triển khai nằm trong method body**, không xuất hiện trong public method signature.
- Khi method chạy, JVM cần class `org.apache.commons.lang3.StringUtils`. Vì thế `commons-lang3` phải có trong runtime dependency graph của app.
- Với input chính xác `"from core"`, `StringUtils.capitalize` trả `"From core"`. Class này không có entrypoint `main()` và không tự chạy bằng `java GreetingComposer`; nó là thư viện để ứng dụng gọi.

### 4.2. Module app gọi core

`app/src/main/java/com/example/app/MultiModuleApplication.java`:

~~~java
package com.example.app;

import com.example.core.GreetingComposer;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class MultiModuleApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiModuleApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "hello " + GreetingComposer.message();
    }
}
~~~

Khi `GET /ping` đi qua app, luồng thực thi:

~~~text
HTTP GET /ping
  -> MultiModuleApplication.ping()   (app module)
  -> GreetingComposer.message()      (core module)
  -> StringUtils.capitalize(...)     (commons-lang3 transitive dependency)
  -> HTTP 200 / "hello From core"
~~~

Đây là **phép thử tốt hơn** một `/ping` trả literal trong app mà không gọi core: nếu runtime thiếu `core` hoặc `commons-lang3`, request sẽ thất bại và báo lỗi phù hợp. Khi chỉ test startup mà không chạm dependency, thiếu class có thể bị bỏ sót.

### 4.3. App test bằng JUnit + MockMvc

`app/src/test/java/com/example/app/MultiModuleApplicationTest.java`:

~~~java
package com.example.app;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MultiModuleApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void applicationUsesCoreAndTransitiveLibrary() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("hello From core"));
    }
}
~~~

Test dùng **Spring test context và MockMvc**, không mở HTTP port thật. Nó chứng minh app/core cùng hoạt động trên **test runtime classpath**. Nó **không thay thế** phép thử `java -jar` vì test classpath có thể rộng hơn classpath của archive. Một pipeline tốt sẽ kiểm tra cả test report lẫn **executable JAR**.

## 5. Maven: ba POM, một reactor, đúng dependency scopes

### 5.1. Root `pom.xml`: aggregator và parent của hai module

Tạo `multi-module-demo/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>multi-module-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
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

**Điểm chính:**

- `<packaging>pom</packaging>` là bắt buộc cho POM đóng vai trò aggregator kiểu này.
- `<modules>` liệt kê hai module để Maven reactor biết thứ tự build theo dependency, không tự động gắn thêm `core` vào app.
- Parent `spring-boot-starter-parent` giúp root và các con kế thừa dependency/plugin management phù hợp Spring Boot 3.3.13.
- Root **không** khai báo `spring-boot-maven-plugin` trong `<build><plugins>`. Nhờ đó, không tự áp dụng goal `repackage` cho root hoặc core.
- Đây là cấu hình minh họa dùng Boot starter parent. Trong tổ chức dùng corporate parent và import BOM, cần thiết lập compiler/JDK, plugin versions và `repackage` riêng; BOM không tự cho toàn bộ build defaults.

### 5.2. `core/pom.xml`: chỉ tạo library JAR

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>multi-module-demo</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</project>
~~~

- `core` không áp dụng Spring Boot Maven plugin, nên `mvn package` tạo **plain `core-1.0.0-SNAPSHOT.jar`** với class ở `com/example/core/...` ngay dưới root JAR.
- `commons-lang3` có Maven scope mặc định `compile`, do đó là **dependency transitively visible** theo Maven dependency graph, không phải `test`/`provided`/`system`.
- Version `3.14.0` là **requested version** của riêng khai báo ví dụ. Khi app có dependency management/BOM hoặc một đường dependency khác, **selected version** ở graph cuối có thể khác. Đừng viết một assertion yêu cầu chính xác `commons-lang3-3.14.0.jar` mà chưa đọc dependency tree.
- Vì code `GreetingComposer` trực tiếp dùng `StringUtils` lúc compile, không nên đổi khai báo Commons Lang sang `runtime` scope của Maven: `core` sẽ thiếu class lúc compile.

### 5.3. `app/pom.xml`: Boot JAR và dependency nội bộ trực tiếp

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>multi-module-demo</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <!-- Dependency nội bộ: app thực sự gọi class thuộc core -->
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>

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
            <!-- Chỉ application module mới có Spring Boot repackage -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Cơ chế đóng gói:**

1. Maven reactor xây `core` trước `app` vì app khai báo dependency tới `core` cùng build.
2. `core` xuất plain library JAR, không Boot-repackage.
3. `app` compile với `core` và Spring MVC từ starter.
4. App runtime dependency graph có `core`; `core` kéo theo `commons-lang3` qua Maven transitivity/scope, trừ khi bị exclusions, optional hoặc dependency management thay đổi.
5. Khi `mvn package` tạo app JAR, Spring Boot plugin `repackage` đóng nó thành executable archive với `BOOT-INF/classes` và các runtime libraries ở `BOOT-INF/lib`.
6. `spring-boot-starter-test` thuộc test scope nên **không** được đưa vào Boot runtime archive theo layout thông thường.

`${project.version}` trong dependency app là Maven expression, có giá trị `1.0.0-SNAPSHOT` được kế thừa. Nó dùng để giữ phiên bản core nhất quán với reactor trong ví dụ; các đội lớn có thể quản lý module versions bằng `dependencyManagement`, BOM nội bộ hoặc CI versioning, nhưng phải đảm bảo coordinate của app trỏ đúng artifact core.

### 5.4. Build Maven từ root reactor

Từ thư mục root, với Maven Wrapper đã được lưu:

~~~bash
# Kiểm tra Maven/JDK
./mvnw -version

# Chỉ chọn app và tất cả reactor modules mà app cần
./mvnw -pl app -am clean verify

# Hoặc build toàn bộ reactor
./mvnw clean verify
~~~

Ý nghĩa:

- `-pl app`: chọn module `app`.
- `-am`: thêm các **reactor projects cần để build app**, ví dụ `core` (và aggregator).
- Maven sắp xếp các project phù hợp theo dependency graph. `-am` chỉ có tác dụng với module **cùng reactor**, không tự tìm source code của một library bên ngoài repo.
- `clean verify` chạy lifecycle thích hợp, gồm compile, test, package và repackage của **app**, nhưng **không** Boot-repackage `core` vì core không khai báo Boot plugin.

**Lỗi thường gặp:** chạy `./mvnw -f app/pom.xml clean package` khi `core` chưa được cài vào local Maven repository. Child POM có thể tìm được parent qua `relativePath`, nhưng binary dependency `com.example:core` vẫn cần resolve. Chạy từ root với `-pl app -am` sẽ dùng reactor; hoặc `install` library/parent hợp lệ trước nếu chạy module đơn.

### 5.5. Chạy Maven goal ở đúng module

Để thử app qua `spring-boot:run` trong cấu hình nhiều module:

~~~bash
# Chuẩn bị các reactor artifacts vào local Maven repository nếu cần
./mvnw -pl app -am install

# Sau đó gọi run goal chỉ ở app module
./mvnw -pl app spring-boot:run -Dspring-boot.run.arguments="--server.port=18085"
~~~

Không máy móc dùng `./mvnw -pl app -am spring-boot:run`: nhiều plugin goals được thực thi cho **mọi project đã chọn**, khiến Maven cố chạy Boot app goal ở `core` không có main class. Với `mvn clean verify`, các plugin goals đã bind đúng module/lifecycle nên đây không phải vấn đề.

Với development run ở local đã có core dependency trong repository, app có thể gọi trực tiếp. Khi core SNAPSHOT thay đổi, cần bảo đảm repo local phản ánh bản mới hoặc dùng quy trình reactor để không chạy nhầm code cũ.

## 6. Maven transitivity: khi nào Commons Lang được kéo theo?

Giả sử app có:

~~~text
app --compile--> core --compile--> commons-lang3
~~~

Trong Maven dependency mechanism, transitive dependencies có thể đi theo dependency graph qua nhiều cấp. Nhưng scope và metadata ảnh hưởng việc chúng xuất hiện trong compile/runtime/test classpath của app.

| Trường hợp ở module `core` | Có ảnh hưởng gì tới `app`? | Hậu quả cần biết |
| --- | --- | --- |
| `commons-lang3` mặc định `compile`, không optional/excluded | Thường có trên app compile/runtime transitive classpath. | `core` dùng được `StringUtils` khi app chạy. |
| `commons-lang3` `runtime` | Có thể tới app runtime, nhưng **core dùng nó để compile** nên cấu hình core này không phù hợp. | Core compile có thể fail nếu không có một đường khác cung cấp class. |
| `commons-lang3` `test` | Chỉ dành cho test của core, không là runtime transitive dependency của app. | Core production source dùng class sẽ không compile đúng. |
| `commons-lang3` `provided` | Maven core compile/test có dependency nhưng không được truyền như compile/runtime transitive của app theo luật Maven thông thường. | App Boot runtime có thể thiếu thư viện khi core method chạy. |
| `commons-lang3` `optional=true` ở core | Consumer như app **không tự kéo** optional dependency qua core. | Nếu app thực sự cần nó khi gọi core, app phải khai báo dependency phù hợp hoặc sửa metadata của core. |
| App áp `<exclusions>` cho `commons-lang3` ở dependency core | Bỏ transitive dependency trên đường từ core. | JAR vẫn có core nhưng có thể thiếu Commons khi chạy. |

**Phân biệt provided của Maven với cấu hình Spring Boot packaging:** Boot Maven Plugin có các quy tắc riêng khi xét direct `provided` dependencies để đóng executable archive. Không vì thế mà bạn được giả định **mọi `provided` dependency sâu trong core** luôn transitively xuất hiện ở app. Dependency resolution của Maven xảy ra trước; nếu graph app không có Commons thì repackage không thể tự suy ra cần nó chỉ bằng cách quét bytecode.

### 6.1. `optional` không giống `exclude`

`optional=true` trên một dependency khai báo trong **core** nói với project tiêu thụ rằng đây là một dependency có thể không cần trong tất cả trường hợp. Nó thường **không được kéo qua đường transitive**. Nếu feature của core là bắt buộc mỗi khi app chạy, để optional là sai hợp đồng.

`<exclusions>` ở app lại là chủ động bỏ một transitive dependency trên đường dependency cụ thể; nếu cùng artifact đến từ đường khác nó vẫn có thể xuất hiện. Việc bỏ dependency khỏi graph khác với **chỉ loại dependency khỏi archive trong Spring Boot repackage**.

### 6.2. Không dùng `dependencyManagement` để “thêm Commons”

Ví dụ app có version được quản lý trong root POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **mảnh minh họa**, không có trong root POM tối thiểu ở mục 5. `dependencyManagement` chọn version cho dependency mà graph thực sự chứa; **không tự tạo dependency** nếu không có declaration/transitive path. Nếu app đã loại Commons bằng exclusions/optional và thiếu runtime library, thêm version management một mình không chữa lỗi.

### 6.3. Trường hợp cùng thư viện nhiều version

Nếu app trực tiếp hoặc qua starter nhận một version Commons Lang khác với version core khai báo, Maven có **dependency mediation** và dependency management precedence. Bạn phải đọc output `dependency:tree -Dverbose` hoặc `dependency:tree` theo phiên bản Maven Dependency Plugin thực tế, rồi xác định version được chọn. Với ví dụ `StringUtils.capitalize`, API lâu đời giúp demo dễ hiểu nhưng **không có quy tắc rằng mọi thay đổi version đều binary-compatible**.

## 7. Gradle: project dependency và `java-library` variants

Với Gradle, root settings xác định những subprojects tham gia build; `java-library` phân biệt **API mà consumer cần để compile** với **chi tiết triển khai nội bộ mà consumer chỉ cần ở runtime**.

### 7.1. Root `settings.gradle`

~~~groovy
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

rootProject.name = 'multi-module-demo'
include('core', 'app')
~~~

- `include('core', 'app')` đăng ký modules, không tự tạo `app → core`.
- `dependencyResolutionManagement.repositories` cho các subprojects truy cập Maven Central.
- `pluginManagement.repositories` phục vụ plugin resolution.
- Nếu doanh nghiệp dùng repository mirror/nội bộ, thay đúng repositories theo chính sách; không bỏ xác thực hoặc thêm mirror không được duyệt.

### 7.2. Root `build.gradle`: quản lý plugin versions, chưa áp cho mọi module

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}
~~~

`apply false` làm root biết cách resolve những plugin IDs/versions cho subprojects, nhưng **không bật `bootJar` ở root**. App sẽ chủ động apply; core thì không. Với multi-module, đây thường tốt hơn việc `subprojects { apply plugin: 'org.springframework.boot' }` áp Boot cho mọi thư viện.

**Lưu ý:** `java`/`java-library` là Gradle core plugins và không cần version. Plugin version của Spring Boot được khai báo ở root cho bài học, các module app khai báo ID không kèm version.

### 7.3. `core/build.gradle`: thư viện nội bộ

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Vì `GreetingComposer.message()` chỉ trả `String`, class Commons Lang **không xuất hiện trong API public**. `implementation` là lựa chọn đúng:

- Khi compile `core`, Gradle có Commons Lang.
- Khi compile `app` dựa trên `core`, Gradle không cần lộ Commons Lang lên app compile classpath chỉ vì core dùng nó nội bộ.
- Khi chạy `app`, module core **vẫn cần** Commons Lang; Gradle variant `runtimeElements` của core mang `implementation` dependencies tới consumer runtime graph.
- Khi đóng `:app:bootJar`, `core.jar` và Commons Lang được resolve làm runtime libraries (nếu graph không bị thay đổi/excluded).

**Không biến `core` thành Spring Boot application module** chỉ để được hưởng dependency management plugin. Commons Lang trong core ví dụ có version trực tiếp, và Boot starter dependency versions ở app được quản lý theo Boot plugin/dependency-management đã khai báo. Nếu tổ chức muốn quản lý tất cả versions tập trung, dùng version catalog, platform/BOM, dependency constraints hoặc convention plugin nhưng vẫn giữ đúng scope/configuration.

### 7.4. `app/build.gradle`: app dependency tới `:core`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

group = 'com.example'
version = '1.0.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // Phụ thuộc trực tiếp tới project core trong cùng Gradle build
    implementation project(':core')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là build script hoàn chỉnh để dùng cùng source ở mục 4:

- `implementation project(':core')` là **project dependency**; Gradle biết producer tasks/artifacts cần thiết và nối task graph phù hợp.
- `spring-boot-starter-web` là ứng dụng Servlet Spring MVC và embedded Tomcat trong ví dụ.
- `io.spring.dependency-management` phối hợp Spring Boot plugin để quản lý versions phù hợp cho starters/test libs.
- JUnit/MockMvc trong test source, không thuộc runtime artifact thông thường.
- `bootJar` chỉ có ý nghĩa ở app; `core` vẫn có Java library `jar`, không phải executable Boot JAR.

Khi core và app dùng cùng Gradle toolchain/bộ plugin conventions, hãy đảm bảo versions phù hợp ở **cả hai module**. Ví dụ đặt Java 17 tường minh cho từng module để code tự chứa; project lớn có thể chuyển quy tắc toolchain vào convention plugin chung.

### 7.5. Gradle task graph không cần install core vào Maven local

~~~bash
# Từ root Gradle repository đã có Wrapper
./gradlew :app:build

# Chỉ tạo executable archive của app
./gradlew :app:bootJar

# Xem đồ thị task trước khi chạy thật
./gradlew :app:bootJar --dry-run
~~~

Gradle biết `:core` là **project dependency cùng build** và lấy artifact/output của core theo đúng variant. Bạn **không cần** chạy `publishToMavenLocal` để app nhận core trong cùng build. Nếu công ty tách `core` thành repository/published dependency, khi đó cần tọa độ/metadata/repository và version được publish, khác trường hợp project dependency.

**Đừng suy từ tên task `:core:jar` rằng mọi class core nằm trực tiếp trong `BOOT-INF/classes` của app**. BootJar thông thường đặt artifact core vào nested `BOOT-INF/lib/core-...jar`. Điều này vẫn làm classloader Spring Boot có thể tìm class nội bộ khi chạy.

## 8. Gradle `api` và `implementation`: xuất hiện ở compile và runtime khác nhau

Bộ plugin `java-library` hỗ trợ *API/implementation separation*. Hãy nhìn hai tình huống:

**Tình huống A — đúng với demo hiện tại:**

~~~java
// Public API chỉ dùng java.lang.String:
public static String message() {
    return org.apache.commons.lang3.StringUtils.capitalize("from core");
}
~~~

Commons Lang là **implementation detail**, nên ở `core/build.gradle`:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Khi `app` gọi `GreetingComposer.message()`, compiler của app không cần biết `StringUtils`. Nhưng khi app chạy, `core` vẫn nạp `StringUtils`, nên Commons Lang cần trên **app runtimeClasspath** và trong Boot JAR.

**Tình huống B — nếu public API trả một type của library ngoài:**

~~~java
// Chỉ là chữ ký minh họa về lộ type ra API.
// Giả sử ExternalType là public class từ một thư viện thứ ba:
public ExternalType compute();
~~~

Nếu type của thư viện ngoài thực sự xuất hiện trong public methods, fields, generic types hoặc base classes của core, consumer có thể cần type đó để **compile**; Gradle nên dùng `api` thay vì `implementation` khi thư viện cũng cần runtime:

~~~groovy
dependencies {
    api 'com.example:public-contract-library:1.0.0'
}
~~~

Đây là **mảnh minh họa**, không phải dependency có thật trong demo. Cách chọn `api` phụ thuộc ABI Java thực tế; nếu chỉ dùng thư viện trong private method body, vẫn ưu tiên `implementation` để giảm compile classpath và rebuild không cần thiết.

| Configuration của `core` | App compile classpath? | App runtime classpath? | Khi nào dùng? |
| --- | --- | --- | --- |
| `api` | Có, transitively exposed. | Có. | Type của dependency nằm trên API/public ABI của core. |
| `implementation` | Không lộ trực tiếp implementation dependency tới app compile classpath. | Có. | Chi tiết triển khai nội bộ, như Commons Lang của demo. |
| `runtimeOnly` | Không. | Có. | Library chỉ cần lúc chạy (driver, plugin runtime...), không dùng để compile source của core. |
| `compileOnly` | Không làm dependency runtime transitively available. | **Không**. | Compile-time API/annotation chưa cần ở runtime; nguy hiểm nếu code thực sự gọi class lúc chạy. |
| `testImplementation` | Không. | Không trong main runtime. | Test core, không phân phối cho app. |

**Lỗi thực tế:** đổi Commons Lang của `core` từ `implementation` sang `compileOnly` có thể khiến `core` compile thành công, `app` cũng compile/test trong một môi trường có classpath bổ sung, nhưng executable Boot JAR **thiếu Commons Lang** nếu không có đường dependency runtime khác. Kết quả có thể là `NoClassDefFoundError: org/apache/commons/lang3/StringUtils` khi gọi `/ping`. Không sửa bằng cách bỏ test hoặc copy thủ công JAR vào archive; sửa **dependency configuration**.

## 9. Đối chiếu compile/test/runtime ở Maven và Gradle

### 9.1. Phân loại theo nguồn của dependency

| Nguồn/thành phần | Khi compile app | Khi test app | Khi chạy packaged Boot JAR |
| --- | --- | --- | --- |
| Mã `app` production | Có. | Có. | Có, thường ở `BOOT-INF/classes`. |
| Mã `core` library nội bộ | Có nếu app khai báo core dependency đúng. | Có. | Có, thường trong `BOOT-INF/lib/core-...jar`. |
| Commons Lang, dependency core dùng trong method body | Maven compile transitively; Gradle implementation của core có thể **không lộ** ở app compile classpath. | Có trong app runtime test graph phù hợp. | Phải có ở runtime transitive dependency graph của app. |
| Spring MVC, Jackson, embedded web server | Theo starter và scopes. | Có để test context chạy. | Có các runtime JAR tương ứng. |
| `src/test/java` + JUnit + MockMvc test-only libs | Không thuộc main output. | Có. | **Không** theo packaging thông thường. |
| Build plugins: Maven/Gradle plugin implementation | Chạy lúc cấu hình/build. | Chạy theo build lifecycle. | Không tự là Spring application runtime dependencies. |

**Điểm tinh tế:** ở Maven, transitive `compile` scope thường làm consumer thấy implementation dependency ở compile. Ở Gradle `java-library`, `implementation` **không lộ ra consumer compile classpath** nhưng **vẫn truyền vào runtime**. Chúng đạt **cùng mục tiêu đóng runtime đầy đủ**, dù bề mặt compile khác nhau. Không chuyển mã Maven sang Gradle bằng cách đổi mọi `compile` thành `api` một cách máy móc.

### 9.2. Maven `provided` và Boot repackage

Khi một module trực tiếp dùng `provided`, luật Maven transitivity và lựa chọn package khác nhau theo tầng. Spring Boot Maven Plugin có quy tắc đặc biệt để đóng một số provided dependencies trong executable archives; tuy nhiên app **không thể** đóng một library không xuất hiện trong graph do metadata optional/exclusion không truyền tới. Quy trình an toàn là:

1. Xem `mvn dependency:tree` của **app**.
2. Kiểm tra scope của từng dependency và đường đưa nó vào graph.
3. Xem `jar tf app.jar` để xác nhận package output.
4. Chạy code path cần library sau khi dùng `java -jar`.

### 9.3. Phạm vi đúng cho dependency quản lý phiên bản

Spring Boot BOM quản lý version của rất nhiều Spring/third-party libraries; nó **không tự** thêm core vào app. Maven root `dependencyManagement` cũng không tự thêm project dependency. Gradle plugin/dependency-management/version catalog cũng không tự tạo `implementation project(':core')`. Những dòng quyết định relation vẫn là:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>core</artifactId>
    <version>${project.version}</version>
</dependency>
~~~

và:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

Nếu Maven parent và app cùng kế thừa dependency management nhưng app quên khai báo core, compiler sẽ báo thiếu package (trừ khi có một dependency khác vô tình kéo core). Đó là lỗi **khai báo dependency**, không phải lỗi `repackage`.

## 10. Kiểm chứng Maven: module order, dependency tree, archive và runtime

### 10.1. Bước 1 — kiểm tra reactor và build

~~~bash
./mvnw -version
./mvnw -pl app -am clean verify
~~~

**Kỳ vọng:**

- Reactor có root aggregator, `core` và `app` được chọn.
- Build `core` trước `app` theo dependency, tạo `core/target/core-1.0.0-SNAPSHOT.jar` dạng plain library JAR.
- App compile thành công khi import `com.example.core.GreetingComposer`.
- App JUnit/MockMvc test `applicationUsesCoreAndTransitiveLibrary` được phát hiện và pass.
- App Boot plugin tạo `app/target/app-1.0.0-SNAPSHOT.jar` executable.
- Test report app thường ở `app/target/surefire-reports/`. Không chỉ nhìn `BUILD SUCCESS`; xem số test thực chạy.

**Không dùng `mvn -pl app -am spring-boot:repackage` trực tiếp trên cả reactor** nếu library không được cấu hình tương ứng. Goal `repackage` cần JAR/WAR đã được tạo bởi `package`; root `pom`/core library không có cùng mục đích. `clean verify` với plugin chỉ khai báo trong app là cách rõ hơn.

### 10.2. Bước 2 — xem dependency graph của app

~~~bash
./mvnw -pl app -am dependency:tree
~~~

Tìm các phần sau trong cây output thực tế (format/ordering tùy Maven Dependency Plugin):

~~~text
com.example:app:jar:1.0.0-SNAPSHOT
+- com.example:core:jar:1.0.0-SNAPSHOT:compile
|  \- org.apache.commons:commons-lang3:jar:<resolved-version>:compile
\- org.springframework.boot:spring-boot-starter-web:jar:<resolved-version>:compile
   \- ... other dependencies ...
~~~

Đoạn trên là **mẫu diễn giải**, không phải output cam kết đã chạy. Dependency mediation có thể đổi version, Maven có thể hiển thị transitive dependencies theo thứ tự khác. Xem cả direct `core` và descendant `commons-lang3`; nếu chỉ thấy core mà không có Commons, điều tra `optional`, scope, exclusions hoặc dependency metadata.

Nếu muốn lọc theo nhóm và plugin version hỗ trợ:

~~~bash
./mvnw -pl app -am dependency:tree -Dincludes=com.example:core,org.apache.commons:commons-lang3
~~~

Khi dùng `-Dincludes` qua shell, giữ format đúng với Maven Dependency Plugin trong dự án; nếu lỗi filter hoặc cây rỗng, chạy lại `dependency:tree` không filter trước để xác nhận graph.

### 10.3. Bước 3 — đọc plain core JAR trước

~~~bash
jar tf core/target/core-1.0.0-SNAPSHOT.jar
~~~

**Kỳ vọng có** `com/example/core/GreetingComposer.class` ngay ở package path root. Không kỳ vọng thấy `BOOT-INF/classes` hoặc Boot Loader trong core; nếu có, bạn đã đưa nhầm Boot repackage vào library module.

### 10.4. Bước 4 — đọc executable app JAR

~~~bash
jar tf app/target/app-1.0.0-SNAPSHOT.jar
~~~

Kỳ vọng các entry dạng:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/app/MultiModuleApplication.class
BOOT-INF/lib/core-1.0.0-SNAPSHOT.jar
BOOT-INF/lib/commons-lang3-<resolved-version>.jar
BOOT-INF/lib/spring-boot-<resolved-version>.jar
BOOT-INF/lib/spring-webmvc-<resolved-version>.jar
...
~~~

Số version và tập starter/dependency phải lấy từ **JAR thật**, không dùng ký hiệu góc nhọn làm tên file. Nếu project dùng Boot phiên bản khác, loader package/classname có thể thay đổi; kiểm tra manifest của đúng archive.

**Chú ý:** `jar tf app.jar` chỉ liệt kê nested `core.jar` như một entry; nó **không** tự liệt kê `GreetingComposer.class` bên trong nested core.jar. Để xem, liệt kê `core/target/core-...jar` riêng hoặc trích nested JAR ra file rồi mở bằng `jar tf` lần hai.

### 10.5. Bước 5 — chạy chính executable JAR

~~~bash
java -jar app/target/app-1.0.0-SNAPSHOT.jar --server.port=18085
~~~

Ở terminal khác, sau khi app ready:

~~~bash
curl -i http://localhost:18085/ping
~~~

**Kỳ vọng:** HTTP status **200**, body chính xác **`hello From core`**. Đường chạy đã thực hiện lời gọi app → core → Commons Lang trên **classpath do Boot Loader dựng từ artifact**.

Dừng instance bằng Ctrl+C và xác nhận process kết thúc. Nếu app đã chạy ở port 8080 do lệnh khác, không gọi nhầm 18085. Với Batch/CLI không có HTTP server, kiểm tra exit code/job result/side effects thay `curl`.

## 11. Kiểm chứng Gradle: project variants, runtimeClasspath và BootJar

### 11.1. Xem module/tasks

~~~bash
./gradlew --version
./gradlew projects
./gradlew :core:tasks --all
./gradlew :app:tasks --all
~~~

**Kỳ vọng:** có subproject `:core`, `:app`; `core` có task `jar`, `app` có `bootJar`/`bootRun`. Nếu `:core:bootJar` cũng có, kiểm tra vì sao Boot plugin bị áp vào core; library đơn giản này không cần executable archive.

### 11.2. Chạy build và test

~~~bash
./gradlew :core:clean :app:clean :app:build
~~~

Gradle sẽ chạy các producer tasks cần thiết cho `app` theo project dependency `:core`. Không cần tự gọi `:core:jar` trước nếu task graph đã đầy đủ. Kỳ vọng report `app/build/reports/tests/test/` (hoặc `app/build/test-results/test/`) có bài `applicationUsesCoreAndTransitiveLibrary` pass.

Đừng hiểu `UP-TO-DATE` hoặc `FROM-CACHE` là “test chưa từng chạy”: xem report và task inputs/cache provenance theo quy trình CI; với debug nghi vấn, chạy có kiểm soát bằng `--rerun-tasks` nhưng không dùng bừa mọi lần build.

### 11.3. Đọc runtime graph

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath

# Nếu muốn xem riêng Commons Lang và lý do chọn version:
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3

# Phân biệt compileClasspath của app nếu cần:
./gradlew :app:dependencies --configuration compileClasspath
~~~

Trong `runtimeClasspath`, tìm project dependency `project :core` và descendant Commons Lang. Với `compileClasspath` của app, `commons-lang3` có thể **không** được lộ ra qua `core` vì core dùng `implementation` thay vì `api`. Đó là hành vi **đúng** của Java Library plugin, không chứng minh Commons Lang thiếu khỏi runtime.

**Khi nhìn `dependencyInsight`:** chú ý version được yêu cầu, version được chọn và lý do do constraints/conflict resolution. Đừng cố ép archive chứa đúng `3.14.0` chỉ vì `core/build.gradle` đã khai báo requested version đó.

### 11.4. Kiểm tra nested JAR trong app artifact

~~~bash
./gradlew :app:bootJar
jar tf app/build/libs/app-1.0.0-SNAPSHOT.jar
jar tf core/build/libs/core-1.0.0-SNAPSHOT.jar
~~~

Kỳ vọng:

- Plain core jar: class ở `com/example/core/GreetingComposer.class`.
- Boot app jar: class app ở `BOOT-INF/classes/...`, `core-1.0.0-SNAPSHOT.jar` và Commons Lang JAR ở `BOOT-INF/lib/...`.
- JUnit test classes và starter-test không được đưa vào app runtime archive theo cấu hình chuẩn.
- Nếu Gradle tạo `app-1.0.0-SNAPSHOT-plain.jar`, **không chọn nhầm plain archive** để deploy.

Trong cấu hình Java + Boot Gradle Plugin, file `app/build/libs/app-1.0.0-SNAPSHOT.jar` là tên executable JAR điển hình; nếu project có archiveFileName/classifier tùy biến, thay đường dẫn bằng **file do bootJar thực sự tạo**.

### 11.5. Chạy đúng binary Gradle

~~~bash
java -jar app/build/libs/app-1.0.0-SNAPSHOT.jar --server.port=18085
~~~

Ở terminal khác:

~~~bash
curl -i http://localhost:18085/ping
~~~

Kỳ vọng HTTP **200**, body **`hello From core`**. Nếu MockMvc test pass nhưng `java -jar` gặp lỗi classloading, so **testRuntimeClasspath** với **bootJar/runtimeClasspath** và list `BOOT-INF/lib`; đó là cách xác định thiếu dependency bị che bởi test configuration.

## 12. Viết assertion tự động cho archive thay vì nhìn bằng mắt

Một kiểm tra dễ tái sử dụng là xác định **hai runtime JAR quan trọng có thật trong archive app**, đồng thời không lẫn test classes hoặc plain archive. Đoạn Bash sau nhận path executable JAR làm tham số; dùng JDK `jar`, Bash và `grep`.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:?Usage: check-boot-jar.sh <executable-app.jar>}"
ENTRIES="$(jar tf "$ARCHIVE")"

# App main class tồn tại ở BOOT-INF/classes
grep -q '^BOOT-INF/classes/com/example/app/MultiModuleApplication.class$' <<< "$ENTRIES"

# Internal core JAR tồn tại như một nested library
grep -q '^BOOT-INF/lib/core-1\.0\.0-SNAPSHOT\.jar$' <<< "$ENTRIES"

# Commons Lang transitive JAR tồn tại; version không hardcode
grep -Eq '^BOOT-INF/lib/commons-lang3-[^/]+\.jar$' <<< "$ENTRIES"

# Test class không thuộc executable artifact
if grep -q 'MultiModuleApplicationTest.class' <<< "$ENTRIES"; then
    echo "FAIL: test class leaked into runtime archive" >&2
    exit 1
fi

echo "PASS: application, internal module and transitive dependency packaged"
~~~

**Lưu ý kỹ thuật:** trước khi chạy trong Bash thật, thay `${1:?...}`/`$(...)`/`$ARCHIVE`/`$ENTRIES` ở bản hiển thị thành cú pháp shell chuẩn bằng ký tự dollar — đoạn này khi đưa vào file Markdown cuối đã dùng đúng các ký tự `$` tương ứng. Đoạn code trên chỉ kiểm tra vài entry; không thay thế dependency vulnerability scan, runtime test, xác minh license hay SBOM.

**Cách gọi:**

~~~bash
# Maven artifact
bash check-boot-jar.sh app/target/app-1.0.0-SNAPSHOT.jar

# Gradle artifact
bash check-boot-jar.sh app/build/libs/app-1.0.0-SNAPSHOT.jar
~~~

**Stdout dự kiến khi script pass:**

~~~text
PASS: application, internal module and transitive dependency packaged
~~~

Nếu thiếu entry, một trong các lệnh `grep` thất bại và Bash thoát với non-zero status trước khi in PASS. Với đường dẫn archive khác hoặc version core khác, sửa assertion theo artifact thật. Đây là script cho bản demo, không phải scan tổng quát cho mọi project.

**Vì sao dùng here-string `<<< "$ENTRIES"` thay vì `jar tf ... | grep -q`?** Khi bật `set -o pipefail`, đầu đọc kết thúc sớm có thể làm producer gặp SIGPIPE trên archive lớn. Ở đây archive listing được giữ trước, rồi kiểm tra trong shell. Với artifact rất lớn hoặc chính sách CI nghiêm ngặt, nên thay bằng unit test dùng Java ZIP API có failure messages cụ thể và không phải giữ toàn bộ listing trong memory.

### 12.1. Trích nội bộ một nested core JAR khi cần

Nếu muốn xác minh class của core ở trong nested library của **chính app JAR**, có thể dùng `unzip -p` trong một thư mục kiểm tra riêng:

~~~bash
# Ví dụ chạy từ root Maven project, chỉ khi có unzip
mkdir -p jar-inspect
unzip -p app/target/app-1.0.0-SNAPSHOT.jar \
  BOOT-INF/lib/core-1.0.0-SNAPSHOT.jar > jar-inspect/core-from-app.jar

jar tf jar-inspect/core-from-app.jar
~~~

Kỳ vọng thấy `com/example/core/GreetingComposer.class`, không có `BOOT-INF/classes` trong nested core library JAR. Việc `jar tf outer.jar` không liệt kê class nested là bình thường; cần mở JAR lớp trong nếu muốn kiểm tra.

### 12.2. Test negative path có chủ đích

Ở **nhánh học tập riêng**, thử thay `core` dependency Commons Lang thành `compileOnly` trong Gradle core (hoặc Maven optional/exclusion ở quan hệ app→core), build rồi xem:

1. Dependency graph app có còn Commons Lang không?
2. Archive `BOOT-INF/lib` có còn JAR đó không?
3. Test app/`java -jar` fail ở compile, startup hay khi `GET /ping`?
4. Vì sao class loading chỉ lộ lỗi khi code path thật sử dụng `StringUtils`?

Sau đó khôi phục `implementation`/compile scope đúng, build sạch và kiểm tra lại. **Không dùng artifact cố tình thiếu dependency để deploy**. Chỉ thực hiện thử nghiệm trong môi trường được phép.

## 13. Những lỗi phổ biến trong dự án nhiều module

| Triệu chứng | Nguồn gốc thường gặp | Hướng kiểm chứng và sửa |
| --- | --- | --- |
| Maven app báo không resolve được `com.example:core`. | Build child riêng, core chưa cài local repo; groupId/version không khớp reactor. | Chạy từ root với `-pl app -am`, kiểm tra GAV và parent/module paths. |
| Maven reactor không build core trước app. | App không khai báo dependency core, chỉ có tên core trong `<modules>`. | Thêm đúng `<dependency>` và xem reactor build order. |
| Maven `-am spring-boot:run` cố chạy ở core. | Trực tiếp gọi goal trên mọi selected modules, thay vì chỉ app. | Build/install dependency qua reactor rồi chạy `-pl app spring-boot:run`. |
| `java -jar` báo `ClassNotFoundException: com.example.core.GreetingComposer`. | App executable JAR thiếu core JAR hoặc core bị đóng sai kiểu. | Xem `BOOT-INF/lib/core-...jar` và mở nested JAR. |
| `NoClassDefFoundError: org/apache/commons/lang3/StringUtils`. | Commons Lang bị exclude/optional/provided/compileOnly hoặc packaging không lấy runtime dependency. | So app runtime graph và `BOOT-INF/lib`, khôi phục dependency đúng scope. |
| Core có `BOOT-INF/classes` thay vì class ở root package path. | Library bị Boot repackage. | Chỉ áp Boot plugin ở app; core dùng plain jar; rebuild từ source. |
| Gradle app compile không import được Commons Lang trực tiếp. | Core dùng `implementation` và không lộ Commons ở app compileClasspath. | Nếu app thực sự gọi Commons trực tiếp, thêm dependency trực tiếp ở app; hoặc dùng `api` ở core **chỉ nếu type nằm trong public API**. |
| Gradle core dùng `compileOnly` và app thiếu Commons runtime. | Compile-only không truyền sang app runtime. | Dùng `implementation` nếu core gọi dependency khi chạy. |
| Test app pass nhưng executable JAR fail. | Test classpath rộng hơn packaged runtime classpath. | So testRuntimeClasspath/runtimeClasspath và archive list, chạy binary smoke thật. |
| Module app dùng Boot plugin nhưng archive thiếu starter dependencies. | Runtime configuration/exclusions/BOM hoặc BootJar classpath bị chỉnh. | Xem `dependencyInsight`/`dependency:tree`, bootJar/repackage configuration. |
| Maven dependency version core không đúng bản đang sửa. | Local repository có SNAPSHOT cũ, build child ngoài reactor. | Dùng root reactor build, kiểm tra GAV và artifact timestamp/hash nếu cần. |
| Gradle `Project with path ':core' could not be found`. | `settings.gradle` thiếu `include('core')` hoặc project path khác. | Sửa include/path, chạy `./gradlew projects`. |
| Gradle `:core:bootJar` đòi mainClass. | Boot plugin bị apply vào library. | Gỡ Boot ở core, giữ `java-library`/`jar`. |
| App có hai version của một dependency. | BOM/constraints/dependency conflict/exclusions tùy graph. | Dùng dependencyInsight, Maven tree, quản lý version nhất quán; không xóa nested JAR thủ công. |
| Chọn nhầm `app-...-plain.jar`. | Gradle tạo plain và Boot JAR với classifier khác. | Xác nhận task `bootJar`, manifest, `BOOT-INF` và chạy đúng artifact. |
| Thay `mainClass` mà thiếu core vẫn chưa được giải quyết. | MainClass chỉ chọn entrypoint, không tự thêm dependency. | Khai báo app→core và kiểm tra runtime graph. |
| Có BOM/version catalog nhưng không có core JAR. | BOM/catalog chỉ quản lý metadata/version notation. | Thêm actual dependency, không chỉ quản lý version. |
| Ứng dụng lỗi chỉ ở một profile/batch job. | Dependency được load trễ theo code path, smoke không bao phủ. | Test các profile/job dùng module đó; phân tích optional/conditional dependencies. |
| Archive xuất hiện `junit-jupiter` hoặc test classes. | Test dependencies/source sets bị trộn vào production. | Sửa scope/configuration và package inputs, kiểm tra entry negative assertion. |
| Maven plugin ở tất cả module, core không publish dùng được. | Parent `<build><plugins>` bắt buộc repackage và đè library artifact. | Dùng `pluginManagement` hoặc chỉ khai báo Boot plugin ở app; tách classifier nếu thật sự cần executable variant. |

### 13.1. Quy trình chẩn đoán theo bốn lớp

**Lớp 1 — Module membership:** core/app có thực sự ở cùng reactor hoặc Gradle multi-project build? Có khai báo relation app→core chưa?

**Lớp 2 — Dependency resolution:** app runtime graph có core và Commons Lang không? Có bị exclusions, optional, provided, compileOnly, version mediation hoặc constraints làm khác kỳ vọng?

**Lớp 3 — Packaging:** plain core JAR có class đúng không? Boot app JAR có `BOOT-INF/lib/core-*.jar` và Commons Lang JAR không? Có nhầm `*-plain.jar` hoặc repackaged library không?

**Lớp 4 — Runtime behavior:** `java -jar` có startup và `GET /ping` có thực sự đi qua app→core→Commons Lang rồi trả `hello From core`? Nếu app không có server, có test job flow tương đương không?

Không tự động thêm toàn bộ libraries vào trực tiếp `app` để “chữa cháy” khi chưa hiểu metadata/scope; việc đó có thể che một API contract sai trong core và gây dư thừa dependencies ở nhiều consumer.

## 14. Quản lý versions, snapshot và tính tái lập

### 14.1. Tại sao app package có thể lấy version không giống core compile?

Ví dụ core yêu cầu Commons Lang `3.14.0` nhưng app có Spring Boot BOM hoặc dependency constraint/đường dependency khác. Trong Maven, dependency management/mediation có thể chọn một phiên bản cho consumer; Gradle có conflict resolution/constraints. Vì vậy:

- **`core/build.gradle`/`core/pom.xml`** cho biết yêu cầu của producer.
- **App dependency report** cho biết version được chọn trong consumer.
- **`BOOT-INF/lib`** cho biết artifact thư viện **thực sự** được phân phối.

Đừng kết luận jar bị thiếu/chọn sai chỉ từ việc tên file không trùng một version hard-coded ở tài liệu. Điều quan trọng là **đúng group:artifact, version tương thích, đúng scope/variant và behavior test đạt**.

### 14.2. SNAPSHOT và Maven local cache

Core `1.0.0-SNAPSHOT` có thể được cài local ở một trạng thái source cũ. Chạy app như một module đơn mà không build lại core có nguy cơ dùng **binary cũ**. Để tái lập:

1. Ưu tiên build/test app và core trong **một reactor**: `./mvnw -pl app -am clean verify`.
2. Chỉ install/publish khi workflow yêu cầu module chạy đơn hoặc repo ngoài cần artifact.
3. Ghi commit, version, Maven settings/repositories và artifact hash nếu phát hành.
4. Dùng CI sạch hoặc có cache policy rõ để tránh lấy nhầm SNAPSHOT không thuộc commit mong đợi.

### 14.3. Gradle project dependency khác published artifact

`implementation project(':core')` dùng **project output/variants trong cùng build**, Gradle biết cần build producer nào. Nếu thay bằng:

~~~groovy
dependencies {
    implementation 'com.example:core:1.0.0-SNAPSHOT'
}
~~~

thì đây là **external module dependency theo tọa độ**, yêu cầu repository có published artifact và metadata. Khi chuyển từ project dependency sang published dependency, cần kiểm tra Gradle module metadata/POM scope của core có bảo toàn `api`/`implementation` và transitive dependencies không.

### 14.4. Layered JAR và module nội bộ

Spring Boot executable JAR có thể chứa `BOOT-INF/layers.idx` phục vụ layer extraction/build images. Maven Boot Plugin có thể nhận diện **local module dependencies của current build** để đưa vào application layer, nhưng module chỉ được resolve từ local Maven cache như external binary có thể bị phân loại khác. Đây là vấn đề **tối ưu container layer cache**, không phải quyết định core/Commons có tồn tại hay không trong runtime.

Vì vậy, đừng sửa layer index để giải quyết `NoClassDefFoundError`. Trước tiên phải đảm bảo dependency graph và archive contents đúng; tối ưu layers là bước sau.

### 14.5. Không đánh đồng dependency completeness với supply-chain safety

Executable JAR chứa nhiều libraries là điều cần để chạy, nhưng bạn còn cần:

- Quản lý version và vulnerability advisories theo chính sách.
- Dependency verification/checksums/lockfiles khi yêu cầu tái lập.
- License notices/SBOM và provenance của internal artifacts.
- Quét không đưa secrets, test-only tooling hoặc devtools vào production JAR.
- Test các profile/code paths sử dụng optional hoặc reflection-based dependencies.

Bài học này tập trung vào **đóng đủ runtime dependencies một cách có chủ đích**, không khuyến khích đẩy “mọi JAR trên máy” vào sản phẩm.

## 15. Bài thực hành và tiêu chí đạt

### Bài thực hành A — Maven reactor

1. Tạo root `pom.xml`, `core/pom.xml`, `app/pom.xml` và ba file Java chính xác như mục 4–5.
2. Dùng Maven Wrapper được lưu với project, kiểm tra `./mvnw -version`.
3. Chạy `./mvnw -pl app -am clean verify`.
4. Đọc report `app/target/surefire-reports` và xác nhận test `applicationUsesCoreAndTransitiveLibrary` đã chạy.
5. Mở `core/target/core-1.0.0-SNAPSHOT.jar`: class core phải ở package path root.
6. Mở `app/target/app-1.0.0-SNAPSHOT.jar`: app class ở `BOOT-INF/classes`, core và Commons JAR ở `BOOT-INF/lib`.
7. Chạy `./mvnw -pl app -am dependency:tree` rồi chỉ ra đường `app → core → commons-lang3`.
8. Chạy `java -jar app/target/app-1.0.0-SNAPSHOT.jar --server.port=18085` và `curl -i http://localhost:18085/ping`.
9. Đạt khi HTTP status **200**, body **hello From core**, test report pass và artifact structure đúng.

### Bài thực hành B — Gradle multi-project

1. Dùng root `settings.gradle`, root `build.gradle`, `core/build.gradle` và `app/build.gradle` ở mục 7.
2. Chạy `./gradlew projects` xác nhận cả hai subprojects.
3. Chạy `./gradlew :core:clean :app:clean :app:build`, xem report `app` JUnit.
4. Chạy `./gradlew :app:dependencies --configuration runtimeClasspath` và `:app:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3`.
5. So `compileClasspath` với `runtimeClasspath` để giải thích vì sao `implementation` của core **vẫn đi tới runtime** mà không bị lộ qua app compile API.
6. Chạy `./gradlew :app:bootJar`, `jar tf app/build/libs/app-1.0.0-SNAPSHOT.jar` và assert core/Commons trong `BOOT-INF/lib`.
7. Thử `java -jar`/`curl` giống bài A, xác nhận body **hello From core**.

### Bài thực hành C — quan sát transitive dependency khi bị loại

Ở branch học tập, thử một thay đổi có chủ đích:

- Maven: đặt `optional=true` lên dependency Commons Lang trong core hoặc exclude Commons qua app→core, rồi xem tree/app artifact. Nếu app cần Commons Lang runtime, sửa metadata/scope hoặc khai báo explicit dependency thích hợp.
- Gradle: đổi Commons Lang của core từ `implementation` thành `compileOnly`, so app `runtimeClasspath` và archive.
- Build và test hành vi, ghi **lỗi thực tế** nếu xuất hiện, không suy rằng mọi lỗi sẽ cùng một message ở mọi Gradle/Maven/JDK.
- Hoàn nguyên, build lại và chứng minh đầy đủ artifact.

Không dùng bản cố ý thiếu dependency trong production pipeline.

### Checklist đánh giá

- [ ] Phân biệt root aggregator/parent, module dependency graph và resolved runtime classpath.
- [ ] Biết `<modules>`/`include(...)` không tự tạo `app → core`.
- [ ] Maven app khai báo `com.example:core` với version khớp reactor.
- [ ] Gradle app dùng `implementation project(':core')`.
- [ ] Core có plain `jar`; app có executable `repackage`/`bootJar`.
- [ ] Giải thích app class ở `BOOT-INF/classes`, internal/external libraries ở `BOOT-INF/lib`.
- [ ] Biết Commons Lang được kéo theo qua core dù app không khai báo trực tiếp.
- [ ] Phân biệt Maven `compile`, `provided`, `test`, `optional` và transitive exclusions.
- [ ] Phân biệt Gradle `api`/`implementation`/`runtimeOnly`/`compileOnly`/`testImplementation`.
- [ ] Biết Maven reactor `-pl app -am` khác chạy app module đơn khi local SNAPSHOT chưa tồn tại.
- [ ] Biết Gradle project dependency tự nối build tasks, không bắt buộc `publishToMavenLocal`.
- [ ] Dùng dependency reports để xác định selected version và đường phụ thuộc thực tế.
- [ ] Dùng `jar tf` kiểm tra cả core JAR và executable app JAR; không deploy nhầm plain JAR.
- [ ] Test app đi qua core và Commons Lang, không chỉ startup.
- [ ] Có test report và `java -jar` HTTP smoke thực tế.
- [ ] Có thể nêu nguyên nhân khi thiếu core, Commons Lang hoặc dùng nhầm SNAPSHOT.
- [ ] Không tự sửa archive bằng cách chèn/xóa JAR thủ công thay cho cấu hình dependency đúng.
- [ ] Có phương án quản lý version/lock/security/SBOM theo chính sách phát hành.

**Tiêu chí hoàn thành:** trình bày được một **multi-module build** thực sự, cho thấy `app → core → commons-lang3` trong resolved graph, `core.jar` ở dạng plain library, executable app JAR có **cả core và Commons Lang nested JARs**, và endpoint `/ping` khi chạy chính app archive trả `hello From core`. Nếu test hoặc external package chưa được chạy, nêu rõ phần chưa được chứng minh, không biến một lệnh `BUILD SUCCESS` thành lời cam kết về mọi runtime path.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot — Executable JAR Format / Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle — Java Library Plugin, API vs Implementation](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Dependency Management for JVM Projects](https://docs.gradle.org/current/userguide/dependency_management_for_java_projects.html)

**Ghi nhớ:** một module nội bộ có thể kéo theo một hoặc nhiều external libraries mà app không khai báo trực tiếp. Muốn sản phẩm chạy đúng, hãy để **dependency metadata + scopes/configurations + reactor/project variants + Spring Boot packaging** lựa chọn runtime classpath, rồi **kiểm chứng trên executable archive thực tế**, thay vì gom thủ công tất cả JAR hoặc tin vào test classpath.