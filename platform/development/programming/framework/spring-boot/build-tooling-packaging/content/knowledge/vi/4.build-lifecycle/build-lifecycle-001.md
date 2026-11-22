# Mô hình phase và goal của Maven

Một lệnh như `mvn clean verify` trông ngắn gọn, nhưng bên dưới Maven thực hiện nhiều công việc: xóa đầu ra cũ, xử lý tài nguyên, biên dịch Java, chạy unit test, tạo JAR, chạy các kiểm tra bổ sung và xác nhận chất lượng. Để đọc đúng log hoặc thiết kế pipeline Spring Boot, cần phân biệt **lifecycle**, **phase**, **plugin**, **goal** và **execution binding**. Đây là mô hình điều phối tác vụ của Maven, không chỉ là danh sách câu lệnh.

**Mục tiêu học tập:** Sau bài này, bạn có thể (1) giải thích Maven chạy những gì khi gọi một phase; (2) phân biệt phase với goal được gọi trực tiếp; (3) xác định goal nào gắn vào phase nào qua `pom.xml`; (4) hiểu cách Spring Boot tạo executable JAR và cách đưa integration test vào `verify`; (5) chọn lệnh Maven phù hợp cho phát triển, CI và phát hành.

## 1. Năm khái niệm nền tảng

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Project/POM** | Mô tả tọa độ artifact, packaging, dependencies, plugins và cấu hình build | `pom.xml`, `groupId`, `artifactId`, `version` |
| **Lifecycle** | Chuỗi các giai đoạn chuẩn để xử lý một mục tiêu lớn | `default`, `clean`, `site` |
| **Phase** | Một mốc có thứ tự trong lifecycle; bản thân phase không chứa mã thực thi | `compile`, `test`, `package`, `verify` |
| **Plugin** | Thành phần hiện thực những tác vụ build cụ thể | `maven-compiler-plugin`, `maven-surefire-plugin` |
| **Goal** | Tác vụ có thể thực thi thuộc về một plugin | `compiler:compile`, `surefire:test`, `spring-boot:repackage` |

Mối quan hệ:

```text
POM + packaging + cấu hình/inheritance
                |
                v
      Lifecycle: default
                |
                v
       Phase: compile
                |
                v
  Plugin goal: compiler:compile
                |
                v
     target/classes/*.class
```

**Lifecycle là trình tự; phase là điểm trong trình tự; goal là việc thật sự được plugin thực hiện.** Một phase có thể gắn 0, 1 hoặc nhiều goal. Khi không có goal nào được gắn, Maven vẫn đi qua phase đó nhưng không có tác vụ phải chạy.

**Điểm dễ nhầm:** `compile` trong `mvn compile` là **phase**; `compile` trong `mvn compiler:compile` là **goal** của Compiler Plugin. Hai lệnh không tương đương về toàn bộ công việc: phase sẽ kích hoạt các goal đã gắn với mọi phase từ đầu vòng đời đến `compile`, còn gọi goal trực tiếp thường chỉ yêu cầu goal đó (và các điều kiện/phụ thuộc mà chính goal khai báo).

## 2. Maven có ba built-in lifecycle độc lập

| Lifecycle | Phase tiêu biểu | Công dụng |
| --- | --- | --- |
| **default** | `validate` → `compile` → `test` → `package` → `verify` → `install` → `deploy` | Xây dựng, kiểm thử và phân phối artifact |
| **clean** | `pre-clean` → `clean` → `post-clean` | Dọn kết quả build trước đó |
| **site** | `pre-site` → `site` → `post-site` → `site-deploy` | Sinh và xuất bản website tài liệu Maven |

Bảng trên rút gọn các phase của `default`; thực tế còn có nhiều phase trung gian như `process-resources`, `test-compile`, `integration-test`. Tên lifecycle **default** không có nghĩa Maven tự thực thi hết mọi phase sau khi mở project. Maven chỉ chạy khi nhận một phase/goal và dừng tại phase được yêu cầu.

`mvn clean` gọi phase `clean` thuộc **clean lifecycle**; nó không biên dịch hay test. `mvn site` gọi phase `site` thuộc **site lifecycle**; nó không tự tạo executable JAR. Khi chạy:

```bash
mvn clean verify
```

Maven thực hiện hai phần theo thứ tự: chạy clean lifecycle **đến phase `clean`**, rồi chạy default lifecycle **đến phase `verify`**. `post-clean` không tự động chạy chỉ vì bạn yêu cầu `clean`. Tương tự, `mvn verify` không tự dọn `target/` trước khi build; muốn dựng sạch thì chỉ rõ `clean`.

## 3. Default lifecycle: phase được gọi kéo theo mọi phase trước đó

Sơ đồ các mốc chính:

```text
validate → compile → test → package → verify → install → deploy
                     ^                ^
                     |                |
                 mvn test        mvn verify
```

Lệnh `mvn verify` thực hiện mọi phase trước `verify` theo đúng thứ tự. Nó **không** chạy `install` hoặc `deploy`. Ngược lại, `mvn deploy` sẽ đi qua cả `install` và `verify` trước khi xuất bản artifact ra kho từ xa.

Các phase quan trọng của `default` theo thứ tự:

| Phase | Ý nghĩa | Goal thường gặp với packaging `jar` |
| --- | --- | --- |
| `validate` | Kiểm tra mô hình và đầu vào dự án | Có thể không có goal mặc định |
| `initialize` / `generate-sources` | Khởi tạo trạng thái, sinh source nếu plugin được cấu hình | Tùy dự án |
| `process-resources` | Sao chép/xử lý `src/main/resources` | `resources:resources` |
| `compile` | Biên dịch `src/main/java` | `compiler:compile` |
| `process-test-resources` | Xử lý `src/test/resources` | `resources:testResources` |
| `test-compile` | Biên dịch `src/test/java` | `compiler:testCompile` |
| `test` | Chạy unit test theo quy tắc plugin test | `surefire:test` |
| `prepare-package` | Chuẩn bị trước đóng gói nếu có goal tùy chỉnh | Tùy dự án |
| `package` | Tạo JAR/WAR; Spring Boot có thể repackage | `jar:jar`, `spring-boot:repackage` |
| `pre-integration-test` | Chuẩn bị môi trường integration test | Tùy dự án |
| `integration-test` | Chạy integration test đã được cấu hình | `failsafe:integration-test` nếu có |
| `post-integration-test` | Dọn tài nguyên của integration test | Tùy dự án |
| `verify` | Xác nhận kết quả integration test và các quality gate khác | `failsafe:verify` nếu có |
| `install` | Cài artifact vào Maven repository cục bộ | `install:install` |
| `deploy` | Đẩy artifact lên Maven repository từ xa | `deploy:deploy` |

Các phase trung gian còn lại gồm `process-sources`, `generate-resources`, `process-classes`, `generate-test-sources`, `process-test-sources` và `process-test-classes`; chúng chỉ có việc để làm nếu có goal được gắn. Bảng mô tả **default bindings điển hình**, không bảo đảm mọi goal có mặt trong mọi dự án. Kiểu packaging, parent POM, plugin và executions có thể thay đổi kết quả.

Ví dụ lựa chọn lệnh theo mục tiêu:

| Lệnh | Maven sẽ đi đến đâu? | Chưa thực hiện |
| --- | --- | --- |
| `mvn validate` | Dừng ở `validate` | Compile, test, package |
| `mvn test` | Qua `test`, gồm compile + unit test | Package, integration-test, verify |
| `mvn package` | Qua `package`, gồm các phase trước | Failsafe integration test ở các phase sau |
| `mvn verify` | Qua `verify` | Install và deploy |
| `mvn install` | Qua `install` | Deploy từ xa |
| `mvn deploy` | Qua `deploy` | Triển khai ứng dụng lên máy chủ (đây là công việc riêng) |

Gọi `mvn compile test package` trong một dòng là dư thừa: gọi phase cuối `mvn package` đã đi qua các phase trước. Với CI, `mvn clean verify` thường là điểm khởi đầu tốt; những quality gate muốn có phải được cấu hình thực sự.

## 4. Goal được gắn vào phase như thế nào?

Maven xác định goal sẽ chạy nhờ hai nguồn chính:

1. **Default binding theo `packaging`** của project. Với `jar`, Maven tự gắn `compiler:compile` vào `compile`, `surefire:test` vào `test`, `jar:jar` vào `package`, cùng các goal resources/install/deploy phù hợp. Với `war`, phase `package` dùng goal tạo WAR; với `pom`, mô hình đóng gói khác.
2. **Plugin executions khai báo hoặc kế thừa trong POM.** Các execution có thể gắn thêm goal vào phase, cấu hình mục đích, thay đổi tham số hoặc thêm lần chạy. Khi nhiều goal cùng phase, binding mặc định theo packaging chạy trước các execution thêm từ POM; các execution từ POM tuân theo thứ tự cấu hình/effective model tương ứng.

Ví dụ một execution tự gắn goal của Checkstyle Plugin vào `verify`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-checkstyle-plugin</artifactId>
            <version>3.3.1</version>
            <executions>
                <execution>
                    <id>check-code-style</id>
                    <phase>verify</phase>
                    <goals>
                        <goal>check</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn cấu hình chèn vào phần `<project>` của POM**, không phải file POM độc lập. Khi `mvn verify` tới `verify`, Maven chạy goal `checkstyle:check` theo cấu hình này. Chỉ một lời gọi `mvn test` sẽ không chạy goal đó. Checkstyle cần bộ quy tắc phù hợp với dự án; đoạn XML minh họa **cơ chế binding**, không bảo đảm mọi codebase sẽ đạt kiểm tra style mặc định.

Trong một execution, phần tử `<goals>` chỉ ra tác vụ; `<phase>` nói khi nào chạy. Một số goal có **default phase** do plugin khai báo, nên execution có thể không cần chỉ định `<phase>`; nhưng để người đọc dễ kiểm tra, hãy khai báo phase rõ ràng khi cần kiểm soát vị trí. `<id>` giúp nhận diện execution trong log và khi kế thừa/override cấu hình.

### Plugin, pluginManagement và dependencyManagement khác nhau

- `<build><plugins>` kích hoạt/cấu hình plugin trong build hiện tại; với execution hợp lệ, plugin được chạy tại phase đã bind.
- `<build><pluginManagement>` cung cấp phiên bản/cấu hình mặc định cho plugin khi nó được dùng; **chỉ có pluginManagement thường chưa kích hoạt execution cho project con** nếu plugin chưa được áp dụng/không có binding tương ứng.
- `<dependencies>` quản lý thư viện dùng để compile/test/chạy ứng dụng. Thêm `spring-boot-starter-web` không đồng nghĩa Maven tự biết cách tạo executable Boot JAR.
- `<dependencyManagement>` quản lý phiên bản/thuộc tính dependency, không phải nơi điều khiển plugin goal.
- `<parent>` và profile có thể đưa vào plugin configurations/executions từ nơi khác. Vì vậy **POM hiệu lực (effective POM)** mới thể hiện đầy đủ sau kế thừa và kích hoạt profile.

Đừng khai báo trùng cùng plugin trong `<build><plugins>` để chạy nhiều goal; hãy dùng nhiều `<execution>` bên trong cùng một plugin.

## 5. Phase command và goal command: cùng tên nhưng khác nghĩa

Cú pháp Maven CLI phổ biến:

```text
mvn [options] [phase...] [plugin-prefix:goal...]
```

Ví dụ:

```bash
mvn compile
mvn compiler:compile
mvn dependency:tree
mvn clean package
mvn clean package dependency:tree
```

**`mvn compile`**: chạy default lifecycle đến `compile`, gồm `process-resources` và những goal đã gắn vào các phase trước. **`mvn compiler:compile`**: gọi trực tiếp một goal của Compiler Plugin; nó không mặc nhiên kích hoạt toàn bộ các phase trước `compile`. Vì vậy gọi trực tiếp goal thường phù hợp khi chẩn đoán hoặc thao tác có mục đích rõ, không phải cách thay thế tùy tiện cho lifecycle.

**`mvn dependency:tree`**: gọi goal `tree` của Maven Dependency Plugin để xem cây phụ thuộc; nó không phải phase trong lifecycle. Cách gọi rút gọn `plugin-prefix:goal` được Maven phân giải sang plugin tương ứng; cách gọi đầy đủ có dạng `groupId:artifactId:version:goal` khi cần kiểm soát chính xác plugin version.

**`mvn clean package dependency:tree`**: Maven thực hiện `clean`, default lifecycle đến `package`, rồi gọi `dependency:tree`. Thứ tự các đối số trên command line có ý nghĩa. Không cần gọi riêng `test` trước `package` vì `package` đã bao gồm `test` trong lifecycle.

Lưu ý: một số plugin goal tự khai báo việc yêu cầu project, xử lý dependency hoặc gọi phase trước khi chạy; không suy đoán rằng *mọi* direct goal đều có hành vi giống nhau. Đọc tài liệu goal và effective POM để xác định điều kiện thực tế.

## 6. Ví dụ chạy được: Maven phase/goal trong dự án Spring Boot

Dùng Java 17, Maven 3.9.x và Spring Boot 3.3.13. Các tệp tối thiểu:

```text
maven-phase-demo/
├── pom.xml
└── src/
    ├── main/java/dev/example/maven/
    │   └── MavenPhaseApplication.java
    └── test/java/dev/example/maven/
        └── MavenPhaseApplicationTest.java
```

Tạo `pom.xml` hoàn chỉnh:

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
    <artifactId>maven-phase-demo</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/dev/example/maven/MavenPhaseApplication.java`:

```java
package dev.example.maven;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class MavenPhaseApplication {
    public static void main(String[] args) {
        SpringApplication.run(MavenPhaseApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello Maven lifecycle";
    }
}
```

Tệp `src/test/java/dev/example/maven/MavenPhaseApplicationTest.java`:

```java
package dev.example.maven;

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
class MavenPhaseApplicationTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void returnsHello() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello Maven lifecycle"));
    }
}
```

Chạy các mốc độc lập (mỗi lệnh tự đi qua các phase cần thiết):

```bash
mvn -version
mvn clean test
mvn clean package
mvn clean verify
```

Trên máy có Maven Wrapper, thay `mvn` bằng `./mvnw` (Windows dùng `mvnw.cmd`). Mỗi lệnh `clean` sẽ xóa đầu ra build hiện có trước khi chạy phần tiếp theo. `mvn test` chạy test có tên hậu tố `Test` bằng Surefire; `mvn package` tạo `target/maven-phase-demo-1.0.0.jar` nếu thành công.

**Tại sao JAR này chạy được với `java -jar`?** `spring-boot-starter-parent` quản lý execution `repackage` và Spring Boot Maven Plugin được khai báo trong `<build><plugins>`. Khi `package` tạo JAR gốc, goal `spring-boot:repackage` đóng gói lại ứng dụng với Spring Boot loader và dependency runtime. Nếu không có cấu hình này, JAR thường do `jar:jar` tạo ra có thể không tự chạy bằng `java -jar`.

```bash
java -jar target/maven-phase-demo-1.0.0.jar
```

Trong terminal khác, khi ứng dụng đã khởi động:

```bash
curl -s http://localhost:8080/hello
```

Phần thân HTTP response mong đợi, đúng với controller và test:

```text
Hello Maven lifecycle
```

**Chú ý:** `spring-boot:repackage` thao tác trên JAR/WAR đã được tạo, nên nếu gọi trực tiếp trong dự án không có lifecycle binding thì phải chạy `mvn package spring-boot:repackage`, không chạy `spring-boot:repackage` trên thư mục chưa có artifact. Với POM ở ví dụ này, execution đã gắn vào `package` nên chỉ cần `mvn package`; không gọi goal `repackage` lần thứ hai.

## 7. Chèn integration test vào lifecycle đúng cách

Maven có các phase `pre-integration-test` → `integration-test` → `post-integration-test` → `verify`. **Tên phase không khiến integration test tự xuất hiện.** Cần cấu hình plugin hoặc framework test tương ứng. Với Maven, Surefire mặc định xử lý unit test ở `test`, còn Failsafe dành cho integration test và xác minh kết quả ở `verify`.

Bổ sung plugin sau vào **cùng danh sách `<build><plugins>` của POM ở mục 6** (không thay Spring Boot plugin):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.2.5</version>
    <executions>
        <execution>
            <id>integration-tests</id>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Hai goal trên có default phase tương ứng: `failsafe:integration-test` gắn vào `integration-test` và `failsafe:verify` vào `verify`. Tên lớp `*IT` được Failsafe chọn theo pattern mặc định. Ví dụ tạo `src/test/java/dev/example/maven/MavenPhaseApplicationIT.java`:

```java
package dev.example.maven;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MavenPhaseApplicationIT {
    @Autowired
    private TestRestTemplate restTemplate;

    @LocalServerPort
    private int port;

    @Test
    void servesHelloOverRealHttp() {
        ResponseEntity<String> response = restTemplate.getForEntity(
                "http://localhost:" + port + "/hello", String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("Hello Maven lifecycle", response.getBody());
    }
}
```

Chạy:

```bash
mvn clean verify
```

Trình tự: Surefire chạy `MavenPhaseApplicationTest` ở `test` → đóng gói ở `package` → Failsafe chạy `MavenPhaseApplicationIT` ở `integration-test` → goal `failsafe:verify` xác nhận kết quả và làm fail build nếu integration test không đạt. Kiểm tra báo cáo ở `target/surefire-reports/` và `target/failsafe-reports/`. Failsafe được thiết kế để ghi nhận lỗi integration test trước, cho phép các bước `post-integration-test` dọn tài nguyên rồi mới đánh fail ở `verify`.

**Không dừng lệnh ở `mvn integration-test` khi cần kết luận pass/fail cuối cùng.** Khi chỉ gọi phase này, `post-integration-test` và `verify` chưa chạy; môi trường test có thể chưa được giải phóng, và kết luận từ Failsafe chưa đầy đủ. Chọn `mvn verify`.

Trong ứng dụng thực tế, integration test sử dụng database/queue/container cần plugin hoặc công cụ chuẩn bị và thu dọn tương ứng; chỉ thêm Failsafe không tự khởi động những dịch vụ đó.

## 8. Đọc log để nhận biết phase và goal đang thực thi

Maven thường in các dòng goal như sau (rút gọn minh họa, **không phải log cố định**):

```text
--- maven-resources-plugin:...:resources (...) @ maven-phase-demo ---
--- maven-compiler-plugin:...:compile (...) @ maven-phase-demo ---
--- maven-resources-plugin:...:testResources (...) @ maven-phase-demo ---
--- maven-compiler-plugin:...:testCompile (...) @ maven-phase-demo ---
--- maven-surefire-plugin:...:test (...) @ maven-phase-demo ---
--- maven-jar-plugin:...:jar (...) @ maven-phase-demo ---
--- spring-boot-maven-plugin:...:repackage (...) @ maven-phase-demo ---
--- maven-failsafe-plugin:...:integration-test (...) @ maven-phase-demo ---
--- maven-failsafe-plugin:...:verify (...) @ maven-phase-demo ---
BUILD SUCCESS
```

Mỗi dòng cho biết **plugin**, **version thực tế** (ở đây viết `...`), **goal**, **execution id** và artifact/project. Bạn biết một goal có chạy thật hay không bằng log và báo cáo của plugin, không bằng tên phase một cách suy đoán.

Nếu chỉ chạy `mvn test`, log sẽ dừng trước `jar:jar`/`repackage`. Nếu không cấu hình Failsafe, log sẽ không có `failsafe:*` dù `mvn verify` vẫn có thể kết thúc `BUILD SUCCESS`. Với một dự án nhiều module, log còn chứa tên từng module và `Reactor Summary`; lỗi ở một module có thể khiến các module phụ thuộc không chạy.

Công cụ tự kiểm tra cấu hình:

```bash
mvn help:effective-pom
mvn help:active-profiles
mvn help:describe -Dplugin=compiler -Dgoal=compile -Ddetail
mvn dependency:tree
```

- `help:effective-pom`: xem POM sau khi Maven hợp nhất parent, profile, pluginManagement và các khai báo hiệu lực; dùng để tìm `<executions>` hoặc plugin version bị kế thừa.
- `help:active-profiles`: xác nhận profile đang bật.
- `help:describe`: đọc mô tả và tham số của goal.
- `dependency:tree`: đọc dependency graph. Nó không cho biết trực tiếp toàn bộ goal binding; hãy kết hợp effective POM với log.

Không chia sẻ nguyên vẹn debug log hoặc effective settings nếu chứa URL nội bộ, token hay thông tin nhạy cảm.

## 9. `packaging`, parent và profile ảnh hưởng đến kết quả build

Từ `<packaging>jar</packaging>`, Maven chọn bộ goal binding mặc định cho JAR. Chuyển sang `war` thay đổi goal ở `package` và cần cấu hình ứng dụng/dependency phù hợp cho môi trường servlet container. `<packaging>pom</packaging>` thường dùng làm parent/aggregator POM; nó không tự tạo application JAR.

Spring Boot thường có hai lớp đóng gói:

1. Maven JAR Plugin tạo JAR cơ sở theo lifecycle.
2. Spring Boot Maven Plugin với goal `repackage` tái đóng gói thành executable JAR/WAR có loader và runtime dependencies.

Việc thêm dependency Spring Boot **không tự tạo goal `repackage`**. Cần khai báo plugin và execution/binding tương ứng; với `spring-boot-starter-parent`, cấu hình `repackage` được cung cấp sẵn và plugin được khai báo như ví dụ ở trên.

Profiles có thể bật/tắt plugin, property, dependency hoặc repository, nên hai lệnh dùng profile khác nhau có thể kích hoạt khác tập goal. Ví dụ:

```bash
mvn -Pci clean verify
```

Chỉ dùng `-Pci` khi POM thực sự khai báo profile `ci` hoặc được kích hoạt theo một cơ chế hợp lệ. Nếu build trên CI phải có thêm quality gate, kiểm tra `effective-pom` và log với đúng profile để chắc chắn goal được bind.

## 10. Maven trong dự án nhiều module

Một root POM dạng `pom` có thể khai báo `<modules>` và tạo Maven reactor. Maven xác định thứ tự các module dựa trên quan hệ phụ thuộc giữa chúng để build đúng thứ tự. Ví dụ project có `common` và `web-app` phụ thuộc `common`:

```text
root-pom (packaging=pom)
├── common (packaging=jar)
└── web-app (packaging=jar, Spring Boot executable JAR)
```

Chạy từ root:

```bash
mvn clean verify
mvn -pl :web-app -am verify
```

Lệnh đầu áp dụng lifecycle tới các module trong reactor. Lệnh sau chọn module có artifactId `web-app` và bổ sung các module reactor mà nó phụ thuộc thông qua `-am`, như `common` (giả sử đúng quan hệ dependency). Phase/goal vẫn được xét theo POM và packaging của **từng module**, nên không phải module nào cũng tạo executable Boot JAR. Lựa chọn `-pl`/`-am` không thay thế nhu cầu publish/định danh artifact thật của module đích.

## 11. Chọn phase làm quality gate trong CI và phát hành

Một pipeline Maven thực dụng có thể phân các chặng như sau:

| Nhu cầu | Lệnh | Bằng chứng cần có |
| --- | --- | --- |
| Phát triển nhanh, kiểm tra Java/test | `mvn test` | Unit test pass, compile success |
| Build sạch và tạo artifact | `mvn clean package` | JAR/WAR đúng tên, unit test pass |
| Gate tổng hợp trước phát hành | `mvn clean verify` | Test + integration test + quality goals được cấu hình đều pass |
| Cài để module/dự án khác dùng cục bộ | `mvn install` | Artifact xuất hiện trong local Maven repository |
| Công bố lên Maven repository | `mvn deploy` | Đích repository hợp lệ, publish thành công và version truy vết được |

`mvn install` là **phase cài artifact vào kho local** (thường `~/.m2/repository`), không phải lệnh cài ứng dụng vào hệ điều hành. `mvn deploy` là **phase upload artifact lên Maven repository**, không phải lệnh đưa Spring Boot service lên Kubernetes/VM.

Để `deploy` làm việc với kho từ xa, cần cấu hình `<distributionManagement>` cho repository mục tiêu và cung cấp xác thực an toàn qua Maven settings/secret manager. Tránh hard-code mật khẩu/token trong POM. Nếu mục tiêu phát hành là OCI image/registry hoặc server/container runtime, bổ sung một quy trình publish và deploy riêng với artifact/image digest đã xác minh.

**Các tùy chọn bỏ kiểm tra có ảnh hưởng đến gate:**

- `-DskipTests` thường bỏ chạy test của Surefire trong khi vẫn biên dịch test.
- `-Dmaven.test.skip=true` còn bỏ qua biên dịch test đối với các plugin kiểm thử hỗ trợ thuộc tính này.
- Nếu dùng những cờ đó để kiểm tra chẩn đoán, đừng coi artifact là bản đã vượt quality gate. CI phát hành nên chạy chính sách test đầy đủ.

Pin phiên bản Maven, JDK, plugin, dependency và dùng Maven Wrapper khi có; bản build cần truy vết được đến Git commit, môi trường build và artifact version. Một phase báo `BUILD SUCCESS` chỉ khẳng định những goal **thực sự được bind** đã chạy thành công; nó không chứng minh rằng các kiểm tra chưa cấu hình cũng đã hoàn thành.

## 12. Lỗi phổ biến và cách tìm nguyên nhân

| Hiện tượng | Vì sao | Cách xử lý |
| --- | --- | --- |
| `mvn compiler:compile` thành công nhưng `mvn compile` lỗi | Phase kích hoạt thêm xử lý resources/sinh source hoặc goal khác | Xem log goal cụ thể thất bại; sửa cấu hình goal đó |
| `mvn package` vẫn tạo JAR dù chưa chạy integration test | Failsafe ở phase sau `package` hoặc chưa được bind | Cấu hình Failsafe, chạy `mvn verify` |
| `mvn verify` báo thành công nhưng không có report Failsafe | Chưa có execution Failsafe hoặc test không khớp pattern | Kiểm tra effective POM, tên `*IT` và `target/failsafe-reports/` |
| Gọi `mvn integration-test` để kiểm tra cuối | Chưa qua `post-integration-test`/`verify` | Dùng `mvn verify` để dọn môi trường và xác nhận kết quả |
| JAR có trong `target` nhưng `java -jar` báo thiếu main manifest/loader | Chưa có goal `repackage` hợp lệ | Khai báo Spring Boot Maven Plugin/execution, chạy `package` và kiểm tra manifest |
| Thêm plugin ở `pluginManagement` mà goal không chạy | Chưa kích hoạt plugin/execution ở build thực tế | Khai báo tại `<build><plugins>` hoặc cấu hình binding cần thiết |
| `mvn clean` xóa artifact mà không tạo lại | `clean` là lifecycle riêng | Gọi `mvn clean package` hoặc `mvn clean verify` |
| `mvn deploy` không đưa service lên server | Phase này xuất bản Maven artifact | Tạo giai đoạn application deployment riêng |
| Build local và CI chạy goal khác nhau | Maven/JDK, parent, profile, property, plugin version khác nhau | So sánh `mvn -version`, effective POM, active profiles và log |
| `mvn test -DskipTests` báo thành công nhưng test không chạy | Tùy chọn vô hiệu hóa test execution | Bỏ flag, kiểm tra số test thực chạy trong Surefire report |

## 13. Bài tập đọc lệnh và tự kiểm tra

**Tình huống A.** Mục tiêu là biên dịch, chạy unit test nhưng chưa cần JAR. Chọn `mvn test`. Maven tự qua `compile` và `test-compile` trước khi chạy goal Surefire.

**Tình huống B.** Muốn JAR Spring Boot chạy bằng `java -jar`, không cần publish. Chọn `mvn clean package` với `spring-boot-maven-plugin` đã bind `repackage`. Kiểm tra tệp trong `target/` và chạy thật artifact.

**Tình huống C.** Đã cấu hình Failsafe và cần toàn bộ kiểm tra trước release. Chọn `mvn clean verify`. Không chọn `mvn integration-test` vì thiếu phase dọn và kết luận kiểm thử cuối cùng.

**Tình huống D.** Developer nói “tôi chạy `mvn verify` thành công, vậy chắc chắn integration test đã chạy”. Nhận định **sai** nếu POM chưa bind plugin tương ứng. Đọc effective POM, log goal và report thay vì suy luận từ tên phase.

**Tình huống E.** Có người đề nghị `mvn deploy` để deploy HTTP service lên môi trường staging. Phải phân biệt: đây là pha **publish Maven repository**. Việc chạy ứng dụng trên staging cần workflow triển khai riêng tiêu thụ artifact đã xuất bản.

**Quy tắc nhớ:** *Gọi một phase* ⇒ Maven đi qua các phase trước đó của **cùng lifecycle**, chạy những goal đã bind. *Gọi một goal* ⇒ yêu cầu một tác vụ plugin cụ thể. Kết quả thực tế phụ thuộc vào `packaging`, parent/effective POM, profile, plugin execution và phiên bản công cụ.

### Tài liệu chính thức để đối chiếu

- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Running Apache Maven: https://maven.apache.org/run.html
- Maven — Guide to Configuring Plugins: https://maven.apache.org/guides/mini/guide-configuring-plugins.html
- Maven Surefire/Failsafe — Failsafe Plugin: https://maven.apache.org/surefire/maven-failsafe-plugin/
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html