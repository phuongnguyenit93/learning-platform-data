# Kế thừa spring-boot-starter-parent và tùy chỉnh thuộc tính bản dựng

## 1. Bài toán: Vì sao ứng dụng Spring Boot dùng Maven cần parent POM?

Một ứng dụng Spring Boot thường cần Spring Framework, thư viện web, JSON, logging, test và nhiều Maven plugin để biên dịch, kiểm thử, tạo JAR. Nếu tự chọn phiên bản cho từng thư viện và từng plugin, nhà phát triển phải kiểm tra thủ công xem những phiên bản ấy có hoạt động với nhau hay không. Hai thành viên có thể viết hai POM khác nhau cho cùng một nhu cầu; một lần nâng cấp cũng có thể vô tình làm xung đột dependency hoặc đổi cách đóng gói.

**spring-boot-starter-parent** là một **Maven parent POM** do Spring Boot cung cấp. Khi project khai báo nó trong thẻ **parent**, project kế thừa cấu hình Maven được Spring Boot chuẩn bị sẵn: phiên bản dependencies phổ biến, nhiều cấu hình plugins, Java compiler, encoding, resource filtering và cấu hình hỗ trợ tạo executable JAR/WAR.

Kết quả là POM của ứng dụng tập trung hơn vào **dự án thực sự cần dependency gì** và **muốn tùy chỉnh điểm nào**, thay vì sao chép một danh sách dài các phiên bản, mục tiêu và cấu hình build. Parent giúp giảm cấu hình lặp và tăng tính nhất quán; nó không đảm bảo mọi thư viện ngoài hệ sinh thái hay mọi thay đổi tùy ý sẽ tương thích.

### Mục tiêu sau bài học

- Hiểu **kế thừa parent POM** khác với thêm một dependency hay import BOM.
- Viết đúng thẻ **parent** và **properties** trong **pom.xml**.
- Biết những mặc định thường được Spring Boot parent cung cấp và phạm vi có thể ghi đè.
- Phân biệt phiên bản dependency được quản lý, plugin được cấu hình, Java target và cấu hình runtime.
- Dùng **help:effective-pom**, **help:evaluate**, **dependency:tree** để xác minh giá trị thực tế.
- Biết khi nào nên dùng parent và khi nào cần import **spring-boot-dependencies** vì dự án đã có parent khác.

## 2. Quan hệ giữa spring-boot-dependencies, spring-boot-starter-parent và ứng dụng

Sơ đồ quan hệ kế thừa thông dụng:

~~~text
org.springframework.boot:spring-boot-dependencies
              |
              | parent / thừa kế
              v
org.springframework.boot:spring-boot-starter-parent
              |
              | <parent> trong pom.xml của dự án
              v
com.example:parent-demo
              |
              +--> <dependencies>: starter-web, starter-test, ...
              +--> <properties>: java.version, encoding, ...
              +--> <build><plugins>: spring-boot-maven-plugin, ...
~~~

**spring-boot-dependencies** chứa tập dependency management đã được Spring Boot chọn để các thư viện thường dùng hoạt động chung với phiên bản Spring Boot đó. **spring-boot-starter-parent** kế thừa tập quản lý này và bổ sung các mặc định, plugin configuration, resource filtering và cách bind goal liên quan tới build ứng dụng. **POM ứng dụng** đặt parent để nhận các giá trị ấy và có thể ghi đè những phần thật sự cần thay đổi.

Đừng nhầm ba khái niệm:

| Thành phần | Đặt ở đâu? | Tác dụng chính |
| --- | --- | --- |
| **spring-boot-starter-parent** | **project > parent** | Kế thừa cấu hình POM, dependency management, plugin management và mặc định build |
| **spring-boot-dependencies** | Thường là parent gián tiếp; hoặc **dependencyManagement** với **type=pom, scope=import** | Quản lý phiên bản dependencies; khi import chỉ mang phần dependency management của BOM |
| **spring-boot-starter-web** (hoặc starter khác) | **dependencies** | Mang các thư viện cần cho một khả năng của ứng dụng, ví dụ web MVC |

Một parent POM **không tự đưa tất cả starters vào classpath**. Muốn viết ứng dụng web vẫn phải khai báo starter web; muốn dùng JDBC, Batch, Security hay Test thì khai báo những dependencies tương ứng. Parent quyết định nhiều **phiên bản**, còn thẻ **dependencies** quyết định ứng dụng **sử dụng những thư viện nào**.

## 3. Khai báo parent đúng cách

Ví dụ trên nhánh **Spring Boot 3.5**, dùng bản tài liệu đã được công bố là **3.5.16** để có ví dụ nhất quán:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>
~~~

Ý nghĩa:

- **groupId + artifactId** chỉ rõ POM cha do Spring Boot công bố.
- **version** chọn phiên bản Spring Boot mà dự án dùng làm đường chuẩn cho dependencies/build. Trong ví dụ đây là 3.5.16; với dự án thật phải chọn nhánh/bản patch theo chính sách nâng cấp và đối chiếu tài liệu của nhánh đó.
- **relativePath/** để trống là cách thường dùng với parent công bố trên Maven repository. Maven không thử lấy parent mặc định từ đường dẫn tương đối **../pom.xml** của thư mục bên cạnh, tránh vô tình nhận một POM cha không mong muốn.

Một dự án Maven chỉ có **một phần tử parent**. Không thể vừa kế thừa **spring-boot-starter-parent**, vừa kế thừa một **corporate-parent** khác trực tiếp trong cùng POM. Nếu tổ chức yêu cầu corporate parent, dùng phương án BOM ở phần sau và tự cấu hình các plugin cần thiết.

**Parent là cấu hình build, không phải dependency runtime.** Nó không xuất hiện như một thư viện chức năng được ứng dụng gọi trong Java; một phần tác dụng của parent là quyết định phiên bản thực tế của các dependency đã khai báo trong project.

## 4. Những gì parent thường cung cấp sẵn

Theo hướng dẫn Spring Boot Maven Plugin của nhánh 3.5, parent cung cấp các mặc định sau:

| Nhóm | Giá trị/khả năng được kế thừa | Lợi ích |
| --- | --- | --- |
| **Java** | Mức Java mặc định 17; dùng compiler release theo cấu hình parent | Có baseline nhất quán cho mã Java |
| **Encoding** | UTF-8 cho mã nguồn/tài nguyên | Giảm khác biệt ký tự giữa môi trường |
| **Compiler** | Biên dịch với **-parameters** | Giữ metadata tên tham số có ích cho cơ chế binding/reflection |
| **Dependencies** | Managed versions từ **spring-boot-dependencies** | Không cần đặt version cho phần lớn Spring Boot starters và các thư viện được quản lý |
| **Plugins** | Cấu hình/phiên bản mặc định cho nhiều Maven plugins phù hợp | Giảm nhu cầu tự khai báo phiên bản plugin |
| **Packaging** | Execution id **repackage** của Spring Boot Maven Plugin được cấu hình sẵn | Khi khai báo plugin, phase package có thể tạo executable JAR/WAR |
| **Resources** | Filtering hợp lý cho cấu hình ứng dụng | Có thể thay giá trị từ Maven properties vào application.properties/yml khi build |
| **Native** | Profile **native** được chuẩn bị để hỗ trợ build Native Image | Đỡ phải tự cấu hình toàn bộ phần nền tảng khi có nhu cầu native |

Không nên kết luận **“khai báo parent là Maven tự tạo executable JAR”**. Đối với project Maven ứng dụng, bạn còn cần khai báo **spring-boot-maven-plugin** trong phần plugins để execution **repackage** được kích hoạt đúng quy ước. Nếu chỉ có parent và không khai báo plugin, chưa nên coi output của package là Boot executable JAR.

Tương tự, **pluginManagement** thường định nghĩa phiên bản/cấu hình mặc định cho plugin; nó không có nghĩa mọi plugin trong đó đều tự được gọi. Việc plugin goal chạy thực tế còn phụ thuộc Maven lifecycle, execution binding, packaging và các plugin được khai báo/kích hoạt.

## 5. Ví dụ hoàn chỉnh: Maven POM kế thừa parent và đổi Java target

Ví dụ sau tạo ứng dụng HTTP nhỏ có endpoint **GET /info**. Để các lệnh dùng ngay với Wrapper, tạo project Maven bằng **Spring Initializr** hoặc một mẫu dự án tương đương có sẵn **mvnw**, **mvnw.cmd** và thư mục **.mvn/wrapper**. Ví dụ dùng Java 17; cần JDK 17+ tương thích với Spring Boot 3.5 trên máy build và runtime tương thích khi chạy JAR.

### 5.1. Cấu trúc tệp

~~~text
parent-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/parentdemo/ParentDemoApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/parentdemo/ParentDemoApplicationTests.java
~~~

### 5.2. pom.xml đầy đủ

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
    <artifactId>parent-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>parent-demo</name>
    <description>Minh hoa ke thua Spring Boot Maven parent</description>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
~~~

Các chi tiết cần quan sát:

1. **parent version 3.5.16** chọn nhánh Boot và các quy ước build.
2. Hai **starter dependencies** không cần thẻ **version** vì parent đã mang dependency management.
3. **java.version=17** là một property được parent sử dụng. Trong ví dụ, nó đặt rõ cùng mức Java mặc định; muốn dùng Java 21 phải đổi thành **21** và bảo đảm JDK compiler/runtime phù hợp.
4. **project.build.sourceEncoding=UTF-8** được viết tường minh để giải thích cú pháp ghi đè; parent đã cung cấp UTF-8 nên trong dự án bình thường có thể bỏ dòng này.
5. **spring-boot-maven-plugin** không cần thẻ **version** hoặc tự khai báo lại execution **repackage** khi dùng parent theo quy ước.
6. **starter-test** chỉ ở scope test và không phải dependency runtime được đóng gói vào executable JAR.

### 5.3. Mã Java hoàn chỉnh

Lưu tệp **src/main/java/com/example/parentdemo/ParentDemoApplication.java**:

~~~java
package com.example.parentdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ParentDemoApplication {

    @Value("${app.build.version}")
    private String buildVersion;

    @Value("${app.greeting}")
    private String greeting;

    public static void main(String[] args) {
        SpringApplication.run(ParentDemoApplication.class, args);
    }

    @GetMapping("/info")
    public String info() {
        return greeting + " / " + buildVersion;
    }
}
~~~

Lớp này có phương thức main và REST endpoint. Java source không tự chứa Spring Framework: nó biên dịch được vì Maven đã resolve **spring-boot-starter-web** theo dependency management của parent. Dấu **@Value** là annotation của Spring để lấy giá trị cấu hình tại runtime.

Lưu tệp **src/main/resources/application.properties**:

~~~properties
spring.application.name=parent-demo
app.build.version=@project.version@
app.greeting=${APP_GREETING:hello}
~~~

Đây là một ví dụ kết hợp hai cơ chế khác nhau:

- **@project.version@** là placeholder Maven **resource filtering ở build time**; khi process resources, Maven thay bằng **0.0.1-SNAPSHOT** lấy từ POM.
- **${APP_GREETING:hello}** là placeholder cấu hình Spring **ở runtime**; khi không có biến môi trường **APP_GREETING**, Spring dùng giá trị mặc định **hello**.

Để kiểm tra context khởi động, lưu tệp **src/test/java/com/example/parentdemo/ParentDemoApplicationTests.java**:

~~~java
package com.example.parentdemo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ParentDemoApplicationTests {

    @Test
    void contextLoads() {
        // Thành công nếu Spring application context khởi động không lỗi.
    }
}
~~~

Đoạn test chạy được với **spring-boot-starter-test** đã khai báo; nó kiểm tra context khởi động và sự hiện diện của các giá trị cấu hình cần thiết. Nó không thay thế test HTTP thực tế.

### 5.4. Build và quan sát output

Từ thư mục gốc project, trên Linux/macOS chạy:

~~~bash
./mvnw --version
./mvnw clean verify
java -jar target/parent-demo-0.0.1-SNAPSHOT.jar
~~~

Trên Windows dùng **mvnw.cmd** tương ứng. Khi ứng dụng đã khởi động trên cổng mặc định 8080 (nếu không có cấu hình cổng khác), ở terminal thứ hai:

~~~bash
curl http://localhost:8080/info
~~~

Với biến môi trường **APP_GREETING** không được khai báo, response body chính xác của endpoint trong ví dụ là:

~~~text
hello / 0.0.1-SNAPSHOT
~~~

Khi định nghĩa **APP_GREETING=welcome** cho tiến trình ứng dụng rồi chạy lại, phần greeting thay thành **welcome** còn project version đã lọc từ Maven POM vẫn là **0.0.1-SNAPSHOT**. Giá trị Maven được đóng vào artifact khi build; thay đổi POM version sau đó **không tự đổi** file JAR đã đóng gói.

**Đọc đúng kết quả:** **clean verify** chạy các phase của Maven tới verify theo những plugin/executions hiện hành và tạo artifact trong **target**. Với parent và Boot plugin đã khai báo ở ví dụ, goal **repackage** tạo JAR có thể chạy bằng **java -jar**. Log Maven không có một nội dung stdout duy nhất cho mọi máy, do nó phụ thuộc plugin version, cache và môi trường; phần output HTTP ở trên mới là giá trị xác định bởi code và cấu hình của bài.

## 6. Maven kế thừa và ghi đè thuộc tính như thế nào?

### 6.1. Parent và child POM

Ở Maven, POM của ứng dụng (child) nhận cấu hình có khả năng kế thừa từ POM cha. Child có thể khai báo lại một property cùng tên để thay đổi giá trị hiệu lực trong các cấu hình sử dụng property ấy.

Ví dụ, parent đặt Java 17 mặc định. Để chuyển Java mục tiêu sang 21 ở dự án Boot 3.5 có hỗ trợ Java 21, trong **pom.xml**:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

Sau thay đổi, phải dùng JDK/compiler có khả năng tạo class Java 21 và runtime tương ứng để chạy artifact, đồng thời kiểm tra khả năng tương thích của plugin và môi trường CI. **java.version** trong POM không tự cài JDK hoặc đổi JVM của server. Nếu môi trường deploy còn ở Java 17, build Java 21 bytecode sẽ không phù hợp.

Ở Spring Boot parent, **java.version** liên quan đến cài đặt compiler, bao gồm **maven.compiler.release** theo quy ước của parent. Đừng tự thêm các biến ngẫu nhiên như **jdk.version** rồi kỳ vọng parent đọc chúng: chỉ các property mà Maven hoặc plugin thực sự sử dụng mới có tác dụng.

### 6.2. Property do Maven hiểu, property do plugin hiểu và property tự đặt

| Ví dụ | Ai sử dụng? | Hệ quả |
| --- | --- | --- |
| **java.version** | Cấu hình Spring Boot parent | Chọn baseline Java compilation qua cấu hình parent |
| **maven.compiler.release** | Maven Compiler Plugin | Yêu cầu mức bytecode và API chuẩn cho bản Java mục tiêu |
| **project.build.sourceEncoding** | Các plugin dùng property encoding | Quy định encoding cho nguồn/tài nguyên khi plugin hỗ trợ |
| **slf4j.version** | Spring Boot dependency management theo nhánh hỗ trợ | Chọn version SLF4J managed trong POM thừa kế parent |
| **resource.delimiter** | Cấu hình resource filtering của parent | Điều chỉnh dấu phân cách token Maven khi lọc resources |
| **app.message** | Property do project tự tạo | Chỉ có hiệu lực khi được POM/plugin/resource tham chiếu |
| **spring-boot.run.profiles** | Spring Boot Maven Plugin lúc gọi run | Chọn Spring profiles khi chạy goal Spring Boot run |

Một property mới như **app.message=hello** không tự làm Spring Boot nhận thông tin runtime. Nó cần được nối qua **resources filtering**, system property, environment hoặc plugin configuration. Tương tự, không nên nhầm tên property Maven với các key **spring.* ** mà ứng dụng nhận từ **application.properties**.

### 6.3. Ghi đè property đã quản lý phiên bản dependencies

Giả sử một thư viện được Spring Boot BOM quản lý thông qua property **slf4j.version** (property này có trong danh sách nhánh Boot 3.5). Với dự án trực tiếp kế thừa **spring-boot-starter-parent**, có thể định nghĩa lại property đó trong child POM:

~~~xml
<properties>
    <java.version>17</java.version>
    <slf4j.version>2.0.17</slf4j.version>
</properties>
~~~

Đây là **ví dụ cú pháp override**, không phải khuyến nghị bắt buộc đổi SLF4J sang 2.0.17. Trước khi áp dụng một version ngoài mặc định, cần xác nhận tính tương thích với Spring Boot release đang dùng, thư viện logging khác, chính sách bảo mật và test thực tế. Spring Boot đã kiểm chứng một tập phiên bản đi cùng nhau; override bừa có thể gây xung đột lúc chạy dù Maven vẫn resolve được.

Để biết một property có thực sự được nhánh Boot đang dùng hỗ trợ, xem **Dependency Versions Properties** của **đúng nhánh/version**. Không suy ra property từ bài viết phiên bản cũ và coi nó vẫn tồn tại trong mọi nhánh mới.

### 6.4. Ghi đè version dependency ngay ở thẻ dependency

Có thể khai báo **version** ngay trong dependency nếu cần một phiên bản đặc thù:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.17</version>
</dependency>
~~~

Đây cũng là **đoạn XML minh họa**, phải đặt trong **dependencies** của POM hoàn chỉnh. Version tường minh cho dependency đó có thể ưu tiên hơn managed default của BOM. Tuy nhiên, chỉ thay một artifact riêng lẻ trong một nhóm thư viện có liên hệ chặt có thể làm graph thiếu nhất quán. Khi thay một nhóm/version train, nên đánh giá cả BOM và kiểm tra **dependency:tree**.

## 7. Tùy chỉnh compiler: java.version, release, source và target

### 7.1. Cấu hình thường dùng nhất

Với project Boot 3.5 sử dụng Java 21, phần thông dụng là:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

**maven.compiler.release** được parent cấu hình dựa trên Java target. Khi Java compiler dùng tùy chọn **--release**, nó không chỉ đặt mức class file mà còn giới hạn truy cập API của Java tiêu chuẩn theo mức mục tiêu, giúp tránh tình trạng biên dịch trên JDK mới nhưng vô tình dùng API không có ở Java mục tiêu.

**Ví dụ:** biên dịch với JDK 21 nhưng muốn tạo thư viện Java 17-compatible thì có thể sử dụng **--release 17** trong dự án Java thuần có dependency phù hợp. Nhưng với **Spring Boot 3.5**, toàn bộ runtime vẫn cần Java ít nhất 17; chỉ hạ **release** xuống 11 không khiến một ứng dụng Spring Boot 3.5 chạy được trên Java 11.

### 7.2. Cần tùy chỉnh Maven Compiler Plugin khi nào?

Thông thường parent đã lo các giá trị cần thiết. Nếu có yêu cầu compiler đặc biệt (annotation processors, warnings, tham số), có thể khai báo plugin trong **build/plugins** và chỉ đặt những field cần thay đổi, để phần còn lại được quản lý:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <showWarnings>true</showWarnings>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn build bổ sung**, không nên dán thêm nguyên một phần **build** thứ hai vào cùng POM. Khi áp dụng vào project thực, ghép plugin này cùng danh sách plugins đã có.

Trong trường hợp đặc biệt phải dùng các tùy chọn **--add-exports**, **--add-reads** hay **--patch-module** can thiệp vào system modules, Spring Boot Maven Plugin documentation lưu ý cách dùng **maven.compiler.release** có thể chặn các tùy chọn đó. Tài liệu hướng dẫn có thể bỏ release và dùng **maven.compiler.source/target**. Đây là ngoại lệ cần đánh giá kỹ vì source/target không đảm bảo hạn chế Java APIs giống --release; tránh đổi nếu chưa có nhu cầu xác đáng.

### 7.3. Maven Wrapper và toolchain là chuyện khác

**mvnw** ghim bản **Maven** (khi dự án có Wrapper), còn **java.version** điều khiển mức biên dịch; cả hai không tự chọn hay cài được bản JDK máy chủ. Có thể cần JDK phù hợp trên PATH/JAVA_HOME hoặc **Maven Toolchains Plugin** để chọn JDK biên dịch độc lập với JVM chạy Maven.

Luôn kiểm tra bằng:

~~~bash
java -version
./mvnw --version
./mvnw help:evaluate -Dexpression=java.version -q -DforceStdout
./mvnw help:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
~~~

Hai lệnh **help:evaluate** dùng Maven Help Plugin; khi cấu hình đúng, giá trị mong đợi với POM ví dụ là **17** cho Java target và compiler release. Đầu ra console có thể kèm thông tin/log của Maven tùy phiên bản và chế độ thực thi.

## 8. Đọc cấu hình hiệu lực bằng effective POM

Một POM thường chỉ có vài chục dòng **không phải toàn bộ cấu hình mà Maven thực sự dùng**. Plugin version và executions có thể đến từ parent POM, super POM, active profile hoặc POM của module. Công cụ quan trọng là:

~~~bash
./mvnw help:effective-pom
./mvnw help:effective-pom -Dverbose=true
./mvnw help:active-profiles
./mvnw dependency:tree
~~~

Trong kết quả **help:effective-pom**, tìm:

- **properties**: phiên bản/giá trị cuối cùng cho **java.version**, **maven.compiler.release** và những property khác.
- **dependencyManagement**: phiên bản được quản lý theo groupId/artifactId.
- **build/pluginManagement**: phiên bản/cấu hình mặc định của plugins.
- **build/plugins** và **executions**: plugin nào được khai báo và goal nào được bind vào lifecycle.
- **resources**: những thư mục và tùy chọn filtering thực tế.
- **profiles** (khi được kích hoạt): phần cấu hình thay đổi theo profile đang chọn.

**help:effective-pom -Dverbose=true** có thể thêm thông tin nguồn gốc cấu hình, giúp trả lời “dòng này đến từ parent nào?”. **help:active-profiles** cho biết profile được kích hoạt trong lần gọi hiện tại. **dependency:tree** kiểm tra phiên bản dependency đã resolve và phụ thuộc bắc cầu; một POM management có version không có nghĩa library đó đã xuất hiện trong classpath nếu project không phụ thuộc nó.

Ví dụ dùng chính POM ở phần 5:

~~~bash
./mvnw help:evaluate -Dexpression=project.version -q -DforceStdout
./mvnw help:evaluate -Dexpression=java.version -q -DforceStdout
./mvnw dependency:tree -Dincludes=org.springframework.boot
~~~

Giá trị logic của hai expression đầu lần lượt là **0.0.1-SNAPSHOT** và **17**. Danh sách dependencies có thể dài và phụ thuộc vào phiên bản Spring Boot; không nên ghi một cây dependency cứng rồi cho rằng máy nào cũng giống nhau.

Các lệnh Help Plugin chủ yếu phục vụ xem thông tin, **không phải Maven dry-run cho toàn bộ lifecycle**; chúng vẫn có thể truy cập repository/cache để resolve plugins. Việc xem effective POM không chứng minh compile, test hoặc repackage đã thành công.

## 9. Tùy chỉnh việc đóng gói qua Spring Boot Maven Plugin

### 9.1. Khai báo plugin để kích hoạt repackage

Trong POM kế thừa parent, thông thường chỉ cần:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Parent đã chuẩn bị execution **id=repackage**, nên khi goal này được kích hoạt trong package, archive thông thường được đóng gói thành executable JAR/WAR. Không nên khai báo thêm một execution **repackage** không cần thiết rồi khiến goal chạy hai lần hoặc tạo artifact ngoài ý muốn.

**spring-boot:repackage** hoạt động trên archive đã được build ở phase package. Nếu cần chạy goal thủ công trong một trường hợp không bind sẵn, tài liệu Boot khuyến nghị có phase package đi trước, chẳng hạn **mvn package spring-boot:repackage**. Với parent được cấu hình đúng, lệnh **./mvnw package** đã đủ để kích hoạt repackage.

### 9.2. Khi cần giữ cả plain JAR và executable JAR

Trong project có nhu cầu xuất hai artifact, có thể cấu hình **classifier** cho execution có id **repackage**:

~~~xml
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
~~~

Đây là **một lựa chọn thay thế** cho phần build/plugin ở ví dụ ban đầu, không phải đoạn cần dán song song để tạo hai lần khai báo cùng plugin. Khi dự án dùng parent, việc nêu đúng execution id giúp **gộp cấu hình với execution kế thừa**. Với artifact name/version ví dụ, cách cấu hình này thường tạo **parent-demo-0.0.1-SNAPSHOT.jar** dạng plain JAR và **parent-demo-0.0.1-SNAPSHOT-exec.jar** dạng executable JAR. Lệnh chạy phải trỏ đến file **-exec.jar** tương ứng; không mặc định mọi JAR trong target đều bootable.

Không tùy tiện dùng executable JAR làm dependency của ứng dụng Java khác: cấu trúc Boot JAR đưa classes vào **BOOT-INF/classes** và khác plain JAR. Tùy use case, một module thư viện nên giữ plain JAR.

### 9.3. Đổi tên file archive

Nếu muốn đặt tên file kết quả không phụ thuộc artifactId/version, có thể cấu hình Maven build:

~~~xml
<build>
    <finalName>my-service</finalName>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Với packaging jar và không dùng classifier, output trong **target** thường là **my-service.jar**. Đây là **thẻ build/finalName**, không phải property tùy ý **final.name**; bạn phải sửa đúng vị trí XML. Việc thay tên file không tự đổi **groupId:artifactId:version** là định danh Maven của artifact.

## 10. Resource filtering: tùy chỉnh giá trị lúc build mà không làm hỏng Spring placeholders

Đây là tính năng dễ gây hiểu nhầm nhất khi dùng parent.

### 10.1. Hai cú pháp placeholder có hai thời điểm xử lý

Xét file **application.properties**:

~~~properties
app.build.version=@project.version@
app.build.java=@java.version@
app.greeting=${APP_GREETING:hello}
~~~

| Cú pháp | Bên xử lý | Thời điểm | Ví dụ sau xử lý |
| --- | --- | --- | --- |
| **@project.version@** | Maven Resources Plugin theo cấu hình parent | Khi build/process-resources | 0.0.1-SNAPSHOT |
| **@java.version@** | Maven Resources Plugin | Khi build/process-resources | 17 |
| **${APP_GREETING:hello}** | Spring Environment / placeholder resolution | Khi ứng dụng khởi động/đọc property | hello nếu không có APP_GREETING |

Spring Boot parent sử dụng dấu **@...@** cho Maven filtering để tránh đụng cú pháp **${...}** mà Spring dùng trong file cấu hình. Nếu bật Maven filtering theo kiểu thay **${...}**, dễ làm thay nhầm placeholder mà bạn muốn dành cho runtime. Có thể tùy chỉnh property **resource.delimiter** nhưng phải xem kỹ tác động đến mọi config file đang lọc.

### 10.2. Chú ý đường đi của resources

Theo tài liệu Spring Boot, cấu hình filtering mặc định chủ yếu áp dụng cho **production application config** dưới **src/main/resources**; **src/test/resources** không được parent tự lọc theo cùng cách. Không nên khẳng định mọi file trong project đều có thể chứa token @...@ rồi chắc chắn được thay.

Để xem file đã được lọc hay chưa, chạy Maven lifecycle đến **process-resources** hoặc package rồi kiểm tra output:

~~~bash
./mvnw process-resources
~~~

Sau đó tìm **target/classes/application.properties**. Với POM ví dụ, file đã xử lý sẽ chứa giá trị:

~~~properties
spring.application.name=parent-demo
app.build.version=0.0.1-SNAPSHOT
app.greeting=${APP_GREETING:hello}
~~~

Điều này chứng minh Maven đã thay token **@project.version@** nhưng vẫn giữ biểu thức dành cho Spring. Nếu cấu hình plugin **spring-boot:run** bật **addResources=true**, nó có thể đưa thẳng resources gốc vào classpath và **bỏ qua bước filtering**, khiến hành vi khi bootRun khác artifact đóng gói. Khi cần xác minh resource filtering, thử chính JAR sau package.

### 10.3. Cẩn thận với tệp nhị phân và secrets

Không nên bật **filtering=true** cho mọi resource một cách mù quáng: những file nhị phân như ảnh, font, chứng chỉ, keystore hoặc nén có thể bị xử lý sai. Cũng không nên đóng **password**, **token** hoặc **secret theo môi trường** trực tiếp vào JAR qua property filtering; giá trị đã lọc sẽ trở thành một phần của artifact có thể được trích xuất. Dùng biến môi trường, secret manager hoặc cấu hình runtime phù hợp cho dữ liệu nhạy cảm.

## 11. Phân biệt Maven build properties, Maven profiles và Spring profiles

Ba khái niệm xuất hiện gần nhau nhưng có trách nhiệm khác nhau:

- **Maven properties**: các giá trị để cấu hình POM và plugins, ví dụ **java.version** hoặc **project.build.sourceEncoding**.
- **Maven profiles**: các nhánh cấu hình build được kích hoạt bởi **-Pprofile-id**, có thể đổi dependencies, plugin executions, repositories hoặc build properties.
- **Spring profiles**: tập cấu hình/beans runtime của ứng dụng, chẳng hạn **dev**, **test**, **prod**, do Spring Environment xử lý.

Ví dụ một Maven profile minh họa đặt property:

~~~xml
<profiles>
    <profile>
        <id>dev-build</id>
        <properties>
            <app.build.label>development</app.build.label>
        </properties>
    </profile>
</profiles>
~~~

Nếu file **application.properties** có **app.build.label=@app.build.label@** và cấu hình filtering phù hợp, gọi **./mvnw -Pdev-build package** tạo artifact có giá trị **development** đã được lọc lúc build. Nếu property không có default và profile không được kích hoạt, token có thể không được thay như mong đợi; cần định nghĩa một giá trị mặc định khi sử dụng thật.

Trong khi đó, Spring Boot Maven Plugin hỗ trợ chạy ứng dụng với runtime profile:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
~~~

Cờ này tác động tới **Spring profile khi goal run khởi động ứng dụng**, không đồng nghĩa kích hoạt Maven profile tên dev. Còn **java -jar app.jar --spring.profiles.active=prod** dùng cấu hình Spring runtime của artifact đã tạo. Vì vậy tránh coi **-Pprod**, **-Dspring-boot.run.profiles=prod** và **--spring.profiles.active=prod** là những cách viết thay thế nhau.

Một practice dễ bảo trì là dùng một artifact đã được kiểm thử, rồi cung cấp khác biệt môi trường bằng cấu hình/runtime properties thay vì build nhiều JAR riêng chứa secrets cho từng môi trường.

## 12. Khi dự án đã có corporate parent: dùng BOM thay thế như thế nào?

Maven chỉ cho phép **một parent trực tiếp**. Nếu dự án đã buộc kế thừa POM cha của tổ chức, cách phổ biến để tiếp tục dùng **managed dependencies** của Spring Boot là import BOM:

~~~xml
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
~~~

Đây là **một phần của POM sử dụng parent khác**, không phải đoạn phải cộng thêm vào POM đã kế thừa **spring-boot-starter-parent** trong phần 5.

**Import BOM mang theo dependency management, không mang theo parent plugin management/resource filtering/build defaults**. Vì vậy lúc đó dự án cần tự đảm bảo:

- Spring Boot Maven Plugin được khai báo với version phù hợp.
- Execution **repackage** được bind nếu muốn executable JAR/WAR.
- Maven Compiler Plugin và mức Java target được đặt chính xác.
- Maven Resources Plugin/resource filtering được cấu hình phù hợp.
- Các Maven plugins quan trọng có phiên bản được quản lý ổn định.

Ví dụ chỉ riêng cách bind repackage khi không dùng parent:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.5.16</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Nếu đã dùng BOM import mà muốn **ghi đè phiên bản thư viện**, việc chỉ đặt property cùng tên trong POM con thường **không hoạt động như cơ chế kế thừa parent**. Theo hướng dẫn Spring Boot, cách an toàn và rõ ràng là khai báo mục riêng trong **dependencyManagement** trước mục import Boot BOM, hoặc dùng BOM ưu tiên theo quy tắc Maven và xác minh bằng **dependency:tree**.

Đây là khác biệt cần nhớ:

| Quyết định | Kế thừa starter-parent | Import spring-boot-dependencies BOM |
| --- | --- | --- |
| Nhận managed dependency versions | Có | Có |
| Nhận plugin management của Boot parent | Có | Không |
| Nhận compiler/encoding/resource defaults của Boot parent | Có | Không |
| Nhận execution repackage được cấu hình sẵn | Có (khi khai báo plugin phù hợp) | Không; phải cấu hình |
| Override managed version qua property của parent | Có với property được Boot hỗ trợ | Không theo cùng cơ chế; cần dependencyManagement phù hợp |
| Giữ một parent khác của doanh nghiệp | Không thể cùng lúc trực tiếp | Có |

Đừng chọn BOM-only vì nghĩ nó “tương đương 100%” với parent. Hai phương án có trách nhiệm và phạm vi inheritance khác nhau.

## 13. Cách xác định một thiết lập đã có hiệu lực thật

Đọc cấu hình là bước đầu, kiểm chứng artifact là bước cuối.

### Kiểm tra phiên bản Boot và JDK

~~~bash
./mvnw --version
./mvnw help:evaluate -Dexpression=project.parent.version -q -DforceStdout
./mvnw help:evaluate -Dexpression=java.version -q -DforceStdout
~~~

Đối với POM demo, hai expression cuối có giá trị logic lần lượt **3.5.16** và **17**. Nếu cấu hình khác với mong đợi, xem effective POM cùng profile và các property do CI truyền vào.

### Kiểm tra dependency versions

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.boot
~~~

Nếu dependency chưa được khai báo hoặc không có phụ thuộc bắc cầu dẫn tới nó, managed version vẫn có thể tồn tại trong POM nhưng dependency sẽ không xuất hiện trong tree. Một parent/BOM quản lý version **không bắt buộc đưa library vào ứng dụng**.

### Kiểm tra plugin execution

~~~bash
./mvnw help:effective-pom -Dverbose=true
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
~~~

Tìm **spring-boot-maven-plugin** trong **build/plugins**, execution **repackage** và thông tin version plugin được quản lý. Mô tả goal giải thích chức năng goal; effective POM xác định nó được cấu hình thế nào cho dự án. Nếu cần kiểm tra log thực, chạy **./mvnw clean package** trên môi trường build được phép và tìm dòng goal **spring-boot:repackage**.

### Kiểm tra artifact và resource filtering

~~~bash
./mvnw clean package
java -jar target/parent-demo-0.0.1-SNAPSHOT.jar
~~~

Một executable JAR Boot thông thường chứa **BOOT-INF/classes** và **BOOT-INF/lib**. Các class được đóng gói phải chứa app config đã lọc. Khi Java process start thành công nhưng endpoint không như mong đợi, kiểm tra profile/env/runtime config và **target/classes/application.properties**; đừng vội giả định parent đã chọn sai dependency.

### Kiểm tra test

~~~bash
./mvnw clean verify
~~~

Đây là bản dựng thật, không chỉ xem kế hoạch. Maven chạy các plugin goals được bind trong lifecycle và những kiểm thử đã cấu hình. Tránh khẳng định một lần **BUILD SUCCESS** thay thế hoàn toàn integration test hay smoke test production.

## 14. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Maven yêu cầu version cho **spring-boot-starter-web** | Parent/BOM không được resolve, tên dependency sai, hoặc nó không thuộc tập được quản lý | Xem parent/BOM effective POM và Maven repository |
| **Non-resolvable parent POM** | Sai version, Maven repository/network/proxy hoặc relativePath đang trỏ nhầm | Xem parent coordinates, dùng relativePath rỗng khi lấy từ repository |
| Đổi **java.version** nhưng vẫn dùng JDK khác | Property không cài/thay JDK chạy Maven | Kiểm tra ./mvnw --version, JDK/toolchain và compiler target |
| **release version 21 not supported** | Maven đang dùng compiler JDK không hỗ trợ Java 21 | Cung cấp JDK 21 hoặc toolchain phù hợp |
| **UnsupportedClassVersionError** lúc java -jar | JVM deploy quá cũ với class file/Boot dependencies | Đồng bộ compiler target và JVM runtime |
| **no main manifest attribute** | Chạy plain JAR hoặc Spring Boot repackage chưa thực hiện | Khai báo plugin và kiểm tra execution/output archive |
| **@project.version@** vẫn còn trong application.properties sau build | Resource filtering không hoạt động trên file đang dùng hoặc path bị thay | Xem target/classes, plugin resources, addResources |
| **${...}** runtime bị thay trước khi chạy | Cấu hình Maven filtering sử dụng delimiter xung đột với Spring | Dùng @...@ và kiểm tra resource.delimiter |
| Thêm **slf4j.version** mà phiên bản không đổi | Project chỉ import BOM hoặc property không còn được nhánh Boot quản lý | Xem đúng Version Properties, dependencyManagement và dependency:tree |
| Cùng parent nhưng CI resolve thư viện khác laptop | Maven settings/profiles, repository, version overrides, snapshot hoặc cache khác | So sánh command, active-profiles, effective POM và tree |
| Compile pass nhưng test thiếu dependency | Chưa khai báo test starter/scope sai hoặc test được skip | Xem dependency scope và Surefire/test reports |
| Cấu hình plugin trong **pluginManagement** nhưng goal không chạy | Plugin chưa được khai báo/kích hoạt hoặc chưa bind execution | Kiểm tra build/plugins và lifecycle |
| **-Pprod** không bật Spring runtime profile prod | Maven profile khác Spring profile | Dùng spring-boot.run.profiles hoặc spring.profiles.active đúng hoàn cảnh |

### Lưu ý về các cờ bỏ qua kiểm thử

**-DskipTests** thường yêu cầu Surefire/Failsafe bỏ chạy test, còn **-Dmaven.test.skip=true** còn có thể bỏ qua cả biên dịch test; chúng không tương đương nhau và không nên dùng làm đường build phát hành mặc định. Cũng không thể kết luận có test được chạy chỉ vì phase package/verify tồn tại: phải kiểm tra plugin test và log/report. Khi gặp lỗi, hãy sửa nguyên nhân thay vì coi skip test là cách chứng minh bản dựng hợp lệ.

## 15. Checklist thực hành và câu hỏi tự đánh giá

### Checklist

- [ ] POM có **một** parent phù hợp, với **groupId/artifactId/version** và **relativePath** chính xác.
- [ ] Chọn Spring Boot patch được dự án hỗ trợ; Java build/runtime phù hợp với nhánh Boot.
- [ ] Chỉ khai báo dependencies cần thiết, bỏ version ở các thư viện đã được Boot quản lý.
- [ ] Tùy chỉnh **java.version**, encoding và plugin configuration có chủ đích, tránh sao chép toàn bộ cấu hình parent.
- [ ] Khai báo **spring-boot-maven-plugin** nếu cần executable JAR/WAR; kiểm tra execution **repackage**.
- [ ] Xác nhận resource filtering của **application.properties/yml** bằng output trong **target/classes**; phân biệt Maven @...@ và Spring ${...}.
- [ ] Kiểm tra **effective POM**, **active profiles**, **dependency tree** khi thay version.
- [ ] Chạy test, package và **java -jar** với artifact thực tế; dùng Maven Wrapper trong CI.
- [ ] Nếu công ty có parent bắt buộc, import Boot BOM và tự bổ sung plugin/build defaults còn thiếu.

### Câu hỏi 1: Có parent rồi, bỏ hoàn toàn dependencies có được không?

Không. Parent cung cấp các mặc định và version management; project vẫn phải khai báo **starter-web**, **starter-data-jpa**, **starter-test** hoặc dependencies cần dùng. Thiếu dependency nghĩa là classpath không có thư viện chức năng tương ứng.

### Câu hỏi 2: Có thể vừa đặt corporate-parent vừa đặt spring-boot-starter-parent trong một POM không?

Không. Mỗi POM Maven có một parent trực tiếp. Có thể chọn parent chuẩn của công ty và import **spring-boot-dependencies** BOM; khi đó phải tự lo phần plugin management và build conventions cần thiết.

### Câu hỏi 3: Vì sao đã có parent nhưng Maven chưa tạo executable JAR?

Phải kiểm tra **spring-boot-maven-plugin** có trong **build/plugins**, execution **repackage** có được thừa kế/kích hoạt đúng, packaging có phù hợp và project có main class. Parent cung cấp cấu hình execution; khai báo plugin và thực hiện lifecycle phù hợp mới tạo artifact executable.

### Câu hỏi 4: Đổi Java 17 sang Java 21 chỉ bằng property có đủ không?

Chưa. Property điều chỉnh mức biên dịch theo parent nhưng không nâng JDK trên máy build, CI hay server. Cần kiểm tra compiler, Boot/plugin compatibility, toolchain và runtime.

### Câu hỏi 5: Tại sao application.properties dùng @project.version@ mà không dùng ${project.version}?

Parent cố ý chọn delimiter **@...@** cho Maven filtering để tránh xung đột với placeholder **${...}** của Spring tại runtime. Hai loại token thuộc hai giai đoạn khác nhau của ứng dụng.

### Câu hỏi 6: Khi import BOM, tại sao property override version không giống lúc kế thừa parent?

Vì BOM import chỉ đưa dependency management vào POM, không kế thừa toàn bộ properties/plugin configuration theo cấu trúc parent. Muốn override managed dependency trong nhánh BOM-only, dùng mục **dependencyManagement** ưu tiên phù hợp và kiểm tra kết quả.

## 16. Tóm lược cơ chế và nguồn tham khảo

Chuỗi trách nhiệm dễ nhớ là:

~~~text
POM child khai báo <parent>
      |
      +--> Kế thừa defaults / managed versions / plugin settings
      |
      +--> <properties> ghi đè những phần cần thiết
      |
      +--> <dependencies> chọn thư viện được dùng
      |
      +--> <build><plugins> kích hoạt và tùy chỉnh hành vi build
      |
      v
Maven giải effective POM -> dependency graph -> compile/test/package
      |
      v
Spring Boot Maven Plugin: repackage -> executable archive
      |
      v
java -jar + runtime configuration -> ứng dụng hoạt động
~~~

**spring-boot-starter-parent** giúp bắt đầu từ bộ defaults đã được Spring Boot thiết kế để dùng cùng nhau. Khai báo phần cần thay đổi trong **properties** hoặc plugin configuration, quan sát **effective POM** và kiểm tra **artifact thật** là cách sử dụng parent an toàn, dễ kiểm soát và bảo trì hơn.

### Tài liệu chính thức

- Spring Boot 3.5 — Maven Plugin, Using the Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot 3.5 — Dependency Version Properties: https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/properties.html
- Spring Boot 3.5 — Build Systems: https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html
- Spring Boot 3.5 — Build (Executable JAR): https://docs.spring.io/spring-boot/3.5/how-to/build.html
- Spring Boot 3.5 — Properties and Configuration (Maven filtering): https://docs.spring.io/spring-boot/3.5/how-to/properties-and-configuration.html
- Spring Boot — Maven Plugin Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Apache Maven — POM Reference (Inheritance, Properties, Plugin Management): https://maven.apache.org/pom.html
- Apache Maven — Introduction to Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven Help Plugin — Effective POM: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Help Plugin — Evaluate: https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html
