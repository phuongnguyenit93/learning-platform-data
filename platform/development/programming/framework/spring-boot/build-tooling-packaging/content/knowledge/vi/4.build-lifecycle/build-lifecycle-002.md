# Vòng đời build Maven: validate, compile, test, package, verify, install và deploy

Trong dự án Spring Boot dùng **Maven**, các từ `validate`, `compile`, `test`, `package`, `verify`, `install` và `deploy` là **phase** của *default build lifecycle*. Chúng là những cột mốc có thứ tự; Maven thực hiện công việc thực tế nhờ các **plugin goal** được gắn vào từng phase. Nắm được điều này giúp biết lệnh nào chỉ biên dịch, lệnh nào chạy kiểm thử, lệnh nào tạo JAR chạy được và lệnh nào công bố artifact cho dự án khác.

> Phạm vi: bài này giải thích chính xác **Maven lifecycle trong Spring Boot**, rồi đối chiếu ở mức ý tưởng với Gradle. Gradle có cơ chế task riêng; không có chuỗi phase Maven giống hệt.

## 1. Phân biệt lifecycle, phase, plugin và goal

- **Lifecycle** là quy trình build được Maven định nghĩa. Maven có ba lifecycle tích hợp: `default` (build/phát hành artifact), `clean` (dọn output) và `site` (tạo tài liệu site).
- **Phase** là một mốc trong lifecycle, ví dụ `test` hoặc `package`. Bản thân tên phase không chứa thuật toán compile hay chạy test.
- **Plugin** là phần mở rộng cung cấp công việc cụ thể, ví dụ `maven-compiler-plugin`, `maven-surefire-plugin`, `maven-jar-plugin` hoặc `spring-boot-maven-plugin`.
- **Goal** là một thao tác của plugin, ví dụ `compiler:compile`, `surefire:test`, `jar:jar`, `spring-boot:repackage`.
- **Binding** là liên kết một goal với phase. Binding mặc định phụ thuộc `<packaging>` của POM (`jar`, `war`, `pom`, …); plugin/parent POM cũng có thể bổ sung hoặc điều chỉnh binding.

Ví dụ với dự án `jar`, khi chạy `mvn compile`, Maven đi qua các phase cần thiết đến `compile`; tại phase `compile`, plugin compiler thường thực hiện goal biên dịch Java. Lệnh `mvn compiler:compile` gọi trực tiếp một goal; nó không có ý nghĩa tương đương toàn bộ quy trình `mvn compile` vì có thể bỏ qua các phase chuẩn bị resource/source được bind trước đó.

Hai quy tắc cốt lõi:

1. **Gọi phase cuối cần đạt:** `mvn verify` tự đi qua các phase trước `verify`. Không cần gõ `mvn validate compile test package verify`.
2. **Phase chạy không có nghĩa mọi loại kiểm tra đều được cấu hình:** `verify` chỉ thực hiện các kiểm tra thực tế nếu các plugin goal tương ứng được bind; `package` chỉ tạo executable Boot JAR nếu Spring Boot packaging đã cấu hình đúng.

## 2. Thứ tự bảy phase và đầu ra điển hình

~~~text
                      DEFAULT LIFECYCLE (MAVEN)
                               |
       validate -> compile -> test -> package -> verify -> install -> deploy
          |          |         |        |         |         |         |
       POM hợp lệ   .class   unit test  JAR/WAR   check IT   Maven    Remote
                                           |        & QA    local repo artifact repo
                                           v
                                  Spring Boot repackage
                                  nếu plugin được bind
~~~

Đây là **sơ đồ rút gọn**, không phải danh sách đầy đủ mọi phase. Maven còn có các mốc xen giữa như `process-resources`, `test-compile`, `pre-integration-test`, `integration-test`, `post-integration-test`. Khi chạy `mvn verify`, Maven cũng đi qua các mốc trung gian đó theo đúng thứ tự.

| Phase | Maven hướng đến điều gì? | Công việc thường gặp khi plugin được bind | Đã có artifact đưa đi dùng chưa? |
| --- | --- | --- | --- |
| `validate` | Xác nhận thông tin/cấu trúc dự án đủ để build | Kiểm tra POM và các điều kiện cấu hình; có thể thêm Enforcer | Chưa |
| `compile` | Biên dịch mã ứng dụng | Xử lý resources, `compiler:compile` → `target/classes` | Chưa đóng gói |
| `test` | Biên dịch và chạy kiểm thử đơn vị | `compiler:testCompile`, `surefire:test` → báo cáo ở `target/surefire-reports` | Chưa đóng gói |
| `package` | Đóng gói bản phân phối | `jar:jar`/`war:war`; với Boot có thêm `spring-boot:repackage` | Thường đã có JAR/WAR |
| `verify` | Kiểm tra artifact và kết quả kiểm thử bổ sung | Kiểm tra kết quả integration test bằng Failsafe, kiểm tra chất lượng nếu cấu hình | Có; thêm bằng chứng kiểm chứng |
| `install` | Đưa artifact vào Maven repository **trên máy hiện tại** | `install:install` | Có, cho các dự án local khác dùng |
| `deploy` | Xuất bản artifact tới **repository từ xa** | `deploy:deploy` | Có, cho CI/đội/dự án khác lấy về |

`validate` không có nghĩa Maven tự kiểm tra toàn bộ nghiệp vụ. `verify` không có nghĩa mọi project tự chạy integration test, coverage hay security scan. Giá trị thực tế của mỗi mốc phụ thuộc vào **POM, packaging, plugin bindings và profile đang kích hoạt**.

## 3. Từng phase làm gì, và không làm gì?

### 3.1. `validate` — kiểm tra điều kiện khởi đầu

~~~bash
mvn validate
~~~

Maven tải/đọc cấu hình cần thiết, kiểm tra project model và đi đến phase `validate`. Plugin tự viết hoặc `maven-enforcer-plugin` có thể kiểm tra Java/Maven version và policy nếu được cấu hình. Đây là điểm để phát hiện sớm POM thiếu thông tin, cấu hình không hợp lệ hoặc quy tắc dự án bị vi phạm.

**Không suy ra:** `mvn validate` đã chạy unit test hay đã tạo JAR; cũng không mặc định kiểm tra quy tắc nghiệp vụ, bảo mật hoặc coding style.

### 3.2. `compile` — biên dịch mã sản phẩm

~~~bash
mvn compile
~~~

Với Java `jar` project, các goal chuẩn thường xử lý resources rồi dùng compiler để biến `src/main/java` thành `target/classes`. Maven lấy dependencies của compile classpath, còn **JDK** cung cấp compiler thực tế.

Ví dụ `src/main/java/com/example/demo/MessageService.java`:

~~~java
package com.example.demo;

public class MessageService {
    public String message() {
        return "Hello Maven lifecycle";
    }
}
~~~

Sau `mvn compile`, class này thường nằm trong `target/classes/com/example/demo/MessageService.class`. Đây là **bytecode**, chưa phải file JAR phân phối. `compile` chưa đi đến `test-compile` và `test`, nên không coi `mvn compile` là kết quả kiểm thử thành công.

### 3.3. `test` — kiểm thử đơn vị và các bước chuẩn bị

~~~bash
mvn test
~~~

Maven thực hiện các phase trước đó, xử lý test resources, compile code trong `src/test/java`, rồi thường gọi `maven-surefire-plugin` để chạy unit tests. Với JUnit Jupiter phù hợp, lớp kiểm thử có dạng:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MessageServiceTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Hello Maven lifecycle", new MessageService().message());
    }
}
~~~

Tên lớp `MessageServiceTest` phù hợp mẫu nhận diện mặc định của Surefire. Test xác minh hành vi của `MessageService` mà không cần khởi động server. Nếu test thất bại, build thông thường dừng trước `package`.

Chú ý `mvn test` **không tương đương** `mvn -DskipTests package`. Trong trường hợp thứ hai, Maven vẫn có thể compile test sources nhưng bỏ qua bước chạy test; `-Dmaven.test.skip=true` còn yêu cầu bỏ qua test compilation trong các plugin hỗ trợ. Không nên dùng cờ skip để chứng minh chất lượng của bản phát hành.

### 3.4. `package` — tạo artifact

~~~bash
mvn package
~~~

Với `<packaging>jar</packaging>`, Maven tạo file JAR trong `target/` theo tên artifact/version. Nếu dự án Spring Boot có `spring-boot-maven-plugin` được cấu hình để chạy `repackage`, goal này **đóng gói lại archive đã tạo** thành executable Spring Boot JAR có thể chạy bằng `java -jar` và mang dependencies runtime theo cách đóng gói của Boot.

Phân biệt:

- **Plain JAR:** archive Java thông thường; không chắc có launcher, `Main-Class` hay đủ dependencies để chạy độc lập.
- **Executable Spring Boot JAR:** có cấu trúc Boot (chẳng hạn `BOOT-INF/classes` và `BOOT-INF/lib`) cùng launcher. Khi build đúng, có thể khởi động với `java -jar`.
- **WAR:** sử dụng khi chọn `war` packaging và cấu hình phù hợp; có các quy ước deployment/servlet container riêng.

`package` chạy sau unit tests trong lifecycle mặc định. **Một JAR được tạo thành công không bảo đảm ứng dụng sẽ kết nối database, mở cổng hoặc hoạt động đúng trong production.**

### 3.5. `verify` — kiểm tra kết quả build và integration test

~~~bash
mvn verify
~~~

Đây là mốc sau `package`. Trước `verify` có `pre-integration-test`, `integration-test` và `post-integration-test`. Nếu cấu hình Failsafe, integration tests được thực hiện ở `integration-test` và kết quả được xác nhận ở `verify`, cho phép phần dọn môi trường ở `post-integration-test` chạy trước khi build báo lỗi test.

Điểm dễ nhầm:

- **Surefire** thường chạy unit tests tại `test`.
- **Failsafe** thường chạy integration tests tại `integration-test` và kiểm tra kết quả tại `verify`, **nhưng phải khai báo/bind** phù hợp.
- Gọi `mvn integration-test` trực tiếp có thể bỏ qua `post-integration-test`/`verify`, làm dở bước thu dọn hoặc xác nhận kết quả. Khi dự án có integration test lifecycle, **ưu tiên `mvn verify`**.
- `mvn verify` không tự tạo integration tests, quality gate hoặc coverage threshold. Những quy tắc này đến từ plugin/configuration được khai báo.

Nếu dự án chưa khai báo bất kỳ goal riêng nào cho integration test/verify, `mvn package` và `mvn verify` có thể có kết quả thực tế rất giống nhau. Không nên từ đó kết luận hai phase là cùng một khái niệm.

### 3.6. `install` — cài artifact vào repository cục bộ

~~~bash
mvn install
~~~

Maven đi qua các phase trước, sau đó cài artifact, POM và metadata liên quan vào **local Maven repository**. Mặc định repository nằm tại `~/.m2/repository` trên nhiều môi trường; vị trí có thể được thay đổi bởi cấu hình Maven.

Giả sử project có tọa độ Maven:

~~~text
groupId:    com.example
artifactId: lifecycle-demo
version:    1.0.0
packaging:  jar
~~~

Một artifact được cài thành công có đường dẫn kiểu:

~~~text
~/.m2/repository/com/example/lifecycle-demo/1.0.0/lifecycle-demo-1.0.0.jar
~~~

Project khác trên **cùng môi trường Maven/repository** có thể khai báo dependency `com.example:lifecycle-demo:1.0.0` nếu artifact phù hợp để làm dependency. Với executable Boot JAR, việc dùng nó như một thư viện Java thông thường thường **không phải lựa chọn đúng** vì cấu trúc executable archive khác plain library JAR; nên thiết kế module thư viện riêng khi cần chia sẻ API/code.

`install` **không** gửi file lên server của đội, không chạy Spring Boot và không tạo container deployment.

### 3.7. `deploy` — đưa artifact lên Maven repository từ xa

~~~bash
mvn deploy
~~~

Sau khi các phase trước thành công, Maven deploy plugin đẩy artifact cùng POM/metadata tới **remote artifact repository** như Nexus, Artifactory hoặc dịch vụ tương đương, theo cấu hình publish. Thường cần `distributionManagement` trong POM hoặc cấu hình tương đương và thông tin xác thực ứng với repository ID trong `settings.xml` hay cơ chế bảo mật CI.

**Quan trọng: Maven `deploy` không có nghĩa “triển khai và khởi chạy Spring Boot ở production”.** Nó xuất bản bản build cho hệ thống khác tải về. Việc đưa JAR/container image lên VM, Kubernetes hay nền tảng cloud rồi khởi chạy/rolling update là **bước application deployment riêng**, do CD pipeline, Docker/Kubernetes hoặc công cụ vận hành thực hiện.

`mvn deploy` có thể thất bại nếu thiếu repository URL, credential, quyền publish, mạng hoặc policy phiên bản (ví dụ không được ghi đè release). Chỉ chạy deploy khi chủ đích thực sự là xuất bản artifact ra kho chung.

## 4. Gọi một phase sẽ chạy những phase nào?

| Lệnh | Mốc cuối của default lifecycle | Hệ quả điển hình |
| --- | --- | --- |
| `mvn validate` | `validate` | Kiểm tra cấu hình; chưa compile |
| `mvn compile` | `compile` | Compile main code; chưa chạy test |
| `mvn test` | `test` | Compile main/test và chạy unit tests |
| `mvn package` | `package` | Chạy unit tests rồi tạo archive |
| `mvn verify` | `verify` | Package, integration phases và các bước verify được cấu hình |
| `mvn install` | `install` | Verify rồi thêm artifact vào local repo |
| `mvn deploy` | `deploy` | Install rồi publish lên remote artifact repo |
| `mvn clean verify` | `clean` trước, rồi `verify` | Dọn output cũ trước khi build mới đến verify |

**Lưu ý về `clean`:** nó thuộc *clean lifecycle* độc lập. `mvn package` không mặc định xóa thư mục `target`. `mvn clean package` chạy phase `clean` rồi chạy default lifecycle đến `package`. Đây là lý do CI thường dùng một clean build để giảm ảnh hưởng của output còn lại từ lần build trước.

**Lưu ý về thứ tự:** Maven thực hiện các phase theo thứ tự chuẩn; không cần gõ toàn bộ chuỗi. Một phase có thể có nhiều goal, một số phase có thể không có goal nào được bind. Plugin goal gọi trực tiếp như `mvn spring-boot:run` hoặc `mvn surefire:test` là kiểu lệnh khác với gọi phase: hành vi chuẩn bị trước đó phụ thuộc goal và cấu hình, không nên tự coi là toàn bộ lifecycle.

## 5. Bài thực hành: Maven đóng gói Spring Boot JAR

Ví dụ này dùng **Java 21**, **Maven 3.9.x** và **Spring Boot 3.3.5** để cố định hành vi minh họa; các phiên bản này được chọn cho bài thực hành, không phải khẳng định đây là bản phát hành mới nhất. Maven phải có JDK tương thích và có thể truy cập repository tải dependencies.

Tạo cấu trúc:

~~~text
lifecycle-demo/
  pom.xml
  src/
    main/java/com/example/demo/
      DemoApplication.java
      MessageService.java
    test/java/com/example/demo/
      MessageServiceTest.java
~~~

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

**src/main/java/com/example/demo/DemoApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
        System.out.println(new MessageService().message());
    }
}
~~~

**src/main/java/com/example/demo/MessageService.java**

~~~java
package com.example.demo;

public class MessageService {
    public String message() {
        return "Hello Maven lifecycle";
    }
}
~~~

**src/test/java/com/example/demo/MessageServiceTest.java**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MessageServiceTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Hello Maven lifecycle", new MessageService().message());
    }
}
~~~

`spring-boot-starter-parent` cung cấp quy ước/plugin management; `spring-boot-maven-plugin` được khai báo trong `build.plugins` sẽ dùng cấu hình `repackage` mà parent chuẩn bị. `spring-boot-starter-test` cung cấp thư viện JUnit Jupiter trong test scope. Không cần viết tay version của từng starter trong mẫu này.

Từ thư mục `lifecycle-demo`, chạy lần lượt:

~~~bash
java --version
mvn --version
mvn clean test
mvn package
mvn verify
~~~

Với mã và dependencies như trên, `MessageServiceTest` sẽ chạy và pass. Số dòng log, thời gian và định dạng báo cáo của Maven thay đổi theo môi trường; không nên copy những dòng đó như một stdout cố định.

Quan sát artifact sau `package`/`verify`:

~~~bash
jar tf target/lifecycle-demo-1.0.0.jar
java -jar target/lifecycle-demo-1.0.0.jar
~~~

Lệnh `jar tf` liệt kê nội dung archive (hãy tìm `BOOT-INF/classes` và `BOOT-INF/lib`). Trong log khởi động khi chạy JAR sẽ có một dòng:

~~~text
Hello Maven lifecycle
~~~

Đó là dòng do `System.out.println` phát ra; các dòng log Spring Boot khác không được cố định trong ví dụ. Vì mẫu chỉ dùng `spring-boot-starter`, nó **không tạo HTTP server**. Mục đích là quan sát khác nhau giữa **compile**, **unit test**, **tạo executable JAR** và **chạy artifact**.

Nếu dự án có Maven Wrapper, sử dụng `./mvnw` trên Linux/macOS hoặc `mvnw.cmd` trên Windows thay cho `mvn` trong các lệnh trên. Wrapper dùng phiên bản Maven mà dự án cấu hình.

### Mổ xẻ điều gì xảy ra khi chạy `mvn package`

1. Maven đọc POM, parent, dependency và các plugin binding.
2. Các phase tới `compile` tạo `target/classes` từ mã trong `src/main/java`.
3. Các phase đến `test` compile `MessageServiceTest` rồi Surefire chạy test; failure có thể làm build dừng.
4. Tại `package`, plugin JAR tạo archive; Spring Boot Maven plugin chạy `repackage` theo cấu hình parent/plugin để tạo executable JAR.
5. Maven dừng ở `package`, **chưa chạy `verify`, `install` hay `deploy`** trừ khi có thao tác độc lập khác ngoài chuỗi đang mô tả.

`java -jar ...` là lệnh **runtime**, không phải một phase Maven. Sau khi JAR đã sẵn sàng, server chạy ứng dụng không nhất thiết cần Maven.

## 6. Khi nào `verify` khác `package`? Ví dụ integration test với Failsafe

Bài thực hành ở mục 5 có unit test nên `mvn package` và `mvn verify` đều chạy `MessageServiceTest`. Nếu muốn Maven thật sự thực hiện integration test tại các phase riêng, cần cấu hình Failsafe.

Thêm plugin sau vào bên trong `<build><plugins> ... </plugins></build>` của POM (giữ plugin Spring Boot đã có):

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.2.5</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Tạo test **src/test/java/com/example/demo/ApplicationIT.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationIT {
    @Test
    void springApplicationContextStarts() {
        // Thành công khi Spring Boot application context được khởi tạo.
    }
}
~~~

`@SpringBootTest` khởi tạo application context thực thay vì chỉ gọi một Java method; đây là một **integration/smoke test đơn giản về cấu hình ứng dụng**, chưa phải kiểm thử tích hợp database hay HTTP. Tên `ApplicationIT` phù hợp quy ước nhận diện của Failsafe, trong khi test `MessageServiceTest` vẫn chạy bằng Surefire. Với dependency và plugin ở POM mẫu, test có thể khởi tạo context mà không cần server web.

Thực hiện:

~~~bash
mvn clean package
mvn clean verify
~~~

Ở cách cấu hình này:

- `package` chạy **unit test** rồi tạo JAR; nó chưa đến `integration-test`, nên không chạy `ApplicationIT` qua Failsafe.
- `verify` đi qua `integration-test`, Failsafe chạy `ApplicationIT`, rồi goal `failsafe:verify` kiểm tra kết quả. Nếu test lỗi, `verify` báo build thất bại theo cấu hình mặc định.
- Báo cáo tương ứng thường ở `target/surefire-reports` và `target/failsafe-reports`. Để hiểu rõ test nào chạy, kiểm tra log goal và các báo cáo thực tế thay vì chỉ đọc tên phase.

Với integration tests cần dựng database/container: có thể bind tác vụ setup ở `pre-integration-test`, chạy test ở `integration-test`, dọn môi trường tại `post-integration-test` và dùng `verify` để kết luận. Không nên gọi trực tiếp `mvn integration-test` làm lệnh CI cuối cùng vì có thể không chạy phần dọn và kiểm tra.

## 7. Cơ chế công bố artifact: install vs deploy vs chạy ứng dụng

Ba việc rất dễ bị gọi chung là “deploy” nhưng kết quả và nơi nhận khác nhau:

~~~text
mvn verify
   -> Chứng minh build đáp ứng các kiểm tra đã cấu hình
   -> artifact còn ở target/

mvn install
   -> Các bước đến verify + lưu artifact/POM tại local Maven repository
   -> Các build khác dùng chung local repo có thể resolve artifact

mvn deploy
   -> Các bước đến install + upload artifact/POM lên remote Maven repository
   -> CI, đội khác hoặc quy trình CD có thể tải artifact

Application deployment (CD)
   -> Tải artifact hoặc dựng image -> đưa tới runtime -> khởi động/rollout
   -> Cấu hình môi trường, service, network, health check
~~~

Để `mvn deploy` hoạt động, thông thường cấu hình publish repository (minh họa, **URL giả định**):

~~~xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <url>https://repo.example.invalid/maven-releases</url>
    </repository>
</distributionManagement>
~~~

Và cấu hình xác thực ở `settings.xml` của Maven hoặc secret của CI tương ứng với ID `team-releases`; không đặt mật khẩu/token trực tiếp trong POM. Nếu xuất bản SNAPSHOT, cần chính sách và `snapshotRepository` tương ứng. Cấu hình mẫu trên **chỉ giải thích cơ chế**, không phải một repository có thể publish thật.

Khi chỉ cần kiểm tra project trước khi merge, thường dùng `mvn clean verify`. Khi cần project khác trên máy sử dụng dependency vừa build, dùng `mvn install`. Khi release artifact đến repository chung, thực hiện `mvn deploy` theo quyền và quy trình CI/release đã được thiết lập.

**Với Spring Boot:** ứng dụng chạy từ executable JAR tại `target/` và hệ thống CD có thể dùng cùng JAR để tạo image/deploy service. Maven không tự tạo Deployment Kubernetes hay mở cổng ứng dụng chỉ vì `deploy` thành công. Mặt khác, nếu dự án dùng Gradle, các bước publishing có task tương ứng theo plugin cấu hình; tên và thứ tự task không nên lấy nguyên xi từ Maven.

## 8. Maven phase không phải Gradle task: đối chiếu đúng mức

Trong module Spring Boot dùng **Gradle**, cơ chế là đồ thị task và task dependency. Nó không có nguyên chuỗi phase `validate → ... → deploy` của Maven.

| Mục tiêu | Maven thường dùng | Gradle thường dùng khi plugin thích hợp được áp dụng |
| --- | --- | --- |
| Biên dịch nguồn Java | `mvn compile` | `./gradlew classes` hoặc `./gradlew compileJava` |
| Chạy unit tests | `mvn test` | `./gradlew test` |
| Kiểm tra và build | `mvn verify` | `./gradlew build` (thường gồm `check` và `assemble`) |
| Tạo executable Spring Boot JAR | `mvn package` với Boot `repackage` | `./gradlew bootJar` |
| Publish vào Maven local | `mvn install` | `./gradlew publishToMavenLocal` khi có `maven-publish` |
| Publish vào remote artifact repo | `mvn deploy` | `./gradlew publish` khi đã cấu hình repository/publications |

Đây là **ánh xạ về mục đích**, không phải đảm bảo tương đương 100%. Chẳng hạn `gradlew build` không tự bật mọi integration test task nếu dự án chưa nối task vào `check`/`build`; và task `publish` chỉ có ý nghĩa khi được plugin publishing khai báo. Spring Boot Gradle plugin cung cấp task như `bootJar`, còn Spring Boot Maven plugin dùng goal như `repackage`.

## 9. Chẩn đoán vấn đề theo phase thực tế

| Triệu chứng | Kiểm tra trước | Gợi ý xử lý |
| --- | --- | --- |
| Maven không đọc được project/POM | `validate`/project model | Kiểm tra XML, parent, cấu hình repository, plugin có được resolve |
| `invalid target release: 21` | `compile` và JDK | `mvn --version`, JDK mà Maven/Compiler sử dụng, `<java.version>` hoặc compiler release |
| `cannot find symbol` | `compile` | Lỗi source, imports, dependency compile classpath; chưa liên quan deploy |
| Unit test thất bại | `test` / Surefire | Xem `target/surefire-reports`, test name, stack trace |
| `mvn package` PASS nhưng không có executable JAR | `package` / Boot plugin | Kiểm tra `spring-boot-maven-plugin`, `repackage` binding, packaging, tên file trong `target` |
| `mvn package` PASS, `mvn verify` FAIL | `integration-test`/`verify` | Xem Failsafe/quality goals đã cấu hình và báo cáo cụ thể |
| `mvn install` FAIL | `install` / local repository | Kiểm tra quyền ghi, local repository path, dung lượng, artifact metadata |
| `mvn deploy` FAIL với 401/403 hoặc repository missing | `deploy` / publishing | Kiểm tra repository ID/URL, `settings.xml`, credential, quyền phát hành |
| `mvn deploy` PASS nhưng server chưa chạy phiên bản mới | Bước application deployment **ngoài Maven** | Kiểm tra CD pipeline, image/tag, rollout, runtime config |
| `java -jar` lỗi trên server | JVM/runtime/dependencies | Java version, cấu trúc JAR, biến môi trường, memory, database, port |

Một cách đọc log nhanh: tìm **plugin:goal** cuối cùng chạy trước lỗi. Ví dụ `maven-compiler-plugin:compile` chỉ sang build/Java; `maven-surefire-plugin:test` chỉ sang unit tests; `spring-boot-maven-plugin:repackage` chỉ sang đóng gói; `maven-deploy-plugin:deploy` chỉ sang publish artifact. Dòng `BUILD FAILURE` nói build thất bại nhưng không tự cho biết lớp nguyên nhân.

### Các cách bỏ qua test cần hiểu rõ

- `mvn -DskipTests package`: thường compile tests nhưng bỏ qua chạy Surefire/Failsafe tests; không dùng để khẳng định test PASS.
- `mvn -Dmaven.test.skip=true package`: trong các plugin hỗ trợ, còn bỏ qua biên dịch test sources.
- `mvn -Dtest=MessageServiceTest test`: chạy test cụ thể qua Surefire trong một lần điều tra; nó không chứng minh toàn bộ test suite PASS.

Bỏ qua test không giải quyết các lỗi ở `compile`/`repackage` và không thể thay thế `verify` trong quy trình release có kiểm soát.

## 10. Bài tập tự kiểm tra kết quả từng mốc

Với dự án mẫu:

1. Chạy `mvn clean compile`, kiểm tra `target/classes` và xác nhận chưa cần có JAR phân phối.
2. Chạy `mvn test`, quan sát `target/test-classes` và báo cáo Surefire; chủ động làm assertion sai để thấy failure ở test phase, rồi sửa lại.
3. Chạy `mvn package`, kiểm tra `target/lifecycle-demo-1.0.0.jar` và lệnh `jar tf`; giải thích vai trò `repackage`.
4. Cấu hình Failsafe và `ApplicationIT` rồi chạy `mvn verify`; so sánh với `package`.
5. Chạy `mvn install` nếu cần chia sẻ artifact trong local Maven repository, rồi tìm đường dẫn theo tọa độ `groupId:artifactId:version`.
6. **Chỉ trong môi trường publish được cấp quyền**, thử `mvn deploy` với remote repository hợp lệ; xác nhận artifact được xuất bản vào kho, sau đó mô tả bước CD riêng để chạy Spring Boot trên server.

Ba câu tự trả lời cuối bài:

- **Tại sao `mvn package` vẫn chạy unit test?** Vì Maven thực hiện các phase trước `package`, gồm `test`.
- **Tại sao `mvn verify` có thể chạy thêm integration test?** Vì có các phase integration-test ở giữa `package` và `verify`, nếu được bind với Failsafe/tác vụ tương ứng.
- **Tại sao `mvn deploy` thành công mà người dùng chưa thấy tính năng mới?** Vì Maven chỉ xuất bản artifact lên remote repository; chạy/rollout ứng dụng là trách nhiệm của bước triển khai runtime/CD.

## Tài liệu chính thức để đối chiếu

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): ba lifecycle, phase và plugin binding.
- [Apache Maven — Running Maven](https://maven.apache.org/run.html): cú pháp lệnh phase/goal và các mốc thường dùng.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): chạy integration tests và xác nhận ở `verify`.
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html): goal `repackage`, executable JAR/WAR và tương tác với Maven package.

