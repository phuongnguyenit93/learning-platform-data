# Maven `verify` và các bước kiểm chứng trước khi xuất bản

## 1. Vai trò của `verify` trong Maven

Maven có ba lifecycle mặc định: `clean`, `default` và `site`. Trong **default lifecycle**, các pha chính đi theo thứ tự:

~~~text
validate → compile → test → package
                            ↓
                    pre-integration-test
                            ↓
                     integration-test
                            ↓
                    post-integration-test
                            ↓
                          verify
                            ↓
                          install
                            ↓
                          deploy
~~~

Sơ đồ lược bỏ một số pha trung gian như `process-resources`, `test-compile` và `prepare-package`. Ý nghĩa quan trọng:

- **`package`** đóng gói artifact (thường là JAR/WAR) sau các bước biên dịch và kiểm thử được bind trước đó.
- **`verify`** là pha dùng để kiểm tra artifact và tiêu chí chất lượng, có thể đánh giá kết quả integration test và các rule được cấu hình.
- **`install`** cài artifact và POM vào Maven local repository, thường là `~/.m2/repository`.
- **`deploy`** chuyển artifact/POM tới remote **artifact repository** được cấu hình; đó không phải việc khởi động ứng dụng trên production server.

Khi chạy `mvn verify`, Maven tự chạy lần lượt các pha của default lifecycle **từ đầu đến `verify`**, bao gồm `package`, nếu cấu hình và plugin tương ứng yêu cầu. Không cần tự gõ `mvn compile test package verify`. Khi chạy `mvn clean verify`, Maven chạy pha `clean` của lifecycle riêng trước rồi chạy default lifecycle tới `verify`; cách này giảm nguy cơ dùng nhầm kết quả build cũ trong thư mục `target/`.

**Quan trọng:** pha `verify` không tự sinh ra integration test, code coverage gate hay vulnerability scanner. Maven chỉ thực thi các goal thực sự được bind vào các pha. `BUILD SUCCESS` cho biết các công việc **đã được cấu hình và thực thi** hoàn tất, không phải mọi tiêu chí chất lượng trên đời đều đã được kiểm tra.

## 2. So sánh `test`, `package`, `verify`, `install`, `deploy`

| Lệnh | Điểm dừng | Kết quả chính | Chưa thể kết luận |
| --- | --- | --- | --- |
| `mvn test` | `test` | Thực hiện các goal tới pha test, thường có unit test Surefire | Không bảo đảm JAR mới đã đóng gói |
| `mvn package` | `package` | Tạo artifact nếu goal đóng gói thành công | Chưa chạy các goal chỉ gắn ở integration-test/verify |
| `mvn verify` | `verify` | Kiểm chứng theo các goal đã cấu hình, sau package và integration-test | Không bảo đảm có test/integration/scan nếu chúng không được thiết lập |
| `mvn install` | `install` | Qua các bước trước đó rồi cài artifact vào local repository | Chưa chia sẻ lên remote repository |
| `mvn deploy` | `deploy` | Qua các pha trước rồi đẩy artifact tới remote repository | Không có nghĩa ứng dụng đã được triển khai hoặc khởi động |

Trong một dự án JAR mặc định, goal `surefire:test` thường được bind vào pha `test`, goal `jar:jar` vào `package`, còn `verify` **không tự có một goal đóng gói/kiểm thử chung**. Vì vậy, nếu chưa thêm plugin kiểm chứng, `mvn package` và `mvn verify` đôi khi cho kết quả gần giống nhau. Sự khác biệt xuất hiện rõ khi ta bind integration test, code-quality check hoặc một goal tùy biến vào các pha sau `package`.

Một artifact có thể đã xuất hiện trong `target/` rồi `verify` mới thất bại. **Sự tồn tại của file không phải bằng chứng đủ để xuất bản**. Điều kiện phát hành cần dựa vào trạng thái gate và artifact đúng từ lần build đã được chấp nhận.

## 3. Vì sao không chỉ gọi `integration-test`?

Maven hỗ trợ trình tự:

~~~text
pre-integration-test  →  integration-test  →  post-integration-test  →  verify
chuẩn bị môi trường       chạy test             dọn môi trường          xét kết quả
~~~

Ví dụ một dịch vụ có integration test với database:

1. Công cụ của dự án khởi tạo database/container tại `pre-integration-test`.
2. Test tương tác với database tại `integration-test`.
3. Công cụ dọn dữ liệu/container tại `post-integration-test`.
4. Plugin kiểm tra kết quả test tại `verify`.

**Maven không tự khởi động hoặc tắt database**: mỗi bước cần plugin/script/execution được cấu hình. Ý nghĩa của thứ tự pha là tạo chỗ cho quy trình đó.

Hai plugin phổ biến:

- **Maven Surefire Plugin**: thường chạy unit test tại `test`.
- **Maven Failsafe Plugin**: chuyên cho integration test, có goal `failsafe:integration-test` và `failsafe:verify`.

Failsafe ghi nhận lỗi integration test trong `integration-test` và đánh giá làm fail build ở `verify`, cho phép `post-integration-test` chạy trước khi Maven chấm kết quả cuối. Vì vậy, tài liệu Maven khuyến nghị gọi **`mvn verify`** thay vì dừng trực tiếp ở **`mvn integration-test`**, đặc biệt khi có tài nguyên test cần dọn dẹp.

`mvn verify` không thể bảo đảm mọi cleanup chạy trong trường hợp máy CI chết, tiến trình bị kill hoặc timeout cứng. Với hạ tầng thực tế, cần có cơ chế giải phóng tài nguyên trong pipeline ngoài các phase của Maven.

## 4. Dự án Java 17 để đối chiếu `package` và `verify`

Ta tạo một dự án Maven tên `verify-lab` có unit test và một kiểm tra JAR sau đóng gói. Kiểm tra này là **artifact smoke test** chạy qua Failsafe, nhằm làm rõ vòng đời. Nó không phải ví dụ về integration test với external database/API; trong hệ thống thật, các integration test cần bao phủ tương tác thực.

Cấu trúc:

~~~text
verify-lab/
├── pom.xml
└── src/
    ├── main/java/example/Calculator.java
    └── test/java/example/
        ├── CalculatorTest.java
        └── ArtifactIT.java
~~~

`pom.xml` đầy đủ:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>verify-lab</artifactId>
    <version>1.0-SNAPSHOT</version>
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
                <version>3.2.5</version>
            </plugin>
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
        </plugins>
    </build>
</project>
~~~

Các phiên bản trên là **phiên bản ví dụ được chọn rõ ràng**, không phải lời khẳng định đây là bản mới nhất. `maven.compiler.release=17` yêu cầu compiler tạo mã cho Java 17; cần cài JDK phù hợp. Hai goal của Failsafe có default phase lần lượt là `integration-test` và `verify`; khai báo execution như trên gắn chúng vào lifecycle.

`src/main/java/example/Calculator.java`:

~~~java
package example;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        System.out.println(add(2, 3));
    }
}
~~~

`src/test/java/example/CalculatorTest.java`:

~~~java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }
}
~~~

`src/test/java/example/ArtifactIT.java`:

~~~java
package example;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarFile;

import org.junit.jupiter.api.Test;

class ArtifactIT {
    @Test
    void packagedJarContainsCalculatorClass() throws Exception {
        Path artifact = Path.of("target", "verify-lab-1.0-SNAPSHOT.jar");
        assertTrue(Files.isRegularFile(artifact), "Missing packaged JAR");

        try (JarFile jar = new JarFile(artifact.toFile())) {
            assertNotNull(jar.getJarEntry("example/Calculator.class"));
        }
    }
}
~~~

`CalculatorTest` khớp pattern unit test của Surefire (tên kết thúc bằng `Test`). `ArtifactIT` khớp pattern integration test của Failsafe (tên kết thúc bằng `IT`). Đường dẫn JAR trong ví dụ đúng với `artifactId`, `version` và cấu hình đóng gói mặc định; nếu đổi `finalName` hoặc project name, phải đổi đường dẫn trong smoke test tương ứng.

## 5. Chạy `package`, rồi `verify`

Từ thư mục gốc `verify-lab`, chạy:

~~~bash
mvn -B -ntp clean package
~~~

Với project trên:

1. Maven biên dịch `Calculator.java` và mã test.
2. Surefire chạy `CalculatorTest` ở pha `test`.
3. Maven đóng JAR ở `target/verify-lab-1.0-SNAPSHOT.jar`.
4. Lệnh **dừng sau `package`**, do đó Failsafe chưa chạy `ArtifactIT`.

Tiếp tục:

~~~bash
mvn -B -ntp clean verify
~~~

Lần này Maven đi qua `package` đến `integration-test` và `verify`. Các mốc log tiêu biểu (trích đoạn minh họa, có thể khác giữa môi trường):

~~~text
[INFO] --- surefire:3.2.5:test (default-test) @ verify-lab ---
[INFO] Running example.CalculatorTest
[INFO] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
[INFO] --- jar:...:jar (default-jar) @ verify-lab ---
[INFO] --- failsafe:3.2.5:integration-test (default) @ verify-lab ---
[INFO] Running example.ArtifactIT
[INFO] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
[INFO] --- failsafe:3.2.5:verify (default) @ verify-lab ---
[INFO] BUILD SUCCESS
~~~

Phiên bản Maven JAR Plugin không được khóa trong POM, vì vậy dòng `jar:...:jar` cố ý lược bỏ version. Đây không phải toàn bộ stdout nguyên bản.

Để chạy riêng ứng dụng mẫu sau build:

~~~bash
java -cp target/classes example.Calculator
~~~

**Stdout chính xác của Java:**

~~~text
5
~~~

Maven `verify` **không tự chạy `main`** của `Calculator`. Để xem JAR có class không, dùng `jar tf target/verify-lab-1.0-SNAPSHOT.jar` của JDK; danh sách có entry `example/Calculator.class`.

## 6. Khi `package` SUCCESS nhưng `verify` FAILURE

Giữ nguyên mã nguồn và POM, thay đúng **một dòng trong `ArtifactIT.java`**:

~~~java
assertNotNull(jar.getJarEntry("example/Calculator.class"));
~~~

bằng:

~~~java
assertNotNull(jar.getJarEntry("example/Missing.class"));
~~~

Đây là dòng thay thế **bên trong method test**, không phải file Java độc lập. JAR của ví dụ không chứa `example/Missing.class`, do đó assertion fail.

Chạy lại lần lượt:

~~~bash
mvn -B -ntp clean package
mvn -B -ntp clean verify
~~~

Dự kiến `package` vẫn thành công: unit test và việc tạo JAR ổn. Nhưng `verify` chạy `ArtifactIT` qua Failsafe, phát hiện test fail và trả `BUILD FAILURE` ở bước `failsafe:verify`. Một trích đoạn log thường có dạng:

~~~text
[INFO] --- failsafe:3.2.5:integration-test (...) @ verify-lab ---
[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0
[INFO] --- failsafe:3.2.5:verify (...) @ verify-lab ---
[INFO] BUILD FAILURE
[ERROR] There are test failures.
~~~

Không coi dấu `[ERROR]` hay nội dung tóm tắt ở trên là stdout cố định của mọi phiên bản. Hãy đọc chi tiết test fail trong `target/failsafe-reports/`. Với unit test chạy qua Surefire, báo cáo thường ở `target/surefire-reports/`.

**Điểm học cốt lõi:** file JAR có thể đã được Maven tạo trước khi một điều kiện chất lượng phát hiện lỗi. Khi `verify` fail, pipeline phát hành phải chặn upload artifact cho tới khi nguyên nhân được xử lý. Sửa lại tên entry `example/Calculator.class` rồi chạy `clean verify` để xác nhận PASS.

## 7. Các nhóm kiểm chứng trước khi xuất bản

Mỗi nhóm dưới đây cần được cấu hình cụ thể. `verify` chỉ cung cấp một điểm trong lifecycle để hệ thống build tích hợp các phép kiểm tra.

| Nhóm | Câu hỏi cần trả lời | Cách kiểm tra điển hình |
| --- | --- | --- |
| Tính hợp lệ của cấu hình | POM, tọa độ, version, parent, plugin có hợp lệ? | POM validation, Enforcer, effective POM |
| Java/toolchain | Đang dùng đúng JDK, compiler release và Maven? | `mvn -version`, compiler, Enforcer rules |
| Biên dịch | Source/test source có biên dịch được? | Maven Compiler Plugin |
| Unit test | Quy tắc nghiệp vụ và trường hợp biên có đạt? | Surefire tại `test` |
| Đóng gói | JAR/WAR có đúng tên, class, resources và manifest? | Plugin đóng gói và smoke test artifact |
| Integration test | Các thành phần phối hợp qua DB/API/network có đạt? | Failsafe và môi trường test đã cấu hình |
| Code quality | Style, static analysis và coverage threshold có đạt? | Checkstyle, SpotBugs, JaCoCo với rule cụ thể |
| Dependency | Dependency resolve đúng, phiên bản/bản quyền/vulnerability có phù hợp policy? | Dependency tooling, license/security scanner |
| Sẵn sàng phát hành | Artifact được định danh, checksum/provenance và kênh phân phối đúng? | CI artifact checks, signing/staging nếu dự án yêu cầu |

Không được báo “đã chạy security scan” chỉ vì `mvn verify` SUCCESS nếu pipeline không cấu hình scanner. Tương tự, `BUILD SUCCESS` vẫn có thể xảy ra khi dự án không có test nào hoặc có cờ skip.

Với integration test cần hạ tầng (DB/container), đừng quên chi phí dọn môi trường, tài khoản dùng trong CI, thời gian chờ khởi động và phân biệt test môi trường với dữ liệu thật. Không dùng tài khoản production cho integration test trừ khi có quy trình được thiết kế và phê duyệt rõ ràng.

## 8. Đặt quy tắc kiểm chứng vào một pha rõ ràng

Maven không bắt buộc mọi kiểm chứng phải gắn đúng pha tên `verify`. Ví dụ **Enforcer Plugin** có goal `enforcer:enforce` thường gắn ở `validate`, để fail sớm nếu JDK không phù hợp. Đoạn dưới **chèn vào `<build><plugins>`** của POM, không phải XML độc lập:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.7.0</version>
    <executions>
        <execution>
            <id>require-jdk</id>
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
~~~

Quy tắc `[17,)` yêu cầu Java 17 trở lên. `enforcer:enforce` được bind vào pha `validate` theo default phase, nên các lệnh đến `verify` cũng chạy rule đó **trước khi biên dịch**. Việc này hữu ích hơn chờ đến cuối mới phát hiện sai JDK.

Nếu muốn thêm coverage gate, có thể cấu hình `jacoco:check` với ngưỡng cụ thể; muốn kiểm tra style, cấu hình plugin thích hợp và bind goal vào lifecycle. Chỉ đặt phiên bản plugin trong `<pluginManagement>` có thể chưa làm goal tự chạy; cần execution/binding phù hợp. Luôn xem log có goal thực thi và báo cáo thực tế trước khi coi một kiểm tra là bắt buộc.

## 9. Thiết kế pipeline: verify trước, phát hành sau

Một bước CI tối thiểu có thể chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Trong CI, điều kiện chuyển sang bước tiếp theo nên là **mã thoát thành công của tiến trình**, không phải tìm một dòng `BUILD SUCCESS` từ file log cũ. Khi bước verify thất bại, pipeline dừng trước publish/upload. Nếu dự án có nhiều module, xem **Reactor Summary** để kiểm tra các module thực sự đã chạy; `mvn -N verify` chỉ xử lý project gốc, không đi vào module con.

Khi đã đạt gate, `mvn deploy` là một cách Maven đưa artifact lên **remote Maven repository** nếu đã có `distributionManagement`, credential và quyền phù hợp. Tuy nhiên:

- `deploy` là pha sau `verify` trong cùng default lifecycle, do đó khi chạy `mvn deploy`, Maven cũng chạy lại các pha trước nó. Nếu trước đó đã chạy một job `verify`, các test có thể chạy **thêm một lần**.
- CI nên bảo đảm artifact đem upload có cùng source revision/cấu hình với artifact đã vượt kiểm chứng. Có thể dùng artifact bất biến, hash/checksum, provenance hoặc staging do hệ thống CI/repository cung cấp.
- Không đưa password hoặc token trực tiếp vào `pom.xml`, commit lịch sử Git hay log công khai. Dùng cơ chế lưu secret của CI và cấu hình Maven settings/credential đúng phạm vi.
- Maven `deploy` phát hành artifact, **không** tự triển khai ứng dụng tới Tomcat, Kubernetes hay production. Các bước triển khai runtime là workflow riêng.
- `mvn verify` không tự sinh Git tag, release notes, chữ ký số hoặc SBOM; nếu có yêu cầu, phải cấu hình các công cụ tương ứng.

Ví dụ tổ chức các gate trong CI: (1) checkout source revision; (2) thiết lập JDK/Maven; (3) chạy `clean verify`; (4) đánh giá report unit/integration/security; (5) kiểm tra artifact checksum và version; (6) cho phép upload lên repository dùng chung nếu tất cả gate bắt buộc PASS. Nên tránh sửa mã hoặc thay profile giữa bước kiểm chứng và bước phát hành.

## 10. Các trường hợp `verify` SUCCESS nhưng mức kiểm chứng chưa đủ

| Tình huống | Lý do | Cách xác nhận |
| --- | --- | --- |
| Không có integration test | Chưa khai báo Failsafe hoặc không có test khớp pattern | Tìm dòng `failsafe:integration-test`, test count và báo cáo |
| Test bị bỏ qua | Cờ `-DskipTests`, `-Dmaven.test.skip=true`, profile hoặc plugin config | Đọc đầy đủ lệnh, effective POM và test reports |
| Test không được tìm thấy | Surefire thường tìm tên `Test*`, `*Test`, `*Tests`, `*TestCase`; Failsafe tìm `IT*`, `*IT`, `*ITCase` | Đổi tên test hoặc cấu hình includes/excludes |
| Không có coverage threshold | Chưa gắn goal `check` có ngưỡng | Xem log/report của plugin coverage |
| Không có security/license scan | Maven core không tự chạy scanner | Kiểm tra job/plugin và báo cáo policy |
| Chỉ build một phần | Có `-N`, `-pl`, profile hoặc module selection | Xem Reactor Summary và danh sách module |
| Publish nhầm JAR cũ | File ngoài `target` hoặc từ build run khác được upload | Đối chiếu commit, version, timestamp, checksum |
| Integration test dùng mock thay tất cả dependency ngoài | Test chưa kiểm chứng tương tác thực | Bổ sung test theo hợp đồng hạ tầng hoặc hệ thống |
| Đổi settings/profile giữa build và publish | Kết quả phụ thuộc môi trường | Ghi nhận cấu hình và khóa điều kiện phát hành |

`-DskipTests` thường bỏ bước **thực thi** test của các plugin thông dụng, còn `-Dmaven.test.skip=true` có thể bỏ cả **biên dịch** test. Chi tiết phụ thuộc plugin/cấu hình, nên không dựa vào tên cờ đơn lẻ; phải xác nhận log và test count. Với release pipeline, cờ skip chỉ nên được cho phép theo chính sách đã định.

## 11. Đọc lỗi ở pha verify và báo cáo kiểm thử

Trong log, hãy đọc theo thứ tự: project/module nào thất bại → goal nào báo lỗi → thông điệp cụ thể đầu tiên → báo cáo/plugin tương ứng.

- **Compiler:** `cannot find symbol`, `release version 17 not supported`; kiểm tra tệp Java, dòng/cột, JDK và `maven.compiler.release`.
- **Surefire:** `Tests run`, `Failures`, `Errors`; xem `target/surefire-reports/`, test bị trượt và assertion/stack trace.
- **Failsafe:** `failsafe:verify` báo `There are test failures`; xem `target/failsafe-reports/`, tên `*IT` và sự cố môi trường.
- **Quality rule:** plugin đưa ra mức coverage/style/rule không đạt; tìm rule, ngưỡng, báo cáo liên quan.
- **Dependency resolution:** artifact, repository, mã HTTP, mirror, proxy; phân biệt sai tọa độ với mất quyền/kết nối.

Dùng `mvn -e verify` để xem stack trace khi thông báo lỗi Maven/plugin chưa rõ; dùng `mvn -X verify` khi cần phân tích thêm classpath, dependency resolution hoặc cấu hình. Log debug có thể chứa đường dẫn, repository nội bộ hoặc tham số nhạy cảm, phải rà soát và che thông tin trước khi chia sẻ.

Một lỗi test không được chữa bằng cách tắt test để làm `verify` xanh nếu đó là gate bắt buộc. Xử lý nguyên nhân, chạy lại cùng điều kiện và xác nhận report mới thay vì dùng artifact hoặc log cũ.

## 12. Bài tập tự kiểm tra

1. **`mvn package` tạo JAR nhưng `mvn verify` thất bại. Có nên phát hành JAR đó không?** Không; một gate sau đóng gói đã thất bại.
2. **`verify` có tự tạo integration test từ code ứng dụng không?** Không; cần test và plugin/execution phù hợp.
3. **Vì sao gọi `mvn verify` thay vì `mvn integration-test` trực tiếp?** Để có cơ hội chạy `post-integration-test` và kiểm tra kết quả ở `verify`.
4. **`mvn verify` đã cài artifact vào local Maven repository chưa?** Không theo mặc định; việc đó thuộc pha `install`.
5. **`mvn deploy` có khởi động production app không?** Không; Maven deploy đưa artifact lên remote repository.
6. **Unit test PASS, ArtifactIT FAIL. Với POM ví dụ, lệnh nào thường bị chặn?** `verify`, do Failsafe kiểm tra thất bại.
7. **`verify` SUCCESS nhưng mọi test đều bị skip. Có đạt tiêu chí đã test đủ không?** Không; phải đánh giá số lượng test thực chạy và policy.
8. **`mvn -N verify` tại root aggregator có build mọi module không?** Không, vì `-N` tắt recursion.
9. **`verify` có tự kiểm tra CVE/license không?** Không nếu chưa cấu hình công cụ.
10. **Sau build thành công nên đối chiếu những gì trước publish?** Commit/source revision, profile/JDK, test report, artifact version, nội dung và checksum theo policy.

## 13. Checklist kiểm chứng trước khi xuất bản

- [ ] Xác nhận commit/tag, Maven/JDK và profile dành cho phát hành.
- [ ] Chạy `mvn -B -ntp clean verify` thành công trên đúng tập module.
- [ ] Kiểm tra Surefire/Failsafe có chạy đúng test và số lượng; không có skip ngoài ý muốn.
- [ ] Kiểm tra những gate coverage, style, license và security đã được cấu hình trong quy trình.
- [ ] Kiểm tra artifact thực sự mới: GAV/version, JAR/WAR, resource và manifest.
- [ ] Gắn artifact với source/build đã vượt gate bằng định danh hoặc checksum.
- [ ] Bảo vệ credential và không đưa log có secret lên nơi công khai.
- [ ] Chỉ cho phép `install`/`deploy` hoặc upload riêng sau khi mọi gate bắt buộc đạt.
- [ ] Xác nhận artifact đã xuất bản có đúng tọa độ/nội dung tại repository đích.

## Nguồn tham khảo chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): thứ tự pha và ý nghĩa `verify`, `install`, `deploy`.
- [Apache Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/): hai goal `integration-test`, `verify` và cơ chế xử lý test.
- [Maven Surefire Plugin — Test Inclusion/Exclusion](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html): cách Surefire tìm unit test.
- [Maven Failsafe Plugin — Test Inclusion/Exclusion](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html): quy tắc tên integration test.
- [Maven Enforcer Plugin — Usage](https://maven.apache.org/components/enforcer/maven-enforcer-plugin/usage.html): cách khai báo điều kiện và goal `enforcer:enforce`.

Khi chuẩn bị phát hành, nhớ phân biệt: **`package` tạo sản phẩm; `verify` kiểm chứng theo các gate đã cấu hình; `install` đưa vào kho cục bộ; `deploy` đưa lên kho Maven từ xa**. Một pipeline đáng tin cần bảo đảm chính artifact được xuất bản đã vượt qua các phép kiểm chứng bắt buộc.
