# Vai trò và phạm vi quản lý phiên bản của spring-boot-dependencies

Một ứng dụng Spring Boot thường sử dụng đồng thời Spring Framework, Jackson, thư viện logging, servlet container, validation, JDBC, testing và nhiều thư viện bên thứ ba. Chọn phiên bản của từng JAR độc lập có thể khiến chúng không tương thích dù mọi dependency đều tải xuống thành công. **`org.springframework.boot:spring-boot-dependencies`** giải quyết phần lớn bài toán đó bằng một tập **phiên bản dependency được Spring Boot quản lý theo từng release**.

Đây là một **BOM (Bill of Materials)**, được phát hành dưới dạng Maven POM. Với Spring Boot 3.3.13, tọa độ tương ứng là:

```text
groupId    = org.springframework.boot
artifactId = spring-boot-dependencies
version    = 3.3.13
type       = pom
```

Phiên bản `3.3.13` chỉ là **mốc cố định cho các ví dụ có thể tái hiện trong bài**; khi dùng thực tế, lựa chọn release Spring Boot phù hợp với yêu cầu hỗ trợ và cập nhật bảo mật của dự án. Quan trọng là **phiên bản BOM phải được chọn có chủ đích** và các dependency cùng hệ sinh thái cần được kiểm tra với tập phiên bản mà release đó hỗ trợ.

## 1. BOM là gì, và nó khác một dependency thông thường ra sao?

BOM là tài liệu mô tả **những phiên bản nên dùng khi một dependency xuất hiện trong đồ thị phụ thuộc**. Trong Maven, nội dung quản lý được đưa vào `<dependencyManagement>`; nó có thể tham chiếu đến những BOM khác để quản lý đồng bộ cả một họ thư viện.

Hình dung hai trường hợp:

```text
KHÔNG QUẢN LÝ TẬP TRUNG
Application
 ├─ Spring Boot starter: phiên bản do người viết chọn
 ├─ Jackson: phiên bản do người viết chọn
 ├─ Logging: phiên bản do người viết chọn
 └─ Test libraries: phiên bản do người viết chọn
  -> Dễ lệch các nhóm thư viện và tốn công kiểm tra tương thích

CÓ SPRING BOOT BOM
Application
 ├─ BOM Spring Boot 3.3.13: danh mục phiên bản được quản lý
 ├─ spring-boot-starter-web  -> tra phiên bản từ BOM
 ├─ jackson-databind        -> tra phiên bản từ BOM
 ├─ spring-boot-starter-test -> tra phiên bản từ BOM
 └─ các thư viện khác có mục trong BOM -> tra phiên bản từ BOM
  -> Có một baseline phiên bản nhất quán để kiểm thử
```

Phải phân biệt rõ:

- **`<dependencies>` hoặc `implementation`**: khai báo thư viện ứng dụng thực sự cần.
- **`<dependencyManagement>` hoặc Gradle platform**: cung cấp quy tắc chọn phiên bản cho dependency *nếu nó được sử dụng*.
- **`spring-boot-dependencies`**: artifact kiểu POM chứa metadata quản lý phiên bản. Nó **không phải executable JAR**, không chứa lớp Java ứng dụng và không được chạy bằng `java -jar`.
- **Spring Boot starter**: dependency tập hợp những thư viện phục vụ một năng lực (web, data, security, test...). Starter *thường* kéo theo transitive dependencies. BOM chỉ chọn các phiên bản phù hợp.

Ví dụ, chỉ import BOM nhưng không khai báo `spring-boot-starter-web` sẽ **không** tự thêm web server hay endpoint. Ngược lại, khi khai báo starter, BOM giúp chọn phiên bản starter và những thành phần nằm trong phạm vi quản lý.

## 2. Phạm vi quản lý của spring-boot-dependencies

Các nhóm điển hình trong hệ sinh thái Spring Boot 3.3 gồm:

| Nhóm | Ví dụ thành phần có thể được BOM quản lý | Ý nghĩa |
| --- | --- | --- |
| Spring Boot | `spring-boot`, `spring-boot-autoconfigure`, các `spring-boot-starter-*` | Giữ các artifact Boot nhất quán với release được chọn |
| Spring Framework và Spring projects | `spring-core`, `spring-web`, Spring Data, Spring Security... | Căn chỉnh các thế hệ framework và dự án liên quan |
| Web/runtime | Tomcat, Jackson, Jakarta APIs, validation | Chọn baseline cho xử lý HTTP, JSON, API |
| Persistence | Hibernate, HikariCP, JDBC drivers được liệt kê | Hạn chế lệch phiên bản persistence stack |
| Logging/observability | SLF4J, Logback, Micrometer... | Giữ kết hợp logging/metrics phù hợp |
| Testing | JUnit, Mockito, AssertJ, Testcontainers... | Căn chỉnh thư viện test được quản lý |

**Danh sách và phiên bản thực tế phụ thuộc vào release BOM.** Không suy luận rằng Spring Boot quản lý *mọi* artifact thuộc một group hoặc mọi thư viện trong hệ sinh thái Java. Để biết một tọa độ cụ thể có được quản lý hay không, xem **Dependency Versions** tương ứng với release đó và kiểm tra dependency graph/effective model của chính dự án.

BOM của Spring Boot còn có thể **nhập BOM chuyên ngành** (ví dụ tập thư viện Jackson hoặc các Spring projects) để điều phối cùng một release train. Dù đó là cơ chế nội bộ, người sử dụng chỉ cần tiêu thụ `spring-boot-dependencies` đúng cách và xác minh phiên bản được giải quyết.

### BOM có quản lý những gì khác ngoài version?

Trong Maven, `dependencyManagement` có thể chứa một số thuộc tính quản lý khác của dependency, nhưng giá trị chính được Spring Boot cung cấp là **tập version** cho các artifact được liệt kê. Không nên hiểu BOM là một chính sách toàn năng quản lý đường đi runtime, lỗi bảo mật, thiết lập ứng dụng hoặc quá trình triển khai.

| BOM có tác động | BOM không tự làm |
| --- | --- |
| Cung cấp version cho dependency đã khai báo nhưng không chỉ định version | Tự thêm dependency không có trong `<dependencies>` |
| Tham gia chọn version của dependency bắc cầu khi quy tắc build áp dụng | Bảo đảm mọi transitive dependency đều cùng phiên bản trong mọi tình huống override |
| Căn chỉnh các thư viện mà Spring Boot release được thiết kế và kiểm thử cùng | Quản lý phiên bản JDK, Maven, Gradle Wrapper, Docker base image |
| Cho phép bỏ version trên các dependency nằm trong danh mục quản lý | Tự cấu hình Maven build plugins, Java compiler, test execution, đóng gói và deploy |
| Cung cấp baseline để cập nhật theo phiên bản Spring Boot | Tự kiểm tra CVE, license, compatibility với thư viện nằm ngoài BOM |

**Ranh giới quan trọng:** Plugin phục vụ *quy trình build* và dependency phục vụ *mã ứng dụng* là hai nhóm khác nhau. Việc import BOM vào `<dependencyManagement>` **không nhập `<pluginManagement>`** cho Maven. `spring-boot-starter-parent` mang đến thêm các build defaults; đó là một lựa chọn khác với BOM import thuần túy.

## 3. Maven giải quyết phiên bản từ BOM như thế nào?

Trong Maven, một dependency trực tiếp thường có tọa độ `groupId:artifactId:version`. Khi một `groupId:artifactId` được quản lý trong effective POM, bạn có thể bỏ `<version>` ở khai báo dependency và Maven sẽ dùng phiên bản đã quản lý.

Cơ chế tổng quát:

```text
pom.xml:
  dependency: spring-boot-starter-web (không ghi version)
  dependencyManagement:
    import spring-boot-dependencies:3.3.13
                  |
                  v
           Effective POM
       ánh xạ dependency -> managed version
                  |
                  v
       Maven dependency resolution
                  |
                  v
    artifact + transitive dependencies được phân giải
```

Với Maven, khai báo BOM đúng chuẩn là `<type>pom</type>` và `<scope>import</scope>` **bên trong `<dependencyManagement>`**. `import` ở đây không phải runtime scope: Maven đưa các entry quản lý từ BOM vào effective model.

Đừng đặt BOM trong `<dependencies>` rồi mong nó đưa toàn bộ thư viện vào ứng dụng. Cũng đừng dùng `<scope>import</scope>` cho một dependency JAR thông thường.

Khi có khai báo phiên bản trực tiếp hoặc nhiều cơ chế quản lý, kết quả không còn đơn giản là “BOM luôn thắng”. Maven sẽ giải quyết theo effective POM và quy tắc dependency mediation; ở các mục sau ta sẽ xem cách kiểm tra.

## 4. Cách dùng Maven được khuyến nghị cho ứng dụng Boot thông thường: starter parent

Một ứng dụng mới có thể kế thừa `spring-boot-starter-parent`, từ đó nhận dependency management của `spring-boot-dependencies` **và** những cấu hình build hợp lý như encoding, Java compiler, plugin management và execution `repackage`.

Ví dụ `pom.xml` **hoàn chỉnh** cho Java 17, Maven 3.9.x, Spring Boot 3.3.13:

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
    <artifactId>bom-demo</artifactId>
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

Lưu ý:

1. Không cần ghi `<version>` cho `spring-boot-starter-web` và `spring-boot-starter-test` vì parent cung cấp dependency management.
2. `<scope>test</scope>` vẫn phải ghi cho starter test, bởi quản lý phiên bản **không thay thế việc chọn scope** thích hợp.
3. Plugin `spring-boot-maven-plugin` được **khai báo trong `<build><plugins>`** để dùng cấu hình `repackage` mà parent cung cấp. Nếu xóa plugin này, project vẫn có thể build JAR thông thường, nhưng không mặc nhiên có executable Boot JAR.
4. Việc kế thừa starter parent là một quyết định riêng; module đã có parent nội bộ có thể dùng phương án import BOM ở mục 6.

### Mã Java chạy được với POM trên

Tạo `src/main/java/dev/example/bomdemo/BomDemoApplication.java`:

```java
package dev.example.bomdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class BomDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BomDemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "BOM managed";
    }
}
```

Tạo `src/test/java/dev/example/bomdemo/BomDemoApplicationTest.java`:

```java
package dev.example.bomdemo;

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
class BomDemoApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void helloReturnsExpectedText() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("BOM managed"));
    }
}
```

Nếu dự án có Maven Wrapper dùng `./mvnw`, còn không dùng `mvn` từ Maven đã cài:

```bash
mvn -version
mvn clean verify
java -jar target/bom-demo-1.0.0.jar
```

Sau khi ứng dụng khởi động, mở terminal khác:

```bash
curl -s http://localhost:8080/hello
```

Body trả về chính xác:

```text
BOM managed
```

Điều chứng minh được từ ví dụ: **POM không ghi version cho starter** mà Maven vẫn resolve dependency, test và đóng gói được nhờ mô hình parent + dependency management. Phản hồi HTTP là bằng chứng ứng dụng hoạt động; để xem **phiên bản cụ thể** Maven đã chọn, phải dùng công cụ xem dependency graph/effective POM ở mục 9.

## 5. Parent, BOM import và plugin management: ba cơ chế thường bị trộn lẫn

| Cách sử dụng | Nhận quản lý dependency? | Nhận cấu hình plugin/build defaults? | Phù hợp |
| --- | --- | --- | --- |
| Maven kế thừa `spring-boot-starter-parent` | Có, qua `spring-boot-dependencies` | Có, theo parent | Ứng dụng Maven Boot thông thường |
| Maven import `spring-boot-dependencies` | Có | **Không** nhận plugin management bằng import | Dự án có parent riêng |
| Gradle + `io.spring.dependency-management` + Boot plugin | Có, Spring Boot plugin nhập BOM tương ứng tự động | Quản lý Gradle plugin/build theo plugins và cấu hình Gradle riêng | Dự án muốn tùy biến version theo property |
| Gradle `platform("...spring-boot-dependencies...")` | Có dưới dạng version constraints | Không tự thêm build plugins | Dự án ưu tiên cơ chế BOM native của Gradle |

**Parent POM và BOM không phải tên thay thế cho nhau.** Maven chỉ có một `<parent>` trực tiếp; nếu dự án đã có corporate parent, không thể thêm `spring-boot-starter-parent` làm parent thứ hai. Dùng BOM import để nhận quản lý dependency nhưng giữ parent hiện có.

**BOM import cũng khác với việc thêm Spring Boot Maven Plugin.** BOM không biết ứng dụng có cần goal `repackage`, Surefire, Failsafe hay Maven compiler release nào. Những thứ đó phải được cấu hình từ parent hoặc các plugin tương ứng.

## 6. Maven khi không dùng starter parent: import BOM tường minh

Đặt **đoạn cấu hình sau bên trong `<project>` của `pom.xml` hiện có**; đây là **fragment**, không phải một tệp POM độc lập:

```xml
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

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

`jackson-databind` được thêm trực tiếp **chỉ để minh họa việc bỏ version cho một thư viện được quản lý**; trong một ứng dụng web thông thường nó đã có thể được kéo vào qua starter và không cần khai báo thêm nếu không có lý do đặc biệt. Hai dependency trên lấy managed version từ BOM **khi version không bị override**.

Sau import, project vẫn phải quản lý các phần build thiết yếu mà parent của Boot thường cấu hình sẵn. Nếu tạo ứng dụng độc lập, ví dụ cần quyết định rõ:

- JDK/compiler: cấu hình Maven Compiler Plugin (ví dụ `<release>17</release>`) và phiên bản plugin phù hợp.
- Testing: cấu hình Maven Surefire/Failsafe tương thích với JUnit/integration test thực sự sử dụng.
- Executable JAR: khai báo `spring-boot-maven-plugin` cùng **version plugin** và execution goal `repackage` khi cần build `java -jar`.
- Resource filtering, encoding và các plugin khác: kế thừa từ parent nội bộ hoặc tự cấu hình.

Ví dụ một fragment plugin trong `<build><plugins>` để tạo executable JAR khi dùng BOM import (không dùng starter parent):

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.13</version>
    <executions>
        <execution>
            <id>repackage</id>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Goal `repackage` có phase mặc định `package`, nên execution trên sẽ chạy sau khi Maven đóng gói JAR gốc (với packaging `jar`). **Đây vẫn là fragment**: cần POM hoàn chỉnh với compiler/test configuration thích hợp để có một dự án Java 17 chạy thật.

Không thay `<scope>import</scope>` bằng `compile` hoặc `runtime`. BOM import phục vụ bước **xây mô hình dependency management**, không được mang vào runtime classpath.

## 7. Gradle: hai cách tiêu thụ BOM

Gradle không có `<parent>`/`<dependencyManagement>` giống Maven. Spring Boot 3.3 cho phép hai cách quản lý dependency được tài liệu chính thức hỗ trợ.

### Cách A — Spring Dependency Management Plugin

Ví dụ `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Khi cả **Boot Gradle Plugin** và **`io.spring.dependency-management`** được áp dụng, Boot plugin tự import BOM `spring-boot-dependencies` cùng phiên bản Boot plugin (ở đây là `3.3.13`). Nhờ vậy hai starter bỏ được version. Nếu chỉ áp dụng `org.springframework.boot` mà **không** dùng plugin dependency management hoặc native `platform`, đừng tự giả định mọi dependency đã được BOM quản lý.

Plugin dependency management còn cho phép sửa property version được BOM dùng; ví dụ property `slf4j.version` được mô tả trong tài liệu Spring Boot. Chỉ override khi có nguyên nhân rõ và kiểm chứng tương thích.

### Cách B — Native Gradle platform

Cũng dùng `build.gradle`, nhưng để Gradle trực tiếp nhập BOM làm dependency constraints:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'dev.example'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo `settings.gradle`:

```groovy
rootProject.name = 'bom-demo'
```

Dùng lại `BomDemoApplication.java` và `BomDemoApplicationTest.java` ở mục 4 trong đúng đường dẫn `src/main/java/...` và `src/test/java/...`. Với Gradle Wrapper đã được tạo/cài sẵn phù hợp với Boot plugin, lệnh:

```bash
./gradlew clean build
java -jar build/libs/bom-demo-1.0.0.jar
```

Trên Windows, chạy `gradlew.bat` thay cho `./gradlew`. Nếu dự án chưa có Wrapper, cần tạo Wrapper bằng một Gradle phù hợp; không mặc định rằng file `gradlew` luôn tồn tại.

**Sự khác nhau về hiệu lực constraint:** Với `platform(...)`, các version trong BOM thường là **khuyến nghị/constraints** có thể bị thay đổi bởi dependency graph, explicit constraints hoặc giải quyết xung đột của Gradle. Với `enforcedPlatform(...)`, các version bị ép mạnh hơn và có thể ảnh hưởng đến consumers của library; chỉ dùng khi thực sự muốn enforce và hiểu tác động. Spring Boot khuyến nghị cân nhắc Gradle native BOM support vì có thể cải thiện hiệu năng build, còn plugin dependency management hỗ trợ tùy biến theo property thuận tiện hơn.

Native platform chỉ tác động tới những configuration mà bạn gắn platform vào hoặc configuration kế thừa chúng; vì vậy ví dụ trên khai báo cả `implementation` và `testImplementation` để các đường test cũng có constraint rõ ràng. Với Gradle native platform, **không override được property bên trong Maven BOM như cách plugin dependency management làm**; thay bằng dependency constraints hoặc resolution strategy của Gradle.

## 8. Quy tắc ưu tiên: vì sao dependency thực tế có thể khác BOM?

BOM cung cấp baseline, nhưng build tool còn xử lý nhiều nguồn version khác. Bởi vậy không thể nhìn duy nhất version của BOM rồi khẳng định mọi artifact trong `target` hoặc `build/libs` đang dùng đúng phiên bản ấy.

**Trong Maven:**

1. Version ghi tường minh ở dependency trực tiếp thường được dùng cho dependency đó, dù BOM có entry quản lý khác.
2. Entry `<dependencyManagement>` được khai báo trực tiếp trong project có thể override entry tương ứng được import từ BOM.
3. Nếu nhập nhiều BOM có entry cùng tọa độ, thứ tự import và effective dependency management quyết định entry áp dụng; với Maven, **entry từ BOM được import trước thường có ưu tiên khi trùng tọa độ** (trừ entry quản lý trực tiếp/kế thừa có độ ưu tiên cao hơn). Kiểm tra effective POM để tránh giả định.
4. Với transitive dependencies, Maven áp dụng dependency management và dependency mediation (độ gần và thứ tự) theo cấu trúc graph. Khi có xung đột, xem graph thực tế thay vì suy ra từ POM trực tiếp.

**Trong Gradle:**

1. `platform` bổ sung dependency constraints. Gradle vẫn giải quyết xung đột theo rules, constraints và những version khác trên graph.
2. `enforcedPlatform` ép version mạnh hơn, có thể gây tác động ngoài mong muốn với library được xuất bản.
3. Với Spring Dependency Management Plugin, các BOM nhập nhiều lần được xử lý theo thứ tự plugin; theo tài liệu của plugin, **BOM nhập sau có thể ghi đè entry trùng của BOM trước**. Quy tắc này *khác* cách Maven BOM imports truyền thống.
4. BOM chỉ ràng buộc những configuration cần thiết. Test/runtime classpath có thể khác compile classpath nếu wiring khác.

**Ví dụ xung đột:** Ứng dụng chọn BOM Spring Boot 3.3.13, một thư viện nội bộ lại khai báo trực tiếp phiên bản Jackson khác. Nếu graph có cả hai yêu cầu, **kết quả cuối cùng tùy công cụ và các ràng buộc cụ thể**. Cách đúng là dùng `dependency:tree` (Maven) hoặc `dependencyInsight` (Gradle) để tìm chuỗi phụ thuộc và lý do chọn version.

## 9. Kiểm tra điều BOM thực sự đang quản lý

### Maven — xem effective model và dependency graph

Trong thư mục chứa `pom.xml`:

```bash
mvn help:effective-pom
mvn dependency:tree
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
```

- `help:effective-pom` cho thấy project model sau khi áp dụng parent, import, active profiles và quản lý version; tìm `<dependencyManagement>`, `<pluginManagement>` và version của entry đang quan tâm.
- `dependency:tree` cho thấy những dependency **đang tham gia graph thực tế**; rất hữu ích để tìm đường kéo Jackson/SLF4J/Hibernate vào ứng dụng. Nó không liệt kê mọi library có trong BOM nếu ứng dụng không dùng.
- Tham số `-Dincludes` giới hạn đầu ra theo artifact cần tìm; câu lệnh là ví dụ đọc graph, không thay cho gate test hoặc build.

### Gradle — xem resolved configuration và nguyên nhân chọn version

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-web --configuration runtimeClasspath
```

`dependencyInsight` giúp nhận biết module, đường đi transitive và lý do chọn phiên bản (constraint, conflict resolution...). Với Gradle dependency-management plugin, có thể kiểm tra tập managed versions bằng các report mà plugin hỗ trợ; nhưng resolved classpath vẫn là bằng chứng của artifact ứng dụng thực dùng.

**Câu hỏi cần trả lời bằng dữ liệu chứ không bằng suy đoán:** BOM nào đang có hiệu lực? Có nhiều BOM không? Entry target có được quản lý không? Dependency có explicit version không? Runtime/test classpath thực sự dùng phiên bản nào? Parent/profile/plugin constraints có ảnh hưởng không?

## 10. Override phiên bản được BOM quản lý: khi nào và bằng cách nào?

Spring Boot được phát hành sau khi kiểm thử với một tổ hợp thư viện cụ thể. **Override là quyết định cần cân nhắc**, thường vì bản vá khẩn cấp, lỗi đã biết, yêu cầu compatibility của dịch vụ khác hoặc xung đột khi tích hợp hệ thống. Không nên sửa bừa nhiều version chỉ để “lên mới nhất”.

| Ngữ cảnh | Cơ chế override | Lưu ý |
| --- | --- | --- |
| Maven với `spring-boot-starter-parent` | Property được BOM đặt tên (ví dụ `slf4j.version`) hoặc entry trực tiếp trong `dependencyManagement`/dependency | Property override thuận tiện do cơ chế inheritance; kiểm tra đúng tên property trong release đang dùng |
| Maven import BOM không dùng parent | Khai báo entry version mong muốn trực tiếp trong `dependencyManagement` **trước** BOM import; hoặc chỉ định version ở dependency trực tiếp nếu phù hợp | Property đặt ở project thường **không ghi đè** giá trị đã nội suy từ imported BOM |
| Gradle với `io.spring.dependency-management` | Override property managed version hoặc dependency management trực tiếp theo plugin | Cẩn trọng khi tạo/publish Maven POM vì metadata xuất bản có thể không phản ánh mọi property override |
| Gradle với native `platform` | Dependency constraints, resolution strategy hoặc rich versions của Gradle | Không sửa được Maven BOM property như với dependency-management plugin |

Đoạn Maven **minh họa cấu trúc override** (nằm trong `<project>`, không phải POM hoàn chỉnh):

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.3</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Con số `2.17.3` là phiên bản ví dụ để minh họa vị trí pin một artifact trong POM; nó **không có nghĩa bạn nên thay phiên bản BOM đang quản lý bằng con số này** hoặc rằng mọi phiên bản thuộc nhánh 2.17.x đều tương thích. Muốn đổi thật cần tra phiên bản gốc, mục tiêu vá lỗi, compatibility và chạy lại test.

Nếu cần override **cả nhóm thư viện Jackson** nhất quán, cân nhắc quản lý BOM của nhóm đó thay vì pin riêng một JAR rồi để các module anh em khác lệch version; vẫn phải bảo đảm release train Spring Boot hỗ trợ.

### Quy trình thay đổi an toàn

1. Ghi nhận **phiên bản đang resolved** và đường phụ thuộc bằng `dependency:tree`/`dependencyInsight`.
2. Kiểm tra release notes, compatibility và lý do cần đổi; ưu tiên nâng Spring Boot lên release đã cập nhật BOM khi phù hợp.
3. Chọn **một điểm quản lý nhất quán**: parent property, local dependencyManagement, một BOM bổ sung hoặc Gradle constraints.
4. Kiểm tra effective model/resolved classpaths sau sửa, gồm compile, test và runtime.
5. Chạy unit test, integration test và smoke test trên **artifact đã đóng gói**, nhất là khi đổi Spring Framework, Jackson, Tomcat, Hibernate, Spring Data hoặc logging stack.
6. Giữ lại evidence về lý do override và xem xét loại bỏ override khi BOM phiên bản mới đã bao gồm bản sửa.

## 11. Các tình huống giới hạn dễ gặp

### 11.1. Một library không nằm trong BOM

Nếu Maven dependency không có `<version>` và không có entry quản lý nào trong effective POM, Maven sẽ báo lỗi kiểu **dependency version is missing**. BOM không thể đoán version an toàn cho thư viện tùy ý.

**Cách giải quyết:** khai báo version rõ ràng hoặc thêm entry dependencyManagement/BOM thích hợp, rồi xác minh compatibility; không thêm một BOM ngẫu nhiên để triệt lỗi.

### 11.2. Hai BOM khác release train

Spring Boot BOM và BOM của framework/dịch vụ khác có thể cùng quản lý những module trùng nhau. Ví dụ Spring Cloud có release train/compatibility matrix riêng; không mặc định mọi phiên bản Spring Cloud đều tương thích với mọi phiên bản Spring Boot.

**Cách giải quyết:** chọn cặp release theo ma trận tương thích của dự án liên quan, xác định thứ tự BOM và kiểm tra resolved graph. Nếu chỉ import thêm BOM mà không kiểm tra precedence, bạn có thể thay đổi phiên bản ngoài dự kiến.

### 11.3. Dùng starter nhưng gắn version riêng

Ví dụ Maven đã dùng `spring-boot-starter-parent` 3.3.13 nhưng một dependency khai báo `spring-boot-starter-web` version khác. Đó là một cơ chế override rõ ràng; nó có thể làm lệch các artifact Spring Boot với phần còn lại.

**Cách giải quyết:** bỏ version tường minh của starter khi muốn tuân theo baseline BOM. Nâng phiên bản Spring Boot ở parent/BOM như một thay đổi có kiểm soát, không thay rời rạc từng starter.

### 11.4. Import BOM rồi tin rằng `java -jar` sẽ chạy

Một POM import BOM **không tự cấu hình goal `spring-boot:repackage`**. Nó chỉ mang dependency management.

**Cách giải quyết:** thêm Spring Boot Maven Plugin/execution phù hợp hoặc dùng starter parent; build bằng `mvn package`/`verify` rồi kiểm tra JAR và chạy thử.

### 11.5. BOM, JDK và plugin không cùng nguồn quản lý

BOM không chọn Gradle Wrapper, Maven version, JDK 17/21 hoặc phiên bản Maven Compiler Plugin. Nếu dùng Maven import không dùng parent, cấu hình compiler/plugin dễ bị thiếu.

**Cách giải quyết:** quản lý riêng toolchain và build plugins; ghi rõ JDK và build tool trong CI. Phân biệt quản lý **library versions** với quản lý **build tools**.

### 11.6. “Không ghi version” nghĩa là build reproducible?

Không. BOM cố định nhiều version nhưng build còn chịu ảnh hưởng của plugin versions, SNAPSHOT/dynamic dependencies, repository, metadata build, OS, JDK, profile và quy tắc caching/resolution.

**Cách giải quyết:** pin inputs quan trọng, dùng Wrapper, kiểm tra resolved graph, lưu checksum/digest và CI artifacts. BOM là một lớp trong chiến lược reproducible builds, không thay thế toàn bộ chiến lược.

## 12. Tóm lược phạm vi qua các quyết định thực tế

| Câu hỏi | Cách hiểu đúng |
| --- | --- |
| Tôi import `spring-boot-dependencies`, Maven có tự tải mọi starter không? | Không. Chỉ tải dependency được khai báo hoặc kéo theo qua dependency graph. |
| Một starter không ghi version thì ai chọn? | Effective dependency management (thường từ Spring Boot BOM) cung cấp version. |
| Một thư viện bên ngoài BOM có được tự chọn version không? | Không. Phải khai báo quản lý/version khác nếu build tool không có constraint phù hợp. |
| Import BOM có pin Maven/Gradle plugin không? | Không thông qua `import`; plugin/build có nguồn cấu hình riêng. |
| BOM khác `spring-boot-starter-parent` như thế nào? | BOM là quản lý dependency; parent kế thừa thêm build defaults/plugin management. |
| Gradle native platform có luôn ép chính xác mọi version? | Không. `platform` tham gia conflict resolution; `enforcedPlatform` mới có tác động ép mạnh hơn. |
| Tôi đổi version của một dependency, có còn theo baseline Boot không? | Đã có ngoại lệ. Cần kiểm chứng graph và compatibility. |
| Một version trong BOM được chọn nhưng app không dùng thư viện đó, artifact có trong JAR không? | Không chỉ vì nó được BOM quản lý. |
| `mvn verify` thành công là đủ chứng minh versions đúng? | Nó chỉ chạy các goal đã cấu hình. Vẫn cần xem resolved dependencies và kiểm thử theo yêu cầu. |
| Nâng Boot có thể đổi hàng loạt transitive versions không? | Có. Vì BOM release mới có thể quản lý một tập versions mới; cần review dependency diff và test. |

## 13. Bài tập kiểm tra hiểu bài

**Bài 1.** Một POM đã import `spring-boot-dependencies:3.3.13` và khai báo `spring-boot-starter-web` không có `<version>`. Ai chọn phiên bản starter?

*Đáp án:* Maven tra entry dependency management của effective POM; nếu không bị override, version do BOM 3.3.13 quản lý được áp dụng.

**Bài 2.** Chỉ import BOM, không thêm `spring-boot-starter-web`. Ứng dụng có tự có embedded Tomcat không?

*Đáp án:* Không. Import BOM không thêm dependency runtime. Tomcat chỉ xuất hiện nếu graph thực tế kéo nó vào.

**Bài 3.** Một Maven project có corporate parent nên không thể kế thừa `spring-boot-starter-parent` trực tiếp. Có thể vẫn dùng các managed dependencies của Boot không?

*Đáp án:* Có. Import `spring-boot-dependencies` vào `<dependencyManagement>` với `<type>pom</type>`, `<scope>import</scope>`; tự cấu hình build plugins và executable packaging khi cần.

**Bài 4.** Gradle project chỉ có `id 'org.springframework.boot' version '3.3.13'`, mọi dependency đều bỏ version. Điều này luôn đủ không?

*Đáp án:* Không. Phải có cơ chế dependency management hoạt động: apply `io.spring.dependency-management` cùng Boot plugin, hoặc import BOM bằng `platform(...)`/cơ chế tương đương.

**Bài 5.** Sau khi thêm một BOM khác, `jackson-databind` resolve thành version không ngờ tới. Nên kiểm tra gì?

*Đáp án:* Kiểm tra effective POM/import order (Maven) hoặc `dependencyInsight` và constraints (Gradle), explicit versions, transitive graph và compatibilities, rồi sửa tại nguồn version management.

**Bài 6.** Có người nói BOM quản lý luôn bản Docker base image và cấu hình Java runtime. Kết luận thế nào?

*Đáp án:* Sai. BOM quản lý metadata về dependency; JDK/runtime/container image là phần của build và deployment configuration riêng.

### Ghi nhớ

**`spring-boot-dependencies` giúp chọn một tập dependency versions nhất quán theo release Spring Boot.** Nó không tự thêm thư viện, không thay thế project POM/Gradle build, không nhập plugin management qua BOM import và không ngăn mọi override hay xung đột. Hãy chọn một cơ chế tiêu thụ BOM rõ ràng, kiểm tra **resolved graph thực tế**, và test mỗi khi thay đổi phiên bản.

### Tài liệu đối chiếu chính thức

- Spring Boot 3.3 — Maven Plugin, Using the Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot 3.3 — Gradle Plugin, Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Platforms and BOM imports: https://docs.gradle.org/current/userguide/platforms.html
- Spring Dependency Management Plugin reference: https://docs.spring.io/dependency-management-plugin/docs/current/reference/html/