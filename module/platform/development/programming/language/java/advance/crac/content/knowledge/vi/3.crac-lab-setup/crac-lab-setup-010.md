# Cấu trúc dự án mẫu và lệnh chạy có thể tái lập

Khi thực hành CRaC (Coordinated Restore at Checkpoint), kết quả phụ thuộc vào cả mã nguồn ứng dụng và môi trường chạy. Một dự án có thể build thành công trên JDK thông thường nhưng không tạo được checkpoint nếu JDK không hỗ trợ CRaC hoặc Linux host thiếu điều kiện cho CRIU. Tương tự, checkpoint tạo được trên một máy chưa chắc restore được trên máy khác có kiến trúc, kernel hoặc bản JDK khác.

Bài này xây dựng một dự án Java nhỏ để quan sát đầy đủ vòng đời: build ứng dụng, chạy server, chuẩn bị tài nguyên trước checkpoint, tạo checkpoint, restore và kiểm tra server hoạt động trở lại. Ví dụ dùng Maven, Java 21 và HTTP server có sẵn trong JDK để tập trung vào CRaC API, không phụ thuộc framework web.

## 1. Mục tiêu và điều kiện thực hành

Dự án mẫu cần chứng minh được bốn việc:

1. Cùng một source code tạo ra một artifact có thể build lại bằng các phiên bản công cụ đã khóa.
2. Ứng dụng đăng ký tài nguyên với CRaC thông qua `org.crac.Resource`.
3. Callback `beforeCheckpoint` giải phóng tài nguyên cần đóng; callback `afterRestore` tạo lại tài nguyên cần hoạt động sau restore.
4. Sau khi restore, endpoint HTTP phản hồi bình thường mà không phải chạy lại toàn bộ quá trình khởi động ứng dụng.

### 1.1. Môi trường

| Thành phần | Yêu cầu |
|---|---|
| Hệ điều hành | Linux có hỗ trợ checkpoint/restore của CRIU |
| JDK | Bản phân phối JDK có tích hợp CRaC; ví dụ này dùng Java 21 |
| Maven | Maven Wrapper với phiên bản được khóa trong dự án |
| CRIU | Được cài đặt và vượt qua bước kiểm tra trên chính môi trường chạy |
| Quyền hệ điều hành | Đủ capability/quyền mà CRIU và kernel yêu cầu |
| Kiến trúc | Ghi nhận rõ kiến trúc CPU và dùng nhất quán khi checkpoint/restore |

JDK 21 thông thường không đồng nghĩa với JDK 21 có CRaC. Hãy kiểm tra bản phân phối và build cụ thể trước khi chạy. Khi khởi động, nếu JVM báo không nhận diện được tùy chọn `-XX:CRaCCheckpointTo`, nhiều khả năng đang dùng JDK không có CRaC.

CRaC checkpoint/restore dựa vào cơ chế của Linux và CRIU. Trên máy Windows hoặc macOS, hãy sử dụng một Linux host hoặc VM/container có kernel và quyền cần thiết. Với WSL2 hoặc Docker Desktop, chỉ tiếp tục khi CRIU thực sự vượt qua kiểm tra trong môi trường đó; việc cài CRIU vào filesystem chưa chứng minh kernel hỗ trợ đầy đủ.

Kiểm tra trước khi build:

```bash
java -version
javac -version
./mvnw -version
criu --version
criu check
uname -a
uname -m
```

Các lệnh `criu` và `uname` chạy trong Linux environment sẽ dùng để checkpoint. Nếu `criu check` thất bại, cần xử lý quyền, capability, kernel hoặc cấu hình container trước khi điều tra mã Java.

## 2. Cấu trúc dự án

Dự án ví dụ có tên `crac-demo`. Cấu trúc thư mục:

```text
crac-demo/
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
├── mvnw
├── mvnw.cmd
├── pom.xml
├── .gitignore
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   └── crac/
│                       ├── Application.java
│                       └── HttpServerResource.java
└── target/                         # sinh ra khi build; không commit
    ├── crac-demo-1.0.0.jar
    └── crac-checkpoint/            # sinh ra khi checkpoint; không commit
```

Vai trò từng thành phần:

- `pom.xml`: khóa phiên bản Java, CRaC API và các Maven plugin.
- `.mvn/wrapper/`, `mvnw`, `mvnw.cmd`: giúp mọi máy dùng cùng phiên bản Maven.
- `Application.java`: điểm bắt đầu của ứng dụng, tạo resource và giữ tiến trình hoạt động.
- `HttpServerResource.java`: sở hữu HTTP server và đăng ký callback với CRaC.
- `target/`: chứa artifact build và checkpoint cục bộ. Đây là dữ liệu phát sinh theo môi trường, không đưa vào Git.

### 2.1. Maven Wrapper

Commit các file Maven Wrapper vào repository để người khác không phải tự chọn một phiên bản Maven. File `.mvn/wrapper/maven-wrapper.properties` cần trỏ đến một bản Maven cố định, ví dụ:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
```

Các file `mvnw`, `mvnw.cmd` và wrapper JAR/properties phải được tạo bằng Maven Wrapper và commit cùng dự án. Không thay URL bằng `LATEST`, phiên bản động hoặc snapshot. Nếu tổ chức yêu cầu xác minh checksum Maven distribution, thêm `distributionSha256Sum` lấy từ checksum chính thức của đúng bản Maven đã chọn.

## 3. Khai báo build và CRaC API

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>crac-demo</artifactId>
    <version>1.0.0</version>
    <name>CRaC Demo</name>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <crac.version>1.4.0</crac.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.crac</groupId>
            <artifactId>crac</artifactId>
            <version>${crac.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.crac.Application</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Dependency `org.crac:crac` cung cấp API để source code tham chiếu `Core`, `Context` và `Resource`. Phiên bản trong ví dụ được khai báo tường minh để các lần build không tự thay đổi theo phiên bản mới trên Maven repository. Runtime thực hiện checkpoint vẫn phải là JDK có hỗ trợ CRaC và tương thích với API được ứng dụng biên dịch.

Có thể bỏ qua Maven Wrapper nếu chỉ thử nghiệm nhanh bằng Maven đã cài, nhưng kết quả khi đó phụ thuộc phiên bản Maven trên máy. Với bài thực hành có thể chia sẻ, hãy dùng `./mvnw` trên Linux hoặc `mvnw.cmd` trên Windows cho bước build thông thường.

## 4. Viết ứng dụng mẫu

### 4.1. Điểm bắt đầu Application

Tạo file `src/main/java/com/example/crac/Application.java`:

```java
package com.example.crac;

import java.util.concurrent.CountDownLatch;

public final class Application {

    private Application() {
    }

    public static void main(String[] args) throws Exception {
        int port = Integer.getInteger("server.port", 8080);

        new HttpServerResource(port);

        System.out.println("READY: HTTP server listening on port " + port);

        // Giữ tiến trình sống để có thể gửi lệnh JDK.checkpoint.
        new CountDownLatch(1).await();
    }
}
```

Ứng dụng tạo một `HttpServerResource`, sau đó chờ vô hạn để tiến trình tiếp tục hoạt động. Đây là cách giữ ví dụ nhỏ gọn; trong ứng dụng thực tế, các thread phục vụ request và các thành phần runtime khác thường đã giữ tiến trình hoạt động.

### 4.2. Resource quản lý HTTP server

Tạo file `src/main/java/com/example/crac/HttpServerResource.java`:

```java
package com.example.crac;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class HttpServerResource implements Resource {

    private final int port;

    private HttpServer server;
    private ExecutorService executor;

    public HttpServerResource(int port) throws IOException {
        this.port = port;

        // Đăng ký resource để JVM gọi hai callback của CRaC.
        Core.getGlobalContext().register(this);

        startServer();
    }

    private synchronized void startServer() throws IOException {
        if (server != null) {
            return;
        }

        HttpServer newServer =
                HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
        ExecutorService newExecutor =
                Executors.newVirtualThreadPerTaskExecutor();

        newServer.setExecutor(newExecutor);
        newServer.createContext("/health", this::handleHealth);
        newServer.createContext("/", this::handleHome);
        newServer.start();

        executor = newExecutor;
        server = newServer;

        System.out.println("HTTP server started on port " + port);
    }

    private void handleHealth(HttpExchange exchange) throws IOException {
        reply(exchange, "OK\n");
    }

    private void handleHome(HttpExchange exchange) throws IOException {
        reply(exchange, "Hello from the CRaC demo\n");
    }

    private static void reply(HttpExchange exchange, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, bytes.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        System.out.println("beforeCheckpoint: stopping HTTP server");

        if (server != null) {
            // Ngừng nhận kết nối mới và cho exchange hiện tại thời gian kết thúc.
            server.stop(1);
            server = null;
        }

        if (executor != null) {
            executor.shutdown();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }

            executor = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        System.out.println("afterRestore: starting HTTP server");
        startServer();
    }
}
```

Điểm chính của ví dụ nằm ở vòng đời resource:

- Constructor đăng ký object với `Core.getGlobalContext().register(this)`, sau đó mở HTTP server.
- `beforeCheckpoint` dừng server và executor trước khi JVM tạo checkpoint. Điều này tránh lưu một listener socket đang mở vào trạng thái cần khôi phục.
- `afterRestore` tạo server và executor mới để tiến trình nhận request trở lại.
- Hai callback được đồng bộ hóa để tránh việc start/stop đồng thời trên cùng resource.

Đây là ví dụ cho một HTTP server nhỏ. Ứng dụng thực tế còn phải xử lý request đang chạy, connection pool, database connection, message consumer, scheduler, thread riêng, file handle và các tài nguyên phụ thuộc thời gian. Không nên sao chép nguyên callback này cho mọi thư viện; hãy dùng lifecycle API của thư viện tương ứng và bảo đảm resource được đóng/mở đúng thứ tự.

## 5. Cấu hình file và build artifact

Tạo `.gitignore`:

```gitignore
/target/
/checkpoint/
*.hprof
hs_err_pid*
```

Checkpoint thường chứa trạng thái bộ nhớ của ứng dụng tại thời điểm chụp. Nó có thể lớn, phụ thuộc môi trường và chứa dữ liệu runtime. Giữ checkpoint ở vùng lưu trữ thực hành cục bộ; không đưa nó vào Git như một artifact portable.

Build từ thư mục gốc dự án:

```bash
./mvnw -B -ntp clean verify
```

Kết quả mong đợi là:

```text
target/crac-demo-1.0.0.jar
```

Kiểm tra manifest và dependency tree khi cần xác nhận main class và phiên bản API:

```bash
unzip -p target/crac-demo-1.0.0.jar META-INF/MANIFEST.MF
./mvnw -B -ntp dependency:tree
```

Lệnh `clean` xóa thư mục `target` cũ trước build, giúp tránh nhầm artifact hoặc checkpoint từ lần thực hành trước. Không đổi JDK giữa bước build và bước chạy nếu chưa chủ động kiểm tra tương thích bytecode, API và CRaC runtime.

## 6. Chạy ứng dụng bình thường trước khi checkpoint

Trước tiên có thể chạy ứng dụng mà không yêu cầu checkpoint để kiểm tra endpoint:

```bash
java -jar target/crac-demo-1.0.0.jar
```

Mở terminal khác:

```bash
curl --fail --show-error http://127.0.0.1:8080/health
curl --fail --show-error http://127.0.0.1:8080/
```

Kết quả mong đợi:

```text
OK
Hello from the CRaC demo
```

Dừng tiến trình thử nghiệm này trước khi chạy bài checkpoint. Nếu để tiến trình cũ tiếp tục giữ port 8080, lần chạy tiếp theo có thể gặp lỗi `Address already in use`.

Việc endpoint hoạt động trên JDK thông thường chỉ kiểm tra ứng dụng và HTTP handler. Nó chưa chứng minh môi trường có thể checkpoint/restore. Bước tiếp theo phải dùng đúng CRaC-enabled JDK.

## 7. Tạo checkpoint

### 7.1. Khởi động bằng CRaC-enabled JDK

Từ thư mục dự án, chọn một đường dẫn checkpoint mới cho lần chạy này:

```bash
java -XX:CRaCCheckpointTo="$PWD/target/crac-checkpoint" \
     -jar target/crac-demo-1.0.0.jar
```

Giữ terminal này mở. Ứng dụng phải in thông báo server đã sẵn sàng. Dùng một terminal khác, cùng user và cùng JDK, tìm PID:

```bash
jcmd -l
```

Chọn PID của `com.example.crac.Application` hoặc tiến trình JAR tương ứng. Gửi lệnh checkpoint:

```bash
jcmd <PID> JDK.checkpoint
```

Thay `<PID>` bằng số PID thật. JVM gọi các resource callback đã đăng ký; trong ví dụ, log `beforeCheckpoint` xuất hiện và HTTP server được dừng trước khi checkpoint hoàn tất.

Không gọi trực tiếp `criu dump` để thay thế lệnh này. CRaC-enabled JDK phối hợp checkpoint với JVM, bao gồm callback và các xử lý runtime cần thiết.

### 7.2. Kiểm tra kết quả checkpoint

Sau khi lệnh hoàn tất, kiểm tra thư mục `target/crac-checkpoint` có dữ liệu checkpoint. Cách bố trí file cụ thể phụ thuộc JDK/CRIU và không nên giả định chỉ có một file duy nhất.

Một lần chạy mới nên dùng thư mục checkpoint mới. Không trộn file từ nhiều lần checkpoint vào cùng một thư mục. Nếu cần chạy lại từ đầu, build bằng `clean` để loại bỏ `target` cũ rồi tạo checkpoint mới.

## 8. Restore tiến trình

Restore bằng chính CRaC-enabled JDK đã tạo checkpoint:

```bash
java -XX:CRaCRestoreFrom="$PWD/target/crac-checkpoint"
```

Lệnh restore khởi tạo JVM từ trạng thái checkpoint. Khi resource callback được gọi, `afterRestore` tạo HTTP server mới trên port 8080.

Kiểm tra endpoint từ terminal khác:

```bash
curl --fail --show-error http://127.0.0.1:8080/health
curl --fail --show-error http://127.0.0.1:8080/
```

Nếu trả về `OK` và `Hello from the CRaC demo`, server đã nhận request sau restore. Có thể gửi nhiều request liên tiếp để xác nhận listener vẫn hoạt động:

```bash
for i in 1 2 3 4 5; do
    curl --fail --silent http://127.0.0.1:8080/health
done
```

Không khởi chạy một bản ứng dụng mới trên cùng port trong lúc đang restore. Khi restore thất bại, hãy đọc log của JVM và CRIU để xác định checkpoint đã được đọc đến đâu, callback nào đã chạy và tài nguyên nào không khôi phục được.

## 9. Tổ chức lệnh để lần chạy sau tái lập được

Không nên phụ thuộc vào trí nhớ về các lệnh đã gõ trong terminal. Lưu lệnh thực hành vào README hoặc script của repository để người khác có thể chạy theo cùng trình tự.

Một quy trình chuẩn có thể được ghi thành các bước:

```text
1. Xác nhận Linux, kernel, CRIU và quyền checkpoint.
2. Chọn đúng CRaC-enabled JDK.
3. Ghi lại phiên bản công cụ và Git commit.
4. ./mvnw clean verify
5. Chạy JAR với -XX:CRaCCheckpointTo=<checkpoint-dir>.
6. Tìm PID bằng jcmd -l.
7. Gửi jcmd <PID> JDK.checkpoint.
8. Restore với -XX:CRaCRestoreFrom=<checkpoint-dir>.
9. Gọi /health và kiểm tra log afterRestore.
```

Để lưu bằng chứng môi trường trước khi checkpoint, có thể tạo file `target/environment.txt`:

```bash
{
    date -u
    git rev-parse HEAD
    uname -a
    uname -m
    java -version 2>&1
    ./mvnw -version
    criu --version
    sha256sum target/crac-demo-1.0.0.jar
} > target/environment.txt
```

Nếu build không nằm trong Git repository thì bỏ dòng `git rev-parse HEAD` hoặc thay bằng mã phiên bản source mà nhóm đang sử dụng. Lưu cả log build, log checkpoint và log restore khi cần so sánh nhiều lần thực nghiệm.

## 10. Khóa các yếu tố ảnh hưởng đến khả năng tái lập

Một lệnh giống nhau chưa bảo đảm checkpoint giống nhau. Hãy ghi lại và kiểm soát các yếu tố sau:

| Yếu tố | Cách ghi nhận hoặc khóa |
|---|---|
| Source code | Git commit hoặc tag cụ thể |
| Java | Vendor, version, build number và kiến trúc |
| Maven | Phiên bản Maven Wrapper và wrapper distribution URL |
| Dependency | Phiên bản dependency/plugin tường minh; lưu dependency tree |
| CRIU | Phiên bản và kết quả `criu check` |
| Linux | Distribution, kernel version, kiến trúc và capability |
| Cấu hình app | Port, biến môi trường, JVM options và file cấu hình |
| Artifact | SHA-256 của JAR sau build |
| Checkpoint path | Đường dẫn tuyệt đối và filesystem được dùng |

### 10.1. Cùng JDK build

Dùng cùng vendor, version và build của JDK cho cả checkpoint lẫn restore. Chỉ ghi “Java 21” là chưa đủ vì các bản phân phối có thể khác patch level, cách tích hợp CRaC hoặc cấu hình native. Lệnh `java -version` cần được lưu nguyên văn.

### 10.2. Cùng môi trường Linux

Checkpoint có thể phụ thuộc kernel, kiến trúc CPU, CRIU, filesystem, network namespace và các capability được cấp cho tiến trình. Vì vậy, không xem checkpoint là file JAR có thể mang sang máy bất kỳ để chạy. Hãy tạo và restore trong môi trường tương thích đã được xác định.

Nếu chạy trong container, ghi lại image digest thay vì chỉ ghi tag có thể thay đổi. Đảm bảo checkpoint directory nằm trên filesystem được phép và có cùng đường dẫn khi restore. Các mount, port, network namespace và quyền truy cập cần phù hợp với trạng thái lúc tạo checkpoint.

### 10.3. Cùng artifact và cấu hình

Build từ source commit đã chọn, ghi checksum JAR và giữ nguyên JVM options. Thay đổi biến môi trường, system property, thư viện native hoặc file cấu hình có thể làm hành vi sau restore khác với lần thử trước.

Không dùng dependency version dạng `LATEST`, version range hoặc snapshot cho một bài thực hành cần tái lập. Khóa Maven plugin và dependency trực tiếp; khi cần kiểm soát sâu hơn, lưu dependency tree và checksum các artifact đã resolve.

### 10.4. Checkpoint là đầu ra của một trạng thái runtime

Ngay cả khi code và công cụ giống nhau, dữ liệu đang nằm trong heap có thể khác do workload, thứ tự request, thời điểm warm-up hoặc cache. Vì thế cần cố định workload chuẩn bị, thứ tự gọi endpoint, thời gian chờ và điều kiện dừng request trước checkpoint.

Nếu mục tiêu là so sánh thời gian restore, hãy chạy cùng kịch bản warm-up và cùng số lượng request. Ghi rõ checkpoint được tạo sau bao lâu và ứng dụng đã xử lý loại request nào.

## 11. Một số lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| `Unrecognized VM option 'CRaCCheckpointTo'` | Đang dùng JDK không hỗ trợ CRaC hoặc sai build | Xác nhận `JAVA_HOME`, `java -version` và đường dẫn `jcmd` |
| `criu check` thất bại | Kernel, quyền, capability hoặc cấu hình container chưa phù hợp | Kiểm tra trên đúng Linux host/container; xử lý điều kiện hệ điều hành trước |
| `Operation not permitted` | Tiến trình thiếu quyền/capability checkpoint cần thiết | Kiểm tra user, container runtime và capability được cấp |
| `Address already in use` sau restore hoặc lúc start | Tiến trình cũ hoặc listener khác đang giữ port | Xác định PID và trạng thái listener trước khi chạy lại |
| Không thấy log `afterRestore` | Restore chưa tới callback, resource chưa đăng ký hoặc restore thất bại trước đó | Đọc log JVM/CRIU và kiểm tra đăng ký resource |
| Endpoint không phản hồi sau restore | Callback không mở lại server, sai port hoặc namespace mạng | Kiểm tra log `afterRestore`, port bind và network namespace |
| Build không tìm thấy `org.crac` | Thiếu dependency hoặc Maven không resolve được repository | Kiểm tra dependency trong POM và dependency tree |
| Restore lỗi khi đổi máy | Khác JDK, kernel, kiến trúc, filesystem hoặc môi trường native | Quay lại môi trường tương thích đã tạo checkpoint |

Khi điều tra, tách lỗi thành ba lớp: build artifact, checkpoint của JVM/CRIU và khởi tạo resource sau restore. Một JAR build thành công không chứng minh checkpoint thành công; checkpoint được tạo cũng không chứng minh ứng dụng đã sẵn sàng phục vụ request sau restore.

## 12. Mở rộng dự án cho ứng dụng thực tế

Sau khi ví dụ HTTP server hoạt động, có thể thêm từng loại resource vào cùng cấu trúc dự án:

- **Database pool**: đóng pool trước checkpoint; tạo pool mới và kiểm tra kết nối sau restore.
- **HTTP client**: xử lý connection pool và socket đang mở theo lifecycle của client.
- **Message consumer**: dừng nhận message, xử lý hoặc hoàn tác message đang dở dang, sau đó subscribe lại.
- **Scheduler**: tạm dừng job, tránh chạy trùng hoặc bỏ sót lịch khi restore.
- **Cache**: xác định cache nào có thể giữ lại, cache nào cần refresh vì dữ liệu có thời hạn.
- **Credential/token**: kiểm tra hạn sử dụng và làm mới nếu token không còn hợp lệ sau thời gian checkpoint.

Mỗi resource nên có một chủ sở hữu rõ ràng, một cách đóng trước checkpoint và một cách khôi phục sau restore. Callback cần idempotent khi phù hợp: gọi lại trong tình huống retry không được tạo nhiều pool, nhiều listener hoặc nhiều scheduler trùng nhau.

Khi đưa vào Spring Boot, có thể đăng ký resource thông qua bean quản lý vòng đời hoặc một thành phần khởi tạo chuyên biệt. Không nên chỉ dựa vào việc Spring context còn tồn tại trong heap để kết luận mọi connection, socket và thread do bean quản lý đều còn hợp lệ sau restore.

## 13. Tiêu chí xác nhận một lần thực hành

Một lần chạy có thể xem là tái lập được khi người khác có thể lấy đúng source commit, dùng đúng JDK/Maven/CRIU và môi trường Linux đã ghi nhận, sau đó thực hiện lại toàn bộ lệnh mà không cần sửa source hoặc đoán cấu hình.

Các bằng chứng tối thiểu nên được lưu:

- Git commit của source và checksum JAR.
- Phiên bản JDK đầy đủ, Maven Wrapper và CRIU.
- Thông tin Linux kernel, kiến trúc và kết quả `criu check`.
- Lệnh khởi động có `CRaCCheckpointTo` và lệnh `JDK.checkpoint`.
- Log callback `beforeCheckpoint` và `afterRestore`.
- Kết quả gọi endpoint trước checkpoint và sau restore.
- Đường dẫn checkpoint và cấu hình cần thiết để restore trong cùng môi trường.

Khi đã có các bằng chứng này, có thể thay đổi từng yếu tố một — chẳng hạn JDK build, cấu hình warm-up hoặc loại resource — để đánh giá ảnh hưởng. Giữ nguyên các yếu tố còn lại giúp kết quả so sánh có ý nghĩa và giúp xác định lỗi thuộc source code, JVM, CRIU hay môi trường triển khai.

