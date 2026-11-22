# Rủi ro gọi integration-test mà không đi tiếp đến các phase dọn dẹp trong Maven

## 1. Vấn đề thực tế

Một dự án Maven có thể khởi động PostgreSQL, Redis, một container Docker, một máy chủ HTTP hoặc một môi trường kiểm thử tạm trước khi chạy **integration test** (kiểm thử tích hợp). Sau khi test kết thúc, dự án phải tắt dịch vụ, giải phóng cổng, xóa dữ liệu tạm, thu thập báo cáo và kiểm tra kết quả cuối. Nếu người phát triển gọi:

~~~bash
mvn integration-test
~~~

thì trên **Maven 3.x**, Maven chạy default lifecycle đến phase `integration-test` rồi dừng, **chưa thực hiện `post-integration-test` và `verify`**. Nếu tác vụ dừng dịch vụ được gắn vào `post-integration-test`, dịch vụ có thể còn hoạt động. Nếu dự án dùng Maven Failsafe Plugin, kết quả test có thể đã được ghi vào báo cáo nhưng goal `failsafe:verify` chưa xác nhận nó.

Vì vậy, đối với dự án Maven 3 có kiểm thử tích hợp, lệnh thường phù hợp là:

~~~bash
mvn -B -ntp clean verify
~~~

`-B` bật batch mode, `-ntp` giảm log tải artifact; `clean` dọn sản phẩm build cũ, và `verify` đi qua các phase cần thiết của default lifecycle, bao gồm phần dọn môi trường **nếu có goal được cấu hình cho phase đó**.

**Chú ý khác biệt với Maven 4:** Maven 4 có cấu trúc phase `before:` và `after:` mới. Khi gọi một phase chính, Maven 4 có thể chạy luôn các phase `before:`/`after:` tương ứng; `post-integration-test` cũ là alias cho `after:integration-test`. Vì thế phát biểu “`mvn integration-test` luôn bỏ qua cleanup” **chỉ chính xác với hành vi Maven 3**. Trên Maven 4, phase hậu tương ứng được chạy cùng phase chính, nhưng lệnh `integration-test` vẫn **không đồng nghĩa với việc đã thực hiện goal `failsafe:verify`**. Hãy kiểm tra bản Maven thực sự bằng `mvn -version` hoặc `./mvnw -version`.

Bài thực hành bên dưới sử dụng Maven 3.9.x, JDK 17+ để tái hiện chính xác trường hợp dừng sớm; cuối bài có phần so sánh Maven 4.

## 2. Mục tiêu học tập

Sau bài này, người học có thể:

1. Chỉ đúng vai trò của `pre-integration-test`, `integration-test`, `post-integration-test` và `verify`.
2. Phân biệt **phase của Maven** với **goal của plugin**; biết vì sao `mvn integration-test` và `mvn failsafe:integration-test` không tương đương.
3. Giải thích Maven Failsafe Plugin trì hoãn việc báo lỗi test đến `failsafe:verify` để tạo cơ hội chạy teardown.
4. Nêu rủi ro thực tế khi bỏ qua cleanup: container treo, giữ cổng, dữ liệu test còn lại, báo cáo/coverage thiếu và CI báo kết quả sai.
5. Cấu hình một dự án Java 17 có unit test, integration test, setup và teardown; quan sát khác biệt khi dừng ở `integration-test` hoặc đi đến `verify`.
6. Thử một integration test thất bại có kiểm soát và phân tích giới hạn cleanup khi tiến trình bị ngắt.
7. Chọn cách gọi lệnh, cấu hình CI và xử lý resource an toàn, có khả năng chạy lại.

## 3. Chuỗi phase của kiểm thử tích hợp

Trên Maven 3, các phase liên quan nằm trong **default lifecycle** theo thứ tự:

~~~text
... → compile → test → package
                          │
                          ▼
                 pre-integration-test
                          │
                          ▼
                   integration-test
                          │
                          ▼
                post-integration-test
                          │
                          ▼
                       verify
                          │
                          ▼
                    install → deploy
~~~

| Phase | Vai trò | Goal minh họa |
| --- | --- | --- |
| `pre-integration-test` | Chuẩn bị môi trường trước khi test | Start service, tạo dữ liệu/volume/fixture |
| `integration-test` | Chạy các kiểm thử tích hợp | `failsafe:integration-test` |
| `post-integration-test` | Dọn môi trường, thu thập một số dữ liệu hậu kiểm | Stop service, xóa tài nguyên tạm |
| `verify` | Xác nhận kết quả kiểm thử và kiểm tra bổ sung | `failsafe:verify` |

**Phase là mốc thực thi**, không tự là một chương trình. Maven chỉ có tác vụ để thực hiện ở phase khi packaging hoặc cấu hình plugin đã **gắn goal vào phase**. Nếu không có goal start server ở `pre-integration-test`, Maven không tạo server. Nếu không có goal stop server ở `post-integration-test`, đi qua phase này cũng không giúp tắt server.

Khác biệt với unit test: phase `test` thường sử dụng Maven Surefire Plugin để chạy unit tests. Kiểm thử tích hợp thường được chạy muộn hơn, sau `package`, để có thể kiểm thử trên sản phẩm đã đóng gói hoặc môi trường gần thực tế hơn.

## 4. Gọi phase và gọi trực tiếp goal là hai việc khác nhau

| Lệnh | Ý nghĩa | Hệ quả cần lưu ý |
| --- | --- | --- |
| `mvn integration-test` | Chạy default lifecycle đến phase `integration-test` | Maven 3 chưa qua teardown và `verify` |
| `mvn failsafe:integration-test` | Gọi trực tiếp một plugin goal | Không tự chạy cả lifecycle để tạo artifact/khởi động môi trường |
| `mvn post-integration-test` | Chạy đến phase dọn môi trường | Maven 3 có thể chạy teardown nhưng chưa tới `verify` |
| `mvn failsafe:verify` | Gọi trực tiếp goal xác nhận Failsafe | Không tự tạo môi trường hoặc chạy lại toàn bộ test |
| `mvn verify` | Chạy qua phase `verify` của default lifecycle | Có cơ hội chạy setup, integration test, cleanup và xác nhận kết quả theo cấu hình |
| `mvn clean verify` | Dọn output rồi chạy qua `verify` | Phù hợp để kiểm chứng từ một lần build sạch |
| `mvn install` | Đi đến `install` | Bao gồm `verify` trước khi cài artifact vào local repository |

Không nên gọi trực tiếp `pre-integration-test`, `integration-test` hoặc `post-integration-test` làm lệnh CI cuối cùng trên Maven 3. Các phase này là những điểm trung gian của quy trình; chúng không thay thế kết quả cuối ở `verify`.

Khi dùng Maven Wrapper, thay `mvn` bằng `./mvnw` (Unix) hoặc `.\mvnw.cmd` (Windows) để dùng phiên bản Maven do dự án khai báo. Wrapper không tự bảo đảm JDK phù hợp; vẫn cần xem `java -version` và đầu ra Java của `mvnw -version`.

## 5. Maven Failsafe khác Surefire ở điểm quan trọng nào?

**Maven Surefire Plugin** thường chạy unit test tại phase `test` và làm build thất bại khi unit test thất bại, tùy cấu hình plugin. **Maven Failsafe Plugin** được thiết kế cho integration test, nơi cần thêm bước teardown sau khi test.

Failsafe có hai goal chính:

- `failsafe:integration-test`: chạy integration tests và tạo báo cáo/summary. Một assertion test thất bại thường được **ghi nhận mà không làm build fail ngay tại goal này**, để lifecycle có thể đi tiếp qua `post-integration-test`.
- `failsafe:verify`: đọc kết quả đã tạo, xác nhận các test tích hợp đạt điều kiện và **làm build thất bại nếu integration test không đạt**.

Cơ chế cần hiểu:

~~~text
pre-integration-test
    Start database / server
          │
          ▼
integration-test
    Failsafe chạy test
    Test assertion thất bại ──> ghi kết quả, thường chưa stop lifecycle
          │
          ▼
post-integration-test
    Stop database / server
          │
          ▼
verify
    Failsafe đọc kết quả ──> BUILD FAILURE nếu IT không đạt
~~~

Tách việc **ghi nhận lỗi test** và **kết luận lỗi build** giúp chạy goal cleanup ở giữa. Đây là lý do Failsafe phù hợp hơn việc tùy tiện gắn Surefire vào `integration-test`: Surefire có thể dừng ngay khi test failure, khiến teardown không có cơ hội chạy.

**Giới hạn quan trọng:** Failsafe không biến Maven thành một khối `try/finally` tuyệt đối. Nếu Maven bị kill, runner bị mất kết nối, setup plugin lỗi, JVM hỏng, lệnh teardown ném exception hoặc hệ điều hành dừng tiến trình, cleanup vẫn có thể bị bỏ qua. Vì vậy các hệ thống có container, server hoặc tài nguyên cloud thực tế còn cần cơ chế dọn dự phòng.

### Kết quả có thể gây hiểu nhầm

Trên Maven 3, khi chạy `mvn integration-test` với Failsafe và test có assertion failure, Maven có thể in `BUILD SUCCESS` cho lời gọi đó, dù test thực tế **không đạt**. Đó không phải trạng thái test PASS; goal `failsafe:verify` chưa chạy. Cần kiểm tra test report, goal verify và exit code của lệnh `mvn verify`.

Thư mục report thông thường:

~~~text
target/failsafe-reports/
    dev.example.EnvironmentIT.txt
    TEST-dev.example.EnvironmentIT.xml
    failsafe-summary.xml
~~~

Tên báo cáo có thể khác tùy plugin/test classname. `failsafe-summary.xml` là dữ liệu để `failsafe:verify` đánh giá; bản thân sự tồn tại của file không đủ chứng minh build đã xác minh thành công.

## 6. Rủi ro kỹ thuật khi bỏ qua các phase hậu

### 6.1. Server hoặc container treo

Một plugin khởi động PostgreSQL, Kafka, Redis, Jetty, Tomcat, một Docker Compose stack hoặc mock HTTP server tại `pre-integration-test`. Trên Maven 3, `mvn integration-test` không đi đến goal dừng ở `post-integration-test`. Server có thể tiếp tục lắng nghe cổng, giữ kết nối mạng và gây xung đột khi chạy lại test. Nếu JVM/process không thoát, cả job CI có thể tiếp tục treo.

### 6.2. Dữ liệu kiểm thử còn lại và làm kết quả không ổn định

Bài integration test có thể tạo bảng, record, user test, bucket, file tạm, database hoặc volume. Nếu cleanup bị bỏ qua, lần chạy sau đọc phải trạng thái cũ, làm test phụ thuộc thứ tự chạy hoặc bất ngờ báo lỗi vì dữ liệu đã tồn tại. Với CI chạy song song, hai job có thể tương tác cùng resource và tạo kết quả không đáng tin.

### 6.3. CI báo xanh sai

Failsafe có thể lưu lỗi test nhưng chưa báo build failure trước `verify`. Nếu CI coi exit code `mvn integration-test` là thành công toàn bộ, pipeline có nguy cơ cho phép merge/release dù integration test đỏ. Chỉ xem `BUILD SUCCESS` ở phase này là chưa đủ.

### 6.4. Báo cáo hoặc coverage chưa hoàn chỉnh

Plugin thống kê coverage có thể gắn việc thu thập/tổng hợp dữ liệu vào các phase sau integration test. Nếu bỏ qua, file coverage có thể chưa được hoàn thiện hoặc chưa đủ để đưa ra quyết định. Cần kiểm tra cả goal sinh report và goal kiểm tra ngưỡng coverage có chạy không.

### 6.5. Chi phí và ảnh hưởng môi trường dùng chung

VM, cloud database, cluster namespace, container/volume và dịch vụ ngoài máy phát triển có thể phát sinh chi phí hoặc giữ khóa. Cleanup thiếu có thể tác động người dùng khác. Cần luôn định danh tài nguyên theo build/job id và chỉ dọn phần **đúng job sở hữu**.

### 6.6. Cleanup chỉ chạy được khi được khai báo

Ngay cả `mvn verify` cũng **không tự dừng Docker**. Nếu POM không có goal dừng dịch vụ ở phase dọn, Maven sẽ đi qua phase đó mà không làm gì. Vì vậy phải kiểm tra hai điều kiện độc lập: **lệnh đã đi đủ phase** và **goal dọn dẹp đã được cấu hình đúng**.

## 7. Dự án thực hành Java 17: mô phỏng setup, test và teardown

Để tránh phải khởi động database hoặc container thật, ví dụ này dùng file `target/it-env/ready.txt` làm dấu hiệu một môi trường đã được chuẩn bị:

- `pre-integration-test` tạo file chứa chữ `READY`.
- `EnvironmentIT` xác minh file có tồn tại và nội dung đúng.
- `post-integration-test` xóa thư mục `target/it-env`.
- `verify` đánh giá kết quả Failsafe.

Nhờ vậy, sau `mvn integration-test` trên Maven 3 ta quan sát được **marker còn lại**; sau `mvn verify` ta quan sát được **marker biến mất**.

Điều kiện: JDK 17+, Maven 3.9.x, kết nối mạng để tải plugin/dependency ở lần chạy đầu. Tạo cấu trúc:

~~~text
integration-lifecycle-demo/
├── pom.xml
└── src/
    ├── main/java/dev/example/App.java
    └── test/java/dev/example/
        ├── AppTest.java
        └── EnvironmentIT.java
~~~

### 7.1. File pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>integration-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <it.forceFailure>false</it.forceFailure>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <systemPropertyVariables>
                        <it.marker.path>${project.build.directory}/it-env/ready.txt</it.marker.path>
                        <it.forceFailure>${it.forceFailure}</it.forceFailure>
                    </systemPropertyVariables>
                </configuration>
                <executions>
                    <execution>
                        <id>run-and-verify-integration-tests</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>prepare-integration-environment</id>
                        <phase>pre-integration-test</phase>
                        <goals><goal>run</goal></goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/it-env"/>
                                <echo file="${project.build.directory}/it-env/ready.txt"
                                      message="READY"/>
                            </target>
                        </configuration>
                    </execution>
                    <execution>
                        <id>teardown-integration-environment</id>
                        <phase>post-integration-test</phase>
                        <goals><goal>run</goal></goals>
                        <configuration>
                            <target>
                                <delete dir="${project.build.directory}/it-env"
                                        quiet="true"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ở cấu hình này:

- Compiler Plugin tạo bytecode cho Java 17.
- Surefire chạy unit test ở phase `test`.
- Failsafe có hai goal `integration-test` và `verify`. Khi đặt chúng trong `executions` như trên, Maven gắn từng goal theo **default phase do chính goal khai báo**; đây là cách cấu hình theo tài liệu chính thức.
- Antrun tạo marker ở `pre-integration-test` và xóa marker ở `post-integration-test`. Hai execution có `id` riêng để dễ kiểm tra log.
- `systemPropertyVariables` chuyển đường dẫn file marker và cờ lỗi test vào JVM mà Failsafe dùng; `it.forceFailure` mặc định `false` và có thể được ghi đè bởi `-Dit.forceFailure=true`.

Các goal Antrun ở đây chỉ tác động `target/it-env` của ví dụ. Trong dự án dùng Docker/Jetty thật, phần start/stop phải được thay bằng plugin hoặc script thích hợp với resource thực tế và đảm bảo an toàn khi chạy lại.

### 7.2. Class Java độc lập

Tạo `src/main/java/dev/example/App.java`:

~~~java
package dev.example;

public final class App {
    private App() {
    }

    public static String message() {
        return "Integration lifecycle ready";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Lệnh biên dịch và chạy chương trình:

~~~bash
mvn -B -ntp compile
java -cp target/classes dev.example.App
~~~

**Stdout chính xác của lệnh Java cuối:**

~~~text
Integration lifecycle ready
~~~

Lệnh `mvn compile` mới dừng ở `compile`, vì vậy chưa yêu cầu tạo marker ở phase `pre-integration-test`.

### 7.3. Unit test bằng JUnit 5

Tạo `src/test/java/dev/example/AppTest.java`:

~~~java
package dev.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void messageIsStable() {
        assertEquals("Integration lifecycle ready", App.message());
    }
}
~~~

Tên `AppTest` thuộc mẫu tìm unit test thông thường của Surefire. Nó kiểm tra mã Java, không phụ thuộc vào marker môi trường.

### 7.4. Integration test có thể gây lỗi có chủ đích

Tạo `src/test/java/dev/example/EnvironmentIT.java`:

~~~java
package dev.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class EnvironmentIT {
    @Test
    void environmentMustBePrepared() throws IOException {
        Path marker = Path.of(System.getProperty("it.marker.path"));

        assertTrue(Files.exists(marker),
                "pre-integration-test must create the marker");
        assertEquals("READY", Files.readString(marker).trim());
        assertEquals("Integration lifecycle ready", App.message());

        if (Boolean.parseBoolean(
                System.getProperty("it.forceFailure", "false"))) {
            fail("Intentional integration-test failure");
        }
    }
}
~~~

`EnvironmentIT` khớp mẫu `*IT.java` thường được Failsafe khám phá mặc định; class này **không** trùng mẫu `*Test.java` dùng để chạy unit test theo cấu hình Surefire phổ biến. Cả hai nằm ở `src/test/java` và đều được biên dịch tại `test-compile`.

Cờ `it.forceFailure` do dự án tự định nghĩa để thử luồng lỗi; nó không phải tham số có sẵn mang ý nghĩa đặc biệt của Failsafe.

## 8. Thực hành A: dừng ở integration-test

Chạy **trên Maven 3.9.x**, ở thư mục chứa POM:

~~~bash
mvn -version
mvn -B -ntp clean integration-test
~~~

Các thao tác dự kiến, theo thứ tự:

1. `clean` dọn output build cũ.
2. `compile`, `test-compile` và `test` biên dịch mã và chạy `AppTest`.
3. `package` tạo JAR chính.
4. `pre-integration-test` chạy Antrun `prepare-integration-environment` và tạo `target/it-env/ready.txt`.
5. `integration-test` chạy Failsafe và `EnvironmentIT` đọc marker `READY`.
6. Maven **dừng** tại `integration-test`; chưa chạy execution `teardown-integration-environment` và goal `failsafe:verify`.

Kiểm tra file trên Linux/macOS:

~~~bash
test -f target/it-env/ready.txt && echo "MARKER_EXISTS"
~~~

Với build thành công, stdout của lệnh kiểm tra trên:

~~~text
MARKER_EXISTS
~~~

Kiểm tra tương đương trên Windows PowerShell:

~~~powershell
Test-Path .\target\it-env\ready.txt
~~~

Kết quả dự kiến:

~~~text
True
~~~

Đó là bằng chứng có thể nhìn thấy: **setup đã tạo tài nguyên nhưng teardown chưa chạy**. Với server hoặc container thực, resource tương ứng có thể tiếp tục sử dụng CPU, RAM, cổng mạng hoặc tiền dịch vụ.

Đừng áp dụng kỳ vọng “MARKER_EXISTS” này cho Maven 4 mà không kiểm tra: Maven 4 đã thay đổi hành vi chạy phase hậu khi gọi phase chính.

## 9. Thực hành B: chạy đến verify để dọn dẹp

Trong cùng thư mục, chạy:

~~~bash
mvn -B -ntp verify
~~~

Trên Maven 3, Maven lại đi qua các phase cần thiết, tạo marker khi tới `pre-integration-test`, chạy `EnvironmentIT` rồi thực hiện `post-integration-test` và `failsafe:verify`. Bước teardown xóa thư mục `target/it-env`, còn report Failsafe dưới `target/failsafe-reports` vẫn được giữ lại để xem.

Trên Linux/macOS:

~~~bash
if test -f target/it-env/ready.txt; then
    echo "MARKER_REMAINS"
else
    echo "MARKER_CLEANED"
fi
~~~

Stdout kỳ vọng sau khi verify/cleanup thành công:

~~~text
MARKER_CLEANED
~~~

Trên Windows PowerShell:

~~~powershell
Test-Path .\target\it-env\ready.txt
~~~

Kết quả kỳ vọng:

~~~text
False
~~~

Trong log build, kiểm tra **thứ tự** các goal/execution sau (đây là mẫu nhận diện rút gọn, không phải toàn bộ log):

~~~text
maven-antrun-plugin:3.1.0:run (prepare-integration-environment)
maven-failsafe-plugin:3.5.2:integration-test (run-and-verify-integration-tests)
maven-antrun-plugin:3.1.0:run (teardown-integration-environment)
maven-failsafe-plugin:3.5.2:verify (run-and-verify-integration-tests)
~~~

Lệnh dùng trong CI khi cần chắc chắn không sử dụng output cũ:

~~~bash
mvn -B -ntp clean verify
~~~

Không cần chạy riêng `mvn package` trước `mvn verify` để “đảm bảo package”: `verify` nằm sau `package` và Maven tự thực hiện các phase trước đó.

## 10. Thực hành C: test thất bại nhưng teardown vẫn có cơ hội chạy

Chạy lệnh sau để cố ý làm `EnvironmentIT` báo assertion failure:

~~~bash
mvn -B -ntp clean integration-test -Dit.forceFailure=true
~~~

Ở đây `it.forceFailure` được chuyển vào JVM test theo cấu hình `systemPropertyVariables`. Failsafe sẽ ghi nhận lỗi `Intentional integration-test failure`. Với lỗi assertion thông thường, goal `failsafe:integration-test` được thiết kế để **chưa thất bại ngay**, nhằm cho các phase cleanup có cơ hội chạy. Tuy nhiên do lệnh dừng ở phase `integration-test` trên Maven 3, **teardown chưa được gọi** và `failsafe:verify` cũng chưa chạy. Vì vậy exit code của lệnh này có thể không phản ánh rằng integration test đỏ.

Bây giờ gọi:

~~~bash
mvn -B -ntp clean verify -Dit.forceFailure=true
~~~

Dự kiến:

1. Antrun tạo marker.
2. Failsafe chạy `EnvironmentIT` và ghi nhận test failure.
3. Antrun ở `post-integration-test` xóa marker.
4. Failsafe ở `verify` đọc kết quả và **làm build FAILED**.

Xem báo cáo:

~~~text
target/failsafe-reports/
    dev.example.EnvironmentIT.txt
    TEST-dev.example.EnvironmentIT.xml
    failsafe-summary.xml
~~~

Báo cáo có thể còn trên ổ đĩa dù marker đã được xóa, vì cleanup chỉ xóa `target/it-env`. Đó là lựa chọn đúng để CI còn lưu artifact report khi test thất bại.

**Chú ý về giới hạn:** Nếu lỗi xảy ra ở một goal setup, trong trình khởi chạy plugin, hoặc do runner/OS bị kill trước teardown thì lifecycle không bảo đảm gọi cleanup. Trường hợp thử này chỉ kiểm tra failure kiểu assertion được Failsafe ghi nhận đúng thiết kế.

Hoàn nguyên môi trường bằng lệnh bình thường:

~~~bash
mvn -B -ntp clean verify
~~~

Nếu các dependency/plugin và mã đều hợp lệ, build sẽ PASS trở lại.

## 11. Vì sao Maven 4 xử lý khác Maven 3?

Apache Maven 4 thay đổi cấu trúc phase:

| Tình huống | Maven 3.x | Maven 4.x |
| --- | --- | --- |
| Phase setup | `pre-integration-test` | `before:integration-test`; tên cũ có thể là alias tương thích |
| Phase teardown | `post-integration-test` | `after:integration-test`; tên cũ có thể là alias tương thích |
| Lệnh `mvn integration-test` | Dừng trước phase `post-integration-test` | Chạy các phase phụ `before:` và `after:` của phase `integration-test` |
| `failsafe:verify` | Cần đi đến `verify` | Vẫn cần đi đến `verify` |
| Lệnh nhất quán cho dự án có Failsafe | `mvn clean verify` | `mvn clean verify` vẫn rõ ràng, sau khi đã kiểm tra plugin tương thích |

Vì vậy, khi nâng Maven 3 → 4:

- Không lặp lại tuyên bố “integration-test chắc chắn không dọn resource” mà không phân biệt version.
- Đọc hướng dẫn di chuyển để chuyển binding từ `pre-integration-test`/`post-integration-test` sang `before:integration-test`/`after:integration-test`.
- Kiểm tra compatibility của Failsafe, plugin điều khiển container, plugin coverage, profile và parent POM với Maven 4.
- Tiếp tục dùng `verify` làm mốc kết luận kiểm thử tích hợp, thay vì coi `integration-test` là kết quả cuối.
- Chạy một bài test cố ý thất bại và quan sát teardown trên Maven version thực tế trước khi đổi CI.

Thay đổi phase của Maven 4 **không** bảo đảm resource cleanup khi tiến trình bị ngắt bất thường. Quy tắc dự phòng ở mục tiếp theo vẫn có giá trị.

## 12. Tổ chức cleanup đáng tin cậy trong dự án thật

Một quy trình tốt cần đủ ba lớp:

**Lớp 1 — lifecycle:** plugin start ở phase setup và plugin stop ở phase teardown. Lệnh CI đi đến `verify` và có Failsafe `integration-test` + `verify`.

**Lớp 2 — dọn dự phòng:** CI dùng bước cuối job để cố gắng tắt resource ngay cả khi Maven fail. Ví dụ nếu dự án thực sự có file `compose.it.yml` được cấu hình riêng cho integration test, có thể dùng một bước GitHub Actions:

~~~yaml
steps:
  - name: Checkout source
    uses: actions/checkout@v4

  - name: Configure Java
    uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'

  - name: Run verification
    run: ./mvnw -B -ntp clean verify

  - name: Cleanup integration containers
    if: always()
    run: docker compose -f compose.it.yml down --remove-orphans
~~~

Đây là **đoạn steps**, không phải workflow hoàn chỉnh; job cần `runs-on`, Maven Wrapper và `compose.it.yml` thực sự tồn tại. Bước `if: always()` cho phép cố gắng dọn cả khi Maven báo FAIL, nhưng không giải quyết mọi trường hợp runner bị mất hoặc bị ngắt cưỡng bức. Dùng đúng compose project name/working directory để chỉ xóa resource của job này.

**Lớp 3 — quản lý tài nguyên:** đặt resource name theo job/build id, dùng TTL khi có thể, cô lập môi trường test và ghi log tài nguyên đã tạo. Nếu sử dụng cloud, cần cơ chế dọn tài nguyên mồ côi khi runner không còn sống. Đừng để cleanup “quét hết” container hoặc volume vì có thể xóa dữ liệu của người khác.

Một tác vụ cleanup nên:

- **Idempotent:** chạy lại an toàn khi resource đã được dọn.
- **Giới hạn phạm vi:** chỉ tác động tài nguyên do job sở hữu.
- **Có thể xác minh:** sau cleanup có lệnh kiểm tra container/process/file/port còn hay không.
- **Không che lỗi chính:** lưu lại kết quả test thất bại và lỗi cleanup riêng.
- **Giữ bằng chứng:** lưu Failsafe reports trước khi xóa báo cáo hoặc thư mục build.

Nếu dùng hai cơ chế dọn (teardown trong Maven và dọn dự phòng trong CI), chúng phải hoạt động an toàn ngay cả khi cùng chạy; tránh quy trình xóa hai lần nhưng lần thứ hai lại bị xem là lỗi nghiêm trọng.

## 13. Trường hợp `mvn verify` vẫn để lại dịch vụ

Xét POM có dạng:

~~~text
pre-integration-test: start-database
integration-test:     failsafe:integration-test
post-integration-test:(không có stop-database)
verify:              failsafe:verify
~~~

Maven có đi qua `post-integration-test`, nhưng **không có goal nào dọn database**. Vì vậy server có thể tiếp tục chạy dù `verify` báo PASS. Cần thêm goal stop phù hợp, không sửa lệnh thành `mvn integration-test` hay chỉ đổi Failsafe.

Các trường hợp tương tự gồm:

- Cleanup goal nằm trong profile chưa bật.
- Parent POM khai báo execution nhưng module không kế thừa/kích hoạt như dự kiến.
- Start và stop không dùng cùng resource id, project name hoặc môi trường.
- Stop goal được gắn vào phase sau `verify` hoặc dùng sai phase.
- Resource được tạo bởi script ngoài Maven mà plugin teardown không biết.
- Failsafe hoàn thành nhưng báo cáo bị xóa trước khi CI lưu lại.

Hãy kiểm tra effective POM và log goal thực tế, không chỉ đọc tên phase.

## 14. Quy trình xử lý sự cố từng bước

Khi CI có container treo, cổng bị chiếm hoặc kết quả integration test không đáng tin:

1. **Xác định lệnh đã gọi:** `mvn integration-test`, `mvn failsafe:integration-test` hay `mvn verify`? Có `clean` không?
2. **Xác định Maven core:** `mvn -version` hoặc Wrapper `-version`. Maven 3 và 4 có khác biệt phase hậu.
3. **Xem execution plan:** kiểm tra `<build><plugins><executions>`, parent, profile và packaging.
4. **Tìm goal setup:** có `pre-integration-test` (Maven 3) hoặc `before:integration-test` (Maven 4) không?
5. **Tìm goal teardown:** đúng phase, đúng plugin, cùng resource ID không? Có lỗi trong log không?
6. **Đọc Failsafe reports:** số lượng test thực sự chạy, test error/failure, summary và goal verify.
7. **Kiểm tra tài nguyên còn lại:** theo job id; không xóa nhầm dịch vụ dùng chung.
8. **Kiểm tra nguyên nhân ngắt:** timeout, cancel, JVM crash, mất điện, plugin setup lỗi.
9. **Sửa tại cơ chế:** lệnh `verify`, Failsafe goal, teardown và cleanup CI dự phòng.
10. **Kiểm chứng lại:** chạy pass case và failure injection; xác minh trạng thái sau cùng đúng.

Các lệnh tham khảo:

~~~bash
mvn -B -ntp help:effective-pom
mvn -B -ntp help:describe -Dplugin=org.apache.maven.plugins:maven-failsafe-plugin -Dgoal=integration-test -Ddetail
mvn -B -ntp help:describe -Dplugin=org.apache.maven.plugins:maven-failsafe-plugin -Dgoal=verify -Ddetail
~~~

`help:effective-pom` cho thấy cấu hình đã áp dụng inheritance/profile. `help:describe` cung cấp thông tin goal. Cả hai có thể tải Maven Help Plugin nếu chưa có trong cache. Dùng chúng để đối chiếu phase mặc định và cấu hình execution, không suy ra chỉ từ một dòng `BUILD SUCCESS`.

## 15. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| “`mvn integration-test` dọn sạch resource trong mọi Maven.” | Trên Maven 3 sẽ dừng trước `post-integration-test`; Maven 4 có `after:` mới. |
| “`BUILD SUCCESS` ở integration-test nghĩa là mọi IT đều PASS.” | Failsafe có thể trì hoãn báo lỗi test đến `failsafe:verify`. |
| “`mvn failsafe:verify` là tương đương `mvn verify`.” | Goal trực tiếp không tự chạy mọi phase setup/test/cleanup. |
| “`mvn verify` tự động dừng Docker.” | Chỉ khi có goal dọn được bind và hoạt động đúng. |
| “Đổi Surefire thành Failsafe là đủ.” | Còn phải đặt test naming, dependencies, setup/teardown và goal verify đúng. |
| “Đặt `*IT.java` sẽ tự chạy integration test.” | Cần plugin Failsafe và execution phù hợp; kiểm tra test count. |
| “Không có lỗi test nên không cần teardown.” | Resource vẫn có thể giữ cổng/chi phí dù mọi assertion PASS. |
| “Failsafe luôn cleanup ngay cả khi máy bị kill.” | Maven lifecycle không phải `finally` chống mọi loại ngắt. |
| “`post-integration-test` là một goal của Failsafe.” | Đây là **phase** của Maven 3, còn cleanup goal do plugin khác cung cấp. |
| “Có `failsafe-summary.xml` là đủ chứng minh verification PASS.” | Phải xem goal `failsafe:verify` và trạng thái build cuối. |

## 16. Bài tập tự kiểm tra

**Bài 1 — dự đoán trước khi chạy.** Với POM ở mục 7 trên Maven 3, chạy `mvn clean integration-test`. Marker còn hay mất? Goal nào đã chạy? **Đáp án:** marker còn; Failsafe `integration-test` đã chạy, Antrun teardown và Failsafe `verify` chưa chạy.

**Bài 2 — sửa lệnh.** Thay bằng `mvn clean verify`. Cần quan sát gì? **Đáp án:** test chạy, teardown ở `post-integration-test` xóa marker, Failsafe `verify` kết luận kết quả; marker không còn sau build.

**Bài 3 — kiểm tra exit code.** Gây lỗi với `-Dit.forceFailure=true` rồi so sánh `mvn integration-test` và `mvn verify`. **Đáp án:** trên Maven 3, kết quả Failsafe ở integration-test có thể chưa làm command fail; ở `verify` test failure được đánh dấu FAILURE sau khi teardown có cơ hội chạy.

**Bài 4 — không có plugin cleanup.** Nếu xóa execution `teardown-integration-environment` khỏi POM nhưng vẫn gọi `mvn verify`, marker ra sao? **Đáp án:** có thể còn, vì phase được đi qua nhưng không có goal xóa marker.

**Bài 5 — Maven 4.** Có thể khẳng định `mvn integration-test` trên Maven 4 luôn bỏ qua `post-integration-test` không? **Không.** Maven 4 chạy `after:integration-test` với phase chính. Tuy vậy, vẫn cần `verify` để xác nhận kết quả Failsafe.

**Bài 6 — thiết kế CI.** Với PostgreSQL chạy trong Docker Compose, hãy chỉ ra (a) nơi start, (b) nơi chạy IT, (c) nơi stop, (d) nơi verify, (e) cơ chế cuối job để dọn tài nguyên mồ côi. Bản thiết kế đạt khi job test thất bại vẫn báo FAILED, resource được dọn an toàn và report được giữ lại.

## 17. Checklist áp dụng vào dự án Maven

- [ ] Xác định Maven 3/Maven 4 qua phiên bản runtime thực tế.
- [ ] Kiểm tra setup, integration-test, teardown và verify được gắn vào đúng phase.
- [ ] Dùng Maven Failsafe với đủ goal `integration-test` và `verify`.
- [ ] Trên Maven 3, tránh dùng `mvn integration-test` làm lệnh CI cuối.
- [ ] Trên Maven 4, kiểm tra `before:`/`after:`, alias phase cũ và plugin compatibility.
- [ ] Có test thực sự được Failsafe khám phá và báo cáo số lượng test.
- [ ] Đã thực hiện kiểm thử lỗi có chủ đích để chứng minh `verify` báo FAIL đúng.
- [ ] Cleanup xóa đúng resource theo job id và idempotent.
- [ ] Có bước cleanup dự phòng cho lỗi setup, timeout hoặc cancel.
- [ ] Có cách xác minh tài nguyên đã tắt sau build.
- [ ] Lưu Failsafe reports/coverage cần thiết để phân tích, không xóa sớm.
- [ ] Không dùng `BUILD SUCCESS` ở riêng `integration-test` để tuyên bố IT PASS.

## 18. Tài liệu chính thức

1. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): thứ tự phase, rủi ro gọi `integration-test` trên Maven 3 và ghi chú hành vi Maven 4.
2. [Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/index.html): mục đích Failsafe, `integration-test` và `verify`, báo cáo kết quả.
3. [Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html): cấu hình plugin và hai goal trong POM.
4. [Apache Maven — What's new in Maven 4?](https://maven.apache.org/whatsnewinmaven4.html): các phase `before:`/`after:` và thay đổi phạm vi thực thi khi gọi phase.
5. [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html): chuyển cấu hình phase `pre-integration-test` và `post-integration-test`.
6. [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): execution, phase và goal binding.
