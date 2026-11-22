# Phân biệt tham số Gradle, thuộc tính JVM và đối số ứng dụng trong Spring Boot 3.3

## 1. Vì sao cùng một chữ `-D` hay `--` lại có kết quả khác nhau?

Khi học Spring Boot Externalized Configuration, người lập trình thường thấy những lệnh như:

```bash
./gradlew bootRun -PdeployRegion=ap-southeast-1
./gradlew bootRun -Ddemo.region=ap-southeast-1
./gradlew bootRun --args='--demo.region=ap-southeast-1'
java -Ddemo.region=ap-southeast-1 -jar app.jar
java -jar app.jar --demo.region=ap-southeast-1
```

Nhìn bề ngoài, tất cả đều nhắc tới “region”. Nhưng chúng **không đi vào cùng nơi** và không được **cùng chương trình** xử lý:

- `-P...` của Gradle thiết lập **Gradle project property** cho quá trình build.
- `-D...` đặt sau `gradlew` thiết lập **system property cho JVM chạy Gradle**, không tự động cho JVM ứng dụng do `bootRun` khởi chạy.
- `--args='...'` của task `bootRun` chuyển một chuỗi đối số cho **hàm `main(String[] args)` của ứng dụng**.
- `-D...` đặt **trước** `-jar` trong lệnh `java` thiết lập **Java system property của JVM ứng dụng**.
- `--demo.region=...` đặt **sau** tên JAR là **đối số ứng dụng**, được Spring Boot mặc định chuyển thành một property trong `Environment`.

Một lệnh có thể khởi động thành công mà ứng dụng vẫn dùng cấu hình cũ, đơn giản vì giá trị được đưa nhầm đến **Gradle** thay vì đến **Spring Boot application**.

Đây là chủ đề “Phân biệt tham số Gradle, thuộc tính JVM và đối số ứng dụng”, thuộc nhóm **Triển khai cấu hình** của **Spring Boot Externalized Configuration**.

### Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích ranh giới giữa terminal/shell, Gradle, JVM ứng dụng và Spring Boot.
2. Phân biệt `-P`, `-D`, `--args`, `args`, `jvmArgs`, `systemProperty`, biến môi trường và `--key=value`.
3. Viết đúng lệnh cho `bootRun` và `java -jar` trên Unix hoặc PowerShell.
4. Hiểu vì sao `-D` trên lệnh Gradle không mặc định chuyển sang JVM con.
5. Chủ động nối một Gradle project property sang Java system property hoặc đối số ứng dụng nếu thật sự cần.
6. Giải thích cách Spring Boot chọn giá trị cuối cùng khi file, system properties, environment variables và CLI cùng cấp một khóa.
7. Dùng `System.getProperty`, `ApplicationArguments` và `Environment` để chẩn đoán giá trị thực.
8. Không dùng `org.gradle.jvmargs` để thay thế JVM options của ứng dụng.
9. Kiểm thử trên Gradle/CI và tránh làm lộ thông tin bí mật trong tham số khởi động.

Các ví dụ hướng tới **Java 17+**, **Spring Boot 3.3.x**, Gradle Wrapper của dự án và plugin Spring Boot Gradle 3.3.x.

## 2. Sơ đồ bốn tầng: shell → Gradle → JVM ứng dụng → Spring Boot

Một lệnh `bootRun` đi qua nhiều tầng:

```text
Bash / PowerShell / cmd
    |
    | phân tích nháy, biến môi trường, ký tự đặc biệt
    v
./gradlew (hoặc gradlew.bat)
    |
    | phân tích -P, -D, --offline, --info, task name
    v
Gradle build process / Gradle Daemon JVM
    |
    | đọc build.gradle, gradle.properties, task configuration
    | thực hiện task bootRun
    v
bootRun / JavaExec
    |
    | tạo JVM chạy ứng dụng (Java process riêng)
    | thiết lập jvmArgs, systemProperty, environment, args
    v
JVM ứng dụng
    |
    | nhận -D..., -Xmx... trước main class/JAR
    | System.getProperties()
    v
main(String[] args) của Spring Boot
    |
    | nhận --demo.region=... và đối số khác
    | SpringApplication chuẩn bị Environment
    v
Spring Environment / Binder
    |
    +-- system properties của JVM ứng dụng
    +-- biến môi trường OS ứng dụng
    +-- application.properties / YAML
    +-- command-line properties của ứng dụng
    |
    v
@Value / @ConfigurationProperties / Environment
```

Với lệnh `java -jar` trực tiếp, không có tầng Gradle:

```text
Shell → Java launcher → JVM ứng dụng → Spring Boot
```

Do đó, hãy hỏi trước khi chọn cú pháp:

> Tôi muốn thay đổi hành vi của **Gradle build**, **JVM đang chạy ứng dụng**, hay **cấu hình Spring Boot**?

Câu trả lời quyết định dùng `-P`, `-D`, `--args` hay `--spring.some-key=value`.

## 3. Bảng phân biệt nhanh

| Cú pháp | Ai xử lý trước? | Tác dụng chính |
| --- | --- | --- |
| `./gradlew build --offline` | Gradle | Chạy build không dùng mạng để lấy dependency mới |
| `./gradlew bootRun --info` | Gradle | Tăng mức log của Gradle |
| `./gradlew bootRun -Pstage=qa` | Gradle | Đặt project property `stage` cho build |
| `./gradlew bootRun -Ddemo.mode=qa` | JVM/Gradle | Đặt Java system property ở phía Gradle |
| `./gradlew bootRun --args='--demo.mode=qa'` | Task `bootRun` | Chuyển `--demo.mode=qa` vào `main` ứng dụng |
| `java -Ddemo.mode=qa -jar app.jar` | Java launcher | Đặt system property **JVM ứng dụng** |
| `java -Xmx512m -jar app.jar` | Java launcher | Giới hạn heap JVM ứng dụng |
| `java -jar app.jar --demo.mode=qa` | Spring Boot | Nhận option của ứng dụng và đưa vào `Environment` |
| `DEMO_MODE=qa java -jar app.jar` | Shell/OS | Đặt biến môi trường cho tiến trình ứng dụng |
| `tasks.named("bootRun") { systemProperty(...) }` | Gradle task config | Cấu hình Java system property cho JVM do `bootRun` tạo |
| `tasks.named("bootRun") { jvmArgs(...) }` | Gradle task config | Cấu hình JVM arguments cho JVM ứng dụng |
| `tasks.named("bootRun") { args(...) }` | Gradle task config | Cấu hình application arguments cho JVM ứng dụng |

**Bẫy phổ biến:** cả Gradle lẫn Java đều dùng cú pháp `-D`, nhưng chương trình **đứng trước `-D`** và cách Gradle tạo process quyết định thuộc tính ấy thuộc về JVM nào.

## 4. Tầng thứ nhất: shell phân tích lệnh trước

Trước khi Gradle hay Java nhìn thấy tham số, terminal đã xử lý:

- Dấu nháy đơn hoặc kép.
- Dấu cách và việc chia thành đối số.
- Mở rộng biến môi trường.
- Ký tự đặc biệt như `$`, `&`, `;`, `|`, `*`, `?`.
- Cú pháp xuống dòng.

Ví dụ trên Bash:

```bash
./gradlew bootRun --args='--demo.message=hello world'
```

Dấu nháy ngoài bảo vệ khoảng trắng để `--args` nhận một chuỗi phù hợp. Task `bootRun` sẽ phân tích chuỗi và chuyển nội dung sang đối số ứng dụng theo cơ chế Gradle.

Trên PowerShell:

```powershell
.\gradlew.bat bootRun '--args=--demo.message=hello world'
```

Lệnh này được PowerShell truyền dưới dạng một argument dành cho Gradle. Nếu muốn đảm bảo một **giá trị ứng dụng có khoảng trắng** được giữ thành một đối số sau khi Gradle phân tích, cần kiểm soát cả **hai lớp nháy**: lớp shell và lớp phân tích của Gradle.

Trường hợp có dấu cách phức tạp, cách ổn định hơn là cấu hình danh sách argument trực tiếp trong task:

```groovy
tasks.named("bootRun") {
    args("--demo.message=hello world")
}
```

Ở đây `args(...)` nhận **một phần tử** của danh sách application arguments, không cần chuỗi chứa cú pháp nháy lồng nhau.

### 4.1. Dấu nháy không thuộc giá trị nhận được

Khi shell dùng:

```bash
export DEMO_MESSAGE='hello world'
```

dấu nháy thường chỉ có nhiệm vụ bảo vệ chuỗi ở shell. Giá trị biến môi trường là `hello world`, không có ký tự nháy đơn.

Tương tự, trong:

```bash
java -jar app.jar '--demo.message=hello world'
```

ứng dụng nhận một argument có nội dung `--demo.message=hello world`.

### 4.2. Không dùng một cú pháp nguyên xi cho mọi shell

Lệnh:

```bash
DEMO_MODE=qa java -jar app.jar
```

phù hợp trên shell Unix như Bash, nhưng không phải cú pháp gán biến môi trường chuẩn của Windows PowerShell.

PowerShell:

```powershell
$env:DEMO_MODE = 'qa'
java -jar .\app.jar
```

Hãy xác định shell đang chạy trước khi sao chép ví dụ từ tài liệu.

## 5. Gradle command-line options: `--info`, `--offline`, `-P`, `-D`

Khi bạn gõ:

```bash
./gradlew bootRun --info
```

`--info` yêu cầu Gradle ghi log build chi tiết hơn. Nó **không** tự đặt:

```properties
logging.level.root=INFO
```

cho Spring Boot application. Tương tự:

```bash
./gradlew bootRun --debug
```

là yêu cầu mức log cho **Gradle**, không tương đương với:

```bash
java -jar app.jar --debug
```

mà Spring Boot có thể diễn giải ở tầng ứng dụng.

Các lựa chọn Gradle phổ biến:

| Tham số | Ý nghĩa |
| --- | --- |
| `tasks` | Liệt kê các task Gradle |
| `build` | Chạy task build |
| `bootRun` | Task chạy Spring Boot trong Gradle |
| `--offline` | Hạn chế Gradle sử dụng network khi phân giải dependency |
| `--info` / `--debug` | Tăng mức logging của Gradle |
| `--stacktrace` | Hiển thị stack trace của lỗi Gradle |
| `--no-daemon` | Yêu cầu chế độ chạy Gradle không tái sử dụng daemon lâu dài |
| `--max-workers=N` | Giới hạn worker của Gradle |
| `-Pname=value` | Đặt Gradle project property |
| `-Dname=value` | Đặt system property cho phía JVM Gradle |
| `--args=...` với `bootRun` | Task option chuyển application arguments sang process ứng dụng |

Không nên kết luận `--max-workers=2` giới hạn worker thread của business service; nó kiểm soát công việc của **Gradle build**, không phải cấu hình thread pool Spring Boot.

## 6. `-P` là Gradle project property

Ví dụ:

```bash
./gradlew bootRun -PdeployRegion=ap-southeast-1
```

Giá trị `deployRegion` đi vào **mô hình project properties của Gradle**. Build script có thể đọc:

```groovy
def region = project.findProperty("deployRegion")
println("Gradle project property = " + region)
```

Hoặc API Provider:

```groovy
def region = providers.gradleProperty("deployRegion")
```

**Nhưng Spring Boot không tự nhận** `deployRegion` chỉ vì dòng lệnh có `-PdeployRegion=...`.

Mặc định, code Java của ứng dụng không nhận một Spring property tên `deployRegion` từ Gradle project property. Muốn truyền sang ứng dụng, cần **bridge có chủ đích** ở task `bootRun` hoặc qua môi trường triển khai.

### 6.1. `-P` có tác dụng cả khi task không chạy ứng dụng

Ví dụ:

```bash
./gradlew test -PtestGroup=smoke
```

Build script có thể dùng `testGroup` để chọn một tập test hoặc cấu hình build. Project property thuộc phạm vi build chứ không nhất thiết phải tạo JVM ứng dụng.

Không nên dùng `-P` để biểu diễn cấu hình production mà artifact cần đọc sau khi triển khai, trừ khi build/triển khai có một hợp đồng rõ ràng đưa giá trị đó vào runtime.

### 6.2. Project properties cũng có thể đến từ `gradle.properties`

Ví dụ:

```properties
deployRegion=ap-southeast-1
```

trong file `gradle.properties` có thể làm Gradle project nhận `deployRegion`. Điều đó **không biến nó thành** `app.region` trong Spring `Environment`.

Một project property còn có thể được cấp qua cách Gradle hỗ trợ như:

```bash
./gradlew bootRun -Dorg.gradle.project.deployRegion=eu-west-1
```

hoặc biến môi trường Gradle thích hợp:

```text
ORG_GRADLE_PROJECT_deployRegion
```

Cơ chế này chỉ làm Gradle có project property tương ứng, không tự chuyển thành Spring Boot property. Đừng nhầm prefix `org.gradle.project.` với prefix cấu hình `spring.*`.

## 7. `-D` sau `gradlew` thuộc JVM của Gradle

Ví dụ:

```bash
./gradlew bootRun -Ddemo.region=eu-central-1
```

Theo CLI Gradle, `-D` đặt một **Java system property cho phía JVM thực thi Gradle**.

Có thể kiểm tra trong build logic:

```groovy
println("Gradle sees: " + System.getProperty("demo.region"))
```

Tuy nhiên, task `bootRun` của Spring Boot Gradle Plugin là một dạng `JavaExec` khởi chạy ứng dụng bằng một **Java process riêng**. Nó không bảo đảm tự động sao chép toàn bộ `System.getProperties()` của Gradle sang JVM con.

Vì vậy, trong JVM ứng dụng:

```java
System.getProperty("demo.region")
```

có thể trả `null` dù Gradle thấy `eu-central-1`, trừ khi task/launcher đã chuyển giá trị bằng cơ chế khác.

### 7.1. So sánh hai lệnh có vẻ giống nhau

```bash
./gradlew bootRun -Ddemo.region=qa
```

Tác động chính:

```text
Gradle build JVM: demo.region=qa
Boot application JVM: không tự được đảm bảo
```

Trong khi:

```bash
java -Ddemo.region=qa -jar app.jar
```

Tác động chính:

```text
JVM trực tiếp chạy ứng dụng: demo.region=qa
Spring Environment: thường có thể đọc demo.region=qa
```

**Một chữ `-D` không xác định đích nhận; context của Java launcher hoặc Gradle launcher mới xác định đích.**

### 7.2. `systemProp.*` trong `gradle.properties`

Ví dụ:

```properties
systemProp.demo.region=qa
```

đặt system property trong môi trường Gradle. Nó **không đồng nghĩa** với cấu hình:

```properties
demo.region=qa
```

trong `application.properties`.

Nếu `bootRun` cần property này, hãy định nghĩa cách forwarding rõ ràng thay vì trông chờ vào sự trùng tên giữa hai hệ sinh thái.

## 8. Gradle Daemon là một JVM khác

Nhiều phiên bản Gradle dùng **Gradle Daemon**, một JVM tồn tại để thực hiện build và có thể được tái sử dụng.

Một mô hình đơn giản:

```text
Terminal
   |
   v
Gradle client / wrapper
   |
   v
Gradle daemon JVM
   |
   +-- đọc build script
   +-- biên dịch, resolve dependencies
   +-- tạo process cho bootRun
                |
                v
           JVM Spring Boot
```

Vì vậy, Gradle có thể đang sử dụng heap 2 GB trong khi ứng dụng Java được `bootRun` chạy dùng heap giới hạn 512 MB, hoặc ngược lại.

### 8.1. `org.gradle.jvmargs` là cho Gradle, không phải ứng dụng

Trong `gradle.properties`:

```properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
```

thiết lập JVM arguments cho **Gradle Daemon** theo cơ chế cấu hình Gradle.

Nó **không thay thế**:

```bash
java -Xmx2g -jar app.jar
```

và không có nghĩa heap của ứng dụng `bootRun` mặc định là 2 GB.

Nếu ứng dụng thiếu heap, tăng `org.gradle.jvmargs` có thể chỉ khiến **build** có nhiều bộ nhớ hơn mà không giải quyết memory limit của process Spring Boot.

### 8.2. Cách thiết lập heap cho ứng dụng qua `bootRun`

Groovy DSL:

```groovy
tasks.named("bootRun") {
    jvmArgs("-Xms128m", "-Xmx512m")
}
```

Hoặc thông qua API JavaExec:

```groovy
tasks.named("bootRun") {
    minHeapSize = "128m"
    maxHeapSize = "512m"
}
```

Đây là các thiết lập dành cho process **ứng dụng** do `bootRun` tạo, không phải cho Gradle Daemon.

Lưu ý nhiều cách cấu hình JVM args có thể ảnh hưởng nhau; không nên đồng thời đặt các lựa chọn trái ngược như `-Xmx512m` và `maxHeapSize="1g"` mà không hiểu kết quả cuối. Giữ một quy ước nhất quán.

### 8.3. `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS`

Các biến môi trường Java launcher có thể ảnh hưởng đến nhiều process Java được khởi động trong môi trường đó, bao gồm Gradle và JVM ứng dụng trong một số tình huống.

Không coi `JAVA_TOOL_OPTIONS` là Gradle project property hay Spring application argument. Nó hoạt động ở tầng **Java tooling/launcher**. Vì có phạm vi rộng, cần thận trọng khi đặt trong terminal CI dùng chung.

## 9. `bootRun` tạo JVM ứng dụng: API `JavaExec`

Trong Spring Boot 3.3, task `bootRun` là task loại `BootRun`, kế thừa từ `JavaExec` của Gradle.

Do đó, có những nhóm cấu hình riêng:

| Task API | Tác động tới |
| --- | --- |
| `args(...)` | Đối số truyền vào `main(String[] args)` của app |
| `setArgs(...)` | Danh sách application arguments |
| `jvmArgs(...)` | JVM arguments cho app process |
| `systemProperty(name, value)` | Java system property của app process |
| `environment(name, value)` | Biến môi trường cho app process |
| `minHeapSize`, `maxHeapSize` | Heap của JVM ứng dụng |
| `workingDir` | Thư mục làm việc của app process |

Các lựa chọn này không giống như `-P` hoặc `-D` ở cấp lệnh Gradle; chúng được định nghĩa **bên trong task** để điều khiển Java process mà task khởi chạy.

### 9.1. Cấu hình một system property cho JVM ứng dụng

Trong `build.gradle` Groovy DSL:

```groovy
tasks.named("bootRun") {
    systemProperty("demo.region", "ap-southeast-1")
}
```

Khi `bootRun` chạy, JVM ứng dụng có thể thấy:

```java
System.getProperty("demo.region")
```

và Spring Boot có thể tra cứu:

```java
environment.getProperty("demo.region")
```

Trong trường hợp trên, task đưa property trực tiếp vào JVM con; không phải vì lệnh Gradle có `-D` tự đi qua.

### 9.2. Cấu hình argument cho ứng dụng

```groovy
tasks.named("bootRun") {
    args("--demo.mode=qa", "--spring.profiles.active=dev")
}
```

Hai chuỗi này là **hai phần tử application arguments**.

Spring Boot mặc định chuyển option `--demo.mode=qa` và `--spring.profiles.active=dev` vào `Environment`, vì vậy các bean có thể thấy mode là `qa` và profile là `dev`.

### 9.3. Cấu hình biến môi trường cho ứng dụng

```groovy
tasks.named("bootRun") {
    environment("DEMO_REGION", "ap-southeast-1")
}
```

Đây là **biến môi trường của process ứng dụng**, khác với:

```groovy
systemProperty("demo.region", "ap-southeast-1")
```

Hai nguồn đều có thể được Spring Boot đọc nhưng khác về API trực tiếp:

```java
System.getenv("DEMO_REGION")
System.getProperty("demo.region")
```

Trong hệ thống Spring Boot, `Environment` còn áp dụng relaxed binding cho tên biến môi trường.

## 10. Dùng `--args` để chuyển đối số runtime qua `bootRun`

Một cách thông dụng mà không cần sửa build script:

```bash
./gradlew bootRun --args='--demo.region=ap-southeast-1'
```

`--args` ở đây là **task option của JavaExec/bootRun**, dùng để chuyển chuỗi đối số cho ứng dụng.

Tương đương về mục đích với:

```bash
java -jar app.jar --demo.region=ap-southeast-1
```

Cả hai đưa `--demo.region=...` vào đối số ứng dụng. Không phải vì Gradle nhận `-P` hay JVM tự nhận `-D`.

### 10.1. Nhiều đối số

Bash:

```bash
./gradlew bootRun \
  --args='--demo.mode=qa --demo.worker-count=4 --spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun '--args=--demo.mode=qa --demo.worker-count=4 --spring.profiles.active=dev'
```

Cả hai ví dụ đều dùng **một giá trị** cho task option `--args`, chứa ba application arguments.

### 10.2. `--args` không có nghĩa mọi chuỗi đều trở thành Spring property

Nếu ứng dụng nhận:

```text
--demo.mode=qa
```

Spring Boot mặc định đọc nó như option property.

Nhưng nếu ứng dụng nhận:

```text
job-123
```

đó là **non-option argument**. Spring Boot không tự diễn giải `job-123` thành property `demo.job-id`.

Có thể đọc các đối số kiểu này qua:

```java
ApplicationArguments#getNonOptionArgs()
```

hoặc qua `main(String[] args)`, tùy thiết kế.

### 10.3. `--args` thuộc task, không phải tùy chọn runtime của JVM

Không dùng lệnh Java trực tiếp như:

```bash
java -jar app.jar --args='--demo.mode=qa'
```

với kỳ vọng Java launcher tự bóc `--args`. Java không có cơ chế mặc định tương đương task option `bootRun --args`.

Trong lệnh `java -jar`, hãy truyền trực tiếp:

```bash
java -jar app.jar --demo.mode=qa
```

## 11. Dùng `-P` rồi chuyển giá trị sang ứng dụng có chủ đích

Đây là một pattern Gradle rõ ràng khi đội phát triển muốn đặt tên project property cho quy trình chạy.

### 11.1. Groovy DSL

Trong `build.gradle`:

```groovy
tasks.named("bootRun") {
    def region = providers.gradleProperty("deployRegion")
            .orElse("local")
            .get()

    systemProperty("demo.region", region)
}
```

Chạy:

```bash
./gradlew -PdeployRegion=eu-west-1 bootRun
```

Luồng:

```text
Gradle -PdeployRegion=eu-west-1
             |
             v
providers.gradleProperty("deployRegion")
             |
             v
bootRun.systemProperty("demo.region", "eu-west-1")
             |
             v
JVM ứng dụng System.getProperty("demo.region")
             |
             v
Spring Environment demo.region
```

Ở đây `-P` **không tự đi tới ứng dụng**. Chính đoạn `systemProperty(...)` trong build script đã xây cầu nối.

### 11.2. Kotlin DSL

Trong `build.gradle.kts`:

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    val region = providers.gradleProperty("deployRegion")
        .orElse("local")
        .get()

    systemProperty("demo.region", region)
}
```

Lệnh chạy vẫn là:

```bash
./gradlew -PdeployRegion=eu-west-1 bootRun
```

Sự khác biệt nằm ở cú pháp cấu hình task của Gradle. Không sao chép nguyên Groovy DSL vào `build.gradle.kts`.

### 11.3. Khi nào nên dùng bridge này?

Phù hợp khi:

- Build pipeline đã có một Gradle project property được quản lý tập trung.
- Task chạy ứng dụng cần chuyển một giá trị build-time thành runtime cho môi trường test cục bộ.
- Muốn định nghĩa một default cho `bootRun` trong build script.
- Muốn đổi tên property phía build so với key Spring Boot.

Không nên dùng project property làm nơi lưu secret lâu dài. `-Ppassword=...` có thể xuất hiện trong command history, process list hoặc log CI.

## 12. Dùng `-P` rồi chuyển thành application arguments

Ngoài `systemProperty`, có thể nối Gradle project property sang application argument.

Groovy DSL:

```groovy
tasks.named("bootRun") {
    def stage = providers.gradleProperty("deployStage")
            .orElse("local")
            .get()

    args("--demo.stage=${stage}")
}
```

Chạy:

```bash
./gradlew -PdeployStage=qa bootRun
```

JVM ứng dụng sẽ nhận một argument:

```text
--demo.stage=qa
```

Cơ chế này có khác biệt về precedence với `systemProperty`:

- `systemProperty("demo.stage", "qa")` đưa giá trị vào nguồn **Java system properties** của Spring.
- `args("--demo.stage=qa")` đưa giá trị vào nguồn **application command-line properties** mặc định của Spring Boot.

Theo thứ tự ưu tiên chuẩn Spring Boot 3.3, command-line properties thường ưu tiên hơn Java system properties và config data.

### Cẩn trọng nếu đồng thời sử dụng `args(...)` và `--args`

Nếu build script đặt default application arguments, còn người chạy thêm `bootRun --args='...'`, cơ chế task option có thể thiết lập lại danh sách arguments tùy cách Gradle xử lý. Đừng xây một hợp đồng ứng dụng dựa trên việc hai nguồn arguments **luôn tự nối** mà không kiểm chứng.

Nếu cần hợp nhất đối số từ nhiều nơi, thiết kế một quy tắc trong build script và kiểm thử kết quả thực nhận ở `ApplicationArguments`.

## 13. Thuộc tính JVM trong lệnh `java -jar`

Khi chạy artifact đã build:

```bash
java -Ddemo.region=ap-southeast-1 -jar app.jar
```

`-Ddemo.region=...` xuất hiện **trước** `-jar`, nên được Java launcher xử lý thành Java system property của JVM ứng dụng.

Trong Java:

```java
System.getProperty("demo.region")
```

trả về chuỗi nếu property đã được đặt và không bị mã khác thay đổi.

Spring Boot cũng đưa Java system properties vào `Environment`, nên:

```java
environment.getProperty("demo.region")
```

có thể nhận cùng giá trị khi không có nguồn cấu hình ưu tiên cao hơn.

### 13.1. Thứ tự tương đối trước `-jar`

Các JVM options nằm trước `-jar`:

```bash
java -Xms128m -Xmx512m -Ddemo.region=qa -jar app.jar
```

hoặc:

```bash
java -Ddemo.region=qa -Xmx512m -jar app.jar
```

đều đặt JVM options cho ứng dụng, miễn là chúng đứng ở vị trí Java launcher nhận như JVM options.

Không đưa `-D` **sau** tên JAR rồi mong Java launcher xử lý nó:

```bash
java -jar app.jar -Ddemo.region=qa
```

Trong lệnh này, phần `-Ddemo.region=qa` sau JAR được chuyển vào **application arguments**. Nó không còn là JVM `-D` theo nghĩa của Java launcher. Spring Boot cũng không tự coi tùy chọn một dấu gạch `-D...` là `--demo.region=...`.

### 13.2. Tại sao Java system property khác environment variable?

Java system property:

```java
System.getProperty("demo.region")
```

OS environment variable:

```java
System.getenv("DEMO_REGION")
```

là hai API khác nhau.

`-Ddemo.region=qa` không tạo biến môi trường `DEMO_REGION`.

`DEMO_REGION=qa` không tự tạo một phần tử trong `System.getProperties()` tên `demo.region`.

Spring Boot có thể đọc **cả hai nguồn** qua `Environment`, rồi áp dụng quy tắc precedence và relaxed binding.

## 14. Đối số ứng dụng sau JAR

Một lệnh khác:

```bash
java -jar app.jar --demo.region=qa
```

Ở đây `--demo.region=qa` **không** được Java launcher diễn giải là system property. Java chuyển nó thành argument của hàm main, và `SpringApplication` mặc định nhận các option bắt đầu bằng `--` để đưa vào `Environment`.

Ví dụ:

```java
SpringApplication.run(Application.class, args);
```

Nếu bạn không chủ động vô hiệu hóa command-line properties, có thể dùng:

```java
environment.getProperty("demo.region")
```

để đọc `qa`.

Nếu chỉ gọi:

```java
System.getProperty("demo.region")
```

thì có thể là `null` vì ứng dụng nhận giá trị từ **command-line property source**, không phải Java system properties.

### 14.1. Có thể vô hiệu hóa command-line properties

Spring Boot cho phép:

```java
SpringApplication application =
        new SpringApplication(Application.class);

application.setAddCommandLineProperties(false);
application.run(args);
```

Khi dùng tùy chọn này, các đối số `--demo.region=qa` vẫn có thể tồn tại trong `ApplicationArguments`, nhưng **không còn tự động được thêm** vào `Environment` như command-line property source.

Vì vậy, mọi quy tắc precedence nói rằng CLI `--key=value` thắng các nguồn khác cần hiểu là **với cấu hình mặc định của SpringApplication**.

### 14.2. Positional arguments

Ví dụ:

```bash
java -jar app.jar import orders.csv
```

`import` và `orders.csv` là các non-option arguments, không tương đương với:

```properties
demo.import=orders.csv
```

Nếu ứng dụng là công cụ CLI, bạn có thể tự phân tích chúng bằng `ApplicationArguments` hoặc thư viện CLI chuyên dụng.

## 15. So sánh hai loại `-D` bằng cùng một khóa

Đặt một thuộc tính:

```text
demo.stage
```

Bốn trường hợp:

| Lệnh | Gradle JVM thấy? | JVM ứng dụng thấy dưới dạng System property? |
| --- | --- | --- |
| `./gradlew bootRun -Ddemo.stage=qa` | Có thể có | Không tự bảo đảm |
| `./gradlew bootRun --args='--demo.stage=qa'` | Không cần | Không; app nhận command-line argument |
| `java -Ddemo.stage=qa -jar app.jar` | Không có Gradle | Có |
| `java -jar app.jar --demo.stage=qa` | Không có Gradle | Không nhất thiết; Spring Environment nhận |

Một quy tắc chẩn đoán:

```text
System.getProperty("demo.stage") != null?
    Có -> Có Java system property trong JVM ứng dụng.
    Không -> Chưa chắc cấu hình Spring thiếu.
            Kiểm tra command-line, env, YAML, profile.
```

Và:

```text
environment.getProperty("demo.stage")
```

là cách quan sát giá trị **có hiệu lực với Spring**. Đừng thay thế một API bằng API kia khi đang phân biệt nguồn.

## 16. Spring Boot Externalized Configuration chọn giá trị cuối ra sao?

Giả sử `application.properties` có:

```properties
demo.region=file-region
demo.mode=file-mode
```

Và JVM ứng dụng được chạy:

```bash
java -Ddemo.region=jvm-region -jar app.jar --demo.region=cli-region
```

Trong cấu hình Spring Boot 3.3 thông thường:

- Giá trị trong file cấu hình được nạp.
- Java system property `demo.region=jvm-region` có ưu tiên cao hơn config data.
- Command-line property `demo.region=cli-region` có ưu tiên cao hơn system property.

Vì vậy:

```java
System.getProperty("demo.region")
```

trả `jvm-region`, nhưng:

```java
environment.getProperty("demo.region")
```

trả `cli-region`.

Đây là ví dụ rất quan trọng: **cùng một ứng dụng, hai API trả hai giá trị khác nhau mà đều đúng theo hợp đồng của chúng**.

### 16.1. Thứ tự ưu tiên rút gọn

Với các nguồn phổ biến, thường có quan hệ:

```text
Command-line properties của Spring Boot
                |
                v ưu tiên hơn
Java system properties của JVM ứng dụng
                |
                v ưu tiên hơn
Biến môi trường OS ứng dụng
                |
                v ưu tiên hơn
Config Data (application.properties/YAML)
                |
                v ưu tiên hơn
Default properties
```

Spring Boot có nhiều nguồn khác như JNDI, servlet parameters, `SPRING_APPLICATION_JSON`, test properties, devtools và các nguồn tùy biến. Đừng dùng sơ đồ rút gọn này như danh sách đầy đủ cho mọi môi trường.

Nếu cần kiểm tra giá trị cụ thể, xét toàn bộ `PropertySources` đang có và active profiles, không chỉ nhìn một file YAML.

### 16.2. Gradle `-P` không xuất hiện trong thứ tự này

`-PdeployRegion=qa` là Gradle project property, **không phải một PropertySource của Spring Boot theo mặc định**.

Nó chỉ tham gia sơ đồ khi build script **chủ động chuyển** sang system property, application argument, environment variable hoặc một cơ chế cấp giá trị phù hợp.

## 17. Ví dụ hoàn chỉnh: ứng dụng hiển thị giá trị từng tầng

Tạo một ứng dụng nhỏ có thể dùng để quan sát các cách truyền.

### 17.1. `application.properties`

`src/main/resources/application.properties`:

```properties
spring.application.name=gradle-jvm-args-demo

demo.region=from-file
demo.mode=default-mode
demo.worker-count=2
```

### 17.2. Lớp Spring Boot và ApplicationRunner

`src/main/java/example/argslab/ArgsLabApplication.java`:

```java
package example.argslab;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ArgsLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ArgsLabApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(
            Environment environment,
            ApplicationArguments applicationArguments
    ) {
        return runnerArgs -> {
            String sysRegion = System.getProperty("demo.region");
            String envRegion = System.getenv("DEMO_REGION");
            String springRegion =
                    environment.getProperty("demo.region");

            System.out.println("System.getProperty(demo.region)="
                    + sysRegion);
            System.out.println("System.getenv(DEMO_REGION)="
                    + envRegion);
            System.out.println("Spring Environment demo.region="
                    + springRegion);

            System.out.println("Spring Environment demo.mode="
                    + environment.getProperty("demo.mode"));

            System.out.println("Spring Environment demo.worker-count="
                    + environment.getProperty("demo.worker-count"));

            List<String> cliRegions =
                    applicationArguments.getOptionValues("demo.region");
            System.out.println("CLI option demo.region=" + cliRegions);

            System.out.println("Source args="
                    + String.join(" ", applicationArguments.getSourceArgs()));
        };
    }
}
```

Lớp trên phân biệt:

1. `System.getProperty(...)`: Java system property **của app JVM**.
2. `System.getenv(...)`: biến môi trường OS **của app process**.
3. `environment.getProperty(...)`: giá trị có hiệu lực theo Spring `PropertySources`.
4. `ApplicationArguments`: những arguments **được đưa tới main**, không nhất thiết là properties.
5. `getSourceArgs()`: danh sách application arguments, không chứa JVM `-D` đã được launcher tiêu thụ.

Các dòng in chỉ chứa giá trị mẫu. Trong ứng dụng thật **không in toàn bộ đối số hoặc secret**; ví dụ `String.join` có thể làm lộ mật khẩu nếu CLI có chứa credential.

### 17.3. Chạy ứng dụng không có override

```bash
./gradlew bootRun
```

Trong trường hợp không có nguồn khác cung cấp `demo.region`:

```text
System.getProperty(demo.region)=null
System.getenv(DEMO_REGION)=null
Spring Environment demo.region=from-file
Spring Environment demo.mode=default-mode
Spring Environment demo.worker-count=2
CLI option demo.region=null
```

Đây là output minh họa. Các biến môi trường thực tế từ máy/CI có thể thay đổi kết quả.

## 18. Thử nghiệm 1 — `bootRun --args`

Bash:

```bash
./gradlew bootRun --args='--demo.region=from-args'
```

Dự kiến trong môi trường sạch:

```text
System.getProperty(demo.region)=null
System.getenv(DEMO_REGION)=null
Spring Environment demo.region=from-args
CLI option demo.region=[from-args]
```

Nguyên nhân:

- `--args` chuyển giá trị vào main.
- Spring Boot thêm `--demo.region=from-args` thành command-line property.
- `System.getProperty` không tự thay đổi.

PowerShell:

```powershell
.\gradlew.bat bootRun '--args=--demo.region=from-args'
```

### Thử nhiều option

```bash
./gradlew bootRun \
  --args='--demo.region=eu-west-1 --demo.mode=qa --demo.worker-count=4'
```

Trong app:

```text
Spring Environment demo.region=eu-west-1
Spring Environment demo.mode=qa
Spring Environment demo.worker-count=4
```

Các giá trị đó được ứng dụng nhận như **command-line properties**.

## 19. Thử nghiệm 2 — `bootRun -D` nhưng chưa có bridge

Chạy:

```bash
./gradlew -Ddemo.region=from-gradle bootRun
```

Nếu build script không chuyển property này sang ứng dụng, môi trường app có thể vẫn thấy:

```text
System.getProperty(demo.region)=null
Spring Environment demo.region=from-file
CLI option demo.region=null
```

Điều này không chứng minh Gradle đã bỏ qua `-D`; nó cho thấy **system property của JVM Gradle không mặc định trở thành system property của app JVM**.

Nếu trước đó bạn đã cấu hình trong `build.gradle`:

```groovy
tasks.named("bootRun") {
    systemProperty("demo.region",
            System.getProperty("demo.region", "from-task-default"))
}
```

thì lệnh `-Ddemo.region=from-gradle` mới có thể ảnh hưởng app thông qua **bridge do build script chỉ định**.

Phân biệt hai tình huống để không đưa ra kết luận sai trong code review.

## 20. Thử nghiệm 3 — `java -D... -jar`

Trước tiên tạo executable JAR bằng task Gradle:

```bash
./gradlew bootJar
```

Đường dẫn JAR thực tế tùy `group`, `version`, `archiveFileName`, module và cấu hình build, thường nằm ở:

```text
build/libs/
```

Sau đó chạy một tên JAR cụ thể, ví dụ:

```bash
java -Ddemo.region=from-jvm -jar build/libs/argslab.jar
```

Thay `argslab.jar` bằng artifact được tạo.

Kết quả minh họa:

```text
System.getProperty(demo.region)=from-jvm
Spring Environment demo.region=from-jvm
CLI option demo.region=null
```

Nếu app có môi trường hoặc nguồn ưu tiên cao hơn, Spring Environment có thể chọn giá trị khác. Java system property vẫn là `from-jvm` trừ khi có code sửa nó trong JVM.

### Thử đặt `-D` sai vị trí

```bash
java -jar build/libs/argslab.jar -Ddemo.region=from-jvm
```

`-Ddemo.region=from-jvm` ở đây **nằm sau JAR**. Đó là application argument, không phải Java system property. Đừng kỳ vọng:

```java
System.getProperty("demo.region")
```

nhận `from-jvm`.

Nếu muốn Spring Boot nhận một cấu hình CLI, dùng:

```bash
java -jar build/libs/argslab.jar --demo.region=from-cli
```

## 21. Thử nghiệm 4 — cùng lúc JVM property và application argument

Chạy:

```bash
java \
  -Ddemo.region=from-jvm \
  -jar build/libs/argslab.jar \
  --demo.region=from-cli
```

Dự kiến:

```text
System.getProperty(demo.region)=from-jvm
Spring Environment demo.region=from-cli
CLI option demo.region=[from-cli]
```

Trong Spring Boot 3.3 mặc định, command-line property thắng Java system property cho cùng key.

Đây là một bài test tốt để phân biệt:

- **Nguồn dữ liệu hiện diện** trong JVM là gì?
- **Giá trị sau precedence** Spring chọn là gì?

Khi dùng `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(String region) {}
```

Binder nhận giá trị từ Spring `Environment`, vì vậy thường thấy `from-cli`, không phải do nó đọc thẳng `System.getProperty`.

## 22. Gradle Groovy DSL: đặt một số giá trị cho bootRun

Trong `build.gradle`:

```groovy
tasks.named("bootRun") {
    systemProperty("demo.region", "from-task-system")
    environment("DEMO_MODE", "from-task-environment")
    jvmArgs("-Xms128m", "-Xmx512m")
    args("--demo.worker-count=5")
}
```

Ý nghĩa:

| Cấu hình | Đích |
| --- | --- |
| `systemProperty("demo.region", ...)` | JVM ứng dụng; `System.getProperty` |
| `environment("DEMO_MODE", ...)` | OS environment của app; `System.getenv` |
| `jvmArgs("-Xms128m", "-Xmx512m")` | JVM heap settings cho app |
| `args("--demo.worker-count=5")` | ApplicationArgs và Spring Boot CLI |

Với cấu hình trên:

```text
demo.region=from-task-system
demo.mode=from-task-environment
demo.worker-count=5
```

có thể là các giá trị Spring có hiệu lực nếu không có nguồn khác ưu tiên hơn.

**Lưu ý:** đặt một task default cố định cho `demo.region` có thể vượt giá trị file YAML của developer và gây ngạc nhiên. Chỉ làm như vậy nếu team thực sự muốn `bootRun` hoạt động theo quy ước riêng. Nếu muốn fallback thực sự, cân nhắc cấp giá trị thông qua file cấu hình chung hoặc kiểm soát precedence.

## 23. Gradle Kotlin DSL: cấu hình tương đương

Trong `build.gradle.kts`:

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    systemProperty("demo.region", "from-task-system")
    environment("DEMO_MODE", "from-task-environment")
    jvmArgs("-Xms128m", "-Xmx512m")
    args("--demo.worker-count=5")
}
```

Các phương thức tương ứng với `JavaExec`, nhưng cú pháp gọi, kiểu task và Provider API có khác với Groovy DSL.

Khi đọc ví dụ trên mạng, hãy xác định file của project là:

```text
build.gradle     (Groovy DSL)
build.gradle.kts (Kotlin DSL)
```

Tránh trộn:

```groovy
systemProperty "demo.region", "qa"
```

vào `.kts` vì đó là cú pháp Groovy chứ không phải Kotlin.

## 24. Quy tắc đối với Gradle project property trong CI

Giả sử pipeline có:

```bash
./gradlew -PdeployRegion=eu-west-1 bootRun
```

Nếu build script đọc `deployRegion` và gán:

```groovy
systemProperty("demo.region",
        providers.gradleProperty("deployRegion").get())
```

thì ứng dụng nhận giá trị qua Java system property.

Nhưng khi tạo executable JAR:

```bash
./gradlew -PdeployRegion=eu-west-1 bootJar
```

**không có nghĩa** JAR được tạo sẽ tự có cấu hình region `eu-west-1` ở mọi nơi chạy sau này.

Đây là khác biệt lớn giữa:

- **Build-time data**: dùng để cấu hình các task, tên artifact, version, compiler.
- **Run-time data**: đọc khi ứng dụng chạy trong container, VM hoặc Kubernetes.

Một workflow có thể chủ ý đóng gói giá trị vào artifact khi build, nhưng đó là quyết định thiết kế riêng. Spring Boot externalized configuration thường hướng tới **giữ cùng một artifact** cho nhiều môi trường, chuyển giá trị bằng nguồn runtime khi triển khai.

### Ví dụ triển khai giữ artifact bất biến

Build:

```bash
./gradlew clean bootJar
```

Staging:

```bash
java -jar app.jar --spring.profiles.active=staging
```

Production:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Hoặc cung cấp biến môi trường từ container platform. Cùng JAR có thể chạy ở hai môi trường với cấu hình khác nhau, không cần rebuild chỉ để đổi một property.

## 25. Spring Profiles qua ba con đường

Một ví dụ điển hình là bật profile `dev`.

### 25.1. Đối số ứng dụng trực tiếp

```bash
java -jar app.jar --spring.profiles.active=dev
```

Đây là Spring Boot CLI property.

### 25.2. System property của JVM ứng dụng

```bash
java -Dspring.profiles.active=dev -jar app.jar
```

Đây là Java system property được Spring Boot đọc từ `Environment`.

### 25.3. bootRun task option

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Đây là cách truyền Spring Boot CLI property vào JVM do `bootRun` khởi chạy.

### 25.4. Cẩn trọng với cách này

```bash
./gradlew bootRun -Dspring.profiles.active=dev
```

Lệnh này đặt `spring.profiles.active` ở phía JVM Gradle; **không mặc định** là cách bật profile của Spring Boot application trong process do `bootRun` tạo.

Nếu project có một bridge trong build script, lệnh trên có thể hoạt động, nhưng đó là kết quả **cấu hình riêng của task** và không nên được mô tả như mặc định của mọi dự án.

## 26. Biến môi trường của ứng dụng không phải Gradle property

Một giá trị:

```text
DEMO_REGION=ap-southeast-1
```

có thể được Spring Boot relaxed binding nhận dưới tên:

```text
demo.region
```

Trong Bash:

```bash
DEMO_REGION=ap-southeast-1 java -jar app.jar
```

Hoặc với `bootRun`:

```bash
DEMO_REGION=ap-southeast-1 ./gradlew bootRun
```

Trong PowerShell:

```powershell
$env:DEMO_REGION = 'ap-southeast-1'
.\gradlew.bat bootRun
```

Với cấu hình JavaExec mặc định phù hợp, process ứng dụng có thể kế thừa biến môi trường từ process khởi chạy hoặc nhận những biến được task thiết lập cụ thể. Nhưng không nên đánh đồng:

```text
DEMO_REGION
```

với:

```text
ORG_GRADLE_PROJECT_deployRegion
```

Biến đầu hướng tới Spring Boot environment property theo quy tắc tên tương ứng; biến thứ hai là một cách Gradle nhận **project property**.

### 26.1. Quy tắc tên canonical cho Spring Boot

Một khóa:

```text
demo.worker-count
```

thường tương ứng với biến môi trường:

```text
DEMO_WORKERCOUNT
```

Quy tắc binding tên biến môi trường:

1. Thay dấu `.` bằng `_`.
2. Bỏ dấu `-`.
3. Viết in hoa.

Không mặc định `DEMO_WORKER_COUNT` sẽ tương đương hoàn toàn với `demo.worker-count` theo mọi quy tắc Binder; phân biệt rõ dấu gạch nối trong cùng một segment với dấu phân cấp tên.

### 26.2. Dọn biến môi trường sau khi thử

PowerShell:

```powershell
Remove-Item Env:DEMO_REGION
```

Bash:

```bash
unset DEMO_REGION
```

Tránh để một biến môi trường từ bài thử trước âm thầm ghi đè file cấu hình trong lần chạy sau.

## 27. Spring Boot property và JVM option có thể ở các tầng khác nhau

Ví dụ:

```bash
java -Xmx512m -Duser.timezone=UTC -jar app.jar --server.port=8081
```

Trong đó:

- `-Xmx512m`: JVM heap option.
- `-Duser.timezone=UTC`: Java system property tác động đến cấu hình thời gian của JVM/Java API.
- `--server.port=8081`: Spring Boot application property điều khiển cổng embedded server nếu app có web server.

Đổi `server.port` không phải đổi một JVM option. Đổi `-Xmx` không phải một property mà Binder phải chuyển sang `DataSize`.

Một số Java system properties cũng có ý nghĩa với Spring Boot khi Spring đưa chúng vào `Environment`. Nhưng không phải mọi JVM option đều có tên khóa tương ứng với Spring.

Ví dụ `-XX:+UseG1GC` được JVM xử lý; không thể thay thế bằng:

```properties
spring.jvm.use-g1-gc=true
```

trừ khi bạn tự viết một cơ chế rất đặc thù, và thậm chí lúc đó nhiều lựa chọn JVM phải được thiết lập **trước khi JVM khởi động**.

## 28. Phân biệt `-D` và `--` khi dùng Spring Boot

Giả sử cùng một khóa:

```text
demo.timeout
```

Lệnh A:

```bash
java -Ddemo.timeout=5s -jar app.jar
```

Lệnh B:

```bash
java -jar app.jar --demo.timeout=5s
```

Với `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(Duration timeout) {}
```

cả A và B có thể làm Binder nhận `Duration.ofSeconds(5)`.

Nhưng **nguồn được biểu diễn khác nhau**:

- A đi qua Java system properties.
- B đi qua Spring Boot command-line property source.

Nếu cả hai cùng có mặt và khác giá trị:

```bash
java -Ddemo.timeout=5s -jar app.jar --demo.timeout=8s
```

thì Spring Boot mặc định ưu tiên command-line property `8s`.

Nếu code dùng:

```java
System.getProperty("demo.timeout")
```

nó vẫn chỉ nhìn thấy `5s`, không phải giá trị Spring đã hợp nhất.

## 29. Không nhầm Gradle task option với Spring Boot application option

Xem cặp lệnh:

```bash
./gradlew bootRun --debug
```

và:

```bash
./gradlew bootRun --args='--debug'
```

Lệnh đầu dùng `--debug` cho logging của **Gradle**.

Lệnh thứ hai đưa `--debug` vào application arguments của **Spring Boot**. Spring Boot có thể kích hoạt debug mode theo khả năng của ứng dụng và cấu hình liên quan.

Tương tự:

```bash
./gradlew bootRun --info
```

không tương đương với:

```bash
./gradlew bootRun --args='--logging.level.root=INFO'
```

Lệnh đầu ảnh hưởng Gradle logging; lệnh sau ảnh hưởng Spring Boot logging property.

### `--stacktrace` thì sao?

`--stacktrace` là tùy chọn chẩn đoán lỗi Gradle, không tự làm Java app in stacktrace theo một quy tắc tương ứng.

Khi cần chẩn đoán app, hãy xem startup logs và cấu hình log của app; khi cần chẩn đoán task/build thất bại, dùng Gradle `--stacktrace`, `--info`, `--debug` theo nhu cầu.

## 30. So sánh lệnh trên Bash và PowerShell

| Mục đích | Bash/Unix | PowerShell/Windows |
| --- | --- | --- |
| Chạy Gradle | `./gradlew bootRun` | `.\gradlew.bat bootRun` |
| App CLI region | `./gradlew bootRun --args='--demo.region=qa'` | `.\gradlew.bat bootRun '--args=--demo.region=qa'` |
| Gradle property | `./gradlew -PdeployRegion=qa bootRun` | `.\gradlew.bat -PdeployRegion=qa bootRun` |
| Gradle JVM system property | `./gradlew -Ddemo.region=qa bootRun` | `.\gradlew.bat -Ddemo.region=qa bootRun` |
| App JVM property | `java -Ddemo.region=qa -jar app.jar` | `java -Ddemo.region=qa -jar .\app.jar` |
| App CLI property | `java -jar app.jar --demo.region=qa` | `java -jar .\app.jar --demo.region=qa` |
| Biến môi trường | `DEMO_REGION=qa java -jar app.jar` | `$env:DEMO_REGION='qa'; java -jar .\app.jar` |

Với chuỗi chứa khoảng trắng, ký tự đặc biệt hoặc giá trị JSON, cần thêm dấu nháy phù hợp với shell. Đừng kết luận một câu lệnh Gradle sai chỉ vì copy nguyên cú pháp Unix sang PowerShell.

## 31. Cấu hình `spring.config.location` và thời điểm đọc

Một số thuộc tính Spring Boot được tiêu thụ **rất sớm**, trước hoặc trong quá trình chuẩn bị Config Data:

```text
spring.config.name
spring.config.location
spring.config.additional-location
```

Vì vậy, khi muốn thay đổi nơi Spring Boot tìm file cấu hình, có thể dùng runtime argument:

```bash
java -jar app.jar \
  --spring.config.location=optional:file:./config/
```

hoặc system property JVM ứng dụng:

```bash
java \
  -Dspring.config.location=optional:file:./config/ \
  -jar app.jar
```

Với `bootRun`, cách tường minh:

```bash
./gradlew bootRun \
  --args='--spring.config.location=optional:file:./config/'
```

**Không mặc định** rằng:

```bash
./gradlew bootRun \
  -Dspring.config.location=optional:file:./config/
```

sẽ làm Spring Boot app đọc đúng location, vì `-D` của Gradle chưa chắc được forward tới app JVM.

### `spring.config.location` và đường dẫn tương đối

Đường dẫn `./config/` được giải quyết tương đối với **working directory của ứng dụng**, không nhất thiết với một thư mục bạn tưởng tượng.

`bootRun` có working directory được Gradle task xác định; khi chạy JAR từ terminal, working directory thường là thư mục hiện tại. Nếu cùng một relative path cho kết quả khác nhau, hãy kiểm tra:

```java
System.getProperty("user.dir")
```

trong JVM ứng dụng, cùng task `workingDir` nếu có cấu hình đặc biệt.

## 32. `SPRING_APPLICATION_JSON` là một nguồn khác nữa

Spring Boot cho phép truyền cấu hình JSON thông qua biến môi trường hoặc system property:

Bash:

```bash
SPRING_APPLICATION_JSON='{"demo":{"region":"qa","worker-count":3}}' \
  java -jar app.jar
```

Hoặc:

```bash
java \
  -Dspring.application.json='{"demo":{"region":"qa","worker-count":3}}' \
  -jar app.jar
```

Hoặc:

```bash
java -jar app.jar \
  --spring.application.json='{"demo":{"region":"qa","worker-count":3}}'
```

Các lệnh này đều có thể đưa dữ liệu JSON vào Spring Environment nhưng thông qua các nguồn cụ thể khác nhau.

### Tại sao không nên dùng JSON khi không cần?

Khi một khóa scalar đơn giản có thể truyền bằng:

```bash
java -jar app.jar --demo.region=qa
```

thì nó dễ đọc hơn một JSON lồng trong dấu nháy. `SPRING_APPLICATION_JSON` hữu ích khi môi trường hoặc công cụ triển khai không thuận tiện cho các khóa dấu chấm hay danh sách, nhưng có chi phí về quoting và độ khó debug.

`null` trong JSON cũng không mặc định hoạt động như một lệnh xóa giá trị của nguồn có ưu tiên thấp hơn; `PropertySourcesPropertyResolver` xem property null là thiếu trong nhiều trường hợp.

## 33. Khi build JAR và khi chạy JAR là hai việc khác nhau

Cần tách hai bước triển khai:

### Build

```bash
./gradlew clean bootJar
```

Tạo executable JAR. Các Gradle project properties, `org.gradle.jvmargs`, Gradle daemon và môi trường build tham gia thực hiện task.

### Run

```bash
java -jar build/libs/app.jar --spring.profiles.active=prod
```

Khởi động ứng dụng. Những Spring Boot properties được đọc theo **runtime environment** của lệnh này.

Giữa build và run có thể là:

- Hai terminal khác nhau.
- Hai máy khác nhau.
- CI server và container.
- Nhà phát triển và production host.
- Hai user với các biến môi trường khác nhau.

Vì vậy:

```bash
./gradlew -Pstage=prod bootJar
```

không đồng nghĩa:

```bash
java -jar app.jar --spring.profiles.active=prod
```

trừ khi build script đã chủ động mã hóa profile vào artifact hoặc script triển khai đã cung cấp profile cho runtime. Không nên ngầm áp giả định đó cho toàn bộ dự án.

## 34. `bootRun` tiện cho phát triển, không phải bản sao hoàn toàn của packaged deployment

`bootRun` thường chạy ứng dụng với runtime classpath của source set `main`, không đòi hỏi tạo một executable JAR trước.

Khi chạy JAR:

```bash
java -jar build/libs/app.jar
```

classpath, working directory, tài nguyên được đóng gói và môi trường deploy có thể khác. Do đó, cùng một property có thể đến từ nguồn khác nếu bạn không giữ cấu hình giống nhau.

Các khác biệt có thể gồm:

- Tệp cấu hình ngoài JAR.
- Working directory và đường dẫn tương đối.
- Biến môi trường của shell/CI/container.
- JVM options từ launcher hoặc task.
- Runtime profile.
- Application arguments.
- Build source resources được cập nhật chưa.
- Sự hiện diện của devtools hoặc dependency chỉ dành cho phát triển.

Khi lỗi chỉ xuất hiện ở packaged JAR, hãy kiểm tra những khác biệt này trước khi kết luận cơ chế Binder thay đổi.

## 35. Gradle `-Dorg.gradle.jvmargs` không thay thế `jvmArgs` của app

Cặp ví dụ:

```bash
./gradlew bootRun -Dorg.gradle.jvmargs='-Xmx2g'
```

và trong `build.gradle`:

```groovy
tasks.named("bootRun") {
    jvmArgs("-Xmx2g")
}
```

Không nên coi hai cách này tương đương.

Cách đầu liên quan cách Gradle cấu hình JVM cho **quá trình build/daemon**. Cách sau cấu hình JVM mà `bootRun` dùng cho **ứng dụng**.

Thực tế, Gradle có thể phải khởi tạo daemon mới khi thay đổi JVM settings; hành vi cụ thể phụ thuộc cấu hình Gradle. Điều quan trọng vẫn là **ranh giới process**.

Muốn heap runtime của JAR, dùng:

```bash
java -Xmx2g -jar app.jar
```

Muốn heap khi `bootRun`, dùng JavaExec task configuration hoặc cơ chế launch app phù hợp.

## 36. Phân biệt system property với Gradle project property trong build.gradle

Trong Groovy DSL:

```groovy
def projectValue = project.findProperty("demoRegion")
def gradleSystemValue = System.getProperty("demo.region")

println("projectValue=" + projectValue)
println("gradleSystemValue=" + gradleSystemValue)
```

Với:

```bash
./gradlew -PdemoRegion=eu-west-1 -Ddemo.region=qa help
```

hai giá trị khác nhau:

```text
projectValue=eu-west-1
gradleSystemValue=qa
```

Nhưng đây đều là dữ liệu **bên trong quá trình Gradle**, chưa phải một chứng minh rằng Spring Boot app đã nhận.

### Provider API

Gradle có thể truy cập project property và system property theo dạng lazy:

```groovy
providers.gradleProperty("demoRegion")
providers.systemProperty("demo.region")
```

Các provider này phù hợp khi kết nối giá trị Gradle tới cấu hình task. Đừng coi `providers.systemProperty(...)` là một API của Spring `Environment`.

## 37. Kiểm tra thứ tự ưu tiên với một ma trận thực hành

Dùng ứng dụng ở phần 17, thử những nguồn:

| `application.properties` | OS env | JVM app `-D` | Spring app `--` | Giá trị Spring có hiệu lực (mặc định) |
| --- | --- | --- | --- | --- |
| `from-file` | Không | Không | Không | `from-file` |
| `from-file` | `from-env` | Không | Không | `from-env` |
| `from-file` | `from-env` | `from-jvm` | Không | `from-jvm` |
| `from-file` | `from-env` | `from-jvm` | `from-cli` | `from-cli` |
| `from-file` | Không | `from-jvm` | `from-cli` | `from-cli` |

Ma trận áp dụng cho những nguồn được liệt kê và thứ tự mặc định của Spring Boot 3.3; các PropertySource tùy chỉnh, test properties, `SPRING_APPLICATION_JSON`, servlet/JNDI hoặc cấu hình đặc biệt có thể làm kết quả khác.

**Không đặt Gradle `-P` hay `-D` vào ma trận như Spring input tự động.** Nếu muốn kiểm tra chúng, thêm một hàng riêng chỉ khi build script có bridge.

## 38. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân điển hình | Cách sửa |
| --- | --- | --- |
| `-PdemoRegion=qa` nhưng app vẫn nhận mặc định | Gradle project property không tự chuyển vào app | Dùng `--args` hoặc task `systemProperty`/`args` |
| `./gradlew bootRun -Ddemo.region=qa` không hiệu lực | `-D` được đặt ở phía Gradle JVM | Dùng `--args` hoặc bridge rõ ràng |
| `System.getProperty` null nhưng Spring Environment có giá trị | Giá trị đến từ CLI/YAML/env, không phải Java system property | Dùng `Environment`/Binder để xem giá trị Spring |
| `java -jar app.jar -Ddemo.region=qa` không hiệu lực | `-D` đứng sau JAR | Đưa `-D` trước `-jar` |
| `--info` không tăng log Spring | `--info` là Gradle option | Dùng `--args='--logging.level.root=INFO'` |
| `--debug` tăng log Gradle nhưng không bật Boot debug | Option áp vào Gradle | Dùng `bootRun --args='--debug'` |
| `org.gradle.jvmargs=-Xmx2g` nhưng app vẫn thiếu heap | Cấu hình JVM Gradle, không phải app | Dùng `bootRun.jvmArgs` hoặc `java -Xmx2g` |
| Truyền `--spring.profiles.active=dev` qua `-P` không hiệu lực | Build property không tự thành runtime property | Dùng Spring CLI trực tiếp |
| Không thấy profile-specific YAML | Active profile không được cấp cho app JVM | Kiểm tra `Environment#getActiveProfiles()` |
| Build script nhận đúng project property nhưng app không | Thiếu bridge hoặc task không chạy như dự kiến | Xem `bootRun` configuration |
| Dòng lệnh có khoảng trắng làm sai giá trị | Shell và Gradle parse arguments khác nhau | Dùng nháy đúng hoặc cấu hình `args` theo danh sách |
| CI chạy được nhưng máy developer không | Khác biến môi trường, JDK, workingDir, artifact | So sánh tầng runtime, không chỉ Gradle options |
| `System.getenv` khác Spring `Environment` | Có nhiều nguồn precedence | Kiểm tra toàn bộ `PropertySources` |
| Java heap khác kỳ vọng | Nhầm Gradle daemon với app JVM | Quan sát JVM app và cách nó được khởi chạy |
| Đối số ứng dụng đúng nhưng Spring bỏ qua | `setAddCommandLineProperties(false)` | Kiểm tra cấu hình SpringApplication |
| Tệp config ngoài không được tìm thấy | Relative path/working directory khác | Kiểm tra `user.dir`/`workingDir` |
| Cấu hình bị CLI ghi đè dù file đúng | CLI có ưu tiên cao hơn | Xác nhận giá trị cuối, tránh “sửa” file vô hiệu |
| `-D` không đúng trong một task JavaExec tùy chỉnh | Task chưa được cấu hình systemProperty | Chỉ rõ `systemProperty`/`jvmArgs` cho task đó |

## 39. Chẩn đoán từng lớp thay vì thay thử ngẫu nhiên

Khi Spring Boot không nhận property, hãy kiểm tra theo thứ tự.

### Bước 1 — Lệnh có được shell chia đúng không?

- Có đặt nháy đúng quanh argument chứa khoảng trắng?
- Có ký tự `$` hoặc `&` bị shell xử lý trước không?
- Đang dùng Bash, zsh, PowerShell hay cmd?
- `--args` có thực sự là một task option của `bootRun` trong lệnh được dùng không?

### Bước 2 — Giá trị dừng ở Gradle hay tới JVM app?

- `-P` được build script đọc chưa?
- `-D` của Gradle có được forward chưa?
- Task `bootRun` có cấu hình `systemProperty`, `jvmArgs`, `args` đúng không?
- Có dùng lệnh `java -jar` trực tiếp hay task JavaExec?

### Bước 3 — Java system property và environment variable có mặt chưa?

Trong JVM app:

```java
System.getProperty("demo.region")
System.getenv("DEMO_REGION")
```

Không in mọi property hoặc secret. Chỉ kiểm tra một khóa mẫu không nhạy cảm.

### Bước 4 — Spring Environment chọn nguồn nào?

```java
environment.getProperty("demo.region")
```

Nếu khác `System.getProperty`, kiểm tra CLI, biến môi trường, Config Data và các nguồn khác.

### Bước 5 — Binder và validation có thành công?

Ngay cả khi giá trị cuối đã đúng, có thể cấu hình sai kiểu:

```properties
demo.worker-count=abc
```

hoặc đúng kiểu nhưng không hợp lệ:

```properties
demo.worker-count=-1
```

Đây là vấn đề conversion và validation, không còn là Gradle property forwarding.

### Bước 6 — Có phụ thuộc runtime khác không?

Ví dụ endpoint hợp lệ nhưng service ngoài không truy cập được, hoặc cổng được lấy đúng nhưng đã bị tiến trình khác chiếm. Không coi mọi lỗi startup là lỗi tham số Gradle.

## 40. Thử nghiệm với `ApplicationArguments`

`ApplicationArguments` hữu ích vì nó cho biết đối số **thực sự tới main**.

Ví dụ:

```java
@Bean
ApplicationRunner printArgs(ApplicationArguments applicationArguments) {
    return args -> {
        System.out.println(
                applicationArguments.getOptionNames());
        System.out.println(
                applicationArguments.getNonOptionArgs());
    };
}
```

Đặt method bên trong một lớp `@Configuration` hoặc `@SpringBootApplication`.

Với:

```bash
java -jar app.jar --demo.region=qa job-123
```

có thể quan sát:

```text
optionNames chứa demo.region
nonOptionArgs chứa job-123
```

`-Ddemo.region=qa` đặt trước `-jar` không xuất hiện trong `ApplicationArguments`, vì Java launcher đã sử dụng nó để tạo system property trước khi gọi main.

Ngược lại, nếu đặt chuỗi `-Ddemo.region=qa` sau JAR, nó có thể được đưa vào non-option args hoặc được code CLI xử lý riêng, nhưng không trở thành system property của JVM.

## 41. Cách tránh lỗi khi dùng Gradle Wrapper

Trong một dự án đã có Gradle Wrapper, nên dùng:

Bash/Unix:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Thay vì phụ thuộc vào một bản Gradle cài toàn máy có phiên bản khác với dự án:

```bash
gradle bootRun
```

Wrapper giúp chọn phiên bản Gradle theo cấu hình project, giúp kết quả gần nhất quán giữa developer và CI.

Tuy nhiên, Wrapper không tự đồng bộ **JDK đang dùng**, biến môi trường OS, secret, working directory hoặc những property do CI cung cấp. Khi chẩn đoán cấu hình runtime, vẫn phải kiểm tra các đầu vào thực tế.

## 42. Truyền property chứa khoảng trắng và ký tự đặc biệt

Giá trị minh họa:

```text
demo.message=hello Spring Boot
```

Với JAR trực tiếp trên Bash:

```bash
java -jar app.jar '--demo.message=hello Spring Boot'
```

Trên PowerShell:

```powershell
java -jar .\app.jar '--demo.message=hello Spring Boot'
```

Trong `bootRun`, một cách rõ ràng là:

```groovy
tasks.named("bootRun") {
    args("--demo.message=hello Spring Boot")
}
```

Cách này tạo một phần tử argument, không cần người gọi tự dựng chuỗi escaping nhiều tầng.

Nếu muốn điều khiển qua CLI Gradle, cần truyền giá trị task `--args` đúng theo quy tắc shell và parser của Gradle. Với giá trị phức tạp/JSON, có thể cân nhắc file cấu hình ngoài, biến môi trường hoặc `SPRING_APPLICATION_JSON` nếu phù hợp.

**Không đưa password/token vào command-line examples hoặc log.** Hệ điều hành, shell history hoặc công cụ giám sát có thể ghi lại đối số tiến trình.

## 43. Thiết kế triển khai cho container và Kubernetes

Trong container, nhiều hệ thống không có Gradle trong runtime image. Build được thực hiện trước:

```bash
./gradlew bootJar
```

Runtime image chỉ chứa Java runtime và JAR, rồi chạy:

```bash
java -jar app.jar
```

hoặc dùng environment variables do container platform cấp:

```text
SPRING_PROFILES_ACTIVE=prod
DEMO_REGION=ap-southeast-1
```

Trong mô hình này:

- Gradle `-P` chỉ có ý nghĩa ở giai đoạn build.
- `org.gradle.jvmargs` không có tác dụng lên container runtime nếu Gradle không chạy ở đó.
- JVM flags của process app có thể đặt trong entrypoint/launcher được kiểm soát.
- Spring Boot configuration nên đến từ biến môi trường, Config Data, volume/config tree, hoặc args theo quy ước triển khai.

Dùng cùng JAR cho nhiều môi trường giúp giảm rủi ro chênh lệch artifact, nhưng vẫn cần kiểm soát cấu hình cuối cùng và chính sách bảo mật.

### 43.1. CI pipeline có hai giai đoạn

Ví dụ:

```text
CI build stage
    ./gradlew test bootJar -PbuildFlavor=release
            |
            v
    artifact: app.jar
            |
            v
Deploy stage
    java -Xmx512m -jar app.jar --spring.profiles.active=prod
```

`buildFlavor` có thể ảnh hưởng build nếu build script sử dụng. `spring.profiles.active` ở bước deploy được app đọc lúc chạy. Không nên suy ra profile production từ việc build có chữ `release`.

## 44. Bài tập 1 — phân loại 10 tham số

Với các chuỗi:

```text
-Pstage=qa
-Ddemo.region=qa
--offline
--info
--args=--demo.region=qa
jvmArgs("-Xmx512m")
systemProperty("demo.region", "qa")
args("--demo.region=qa")
java -Ddemo.region=qa -jar app.jar
java -jar app.jar --demo.region=qa
```

**Yêu cầu:** phân loại thành Gradle build input, Gradle task forwarding, JVM option của app hoặc application arguments.

**Đáp án:**

- `-Pstage=qa`, `-Ddemo.region=qa` khi đứng sau `gradlew`, `--offline`, `--info`: thuộc phía Gradle.
- `--args` của `bootRun`, `args(...)`: chuyển application arguments tới app.
- `jvmArgs(...)`, `systemProperty(...)` trong `bootRun`: thiết lập JVM options/system properties cho app process.
- `java -D... -jar`: Java system property của app.
- `java -jar ... --demo.region=qa`: Spring Boot application argument.

## 45. Bài tập 2 — Gradle daemon và heap

Có trong `gradle.properties`:

```properties
org.gradle.jvmargs=-Xmx3g
```

**Hỏi:** JVM ứng dụng khi chạy `bootRun` có chắc chắn heap tối đa 3 GB không?

**Đáp án:** Không. Thuộc tính đó cấu hình JVM dành cho Gradle. App JVM do `bootRun` tạo có thể có JVM options/heap khác. Muốn điều khiển app heap, cấu hình `bootRun.jvmArgs`, `maxHeapSize` hoặc runtime Java launcher tương ứng.

## 46. Bài tập 3 — profile không được bật

Lệnh:

```bash
./gradlew bootRun -Dspring.profiles.active=prod
```

Nhưng ứng dụng vẫn dùng profile mặc định.

**Hỏi:** Nguyên nhân có thể là gì?

**Đáp án:** `-D` được đưa vào phía JVM Gradle. Task `bootRun` không tự copy toàn bộ system properties sang JVM ứng dụng. Dùng:

```bash
./gradlew bootRun --args='--spring.profiles.active=prod'
```

hoặc cấu hình:

```groovy
tasks.named("bootRun") {
    systemProperty("spring.profiles.active", "prod")
}
```

## 47. Bài tập 4 — `System.getProperty` và Environment khác nhau

Lệnh:

```bash
java -Ddemo.region=jvm -jar app.jar --demo.region=cli
```

**Hỏi:** hai API trả gì?

**Đáp án:**

```text
System.getProperty("demo.region") -> jvm
environment.getProperty("demo.region") -> cli
```

với Spring Boot command-line properties mặc định và không có nguồn ưu tiên bất thường khác.

## 48. Bài tập 5 — Gradle `-P` không chuyển vào runtime

Lệnh:

```bash
./gradlew -PdeployRegion=ap-southeast-1 bootRun
```

Java app vẫn đọc `demo.region=from-file`.

**Hỏi:** có lỗi Binder không?

**Đáp án:** Chưa có bằng chứng lỗi Binder. Gradle project property không tự map sang `demo.region`. Cần bridge:

```groovy
tasks.named("bootRun") {
    systemProperty("demo.region",
            providers.gradleProperty("deployRegion").get())
}
```

Hoặc truyền:

```bash
./gradlew bootRun --args='--demo.region=ap-southeast-1'
```

## 49. Bài tập 6 — đặt `-D` sau JAR

Lệnh:

```bash
java -jar app.jar -Ddemo.mode=qa
```

**Hỏi:** `System.getProperty("demo.mode")` có chắc là `qa` không?

**Đáp án:** Không. Java launcher đã gặp `-jar` và tên JAR; chuỗi sau đó là application argument, không phải JVM option. Đặt `-Ddemo.mode=qa` trước `-jar` hoặc dùng `--demo.mode=qa` sau JAR nếu muốn Spring Boot application property.

## 50. Bài tập 7 — biến môi trường hay Gradle property?

Cho hai biến:

```text
DEMO_MODE=qa
ORG_GRADLE_PROJECT_deployStage=qa
```

**Hỏi:** biến nào hướng tới Spring Boot runtime, biến nào hướng tới Gradle project property?

**Đáp án:** `DEMO_MODE` là biến môi trường có thể được Spring Boot bind thành `demo.mode`. `ORG_GRADLE_PROJECT_deployStage` là một phương thức Gradle nhận project property `deployStage`; nó không tự thành property `demo.stage` trong Spring Environment.

## 51. Bài tập 8 — logger

Lệnh:

```bash
./gradlew bootRun --debug
```

**Hỏi:** có chắc Spring Boot application ghi log DEBUG không?

**Đáp án:** Không. Cờ `--debug` thuộc Gradle. Nếu muốn Spring Boot nhận đối số `--debug`, dùng:

```bash
./gradlew bootRun --args='--debug'
```

hoặc đặt các cấu hình `logging.level.*` phù hợp cho ứng dụng.

## 52. Bài tập 9 — lưu giá trị bí mật

Một nhóm đề xuất:

```bash
./gradlew -PapiPassword=very-secret bootRun
```

và forward sang Java system property.

**Hỏi:** có nên dùng phương pháp này cho production secret không?

**Đáp án:** Không nên dùng CLI argument lộ trực tiếp hoặc Gradle project property theo cách này như giải pháp mặc định. Chúng có thể xuất hiện trong history/process list/build logs. Ưu tiên secret manager, file mount được bảo vệ hoặc cơ chế cấp secret của nền tảng, với quyền truy cập và không log giá trị.

## 53. Bài tập 10 — ứng dụng trong CI

CI chạy:

```bash
./gradlew -Pstage=production bootJar
```

sau đó deploy:

```bash
java -jar app.jar
```

**Hỏi:** ứng dụng chắc chắn có `spring.profiles.active=production` không?

**Đáp án:** Không. `-Pstage` thuộc build; runtime chỉ có profile production nếu có nguồn cấu hình/logic bridge khác. Muốn rõ ràng:

```bash
java -jar app.jar --spring.profiles.active=prod
```

hoặc cấp `SPRING_PROFILES_ACTIVE=prod` trong môi trường triển khai.

## 54. Checklist trước khi chạy một Spring Boot app

- [ ] Lệnh đang chạy `gradlew bootRun` hay `java -jar`?
- [ ] Tham số đang dành cho Gradle, JVM ứng dụng hay Spring Boot?
- [ ] Với Gradle project property, có bridge rõ ràng sang app chưa?
- [ ] Với Gradle `-D`, có nhầm JVM Gradle với JVM con không?
- [ ] Với Java `-D`, nó đã đứng trước `-jar` chưa?
- [ ] Với `bootRun`, đã dùng `--args` khi muốn application CLI chưa?
- [ ] Với JVM heap/GC, đã cấu hình đúng process ứng dụng chưa?
- [ ] Shell hiện tại là Bash, PowerShell hay cmd?
- [ ] Các chuỗi có dấu cách/ký tự đặc biệt đã được quote đúng chưa?
- [ ] Biến môi trường có được truyền vào process ứng dụng thực không?
- [ ] Cấu hình có bị nguồn ưu tiên cao hơn ghi đè không?
- [ ] Active profiles có đúng không?
- [ ] File ngoài JAR có được giải quyết từ working directory đúng không?
- [ ] `System.getProperty`, `System.getenv` và `Environment` có đang bị dùng thay thế nhau không?
- [ ] Có vô tình log token, password hoặc toàn bộ arguments không?
- [ ] Có thử chạy packaged JAR ở môi trường gần giống deployment chưa?
- [ ] Có kiểm thử kết quả của `bootRun` và lệnh `java -jar` thay vì suy luận chỉ từ build script không?

## 55. Tổng kết

Chìa khóa là **nhìn đúng process và đúng người phân tích tham số**:

```text
./gradlew -PdeployRegion=qa bootRun
      |
      v
Gradle project property (build logic)

./gradlew -Ddemo.region=qa bootRun
      |
      v
System property phía Gradle JVM

./gradlew bootRun --args='--demo.region=qa'
      |
      v
Application arguments tới main của Spring Boot

tasks.named("bootRun") {
    systemProperty("demo.region", "qa")
}
      |
      v
Java system property của JVM ứng dụng

java -Ddemo.region=qa -jar app.jar
      |
      v
Java system property của JVM ứng dụng

java -jar app.jar --demo.region=qa
      |
      v
Spring Boot command-line property
```

Hãy ghi nhớ năm quy tắc:

1. **`-P` và `-D` của lệnh Gradle thuộc tầng build**, không tự trở thành Spring Boot properties.
2. **`bootRun --args` chuyển application arguments**, còn `bootRun.systemProperty`/`jvmArgs` điều khiển JVM con mà task khởi chạy.
3. **`java -D... -jar` và `java -jar ... --...` là hai nguồn khác nhau** nhưng đều có thể được Spring Boot Environment đọc.
4. **Spring Boot áp dụng PropertySource precedence**, vì vậy `Environment#getProperty` có thể trả giá trị khác `System.getProperty`.
5. **Build-time và runtime phải được phân biệt**, đặc biệt khi tạo JAR trong CI rồi chạy ở container hoặc máy chủ khác.

Nếu ứng dụng “không nhận tham số”, đừng sửa ngay Binder hoặc file YAML. Hãy xác định trước tham số đã đến đúng **shell → Gradle → JVM ứng dụng → Spring Boot** hay chưa. Nhiều lỗi cấu hình sẽ trở nên dễ hiểu ngay khi nhận diện chính xác ranh giới này.

## Tài liệu tham khảo

- Spring Boot 3.3 — Externalized Configuration và PropertySource Order: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Running Your Application with Gradle / `bootRun`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Spring Boot 3.3 — Gradle Plugin Reference: https://docs.spring.io/spring-boot/3.3/gradle-plugin/index.html
- Gradle — Command-Line Interface (`-P`, `-D`, task options): https://docs.gradle.org/current/userguide/gradle_command_line.html
- Gradle — Build Environment Configuration (project/system properties): https://docs.gradle.org/current/userguide/build_environment.html
- Gradle JavaExec API — `args`, `systemProperty`, `jvmArgs`, `environment`: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/JavaExec.html
- Spring Boot 3.3 — ApplicationArguments API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
