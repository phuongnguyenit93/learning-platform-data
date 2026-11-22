# Đóng gói và khôi phục ứng dụng trong container Linux

Đóng gói một ứng dụng Java dùng CRaC (Coordinated Restore at Checkpoint) trong container Linux cần chuẩn bị cả application image lẫn môi trường có khả năng checkpoint và restore tiến trình. Container image chứa ứng dụng, JDK có CRaC support và thư viện hệ thống. Checkpoint được tạo khi ứng dụng đang chạy, lưu trạng thái tiến trình cùng các file ảnh cần thiết, sau đó được khôi phục bằng đúng JDK và cơ chế CRaC tương thích.

Bài thực hành này xây dựng một HTTP server Java nhỏ, đóng gói nó vào container Linux, tạo checkpoint, rồi khôi phục ứng dụng từ checkpoint. Trong quá trình đó, bạn sẽ kiểm tra CRIU trên Linux host, cấu hình volume lưu checkpoint, xử lý listener mạng qua callback CRaC, xác minh ứng dụng sau restore và nhận biết những giới hạn khi chuyển checkpoint giữa các container hoặc node.

Có một điểm cần phân biệt ngay từ đầu: **JDK CRaC checkpoint** phối hợp callback của Java Resource với cơ chế checkpoint/restore tiến trình. Tính năng **Docker container checkpoint** cũng có thể dùng CRIU nhưng là một cơ chế ở tầng container runtime với lifecycle khác. Hai cách này không thể thay thế lẫn nhau chỉ bằng cách đổi tên lệnh.

## 1. Mục tiêu và kiến trúc bài thực hành

Sau khi hoàn thành, bạn sẽ có thể:

- Xây dựng một JAR có đăng ký CRaC Resource.
- Chạy ứng dụng bằng JDK Linux có CRaC support.
- Chuẩn bị Linux host và CRIU để checkpoint/restore.
- Lưu checkpoint ở volume riêng, không trộn với application image.
- Dùng callback trước checkpoint để dừng listener và worker.
- Tạo checkpoint bằng công cụ của JDK.
- Khởi động lại ứng dụng từ checkpoint theo cơ chế được JDK cung cấp.
- Kiểm tra endpoint HTTP và log để xác nhận restore.
- Đóng gói metadata để biết checkpoint được tạo từ image/JDK nào.

Mô hình tổng quát:

~~~text
Source code + CRaC API
        |
        v
Gradle build
        |
        v
Application JAR
        |
        v
Linux container image
  - CRaC-enabled JDK
  - application JAR
  - native dependencies
        |
        v
Run and warm up application
        |
        v
JDK CRaC checkpoint command
        |
        v
Checkpoint directory on persistent volume
        |
        v
Compatible Linux restore environment
        |
        v
JDK CRaC restore
        |
        v
afterRestore callbacks
        |
        v
HTTP server ready
~~~

Checkpoint không phải một lớp cache có thể copy tùy ý sang mọi image. Nó là trạng thái của một tiến trình cụ thể, gắn với JDK, native runtime, kernel, CPU, namespace và các tài nguyên mà tiến trình đang sử dụng. Hãy dùng cùng image digest và một restore environment đã được xác nhận tương thích trong suốt bài thực hành.

## 2. Chuẩn bị môi trường Linux

Bài thực hành cần một Linux host hoặc Linux VM có kernel và quyền hệ thống phù hợp. Có thể dùng một máy Linux riêng hoặc môi trường ảo hóa có hỗ trợ các tính năng cần thiết của CRIU.

Các thành phần cần có:

| Thành phần | Vai trò |
|---|---|
| Linux kernel | Cung cấp process, memory, namespace và checkpoint-related features |
| CRIU | Dump/restore trạng thái tiến trình ở cấp hệ điều hành |
| Docker Engine hoặc runtime tương đương | Chạy container với cấu hình cần thiết |
| CRaC-enabled JDK | Cung cấp CRaC API và lệnh checkpoint/restore |
| Gradle | Build application JAR |
| curl | Gửi request kiểm tra HTTP |
| Persistent volume/directory | Lưu checkpoint files ngoài writable layer của container |

### 2.1. Kiểm tra kernel và kiến trúc

Chạy trên Linux host:

~~~bash
uname -a
uname -r
uname -m
cat /etc/os-release
lscpu
~~~

Ghi lại kernel release, architecture và CPU feature. Checkpoint tạo trên x86-64 cần được restore trong môi trường tương thích với kiến trúc và các ràng buộc CPU của JDK/CRIU. Không dùng một checkpoint x86-64 cho ARM64 chỉ vì cả hai host đều chạy Linux.

### 2.2. Kiểm tra CRIU

Cài CRIU theo package manager của distribution hoặc theo hướng dẫn chính thức của nền tảng. Sau đó chạy:

~~~bash
criu --version
sudo criu check
~~~

Lệnh `criu check` kiểm tra một số khả năng của kernel và quyền hiện tại. Kết quả thành công là điều kiện ban đầu, không phải bằng chứng rằng mọi workload Java đều có thể restore. Cần thử với đúng container, JDK, namespace và resource của ứng dụng.

Nếu lệnh báo thiếu capability hoặc kernel feature, hãy kiểm tra log và cấu hình host. Các yêu cầu có thể khác theo kernel và phiên bản CRIU; không nên đoán rằng một container image mới hơn sẽ tự bổ sung khả năng còn thiếu của host kernel.

### 2.3. Docker Desktop, WSL2 và máy Linux từ xa

Container trên Linux dùng chung kernel với host. Vì vậy, việc Docker CLI chạy được trên Windows hoặc macOS không có nghĩa môi trường đó có đủ tính năng CRIU để thực hiện bài lab.

Nếu dùng Windows, hãy chạy phần checkpoint/restore bên trong một Linux VM hoặc một Linux host được hỗ trợ. WSL2 hoặc Docker Desktop chỉ phù hợp khi kernel, quyền, namespace và tích hợp container runtime thực tế đáp ứng yêu cầu của CRaC/CRIU. Kiểm tra `criu check` trong môi trường Linux nơi tiến trình sẽ được checkpoint.

### 2.4. Kiểm tra Docker Engine

~~~bash
docker version
docker info
~~~

Cần xác định phiên bản Docker Engine và cách daemon được cấu hình. Nếu dùng rootless container, user namespace hoặc một runtime Kubernetes, yêu cầu quyền và cách restore có thể khác đáng kể so với Docker Engine chạy rootful trên Linux.

## 3. Tạo cấu trúc project

Tạo một project nhỏ:

~~~text
crac-container-lab/
├── build.gradle
├── settings.gradle
├── Dockerfile
├── .dockerignore
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── CracHttpApp.java
~~~

Thư mục checkpoint sẽ được tạo riêng khi chạy container. Không đưa checkpoint vào JAR hoặc đóng gói nó thành một phần cố định của image nếu mục tiêu là quản lý image và checkpoint như hai artifact có vòng đời khác nhau.

### 3.1. settings.gradle

~~~groovy
rootProject.name = 'crac-container-lab'
~~~

### 3.2. build.gradle

Ví dụ dùng Java 21 và CRaC API. Phiên bản API phải tương thích với JDK CRaC distribution mà bạn chọn; hãy xác nhận phiên bản artifact trong repository và tài liệu của distribution trước khi khóa phiên bản cho production.

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.crac:crac:1.4.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'com.example.CracHttpApp'
        )
    }
}
~~~

Nếu JDK CRaC của bạn cung cấp API theo một dependency version khác, cập nhật dependency tương ứng. Không nên chọn JDK chỉ theo major version; cần dùng đúng distribution/build đã được kiểm thử với CRaC.

### 3.3. .dockerignore

~~~text
.gradle
build/tmp
.git
.idea
.vscode
*.iml
checkpoint
~~~

Không đưa thư mục checkpoint vào Docker build context. Điều này tránh vô tình copy memory image vào application image, làm image phình lớn và trộn lẫn hai artifact có lifecycle khác nhau.

## 4. Viết ứng dụng Java có CRaC Resource

Ứng dụng sẽ mở một HTTP server trên port 8080. Trước checkpoint, nó dừng listener và executor để không giữ socket hoặc worker đang hoạt động trong trạng thái cần khôi phục. Sau restore, callback tạo listener và executor mới.

Trong production, cần drain request đang chạy và đóng các client khác như JDBC, Redis, HTTP hoặc message broker theo đúng contract của từng thư viện. Bài lab dùng HTTP server để minh họa vòng đời resource.

Tạo file **src/main/java/com/example/CracHttpApp.java**:

~~~java
package com.example;

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

public final class CracHttpApp implements Resource {

    private final int port;

    private volatile HttpServer server;
    private volatile ExecutorService requestExecutor;

    private static CracHttpApp application;

    public CracHttpApp(int port) throws Exception {
        this.port = port;

        Core.getGlobalContext().register(this);
        startListener();
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        System.out.println("CRAC beforeCheckpoint: stopping HTTP listener");
        stopListener();
        System.out.println("CRAC beforeCheckpoint: resources are ready");
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        System.out.println("CRAC afterRestore: recreating HTTP listener");
        startListener();
        System.out.println("CRAC afterRestore: HTTP listener started");
    }

    private synchronized void startListener() throws IOException {
        if (server != null) {
            return;
        }

        ExecutorService executor = Executors.newFixedThreadPool(4);
        HttpServer newServer = null;

        try {
            newServer = HttpServer.create(
                    new InetSocketAddress("0.0.0.0", port),
                    0
            );

            newServer.setExecutor(executor);
            newServer.createContext("/", this::handleRequest);
            newServer.start();

            requestExecutor = executor;
            server = newServer;

        } catch (IOException | RuntimeException e) {
            if (newServer != null) {
                newServer.stop(0);
            }

            executor.shutdownNow();
            throw e;
        }
    }

    private synchronized void stopListener() throws InterruptedException {
        HttpServer currentServer = server;
        ExecutorService currentExecutor = requestExecutor;

        server = null;
        requestExecutor = null;

        if (currentServer != null) {
            currentServer.stop(0);
        }

        if (currentExecutor != null) {
            currentExecutor.shutdown();

            if (!currentExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                currentExecutor.shutdownNow();

                if (!currentExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "HTTP request executor did not terminate"
                    );
                }
            }
        }
    }

    private void handleRequest(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();

        String body;
        if ("/health/ready".equals(path)) {
            body = "READY\n";
        } else {
            body = "Hello from a CRaC-enabled Java container\n"
                    + "path=" + path + "\n"
                    + "java.version=" + System.getProperty("java.version") + "\n"
                    + "java.vendor=" + System.getProperty("java.vendor") + "\n";
        }

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type",
                "text/plain; charset=utf-8"
        );

        exchange.sendResponseHeaders(200, bytes.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        int port = Integer.getInteger("server.port", 8080);
        application = new CracHttpApp(port);

        System.out.println("Application started on port " + port);
    }
}
~~~

### 4.1. Vai trò của callback

`beforeCheckpoint()` được gọi trước khi trạng thái tiến trình được lưu. Ứng dụng nên dừng nhận công việc mới, drain các thao tác đang chạy và đóng hoặc chuẩn bị lại resource không an toàn khi giữ qua checkpoint.

`afterRestore()` được gọi khi tiến trình được khôi phục. Ứng dụng có thể tạo lại listener, connection pool, scheduler hoặc client cần thiết. Chỉ chuyển readiness sang READY sau khi các resource bắt buộc đã sẵn sàng.

Trong ví dụ, listener được đóng trước checkpoint và mở lại sau restore. Điều này giúp tránh giả định rằng socket cũ vẫn hợp lệ trong network namespace của môi trường đích.

### 4.2. Vì sao giữ Resource trong static field?

Biến **application** giữ một reference đến object đăng ký callback trong ví dụ. CRaC context cũng quản lý resource đã đăng ký, nhưng giữ reference rõ ràng giúp vòng đời của object dễ hiểu khi mở rộng ứng dụng.

### 4.3. Vì sao không giữ executor cũ?

Executor có thread và trạng thái nội bộ. Dừng nó trước checkpoint rồi tạo executor mới sau restore làm rõ ownership của thread pool. Với thư viện khác, cần theo tài liệu riêng: một số client có CRaC integration và tự quản lý resource; không đóng trùng resource do thư viện sở hữu.

### 4.4. Giới hạn của ví dụ

`stop(0)` dừng server ngay và không phải chiến lược drain phù hợp cho mọi production workload. Trong hệ thống thật, cần ngừng admission, chờ request đang chạy hoàn tất trong timeout, đóng connection và xử lý lỗi nếu drain không thành công.

## 5. Build JAR

Từ thư mục project, chạy:

~~~bash
./gradlew clean test jar
~~~

Nếu project chưa có Gradle Wrapper, tạo wrapper bằng Gradle đã cài:

~~~bash
gradle wrapper
./gradlew clean test jar
~~~

Kiểm tra artifact:

~~~bash
ls -lh build/libs/
jar tf build/libs/crac-container-lab-1.0.0.jar
sha256sum build/libs/crac-container-lab-1.0.0.jar
~~~

Tên JAR thực tế phụ thuộc `rootProject.name` và `version`. Nếu tên file khác, cập nhật đường dẫn trong Dockerfile ở bước tiếp theo.

Build JAR bằng JDK toolchain phù hợp. Runtime container vẫn phải dùng JDK có CRaC support; một JDK Java 21 thông thường không tự có khả năng CRaC chỉ vì JAR đã import `org.crac.Resource`.

## 6. Tạo container image với CRaC-enabled JDK

Chọn một base image Linux chứa JDK CRaC đã được xác nhận. Dùng digest cụ thể thay vì tag floating. Thay placeholder trong Dockerfile bằng image thật từ distribution bạn sử dụng.

Ví dụ **Dockerfile**:

~~~dockerfile
FROM registry.example.com/java-crac:21@sha256:<verified-image-digest>

WORKDIR /opt/app

RUN mkdir -p /checkpoint

COPY build/libs/crac-container-lab-1.0.0.jar /opt/app/app.jar

EXPOSE 8080

VOLUME ["/checkpoint"]

CMD ["java", "-XX:CRaCCheckpointTo=/checkpoint", "-jar", "/opt/app/app.jar"]
~~~

Đây là Dockerfile mẫu. Tên image, digest, đường dẫn checkpoint flag và cách restore cần được xác nhận với JDK CRaC distribution. Một số vendor cung cấp image hoặc wrapper riêng cho checkpoint/restore.

### 6.1. Vì sao checkpoint directory là volume?

Checkpoint có thể gồm nhiều file và có kích thước lớn. Lưu trong writable layer của container khiến artifact dễ mất khi container bị xóa hoặc thay thế.

Mount một host directory hoặc persistent volume vào `/checkpoint` giúp:

- Giữ checkpoint độc lập với container lifecycle.
- Có thể tính checksum và lưu manifest.
- Dùng lại artifact trong quy trình restore đã được kiểm chứng.
- Áp dụng retention và access control riêng.

Không nên commit checkpoint vào source repository hoặc đưa vào Docker build context.

### 6.2. Build image

~~~bash
docker build -t crac-container-lab:1.0.0 .
~~~

Sau khi build, xem image:

~~~bash
docker image inspect crac-container-lab:1.0.0
docker image ls crac-container-lab
~~~

Với release thực tế, push image lên registry rồi lấy digest do registry trả về. Dùng digest đó để triển khai và lưu trong checkpoint manifest.

### 6.3. Kiểm tra JDK trong image

~~~bash
docker run --rm crac-container-lab:1.0.0 java -version
docker run --rm crac-container-lab:1.0.0 java -XX:+PrintFlagsFinal -version
~~~

Lệnh thứ hai giúp kiểm tra JVM flags mà runtime nhận biết, nhưng không thay thế tài liệu CRaC của vendor. Nếu JDK không nhận cờ `-XX:CRaCCheckpointTo`, image không phải runtime phù hợp hoặc cú pháp khác với distribution đã chọn.

## 7. Chuẩn bị checkpoint volume

Trên Linux host:

~~~bash
mkdir -p "$PWD/checkpoint"
chmod 700 "$PWD/checkpoint"
~~~

Directory phải được user chạy container và CRIU truy cập được. Nếu container chạy bằng UID không phải root, cần điều chỉnh ownership hoặc mount option tương ứng.

Không dùng một directory checkpoint đang chứa artifact cũ mà không kiểm tra nội dung. Mỗi lần tạo checkpoint nên dùng một thư mục riêng hoặc xóa artifact cũ theo quy trình có kiểm soát.

Ví dụ cấu trúc sau khi checkpoint:

~~~text
crac-container-lab/
├── build/
├── checkpoint/
│   ├── checkpoint.img
│   ├── pages-1.img
│   ├── core-*.img
│   └── metadata...
├── Dockerfile
└── src/
~~~

Tên và số lượng file phụ thuộc CRaC/CRIU version. Không giả định mọi phiên bản tạo đúng các tên minh họa này.

## 8. Chạy container với quyền checkpoint/restore

CRIU cần tương tác với kernel và process. Quyền cần thiết phụ thuộc kernel, CRIU, container runtime, user namespace và security profile.

Một lệnh minh họa trên Linux Docker Engine:

~~~bash
docker run -d \
  --name crac-demo \
  -p 8080:8080 \
  --mount type=bind,src="$PWD/checkpoint",dst=/checkpoint \
  --cap-add=CHECKPOINT_RESTORE \
  --cap-add=SYS_PTRACE \
  --cap-add=SYS_ADMIN \
  --security-opt seccomp=unconfined \
  crac-container-lab:1.0.0
~~~

Các capability và security option ở trên là ví dụ để kiểm thử trong môi trường Linux lab. Không áp dụng nguyên trạng cho production. Dùng cấu hình tối thiểu được JDK/CRIU và container runtime của bạn hỗ trợ. Một số kernel cũ không có `CAP_CHECKPOINT_RESTORE`; một số cấu hình yêu cầu quyền hoặc policy khác.

Nếu container không khởi động được hoặc `criu check` thất bại, kiểm tra:

- Kernel release và CRIU version.
- Capability của container.
- Seccomp profile.
- AppArmor/SELinux policy.
- User namespace và UID mapping.
- Quyền truy cập `/proc`, mount và checkpoint directory.
- Cách Docker daemon được cấu hình.

Không nên chỉ tăng quyền vô hạn để che một cấu hình host chưa phù hợp. Hãy xác định thao tác hệ thống nào bị chặn và dùng policy phù hợp cho lab hoặc production.

### 8.1. Kiểm tra container và ứng dụng

~~~bash
docker ps --filter name=crac-demo
docker logs crac-demo
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/health/ready
~~~

Kết quả mong đợi là HTTP 200 và body chứa thông tin ứng dụng. Nếu container thoát ngay, xem log trước khi tiếp tục.

### 8.2. Xác định PID Java

~~~bash
docker exec crac-demo jcmd -l
~~~

Với CMD ở Dockerfile, Java thường là PID 1 trong container vì Docker chạy command trực tiếp. Tuy vậy, hãy lấy PID từ `jcmd -l` thay vì mặc định luôn là 1.

## 9. Tạo checkpoint bằng JDK CRaC

Trước khi checkpoint:

1. Gửi request kiểm tra và xác nhận ứng dụng đang phục vụ.
2. Xác nhận checkpoint directory được mount và có quyền ghi.
3. Kiểm tra không có request hoặc job đang dang dở.
4. Ghi lại image digest, JDK build và runtime profile.
5. Đảm bảo CRIU và host đáp ứng yêu cầu.

Với JDK CRaC hỗ trợ lệnh `JDK.checkpoint`, có thể kích hoạt checkpoint bằng `jcmd`:

~~~bash
docker exec crac-demo jcmd 1 JDK.checkpoint
~~~

Thay PID `1` bằng PID Java thực tế lấy từ `jcmd -l`. Một số distribution có wrapper hoặc cú pháp điều khiển riêng; hãy dùng đúng hướng dẫn của JDK đang chạy.

Khi lệnh được thực hiện, CRaC sẽ gọi các Resource callback đã đăng ký trước khi lưu process state. Trong ví dụ, `beforeCheckpoint()` dừng HTTP listener và executor. Sau đó, cơ chế checkpoint của runtime ghi các file cần thiết vào `/checkpoint`.

### 9.1. Kiểm tra kết quả

~~~bash
find checkpoint -maxdepth 2 -type f -printf '%p %s bytes\n'
du -sh checkpoint
~~~

Nếu checkpoint directory vẫn trống, kiểm tra output của `jcmd`, log JVM và log CRIU. Đừng tiếp tục restore với một directory rỗng hoặc checkpoint chỉ có một phần file.

### 9.2. Process gốc sau checkpoint

Hành vi của process gốc sau khi tạo checkpoint phụ thuộc JDK CRaC distribution và cách công cụ checkpoint được tích hợp. Có runtime để process tiếp tục chạy sau khi ảnh được tạo; cũng có quy trình quản lý process khác.

Hãy đọc output và kiểm tra trạng thái:

~~~bash
docker ps --filter name=crac-demo
docker logs crac-demo
~~~

Nếu process gốc vẫn đang chạy, không để nó và process được restore cùng bind vào cùng một port/network endpoint. Dừng hoặc cô lập instance gốc theo hướng dẫn của runtime trước khi restore.

## 10. Khôi phục ứng dụng từ checkpoint

Restore cần đúng JDK/CRaC runtime, checkpoint files đầy đủ và môi trường Linux tương thích. Không phải cứ chạy `docker start` là ứng dụng sẽ tự restore từ JDK CRaC checkpoint. `docker start` thông thường chỉ khởi động lại container theo command của image.

Với các JDK CRaC dùng flag `-XX:CRaCRestoreFrom`, hình thức lệnh thường gặp là:

~~~bash
java -XX:CRaCRestoreFrom=/checkpoint
~~~

Checkpoint đã chứa trạng thái process và thông tin khởi chạy của tiến trình được lưu; vì vậy lệnh restore thường chỉ chỉ định đường dẫn checkpoint, không chạy lại main class như một lần cold start. Lệnh cụ thể cần theo tài liệu của distribution. Một số runtime yêu cầu wrapper hoặc container restore integration để thiết lập namespace, mount, process tree và CRIU options. Không bỏ qua yêu cầu đó bằng cách chỉ copy thư mục checkpoint sang một container bất kỳ.

### 10.1. Restore với cùng image và volume

Về nguyên tắc, restore phải dùng:

- Cùng application image digest đã tạo checkpoint.
- Cùng JDK/CRaC build.
- Cùng native libraries và runtime files.
- Cùng architecture và CPU baseline tương thích.
- Mount path cần thiết.
- Kernel/CRIU và security configuration được xác nhận.
- Network và namespace configuration phù hợp.

Nếu JDK cung cấp command line restore trực tiếp, có thể dùng một command tương tự sau trong môi trường đã được runtime hỗ trợ:

~~~bash
docker run --rm \
  --name crac-demo-restored \
  -p 8080:8080 \
  --mount type=bind,src="$PWD/checkpoint",dst=/checkpoint \
  --cap-add=CHECKPOINT_RESTORE \
  --cap-add=SYS_PTRACE \
  --cap-add=SYS_ADMIN \
  --security-opt seccomp=unconfined \
  crac-container-lab:1.0.0 \
  java -XX:CRaCRestoreFrom=/checkpoint
~~~

Đây là command shape minh họa, không phải cam kết rằng mọi Docker Engine hoặc JDK có thể restore checkpoint từ một container mới với namespace mới. CRIU cần restore process vào môi trường tương thích; runtime có thể phải giữ hoặc tái tạo PID, mount và network namespace theo một quy trình cụ thể.

Nếu distribution cung cấp một CRaC-aware container runtime, wrapper script hoặc Kubernetes integration, hãy dùng cơ chế đó thay cho command minh họa này.

### 10.2. Không nhầm với Docker container checkpoint

Docker có thể cung cấp lệnh dạng:

~~~bash
docker checkpoint create <container> <checkpoint-name>
docker start --checkpoint <checkpoint-name> <container>
~~~

Đây là checkpoint/restore ở cấp container runtime, không phải thao tác JDK CRaC tương đương. Cơ chế này không thay thế callback `beforeCheckpoint()`/`afterRestore()` của Java Resource theo cùng contract. Nếu ứng dụng cần chuẩn bị connection, cache hoặc listener, vẫn phải thiết kế lifecycle CRaC phù hợp.

### 10.3. Xử lý port và network namespace

Ứng dụng trong bài lab đóng HTTP listener trước checkpoint rồi bind lại sau restore. Tuy vậy, container runtime vẫn có thể tạo network namespace hoặc port mapping khác khi tạo container mới.

Nếu restore trong một namespace khác, phải xác nhận cách runtime khôi phục socket và cách host port được ánh xạ. Không giả định checkpoint chứa socket cũ sẽ tự hoạt động trên một network namespace mới.

## 11. Xác minh sau restore

Sau khi runtime báo restore thành công, kiểm tra log:

~~~bash
docker logs crac-demo-restored
~~~

Mong đợi thấy các thông báo:

~~~text
CRAC afterRestore: recreating HTTP listener
CRAC afterRestore: HTTP listener started
~~~

Sau đó gửi request:

~~~bash
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/health/ready
~~~

Mong đợi HTTP 200 và body `READY` ở endpoint readiness. Nếu restore thành công nhưng listener không mở lại, kiểm tra callback `afterRestore`, port binding và log exception.

### 11.1. Kiểm tra process và runtime identity

~~~bash
docker exec crac-demo-restored jcmd -l
docker exec crac-demo-restored java -version
~~~

Tên container và cách gọi `jcmd` có thể thay đổi theo cách runtime restore. Quan trọng là xác nhận process đang chạy đúng image/JDK đã định và ứng dụng phục vụ request sau callback.

### 11.2. Xác nhận callback được gọi đúng thứ tự

Log cần cho thấy:

- Ở thời điểm tạo checkpoint, `beforeCheckpoint()` dừng listener.
- Sau restore, `afterRestore()` tạo listener mới.
- Readiness chỉ thành công sau khi resource cần thiết sẵn sàng.
- Không có lỗi bind port hoặc thread pool.
- Request sau restore trả response thành công.

Không dựa vào việc container có trạng thái Running để kết luận ứng dụng đã Ready.

## 12. Đóng gói checkpoint như artifact riêng

Sau khi tạo checkpoint, cần ghi nhận thông tin để biết ảnh thuộc release nào và có thể restore trong môi trường nào.

Một manifest tối thiểu:

~~~yaml
schemaVersion: 1

application:
  name: crac-container-lab
  version: 1.0.0
  sourceCommit: "<git-commit-sha>"
  jarSha256: "<jar-sha256>"

container:
  image: "registry.example.com/crac-container-lab@sha256:<image-digest>"
  architecture: "amd64"

runtime:
  jdkVendor: "<vendor>"
  javaVersion: "<full-java-version>"
  jdkBuild: "<exact-build>"
  cracSupport: "<crac-build>"
  jvmFlags:
    - "-XX:CRaCCheckpointTo=/checkpoint"

platform:
  os: Linux
  kernel: "<kernel-release>"
  criu: "<criu-version>"
  containerRuntime: "<runtime-version>"
  cpuBaseline: "<validated-cpu-baseline>"

checkpoint:
  id: "crac-container-lab-1.0.0-linux-x86-001"
  path: "checkpoint/"
  totalBytes: 0
  files:
    - path: "checkpoint.img"
      sha256: "<sha256>"
    - path: "pages-1.img"
      sha256: "<sha256>"

validation:
  restoreTest: "<test-run-id>"
  status: "<passed-or-failed>"
  testedNodePool: "<node-pool-profile>"
~~~

Các giá trị là placeholder. Tạo manifest sau khi checkpoint hoàn tất và tính digest thực tế cho tất cả file. Không giữ `totalBytes: 0` hoặc placeholder trong manifest phát hành.

### 12.1. Tính checksum cho checkpoint

Ví dụ:

~~~bash
find checkpoint -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum > checkpoint.SHA256SUMS
~~~

Nếu lưu checksum file bên trong chính thư mục checkpoint, cần tránh tự đưa file checksum vào danh sách checksum của nó. Có thể lưu `SHA256SUMS` bên ngoài thư mục hoặc tạo danh sách trước khi thêm file checksum.

Khi restore:

~~~bash
sha256sum -c checkpoint.SHA256SUMS
~~~

Dùng đúng danh sách file đã ký hoặc lưu trong catalog đáng tin cậy. Checksum chỉ có ý nghĩa nếu giá trị kỳ vọng được bảo vệ; nếu attacker thay cả checkpoint và checksum, phép so sánh không chứng minh nguồn gốc artifact.

### 12.2. Ký manifest và bảo vệ artifact

Trong production, ký manifest hoặc tạo attestation liên kết digest checkpoint với image digest, source commit và JDK build. Giới hạn quyền đọc checkpoint vì memory image có thể chứa token, credential, session hoặc dữ liệu nhạy cảm trong heap.

Không lưu secret dạng plaintext trong manifest. Chỉ ghi secret reference hoặc version ID.

## 13. Dockerfile và quy trình restore theo hai mode

Một image có thể cung cấp hai mode khởi chạy: tạo checkpoint và restore checkpoint. Có thể dùng entrypoint script để chọn mode, nhưng cần xác nhận cờ tương ứng của JDK.

Ví dụ **entrypoint.sh**:

~~~sh
#!/bin/sh
set -eu

MODE=$(printenv START_MODE 2>/dev/null || true)
if [ -z "$MODE" ]; then
  MODE=normal
fi

case "$MODE" in
  normal)
    exec java \
      -XX:CRaCCheckpointTo=/checkpoint \
      -jar /opt/app/app.jar
    ;;
  restore)
    exec java \
      -XX:CRaCRestoreFrom=/checkpoint
    ;;
  *)
    echo "Unsupported START_MODE: $MODE" >&2
    exit 2
    ;;
esac
~~~

Nếu dùng script, cập nhật Dockerfile:

~~~dockerfile
FROM registry.example.com/java-crac:21@sha256:<verified-image-digest>

WORKDIR /opt/app

RUN mkdir -p /checkpoint

COPY build/libs/crac-container-lab-1.0.0.jar /opt/app/app.jar
COPY entrypoint.sh /opt/app/entrypoint.sh

RUN chmod 755 /opt/app/entrypoint.sh

EXPOSE 8080
VOLUME ["/checkpoint"]

ENTRYPOINT ["/opt/app/entrypoint.sh"]
~~~

Khởi chạy bình thường:

~~~bash
docker run -d \
  --name crac-demo \
  -e START_MODE=normal \
  -p 8080:8080 \
  --mount type=bind,src="$PWD/checkpoint",dst=/checkpoint \
  crac-container-lab:1.0.0
~~~

Khởi chạy theo restore mode trong runtime được hỗ trợ:

~~~bash
docker run --rm \
  --name crac-demo-restored \
  -e START_MODE=restore \
  -p 8080:8080 \
  --mount type=bind,src="$PWD/checkpoint",dst=/checkpoint \
  crac-container-lab:1.0.0
~~~

Script này chỉ chọn JVM option. Nó không tự cấp capability, dựng namespace, gọi CRIU hoặc cấu hình container runtime. Những phần đó vẫn phải do môi trường restore hỗ trợ.

## 14. Dùng checkpoint trong Kubernetes

Trong Kubernetes, application image và checkpoint artifact thường được phân phối riêng. Image chứa JDK CRaC và ứng dụng; checkpoint được tải vào volume hoặc cung cấp bởi một restore-aware runtime.

Một Pod chỉ nên được đánh dấu Ready sau khi:

- Checkpoint được xác minh và restore thành công.
- Callback `afterRestore()` hoàn tất.
- Connection và resource thiết yếu được tạo lại.
- Listener hoặc request handler sẵn sàng.
- Readiness state được cập nhật.

Ví dụ cấu hình minh họa volume checkpoint và readiness probe:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: crac-container-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: crac-container-lab
  template:
    metadata:
      labels:
        app: crac-container-lab
    spec:
      containers:
        - name: app
          image: registry.example.com/crac-container-lab@sha256:<image-digest>
          ports:
            - name: http
              containerPort: 8080
          volumeMounts:
            - name: checkpoint
              mountPath: /checkpoint
              readOnly: true
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
      volumes:
        - name: checkpoint
          persistentVolumeClaim:
            claimName: crac-checkpoint-pvc
~~~

Đây là ví dụ về cách mount checkpoint và khai báo readiness. Nó chưa phải một cấu hình CRaC Kubernetes hoàn chỉnh: Kubernetes không tự biết cách gọi JDK restore hoặc CRIU chỉ nhờ volume mount. Cần runtime, operator, init process hoặc integration chuyên biệt để thực hiện restore theo yêu cầu của distribution.

### 14.1. Readiness và liveness

Readiness phản ánh khả năng nhận traffic. Nếu restore hoặc dependency initialization chưa hoàn tất, endpoint `/health/ready` nên trả trạng thái không sẵn sàng.

Liveness nên tập trung vào sức khỏe nội bộ của process. Không nên restart Pod chỉ vì database hoặc Redis tạm thời chậm; việc restart có thể tạo thêm restore/reconnect storm.

### 14.2. Checkpoint volume và access control

Checkpoint volume cần:

- Đúng checkpoint ID của release.
- Read-only đối với process sau khi artifact đã được tạo và xác minh, nếu runtime không cần ghi.
- Đủ dung lượng và tốc độ đọc.
- Ownership/permission phù hợp.
- Access control giới hạn workload được phép đọc.
- Retention bảo vệ checkpoint còn được Pod hoặc rollback tham chiếu.

Một PVC có thể được mount vào nhiều Pod nhưng điều đó không có nghĩa mọi Pod có thể restore cùng checkpoint trong mọi cấu hình. Cần xác minh cách CRIU và runtime xử lý namespace, PID và file lock khi restore nhiều bản sao.

## 15. Những điều kiện cần giữ tương thích

Khi tạo và restore checkpoint trong container Linux, hãy lưu và đối chiếu ít nhất các nhóm sau:

| Nhóm | Cần ghi nhận |
|---|---|
| Application | Release ID, source commit, JAR digest |
| Image | OCI image digest, base image digest |
| JDK | Vendor, full version, build, CRaC support |
| JVM | JVM flags, GC/compiler configuration |
| Native runtime | libc, dynamic linker, JNI/native library |
| CPU | Architecture và CPU feature baseline |
| Kernel | Kernel release/build và feature cần thiết |
| CRIU | Version và capability check |
| Container runtime | Docker/containerd/CRI-O version và restore integration |
| Namespace | PID, mount, network, user namespace |
| Security | Capability, seccomp, AppArmor/SELinux |
| Filesystem | Checkpoint path, mount, ownership, storage behavior |

Cùng container image không đảm bảo restore được trên mọi host vì container vẫn dùng kernel của host. Cùng kernel version cũng chưa đủ nếu capability, namespace, CPU feature hoặc security policy khác.

## 16. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| JVM không nhận `-XX:CRaCCheckpointTo` | JDK không có CRaC hoặc cờ khác theo distribution | Kiểm tra `java -version` và tài liệu JDK |
| Không tìm thấy `JDK.checkpoint` | Runtime không hỗ trợ command hoặc jcmd không đúng JDK | Kiểm tra `jcmd -l`, JDK build và command reference |
| `criu check` thất bại | Kernel feature hoặc quyền không đủ | Kiểm tra CRIU log, capability và security policy |
| Permission denied khi ghi checkpoint | Volume ownership/mode sai | Kiểm tra UID/GID và mount |
| Checkpoint directory rỗng | Checkpoint chưa chạy xong hoặc output path sai | Xem jcmd/JVM/CRIU log |
| Restore báo thiếu file | Artifact copy chưa đầy đủ | Đối chiếu manifest và checksum |
| Restore lỗi trên node khác | Kernel, CPU, CRIU hoặc namespace khác | So sánh platform manifest |
| Port 8080 đã được dùng | Listener cũ hoặc process khác vẫn chạy | Kiểm tra process, socket và port mapping |
| Restore xong nhưng HTTP không phản hồi | `afterRestore()` lỗi hoặc listener không bind | Kiểm tra callback log và readiness |
| Container thoát sau restore | Runtime/entrypoint không đúng quy trình | Xem exit code, JVM log và restore wrapper |
| Native library load lỗi | ABI hoặc dependency khác | Kiểm tra image digest, `ldd`, `readelf` |
| Restore chậm bất thường | Checkpoint lớn hoặc storage I/O chậm | Đo dung lượng và thời gian đọc ảnh |

### 16.1. Thu thập thông tin khi lỗi

~~~bash
java -version
jcmd -l
criu --version
sudo criu check
docker version
docker info
docker logs crac-demo
~~~

Thu thập thêm kernel log hoặc CRIU log theo cách runtime cung cấp. Không chỉ ghi lại một dòng exception Java vì lỗi gốc có thể nằm ở kernel hoặc container runtime.

### 16.2. Không xóa checkpoint ngay sau restore thất bại

Giữ lại artifact và log để điều tra. Nếu cần thử lại, copy checkpoint sang thư mục test riêng và giữ nguyên bản gốc. Không ghi đè artifact đã được ký hoặc đang được release catalog tham chiếu.

## 17. Quy trình thực hành từ đầu đến cuối

Thực hiện theo trình tự sau trên Linux host tương thích.

### Giai đoạn A: Build

1. Tạo project Gradle.
2. Thêm CRaC API dependency tương thích.
3. Viết `CracHttpApp` và đăng ký Resource.
4. Chạy `./gradlew clean test jar`.
5. Tính SHA-256 của JAR.
6. Chọn CRaC-enabled JDK image bằng digest.

### Giai đoạn B: Package

1. Viết Dockerfile dùng đúng JDK image.
2. Copy JAR vào image.
3. Khai báo checkpoint directory.
4. Build container image.
5. Lưu image digest và runtime identity.

### Giai đoạn C: Chuẩn bị host

1. Kiểm tra kernel và CPU architecture.
2. Cài CRIU.
3. Chạy `criu check`.
4. Xác định capability và security profile cần thiết.
5. Chuẩn bị checkpoint volume.
6. Kiểm tra quyền đọc/ghi.

### Giai đoạn D: Chạy và checkpoint

1. Khởi động container.
2. Gửi request đến `/` và `/health/ready`.
3. Lấy PID Java bằng `jcmd -l`.
4. Kích hoạt `JDK.checkpoint` theo tài liệu JDK.
5. Quan sát `beforeCheckpoint()` trong log.
6. Xác nhận checkpoint files đã được ghi đầy đủ.
7. Tính checksum và tạo manifest.

### Giai đoạn E: Restore và xác minh

1. Dừng hoặc cô lập process gốc theo quy trình runtime.
2. Chọn đúng image digest và JDK build.
3. Mount checkpoint directory.
4. Gọi restore bằng JDK hoặc wrapper được hỗ trợ.
5. Quan sát `afterRestore()` trong log.
6. Gửi request đến `/health/ready`.
7. Xác nhận HTTP 200.
8. Ghi restore attempt, node profile và thời gian readiness.

### Giai đoạn F: Đóng gói release

1. Lưu JAR/image digest và checkpoint manifest.
2. Ký manifest hoặc attestation.
3. Lưu checkpoint trong storage có access control.
4. Liên kết checkpoint ID với release ID.
5. Chỉ promote sau khi restore validation thành công.

## 18. Checklist trước khi dùng production

### Build và image

- [ ] JDK image có CRaC support và được pin bằng digest.
- [ ] JAR được build bằng toolchain đã ghi nhận.
- [ ] CRaC API dependency tương thích với runtime.
- [ ] Native dependencies đã được kiểm kê.
- [ ] Image không chứa checkpoint cũ ngoài chủ đích.

### Linux host và container runtime

- [ ] Kernel/architecture đã được xác nhận.
- [ ] CRIU version và capability check đã được ghi lại.
- [ ] Container runtime hỗ trợ quy trình restore được chọn.
- [ ] Capability và security profile ở mức tối thiểu cần thiết.
- [ ] PID/mount/network namespace phù hợp.
- [ ] Checkpoint storage đủ dung lượng và quyền truy cập.

### Application lifecycle

- [ ] Resource đã đăng ký callback CRaC.
- [ ] `beforeCheckpoint()` dừng admission và drain công việc.
- [ ] Connection và listener được đóng hoặc chuẩn bị đúng cách.
- [ ] `afterRestore()` tạo lại resource cần thiết.
- [ ] Callback có timeout và xử lý lỗi.
- [ ] Readiness chỉ mở khi dependency thiết yếu sẵn sàng.
- [ ] Scheduled task, lock và consumer state được kiểm tra sau restore.

### Artifact và restore

- [ ] Checkpoint có ID riêng.
- [ ] Manifest ghi source, image, JDK, platform và warm-up profile.
- [ ] Mọi checkpoint file có checksum.
- [ ] Manifest/attestation được ký.
- [ ] Checkpoint được lưu immutable và có access control.
- [ ] Đã restore thử trên đúng node pool mục tiêu.
- [ ] Có rollback hoặc cold-start fallback đã kiểm thử.

## 19. Câu hỏi thường gặp

### Có thể dùng bất kỳ JDK 21 image nào không?

Không. JDK phải có CRaC support tương thích với ứng dụng và checkpoint. Cùng major version Java không đảm bảo có cùng CRaC patch, native runtime hoặc build. Hãy pin distribution/build và image digest.

### Chỉ cần thêm thư viện `org.crac` vào JAR là đủ chưa?

Chưa. Dependency cung cấp API để ứng dụng đăng ký resource và xử lý callback. Khả năng checkpoint/restore còn cần JDK hỗ trợ CRaC, CRIU và Linux environment phù hợp.

### Có thể tạo checkpoint trên Windows hoặc macOS rồi restore trong Linux container không?

Không nên giả định. Checkpoint gắn với process, kernel và native runtime. Bài thực hành này tạo và restore trên Linux environment tương thích. Nếu dùng host Windows/macOS, hãy chạy trong Linux VM hoặc môi trường được JDK/CRIU hỗ trợ.

### Có thể copy checkpoint vào một image mới rồi restore không?

Chỉ khi image mới giữ nguyên runtime và native dependencies tương thích, đồng thời các điều kiện kernel, CPU và namespace được đáp ứng. Thay JDK, libc hoặc native library có thể làm checkpoint không còn hợp lệ. Hãy dùng manifest và restore validation để xác nhận.

### Docker `checkpoint create` có giống `jcmd JDK.checkpoint` không?

Không. Docker checkpoint là thao tác ở tầng container runtime. `JDK.checkpoint` là thao tác của JDK CRaC và phối hợp với callback Resource trong ứng dụng. Chọn cơ chế theo kiến trúc và integration đang dùng.

### Có thể dùng `docker start` để restore JDK CRaC checkpoint không?

Không theo mặc định. `docker start` khởi động lại container theo command thông thường. Restore CRaC cần JDK restore option hoặc wrapper/integration tương ứng. Docker có lệnh restore container riêng nhưng đó là một cơ chế khác.

### Vì sao phải đóng HTTP listener trước checkpoint?

Socket và network namespace có thể không còn hợp lệ trong môi trường restore. Ví dụ này đóng listener rồi mở lại trong `afterRestore()`. Production cần drain request trước khi đóng và kiểm tra port mapping ở runtime.

### Checkpoint có thể lưu ở volume riêng không?

Có, và đó thường là cách tổ chức thuận tiện. Volume giúp checkpoint tồn tại độc lập với writable layer của container. Cần bảo đảm mount path, permission, storage behavior và access control phù hợp.

### Có thể restore cùng checkpoint trên nhiều container cùng lúc không?

Không nên giả định. Restore nhiều bản sao phụ thuộc CRIU, namespace, PID, network, storage và cách runtime hỗ trợ. Ngoài tương thích kỹ thuật, cần kiểm tra trạng thái heap bị nhân bản như scheduler, lock, consumer và job đang chạy.

### Khi restore thành công nhưng readiness thất bại thì kiểm tra gì?

Kiểm tra log `afterRestore()`, resource initialization, connection pool, listener bind, secret, DNS và dependency health. Container Running chỉ cho biết process tồn tại; không chứng minh ứng dụng đã phục vụ được request.

### Có cần đưa checkpoint vào container image không?

Thông thường nên quản lý image và checkpoint thành artifact riêng. Image chứa ứng dụng và runtime; checkpoint được lưu ở registry hoặc storage phù hợp và gắn với image digest bằng manifest. Cách này giúp quản lý retention, validation và rollback rõ ràng hơn.

## Kết luận

Đóng gói và khôi phục ứng dụng Java trong container Linux với CRaC cần phối hợp ba lớp: application lifecycle, JDK CRaC runtime và Linux/container environment. Ứng dụng phải đăng ký Resource để dừng hoặc tái lập các resource phù hợp; image phải chứa đúng JDK và native dependency; host phải đáp ứng yêu cầu kernel, CRIU, namespace và security policy.

Trong bài thực hành, HTTP server được đóng trước checkpoint và tạo lại trong `afterRestore()`. JAR được đóng gói trong image, còn checkpoint được lưu trên volume riêng và gắn với manifest chứa image digest, JDK build, platform profile và checksum. Sau restore, kiểm tra callback, readiness và request HTTP để xác nhận ứng dụng hoạt động.

Khi triển khai thực tế, hãy dùng đúng restore integration của JDK/container runtime, giữ môi trường tương thích, xác minh artifact trước khi restore và chỉ mở traffic khi resource thiết yếu đã sẵn sàng.
