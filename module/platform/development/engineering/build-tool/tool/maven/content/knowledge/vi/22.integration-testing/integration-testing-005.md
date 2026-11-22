# Khởi tạo tài nguyên ở pre-integration-test và dọn ở post-integration-test với Maven

## 1. Bài toán: integration test cần môi trường sống tạm thời

Một unit test có thể kiểm tra hàm `add(2, 3)` chỉ bằng bộ nhớ và một vài assertion. Integration test thường khác: ứng dụng cần một cơ sở dữ liệu, một HTTP service, một hàng đợi, một thư mục dữ liệu, một server được deploy hoặc một file cấu hình tạm để kiểm tra sự phối hợp giữa nhiều thành phần.

Nếu tài nguyên chưa sẵn sàng trước khi test chạy, test có thể lỗi giả:

- HTTP client nhận `Connection refused` vì server chưa khởi động.
- Test đọc file nhưng `NoSuchFileException` vì fixture chưa tạo.
- Database test nhận `Connection refused` hoặc lỗi schema vì database chưa sẵn sàng.
- Hai job CI cùng dùng một cổng, database hoặc volume khiến test lúc pass lúc fail.

Nếu tài nguyên không được dọn sau test, những lần build tiếp theo có thể chịu hậu quả:

- Server/process còn chạy chiếm cổng.
- Container và volume tiêu tốn tài nguyên.
- Dữ liệu tạm tạo kết quả không ổn định.
- Secret hoặc dữ liệu test còn nằm trên máy sau khi job kết thúc.
- CI worker hết dung lượng hoặc nhiễm trạng thái từ lần chạy trước.

Maven cung cấp những **phase** trong default lifecycle để tổ chức việc này:

~~~text
package
   |
   v
pre-integration-test   -> chuẩn bị/khởi động tài nguyên
   |
   v
integration-test       -> chạy integration tests
   |
   v
post-integration-test  -> dừng và dọn tài nguyên
   |
   v
verify                 -> xác nhận integration tests đạt yêu cầu
~~~

**Điểm trọng tâm:** ở Maven **3.9.x**, hãy chạy `mvn verify` (hoặc `mvn clean verify` khi cần build sạch), **không** chạy riêng `mvn integration-test` nếu bạn cần chắc chắn post-integration-test và verify được thực hiện.

Bài sử dụng Maven 3.9.x, Java 17, JUnit Jupiter 5, Maven Failsafe Plugin 3.5.4, Maven Surefire Plugin 3.5.4 và Maven AntRun Plugin 3.1.0. Tất cả version đều là ví dụ được ghim, không có nghĩa luôn mới nhất. Có thể áp dụng tư duy tương tự cho database, container và server thật, nhưng ví dụ chạy được chủ ý dùng **file fixture dưới thư mục target** để không cần cài Docker hoặc database.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Nêu đúng nhiệm vụ và thứ tự của `pre-integration-test`, `integration-test`, `post-integration-test` và `verify`.
2. Phân biệt **phase Maven** với **goal plugin** và biết rằng phase trống sẽ không tự thực hiện thao tác nào.
3. Viết POM khai một goal tạo tài nguyên ở `pre-integration-test` và goal xóa đúng tài nguyên ấy ở `post-integration-test`.
4. Dùng **Failsafe** chạy integration tests và **Failsafe verify** báo kết quả sau cleanup, thay vì dùng Surefire để chạy IT sai thời điểm.
5. Chạy một project Java 17/JUnit 5 hoàn chỉnh, kiểm chứng fixture tồn tại khi test chạy nhưng không tồn tại sau `verify`.
6. Chứng minh bằng thí nghiệm rằng **assertion failure của Failsafe thường không ngăn phase cleanup**, song Maven lifecycle không phải khối `finally` tuyệt đối.
7. Nhận diện các lỗi như sai phase, test không được discovery, thiếu server readiness, cổng trùng, test fail mà build báo success tạm thời, lệnh bỏ qua IT nhưng setup vẫn chạy.
8. Áp dụng cleanup an toàn, idempotent, giới hạn phạm vi tài nguyên và phù hợp CI/multi-module.

---

## 2. Bốn phase và trách nhiệm của từng phase

Trong Maven 3 default lifecycle, những phase quan trọng bao gồm:

~~~text
validate
  ...
compile
  ...
test-compile
test
  ...
package
pre-integration-test
integration-test
post-integration-test
verify
install
deploy
~~~

Khi gọi một phase, Maven chạy các phase cần thiết **từ đầu default lifecycle đến phase đó** theo thứ tự. Một phase không có goal được bind có thể hoàn toàn không có việc gì để thực hiện.

| Phase | Mục đích | Tác vụ tiêu biểu |
| --- | --- | --- |
| `pre-integration-test` | Chuẩn bị môi trường sau khi đã tạo package | Start server, tạo database/schema test, provision fixture, bắt đầu container |
| `integration-test` | Chạy và thu thập kết quả integration tests | Goal `failsafe:integration-test`, request HTTP, query database |
| `post-integration-test` | Dọn tài nguyên sau khi chạy integration test | Stop server, xóa fixture/volume, thu log, đóng connection, deprovision container |
| `verify` | Kiểm tra integration test result và các quality gates | Goal `failsafe:verify` kết luận pass/fail, kiểm tra package |

### 2.1. Phase tự nó không tạo database

Viết:

~~~bash
mvn pre-integration-test
~~~

chỉ đưa Maven tới phase đó. Nếu POM không có plugin goal được bind ở `pre-integration-test`, sẽ **không có database hoặc service nào tự khởi động**.

Bạn phải cấu hình một plugin cung cấp goal thật, ví dụ AntRun Plugin tạo fixture, plugin của server dùng goal `start`, một plugin container chạy `start` hoặc một script đã được kiểm soát. Gắn goal vào phase đúng vị trí:

~~~xml
<execution>
    <id>prepare-it-resource</id>
    <phase>pre-integration-test</phase>
    <goals>
        <goal>run</goal>
    </goals>
</execution>
~~~

Đây là **trích đoạn của một plugin có goal `run`**, trong bài là AntRun; không phải một POM độc lập. Một plugin khác có thể gọi goal là `start` hoặc `up`, không thể tùy ý dùng `run` nếu plugin đó không cung cấp goal ấy.

### 2.2. Tại sao pre-integration-test nằm sau package?

Một integration test có thể cần chính JAR, WAR hoặc image được build. Từ `mvn verify`, Maven đã đi qua `package` trước khi bắt đầu phase chuẩn bị tài nguyên, nên plugin deployment có thể lấy artifact vừa được tạo.

Ngược lại, `mvn test` kết thúc **trước** `package` và `pre-integration-test`. Đừng đòi một integration fixture đã được tạo chỉ bằng lệnh `mvn test` nếu bạn bind nó vào pre-integration-test.

### 2.3. Tại sao phải có verify riêng?

Trong mô hình Maven 3, nếu lỗi assertion làm build dừng ngay tại `integration-test`, những goal ở `post-integration-test` sẽ không được gọi. Maven Failsafe giải quyết tình huống test failure bằng việc **ghi nhận lỗi kiểm thử tại `integration-test` và để `failsafe:verify` đánh dấu build thất bại sau phase cleanup**.

**Quan trọng:** cơ chế này giúp qua được các **test assertion failures** thông thường. Nó không biến mọi lỗi Maven/plugin thành một luồng cleanup đảm bảo. Một plugin start server lỗi ngay tại pre-integration-test, Maven bị kill, máy hết điện hay CI runner bị hủy có thể khiến phase sau không chạy.

---

## 3. Vì sao cần Failsafe thay cho Surefire để chạy integration tests?

Trong Maven, hai plugin cùng họ nhưng phục vụ hai mục đích khác nhau:

| Thành phần | Maven Surefire Plugin | Maven Failsafe Plugin |
| --- | --- | --- |
| Mục tiêu thông thường | Unit tests | Integration tests |
| Goal | `surefire:test` | `failsafe:integration-test` và `failsafe:verify` |
| Phase | `test` | `integration-test` và `verify` |
| File mặc định thường gặp | `*Test.java`, `*Tests.java`, `Test*.java` | `*IT.java`, `IT*.java`, `*ITCase.java` |
| Reports | `target/surefire-reports` | `target/failsafe-reports` |
| Khi assertion test thất bại | Thường dừng build tại phase `test` | Ghi kết quả ở integration-test, kết luận thất bại ở verify |
| Phù hợp tài nguyên IT tạo ở pre? | Không phải thiết kế chuẩn | Có, vì IT nằm giữa pre và post |

Các pattern là mặc định của plugin, có thể được sửa bằng `includes/excludes`. Một tên test theo đúng quy ước giúp tránh tình huống Surefire chạy integration test quá sớm, lúc fixture chưa tồn tại.

### 3.1. Sai thiết kế: ép integration tests chạy bằng Surefire tại phase IT

Maven Failsafe documentation giải thích lý do tách `integration-test` và `verify`: Surefire được thiết kế cho unit tests. Nếu một goal kiểm thử thất bại làm Maven kết thúc trước `post-integration-test`, môi trường kiểm thử có thể còn chạy.

Không nên giải quyết vấn đề bằng cách “chạy Surefire lần nữa trong integration-test” mà không hiểu cách fail-fast của goal. Hãy dùng Failsafe được thiết kế cho integration test lifecycle.

### 3.2. Failsafe không được kích hoạt chỉ vì có dependency JUnit

JUnit là **test framework**. Failsafe là **Maven build plugin**. Dù có lớp `FixtureLifecycleIT.java` được biên dịch, chỉ khai JUnit trong dependencies **không tự bind** hai goal Failsafe vào lifecycle.

Cần có plugin execution tương ứng với `integration-test` và `verify`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.4</version>
    <executions>
        <execution>
            <id>run-integration-tests</id>
            <phase>integration-test</phase>
            <goals>
                <goal>integration-test</goal>
            </goals>
        </execution>
        <execution>
            <id>check-integration-results</id>
            <phase>verify</phase>
            <goals>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đoạn này là **snippet plugin**. Chúng ta sẽ đặt một phiên bản cấu hình đầy đủ vào POM runnable ở mục 7. Khai tường minh hai execution/phase giúp thấy rõ trách nhiệm của từng goal, dù plugin descriptors cũng định nghĩa default phase cho các goal.

---

## 4. Cách thiết kế vòng đời tài nguyên đúng

Với một resource tạm, hãy xây dựng hợp đồng rõ ràng:

~~~text
PREPARE
  1. xác định tên/path/port tài nguyên riêng cho build
  2. dọn trạng thái cũ đúng phạm vi nếu cần
  3. tạo hoặc khởi động tài nguyên
  4. kiểm tra readiness; chỉ báo thành công khi sẵn sàng
           |
           v
TEST
  5. gọi tài nguyên bằng thông tin kết nối đã công bố
  6. xác minh hành vi và ghi report
           |
           v
CLEANUP
  7. thu diagnostic logs cần thiết
  8. dừng resource nếu đang chạy
  9. xóa fixture, temporary files, volumes được phép
 10. xác nhận resource thật sự không còn
           |
           v
VERIFY
 11. báo build PASS/FAIL từ IT report và quality gates
~~~

Một resource tốt cho IT cần đáp ứng:

- **Isolated**: mỗi build có ID/path/port riêng khi có thể, không làm hỏng test khác.
- **Deterministic**: cùng đầu vào tạo trạng thái phù hợp, test không phụ thuộc dữ liệu còn từ lần trước.
- **Ready before use**: không nhầm “process đã spawn” với “HTTP/database đã sẵn sàng”.
- **Idempotent cleanup**: xóa/dừng một resource đã không còn tồn tại nên là thao tác an toàn trong phạm vi bài test.
- **Least privilege**: job chỉ được xóa những gì nó tạo; không chạm production database hoặc thư mục dùng chung.
- **Observable**: log, marker, report hoặc health checks cho thấy thời điểm setup, test, teardown.
- **Recoverable**: CI có cleanup dự phòng cho tình huống Maven bị hủy cứng, không đặt mọi hy vọng vào post-integration-test.

Ví dụ runnable dưới đây minh họa các nguyên tắc bằng **thư mục tạm dưới `target/it-fixture`**. Sau đó bài sẽ giải thích cách chuyển mô hình này thành server/container/database thật.

---

## 5. Vì sao nên đặt fixture dưới target?

`target` là thư mục build output mặc định của Maven. Dùng:

~~~text
target/it-fixture/
└── state.txt
~~~

có ba lợi ích:

1. `mvn clean` dọn output cũ của build, giúp thí nghiệm rõ ràng.
2. Đường dẫn dựa trên `${project.build.directory}` nên không hardcode `C:\...` hay `/tmp/...`.
3. Một module bình thường có `target` riêng, giảm rủi ro ghi đè dữ liệu của module khác.

Trong production CI, còn cần tránh dùng cùng working directory cho **hai build chạy đồng thời**. Thư mục `target` riêng giữa module không có nghĩa giữa hai job cùng workspace đã được cách ly. Nếu chạy song song, dùng workspace/container/job ID riêng.

### 5.1. Fixture có phải integration resource “thật” không?

Một file tạm không cần service/network, nên nó là **bài tập tối giản về vòng đời fixture**, không chứng minh toàn bộ hành vi của một database hay HTTP service. Điểm đáng học là Maven thực thi mục tiêu setup/cleanup **ở đúng phase** và integration test quan sát được trạng thái trung gian.

Khi ứng dụng thực dùng database, hãy thay goal tạo file bằng goal provision database và thay goal xóa file bằng goal teardown database, kèm readiness, ownership và timeouts. Không giả vờ rằng một marker file là bằng chứng database đã kết nối được.

---

## 6. Ví dụ hoàn chỉnh: một project Maven có unit test và integration test

Dự án sẽ có:

- Một ứng dụng Java 17 chạy được.
- Một unit test `AppTest` chạy trong phase `test`.
- Một integration test `FixtureLifecycleIT` chạy trong `integration-test`.
- Maven AntRun Plugin tạo fixture ở `pre-integration-test` và xóa nó ở `post-integration-test`.
- Maven Failsafe Plugin kiểm tra integration test results tại `verify`.
- Một cờ `it.force.failure` để **cố tình làm một test fail** và kiểm tra rằng cleanup vẫn chạy trong tình huống assertion failure bình thường.

### 6.1. Cây thư mục

~~~text
it-resource-lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/vn/example/itlifecycle/App.java
    └── test/
        └── java/vn/example/itlifecycle/
            ├── AppTest.java
            └── FixtureLifecycleIT.java
~~~

Yêu cầu môi trường: Maven **3.9.x**, JDK **17+**, network/repository Maven đã cấu hình để lấy plugin/JUnit nếu chưa cache.

### 6.2. POM hoàn chỉnh: pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>it-resource-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <it.force.failure>false</it.force.failure>
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
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.itlifecycle.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
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
                                <echo file="${project.build.directory}/it-fixture/state.txt"
                                      message="READY"/>
                                <echo file="${project.build.directory}/it-setup.marker"
                                      message="SETUP_DONE"/>
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
                                <echo file="${project.build.directory}/it-cleanup.marker"
                                      message="CLEANUP_DONE"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.4</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <it.fixture.dir>${project.build.directory}/it-fixture</it.fixture.dir>
                        <it.force.failure>${it.force.failure}</it.force.failure>
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
                        <id>verify-integration-tests</id>
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
~~~

Đây là POM **hoàn chỉnh**. Hãy giữ nguyên tên class, package và các đường dẫn của source bên dưới để chương trình và tests khớp nhau.

### 6.3. Phân tích từng khối POM

**Compiler Plugin 3.14.1:** tạo bytecode cho Java 17 theo `maven.compiler.release=17`. Nó không khởi động server hay tạo fixture IT.

**Surefire Plugin 3.5.4:** được Maven gắn vào phase `test` của packaging `jar`. Nó chạy `AppTest` (unit test) và theo các include patterns mặc định **không chạy `FixtureLifecycleIT`** trong phase test.

**JAR Plugin 3.4.2:** tạo JAR ở `package` và thêm `Main-Class`. Khi Maven đi tới `pre-integration-test`, artifact đã được package.

**AntRun Plugin 3.1.0:** được đặt trong `build/plugins` với hai **execution ids khác nhau**, hai phase khác nhau và cùng goal `run`:

- `prepare-it-fixture` chạy ở `pre-integration-test`, tạo thư mục `it-fixture`, ghi `state.txt` bằng `READY` và tạo dấu mốc `it-setup.marker`.
- `cleanup-it-fixture` chạy ở `post-integration-test`, xóa **đúng** thư mục `it-fixture`, rồi tạo `it-cleanup.marker` để chứng minh goal cleanup đã được thực thi.

**Failsafe Plugin 3.5.4:** chạy integration tests ở `integration-test`. Trong test fork JVM, nó truyền hai system properties:

~~~text
it.fixture.dir = đường dẫn target/it-fixture của project
it.force.failure = false mặc định
~~~

`it.fixture.dir` là đường dẫn cấu hình, **không tự tạo file**. File phải được AntRun setup tạo ra. `it.force.failure` chỉ phục vụ thí nghiệm failure, không làm thay đổi logic production app.

**Failsafe `failIfNoTests=true`:** trong ví dụ kiểm chứng, nếu không tìm thấy integration test nào thì build phải fail thay vì im lặng qua. Với project thật có một vài module không chứa IT, hãy đặt option này đúng module hoặc profile, không ép vào mọi module aggregator.

### 6.4. Lưu ý về XML tên system properties

Trong `systemPropertyVariables`, hai tên `it.fixture.dir` và `it.force.failure` là **tên Java system properties** truyền vào test JVM. Dấu chấm là hợp lệ trong tên XML element kiểu này, và test đọc bằng:

~~~java
System.getProperty("it.fixture.dir")
Boolean.getBoolean("it.force.failure")
~~~

Hai giá trị này không tự động trở thành Java environment variables hoặc file config. Muốn truyền endpoint cho server thật, thường khai một property tương tự `it.base.url` rồi test đọc nó, thay vì hardcode URL vào source test.

---

## 7. Mã Java và unit test

### 7.1. App.java

File `src/main/java/vn/example/itlifecycle/App.java`:

~~~java
package vn.example.itlifecycle;

public final class App {
    private App() {
    }

    public static String status() {
        return "BUILD READY";
    }

    public static void main(String[] args) {
        System.out.println(status());
    }
}
~~~

Đây là Java 17 hợp lệ, không cần thư viện runtime ngoài JDK.

Stdout **chính xác** của `App.main`:

~~~text
BUILD READY
~~~

Lưu ý: lệnh `mvn clean verify` không tự gọi `App.main`. Chỉ khi bạn chạy `java` hoặc một plugin execution riêng gọi main thì dòng stdout này mới xuất hiện.

### 7.2. AppTest.java: unit test không cần fixture

File `src/test/java/vn/example/itlifecycle/AppTest.java`:

~~~java
package vn.example.itlifecycle;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void statusIsStable() {
        assertEquals("BUILD READY", App.status());
    }
}
~~~

Tên `AppTest` khớp quy tắc khám phá mặc định của Surefire. Test này hoàn toàn không đọc `it-fixture`, nên chạy được **trước pre-integration-test** ở phase `test`. Mong đợi **1 unit test PASS**.

Phân tách này quan trọng: nếu unit test bị phụ thuộc vào database/server chưa được setup, bạn đã làm mờ ranh giới giữa unit và integration tests.

---

## 8. Integration test: fixture phải tồn tại trong khi Failsafe chạy

### 8.1. FixtureLifecycleIT.java

Tạo `src/test/java/vn/example/itlifecycle/FixtureLifecycleIT.java`:

~~~java
package vn.example.itlifecycle;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class FixtureLifecycleIT {
    @Test
    void fixtureIsReadyDuringIntegrationTest() throws IOException {
        String fixtureDirectory = System.getProperty("it.fixture.dir");
        assertNotNull(fixtureDirectory, "Missing it.fixture.dir");

        Path file = Path.of(fixtureDirectory, "state.txt");
        assertTrue(Files.isRegularFile(file), "Missing prepared state.txt");

        String content = Files.readString(file, StandardCharsets.UTF_8).trim();
        assertEquals("READY", content);
    }

    @Test
    void optionalFailureDemonstratesCleanupOrder() {
        assertFalse(
                Boolean.getBoolean("it.force.failure"),
                "Intentional integration-test failure"
        );
    }
}
~~~

Có **2 integration tests**:

1. `fixtureIsReadyDuringIntegrationTest` xác nhận AntRun đã chuẩn bị file trước khi Failsafe bắt đầu.
2. `optionalFailureDemonstratesCleanupOrder` pass khi `it.force.failure=false`. Khi chạy `-Dit.force.failure=true`, test này cố tình fail, giúp quan sát việc Failsafe không làm gián đoạn cleanup thông thường chỉ vì assertion failure.

Tên file kết thúc `IT.java`, thuộc các pattern mặc định của Failsafe. Nó **không kết thúc `Test.java`**, vì vậy Surefire không nhận nó như unit test mặc định.

### 8.2. Vì sao test đọc file thay vì tạo file?

Nếu integration test tự gọi `Files.createDirectories` rồi tự ghi `state.txt`, nó sẽ không chứng minh Maven setup phase đã hoạt động. Ở ví dụ này, **test chỉ đọc và kiểm chứng tài nguyên**, không tạo nó.

Tách trách nhiệm:

- POM/AntRun setup → tạo fixture.
- Failsafe/JUnit → đọc, kiểm chứng fixture đã sẵn sàng.
- POM/AntRun cleanup → xóa fixture.
- Failsafe verify → báo kết quả kiểm thử.

Đây là tiêu chí quan trọng của một bài thực hành nhằm kiểm tra **vòng đời tài nguyên**, không chỉ kiểm tra API đọc file.

### 8.3. Khi tài nguyên thật là HTTP server

Thay vì `Path.of(...)`, integration test có thể nhận URL từ `System.getProperty("it.base.url")` rồi gửi HTTP request. Nhưng test vẫn nên **không tự khởi động** server nếu trách nhiệm start/stop được giao cho Maven pre/post phases.

Có ngoại lệ hợp lý: một test tự dùng Testcontainers hoặc một extension quản lý resource riêng. Khi đó nên chọn **một owner duy nhất** của vòng đời tài nguyên để tránh Maven cleanup và test framework cùng xóa một container.

---

## 9. Thực thi bình thường: mvn clean verify

Từ thư mục `it-resource-lifecycle-demo` chạy:

~~~bash
mvn -version
java -version
mvn clean verify
~~~

Quy trình mong đợi:

~~~text
clean
  |
  v
compile + test-compile
  |
  v
test
  |--> Surefire chạy AppTest (1 PASS)
  |
  v
package
  |--> JAR plugin tạo it-resource-lifecycle-demo-1.0.0.jar
  |
  v
pre-integration-test
  |--> antrun:run (prepare-it-fixture)
  |--> tạo target/it-fixture/state.txt = READY
  |--> tạo target/it-setup.marker
  |
  v
integration-test
  |--> failsafe:integration-test
  |--> FixtureLifecycleIT: 2 tests PASS
  |
  v
post-integration-test
  |--> antrun:run (cleanup-it-fixture)
  |--> xóa target/it-fixture/
  |--> tạo target/it-cleanup.marker
  |
  v
verify
  |--> failsafe:verify: PASS
  |
  v
BUILD SUCCESS
~~~

Đây là **diễn giải thứ tự và số test mong đợi**, không phải nguyên văn toàn bộ log Maven.

### 9.1. Các file sau một lần build sạch thành công

~~~text
target/
├── classes/vn/example/itlifecycle/App.class
├── test-classes/vn/example/itlifecycle/AppTest.class
├── test-classes/vn/example/itlifecycle/FixtureLifecycleIT.class
├── it-setup.marker
├── it-cleanup.marker
├── it-resource-lifecycle-demo-1.0.0.jar
├── surefire-reports/
│   └── TEST-vn.example.itlifecycle.AppTest.xml
└── failsafe-reports/
    ├── TEST-vn.example.itlifecycle.FixtureLifecycleIT.xml
    └── failsafe-summary.xml
~~~

Điều **không được còn** sau khi `post-integration-test` chạy thành công:

~~~text
target/it-fixture/
target/it-fixture/state.txt
~~~

Thư mục `target` vẫn tồn tại để giữ JAR và test reports; cleanup **chỉ xóa subtree `it-fixture`**, không xóa cả `target`. Các file report và dấu mốc giúp điều tra mà không giữ môi trường test còn hoạt động.

### 9.2. Kiểm tra bằng lệnh không cần plugin khác

Sau `mvn clean verify` trên Linux/macOS:

~~~bash
test -f target/it-setup.marker && echo "setup=yes" || echo "setup=no"
test -f target/it-cleanup.marker && echo "cleanup=yes" || echo "cleanup=no"
test -e target/it-fixture/state.txt && echo "fixture=present" || echo "fixture=absent"
~~~

Kết quả mong đợi:

~~~text
setup=yes
cleanup=yes
fixture=absent
~~~

Trên Windows PowerShell:

~~~powershell
"setup=$(Test-Path 'target/it-setup.marker')"
"cleanup=$(Test-Path 'target/it-cleanup.marker')"
"fixture=$(Test-Path 'target/it-fixture/state.txt')"
~~~

Giá trị mong đợi lần lượt là `True`, `True` và `False`.

Nếu chạy `mvn verify` **không clean** sau những lần chạy cũ, marker cũ có thể còn và gây hiểu nhầm. Vì vậy phần thực hành đối chiếu **luôn dùng `mvn clean verify`**. Ở CI, nên có log phase và một build workspace mới.

### 9.3. Đọc reports để biết thực sự có test

Surefire:

~~~text
target/surefire-reports/TEST-vn.example.itlifecycle.AppTest.xml
~~~

Failsafe:

~~~text
target/failsafe-reports/TEST-vn.example.itlifecycle.FixtureLifecycleIT.xml
target/failsafe-reports/failsafe-summary.xml
~~~

Kết quả kỳ vọng:

| Báo cáo | Tests run | Failures | Errors |
| --- | ---: | ---: | ---: |
| AppTest ở Surefire | 1 | 0 | 0 |
| FixtureLifecycleIT ở Failsafe | 2 | 0 | 0 |
| Tổng | 3 | 0 | 0 |

Đừng chỉ nhìn dòng `BUILD SUCCESS`: nếu IT không được discovery hoặc goal chưa bind đúng, một build có thể thành công khi **0 integration tests** đã chạy. Trong POM mẫu, `<failIfNoTests>true</failIfNoTests>` giúp phát hiện trường hợp này.

### 9.4. Chạy ứng dụng sau verify

Vì JAR Plugin đã tạo manifest `Main-Class`:

~~~bash
java -jar target/it-resource-lifecycle-demo-1.0.0.jar
~~~

Stdout **chính xác**:

~~~text
BUILD READY
~~~

Ứng dụng không cần `target/it-fixture` để chạy vì logic production không đọc file fixture. Đó là hành vi mong muốn: tài nguyên test **không phải dependency runtime của sản phẩm**.

---

## 10. Thí nghiệm quan trọng: integration test fail nhưng cleanup vẫn chạy

Chạy lại từ một build sạch và chỉ đổi property:

~~~bash
mvn "-Dit.force.failure=true" clean verify
~~~

Cờ CLI ghi đè property `it.force.failure=false` của POM trong lần build này, nên Failsafe truyền Java system property `it.force.failure=true` tới integration test JVM.

Trong `FixtureLifecycleIT`:

~~~java
assertFalse(
        Boolean.getBoolean("it.force.failure"),
        "Intentional integration-test failure"
);
~~~

Khi property là `true`, assertion này fail. Test kiểm tra fixture vẫn có thể pass; goal `failsafe:integration-test` ghi nhận **1 failure**.

### 10.1. Kết quả mong đợi theo phase

~~~text
pre-integration-test
  └── setup tạo fixture                     PASS

integration-test
  └── fixtureIsReadyDuringIntegrationTest   PASS
  └── optionalFailureDemonstratesCleanupOrder  FAIL (có chủ đích)
      Failsafe ghi report, không chặn post chỉ vì assertion failure

post-integration-test
  └── cleanup xóa fixture                   RUN

verify
  └── failsafe:verify đọc kết quả            BUILD FAILURE
~~~

Ở lần build này, **BUILD FAILURE là đúng kỳ vọng**. Đừng cố làm build xanh bằng `-Dmaven.test.failure.ignore=true`; mục tiêu là chứng minh cleanup vẫn diễn ra **trước khi trạng thái thất bại được báo ở verify**.

### 10.2. Kiểm tra bằng chứng sau khi build thất bại

Dù Maven trả exit code khác 0:

~~~text
target/it-setup.marker           tồn tại
target/it-cleanup.marker         tồn tại
target/it-fixture/state.txt      không tồn tại
target/failsafe-reports/         có báo cáo lỗi
~~~

Dùng lại lệnh kiểm tra file của mục 9.2, đồng thời mở `TEST-vn.example.itlifecycle.FixtureLifecycleIT.xml` và `failsafe-summary.xml` để thấy failure.

Đây là lợi ích thiết kế chính của Failsafe: **kết quả assertion failure không bị mất, nhưng teardown có cơ hội chạy**.

### 10.3. Khôi phục cấu hình bình thường

Bỏ cờ CLI gây lỗi:

~~~bash
mvn clean verify
~~~

Với property mặc định `false`, cả hai IT phải pass và build kết thúc `BUILD SUCCESS`. Không sửa test để xóa assertion minh họa; giữ test ở trạng thái chạy bình thường với default property.

### 10.4. Giới hạn: post-integration-test không phải finally tuyệt đối

Không hứa rằng cleanup **luôn** chạy trong mọi lỗi. Các tình huống có thể làm Maven không tới phase cleanup:

- Goal setup ném lỗi ngay ở `pre-integration-test`.
- JVM Maven bị kill cứng, runner bị hủy hoặc máy mất điện.
- Lỗi phân giải dependency/plugin nghiêm trọng trước hoặc trong integration-test.
- Một plugin không tuân thủ cách Failsafe hoãn thất bại và làm build ngừng trước post.
- Đôi khi test fork bị treo vô hạn hoặc hỏng theo cách plugin không thể hoàn tất goal.

Vì thế, tài nguyên ngoài process như database/container/server cần **timeout, cleanup dự phòng ở tầng CI/orchestrator, ownership ID và TTL**. Failsafe xử lý đường đi bình thường của test assertion failure; nó không thay thế hệ thống thu hồi tài nguyên.

---

## 11. Vì sao không nên chạy mvn integration-test trực tiếp trong Maven 3?

Đây là một bẫy lớn:

~~~bash
mvn integration-test
~~~

Trong **Maven 3.9.x**, lệnh gọi phase `integration-test` chạy default lifecycle đến **hết phase đó** nhưng **không tự chạy phase `post-integration-test` hoặc `verify` đứng sau**.

Với POM mẫu:

- AntRun setup tạo `it-fixture`.
- Failsafe chạy `FixtureLifecycleIT`.
- **AntRun cleanup không chạy** nếu lệnh kết thúc tại integration-test.
- Failsafe verify chưa đọc kết quả để quyết định build theo đúng luồng.

Điều này có thể khiến resource còn sống và trạng thái build bị hiểu sai. Với server thật, tiến trình có thể vẫn chiếm cổng sau khi lệnh Maven kết thúc.

### 11.1. So sánh các lệnh

| Lệnh trên Maven 3.9.x | Unit tests | Package | Setup IT | IT | Cleanup IT | Failsafe verify |
| --- | --- | --- | --- | --- | --- | --- |
| `mvn test` | Có | Chưa | Không | Không | Không | Không |
| `mvn package` | Có | Có | Không | Không | Không | Không |
| `mvn pre-integration-test` | Có | Có | Có | Chưa | Chưa | Chưa |
| `mvn integration-test` | Có | Có | Có | Có | **Không** | **Không** |
| `mvn post-integration-test` | Có | Có | Có | Có | Có | Chưa |
| `mvn verify` | Có | Có | Có | Có | **Có** | **Có** |
| `mvn clean verify` | Có | Có | Có | Có | **Có** | **Có** |

Bảng giả định POM mẫu, không có skip flags và các plugin goals thực sự thành công tới phase tương ứng. `clean` thuộc clean lifecycle chạy trước default lifecycle của `verify`.

### 11.2. Maven 4 có thay đổi quy tắc một số boundary phases

Tài liệu lifecycle cập nhật của Apache Maven mô tả thay đổi với **Maven 4**, trong đó có các phase bổ sung và hành vi thực thi các `after` phases. **Bài này lấy Maven 3.9.x làm chuẩn**: không suy rộng lập luận “`mvn integration-test` bỏ qua post” thành một tuyên bố không điều kiện về mọi phiên bản Maven tương lai.

Trong dự án cụ thể, luôn ghi nhận `mvn -version` và ưu tiên lệnh `mvn verify` có mục đích rõ ràng.

---

## 12. Quan sát chính xác setup, test, teardown và verify ở Maven log

Trong POM mẫu, bốn executions/goal trọng yếu có ids hoặc tên goal:

~~~text
maven-antrun-plugin:3.1.0:run (prepare-it-fixture)
maven-failsafe-plugin:3.5.4:integration-test (run-integration-tests)
maven-antrun-plugin:3.1.0:run (cleanup-it-fixture)
maven-failsafe-plugin:3.5.4:verify (verify-integration-tests)
~~~

Dạng hiển thị dòng log thay đổi giữa plugin/Maven versions, nhưng **thứ tự theo phase** phải khớp.

Lệnh để kiểm tra effective plugin configuration:

~~~bash
mvn help:effective-pom
mvn help:effective-pom -Dverbose
~~~

Tìm:

- `maven-antrun-plugin` version 3.1.0.
- Execution `prepare-it-fixture` → phase `pre-integration-test`.
- Execution `cleanup-it-fixture` → phase `post-integration-test`.
- `maven-failsafe-plugin` version 3.5.4, hai executions tương ứng.
- `failIfNoTests=true` và `systemPropertyVariables`.

Vì ví dụ không dùng parent inheritance/profiles, effective POM tương đối dễ đọc. Trong dự án thật, nhiều cấp parent và `pluginManagement` có thể bổ sung/cập nhật executions; phải xem effective POM của **module đang chạy integration tests**.

### 12.1. Marker không chứng minh process/service đã sẵn sàng

Trong demo, `it-setup.marker` là một bằng chứng AntRun goal đã chạy. Nhưng trong hệ thống HTTP/database thật, marker “START CALLED” không đủ chứng minh service đã chấp nhận kết nối.

Giả sử process đã được spawn nhưng cần 15 giây để chạy migration. Goal setup phải **đợi health endpoint/connection readiness**, với **deadline cụ thể**, trước khi trả success. Đừng thay bằng `sleep 30` rồi coi là chắc chắn: trên CI tải nặng service có thể lâu hơn, trên laptop lại mất thời gian thừa.

---

## 13. Mở rộng từ file fixture đến service thật

Một integration test thường cần một dịch vụ có lifecycle riêng. Mô hình vẫn giữ bốn phase:

~~~text
pre-integration-test:
    reserve unique port/network
    start HTTP server / DB container
    await healthy state with deadline
    export endpoint/credentials only for tests

integration-test:
    Failsafe executes *IT tests
    tests call endpoint / DB

post-integration-test:
    collect logs and diagnostics
    gracefully stop service
    force stop owned resource after timeout if needed
    remove temp network/volume/fixtures

verify:
    Failsafe evaluates reports and quality checks
~~~

### 13.1. Plugin start/stop phải là plugin thật

Ví dụ cấu trúc **minh họa** (không phải plugin cụ thể để copy chạy):

~~~xml
<execution>
    <id>start-it-service</id>
    <phase>pre-integration-test</phase>
    <goals>
        <goal>start</goal>
    </goals>
</execution>

<execution>
    <id>stop-it-service</id>
    <phase>post-integration-test</phase>
    <goals>
        <goal>stop</goal>
    </goals>
</execution>
~~~

`start` và `stop` chỉ là **tên goal giả định**. Một plugin dùng để điều khiển Jetty, Docker, database hoặc server riêng sẽ có tọa độ, goals, parameters và yêu cầu version riêng. Không thêm hai execution trên vào AntRun plugin của POM mẫu vì AntRun không cung cấp goal `start`/`stop` như hai goal chung đó.

Cần đọc plugin docs để biết:

- Cách khởi động **không chiếm foreground** (daemon/background), nếu integration-test còn phải chạy tiếp.
- Cách lấy ID của process/container đã tạo.
- Cách chờ readiness và đặt timeout.
- Cách dừng **đúng resource của build**.
- Cách giữ/thu logs khi test fail.

### 13.2. Vì sao không dùng shell background một cách tùy tiện?

Một lệnh như `java -jar server.jar &` có thể hoạt động trong một shell Unix, nhưng sẽ không tương đương trên PowerShell/CMD và có thể để lại process con khi Maven bị kill. Nếu cần một service thật, dùng plugin/container orchestration đã hỗ trợ lifecycle hoặc script có quản lý PID/port và cleanup đáng tin.

Không dùng lệnh dọn kiểu “kill tất cả process java”, “xóa mọi container” hoặc “xóa hết /tmp” để xử lý resource IT. Những tác vụ đó có thể ảnh hưởng người dùng và job khác.

### 13.3. Resource ownership và CI isolation

Một thiết kế tốt nên đặt tên resource theo build ID, ví dụ:

~~~text
service-it-<build-id>
database-it-<build-id>
network-it-<build-id>
volume-it-<build-id>
~~~

Các giá trị có dấu `<...>` là **các trường cần thay bằng ID thực**, không phải lệnh để chạy. Trước cleanup, xác minh ID này thuộc job hiện tại. Với database, xóa chỉ schema/database **do test tạo ra**; tuyệt đối không cấu hình connection tới production rồi chạy teardown vô điều kiện.

---

## 14. Readiness, timeouts và kiểm tra sức khỏe

Một resource “đã start” chưa chắc “đã ready”.

Với HTTP service:

1. Start service và nhận process/container ID.
2. Chờ endpoint health trả mã thành công theo chính sách.
3. Giới hạn thời gian chờ, ví dụ 60 giây (chọn theo SLO của ứng dụng).
4. Nếu quá deadline, xuất log và đánh dấu **setup failure**.
5. Chỉ cho phép Maven đi tới `integration-test` sau khi setup goal xác nhận ready.

Với database:

1. Đảm bảo network và database instance đã có.
2. Chờ kết nối mở được; không chỉ kiểm tra process tồn tại.
3. Chờ migration/schema version mà test cần.
4. Tạo dữ liệu seed có ID riêng.
5. Đóng kết nối/rollback/xóa dữ liệu theo mô hình test khi cleanup.

### 14.1. Không đợi vô hạn

Một health check không có timeout làm CI bị treo. Một loop tự viết có thể làm log rất lớn. Thiết kế nên gồm **deadline, retry interval có giới hạn và error report rõ**.

Nếu setup không sẵn sàng, goal ở pre-integration-test nên fail nhanh với thông tin về lỗi resource, nhưng phải có **cleanup dự phòng ngoài Maven** vì phase post có thể không chạy sau setup failure.

### 14.2. Không lộ secrets qua log

Một integration environment có thể cần credentials. Tránh ghi password/token trong Maven command, POM được commit, Ant `echo` hoặc reports công khai. Dùng secret store/CI secret injection và giới hạn quyền; test có thể nhận environment variables được cấp, nhưng phải tránh đưa chúng vào stack trace hoặc stdout.

---

## 15. Thiết kế cleanup: an toàn, idempotent và có bằng chứng

Ví dụ runnable dùng:

~~~xml
<delete dir="${project.build.directory}/it-fixture"
        quiet="true"/>
~~~

Mục tiêu được ràng buộc trong thư mục output **của project hiện hành**. Nếu thư mục không tồn tại, Ant không nên làm workflow fail chỉ vì một resource vốn đã dọn; thuộc tính `quiet` hỗ trợ xử lý việc này. Sau đó:

~~~xml
<echo file="${project.build.directory}/it-cleanup.marker"
      message="CLEANUP_DONE"/>
~~~

Dấu mốc chỉ được tạo **sau lệnh delete** trong target của ví dụ, nên cho thấy thứ tự các task đã chạy. Tuy nhiên, một file marker không chứng minh Docker container/database thật đã dừng nếu lệnh stop ở plugin khác trả success sai.

### 15.1. Những điều không nên làm

- **Không** xóa toàn bộ `${project.build.directory}` ở post-integration-test vì nó chứa JAR và reports dùng trong verify.
- **Không** dùng đường dẫn tương đối dựa vào current working directory nếu project là reactor và plugin có thể chạy ở những module khác nhau.
- **Không** dừng service bằng tên chung có thể trùng với process/job khác.
- **Không** xóa logs trước khi đã thu thập evidence cần điều tra test fail.
- **Không** cho cleanup chạy với credentials production hoặc quyền admin không cần thiết.
- **Không** coi `quiet=true` là lý do nuốt mọi lỗi khi cần xác minh resource đã được thu hồi. Với service thật, phải kiểm tra stop status/health/ownership rõ hơn.

### 15.2. Dọn riêng, log riêng

Trong hệ thống thật, thường thu logs vào artifact CI **trước** khi xóa container/volume. Với ví dụ file, `target/failsafe-reports` và `target/surefire-reports` được giữ lại; chỉ `target/it-fixture` bị xóa.

Một workflow thực tế có thể lưu diagnostics khi test fail, nhưng vẫn thu hồi resource trong mọi đường đi có thể. Giữ một container sống sau failure để debug chỉ nên làm theo policy có thời hạn/ownership rõ ràng, không để chiếm tài nguyên vô hạn.

---

## 16. Failure modes: cleanup có chạy trong mọi trường hợp không?

| Tình huống | Dự đoán cleanup ở Maven 3 | Cần làm gì? |
| --- | --- | --- |
| Tất cả IT PASS, `mvn verify` | **Có**, nếu post goal cấu hình đúng | Kiểm tra log, marker, reports |
| Một JUnit assertion FAIL khi dùng Failsafe | **Thông thường có**, do Failsafe hoãn kết luận đến verify | Xác nhận post goal chạy, verify trả failure |
| Test code tự ghi report failure | **Thông thường có** nếu Failsafe goal hoàn thành bình thường | Đọc failsafe-summary |
| Setup plugin FAIL ở pre | **Không đảm bảo** post chạy | CI cleanup dự phòng, cleanup partial resources |
| Maven bị kill cứng | **Không đảm bảo** | Job finalizer, TTL, external resource janitor |
| Server không ready và pre timeout | **Không đảm bảo** | Timeout + external cleanup |
| Goal plugin khác FAIL tại integration-test | **Không đảm bảo** | Thiết kế goal và cleanup dự phòng |
| Chỉ gọi `mvn integration-test` (Maven 3) | **Không**, phase post đứng sau | Dùng `mvn verify` |
| Chạy `mvn package` | Không đến pre/post | Bình thường vì IT chưa yêu cầu |
| Chạy `mvn -DskipITs verify` | Failsafe có thể skip, **nhưng pre/post goals khác vẫn có thể chạy** | Đưa cả lifecycle IT vào profile/điều kiện nếu muốn skip toàn môi trường |
| Chạy `mvn test` | Không đến pre/post | Chỉ unit test ở phase test |

### 16.1. Failsafe hoãn assertion failure, không “bỏ qua lỗi”

Nếu Failsafe thấy integration test fail, goal `integration-test` ghi report rồi cho phép lifecycle đi qua post theo thiết kế. Goal `verify` đọc kết quả và **đánh dấu Maven build failure**. Vì thế test fail **không được coi là pass**, dù tại thời điểm kết thúc phase integration-test Maven chưa dừng.

`failsafe:verify` phải được bind và được chạy. Bỏ goal verify có thể khiến build trông thành công dù reports đã có failures.

### 16.2. Đừng nhầm với -DskipITs

Trong Failsafe, `-DskipITs` có thể bỏ chạy IT và verification tùy version/config. Nhưng Maven lifecycle vẫn đi qua `pre-integration-test` và `post-integration-test` nếu một plugin khác đã bind goals ở hai phase này.

Một project chạy server thật có thể tốn chi phí khởi động server **dù bạn đã skip IT**. Nếu muốn bỏ cả **provisioning + IT + teardown** theo một lựa chọn, hãy đặt **các executions liên quan trong cùng một Maven profile** được bật/tắt cùng nhau, hoặc dùng cơ chế skip của chính plugin provisioning. Đừng giả định skip flag của Failsafe tự kiểm soát AntRun, Docker plugin hoặc Jetty plugin.

---

## 17. Profile để kích hoạt cả vòng đời integration test

Với sản phẩm lớn, một chiến lược hợp lý là đặt các plugin executions liên quan IT trong một **profile** chung, ví dụ `with-it`:

~~~xml
<profiles>
    <profile>
        <id>with-it</id>
        <build>
            <plugins>
                <!-- Plugin provisioning: pre-integration-test -->
                <!-- Failsafe: integration-test và verify -->
                <!-- Plugin cleanup: post-integration-test -->
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Đây là **sơ đồ vị trí trong POM**, không phải cấu hình runnable. Muốn dùng profile thật, phải chuyển nguyên các plugin/execution từ `build/plugins` vào `profile/build/plugins` đúng cấu trúc XML.

Sau đó CI hoặc developer chọn:

~~~bash
mvn -Pwith-it clean verify
~~~

Nếu không bật profile, những goal IT chỉ có trong profile sẽ không được kích hoạt. Đây là cách điều phối cả resource lifecycle thống nhất hơn việc chỉ truyền `-DskipITs` rồi để plugin server tự chạy.

**Cảnh báo:** Maven profiles có thể được kích hoạt qua settings, JDK, file hoặc property, nên muốn biết chúng có hiệu lực thật hãy kiểm tra `mvn help:active-profiles` và `mvn help:effective-pom`, không chỉ nhìn POM.

---

## 18. Multi-module: module nào nên sở hữu tài nguyên IT?

Trong reactor:

~~~text
platform/
├── pom.xml
├── core/
│   └── pom.xml
├── adapter/
│   └── pom.xml
└── integration-tests/
    └── pom.xml
~~~

Có hai kiểu thiết kế phổ biến:

1. **Mỗi module tự sở hữu fixture** dưới `${project.build.directory}` của nó và có pre/post bindings riêng.
2. **Một module chuyên integration-tests** sở hữu môi trường dùng cho một nhóm module, tránh nhiều module đồng thời khởi động/giải phóng cùng database hoặc service.

Không đặt một execution provision database **mặc định inherited cho mọi module** nếu thực tế chỉ một module cần database. Các module có thể chạy build song song và tranh cổng, schema hoặc volume.

### 18.1. Aggregation khác inheritance

`<modules>` chỉ đưa module vào reactor; việc truyền plugin configuration qua parent cần quan hệ `<parent>`. Một plugin được khai `build/plugins` ở parent có thể được kế thừa sang child theo model Maven; một execution tạo service hoặc xóa file ở parent vì thế có thể chạy nhiều lần nếu không giới hạn.

Nếu một execution chỉ phục vụ parent, có thể xem xét `<inherited>false</inherited>` ở đúng plugin/execution. Nếu chỉ phục vụ module IT, đặt nó trong POM module đó. Đừng sửa bằng cách hardcode mọi module vào cùng một `target/it-fixture`; điều này làm tăng rủi ro dữ liệu/cleanup chồng chéo.

### 18.2. -pl và -am có thể thay phạm vi resource lifecycle

Ví dụ (chỉ khi reactor thật có artifactId `integration-tests`):

~~~bash
mvn -pl :integration-tests verify
~~~

Chỉ chọn module integration-tests. Nếu module này phụ thuộc artifact nội bộ chưa install, build có thể không resolve dependency.

~~~bash
mvn -pl :integration-tests -am verify
~~~

`-am` build thêm các dependency modules trong reactor. Nếu các module đó cũng bind pre/post/IT goals, chúng có thể chạy resource lifecycle riêng và gây tranh chấp.

Hãy kiểm tra effective POM, phase bindings và resource names của **từng module được chọn** trước khi bật parallel build.

### 18.3. Đừng dùng một port cố định cho nhiều build song song

Hai job cùng đòi `localhost:8080` có thể gây `Address already in use`. Giải pháp: cấp port động, network isolation, CI workspace riêng, hoặc một service sandbox riêng theo build ID. Tham số endpoint đã xác định phải được truyền tới integration tests theo cách nhất quán.

---

## 19. Dùng Testcontainers hoặc JUnit extension có phù hợp không?

Có. Nếu một integration test trực tiếp sở hữu resource, chẳng hạn tạo PostgreSQL container trong JUnit `@BeforeAll` và dừng trong `@AfterAll` hoặc Testcontainers extension, bạn **có thể không cần** plugin provisioning ở pre/post.

Hai mô hình:

| Vòng đời do ai sở hữu? | Khi nào dùng? | Lưu ý |
| --- | --- | --- |
| Maven pre/post | Resource cấp build, cần sẵn trước khi Failsafe chạy, ví dụ deploy WAR/service chung | Cần binding setup/teardown, readiness, CI cleanup dự phòng |
| JUnit extension/Testcontainers | Resource gắn với test class/suite, cần fixture isolated theo tests | Đảm bảo JUnit/Testcontainers dọn resource và không xung đột Maven cleanup |
| CI orchestration | Resource cấp pipeline hoặc cấp nhiều project | Maven test chỉ nhận endpoint, CI chịu trách nhiệm setup/teardown ngoài Maven |

Không nên đồng thời để Maven `post-integration-test` xóa container mà JUnit extension vẫn coi là resource do nó quản lý, hoặc ngược lại. Chọn **một owner chính**, các lớp khác chỉ làm cleanup dự phòng có kiểm soát.

### 19.1. Testcontainers không tự giải quyết tất cả vấn đề

Một container test có thể cần Docker runtime phù hợp, quyền mạng, image có sẵn và timeout. Nó cũng cần cơ chế cleanup khi CI bị kill. Việc chọn Testcontainers là một quyết định kiến trúc, không phải điều kiện bắt buộc để hiểu Maven phases.

---

## 20. Kiểm tra test discovery và report khi resource vẫn không được dùng

Nếu bạn chạy `mvn clean verify` và thấy:

~~~text
target/it-setup.marker
target/it-cleanup.marker
~~~

nhưng Failsafe report không có `FixtureLifecycleIT`, có thể gặp:

- Failsafe plugin chưa được bind đúng phase.
- Lớp test bị đặt sai thư mục `src/test/java`.
- Tên không khớp `*IT.java`/`IT*.java`/`*ITCase.java`.
- JUnit dependency/engine hoặc test classpath sai.
- Profile chứa plugin chưa được bật.
- `-DskipITs` hoặc một skip flag khác đang có hiệu lực.
- Runtime IT bị loại bằng includes/excludes.
- Test không biên dịch được nên Maven dừng tại `test-compile`.

### 20.1. Đọc đúng reports

Surefire:

~~~text
target/surefire-reports/
~~~

Failsafe:

~~~text
target/failsafe-reports/
target/failsafe-reports/failsafe-summary.xml
~~~

Một report XML Failsafe từ bài thực hành có thể chứa:

~~~xml
<testsuite name="vn.example.itlifecycle.FixtureLifecycleIT"
           tests="2"
           failures="0"
           errors="0"
           skipped="0">
    <!-- testcase và properties khác do plugin sinh -->
</testsuite>
~~~

Đây là **snippet minh họa**, không phải toàn bộ XML cố định mà plugin bắt buộc xuất đúng như vậy. Một lần test fail có thể cho `tests=2, failures=1`. Quan trọng là đọc kết quả của lần build hiện tại.

### 20.2. failIfNoTests=true để kiểm soát test zero

POM mẫu khai:

~~~xml
<failIfNoTests>true</failIfNoTests>
~~~

trong Failsafe configuration. Nếu không có IT được phát hiện, plugin được yêu cầu xử lý theo chính sách fail, tránh báo xanh giả.

Với hệ thống nhiều module mà chỉ một module chứa IT, không nên copy `failIfNoTests=true` sang tất cả module rồi khiến module library vô cớ fail. Thay vào đó, bind Failsafe ở module IT hoặc profile thích hợp.

---

## 21. Chẩn đoán tình huống phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `mvn test` không tạo fixture | Chưa đến phase pre-integration-test | Chạy `mvn clean verify` |
| `mvn package` tạo JAR nhưng không chạy IT | Package đứng trước pre/IT | Chạy `verify` |
| Fixture vẫn còn sau `mvn integration-test` | Maven 3 dừng ở phase IT, chưa đến post | Không dùng lệnh phase này để chạy vòng đời đầy đủ; chọn `verify` |
| Test fail và cleanup không chạy | Dùng plugin fail-fast hoặc lỗi plugin/JVM trước post | Đọc log; dùng Failsafe và external cleanup |
| IT fail dù resource “đã start” | Resource chưa ready | Thêm health/readiness check có deadline |
| JUnit IT chạy sớm ở phase test | Tên test khớp Surefire patterns hoặc includes sai | Đổi tên `*IT`, tách Surefire/Failsafe |
| IT không chạy | Không bind Failsafe hoặc includes sai | Effective POM, failsafe reports, failIfNoTests |
| Failsafe integration-test ghi failure nhưng Maven chưa dừng | Kết quả được defer để post chạy | Đảm bảo `failsafe:verify` bind ở verify |
| Test failed nhưng `BUILD SUCCESS` | Bỏ goal verify, skip flags hoặc ignore failures | Kiểm tra CLI, effective POM và summary |
| Sau cleanup mất luôn JAR/reports | Goal delete nhầm cả `target` | Giới hạn xóa đúng `target/it-fixture` |
| Marker cleanup vẫn tồn tại sau lần failed build cũ | File stale vì không clean | Dùng `mvn clean verify` và đọc log |
| Service/DB test bị tranh chấp | Hai job dùng cùng port/name/schema | Isolation theo job ID, dynamic ports |
| `-DskipITs` nhưng service vẫn start | Skip flag chỉ áp dụng Failsafe | Đặt setup/teardown trong profile hoặc skip tương ứng |
| Windows chạy shell script Unix thất bại | Script hoặc background process không portable | Dùng plugin hỗ trợ OS hoặc script riêng đúng shell |
| Test dùng sai endpoint | Hardcode host/port hoặc system property không được truyền | Kiểm tra Failsafe systemPropertyVariables |
| IT bị lỗi mất class | Test dependency/classpath không đủ | Xem Failsafe report, dependency tree |
| Setup fail làm resource còn lại | Maven không tự chạy post sau pre failure | External CI cleanup và TTL |
| Parallel modules cùng stop một service | Không rõ resource owner | Chọn một owner module hoặc isolation theo module |

### 21.1. Sáu bước điều tra

1. Ghi nguyên văn Maven command, Maven version và module chạy lệnh.
2. Xác định phase lỗi ở `pre-integration-test`, `integration-test`, `post-integration-test` hay `verify`.
3. Đọc effective POM: plugin nào bind goal nào, execution ids và profiles.
4. Kiểm tra setup logs/health, sau đó IT reports và test count.
5. Kiểm tra post cleanup logs và resource còn lại; không chỉ nhìn marker có thể stale.
6. Sửa đúng nguyên nhân rồi chạy lại `mvn clean verify` trong workspace an toàn; với resource thật, xác nhận không có container/volume/process của build còn sót.

Không xóa toàn bộ Docker resources hoặc Maven repository một cách mù quáng để “làm sạch”; cleanup phải đúng resource do test tạo ra.

---

## 22. Chiến lược setup/teardown trong CI

Một pipeline integration test thường có ít nhất hai lớp cleanup:

**Lớp 1 — Maven lifecycle:**

~~~text
pre-integration-test -> integration-test -> post-integration-test -> verify
~~~

**Lớp 2 — CI finalizer:**

~~~text
job finishes / fails / is cancelled
    |
    v
cleanup only resources tagged with this job/build ID
    |
    v
collect logs + report cleanup outcome
~~~

CI finalizer không cần can thiệp vào đường đi bình thường khi Maven đã cleanup đủ, nhưng có thể thu hồi resource khi Maven bị hủy trước post. Nên thiết kế cleanup **idempotent**: gọi lại không gây mất dữ liệu ngoài scope.

### 22.1. Những gì nên lưu vào CI artifact

- Maven/JDK versions, source revision và profile/flags được dùng.
- Surefire/Failsafe reports, nhất là `failsafe-summary.xml`.
- Log của plugin start/stop resource, readiness và timeout.
- Resource ID/namespace ở dạng an toàn, không lộ credentials.
- Kiểm tra cuối rằng resource của build đã dừng/xóa.
- Hash của artifact được test và deploy.

Một build `BUILD FAILURE` nhưng cleanup đã thành công là **một kết quả có giá trị**: thất bại kiểm thử được giữ nguyên, môi trường vẫn được thu hồi.

### 22.2. Không giao quyền phá hủy quá mức cho test runner

Một tài khoản test chỉ nên provision và delete resource trong namespace dành riêng cho test. Nếu tài khoản có quyền xóa production database, một lỗi POM/script có thể gây mất dữ liệu nghiêm trọng. Dùng credentials scoped và endpoint test, verify guardrails trước khi cleanup.

---

## 23. Bài tập thực hành

### Bài A — Giải thích thứ tự phase

Không nhìn lại bảng, vẽ thứ tự `package → pre-integration-test → integration-test → post-integration-test → verify`. Nêu một loại công việc cho mỗi phase. Giải thích vì sao một phase không được bind goal thì tự nó không tạo tài nguyên.

### Bài B — Chạy thành công

Dựng `it-resource-lifecycle-demo` từ mục 6–8. Chạy:

~~~bash
mvn clean verify
~~~

Xác nhận **1 unit test và 2 integration tests PASS**. Kiểm tra cả `it-setup.marker`, `it-cleanup.marker` và việc không còn `it-fixture/state.txt`.

### Bài C — Đọc state trong lúc integration-test

Trong `FixtureLifecycleIT`, giải thích vì sao `fixtureIsReadyDuringIntegrationTest` phải tìm được `state.txt`, dù sau verify file đó bị xóa. Nếu nó mất trước khi test chạy, phase binding nào có thể bị đặt sai?

### Bài D — Cố ý làm test fail

Chạy:

~~~bash
mvn "-Dit.force.failure=true" clean verify
~~~

Kỳ vọng `failsafe:verify` làm build FAIL. Kiểm tra cleanup marker vẫn tồn tại và thư mục it-fixture đã bị xóa. Vì sao trạng thái build thất bại **không mâu thuẫn** với cleanup thành công?

### Bài E — Đặt cleanup sai phase

Trong bản sao project, thử đổi `cleanup-it-fixture` từ `post-integration-test` sang `pre-integration-test`. Dự đoán fixture có thể bị xóa ngay trước khi integration-test chạy, khiến `fixtureIsReadyDuringIntegrationTest` fail. Khôi phục phase đúng sau khi quan sát.

### Bài F — Bỏ verify

Trong bản sao POM, tạm bỏ execution `verify-integration-tests` rồi chạy failure scenario. Vì sao báo cáo IT lỗi có thể tồn tại mà Maven không kết luận như mong muốn? Khôi phục execution và xác nhận Failsafe verify đánh dấu lỗi.

### Bài G — Chạy integration-test trực tiếp

Phân tích lệnh `mvn integration-test` trong **Maven 3.9.x**: phase nào đã chạy, phase nào chưa? Vì sao không an toàn khi resource là server vẫn chiếm cổng? Không cố tình chạy kịch bản này trên server thật mà không có kế hoạch teardown dự phòng.

### Bài H — Bỏ qua integration tests

Chạy:

~~~bash
mvn -DskipITs clean verify
~~~

Quan sát liệu AntRun setup/cleanup có còn chạy dù Failsafe skip. Thiết kế một profile để bật/tắt **cả ba nhóm hành động**: setup, integration tests và cleanup.

### Bài I — Từ fixture sang database

Đề xuất một thiết kế database IT có namespace theo build ID, schema migration, readiness timeout, connection property, test queries và cleanup idempotent. Phân biệt **đã tạo container** với **database đã sẵn sàng phục vụ query**.

### Bài J — Multi-module

Reactor có `core`, `api` và `integration-tests`. Chọn module nào sở hữu database test? Vì sao plugin start database không nên inherited tự động bởi mọi module? Phân tích `-pl :integration-tests -am verify` khi các modules khác cũng bind resource lifecycle.

### Bài K — Lỗi không chạy post

Một CI runner bị kill giữa `integration-test`. Vì sao Failsafe không thể bảo đảm post cleanup? Đề xuất cơ chế CI finalizer + resource TTL và cách chứng minh chỉ xóa tài nguyên do build sở hữu.

### Bài L — Review một PR

Một PR đổi từ `mvn clean verify` sang `mvn integration-test` để “nhanh hơn”. Hãy review tác động trong Maven 3: resource cleanup, Failsafe verify và nguy cơ báo xanh giả. Đề xuất lệnh phù hợp và cách tối ưu hợp lệ, ví dụ lựa chọn module hoặc profile, không bỏ lifecycle hậu kiểm.

---

## 24. Checklist trước khi dùng trên dự án thực

- [ ] Phân loại đúng unit test và integration test; IT có tên phù hợp Failsafe.
- [ ] Đã ghim version Surefire, Failsafe và plugin provisioning/cleanup.
- [ ] Goal setup được bind đúng `pre-integration-test`.
- [ ] Goal chạy test được bind đúng `integration-test` bằng Failsafe.
- [ ] Goal cleanup được bind đúng `post-integration-test`.
- [ ] Goal `failsafe:verify` được bind đúng `verify`.
- [ ] Maven command thực sự chạy tới `verify` trên Maven 3.
- [ ] Không coi `mvn integration-test` đơn lẻ là hoàn tất resource lifecycle.
- [ ] Setup kiểm tra resource readiness có timeout rõ, không chỉ spawn process.
- [ ] Resource có tên/path/port/namespace riêng và một owner rõ ràng.
- [ ] Cleanup chỉ dừng/xóa tài nguyên do build tạo, không xóa cả target/reports.
- [ ] Cleanup có thể gọi lại an toàn, có timeout và evidence.
- [ ] Có cleanup dự phòng khi pre fail, runner bị kill hoặc job cancelled.
- [ ] Biết `-DskipITs` không tự động tắt goals của plugin khác.
- [ ] Kiểm tra số test thực sự chạy từ Failsafe Reports và `failsafe-summary.xml`.
- [ ] Đã thử một assertion failure thông thường và xác nhận post cleanup vẫn chạy.
- [ ] Đã thử runtime/container/CI môi trường thật trước khi đưa vào pipeline sản phẩm.
- [ ] Secrets và quyền xóa tài nguyên test đã được giới hạn phù hợp.

**Kết luận:** Trong Maven 3, `pre-integration-test` là nơi **chuẩn bị tài nguyên**, `integration-test` là nơi **Failsafe chạy kiểm thử**, `post-integration-test` là nơi **thu hồi tài nguyên**, còn `verify` là nơi **xác nhận kết quả kiểm thử sau cleanup**. Để cả bốn bước được thực hiện theo đúng thứ tự, dùng `mvn verify`. Đây là một quy trình an toàn hơn cho assertion failures thông thường, nhưng vẫn cần cleanup dự phòng ở CI cho lỗi hạ tầng hoặc Maven bị hủy đột ngột.

## 25. Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): thứ tự default lifecycle, nhiệm vụ `pre-integration-test`, `integration-test`, `post-integration-test`, `verify` và cảnh báo về lời gọi phase trực tiếp trong Maven 3.
- [Apache Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/): vì sao Failsafe hoãn integration-test assertion failure để cleanup chạy và giới thiệu hai goals `integration-test`/`verify`.
- [Maven Failsafe Plugin 3.5.4 — Usage](https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-failsafe-plugin/usage.html): cấu hình executions và cách chạy `mvn verify`.
- [Maven Failsafe Plugin 3.5.4 — Plugin Details](https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-failsafe-plugin/plugin-info.html): yêu cầu Maven/JDK, goals và tham số plugin.
- [Maven Failsafe Plugin — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html): tên lớp IT mặc định và cấu hình discovery.
- [Maven Failsafe Plugin — Using JUnit Platform](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/junit-platform.html): tích hợp JUnit Jupiter engine.
- [Apache Maven AntRun Plugin 3.1.0 — Usage](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/usage.html): Ant `target`, `mkdir`, `echo` và `delete` trong Maven build.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): kiểm tra plugin executions và configurations sau parent/profile merge.
