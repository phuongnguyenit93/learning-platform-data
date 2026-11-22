# Thêm spring-boot-starter-actuator bằng Maven hoặc Gradle

## 1. Thêm starter để ứng dụng có khả năng vận hành

Một ứng dụng Spring Boot đã chạy được chưa chắc đã có các khả năng Actuator. Để bổ sung chúng, cách thông dụng là khai báo dependency:

~~~text
org.springframework.boot:spring-boot-starter-actuator
~~~

**Starter** là một đầu mối khai báo phụ thuộc: công cụ dựng sẽ lấy các thư viện liên quan và đưa chúng vào tập thư viện của ứng dụng. Nhờ đó, người viết ứng dụng không phải tự lựa chọn từng thành phần Actuator và cấu hình tự động tương ứng.

Sau khi các thư viện có mặt, Spring Boot còn xét điều kiện để tự cấu hình những khả năng phù hợp. Việc thêm starter không đồng nghĩa mọi endpoint đều được công khai hoặc ứng dụng đã có một hệ thống giám sát tập trung.

Cú pháp bổ sung starter chính thức được trình bày trong [Spring Boot 3.3 — Enabling Production-ready Features](https://docs.spring.io/spring-boot/3.3/reference/actuator/enabling.html).

Bài này dùng Spring Boot **3.3.13** làm phiên bản cụ thể cho ví dụ và JDK **21**. Spring Boot 3.3.13 yêu cầu Java từ 17, hỗ trợ Maven từ 3.6.3 và các dòng Gradle 7.x từ 7.5 hoặc 8.x. Với ví dụ Gradle chạy bằng JDK 21, có thể dùng wrapper 8.5, phiên bản đã hỗ trợ chạy Gradle bằng Java 21. Xem [Gradle 8.5 — Release Notes](https://docs.gradle.org/8.5/release-notes.html). Khi làm trên dự án có sẵn, giữ tuyến phiên bản và wrapper đã được dự án xác định. Xem [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html).

## 2. Phân biệt dependency, BOM và plugin

Ba thành phần này có trách nhiệm khác nhau:

| Thành phần | Vai trò | Có tự đưa starter Actuator vào ứng dụng không? |
| --- | --- | --- |
| Dependency `spring-boot-starter-actuator` | Yêu cầu công cụ dựng lấy starter và các phụ thuộc cần thiết | Có, khi khai báo ở phạm vi thích hợp |
| BOM `spring-boot-dependencies` | Cung cấp tập phiên bản được quản lý cho các dependency | Không; quản lý phiên bản không thay cho khai báo sử dụng |
| Spring Boot Maven/Gradle plugin | Bổ sung khả năng dựng, đóng gói và chạy ứng dụng Boot | Không tự thêm mọi starter vào ứng dụng |

**BOM (Bill of Materials)** là danh mục quản lý phiên bản. Spring Boot cung cấp một BOM cho mỗi phiên bản để các thư viện được lựa chọn nhất quán. Khi dự án đã dùng cơ chế quản lý đó, khai báo starter thường không cần ghi phiên bản riêng. Xem [Spring Boot 3.3 — Build Systems](https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html).

Ví dụ: đặt phiên bản Boot ở parent là 3.3.13 nhưng ép riêng Actuator sang một tuyến khác có thể tạo đồ thị phụ thuộc không đồng bộ. Hãy để cơ chế quản lý chung chọn phiên bản, trừ khi dự án có chủ đích ghi đè đã được kiểm tra.

Trong dự án nhiều module, cần xác định **module ứng dụng thực sự chạy** và nơi quản lý dependency của nó. Chỉ thêm starter vào một module không được ứng dụng sử dụng, hoặc chỉ liệt kê trong danh mục phiên bản, sẽ không làm starter xuất hiện trong ứng dụng đang chạy.

## 3. Phương án Maven

### 3.1. Dự án đã dùng parent hoặc BOM của Spring Boot

Thêm vào phần `<dependencies>` của module ứng dụng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Đây là một phần tử dependency để ghép vào POM hiện có, không phải toàn bộ tệp. Không cần thêm `<version>` nếu parent/BOM đã quản lý starter. Không đặt starter trong phạm vi `test` nếu muốn nó có mặt khi chạy ứng dụng chính.

Cũng không cần khai báo trực tiếp thêm `spring-boot-actuator` và `spring-boot-actuator-autoconfigure` chỉ để “bật đủ”. Starter đã dẫn tới các thành phần liên quan qua đồ thị phụ thuộc.

### 3.2. POM hoàn chỉnh cho dự án thử nghiệm

Nếu cần một dự án nhỏ để quan sát Actuator qua HTTP, có thể dùng `pom.xml` sau. Chọn phương án Maven này hoặc phương án Gradle ở phần tiếp theo cho cùng ví dụ.

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

    <groupId>example</groupId>
    <artifactId>actuator-start-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
~~~

Vai trò của các phần:

- Parent quản lý các phiên bản và cấu hình dựng thông dụng.
- `java.version` chọn mức Java của dự án thử nghiệm; máy dựng cần JDK phù hợp.
- Web starter tạo nền tảng web Servlet cho ví dụ gọi HTTP.
- Actuator starter bổ sung các thư viện vận hành.
- Maven plugin của Boot hỗ trợ chạy và đóng gói ứng dụng.

Parent của Boot cung cấp quản lý dependency và các mặc định cho plugin; vì vậy POM trên không ghi lại phiên bản cho từng starter hoặc cho Boot Maven plugin. Xem [Spring Boot 3.3 — Using the Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html).

### 3.3. Khi dự án phải giữ parent riêng

Nếu dự án đang kế thừa một parent khác, không cần thay parent đó chỉ để dùng Actuator. Có thể nhập BOM của Boot trong `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là phần ghép vào POM có sẵn. Vẫn phải khai báo starter trong `<dependencies>` của ứng dụng.

Nhập BOM chỉ cung cấp quản lý dependency; nó không mang theo toàn bộ quản lý plugin và mặc định biên dịch của `spring-boot-starter-parent`. Dự án giữ parent riêng cần có cấu hình Java/compiler và Boot plugin phù hợp nếu muốn dùng các lệnh chạy hoặc đóng gói tương ứng. Không xem riêng đoạn BOM này là một dự án hoàn chỉnh.

## 4. Phương án Gradle

### 4.1. Dự án đã có quản lý phiên bản của Spring Boot

Với Groovy DSL trong `build.gradle`, thêm vào khối dependencies đang có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Với Kotlin DSL trong `build.gradle.kts`, cú pháp tương ứng là:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Hai đoạn trên giả định phiên bản đã được cung cấp bởi dependency-management plugin hoặc BOM. Đừng bỏ phiên bản rồi kỳ vọng Gradle tự đoán khi dự án chưa có cơ chế quản lý nào.

`implementation` là lựa chọn thông thường cho ví dụ ứng dụng. Nếu chỉ dùng `testImplementation`, dependency chỉ thuộc phía kiểm thử; nếu dùng `compileOnly`, nó không được đưa vào runtime classpath của ứng dụng chính.

### 4.2. Ví dụ hoàn chỉnh bằng Groovy DSL

Trong `settings.gradle`:

~~~groovy
rootProject.name = 'actuator-start-demo'
~~~

Trong `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Khi cùng áp dụng Boot plugin và `io.spring.dependency-management`, Boot plugin tích hợp để nhập BOM ứng với phiên bản Boot đang dùng. Đó là lý do hai starter không cần ghi phiên bản riêng.

Gradle wrapper phải có sẵn và phù hợp, chẳng hạn 8.5 cho ví dụ này. JDK 21 cần được cài đặt hoặc có cơ chế cấp toolchain được cấu hình; chỉ khai báo toolchain không bảo đảm một máy chưa có JDK sẽ tự tải được nó.

### 4.3. Nếu dự án dùng BOM gốc của Gradle

Một cách khác là giữ plugin `java` và Boot plugin, không dùng `io.spring.dependency-management`, rồi khai báo platform:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Đây là biến thể của **cơ chế quản lý phiên bản**; không cần thêm đồng thời cả hai cách chỉ để starter hoạt động. Trong biến thể này, giữ phiên bản BOM nhất quán với phiên bản Boot plugin.

Gradle `platform` đưa các ràng buộc phiên bản vào đồ thị phụ thuộc; các khai báo hoặc ràng buộc khác vẫn có thể ảnh hưởng phiên bản thực sự được chọn. Vì vậy, kiểm tra kết quả resolve thay vì chỉ nhìn một dòng BOM. Hai cơ chế được giải thích trong [Spring Boot 3.3 — Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html).

## 5. Starter đưa những gì vào ứng dụng?

Có thể hình dung quan hệ chính như sau:

~~~text
Ứng dụng
└── spring-boot-starter-actuator
    ├── nền tảng starter chung
    ├── spring-boot-actuator-autoconfigure
    │   └── spring-boot-actuator
    └── các thành phần Micrometer liên quan
~~~

Sơ đồ chỉ thể hiện các quan hệ cần hiểu, không phải toàn bộ cây dependency. POM được xuất bản của starter 3.3.13 liệt kê các phụ thuộc trực tiếp, còn những thư viện phía dưới tiếp tục được công cụ dựng phân giải. Có thể đối chiếu tại [Maven Central — spring-boot-starter-actuator 3.3.13](https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-actuator/3.3.13).

Từ góc nhìn người sử dụng:

- **Starter** là điểm khai báo thuận tiện.
- **Actuator** chứa các thành phần vận hành.
- **Actuator auto-configuration** tích hợp chúng theo điều kiện của ứng dụng.
- **Cơ chế quản lý phiên bản** giúp giữ các thành phần tương thích theo tuyến Boot đã chọn.

Không cần tự giải nén JAR rồi chép thư viện vào source. Maven/Gradle chịu trách nhiệm tải và tổ chức các phụ thuộc dựa trên khai báo.

### Có Actuator chưa đồng nghĩa có HTTP server

Actuator starter không thay thế Web starter. Nếu dự án không có nền tảng web thích hợp, việc thêm riêng Actuator không tự biến nó thành ứng dụng HTTP trên cổng 8080.

Ví dụ thử nghiệm ở bài này thêm Web starter vì cần gọi health qua HTTP. Nếu ứng dụng có sẵn WebFlux và được thiết kế theo mô hình reactive, hãy giữ nền tảng đó; không thêm Web MVC chỉ vì muốn dùng Actuator. Ứng dụng không có HTTP vẫn có thể dùng các khả năng vận hành phù hợp với cấu hình của nó.

## 6. Ứng dụng thử nghiệm dùng chung cho hai phương án

Sau khi chọn Maven hoặc Gradle, tạo tệp:

~~~text
src/main/java/example/actuatorstarter/ActuatorStarterApplication.java
~~~

Nội dung Java đầy đủ:

~~~java
package example.actuatorstarter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorStarterApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorStarterApplication.class, args);
    }
}
~~~

Không cần tự viết controller cho health và không có annotation riêng bắt buộc kiểu “EnableActuator” trong ví dụ Boot 3.3 này.

Trong `src/main/resources/application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

Cấu hình chỉ lắng nghe loopback để thử cục bộ. Ví dụ giả định không có Spring Security, không đổi context path, không tách management port và không có cấu hình tắt health.

Không cần mở tất cả endpoint để xác minh lần đầu: trong Spring Boot 3.3, health được đưa ra HTTP theo mặc định. Việc bật endpoint, đưa ra HTTP và cấp quyền truy cập là những quyết định khác nhau. Xem [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 6.1. Chạy bằng Maven

Nếu dự án đã có Maven wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Nếu dùng Maven cài sẵn thay vì wrapper, lệnh tương ứng là `mvn spring-boot:run`, chạy trong thư mục chứa POM ứng dụng. Mục tiêu run do Spring Boot Maven plugin cung cấp. Xem [Spring Boot 3.3 — Running with Maven](https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html).

### 6.2. Chạy bằng Gradle

Nếu dự án đã có Gradle wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

Chạy trong thư mục dự án phù hợp; với dự án nhiều module cần gọi đúng task của module ứng dụng. BootRun sử dụng runtime classpath của mã ứng dụng chính. Xem [Spring Boot 3.3 — Running with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html).

Chỉ chạy một phương án tại một thời điểm nếu cả hai dùng cùng cổng 8080.

### 6.3. Gọi health và đọc đúng bằng chứng

Sau khi ứng dụng khởi động thành công, mở một cửa sổ PowerShell khác:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/actuator/health
~~~

Khi các kiểm tra sức khỏe hiện có đều tốt, mã trạng thái thường là 200 và body tối thiểu là:

~~~json
{"status":"UP"}
~~~

Đây là body HTTP; không phải dòng do phương thức main in ra stdout. Header, thời gian và log khởi động có thể thay đổi nên không coi chúng là đầu ra cố định.

Nếu gọi `/` và nhận 404 trong ví dụ tối thiểu, điều đó không chứng minh Actuator bị lỗi: mã trên không khai báo controller hoặc trang chủ cho đường dẫn gốc.

Cũng không dùng việc một endpoint khác chưa truy cập được để kết luận starter chưa được tải. Cần kiểm tra riêng dependency, trạng thái khởi động và cấu hình của endpoint đó.

## 7. Xác minh dependency thực sự đã được phân giải

Sửa tệp build chỉ là bước khai báo. Cần tải lại mô hình Maven/Gradle trong IDE, rồi dựng hoặc chạy lại ứng dụng với classpath mới.

### 7.1. Maven: xem cây dependency

~~~powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework.boot:spring-boot-starter-actuator"
~~~

Tìm một nút có tọa độ tương ứng:

~~~text
org.springframework.boot:spring-boot-starter-actuator:jar:3.3.13:compile
~~~

Đoạn trên là **tọa độ cần nhận ra**, không phải toàn bộ console output. Nếu dự án dùng phiên bản Boot khác, đọc phiên bản thực tế của dự án.

Muốn kiểm tra thêm các thành phần bên dưới:

~~~powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework.boot:spring-boot-actuator,org.springframework.boot:spring-boot-actuator-autoconfigure"
~~~

Maven Dependency Plugin hỗ trợ mục tiêu `dependency:tree` và bộ lọc `includes`. Xem [Apache Maven — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).

### 7.2. Gradle: xem phiên bản và lý do được chọn

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-boot-starter-actuator --configuration runtimeClasspath
~~~

Kiểm tra:

1. Có dependency khớp tên starter không?
2. Phiên bản được chọn là gì?
3. Có bị chọn lại do ràng buộc hoặc xung đột với khai báo khác không?
4. Đang xem đúng configuration của ứng dụng chính không?

Có thể xem rộng hơn bằng:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Các báo cáo dependency và dependencyInsight giúp nhìn đồ thị thực tế thay vì suy đoán từ tệp build. Xem [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).

### 7.3. Kiểm tra theo ba lớp bằng chứng

| Lớp kiểm tra | Bằng chứng cần tìm | Chưa đủ để kết luận điều gì? |
| --- | --- | --- |
| Khai báo | Starter nằm đúng trong POM/build.gradle của ứng dụng | Chưa chứng minh tải dependency thành công |
| Phân giải | Cây dependency/runtimeClasspath có starter và phiên bản phù hợp | Chưa chứng minh ứng dụng đã khởi động thành công |
| Chạy ứng dụng | Tiến trình khởi động và endpoint mong đợi phản hồi đúng điều kiện | Một lời gọi thành công chưa chứng minh mọi endpoint đã được mở |

Lần dựng đầu có thể cần mạng để tải parent, BOM, plugin, Gradle distribution và các JAR. Chế độ offline chỉ hoạt động khi những thành phần cần thiết đã có trong cache phù hợp.

Nếu công cụ không tải được dependency, cần phân biệt sai tọa độ/phiên bản với sự cố mạng, proxy, repository hoặc chế độ offline. Không nên tự đổi ngẫu nhiên sang một phiên bản starter khác chỉ để hết thông báo lỗi.

## 8. Các lỗi thường gặp khi thêm starter

| Biểu hiện | Hướng kiểm tra |
| --- | --- |
| Maven báo dependency thiếu version | Parent/BOM có thực sự được áp dụng cho module ứng dụng không? |
| Gradle không tìm được phiên bản cho starter không ghi version | Có dependency-management plugin hoặc BOM ở configuration phù hợp không? |
| Có starter trong phần quản lý phiên bản nhưng không có trong cây phụ thuộc | Đã khai báo sử dụng starter trong dependencies chưa? |
| IDE nhận thư viện nhưng ứng dụng đang chạy không có Actuator | Đã dựng/chạy lại đúng module với runtime classpath mới chưa? |
| Chỉ kiểm thử có Actuator | Có đặt nhầm `test` hoặc `testImplementation` không? |
| Dự án không có HTTP server | Có nền tảng web phù hợp không, hay đây là ứng dụng không có web? |
| Health không ở địa chỉ mặc định | Kiểm tra port, context path, management base path, exposure và security |
| Thêm nhiều dependency Actuator kèm phiên bản riêng để “chắc chắn” | Xem lại starter và cơ chế quản lý phiên bản chung trước |
| Task bootRun không tồn tại ở nơi gọi | Boot plugin có được áp dụng cho đúng project ứng dụng không? |
| Dự án nhiều module nhưng thêm vào module không được dùng | Kiểm tra đồ thị phụ thuộc của module thực sự khởi chạy |

Không cần mở `management.endpoints.web.exposure.include=*` để sửa một lỗi tải dependency. Exposure điều khiển giao diện vận hành được đưa ra HTTP; nó không sửa POM, không tải JAR và không giải quyết xung đột phiên bản.

### Tự thực hành

1. Với một ứng dụng Boot đã có parent/BOM, viết khai báo Actuator tối thiểu bằng công cụ dựng đang dùng.
2. Chỉ ra dòng nào quản lý phiên bản và dòng nào thực sự thêm starter vào ví dụ Maven hoặc Gradle.
3. Dùng dependency tree/insight để tìm phiên bản được chọn; nếu có thay đổi phiên bản, đọc lý do thay vì chỉ nhìn phiên bản đã khai báo.
4. Chạy dự án thử nghiệm và gọi health. Nếu không truy cập được, phân loại vấn đề thuộc tải thư viện, khởi động ứng dụng, HTTP mapping hay quyền truy cập.
5. Giải thích vì sao thêm Actuator vào `testImplementation` hoặc chỉ nhập BOM chưa đáp ứng yêu cầu dùng Actuator khi chạy ứng dụng chính.

**Gợi ý đối chiếu:** cần đồng thời có khai báo sử dụng ở phạm vi đúng, phiên bản được phân giải phù hợp và cấu hình chạy đáp ứng điều kiện của khả năng muốn dùng. Maven/Gradle lấy thư viện; Spring Boot tạo cấu hình phù hợp; HTTP endpoint chỉ xuất hiện theo môi trường và cấu hình tương ứng.
