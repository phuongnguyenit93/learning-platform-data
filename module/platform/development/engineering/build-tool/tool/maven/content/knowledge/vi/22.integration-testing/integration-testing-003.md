# Goal integration-test, goal verify và cách báo lỗi kiểm thử trong Maven

Một dự án Java thường có **unit tests** chạy nhanh để kiểm tra từng hàm hoặc thành phần nhỏ, và **integration tests** kiểm tra nhiều thành phần phối hợp với nhau: ứng dụng đọc/ghi dữ liệu, kết nối dịch vụ, sử dụng file cấu hình hoặc thực hiện một kịch bản qua HTTP. Maven hỗ trợ sắp xếp các bước đó bằng **default build lifecycle**. Đối với integration tests, **Maven Failsafe Plugin** cung cấp hai goal then chốt:

1. **`failsafe:integration-test`**: tìm và chạy integration tests; ghi kết quả vào báo cáo và **summary file**. Khi test assertion thất bại, goal này được thiết kế để chưa lập tức báo build failure theo cách ngăn Maven chạy các phase dọn dẹp tiếp theo.
2. **`failsafe:verify`**: đọc summary của Failsafe, **xác minh kết quả** và báo build failure ở giai đoạn `verify` nếu integration tests không đạt chính sách đã cấu hình.

**Phân biệt goal và phase:** `integration-test` và `verify` vừa là tên **phases** của default lifecycle vừa xuất hiện trong tên **goals** của plugin. Chúng không phải một khái niệm:

- `mvn integration-test`: yêu cầu Maven chạy lifecycle **đến phase `integration-test`**, không bao gồm `post-integration-test` hay `verify`.
- `mvn verify`: yêu cầu chạy lifecycle **đến phase `verify`**, có thể gồm setup, chạy integration tests, cleanup và kiểm tra kết quả.
- `mvn failsafe:integration-test` hoặc `mvn failsafe:verify`: gọi một **goal trực tiếp**, không tự chạy toàn bộ những phase trước đó.

Vì vậy, với một build có integration-test environment, **thông thường hãy gọi `mvn verify`, không dừng ở `mvn integration-test`**.

Sơ đồ luồng phù hợp với dự án Java JAR có unit và integration tests:

```text
mvn clean verify
  |
  +-- clean lifecycle: clean:clean
  |
  +-- default lifecycle (packaging jar)
       |
       +-- compile                   compiler:compile
       +-- test-compile              compiler:testCompile
       +-- test                      surefire:test
       |
       +-- package                   jar:jar
       |
       +-- pre-integration-test      chuẩn bị dữ liệu / dịch vụ (nếu bind)
       |
       +-- integration-test          failsafe:integration-test (nếu bind)
       |                                 |
       |                                 +-- chạy IT cases
       |                                 +-- ghi failsafe-reports
       |                                 +-- ghi failsafe-summary.xml
       |                                 +-- deferred test failure
       |
       +-- post-integration-test     dọn môi trường (nếu bind)
       |
       +-- verify                    failsafe:verify (nếu bind)
                                         |
                                         +-- đọc summary
                                         +-- báo BUILD FAILURE nếu IT không đạt
```

Đây là **sơ đồ mô hình**, không phải danh sách đầy đủ mọi lifecycle phase và không phải lời bảo đảm rằng cleanup luôn chạy bất chấp lỗi hạ tầng. Nếu compile không được, plugin resolution gặp lỗi, quá trình Maven bị dừng hoặc bước setup gặp exception, build vẫn có thể dừng **trước `post-integration-test`**. Tính chất “deferred failure” của Failsafe chủ yếu xử lý **test results**, không phải cơ chế try/finally bao trùm mọi lỗi.

Bài dùng **Maven 3.6.3+**, **JDK 17+**, **Maven Failsafe Plugin 3.6.1**, **Surefire 3.6.1**, **JUnit Jupiter 5.11.4** và **Maven Antrun Plugin 3.1.0** trong ví dụ. Các phiên bản được chọn để minh họa một bộ build xác định, không phải tuyên bố là bản mới nhất trong mọi thời điểm.

## 1. Phase, goal và plugin: ba tầng khác nhau

| Thuật ngữ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Lifecycle phase | `integration-test` | Mốc để chạy các goals được bind ở giai đoạn integration tests. |
| Lifecycle phase | `verify` | Mốc kết thúc việc kiểm tra chất lượng của artifact trước các phase sau. |
| Plugin | `org.apache.maven.plugins:maven-failsafe-plugin` | Artifact cung cấp cơ chế thực thi và kiểm tra integration tests. |
| Plugin goal | `failsafe:integration-test` | Thực thi các integration tests và lưu kết quả. |
| Plugin goal | `failsafe:verify` | Đọc/đánh giá kết quả integration tests. |
| Unit-test plugin | `maven-surefire-plugin` | Thường chạy unit tests ở phase `test`. |
| Test framework | JUnit Jupiter | `@Test`, assertions và TestEngine thực hiện test methods. |
| Setup/cleanup goal | `antrun:run` trong lab | Tạo/xóa fixture để mô phỏng môi trường tích hợp. |

Cả hai Failsafe goals có **default phases** thích hợp, nhưng **Failsafe không được Maven tự thêm vào mọi project jar**. Muốn chúng chạy khi gọi `mvn verify`, dự án phải có **plugin execution** hoặc cơ chế binding tương đương.

Không nhầm **Maven Failsafe Plugin** với cơ chế JUnit: Failsafe là build integration; JUnit cung cấp assertions và cách khám phá test methods. Một test class có `@Test` nhưng không khớp quy tắc Failsafe discovery hoặc không có engine thích hợp vẫn có thể không chạy.

### 1.1. Tại sao Failsafe không mặc định chạy trong mọi dự án?

Maven không biết project nào có external database, Docker container, HTTP server hoặc fixtures cần khởi động, và không muốn chạy những integration tests tốn thời gian trong mọi build đơn giản. **Unit tests** phù hợp ở phase `test`; integration tests thường cần setup, artifact đã package và cleanup riêng. Vì thế tác giả POM phải khai báo Failsafe cùng các môi trường mà ứng dụng cần.

### 1.2. Khác nhau giữa goal và phase cùng tên

```bash
mvn verify
```

là chạy **phase**. Còn:

```bash
mvn org.apache.maven.plugins:maven-failsafe-plugin:3.6.1:verify
```

là chạy **một goal trực tiếp**. Goal `verify` không tự đi ngược lại toàn lifecycle để compile tests, start service và chạy `integration-test`.

Nếu summary file chưa tồn tại, đã cũ hoặc không đúng nơi, goal verify trực tiếp có thể không thể đánh giá đúng lượt test bạn nghĩ tới. **Ưu tiên `mvn clean verify` từ một dự án đã cấu hình đầy đủ**, thay vì ghép hai goal rời rạc trong shell mà quên cleanup.

## 2. Các phase phục vụ integration tests

Default lifecycle của Maven có các phase đáng chú ý:

| Phase | Vai trò |
| --- | --- |
| `validate` | Kiểm tra cấu hình project theo goals được bind. |
| `compile` | Biên dịch mã chính. |
| `test-compile` | Biên dịch mã test. |
| `test` | Chạy unit tests (thông thường do Surefire). |
| `package` | Tạo JAR/WAR hoặc artifact thích hợp. |
| `pre-integration-test` | Chuẩn bị môi trường cần cho IT (nếu đã bind goal). |
| **`integration-test`** | Chạy integration tests (Failsafe khi được bind). |
| **`post-integration-test`** | Dọn dịch vụ, file/fixture, container… (nếu đã bind). |
| **`verify`** | Đánh giá kết quả của những kiểm tra tích hợp và quality gates. |
| `install` | Đưa artifact vào local Maven repository nếu các phase trước đạt. |
| `deploy` | Phát hành artifact lên remote repository được phép, sau các phase trước. |

Đối với packaging `jar`, Surefire goal thường có binding mặc định ở `test`; **Failsafe integration-test/verify cần khai báo executions** trong POM hoặc parent phù hợp. Các phase `pre-integration-test` và `post-integration-test` không tự động khởi động/dừng database: plugin khác hoặc script được **bind** để làm việc đó.

### 2.1. Một lỗi khiến cả chiến lược teardown bị vô hiệu

Giả sử bạn bind goal `surefire:test` hoặc một plugin dừng build ngay khi assertion sai tại **phase `integration-test`**. Maven có thể dừng trước `post-integration-test`, khiến server/container còn mở.

Failsafe xử lý cách khác:
- Ở `integration-test`: chạy tests, ghi kết quả để kiểm tra về sau.
- `post-integration-test`: Maven có cơ hội chạy bước dọn môi trường.
- Ở `verify`: goal Failsafe đọc summary và mới báo lỗi kết quả.

**Không coi đây là bảo đảm cleanup tuyệt đối.** Một test fork JVM bị crash, thiếu artifact, lỗi Plugin Class Realm, JVM bị kill, CI timeout hoặc plugin setup/teardown ném exception vẫn có thể làm dừng lifecycle không đúng như kỳ vọng. Trong CI, nên có **cleanup dự phòng ở cấp pipeline** cho các tài nguyên đắt tiền hoặc dùng chung.

## 3. Hai goal Failsafe phối hợp qua summary file

### 3.1. `failsafe:integration-test`

Tài liệu Apache Maven mô tả goal này:
- Cần Maven project và test-scope dependencies được resolve.
- Có default phase là `integration-test`.
- Chạy integration tests theo những include/exclude/test selectors phù hợp.
- Ghi các reports ở `target/failsafe-reports` (theo mặc định).
- Ghi **`failsafe-summary.xml`** để goal verify đọc về sau.

Đường dẫn mặc định:

```text
target/failsafe-reports/failsafe-summary.xml
```

Summary là một **artifact báo cáo nội bộ** của Failsafe, không phải POM, không phải JUnit source file, không phải file người dùng tự tạo để “ghi đè kết quả”.

### 3.2. `failsafe:verify`

Goal này:
- Có default phase là `verify`.
- Đọc summary file từ lượt Failsafe integration-test được cấu hình.
- Kiểm tra test failures/errors và một số chính sách như `failIfNoTests`.
- Nếu kết quả không đạt và không được cấu hình ignore, báo build failure tại phase verify.

Hai goals cần dùng **cùng đường dẫn summary** khi có cấu hình tùy chỉnh. Nếu chỉ thay `summaryFile` cho một goal/execution, verify có thể đọc sai hoặc không đọc được dữ liệu của lượt integration tests.

### 3.3. Phân biệt test reports và summary file

Một lượt chạy có thể tạo:

```text
target/
  surefire-reports/
    TEST-dev.training.integration.GreetingServiceTest.xml
    dev.training.integration.GreetingServiceTest.txt
  failsafe-reports/
    TEST-dev.training.integration.GreetingServiceIT.xml
    dev.training.integration.GreetingServiceIT.txt
    failsafe-summary.xml
```

**Surefire reports** và **Failsafe reports** thuộc hai plugins khác nhau. XML `TEST-*.xml` thường phục vụ CI đọc kết quả từng test suite/case; `failsafe-summary.xml` đặc biệt quan trọng vì **goal verify dùng nó để quyết định outcome**.

Không viết script giả định summary và XML JUnit reports có cấu trúc giống nhau, hoặc dùng một file `TEST-*.xml` để thay summary. Chi tiết trường XML có thể thay đổi theo phiên bản plugin; muốn làm parser production phải tham khảo schema/tài liệu của đúng phiên bản thay vì đoán nội dung.

### 3.4. Tại sao cần hai goals thay vì một goal duy nhất?

Giả sử integration test tạo một DB container ở phase pre-, test có assertion thất bại, và phase post- cần dừng container. Nếu báo Maven failure ngay trong `integration-test`, quá trình dọn có thể không chạy. Thiết kế **run now, verify later** tách **thực hiện test** khỏi **ra quyết định thất bại cuối cùng**.

Bài học quan trọng: test log có `Failures: 1` ở phase integration-test nhưng chưa thấy `BUILD FAILURE` tại thời điểm đó **không có nghĩa lỗi được bỏ qua**. Cần xem `failsafe:verify` và exit code của toàn lệnh `mvn verify`.

## 4. Cấu hình Failsafe trong POM

Một đoạn plugin chuẩn cho `jar` project có integration tests:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.6.1</version>
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

Đây là đoạn XML **bên trong `<build><plugins>`**, không phải POM độc lập. Plugin goals có default phase phù hợp, nên không cần khai báo `<phase>` trong ví dụ này. Khi Maven đi đến phase tương ứng, nó chạy goal đã bind.

**Chú ý:** nếu bạn chỉ khai báo artifact Failsafe với version mà không khai báo `<executions>` (hoặc cơ chế binding khác), project `jar` sẽ **không tự** chạy các Failsafe goals khi `mvn verify`. Điều đó khác với Surefire, vốn đã có binding mặc định ở `test` của packaging `jar`.

### 4.1. Có thể dùng hai executions tách biệt không?

Có. Với cấu hình phức tạp, bạn có thể gắn:
- `integration-test` vào phase `integration-test`.
- `verify` vào phase `verify`.

Khi sử dụng executions riêng, giữ version, summary location và properties nhất quán; không bind `verify` nhầm sang phase `integration-test`. Đoạn trên dùng **một execution gồm hai goals có default phases tương ứng**, dễ đọc hơn cho lab.

### 4.2. Nếu chỉ chạy `mvn integration-test` thì sao?

Maven chạy mọi phase đến và **bao gồm** phase `integration-test`, **nhưng không chạy `post-integration-test` hoặc `verify`**. Với Failsafe, một assertion failure có thể đã được ghi vào summary mà lệnh chưa kết thúc bằng status thất bại vì chưa có `failsafe:verify`.

Đây chính là lý do tài liệu Maven khuyến cáo **không gọi phase `integration-test` như endpoint cuối của pipeline**. Dùng `mvn verify` để cho cleanup và verification được thực hiện.

## 5. Surefire và Failsafe: phạm vi trách nhiệm

| Tiêu chí | Surefire | Failsafe |
| --- | --- | --- |
| Mục tiêu chính | Unit tests | Integration tests |
| Goal chạy tests | `surefire:test` | `failsafe:integration-test` |
| Goal đánh giá riêng | Test outcome thường xử lý ngay ở `surefire:test` | `failsafe:verify` đọc summary |
| Lifecycle phase thường dùng | `test` | `integration-test` và `verify` |
| Auto-binding cho packaging `jar` | Thường có | Thường **không**; cần execution |
| Default test class patterns | `Test*.java`, `*Test.java`, `*Tests.java`, `*TestCase.java` | `IT*.java`, `*IT.java`, `*ITCase.java` |
| Reports mặc định | `target/surefire-reports` | `target/failsafe-reports` |
| Cần JUnit/TestNG engine | Có, khi framework yêu cầu | Có, khi framework yêu cầu |
| Hợp với test cần setup/teardown nhiều phase | Không phải mục đích chính | Có |

Tên class chỉ là **quy ước discovery mặc định**, không phải cơ chế tuyệt đối phân biệt test. Bạn có thể chỉnh includes/excludes ở cả hai plugins. Nếu cấu hình nhầm để **Surefire** chạy `*IT` ở phase test, integration tests có thể chạy **trước package**, và failure có thể ngăn setup/cleanup sau đó.

### 5.1. Vì sao hai plugins cùng phụ thuộc framework?

Cả hai chạy **test classes** đã biên dịch, có thể sử dụng cùng JUnit Platform/Jupiter engine khi versions tương thích. Dependency JUnit trong POM thường có `scope=test`, còn Surefire/Failsafe là Maven **build plugins**, không phải test dependencies của ứng dụng.

Ví dụ:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

JUnit Jupiter cung cấp API và engine phù hợp. Ở dòng Surefire/Failsafe **3.6.x**, JUnit Platform là cơ chế thống nhất để chạy frameworks được hỗ trợ. Không áp dụng quy tắc provider này như thể mọi bản Surefire 2.x đều hoạt động giống nhau.

## 6. Lab Java 17: setup fixture → integration-test → teardown → verify

Ta tạo một chương trình Java đơn giản gồm:
- Một service đọc nội dung từ file và định dạng thông điệp.
- Một unit test kiểm tra định dạng chuỗi, **không cần file bên ngoài**.
- Một integration test kiểm tra service khi đọc file **do lifecycle setup tạo ra**.
- Một Maven Antrun execution tạo fixture ở `pre-integration-test` và một execution xóa fixture ở `post-integration-test`.
- Maven Surefire ở `test` và Maven Failsafe ở `integration-test`, `verify`.

Không cần HTTP server, database hoặc Docker; tuy nhiên **đây vẫn là integration test có ý nghĩa thực hành**, vì nó kiểm tra phối hợp application service, filesystem và môi trường được dựng bởi build lifecycle. Trong dự án thật, môi trường có thể là database, queue, HTTP service hoặc container.

### 6.1. Điều kiện và cây thư mục

Yêu cầu:
- JDK 17+ có `javac` và `java`.
- Maven 3.6.3+ thích hợp với plugin versions đã chọn.
- Truy cập Maven Central hoặc mirror được phép ở lần đầu nếu local cache chưa có.
- Quyền ghi trong project `target` và local Maven repository.

```text
failsafe-integration-lab/
├── pom.xml
└── src/
    ├── main/java/dev/training/integration/
    │   ├── GreetingService.java
    │   └── App.java
    └── test/java/dev/training/integration/
        ├── GreetingServiceTest.java
        └── GreetingServiceIT.java
```

Hai test classes có tên **khác nhau** để phù hợp quy tắc discovery:
- `GreetingServiceTest`: Surefire, ở phase test.
- `GreetingServiceIT`: Failsafe, ở phase integration-test.

Linux/macOS, đứng tại thư mục mà bạn muốn tạo project:

```bash
mkdir -p failsafe-integration-lab/src/main/java/dev/training/integration
mkdir -p failsafe-integration-lab/src/test/java/dev/training/integration
cd failsafe-integration-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "failsafe-integration-lab/src/main/java/dev/training/integration" | Out-Null
New-Item -ItemType Directory -Force -Path "failsafe-integration-lab/src/test/java/dev/training/integration" | Out-Null
Set-Location failsafe-integration-lab
```

Các lệnh tiếp theo giả định **current working directory là `failsafe-integration-lab`**, và các code blocks được ghi rõ đường dẫn là **toàn bộ nội dung file tương ứng**.

### 6.2. POM Maven hoàn chỉnh: `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.integration</groupId>
    <artifactId>failsafe-integration-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
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
                <version>3.6.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
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
                                <mkdir dir="${project.build.directory}/it-env"/>
                                <echo file="${project.build.directory}/it-env/greeting.txt">Maven</echo>
                            </target>
                        </configuration>
                    </execution>

                    <execution>
                        <id>clean-it-fixture</id>
                        <phase>post-integration-test</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
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
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <demo.fixture>${project.build.directory}/it-env/greeting.txt</demo.fixture>
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
        </plugins>
    </build>
</project>
```

**Giải thích cấu hình:**

1. `<packaging>jar</packaging>`: với packaging này, Surefire đã có default binding ở phase `test`.
2. `<maven.compiler.release>17</maven.compiler.release>`: main/test source được biên dịch theo Java 17.
3. `junit-jupiter` dùng `scope=test` để cung cấp API và engine; không kéo JUnit vào runtime dependency của ứng dụng.
4. `maven-antrun-plugin`: goal `run` tạo file fixture ở `pre-integration-test`, sau đó goal `run` khác xóa thư mục ở `post-integration-test`.
5. `maven-failsafe-plugin`: hai goals được bind theo default phases `integration-test` và `verify`. Đây là phần **bắt buộc để `mvn verify` thực sự chạy IT** trong lab.
6. `<systemPropertyVariables>`: chuyển path fixture sang JVM test qua property `demo.fixture`. Test không phải đoán thư mục hiện hành.
7. `failIfNoTests=true` ở Surefire và Failsafe: đây là **chính sách riêng của lab** để nhận biết nếu test discovery không chạy đúng. Không áp dụng bừa lên module `pom` hoặc module hợp lệ không có tests.
8. `maven-jar-plugin` được ghim version; integration tests chạy **sau package**, nên artifact JAR đã được tạo trước phase integration-test nếu các phase trước thành công.

**Về cleanup:** Maven Antrun Plugin sử dụng Apache Ant tasks `mkdir`, `echo` và `delete`. Trong lab, `delete` chỉ xóa `target/it-env` do bước prepare của chính project tạo. **Không thay bằng đường dẫn cố định ngoài `target` hoặc xóa đệ quy một thư mục không thuộc phạm vi project.**

### 6.3. Java application service: `GreetingService.java`

Tệp `src/main/java/dev/training/integration/GreetingService.java`:

```java
package dev.training.integration;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GreetingService {

    public String format(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }

    public String readAndFormat(Path file) throws IOException {
        String name = Files.readString(file, StandardCharsets.UTF_8);
        return format(name);
    }
}
```

Hai chức năng:
- `format` là logic thuần; unit test có thể kiểm tra mà không cần môi trường.
- `readAndFormat` kết hợp file I/O của JDK và logic format, phù hợp để thử với fixture do build thiết lập.

`String.strip()` và `Files.readString` đều có trên Java 17. `IOException` được truyền ra để integration test biết lỗi khi file bị thiếu, không bị nuốt mất.

### 6.4. Java `main` để kiểm tra hành vi độc lập: `App.java`

Tệp `src/main/java/dev/training/integration/App.java`:

```java
package dev.training.integration;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        System.out.println(new GreetingService().format(" Maven "));
    }
}
```

Lớp này không cần JUnit hoặc filesystem. Khi chạy sau khi Maven compile thành công:

Linux/macOS:

```bash
java -cp target/classes dev.training.integration.App
```

Windows PowerShell:

```powershell
java -cp target\classes dev.training.integration.App
```

**Stdout chính xác của Java application:**

```text
Hello, Maven!
```

Đây là output của `App.main`, **không phải stdout nguyên văn của Maven/Failsafe**, vốn có thêm tên goal, test count và log.

### 6.5. Unit test cho logic thuần: `GreetingServiceTest.java`

Tệp `src/test/java/dev/training/integration/GreetingServiceTest.java`:

```java
package dev.training.integration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {

    private final GreetingService service = new GreetingService();

    @Test
    void formatsGreeting() {
        assertEquals("Hello, Maven!", service.format("  Maven  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
            () -> service.format("   "));
    }
}
```

Class tên `GreetingServiceTest` khớp quy tắc Surefire `**/*Test.java` và có **2 JUnit Jupiter methods**. Nó không cần fixture hay file `target/it-env`. Dự kiến hai tests chạy ở phase `test` trước khi Maven tạo môi trường integration test.

### 6.6. Integration test cho fixture được chuẩn bị: `GreetingServiceIT.java`

Tệp `src/test/java/dev/training/integration/GreetingServiceIT.java`:

```java
package dev.training.integration;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GreetingServiceIT {

    private final GreetingService service = new GreetingService();

    @Test
    void readsFixturePreparedByIntegrationLifecycle() throws IOException {
        String fileName = System.getProperty("demo.fixture");
        assertNotNull(fileName, "Maven must supply demo.fixture");

        Path fixture = Path.of(fileName);
        assertTrue(Files.isRegularFile(fixture),
            "pre-integration-test should create the fixture");

        assertEquals("Hello, Maven!", service.readAndFormat(fixture));
    }
}
```

Điểm then chốt:
- Tên class **`GreetingServiceIT`** khớp default includes của Failsafe `**/*IT.java`.
- `System.getProperty("demo.fixture")` nhận đường dẫn do Failsafe configuration chuyển vào test JVM.
- `assertTrue(Files.isRegularFile(fixture))` chứng minh môi trường đã được dựng.
- `readAndFormat` kiểm tra phối hợp Maven lifecycle setup → file I/O → ứng dụng.
- `assertEquals` chứng minh nội dung fixture và logic ứng dụng tương thích.
- Không có network, Docker, database hay credentials, nên bài có thể chạy hoàn toàn trên máy dùng JDK/Maven phù hợp.

Đối với môi trường production, integration tests thường kiểm tra nhiều hệ thống hơn; đây là ví dụ nhỏ để thấy **cơ chế Failsafe/phase**, không phải mẫu kiến trúc tích hợp phức tạp.

### 6.7. Chạy toàn bộ quy trình đúng cách

Từ thư mục project:

```bash
mvn -version
mvn -B -ntp clean verify
```

Nếu JDK/Maven/repository phù hợp:
1. Maven xóa `target` cũ.
2. Compiler Plugin biên dịch mã chính/test.
3. **Surefire** chạy 2 unit tests của `GreetingServiceTest` ở phase `test`.
4. JAR Plugin tạo `target/failsafe-integration-lab-1.0.0.jar` ở phase `package`.
5. **Antrun prepare** tạo `target/it-env/greeting.txt` chứa `Maven`.
6. **Failsafe integration-test** chọn `GreetingServiceIT` và chạy **1 integration test**, ghi reports và summary.
7. **Antrun cleanup** xóa thư mục `target/it-env`.
8. **Failsafe verify** đọc summary, thấy test pass và cho build hoàn thành `BUILD SUCCESS` nếu không có lỗi khác.

**Các thống kê test kỳ vọng:**

```text
Surefire: Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
Failsafe: Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **hai dòng tổng hợp về nội dung thống kê**, không phải nguyên văn stdout Maven. Console có thể in `[INFO]`, tên test class, tốc độ chạy, log plugins và thứ tự thông điệp khác. Kiểm tra **thư mục reports và exit code thật** để xác nhận.

### 6.8. Xem reports sau khi `mvn verify` hoàn tất

Các file thường xuất hiện:

```text
target/
  surefire-reports/
    TEST-dev.training.integration.GreetingServiceTest.xml
    dev.training.integration.GreetingServiceTest.txt
  failsafe-reports/
    TEST-dev.training.integration.GreetingServiceIT.xml
    dev.training.integration.GreetingServiceIT.txt
    failsafe-summary.xml
```

Báo cáo XML `TEST-*.xml` mô tả test suites/cases, giúp CI tổng hợp kết quả. File summary của Failsafe được **goal verify** sử dụng. Tên file có thể bị thay đổi nếu cấu hình report suffix/directory khác.

Linux/macOS:

```bash
ls target/surefire-reports
ls target/failsafe-reports
```

PowerShell:

```powershell
Get-ChildItem -Path target/surefire-reports
Get-ChildItem -Path target/failsafe-reports
```

Sau verify thành công, **`target/it-env` không còn** do execution cleanup. Điều này chứng minh setup/cleanup lifecycle hoạt động trong lab. **Đừng xóa `target/failsafe-reports` bằng cleanup**, vì đó là dữ liệu cần cho `failsafe:verify` và CI.

## 7. Tạo một integration-test failure để quan sát deferred failure

Hãy thử trên một bản lab có thể khôi phục. Trong `GreetingServiceIT.java`, thay duy nhất:

```java
assertEquals("Hello, Maven!", service.readAndFormat(fixture));
```

bằng:

```java
assertEquals("Hello, Java!", service.readAndFormat(fixture));
```

Đây là **một dòng thay thế bên trong test method**, không phải Java class độc lập. Vì fixture thực chứa `Maven`, giá trị service trả về là `Hello, Maven!`, nên assertion mới sẽ thất bại.

Chạy:

```bash
mvn -B -ntp clean verify
```

Quan sát:
- Unit tests của Surefire vẫn pass.
- Failsafe integration-test thấy một **assertion failure**.
- Maven vẫn có cơ hội thực hiện execution `clean-it-fixture` ở phase `post-integration-test`.
- Failsafe verify đọc summary và báo lỗi; toàn bộ lệnh kết thúc **BUILD FAILURE** với exit status khác 0 theo behavior Failsafe mặc định.
- Folder `target/it-env` đã được xóa nếu bước teardown đã chạy thành công; report `target/failsafe-reports` vẫn còn phục vụ điều tra.

**Bảng kỳ vọng của thí nghiệm:**

| Thành phần | Kết quả |
| --- | --- |
| Surefire unit tests | 2 passed |
| Failsafe IT test | 1 failed assertion |
| `pre-integration-test` | Tạo fixture |
| `post-integration-test` | Xóa fixture |
| `failsafe:verify` | Báo test failure và làm build thất bại |
| `target/failsafe-reports` | Vẫn chứa dữ liệu chẩn đoán |

**Rất quan trọng:** Không cố định nguyên văn stack trace, summary XML fields hay thứ tự log. Kết quả có thể khác nếu có lỗi môi trường, thiếu plugin artifact, JVM fork bị crash hoặc teardown lỗi. Luồng trên minh họa **assertion failure bình thường** mà Failsafe thiết kế để defer.

Sau thí nghiệm, **khôi phục assertion thành `"Hello, Maven!"`**, rồi chạy lại `mvn clean verify` để có build PASS trước khi tiếp tục.

## 8. Vì sao không nên dừng ở `mvn integration-test`?

Nếu từ project lab bạn chạy:

```bash
mvn -B -ntp clean integration-test
```

Maven dừng sau phase `integration-test`:
- Setup đã tạo `target/it-env`.
- Failsafe đã chạy IT (nếu goals được bind và project build tới đó).
- **`post-integration-test` chưa chạy**, nên fixture có thể còn trên disk.
- **`failsafe:verify` chưa chạy**, nên test failure chưa được chuyển thành build failure như lộ trình bình thường.

Ngay cả khi goal integration-test đã báo một lỗi assertion trong logs, **exit code cuối có thể chưa phản ánh failure đó**. Đây không phải bug; bạn đã yêu cầu dừng lifecycle quá sớm.

Nếu cố chạy:

```bash
mvn org.apache.maven.plugins:maven-failsafe-plugin:3.6.1:verify
```

ngay sau đó thì mục đích verify có thể đọc summary cũ/hiện có, nhưng **đây vẫn không phải thay thế đầy đủ cho phase `post-integration-test`**, và có rủi ro nếu quá trình trước chưa chạy đủ. Để kết thúc đúng quy trình, hãy quay về `mvn clean verify` (hoặc pipeline nhiều bước đã thiết kế có teardown rõ ràng), không coi việc gọi một goal lẻ là mô hình đáng khuyến cáo.

### 8.1. Tại sao CI dễ bị “xanh giả”?

Nếu pipeline chạy `mvn integration-test` rồi chỉ kiểm tra exit code, nhưng không chạy `mvn verify`, một integration assertion failure có thể đã được ghi vào report mà pipeline vẫn kết thúc thành công.

Với dự án có Failsafe, **release gate phải chờ phase verify** (hoặc một cơ chế kiểm tra kết quả tương đương có chủ đích). Không phát hành artifact chỉ vì `integration-test` đã hoàn tất mà bỏ qua result verification.

## 9. Test failure, test error và lỗi hạ tầng: không phải một loại

### 9.1. Assertion failure

Ví dụ:

```java
assertEquals("Hello, Java!", "Hello, Maven!");
```

Đây là **đoạn assertion minh họa bên trong test method**. JUnit thông báo không đúng expected value; Failsafe ghi **failure**. Deferred-failure thiết kế cho tình huống này.

### 9.2. Test error do exception

Ví dụ `Files.readString` ném `IOException` vì fixture không có. JUnit/Failsafe có thể ghi test **error**. Trong các tình huống test chạy và provider có thể ghi kết quả, Failsafe thường defer **test errors** tương tự test failures để phase teardown có cơ hội chạy.

Tuy nhiên khi test JVM bị kill đột ngột, mất kết nối với fork hoặc provider/plugin crash, không được giả định summary đã được ghi thành công hoặc cleanup vẫn sẽ chạy.

### 9.3. Compilation failure

Nếu Java test import sai `@Test` hoặc mã nguồn lỗi cú pháp, Maven thất bại ở `compiler:testCompile`, **trước khi đến pre-integration-test**. Failsafe chưa chạy, không có test summary mới.

### 9.4. Setup failure

Nếu Antrun ở `pre-integration-test` không tạo được fixture do permission hay cấu hình Ant sai, Maven có thể dừng ngay; việc deferred test failure không có cơ hội xảy ra. Những tài nguyên setup được một phần cần cleanup dự phòng ở CI nếu có rủi ro.

### 9.5. Teardown failure

Nếu `post-integration-test` xóa fixture không được, Maven có thể báo build failure **ở cleanup goal**, ngay cả khi các integration test assertions đã pass. Không che mất lỗi này bằng cách chỉ đọc test count.

### 9.6. Failsafe verify failure

Khi summary cho thấy test failures/errors, `failsafe:verify` làm build failure ở phase verify theo cấu hình mặc định. Đây là cách báo lỗi **có trì hoãn** mà ta mong muốn trong bài.

**Bảng chẩn đoán:**

| Dấu hiệu | Giai đoạn thường gặp | Có phải deferred test failure của Failsafe? |
| --- | --- | --- |
| Assertion expected/actual khác nhau | `failsafe:integration-test` | Có, nếu test result được ghi nhận. |
| Test method ném exception | `failsafe:integration-test` | Thường có nếu provider vẫn ghi được result. |
| Java test không compile | `compiler:testCompile` | Không. |
| Maven không tải được Failsafe Plugin | Plugin resolution | Không. |
| DB/container start không được | `pre-integration-test` | Không. |
| JVM bị OOM/kill ngoài dự kiến | Test execution infrastructure | Không thể hứa defer/cleanup. |
| Dọn fixture/container bị lỗi | `post-integration-test` | Không, đây là teardown failure. |
| Summary được đọc và cho thấy tests failed | `failsafe:verify` | Đây là bước **báo fail cuối cùng**. |

## 10. Cách chọn đúng integration-test class

Failsafe 3.6.1 mặc định tìm những tên lớp kiểu:

```text
**/IT*.java
**/*IT.java
**/*ITCase.java
```

Đây là **patterns tương ứng với test source/class naming**, không có nghĩa plugin thực thi thẳng file `.java`. Maven Compiler Plugin biên dịch test sources ở phase `test-compile`; Failsafe tìm compiled classes và framework engine thực thi methods có `@Test`.

Ví dụ:

| Tên class | Surefire mặc định? | Failsafe mặc định? |
| --- | --- | --- |
| `GreetingServiceTest` | Có | Không |
| `GreetingServiceIT` | Không | Có |
| `ITGreetingService` | Không | Có |
| `GreetingServiceITCase` | Không | Có |
| `GreetingServiceSpec` | Không | Không, trừ cấu hình bổ sung |

Trong lab, `GreetingServiceTest` và `GreetingServiceIT` tách biệt nên không chạy trùng. Nếu custom includes/excludes, hãy đảm bảo một test suite không bị chạy cả Surefire và Failsafe ngoài ý muốn.

### 10.1. Chọn một integration-test class

Failsafe dùng selector riêng có tên property **`it.test`**. Khi đang ở thư mục lab:

```bash
mvn -B -ntp clean verify -Dit.test=GreetingServiceIT
```

Goal Failsafe chọn class phù hợp, trong khi Surefire vẫn có thể chạy unit tests theo cấu hình bình thường. Nếu tên class không tồn tại, chính sách `failIfNoSpecifiedTests` hoặc cấu hình tương ứng có thể gây lỗi. **Không dùng `-Dtest=...` rồi mặc định nó điều khiển Failsafe**; `-Dtest` là convention của Surefire, còn Failsafe sử dụng `-Dit.test`.

### 10.2. Chọn test method cụ thể

Failsafe cũng có cơ chế chọn class/method theo selector phù hợp với phiên bản plugin. Ví dụ:

```bash
mvn -B -ntp clean verify "-Dit.test=GreetingServiceIT#readsFixturePreparedByIntegrationLifecycle"
```

Dấu nháy tránh một số shell parsing với `#` hoặc ký tự đặc biệt. Test method phải tồn tại và được engine phát hiện. Kết quả chạy subset không cho phép kết luận các tests không được chọn đều đã pass.

### 10.3. Lọc theo JUnit Jupiter tags

Nếu các tests có `@Tag("integration")`, Failsafe/JUnit Platform hỗ trợ group/tag filtering theo versions tương thích. Ví dụ annotation:

```java
@Test
@org.junit.jupiter.api.Tag("integration")
void readsFixturePreparedByIntegrationLifecycle() throws IOException {
    // Nội dung test giống lab, được lược bỏ ở snippet minh họa này.
}
```

Đây là **đoạn Java minh họa cách đặt annotation**, không phải file độc lập hoặc phần cần thay vào lab. Không thêm comment placeholder vào code lab khi muốn chạy; file `GreetingServiceIT.java` đầy đủ nằm ở mục 6.6.

Lọc qua property:

```bash
mvn clean verify -Dgroups=integration
```

Vì `groups` có thể ảnh hưởng cả Surefire và Failsafe cùng dùng JUnit Platform, **không dùng lệnh này để kết luận unit tests vẫn chạy đầy đủ**; kiểm tra từng plugin report. Nếu chỉ muốn filter Failsafe, cấu hình `groups` trong Failsafe plugin hoặc profile dành cho integration tests.

## 11. Bỏ qua integration tests: các flags dễ gây hiểu lầm

**Đặc biệt với Failsafe 3.6.1**, các flags có ý nghĩa không giống những bài hướng dẫn cũ.

| Flag / lựa chọn | Surefire unit tests | Failsafe integration tests | Test source compilation |
| --- | --- | --- | --- |
| Không skip | Chạy | Chạy nếu Failsafe bind đúng | Có |
| **`-DskipITs`** | Vẫn chạy | **Skip IT execution** | Vẫn biên dịch test sources theo luồng thông thường |
| **`-DskipTests`** | **Skip Surefire execution** | **Không tự skip Failsafe trong 3.6.x** | Vẫn biên dịch test sources theo luồng thông thường |
| **`-Dmaven.test.skip=true`** | Skip theo plugins tiêu chuẩn | Skip theo plugins tiêu chuẩn | Compiler Plugin bỏ qua test compilation |
| `<testFailureIgnore>true</testFailureIgnore>` | Không phải cờ skip | Failsafe vẫn có thể chạy tests nhưng không fail build vì test results | Không đổi riêng vì cờ này |

**Lưu ý thay đổi phiên bản:** Tài liệu *What’s New in Surefire 3.6.x* nêu rõ **Failsafe `skipTests` đã bị deprecated và không còn bind vào user property `skipTests`**. Để skip IT trong Failsafe 3.6.1, sử dụng **`-DskipITs`**. Tuy nhiên một cấu hình XML tường minh `<skipTests>true</skipTests>` trong Failsafe vẫn có thể được chấp nhận theo plugin docs.

### 11.1. Ví dụ trong lab

Chỉ skip Failsafe IT tests:

```bash
mvn -B -ntp clean verify -DskipITs
```

Chỉ skip Surefire unit tests trong các thiết lập 3.6.1 phổ biến:

```bash
mvn -B -ntp clean verify -DskipTests
```

Bỏ cả compilation/execution test theo các plugins chuẩn:

```bash
mvn -B -ntp clean verify -Dmaven.test.skip=true
```

**Bẫy rất quan trọng:** `-DskipITs` chỉ yêu cầu **Failsafe bỏ chạy IT**. Nó **không tự tắt các executions Antrun** đang bind ở `pre-integration-test` và `post-integration-test`. Với lab, chúng vẫn có thể tạo/xóa file fixture dù IT bị skip. Với hệ thống có container tốn phí, nên cấu hình profile/property điều kiện để tắt **cả setup và teardown** khi bạn thực sự chủ động skip integration tests.

### 11.2. Đừng dùng skip làm tiêu chí “QA PASS”

`mvn verify -DskipITs` có thể hoàn tất thành công nhưng **không chứng minh integration tests đã qua**. Khi release artifact, phải dựa trên pipeline có integration tests thật sự được chạy, hoặc một chính sách minh bạch về các trường hợp được miễn chạy.

## 12. `failIfNoTests`, `failIfNoSpecifiedTests` và `testFailureIgnore`

Ba cờ phục vụ ba loại tình huống khác nhau:

| Tham số | Ý nghĩa | Rủi ro nếu dùng sai |
| --- | --- | --- |
| `failIfNoTests` | Báo lỗi nếu không có test nào chạy theo chính sách goal khi kỳ vọng phải có. | Đặt lên mọi module `pom` hoặc module hợp lệ không có IT gây fail không mong muốn. |
| `failIfNoSpecifiedTests` | Có nên lỗi nếu selector cụ thể như `it.test` không khớp test nào? | Tắt nó có thể che typo trong CI. |
| `testFailureIgnore` | Không làm build thất bại vì kết quả test fail. | Cho phép phát hành artifact khi IT failures vẫn tồn tại. |

Trong lab đã đặt `<failIfNoTests>true</failIfNoTests>` cho cả Surefire và Failsafe vì **biết trước có một unit test class và một IT test class**. Nhưng khi áp dụng vào dự án nhiều Maven modules, hãy đặt chính sách theo từng module thay vì copy vào parent aggregator vô điều kiện.

### 12.1. Có nên dùng testFailureIgnore?

Thông thường **không** ở release gate:

```xml
<configuration>
    <testFailureIgnore>true</testFailureIgnore>
</configuration>
```

Đây là đoạn cấu hình có thể dùng trong mục đích thí nghiệm/diagnostics, **không phải lời khuyên đưa vào POM production**. Nếu cần thu thập nhiều reports ngay cả khi tests fail, nên để Failsafe ghi reports rồi thực hiện cleanup và **đánh giá failure ở verify** thay vì bật ignore vĩnh viễn.

### 12.2. Test failure khác no-tests failure

Nếu không có integration test nào được discover mà `failIfNoTests=false`, build có thể báo success dù project từng có IT tests. Ngược lại, `failIfNoTests=true` có thể gây fail ở project không thiết kế có tests.

Trong CI:
- Xác định modules nào bắt buộc có IT.
- Ghi số lượng test tối thiểu kỳ vọng khi thích hợp.
- Kiểm tra report files đúng phiên build, tránh file cũ.
- Nếu cần chọn một test class, giữ `failIfNoSpecifiedTests` bật để typo không qua lặng lẽ.
- Không coi một report thiếu là success.

## 13. Kiểm tra trạng thái build: dùng exit code, report và goal logs

Một chiến lược đáng tin cậy:
1. **Xem lệnh CI thật:** `mvn verify` hay chỉ `mvn integration-test`?
2. **Xem Failsafe execution bindings:** có cả hai goals không?
3. **Xem stdout/stderr:** goal nào thất bại, test counts là bao nhiêu?
4. **Xem `target/failsafe-reports/`:** XML suite reports, test names và summary.
5. **Xem exit code của `mvn verify`:** khác 0 thì pipeline phải coi là thất bại.
6. **Kiểm tra cleanup:** fixture/container đã dọn chưa; nếu chưa, kích hoạt fallback teardown theo chính sách.
7. **Không dùng report cũ:** chạy `mvn clean verify` hoặc đối chiếu timestamp/artifact khi điều tra.

### 13.1. Có nên chỉ grep BUILD SUCCESS?

Không. Có thể một lệnh chỉ chạy `mvn test` (chưa đến integration-test) hoặc `mvn integration-test` (chưa verify). Dù in BUILD SUCCESS, điều đó không chứng minh đã chạy **đúng bộ IT và result verification**. Phải xác minh log goal, report và CI command.

### 13.2. Có nên dựa vào một file reports?

Không. `failsafe-summary.xml` là input để Failsafe verify đánh giá kết quả; `TEST-*.xml` mô tả test cases. Với multi-module build, mỗi module có thể có file summary/report riêng. Chỉ nhìn một file root có thể bỏ sót failures ở modules khác.

### 13.3. Output chính xác của lab là gì?

- `java -cp target/classes dev.training.integration.App`: **chính xác một dòng** `Hello, Maven!` trên stdout.
- `mvn clean verify` khi tests pass: log Maven khác nhau theo môi trường; dự kiến Surefire **2 tests pass**, Failsafe **1 IT pass**, cleanup và build success.
- `mvn clean verify` khi đổi assertion trong IT: dự kiến Failsafe **1 test failure**, cleanup vẫn có cơ hội chạy, rồi build failure ở verify.

Không in một stack trace giả làm “kết quả thực thi”; khi dạy, nêu các điều kiện cần kiểm chứng và nội dung báo cáo dự kiến.

## 14. Các lỗi phổ biến

### Lỗi A — `mvn verify` không chạy integration tests

Nguyên nhân thường gặp:
- Chưa khai báo Maven Failsafe Plugin trong `<build><plugins>`.
- Có plugin nhưng thiếu `<executions>` cho `integration-test` và `verify`.
- Test class không khớp `IT*.java` / `*IT.java` / `*ITCase.java`.
- `-DskipITs` đang bật, profile IT chưa được kích hoạt.
- Test framework/engine không có trên test classpath.

**Cách xử lý:** xem effective POM, test discovery và log goal. Không chỉ thêm `maven-failsafe-plugin` vào `<pluginManagement>` rồi kỳ vọng nó tự chạy.

### Lỗi B — `mvn integration-test` báo success dù test thất bại

Đây thường là **hành vi deferred failure** của Failsafe do verify chưa được gọi. **Đổi CI command sang `mvn verify`**; không biến Failsafe thành plugin fail sớm để “sửa” điều đó.

### Lỗi C — Cleanup không chạy

Kiểm tra CI có dừng ở `integration-test` không, hoặc có lỗi build sớm trước `post-integration-test`. Nếu cần tài nguyên ngoài như container/DB, thiết kế **pipeline finally/always cleanup** ngoài Maven để xử lý CI cancel/timeout và các lỗi hạ tầng.

### Lỗi D — `failsafe:verify` không thấy summary

Có thể chưa chạy `failsafe:integration-test`, đã gọi verify trực tiếp không đúng lifecycle, summary bị xóa bởi cleanup hoặc hai goals dùng `summaryFile` khác nhau. Đừng tạo file XML giả để làm verify pass; hãy chạy đúng lifecycle và kiểm tra đường dẫn summary.

### Lỗi E — `Tests run: 0` nhưng có test class

Kiểm tra:
- Test file nằm đúng `src/test/java` và được compiler biên dịch thành `target/test-classes`.
- Tên class có đúng Failsafe convention?
- JUnit `@Test` import đúng `org.junit.jupiter.api.Test`?
- `junit-jupiter` có Jupiter Engine không?
- Maven/Failsafe version có JUnit Platform provider tương thích?
- `it.test`, tags, includes/excludes, `@Disabled` hay skip flags có lọc hết tests?
- Project/module nào đang được chạy?

### Lỗi F — Tests chạy cả Surefire và Failsafe

Thường do cấu hình includes của Surefire vô tình thêm `*IT`, hoặc includes của Failsafe bắt cả `*Test`. Hậu quả: tests chạy sớm, chậm, có side effects lặp và báo cáo không như mong muốn. Phân tách tên file và profiles/configuration rõ ràng.

### Lỗi G — Unit tests thất bại, Failsafe không được gọi

Surefire chạy ở phase `test` trước Failsafe. Nếu unit test fail làm Maven dừng, build sẽ không đi đến `package` hoặc `integration-test`. Đây là hành vi hợp lý; sửa unit tests trước khi kết luận Failsafe bị lỗi.

### Lỗi H — IT pass local nhưng fail CI

Kiểm tra JDK/Maven versions, file path separators, filesystem permission, môi trường mạng, startup readiness, timing, cleanup, shared resources và dependencies của test. Tránh assertions dựa vào sleep cố định; ưu tiên health checks, polling có timeout, fixtures độc lập và môi trường isolation.

### Lỗi I — Failsafe reports có failures nhưng pipeline vẫn deploy

Kiểm tra:
- Pipeline chỉ chạy `mvn integration-test`?
- Có `testFailureIgnore=true` hoặc `maven.test.failure.ignore=true`?
- Có wrapper shell dùng `|| true`, nuốt exit code?
- Artifact publish có được thực hiện trước `verify`?
- CI đang đọc report của build hiện tại hay file từ cache?

Release gate phải dựa trên **verify outcome** và chính sách chất lượng, không chỉ test count log.

## 15. Maven reactor nhiều modules và Failsafe

Một workspace có:
```text
workspace/
├── pom.xml                 (packaging=pom)
├── service/
│   ├── pom.xml             (packaging=jar)
│   └── src/test/java/...IT.java
└── client/
    ├── pom.xml             (packaging=jar)
    └── src/test/java/...IT.java
```

Khi `mvn verify` chạy từ root:
- Maven reactor xử lý các modules theo dependency relationships và build order.
- Mỗi module jar có execution Failsafe nếu POM/parent thiết lập phù hợp.
- Test reports thường nằm **trong `target/failsafe-reports` của từng module**, không phải một thư mục root duy nhất.
- Module `pom` có thể không có IT tests; hãy áp `failIfNoTests` ở những modules thực sự có IT requirement.

Ví dụ CLI chọn module:

```bash
mvn -pl :service -am clean verify
```

`-pl` chọn module; `-am` bao gồm Maven reactor dependencies cần thiết. Nhưng nếu `service` cần một DB/server chạy ngoài Maven, bản thân `-am` **không khởi động service đó**; vẫn cần setup step/profile/container orchestration.

### 15.1. Thu thập report nhiều module

Một glob CI có thể dùng:

```text
**/target/failsafe-reports/TEST-*.xml
```

Đây là **glob minh họa**, không phải một lệnh shell runnable. Cần kiểm tra syntax của CI provider và đừng xóa report trước khi upload artifact từ job thất bại.

### 15.2. Reactor failure và deferred failure

Nếu một module có IT failure ở `verify`, Maven có thể dừng/đánh dấu failure theo reactor behavior, ảnh hưởng các modules downstream. Deferred failure **chỉ đảm bảo cơ hội teardown trong module/luồng tương ứng** khi lifecycle đi qua `post-integration-test`; nó không phải “chạy toàn bộ mọi module rồi mới fail ở cuối”.

## 16. Profiles và môi trường integration tests

Nhiều nhóm muốn unit tests chạy trong mỗi pull request, còn integration tests chỉ chạy trong một pipeline/profile nhất định. Bạn có thể dùng Maven profile để kích hoạt Failsafe/setup, nhưng cần thiết kế sao cho:
- Nếu profile không bật, đừng suy ra IT đã chạy.
- Nếu profile bật, bind **đủ prepare → integration-test → cleanup → verify**.
- Không chỉ skip Failsafe mà vẫn start dịch vụ tốn phí.
- Dùng credentials/endpoint từ CI secret manager; không hardcode vào POM.
- Ghi lại profile được kích hoạt để người điều tra biết pipeline đã chạy gì.
- Khi deploy, chính sách release nên đòi các IT results phù hợp với commit/artifact.

Ví dụ profile chỉ bật khi chỉ định:

```bash
mvn -Pwith-it clean verify
```

Lệnh trên **chỉ có ý nghĩa khi POM thật sự định nghĩa profile `with-it`**. Đây là cách gọi minh họa, không phải profile có sẵn trong lab. Lab ở mục 6 cố ý bật executions trực tiếp để người học nhìn thấy chúng mà không phải cấu hình profile.

## 17. Fail-fast và hiệu quả chạy tests

Failsafe có những option như `skipAfterFailureCount` trong các phiên bản hỗ trợ để giới hạn số tests còn chạy sau failures; nhưng:
- Với parallel/fork execution, số tests ngừng thực tế có thể không chính xác tuyệt đối do race conditions.
- Không nhầm **fail-fast trong một test suite** với **deferred build failure đến verify**. Failsafe vẫn có cơ chế báo trạng thái cuối ở verify.
- Chỉ bật fail-fast khi tiết kiệm thời gian quan trọng hơn việc thu thập đầy đủ số failures trong lần chạy.
- Đối với integration test environment chung, dọn dẹp resources phải độc lập với việc một test method có chạy hay không.

Ví dụ tham số:

```bash
mvn clean verify -Dfailsafe.skipAfterFailureCount=1
```

Không giả định chỉ đúng một test đã thực thi khi bật parallel; xem báo cáo và phiên bản plugin để hiểu giới hạn.

## 18. Bảo mật dữ liệu kiểm thử và reports

Integration tests thường chạm vào dịch vụ thật hoặc dữ liệu gần thật. Một số nguyên tắc:
- Sử dụng test account và test fixtures, không dùng production credentials.
- Không in token, Authorization header, password, connection strings có secret vào Maven logs hoặc JUnit report `system-out`.
- Không lưu raw `settings.xml`, `mvn -X` output hoặc report chưa kiểm duyệt trong issue công khai.
- Giới hạn tài nguyên môi trường IT, thiết lập teardown và retention.
- Chặn artifact publishing khi test result verification thất bại.
- Bảo vệ CI artifacts vì stack traces/reports có thể chứa đường dẫn nội bộ và system properties.
- Với DB tests, reset data giữa tests và không chia sẻ mutable environment không có isolation.
- Tránh container/network service cần internet ngoài nếu có thể kiểm chứng bằng local stub/mocks ở mức phù hợp.
- Không coi việc Failsafe viết report thành công là bằng chứng secret đã được che tự động.

## 19. Checklist áp dụng trong dự án thật

- [ ] Dự án biết rõ phần nào là unit tests và phần nào là integration tests.
- [ ] Surefire và Failsafe có versions được ghim và tương thích với JDK/test engine.
- [ ] IT class naming patterns/engine phù hợp; không có test suite “mất tích”.
- [ ] Failsafe **có cả goals `integration-test` và `verify`** khi dùng lifecycle.
- [ ] Setup được bind ở `pre-integration-test`; teardown ở `post-integration-test` khi cần.
- [ ] Pipeline dùng **`mvn verify`**, không kết thúc ở phase `integration-test`.
- [ ] Failsafe summary không bị xóa trước `verify`.
- [ ] Chạy thử một integration assertion failure và xác nhận teardown vẫn có cơ hội chạy.
- [ ] Có cleanup dự phòng khi CI abort, timeout hoặc plugin infrastructure fail.
- [ ] Không bật `testFailureIgnore` cho release gate.
- [ ] Biết sự khác biệt `-DskipITs` và `-DskipTests` trong Failsafe 3.6.x.
- [ ] Kiểm tra `failIfNoTests` phù hợp từng Maven module.
- [ ] Thu thập `target/failsafe-reports/TEST-*.xml` và Surefire reports trong CI.
- [ ] Dựa trên exit code của `mvn verify`, report counts và goals thực thi để quyết định phát hành.
- [ ] Test environment có isolation, timeout và cleanup an toàn.
- [ ] Không để token/password lọt vào POM, logs hay test reports.

## 20. Bài tập tự kiểm tra và đáp án

**Câu 1.** `mvn integration-test` và `mvn failsafe:integration-test` có giống nhau không?

**Đáp án:** Không. Lệnh đầu chạy default lifecycle đến phase `integration-test`; lệnh sau gọi một Failsafe goal trực tiếp, không tự gọi tất cả các phase trước.

**Câu 2.** Failsafe goal nào ghi test results và summary?

**Đáp án:** `failsafe:integration-test`.

**Câu 3.** Failsafe goal nào đánh giá kết quả để báo build failure?

**Đáp án:** `failsafe:verify`, thường được bind vào phase `verify`.

**Câu 4.** Vì sao Failsafe không fail ngay khi assertion integration test sai?

**Đáp án:** Để phase `post-integration-test` có cơ hội teardown môi trường trước khi build bị đánh dấu thất bại ở `verify`.

**Câu 5.** Deferred failure có bảo đảm cleanup chạy khi CI kill process/JVM hoặc plugin resolution lỗi không?

**Đáp án:** Không. Nó xử lý test results thông thường, không thay cho cleanup dự phòng trước lỗi hạ tầng/CI abort.

**Câu 6.** Khi dự án jar chỉ khai báo Failsafe version nhưng không có executions, `mvn verify` có tự chạy IT không?

**Đáp án:** Không mặc định; cần bind `integration-test` và `verify` hoặc cơ chế tương ứng.

**Câu 7.** Tên class `GreetingServiceIT` thường được plugin nào chọn mặc định?

**Đáp án:** Failsafe. Surefire mặc định chọn tên `*Test`, `Test*`, `*Tests` hoặc `*TestCase`.

**Câu 8.** File `failsafe-summary.xml` mặc định ở đâu?

**Đáp án:** `target/failsafe-reports/failsafe-summary.xml`; goal verify đọc nó.

**Câu 9.** Trong lab có bao nhiêu Surefire unit tests và Failsafe integration tests?

**Đáp án:** **2 unit tests** và **1 integration test**.

**Câu 10.** Trong lab, khi thay assertion IT thành `Hello, Java!`, build dự kiến fail ở phase nào?

**Đáp án:** Failsafe có thể ghi failure tại `integration-test`, cleanup ở `post-integration-test`, rồi `failsafe:verify` báo build failure tại `verify`.

**Câu 11.** Vì sao `mvn clean integration-test` không phải lệnh hoàn chỉnh cho lab?

**Đáp án:** Nó chưa đi tới `post-integration-test` và `verify`, nên fixture có thể chưa được dọn và test failure chưa được đánh giá cuối.

**Câu 12.** Trong Failsafe 3.6.1, muốn skip integration tests bằng CLI dùng `-DskipTests` hay `-DskipITs`?

**Đáp án:** Dùng **`-DskipITs`**. `-DskipTests` không còn tự skip Failsafe integration tests trong dòng 3.6.x.

**Câu 13.** `-DskipITs` có tự bỏ qua Antrun setup/teardown trong lab không?

**Đáp án:** Không. Nó điều khiển Failsafe, không tự hủy những plugin goals khác đã bind ở lifecycle phases.

**Câu 14.** `-Dit.test=GreetingServiceIT` dùng cho plugin nào?

**Đáp án:** Failsafe integration-test selection. `-Dtest` thường là selector của Surefire.

**Câu 15.** Tại sao không nên cho CI publish artifact sau khi chỉ chạy `mvn integration-test`?

**Đáp án:** Vì chưa có `failsafe:verify` để xác nhận test failures và chưa chạy cleanup phase, có nguy cơ “xanh giả”.

**Câu 16.** Trong lab, stdout chính xác của Java `App.main` là gì?

**Đáp án:** Một dòng `Hello, Maven!`, không phải toàn bộ Maven test log.

**Câu 17.** Làm sao biết failure là do test assertion hay teardown?

**Đáp án:** Xem goal thất bại trong Maven log, summary/XML Failsafe, và error details của Antrun post-integration-test. Hai trường hợp khác nhau về nguyên nhân.

**Câu 18.** `mvn -DskipITs verify` có chứng minh integration tests đã pass không?

**Đáp án:** Không. Flag đó bỏ chạy IT; phải có pipeline/report từ một lần kiểm thử thực sự nếu muốn release gate dựa vào IT.

## 21. Tài liệu chính thức

- [Apache Maven Failsafe Plugin – Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/): lý do chia integration-test và verify, cleanup ở post-integration-test.
- [Apache Maven Failsafe Plugin – Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html): POM executions gồm `integration-test` và `verify`.
- [Apache Maven Failsafe Plugin – failsafe:integration-test](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html): default phase, summaryFile, test selection, skip flags và output.
- [Apache Maven Failsafe Plugin – failsafe:verify](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html): summaryFile, failIfNoTests, testFailureIgnore và verification.
- [Apache Maven Failsafe Plugin – Using JUnit Platform](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/junit-platform.html): test engine, IT naming patterns, tags và JUnit Platform.
- [Apache Maven Surefire/Failsafe – What’s New in 3.6.x](https://maven.apache.org/surefire/maven-failsafe-plugin/whats-new-3-6-x.html): sự thay đổi `skipTests`, `skipITs` và provider architecture.
- [Apache Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): các phase pre-/post-integration-test, integration-test và verify.
- [Apache Maven Surefire Plugin – Introduction](https://maven.apache.org/surefire/maven-surefire-plugin/): unit tests ở phase test.
- [Apache Maven Antrun Plugin – Usage](https://maven.apache.org/plugins/maven-antrun-plugin/usage.html): bind Ant targets vào lifecycle để tạo và dọn fixtures.
- [JUnit 5 User Guide – Maven](https://junit.org/junit5/docs/current/user-guide/#running-tests-build-maven): JUnit Jupiter test methods và Maven/Surefire/Failsafe integration.
