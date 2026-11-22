# Phân biệt Maven parent, aggregator và dependency giữa các module trong Spring Boot

## 1. Vấn đề: cùng nằm trong một repository không có nghĩa cùng một quan hệ

Một dự án Spring Boot lớn có thể tách thành `domain` (mô hình/nghiệp vụ dùng chung), `web-app` (ứng dụng HTTP), `batch` (xử lý nền) và một số thư viện tích hợp. Maven hỗ trợ tổ chức chúng bằng **nhiều project/POM**, nhưng có **ba loại quan hệ hoàn toàn khác nhau** cần phân biệt:

1. **Parent / inheritance**: một POM con có `<parent>` trỏ đến parent POM để **kế thừa cấu hình** như group/version mặc định, properties, dependencyManagement và pluginManagement.
2. **Aggregator / aggregation**: một POM có `<modules>` liệt kê các đường dẫn module để Maven **gom và xây dựng trong một reactor**. Reactor sắp xếp các project theo quan hệ build thực tế.
3. **Inter-module dependency**: project A khai báo `<dependencies><dependency>...B...</dependency></dependencies>` để **sử dụng artifact và class của module B** trên classpath thích hợp.

Ba quan hệ này có thể tồn tại cùng lúc, hoặc chỉ tồn tại riêng lẻ.

| Quan hệ | Khai báo ở đâu? | Chức năng chính | Có tự đưa class module khác lên classpath không? |
|---|---|---|---|
| Parent | POM **con**: `<parent>` | Kế thừa cấu hình build | **Không**, chỉ vì là parent |
| Aggregator | POM **gom**: `<modules>` | Chọn những project cùng tham gia reactor | **Không**, chỉ vì nằm cùng modules |
| Dependency | POM **module cần dùng**: `<dependencies>` | Biểu diễn quan hệ sử dụng artifact; xác định classpath và thứ tự build | **Có**, khi scope và artifact phù hợp |
| Dependency management | POM quản lý: `<dependencyManagement>` | Quản lý version/scope cho dependency **nếu được khai báo/sử dụng** | **Không** tự thêm dependency |
| Plugin management | Parent/POM: `<pluginManagement>` | Quản lý version/cấu hình mặc định cho plugin | **Không** tự áp dụng mọi plugin/task |

**Câu ghi nhớ:** `<parent>` là **“kế thừa ai?”**; `<modules>` là **“build cùng ai?”**; `<dependencies>` là **“dùng mã của ai?”**. Những câu hỏi này không thể thay thế cho nhau.

## 2. Mô hình hình học: ba loại cạnh trong một dự án

Ví dụ repository:

```text
acme-platform/
├── pom.xml                     (parent + aggregator)
├── domain/
│   ├── pom.xml                 (library)
│   └── src/main/java/...
└── web-app/
    ├── pom.xml                 (Spring Boot application)
    └── src/main/java/...
```

Có thể vẽ **ba sơ đồ độc lập**:

```text
INHERITANCE (quan hệ <parent>)
       acme-platform
          /    \
       domain  web-app

AGGREGATION (quan hệ <modules>)
  acme-platform reactor
       +-- domain
       +-- web-app

DEPENDENCY (quan hệ <dependency>)
  web-app ----------> domain
  [sử dụng class Greeter từ domain]
```

Ở ví dụ trên root POM **vừa** là parent **vừa** là aggregator, nhưng điều đó **không tự sinh** mũi tên dependency từ `web-app` sang `domain`. Mũi tên cuối chỉ xuất hiện nếu POM `web-app` khai báo dependency vào artifact `domain`.

**Phân biệt build order với dependency graph:** Reactor có thể build `domain` trước `web-app` vì nhận thấy dependency module này. Nó **không** cần bạn đặt `domain` trước trong danh sách `<modules>` nếu quan hệ dependency được khai báo đúng.

## 3. Parent POM: kế thừa cấu hình, không phải cơ chế gom module

### 3.1. Khai báo parent như thế nào?

Trong `domain/pom.xml`:

```xml
<parent>
    <groupId>com.example.acme</groupId>
    <artifactId>acme-platform</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

Maven tìm parent POM có tọa độ `com.example.acme:acme-platform:1.0.0-SNAPSHOT`. `<relativePath>../pom.xml</relativePath>` là đường dẫn **từ thư mục chứa POM con** đến file POM parent trong source checkout. Nếu không khai báo `relativePath`, Maven mặc định kiểm tra `../pom.xml`; nhưng ghi rõ trong ví dụ giúp người đọc thấy ý định.

Khi **parent là artifact bên ngoài** đã được publish, ví dụ Spring Boot starter parent, thường dùng `<relativePath/>` để Maven không cố suy luận một parent POM nằm ở thư mục cha trong repository hiện tại:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>
```

Hai đoạn trên nói về **hai cấp khác nhau**: root `acme-platform` có thể kế thừa `spring-boot-starter-parent`; các module con kế thừa `acme-platform`. Một POM Maven chỉ khai báo **một `<parent>` trực tiếp**, nhưng kế thừa được cấu hình qua **chuỗi parent nhiều tầng**.

### 3.2. Parent kế thừa những gì?

Tùy POM và Maven model, các nội dung có thể được kế thừa/ghép gồm:

- `groupId` và `version` của project nếu con không ghi đè.
- `properties` như `java.version`, `project.build.sourceEncoding`.
- `dependencyManagement` và `pluginManagement`.
- Một số `dependencies` và cấu hình plugin/execution đặt ở phần áp dụng trực tiếp của parent.
- Cấu hình build, repositories và reporting phù hợp theo quy tắc inheritance của Maven.

**Không phải mọi phần của parent được sao chép nguyên xi.** POM con có `artifactId` riêng, có thể ghi đè nhiều thuộc tính; `<modules>` trong parent là danh sách cho aggregator của parent, **không phải danh sách module tự sinh ở mọi POM con**.

Dùng `./mvnw -pl :web-app help:effective-pom` để xem cấu hình hiệu lực đã hợp nhất từ Super POM, Spring Boot parent, root parent và POM con. Nếu máy chưa có Maven Wrapper, dùng `mvn` theo phiên bản do tổ chức quy định.

### 3.3. Tại sao parent thường có packaging=pom?

Parent dùng để chứa metadata/cấu hình thay vì biên dịch một thư viện Java cụ thể, nên thường khai báo:

```xml
<packaging>pom</packaging>
```

Parent POM có thể được `install` hoặc `deploy` như **POM artifact**, để project con ở repository khác vẫn resolve được cấu hình parent. Nó **không** tạo class Java của một module con chỉ vì cùng nằm trong cây thư mục.

Trong ví dụ đa module, root POM có `packaging=pom`, còn `domain` và `web-app` có packaging `jar`. Các module con không kế thừa packaging kiểu `pom` để làm archive chính của chúng: cần đặt packaging đúng vai trò của mỗi module khi cần, và hiểu default Maven packaging là `jar`.

### 3.4. Bẫy: dependencies trong parent khác dependencyManagement

Nếu root parent đặt:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

thì declaration này có thể **được các POM con kế thừa** như dependency thực sự. Hệ quả là `domain`, dù chỉ là thư viện Java thuần, cũng có thể nhận web starter trên classpath — điều thường không mong muốn.

Nếu chỉ muốn quản lý version chung, đặt dependency vào `<dependencyManagement>`; khi muốn module dùng thực sự, **mỗi module tự khai báo** trong `<dependencies>`. Đối với plugin Spring Boot tạo executable archive, cũng không nên áp dụng tràn lan cho library module chỉ vì parent đã quản lý được version plugin.

## 4. Aggregator POM và Maven reactor: gom project để build

### 4.1. Khai báo module theo đường dẫn

Trong root `pom.xml`:

```xml
<packaging>pom</packaging>
<modules>
    <module>domain</module>
    <module>web-app</module>
</modules>
```

`<module>domain</module>` là **đường dẫn tương đối tới project trong repository**, không phải GAV `groupId:artifactId:version`. Nó thường trùng artifactId vì tiện đọc, nhưng Maven quan tâm tới path của POM, nên tên thư mục có thể khác artifactId.

Khi đứng tại root chạy:

```bash
./mvnw clean verify
```

Maven reactor thu thập project root và các module được khai báo, tính thứ tự phù hợp, rồi chạy các goal/phase đối với những project được chọn. Không cần chạy tay `cd domain && mvn install` trước `cd web-app && mvn package` cho một reactor build đã cấu hình đúng.

**Reactor không đồng nghĩa repository:** Reactor làm việc với các project trong cùng một lần Maven invocation; Maven local repository (`~/.m2/repository`) là nơi giữ artifact đã cache/install. Trong reactor, một dependency phù hợp với module cùng phiên build có thể được resolve từ reactor build, không phải bắt buộc phải install tất cả module trước.

### 4.2. Thứ tự reactor phụ thuộc quan hệ đã “thực sự khai báo”

Maven reactor xét các quan hệ như:

- Module A có **dependency thật** tới module B trong cùng reactor.
- Module A dùng một module khác như plugin/build extension hoặc plugin dependency khi phù hợp.
- Project dùng parent nằm trong reactor.
- Thứ tự `<modules>` chỉ là **tiebreaker** khi không có quan hệ nào mạnh hơn quyết định trước sau.

Quan trọng: mục `<dependencyManagement>` hay `<pluginManagement>` **không tự làm** reactor sắp xếp như có dependency/plugin thực sự. Ví dụ root quản lý version của `domain` nhưng `web-app` không khai báo `<dependency>` tới `domain` thì Maven không tự hiểu `web-app` cần class của `domain`.

### 4.3. Aggregator và parent có thể là hai project khác nhau

Một repository có thể dùng:

```text
repo/
├── build-all/pom.xml      (aggregator: khai báo <modules>)
├── shared-parent/pom.xml  (parent: chuẩn chung, publish được)
├── domain/pom.xml         (parent = shared-parent)
└── web-app/pom.xml        (parent = shared-parent;
                           dependency = domain)
```

`build-all` có thể liệt kê `../domain` và `../web-app` trong `<modules>`, trong khi `domain` và `web-app` kế thừa `shared-parent`, **không kế thừa build-all**. Cách thiết kế này phù hợp khi tổ chức muốn tái sử dụng một corporate parent cho nhiều repository nhưng vẫn gom nhiều module khác nhau trong một reactor.

Ngược lại, một POM ở repository nội bộ có thể làm **parent** cho nhiều project nhưng **không có `<modules>`**. Nó vẫn là parent hợp lệ vì inheritance không yêu cầu aggregator.

## 5. Inter-module dependency: điều gì thực sự đưa mã dùng chung vào classpath?

Giả sử class `com.example.acme.domain.Greeter` nằm trong artifact:

```text
com.example.acme:domain:1.0.0-SNAPSHOT
```

Trong `web-app/pom.xml`, phải khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>com.example.acme</groupId>
        <artifactId>domain</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </dependency>
</dependencies>
```

Đây là dependency **trực tiếp**, tạo quan hệ compile/runtime theo scope mặc định `compile`. Nếu source `web-app` gọi `Greeter` mà chỉ có `<module>domain</module>` ở aggregator, Maven không tự đặt domain.jar lên classpath và compiler có thể báo `package com.example.acme.domain does not exist`.

Một module **phụ thuộc** module khác qua artifact version và GAV; việc chúng có cùng `<parent>` không tạo quan hệ classpath.

### 5.1. dependencyManagement chỉ quản lý version

Nếu root parent có:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.acme</groupId>
            <artifactId>domain</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

thì `web-app` có thể khai báo versionless dependency:

```xml
<dependency>
    <groupId>com.example.acme</groupId>
    <artifactId>domain</artifactId>
</dependency>
```

**Nhưng phải có dependency declaration trong `web-app`.** Chỉ đặt `domain` trong `dependencyManagement` không tự làm `Greeter` xuất hiện ở runtime classpath. Khi các module dùng version khác nhau hoặc phát hành độc lập, `${project.version}` không phải lựa chọn an toàn mặc định; phải quản lý version dependency tường minh theo quy ước release thực tế.

### 5.2. Scope và dependency bắc cầu

| Scope trong Maven | Ý nghĩa phổ biến ở module phụ thuộc |
|---|---|
| `compile` (default) | Dùng khi compile và runtime; có thể truyền dependency bắc cầu đến consumer |
| `runtime` | Cần khi chạy nhưng thường không cần trực tiếp khi compile |
| `provided` | Cần compile/test nhưng mong runtime/container ngoài cung cấp; không phải cách khai báo module dùng chung thông thường |
| `test` | Chỉ dành cho test của module đó; không trở thành main dependency cho ứng dụng khác |
| `import` | Chỉ hợp lệ khi nhập POM vào `dependencyManagement` với `type=pom`; **không** phải dependency runtime |

Ví dụ `web-app` phụ thuộc `domain` ở scope `compile`, các public API của `domain` cần được quản lý ổn định nếu module khác tiêu thụ. Một module có dependency test-only của riêng nó **không làm** các thư viện test đó tràn sang runtime của `web-app` chỉ vì `web-app` phụ thuộc module ấy.

Để xem kết quả dependency thực tế, dùng `dependency:tree` ở đúng module; đừng chỉ nhìn root `<modules>` hoặc `dependencyManagement`.

## 6. Ví dụ đầy đủ Java 17 + Spring Boot 3.5: root vừa parent vừa aggregator

Phần này xây dựng một repository **có thể build bằng Maven**, gồm một Java library module và một Spring Boot web application module. Mỗi file có tên và nội dung rõ ràng; những ví dụ về cấu hình khác ở các phần sau là **biến thể**, không được dán cộng dồn vào POM này.

### 6.1. Cây thư mục

```text
acme-platform/
├── pom.xml
├── mvnw, mvnw.cmd, .mvn/wrapper/...    # Maven Wrapper (từ Initializr hoặc tạo riêng)
├── domain/
│   ├── pom.xml
│   └── src/
│       └── main/java/com/example/acme/domain/
│           └── Greeter.java
└── web-app/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/acme/app/
        │   ├── WebApplication.java
        │   └── GreetingController.java
        └── test/java/com/example/acme/app/
            └── GreetingControllerTest.java
```

Đối với project tự tạo bằng tay chưa có Maven Wrapper, bạn có thể dùng `mvn` đã cài phù hợp; để làm việc nhóm/CI, **tạo và commit Maven Wrapper đúng cách** thay vì chỉ tạo file script giả. Những command ở dưới giả định wrapper đã tồn tại.

### 6.2. Root pom.xml — parent + aggregator

`acme-platform/pom.xml` là **POM hoàn chỉnh**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example.acme</groupId>
    <artifactId>acme-platform</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>domain</module>
        <module>web-app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.acme</groupId>
                <artifactId>domain</artifactId>
                <version>${project.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Giải thích các tầng:

- Root kế thừa Spring Boot `spring-boot-starter-parent` để có defaults Java/plugin/dependency management.
- Root là **parent của các module trong repository** nhờ phần `<parent>` của mỗi POM con (xem phần 6.3 và 6.5).
- Root là **aggregator** nhờ `<packaging>pom</packaging>` và `<modules>`.
- Root **quản lý version** của module `domain` qua `dependencyManagement`, nhưng **không tự thêm domain vào classpath** của `web-app`.
- Root **không** áp dụng trực tiếp `spring-boot-maven-plugin` để tạo executable JAR cho `domain`; plugin được đặt riêng tại module ứng dụng.

Vì tất cả module trong ví dụ kế thừa version `1.0.0-SNAPSHOT`, `${project.version}` phù hợp để quản lý version của `domain`. Nếu dự án chọn nhiều release streams/version riêng, cần sửa chiến lược version management.

### 6.3. domain/pom.xml — thư viện Java thường

`domain/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.acme</groupId>
        <artifactId>acme-platform</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>domain</artifactId>
    <packaging>jar</packaging>
</project>
```

Module này kế thừa group/version/Java config và dependency management, nhưng **không cần** Spring Boot Maven Plugin hay `spring-boot-starter-web`. Output chính của nó là thư viện Java thông thường `domain-1.0.0-SNAPSHOT.jar`, phù hợp để module khác dùng trên classpath.

### 6.4. Greeter.java — mã thuần Java 17

`domain/src/main/java/com/example/acme/domain/Greeter.java`:

```java
package com.example.acme.domain;

public final class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Lớp này không dùng Spring Framework. Nó được package thành artifact `domain` và được ứng dụng web sử dụng thông qua Maven dependency. Không vì package Java là `com.example.acme.domain` mà Maven tự nhận biết dependency; **dependency là quan hệ giữa artifact, không phải giữa tên Java package**.

### 6.5. web-app/pom.xml — ứng dụng Boot phụ thuộc domain

`web-app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.acme</groupId>
        <artifactId>acme-platform</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>web-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.acme</groupId>
            <artifactId>domain</artifactId>
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

**Điều mấu chốt nằm ở hai vị trí riêng:**

- `<dependency>domain</dependency>` ở `web-app` tạo quan hệ sử dụng `domain.jar`. Version được lấy từ `dependencyManagement` của root.
- `spring-boot-maven-plugin` chỉ được **áp dụng** ở `web-app` để tạo executable JAR; parent Spring Boot đã quản lý version/cấu hình và repackage goal thích hợp.

`web-app` không cần viết lại version của `spring-boot-starter-web` vì version được quản lý qua chuỗi `spring-boot-starter-parent` → `acme-platform` → `web-app`.

### 6.6. WebApplication.java — main class và đăng ký bean từ domain

`web-app/src/main/java/com/example/acme/app/WebApplication.java`:

```java
package com.example.acme.app;

import com.example.acme.domain.Greeter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }

    @Bean
    public Greeter greeter() {
        return new Greeter();
    }
}
```

Greeter nằm ở module khác và package `com.example.acme.domain`. Ta đăng ký `@Bean` tường minh để Spring có thể inject nó; **Maven dependency chỉ đưa class lên classpath**, không tự làm mọi class thuần Java thành Spring bean. Nếu dùng component scanning và annotation thì cần thiết kế scan boundary đúng, không nên đoán `@SpringBootApplication` sẽ quét mọi package của mọi module.

### 6.7. GreetingController.java — sử dụng class từ module domain

`web-app/src/main/java/com/example/acme/app/GreetingController.java`:

```java
package com.example.acme.app;

import com.example.acme.domain.Greeter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final Greeter greeter;

    public GreetingController(Greeter greeter) {
        this.greeter = greeter;
    }

    @GetMapping("/hello")
    public String hello(
            @RequestParam(name = "name", defaultValue = "Java") String name) {
        return greeter.greet(name);
    }
}
```

`@RequestParam` có tên tường minh `name` để không phụ thuộc vào việc tìm tham số bằng reflection trong ví dụ. Constructor injection chứng minh `Greeter` được Spring đăng ký như bean; class `Greeter` chỉ compile thành công vì **Maven có dependency thực tế từ `web-app` đến `domain`**.

### 6.8. GreetingControllerTest.java — kiểm tra module web-app

`web-app/src/test/java/com/example/acme/app/GreetingControllerTest.java`:

```java
package com.example.acme.app;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void defaultsToJava() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Java"));
    }

    @Test
    void passesQueryToDomain() throws Exception {
        mockMvc.perform(get("/hello").param("name", "Maven"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Maven"));
    }
}
```

Đây là test trong Maven project có `spring-boot-starter-test`; cần Maven/JUnit/Spring classpath, **không** phải file `javac` độc lập. Test dùng MockMvc, không cần mở cổng HTTP 8080. Nếu fail, đọc stacktrace để phân biệt lỗi compile/dependency, lỗi context/bean và lỗi assertion.

## 7. Lệnh build và kết quả có thể tự đối chiếu

### 7.1. Build cả reactor từ root

Ở root `acme-platform/`, chạy:

```bash
./mvnw clean verify
```

Maven sẽ đưa root POM, `domain` và `web-app` vào reactor. Thứ tự hợp lý là parent root trước, `domain` trước `web-app` vì `web-app` **phụ thuộc** `domain`. Dù bạn đảo thứ tự hai `<module>` trong root POM, dependency đã khai báo vẫn quyết định thứ tự cần thiết.

Nếu build thành công, các artifact thường xuất hiện:

```text
domain/target/domain-1.0.0-SNAPSHOT.jar
web-app/target/web-app-1.0.0-SNAPSHOT.jar
```

`domain` là JAR Java library thường; `web-app` là executable JAR Spring Boot vì chỉ module này áp dụng Spring Boot Maven Plugin. Tên file giả định chưa thay `finalName` hoặc classifier.

### 7.2. Chạy executable JAR sau khi build

```bash
java -jar web-app/target/web-app-1.0.0-SNAPSHOT.jar
```

Trong terminal khác, gọi:

```bash
curl -s "http://localhost:8080/hello"
curl -s "http://localhost:8080/hello?name=Maven"
```

**Response body** lần lượt là:

```text
Hello, Java
Hello, Maven
```

Đây không phải toàn bộ stdout khởi động ứng dụng; Spring Boot còn in startup logs. Nếu port 8080 đã dùng, truyền `--server.port=8081` sau tên JAR rồi gọi URL với cổng 8081.

### 7.3. Chỉ build module ứng dụng và những thứ cần thiết

```bash
./mvnw -pl :web-app -am verify
```

Trong đó:

- `-pl :web-app` (`--projects`) chọn project có `artifactId=web-app` trong reactor.
- `-am` (`--also-make`) chọn **thêm những project mà web-app cần**, ví dụ `domain` và parent trong cùng reactor khi phù hợp.
- `verify` chạy lifecycle đến phase verify cho project được chọn.

Với một checkout sạch, chạy:

```bash
./mvnw -pl :web-app verify
```

**có thể thất bại** vì dependency nội bộ `domain` chưa được build/installed/available trong repository. `-pl` một mình chọn project, **không có nghĩa** Maven tự build tất cả phụ thuộc trong reactor. Khi cùng phát triển các module, `-pl ... -am` là lựa chọn thường phù hợp.

### 7.4. Xem thứ tự và dependency graph

```bash
# Đọc dependency tree của module web-app
./mvnw -pl :web-app dependency:tree

# Xem POM hiệu lực sau inheritance
./mvnw -pl :web-app help:effective-pom

# Build chỉ library và các parent cần thiết
./mvnw -pl :domain -am verify
```

Trong dependency tree của `web-app`, bạn cần thấy `com.example.acme:domain:jar:1.0.0-SNAPSHOT` (ngoài các dependency Spring Boot) khi dependency được resolve. Nếu dự án chưa build/install domain artifact, việc chạy dependency plugin riêng lẻ có thể cần một reactor build trước, ví dụ `./mvnw -pl :web-app -am verify`.

## 8. Ví dụ Java Standard Library độc lập để kiểm tra domain trước Maven

`Greeter.java` là Java thuần. Bạn có thể tự kiểm chứng class này mà không dùng Spring, giúp phân biệt “mã thư viện chạy được” và “Maven dependency có được khai báo đúng hay không”.

Tạo thêm **file thử nghiệm ngoài source set Maven**, `examples/GreeterProbe.java`:

```java
import com.example.acme.domain.Greeter;

public class GreeterProbe {
    public static void main(String[] args) {
        System.out.println(new Greeter().greet("Maven"));
    }
}
```

Từ thư mục root (giả sử đã tạo thư mục `examples` và `out`):

```bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out \
    domain/src/main/java/com/example/acme/domain/Greeter.java \
    examples/GreeterProbe.java
java -cp out GreeterProbe
```

**Stdout chính xác:**

```text
Hello, Maven
```

Lệnh `javac` trực tiếp đưa cả hai source file vào compile classpath và đặt bytecode dưới `out/`; không sử dụng Maven reactor, parent hay dependencyManagement. Do đó thí nghiệm này xác nhận **Java code** nhưng **không** xác nhận cấu hình Maven multi-module. Nếu trên Windows, tạo `out` bằng PowerShell và nhập lệnh `javac` trên một dòng; dấu `\` nối dòng ở trên dành cho shell Unix/macOS.

Khi chuyển sang Maven `web-app`, không có lệnh javac thủ công này: **POM dependency** mới có trách nhiệm khiến compiler thấy thư viện `domain` trong quá trình build chuẩn.

## 9. Spring Boot starter parent, BOM và parent riêng của tổ chức

### 9.1. Một POM không có hai parent trực tiếp

POM Maven chỉ có một `<parent>` trực tiếp. Với dự án nhiều module dùng Spring Boot, hai chiến lược phổ biến:

**Chiến lược A — root kế thừa Spring Boot starter parent** (đã dùng ở mục 6):

```text
spring-boot-starter-parent:3.5.16
                |
                v
        acme-platform (root)
             /     \
          domain   web-app
```

Các module con kế thừa Boot dependency management và plugin defaults thông qua root. Nếu dự án cần tổ chức parent chung, có thể đổi mô hình:

**Chiến lược B — root kế thừa corporate parent** và **import Spring Boot BOM** trong `dependencyManagement` của root:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn thay thế** trong parent không kế thừa Boot starter parent; không phải một POM hoàn chỉnh và **không phải** một dependency runtime của ứng dụng. Với corporate parent, phải xem riêng cấu hình compiler Java 17, encoding UTF-8, test plugins và Spring Boot Maven Plugin `repackage` vì **import BOM chỉ mang dependency management, không tự mang plugin management/executions của starter parent**.

### 9.2. Khi nào đặt plugin ở parent?

`<pluginManagement>` chỉ **quản lý version và cấu hình mặc định** để các module áp dụng plugin có thể dùng thống nhất. Nó không có nghĩa mọi module sẽ thực hiện `repackage`.

Nếu đặt `spring-boot-maven-plugin` trong `<build><plugins>` của root parent và để execution được kế thừa, thư viện `domain` có thể cố thực hiện repackage dù không có main class. Điều đó có thể gây lỗi build hoặc tạo artifact executable không phù hợp để dùng làm dependency.

Với mô hình “library + ứng dụng”, cách rõ ràng là **chỉ khai báo áp dụng `spring-boot-maven-plugin` ở `web-app`**, còn version/cấu hình quản lý qua starter parent hoặc `pluginManagement` của root khi dùng corporate parent.

Điều này phù hợp khuyến nghị Spring Boot: **không nên sử dụng executable Boot JAR làm dependency thư viện**. Trong executable JAR, class thường nằm ở `BOOT-INF/classes`; nếu bạn muốn chia sẻ code, hãy chuyển code đó sang module/library JAR thường (`domain`), rồi khai báo dependency vào library.

### 9.3. Parent và BOM cũng không thay thế aggregation

Một POM chỉ import BOM Spring Boot nhưng không có `<modules>` **không tự gom** các module trong repository vào reactor. Ngược lại, một aggregator có `<modules>` nhưng không import BOM hoặc kế thừa parent phù hợp **không tự quản lý** version Spring Boot starter cho các child.

## 10. Các biến thể thiết kế multi-module thường gặp

### 10.1. Một root làm cả parent và aggregator

Phù hợp nhóm nhỏ hoặc một sản phẩm có một nhịp phát hành:

```text
root pom:
  <parent> Spring Boot starter parent
  <packaging>pom</packaging>
  <modules>domain, web-app</modules>
  <dependencyManagement>internal modules</dependencyManagement>

domain pom:
  <parent>root</parent>
  ordinary jar

web-app pom:
  <parent>root</parent>
  <dependencies>domain + Boot starter</dependencies>
  Spring Boot plugin applied
```

Ưu điểm là đơn giản, dùng một version chung; đánh đổi là các module có thể bị ghép chặt vào chu kỳ nâng cấp/version của toàn repository.

### 10.2. Parent riêng, aggregator riêng

Phù hợp nhiều repository/đơn vị dùng một corporate parent:

```text
org-parent (đã publish POM)
   ^                  ^
   |                  |
domain           web-app
   ^                  |
   +------------------+   dependency web-app -> domain

all-modules/pom.xml
  <modules>../domain, ../web-app</modules>
  packaging=pom
  (không nhất thiết là parent của hai module)
```

Ví dụ `all-modules/pom.xml` chỉ gom build, còn mỗi module khai báo parent riêng. Reactor vẫn cần dependency thực tế để sắp xếp đúng. Nếu `org-parent` không nằm trong reactor, Maven phải tải parent từ repository hoặc tìm đúng `relativePath`.

### 10.3. Module dùng chung phát hành phiên bản độc lập

Giả sử `domain` được publish dưới `com.example.acme:domain:2.1.0` và ứng dụng dùng `web-app:1.0.0`. Khi đó dependency nên trỏ **đúng version domain phát hành**; không dùng mù quáng `${project.version}`. Các project có thể nằm trong một repository hoặc các repository riêng tùy chính sách release.

Với source đóng chung repository nhưng version độc lập, reactor build được các module đang khai báo tương thích GAV/version; nếu version dependency không khớp với artifact module hiện tại, Maven có thể tải bản từ repository thay vì dùng module trong reactor như bạn tưởng. Khi nâng version, kiểm tra dependency tree và release process.

## 11. Maven reactor: các lệnh thường cần

| Lệnh | Ý nghĩa |
|---|---|
| `./mvnw clean verify` | Chạy lifecycle đến `verify` trên root + các module trong reactor |
| `./mvnw -pl :web-app -am verify` | Chọn `web-app` và build những project cần thiết trong cùng reactor |
| `./mvnw -pl :domain -amd test` | Chọn `domain` và thêm những module phụ thuộc nó trong reactor |
| `./mvnw -pl :domain verify` | Chỉ project `domain`; không tự chọn phụ thuộc/dependents |
| `./mvnw -N validate` | Non-recursive: không duyệt module; chỉ xử lý current POM |
| `./mvnw -rf :web-app verify` | Resume reactor từ `web-app`; không coi đây là thay thế việc rebuild các dependency cần thiết |
| `./mvnw -pl :web-app help:effective-pom` | Đọc cấu hình effective POM của ứng dụng |
| `./mvnw -pl :web-app dependency:tree` | Quan sát dependency thực tế nếu có artifact/resolution phù hợp |
| `./mvnw -pl :web-app -am install` | Build/install các project được chọn để artifact nằm trong local repository |

`-amd` là `--also-make-dependents`, thích hợp khi sửa một thư viện và muốn chạy test ở những module sử dụng nó. `-am` là `--also-make`, thích hợp khi tập trung build một app cần các library modules. `-pl` dùng project selector bằng đường dẫn hoặc `:artifactId`; không nên đoán rằng chỉ cần chọn artifactId là Maven sẽ tự thêm dependency graph khi thiếu `-am`.

**Lưu ý build chọn lọc:** Các lệnh `-pl`, `-am`, `-amd` điều khiển **reactor selection**, không thay đổi `pom.xml` hay scope dependency đã khai báo. Chúng cũng không làm project chưa nằm trong reactor trở thành module mới. Nếu muốn build từ source của module khác, aggregator phải đưa project đó vào reactor (hoặc phải có một build được kết nối phù hợp).

## 12. Các lỗi thường gặp khi phân biệt parent, aggregator và dependency

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
|---|---|---|
| `web-app` báo không tìm thấy `Greeter` | Chỉ có `domain` trong `<modules>`, thiếu `<dependency>` ở `web-app` | Thêm dependency GAV đúng, build bằng `-am` từ root |
| Maven không tìm được parent POM | `<parent>` tọa độ sai, `relativePath` sai, parent chưa publish | Kiểm tra GAV/relativePath, root checkout, Maven repository |
| Root `mvn verify` không xây dựng mọi module | Thiếu module path trong `<modules>` hoặc module nằm ngoài reactor | Bổ sung đúng relative path, gọi từ đúng root/aggregator |
| Build module con riêng lẻ không resolve dependency nội bộ | Chưa install dependency hoặc build không chọn reactor dependencies | Dùng `-pl :web-app -am verify` hoặc install artifact phù hợp |
| `domain` chứa Spring Boot executable JAR | Plugin repackage được áp dụng ở library hoặc parent không giới hạn inheritance | Chỉ áp dụng Boot plugin ở module app; giữ domain plain JAR |
| `domain` bị kéo starter-web vào classpath | Parent khai báo starter ở `<dependencies>` trực tiếp | Chuyển version management vào `dependencyManagement` và khai báo starter ở module thật sự dùng |
| Có `dependencyManagement` nhưng không thấy domain ở dependency tree | Version management không tự tạo dependency | Thêm `<dependency>` thực tế ở consumer |
| Reactor không build theo thứ tự `<modules>` | Có dependency/parent/plugin relationship làm reactor sort lại | Đây thường là đúng; kiểm tra đường dependency thay vì ép thứ tự bằng list |
| Reactor báo vòng lặp dependency | `domain` phụ thuộc `web-app` trong khi `web-app` phụ thuộc `domain` | Tách API chung sang module thứ ba, xóa chiều phụ thuộc ngược |
| POM con tự đặt version khác parent làm nội bộ mismatch | Module releases không cùng version nhưng dependency dùng `${project.version}` | Đồng bộ version theo chính sách hoặc khai báo version dependency chính xác |
| Chỉ thêm Spring Boot BOM vào parent rồi kỳ vọng executable JAR | BOM quản lý library versions, không tự thêm packaging plugin | Áp dụng Spring Boot Maven Plugin + repackage execution đúng module |
| Parent dùng `<pluginManagement>` nhưng plugin không chạy | Plugin mới được quản lý version, chưa được áp dụng | Đưa plugin vào `<build><plugins>` ở module cần dùng |
| `java -jar domain.jar` không chạy | Domain là Java library không có application entry point | Chạy executable JAR của `web-app`; domain chỉ được nạp qua dependency |
| File build đúng ở local nhưng CI fail | CI build từ thư mục con, thiếu parent/module hoặc dùng Maven/JDK khác | Chạy wrapper từ root, kiểm tra reactor summary và artifacts |
| Dependency tree có phiên bản bất ngờ | BOM, direct/nearest dependency mediation hoặc version bị override | Xem `dependency:tree` và effective POM để tìm nguồn quản lý version |

### 12.1. Giải quyết circular dependency bằng cấu trúc module

Thiết kế xấu:

```text
web-app -> domain
domain  -> web-app
```

Maven reactor không thể có thứ tự build topo hợp lệ khi hai module cần class của nhau. Đừng “sửa” bằng cách đổi thứ tự `<modules>`; cách đúng là tách API/contract dùng chung ra một module không phụ thuộc app:

```text
             shared-api
             ^        ^
             |        |
          domain   web-app
             ^        |
             +--------+
```

Chỉ tạo những cạnh thật sự cần thiết, giữ chiều phụ thuộc từ application layer về domain/library thay vì ngược lại.

## 13. Thực nghiệm: sửa một quan hệ tại một thời điểm để thấy khác biệt

**Thí nghiệm A — bỏ dependency trong web-app:** Giữ root `<modules>domain, web-app</modules>` và parent inheritance, nhưng **tạm bỏ** `<dependency>com.example.acme:domain</dependency>` ở `web-app`. Khi source vẫn import `Greeter`, compile `web-app` sẽ thất bại vì thiếu classpath dependency. Kết luận: aggregation/inheritance không thay thế dependency.

**Thí nghiệm B — bỏ module khỏi aggregator:** Giữ `<parent>` trong `domain` và `web-app`, giữ dependency vào domain, nhưng tạm bỏ `<module>domain</module>` ở root. Reactor không còn build `domain` từ source theo root aggregator; `web-app` chỉ có thể resolve domain nếu artifact tương ứng đã có trong local/remote repository. Kết luận: inheritance và dependency vẫn tồn tại, nhưng aggregation quyết định tập project build cùng nhau.

**Thí nghiệm C — parent khác aggregator:** Cho hai module kế thừa corporate parent ở repository trong khi một POM độc lập gom chúng bằng `<modules>`. Maven vẫn build cùng reactor nếu các đường dẫn đúng. Kết luận: aggregator không bắt buộc là parent.

**Thí nghiệm D — chỉ management, không use:** Trong root, giữ `<dependencyManagement>domain version</dependencyManagement>` nhưng bỏ declaration dependency trong `web-app`. Dependency tree không tự thêm `domain`. Kết luận: version management không phải yêu cầu classpath.

**Thí nghiệm E — đảo thứ tự module:** Trong `<modules>`, đặt `web-app` trước `domain` nhưng giữ dependency thực tế. Maven reactor vẫn phải build `domain` trước `web-app`. Kết luận: quan hệ dependency thực tế quan trọng hơn thứ tự gõ trong XML.

Các thử nghiệm thay đổi cấu hình ở **bản sao project** hoặc branch thử nghiệm; sau mỗi lượt hãy **khôi phục POM gốc** rồi chạy `./mvnw clean verify`. Không làm các lượt thay đổi cùng lúc vì sẽ khó quy nguyên nhân.

## 14. Thiết kế parent và module khi phát triển Spring Boot thực tế

**Quản lý version:** Khi tất cả module phát hành theo cùng một release, parent chung và `${project.version}` có thể giúp tránh sai version. Khi module phát hành độc lập, phải có chiến lược dependency coordinates/version riêng, release notes và compatibility matrix.

**Ranh giới module:** Đặt logic không phụ thuộc Spring Boot web vào `domain`/`shared-core` khi hợp lý. Cho phép ứng dụng/adapter phụ thuộc domain, hạn chế domain phụ thuộc ngược app hoặc phụ thuộc trực tiếp các controller/server libraries.

**Build plugin:** Chỉ những module có entry point Spring Boot cần repackage executable JAR/WAR. Thư viện dùng chung phải tạo artifact library mà compiler/consumer tìm được class trực tiếp, không phải Boot executable archive.

**Quy tắc kiểm thử:** Unit test có thể nằm trong domain module; controller/context test nằm ở app module. Chạy toàn reactor ở CI để thấy cả sự cố API giữa module. `-pl -am` hữu ích cho vòng lặp phát triển nhanh, nhưng không nên bỏ test ở dependents của shared library trước release.

**Tái lập:** Commit POM/module paths/wrapper, pin Java version, dùng repository tin cậy, kiểm soát SNAPSHOT và không dựa vào trạng thái `~/.m2/repository` chưa xác định. Một máy có artifact domain cũ trong local repo có thể vô tình che lấp cấu hình thiếu `-am`.

**Corporate parent:** Nếu tổ chức có một parent bắt buộc, import Boot BOM cho dependency versions và cấu hình compiler/plugins riêng; đừng khai báo hai `<parent>`. Dù corporate parent là remote artifact, aggregator vẫn có thể nằm ở root repository.

**CI/CD:** Một quy trình release nên build cả những module liên quan trong reactor, chạy `verify`, kiểm tra `Reactor Summary` và chọn đúng `web-app/target/*.jar` để deploy. Không đưa `domain/target/*.jar` vào pipeline chạy `java -jar` như ứng dụng.

## 15. Checklist kiểm tra cấu trúc đa mô-đun

1. **Parent GAV:** Mỗi module trỏ đúng parent, `relativePath` đúng hoặc parent đã publish.
2. **Packaging:** Parent/aggregator là `pom`; library là `jar`; Spring Boot app là `jar` hoặc `war` theo yêu cầu.
3. **Aggregation:** Root liệt kê đúng các module muốn build trong `<modules>`, đường dẫn tồn tại.
4. **Classpath:** Mọi module dùng class của module khác đều có `<dependency>` đúng tọa độ, scope và version.
5. **Version management:** `dependencyManagement` chỉ quản lý version, không bị nhầm với dependency thật.
6. **Plugin management:** `pluginManagement` quản lý nhưng không thay việc áp dụng plugin ở module cần dùng.
7. **Reactor:** Chạy `-pl`/`-am`/`-amd` đúng mục tiêu, quan sát `Reactor Summary`.
8. **Spring Boot packaging:** Chỉ app module dùng `spring-boot-maven-plugin` để repackage; library vẫn là plain JAR.
9. **Build từ checkout sạch:** `./mvnw clean verify` ở root phải thành công với JDK phù hợp và repository khả dụng.
10. **Tests:** Unit tests theo module và integration tests ứng dụng xác nhận API giữa module.
11. **Dependency graph:** `dependency:tree` của web-app thấy domain và không chứa những dependency không mong đợi.
12. **Effective POM:** Kiểm tra inheritance thực tế thay vì đoán plugin/dependency version.
13. **Không vòng lặp:** Module dependency graph không có chu trình.
14. **Phát hành:** Version internal modules và hướng publish/install đúng với repository/CI policy.

### Nguồn tài liệu chính thức

- [Apache Maven — Introduction to the POM: Inheritance & Aggregation](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Guide to Working with Multiple Modules & Reactor](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Dependency Mechanism và dependencyManagement](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Spring Boot 3.5 Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html)
- [Spring Boot 3.5 — Build & executable JAR as a dependency](https://docs.spring.io/spring-boot/3.5/how-to/build.html)

**Ghi nhớ:** `<parent>` nói **kế thừa cấu hình**, `<modules>` nói **tham gia reactor**, còn `<dependencies>` mới tạo **quan hệ sử dụng mã và classpath**. Một root có thể vừa là parent vừa là aggregator, nhưng Maven không tự nối dependency giữa các module. Đối với Spring Boot multi-module, giữ các library ở dạng JAR thường và chỉ repackage module ứng dụng.
