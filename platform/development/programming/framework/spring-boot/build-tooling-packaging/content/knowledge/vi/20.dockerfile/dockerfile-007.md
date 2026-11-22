# Cấu hình WORKDIR, quyền sở hữu tệp và người dùng không phải root

Dockerfile cho ứng dụng Spring Boot cần làm nhiều hơn việc `COPY app.jar` rồi `java -jar app.jar`. Một image có thể build thành công nhưng container không khởi động vì không đọc được JAR, không thể ghi file tạm, hoặc chạy bằng quyền `root` dù ứng dụng thực tế không cần đặc quyền. Ba chỉ dẫn/khái niệm liên quan trực tiếp:

1. **`WORKDIR`** xác định thư mục làm việc trong image/container cho các chỉ dẫn theo sau. Nó **không tự đồng nghĩa** với việc cấp quyền ghi cho tiến trình.
2. **Owner, group và permission** xác định UID/GID nào có thể đọc, ghi hoặc đi vào một thư mục. `COPY --chown` và `COPY --chmod` giúp khai báo các quyền đó ngay lúc tạo image.
3. **`USER`** đặt tài khoản/UID/GID mặc định cho những lệnh `RUN` tiếp theo trong cùng stage và tiến trình container khi chạy `ENTRYPOINT`/`CMD`. Với ứng dụng web thông thường, nên dùng **non-root** và chỉ cấp quyền tối thiểu.

Bài này sử dụng **Java 17, Spring Boot 3.3.13, Maven 3.9.x**, runtime image Ubuntu/JRE của Eclipse Temurin, Docker Engine với BuildKit/Dockerfile frontend hỗ trợ `COPY --chown` và `--chmod`. Phiên bản được cố định cho ví dụ học tập; trước production cần chọn tag/digest image được tổ chức phê duyệt, vá CVE và kiểm tra compatibility. Tất cả lệnh `docker` là minh họa cho máy đã cài Docker/được cấp quyền; chúng không được thực thi trong bài viết.

## 1. Sơ đồ quyền và vai trò trong một Spring Boot container

Ta dùng filesystem layout:

```text
Image runtime
/
├── opt/
│   └── app/                       WORKDIR
│       └── app.jar                mode 0444, owner 10001:10001
├── var/
│   └── app-data/                  mode 0750, owner 10001:10001
├── tmp/                           JVM/Tomcat temp; cần mount nếu root FS read-only
└── usr/lib/jvm/...                 Java runtime từ base image

Container process:
  UID = 10001
  GID = 10001
  command = java -jar /opt/app/app.jar
  HTTP port = 8080
```

**Thiết kế có chủ đích:**

- `/opt/app` chỉ chứa chương trình. Thư mục này root-owned/không cho app user ghi, nhưng cần cho phép **đi qua thư mục** (`x`) và đọc file JAR.
- `/opt/app/app.jar` do UID/GID `10001:10001` sở hữu nhưng mode `0444` (chỉ đọc). Owner vẫn **không** tự có quyền ghi vì mode không cấp `w`.
- `/var/app-data` là **vùng ghi được** dành cho tác vụ cần lưu dữ liệu tạm/thực (nếu có). Mode `0750` và owner `10001:10001` giới hạn quyền của người khác.
- `/tmp` phù hợp một số file tạm của Java/Spring Boot, nhưng khi bật **read-only root filesystem** phải cấp tmpfs/volume thích hợp. Việc ứng dụng cần ghi ở đâu phải được kiểm tra trên thực tế.
- `USER 10001:10001` ngăn application process chạy bằng container root theo mặc định. Điều này là **giảm đặc quyền**, không thay thế seccomp, capabilities, network isolation, bảo vệ secret hay cập nhật dependency.

**Mục tiêu cuối:** Một Spring Boot executable JAR chạy tốt dưới non-root; có thể kiểm chứng UID, GID, quyền tệp, working directory, endpoint và các writable paths. Không dùng `chmod -R 777` hoặc đổi `USER root` để che lỗi quyền.

## 2. `WORKDIR` thực sự làm gì?

Theo Dockerfile reference, `WORKDIR /path` đặt working directory cho các chỉ dẫn `RUN`, `CMD`, `ENTRYPOINT`, `COPY` và `ADD` **theo sau**. Nếu thư mục chưa tồn tại, Docker có thể tự tạo; điều đó **không phải cam kết** rằng một user khác về sau sẽ có quyền ghi vào nó.

Ví dụ:

```dockerfile
FROM eclipse-temurin:17-jre-jammy
WORKDIR /opt/app
COPY app.jar ./app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
```

Từ `WORKDIR /opt/app`:

- `COPY app.jar ./app.jar` đưa file vào `/opt/app/app.jar`.
- Process khi container chạy có current working directory `/opt/app`.
- `java -jar app.jar` dùng đường dẫn tương đối từ `/opt/app`.
- Nếu orchestration hoặc lệnh `docker run -w /another/path` thay working directory, đường dẫn tương đối `app.jar` có thể không còn đúng.
- Cách ổn định hơn cho entry point là `["java", "-jar", "/opt/app/app.jar"]` — đường dẫn tuyệt đối không phụ thuộc `pwd`.

**Nên dùng đường dẫn tuyệt đối cho `WORKDIR` và runtime artifact.** Tránh suy đoán default working directory của base image; nếu Dockerfile không khai báo `WORKDIR`, default thường là `/`, nhưng base image có thể đã đặt một `WORKDIR` khác.

### 2.1. `WORKDIR` liên tiếp nối đường dẫn tương đối

```dockerfile
FROM eclipse-temurin:17-jre-jammy
WORKDIR /srv
WORKDIR app
WORKDIR logs
RUN pwd
```

Trong stage này, `pwd` tại `RUN` sẽ là:

```text
/srv/app/logs
```

Vì `WORKDIR app` và `WORKDIR logs` là **đường dẫn tương đối** theo `WORKDIR` trước. Đây là cách dễ khiến file bị copy vào nơi khác kỳ vọng; dùng `WORKDIR /opt/app` nhất quán để tránh nhầm.

### 2.2. `WORKDIR` không làm thay `USER` hoặc `chown`

Hai Dockerfile sau **khác nhau về quyền**:

```dockerfile
# Chỉ chọn thư mục; chưa bảo đảm user 10001 ghi được.
WORKDIR /opt/app
USER 10001:10001
```

và:

```dockerfile
# Phân quyền rõ ràng cho thư mục dữ liệu.
RUN mkdir -p /var/app-data \
    && chown 10001:10001 /var/app-data \
    && chmod 0750 /var/app-data
WORKDIR /opt/app
USER 10001:10001
```

Đoạn thứ hai là **fragment**: cần base image và user/group phù hợp để hoàn chỉnh. Thư mục `/var/app-data` được chuẩn bị **trước** khi hạ quyền; `WORKDIR` chỉ quyết định chỗ thực thi tương đối, không tự thay đổi permission bits.

## 3. Hiểu UID, GID, owner, group và ba loại quyền Linux

Trên Linux, một file/directory thường có:

- **UID owner:** numeric user ID của chủ sở hữu.
- **GID group:** numeric group ID của nhóm sở hữu.
- **Mode bits:** quyền `r` (read), `w` (write), `x` (execute/search) cho user owner, group và others.
- **Các cơ chế khác:** ACL, SELinux/AppArmor labels, mount flags, capabilities, user namespaces có thể làm quyền truy cập khác kết luận từ `ls -l` đơn thuần.

Ví dụ:

```text
-r--r--r--  1 10001 10001  ... /opt/app/app.jar
drwxr-xr-x  2     0     0  ... /opt/app
drwxr-x---  2 10001 10001  ... /var/app-data
```

Dòng có số UID/GID ở trên là **output minh họa theo layout bài**, không phải kết quả một lệnh vừa chạy. Diễn giải:

| Đường dẫn | Mode | UID:GID | User 10001 làm được gì? |
| --- | --- | --- | --- |
| `/opt/app` | `0755` | `0:0` | Có thể đi vào, liệt kê/đọc tên; **không ghi/thêm file** |
| `/opt/app/app.jar` | `0444` | `10001:10001` | Đọc JAR, **không sửa JAR** |
| `/var/app-data` | `0750` | `10001:10001` | Đọc/ghi/tạo file, đi vào thư mục |
| `/etc/shadow` của base image | Thường hạn chế cao | `0:0` | Non-root không có quyền đọc phù hợp |

### Directory `x` không giống file `x`

Đối với directory, `x` là quyền **search/traverse**. Nếu app.jar là file readable nhưng một directory cha thiếu quyền traverse, tiến trình vẫn không mở được file.

Ví dụ chỉ cấp:

```bash
chmod 0644 /opt/app
```

trên **directory** sẽ loại quyền traverse và thường làm truy cập file bên trong lỗi. Đây là cấu hình **sai**, không phải đề xuất. Với thư mục chứa JAR, `0755` (root-owned) là convention hợp lý khi cần read/traverse; với thư mục writable riêng, `0750` (app-owned) thu hẹp quyền.

**Nguyên tắc least privilege:** chỉ cấp write ở những đường thực sự cần. Không cấp `w` cho code/config không cần sửa lúc runtime.

## 4. `USER`: hạ quyền cho tiến trình, không phải đổi owner của tất cả tệp

`USER appuser` hoặc `USER 10001:10001` đặt identity mặc định cho các `RUN` nằm sau lệnh đó trong stage và cho runtime `ENTRYPOINT`/`CMD` của stage cuối.

Ví dụ:

```dockerfile
FROM eclipse-temurin:17-jre-jammy

RUN groupadd --gid 10001 appgroup \
    && useradd --no-log-init --uid 10001 --gid 10001 \
       --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin appuser

USER 10001:10001
ENTRYPOINT ["java", "-version"]
```

- `groupadd` và `useradd` là công cụ Linux user/group trên base image Ubuntu ví dụ. Nếu image là Alpine, UBI minimal, distroless hoặc scratch, syntax/công cụ có thể khác hoặc **không tồn tại**.
- `--no-log-init` là option của `useradd` trong Debian/Ubuntu giúp tránh cập nhật log files với UID lớn theo cảnh báo Docker best practices.
- `--uid`/`--gid` dùng numeric ID cố định để làm việc rõ ràng với files, Kubernetes `runAsUser` và volumes.
- `/usr/sbin/nologin` không dùng làm shell đăng nhập; container vẫn có thể chạy `java` thông qua exec-form `ENTRYPOINT`. Nó **không tự tăng cường sandbox** hay ngăn mọi cách tiến trình bị khởi động khác.
- `USER` không “chown” các file đã có. Nếu `app.jar` root-owned và mode `0600` thì `USER 10001` không làm nó readable.
- Dockerfile có nhiều stages: `USER` của **build stage** không tự quy định user của **runtime stage**. Cần đặt `USER` ở final image stage.

### Dùng tên hay UID số?

`USER appuser` có thể hữu ích cho người đọc nhưng đòi image có account đó. `USER 10001:10001` dễ kiểm tra với orchestrator và nhất quán khi mount volume. Một số hardened base images không có `/etc/passwd` entry tương ứng; JVM/third-party library đôi khi cần home directory hoặc username lookup. Vì ví dụ tạo account thực, `10001` vẫn được ánh xạ tới tên `appuser` khi kiểm tra `id`.

**Không mặc định rằng UID 10001 luôn hợp lệ ở mọi tổ chức**: xác nhận không đụng UID dành riêng của base image, chính sách OpenShift/Kubernetes random UID, bind mounts và host user mapping. Nếu runtime bắt buộc random non-root UID, thiết kế phải cho phép **quyền đọc bằng group/others** và writable volume phù hợp thay vì hard-code ownership ở mọi nơi.

## 5. `COPY --chown` và `COPY --chmod`: chủ sở hữu khác permission

Theo Dockerfile reference, trên Linux:

```dockerfile
COPY --chown=10001:10001 --chmod=0444 app.jar /opt/app/app.jar
```

Có hai tác động độc lập:

- `--chown=10001:10001`: đặt UID/GID chủ sở hữu của **file vừa COPY**.
- `--chmod=0444`: đặt mode **read-only cho user/group/others**; không có bit `w`.
- Không có `--chown`, Docker `COPY` thông thường tạo file trong image với owner `0:0` (root), ngay cả khi ta định sẽ chạy app bằng non-root.
- `COPY --chown=appuser:appgroup` dùng tên, yêu cầu account/group tồn tại trong filesystem của stage lúc COPY; numeric IDs không cần lookup tên.
- `COPY --chmod` cần Dockerfile frontend/build tooling có hỗ trợ; mẫu dùng `# syntax=docker/dockerfile:1` với BuildKit hiện đại.

Ví dụ riêng:

```dockerfile
# Case A: app readable nhưng root sở hữu.
COPY --chmod=0444 app.jar /opt/app/app.jar

# Case B: app UID/GID sở hữu file, mode vẫn chỉ đọc.
COPY --chown=10001:10001 --chmod=0444 app.jar /opt/app/app.jar

# Case C: chỉ dùng để minh họa cấu hình KHÔNG nên làm.
# RUN chmod -R 777 /opt/app
```

**Case A không sai mặc định** nếu JAR chỉ cần đọc và directory có traverse permission. Không phải mọi file ứng dụng đều bắt buộc phải thuộc về non-root. Nhiều cấu hình an toàn hơn khi **JAR/config root-owned nhưng readable**, vì process non-root không tự thay chúng được. Case B giúp minh họa `--chown` nhưng mode `0444` vẫn ngăn user tự viết lên file trong điều kiện quyền POSIX thông thường.

### Vì sao `COPY --chown` tốt hơn chạy `chown -R` sau COPY?

Đối với tập file lớn, gắn owner ngay tại `COPY` thường gọn và tránh thêm bước thay đổi metadata toàn bộ cây thư mục trong layer sau đó. `RUN chown -R /opt/app` đôi khi tăng chi phí build/layer và còn dễ cấp write quyền rộng hơn ý định. Chỉ `chown` đúng **thư mục dữ liệu** cần ghi khi cần; không blanket-owner toàn bộ root filesystem.

### Bối cảnh là Linux containers

`COPY --chown` và `--chmod` theo Dockerfile reference dành cho Linux containers, không áp dụng y hệt trên Windows containers. Các ví dụ quyền `0750`, `uid/gid` và `useradd` cũng là ngữ nghĩa Linux. Không copy nguyên sang Windows Server Core container rồi kỳ vọng hoạt động.

## 6. Ví dụ Java 17 Spring Boot hoàn chỉnh

Một REST endpoint đơn giản trả về chuỗi `Hello non-root`. Ứng dụng **không cần ghi bất kỳ file nào vào `/opt/app`**, giúp việc phân quyền rõ ràng. Các ví dụ lệnh Docker sau đó sẽ kiểm chứng JAR readable, vùng dữ liệu writable và user thực thi.

Cấu trúc project Maven:

```text
ownership-demo/
├── pom.xml
├── Dockerfile
├── .dockerignore
└── src/
    ├── main/java/dev/example/ownership/
    │   ├── OwnershipDemoApplication.java
    │   └── HelloController.java
    └── test/java/dev/example/ownership/
        └── HelloControllerTest.java
```

### 6.1. `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>ownership-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Starter parent quản lý dependency/plugin versions và execution của `repackage` khi `spring-boot-maven-plugin` được khai báo. Sau `mvn clean verify`, `target/ownership-demo-1.0.0.jar` là **Spring Boot executable JAR**, với loader/`BOOT-INF/classes`/`BOOT-INF/lib`. Dockerfile sẽ copy **đúng tệp này**, không copy `.jar.original` hoặc một plain JAR thiếu runtime libraries.

### 6.2. Main class

`src/main/java/dev/example/ownership/OwnershipDemoApplication.java`:

```java
package dev.example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OwnershipDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OwnershipDemoApplication.class, args);
    }
}
```

### 6.3. REST controller

`src/main/java/dev/example/ownership/HelloController.java`:

```java
package dev.example.ownership;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello non-root";
    }
}
```

### 6.4. Unit/web test

`src/test/java/dev/example/ownership/HelloControllerTest.java`:

```java
package dev.example.ownership;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HelloControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void helloWorks() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello non-root"));
    }
}
```

Test này bảo đảm Spring context và endpoint hoạt động khi Maven chạy test; **nó không khẳng định image có `USER` đúng**. Dockerfile cần được build, kiểm tra `id`/permissions và smoke test container riêng.

## 7. Dockerfile multi-stage chuẩn: Maven build bằng JDK, chạy bằng JRE non-root

Dưới đây là Dockerfile hoàn chỉnh cho chính source ở mục 6.

`Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: build + test, không đưa Maven/JDK build vào runtime image.
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src

COPY pom.xml ./
COPY src ./src
RUN mvn -B -ntp clean verify

# Stage 2: runtime tối thiểu có JRE 17, không dùng build stage user.
FROM eclipse-temurin:17-jre-jammy

# Thực hiện setup bằng root ở thời điểm build.
RUN groupadd --gid 10001 appgroup \
    && useradd --no-log-init --uid 10001 --gid 10001 \
       --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin appuser \
    && mkdir -p /opt/app /var/app-data \
    && chmod 0755 /opt/app \
    && chown 10001:10001 /var/app-data \
    && chmod 0750 /var/app-data

WORKDIR /opt/app

# JAR đọc được nhưng không sửa được ở runtime.
COPY --from=build --chown=10001:10001 --chmod=0444 \
    /src/target/ownership-demo-1.0.0.jar /opt/app/app.jar

# Mọi tiến trình chính chạy UID/GID thường, không phải root.
USER 10001:10001

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
```

**Phân tích từng bước:**

1. `FROM maven:3.9-eclipse-temurin-17 AS build` cung cấp Maven/JDK cho build. Tag là ví dụ; production có thể pin digest và lưu BOM/SBOM.
2. `WORKDIR /src` bảo đảm `pom.xml` và `src/` được copy vào đúng vị trí cho Maven.
3. `RUN mvn -B -ntp clean verify` chạy compile/test/package trong **builder**. Không chọn `-DskipTests` khi đây là required QA build.
4. `FROM eclipse-temurin:17-jre-jammy` mở **stage mới** chỉ có runtime Java 17 trên Ubuntu; build tools/source không tự xuất hiện trong image cuối.
5. `groupadd`/`useradd` tạo nhóm/tài khoản Linux với UID/GID `10001`. Các lệnh setup cần quyền root tại **build time**, không có nghĩa app runtime phải chạy root.
6. `mkdir -p /opt/app /var/app-data` tạo directories. `/opt/app` giữ root-owned với mode `0755` để app **đọc/đi qua nhưng không ghi**.
7. `chown 10001:10001 /var/app-data && chmod 0750 /var/app-data` cấp write chỉ cho thư mục data cần thiết.
8. `WORKDIR /opt/app` đặt working directory thực tế của process. `ENTRYPOINT` lại dùng đường dẫn tuyệt đối để tránh lỗi nếu orchestration override working directory.
9. `COPY --from=build ... --chown=10001:10001 --chmod=0444` chuyển **duy nhất executable JAR** từ builder sang runtime, không copy cả source/target directory. User app có thể đọc file, nhưng không có bit write.
10. `USER 10001:10001` làm default runtime identity. Hai số phải được kiểm tra trùng với chủ sở hữu volume/directory cần ghi.
11. `EXPOSE 8080` chỉ là **metadata khai báo cổng mà image dự kiến nghe**. Nó không publish cổng ra host; muốn truy cập từ máy cần `docker run -p ...` hoặc network/orchestration tương ứng.
12. Exec-form `ENTRYPOINT ["java", "-jar", ...]` không bọc ứng dụng trong `sh -c`, giúp JVM là process chính và xử lý signal/exit code theo cách trực tiếp hơn.

**Một lưu ý hữu ích:** Đặt `USER` gần cuối runtime stage là một convention rõ ràng. Nếu đặt `USER 10001` trước `RUN groupadd/useradd/chown`, các lệnh setup có thể báo `Operation not permitted`. Nếu dùng `COPY --chown=appuser:appgroup` theo tên, tài khoản/group phải được tạo trước `COPY` trong stage đó. Bài dùng numeric IDs để hạn chế lookup ambiguities.

## 8. `.dockerignore` và build context

Tệp `.dockerignore` trong project mẫu:

```dockerignore
.git
target/
build/
.gradle/
.idea/
*.log
*.iml
.env
```

Dockerfile multi-stage ở mục 7 chỉ cần `pom.xml` và `src/` từ build context, nên bỏ `target/` của host khỏi context là **hợp lý**: image không phụ thuộc vào artifacts cũ còn nằm trên máy người lập trình. `.env` là ví dụ dữ liệu môi trường không nên đưa vào image build context.

Từ thư mục chứa `pom.xml`, `Dockerfile`, `src`, thực hiện:

```bash
docker build --pull -t ownership-demo:local .
```

- Dấu `.` là **build context root**, không phải tùy chọn chỉ current Dockerfile.
- `--pull` yêu cầu kiểm tra base image mới hơn cho tag được chọn, nhưng **không đảm bảo provenance/immutability**. Ở CI production, pin digest và áp dụng image scanning theo policy.
- Docker build sẽ chạy Maven test trong builder stage. Nếu test fail, build image sẽ fail, không ra một bản release image “xanh” giả.
- Nếu repository có thêm dependencies vào code generator hoặc tệp nằm ngoài `src` và `pom.xml`, Dockerfile phải copy đúng inputs đó. Ví dụ cố ý tối giản.

**Không dùng `COPY . .` một cách vô điều kiện** trong runtime stage: có thể mang theo `.git`, build output, file môi trường, credential hay source không cần thiết. Hãy copy đúng executable JAR và những runtime resources đã được duyệt.

## 9. Kiểm chứng image và user/permissions bằng Docker

Sau khi build thành công, có thể kiểm tra image **mà không mở web server** bằng cách override entrypoint sang `sh` (base image Ubuntu ví dụ có shell).

### 9.1. Kiểm tra image config

```bash
docker image inspect --format '{{.Config.User}}' ownership-demo:local
docker image inspect --format '{{.Config.WorkingDir}}' ownership-demo:local
```

Với Dockerfile mẫu, hai dòng kết quả dự kiến:

```text
10001:10001
/opt/app
```

Đây là **kiểm tra metadata**, chưa bảo đảm mọi thư mục được chmod đúng. Dùng thêm kiểm tra runtime thực.

### 9.2. Đọc identity thực khi container chạy

```bash
docker run --rm --entrypoint sh ownership-demo:local -c 'id; pwd'
```

Output tiêu biểu (format `id` tùy implementation):

```text
uid=10001(appuser) gid=10001(appgroup) groups=10001(appgroup)
/opt/app
```

- `--entrypoint sh` chỉ dành cho **kiểm thử image**, thay `ENTRYPOINT java` trong lần chạy này.
- `USER` của image vẫn áp dụng vì ta **không** truyền `--user 0`.
- `pwd` xác nhận `WORKDIR` là `/opt/app`.
- Không cần cài `sudo` trong image để kiểm chứng quyền.

### 9.3. Kiểm tra owner/mode qua numeric stat

```bash
docker run --rm --entrypoint sh ownership-demo:local \
  -c 'stat -c "%u:%g %a %n" /opt/app /opt/app/app.jar /var/app-data'
```

Kết quả mong đợi theo Dockerfile:

```text
0:0 755 /opt/app
10001:10001 444 /opt/app/app.jar
10001:10001 750 /var/app-data
```

Giá trị numeric mode hiển thị từ `stat` thường không có số 0 ở trước. Dockerfile sử dụng `0444`/`0750`, còn `stat -c %a` thường in `444`/`750`.

### 9.4. Thử quyền thật của process

```bash
docker run --rm --entrypoint sh ownership-demo:local \
  -c 'test -r /opt/app/app.jar && \
      test ! -w /opt/app/app.jar && \
      test ! -w /opt/app && \
      test -w /var/app-data && \
      echo "PASS: least-privilege file permissions"'
```

Nếu đúng layout ở mục 7, output:

```text
PASS: least-privilege file permissions
```

Tại sao kiểm tra `test -w` có ý nghĩa? Vì không chỉ đọc metadata mode/owner, ta yêu cầu chính user của container thực hiện access checks. Trên filesystem có ACL, user namespace hoặc mount policies đặc biệt, hành vi thực tế mới là điều cần quan sát.

**Không chạy lệnh kiểm tra với `docker run --user 0`**, vì khi đó root có khả năng vượt qua nhiều DAC checks, làm việc kiểm tra non-root mất ý nghĩa.

## 10. Chạy Spring Boot và smoke test endpoint

Bắt đầu container (Linux/macOS/Windows PowerShell, Docker CLI như nhau):

```bash
docker run --rm --name ownership-demo \
  -p 127.0.0.1:8080:8080 \
  ownership-demo:local
```

**Lưu ý hệ điều hành:** Lệnh trình bày nhiều dòng với `\` là Bash syntax. Trong PowerShell, dùng **một dòng** sau:

```powershell
docker run --rm --name ownership-demo -p 127.0.0.1:8080:8080 ownership-demo:local
```

- `-p 127.0.0.1:8080:8080` publish cổng 8080 ra **loopback của Docker host** cho kiểm thử local. Không tự mở ra mọi giao diện mạng như `-p 8080:8080` thường làm.
- Spring Boot embedded server mặc định dùng `server.port=8080` khi không cấu hình khác; ứng dụng mẫu có controller `/hello`.
- Container startup tạo process Java với `USER 10001:10001` mặc định. Port 8080 là cổng không đặc quyền trên Linux thông thường, nên không cần root chỉ để bind cổng này.

Ở **terminal thứ hai** sau khi log báo ứng dụng khởi động:

```bash
curl -fsS http://127.0.0.1:8080/hello
```

Body HTTP mong đợi:

```text
Hello non-root
```

Nếu process không khởi động, xem logs; đừng chuyển sang `USER root` trước khi kiểm tra permission. Nếu image đã chạy tên `ownership-demo` rồi, Docker báo conflict tên; dừng container cũ hoặc dùng tên khác. `--rm` sẽ tự dọn container khi nó kết thúc, không xóa image.

## 11. Quyền tệp trong image khác quyền của bind mount và volume

Đây là lỗi phổ biến nhất khi áp dụng non-root. Giả sử image đã có:

```text
/var/app-data -> owner 10001:10001, mode 0750
```

Sau đó người vận hành bind mount một thư mục host vào đúng đường đó:

```bash
docker run --rm \
  --mount type=bind,src=/srv/ownership-demo-data,dst=/var/app-data \
  ownership-demo:local
```

**Đây là fragment minh họa dành cho Linux host thực sự có thư mục `/srv/ownership-demo-data`.** Nó không phải lệnh portable sang mọi máy. Khi bind mount, nội dung/quyền của mount **che khuất** directory tương ứng trong image. Việc `chown` thư mục image lúc build **không tự sửa ownership của host directory**.

Hệ quả:

- Nếu host directory chỉ root có quyền ghi, process UID 10001 có thể nhận `Permission denied`.
- Nếu Docker daemon dùng user namespace remapping/rootless engine, numeric host UID/GID nhìn từ container có thể được ánh xạ; không đồng nhất một cách máy móc mọi UID trên host và container.
- Nếu Docker Desktop chia sẻ filesystem từ Windows/macOS, cơ chế permissions có thể khác native Linux; phải kiểm tra trong container thực.
- Nếu mount nằm đè lên `/opt/app`, nó có thể **che cả app.jar** đã COPY trong image; `java -jar /opt/app/app.jar` lúc này báo không tìm thấy file.

### Xử lý đúng khi mount cần ghi

1. Xác định process UID/GID trong container bằng `id`.
2. Kiểm tra file/dir permissions tại đúng **mount path** bằng `stat`/`ls -ldn` và thử `test -w` hoặc một thao tác ghi an toàn.
3. Với native Linux bind mount, chuẩn bị host directory ownership/ACL **bằng quản trị host phù hợp** cho UID/GID/namespace mapping. Không mặc định dùng `chmod 777`.
4. Nếu dùng Docker named volume, chú ý Docker volume có lifecycle và initialization rules riêng; xem owner thực sau mount, không suy rằng `chown` trong image luôn thắng.
5. Khi dùng Kubernetes PVC, kiểm tra StorageClass/CSI driver, `fsGroup` support và pod security policy; không tự động `chown -R` toàn bộ volume lớn mỗi lần app startup.
6. Nếu ứng dụng không thực sự cần ghi lâu dài, **không cấp volume writable chỉ vì tiện**.

### Không để app tự `chown` khi startup

Một non-root process thường **không có đặc quyền đổi owner** cho mọi file. Tạo init script chạy root để `chown -R` rồi hạ quyền có thể tăng surface attack và làm startup chậm, nhất là volume nhiều file. Khi cần init container hoặc một bước provision volume có đặc quyền, đó phải là thiết kế vận hành được giới hạn quyền, được audit và có kế hoạch ownership rõ ràng.

## 12. `readOnlyRootFilesystem` và `/tmp` với Spring Boot

Bên cạnh `USER`, runtime có thể áp dụng filesystem read-only:

```bash
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 \
  -p 127.0.0.1:8080:8080 \
  ownership-demo:local
```

Điều kiện:

- Image mẫu không ghi vào `/opt/app` và không có persistent write requirement trong application code.
- `--read-only` biến root filesystem layer của container thành read-only; nó **không cấm** writable mounts/tmps riêng.
- `--tmpfs /tmp:...` tạo vùng ghi tạm ở `/tmp`. Spring Boot/Tomcat/JVM hoặc thư viện nào đó có thể cần temp files khi khởi động; kích thước 64 MiB chỉ là **giá trị học tập**, cần tăng/đo theo workload thật.
- `mode=1777` cho phép các user dùng temp directory theo cơ chế sticky bit, giống directory `/tmp` phổ biến.
- Trong chế độ này, `/var/app-data` trên root filesystem **không còn writable**, dù image từng `chown` directory cho UID 10001. Nếu app cần ghi data, gắn writable volume/tmpfs riêng **và** kiểm tra ownership sau mount.
- Nếu runtime cần viết heap dump, GC log file, uploaded files hoặc embedded DB ở path khác, phải định tuyến các output đó tới volume/path được cấp quyền hoặc thay workload design.

Một lệnh kiểm tra bổ sung:

```bash
docker run --rm --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 \
  --entrypoint sh ownership-demo:local \
  -c 'test -w /tmp && test ! -w /opt/app && echo "PASS: read-only root with writable tmp"'
```

Nếu mount/permission chính xác, output:

```text
PASS: read-only root with writable tmp
```

**Cẩn thận:** Không dùng `--read-only` làm “mẹo sửa quyền” để ứng dụng chạy. Nó là ràng buộc mạnh hơn, thường lộ ra những write paths chưa được thiết kế. Với app cần database file hoặc upload bền vững, phải cấp volume hợp lệ và quản lý lifecycle.

## 13. Kubernetes: `runAsNonRoot`, `runAsUser`, `runAsGroup` và `fsGroup`

Trong Kubernetes, image Dockerfile không phải nguồn quyền duy nhất. Một Pod có `securityContext` có thể override runtime identity; một volume có quyền do CSI/storage backend quyết định. Ví dụ fragment cho container đã được push/load vào cluster:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ownership-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ownership-demo
  template:
    metadata:
      labels:
        app: ownership-demo
    spec:
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          image: ownership-demo:local
          imagePullPolicy: Never
          ports:
            - containerPort: 8080
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
```

**Đây là ví dụ local cluster**: `imagePullPolicy: Never` đòi image `ownership-demo:local` đã được load vào **chính node** mà Pod chạy (ví dụ kind/minikube load image workflow). Nếu chưa có image trên node, Pod sẽ không khởi động; đó không phải lỗi `USER`. Trong production, hãy dùng image từ registry được kiểm soát, pin digest và cấu hình pull policy thích hợp.

Giải thích:

- `runAsUser: 10001`: chỉ định UID process.
- `runAsGroup: 10001`: chỉ định primary GID. Không bỏ qua thông số này rồi ngầm kết luận process không thuộc root group.
- `runAsNonRoot: true`: kubelet yêu cầu container không chạy như UID 0; nó là guard, không tự cấp quyền cho mounted files.
- `allowPrivilegeEscalation: false`: hạn chế cơ chế tăng đặc quyền của tiến trình theo cơ chế runtime/kernel; không thay `runAsNonRoot`.
- `capabilities.drop: ["ALL"]`: drop Linux capabilities được cấp theo mặc định, phù hợp service chỉ cần HTTP 8080. Workload khác cần capability đặc biệt phải phân tích có giới hạn, không thêm `SYS_ADMIN` một cách tùy tiện.
- `readOnlyRootFilesystem: true`: root layer không writable; `emptyDir` ở `/tmp` cấp vùng tạm. **Owner/mode của emptyDir thực tế vẫn cần kiểm chứng**, nhất là khi chạy theo UID ngẫu nhiên hoặc có security policy riêng.
- `seccompProfile.type: RuntimeDefault`: sử dụng seccomp profile mặc định của container runtime nếu được hỗ trợ.
- `fsGroup` (không có trong mẫu vì không mount PVC) có thể hỗ trợ access permissions cho một số volumes, nhưng behavior phụ thuộc volume type/CSI driver và các chính sách `fsGroupChangePolicy`. **Không** coi nó là một lệnh `chown` universal cho mọi mount.

### `fsGroup` và writable PVC

Khi cần persistent volume, Pod-level security context có thể có:

```yaml
securityContext:
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
  fsGroupChangePolicy: OnRootMismatch
```

Đây là **fragment**, phải đặt đúng dưới `spec.template.spec.securityContext` của Deployment/Pod, và cần volume/storage class phù hợp. `fsGroupChangePolicy` chỉ có hiệu lực với loại volume hỗ trợ chính sách đó; không phải phép bảo đảm mọi PVC/bind mount ngay lập tức được owner 10001. Với một số CSI drivers, việc điều chỉnh ownership được ủy quyền cho driver.

### OpenShift/random UID

Một số cluster áp đặt UID khác với `USER` được định nghĩa trong image. Khi đó:

- Hãy biết rõ UID/GID thực của process trong Pod và allowed security context constraints.
- JAR/config thường nên **readable** ngay cả với UID khác.
- Vùng writable nên dựa trên group/volume ACL phù hợp, không giả định mọi Pod đều chạy đúng UID 10001.
- Không “sửa” bằng cách ép Pod `privileged: true` hoặc container root nếu policy không cho phép.

## 14. Bản Dockerfile khi JAR đã được build ngoài Docker

Đôi khi CI chạy Maven trước, sau đó Docker chỉ đóng gói **artifact đã qua QA**. Lúc này bạn không cần build stage chứa Maven; thay vào đó Dockerfile có thể chỉ có runtime stage. Ví dụ **Dockerfile.runtime**:

```dockerfile
# syntax=docker/dockerfile:1
FROM eclipse-temurin:17-jre-jammy

RUN groupadd --gid 10001 appgroup \
    && useradd --no-log-init --uid 10001 --gid 10001 \
       --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin appuser \
    && mkdir -p /opt/app /var/app-data \
    && chmod 0755 /opt/app \
    && chown 10001:10001 /var/app-data \
    && chmod 0750 /var/app-data

WORKDIR /opt/app
COPY --chown=10001:10001 --chmod=0444 \
    target/ownership-demo-1.0.0.jar /opt/app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
```

Lúc này phải **chủ động thay `.dockerignore` của mục 8**, vì nó đang ignore `target/`. Nếu giữ ignore `target/`, `COPY target/...jar` sẽ thất bại dù Maven đã tạo JAR ở filesystem host.

Workflow tương ứng:

```bash
mvn -B -ntp clean verify
docker build -f Dockerfile.runtime -t ownership-demo:prebuilt .
```

Điều kiện là `Dockerfile.runtime` và `target/ownership-demo-1.0.0.jar` được đưa vào build context, và file là **executable Boot JAR**, không phải `.jar.original` hoặc plain archive. Khi dùng mô hình CI hai bước, có lợi thế dễ liên kết JAR SHA-256 đã kiểm tra với image; nhưng cũng cần bảo đảm Docker chỉ COPY đúng artifact đã test.

**Chỉ chọn một trong hai chiến lược cho một workflow rõ ràng:**

- **Multi-stage** ở mục 7: Maven build + test bên trong Docker build stage, runtime image chỉ có JRE/JAR.
- **Prebuilt artifact** ở mục 14: Maven build + test ở CI, Dockerfile chỉ COPY JAR đã xác minh.

Không vô tình build lại JAR với khác dependency/version trong Docker khi CI định deploy chính artifact đã ký/qua QA ở bước trước.

## 15. ENTRYPOINT, CMD, signal và lý do tránh `sh -c`

`USER` xác định quyền, còn `ENTRYPOINT`/`CMD` xác định tiến trình. Ví dụ tốt:

```dockerfile
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
```

Đây là **exec form**. Java process trở thành tiến trình chính của container, nhận signal từ Docker/Kubernetes theo runtime behavior, và exit code truyền rõ cho container lifecycle. Điều này phù hợp với Spring Boot graceful shutdown khi ứng dụng được cấu hình và cho đủ thời gian dừng.

Tránh shell form không cần thiết:

```dockerfile
ENTRYPOINT java -jar /opt/app/app.jar
```

Shell form thường được chạy thông qua shell và có thể ảnh hưởng signal forwarding, shell expansion và PID 1. Nếu cần dùng shell để chuẩn bị environment, hãy giải thích vì sao, đảm bảo dùng `exec java ...` ở bước cuối và không cần root khi runtime.

### Truyền JVM option an toàn

Khi cần memory/runtime flags:

```dockerfile
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "/opt/app/app.jar"]
```

Đây là **fragment thay dòng ENTRYPOINT**, không dùng đồng thời hai ENTRYPOINT. JVM options phải đứng trước `-jar`; Spring Boot application args như `--server.port=8081` được truyền **sau** JAR hoặc qua environment phù hợp.

Nếu dùng `JAVA_TOOL_OPTIONS`, nhớ giá trị environment có thể xuất hiện trong logs/diagnostics. Không đưa secrets vào Dockerfile `ENV` hoặc `ARG` vì image metadata/build history có thể làm lộ chúng; dùng secret managers/runtime injection.

## 16. Phần khác nhau giữa Docker non-root và rootless Docker

Hai khái niệm thường bị nhầm:

- **Non-root container process:** ứng dụng **bên trong container** chạy với UID không phải 0 (ví dụ `USER 10001:10001`).
- **Rootless Docker Engine/user namespace:** Docker daemon/host-side container mapping được cấu hình để không phụ thuộc vào host root theo một số workflow hoặc remap UID/GID.

Chúng giải quyết các tầng khác nhau. Một container có `USER 10001` chạy trên Docker daemon rootful vẫn là **non-root trong container**, nhưng Docker daemon có quyền riêng trên host. Ngược lại, rootless engine không tự bảo đảm image/application không có lỗi phân quyền. Không xem `USER` là đủ để tránh rủi ro khi mount Docker socket hoặc dùng `--privileged`.

Để tăng khả năng phòng thủ, ngoài `USER non-root` có thể áp dụng:

- Không dùng `--privileged`.
- Drop capabilities không cần thiết, hạn chế privilege escalation.
- Dùng read-only root filesystem với writable tmpfs/volume được chuẩn bị đúng.
- Không mount `/var/run/docker.sock` hay host paths nhạy cảm vào app container.
- Giới hạn network egress, resources, syscalls theo môi trường.
- Pin base image digest, scan vulnerabilities và cập nhật image thường xuyên.
- Lưu secrets qua runtime mechanism có kiểm soát; không bake vào JAR/image layer.

## 17. Khi nào cần owner là root, khi nào là appuser?

Một ngộ nhận là “mọi file trong image phải `chown appuser`”. Thực tế nên thiết kế theo **mục đích truy cập**:

| Thành phần | Owner gợi ý | Mode gợi ý | Lý do |
| --- | --- | --- | --- |
| `/opt/app` directory | `root:root` | `0755` | App chỉ traverse/read, không tự thay code |
| `/opt/app/app.jar` | `root:root` **hoặc** `10001:10001` | `0444`/`0644` | App chỉ đọc; mode quan trọng ngang owner |
| `/etc/app/config.yml` không có secret | `root:root` | `0644` hoặc chặt hơn | App chỉ đọc cấu hình |
| `/etc/app/secret-file` | Theo secret manager/mount | Quyền tối thiểu cho app | Không đưa secret vào image build |
| `/var/app-data` | `10001:10001` hoặc group ACL | `0750`/`0770` tùy chia sẻ | App được ghi dữ liệu có chủ đích |
| `/tmp` | Theo runtime mount | Sticky mode `1777` thường dùng | Nhiều process/Java có thể cần tạo temp file |
| Log ứng dụng | stdout/stderr | Không cần writable app log directory | Container logging collects streams |
| JVM heap dump/GC file logs | Writable volume có giới hạn | Theo UID/GID app | Chỉ khi bật flags cần ghi file |

Bảng là **các lựa chọn thiết kế**, không phải chmod đúng cho mọi tổ chức. Nếu cần group sharing giữa nhiều process hoặc random UID, mode/ACL và group permissions phải được đánh giá lại. Không nên cấp world-write chỉ để giảm công cấu hình.

### Ghi log: stdout/stderr thường tốt hơn file trong WORKDIR

Ứng dụng Spring Boot container nên mặc định log ra stdout/stderr để runtime thu thập. Nếu cấu hình `logging.file.name=/opt/app/app.log` trong khi `/opt/app` không writable, có thể gây lỗi. Thay vì đổi quyền toàn bộ code directory, ưu tiên stdout hoặc chuyển file log sang volume có owner/group phù hợp nếu policy yêu cầu.

## 18. Những lỗi thực tế và cách chẩn đoán

| Triệu chứng | Nguyên nhân phổ biến | Bước kiểm tra/sửa |
| --- | --- | --- |
| `java -jar app.jar`: unable to access jarfile | `WORKDIR` khác vị trí JAR hoặc file thiếu quyền đọc | `docker image inspect` WorkingDir, `pwd`, `stat` JAR; dùng absolute path |
| `Permission denied` khi đọc JAR | File mode `0600` root-owned, directory cha thiếu traverse | `id`, `stat -c '%u:%g %a %n'` trên cả file/dirs; chỉ cấp quyền đọc/traverse cần thiết |
| `Permission denied` khi ghi `/opt/app` | Directory được thiết kế code-only, mode `0755` root-owned | Không chown code; chuyển output sang `/var/app-data` hoặc volume |
| `Permission denied` khi ghi `/var/app-data` | Host bind mount/PVC che owner/mode image | Inspect mounted path, sửa volume ownership/ACL hoặc fsGroup policy |
| `USER appuser` báo unknown user | Account chưa được tạo trong final stage hoặc base image không có passwd | Tạo account ở runtime stage; có thể dùng numeric UID |
| `RUN apt-get`/`useradd` lỗi sau `USER 10001` | Đã hạ quyền trước setup | Đưa setup commands trước `USER`, không cần runtime root |
| Dùng `COPY --chown=appuser:appgroup` rồi fail | Tên chưa tồn tại tại COPY time | Tạo group/user trước hoặc dùng numeric chown |
| `COPY --chown` không có tác dụng như mong đợi | Dùng Windows container hoặc stage/context không đúng | Kiểm tra Dockerfile syntax, platform, Dockerfile frontend và `stat` |
| Container chạy `uid=0(root)` dù Dockerfile có USER | `docker run --user 0`, Kubernetes securityContext override, image khác | Inspect final image config và runtime process ID; xem deployment spec |
| Docker image build được nhưng app không start | Copy nhầm plain JAR hoặc dependencies không có | `jar tf` tìm `BOOT-INF/lib`, chạy `java -jar` artifact; kiểm tra build stage |
| Spring Boot lỗi tạo temp directory | Read-only root filesystem hoặc `/tmp` không writable | Cấp tmpfs/volume `/tmp` với quyền/mode/size phù hợp |
| Chạy local Docker okay nhưng Kubernetes fails | UID/GID khác, readOnlyRootFilesystem, PVC/CSI policy | Đọc Pod securityContext và mounted paths, `kubectl logs` |
| Mount vào `/opt/app` làm mất app.jar | Bind mount che nội dung image | Không mount đè code directory; mount riêng data/config path |
| App không bind port 80 non-root | Privileged port/capabilities/sysctl và runtime policy | Dùng port không đặc quyền như 8080; mapping host port/reverse proxy bên ngoài |
| `EXPOSE 8080` mà host không truy cập được | EXPOSE chỉ metadata | Dùng `docker run -p`/service/network; kiểm tra interface bind và firewall |
| `chmod -R 777` “sửa” lỗi nhưng mất an toàn | Cấp world-write quá rộng | Thu hẹp write paths và owner/group/ACL; rollback chmod rộng |
| Build dùng Gradle nhưng Dockerfile tìm `target/*.jar` | Maven và Gradle outputs khác nhau | Với Gradle dùng `build/libs/` và chọn đúng `bootJar`, không dùng `-plain.jar` |
| Runtime image báo `sh: not found` khi debug | Base image distroless/minimal không có shell | Dùng image debug phù hợp hoặc inspect metadata/tooling ngoài; không thêm shell vào production chỉ để debug |
| Build image cùng tag nhưng khác binary | Base image tag trôi, JAR build lại, input khác | Pin base digest, lưu source commit và image/JAR digest; deploy đúng artifact QA |

### Quy trình điều tra theo lớp

1. **Xác định image thực chạy**: tag, digest, runtime spec. Đừng chẩn đoán nhầm image đã build nhưng chưa deploy.
2. **Xác định process identity**: `docker image inspect ...Config.User` hoặc `docker run --entrypoint sh ... -c id`, Kubernetes `runAsUser` và thực tế trong Pod.
3. **Xác định current working directory**: `WORKDIR`/`docker run -w`/Kubernetes `workingDir`, và đường JAR trong `ENTRYPOINT`.
4. **Xem permissions của cả đường dẫn**: UID/GID/mode file, directory cha, mount options, ACL/SELinux.
5. **Kiểm tra runtime write paths**: `/tmp`, uploaded files, logs, cache, heap dumps, embedded database, certificate store.
6. **Kiểm tra archive**: executable Boot JAR hay plain JAR; Java version và dependencies.
7. **Kiểm tra volumes**: mount có che file không, owner runtime khác image, fsGroup/CSI hỗ trợ ra sao.
8. **Sửa Dockerfile/securityContext/volume provisioning có chủ đích**, build lại, test quyền và smoke test — không bypass bằng root nếu không thật sự cần.

## 19. Các tình huống tự kiểm tra

**Tình huống A:** `WORKDIR /opt/app` được khai báo và `USER 10001:10001`, nhưng `app.jar` root-owned `0600`. App chạy được không?

*Đáp án:* Không theo permission POSIX thông thường. `WORKDIR` không cấp quyền đọc; app user không có quyền đọc file root-owned `0600`. Có thể giữ root owner nhưng đổi mode đọc phù hợp (`0644`/`0444`) hoặc set ownership/mode theo policy.

**Tình huống B:** `app.jar` owner là `10001` nhưng mode `0444`. App có thể tự sửa JAR không?

*Đáp án:* Không, vì bit `w` không được cấp cho owner. Ownership không đồng nghĩa full permissions.

**Tình huống C:** Dockerfile `COPY --chown=10001:10001 ... /var/app-data` đúng, nhưng khi dùng bind mount thì app vẫn không ghi được. Vì sao?

*Đáp án:* Bind mount che filesystem path trong image; quyền được quyết định bởi mounted path/host mapping. Cần inspect permissions của mount và chuẩn bị host/volume, không chỉ xem image layer.

**Tình huống D:** Đặt `USER 10001` rồi chạy `RUN groupadd ...` trong Dockerfile và gặp lỗi. Sửa sao?

*Đáp án:* Lệnh tạo group/user cần đặc quyền build-time trên base image; đặt nó trước `USER`. Runtime vẫn hạ quyền.

**Tình huống E:** Dockerfile không khai báo `WORKDIR` nhưng dùng `ENTRYPOINT ["java","-jar","app.jar"]`. Có an toàn không?

*Đáp án:* Không nên dựa vào default working directory không xác định rõ của base image. Đặt `WORKDIR /opt/app` và dùng `/opt/app/app.jar` tuyệt đối trong entrypoint.

**Tình huống F:** `docker run --read-only` làm Tomcat báo lỗi tạo temp file mặc dù JAR readable. Vì sao?

*Đáp án:* Read-only root layer cấm ghi file tạm; cần cấp tmpfs hoặc volume cho đường thực tế mà JVM/Tomcat dùng, chẳng hạn `/tmp`, với quyền đúng.

**Tình huống G:** Kubernetes `runAsNonRoot: true` nhưng PV owner root và mode `0700`. Pod chắc chắn ghi được không?

*Đáp án:* Không. `runAsNonRoot` chỉ ràng buộc process UID; volume access cần filesystem permissions/ACL hoặc storage driver `fsGroup` support phù hợp. Không dùng root để che lỗi.

**Tình huống H:** Docker `EXPOSE 8080` có làm port truy cập được từ browser host không?

*Đáp án:* Không. Phải publish cổng qua `-p` hoặc cấu hình container network/orchestration; `EXPOSE` chỉ khai báo thông tin về cổng.

**Tình huống I:** Người vận hành đặt `docker run --user 0` cho image có `USER 10001:10001`. Runtime còn non-root không?

*Đáp án:* Không. `--user` override default image identity. Vì vậy CI/production cần inspect runtime spec, không chỉ Dockerfile.

**Tình huống J:** Cần dùng UID tùy ý do nền tảng cấp. Có nên cố đổi quyền toàn bộ filesystem sang `10001`?

*Đáp án:* Không. Thiết kế code files readable cho UID được phép, writable volumes bằng group/ACL/`fsGroup`, và kiểm tra thật theo platform constraints.

## 20. Checklist kiểm chứng Dockerfile trước khi phát hành

**Đường dẫn và nội dung image:**

- `WORKDIR` là đường dẫn tuyệt đối, ổn định; `ENTRYPOINT` dùng absolute JAR path.
- Chỉ copy Spring Boot **executable JAR** vào runtime stage; không mang source, Maven cache hoặc secrets.
- Image runtime dùng JRE/JDK cần thiết, không mặc định chứa full build tools.
- `.dockerignore` hợp với chiến lược multi-stage hoặc prebuilt-jar, không vô tình loại artifact cần copy.

**Owner, mode và user:**

- Final stage khai báo `USER` non-root với UID/GID được quản lý.
- Có bằng chứng `id`/image inspect về UID/GID runtime; không bị `--user 0`/orchestrator override.
- Tệp code/config readable nhưng không tùy ý writable bởi ứng dụng.
- Thư mục dữ liệu thật sự cần ghi được chuẩn bị đúng UID/GID/mode; tránh `chmod 777`.
- Directory cha có quyền traverse; kiểm tra cả file lẫn directory.
- `COPY --chown` và `COPY --chmod` được dùng đúng stage và Dockerfile frontend.

**Runtime và storage:**

- Spring Boot khởi động ở port không đặc quyền như 8080; `EXPOSE` không được nhầm với `-p`.
- `/tmp` và những write paths thực tế được cấp chỗ ghi khi bật read-only root filesystem.
- Bind mounts/PVC/volumes được inspect ownership **sau mount**, không dựa vào quyền image gốc.
- K8s `runAsUser`/`runAsGroup`/`runAsNonRoot`/`fsGroup` phù hợp với storage runtime.
- Không dùng privileged mode/capabilities rộng, không mount Docker socket, không bake secrets.

**QA và giao artifact:**

- Maven `verify`/Gradle `build` và kiểm thử bắt buộc thực sự chạy trong build workflow.
- Kiểm tra image config `User` và `WorkingDir`, process `id`, `stat`/access checks.
- Smoke test container theo đúng URL; kiểm tra cả Docker runtime và Kubernetes nếu deploy vào cluster.
- Pin base image digest theo release, quét CVE và giữ checksum của image/artifact đã qua QA.
- Kiểm chứng read-only mode/volumes ở môi trường tương tự production trước khi bật bắt buộc.

**Kết luận:** `WORKDIR` chọn nơi làm việc; **owner/GID/mode** quyết định quyền truy cập; `USER` xác định identity của tiến trình. Cấu hình đúng cho Spring Boot container là: **JAR readable nhưng không writable, directory chạy có quyền traverse, vùng dữ liệu writable riêng, runtime UID/GID non-root, và các mounts có quyền tương thích**. Dùng `COPY --chown`/`--chmod` để thể hiện quyền trong image, `USER` cuối runtime stage để hạ đặc quyền, rồi xác nhận bằng **`id` + `stat` + test quyền + HTTP smoke test**. Không xem build success hay `WORKDIR` là bằng chứng hệ thống phân quyền đã đúng.

### Tài liệu chính thức

- Dockerfile reference (`WORKDIR`, `USER`, `COPY --chown`, `COPY --chmod`): https://docs.docker.com/reference/dockerfile/
- Docker — Building Best Practices (USER và UID/GID cố định): https://docs.docker.com/build/building/best-practices/
- Docker — Dockerfile Overview: https://docs.docker.com/build/concepts/dockerfile/
- Docker — Bind Mounts (mount che nội dung và quyền image): https://docs.docker.com/engine/storage/bind-mounts/
- Docker — tmpfs mounts và `--tmpfs`: https://docs.docker.com/engine/storage/tmpfs/
- Docker — `docker container run`: https://docs.docker.com/reference/cli/docker/container/run/
- Spring Boot — Container Images/Dockerfiles: https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html
- Spring Boot — Efficient Images/Layering: https://docs.spring.io/spring-boot/reference/packaging/container-images/efficient-images.html
- Kubernetes — Security Context (`runAsUser`, `runAsGroup`, `fsGroup`, `readOnlyRootFilesystem`): https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Eclipse Temurin — Official Container Image Sources: https://github.com/adoptium/containers