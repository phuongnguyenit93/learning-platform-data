# Xây dựng Maven reactor với -pl, -am và thứ tự phụ thuộc

## 1. Mục tiêu: build đúng phần cần thiết của dự án Spring Boot đa mô-đun

Trong một dự án Java/Spring Boot lớn, mỗi Maven module có thể tạo một artifact riêng. Một ứng dụng web có thể dùng module nghiệp vụ; module nghiệp vụ lại dùng module core. Nếu chạy Maven bằng tay ở các thư mục theo thứ tự ngẫu nhiên, build dễ dùng nhầm artifact cũ trong `~/.m2/repository` hoặc lỗi không tìm được dependency.

**Maven reactor** giải quyết phần điều phối đó: Maven thu thập các projects thuộc reactor, sắp xếp theo quan hệ phụ thuộc, rồi chạy lifecycle/goal cho tập project đã chọn.

Ba cờ quan trọng nhất:
- `-pl`/`--projects`: **chọn** một hoặc nhiều modules.
- `-am`/`--also-make`: với `-pl`, **build thêm những modules upstream** mà selected modules cần.
- Reactor sorting: giữ **thứ tự phụ thuộc** hợp lệ, không chỉ chạy theo thứ tự các dòng `<module>` trong POM.

Các cờ bổ sung hữu ích:
- `-amd`/`--also-make-dependents`: build thêm **modules downstream** phụ thuộc vào module được chọn.
- `-rf`/`--resume-from`: tiếp tục reactor từ một project sau khi build lỗi, nhưng phải kiểm tra upstream artifacts.
- `-T`: cho phép build song song các nhánh không phụ thuộc nhau, khi plugin/test thread-safe.

Ví dụ lệnh sử dụng thường xuyên, chạy tại root multi-module project:

```bash
mvn -B -ntp -pl :boot-app -am clean package
```

Lệnh này tập trung build `boot-app` cùng những local Maven modules nó cần, theo thứ tự phù hợp. `-B` là batch mode và `-ntp` giảm log tải artifact. Bài này minh họa trên **Maven 3.9.x, Java 17+, Spring Boot 3.5.0**. Đây là các phiên bản cố định cho ví dụ, **không phải khẳng định phiên bản mới nhất**. Maven 4 có thay đổi cách xác định root/subprojects; khi dùng Maven 4 phải đối chiếu hướng dẫn Maven 4 thay vì giả định mọi chi tiết giống Maven 3.

## 2. Ba khái niệm cần tách bạch: aggregator, parent và dependency

### 2.1. Aggregator quy định thành viên reactor

Một root `pom.xml` có:

```xml
<packaging>pom</packaging>
<modules>
    <module>boot-app</module>
    <module>service-lib</module>
    <module>core-lib</module>
</modules>
```

`<modules>` là danh sách **đường dẫn tương đối** đến các child project POM; reactor sẽ thu thập chúng. Nó không nói `boot-app` phụ thuộc `service-lib`. Việc kê `boot-app` đầu tiên cũng không buộc Maven build app trước thư viện nếu các dependency được khai báo đúng.

Một module cũng có thể là aggregator cho những module sâu hơn. Với Maven 3, chạy từ aggregator root là cách rõ ràng nhất để lựa chọn reactor projects bằng `-pl`.

### 2.2. Parent POM quy định cấu hình được kế thừa

Một child POM có:

```xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>reactor-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

`<parent>` là quan hệ **POM inheritance**: child có thể kế thừa version, properties, dependency/plugin management và các cấu hình Maven phù hợp. Nó **không** tự thêm class Java từ mọi sibling module vào classpath của child.

Root có thể đồng thời là **aggregator và parent**, nhưng hai khái niệm không đồng nhất. Một aggregator có thể thu thập module dùng parent riêng; một corporate parent có thể chỉ quản lý cấu hình mà không khai báo `<modules>`.

### 2.3. Dependency mới tạo quan hệ library consumer

Giả sử `service-lib` dùng `core-lib`. Trong `service-lib/pom.xml` cần có dependency thật:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>core-lib</artifactId>
        <version>0.0.1-SNAPSHOT</version>
    </dependency>
</dependencies>
```

Đó là **instantiated project dependency** tạo ràng buộc: `core-lib` phải sẵn sàng trước `service-lib`. Chỉ liệt kê hai module dưới `<modules>` hoặc đặt `core-lib` trong `dependencyManagement` không đủ.

**Mô hình tư duy:** aggregator quyết định **những project được thu thập**; inheritance quyết định **cấu hình được kế thừa**; dependency quyết định **module cần artifact của module nào**; reactor quyết định **thứ tự và tập build**.

## 3. Reactor thu thập, sắp xếp và thực thi dự án ra sao?

Reactor hoạt động theo ba bước:
1. **Collect:** đọc aggregator và các POM của modules, hình thành tập Maven projects.
2. **Sort:** tìm thứ tự đáp ứng quan hệ phụ thuộc, ví dụ core trước service, service trước application.
3. **Build:** thực thi các Maven lifecycle phases/goals được yêu cầu trên những projects được lựa chọn.

Ví dụ đồ thị:

```text
core-lib  ------>  service-lib  ------>  boot-app
  tạo JAR             tạo JAR             Boot executable JAR

A --> B nghĩa là B cần artifact của A, nên A phải được xây trước B.

Root reactor-demo:
  parent POM của tất cả modules
  packaging = pom, không phải executable JAR
```

Ngay cả khi `<modules>` liệt kê `boot-app` trước `service-lib` và `core-lib`, reactor vẫn cần thứ tự hợp lệ **root/parent → core-lib → service-lib → boot-app**.

### 3.1. Reactor sorting xét quan hệ nào?

Theo hướng dẫn Maven 3, reactor dùng những tham chiếu được **khai báo và sử dụng thực tế** trong reactor, gồm:

- Một project `<dependency>` đến artifact được tạo bởi một module khác.
- Plugin declaration sử dụng một plugin do module khác trong reactor tạo.
- Plugin dependency dùng artifact từ module trong reactor.
- Build extension từ module khác trong reactor.
- Parent POM của module nếu parent cũng nằm trong reactor.
- Thứ tự trong `<modules>` khi không có ràng buộc nào có độ ưu tiên cao hơn.

Chỉ khai báo trong `<dependencyManagement>` hoặc `<pluginManagement>` **không** tự hình thành edge; các mục đó mới quản lý version/cấu hình mặc định, chưa chứng minh dependency/plugin thực sự được dùng.

### 3.2. Topological order và nhánh độc lập

Một đồ thị phụ thuộc không có chu trình (DAG) có thể có nhiều thứ tự topological hợp lệ. Ví dụ:

```text
                +--> report-lib
core-lib -------|
                +--> audit-lib
```

`report-lib` và `audit-lib` không phụ thuộc nhau, nên reactor có thể xử lý chúng theo thứ tự khai báo (hoặc song song với `-T` khi hợp lệ) sau khi core đã sẵn sàng. Không nên dựa vào “module X luôn xuất hiện thứ ba” khi nó không có dependency edge buộc đúng vị trí đó.

### 3.3. Circular dependency là lỗi kiến trúc

Nếu `core-lib` khai báo dependency tới `service-lib` và `service-lib` cũng khai báo ngược lại, đồ thị có vòng lặp:

```text
core-lib ---> service-lib ---> core-lib
```

Không tồn tại thứ tự build hợp lệ. Đổi thứ tự `<modules>` hoặc dùng `-am` không sửa được cycle. Hãy tách API/contract vào module thấp hơn, đảo chiều dependency hoặc refactor trách nhiệm. Không giải quyết bằng cách thủ công cài một JAR cũ trong local repository để “vượt” lỗi vì sẽ làm build không tái lập được.

## 4. Ví dụ Maven đa module hoàn chỉnh, runnable với Java 17

Ta tạo 3 child modules:
- `core-lib`: thư viện Java format lời chào.
- `service-lib`: dùng class từ core-lib.
- `boot-app`: Spring Boot web application, gọi service-lib, tạo executable JAR.

Root POM cố ý kê modules **ngược thứ tự dependency** để quan sát tác dụng của reactor sorting.

### 4.1. Cấu trúc thư mục

```text
reactor-demo/
├── pom.xml
├── core-lib/
│   ├── pom.xml
│   └── src/main/java/com/example/core/GreetingFormatter.java
├── service-lib/
│   ├── pom.xml
│   └── src/main/java/com/example/service/GreetingService.java
└── boot-app/
    ├── pom.xml
    └── src/main/java/com/example/app/DemoApplication.java
```

Cần Java 17 trở lên, Maven tương thích với Spring Boot 3.5.0, và repository truy cập được các Spring Boot artifacts/Maven plugins. Dùng Maven Wrapper của repo nếu đã có; ví dụ chạy với lệnh `mvn` cho đơn giản.

### 4.2. Root `reactor-demo/pom.xml`

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
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactor-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>pom</packaging>
    <name>Reactor Demo Parent</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <modules>
        <module>boot-app</module>
        <module>service-lib</module>
        <module>core-lib</module>
    </modules>
</project>
```

Giải thích:
- `packaging=pom`: root dùng để aggregate/inherit, không cố tạo Java JAR từ root.
- `<modules>` chỉ thu thập thành viên; thứ tự kê ngược là có chủ đích.
- Root kế thừa Spring Boot starter parent để có quản lý dependency/plugin versions và Java release.
- Root **không khai báo** `spring-boot-maven-plugin` trong `<build><plugins>`, vì các module library không nên repackage thành executable Boot JAR.
- Child modules đều có version `0.0.1-SNAPSHOT` kế thừa từ root.

### 4.3. Module core-lib

**`core-lib/pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>reactor-demo</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>core-lib</artifactId>
    <packaging>jar</packaging>
</project>
```

**`core-lib/src/main/java/com/example/core/GreetingFormatter.java`:**

```java
package com.example.core;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Đây là Java class thuần. `core-lib` không cần `@SpringBootApplication` hay Spring Boot Maven Plugin. Maven sẽ tạo **plain JAR** `core-lib/target/core-lib-0.0.1-SNAPSHOT.jar`.

### 4.4. Module service-lib

**`service-lib/pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>reactor-demo</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>service-lib</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

**Chính dependency `core-lib` ở đây tạo edge reactor `core-lib → service-lib`**. Biểu thức `${project.version}` được Maven nội suy bằng version effective project, là `0.0.1-SNAPSHOT` trong demo.

**`service-lib/src/main/java/com/example/service/GreetingService.java`:**

```java
package com.example.service;

import com.example.core.GreetingFormatter;

public final class GreetingService {
    public String message(String name) {
        return GreetingFormatter.greet(name);
    }
}
```

Nếu bỏ `<dependency>core-lib</dependency>` khỏi service POM, source Java sẽ không có `com.example.core.GreetingFormatter` trên compile classpath dù cả hai là siblings trong aggregator.

### 4.5. Module boot-app

**`boot-app/pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>reactor-demo</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>boot-app</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>service-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Module `boot-app` khai báo dependency **trực tiếp** vào `service-lib`; dependency vào `core-lib` được mang theo qua service transitive. `spring-boot-starter-web` cung cấp Spring MVC/embedded server. Spring Boot Maven Plugin chỉ nằm trong app để tạo **executable JAR** từ module đó.

Vì root kế thừa `spring-boot-starter-parent`, module app đã có execution `repackage` khi plugin được khai báo. Library modules không cần plugin này; nếu đặt ở parent build/plugins rồi để child kế thừa, library có thể báo không có main class hoặc tạo archive không phù hợp làm dependency.

### 4.6. Java application thật sự chạy được

**`boot-app/src/main/java/com/example/app/DemoApplication.java`:**

```java
package com.example.app;

import com.example.service.GreetingService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}

@RestController
class GreetingController {
    private final GreetingService service;

    GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/hello")
    public String hello(
            @RequestParam(name = "name", defaultValue = "World") String name) {
        return service.message(name);
    }
}
```

Có hai Java classes trong cùng file, chỉ `DemoApplication` là `public` nên hợp lệ. `@Bean` đăng ký `GreetingService` vào Spring context một cách tường minh; core/service libs không phải tự thêm Spring component scanning. `GreetingController` được phát hiện trong package của application và gọi service chain.

Luồng HTTP:

```text
GET /hello?name=Lan
   -> GreetingController.hello("Lan")
      -> GreetingService.message("Lan")
         -> GreetingFormatter.greet("Lan")
            -> "Xin chào, Lan!"
```

Output này kiểm chứng cả việc compile, dependency resolution trong reactor và classpath runtime của executable Boot JAR.

## 5. Chạy full reactor và kiểm tra build order

Đứng tại **root reactor-demo/**:

```bash
java -version
mvn -version
mvn -B -ntp clean package
```

Maven sẽ đọc root aggregator, thu thập ba modules và xác định thứ tự build. Dù root khai báo `boot-app` đầu tiên, thứ tự logic cần xuất hiện trong `Reactor Build Order` là:

```text
Reactor Demo Parent
core-lib
service-lib
boot-app
```

Đây là **các dòng minh họa thứ tự/tên projects**; log thực tế còn có plugin goals, timestamps, progress và `Reactor Summary` tùy Maven version. Nếu bật parallel build, log có thể xen kẽ các modules độc lập.

Các artifacts tiêu biểu sau khi build thành công:

```text
core-lib/target/core-lib-0.0.1-SNAPSHOT.jar
service-lib/target/service-lib-0.0.1-SNAPSHOT.jar
boot-app/target/boot-app-0.0.1-SNAPSHOT.jar
```

Hai file library là plain JAR. `boot-app` đã được Spring Boot repackage, chứa application classes ở `BOOT-INF/classes` và runtime dependencies ở `BOOT-INF/lib`.

Chạy ứng dụng:

```bash
java -jar boot-app/target/boot-app-0.0.1-SNAPSHOT.jar
```

Từ terminal khác:

```bash
curl -fsS 'http://localhost:8080/hello?name=Lan'
```

**Response body chính xác:** `Xin chào, Lan!` (không nhất thiết có newline). Nếu port 8080 bị chiếm, có thể truyền `--server.port=9090` sau file JAR và đổi URL curl tương ứng. Dừng JVM bằng Ctrl+C trước khi chạy lệnh khác.

**Điểm quan trọng:** `mvn package` tạo artifacts trong từng thư mục `target`; nó **không tự cài** chúng vào `~/.m2/repository`. Một lần reactor build có thể sử dụng kết quả sibling modules trong session đó, nhưng khi chỉ chạy một module ở session khác, Maven có thể phải tìm sibling artifact ở local/remote repository.

## 6. `-pl`: chọn projects theo đường dẫn hoặc tọa độ

`-pl` là viết tắt của `--projects` và dùng để chỉ định tập project muốn build trong reactor. Một số cách chọn tương đương với demo (đứng tại root):

```bash
# Chọn bằng tên thư mục tương đối:
mvn -pl boot-app package

# Chọn bằng artifactId (dấu : đứng trước):
mvn -pl :boot-app package

# Chọn bằng groupId:artifactId:
mvn -pl com.example:boot-app package

# Chọn nhiều module bằng dấu phẩy:
mvn -pl :core-lib,:boot-app package
```

Trong Maven 3:
- `-pl boot-app` tương ứng **path** của module.
- `-pl :boot-app` tương ứng **artifactId**.
- `-pl com.example:boot-app` tương ứng **groupId:artifactId**.
- Nếu tên thư mục khác artifactId, chọn đúng định dạng; đừng mặc định hai tên trùng nhau.
- `-pl` chỉ chọn những Maven projects **đã thuộc reactor**; nó không tìm mọi artifact cùng tên trên Maven Central.

### 6.1. Tại sao chỉ dùng -pl có thể lỗi?

Chạy:

```bash
mvn -B -ntp -pl :boot-app package
```

Maven được yêu cầu build `boot-app`, **không** được yêu cầu build upstream `service-lib` và `core-lib`. Trên máy sạch, phiên bản sibling `0.0.1-SNAPSHOT` chưa được install/publish có thể gây lỗi dependency resolution. Trên máy dev đã cài version cũ của `service-lib`, lệnh có thể “PASS” nhưng chạy với **JAR lỗi thời** thay vì source mới trong repository.

Vì vậy `-pl` đơn lẻ thích hợp khi module không phụ thuộc siblings, hoặc khi bạn **cố ý** tiêu thụ binaries đã publish/install một cách kiểm soát. Trong một mono-repo đang phát triển, nếu muốn lấy source build của sibling dependencies, nên thêm `-am`.

### 6.2. Module path, selector và root POM

Nếu module nằm trong `apps/payments/` nhưng artifactId là `checkout-api`, selector:
- `-pl apps/payments`: theo đường dẫn.
- `-pl :checkout-api`: theo artifactId.
- `-pl com.example:checkout-api`: theo GAV rút gọn.

Nếu bạn thực thi Maven từ thư mục bên ngoài root, có thể chỉ rõ file:

```bash
mvn -f /path/to/reactor-demo/pom.xml -pl :boot-app -am package
```

`/path/to/reactor-demo` là đường dẫn minh họa. Khi debug selection, cách đơn giản nhất là `cd` vào root chứa aggregator `pom.xml` rồi chạy các lệnh reactor.

## 7. `-am`: tự động chọn prerequisites trong cùng reactor

`-am`/`--also-make` thêm những reactor projects mà selected projects phụ thuộc vào. Với demo:

```bash
mvn -B -ntp -pl :boot-app -am clean package
```

Về quan hệ:

```text
             selected bởi -pl
                  |
                  v
core-lib ---> service-lib ---> boot-app
    ^              ^
    |              |
    +------ -am tìm các prerequisite upstream
```

Kết quả cần xây gồm app và các sibling upstream liên quan (cùng parent POM cần thiết). Nếu có một module khác không có dependency edge đến app, nó thường **không** được đưa vào closure chỉ vì có mặt trong root `<modules>`.

**`-am` không build source của external dependencies** như Spring MVC, Jackson, Hibernate, Tomcat. Các artifacts không nằm trong reactor vẫn được Maven resolve từ local/remote repositories, theo POM và settings.

### 7.1. So sánh các lệnh chọn và closure

| Lệnh từ root | Tập công việc mong muốn | Ý nghĩa |
| --- | --- | --- |
| `mvn package` | Tất cả modules | Full reactor build |
| `mvn -pl :boot-app package` | Boot app | Có thể thiếu sibling artifacts trên máy sạch |
| `mvn -pl :boot-app -am package` | App + service + core + parent cần thiết | Chọn upstream prerequisites |
| `mvn -pl :service-lib -am package` | Service + core + parent cần thiết | Không tự test boot-app |
| `mvn -pl :core-lib -am package` | Core + parent cần thiết | Không tự build downstream consumers |
| `mvn -pl :core-lib,:boot-app -am package` | Hợp upstream closure cho cả hai | Module cần thiết chỉ build một lần |

Bảng mô tả **quan hệ module của demo**, không phải lời hứa về số dòng log, vì Maven version và parent/plugin relationships có thể ảnh hưởng projects được thực thi.

### 7.2. -am không tự tạo dependency bị thiếu

Nếu Java code của `service-lib` import `GreetingFormatter` nhưng POM không khai báo `core-lib` trong `<dependencies>`, reactor không suy ra được edge chỉ bằng cách quét `import` của Java. `-am` cũng không sửa được POM thiếu dependency. Cần khai báo đúng groupId/artifactId/version/scope và kiểm tra dependency tree.

Nếu `core-lib` nằm ngoài reactor (chẳng hạn là artifact của repository khác), `-am` không tự “clone” repository nguồn hoặc tìm sibling module khác ngoài aggregator; Maven sẽ resolve binary thông thường.

## 8. `-amd`: chọn các modules phụ thuộc vào module được sửa

`-amd`/`--also-make-dependents` đi theo hướng **downstream**. Khi sửa API của core, bạn muốn biết service và app còn compile không:

```bash
mvn -B -ntp -pl :core-lib -amd verify
```

Với demo, xét quan hệ:

```text
selected:
  core-lib ---> service-lib ---> boot-app
               dependents của core
```

`-am` và `-amd` đối ngược:
- `-am` thêm những modules **được selected modules dùng**.
- `-amd` thêm những modules **dùng selected modules**.
- `-pl` xác định điểm xuất phát.
- Khi cần kết hợp hai chiều trong repo lớn, kiểm tra tập build thực tế thay vì mặc định rằng mọi nhánh sẽ được đưa vào.

**Lưu ý với môi trường mới:** `-amd` không có nghĩa là mọi prerequisite khác của mỗi downstream project đều được tự động thêm giống `-am`; parent/build extensions hoặc những upstream khác có thể cần build cùng. Với CI quyết định release, full `mvn clean verify` thường là baseline đáng tin nhất, còn partial selection là tối ưu cần đo đạc.

### 8.1. Khi nào dùng -amd?

Giả sử sửa chữ ký public method ở `GreetingFormatter`. Test riêng `core-lib` có thể PASS nhưng `service-lib` và `boot-app` compile fail. Chạy `-amd verify` cho thấy tác động xuống các consumers. Ngược lại, khi chỉ muốn chạy web app sau khi sửa shared module, `-pl :boot-app -am` là con đường tự nhiên hơn.

## 9. `-rf`/`--resume-from`: tiếp tục sau build lỗi

Maven 3 có thể hiển thị gợi ý resume sau khi một module fail:

```bash
mvn -rf :service-lib package
```

`-rf` thường bỏ qua các project đứng trước mốc resume trong reactor order rồi chạy phần còn lại. Nhưng **không tự build lại mọi dependency upstream**.

Ví dụ một build trước:

```text
Reactor Demo Parent    SUCCESS
core-lib               SUCCESS
service-lib            FAILURE
boot-app               SKIPPED
```

Sau khi sửa `service-lib`:
- Nếu các artifacts upstream đã được install/publish đúng version và không đổi, resume có thể giúp tiết kiệm thời gian.
- Nếu build trước chỉ tới `package`, `core-lib` có thể chỉ có JAR ở `core-lib/target`, **chưa có trong local Maven repository**. Khi resume bỏ qua core, Maven có thể lại fail resolve `core-lib`.
- Lệnh an toàn khi nghi ngờ trạng thái máy: `mvn -pl :boot-app -am package` hoặc full `mvn clean verify`.

`-rf` không có nghĩa “resume đúng vị trí instruction test bị dừng”; lifecycle/goal chạy lại cho các projects được chọn. Với Maven 4, selection/resume semantics có thêm thay đổi; không sao chép lệnh một cách máy móc khi nâng Maven major version.

## 10. `-T`: song song hóa mà không phá thứ tự phụ thuộc

Maven hỗ trợ parallel reactor:

```bash
mvn -B -ntp -T 1C clean verify
```

`-T 1C` cho Maven dùng số threads tỉ lệ CPU cores; có thể dùng `-T 4` để chỉ định trực tiếp số threads. Tuy nhiên:

- `core-lib → service-lib → boot-app` là chuỗi phụ thuộc tuyến tính, không thể tự chạy ba modules cùng lúc.
- Với graph phân nhánh, ví dụ core → audit-lib và core → reporting-lib, hai module độc lập có thể chạy song song sau khi core sẵn sàng.
- Plugin không thread-safe hoặc tests dùng chung port, database/schema, temp folder có thể gây flaky failures.
- Log giữa các modules có thể xen kẽ do parallelism; không suy luận lỗi thứ tự chỉ từ các dòng console gần nhau.
- CI nên xác minh Maven plugin compatibility và cô lập test resources trước khi tăng `-T`.

`-T` là tối ưu **scheduling**, không thay `<dependency>`, không chữa cyclic dependencies.

## 11. Fail fast, fail at end và non-recursive build

| Cờ | Hành vi chính | Lưu ý |
| --- | --- | --- |
| `-ff`/`--fail-fast` | Dừng sớm khi một module fail; thường là mặc định | Thích hợp phản hồi nhanh |
| `-fae`/`--fail-at-end` | Tiếp tục các module không phụ thuộc phần đã fail, báo lỗi sau | Hữu ích khi muốn thu thập nhiều lỗi |
| `-fn`/`--fail-never` | Không dùng failure exit status như thường lệ | **Tránh dùng làm CI release gate** |
| `-N`/`--non-recursive` | Không đi xuống child modules | Chỉ build project hiện tại |

Ví dụ:

```bash
mvn -B -ntp -fae clean verify
mvn -N validate
```

Khi `core-lib` fail, những modules phụ thuộc core không thể build thành công dựa trên class cần thiết; `-fae` có thể cho một nhánh **độc lập** tiếp tục, không ép Maven bỏ qua dependency edges.

`mvn -N validate` chạy project của working directory (ở root là aggregator), **không** tự build toàn bộ modules. `-N` không phải cách chọn một sibling module ngẫu nhiên.

## 12. `dependencyManagement` và `pluginManagement` không tự tạo reactor edge

Ví dụ trong root parent:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Phần trên **chỉ quản lý version** nếu child sau đó khai báo dependency thực tế. Để `service-lib` thực sự dùng core:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>core-lib</artifactId>
    </dependency>
</dependencies>
```

Khi có cả hai đoạn, edge `core-lib → service-lib` mới hình thành. Nếu chỉ có `dependencyManagement`, reactor không tự build core trước service vì “project có nhắc tên core” trong mục quản lý.

Tương tự:
- `pluginManagement` định nghĩa version/default config của Maven plugins **nếu project thực sự sử dụng plugin**.
- `build/plugins` mới khai báo plugin được sử dụng trong module, có thể tạo mối quan hệ khi plugin chính là reactor module.
- `modules` thu thập các POM; không ép Maven thêm dependency classpath.
- Spring Boot BOM quản lý dependency versions; không phải công cụ quản lý order của local sibling modules.

Đây là lý do một POM root nhìn có đủ mọi version nhưng reactor vẫn fail: những module tiêu thụ code chưa khai báo edges thực sự.

## 13. Spring Boot Maven plugin: tránh repackage mọi library module

Đối với Spring Boot multi-module:
- `core-lib` và `service-lib` là **plain JAR**; class ở root theo package Java, phù hợp làm dependency.
- `boot-app` là **executable JAR**; loader đặt application classes dưới `BOOT-INF/classes` và dependencies dưới `BOOT-INF/lib`.

Nếu đặt `spring-boot-maven-plugin` trong root `<build><plugins>` và cho child kế thừa, `repackage` có thể được áp dụng lên libraries, gây lỗi thiếu main class hoặc biến archive thành executable layout không phù hợp cho các consumer như Maven JAR bình thường.

Ví dụ cấu hình **không nên lan sang library**:

```xml
<!-- Không đặt plugin này ở parent build/plugins nếu mọi library đều kế thừa -->
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
</plugin>
```

Đây là **đoạn plugin**, không phải POM hoàn chỉnh. Chỉ `boot-app` cần plugin như ví dụ ở mục 4.5. Parent có thể quản lý version trong `pluginManagement`; child app khai báo plugin trong `build/plugins` để kích hoạt.

Trong module app, lifecycle `package` thường thực hiện `maven-jar-plugin:jar` trước, sau đó `spring-boot-maven-plugin:repackage`. Reactor phụ thuộc giữa **modules**, còn việc repackage là một goal **bên trong module ứng dụng**; hai cấp thứ tự không được nhầm lẫn.

## 14. Tối ưu CI/CD mà không dựa vào cache tình cờ

### 14.1. Full reactor build là baseline

Một pipeline đáng tin nên có bước:

```bash
mvn -B -ntp clean verify
```

Nó kiểm tra các modules trong tập reactor với thứ tự hợp lệ. Sau đó mới đo thời gian và áp dụng partial builds.

### 14.2. Partial app build với -pl và -am

Cho một job chỉ cần executable Spring Boot JAR:

```bash
mvn -B -ntp -pl :boot-app -am clean verify
```

Lệnh này build app cùng các local prerequisites được Maven biết thông qua dependency graph. Tránh “install core bằng tay, install service bằng tay, rồi package app” vì thứ tự thủ công dễ sót thay đổi và gây lệch local Maven repository giữa các nhánh.

Nếu repository có wrapper, thay Maven CLI:

```bash
./mvnw -B -ntp -pl :boot-app -am clean verify
```

Trên Windows dùng `mvnw.cmd`. Dùng đúng Java/Maven versions đã kiểm thử trong CI.

### 14.3. Kiểm thử downstream khi sửa shared code

Nếu pull request chỉ sửa `core-lib`, đừng chỉ chạy `mvn -pl :core-lib -am verify` rồi cho rằng consumers đã an toàn. Cần một job kiểm thử những module phụ thuộc, ví dụ:

```bash
mvn -B -ntp -pl :core-lib -amd verify
```

Với reactor lớn, downstream modules có thể cần prerequisite khác không thuộc selection; phải tính closure phù hợp, hoặc quay về full build cho release gate. Các cờ là công cụ **lựa chọn graph**, không thay thế coverage strategy của CI.

### 14.4. Phân biệt package, install và deploy

- `package`: tạo JAR/WAR trong thư mục `target` của mỗi project.
- `verify`: chạy đến phase verify, có thể chứa integration/quality goals nếu cấu hình.
- `install`: cài artifacts vào **local** Maven repository để các Maven invocations khác dùng.
- `deploy`: publish lên **remote** Maven artifact repository, cần `distributionManagement`/credentials.

Reactor build trong cùng invocation thường không cần `install` giữa các modules để resolve sibling artifacts. Dùng `install` khi có nhu cầu khác thật sự; không biến local cache thành một “máy chủ sự thật” cho source hiện tại.

### 14.5. Cẩn trọng với SNAPSHOT và cache

Khi nhiều branches cùng dùng tọa độ `com.example:core-lib:0.0.1-SNAPSHOT`, việc `mvn install` lên một local repository chung có thể khiến build của branch khác dùng lại binary không phù hợp.

Quy trình tốt hơn:
- Dùng reactor selected closure trong một Maven invocation.
- Giữ CI workspace/cache boundaries rõ ràng; có thể cô lập local repository theo job nếu cần.
- Pin build/plugin versions và ghi Maven/JDK versions vào log.
- Khi publish, dùng version/commit metadata có thể truy vết và cơ chế repository chuẩn; không chỉ dựa vào một SNAPSHOT tên chung.
- Xác minh đúng artifact `boot-app/target/boot-app-0.0.1-SNAPSHOT.jar` và chạy smoke test.

## 15. Lệnh chẩn đoán khi reactor build lỗi

```bash
mvn -version
mvn -B -ntp clean verify
mvn -B -ntp -pl :boot-app -am package
mvn -B -ntp -pl :boot-app dependency:tree
mvn help:effective-pom
```

**Lưu ý:** `dependency:tree` là goal của Maven Dependency Plugin, có thể cần plugin resolution từ repository. `help:effective-pom` là goal Maven Help Plugin, hữu ích khi muốn xem parent, dependencyManagement và plugin execution đã được thừa hưởng. Khi source sibling artifacts chưa sẵn sàng trong selected reactor hoặc local cache, một số goal chỉ chạy trên module đơn lẻ có thể fail resolution. Hãy kiểm tra lệnh CLI, reactor selection và dependency graph trước.

Không dùng `-q`/`--quiet` khi đang muốn quan sát `Reactor Build Order` và `Reactor Summary`, vì chế độ quiet có thể ẩn những thông tin cần debug.

### 15.1. Quy trình xác định lỗi

1. Đứng tại root aggregator và xác nhận `<modules>` trỏ đúng child directories.
2. Kiểm tra Maven/JDK version, POM parent và `relativePath` của các children.
3. Xác nhận module consumer có **dependency thực tế** tới sibling artifact đúng groupId/artifactId/version.
4. Chạy full build để xem reactor order và module thất bại đầu tiên.
5. Thử `-pl :boot-app -am package` để kiểm tra upstream closure.
6. Nếu fail **sibling artifact resolution**, kiểm tra thiếu `-am`, sai tọa độ hoặc local repository artifact cũ.
7. Nếu fail **external artifact resolution**, kiểm tra Maven repository/mirror/proxy/credentials; `-am` không khắc phục được lỗi network.
8. Nếu fail **compile/test**, sửa source/test/plugin config; reactor chỉ tổ chức thứ tự.
9. Nếu fail **Spring Boot packaging**, kiểm tra Boot plugin chỉ ở app, main class và archive layout.
10. Nếu fail sau `-rf`, chạy lại upstream closure thay vì dựa vào artifacts chỉ có ở `target`.
11. Nếu fail bất thường với `-T`, tạm chạy tuần tự và kiểm tra thread safety hoặc shared resources.

## 16. Lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân có khả năng cao | Giải pháp |
| --- | --- | --- |
| `Could not find artifact com.example:service-lib` | Chọn boot-app bằng `-pl` nhưng thiếu upstream | Thêm `-am` từ root reactor |
| Maven tìm `core-lib` bản cũ trong cache | Sibling không được build trong invocation, version SNAPSHOT trùng | Chạy selected closure, đồng bộ versions/cache isolation |
| `package ... does not exist` ở module consumer | Chưa khai báo `<dependency>`, scope sai hoặc version sai | Thêm dependency thật, không chỉ dependencyManagement |
| Build order khác thứ tự `<modules>` | Reactor topologically sort các dependencies | Đây là hành vi đúng; đọc reactor sort rules |
| Maven không nhận `-pl :module` | ArtifactId khác, module ngoài reactor hoặc sai root | Xem POM aggregator và đúng selector |
| Parent POM không resolve | `relativePath`/GAV sai hoặc parent unavailable | Sửa parent coordinates, `../pom.xml` |
| Reactor báo cyclic reference | Hai modules phụ thuộc vòng nhau | Tách interface/model, refactor graph |
| App module không tạo executable JAR | Chưa khai báo Boot Maven plugin ở app | Khai báo plugin và bảo đảm `repackage` execution |
| Library module báo thiếu main class | Boot plugin bị kế thừa bởi library | Chỉ bật plugin ở app |
| Consumer không đọc được class từ executable JAR | Boot JAR layout không phải plain Java library | Giữ module library là plain JAR |
| `-rf` fail dù upstream SUCCESS lần trước | Upstream đã package nhưng chưa install, resume bỏ qua upstream | Chạy lại `-pl ... -am` hoặc full reactor |
| `-amd` không chọn downstream mong đợi | Thiếu dependency edge hoặc module không thuộc reactor | Sửa dependency/aggregation, kiểm tra graph |
| `-T` gây fail không ổn định | Plugin/test không thread-safe, shared state | Chạy tuần tự, cô lập tài nguyên |
| CI pass dù test fail | Dùng `-fn`, bỏ exit code, skip tests | Loại `-fn`, kiểm tra status và test reports |
| Build chỉ fail trên CI | Maven/JDK/repo/cache/root khác dev | Dùng wrapper, log versions và CI settings |
| `curl` vào app fail | JAR/app chưa start, port khác hoặc bootstrap lỗi | Kiểm tra Spring logs, port và artifact đúng |

## 17. Bảng ghi nhớ các cờ reactor

| Cờ | Tên dài | Tác động |
| --- | --- | --- |
| `-pl` | `--projects` | Chọn module bắt đầu |
| `-am` | `--also-make` | Build thêm prerequisites **upstream** |
| `-amd` | `--also-make-dependents` | Build thêm consumers **downstream** |
| `-rf` | `--resume-from` | Resume từ project trong reactor order |
| `-N` | `--non-recursive` | Không đi xuống child modules |
| `-T` | `--threads` | Cho phép parallel reactor khi an toàn |
| `-ff` | `--fail-fast` | Dừng khi module fail |
| `-fae` | `--fail-at-end` | Tiếp tục nhánh độc lập, báo lỗi cuối |
| `-fn` | `--fail-never` | Không dùng cho release gate |
| `-f` | `--file` | Chọn POM đầu vào, ví dụ root POM |

Tóm tắt: **`-pl` chọn module mục tiêu; `-am` bổ sung những module mục tiêu cần; `-amd` bổ sung những module cần mục tiêu**. Maven vẫn phải sắp xếp các project đã chọn theo dependency edges đã khai báo.

## 18. Tài liệu học tập và checklist kết thúc

### Checklist

- Root `pom.xml` có packaging `pom` và danh sách modules đúng path.
- Child modules dùng parent đúng groupId/artifactId/version, `relativePath` khi phù hợp.
- Các quan hệ Java giữa siblings được khai báo trong `<dependencies>`.
- Không có circular dependencies hoặc modules trùng tọa độ.
- `dependencyManagement`/`pluginManagement` không bị hiểu nhầm là actual dependency edges.
- Library modules là plain JAR; Spring Boot executable plugin chỉ nằm trong module app.
- Full reactor build pass trước khi tối ưu selective CI builds.
- Khi build app từ source cùng repo, dùng `-pl :boot-app -am` để bao gồm upstream prerequisites.
- Khi đổi public API của core, kiểm tra downstream qua `-amd`/full build.
- Không dựa vào `-rf` để rebuild upstream chưa install; tránh binary cache cũ.
- `-T` chỉ bật khi plugins/tests có thể chạy song song.
- Reactor summary/exit status được kiểm tra thật; `-fn` không dùng để quyết định deploy.
- CI kiểm tra đúng executable JAR, Java runtime, smoke test và artifact checksum.

### Tài liệu chính thức

- Apache Maven 3 – [Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): collection, reactor sorting và selectors.
- Apache Maven – [POM Reference](https://maven.apache.org/pom.html): aggregation, inheritance, `<modules>`, `<dependencies>`, `dependencyManagement`.
- Apache Maven – [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): package/verify/install/deploy.
- Apache Maven 3.9.9 – [CLI Options](https://maven.apache.org/ref/3.9.9/maven-embedder/cli.html): `-pl`, `-am`, `-amd`, `-rf`, `-T` và failure modes.
- Apache Maven 4 – [Working with Multiple Subprojects](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html): điều khác biệt khi dùng Maven 4.
- Spring Boot 3.5 – [Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): executable JAR và goal `repackage`.
- Spring Boot 3.5 – [Using the Maven Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html): starter parent và plugin configuration.

**Kết luận:** Maven reactor thu thập multi-module projects, sắp xếp theo dependencies **thực sự được dùng**, rồi build selected projects theo thứ tự hợp lệ. `-pl` giúp khoanh vùng module; `-am` kéo theo các prerequisite cùng reactor để tránh phụ thuộc artifact local cũ; `-amd` xác minh ảnh hưởng tới consumers. Trong ứng dụng Spring Boot đa mô-đun, giữ library modules là plain JAR, chỉ module ứng dụng tạo executable JAR, và dùng `mvn -pl :boot-app -am clean package` khi cần build ứng dụng cùng toàn bộ chuỗi thư viện của nó.