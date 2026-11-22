# Chọn version CI cho dự án Java

Chọn version cho CI/CD là quyết định những phiên bản Java, build tool, runner image và thành phần pipeline sẽ được dùng để build, test và đóng gói ứng dụng. Nếu chỉ chọn một con số Java rồi để các phần còn lại tự cập nhật, cùng một commit có thể build khác nhau giữa máy developer, CI và production.

Với dự án Java, cần tách riêng năm lớp phiên bản:

1. **JDK chạy CI job và build tool:** JVM mà Gradle hoặc Maven đang chạy trên đó.
2. **Java toolchain:** JDK compiler và Java launcher dùng để compile, test hoặc chạy task.
3. **Java release target:** phiên bản Java thấp nhất mà bytecode và API của ứng dụng phải tương thích.
4. **Build tool và plugin:** Gradle/Maven Wrapper, plugin, compiler plugin và dependency.
5. **CI environment:** runner/agent, operating system image, container image và CI action/plugin.

Các lớp này liên quan với nhau nhưng không nhất thiết phải cùng một version. Ví dụ, CI có thể chạy Gradle trên JDK 25, compile bằng toolchain JDK 25, nhưng dùng `--release 17` để bảo đảm artifact vẫn chạy trên Java 17. Sau đó, pipeline có thể chạy test trên JDK 17, 21 và 25 để kiểm tra tương thích trên nhiều runtime.

## 1. Bắt đầu từ phiên bản Java mà ứng dụng phải hỗ trợ

Trước khi chọn JDK cho CI, hãy xác định runtime thấp nhất mà sản phẩm cam kết hỗ trợ. Đây là quyết định về compatibility của sản phẩm, không phải quyết định về runner.

Ví dụ:

- Ứng dụng chỉ chạy trên Java 17 trở lên: target release là 17.
- Ứng dụng đã chuyển sang Java 21 và dùng API/feature của Java 21: target release là 21.
- Ứng dụng yêu cầu Java 25: target release là 25.
- Thư viện phải phục vụ nhiều ứng dụng cũ: cần target theo runtime thấp nhất mà người dùng thư viện còn được hỗ trợ.

Lựa chọn LTS thường phù hợp với hệ thống production cần vòng đời ổn định. Tại thời điểm tháng 11/2026, Oracle liệt kê Java 17, 21 và 25 là các bản LTS; lịch hỗ trợ và điều khoản thực tế vẫn phụ thuộc vendor JDK và hợp đồng hỗ trợ mà tổ chức sử dụng.

| Phiên bản | Vai trò tham khảo |
|---|---|
| Java 17 | Baseline phổ biến cho hệ thống cần tương thích lâu dài với ứng dụng Java 17 |
| Java 21 | LTS tiếp theo, phù hợp khi dự án đã xác nhận framework và dependency hỗ trợ |
| Java 25 | LTS mới hơn tại thời điểm bài viết, phù hợp để đánh giá nâng cấp và làm runtime đích mới |

Không nâng target chỉ vì CI runner đã có JDK mới. Hãy kiểm tra framework, application server, database driver, agent giám sát, thư viện native, container base image và môi trường production trước khi thay đổi runtime tối thiểu.

## 2. Phân biệt JDK chạy Gradle/Maven với JDK compile/test

Đây là nguồn gây nhầm lẫn thường gặp.

**JDK chạy build tool**

Đây là Java mà process Gradle hoặc Maven dùng để khởi động. Nó chịu ràng buộc bởi yêu cầu của phiên bản Gradle/Maven và plugin.

**JDK toolchain**

Đây là JDK mà task compile/test/JavaExec dùng. Gradle Java Toolchains cho phép chọn compiler và launcher theo version, vendor hoặc implementation. Toolchain có thể khác JVM đang chạy Gradle.

**Java release target**

Đây là mức ngôn ngữ, API JDK và bytecode mà compiler được phép sử dụng/tạo ra. Nó quyết định ứng dụng có thể chạy trên runtime nào, trong giới hạn các dependency đi kèm.

Ví dụ:

| Lớp | Giá trị |
|---|---|
| JVM chạy Gradle trong CI | JDK 25 |
| Java toolchain dùng compile/test | JDK 25 |
| Java release target | 17 |
| Runtime production tối thiểu | Java 17 |
| CI test matrix | 17, 21, 25 |

Trong ví dụ này, Gradle chạy bằng Java 25 nhưng code được compile theo Java 17. Pipeline còn chạy test trên nhiều JDK để tìm lỗi tương thích runtime.

Không giả định `JAVA_HOME` quyết định tất cả. `JAVA_HOME` thường chọn JVM mặc định cho Gradle/Maven, trong khi Java toolchain có thể chọn một JDK khác cho compiler hoặc test launcher.

## 3. Kiểm tra compatibility của build tool trước khi chọn JDK

JDK mới có thể được phát hành trước khi phiên bản Gradle, Maven hoặc plugin mà dự án đang dùng hỗ trợ nó. Cần kiểm tra cả hai chiều:

- Build tool có chạy được trên JDK mà CI cung cấp không?
- Build tool/plugin có hỗ trợ compile và test bằng JDK mục tiêu không?

Ví dụ với Gradle 9.9.0, compatibility matrix hiện hành yêu cầu Java 17 trở lên để chạy Gradle. Java 25 được hỗ trợ để chạy Gradle từ Gradle 9.1.0 trở đi. Vì vậy, dự án dùng Gradle 9.9.0 có thể chọn JDK 17, 21 hoặc 25 làm JVM chạy build, nếu plugin và các thành phần còn lại cũng tương thích.

Bảng kiểm tra nhanh theo Gradle 9.9.0:

| JDK | Có thể chạy Gradle 9.9.0? | Toolchain compile/test |
|---|---|---|
| 17 | Có | Có |
| 21 | Có | Có |
| 25 | Có | Có |
| 26 | Có từ Gradle 9.4.0 | Có từ Gradle 9.4.0 |
| 27 | Có từ Gradle 9.8.0 | Có từ Gradle 9.8.0 |

Bảng này là compatibility của Gradle, không phải cam kết rằng mọi plugin, annotation processor hoặc thư viện trong dự án đều hỗ trợ tất cả version đó. Kiểm tra thêm tài liệu compatibility của plugin và framework đang sử dụng.

Với Maven, kiểm tra version Maven Wrapper, JDK mà Maven đang chạy và cấu hình Maven Compiler Plugin/toolchains. Không tự suy luận rằng Maven cũ sẽ hỗ trợ mọi JDK mới chỉ vì `javac` có thể compile source.

## 4. Dùng Gradle Wrapper để cố định build tool

Không để CI gọi một bản Gradle cài sẵn tùy ý trên runner. Commit Gradle Wrapper vào repository và chạy build qua `./gradlew` hoặc `gradlew.bat`.

File `gradle/wrapper/gradle-wrapper.properties` có thể chỉ định một bản phân phối cụ thể:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
```

Điều này giúp developer và CI sử dụng cùng một Gradle distribution. Khi cần bảo vệ tính toàn vẹn của distribution, thêm `distributionSha256Sum` với checksum chính thức tương ứng chính xác với file ZIP đã chọn.

Các nguyên tắc:

- Commit `gradlew`, `gradlew.bat`, thư mục `gradle/wrapper` và `gradle-wrapper.properties`.
- Không dùng bản Gradle được cài global làm nguồn version chính.
- Không dùng URL trỏ đến `current`, `latest` hoặc nightly trong build production.
- Nâng Gradle Wrapper qua pull request riêng, đọc release notes và chạy toàn bộ verification.
- Kiểm tra compatibility của Gradle với JDK chạy build và plugin trước khi merge.

Nếu dùng Maven, áp dụng nguyên tắc tương tự với Maven Wrapper (`mvnw`, `mvnw.cmd` và `.mvn/wrapper/maven-wrapper.properties`). Chạy `./mvnw` thay vì dựa vào `mvn` cài sẵn trên runner.

## 5. Dùng Java Toolchains và --release để cố định compiler/runtime

Với Gradle Java Plugin, cấu hình toolchain ở cấp project:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Hai cấu hình có ý nghĩa khác nhau:

- `languageVersion = 17` yêu cầu Gradle chọn JDK 17 cho các task Java dùng toolchain.
- `options.release = 17` yêu cầu compiler giới hạn language feature, JDK API và bytecode theo Java 17.

Nếu CI chạy Gradle bằng JDK 25 nhưng toolchain là 17, Gradle cần tìm hoặc provision JDK 17 để compile/test. Điều này hữu ích khi muốn giữ build runtime mới nhưng vẫn compile bằng compiler của baseline.

Một cách khác là chạy từng matrix job trên đúng JDK và truyền version vào Gradle build. Phần thực hành bên dưới minh họa cách này.

Không chỉ dùng `sourceCompatibility` và `targetCompatibility` để thay thế `--release` khi cần bảo đảm API compatibility. Hai thuộc tính cũ chủ yếu cấu hình source/target của compiler; chúng không cung cấp cùng mức kiểm tra API như `--release`.

## 6. Chọn JDK distribution và vendor

Ngoài version, CI còn cần chọn bản phân phối JDK. Một số lựa chọn thường gặp:

- Eclipse Temurin.
- Amazon Corretto.
- Azul Zulu.
- Oracle JDK.
- Microsoft Build of OpenJDK.
- Red Hat Build of OpenJDK.
- GraalVM khi cần Native Image hoặc tính năng riêng của GraalVM.

Hãy chọn theo tiêu chí vận hành:

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| Support lifecycle | Vendor cung cấp cập nhật bảo mật và hỗ trợ đến khi nào? |
| License | Điều khoản sử dụng có phù hợp CI, staging và production không? |
| Patch cadence | Bản cập nhật CPU/PSU được phát hành và áp dụng ra sao? |
| Architecture | Có package cho x64, ARM64 hoặc kiến trúc runner cần dùng không? |
| Platform | Có bản phù hợp Linux, Windows, macOS và container base image không? |
| Compatibility | Framework, native library, crypto provider và monitoring agent có tương thích không? |
| Distribution consistency | CI có cần dùng cùng vendor/build với production không? |

Nếu production dùng một vendor JDK cụ thể vì yêu cầu hỗ trợ hoặc crypto provider, nên kiểm thử CI trên cùng distribution ở ít nhất một job quan trọng. Nếu sản phẩm hỗ trợ nhiều vendor, có thể bổ sung job kiểm thử chéo theo vendor.

Không trộn vendor trong cùng một matrix nếu mục tiêu chỉ là kiểm tra Java language version. Mỗi chiều matrix làm tăng số job và chi phí. Chỉ thêm vendor matrix khi có yêu cầu tương thích thực tế.

## 7. Chọn matrix Java phù hợp

Matrix giúp chạy cùng một bộ kiểm thử trên nhiều version Java. Không nhất thiết phải chạy mọi phiên bản tồn tại.

Một chiến lược thường dùng cho ứng dụng hỗ trợ Java 17 trở lên:

- Pull request: chạy trên Java 17 (baseline) và Java 25 (LTS mới hơn).
- Nightly hoặc trước release: chạy Java 17, 21 và 25.
- Release candidate: chạy thêm đúng runtime/vendor/OS mà production sử dụng.
- Khi nâng target từ 17 lên 21: thay baseline matrix theo kế hoạch migration, sau khi kiểm tra framework và dependency.

Ví dụ matrix:

| Job | JDK | Mục tiêu |
|---|---:|---|
| Compatibility baseline | 17 | Xác nhận ứng dụng vẫn chạy trên runtime thấp nhất |
| Intermediate LTS | 21 | Phát hiện khác biệt giữa các LTS |
| Current LTS | 25 | Phát hiện sớm vấn đề khi nâng cấp runtime |

Nếu dự án chỉ hỗ trợ Java 21, không cần test Java 17 chỉ vì đây là một bản LTS. Matrix phải phản ánh hợp đồng hỗ trợ thật của sản phẩm.

Matrix cũng có thể kết hợp OS hoặc architecture:

- Linux x64 cho build nhanh thường ngày.
- Windows nếu ứng dụng hoặc script phụ thuộc Windows.
- macOS nếu cần kiểm thử hành vi trên macOS hoặc build artifact dành cho nền tảng đó.
- ARM64 nếu production hoặc người dùng chạy trên ARM64.

Không nhân tất cả chiều matrix một cách máy móc. Chọn các tổ hợp có rủi ro hoặc có người dùng thực tế.

## 8. Không nhầm version major với patch version

Khai báo `java-version: '25'` thường chọn một bản JDK thuộc dòng Java 25 theo quy tắc của công cụ setup và cache. Nó không nhất thiết cố định một patch release duy nhất.

Có ba mức pin thường gặp:

| Cách chọn | Ví dụ | Tính chất |
|---|---|---|
| Major line | `25` | Dễ nhận patch update mới trong dòng 25; phù hợp khi cập nhật patch tự động có kiểm soát |
| Full feature/update version | `25.0.x` hoặc version đầy đủ mà vendor phát hành | Kiểm soát patch cụ thể hơn |
| Immutable artifact | Container image digest hoặc checksum của JDK archive | Xác định chính xác artifact được tải/chạy |

Chọn mức pin dựa trên yêu cầu:

- CI thông thường có thể theo major line và cập nhật patch định kỳ.
- Release build hoặc môi trường kiểm soát chặt có thể pin patch cụ thể hoặc JDK archive đã xác minh.
- Containerized runner có thể pin image bằng digest.
- Không dùng `latest` cho pipeline cần kết quả ổn định; alias này có thể trỏ sang Java major mới khi vendor phát hành.

Pin version không có nghĩa là giữ mãi một bản cũ. Phải có quy trình cập nhật security patch và kiểm thử trước khi đưa version mới vào pipeline chính.

## 9. Chọn version của CI runner, image và action/plugin

JDK chỉ là một phần của môi trường CI.

### Runner image và operating system

Với GitHub-hosted runner, chọn image có phiên bản OS rõ ràng như `ubuntu-24.04` khi muốn tránh việc label `ubuntu-latest` tự chuyển sang một OS major mới. Tuy nhiên, image hosted vẫn được cập nhật package và tool theo thời gian; label OS không phải immutable snapshot.

Với GitLab CI hoặc runner Docker, khai báo image có tag rõ ràng. Khi cần môi trường bất biến hơn, dùng image digest và lưu image trong registry đáng tin cậy.

Với Jenkins, cần kiểm tra cả Jenkins controller, agent, tool installation và JDK mà job sử dụng. Một Jenkins job có thể chạy trên agent khác OS hoặc architecture; tên tool phải được cấu hình nhất quán trên các agent đó.

### CI action và plugin

Action/plugin cũng có version riêng:

- GitHub Actions: version của `actions/checkout`, `actions/setup-java` và các action bên thứ ba.
- GitLab CI: version của GitLab Runner, container image và CI component được include.
- Jenkins: version Jenkins LTS, plugin và JDK tool definition.

Không để action/plugin dùng nhánh `main` hoặc `latest` trong pipeline production. Chọn release đã được kiểm tra, theo dõi security advisory và nâng cấp có kiểm soát.

Đối với GitHub Actions, tag như `@v6` thuận tiện cho cập nhật nhưng có thể thay đổi nội dung khi tag bị di chuyển. GitHub khuyến nghị pin action vào full-length commit SHA để có tham chiếu bất biến; có thể dùng Dependabot hoặc workflow lockfile để quản lý cập nhật.

## 10. Ví dụ GitHub Actions: kiểm thử Java 17, 21 và 25

Workflow dưới đây chạy cùng build trên ba JDK. Ví dụ dùng `actions/checkout@v7` và `actions/setup-java@v6` theo release hiện hành tại thời điểm viết bài. Trong repository có yêu cầu supply-chain security cao, thay tag bằng full commit SHA đã xác minh từ repository chính thức của từng action.

Tạo file `.github/workflows/java-ci.yml`:

```yaml
name: Java CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    name: Verify on Java ${{ matrix.java }}
    runs-on: ubuntu-24.04
    strategy:
      fail-fast: false
      matrix:
        java: [17, 21, 25]

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up Java
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: "${{ matrix.java }}"
          cache: gradle

      - name: Show build environment
        run: |
          java --version
          javac --version
          ./gradlew --version
          ./gradlew -q javaToolchains

      - name: Verify
        run: ./gradlew --no-daemon -PciJavaVersion=${{ matrix.java }} clean check
```

Giải thích:

- `matrix.java` tạo ba job độc lập.
- `setup-java` cài JDK tương ứng và cấu hình `JAVA_HOME`/`PATH`.
- `cache: gradle` cache dependency và wrapper distribution để giảm thời gian tải.
- `javaToolchains` cho biết Gradle phát hiện những JDK nào.
- `-PciJavaVersion=...` truyền JDK đang kiểm thử vào Gradle build.
- `clean check` chạy build và verification từ đầu.

Cache chỉ là tối ưu hiệu năng. Cache không phải cơ chế chọn JDK và không thay thế việc pin Wrapper, toolchain hoặc dependency.

## 11. Ví dụ GitLab CI: cố định container JDK

Với GitLab CI dùng Docker executor, job image quyết định môi trường container chạy script. Ví dụ:

```yaml
verify:
  image: eclipse-temurin:25-jdk-noble
  stage: test
  script:
    - java --version
    - javac --version
    - ./gradlew --no-daemon -PciJavaVersion=25 clean check
```

Tag image giúp chọn dòng JDK và base OS cụ thể. Để kiểm soát chính xác artifact, có thể dùng dạng `image: registry.example.com/team/temurin:25-jdk-noble@sha256:...` với digest thực tế lấy từ registry đáng tin cậy. Không sao chép digest từ image khác hoặc dùng một digest không còn tồn tại trong registry.

Khi cần matrix, tạo các job cho JDK 17, 21 và 25 hoặc dùng `parallel:matrix` với image được xây dựng từ biến CI. Kiểm tra cấu hình bằng CI Lint và xác nhận runner hỗ trợ Docker executor/image đã chọn.

## 12. Ví dụ Jenkins Pipeline: chọn JDK tool đã cấu hình

Jenkins quản lý JDK qua Manage Jenkins > Tools. Administrator tạo tool name như `temurin-17`, `temurin-21` hoặc `temurin-25`, trỏ đến installation có sẵn hoặc cấu hình installer.

Pipeline tham chiếu tool theo tên:

```groovy
pipeline {
    agent any

    tools {
        jdk 'temurin-25'
    }

    stages {
        stage('Verify') {
            steps {
                sh 'java --version'
                sh './gradlew --no-daemon clean check'
            }
        }
    }
}
```

Tên `temurin-25` phải khớp với tên JDK đã cấu hình trong Jenkins. Trên Windows agent, dùng `bat` thay cho `sh` nếu agent không có shell POSIX.

Nếu agent Linux và Windows cài JDK ở các đường dẫn khác nhau, cấu hình Tool Locations theo từng agent. Không giả định cùng một `JAVA_HOME` path tồn tại trên mọi node.

## 13. Cấu hình Gradle để chạy matrix và giữ Java 17 compatibility

Ví dụ build script Kotlin DSL sau dùng version truyền từ CI để chọn toolchain, nhưng giữ `--release 17` để artifact vẫn tương thích với Java 17.

File `build.gradle.kts`:

```kotlin
plugins {
    application
}

val ciJavaVersion = providers.gradleProperty("ciJavaVersion")
    .map { it.toInt() }
    .getOrElse(17)

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(ciJavaVersion))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

application {
    mainClass.set("com.example.App")
}
```

File `src/main/java/com/example/App.java`:

```java
package com.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("ci-version-ok");
    }
}
```

Tạo Gradle Wrapper trỏ đến Gradle 9.9.0, sau đó chạy:

Linux/macOS:

```sh
./gradlew -PciJavaVersion=17 clean check
./gradlew -PciJavaVersion=21 clean check
./gradlew -PciJavaVersion=25 clean check
./gradlew -PciJavaVersion=25 run
```

Windows:

```powershell
.\gradlew.bat -PciJavaVersion=17 clean check
.\gradlew.bat -PciJavaVersion=21 clean check
.\gradlew.bat -PciJavaVersion=25 clean check
.\gradlew.bat -PciJavaVersion=25 run
```

Stdout của ứng dụng:

```text
ci-version-ok
```

Ba lệnh `check` dùng compiler/test toolchain tương ứng với version được truyền. `options.release.set(17)` giữ source/API/bytecode compatibility ở Java 17. Lệnh `run` dùng application runtime launcher theo toolchain của project.

Trong CI, JDK cần thiết phải được cài sẵn hoặc Gradle phải được cấu hình toolchain provisioning. Nếu không có JDK phù hợp, build có thể dừng với lỗi không tìm thấy toolchain.

## 14. Ví dụ Maven: tách JDK chạy Maven khỏi release target

Nếu dự án dùng Maven, chọn JDK chạy Maven trong CI bằng `JAVA_HOME` hoặc CI setup step. Sau đó cấu hình release target trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Dùng Maven Wrapper để cố định Maven distribution:

```sh
./mvnw --version
./mvnw --batch-mode clean verify
```

`maven.compiler.release` yêu cầu compiler kiểm tra ngôn ngữ, API và bytecode theo Java 17. Nếu muốn compile bằng JDK riêng với JVM đang chạy Maven, cấu hình Maven Toolchains và khai báo toolchain tương ứng.

Trong CI matrix, có thể chạy Maven trên từng JDK đã chọn và dùng cùng `maven.compiler.release` để xác nhận ứng dụng tương thích trên các runtime đó.

## 15. Kiểm tra version thực tế trong log CI

Không chỉ tin vào cấu hình YAML. Hãy in version thực tế ở đầu job:

```sh
java --version
javac --version
echo "$JAVA_HOME"
./gradlew --version
./gradlew -q javaToolchains
```

Với Maven:

```sh
java --version
javac --version
echo "$JAVA_HOME"
./mvnw --version
```

Các lệnh này giúp phát hiện:

- Runner đang dùng JDK khác dự kiến.
- Gradle chạy bằng JVM khác với Java toolchain.
- Gradle không phát hiện toolchain cần thiết.
- Maven đang chạy từ một installation khác.
- Agent/container có architecture hoặc vendor khác.

Trên Windows PowerShell, dùng `$env:JAVA_HOME` để in environment variable.

Khi cần biết task cụ thể dùng compiler/launcher nào, chạy Gradle với `--info` hoặc xem metadata toolchain. Không chỉ nhìn `java --version` rồi kết luận compiler và test launcher cũng dùng cùng JDK.

## 16. Pin version của plugin và dependency

Ngay cả khi JDK và Wrapper đã cố định, build vẫn có thể thay đổi nếu plugin hoặc dependency được khai báo bằng version động.

Nên:

- Ghi rõ version của Gradle plugin trong `plugins {}` hoặc `pluginManagement`.
- Dùng version catalog để quản lý version thống nhất trong multi-project build.
- Dùng dependency locking khi cần cố định dependency graph.
- Bật dependency verification/checksum hoặc signature verification theo chính sách.
- Không dùng version range hoặc dynamic version như `1.+` trong build release.
- Kiểm tra plugin compatibility khi nâng Gradle hoặc JDK.

Ví dụ plugin version được khai báo rõ:

```kotlin
plugins {
    java
    id("com.example.quality") version "2.4.1"
}
```

Ví dụ này minh họa việc khai báo version cố định. Khi dùng plugin thật, chọn version đã được xác nhận tương thích với Gradle Wrapper và JDK của dự án.

Không nên nâng đồng thời JDK, Gradle, plugin và framework trong một thay đổi lớn nếu có thể chia thành các bước. Khi build fail, thay đổi từng lớp giúp xác định nguyên nhân nhanh hơn.

## 17. Cache không thay thế version pinning

CI cache có thể lưu:

- JDK đã tải.
- Gradle/Maven distribution.
- Dependency đã tải.
- Build output cache.

Cache làm build nhanh hơn nhưng không phải nguồn cấu hình version đáng tin cậy. Khi cache miss, pipeline phải vẫn tải đúng version đã khai báo. Khi cache hit, pipeline cũng phải kiểm tra version metadata và cache key phù hợp.

Để tránh cache cũ:

- Đưa `gradle-wrapper.properties`, build scripts, `gradle.properties` và version catalog vào cache key.
- Đưa `pom.xml`, Maven Wrapper properties và Maven extension configuration vào cache key.
- Tách cache theo OS, architecture, JDK major và build tool khi các yếu tố đó ảnh hưởng artifact.
- Không dùng cache để bỏ qua bước cài JDK hoặc xác minh version.
- Dùng cache read-only cho job matrix fan-out nếu nhiều job cùng ghi vào một key và gây xung đột.

Nếu build output phụ thuộc JDK vendor hoặc patch version, hãy đảm bảo cache/build cache nhận diện đúng toolchain inputs. Không tái sử dụng output của một JDK cho một môi trường khác khi tính tương thích chưa được xác nhận.

## 18. Lộ trình nâng version CI

Nâng JDK hoặc CI image nên là một thay đổi có kế hoạch:

1. Ghi lại JDK production, JDK build hiện tại, Gradle/Maven Wrapper, plugin và runner image.
2. Kiểm tra compatibility matrix của build tool và framework.
3. Tạo branch thử nghiệm hoặc pull request chỉ nâng JDK.
4. Chạy compile, unit test, integration test, static analysis và package.
5. Chạy matrix trên baseline và JDK mới.
6. So sánh warning, test failure, performance và artifact metadata.
7. Cập nhật runner image/action/plugin trong thay đổi riêng nếu cần.
8. Thử nghiệm trên staging với runtime giống production.
9. Phát hành theo từng môi trường và theo dõi lỗi.
10. Ghi lại version mới trong tài liệu build/release.

Nên có lịch kiểm tra JDK security update định kỳ. Không giữ JDK cũ vô thời hạn chỉ để build ổn định; thay vào đó, cập nhật có kiểm soát và lưu lại version cụ thể trong mỗi release.

## 19. Lỗi thường gặp khi chọn version CI

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Unsupported class file major version` | JDK chạy build hoặc plugin không đọc được bytecode version đang dùng | Kiểm tra `java --version`, Gradle/Maven version và plugin compatibility |
| Gradle không chạy trên JDK mới | Gradle Wrapper quá cũ để hỗ trợ JVM đó | Kiểm tra Gradle compatibility matrix và nâng Wrapper |
| Compile chạy Java 17 dù CI đã cài Java 25 | Gradle toolchain cố định Java 17 | Kiểm tra `java.toolchain` và `javaToolchains` task |
| App chạy trên CI nhưng fail trên Java 17 production | Compile không giới hạn API/bytecode bằng `--release` | Đặt `options.release` hoặc `maven.compiler.release` theo baseline |
| `JAVA_HOME` đúng nhưng compiler sai | Build dùng toolchain khác với JVM chạy Gradle/Maven | Kiểm tra toolchain compiler và launcher |
| CI local pass nhưng hosted runner fail | OS image, architecture, JDK vendor hoặc native library khác | Cố định OS/image và kiểm thử trên môi trường tương ứng |
| Build thay đổi dù commit không đổi | Runner image, action, JDK patch hoặc dependency version trôi | Pin version/digest phù hợp và ghi lại tool metadata |
| JDK setup step báo không hỗ trợ version | Action/runner cũ hoặc distribution không có package cho platform | Nâng action/runner hoặc chọn package phù hợp |
| Jenkins dùng sai JDK | Tool name không khớp hoặc agent có installation path khác | Kiểm tra Manage Jenkins > Tools và Tool Locations |
| GitLab job không tìm thấy `java` | Image không chứa JDK hoặc job chạy shell executor khác dự kiến | Kiểm tra `image`, executor và `PATH` |
| Cache restore làm build khó tái hiện | Cache key không tính đến Wrapper/JDK/dependency inputs | Điều chỉnh cache key; xác minh version độc lập với cache |
| Java 25 build fail nhưng Java 17 pass | Plugin/framework chưa hỗ trợ JDK mới hoặc có thay đổi runtime | Khoanh vùng plugin/dependency, kiểm tra release notes và chạy thử nghiệm riêng |

## 20. Runbook chọn version cho một dự án mới

Dùng thứ tự sau khi thiết lập CI lần đầu:

1. Xác định runtime tối thiểu mà sản phẩm hỗ trợ.
2. Chọn LTS JDK distribution và vendor phù hợp với production.
3. Chọn Gradle/Maven Wrapper tương thích với JDK chạy build.
4. Cấu hình Java toolchain và `--release` theo yêu cầu sản phẩm.
5. Chọn runner OS, architecture và container image.
6. Pin CI action/plugin vào release đã kiểm tra; dùng SHA hoặc digest khi cần immutable reference.
7. Thiết lập matrix gồm baseline và các runtime cần hỗ trợ.
8. Chạy compile, unit test, integration test và package.
9. In version thực tế trong log.
10. Thiết lập dependency cache với key phản ánh version inputs.
11. Thiết lập quy trình cập nhật JDK patch và CI tooling.
12. Ghi lại version đã chọn cùng lý do và thời điểm đánh giá.

## 21. Checklist

- [ ] Đã xác định Java runtime tối thiểu mà ứng dụng hỗ trợ.
- [ ] Đã chọn JDK LTS và distribution/vendor phù hợp.
- [ ] Đã phân biệt JVM chạy CI build với Java toolchain.
- [ ] Đã cấu hình `--release`/`maven.compiler.release` theo runtime target.
- [ ] Đã kiểm tra Gradle/Maven Wrapper tương thích với JDK.
- [ ] Đã pin Gradle/Maven Wrapper và plugin version.
- [ ] Đã chọn runner OS/architecture và container image phù hợp.
- [ ] Đã cố định action/plugin version và cân nhắc SHA/digest pinning.
- [ ] Đã thiết lập matrix cho baseline và runtime cần hỗ trợ.
- [ ] Đã in `java --version`, `javac --version` và build tool version trong CI.
- [ ] Đã xác minh toolchain compiler/test launcher.
- [ ] Đã kiểm tra dependency lock/verification và cache key.
- [ ] Đã thử build trên môi trường gần production.
- [ ] Đã có lịch cập nhật security patch và nâng version CI.
- [ ] Đã ghi lại quyết định version để các thành viên có thể tái tạo build.

## 22. Tài liệu tham khảo

- Oracle Java Verified Portfolio Support Roadmap: https://www.oracle.com/java/technologies/jvp-support-roadmap.html
- Gradle 9.9.0 — Compatibility Matrix: https://docs.gradle.org/9.9.0/userguide/compatibility.html
- Gradle 9.9.0 — Toolchains for JVM Projects: https://docs.gradle.org/9.9.0/userguide/toolchains.html
- Gradle User Manual — Building Java & JVM Projects: https://docs.gradle.org/current/userguide/building_java_projects.html
- GitHub Actions — actions/setup-java: https://github.com/actions/setup-java
- GitHub Actions — Secure Use Reference: https://docs.github.com/en/actions/reference/security/secure-use
- GitLab CI/CD YAML — image keyword: https://docs.gitlab.com/ci/yaml/#image
- Jenkins — Managing Tools: https://www.jenkins.io/doc/book/managing/tools/

Chọn version CI tốt bắt đầu từ runtime mà sản phẩm cam kết hỗ trợ. Hãy cố định build tool và môi trường runner, chọn JDK toolchain phù hợp, đặt Java release target rõ ràng, rồi dùng matrix để kiểm thử các runtime cần hỗ trợ. Pinning tạo ra build có thể tái tạo; quy trình cập nhật định kỳ giúp pipeline vẫn nhận được bản vá bảo mật và cải tiến mới.