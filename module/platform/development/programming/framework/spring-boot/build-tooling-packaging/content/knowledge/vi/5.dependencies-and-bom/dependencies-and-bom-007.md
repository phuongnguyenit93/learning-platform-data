# Phân biệt `spring-boot-starter-parent` với việc nhập BOM độc lập trong Maven

## 1. Bài toán: cùng một bộ phiên bản dependency, nhưng hai cách quản lý build khác nhau

Một dự án **Spring Boot dùng Maven** cần trả lời ít nhất hai câu hỏi tách biệt:

1. **Dependency dùng phiên bản nào?** Ví dụ `spring-boot-starter-web`, Jackson, Spring Framework, logging, thư viện test nên phối hợp theo phiên bản nào?
2. **Maven sẽ build bằng cấu hình nào?** Ví dụ compiler target Java bao nhiêu, plugin test/đóng gói dùng version gì, tài nguyên được filter ra sao và có chạy `spring-boot:repackage` khi `package` hay không?

Spring Boot cung cấp hai cơ chế thường gặp:

- **Kế thừa parent:** khai báo `org.springframework.boot:spring-boot-starter-parent` trong phần `<parent>` của `pom.xml`. Dự án nhận **dependency management và nhiều cấu hình build/plugin mặc định** từ chuỗi parent POM.
- **Nhập BOM độc lập:** import `org.springframework.boot:spring-boot-dependencies` vào `<dependencyManagement>` với `<type>pom</type>` và `<scope>import</scope>`. Dự án chủ yếu nhận **các quy tắc quản lý phiên bản dependency**, còn phần lớn cấu hình build/plugin phải được dự án hoặc parent riêng khai báo.

**Kết luận trọng tâm:** hai cách có thể cho ra **cùng phiên bản thư viện runtime**, nhưng không tự động có **cùng effective POM hoặc executable JAR**. Chọn cách nào tùy việc dự án có cần giữ một parent Maven khác hay muốn Spring Boot quản lý thêm các mặc định của build.

Tên gọi dễ gây nhầm: `spring-boot-starter-parent` **không phải một starter được thêm vào classpath ứng dụng**; nó là POM để **kế thừa**. `spring-boot-dependencies` là **BOM (Bill of Materials)**, dùng để điều phối phiên bản; import nó **không tự thêm bất kỳ starter nào** vào `<dependencies>`.

## 2. Ba khái niệm Maven cần phân biệt trước khi so sánh

### 2.1. `<parent>`: kế thừa cấu hình mô hình dự án

Maven cho một POM có **một** `<parent>` trực tiếp. Parent có thể cung cấp/inherit các phần được Maven hỗ trợ: `<properties>`, `<dependencyManagement>`, `<build><pluginManagement>`, khai báo plugin có tính kế thừa, profiles và các thiết lập build khác. Maven hợp nhất chúng thành **effective POM** với cấu hình của project hiện tại.

Trong Spring Boot, `spring-boot-starter-parent` kế thừa `spring-boot-dependencies` và bổ sung những giá trị mặc định thuận tiện cho một ứng dụng Spring Boot. Khi chọn nó, dự án không cần tự khai báo nhiều cấu hình thông thường.

### 2.2. `<dependencyManagement>`: quản lý phiên bản, không khai báo sử dụng

Một dependency nằm trong `<dependencyManagement>` có nghĩa Maven biết áp dụng version/scope/exclusion do mục đó quản lý **khi dependency tương ứng được đưa vào đồ thị**. Nó không tự tạo dependency trực tiếp cho ứng dụng.

Ví dụ:

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

Khối trên **chưa đủ** để chạy Spring Boot Web. Muốn dùng web starter, phải **khai báo sử dụng**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Không có `<version>` ở dependency vì phiên bản đã được quản lý. Nếu tự khai báo một `<version>` trực tiếp tại dependency, phiên bản trực tiếp đó sẽ được dùng cho khai báo ấy, có thể làm lệch bộ tương thích của Boot.

### 2.3. `<pluginManagement>` khác với `<dependencyManagement>`

- `<dependencyManagement>` quản lý **dependency của ứng dụng** như starter, Jackson, SLF4J, JUnit.
- `<build><pluginManagement>` quản lý **build plugin** như `maven-compiler-plugin`, `maven-surefire-plugin`, `maven-resources-plugin`, `spring-boot-maven-plugin`: version và cấu hình plugin có thể được cung cấp cho plugin thực sự được sử dụng.
- `<build><plugins>` khai báo **plugin tham gia build**. Một mục trong `pluginManagement` không mặc nhiên khiến mọi goal của plugin đó chạy.

Nhập `spring-boot-dependencies` bằng `scope=import` không nhập `<pluginManagement>` từ POM đó, cũng không nhập các execution/filters/profiles của `spring-boot-starter-parent`.

## 3. Bảng so sánh theo hành vi có thể kiểm chứng

| Tiêu chí | Kế thừa `spring-boot-starter-parent` | Import `spring-boot-dependencies` BOM |
| --- | --- | --- |
| Vị trí trong `pom.xml` | `<parent>`. | `<dependencyManagement><dependencies>` với `type=pom`, `scope=import`. |
| Có dùng parent riêng đồng thời? | **Một parent trực tiếp**: phải điều chỉnh chuỗi kế thừa hoặc chọn giải pháp khác. | **Có thể** giữ corporate parent và import BOM trong project. |
| Phiên bản các dependency do Boot quản lý | Có, kế thừa từ `spring-boot-dependencies`. | Có, do BOM import quản lý. |
| Starter tự xuất hiện trong classpath? | Không; vẫn phải khai báo trong `dependencies`. | Không; vẫn phải khai báo trong `dependencies`. |
| Quản lý version/config build plugin | Có nhiều mặc định hữu ích do parent cung cấp. | **Không tự có** cấu hình plugin của parent; cần khai báo ở project/parent khác. |
| Mặc định Java compiler, UTF-8, `-parameters` | Parent cung cấp mặc định theo phiên bản Boot. | Tự cấu hình hoặc sử dụng cấu hình của corporate parent. |
| Maven resource filtering cho Spring config | Parent có thiết lập phù hợp với các file `application*.properties/yml`. | Không tự nhận thiết lập đó. |
| `spring-boot:repackage` khi packaging | Parent đã có execution `repackage`; thông thường chỉ cần khai báo Spring Boot Maven plugin. | Cần khai báo Spring Boot plugin **và** bind goal `repackage` vào lifecycle. |
| Điều chỉnh dependency version bằng property của Boot | Có thể override property mà parent/BOM dùng, nếu property đó có trong phiên bản đã chọn. | Property cùng tên trong project **không tự sửa giá trị bên trong BOM đã import**; dùng quản lý dependency/BOM rõ ràng. |
| Quyền kiểm soát build | Ít cấu hình lặp, đi theo convention của Boot parent. | Chủ động hơn; đồng thời phải duy trì plugin/toolchain/packaging một cách tường minh. |
| Trường hợp điển hình | Ứng dụng mới, không có parent bắt buộc khác. | Doanh nghiệp có Maven parent riêng, multi-module đã có parent hoặc cần kiểm soát build theo chuẩn tổ chức. |

**Hai lớp cần luôn được kiểm tra độc lập:** dependency tree chỉ nói về thư viện; effective POM/plugin executions nói về **cách Maven chạy build**. Việc cả hai dự án dùng đúng `spring-boot-starter-web` cùng version chưa chứng minh cùng kết quả đóng gói.

## 4. Mẫu A — dùng `spring-boot-starter-parent`: cấu hình gọn

Ví dụ dưới đây cố định **Spring Boot 3.3.13** để có một bản minh họa nhất quán; đây là phiên bản dùng cho bài học, **không phải tuyên bố nó là phiên bản mới nhất hoặc còn trong thời hạn hỗ trợ**. Khi tạo ứng dụng mới, chọn dòng Spring Boot còn được hỗ trợ theo chính sách dự án và đối chiếu yêu cầu JDK/Maven tương ứng.

File `pom.xml` hoàn chỉnh cho ứng dụng Web có một test:

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
    <artifactId>pom-contrast-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>pom-contrast-demo</name>
    <description>Comparison of Spring Boot Maven dependency management options</description>

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
~~~

Vì sao mẫu này đủ gọn:

1. `<parent>` cho Maven kế thừa dependency management từ Boot, nên starter không cần khai báo version.
2. Parent 3.3.13 quy định mặc định compiler Java 17, encoding UTF-8, cách truyền metadata tham số và cấu hình plugin/lifecycle phù hợp; `java.version` được đặt tường minh cho người đọc dễ nhận biết.
3. Khai báo `spring-boot-maven-plugin` trong `<plugins>` kích hoạt cấu hình phù hợp từ parent. Parent đã cấu hình execution có ID `repackage` để đóng gói executable archive trong lifecycle.
4. `spring-boot-starter-test` chỉ ở `test` scope, không cần nằm trong runtime JAR.
5. `<relativePath/>` yêu cầu Maven resolve parent theo GAV qua repository, thay vì dò một `pom.xml` ở thư mục cha mà dự án không chủ ý sử dụng.

Cần phân biệt **“parent có sẵn execution `repackage`” với “không cần khai báo plugin”**. Khi dùng Spring Boot starter parent theo ví dụ, vẫn khai báo `spring-boot-maven-plugin` để execution áp dụng. Một POM không khai báo plugin mà vẫn đạt `mvn package` có thể chỉ sinh JAR thường, tùy các cấu hình thừa kế khác.

### 4.1. Kiểm chứng ngay cách A

~~~bash
# macOS/Linux; sử dụng Maven Wrapper đã được tạo/lưu trong repo
./mvnw help:effective-pom -Doutput=effective-parent.xml
./mvnw dependency:tree
./mvnw clean verify
jar tf target/pom-contrast-demo-0.0.1-SNAPSHOT.jar
~~~

Windows dùng `mvnw.cmd`. Trong effective POM, tìm `spring-boot-maven-plugin` và execution `repackage`; trong JAR, tìm `BOOT-INF/classes` và `BOOT-INF/lib`. `clean verify` đi qua `package` nên thường đã chạy packaging, miễn là plugin bind như trên và không bị skip. **Đây là các lệnh người học cần chạy; chúng chưa phải output thực tế đã được quan sát trong bài viết.**

## 5. Mẫu B — không kế thừa Boot parent, chỉ import BOM

Giữ nguyên module có `groupId=com.example`, `artifactId=pom-contrast-demo` và Java 17. POM dưới đây **không dùng Boot parent**; dùng Maven Super POM làm nền, import BOM rồi khai báo **build plugin version, compiler, test runner và Spring Boot repackaging execution** tường minh.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>pom-contrast-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>pom-contrast-demo</name>

    <properties>
        <spring-boot.version>3.3.13</spring-boot.version>
        <maven.compiler.release>17</maven.compiler.release>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
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
~~~

### 5.1. Cấu hình nào ở mẫu B phải tự gánh?

- **BOM import:** quản lý version của `spring-boot-starter-web`, `spring-boot-starter-test` và các dependency khác thuộc danh sách Boot. Nó **không** đăng ký Boot Maven plugin.
- **Compiler:** `maven-compiler-plugin` cùng `release=17` đảm bảo mã được biên dịch với API/classfile Java 17; `parameters=true` cung cấp metadata tên tham số cho các framework cần reflection.
- **Testing:** `maven-surefire-plugin` 3.2.5 có khả năng chạy JUnit Platform/Jupiter của `spring-boot-starter-test` theo cấu hình mặc định thích hợp.
- **Đóng gói JAR:** `maven-jar-plugin` sinh JAR thông thường ở `package`. Sau đó `spring-boot-maven-plugin` với goal `repackage` tạo executable Spring Boot JAR từ archive đó.
- **Plugin version:** được khai báo rõ, vì BOM import không kế thừa phiên bản plugin theo Spring Boot parent. Ví dụ cố tình chốt các version plugin phù hợp để người học biết chúng đến từ đâu, nhưng dự án thật cần chọn version tuân thủ công ty và kiểm thử tương thích.
- **Resources:** ví dụ không bật filtering cho file cấu hình; nếu cần thay biến Maven trong `application.properties`/`application.yml`, phải thiết kế `maven-resources-plugin`/resource filters riêng một cách an toàn.

### 5.2. Vì sao phải khai báo execution `repackage`?

Goal `repackage` **đóng gói lại archive đã tồn tại** để Spring Boot có launcher và dependency phù hợp. Khai báo tên plugin mà không ràng buộc goal vào lifecycle **không đủ** để bảo đảm `mvn package` tạo executable JAR khi không dùng Boot parent.

Khi phần `<executions>` trên có mặt, `repackage` chạy ở phase `package` theo default phase của goal, sau công việc tạo JAR thích hợp. Nếu một dự án tùy biến thứ tự/thêm execution của `maven-jar-plugin` trong cùng phase, cần chú ý để JAR gốc được tạo trước khi repackage.

Lệnh dùng với POM B:

~~~bash
./mvnw help:effective-pom -Doutput=effective-bom.xml
./mvnw dependency:tree
./mvnw clean verify
jar tf target/pom-contrast-demo-0.0.1-SNAPSHOT.jar
~~~

**Kỳ vọng đúng nếu project có Java source/test bên dưới:** cả A và B giải quyết starter theo cùng bộ BOM 3.3.13; đều biên dịch bằng Java 17, chạy test và tạo executable archive. Việc có cùng kết quả này xuất phát từ **cấu hình tường minh của POM B**, không phải vì import BOM tự mang toàn bộ parent build behavior.

Để so sánh **trong một bài tập**, hãy chạy A rồi lưu hai loại bằng chứng `effective-parent.xml` và dependency tree; thay POM bằng B, chạy sạch rồi lưu `effective-bom.xml`. Không đồng thời đặt hai POM ở cùng project và kỳ vọng Maven tự chọn đúng.

## 6. Một chương trình chung để kiểm thử cả hai POM

Đặt cùng source code trong **một project tại một thời điểm** để tránh đánh giá nhầm lỗi Java thành lỗi POM.

Cấu trúc file:

~~~text
pom-contrast-demo/
  pom.xml
  mvnw                 (Maven Wrapper của project)
  mvnw.cmd
  .mvn/wrapper/...
  src/main/java/com/example/demo/DemoApplication.java
  src/test/java/com/example/demo/DemoApplicationTest.java
~~~

`src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

`src/test/java/com/example/demo/DemoApplicationTest.java`:

~~~java
package com.example.demo;

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
class DemoApplicationTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void pingReturnsPong() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }
}
~~~

Chương trình dùng `spring-boot-starter-web` và `spring-boot-starter-test`, tương thích với **cấu trúc API của ví dụ Boot 3.3.13**. `@SpringBootTest` tải application context; `@AutoConfigureMockMvc` tạo MockMvc để thử request mà không cần mở HTTP listener thật; test kiểm tra status 200 và body `pong`. `src/test/java` không đi vào runtime archive như mã ứng dụng.

Khi có Maven Wrapper và một **JDK 17 tương thích**:

~~~bash
./mvnw clean verify

# Kiểm tra cấu trúc executable JAR
jar tf target/pom-contrast-demo-0.0.1-SNAPSHOT.jar

# Mở một terminal khác khi ứng dụng chạy:
java -jar target/pom-contrast-demo-0.0.1-SNAPSHOT.jar --server.port=8085
~~~

Sau khi app khởi động, ở terminal khác:

~~~bash
curl -i http://localhost:8085/ping
~~~

**Kỳ vọng hành vi:** HTTP 200 với response body chính xác `pong`. Log startup, thứ tự dòng, PID và thời gian không phải output cố định; hãy ghi lại kết quả thực tế. Nếu `java -jar` báo thiếu main manifest/launcher hoặc class, kiểm tra plugin `repackage` đã chạy hay chưa và có chọn đúng file JAR sau package không. Lưu ý đây là hướng dẫn thực hành và kỳ vọng kỹ thuật, **không phải báo cáo đã thực thi Maven trong môi trường của người học**.

## 7. Cách Maven quyết định phiên bản: property, quản lý cục bộ và xung đột

### 7.1. Khi kế thừa parent: override một property do Boot quản lý

Giả sử dự án dùng Boot parent và có lý do đã được kiểm chứng để thay version của nhóm SLF4J, một ví dụ *cơ chế* là:

~~~xml
<properties>
    <java.version>17</java.version>
    <slf4j.version>2.0.16</slf4j.version>
</properties>
~~~

**Vì sao có tác dụng:** trong chuỗi **kế thừa**, property do child định nghĩa có thể được dùng để nội suy version được quản lý tại mô hình parent. Tuy nhiên chỉ property thực sự tồn tại và được BOM/parent sử dụng ở phiên bản đang chọn mới có tác dụng. **Đừng dùng phiên bản trên làm lời khuyên nâng/hạ SLF4J:** Spring Boot đã kiểm thử với bộ dependency cụ thể; một override có thể phá tương thích với Logback/Spring Framework hoặc các starter khác.

Để xem property nào có trong bản Spring Boot đang dùng, đọc tài liệu dependency-version properties của **đúng phiên bản**, sau đó kiểm tra `effective-pom` và `dependency:tree`.

### 7.2. Khi chỉ import BOM: property ở project không tự override nội bộ BOM

Giả sử trong mẫu B, bạn viết:

~~~xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
    <slf4j.version>2.0.16</slf4j.version>
</properties>
~~~

`spring-boot.version` ở đây **có tác dụng** vì **chính POM hiện tại** đặt `${spring-boot.version}` trong tọa độ import BOM và Boot plugin.

Ngược lại, property `slf4j.version` **không tự chỉnh phiên bản SLF4J bên trong POM của BOM đã import**. Imported BOM được resolve như một mô hình độc lập; Maven đưa các dependency management entry của BOM vào dự án, không coi property của project nhập vào như override một parent được kế thừa.

Để quản lý một dependency cụ thể khác với BOM trong trường hợp này, khai báo **entry quản lý của chính project** trước entry import:

~~~xml
<dependencyManagement>
    <dependencies>
        <!-- Ví dụ minh họa cơ chế override, chỉ dùng sau khi kiểm tra tương thích -->
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Điều này là override cho tọa độ **`org.slf4j:slf4j-api`** được nêu, **không tự đồng bộ mọi module SLF4J**. Nếu một hệ thư viện được quản lý bởi BOM chuyên biệt, có thể cần import một BOM tương ứng đã được kiểm chứng trước Spring Boot BOM theo thứ tự ưu tiên của Maven. Tránh tự thay từng artifact trong một hệ sinh thái phức tạp nếu chưa hiểu tương thích toàn bộ.

### 7.3. Quy tắc ưu tiên thực tế cần nhớ

1. **Version khai báo trực tiếp** trên dependency đang dùng có thể làm lệch version managed của chính dependency đó.
2. **`dependencyManagement` cục bộ** cho một tọa độ có thể áp dụng version mong muốn thay entry được import.
3. **Nếu import nhiều BOM có entry trùng nhau**, thứ tự import và quy tắc quản lý Maven có thể quyết định entry nào được giữ; với các imported BOM cùng mức, thông thường mục xuất hiện **trước** được ưu tiên cho tọa độ trùng.
4. **Dependency mediation** là vấn đề khác: khi không có managed version, Maven xét các đường phụ thuộc theo quy tắc như nearest definition; không coi BOM import là lệnh buộc mọi transitive dependency bằng mọi giá.
5. Kiểm tra **resolved dependency tree**, không chỉ nhìn `pom.xml` hay tin rằng hai BOM “chắc chắn tương đương”.

~~~bash
# Xem resolved dependency, bao gồm transitive dependencies
./mvnw dependency:tree

# Giới hạn kết quả khi điều tra SLF4J
./mvnw dependency:tree -Dincludes=org.slf4j
~~~

Nếu project có quản lý version qua corporate parent, hãy xem **effective POM**, vì parent đó có thể chèn các entry hoặc plugin configuration khác với hai ví dụ.

## 8. Khác biệt thực dụng nhất: build plugin và executable packaging

Maven có hai luồng khác nhau mà người học thường gộp sai:

~~~text
Spring Boot parent
  -> dependencyManagement  -> version của starter/thư viện
  -> pluginManagement      -> version/config plugin
  -> plugin/lifecycle      -> mặc định resource, compiler, repackage...
                                 |
                         project khai báo Boot plugin
                                 |
                         mvn package -> executable archive
~~~

~~~text
Import Spring Boot BOM
  -> dependencyManagement  -> version của starter/thư viện
                                 |
  + project/parent riêng phải khai báo compiler, test, resources,
    Spring Boot Maven plugin và execution repackage
                                 |
                         mvn package -> executable archive
                         (khi cấu hình thêm đúng)
~~~

Tức là **`<dependencyManagement>` không chạy goal `repackage`**. Thậm chí trong dự án không có Spring Boot parent, plugin sau mới chỉ là **khai báo plugin**, chưa bảo đảm bind goal khi chạy `package`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.13</version>
</plugin>
~~~

Cấu hình độc lập đúng cho executable package cần goal `repackage` như ở mẫu B. Mặt khác, nếu đã dùng Boot parent, việc khai báo thêm execution `repackage` vô tình có ID khác với execution do parent cấp có thể khiến goal chạy hai lần; khi cần thay cấu hình execution có sẵn, tham chiếu đúng ID `repackage`.

**Cách kiểm chứng:** không chỉ xem `BUILD SUCCESS`, mà cần kiểm tra `target/*.jar` bằng `jar tf` và chạy `java -jar` thật. Spring Boot executable JAR thường có `BOOT-INF/classes/` và `BOOT-INF/lib/`. Một plain JAR thành công ở phase `package` vẫn có thể thiếu launcher hoặc các runtime dependency cần thiết.

Ngoài JAR, các trường hợp WAR, layered JAR, OCI image và native image cần thêm cấu hình/plugin/goal phù hợp. Việc import BOM không tự kích hoạt chúng; cả khi dùng parent cũng không mặc nhiên tạo mọi dạng package.

## 9. Khác biệt về compiler, test, resource filtering và build reproducibility

### 9.1. Java, encoding và metadata tham số

Trong Spring Boot 3.3.13, starter parent có mặc định compile ở Java 17, encoding UTF-8 và `-parameters`. Import BOM **không tự quy định** những giá trị này. Nếu không cấu hình compiler, version của compiler plugin/Maven defaults có thể khác với mong đợi hoặc không hỗ trợ bytecode cần thiết.

Trong mẫu B, các thiết lập:

~~~xml
<maven.compiler.release>17</maven.compiler.release>
<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
~~~

và `<parameters>true</parameters>` ở `maven-compiler-plugin` có mục đích tái hiện những đặc điểm quan trọng, nhưng **không đồng nghĩa sao chép toàn bộ cấu hình parent**. Nếu ứng dụng cần generated sources, annotation processors hoặc test-specific compiler options, chúng vẫn phải được cấu hình riêng.

### 9.2. JUnit và Surefire/Failsafe

`spring-boot-starter-test` quản lý **dependency test**; việc Maven khám phá test còn phụ thuộc **maven-surefire-plugin**, JUnit Platform engine và cấu hình test. Trong mẫu B, Surefire version được khai báo rõ để tránh lệ thuộc mặc định từ Maven/Super POM. Parent thường quản lý version và cấu hình plugin tương ứng.

**Integration test không tự xuất hiện** chỉ vì dùng parent hoặc import BOM. Nếu dùng Failsafe, Testcontainers, profile/tách source sets, cần cấu hình thực sự và báo cáo test cho phase `integration-test`/`verify`. Vì vậy mọi kết luận về test phải dựa trên report thực tế.

### 9.3. Filtering file cấu hình Spring Boot

Một file `application.properties` có thể chứa placeholder của Spring như:

~~~properties
server.port=${PORT:8080}
spring.application.name=pom-contrast-demo
~~~

Dòng `${PORT:8080}` là placeholder được Spring giải quyết **khi ứng dụng chạy**. Nếu Maven resource filtering vô tình xử lý `${...}` như Maven property, có nguy cơ thay/chạm vào giá trị runtime.

Spring Boot starter parent có thiết lập resource filtering riêng, dùng delimiter kiểu `@project.version@` cho dữ liệu build khi cần, tránh xung đột thông thường với Spring placeholder. Khi chỉ import BOM, bạn phải tự chọn có bật filtering hay không, xác định delimiter và tài nguyên nào được filter; **không sao chép mù quáng tùy chọn Maven resource mặc định**.

Ví dụ minh họa một **template có chủ đích**:

~~~properties
app.build.version=@project.version@
app.runtime.port=${PORT:8080}
~~~

Chỉ kỳ vọng `@project.version@` biến thành version tại build **khi đã cấu hình resource filtering phù hợp**; BOM import riêng lẻ sẽ không bảo đảm điều đó. Sau đóng gói, kiểm tra file trong archive, đừng suy từ YAML/properties ở source.

### 9.4. Khả năng tái lập và quản lý công ty

- Ghi và dùng **Maven Wrapper** cùng JDK/toolchain được hỗ trợ; parent hay BOM đều không thay thế Wrapper.
- Cố định version Boot BOM, Spring Boot Maven plugin và các build plugin mà project kiểm soát; tránh ghép Boot BOM version X với plugin version Y không được kiểm thử.
- Corporate parent có thể cung cấp plugin versions, repositories, profile, enforcer, security gates, distribution management hoặc quy tắc release riêng. Nhập BOM giúp giữ các quy tắc đó nhưng **không bảo đảm chúng không xung đột** với Boot.
- Plugin repositories khác dependency repositories; cùng dependency tree không chứng minh plugin versions giống nhau.
- Với Maven reactor nhiều module, quyết định **module nào dùng BOM** và **module nào là ứng dụng thực thi**. Đừng đặt `repackage` cho mọi library module không có main class.
- Để kiểm tra hai cách tương đương ở mức cần thiết, so sánh resolved dependency tree, plugin executions, compiler level, test discovery, cấu trúc JAR và runtime smoke test.

## 10. Kịch bản multi-module và corporate parent: chọn đúng tầng kế thừa

Giả sử công ty yêu cầu mọi Maven module kế thừa `com.company:company-parent` để tuân thủ các quy tắc chuẩn. Mỗi module Maven vẫn chỉ có một `<parent>` trực tiếp, nên không thể thêm cùng lúc `spring-boot-starter-parent` như **parent thứ hai**.

Lựa chọn phổ biến:

1. **Giữ company parent; import Boot BOM** tại corporate parent hoặc module phù hợp và khai báo build plugin/repackage ở module ứng dụng. Các module thư viện không cần `repackage`.
2. **Company parent tự kế thừa Boot starter parent** nếu công ty chủ động thiết kế chuỗi kế thừa đó. Khi ấy module con có thể nhận mặc định Boot theo parent chain, nhưng việc khóa version Boot phải được phối hợp ở cấp tổ chức.
3. **Không có parent bắt buộc:** dùng thẳng starter parent ở ứng dụng đơn lẻ, giảm lượng cấu hình phải duy trì.
4. **Cần kiểm soát plugin tập trung khác Boot:** corporate parent + import BOM thường dễ hợp nhất với quy tắc build hiện hữu hơn, với điều kiện nhóm ghi rõ các plugin versions và quality gate.

Ví dụ *đoạn* POM cho module ứng dụng đang kế thừa một parent nội bộ (không phải POM chạy độc lập):

~~~xml
<parent>
    <groupId>com.company</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
</parent>

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

Đây là **mảnh minh họa**, không có nghĩa `com.company:company-parent:1.0.0` tồn tại trên repository của bạn. Thực tế phải xem parent nội bộ có quy tắc nào về `dependencyManagement`, `pluginManagement`, Maven Enforcer, Java target và cách publish. Đặt BOM ở parent chung khi muốn tất cả module theo một bộ version; nếu chỉ module Spring Boot cần BOM thì scope chính xác ở module đó.

### Quy tắc chia vai trò trong Maven reactor

- **Library module:** thường sinh JAR thông thường, cung cấp class cho module khác; không nên ép thành executable JAR.
- **Application module:** chứa main Spring Boot, thêm starter, plugin `repackage` và cấu hình package chạy được.
- **Parent/aggregator POM:** điều phối dependency/plugin management và module list; không nhất thiết có mã ứng dụng hay artifact chạy bằng `java -jar`.

Đừng nhầm `<modules>` (aggregation) với `<parent>` (inheritance): một reactor root liệt kê module chưa chắc là parent của mọi module nếu mỗi module không khai báo kế thừa. Tách rõ ranh giới này giúp đặt BOM đúng cấp và tránh mất hiệu lực management.

## 11. Bài kiểm chứng: đo ba kết quả, đừng chỉ so POM bằng mắt

Dùng **cùng source Java/test** ở mục 6; lần lượt thử POM A rồi POM B. Với mỗi cách, ghi bằng chứng:

| Kiểm chứng | Lệnh/quan sát | Điều cần xác nhận |
| --- | --- | --- |
| **Dependency versions** | `./mvnw dependency:tree` | Starter/Jackson/Spring/JUnit dùng những version được BOM quản lý; không xuất hiện dependency thiếu version. |
| **Effective POM** | `./mvnw help:effective-pom -Doutput=effective-pom.xml` | Có khác biệt ở parent chain, compiler/pluginManagement, resource settings và execution `repackage`. |
| **Toolchain** | `./mvnw -version`, compiler config | Maven chạy bằng JDK phù hợp, bytecode target là Java 17. |
| **Test** | `./mvnw clean verify`, `target/surefire-reports/` | JUnit test được phát hiện, chạy và PASS; không bị skip. |
| **Artifact** | `jar tf target/pom-contrast-demo-0.0.1-SNAPSHOT.jar` | JAR có loader/manifest và runtime dependency phù hợp cho Spring Boot. |
| **Runtime** | `java -jar ... --server.port=8085`; `curl -i localhost:8085/ping` | Khởi động được và `GET /ping` trả status 200, body `pong`. |

Nếu A pass nhưng B fail, chẩn đoán theo nguyên nhân:

- **`maven-compiler-plugin` lỗi:** kiểm tra plugin version, `release`, JDK đang chạy và corporate parent.
- **Test không chạy hoặc không tìm thấy engine:** kiểm tra Surefire/Failsafe plugin và report, đừng suy từ starter-test một cách tự động.
- **JAR plain / `no main manifest attribute`:** kiểm tra `spring-boot-maven-plugin` execution `repackage` trong effective POM và output Maven `package`.
- **Sai Spring Boot plugin version:** so khớp property/khai báo version plugin với BOM.
- **Resource bị sửa ngoài ý muốn:** kiểm tra filtering/delimiter và nội dung file trong archive.
- **Dependency conflict:** dùng dependency tree và nguồn `dependencyManagement` hiệu lực; kiểm tra corporate parent, imported BOM khác và dependency version trực tiếp.
- **Build xanh nhưng không chạy:** runtime config, profile, port, Java version hoặc external services chưa phù hợp; đây là lớp kiểm chứng riêng.

### Câu hỏi tự kiểm tra

1. Vì sao `spring-boot-starter-parent` là POM ở `<parent>`, còn `spring-boot-dependencies` được import ở `<dependencyManagement>`?
2. Khi import BOM, tại sao vẫn phải khai báo `spring-boot-starter-web` trong `<dependencies>`?
3. Tại sao cùng BOM có thể cho ra cùng cây dependency nhưng chỉ một project tạo executable JAR?
4. Maven chỉ có một parent trực tiếp: dự án buộc dùng corporate parent thì làm sao giữ dependency alignment với Spring Boot?
5. Tại sao override property `slf4j.version` có tác dụng với parent nhưng không tự sửa nội dung imported BOM?
6. `pluginManagement` và `dependencyManagement` quản lý hai loại version nào? `<plugins>` đóng vai trò gì?
7. Khi không dùng starter parent, cần khai báo những gì để Java 17, JUnit test, resource handling và `repackage` hoạt động đúng?
8. Trong reactor có library module, vì sao không nên áp cùng Spring Boot executable repackage goal lên mọi module?
9. Sẽ kiểm tra nội dung nào của `effective-pom`, dependency tree và JAR trước khi kết luận hai phương án đã tương đương về chất lượng?
10. Nếu dùng parent mà `mvn package` vẫn tạo plain JAR, bạn sẽ kiểm tra điều gì đầu tiên?

**Tiêu chí hoàn thành:** người học tự chọn được mô hình phù hợp yêu cầu dự án, viết được POM tương ứng, giải thích nơi xuất phát của dependency version **và** plugin version, xác minh được execution `repackage` cùng test/report, rồi chạy đúng executable artifact. Đạt bài khi kết quả kiểm chứng hỗ trợ nhận định, không chỉ vì cú pháp XML được chấp nhận.

## 12. Tài liệu tham khảo

- [Spring Boot Maven Plugin — Using the Plugin: Parent vs BOM](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)

**Ghi nhớ:** lựa chọn parent hay BOM import không phải một nhãn chất lượng. Chất lượng bản dựng được đánh giá bằng **effective POM, dependency tree, compiler/test evidence, archive và hành vi runtime**. Parent giảm cấu hình lặp; BOM import tạo quyền kiểm soát rõ hơn khi dự án có parent khác, đồng thời chuyển trách nhiệm cấu hình phần còn lại sang nhóm phát triển.