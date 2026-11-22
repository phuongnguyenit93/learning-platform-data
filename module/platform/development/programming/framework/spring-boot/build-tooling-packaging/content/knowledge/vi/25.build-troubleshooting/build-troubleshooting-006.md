# Kiểm tra khởi động JAR hoặc image trên môi trường sạch

## 1. Mục tiêu

Một ứng dụng Spring Boot có thể chạy tốt bằng `./gradlew bootRun` trên laptop nhưng thất bại khi chạy JAR đã đóng gói hoặc OCI image trên server. Nguyên nhân thường nằm ở classpath, cấu hình chỉ có trên máy lập trình, file ngoài JAR, working directory, Java runtime, permissions, network hoặc container entrypoint.

**Kiểm tra trên môi trường sạch** là chạy đúng sản phẩm phát hành trong một môi trường tách biệt với workspace/build process của developer, rồi xác nhận ứng dụng thực sự khởi động, sẵn sàng nhận request, trả đúng kết quả và dừng đúng cách.

Bài học phân biệt ba mức:

1. **Kiểm JAR:** chạy executable Boot JAR bằng `java -jar`, trong thư mục tạm và environment được kiểm soát. Không dùng Gradle/Maven runtime classpath để che thiếu dependency.
2. **Kiểm image:** chạy chính OCI image đã build, không mount source/build outputs từ host, không truyền các biến môi trường ngầm từ máy developer.
3. **Kiểm release candidate:** xác nhận artifact/image digest, Java runtime, health/readiness, logs và những external dependencies mà môi trường đích yêu cầu.

Mục tiêu thực hành:

- Tạo một Spring Boot Java 17 application có endpoint smoke test và Actuator health probes.
- Build executable JAR bằng Gradle hoặc Maven.
- Kiểm tra manifest, JAR entries và checksum trước khi chạy.
- Chạy JAR trong temporary working directory với environment allowlist, readiness timeout và cleanup.
- Tạo image bằng Spring Boot Buildpacks hoặc Dockerfile, chạy image không bind source/cache của host.
- Phân biệt process started, liveness, readiness và application-level response.
- Thêm kiểm thử vào CI để chạy **artifact đã build** trên một job/môi trường sạch.
- Chẩn đoán lỗi cấu hình, port, Java, permission, health checks, database và container startup.

**Phiên bản ví dụ:** Java 17, Spring Boot 3.3.13. Các lệnh shell chính dùng Linux/macOS và Docker CLI; phần Windows PowerShell được nêu riêng. Đây là mốc minh họa, không phải tuyên bố phiên bản mới nhất.

## 2. “Môi trường sạch” có nghĩa gì?

Một test chỉ thực sự kiểm tra artifact khi nó không vô tình dùng những thứ mà artifact không mang theo.

| Thành phần | Môi trường developer thường có | Môi trường smoke test sạch cần làm rõ |
| --- | --- | --- |
| Classpath | Gradle/Maven IDE classpath, compiled classes | Chỉ executable JAR và runtime dependencies đã đóng gói |
| Working directory | Root repository có config/logs/files | Temporary directory trống, chỉ cấp những file được phép |
| Environment variables | JAVA_TOOL_OPTIONS, SPRING_*, proxy, secrets | Environment allowlist; chỉ truyền biến cần thiết |
| Java | JDK/toolchain trên laptop | JRE/JDK đúng version và vendor policy |
| File system | Source, build/, target/, local certificates | Không mount source/cache; quyền đọc/ghi rõ |
| Network | DB/Redis/service đang chạy trên máy | Không giả định external service có sẵn; dùng test dependency riêng |
| Container | Docker Compose dev stack | Chính image release candidate, config và mounts có chủ đích |
| Artifact | Có thể chạy `bootRun` từ classes | Chạy file JAR/image đã đóng gói, có digest xác định |

**Clean không đồng nghĩa offline hoặc không có dependency.** Nếu production cần PostgreSQL, Redis hoặc message broker, một smoke test chỉ xác nhận JVM và HTTP server không chứng minh các tích hợp đó hoạt động. Hãy thêm một test environment có external services ephemeral/được quản lý, ví dụ Testcontainers hoặc test namespace.

Một môi trường sạch cũng không hoàn toàn hermetic: kernel, Docker daemon, CPU architecture, DNS, clock và network vẫn là inputs. Hãy ghi nhận những yếu tố quan trọng và không tuyên bố reproducibility tuyệt đối chỉ vì chạy trong một temporary directory.

## 3. Project Spring Boot mẫu

Ta xây một HTTP application có:

- `GET /smoke` trả chính xác `ok` để xác nhận request đi tới controller.
- `GET /actuator/health/liveness` để kiểm process còn sống và health indicator liveness.
- `GET /actuator/health/readiness` để kiểm ứng dụng đã sẵn sàng nhận traffic.
- Graceful shutdown để container/CI có thể gửi SIGTERM và chờ process kết thúc.

Cấu trúc:

~~~text
smoke-app/
├── settings.gradle                 # chọn Groovy DSL
├── build.gradle
│   hoặc settings.gradle.kts        # chọn Kotlin DSL
│   hoặc build.gradle.kts
├── pom.xml                         # thay Gradle nếu dùng Maven
└── src/
    ├── main/
    │   ├── java/com/example/smoke/
    │   │   ├── SmokeApplication.java
    │   │   └── SmokeController.java
    │   └── resources/application.properties
    └── test/java/com/example/smoke/
        └── SmokeControllerTest.java
~~~

Không để Gradle Groovy, Kotlin DSL và Maven cùng được hiểu là ba build scripts cho cùng một module. Chọn build tool thực sự dùng trong repository.

### 3.1. Main class

`src/main/java/com/example/smoke/SmokeApplication.java`:

~~~java
package com.example.smoke;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SmokeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SmokeApplication.class, args);
    }
}
~~~

### 3.2. Controller

`src/main/java/com/example/smoke/SmokeController.java`:

~~~java
package com.example.smoke;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SmokeController {

    @GetMapping("/smoke")
    public String smoke() {
        return "ok";
    }
}
~~~

Body HTTP chính xác của endpoint này là `ok` (không cần JSON wrapper). Endpoint này cố ý đơn giản để phân biệt lỗi khởi động HTTP server với lỗi nghiệp vụ phức tạp.

### 3.3. application.properties

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
~~~

- `server.port` xác định port bên trong process.
- `server.shutdown=graceful` cho Spring Boot chờ request đang xử lý trong quá trình shutdown theo lifecycle.
- `spring.lifecycle.timeout-per-shutdown-phase` giới hạn thời gian chờ cho từng shutdown phase.
- `management.endpoint.health.probes.enabled=true` bật liveness/readiness health groups cho local smoke test.
- Chỉ expose `health` trong ví dụ, không mở toàn bộ Actuator endpoints.

Với Spring Boot 3.3, khi chạy trong Kubernetes, availability probes có thể được cấu hình tự động theo môi trường; bật tường minh ở đây giúp kiểm tra local/container nhất quán. Health endpoint không tự xác minh mọi nghiệp vụ hoặc mọi dependency nếu chưa có health indicators tương ứng.

### 3.4. JUnit test

`src/test/java/com/example/smoke/SmokeControllerTest.java`:

~~~java
package com.example.smoke;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SmokeControllerTest {

    @Test
    void returnsSmokeResponse() {
        SmokeController controller = new SmokeController();
        assertEquals("ok", controller.smoke());
    }
}
~~~

Test trên kiểm tra controller logic nhưng **không khởi động Spring context hoặc HTTP server**. Smoke test chạy JAR/image ở phần sau mới xác nhận wiring, embedded server, classpath, runtime config và endpoint thật.

## 4. Build executable JAR bằng Gradle

### 4.1. Groovy DSL

`settings.gradle`:

~~~groovy
rootProject.name = 'smoke-app'
~~~

`build.gradle` đầy đủ:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'smoke-app.jar'
}

tasks.named('bootBuildImage') {
    imageName = 'local/smoke-app:1.0.0'
}
~~~

`bootJar` tạo executable Spring Boot archive có dependencies/loader layout phù hợp. Đặt archive filename rõ ràng để test script luôn lấy đúng file `build/libs/smoke-app.jar`. Không chọn ngẫu nhiên một file từ glob `*.jar` vì có thể có cả `-plain.jar`.

### 4.2. Kotlin DSL

Nếu project dùng Kotlin DSL, thay cặp Groovy files bằng:

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "smoke-app"
~~~

`build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("smoke-app.jar")
}

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("local/smoke-app:1.0.0")
}
~~~

Kotlin DSL chỉ thay cách viết build script; application Java source không thay đổi. Chỉ dùng một DSL trong cùng module.

### 4.3. Build và test

Với Gradle Wrapper:

~~~bash
./gradlew --version
./gradlew clean test bootJar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar
~~~

File cần kiểm tra:

~~~text
build/libs/smoke-app.jar
~~~

Nếu `bootJar` chưa tạo file, xem task output và build logs trước khi chạy smoke script. Đừng thay bằng `bootRun`: `bootRun` chạy từ Gradle-managed classes/runtime classpath, không chứng minh executable JAR đã đóng gói đúng.

## 5. Build executable JAR bằng Maven

Đây là project Maven thay thế Gradle, sử dụng cùng Java source/resources ở mục 3.

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>smoke-app</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <finalName>smoke-app</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot parent quản lý dependency/plugin versions và repackage execution. `<finalName>smoke-app</finalName>` làm tên artifact ổn định là `target/smoke-app.jar`; tọa độ Maven vẫn là `smoke-app:1.0.0`.

Build:

~~~bash
./mvnw -B -ntp clean verify
~~~

Nếu không có Maven Wrapper nhưng có Maven đã cài theo policy:

~~~bash
mvn -B -ntp clean verify
~~~

Artifact:

~~~text
target/smoke-app.jar
~~~

Goal `verify` chạy các lifecycle phases trước đó, gồm test/package theo cấu hình project. Đảm bảo Maven repackage đã chạy để JAR có Spring Boot loader và dependencies. Không lấy plain Maven JAR chưa repackage rồi kỳ vọng `java -jar` chạy được.

## 6. Kiểm tra artifact trước khi khởi động

Một smoke test có thể fail vì chọn nhầm file hoặc file transfer hỏng. Xác nhận đúng artifact trước:

### 6.1. Kiểm tra kích thước và SHA-256

Linux/macOS:

~~~bash
ls -lh build/libs/smoke-app.jar
sha256sum build/libs/smoke-app.jar
~~~

Maven đổi path:

~~~bash
ls -lh target/smoke-app.jar
sha256sum target/smoke-app.jar
~~~

Windows PowerShell:

~~~powershell
Get-Item .\build\libs\smoke-app.jar | Select-Object Name, Length
Get-FileHash .\build\libs\smoke-app.jar -Algorithm SHA256
~~~

Lưu digest trong CI artifact metadata để so sánh trước/sau khi upload/download. Checksum tự tính không chứng minh publisher; nó giúp phát hiện artifact bị thay đổi khi so với digest được truyền qua kênh đáng tin cậy.

### 6.2. Kiểm JAR entries

~~~bash
jar tf build/libs/smoke-app.jar
~~~

Một executable Spring Boot JAR thường có:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/smoke/SmokeApplication.class
BOOT-INF/classes/com/example/smoke/SmokeController.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/...
~~~

Đường dẫn loader có thể thay đổi theo Spring Boot version; các entry `BOOT-INF/classes` và `BOOT-INF/lib` là những dấu hiệu quan trọng của executable Boot archive. Không chỉ kiểm file có đuôi `.jar`.

### 6.3. Kiểm Manifest

Nếu có `unzip`:

~~~bash
unzip -p build/libs/smoke-app.jar META-INF/MANIFEST.MF
~~~

Manifest của executable JAR có thể có `Main-Class` trỏ tới Spring Boot launcher và `Start-Class` trỏ tới main application class. Tên launcher thay đổi theo Spring Boot version/packaging mode; đọc manifest thực tế thay vì hardcode một giá trị cho mọi dòng Boot.

Nếu không có `unzip`, có thể dùng JDK `jar` giải nén vào thư mục tạm rồi đọc manifest. Không giải nén untrusted archive vào project root.

### 6.4. Kiểm Java runtime

~~~bash
java -version
~~~

Ứng dụng mẫu được compile `--release 17` và Spring Boot 3.3.13 cần Java 17 trở lên. Smoke test nên dùng đúng JRE/vendor/version được môi trường deploy chấp nhận. Nếu chạy trên Java mới hơn, cần xác minh compatibility thay vì cho rằng mọi patch/vendor đều giống nhau.

## 7. Chạy JAR trong môi trường sạch

### 7.1. Vì sao dùng java -jar?

Lệnh:

~~~bash
java -jar build/libs/smoke-app.jar
~~~

chạy executable archive theo manifest/loader của Spring Boot. Đây là cách gần với production launch hơn `bootRun` hoặc `spring-boot:run`, vốn có thể sử dụng source classes và build tool classpath.

Để kiểm tra độc lập hơn, chạy từ một temporary directory trống, dùng absolute path tới JAR và chỉ cung cấp environment cần thiết.

### 7.2. Smoke test script cho Linux/macOS

Tạo `scripts/smoke-jar.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

APP_JAR="build/libs/smoke-app.jar"
PORT="18080"
BASE_URL="http://127.0.0.1:$PORT"

if [[ ! -f "$APP_JAR" ]]; then
  echo "JAR not found: $APP_JAR" >&2
  exit 1
fi

APP_JAR="$(cd "$(dirname "$APP_JAR")" && pwd)/$(basename "$APP_JAR")"
WORK_DIR="$(mktemp -d)"
mkdir -p "$WORK_DIR/home" "$WORK_DIR/tmp"
LOG_FILE="$WORK_DIR/application.log"
APP_PID=""

cleanup() {
  if [[ -n "$APP_PID" ]] && kill -0 "$APP_PID" 2>/dev/null; then
    kill -TERM "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

(
  cd "$WORK_DIR"
  exec env -i \
    PATH="$PATH" \
    HOME="$WORK_DIR/home" \
    TMPDIR="$WORK_DIR/tmp" \
    LANG="C.UTF-8" \
    TZ="UTC" \
    java -jar "$APP_JAR" \
      --server.address=127.0.0.1 \
      --server.port="$PORT"
) >"$LOG_FILE" 2>&1 &
APP_PID="$!"

READY=0
ATTEMPT=0
while [[ "$ATTEMPT" -lt 60 ]]; do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "Application exited before readiness." >&2
    cat "$LOG_FILE" >&2
    exit 1
  fi

  if curl --fail --silent --connect-timeout 1 --max-time 2 \
    "$BASE_URL/actuator/health/readiness" >/dev/null; then
    READY=1
    break
  fi

  ATTEMPT=$((ATTEMPT + 1))
  sleep 1
done

if [[ "$READY" -ne 1 ]]; then
  echo "Application did not become ready within 60 seconds." >&2
  cat "$LOG_FILE" >&2
  exit 1
fi

BODY="$(curl --fail --silent --connect-timeout 1 --max-time 5 "$BASE_URL/smoke")"
if [[ "$BODY" != "ok" ]]; then
  echo "Unexpected /smoke response: $BODY" >&2
  cat "$LOG_FILE" >&2
  exit 1
fi

curl --fail --silent --connect-timeout 1 --max-time 5 \
  "$BASE_URL/actuator/health/liveness" >/dev/null
echo "JAR_SMOKE_PASS"
~~~

Chạy sau khi build:

~~~bash
chmod +x scripts/smoke-jar.sh
./scripts/smoke-jar.sh
~~~

Stdout khi toàn bộ checks pass:

~~~text
JAR_SMOKE_PASS
~~~

Script tạo HOME/TMPDIR riêng, bỏ phần lớn environment variables thừa bằng `env -i`, đổi working directory sang thư mục tạm, khởi chạy đúng JAR và đợi readiness tối đa 60 giây. `exec` giúp shell trong subshell được thay bằng process Java để signal/cleanup nhắm đúng process hơn. Nếu app exit sớm hoặc timeout, script in log để chẩn đoán. Trap dừng process và xóa temporary directory.

**Điều chỉnh trước khi dùng cho app thật:** thêm đúng environment variables/secrets cần thiết bằng allowlist; đổi port nếu bị chiếm; điều chỉnh readiness timeout theo startup budget thực tế. Không truyền toàn bộ `env` của developer vào script.

### 7.3. Ý nghĩa của timeout

60 giây trong ví dụ là timeout smoke test, không phải cam kết mọi ứng dụng phải start trong 60 giây. Ứng dụng lớn, JIT warmup, migrations hoặc dependencies có thể cần ngân sách khác. Đặt timeout dựa trên SLA/startup characteristics, giữ đủ dài để CI ổn định nhưng đủ ngắn để fail nhanh khi process lỗi.

Nếu process chết trước readiness, ưu tiên đọc log startup. Nếu process còn sống nhưng readiness chưa đạt, kiểm health indicators, config và external dependencies. Không tăng timeout vô hạn để che một readiness failure.

## 8. PowerShell: kiểm JAR trên Windows

Có thể kiểm tra JAR bằng PowerShell/.NET Process API. Đoạn dưới khởi chạy Java với working directory tạm và chuyển stdout/stderr vào log file; với project thực, bổ sung environment allowlist theo policy.

~~~powershell
$ErrorActionPreference = "Stop"

$jar = (Resolve-Path ".\build\libs\smoke-app.jar").Path
$port = 18080
$baseUrl = "http://127.0.0.1:$port"
$workDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString("N"))
$logFile = Join-Path $workDir "application.log"
New-Item -ItemType Directory -Path $workDir | Out-Null

$process = $null
$logWriter = $null

try {
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = (Get-Command java).Source
    $psi.WorkingDirectory = $workDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.ArgumentList.Add("-jar")
    $psi.ArgumentList.Add($jar)
    $psi.ArgumentList.Add("--server.address=127.0.0.1")
    $psi.ArgumentList.Add("--server.port=$port")

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    $logWriter = [System.IO.StreamWriter]::new($logFile, $false)

    $process.add_OutputDataReceived({
        param($sender, $eventArgs)
        if ($eventArgs.Data) { $logWriter.WriteLine($eventArgs.Data) }
    })
    $process.add_ErrorDataReceived({
        param($sender, $eventArgs)
        if ($eventArgs.Data) { $logWriter.WriteLine($eventArgs.Data) }
    })

    [void]$process.Start()
    $process.BeginOutputReadLine()
    $process.BeginErrorReadLine()

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($process.HasExited) {
            throw "Application exited before readiness. See $logFile"
        }

        try {
            $response = Invoke-WebRequest -Uri "$baseUrl/actuator/health/readiness" -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    if (-not $ready) {
        throw "Application did not become ready within 60 seconds. See $logFile"
    }

    $body = (Invoke-WebRequest -Uri "$baseUrl/smoke" -TimeoutSec 5).Content
    if ($body -ne "ok") {
        throw "Unexpected /smoke response: $body"
    }

    Write-Output "JAR_SMOKE_PASS"
}
finally {
    if ($process -and -not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit()
    }
    if ($process) { $process.Dispose() }
    if ($logWriter) { $logWriter.Dispose() }
    if (Test-Path $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force }
}
~~~

Chạy:

~~~powershell
.\scripts\smoke-jar.ps1
~~~

Output khi pass:

~~~text
JAR_SMOKE_PASS
~~~

Ví dụ dùng `ProcessStartInfo.ArgumentList` trên PowerShell/.NET hiện đại. Nếu runner dùng Windows PowerShell/.NET cũ không hỗ trợ property này, hãy dùng cách tạo process arguments được quote đúng hoặc chuyển sang PowerShell 7. Không ghép chuỗi arguments từ dữ liệu không tin cậy.

Script trên dùng environment của process cha theo mặc định. Muốn cô lập kỹ hơn, xóa các biến thừa khỏi `psi.Environment` rồi thêm allowlist (ví dụ PATH, TEMP, JAVA_HOME và các biến app bắt buộc); đừng xóa các biến runtime Windows bắt buộc một cách máy móc.

## 9. Liveness, readiness và startup: ba câu hỏi khác nhau

Spring Boot Actuator cung cấp health groups:

- **Liveness:** ứng dụng process còn ở trạng thái có thể tiếp tục chạy không? Nếu liveness fail, platform có thể restart container.
- **Readiness:** ứng dụng đã sẵn sàng nhận request chưa? Nếu readiness fail, platform nên ngừng route traffic tới instance đó.
- **Startup probe:** dành cho platform/orchestrator để cho ứng dụng thời gian khởi động; trong Kubernetes đây là probe riêng ở cấu hình Pod, không phải cùng một health group bắt buộc cho mọi Spring Boot app.

### 9.1. Vì sao không đưa mọi external dependencies vào liveness?

Nếu database tạm thời mất kết nối và liveness phụ thuộc trực tiếp DB, mọi app instance có thể bị restart liên tục, làm hệ thống phục hồi khó hơn. Spring Boot khuyến nghị phân biệt trạng thái ứng dụng với trạng thái external dependencies; readiness có thể phù hợp hơn để phản ánh app có thể phục vụ request hay chưa.

Mặc định của liveness/readiness groups không tự kiểm tra mọi external services. Nếu business readiness yêu cầu database/broker, hãy thêm indicator có chủ đích vào readiness group và test behavior. Không đưa check nặng hoặc phụ thuộc chéo vào liveness nếu có nguy cơ restart loop.

### 9.2. Endpoints trong ví dụ

Với properties mục 3:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Khi trạng thái UP, HTTP status thường là 200 và JSON có dạng:

~~~json
{
  "status": "UP"
}
~~~

Response có thể có chi tiết components tùy security/configuration. Smoke test chỉ kiểm HTTP success; không hardcode JSON formatting/ordering. Nếu security policy bảo vệ endpoint, test phải dùng đúng credentials/route nội bộ đã được cấp.

### 9.3. Health 200 chưa chứng minh nghiệp vụ đúng

Vì vậy script còn gọi:

~~~bash
curl --fail --silent http://127.0.0.1:18080/smoke
~~~

và so sánh body chính xác với `ok`. Trong app thật, hãy chọn một endpoint smoke test không tạo side effects, không yêu cầu dữ liệu cá nhân và đủ xác nhận đường request quan trọng. Không dùng endpoint tạo giao dịch hoặc xóa dữ liệu trong startup smoke test.

### 9.4. Health endpoint có thể bị bảo vệ

Nếu Spring Security được cấu hình, Actuator endpoints có thể trả 401/403 dù app đã khởi động. Điều đó có thể là behavior đúng. Hãy cấp test credentials/token qua secret manager hoặc expose probe endpoint trên management interface/network nội bộ theo policy; không mở health details ra public chỉ để CI dễ gọi.

## 10. Kiểm tra image trong môi trường sạch

Có hai cách phổ biến tạo image:

1. Spring Boot Buildpacks: Gradle `bootBuildImage` hoặc Maven `spring-boot:build-image`.
2. Dockerfile multi-stage: build JAR ở builder stage rồi copy JAR vào runtime image.

Smoke test runtime gần giống nhau: chạy **image reference đã build**, không mount source/build folder hoặc Maven/Gradle cache từ host.

### 10.1. Build image bằng Spring Boot Buildpacks

Gradle project ở mục 4 đã cấu hình:

~~~groovy
tasks.named('bootBuildImage') {
    imageName = 'local/smoke-app:1.0.0'
}
~~~

Build:

~~~bash
./gradlew bootBuildImage
~~~

Maven POM thêm image configuration:

~~~xml
<configuration>
    <image>
        <name>local/smoke-app:1.0.0</name>
    </image>
</configuration>
~~~

Sau đó:

~~~bash
mvn spring-boot:build-image
~~~

Buildpacks tạo image thông qua builder/run image. Việc build thành công chưa xác nhận endpoint chạy được; vẫn phải chạy container.

### 10.2. Dockerfile multi-stage (lựa chọn thay thế)

Nếu repository dùng Dockerfile, ví dụ:

~~~dockerfile
# syntax=docker/dockerfile:1

FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

COPY gradlew ./
COPY gradle/ ./gradle/
COPY settings.gradle build.gradle ./
RUN chmod +x gradlew

COPY src/ ./src/
RUN ./gradlew --no-daemon clean test bootJar

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app
COPY --from=build /workspace/build/libs/smoke-app.jar /app/smoke-app.jar

EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/smoke-app.jar"]
~~~

Build image:

~~~bash
docker build --pull -t local/smoke-app:1.0.0 .
~~~

Dockerfile này dùng Gradle Groovy DSL và yêu cầu wrapper files/source nằm trong build context, không bị `.dockerignore` loại bỏ. Nếu dùng Kotlin DSL, thay các file Gradle tương ứng. Nếu project dùng Maven, builder stage phải copy POM/Wrapper và output của Maven repackage đúng path.

Đây là **một phương án tạo image**, không cần thêm Dockerfile nếu pipeline đã dùng Buildpacks. Trong mọi trường hợp, bước smoke test phải chạy đúng final image.

### 10.3. Kiểm image identity

~~~bash
docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}}' local/smoke-app:1.0.0
~~~

Ghi lại image ID, OS và architecture để biết đang kiểm image nào. Trong CI/release, ưu tiên digest immutable của registry sau khi push. Không dùng tag mutable làm bằng chứng duy nhất rằng smoke test và deployment đang chạy cùng bytes.

## 11. Smoke test image bằng Docker

### 11.1. Chạy thủ công

~~~bash
docker run --rm -p 18081:8080 local/smoke-app:1.0.0
~~~

Giữ container chạy foreground. Terminal khác:

~~~bash
curl --fail --silent http://127.0.0.1:18081/actuator/health/readiness
curl --fail --silent http://127.0.0.1:18081/smoke
~~~

Body của endpoint ứng dụng:

~~~text
ok
~~~

Dừng bằng Ctrl+C. `EXPOSE 8080` trong Dockerfile chỉ là metadata; `-p 18081:8080` mới ánh xạ port host 18081 sang container port 8080.

### 11.2. Automated image smoke script

Tạo `scripts/smoke-image.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

IMAGE_REF="local/smoke-app:1.0.0"
CONTAINER_NAME="smoke-app-smoke-$$"
HOST_PORT="18081"
BASE_URL="http://127.0.0.1:$HOST_PORT"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker run --detach \
  --name "$CONTAINER_NAME" \
  --publish "127.0.0.1:$HOST_PORT:8080" \
  "$IMAGE_REF"

READY=0
ATTEMPT=0

while [[ "$ATTEMPT" -lt 60 ]]; do
  RUNNING="$(docker inspect --format '{{.State.Running}}' \
    "$CONTAINER_NAME" 2>/dev/null || echo false)"

  if [[ "$RUNNING" != "true" ]]; then
    echo "Container exited before readiness." >&2
    docker logs "$CONTAINER_NAME" >&2 || true
    exit 1
  fi

  if curl --fail --silent --connect-timeout 1 --max-time 2 \
    "$BASE_URL/actuator/health/readiness" >/dev/null; then
    READY=1
    break
  fi

  ATTEMPT=$((ATTEMPT + 1))
  sleep 1
done

if [[ "$READY" -ne 1 ]]; then
  echo "Container did not become ready within 60 seconds." >&2
  docker logs "$CONTAINER_NAME" >&2 || true
  exit 1
fi

BODY="$(curl --fail --silent --connect-timeout 1 --max-time 5 "$BASE_URL/smoke")"
if [[ "$BODY" != "ok" ]]; then
  echo "Unexpected /smoke response: $BODY" >&2
  docker logs "$CONTAINER_NAME" >&2 || true
  exit 1
fi

curl --fail --silent --connect-timeout 1 --max-time 5 \
  "$BASE_URL/actuator/health/liveness" >/dev/null

docker stop --time 20 "$CONTAINER_NAME" >/dev/null
echo "IMAGE_SMOKE_PASS"
~~~

Chạy:

~~~bash
chmod +x scripts/smoke-image.sh
./scripts/smoke-image.sh
~~~

Stdout cuối cùng khi pass:

~~~text
IMAGE_SMOKE_PASS
~~~

Script không mount project, `build/`, `target/`, `.gradle`, `.m2` hoặc source vào container. Nó chạy đúng image, đợi readiness, kiểm body ứng dụng và dừng container. Trap dọn container khi thành công hoặc thất bại.

Nếu Docker daemon dùng context khác, image chưa có local hoặc port 18081 đang bận, sửa môi trường/test port theo CI policy. Không đổi sang một image tag khác chỉ để script pass mà quên ghi lại image ID/digest.

### 11.3. Kiểm tra môi trường runtime chặt hơn

Với ứng dụng mẫu không ghi vào root filesystem, có thể thử thêm các hạn chế:

~~~bash
docker run --detach \
  --name smoke-app-readonly \
  --publish 127.0.0.1:18081:8080 \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=64m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  local/smoke-app:1.0.0
~~~

Đây là **hardening test tùy chọn**. Một số ứng dụng cần writable directories, certificates, native temp files hoặc Linux capabilities; khi đó phải thiết kế mount/quyền tối thiểu và test theo runtime contract. Không dùng các flags này mà không hiểu yêu cầu ứng dụng. Nếu container fail chỉ khi `--read-only`, điều tra filesystem writes trước khi kết luận JAR lỗi.

### 11.4. Không dùng --network none một cách máy móc

Nếu app không cần external services, có thể kiểm tra không kết nối network ngoài bằng network isolation phù hợp. Nhưng publish port từ host và network `none` không hoạt động giống bridge network; test connectivity cần được thiết kế lại. Với app cần DB/Redis, network isolation tuyệt đối sẽ khiến readiness fail đúng như dự kiến. Hãy dùng một network test có các dependencies ephemeral thay vì bỏ qua dependency checks.

## 12. Không kế thừa config developer ngoài ý muốn

### 12.1. Những biến có thể làm test pass giả

Các biến môi trường có ảnh hưởng Spring Boot:

- `SPRING_PROFILES_ACTIVE`: chọn profile và file config.
- `SPRING_DATASOURCE_URL`/username/password: kết nối database.
- `SPRING_CONFIG_LOCATION`/`SPRING_CONFIG_ADDITIONAL_LOCATION`: nạp config ngoài JAR.
- `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`: thêm JVM flags.
- `SERVER_PORT`: thay port mặc định.
- `HTTP_PROXY`/`HTTPS_PROXY`: ảnh hưởng network.
- Các secret/token/cloud credentials: làm app kết nối được service mà image sạch không có.

Nếu test trên laptop đang có `.env`/IDE run configuration, app có thể pass dù release image thiếu config cần thiết. Script JAR dùng `env -i` để xóa hầu hết inherited variables; sau đó chỉ thêm biến được khai báo rõ.

### 12.2. Externalized configuration là một contract

Nếu production cần:

~~~text
SPRING_DATASOURCE_URL
SPRING_DATASOURCE_USERNAME
SPRING_DATASOURCE_PASSWORD
~~~

hãy cấp đúng values từ test secret manager/test database ở smoke/integration environment. Không hardcode credentials vào JAR, Dockerfile, build args hoặc test script. Một test không có database chỉ xác nhận app có thể start **khi không cần database**; không thể chứng minh production configuration với DB.

### 12.3. Kiểm working directory

Spring Boot có thể nạp external config theo các locations tương đối/current directory. Vì vậy chạy từ thư mục tạm trống giúp phát hiện dependency vào file `./application.yml` hoặc `./config/` vô tình có ở repository root.

Nếu ứng dụng chủ đích dùng external config mount, hãy test cả hai trường hợp:

1. Không có mount: ứng dụng fail với thông báo rõ ràng nếu config là bắt buộc.
2. Có mount đúng contract: app khởi động và readiness đạt.

Không copy mọi file local vào container để chữa config missing; xác định chính xác file config phải được phát hành hoặc mount.

## 13. Kiểm external dependencies trong môi trường sạch

Một service có thể chỉ start HTTP server và vẫn chưa sẵn sàng nghiệp vụ vì database/broker chưa kết nối. Cần xác định startup contract:

| Loại test | External dependencies | Mục tiêu |
| --- | --- | --- |
| JAR smoke cơ bản | Không hoặc mock | Kiểm executable, runtime, HTTP wiring |
| Image smoke cơ bản | Không hoặc mock | Kiểm final image, entrypoint, ports, permissions |
| Integration smoke | DB/Redis/broker ephemeral | Kiểm connection/config/schema/auth |
| Deployment smoke | Test/staging services | Kiểm network, secrets, service discovery và platform |
| Production readiness | Dependencies thật theo policy | Kiểm vận hành nhưng không gây side effects |

### 13.1. Testcontainers cho database

Nếu ứng dụng cần PostgreSQL, dùng Testcontainers để tạo DB ephemeral trong integration tests thay vì dựa vào một PostgreSQL developer đã cài trên máy. Testcontainers quản lý lifecycle container test, port mapping và connection details; cần Docker daemon khả dụng.

Ví dụ dependency test (version phải được pin và tương thích với project):

~~~groovy
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
~~~

Với Maven, thêm dependencies Testcontainers có scope `test` và quản lý versions bằng BOM/versions đã được kiểm duyệt. Không để dependency version động.

Integration tests phải tạo schema/test data, kiểm app query/transaction và cleanup. Một smoke test JAR không tự tạo database. Khi chạy **final image**, cung cấp database container qua Docker network/test compose hoặc một integration environment riêng, không mount local DB state.

### 13.2. Readiness với external dependencies

Nếu DB bắt buộc để phục vụ request, có thể bổ sung custom health indicator vào readiness group. Cần cân nhắc timeout, retry, fail behavior và tránh query nặng mỗi lần probe. Liveness nên phản ánh app process, không phụ thuộc tùy tiện vào mọi dịch vụ bên ngoài để tránh restart storm.

### 13.3. Migrations

Nếu app chạy Flyway/Liquibase migrations khi startup, clean database smoke test cần tạo DB rỗng và xác minh migrations thành công. Nếu dùng database đã có schema, test riêng cả upgrade path. Đừng test migration trên production data bằng startup smoke script.

## 14. CI: build một lần, test đúng artifact đã build

Một pipeline tốt tách bước build/test artifact khỏi bước smoke test trên môi trường sạch. Job smoke nhận artifact đã upload từ job build; nó **không compile lại** rồi kiểm một file khác.

Ví dụ GitHub Actions Gradle:

~~~yaml
name: Spring Boot Artifact Smoke

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Build and unit test
        run: ./gradlew --no-daemon clean test bootJar

      - name: Upload executable JAR
        uses: actions/upload-artifact@v4
        with:
          name: smoke-app-jar
          path: build/libs/smoke-app.jar
          if-no-files-found: error

  smoke-jar:
    needs: build
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: actions/download-artifact@v4
        with:
          name: smoke-app-jar
          path: build/libs

      - name: Run executable JAR smoke test
        run: ./scripts/smoke-jar.sh
~~~

Workflow minh họa artifact handoff giữa hai job/runner. Trong production:

- Pin actions bằng full commit SHA đã review, không chỉ tag `@v4`.
- Kiểm JDK full version/vendor nếu policy yêu cầu, và ghi OS/architecture.
- Tính SHA-256 ở job build, truyền checksum cùng artifact và xác minh ở job smoke.
- Không cấp signing/publishing secrets cho job pull request không tin cậy.
- Nếu dùng Maven, đổi build command thành `./mvnw -B -ntp clean verify`, upload `target/smoke-app.jar` và download đúng path mà smoke script sử dụng.
- Nếu workflow chạy từ fork PR, hạn chế token/permissions và tránh thực thi untrusted artifact với credentials release.

### 14.1. Image CI smoke test

Khi pipeline build image bằng Buildpacks/Dockerfile, thêm job sau khi image đã được build:

1. Gắn tag có liên kết với commit/build ID.
2. Chạy `docker image inspect` để ghi image ID/architecture.
3. Chạy `scripts/smoke-image.sh` với đúng image reference.
4. Nếu push registry trước khi smoke, resolve digest và smoke đúng digest.
5. Chỉ publish/deploy digest sau khi smoke và policy gates pass.

Đối với multi-architecture image manifest list, xác định platform mà runner pull. Một test amd64 không chứng minh image arm64 cũng chạy; chạy matrix trên từng architecture được hỗ trợ hoặc có platform-specific test evidence.

### 14.2. Artifact promotion

Build once, promote same artifact/image digest qua dev → staging → production. Không rebuild lại ở từng environment nếu yêu cầu là deploy đúng bytes đã test. Thay đổi configuration/secrets theo environment thông qua runtime config, không rebuild image để chèn credentials.

## 15. Startup, readiness và graceful shutdown

### 15.1. Process started chưa chắc ready

Các trạng thái:

- JVM process đã tạo.
- Spring ApplicationContext đã refresh.
- Embedded web server đang listen.
- Readiness health group trả UP.
- Business endpoint trả kết quả đúng.
- External dependencies và migrations sẵn sàng theo contract.

Không chỉ grep log `Started ...` rồi kết luận mọi chức năng hoạt động. Log startup là tín hiệu tốt, HTTP readiness/business probe mới xác nhận đường phục vụ request.

### 15.2. Startup timeout và retry

Dùng retry có giới hạn và thời gian chờ rõ. Khi fail:

- Kiểm tra process exit code và logs.
- Kiểm cổng có bị chiếm.
- Kiểm Java version và classpath.
- Kiểm config profile/env.
- Kiểm external service DNS/port/auth/schema.
- Kiểm container exit state/OOMKilled/restart count.

Không tăng timeout từ 60 lên hàng chục phút để che deadlock, migration fail hoặc dependency outage.

### 15.3. Graceful shutdown

Spring Boot graceful shutdown cho web server có thể chờ request đang xử lý trước khi process kết thúc. Docker gửi SIGTERM khi `docker stop`, rồi sau grace period mới gửi SIGKILL. `docker stop --time 20` trong ví dụ cho container 20 giây.

Nếu dùng shell-form entrypoint, signal có thể đến shell thay vì Java process; Dockerfile nên dùng exec form:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/smoke-app.jar"]
~~~

Buildpacks launcher cũng quản lý process startup; hãy kiểm launch process thực và shutdown behavior của image. Không giả định mọi custom entrypoint chuyển signal giống nhau.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm |
| --- | --- | --- |
| `no main manifest attribute` | Plain JAR hoặc chưa repackage | Dùng Gradle `bootJar`/Maven Boot repackage, xem manifest |
| `ClassNotFoundException`/`NoClassDefFoundError` | Dependency thiếu hoặc JAR đóng gói sai | Kiểm `BOOT-INF/lib`, runtime dependency scopes |
| `UnsupportedClassVersionError` | Java runtime thấp hơn bytecode | Kiểm `java -version`, `javap -verbose`, toolchain |
| App start ở bootRun nhưng JAR fail | Classpath/config/file phụ thuộc workspace | Chạy đúng executable JAR từ temp directory |
| Port already in use | Port host/container đã bị process khác chiếm | Đổi host port, kiểm port mapping |
| Container running nhưng curl fail | App chưa ready, bind sai interface/port hoặc mapping sai | Logs, readiness endpoint, `docker port` |
| Health endpoint 404 | Actuator thiếu hoặc health probes chưa bật/expose | Dependency và management properties |
| Health endpoint 401/403 | Security policy bảo vệ endpoint | Dùng credentials nội bộ/test hoặc probe route được phép |
| Readiness 503 nhưng liveness 200 | App process còn sống nhưng chưa sẵn sàng | Xem readiness components/config/dependencies |
| JAR pass, image fail | Runtime image khác JDK/OS, permission, entrypoint | Kiểm image logs/user/env/architecture |
| Image pass trên laptop, fail CI | Host ports, Docker daemon, architecture hoặc env khác | Ghi image ID, runner details, run đúng digest |
| App cần file local không có trong JAR | External file không được package/mount | Xác định config/resource contract và test mount |
| App fail khi HOME khác | Ghi file vào user home hoặc phụ thuộc cache local | Dùng explicit writable directory/mount |
| Container exit code 137 | Có thể bị OOM kill hoặc SIGKILL | Kiểm inspect state, memory limit và logs |
| Container chạy root ngoài ý muốn | Base/Dockerfile/user config | Kiểm `docker inspect Config.User` và policy |
| Smoke script treo | Retry vô hạn/không kiểm process | Đặt timeout, check PID/container state |
| Test pass dù app sai chức năng | Chỉ gọi health endpoint | Thêm assertion vào business smoke endpoint |
| Database readiness fail | DB không có hoặc credentials/schema sai | Dùng ephemeral DB và integration tests |
| JAR checksum đổi giữa jobs | Artifact khác file hoặc transfer/packaging khác | Verify digest, truyền đúng artifact đã build |
| Test image tag nhưng deploy digest khác | Tag bị ghi đè/mutable | Verify/deploy immutable digest |
| PowerShell process không dừng | Child process hoặc event/stream handling | Đảm bảo quản lý Process, timeout và cleanup |
| Temporary files tồn đọng | Trap/finally không chạy khi runner bị kill | CI cleanup job/workspace isolation, timeout |

### 16.1. Quy trình chẩn đoán

1. Xác định chính xác JAR path/image digest đã chạy.
2. Kiểm checksum/size và JAR manifest.
3. Kiểm Java runtime, OS/architecture.
4. Chạy thủ công bằng `java -jar` hoặc `docker run` với logs.
5. Kiểm process exit, port mapping và readiness.
6. Kiểm external config/dependencies.
7. So sánh môi trường sạch với developer environment, chỉ bổ sung từng input được phép.
8. Chạy lại cùng artifact sau khi sửa, lưu digest và test evidence.

Không sửa code ứng dụng khi lỗi thực chất là đang test nhầm plain JAR, port mapping sai hoặc thiếu secret ở môi trường smoke.

## 17. Bài tập thực hành có đáp án

### Bài 1 — Vì sao không dùng bootRun?

Ứng dụng pass `./gradlew bootRun` nhưng fail khi chạy `java -jar build/libs/app.jar`. Khác biệt quan trọng là gì?

**Đáp án:** `bootRun` dùng Gradle runtime classpath và source/build outputs; `java -jar` dùng đúng executable archive và manifest/loader. JAR test phát hiện lỗi đóng gói, resource và dependency scope.

### Bài 2 — Process started nhưng readiness 503

Liveness trả 200, readiness trả 503. Có thể kết luận app crash không?

**Đáp án:** không. Process có thể còn sống nhưng chưa sẵn sàng nhận traffic, ví dụ đang chờ startup dependency hoặc health indicator. Xem readiness components và logs.

### Bài 3 — Health 200 nhưng endpoint nghiệp vụ sai

`/actuator/health/readiness` trả 200, `/smoke` trả 500. Smoke test phải kết luận gì?

**Đáp án:** fail. Health group xác nhận trạng thái theo indicators; business endpoint test xác nhận request path cụ thể.

### Bài 4 — JAR chỉ chạy khi ở project root

Nguyên nhân thường gặp?

**Đáp án:** ứng dụng phụ thuộc external config/file path tương đối có trong repository. Chạy từ temp directory và định nghĩa rõ config file phải package hay mount.

### Bài 5 — Container chạy trên laptop nhưng không ở CI

Những yếu tố cần so sánh?

**Đáp án:** image digest/architecture, Docker daemon, host port, runner permissions, external network/DNS, environment variables, secrets và memory limits.

### Bài 6 — Plain JAR

Thư mục build có `smoke-app-1.0.0.jar` và `smoke-app-1.0.0-plain.jar`. File nào nên smoke test?

**Đáp án:** executable Boot JAR được tạo bởi `bootJar`/Maven repackage, thường là file không có classifier `plain`. Cấu hình output path cố định để tránh chọn nhầm.

### Bài 7 — Không có Actuator

Nếu project không muốn thêm Actuator, có thể smoke test thế nào?

**Đáp án:** dùng business endpoint/readiness endpoint riêng đã thiết kế an toàn. Chỉ gọi endpoint không tạo side effects và kiểm status/body. Actuator probes hữu ích nhưng không bắt buộc cho mọi project.

### Bài 8 — Database cần cho startup

JAR fail readiness khi không có PostgreSQL. Đây có phải smoke test sai?

**Đáp án:** tùy contract. Nếu production bắt buộc DB thì môi trường sạch phải cung cấp DB ephemeral/test và credentials; test không có DB chỉ kiểm được startup mode không cần DB.

### Bài 9 — Read-only container fail

Ứng dụng mẫu chạy được trên image bình thường nhưng fail với `--read-only`. Điều tra gì?

**Đáp án:** xem logs và writable paths, temp directories, log files, upload/cache. Cấp tmpfs/volume đúng path với permissions tối thiểu hoặc sửa app để không ghi root filesystem vô cớ.

### Bài 10 — Build once, smoke elsewhere

CI job build JAR và upload artifact; job khác build lại JAR rồi smoke. Có đúng mục tiêu không?

**Đáp án:** không. Job smoke phải download và test **chính artifact** từ build job, xác minh checksum/digest; nếu rebuild, có thể đang kiểm bytes khác.

## 18. Checklist trước khi phát hành

- [ ] Dùng Gradle `bootJar` hoặc Maven repackage để tạo đúng executable Boot JAR.
- [ ] Chọn file artifact bằng path/tên cố định; không chọn wildcard có thể lấy plain JAR.
- [ ] Kiểm size, SHA-256, manifest và expected JAR entries.
- [ ] Chạy `java -jar` trong temporary working directory.
- [ ] Cô lập environment variables và chỉ truyền config/secrets cần thiết.
- [ ] Dùng JRE/JDK và OS/architecture đúng với môi trường deploy.
- [ ] Đặt readiness timeout, kiểm process exit và thu logs khi fail.
- [ ] Kiểm health/readiness/liveness và ít nhất một business smoke endpoint.
- [ ] Kiểm container image không mount source, build outputs hoặc local caches.
- [ ] Xác minh image ID/digest và chạy đúng image dự kiến deploy.
- [ ] Kiểm ports, entrypoint, user, permissions, tmp directories và graceful shutdown.
- [ ] Nếu có DB/broker, dùng test services ephemeral/được quản lý và integration checks.
- [ ] CI smoke job nhận đúng artifact đã build, xác minh checksum và không rebuild.
- [ ] Image smoke job kiểm đúng digest, không chỉ tag mutable.
- [ ] Dọn process/container/temp files sau cả pass lẫn fail.
- [ ] Lưu logs, build ID, artifact digest, image digest và kết quả test có thể audit.
- [ ] Không đưa secrets vào JAR/image/logs; không expose Actuator details công khai chỉ để tiện test.

**Kết luận:** `bootRun` hoặc Maven run goal chỉ cho biết ứng dụng chạy trong build environment. Release readiness cần chạy **executable JAR thật** bằng `java -jar` trong môi trường sạch và chạy **final image thật** mà không dựa vào workspace/cache của host. Kết hợp process check, readiness, business endpoint, external dependency tests, checksum/digest và cleanup để biết chính xác sản phẩm có thể khởi động và phục vụ request trong môi trường dự kiến hay không.

## 19. Tài liệu chính thức

- Spring Boot 3.3 — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Maven Plugin Repackage: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Actuator Liveness and Readiness Probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Docker Docs — Run a container: https://docs.docker.com/engine/containers/run/
- Docker Docs — Container lifecycle and logs: https://docs.docker.com/engine/containers/
- Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Testcontainers for Java — Getting Started: https://java.testcontainers.org/
- GitHub Actions — Store and share data with workflow artifacts: https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts

Các thời gian chờ, ports, image tags và runner labels trong ví dụ là giá trị của lab. Khi đưa vào CI/release, pin tool/action versions theo policy, chọn timeout dựa trên startup budget, kiểm tra đúng image digest và chỉ cấp những external configuration cần thiết.