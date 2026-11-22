# Build riêng một mô-đun và kiểm tra mức độ độc lập của sản phẩm

Một repository Spring Boot có nhiều mô-đun thường được tổ chức để tái sử dụng Java code, chia trách nhiệm và rút ngắn vòng lặp phát triển. Tuy nhiên, câu nói **“build riêng mô-đun A thành công”** dễ bị hiểu thành **“sản phẩm của A độc lập hoàn toàn”**. Hai kết luận này **không tương đương**.

Ví dụ một ứng dụng `catalog-app` dùng thư viện nội bộ `catalog-core`:

- Bạn có thể chỉ yêu cầu Maven/Gradle build `catalog-app`, nhưng build tool vẫn phải tìm hoặc biên dịch `catalog-core` nếu đó là phụ thuộc của ứng dụng.
- Bạn có thể chạy executable Spring Boot JAR của `catalog-app` ở một thư mục khác không có source của `catalog-core`, bởi JAR đã đóng gói dependency này; điều đó **chứng minh tính tự chứa về Java runtime classpath**, không chứng minh ứng dụng không cần database, mạng hay cấu hình môi trường.
- Bạn có thể cố build `catalog-app` từ một checkout chỉ có module ứng dụng nhưng thiếu parent/dependency đã được publish; lỗi resolve Maven/Gradle lúc ấy chứng tỏ **build từ source vẫn có coupling**.

Bài này hướng dẫn cách **chọn một mô-đun để build**, xem đúng **đồ thị phụ thuộc**, đóng gói và **kiểm chứng sản phẩm riêng biệt**. Có hai lựa chọn build: Maven Reactor và Gradle Multi-Project. Ví dụ Java 17, Spring Boot 3.3.13 được giữ nhất quán; hãy dùng các phiên bản còn phù hợp với chính sách dự án khi áp dụng thực tế.

## 1. Hiểu ba loại “độc lập” trước khi viết lệnh

| Loại độc lập | Câu hỏi cần trả lời | Bằng chứng đúng |
| --- | --- | --- |
| **Phạm vi build** | Có thể chỉ chọn một module đích thay vì build/test toàn bộ repository không? | Maven `-pl`, Gradle task path `:module:build`, log task/reactor được chọn |
| **Khả năng build từ nguồn** | Có thể biên dịch module khi không dùng source của sibling modules không? | Parent/config và mọi dependency đã được publish hoặc cung cấp hợp lệ; thử với repository/cache sạch có kiểm soát |
| **Tính tự chứa của artifact runtime** | File ứng dụng có chạy được trên máy chỉ có JVM tương thích và cấu hình cần thiết không? | Kiểm tra `BOOT-INF/lib`/manifest; copy đúng executable JAR sang thư mục khác; `java -jar` + smoke test |

Một tiêu chí bổ sung là **độc lập về hệ thống/vận hành**: ứng dụng không cần các dịch vụ ngoài hoặc có khả năng xử lý sự cố của chúng? Đây là bài toán kiến trúc lớn hơn, **không được chứng minh chỉ bằng build hoặc một lần `java -jar` thành công**.

### Phân biệt bốn từ thường dùng

- **Module:** một đơn vị build (Maven project/Gradle subproject) có source, dependency và đầu ra riêng.
- **Aggregator:** Maven POM `<packaging>pom</packaging>` liệt kê `<modules>`; Gradle root/settings liệt kê `include(...)`. Nó tập hợp nhiều module thành một build.
- **Dependency:** một module cần class/artifact của module khác. Ví dụ `catalog-app → catalog-core` là quan hệ thật, không phải “cùng folder”.
- **Product/artifact:** JAR/WAR được publish/deploy. Nó có thể chỉ là **plain library JAR** hoặc là **Spring Boot executable JAR** có Boot Loader và các runtime dependencies.

Khi nhận yêu cầu “build riêng mô-đun và kiểm tra độc lập”, đừng chỉ trả lời “`mvn -pl` chạy thành công”. Hãy kiểm chứng **đúng tầng mà người yêu cầu quan tâm**.

## 2. Sơ đồ Maven/Gradle multi-module làm mẫu

Ta xây hai module:

```text
multi-module-demo/
├── pom.xml                           (Maven aggregator + parent)
├── catalog-core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/example/catalog/core/
│       │   └── GreetingFormatter.java
│       └── test/java/dev/example/catalog/core/
│           └── GreetingFormatterTest.java
└── catalog-app/
    ├── pom.xml
    └── src/
        ├── main/java/dev/example/catalog/app/
        │   ├── CatalogApplication.java
        │   └── GreetingController.java
        └── test/java/dev/example/catalog/app/
            └── GreetingControllerTest.java
```

Với Gradle, thay ba tệp `pom.xml` bằng `settings.gradle`, `build.gradle` ở root và `build.gradle` trong mỗi module; giữ nguyên các file Java.

Đồ thị phụ thuộc ứng dụng:

```text
              multi-module-demo
                 [root build]
                      |
              +-------+--------+
              |                |
         catalog-core      catalog-app
         [Java library]    [Boot service]
              ^                |
              +----------------+
                 app depends on core
```

**Quan hệ trọng yếu:** `catalog-app` cần `catalog-core`. `catalog-core` **không** phụ thuộc `catalog-app`. Khi chỉ muốn kiểm tra core, không cần khởi động app. Khi build app, phải có core từ **cùng reactor/multi-project build** hoặc từ **repository chứa artifact phù hợp**.

### Mục tiêu quan sát

Sau ví dụ chạy đúng:

- `catalog-core` tạo **plain JAR** với class `dev.example.catalog.core.GreetingFormatter`.
- `catalog-app` tạo **executable Spring Boot JAR** với `BOOT-INF/classes` của app và dependency `BOOT-INF/lib/catalog-core-1.0.0.jar`.
- Lệnh HTTP `GET /hello` trả `Hello, Ada!`; `GET /hello?name=Linh` trả `Hello, Linh!`.
- Nếu chuyển riêng file `catalog-app-1.0.0.jar` ra khỏi source tree, ứng dụng vẫn tìm được `GreetingFormatter` thông qua nested library `catalog-core`.
- Nếu thiếu core dependency ở build-time, lệnh chọn chỉ app **không tự biến** source core thành độc lập; Maven/Gradle phải resolve đúng artifact.

## 3. Mã Java dùng chung cho cả Maven và Gradle

Bốn class chính và hai test dưới đây là **file hoàn chỉnh**. Tạo source ở đúng đường dẫn package tương ứng.

### 3.1. Library `catalog-core`

`catalog-core/src/main/java/dev/example/catalog/core/GreetingFormatter.java`:

```java
package dev.example.catalog.core;

public final class GreetingFormatter {

    public String render(String name) {
        return "Hello, " + name + "!";
    }
}
```

Class không dùng Spring, nên module core có thể là Java library thuần. Việc tách core như vậy giúp tránh áp dụng Spring Boot `repackage` vào một library mà module khác cần import.

`catalog-core/src/test/java/dev/example/catalog/core/GreetingFormatterTest.java`:

```java
package dev.example.catalog.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingFormatterTest {

    @Test
    void formatsGreeting() {
        GreetingFormatter formatter = new GreetingFormatter();
        assertEquals("Hello, Ada!", formatter.render("Ada"));
    }
}
```

Test này chứng minh **core tự biên dịch và test được** với dependency test mà module định nghĩa. Nó không chứng minh core hoàn toàn độc lập với mọi external library trong dự án thật; ví dụ cố ý chỉ dùng JDK và JUnit lúc test.

### 3.2. Spring Boot application `catalog-app`

`catalog-app/src/main/java/dev/example/catalog/app/CatalogApplication.java`:

```java
package dev.example.catalog.app;

import dev.example.catalog.core.GreetingFormatter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
```

Tại sao khai báo `@Bean`? Module core có package `dev.example.catalog.core`, nằm **ngoài** package con của `dev.example.catalog.app`; component scan mặc định từ `CatalogApplication` không tự quét mọi package khác chỉ vì hai module cùng repository. Ví dụ chủ động đăng ký `GreetingFormatter` từ core để dependency và wiring được nhìn thấy rõ.

`catalog-app/src/main/java/dev/example/catalog/app/GreetingController.java`:

```java
package dev.example.catalog.app;

import dev.example.catalog.core.GreetingFormatter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingFormatter formatter;

    public GreetingController(GreetingFormatter formatter) {
        this.formatter = formatter;
    }

    @GetMapping("/hello")
    public String hello(@RequestParam(defaultValue = "Ada") String name) {
        return formatter.render(name);
    }
}
```

Đối với endpoint này, không cần database hoặc gọi API ngoài, nên việc chạy artifact ở thư mục tách biệt dễ quan sát. Trong production, service có thể cần external configuration, secrets, network và backend services.

`catalog-app/src/test/java/dev/example/catalog/app/GreetingControllerTest.java`:

```java
package dev.example.catalog.app;

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
class GreetingControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void usesCodeFromCoreModule() throws Exception {
        mvc.perform(get("/hello").param("name", "Linh"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Linh!"));
    }
}
```

App test xác nhận app đã **resolve, biên dịch và gọi API của core** dưới test classpath. Tuy nhiên, giống mọi `@SpringBootTest`, điều này chưa chứng minh **JAR được đóng gói** chạy đúng; cần chạy `java -jar` sau build.

## 4. Maven: cấu hình root aggregator/parent

Maven gọi tập module trong một lần build là **reactor**. Một root aggregator có `<modules>`; các module cùng kế thừa parent để dùng chung version/dependency management. Hai vai trò aggregator và parent có thể cùng nằm trong một POM nhưng bản chất khác nhau.

`multi-module-demo/pom.xml`:

```xml
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

    <groupId>dev.example</groupId>
    <artifactId>multi-module-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>catalog-core</module>
        <module>catalog-app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
    </properties>
</project>
```

Một số chi tiết quan trọng:

- `packaging=pom`: root là aggregator/parent, **không** phải Spring Boot app cần `repackage`.
- `<modules>`: Maven reactor biết hai module và có thể build chúng theo phụ thuộc thực tế.
- `spring-boot-starter-parent`: cung cấp BOM và plugin management phù hợp với Boot 3.3.13, kể cả các convention kiểm thử và compiler cho Java 17.
- **Không** khai báo `spring-boot-maven-plugin` trong `<build><plugins>` tại root để tránh kế thừa execution `repackage` không cần thiết vào `catalog-core`. Chỉ app mới có executable main class.

Maven reactor sắp xếp thứ tự dựa trên dependency project thực tế, parent/relationship và thông tin build. **Thứ tự liệt kê module không phải cách thay thế dependency declaration**. Nếu `catalog-app` import class của core thì phải khai báo dependency `catalog-core` rõ ràng.

## 5. Maven: POM của core và app

### 5.1. `catalog-core/pom.xml` — library JAR

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>multi-module-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>catalog-core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Maven dùng `jar` packaging để tạo `catalog-core-1.0.0.jar`, chỉ gồm app-independent classes/resources của core và metadata thông thường. JUnit ở test scope **không** trở thành runtime dependency của catalog-app qua core.

Đặc biệt, core **không** khai báo Spring Boot Maven Plugin. Đưa executable Boot JAR (đặt application classes dưới `BOOT-INF/classes`) làm dependency cho một module khác là lỗi packaging thường gặp: consumer cần library JAR có compiled classes ở package root.

### 5.2. `catalog-app/pom.xml` — Boot application

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>multi-module-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>catalog-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>catalog-core</artifactId>
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
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`${project.version}` ở đây lấy version `1.0.0` của project app, khớp core trong ví dụ. Dự án thực có thể version mỗi module độc lập, khi đó phải dùng version đã được publish hoặc property/version catalog riêng; không bắt buộc mọi module cùng version.

Phần `catalog-core` trong `<dependencies>` là **quan hệ dùng code thật**. Maven reactor có thể cung cấp core artifact khi cả hai module nằm trong build; nếu chỉ chọn app và không build core, Maven phải resolve `dev.example:catalog-core:1.0.0` từ cache/repository phù hợp.

Spring Boot Maven Plugin chỉ ở app, để goal `repackage` biến JAR ứng dụng thành executable archive có nested dependencies. Với starter parent ở root, execution `repackage` được quản lý theo convention khi app khai báo plugin.

## 6. Maven Reactor: build một module đúng cách

Mở terminal tại **root `multi-module-demo`** chứa aggregator `pom.xml`. Cần JDK 17 và Maven tương thích, hoặc Maven Wrapper nếu repository cung cấp.

### 6.1. Build toàn bộ repository

```bash
mvn -version
mvn clean verify
```

Lệnh này thường đi qua root POM, core và app. `verify` chạy các phase trước đó, bao gồm `package`; Spring Boot Maven Plugin ở app thực hiện `repackage`, nên output app là executable JAR.

Đây là **baseline** hữu ích khi kiểm chứng trước khi tối ưu phạm vi build. Nếu repository có nhiều module không liên quan, toàn build có thể mất nhiều thời gian.

### 6.2. Chỉ chọn module app — cần `-am` khi phụ thuộc sibling chưa được publish

```bash
mvn -B -pl :catalog-app -am clean verify
```

Giải thích các cờ:

- `-B`: batch mode, phù hợp CI; không liên quan trực tiếp việc chọn module.
- `-pl`/`--projects`: chỉ định project đích trong reactor. `:catalog-app` là cách chọn theo **artifactId**, còn `-pl catalog-app` thường chọn theo **relative path**.
- `-am`/`--also-make`: xây thêm các **module dependency cần thiết** trong reactor. Ở ví dụ này, `catalog-core` được build vì app cần nó; root parent/aggregator cũng có thể tham gia theo reactor model.
- `clean verify`: clean và build/test cho những project được chọn; lệnh không có nghĩa tất cả module trong repository đều được test.

Ví dụ thứ tự mang tính khái niệm:

```text
multi-module-demo [pom]
       |
       v
catalog-core [jar]
       |
       v
catalog-app [jar + Boot repackage]
```

Nếu project có thêm `unrelated-reporting` không liên quan app, `-pl :catalog-app -am` không tự lựa chọn module ấy chỉ vì nó nằm trong `<modules>`.

**Điểm quan trọng:** `-am` chứng minh Maven tính đúng đồ thị phụ thuộc và chỉ xây **các module cần thiết**, chứ không chứng minh app không phụ thuộc core.

### 6.3. Chỉ build core để xác nhận ranh giới upstream

```bash
mvn -B -pl :catalog-core -am clean verify
```

Với ví dụ, lệnh này test core và không cần compile app. Điều này phù hợp đồ thị một chiều `app → core`. Ở dự án thật, nếu core bất ngờ có dependency ngược lên app, đó có thể là dấu hiệu coupling/vòng phụ thuộc cần sửa.

### 6.4. `-amd` là hướng **ngược lại** `-am`

```bash
mvn -B -pl :catalog-core -amd test
```

`-amd`/`--also-make-dependents` mở rộng selection sang các module **phụ thuộc vào** core, chẳng hạn catalog-app. Nó hữu ích khi bạn đổi API của core và muốn đánh giá những consumer trong reactor. Nhưng lưu ý:

- `-amd` không tự có cùng mục đích với `-am`; một cờ chọn **upstream dependencies**, cờ kia chọn **downstream dependents**.
- Với lệnh test phụ thuộc vào artifact từ reactor, Maven có thể cần các module liên quan được đưa vào build đúng cách; nếu nhiều module/phụ thuộc phức tạp, chọn phase và scope theo thực tế, có thể dùng kết hợp `-am` hoặc một reactor build phù hợp.
- Đừng coi `-amd` là cờ tối ưu cho việc chỉ đóng gói app; mục đích chính là kiểm tra ảnh hưởng downstream.

### 6.5. `-pl` không kèm `-am`: vì sao có thể “lúc chạy được, lúc lỗi”?

```bash
mvn -B -pl :catalog-app clean verify
```

Lệnh này chỉ chọn app. Nếu `catalog-core:1.0.0` **chưa có trong reactor đã chọn hoặc repository mà Maven truy cập được**, Maven có thể báo lỗi không resolve dependency. Nếu máy phát triển trước đó đã chạy `mvn install` cho core, lệnh có thể **thành công nhờ local Maven repository**, làm che giấu vấn đề khi chạy trên một CI agent mới.

Đó là lý do không thể lấy một lần `mvn -pl :catalog-app verify` trên laptop làm chứng cứ “app độc lập hoàn toàn”. Build có thể đã dùng artifact core nằm ở `~/.m2/repository` từ lần chạy cũ, không phải source core đang sửa.

**Lệnh mặc định khuyến nghị trong monorepo khi chưa publish sibling module:** `mvn -pl :catalog-app -am clean verify`.

## 7. Build app riêng mà không build lại core source: cần artifact đã có

Đây là một yêu cầu khác với reactor subset build. Nhóm có thể muốn:

1. Build và publish `catalog-core` trước.
2. Sau đó build `catalog-app` chỉ dựa trên **version artifact đã công bố**, không compile source core trong cùng lần build.

### Thử trong local repository có kiểm soát

Tại root, thực hiện:

```bash
# Bước 1: cài parent và catalog-core vào local Maven repository.
mvn -B -pl :catalog-core -am clean install

# Bước 2: build riêng app; không dùng -am.
mvn -B -pl :catalog-app clean verify
```

Bước 1 đặt POM/artifact của parent và core vào local Maven repository; bước 2 có thể resolve core từ đó mà không compile lại source của `catalog-core`. Đây là **module-only source build được nhờ artifact đã cài**, không phải bằng chứng app không có dependency.

Đối với môi trường CI thật, tốt hơn nên publish core/parent tới artifact repository được quản lý hoặc dùng reactor trong cùng workflow. `mvn install` là tác vụ **cục bộ**; không phải cách publish mà mọi CI agent khác nhìn thấy. Khi build core có version thay đổi theo commit, không nên cài artifact cũ vào local cache rồi build app mà tin rằng đang dùng code mới.

### Ba mức thử nghiệm riêng

| Thí nghiệm | Phụ thuộc core được cung cấp bằng cách nào? | Kết luận hợp lệ |
| --- | --- | --- |
| `mvn -pl :catalog-app -am clean verify` | Reactor build source core trong lần chạy này | Targeted reactor build thành công |
| `mvn -pl :catalog-app clean verify` sau khi `install` core | Local Maven repository | App build được khi có core artifact đã cài |
| Build app trên máy/CI sạch chỉ có source app | Artifact repository + parent/plugin/config hợp lệ | App build từ source độc lập với checkout core nếu mọi input đã công bố |

Ở thử nghiệm thứ ba, **đường parent POM** cũng cần tính đến. Trong ví dụ, app có `<parent>dev.example:multi-module-demo:1.0.0</parent>` với `relativePath=../pom.xml`. Nếu tách riêng `catalog-app` khỏi root, Maven cần parent POM trong repository và có thể phải điều chỉnh `relativePath` để lookup hợp lệ (thường dùng `<relativePath/>` khi parent được publish). **Copy mỗi thư mục app không tự có đủ cấu hình build**.

Nếu mục tiêu là khả năng build từ một checkout độc lập lâu dài, hãy thiết kế release/versioning, repository credentials, plugin versions, parent/BOM publication và lock down external dependencies. Không sửa tạm POM cho một phép thử rồi gọi đó là bằng chứng reproducible.

## 8. Đồ thị module và dependency graph: xem đúng thứ app thực sự dùng

Maven reactor chỉ ra **module nào build**; Maven dependency plugin cho thấy **artifact nào vào dependency tree**. Đây là hai loại thông tin khác nhau.

Từ root:

```bash
mvn -pl :catalog-app -am dependency:tree
```

Kết quả chi tiết phụ thuộc version plugin và Maven; những dependency quan trọng dự kiến:

```text
dev.example:catalog-app:jar:1.0.0
+- dev.example:catalog-core:jar:1.0.0:compile
+- org.springframework.boot:spring-boot-starter-web:jar:3.3.13:compile
\- org.springframework.boot:spring-boot-starter-test:jar:3.3.13:test
```

Đây là **sơ đồ rút gọn**, không phải stdout chính xác, vì dependency tree còn chứa rất nhiều transitive entries, format và version do tool quyết định. Nếu muốn chỉ xem dependency core:

```bash
mvn -pl :catalog-app dependency:tree -Dincludes=dev.example:catalog-core
```

Điểm cần đọc là **core xuất hiện với scope compile**. Khi `spring-boot:repackage` đóng executable JAR app, core plain JAR được đưa vào `BOOT-INF/lib` (trừ khi project chủ động exclude hoặc cấu hình đặc biệt).

**Đừng suy từ dependency tree rằng tất cả dependency chắc chắn được đóng gói:** `provided`, `optional`, exclusions, plugin packaging config và dependency conflicts có thể làm output khác. Cần **kiểm tra archive thật**.

## 9. Build, inspect và chạy sản phẩm Spring Boot của riêng app

Từ root repository:

```bash
mvn -B -pl :catalog-app -am clean verify
```

Bản build Maven của ví dụ tạo:

```text
catalog-core/target/catalog-core-1.0.0.jar
catalog-app/target/catalog-app-1.0.0.jar
catalog-app/target/catalog-app-1.0.0.jar.original
```

**Phân biệt:**

- `catalog-core-1.0.0.jar` là **library JAR**: class `GreetingFormatter` nằm tại package root.
- `catalog-app-1.0.0.jar` là **Spring Boot executable JAR** sau repackage: Boot Loader, `BOOT-INF/classes`, `BOOT-INF/lib`.
- `catalog-app-1.0.0.jar.original` là plain app JAR trước repackage; nó **không** mang đủ runtime dependencies theo layout executable Boot, không phải file deploy chính.

### 9.1. Kiểm tra archive entries

```bash
jar tf catalog-core/target/catalog-core-1.0.0.jar
jar tf catalog-app/target/catalog-app-1.0.0.jar
```

Ở core JAR cần thấy:

```text
dev/example/catalog/core/GreetingFormatter.class
```

Ở Boot app JAR cần thấy các entry tiêu biểu:

```text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/example/catalog/app/CatalogApplication.class
BOOT-INF/classes/dev/example/catalog/app/GreetingController.class
BOOT-INF/lib/catalog-core-1.0.0.jar
BOOT-INF/lib/spring-boot-3.3.13.jar
```

Đây là các **entry phải tìm trong output dài**, không phải toàn bộ kết quả `jar tf`. Những dependency khác có version resolved tương ứng BOM. Core class **không bắt buộc** nằm trực tiếp dưới `BOOT-INF/classes/dev/example/catalog/core/`: nó có thể nằm bên trong nested JAR `BOOT-INF/lib/catalog-core-1.0.0.jar`. Đó là hình thức đóng gói đúng.

### 9.2. Kiểm tra không dùng source tree khi chạy

Tạo một thư mục trống **bên ngoài repository**, sao chép đúng executable app JAR vào đó, rồi chạy từ thư mục này. Linux/macOS:

```bash
mkdir -p /tmp/catalog-artifact-test
cp catalog-app/target/catalog-app-1.0.0.jar /tmp/catalog-artifact-test/
cd /tmp/catalog-artifact-test

java -jar catalog-app-1.0.0.jar --server.port=18080
```

Đây là các lệnh sau khi đã build tại root; dùng thư mục riêng không chứa `catalog-core/`, `catalog-app/src/` hay `target/`. Nếu môi trường không cho ghi `/tmp`, chọn thư mục tạm riêng được cấp quyền.

PowerShell trên Windows:

```powershell
New-Item -ItemType Directory -Force -Path "$env:TEMP\catalog-artifact-test" | Out-Null
Copy-Item ".\catalog-app\target\catalog-app-1.0.0.jar" "$env:TEMP\catalog-artifact-test\"
Set-Location "$env:TEMP\catalog-artifact-test"

java -jar catalog-app-1.0.0.jar --server.port=18080
```

Mở **terminal thứ hai**, khi ứng dụng đã log startup thành công:

```bash
curl -fsS http://localhost:18080/hello
curl -fsS "http://localhost:18080/hello?name=Linh"
```

Hai HTTP response body, theo thứ tự:

```text
Hello, Ada!
Hello, Linh!
```

Bằng chứng: executable JAR chạy bằng JVM mà không cần Maven chạy lúc runtime và không cần source folder của core trên filesystem. `GreetingFormatter` được tải từ nested JAR của core trong app artifact.

**Giới hạn suy luận:** thử nghiệm này không đảm bảo môi trường production có cùng JDK, network, environment variables, secrets, database hay timezone. Với ví dụ không có external integration, kết quả cố tình dễ tái hiện; hệ thống thật cần smoke test và deployment validation theo contract của nó.

### 9.3. Ngăn nhầm dependency có trên local cache nhưng không có trong JAR

Trong lần chạy `java -jar` ở thư mục tách biệt, ứng dụng **không nhờ Maven đọc `~/.m2` để nạp class**. Nếu JAR thiếu `catalog-core`, test sẽ có khả năng thất bại khi ứng dụng cần `GreetingFormatter`; việc local Maven repository còn file core **không tự cứu** runtime của executable JAR.

Đây là điểm khác biệt lớn giữa:

- Maven build resolve dependency từ repository để **tạo artifact**, và
- JVM/Boot Loader nạp dependency **đã đóng gói** để chạy artifact.

## 10. Kiểm tra artifact tự chứa bằng một gate nhỏ trong CI

Một pipeline nên kiểm tra cấu trúc **và** hành vi. Trên Linux/macOS có JDK `jar` và `grep`, tại root:

```bash
set -e

APP="catalog-app/target/catalog-app-1.0.0.jar"

jar tf "$APP" | grep -q '^BOOT-INF/classes/dev/example/catalog/app/CatalogApplication.class$'
jar tf "$APP" | grep -q '^BOOT-INF/lib/catalog-core-1.0.0.jar$'
jar tf "$APP" | grep -q '^org/springframework/boot/loader/launch/JarLauncher.class$'

echo "PASS: app classes, core library and Boot loader are packaged"
```

Khi tất cả điều kiện đúng, stdout từ phần kiểm tra này là:

```text
PASS: app classes, core library and Boot loader are packaged
```

Lệnh trên dùng các tên JAR của **ví dụ**; nếu version module thay đổi, phải xác định artifact path/name từ build metadata thay vì hard-code mãi. Cũng cần kiểm tra manifest:

```bash
unzip -p catalog-app/target/catalog-app-1.0.0.jar META-INF/MANIFEST.MF
```

Tìm:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.catalog.app.CatalogApplication
```

Một số trường manifest khác có thể xuất hiện. **Gate cấu trúc không thay thế smoke test `java -jar`**. Một JAR có đủ tên entry vẫn có thể lỗi startup do cấu hình, version mismatch hoặc thiếu dependencies khác.

### Gợi ý smoke test CI an toàn hơn

- Chạy trong container/VM test riêng và dùng port không trùng workload đang hoạt động.
- Bật lệnh `java -jar` như một tiến trình có lifecycle rõ, chờ health endpoint/HTTP response với timeout do CI quản lý.
- Khi pass/fail đều dừng process, thu logs và giữ artifact checksum.
- Sau khi pass, publish **chính file đã test**; không build lại bằng profile/dependency khác rồi thay file ở deploy stage.
- Tránh chạy indefinite background server trong shell không có cleanup/timeout.

Mốc quan trọng là **đúng artifact ID**. Nếu có công cụ tạo Docker image từ layered JAR, hãy kiểm tra image được build từ đúng executable JAR đã qua gate và JVM/base image tương thích.

## 11. Gradle Multi-Project: cùng đồ thị, cách chọn build khác Maven

Gradle gọi các module là **subprojects**. `settings.gradle` khai báo module paths, còn `implementation project(':catalog-core')` tạo project dependency từ app sang core. Khi yêu cầu một task ở app, Gradle **tự đưa các task dependency cần thiết của core vào task graph**.

Điểm khác Maven:

- Maven dùng project selector `-pl` và reactor flags `-am`/`-amd`.
- Gradle dùng **fully qualified task path** như `:catalog-app:build`.
- Gradle project dependency được nối vào task graph; không có yêu cầu dùng một cờ `-am` tương đương cho trường hợp chuẩn.

Dưới đây là build configuration **thay thế Maven**, sử dụng lại bốn class Java và hai test ở mục 3.

### 11.1. `settings.gradle` ở root

```groovy
rootProject.name = 'multi-module-demo'

include 'catalog-core', 'catalog-app'
```

### 11.2. `build.gradle` ở root

```groovy
allprojects {
    group = 'dev.example'
    version = '1.0.0'

    repositories {
        mavenCentral()
    }
}
```

Root chỉ chia sẻ group, version và repository trong ví dụ; không áp dụng Spring Boot plugin cho tất cả subprojects.

### 11.3. `catalog-core/build.gradle`

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Module core có task `jar` và `test` của Java Library plugin. Nó **không** có `bootJar` vì không áp dụng Spring Boot plugin. Test dependency được giữ trong test configurations và không truyền sang app.

### 11.4. `catalog-app/build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':catalog-core')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'dev.example.catalog.app.CatalogApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot Gradle Plugin và Dependency Management Plugin phối hợp dùng BOM tương ứng Boot release; vì vậy các starter không cần version riêng trong ví dụ. Đặt Boot plugin ở **app** chứ không ở core để core vẫn tạo plain library JAR được consumer dùng qua classpath chuẩn.

### 11.5. Chọn task theo từng module

Nếu repository có Gradle Wrapper tương thích Spring Boot 3.3, từ root:

```bash
./gradlew projects
./gradlew :catalog-core:build
./gradlew :catalog-app:build
./gradlew :catalog-app:bootJar
```

Trên Windows dùng `gradlew.bat`. Nếu chưa có Wrapper, phải cài/tạo Gradle version phù hợp; không tự giả định mọi repository có file `gradlew`.

Ý nghĩa:

- `:catalog-core:build`: build + test core, không có lý do tự chạy test app.
- `:catalog-app:build`: chọn lifecycle task của app, nhưng **vẫn phải thực hiện những upstream tasks ở core** để cung cấp dependency artifact/classes.
- `:catalog-app:bootJar`: đóng executable app JAR và kéo những task cần thiết cung cấp core artifact; **không bảo đảm chạy test core** nếu task graph không yêu cầu.
- `./gradlew build` từ root có thể là **task selector** chạy task `build` ở những subproject liên quan, khác với fully qualified path `:catalog-app:build`.

Xem trước task graph mà không build:

```bash
./gradlew :catalog-app:build --dry-run
```

`--dry-run` chỉ cho thấy tasks dự định chạy, **không tạo artifact mới**, nên phải chạy build thật trước khi inspect file.

### 11.6. Kiểm tra Gradle runtime dependency

```bash
./gradlew :catalog-app:dependencies --configuration runtimeClasspath
./gradlew :catalog-app:dependencyInsight --dependency catalog-core --configuration runtimeClasspath
```

Đầu ra cần cho thấy app resolve project dependency `:catalog-core`. Nó có thể đại diện bằng **project dependency/variant** thay vì tên binary JAR từ một repository như Maven. Build tool chọn variant phù hợp với consumer, có thể kèm tasks compile/jar cần thiết.

Gradle có incremental compilation, build cache, configuration cache và task avoidance. Vì thế “task không chạy lần này” **không đồng nghĩa module độc lập**; task có thể ở trạng thái `UP-TO-DATE` hoặc lấy kết quả từ cache. Muốn kiểm tra sau một clean build, dùng `./gradlew clean :catalog-app:build` (có thể thực hiện clean rộng) hoặc setup workspace/cache test có kiểm soát theo yêu cầu tái lập.

### 11.7. Kiểm tra Boot JAR do Gradle tạo

Với version/name trong ví dụ, artifact thường ở:

```text
catalog-core/build/libs/catalog-core-1.0.0.jar
catalog-app/build/libs/catalog-app-1.0.0.jar
catalog-app/build/libs/catalog-app-1.0.0-plain.jar
```

Hai mục quan trọng:

- `catalog-core-1.0.0.jar` là plain library, không chứa Boot Loader.
- `catalog-app-1.0.0.jar` là Boot executable archive; nội dung cần có `BOOT-INF/lib/catalog-core-1.0.0.jar` và compiled app classes.
- `catalog-app-1.0.0-plain.jar` là output của task `jar` với classifier `plain` theo convention Boot Gradle Plugin. Không dùng plain JAR này để kết luận sản phẩm deploy độc lập.

Inspect:

```bash
jar tf catalog-app/build/libs/catalog-app-1.0.0.jar
java -jar catalog-app/build/libs/catalog-app-1.0.0.jar --server.port=18080
```

Gọi `curl` ở terminal khác khi ứng dụng chạy, tương tự mục 9. Có thể copy JAR Gradle ra một thư mục độc lập để test không có sibling module source.

## 12. “Build app một mình” trong Gradle nghĩa là gì?

`implementation project(':catalog-core')` có nghĩa app đang dùng **project dependency**, không phải một binary module đã phát hành độc lập. Do đó:

```bash
./gradlew :catalog-app:build
```

**Không** tương đương việc cắt thư mục `catalog-app` ra khỏi monorepo rồi yêu cầu Gradle build với file `build.gradle` hiện tại. Khi tách, cấu hình `settings.gradle` không còn khai báo `:catalog-core` và dependency `project(':catalog-core')` sẽ không resolve.

Nếu muốn phát triển/publish app độc lập khỏi source core:

1. Build và publish `catalog-core` (plain JAR kèm POM/module metadata và transitive dependencies) vào artifact repository hợp lệ.
2. Đổi dependency app từ **project dependency** sang **external module dependency**, với version cụ thể.
3. Đảm bảo repository credentials, BOM/plugin versions và toàn bộ build inputs có thể truy cập trong một checkout/workspace mới.
4. Build app tại môi trường sạch và quan sát resolved artifact/version.

Đoạn Gradle thay thế trong `catalog-app/build.gradle` sau khi core đã được publish:

```groovy
dependencies {
    implementation 'dev.example:catalog-core:1.0.0'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây chỉ là **fragment thay thế phần dependencies**, không phải build script đầy đủ; repository phải thật sự chứa `dev.example:catalog-core:1.0.0`. Không đồng thời giữ `implementation project(':catalog-core')` và `implementation 'dev.example:catalog-core:1.0.0'` nếu không có chiến lược resolution rõ ràng, vì có thể đưa cùng mã vào classpath bằng hai đường khác nhau.

**Không sửa build model của chính ví dụ đang dùng project dependency trước khi hoàn tất phép thử `:catalog-app:build`**; hai mô hình là hai tình huống khác nhau để hiểu “độc lập”.

## 13. Những mức độc lập không nên đánh đồng

### 13.1. Build chọn một mục tiêu không phải “compile không có upstream”

Trong Maven, `-pl :catalog-app -am` build core vì upstream dependency. Trong Gradle, `:catalog-app:build` có thể chạy `:catalog-core:compileJava`/`jar` theo task graph. Cả hai đều là **targeted build**, không phải “app không dùng core”.

### 13.2. Artifact có đủ Java classes không có nghĩa độc lập với external services

Executable JAR có thể chứa toàn bộ Spring Boot/Tomcat/Jackson và core library, nhưng khi chạy vẫn cần:

- JVM đúng version (ví dụ Java 17).
- Environment variables và configuration sources phù hợp.
- Database, message broker, cache hoặc HTTP services nếu ứng dụng có gọi.
- Các filesystem paths, mounted volumes, TLS certificates hoặc native libraries cần thiết.
- Port, DNS, network policy, resource quotas và quyền vận hành phù hợp.

**“Self-contained JAR” có nghĩa hẹp:** chủ yếu tự mang code/dependencies Java cần thiết cho launcher; không phải một máy ảo, container image hoặc hệ thống nghiệp vụ tự tồn tại không cần bên ngoài.

### 13.3. Module nào được test là một câu hỏi riêng

`mvn -pl :catalog-app -am test` có thể chạy test ở core và app theo reactor selection. Với Gradle, `:catalog-app:build` chạy test app nhưng **không tự hứa sẽ chạy toàn bộ test của core**: upstream tasks chủ yếu phục vụ build dependency và có thể không bao gồm `:catalog-core:test`. Nếu đổi core API hoặc behavior, CI nên có gate dành cho core test và consumer test.

### 13.4. “Chạy được trên máy tôi” chưa đủ tính tái lập

Một lần build thành công có thể phụ thuộc:

- `~/.m2`/Gradle cache có artifact nội bộ chưa publish.
- Workspace còn `target/`/`build/` từ build cũ.
- SNAPSHOT dependency được resolve khác thời điểm.
- JDK/toolchain, plugin version, environment, build profile khác CI.
- Dependency graph có conflict hoặc exclude vô tình.

Để đánh giá reproducibility, cần version hóa Wrapper, pin dependency versions theo policy, dùng môi trường sạch, kiểm tra checksum và lưu provenance. **Không nên gọi build “độc lập” chỉ vì bỏ `-am` mà nó vẫn pass nhờ cache.**

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh và xử lý |
| --- | --- | --- |
| `mvn -pl :catalog-app package` báo không resolve `catalog-core` | Core không nằm trong reactor đã chọn và chưa có trong repository | Dùng `-am` hoặc publish/install core trước; đừng xóa dependency |
| Chạy `mvn -pl :catalog-app ...` thành công ở laptop nhưng fail CI | Local Maven cache có core/parent phiên bản cũ | Build trên repository sạch, dùng `-am` hoặc artifact repository được quản lý |
| `mvn -pl :catalog-core -am verify` vẫn build app | Selection hoặc parent/aggregator có cấu hình khác dự kiến | Kiểm tra lệnh thực tế, Maven reactor summary và dependency graph |
| Core thay đổi nhưng app dùng behavior cũ | Resolve từ local repository hoặc cached version, không dùng source core mới | Xem artifact coordinates, reactor selection, dependency tree và timestamp/version |
| App dùng `@Component` của core nhưng không inject được | Package core nằm ngoài component scan, hoặc implementation chưa đóng gói | Khai báo bean/scan hợp lệ; kiểm tra dependency JAR và runtime classpath |
| Gradle `:catalog-app:build` chạy task ở core | `implementation project(':catalog-core')` tạo task dependencies | Đây là behavior đúng; không nhầm targeted build với zero upstream work |
| Gradle báo `Project with path ':catalog-core' could not be found` | Đã tách app khỏi `settings.gradle` nhưng vẫn dùng project dependency | Publish core rồi dùng external module coordinate hoặc giữ multi-project settings |
| Gradle task `:catalog-core:jar` báo `UP-TO-DATE` | Incremental build/cache | Đọc task graph và inputs; thực hiện clean/cache-controlled build nếu cần |
| App Boot JAR không có `BOOT-INF/lib/catalog-core-...jar` | Dependency bị exclude/scope sai, dùng nhầm plain app JAR hoặc plugin packaging khác | Xem `jar tf` và app dependency graph, chọn đúng `bootJar`/`repackage` |
| `java -jar` báo `NoClassDefFoundError` từ core | Core chưa được đóng vào app JAR hoặc classpath bị đổi | Kiểm tra nested library JAR, version và Boot loader; rebuild bằng plugin |
| Plain core JAR chứa `BOOT-INF/classes` | Boot plugin repackage nhầm library | Giữ core plain `jar`, chỉ app dùng Boot plugin |
| `java -jar catalog-app...jar` chạy ở root nhưng fail trong thư mục khác | Relative file/resource path hoặc config đang phụ thuộc source cwd | Dùng classpath resources/config bên ngoài rõ ràng; tránh tham chiếu file repo không portable |
| Artifact chạy local nhưng không kết nối DB production | External config/network/secrets khác nhau | Không kết luận từ classpath; kiểm tra deployment dependencies, health và credentials |
| Có nhiều version `catalog-core` trong app JAR | Trùng khai báo dependency, nhầm project/external coordinates hoặc custom packaging | Đọc `BOOT-INF/lib` và dependency tree; giải quyết conflict và pin versions |
| Sau đổi classifier, pipeline deploy `-plain.jar` | Script dựa vào glob/tên file | Chọn chính output `bootJar` hoặc `spring-boot:repackage`, kiểm tra manifest |

### Quy trình debug ưu tiên

1. Đọc **câu lệnh**: Maven `-pl`/`-am` hay Gradle task path nào đã chạy?
2. Xem **graph**: module nào phụ thuộc module nào, dependency version/scope/variant?
3. Xác định **đúng artifact**: core library JAR hay app executable JAR, tên/version/classifier.
4. Chạy **clean targeted build** tại root với lựa chọn đúng.
5. Kiểm tra **test result của từng module**, không chỉ project summary.
6. Kiểm tra **JAR content**: app classes, core library, Boot Loader và manifest.
7. Copy app JAR ra **thư mục không có repository source** và chạy `java -jar`.
8. Nếu cần source independence, thử build trên environment sạch với **đã publish parent và core**, không dùng nguồn/cache cũ.
9. Lưu **checksum artifact**, CI logs, runtime smoke test và kết quả dependency scanning.

## 15. Một số bài tập tự kiểm tra

**Tình huống A.** Chạy `mvn -pl :catalog-app -am clean verify` thành công. Điều đó chứng minh app không phụ thuộc core?

*Đáp án:* Không. `-am` chính là cờ yêu cầu Maven build các dependency upstream trong reactor, bao gồm core. Kết luận đúng là build theo tập module liên quan thành công.

**Tình huống B.** `mvn -pl :catalog-app verify` thành công sau khi trước đó có `mvn install` ở máy cá nhân. Bạn đã chứng minh build độc lập chưa?

*Đáp án:* Chỉ chứng minh app có thể resolve core artifact đã cài trong local repository. Muốn kiểm tra khả năng build từ checkout độc lập, cần repository cung cấp đầy đủ parent/core và môi trường sạch; phải xác nhận version dùng thật.

**Tình huống C.** `./gradlew :catalog-app:build` vẫn hiển thị `:catalog-core:compileJava`. Gradle bỏ qua yêu cầu chỉ build app?

*Đáp án:* Không. Bạn chỉ chọn task lifecycle của app, còn project dependency core được build vì đó là input cần thiết để app biên dịch/chạy. Task graph là hành vi đúng.

**Tình huống D.** File app executable JAR có `BOOT-INF/lib/catalog-core-1.0.0.jar`. Nó có thể chạy trên server không có source core?

*Đáp án:* Có thể, nếu JVM/config/dependencies còn lại phù hợp. Trên Spring Boot executable JAR chuẩn, core library đã được đóng gói. Hãy copy đúng file ra môi trường tách biệt, chạy và smoke test thay vì chỉ suy từ tên entry.

**Tình huống E.** Có nên áp dụng Spring Boot Maven Plugin `repackage` cho cả `catalog-core` và `catalog-app` cho “đồng bộ”?

*Đáp án:* Không. Core là plain library JAR được app phụ thuộc; executable Boot archive đặt app classes dưới `BOOT-INF/classes` và không thay thế library artifact thông thường. Chỉ app (có main method) cần `repackage`.

**Tình huống F.** Core có các JUnit test nhưng Gradle `:catalog-app:build` pass. Có thể chắc rằng core test đã chạy?

*Đáp án:* Không. Project dependency tạo task compile/jar cần cho app, không buộc toàn bộ `:catalog-core:test`. CI cần chạy core test riêng hoặc chọn phù hợp task graph.

**Tình huống G.** App JAR đã copy ra thư mục khác, `java -jar` pass, nhưng service không kết nối được Redis khi deploy. App có “không độc lập” không?

*Đáp án:* Về Java classpath, artifact có thể tự chứa; về vận hành, nó vẫn phụ thuộc Redis và cấu hình/network. Phải ghi rõ **tiêu chí độc lập** đang kiểm tra, không gộp hai kết luận.

**Tình huống H.** Cần build core và các module tiêu thụ nó để bắt lỗi API sau khi sửa core. Dùng Maven option nào?

*Đáp án:* `-pl :catalog-core -amd` chọn dependents theo reactor. Tùy graph/lifecycle, cần kết hợp dependency modules và test phases phù hợp; kiểm tra reactor log thực tế.

**Tình huống I.** Muốn tách `catalog-app` thành repository riêng, nhưng `build.gradle` vẫn dùng `implementation project(':catalog-core')`. Điều gì cần thay?

*Đáp án:* Publish core thành versioned artifact, đổi sang `implementation 'dev.example:catalog-core:1.0.0'`, cấu hình repository và giữ project dependency chỉ khi cùng multi-project build.

**Tình huống J.** Hai CI job dùng cùng source nhưng app JAR checksum khác nhau. Có thể kết luận module không độc lập không?

*Đáp án:* Chưa. Chênh lệch có thể do timestamps, toolchain, SNAPSHOT, dependency resolution, build metadata hoặc file resources. Cần phân tích reproducibility riêng; kiểm tra dependency versions, cấu hình archive và plugin.

## 16. Checklist nghiệm thu sản phẩm từ một module

**Trước build:**

- Xác định module đích và dependency graph hướng upstream/downstream.
- Chọn Maven `-pl/-am` hoặc Gradle fully qualified task path; tránh build nhầm mọi subproject.
- Xác định Java toolchain, Spring Boot plugin, version của các internal modules.
- Tách application module khỏi library modules; không repackage library để dùng làm dependency.

**Sau build:**

- Chỉ các module/task cần thiết được thực hiện; đọc reactor summary/Gradle task graph.
- Test core và app được thực thi theo policy; không suy từ việc app test pass rằng mọi sibling tests đã chạy.
- Artifact app là **executable Boot JAR**, không phải plain library JAR hoặc `.jar.original`/`-plain.jar`.
- `jar tf` cho thấy `BOOT-INF/classes`, `BOOT-INF/lib/catalog-core-...jar`, Boot Loader; manifest `Main-Class`/`Start-Class` hợp lệ.
- Không có các thư viện nội bộ bị exclude, duplicate hoặc resolve sai version.

**Kiểm thử độc lập sau build:**

- Sao chép JAR vào thư mục sạch không có source repository và chạy bằng JVM tương thích.
- Smoke test endpoint hoặc workflow chính, xác nhận code core thực sự chạy.
- Tài liệu hóa các điều kiện ngoài JAR: env, secrets, database, broker, ports, filesystem, network, TLS.
- Nếu mục tiêu là build từ source độc lập, chạy ở môi trường có **published parent/core artifacts** và không sử dụng source/cache ngẫu nhiên.
- Giữ logs, dependency tree, artifact digest và test evidence; CI deploy đúng tệp đã qua QA.

**Kết luận:** **Build riêng một module** là thao tác chọn phạm vi công việc của build tool; nó không xóa quan hệ phụ thuộc. **Artifact độc lập về Java runtime** là một kết luận khác, phải kiểm tra nội dung executable JAR và chạy nó ngoài repository. **Build từ source độc lập với sibling repository** còn cần dependency/parent đã publish và build inputs có thể resolve trong môi trường sạch. Với Spring Boot multi-module, cách thực tiễn là giữ **core như plain library JAR**, **app như Boot executable JAR**, dùng `-pl :app -am` hoặc `:app:build` để build đúng dependency graph, rồi chứng minh artifact bằng **archive inspection và smoke test**.

### Tài liệu chính thức

- Apache Maven — Guide to Working with Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
- Gradle — Structuring Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds_intermediate.html
- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot — Use an Application as a Dependency: https://docs.spring.io/spring-boot/how-to/build.html