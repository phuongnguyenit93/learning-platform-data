# Dùng Wrapper, JDK và toolchain nhất quán trên máy CI với Gradle

## 1. Bài toán và mục tiêu trong Tích hợp CI/CD

Một dự án Java có thể `BUILD SUCCESSFUL` trên laptop nhưng thất bại ở GitHub Actions, GitLab CI hay Jenkins. Nguyên nhân nhiều khi không nằm ở Java source: người phát triển chạy Gradle 8.x còn CI dùng Gradle 9.x; laptop chạy JDK 21 còn CI chạy JDK 17; compiler là JDK 17 nhưng process `test` lại dùng JDK khác; hoặc CI tải một Gradle distribution không được xác minh checksum.

**Một pipeline CI/CD tái lập đáng tin phải quy định ít nhất ba lớp phiên bản:**

1. **Gradle distribution** — phiên bản build tool, cố định trong **Gradle Wrapper**.
2. **Gradle runtime JVM** — JDK dùng để khởi động Gradle client/daemon và chạy build logic/plugins.
3. **Java toolchains** — JDK/compiler/launcher được các task như `compileJava`, `test`, `javadoc` và `JavaExec` sử dụng.

Ba lớp có liên quan nhưng **không phải một thứ**. Một pipeline ổn định cần khóa/mô tả các lớp phù hợp, kiểm tra tính tương thích, và chỉ truyền tham số khác biệt khi có chủ đích.

Trong bài này, chúng ta xây một **ứng dụng Java 17** bằng Gradle **Groovy DSL** với:
- Wrapper **Gradle 8.14.3**, có SHA-256 distribution ZIP xác minh từ trang checksum Gradle.
- JDK runtime của CI là **Eclipse Temurin 17**.
- Java toolchain yêu cầu **Java 17, vendor ADOPTIUM**.
- `options.release = 17` cho `javac` để giới hạn Java API/bytecode target.
- JUnit 5 test có kiểm tra thực tế test JVM chạy Java 17.
- GitHub Actions workflow dùng Wrapper thay cho Gradle preinstalled trên runner.
- Một GitLab CI variant và các nguyên tắc tương tự cho Jenkins/container.

Các số phiên bản ở đây là một **ví dụ cụ thể, cố định để người học có thể lặp lại**; không có nghĩa mọi project phải dùng Gradle 8.14.3 hoặc đó là bản Gradle mới nhất. Khi cập nhật toolchain, phải kiểm tra compatibility matrix và nâng có kiểm thử.

### 1.1. Bạn sẽ làm được gì?

- Giải thích `gradlew`, `gradlew.bat`, `gradle-wrapper.jar` và `gradle-wrapper.properties`.
- Hiểu `distributionUrl`, `distributionSha256Sum` và kiểm tra integrity của Wrapper JAR.
- Phân biệt `JAVA_HOME`, PATH, Gradle client JVM, Gradle daemon JVM, `org.gradle.java.home` và daemon JVM criteria.
- Áp `java { toolchain { languageVersion = JavaLanguageVersion.of(17) } }` và pin vendor khi cần.
- Phân biệt `java.toolchain` với `sourceCompatibility`, `targetCompatibility` và `options.release`.
- Chẩn đoán `No matching toolchains found`, `UnsupportedClassVersionError`, Java compiler mismatch, Wrapper download errors và CI cache poisoning.
- Viết và chạy đầy đủ Java 17 project + CI YAML, đối chiếu stdout của ứng dụng.
- Thiết kế cache, release pipeline và nâng cấp Gradle/JDK mà không phá tính nhất quán.

## 2. Ba lớp phiên bản: sơ đồ luồng thực thi

~~~text
CI job / Developer shell
     |
     | JAVA_HOME hoặc java trên PATH
     v
./gradlew (hoặc gradlew.bat)
     |
     | Đọc gradle/wrapper/gradle-wrapper.properties
     | Tải/chọn Gradle distribution đã pin
     v
Gradle client JVM ---- gửi yêu cầu ----> Gradle daemon JVM
                                              |
                                              | Cấu hình Gradle build
                                              | Chọn Java toolchain
                                              v
                                      JavaCompile / Test / Javadoc
                                              |
                                              | JDK 17 được chọn
                                              v
                                      Java class files / reports
~~~

**Gradle Wrapper** chọn **bản Gradle nào**. Nó không tự đảm bảo CI có JDK 17 hay compiler của project chạy trên Java 17.

**`JAVA_HOME`** thường quyết định JVM khởi động Wrapper/client. Nếu không có daemon JVM criteria hoặc `org.gradle.java.home`, daemon thường dùng JVM tương ứng; nhưng có thể khác khi có cấu hình riêng, IDE hoặc một daemon phù hợp.

**Java toolchain** quyết định JDK cho compile/test/javadoc Java tasks. Nó có thể là một JDK khác với JVM đang chạy Gradle, nếu điều này được khai có chủ đích.

### 2.1. Bảng phân biệt

| Thành phần | Nơi cấu hình | Ảnh hưởng |
| --- | --- | --- |
| Gradle distribution | `gradle-wrapper.properties` | Gradle APIs, plugin compatibility, task behavior |
| Wrapper bootstrap JVM | `JAVA_HOME` hoặc `java` trên PATH | Chạy `gradle-wrapper.jar`/client |
| Gradle daemon JVM | `JAVA_HOME` mặc định; `org.gradle.java.home` hoặc daemon JVM criteria khi cấu hình | Build scripts, plugins, Gradle runtime |
| Java compiler JDK | `java.toolchain`/`JavaCompiler` | `compileJava`, compiler APIs, bytecode |
| Test launcher JDK | Java toolchain/`Test.javaLauncher` | JVM chạy JUnit/test code |
| JavaExec launcher | `JavaExec.javaLauncher` hoặc application plugin integration | JVM chạy application/process Java |
| Bytecode/API target | `options.release` | Cấp Java API/classfile mà source có thể sử dụng |
| JUnit/tool dependency versions | `dependencies`/locks/catalog | Test implementation/classpath, không thay Gradle/JDK |

**Lưu ý:** dùng cùng Java major version chưa chắc tạo output byte-for-byte giống nhau nếu JDK patch, vendor, OS, locale, timezone, dependencies hoặc công cụ sinh mã khác nhau. “Nhất quán” ở đây có nhiều mức: major/vendor, patch build, container digest và đầy đủ inputs.

## 3. Gradle Wrapper: bản Gradle đi cùng source code

### 3.1. Bốn tệp cần commit

~~~text
project-root/
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

- `gradlew`: shell script cho Linux/macOS/Unix-like.
- `gradlew.bat`: Windows batch script.
- `gradle-wrapper.jar`: bootstrap logic tải/chạy Gradle distribution.
- `gradle-wrapper.properties`: URL, checksum và một số thiết lập network/cache của distribution.

**Commit cả bốn files**, kể cả `gradle-wrapper.jar`. Wrapper JAR không phải output từ `build/` cần xóa khỏi Git; nó là thành phần bootstrap được Gradle tạo và phải được review/verify.

### 3.2. Vì sao CI phải chạy `./gradlew` thay vì `gradle`?

~~~bash
./gradlew build
~~~

dùng bản Gradle được khai trong repository.

~~~bash
gradle build
~~~

dùng bản Gradle tình cờ cài sẵn trên runner/PATH. Nếu CI image nâng `gradle` mà repo không đổi, build có thể thay hành vi bất ngờ.

**Quy tắc:** trong scripts, pipeline, README và release workflow, dùng Wrapper. Chỉ dùng command `gradle wrapper` từ Gradle được cài sẵn **khi tạo Wrapper ban đầu** và đã xác minh nguồn cài đặt; sau đó dùng `./gradlew`.

### 3.3. `gradle-wrapper.properties` mẫu có checksum thật

Ví dụ cố định ở **Gradle 8.14.3**:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
distributionSha256Sum=bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

SHA-256 trên là **checksum chính thức của Gradle 8.14.3 binary-only ZIP**, không phải giá trị giả hoặc checksum của `-all.zip`. Có thể đối chiếu tại [Gradle distribution checksums](https://gradle.org/release-checksums/). Chữ `\` trong `https\://` là cú pháp escape của Java `.properties` file.

**Không bao giờ áp checksum này cho phiên bản khác**: nếu đổi `distributionUrl` sang 8.14.4, 9.x hay `-all.zip`, phải lấy checksum tương ứng của đúng ZIP.

- `distributionUrl`: tải chính xác `gradle-8.14.3-bin.zip`.
- `distributionSha256Sum`: từ chối ZIP có hash không khớp khi Wrapper thực hiện tải mới.
- `distributionBase`/`distributionPath`: nơi giải nén distribution.
- `zipStoreBase`/`zipStorePath`: nơi lưu ZIP.
- `validateDistributionUrl`: kiểm tra URL trong quá trình tạo/cập nhật Wrapper, không thay checksum.
- `networkTimeout`: timeout tải xuống, không liên quan dependency resolution.

`-bin.zip` nhỏ hơn `-all.zip` vì không chứa full source/documentation của Gradle; CI thông thường nên dùng `-bin.zip`.

### 3.4. Sinh Wrapper bằng lệnh chuẩn

Khi chưa có Wrapper, trên máy **đã cài Gradle được tin cậy** có hỗ trợ các options:

~~~bash
gradle wrapper --gradle-version 8.14.3 --distribution-type bin --gradle-distribution-sha256-sum bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531
~~~

Sau đó dùng Wrapper mới để tái sinh các scripts/JAR theo phiên bản được khai:

~~~bash
./gradlew wrapper --gradle-version 8.14.3 --distribution-type bin --gradle-distribution-sha256-sum bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531
~~~

Kiểm tra:

~~~bash
./gradlew --version
~~~

Bạn phải thấy Gradle **8.14.3** trong kết quả, cùng thông tin JVM thực tế của invocation. Output khác nhau theo OS/JDK và không có một bản log cố định để sao chép.

Lần đầu máy CI mới chạy Wrapper, nó cần truy cập distribution URL (hoặc mirror được tổ chức cho phép). Những lần sau có thể dùng ZIP/distribution trong Gradle User Home cache.

### 3.5. Checksum của distribution và Wrapper JAR là hai thứ khác

- **Distribution ZIP checksum** được pin trong `gradle-wrapper.properties` và được Wrapper kiểm tra khi tải ZIP mới.
- **Wrapper JAR checksum** phải được đối chiếu với Wrapper JAR chính thức từ Gradle hoặc kiểm tra bằng action chuyên dụng trong CI. Nó là code chạy **trước khi** build logic và trước khi Gradle distribution verification, nên đặc biệt nhạy cảm.

Checksum chính thức của **Gradle 8.14.3 Wrapper JAR** trên trang release-checksums là:

~~~text
7d3a4ac4de1c32b59bc6a4eb8ecb8e612ccd0cf1ae1e99f66902da64df296172
~~~

Kiểm tra local Linux:

~~~bash
sha256sum gradle/wrapper/gradle-wrapper.jar
~~~

PowerShell:

~~~powershell
(Get-FileHash 'gradle/wrapper/gradle-wrapper.jar' -Algorithm SHA256).Hash.ToLower()
~~~

**Quan trọng:** checksum Wrapper JAR trên phù hợp với artifact Wrapper JAR chính thức của Gradle 8.14.3, nhưng repository có thể có Wrapper JAR được tạo từ một bản Gradle khác và properties đã được nâng cấp chưa đồng bộ. Không tự thay byte JAR bằng một file lạ chỉ để hash “đúng”; hãy review và tái sinh Wrapper từ distribution chính thức. Trong CI, `gradle/actions/setup-gradle` còn tự xác minh Wrapper JAR qua danh sách checksums đáng tin.

### 3.6. Khi nâng Gradle

Một thay đổi Wrapper cần:
1. Chọn phiên bản **được hỗ trợ bởi JDK chạy Gradle**, các plugins và công cụ CI.
2. Chạy `wrapper` task với version chính xác.
3. Cập nhật `distributionSha256Sum` cho đúng ZIP.
4. Đảm bảo Wrapper JAR/scripts được cập nhật/review, kiểm tra checksums.
5. Commit cả Wrapper scripts/JAR/properties thay đổi.
6. Chạy `./gradlew --version`, `./gradlew build`, integration tests và CI matrix.
7. Kiểm tra Gradle deprecations trước khi nâng major.
8. Không dùng alias `latest` trong release CI vì version có thể thay mà không có source diff.

Một phiên bản Gradle khác có thể thay task validation, DSL APIs hoặc supported JVMs. Pin Wrapper là điều kiện tiên quyết để phát hiện chính xác thay đổi đó qua Pull Request.

## 4. JDK trong CI: hiểu `JAVA_HOME`, JVM client và Gradle daemon

### 4.1. `JAVA_HOME` là gì?

Trong một Linux runner:

~~~bash
echo "$JAVA_HOME"
java -version
javac -version
~~~

- `JAVA_HOME` nên trỏ tới **JDK root**, không phải `bin/java`.
- `PATH` cần ưu tiên `$JAVA_HOME/bin` nếu muốn `java` và `javac` từ JDK đó.
- `java -version` báo JVM mà shell tìm được.
- `javac -version` báo compiler trên PATH; hai lệnh có thể không cùng JDK nếu cấu hình sai.

Trên Windows PowerShell:

~~~powershell
$env:JAVA_HOME
java -version
javac -version
~~~

Windows machine có thể có nhiều JDKs, IDE tự chọn JDK khác, hoặc PATH ưu tiên Java cũ. Không kết luận build đúng chỉ từ `JAVA_HOME` value; cần kiểm tra thực tế.

### 4.2. Gradle client JVM và daemon JVM

Khi gọi `./gradlew`, script khởi động **client JVM** (thường từ `JAVA_HOME`/PATH). Build thường được thực thi trong **Gradle daemon JVM**; daemon có thể dùng:
- Mặc định, JVM tương ứng với client.
- `org.gradle.java.home` trong Gradle properties.
- JVM configuration được Tooling API/IDE yêu cầu.
- **Daemon JVM criteria** trong `gradle/gradle-daemon-jvm.properties` ở những Gradle versions hỗ trợ.

Nếu daemon JVM criteria hiện diện, nó có thể **ưu tiên hơn** `JAVA_HOME` và `org.gradle.java.home`. Vì vậy đừng chẩn đoán “Gradle chắc chắn dùng JAVA_HOME” trong mọi tình huống.

### 4.3. `org.gradle.java.home` không phải Java toolchain

Ví dụ **chỉ dùng khi có chính sách cụ thể**:

~~~properties
org.gradle.java.home=/opt/ci/jdk17
~~~

Nó xác định **JDK/JRE home của Gradle build process**, không trực tiếp cấu hình Java compiler target 17. Đường dẫn tuyệt đối này là machine-specific, nên **không commit** vào shared `gradle.properties` nếu project chạy trên Windows/macOS/Linux với paths khác nhau.

Thay vào đó, trong CI dùng `actions/setup-java` hoặc image chuẩn để thiết lập JVM, và trong build.gradle dùng `java.toolchain` cho compile/test tasks.

### 4.4. `org.gradle.jvmargs` không chọn Java version

~~~properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
~~~

Đây là JVM args/memory settings của Gradle daemon, **không** chọn JDK version. Không sửa `-Xmx` rồi kỳ vọng Java 21 chuyển thành Java 17.

### 4.5. Debug JVM thực sự

~~~bash
java -version
javac -version
./gradlew --version
./gradlew -q javaToolchains
~~~

`./gradlew --version` xác nhận Gradle distribution và thông tin Java runtime của Gradle; `javaToolchains` liệt kê JDKs Gradle phát hiện và các metadata như language version, vendor, installation path. Để biết task compile/test thực sự dùng JDK nào, xem task logs/`--info` hoặc toolchain properties.

**Không nhầm:** `javaToolchains` phát hiện nhiều JDKs là bình thường; chỉ một matching toolchain cụ thể được chọn cho mỗi task request.

## 5. Java toolchains: pin JDK dùng cho compile/test/javadoc

Gradle Java Toolchains giúp build không phụ thuộc máy dev có đặt `JAVA_HOME` như thế nào, miễn Gradle tìm được một JDK phù hợp.

### 5.1. Groovy DSL cơ bản

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Khi áp Java/Application/Java Library plugin, Gradle sẽ dùng Java 17 toolchain cho các tasks hỗ trợ toolchains như `compileJava`, `test`, `javadoc`. Nó:
- Tìm toolchains có sẵn trên máy.
- Chọn bản phù hợp.
- Có thể tải/provision khi có repository resolver và chính sách cho phép.
- Sử dụng JDK chọn được cho task, có thể khác daemon JVM.

**Java 17 ở đây là major version**, không cố định patch build. Máy A có Temurin 17.0.x, máy B có 17.0.y; cả hai phù hợp nếu không pin thêm điều kiện.

### 5.2. Pin vendor để CI và developer tương đồng hơn

~~~groovy
import org.gradle.jvm.toolchain.JvmVendorSpec

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Với `JvmVendorSpec.ADOPTIUM`, Gradle chọn JDK Java 17 của Eclipse Adoptium/Temurin trong danh sách phù hợp. Nếu máy dev chỉ có Oracle JDK 17, lab có thể báo **No matching toolchains found**. Đây là **fail-fast có chủ đích** chứ không phải Gradle tự hỏng.

Bạn có thể bỏ vendor restriction nếu tổ chức chấp nhận nhiều JDK vendors và output/test behavior đã được kiểm chứng tương đương. Nếu thật sự cần reproducible release byte-for-byte, còn phải kiểm soát patch build, OS/arch, JVM implementation, Gradle/plugins/dependencies và generated inputs.

### 5.3. JDK toolchain không đồng nghĩa `sourceCompatibility`

~~~groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
~~~

Hai settings trên khai source/bytecode compatibility, nhưng **không bảo đảm javac thực sự lấy từ JDK 17**, đặc biệt khi Gradle runtime là JDK mới hơn. Nếu compiler dùng JDK 21 mà chỉ đặt target17, bạn có thể vô tình compile với APIs được thêm sau Java17.

Toolchain chọn **compiler** đúng major17. `options.release = 17` còn giới hạn:
- Java language level,
- Bytecode target,
- Java standard library APIs có thể sử dụng.

### 5.4. Dùng `options.release` khi cần cross-compilation nghiêm ngặt

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

Trong lab Java 17 toolchain + release17 là explicit policy dễ review. Không đặt `options.release` cao hơn compiler có thể hỗ trợ; ví dụ javac17 không thể phát hành Java21 bytecode.

### 5.5. Java test launcher phải được kiểm tra

Java plugin liên kết toolchain tới test tasks theo convention. Nếu plugin tùy chỉnh hoặc build script set `Test.javaLauncher` khác, tests có thể chạy trên JDK khác. JUnit test của lab sẽ assert:

~~~java
assertEquals(17, Runtime.version().feature());
~~~

Đây là **assert runtime của test JVM thật**, không chỉ một dòng cấu hình trên giấy. Nếu test bị chạy trên Java21, test sẽ fail dù mã ứng dụng vẫn compile.

### 5.6. `JavaExec` và application plugin

Application plugin tạo `run` task sử dụng JavaExec infrastructure; các phiên bản Gradle hiện đại kết nối toolchain cho Java tasks theo conventions. Với một custom JavaExec task không nhận toolchain mặc định, bạn có thể set launcher explicit:

~~~groovy
def jdk17Launcher = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(17)
    vendor = JvmVendorSpec.ADOPTIUM
}

tasks.register('runTool', JavaExec) {
    javaLauncher = jdk17Launcher
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'dev.example.ci.App'
}
~~~

Đây là snippet mở rộng **sau khi đã có Java plugin**, không thuộc full build.gradle chính của lab. Nếu project không có Java source sets, classpath expression không tồn tại. Dùng Provider thay hard-code `/usr/lib/jvm/.../bin/java`.

## 6. Java toolchain discovery và auto-provisioning

### 6.1. Gradle tìm JDK ở đâu?

Gradle thường tự phát hiện JDKs từ:
- `JAVA_HOME`.
- OS-specific standard directories.
- SDKMAN!, asdf, Jabba hoặc công cụ quản lý JDK.
- IDE installations.
- Custom `org.gradle.java.installations.paths`.
- Environment variables được khai trong `org.gradle.java.installations.fromEnv`.
- JDKs được Gradle provision trước đó ở Gradle User Home.

Xem:

~~~bash
./gradlew -q javaToolchains
~~~

Output chứa toolchain metadata, location, vendor và language version. Trên cùng máy, Gradle có thể phát hiện Java17, Java21 và Java25; chọn dựa trên toolchain specification và precedence rules, **không đơn thuần chọn bản mới nhất**.

### 6.2. Tắt auto-download để CI thiếu JDK thì fail

Trong `gradle.properties` của lab:

~~~properties
org.gradle.java.installations.auto-download=false
~~~

Khi CI đã cài Temurin 17 bằng setup-java, không cần Gradle tự tải thêm JDK. Nếu JDK không tồn tại, fail-fast giúp phát hiện provisioning sai. Developer cần có JDK17 matching hoặc điều chỉnh policy khi onboarding.

**Lưu ý:** auto-detection là cơ chế khác auto-download. Tắt auto-download không tắt việc phát hiện JDK cài sẵn. Nếu tắt luôn auto-detect, phải khai explicit JDK locations.

### 6.3. Gradle 8+ không tự tìm repository tải JDK nếu chưa cấu hình

Từ Gradle 8.0, **automatic JDK download không còn hoạt động khi chưa khai toolchain download repository**. Để cho phép Gradle tải toolchain, cần toolchain resolver plugin trong `settings.gradle`.

Ví dụ **phương án thay thế** khi tổ chức muốn provisioning JDK bằng Gradle:

~~~groovy
plugins {
    id 'org.gradle.toolchains.foojay-resolver-convention' version '1.0.0'
}

rootProject.name = 'consistent-ci'
~~~

Đây là Settings plugin dựa trên Foojay Disco API. Phiên bản 1.0.0 yêu cầu Gradle tương thích và Java 17+ để chạy plugin. Đồng thời cần **bỏ hoặc đổi `org.gradle.java.installations.auto-download=false`** nếu muốn provisioning JDK; không giữ chính sách cấm tải rồi kỳ vọng resolver tải được.

**Không nhầm:** `repositories { mavenCentral() }` ở build.gradle để giải dependencies **không phải** Java toolchain download repository. Trong corporate CI offline/air-gapped, dùng JDK preinstalled hoặc mirror được kiểm soát thay vì dựa vào endpoint bên ngoài.

### 6.4. Pin patch/vender cụ thể có giới hạn

`languageVersion=17` và `vendor=ADOPTIUM` pin **major + vendor**, nhưng không pin exact 17.0.x build. Toolchain detection có precedence (JDK đang chạy Gradle, JDK vs JRE, vendor, version/architecture) và Gradle không tự nâng JDK đã được provision lên patch mới nhất.

Nếu tổ chức đòi exact JDK build:
- Dùng image/container được pin **theo digest** hoặc JDK installation artifact có checksum riêng.
- Tại CI kiểm tra `java -version` và toolchain metadata thực tế.
- Kiểm soát OS/CPU architecture.
- Thiết lập toolchain locations theo CI image.
- Không giả định `setup-java java-version: '17'` là pin exact patch.

## 7. Bài thực hành end-to-end: Java 17 Application + JUnit 5

Lab này là một repository Java nhỏ, có test xác minh **JDK runtime trong Test task**.

### 7.1. Cấu trúc

~~~text
consistent-ci/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── main/
│   │   └── java/
│   │       └── dev/
│   │           └── example/
│   │               └── ci/
│   │                   └── App.java
│   └── test/
│       └── java/
│           └── dev/
│               └── example/
│                   └── ci/
│                       └── AppTest.java
└── .github/
    └── workflows/
        └── verify.yml
~~~

**Yêu cầu:**
- Tạo Wrapper Gradle 8.14.3 như phần 3 và có đủ bốn files.
- Có JDK **Temurin 17** cho chạy Gradle và toolchain của lab.
- Gradle cần mạng hoặc dependency cache để giải JUnit Jupiter/Platform dependencies.
- Linux shell cần executable bit cho `gradlew`. Trên Git, commit file mode đúng.

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'consistent-ci'
~~~

### 7.3. `gradle.properties`

~~~properties
org.gradle.java.installations.auto-download=false
~~~

Đây là repo-wide policy: toolchain Java17 cần được preinstall. Không đặt `org.gradle.java.home=/some/personal/path` trong file dùng chung. CI workflow sẽ setup JDK17 cụ thể.

### 7.4. `build.gradle` — toàn bộ

~~~groovy
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.jvm.toolchain.JvmVendorSpec

plugins {
    id 'application'
}

group = 'dev.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

application {
    mainClass = 'dev.example.ci.App'
}
~~~

**Giải thích:**
1. `application` áp Java capabilities và đăng ký `run`.
2. `repositories.mavenCentral()` để lấy JUnit test dependencies, **không** dùng để tải Gradle distribution hoặc JDK toolchain.
3. `languageVersion=17` chọn Java 17 toolchain.
4. `vendor=ADOPTIUM` chọn JDK Temurin/Eclipse Adoptium để khớp CI setup-java.
5. `options.encoding='UTF-8'` giúp đọc source ổn định.
6. `options.release=17` giới hạn public Java APIs và bytecode target.
7. `testImplementation` cung cấp JUnit Jupiter API/engine version 5.11.4.
8. `testRuntimeOnly` cung cấp JUnit Platform Launcher 1.11.4, đồng bộ với JUnit Jupiter family.
9. `useJUnitPlatform()` cho Gradle Test task chạy JUnit5.
10. `mainClass` là fully-qualified Java class có `public static void main(String[])`.
11. Không ép test JVM qua `org.gradle.java.home` hoặc hard-coded `/opt/java/bin/java`.
12. JUnit versions được pin để ví dụ ổn định; muốn tái lập dependency graph thật sự có thể dùng locking/verification.

### 7.5. `src/main/java/dev/example/ci/App.java`

~~~java
package dev.example.ci;

public final class App {

    private App() {
    }

    public static String message() {
        return "CI ready: Java 17";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

### 7.6. `src/test/java/dev/example/ci/AppTest.java`

~~~java
package dev.example.ci;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class AppTest {

    @Test
    void applicationMessageIsStable() {
        assertEquals("CI ready: Java 17", App.message());
    }

    @Test
    void testsReallyRunOnJava17() {
        assertEquals(17, Runtime.version().feature());
    }
}
~~~

Hai tests kiểm tra **hai chuyện khác nhau**:
- App behavior: chính xác string được chương trình trả về.
- Runtime environment: Test task phải chạy trên Java17, không chỉ compile target17.

Nếu JUnit test launcher bị ép dùng Java21, `testsReallyRunOnJava17` phải FAIL. Đây là phép đo runtime, không phải lời khẳng định “CI có JAVA_HOME 17 nên tất cả tasks dùng 17”.

### 7.7. Chạy ở máy developer

~~~bash
java -version
javac -version
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean build
./gradlew run --quiet
~~~

**Stdout chính xác của ứng dụng Java khi chạy `run --quiet`:**

~~~text
CI ready: Java 17
~~~

Task logs Gradle thay đổi theo version/caching, nên không đưa stdout cho `clean build` như một hằng số. Khi chạy `build` thành công, kỳ vọng:
- `compileJava` dùng Java17 toolchain.
- `test` chạy **hai JUnit tests PASS**.
- `jar` tạo `build/libs/consistent-ci-1.0.0.jar` (tên theo project/version của lab).
- Test results dưới `build/test-results/test` và HTML report dưới `build/reports/tests/test`.

**Không nhầm:** plain Application plugin JAR không tự chứa tất cả runtime dependencies; `./gradlew run` sử dụng configured runtime classpath. Để phân phối ứng dụng, dùng `installDist`/`distZip` theo application plugin khi cần.

### 7.8. Kiểm tra Java 17 độc lập không cần Gradle

`App.java` không phụ thuộc external libraries; có thể compile/run trực tiếp:

~~~bash
javac --release 17 -encoding UTF-8 -d standalone src/main/java/dev/example/ci/App.java
java -cp standalone dev.example.ci.App
~~~

**Stdout chính xác:**

~~~text
CI ready: Java 17
~~~

Đây chỉ là phép thử Java code và compiler target, **không chứng minh** Gradle Wrapper, dependency resolution, Test task launcher hoặc CI workflow đúng. Các lớp đó cần các lệnh kiểm tra ở phần 7.7 và CI phía sau.

## 8. GitHub Actions CI: dùng Wrapper và Temurin 17

Tạo `.github/workflows/verify.yml`:

~~~yaml
name: Verify Gradle Java 17

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Install Temurin JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          check-latest: false

      - name: Setup Gradle and validate Wrapper
        uses: gradle/actions/setup-gradle@v6
        with:
          gradle-version: wrapper

      - name: Inspect effective environment
        run: |
          java -version
          javac -version
          ./gradlew --version
          ./gradlew -q javaToolchains

      - name: Build and test with repository Wrapper
        run: ./gradlew build --stacktrace

      - name: Smoke test Java application
        run: ./gradlew run --quiet
~~~

**Tại sao workflow này nhất quán?**

1. `actions/checkout` lấy chính Wrapper files được commit vào repository.
2. `actions/setup-java` cài **Temurin 17**, đặt `JAVA_HOME`/PATH phù hợp trong job.
3. `gradle/actions/setup-gradle@v6` theo tài liệu Gradle hiện hành quản lý Gradle User Home cache và **xác thực Wrapper JAR**. `gradle-version: wrapper` chọn đúng bản từ repository, không lén dùng một Gradle version khác.
4. `./gradlew --version` hiển thị distribution/runtime; `javaToolchains` cho biết Gradle nhận JDK nào.
5. `./gradlew build` chạy compilation/tests/assemble bằng project toolchain Java17.
6. `./gradlew run --quiet` tạo stdout của ứng dụng.
7. Job không cần cài riêng Gradle bằng apt/Homebrew và không dùng `gradle build`.
8. Pipeline không có bước upload/publish; PR không có quyền ghi release artifact.

**Output ứng dụng từ bước Smoke test:**

~~~text
CI ready: Java 17
~~~

Không khẳng định `java -version` hoặc `./gradlew --version` in y hệt giữa các machines, vì JDK patch/build metadata và OS khác.

### 8.1. Ý nghĩa `java-version: '17'`

GitHub Actions setup-java với `java-version: '17'` chọn một JDK thuộc **major 17** của vendor Temurin, nhưng không nhất thiết đúng một patch release cố định. `check-latest: false` là cache/lookup policy, **không** biến `'17'` thành một patch lock.

Nếu cần byte-for-byte parity giữa các jobs/release:
- Chọn exact JDK patch build có thực và được setup-java hỗ trợ, hoặc dùng vetted JDK tarball/image.
- Pin Docker image **digest** khi dùng container.
- Đối chiếu JDK vendor/version/arch ở logs.
- Gắn release provenance, Gradle version và dependencies lock.
- Dùng toolchain matching criteria phù hợp nhưng không giả định Gradle tự pin patch version.

### 8.2. GitHub Actions action version cũng là dependency

Các tags `actions/checkout@v4`, `actions/setup-java@v4` và `gradle/actions/setup-gradle@v6` là versions được chọn cho ví dụ. Actions security best practices có thể yêu cầu **pin full commit SHA** để tránh tag bị thay. Repo production nên dùng action SHA đã được tổ chức xác minh, theo dependabot/renovate policy; không tự bịa SHA khi tài liệu không cung cấp.

### 8.3. Validate Wrapper JAR khác download distribution

`setup-gradle` có Wrapper validation và Gradle Wrapper có `distributionSha256Sum`:
- Validation Wrapper JAR để tránh chạy bootstrap code lạ.
- Checksum distribution ZIP để bảo đảm Gradle binary đúng khi tải ZIP mới.

Không bỏ một lớp chỉ vì đã có lớp kia. Khi CI cache đã có distribution unpacked và marker hợp lệ, checksum ZIP không nhất thiết được tính lại ở mỗi invocation; vẫn phải duy trì chain of trust cho cache và Wrapper JAR.

### 8.4. CI cache và security

`setup-gradle` quản lý Gradle User Home caches gồm wrapper distributions, dependency artifacts và local build cache theo thiết lập action. CI tránh:
- Cache toàn bộ home directory có credentials.
- Chia writeable cache giữa untrusted Pull Request và trusted release job mà không kiểm soát.
- Dùng cache key không có nguồn gốc/version, gây artifact bẩn.
- Lấy cache hit làm bằng chứng tests PASS khi CI đã bỏ test tasks.

Bạn có thể đặt `cache-read-only: true` cho các nhánh/matrix legs không được phép cập nhật shared cache. Khi có configuration cache trên CI, chú ý thông tin nhạy cảm trong cache entries và encryption key policy.

### 8.5. Vì sao không buộc dùng `--no-daemon` mọi job?

Gradle docs hiện khuyến nghị dùng daemon cả trên CI khi phù hợp để giảm overhead; trong ephemeral runner, daemon sẽ kết thúc theo lifecycle job. `--no-daemon` có thể tăng thời gian và thậm chí dùng single-use daemon tùy JVM args. Chỉ vô hiệu hóa khi môi trường hạn chế/CI policy thật sự yêu cầu.

### 8.6. Linux executable bit

Nếu Git Checkout làm `./gradlew: Permission denied`, kiểm tra executable bit đã được Git theo dõi:

~~~bash
git ls-files --stage gradlew
git update-index --chmod=+x gradlew
~~~

Commit file mode change nếu cần. Không cần cài Gradle riêng để sửa lỗi execute permission. Trên Windows dùng `gradlew.bat`.

## 9. GitLab CI: cùng nguyên tắc

GitLab Runner có thể dùng Docker image với JDK17:

~~~yaml
image: eclipse-temurin:17-jdk

stages:
  - test

variables:
  GRADLE_USER_HOME: "$CI_PROJECT_DIR/.gradle"

test:
  stage: test
  script:
    - chmod +x gradlew
    - java -version
    - ./gradlew --version
    - ./gradlew -q javaToolchains
    - ./gradlew build --stacktrace
    - ./gradlew run --quiet
  artifacts:
    when: always
    paths:
      - build/test-results/test/
      - build/reports/tests/test/
~~~

**Giải thích:**
- Docker image cung cấp JDK17; Wrapper vẫn chọn chính xác Gradle8.14.3.
- `GRADLE_USER_HOME` nằm trong job workspace để CI có thể quản lý cache theo policy; snippet **không** mặc định publish toàn bộ cache.
- `artifacts.when: always` giữ raw/HTML test results nếu build fail, hữu ích cho debug. Nếu build dừng trước tests thì đường dẫn có thể chưa tồn tại, tùy GitLab Runner warning policy.
- `eclipse-temurin:17-jdk` là **tag trôi theo patch build**, không pin digest. Với strict reproducibility hãy dùng immutable digest được xác minh trong registry của tổ chức.
- Runner/network phải cho phép Wrapper tải Gradle distribution và Gradle giải dependencies, hoặc có internal mirrors/cache.

### 9.1. Jenkins và các CI khác

Với Jenkins Pipeline/agent container, nguyên tắc giống:
1. Checkout repository có Wrapper.
2. Provision JDK17 đã được chọn/verified.
3. Đặt `JAVA_HOME`/PATH hoặc daemon JVM criteria theo build policy.
4. Chạy `./gradlew --version` và `./gradlew -q javaToolchains`.
5. Chạy `./gradlew build`.
6. Archive JUnit XML/HTML test reports.
7. Chỉ publish artifacts sau quality gate PASS.

Không phụ thuộc vào Jenkins global Gradle installation nếu repo đã có Wrapper. Nếu Jenkins agent chạy Windows, dùng `gradlew.bat` hoặc một shell phù hợp.

## 10. Cùng Java major không đồng nghĩa cùng mọi bit

Đây là điểm thường bị hiểu quá mức khi nói “CI nhất quán”.

| Cấp kiểm soát | Cấu hình | Chưa được kiểm soát |
| --- | --- | --- |
| Gradle version | Wrapper exact version 8.14.3 | Gradle JAR/source integrity nếu không validate |
| Java major | Toolchain 17 | Vendor/patch/architecture |
| Java vendor | `JvmVendorSpec.ADOPTIUM` | Patch build/OS/CPU features |
| CI runtime JDK | `setup-java distribution: temurin, java-version: '17'` | Patch changes trong chuỗi 17.x |
| Exact JDK artifact | Checked checksum/container digest | OS libc/timezone/locale nếu không kiểm soát |
| Dependencies | Versions/locks/verification | Network repo content, dynamic metadata nếu bỏ policy |
| Archive reproducibility | Stable order/timestamps | Generated timestamps/absolute paths/Javadoc HTML variations |

Với phần lớn team, **Wrapper version exact + Java major/vendor + dependency versions và CI image được review** là nền tảng tốt. Với phát hành có compliance/reproducible-build yêu cầu cao, phải pin patch artifact/digest và mô tả môi trường chi tiết hơn.

### 10.1. Java bytecode và runtime

Java 17 compile target thường tạo class file major version **61**. Nếu cố chạy class đó trên Java 11, có thể gặp:

~~~text
java.lang.UnsupportedClassVersionError
~~~

Nó không chứng minh Wrapper sai; cần xem **JVM dùng để chạy class** có hỗ trợ bytecode hay không. Java source compiler, Test JVM và application runtime có thể khác trong một build.

### 10.2. `options.release` không thay thế toolchain

`options.release=17` giúp ngăn dùng Java API sau17 và tạo target bytecode17, nhưng nếu compiler là JDK21, kết quả không hoàn toàn đồng nhất với chạy chính javac17. Toolchain là cách chọn compiler thực tế; `release` là API/target contract.

### 10.3. Docker image tag không phải digest

`eclipse-temurin:17-jdk` có thể được cập nhật patch release. Điều này tốt cho security updates nhưng không đủ nếu yêu cầu một JDK build cố định. Với production release, dùng digest của image đã quét/lưu trữ trong registry tin cậy; ở đây không bịa một digest để làm mẫu.

## 11. Daemon JVM criteria: cơ chế nâng cao

Gradle mới hỗ trợ declarative Daemon JVM requirements. Khi áp dụng, một file dưới `gradle/gradle-daemon-jvm.properties` có thể mô tả major/vendor cần dùng để chạy Gradle daemon, tách khỏi `JAVA_HOME` của shell.

Ví dụ task trong Gradle version có hỗ trợ:

~~~bash
./gradlew updateDaemonJvm --jvm-version=17
~~~

**Đây là hướng nâng cao**, không phải bước bắt buộc của lab:
- Cần cấu hình toolchain download repositories/resolver phù hợp khi task cần provision Daemon JVM.
- Daemon JVM criteria có thể ưu tiên hơn `JAVA_HOME`/`org.gradle.java.home`.
- Phải commit/review file criteria khi dự án chọn dùng.
- Không cùng lúc khai nhiều yêu cầu JVM mâu thuẫn rồi kỳ vọng một giá trị duy nhất tự thắng.
- Kiểm tra Gradle version hiện tại có những options nào bằng `./gradlew help --task updateDaemonJvm`.

Với một CI Java17 nhỏ như lab, setup-java + Wrapper + java.toolchain đã đủ. Không cần thêm cơ chế daemon criteria chỉ để có nhiều file cấu hình.

## 12. Những lỗi thường gặp trên CI và cách sửa

### 12.1. `JAVA_HOME is set to an invalid directory`

**Nguyên nhân:** đường dẫn tới JDK bị xóa/sai, `JAVA_HOME` trỏ vào `bin` thay vì root JDK, hoặc runner image đổi layout.

**Chẩn đoán:**

~~~bash
echo "$JAVA_HOME"
test -x "$JAVA_HOME/bin/java" && echo "JAVA_HOME valid"
java -version
~~~

**Sửa:** provisioning JDK đúng trước bước Wrapper; không commit personal absolute paths.

### 12.2. `No matching toolchains found for requested specification`

**Nguyên nhân:** project yêu cầu Java17/ADOPTIUM nhưng CI chỉ có Java21 hoặc JDK17 từ vendor khác; auto-download bị tắt; resolver không cấu hình.

**Chẩn đoán:**

~~~bash
./gradlew -q javaToolchains
./gradlew compileJava --info
~~~

**Sửa:** setup Temurin17 theo policy hoặc cho toolchain download qua resolver được phê duyệt. Không sửa bừa `languageVersion=21` nếu application cần Java17.

### 12.3. `Unsupported class file major version` hoặc `UnsupportedClassVersionError`

**Nguyên nhân:** JVM chạy Gradle/plugin/test/application quá cũ so với bytecode mà nó cần load.

**Sửa:** kiểm tra compatibility matrix, `./gradlew --version`, `java -version` và toolchain/test launcher. Ví dụ Java17 class (major61) không chạy trên JVM11.

### 12.4. `Could not determine java version`

Gradle quá cũ có thể không hiểu JDK mới. Pin Wrapper một bản Gradle hỗ trợ JVM đó thay vì chạy Gradle đã cài sẵn. **Kiểm tra compatibility matrix**, không chỉ nâng JDK.

### 12.5. `gradlew: Permission denied`

Linux executable bit mất; sửa Git file mode hoặc có bước `chmod +x gradlew` trên runner. Nên commit mode đúng.

### 12.6. Wrapper download timeout/SSL/proxy fail

- Runner không tới được `services.gradle.org`.
- Proxy yêu cầu cấu hình.
- Firewall không cho redirection/network.
- TLS trust store thiếu certificate.
- Mirror nội bộ chưa có đúng ZIP.

Kiểm tra network/proxy/TLS policy; dùng approved mirror pin đúng artifact và checksum. Không bỏ `distributionSha256Sum`, không dùng plain HTTP để “chữa” SSL problem.

### 12.7. `Verification of Gradle distribution failed`

Checksum ZIP đã tải **không khớp** với `distributionSha256Sum`. Có thể cấu hình hash cho sai version/edition, artifact bị corrupt/tamper hoặc mirror cung cấp sai bytes.

**Không** sửa hash bằng cách lấy nó từ ZIP không tin cậy. So version URL/hash với checksum chính thức của Gradle, kiểm tra mirror và chỉ dùng distribution được xác minh.

### 12.8. Wrapper JAR validation fail

`gradle-wrapper.jar` hash không có trong danh sách official; có thể bị thay đổi, tạo từ bản custom, hoặc artifact nguy hiểm. Không bỏ bước validation để CI xanh. Khôi phục/tái sinh Wrapper qua nguồn tin cậy rồi review diff, so checksum official.

### 12.9. Gradle build khác máy dev dù Wrapper và Java17 giống

Kiểm tra:
- Gradle daemon JVM khác compiler/test toolchain?
- JDK patch/vendor/architecture khác?
- Environment variables, timezone, locale, file encoding?
- Dynamic dependency versions hoặc plugin versions?
- Local Maven cache/stale generated source?
- OS case sensitivity, file permissions và line endings?
- Annotation processors/code generators có dùng timestamp?
- Native dependencies/toolchains khác nhau?

Gradle Wrapper giải quyết **Gradle version**, không khóa toàn bộ môi trường.

### 12.10. CI `build` PASS nhưng code không chạy trên Java17

Task `compileJava` có thể dùng compiler JDK21 với `targetCompatibility=17` nhưng vô tình gọi Java21 APIs. Dùng toolchain Java17 và `options.release=17`; chạy runtime/functional tests trên Java17. Lab có JUnit test `Runtime.version().feature()==17` để phát hiện test launcher sai.

### 12.11. Gradle dùng JDK khác `java -version`

Có `org.gradle.java.home`, daemon JVM criteria, IDE Tooling API JVM hoặc daemon reuse. Kiểm tra `./gradlew --version`, `javaToolchains` và daemon config. Không dùng `java -version` làm bằng chứng duy nhất.

### 12.12. Build cache chứa dữ liệu cũ

Nếu task inputs chưa khai đầy đủ, cache có thể reuse output sai. Sửa input model và task outputs; không dựa vào `clean build` mọi lần như một giải pháp thiết kế. CI cache permissions phải tách trusted/untrusted environments.

## 13. Kiểm thử CI có kiểm soát

Một bộ kiểm tra cần ở mỗi PR:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew compileJava --info
./gradlew test --stacktrace
./gradlew build
./gradlew run --quiet
~~~

**Kỳ vọng:**
- Wrapper báo Gradle8.14.3.
- Gradle nhìn thấy matching Temurin17 toolchain.
- Java compile và JUnit tests PASS, hai tests được thực thi khi fresh.
- `run --quiet` in chính xác `CI ready: Java 17`.
- Không có `UnsupportedClassVersionError` hay download/checksum error.

Không nên dựa vào một dòng test summary/historical cache để chứng minh tests đã chạy trên đúng JDK. JUnit test của lab kiểm tra runtime version trực tiếp.

### 13.1. Thử trường hợp thiếu JDK

Trong một runner thử nghiệm chỉ cài JDK21, với `vendor=ADOPTIUM` + Java17 + `auto-download=false`, build phải fail do không tìm thấy matching toolchain. Đây là **đúng mong muốn fail-fast**.

Đừng biến pipeline đỏ thành xanh bằng cách bỏ toolchain block: nó sẽ ẩn lại dependency vào môi trường host.

### 13.2. Thử Gradle version drift

Nếu thay `gradle-wrapper.properties` bằng version khác mà không cập nhật checksum, Wrapper phải từ chối ZIP không khớp. Đó là lớp kiểm soát, không phải bug. Quy trình nâng chính thức phải cập nhật version + checksum đồng bộ.

### 13.3. Thử Test JVM sai

Trong một branch thử nghiệm, nếu ép `Test.javaLauncher` sang Java21 trong khi test yêu cầu Java17, `testsReallyRunOnJava17` sẽ fail. Không commit cấu hình phá môi trường; mục tiêu chỉ là chứng minh test kiểm tra đúng JVM dùng khi chạy.

### 13.4. Đối chiếu output Java độc lập

~~~bash
javac --release 17 -encoding UTF-8 -d standalone src/main/java/dev/example/ci/App.java
java -cp standalone dev.example.ci.App
~~~

Stdout:

~~~text
CI ready: Java 17
~~~

Nếu bước Gradle `run` sai mà Java-only test đúng, tập trung chẩn đoán Gradle application/run classpath, launcher/toolchain hoặc project configuration thay vì nghi ngờ nội dung `App.java`.

## 14. Dependency và plugin consistency không thể bỏ qua

Pin Wrapper/JDK vẫn chưa đủ cho build có external dependencies. Ví dụ:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}
~~~

Các versions này cố định; ngược lại `5.+`, `latest.release`, `SNAPSHOT` hoặc dependency thay đổi trên repository có thể khiến CI dùng graph khác.

Các cơ chế Gradle hữu ích:
- Dependency locking: kiểm soát resolved versions trên các configurations.
- Dependency verification: checksums/signatures của dependencies.
- Version catalog/convention plugin: thống nhất version declarations giữa modules.
- Toolchain/JDK pinning: giảm khác biệt compiler/runtime.
- Repository policy: ưu tiên HTTPS, mirrors và trusted sources.
- Reproducible archives: kiểm soát ZIP entry order/timestamps và generated data.

**Phân biệt nguồn tải:** Wrapper ZIP từ `distributionUrl`; JDK từ setup-java/installed toolchain/resolver; dependencies từ `repositories`; plugin metadata từ `pluginManagement.repositories`. Chỉ có `repositories { mavenCentral() }` không tự cung cấp Wrapper/JDK.

## 15. Thiết kế CI matrix và release pipeline

### 15.1. PR verification vs release

PR:
- Checkout code.
- Validate Wrapper integrity.
- Provision supported JDK.
- Build/tests/lint.
- Lưu reports nếu fail.
- Không cấp publication credentials.

Release:
- Chạy từ trusted tag/branch.
- Kiểm tra test/quality gates.
- Pin tool versions và JDK artifact provenance.
- Ký/xác minh artifacts theo chính sách.
- Chỉ publish nếu tất cả checks PASS.
- Không overwrite immutable release version.

### 15.2. CI matrix có tác dụng gì?

Nếu sản phẩm hỗ trợ JDK17 và JDK21, có thể chạy **matrix runtime tests** trên cả hai JDKs. Nhưng compiler toolchain Java17 có thể vẫn được pin để tạo bytecode17. Phân biệt:
- **Build JVM matrix:** Gradle runtime trên các JVM được Gradle hỗ trợ.
- **Compile toolchain:** target Java mà artifact công bố.
- **Test runtime matrix:** JVM mà ứng dụng được bảo đảm chạy.

Nếu mọi matrix leg cùng khai `java.toolchain=17`, thay `JAVA_HOME` của runner sang 21 **không chứng minh** tests đang chạy trên Java21. Khi kiểm tra compatibility, cần cấu hình test launcher rõ cho từng leg và giữ compile target phù hợp.

### 15.3. Avoid matrix cache contamination

Không cho nhiều matrix legs cùng ghi một mutable cache key. Tách theo Gradle/JDK/OS hoặc chỉ một job ghi cache; đọc shared cache khi build tool hỗ trợ và security policy cho phép. Configuration cache có dữ liệu nhạy cảm hơn dependency artifacts, cần encryption/matching environment controls.

## 16. Bài tập có đáp án

### Bài 1 — Wrapper vs Gradle installed
**Hỏi:** CI có Gradle9 trên PATH, repo Wrapper pin8.14.3. Lệnh nào phải dùng?

**Đáp án:** `./gradlew build`; không dùng `gradle build`.

### Bài 2 — Wrapper files
**Hỏi:** Có cần commit `gradle-wrapper.jar` không?

**Đáp án:** Có, cùng `gradlew`, `gradlew.bat` và `gradle-wrapper.properties`; đồng thời xác minh integrity.

### Bài 3 — SHA-256
**Hỏi:** Đổi `distributionUrl` từ 8.14.3 sang 8.14.4 nhưng giữ checksum8.14.3 có đúng không?

**Đáp án:** Không. Phải cập nhật distribution checksum khớp đúng ZIP của version/edition mới.

### Bài 4 — Wrapper vs JDK
**Hỏi:** Pin Wrapper đã đảm bảo `javac 17` chưa?

**Đáp án:** Chưa. Cần provisioning JDK và toolchain specification phù hợp.

### Bài 5 — `JAVA_HOME`
**Hỏi:** `JAVA_HOME` thường quyết định JVM gì?

**Đáp án:** JVM khởi động Wrapper/client và thường daemon mặc định, nhưng daemon có thể bị override. Không tự đồng nghĩa compiler/test toolchain.

### Bài 6 — Vendor
**Hỏi:** JDK17 Oracle cài trên máy, project yêu cầu `JvmVendorSpec.ADOPTIUM` và auto-download off. Kết quả?

**Đáp án:** Có thể `No matching toolchains found` vì vendor không phù hợp; cần Temurin17 hoặc thay policy có chủ đích.

### Bài 7 — Toolchain vs release
**Hỏi:** `sourceCompatibility=17` và `targetCompatibility=17` có đảm bảo không dùng API Java21 không?

**Đáp án:** Không chắc nếu dùng compiler JDK21; dùng Java17 toolchain và `options.release=17` để ràng buộc API/bytecode.

### Bài 8 — Test JVM
**Hỏi:** JUnit test nào trong lab chứng minh tests chạy Java17?

**Đáp án:** `assertEquals(17, Runtime.version().feature())`.

### Bài 9 — stdout
**Hỏi:** `App.main` in gì?

**Đáp án:** Chính xác một dòng `CI ready: Java 17` có newline cuối do `println`.

### Bài 10 — Patch
**Hỏi:** `java-version: '17'` có pin Temurin 17.0.x exact patch?

**Đáp án:** Không. Chỉ major version; cần exact JDK build/image digest khi strict parity.

### Bài 11 — Auto-download
**Hỏi:** Gradle 8.14.3 thiếu JDK17, bật auto-download nhưng không có resolver. Có chắc tự tải thành công?

**Đáp án:** Không. Gradle8+ cần configured toolchain download repository/resolver.

### Bài 12 — Marker khác checksum
**Hỏi:** Wrapper ZIP checksum thay thế Wrapper JAR validation được không?

**Đáp án:** Không. Hai thành phần khác nhau trong bootstrap chain.

### Bài 13 — No daemon
**Hỏi:** CI có buộc chạy mọi build với `--no-daemon` không?

**Đáp án:** Không. Gradle daemon phù hợp cả CI; lựa chọn theo policy/performance/runner lifecycle.

### Bài 14 — CI green
**Hỏi:** `./gradlew build` PASS nhưng deployment từ PR không tin cậy có được tự publish không?

**Đáp án:** Không. Release credentials và publish permissions chỉ dành cho trusted release context sau gates.

### Bài 15 — Thực hành tuần tự
1. Tạo project `consistent-ci` đầy đủ phần 7.
2. Sinh Wrapper8.14.3 với checksum chính thức như phần 3.
3. Commit bốn Wrapper files và review executable bit.
4. Cài Temurin17, kiểm tra `JAVA_HOME`/`java -version`/`javac -version`.
5. Chạy `./gradlew --version`, xác nhận Gradle8.14.3.
6. Chạy `./gradlew -q javaToolchains`, tìm JDK17 ADOPTIUM.
7. Chạy `./gradlew clean build`, xác nhận hai JUnit tests PASS.
8. Chạy `./gradlew run --quiet`, đối chiếu stdout `CI ready: Java 17`.
9. Chạy Java-only `javac`/`java`, đối chiếu stdout giống.
10. Thêm GitHub Actions workflow phần 8, quan sát PR build.
11. Kiểm tra Wrapper JAR validation và distribution hash.
12. Tắt toolchain auto-provisioning, thử runner không có Temurin17 và xem fail-fast.
13. Đối chiếu behavior khi máy có nhiều Java versions.
14. Giải thích vì sao pin Gradle + JDK major chưa phải byte-for-byte reproducibility.
15. Viết checklist release upgrade version/patch và chạy CI matrix trước khi phát hành.

**Tiêu chí đạt:** bạn giải thích được ba lớp Gradle Wrapper/runtime JVM/toolchain, tự xây và chạy Java17 app/tests bằng Wrapper đã pin, biết xác minh checksums, và CI có pipeline không phụ thuộc Gradle cài sẵn.

## 17. Checklist trước khi vận hành CI/CD thực tế

- [ ] Repository có đủ `gradlew`, `gradlew.bat`, Wrapper JAR và Wrapper properties.
- [ ] CI luôn dùng `./gradlew`, không dùng Gradle system binary.
- [ ] `distributionUrl` pin exact Gradle version và edition.
- [ ] `distributionSha256Sum` lấy từ official release-checksums, khớp URL.
- [ ] Wrapper JAR được kiểm tra integrity qua checksum/action tin cậy.
- [ ] Mọi Wrapper updates được review và test CI.
- [ ] Gradle version tương thích với JVM chạy build/plugins.
- [ ] CI provisioning xác định JDK major/vendor, có thể pin exact patch nếu cần.
- [ ] `JAVA_HOME`/PATH được kiểm tra, không dùng user-specific absolute paths trong shared config.
- [ ] Gradle daemon JVM config/criteria không mâu thuẫn với CI policy.
- [ ] Java compiler/test/javadoc toolchains được khai rõ.
- [ ] `options.release` phản ánh Java API/bytecode contract.
- [ ] Tests chạy trên đúng JVM runtime được support, không chỉ compile đúng.
- [ ] `javaToolchains` diagnostic có thể chạy khi pipeline fail.
- [ ] JDK auto-download policy rõ; resolver/mirror được cấu hình nếu muốn provisioning.
- [ ] Dependencies/plugins versions và repository source tin cậy/khóa khi cần.
- [ ] CI cache không ghi chung thiếu kiểm soát giữa PR và release.
- [ ] Console logs/reports không lộ secrets/proxy credentials.
- [ ] Release job chỉ có quyền publish khi verification PASS.
- [ ] Gradle/toolchain upgrades đi kèm checklist compatibility và rollback.
- [ ] Artifact provenance đủ Gradle version, JDK version, source revision và dependency graph.
- [ ] Multi-OS/multi-JDK matrix được cấu hình theo phạm vi support thực tế.

## 18. Tài liệu chính thức

- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): files, distributionUrl, checksum, nâng cấp.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): Java runtime/compiler support theo Gradle version.
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html): Java toolchain, vendor, auto-detection/provisioning và diagnostics.
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): client vs daemon JVM, criteria và environment.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): JAVA_HOME, org.gradle.java.home, JVM args và installations policies.
- [Gradle — Gradle on GitHub Actions](https://docs.gradle.org/current/userguide/github-actions.html): setup-gradle, Wrapper validation và CI cache.
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): pin distribution và SHA-256.
- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html): Wrapper JAR/download validation.
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): Java source/release/target compatibility.
- [Gradle — Testing in Java/JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): Test JVM execution, JUnit Platform.
- [Gradle — Toolchain Resolver Plugins](https://docs.gradle.org/current/userguide/toolchain_plugins.html): cấu hình JDK download resolver.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): resolved versions.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): artifact integrity.
- [Gradle — Release Checksums](https://gradle.org/release-checksums/): SHA-256 chuẩn của Gradle distributions/Wrapper JARs.
