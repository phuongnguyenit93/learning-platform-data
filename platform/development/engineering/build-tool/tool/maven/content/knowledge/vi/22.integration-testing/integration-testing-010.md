# Kiểm soát cổng, cơ sở dữ liệu và tài nguyên ngoài khi chạy trên CI

## 1. Vấn đề: integration test đúng trên laptop nhưng thất bại trong CI

**Kiểm thử tích hợp (integration test)** xác nhận nhiều thành phần thực sự phối hợp: ứng dụng và cơ sở dữ liệu, giao tiếp TCP/HTTP, hàng đợi, object storage, dịch vụ OAuth thử nghiệm hoặc một container phụ trợ. Khác với unit test chỉ gọi hàm và mock, integration test thường phải **tạo, truy cập và dọn dẹp tài nguyên có vòng đời thực**.

Trong môi trường CI, nhiều job có thể chạy đồng thời trên cùng host, cùng Docker daemon hoặc một dịch vụ dùng chung. Lúc đó những giả định “máy này chỉ có một test” dễ gây lỗi:

- Hai job cùng bind **cổng 8080** dẫn đến `BindException: Address already in use`.
- Hai test cùng ghi bảng `users` trong database tên `test`, làm assertions sai hoặc xóa dữ liệu của nhau.
- Một job kết thúc và dọn **container hoặc schema của job khác** vì hai job dùng chung project name.
- Test kết nối **localhost** nhưng dịch vụ thực sự chạy ở container khác hoặc ở Docker host khác.
- Database process đã start, nhưng **chưa sẵn sàng nhận connection**; test fail ngẫu nhiên do timing.
- CI không có quyền truy cập Docker socket hoặc private repository chứa image.
- Dịch vụ bên ngoài phản hồi chậm, rate-limit hoặc có dữ liệu cũ; test không tái lập được.
- Test lỗi ngay trong phase integration-test; script cleanup không chạy và để lại port, process, volume hay dữ liệu.
- Mật khẩu test database bị ghi vào log, URL chứa password hoặc artifact CI.

Mục tiêu không đơn giản là “mở cổng trống” hay “tăng timeout”, mà là **quản trị toàn bộ vòng đời tài nguyên**:

**Tạo đúng phạm vi → chờ sẵn sàng → dùng với định danh riêng → xác minh → dọn dẹp dù test fail → ghi nhận lỗi đủ chẩn đoán mà không lộ secret.**

Trong Maven, nên phối hợp **Maven Failsafe Plugin**, JUnit Jupiter và cơ chế cấp tài nguyên của CI/Testcontainers hoặc service orchestration. Mỗi thành phần có phạm vi kiểm soát riêng.

## 2. Bản đồ những tài nguyên cần kiểm soát

| Tài nguyên | Xung đột điển hình | Cách kiểm soát ưu tiên |
| --- | --- | --- |
| **TCP/HTTP port** | Hai server bind cùng host/port. | Cho OS cấp cổng động `0`; đọc cổng đã bind; ở container dùng mapped port do runtime cung cấp. |
| **Database instance** | Nhiều job xóa/sửa cùng dữ liệu. | Instance/container riêng; nếu phải chia sẻ, schema/tenant/database riêng theo job. |
| **Database rows** | Test dùng ID cố định, xóa toàn bảng. | UUID/namespace riêng; cleanup theo ownership, transaction rollback khi áp dụng đúng. |
| **Container** | Job dừng nhầm container hoặc trùng hostname/network. | Tên/project/network riêng theo job; label ownership; cleanup đúng nguồn. |
| **Filesystem/volume** | Test cùng ghi `target/output.json` hoặc volume chung. | `@TempDir`, thư mục theo module/job, volume riêng. |
| **Network service** | Không sẵn sàng, rate limit, timeout, DNS không ổn định. | Health/readiness check, timeout hữu hạn, endpoint thử nghiệm do nhóm quản lý. |
| **Queue/topic/bucket** | Message của test A đi vào test B. | Topic/queue/prefix riêng, correlation ID, TTL, cleanup có giới hạn. |
| **Credentials** | Secret lộ qua command line/log; quyền quá rộng. | Secret store, tài khoản test riêng, quyền tối thiểu, redaction. |
| **CPU/RAM/connection pool** | Nhiều fork/JVM/container gây OOM hoặc hết kết nối. | Giới hạn song song, metrics, quotas, phân bổ resource trên CI. |

**Không dùng tài nguyên production cho integration tests có thể ghi/xóa dữ liệu.** Endpoint phải thuộc môi trường thử nghiệm được cho phép, và các thao tác cleanup phải giới hạn đúng tài nguyên do job sở hữu.

## 3. Phân biệt cổng cố định, cổng động và container mapped port

Một server TCP phải bind đến một **địa chỉ mạng** và **cổng**. Ghi `localhost:8080` trong test có vẻ tiện, nhưng chỉ an toàn nếu bảo đảm duy nhất một process chiếm cổng đó trên network namespace đang xét.

### 3.1. Cổng động bằng port 0

Với Java:

~~~java
try (java.net.ServerSocket listener =
         new java.net.ServerSocket(
                 0, 10, java.net.InetAddress.getLoopbackAddress())) {
    int actualPort = listener.getLocalPort();
    System.out.println("Port đã được cấp: " + actualPort);
}
~~~

Đây là **đoạn mã minh họa**, không phải chương trình độc lập, vì còn cần class/method bao quanh. Tham số `0` yêu cầu hệ điều hành **cấp một cổng khả dụng ngay trong thao tác bind**. Sau đó `getLocalPort()` trả về cổng đã được cấp.

Không assert một con số cụ thể: cổng được chọn có thể khác ở mỗi lượt chạy. Một chương trình thử nghiệm tốt chỉ assert **port nằm trong dải hợp lệ** và kết nối được tới endpoint thật.

**Tránh mô hình check-then-bind:**

~~~text
Bước 1: mở socket tạm để "tìm cổng rảnh"
Bước 2: đóng socket đó
Bước 3: khởi động server thật trên cùng số cổng
~~~

Giữa bước 2 và 3, một process khác có thể chiếm cổng. Đây là **TOCTOU race** (time-of-check/time-of-use). Ưu tiên framework hỗ trợ `port=0` **và trả cổng sau khi server đã bind**, hoặc cấp/giữ socket theo cách server thực sự hỗ trợ.

### 3.2. Loopback không giống hostname của container

`InetAddress.getLoopbackAddress()` trỏ tới loopback của **network namespace đang chạy test**. Nếu test và ứng dụng cùng JVM/host, điều này hợp lý. Nhưng `localhost` **bên trong một container khác** không phải localhost của Docker host hay container dịch vụ.

Với dịch vụ container hóa, phải dùng **hostname/IP và mapped port do hạ tầng cấp**, không mặc định `localhost:5432`. Khi Testcontainers chạy trên Docker host từ xa, `container.getHost()` có thể khác `localhost`.

### 3.3. Readiness khác với process started

Một container/process đã được tạo **không có nghĩa dịch vụ có thể phục vụ request**. Đối với cơ sở dữ liệu, cần đủ điều kiện: socket đang mở, authentication/DB startup hoàn tất, schema/migration phù hợp và user thử nghiệm có quyền.

Không dùng cố định `Thread.sleep(5000)` như một hợp đồng sẵn sàng. Hãy dùng health check, kiểm tra JDBC connection hoặc HTTP readiness với **deadline hữu hạn**, backoff hợp lý và thông báo lỗi rõ.

## 4. Maven Surefire và Failsafe giữ những vai trò nào?

### Maven Surefire Plugin

**Surefire** thường chạy các **unit tests** ở phase `test`. Tên class mặc định thường như `ExampleTest`, `TestExample`, `ExampleTests`, `ExampleTestCase`. Những test thuần logic nhanh không cần Docker/DB nên giữ ở tầng unit.

### Maven Failsafe Plugin

**Failsafe** dành cho **integration tests**, thường có tên class:

- Bắt đầu bằng `IT` như `ITDatabase`.
- Kết thúc bằng `IT` như `DatabaseIT`.
- Kết thúc bằng `ITCase` như `DatabaseITCase`.

Hai goal quan trọng:

- `failsafe:integration-test`: thực thi integration tests và ghi kết quả, **không kết thúc build ngay chỉ vì assertion failure**.
- `failsafe:verify`: đánh giá kết quả integration tests và **đánh fail build** nếu cần.

Điều này cho phép Maven tiếp tục đi qua `post-integration-test` để đóng dịch vụ hoặc giải phóng môi trường sau khi test thất bại, trước khi goal `verify` đánh dấu thất bại.

### Chuỗi phase đáng nhớ

~~~text
validate
  |
compile -> test-compile -> test (Surefire unit tests)
  |
package
  |
pre-integration-test    setup môi trường bên ngoài, nếu có plugin bind
  |
integration-test        Failsafe chạy IT và lưu kết quả
  |
post-integration-test   dọn môi trường, nếu có plugin bind
  |
verify                  Failsafe kiểm tra IT result và quyết định PASS/FAIL
~~~

**Dùng `mvn verify` cho quy trình integration test.** Không gọi riêng `mvn integration-test` như lệnh cuối pipeline: Maven sẽ dừng tại phase đó, nên các phase sau — trong đó có `post-integration-test` và `verify` — **không chạy**.

Phân biệt rõ: Failsafe giúp **không fail sớm vì test assertion trong phase integration-test**, nhưng **không bảo đảm cleanup khi Maven bị kill, máy mất điện, Docker daemon sập, setup plugin lỗi trước đó, hoặc một goal khác chặn lifecycle**. CI vẫn cần cleanup hook/TTL và chính sách sở hữu tài nguyên.

## 5. Ví dụ Java 17 chạy được không cần Docker: TCP + H2

Ta xây một dự án Maven nhỏ có:

- **Unit test** cho một hàm trả trạng thái.
- **Integration test TCP**: mở server qua `ServerSocket(0)` rồi client kết nối vào **cổng động thực tế**.
- **Integration test JDBC**: dùng H2 in-memory database **riêng cho từng test**, tạo bảng, ghi và truy vấn dữ liệu rồi đóng kết nối.

Đây là **môi trường thực thi giao tiếp TCP/JDBC thật**, nhưng **H2 chạy trong process** chứ không phải một PostgreSQL/MySQL server ngoài JVM. Nó là **baseline tái lập không cần Docker**, không thay thế test với engine DB production. Phần sau trình bày cách chuyển sang PostgreSQL/Testcontainers.

Yêu cầu: **JDK 17+**, Maven tương thích với plugin versions được pin và kết nối tới Maven repository được phép để tải JUnit, H2 và plugins.

Cấu trúc:

~~~text
ci-integration-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/vn/example/ci/StatusEndpoint.java
    └── test/
        └── java/vn/example/ci/
            ├── StatusEndpointTest.java
            ├── TcpPortIT.java
            └── DatabaseIT.java
~~~

### 5.1. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>ci-integration-demo</artifactId>
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
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
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
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                </configuration>
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
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                </configuration>
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

Đọc POM:

1. JUnit Jupiter và H2 có **scope test**: chúng không là dependency runtime của class chính.
2. Compiler Plugin nhắm Java 17.
3. Surefire chạy `StatusEndpointTest` trong phase `test`.
4. Failsafe được **bind cả `integration-test` và `verify`**; hai class `TcpPortIT`, `DatabaseIT` khớp quy ước Failsafe.
5. `failIfNoTests=true` giúp pipeline phát hiện khi test tương ứng bị đổi tên/lọc sai và không còn test nào được phát hiện. Nếu một module hợp lệ thực sự không có IT, cần cấu hình theo module/profile thay vì áp quy tắc này bừa bãi vào toàn reactor.
6. `forkCount=1`, `reuseForks=true` giới hạn mỗi plugin execution theo một JVM test fork cho ví dụ, giúp dễ chẩn đoán. Không có nghĩa toàn CI chỉ có một JVM: nhiều module/job vẫn có thể chạy đồng thời.
7. Version được chốt cho ví dụ; **không khẳng định đây là bản mới nhất**. Khi áp dụng production cần xem compatibility/security policy và cập nhật có kiểm chứng.

### 5.2. src/main/java/vn/example/ci/StatusEndpoint.java

~~~java
package vn.example.ci;

import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public final class StatusEndpoint {
    private StatusEndpoint() {
    }

    public static String status() {
        return "PONG";
    }

    public static void serveOnce(ServerSocket listener) throws IOException {
        try (Socket client = listener.accept();
             Writer writer = new OutputStreamWriter(
                     client.getOutputStream(), StandardCharsets.UTF_8)) {
            writer.write(status() + "\n");
            writer.flush();
        }
    }

    public static void main(String[] args) {
        System.out.println("CI integration demo: " + status());
    }
}
~~~

`serveOnce()` thực hiện **giao tiếp thật qua TCP**: chờ một kết nối, ghi chuỗi `PONG` và ký tự xuống dòng, rồi đóng client. Nó **không tự bind cổng hoặc tạo background server**; integration test sẽ cấp `ServerSocket` và quản lý thread/lifecycle. Nhờ vậy việc chọn cổng và cleanup nằm trong test harness.

### 5.3. src/test/java/vn/example/ci/StatusEndpointTest.java

~~~java
package vn.example.ci;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class StatusEndpointTest {
    @Test
    void statusIsStable() {
        assertEquals("PONG", StatusEndpoint.status());
    }
}
~~~

Đây là **unit test** thuần, không mở TCP socket hoặc DB. Surefire nhận diện class `StatusEndpointTest` qua tên kết thúc bằng `Test`.

### 5.4. src/test/java/vn/example/ci/TcpPortIT.java

~~~java
package vn.example.ci;

import org.junit.jupiter.api.Test;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TcpPortIT {
    @Test
    void realTcpServiceUsesAssignedPort() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try (ServerSocket listener = new ServerSocket(
                0, 10, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(5_000);

            int assignedPort = listener.getLocalPort();
            assertTrue(assignedPort > 0);
            assertTrue(assignedPort <= 65_535);

            Future<?> service = executor.submit(() -> {
                try {
                    StatusEndpoint.serveOnce(listener);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(), assignedPort), 2_000);
                client.setSoTimeout(3_000);

                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(client.getInputStream(),
                                StandardCharsets.UTF_8))) {
                    assertEquals("PONG", reader.readLine());
                }
            }

            service.get(5, TimeUnit.SECONDS);
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

**Vì sao ví dụ này tránh xung đột cổng:**

- `new ServerSocket(0, ...)` **bind luôn** cổng trống, không check rồi đóng socket.
- `assignedPort` được đọc **sau khi bind**, nên client dùng đúng cổng.
- Server và client cùng dùng `InetAddress.getLoopbackAddress()`, tránh hardcode IPv4 `127.0.0.1` khi JVM/OS ưu tiên IPv6 loopback.
- `Socket.connect` và `readLine` có timeout hữu hạn; `listener.setSoTimeout` tránh chờ accept vô hạn.
- `try-with-resources` đóng client và listener; `finally` dừng executor.
- `Future.get(...)` truyền lỗi từ worker thread về test thay vì chỉ in lỗi ở background thread rồi để test pass giả.

**Không assert port phải là 8080, 50000 hay bất kỳ giá trị cố định nào.** Nếu CI hạn chế socket loopback, test cần chạy trên runner có quyền network phù hợp hoặc được đánh dấu skip theo policy rõ ràng; đừng tự động mở inbound port công khai.

### 5.5. src/test/java/vn/example/ci/DatabaseIT.java

~~~java
package vn.example.ci;

import org.junit.jupiter.api.Test;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DatabaseIT {
    @Test
    void writesAndReadsAnIsolatedDatabase() throws Exception {
        String databaseName = "ci_" +
                UUID.randomUUID().toString().replace("-", "");
        String jdbcUrl = "jdbc:h2:mem:" + databaseName;

        try (Connection connection =
                     DriverManager.getConnection(jdbcUrl, "sa", "")) {
            try (Statement ddl = connection.createStatement()) {
                ddl.execute("CREATE TABLE ci_events (" +
                        "id INTEGER PRIMARY KEY, " +
                        "result_text VARCHAR(40) NOT NULL)");
                ddl.executeUpdate("INSERT INTO ci_events " +
                        "(id, result_text) VALUES (1, 'ready')");
            }

            try (PreparedStatement query =
                         connection.prepareStatement(
                                 "SELECT result_text FROM ci_events WHERE id = ?")) {
                query.setInt(1, 1);

                try (ResultSet results = query.executeQuery()) {
                    assertTrue(results.next());
                    assertEquals("ready", results.getString(1));
                    assertFalse(results.next());
                }
            }
        }
    }
}
~~~

Ví dụ sử dụng **JDBC thật và SQL DDL/DML thật**, nhưng **H2 in-memory**, không cần database process bên ngoài. Mỗi lần test tạo một tên database ngẫu nhiên dạng chữ/số; test A không dùng chung database với test B ngay cả khi chúng nằm trong cùng JVM.

- `try-with-resources` đóng `ResultSet`, `PreparedStatement`, `Statement` và `Connection`.
- Không bật `DB_CLOSE_DELAY=-1`: database H2 in-memory có thể bị hủy khi connection cuối đóng theo cấu hình mặc định, tránh tích lũy nhiều database trong fork.
- Không dùng credential production; tài khoản `sa` và password rỗng chỉ trong **H2 local thử nghiệm**, không nên suy rộng sang service thật.
- Không sinh SQL object name từ dữ liệu CI tùy ý: tên trong ví dụ được tạo bằng UUID và tiền tố cố định, không lấy trực tiếp tên branch/job thiếu kiểm tra.

**Giới hạn:** H2 không đảm bảo hành vi PostgreSQL/MySQL về transaction isolation, locking, kiểu dữ liệu, SQL dialect, extension, migration hoặc connection limits. Hãy dùng H2 cho baseline/logic phù hợp và **thêm test với engine database thực sự** khi ứng dụng phụ thuộc vào đặc tính của engine đó.

## 6. Chạy và kiểm chứng kết quả của dự án

Tại thư mục `ci-integration-demo`:

~~~bash
mvn --version
mvn -B -ntp clean verify
java -cp target/classes vn.example.ci.StatusEndpoint
~~~

Khi JDK 17, Maven, dependency và quyền mở loopback socket hợp lệ, có thể kỳ vọng:

- Surefire chạy **1 unit test**: `StatusEndpointTest`.
- Failsafe chạy **2 integration tests**: `TcpPortIT` và `DatabaseIT`.
- Báo cáo unit test ở `target/surefire-reports`.
- Báo cáo integration test ở `target/failsafe-reports`.
- Lệnh `mvn verify` chạy cả hai tầng, rồi dùng goal Failsafe verify quyết định kết quả IT.

**Stdout chính xác của riêng lệnh Java cuối cùng:**

~~~text
CI integration demo: PONG
~~~

`mvn verify` **không tự chạy `StatusEndpoint.main`**. Không khẳng định tổng log Maven sẽ đúng một mẫu cố định vì thread timing, cache, Maven/JDK version và plugin logs có thể khác nhau.

### Quan sát test reports

**Linux/macOS:**

~~~bash
ls target/surefire-reports
ls target/failsafe-reports
~~~

**Windows PowerShell:**

~~~powershell
Get-ChildItem target\surefire-reports
Get-ChildItem target\failsafe-reports
~~~

Một số file có tên dạng `TEST-vn.example.ci.DatabaseIT.xml`, `TEST-vn.example.ci.TcpPortIT.xml` và summary của Failsafe; tên/metadata cụ thể phụ thuộc plugin version. Báo cáo là bằng chứng test đã được phát hiện/chạy; **đừng chỉ thấy `BUILD SUCCESS` rồi bỏ qua việc test đã bị skip hoặc không được match**.

### Vì sao `mvn test` không đủ?

~~~bash
mvn -B -ntp test
~~~

Thông thường Surefire chạy unit tests, nhưng lifecycle **chưa tới integration-test/verify**, nên ví dụ không chạy Failsafe IT. Lệnh `mvn package` cũng chưa tới phase integration-test; không dùng nó làm bằng chứng integration tests pass.

**Lệnh chính cho CI có kiểm thử tích hợp là `mvn clean verify`**, sau đó xem báo cáo và artifact được phát hành.

## 7. Một ứng dụng thật cần cổng từ đâu?

Tùy kiến trúc, cổng được cấp ở nơi khác nhau:

| Kiến trúc | Cách chọn cổng đúng | Cách test lấy địa chỉ |
| --- | --- | --- |
| Server Java trong cùng JVM | Bind `port=0`. | Đọc `ServerSocket.getLocalPort()` hoặc API server của framework. |
| Spring Boot test khởi chạy HTTP | Dùng random-port test mode của framework. | Lấy actual local server port được framework inject, không hardcode 8080. |
| Container Testcontainers | Expose **container port** cố định nhưng map sang **host port ngẫu nhiên**. | `container.getHost()` + `container.getMappedPort(containerPort)` sau khi start. |
| Docker Compose trong CI | Dùng project name/network riêng, chọn port mapping có kiểm soát. | Đọc mapping từ Docker/Compose; không giả định host port cố định. |
| Kubernetes test namespace | Service DNS/port trong namespace; ingress chỉ khi cần. | Endpoint được orchestrator cấp trong namespace, không gán localhost máy CI. |
| Dịch vụ ngoài do đội khác vận hành | URL/credentials từ cấu hình môi trường thử nghiệm. | Health check, contract và quyền; không tự mở cổng trên host đó. |

**Cổng trong container** và **cổng trên host** không giống nhau. PostgreSQL có thể nghe cổng **5432 bên trong container**, nhưng Testcontainers ánh xạ nó sang một cổng host ngẫu nhiên để tránh va chạm. Đó là lý do không được tự tạo JDBC URL `jdbc:postgresql://localhost:5432/...` khi dùng Testcontainers trong CI.

## 8. Testcontainers: cô lập PostgreSQL để test integration thực hơn

Nếu ứng dụng phụ thuộc tính năng PostgreSQL cụ thể, nên có một tầng IT dùng PostgreSQL thực sự. **Testcontainers for Java** có thể khởi tạo container theo vòng đời test, expose port ngẫu nhiên và cung cấp JDBC URL thực.

**Điều kiện để chạy phần này:** runner phải có **container runtime/Docker API tương thích**, quyền truy cập image và tài nguyên cần thiết. Không phải mọi hosted CI runner cho phép Docker-in-Docker hoặc mount Docker socket. Phần này **là ví dụ mở rộng có điều kiện**, không nằm trong POM Docker-free ở mục 5.

### 8.1. Thêm dependency cho Testcontainers

Với các module Testcontainers **2.0.5** theo tài liệu cùng nhánh và PostgreSQL JDBC driver được pin, thêm các mục sau vào `<dependencies>` của POM:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-postgresql</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>42.7.4</version>
    <scope>test</scope>
</dependency>
~~~

Đây là **đoạn phụ thuộc thêm**, không phải POM độc lập. Các tọa độ Testcontainers 2.x ở đây khác một số ví dụ cũ dùng tên artifact từ Testcontainers 1.x; **không trộn BOM/module versions giữa hai nhánh**. Kiểm tra Java/Docker compatibility và chính sách vulnerability/license trước khi dùng trong sản phẩm.

### 8.2. src/test/java/vn/example/ci/PostgresIT.java (mở rộng)

~~~java
package vn.example.ci;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class PostgresIT {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4");

    @Test
    void connectsToEphemeralPostgres() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                     postgres.getJdbcUrl(),
                     postgres.getUsername(),
                     postgres.getPassword());
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT 1")) {
            assertTrue(result.next());
            assertEquals(1, result.getInt(1));
        }
    }
}
~~~

Khi Docker phù hợp và image pull được, extension quản lý vòng đời container static **theo test class**. Test dùng `postgres.getJdbcUrl()` chứ không hardcode host/cổng. Password là credential **chỉ của container test vừa tạo**, không được log hoặc dùng chung với tài khoản production.

**Chú ý quan trọng về concurrency:** tài liệu Testcontainers JUnit 5 extension nói rõ nó được kiểm thử với **thực thi tuần tự**, còn chạy **song song không được hỗ trợ như một cam kết** và có thể tạo side effects. Không bật JUnit concurrent cho các Testcontainers IT theo mặc định; nếu muốn tăng tốc, phải kiểm chứng chiến lược isolation cụ thể hoặc tách JVM/job sao cho tài nguyên không trùng.

### 8.3. Container port mapping

Với generic container expose cổng 8080, cách xây URL sau khi container đã start:

~~~java
String host = container.getHost();
int port = container.getMappedPort(8080);
String url = "http://" + host + ":" + port;
~~~

Đây là **đoạn Java minh họa**, giả định biến `container` đã là container **đang chạy**. `getMappedPort()` chỉ có ý nghĩa sau startup; dùng trước có thể lỗi. Khi host dùng IPv6, việc ghép URL cần format hostname thích hợp; các module có API URI/URL nên tận dụng API đó thay vì nối chuỗi thủ công nếu hỗ trợ.

**Đối với PostgreSQLContainer**, `getJdbcUrl()` thường là lựa chọn tốt hơn tự ghép `getHost()+getMappedPort(5432)` vì nó đóng gói thêm tên database và thuộc tính cần thiết.

### 8.4. Readiness của DB container

Testcontainers có **wait strategies** để chờ service đủ sẵn sàng theo cơ chế hỗ trợ, không chỉ container process ở trạng thái “running”. Với PostgreSQLContainer, module chuyên dụng có startup/readiness logic. Nếu ứng dụng khởi chạy migration Flyway/Liquibase hoặc seed dữ liệu, có thể cần **thêm bước chờ điều kiện nghiệp vụ**, chẳng hạn schema version đã cập nhật.

Không đặt `Thread.sleep(10_000)` rồi mặc định mọi CI/architecture đều khởi động DB trong 10 giây. Chọn deadline hữu hạn, log nguyên nhân không sẵn sàng và cleanup khi timeout. **Timeout đủ dài nhưng vô hạn không phải chiến lược ổn định.**

## 9. Tài nguyên cấp test, class, fork, module và CI job

Một lỗi thiết kế thường gặp là gán một tên tài nguyên **chỉ duy nhất trong một JVM** nhưng lại dùng chung database giữa nhiều CI jobs.

Có thể hình dung:

~~~text
CI pipeline run
  |
  +-- job / runner riêng
        |
        +-- Maven reactor module
              |
              +-- Surefire/Failsafe JVM fork
                    |
                    +-- JUnit test class
                          |
                          +-- test method
~~~

**Phạm vi càng rộng, khóa/định danh càng phải đủ độc lập.**

| Phạm vi tài nguyên | Có thể chia sẻ với ai? | Gợi ý |
| --- | --- | --- |
| Test method | Một test duy nhất. | `@TempDir`, UUID, instance DB per test. |
| Test class | Các method trong cùng class. | Static Testcontainers container, seed/cleanup rõ ràng, cân nhắc chạy tuần tự. |
| JVM fork | Nhiều class được Failsafe phân cho fork. | Namespace có fork ID; tránh static/global mutable state không được restore. |
| Maven module | Nhiều test/fork trong module. | Module ID trong path/schema; test suite owner. |
| CI job | Nhiều modules/JVM trong job. | Namespace gồm CI job/run ID; container project/volume riêng. |
| Nhiều CI jobs | Có thể chạy trên host/dịch vụ chung. | UUID/lease/namespace toàn cục hoặc môi trường thử nghiệm riêng; cleanup theo ownership. |

Một định danh thường phải bao gồm **job ID + module + fork + test** ở những tài nguyên dùng chung xuyên nhiều tầng. Không nên in cả branch name chưa chuẩn hóa vào tên SQL object, Docker resource hoặc URL; phải **sanitize** và giới hạn độ dài hợp lệ của từng hệ thống.

### surefire.forkNumber

Surefire/Failsafe hỗ trợ placeholder **`${surefire.forkNumber}`** trong một số cấu hình, ví dụ system property của forked JVM:

~~~xml
<configuration>
    <forkCount>2</forkCount>
    <reuseForks>true</reuseForks>
    <systemPropertyVariables>
        <test.fork.id>${surefire.forkNumber}</test.fork.id>
    </systemPropertyVariables>
</configuration>
~~~

Đây là **đoạn đặt trong plugin Failsafe/Surefire**, không phải POM hoàn chỉnh. Giá trị fork number không phải UUID toàn cục. Trong **hai CI jobs khác nhau**, cùng fork number `1` có thể xuất hiện; phải kết hợp job/run identifier khi tài nguyên nằm ngoài JVM.

**`@ResourceLock` của JUnit Jupiter chỉ đồng bộ các test trong phạm vi cùng Jupiter engine**, không khóa các JVM khác hay Docker/DB server dùng chung. Đừng dùng annotation này như khóa liên tiến trình.

## 10. Database isolation: năm chiến lược và giới hạn

### 10.1. Instance/container riêng theo test hoặc job

Đây là giải pháp ít xung đột nhất khi hạ tầng cho phép. Mỗi job dùng DB instance/container của mình. Không có test nào nên biết mật khẩu hoặc URL của database production.

**Chi phí:** startup container, CPU/RAM, disk và image pull. Với hàng trăm test class, không phải lúc nào một DB container mỗi method cũng tối ưu.

### 10.2. Database/schema riêng trên cùng server

Nếu cùng một PostgreSQL server thử nghiệm phải phục vụ nhiều job, tạo **database/schema riêng** theo job, cấp quyền giới hạn đúng namespace. Chỉ xóa schema/database do job đã tạo sau khi xác minh ownership.

**Cẩn thận:** DDL/migration có thể vượt khỏi một transaction; shared extensions, advisory locks, sequence/global settings hoặc role permissions vẫn có thể ảnh hưởng nhau. Schema isolation không luôn tương đương instance isolation.

### 10.3. Mỗi test dùng row ID/tenant riêng

Nếu cùng schema phục vụ nhiều test, dùng record IDs ngẫu nhiên và tenant/correlation ID riêng:

~~~text
ci_job_6247 / test_1  -> customer_id = 7e9...
ci_job_6247 / test_2  -> customer_id = af3...
ci_job_6248 / test_1  -> customer_id = 05b...
~~~

Đây chỉ là **mẫu biểu diễn**; không phải dữ liệu database thực. Cleanup dùng **ID/tenant thuộc quyền sở hữu của test**, không dùng `DELETE FROM customers` trên bảng chia sẻ. Dữ liệu phải được lọc đúng tenant trong mọi query của test.

### 10.4. Transaction rollback

Với những bài test chỉ thực hiện thao tác trên **một transaction do test kiểm soát**, rollback sau test có thể đưa DB về trạng thái cũ.

**Không nên coi rollback là “cách ly tuyệt đối”:** code ứng dụng có thể mở transaction khác, async worker commit dữ liệu ngoài transaction của test, migration DDL commit riêng, queue/outbox tạo side effects hoặc nhiều connections cùng ghi. Đọc transaction semantics của framework và database.

### 10.5. Fixture cleanup

Nếu phải tạo tài nguyên thật, dùng cấu trúc:

~~~text
SETUP:  tạo ID/namespace riêng, cấp quyền, seed dữ liệu tối thiểu
ACT:    gửi request / truy vấn / phát message
ASSERT: kiểm tra đúng dữ liệu của test
TEARDOWN: xóa theo owner, luôn chạy dù assertion lỗi
~~~

`try/finally`, `@AfterEach`, `@AfterAll`, Testcontainers extension và lifecycle plugin giúp cleanup trong hoàn cảnh bình thường. Tuy nhiên **process bị kill hoặc network chia cắt** vẫn có thể bỏ lại tài nguyên; kết hợp TTL, janitor job và labeling để dọn orphan resources theo chính sách.

## 11. Cleanup phải có ownership, không được xóa rộng

Một `finally` có câu lệnh xóa dữ liệu không giới hạn còn nguy hiểm hơn việc test bị fail. Khi cleanup, **phải chứng minh tài nguyên thuộc job**.

**Ví dụ không an toàn:**

~~~text
DROP DATABASE test;
docker container prune --force
docker volume prune --force
rm -rf /shared/test-data
~~~

Đây là **danh sách anti-pattern minh họa**, không phải hướng dẫn thực thi. Những lệnh xóa rộng có thể phá dữ liệu của job khác nếu chạy trên hạ tầng chia sẻ.

**Mẫu an toàn hơn:**

- Gắn `owner=ci-run-id`, `module`, `createdAt` vào container/volume/schema nếu hạ tầng hỗ trợ.
- Tạo namespace bằng token ngẫu nhiên hoặc ID job đã chuẩn hóa, **không trùng giữa nhiều pipeline**.
- Giữ danh sách ID tài nguyên mà job vừa tạo và chỉ cleanup danh sách đó.
- Không xóa tài nguyên không có owner khớp; orphan cleanup phải chạy trong workflow được phép và có TTL.
- Dừng service trước khi xóa volume/schema; log status cleanup mà không lộ credentials.
- Đối với DB/container có dữ liệu nhạy cảm, tuân thủ retention/audit policy và quyền tối thiểu.

### Tách lỗi test và lỗi cleanup

Nếu assertion test fail, teardown vẫn phải được thử. Nếu teardown fail, báo cả hai lỗi nếu công cụ hỗ trợ mà không che root cause. Trong Java, `try-with-resources` có **suppressed exceptions** giúp lưu lỗi khi đóng resource bên cạnh lỗi chính; đọc log đầy đủ khi cần chẩn đoán.

**Đừng xem pipeline success nếu cleanup bắt buộc chưa hoàn tất** trừ khi tổ chức có quy tắc xử lý ngoại lệ và janitor đáng tin cậy.

## 12. Maven pre-integration-test và post-integration-test

Maven lifecycle cung cấp các phase **`pre-integration-test`**, **`integration-test`**, **`post-integration-test`**, **`verify`**.

Một hệ thống tự chạy service qua plugin có thể gắn:

~~~text
pre-integration-test:
  start disposable service/container
  wait readiness, publish connection parameters
integration-test:
  failsafe:integration-test
post-integration-test:
  stop service/container and collect logs
verify:
  failsafe:verify checks test result
~~~

Đây là **sơ đồ luồng**, không phải POM/plugin cấu hình đầy đủ. Plugin start/stop cụ thể khác nhau theo server, Docker/Compose/Kubernetes hoặc framework. Khi tạo service bằng plugin, dùng đúng **start goal nonblocking** và **stop goal** của plugin được chọn.

**Lợi ích của Failsafe:** test thất bại tại integration-test không lập tức chặn post-integration-test, khác với việc dùng plugin/command tự fail sớm và bỏ qua cleanup.

**Giới hạn của lifecycle:** lỗi ở phase setup, process termination, `SIGKILL`, CI cancel, máy chết hoặc stop goal báo lỗi có thể để lại tài nguyên. Vì vậy vẫn nên có **CI cleanup hook**, namespace độc lập và TTL/hạ tầng dọn orphan.

Không gọi riêng:

~~~bash
mvn integration-test
~~~

rồi coi là xong: lệnh này **không chạy tiếp `post-integration-test` và `verify`**. Với cấu hình bài tập ở mục 5, dùng:

~~~bash
mvn -B -ntp clean verify
~~~

## 13. Docker Compose trên CI: project name phải duy nhất

Nếu đã có một file Compose hợp lệ trong repository kiểm thử, pattern phổ biến là cấp **project name riêng** cho mỗi job để container/network/volume của job không trùng tên. Ví dụ **ý tưởng cho runner Bash**, cần điều chỉnh theo CI provider và chính sách tài nguyên:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

project="it_${CI_JOB_ID:-local}_${RANDOM}_${RANDOM}"

cleanup() {
  docker compose -p "$project" down -v --remove-orphans \
    >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -p "$project" up -d --wait
mvn -B -ntp clean verify
~~~

**Đây là pattern, không phải script chạy độc lập trên mọi máy**: cần Compose file thật, Docker Compose hỗ trợ `--wait`, Docker daemon và quyền truy cập. `CI_JOB_ID` ở đây chỉ là biến giả định CI provider có thể cấp; suffix ngẫu nhiên làm giảm nguy cơ trùng trong cùng host. Với môi trường lớn nên dùng **ID job/run được chuẩn hóa, có đủ tính duy nhất và có kiểm soát**.

**Cảnh báo an toàn về `down -v`:** câu lệnh này xóa volume của **Compose project đã được chỉ định**. Chỉ áp dụng cho **volume thử nghiệm hoàn toàn disposable do job vừa tạo**. Không dùng khi Compose file tham chiếu volume dữ liệu production hoặc volume chia sẻ; trước khi dùng phải kiểm tra manifest Compose và quy định cleanup.

`trap cleanup EXIT` sẽ chạy khi shell thoát bình thường, nhưng không bảo vệ mọi trường hợp bị kill cưỡng bức hoặc host bị mất. Các CI provider thường có after-script/post-job hook, TTL/labels hay chính sách dọn orphan riêng; dùng chúng bổ sung.

### Không hardcode host port trong Compose

Nếu mọi job publish `5432:5432` lên cùng Docker host, job thứ hai có thể fail bind. Cho Docker/Compose ánh xạ cổng host động hoặc chỉ giao tiếp **qua service DNS nội bộ của project network** khi app/test cùng network. Test chạy ở host cần đọc cổng mapped thực tế; test chạy trong cùng Compose network có thể dùng service name và cổng nội bộ.

**Tính nhất quán network namespace quan trọng hơn việc mọi URL đều chứa localhost.**

## 14. Khi nào cần Docker-based integration test, khi nào không?

Không phải mọi integration test đều phải khởi động PostgreSQL, Kafka hoặc Redis thật. Phân loại test để tối ưu độ tin cậy:

| Loại test | Nguồn tài nguyên | Giá trị | Hạn chế |
| --- | --- | --- | --- |
| Unit test | Pure functions/mocks | Nhanh, đơn giản, dễ song song. | Không xác nhận giao thức/driver/DB thật. |
| Lightweight IT | TCP loopback + H2 in-memory | Tái lập, không cần Docker, kiểm tra network/JDBC path. | Không mô phỏng đầy đủ database/server production. |
| Container IT | PostgreSQL/Redis/Kafka container per class/job | Test engine/protocol gần thực tế. | Cần runtime, image, RAM, cleanup/readiness. |
| Shared staging IT | Dịch vụ staging dùng chung | Test tích hợp nhiều thành phần đã triển khai. | Dữ liệu và tài nguyên dễ va chạm; cần namespace/contract. |
| E2E | Toàn bộ luồng qua nhiều service | Phát hiện tích hợp hệ thống. | Chậm hơn, phụ thuộc môi trường rộng, cần quan sát kỹ. |

**Không đánh đồng H2 và PostgreSQL**. Nếu production dùng transaction isolation, lock, index hoặc SQL extensions đặc thù PostgreSQL, test cần có ít nhất một tầng dùng PostgreSQL thật hoặc dịch vụ tương đương được phê duyệt.

**Không dùng dữ liệu sản xuất nguyên bản để test**. Fixtures phải là dữ liệu giả/ẩn danh hợp lệ, không chứa credentials thật hoặc thông tin nhạy cảm.

## 15. Tính song song ở bốn lớp

Khi CI chạy nhiều integration tests đồng thời, phải xem nhiều cơ chế:

1. **JUnit Jupiter parallel execution** trong một JVM theo `junit.jupiter.execution.parallel.*`.
2. **Surefire/Failsafe forks** (`forkCount`, `reuseForks`) tạo một hoặc nhiều JVM.
3. **Maven Reactor** (`mvn -T ...`) chạy nhiều module đồng thời theo dependency graph.
4. **CI jobs/matrix** có thể chạy trên cùng host, Docker daemon hoặc database staging.

Ví dụ:

~~~text
2 CI jobs
  x 2 Maven modules concurrently
  x 2 Failsafe forks per module
  x 4 Jupiter workers per fork
~~~

Đó là **công thức tư duy về nguồn gây contention**, không phải khẳng định luôn có 32 test chạy chính xác cùng lúc. Scheduling, dependency graph, CPU limits và blocking làm mức thực tế thay đổi.

**Khởi đầu bảo thủ:** với IT dùng DB/container, giữ Failsafe `forkCount=1`, hạn chế JUnit parallel, tách tài nguyên trước khi tăng Maven `-T` hay CI matrix. Đo RAM, số Docker containers, DB connections và thời gian build.

### Vì sao @ResourceLock chưa đủ?

JUnit `@ResourceLock` có thể phối hợp các test trong **cùng một Jupiter engine** dùng chung tên khóa. Nó **không khóa JVM khác**, càng không khóa CI job trên máy khác. Nếu hai forks cùng dùng schema `ci_test`, dù annotation giống nhau, hai process vẫn có thể ghi cùng dữ liệu.

Dùng **isolation theo resource**, không dùng lock chỉ vì dễ thêm annotation. Với Testcontainers JUnit 5 extension, chạy test tuần tự theo hướng dẫn hiện hành khi chưa có chiến lược song song được hỗ trợ và kiểm chứng.

## 16. Timeouts: phải phân biệt ba loại

### 16.1. Startup/readiness timeout

Đây là giới hạn thời gian cho DB/service khởi động và sẵn sàng. Nên dùng healthcheck/connection readiness với deadline phù hợp thay vì sleep cứng. Nếu timeout, ghi trạng thái endpoint/container và logs đã redacted.

### 16.2. Test/request timeout

HTTP/TCP/JDBC operation cũng cần timeout hữu hạn. Trong Java TCP IT, `connect` có deadline **2.000 ms**, `readLine` có SO_TIMEOUT **3.000 ms**, `accept` có SO_TIMEOUT **5.000 ms**, `Future.get` có deadline **5 giây**. Các giá trị là **mẫu cho loopback test nhẹ**, không phải SLA đề xuất cho DB container trong mọi CI.

### 16.3. CI job timeout

Nếu toàn job quá giới hạn, CI có thể cancel process và teardown trong Maven không chạy. Cần chính sách dọn tài nguyên ngoài process, TTL/labels và giới hạn riêng cho setup/test/teardown khi nền tảng hỗ trợ.

**Timeout không phải “cách sửa flakiness” nếu vấn đề gốc là xung đột dữ liệu hoặc cổng cố định.** Trước khi tăng timeout, xác định test đang chờ readiness, chờ port, chờ DB lock, chờ pool connection hay bị nghẽn CPU.

## 17. Cấp credentials và cấu hình endpoint an toàn

CI có thể cần password cho database/container registry/private repository. Các nguyên tắc tối thiểu:

- Dùng **secret store** của CI hoặc cơ chế workload identity phù hợp; không commit password vào `pom.xml`, test source, `.env` trong repository.
- Tài khoản test có quyền **trên môi trường thử nghiệm**, không quyền quản trị/production.
- Tách credentials theo job nếu khả thi; revoke/rotate theo chính sách, không dùng token vĩnh viễn chung.
- Không in full JDBC URL khi nó có thể chứa password ở query string; không in toàn bộ `System.getenv()` hoặc Maven debug log lên kênh công khai.
- Không lưu database dump chứa dữ liệu nhạy cảm vào test reports/artifact CI mặc định.
- Với container test, sử dụng credentials ngắn hạn dành riêng cho disposable instance.
- Nếu cần certificate/truststore, cấp qua secret store/file mount giới hạn quyền và loại chúng khỏi binary artifact.

**Đừng dùng mục tiêu “CI phải chạy được” để tắt TLS verification, chặn security policy hoặc cấp đặc quyền Docker/DB vô hạn.** Lỗi security/network cần được điều tra ở đúng tầng.

### Chuyển cấu hình vào test runtime

Trong Maven Failsafe, `systemPropertyVariables` có thể chuyển **giá trị không nhạy cảm** như môi trường hoặc namespace:

~~~xml
<configuration>
    <systemPropertyVariables>
        <test.environment>ci</test.environment>
        <test.namespace>${env.CI_TEST_NAMESPACE}</test.namespace>
    </systemPropertyVariables>
</configuration>
~~~

Đây là **đoạn cấu hình đặt trong Failsafe plugin**, không phải file độc lập. Biến `CI_TEST_NAMESPACE` cần được CI cấp giá trị hợp lệ và đủ duy nhất. Nếu đây là secret, nên dùng cơ chế secret injection chuyên dụng và tránh đưa vào POM interpolated/log. Không dựa vào `test.namespace` để tạo SQL identifiers chưa sanitize.

### skipITs và giới hạn của việc skip

Maven Failsafe hỗ trợ `-DskipITs` để bỏ thực thi integration tests khi cần trong một hoàn cảnh kiểm soát, nhưng **không được dùng trong pipeline phải chứng minh integration tests đã chạy**. Các cờ skip khác nhau về compile vs execute tests và khác nhau giữa plugin versions, vì vậy kiểm tra tài liệu Failsafe/Surefire phiên bản đang dùng.

Một pipeline có thể `BUILD SUCCESS` khi IT bị skip; phải kiểm tra **báo cáo và số test thực thi**.

## 18. Chẩn đoán lỗi cổng trên CI

### Lỗi 1 — Address already in use

~~~text
java.net.BindException: Address already in use
~~~

Có thể do hai process cùng cố bind `0.0.0.0:8080` hoặc cổng cố định khác. Cách giải quyết ưu tiên: dùng **OS-assigned port 0** hoặc network namespace/container riêng. Nếu buộc dùng cổng cố định cho hệ thống không hỗ trợ dynamic port, phải **reserve port và lock ở cấp host/orchestrator**, không chỉ gọi `isPortFree()` trước mỗi test.

### Lỗi 2 — Connection refused

~~~text
java.net.ConnectException: Connection refused
~~~

Chưa có process đang listen tại host/port mà client dùng, service chưa sẵn sàng, endpoint sai hoặc mapping chưa tồn tại. Đọc **actual bound/mapped port**, xác định network namespace, rồi chờ readiness theo deadline.

### Lỗi 3 — Timeout

Có thể do firewall, service không nhận request, DB lock, connection pool hoặc runner thiếu CPU. `read timeout` khác `connect timeout`; cần đo từ đâu bị chậm. **Không đổi cả timeout lên vô hạn**.

### Lỗi 4 — Localhost sai môi trường

Test chạy bên trong container A nhưng trỏ `localhost:5432` trong khi PostgreSQL chạy container B. `localhost` là container A, không phải B. Dùng Docker network service name/port bên trong network hoặc mapped host/port nếu chạy từ host; Testcontainers có `getHost()` và `getMappedPort()` sau startup.

### Lỗi 5 — Cổng được chọn rồi lại không bind được

Test dùng “find free port” bằng cách tạo socket, đóng ngay rồi khởi động server. Đây là race. Thay bằng **bind trực tiếp port 0** và truyền socket/port đã thực sự được server sử dụng, hoặc dùng framework random-port API.

## 19. Chẩn đoán lỗi database trên CI

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| `connection refused` | DB chưa start, sai hostname/mapped port. | Xem health, actual host/port và network namespace. |
| `password authentication failed` | Secret không được cấp, sai user/DB, quyền thiếu. | Xem CI secret injection và account **test**, không log password. |
| `database does not exist` | Tên DB/namespace sai hoặc setup chưa chạy. | Chứng minh setup tạo DB theo job trước khi test. |
| `relation/table does not exist` | Migration chưa hoàn tất hoặc đang dùng schema khác. | Kiểm tra schema version, search path, namespace và thứ tự setup. |
| Duplicate key/unique constraint ngẫu nhiên | Test dùng ID cố định hoặc dữ liệu cũ. | UUID riêng, fixture độc lập, cleanup theo owner. |
| Lock wait timeout/deadlock | Nhiều test mutate cùng rows/bảng. | Isolation, transaction boundary, giảm concurrency, phân tích query/locks. |
| Too many connections | Nhiều forks/jobs cùng mở pool hoặc leak connection. | Đóng JDBC resources, giảm đồng thời, giới hạn pool. |
| Test pass local fail CI | H2 khác engine production; image/schema/version khác. | Pin image/dependency, test DB engine thật, so môi trường. |
| Dữ liệu còn từ job trước | Cleanup bỏ sót, DB/schema dùng chung. | Namespace per job, TTL janitor, không xóa rộng. |
| Testcontainers không tìm thấy Docker | Runner thiếu Docker API/quyền. | Bật runtime được CI hỗ trợ hoặc chọn loại runner phù hợp; không cấp quyền tùy tiện. |
| Pull image timeout/quota | Registry/network/rate limits. | Mirror/cache registry được duyệt, pin tag/digest và giám sát. |

**Nếu lỗi lộ thông tin nhạy cảm:** đừng đính kèm nguyên connection string có password hoặc toàn bộ dump database vào ticket/chat. Redact trước khi chia sẻ.

## 20. Quan sát và báo cáo đúng cho Maven CI

Sau `mvn clean verify`, cần thu thập những thứ giúp chẩn đoán:

- Maven version và **JDK thực sự dùng** (`mvn --version`).
- Module, Failsafe/Surefire versions, goal và profile.
- Số test được phát hiện, passed/failed/skipped; lưu báo cáo `target/failsafe-reports` và `target/surefire-reports`.
- Resource owner/job ID (không nhạy cảm), DB engine/image version và readiness status.
- Actual endpoint port hoặc mapped port (khi policy cho phép), **không** ghi password.
- Thời gian setup, test, teardown, số kết nối, container startup latency.
- Root cause đầu tiên và kết quả cleanup sau test fail.

Maven Failsafe ghi báo cáo XML/text, CI có thể parse để hiển thị test failures. **Một file report tồn tại không tự chứng minh suite có số test mong muốn**; kiểm tra tổng số test và status.

### Quy trình chẩn đoán có thứ tự

1. Xem `mvn --version`, file POM của module và config/plugin versions.
2. Xác minh test class match **`*IT`** và Failsafe đã bind hai goal `integration-test`, `verify`.
3. Xem log phase: setup đã chạy? Service readiness báo gì? Failsafe test reports có test được chạy không?
4. Phân biệt **port bind** với **port mapping**; xác nhận địa chỉ từ đúng network namespace.
5. Xem DB namespace/schema/job ID, migration version, quyền tài khoản test.
6. Kiểm tra tài nguyên xuyên test: static state, schema dùng chung, fixed file, queue/topic/bucket.
7. Giảm Failsafe forkCount về 1, tắt Jupiter concurrent và Maven `-T` để phân lập race; **không coi đó là biện pháp sửa dứt điểm**.
8. Chạy lại với tài nguyên mới, không kế thừa dữ liệu cũ; giữ log chẩn đoán phù hợp.
9. Kiểm tra cleanup và orphan resources sau khi fail; không xóa tài nguyên của job khác.
10. Chỉ nâng concurrency sau khi tests độc lập và có metrics chứng minh lợi ích.

## 21. So sánh cleanup trong test và cleanup của CI

| Cấp | Cơ chế | Hoàn cảnh có hiệu lực | Trường hợp còn sót |
| --- | --- | --- | --- |
| Java/JUnit | `try-with-resources`, `try/finally`, `@AfterEach`, `@AfterAll` | Khi JVM còn sống và lifecycle callback chạy. | JVM bị kill, host chết, test không tới callback. |
| Testcontainers extension | Start/stop `@Container` theo scope | JVM/JUnit extension hoạt động bình thường và Docker đáp ứng. | Docker API gián đoạn, JVM bị kill, cleanup không hoàn tất. |
| Maven Failsafe | `integration-test`, `post-integration-test`, `verify` | Lifecycle tiếp tục sau test assertion failure. | Setup goal fail sớm, cancel/kill, hạ tầng đứt. |
| CI runner | Post-job/after-script hook | Runner còn có thể chạy cleanup. | Runner mất điện, policy không cho access, kill cưỡng bức. |
| Hạ tầng | TTL labels, janitor, lease expiry, quota | Có controller độc lập giám sát. | Cấu hình owner/TTL sai, controller ngừng hoặc thiếu quyền. |

**Cần kết hợp nhiều tầng.** Một `finally` tốt không thay thế TTL cho Docker resources. Một TTL tốt không thay thế cleanup nhanh vì container rác có thể chiếm CPU/RAM, làm job kế tiếp fail.

## 22. Lưu ý bảo mật và chi phí tài nguyên

### Không cho test phá môi trường ngoài

- Chỉ dùng database/queue/bucket **sandbox** có quyền rõ ràng.
- Đặt prefix, TTL và quota để tránh test tạo tài nguyên vô hạn.
- Không cho phép các lệnh xóa rộng trên Docker host dùng chung hoặc database ngoài namespace.
- Với dịch vụ trả phí, giới hạn rate/quota và kiểm soát số job concurrent.

### Dùng image và artifact có kiểm soát

Pin PostgreSQL image version phù hợp; để tái lập mạnh hơn có thể pin theo digest đã kiểm tra, thay vì tag biến đổi. Không tự đưa digest đoán vào POM/code. Lưu bộ phiên bản Java, Maven, plugin, database image và migration version trong báo cáo CI khi cần.

### Tránh log secrets

Failing test đôi khi làm framework in JDBC URL, HTTP headers hoặc environment. Cấu hình redaction cho CI, không gắn password vào URL/log messages. Giới hạn quyền đọc reports/artifacts, rotation nếu secret đã lộ.

### Tài nguyên không miễn phí

Một fork Failsafe tạo JVM mới; một container DB tạo process/volume/network mới. Nhiều modules/jobs concurrent làm tăng RAM, CPU, disk, I/O và pool connections. Đo trước khi tăng `-T`, forkCount hoặc mở nhiều Docker containers.

## 23. Mẫu quyết định chọn isolation

**Nếu test chỉ cần xác minh hàm thuần:** dùng unit test và mock; đừng mở database.

**Nếu cần xác minh giao thức TCP/HTTP:** dùng server thật trên loopback với port 0, hoặc random-port API của framework. Đảm bảo timeout, close và không có hardcoded port.

**Nếu cần xác minh JDBC/query cơ bản:** H2 in-memory hoặc database thử nghiệm riêng có thể là bước đầu; ghi rõ giới hạn SQL dialect/transaction behavior.

**Nếu cần xác minh PostgreSQL-specific behavior:** dùng PostgreSQL container/service thử nghiệm có phiên bản được chốt; lấy JDBC URL động, migration và readiness. Cô lập tài nguyên và cleanup.

**Nếu integration test tác động nhiều dịch vụ:** tạo môi trường riêng theo job/namespace khi có thể; nếu dùng staging chung, cần tenant/ID riêng và API cleanup theo owner.

**Nếu không thể tránh một tài nguyên độc quyền dùng chung:** xếp lịch test serial hoặc dùng lock/lease **ở cấp dịch vụ/hạ tầng**, có timeout và owner rõ ràng. JUnit `@ResourceLock` không đủ giữa nhiều JVM/máy.

**Nếu CI thiếu Docker:** tách test profile/runner theo capability, không mặc định skip toàn bộ kiểm thử tích hợp mà không thông báo. Build cần ghi rõ test nào chạy, test nào không.

## 24. Checklist trước khi chạy integration tests trên CI

1. **Xác định test scope**: unit tests ở Surefire, integration tests ở Failsafe, đặt tên class đúng.
2. **Pin Maven/JDK/Failsafe/Surefire versions** đã được CI kiểm chứng.
3. **Gọi `mvn clean verify`**, không kết thúc ở `integration-test`.
4. **Xác minh hai Failsafe goals** được bind và báo cáo test thực thi có số lượng kỳ vọng.
5. **Không hardcode host port**, dùng port 0 hoặc mapped port được runtime cấp.
6. **Không dùng localhost sai namespace** khi app và database ở container khác nhau.
7. **Chờ readiness có deadline**, không dùng `sleep` cố định thay health check.
8. **Tạo database/schema/tenant riêng** theo test/job hoặc container riêng khi có thể.
9. **Seed dữ liệu tối thiểu** và migration ở đúng DB/schema; tránh dữ liệu production.
10. **Close JDBC, sockets, threads** bằng try-with-resources/finally.
11. **Cleanup container/network/volume theo ownership**, không prune/xóa toàn cục.
12. **Có CI cleanup hook và TTL** để xử lý trường hợp Maven bị kill.
13. **Giới hạn concurrent forks/modules/jobs** dựa trên CPU/RAM/DB quota thực.
14. **Không dùng JUnit @ResourceLock thay lock liên process**.
15. **Không tự bật JUnit concurrent cho Testcontainers extension** khi chưa có hỗ trợ/chiến lược tương thích đã kiểm chứng.
16. **Dùng secret store và quyền tối thiểu**, không log/password trong URL báo cáo.
17. **Lưu reports và nguyên nhân lỗi** đã redacted, xác nhận cleanup sau khi fail.
18. **Định kỳ thử failure paths**: database không sẵn sàng, port bị chiếm, test timeout, CI cancel và secret không được cấp.
19. **Giữ metric** về thời gian setup, test, cleanup và orphan resources sau job.
20. **Chỉ công bố “CI xanh” khi test thực sự chạy** theo danh sách bắt buộc, không phải do `skipITs` hoặc test discovery sai.

## 25. Bài tập thực hành

**Bài 1 — baseline không Docker.** Tạo đầy đủ POM và ba file test cùng `StatusEndpoint.java` ở mục 5. Chạy `mvn clean verify`, xác nhận Surefire chạy 1 unit test và Failsafe chạy 2 integration tests. Đọc báo cáo chứ không suy luận từ log tổng.

**Bài 2 — cổng động.** Chạy `TcpPortIT` nhiều lần, quan sát `getLocalPort()` nếu cần log số cổng, nhưng **không assert cổng cố định**. Giải thích vì sao bind port 0 an toàn hơn mô hình “tìm port trống rồi đóng socket”.

**Bài 3 — JDBC isolation.** Thay UUID bằng một tên DB cố định trong **bản sao thử nghiệm** rồi chạy hai test tương tác cùng DB; thảo luận nguy cơ trùng bảng khi hai test cùng chạy. Khôi phục UUID và xác minh tài nguyên đóng đúng.

**Bài 4 — chạy phase đúng.** So sánh `mvn test`, `mvn integration-test` và `mvn verify`: mục nào chạy Surefire, mục nào chạy Failsafe, mục nào thực thi `post-integration-test` và goal xác nhận IT result?

**Bài 5 — Docker có điều kiện.** Trên runner được cấp Docker API, thêm ba dependency Testcontainers/PostgreSQL ở mục 8 và `PostgresIT`. So sánh `getJdbcUrl()` với giả định `localhost:5432`; đọc kết quả của Failsafe reports.

**Bài 6 — xung đột CI.** Giả lập hai job cùng muốn dùng DB tên `test`, host port 8080 và thư mục `/tmp/integration-test`. Thiết kế namespace/port/volume riêng, cleanup theo owner và TTL cho trường hợp bị cancel.

**Bài 7 — giới hạn tài nguyên.** Với một môi trường nhiều module, vẽ các lớp song song CI jobs × Maven -T × Failsafe forks × JUnit workers. Đặt giới hạn thử nghiệm rồi so CPU/RAM/DB connections; không suy ra số đồng thời từ một cấu hình duy nhất.

**Bài 8 — sự cố và cleanup.** Cố ý làm assertion fail ở một IT không chứa dữ liệu nhạy cảm, chạy `mvn verify` và xác nhận Failsafe báo failure sau khi các bước cleanup được thực hiện theo lifecycle đã cấu hình. Sau đó thảo luận trường hợp runner bị kill và cơ chế TTL/janitor cần bổ sung.

### Tổng kết

**Integration tests trên CI phải quản lý tài nguyên như một phần của hợp đồng kiểm thử**, không phải chi tiết môi trường để bỏ mặc. Với cổng TCP, ưu tiên **bind port 0** và dùng cổng đã cấp; với container, dùng **actual host/mapped port**; với database, dùng **instance/schema/tenant riêng** và cleanup có ownership. Readiness, timeout và secret management là một phần của chất lượng test.

Trong Maven, **Surefire phục vụ unit tests; Failsafe phục vụ integration tests và nên được gọi qua `mvn verify`** để phase dọn dẹp có cơ hội chạy trước khi kết quả test bị đánh fail. `@ResourceLock` không thay thế isolation xuyên JVM/CI jobs; Testcontainers JUnit 5 không mặc nhiên an toàn với parallel execution. Chọn mức đồng thời từ khả năng hạ tầng và độ độc lập của test, không chỉ vì cần rút thời gian build.

### Tài liệu chính thức

- [Apache Maven Failsafe Plugin — Introduction and lifecycle](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Apache Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
- [Apache Maven Failsafe Plugin — JUnit Platform integration](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/junit-platform.html)
- [Apache Maven Failsafe Plugin — integration-test goal parameters](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Apache Maven Surefire Plugin — Usage](https://maven.apache.org/surefire/maven-surefire-plugin/usage.html)
- [Testcontainers for Java — JUnit 5 extension](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers for Java — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/)
- [Testcontainers for Java — Networking](https://java.testcontainers.org/features/networking/)
- [Testcontainers for Java — Waiting Strategies](https://java.testcontainers.org/features/startup_and_waits/)
- [JUnit 5.10.2 — TempDir API](https://docs.junit.org/5.10.2/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDir.html)
- [Oracle Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
