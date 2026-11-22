# Pin chính xác phiên bản JDK cho Java build

Pin phiên bản JDK nghĩa là mọi máy build đều sử dụng cùng một bản JDK đã được xác định, thay vì chỉ yêu cầu “Java 17” hoặc “Java mới nhất”. Một JDK cần được nhận diện bằng nhiều thông tin: Java feature/update/build version, nhà phân phối, VM implementation, hệ điều hành, kiến trúc CPU, loại package và checksum của bộ cài.

Ví dụ, hai máy đều báo Java 17 nhưng một máy dùng Temurin 17.0.15, máy kia dùng Corretto 17.0.15+6-LTS. Chúng cùng feature version, nhưng khác bản phân phối và có thể khác build. Nếu compiler, annotation processor hoặc runtime có hành vi phụ thuộc patch/vendor, kết quả build và test có thể khác nhau.

Pin JDK là một phần của reproducible build. Nó giúp xác định rõ compiler/runtime, nhưng vẫn cần cố định Gradle/Maven, plugin, dependencies, container image, OS/architecture và các yếu tố môi trường khác.

## 1. Một JDK cần pin những gì?

Một bản cài JDK có thể được mô tả bằng các trường sau:

| Thuộc tính | Ví dụ | Vì sao cần |
|---|---|---|
| Feature version | `17` | Chọn dòng Java chính |
| Runtime version đầy đủ | `17.0.15+6-LTS` | Phân biệt update và build |
| Distribution/vendor | Amazon Corretto | Phân biệt cách đóng gói và bản vá của nhà cung cấp |
| VM implementation | HotSpot | Phân biệt HotSpot, OpenJ9 và các VM khác |
| Vendor build/version | `Corretto-17.0.15.6.1` | Nhận diện build cụ thể của vendor |
| OS và architecture | Windows x64, Linux amd64, Linux arm64 | Chọn đúng binary |
| libc/platform variant | glibc hoặc musl | Tránh dùng package không tương thích |
| Package type | JDK, JRE, JDK có jmods | Đảm bảo có compiler/tool cần thiết |
| Archive checksum | SHA-256 của file tải về | Xác minh đúng bộ cài |
| Container image digest | `sha256` của image manifest | Cố định image chứa JDK |

Không chỉ lưu “Java 17”. Nếu yêu cầu tái lập build ở mức patch/build, hãy ghi rõ cả runtime version và vendor. Nếu cần chứng minh binary giống nhau, checksum hoặc image digest là lớp xác minh cuối cùng.

### 1.1. Đọc version string của Java

Từ Java 9, version number theo dạng:

~~~text
FEATURE.INTERIM.UPDATE.PATCH
~~~

Các thành phần có ý nghĩa:

- `FEATURE`: feature release, ví dụ 17 hoặc 21.
- `INTERIM`: interim release.
- `UPDATE`: bản cập nhật tương thích, thường chứa sửa lỗi và bảo mật.
- `PATCH`: emergency patch release.
- Phần sau dấu `+` là build number; thông tin sau dấu `-` có thể chứa định danh bổ sung của nhà cung cấp.

Ví dụ `17.0.15+6-LTS` có feature 17, update 15, build 6 và thông tin bổ sung `LTS`. Các vendor có thể biểu diễn phần bổ sung khác nhau.

### 1.2. Phân biệt các thuộc tính version

| Lệnh/thuộc tính | Nội dung |
|---|---|
| `java --version` | Version, vendor, runtime và VM |
| `javac --version` | Version của compiler, thường chỉ hiện số version |
| `java.version` | Product version |
| `java.runtime.version` | Runtime version đầy đủ, bao gồm build identifier |
| `java.vm.name` | Tên VM |
| `java.vm.version` | Version của VM |
| `java.vendor` | Chuỗi vendor do runtime cung cấp |
| `os.arch` | Kiến trúc mà JVM báo cáo |
| `java.home` | Thư mục Java runtime đang chạy |

Với JDK Corretto được dùng trong ví dụ thực hành:

~~~text
java.version = 17.0.15
java.runtime.version = 17.0.15+6-LTS
java.vendor = Amazon.com Inc.
java.vm.name = OpenJDK 64-Bit Server VM
java.vm.version = 17.0.15+6-LTS
os.arch = amd64
~~~

Lưu ý: Gradle có thể chuẩn hóa vendor thành `Amazon Corretto`, trong khi system property của JVM trả về `Amazon.com Inc.`. Đây là hai trường metadata khác nhau. Khi viết kiểm tra, hãy so sánh đúng loại giá trị với nguồn tương ứng.

Có thể xem system properties mà không cần viết code:

~~~bash
java -XshowSettings:properties -version
~~~

Trong output, tìm `java.version`, `java.runtime.version`, `java.vendor`, `java.vm.version`, `java.home` và `os.arch`.

JDK còn có file `release` ngay tại thư mục cài đặt. File này thường chứa `JAVA_VERSION`, `IMPLEMENTOR`, `IMPLEMENTOR_VERSION`, `OS_ARCH` và các thông tin build khác. Đây là nguồn chẩn đoán hữu ích khi cần xác định package đã được cài.

## 2. Phân biệt pin major version và pin exact build

Các cách khai báo dưới đây có độ chặt khác nhau:

| Cấu hình | Mức pin | Hạn chế |
|---|---|---|
| `17` | Feature version | Cho phép nhiều bản update/build của Java 17 |
| `17.0` | Feature/interim | Chưa xác định đầy đủ update/build |
| `17.0.15` | Version đến update | Chưa xác định build number và vendor |
| `17.0.15+6-LTS` | Full runtime version | Vẫn cần xác định vendor, package, OS và binary |
| Vendor + full runtime version + checksum | Rất chặt | Cần quản lý artifact và cập nhật pin |
| Container image digest chứa JDK đã xác minh | Cố định image bytes | Phụ thuộc platform/manifest và image provenance |

Một file version chỉ chứa `17` có thể hữu ích để chọn feature version thống nhất, nhưng không đủ để tái lập một build cần exact patch. Tương tự, tag container `jdk:17` hoặc `jdk:17.0.15` vẫn có thể được nhà cung cấp cập nhật hoặc di chuyển. Digest của image là định danh bất biến cho nội dung image.

### 2.1. Version file trong repository

Có thể lưu full version trong `.java-version`:

~~~text
17.0.15+6
~~~

File này cho biết version mong muốn, nhưng không tự xác định vendor. Vì vậy, CI và công cụ quản lý JDK vẫn cần khai báo distribution, ví dụ `corretto`.

GitHub Actions `setup-java` hỗ trợ đọc `.java-version`, `.tool-versions` và `.sdkmanrc` qua `java-version-file`. Nếu file chỉ có version, hãy cấu hình distribution riêng để tránh mỗi máy chọn một vendor khác nhau.

Một manifest của dự án nên ghi tối thiểu:

- Distribution và vendor.
- `java.runtime.version` đầy đủ.
- VM implementation/version.
- OS/architecture/package variant.
- SHA-256 của archive hoặc digest của image.
- Nguồn tải và chính sách xác minh chữ ký.

Không ghi đường dẫn `JAVA_HOME` của một developer vào manifest dùng chung. Đường dẫn cài đặt có thể khác trên Windows, Linux, macOS và CI; version/vendor/checksum mới là thông tin có thể đối chiếu giữa các máy.

## 3. Cài và xác minh JDK local

Tải JDK từ website/repository chính thức của vendor và chọn đúng OS, architecture, package type. Giải nén vào một thư mục có tên chứa full version, ví dụ:

~~~text
/opt/jdks/amazon-corretto-17.0.15.6
~~~

Trên Windows có thể dùng một đường dẫn riêng như:

~~~text
C:\jdks\amazon-corretto-17.0.15.6
~~~

Tránh dùng một thư mục chung như `C:\Java\current` nếu nó bị thay thế âm thầm khi có bản cập nhật. Một đường dẫn versioned giúp biết build đang sử dụng package nào.

### 3.1. Đặt JAVA_HOME tạm thời

PowerShell:

~~~powershell
$env:JAVA_HOME = "C:\jdks\amazon-corretto-17.0.15.6"
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"

java --version
javac --version
~~~

Linux/macOS:

~~~bash
export JAVA_HOME=/opt/jdks/amazon-corretto-17.0.15.6
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
~~~

Đường dẫn chỉ là ví dụ; hãy đặt đúng thư mục JDK đã được xác minh trên máy. Mở terminal mới sau khi thay đổi biến môi trường ở cấp user/system.

### 3.2. Xác minh checksum của archive

Sau khi tải file, tính SHA-256:

PowerShell:

~~~powershell
Get-FileHash .\amazon-corretto-17.0.15-windows-x64.zip -Algorithm SHA256
~~~

Linux:

~~~bash
sha256sum amazon-corretto-17.0.15-linux-x64.tar.gz
~~~

macOS:

~~~bash
shasum -a 256 amazon-corretto-17.0.15-macosx-x64.tar.gz
~~~

Nếu vendor phát hành chữ ký số, xác minh chữ ký bằng public key được lấy từ nguồn chính thức, ví dụ:

~~~bash
gpg --verify jdk-archive.tar.gz.asc jdk-archive.tar.gz
~~~

So sánh checksum với giá trị vendor công bố cho đúng file, version, OS và architecture. Không coi checksum lấy từ cùng một mirror không đáng tin cậy là bằng chứng xác thực độc lập.

Sau khi xác minh, lưu checksum cùng thông tin release hoặc đưa archive vào artifact repository nội bộ có kiểm soát. Khi cần cài lại, lấy đúng artifact đã được xác minh thay vì tải một file cùng tên từ nguồn bất kỳ.

## 4. Pin JDK trong Gradle

Gradle Java Toolchains rất hữu ích để chọn JDK cho compile, test, run và Javadoc. Tuy nhiên, cần hiểu giới hạn của API:

- `languageVersion` chọn Java feature version, ví dụ 17.
- `vendor` chọn vendor được Gradle nhận diện.
- `implementation` chọn loại VM như HotSpot hoặc OpenJ9.
- `JavaToolchainSpec` không có thuộc tính riêng để yêu cầu đúng `java.runtime.version` hoặc build number.

Do đó, cấu hình `languageVersion = 17` và `vendor = AMAZON` chưa đủ để pin `17.0.15+6-LTS`. Gradle có thể chọn một JDK khác vẫn thỏa mãn major/vendor. Muốn exact pin, hãy giới hạn tập JDK được Gradle phát hiện vào đúng installation đã quản lý và xác minh full runtime version trong build.

### 4.1. Chọn major version và vendor

Trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.AMAZON)
    }
}
~~~

Cấu hình trên chọn JDK 17 của Amazon. Nó không tự giới hạn update/build number.

### 4.2. Chỉ cho Gradle thấy một JDK đã pin

Trong `gradle.properties` của project:

~~~properties
org.gradle.java.installations.auto-detect=false
org.gradle.java.installations.auto-download=false
org.gradle.java.installations.paths=/opt/jdks/amazon-corretto-17.0.15.6
~~~

Trên Windows, dùng đường dẫn JDK cục bộ:

~~~properties
org.gradle.java.installations.auto-detect=false
org.gradle.java.installations.auto-download=false
org.gradle.java.installations.paths=C:/jdks/amazon-corretto-17.0.15.6
~~~

Khi tắt auto-detection và auto-download, Gradle chỉ được phép dùng toolchain từ các đường dẫn đã khai báo. Đường dẫn phải trỏ đến thư mục cài đặt JDK có `bin/java` và `bin/javac`.

Cách này hạn chế Gradle chọn một JDK khác trên máy developer hoặc runner. Nó cũng có nghĩa mỗi máy/runner phải được cài đúng JDK trước khi build.

Có thể xem Gradle phát hiện toolchain nào bằng:

~~~bash
./gradlew -q javaToolchains
~~~

### 4.3. Kiểm tra full runtime version trong build

Gradle cung cấp `JavaInstallationMetadata.javaRuntimeVersion`, chứa full runtime version gồm build number. Metadata `vendor` là tên vendor mà Gradle chuẩn hóa; không nhất thiết giống `System.getProperty("java.vendor")`.

Trong `gradle.properties`, lưu version và tên vendor mà Gradle trả về:

~~~properties
jdkRuntimeVersion=17.0.15+6-LTS
jdkGradleVendor=Amazon Corretto
~~~

Thêm task kiểm tra trong `build.gradle.kts`:

~~~kotlin
val expectedRuntime = providers.gradleProperty("jdkRuntimeVersion")
val expectedVendor = providers.gradleProperty("jdkGradleVendor")

tasks.withType<JavaCompile>().configureEach {
    inputs.property("pinnedJdkRuntimeVersion", expectedRuntime)
}

tasks.withType<Test>().configureEach {
    inputs.property("pinnedJdkRuntimeVersion", expectedRuntime)
}

tasks.withType<JavaExec>().configureEach {
    inputs.property("pinnedJdkRuntimeVersion", expectedRuntime)
}

tasks.register("verifyPinnedJdk") {
    // Metadata version is checked at every build invocation.
    outputs.upToDateWhen { false }

    doLast {
        val compiler = javaToolchains.compilerFor {
            languageVersion.set(JavaLanguageVersion.of(17))
            vendor.set(JvmVendorSpec.AMAZON)
        }.get()

        val launcher = javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
            vendor.set(JvmVendorSpec.AMAZON)
        }.get()

        listOf(
            "COMPILER" to compiler.metadata,
            "LAUNCHER" to launcher.metadata
        ).forEach { (role, metadata) ->
            check(metadata.javaRuntimeVersion == expectedRuntime.get()) {
                role + " expected " + expectedRuntime.get() +
                    " but found " + metadata.javaRuntimeVersion
            }

            check(metadata.vendor == expectedVendor.get()) {
                role + " expected Gradle vendor " + expectedVendor.get() +
                    " but found " + metadata.vendor
            }

            println(role + "_RUNTIME_VERSION=" + metadata.javaRuntimeVersion)
            println(role + "_GRADLE_VENDOR=" + metadata.vendor)
        }
    }
}
~~~

Task kiểm tra cả compiler và launcher. Nếu một máy có đúng Java 17 nhưng sai update/build, task sẽ fail. Khi đổi expected version, khai báo đó cũng trở thành input của compile/test/JavaExec tasks để thay đổi pin làm mất hiệu lực kết quả up-to-date/build cache tương ứng.

Điểm này quan trọng vì Gradle đánh dấu full runtime version/vendor trong `JavaInstallationMetadata` là metadata nội bộ; không nên mặc định patch/build number sẽ tự động tham gia mọi task cache key. Hãy khai báo pin như một input của task và chạy kiểm tra exact version mỗi build.

Output kiểm tra thành công trên Gradle 9.2.1 với Corretto 17.0.15+6-LTS:

~~~text
COMPILER_RUNTIME_VERSION=17.0.15+6-LTS
COMPILER_GRADLE_VENDOR=Amazon Corretto
LAUNCHER_RUNTIME_VERSION=17.0.15+6-LTS
LAUNCHER_GRADLE_VENDOR=Amazon Corretto
~~~

Có thể kiểm tra guard từ chối một version khác bằng cách chạy task với expected version không đúng:

~~~bash
./gradlew -PjdkRuntimeVersion=17.0.15+99 verifyPinnedJdk
~~~

Output lỗi dự kiến:

~~~text
COMPILER expected 17.0.15+99 but found 17.0.15+6-LTS
~~~

Build phải fail khi runtime version không khớp. Không bỏ qua lỗi này hoặc đổi expected version chỉ để làm build xanh; hãy cài đúng JDK đã pin hoặc cập nhật pin qua quy trình review.

### 4.4. Xác minh Gradle Daemon riêng

Project toolchain không quyết định JVM chạy Gradle Daemon. Nếu cần pin cả Daemon, hãy khởi chạy Gradle bằng `JAVA_HOME` trỏ đến JDK đã xác minh hoặc đặt `org.gradle.java.home` tới đúng installation.

Daemon JVM criteria của Gradle có thể pin Java feature version và vendor, nhưng không thay thế việc kiểm tra full patch/build version. Sau khi đổi đường dẫn JDK, dừng daemon cũ:

~~~bash
./gradlew --stop
./gradlew --version
~~~

`./gradlew --version` hiển thị Gradle version và JVM đang chạy Gradle. Dùng thêm `java --version` hoặc runtime identity probe để xác nhận full version.

### 4.5. Pin Gradle Wrapper

JDK không phải thành phần duy nhất của build environment. Dùng Gradle Wrapper để cố định Gradle distribution trong `gradle/wrapper/gradle-wrapper.properties`:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.2.1-bin.zip
~~~

Có thể thêm `distributionSha256Sum` lấy từ trang checksum chính thức của Gradle để xác minh archive Wrapper tải về. Gradle Wrapper version và JDK version là hai pin riêng biệt.

## 5. Pin JDK trong Maven

Maven có thể chạy bằng một JDK nhưng dùng JDK khác làm toolchain cho compiler, Surefire, Failsafe và các plugin tương thích toolchain.

Maven Toolchains dùng hai phần:

1. `toolchains.xml` mô tả JDK đã cài trên máy và version/vendor của nó.
2. `maven-toolchains-plugin` trong POM yêu cầu một toolchain phù hợp.

### 5.1. Khai báo JDK trong toolchains.xml

File mặc định nằm tại `~/.m2/toolchains.xml`. Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17.0.15+6-LTS</version>
            <vendor>Amazon.com Inc.</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/amazon-corretto-17.0.15.6</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

`jdkHome` phải trỏ đến đúng JDK đã xác minh. `version` và `vendor` là các token để Maven so khớp.

### 5.2. Yêu cầu exact version trong POM

Ví dụ cấu hình Maven Toolchains Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>17.0.15+6-LTS</version>
                <vendor>Amazon.com Inc.</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

Với một version đơn, Maven yêu cầu giá trị trong POM khớp chính xác với token trong `toolchains.xml`. Ví dụ version `17` không khớp token `17.0.15`; version range như `[17,18)` có thể khớp nhiều bản hơn. Nếu cần exact patch/build, dùng full version string ở cả hai nơi.

Vendor cũng được so khớp chính xác, không phân biệt chữ hoa/chữ thường. Nếu CI tự sinh `toolchains.xml`, hãy kiểm tra giá trị vendor/version mà công cụ sinh ra trước khi đặt yêu cầu trong POM. Ví dụ GitHub `setup-java` có thể ghi distribution name như `corretto`, còn file được sinh bằng Maven discovery có thể ghi `java.vendor` như `Amazon.com Inc.`.

### 5.3. Maven runtime và Maven toolchain là hai JDK khác nhau

`mvn --version` cho biết JDK chạy Maven. Toolchain được chọn sau đó có thể là một JDK khác. Kiểm tra cả hai:

~~~bash
mvn --version
mvn -t ~/.m2/toolchains.xml -B -ntp clean verify
~~~

Trên Windows, có thể dùng đường dẫn toolchains file phù hợp với máy. Không commit `toolchains.xml` có đường dẫn tuyệt đối của một developer vào repository; CI nên tạo file từ JDK đã cài hoặc mount cấu hình toolchain riêng.

Nếu dùng `maven-compiler-plugin`, cấu hình thêm `release` để giới hạn API và bytecode đích. `maven.compiler.release` không thay thế Maven Toolchains và không pin patch JDK.

## 6. Pin JDK trong GitHub Actions CI

GitHub Actions `setup-java` cho phép chọn distribution và version cụ thể. Ví dụ với Amazon Corretto:

~~~yaml
steps:
  - uses: actions/checkout@v4

  - name: Install pinned JDK
    id: setup-java
    uses: actions/setup-java@v6
    with:
      distribution: corretto
      java-version: '17.0.15+6'
      force-download: true
      cache: gradle

  - name: Verify JDK identity
    run: |
      java --version
      javac --version
      java -XshowSettings:properties -version

  - name: Build
    run: ./gradlew --no-daemon clean check
~~~

`java-version` hỗ trợ version cụ thể theo dạng JEP 322, bao gồm update và build number. `force-download: true` yêu cầu tải lại JDK thay vì chỉ dùng bản đã có trong tool cache. `setup-java` tự kiểm tra checksum khi distribution phát hành checksum chính thức; khả năng xác minh chữ ký package tùy distribution.

Trong workflow bảo mật nghiêm ngặt, pin cả GitHub Action bằng full commit SHA đã được review thay vì chỉ dùng major tag `v6`. Action version và JDK version là hai thành phần độc lập cần quản lý.

### 6.1. Dùng version file chung

Có thể đọc version từ `.java-version`:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: corretto
    java-version-file: .java-version
    force-download: true
~~~

File `.java-version` giúp developer và CI đọc cùng một version. Vendor vẫn phải được xác định riêng bằng `distribution`. Nếu dùng file version cho nhiều công cụ, hãy kiểm tra mọi tool version manager hiểu cùng cú pháp version.

### 6.2. Kiểm tra version đã được cài

Action có output `version` chứa version thực tế được cài. Hãy in output đó vào log và đối chiếu với `java.runtime.version`, vendor và architecture. Đừng chỉ nhìn input `17.0.15+6`; hãy xác minh JDK thực tế sau khi action hoàn tất.

Nếu build chạy trên nhiều OS/architecture, pin riêng từng package phù hợp và giữ matrix rõ ràng.

## 7. Pin JDK trong Docker/container

Một Docker image tag thuận tiện để chọn version, nhưng tag có thể được cập nhật. Digest `sha256` xác định nội dung image bất biến.

Để lấy digest của image đã tải:

~~~bash
docker pull amazoncorretto:17.0.15
docker image inspect --format '{{index .RepoDigests 0}}' amazoncorretto:17.0.15
~~~

Lệnh thứ hai trả về repository digest. Dùng chính chuỗi digest đầy đủ đó trong dòng `FROM` của Dockerfile để build luôn tham chiếu cùng image content. Không tự tạo hoặc đoán digest.

Với multi-stage build, pin cả image builder và runtime. Nếu build phải tái lập giữa nhiều CPU, cố định platform như `linux/amd64` hoặc `linux/arm64` và sử dụng digest của manifest phù hợp. Một multi-architecture manifest digest và một platform-specific image digest có phạm vi khác nhau; ghi rõ platform trong pipeline.

Image digest cố định toàn bộ filesystem image, bao gồm JDK, OS libraries và các file khác. Đây là cách mạnh hơn chỉ pin `java.runtime.version`, nhưng vẫn cần lưu thông tin nguồn image, chữ ký/provenance và quy trình cập nhật image.

## 8. Java identity probe: kiểm tra JDK lúc chạy

Một chương trình nhỏ có thể xác minh runtime chính xác trước khi chạy workload hoặc trong smoke test. Tạo file `JdkIdentityProbe.java`:

~~~java
public final class JdkIdentityProbe {
    public static void main(String[] args) {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Expected runtime version, vendor and architecture"
            );
        }

        String version = System.getProperty("java.runtime.version");
        String vendor = System.getProperty("java.vendor");
        String arch = System.getProperty("os.arch");

        System.out.println("JAVA_VERSION=" + System.getProperty("java.version"));
        System.out.println("JAVA_RUNTIME_VERSION=" + version);
        System.out.println("JAVA_VENDOR=" + vendor);
        System.out.println("JAVA_VM_VERSION=" + System.getProperty("java.vm.version"));
        System.out.println("OS_ARCH=" + arch);

        if (!version.equals(args[0])
                || !vendor.equals(args[1])
                || !arch.equals(args[2])) {
            throw new IllegalStateException(
                "JDK identity does not match the pinned values"
            );
        }

        System.out.println("JDK_PIN=PASS");
    }
}
~~~

Biên dịch và chạy bằng JDK đã pin:

~~~powershell
$JdkHome = "C:\jdks\amazon-corretto-17.0.15.6"

& "$JdkHome\bin\javac.exe" --release 17 -d out JdkIdentityProbe.java
& "$JdkHome\bin\java.exe" -cp out JdkIdentityProbe "17.0.15+6-LTS" "Amazon.com Inc." "amd64"
~~~

Output của lần kiểm thử với Amazon Corretto 17.0.15+6-LTS trên Windows x64:

~~~text
JAVA_VERSION=17.0.15
JAVA_RUNTIME_VERSION=17.0.15+6-LTS
JAVA_VENDOR=Amazon.com Inc.
JAVA_VM_VERSION=17.0.15+6-LTS
OS_ARCH=amd64
JDK_PIN=PASS
~~~

Probe kiểm tra runtime đang thực thi. Nếu build có compile bằng một JDK và chạy test bằng một JDK khác, cần kiểm tra cả compiler toolchain và launcher/toolchain test như ví dụ Gradle ở phần trước.

## 9. Checksum, signature và provenance

Version string giúp nhận diện JDK, nhưng không chứng minh file cài đặt là binary nguyên vẹn từ vendor. Với build cần kiểm soát supply chain:

1. Lấy JDK từ nguồn phát hành chính thức hoặc artifact repository nội bộ.
2. Chọn đúng version, vendor, OS, architecture và package type.
3. Tải checksum từ metadata phát hành đáng tin cậy.
4. Xác minh SHA-256 trước khi giải nén.
5. Xác minh chữ ký số nếu vendor cung cấp signature và public key.
6. Lưu checksum, URL/source, version và thời điểm tải vào artifact record.
7. Không thay archive đã lưu bằng file khác cùng tên.
8. Trong CI, ghi nhận digest của container image và nguồn JDK.

Checksum chỉ chứng minh file tải về khớp với giá trị checksum mà bạn tin cậy. Nếu cả file và checksum cùng đến từ một nguồn đã bị thay đổi, checksum không đủ chứng minh nguồn gốc. Chữ ký số và provenance giúp xác minh nguồn phát hành tốt hơn.

## 10. JDK pinning và reproducible build

Pin JDK là điều kiện cần, nhưng không bảo đảm mọi lần build đều tạo ra artifact giống byte-for-byte. Những yếu tố khác có thể làm output khác nhau:

| Thành phần | Cách kiểm soát |
|---|---|
| Gradle/Maven version | Dùng Wrapper và cố định distribution |
| Plugin version | Khai báo version cụ thể, tránh dynamic version |
| Dependencies | Gradle dependency locking/verification hoặc Maven dependency management |
| Compiler JDK | Pin full runtime version, vendor, installation path và checksum |
| Annotation processors | Pin version và cấu hình |
| OS/architecture | Dùng runner/container image có digest và platform rõ ràng |
| Locale/timezone | Đặt cấu hình nhất quán |
| Environment variables | Khai báo rõ các biến ảnh hưởng build |
| Timestamps/archive metadata | Dùng cơ chế reproducible archive và timestamp chuẩn nếu plugin hỗ trợ |
| Native tools | Pin compiler, linker và package version riêng |

`--release` giúp kiểm soát language/API/bytecode target, nhưng không chọn JDK cụ thể. `sourceCompatibility` và `targetCompatibility` cũng không pin vendor hay patch version. Cần kết hợp toolchain, exact-version guard và compiler options.

## 11. Quy trình cập nhật JDK pin an toàn

Không nên giữ một bản JDK đã pin mãi mãi. Pin chính xác để build có thể tái lập; cập nhật theo lịch để nhận security fixes và bug fixes.

Một quy trình cập nhật có kiểm soát:

1. Chọn bản JDK update đã được vendor phát hành và được tổ chức phê duyệt.
2. Ghi lại full runtime version, vendor, implementation, architecture và package.
3. Xác minh checksum/signature của archive hoặc digest image.
4. Cập nhật `.java-version`, manifest, Gradle/Maven toolchain và CI.
5. Cập nhật expected runtime version trong exact-version guard.
6. Chạy clean build, unit/integration tests và smoke tests trên JDK mới.
7. So sánh artifact, class-file version, test output và performance baseline khi phù hợp.
8. Lưu SBOM/provenance và ghi lại lý do nâng cấp.
9. Merge pin mới sau khi CI xác nhận.
10. Giữ lại thông tin pin cũ để tái lập release cần điều tra.

Không đổi từ version pin sang `latest` để tự động nhận patch. Hãy để một pull request cập nhật pin, checksum và image digest; người review có thể nhìn thấy chính xác JDK nào được thay đổi.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hai máy đều Java 17 nhưng build khác nhau | Khác update/build/vendor | So sánh `java.runtime.version`, vendor và checksum |
| `java --version` đúng nhưng compiler khác | `PATH` trỏ đến `javac` khác `JAVA_HOME` | Dùng đường dẫn `JAVA_HOME/bin/javac`, kiểm tra `Get-Command javac` hoặc `which javac` |
| Gradle chọn sai patch cùng major | Toolchain spec chỉ yêu cầu major/vendor | Giới hạn installation paths và kiểm tra `JavaInstallationMetadata.javaRuntimeVersion` |
| Gradle task không chạy lại sau khi đổi patch | Patch metadata không được coi như một input công khai của mọi task | Thêm full runtime version vào task inputs và chạy exact-version guard |
| Gradle không tìm thấy JDK sau khi tắt auto-detection | Đường dẫn cài đặt sai hoặc không có JDK hợp lệ | Kiểm tra `org.gradle.java.installations.paths`, `bin/java` và `bin/javac` |
| Maven báo không có toolchain phù hợp | Version/vendor token không khớp chính xác | So sánh POM với `toolchains.xml`, bao gồm build suffix |
| Maven chạy đúng nhưng compiler sai | Maven runtime và compiler toolchain là hai JVM khác nhau | Kiểm tra toolchain plugin selection và Maven `--version` |
| CI chọn bản mới hơn dự kiến | Chỉ yêu cầu major version hoặc dùng `latest` | Dùng exact version và xác minh action output/runtime properties |
| Docker build thay đổi dù tag không đổi | Registry đã di chuyển tag sang digest khác | Pin repository digest và platform |
| Checksum không khớp | Download lỗi, sai architecture hoặc file đã thay đổi | Tải lại từ nguồn chính thức, xác minh signature và release metadata |
| JDK cài là JRE | Package thiếu `javac`/Javadoc | Cài đúng JDK package |
| Version giống nhau nhưng binary khác | Khác vendor build hoặc archive bytes | So sánh vendor/build metadata và SHA-256 |
| Build cache trả lại output cũ | Cache key không bao gồm exact JDK pin | Thêm full runtime version vào task inputs/cache key và đổi key khi cập nhật |

### 12.1. Bộ lệnh chẩn đoán nhanh

Kiểm tra Java runtime và compiler trên shell:

~~~bash
java --version
javac --version
java -XshowSettings:properties -version
~~~

PowerShell:

~~~powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
Get-FileHash "$env:JAVA_HOME\release" -Algorithm SHA256
~~~

Gradle:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew verifyPinnedJdk
~~~

Maven:

~~~bash
mvn --version
mvn -t ~/.m2/toolchains.xml -B -ntp validate
~~~

Docker:

~~~bash
docker image inspect --format '{{index .RepoDigests 0}}' amazoncorretto:17.0.15
~~~

So sánh cả runtime version, vendor, path và digest. Một mình `java --version` không đủ để xác minh compiler, toolchain của test hoặc image được dùng ở bước build khác.

## 13. Checklist trước khi chốt JDK pin

- [ ] Đã ghi feature, update và build number đầy đủ.
- [ ] Đã xác định distribution/vendor và VM implementation.
- [ ] Đã chọn đúng OS, architecture, libc variant và package type.
- [ ] Đã xác minh checksum/signature của JDK archive.
- [ ] Đã lưu version pin trong repository hoặc build manifest.
- [ ] Gradle toolchain được giới hạn vào installation đã xác minh.
- [ ] Gradle exact-version guard kiểm tra compiler và launcher metadata.
- [ ] Full JDK version được đưa vào task inputs/cache key khi cần.
- [ ] Maven toolchains version/vendor khớp chính xác với toolchains.xml.
- [ ] Gradle/Maven runtime JVM được pin riêng nếu build engine cũng cần exact JDK.
- [ ] CI cài đúng distribution và exact version, sau đó kiểm tra runtime identity.
- [ ] Container image được pin bằng digest và platform rõ ràng.
- [ ] Gradle/Maven Wrapper và plugin version cũng được cố định.
- [ ] Có lịch cập nhật security patch với checksum/digest mới.
- [ ] Build có thể tái lập từ archive/image đã lưu mà không cần tag floating.

## 14. Ghi nhớ

Pin JDK cho reproducible build cần xác định cả full runtime/build version, vendor, implementation, architecture và binary checksum. Major version như Java 17 chỉ xác định feature release, chưa phân biệt các patch/build khác nhau.

Gradle Toolchains chọn major version và vendor/implementation; để pin exact patch, hãy giới hạn JDK installation path, kiểm tra `JavaInstallationMetadata.javaRuntimeVersion` và đưa full version vào task inputs. Maven Toolchains có thể so khớp full version token chính xác. CI cần chọn đúng distribution/version, còn container nên pin bằng image digest.

Pin không có nghĩa là ngừng cập nhật. Hãy cập nhật JDK theo quy trình review có kiểm soát, thay đổi version/checksum/digest cùng lúc và chạy lại build/test. Như vậy nhóm có thể tái lập một build cũ và vẫn chủ động chuyển sang security patch mới.

Tài liệu tham khảo:

- [JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322)
- [Runtime.Version — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html)
- [Gradle Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle JavaInstallationMetadata API](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JavaInstallationMetadata.html)
- [Gradle JavaToolchainSpec API](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JavaToolchainSpec.html)
- [Maven Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [Maven Toolchains Plugin Usage](https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html)
- [GitHub Actions setup-java](https://github.com/actions/setup-java)
- [Docker Docs — Validate image inputs and require digests](https://docs.docker.com/build/policies/validate-images/)