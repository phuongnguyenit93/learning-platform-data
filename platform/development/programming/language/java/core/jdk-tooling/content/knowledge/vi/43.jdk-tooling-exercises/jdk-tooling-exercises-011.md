# Tích hợp toàn bộ JDK Tooling vào CI

CI (Continuous Integration) tự động hóa vòng đời build Java: chọn JDK và build tool, compile, test, kiểm tra bytecode/dependency, tạo JAR, sinh Javadoc, đóng gói runtime/installer, ký artifact, xác minh checksum và lưu bằng chứng của lần build. Khi tích hợp đúng, mỗi commit được kiểm tra theo cùng một quy trình và release có thể truy vết tới source revision cùng toolchain đã tạo ra nó.

Không phải mọi lệnh JDK đều phải chạy ở mọi pull request. CI nên phân chia theo mục đích: kiểm tra nhanh ở pull request; kiểm tra tương thích và chẩn đoán mở rộng theo lịch; đóng gói native và ký số trong release pipeline. jlink chỉ dùng khi cần custom runtime từ module; jpackage chỉ dùng khi phân phối application image/installer; jcmd cần JVM đích còn chạy; jarsigner chỉ chạy trong phát hành có chứng thư ký hợp lệ.

## 1. Toàn cảnh các công cụ trong pipeline

| Giai đoạn | Công cụ | Kết quả/điều kiện cần kiểm tra |
| --- | --- | --- |
| Chuẩn bị môi trường | java, javac, Gradle/Maven Wrapper | Ghi version, vendor, build JVM, compiler JDK và OS |
| Compile | javac hoặc task compile của Gradle/Maven | Bytecode/API target đúng Java release |
| Test | java, Gradle Test, Maven Surefire/Failsafe | Unit/integration test pass trên các JDK hỗ trợ |
| Kiểm tra artifact | jar, javap | Manifest, nội dung archive và class-file version đúng |
| Phân tích dependency | jdeps, jdeprscan | Không dùng JDK internal API ngoài chủ đích; kiểm tra deprecated API |
| Tài liệu | javadoc | API docs sinh thành công, DocLint không có lỗi |
| Runtime tùy chỉnh | jlink | Image chỉ chứa các module cần thiết, launcher chạy được |
| Application image/installer | jpackage | Package đúng OS/architecture, smoke test chạy được |
| Chứng thư và ký | keytool, jarsigner | Certificate chain hợp lệ, chữ ký và timestamp được xác minh |
| Chẩn đoán | jcmd, jfr, jstack, jmap, jstat | Thread dump, heap/JVM information và Flight Recording khi cần |
| Lưu kết quả | SHA-256, CI artifact upload, provenance report | JAR, docs, test reports, checksum và build metadata được lưu cùng nhau |

Một pipeline tốt dùng build tool làm đường đi chính cho compile/test/package, sau đó gọi các JDK tools trực tiếp để kiểm tra đầu ra. Điều này giúp các bước chạy đúng thứ tự và dùng cùng artifact.

## 2. Xác định hợp đồng build trước khi cấu hình CI

Repository cần ghi rõ:

- JDK distribution/vendor và các Java version cần hỗ trợ.
- Java release target, ví dụ Java 17.
- Gradle/Maven version qua Wrapper.
- Plugin versions và dependency versions/lock state.
- Lệnh build chuẩn, test profiles và tên artifact.
- OS/architecture cần tạo native package.
- Những bước chỉ chạy trên release: signing, timestamp, publishing và attestation.

Phân biệt **JDK chạy build**, **compiler/test toolchain** và **release target**. Ví dụ build có thể chạy bằng JDK 25, compiler dùng JDK 25 nhưng --release 17 tạo bytecode và giới hạn API ở Java 17. --release không chọn JDK compiler; toolchain mới quyết định compiler và test launcher.

Dùng Gradle/Maven Wrapper để CI không phụ thuộc build tool cài sẵn trên runner. Với Gradle, pin distributionUrl và cấu hình distributionSha256Sum lấy từ checksum chính thức. Kiểm tra gradle-wrapper.jar mỗi khi nâng cấp Wrapper vì file này được thực thi trước khi các kiểm soát bên trong build chạy.

## 3. Cấu hình Gradle cho CI

Ví dụ build.gradle dùng Java 17 làm baseline, cho phép CI truyền JDK matrix bằng property, tạo executable JAR và làm Javadoc warnings thành lỗi:

```groovy
plugins {
    id 'java'
    id 'application'
}

group = 'com.example'
version = '1.0.0'

def ciJdk = providers.gradleProperty('ciJdk')
    .map { Integer.parseInt(it) }
    .getOrElse(17)

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(ciJdk)
    }
}

application {
    mainClass = 'com.example.Main'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
    options.compilerArgs.addAll(['-Xlint:all'])
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}

tasks.withType(Javadoc).configureEach {
    options.addBooleanOption('Werror', true)
}

tasks.named('jar', Jar) {
    archiveBaseName = 'myapp'
    manifest {
        attributes(
            'Main-Class': 'com.example.Main',
            'Implementation-Version': project.version
        )
    }
}
```

Với cấu hình này, file JAR mẫu là build/libs/myapp-1.0.0.jar. Điều chỉnh mainClass, test framework và version theo dự án. Task check chạy các verification tasks được gắn vào lifecycle; javadoc cần được gọi rõ nếu muốn CI kiểm tra tài liệu API ở mọi build.

### Gradle Wrapper

Commit các file gradlew, gradlew.bat, gradle/wrapper/gradle-wrapper.jar và gradle/wrapper/gradle-wrapper.properties. Ví dụ:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.2.1-bin.zip
distributionSha256Sum=<SHA256_OFFICIAL_CUA_DISTRIBUTION>
```

Thay giá trị checksum bằng checksum chính thức của đúng distribution đã pin. Không tự tạo checksum từ file ZIP vừa tải về rồi dùng chính giá trị đó để xác minh file.

Lệnh local và CI phải dùng ./gradlew hoặc gradlew.bat, không dùng gradle toàn cục.

## 4. GitHub Actions: kiểm tra pull request và build matrix

Workflow dưới đây chạy trên Java 17, 21 và 25. Mỗi job dùng JDK trong matrix để compile/test, nhưng options.release = 17 giữ compatibility baseline ở Java 17.

Tạo .github/workflows/java-ci.yml:

```yaml
name: Java CI

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify:
    name: Verify with JDK ${{ matrix.jdk }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        jdk: ['17', '21', '25']

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.jdk }}
          cache: gradle

      - name: Record toolchain
        run: |
          mkdir -p build/reports/toolchain
          {
            java --version
            javac --version
            jar --version
            javadoc --version
            jdeps --version
            jlink --version
            jpackage --version
            ./gradlew --version
            ./gradlew javaToolchains
            git rev-parse HEAD
            git status --short
          } > build/reports/toolchain/environment.txt 2>&1

      - name: Compile, test, document and package
        run: |
          ./gradlew --no-daemon \
            -PciJdk=${{ matrix.jdk }} \
            clean check javadoc jar

      - name: Inspect JAR with JDK tools
        run: |
          APP_JAR=build/libs/myapp-1.0.0.jar
          test -f "$APP_JAR"
          mkdir -p build/reports/jdk

          jar --validate --file "$APP_JAR"
          jar --list --verbose --file "$APP_JAR" \
            > build/reports/jdk/jar-contents.txt

          jdeps --multi-release 17 --jdk-internals "$APP_JAR" \
            > build/reports/jdk/internal-api-report.txt

          jdeprscan --release 17 "$APP_JAR" \
            > build/reports/jdk/deprecated-api-report.txt

          javap -classpath "$APP_JAR" -verbose com.example.Main \
            > build/reports/jdk/main-class.txt

          grep -q "major version: 61" \
            build/reports/jdk/main-class.txt

      - name: Upload JAR for release packaging
        if: ${{ matrix.jdk == '17' }}
        uses: actions/upload-artifact@v7
        with:
          name: myapp-jar
          path: build/libs/myapp-1.0.0.jar
          if-no-files-found: error

      - name: Upload reports and test results
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: java-ci-reports-${{ matrix.jdk }}
          path: |
            build/reports/**
            build/test-results/**
            build/docs/javadoc/**
          if-no-files-found: warn
```

Trong workflow này:

- setup-java cài JDK, thiết lập JAVA_HOME/PATH và cache dependency/wrapper phù hợp.
- ./gradlew --version ghi Gradle version cùng JVM chạy Gradle; javaToolchains liệt kê JDK mà Gradle phát hiện.
- check, javadoc và jar tạo test results, API docs và artifact.
- jar --validate kiểm tra archive; jar --list lưu nội dung để điều tra khi package sai.
- jdeps --jdk-internals báo dependency tới JDK internal APIs. Lưu report và áp dụng policy review/fail nếu dự án cấm các dependency này.
- jdeprscan --release 17 kiểm tra việc sử dụng deprecated API theo release target. Đặt ngưỡng xử lý warning theo chính sách tương thích của dự án.
- javap -verbose kiểm tra class-file major version. Java 17 có major version 61; vì vậy workflow fail nếu class mẫu không đúng baseline.
- Artifact JAR chỉ được upload từ job Java 17 để release dùng đúng binary đã qua kiểm tra baseline; các matrix job còn lại vẫn kiểm tra tương thích.

Nếu ứng dụng dùng thư viện ngoài, cung cấp runtime dependency classpath cho jdeps bằng --class-path (hoặc module path với modular app). Chỉ phân tích một JAR thiếu dependency có thể tạo báo cáo không đầy đủ.

actions/setup-java hỗ trợ nhiều JDK distribution, version matrix, cache Maven/Gradle, Maven Toolchains và xác minh checksum của JDK archive khi nhà cung cấp công bố checksum. Với yêu cầu supply-chain nghiêm ngặt, pin GitHub Actions bằng commit SHA đã xác minh và xác minh Gradle Wrapper JAR/distribution.

## 5. Maven: tích hợp cùng quy trình

Nếu dự án dùng Maven, chạy Wrapper và verify để compile, unit test, integration test (khi Failsafe được cấu hình), package và các verification goals đã bind vào lifecycle.

Ví dụ phần cấu hình plugin trong pom.xml:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
</properties>

<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-enforcer-plugin</artifactId>
        <version>3.6.3</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.16.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.5</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-failsafe-plugin</artifactId>
        <version>3.5.5</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-javadoc-plugin</artifactId>
        <version>3.12.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </pluginManagement>

  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-enforcer-plugin</artifactId>
      <executions>
        <execution>
          <id>enforce-build-environment</id>
          <goals>
            <goal>enforce</goal>
          </goals>
          <configuration>
            <rules>
              <requireMavenVersion>
                <version>[3.9,4)</version>
              </requireMavenVersion>
              <requireJavaVersion>
                <version>[17,26)</version>
              </requireJavaVersion>
            </rules>
          </configuration>
        </execution>
      </executions>
    </plugin>

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
      </configuration>
    </plugin>

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-javadoc-plugin</artifactId>
      <configuration>
        <failOnWarnings>true</failOnWarnings>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Điều chỉnh version range trong Enforcer theo support policy. requireJavaVersion kiểm tra JVM đang chạy Maven. Nếu compiler hoặc test cần JDK riêng, cấu hình Maven Toolchains; không nhầm Maven runtime với compiler toolchain.

Workflow Maven tương ứng:

```yaml
name: Maven Java CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        jdk: ['17', '21', '25']

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.jdk }}
          cache: maven

      - name: Record toolchain
        run: |
          java --version
          javac --version
          ./mvnw --version
          ./mvnw toolchains:display-discovered-jdk-toolchains

      - name: Verify
        run: |
          ./mvnw --batch-mode --no-transfer-progress clean verify
          ./mvnw --batch-mode --no-transfer-progress javadoc:javadoc

      - name: Inspect artifact
        run: |
          APP_JAR=target/myapp-1.0.0.jar
          jar --validate --file "$APP_JAR"
          jar --list --verbose --file "$APP_JAR"
          jdeps --multi-release 17 --jdk-internals "$APP_JAR"
          jdeprscan --release 17 "$APP_JAR"
```

setup-java có thể tạo Maven Toolchains entries cho JDK đã cài. Nếu POM yêu cầu toolchain version/vendor cụ thể, đảm bảo action cài đúng distribution và ~/.m2/toolchains.xml cung cấp mapping tương ứng. Dùng ./mvnw, không dựa vào Maven cài toàn cục.

Maven verify không tự động chạy Javadoc goal trong mọi project; gọi javadoc:javadoc hoặc bind goal vào lifecycle nếu muốn nó trở thành gate bắt buộc. Maven Compiler Plugin release giới hạn language/API/bytecode; Maven Toolchains chọn JDK thực sự dùng bởi plugin có hỗ trợ toolchain.

## 6. Đưa jdeps, jlink và jpackage vào giai đoạn đóng gói

Ba công cụ này phục vụ các mục đích khác nhau:

- jdeps phân tích dependency giữa class, package, JAR và module. Dùng --print-module-deps để lấy module dependency list phục vụ jlink.
- jlink tạo custom runtime image từ module cùng dependency bắc cầu. Chỉ dùng khi ứng dụng là modular hoặc dependency graph đã được chuyển thành module phù hợp.
- jpackage tạo application image hoặc native installer. Nếu không cung cấp runtime image, jpackage có thể tự gọi jlink để tạo runtime cho package.

### Tạo runtime image bằng jlink

Ví dụ cho modular app có module com.example.myapp và main class com.example.Main:

```bash
APP_JAR=build/libs/myapp-1.0.0.jar

MODULE_DEPS=$(jdeps \
  --module-path "$APP_JAR" \
  --print-module-deps \
  "$APP_JAR")

jlink \
  --module-path "$JAVA_HOME/jmods:$APP_JAR" \
  --add-modules "com.example.myapp,$MODULE_DEPS" \
  --launcher myapp=com.example.myapp/com.example.Main \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime

build/runtime/bin/myapp
```

Thay module và main class bằng tên thực tế. jdeps trả về dependency của ứng dụng; module gốc được thêm rõ ràng vào --add-modules. Chạy launcher trong runtime image như smoke test trước khi đóng gói. Runtime image phải được cập nhật khi JDK security update hoặc dependency module thay đổi.

Với JDK trên Windows, path separator của module path là dấu ; thay vì :. Dùng PowerShell hoặc script riêng cho runner Windows.

### Tạo application image/installer bằng jpackage

Với ứng dụng không modular, thư mục input chứa JAR và resource:

```bash
mkdir -p dist
cp build/libs/myapp-1.0.0.jar dist/

jpackage \
  --type app-image \
  --name MyApp \
  --app-version 1.0.0 \
  --input dist \
  --main-jar myapp-1.0.0.jar \
  --main-class com.example.Main \
  --dest build/package
```

Smoke test application image theo OS:

```bash
# Linux
./build/package/MyApp/bin/MyApp

# macOS
./build/package/MyApp.app/Contents/MacOS/MyApp
```

Windows PowerShell:

```powershell
$process = Start-Process -FilePath ".\\build\\package\\MyApp\\MyApp.exe" -Wait -PassThru -NoNewWindow
if ($process.ExitCode -ne 0) {
    exit $process.ExitCode
}
```

Đối với modular app, có thể dùng --module-path và --module thay cho --input, --main-jar, --main-class. app-image tạo thư mục chạy được để smoke test; các loại package như MSI/EXE, DEB/RPM hoặc PKG/DMG là bước tiếp theo.

**Native package phải được tạo trên OS đích.** Dùng matrix runner Windows, Linux và macOS để tạo đúng định dạng. Windows MSI/EXE cần công cụ đóng gói phù hợp như WiX; macOS distribution cần quy trình Developer ID signing/notarization; Linux package cần công cụ package của distro. jpackage không cross-compile native installer cho hệ điều hành khác.

## 7. Ký artifact bằng keytool và jarsigner

keytool quản lý keystore, key pair và certificate. jarsigner ký JAR và xác minh signature/integrity. Tạo hoặc import release key trong quy trình quản trị khóa riêng; CI chỉ nhận credential từ protected secret store hoặc HSM/KMS.

Trong release job, chỉ chạy sau khi build/test đã pass và chỉ ký đúng JAR đã upload từ job verify. Ví dụ trên Linux runner:

```bash
mkdir -p dist
printf '%s' "$JAR_SIGNING_KEYSTORE_BASE64" \
  | base64 --decode > "$RUNNER_TEMP/release.p12"
chmod 600 "$RUNNER_TEMP/release.p12"

export JAR_STORE_PASSWORD
export JAR_KEY_PASSWORD

keytool -list -v \
  -keystore "$RUNNER_TEMP/release.p12" \
  -storetype PKCS12 \
  -storepass:env JAR_STORE_PASSWORD

jarsigner \
  -keystore "$RUNNER_TEMP/release.p12" \
  -storetype PKCS12 \
  -storepass:env JAR_STORE_PASSWORD \
  -keypass:env JAR_KEY_PASSWORD \
  -tsa "$JAR_TSA_URL" \
  -signedjar dist/myapp-1.0.0-signed.jar \
  dist/myapp-1.0.0.jar \
  "$JAR_SIGNING_ALIAS"

jarsigner -verify -strict -verbose -certs \
  dist/myapp-1.0.0-signed.jar

sha256sum dist/myapp-1.0.0-signed.jar \
  > dist/myapp-1.0.0-signed.jar.sha256
```

Khai báo JAR_SIGNING_KEYSTORE_BASE64, JAR_STORE_PASSWORD, JAR_KEY_PASSWORD, JAR_SIGNING_ALIAS và JAR_TSA_URL trong protected environment của release job. -storepass:env và -keypass:env đọc password từ environment variable, tránh ghi password rõ trong command. Không in secret hoặc keystore vào log/artifact; xóa file keystore tạm sau khi ký.

jarsigner -verify -strict biến severe certificate warnings thành lỗi. Self-signed test certificate chỉ phù hợp để kiểm thử pipeline; production cần certificate chain được bên nhận tin cậy và timestamp authority hợp lệ. Chữ ký JAR và checksum SHA-256 có mục đích khác nhau: signature xác thực signer/integrity theo certificate trust model, checksum xác nhận byte của file.

jarsigner ký JAR; nó không thay thế Authenticode cho Windows executable hay Developer ID signing/notarization cho macOS app bundle. Native installer signing là gate riêng sau khi jpackage hoàn tất.

## 8. Release job: đóng gói từ artifact đã được kiểm tra

Ví dụ job tạo application image trên từng OS khi push tag release. Job download JAR đã upload từ matrix Java 17 và đóng gói lại trên runner đích:

```yaml
  package:
    if: ${{ startsWith(github.ref, 'refs/tags/v') }}
    needs: verify
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - uses: actions/download-artifact@v7
        with:
          name: myapp-jar
          path: dist

      - name: Create Windows app image
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          jpackage --type app-image --name MyApp --app-version 1.0.0 --input dist --main-jar myapp-1.0.0.jar --main-class com.example.Main --win-console --dest build/package

      - name: Create Linux or macOS app image
        if: runner.os != 'Windows'
        run: |
          jpackage --type app-image --name MyApp \
            --app-version 1.0.0 \
            --input dist \
            --main-jar myapp-1.0.0.jar \
            --main-class com.example.Main \
            --dest build/package

      - name: Smoke test Linux image
        if: runner.os == 'Linux'
        run: ./build/package/MyApp/bin/MyApp

      - name: Smoke test macOS image
        if: runner.os == 'macOS'
        run: ./build/package/MyApp.app/Contents/MacOS/MyApp

      - name: Smoke test Windows image
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          $process = Start-Process -FilePath ".\\build\\package\\MyApp\\MyApp.exe" -Wait -PassThru -NoNewWindow
          if ($process.ExitCode -ne 0) {
            exit $process.ExitCode
          }

      - uses: actions/upload-artifact@v7
        with:
          name: myapp-image-${{ runner.os }}
          path: build/package/**
          if-no-files-found: error
```

Job package cần nằm cùng cấp với verify trong jobs của workflow. Nếu release cần MSI/DEB/RPM/PKG/DMG, thay --type app-image bằng định dạng phù hợp và cài các prerequisite trên runner. Chỉ publish sau khi smoke test và signing gate của từng OS pass.

Không build lại JAR ở release job. Dùng artifact đã qua test, ký chính binary đó, rồi lưu signed JAR, checksum và application image. Cách này giữ mối liên hệ giữa kết quả CI và file được phát hành.

## 9. Chẩn đoán JVM trong CI bằng jcmd và JFR

jcmd dùng để gửi diagnostic command tới JVM đang chạy trên cùng host, thường cùng effective user/group. Nó hữu ích khi CI chạy integration service hoặc test JVM còn sống sau timeout.

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> Thread.print \
  > build/reports/diagnostics/thread-dump.txt
jcmd <PID> GC.heap_info \
  > build/reports/diagnostics/heap-info.txt
```

Không phải mọi test runner đều giữ JVM sống đủ lâu để attach. Nếu process đã thoát, jcmd không thể khôi phục thread dump. Với test timeout, có thể cấu hình Surefire/Failsafe để thu thập thread dump hoặc bật JFR từ startup.

Ghi JFR trong một lần chạy smoke/integration:

```bash
mkdir -p build/reports/diagnostics

java \
  -XX:StartFlightRecording=filename=build/reports/diagnostics/ci.jfr,settings=profile,dumponexit=true \
  -jar build/libs/myapp-1.0.0.jar

jfr summary build/reports/diagnostics/ci.jfr
```

profile thu thập chi tiết hơn default và có thể tăng overhead. Chỉ bật trên job cần điều tra performance hoặc flaky test. Thread dump, heap dump và JFR có thể chứa dữ liệu nhạy cảm; giới hạn quyền truy cập, retention và upload của chúng.

Khi job thất bại, lưu jcmd -l, application logs, test reports và dump nếu target JVM còn chạy. Không coi jcmd -l không có kết quả là bằng chứng JVM chưa từng chạy; runner/container namespace có thể khác và process có thể đã thoát.

## 10. Ghi provenance và tạo checksum cho mỗi build

Mỗi artifact nên đi cùng một report gồm:

- Git commit SHA, tag và trạng thái working tree.
- Gradle/Maven Wrapper version và distribution checksum.
- JDK distribution/vendor/version, build JVM và compiler/test toolchain.
- Java release target, OS, architecture và runner/container image.
- Build command, test result và plugin/dependency lock state.
- JAR manifest, module/dependency report, Javadoc output.
- SHA-256 của JAR, signed JAR và native package.
- Certificate identity, timestamp và signature verification result khi release.

Ví dụ trên Linux:

```bash
java --version
javac --version
./gradlew --version
./gradlew javaToolchains
git rev-parse HEAD
sha256sum build/libs/myapp-1.0.0.jar
```

Trên Windows PowerShell:

```powershell
java --version
javac --version
.\gradlew.bat --version
.\gradlew.bat javaToolchains
git rev-parse HEAD
Get-FileHash .\\build\\libs\\myapp-1.0.0.jar -Algorithm SHA256
```

Lưu report, JAR, Javadoc, test results, dependency analysis, checksum và package image dưới dạng CI artifacts. Không ghi toàn bộ environment variables vào report vì chúng có thể chứa credentials. Chỉ ghi whitelist metadata cần thiết và redact giá trị nhạy cảm.

Để tăng tính reproducible, pin Wrapper, JDK distribution/version, plugin/dependency versions, locale/timezone và output timestamp. Gradle archive tasks hỗ trợ reproducible file order/timestamps; Maven có thể dùng project.build.outputTimestamp. Cache chỉ là tối ưu thời gian: cache hit không thay thế version pinning, dependency verification hoặc kiểm tra checksum.

## 11. Bố trí quality gates theo loại pipeline

| Gate | Pull request | Nightly/scheduled | Tag/release |
| --- | --- | --- | --- |
| JDK/build tool version | Bắt buộc | Bắt buộc | Bắt buộc |
| Compile, unit test, integration test | Bắt buộc | Bắt buộc | Bắt buộc |
| Javadoc/DocLint | Bắt buộc với library/API | Bắt buộc | Bắt buộc |
| jar --validate, javap, jdeps, jdeprscan | Bắt buộc theo policy | Bắt buộc | Bắt buộc |
| Matrix nhiều JDK/OS | Baseline + JDK được hỗ trợ | Matrix rộng hơn | Release matrix đã duyệt |
| jlink custom runtime | Khi thay đổi module | Có thể chạy thường xuyên | Khi phát hành runtime image |
| jpackage native image/installer | Có thể bỏ qua | Có thể build thử | Bắt buộc nếu phân phối installer |
| keytool/jarsigner | Không dùng release private key | Có thể kiểm tra certificate public | Ký và verify bằng protected secret |
| jcmd/JFR profiling | Chỉ khi cần chẩn đoán | Hữu ích cho flaky/performance tests | Theo dõi smoke/soak test |
| Checksum/provenance/upload | Lưu test/report | Lưu report đầy đủ | Lưu signed artifact, checksum và provenance |

Không mở signing secrets cho pull request từ fork hoặc code chưa được tin cậy. Dùng protected GitHub environment cho release, giới hạn quyền token, pin action theo commit SHA khi chính sách yêu cầu và chỉ cho phép release job đọc key/certificate.

## 12. Lỗi CI thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Local pass, CI fail | JDK distribution/version, OS hoặc build tool khác | So sánh toolchain report và Wrapper |
| Unsupported class file major version | Compiler/runtime/plugin không tương thích bytecode | Kiểm tra build JVM, plugin và JDK toolchain |
| javac báo API không có | --release không khớp baseline | Kiểm tra options.release hoặc maven.compiler.release |
| Javadoc -Werror fail | Thiếu comment/tag, link hoặc HTML không hợp lệ | Sửa Javadoc; không tắt DocLint chỉ để làm build xanh |
| jdeps báo missing dependency | Chưa cung cấp classpath/module path runtime đầy đủ | Truyền resolved dependency path hoặc module path |
| jdeps --jdk-internals phát hiện internal API | Code phụ thuộc API JDK không ổn định | Thay bằng API supported hoặc ghi nhận exception có thời hạn |
| jdeprscan báo deprecated API | Code dùng API đã deprecated trong release target | Review migration plan và policy deprecation |
| jlink báo module not found | Thiếu module path/JMOD hoặc module name sai | Kiểm tra jdeps --print-module-deps và module-info |
| jpackage thiếu WiX/tool hệ điều hành | Runner chưa có prerequisite native package | Cài tool tương ứng trên runner đúng OS |
| jpackage image không chạy | Input, main class, runtime hoặc native dependency sai | Chạy launcher từ app-image và lưu config/log |
| jarsigner -verify -strict fail | Certificate chain không tin cậy, hết hạn hoặc signature lỗi | Dùng certificate chain đúng, timestamp và kiểm tra alias |
| Chữ ký hỏng sau khi verify | JAR bị chỉnh sửa sau khi ký | Hoàn tất mọi thay đổi trước khi ký lại artifact cuối |
| jcmd không tìm thấy PID | JVM đã thoát hoặc nằm trong namespace khác | Giữ process sống, chạy cùng host/user/container và lấy PID đúng |
| Hash khác giữa hai build | Timestamp, dependency hoặc generated metadata khác | Kiểm tra reproducible build và toolchain provenance |

## 13. Checklist hoàn tất JDK Tooling CI

1. Commit Gradle/Maven Wrapper và pin distribution/checksum.
2. Chọn JDK vendor/version, Java release target và support matrix.
3. Ghi riêng build JVM, compiler JDK, test launcher và production runtime.
4. Pin plugin/dependency versions; bật lock/verification phù hợp.
5. Chạy compile, unit test và integration test qua Wrapper.
6. Chạy javadoc với DocLint và fail-on-warning theo policy.
7. Kiểm tra JAR bằng jar --validate, jar --list, javap.
8. Phân tích internal/deprecated API và module dependency bằng jdeps, jdeprscan.
9. Tạo runtime image bằng jlink khi ứng dụng modular cần custom runtime.
10. Tạo và smoke test application image/installer bằng jpackage trên OS đích.
11. Chỉ ký release artifact trong protected job; xác minh bằng jarsigner -verify -strict.
12. Kiểm tra certificate/keystore bằng keytool; không đưa private key vào repository.
13. Thu thập jcmd/JFR khi test JVM còn chạy và có nhu cầu chẩn đoán.
14. Tạo SHA-256 checksum, provenance report và upload JAR/docs/test/package outputs.
15. Chỉ publish artifact đã qua toàn bộ gate và giữ đúng binary đã test.

## 14. Ghi nhớ

- Wrapper và JDK toolchain tạo môi trường build nhất quán; --release xác định API/bytecode baseline.
- Gradle check hoặc Maven verify là trục chính của compile/test; gọi Javadoc và JDK analysis rõ ràng nếu chúng là release gate.
- jar, javap, jdeps, jdeprscan kiểm tra artifact và dependency sau khi build.
- jlink tạo runtime image từ module; jpackage tạo application image/installer theo OS đích.
- keytool quản lý/kiểm tra certificate; jarsigner ký và xác minh JAR.
- jcmd/JFR giúp điều tra JVM đang chạy; chúng không thay thế test assertions.
- Pull request không được truy cập release signing keys. Ký đúng artifact đã được kiểm tra, xác minh chain/timestamp rồi tạo checksum.
- CI artifact phải có JAR, test reports, Javadoc, toolchain/provenance, dependency reports và checksum.
- Không chạy mọi công cụ trong mọi job một cách máy móc; chỉ bật jlink, jpackage, signing và diagnostics khi mục tiêu sản phẩm cần chúng.

Khi CI kết nối được toàn bộ vòng đời từ toolchain đến artifact, nhóm có thể kiểm tra chất lượng trên nhiều JDK, đóng gói đúng nền tảng, ký đúng binary và truy lại môi trường đã tạo ra từng release.

## Tài liệu tham khảo

- [JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/index.html)
- [The jar Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [The javadoc Command and DocLint](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- [The jdeps Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- [The jlink Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
- [The jpackage Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html)
- [The jarsigner Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [Gradle: Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle: Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle: Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Maven: Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Maven Compiler Plugin: Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Surefire](https://maven.apache.org/surefire/)
- [Maven Javadoc Plugin](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html)
- [GitHub Actions: actions/setup-java](https://github.com/actions/setup-java)
