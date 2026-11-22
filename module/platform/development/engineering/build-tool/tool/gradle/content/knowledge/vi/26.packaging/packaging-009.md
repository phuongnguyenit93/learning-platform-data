# Kết nối đóng gói container qua task hoặc plugin có phạm vi rõ ràng trong Gradle

## 1. Bài toán: từ một dự án Java đến container image

Gradle biên dịch Java, chạy test, tạo JAR và bản phân phối ứng dụng. Nhưng **container image** là một sản phẩm khác: nó chứa application files, Java runtime/base image metadata, filesystem layers, launcher, environment mặc định và cấu hình quyền chạy. Khi dự án cần đóng gói container, câu hỏi không chỉ là “gọi `docker build` ở đâu?”, mà còn là:

1. **Task nào tạo đầu vào cho container?** Java classes, JAR, distribution hay executable script?
2. **Ai thực sự xây image?** Docker CLI/BuildKit, Jib hay buildpack plugin?
3. **Task graph có đúng không?** Không được dùng JAR cũ hoặc thiếu dependency vì build chạy sai thứ tự.
4. **Phạm vi nào được phép?** Chỉ module ứng dụng cần image; `test` hoặc `build` thông thường không nên mặc nhiên đòi Docker daemon hoặc quyền push registry.
5. **Đầu ra ở đâu?** Image có thể nằm trong Docker daemon/registry, không giống file `build/libs/app.jar` mà Gradle theo dõi dễ dàng.
6. **Tính tin cậy và bảo mật ra sao?** Base image tag/digest, image labels, secrets, registry permissions, build context, vulnerabilities, user không có quyền root.
7. **CI phát hành như thế nào?** Test → build image → smoke test → inspect/scan/sign → push/deploy dưới một policy riêng.

**Trọng tâm bài:** kết nối **bước đóng gói container có phạm vi rõ ràng** với Gradle qua hai cách: dùng `Sync` + `Exec` để gọi Docker CLI, hoặc áp dụng một plugin chuyên dụng như **Jib**. Không biến mọi Gradle task thành một bước container build/push ngầm.

~~~text
Java source + resources
          |
          v
compileJava / processResources / classes
          |
          +-------> test ------------------------> CI quality gate
          |
          v
Java application distribution (installDist)
          |
          v
stageContainerContext (Sync)
          |
          v
containerBuild (Exec -> docker build)
          |
          v
Docker daemon: hello-cli:local
          |
          v
containerSmokeTest (Exec -> docker run)
          |
          v
Separate, authorized release/push step
~~~

Một hướng thay thế: Jib sẽ tạo container layers từ Gradle Java sources/classes/runtime dependencies **không cần Dockerfile**. Task `jibDockerBuild` đưa image vào local Docker daemon; `jibBuildTar` tạo TAR; `jib` đẩy image đến registry khi được gọi tường minh và có quyền.

## 2. Các khái niệm và ranh giới cần tách bạch

| Khái niệm | Quản lý gì? | Ví dụ |
| --- | --- | --- |
| Java compilation | Chuyển source thành `.class` | `compileJava` |
| Runtime classpath | Classes/resources + runtime dependencies | `sourceSets.main.runtimeClasspath` |
| JAR | Archive của classes/resources theo Java plugin | `jar` |
| Application distribution | Start scripts, app JAR và libraries | `installDist`, `distZip` |
| Docker build context | Những file Docker builder được quyền thấy | `build/container/context` |
| Dockerfile | Cách xếp các layers, base image, user, entrypoint | `src/container/Dockerfile` |
| Docker image | Tập layers và cấu hình chạy container | `hello-cli:local` |
| Container | Instance runtime từ image | `docker run --rm ...` |
| Registry | Nơi lưu/publish image theo repository/tag/digest | Registry nội bộ hoặc nhà cung cấp cloud |
| Gradle `Sync` | Staging đúng files vào thư mục riêng | `stageContainerContext` |
| Gradle `Exec` | Chạy một external process | `containerBuild` |
| Jib | Gradle plugin chuyên tạo image Java | `jibDockerBuild`, `jibBuildTar`, `jib` |
| Build Cache của Gradle | Cache outputs Gradle có model | Không đồng nhất Docker layer cache |
| Docker/BuildKit cache | Reuse các image layers/build steps | `docker build` có thể dùng layers cũ |

**Chú ý:** `docker build` làm thay đổi trạng thái Docker daemon (hoặc remote builder), không giống một Gradle task tạo file thuần túy. Đừng giả định Gradle tự biết image local `hello-cli:local` đã tồn tại, chưa bị xóa hoặc đang có digest nào, chỉ từ một chuỗi tag.

### 2.1. Ba phạm vi cần phân biệt

- **Phạm vi dự án:** build container cho module executable `:app`, không tự áp dụng plugin cho `:library` hoặc mọi subproject.
- **Phạm vi task:** chỉ khi gọi `containerBuild` hoặc `jibDockerBuild` mới thực hiện image build; lệnh `test` không phụ thuộc Docker.
- **Phạm vi hệ thống:** build local chỉ ghi vào local Docker daemon; push lên registry là bước khác, cần credentials và quyền release riêng.

Một script có cú pháp đúng nhưng vô tình đăng ký `build.dependsOn(containerPush)` ở root vẫn là **thiết kế kém** vì mỗi developer chạy `./gradlew build` có thể bị yêu cầu registry credentials hoặc thực hiện side effects không mong muốn.

## 3. Chọn công cụ phù hợp: task Exec hay plugin?

| Tình huống | Lựa chọn hợp lý | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Có Dockerfile được tổ chức quản lý | `Sync`/`Copy` + `Exec` gọi `docker build` | Dễ đọc đúng CLI/build context, dùng Dockerfile thống nhất | Cần Docker CLI + daemon/BuildKit; trách nhiệm cache/tag/security tự quản |
| Chỉ muốn containerize Java app | Jib Gradle plugin | Hiểu Java classpath, tạo layers, hỗ trợ tar/daemon/registry | Thêm plugin và metadata/config riêng; không phù hợp mọi nhu cầu hệ điều hành |
| Dự án Spring Boot đã dùng plugin Spring Boot | `bootBuildImage` | Tích hợp buildpacks và lifecycle Spring | Chỉ phù hợp khi đã có Spring Boot plugin và builder/runtime tương thích |
| Tổ chức đã dùng Cloud Native Buildpacks | Buildpack plugin/`pack`/CI pipeline | Xây image theo buildpack contracts | Builder image, network/cache/policy phải quản lý |
| Cần multi-stage Dockerfile phức tạp, native tools | Dockerfile/BuildKit | Linh hoạt từng OS package/layer | Dễ tăng build context, kích thước, bề mặt tấn công |
| Chỉ chạy Java trên máy dev | `application.run` | Không cần container | Không thử tính tương thích image/runtime |
| Chỉ đóng JAR gửi Maven repository | `jar`/publishing | Đúng mục đích thư viện | Không tạo image |
| Cần push production registry | Release pipeline/task tách biệt | Rõ quyền và audit | Cần authentication, scanning, approval/attestation |

Không có plugin nào thay thế hoàn toàn việc hiểu **base image**, **image tag/digest**, **runtime user**, **secret injection**, **network policy** và **image provenance**. Plugin chỉ giúp đóng gói đúng task model.

## 4. Thiết kế Gradle task graph có ranh giới rõ

Với hướng Dockerfile, một pipeline nhỏ nên có quan hệ:

~~~text
:compileJava
     |
     v
:classes
     |
     v
:jar -----------------------+
                            |
:startScripts --------------+
                            |
                            v
                       :installDist
                            |
                            v
                  :stageContainerContext
                            |
                            v
                      :containerBuild
                            |
                            v
                   :containerSmokeTest
~~~

Task `installDist` do Application plugin cung cấp. Nó tạo một directory có launcher scripts và runtime libraries. Task `stageContainerContext` chỉ lấy directory đó và Dockerfile, đặt vào một **build context chuyên dụng**, không copy toàn bộ source repository. Task `containerBuild` là `Exec` gọi Docker CLI.

Trong mô hình này:

- `stageContainerContext` là Gradle `Sync`, có đầu ra thư mục thật, dễ theo dõi incremental.
- `containerBuild` là external side-effect task, phải có dependency tường minh vào staging.
- `containerSmokeTest` chạy image và chỉ có nghĩa khi image build đã thành công.
- `test` độc lập với `containerBuild`, trừ khi tổ chức chọn một **release verification lifecycle** riêng có yêu cầu cả hai.
- **Không** tự nối `containerBuild` vào `build` hoặc `check` mặc định chỉ vì thấy task mới đã có.

### 4.1. Task dependency và data flow

Khi dùng `from(tasks.named("installDist"))` trong `Sync`, CopySpec lấy **task outputs** làm nguồn; Gradle có thể giữ quan hệ task producer/consumer. Với `Exec` chỉ gọi chuỗi lệnh bên ngoài, Gradle không thể suy ra dependency từ argument `"."`, nên cần:

~~~kotlin
tasks.register<Exec>("containerBuild") {
    dependsOn(stageContainerContext)
    // commandLine("docker", "build", ...)
}
~~~

Đây là **snippet giải thích**; định nghĩa `stageContainerContext` và phần chạy đầy đủ nằm ở demo sau. `mustRunAfter` không đủ vì chỉ sắp xếp nếu hai task đã ở trong graph, không buộc producer chạy.

## 5. Demo hoàn chỉnh A: Java 17 + Application plugin + Dockerfile + Exec

Demo dùng một ứng dụng CLI Java rất nhỏ. Gradle tạo distribution qua `installDist`, copy vào build context bằng `Sync`, rồi gọi Docker qua `Exec`. Bạn có thể biên dịch/chạy Java riêng ngay cả khi Docker chưa cài để phân biệt lỗi Gradle với lỗi daemon.

### 5.1. Yêu cầu môi trường

- JDK 17, Gradle Wrapper tương thích và đã được tổ chức phê duyệt.
- Docker CLI cùng **Docker Engine/daemon** hoặc backend tương thích đang chạy và user hiện tại có quyền truy cập. Trên Windows dùng Docker Desktop ở chế độ Linux containers hoặc builder Linux tương ứng.
- Có mạng để tải Java base image lần đầu, hoặc base image đã có từ mirror/cache được kiểm soát.
- Không có registry credentials cần thiết cho `docker build` local public-base demo, nhưng mạng/proxy vẫn phải hợp lệ.
- Không chạy ví dụ trên production Docker daemon khi chưa có quyền; `docker run` tạo process/container với quyền được daemon cấp.

Cấu trúc dự án:

~~~text
hello-container/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── main/java/demo/Main.java
│   └── container/Dockerfile
└── build/                      (Gradle tự tạo khi build)
    ├── install/hello-cli/...
    └── container/context/...
~~~

Không tự tạo file Wrapper giả. Dùng các file Wrapper đúng version của dự án, có checksum distribution khi policy yêu cầu.

### 5.2. settings.gradle.kts

~~~kotlin
rootProject.name = "hello-container"
~~~

### 5.3. Toàn bộ build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.Sync
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
}

group = "demo"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

application {
    mainClass.set("demo.Main")
    applicationName = "hello-cli"
}

// Chỉ thư mục này được gửi tới Docker builder.
val containerContextDir =
    layout.buildDirectory.dir("container/context")

// Chuẩn bị app distribution + Dockerfile.
// installDist là task do Application plugin tạo.
val stageContainerContext =
    tasks.register<Sync>("stageContainerContext") {
        group = "distribution"
        description = "Stage only the files required for Docker build"

        from(tasks.named("installDist")) {
            into("app")
        }
        from(layout.projectDirectory.file("src/container/Dockerfile"))

        into(containerContextDir)
    }

// Docker image là side effect của Docker daemon, không phải một
// OutputFile mà Gradle tự quản lý.
val containerBuild =
    tasks.register<Exec>("containerBuild") {
        group = "distribution"
        description = "Build local image hello-cli:local with Docker"

        dependsOn(stageContainerContext)

        workingDir = containerContextDir.get().asFile
        commandLine(
            "docker", "build",
            "--tag", "hello-cli:local",
            "."
        )
    }

// Smoke test tách riêng, chỉ chạy khi yêu cầu.
tasks.register<Exec>("containerSmokeTest") {
    group = "verification"
    description = "Run local image to check its launcher"

    dependsOn(containerBuild)
    commandLine(
        "docker", "run", "--rm",
        "hello-cli:local", "Ada"
    )
}
~~~

**Hợp đồng của từng phần:**

1. `plugins { application }` tạo `installDist`, `run`, `jar` và model source set Java.
2. `applicationName = "hello-cli"` làm launcher cài đặt có tên `hello-cli`, còn class Java là `demo.Main`.
3. `containerContextDir` là `Provider<Directory>` dưới `build`; không dùng thư mục root làm context.
4. `stageContainerContext` là `Sync`. Nó lấy outputs của `installDist` và đặt dưới `app/`; đồng thời đưa Dockerfile vào context root.
5. `from(tasks.named("installDist"))` giữ thông tin producer task khi `Sync` là task type chính thức.
6. `dependsOn(stageContainerContext)` quan trọng vì lệnh `docker build` là external command không tự mang task dependency.
7. `workingDir` của `containerBuild` là context root, nên dấu `.` trong Docker command chính là `build/container/context`.
8. `containerSmokeTest` phụ thuộc image build, gọi `docker run --rm` với argument `Ada`, nhưng không tự chạy khi gọi `build` hoặc `test`.
9. `Exec` dùng default failure behavior: nếu `docker` trả non-zero exit status, Gradle task thất bại; không bật `isIgnoreExitValue` chỉ để CI có màu xanh.
10. `Sync` sẽ làm sạch file dư trong **destination của chính task**. Vì vậy tuyệt đối không đặt `into` ở project root, home hoặc một shared directory có files của task khác.

Lưu ý: `containerContextDir.get()` ở đây chỉ resolve đường dẫn do `layout.buildDirectory` quản lý khi **cấu hình một task được yêu cầu**, không duyệt/tải file của task producer trong configuration phase. `containerBuild` không gọi `docker` khi Gradle chỉ đang đọc build script.

### 5.4. Java source: src/main/java/demo/Main.java

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "World";
        System.out.println("Hello from container, " + name + "!");
    }
}
~~~

Không dùng external dependencies, network, random hoặc đồng hồ. Đầu ra có thể xác định chính xác theo arguments.

### 5.5. Dockerfile: src/container/Dockerfile

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /opt/app

COPY app/ /opt/app/

RUN chmod +x /opt/app/bin/hello-cli

USER 10001:10001

ENTRYPOINT ["/opt/app/bin/hello-cli"]
~~~

Giải thích:

- `FROM` dùng một **Linux Java 17 JRE** có JVM đủ cho demo. Đây là **tag minh họa**, chưa pin digest nên không bảo đảm byte-for-byte reproducibility lâu dài.
- `WORKDIR /opt/app` là working directory trong container, không phải `workingDir` của Gradle Exec task.
- `COPY app/ /opt/app/` lấy **thư mục app/** trong Docker build context do Gradle stage; nó không đọc path ngoài context.
- Application plugin đã tạo `app/bin/hello-cli` và `app/lib/hello-container-1.0.0.jar`; launcher biết tìm classpath tương đối.
- `RUN chmod +x` đảm bảo launcher Unix có executable bit trong Linux image, đặc biệt hữu ích khi context được stage trên Windows.
- `USER 10001:10001` giảm quyền của process runtime so với root. Demo không cần ghi file vào image filesystem nên UID/GID numeric có thể chạy được nếu files có quyền đọc/thực thi.
- `ENTRYPOINT` gọi generated shell launcher; arguments sau image name trong `docker run` sẽ được truyền xuống Java Main.
- Không `EXPOSE` vì chương trình CLI không mở cổng mạng. Không thêm port mapping tùy tiện.
- Demo giả định base image có shell/Java đủ để chạy Gradle launcher script; khi chọn distroless image không có shell, cần thiết kế Java entrypoint khác.

**Không đặt** `RUN gradle build` trong Dockerfile của demo: Gradle đã tạo app distribution trước. Dockerfile chỉ đóng gói runtime distribution, tránh đưa Gradle Wrapper/source/compilers vào runtime image.

### 5.6. Build và chạy

Linux/macOS:

~~~bash
./gradlew -q run --args="Ada"
./gradlew stageContainerContext
./gradlew containerBuild
./gradlew containerSmokeTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q run --args="Ada"
.\gradlew.bat stageContainerContext
.\gradlew.bat containerBuild
.\gradlew.bat containerSmokeTest
~~~

**Dòng stdout do Java Main in khi truyền Ada:**

~~~text
Hello from container, Ada!
~~~

Trong `./gradlew containerBuild` và `containerSmokeTest`, console có thêm logs Gradle/Docker. Docker image name dự kiến là `hello-cli:local` nếu Docker build thành công; không có giá trị image ID/digest cố định để bịa ra.

Chạy image trực tiếp:

~~~bash
docker run --rm hello-cli:local
docker run --rm hello-cli:local Ada
~~~

Dòng do Java in khi không truyền argument:

~~~text
Hello from container, World!
~~~

Dòng do Java in khi truyền `Ada`:

~~~text
Hello from container, Ada!
~~~

Nếu đang dùng Docker Desktop Linux backend, shell launcher bên trong image chạy theo Linux, dù Gradle được gọi từ Windows PowerShell.

### 5.7. Chạy Java source độc lập bằng javac/java

Câu lệnh dưới đây **không cần Gradle, Docker hoặc thư viện ngoài JDK**, hữu ích để xác nhận app logic:

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
    -d out src/main/java/demo/Main.java
java -cp out demo.Main Ada
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src\main\java\demo\Main.java
java -cp out demo.Main Ada
~~~

Stdout Java chính xác:

~~~text
Hello from container, Ada!
~~~

Tên output giống ví dụ trong container vì nội dung Java giống nhau, **không có nghĩa** lệnh `javac/java` đã tạo container image. Nó chỉ tách biệt lỗi application code với Gradle/Docker integration.

## 6. Kiểm tra build context trước docker build

Sau khi chạy `./gradlew stageContainerContext`, cấu trúc dự kiến:

~~~text
build/container/context/
├── Dockerfile
└── app/
    ├── bin/
    │   ├── hello-cli
    │   └── hello-cli.bat
    └── lib/
        └── hello-container-1.0.0.jar
~~~

Runtime dependencies bổ sung (nếu khai báo) được Application plugin đưa vào `app/lib`. Tên JAR hoặc layout có thể thay đổi nếu project tùy biến archives/applicationDistribution.

Điểm an toàn quan trọng: Docker builder chỉ nhận context `build/container/context`, **không nhận toàn bộ thư mục dự án**. Context này không nên có:

- `.git` và lịch sử commit;
- `gradle.properties` có credentials;
- `~/.gradle`, caches, init scripts;
- `.env` chứa secrets;
- test reports/logs/source code không cần chạy;
- private keys, SSH configs, CI token files;
- artifacts cũ của job khác.

Một `.dockerignore` rất hữu ích khi build trực tiếp từ repository root. Trong mô hình **staged context**, phương án an toàn hơn là **allowlist bằng `Sync.from(...)`**: không đưa file nhạy cảm vào ngay từ đầu. Có thể thêm `.dockerignore` trong context để phòng vệ nhiều lớp, nhưng không thay thế việc giới hạn files ở nguồn.

### 6.1. Tại sao Sync thay vì Copy?

`Sync` copy files cần thiết rồi loại files dư ở destination theo semantics của nó. Điều này có ích nếu runtime dependency JAR bị loại ở lần build tiếp theo: context không giữ một JAR cũ vô tình bị đóng vào image.

`Copy` chỉ bổ sung/ghi đè, có thể để files không còn trong source tồn tại ở destination. Trong pipeline container, **stale files trong context** là một rủi ro đáng chú ý.

Tuy nhiên, `Sync` có thể **xóa files trong destination** mà nó không copy. Vì vậy, chỉ định một dedicated output directory bên trong `layout.buildDirectory` mà **duy nhất task staging quản lý**, không dùng chung với reports, user data hoặc files của CI.

### 6.2. Dockerfile luôn nhìn theo context root

Trong Dockerfile:

~~~dockerfile
COPY app/ /opt/app/
~~~

`app/` là đường dẫn tương đối với **Docker build context**, không phải project root, không phải thư mục chứa Dockerfile gốc. Nếu bạn gọi `docker build` với context `.` ở root dự án mà không stage, Dockerfile sẽ không tự thấy `app/` theo layout này.

Đây là lý do `workingDir` của Exec phải khớp với context đã chuẩn bị hoặc lệnh Docker phải truyền đúng context path.

## 7. Những lỗi wiring phổ biến giữa Gradle và Docker

| Dấu hiệu | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `COPY app/ ...` báo không tìm thấy | Docker build context thiếu `app/` | Chạy `stageContainerContext` và dùng đúng context |
| Build qua Docker trực tiếp PASS, Gradle task FAIL | Gradle Exec working directory khác | Kiểm tra `workingDir`, daemon env và CLI path |
| Gradle `containerBuild` chạy trước `installDist` | Thiếu quan hệ task producer/consumer | `Sync.from(installDist)` và `Exec.dependsOn(stage)` |
| Image có JAR cũ | Context giữ output stale, task upstream chưa chạy | Dùng `Sync` với outputs từ `installDist` |
| `docker: command not found` | Docker CLI không trên PATH | Cài/provision CLI hoặc dùng plugin/CI builder khác |
| `Cannot connect to Docker daemon` | Engine/Desktop chưa chạy, socket permission, remote context sai | Kiểm tra `docker info` và quyền daemon |
| `permission denied` chạy launcher | Unix script thiếu executable bit | `chmod +x` trong Dockerfile hoặc nguồn |
| `Unable to access jarfile` / ClassNotFound | Launcher/lib layout bị đổi hoặc runtime dependencies thiếu | Inspect `app/bin`, `app/lib`; dùng distribution đúng |
| `exec format error` | Image platform/CPU arch không tương thích | Chọn base/platform và builder phù hợp |
| `no such file or directory` dù script tồn tại | Shebang/interpreter thiếu, CRLF hoặc base distroless | Kiểm tra shell, line endings, binary architecture |
| CI image build thành công nhưng `docker run` lỗi | Java JRE, env, working dir, permissions hoặc external service sai | Smoke test image đã build, xem logs |
| `docker build` luôn chạy khi `build` | Task được mắc vào lifecycle rộng | Bỏ `build.dependsOn(containerBuild)` ngoài policy rõ |
| Docker build cache “thành công” nhưng image sai | Cache/layers/source context hoặc tag dùng nhầm | Inspect image ID/digest, context và đúng daemon |
| `Sync` xóa file ngoài ý muốn | Destination dùng chung | Dedicated build output directory, không dùng project root |

### 7.1. Lệnh chẩn đoán tương ứng

~~~bash
./gradlew stageContainerContext --dry-run
./gradlew containerBuild --dry-run
./gradlew stageContainerContext --info --console=plain

docker version
docker info
docker image inspect hello-cli:local
docker run --rm hello-cli:local Ada
~~~

`--dry-run` cho biết task graph dự kiến, không thật sự gọi Docker hoặc tạo context. `docker image inspect` trả metadata thực tế, không có stdout bất biến. Lỗi Docker daemon cần xử lý theo môi trường; thay Java source khi daemon tắt sẽ không giúp.

### 7.2. Đừng che exit code của Docker

Với `Exec`, non-zero exit code thông thường làm task Gradle FAIL. Nếu cấu hình `isIgnoreExitValue = true` một cách vô trách nhiệm, Gradle có thể báo thành công dù Docker build đã lỗi.

Khi dùng command wrapper hoặc custom task type phức tạp, phải check process exit code và bảo toàn stderr. Không dùng `try/catch` nuốt mọi lỗi để image release pipeline có màu xanh.

## 8. Exec task: điểm mạnh và giới hạn

`Exec` là task built-in chạy external process. Nó rất hợp lý khi:

- Tổ chức đã có Dockerfile/BuildKit tiêu chuẩn.
- Gradle chỉ cần điều phối **một bước tích hợp có tên rõ ràng**.
- CI có Docker CLI/builder hợp lệ.
- Không cần một plugin Java riêng để phân lớp classpath.
- Developer muốn reproduce chính xác lệnh Docker bên ngoài Gradle.

Nhưng `Exec` **không tự biết semantics của Docker image**:

1. Docker daemon có thể dùng cache riêng, không thuộc Gradle Build Cache.
2. Tag `hello-cli:local` có thể bị một process khác thay thế.
3. Image ở Docker daemon không phải một file Gradle output đã khai báo.
4. Gradle có thể rerun Exec task, còn Docker vẫn reuse layers.
5. Docker command có thể cần network, socket permission hoặc credentials không được Gradle tự provision.
6. Side effects của `docker push` không nên được gắn nhầm với task output cacheable.

**Không đánh dấu raw `Exec` build Docker image là `@CacheableTask` rồi tự tạo một output file giả để “skip” image build**, vì file giả còn đó không chứng minh Docker daemon vẫn giữ đúng image. Nếu muốn một artifact kiểm chứng được trên disk, xem `docker save` hoặc Jib `jibBuildTar` và quản lý outputs/provenance theo mô hình có thể kiểm tra.

### 8.1. Tắt container build trong build task thông thường

Một anti-pattern:

~~~kotlin
// KHONG NEN neu moi build/test deu phai can Docker/registry:
tasks.named("build") {
    dependsOn("containerBuild")
}
~~~

Nó buộc lệnh `./gradlew build` tại mọi developer workstation yêu cầu Docker daemon. Nếu containerBuild còn gọi push, mọi developer có thể cần registry credentials.

Chỉ khi **policy cụ thể** yêu cầu build thông thường luôn tạo image mới, mới nên nối lifecycle. Phương án an toàn hơn: tạo task `containerBuild` và một CI job gọi **tường minh** sau khi tests đã PASS.

## 9. Demo hoàn chỉnh B: Jib Gradle plugin, không cần Dockerfile

Nếu mục tiêu là một **Java application** và không cần OS packages/custom Dockerfile phức tạp, **Jib** là lựa chọn đáng cân nhắc. Jib đọc Java classes/resources/runtime dependencies và tạo container layers, thường phân tầng dependency/class files để giảm công việc khi chỉ thay source code.

Theo Gradle Plugin Portal tháng 11/2026, plugin ID là `com.google.cloud.tools.jib` và phiên bản phát hành mới được xác nhận trong bài là **3.5.4** (phát hành 14/07/2026). Đối với dự án thực tế, pin phiên bản được tổ chức phê duyệt và kiểm tra compatibility với Gradle Wrapper/JDK; không nhầm plugin version với Java version.

**Hướng Jib là phương án THAY THẾ cho hướng Dockerfile/Exec.** Đừng paste cả hai configurations vào một project rồi buộc chúng tự chạy cùng nhau, trừ khi bạn chủ động duy trì hai pipeline độc lập.

### 9.1. Project Java dùng Kotlin DSL và Jib

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "hello-jib"
~~~

`build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
    id("com.google.cloud.tools.jib") version "3.5.4"
}

group = "demo"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

application {
    mainClass.set("demo.Main")
}

jib {
    from {
        image = "eclipse-temurin:17-jre"
    }
    to {
        image = "hello-cli:jib-local"
    }
    container {
        mainClass = "demo.Main"
        user = "10001:10001"
        jvmFlags = listOf("-Dfile.encoding=UTF-8")
    }
}
~~~

`src/main/java/demo/Main.java` chính là file Java đã khai báo ở **mục 5.4**, không phải một class khác. Jib dùng cùng logic Java Main nhưng cách tạo image **không cần `installDist` hoặc `Dockerfile`**. `container.mainClass` được set tường minh để tránh mơ hồ khi project có nhiều main methods.

### 9.2. Các task Jib và điều kiện chạy

| Task | Sản phẩm/side effect | Docker daemon? |
| --- | --- | --- |
| `jibDockerBuild` | Đưa image tới local Docker daemon | **Cần** daemon/client phù hợp |
| `jibBuildTar` | Tạo image TAR trên disk (thường `build/jib-image.tar`) | **Không cần** Docker daemon để tạo TAR |
| `jib` | Build và push image đến container registry | **Không cần** Docker daemon; **cần registry/network/credentials** |
| `run` | Chạy Java app trong môi trường Gradle | Không cần daemon |
| `build` | Build/test thông thường | Không tự chạy Jib tasks nếu không nối lifecycle |

Chạy local image:

~~~bash
./gradlew jibDockerBuild
docker run --rm hello-cli:jib-local Ada
~~~

Java Main dự kiến in:

~~~text
Hello from container, Ada!
~~~

Nếu không có Docker daemon, có thể tạo TAR:

~~~bash
./gradlew jibBuildTar
~~~

Khi muốn tải TAR vào Docker daemon ở một bước riêng:

~~~bash
docker load --input build/jib-image.tar
~~~

**Không** coi `jibBuildTar` là lệnh push registry. Task `jib` chỉ nên được gọi tại bước release được cấp quyền. Nếu registry target chưa được cấu hình phù hợp, Gradle/Jib có thể yêu cầu image name/credentials và thất bại — không tự suy một repository hợp lệ.

### 9.3. Ưu điểm về layers

Jib có thể tách dependency JARs và classes/resources thành các layers khác nhau. Khi chỉ thay Java source, các dependency layers không nhất thiết phải rebuild; cache behavior còn phụ thuộc metadata, base image và phiên bản plugin.

Jib mặc định cố gắng tạo images tái lập bằng timestamps ổn định (epoch-based). Nhưng **base image tag vẫn có thể đổi** và các đầu vào khác cũng cần khóa/xác minh để đạt reproducibility thật sự. Jib cung cấp image digest/image ID outputs, thường dưới `build/jib-image.digest` và `build/jib-image.id` theo tài liệu.

### 9.4. Không dùng Jib như một lệnh chạy Dockerfile

Jib và `docker build` là **hai cách đóng gói khác nhau**. Jib không đọc Dockerfile ở mục 5 khi tạo layers Java theo cơ chế riêng. Nếu bắt buộc cài OS packages hay có multi-stage Dockerfile phức tạp, dùng Dockerfile/BuildKit hoặc extension chuyên dụng đã được đánh giá.

Cũng không giả định Jib luôn tự biết JVM main class chính xác: có thể infer trong một số dự án nhưng với nhiều main classes, cấu hình `jib.container.mainClass` rõ ràng là an toàn hơn.

## 10. Groovy DSL tương đương

### 10.1. Docker CLI/Exec với Groovy DSL

Giả sử Application plugin đã được áp dụng, Groovy build script có thể wiring các tasks tương đương:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.Main'
    applicationName = 'hello-cli'
}

def contextDir = layout.buildDirectory.dir('container/context')

def stageContainerContext = tasks.register('stageContainerContext', Sync) {
    from(tasks.named('installDist')) {
        into 'app'
    }
    from layout.projectDirectory.file('src/container/Dockerfile')
    into contextDir
}

tasks.register('containerBuild', Exec) {
    dependsOn stageContainerContext
    workingDir = contextDir.get().asFile
    commandLine 'docker', 'build', '--tag', 'hello-cli:local', '.'
}
~~~

Đây là **bộ khung Groovy DSL có nhiệm vụ tương đương**, để chạy cần cùng `settings.gradle`, `Main.java`, Dockerfile, JDK và Docker Engine như demo A. Không trộn Groovy syntax `id 'application'` trong `build.gradle.kts`.

### 10.2. Jib với Groovy DSL

~~~groovy
plugins {
    id 'application'
    id 'com.google.cloud.tools.jib' version '3.5.4'
}

application {
    mainClass = 'demo.Main'
}

jib {
    from {
        image = 'eclipse-temurin:17-jre'
    }
    to {
        image = 'hello-cli:jib-local'
    }
    container {
        mainClass = 'demo.Main'
        user = '10001:10001'
    }
}
~~~

Đây là phương án **thay thế** với plugin Jib. Nếu dùng Groovy demo cho Java 17, cần phần toolchain/encoding tương tự Kotlin DSL (hoặc dùng JDK build thích hợp), chứ không chỉ copy từng snippet rồi xem như cấu hình production hoàn chỉnh.

## 11. Multi-project: chỉ module executable tạo image

Giả sử repository gồm:

~~~text
workspace/
├── settings.gradle.kts
├── api/
│   └── build.gradle.kts
├── core/
│   └── build.gradle.kts
└── app/
    ├── build.gradle.kts
    └── src/container/Dockerfile
~~~

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "workspace"
include(":api", ":core", ":app")
~~~

`app/build.gradle.kts` có thể viết:

~~~kotlin
plugins {
    application
}

dependencies {
    implementation(project(":core"))
    implementation(project(":api"))
}

application {
    mainClass.set("com.example.app.Main")
}
~~~

Sau đó đặt **container staging/Exec tasks chỉ trong module `:app`**, tương tự demo A. Những code snippets trên chỉ là phần dependency/plugin setup, không phải ứng dụng runnable khi chưa có `com.example.app.Main` và source từ các modules liên quan.

Lệnh:

~~~bash
./gradlew :app:run
./gradlew :app:containerBuild
./gradlew :app:containerSmokeTest
~~~

Java plugin và project dependency model nối `:app` với `:core`/`:api`. Không viết:

~~~kotlin
// ANTI-PATTERN neu moi subproject deu bi ep tao image.
subprojects {
    apply(plugin = "com.google.cloud.tools.jib")
}
~~~

Vì module `:core` có thể là library không có main method. Nếu chỉ ứng dụng cần image, apply Jib **chỉ ở `:app`**, hoặc dùng convention plugin có điều kiện rõ và được áp dụng tường minh tại modules executable.

### 11.1. Convention plugins có ích khi nào?

Khi tổ chức có nhiều microservices cùng cần policy container (base image, labels, non-root, registry, scanning), nên tạo một **convention plugin** cung cấp Gradle task/configuration thống nhất. Các ứng dụng apply plugin đó tường minh, thay vì copy/paste arbitrary `allprojects` blocks.

Convention plugin cần:

- task names không xung đột;
- properties cho image repo/tag/platform;
- output providers cho staging artifacts;
- clear separation giữa build local, publish và deploy;
- validation của registry/tag input và không lộ credentials;
- compatibility với Gradle Configuration Cache khi có thể;
- test cho plugin ở sample consumer projects.

**Không** tạo một plugin nội bộ chỉ để wrap một dòng `docker build` nếu dự án đơn rất nhỏ; có thể giữ `Exec` task rõ ràng. Tăng abstraction khi nó thực sự loại bỏ duplication và enforce policy.

## 12. Phân biệt local build, push và deploy

| Hành động | Lệnh ví dụ | Side effect | Rủi ro |
| --- | --- | --- | --- |
| Compile/test | `./gradlew test` | Output Gradle | Tests không đáng tin, thiếu dependencies |
| Docker build local | `./gradlew containerBuild` | Image trong local daemon | Docker socket và base image trust |
| Jib local | `./gradlew jibDockerBuild` | Image trong daemon | Cần daemon |
| Jib image TAR | `./gradlew jibBuildTar` | `build/jib-image.tar` | Artifact chứa code/deps, phải kiểm soát truy cập |
| Image smoke test | `docker run --rm ...` | Container process | Side effects của app |
| Push | `docker push ...` hoặc `./gradlew jib` | Image trên registry | Credentials, overwrite tag, audit |
| Deploy | Tool Kubernetes/Cloud/Helm/CI riêng | Hệ thống đang chạy thay đổi | Rollout/rollback, quyền production |

**Build không phải deploy.** Đừng cho rằng image xây xong là được publish/triển khai. Registry và production cần giai đoạn phê duyệt, scan/sign, policy kiểm soát và có thể tách thành một job với credentials khác.

### 12.1. Vì sao image tag không đủ?

Một tag như `hello-cli:local` hoặc `service:latest` là **con trỏ có thể thay đổi**. Hai lệnh build có cùng tag không bảo đảm cùng digest. Với CI nên dùng tag bất biến gắn commit SHA/version build, ví dụ:

~~~text
registry.example.com/team/hello-cli:<commit-sha>
~~~

Đây là **mẫu đặt tên**, không phải lệnh push và không phải digest thật. Trong môi trường production, sử dụng image **digest** ở deployment reference khi policy yêu cầu pin chính xác bytes. Image digest chỉ được lấy từ **image đã build/push thật**, không bịa một hash trông có vẻ hợp lệ.

### 12.2. Base image tag cũng có thể thay đổi

Dockerfile demo dùng `eclipse-temurin:17-jre` vì dễ học, nhưng tag này có thể được nhà cung cấp cập nhật. Khi cần reproducibility/chứng minh provenance, pin base image theo digest được xác minh:

~~~dockerfile
# Minh hoa DINH DANG, khong phai digest thuc:
# FROM eclipse-temurin:17-jre@sha256:<trusted-digest>
FROM eclipse-temurin:17-jre
~~~

**Không copy dòng có `<trusted-digest>` thành Dockerfile thật**; đó chỉ là format. Hãy lấy digest từ registry đáng tin, quản lý cập nhật để tiếp tục nhận security patches và kiểm tra vulnerability scan.

## 13. Security: giới hạn context, secrets, runtime quyền thấp

### 13.1. Docker daemon socket là quyền mạnh

Truy cập Docker daemon trên một máy thường cấp khả năng ảnh hưởng sâu tới host/container runtime; không cho untrusted PR jobs dùng privileged Docker daemon có secrets hoặc quyền production. Trong CI, sử dụng runners/builders tách biệt và quyền tối thiểu.

### 13.2. Không đưa secrets vào Docker image layers

Không dùng:

~~~dockerfile
# KHONG AN TOAN de dua token vao image.
ARG API_TOKEN
ENV API_TOKEN=some-private-token
RUN echo "$API_TOKEN" > /opt/app/token.txt
~~~

`ARG`/`ENV` hoặc nội dung file có thể lộ qua image metadata/layers/build logs/cache. Với build-time secrets, dùng **BuildKit secret mounts** hoặc cơ chế registry/cloud secret phù hợp, truyền trên CI được cấp quyền; không dùng build arguments để giấu credentials. Với runtime secrets, inject khi deploy qua secret manager, không đóng gói vào image.

Khi dùng Jib, tương tự không viết username/password vào `jib.to.auth` trong source hoặc Gradle logs. Dùng credential helpers/CI service accounts và các phương thức authentication được plugin hỗ trợ, không in token hay đẩy image sang registry lạ.

### 13.3. Bảo vệ container runtime

- Chạy dưới UID/GID không phải root khi image/app hỗ trợ.
- Chỉ cấp file permissions cần thiết.
- Không để JVM ghi vào source/image layer read-only; dùng writable volumes/temp theo policy.
- Không `EXPOSE`/publish port nếu ứng dụng CLI không cần.
- Không add OS packages/compiler/build tools vào runtime image nếu không dùng.
- Chỉ chọn base image từ trusted registry và có vulnerability patch policy.
- Chạy image scanner/provenance/signing theo release pipeline đã được phê duyệt.
- Nếu chạy service, cấu hình health checks và graceful shutdown theo ứng dụng cụ thể.

### 13.4. .dockerignore không phải mật mã bảo vệ

Một Dockerfile có thể nhận toàn bộ build context mà CLI gửi. `.dockerignore` giúp loại files không cần, nhưng **không thay thế** việc tạo context allowlist từ staged artifacts. Trong demo, Gradle staging chỉ copy app distribution và Dockerfile; không đưa cả repository root vào Docker builder.

Nếu dùng direct root context (một phương án khác), review `.dockerignore` để loại `.git`, `.gradle`, build reports, `.env`, credentials, private keys và files không cần, nhưng phải bảo đảm **không loại chính artifacts sẽ COPY**.

## 14. Gradle Build Cache, Docker cache và Jib cache

Ba lớp cache tách biệt:

| Cơ chế | Đầu vào/đầu ra | Khi nào có ích |
| --- | --- | --- |
| Gradle incremental/Build Cache | Inputs/outputs của `compileJava`, `jar`, `installDist`, `Sync` khi đủ điều kiện | Không rebuild Java artifacts/staging không đổi |
| Docker/BuildKit layer cache | Dockerfile instruction, build context contents/metadata, base image | Reuse layers khi không cần build lại |
| Jib layer/cache | Java classes/resources/dependencies, base layers và Jib metadata | Tách dependency layer khỏi frequently changed source |

**Cấm suy luận sai:** nếu `:containerBuild` được chạy lại, không có nghĩa Docker phải rebuild toàn bộ layers; Docker builder có thể cache. Ngược lại, Gradle `UP-TO-DATE` cho `stageContainerContext` không bảo đảm image trong daemon tồn tại.

### 14.1. Không lạm dụng outputs giả

Đừng khai báo:

~~~kotlin
// ANTI-PATTERN: file gia khong chung minh image ton tai.
tasks.register("fakeDockerBuild") {
    outputs.file(layout.buildDirectory.file("image-built.flag"))
    doLast {
        // Chua thuc su build image hoac doi chieu daemon state.
    }
}
~~~

Nếu flag file còn, Gradle có thể skip task, trong khi Docker daemon bị xóa image hoặc tag đã trỏ tới thứ khác. Một container build task làm side effect phải được quản lý đúng loại công việc. Khi cần artifact file thật, xuất image TAR và công bố output/archive digest.

### 14.2. Image reproducibility

Để so image digests có ý nghĩa, cần kiểm soát:

- Java/Gradle Wrapper/toolchains.
- Runtime dependencies/plugins và verified checksums.
- Base image digest/platform.
- Dockerfile/Jib configuration, entrypoint, environment, UID/GID.
- Archive timestamps/order/permissions.
- Build arguments, source version, labels, creation time và tool version.
- Registry/mirror, builder platform và compression/media format.

Hai images chạy giống nhau **không nhất thiết có cùng digest** nếu metadata/layers/timestamps khác. Jib có hỗ trợ timestamps ổn định; Docker BuildKit có các cơ chế reproducible build nhưng không có phép màu nào bảo đảm mọi external input đã pin.

## 15. Multi-platform containers: khác biệt giữa build và run

Một image cho `linux/amd64` có thể không chạy native trên `linux/arm64`, trừ khi base image có architecture thích hợp hoặc emulator được cấu hình. Error thường gặp:

~~~text
exec format error
~~~

Với Docker Buildx, CI có thể tạo multi-platform image bằng công cụ phù hợp:

~~~bash
docker buildx version
docker buildx ls
~~~

Tùy builder/multi-platform support, `docker buildx build` có `--platform` và các tùy chọn export/push. **Không tự thêm `--push` vào Gradle `containerBuild` local**: registry publication là hành động khác với credentials/audit. Phải kiểm tra base image có variants cho mọi architecture, và JVM native libraries/OS dependencies tương thích.

Với Jib, một số phiên bản có cơ chế lựa chọn base platforms; hãy kiểm tra version/docs cụ thể, không giả định mọi cấu hình tự tạo image multi-arch.

## 16. Chạy image và verify runtime thay vì chỉ xem BUILD SUCCESSFUL

Sau khi container build:

~~~bash
docker image inspect hello-cli:local
docker run --rm hello-cli:local Ada
~~~

Với demo, application in:

~~~text
Hello from container, Ada!
~~~

Nhưng một smoke test production nên kiểm tra rộng hơn:

1. Java version thực tế trong image có phù hợp class file major version không?
2. Classpath và runtime dependency JARs có đủ?
3. User không-root đọc/ghi được đúng directories cần?
4. Configuration được inject ở runtime chứ không hardcode trong image?
5. Service startup/health readiness có đúng điều kiện?
6. Container dừng đúng exit code và giải phóng tài nguyên?
7. External services được mock/isolated hoặc test instance riêng?
8. OCI image metadata, digest, provenance, SBOM/scan records có được lưu theo policy?

**Không dùng image build success như bằng chứng app đúng.** Dockerfile có thể build thành công dù ENTRYPOINT path sai; smoke test sẽ bắt được.

### 16.1. Khi muốn CI test trước image build

CI có thể gọi:

~~~bash
./gradlew clean test
./gradlew containerBuild
./gradlew containerSmokeTest
~~~

Đây là workflow minh họa cho dự án đơn. Nếu `test` fail, CI nên dừng stage trước khi build image theo policy. Không cần viết `containerBuild.dependsOn(test)` trong mọi môi trường nếu pipeline đã điều phối quality gates rõ ràng. Nếu tổ chức muốn guarantee ngay trong task graph cho một release target, có thể tạo một lifecycle task riêng, **không tác động tới `build` mặc định**.

## 17. Thiết kế một release task có chủ đích

Có thể tạo một task tổng hợp rõ ràng chỉ dùng khi CI gọi:

~~~kotlin
tasks.register("verifyContainerRelease") {
    group = "verification"
    description = "Run tests and verify the locally built image"
    dependsOn("test", "containerSmokeTest")
}
~~~

**Đây là snippet bổ sung cho demo A.** Nó đưa cả `test` và `containerSmokeTest` vào graph, nhưng Gradle không bảo đảm `test` phải hoàn tất **trước** `containerBuild` nếu hai branches độc lập. Nếu policy thực sự yêu cầu tests PASS trước khi Docker build, hãy:

- Dùng hai stage CI tuần tự, stage test fail thì không chạy stage image; **hoặc**
- Khai báo một dependency graph rõ ràng trong một task chuyên dùng cho release, ví dụ `containerBuild.dependsOn("test")` trong module/release configuration phù hợp.

Đừng dùng `mustRunAfter` để thay cho một gate cần buộc chạy: nó chỉ định thứ tự khi cả hai tasks đã có trong graph, không tự schedule test.

### 17.1. Các task quyền cao chỉ chạy khi được yêu cầu

- `containerBuild`: chỉ tạo local image.
- `containerSmokeTest`: chạy local image/assumptions.
- `containerPush` hoặc `jib`: chỉ ở release stage có quyền registry.
- `containerDeploy`: chỉ ở deployment stage đã được phê duyệt.

Tách task names theo verbs là một cách bảo vệ developer khỏi những tác dụng phụ bất ngờ của lifecycle.

## 18. Khi dùng Buildpacks hoặc Spring Boot thay vì Jib/Dockerfile

Một dự án Spring Boot đã áp dụng plugin Spring Boot có thể được cấp task `bootBuildImage` (tùy plugin version). Nó dùng buildpacks để containerize executable application và một builder phù hợp.

**Không viết `tasks.named("bootBuildImage")` trong dự án chỉ có Java/Application plugin**, vì task đó không tồn tại. Cần:

1. Plugin Spring Boot đúng version đã áp dụng.
2. Compatible boot artifact và builder image.
3. Docker/buildpack daemon hoặc remote builder theo plugin requirements.
4. Runtime metadata/base image policy và target image tagging.
5. Quản lý buildpack/env variables không chứa secrets.
6. CI workflow scan/sign/push riêng.

Buildpacks phù hợp khi tổ chức quản lý builder stacks và muốn tránh viết Dockerfile; Jib phù hợp với Java classpath layers; Dockerfile phù hợp khi cần toàn quyền quyết định filesystem/runtime. **Chọn một primary path có chủ đích** để giảm duplicate image behaviors.

## 19. Container artifact và Gradle publication là hai hệ khác nhau

`maven-publish` dùng cho Maven artifacts như JAR/POM/Gradle Module Metadata; registry OCI dùng image manifest/layers/digests. Việc `publish` JAR đến Maven không tự push image.

Trong CI:

~~~text
Java source
   |
   +--> test/check
   |
   +--> jar/distribution
             |
             +--> container image
                        |
                        +--> scan/SBOM/sign
                                   |
                                   +--> registry push
                                               |
                                               +--> deployment
~~~

Mỗi bước có artifact/provenance/permission riêng. Không suy “JAR upload thành công” đồng nghĩa registry image đã cập nhật, hoặc container image build thành công đồng nghĩa Maven publication đã có.

Nếu artifact signing/attestations cần dùng, tránh tự log private keys. Dùng OCI-aware tooling được tổ chức cho phép, policy scan và identity-based auth nơi có thể.

## 20. Multi-module và convention plugin: các lỗi thường gặp

| Vấn đề | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| Mỗi subproject đều có `containerBuild` | Apply container plugin trong `allprojects` | Chỉ apply ở executable module |
| Image chứa code module library thiếu | App chưa khai báo project dependency | `implementation(project(":core"))` tại app |
| Consumer đọc đường dẫn `../lib/build/libs/*.jar` | Hardcode output của project khác | Dùng Gradle dependency/artifact providers |
| Task `build` bị chậm vì Docker | Tự nối lifecycle root | Tách container tasks và CI stage |
| Jib mainClass infer sai | Nhiều entry points, plugin khác | Set `jib.container.mainClass` |
| Docker image tag bị overwrite giữa jobs | Dùng cùng `:latest`/`:local` trong shared daemon | Per-commit tag, isolated builder/namespace |
| Docker build trên Windows nhưng image Linux lỗi | Shell/permissions/CRLF/cross-platform | Kiểm tra Linux Docker backend và launcher |
| Registry push đòi password local | Push nối nhầm vào build | Tách publish job và secret scope |
| Generated context thiếu dependency JAR | Dùng `jar` thay vì `installDist` | Dùng distribution hoặc Jib runtime classpath |
| Two tasks ghi cùng Docker context | Overlapping outputs | Một Sync task sở hữu destination |
| CI dùng Docker daemon của host không tin cậy | Socket quá nhiều quyền | Dedicated isolated builder |
| Container chỉ chạy bằng root | Dockerfile/base mặc định | Chọn non-root UID/GID và kiểm tra filesystem |

### 20.1. Library module không cần image

Một library Gradle module tạo JAR được các apps sử dụng. Nó **không có một main class** để trực tiếp chạy trong container. Không auto-apply Jib cho mọi module thư viện; khi đó Jib có thể không biết entrypoint hoặc tạo image vô nghĩa. Chỉ những modules thực sự là deployable app/service mới nên có container packaging config.

### 20.2. Lỗi duplicate Docker output trong concurrent builds

Hai Gradle builds hoặc CI jobs cùng dùng Docker daemon chung và tag `hello-cli:local` có thể ghi đè lên nhau. Workspaces khác nhau vẫn không giúp nếu **daemon image tag** chung.

Giải pháp: per-run/per-commit unique tags, isolated Docker contexts/builders, và không dựa vào image tag shared để làm một phép kiểm thử security/reproducibility. Với release, xác định digest và push registry theo staging/prod policy.

## 21. Bài tập thực hành có đáp án

**Bài 1 — Phân biệt artifact.** `./gradlew jar` đã tạo JAR. Có nghĩa Docker image tự xuất hiện không?  
**Đáp án:** không. Container image cần Docker/Jib/buildpack stage riêng.

**Bài 2 — Lựa chọn task.** Dự án đã có Dockerfile và Docker daemon trong CI. Có thể dùng task Gradle nào để gọi Docker?  
**Đáp án:** `Exec`, với `commandLine("docker", "build", ...)` và task dependencies chính xác.

**Bài 3 — Phạm vi.** Một multi-project có `:core` library và `:app` executable. Module nào nên cấu hình `containerBuild`?  
**Đáp án:** `:app`, không phải mọi subproject.

**Bài 4 — Input của image.** Vì sao demo dùng `installDist` thay vì chỉ `jar`?  
**Đáp án:** distribution có launcher scripts, JAR ứng dụng và runtime dependencies, phù hợp đóng gói CLI.

**Bài 5 — Context.** Dockerfile có `COPY app/ /opt/app/`. `app/` đến từ đâu?  
**Đáp án:** từ `build/container/context/app` do Sync stage; Docker builder nhìn đường dẫn tương đối theo context root.

**Bài 6 — Thứ tự.** `containerBuild` chỉ có `mustRunAfter(stageContainerContext)`. Có đủ để stage luôn chạy không?  
**Đáp án:** không; cần `dependsOn(stageContainerContext)` vì Docker CLI không có provider provenance tự động.

**Bài 7 — Runtime output.** Chạy `docker run --rm hello-cli:local Ada` với demo Java thì in gì?  
**Đáp án:** `Hello from container, Ada!`.

**Bài 8 — Chưa có Docker.** Có thể kiểm tra Java Main bằng công cụ gì?  
**Đáp án:** `javac --release 17` và `java -cp ... demo.Main`; đây không kiểm tra image.

**Bài 9 — Docker daemon.** `jibDockerBuild` có cần local daemon không?  
**Đáp án:** có, cần Docker daemon/client phù hợp.

**Bài 10 — Jib TAR.** `jibBuildTar` tạo gì?  
**Đáp án:** image TAR, thường `build/jib-image.tar`, không cần Docker daemon để tạo TAR.

**Bài 11 — Registry.** Task Jib nào push image tới registry?  
**Đáp án:** `jib`, cần target registry/credentials phù hợp; không nên chạy ngầm cùng `build`.

**Bài 12 — Local image ID.** Có thể ghi sẵn image digest “chắc chắn đúng” vào README mà chưa build không?  
**Đáp án:** không. Digest phải lấy từ image thực tế và được xác minh.

**Bài 13 — Tag.** Dùng `latest` có bảo đảm reproducible image không?  
**Đáp án:** không; tag có thể thay đổi. Pin base image digest và theo dõi output digest khi cần.

**Bài 14 — Security.** Vì sao không dùng `ARG PASSWORD` để nhúng secret vào Docker image?  
**Đáp án:** có thể lộ trong layers/metadata/logs/cache; dùng BuildKit secrets hoặc secret injection được kiểm soát.

**Bài 15 — Least privilege.** Dockerfile demo dùng `USER 10001:10001` để làm gì?  
**Đáp án:** chạy JVM dưới UID/GID không phải root khi filesystem/ứng dụng cho phép.

**Bài 16 — Cache.** Gradle `stageContainerContext` UP-TO-DATE có chứng minh Docker image vẫn có trong daemon không?  
**Đáp án:** không. Stage output là files; daemon image là trạng thái khác.

**Bài 17 — Sync.** Có nên để `stageContainerContext` ghi vào thư mục root có mã nguồn và dữ liệu user không?  
**Đáp án:** không; Sync có thể xóa files dư. Dùng dedicated build directory.

**Bài 18 — Build.** Có nên gắn `build.dependsOn(containerBuild)` vô điều kiện cho mọi developer?  
**Đáp án:** thường không; điều này biến Docker thành phụ thuộc của toàn bộ build dù không phải ai cũng cần image.

**Bài 19 — Spring Boot.** Một Java project không áp dụng Spring Boot plugin có tự có `bootBuildImage` không?  
**Đáp án:** không. Task thuộc integration của Spring Boot plugin.

**Bài 20 — Jib scope.** Một library module không có main class có nên áp dụng Jib mặc định không?  
**Đáp án:** không; cần container executable entry point, không auto-apply trên toàn bộ modules.

**Bài 21 — CI.** Image build thành công nhưng `docker run` fail. Có thể kết luận task Gradle compile lỗi không?  
**Đáp án:** chưa; inspect ENTRYPOINT, launcher permissions, classpath, runtime Java, env và runtime service dependencies.

**Bài 22 — Docker context.** Ưu điểm của staged context so với `docker build .` tại repository root?  
**Đáp án:** chỉ gửi artifacts và Dockerfile cần thiết, giảm nguy cơ leak secrets/source/logs và giảm build context size.

**Bài 23 — Smoke test.** Có thể gọi trực tiếp task nào trong demo A để build rồi chạy kiểm tra?  
**Đáp án:** `./gradlew containerSmokeTest`; dependency graph yêu cầu `containerBuild` và staging trước.

**Bài 24 — CI gate.** Một lifecycle task phụ thuộc `test` và `containerBuild` có bảo đảm test PASS xong mới build image không?  
**Đáp án:** không tự bảo đảm, vì Gradle có thể thực thi hai branches độc lập song song. Dùng CI stages tuần tự hoặc dependency graph tường minh.

**Bài 25 — Publication.** Maven `publish` có đẩy OCI image lên registry không?  
**Đáp án:** không; Maven artifacts và OCI images có publication model khác nhau.

## 22. Checklist chuẩn bị container pipeline

- [ ] Dự án có executable entry point, không phải chỉ library?
- [ ] Đã chọn đúng một primary path: Dockerfile/Exec, Jib hoặc buildpack?
- [ ] `containerBuild`/Jib plugin chỉ áp dụng ở module deployable?
- [ ] Container tasks có tên và group rõ, không tự nối mọi `build`/`test`?
- [ ] Source app/dist/JAR đã được tạo trước khi Docker/Jib tiêu thụ?
- [ ] Có TaskProvider/output provenance hoặc `dependsOn` chính xác?
- [ ] Docker build context chỉ có những files cần thiết, không leak `.git`/secrets?
- [ ] Nếu dùng Sync, destination là directory chỉ task đó sở hữu?
- [ ] Docker CLI/daemon hoặc Jib plugin/registry prerequisites được kiểm tra?
- [ ] Java runtime trong base image đủ version cho bytecode ứng dụng?
- [ ] Với app có runtime dependencies, launcher/classpath đã đầy đủ?
- [ ] ENTRYPOINT chạy được và container smoke test kiểm tra output/exit code?
- [ ] Container chạy non-root theo khả năng filesystem/ứng dụng?
- [ ] Base image tag/digest và policy security updates được xác định?
- [ ] Không đưa credentials vào Dockerfile ARG/ENV, image layers hoặc Gradle logs?
- [ ] Local build, image push và deploy là các bước có quyền tách biệt?
- [ ] Registry target, tag, digest và release provenance được ghi rõ?
- [ ] Không dùng image tag shared giữa concurrent CI jobs?
- [ ] Đã kiểm tra Docker/BuildKit cache khác Gradle Build Cache?
- [ ] Nếu dùng Jib, phân biệt `jibDockerBuild`/`jibBuildTar`/`jib`?
- [ ] Nếu dùng buildpack, plugin/builder/runtime policy là điều kiện riêng?
- [ ] Multi-platform image chỉ xuất khi builder/base image hỗ trợ?
- [ ] CI quality gate kiểm tra test và image trước authorized publish?
- [ ] Có kế hoạch image vulnerability scan/SBOM/signing/rollback phù hợp?

## 23. Tài liệu chính thức

- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, `installDist`, `startScripts`, runtime distribution.
- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): `Sync`, `CopySpec.from(TaskProvider)`, build directory và task outputs.
- [Gradle — Exec task DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.Exec.html): `commandLine`, `workingDir`, exit behavior.
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): `dependsOn` vs `mustRunAfter`, task graph.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `TaskProvider` và lazy configuration.
- [Gradle Plugin Portal — Jib](https://plugins.gradle.org/plugin/com.google.cloud.tools.jib): plugin ID, version 3.5.4 (2026).
- [Jib Gradle Plugin — README](https://github.com/GoogleContainerTools/jib/blob/master/jib-gradle-plugin/README.md): `jib`, `jibDockerBuild`, `jibBuildTar`, image config và layers.
- [Jib — FAQ](https://github.com/GoogleContainerTools/jib/blob/master/docs/faq.md): Docker daemon, tar, entrypoint và troubleshooting.
- [Docker Docs — Build Context](https://docs.docker.com/build/concepts/context/): ý nghĩa context, file visibility và `.dockerignore`.
- [Docker Docs — Dockerfile Reference](https://docs.docker.com/reference/dockerfile/): `FROM`, `COPY`, `RUN`, `USER`, `ENTRYPOINT`.
- [Docker Docs — Build Best Practices](https://docs.docker.com/build/building/best-practices/): pin base image digest, giảm context, cache và cập nhật bảo mật.
- [Docker Docs — Build Secrets](https://docs.docker.com/build/building/secrets/): BuildKit secret mounts thay cho secrets trong `ARG`/`ENV`.
- [Docker Docs — Cache Optimization](https://docs.docker.com/build/cache/optimize/): Docker layer cache và build context.
- [Spring Boot — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootBuildImage`/buildpacks khi có Spring Boot plugin.

**Kết luận:** kết nối đóng gói container với Gradle tốt nhất là **mô hình hóa một pipeline nhỏ, có tên và ranh giới rõ**. Với Dockerfile, `installDist` tạo application distribution, `Sync` stage context an toàn và `Exec` gọi `docker build` khi được yêu cầu; task graph thể hiện dependencies nhưng không ép mọi `build`/`test` dùng Docker. Với Java thuần, Jib cho phép build layers, image TAR, local Docker image hoặc registry image bằng các tasks chuyên dụng. Trong cả hai hướng, tách **build local** khỏi **push/deploy**, giới hạn quyền và build context, pin/truy vết base image cùng output digest, rồi smoke-test image trước khi phát hành.