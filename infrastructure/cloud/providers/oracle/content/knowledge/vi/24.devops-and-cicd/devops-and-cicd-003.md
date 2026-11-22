# Build, kiểm tra và đóng gói ứng dụng Java

## Mục tiêu bài học

Trong chương **DevOps và CI/CD trên OCI** của module **CLOUD_PROVIDERS_ORACLE**, bài này xây dựng quy trình biến mã nguồn Java thành gói ứng dụng đã được kiểm tra, có thể nhận diện và chuyển sang bước triển khai.

Quy trình được đặt trong bối cảnh một tenancy OCI có compartment, IAM và mạng truy cập phù hợp. Ứng dụng sau này có thể chạy trên Compute, Kubernetes hoặc sử dụng lưu trữ và cơ sở dữ liệu Oracle; riêng bước build cần tập trung tạo artifact đúng, kiểm tra được và không mang theo bí mật của môi trường chạy.

Sau bài học, bạn có thể:

- Phân biệt biên dịch, unit test, kiểm tra tích hợp, đóng gói và phát hành artifact.
- Thiết lập dự án Java 17/Maven với lệnh kiểm tra nhất quán giữa máy cá nhân và OCI.
- Viết unit test và kiểm tra chạy chính file JAR được tạo ra.
- Khai báo `build_spec.yaml` cho OCI DevOps Managed Build.
- Tạo JAR, báo cáo test, checksum và thông tin truy vết.
- Nhận biết lỗi toolchain, đường dẫn artifact, quyền IAM và kết nối dependency.

Ví dụ sử dụng một ứng dụng dòng lệnh nhỏ, không có dependency khi chạy và không cần khởi tạo Compute hay cơ sở dữ liệu. Mọi file mã nguồn bên dưới là nội dung mẫu để người học tạo trong repository ứng dụng của mình.

## 1. Từ commit đến artifact đủ điều kiện triển khai

Một pipeline build tốt phải trả lời được bốn câu hỏi:

1. Mã nào đã được build?
2. Dùng JDK, công cụ và dependency nào?
3. Những kiểm tra nào thực sự đã chạy và kết quả ra sao?
4. File nào sẽ được chuyển sang triển khai?

~~~mermaid
flowchart LR
    A["Commit trong Git"] --> B["OCI Managed Build lấy mã"]
    B --> C["Kiểm tra JDK và Maven"]
    C --> D["Biên dịch và unit test"]
    D --> E["Đóng gói JAR"]
    E --> F["Chạy kiểm tra trên JAR"]
    F --> G["Chuẩn bị artifact, báo cáo, checksum"]
    G --> H["Deliver Artifacts"]
    H --> I["Kho artifact để triển khai"]
    D --> J["Thất bại: không chuyển gói sang triển khai"]
    F --> J
~~~

Đóng gói và kiểm tra không luôn đứng theo thứ tự “chạy hết test rồi mới có file”. Unit test thường chạy trước khi đóng gói, còn kiểm tra khởi động hoặc tích hợp có thể cần chính file đã đóng gói. Điều cần bảo đảm là **chỉ chuyển artifact sang bước phát hành khi tất cả kiểm tra bắt buộc đã đạt**.

| Hoạt động | Đầu vào | Kết quả | Chưa chứng minh được |
| --- | --- | --- | --- |
| Biên dịch | Mã Java và compile dependencies | Bytecode | Logic đúng hoặc app khởi động được |
| Unit test | Các đơn vị mã và test dependencies | Kết quả kiểm tra logic nhỏ | IAM hay kết nối Database trên OCI |
| Đóng gói | Bytecode, tài nguyên và cấu hình đóng gói | JAR/WAR hoặc định dạng khác | File có đầy đủ thành phần để chạy |
| Kiểm tra trên gói | File vừa đóng gói | Bằng chứng chạy gói đó | Tính sẵn sàng của workload production |
| Phát hành artifact | Gói đã đạt kiểm tra | Phiên bản lưu trong kho | Workload đã được triển khai |
| Triển khai | Artifact và cấu hình môi trường | Phiên bản ứng dụng đang chạy | Mọi yêu cầu nghiệp vụ đều đạt |

Không dùng việc pipeline “xanh” để thay cho việc kiểm tra loại test, số test và artifact thực tế được tạo.

## 2. Chọn toolchain và vòng đời build

### 2.1. Đồng bộ JDK khi build và runtime khi chạy

Ví dụ chọn:

| Thành phần | Lựa chọn minh họa |
| --- | --- |
| Ngôn ngữ và bytecode | Java 17 |
| JDK chạy Maven | JDK 17 |
| Công cụ build | Maven 3.9.x |
| Test framework | JUnit Jupiter 5.13.1 |
| Unit test runner | Maven Surefire 3.5.3 |
| Integration test runner | Maven Failsafe 3.5.3 |
| Gói đầu ra | Executable JAR, không có runtime dependency bên ngoài |

Đây là bộ phiên bản cụ thể cho ví dụ, không phải danh sách phiên bản mới nhất. Dự án thật cần cập nhật theo quy trình quản lý dependency của nhóm.

OCI cung cấp môi trường Managed Build có sẵn JDK và công cụ build; các phiên bản có thể thay đổi. Luôn xem [Build Runner Runtime Details](https://docs.oracle.com/en-us/iaas/Content/devops/using/runtime_details.htm) và ghi kết quả `java -version`, `javac -version`, `mvn -version` vào log.

Chọn build runner **Oracle Linux 8** cho bài này. Oracle đã thông báo kết thúc hỗ trợ build runner Oracle Linux 7; không sao chép cấu hình OL7 từ ví dụ cũ. Xem [Service Change Announcements](https://docs.oracle.com/en-us/iaas/Content/servicechanges.htm).

`JAVA_HOME` ảnh hưởng JDK mà Maven sử dụng; lệnh `java` trên `PATH` có thể trỏ sang nơi khác. Đọc `mvn -version` để biết JDK thật của Maven, không chỉ nhìn JDK mà IDE đang chọn.

Thuộc tính `maven.compiler.release=17` yêu cầu biên dịch theo mức Java 17. Nó không tự cài JDK, cũng không làm JDK 11 biên dịch được mã yêu cầu Java 17. Gói tạo cho Java 17 cần runtime tương thích; JRE 11 có thể báo `UnsupportedClassVersionError`.

### 2.2. Các phase Maven quan trọng

| Lệnh/phase | Phạm vi |
| --- | --- |
| `mvn compile` | Biên dịch mã chính |
| `mvn test` | Chạy tới phase unit test |
| `mvn package` | Chạy các phase trước và đóng gói |
| `mvn verify` | Chạy tới các kiểm tra ở phase verify, bao gồm integration test khi đã cấu hình |
| `mvn install` | Đưa artifact vào Maven repository cục bộ |
| `mvn deploy` | Phát hành artifact tới remote Maven repository đã cấu hình |
| `mvn clean verify` | Xóa sản phẩm build cũ rồi chạy tới verify |

`mvn deploy` không có nghĩa triển khai ứng dụng lên OCI Compute hay Kubernetes. Ngoài ra, gọi `verify` không tự sinh integration test nếu chưa cấu hình plugin và test tương ứng. Xem [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle).

Lệnh chính cho bài:

~~~bash
mvn --batch-mode --no-transfer-progress clean verify
~~~

Không cần gọi lần lượt `compile`, `test`, `package` rồi `verify` vì phase sau đã bao gồm phase trước. Chạy lặp nhiều lần vừa tốn thời gian vừa dễ làm người đọc log nhầm lần kiểm tra nào thuộc artifact nào.

## 3. Repository ứng dụng mẫu

Bố cục dự án:

~~~text
oci-java-demo/
├── pom.xml
├── build_spec.yaml
├── .gitignore
└── src/
    ├── main/
    │   └── java/
    │       └── vn/example/ocijava/
    │           ├── GreetingService.java
    │           └── Main.java
    └── test/
        └── java/
            └── vn/example/ocijava/
                ├── GreetingServiceTest.java
                └── PackagedAppIT.java
~~~

`target/` là thư mục Maven tạo; `dist/` sẽ chứa bộ file xuất từ pipeline. Không commit hai thư mục này.

`.gitignore`:

~~~gitignore
target/
dist/
.idea/
*.iml
.env
.env.*
*.pem
*.key
settings-private.xml
~~~

Dependency, plugin và test được khai báo trong POM. Credential truy cập repository riêng không được nhúng vào POM hoặc commit cùng mã.

### 3.1. Mã ứng dụng

`src/main/java/vn/example/ocijava/GreetingService.java`:

~~~java
package vn.example.ocijava;

public final class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }
}
~~~

`src/main/java/vn/example/ocijava/Main.java`:

~~~java
package vn.example.ocijava;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "OCI" : args[0];
        System.out.println(new GreetingService().greet(name));
    }
}
~~~

Không thêm kết nối OCI vào ví dụ chỉ để chứng minh build. Một unit test kiểm tra tạo lời chào không cần quyền đọc Object Storage, không cần VCN và không cần mật khẩu cơ sở dữ liệu.

### 3.2. POM có phiên bản plugin và test rõ ràng

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>oci-java-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.13.1</junit.version>
        <test.plugins.version>3.5.3</test.plugins.version>
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
        <finalName>oci-java-demo</finalName>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <id>check-toolchain</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireJavaVersion>
                                    <version>[17,18)</version>
                                </requireJavaVersion>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${test.plugins.version}</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.ocijava.Main</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>${test.plugins.version}</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <app.jar>${project.build.directory}/${project.build.finalName}.jar</app.jar>
                    </systemPropertyVariables>
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
        </plugins>
    </build>
</project>
~~~

Các điểm cần hiểu:

- Enforcer chặn sai JDK hoặc Maven ngay tại phase `validate`. Dải `[17,18)` chỉ nhận JDK 17 trong ví dụ này; nếu dự án chuyển JDK, phải thay yêu cầu có chủ đích.
- JUnit có scope `test` nên không trở thành runtime dependency của ứng dụng.
- Surefire chạy unit test. Failsafe được gắn vào `integration-test` và `verify` để chạy test sau khi có JAR và quyết định kết quả build.
- `failIfNoTests=true` giúp tránh trạng thái thành công do không tìm thấy test trong nhóm kiểm tra bắt buộc.
- `finalName` cố định đường dẫn file thành `target/oci-java-demo.jar`; nó không thay đổi tọa độ Maven `vn.example:oci-java-demo:1.0.0`.
- Manifest khai báo `Main-Class` để dùng `java -jar`.

Cách cấu hình JUnit với Surefire/Failsafe được mô tả tại [JUnit 5 User Guide](https://docs.junit.org/5.13.1/user-guide/index.html). Ràng buộc phiên bản công cụ dựa trên [Enforcer Version Ranges](https://maven.apache.org/enforcer/enforcer-rules/versionRanges.html), còn entry point của JAR theo [Maven Archiver: Make The Jar Executable](https://maven.apache.org/components/shared/maven-archiver/examples/classpath.html).

Gói này chạy độc lập vì mã chính chỉ dùng Java SE. Thêm `Main-Class` không tự đóng gói các thư viện bên ngoài vào JAR. Nếu sau này thêm JDBC driver, HTTP client hoặc framework, phải chọn chiến lược phân phối dependency thích hợp.

## 4. Viết test cho logic và cho gói đã đóng

### 4.1. Unit test không phụ thuộc hạ tầng OCI

`src/test/java/vn/example/ocijava/GreetingServiceTest.java`:

~~~java
package vn.example.ocijava;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void stripsWhitespaceFromName() {
        assertEquals("Hello, OCI!", service.greet("  OCI  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class, () -> service.greet(" "));
    }
}
~~~

Hai test kiểm tra hành vi cụ thể: chuẩn hóa tên và từ chối đầu vào rỗng. Chúng không kiểm tra rằng pipeline đọc được credential, cũng không cần gọi API OCI.

Tên lớp kết thúc bằng `Test` để Surefire phát hiện theo quy ước. Khi có nhiều module, xác định nhóm nào bắt buộc có test; không áp dụng quy tắc “không có test thì lỗi” một cách máy móc cho module chỉ chứa tài liệu hoặc tài nguyên.

### 4.2. Kiểm tra chạy chính file JAR

`src/test/java/vn/example/ocijava/PackagedAppIT.java`:

~~~java
package vn.example.ocijava;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PackagedAppIT {
    @Test
    void startsPackagedApplication() throws Exception {
        Path jar = Path.of(System.getProperty("app.jar"));
        assertTrue(Files.isRegularFile(jar), "Packaged JAR must exist");

        boolean windows = System.getProperty("os.name")
                .toLowerCase(java.util.Locale.ROOT)
                .contains("win");
        String executable = windows ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"), "bin", executable);

        Process process = new ProcessBuilder(
                java.toString(), "-jar", jar.toString(), "OCI")
                .redirectErrorStream(true)
                .start();

        try {
            assertTrue(process.waitFor(10, TimeUnit.SECONDS),
                    "Application did not exit in time");

            String output = new String(
                    process.getInputStream().readAllBytes(),
                    StandardCharsets.UTF_8).strip();

            assertEquals(0, process.exitValue(), output);
            assertEquals("Hello, OCI!", output);
        } finally {
            process.destroyForcibly();
        }
    }
}
~~~

Test này có thể phát hiện JAR không tồn tại, thiếu entry point, lỗi khởi động hoặc output sai. `ProcessBuilder` nhận từng đối số riêng nên không phụ thuộc cách shell xử lý dấu cách trong đường dẫn.

Tên `PackagedAppIT` khớp quy ước `*IT` của Failsafe. Nguồn về quy ước đặt tên: [Failsafe Test Inclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html).

Ứng dụng mẫu chỉ in một dòng nên cách chờ process rồi đọc output phù hợp với ví dụ. Với dịch vụ sinh nhiều log hoặc chạy liên tục, cần đọc output đồng thời, kiểm tra readiness và chủ động dừng tiến trình; không sao chép nguyên test dòng lệnh này làm test cho web server.

Đây là kiểm tra gói ứng dụng trong một tiến trình riêng, chưa phải kiểm tra tích hợp với Oracle Database, Object Storage hoặc dịch vụ OCI khác. Khi bổ sung các test đó, cần tài nguyên test riêng, timeout, quyền IAM và cơ chế dọn tài nguyên.

### 4.3. Chạy và đọc kết quả

Từ thư mục chứa POM:

~~~bash
java -version
javac -version
mvn -version
mvn --batch-mode --no-transfer-progress clean verify
java -jar target/oci-java-demo.jar OCI
~~~

Kết quả chạy ứng dụng dự kiến:

~~~text
Hello, OCI!
~~~

Với đúng mã mẫu, mong đợi hai unit test và một test của gói được thực thi, không bị skip. Báo cáo nằm tại:

~~~text
target/
├── oci-java-demo.jar
├── surefire-reports/
└── failsafe-reports/
~~~

Không chỉ tìm dòng `BUILD SUCCESS`. Kiểm tra số test, lỗi, thất bại và skip trong hai nhóm báo cáo. Failsafe quyết định kết quả tại `verify`; vì vậy dùng `mvn verify` thay vì dừng ở `mvn integration-test`. Xem [Failsafe verify goal](https://maven.apache.org/components/surefire/maven-failsafe-plugin/verify-mojo.html).

Các tùy chọn như `-DskipTests`, `-Dmaven.test.skip=true` hoặc `-DskipITs` có thể bỏ qua những lớp kiểm tra khác nhau. Chúng không thuộc lệnh phát hành của bài. Không thêm tùy chọn skip chỉ để làm pipeline đạt.

## 5. Chọn loại gói phù hợp

| Loại gói | Phù hợp khi | Điều cần kiểm tra |
| --- | --- | --- |
| JAR thường có entry point | Ứng dụng nhỏ, hoặc dependency được phân phối riêng | `Main-Class` và classpath |
| Fat/uber JAR | Muốn mang theo runtime dependencies | Trùng resource, service loader, license và cách merge |
| Executable JAR của framework | Framework có cơ chế đóng gói riêng | Plugin repackage/boot task và đúng file cần chạy |
| WAR | Triển khai lên application server phù hợp | Java/Jakarta API và phiên bản server |
| Container image | Phân phối cả ứng dụng cùng môi trường runtime | Base image, JRE, kiến trúc, user và image digest |
| Native executable | Có yêu cầu khởi động/tài nguyên phù hợp | Toolchain native, thư viện động và nền tảng đích |

Đổi đuôi file thành `.jar` không tạo ra Java archive hợp lệ. Đặt JAR vào image cũng không tự biến JAR thiếu dependency thành gói chạy được.

Đối với ứng dụng dùng framework, không dùng lệnh sao chép `target/*.jar` một cách tùy ý: thư mục có thể chứa cả JAR thường, executable JAR, sources JAR hoặc bản `original`. Xác định chính xác sản phẩm được plugin tạo và kiểm tra đúng file đó.

Ví dụ hiện tại chỉ phát hành `target/oci-java-demo.jar`. JUnit là test dependency nên không cần mang vào artifact chạy.

## 6. Build specification cho OCI DevOps

### 6.1. Vai trò của build spec

`build_spec.yaml` mô tả lệnh chạy trên build runner; POM mô tả cách build dự án Java. Giữ logic Java trong POM giúp máy cá nhân và CI dùng cùng một lệnh.

File build spec dưới đây đặt ở gốc primary source. Nó gồm ba bước: ghi nhận toolchain, chạy `clean verify` và chuẩn bị bộ artifact. `outputArtifacts` khai báo bốn file cụ thể cho các stage sau.

~~~yaml
version: 0.1
component: build
timeoutInSeconds: 1800
shell: bash
failImmediatelyOnError: true

steps:
  - type: Command
    name: Inspect toolchain
    timeoutInSeconds: 120
    command: |
      set -euo pipefail
      cd "${OCI_PRIMARY_SOURCE_DIR}"
      test -f pom.xml
      java -version
      javac -version
      mvn -version

  - type: Command
    name: Compile test package and verify
    timeoutInSeconds: 1200
    command: |
      set -euo pipefail
      cd "${OCI_PRIMARY_SOURCE_DIR}"
      mvn --batch-mode --no-transfer-progress clean verify
    onFailure:
      - type: Command
        timeoutInSeconds: 60
        command: |
          cd "${OCI_PRIMARY_SOURCE_DIR}"
          printf '%s\n' 'Maven failed; inspect test output and available reports.'
          find target/surefire-reports target/failsafe-reports             -maxdepth 1 -type f -name '*.txt' -print 2>/dev/null || true

  - type: Command
    name: Prepare verified artifacts
    timeoutInSeconds: 180
    command: |
      set -euo pipefail
      cd "${OCI_PRIMARY_SOURCE_DIR}"
      test -s target/oci-java-demo.jar
      : "${OCI_PRIMARY_SOURCE_COMMIT_HASH:?Missing primary source commit}"
      : "${OCI_BUILD_RUN_ID:?Missing build run identifier}"
      mkdir -p dist
      cp target/oci-java-demo.jar dist/app.jar
      tar -czf dist/test-reports.tar.gz         -C target surefire-reports failsafe-reports
      (
        cd dist
        sha256sum app.jar > app.jar.sha256
      )
      printf 'sourceCommit=%s\nbuildRunId=%s\njavaRelease=17\napplicationVersion=1.0.0\n'         "${OCI_PRIMARY_SOURCE_COMMIT_HASH}"         "${OCI_BUILD_RUN_ID}" > dist/build-metadata.properties

outputArtifacts:
  - name: java-app
    type: BINARY
    location: dist/app.jar

  - name: java-app-checksum
    type: BINARY
    location: dist/app.jar.sha256

  - name: java-test-reports
    type: BINARY
    location: dist/test-reports.tar.gz

  - name: java-build-metadata
    type: BINARY
    location: dist/build-metadata.properties
~~~

Cú pháp, biến dựng sẵn và cách khai báo đầu ra theo [OCI DevOps Build Specification](https://docs.oracle.com/en-us/iaas/Content/devops/using/build_specs.htm). Các tên bước và lệnh Maven trong ví dụ là thiết kế của bài.

### 6.2. Những chi tiết bảo đảm kết quả có ý nghĩa

- `set -euo pipefail` làm Bash dừng khi lệnh lỗi, dùng biến chưa đặt hoặc một thành phần của pipeline shell thất bại.
- Mỗi bước chủ động `cd` vào `OCI_PRIMARY_SOURCE_DIR`, không dựa vào thư mục làm việc còn lại từ bước trước.
- `clean verify` phải thành công trước khi sao chép JAR sang `dist`.
- `test -s` kiểm tra file cần xuất tồn tại và không rỗng.
- `java-app` là tên logic để stage sau tham chiếu; `dist/app.jar` là đường dẫn file cục bộ.
- SHA-256 được tính trên chính bản JAR sẽ phát hành.
- Metadata dùng commit của **primary source**, không lấy nhầm commit của repository chỉ kích hoạt trigger.
- Báo cáo test được đóng thành một file để xuất rõ ràng.

`|| true` chỉ xuất hiện trong lệnh liệt kê báo cáo lúc xử lý lỗi, để thiếu thư mục báo cáo không gây nhiễu chẩn đoán. Không đặt nó sau lệnh Maven hoặc lệnh phát hành.

Đổi tên `oci-java-demo.jar` thành `app.jar` chỉ là sao chép byte; không build lại. Không dùng việc sửa tên file làm cơ chế quản lý phiên bản.

Bốn file trong `dist`:

~~~text
dist/
├── app.jar
├── app.jar.sha256
├── test-reports.tar.gz
└── build-metadata.properties
~~~

Nếu Maven thất bại, bước chuẩn bị artifact không chạy. Đừng kỳ vọng gói báo cáo của luồng thành công sẽ tự xuất hiện ở build lỗi; cần xem log Maven và thiết kế riêng việc giữ báo cáo lỗi nếu nhóm có yêu cầu.

### 6.3. File build spec không thuộc gốc repository

Nếu ứng dụng nằm trong `services/greeting`, phải đồng bộ ba nơi:

| Nơi cấu hình | Ví dụ cần chỉnh |
| --- | --- |
| Đường dẫn build spec trong Managed Build | `services/greeting/build_spec.yaml` |
| Thư mục chạy lệnh | `cd "${OCI_PRIMARY_SOURCE_DIR}/services/greeting"` |
| Đường dẫn output tính từ primary source | `services/greeting/dist/app.jar` |

Đổi vị trí build spec không tự làm mọi đường dẫn trong file trở thành tương đối với vị trí mới. Với nhiều build source, xác định nguồn nào là primary; không chọn thư mục chỉ bằng phỏng đoán tên repository.

## 7. Đưa dự án lên OCI Managed Build

### 7.1. Chuẩn bị project, source và log

Chuẩn bị trong region và compartment lab:

1. Một OCI DevOps project có cấu hình log build để theo dõi quá trình chạy.
2. Repository chứa POM, mã Java, test và `build_spec.yaml`.
3. Build pipeline với Managed Build stage.
4. Quyền cho người vận hành và danh tính pipeline.
5. Kết nối mạng tới nơi tải dependency/plugin.
6. Kho Artifact Registry nếu cần lưu gói sau build.

Có thể dùng OCI Code Repository hoặc nguồn Git được dịch vụ hỗ trợ. Nếu dùng repository ngoài OCI, cấu hình external connection và credential tương ứng; không thay external connection của OCI DevOps bằng configuration source provider của Resource Manager. Đây là hai tích hợp thuộc hai dịch vụ khác nhau.

Trong Managed Build stage, chọn build source và primary source, đường dẫn build spec, image Oracle Linux 8 và cấu hình tài nguyên runner phù hợp. Với bố cục mẫu, POM và build spec đều ở gốc primary source. Thao tác thêm stage được mô tả tại [Adding a Managed Build Stage](https://docs.oracle.com/en-us/iaas/Content/devops/using/add_buildstage.htm).

Lần đầu nên chạy thủ công với branch/commit đã xác định để kiểm tra cấu hình. Trigger tự động là cấu hình riêng; việc đã tạo pipeline không có nghĩa mọi commit sẽ tự chạy build. Chỉ bật trigger sau khi luồng thủ công hoạt động đúng.

### 7.2. Tách quyền của người và quyền của pipeline

| Danh tính | Quyền phục vụ công việc |
| --- | --- |
| Người cấu hình DevOps | Thao tác project, pipeline, stage, source connection trong phạm vi được giao |
| Build pipeline qua resource principal | Đọc OCI repository hoặc nguồn cần thiết, truy cập dịch vụ OCI trong các bước build |
| Pipeline phát hành artifact | Ghi đúng kho artifact đích |
| Pipeline cần bí mật | Đọc đúng secret trong Vault theo chính sách |
| Ứng dụng sau triển khai | Quyền runtime riêng tới Object Storage, Database hoặc dịch vụ khác |

Quyền của tài khoản đăng nhập Console không tự được truyền nguyên vẹn cho build runner. OCI mô tả việc dùng dynamic group và IAM policy cho pipeline trong [DevOps Policies](https://docs.oracle.com/en-us/iaas/Content/devops/using/devops_iampolicies.htm). Giới hạn phạm vi theo compartment và tài nguyên, tránh cấp toàn tenancy chỉ để thử build.

Ứng dụng mẫu không gọi dịch vụ OCI, vì vậy bước biên dịch/test không cần quyền quản lý Compute, VCN hoặc Database. Nếu pipeline phát hành gói, nó mới cần quyền thích hợp tại kho đích.

Không đưa OCI API signing key vào image hoặc POM để chạy CLI trong build. Khi bước build cần gọi dịch vụ OCI, dùng danh tính dịch vụ đã được cấp quyền và xác nhận phạm vi của nó.

### 7.3. Mạng tải dependency là một điều kiện của build

Maven phải truy cập được repository chứa cả dependency ứng dụng lẫn Maven plugin. Có thể cần:

- DNS phân giải được hostname repository.
- Route và egress phù hợp với cấu hình runner.
- Proxy/mirror doanh nghiệp và TLS trust hợp lệ.
- Credential cho private dependency repository.
- Đường truy cập riêng nếu integration test gọi dịch vụ trong VCN.

Service Gateway phục vụ các dịch vụ OCI được hỗ trợ; nó không tự cung cấp truy cập mọi Maven repository trên Internet. Nếu dùng runner với truy cập mạng riêng, thiết kế egress hoặc mirror theo mô hình mạng cụ thể.

Lỗi tải plugin xảy ra trước khi Java được biên dịch cũng có thể do DNS, proxy, certificate hoặc xác thực. Đừng sửa POM ngẫu nhiên khi log đang cho thấy lỗi kết nối.

Credential repository riêng nên lấy từ cơ chế quản lý bí mật, rồi cấp cho Maven qua cấu hình được bảo vệ. Không in toàn bộ `settings.xml` hoặc biến môi trường vào log. Khi có integration test dùng Oracle Database, không dùng credential production cho build pull request.

## 8. Từ output của build tới artifact lưu bền vững

### 8.1. Output artifact chưa phải kho phát hành

`outputArtifacts` giúp chuyển kết quả sang stage tiếp theo trong build run. Để lưu và sử dụng sau build, thêm **Deliver Artifacts** với kho đích phù hợp:

| Sản phẩm | Kho đích |
| --- | --- |
| JAR, ZIP, báo cáo hoặc metadata dạng file | OCI Artifact Registry, generic artifact |
| Container image | OCI Container Registry |
| Maven module để dự án khác resolve bằng tọa độ | Remote repository tương thích Maven đã được cấu hình |

Đừng mặc định một kho generic artifact chính là endpoint Maven cho `mvn deploy`. Việc tải lên một file JAR và việc cung cấp cấu trúc repository Maven là hai yêu cầu khác nhau.

Với ví dụ này, tạo tham chiếu DevOps artifact tới vị trí trong Artifact Registry rồi thêm Deliver Artifacts sau Managed Build. Giá trị **Build config/result Artifact name** phải khớp tên `java-app` trong build spec; không nhập `dist/app.jar` vào trường tên logic đó.

Nếu muốn giữ checksum, báo cáo và metadata cùng phiên bản, cấu hình ánh xạ riêng cho `java-app-checksum`, `java-test-reports` và `java-build-metadata`. Luồng tạo và ánh xạ được mô tả tại [Adding a Deliver Artifacts Stage](https://docs.oracle.com/en-us/iaas/Content/devops/using/add_deliverartifact.htm).

### 8.2. Phiên bản và danh tính artifact

Có ba giá trị cần tách biệt:

| Giá trị | Ví dụ | Công dụng |
| --- | --- | --- |
| Phiên bản trong POM | `1.0.0` | Phiên bản ứng dụng/Maven |
| Phiên bản lưu trong kho | `1.0.0-gabc123def456-b42` | Nhận diện một lần phát hành |
| SHA-256 của file | Chuỗi hex của JAR | Đối chiếu byte thực tế |

Trong ví dụ phiên bản kho, `g...` đại diện commit rút gọn, `b42` là mã build do nhóm quy định; chúng không phải biến dựng sẵn có thể chép nguyên vào Console.

Nhóm cần quy tắc sinh phiên bản không trùng và cơ chế thay tham số khi tự động phát hành. OCI cho phép cấu hình phiên bản artifact bằng pipeline parameter hoặc exported variable; việc đó phải được khai báo và ánh xạ riêng. Xem [Configuring Delivered Artifact Version](https://docs.oracle.com/en-us/iaas/Content/devops/using/deliverartifact-stage.htm).

Build spec của bài cố ý giữ đường dẫn file ổn định; **nó chưa tự sinh phiên bản kho phát hành**. Khi chạy lab, chọn phiên bản kho riêng cho từng lần Deliver và lưu liên hệ với build run. Không dùng một nhãn `latest` làm bằng chứng duy nhất cho gói triển khai.

### 8.3. Kiểm tra tính toàn vẹn sau khi nhận gói

Sau khi tải về JAR và checksum từ cùng phiên bản kho, trên Linux có thể kiểm tra:

~~~bash
sha256sum --check app.jar.sha256
java -jar app.jar OCI
~~~

File checksum được tạo tương đối với tên `app.jar`, nên chạy lệnh trong thư mục chứa hai file đó.

Checksum giúp phát hiện khác biệt byte khi truyền hoặc chọn nhầm gói; nó không tự chứng minh người phát hành đáng tin cậy. Nếu cần xác thực nguồn gốc, bổ sung ký artifact và kiểm soát nơi lưu chữ ký/metadata theo chính sách của nhóm.

Giữ nguyên artifact đã kiểm tra khi chuyển từ dev sang test và production. Thay cấu hình runtime phù hợp từng môi trường thay vì build lại cùng commit cho mỗi môi trường rồi coi các gói là một.

## 9. Kiểm soát chất lượng, thời gian và chi phí

### 9.1. Những cổng kiểm tra nên bổ sung theo nhu cầu

| Kiểm tra | Phát hiện được gì? | Giới hạn |
| --- | --- | --- |
| Unit test | Sai logic trong phạm vi nhỏ | Có thể bỏ sót tương tác với dịch vụ ngoài |
| Test chạy JAR | Sai entry point, thiếu thành phần khi khởi động | Không kiểm tra toàn bộ nghiệp vụ |
| Integration test với hệ thống ngoài | Sai truy vấn, protocol, cấu hình kết nối | Cần môi trường test và dọn tài nguyên |
| Phân tích tĩnh/format | Vi phạm quy tắc mã và một số lỗi phổ biến | Không thay kiểm tra hành vi |
| Coverage gate | Phần mã được test đi qua | Coverage cao không bảo đảm assertion tốt |
| Dependency/vulnerability scan | Dependency có vấn đề đã được nhận diện | Cần cơ sở dữ liệu và quy tắc xử lý phù hợp |
| SBOM và metadata | Thành phần và nguồn gốc gói | Không tự ngăn thực thi gói có lỗi |

Các cổng bổ sung phải được cấu hình thành kiểm tra có điều kiện thất bại rõ ràng. Không tuyên bố bài mẫu đã quét lỗ hổng, kiểm tra coverage hoặc sinh SBOM: POM và build spec hiện tại mới thực hiện biên dịch, unit test, kiểm tra JAR và chuẩn bị artifact.

Với Java service dùng cơ sở dữ liệu Oracle, test tích hợp cần kiểm tra đúng phiên bản driver, schema migration và hợp đồng truy cập. Dành compartment hoặc môi trường test riêng, đưa bí mật từ nơi quản lý thích hợp, đặt timeout và dọn tài nguyên kể cả khi test lỗi.

### 9.2. Cache giúp nhanh hơn nhưng không phải nguồn sự thật

Maven tải dependency vào local repository; một runner mới có thể chưa có cache đó. Không giả định `~/.m2` của lần build trước luôn tồn tại trong lần sau.

Nếu nhóm triển khai cache hoặc repository mirror:

- Quản lý khóa cache theo toolchain và cấu hình dependency liên quan.
- Phân tách dữ liệu có credential khỏi dữ liệu cache được chia sẻ.
- Kiểm tra build từ môi trường sạch theo quy trình của nhóm.
- Tránh phụ thuộc vào artifact chỉ có trên máy của một lập trình viên.

`clean` xóa output dự án, không xóa toàn bộ Maven local repository. Vì thế “đã chạy clean” không đồng nghĩa mọi dependency đều vừa được tải mới.

### 9.3. Quy mô runner, timeout và tài nguyên test

Bắt đầu với cấu hình runner đủ cho ứng dụng nhỏ, đo thời gian từng bước rồi mới tăng CPU/RAM. Thiếu bộ nhớ có thể làm JVM hoặc tiến trình test bị hệ điều hành dừng; tăng timeout không sửa được nguyên nhân đó.

Oracle mô tả việc tính phí theo tài nguyên compute của runner trong thời gian build tại [Managed Build Stage](https://docs.oracle.com/en-us/iaas/Content/devops/using/managed_buildstage.htm). Chi phí thực tế còn phụ thuộc cấu hình và các dịch vụ sử dụng; không suy từ việc build thành công rằng toàn bộ bài thực hành miễn phí.

Đối với dự án lớn, cân nhắc chạy kiểm tra độc lập song song khi đã đo đủ tài nguyên. Không bật số luồng Maven hoặc số test fork quá cao trên runner nhỏ. Đặt timeout cho test, build step và toàn stage theo tính chất công việc.

Một build lỗi sau khi cấp cơ sở dữ liệu test có thể để lại chi phí nếu không có cleanup. Ngược lại, xóa môi trường test dùng chung khi một build kết thúc có thể làm gián đoạn build khác. Quyền sở hữu và vòng đời tài nguyên phải rõ ràng.

Tính sẵn sàng của production cần được kiểm chứng trong thiết kế triển khai, health check và chiến lược rollout/rollback. Bước build đóng góp artifact đáng tin cậy, không tự tạo khả năng dự phòng cho workload.

## 10. Chẩn đoán lỗi thường gặp

| Biểu hiện | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Enforcer báo sai Java/Maven | `JAVA_HOME`, `PATH` hoặc image runner khác dự kiến | Xem `mvn -version` và chọn đúng toolchain |
| `release version 17 not supported` | Compiler JDK quá cũ | Dùng JDK hỗ trợ mức release đã chọn |
| `UnsupportedClassVersionError` khi chạy | Runtime thấp hơn bytecode | Đồng bộ mức bytecode và runtime |
| Build thành công nhưng không thấy test | Tên lớp, test engine, plugin hoặc tùy chọn skip | Đối chiếu cấu hình và báo cáo thực tế |
| `no main manifest attribute` | Chưa khai báo entry point hoặc lấy nhầm JAR | Kiểm tra manifest và file artifact được chọn |
| `ClassNotFoundException`/`NoClassDefFoundError` | Dependency runtime thiếu hoặc classpath sai | Kiểm tra cách đóng gói và dependency scope |
| Tải dependency/plugin thất bại | DNS, proxy, TLS, mirror hoặc credential | Kiểm tra đường truy cập và quyền repository |
| Output artifact không được tìm thấy | Sai đường dẫn, tên file hoặc build chưa tạo gói | Đối chiếu vị trí file với `outputArtifacts.location` |
| Managed Build đạt nhưng Deliver lỗi | Tên logic không khớp, IAM hoặc kho đích sai | Kiểm tra mapping và quyền danh tính pipeline |
| `Permission denied` với wrapper | Chưa đặt executable bit hoặc file dùng CRLF | Sửa quyền/file trong Git và dùng LF cho script Linux |
| JVM/test process bị kill | Thiếu bộ nhớ hoặc quá nhiều tiến trình | Xem log và giảm mức song song hoặc đổi runner |
| Integration test treo | Không đặt timeout, dịch vụ chưa sẵn sàng | Thêm readiness, timeout và cleanup |

Nếu sử dụng Maven Wrapper, commit các file wrapper cần thiết, cố định bản phân phối và review nguồn tải. Trên Linux dùng `./mvnw`; trên Windows dùng `mvnw.cmd`. Nếu thay Maven có sẵn bằng wrapper trong pipeline, kiểm tra executable bit, line ending và khả năng tải distribution trước.

Với Gradle, giữ cùng nguyên tắc: toolchain được chỉ rõ, test phải thực chạy và chọn đúng task đóng gói. `./gradlew clean build` thường bao gồm các kiểm tra được dự án nối vào `check`, nhưng task integration test tùy chỉnh chỉ chạy khi đã được cấu hình; `jar`, `bootJar` và `war` không mặc nhiên tạo cùng một loại sản phẩm. Không đổi công cụ build chỉ để bỏ qua lỗi kiểm tra.

## 11. Tiêu chí hoàn thành phòng thực hành

Bài thực hành hoàn chỉnh có đủ bằng chứng:

- Repository chứa POM, mã, test và build spec; không có credential hoặc output cục bộ.
- Log ghi nhận JDK/Maven đúng yêu cầu.
- Hai unit test và một kiểm tra JAR chạy thành công, không bị skip.
- `target/oci-java-demo.jar` chạy được với `java -jar`.
- Managed Build chỉ chuẩn bị artifact sau khi `clean verify` đạt.
- JAR đầu ra, checksum, báo cáo test và metadata khớp với build run.
- Nếu có Deliver Artifacts, gói được lưu dưới phiên bản xác định và tải lại kiểm tra được.
- Thử làm sai một assertion trong một nhánh lab khiến build thất bại và không đi tiếp tới phát hành; sau đó khôi phục mã.
- Tài nguyên phụ trợ của integration test được dọn và artifact/log được giữ theo thời hạn của nhóm.

Trong phòng thực hành này không cần triển khai ứng dụng lên Compute hay tạo Database. Nếu đã bổ sung các tài nguyên đó để mở rộng, xác minh quyền sở hữu trước khi dọn; giữ các artifact còn phục vụ kiểm tra hoặc rollback.

Kết quả cần đạt là một chuỗi bằng chứng rõ ràng: **commit xác định → toolchain xác định → kiểm tra đạt → artifact xác định**. Đó là đầu vào để các bước CI/CD tiếp theo triển khai ứng dụng Java trên OCI có kiểm soát.
