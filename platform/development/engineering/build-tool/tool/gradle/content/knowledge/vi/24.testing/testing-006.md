# Dependency giữa kiểm thử tích hợp và hạ tầng cần khởi động trong Gradle

## 1. Mục tiêu bài học

**Kiểm thử tích hợp (integration test)** thường cần một hệ thống thật hoặc gần thật bên ngoài mã đang test: PostgreSQL, Redis, message broker, HTTP API giả lập, object storage, Docker Compose stack hoặc service được cấp sẵn trên CI. Nếu test được chạy trước khi hạ tầng sẵn sàng, kết quả thường là `Connection refused`, timeout, lỗi xác thực hoặc test “lúc xanh lúc đỏ” tùy tốc độ máy.

Trong Gradle có **hai loại dependency cần phân biệt**:

1. **Task dependency**: việc nào cần hoàn thành trước khi một task khác được thực thi? Ví dụ `integrationTest` phải đợi `startDatabase` hoàn thành thành công.
2. **Dependency về trạng thái môi trường**: database có **thực sự healthy, reachable và đã có schema/data phù hợp** không? Một task khởi động container trả về thành công chưa nhất thiết chứng minh hệ thống đã sẵn sàng phục vụ request.

Để giải quyết đúng, cần mô hình hóa chuỗi:

~~~text
Biên dịch test + chuẩn bị hạ tầng
                   |
                   v
            Hạ tầng READY
                   |
                   v
             integrationTest
                   |
              PASS / FAIL
                   |
                   v
           Dọn tài nguyên test
~~~

Bài học giúp bạn:

- Tạo nhóm kiểm thử tích hợp riêng bằng **JVM Test Suite** hoặc `sourceSets` + `Test`.
- Dùng đúng `dependsOn`, `mustRunAfter`, `shouldRunAfter`, `finalizedBy`; không nhầm **thứ tự** với **dependency bắt buộc**.
- Hiểu readiness, health check, timeout, migrations/seed data, cleanup và lỗi khi startup một phần.
- Chạy một ví dụ **Java 17 + Gradle Kotlin DSL + JUnit Jupiter** kiểm thử qua HTTP thật bằng fixture cục bộ trong test JVM.
- Mở rộng thành workflow **Docker Compose + PostgreSQL**, có `composeUp`, `integrationTest` và `composeDown`, đồng thời hiểu các giới hạn của việc khởi động hạ tầng từ Gradle task.
- So sánh Docker Compose orchestration với **Testcontainers**, **shared build service** và service do CI cấp sẵn.
- Tránh tình trạng up-to-date/build cache làm test bỏ qua kiểm tra môi trường đang thay đổi; tránh xung đột port khi CI chạy song song.
- Kiểm tra task graph/log, khắc phục startup failure, giữ test deterministic và bảo vệ thông tin nhạy cảm.

Các ví dụ dùng Gradle Wrapper. Linux/macOS chạy `./gradlew`, Windows PowerShell chạy `.\gradlew.bat`. Những phần cần Docker/network được đánh dấu rõ; không coi ví dụ PostgreSQL là runnable trên máy chưa có Docker.

## 2. Phân biệt dependency graph của tasks với dependency graph của libraries

Khi bạn viết:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}
~~~

Gradle giải quyết **library dependency** để compiler/test runtime thấy các class của JUnit.

Khi bạn viết:

~~~kotlin
tasks.named("integrationTest") {
    dependsOn("startDatabase")
}
~~~

Gradle lập **task execution graph**: khi `integrationTest` được yêu cầu, `startDatabase` cũng phải được scheduled và thực hiện trước theo quan hệ bắt buộc.

Hai thứ khác nhau:

| Việc cần làm | Gradle API | Giải quyết vấn đề gì? |
| --- | --- | --- |
| Test import JUnit/JDBC driver | `testImplementation`, `integrationTestImplementation` | Classpath compile/runtime của test. |
| Test cần hạ tầng khởi động trước | `dependsOn(startInfra)` | Chạy prerequisite task trước. |
| Test không được chạy đồng thời với một task khác | `mustRunAfter(otherTask)` | Thứ tự nếu hai task đều đã được scheduled. |
| Muốn ưu tiên unit test trước integration test | `shouldRunAfter(test)` | Thứ tự mềm, hỗ trợ scheduler linh hoạt. |
| Phải dọn hạ tầng khi test hoàn tất hoặc test fail | `finalizedBy(stopInfra)` | Đưa finalizer vào graph. |
| Cần service có health check | Compose `--wait`, polling/ready probe, Testcontainers wait strategy | **Readiness thực tế**, không chỉ thứ tự task. |
| Chặn concurrent tasks dùng chung DB/port | Gradle Build Service + `maxParallelUsages` hoặc resource lock thích hợp | Kiểm soát tranh chấp tài nguyên. |

**Quan trọng:** `dependsOn` không có nghĩa “chờ database sẵn sàng ở tầng ứng dụng”. Nó chỉ có nghĩa **task khởi động đã hoàn tất theo cách Gradle nhìn thấy**. Nếu `startDatabase` chỉ gọi `docker compose up -d`, container có thể đang khởi tạo bên trong ngay cả khi command đã trả exit code 0.

## 3. Bốn quan hệ task thường bị dùng nhầm

Giả sử đã đăng ký:

~~~kotlin
val startInfra by tasks.registering {
    doLast {
        println("INFRA_START_TASK_DONE")
    }
}

val stopInfra by tasks.registering {
    doLast {
        println("INFRA_STOP_TASK_DONE")
    }
}

val integrationTest by tasks.registering {
    dependsOn(startInfra)
    finalizedBy(stopInfra)
    doLast {
        println("INTEGRATION_TASK_EXECUTED")
    }
}
~~~

Đây là **mẫu Kotlin DSL mô phỏng thứ tự**, không thực sự khởi động server/database. Nếu project có các task thật tên `integrationTest` do JVM Test Suite tạo, **không** đăng ký thêm task `integrationTest` trùng tên; phần trên là demo quan hệ task trong một project khác.

Chạy:

~~~bash
./gradlew -q integrationTest
~~~

Trong một project chỉ có các task trên và không có can thiệp khác, stdout:

~~~text
INFRA_START_TASK_DONE
INTEGRATION_TASK_EXECUTED
INFRA_STOP_TASK_DONE
~~~

### 3.1. `dependsOn`: prerequisite bắt buộc

~~~kotlin
tasks.named("integrationTest") {
    dependsOn("startInfra")
}
~~~

Gradle sẽ đưa `startInfra` vào graph khi `integrationTest` được scheduled. Nếu startup task thất bại, Gradle thường không thực thi phần test phụ thuộc nó. **Đó là chủ đích**: test không nên chạy khi hạ tầng chưa sẵn sàng.

**Không nhầm** với:

~~~kotlin
tasks.named("integrationTest") {
    mustRunAfter("startInfra")
}
~~~

`mustRunAfter` **không** khiến Gradle tự schedule `startInfra`. Nếu chỉ gọi `./gradlew integrationTest`, `startInfra` có thể không chạy. Nó chỉ áp một quy tắc thứ tự **nếu cả hai task đều đã ở graph**.

### 3.2. `shouldRunAfter`: thứ tự mềm

~~~kotlin
tasks.named("integrationTest") {
    shouldRunAfter("test")
}
~~~

Điều này hữu ích khi cả unit tests và integration tests đều được chạy trong `check`: Gradle có thể ưu tiên unit tests trước để fail nhanh. Nhưng nếu chỉ gọi `./gradlew integrationTest`, `test` không tự chạy.

`shouldRunAfter` có thể không được đáp ứng trong một số tình huống scheduler song song hoặc xung đột ordering rules. Không dùng nó để đảm bảo database bắt buộc được khởi động trước.

### 3.3. `mustRunAfter`: thứ tự cứng nhưng không kéo task vào

~~~kotlin
tasks.named("integrationTest") {
    mustRunAfter("prepareSchema")
}
~~~

Nếu `prepareSchema` và `integrationTest` đều đã được schedule, Gradle sẽ đặt `prepareSchema` trước; **nếu không** thì nó không bắt Gradle thêm `prepareSchema` vào graph. Khi chuẩn bị schema là điều kiện tiên quyết tuyệt đối, dùng `dependsOn(prepareSchema)`.

### 3.4. `finalizedBy`: cleanup

~~~kotlin
tasks.named("integrationTest") {
    finalizedBy("stopInfra")
}
~~~

Gradle đưa `stopInfra` vào graph như một **finalizer** của `integrationTest`. Tài liệu Gradle nêu finalizer chạy cả khi task được finalize **fail** hoặc có kết quả `UP-TO-DATE`; điều này rất phù hợp dọn container sau integration test.

Tuy nhiên **không được hứa tuyệt đối**: nếu Gradle process bị kill, daemon crash, máy mất điện, hoặc prerequisite startup fail khiến `integrationTest` không thực sự được thực thi, finalizer gắn vào test có thể không giải quyết được mọi tài nguyên còn sót. Dự án nghiêm túc cần **cleanup ở CI `finally`/`after_script`**, timeout và/hoặc cơ chế tài nguyên có TTL.

### 3.5. Bảng ghi nhớ

| API | Tự đưa task khác vào graph? | Đảm bảo thứ tự? | Dùng để start/stop infra? |
| --- | --- | --- | --- |
| `dependsOn` | **Có** | Prerequisite trước dependent. | **Có**, cho bước startup/ready. |
| `mustRunAfter` | **Không** | Có, khi cả hai scheduled. | Không đủ để buộc start infra. |
| `shouldRunAfter` | **Không** | Mềm, có thể nhường để scheduler linh hoạt. | Không đủ để buộc start infra. |
| `finalizedBy` | **Có** | Finalizer sau task được finalize. | **Có**, cleanup sau test; cần fallback. |

**Quy tắc thiết kế:** nếu A **không thể chạy đúng khi thiếu B**, hãy bắt đầu từ `A.dependsOn(B)`, không thay bằng ordering-only API.

## 4. “Khởi động xong” và “READY” là hai sự kiện khác nhau

Một quy trình Docker thường có các giai đoạn:

~~~text
Docker command trả thành công
    -> container process chạy
    -> database mở TCP port
    -> authentication/configuration hoạt động
    -> schema migrations hoàn tất
    -> seed/test data sẵn sàng
    -> integration test có thể chạy
~~~

Đừng biến một `Thread.sleep(5000)` hoặc `sleep 10` thành chứng cứ readiness: CI chậm có thể cần 30 giây, máy dev nhanh chỉ cần 1 giây. Delay cố định làm test vừa chậm vừa flaky.

Một **readiness check tốt** cần:

1. Test đúng endpoint/port/protocol mà consumer sẽ sử dụng.
2. Thực hiện nhiều lần nếu chưa sẵn sàng, với **timeout hữu hạn**.
3. Phân biệt lỗi “chưa ready” có thể retry với lỗi “configuration/credentials sai” cần fail sớm.
4. Nếu database cần schema, probe schema/SQL query sau migrations, không chỉ chờ TCP port mở.
5. Nếu nhiều services, mỗi service có readiness contract riêng và một điểm quyết định “toàn bộ stack ready”.
6. Ghi log đủ để biết đã chờ bao lâu và service nào không đạt điều kiện.
7. Fail startup task nếu hết deadline; khi đó Gradle không nên chạy test.

**Readiness** khác **liveness**: một server có thể đang sống nhưng chưa nhận yêu cầu nghiệp vụ. Docker `healthcheck` có thể biểu diễn readiness gần đúng nếu câu lệnh probe được thiết kế đúng; một query SQL thực trong test còn có thể chứng minh kết nối và schema.

## 5. Tách integration tests bằng JVM Test Suite (cách được Gradle hỗ trợ)

Gradle có **JVM Test Suite plugin** để mô hình hóa những nhóm test riêng theo mục đích. Khi dùng Java/Application plugin, các khả năng JVM test suite đã được áp dụng theo integration của Java plugin; bạn thường không cần áp lại `jvm-test-suite` riêng.

Ví dụ Kotlin DSL:

~~~kotlin
testing {
    suites {
        named<JvmTestSuite>("test") {
            useJUnitJupiter("5.11.4")
        }

        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter("5.11.4")
            dependencies {
                implementation(project())
            }

            targets {
                all {
                    testTask.configure {
                        shouldRunAfter(tasks.named("test"))
                    }
                }
            }
        }
    }
}

tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}
~~~

**Đây là mảnh cấu hình** cần project có Java plugin, repository JUnit và project source. Nó được đưa vào file đầy đủ ở mục 6.

Ý nghĩa:

- `testing.suites.register<JvmTestSuite>("integrationTest")` tạo source set và target test task riêng, thường lấy Java source từ `src/integrationTest/java`.
- `useJUnitJupiter("5.11.4")` chọn JUnit Jupiter và thêm những dependencies/framework configuration cần cho suite; khác `Test.useJUnitPlatform()` chỉ cấu hình engine execution.
- `implementation(project())` là điểm **rất quan trọng**: suite mới cần dependency đến production code của chính project, chứ không tự kế thừa hết như built-in `test` suite.
- `shouldRunAfter(tasks.named("test"))` chỉ đặt thứ tự khi unit test cũng được schedule.
- `check.dependsOn(...)` mới làm `./gradlew check` kéo integration test suite vào graph. Gradle không tự thêm mọi suite tùy chỉnh vào `check`.
- Task `integrationTest` được JVM Test Suite tạo tự động; **không** tạo thêm một task cùng tên bằng `tasks.register<Test>("integrationTest")`.

JVM Test Suite DSL vẫn được tài liệu Gradle ghi nhận là API có thể còn thay đổi theo phiên bản. Với dự án cần support Gradle cũ, có thể dùng `sourceSets` và `Test` task thủ công (mục 10). Đừng trộn cả hai cách đăng ký **cùng tên task/source set**.

## 6. Lab Java 17 chạy được: HTTP integration test không cần Docker

Mục này tạo một test **thực sự gửi HTTP request** đến một HTTP server chạy trong cùng test process. Server được tạo tại test method và dừng trong `finally`. Đây là mô hình **test-managed fixture**, hữu ích để học lifecycle, readiness và cleanup trước khi chuyển sang database/container ngoài process.

**Ranh giới cần nói rõ:** lab này **không khởi động PostgreSQL hay Docker từ một Gradle task**. Test tự tạo hạ tầng HTTP đơn giản bằng JDK; mục 8 mới chứng minh orchestration bằng `dependsOn(composeUp)` cho hạ tầng ngoài test JVM.

### 6.1. Cấu trúc

~~~text
integration-test-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── src/main/java/example/App.java
└── src/integrationTest/java/example/HealthIntegrationTest.java
~~~

Yêu cầu: **Gradle Wrapper hoạt động**, JDK 17 phù hợp hoặc có toolchain provisioning, Internet/Maven repository để resolve JUnit Jupiter lần đầu. Không cần Docker trong lab này.

### 6.2. `settings.gradle.kts`

~~~kotlin
rootProject.name = "integration-test-lab"
~~~

### 6.3. Toàn bộ `build.gradle.kts`

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("example.App")
}

testing {
    suites {
        named<JvmTestSuite>("test") {
            useJUnitJupiter("5.11.4")
        }

        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter("5.11.4")

            dependencies {
                // Cho source integrationTest thấy source/main của project.
                implementation(project())
            }

            targets {
                all {
                    testTask.configure {
                        shouldRunAfter(tasks.named("test"))

                        // Chỉ phục vụ lab: nhìn thấy stdout do test in ra.
                        testLogging {
                            showStandardStreams = true
                            events("passed", "failed")
                        }
                    }
                }
            }
        }
    }
}

tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}
~~~

**Đọc kỹ các quan hệ:** `check` phụ thuộc suite `integrationTest`; suite cần production code qua `implementation(project())`; `integrationTest` chỉ có thứ tự mềm sau `test`, chứ **không tự chạy `test`** nếu bạn chỉ gọi riêng `integrationTest`.

### 6.4. `src/main/java/example/App.java`

~~~java
package example;

public final class App {
    private App() {
    }

    public static String status() {
        return "OK";
    }

    public static void main(String[] args) {
        System.out.println("APP_STATUS=" + status());
    }
}
~~~

Lệnh:

~~~bash
./gradlew -q run
~~~

Stdout chính xác từ `App.main`:

~~~text
APP_STATUS=OK
~~~

### 6.5. `src/integrationTest/java/example/HealthIntegrationTest.java`

~~~java
package example;

import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HealthIntegrationTest {
    @Test
    void callsRealHttpEndpoint() throws Exception {
        // Port 0: hệ điều hành chọn port trống để giảm va chạm.
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0
        );

        server.createContext("/health", exchange -> {
            byte[] responseBytes =
                ("READY:" + App.status()).getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8"
            );
            exchange.sendResponseHeaders(200, responseBytes.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(responseBytes);
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();
            URI uri = URI.create("http://127.0.0.1:" + port + "/health");

            HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

            HttpResponse<String> response =
                HttpClient.newHttpClient().send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8
                    )
                );

            assertEquals(200, response.statusCode());
            assertEquals("READY:OK", response.body());

            System.out.println(
                "HTTP_STATUS=" + response.statusCode()
            );
            System.out.println(
                "HTTP_BODY=" + response.body()
            );
        } finally {
            server.stop(0);
        }
    }
}
~~~

**Tại sao ví dụ này đáng học?**

- `HttpServer` là HTTP server được JDK cung cấp, không phải mock Java method thuần. Test thực sự tạo một socket, gửi HTTP request, đọc HTTP response.
- `new InetSocketAddress("127.0.0.1", 0)` để OS tự cấp cổng rảnh, tránh hard-code 8080 gây collision.
- `server.start()` xảy ra trước HTTP request trong cùng test method; nếu setup thất bại, test fail.
- `try/finally` dừng server khi assertion hoặc HTTP call fail. Nếu cả JVM bị kill, vẫn có thể cần OS cleanup, nhưng server process gắn cùng test JVM nên không có container ngoài còn sống.
- Test gọi `App.status()` từ production code, chứng minh `implementation(project())` có ý nghĩa.
- `assertEquals` kiểm tra cả HTTP status và body, không chỉ kiểm tra port mở.
- JDK `jdk.httpserver` cung cấp `HttpServer` trên JDK 17; nếu một toolchain/module environment tùy biến không resolve module này, kiểm tra JDK thật và module path.

### 6.6. Lệnh và output kiểm chứng

~~~bash
./gradlew --version
./gradlew test
./gradlew integrationTest --info
./gradlew check
~~~

Các dòng **do test method in ra khi test pass**:

~~~text
HTTP_STATUS=200
HTTP_BODY=READY:OK
~~~

Vì build script bật `showStandardStreams = true` cho target integration test, hai dòng có thể thấy trong phần Gradle test logging theo format của phiên bản Gradle. Không coi cả đoạn `--info` là stdout cố định. Với `./gradlew -q integrationTest`, behavior in log có thể còn phụ thuộc logging configuration; assert thành công mới là tiêu chí pass, không phải có đủ hai dòng terminal.

Báo cáo HTML mặc định thường nằm dưới `build/reports/tests/integrationTest/`; kết quả test XML thường ở `build/test-results/integrationTest/`. Kiểm tra file thực tế nếu Gradle version/plugin thay đổi layout.

### 6.7. Không cần Docker không có nghĩa mọi bài integration test đều đơn giản

HTTP fixture trong test là đúng khi muốn kiểm chứng client/server protocol/serialization mà không cần database thật. Nếu sản phẩm phụ thuộc PostgreSQL SQL dialect, transactions, migrations hay broker semantics, dùng fixture JDK **không thay thế** được test với hạ tầng thật. Mục 8 chuyển sang PostgreSQL để mô hình hóa startup và readiness ở mức task.

## 7. `dependsOn` cho điều kiện phải chuẩn bị trước: demo task không cần Docker

Một bài toán khác là cần chuẩn bị **dữ liệu/config đầu vào** trước integration test. Nếu bước chuẩn bị có output file, Gradle có thể mô hình hóa nó thành task có declared output và nối dependencies qua provider.

Ví dụ **mảnh Kotlin DSL**, đặt trong project lab mục 6:

~~~kotlin
val prepareIntegrationData by tasks.registering {
    val generatedFile =
        layout.buildDirectory.file("integration-fixture/ready.txt")

    outputs.file(generatedFile)

    doLast {
        val file = generatedFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText("fixture-ready", Charsets.UTF_8)
    }
}

tasks.named("integrationTest") {
    dependsOn(prepareIntegrationData)
}
~~~

Đây là **minh họa task prerequisite tạo file**, **không** khởi động HTTP server hay DB; test trong mục 6 không đọc file này, vì mục tiêu là nhìn thấy task graph. Lệnh `./gradlew integrationTest` sẽ schedule `prepareIntegrationData` trước test.

Điểm quan trọng:

- Nếu test thực sự **đọc** file, phải truyền file path đúng cách và khai báo input để Gradle biết file đó ảnh hưởng kết quả.
- Đối với output file, Gradle có thể sử dụng up-to-date checks; việc file vẫn đúng không đòi tạo lại mọi lần.
- Đối với **service ngoài process**, “task chạy xong” chưa đủ: service state không nhất thiết được mô tả như một output file cố định, cần readiness và lifecycle.

### Không lấy `mustRunAfter` thay thế prerequisite

Mẫu sau là **sai** nếu test bắt buộc có fixture:

~~~kotlin
tasks.named("integrationTest") {
    mustRunAfter(prepareIntegrationData)
}
~~~

Gọi riêng `integrationTest` có thể không schedule `prepareIntegrationData`. Khi fixture là điều kiện bắt buộc, dùng `dependsOn`. Còn `mustRunAfter` hữu ích khi hai task vốn được schedule và phải thực thi theo thứ tự mà không có dependency dữ liệu thực.

## 8. Mở rộng thực tế: PostgreSQL qua Docker Compose

Đây là **phương án thay thế** cho fixture HTTP ở mục 6 khi integration tests cần PostgreSQL. Yêu cầu Docker Engine và **Docker Compose V2** có thể chạy bằng `docker compose`, kết nối mạng để lấy image nếu chưa có, và quyền mở port cục bộ.

Mục này nêu đầy đủ từng file/configuration cần thêm. **Không áp dụng Docker Compose workflow lên test HTTP rồi kết luận đã kiểm thử database**; bạn phải thêm cả JDBC test ở mục 8.4.

### 8.1. Cấu trúc bổ sung

~~~text
integration-test-lab/
├── infra/
│   └── compose.yaml
├── src/integrationTest/java/example/
│   ├── HealthIntegrationTest.java
│   └── DatabaseIntegrationTest.java
└── build.gradle.kts
~~~

Ví dụ dùng port **15432** cố định để dễ thao tác trên một máy. **Không dùng nguyên cấu hình port này cho nhiều CI jobs song song trên cùng host**; mục 12 trình bày cách cô lập.

### 8.2. `infra/compose.yaml`

~~~yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: demo
      POSTGRES_USER: demo
      POSTGRES_PASSWORD: demo_local_only
    ports:
      - "127.0.0.1:15432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U demo -d demo"]
      interval: 2s
      timeout: 3s
      retries: 20
~~~

**Lưu ý:** `demo_local_only` là credential minh họa cho DB không chứa dữ liệu thật trên loopback, **không** dùng cho production. Nếu cần chính sách credential của CI, lấy từ secrets/CI variables, không commit mật khẩu thật vào Compose file hoặc Gradle logs.

`healthcheck` dùng `pg_isready` bên trong container để kiểm tra PostgreSQL nhận kết nối. Điều này chưa tự bảo đảm schema migrations đã chạy. Nếu test yêu cầu bảng/schema, cần chạy migrations trong một bước **sau DB health**, trước khi test queries; hoặc test tự quản lý schema hợp lệ.

### 8.3. Đăng ký start/stop tasks và nối với `integrationTest`

**Thêm mảnh này vào cuối `build.gradle.kts` của mục 6** (không đăng ký lại `integrationTest` suite):

~~~kotlin
val composeProjectName =
    providers.gradleProperty("itComposeProject")
        .orElse("gradle-it-local")

val composeUp by tasks.registering(Exec::class) {
    group = "verification"
    description = "Starts disposable PostgreSQL for integration tests"

    workingDir = layout.projectDirectory.dir("infra").asFile
    commandLine(
        "docker", "compose",
        "-p", composeProjectName.get(),
        "-f", "compose.yaml",
        "up", "-d", "--wait", "--wait-timeout", "90"
    )
}

val composeDown by tasks.registering(Exec::class) {
    group = "verification"
    description = "Stops PostgreSQL after integration tests"

    workingDir = layout.projectDirectory.dir("infra").asFile
    commandLine(
        "docker", "compose",
        "-p", composeProjectName.get(),
        "-f", "compose.yaml",
        "down", "-v", "--remove-orphans"
    )
}

tasks.named<Test>("integrationTest") {
    dependsOn(composeUp)
    finalizedBy(composeDown)

    // Server/database bên ngoài không được fingerprint đầy đủ như file.
    // Tránh coi kết quả cũ là hợp lệ cho DB mới của mỗi lần chạy.
    outputs.upToDateWhen { false }

    // Chỉ dành cho DB demo trên loopback.
    systemProperty(
        "it.jdbcUrl",
        "jdbc:postgresql://127.0.0.1:15432/demo"
    )
    systemProperty("it.dbUser", "demo")
    systemProperty("it.dbPassword", "demo_local_only")
}
~~~

**Giải thích luồng:**

1. `integrationTest.dependsOn(composeUp)` yêu cầu Gradle chạy Compose start trước.
2. `docker compose up -d --wait --wait-timeout 90` trả về khi services đạt trạng thái **running/healthy** theo Compose; `--wait` yêu cầu Compose V2 có hỗ trợ tùy chọn này. Service có healthcheck sẽ được đánh giá qua health status.
3. `integrationTest.finalizedBy(composeDown)` đưa cleanup vào graph ngay cả khi test task fail. Đây là điểm rất quan trọng để không để PostgreSQL chạy mãi sau một assertion failure.
4. `outputs.upToDateWhen { false }` khiến integration test thực thi mỗi lần được yêu cầu, vì server state/DB data ngoài filesystem không được Gradle tự fingerprint đầy đủ. Nó **đánh đổi thời gian build để tránh test false-positive do cache/up-to-date**.
5. `systemProperty` truyền JDBC URL/user/password vào **test JVM**. Test có thể đọc bằng `System.getProperty(...)`.
6. `composeProjectName` nhận `-PitComposeProject=...` để giảm collision về Compose project resources, nhưng **port 15432 vẫn cố định**: CI nhiều jobs phải có isolation về host/port.
7. `down -v` xóa **volume data của Compose project này**; chỉ dùng cho DB hoàn toàn disposable, **không** chỉ nhầm vào database thật.

**Các giới hạn của finalizer:** nếu `composeUp` fail một phần **trước khi `integrationTest` thực sự chạy**, hoặc quá trình Gradle/agent bị kill, một `finalizedBy(composeDown)` gắn với test **không bảo đảm** cleanup mọi tình huống. Hãy tạo CI `finally`/`after_script` gọi `docker compose down` với **cùng project name**, hoặc có cơ chế TTL/manual cleanup. Không gắn `composeUp.finalizedBy(composeDown)` một cách máy móc mà chưa hiểu Gradle task graph, vì có thể tạo thứ tự teardown không như mong đợi.

### 8.4. Thêm JDBC driver vào đúng integration-test suite

Trong **block `register<JvmTestSuite>("integrationTest")` có sẵn** ở `build.gradle.kts`, **bổ sung vào block `dependencies`**, không thay toàn bộ:

~~~kotlin
dependencies {
    implementation(project())
    implementation("org.postgresql:postgresql:42.7.4")
}
~~~

Đây là **nội dung block `dependencies` bên trong `integrationTest` suite**, không phải top-level `dependencies` của main application. Driver chỉ cần cho integration tests, không tự là production dependency nếu app chưa sử dụng PostgreSQL driver.

Version `42.7.4` chỉ là mốc ví dụ. Khi làm production, xem compatibility/security updates của JDBC driver và Gradle/JDK.

### 8.5. `src/integrationTest/java/example/DatabaseIntegrationTest.java`

~~~java
package example;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DatabaseIntegrationTest {
    @Test
    void canExecuteSqlAgainstReadyDatabase() throws Exception {
        String url = System.getProperty("it.jdbcUrl");
        String user = System.getProperty("it.dbUser");
        String password = System.getProperty("it.dbPassword");

        try (
            Connection connection =
                DriverManager.getConnection(url, user, password);
            Statement statement = connection.createStatement();
            ResultSet rows = statement.executeQuery("SELECT 1")
        ) {
            assertTrue(rows.next());
            assertEquals(1, rows.getInt(1));
            System.out.println("DB_QUERY_RESULT=1");
        }
    }
}
~~~

Test thực sự mở JDBC connection và chạy SQL trên PostgreSQL. Nếu Compose readiness báo healthy nhưng database không reachable từ test process do network/port mapping sai, nó **fail**; đó là bằng chứng hữu ích thay vì test pass giả.

Với cấu hình Compose đúng trên một máy Docker hoạt động, output do test in:

~~~text
DB_QUERY_RESULT=1
~~~

Đây là stdout của test, có thể được Gradle bọc theo test logging. Đừng khẳng định toàn bộ `docker compose` logs hay Gradle task output giống hệt ở mọi môi trường.

### 8.6. Chạy và dọn tài nguyên

~~~bash
./gradlew integrationTest --info
./gradlew check

# Khi cần dọn thủ công sau bị hủy/lỗi startup:
./gradlew composeDown
~~~

Nếu container bị dừng và Java test process đang chờ, test sẽ fail. Khi kiểm thử một build có nhiều modules cùng cần DB, đừng để mỗi module tự độc lập chạy `composeUp`/`composeDown` với cùng Compose project/port mà không có kế hoạch lifecycle: một test có thể teardown DB khi test khác còn dùng.

**Dữ liệu test:** compose example chưa có migrations. `SELECT 1` không cần bảng, nên chạy được sau khi DB sẵn sàng. Nếu thay bằng repository/DAO test truy vấn bảng, phải thêm migrations/seed data trước; không kết luận healthcheck đã bảo đảm schema.

## 9. Healthcheck, timeout và migrations cần được mô hình hóa riêng

Với PostgreSQL trong ví dụ:

~~~text
composeUp
  -> PostgreSQL process running
  -> pg_isready reports ready
  -> (optional) migrateDb
  -> (optional) seedTestData
  -> integrationTest
  -> composeDown
~~~

Nếu migrations do một Gradle task chạy sau DB healthy, có thể khai báo:

~~~kotlin
val migrateDb by tasks.registering {
    dependsOn(composeUp)
    doLast {
        // Tích hợp migration tool thực, không dùng sleep giả readiness.
    }
}

tasks.named("integrationTest") {
    dependsOn(migrateDb)
}
~~~

**Đây là skeleton mô hình hóa dependencies**, không phải migration implementation có thể chạy: tác vụ `migrateDb` không thực hiện migration vì chưa có Flyway/Liquibase/tool/schemas trong ví dụ. Dự án thực phải thay body bằng migration tool có exit code rõ, timeout và database credentials an toàn; chỉ khi migration task thật trả success mới cho test chạy.

Đừng để migrations tự động apply ở task `test` của unit tests nếu unit tests không cần DB. Đừng dùng file `ready.txt` không liên quan trạng thái DB như bằng chứng môi trường healthy.

### Readiness timeout

Dù Compose có `--wait --wait-timeout 90`, mỗi test/network call cũng nên có timeout riêng. Không để một integration test treo vô hạn vì HTTP client, JDBC connect hoặc broker receive.

- **Startup timeout**: deadline hạ tầng đạt trạng thái ready.
- **Connection timeout**: deadline một client mở kết nối.
- **Request/query timeout**: deadline một tương tác nghiệp vụ.
- **Test timeout**: deadline toàn test hoặc test class.
- **CI job timeout**: fallback cuối cùng, đừng để thay thế readiness logic.

Nếu hết timeout, fail nhanh kèm nguyên nhân rõ: service, endpoint, hostname, retry count và log phù hợp. Retry **setup/readiness** có giới hạn có thể hợp lý; retry **assertion nghiệp vụ ngẫu nhiên** vô tội vạ thường che flaky test.

## 10. Cách truyền thống: `sourceSets` và `Test` task riêng

Trước JVM Test Suite DSL, Gradle thường tạo source set `integrationTest` bằng tay. Hướng này vẫn hữu ích khi project có plugin hoặc bản Gradle cũ chưa hỗ trợ tốt suite API. **Chọn một trong hai**, không đăng ký suite và task cùng tên từ hai cơ chế khác nhau.

Mẫu `build.gradle.kts` độc lập về **cấu hình test**, giả định có Java project source và JUnit dependencies:

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

val integrationTest by sourceSets.creating {
    java.srcDir("src/integrationTest/java")
    resources.srcDir("src/integrationTest/resources")

    // Cho integration test nhìn thấy production code.
    compileClasspath += sourceSets.main.get().output
    runtimeClasspath += sourceSets.main.get().output
}

configurations[
    integrationTest.implementationConfigurationName
].extendsFrom(configurations.testImplementation.get())

configurations[
    integrationTest.runtimeOnlyConfigurationName
].extendsFrom(configurations.testRuntimeOnly.get())

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

val integrationTestTask by tasks.registering(Test::class) {
    description = "Runs integration tests"
    group = "verification"
    testClassesDirs = integrationTest.output.classesDirs
    classpath = integrationTest.runtimeClasspath
    useJUnitPlatform()
    shouldRunAfter(tasks.named("test"))
}

tasks.named("check") {
    dependsOn(integrationTestTask)
}
~~~

Ở cách này, Gradle tạo `integrationTestImplementation`, `integrationTestRuntimeOnly` theo source set. Các configuration được cho kế thừa JUnit dependencies của built-in test, và classpath nhận production outputs. `integrationTestTask` là một `Test` task mới, khác `test` mặc định.

**Chú ý về compilation:** nếu production code cần dependencies từ `implementation` (không nằm trong `api`), cần kiểm tra `integrationTest.compileClasspath`/`runtimeClasspath` sau khi khai báo, thay vì tự cho rằng production output chứa mọi library. Đối với Java library project, thêm project dependency/extendsFrom thích hợp. Với JVM Test Suite DSL, `implementation(project())` là phương thức model hóa rõ ràng hơn.

### Gắn infra startup ở cách truyền thống

~~~kotlin
integrationTestTask.configure {
    dependsOn("composeUp")
    finalizedBy("composeDown")
}
~~~

Đây là mảnh bổ sung **chỉ khi đã đăng ký hai Compose tasks thật** như mục 8. Nếu chưa có task `composeUp`/`composeDown`, Gradle sẽ báo unknown task. `shouldRunAfter(test)` vẫn chỉ là thứ tự giữa các loại test, không thay thế `dependsOn(composeUp)`.

## 11. Testcontainers: test sở hữu hạ tầng thay vì Gradle task quản lý Compose

Một cách khác là để **Testcontainers** khởi động container trong lifecycle của test. Nó phù hợp với database/broker/cache cần môi trường disposable riêng cho từng lớp test hoặc test suite.

Khái niệm JUnit Jupiter:

~~~java
@Testcontainers
class DatabaseIT {
    @Container
    static PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("demo")
            .withUsername("demo")
            .withPassword("demo_local_only");

    @Test
    void queriesDatabase() throws Exception {
        try (Connection connection = DriverManager.getConnection(
            database.getJdbcUrl(),
            database.getUsername(),
            database.getPassword()
        )) {
            // Thực hiện SQL/assertions.
        }
    }
}
~~~

Đây là **mảnh Java minh họa**; để compile cần imports Testcontainers/JUnit/JDBC và các dependencies phù hợp trong integration-test scope. Cụ thể, cấu hình Testcontainers 2.x có module artifact IDs có thể khác bản 1.x, nên **dùng tọa độ module và version theo tài liệu chính thức đang áp dụng**. Không dán fragment này thành file Java độc lập rồi kỳ vọng chạy khi chưa có dependencies.

Trong JUnit extension của Testcontainers:
- `@Testcontainers` tích hợp lifecycle JUnit.
- `@Container` trên **static field** dùng container chia sẻ giữa các methods của một test class; instance field thường có lifecycle theo từng test method.
- Testcontainers tìm Docker daemon, start container, đợi readiness theo wait strategy của image và dọn container trong lifecycle phù hợp.
- Test nên đọc `getJdbcUrl()`/`getHost()`/`getMappedPort()`, tránh hard-code `localhost:5432` vì port thường được cấp động.
- JUnit 5 Testcontainers extension **không mặc định hỗ trợ mọi kiểu concurrent execution** của cùng test class; kiểm tra hạn chế version cụ thể trước khi bật parallel tests.

### Testcontainers có cần `dependsOn(composeUp)` không?

**Không**, nếu container do chính Testcontainers tạo và quản lý bên trong test. Test task `integrationTest` được Gradle schedule, còn Testcontainers khởi động và cleanup service khi test runtime thực thi. Bạn vẫn có thể có một **preflight task** kiểm tra Docker daemon/credential nếu cần fail sớm, nhưng đừng vừa start cùng database qua Compose vừa để Testcontainers tạo thêm một database không sử dụng, chỉ làm chậm và gây hiểu nhầm.

### Khi nào chọn Compose vs Testcontainers?

| Trường hợp | Compose do Gradle/CI start | Testcontainers do test quản lý |
| --- | --- | --- |
| Cần stack nhiều services cố định cho E2E | Phù hợp nếu team có Compose file rõ và healthchecks. | Có thể, nhưng orchestration phức tạp hơn trong test code. |
| Cần DB/broker disposable theo từng test class | Phức tạp nếu chia sẻ port/database. | Thường phù hợp hơn, có lifecycle và mapped ports. |
| Cần CI tự quản lý resources | Dễ tích hợp job setup/teardown. | CI cần Docker daemon, tests tự quản lý. |
| Cần chạy test trên máy không có Docker | Không chạy được. | Không chạy được nếu image cần Docker. |
| Muốn tránh class/test biết Docker API | Phù hợp; test chỉ đọc host/port/credentials. | Test phải biết container APIs hoặc dùng test infrastructure extension. |
| Muốn test không phụ thuộc port cố định | Cần cấu hình dynamic port discovery. | Có mapped ports và APIs truy xuất. |
| Chống startup/cleanup rơi rớt | Cần finalizer + CI fallback. | Lifecycle hỗ trợ nhưng vẫn cần xử lý kill/daemon failure. |

**Không có lựa chọn tuyệt đối**. Điều quan trọng là phải có **một owner rõ ràng** cho lifecycle của mỗi service: Gradle task, test framework hay CI orchestrator. Hai bên cùng quản lý một container/port dễ gây race và teardown bất ngờ.

## 12. Parallelism: một hạ tầng dùng chung cho nhiều tests có thể gây race

Ví dụ có hai modules `:api` và `:worker` cùng dùng PostgreSQL ở port 15432. Cả hai đăng ký `composeDown` cho cùng Compose project; `:api:integrationTest` xong có thể dừng DB ngay khi `:worker:integrationTest` còn đang chạy.

Những rủi ro:

1. **Port collision**: hai Compose projects cùng publish `127.0.0.1:15432`; project thứ hai fail bind.
2. **Shared data contamination**: tests dùng cùng schema/table, test A xóa dữ liệu của test B.
3. **Premature teardown**: finalizer của một task dừng hạ tầng của task khác.
4. **Race migrations**: hai jobs đồng thời thay schema.
5. **Parallel Gradle tasks**: `--parallel` chạy tasks của nhiều projects, không hiểu một DB ngoài Gradle là tài nguyên độc quyền nếu không khai báo.

### Các chiến lược có thể chọn

- Mỗi job có **database/container riêng**, Compose project name riêng và **host port riêng** hoặc dynamic mapping.
- Tách schema/database theo worker, seed data riêng và rollback transaction khi phù hợp.
- Dùng Testcontainers để container/port được quản lý theo test; đọc mapped endpoints từ API.
- Với một service dùng chung, tạo **một owner** cho startup/teardown tại build hoặc CI level, chỉ cleanup **sau khi tất cả consumers kết thúc**.
- Nếu nhiều Gradle tasks cùng tiêu thụ tài nguyên độc quyền, dùng **Shared Build Service** với `maxParallelUsages.set(1)` và mỗi task khai báo `usesService(...)` hoặc `@ServiceReference` để Gradle biết giới hạn concurrent access.
- Không dùng `mustRunAfter` để giả lập resource lock giữa hàng chục tasks; thứ tự thủ công khó bảo trì và không bảo đảm concurrency đúng khi graph thay đổi.

### Shared Build Service trong Gradle

Shared Build Services có thể giữ tài nguyên lâu hơn một task và đóng khi không còn được sử dụng. Một service implement `BuildService<BuildServiceParameters.None>` và `AutoCloseable`; Gradle quản lý lifecycle và gọi `close()` ở thời điểm service bị loại bỏ.

Mẫu đăng ký:

~~~kotlin
val sharedDbResource =
    gradle.sharedServices.registerIfAbsent(
        "integration-db-resource",
        MyDbBuildService::class.java
    ) {
        maxParallelUsages.set(1)
    }

tasks.named<Test>("integrationTest") {
    usesService(sharedDbResource)
}
~~~

**Đây là mảnh API minh họa**, không runnable nếu chưa định nghĩa class `MyDbBuildService` trong build logic. Để dùng production cần định nghĩa service implementation, thread safety, resource parameters và cách truyền endpoint vào test JVM mà không vi phạm Configuration Cache.

`maxParallelUsages` chỉ giới hạn **những tasks đã khai báo dùng service với Gradle**. Nếu một process bên ngoài hoặc task khác không khai báo `usesService`, Gradle không thể tự biết để khóa nó. Khi CI có nhiều **Gradle builds độc lập**, shared build service của một build không khóa service của build khác; cần isolation/lock ở cấp CI hoặc infra.

## 13. Up-to-date checks, build cache và test dựa trên external state

Một lỗi khó nhận biết: `integrationTest` có thể bị xem là `UP-TO-DATE` hoặc `FROM-CACHE` nếu inputs/outputs được Gradle cho là không đổi, trong khi database bên ngoài **đã được reset hoặc thay đổi**.

Gradle có thể theo dõi:
- Source files, compiled test classes và classpath.
- Test task properties/environment **được khai báo là inputs**.
- Output files, test result files.

Gradle **không tự fingerprint**:
- Bản ghi PostgreSQL hiện đang có trong server.
- Trạng thái message broker/cache bên ngoài.
- Docker container vừa bị tạo hay đang healthy.
- API của dịch vụ ngoài có thay đổi response theo thời gian.

Vì vậy, nếu test thực sự phụ thuộc external state mà chưa được mô hình hóa trong task inputs, có thể chọn:

~~~kotlin
tasks.named<Test>("integrationTest") {
    outputs.upToDateWhen { false }
}
~~~

Dòng này giúp integration test **thực thi khi được yêu cầu**, nhưng có chi phí lớn và không tự bảo đảm môi trường ready; vẫn cần `dependsOn`/readiness. Nếu có thể tạo snapshot/fixture bất biến và khai báo inputs đầy đủ, bạn có thể thiết kế cacheability chính xác hơn, nhưng đừng giả định environment sống là input có thể cache đơn giản.

### Cũng cần chú ý task startup

Một `Exec` task chạy Compose start không có output hữu ích sẽ thường thực thi khi graph yêu cầu; đừng tạo file marker `build/db-started.txt` rồi coi đó là trạng thái service đủ lâu. File marker có thể còn dù container chết từ build trước, gây false positive nếu startup task bị `UP-TO-DATE`.

**Một nguyên tắc:** một output file đại diện cho dữ liệu có thể kiểm tra; một socket/database sống là tài nguyên động. Task model và health probe phải phản ánh bản chất tài nguyên đó.

## 14. Không biến test thành một task `doLast` chạy Java thủ công

Anti-pattern:

~~~kotlin
tasks.register("integrationTest") {
    dependsOn("startDb")
    doLast {
        exec {
            commandLine("java", "-jar", "it-tests.jar")
        }
    }
}
~~~

Đây là **phản ví dụ**:

- Không tận dụng Gradle `Test` task, test classpath, JUnit Platform, XML/HTML reports, filtering và Gradle JVM toolchain.
- `java` từ `PATH` có thể khác JVM mà Java plugin yêu cầu.
- `exec` trực tiếp từ task action có thể khó tương thích với Configuration Cache nếu giữ Project API.
- Exit codes, stdout, test retries và test reports có thể bị xử lý thô sơ.
- Nếu `startDb` không chờ readiness, test vẫn flaky.

Nên dùng **`Test` task** do JVM Test Suite tạo, hoặc `tasks.register<Test>("integrationTest")` ở cách sourceSet truyền thống; cấu hình `javaLauncher` cho test nếu cần. Với hạ tầng, dùng task/provider riêng cho orchestration.

## 15. Debug task graph và lifecycle khi tests fail

Các lệnh hữu ích:

~~~bash
# Xem những task sẽ được lên kế hoạch, không chạy thực.
./gradlew integrationTest --dry-run

# Đọc lý do Gradle chạy/skips tasks, startup logs, test failures.
./gradlew integrationTest --info --stacktrace

# Buộc test chạy lại nếu cần quan sát lifecycle.
./gradlew integrationTest --rerun-tasks --info

# Chạy unit + integration qua lifecycle check.
./gradlew check --info

# Xem các tasks được đăng ký.
./gradlew tasks --all
~~~

`--dry-run` chỉ cho biết **task graph và thứ tự dự kiến**, **không** mở Docker, không kiểm tra health và không chứng minh tests sẽ pass. `--rerun-tasks` buộc nhiều tasks chạy lại, có thể làm Compose restart hoặc làm mất thời gian đáng kể; dùng khi chẩn đoán, không bật vô điều kiện ở CI.

Khi `integrationTest` fail, cần hỏi:

1. `composeUp` có nằm trong task graph không? Nếu không, có khai báo `dependsOn` thật không?
2. `composeUp` có trả success không? Compose `up -d` hay `--wait`? Có healthcheck không?
3. Port/hostname mà test dùng có đúng theo network namespace không? `127.0.0.1` từ host khác `localhost` bên trong container.
4. Migration/schema đã chạy chưa? `pg_isready` không chứng minh bảng đã tồn tại.
5. Credentials có đến đúng process không? Có bị override từ env/properties không?
6. `integrationTest` có đang `UP-TO-DATE` nên không thực thi không?
7. `composeDown` có trong graph và được chạy sau test fail không?
8. Có concurrent job/module khác dùng cùng Compose project name/port không?
9. Test XML/HTML reports cho biết assertion/stacktrace gì?
10. Nếu Docker daemon hoặc Gradle process bị kill, CI cleanup fallback có chạy không?

### Bảng lỗi hay gặp

| Triệu chứng | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| `Connection refused` ngay đầu test | Test bắt đầu khi server chưa listen hoặc endpoint sai. | Dùng readiness health probe + `dependsOn` đúng, xem host/port. |
| Compose báo started nhưng test timeout | Container process đã chạy nhưng app/database chưa healthy. | `docker compose up --wait`, healthcheck có ý nghĩa, deadline rõ. |
| `UnknownTaskException: startDb` | `dependsOn("startDb")` trỏ task chưa đăng ký/sai project path. | Đăng ký TaskProvider hoặc dùng `dependsOn(":infra:startDb")` khi ở project khác. |
| `mustRunAfter` nhưng start task không chạy | Ordering-only không schedule task. | Đổi sang `dependsOn(startInfra)` cho prerequisite thật. |
| Test pass khi chạy riêng nhưng fail trong `check` | Parallelism, thứ tự test/infra, contamination. | Xem `shouldRunAfter`, task graph, DB isolation. |
| `No tests found` hoặc `NO-SOURCE` | Sai `src/integrationTest/java`, suite/test discovery/configuration. | Kiểm tra JVM Test Suite, JUnit, task report, source path. |
| Test import class app thất bại | Custom suite chưa `implementation(project())`. | Thêm project dependency cho suite/sourceSets classpath. |
| Không có `integrationTest` trong `check` | Chưa nối `check.dependsOn(...)`. | Đăng ký quan hệ lifecycle rõ ràng. |
| `finalizedBy` không dọn sau CI kill | Finalizer không bảo đảm khi Gradle process bị kill. | CI finally/TTL/cleanup script dự phòng. |
| Container bị dừng khi module khác đang test | Nhiều task quản lý cùng DB không có owner. | Một owner + lifecycle, service lock hoặc DB riêng. |
| Lỗi bind port 15432 | Another process/container dùng port. | Đổi port, dynamic port mapping, CI isolation. |
| `SELECT 1` pass nhưng DAO test lỗi relation | Database ready nhưng schema chưa migrate. | Thêm migration task/test fixture setup trước DAO tests. |
| `UP-TO-DATE` dù DB đổi | External state không khai báo trong task inputs. | Xem cache model; cân nhắc `outputs.upToDateWhen { false }`. |
| Testcontainers không thấy Docker | Docker daemon/socket permission thiếu. | Kiểm tra Docker access, không cố chạy khi môi trường không hỗ trợ. |
| `BUILD SUCCESSFUL` nhưng không có test thật | `integrationTest` chỉ đăng ký rỗng/NO-SOURCE hoặc không được schedule. | Xem task outcomes, XML/HTML reports, thêm assertions. |
| Java 17 class file nhưng Test task dùng JVM khác | Toolchain test launcher override. | Xem `Test.javaLauncher`/`javaToolchains`, runtime probe. |
| Test logs có secret DB | Password bị in từ env/Gradle debug. | Che log, dùng CI secret store, không đưa credentials thật vào code. |

## 16. Chiến lược CI/CD: setup, test, teardown có chủ sở hữu

Một pipeline có thể đặt startup/cleanup ở **CI level** thay vì Gradle tasks:

~~~text
CI setup:
  - cấp PostgreSQL service/container
  - chờ health + migrations
CI test:
  - ./gradlew integrationTest
CI finally:
  - dọn DB/container/job resources
  - lưu test reports/logs
~~~

Khi đó Gradle integration test task **không nhất thiết** cần `dependsOn(composeUp)` vì CI đã cam kết cung cấp ready service. Điều quan trọng là contract này phải được viết rõ, có health check và fail fast; nếu không, người dùng chạy `./gradlew integrationTest` ở local sẽ thất bại do thiếu infrastructure.

Hai cách vận hành có trade-off:

- **Infra do Gradle quản lý:** local một lệnh tiện, task graph mô tả dependencies; cần cẩn trọng cleanup, cache và parallelism.
- **Infra do CI quản lý:** dễ dùng service containers của CI platform, cleanup tốt qua job lifecycle; local developer cần setup riêng hoặc wrapper script.
- **Infra do Testcontainers quản lý:** lifecycle gần tests, isolation/dynamic ports tốt; cần Docker và API của Testcontainers trong test code.

Không “start hai lần”: nếu CI đã dựng PostgreSQL thật, đừng để Gradle `composeUp` đồng thời khởi động DB khác cùng port. Tài liệu CI cần nêu một owner duy nhất của mỗi resource.

### Secrets, test data và isolation

- Không dùng database production để chạy integration tests có thể ghi/xóa dữ liệu.
- Không hard-code production credentials trong Gradle/Compose/test code; dùng secret injection an toàn.
- Các biến như `it.jdbcUrl`, `it.dbUser`, `it.dbPassword` phải được truyền tới đúng **forked test JVM**. `System.getProperty` khác `System.getenv`; chọn một contract rõ.
- Test cleanup cần xóa dữ liệu nó tạo hoặc reset DB sau test để tránh test order dependence.
- Khi chạy song song, mỗi test job có DB/schema/namespace riêng hoặc dùng resource lock.
- Đánh giá timeouts, network ACL, image provenance, patch versions và resource quotas của Docker/CI.

## 17. Anti-patterns và cách sửa

### Anti-pattern A: “Đã dùng `mustRunAfter` nên database chắc chắn đã chạy”

~~~kotlin
tasks.named("integrationTest") {
    mustRunAfter("startDatabase")
}
~~~

**Sai nếu startDatabase là bắt buộc**. `mustRunAfter` không schedule start task. Sửa:

~~~kotlin
tasks.named("integrationTest") {
    dependsOn("startDatabase")
}
~~~

### Anti-pattern B: “Task `docker compose up -d` thành công thì DB ready”

Container started không đồng nghĩa DB nhận connection, migrations hoàn tất. Sửa: `--wait` kết hợp healthcheck, và probe schema hoặc app readiness nếu contract yêu cầu.

### Anti-pattern C: “Chờ 10 giây là đủ”

~~~kotlin
tasks.register("waitForDb") {
    doLast {
        Thread.sleep(10_000)
    }
}
~~~

Đây là **phản ví dụ**, không nên dùng. Dùng bounded polling/health check hoặc Testcontainers wait strategy. Sleep cố định gây chậm trên máy nhanh, vẫn fail trên máy chậm.

### Anti-pattern D: “Finalizer dọn được cả khi máy bị kill”

`finalizedBy` thường chạy khi task được finalize fail, nhưng process crash/kill có thể cắt ngang. Thêm CI `finally` cleanup và TTL.

### Anti-pattern E: “Mỗi integrationTest tự up/down một DB dùng chung”

Nếu nhiều projects cùng dùng DB, test thứ nhất xong dừng DB của test thứ hai. Sửa: một owner hoặc isolation theo project/CI job; nếu cần giới hạn concurrent Gradle tasks, dùng shared service/maxParallelUsages.

### Anti-pattern F: “Test chạy xanh vì Gradle không thực thi nó”

Một task có `UP-TO-DATE` hoặc `NO-SOURCE` không chứng minh behavior hiện tại. Kiểm tra reports/test count, thử `--rerun-tasks` khi cần, và mô hình hóa external state.

### Anti-pattern G: “Dùng `dependsOn(test)` thay vì `shouldRunAfter(test)` cho mọi integration suite”

Nếu cần **luôn chạy unit tests trước integration tests**, `dependsOn(test)` là hợp lý. Nhưng trong nhiều dự án bạn muốn chạy riêng `integrationTest` mà không bắt unit test, còn `check` chạy cả hai. Khi đó dùng `shouldRunAfter(test)` và `check.dependsOn(integrationTest)` để giữ quyền chạy độc lập.

## 18. Checklist hoàn thành tích hợp hạ tầng

- [ ] Integration tests tách biệt khỏi unit tests, có source set/suite và test report riêng.
- [ ] Tất cả test dependencies nằm trong đúng configuration/suite.
- [ ] Test thấy production output qua `implementation(project())` hoặc classpath model đúng.
- [ ] Hạ tầng có một owner cho startup và teardown.
- [ ] Nếu Gradle quản lý, `integrationTest.dependsOn(startInfra)` được khai báo thực sự.
- [ ] `startInfra` chỉ báo success sau khi **readiness** thỏa điều kiện.
- [ ] Có health check, bounded timeout, migrations/seed data nếu cần.
- [ ] `integrationTest.finalizedBy(stopInfra)` hoặc lifecycle cleanup tương đương.
- [ ] Có fallback cleanup nếu startup fail một phần hoặc CI/Gradle bị kill.
- [ ] Không dùng `mustRunAfter`/`shouldRunAfter` thay `dependsOn` cho prerequisite.
- [ ] Không dùng fixed sleep làm readiness.
- [ ] Port, namespace, DB/schema và Compose project được cô lập khi parallel.
- [ ] External state được xử lý đúng trong Gradle up-to-date/build-cache model.
- [ ] Test task không bị `NO-SOURCE` hoặc bị skip ngoài ý muốn.
- [ ] Test thật sự chạm service và có assertions có ý nghĩa.
- [ ] Lệnh `check` có đưa suite integration vào graph khi policy yêu cầu.
- [ ] CI có timeouts, logs, XML/HTML reports, failure triage, secret redaction.
- [ ] Không chứa production data/secret trong local demo hay test logs.
- [ ] Có quy trình chạy local và CI cùng contract environment rõ ràng.

## 19. Câu hỏi tự kiểm tra

1. **Sự khác biệt giữa `testImplementation` và `dependsOn(startDatabase)`?** Cái đầu thêm thư viện vào test classpath; cái sau thêm task prerequisite vào execution graph.
2. **`mustRunAfter(startDatabase)` có tự chạy startDatabase không?** Không; chỉ có hiệu lực nếu cả hai tasks đã được schedule.
3. **`shouldRunAfter(test)` có bắt `test` chạy khi gọi `integrationTest` không?** Không.
4. **`dependsOn(startInfra)` có chắc database đã ready không?** Chỉ khi startInfra thực sự xác minh readiness trước khi báo success.
5. **`docker compose up -d` có đủ để kết luận PostgreSQL ready không?** Không; cần healthcheck/`--wait`/probe phù hợp.
6. **`finalizedBy(stopInfra)` làm gì khi integrationTest fail?** Thường vẫn chạy finalizer; không bảo đảm khi process bị kill hoặc prerequisite fail khiến test không chạy.
7. **JVM Test Suite có tự thêm integrationTest vào `check` không?** Không mặc định; nối `check.dependsOn(testing.suites.named("integrationTest"))` nếu policy muốn.
8. **Vì sao suite `integrationTest` cần `implementation(project())`?** Để thấy production code và dependencies cần thiết theo model của suite.
9. **Khi nào dùng Testcontainers thay vì Compose?** Khi muốn test quản lý container lifecycle/dynamic ports, isolation theo test class hoặc suite.
10. **Có nên để Gradle composeUp cùng lúc với Testcontainers start một DB khác không?** Không nếu không có nhu cầu rõ; cần một owner hạ tầng.
11. **Vì sao `outputs.upToDateWhen { false }` có thể cần?** External database state thường không được fingerprint bởi task inputs; phải tránh test skip do cache/up-to-date sai.
12. **`--dry-run` chứng minh gì?** Task graph dự kiến; không chứng minh service ready hay test pass.
13. **Hai modules dùng một DB có thể chạy `--parallel` an toàn không?** Chỉ khi data isolation/resource lock/lifecycle được thiết kế rõ.
14. **`pg_isready` có đảm bảo bảng `orders` tồn tại không?** Không, nó kiểm tra database server sẵn sàng chấp nhận connection, migrations là việc khác.
15. **Test `SELECT 1` có thể pass mà DAO test fail không?** Có, khi schema sai/migrations chưa chạy.
16. **Test Docker/Compose không chạy khi máy không có Docker là lỗi Java?** Không; là lỗi prerequisite infrastructure/runtime environment.
17. **Khi Gradle test bị `NO-SOURCE`, xem gì?** Source paths, registration, JUnit discovery, test task report.
18. **Có nên hard-code `localhost:5432` cho Testcontainers?** Không; đọc host/mapped port hoặc JDBC URL từ container.
19. **Gradle Build Service `maxParallelUsages` khóa các CI jobs độc lập không?** Không; nó phối hợp tasks có dùng service trong cùng Gradle build.
20. **Một pipeline đáng tin cần những bước nào?** Setup/readiness, schema/data prep, test thực, teardown cuối cùng và evidence/logs.

## 20. Nguồn chính thức và đọc thêm

- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): đăng ký `integrationTest` suite, JUnit Jupiter, `implementation(project())`, `shouldRunAfter`, gắn vào `check`.
- [Gradle — Testing in JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `sourceSets`/`Test` task, test classpath và test reports.
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): `dependsOn`, `mustRunAfter`, `shouldRunAfter`, `finalizedBy`, task failures.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `tasks.named`, TaskProvider và task relationships.
- [Gradle — Shared Build Services](https://docs.gradle.org/current/userguide/build_services.html): lifecycle, `AutoCloseable`, `usesService`, `maxParallelUsages` và Configuration Cache.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): task inputs/outputs và up-to-date checks.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): caching và mô hình input.
- [Docker Docs — docker compose up](https://docs.docker.com/reference/cli/docker/compose/up/): `--wait`, `--wait-timeout`, detached services.
- [Docker Docs — Healthchecks in Compose](https://docs.docker.com/compose/how-tos/startup-order/): health, startup order và service dependencies.
- [Testcontainers — JUnit 5 Quickstart](https://java.testcontainers.org/quickstart/junit_5_quickstart/): JUnit integration, `@Container`, lifecycle, dynamic ports.
- [Testcontainers — JUnit Jupiter Integration](https://java.testcontainers.org/test_framework_integration/junit_5/): static/instance container lifecycle và parallelism limitations.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): JDBC URL, driver dependencies và PostgreSQL container.
