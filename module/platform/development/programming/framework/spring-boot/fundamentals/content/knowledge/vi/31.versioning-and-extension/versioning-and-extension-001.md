# Quan hệ phiên bản giữa Spring Boot, Spring Framework và JDK

Khi bắt đầu hoặc nâng cấp một ứng dụng Spring Boot, có ba phiên bản cần được xem xét cùng nhau:

- **Spring Boot:** nền tảng tích hợp, auto-configuration, starters, plugin build và bộ dependency được quản lý.
- **Spring Framework:** nền tảng cốt lõi cung cấp IoC container, dependency injection, AOP, transaction, web và các API Spring.
- **JDK:** môi trường Java dùng để build, compile và chạy ứng dụng.

Ba thành phần này có quan hệ tương thích nhưng **không có cùng số phiên bản và không thay thế lẫn nhau**. Ví dụ, một dự án có thể dùng Spring Boot 3.x, Spring Framework 6.x và JDK 17 hoặc một JDK mới hơn được release đó hỗ trợ.

Sai lệch phiên bản có thể gây lỗi ngay khi build, lỗi lúc khởi động, lỗi liên kết class/method hoặc lỗi chỉ xuất hiện khi chạy một chức năng cụ thể. Hiểu cách Spring Boot quản lý Spring Framework và cách JDK ảnh hưởng tới bytecode là nền tảng để chọn cấu hình ổn định.

## 1. Ba thành phần, ba trách nhiệm

Có thể hình dung quan hệ tổng quát:

~~~text
                  JDK
      compile / bytecode / runtime
                    |
                    v
             Spring Framework
      IoC / DI / AOP / transaction / web
                    |
                    v
               Spring Boot
  auto-configuration / starters / BOM / plugins
                    |
                    v
             Ứng dụng thực tế
~~~

Ứng dụng Spring Boot sử dụng API của Spring Framework và chạy trên JVM do JDK cung cấp. Spring Boot tập hợp và cấu hình các thành phần này để giảm công việc tích hợp thủ công.

| Thành phần | Vai trò | Phiên bản quyết định điều gì? |
|---|---|---|
| Spring Boot | Nền tảng tích hợp ứng dụng | Bộ dependency, auto-configuration, plugin và yêu cầu Java |
| Spring Framework | Core framework | API container, AOP, transaction, MVC, WebFlux và module liên quan |
| JDK | Bộ công cụ và JVM | Khả năng compile, Java API, bytecode và môi trường thực thi |
| Maven/Gradle | Build tool | Cách resolve dependency, compile, test và đóng gói |
| Spring Cloud hoặc hệ mở rộng | Các dự án tích hợp bổ sung | Release train tương thích với dòng Spring Boot |

Spring Boot thường quản lý phiên bản Spring Framework thông qua dependency management. Người phát triển nên bắt đầu từ **một dòng Spring Boot được chọn**, để Boot quản lý các module Spring tương ứng, sau đó chọn JDK nằm trong phạm vi hỗ trợ của dòng Boot đó.

## 2. Spring Boot không phải Spring Framework

Hai tên thường đi cùng nhau nhưng chỉ hai sản phẩm khác nhau.

**Spring Framework** cung cấp những khả năng nền tảng:

- IoC container và dependency injection.
- Bean lifecycle.
- AOP và transaction abstraction.
- Spring MVC và WebFlux.
- Resource abstraction.
- Event publishing.
- Data binding và validation integration.
- Các abstraction hỗ trợ tích hợp hệ thống.

**Spring Boot** xây dựng trải nghiệm phát triển và vận hành ứng dụng dựa trên Spring Framework:

- Auto-configuration theo classpath và property.
- Starter dependencies để nhóm thư viện thường dùng.
- Dependency management thông qua BOM.
- Plugin Maven/Gradle để build executable JAR/WAR.
- Externalized configuration.
- Actuator và các tiện ích production-ready.
- Cơ chế chạy ứng dụng độc lập và tích hợp với container.

Ví dụ, `spring-context` thuộc Spring Framework. `spring-boot-autoconfigure` và `spring-boot-starter-web` thuộc hệ Spring Boot.

Khi khai báo:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

starter đưa vào một nhóm dependency phù hợp cho web application. Nó không có nghĩa Spring Framework được đóng gói thành một sản phẩm có cùng version number với Spring Boot.

### 2.1. Version number của Boot và Framework có thể khác

Ví dụ minh họa:

~~~text
Spring Boot       3.3.x
Spring Framework  6.1.x
JDK               17
~~~

Đây là ba dòng version khác nhau. Khi dùng dependency management của Spring Boot, phiên bản Spring Framework tương ứng được Boot quản lý.

Không nên suy luận rằng Boot 3.3 phải dùng Framework 3.3 hoặc JDK 3.3. Số phiên bản của ba thành phần có lịch phát hành và quy tắc riêng.

## 3. Spring Boot quản lý phiên bản Spring Framework bằng BOM

Spring Boot cung cấp một **BOM (Bill of Materials)** có tên `spring-boot-dependencies`. BOM khai báo các phiên bản dependency được khuyến nghị và kiểm thử cùng một dòng Spring Boot.

Các module Framework thường nằm trong tập dependency do BOM quản lý, ví dụ:

- `spring-core`
- `spring-beans`
- `spring-context`
- `spring-aop`
- `spring-expression`
- `spring-web`
- `spring-webmvc`
- `spring-tx`

Thay vì tự đặt version cho từng module, ứng dụng khai báo dependency và để BOM chọn phiên bản phù hợp.

~~~text
Spring Boot release
       |
       v
spring-boot-dependencies BOM
       |
       +-- Spring Framework modules
       +-- Jackson
       +-- Logging libraries
       +-- Hibernate / persistence libraries
       +-- Embedded server
       +-- Other managed dependencies
~~~

Lợi ích:

1. Các module thuộc cùng một hệ sinh thái được căn chỉnh phiên bản.
2. Giảm nguy cơ một module Spring mới kết hợp với module Spring cũ.
3. Dễ nâng cấp theo release line.
4. POM hoặc build file ngắn và dễ đọc hơn.
5. Có một điểm quản lý version trung tâm thay vì nhiều version rời rạc.

**BOM không phải một thư viện runtime duy nhất.** Nó là metadata dependency management để build tool chọn phiên bản cho các dependency được khai báo.

## 4. Vì sao không nên tự đặt version cho từng module Spring?

Giả sử một project dùng Spring Boot 3.x nhưng khai báo thủ công:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
    <version>5.3.30</version>
</dependency>
~~~

Trong khi các module khác do Boot quản lý có thể thuộc Spring Framework 6.x.

Kết quả có thể là một classpath chứa các module Framework không cùng dòng. Chúng có thể có API và kỳ vọng nội bộ khác nhau.

Các lỗi có thể gặp:

- `NoSuchMethodError` khi code gọi method không có trong version thực tế được load.
- `NoClassDefFoundError` khi class cần thiết không có trên runtime classpath.
- `ClassNotFoundException` khi class được yêu cầu không tồn tại.
- Lỗi khởi tạo bean do API hoặc behavior không tương thích.
- Lỗi chỉ xảy ra trên một nhánh code vì method liên quan chưa được gọi trong startup.

Không phải mọi trường hợp override đều chắc chắn thất bại, nhưng **tự trộn module Spring từ nhiều release line làm mất giả định tương thích mà Boot BOM cung cấp**.

Nguyên tắc thực hành:

- Dùng Boot BOM làm nguồn version chính.
- Không khai báo version riêng cho từng module Spring nếu không có lý do cụ thể.
- Nếu cần override vì một bản vá hoặc tương thích đặc biệt, phải hiểu dependency graph và kiểm tra toàn bộ nhóm module liên quan.
- Ghi lại lý do override để lần nâng cấp tiếp theo có thể xem xét lại.

## 5. JDK là một chiều tương thích riêng

JDK không phải dependency giống Spring Framework. Nó cung cấp:

- Compiler `javac`.
- JVM để thực thi bytecode.
- Java standard libraries.
- Các công cụ như `jar`, `javadoc`, `jlink`.
- Runtime modules và các tiện ích phát triển.

Spring Boot có yêu cầu Java tối thiểu và phạm vi Java được hỗ trợ theo từng release. Spring Framework cũng có yêu cầu Java riêng. Ứng dụng phải chọn JDK đáp ứng **cả Boot, Framework và các dependency khác**.

Ví dụ khái quát:

~~~text
Spring Boot 3.x
      |
      +-- Dựa trên Spring Framework 6.x
      |
      +-- Yêu cầu baseline Java 17
      |
      v
Ứng dụng cần JDK/runtime tương thích
~~~

Spring Boot 3.0 đánh dấu một thay đổi lớn: yêu cầu Java 17 trở lên và sử dụng Spring Framework 6.0. Điều này khiến ứng dụng đang ở Boot 2.x/Framework 5.x không thể chỉ đổi version Boot rồi tiếp tục build bằng Java 8 như trước.

Các minor/patch release sau đó có thể mở rộng phạm vi JDK được hỗ trợ, nhưng cần xem tài liệu của **đúng release line** thay vì áp dụng một con số chung cho mọi phiên bản.

## 6. Phân biệt JDK dùng để build và Java dùng để chạy ứng dụng

Một dự án có thể sử dụng nhiều Java version trong pipeline:

1. JDK chạy Maven hoặc Gradle.
2. JDK toolchain dùng để compile source.
3. Java release/target của bytecode.
4. JRE/JDK trên máy chạy ứng dụng.

Các phiên bản này có thể giống nhau, nhưng không bắt buộc luôn luôn giống.

Ví dụ:

~~~text
Build agent:
  JDK 21
      |
      v
Compiler toolchain:
  Java 17, --release 17
      |
      v
Artifact:
  Bytecode/API target Java 17
      |
      v
Production runtime:
  Java 17 hoặc JDK mới hơn tương thích
~~~

JDK 21 có thể compile source theo release 17 nếu build được cấu hình đúng. Artifact sau đó có thể chạy trên Java 17, miễn là:

- Code và dependency không sử dụng API chỉ có từ Java 18 trở lên.
- Bytecode được tạo tương thích với release 17.
- Các plugin/annotation processor không tạo ra bytecode hoặc yêu cầu runtime vượt quá mục tiêu.
- Spring Boot và toàn bộ dependency hỗ trợ Java 17.

Nếu compile thành bytecode Java 21 thì runtime Java 17 không thể chạy artifact đó.

### 6.1. Xem Java đang dùng

~~~bash
java -version
javac -version
~~~

Trên môi trường build Maven:

~~~bash
./mvnw -version
~~~

Với Gradle:

~~~bash
./gradlew --version
~~~

Những lệnh này giúp xác định JVM mà shell hoặc build tool đang sử dụng. Gradle có thể dùng daemon JVM khác với Java mặc định trong một terminal nếu toolchain hoặc cấu hình daemon được đặt riêng; cần kiểm tra cả cấu hình build.

## 7. Java source, target và release khác nhau thế nào?

Khi compile Java, cần phân biệt:

- **Source level:** cú pháp Java compiler chấp nhận.
- **Target bytecode:** định dạng class file được sinh.
- **Release:** giới hạn cú pháp, bytecode và Java platform API theo một Java release.

Tùy build tool và plugin, cấu hình cũ có thể dùng `source` và `target`, còn cấu hình hiện đại thường ưu tiên `--release` hoặc Java toolchain kết hợp release.

Ví dụ:

~~~bash
javac --release 17 -d out src/main/java/com/example/App.java
~~~

`--release 17` yêu cầu compiler biên dịch tương thích với Java 17, bao gồm API platform tương ứng, thay vì chỉ tạo bytecode có version thấp hơn nhưng vô tình gọi API mới.

Nếu chỉ đặt target bytecode thấp mà compile với API của JDK mới, ứng dụng có thể build thành công nhưng khi chạy trên JDK cũ lại gặp `NoSuchMethodError` hoặc `NoClassDefFoundError` đối với Java API.

## 8. Cấu hình Maven với Spring Boot parent

Một cách phổ biến là sử dụng `spring-boot-starter-parent`.

Ví dụ POM minh họa:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
</parent>

<groupId>com.example</groupId>
<artifactId>orders-api</artifactId>
<version>1.0.0</version>

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
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`3.3.5` là version minh họa để giải thích cấu hình, không phải khuyến nghị rằng mọi dự án mới nên chọn đúng version đó. Hãy chọn release line đang được dự án hỗ trợ và tương thích với JDK mục tiêu.

### 8.1. Parent làm gì?

Spring Boot parent cung cấp:

- Dependency management thông qua Boot BOM.
- Default plugin configuration.
- Cấu hình Maven compiler phù hợp.
- Default resource filtering và encoding theo cấu hình.
- Các plugin management convention giúp build nhất quán.

Khi dùng parent, nhiều dependency có thể không cần khai báo version riêng:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
</dependency>
~~~

Tuy nhiên, trong ứng dụng Boot, thường nên ưu tiên starter và abstraction phù hợp thay vì tự khai báo module nội bộ chỉ vì thấy nó có sẵn.

### 8.2. java.version không phải Spring Boot version

Trong ví dụ:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

Property này dùng để cấu hình Java version của quá trình compile theo cơ chế do parent/plugin hỗ trợ. Nó không đổi Spring Boot thành version 17 và cũng không tự cài JDK 17 trên máy build.

Máy build vẫn cần JDK tương thích và có thể cần cấu hình toolchain nếu muốn chọn compiler cụ thể.

## 9. Maven không dùng Spring Boot parent vẫn có thể dùng BOM

Một số dự án có parent POM riêng của tổ chức. Khi đó có thể import Boot dependency BOM trong `dependencyManagement`.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo dependency mà không cần version nếu BOM quản lý nó:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Khác biệt chính:

| Dùng Boot parent | Import Boot BOM |
|---|---|
| Có dependency management | Có dependency management |
| Kế thừa plugin management và nhiều cấu hình mặc định | Không tự kế thừa toàn bộ parent configuration |
| Thường ít cấu hình hơn | Phù hợp khi đã có parent POM riêng |
| Parent hierarchy chỉ có một parent trực tiếp | Có thể import nhiều BOM theo quy tắc Maven |

Nếu không dùng Boot parent, cần tự cấu hình plugin build/compile và Spring Boot Maven Plugin theo yêu cầu dự án.

## 10. Maven compiler plugin và Java toolchain

Với dự án Maven cần chỉ định release rõ ràng, có thể cấu hình compiler plugin:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Khi dùng Spring Boot parent, property `java.version` thường là cách cấu hình thuận tiện được parent hỗ trợ. Tránh khai báo nhiều property mâu thuẫn như `java.version=17` nhưng `maven.compiler.release=21` nếu không có chủ đích.

### 10.1. Maven Toolchains

Nếu máy chạy Maven bằng một JDK nhưng project cần compiler JDK khác, Maven Toolchains có thể chọn JDK toolchain.

~~~text
Maven process JVM
       |
       v
Maven Toolchains chọn compiler JDK
       |
       v
Compile theo release đã cấu hình
~~~

Cấu hình toolchain thường nằm trong Maven settings/toolchains của môi trường build và được compiler plugin hỗ trợ. Không nên hardcode đường dẫn JDK cục bộ của một lập trình viên vào POM dùng chung cho cả nhóm.

Điều quan trọng là pipeline phải xác nhận đúng JDK được chọn, không chỉ nhìn `java -version` của terminal.

## 11. Cấu hình Gradle với Spring Boot plugin

Ví dụ Groovy DSL:

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

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các version plugin trong ví dụ chỉ minh họa một cấu hình đồng bộ. Khi tạo dự án mới hoặc nâng cấp, hãy chọn Boot plugin và dependency-management plugin tương thích với Gradle Wrapper của project.

Khi Spring Boot Gradle plugin được kết hợp với plugin `io.spring.dependency-management`, Boot BOM được import để quản lý version dependency theo release Boot tương ứng.

### 11.1. Gradle không tự dùng JDK toolchain chỉ vì cài nhiều JDK

Cấu hình:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

yêu cầu Gradle chọn toolchain Java 17 cho những task hỗ trợ Java toolchain, chẳng hạn compile/test. Nó không tự bảo đảm Gradle daemon đang chạy bằng JVM 17.

Gradle daemon JVM là môi trường chạy build tool. Toolchain JVM là môi trường compiler/test được task lựa chọn. Chúng có thể khác nhau.

### 11.2. Gradle Wrapper cũng có yêu cầu JDK

Gradle Wrapper cố định Gradle distribution mà project sử dụng. Phiên bản Gradle đó có yêu cầu JVM tối thiểu riêng.

Một dự án có thể có:

- Spring Boot plugin version tương thích với Gradle Wrapper.
- Gradle Wrapper yêu cầu một JVM để chạy.
- Java toolchain chọn JDK khác để compile/test.
- Runtime image dùng JRE tương thích với bytecode và Spring Boot.

Do đó, khi build thất bại ngay lúc Gradle khởi chạy, chưa chắc nguyên nhân nằm ở Spring Framework; có thể Gradle Wrapper không chạy được trên JVM hiện tại.

## 12. Bảng tương thích cần đọc theo release line

Không có một quy tắc duy nhất kiểu “mọi Spring Boot đều chạy trên mọi JDK”. Mỗi release line có baseline và giới hạn hỗ trợ riêng.

Một số mốc lịch sử có ích:

| Dòng nền tảng | Spring Framework tương ứng | Mốc Java quan trọng |
|---|---|---|
| Spring Boot 2.7.x | Spring Framework 5.3.x | Dòng 2.7 có thể hỗ trợ Java 8 trở lên theo ma trận release |
| Spring Boot 3.0.x | Spring Framework 6.0.x | Yêu cầu Java 17 trở lên |
| Spring Boot 3.x tiếp theo | Framework 6.x theo BOM của từng release | Java 17 là baseline của dòng 3; phạm vi JDK được hỗ trợ thay đổi theo minor release |
| Các dòng Boot/Framework mới hơn | Cặp Framework do Boot release quản lý | Phải tra bảng system requirements của chính release |

Bảng trên giúp hiểu các mốc lớn, **không thay thế ma trận tương thích chính thức** cho từng patch/minor release. Khi chọn version cụ thể, kiểm tra đồng thời:

1. System Requirements của Spring Boot release.
2. System Requirements của Spring Framework tương ứng.
3. JDK support của dependency quan trọng.
4. Gradle/Maven version và plugin compatibility.
5. Container runtime image có JRE phù hợp.

### 12.1. Tại sao Boot 3 là một bước nâng cấp lớn?

Spring Boot 3 dựa trên Spring Framework 6 và yêu cầu Java 17 trở lên. Cùng với đó, hệ sinh thái chuyển từ nhiều API Java EE cũ sang Jakarta EE namespace.

Ví dụ:

~~~java
// Trước đây ở nhiều ứng dụng Boot 2.x
import javax.servlet.Filter;
~~~

~~~java
// Ứng dụng dựa trên Spring Framework 6 / Boot 3
import jakarta.servlet.Filter;
~~~

Đây là ví dụ servlet API. Không được thay mọi package bắt đầu bằng `javax` thành `jakarta` một cách máy móc: một số package `javax.*` thuộc Java SE vẫn giữ nguyên, chẳng hạn `javax.sql` hoặc `javax.crypto`.

Khi nâng Boot 2 lên Boot 3, cần kiểm tra:

- Java 17 trở lên trong build và runtime.
- Spring Framework 6.
- Jakarta namespace trong các API đã chuyển đổi.
- Dependency bên thứ ba có hỗ trợ Jakarta không.
- Servlet container, persistence provider và validation provider tương thích.
- Các cấu hình cũ đã bị loại bỏ hoặc thay đổi.

Đây là ví dụ rõ ràng cho thấy Boot, Framework và JDK cần được nâng cấp theo một kế hoạch đồng bộ.

## 13. Spring Framework version nên được quyết định bởi Boot BOM

Trong ứng dụng Boot thông thường, không nên tự chọn Spring Framework version độc lập nếu không có yêu cầu cụ thể.

Ví dụ, một project dùng:

~~~text
Spring Boot BOM: 3.3.5
Spring Framework: do BOM quản lý
~~~

Nếu tự override một module:

~~~xml
<properties>
    <spring-framework.version>...</spring-framework.version>
</properties>
~~~

hoặc khai báo version riêng cho `spring-context`, có thể tạo classpath không còn giống cấu hình đã được Boot kiểm thử.

Khi thật sự cần override:

1. Xác định lý do, chẳng hạn một bản vá bảo mật hoặc lỗi đã được xác nhận.
2. Kiểm tra version đồng bộ của toàn bộ Spring Framework modules.
3. Kiểm tra các module Boot và dependency tích hợp có tương thích.
4. Chạy test suite phù hợp.
5. Kiểm tra dependency tree để xác nhận version thực tế.
6. Ghi lại ngày và lý do cần bỏ override.

Không nên chỉ đổi `spring-core` mà để `spring-beans`, `spring-context` và `spring-expression` ở version khác.

## 14. Spring Boot BOM quản lý dependency nào?

BOM không chỉ quản lý Spring Framework. Nó còn quản lý nhiều dependency mà các starter sử dụng gián tiếp.

Ví dụ một ứng dụng web có thể có:

~~~text
spring-boot-starter-web
       |
       +-- spring-web
       +-- spring-webmvc
       +-- JSON libraries
       +-- embedded servlet container
       +-- logging
       +-- ...
~~~

Một ứng dụng data có thể thêm:

~~~text
spring-boot-starter-data-jpa
       |
       +-- Spring Data JPA
       +-- Hibernate
       +-- JDBC-related dependencies
       +-- transaction integration
       +-- ...
~~~

Nếu tự nâng một thư viện con mà không xem dependency graph, có thể tạo xung đột không dễ thấy ngay trong compile.

BOM giúp giảm vấn đề này bằng cách quản lý một tập version đã được kiểm thử cùng nhau.

### 14.1. BOM không bảo đảm mọi thư viện ngoài đều tương thích

Nếu project thêm một SDK bên thứ ba, một thư viện nội bộ hoặc một Spring extension không nằm trong Boot BOM, người phát triển vẫn phải kiểm tra compatibility riêng.

Spring Cloud là ví dụ quan trọng: các release train của Spring Cloud có ma trận tương thích với các dòng Spring Boot. Không nên chọn phiên bản Spring Cloud chỉ vì số version mới nhất hoặc vì Maven/Gradle tải được dependency.

## 15. Spring Cloud và các hệ mở rộng

Một ứng dụng có thể dùng thêm:

- Spring Cloud Config.
- Spring Cloud Gateway.
- Spring Cloud Circuit Breaker.
- Spring Cloud OpenFeign.
- Spring Cloud Stream.
- Các dự án Spring Integration khác.

Những project này có release train riêng. Release train được thiết kế để hoạt động với một hoặc một số dòng Spring Boot cụ thể.

Khi thêm Spring Cloud BOM, cần chọn release train phù hợp với Boot version của ứng dụng:

~~~text
Spring Boot release line
          |
          v
Spring Cloud compatibility matrix
          |
          v
Spring Cloud BOM/release train
          |
          v
Các Spring Cloud modules
~~~

Không nên chỉ thêm dependency `spring-cloud-starter-*` với version ngẫu nhiên. Nếu hai hệ thống quản lý version không cùng ma trận, ứng dụng có thể compile nhưng lỗi ở auto-configuration, API integration hoặc runtime.

## 16. Kiểm tra version thực tế bằng Maven

Một file POM có thể khai báo một version nhưng dependency graph cuối cùng lại chọn version khác do transitive dependency hoặc dependency management precedence.

Dùng Maven Wrapper:

~~~bash
./mvnw dependency:tree
~~~

Để tập trung vào Spring Framework:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework
~~~

Có thể xem dependency được resolve:

~~~bash
./mvnw help:effective-pom
~~~

`effective-pom` cho biết POM sau khi áp dụng parent, properties và dependency management. Đây là cách hữu ích khi project có nhiều parent/BOM.

Để xem môi trường Maven:

~~~bash
./mvnw -version
~~~

Để xác nhận một dependency cụ thể đến từ đâu, có thể lọc dependency tree theo group/artifact hoặc xem các đường dẫn transitive trong output.

**Đừng chỉ đọc version được ghi trong POM; hãy kiểm tra version Maven thực sự resolve.**

## 17. Kiểm tra version thực tế bằng Gradle

Gradle có các lệnh giúp xem dependency graph:

~~~bash
./gradlew dependencies
~~~

Xem cấu hình runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Xem lý do chọn version cho một module:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Có thể thay `spring-core` bằng dependency cần điều tra.

Kiểm tra toolchain:

~~~bash
./gradlew javaToolchains
~~~

Xem phiên bản Gradle và JVM daemon:

~~~bash
./gradlew --version
~~~

Các lệnh này giúp trả lời:

- Dependency đến từ module nào?
- Có nhiều version cùng được yêu cầu không?
- Version nào được chọn?
- Tại sao Gradle chọn version đó?
- JDK nào có sẵn để làm toolchain?

Khi gặp lỗi `NoSuchMethodError`, dependency insight thường hữu ích hơn việc đoán và nâng tất cả dependency lên version mới.

## 18. Dấu hiệu lỗi do lệch phiên bản

Một số lỗi thường gặp:

| Triệu chứng | Khả năng liên quan | Hướng điều tra |
|---|---|---|
| `UnsupportedClassVersionError` | Bytecode mới hơn JVM runtime | So sánh compile release và `java -version` trên server |
| `NoSuchMethodError` | Runtime load class version không có method mà caller mong đợi | Dependency tree, BOM và version override |
| `NoClassDefFoundError` | Class cần thiết không có hoặc khởi tạo class thất bại | Runtime classpath và root cause |
| `ClassNotFoundException` | Class không tìm thấy qua classloader | Dependency scope, module/classpath và namespace |
| Lỗi `javax.*` / `jakarta.*` | Thư viện thuộc thế hệ API khác nhau | Kiểm tra Boot 2/3 và dependency Jakarta |
| Gradle không khởi chạy | Gradle Wrapper/JVM không tương thích | Gradle version và daemon JDK |
| Maven compiler lỗi | Compiler plugin hoặc JDK không đáp ứng cấu hình | Maven version, toolchain, `release` |
| Auto-configuration không hoạt động | Dependency/version hoặc API condition không phù hợp | Condition report và dependency graph |
| Lỗi method/constructor khi startup | Module Spring hoặc thư viện liên quan không đồng bộ | BOM, effective POM, runtime classpath |

Một số exception có thể xuất phát từ bug ứng dụng hoặc dependency scope sai chứ không phải lệch version. Hãy xác nhận nguyên nhân từ class thực tế được load và dependency graph.

### 18.1. UnsupportedClassVersionError

Ví dụ:

~~~text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
~~~

Ý nghĩa: JVM đang chạy không hiểu bytecode của class được load.

Ví dụ project compile bằng Java 21 nhưng container runtime là Java 17. Cách xử lý:

- Nâng runtime lên JDK/JRE tương thích nếu đó là mục tiêu của ứng dụng.
- Hoặc compile theo Java release thấp hơn nếu toàn bộ code và dependency hỗ trợ.
- Kiểm tra Docker base image và deployment environment.
- Không chỉ sửa Java version trên máy developer rồi bỏ qua CI/server.

### 18.2. NoSuchMethodError

Ví dụ:

~~~text
java.lang.NoSuchMethodError:
'void org.springframework....someMethod(...)'
~~~

Đây thường là lỗi linkage: code được compile với một API nhưng runtime load class version không có method đó.

Hướng điều tra:

1. Xác định class chứa method.
2. Xem JAR thực tế cung cấp class đó.
3. Kiểm tra dependency tree.
4. Tìm dependency override hoặc transitive conflict.
5. Đưa các module về version set tương thích.
6. Rebuild và test lại artifact.

Không nên chữa bằng cách thêm JAR mới vào runtime một cách thủ công nếu chưa hiểu classpath đang chọn version nào.

## 19. Kiểm tra JDK của build agent và runtime container

Một pipeline thường có nhiều môi trường:

~~~text
Developer workstation
       |
       v
CI build agent
       |
       +-- Maven / Gradle JVM
       +-- Java compiler toolchain
       |
       v
Executable JAR
       |
       v
Container image / server
       |
       +-- Runtime JVM
       |
       v
Application
~~~

Có thể build thành công trên workstation nhưng container không chạy do runtime JRE thấp hơn bytecode. Cũng có thể Gradle daemon không chạy vì wrapper yêu cầu JDK cao hơn JDK được cài.

Một Dockerfile minh họa:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app

COPY target/orders-api.jar /app/app.jar

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ giả định artifact đã được compile tương thích với Java 17 và Spring Boot release được chọn hỗ trợ runtime này.

Nếu project compile target Java 21 thì phải chọn runtime phù hợp. Chọn image tag theo JDK trên máy lập trình viên mà không kiểm tra bytecode là một nguồn lỗi phổ biến.

## 20. Quy trình chọn bộ version mới cho dự án

Trước khi tạo project hoặc nâng cấp, nên làm theo trình tự:

### Bước 1 — Chọn Spring Boot release line

Xác định release line phù hợp với vòng đời hỗ trợ, yêu cầu tính năng và chính sách của tổ chức.

Không chọn chỉ vì version có số lớn nhất. Cần cân nhắc support window, dependency compatibility, security fixes và khả năng nâng cấp của ứng dụng.

### Bước 2 — Kiểm tra yêu cầu Java của Boot

Đọc system requirements của đúng release. Xác định Java tối thiểu và phạm vi JDK được hỗ trợ.

### Bước 3 — Để Boot quản lý Spring Framework

Dùng Boot parent hoặc Boot BOM. Tránh tự chọn Framework version độc lập nếu không có lý do.

### Bước 4 — Kiểm tra các hệ mở rộng

Nếu có Spring Cloud hoặc thư viện Spring tích hợp khác, chọn release train phù hợp với Boot.

### Bước 5 — Chọn build tool và wrapper

Kiểm tra Maven/Gradle version hỗ trợ JDK dùng để build và plugin Boot đã chọn.

### Bước 6 — Cố định compiler toolchain/release

Chọn Java API/bytecode target phù hợp với runtime production. Ghi cấu hình vào build file để toàn đội và CI dùng nhất quán.

### Bước 7 — Kiểm tra runtime image

Đảm bảo JRE/JDK trên container hoặc server nằm trong phạm vi được hỗ trợ và đủ để chạy bytecode cùng dependencies.

### Bước 8 — Xác nhận dependency graph

Chạy dependency tree/insight để tìm version override và dependency xung đột.

### Bước 9 — Chạy test và đóng gói artifact

Build, unit/integration tests và smoke test artifact trong môi trường tương tự deployment.

## 21. Nâng cấp patch, minor và major

Các loại nâng cấp có mức độ ảnh hưởng khác nhau.

| Loại nâng cấp | Ví dụ khái quát | Cách tiếp cận |
|---|---|---|
| Patch | 3.3.4 lên 3.3.5 | Thường tập trung bug/security fixes; vẫn cần test |
| Minor | 3.2.x lên 3.3.x | Có thể có tính năng mới, thay đổi behavior hoặc deprecation |
| Major | 2.x lên 3.x | Có thể có baseline Java/API/namespace và breaking changes |

Không nên giả định patch update hoàn toàn không có rủi ro, hoặc minor update không thể thay đổi behavior. Hãy đọc release notes và migration guidance của đúng phiên bản.

### 21.1. Nâng cấp Spring Boot thường kéo theo Framework

Nếu nâng Boot BOM, Spring Framework version do BOM quản lý có thể thay đổi theo.

Đây là lý do nên nâng theo Boot release line thay vì chỉ cập nhật một module Framework. Một bản Boot mới được xây dựng và kiểm thử với một bộ dependency nhất định; giữ một số module Spring cũ có thể làm mất tính nhất quán.

### 21.2. Major upgrade cần kiểm tra code và dependency ngoài

Khi chuyển từ Boot 2 lên Boot 3, cần quan tâm:

- Java 17 baseline.
- Spring Framework 6.
- Jakarta EE namespace.
- Servlet container và persistence provider.
- Validation, security, serialization và các integration library.
- Property hoặc API đã deprecated/removed.
- Plugin Maven/Gradle và build scripts.

Không nên coi việc sửa compile errors là hoàn tất. Một số thay đổi là runtime behavior hoặc configuration behavior, cần integration test và smoke test.

## 22. Dependency override: khi nào có thể chấp nhận?

Có thể có tình huống cần override một dependency do:

- Bản vá bảo mật chưa được Boot BOM của release line cung cấp.
- Một bug đã được xác nhận và có workaround version cụ thể.
- Một dependency bên thứ ba yêu cầu version tối thiểu.
- Tổ chức có chính sách bắt buộc dùng một version đã kiểm định.

Khi override, nên:

1. Xác định module bị override và các module liên quan.
2. Kiểm tra compatibility matrix của framework/library.
3. Xem dependency tree để xác nhận version cuối.
4. Ghi lý do và nguồn quyết định.
5. Thêm test cho chức năng bị ảnh hưởng.
6. Đặt thời điểm xem xét bỏ override khi Boot release mới đã quản lý version phù hợp.

Không nên override cả nhóm dependency chỉ để làm mất một cảnh báo scanner nếu chưa biết bản vá đó có tương thích với release line hiện tại không.

## 23. Maven dependency management precedence

Trong Maven, version cuối được chọn chịu ảnh hưởng của dependency management, parent POM, imported BOM và khai báo trực tiếp.

Khi có nhiều BOM, thứ tự import và các rule precedence có thể ảnh hưởng version được chọn. Một dependency khai báo version trực tiếp cũng có thể khiến kết quả khác với version do Boot BOM quản lý.

Vì vậy, nếu POM có:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>...</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

thì cần hiểu vì sao version này được đặt và nó có ghi đè version do Boot BOM cung cấp không.

Lệnh:

~~~bash
./mvnw help:effective-pom
~~~

giúp nhìn cấu hình sau khi Maven hợp nhất parent và dependency management. Lệnh:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework
~~~

giúp nhìn dependency thực tế được resolve.

**POM nguồn không phải lúc nào cũng kể đầy đủ câu chuyện về classpath cuối cùng.**

## 24. Gradle version conflict và dependency constraints

Gradle resolve dependency graph theo các rule của nó. Khi nhiều dependency yêu cầu các version khác nhau, Gradle chọn version theo resolution strategy và metadata/constraints của cấu hình.

Ví dụ, một dependency bắc cầu yêu cầu `spring-core` khác version do Boot BOM quản lý. Có thể dùng:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

để xem:

- Version nào được chọn.
- Những dependency nào yêu cầu module đó.
- Constraint hoặc platform nào tham gia.
- Vì sao một version được chọn.

Khi dùng Gradle platform/BOM, nên giữ các dependency trong cùng hệ sinh thái theo platform. Tránh thêm resolution rule toàn cục mà không hiểu tác động lên các module khác.

## 25. Spring Boot plugin version và starter version

Một nhầm lẫn khác là cho rằng Spring Boot Gradle plugin version và starter version phải được ghi ở mọi dependency.

Ví dụ:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.5'
}
~~~

Khi kết hợp dependency management phù hợp, có thể khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Không cần thêm version cho từng starter nếu BOM đang quản lý.

Trong Maven với Boot parent/BOM cũng tương tự.

**Boot plugin version** điều khiển build integration. **Starter dependency version** được dependency management chọn. Hai khái niệm liên quan nhưng không phải một trường duy nhất.

## 26. Spring Framework modules cần đồng bộ

Spring Framework được chia thành nhiều module. Một ứng dụng có thể kéo các module qua starter hoặc trực tiếp.

Ví dụ:

~~~text
spring-core
spring-jcl
spring-beans
spring-context
spring-aop
spring-expression
spring-tx
spring-web
spring-webmvc
~~~

Các module này có dependency và quan hệ nội bộ. Không nên nâng một module riêng mà không xác định yêu cầu của các module còn lại.

Một cách kiểm tra nhanh:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework
~~~

hoặc:

~~~bash
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
~~~

Mục tiêu là xác nhận các module Framework thực tế được resolve theo bộ version nhất quán mà Boot release quản lý.

## 27. Kiểm tra trong CI để tránh “works on my machine”

Một cấu hình version chỉ hữu ích nếu CI sử dụng nó thật.

Nên cố định:

- Maven Wrapper hoặc Gradle Wrapper trong repository.
- JDK/toolchain cho compile và test.
- Java release target.
- Spring Boot plugin/parent version.
- Dependency BOM.
- Container runtime image.
- Các plugin build quan trọng.

Một pipeline có thể thực hiện:

~~~text
Checkout source
      |
      v
Select supported build JDK
      |
      v
Run Maven/Gradle Wrapper
      |
      v
Resolve dependencies
      |
      v
Compile with configured release
      |
      v
Run unit/integration tests
      |
      v
Package executable artifact
      |
      v
Run artifact smoke test
      |
      v
Build runtime image with compatible JRE
~~~

Nếu developer dùng JDK 21 nhưng CI dùng JDK 17, build có thể thất bại do compiler/plugin hoặc API khác nhau. Ngược lại, CI build bằng JDK 21 và target 17 nhưng container runtime dùng JDK 11 vẫn không tương thích với ứng dụng Boot 3.

## 28. Lựa chọn Java version theo vòng đời triển khai

JDK mục tiêu không chỉ là lựa chọn cá nhân. Nó ảnh hưởng:

- Hình ảnh container.
- Hệ điều hành server.
- Runtime policy của tổ chức.
- Thư viện bên thứ ba.
- Performance và garbage collector.
- Security update cadence.
- Công cụ giám sát và APM agent.
- Khả năng vận hành trong môi trường cloud.

Nếu tổ chức đang chạy Java 17, chọn một dependency yêu cầu Java 21 có thể làm ứng dụng không deploy được dù compile trên máy lập trình viên thành công.

Trước khi nâng Java:

1. Kiểm tra Boot và Framework hỗ trợ JDK mục tiêu.
2. Kiểm tra build plugins và annotation processors.
3. Kiểm tra toàn bộ dependency.
4. Kiểm tra runtime image và APM agent.
5. Chạy integration test.
6. Kiểm tra startup, memory, TLS và các tính năng vận hành trong staging.

## 29. Ví dụ: một cấu hình lệch version

Giả sử project có:

~~~text
Spring Boot BOM: 3.3.x
Spring Framework: một module bị ép về 5.3.x
Build JDK: 21
Java release target: 17
Runtime JRE: 17
~~~

Phần Java có thể hợp lệ: build bằng JDK 21 nhưng tạo bytecode/API tương thích Java 17 nếu cấu hình release đúng và mọi dependency cũng hỗ trợ.

Tuy nhiên, Spring Framework module bị ép về 5.3.x có thể không tương thích với các module 6.x do Boot BOM quản lý. Khi ứng dụng gọi API mới hoặc Framework modules tương tác, lỗi linkage/runtime có thể xuất hiện.

Cách khắc phục:

- Gỡ override không cần thiết.
- Để Boot BOM quản lý đồng bộ Framework modules.
- Kiểm tra effective POM/dependency insight.
- Build lại và test với đúng JDK/runtime mục tiêu.

Ví dụ này cho thấy **JDK 21/17 có thể là một lựa chọn hợp lệ, trong khi Framework version vẫn sai**. Ba chiều tương thích cần được xem xét độc lập rồi kết hợp.

## 30. Ví dụ: Boot 2 lên Boot 3

Một ứng dụng cũ:

~~~text
Spring Boot 2.7.x
Spring Framework 5.3.x
Java 8 hoặc Java 11 (tùy cấu hình)
javax.servlet / Java EE namespace
~~~

Định hướng nâng cấp:

~~~text
Spring Boot 3.x
Spring Framework 6.x
Java 17+
jakarta.servlet / Jakarta EE namespace
~~~

Đây không phải thay version đơn giản. Cần kiểm tra:

- Build agent và runtime đã có Java 17 chưa?
- Dependency nào còn dùng `javax.servlet`?
- Servlet container có hỗ trợ Jakarta namespace không?
- Validation và persistence provider có tương thích không?
- Security configuration có thay đổi API không?
- Third-party starter có release hỗ trợ Boot 3 không?
- Test có bao phủ các integration quan trọng không?

Có thể nâng qua một bước trung gian theo migration guidance để tách việc xử lý deprecation khỏi thay đổi major, tùy trạng thái project. Mục tiêu là giảm số thay đổi lớn xảy ra đồng thời và giúp truy nguyên lỗi dễ hơn.

## 31. Một checklist đọc compatibility matrix

Khi xem bảng tương thích của một release, không chỉ tìm từ “Java”. Hãy kiểm tra:

| Mục | Câu hỏi |
|---|---|
| Spring Boot version | Đúng patch/minor line mà dự án muốn dùng chưa? |
| Spring Framework version | Boot BOM quản lý module Framework nào? |
| Java baseline | JDK tối thiểu để build/run là bao nhiêu? |
| Java support range | Những JDK nào được release đó hỗ trợ? |
| Maven/Gradle | Build tool và wrapper version nào được hỗ trợ? |
| Servlet container | Embedded/external container có tương thích không? |
| Spring Cloud | Release train nào phù hợp? |
| Persistence provider | Hibernate/JPA version có phù hợp không? |
| Security | Spring Security và API namespace có tương thích không? |
| Third-party starters | Có support Boot line này không? |
| Runtime image | JRE trong image có phù hợp bytecode và Boot không? |

Compatibility matrix phải gắn với release cụ thể. Không nên lấy một bài blog cũ về Boot 2 rồi dùng làm cơ sở chọn JDK cho Boot 3 hoặc một dòng mới hơn.

## 32. Nguyên tắc quản lý version trong team

Một nhóm phát triển nên thống nhất:

1. Một nguồn version trung tâm cho Spring Boot.
2. Spring Framework được quản lý bởi Boot BOM.
3. Các BOM khác như Spring Cloud được chọn theo compatibility matrix.
4. Java toolchain/release được ghi trong build file.
5. Maven/Gradle Wrapper được commit cùng repository.
6. Runtime image có tag JDK/JRE rõ ràng.
7. Version override phải có lý do và người chịu trách nhiệm.
8. CI kiểm tra dependency graph và test artifact.
9. Nâng cấp có changelog và migration notes.
10. Không dùng dependency version động không kiểm soát trong production build.

Một bảng trong README nội bộ có thể ghi:

~~~text
Spring Boot:        3.3.5
Spring Framework:   managed by Spring Boot BOM
Build JDK:          21
Java release:       17
Runtime JRE:        17
Gradle Wrapper:     version pinned in gradle-wrapper.properties
Spring Cloud:       compatible release train selected
~~~

Các giá trị chỉ là ví dụ. Điều quan trọng là ghi rõ **build JDK khác Java release target nếu có**, để người khác không nhầm môi trường compiler với runtime requirement.

## 33. Những hiểu lầm thường gặp

**“Spring Boot 3 thì Spring Framework cũng version 3.”** Sai. Boot 3.x dựa trên Framework 6.x.

**“JDK 21 cài trên máy nghĩa ứng dụng chắc chắn chạy được Java 21.”** Không. Build có thể target Java 17, và runtime production có thể khác build machine.

**“Chỉ cần đổi `java.version` là tự cài JDK tương ứng.”** Sai. Property chỉ cấu hình build; máy/CI vẫn phải có JDK phù hợp hoặc toolchain có thể tải/chọn JDK theo cấu hình.

**“BOM là một dependency runtime.”** Sai. BOM là metadata quản lý version, không phải một thư viện được thêm vào classpath như starter.

**“Starter tự chọn mọi version bên thứ ba.”** Chỉ các dependency được BOM quản lý mới nhận version từ BOM; dependency ngoài cần kiểm tra riêng.

**“Có thể nâng riêng spring-core để nhận bản vá.”** Có thể tạo Framework modules lệch version; cần xem toàn bộ nhóm và dependency graph.

**“Compile thành công nghĩa runtime tương thích.”** Sai. Bytecode, API và classpath có thể khác runtime.

**“sourceCompatibility hoặc target thấp bảo đảm dùng được API cũ.”** Không nhất thiết. Dùng `--release` hoặc cấu hình tương ứng để kiểm soát cả Java API.

**“Boot parent và Boot BOM giống nhau hoàn toàn.”** Không. BOM quản lý dependency versions; parent còn cung cấp nhiều cấu hình Maven/plugin management.

**“@Primary hoặc đổi starter sửa được lỗi linkage.”** Không. Lỗi version cần kiểm tra classpath và version thực tế.

**“Nâng Java là nâng Spring Boot.”** Không. JDK và Spring Boot là các thành phần version độc lập nhưng phải tương thích.

**“Build trên JDK mới thì container có thể dùng JRE cũ.”** Chỉ khi bytecode và mọi API/dependency thực sự tương thích với JRE cũ, đồng thời release Boot hỗ trợ runtime đó.

## 34. Bài tập thực hành

### Bài tập 1 — Nhận diện ba phiên bản

Cho cấu hình:

~~~text
Spring Boot 3.3.5
Spring Framework 6.1.x
JDK 17
~~~

Hãy giải thích:

- Boot và Framework khác vai trò như thế nào?
- Vì sao số version không giống nhau?
- Ai quản lý version Framework?
- JDK cung cấp những gì cho quá trình build và runtime?

### Bài tập 2 — Tìm dependency bị override

Giả sử POM dùng Boot parent nhưng khai báo version riêng cho `spring-context`.

Hãy chạy:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dincludes=org.springframework
~~~

Xác định version cuối và đường dẫn dependency. Giải thích rủi ro khi `spring-context` không cùng release với các module Framework khác.

### Bài tập 3 — Phân biệt build JDK và runtime JDK

Giả sử:

~~~text
Build JDK: 21
Java release: 17
Runtime: 17
~~~

Trả lời khi nào cấu hình này có thể chạy được, điều kiện nào có thể làm nó thất bại và tại sao chỉ nhìn `java -version` trên máy developer chưa đủ.

### Bài tập 4 — Chẩn đoán UnsupportedClassVersionError

Một artifact chạy tốt trên máy lập trình viên nhưng container báo `UnsupportedClassVersionError`.

Hãy xác định:

- Compiler JDK và `--release` đã dùng.
- Runtime Java trong container.
- Base image của Dockerfile.
- Dependency có bytecode yêu cầu Java cao hơn không.

Đề xuất thay đổi để hai môi trường tương thích.

### Bài tập 5 — Lập kế hoạch nâng Boot 2 lên Boot 3

Liệt kê các nhóm thay đổi:

- Java 17 baseline.
- Framework 6.
- Jakarta namespace.
- Third-party dependencies.
- Servlet container.
- Spring Security, validation và persistence.
- Maven/Gradle wrapper và plugins.
- Runtime image.
- Integration test.

Mục tiêu là tạo một kế hoạch có thể chia thành các bước review được, không chỉ sửa version trong POM.

## Kết luận

Spring Boot, Spring Framework và JDK là ba thành phần có quan hệ chặt chẽ nhưng giữ những trách nhiệm khác nhau.

- **Spring Boot** chọn và tích hợp một bộ dependency, trong đó có phiên bản Spring Framework tương thích.
- **Spring Framework** cung cấp container, AOP, transaction, web và các API nền tảng.
- **JDK** quyết định compiler, Java API, bytecode và JVM dùng để chạy ứng dụng.

Trong dự án Spring Boot thông thường, hãy để **Boot parent/BOM quản lý version Framework**, chọn JDK theo system requirements của release Boot, cố định Java toolchain/release trong build và xác nhận runtime container tương thích. Khi nâng cấp, kiểm tra thêm Maven/Gradle, Spring Cloud và các thư viện bên thứ ba.

Nếu gặp lỗi, hãy xem version thực tế trong dependency tree, JVM của build/runtime và bytecode target. **Build thành công chỉ chứng minh một giai đoạn; một bộ version đúng phải tương thích từ compiler đến runtime và toàn bộ dependency graph.**
