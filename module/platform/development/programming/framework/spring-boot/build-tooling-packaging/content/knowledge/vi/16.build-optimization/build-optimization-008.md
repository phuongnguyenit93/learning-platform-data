# Giảm tác vụ không cần thiết mà vẫn giữ các bước kiểm tra bắt buộc

Một bản dựng Spring Boot nhanh **không phải** là bản dựng bỏ qua nhiều kiểm thử nhất. Mục tiêu đúng là **không thực hiện lại công việc đã có kết quả hợp lệ, không xây module không liên quan, không chạy bước nặng ở mọi lần chỉnh sửa**, đồng thời bảo đảm mọi thay đổi được đưa vào nhánh chính hoặc phát hành đều đi qua những **quality gates** mà dự án đã cam kết.

Ví dụ:

- Lập trình viên đang sửa một hàm Java có thể chạy đúng một unit test liên quan để nhận phản hồi nhanh.
- CI kiểm tra Pull Request vẫn phải chạy toàn bộ bộ kiểm thử **bắt buộc** cho phạm vi thay đổi theo chính sách, kể cả integration tests nếu đó là điều kiện merge.
- Build tool có thể **tái sử dụng output** của task từ lần chạy trước khi đầu vào không đổi; điều này khác về bản chất với việc dùng cờ **skip** làm biến mất bước xác minh.
- Một executable Spring Boot JAR phải được **đóng gói và kiểm tra** trước khi deploy; chạy unit test thành công trên classpath IDE không chứng minh JAR phát hành hoạt động.

Bài học thuộc chủ đề **Tối ưu bản dựng** của Spring Boot Build Tooling Packaging. Các ví dụ được cố định ở **Java 17, Spring Boot 3.3.13**, Maven 3.9.x và Gradle tương thích với Spring Boot 3.3. Đây là baseline học tập, không phải tuyên bố về các phiên bản mới nhất. Trọng tâm là các chiến lược áp dụng được lâu dài, không phụ thuộc một mẹo riêng của một bản plugin.

## 1. Phân biệt bỏ việc thừa và bỏ hàng rào chất lượng

Hãy xét một pipeline:

```text
Commit / Pull Request
        |
        v
Resolve dependencies + compile
        |
        v
Unit tests
        |
        v
Integration tests
        |
        v
Static / architecture / dependency checks (nếu được yêu cầu)
        |
        v
Package Spring Boot executable JAR
        |
        v
Archive inspection + artifact smoke test
        |
        v
Publish / deploy
```

Tối ưu đúng hướng sẽ hỏi:

1. **Bước nào được yêu cầu?** Những điều kiện nào phải pass trước khi merge, release hoặc deploy?
2. **Bước nào lặp lại không cần thiết?** Ví dụ chạy unit tests giống nhau hai lần liên tiếp mà không đổi input.
3. **Bước nào có thể chọn theo phạm vi?** Ví dụ một module thay đổi, không cần build tất cả module không liên quan.
4. **Bước nào có thể dùng cache?** Task deterministic có khai báo đầy đủ inputs/outputs.
5. **Bước nào không được thay bằng suy đoán?** Ví dụ integration test phụ thuộc database thực, security scan bắt buộc, kiểm chứng artifact để phát hành.

### Bảng đối chiếu chiến lược

| Kỹ thuật | Có giảm công việc không? | Có giữ chất lượng không? | Điều kiện |
| --- | --- | --- | --- |
| Maven `-pl :app -am` | Có, bỏ module không liên quan | Có thể | Reactor dependency graph đầy đủ; test của module không chọn phải được quản lý bằng policy |
| Gradle `:app:build` | Có, chỉ chọn task graph cần cho app | Có thể | Task dependencies và quality gates của app được nối đúng |
| Gradle `UP-TO-DATE` | Có | Có thể | Inputs/outputs được khai báo đúng, cache không bị ảnh hưởng bởi trạng thái ngoài |
| Gradle `FROM-CACHE` | Có | Có thể | Reuse output hợp lệ từ cache đáng tin, cùng effective inputs |
| Maven `mvn test` thay `mvn verify` khi sửa một hàm | Có | **Chỉ trong vòng lặp local** | Trước khi merge/release vẫn có gate `verify` |
| Maven `-DskipTests` trong release job | Có | **Không** | Bỏ qua unit tests; không được coi là QA pass |
| Maven `-Dmaven.test.skip=true` | Có | **Không** | Có thể bỏ cả compile test source, che lỗi test compilation |
| Gradle `build -x test` trong release job | Có | **Không** | Loại test task khỏi task graph |
| Để task test trả kết quả fail nhưng bỏ qua exit code | Có vẻ nhanh | **Không** | Pipeline có thể phát hành code chưa đạt |
| Chạy `bootJar` mà không có `check` rồi phát hành ngay | Có | **Không đủ** | `bootJar` là đóng gói, không thay bộ kiểm thử |

**Mệnh đề cốt lõi:** *Ít task hơn* không đồng nghĩa *bớt kiểm tra bắt buộc*. Việc tối ưu phải có **bản đồ từ yêu cầu chất lượng sang task/goal thực sự chạy**.

## 2. Định nghĩa quality gates trước khi tối ưu

Một dự án nên mô tả các mức kiểm tra rõ ràng. Chúng có thể khác nhau giữa local development, Pull Request và release, nhưng không được âm thầm bỏ qua một điều kiện mà chính sách coi là bắt buộc.

| Tầng | Mục tiêu | Ví dụ lệnh | Kết quả được phép kết luận |
| --- | --- | --- | --- |
| Local fast feedback | Xác định nhanh lỗi đang sửa | Maven chọn một unit test; Gradle `test --tests` | **Test được chọn** pass, chưa xác minh toàn dự án |
| Module verification | Xác nhận module và các phụ thuộc liên quan | Maven `-pl/-am verify`; Gradle `:module:build` | Các gate **được cấu hình** trong selected module/task graph đã pass |
| Required PR gate | Trước merge theo chính sách | Maven `verify`; Gradle `build` + custom checks | Unit/integration/static checks bắt buộc của phạm vi PR đã chạy/pass |
| Release validation | Kiểm tra artifact phát hành | Full required gate + `java -jar` smoke test + artifact scan | Artifact cụ thể đủ điều kiện phát hành theo policy |
| Production monitoring | Phát hiện lỗi môi trường thực | Health/metrics/logs/canary | Không thay thế build-time test; theo dõi sau deploy |

Những bước như SAST, dependency vulnerability scan, license check, Checkstyle, SpotBugs, JaCoCo coverage threshold, OpenAPI compatibility hoặc database migration validation **chỉ thực sự bắt buộc** khi được ghi trong policy và được cấu hình thành các job/task có status required. `mvn verify` hay `./gradlew build` **không tự chạy mọi công cụ kiểm tra trên đời** chỉ vì tên lifecycle nghe đầy đủ.

### Một quy tắc bảo vệ chất lượng

Nếu nhóm công bố “PR chỉ được merge khi unit tests, integration tests và static checks đều đạt”, pipeline phải bảo đảm:

- Mỗi loại kiểm tra có task/goal hoặc CI job cụ thể.
- Nếu kiểm tra fail, job trả **exit code khác 0**, không dùng `|| true` hoặc `ignoreFailures = true` để che lỗi.
- Nếu một test suite trống bất thường do cấu hình nhầm, hệ thống nên **fail** thay vì âm thầm báo không có test; tùy plugin cần bật `failIfNoTests`/`failOnNoMatchingTests`.
- Việc dùng cache phải có bằng chứng rằng output khớp inputs và không bị can thiệp.
- Chỉ sau khi các gate đạt mới publish/deploy **chính artifact được xác minh**.

## 3. Maven lifecycle: `test`, `package` và `verify` không giống nhau

Maven có build lifecycle theo phase, trong đó các phase thường liên quan bài này gồm:

```text
validate
   |
compile
   |
test-compile
   |
test          -> Surefire (nếu cấu hình và có test phù hợp)
   |
package       -> JAR/WAR Plugin; Spring Boot repackage (nếu cấu hình)
   |
integration-test  -> Failsafe integration-test (nếu được bind)
   |
verify        -> Failsafe verify và các checker khác (nếu được bind)
```

Khi gọi `mvn verify`, Maven chạy các phase trước đó theo thứ tự. Khi gọi `mvn test`, Maven dừng ở phase test, không đi tới package/integration-test/verify.

| Lệnh Maven | Thường thực hiện | Không được tự kết luận |
| --- | --- | --- |
| `mvn compile` | Biên dịch main source | Unit tests đã chạy |
| `mvn test` | Biên dịch source/test source, chạy unit tests theo Surefire | Integration tests, archive validation hoặc release gate đã đạt |
| `mvn package` | Tới package; có thể tạo executable JAR nếu plugin Boot được bind | Integration tests gắn sau package đã chạy |
| `mvn verify` | Toàn bộ lifecycle tới verify, gồm các plugin goals đã cấu hình | Mọi loại security/static scan tự tồn tại |
| `mvn clean verify` | Xóa build output cũ, thực hiện lại lifecycle | Luôn nhanh hơn; thực tế clean có thể làm mất lợi ích incremental |
| `mvn -pl :app -am verify` | Chọn app và upstream modules cần thiết trong reactor | Mọi module không chọn cũng đã kiểm tra |

**Cảnh báo Failsafe:** Khi dùng Maven Failsafe Plugin, phải bind **cả goal `integration-test` và `verify`**. Không lấy `mvn integration-test` thay cho `mvn verify` trong release pipeline: Failsafe thiết kế để xác nhận kết quả kiểm thử và trả lỗi build ở `verify`, sau khi các bước teardown ở lifecycle có cơ hội chạy.

## 4. Gradle task graph: `build`, `check`, `test` và `bootJar`

Với Java/Java Library plugin, các task lifecycle thường có quan hệ:

```text
build
├── assemble
│   └── jar / bootJar theo plugin và cấu hình
└── check
    ├── test
    ├── integrationTest   (chỉ khi bạn cấu hình dependsOn)
    └── staticChecks      (chỉ khi được plugin/task nối vào)
```

Gradle lập **task graph** từ những task đích bạn yêu cầu và những dependency task của chúng. Task không thuộc graph thường không được thực thi. Hệ thống có thể đánh dấu task `UP-TO-DATE` hoặc `FROM-CACHE` khi kết quả đủ điều kiện tái dùng.

- `./gradlew test`: tập trung vào task test, không mặc định tạo executable JAR.
- `./gradlew check`: chạy verification tasks được cấu hình nối vào `check`.
- `./gradlew bootJar`: tạo executable Spring Boot JAR nhưng **không mặc định bảo đảm mọi test bắt buộc đã chạy**.
- `./gradlew build`: chạy assemble + check của build model phù hợp; nó chỉ bao gồm integration tests nếu bạn nối vào `check` hoặc cơ chế verification tương đương.
- `./gradlew :catalog-app:build`: nhắm đúng subproject; những dependency tasks cần thiết ở module khác vẫn có thể chạy.

### Vì sao `-x test` nguy hiểm?

Gradle cho phép:

```bash
./gradlew build -x test
```

nhưng tài liệu chính thức khuyến cáo tránh lạm dụng `-x`: nó loại task đó và có thể loại cả những task chỉ phụ thuộc bởi task bị exclude khỏi graph. Vì thế build **có thể báo SUCCESS trong khi không chạy unit tests**.

Nếu bạn cần một đường **package-only** ở local, hãy định nghĩa lifecycle task đúng ý như `assemble` hoặc `bootJar` và **nói rõ đó chưa phải gate để merge/release**. Đừng dùng `-x test` trong một job được đặt tên “Full QA” rồi trình bày kết quả như đã test.

## 5. Ví dụ Spring Boot Java 17 có unit test và integration test tách biệt

Chúng ta dùng một ứng dụng nhỏ: `GET /ping` trả đúng `pong`. Hai bộ test kiểm tra những điều khác nhau:

- Unit test `GreetingServiceTest` gọi Java service trực tiếp, không cần Spring ApplicationContext.
- Integration test `PingEndpointIT` khởi động Spring Boot ở một **random HTTP port**, gọi HTTP thật và xác nhận body/status.

Chúng được cố ý đặt tên theo convention Maven Surefire (`*Test`) và Failsafe (`*IT`). Gradle sẽ khai báo test filters và hai task rõ ràng. **Nếu thiếu bước cấu hình integrationTest ở Gradle hoặc Failsafe ở Maven, `build`/`verify` có thể báo thành công nhưng không chạy IT — đó là chính lỗi mà bài muốn phòng ngừa.**

### 5.1. Cấu trúc source

```text
build-gates-demo/
├── pom.xml                         (chọn Maven)
├── settings.gradle                 (chọn Gradle)
├── build.gradle                    (chọn Gradle)
└── src/
    ├── main/java/dev/example/gates/
    │   ├── BuildGatesDemoApplication.java
    │   ├── GreetingService.java
    │   └── PingController.java
    └── test/java/dev/example/gates/
        ├── GreetingServiceTest.java
        └── PingEndpointIT.java
```

**Chỉ chọn một build definition cho phép thử:** dùng `pom.xml` khi học Maven, hoặc `settings.gradle` + `build.gradle` khi học Gradle. Không cần dùng cả hai build tools đồng thời trên cùng project.

### 5.2. Main class

`src/main/java/dev/example/gates/BuildGatesDemoApplication.java`:

```java
package dev.example.gates;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BuildGatesDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuildGatesDemoApplication.class, args);
    }
}
```

### 5.3. Service đơn giản

`src/main/java/dev/example/gates/GreetingService.java`:

```java
package dev.example.gates;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String message() {
        return "pong";
    }
}
```

### 5.4. Controller

`src/main/java/dev/example/gates/PingController.java`:

```java
package dev.example.gates;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    private final GreetingService service;

    public PingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/ping")
    public String ping() {
        return service.message();
    }
}
```

### 5.5. Unit test: không khởi động Spring

`src/test/java/dev/example/gates/GreetingServiceTest.java`:

```java
package dev.example.gates;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {

    @Test
    void messageIsPong() {
        GreetingService service = new GreetingService();
        assertEquals("pong", service.message());
    }
}
```

Nếu đổi kết quả từ `pong` sang `pang`, unit test fail nhanh mà không cần khởi động Tomcat. Đây là **fast feedback** lý tưởng khi đang sửa logic service.

### 5.6. Integration test: HTTP thật ở random port

`src/test/java/dev/example/gates/PingEndpointIT.java`:

```java
package dev.example.gates;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PingEndpointIT {

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void pingIsServedOverHttp() {
        ResponseEntity<String> response =
                restTemplate.getForEntity("/ping", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("pong", response.getBody());
    }
}
```

Random port giảm nguy cơ xung đột với app khác đang dùng 8080. Test xác nhận Spring context, controller mapping, embedded server và HTTP serialization. Nó vẫn **chưa phải smoke test của JAR đã đóng gói**, vì test runner dùng test/runtime classpath thay vì mở executable archive qua `java -jar`.

## 6. Maven: POM có quality gates được bind thật

`pom.xml` đầy đủ:

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
    <artifactId>build-gates-demo</artifactId>
    <version>1.0.0</version>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.4.1</version>
                <executions>
                    <execution>
                        <id>enforce-build-java</id>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Đọc POM theo chất lượng:

- **Enforcer:** chạy theo default phase `validate` của goal `enforce` được bind, fail khi Java đang dùng để build thấp hơn 17. Điều này không thay mọi rule phiên bản Maven/Dependency Convergence khác; những rule khác phải cấu hình riêng nếu policy yêu cầu.
- **Surefire 3.3.1:** chạy unit tests có tên đúng convention `*Test` ở phase `test`; `failIfNoTests=true` tránh việc project mẫu vô tình không có unit test mà vẫn qua gate.
- **Failsafe 3.3.1:** chạy `*IT` trong `integration-test` và xác nhận kết quả tại `verify`; `failIfNoTests=true` giúp phát hiện tình trạng integration suite trống.
- **Spring Boot Maven Plugin:** starter parent cung cấp execution `repackage` trong phase `package` khi plugin được khai báo, tạo executable JAR. Nó là **packaging**, không phải replacement cho tests.
- **Starter test:** cung cấp JUnit 5/TestRestTemplate và Spring testing support. Nó được dùng ở test scope, không đi vào runtime executable JAR.

Trong dự án thực, nếu có module **không có unit/IT**, không thể bật `failIfNoTests=true` bừa cho tất cả module rồi buộc mọi module viết test giả. Policy nên áp dụng gate theo loại module và yêu cầu thực tế. Ở ví dụ **đều có test** nên cấu hình này cố ý nghiêm ngặt và chạy được.

### 6.1. Phân biệt hai plugin test Maven

| Plugin | Convention mặc định liên quan ví dụ | Phase |
| --- | --- | --- |
| Maven Surefire | `GreetingServiceTest.java` (tên `*Test`) | `test` |
| Maven Failsafe | `PingEndpointIT.java` (tên `*IT`) | `integration-test` và `verify` |

Không cần chạy cả hai test trong `mvn test`: bài thiết kế fast feedback chỉ là Surefire ở phase test, còn verify/full gate bao gồm IT. Nếu nhóm muốn IT ở mọi lần PR, **required CI job phải gọi `verify`** và kiểm tra Failsafe reports, không chỉ `mvn test`.

### 6.2. Local nhanh nhưng không bỏ full gate của CI

Khi đang sửa một hàm trong `GreetingService`:

```bash
mvn -B -ntp -Dtest=GreetingServiceTest test
```

Lệnh này chạy unit test được chọn (đồng thời Maven chạy các phase cần trước test); chưa đi tới package/IT/verify. Nó **phù hợp vòng lặp local** chứ không phải tín hiệu phát hành.

Khi muốn chạy toàn bộ unit test mà không đóng gói:

```bash
mvn -B -ntp test
```

Khi chuẩn bị merge/release, chạy gate:

```bash
mvn -B -ntp clean verify
```

Với cấu hình POM mẫu, `verify` bao gồm Enforcer, biên dịch, Surefire, `repackage`, Failsafe integration-test và Failsafe verify. `clean` giúp baseline loại output cũ; trong vòng lặp local có thể bỏ `clean` để không hủy những tối ưu build hợp lệ.

### 6.3. Báo cáo test thật thay vì chỉ nhìn BUILD SUCCESS

Sau `mvn verify`, kiểm tra:

```text
target/surefire-reports/...
target/failsafe-reports/...
target/build-gates-demo-1.0.0.jar
```

Với project mẫu, cần có **ít nhất một unit test và một integration test** được phát hiện/chạy thành công. Xem test count, failures và skips trong logs/reports, không chỉ tên file. Nếu Failsafe không được bind, `mvn verify` **không tự đoán có test `*IT`** để chạy.

## 7. Những cờ skip của Maven và rủi ro với quality gates

**Không dùng các cờ dưới đây như giải pháp tối ưu mặc định cho required PR/release jobs.** Chúng phục vụ trường hợp có kiểm soát như build package tạm thời trong local.

| Cờ/lệnh | Tác động chính | Tác hại khi dùng sai |
| --- | --- | --- |
| `mvn -DskipTests package` | Thường bỏ chạy Surefire tests, nhưng vẫn compile test sources | Gói artifact không qua unit tests; ảnh hưởng Failsafe **phụ thuộc plugin/version và cấu hình** |
| `mvn -Dmaven.test.skip=true package` | Bỏ compile và chạy tests theo các plugin hỗ trợ flag | Có thể che cả lỗi biên dịch mã test |
| `mvn -DskipITs verify` | Failsafe bỏ integration tests khi phiên bản/plugin hỗ trợ | Không còn integration gate |
| `mvn -Dtest=GreetingServiceTest test` | Chọn test Surefire cần thiết | Không phải full test suite |
| `mvn package` | Không tự tới phase `integration-test`/`verify` | Release artifact chưa qua Failsafe gate |
| `mvn -DfailIfNoTests=false verify` | Có thể không fail dù suite cần chạy không có test | Che misconfiguration/missing tests |

**Chi tiết version-sensitive cần nhớ:** Maven Surefire thường gắn `-DskipTests` với việc bỏ chạy unit tests nhưng vẫn biên dịch tests; `-Dmaven.test.skip=true` còn được Compiler Plugin hỗ trợ để bỏ test compilation. Maven Failsafe **thay đổi binding của thuộc tính `skipTests` ở các phiên bản mới** (ví dụ từ Failsafe 3.6.0, property `-DskipTests` không còn có cùng ý nghĩa với Failsafe như các release trước). Vì vậy, với IT, dùng cờ chuyên biệt `-DskipITs` nếu thực sự muốn tạm skip và **đọc Failsafe logs theo version của dự án**. Đừng lập một quy tắc bất biến rằng `-DskipTests` luôn luôn skip mọi bộ test trong mọi version.

**Không gán mặc định `skipTests=true` trong parent POM chỉ để developer thấy build nhanh** nếu điều đó lan tới required CI. Thay vào đó hãy có hai command profiles/CI jobs tách biệt với nhãn rõ ràng: *local-fast* và *required-verification*. Release gate không được truyền cờ skip.

### Khi dùng Maven reactor để chỉ build phần liên quan

Trong một monorepo, cách chọn phạm vi là:

```bash
mvn -B -ntp -pl :catalog-app -am verify
```

Đây là **fragment chỉ áp dụng cho monorepo có module `catalog-app`**, không áp dụng trực tiếp vào project một module `build-gates-demo` ở trên. `-pl` chọn app; `-am` chọn các module upstream cần để build app, tránh build unrelated modules.

Tuy nhiên: những module **không được chọn** không có test chạy trong job ấy. Nếu policy yêu cầu kiểm tra tất cả modules trước merge/release, phải có một required job khác kiểm tra phần còn lại hoặc chạy full-reactor verification ở thời điểm phù hợp. Không được dùng `-pl` như cách “né” test module bị lỗi.

## 8. Gradle: cấu hình tách unit test và integration test nhưng giữ `build` là full gate

Dùng **cùng các tệp Java** ở mục 5. Thay POM bằng hai file Gradle sau.

`settings.gradle`:

```groovy
rootProject.name = 'build-gates-demo'
```

`build.gradle` (Groovy DSL):

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

tasks.named('test', Test) {
    useJUnitPlatform()
    filter {
        includeTestsMatching '*Test'
        failOnNoMatchingTests = true
    }
}

tasks.register('integrationTest', Test) {
    description = 'Run HTTP integration tests before verification is complete'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform()

    filter {
        includeTestsMatching '*IT'
        failOnNoMatchingTests = true
    }

    shouldRunAfter tasks.named('test')
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

**Vì sao cấu hình này giữ gate?**

1. `test` lọc những class kết thúc bằng `Test` — trong ví dụ là `GreetingServiceTest` — để phản hồi nhanh khi gọi riêng.
2. `integrationTest` dùng cùng compiled test source set nhưng lọc class `*IT` — trong ví dụ là `PingEndpointIT` — và dùng JUnit Platform. Đây là một task **mới**; không tự xuất hiện chỉ vì file tên `*IT.java`.
3. `check.dependsOn(integrationTest)` bảo đảm rằng `./gradlew check` và `./gradlew build` theo Java lifecycle **phải xử lý** integrationTest.
4. `failOnNoMatchingTests=true` khiến test filtering thất bại khi không khớp test theo cấu hình, thay vì im lặng “0 tests” trong ví dụ.
5. `shouldRunAfter test` thể hiện ưu tiên thứ tự khi cả hai task ở graph, **không** tự làm task test trở thành dependency của integrationTest. Việc cả hai được gọi ở `build` là nhờ `check` phụ thuộc `test` theo Java plugin và `integrationTest` theo cấu hình mới.
6. `bootJar` đóng executable JAR, nhưng không tự có trách nhiệm thay `check`.

Ở dự án thật, nếu IT cần runtime/data riêng, nên dùng **dedicated integrationTest source set/JVM test suite**, Docker/Testcontainers hoặc cấu hình test resources riêng. Ví dụ cố ý chia theo **class-name filter** để giữ trọn source tree và dễ kiểm tra logic quality gate. Khi mở rộng, phải quản lý classpath, test dependencies, CI services và cacheability của IT một cách explicit.

### Gradle commands: nhanh ở local, đầy đủ ở CI

Nếu dự án đã có Gradle Wrapper tương thích, trên Linux/macOS:

```bash
# Đúng một unit test khi đang sửa code:
./gradlew test --tests 'dev.example.gates.GreetingServiceTest'

# Toàn bộ unit tests:
./gradlew test

# Chạy riêng bộ IT:
./gradlew integrationTest

# Full verification gate: unit + integration:
./gradlew check

# Build: verification + executable archive:
./gradlew build
```

Windows dùng `gradlew.bat`. Với Gradle chưa có Wrapper, phải dùng phiên bản Gradle tương thích và quản lý trong build setup; không giả định file `gradlew` có sẵn.

Câu lệnh `./gradlew bootJar` phù hợp khi muốn kiểm tra nhanh phần **packaging**, nhưng **không thay `./gradlew build`** trong required CI. Với ví dụ trên, `./gradlew build` kéo cả `test` và `integrationTest` qua `check`.

### Quan sát task graph

```bash
./gradlew build --dry-run
./gradlew tasks --all
```

`--dry-run` cho thấy task dự kiến được thực thi nhưng **không tạo output và không chạy tests**. Nó là công cụ phân tích đồ thị, không phải bằng chứng QA. Với build thực, tìm những task:

```text
:test
:integrationTest
:check
:bootJar
:build
```

Thứ tự/tên hiển thị có thể khác theo Gradle version hoặc tùy chỉnh, nhưng các bước bắt buộc phải nằm trong graph hoặc có kết quả hợp lệ được tái sử dụng theo policy. Nếu `integrationTest` vắng mặt khi chạy `build`, kiểm tra `check.dependsOn(...)` và applied plugins.

## 9. Gradle UP-TO-DATE và build cache: giảm chạy lại, không bỏ gate

Gradle có nhiều lớp tối ưu khác nhau:

1. **Task avoidance:** task không thuộc selected graph thì không được lên lịch.
2. **Up-to-date checks:** khi task inputs/outputs được khai báo và kết quả output local vẫn hợp lệ, Gradle có thể báo `UP-TO-DATE`.
3. **Build cache:** khi task cacheable có cùng effective inputs, Gradle có thể tái sử dụng outputs từ local/remote cache và báo `FROM-CACHE`.
4. **Incremental compilation:** một số task/compilers làm ít công việc hơn khi chỉ một phần input thay đổi.
5. **Configuration cache:** lưu kết quả configuration phase khi build scripts/plugins tuân thủ yêu cầu; nó khác output cache của task.

Tình huống log:

```text
> Task :compileJava UP-TO-DATE
> Task :test FROM-CACHE
> Task :integrationTest
> Task :check
> Task :bootJar
BUILD SUCCESSFUL
```

Đây là **log minh họa**, không phải kết quả bảo đảm mọi máy: task có thể EXECUTED, NO-SOURCE, UP-TO-DATE, FROM-CACHE hoặc bị skip tùy trạng thái thực tế.

### 9.1. Bật build cache

Một lần chạy:

```bash
./gradlew build --build-cache
```

Hoặc cấu hình `gradle.properties`:

```properties
org.gradle.caching=true
```

**Không mặc định rằng mọi task đều cacheable.** Gradle chỉ cache khi task có đủ metadata về inputs/outputs và điều kiện cho phép; task tự viết đọc biến môi trường, thời gian, network hoặc secret không được khai báo có thể tạo kết quả cũ/sai.

### 9.2. Cache test có an toàn không?

Một test pure Java chỉ dựa trên source/dependencies và declared properties có thể phù hợp output cache. Nhưng **integration tests** thường liên quan database, Docker services, network APIs, time zone, current time, môi trường OS hoặc credential. Với loại này, cache hit có thể làm mất cơ hội phát hiện lỗi mới bên ngoài code.

Quy tắc:

- Chỉ cache test khi behavior thực sự **hermetic/deterministic** hoặc mọi inputs ngoài đều đã được khai báo.
- Không cache báo cáo scan/IT phụ thuộc dịch vụ bên ngoài mà chỉ gắn mỗi commit hash vào key.
- Xác nhận Gradle task được cache nhờ đúng inputs chứ không phải do custom task quên khai báo input.
- Nếu policy đòi **fresh integration execution** trên release, cấu hình task/CI để thực thi mới; không lấy cache làm bằng chứng môi trường production vẫn khỏe.
- Remote cache phải có trust model: ai được phép ghi, key bị poison hay không, có thông tin nhạy cảm trong outputs không.

Trong ví dụ `PingEndpointIT` chỉ mở HTTP server ở random local port và không gọi external service, nên phù hợp để học về input-based caching; không suy rộng thành mọi test tích hợp đều có thể bỏ chạy nhờ cache.

### 9.3. Khi nào cần ép chạy lại?

Dùng để **chẩn đoán**, không phải default trong vòng lặp tối ưu:

```bash
./gradlew check --rerun-tasks --no-build-cache
```

Lệnh này ép chạy các task trong graph thay vì dùng up-to-date/build-cache outputs. Nó có ích khi nghi cache hoặc task inputs bị khai báo sai, nhưng tăng thời gian; trong CI sạch có thể còn cần container/build cache policy riêng.

**Không chạy `clean` ở mọi lần save file**: `clean` xóa output, làm mất lợi ích incremental local. Với release baseline hoặc khi nghi output cũ, `clean build` giúp xác nhận từ trạng thái đã dọn.

## 10. Maven và Gradle: tối ưu cùng mục tiêu nhưng cơ chế khác nhau

| Tình huống | Maven | Gradle |
| --- | --- | --- |
| Chạy một unit test local | `mvn -Dtest=GreetingServiceTest test` | `./gradlew test --tests '*GreetingServiceTest'` |
| Chạy unit tests thôi | `mvn test` | `./gradlew test` |
| Bắt buộc cả unit + IT trong ví dụ | `mvn verify` khi Failsafe goals được bind | `./gradlew check` khi `integrationTest` phụ thuộc `check` |
| Bắt buộc có executable JAR và tests | `mvn verify` + artifact inspection | `./gradlew build` + artifact inspection |
| Chọn module/app trong monorepo | `mvn -pl :app -am verify` | `./gradlew :app:build` |
| Thăm dò work graph | `mvn help:effective-pom`, Reactor Summary/logs | `./gradlew build --dry-run` |
| Reuse output không đổi | Maven/plugin-specific, repository caching; không có task cache giống Gradle mặc định | `UP-TO-DATE` và `--build-cache` |
| Khi CI cần xây sạch | `mvn clean verify` | `./gradlew clean build` |
| Tránh cách tối ưu nguy hiểm | Đừng dùng `-DskipTests`/`-Dmaven.test.skip` ở required gate | Đừng dùng `-x test`/`enabled=false` ở required gate |

**Không mô tả Maven 3 như có Gradle build cache mặc định**. Maven có incremental/plugin optimizations, dependency caching và hệ sinh thái plugin/extension riêng; cách skip/reuse được điều khiển khác Gradle. Nếu một nhóm có Maven build-cache extension, phải đọc và xác thực tính đúng của extension đó; không giả định CLI `mvn verify` tự cache task outputs như Gradle.

## 11. Giảm thời gian bằng phân loại thay vì tắt task

Hướng tiếp cận nên ưu tiên theo thứ tự có ít rủi ro nhất:

### 11.1. Đo trước khi sửa

Trước khi chạy tối ưu, ghi ít nhất:

- Tổng thời gian build cold/warm.
- Thời gian compile, unit tests, integration tests, packaging, static checks.
- Số test đã chạy, pass/fail/skipped; số module/task đã xử lý.
- Cache hit/miss, remote repository downloads và container startup.
- JDK, Maven/Gradle/Boot plugin versions, CPU/RAM và môi trường CI.

Một số lệnh hữu ích:

```bash
# Maven:
mvn -B -ntp verify

# Gradle: báo cáo thời gian task tại local:
./gradlew build --profile
```

Gradle `--profile` tạo báo cáo profile cục bộ cho task/configuration, **không phải automatic release gate**. Maven có logs theo plugin/phase và có thể dùng profiling extensions hoặc CI timestamps; đừng gắn một con số cải thiện nếu chưa đo cùng input và môi trường.

### 11.2. Thu hẹp phạm vi đúng đồ thị phụ thuộc

Monorepo Maven:

```bash
mvn -B -ntp -pl :catalog-app -am verify
```

Monorepo Gradle:

```bash
./gradlew :catalog-app:build
```

Hai lệnh là **minh họa cho repository có module `catalog-app`**. Chúng chọn mục tiêu nhưng vẫn phải build upstream dependencies. Việc tiết kiệm đến từ **không chạy các module không liên quan**, không phải bỏ dependency có thật.

**Điều kiện QA:** nếu required PR policy vẫn yêu cầu kiểm tra những module bị tác động gián tiếp (downstream consumers), cần bổ sung job/selection phù hợp. Một thay đổi API ở module core có thể ảnh hưởng nhiều services, nên không thể chọn mỗi core và coi mọi consumer đã pass.

### 11.3. Không đóng gói lại khi chỉ cần test logic

Trong local dev:

- Maven `mvn test` dừng trước package.
- Gradle `./gradlew test` chỉ chạy task graph cần cho unit tests.
- Gradle `./gradlew classes` có thể đủ để xác minh compile main source nhưng **không** chạy test.

Sau đó, **full CI gate** vẫn phải tạo package, kiểm tra integration tests và release artifact nếu chính sách yêu cầu.

### 11.4. Tối ưu dependencies và annotation processing

- Tránh dependency trùng/không dùng đến, nhưng đừng tự xóa runtime library để làm JAR nhỏ nếu application cần nó.
- Đặt annotation processors trên đúng processor path; tránh để processor vô tình chạy vì nó nằm trong classpath thông thường.
- Khi code generation nặng, khai báo task inputs/outputs và generated sources đúng để Gradle incremental/build cache hoạt động an toàn.
- Không check-in generated sources bằng tay để “tránh build” nếu generator là phần quan trọng của quality/reproducibility; policy có thể khác cho contract được generate bên ngoài.
- Nếu Spring Boot `bootJar`/Maven `repackage` tạo archive lại khi dependencies thay đổi, đó có thể là **công việc cần thiết**; đừng disable đóng gói của release để lấy số thời gian đẹp.

### 11.5. Chỉ bật parallel khi test và plugins an toàn

Maven có tùy chọn build nhiều project song song trong reactor:

```bash
mvn -B -ntp -T 1C verify
```

Tùy chọn `-T 1C` yêu cầu mức concurrency gắn với CPU cores. Nó **không đảm bảo nhanh hơn** với repository một module; còn có thể làm nặng CPU/RAM, tăng lock/contention hoặc phát hiện plugin không thread-safe. Những tests tranh cùng cổng/database/shared filesystem có thể fail không ổn định. Chỉ dùng khi đã kiểm tra khả năng chạy song song, resource limits và log cảnh báo thread safety của Maven.

Gradle có thể bật parallel cho multi-project builds:

```properties
org.gradle.parallel=true
```

Nhưng vẫn phải bảo đảm tasks declare dependencies/outputs rõ ràng, tests không dùng shared mutable state và CI runner đủ tài nguyên. **Không đồng nhất parallelism với bỏ qua verification**: kết quả phải còn deterministic và các required tasks vẫn thuộc graph.

## 12. Tách local, PR và release thành ba “đường” rõ ràng

Thay vì một lệnh skip dùng khắp nơi, nên định nghĩa quy trình công khai:

### Local: ưu tiên vòng lặp ngắn

```bash
# Chọn một trong hai build tools.

# Maven: một test tập trung
mvn -B -ntp -Dtest=GreetingServiceTest test

# Gradle: một test tập trung
./gradlew test --tests 'dev.example.gates.GreetingServiceTest'
```

Lập trình viên **không** được trình bày trạng thái này như “full QA pass”. Nó chỉ cho biết tập con test đã chạy.

### Pull Request: đủ required quality gates

```bash
# Maven, POM mẫu với Failsafe được bind:
mvn -B -ntp verify

# Gradle, build.gradle mẫu với integrationTest -> check:
./gradlew build --build-cache
```

Đây là **hai lựa chọn thay thế**, không chạy cả Maven và Gradle cho một dự án nếu team không chủ đích duy trì hai build definitions.

Nếu có static analysis, license/security checks hoặc quality thresholds, nối chúng vào CI required jobs với status bắt buộc. Không giấu chúng đằng sau một profile “optional” mà PR pipeline không bật.

### Release: artifact đã test, chạy thử và chỉ publish khi pass

Ví dụ:

```bash
# Maven:
mvn -B -ntp clean verify

# Hoặc Gradle:
./gradlew clean build --build-cache
```

Sau build, kiểm tra đúng file:

```text
target/build-gates-demo-1.0.0.jar            (Maven)
build/libs/build-gates-demo-1.0.0.jar       (Gradle)
```

**Không cần thiết bắt buộc `clean` ở mọi PR** nếu runner sạch hoặc inputs được quản lý, nhưng release validation có thể chủ động chọn clean baseline để giảm rủi ro output cũ. Quyết định dựa trên môi trường và chính sách, không dựa vào cảm giác “clean luôn tốt hơn”.

## 13. Artifact inspection: test pass không có nghĩa JAR chạy được

Spring Boot executable JAR thường chứa:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/example/gates/BuildGatesDemoApplication.class
BOOT-INF/classes/dev/example/gates/GreetingService.class
BOOT-INF/classes/dev/example/gates/PingController.class
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/...
```

Trong đó `BOOT-INF/lib` chứa runtime dependencies, còn `BOOT-INF/classes` chứa app classes/resources. Spring Boot Loader dùng manifest `Main-Class` và `Start-Class` để tìm app main class khi `java -jar`.

Kiểm tra Maven artifact:

```bash
jar tf target/build-gates-demo-1.0.0.jar
unzip -p target/build-gates-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Với Gradle:

```bash
jar tf build/libs/build-gates-demo-1.0.0.jar
unzip -p build/libs/build-gates-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Manifest tiêu biểu trong Spring Boot 3.3:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.gates.BuildGatesDemoApplication
```

Đây là nội dung quan trọng cần tìm, không phải toàn bộ manifest. Chạy `jar tf` và đọc manifest giúp phát hiện deploy nhầm `-plain.jar` hoặc JAR chưa `repackage`.

**Tối ưu an toàn:** Không cần chạy một smoke test ở từng lần save file Java. Nhưng với release, một lần chạy chính executable JAR kèm HTTP probe có giá trị cao, vì nó kiểm tra packaging, loader, dependencies và runtime startup theo cách unit/IT test classpath chưa làm.

## 14. Smoke test độc lập cho chính executable JAR

Sau khi tất cả unit/integration tests và archive checks đã đạt, chạy artifact thật. Ví dụ local, dùng port 18080:

```bash
java -jar target/build-gates-demo-1.0.0.jar --server.port=18080
```

Nếu chọn Gradle, thay đường dẫn file bằng `build/libs/build-gates-demo-1.0.0.jar`. Ở **terminal thứ hai** khi Spring Boot đã startup:

```bash
curl -fsS http://localhost:18080/ping
```

Response body chính xác:

```text
pong
```

Đây là một smoke test trên archive đã đóng gói. Nó **không** thay toàn bộ integration tests hay production monitoring, nhưng bắt được lỗi thiếu dependency, sai main class, startup config hoặc deploy nhầm archive.

### Ví dụ shell gate có cleanup cho CI Linux

Đoạn này áp dụng **sau khi đã build Maven**; với Gradle thay biến `APP`. Runner cần `bash`, JDK và `curl`:

```bash
#!/usr/bin/env bash
set -euo pipefail

APP="target/build-gates-demo-1.0.0.jar"

java -jar "$APP" --server.port=18080 > boot-smoke.log 2>&1 &
pid=$!

trap 'kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true' EXIT

ready=0
response=""
for i in {1..30}; do
    if response=$(curl -fsS http://localhost:18080/ping 2>/dev/null); then
        ready=1
        break
    fi
    sleep 1
done

test "$ready" -eq 1
test "$response" = "pong"
echo "PASS: packaged Spring Boot JAR serves /ping"
```

Khi đạt, script in:

```text
PASS: packaged Spring Boot JAR serves /ping
```

Giới hạn: đây là script mẫu dùng cổng cố định 18080; trong shared CI runner cần đặt port/test isolation hợp lý. Một process khác không được trả lời nhầm endpoint. Một job release thực tế nên còn kiểm tra PID/process còn sống, artifact checksum, logs, timeout và phân vùng cổng. Script cố tình không để background process sống sau khi kết thúc vì có `trap` cleanup.

**Không chỉ chạy smoke test trên mã nguồn qua `spring-boot:run`/`bootRun`** khi mục tiêu là kiểm chứng artifact: những lệnh đó dùng classpath từ build output, không nhất thiết mở executable JAR đã phát hành.

## 15. Đo lường: tối ưu có thật hay chỉ bỏ kiểm tra?

Để so sánh trước/sau, lưu evidence cùng một baseline:

| Chỉ số | Điều cần ghi | Lý do |
| --- | --- | --- |
| Build duration | Tổng thời gian, cold/warm, cùng runner class | So sánh công bằng |
| Compile time | Main/test compilation | Phát hiện processor/generator nặng |
| Unit test count | Discovered/executed/pass/fail/skip | Đảm bảo không “tăng tốc” bằng chạy 0 tests |
| Integration test count | Discovered/executed/pass/fail/skip | Phát hiện IT biến mất khỏi lifecycle |
| Static/security jobs | Status và rule/scan version | Không mất required gates |
| Gradle task outcomes | `EXECUTED`, `UP-TO-DATE`, `FROM-CACHE` | Phân biệt reuse hợp lệ và skip |
| Maven reactor scope | Modules built vs unaffected modules | Kiểm soát selection |
| Artifact check | Manifest/`BOOT-INF`/checksum | Đảm bảo output deployable |
| Smoke test | Trạng thái startup và HTTP contract | Xác minh build artifact |

Ví dụ bảng kết quả minh họa (không phải số đo thực tế):

| Trước tối ưu | Sau tối ưu hợp lệ |
| --- | --- |
| Chạy full reactor dù chỉ sửa app | Targeted reactor/build đúng dependency graph |
| Build lại toàn bộ class và resources ở mỗi lần | Gradle reuse outputs khi inputs không đổi |
| Test suite có 12 test pass | Vẫn có 12 test pass khi required gate chạy |
| IT suite có 3 test pass | Vẫn có 3 test pass hoặc cache verified theo policy |
| Artifact smoke test pass | Artifact smoke test vẫn pass |
| Mọi bước được ghi nhận | Mọi bước được ghi nhận, chỉ giảm redundant work |

**Nếu số test từ 12 xuống 0 mà không có thay đổi policy, đó là sự suy giảm coverage của gate, không phải tối ưu hợp lệ.** Nếu một task từ EXECUTED thành FROM-CACHE, phải xác nhận cache trust/inputs rồi mới gọi đó là tiết kiệm hợp lệ.

## 16. Cách tránh bypass vô tình trong CI

### 16.1. Không che exit code

Không dùng:

```bash
mvn verify || true
./gradlew build || true
```

trong required validation. Các lệnh trên có thể khiến shell job trả success dù Maven/Gradle thất bại. Nếu CI cần luôn thu logs/reports sau lỗi, dùng cơ chế `finally`/`post` của CI hoặc script lưu exit code rồi trả lại nonzero một cách chính xác.

### 16.2. Không bỏ qua test failures

Trong Maven, đừng bật `maven.test.failure.ignore` để “tăng tỉ lệ xanh” của release job; trong Gradle, đừng đặt `ignoreFailures = true` cho các `Test` tasks bắt buộc. Những option này có thể làm báo cáo đẹp nhưng không đảm bảo chương trình đúng.

### 16.3. Không để suite trống ngoài ý muốn

Tình huống:

- Có cấu hình Failsafe nhưng đặt tên test `PingEndpointIntegration.java` không khớp default `*IT`.
- Có task `integrationTest` nhưng quên `check.dependsOn(integrationTest)`.
- Test nằm trong source set khác mà không được compile.
- Gradle dùng filter sai tên và báo không có test.

Biện pháp: đọc reports và test counts; áp dụng `failIfNoTests`/`failOnNoMatchingTests` theo module policy; thêm CI assertion về những gate phải chạy. **Nếu một project hợp lệ không có IT, đừng tạo test giả; hãy nói rõ lý do không áp dụng gate đó**.

### 16.4. Không dùng output của nhánh không đáng tin

Remote caches và shared artifacts có thể chứa mã, test reports và dependencies. Nếu job của fork/untrusted user được quyền **ghi** vào cùng cache tin cậy dùng để release, có nguy cơ cache poisoning. CI nên phân vùng quyền đọc/ghi cache và không đưa secrets vào untrusted PR jobs. Việc tái sử dụng build outputs phải bảo toàn tính xác thực, không chỉ tăng cache hit rate.

### 16.5. Không phát hành artifact khác artifact đã test

Nếu PR/release validation test file A nhưng deploy script build lại file B bằng khác Java version/profile/dependencies, evidence không còn đại diện. Hãy attach/publish **chính file đã qua gate**, kèm checksum hoặc digest và provenance. Với container image, xác minh image lấy đúng Boot JAR đầu vào.

## 17. Những tình huống Maven/Gradle cần quyết định khác nhau

**Tình huống A: Developer chỉ sửa `GreetingService.message()`.**

*Khuyến nghị:* Chạy một unit test cho phản hồi nhanh. Trước merge, required gate vẫn chạy đủ Surefire + Failsafe/Gradle `check` như chính sách.

**Tình huống B: PR chỉ sửa README hoặc tài liệu không liên quan code.**

*Khuyến nghị:* Có thể dùng change detection/path filters để tránh một số job nặng, **nếu** policy xác nhận thay đổi đó không thể ảnh hưởng build và các required checks vẫn có trạng thái hợp lệ. Build scripts, generated docs, API specs, Dockerfiles và release configs đôi khi nằm trong “docs” nhưng lại ảnh hưởng sản phẩm, nên không được bỏ qua bằng pattern quá rộng.

**Tình huống C: Một module core thay đổi API, app khác không sửa source.**

*Khuyến nghị:* Test downstream consumers theo dependency graph. Maven `-amd` hoặc Gradle task/project selection phù hợp có thể giúp chọn phạm vi; đừng chỉ test mỗi core vì compile contract của app có thể bị phá.

**Tình huống D: Gradle báo `:test FROM-CACHE`.**

*Khuyến nghị:* Nếu task cacheable và inputs đúng, đây có thể là reuse hợp lệ. Đọc cache policy và đối chiếu test reports; với integration tests tác động external system, cân nhắc yêu cầu fresh run.

**Tình huống E: Maven `mvn package` tạo Boot JAR thành công.**

*Khuyến nghị:* Không kết luận integration tests pass. Nếu Failsafe bind ở `integration-test`/`verify`, phải gọi `mvn verify` cho required gate. Cần artifact smoke test theo release policy.

**Tình huống F: Gradle `bootJar` nhanh hơn `build`.**

*Khuyến nghị:* Đúng vì `bootJar` không nhất thiết chạy `check`. Nó là packaging task, không phải full verification. Có thể dùng ở local, không thay release gate.

**Tình huống G: Maven dùng `-Dmaven.test.skip=true` để làm jar nhanh.**

*Khuyến nghị:* Nhận diện đây là bỏ cả test compilation theo cơ chế các plugin tương ứng. Không dùng trong release; thay bằng scoped/local test command nếu chỉ cần phản hồi nhanh.

**Tình huống H: Failsafe 3.6+ vẫn chạy IT dù dùng `-DskipTests`.**

*Giải thích:* Behavior đã thay đổi ở binding flag. Kiểm tra plugin version và logs; nếu tạm bỏ IT trong local thì dùng `-DskipITs`. Trên required gate, không dùng skip flag.

**Tình huống I: CI bật `--parallel`/`-T` và test trở nên flaky.**

*Khuyến nghị:* Kiểm tra test isolation, cổng, DB state, file locks, RAM, plugin thread-safety. Chỉ giữ parallel khi kết quả deterministic; đừng nuốt lỗi flaky.

**Tình huống J: IT test bị lỗi do database ngoài tạm ngắt.**

*Khuyến nghị:* Đây có thể là lỗi hạ tầng hoặc dependency contract, nhưng không nên biến nó thành green bằng skip vô thời hạn. Xây test environment ổn định, retry có giới hạn theo policy và lưu root cause. Required gate vẫn phải mang tín hiệu đúng về readiness.

## 18. Checklist trước khi chấp nhận tối ưu build

### Về phạm vi công việc

- Đã đo cold/warm baseline, không đưa ra con số “nhanh hơn” khi chưa đo.
- Chọn module/task theo dependency graph, không vô tình bỏ consumer bị ảnh hưởng.
- Không chạy lại những phase/task không cần ở local; cache/incremental được thiết lập và kiểm soát.
- Không lạm dụng `clean` khi chỉ cần fast feedback.
- Parallel được bật chỉ sau khi tests/plugins chứng minh an toàn.

### Về quality gates

- Unit tests bắt buộc có report/count và fail khi test lỗi.
- Integration tests bắt buộc được nối đúng vào Maven `verify`/Gradle `check` hoặc required CI job.
- Static/architecture/security/license checks nếu policy yêu cầu đều có status required rõ ràng.
- Các cờ `skipTests`, `maven.test.skip`, `skipITs`, `-x test` không xuất hiện trong command required gate.
- Không dùng `ignoreFailures`, `maven.test.failure.ignore`, `|| true` để che trạng thái đỏ.
- Cache có policy trust/inputs; critical external-state checks không bị bỏ lặng lẽ.
- Các test suites rỗng bất thường gây fail hoặc có ngoại lệ được phê duyệt.

### Về sản phẩm cuối

- Build tạo đúng **Spring Boot executable JAR**, không deploy nhầm plain JAR.
- Archive chứa main class, Boot loader, runtime dependencies; manifest hợp lệ.
- Thử `java -jar` trên đúng artifact với HTTP smoke test khi đến release gate.
- Chỉ publish/deploy artifact đã được xác minh, có version/digest và logs để truy vết.
- Không đánh đồng “build success” với “application đủ điều kiện chạy production”.

**Kết luận:** Giảm tác vụ không cần thiết bằng **targeted scope, task dependency đúng, incremental/up-to-date/build cache, fast local test selection và loại bỏ công việc lặp**. Giữ chất lượng bằng **đường required verification rõ ràng**: Maven `verify` với Surefire/Failsafe được bind hoặc Gradle `build` với `check` nối đủ test tasks, cùng các kiểm tra tĩnh/bảo mật được policy yêu cầu và smoke test trên executable artifact. **Tối ưu là tránh chạy lại công việc không cần, không phải tạo ra bản dựng xanh bằng cách không chạy kiểm tra.**

### Tài liệu tham khảo chính thức

- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Working with Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Maven Surefire 3.3.1 — Skipping Tests: https://maven.apache.org/components/surefire-archives/surefire-3.3.1/maven-surefire-plugin/examples/skipping-tests.html
- Maven Failsafe 3.3.1 — Usage: https://maven.apache.org/components/surefire-archives/surefire-3.3.1/maven-failsafe-plugin/usage.html
- Maven Failsafe — Integration Test Goal: https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html
- Gradle — Controlling Task Execution: https://docs.gradle.org/current/userguide/controlling_task_execution.html
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
- Spring Boot 3.3 — Maven Plugin Packaging: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin Packaging: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html