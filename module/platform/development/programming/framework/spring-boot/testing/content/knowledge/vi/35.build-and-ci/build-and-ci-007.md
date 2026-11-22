# Cache dependency, image và giới hạn của việc tái sử dụng kết quả test

## 1. Mục tiêu và câu hỏi chính

Trong nhóm **Build và CI** của **Spring Boot - testing**, cache có thể giảm đáng kể thời gian tải dependency, biên dịch và khởi động container. Tuy nhiên, **cache hit không đồng nghĩa bộ test đã được thực thi trong lần CI hiện tại**. Một pipeline xuất hiện kết quả xanh vẫn có thể chưa kiểm tra lại database, Kafka, API bên ngoài, secrets hoặc image vừa đổi.

Bài phân biệt rõ bốn đối tượng:
1. **Dependency cache:** thư viện, metadata dependency resolution và bản Gradle Wrapper đã tải.
2. **Configuration Cache:** kết quả cấu hình build, task graph và task state.
3. **Gradle Build Cache / up-to-date checks:** outputs của tasks được khôi phục hoặc tái sử dụng khi declared inputs tương ứng không đổi, bao gồm cả outputs của task **Test** khi đủ điều kiện.
4. **Docker image/layer cache:** layers của image đã pull hoặc đã build; không phải database state, đang-running container hay báo cáo test mới.

Mục tiêu học tập là **phân loại cache nào an toàn**, đọc **UP-TO-DATE / FROM-CACHE**, kiểm soát **hidden inputs** của integration tests, tổ chức Spring Boot Gradle/JUnit suites, dùng **Gradle setup trên CI**, hiểu cache Docker/Testcontainers images và tránh **cache poisoning/secret leakage**.

Ví dụ hoàn chỉnh dùng **Java 17+, Spring Boot 3.4.5, Gradle, JUnit Jupiter, @WebMvcTest/MockMvc và @SpringBootTest(RANDOM_PORT)**. Unit/MVC tests được phép hưởng lợi từ build cache nếu deterministic; task **integrationTest** được cấu hình **không up-to-date và không build-cache reuse**, vì nó phải gửi request tới embedded HTTP server thật. Các expected results là lý giải từ mã; **chưa có lần chạy Gradle hoặc CI thực tế được quan sát khi biên soạn bài**.

## 2. Các lớp cache khác nhau về dữ liệu và mức độ tin cậy

| Cơ chế | Lưu cái gì? | Chi phí tránh được | Không chứng minh |
| --- | --- | --- | --- |
| Gradle Dependency Cache | JAR, POM, Gradle Module Metadata, metadata resolution | Download/resolve lại dependency | Tests đã chạy |
| Gradle Wrapper Cache | Gradle distribution | Download phiên bản Gradle | Test task đúng |
| Configuration Cache | Configured task graph/state | Configuration phase | Test execution hiện tại |
| Up-to-date check | So khớp local task inputs/outputs | Task actions | External service hiện khỏe |
| Gradle Build Cache | Cacheable task outputs theo cache keys | Recompute compilation/test reports | Live integration tests được chạy lại |
| GitHub Actions Cache | Reusable directories giữa workflow jobs | Remote fetch/compile state | Artifact từ run mới |
| Docker pulled layers | Image blobs/layers trong daemon | Download image | Container đã start |
| BuildKit cache | Intermediate Docker build layers | Rebuild layer không đổi | Image đã load vào daemon |
| Testcontainers images | Image runtime sẵn có theo Docker runtime | Image pull | Database schema và data đúng |
| CI artifacts | HTML/XML test reports, logs | Bảo quản evidence | Input model của cache tự đúng |

**Cache** chủ yếu tăng tốc; một lần cache miss phải có thể tự tải/tạo lại nguồn hợp lệ. **Artifact** dùng để lưu báo cáo hay đầu ra có thể xem lại. Không dùng actions/cache như nơi lưu vĩnh viễn duy nhất cho XML reports, coverage hoặc chứng cứ release.

## 3. Gradle dependency cache: nhanh hơn, chưa đủ để đúng

Gradle User Home thường tại **~/.gradle** hoặc **GRADLE_USER_HOME**. Cache artifacts/metadata thường dưới **~/.gradle/caches/modules-2**, Gradle Wrapper distributions dưới **~/.gradle/wrapper**. Khi một dependency đã cache và metadata còn hợp lệ, Gradle có thể không cần download lại. Nhưng cache không thay quá trình kiểm dependency graph, versions, constraints và conflict resolution.

Ví dụ build Spring Boot có versions cụ thể:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Cache hit không bảo đảm tất cả dependencies đều nằm trong runtime classpath. Một artifact cached vẫn có thể bị loại khỏi configuration do resolution rules/capabilities. Cần inspect dependency graph đúng configuration.

### Dynamic và changing dependencies

Version động như **1.+**, **latest.release**, hoặc một dependency **SNAPSHOT** có thể resolve sang nội dung/version khác tại thời điểm khác. Gradle cache metadata của **dynamic versions** và **changing modules** theo TTL; mặc định thường là **24 giờ**, có thể tùy chỉnh. Hai máy với cache khác tuổi có thể resolve khác nhau dù source code không đổi.

Khuyến nghị:
- Ghim dependency versions hợp lý và dùng Spring Boot BOM/version catalog.
- Dùng **dependency locking** khi cần tái hiện exact resolved versions.
- Dùng **dependency verification** (checksum/signature) cho supply-chain controls.
- Review metadata/lockfile khi nâng cấp.
- Không dùng cache hit để suy luận upstream registry chưa đổi.
- Không bỏ qua verification hoặc repository trust vì đã có jar trong Gradle cache.

### --offline và --refresh-dependencies

~~~bash
./gradlew dependencies --offline
./gradlew dependencies --refresh-dependencies
./gradlew test --refresh-dependencies
~~~

**--offline** chỉ dựa trên dependency cache, có thể fail nếu thiếu artifact. **--refresh-dependencies** revalidate dependencies/metadata với repositories theo Gradle semantics; nó không bắt buộc xóa tất cả jars và **không phải lệnh force test execution**. Nếu test task vẫn UP-TO-DATE hay FROM-CACHE, cần cách khác để chạy lại.

### Wrapper là nguồn Gradle version

Commit **gradlew**, **gradlew.bat**, **gradle/wrapper/gradle-wrapper.properties** và wrapper JAR đáng tin cậy. CI nên dùng Wrapper thay vì bản Gradle ngẫu nhiên được cài sẵn. Có thể đặt distribution checksum, kiểm Gradle Wrapper trước khi build theo supply-chain policy. Dependency cache không bảo đảm plugin hay Gradle version được cập nhật đúng yêu cầu.

**Không cache passwords/tokens** trong ~/.gradle/gradle.properties, Maven repository credentials hoặc signing keys. Gradle User Home có thể chứa nhiều loại state ngoài dependency artifacts; chọn scope cache có kiểm soát.

## 4. Configuration Cache khác Build Cache ra sao?

Gradle build gồm initialization, configuration và execution. **Configuration Cache** giúp bỏ qua công việc configuration khi yêu cầu task, build logic và inputs tương ứng cho phép. **Build Cache** giúp bỏ qua actions của một task **cacheable** bằng output đã tạo cho input key giống nhau.

| | Configuration Cache | Build Cache |
| --- | --- | --- |
| Dữ liệu | Configured task graph/state | Outputs và task artifacts |
| Bỏ qua | Configuration phase | Task execution |
| Key phụ thuộc | Build logic/config/environment config inputs | Task implementation + declared inputs |
| Trạng thái dễ thấy | Reusing configuration cache | :compileJava FROM-CACHE |
| Rủi ro | Unsafe configuration logic, serialized secrets | Hidden inputs, stale results |
| Bật trong CLI | --configuration-cache | --build-cache |

Có thể bật cả hai:

~~~bash
./gradlew test --configuration-cache
./gradlew test --build-cache
./gradlew test --configuration-cache --build-cache
~~~

Hoặc trong gradle.properties:

~~~properties
org.gradle.caching=true
org.gradle.configuration-cache=true
~~~

Đây là **cấu hình tùy chọn**, không bắt buộc cho project runnable bên dưới. Trước khi bật Configuration Cache trên một repo lớn, kiểm compatibility của Gradle plugins, task actions và project-specific build logic. Cache này có thể chứa configured values hoặc credentials nếu task state giữ chúng; không lưu/chia sẻ directory configuration-cache bừa bãi.

**Không đánh đồng một configuration cache hit với việc đã compile hoặc đã chạy test**. Build vẫn có execution phase theo task outcomes.

## 5. Gradle Test task và cache key

Gradle built-in **Test** là loại task có thể cache outputs khi Build Cache được bật và task đủ điều kiện. Gradle input model của Test bao gồm test classes/classpath, task configuration và declared inputs. Khi key match, Gradle có thể restore outputs thay vì chạy JUnit lại.

Build cache giúp những tests **deterministic**, không có trạng thái ngoài được bỏ sót, chạy nhanh. Nhưng test có thể đọc dữ liệu mà Gradle không biết:
- Current clock/timezone/default Locale;
- External database rows/schema, Kafka topics, Redis keys;
- Remote API response hoặc HTTP 503/rate limits;
- Environment variables/secrets/feature flags không declared;
- Docker image tag mới trỏ sang digest mới;
- DNS, TLS certificates, OS/network/port;
- Files ngoài input tree, mounted volumes, user home;
- Random seed, process state, CPU/JDK/architecture differences;
- Cloud service permissions hoặc credentials expiry.

Khi test dựa vào những biến này, **cùng compiled classes không bảo đảm cùng result**. Nếu không khai đầy đủ task inputs, build cache có thể trả kết quả cũ sai với trạng thái môi trường hiện tại.

### Có thể khai inputs tốt hơn không?

Có, với inputs **ổn định và mô hình hóa được**, như một fixture file hay một property quan trọng. Trích đoạn Gradle minh họa:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'app.testing.mode', 'unit'
    inputs.property('testingMode', 'unit')
}
~~~

Nếu test thật đọc fixture file, declare file với path normalization phù hợp. Không thêm arbitrary timestamp vào key để ép mọi lần cache miss; điều đó chỉ mất lợi ích cache mà không chữa nondeterminism.

### Khi không nên cache Test outputs?

Những tests kiểm **môi trường thực đang sống** như database migration, remote API availability, HTTP server socket, broker delivery, IAM permissions hoặc deployment E2E thường nên chạy thật ở acceptance gate. Không chỉ đặt task name *Integration* rồi kết luận không cache; cần xem hidden inputs/side effects thực.

**Một integration test hermetic hoàn toàn và khai báo đủ inputs vẫn có thể cache về kỹ thuật**. Ngược lại, một test tên *UnitTest* nhưng gọi external API vẫn không cache-safe. Quyết định dựa trên input/side effects, không dựa vào tên.

## 6. Đọc Gradle log: UP-TO-DATE và FROM-CACHE

Ví dụ minh họa:

~~~text
> Task :compileJava UP-TO-DATE
> Task :compileTestJava FROM-CACHE
> Task :test FROM-CACHE
> Task :integrationTest

BUILD SUCCESSFUL
~~~

Không phải stdout quan sát được trong bài này. Ý nghĩa:
- **UP-TO-DATE:** local outputs phù hợp với tracked inputs; task actions được skip.
- **FROM-CACHE:** outputs được restore từ cache cho cache key tương ứng; task actions không chạy ở invocation này.
- **EXECUTED/task không có skip label:** task actions đã được chạy; kiểm --info hoặc task outcome chi tiết khi audit.
- **NO-SOURCE:** task không có source tương ứng.
- **SKIPPED:** do onlyIf/disabled/skip conditions, không đồng nghĩa tests pass.
- **FAILED:** task/test failure, CI phải trả non-zero exit code.

Một **JUnit XML report từ FROM-CACHE** có thể chứa tests passed ở lần thực thi cũ. Nó là output đã được Gradle chọn theo fingerprint, không phải bằng chứng JUnit engine đã chạy hôm nay.

**Không nói “100 tests vừa chạy” chỉ vì báo cáo XML ghi 100 passed** nếu task outcome là FROM-CACHE/UP-TO-DATE. Với release gate cần đảm bảo current environment, hãy buộc các tests tương ứng thực thi thật.

## 7. --no-build-cache khác --rerun-tasks

~~~bash
./gradlew test --build-cache
./gradlew test --no-build-cache
./gradlew test --rerun-tasks
./gradlew clean test --no-build-cache
./gradlew test --rerun-tasks --info
~~~

- **--build-cache:** cho phép reuse cacheable task outputs.
- **--no-build-cache:** không dùng Build Cache trong invocation; nhưng **up-to-date checks vẫn có thể skip task**.
- **--rerun-tasks:** force tasks execute, bypass up-to-date checks và build cache reuse; thường làm cả compilation/tests phụ thuộc chạy lại.
- **clean test --no-build-cache:** xóa build outputs local rồi không cache lại; thường giúp chạy lại với fresh outputs, nhưng chi phí cao hơn.
- **--info:** xem nguyên nhân task được cache/skip hoặc execute.
- **--offline:** dependency resolution offline, không force tests.
- **--refresh-dependencies:** revalidate dependency resolution, không force tests.

Không dùng --rerun-tasks vô điều kiện cho mọi developer build nếu cần giữ lợi ích incremental compilation. Thay vào đó phân chia **unit task có thể cache** và **integration task luôn chạy**.

## 8. Ví dụ Gradle/Spring Boot runnable

Ứng dụng có **AccountLabelService** pure logic và **AccountController** exposing REST endpoint. Pure unit tests và @WebMvcTest không dùng external network. Integration test @SpringBootTest(RANDOM_PORT) khởi embedded server và gửi HTTP request thật; vì phải kiểm process state hiện tại, ta cấu hình **integrationTest không cache**.

### Cây tệp

~~~text
settings.gradle
build.gradle
src/main/java/com/example/cacheci/CacheCiApplication.java
src/main/java/com/example/cacheci/AccountLabelService.java
src/main/java/com/example/cacheci/AccountController.java
src/test/java/com/example/cacheci/AccountLabelServiceTest.java
src/test/java/com/example/cacheci/AccountControllerWebTest.java
src/test/java/com/example/cacheci/RandomPortHttpIT.java
.github/workflows/ci.yml
~~~

### 8.1. settings.gradle

~~~groovy
rootProject.name = 'spring-boot-ci-cache-contracts'
~~~

### 8.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    exclude '**/*IT.class'
}

tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'Verify current embedded HTTP server'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    include '**/*IT.class'
    useJUnitPlatform()

    shouldRunAfter(tasks.named('test'))

    // External process/HTTP socket state là hidden input.
    outputs.upToDateWhen { false }
    outputs.doNotCacheIf(
        'requires live embedded HTTP environment'
    ) { true }
}

tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

Đây là một build script hoàn chỉnh cho project mẫu: **Test** task vốn thuộc Java plugin, **integrationTest** là Test task riêng nhưng dùng cùng test source set và classpath. Lọc classes theo hậu tố **IT**; tránh chạy RandomPortHttpIT hai lần ngoài ý muốn.

**outputs.upToDateWhen { false }** chống skip do local outputs. **outputs.doNotCacheIf(...) { true }** chống restore/store output task từ Build Cache. Compilation, dependency resolution và deterministic unit tests vẫn được hưởng cache. **check.dependsOn(integrationTest)** làm Gradle lifecycle check chạy integration tests khi được gọi.

Một project lớn có thể dùng separate **sourceSets.integrationTest**; khi đó phải wire compile/runtime classpaths, fixtures và reporting. Demo dùng một source set để tập trung vào chính sách cache, không tạo phụ thuộc phức tạp.

### 8.3. CacheCiApplication.java

~~~java
package com.example.cacheci;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheCiApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheCiApplication.class, args);
    }
}
~~~

### 8.4. AccountLabelService.java

~~~java
package com.example.cacheci;

import java.util.Locale;

import org.springframework.stereotype.Service;

@Service
public class AccountLabelService {

    public String label(String account, int points) {
        if (account == null || account.isBlank()) {
            throw new IllegalArgumentException(
                "account must not be blank");
        }
        if (points < 0) {
            throw new IllegalArgumentException(
                "points must not be negative");
        }

        return account.toLowerCase(Locale.ROOT)
            + ":" + points;
    }
}
~~~

**Locale.ROOT** tránh phụ thuộc default locale máy CI. Service không đọc clock, network, file hoặc external state, thích hợp cho cache-safe unit tests.

### 8.5. AccountController.java

~~~java
package com.example.cacheci;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    private final AccountLabelService service;

    public AccountController(AccountLabelService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{name}/label",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String label(
            @PathVariable String name,
            @RequestParam int points) {
        return service.label(name, points);
    }
}
~~~

### 8.6. AccountLabelServiceTest.java

~~~java
package com.example.cacheci;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AccountLabelServiceTest {

    private final AccountLabelService service =
        new AccountLabelService();

    @Test
    void normalizesNameWithStableLocale() {
        assertEquals("ada:7", service.label("ADA", 7));
        assertEquals("bob:0", service.label("BOB", 0));
    }

    @Test
    void rejectsBlankAccount() {
        assertThrows(IllegalArgumentException.class,
            () -> service.label(" ", 1));
    }

    @Test
    void rejectsNegativePoints() {
        assertThrows(IllegalArgumentException.class,
            () -> service.label("ADA", -1));
    }
}
~~~

JUnit thuần, không tạo Spring context. Assertions deterministic theo input. Không coi cache làm tăng chất lượng assertion; nó chỉ tái sử dụng outputs khi Gradle tin inputs tương ứng.

### 8.7. AccountControllerWebTest.java

~~~java
package com.example.cacheci;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AccountController.class)
class AccountControllerWebTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private AccountLabelService service;

    @Test
    void routeSerializesLabelWithoutNetwork() throws Exception {
        when(service.label("ADA", 7))
            .thenReturn("ada:7");

        mvc.perform(
            get("/api/accounts/ADA/label")
                .param("points", "7"))
            .andExpect(status().isOk())
            .andExpect(content().string("ada:7"));
    }
}
~~~

**@WebMvcTest** kiểm Spring MVC route/status/body qua MockMvc, không bind TCP listener. **@MockitoBean** là Spring Framework 6.2 bean override mechanism dùng trong Spring Boot 3.4; service mock chỉ dành cho test controller mapping. Đây là một lý do để tách web slice khỏi slow real HTTP integration tests.

### 8.8. RandomPortHttpIT.java

~~~java
package com.example.cacheci;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = WebEnvironment.RANDOM_PORT,
    properties = "server.address=127.0.0.1")
class RandomPortHttpIT {

    @LocalServerPort
    private int port;

    @Test
    void currentEmbeddedServerActuallyHandlesHttp()
            throws Exception {
        assertTrue(port > 0);

        URI uri = URI.create(
            "http://127.0.0.1:" + port
            + "/api/accounts/ADA/label?points=7");

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(5))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("ada:7", response.body());
    }
}
~~~

**RANDOM_PORT** làm OS cấp cổng cho embedded server; **@LocalServerPort** được inject sau khi bind, tránh tranh chấp 8080 trong CI parallel. Tên class kết thúc **IT** nên được chạy bởi **integrationTest**, không phải **test**. Kết quả phụ thuộc khả năng tạo web server và HTTP request hiện tại, nên ta không reuse task outputs.

**Test này không chứng minh Kafka, Postgres, Docker hoặc production API sẵn sàng**. Nó chỉ chứng minh embedded HTTP route hoạt động trong runtime CI hiện tại.

## 9. GitHub Actions CI mẫu: một owner cache và báo cáo mới

Tạo file **.github/workflows/ci.yml**:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Setup Gradle cache
        uses: gradle/actions/setup-gradle@v6
        with:
          cache-provider: basic

      - name: Verify unit and integration tests
        run: ./gradlew test integrationTest --build-cache --stacktrace

      - name: Save reports from this CI job
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-reports
          path: |
            build/reports/tests
            build/test-results
          if-no-files-found: warn
~~~

Các action versions là **major release tags** để minh họa. Với repository bảo mật cao, nên pin **full commit SHA đã review** và cập nhật có kiểm soát. Theo tài liệu gradle/actions, setup-gradle hiện có các providers **enhanced/basic**; ví dụ chọn **cache-provider: basic** để dùng chiến lược cache đơn giản, minh bạch.

**Không vừa dùng setup-gradle vừa bật actions/setup-java cache: gradle hoặc actions/cache riêng cho cùng Gradle User Home**. Những hệ thống cache đè/chồng cùng directories có thể làm khó kiểm snapshot và trust. Chọn **một owner**.

Job kiểm:
- Cache dependency/Wrapper/Gradle User Home nếu có entry.
- Reuse compile outputs khi task inputs match.
- :test có thể được Gradle đánh dấu UP-TO-DATE hoặc FROM-CACHE theo policy.
- :integrationTest **không dùng task output cache và luôn được execute** theo build.gradle.
- Test reports của run được upload dưới artifacts, kể cả khi test task fail (nếu reports tồn tại).
- Workflow exit code của Gradle quyết định pass/fail, không ẩn thất bại bằng continue-on-error.

**Cache miss không phải lỗi:** CI phải có khả năng build bằng cách tải lại dependencies nếu entry bị evict. **Upload artifact không thay cache**: nó giữ reports để xem, không là nơi lưu task outputs cho Gradle reuse.

### Trusted và untrusted cache

Một pull request từ fork không nên có quyền ghi cache để sau đó workflow trusted dùng nội dung đã bị poisoning. GitHub Actions áp các hạn chế với cache scope/triggers; vẫn cần:
- Low-trust PR chỉ **read/restore** theo policy.
- Chỉ trusted push/deployment workflows được write high-trust cache.
- Không chủ động mở write-capable cache mode cho trigger bị actor bên ngoài kiểm soát.
- Không lưu token/password/private key trong cache paths.
- Phân quyền GITHUB_TOKEN tối thiểu và tách signing/deploy jobs khỏi untrusted code.
- Review action/dependency/wrapper versions; cache contents có thể được thực thi gián tiếp.

GitHub Actions cache không phải secret store. Nếu cache được restore từ nơi không đáng tin và dùng để execute scripts/artifacts, nguy cơ **cache poisoning** và supply-chain compromise cần được tính như một trust-boundary vấn đề thực.

## 10. Docker image cache và BuildKit cache khác nhau

**Docker pull cache:** daemon có image layers, lần pull sau có thể tận dụng blobs. GitHub-hosted runners thường ephemeral; không bảo đảm image từ job trước còn trong local daemon.

**Docker BuildKit cache:** lưu intermediate layers theo Dockerfile và build inputs, có thể dùng registry/GitHub Actions cache exporter. Nó không tự khởi DB container hoặc chứng minh SQL works.

**Testcontainers runtime images:** Testcontainers dùng image ref để start container; nếu image chưa có trên daemon, runtime cần pull. Image available giúp giảm pull time, **nhưng container vẫn phải start, đợi health và được test bằng actual operation**.

### Tag mutable vs image digest

Image tag như **postgres:16** có thể thay đổi digest. Nếu test task cache dựa trên compiled classes mà không tính tới image content/runtime DB state, kết quả FROM-CACHE cũ có thể che một regression ở image mới. Khi reproducibility là yêu cầu, pin image bằng **immutable digest** phù hợp và lên kế hoạch security updates. Dù pin image digest vẫn phải kiểm container start, migrations, credentials và SQL behavior trong acceptance integration.

### Không cache mutable database volumes

**Image layers** là artifacts có thể reuse; **database volume/data state** là mutable test fixture. Giữ schema/data từ run trước có thể tạo order dependencies, migrations bị bỏ qua, duplicate IDs hoặc test pass giả. Với CI, ưu tiên:
- Fresh container/schema per suite;
- Migration chạy trong test environment;
- Deterministic seed fixtures;
- Unique test data IDs;
- Cleanup và isolation khi chạy parallel;
- Không bật Testcontainers container reuse bừa bãi trong CI.

### BuildKit layer cache không tự load image

Trích đoạn **minh họa ngoài runnable project**, cần Dockerfile/runner thích hợp:

~~~yaml
- name: Buildx
  uses: docker/setup-buildx-action@v3

- name: Build app image with layer cache
  uses: docker/build-push-action@v6
  with:
    context: .
    load: true
    tags: example/app:ci
    cache-from: type=gha,scope=app
    cache-to: type=gha,mode=max,scope=app
~~~

**cache-from/cache-to** dành cho Docker build layers. **load: true** hướng tới image trong Docker daemon local cho bước docker run trong job, với builder/driver hỗ trợ. Không đồng nghĩa postgres:16 đã được pull vào daemon, cũng không đồng nghĩa Testcontainers được chạy.

## 11. Testcontainers: mapped host ports và @ServiceConnection

Một Testcontainers PostgreSQL server có **container port 5432**, nhưng Docker thường map nó tới **host port động**. Java test JVM không nên hard-code localhost:5432. Ví dụ minh họa:

~~~java
@Testcontainers
class DatabaseContainerExample {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @Test
    void inspectRuntimeEndpoint() {
        assertTrue(postgres.isRunning());
        int hostPort = postgres.getMappedPort(5432);
        assertTrue(hostPort > 0);
    }
}
~~~

Đây **không phải file runnable của project demo**; cần Testcontainers JUnit Jupiter/PostgreSQL dependencies và imports. **getMappedPort** phải gọi sau khi container start. Với PostgreSQLContainer thường dùng **getJdbcUrl/getUsername/getPassword** hoặc Spring Boot **@ServiceConnection** thay vì tự ghép URL.

Spring Boot 3.4 hỗ trợ minh họa:

~~~java
@Container
@ServiceConnection
static PostgreSQLContainer<?> db =
    new PostgreSQLContainer<>("postgres:16");
~~~

Cần **spring-boot-testcontainers**, correct runtime driver và Spring Boot/Testcontainers integration. @ServiceConnection cung cấp ConnectionDetails, có precedence hơn datasource connection properties tương ứng. Do đó Testcontainers success **không chứng minh production JDBC URL/secrets đúng** nếu test đã override chúng.

### Phân biệt cache image và cache test results

Hãy cache image/download layers nếu có lợi, nhưng giữ **integrationTest execution** để kiểm:
- DB container thực sự start;
- Health/migrations thành công;
- JDBC connection hoặc SQL query chạy;
- Contract của schema phiên bản hiện tại;
- Test-owned fixtures và cleanup đúng;
- Không xảy ra race/port collision.

Một CI image pull nhanh nhưng bỏ qua SQL assertion không bảo vệ release.

## 12. Những hidden inputs phổ biến trong Spring Boot tests

| Hidden input | Nếu bị bỏ sót | Thiết kế test |
| --- | --- | --- |
| System clock | Output hôm nay khác hôm qua | Inject Clock.fixed cho deterministic unit |
| Default Locale/timezone | String/date formatting lệch | Locale.ROOT, explicit ZoneId |
| Random seed | Flaky assertion | Fixed seed hoặc deterministic fixture |
| External API | Upstream status/contract đổi | Stub unit; live integration always-run |
| DB migrations/schema | Schema thay đổi | Testcontainers/integration always-run |
| Kafka topic/Redis keys | Shared state/consumer offsets | Isolated namespaces, cleanup |
| Environment/profile | Config branch khác | Declare inputs hoặc per-profile CI |
| Secrets/token expiry | Authentication hôm nay fail | Live auth check trong trusted gate |
| Docker tag/digest | Image đổi nội dung | Digest pin + execution |
| TLS/DNS | Cert/route thay đổi | Current environment check |
| OS/JDK version | Runtime behavior khác | CI matrix, verify actual task execution |
| Static singleton/file | Cross-test contamination | Remove shared state; temp directories |
| Fixed ports | CI port conflict | RANDOM_PORT, Testcontainers mapped ports |

**Không gắn timestamp vào mọi cache key** như cách chữa hidden inputs. Điều đó chỉ khiến cache miss vô điều kiện mà không làm test có isolation. Nếu business logic deterministic, mô hình hóa inputs; nếu test xác minh current environment, cấu hình always-run riêng.

### @Transactional qua real HTTP

Trong @SpringBootTest(RANDOM_PORT), HTTP request chạy ở server thread khác test thread. **@Transactional trên test method không tự rollback DB writes do server request tạo ra**. Vì vậy dù task integrationTest luôn chạy, DB state vẫn có thể rò giữa tests nếu thiếu fixtures/cleanup. Cache và isolation là hai chủ đề có liên quan nhưng khác nhau.

### Spring TestContext cache không phải Gradle Build Cache

Spring TestContext **ApplicationContext cache** reuse một context giữa test methods/classes có cùng configuration trong một test JVM. Nó giảm startup cost bên trong test run. Nó **khác** Gradle Test task FROM-CACHE:
- Spring context reused vẫn có thể khiến test methods **chạy thật**.
- Gradle task FROM-CACHE có thể không khởi test JVM/JUnit engine lần này.
- @DirtiesContext làm context mới trong TestContext, **không phải** cách force Gradle rerun tasks.
- --rerun-tasks force Gradle task execution, không đảm bảo mỗi method có ApplicationContext riêng.

Đừng nhầm hai mức reuse khi điều tra test results.

## 13. Test reports: artifacts của job khác cache hit

CI có thể upload **build/reports/tests/** và **build/test-results/** dưới artifacts, hữu ích cho review thất bại/coverage. Nhưng cần ghi rõ:
- Report thuộc invocation/task execution nào.
- Test task outcome có phải FROM-CACHE hay UP-TO-DATE.
- Những test suites nào được thực thi.
- Có test classes bị exclude/NO-SOURCE không.
- Failure exit code có được pipeline truyền đúng không.
- Report cũ trong cache không được coi là evidence current job một cách tự động.

**Cache một thư mục build/test-results bằng actions/cache với key theo branch là anti-pattern**: GitHub cache không có Gradle task input validation cho JUnit results. Nếu muốn tái dùng Test outputs, dùng Gradle Build Cache với mô hình inputs đúng; nếu cần current integration evidence, không reuse Test task output.

## 14. Dependency locking, verification và reproducibility

Cache giúp hiệu năng nhưng **không tự bảo vệ khỏi supply-chain changes**. Nên xem xét:
1. Dependency versions cụ thể, Spring Boot BOM/version catalog.
2. Gradle dependency locking cho resolved graph.
3. Dependency verification qua checksum/signature metadata được review.
4. Gradle Wrapper version/distribution checksum và wrapper JAR validation.
5. SHA-pinned/approved GitHub Actions trong môi trường sensitive.
6. Container image digest pin khi reproducibility yêu cầu.
7. Audit versions và security updates thay vì giữ cache stale vô hạn.
8. Trust controls giữa PR forks và privileged CI jobs.

Gradle commands minh họa:

~~~bash
./gradlew dependencies --write-locks
./gradlew --write-verification-metadata sha256 help
~~~

Cần thật sự enable dependency locking trong build và resolve relevant configurations; một lệnh không bảo đảm toàn bộ graph locked. Review lockfiles và verification metadata, không chấp nhận mọi artifact hash tự động. **Reproducible dependency graph vẫn không có nghĩa external database đã được kiểm hôm nay**.

## 15. Configuration Cache và bí mật

Configuration Cache lưu task graph/configured state và có thể chứa values đã được lấy trong configuration phase, gồm credentials nếu build logic sử dụng không an toàn. Khi chia sẻ cache:
- Dùng Provider API, tránh lấy secret quá sớm.
- Không serialize passwords/tokens vào task fields khi không cần.
- Đọc hướng dẫn Gradle encryption key/trust model cho cross-job Configuration Cache.
- Không cache project .gradle/configuration-cache sang repository/untrusted archive tùy tiện.
- Restrict cache write cho trusted workflows; tránh cache poisoning.
- Không để test log/stack trace in raw credential values.
- Cache eviction phải không làm mất khả năng build.

**GitHub Actions cache không phải secret store**. Kể cả khi đã có encryption mechanism, key management và actor permissions vẫn cần review.

## 16. Khi nghi “test xanh nhờ cache” thì kiểm gì?

Một quy trình chẩn đoán:
1. Đọc task outcomes ở Gradle log, không chỉ BUILD SUCCESSFUL.
2. Kiểm :test có **FROM-CACHE, UP-TO-DATE hay EXECUTED**.
3. Kiểm task integrationTest **đã được yêu cầu** và không bị excludes/onlyIf.
4. Chạy thử có chủ đích với **--rerun-tasks --info**.
5. Nếu outcomes khác nhau, phân tích hidden inputs, leaked global state, external dependency availability và flaky timing.
6. Kiểm Gradle Wrapper, JDK, OS, timezone, locale, profile.
7. Kiểm dependency locks, changing modules, image digest.
8. Kiểm container mapping/port, DB schema, broker topics, fixtures.
9. Kiểm cache trust/branch scope/restore keys và double cache ownership.
10. Kiểm report XML/HTML có xuất phát từ run hiện tại không.
11. Không chữa flake bằng cách xóa tất cả cache rồi bỏ nguyên nhân shared state.
12. Giữ environment-dependent integration gate always-run khi cần bằng chứng hiện tại.

~~~bash
./gradlew test integrationTest --build-cache --info
./gradlew test integrationTest --rerun-tasks --info
~~~

Hai lệnh dùng cho A/B diagnosis; lệnh hai buộc tasks execute. Nếu chỉ fail khi rerun, có thể là **hidden inputs, test nondeterminism, shared state hoặc caching configuration sai**. Cần sửa nguyên nhân, không chỉ luôn force clean nếu vấn đề ảnh hưởng production.

### Khi nào chỉ rerun một task?

Gradle có task-specific rerun options trong các phiên bản phù hợp, và CLI **--rerun-tasks** cho toàn requested graph. Để cân bằng cost, project mẫu biến integrationTest thành task always-execute; compileJava và unit tests vẫn có thể reuse. Khi release audit cần chứng minh toàn suite chạy, dùng --rerun-tasks trong job riêng, không phá toàn bộ developer incremental workflow.

## 17. Build cache security và untrusted pull requests

**Cache poisoning** xảy ra khi untrusted actor có thể lưu nội dung mà privileged workflow sau đó khôi phục và tin. Rủi ro tăng nếu cache chứa compiled plugins/scripts, execution artifacts hoặc dữ liệu chạy trước validation.

Giảm rủi ro:
- Low-trust triggers thường chỉ được **read** trusted branch cache.
- Trusted push workflows quản lý writes, không cấp cache write cho PR từ fork một cách tùy tiện.
- Không restore low-trust cache trong deployment/signing environment có secrets nếu chưa có trust controls.
- Không lưu raw secrets/credentials trong cache.
- Ghim/review action SHA khi cần, validate Wrapper và dependencies.
- Dùng principle of least privilege cho CI token.
- Kiểm cache scoping theo repository/branch/tag và service provider hiện hành.
- Audit exceptions khi ai đó phải bật write access cho workflow trigger không đáng tin.

**Giảm thời gian CI không đáng đánh đổi supply-chain trust**. Một lần build lâu hơn thường ít rủi ro hơn tái sử dụng state có khả năng bị can thiệp.

## 18. Ma trận quyết định cache

| Loại task | Cache? | Lý do |
| --- | --- | --- |
| Download fixed dependencies | Có | Artifacts tái sử dụng, verify/lock |
| Gradle Wrapper distribution | Có | Same distribution version |
| Java compilation | Có | Inputs/implementation được theo dõi |
| JUnit pure business logic | Có thể | Deterministic, không hidden inputs |
| @WebMvcTest với mocks | Có thể | Không external network, review configuration |
| @SpringBootTest(RANDOM_PORT) acceptance | Thường không cache task results | Current HTTP server/process |
| Testcontainers DB migration | Thường không cache task results | Runtime DB/schema |
| Live OAuth/API contract | Không cache khi cần current result | External permissions/availability |
| Docker image pull layers | Có thể | Cache blobs, nhưng container vẫn start |
| Docker BuildKit layers | Có thể | Reuse build work |
| Mutable DB volumes/fixtures | Không mặc định | Shared state và flakiness |
| JUnit HTML/XML reports | Upload artifact | Evidence/review, không generic cache |

Đây là chính sách gợi ý, không phải luật Gradle cứng. Một integration test hermetic có thể cache-safe, trong khi một test được đặt tên unit nhưng đọc internet là không cache-safe.

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả | Thay bằng |
| --- | --- | --- |
| Coi dependency cache là test result cache | Hiểu sai evidence | Phân biệt layer |
| Coi Configuration Cache là Build Cache | Lẫn configuration và execution | Phân biệt task graph vs outputs |
| BUILD SUCCESSFUL nghĩa tất cả JUnit vừa chạy | Có thể FROM-CACHE | Kiểm task outcomes |
| --no-build-cache chắc chắn chạy test | UP-TO-DATE vẫn skip | --rerun-tasks/always-execute |
| --refresh-dependencies là rerun test | Không force execution | --rerun-tasks |
| Cache build/test-results bằng branch key | Report xanh cũ | Gradle task model + upload artifact |
| Cache live DB tests | Hidden DB state | integrationTest always-run |
| Disable cache mọi compilation | CI chậm | Chỉ tắt cache risk tasks |
| Cache Docker image tag như immutable | Digest có thể đổi | Pin digest khi cần |
| Cache Docker volume DB giữa runs | Dirty fixtures | Fresh container/schema |
| BuildKit cache mà quên load image | docker run không thấy image | load/push rõ |
| Testcontainers image có nghĩa DB ready | Chưa start/query | Wait + actual SQL |
| Hard-code host port 5432 | Parallel collision | Dynamic mapped ports |
| setup-gradle và setup-java cache Gradle cùng lúc | Double cache state | Một owner |
| Store secrets trong ~/.gradle cache | Data exposure | Secret store/Provider API |
| Untrusted PR write privileged cache | Poisoning | Read-only trust boundary |
| Chỉ đo CI duration | Che missing test execution | Đo outcomes và acceptance evidence |
| Dùng timestamp cache key để chữa flake | Không sửa nondeterminism | Mock clock/declare inputs |

## 20. Câu hỏi luyện tập

**1.** Gradle dependency cache có phải test outputs không? **Không**. Nó lưu dependency artifacts và resolution metadata.

**2.** Configuration Cache lưu gì? **Configured task graph/state**, không phải JUnit result.

**3.** Build Cache có thể reuse Test outputs? **Có**, nếu Test task cacheable và keys match.

**4.** UP-TO-DATE nghĩa test vừa chạy? **Không**, task actions được skip.

**5.** FROM-CACHE nghĩa JUnit vừa thực thi? **Không**, outputs được restore.

**6.** --no-build-cache có force rerun không? **Không**, local up-to-date vẫn hoạt động.

**7.** --rerun-tasks có làm gì? **Bypass up-to-date/build cache reuse để thực thi tasks**.

**8.** --refresh-dependencies có force JUnit chạy? **Không**.

**9.** Một report 50 passed FROM-CACHE chứng minh điều gì? Gradle reuse outputs theo declared inputs; **không chứng minh tests vừa chạy ở job này**.

**10.** Dependency locking có thay việc chạy tests? **Không**, nó ổn định resolved versions.

**11.** Docker image có sẵn chứng minh PostgreSQL healthy? **Không**, vẫn cần container start và query.

**12.** Docker image tag postgres:16 có immutable không? **Không**, tag có thể đổi digest.

**13.** BuildKit cache có tự load final image vào daemon không? **Không mặc định**, cần output/load/push.

**14.** Testcontainers nên hard-code host port 5432? **Không**, dùng getMappedPort/getJdbcUrl/@ServiceConnection.

**15.** Why not cache DB volumes? Mutable state làm tests phụ thuộc lần chạy trước.

**16.** Vì sao unit tests dùng Locale.ROOT? Tránh host default locale làm hidden input.

**17.** Vì sao integrationTest luôn execute? Để kiểm **HTTP server thật hiện tại**, không lấy result cũ.

**18.** @WebMvcTest có mở socket không? **Không**, dùng MockMvc.

**19.** @SpringBootTest(RANDOM_PORT) có mở socket không? **Có**, port do OS cấp.

**20.** setup-gradle có nên chồng setup-java cache: gradle? **Không nên**, một owner cho Gradle User Home.

**21.** GitHub Actions cache có thể chứa credentials? **Không nên**, cache không phải secret store.

**22.** Low-trust PR có nên write privileged cache? **Không**, giảm rủi ro cache poisoning.

**23.** Report XML của job nên lưu ở đâu? **Upload artifacts từ current job**.

**24.** Configuration Cache có thể chứa sensitive task state? **Có**, cần kiểm encryption/trust và Provider API.

**25.** Nguyên tắc cốt lõi? **Cache dữ liệu tái tạo được với tracked inputs; không tái sử dụng kết quả xanh cũ để thay evidence của live integration environment**.

### Checklist QA

- Đã phân biệt dependency cache, configuration cache, build cache, image/layer cache và report artifacts?
- Có ghim Gradle Wrapper/versions, review dependencies và image digests?
- Có biết task Test có thể dùng Build Cache?
- Có nhìn UP-TO-DATE/FROM-CACHE/NO-SOURCE thay vì chỉ BUILD SUCCESSFUL?
- Có tách deterministic unit tests khỏi environment-dependent integration tests?
- integrationTest có always-run và doNotCacheIf đúng?
- Task outputs/inputs được Gradle model đúng, không hidden env/network/files?
- CI có thể tự chạy khi cache miss/eviction?
- Không double-cache Gradle User Home?
- Reports được upload như artifacts, không giả làm test evidence hiện tại?
- Docker layers cached không bị nhầm với container/data ready?
- Testcontainers được start/health/query và không hard-code mapped ports?
- Không cache DB mutable volumes giữa các CI jobs không có isolation?
- Có phân biệt Spring TestContext cache và Gradle task output cache?
- Có policy secrets, untrusted PR cache permissions và supply-chain verification?
- Có kiểm actual JDK/OS/profile acceptance matrix khi cần?
- Không hứa có build/CI execution khi chưa chạy?

**Kết luận:** **Cache dependency và Docker image giúp giảm tải/download, nhưng reuse kết quả Test là một quyết định về độ tin cậy.** Spring Boot/Gradle CI nên cache dependencies/compilation và chỉ cho test task reuse outputs khi inputs thực sự đầy đủ, đồng thời **luôn thực thi những integration checks cần current evidence**. Bảo vệ cache khỏi untrusted writers, tránh lưu secrets và giữ test reports theo từng job sẽ giúp pipeline vừa nhanh vừa đáng tin.

## Nguồn chính thức

- Gradle — Dependency Caching: https://docs.gradle.org/current/userguide/dependency_caching.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle — CLI options và --rerun-tasks: https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — GitHub Actions: https://docs.gradle.org/current/userguide/github-actions.html
- Gradle Actions — setup-gradle caching: https://github.com/gradle/actions/blob/main/docs/setup-gradle.md
- GitHub Actions — Dependency caching/security: https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
- Spring Boot 3.4 — Testing Spring Boot Apps: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — Testcontainers/@ServiceConnection: https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html
- Testcontainers — Networking: https://java.testcontainers.org/features/networking/
- Docker — Build caching: https://docs.docker.com/build/cache/
- Docker — GitHub Actions cache backend: https://docs.docker.com/build/cache/backends/gha/
