# Docker trên runner và tài nguyên cho Testcontainers trong Spring Boot CI

## 1. Bài toán và mục tiêu

Testcontainers cho phép JUnit chạy PostgreSQL, Redis, Kafka hoặc dịch vụ khác trong Docker-compatible containers. Tuy nhiên, test PASS trên laptop có Docker Desktop vẫn có thể FAIL trong CI vì:

- Job không truy cập được Docker daemon/API.
- Docker socket bị từ chối quyền hoặc Docker-in-Docker (DinD) không khởi động được.
- Job chạy bên trong container, làm `localhost` và các filesystem paths khác host.
- Image pull bị Docker Hub rate limit, private registry auth hoặc DNS/proxy chặn.
- Ryuk resource reaper không chạy do privileged/security policy.
- Container STARTED nhưng mapped port không tới được từ Java test JVM.
- Runner thiếu CPU/RAM/disk/inodes, gây OOMKilled, exit 137 hoặc timeout.
- Gradle forks, JUnit parallelism và nhiều CI jobs tạo quá nhiều containers cùng lúc.
- Orphan containers/volumes trên self-hosted runner làm đầy Docker storage.

**Mục tiêu:** hiểu topology Docker trên CI runner, chuẩn bị runtime và tài nguyên, viết Spring Boot Testcontainers integration test đúng, xây workflow GitHub/GitLab có preflight và kiểm chứng lỗi theo từng tầng.

### Sau bài học

Bạn sẽ biết kiểm Docker API, phân biệt Docker API host với mapped JDBC host, dùng `DOCKER_HOST`/`TESTCONTAINERS_HOST_OVERRIDE` đúng chỗ, chọn socket/DinD/TLS, xử lý Ryuk, tính resource budget, cấu hình `@ServiceConnection`, đọc Docker error logs và tối ưu Testcontainers suite mà không bỏ các integration tests bắt buộc.

## 2. Docker CLI, daemon, registry và Testcontainers không phải một thứ

~~~text
CI runner process
  |
  +-- Java: JUnit + Spring Boot + Testcontainers client
  |      |
  |      | Docker API via socket / TCP / TLS
  |      v
  |   Docker daemon
  |      +-- PostgreSQL dependency container
  |      +-- Redis/Kafka containers
  |      +-- Ryuk cleanup container
  |      +-- mapped host ports
  |             |
  +-------------+---- JDBC/HTTP from test JVM
~~~

**Hai đường kết nối:**

1. **Control plane** từ JVM tới Docker API để create/start/inspect container.
2. **Data plane** từ JVM tới Docker mapped host/port để dùng PostgreSQL/HTTP thực.

`docker --version` chỉ cho biết Docker CLI có mặt. `docker version` hoặc `docker info` mới thử cả daemon. Nhưng ngay cả khi Docker API reachable, JDBC vẫn có thể fail nếu network/port mapping sai.

| Thành phần | Chức năng | Lỗi thường gặp |
| --- | --- | --- |
| Docker CLI | Chạy lệnh chẩn đoán | command not found |
| Docker daemon | Quản lý container | Cannot connect to daemon |
| Docker API endpoint | Socket hoặc TCP/TLS | Permission/TLS error |
| Registry | Cung cấp image layers | 401/403/429 |
| Ryuk | Cleanup orphan resources | Privileged denied |
| Dependency container | PostgreSQL/Kafka/Redis | Exited/OOM/unhealthy |
| Published port | JVM truy cập service | Connection refused |

Testcontainers Java cần Docker-API-compatible runtime, không tự cài Docker daemon qua Gradle dependency.

## 3. Bốn topology CI thường gặp

### A. Linux VM runner có Docker Engine

~~~text
GitHub-hosted Ubuntu VM / dedicated self-hosted VM
  +-- Gradle / JUnit on VM
  +-- local Docker Engine/socket
  +-- Testcontainers dependency containers
~~~

Đơn giản nhất khi mới triển khai. Với GitHub Actions `runs-on: ubuntu-24.04`, job chạy trực tiếp trên Ubuntu VM (không có job-level `container:`), Docker thường đã có sẵn. Kiểm `docker version` trong job để xác nhận thay vì đoán.

Runner resources tùy label, public/private repository, architecture và plan; không tự khẳng định tất cả hosted runners có cùng vCPU/RAM/disk.

### B. Job container dùng socket của host (“wormhole”)

~~~text
Docker host daemon
  +-- build job container (JDK + Gradle)
  |      +-- /var/run/docker.sock mounted
  |      +-- Testcontainers API client
  +-- sibling PostgreSQL container
  +-- sibling Ryuk container
~~~

Cần socket permission, network route tới mapped ports và **same absolute source paths** nếu module dùng bind mounts. Socket trao quyền điều khiển Docker host rất mạnh; không mount cho untrusted PR jobs.

### C. Docker-in-Docker (DinD)

~~~text
GitLab job container
  +-- Java Testcontainers
        |
        v
  Docker API tcp://docker:2375 (isolated non-TLS example)
        |
  DinD service container
        +-- Docker daemon and dependency containers
~~~

DinD thường yêu cầu runner privileged policy/cgroups phù hợp. TCP 2375 không TLS chỉ được dùng trong ephemeral isolated CI service network, không mở ra public/shared network. Với CI lâu dài cần TLS 2376, dedicated socket runner hoặc remote service có xác thực/network policy.

### D. Remote/managed Docker-compatible runtime

Khi Kubernetes PodSecurity cấm privileged và host socket, chọn Docker API-compatible runtime có TLS/quotas/cleanup hoặc managed Testcontainers service. Kubernetes dùng containerd/CRI **không có nghĩa** Testcontainers tự nhận được Docker API.

## 4. Docker preflight ở đúng job environment

Ví dụ trên Linux runner có Docker CLI:

~~~bash
set -eu
docker version
docker info --format 'Docker server={{.ServerVersion}}'
df -h
df -i
free -m
docker system df
java -version
~~~

Đây là **lệnh cần chạy**, không phải stdout được ghi lại. `docker version` kiểm daemon, `df -h` kiểm bytes, `df -i` kiểm inodes, `free -m` xem RAM host, `docker system df` xem Docker disk usage.

**Chạy preflight nơi test JVM thực sự chạy**: nếu Docker hoạt động trên Jenkins VM nhưng Gradle nằm trong container không mount socket, host preflight PASS không bảo đảm Java Testcontainers PASS.

Một số minimal images không cài `free` hoặc Docker CLI dù Java Docker API client vẫn có thể hoạt động; dùng chẩn đoán tương đương đúng runtime.

Không in toàn bộ environment, registry tokens, Docker config JSON hoặc private certs ra CI logs.

## 5. Environment variables: hiểu trước khi đặt

| Biến | Ý nghĩa |
| --- | --- |
| `DOCKER_HOST` | Docker API Unix/TCP endpoint |
| `DOCKER_TLS_VERIFY` | Xác minh TLS cho API |
| `DOCKER_CERT_PATH` | Client certificates |
| `TESTCONTAINERS_HOST_OVERRIDE` | Mapped-port hostname reachable từ JVM |
| `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` | Docker socket path dành cho Ryuk/helper |
| `DOCKER_CONFIG` | Docker registry config directory |
| `DOCKER_AUTH_CONFIG` | Registry authentication nếu runtime hỗ trợ |
| `TESTCONTAINERS_RYUK_DISABLED` | Tắt Ryuk có điều kiện |
| `TESTCONTAINERS_CHECKS_DISABLE` | Tắt startup checks, không dùng để che setup lỗi |

Trên một Ubuntu VM với local daemon, Testcontainers thường tự detect mà không cần thêm variables. Một `DOCKER_HOST`/override tự đặt sai có thể phá môi trường vốn đang hoạt động.

### DOCKER_HOST khác database host

Với DinD:

~~~yaml
variables:
  DOCKER_HOST: "tcp://docker:2375"
~~~

Đây là **Docker API** host, không phải JDBC endpoint. Java dùng:

~~~java
postgres.start();
String jdbcUrl = postgres.getJdbcUrl();
String host = postgres.getHost();
int port = postgres.getMappedPort(5432);
~~~

Hostport thường random, không ghép `localhost:5432`. `@ServiceConnection` trong Spring Boot dùng connection details từ container khi module tương ứng có mặt.

### TESTCONTAINERS_HOST_OVERRIDE khi nào?

Chỉ khi host/IP Testcontainers dùng cho published ports không reachable từ test JVM, thường trong job container/remote runtime. Trước khi đặt, kiểm JVM network namespace, Docker daemon route, DNS, published port, firewall và service readiness. Không đặt `localhost` theo thói quen.

## 6. Docker socket, privileged và bảo mật

`/var/run/docker.sock` có quyền điều khiển host Docker daemon gần như quyền quản trị hệ thống. **Không** sửa permission denied bằng lệnh sau:

~~~bash
sudo chmod 666 /var/run/docker.sock
~~~

Đây là ví dụ **sai về bảo mật**, không áp dụng trong CI. Dùng dedicated runner, UID/GID được quản lý và giới hạn trusted repositories/branches.

- Không cấp socket/privileged cho untrusted pull requests.
- Không mở Docker API TCP 2375 ra Internet hoặc mạng shared.
- Nếu remote Docker API, bảo vệ bằng TLS 2376/client cert hoặc phương án được admin phê duyệt.
- Không để Docker secrets trong logs/volumes của job không tin cậy.
- Không chạy job cleanup có thể xóa containers của jobs khác trên shared daemon.
- Không suy rằng job container không privileged thì an toàn khi socket đã mount.

## 7. Ryuk resource reaper và cleanup

Ryuk là Testcontainers helper container giúp thu dọn Docker resources khi JVM/test session chết bất thường. Nó có thể bị runner policy chặn, đặc biệt với môi trường không cho privileged helper.

Testcontainers cho phép:

~~~bash
export TESTCONTAINERS_RYUK_DISABLED=true
~~~

**Chỉ dùng nếu có cleanup thay thế đáng tin**: ephemeral VM/daemon bị hủy sau job hoặc resource cleanup quản lý theo job ownership. Trên self-hosted persistent daemon, disable Ryuk có thể để lại orphan containers sau kill -9/crash, làm đầy disk.

| Dấu hiệu | Hướng giải quyết |
| --- | --- |
| Ryuk privileged denied | Security policy, dedicated runner hoặc cleanup alternative |
| No valid Docker environment | Socket/DOCKER_HOST/TLS, không phải luôn Ryuk |
| Postgres exited 137 | Memory/OOM investigation |
| Image pull 429 | Registry auth/rate-limit |
| JDBC connection refused | Mapped-port network/readiness |
| No space left | Docker layers/volumes/inodes |

Tắt Ryuk không tự cấp quyền cho DinD daemon bị cấm start.

## 8. Registry auth, image pinning và helper images

Testcontainers có thể pull cả image trong source code và **helper images** như Ryuk/Alpine/network tools. Do đó doanh nghiệp dùng private registry mirror phải có chính sách cho helper images, không chỉ `postgres`.

| Failure | Nguyên nhân |
| --- | --- |
| 401 | Registry authentication sai |
| 403 | Không có quyền image |
| 429 | Registry rate limit |
| Manifest unknown | Image tag/digest/architecture sai |
| x509 failure | TLS CA/proxy |
| I/O timeout | DNS/egress |
| No space | Docker image storage đầy |

Dùng Docker auth ở CI secret store hoặc `DOCKER_CONFIG`/`DOCKER_AUTH_CONFIG` đúng runtime, không commit config hay in secrets.

Image ví dụ:

~~~java
new PostgreSQLContainer<>("postgres:16-alpine");
~~~

Tag major 16 chưa hoàn toàn bất biến: để reproducible benchmark nên pin patch tag/digest. Tránh `latest` khi muốn biết chính xác version. Docker image cache và Gradle dependency cache **là hai caches khác nhau**; GitHub ephemeral VM có thể pull lại Docker layers mỗi job.

## 9. Tính CPU, RAM và disk cho runner

Memory budget khái niệm:

~~~text
RAM runner ~= OS + Docker daemon
           + Gradle JVM
           + all Test JVM working sets
           + all live container memory
           + caches/native memory/headroom
~~~

Đây không phải công thức OOM chính xác do shared pages/cgroups/overcommit. Ví dụ **giả định, không phải thông số GitHub runner**:

| Thành phần | Ngân sách minh họa |
| --- | ---: |
| OS + Docker | 1.0 GiB |
| Gradle | 0.7 GiB |
| Một Test worker JVM | 1.5 GiB |
| Postgres | 0.6 GiB |
| Redis | 0.2 GiB |
| Kafka | 1.5 GiB |
| Headroom/cache | 2.0 GiB |
| Tổng | 7.5 GiB |

Một host 8 GiB sẽ rất sát ở peak; nếu tăng forks/containers có thể OOM. Java `-Xmx` chỉ giới hạn heap, không bao gồm native memory, threads, metaspace, direct buffers, page cache.

### Disk, inode và shared memory

Disk gồm pulled layers, writable DB volumes, Gradle caches, compiled classes và reports. `df -i` cần được xem khi `No space left` nhưng vẫn còn GB. Browser/Elasticsearch/DB còn có `/dev/shm`, file descriptors, thread/PID limits. Không tăng startup timeout để chữa thiếu RAM/disk.

### Exit 137

Exit 137 có thể là SIGKILL vì OOM nhưng cần kiểm:

~~~bash
docker inspect --format '{{.State.ExitCode}} {{.State.OOMKilled}}' CONTAINER_ID
~~~

Thay `CONTAINER_ID` bằng ID thật. Kết hợp cgroup metrics/host logs; không gán mọi exit 137 cho Java code.

## 10. Gradle forks và số containers đồng thời

CI có thể song song ở nhiều tầng:

1. Nhiều jobs trong CI matrix.
2. Gradle `maxParallelForks`.
3. JUnit parallel classes/methods.
4. Static/instance `@Container`.
5. Nhiều services/containers mỗi test.
6. Shared Docker daemon trên self-hosted runner.

Nếu một class cần Postgres + Kafka, bốn Gradle forks và nhiều jobs có thể nhân số containers lên đáng kể. Để chẩn đoán baseline:

~~~groovy
tasks.withType(Test).configureEach {
    maxParallelForks = 1
    forkEvery = 0
}
~~~

Sau khi baseline ổn định, đo CPU/RAM peaks, container count, test wall time rồi mới tăng concurrency. `forkEvery=1` tạo Test JVM mới sau mỗi class, giảm hiệu quả Spring TestContext cache xuyên classes.

## 11. @Container và Spring TestContext cache

JUnit 5:

~~~java
@Testcontainers
class RepositoryTests {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Static `@Container` thường start một lần **per test class**, stop sau class. Instance `@Container` start/stop mỗi test method.

**Bẫy cache context:**

~~~text
Class A starts static container A
  -> Spring context X caches DataSource URL of A
Class A ends -> JUnit stops A
Class B reuses cached context X
  -> DataSource points to stopped A -> JDBC FAIL
~~~

Nếu dùng nhiều classes chung context, cân nhắc container bean do Spring context quản lý hoặc cô lập context/lifecycle đúng. `@ServiceConnection` tạo connection details nhưng không tự biến static @Container thành singleton toàn suite.

Không dùng `@DirtiesContext` mọi method nếu có thể reset fixtures an toàn. Trường hợp context bị mutate không hồi phục được, đánh dirty là đúng dù tốn thời gian.

## 12. Demo Spring Boot 3.5/Java 17 có PostgreSQL thật

Cấu trúc dự án:

~~~text
ci-testcontainers-demo/
  settings.gradle
  build.gradle
  src/main/java/example/ci/
    CiDemoApplication.java
    InventoryRules.java
  src/test/java/example/ci/
    InventoryRulesTest.java
    InventoryPostgresTest.java
  .github/workflows/test.yml
~~~

Có **4 JUnit @Test methods**: 2 unit không Docker, 2 integration có PostgreSQLContainer. Không cần Docker Compose, Flyway hoặc service bên ngoài.

### settings.gradle

~~~groovy
rootProject.name = 'ci-testcontainers-demo'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0
    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
    reports {
        html.required = true
        junitXml.required = true
    }
}

tasks.register('unitTest', Test) {
    group = 'verification'
    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform { includeTags 'unit' }
}

tasks.register('integrationTest', Test) {
    group = 'verification'
    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform { includeTags 'integration' }
}
~~~

Spring Boot dependency management chọn versions Testcontainers modules phù hợp BOM; không tự trộn hai Testcontainers major versions. Các bản pin cho demo không khẳng định là versions mới nhất. Cần Gradle wrapper tương thích được commit để chạy CI.

### CiDemoApplication.java

~~~java
package example.ci;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CiDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CiDemoApplication.class, args);
    }
}
~~~

### InventoryRules.java

~~~java
package example.ci;

public final class InventoryRules {
    private InventoryRules() {
    }

    public static boolean canReserve(int available, int requested) {
        return available >= 0
                && requested > 0
                && available >= requested;
    }
}
~~~

### InventoryRulesTest.java — hai unit methods

~~~java
package example.ci;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("unit")
class InventoryRulesTest {
    @Test
    void acceptsValidReservation() {
        assertTrue(InventoryRules.canReserve(7, 3));
    }

    @Test
    void rejectsInvalidReservation() {
        assertFalse(InventoryRules.canReserve(7, 8));
        assertFalse(InventoryRules.canReserve(7, 0));
        assertFalse(InventoryRules.canReserve(-1, 1));
    }
}
~~~

Hai tests này không khởi tạo Spring context/Docker. Chúng có thể chạy ở fast CI lane, nhưng phải có một integration gate riêng cho DB behavior.

### InventoryPostgresTest.java — hai real PostgreSQL methods

~~~java
package example.ci;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("integration")
@Testcontainers
@SpringBootTest(classes = CiDemoApplication.class)
class InventoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("ci_inventory")
                    .withUsername("ci_user")
                    .withPassword("ci_password");

    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void prepare() {
        jdbc.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    sku VARCHAR(64) PRIMARY KEY,
                    available INTEGER NOT NULL
                )
                """);
        jdbc.update("DELETE FROM inventory");
    }

    @Test
    void insertsAndReadsFromRealDatabase() {
        int rows = jdbc.update(
                "INSERT INTO inventory (sku, available)"
                + " VALUES (?, ?)", "SKU-1", 7);
        Integer quantity = jdbc.queryForObject(
                "SELECT available FROM inventory WHERE sku = ?",
                Integer.class, "SKU-1");

        assertEquals(1, rows);
        assertEquals(7, quantity);
        assertTrue(postgres.isRunning());
    }

    @Test
    void duplicatePrimaryKeyIsRejected() {
        jdbc.update(
                "INSERT INTO inventory (sku, available)"
                + " VALUES (?, ?)", "SKU-2", 4);
        assertThrows(DataIntegrityViolationException.class,
                () -> jdbc.update(
                    "INSERT INTO inventory (sku, available)"
                    + " VALUES (?, ?)", "SKU-2", 9));
    }
}
~~~

`@ServiceConnection` có trong `spring-boot-testcontainers`, tạo JDBC connection details cho PostgreSQLContainer. Không hardcode localhost:5432; Testcontainers dùng mapped port động. Tests kiểm SQL insert/read và primary-key constraint thật, không phải Mockito stub.

`@BeforeEach` dọn fixtures. Không bật parallel methods sử dụng cùng table/DB trừ khi cách ly rows/schemas đúng.

### Chạy Gradle

~~~bash
./gradlew unitTest
./gradlew integrationTest
./gradlew clean test
~~~

`unitTest` chỉ có 2 methods; `integrationTest` 2 methods; `test` mặc định chạy cả 4. Không chạy cả `unitTest integrationTest test` rồi đếm tổng 4 invocations — cùng test có thể được chạy ở nhiều tasks. Ví dụ dự kiến PASS khi Docker/PostgreSQL khả dụng, **chưa chạy Gradle thực tế**.

## 13. GitHub Actions workflow trên Ubuntu VM

File `.github/workflows/test.yml`:

~~~yaml
name: Spring Boot Testcontainers CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 30

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Docker preflight
        shell: bash
        run: |
          set -euo pipefail
          docker version
          docker info --format 'Server={{.ServerVersion}}'
          df -h
          df -i
          free -m
          docker system df

      - name: Run JUnit tests
        shell: bash
        run: |
          chmod +x ./gradlew
          ./gradlew --no-daemon clean test --stacktrace

      - name: Failure diagnostics
        if: failure()
        shell: bash
        run: |
          docker ps -a || true
          docker system df || true
          df -h || true

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: spring-test-results
          path: |
            build/test-results/test/
            build/reports/tests/test/
          if-no-files-found: warn
          retention-days: 7
~~~

Workflow dùng **GitHub Ubuntu VM**, không khai báo job-level `container:` hay DinD. Docker thường có sẵn trên loại runner này nhưng preflight vẫn cần kiểm. Không tạo thêm `services: postgres`, vì PostgreSQLContainer đã sở hữu DB riêng.

`ubuntu-24.04` tránh OS label `ubuntu-latest` thay đổi major distro bất ngờ, nhưng image vẫn được cập nhật. Specs public/private hosted runners khác nhau; kiểm GitHub Docs.

`if: always()` lưu JUnit reports dù test FAIL. Không upload Docker auth config, TLS private keys, container volumes có customer data hoặc full environment dump.

## 14. GitLab CI Docker-in-Docker

Ví dụ **chỉ áp dụng cho privileged isolated runner đã được admin phê duyệt**:

~~~yaml
stages:
  - test

testcontainers:
  stage: test
  image: eclipse-temurin:17-jdk
  tags:
    - isolated-dind

  services:
    - name: docker:27-dind
      alias: docker
      command: ["--tls=false"]

  variables:
    DOCKER_HOST: "tcp://docker:2375"
    DOCKER_TLS_CERTDIR: ""
    DOCKER_DRIVER: "overlay2"

  script:
    - chmod +x ./gradlew
    - ./gradlew --no-daemon clean test --stacktrace

  artifacts:
    when: always
    expire_in: 7 days
    paths:
      - build/test-results/test/
      - build/reports/tests/test/
~~~

**Cảnh báo bảo mật:** daemon TCP 2375 không TLS phải bị cô lập trong ephemeral CI service network. Đối với runner production/long-lived, cân nhắc TLS 2376 với certificates, protected socket-runner hoặc managed Docker API. YAML này không tự bật privileged nếu runner policy cấm; lỗi DinD `operation not permitted` phải sửa ở tầng runner provisioning.

### GitLab socket binding

Mô hình socket của GitLab self-hosted runner có thể giảm overhead DinD nhưng trao quyền mạnh tới Docker host. Chỉ dùng trusted dedicated runner; không coi `privileged=false` của build container là bảo vệ đầy đủ khi socket đã mount.

## 15. GitHub job container khác host VM

Nếu thêm:

~~~yaml
jobs:
  test:
    runs-on: ubuntu-24.04
    container:
      image: eclipse-temurin:17-jdk
~~~

thì Gradle/JUnit chạy trong **job container**. `localhost` trỏ vào container đó chứ không phải VM. Docker socket, mapped ports và bind mount paths có thể không tự hoạt động như workflow VM.

Trước khi chuyển, kiểm Docker API detection, host override, networking, workspace mount path, user permissions và chính sách bảo mật. Bài mẫu dùng host VM để đơn giản hóa.

## 16. Kubernetes và Jenkins

- **Jenkins VM agent:** như Ubuntu VM nếu Docker Engine/socket accessible.
- **Jenkins Docker agent:** cần Docker wormhole/DinD/remote runtime.
- **Kubernetes executor:** containerd/CRI không đồng nghĩa có Docker API.
- **Restricted PodSecurity:** không tự bật privileged/hostPath; cần isolated/remote/managed runtime.
- **Self-hosted persistent runner:** cần quota, resource cleanup theo job ownership và không dùng `docker system prune` trên host shared.
- **Untrusted PR jobs:** không đưa socket, privileged mode hay registry/cloud secrets.

## 17. Khi Docker API OK nhưng JDBC FAIL

Kiểm thứ tự:

1. JVM đang trên VM hay trong job container?
2. `DOCKER_HOST` đang trỏ daemon nào?
3. `postgres.getHost()`/`getMappedPort(5432)` sau start là gì?
4. Docker mapped port có reachable từ JVM không?
5. Có `TESTCONTAINERS_HOST_OVERRIDE` sai không?
6. PostgreSQL đã ready theo wait strategy chưa?
7. Container logs/exit code/OOMKilled ra sao?
8. Spring Boot DataSource có nhận `@ServiceConnection` không?
9. Firewall/DNS/network alias của DinD ra sao?

Đừng sửa bằng `Thread.sleep(10000)`. Nếu network route sai, chờ thêm không giúp.

## 18. Startup timeout và image pull timeout

Testcontainers module có wait strategy cho dependency. Nếu service startup thật chậm ở runner thiếu CPU, có thể điều chỉnh timeout khi có bằng chứng:

~~~java
new PostgreSQLContainer<>("postgres:16-alpine")
        .withStartupTimeout(java.time.Duration.ofMinutes(2));
~~~

Snippet này minh họa **container service startup deadline**. Nó không sửa registry 401/429, socket permission denied, Docker API TLS lỗi hay JDBC mapped host unreachable.

Phân biệt: CI job timeout, Docker image pull timeout, container readiness timeout, JDBC connect timeout, HTTP client timeout và JUnit method timeout.

## 19. Troubleshooting matrix

| Triệu chứng | Hướng điều tra |
| --- | --- |
| No valid Docker environment | Docker socket/DOCKER_HOST/TLS |
| Permission denied docker.sock | Runner UID/GID/security |
| DinD mount denied | Privileged/cgroups |
| Ryuk cannot start | Helper policy/cleanup |
| Image pull 401/403 | Registry credentials |
| Image pull 429 | Rate limit/mirror |
| x509 unknown authority | CA/proxy TLS |
| Postgres exited 137 | OOM/cgroup limits |
| No space left on device | Disk/inodes/volumes |
| JDBC refused after start | Mapped-port routing |
| Spring DataSource fails | @ServiceConnection/credentials/DB readiness |
| SQL assertion fails | Fixtures/business logic |
| Test task skips integration | JUnit tags/CI gate |
| Build hangs after tests | Threads/container cleanup |

**Retry là giải pháp cuối cho transient failures**, không phải cách chữa no socket, missing permission hay invalid registry image.

## 20. Thu thập diagnostics không rò secrets

Ghi lại: JUnit XML/HTML, runner label, Docker/JDK/Gradle versions, image tag/digest, Docker disk summary, test-owned container exit codes/OOMKilled, startup duration và sanitized logs.

Không đăng: `DOCKER_AUTH_CONFIG`, Docker private TLS cert, toàn bộ env, customer database volume, full inspect của unrelated jobs hoặc `/var/lib/docker`. Self-hosted daemon thường chứa containers của nhiều job; diagnostic/cleanup phải giới hạn theo ownership.

## 21. Hiệu năng và tối ưu theo số đo

Đo riêng:

~~~text
image pull/cache lookup
   -> container create/start
   -> wait strategy ready
   -> Spring context / JDBC pool
   -> first query
   -> JUnit method body
   -> cleanup
~~~

`container.start()` có thể bao gồm cold image pull và Testcontainers helper setup. Không so local warm image với hosted ephemeral CI cold image rồi kết luận Spring Boot regression.

Các hướng tối ưu:

- Dùng unit tests không Docker khi không cần DB.
- Giữ integration gate bắt buộc trước release.
- Dùng Spring TestContext cache khi test configuration và fixture isolation cho phép.
- Không `@DirtiesContext` mọi method nếu reset data được.
- Chọn container lifecycle cùng với context lifecycle.
- Pin images/approved mirrors, tránh registry rate-limit.
- Tăng Gradle forks chỉ sau khi đo runner CPU/RAM và container concurrency.
- Không dùng Testcontainers reuse trên shared CI thiếu data isolation.
- Không tắt Ryuk hoặc disable integration suite chỉ để pipeline xanh.

### Checklist cuối

- [ ] Docker API accessible từ đúng JUnit JVM process.
- [ ] Docker daemon/image registry có credentials/network.
- [ ] Docker API host khác mapped JDBC host được hiểu đúng.
- [ ] Không hardcode localhost:5432.
- [ ] Socket/privileged mode chỉ cho trusted jobs.
- [ ] Remote Docker API có TLS/auth.
- [ ] Ryuk hoạt động hoặc cleanup thay thế đã được đảm bảo.
- [ ] RAM/CPU/disk/inode budget phản ánh peak concurrent jobs.
- [ ] Images được pin, registry auth không lộ logs.
- [ ] Java17/Boot3.5/@ServiceConnection dùng đúng dependencies.
- [ ] Unit tests tách khỏi DB integration tests.
- [ ] Context cache không giữ DataSource tới stopped container.
- [ ] Không chạy parallel tests xóa cùng table.
- [ ] Docker preflight và JUnit artifacts tồn tại ngay khi FAIL.
- [ ] Không prune shared Docker daemon vô điều kiện.
- [ ] Benchmark phân biệt cold và warm image pulls.
- [ ] Integration suite không bị skip âm thầm.

## 22. Kết luận

**Docker trên CI runner là một phần thiết yếu của Testcontainers testing contract.** JVM cần Docker API, runtime cần quyền và tài nguyên, image registry cần reachable, còn mapped service ports phải được route tới test JVM. Trên Ubuntu VM, cấu hình thường đơn giản; trong Docker job containers, DinD hoặc Kubernetes, socket/network/TLS/privileged policies là những điểm cần thiết kế kỹ.

Một pipeline đáng tin dùng preflight, resource budgeting, connection details từ Testcontainers, wait strategy đúng, cleanup theo ownership và JUnit diagnostics an toàn. Không sửa lỗi môi trường bằng cách lạm dụng sleep, tắt Ryuk, prune shared resources hoặc skip toàn bộ integration tests.

### Tài liệu tham khảo chính thức

- [Testcontainers for Java — Supported Docker Environments](https://java.testcontainers.org/supported_docker_environment/)
- [Testcontainers for Java — Custom Configuration](https://java.testcontainers.org/features/configuration/)
- [Testcontainers for Java — Tests Inside Docker Containers](https://java.testcontainers.org/supported_docker_environment/continuous_integration/dind_patterns/)
- [Testcontainers for Java — GitLab CI](https://java.testcontainers.org/supported_docker_environment/continuous_integration/gitlab_ci/)
- [Testcontainers for Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers — Registry Rate Limiting](https://java.testcontainers.org/supported_docker_environment/image_registry_rate_limiting/)
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Docker — Protect Daemon Socket](https://docs.docker.com/engine/security/protect-access/)
- [GitHub Actions — Choosing Runner](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)
- [GitLab — Docker Runner Setup](https://docs.gitlab.com/ci/docker/using_docker_build/)
- [Gradle — Testing in Java](https://docs.gradle.org/current/userguide/java_testing.html)
