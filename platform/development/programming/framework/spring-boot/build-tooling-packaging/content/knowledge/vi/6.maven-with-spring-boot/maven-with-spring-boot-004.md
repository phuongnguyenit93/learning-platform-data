# Khai báo và quản lý phiên bản `spring-boot-maven-plugin`

Khi phát triển ứng dụng Spring Boot với Maven, chỉ khai báo dependency `spring-boot-starter-web` hoặc `spring-boot-starter` chưa đủ để tạo một **executable JAR** đúng chuẩn Spring Boot. Maven cần một **build plugin** đảm nhiệm tác vụ chạy ứng dụng trong lúc phát triển, tái đóng gói JAR/WAR và một số tác vụ build khác: **`org.springframework.boot:spring-boot-maven-plugin`**.

Bài này tập trung vào hai quyết định kỹ thuật: **khai báo plugin ở đâu** và **phiên bản plugin được chọn như thế nào**. Bạn sẽ thực hành hai cách cấu hình phổ biến — có và không có `spring-boot-starter-parent` — rồi biết cách kiểm tra phiên bản thực được Maven sử dụng và tránh những lỗi khi nâng cấp, đóng gói hoặc tổ chức nhiều module.

Các ví dụ dùng **Spring Boot 3.3.13, Maven 3.9+ và Java 17** để giữ nhất quán trong một bản hướng dẫn có thể tái lập. `3.3.13` là **phiên bản minh họa của nhánh 3.3**, không có nghĩa đây là phiên bản Spring Boot mới nhất hay lựa chọn mặc định cho một dự án mới. Khi áp dụng thực tế, chọn một phiên bản đang được duy trì và phù hợp với nền tảng của dự án, rồi thay **đồng bộ** các chỗ thể hiện version.

## 1. Phân biệt Maven plugin, starter và BOM

Ba khái niệm dễ nhầm nhưng giữ những vai trò khác nhau:

| Thành phần | Artifact ví dụ | Vai trò | Nằm ở đâu trong POM? |
| --- | --- | --- | --- |
| **Maven plugin** | `spring-boot-maven-plugin` | Thực thi các goal **trong quá trình build**, như `run`, `repackage`, `build-image` | `<build><plugins>` hoặc phần quản lý `<pluginManagement>` |
| **Spring Boot starter** | `spring-boot-starter-web` | Gom **dependency ứng dụng** như Spring MVC, JSON và web server nhúng | `<dependencies>` |
| **BOM** (Bill of Materials) | `spring-boot-dependencies` | Quản lý **version của dependency** theo một tập tương thích | `<dependencyManagement>` (nhập bằng `type=pom`, `scope=import`) |
| **Starter parent** | `spring-boot-starter-parent` | Kế thừa BOM, thiết lập mặc định build và quản lý Maven plugin | `<parent>` |

Điểm then chốt: **Maven plugin không phải dependency runtime của ứng dụng.** Việc khai báo `spring-boot-maven-plugin` dưới `<build>` khiến Maven có thể chạy goal của plugin; nó **không** biến các lớp của plugin thành thư viện cho controller/service và không có nghĩa JAR plugin được nhúng vào `BOOT-INF/lib`.

Tương tự, import `spring-boot-dependencies` BOM **không tự quản lý version** của `spring-boot-maven-plugin`. BOM được import vào **dependency management**, còn phiên bản Maven plugin thuộc hệ thống **plugin management**.

## 2. Goal, phase và execution: plugin thực sự chạy khi nào?

Maven sử dụng **lifecycle phase**, chẳng hạn `compile`, `test`, `package`, `verify`, `install`. **Plugin goal** là một thao tác cụ thể có thể được gắn vào một phase hoặc được gọi trực tiếp.

`spring-boot-maven-plugin` cung cấp một số goal thường gặp:

- `spring-boot:run` — chạy ứng dụng từ project, thuận tiện để phát triển.
- `spring-boot:repackage` — lấy JAR/WAR đã được build và **tái đóng gói** thành Spring Boot archive có thể chạy bằng `java -jar` nếu cấu hình hỗ trợ.
- `spring-boot:build-image` — tạo OCI image theo cơ chế được plugin hỗ trợ; cần môi trường/container builder phù hợp.
- `spring-boot:start` và `spring-boot:stop` — hỗ trợ một số quy trình tích hợp/kiểm thử.

Một chuỗi build phổ biến:

```text
pom.xml
  |
  v
Maven đọc parent, dependencyManagement, pluginManagement
  |
  v
compile -> test -> package
                    |
                    +--> maven-jar-plugin tạo JAR ban đầu
                    |
                    +--> spring-boot-maven-plugin:repackage
                         tái đóng gói JAR cho java -jar
```

Khi thêm plugin vào `<build><plugins>`, **không phải mọi goal đều tự chạy**. Maven chỉ chạy goal được gọi trực tiếp hoặc được gắn vào lifecycle qua **execution**. Với `spring-boot-starter-parent`, một execution có id `repackage` đã được cấu hình sẵn; bạn chỉ cần khai báo plugin trong danh sách plugin của ứng dụng. Khi không dùng parent này, bạn cần tự thiết lập execution nếu muốn `mvn package` tự chạy `repackage`.

Lệnh `mvn package` phải build thành công JAR ban đầu trước khi `repackage` xử lý nó. Vì thế gọi riêng `mvn spring-boot:repackage` trên một project chưa có artifact để tái đóng gói có thể thất bại; hãy dùng execution gắn với `package` hoặc trước tiên build bằng `mvn package`.

## 3. Cách 1 — Dùng `spring-boot-starter-parent` (đường đi phổ biến)

Đây là lựa chọn đơn giản khi project **không bắt buộc kế thừa parent POM khác**. Parent Spring Boot đã quản lý version cho nhiều Maven plugin, cung cấp mặc định Java/compiler và cấu hình execution `repackage`.

### 3.1. POM đầy đủ

Tạo `pom.xml` ở gốc dự án:

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
    <artifactId>boot-plugin-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Cần quan sát bốn điểm:

1. `<parent>` cố định phiên bản **3.3.13** của hệ cấu hình Spring Boot.
2. Các dependency starter **không cần ghi `<version>`** vì có dependency management kế thừa.
3. `spring-boot-maven-plugin` cũng **không cần ghi `<version>`**, lần này vì parent quản lý **plugin version** qua `<pluginManagement>`.
4. Khai báo plugin trong `<build><plugins>` **kích hoạt cấu hình execution `repackage` đã được parent chuẩn bị**. Không cần tự thêm một execution thứ hai.

**Phân biệt hai chữ “không cần version”:** với starter, nguồn version là quản lý **dependency**; với Maven plugin, nguồn version là quản lý **plugin**. Chúng là hai khu vực khác nhau của effective POM.

### 3.2. Vì sao không tự ghi lại `<executions>`?

Khi dùng parent, phần cấu hình đã có về logic tương đương một execution id `repackage` gọi goal `repackage` trong pha packaging. Nếu tự thêm một execution mới với id khác, bạn có thể khiến goal chạy **hai lần**, gây lỗi hoặc tạo artifact không đúng mong muốn.

Nếu chỉ muốn **tùy chỉnh execution có sẵn**, hãy dùng đúng id `repackage`; ví dụ mục 7 trình bày cách đặt classifier.

### 3.3. Parent có tự bật plugin dù POM không khai báo không?

Đừng đồng nhất **`<pluginManagement>`** với **`<plugins>`**. Plugin management chủ yếu cung cấp version, cấu hình và execution mặc định **khi plugin được khai báo/được sử dụng thích hợp**. Cách cấu hình rõ ràng cho ứng dụng chạy thật là vẫn khai báo `spring-boot-maven-plugin` trong `<build><plugins>` như ví dụ. Chỉ có parent hoặc chỉ có starter dependency không phải lời bảo đảm rằng executable archive sẽ được tạo trong mọi bố cục dự án.

## 4. Cách 2 — Không dùng Spring Boot parent, chỉ import BOM

Nhiều doanh nghiệp bắt buộc dùng corporate parent, hoặc một dự án Maven nhiều module có parent build riêng. Maven chỉ có **một parent trực tiếp**; bạn có thể **import BOM** để quản lý các dependency Spring Boot, nhưng **phải tự quản lý version plugin và execution**.

### 4.1. POM đầy đủ không kế thừa starter parent

Ví dụ `pom.xml` độc lập sau đây không khai báo Spring Boot parent. Nó có thể được mở rộng để dùng corporate parent ở vị trí `<parent>` nếu hệ thống nội bộ yêu cầu.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>boot-plugin-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <spring-boot.version>3.3.13</spring-boot.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích riêng từng phần:**

- `<spring-boot.version>3.3.13</spring-boot.version>` là **property do project định nghĩa**, để BOM và plugin cùng sử dụng một phiên bản.
- `<dependencyManagement>` import `spring-boot-dependencies`, từ đó dependency `spring-boot-starter-web` không phải khai báo version.
- `<version>${spring-boot.version}</version>` ở **plugin** là bắt buộc trong ví dụ này vì không có Boot parent quản lý plugin version.
- `<execution><goal>repackage</goal></execution>` gắn goal vào lifecycle (goal này có default phase thích hợp) để `mvn package` tạo executable JAR.
- `maven-compiler-plugin` và Java release được khai báo riêng để ví dụ độc lập và tránh phụ thuộc mặc định compiler của một parent khác.

Khi đưa vào corporate parent, kiểm tra `effective-pom` để xem parent đã quản lý compiler, plugin, execution và encoding nào; chỉ giữ các khai báo bổ sung thật sự cần thiết. **Import BOM không thay thế toàn bộ cấu hình build từ `spring-boot-starter-parent`.**

### 4.2. Nếu chỉ import BOM rồi quên version plugin?

Maven có thể cố phân giải version plugin từ nơi khác hoặc báo cảnh báo khi thiếu version; kết quả có thể đổi theo repository/phiên bản Maven. Đây là cấu hình **không tái lập ổn định**, ngay cả khi dependency graph ứng dụng đã được BOM kiểm soát.

Mẫu không nên dùng khi không có plugin management tương ứng:

```xml
<!-- Chưa đủ an toàn khi project không có Boot parent/pluginManagement -->
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
</plugin>
```

Sửa bằng cách đặt `<version>${spring-boot.version}</version>` hoặc quản lý version tập trung dưới `<pluginManagement>` rồi khai báo plugin ở module cần dùng.

## 5. Maven chọn phiên bản plugin từ đâu?

Khi Maven xử lý một plugin trong build, cần phân biệt:

1. **Version ghi trực tiếp** tại `<build><plugins><plugin><version>...`: chỉ rõ version dùng cho plugin đó.
2. **`<build><pluginManagement>` trong POM hiện tại hoặc parent hợp lệ**: cung cấp version/configuration khi plugin được sử dụng mà không ghi version riêng.
3. **Maven tự phân giải version khi không có nguồn version rõ ràng**: có thể phụ thuộc metadata/repository và gây build khó tái lập. Hãy tránh để đến bước này.

`spring-boot-starter-parent` thuộc trường hợp (2). Import `spring-boot-dependencies` BOM **không tạo nguồn version plugin ở (2)**. `<dependencyManagement>` cũng không phải nơi đặt `spring-boot-maven-plugin`.

Để kiểm tra Maven đang thật sự dùng version nào, hãy tạo **effective POM** sau khi Maven xử lý parent, profile, property và phần kế thừa:

```bash
# Đứng ở thư mục chứa pom.xml
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd help:effective-pom -Doutput=target/effective-pom.xml
```

Mở `target/effective-pom.xml` và tìm **`spring-boot-maven-plugin`** trong phần `<build>`, xem `<version>`, `<executions>`, `<id>repackage</id>` và `<configuration>`. Với project dùng parent, effective POM thường có thêm phần `<pluginManagement>` và bản plugin đã áp dụng trong `<plugins>` — hãy phân biệt thông tin **quản lý** với execution **thực sự được dùng**.

Ngoài ra:
- `./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Ddetail` giúp khám phá goal và tham số (cần các plugin Maven liên quan có thể được resolve).
- `./mvnw -X package` in log debug chi tiết về plugin/goal được chạy; chỉ bật khi cần chẩn đoán.
- `./mvnw dependency:tree` xem **dependency của ứng dụng**; không đủ để kết luận plugin build đang dùng version nào.

Nếu dự án không tạo Maven Wrapper, có thể dùng `mvn` thay `./mvnw`, với Maven đã được cài đặt. Luôn kiểm tra `./mvnw -version` hoặc `mvn -version` để biết Maven chạy bằng JDK nào.

## 6. Ví dụ Maven nhiều module: quản lý tập trung nhưng chỉ bật đúng nơi

Một parent nội bộ có thể quản lý version plugin cho các module con. Ví dụ đoạn POM ở parent `<packaging>pom</packaging>`:

```xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
</properties>

<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Đây là **đoạn cấu hình để ghép vào POM parent**, không phải một `pom.xml` độc lập. Ở **module ứng dụng chạy được**, opt-in bằng:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Module **thư viện thuần** không cần khai báo plugin trên, nên build JAR thư viện thông thường. Nếu đưa plugin kèm execution trực tiếp vào `<build><plugins>` của parent và để kế thừa cho mọi module, một module thư viện không có main class có thể bị chạy `repackage` không mong muốn và thất bại. **`pluginManagement` phù hợp khi muốn quản lý chung nhưng cho từng module quyết định có bật plugin hay không.**

Một parent nội bộ phải quản lý **dependency version và plugin version như hai phần riêng**, dù chúng cùng tham chiếu property `spring-boot.version`. Nếu một module con có `<plugin>` version tường minh khác, hãy xem đó là lựa chọn override có chủ đích và kiểm tra tính tương thích.

## 7. Tùy chỉnh `repackage` đúng cách

### 7.1. Muốn có thêm một JAR chạy được nhưng giữ JAR gốc

Với `spring-boot-starter-parent`, đặt cấu hình **đúng execution id `repackage`** để không thêm execution thứ hai:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>repackage</id>
                    <configuration>
                        <classifier>exec</classifier>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Ví dụ này giữ artifact JAR gốc và gắn artifact đã repackage với classifier `exec`, thường tạo tên dạng `boot-plugin-demo-0.0.1-SNAPSHOT-exec.jar` bên cạnh JAR gốc. Khi muốn chạy, chọn **đúng JAR có classifier**:

```bash
java -jar target/boot-plugin-demo-0.0.1-SNAPSHOT-exec.jar
```

Đây là **đoạn thay thế cho khai báo plugin tại mục 3.1**, không phải một plugin thứ hai trong cùng `<plugins>`. Khi dùng corporate parent, kiểm tra execution thực sự có id phù hợp rồi mới chỉnh; không mặc định parent riêng của công ty đã tạo sẵn id `repackage`.

### 7.2. Đặt main class khi Maven không xác định đúng

Nếu có nhiều lớp `main` hoặc muốn chọn entry point cụ thể:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.plugindemo.PluginDemoApplication</mainClass>
    </configuration>
</plugin>
```

Thêm đoạn này dưới `<build><plugins>` trong dự án **đã có version/execution phù hợp** (qua parent hoặc tự quản lý). `mainClass` phải là tên fully qualified của lớp main thực tế. Chỉ khai báo khi thật sự cần: plugin có khả năng tự tìm main class trong nhiều dự án đơn giản.

### 7.3. Tắt repackage có chủ đích

Với một module **không được triển khai độc lập**, cách rõ ràng thường là **không khai báo plugin** trong module đó. Nếu do kế thừa hoặc quy trình đặc biệt bạn vẫn có execution, có thể cấu hình `<skip>true</skip>` cho execution tương ứng. Đừng tắt `repackage` ở module cần `java -jar` mà không đổi cách đóng gói, vì sản phẩm `package` khi đó có thể chỉ là plain JAR.

### 7.4. Repackage không thay thế mọi tác vụ packaging

`spring-boot:repackage` **xử lý JAR/WAR được build trước đó**; nó không biên dịch Java thay `maven-compiler-plugin`, không chạy test thay `maven-surefire-plugin` và không tự biến module `pom` thành ứng dụng. Chọn `jar` hoặc `war` phù hợp; hiểu thứ tự plugin/phase khi tùy chỉnh default lifecycle. Với logic đóng gói riêng, xác nhận plugin tạo JAR gốc trước khi Boot plugin tái đóng gói.

## 8. Bài thực hành chạy được: kiểm chứng version và executable JAR

Bạn có thể dùng **một trong hai POM đầy đủ** ở mục 3.1 hoặc 4.1. Tạo file:

```text
boot-plugin-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── plugindemo/
                        └── PluginDemoApplication.java
```

Nội dung `src/main/java/com/example/plugindemo/PluginDemoApplication.java`:

```java
package com.example.plugindemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PluginDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PluginDemoApplication.class, args);
    }
}

@RestController
class HealthProbeController {

    @GetMapping("/ping")
    public String ping() {
        return "plugin-ok";
    }
}
```

Đây là Java 17 hợp lệ. Tệp chứa một lớp `public` có tên trùng tệp; controller cùng package nhưng không cần `public`. `@SpringBootApplication` quét từ package `com.example.plugindemo` nên tìm thấy controller. `spring-boot-starter-web` cung cấp Spring MVC và Servlet web server nhúng theo mặc định.

**Bước 1 — Kiểm tra Java và Maven:**

```bash
java -version
./mvnw -version
```

Nếu chưa tạo Maven Wrapper, dùng `mvn -version` và các lệnh `mvn` tương ứng. JDK chạy Maven cần phù hợp với Spring Boot và compiler release đã chọn.

**Bước 2 — Build, có chạy test nếu project có test:**

```bash
./mvnw clean package
```

Lệnh trên phải resolve plugin và dependency, biên dịch Java và chạy goal `repackage` khi được cấu hình đúng. Với hai POM cơ bản chưa dùng classifier, tên JAR dự kiến:

```text
target/boot-plugin-demo-0.0.1-SNAPSHOT.jar
```

**Bước 3 — Xác minh JAR chứa bộ khởi chạy Spring Boot:**

```bash
jar tf target/boot-plugin-demo-0.0.1-SNAPSHOT.jar
```

Với **Spring Boot 3.3.x executable JAR** thông thường, bạn sẽ thấy các đường dẫn thuộc `BOOT-INF/classes/`, `BOOT-INF/lib/` và bộ loader dưới `org/springframework/boot/loader/`. Chẳng hạn:

```text
BOOT-INF/classes/com/example/plugindemo/PluginDemoApplication.class
BOOT-INF/classes/com/example/plugindemo/HealthProbeController.class
BOOT-INF/lib/...
```

Các dòng trên chỉ là **mẫu đường dẫn cần tìm**, không phải toàn bộ output `jar tf`. Nếu chỉ có class mà thiếu cấu trúc Boot loader/`BOOT-INF/lib`, có thể `repackage` chưa chạy hoặc bạn đã mở nhầm plain JAR. Cấu trúc khác có thể xuất hiện nếu bạn chủ động chọn WAR/layout khác.

**Bước 4 — Chạy artifact đã đóng gói:**

```bash
java -jar target/boot-plugin-demo-0.0.1-SNAPSHOT.jar
```

Giữ tiến trình đang chạy, mở terminal thứ hai:

```bash
curl -s http://localhost:8080/ping
```

HTTP response body kỳ vọng là chính xác:

```text
plugin-ok
```

`curl -s` thường in chuỗi không có dấu xuống dòng cuối; terminal có thể hiển thị prompt liền sau đó. Nếu cấu hình `server.port` khác 8080 hoặc port bị chiếm, dùng cổng thực tế. Các dòng log Spring Boot phụ thuộc môi trường nên không có stdout log cố định để so sánh.

**Bước 5 — Chứng minh plugin version đang dùng:**

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

Trong file sinh ra, tìm `spring-boot-maven-plugin`, version `3.3.13` và execution `repackage` đã áp dụng. Nếu dùng parent, version/execution đến từ phần kế thừa; nếu import BOM, chúng đến từ khai báo plugin tường minh trong POM mục 4.1.

Trên Windows PowerShell, thay `./mvnw` bằng `.\mvnw.cmd` khi có Wrapper; các lệnh `java -jar`, `jar tf`, `curl` vẫn chạy theo cách tương đương với các công cụ được cài.

## 9. Quản lý phiên bản khi nâng cấp Spring Boot

Trong một dự án sử dụng Maven plugin để đóng gói Spring Boot, nên **điều phối phiên bản plugin với phiên bản Spring Boot dependency/BOM**. Điều này giảm khả năng dùng loader/build format không phù hợp với runtime hoặc configuration hiện có.

### 9.1. Dự án dùng parent

Nguồn điều khiển chính ở ví dụ mục 3.1:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
</parent>
```

Khi đổi sang một release Spring Boot mới phù hợp, hãy thay **version ở parent**, xem release notes/migration notes, rồi build/test. Trong cấu hình thông thường, plugin version và starter dependency management sẽ đi theo parent. **Đừng chỉ ghim riêng version `spring-boot-maven-plugin` ở mức khác mà không có lý do/kiểm thử.**

Lưu ý: Maven phải resolve `<parent><version>` ở giai đoạn sớm; không nên giả định property do chính POM con khai báo có thể thay thế version của parent một cách an toàn. Dùng version xác định trong `<parent>` hoặc một chiến lược quản lý parent của tổ chức đã được kiểm chứng.

### 9.2. Dự án không dùng parent

Đổi property chung:

```xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
</properties>
```

BOM và Maven plugin phải cùng tham chiếu `${spring-boot.version}` như ví dụ mục 4.1. Đây là cách giảm rủi ro **nâng một bên nhưng quên bên còn lại**. Hãy kiểm tra corporate parent, plugin management khác, BOM khác và các dependency có version ghi đè để xác định version cuối cùng.

### 9.3. Quy trình nâng cấp an toàn

1. Chọn release Spring Boot phù hợp với JDK, Spring Framework, plugins và các thư viện tích hợp của dự án.
2. Cập nhật parent **hoặc** property BOM + plugin một cách đồng bộ.
3. Kiểm tra `mvn -version` để biết JDK Maven đang dùng, đặc biệt trên CI.
4. Tạo `help:effective-pom`, xác minh plugin version và execution `repackage`.
5. Xem `dependency:tree` để phát hiện dependency override không tương thích.
6. Chạy `clean verify` hoặc ít nhất `clean package` và các bài kiểm thử dự án.
7. Kiểm tra JAR/WAR thật, chạy thử artifact và xác minh startup/endpoint.
8. Khi đổi major Spring Boot, đọc tài liệu migration và kiểm tra các goal/parameter plugin thay đổi.

**Một version “mới hơn” của Maven plugin không tự động là “tốt hơn” nếu dependency runtime Spring Boot vẫn ở dòng cũ.** Việc hỗ trợ các phối hợp version cụ thể phải được kiểm chứng theo release notes và kết quả build/test.

## 10. Những lỗi thường gặp và cách xác minh

| Triệu chứng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| `mvn package` tạo JAR nhưng `java -jar` không khởi động được như Boot executable | Plugin không được khai báo hoặc `repackage` chưa gắn vào lifecycle | Kiểm tra `<build><plugins>`, effective POM, log goal `spring-boot:repackage` và nội dung JAR |
| Import BOM rồi Maven cảnh báo plugin thiếu version | BOM chỉ quản lý dependency, không quản lý plugin | Ghi version plugin hoặc thêm `<pluginManagement>` được kế thừa đúng |
| Version plugin khác Spring Boot runtime mà không chủ đích | Override version ở plugin, parent hoặc corporate POM | Kiểm tra effective POM và dependency tree; đưa về tập version được kiểm thử |
| `spring-boot:repackage` báo không có source artifact | Chạy goal trước khi package hoặc plugin execution/packaging sai | Chạy `package` với execution đúng; xác nhận JAR/WAR đã được tạo |
| `repackage` chạy hai lần | Với Boot parent, thêm một execution mới thay vì sửa id `repackage` | Giữ đúng id `repackage` khi tùy chỉnh execution kế thừa |
| Module thư viện bị lỗi không tìm thấy main class | Plugin/repackage bị áp dụng cho mọi module từ parent | Đặt mặc định vào `pluginManagement` và chỉ bật trong ứng dụng chạy được |
| Maven không biết goal `spring-boot:run` hoặc gọi sai phiên bản | Plugin chưa được resolve/khai báo, thiếu plugin group/version hoặc repository | Kiểm tra POM, internet/repository, sử dụng tọa độ plugin và version rõ ràng |
| `ClassNotFoundException` khi chạy JAR | Dependency runtime bị loại, scope sai hoặc packaging không đúng | Xem dependency tree/runtime artifact và `BOOT-INF/lib` |
| Đổi plugin version mà build CI khác máy local | Maven/JDK/profile/settings/repository khác nhau, plugin version chưa được cố định | Kiểm tra Wrapper, `mvn -version`, profile, effective POM và repository settings |
| Chọn nhầm `target/*-exec.jar` hoặc plain JAR | Cấu hình `classifier` tạo nhiều artifacts | Xem tên file và nội dung bằng `jar tf`, chạy đúng artifact đã repackaged |
| Override `<mainClass>` sai | Sai package/tên lớp Java hoặc lớp không có `main` thích hợp | Dùng tên fully qualified đúng và biên dịch lại |
| `spring-boot-starter-web` có version quản lý nhưng plugin không có | Nhầm dependency management với plugin management | Kiểm tra hai khu vực POM riêng biệt và khai báo plugin version khi không có parent |

## 11. Checklist khi viết hoặc review `pom.xml`

- [ ] Xác định ứng dụng **có kế thừa `spring-boot-starter-parent` không**.
- [ ] Nếu **có parent**, đã khai báo `spring-boot-maven-plugin` trong `<build><plugins>` và sử dụng version/execution được parent quản lý trừ khi có yêu cầu riêng.
- [ ] Nếu **không có parent**, đã quản lý **plugin version** rõ ràng và cấu hình `repackage` cho ứng dụng cần executable JAR.
- [ ] Không nhầm `<dependencyManagement>` với `<pluginManagement>`.
- [ ] BOM, runtime Spring Boot, plugin và Java toolchain dùng phiên bản được chọn có chủ đích.
- [ ] Module library không bị `repackage` nhầm; module ứng dụng chạy thật có main class phù hợp.
- [ ] Tùy chỉnh execution kế thừa dùng đúng id `repackage` để tránh chạy trùng.
- [ ] `help:effective-pom` cho thấy version và execution cuối cùng đúng ý định.
- [ ] `clean package` / `clean verify` thành công; `jar tf` xác nhận archive đúng; `java -jar` chạy được nếu đây là ứng dụng deploy.

**Cách ghi nhớ:** `spring-boot-starter-parent` cho bạn **plugin management và execution `repackage` đã chuẩn bị**; BOM `spring-boot-dependencies` chỉ cung cấp **dependency management**. Khi không kế thừa parent, bạn phải tự chốt **version + execution** cho `spring-boot-maven-plugin`. Căn cứ cuối cùng là **effective POM, log Maven và artifact đóng gói thực tế**.

## Tham khảo

- [Spring Boot Maven Plugin — Using the Plugin (3.3)](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives (3.3)](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)