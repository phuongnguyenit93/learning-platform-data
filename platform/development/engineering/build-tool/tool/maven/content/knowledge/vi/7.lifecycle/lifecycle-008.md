# pre-integration-test, integration-test và post-integration-test trong vòng đời Maven

## 1. Vấn đề cần giải quyết: kiểm thử tích hợp cần một môi trường sống

Unit test thường chạy trực tiếp trên lớp Java và các dependency nằm trong classpath. Trái lại, **integration test** (kiểm thử tích hợp) có thể phải tương tác với nhiều thành phần cùng lúc: ứng dụng đã đóng gói, cơ sở dữ liệu, message broker, HTTP server, file cấu hình hoặc một dịch vụ giả lập. Nếu chỉ chạy test mà không chuẩn bị môi trường, kết quả dễ thất bại vì thiếu tài nguyên. Nếu test xong mà không dọn, máy phát triển hoặc CI có thể còn tiến trình/port/container đang hoạt động.

Maven dành các phase trong **default build lifecycle** cho nhu cầu này:

1. `pre-integration-test`: chuẩn bị môi trường kiểm thử.
2. `integration-test`: chạy các kiểm thử tích hợp theo plugin được cấu hình.
3. `post-integration-test`: thu hồi tài nguyên và thực hiện công việc sau test.
4. `verify`: đánh giá kết quả kiểm thử, áp dụng các điều kiện chấp nhận và báo build thành công/thất bại.

Ba phase đầu là trọng tâm của bài; `verify` được giải thích cùng vì thiếu bước này sẽ hiểu sai trạng thái kiểm thử. Với Maven 3, lệnh được khuyến nghị để chạy đầy đủ chu trình là **`mvn verify`** hoặc **`mvn clean verify`**.

Điểm quan trọng: tên phase **không tự tạo server hay tự sinh bộ integration test**. Maven chỉ chạy **plugin goal đã được gắn (bound)** vào phase tương ứng. Nếu không có goal nào gắn vào một phase thì phase đó có thể không tạo ra hành động nào.

## 2. Vị trí của ba phase trong toàn bộ lifecycle

Đây là thứ tự rút gọn của default lifecycle trong Maven 3:

```text
validate
   |
compile
   |
test-compile
   |
test                  <-- unit test (thường Maven Surefire)
   |
package               <-- tạo JAR/WAR
   |
pre-integration-test  <-- dựng môi trường
   |
integration-test      <-- chạy integration test (thường Maven Failsafe)
   |
post-integration-test <-- dọn môi trường
   |
verify                <-- đánh giá kết quả, quyết định PASS/FAIL
   |
install
   |
deploy
```

Còn có các phase trung gian như `process-resources`, `prepare-package` trong lifecycle thực. Sơ đồ chỉ giữ các mốc giúp thấy quan hệ giữa compile, test, package và integration test.

**Gọi một phase trong lifecycle sẽ đi qua các phase đứng trước nó**, nhưng không tự chạy các phase đứng sau. Ví dụ trong Maven 3:

- `mvn test`: dừng ở phase `test`; không đến `package` và bộ ba phase integration test.
- `mvn package`: dừng ở `package`; thường tạo JAR và đã chạy unit test, nhưng chưa đến `pre-integration-test`.
- `mvn integration-test`: chạy các phase đến `integration-test`, **chưa đến `post-integration-test` hoặc `verify`**; vì vậy có thể để lại môi trường đang chạy.
- `mvn verify`: đi qua **toàn bộ** pre → integration → post → verify.
- `mvn clean verify`: chạy **clean lifecycle** để dọn đầu ra build cũ, sau đó chạy default lifecycle đến verify. `clean` và `post-integration-test` phục vụ hai mục đích khác nhau.

Với Maven 4 có thay đổi về các phase `before:`/`after:` và cách gọi trực tiếp `integration-test`: Maven 4 có thể chạy các bước sau phase tương ứng được gắn với cơ chế mới, thay vì hành vi Maven 3 nêu trên. Khi làm tài liệu cho nhiều môi trường, vẫn nên **chọn `verify` làm điểm kết thúc** vì nó diễn đạt đúng mục tiêu “chạy và xác minh integration test” và bao gồm kiểm tra kết quả của Failsafe.

## 3. Vai trò riêng của từng phase

### 3.1. `pre-integration-test`: chuẩn bị môi trường

Phase này chạy **sau package, trước integration-test**. Những việc thường gắn vào phase:

- Khởi động database tạm, HTTP server, container hoặc dịch vụ giả lập.
- Tạo schema, seed dữ liệu fixture hoặc triển khai ứng dụng thử nghiệm.
- Cấp thông tin kết nối, cổng và biến môi trường cần thiết cho test.
- Tạo một số tệp trạng thái/cấu hình phục vụ integration test.
- Chờ điều kiện sẵn sàng (`readiness`), nếu plugin/script đã cấu hình làm điều đó.

Ví dụ service cần PostgreSQL: plugin/tool của dự án có thể bật container database, chờ health check, áp dụng migration và cung cấp JDBC URL. Không nên chỉ “sleep vài giây” rồi giả định service đã sẵn sàng.

**Không phải tất cả bước chuẩn bị thuộc Maven mặc định.** Chúng có được thực hiện hay không phụ thuộc plugin và cấu hình POM. Mọi ví dụ trong tài liệu này dùng **Maven Antrun Plugin** để tạo một fixture file nhỏ, chỉ nhằm quan sát thứ tự lifecycle mà không cần cài Docker hay DB thật.

### 3.2. `integration-test`: chạy test trên môi trường đã dựng

Phase này dùng để chạy những kiểm thử đánh giá **sự phối hợp của nhiều thành phần**. Với dự án Java, thường dùng **Maven Failsafe Plugin**, goal `failsafe:integration-test`. Test có thể gọi REST endpoint, truy vấn DB, đọc thông điệp gửi vào broker hoặc xác nhận tài nguyên do phase trước tạo.

Một số nguyên tắc:

- Test phải kiểm tra hành vi có ý nghĩa; chỉ kiểm tra “server trả HTTP 200” chưa đủ với mọi chức năng.
- Test nên độc lập và có thể tái tạo; làm sạch dữ liệu test, tránh tác động database thật.
- Phân biệt lỗi assertion với lỗi hạ tầng, timeout, port đang bận hoặc dữ liệu test không sạch.
- Sử dụng cơ chế chờ sẵn sàng và timeout hợp lý, tránh race condition.

**Khi dùng Failsafe đúng cấu hình, lỗi assertion của integration test không làm Maven chấm dứt ngay ở phase này.** Failsafe giữ kết quả để tới phase `verify` mới quyết định build thất bại. Nhờ vậy phase `post-integration-test` vẫn có cơ hội chạy và dọn môi trường. Nếu sử dụng một goal khác trả lỗi ngay ở `integration-test`, Maven có thể dừng trước cleanup; vì thế lựa chọn plugin và điểm báo lỗi rất quan trọng.

### 3.3. `post-integration-test`: thu hồi và hoàn tất

Những việc có thể gắn vào phase:

- Tắt test server, database/container, trả lại port và kết nối.
- Dọn file tạm, volume hoặc dữ liệu fixture đã tạo cho integration test.
- Thu thập log, báo cáo, trace/coverage trước khi xóa tài nguyên cần thiết.
- Khôi phục trạng thái tạm được tạo cho test.

**Lưu ý quan trọng:** đây là phase thông thường trong Maven lifecycle, không phải một khối `finally` tuyệt đối. Nếu Maven bị kill, máy CI sập hoặc một plugin thất bại trước khi tới post, cleanup có thể không chạy. Với hệ thống thật, nên kết hợp cleanup trong công cụ quản lý test environment và cơ chế dọn cuối job CI (ví dụ bước luôn thực thi), cùng timeout/giới hạn tài nguyên.

### 3.4. `verify`: quyết định kết quả cuối cùng

Phase `verify` chạy sau `post-integration-test`. Thường gắn goal `failsafe:verify` để đọc báo cáo trước đó và **fail build** nếu integration test thất bại. Các plugin khác có thể gắn vào verify để kiểm tra chất lượng artifact, coverage hoặc quy tắc phát hành.

Với Maven Failsafe, cặp goal có vai trò tách biệt:

| Plugin goal | Phase thường gắn | Vai trò |
| --- | --- | --- |
| `failsafe:integration-test` | `integration-test` | Chạy các `*IT` test và ghi kết quả |
| `failsafe:verify` | `verify` | Đọc kết quả integration test và báo PASS/FAIL cho Maven |

Nếu chỉ chạy tới `integration-test` hoặc gọi riêng `failsafe:integration-test`, một lần test lỗi **không nhất thiết làm lệnh Maven có exit code lỗi đúng như mong đợi**. Mốc verify là phần không thể bỏ qua khi cần CI chặn bản build không đạt.

## 4. Surefire và Failsafe: đều chạy test, nhưng khác vị trí

| Tiêu chí | Maven Surefire Plugin | Maven Failsafe Plugin |
| --- | --- | --- |
| Mục tiêu thường dùng | Unit test | Integration test |
| Phase mặc định | `test` | `integration-test` và `verify` |
| Mẫu tên test thông dụng | `Test*.java`, `*Test.java`, `*Tests.java`, `*TestCase.java` | `IT*.java`, `*IT.java`, `*ITCase.java` |
| Thư mục mã test theo quy ước | `src/test/java` | Cũng có thể là `src/test/java` |
| Báo cáo thông dụng | `target/surefire-reports` | `target/failsafe-reports` |
| Khi assertion fail | Thường fail ở `test` | Ghi lỗi lúc integration-test, fail build tại `verify` |

**Tên class chỉ là quy ước khám phá test, không phải định nghĩa chất lượng test.** Một lớp `GreetingIT` chỉ được xem là integration test có ý nghĩa khi nó thực sự kiểm chứng sự tương tác phù hợp. Có thể cấu hình pattern khác bằng `includes`/`excludes`.

Cả hai plugin đều cần một test framework/engine tương thích (ví dụ JUnit Jupiter) trên test classpath. Việc thêm JUnit dependency **không tự cấu hình Failsafe** để chạy integration test trong lifecycle: cần gắn goal tương ứng vào phase.

Đừng gắn Surefire một cách tùy tiện vào `integration-test` khi cần dọn môi trường sau test: fail sớm có thể chặn `post-integration-test`. Failsafe được thiết kế để hoãn kết luận thất bại sang verify.

## 5. Ví dụ đầy đủ Java 17: chuẩn bị → chạy IT → dọn → xác minh

Ta tạo một dự án Java nhỏ, **không cần kết nối database hay Docker**. Ở `pre-integration-test`, AntRun tạo file `target/it-fixture/ready.txt` với chuỗi `READY`. Ở `integration-test`, Failsafe chạy test `GreetingIT` đọc đúng file đó và gọi mã ứng dụng. Ở `post-integration-test`, AntRun xóa thư mục fixture. Ở `verify`, Failsafe kiểm tra kết quả test.

Ví dụ sử dụng JDK 17+, Maven 3.9.x và các plugin đã ghim phiên bản. Khi dùng Maven 4 hoặc phiên bản plugin khác, cần xác minh tương thích theo tài liệu hiện hành.

### 5.1. Cấu trúc thư mục cần tạo

```text
maven-integration-lifecycle/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/lifecycle/Greeting.java
    └── test/
        └── java/
            └── com/example/lifecycle/
                ├── GreetingTest.java
                └── GreetingIT.java
```

- `Greeting.java` chứa code ứng dụng và `main`.
- `GreetingTest.java` là unit test, chạy bởi Surefire ở phase `test`.
- `GreetingIT.java` là integration test, chạy bởi Failsafe ở phase `integration-test`.
- `target/` và fixture được tạo **khi build**. Không tự tạo trước `target/it-fixture`; đó là việc của pre-integration-test.

### 5.2. Tệp `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>maven-integration-lifecycle</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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
                                <echo file="${project.build.directory}/it-fixture/ready.txt"
                                      encoding="UTF-8">READY</echo>
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
                                <delete dir="${project.build.directory}/it-fixture"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <systemPropertyVariables>
                        <fixture.path>${project.build.directory}/it-fixture/ready.txt</fixture.path>
                    </systemPropertyVariables>
                </configuration>
                <executions>
                    <execution>
                        <id>run-integration-tests</id>
                        <phase>integration-test</phase>
                        <goals>
                            <goal>integration-test</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>verify-integration-results</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Những gì POM này **chủ động cấu hình**:

1. `maven.compiler.release=17`: yêu cầu bytecode/API Java 17 và JDK hỗ trợ.
2. `junit-jupiter` với `scope=test`: cung cấp thư viện và engine JUnit Jupiter cho test; không thêm JUnit vào runtime của ứng dụng.
3. `maven-surefire-plugin`: chạy lớp `GreetingTest` trong phase `test` theo binding JAR lifecycle thông dụng.
4. `maven-antrun-plugin` với hai `execution`: tạo file fixture ở `pre-integration-test`; xóa riêng thư mục fixture ở `post-integration-test`.
5. `maven-failsafe-plugin` với hai goal có phase rõ ràng: chạy `GreetingIT` ở `integration-test`, đánh giá kết quả ở `verify`.
6. `fixture.path`: JVM chạy integration test nhận đường dẫn đến fixture bằng system property để tránh phụ thuộc vào thư mục làm việc của tiến trình fork.

Cấu hình ở đây dùng AntRun chỉ để quan sát lifecycle. Với HTTP server, DB hoặc container thật, nên dùng plugin/công cụ thích hợp và điều kiện sẵn sàng rõ ràng. Đừng lấy ví dụ này làm lời hứa rằng Maven/AntRun tự hiểu cách khởi chạy mọi loại hạ tầng.

### 5.3. Tệp `src/main/java/com/example/lifecycle/Greeting.java`

```java
package com.example.lifecycle;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello, Maven IT!";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

`message()` là một chức năng nhỏ có thể kiểm tra độc lập; `main` cho phép chạy và kiểm chứng stdout sau build.

### 5.4. Tệp `src/test/java/com/example/lifecycle/GreetingTest.java`

```java
package com.example.lifecycle;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void messageHasExpectedValue() {
        assertEquals("Hello, Maven IT!", Greeting.message());
    }
}
```

Đây là **unit test**. Nó không cần file fixture hay dịch vụ ngoài, nên thích hợp chạy từ phase `test`. Surefire sẽ nhận diện vì tên `GreetingTest` khớp pattern `*Test`.

### 5.5. Tệp `src/test/java/com/example/lifecycle/GreetingIT.java`

```java
package com.example.lifecycle;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class GreetingIT {
    @Test
    void seesFixturePreparedByLifecycle() throws IOException {
        String configuredPath = System.getProperty("fixture.path");
        assertTrue(configuredPath != null && !configuredPath.isBlank(),
                "Missing fixture.path system property");

        Path fixture = Path.of(configuredPath);
        assertTrue(Files.isRegularFile(fixture),
                "Fixture must exist before integration tests");

        String contents = Files.readString(fixture, StandardCharsets.UTF_8).trim();
        assertEquals("READY", contents);
        assertEquals("Hello, Maven IT!", Greeting.message());
    }
}
```

Đây là **integration test mô phỏng** một tình huống phụ thuộc vào môi trường đã được chuẩn bị: nếu không có fixture hoặc fixture bị tạo sai, test sẽ thất bại. Trong hệ thống thực, fixture có thể là một database/schema, HTTP server hoặc broker thay cho file.

`GreetingIT` thuộc `src/test/java` nên vẫn được **biên dịch** ở `test-compile`. Khác biệt chủ yếu là **thời điểm plugin tìm và chạy test**: mặc định Surefire chạy `*Test`, Failsafe chạy `*IT`. Test tích hợp không bắt buộc phải đặt ở một thư mục khác; bạn có thể tổ chức riêng bằng plugin configuration nếu dự án cần.

### 5.6. Chạy đúng chu trình và quan sát đầu ra

Mở terminal tại thư mục chứa `pom.xml`:

```bash
mvn -version
mvn clean verify
java -cp target/classes com.example.lifecycle.Greeting
```

Nếu dependency/plugin có thể phân giải và JDK phù hợp, Maven lần lượt thực hiện:

```text
test:                  GreetingTest chạy qua Surefire
package:               tạo JAR thông thường
pre-integration-test:  AntRun tạo target/it-fixture/ready.txt
integration-test:      Failsafe chạy GreetingIT và ghi kết quả
post-integration-test: AntRun xóa target/it-fixture
verify:                Failsafe kiểm tra kết quả integration test
```

Đây là **mô tả theo phase**, không phải log stdout cố định của Maven. Sau khi `verify` thành công, bạn sẽ thường thấy:

- `target/classes/com/example/lifecycle/Greeting.class`;
- `target/maven-integration-lifecycle-1.0.0.jar`;
- `target/surefire-reports` chứa kết quả của `GreetingTest`;
- `target/failsafe-reports` chứa kết quả của `GreetingIT` và file summary Failsafe;
- `target/it-fixture` **không còn**, vì post-integration-test đã xóa.

**Đầu ra chính xác** của lệnh Java `java -cp target/classes ...`:

```text
Hello, Maven IT!
```

Nếu chỉ chạy `mvn test`, bước chuẩn bị fixture và `GreetingIT` chưa đến lượt chạy. Nếu chỉ chạy `mvn package`, JAR được đóng gói nhưng vẫn chưa tới integration-test. Sự khác biệt giữa các lệnh chính là lý do bạn nên chọn `verify` trong job CI cần kiểm thử tích hợp.

## 6. Thí nghiệm quan trọng: nếu integration test FAIL thì chuyện gì xảy ra?

Để quan sát đúng vai trò của Failsafe, sửa trong `GreetingIT.java` duy nhất dòng:

```java
assertEquals("READY", contents);
```

thành:

```java
assertEquals("WRONG", contents);
```

Hai đoạn trên là **dòng mã thay thế trong class `GreetingIT`**, không phải chương trình Java độc lập. Sau đó chạy:

```bash
mvn clean verify
```

Diễn biến **dự kiến** (giả sử các plugin khởi chạy bình thường):

1. `pre-integration-test` vẫn tạo fixture với nội dung `READY`.
2. `failsafe:integration-test` chạy và ghi nhận assertion thất bại vì expected là `WRONG` còn actual là `READY`.
3. Failsafe không fail build ngay chỉ vì assertion này; Maven tiếp tục tới `post-integration-test`.
4. AntRun dọn `target/it-fixture`.
5. `failsafe:verify` đọc kết quả và báo build **FAIL**, Maven trả exit code khác 0. CI có thể chặn phát hành.

Khôi phục assertion thành `assertEquals("READY", contents);` rồi chạy lại để test PASS.

**Giới hạn cần hiểu:** bảo đảm thứ tự trên áp dụng cho kiểu lỗi kiểm thử mà Failsafe xử lý theo thiết kế. Lỗi tải plugin, plugin `pre-integration-test` không khởi chạy được, process bị tắt đột ngột hay lỗi hạ tầng nằm ngoài cơ chế trì hoãn test failure có thể ngăn cleanup. Đối với tài nguyên thật có chi phí, vẫn cần cleanup an toàn ở cấp job hoặc hệ thống điều phối.

## 7. Vì sao không nên gọi riêng các phase tích hợp trong Maven 3?

Trong Maven 3, việc chạy:

```bash
mvn integration-test
```

**đến hết phase integration-test rồi dừng lại**. Nếu `pre-integration-test` đã khởi động database, Jetty/Tomcat hoặc container, `post-integration-test` **chưa chạy**, nên dịch vụ có thể còn sống. Chưa có `failsafe:verify`, nên kết quả test cũng chưa nhất thiết được đánh giá thành exit code thất bại.

Tương tự:

- `mvn pre-integration-test`: có thể chỉ dựng môi trường, không chạy test hay teardown.
- `mvn post-integration-test`: đi qua pre, integration và post nhưng **chưa tới verify**, nên không nên coi là kết thúc kiểm tra chất lượng.
- `mvn failsafe:integration-test`: gọi **plugin goal trực tiếp**, không có nghĩa Maven sẽ tự chạy cả các phase pre/post/verify; trong ví dụ có thể thiếu fixture.

**Lệnh nên dùng cho quy trình hoàn chỉnh:**

```bash
mvn verify
mvn clean verify
```

Maven 4 có thay đổi đáng kể trong cách gọi các phase đặc biệt (các phase `before:`/`after:`); không áp dụng máy móc hành vi Maven 3 cho Maven 4. Dù Maven 4 có thể chạy cleanup khi gọi một phase riêng, kiểm chứng kết quả tích hợp ở phase `verify` vẫn là lựa chọn rõ ràng, dễ hiểu và phù hợp với Failsafe.

## 8. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân/việc nên kiểm tra |
| --- | --- |
| Chạy `mvn test` nhưng `*IT` không chạy | Đúng hành vi phổ biến: Failsafe chạy ở `integration-test`; thử `mvn verify` |
| Chạy `mvn verify` nhưng không có IT nào được chạy | Kiểm tra Failsafe đã gắn goals vào phase, pattern `*IT`/`IT*`, classpath/engine JUnit, log plugin |
| Integration test không thấy file/server/DB | Kiểm tra goal chuẩn bị ở `pre-integration-test`, đường dẫn, permission và readiness |
| Fixture có nhưng test fail vì dữ liệu không đúng | Kiểm tra seed, assertion, encoding, thứ tự test và môi trường |
| Test FAIL nhưng phase integration-test không dừng | Failsafe cố ý hoãn lỗi assertion cho phase `verify`; kiểm tra báo cáo và exit code cuối |
| Chạy `mvn integration-test` rồi server vẫn còn chạy | Với Maven 3, post/verify chưa được gọi; dừng dịch vụ theo quy trình và dùng `mvn verify` |
| Đã thêm Failsafe nhưng không có `failsafe-reports` | Có thể goal chưa được gắn/không chạy, test không khớp pattern hoặc plugin chưa có cấu hình đúng |
| Surefire chạy nhầm IT hoặc Failsafe chạy nhầm unit test | Kiểm tra `includes`/`excludes` và tên lớp, không chỉ nhìn thư mục |
| `java -jar` báo thiếu `Main-Class` | JAR demo chưa cấu hình manifest main; dùng `java -cp ... Greeting` hoặc cấu hình đóng gói phù hợp |
| Post đã xóa fixture nhưng report còn | Đúng kỳ vọng: xóa riêng `target/it-fixture`, để lại `target/failsafe-reports` |
| Cleanup không chạy khi CI bị hủy | Phase post không phải finally tuyệt đối; thêm cleanup ở cấp CI/container với quyền phù hợp |

Một số lệnh chẩn đoán:

```bash
mvn -version
mvn help:effective-pom
mvn -e clean verify
```

`mvn -version` xác nhận Maven/JDK; `help:effective-pom` cho thấy plugin execution sau khi áp dụng cấu hình/parent; `-e` in thêm stack trace khi build lỗi. Có thể dùng `-X` để debug sâu nhưng log rất dài và đôi khi chứa cấu hình nhạy cảm.

Nên đọc file báo cáo `target/failsafe-reports` thay vì chỉ tìm dòng `BUILD FAILURE`. Khi dùng môi trường tích hợp thực, cũng phải thu thập log từ service/container và đảm bảo teardown không xóa chứng cứ cần cho việc điều tra.

## 9. Nguyên tắc thiết kế một vòng kiểm thử tích hợp đáng tin

1. **Dựng đúng tài nguyên:** xác định service, version, port, credential và dữ liệu test cần thiết trước khi bắt đầu.
2. **Chờ sẵn sàng thay vì đoán:** dùng health/readiness probe, timeout và retry có giới hạn ở nơi phù hợp.
3. **Tách unit test và integration test:** unit test nhanh ở `test`; integration test có thể chậm và cần hạ tầng hơn, chạy theo policy của dự án.
4. **Dùng Failsafe cho chu trình integration-test/verify:** tận dụng việc báo lỗi test tại verify để post có cơ hội dọn.
5. **Không coi post là cleanup duy nhất:** CI có thể bị hủy hoặc service lỗi trước khi post; bổ sung cơ chế dọn an toàn.
6. **Giữ test độc lập:** dùng dữ liệu tạm, tránh dùng production database hoặc tài khoản có quyền rộng.
7. **Giữ lại báo cáo:** kết quả Surefire/Failsafe và log cần đủ để xác minh nguyên nhân thất bại.
8. **Chạy đúng mốc:** chọn `mvn verify` khi cần xác nhận integration test; `install` hoặc `deploy` chỉ sau khi quyết định chất lượng build phù hợp.

## 10. Tự đánh giá sau bài học

- `pre-integration-test` khác `integration-test` như thế nào?
- Tại sao một integration test thường cần cả `post-integration-test` và `verify`?
- Vì sao Surefire có thể không phù hợp nếu được gắn trực tiếp vào phase integration-test trong quy trình cần cleanup?
- Trong Maven 3, điều gì có thể xảy ra nếu chỉ gọi `mvn integration-test`?
- Test `GreetingIT` trong ví dụ lấy fixture ở đâu, và phase nào xóa nó?
- Nếu `GreetingIT` bị assertion failure nhưng `target/it-fixture` đã được xóa trước khi build fail, việc đó minh họa cơ chế nào của Failsafe?
- Vì sao không nên chỉ tin vào phase post để dọn database/container thật?
- Khi chuyển sang Maven 4, tại sao phải xem tài liệu lifecycle của đúng phiên bản?

Điểm cần nhớ: **`pre-integration-test` chuẩn bị, `integration-test` kiểm thử, `post-integration-test` thu hồi, và `verify` chấm kết quả.** Maven điều phối **thứ tự phase**, plugin thực hiện hành động thực tế; chọn đúng plugin và đúng phase kết thúc giúp tránh môi trường treo và kết luận sai về chất lượng bản build.

### Tài liệu chính thức

- [Maven Build Lifecycle: danh sách phase, thứ tự và lưu ý khi gọi trực tiếp](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Failsafe Plugin: integration-test, post và verify](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Maven Failsafe Plugin: goal integration-test](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Maven Failsafe Plugin: goal verify](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
- [Maven Surefire: JUnit Platform và quy ước test names](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven AntRun Plugin: cấu hình goal run trong lifecycle](https://maven.apache.org/plugins/maven-antrun-plugin/usage.html)
