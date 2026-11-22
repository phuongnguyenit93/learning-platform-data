# Chạy Testcontainers trên CI với quyền, tài nguyên và Docker phù hợp

> **Module:** Spring Boot – testing  
> **Nhóm kiến thức:** Testcontainers  
> **Đề bài:** Chạy Testcontainers trên CI với quyền, tài nguyên và Docker phù hợp  
> **Mục tiêu:** Hiểu yêu cầu về Docker runtime/daemon, quyền CI runner, mạng và mapped ports, CPU/RAM/disk, image registry, Ryuk/cleanup, Spring TestContext lifecycle; triển khai một ví dụ Java 17 + Spring Boot 3.5 + PostgreSQL Testcontainers chạy qua GitHub Actions; đánh giá phương án GitLab CI, Jenkins và Kubernetes an toàn.

## 1. Vấn đề: vì sao Testcontainers chạy local nhưng fail trên CI?

Khi chạy local, developer có Docker Desktop/Engine đang hoạt động và `mvn test` có thể tạo PostgreSQL container dễ dàng. Khi chạy trong CI, các lỗi thường gặp:

```text
Could not find a valid Docker environment
permission denied while trying to connect to the Docker daemon socket
ContainerLaunchException: Container startup failed
Connection refused: localhost:32771
no space left on device
Process finished with exit code 137
```

Những lỗi này không nhất thiết đến từ Java code, Spring Data hoặc câu SQL. Testcontainers điều khiển Docker-compatible daemon để chạy dịch vụ **thật** bên trong container. Vì vậy cần đồng thời bảo đảm:

1. JVM của test nhận ra và truy cập được **Docker API**.
2. Docker daemon có quyền tạo container/network/volume, pull images và publish ports.
3. JVM có kết nối mạng tới port thực tế của PostgreSQL/Redis/Kafka/... sau khi container được tạo.
4. CI runner có đủ CPU, RAM, disk, file descriptors và timeout cho toàn bộ process.
5. Runner được cấp quyền an toàn và dọn resources sau khi chạy, kể cả khi test fail.
6. Integration tests **thực sự được thực thi**, không bị skip mà pipeline vẫn báo xanh.

Mục tiêu không phải “làm CI xanh bằng mọi giá”, mà là có bằng chứng test database đúng và một cấu hình runtime an toàn, tái lập được.

### 1.1. Luồng thực thi

```text
CI job (JDK 17 + Maven)
          │
          ▼
       mvn test
          │
          ▼
JUnit Jupiter + Spring TestContext
          │
          ▼
Testcontainers Java API ──────► Docker daemon
                                    │
                  ┌─────────────────┴────────────────┐
                  ▼                                  ▼
        postgres:16-alpine                     Ryuk helper
                  │                                  │
           Host/port published                Cleanup resources
                  │
                  ▼
       JDBC DataSource (@ServiceConnection)
                  │
                  ▼
      Repository + SQL assertions
```

**Docker CLI không phải Docker daemon.** CI có thể cài lệnh `docker` nhưng daemon không chạy; ngược lại một Maven job container không có Docker CLI vẫn có thể dùng Testcontainers nếu Java client được kết nối tới Docker API endpoint tương thích.

## 2. Năm lớp cần kiểm tra trước khi đổ lỗi cho test

| Lớp | Câu hỏi bắt buộc | Tín hiệu cần xem |
| --- | --- | --- |
| Java/build | JDK/Maven/Testcontainers versions có tương thích? | `java -version`, `mvn -version`, dependency tree |
| Docker API | JVM thấy đúng daemon? | `docker version`, `docker info` (nếu có CLI), `DOCKER_HOST` |
| Quyền | Runner user có quyền tạo containers? | Socket permissions, remote Docker TLS/ACL |
| Images/network | Có pull image và reach published ports? | Registry auth, outbound network, `getHost()`, `getMappedPort()` |
| Resources/lifecycle | RAM/CPU/disk/timeouts/cleanup đủ? | Container logs, OOM exit 137, disk/metrics, Ryuk |

Một lỗi xảy ra **trước khi PostgreSQL container được tạo** không thể được sửa bằng cách thêm Hibernate annotation. Ngược lại, khi Docker và DB đều healthy nhưng một SQL assertion fail, không nên đổ cho Docker.

### 2.1. Preflight cơ bản cho Docker-enabled VM

```bash
java -version
mvn -version
docker version
docker info
docker system df
```

- `docker version` có thông tin Client và Server khi daemon reachable.
- `docker info` giúp xác định runtime, driver, resource limits và một số thông tin vận hành.
- `docker system df` hiển thị tổng dung lượng images/containers/volumes.
- `java -version` và `mvn -version` bảo đảm test đang dùng đúng JDK.

Trong CI công khai, tránh log toàn bộ metadata host hoặc biến chứa Docker registry credentials. Chỉ in các trường cần chẩn đoán; log của daemon/containers cũng có thể chứa thông tin nhạy cảm.

### 2.2. Các biến cấu hình Docker thường gặp

| Biến | Ý nghĩa | Không nên nhầm với |
| --- | --- | --- |
| `DOCKER_HOST` | Địa chỉ Docker API daemon, ví dụ Unix socket hay TCP | Địa chỉ PostgreSQL JDBC |
| `DOCKER_TLS_VERIFY` | Xác minh TLS của remote Docker API | TLS của database |
| `DOCKER_CERT_PATH` | Client certificates cho Docker API | Credentials của PostgreSQL |
| `TESTCONTAINERS_HOST_OVERRIDE` | Host mà JVM dùng để kết nối **published container ports** khi auto-detection sai | `DOCKER_HOST` |
| `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` | Override socket path mà helper containers cần | Maven workspace path |
| `DOCKER_AUTH_CONFIG` | Credentials/config cho pull từ registries | Runtime database username |
| `TESTCONTAINERS_RYUK_DISABLED` | Tắt cleanup helper trong trường hợp đặc biệt | Cách khắc phục chung cho lỗi Docker |

**Không đặt các biến này nếu cấu hình mặc định đã hoạt động.** Đặc biệt, hard-code `DOCKER_HOST=tcp://localhost:2375` thường gây sai và mở rủi ro nếu daemon TCP không TLS.

## 3. Các mô hình chạy CI và mức độ phù hợp

### 3.1. JVM trực tiếp trên VM có Docker Engine

```text
Ephemeral Linux CI VM
  ├── JDK/Maven
  ├── Docker daemon
  ├── PostgreSQL container
  └── Ryuk container
```

Đây là lựa chọn ít phức tạp nhất cho dự án mẫu. JVM dùng Docker local, container host ports reachable từ VM; GitHub-hosted Ubuntu VM thường phù hợp khi runner image có Docker daemon. Cần đo tài nguyên, bảo vệ secrets và theo dõi image updates.

### 3.2. JVM ở Docker job container, daemon ở host (“Docker wormhole”)

```text
Docker host
  ├── Maven job container --mount /var/run/docker.sock
  ├── PostgreSQL sibling container
  └── Ryuk sibling container
```

Job container được mount socket host và gọi Docker API của host. PostgreSQL container không ở trong network namespace của Maven container: nó là **sibling**. Vì vậy `localhost` bên trong job container thường **không** phải host nơi PostgreSQL port được publish.

Những thứ cần bảo đảm:

- Docker socket/API được mount/cấp cho môi trường đang chạy JVM.
- `TESTCONTAINERS_HOST_OVERRIDE` chỉ đặt nếu host discovery không đúng.
- Nếu test dùng bind mounts, filesystem path của daemon host phải được cân nhắc; path nằm trong job container có thể không tồn tại trên host.
- **Socket Docker rootful có quyền rất mạnh lên Docker host**. Không mount vào untrusted PR jobs hoặc shared runner đang giữ volumes/secrets khác.
- Không khắc phục bằng `chmod 666 /var/run/docker.sock` trên host shared.

### 3.3. Docker-in-Docker (DinD)

JVM chạy trong job container, Docker daemon chạy trong một **service container**:

```text
Maven job container
      │  DOCKER_HOST=tcp://docker:2375 (ví dụ non-TLS)
      ▼
DinD daemon service
      ├── PostgreSQL container
      └── Ryuk container
```

DinD truyền thống thường đòi runner được cấp `privileged` hoặc cấu hình hạ tầng đặc biệt. Docker API `2375` **không có TLS** rất nhạy cảm: chỉ nên dùng nếu CI runner ephemeral, network cô lập, không chạy mã không tin cậy và đã được security/platform team duyệt. Ở môi trường sản xuất nên ưu tiên Docker daemon TLS, runner template chính thức hoặc container runtime được hỗ trợ.

DinD không phải giải pháp mặc định chỉ vì một CI job có lệnh `mvn test`.

### 3.4. Remote daemon, Kubernetes, rootless runtime

Một Kubernetes pod có containerd socket hoặc quyền `kubectl` không mặc nhiên có **Docker API** cho Testcontainers. Các phương án có thể là remote Docker daemon TLS, Testcontainers Cloud hoặc Docker-compatible runtime được hỗ trợ và cấu hình cụ thể. Không tự mount host runtime socket vào tất cả CI pods.

Podman/rootless hoặc alternative runtimes có những giới hạn network/Ryuk/socket riêng; kiểm tra tài liệu của phiên bản Testcontainers và runtime đang dùng. Một setup chỉ “có lệnh podman” chưa chứng minh Testcontainers hoạt động.

### 3.5. Bảng quyết định

| CI topology | Lợi ích | Rủi ro/việc cần test |
| --- | --- | --- |
| Hosted Ubuntu VM + Docker | Đơn giản, ephemeral | Docker engine availability, pull, quotas |
| Trusted self-hosted Docker VM | Cache image, tùy chỉnh runner | Quyền socket, orphaned resources, nhiều jobs |
| Docker executor + mounted socket | Tránh khởi động daemon mới | Host admin capability, volume paths, mapped ports |
| DinD service | Daemon riêng trong CI job | Privileged/TLS security, DNS, port reachability |
| Remote Docker API | Không yêu cầu daemon local | TLS, network/firewall, quotas, mapping host |
| Kubernetes pod không Docker API | Kiểm soát bằng K8s | Cần giải pháp runtime thay thế, không tự hỗ trợ |

## 4. Quyền Docker là vấn đề bảo mật, không chỉ là CI syntax

### 4.1. Cấp quyền theo trust boundary

Người có thể điều khiển rootful Docker daemon thường có khả năng tạo containers và mount filesystem host. Điều này có thể tương đương đặc quyền rất cao. Do đó:

- Dùng runner ephemeral cho code từ forks/contributors bên ngoài.
- Tách self-hosted Docker runners khỏi production hosts và secrets.
- Chỉ cấp Docker socket hoặc privileged executor cho jobs cần Testcontainers.
- Không cho runner chủ động truy cập production DB/secret store.
- Dùng ephemeral volumes và restricted runner credentials.
- Với TCP remote Docker API, bật authentication/TLS theo policy.
- Không dùng Docker daemon chung cho build không tin cậy và workloads quan trọng.
- Có cơ chế audit, quota, teardown resources sau job.

**Không sử dụng production credentials** trong bài test hoặc workflow. PostgreSQL Testcontainers sẽ tạo một database test-only và tự cấp connection details.

### 4.2. Quyền GitHub Actions token khác quyền Docker

Trong GitHub Actions:

```yaml
permissions:
  contents: read
```

giới hạn quyền **GitHub API token**, không cài Docker, không cấp permission socket hoặc root. Testcontainers chỉ cần runtime/container access, không cần quyền ghi repository, publish package hay deployment.

### 4.3. Lỗi quyền thường gặp

| Lỗi | Nguyên nhân | Phương án đúng |
| --- | --- | --- |
| `permission denied ... docker.sock` | Job JVM không có socket permission | Admin runner cấp quyền qua mô hình đã duyệt |
| `Cannot connect to Docker daemon` | Daemon không chạy/endpoint sai | Kiểm tra service/runtime/DOCKER_HOST |
| `HTTP 403` từ registry | Không có registry access | Registry credential/mirror hợp lệ |
| `operation not permitted` khi start helper | Rootless/privileged policy chặn | Điều chỉnh runner architecture, không blanket privilege |
| `TLS handshake failed` Docker API | Cert/path/CA cấu hình sai | Đồng bộ TLS config/certs theo daemon |
| Test không tạo được network | Daemon policy/quotas hạn chế | Platform team sửa runner capabilities |

**Cần phản hồi khác nhau cho từng loại lỗi.** Không đổi business logic để khắc phục thiếu quyền Docker.

## 5. Cơ chế mạng: Docker API khác PostgreSQL host/port

Có **ba đường đi** riêng:

1. JVM → Docker API để tạo container.
2. Docker daemon → registry để pull image.
3. JVM → PostgreSQL published port để gửi JDBC query.

Có thể thành công hai đường đầu nhưng fail đường thứ ba. Ví dụ container chạy ở Docker remote host A, JVM ở host B, nhưng DataSource cố truy cập `localhost:5432` trên B.

### 5.1. Mapped ports là động

```java
String host = postgres.getHost();
Integer port = postgres.getMappedPort(5432);
```

Snippet này chỉ có ý nghĩa **sau khi container đã start**. Testcontainers ánh xạ container port 5432 thành một host port mà Docker cấp, không nhất thiết là 5432. Trên CI runner host có thể là gateway hoặc tên host khác `localhost`.

Trong Spring Boot, `@ServiceConnection` trên `PostgreSQLContainer` cung cấp `JdbcConnectionDetails` để DataSource nhận chính xác URL/user/password do container cấp; không cần tự ghép host, port.

### 5.2. Khi nào cần `TESTCONTAINERS_HOST_OVERRIDE`?

Nếu Docker host discovery không phản ánh địa chỉ mà JVM bên trong job container có thể kết nối tới published ports, đặt host override **theo topology thật**. Với Docker Desktop, một số thiết kế containerized test dùng `host.docker.internal`:

```bash
# Chỉ ví dụ môi trường Docker Desktop phù hợp:
export TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal
```

Không đặt biến này toàn cục trên Linux/GitLab/Kubernetes runner khi chưa kiểm tra DNS/routes/firewall. Một giá trị sai gây connection refused dù database đã healthy.

### 5.3. Docker socket và bind mounts

Khi JVM nằm trong Maven Docker job container nhưng daemon là host, `withFileSystemBind` cần nguồn path tồn tại với **daemon host**. Một path chỉ tồn tại trong Maven container có thể không được mount đúng vào PostgreSQL/helper container. Dùng classpath resources hoặc `withCopyFileToContainer` cho fixtures nhỏ khi phù hợp, hoặc bảo đảm workspace mapping nhất quán.

### 5.4. Đừng hard-code ports

Không expose fixed host port 5432 cho Testcontainers trong một suite cần chạy song song. Fixed host port dễ va chạm giữa jobs/containers. Dùng dynamic port và `@ServiceConnection`/`getHost()` + `getMappedPort()`.

## 6. Dự trù CPU, RAM, disk, image pulls và timeouts

### 6.1. Tài nguyên là tổng nhiều process

```text
One CI job consumes:
  Maven build JVM
  JUnit/Surefire forked JVM(s)
  Spring ApplicationContext(s)
  PostgreSQL container
  Optional Redis/Kafka/Elasticsearch containers
  Ryuk/helpers
  Docker daemon + pulled image layers
  Workspace + Surefire reports + test fixture files
```

`MAVEN_OPTS=-Xmx512m` chỉ áp dụng cho Maven JVM; nó không phải RAM limit của PostgreSQL container hay mọi Surefire fork. Một job chạy 8 parallel workers + Kafka + Elasticsearch + PostgreSQL có thể OOM ngay cả khi mỗi component chạy riêng ổn.

### 6.2. Lỗi resource thường gặp

| Triệu chứng | Root cause khả dĩ | Chẩn đoán |
| --- | --- | --- |
| Exit 137 / `Killed` | OOM kill/SIGKILL | RAM/cgroups/container state |
| `no space left on device` | Image layers/volumes/logs/workspace đầy | `df -h`/`docker system df` |
| Container startup timeout | Service chậm/crash, CPU throttled | Container logs/readiness/resource |
| `image pull failed` | Registry outage/auth/rate-limit/proxy | Docker registry/connectivity |
| `exec format error` | ARM64 vs AMD64 image thiếu support | CPU architecture/image manifest |
| `too many open files` | File descriptors/pool quá lớn | Limits, JUnit parallelism |
| Random failure khi chạy parallel | Shared DB/ports/static state | Ownership, test order, port mapping |

**Không tăng timeout vô hạn** khi container thực sự crash/OOM. Phải đọc logs/metrics rồi điều chỉnh quota, concurrency hoặc config.

### 6.3. Chiến lược sizing

- Chạy unit tests không cần Docker càng nhanh càng tốt.
- Với PostgreSQL/Redis smoke tests, dùng ít containers và static lifecycle khi phù hợp.
- Với Kafka/Elasticsearch, dành runner có RAM/disk cao hơn hoặc một job integration riêng.
- Giới hạn Maven test forks và số container jobs chạy đồng thời.
- Cache Maven dependencies và Docker image layers là **hai cache khác nhau**.
- Pin image tag/digest và xác minh registry access. `postgres:16-alpine` chỉ pin major, patch có thể cập nhật.
- Không dùng image `latest` tùy tiện ở CI quan trọng.
- Theo dõi runner quotas, image pull latency, container startup và memory usage thực để chọn limits.

### 6.4. Timeouts và readiness

Ba lớp timeout: (1) CI job timeout, (2) container startup/readiness, (3) JDBC/HTTP query timeout. Testcontainers có wait strategies/module-specific readiness. Không dùng `Thread.sleep(5000)` như cách chứng minh PostgreSQL đã sẵn sàng.

Nếu service có cold-start chậm, điều chỉnh timeout theo log và baseline; nếu container fail vì sai init script, tăng timeout không làm nó đúng.

## 7. Ryuk, teardown và container lifecycle

Ryuk là resource reaper giúp Testcontainers dọn resources được tạo. Nó không thay test resource ownership hoặc security policy. Khi JVM bị kill/CI cancel, cleanup behavior còn phụ thuộc runner/runtime; runner ephemeral bị hủy hoàn toàn là một lớp bảo vệ bổ sung.

### 7.1. Không tắt Ryuk theo phản xạ

Có biến:

```bash
TESTCONTAINERS_RYUK_DISABLED=true
```

Chỉ cân nhắc khi môi trường restricted/rootless không thể chạy Ryuk và **đã có cơ chế dọn containers/volumes/networks chắc chắn** (ví dụ toàn bộ ephemeral runner VM/daemon được hủy sau job). Trên persistent self-hosted host, tắt Ryuk mà không có cleanup kế hoạch dễ gây rò disk/resources.

Không chạy `docker system prune -af --volumes` trên một daemon chia sẻ nhiều jobs: lệnh destructive có thể xóa dữ liệu của jobs/workloads khác.

### 7.2. Static vs instance containers

- `static @Container` trong `@Testcontainers`: tạo/dừng theo test class.
- Instance `@Container`: tạo/dừng theo test method, chậm hơn và phù hợp khi cần isolation mỗi method.
- Container bean được Spring Boot quản lý có thể sống cùng ApplicationContext, hữu ích khi nhiều test classes reuse context.
- `@DirtiesContext(classMode=AFTER_CLASS)` đóng context sau class; nó **không phải lệnh xóa Docker container**.
- Reusable containers/`withReuse(true)` có thể hữu ích local nhưng không nên bật trên CI cần môi trường sạch.

### 7.3. Spring TestContext caching là bẫy đặc biệt

Spring `ApplicationContext` có thể được cache và reuse giữa test classes. Nếu JUnit đã dừng static container sau class A nhưng context vẫn cached, class B có thể nhận DataSource trỏ port đã đóng.

Cách xử lý: container có lifecycle theo context (Spring bean) hoặc dùng `@DirtiesContext` có chủ đích cho class-scoped container; context configuration phải phân biệt resource identity. Không bật `@DirtiesContext` đại trà vì làm suite chậm, chỉ dùng khi đúng lifecycle risk.

## 8. Dự án Java 17 + Spring Boot 3.5 + PostgreSQL Testcontainers

Project đầy đủ gồm **2 unit tests không cần Docker** và **3 integration tests có PostgreSQL thật**. Không cần database production, credentials bên ngoài hoặc server HTTP. Maven sẽ cần tải dependencies nếu chưa có cache; integration tests yêu cầu Docker-compatible runtime.

### 8.1. Cây thư mục

```text
ci-testcontainers-lab/
├── pom.xml
├── .github/workflows/testcontainers.yml
└── src/
    ├── main/java/com/example/citest/
    │   ├── CiTestLabApplication.java
    │   ├── JobReference.java
    │   └── JobRepository.java
    └── test/
        ├── java/com/example/citest/
        │   ├── JobReferenceTest.java
        │   └── JobRepositoryIntegrationTest.java
        └── resources/schema.sql
```

Tất cả Java public classes có file riêng cùng tên, package `com.example.citest`. `schema.sql` ở `src/test/resources` để không vô tình chạy schema demo khi start application production.

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>ci-testcontainers-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>postgresql</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
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

- `spring-boot-starter-jdbc`: `JdbcTemplate`, Hikari DataSource.
- `postgresql`: PostgreSQL JDBC driver.
- `spring-boot-starter-test`: JUnit, AssertJ, Spring test infrastructure.
- `spring-boot-testcontainers`: `@ServiceConnection` support.
- Testcontainers PostgreSQL và JUnit modules: container implementation/lifecycle.

Spring Boot BOM giữ dependency versions phù hợp. Không cần `spring-boot-starter-web` để kiểm tra database này.

### 8.3. `CiTestLabApplication.java`

```java
// src/main/java/com/example/citest/CiTestLabApplication.java
package com.example.citest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CiTestLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CiTestLabApplication.class, args);
    }
}
```

### 8.4. `JobReference.java`

```java
// src/main/java/com/example/citest/JobReference.java
package com.example.citest;

public final class JobReference {
    private JobReference() {
    }

    public static String normalize(String ref) {
        if (ref == null ||
                !ref.matches("[a-z][a-z0-9-]{0,31}")) {
            throw new IllegalArgumentException(
                    "Invalid job reference");
        }
        return ref;
    }
}
```

Đây chỉ là validation helper của demo, không phải một cơ chế phân quyền. Test của nó không cần Spring context hay Docker.

### 8.5. `JobRepository.java`

```java
// src/main/java/com/example/citest/JobRepository.java
package com.example.citest;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JobRepository {

    private final JdbcTemplate jdbc;

    public JobRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String ref, String status) {
        jdbc.update(
                "INSERT INTO ci_jobs(external_ref,status) " +
                "VALUES (?,?)",
                JobReference.normalize(ref), status);
    }

    public String statusOf(String ref) {
        return jdbc.queryForObject(
                "SELECT status FROM ci_jobs " +
                "WHERE external_ref = ?",
                String.class,
                JobReference.normalize(ref));
    }

    public long count() {
        Long result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ci_jobs", Long.class);
        return result == null ? 0L : result;
    }
}
```

`JdbcTemplate` lấy DataSource từ Spring context. Không tạo JDBC URL hard-code `localhost:5432` trong repository; container có thể publish port ngẫu nhiên.

### 8.6. `src/test/resources/schema.sql`

```sql
CREATE TABLE ci_jobs (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    external_ref VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL
);
```

File trong **test resources** và chỉ được thực thi nhờ properties của integration test. Dự án thật dùng Flyway/Liquibase nên kiểm tra migrations thực thay vì dựng một schema giả khác production.

### 8.7. `JobReferenceTest.java` — unit test không dùng Docker

```java
// src/test/java/com/example/citest/JobReferenceTest.java
package com.example.citest;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JobReferenceTest {

    @Test
    void acceptsValidReference() {
        assertThat(JobReference.normalize("job-1"))
                .isEqualTo("job-1");
    }

    @Test
    void rejectsInvalidReference() {
        assertThatThrownBy(
                () -> JobReference.normalize("bad reference"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Invalid job reference");
    }
}
```

Có **2 `@Test` methods**, chỉ kiểm tra business helper. Chúng không chứng minh database hoạt động và không yêu cầu Docker.

### 8.8. `JobRepositoryIntegrationTest.java` — PostgreSQL thật

```java
// src/test/java/com/example/citest/JobRepositoryIntegrationTest.java
package com.example.citest;

import java.sql.Connection;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Testcontainers
@SpringBootTest(properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:schema.sql"
})
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class JobRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("ci_tests");

    @Autowired
    JobRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    DataSource dataSource;

    @BeforeEach
    void resetTestData() {
        jdbc.update("DELETE FROM ci_jobs");
    }

    @Test
    void writesAndReadsThroughRealDatabase() {
        repository.insert("job-1", "QUEUED");

        assertThat(repository.statusOf("job-1"))
                .isEqualTo("QUEUED");
        assertThat(repository.count()).isEqualTo(1L);
    }

    @Test
    void duplicateBusinessKeyIsRejectedByDatabase() {
        repository.insert("duplicate", "QUEUED");

        assertThatThrownBy(
                () -> repository.insert("duplicate", "DONE"))
                .isInstanceOf(DuplicateKeyException.class);

        assertThat(repository.count()).isEqualTo(1L);
    }

    @Test
    void reallyUsesPostgresqlContainer() throws Exception {
        try (Connection conn = dataSource.getConnection()) {
            assertThat(conn.getMetaData()
                    .getDatabaseProductName())
                    .isEqualTo("PostgreSQL");
        }

        assertThat(jdbc.queryForObject(
                "SELECT current_database()", String.class))
                .isEqualTo("ci_tests");
    }
}
```

**Giải thích:**

- `@Container` + `@Testcontainers` khởi động PostgreSQL cho class.
- `@ServiceConnection` tạo JDBC connection details động; không cần hard-code port/password.
- `@SpringBootTest` nạp application context có `JobRepository` và DataSource.
- `spring.sql.init.mode=always` chạy test schema script trên PostgreSQL container.
- `@BeforeEach` xóa data trong **test-only database** trước mỗi method. Không dùng cách này nếu tests đang chia sẻ database với jobs khác.
- `@DirtiesContext(AFTER_CLASS)` giúp tránh context cache giữ DataSource trỏ container class-scoped đã dừng.
- Ba assertions chứng minh lưu/đọc JDBC thật, PostgreSQL unique constraint và đúng database engine/name.

**Không kết luận** PostgreSQL container là production DB, hoặc đã kiểm thử SQL migrations/performance/replication của production. Bài này minh họa Testcontainers CI environment và một số database contracts cơ bản.

### 8.9. Lệnh chạy và dự kiến test count

```bash
# Chỉ pure unit:
mvn -B -ntp -Dtest=JobReferenceTest test

# Chạy integration — cần container runtime:
docker info
mvn -B -ntp -Dtest=JobRepositoryIntegrationTest test

# Tổng:
mvn -B -ntp test
```

Project có **5 JUnit test methods**: 2 unit + 3 integration. Maven sẽ in test reports tùy JDK/Surefire versions; không có stdout/port cố định. Đây là mã mẫu để người học chạy, **không phải một kết quả build đã được thực thi** trong tài liệu này.

## 9. GitHub Actions: pipeline đơn giản trên Ubuntu-hosted runner

GitHub-hosted Ubuntu VM runner có Docker daemon phù hợp là một lựa chọn thuận tiện. Khi dùng Testcontainers, **không cần khai thêm một `services: postgres`** cho cùng dependency: Java đã quản lý PostgreSQL container. Có thể dùng GitHub `services` như chiến lược khác, nhưng khi đó cần thay đổi cách test lấy DataSource; không chạy hai PostgreSQL services vô tình.

### 9.1. `.github/workflows/testcontainers.yml`

```yaml
name: Spring Boot Testcontainers

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Java 17 with Maven cache
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Docker runtime preflight
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}} Driver={{.Driver}}'
          docker system df

      - name: Run tests
        run: mvn -B -ntp verify

      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: surefire-reports
          path: target/surefire-reports/
          if-no-files-found: ignore
          retention-days: 7
```

- `runs-on: ubuntu-24.04` chọn một VM image cụ thể; nó vẫn có các đợt update, vì vậy xem release notes. Đừng cho rằng `ubuntu-latest` luôn trỏ cùng hệ điều hành.
- `permissions: contents: read` giảm quyền GitHub token; nó **không** cấp quyền Docker.
- Step `docker version/info` fail sớm nếu daemon không hoạt động, tránh hiểu nhầm DB test code sai.
- `mvn verify` chạy Surefire tests theo Maven lifecycle của project; không cần `docker compose up` thủ công.
- Upload reports dù Maven fail; không upload credentials/unredacted container env.
- `cache: maven` chỉ cache Maven dependencies, **không** bảo đảm Docker image layers tồn tại ở daemon job tiếp theo.

**Security note:** Actions version tags dùng minh họa; với môi trường yêu cầu supply-chain pinning, cố định actions theo commit SHA đã review và update có kiểm soát. Hosted runner specs/OS images có thể thay đổi theo nhà cung cấp.

### 9.2. Nếu runner của GitHub thiếu Docker?

Lỗi phải làm integration job fail rõ. Không chuyển sang `@Testcontainers(disabledWithoutDocker=true)` trong mandatory CI vì nó có thể biến thiếu runtime thành test skipped, pipeline xanh giả.

Nếu CI executor là GitHub-hosted job container thay vì trực tiếp trên VM, xem lại Docker socket/host detection/volume mounts theo topology thực; không mặc định mẫu VM ở trên áp dụng y hệt.

### 9.3. Khi test-heavy job thiếu tài nguyên

Một Postgres container có thể chạy ổn nhưng thêm Kafka + Elasticsearch sẽ tăng memory/disk đáng kể. Giảm parallel forks, tách jobs, nâng runner size hoặc tối ưu image/fixtures theo measurements. Không đơn thuần tăng timeout từ 20 lên 120 phút để che OOM.

## 10. GitLab CI: cần kiểm tra runner executor trước khi viết YAML

### 10.1. Socket-based Docker executor

Self-hosted Docker executor có thể mount `/var/run/docker.sock` vào job container; Testcontainers sẽ tạo sibling containers trên host. Điều này cần cấu hình runner do admin cấp, không chỉ sửa `.gitlab-ci.yml`. Cân nhắc security vì Docker socket cấp quyền rất mạnh.

Với job JVM bên trong container, mapped port host phải reachable. `TESTCONTAINERS_HOST_OVERRIDE` có thể cần trong một số Docker host topology, nhưng chỉ cấu hình sau khi xác định hostname/IP đúng; không gán một IP mẫu thành giá trị thật.

### 10.2. DinD — ví dụ có điều kiện, không phải cấu hình an toàn mặc định

Mẫu dưới dùng DinD **không TLS**, chỉ phù hợp **runner ephemeral, network cô lập và code đáng tin** sau khi platform team cho phép. Nó thường cần privileged Docker executor:

```yaml
stages:
  - test

testcontainers:
  stage: test
  image: maven:3.9.9-eclipse-temurin-17
  services:
    - name: docker:27-dind
      alias: docker
      command: ["--tls=false"]
  variables:
    DOCKER_HOST: "tcp://docker:2375"
    DOCKER_TLS_CERTDIR: ""
  script:
    - mvn -B -ntp test
```

- `DOCKER_HOST` trỏ Docker API của DinD service `docker`, không trỏ PostgreSQL.
- Port 2375 không TLS, **không expose ra network công cộng hoặc runner đa tenant không tin cậy**.
- Maven job image có thể không có Docker CLI; Testcontainers Java vẫn có thể giao tiếp qua API daemon.
- Cần xác minh network DNS alias, service readiness, Ryuk và published port reachability.
- Với TLS, cần daemon/certs/`DOCKER_TLS_VERIFY` và config đúng; không chỉ sửa port `2375` thành `2376`.

### 10.3. Nếu chính sách không cho privileged DinD

Đừng dùng `privileged=true` ở mọi runner để thông qua CI. Chọn một Docker-enabled isolated runner, authenticated remote Docker service, hoặc nền tảng container test được tổ chức hỗ trợ. Cần có security review và phân tách untrusted PR workloads.

## 11. Jenkins, Kubernetes và self-hosted CI

### 11.1. Jenkins VM agent

Nếu Jenkins agent chạy trực tiếp trên Linux VM đã có Docker Engine, luồng giống GitHub Actions: checkout, kiểm tra `docker version`, chạy `mvn verify`, archive Surefire reports. Nếu agent persistent, cần quota/cleanup theo job owner; không chạy global Docker prune trên shared host.

### 11.2. Jenkins Docker agent

Nếu Maven chạy bên trong Jenkins Docker agent, xem liệu `/var/run/docker.sock` có mount và Docker API reachable không. Testcontainers tạo sibling containers; `localhost` trong Maven agent không nhất thiết trỏ Docker host. Có thể cần workspace path mapping cho bind-mounted fixtures. Đây là quyền hạ tầng, không phải vấn đề Java import.

### 11.3. Kubernetes executor

Chỉ có pod/containerd không có nghĩa đã có Docker API. Có thể dùng remote Docker service/TLS hoặc một runtime chính thức tương thích; không cấp privileged pods hoặc host container runtime socket toàn namespace chỉ để chữa một integration test.

### 11.4. CPU architecture

Image `postgres` cần support runner platform. ARM64 vs AMD64 mismatch có thể gây `exec format error` hoặc emulation chậm. Kiểm tra image manifest/architecture và runner spec. CI on ARM không luôn giống Docker Desktop trên laptop x86.

## 12. Mandatory integration tests không được silent-skip

### 12.1. Bốn trạng thái phải phân biệt

| Trạng thái | Ý nghĩa |
| --- | --- |
| UNIT PASS | Pure Java/Mockito tests đã chạy và đạt |
| INTEGRATION PASS | Container thực sự start và SQL assertions pass |
| INTEGRATION FAIL | Container chạy nhưng code/schema/assertion có lỗi |
| ENVIRONMENT FAIL | Không có daemon, thiếu permission, registry/pull/Ryuk/host port fail |
| SKIPPED | Không chạy; không thể coi là PASS |

`@Testcontainers(disabledWithoutDocker=true)` có thể hữu ích cho một local optional test, nhưng **không dùng cho mandatory CI integration gate**. Tương tự:

```bash
# Chống chỉ định cho mandatory test job:
mvn test || true
```

Lệnh này làm CI xanh dù tests fail; phải để exit code thật quyết định kết quả. Nếu tách jobs unit/integration, branch protection nên yêu cầu integration job pass khi nó là quality gate.

### 12.2. Logs và test reports

Spring Boot/JUnit/Maven Surefire thường ghi kết quả dưới `target/surefire-reports/`; upload có retention. Khi debug có thể tăng log level `org.testcontainers`/`com.github.dockerjava` tạm thời, nhưng kiểm tra dữ liệu nhạy cảm trước khi chia sẻ.

## 13. Troubleshooting theo tầng

### 13.1. Runtime not found

```text
Could not find a valid Docker environment
```

Kiểm tra `DOCKER_HOST`, Docker daemon/socket permission ở JVM environment, rootless runtime và logs Testcontainers discovery. Nếu runner không cho Docker access, **đừng thêm một fake PostgreSQL** để thay việc integration test, trừ khi có một job khác bảo vệ engine thật.

### 13.2. Socket permission denied

```text
permission denied while trying to connect to the Docker daemon socket
```

Admin runner cần cấp quyền daemon theo approved trust model. Không chmod socket world-writable trên shared runner hoặc root toàn workflow.

### 13.3. Container start nhưng JDBC refused

Kiểm tra container logs/readiness, `getHost()`, `getMappedPort(5432)`, Docker host routing, `TESTCONTAINERS_HOST_OVERRIDE` và firewall. Không hard-code `localhost:5432`. Dùng Spring `@ServiceConnection` từ static PostgreSQLContainer để lấy đúng JDBC URL.

### 13.4. Image pull fail

```text
pull access denied / unauthorized / too many requests
```

Đánh giá image tag, Docker Hub rate limits, registry mirror, proxy/TLS, Docker auth. Không log `DOCKER_AUTH_CONFIG`/registry token. Caching Maven không giải quyết Docker image pull.

### 13.5. Ryuk fail

Kiểm tra helper permission, socket accessibility, network và phiên bản runtime. Tắt Ryuk chỉ nếu có runner teardown tin cậy, không che lỗi bằng env var rồi để persistent runner tích tụ resources.

### 13.6. Exit 137, OOM, no space

Kiểm tra memory cgroups, runner quota, số containers/forks, `df -h` và `docker system df`. Giảm concurrency hoặc nâng runner resources; tránh Docker prune diện rộng trên shared host.

### 13.7. Test pass riêng nhưng fail suite

Nguyên nhân thường gặp: TestContext cache reuse DataSource trỏ container đã stop, tests chia sẻ mutable DB/fixtures, static state, fixed host ports, parallel execution không được hỗ trợ hoặc schema initialization chạy lặp. Xác định ownership/lifecycle, không chỉ thêm `Thread.sleep`.

### 13.8. Service startup timeout

Đọc logs của PostgreSQL container, kiểm tra init SQL, image version, CPU/memory và wait strategy. Khi container crash vì invalid config, tăng wait timeout chỉ làm test đợi lâu hơn chứ không sửa root cause.

## 14. Chạy song song và tối ưu thời gian CI

- Nhiều VM jobs ephemeral: mỗi job có Docker daemon/containers riêng, đơn giản hơn để cô lập.
- Nhiều JVM forks trên cùng runner: resource budgets cộng dồn, có nguy cơ CPU/memory contention.
- Shared container giữa test classes: tiết kiệm startup nhưng cần DB fixture isolation và container lifecycle trùng với Spring context.
- Unit tests có thể chạy song song rộng hơn integration tests; điều chỉnh fork count thay vì mở quá nhiều databases.
- Dùng dynamic ports; fixed 5432 dễ va chạm.
- Tránh Testcontainers container reuse trong CI khi cần clean state.
- Không dùng global cleanup nếu nhiều jobs dùng cùng Docker host.
- Metrics cần theo dõi: image pull time, container startup time, tests executed/failed/skipped, memory peak, disk, retries, network errors.

## 15. Quy trình debug ngắn khi CI fail

**Bước 1 — Docker API:**

```bash
docker version
docker info --format 'Engine={{.ServerVersion}} Driver={{.Driver}}'
```

Nếu daemon unreachable, chưa cần debug JDBC.

**Bước 2 — Resources:**

```bash
docker system df
df -h
```

Kiểm tra image pull, disk, runner memory/CPU, concurrency.

**Bước 3 — Một test DB:**

```bash
mvn -B -ntp -Dtest=JobRepositoryIntegrationTest test
```

Nếu container chưa start: runtime/image/Ryuk. Nếu start nhưng SQL refused: network/host/port/readiness. Nếu SQL chạy mà assertion fail: schema/DAO/business logic.

**Bước 4 — So sánh local và CI:** JDK, Maven, Boot/Testcontainers/driver versions, Docker daemon endpoint, image architecture/tag, TLS/registry, mapped port routing, resource budgets và context lifecycle.

**Bước 5 — Báo cáo có bằng chứng:**

```text
Status: ENVIRONMENT_FAIL / INTEGRATION_FAIL / INTEGRATION_PASS
Runner: hosted VM / Docker executor / self-hosted
Docker API reachable: yes/no
Image: postgres:16-alpine
Failure phase: runtime / pull / startup / JDBC / assertion
Tests run/failed/skipped: ...
Evidence: sanitized logs + Surefire report
Owner/action: CI platform / application team
```

Không dùng báo cáo “QA PASS” nếu integration chỉ bị skip vì thiếu Docker.

## 16. Checklist trước khi merge CI workflow

- [ ] Java 17/Maven/Testcontainers dependencies tương thích.
- [ ] JVM thấy Docker-compatible daemon thực sự, không chỉ Docker CLI.
- [ ] Runner permissions cho Docker API được cấp theo trust boundary.
- [ ] Untrusted PR không điều khiển shared privileged Docker host.
- [ ] Không expose Docker API non-TLS trên mạng công cộng.
- [ ] Docker images/pull registry reachable; versions/digests có chiến lược pin.
- [ ] `DOCKER_HOST`/TLS đúng nếu dùng remote daemon; override host chỉ khi cần.
- [ ] PostgreSQL container connection dùng `@ServiceConnection`/runtime mapped port.
- [ ] Không hard-code `localhost:5432` cho Testcontainers.
- [ ] CPU/RAM/disk/timeouts đủ cho Maven, JUnit forks, containers và Docker.
- [ ] Ryuk/cleanup hoạt động hoặc có verified ephemeral teardown.
- [ ] Không dùng container reuse để đổi lấy CI xanh giả.
- [ ] Context cache và static `@Container` lifecycle phù hợp.
- [ ] Test data không trỏ production; cleanup có scope test-only.
- [ ] Chạy integration mandatory không skip silently khi Docker unavailable.
- [ ] Không dùng `mvn test || true` trong gate bắt buộc.
- [ ] Test results được upload, logs đã redact credentials.
- [ ] CI phân biệt UNIT PASS, INTEGRATION PASS/FAIL, ENVIRONMENT FAIL và SKIPPED.
- [ ] GitHub/GitLab/Jenkins runner topology và network reachability được kiểm tra thực.
- [ ] Nếu CI chạy song song, không có global destructive cleanup hoặc fixed ports.

## 17. Bài tập vận dụng

**Bài 1 — GitHub Actions:** Tạo project phần 8 và workflow phần 9; chạy `mvn test`. Xác định đúng 2 unit + 3 integration methods; nếu Docker daemon không hoạt động, preflight phải fail sớm.

**Bài 2 — Thiếu Docker:** Trên runner test-only không có daemon, chỉ chạy `JobReferenceTest`, sau đó chạy `JobRepositoryIntegrationTest`. Giải thích vì sao kết quả unit PASS không cho phép tuyên bố integration PASS.

**Bài 3 — Mapped port:** Thử hard-code JDBC URL localhost:5432 trong nhánh thử nghiệm, so sánh với `@ServiceConnection` trên runner job container hoặc remote daemon. Giải thích lỗi connection refused.

**Bài 4 — Quyền:** Vẽ trust boundary của Docker socket và DinD privileged runner. Xác định code từ forks có được phép truy cập runner ấy không; đề xuất VM ephemeral hoặc remote TLS daemon khi cần.

**Bài 5 — Tài nguyên:** Chạy cùng suite với nhiều parallel integration jobs trên môi trường thử, đo memory peak/disk/image pull time. Đặt concurrency cap dựa trên dữ liệu thay vì sleep/retry vô hạn.

**Bài 6 — Cleanup:** Trên runner ephemeral test-only, cho một assertion fail rồi quan sát Testcontainers cleanup; khi cân nhắc tắt Ryuk, phải xác minh VM/daemon/resources đã được teardown khi job cancel.

**Bài 7 — GitLab:** Phân biệt Docker socket và DinD, xác định `DOCKER_HOST`, quyền runner và địa chỉ published port. Không copy cấu hình `2375` non-TLS sang môi trường chung không tin cậy.

## 18. Câu hỏi tự kiểm tra

**1.** Có Docker CLI là đủ cho Testcontainers chưa? — **Chưa**, JVM phải gọi được Docker-compatible daemon và được quyền tạo containers.

**2.** `DOCKER_HOST` và `TESTCONTAINERS_HOST_OVERRIDE` khác gì? — Một biến cho Docker API endpoint; biến kia dùng để JVM truy cập published ports khi host discovery sai.

**3.** Vì sao socket mount nguy hiểm? — Job có thể điều khiển Docker host với đặc quyền rất mạnh, gây rủi ro khi có secrets/shared workloads.

**4.** Vì sao `localhost:5432` thường sai trên CI? — Docker publish host ports động; JVM/container namespace/remote host có thể khác localhost.

**5.** `@ServiceConnection` giúp gì? — Spring Boot lấy JDBC connection details của PostgreSQL container, tránh hard-code URL/port/credentials.

**6.** Tắt Ryuk có tự sửa thiếu daemon không? — Không; chỉ tác động cleanup helper. Thiếu daemon vẫn là lỗi runtime.

**7.** Tại sao `@DirtiesContext` không thay cleanup? — Nó đóng/rebuild Spring context, không phải lệnh Docker resource cleanup.

**8.** Testcontainers pass trên PostgreSQL container có chứng minh performance production không? — Không; dữ liệu, index, topology, CPU, disk và tải khác.

**9.** Có nên silently skip integration tests nếu CI không có Docker? — Không, nếu integration là quality gate bắt buộc.

**10.** Tại sao GitLab DinD non-TLS không dùng trên runner shared untrusted? — Docker API 2375 không xác thực/TLS cùng privileged runner tạo rủi ro điều khiển daemon và truy cập tài nguyên khác.

## 19. Tài liệu chính thức

- [Testcontainers Java — Container runtime requirements](https://java.testcontainers.org/supported_docker_environment/): Docker discovery và runtime hỗ trợ.
- [Testcontainers Java — GitLab CI](https://java.testcontainers.org/supported_docker_environment/continuous_integration/gitlab_ci/): Docker socket, DinD và host networking.
- [Testcontainers Java — Running tests inside Docker](https://java.testcontainers.org/supported_docker_environment/continuous_integration/dind_patterns/): sibling containers, workspace mounts.
- [Testcontainers Java — Networking](https://java.testcontainers.org/features/networking/): `getHost()`, `getMappedPort()`, random ports.
- [Testcontainers Java — Configuration](https://java.testcontainers.org/features/configuration/): Ryuk, image pulls, Docker host overrides.
- [Testcontainers Java — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container` và lifecycle.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` và TestContext lifecycle.
- [GitHub Actions — Runner specs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job): hosted runner capabilities.
- [GitHub Actions — Ubuntu 24.04 image](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md): thành phần Docker/JDK/Maven image.
- [Docker Engine — Protect the Docker daemon socket](https://docs.docker.com/engine/security/protect-access/): bảo mật Docker API/TLS.
- [Docker Engine — Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): CPU/memory/OOM và giới hạn container.

**Kết luận:** Chạy Testcontainers trên CI thành công cần đồng thời **runtime Docker thật + quyền an toàn + mạng đúng + tài nguyên đủ + cleanup đáng tin + báo cáo test minh bạch**. Không giải quyết lỗi thiếu Docker bằng skip âm thầm, cố định port, tắt Ryuk vô điều kiện hoặc mở privileged socket cho mọi runner. Với Spring Boot, `@ServiceConnection` giúp dự án dùng cùng cách kết nối PostgreSQL trên máy phát triển và CI khi runtime đã được cấu hình đúng.