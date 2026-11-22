# Vì sao nên kết thúc chuỗi kiểm chứng bằng verify trong Maven

Trong dự án Maven có **kiểm thử tích hợp (integration test)**, câu hỏi quan trọng không chỉ là “test đã chạy chưa?” mà còn là “hệ thống đã được dọn dẹp chưa, kết quả test đã được đánh giá chưa, và build có thật sự đủ điều kiện để phát hành không?”.

Với Maven 3, **`mvn verify` là điểm kết thúc phù hợp cho chuỗi kiểm chứng tích hợp** vì nó chạy các phase trước đó theo đúng thứ tự:

```text
validate → compile → test → package
        → pre-integration-test
        → integration-test
        → post-integration-test
        → verify
```

Khi sử dụng **Maven Failsafe Plugin** đúng cách, goal `failsafe:integration-test` thực hiện integration tests và **ghi nhận lỗi test mà không dừng build ngay vì test assertion thất bại**. Nhờ đó `post-integration-test` vẫn có cơ hội dọn container, fixture hoặc dịch vụ thử nghiệm. Sau cùng, goal **`failsafe:verify` đọc kết quả đã ghi và quyết định build PASS/FAIL**. Nếu chỉ gọi `mvn integration-test`, Maven 3 dừng trước `post-integration-test` và `verify`, dễ để lại tài nguyên và chưa áp dụng kết luận chất lượng cuối cùng.

**Thông điệp cốt lõi:** `verify` không phải một phép kiểm thử khác do Maven tự tạo ra. Nó là **mốc lifecycle sau integration-test và cleanup**; chỉ những goal/quality gates được ràng buộc vào lifecycle mới chạy. Cần cấu hình Failsafe và các bước kiểm chứng một cách tường minh.

Bài học dùng Maven 3.9.x, Java 17, Maven Failsafe Plugin 3.5.2, Surefire Plugin 3.5.2 và Maven Antrun Plugin 3.1.0 để minh họa một build có setup, integration test, teardown và kiểm tra kết quả. Ở phần cuối có lưu ý khác biệt với Maven 4.

## 1. Phân biệt test, package, integration-test và verify

Maven có ba lifecycle chuẩn: `default`, `clean` và `site`. Các phase `test`, `package`, `integration-test` và `verify` nằm trong **default lifecycle**. `clean` thuộc clean lifecycle riêng, vì vậy lệnh `mvn clean verify` nghĩa là thực hiện clean trước, sau đó chạy default lifecycle đến verify.

| Lệnh | Kết thúc ở phase | Những việc có thể đã chạy | Những việc chưa chắc đã chạy |
| --- | --- | --- | --- |
| `mvn test` | `test` | Compile main/test và unit tests qua Surefire theo binding | Chưa đóng gói, chưa integration test/cleanup/verify |
| `mvn package` | `package` | Unit tests, JAR/WAR packaging | Chưa đến pre-integration-test và Failsafe |
| `mvn integration-test` | `integration-test` | Các phase trước, setup, integration tests nếu đã bind | **Chưa đến post-integration-test và verify** trong Maven 3 |
| `mvn verify` | `verify` | Packaging, setup, integration tests, cleanup, kiểm tra kết quả nếu các goal đã bind | Không tự deploy/install, không tự sinh các quality gates chưa cấu hình |
| `mvn install` | `install` | Đi qua verify trước khi install | Không tự đưa artifact lên remote repository |
| `mvn deploy` | `deploy` | Đi qua verify/install trước khi deploy | Không tự khắc phục lỗi hoặc bypass quality gates, trừ khi bị cấu hình skip |

**Maven thực thi tất cả phase trước phase đích theo thứ tự**, không chỉ phase được nhập. Nhưng việc một phase tồn tại **không đồng nghĩa có goal được bind vào phase đó**. Ví dụ, với project JAR tiêu chuẩn, Surefire thường được bind vào `test`; còn **Failsafe không được tự động bind vào tất cả project** chỉ vì Maven có phase `integration-test`. Cần khai báo executions của Failsafe.

### 1.1. Lệnh mvn verify có bao gồm mvn test và mvn package không?

Có, theo thứ tự default lifecycle. Khi chạy:

```bash
mvn -B verify
```

Maven đi qua `validate`, `compile`, `test`, `package`, các integration-test phases và `verify`. Nếu những goal có binding hợp lệ, chúng được chạy khi tới phase của mình.

**Nhưng không phải mọi project đều chạy integration tests.** Một project chưa cấu hình Failsafe hoặc một plugin kiểm thử khác tại `integration-test` có thể `BUILD SUCCESS` với `mvn verify` dù **chưa có một integration test nào được chạy**. Đây là lỗi nhận thức thường gặp nhất khi người học cho rằng “verify là một nút tự động chạy đủ mọi loại test”.

### 1.2. Vì sao package chưa đủ?

`package` chứng minh Maven đã tới bước tạo artifact phân phối (JAR/WAR...) nếu packaging và build hợp lệ. Nó chưa kiểm tra chắc chắn ứng dụng hoạt động khi tương tác với filesystem, service khác, DB hoặc artifact đã đóng gói.

Ví dụ một JAR có thể compile và package thành công nhưng integration test phát hiện lỗi đọc cấu hình đã được deploy, lỗi serialization, HTTP contract hoặc migration script. Muốn dùng kết quả đó làm **release gate**, cần đến phases kiểm chứng tương ứng, thường là `verify`.

## 2. Chuỗi bốn phase dành cho kiểm thử tích hợp

Theo Apache Maven Build Lifecycle và Maven Failsafe:

| Phase | Trách nhiệm điển hình | Plugin/goal có thể gắn |
| --- | --- | --- |
| `pre-integration-test` | Khởi động dependency, chuẩn bị DB, tạo test fixture, deploy app vào container | Antrun, Cargo, Docker orchestration, script chuẩn bị |
| `integration-test` | Gọi test để kiểm tra hoạt động xuyên thành phần | `failsafe:integration-test` |
| `post-integration-test` | Dừng container, thu thập log/coverage, xóa fixture, trả môi trường về trạng thái sạch | Antrun, plugin cleanup, teardown goal |
| `verify` | Đọc kết quả test đã được lưu; quyết định pass/fail; chạy additional validation gates được bind | `failsafe:verify`, các quality plugins khác |

**Thứ tự** là điểm quan trọng. Không nên chuyển bước cleanup lên trước Failsafe test; cũng không nên để một plugin trực tiếp fail build ngay ở `integration-test` vì test assertion nếu mục tiêu là luôn cho `post-integration-test` có cơ hội chạy.

Một minh họa:

```text
[pre-IT]      tạo /target/it-fixture/status.txt = "ready"
     |
[integration] test đọc fixture và xác thực trạng thái
     |         (nếu assertion fail, Failsafe ghi kết quả)
     v
[post-IT]     xóa /target/it-fixture
     |
[verify]      đọc failsafe-summary.xml
               ├─ 0 failure/error → BUILD SUCCESS (nếu các gate khác đạt)
               └─ failure/error   → BUILD FAILURE
```

Tệp `failsafe-summary.xml` chứa tổng hợp kết quả để goal `verify` xử lý. Nó không phải tệp “xác minh Maven core” tự có ở mọi project; đây là một phần cơ chế của Maven Failsafe Plugin.

### 2.1. Vì sao không chỉ chạy integration-test?

Trong **Maven 3**, khi gọi trực tiếp:

```bash
mvn integration-test
```

Maven dừng ở **phase integration-test**. Các goals gắn với `post-integration-test` và `verify` **chưa được thực thi**. Nếu pre-phase đã bật database, container hoặc test server, chúng có thể tiếp tục chạy. Nếu integration-test có assertions thất bại được Failsafe trì hoãn, lệnh trực tiếp này cũng không có điểm kiểm tra cuối để biến kết quả đó thành một build failure đáng tin.

Do đó, với workflow setup → IT → cleanup → đánh giá, **ưu tiên `mvn verify` hoặc `mvn clean verify`** thay vì gọi đến `integration-test` như mốc cuối.

### 2.2. Vì sao không chạy Surefire tại integration-test?

Surefire được thiết kế chủ yếu cho unit tests, thường chạy tại `test` và fail build khi gặp test failure (trừ khi có cấu hình bỏ qua). Nếu cố gắn goal `surefire:test` ở `integration-test`, failure có thể làm Maven **ngừng ngay** trước `post-integration-test`, để lại môi trường chưa dọn.

Failsafe được thiết kế tách:

- **`failsafe:integration-test`:** chạy tests và ghi kết quả, trì hoãn fail build khi test assertion/error thông thường;
- **`failsafe:verify`:** đọc kết quả, fail build nếu integration tests không đạt.

Cơ chế đó là lý do tên *Failsafe*: xử lý lỗi kiểm thử tích hợp sao cho cleanup vẫn có thể diễn ra.

**Giới hạn quan trọng:** điều này **không biến Maven thành hệ thống try/finally tuyệt đối**. Nếu setup plugin lỗi nghiêm trọng, Java process bị kill, VM mất điện, plugin ném lỗi ngoài cơ chế ghi nhận test failure, hoặc CI runner mất kết nối, Maven có thể không chạy được post-phase. CI/provisioning vẫn cần cleanup độc lập (job finally, container TTL, lifecycle quản lý hạ tầng) cho tài nguyên quan trọng.

## 3. Failsafe cần được bind vào hai goals, không chỉ một

Trong POM, cấu hình tối thiểu quan trọng là:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <executions>
        <execution>
            <id>run-integration-tests</id>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn plugin đặt trong `<build><plugins>` của POM**, không phải file POM độc lập.

Theo metadata goal của Failsafe:

- `integration-test` có default phase là `integration-test`;
- `verify` có default phase là `verify`.

Khai cả hai goals trong execution giúp `mvn verify` thực thi cả chạy test và chấm kết quả. Khi cần minh bạch, có thể tách thành hai executions và khai báo phase tường minh cho mỗi goal; tuy nhiên **không đặt cả hai goal cùng phase `integration-test`** vì sẽ mất lợi ích trì hoãn đánh giá sau cleanup.

### 3.1. Điều gì xảy ra nếu chỉ khai integration-test?

Ví dụ cấu hình sai ý định:

```xml
<executions>
    <execution>
        <goals>
            <goal>integration-test</goal>
        </goals>
    </execution>
</executions>
```

Đoạn này có thể chạy integration tests và tạo reports, nhưng **không có goal `failsafe:verify` để kiểm tra tổng kết ở phase verify**. Nếu test assertion fail và goal integration-test trì hoãn failure đúng thiết kế, build có nguy cơ vẫn được xem là thành công vì **không ai chốt kết quả cuối**.

### 3.2. Điều gì xảy ra nếu chỉ khai verify?

Khi chỉ chạy `failsafe:verify` nhưng chưa có `failsafe:integration-test` tạo summary file trong cùng build, kiểm tra có thể không phản ánh test run mong muốn hoặc cho kết quả thiếu dữ liệu tùy cấu hình. Đừng dùng nó làm bằng chứng đã chạy integration tests.

Quy tắc an toàn là **hai goal đi cùng nhau**, kết hợp một chính sách phát hiện “không có integration test nào được chạy”.

### 3.3. failIfNoTests để tránh build xanh giả

Failsafe có tham số `failIfNoTests`, mặc định thường là `false`. Đối với module **bắt buộc phải có integration tests**, có thể đặt:

```xml
<configuration>
    <failIfNoTests>true</failIfNoTests>
</configuration>
```

Nếu project chỉ là library phụ trợ không có `*IT.java`, cấu hình này ở parent cho mọi module có thể làm reactor fail ngoài ý muốn. Hãy đặt quality gate **ở module được yêu cầu có IT**, và kiểm tra reports thay vì giả định mọi module có cùng vai trò.

## 4. Quy ước đặt tên unit tests và integration tests

Maven Surefire và Failsafe quét các lớp test theo những mẫu khác nhau.

| Plugin | Các mẫu thường gặp | Mục tiêu |
| --- | --- | --- |
| Surefire | `**/Test*.java`, `**/*Test.java`, `**/*Tests.java`, `**/*TestCase.java` | Unit tests tại phase `test` |
| Failsafe | `**/IT*.java`, `**/*IT.java`, `**/*ITCase.java` | Integration tests tại phase `integration-test` |

Hai plugin thường dùng cùng nguồn test `src/test/java` và compiler output `target/test-classes`, nhưng **phân loại lớp chạy theo tên và cấu hình plugin**, không theo việc chúng nằm ở hai source folders mặc định tách biệt.

Ví dụ:

```text
src/test/java/vn/example/verify/StatusServiceTest.java  # Surefire
src/test/java/vn/example/verify/StatusServiceIT.java    # Failsafe
```

Nếu đặt integration test tên `DatabaseIntegrationTest.java`, nó có thể lọt Surefire vì suffix `*Test`. Khi đó test kết nối DB có thể chạy sớm ở phase `test` trước khi `pre-integration-test` tạo môi trường, dẫn đến lỗi sai thời điểm. Nên giữ quy ước `*IT` cho integration tests hoặc cấu hình include/exclude chủ động.

Dùng `@Tag("integration")` trong JUnit Jupiter **không tự chuyển test tới phase `integration-test`**: tag chỉ là nhãn framework và cần bộ lọc tương ứng.

## 5. Ví dụ thực hành Java 17: setup fixture → IT → cleanup → verify

Đây là bài thực hành hoàn chỉnh với **một Maven project JAR**. Ta dùng file fixture tạm để mô phỏng một tài nguyên được provision cho integration test, thay vì yêu cầu database hay container ngoài. Điều này giúp ví dụ chạy được trên máy không có Docker; cùng nguyên lý áp dụng khi thay fixture bằng server/database thật.

**Mục tiêu quan sát được:**

1. `maven-antrun-plugin` tạo file `target/it-fixture/status.txt` ở `pre-integration-test`.
2. `maven-failsafe-plugin:integration-test` chạy JUnit Jupiter `StatusServiceIT` để đọc fixture và kiểm tra logic sản phẩm.
3. `maven-antrun-plugin` xóa thư mục fixture ở `post-integration-test`.
4. `maven-failsafe-plugin:verify` chốt trạng thái pass/fail từ summary.
5. Với test cố tình fail, ta vẫn kỳ vọng **cleanup đã thực hiện trước khi build báo FAIL ở verify**.
6. Lệnh chạy Java từ JAR in stdout chính xác `Status=READY`.

Yêu cầu: **JDK 17+**, Maven 3.9.x, có thể tải plugins/JUnit từ repository được cấu hình (hoặc đã cache đầy đủ); project không yêu cầu internet khi chạy Java main sau build.

### 5.1. Cấu trúc thư mục

```text
verify-lifecycle-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/verify/
    │   ├── App.java
    │   └── StatusService.java
    └── test/java/vn/example/verify/
        ├── StatusServiceTest.java
        └── StatusServiceIT.java

# Sau mvn verify:
target/
├── verify-lifecycle-demo-1.0.0.jar
├── surefire-reports/
└── failsafe-reports/
    ├── failsafe-summary.xml
    └── TEST-vn.example.verify.StatusServiceIT.xml

# target/it-fixture/ đã bị xóa bởi post-integration-test
```

Sơ đồ các tệp trong `target` là **những file tiêu biểu cần tìm**, không phải danh sách bắt buộc/đầy đủ mọi file. Các plugin còn tạo `classes`, `test-classes`, metadata và log.

### 5.2. POM hoàn chỉnh

File `verify-lifecycle-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>verify-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <it.expected>Status=READY</it.expected>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>prepare-it-fixture</id>
                        <phase>pre-integration-test</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/it-fixture"/>
                                <echo file="${project.build.directory}/it-fixture/status.txt"
                                      message="ready"/>
                            </target>
                        </configuration>
                    </execution>
                    <execution>
                        <id>cleanup-it-fixture</id>
                        <phase>post-integration-test</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <delete dir="${project.build.directory}/it-fixture"
                                        quiet="true"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.2</version>
                <executions>
                    <execution>
                        <id>check-integration-tests</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <includes>
                        <include>**/*IT.java</include>
                    </includes>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <it.fixture.path>${project.build.directory}/it-fixture/status.txt</it.fixture.path>
                        <it.expected>${it.expected}</it.expected>
                    </systemPropertyVariables>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tại sao POM này có chủ ý như vậy?**

- `maven-compiler-plugin` đặt Java release 17 để project dùng JDK17+ mà tạo class-file Java17.
- `junit-jupiter:5.11.0` ở scope `test` nên không cần có trong runtime JAR.
- Surefire chạy test `StatusServiceTest` ở phase `test`; class `StatusServiceIT` không khớp suffix mặc định `*Test`, nên dành cho Failsafe.
- Antrun có **hai executions độc lập** được bind vào `pre-integration-test` và `post-integration-test`.
- `<mkdir>` và `<echo>` dùng Ant tasks để tạo file fixture; `<delete>` dọn thư mục sau khi integration test hoàn tất.
- Failsafe có **cả hai goals** `integration-test` và `verify`, được Maven bind vào default phases của từng goal theo metadata.
- `systemPropertyVariables` đưa đường dẫn file fixture và expected result tới **test JVM**. Nó không biến chúng thành biến môi trường của mọi process.
- `failIfNoTests=true` buộc module kiểm thử tích hợp này không âm thầm thành công khi thiếu `*IT`.
- Property `it.expected` ở POM cho phép tạo một lượt test sai có chủ ý qua CLI `-Dit.expected=Status=WRONG` mà không cần sửa mã Java.

**Không đặt JAR Plugin ở `verify`** nếu muốn Failsafe kiểm thử artifact đã package: package phải chạy **trước** IT, và trong default lifecycle nó đã ở đúng vị trí. Trong ví dụ này integration test dùng compiled classes cùng fixture; muốn thực sự kiểm thử **JAR/WAR được triển khai**, cần một deploy/launch step ở pre-phase thay vì chỉ đọc classes.

### 5.3. Java service thực sự được kiểm tra

File `src/main/java/vn/example/verify/StatusService.java`:

```java
package vn.example.verify;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class StatusService {
    private StatusService() {
    }

    public static String format(String raw) {
        return "Status=" + raw.strip().toUpperCase(Locale.ROOT);
    }

    public static String fromFile(Path file) throws IOException {
        return format(Files.readString(file, StandardCharsets.UTF_8));
    }
}
```

`format` là logic nghiệp vụ nhỏ có thể unit test không cần I/O. `fromFile` kết hợp file I/O với logic chuyển đổi, là điểm tích hợp để kiểm thử qua fixture được tạo ở `pre-integration-test`. Dùng `Locale.ROOT` tránh khác biệt chuyển chữ hoa do locale máy chạy; `strip()` bỏ whitespace đầu/cuối để file do Ant ghi thêm line ending vẫn cho kết quả ổn định.

### 5.4. Java main và stdout dự kiến

File `src/main/java/vn/example/verify/App.java`:

```java
package vn.example.verify;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(StatusService.format("ready"));
    }
}
```

Ứng dụng main không đòi fixture. Khi build được JAR thường, ta sẽ chạy bằng `java -cp`. Chương trình in **chính xác**:

```text
Status=READY
```

Đây là stdout của Java program, **không phải output của Maven `verify`**. Việc in đúng dòng này một mình chưa chứng minh integration tests đã chạy; bài yêu cầu kiểm tra cả báo cáo và cleanup.

### 5.5. Unit test chạy qua Surefire

File `src/test/java/vn/example/verify/StatusServiceTest.java`:

```java
package vn.example.verify;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StatusServiceTest {
    @Test
    void convertsReadyToUppercase() {
        assertEquals("Status=READY", StatusService.format(" ready "));
    }

    @Test
    void stripsWhitespace() {
        assertEquals("Status=OK", StatusService.format("\n ok \t"));
    }
}
```

Có **hai unit test methods**; chúng không phụ thuộc `target/it-fixture`. Vì vậy phase `test` có thể chạy an toàn **trước** setup integration fixture. Nếu một unit test fail và Surefire dừng build ở phase `test`, pre-integration-test chưa bắt đầu, nên fixture của bài không cần dọn.

### 5.6. Integration test chạy qua Failsafe

File `src/test/java/vn/example/verify/StatusServiceIT.java`:

```java
package vn.example.verify;

import java.nio.file.Path;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StatusServiceIT {
    @Test
    void readsPreparedFixture() throws Exception {
        String fixturePath = System.getProperty("it.fixture.path");
        String expected = System.getProperty("it.expected");

        assertNotNull(fixturePath, "Missing Failsafe fixture path");
        assertNotNull(expected, "Missing Failsafe expected value");
        assertTrue(
            java.nio.file.Files.isRegularFile(Path.of(fixturePath)),
            "pre-integration-test did not prepare fixture"
        );

        assertEquals(
            expected,
            StatusService.fromFile(Path.of(fixturePath))
        );
    }
}
```

Đây là **một integration test method**. File fixture chỉ được tạo tại `pre-integration-test`, tức **sau phase `test` và `package`**. Do đó, nếu class này bị Surefire nhận chạy ở phase test (vì đặt nhầm tên `*Test.java` hoặc cấu hình includes quá rộng), nó có thể fail do fixture chưa tồn tại. Đặt `*IT.java` là một cách bảo vệ lifecycle.

### 5.7. Chạy đúng chuỗi đến verify

Mở terminal trong `verify-lifecycle-demo`:

```bash
java -version
mvn --version
mvn -B clean verify
```

Dự kiến với file POM, JDK 17+ và plugins resolve thành công:

1. `clean` xóa build output của lần trước.
2. `test`: Surefire chạy **2 unit tests** và đạt.
3. `package`: Maven tạo `target/verify-lifecycle-demo-1.0.0.jar`.
4. `pre-integration-test`: Antrun tạo `target/it-fixture/status.txt` chứa `ready`.
5. `integration-test`: Failsafe chạy **1 integration test** và ghi summary.
6. `post-integration-test`: Antrun xóa `target/it-fixture`.
7. `verify`: Failsafe kiểm tra summary, build **SUCCESS** nếu không có lỗi.

Lệnh Java sau đó:

```bash
java -cp target/verify-lifecycle-demo-1.0.0.jar vn.example.verify.App
```

Stdout chính xác:

```text
Status=READY
```

JAR này không cần JUnit tại runtime vì classes chính chỉ dùng JDK API. Các test dependencies chỉ dùng cho build/test. Không dùng `java -jar` nếu manifest chưa có `Main-Class`; ví dụ này dùng `java -cp` và tên class đầy đủ để khỏi phụ thuộc thêm cấu hình manifest.

### 5.8. Kiểm chứng cả báo cáo và cleanup

Sau `mvn verify` thành công, tìm:

```text
target/surefire-reports/
target/failsafe-reports/
target/failsafe-reports/failsafe-summary.xml
target/verify-lifecycle-demo-1.0.0.jar
```

Trong `failsafe-summary.xml`, Failsafe lưu số errors/failures/skipped và trạng thái tổng hợp. Dùng XML/TXT reports để xác nhận test nào đã chạy; không kiểm tra bằng cách chỉ xem một dòng `BUILD SUCCESS`.

Điểm then chốt của chuỗi là:

```text
target/it-fixture/   KHÔNG còn tồn tại sau post-integration-test
```

Lệnh kiểm tra trên Linux/macOS:

```bash
test ! -d target/it-fixture && echo "fixture-cleaned"
```

Output của **lệnh shell** trong trường hợp cleanup thành công:

```text
fixture-cleaned
```

Trên Windows PowerShell:

```powershell
if (-not (Test-Path -LiteralPath "target\it-fixture")) {
    Write-Output "fixture-cleaned"
}
```

Đây là phép kiểm tra hậu điều kiện trên project demo. Nếu không in ra gì, xem log/post-phase và kiểm tra đường dẫn thực tế; không tự coi nó là PASS.

### 5.9. Cố tình làm IT thất bại để thấy lý do cần verify

Đây là phần chứng minh đặc tính Failsafe. **Không sửa Java hoặc POM**; chỉ override expected value:

```bash
mvn -B -Dit.expected=Status=WRONG clean verify
```

Test `StatusServiceIT.readsPreparedFixture` nhận:

```text
Expected: Status=WRONG
Actual:   Status=READY
```

Đây là **mô tả nội dung assertion**; format lỗi cụ thể trong JUnit XML/log có thể khác. Kết quả kỳ vọng với Maven 3 và Failsafe 3.5.2:

1. Unit tests ở `test` vẫn PASS.
2. Antrun tạo fixture.
3. Integration test thất bại do assertion; Failsafe ghi failure vào summary và cho lifecycle tiếp tục tới cleanup.
4. Antrun `post-integration-test` **vẫn xóa** fixture.
5. `failsafe:verify` đọc summary và đánh dấu **BUILD FAILURE**.

Chạy kiểm tra fixture sau lệnh build thất bại:

```bash
test ! -d target/it-fixture && echo "fixture-cleaned"
```

Trong điều kiện chuỗi plugin hoàn tất đúng như dự kiến, vẫn thấy:

```text
fixture-cleaned
```

**Đây mới là lập luận “failsafe”:** test FAIL không đồng nghĩa teardown bị bỏ qua; lỗi chất lượng được báo **sau** khi có cơ hội dọn môi trường. Tuy nhiên một lỗi thiết lập hạ tầng/Ant task hoặc runner bị kill có thể ngăn phase cleanup; cần cơ chế cleanup phụ trợ ở CI.

Nếu dùng PowerShell, chạy lại lệnh kiểm tra Windows ở mục 5.8.

### 5.10. Vì sao không thực hành bằng mvn integration-test trên môi trường thật?

Với Maven 3, gọi:

```bash
mvn -B integration-test
```

sẽ dừng trước post-phase và verify. Trong project demo, fixture có thể còn lại; trong project dùng Docker/DB/server, hậu quả có thể là service chạy tiếp, kết nối bị treo hoặc dữ liệu test chưa được xóa. Vì vậy **không khuyến khích chạy lệnh này làm điểm dừng khi có tài nguyên thật**.

Nếu đã chạy nhầm, không chỉ tiếp tục deploy: kiểm tra tài nguyên và dùng quy trình teardown được quản lý; sau đó chạy lại `mvn clean verify` với môi trường sạch. Tránh xóa dữ liệu test bên ngoài phạm vi dự án nếu chưa xác định quyền sở hữu và ảnh hưởng.

## 6. So sánh kết quả theo phase trong ví dụ

| Invocation | Unit (2) | Package JAR | Tạo fixture | IT (1) | Xóa fixture | Kiểm tra IT PASS/FAIL |
| --- | --- | --- | --- | --- | --- | --- |
| `mvn test` | Có | Không | Không | Không | Không cần | Chưa |
| `mvn package` | Có | Có | Không | Không | Không cần | Chưa |
| `mvn integration-test` (Maven 3) | Có | Có | Có | Có | **Chưa** | **Chưa qua failsafe:verify** |
| `mvn verify` | Có | Có | Có | Có | Có nếu tới post-phase | **Có** |
| `mvn install` | Có | Có | Có | Có | Có nếu tới post-phase | Có trước install |
| `mvn deploy` | Có | Có | Có | Có | Có nếu tới post-phase | Có trước deploy |

Bảng giả định **đúng POM mẫu**, không có `-DskipTests`/`-DskipITs`, các plugin không bị override và build không gặp lỗi khác ngoài tình huống test assertion đã được Failsafe ghi nhận.

**Đừng hiểu “mvn verify luôn bảo đảm cleanup tuyệt đối”.** Nếu một goal ở `compile`, `package`, `pre-integration-test` hoặc bản thân `post-integration-test` fail trước khi lifecycle tới verify, Maven có thể dừng. CI phải thiết kế resource lifecycle đủ an toàn ngay cả khi job bị hủy.

## 7. Các lỗi hiểu sai thường gặp

### 7.1. “Verify chỉ chạy thêm một số test, có gì khác package?”

Sai ở hai điểm. `verify` là phase **sau** `integration-test` và `post-integration-test`, nên nó bảo đảm thứ tự thực thi các goal đã được bind. Và `failsafe:verify` dùng kết quả do goal `integration-test` ghi lại để quyết định build failure sau cleanup.

Một project không có integration tests vẫn có thể `mvn verify` thành công; điều đó là vấn đề **cấu hình test quality gates**, không phải Maven Core tự thiếu phase.

### 7.2. “Chỉ cần Failsafe integration-test, không cần goal verify.”

Không đúng nếu muốn CI báo thất bại khi integration test không đạt. Failsafe trì hoãn test failure ở `integration-test` nhằm dọn môi trường trước; thiếu goal `verify` có nguy cơ **mất kết luận fail cuối cùng**.

### 7.3. “Gắn Surefire vào integration-test cũng như Failsafe.”

Không hoàn toàn. Surefire thường fail ngay khi test fail, do đó có thể chặn `post-integration-test`. Failsafe chia chạy test và xác minh để xử lý trường hợp integration-test thất bại tốt hơn.

### 7.4. “Build success nghĩa là IT đã chạy.”

Không. Có thể không khai Failsafe execution, không có `*IT`, skip flag, hoặc includes/excludes lọc mất mọi test. **Quan sát reports và test counts**, và đặt `failIfNoTests` đúng chỗ khi IT bắt buộc.

### 7.5. “Có @Tag integration thì Maven tự chuyển test tới integration-test.”

Không. `@Tag` chỉ là framework metadata. Cần Surefire/Failsafe provider và include/tag filters. Nên dùng naming convention `*IT` hoặc cấu hình rõ.

### 7.6. “Maven verify sẽ tự sinh coverage, security scan hoặc container.”

Không. JaCoCo, SpotBugs, Checkstyle, OWASP Dependency-Check, container/deployment plugins và các quality gates khác **chỉ chạy khi được khai báo và bind**. Phase verify là điểm phù hợp để gắn một số gate, nhưng nó không tự bật tất cả công cụ.

### 7.7. “Chạy mvn integration-test rồi sau đó mvn verify là tương đương.”

Về tổng thể không nên dùng làm quy trình mặc định. Lệnh thứ nhất có thể để lại tài nguyên do chưa post-cleanup; lệnh thứ hai **chạy lại toàn bộ lifecycle đến verify** (tùy cache/incremental behavior), có thể lặp lại setup và test. Dùng **một invocation `mvn clean verify`** cho chuỗi đầy đủ, hoặc một orchestration rõ ràng có teardown/verify độc lập nếu thực sự cần nhiều invocation.

## 8. Khi nào dùng mvn verify, mvn install và mvn deploy?

| Mục đích | Lệnh phù hợp | Vì sao |
| --- | --- | --- |
| Xác minh chất lượng một change/PR | `mvn -B clean verify` | Build/test/package/IT/cleanup/verify các gates được bind |
| Chỉ kiểm tra unit tests nhanh | `mvn -B test` | Không khởi động môi trường IT, vòng phản hồi nhanh hơn |
| Tạo JAR để thử thủ công | `mvn -B package` | Tạo artifact; chưa thay thế full verify |
| Cài artifact vào local repository của developer | `mvn -B install` | Đi qua verify trước khi `install` |
| Publish artifact ra Maven repository | `mvn -B deploy` | Đi qua verify trước khi deploy nếu không skip, cần distribution management/credentials |
| Chạy IT trong một pipeline chuẩn | `mvn -B verify` | Failsafe có cơ hội chạy post-phase và chốt kết quả |
| Chẩn đoán riêng một integration test | `mvn -Dit.test=StatusServiceIT verify` | Chọn đúng Failsafe test, nhưng vẫn đi đủ phases |

### 8.1. -Dtest khác -Dit.test

Surefire thường dùng `-Dtest=ClassName` để chọn unit test. Failsafe cung cấp `-Dit.test=ClassName` để chọn integration test. Ví dụ:

```bash
# Unit test cụ thể
mvn -Dtest=StatusServiceTest test

# Integration test cụ thể, vẫn đến verify
mvn -Dit.test=StatusServiceIT verify
```

Không thay `-Dit.test` bằng `-Dtest` rồi tin chắc Failsafe sẽ nhận đúng lựa chọn. Xem documentation của đúng plugin version, nhất là multi-module project.

### 8.2. -DskipITs và các dạng skip có thể làm vô hiệu gate

Failsafe hỗ trợ `-DskipITs` để bỏ qua integration tests và verification step liên quan, còn Surefire có `-DskipTests`. `-Dmaven.test.skip=true` có thể làm bỏ cả bước biên dịch/running test theo plugins hỗ trợ.

Ví dụ:

```bash
mvn -B -DskipITs verify
```

Lệnh này **có thể vẫn BUILD SUCCESS nhưng không có IT thực thi**, vì skip flag bỏ test. Và nó **không tự làm Antrun setup/cleanup ở pre/post-phase bị skip**: những plugin khác vẫn có thể chạy trong lifecycle.

Trong CI release, ghi rõ flags và policy cho phép skip. **Không coi “mvn verify SUCCESS” là đủ nếu pipeline có thể bỏ qua integration tests mà không ai biết.**

### 8.3. failIfNoTests trên reactor nhiều module

Nếu áp `<failIfNoTests>true</failIfNoTests>` vào parent với hàng chục modules, những module chỉ chứa interfaces hoặc utilities không có integration test có thể fail. Thiết kế một hoặc vài module IT chuyên dụng, hoặc cấu hình profile/entry gate theo từng module.

Đừng xóa hoàn toàn check này chỉ vì không phù hợp với mọi module; hãy đặt tại **đúng nơi bắt buộc có IT** và kiểm chứng số tests trong CI.

## 9. Những kiểm chứng khác có thể đặt ở verify

Tùy nhu cầu dự án, `verify` còn có thể là điểm chặn trước khi `install`/`deploy`:

- **Coverage thresholds:** JaCoCo `jacoco:check` thường có thể được bind tới `verify`, dùng data thu ở unit và integration tests khi plugin/configuration đúng.
- **Static analysis:** Checkstyle, PMD hoặc SpotBugs có thể chạy trong các phase phù hợp; không nhất thiết phải đợi đúng verify nếu cần phát hiện sớm.
- **API compatibility:** kiểm tra public API khi nâng library version.
- **Artifact verification:** kiểm tra nội dung JAR/WAR, manifest, chữ ký, SBOM/metadata, dependency policy với plugin tương ứng.
- **Integration contracts:** xác minh service endpoints, database migrations, serializer compatibility hoặc môi trường test.
- **Security/license gates:** dependency scan và policy check khi có plugin/rules được cấu hình.

**Cảnh báo thứ tự trong cùng phase:** Nếu có nhiều goal được bind vào `verify`, thứ tự chạy phụ thuộc lifecycle mapping, POM order và executions. Với mục đích cleanup trước check thì đặt cleanup ở **`post-integration-test`**, không đặt lẫn với Failsafe verify rồi hy vọng trật tự ngẫu nhiên. Đối với các quality checks đòi dữ liệu sau IT, bảo đảm report/coverage đã được tạo trước khi gate chạy.

### 9.1. JaCoCo + Failsafe có cần gì đặc biệt?

Không đủ khi chỉ thêm `jacoco:check` vào verify. JaCoCo cần instrumentation/agent được gắn đúng JVM thực thi test, các reports/data files phải được tạo và threshold rules đúng. Đối với integration tests forked JVM, cần kiểm tra agent arguments, exec file merging và lifecycle goals cụ thể.

Ví dụ test JVM không mang JaCoCo agent có thể tạo IT reports mà không tăng số coverage. Vì vậy chất lượng phải dựa trên **kết quả coverage report kiểm chứng**, không chỉ tên phase.

### 9.2. Gate sau packaging có thể kiểm tra gì?

Một project `jar` có thể kiểm:

- JAR tồn tại ở `target/<artifactId>-<version>.jar`.
- Manifest có main class/metadata mong đợi khi đã cấu hình.
- Runtime Java version tương thích.
- Không chứa thông tin nhạy cảm/lỗi đóng gói resource.
- IT thực sự chạy trên **artifact đã đóng gói** nếu đây là điều muốn chứng minh; project demo ở mục 5 chỉ kiểm tra compiled classes và fixture.

Đây là phần **cần cấu hình thêm**, không phải những việc Maven verify tự thực hiện.

## 10. Khi kiểm thử có Docker, DB hoặc server bên ngoài

Trong hệ thống thực, `pre-integration-test` có thể start container hoặc deploy ứng dụng; `post-integration-test` có thể stop container/restore state. Ví dụ luồng khái niệm:

```text
mvn clean verify
    |
    +-- package             → build service.jar
    +-- pre-integration-test→ start test DB, apply schema, deploy service
    +-- integration-test    → call API + verify database state
    +-- post-integration-test→ collect logs + stop service + stop DB
    +-- verify             → read test result, gate artifacts
```

**Phải tránh side effects ngoài phạm vi build**. Container nên có project/job label, tên riêng và TTL. Test database phải tách khỏi production. Secrets nên được lấy từ CI secret manager thay vì hardcode trong POM hoặc log.

### 10.1. Cleanup có thể không chạy dù dùng verify

Điều này xảy ra nếu:

- `pre-integration-test` setup fail ngay trước khi Failsafe bắt đầu;
- Maven process hoặc CI runner bị kill, hết timeout, mất điện;
- một goal/plugin khác ném exception làm lifecycle dừng;
- test thực thi ở plugin không trì hoãn failure;
- script teardown tự fail hoặc bị chặn quyền;
- môi trường hạ tầng nằm ngoài quyền kiểm soát của Maven process.

Vì thế cần **hai lớp bảo vệ**:

1. Trong Maven lifecycle, bind setup/IT/cleanup/verify đúng phases.
2. Trong CI/orchestration, có cleanup cuối cùng độc lập (container TTL, after/finally step, namespacing) cho trường hợp Maven không thể đi tiếp.

Không mô tả Failsafe như một transactional rollback engine. Nó chủ yếu bảo đảm rằng **test failures thông thường không ngăn post-integration-test** theo thiết kế.

### 10.2. Dọn dẹp trong @AfterEach và post-integration-test có giống nhau?

Không:

- `@AfterEach` của JUnit làm cleanup **trong test runtime** cho từng method (nếu framework chạy callback đến đó).
- `@AfterAll` làm teardown theo class.
- `post-integration-test` làm cleanup **ở Maven lifecycle**, ngoài phạm vi một test class.
- CI finally/after-step xử lý **ngoài Maven invocation** khi cần.

Phối hợp nhiều tầng tốt hơn việc buộc một callback JUnit dọn toàn bộ hạ tầng CI. Tài nguyên thuộc test method nên để test framework quản lý; tài nguyên khởi tạo cho cả Maven build nên có teardown tương ứng ở lifecycle/CI.

## 11. Cách xác minh việc verify thực sự chặn release

Một pipeline chất lượng không chỉ nhìn exit code; cần bằng chứng các mục tiêu chất lượng đã được thực thi.

### Checklist theo thứ tự

1. **Kiểm tra POM hiệu lực**: có Failsafe execution với **cả** `integration-test` và `verify` không?
2. **Kiểm tra tên test**: `*IT` và Failsafe includes phù hợp?
3. **Kiểm tra báo cáo**: `target/failsafe-reports/failsafe-summary.xml` và XML test details có số test thật không?
4. **Kiểm tra cleanup**: tài nguyên đã được dừng/xóa trước khi có verdict?
5. **Chạy negative test có chủ đích trên môi trường an toàn**: một integration assertion fail thì pipeline có fail tại verify sau khi teardown không?
6. **Kiểm tra quality gate khác**: coverage/security/package checks có được bind và reports được sinh?
7. **Kiểm tra skip flags**: không có `-DskipITs` hay những profile vô tình bỏ test?
8. **Kiểm tra release pipeline**: chỉ install/deploy sau khi bước verify trong cùng workflow đạt.
9. **Bảo vệ CI secrets và logs**: lọc thông tin nhạy cảm khi lưu artifact reports.
10. **Quan sát trên reactor**: module nào có IT và module nào chỉ build dependencies; không ép mọi module có test giống nhau.

Ví dụ chẩn đoán cấu hình:

```bash
mvn --version
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn -B clean verify
```

`help:effective-pom` cần Maven Help Plugin resolve được. Nó hiển thị POM sau inheritance/profiles/merge, nhưng **không chứng minh plugin đã chạy hoặc test count**; phải kết hợp build log và report.

Nếu dùng debug:

```bash
mvn -B -X verify
```

**Bảo mật:** log `-X` có thể chứa repository URLs, filesystem paths và thông tin hạ tầng; lọc secrets trước khi chia sẻ.

## 12. Khi nào Maven verify chưa đủ?

`verify` là một phase trong build system, không thay thế mọi giai đoạn release.

| Mong muốn | Maven verify có tự bảo đảm? | Cần bổ sung |
| --- | --- | --- |
| Unit tests đạt | Có, nếu Surefire đúng binding và không skip | Assert test counts, CI reports |
| Integration tests đạt | Có, nếu Failsafe đúng hai goals và không skip | Test environment, test coverage, reports |
| Container đã dừng | Không tuyệt đối | Teardown phase + CI finally/TTL |
| JAR/WAR hoạt động trong production | Không | Smoke test trên staging và runtime monitoring |
| Artifact không có CVE | Không | Dependency/security scan và policy |
| Đã kiểm tra license/SBOM | Không | Tool/rules tạo SBOM và license checks |
| Được publish lên Maven repository | Không | `mvn deploy` hoặc release automation có credentials |
| Migrations rollback an toàn | Không | DB migration strategy/test/backup |
| Test đã bao phủ mọi case | Không | Kịch bản/chính sách chất lượng, test design |
| Build tái lập giữa máy | Không tự động | Pin plugin/dependency versions, JDK/CI environment |

**Cách hiểu đúng:** `verify` là một **mốc tổng hợp các kiểm chứng đã cấu hình**, trước khi `install/deploy`. Chất lượng thực tế phụ thuộc những gate nào được gắn vào build và các bằng chứng chúng tạo ra.

## 13. Điều cần biết nếu dự án dùng Maven 4

Bài thực hành nhắm tới Maven 3.9.x, vì trong Maven 3 **gọi trực tiếp phase `integration-test` không chạy tiếp `post-integration-test`**. Apache Maven 4 đã bổ sung các phase `before:` và `after:` và thay đổi semantics khi gọi một phase trực tiếp: tài liệu lifecycle hiện tại nói Maven 4 sẽ chạy các bindings `post-integration-test` cần thiết ngay cả khi lệnh dừng tại `integration-test`. Do đó không nên khẳng định mọi phiên bản Maven đều xử lý đúng như Maven 3.

Tuy nhiên, **`verify` vẫn là mốc kiểm tra kết quả Failsafe** khi goal `failsafe:verify` được bind, và vẫn là cách thể hiện rõ “đi qua toàn bộ chuỗi kiểm chứng trước install/deploy”. Khi nâng Maven 3 lên Maven 4, hãy đối chiếu thay đổi lifecycle, plugin compatibility và chạy lại CI verification cases trước khi đổi pipeline.

Không dùng thay đổi của Maven 4 để biện minh cho việc **bỏ `failsafe:verify`** trong POM: đó là goal chấm kết quả test, khác việc Maven có chạy teardown hay không.

## 14. Câu hỏi tự luyện và đáp án

**Câu 1.** Dự án cấu hình Failsafe đúng, chạy `mvn integration-test` trên Maven 3. Integration test fail do assertion; đã chắc build fail và container được stop chưa?

**Đáp án:** Chưa. Failsafe thường trì hoãn failure của integration tests; lệnh dừng trước `post-integration-test` và `verify`. Cần chạy `mvn verify` hoặc `mvn clean verify` để có cleanup rồi kiểm tra kết quả.

**Câu 2.** `mvn package` thành công. Có thể kết luận integration tests đã pass không?

**Đáp án:** Không. `package` diễn ra trước các phase integration-test. Chỉ kết luận từ kết quả Failsafe thực sự được chạy và verified.

**Câu 3.** Nếu thiếu goal `failsafe:verify` nhưng có `failsafe:integration-test`, nguy cơ nào xuất hiện?

**Đáp án:** Lỗi assertions có thể được ghi vào reports nhưng build không bị fail ở giai đoạn chốt, vì Failsafe đã trì hoãn báo lỗi. Phải bind cả hai goals.

**Câu 4.** Trong bài Java 17, sau khi override `-Dit.expected=Status=WRONG`, điều gì kỳ vọng xảy ra?

**Đáp án:** Failsafe IT ghi một assertion failure, Antrun post-integration-test xóa fixture, sau đó Failsafe verify đánh dấu BUILD FAILURE. Unit tests vẫn đạt.

**Câu 5.** `mvn verify` thành công nhưng thư mục `target/failsafe-reports` trống hoặc không tồn tại. Có thể kết luận Failsafe pass không?

**Đáp án:** Không. Có thể Failsafe chưa được bind, không có test phù hợp hoặc đã skip. Kiểm tra POM, execution logs và test counts.

**Câu 6.** Nếu một unit test của Surefire fail ở phase `test`, có cần Failsafe dọn container do `pre-integration-test` tạo không?

**Đáp án:** Trong chuỗi này chưa chạy pre-integration-test, nên container/fixture từ phase đó chưa được tạo trong lượt Maven hiện tại. Những tài nguyên tồn từ lần trước hoặc CI khác cần quản lý riêng; không phụ thuộc Failsafe dọn chúng.

**Câu 7.** Vì sao `mvn -DskipITs verify` không phải bằng chứng integration tests đạt?

**Đáp án:** Cờ `skipITs` làm Failsafe bỏ qua integration tests. Build có thể thành công dù test không thực thi; cần policy hạn chế skip và reports thực.

**Câu 8.** Nếu pre-integration-test plugin không khởi động được database, `mvn verify` có bảo đảm chạy post-integration-test cleanup không?

**Đáp án:** Không. Maven có thể dừng vì setup failure trước khi post-phase. Cần thiết kế teardown idempotent/CI finally và quản lý lifetime của tài nguyên ngoài.

**Câu 9.** Tại sao tên `SomeIT.java` thường tốt hơn `SomeIntegrationTest.java` trong cấu hình mặc định?

**Đáp án:** `*IT` thường được Failsafe quét, không khớp mẫu Surefire mặc định; `*IntegrationTest` lại khớp `*Test` của Surefire và có thể chạy quá sớm trước setup.

**Câu 10.** Muốn Maven 3 hoàn thành unit tests, packaging, IT setup, IT test, teardown rồi fail khi quality gate thất bại, nên chọn invocation nào?

**Đáp án:** `mvn -B clean verify` với Failsafe cả hai goals, setup/teardown plugins và các quality gates được bind đúng phases.

## Tài liệu chính thức để đối chiếu

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Apache Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
- [Apache Maven Failsafe Plugin — integration-test Goal](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Apache Maven Failsafe Plugin — verify Goal](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
- [Apache Maven Failsafe Plugin — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html)
- [Apache Maven Surefire Plugin — Usage](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Antrun Plugin — Usage and Tasks](https://maven.apache.org/plugins/maven-antrun-plugin/usage.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
