# Phân biệt JVM chạy Gradle daemon với toolchain biên dịch

Khi nâng cấp Java trong một dự án Gradle, câu hỏi “Dự án đang dùng JDK nào?” thường chưa đủ để chẩn đoán sự cố. Một build có thể được **Gradle daemon chạy bằng JDK 17**, trong khi source code được **biên dịch bằng JDK 21**, compiler được cấu hình để chỉ dùng API **Java 11**, và bài integration test lại chạy bằng **JDK 11**. Cả bốn chi tiết đều có thể đúng trong cùng một pipeline.

Nếu nhầm các vai trò này, đội phát triển dễ gặp tình huống: đổi `JAVA_HOME` nhưng version class file không đổi; cấu hình `sourceCompatibility = 11` nhưng code vẫn gọi API Java 17; `gradle --version` báo một JDK còn compiler lại thuộc JDK khác; build chạy tốt trên máy developer nhưng lỗi trên CI; hoặc unit test pass trên JDK mới trong khi ứng dụng production chạy trên JDK cũ và gặp `NoSuchMethodError`.

Bài học trong chủ đề **Java Advance Compatibility Migration** này giải thích chi tiết sự khác biệt giữa JVM chạy Gradle daemon và Java toolchain dùng cho compiler, phân biệt chúng với JVM chạy test/ứng dụng, hướng dẫn cấu hình Groovy/Kotlin DSL, cung cấp các cách quan sát thực tế và một quy trình migration có thể tái hiện trên máy phát triển lẫn CI.

## 1. Mô hình tổng quan: một build, nhiều JVM

Hãy xem ví dụ giả định:

```text
Terminal / IDE
    |
    | ./gradlew build
    v
Gradle launcher / client
    |
    v
Gradle daemon JVM (JDK 17)
    |-- Gradle core, build scripts và build plugins
    |-- Dependency resolution, cấu hình và điều phối task
    |
    +--> JavaCompile task
    |       |
    |       +--> Java compiler toolchain: JDK 21
    |                 |
    |                 +--> options.release = 11
    |                 +--> Bytecode Java 11 và API nền tảng Java 11
    |
    +--> Test task
    |       |
    |       +--> Test worker JVM: JDK 11
    |
    +--> JavaExec / application run
            |
            +--> Launcher JVM: cấu hình riêng theo task
```

Ở đây, **JDK 17 không tự động quyết định bytecode target** và **JDK 21 không tự động chứng minh ứng dụng chạy được trên Java 11**. Mỗi lựa chọn điều khiển một phạm vi khác nhau.

| Thành phần | Chạy gì? | Cách lựa chọn thường gặp | Rủi ro nếu nhầm |
|---|---|---|---|
| Gradle launcher/client | Khởi tạo lệnh Gradle và liên lạc daemon | JVM của shell/IDE, wrapper và cấu hình Gradle | Lệnh không khởi động hoặc dùng nhầm môi trường |
| Gradle daemon JVM | Gradle engine, build scripts và plugins | Gradle JVM settings, daemon criteria, `org.gradle.java.home`, môi trường theo phiên bản Gradle | Plugin/build logic không tương thích JDK |
| Java compiler toolchain | `javac` hoặc compiler Java được task chọn | `java.toolchain` và `JavaCompile.javaCompiler` | Compile bằng JDK ngoài dự kiến |
| Language/bytecode/API target | Mức mã nguồn, class file, API Java nền tảng | `options.release`, source/target compatibility | Artifact không chạy trên runtime mục tiêu |
| Test worker JVM | JUnit/TestNG và code được test | `Test.javaLauncher`, toolchain/default task settings | Test chạy trên JDK khác production |
| JavaExec/application JVM | Main class, integration utilities, app runtime | `JavaExec.javaLauncher` hoặc launcher tương ứng | Lỗi chỉ xuất hiện khi triển khai |
| Production runtime JVM | Ứng dụng được phát hành | Container image, installer, app server hoặc JRE/JDK đích | Không tương thích bytecode, API hoặc hành vi |

Một số tác vụ biên dịch có thể dùng compiler API ngay trong process hoặc worker/daemon khác tùy plugin và cấu hình. Do đó, **“compiler toolchain” là JDK được Gradle chọn cho tác vụ compile**, không nhất thiết luôn là một process `javac` riêng biệt ở mọi trường hợp.

## 2. Gradle daemon JVM là gì?

Gradle daemon là một tiến trình JVM tồn tại để xử lý các build, tái sử dụng trạng thái và giảm chi phí khởi động. Nó thực thi phần lớn logic của Gradle:

- Parse và evaluate `settings.gradle`/`build.gradle` hoặc các bản Kotlin DSL.
- Nạp Gradle core và build plugins.
- Resolve dependency graph và cấu hình task.
- Quản lý cache, incremental compilation và task execution.
- Khởi tạo hoặc điều phối compiler, test process, worker process và công cụ ngoài.
- Thực thi custom task và phần code chạy ngay trong Gradle build process.

**JDK chạy daemon phải tương thích với phiên bản Gradle và plugin build.** Ví dụ, một phiên bản Gradle cũ có thể không khởi động được dưới JDK rất mới, ngay cả khi toolchain mà dự án muốn dùng để compile là một JDK cũ.

### 2.1. Daemon JVM không mặc nhiên là compiler JVM

Ví dụ máy có:

```text
C:\jdks\jdk-17
C:\jdks\jdk-21
```

Gradle daemon được khởi chạy dưới JDK 17. Dự án khai báo toolchain JDK 21 để compile. Khi đó:

- Gradle/build plugins chạy trên JVM 17.
- `JavaCompile` có thể sử dụng `javac` JDK 21.
- `options.release = 11` có thể khiến compiler tạo bytecode và kiểm tra API nền tảng theo Java 11.
- Test JVM cần được xác định riêng.

Vì vậy, lệnh kiểm tra daemon JVM **không phải** phương pháp duy nhất để kết luận compiler version.

### 2.2. Vì sao Gradle daemon có thể tiếp tục tồn tại sau khi đổi môi trường?

Daemon có thể được tái sử dụng cho các lần build khi các tiêu chí tương thích phù hợp. Việc đổi biến môi trường, Gradle JVM setting hoặc daemon criteria có thể khiến Gradle chọn một daemon khác. Trong quá trình điều tra, người dùng thường cần kiểm tra JVM thực tế được chọn thay vì dựa vào một cửa sổ terminal đã mở từ trước.

Các lệnh hỗ trợ:

```bash
./gradlew --status
./gradlew --stop
```

`--status` cho biết tình trạng daemon Gradle thuộc phạm vi quản lý liên quan; `--stop` yêu cầu dừng daemon tương ứng. Không nên coi việc dừng daemon là biện pháp sửa tận gốc cho lỗi compiler/API, nhưng nó có thể giúp loại bỏ nhầm lẫn trong quá trình đổi cấu hình JVM.

## 3. Chọn JDK cho Gradle daemon

Đường đi cấu hình phụ thuộc version Gradle và cách khởi chạy.

### 3.1. `JAVA_HOME` và Java trên `PATH`

Khi chạy Gradle từ terminal, `JAVA_HOME` thường tham gia xác định Java dùng để khởi động Gradle nếu không có cấu hình JVM riêng ưu tiên hơn.

Trên Linux/macOS:

```bash
echo "$JAVA_HOME"
which java
java -version
./gradlew --version
```

Trên Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java
java -version
.\gradlew.bat --version
```

Cần phân biệt:

- `java -version` trong terminal thường là Java được tìm theo shell/PATH.
- `$JAVA_HOME` hoặc `%JAVA_HOME%` chỉ là một giá trị môi trường.
- `./gradlew --version` cho biết thông tin Gradle và JVM Gradle thấy/chọn, nhưng **không khẳng định mọi JavaCompile task dùng JDK đó**.
- Một IDE có thể khởi chạy Gradle bằng Gradle JVM setting riêng, không giống terminal.

### 3.2. `org.gradle.java.home`

Trong các môi trường Gradle hỗ trợ, có thể chỉ định Java home cho Gradle build daemon bằng property:

```properties
# gradle.properties
org.gradle.java.home=/opt/jdks/jdk-17
```

Đây là ví dụ đường dẫn Linux. Trên Windows, cần sử dụng định dạng đường dẫn phù hợp với file properties và môi trường; không chép nguyên đường dẫn Linux.

Điểm quan trọng: **`org.gradle.java.home` chọn JDK cho Gradle process/daemon theo cơ chế tương ứng**, không phải khai báo “hãy tạo bytecode Java 17” cho mọi module.

Nếu đồng thời có Gradle daemon JVM criteria, cấu hình IDE hoặc cơ chế lựa chọn JVM khác, cần kiểm tra quy tắc ưu tiên của **phiên bản Gradle đang dùng** thay vì tự suy đoán.

### 3.3. Gradle JVM trong IDE

IntelliJ IDEA hoặc IDE khác có thể có các lựa chọn riêng:

- Project SDK: JDK mà IDE dùng để phân tích hoặc chạy một số thao tác của project.
- Gradle JVM: JDK dùng để thực hiện Gradle build/import.
- Run configuration JRE: JDK dùng khi chạy chương trình từ IDE.
- Toolchain trong Gradle script: JDK mà `JavaCompile`, `Test` và những task tương ứng có thể chọn.

Các giá trị trên có thể khác nhau hoàn toàn. Ví dụ, IDE hiển thị Project SDK là 21, nhưng Gradle JVM là 17 và JavaCompile toolchain yêu cầu 11. Nếu chỉ nhìn Project SDK rồi khẳng định build dùng Java 21 thì có thể sai.

### 3.4. Gradle wrapper và giới hạn phiên bản

`gradlew`/`gradlew.bat` gọi **phiên bản Gradle đã được dự án ghim trong wrapper**. Wrapper không tự nâng cấp Gradle chỉ vì hệ thống cài JDK mới.

Một ví dụ về giới hạn thực tế:

1. Máy cài JDK 21.
2. Dự án dùng Gradle quá cũ, không hỗ trợ chạy bằng JDK 21.
3. Chạy Gradle có thể thất bại ngay ở startup/configuration.
4. Dù build script đặt toolchain Java 11, điều đó không cứu được Gradle engine chưa khởi động.

Cần kiểm tra **ma trận tương thích giữa phiên bản Gradle wrapper, daemon JDK và compiler toolchain JDK**. Một số Gradle release hỗ trợ dùng JDK mới làm toolchain trước khi hỗ trợ chính JDK đó để chạy Gradle engine; không nên đồng nhất hai khả năng.

### 3.5. Daemon JVM criteria

Những Gradle release hiện đại hỗ trợ cơ chế **Daemon JVM criteria** để khai báo yêu cầu JVM dùng chạy Gradle daemon, thường thông qua metadata đặt dưới thư mục `gradle/` như `gradle-daemon-jvm.properties`. Đây là lựa chọn riêng với Java toolchain dùng cho compilation.

Nếu dự án đang dùng cơ chế này:

- Xác định version/vendor JVM mà criteria yêu cầu.
- Kiểm tra cơ chế tìm hoặc provision JVM.
- Xác định quy tắc tương tác với `JAVA_HOME`, `org.gradle.java.home` và IDE theo Gradle version thực tế.
- Đừng coi file daemon criteria là thay thế cấu hình `java.toolchain`.

Mục tiêu là làm JVM chạy Gradle có thể được chọn một cách tái hiện trong CI, đồng thời compiler vẫn được quản lý độc lập.

## 4. Java toolchain của Gradle là gì?

Java toolchain là cơ chế để Gradle **tìm hoặc cung cấp JDK đáp ứng yêu cầu cho các tác vụ Java** mà không bắt buộc dùng cùng JDK với daemon.

Cấu hình cơ bản Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Trong Kotlin DSL:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

Ví dụ này yêu cầu toolchain Java 17 cho các tác vụ Java dùng thiết lập đó. **Nó không buộc Gradle daemon phải chạy bằng JDK 17.**

### 4.1. Toolchain mô tả nhiều hơn số phiên bản

Ngoài `languageVersion`, một số cấu hình có thể đặt vendor hoặc implementation theo API Gradle mà phiên bản đang dùng hỗ trợ.

Ví dụ Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
```

Cấu hình cụ thể còn phụ thuộc những vendor matchers được Gradle version hỗ trợ. Dự án có yêu cầu FIPS, HSM/native provider hoặc vendor đặc thù nên ghi rõ chính sách lựa chọn, không chỉ chọn “bất kỳ JDK 17 nào”.

### 4.2. Gradle tìm JDK toolchain ở đâu?

Tùy Gradle release và cấu hình:

- Các JDK được cài ở thư mục hệ điều hành chuẩn.
- `JAVA_HOME` và những vị trí JDK khác mà Gradle dò được.
- Các đường dẫn được khai báo trong Gradle properties.
- Tích hợp với môi trường quản lý Java như SDKMAN!/asdf/IDE nếu Gradle phát hiện phù hợp.
- Toolchain provisioning tự động qua resolver/repository đã được cấu hình theo Gradle version tương ứng.

Với dự án cần build offline hoặc có kiểm soát supply chain, nên ghim nguồn tải/provision và biết các JDK thực tế có mặt trên CI runner.

Ví dụ property khai báo nhiều installation paths:

```properties
org.gradle.java.installations.paths=/opt/jdk-11,/opt/jdk-17,/opt/jdk-21
```

Danh sách có thể khác nhau giữa OS. Các path này là nơi Gradle tìm JDK toolchain, **không có nghĩa daemon JVM tự chuyển sang một JDK trong danh sách**.

Có thể cấu hình cách Gradle phát hiện JDK để phục vụ môi trường doanh nghiệp, nhưng cần kiểm tra behavior chính xác theo Gradle version và settings thực tế.

### 4.3. Toolchain không tự bảo đảm runtime tương thích

Nếu compiler toolchain là JDK 21, mặc định có thể biên dịch source Java 21 và dùng API Java 21 nếu không có ràng buộc khác. Nếu ứng dụng phải chạy bằng Java 11, chỉ đặt compiler toolchain JDK 21 **không đủ** để tạo artifact tương thích Java 11.

Cần chọn language/bytecode/API release và kiểm thử runtime target như giải thích tiếp theo.

## 5. Phân biệt compiler JDK, `sourceCompatibility`, `targetCompatibility` và `options.release`

Đây là điểm dễ nhầm nhất khi nâng JDK.

| Tùy chọn | Điều khiển chính | Không tự bảo đảm điều gì? |
|---|---|---|
| `java.toolchain.languageVersion` | JDK được chọn làm toolchain cho tác vụ Java | Không ấn định API/bytecode cũ khi compiler có mức mới |
| `sourceCompatibility` | Mức ngôn ngữ Java cho source | Không giới hạn JDK API platform mà compiler nhìn thấy |
| `targetCompatibility` | Phiên bản class file được tạo | Không chứng minh API mới không bị gọi |
| `options.release` | Ràng buộc source language, class file và API nền tảng theo Java release chỉ định | Không bảo đảm dependency bên thứ ba hoặc hành vi runtime tương thích |
| `Test.javaLauncher` | JDK chạy test worker | Không thay compile bytecode của project đã tạo |
| `JavaExec.javaLauncher` | JDK chạy ứng dụng/tác vụ JavaExec | Không thay daemon JVM hoặc compiler mặc định |

### 5.1. Rủi ro dùng `sourceCompatibility` và `targetCompatibility` riêng lẻ

Ví dụ Gradle:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_1_8
    targetCompatibility = JavaVersion.VERSION_1_8
}
```

Nếu compiler thực tế là JDK 17 và chỉ áp dụng source/target 8, code vẫn có thể vô tình tham chiếu API được thêm sau Java 8. Class file có major version 52 nhưng chứa lời gọi `List.of()` từ Java 9, gây lỗi khi chạy Java 8.

Ví dụ:

```java
import java.util.List;

public class ApiLeak {
    public static void main(String[] args) {
        System.out.println(List.of("A", "B"));
    }
}
```

`List.of` được thêm ở Java 9; một compiler JDK mới không bị giới hạn platform APIs có thể chấp nhận source dù target bytecode là Java 8. JVM Java 8 đọc được định dạng bytecode nhưng không có method, dẫn tới `NoSuchMethodError`.

### 5.2. `options.release` để kiểm soát cả Java API

Với compiler JDK hỗ trợ `--release`:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

Khi sử dụng compiler JDK 17 hoặc 21, `options.release = 11` yêu cầu:

1. Cú pháp Java tương ứng release 11.
2. Class file tương ứng Java 11.
3. API nền tảng Java 11 được compiler chấp nhận.

Nó giúp ngăn code mới vô tình gọi API Java SE chỉ xuất hiện ở JDK mới hơn, nhưng không kiểm soát API và bytecode bên trong một dependency bên thứ ba.

**Không cần đặt đồng thời `sourceCompatibility`, `targetCompatibility` và `options.release` cho cùng compile task khi chúng trùng ý nghĩa.** Với mục tiêu cross-compile, ưu tiên một nguồn target rõ ràng, kiểm tra bản Gradle/compiler và tránh cấu hình xung đột.

### 5.3. `--release` khác runtime JDK

`options.release = 11` không đồng nghĩa test cũng chạy trên JDK 11. Nếu mặc định `Test` task dùng JDK 21, test vẫn có thể pass dù dependency runtime có class file hoặc hành vi không tương thích Java 11.

Nếu thư viện cần hỗ trợ Java 11, hãy kiểm thử trên JDK 11 thực tế hoặc môi trường tương đương, bên cạnh compile target 11.

### 5.4. Compiler JDK phải hỗ trợ release target

Không thể dùng compiler JDK 8 với `--release 11`. `--release` chỉ có từ javac JDK 9 và compiler không thể target một Java release mới hơn khả năng hỗ trợ của chính nó.

Ngược lại, JDK quá mới có thể ngừng hỗ trợ một số release rất cũ, nên phải xác nhận target nằm trong danh sách compiler hỗ trợ.

## 6. Cấu hình Gradle Groovy DSL đầy đủ

Giả sử tổ chức cho phép Gradle daemon chạy JDK 17, muốn compile bằng JDK 21 nhưng phát hành thư viện chạy được trên Java 11 và dùng JDK 11 để chạy test compatibility.

Trong `build.gradle`:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    // Dùng javac của toolchain, nhưng kiểm tra source/API theo Java 11.
    options.release = 11
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    // Chạy test bằng JDK 11 để kiểm chứng runtime target.
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }
}
```

Điểm cần chú ý:

- Cấu hình `java.toolchain` tác động tới compiler toolchain của các Java tasks tương ứng.
- `options.release = 11` đặt mức source/bytecode/API nền tảng.
- `Test.javaLauncher` chỉ định JDK chạy test worker JVM.
- `useJUnitPlatform()` phù hợp khi project sử dụng JUnit Platform; nếu không dùng JUnit Platform, cấu hình test framework tương ứng.
- Daemon JVM được lựa chọn qua cấu hình chạy Gradle, **không phải qua `java.toolchain`**.
- Gradle version phải hỗ trợ công cụ/toolchain và Java release này; môi trường cần có hoặc có khả năng provision JDK 21 và JDK 11.

Ví dụ trên không làm một dependency đã biên dịch bằng Java 17 tự chuyển thành bytecode Java 11. Cần kiểm tra toàn bộ runtime graph.

### 6.1. Vì sao lại dùng compiler JDK 21 nhưng release 11?

Tình huống này hữu ích khi CI đã chuẩn hóa JDK hiện đại làm compiler và team muốn dùng một toolchain nhất quán để compile nhiều module hỗ trợ các mức runtime khác nhau.

Tuy nhiên, nếu project có annotation processor hoặc compiler plugin chỉ hỗ trợ một phạm vi JDK nhất định, việc chọn javac mới có thể làm chúng lỗi. Nên kiểm tra compatibility của annotation processors và build plugin với compiler toolchain.

### 6.2. Đổi sang JDK 17 cho compiler

Nếu compiler JDK 21 không cần thiết và dự án muốn giảm khác biệt:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

Đây vẫn là mô hình **compiler JDK 17, target Java 11**. Test JVM cần được chọn riêng nếu mục tiêu là xác minh runtime 11.

## 7. Cấu hình Gradle Kotlin DSL tương ứng

Trong `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(11))
    })
}
```

Về ý nghĩa, cấu hình giống Groovy DSL; chỉ khác cú pháp Kotlin và cách dùng `Property.set(...)`.

Trong dự án nhiều module, cần thống nhất những module nào hỗ trợ Java 11, 17 hoặc 21. Không nên đặt `options.release = 11` toàn bộ repository nếu có những module chủ đích sử dụng Java 17 APIs.

### 7.1. Cấu hình theo module

Ví dụ ở multi-project build Groovy DSL:

```groovy
project(':shared-api') {
    tasks.withType(JavaCompile).configureEach {
        options.release = 11
    }
}

project(':desktop-client') {
    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }
}
```

Một module compile target 11 có thể được dùng bởi ứng dụng 17. Nhưng module target 11 không được phụ thuộc vào artifact chỉ cung cấp bytecode/API Java 17 nếu nó phải chạy trên JDK 11.

### 7.2. Toolchain có thể được đặt ở tầng conventions plugin

Trong repository lớn, configuration có thể nằm ở `buildSrc`, included build hoặc convention plugin chứ không nằm trực tiếp trong `build.gradle`.

Khi chẩn đoán, hãy tìm cấu hình thực tế của task, không chỉ đọc một script cấp module. Một plugin có thể đặt lại compiler, launcher hoặc release của từng task.

## 8. JVM chạy `Test` khác JVM chạy daemon

Gradle `Test` task thường chạy test trong một hoặc nhiều process JVM riêng. Điều này cho phép chọn JDK test khác daemon/compiler, nhưng cũng tạo nguồn nhầm lẫn.

Ví dụ:

```text
Gradle daemon: JDK 17
JavaCompile:   JDK 21, --release 11
Test worker:   JDK 21
Production:    JDK 11
```

Build xanh không chứng minh ứng dụng chạy Java 11: test đã chạy trên JDK 21.

Một cấu hình compatibility test rõ ràng:

```groovy
tasks.named('test', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }
}
```

Tùy project, test task có thể cần JDK mới hơn vì test framework hoặc dependency test không còn hỗ trợ Java 11. Khi đó có thể tạo **một test job riêng** chỉ chạy tập kiểm chứng Java 11 với dependency tương thích, đồng thời dùng test job mới cho chức năng khác. Không nên báo cáo “hỗ trợ Java 11” nếu chưa có bằng chứng chạy runtime Java 11.

### 8.1. JVM arguments của test không phải JVM arguments của daemon

Ví dụ:

```groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-opens', 'java.base/java.lang=ALL-UNNAMED'
}
```

Đây là JVM argument của test worker. Nếu lỗi nằm trong Gradle plugin chạy ngay trong daemon thì cách cấu hình này không xử lý nguyên nhân; ngược lại, thêm argument cho daemon không bảo đảm test forked JVM nhận được nó.

Điều này đặc biệt quan trọng với reflection, instrumentation agents, TLS, heap settings và hệ thống dùng nhiều classloader.

### 8.2. Test JDK có thể khác JDK dùng cho toolchain của JavaCompile

Nếu project dùng toolchain Java 17, các Java tasks có thể có mặc định liên quan tới toolchain đó, nhưng **hãy khai báo Test.javaLauncher tường minh** khi cần chạy matrix để xác nhận nhiều runtime. Không phụ thuộc vào một cấu hình implicit mà team không biết rõ.

## 9. JVM của `JavaExec` và plugin `application`

Một task `JavaExec` chạy main class trên một Java launcher. Nó có thể được cấu hình độc lập với daemon JVM và compiler:

```groovy
tasks.register('runCompatibilityProbe', JavaExec) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }

    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.app.Main'
}
```

Đây là một ví dụ minh họa. Khi project có plugin `application`, task `run` được tạo bởi plugin và có thể nhận những mặc định từ Java plugin/toolchain. Nếu cần bảo đảm version, hãy xem hoặc đặt `javaLauncher` của task thực tế.

### 9.1. `java -jar` ngoài Gradle là thế giới khác

Sau khi đóng gói artifact, lệnh:

```bash
java -jar build/libs/app.jar
```

dùng `java` của môi trường shell/container đang chạy lệnh. Nó **không tự đọc cấu hình `java.toolchain`** trong Gradle script để lựa chọn JVM.

Trong Docker:

```dockerfile
FROM eclipse-temurin:11-jre
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

runtime của container quyết định ứng dụng chạy dưới JDK/JRE 11. Cần bảo đảm artifact và dependency phù hợp Java 11, độc lập với việc Gradle daemon đang dùng JDK 17 hay 21.

### 9.2. `jlink`/`jpackage` là các tác vụ khác

Nếu dự án tạo runtime image hoặc desktop installer bằng `jlink`/`jpackage`, JDK dùng cho các công cụ đó cũng cần được chọn có chủ đích. Toolchain cho `JavaCompile` không mặc nhiên bảo đảm mọi custom packaging task chọn cùng JDK.

Cần kiểm tra command line và runtime image cuối cùng. Việc compile ra Java 11 bytecode rồi bundle JDK 21 runtime vẫn dẫn tới sản phẩm chạy JDK 21, không phải một phép test Java 11.

## 10. Các trường hợp đặc biệt: Kotlin, Scala, annotation processor và code generation

Java toolchain của Gradle Java plugin là cơ chế quan trọng, nhưng project đa ngôn ngữ có nhiều compiler khác.

### 10.1. Kotlin compile

Kotlin Gradle plugin có configuration toolchain và target bytecode riêng theo phiên bản plugin. Cần kiểm tra `jvmTarget` hoặc `compilerOptions` phù hợp, cũng như Java toolchain mà Kotlin compiler dùng.

Việc đặt:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

**không tự áp dụng `--release 11` cho Kotlin compilation**. Nếu artifact kết hợp Java/Kotlin, phải kiểm tra bytecode target và API được dùng bởi cả hai ngôn ngữ.

### 10.2. Kotlin daemon và worker processes

Kotlin compiler có thể sử dụng Kotlin daemon hoặc worker process riêng tùy plugin/configuration. Đây là một process/JVM khác với Gradle daemon và test worker. Vì vậy, log báo “Kotlin daemon started with JDK ...” không thể dùng để kết luận Gradle daemon hoặc JavaCompile compiler đang chạy cùng JDK.

### 10.3. Scala compiler và Groovy

Scala/Groovy plugins có lựa chọn compiler và target tương ứng; chúng không nhất thiết tuân theo mọi cấu hình của `JavaCompile.options.release`.

Khi xuất bản JAR chứa nhiều loại bytecode, cần phân tích artifact cuối để bảo đảm không có class vô tình được compile cho release cao hơn.

### 10.4. Annotation processors và compiler plugins

Annotation processors thường được thực thi trong ngữ cảnh compiler Java. Một processor được build cho JDK mới có thể lỗi khi compiler toolchain cũ đọc class của nó; một processor cũ dùng `com.sun.tools.javac` nội bộ cũng có thể bị ảnh hưởng mạnh khi đổi compiler JDK.

Cần phân biệt:

- Gradle plugin được nạp bởi daemon JDK.
- Annotation processor được compiler thực thi khi JavaCompile.
- Test dependencies được nạp bởi test worker.
- Runtime dependencies được nạp bởi ứng dụng khi chạy.

Chúng có những yêu cầu version khác nhau.

## 11. Kiểm tra thực tế Gradle daemon và toolchains

### 11.1. Xem phiên bản Gradle và JVM Gradle đang dùng

```bash
./gradlew --version
```

Trên Windows:

```powershell
.\gradlew.bat --version
```

Output tùy release có thể cho thấy Launcher JVM, Daemon JVM hoặc thông tin JVM Gradle đang sử dụng. Đây là đầu mối để điều tra daemon/launcher, **không phải kết luận compiler toolchain của từng task**.

### 11.2. Xem JDK installations mà Gradle phát hiện

Trong dự án có Java plugin và Gradle hỗ trợ toolchain task:

```bash
./gradlew -q javaToolchains
```

Lệnh liệt kê những JVM installations Gradle biết và một số metadata liên quan. Nếu JDK cần thiết không xuất hiện, hãy kiểm tra installation paths, toolchain resolver/provisioning, quyền truy cập và môi trường CI.

Lệnh này mô tả những JDK có thể được dùng, không tự kết luận task đã chọn JDK nào.

### 11.3. In compiler thực tế của JavaCompile task

Có thể tạm bổ sung một tác vụ chẩn đoán trong `build.gradle` khi cần phân tích:

```groovy
tasks.withType(JavaCompile).configureEach {
    doFirst {
        println "Task ${path}"
        println "Java compiler: ${javaCompiler.get().executablePath}"
        println "Release target: ${options.release.orNull}"
    }
}
```

Đây chỉ là cách quan sát khi Gradle task được chạy. Không cần duy trì log dài hạn trong production build nếu nó gây nhiễu.

Nếu dùng custom JavaCompile configuration, convention plugin hoặc compiler daemon đặc biệt, hãy kiểm tra thêm output và thông tin toolchain của task tương ứng.

### 11.4. Kiểm tra bytecode đầu ra

Sử dụng `javap` từ JDK phù hợp:

```bash
javap -verbose \
  -classpath build/classes/java/main \
  com.example.app.Main
```

Tìm `major version`:

| Java target | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Class file version xác nhận một phần đầu ra của compiler, nhưng không chứng minh mọi dependency hoặc runtime API tương thích.

### 11.5. Xem runtime test

Nếu cần chắc chắn test đang chạy JVM nào, một test có thể in các system properties:

```java
System.out.println("java.version = " +
        System.getProperty("java.version"));
System.out.println("java.home = " +
        System.getProperty("java.home"));
System.out.println("java.vendor = " +
        System.getProperty("java.vendor"));
```

Đặt logging này trong test worker, không phải chỉ trong build script, để quan sát JVM thật của test.

### 11.6. So sánh với production

Trong container hoặc máy chạy ứng dụng:

```bash
java -version
```

Nếu ứng dụng có own runtime image, kiểm tra Java binary thuộc image đó thay vì Java có sẵn trên host. Có thể log `java.runtime.version` khi startup theo chính sách vận hành.

## 12. Các lỗi phổ biến khi chọn nhầm JVM

### 12.1. `Unsupported class file major version`

Lỗi này có thể xuất hiện khi một thành phần cố đọc class file có phiên bản cao hơn nó hỗ trợ.

Có thể xảy ra ở nhiều nơi:

- Gradle hoặc Groovy/ASM nội bộ không hỗ trợ class file mới của build script/plugin.
- JDK runtime cũ nạp class đã compile cho Java mới.
- Annotation processor/plugin cố đọc dependency được compile với JDK mới.
- Test worker dùng JDK thấp hơn artifact/test class.

Hãy xác định **thành phần nào đang đọc class file**. Nâng compiler/toolchain không sửa được mọi trường hợp; đôi khi cần nâng Gradle wrapper hoặc plugin, đôi khi cần hạ bytecode target của chính artifact.

### 12.2. `No matching toolchains found`

Gradle có thể báo không tìm thấy JDK tương ứng với `languageVersion`, vendor hoặc implementation yêu cầu.

Hướng điều tra:

1. Xem `./gradlew -q javaToolchains`.
2. Xác nhận JDK đã cài và Java home hợp lệ.
3. Kiểm tra chính sách auto-download/toolchain resolvers.
4. Kiểm tra quyền truy cập, mạng và cache CI nếu provisioning được bật.
5. Đối chiếu Gradle version có hỗ trợ toolchain release đó không.

Đổi `JAVA_HOME` sang JDK bất kỳ không phải lúc nào cũng giải quyết nếu build yêu cầu vendor hoặc JDK riêng.

### 12.3. Gradle chạy được nhưng compiler báo cú pháp không hỗ trợ

Ví dụ source dùng record, nhưng compiler target được đặt Java 11. Record không thuộc ngôn ngữ Java 11, nên biên dịch thất bại.

Điều này có thể là **cấu hình đúng đang bảo vệ compatibility**. Cần quyết định runtime target thực sự trước khi nâng source/release chỉ để hết compiler error.

### 12.4. Compile thành công nhưng Java runtime cũ lỗi API

Nếu chỉ đặt `targetCompatibility = 8` mà không giới hạn JDK APIs, code có thể tham chiếu API Java 9+ rồi lỗi trên Java 8.

Hãy dùng `options.release` khi cross-compile, kiểm tra third-party dependencies và test trên runtime mục tiêu.

### 12.5. Test pass trong IDE, CI thất bại

IDE có thể chọn Gradle JVM và test runtime khác terminal/CI. Cần so sánh:

- Gradle wrapper version.
- IDE Gradle JVM.
- Daemon JVM criteria hoặc `org.gradle.java.home`.
- Compiler toolchain và release.
- Test JVM launcher.
- Dependency graph.
- CI container/base image.

Tránh suy luận “test code giống nhau thì JVM cũng giống nhau”.

### 12.6. Cấu hình `org.gradle.java.home` nhưng class version không đổi

Đây thường là hành vi hợp lý nếu JavaCompile vẫn dùng toolchain JDK khác và có `options.release` cố định. Cần xem compiler toolchain, không sửa daemon JVM để hạ class file target.

### 12.7. Gradle plugin lỗi sau khi nâng daemon JDK

Gradle plugin chạy trong daemon có thể bị ảnh hưởng bởi JDK mới, kể cả khi compiler toolchain vẫn là JDK 11. Cần kiểm tra tương thích Gradle wrapper, plugin version và daemon JVM. Đây là vấn đề độc lập với API source đang được compile.

## 13. Cách nghĩ đúng khi dùng Maven cùng Gradle

Chủ đề này tập trung vào Gradle nhưng trong môi trường chuyển đổi Maven–Gradle cần phân biệt các vai trò tương ứng.

| Vấn đề | Gradle | Maven |
|---|---|---|
| JVM chạy build tool | Gradle daemon JVM | JVM thực thi Maven process |
| Chọn JDK compiler riêng | Gradle Java toolchain, JavaCompile compiler | Maven Toolchains + plugin hỗ trợ toolchain hoặc cấu hình compiler |
| Kiểm soát source/bytecode/API | `JavaCompile.options.release` | Maven Compiler Plugin `<release>` / `maven.compiler.release` |
| JDK chạy test | Gradle `Test.javaLauncher` | Maven Surefire/Failsafe JVM/toolchain cấu hình tương ứng |
| JDK chạy ứng dụng | `JavaExec.javaLauncher`, runtime deploy | Exec/plugin launcher hoặc runtime deploy |

`mvn -version` giúp xem JDK Maven đang chạy, nhưng cũng như `gradlew --version`, nó không tự chứng minh mọi compiler/test task dùng đúng JDK đó nếu project cấu hình toolchains hoặc fork.

### 13.1. Maven Compiler Plugin `<release>`

Ví dụ:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
```

Cấu hình này đặt release target của compilation theo khả năng Maven Compiler Plugin và JDK/compiler thực tế, nhưng không có nghĩa JVM chạy Maven phải là JDK 11.

### 13.2. Maven Toolchains

Maven có cơ chế toolchains để chọn JDK ngoài JVM chạy Maven cho các plugin có hỗ trợ. Khi migration từ Maven sang Gradle hoặc ngược lại, cần ánh xạ **build JVM, compiler JDK, test JDK và target release** thành các cấu hình độc lập.

Không nên bê nguyên giá trị `JAVA_HOME` cũ sang Gradle rồi cho rằng đã tái tạo semantics của Maven toolchains.

## 14. Thiết kế CI/CD cho Java Compatibility Migration

### 14.1. Ghim Gradle wrapper

Sử dụng Gradle Wrapper được version control cùng dự án. Cập nhật wrapper theo ma trận hỗ trợ daemon JDK và compiler toolchain JDK, không dùng “Gradle có sẵn trên máy” với phiên bản bất kỳ.

### 14.2. Chọn daemon JVM tường minh

CI cần chỉ rõ JDK chạy Gradle qua môi trường/criteria/phương thức được dự án hỗ trợ. Tránh để JDK phụ thuộc vào thứ tự `PATH` ngẫu nhiên trên runner.

### 14.3. Khai báo toolchain trong build

Ví dụ module hỗ trợ Java 11:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

CI cần có JDK 17 cho compiler và nếu test target Java 11 thì cần JDK 11 cho test launcher. Toolchain provisioning nếu bật phải có nguồn tải đáng tin cậy, khả năng tái hiện và cache được quản lý.

### 14.4. Tạo runtime compatibility matrix

Một matrix có thể chạy:

```text
Build/compile:
  Gradle daemon JDK 17
  Compiler toolchain JDK 17
  --release 11

Runtime tests:
  JDK 11
  JDK 17
  JDK 21 (nếu thuộc phạm vi hỗ trợ)
```

Không phải mọi module cần hỗ trợ mọi JDK. Hãy công bố **runtime thấp nhất và runtime được hỗ trợ**, rồi thiết kế matrix theo hợp đồng đó.

### 14.5. Đảm bảo artifact cuối được test

Nếu build tạo WAR, fat JAR, Docker image hoặc installer, test phải bao gồm đúng artifact phát hành. Một build Gradle thành công trên daemon JDK 17 không chứng minh WAR chạy được trong application server JDK 11.

### 14.6. Báo cáo metadata có thể truy vết

Nên lưu vào build report:

- Gradle wrapper version.
- Daemon JVM version/vendor.
- Compiler toolchain version/vendor.
- `options.release`.
- Test JVM version.
- Production/runtime image version.
- Artifact checksum, dependency lock và resolved dependency graph khi phù hợp.

Những thông tin này giúp tìm nguyên nhân khi một bản release hoạt động ở môi trường A nhưng lỗi ở môi trường B.

## 15. Các kịch bản thực tế và phương án cấu hình

### Kịch bản A: Nâng JDK của build server, giữ runtime Java 11

Yêu cầu:

```text
Gradle daemon: JDK 17
Compiler:      JDK 17
Bytecode/API:  Java 11
Production:    JDK 11
```

Cách làm:

1. Chọn Gradle wrapper hỗ trợ chạy daemon JDK 17.
2. Dùng toolchain JDK 17.
3. Đặt `options.release = 11`.
4. Đưa test compatibility lên JVM Java 11.
5. Kiểm tra dependency runtime không chứa bytecode/API mới hơn mức Java 11.

### Kịch bản B: Developer dùng JDK 21, CI vẫn chạy daemon JDK 17

Yêu cầu compiler dùng JDK 21 ở cả hai môi trường:

```text
Developer:
  Gradle daemon: JDK 17
  JavaCompile:   JDK 21

CI:
  Gradle daemon: JDK 17
  JavaCompile:   JDK 21
```

Cần cấu hình toolchain và bảo đảm JDK 21 được phát hiện/provision ở cả hai nơi. Version của Gradle wrapper phải hỗ trợ compiler toolchain release đó, dù daemon có thể vẫn dùng JDK 17.

### Kịch bản C: Plugin Gradle cũ lỗi trên JDK 21

Ứng dụng muốn dùng JDK 21 để compile nhưng plugin build chưa tương thích daemon JDK 21.

Có thể cân nhắc daemon JDK được plugin hỗ trợ, compiler toolchain JDK 21, **nếu phiên bản Gradle hỗ trợ kết hợp này**. Cách này tách plugin runtime khỏi compiler runtime.

Tuy nhiên, nếu Gradle wrapper/plugin vẫn không hỗ trợ Java 21 language toolchain, phải nâng toolchain support trong Gradle/plugin thay vì chỉ đổi JDK của daemon.

### Kịch bản D: Ứng dụng biên dịch Java 11 nhưng test chỉ chạy JDK 21

Khi cần công bố hỗ trợ Java 11, đây là lỗ hổng kiểm chứng. Đặt test launcher JDK 11 hoặc thêm một CI job chuyên test tương thích Java 11. Chỉ dùng `options.release = 11` không đủ.

### Kịch bản E: Một build đa module hỗ trợ nhiều Java release

Ví dụ:

```text
shared-legacy: --release 8
core-service:  --release 17
desktop-app:   --release 21
```

Có thể dùng các compiler toolchain phù hợp cho từng module và Gradle daemon chung nếu Gradle/plugins hỗ trợ. Nhưng dependency direction phải hợp lý:

- Service Java 17 có thể dùng thư viện Java 8.
- Thư viện Java 8 không được phụ thuộc vào service/artifact có bytecode Java 17 nếu nó còn phải chạy trên Java 8.
- Mỗi module có mức test runtime tối thiểu được công bố.

## 16. Quy trình chẩn đoán theo bước

Khi thấy lỗi liên quan Java version trong Gradle, đừng vội sửa một property ngẫu nhiên.

**Bước 1 — Xác định lỗi xảy ra ở giai đoạn nào.** Gradle chưa khởi động, plugin configuration lỗi, JavaCompile thất bại, test worker thất bại hay production runtime lỗi?

**Bước 2 — Ghi JDK của Gradle daemon.** Dùng Gradle version output, môi trường và daemon settings.

**Bước 3 — Xác định compiler toolchain.** Dùng `javaToolchains`, task JavaCompile metadata hoặc build logs; không suy từ `JAVA_HOME`.

**Bước 4 — Xem release target.** Kiểm tra `options.release` hoặc source/target settings, kể cả convention plugin và cấu hình module con.

**Bước 5 — Xác định test JVM.** Xem `Test.javaLauncher` và thực tế `java.home` từ test worker.

**Bước 6 — Xác định runtime cuối.** Xem Dockerfile, application server, desktop image hoặc lệnh `java -jar` được triển khai thật.

**Bước 7 — Kiểm tra artifact/dependencies.** Xem class file major version, dependency bytecode và API tương thích. `--release` chỉ giới hạn Java platform API của source được compile, không tự giới hạn mọi dependency.

**Bước 8 — Thử lại với cấu hình tái hiện.** Ghim wrapper, toolchains, CI runner và runtime image; chạy đúng tập test phục vụ mục tiêu migration.

**Bước 9 — Ghi nhận nguồn cấu hình.** Đánh dấu rõ daemon JDK, compiler JDK, release target, test JVM và production runtime ở tài liệu vận hành.

## 17. Checklist trước khi chuyển đổi JDK

- [ ] Đã xác định JVM chạy Gradle daemon thực tế.
- [ ] Đã kiểm tra Gradle wrapper hỗ trợ daemon JDK đang chọn.
- [ ] Đã phân biệt Gradle JVM của IDE với Project SDK.
- [ ] Đã xác định toolchain JDK của JavaCompile, không chỉ `JAVA_HOME`.
- [ ] Đã kiểm tra Gradle có tìm/provision được toolchain trong CI.
- [ ] Đã đặt release target rõ ràng cho các module cần tương thích JDK cũ.
- [ ] Đã phân biệt `sourceCompatibility`, `targetCompatibility` và `options.release`.
- [ ] Đã kiểm tra annotation processor và các compiler plugin.
- [ ] Đã cấu hình JVM chạy test theo runtime được hỗ trợ.
- [ ] Đã kiểm tra riêng JVM chạy JavaExec, Spring Boot run hoặc custom Java tasks.
- [ ] Đã cấu hình Kotlin/Scala compiler nếu dự án có nhiều ngôn ngữ.
- [ ] Đã kiểm tra dependency và bytecode của artifact cuối.
- [ ] Đã thử ứng dụng trên runtime image hoặc application server đích.
- [ ] Đã lưu thông tin daemon/compiler/test/runtime JDK trong CI build report.
- [ ] Đã tránh dùng `org.gradle.java.home` như cách hạ bytecode target.
- [ ] Đã tránh coi `gradlew --version` là bằng chứng compiler/toolchain duy nhất.

## 18. Kết luận

**JVM chạy Gradle daemon và toolchain biên dịch là hai thành phần khác nhau.** Daemon JVM thực thi Gradle engine, build scripts và plugins; compiler toolchain cung cấp JDK cho tác vụ JavaCompile. Ngoài ra còn có release target của source/bytecode/API, JVM chạy test, JavaExec và runtime production. Chúng có thể dùng các JDK khác nhau trong cùng một build.

Khi Java Compatibility Migration, hãy xác định **đúng JVM cho đúng công việc**: chọn Gradle wrapper và daemon JDK để build tool khởi động ổn định; chọn compiler toolchain cho tác vụ biên dịch; dùng `options.release` để giữ mức API/bytecode nền tảng; kiểm thử trên runtime thấp nhất được hỗ trợ; và xác minh artifact thực sự được phát hành. Nhờ tách biệt những vai trò này, đội phát triển có thể nâng JDK từng bước mà không đánh đồng “Gradle chạy bằng Java nào” với “ứng dụng đã tương thích Java nào”.
