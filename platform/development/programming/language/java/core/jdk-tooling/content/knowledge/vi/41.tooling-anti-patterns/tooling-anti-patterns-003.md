# Gọi tool không pin version

Gọi tool không pin version là chạy một công cụ phát triển hoặc build mà không xác định rõ phiên bản cần dùng. Ví dụ thường gặp là gọi Maven hoặc Gradle trực tiếp từ PATH của máy cá nhân, dùng latest trong lệnh tải tool, dùng Maven plugin không khai báo version, hoặc gọi GitHub Action bằng tag có thể thay đổi.

Cấu hình này khiến cùng một commit có thể tạo kết quả khác nhau ở hai thời điểm. Máy developer có thể dùng Maven/Gradle/JDK mới hơn CI; runner mới có thể nhận action hoặc container image khác; một plugin vừa phát hành có thể thay đổi hành vi build dù source code không đổi. Pin version giúp biết chính xác công cụ nào đã tham gia tạo artifact, tái hiện lỗi và đánh giá bản cập nhật trước khi đưa vào release.

## 1. Phân biệt các loại version cần pin

Một dự án Java có nhiều công cụ cùng tham gia build. Chỉ pin JDK là chưa đủ nếu Maven, Gradle, plugin, action hoặc image vẫn thay đổi tự động.

| Thành phần | Ví dụ | Nơi pin thường dùng |
|---|---|---|
| JDK/JRE | Temurin 21.0.7+6 | JDK toolchain, image digest hoặc provisioning script |
| Build tool | Maven 3.9.9, Gradle 9.9.0 | Maven Wrapper, Gradle Wrapper |
| Maven plugin | Compiler Plugin 3.13.0 | POM pluginManagement |
| Gradle plugin | Spring Boot Plugin 3.5.0 | plugins block hoặc version catalog |
| Dependency | org.slf4j:slf4j-api:2.0.17 | Version cố định, BOM, lockfile |
| CI action | actions/checkout | Full commit SHA |
| Container image | Eclipse Temurin JDK image | Tag cụ thể kèm digest |
| CLI phụ trợ | formatter, scanner, code generator | Version trong lệnh hoặc tool manifest |

Có ba mức kiểm soát cần phân biệt:

1. **Release version:** xác định bản phát hành, ví dụ Gradle 9.9.0.
2. **Content identity:** xác định chính xác nội dung được tải, ví dụ SHA-256 của ZIP, digest của container image hoặc commit SHA của GitHub Action.
3. **Dependency graph:** xác định chính xác các thư viện và plugin mà build đã resolve, kể cả dependency bắc cầu.

Pin version giúp tránh tự động trôi sang bản mới. Checksum/digest giúp phát hiện nội dung khác với bản đã duyệt. Lockfile và dependency verification giúp kiểm soát thư viện được kéo vào build. Các cơ chế này bổ sung cho nhau.

## 2. Vì sao gọi tool không pin version là anti-pattern?

### 2.1. Build thay đổi dù source code không đổi

Giả sử workflow chạy:

~~~sh
mvn clean verify
~~~

Hôm nay máy developer có Maven 3.9.x và JDK 21; tuần sau một runner mới có Maven khác hoặc JDK mặc định mới. Nếu POM cũng không pin plugin, Maven có thể resolve một plugin version khác khi metadata repository thay đổi.

Kết quả có thể là:

- Build đang xanh chuyển sang đỏ sau một lần phát hành plugin.
- Warning mới trở thành error hoặc compiler thay đổi cách xử lý.
- Artifact khác nhau giữa máy local, CI và môi trường release.
- Khó tái hiện lỗi vì log chỉ ghi lệnh build, không ghi đầy đủ phiên bản tool.
- Một bản tool bị xâm nhập hoặc phát hành lỗi có thể chạy ngay trong pipeline.

### 2.2. Tag hoặc alias có thể thay đổi đích

Các ví dụ dưới đây đều để phiên bản thay đổi theo thời gian:

~~~sh
docker run eclipse-temurin:latest java -version
npx --yes prettier@latest --check .
curl -fsSL https://example.com/install-latest.sh | sh
~~~

Một tag Docker có thể được nhà phát hành cập nhật sang image mới. latest là alias, không phải định danh bất biến. Script tải từ URL latest có thể đổi nội dung mà URL không đổi. CLI dùng @latest sẽ nhận release mới nhất tại thời điểm chạy.

Nếu cần dùng tool mới, hãy cập nhật phiên bản trong một thay đổi có review, chạy kiểm thử và lưu lại bằng chứng của bản đã chọn.

### 2.3. Rủi ro chuỗi cung ứng phần mềm

Build tool và plugin thường chạy code trong môi trường có quyền đọc source, token hoặc secret của CI. Một plugin hoặc action bị thay đổi có thể thực thi code trong pipeline.

Pin version giúp giới hạn thay đổi ngoài ý muốn. Pin commit SHA hoặc digest còn giúp định danh nội dung cụ thể. Tuy nhiên, pin một bản đã lỗi thời cũng giữ nguyên lỗ hổng đã biết; vì vậy phải có quy trình cập nhật bảo mật định kỳ.

## 3. Pin JDK và compiler toolchain

Không nên dựa hoàn toàn vào JDK mặc định trong PATH. Cấu hình project hoặc CI phải xác định Java version, vendor và khi cần thì cả patch/build.

### 3.1. Phân biệt Java release với JDK patch version

Các cấu hình sau không có cùng mức bảo đảm:

| Cấu hình | Ý nghĩa |
|---|---|
| java-version: '21' | Chọn dòng Java 21; patch/build có thể thay đổi theo resolver |
| languageVersion = JavaLanguageVersion.of(21) | Gradle chọn một toolchain Java 21 phù hợp |
| java-version: '21.0.7+6' | Yêu cầu một bản JDK cụ thể nếu distribution và resolver hỗ trợ version đó |
| Image JDK có digest | Khóa nội dung image, bao gồm JDK và các thành phần đã đóng gói |

Java feature release 21 xác định mức ngôn ngữ/API mục tiêu. Nó không tự xác định patch build của JDK, vendor hoặc nội dung của toàn bộ môi trường build.

### 3.2. Gradle Java Toolchains

Dùng toolchain để build không phụ thuộc vào JDK ngẫu nhiên được chọn qua PATH:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Gradle dùng toolchain phù hợp cho compile, test và Javadoc tasks. Có thể xem các JDK mà Gradle phát hiện:

~~~sh
./gradlew -q javaToolchains
./gradlew --version
~~~

**Giới hạn cần nhớ:** languageVersion chọn major version, ví dụ Java 21; vendor lọc nhà cung cấp. Cấu hình này không khóa riêng patch 21.0.7 hay build number. Nếu release cần cùng patch JDK trên mọi runner, hãy provision đúng JDK bằng image có digest hoặc installation được quản lý, chỉ để toolchain nhìn thấy bản đã chọn, rồi kiểm tra java.version, java.vendor và java.home trong CI.

Ví dụ kiểm tra runtime thực tế:

~~~sh
java -version
javac -version
./gradlew --version
~~~

### 3.3. Maven Toolchains

Maven có thể chọn JDK theo thông tin toolchain trong ~/.m2/toolchains.xml. Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>21.0.7</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/temurin-21.0.7</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Project hoặc Maven Toolchains Plugin có thể yêu cầu toolchain tương ứng. Maven so khớp các giá trị version và vendor như chuỗi metadata; nó không tự kiểm tra xem thư mục jdkHome có thật sự chứa đúng JDK được khai báo hay không. Vì vậy, chỉ dùng đường dẫn JDK do hệ thống provisioning đáng tin cậy cung cấp và xác minh lại bằng java -version/javac -version.

Maven Toolchains cho phép dùng version range, nhưng nếu mục tiêu là pin patch cụ thể, hãy dùng version string cụ thể và kiểm tra nội dung installation.

### 3.4. --release không pin JDK

Ví dụ Maven:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Hoặc javac:

~~~sh
javac --release 17 Example.java
~~~

--release 17 giới hạn ngôn ngữ, bytecode và Java platform API mà source được phép dùng. Nó không cố định JDK compiler patch/vendor đang thực thi. Vẫn cần JDK toolchain riêng để kiểm soát compiler.

## 4. Dùng Maven Wrapper để pin Maven

Không nên yêu cầu mọi developer tự cài Maven rồi chạy mvn. Máy mỗi người có thể có version khác nhau. Maven Wrapper (mvnw và mvnw.cmd) tải và chạy đúng Maven distribution được khai báo trong repository.

Tạo hoặc cập nhật Wrapper bằng Maven Wrapper Plugin:

~~~sh
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

Sau đó commit các file Wrapper và yêu cầu mọi người chạy:

~~~sh
./mvnw --version
./mvnw clean verify
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean verify
~~~

File .mvn/wrapper/maven-wrapper.properties có thể khai báo:

~~~properties
distributionUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=<SHA-256 của Maven 3.9.9 lấy từ nguồn phát hành chính thức>
wrapperSha256Sum=<SHA-256 của maven-wrapper.jar đã xác minh>
~~~

Hai giá trị checksum ở trên là chỗ cần điền giá trị thực, không phải chuỗi literal. Lấy SHA-256 từ trang phát hành chính thức hoặc nguồn độc lập đáng tin cậy. Không tính checksum từ một file vừa tải về rồi dùng chính giá trị đó làm bằng chứng tin cậy.

distributionUrl cố định Maven version; distributionSha256Sum xác minh ZIP Maven; wrapperSha256Sum xác minh Wrapper JAR. Cần dùng Wrapper distribution hỗ trợ các thuộc tính checksum này.

## 5. Pin Maven plugin trong POM

Maven plugin là một phần của build toolchain. Nếu không khai báo version, Maven có thể phải resolve version theo metadata repository. Apache Maven khuyến nghị luôn chỉ định version cho từng plugin để build có thể tái lập.

Dùng pluginManagement để quản lý version tập trung:

~~~xml
<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
      </plugin>
    </plugins>
  </pluginManagement>
</build>
~~~

Các version trong ví dụ là version cố định minh họa. Khi áp dụng cho project, kiểm tra compatibility với Maven/JDK đang dùng và cập nhật có chủ đích.

Nếu gọi plugin trực tiếp từ command line, dùng tọa độ đầy đủ kèm version:

~~~sh
./mvnw org.codehaus.mojo:versions-maven-plugin:2.18.0:display-dependency-updates
~~~

Lệnh ngắn như mvn versions:display-dependency-updates phụ thuộc vào cơ chế plugin prefix resolution và có thể cần tra metadata để tìm plugin. Tọa độ đầy đủ kèm version giúp chỉ rõ plugin cần chạy.

## 6. Pin Gradle bằng Gradle Wrapper

Không gọi gradle build từ bản cài global. Dùng ./gradlew hoặc gradlew.bat để project tự chọn đúng Gradle distribution.

Tạo hoặc cập nhật Wrapper:

~~~sh
gradle wrapper --gradle-version 9.9.0 --distribution-type bin
~~~

Sau đó chạy:

~~~sh
./gradlew --version
./gradlew clean build
~~~

File gradle/wrapper/gradle-wrapper.properties nên có URL cụ thể:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
distributionSha256Sum=<SHA-256 chính thức của gradle-9.9.0-bin.zip>
~~~

Thay placeholder bằng checksum lấy từ trang release checksums chính thức của Gradle. Wrapper sẽ từ chối distribution nếu SHA-256 không khớp. Dùng HTTPS và URL trực tiếp của distribution; tránh URL chuyển hướng hoặc alias trôi nổi.

Commit toàn bộ Wrapper files vào version control:

- gradlew
- gradlew.bat
- gradle/wrapper/gradle-wrapper.jar
- gradle/wrapper/gradle-wrapper.properties

Wrapper JAR cũng cần được xác minh theo hướng dẫn bảo mật của Gradle. Việc pin URL distribution không tự động xác minh Wrapper JAR đã được commit.

## 7. Pin Gradle plugin và dependency

### 7.1. Khai báo version cụ thể trong plugins block

Ví dụ build.gradle.kts:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
}
~~~

Không dùng version động như latest.release, 1.+ hoặc range rộng cho plugin trong build release.

Với project lớn, có thể quản lý version tập trung trong gradle/libs.versions.toml:

~~~toml
[versions]
spring-boot = "3.5.0"
junit = "5.12.2"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
~~~

Sau đó tham chiếu version catalog trong build script. File version catalog phải được commit cùng source.

### 7.2. Tránh dynamic dependency versions

Ví dụ không nên dùng cho release:

~~~kotlin
dependencies {
    implementation("org.springframework:spring-web:5.+")
    testImplementation("org.junit.jupiter:junit-jupiter:5.+")
}
~~~

Các version động có thể resolve thành bản khác ở lần build tiếp theo. Khai báo version cố định:

~~~kotlin
dependencies {
    implementation("org.springframework:spring-web:6.2.8")
    testImplementation("org.junit.jupiter:junit-jupiter:5.12.2")
}
~~~

Version ví dụ phải được kiểm tra tương thích với project trước khi áp dụng.

### 7.3. Bật dependency locking

Version cố định trong file build chưa khóa hoàn toàn dependency bắc cầu. Gradle dependency locking ghi lại version đã resolve để lần sau dùng cùng dependency graph.

Trong build.gradle.kts:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Tạo hoặc cập nhật lock state sau khi resolve các configuration cần dùng:

~~~sh
./gradlew dependencies --write-locks
~~~

Commit các file gradle.lockfile. Khi chủ động nâng dependency, cập nhật lock state cùng thay đổi version và review diff.

Không dùng dependency locking như cách đóng băng dependency SNAPSHOT hoặc changing module; nội dung của chúng có thể thay đổi dù version string không đổi.

### 7.4. Xác minh checksum và chữ ký dependency

Gradle hỗ trợ dependency verification qua gradle/verification-metadata.xml. Có thể khởi tạo metadata cho checksum và chữ ký:

~~~sh
./gradlew --write-verification-metadata sha256,pgp
~~~

Review file được tạo, đối chiếu checksum/chữ ký với nguồn tin cậy rồi commit. Không mặc định tin mọi metadata vừa được sinh ra: lệnh tạo metadata chỉ ghi nhận artifact đang resolve, còn nhóm phát triển vẫn phải xác minh nguồn và nội dung của artifact quan trọng.

Checksum xác nhận nội dung file không đổi so với giá trị đã duyệt. Chữ ký hỗ trợ xác minh danh tính người phát hành. Hai cơ chế có vai trò khác nhau và bổ sung cho nhau.

## 8. Pin GitHub Actions bằng full commit SHA

Trong workflow, tag như @v4 thuận tiện nhưng tag có thể được chuyển sang commit khác. GitHub khuyến nghị pin action bằng full-length commit SHA để dùng một revision bất biến.

Ví dụ cú pháp:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@<FULL_40_CHARACTER_COMMIT_SHA>

      - uses: actions/setup-java@<FULL_40_CHARACTER_COMMIT_SHA>
        with:
          distribution: temurin
          java-version: '21.0.7+6'

      - name: Verify toolchain
        run: |
          java -version
          javac -version

      - name: Build
        run: ./mvnw --batch-mode verify
~~~

<FULL_40_CHARACTER_COMMIT_SHA> là placeholder cần thay bằng commit SHA đầy đủ lấy từ repository chính thức của action. Kiểm tra SHA thuộc repository gốc, không lấy từ fork không đáng tin cậy. Có thể ghi comment chứa version/tag dễ đọc:

~~~yaml
# actions/checkout v4.x.y, pinned to reviewed commit
- uses: actions/checkout@<FULL_40_CHARACTER_COMMIT_SHA>
~~~

Nếu tổ chức chưa pin SHA, tối thiểu phải dùng action từ nhà phát hành tin cậy và review source trước khi cấp quyền truy cập secret. Full SHA là cách rõ ràng hơn để giữ workflow ổn định và audit được thay đổi.

## 9. Pin container image bằng digest

Tag Docker là nhãn có thể thay đổi. Ví dụ eclipse-temurin:21-jdk có thể được cập nhật sang patch JDK mới trong tương lai. Nếu cần build lặp lại cùng một image, pin digest:

~~~dockerfile
FROM eclipse-temurin:21-jdk@sha256:<64_HEX_IMAGE_DIGEST>

WORKDIR /app
COPY . .
RUN ./mvnw --batch-mode verify
~~~

<64_HEX_IMAGE_DIGEST> là placeholder. Lấy digest từ registry đáng tin cậy và xác nhận nó tương ứng với image/tag dự kiến.

Digest cố định nội dung image. Với image đa kiến trúc, digest có thể định danh manifest index chứa nhiều platform manifests; runner vẫn chọn image con theo architecture. Nếu cần kết quả chính xác trên từng kiến trúc, ghi rõ --platform hoặc cấu hình platform trong CI và lưu lại digest đã dùng.

Pin digest giúp build ổn định, nhưng không tự nhận security update. Hãy định kỳ cập nhật digest qua pull request có kiểm thử và review lỗ hổng.

## 10. Pin các CLI và script cài tool

Các tool phụ trợ cũng có thể trôi version:

| Cách gọi thiếu pin | Cách gọi có pin |
|---|---|
| npx prettier@latest --check . | npx --yes prettier@3.5.3 --check . |
| docker run maven:latest mvn -version | Image Maven có tag cụ thể và digest |
| Tải script install-latest.sh | Tải release cụ thể, xác minh checksum/chữ ký |
| mvn versions:set không pin plugin | Gọi plugin bằng groupId, artifactId và version |
| gradle build từ PATH | ./gradlew build |
| mvn verify từ PATH | ./mvnw verify |

Nếu dùng npm/npx trong một bước Java build, hãy commit lockfile npm và dùng phiên bản Node/npm đã được chọn. Với Python tool, dùng requirements/lock file và phiên bản Python cụ thể. Nguyên tắc giống nhau: mọi tool có thể ảnh hưởng đến artifact phải được khai báo và kiểm soát version.

Tránh lệnh tải rồi thực thi script từ Internet mà không kiểm tra nội dung. Nếu tổ chức cần cài tool tự động, dùng repository nội bộ đã xác minh hoặc artifact release có checksum/chữ ký.

## 11. Pin version có tạo ra reproducible build hoàn toàn không?

Không. Pin version là điều kiện quan trọng, nhưng một build vẫn có thể khác nếu các đầu vào khác thay đổi.

Các yếu tố cần kiểm soát thêm:

- Dependency trực tiếp và dependency bắc cầu.
- Plugin, extension, annotation processor và code generator.
- JDK vendor, patch, architecture và compiler.
- Maven/Gradle Wrapper distribution và Wrapper JAR.
- Base image, package manager và OS image.
- Locale, timezone, environment variables và working directory.
- Thời gian build được ghi vào JAR, archive hoặc generated file.
- Repository mirror và nội dung artifact tải về.

Maven có hướng dẫn cấu hình reproducible builds, trong đó project.build.outputTimestamp giúp chuẩn hóa timestamp trong artifact khi plugin hỗ trợ. Điều này cho thấy chỉ pin tool version chưa đủ để tạo binary giống nhau từng byte.

Nên ghi nhận build provenance: commit source, JDK version/vendor, Maven/Gradle version, plugin/dependency versions, container digest và CI run. Khi có sự cố, các thông tin này giúp truy ngược chính xác toolchain đã tạo artifact.

## 12. Quy trình nâng version có kiểm soát

Pin version không có nghĩa giữ nguyên mãi. Tool cũ có thể hết hỗ trợ hoặc có lỗ hổng. Hãy tạo một thay đổi nâng cấp riêng để biết build thay đổi vì lý do gì.

1. Chọn tool cần nâng và xác định version đích từ release notes chính thức.
2. Kiểm tra compatibility giữa JDK, Maven/Gradle, plugin và dependency.
3. Cập nhật Wrapper, toolchain, plugin hoặc image digest ở đúng nơi quản lý.
4. Cập nhật checksum, lockfile và verification metadata tương ứng.
5. Chạy unit test, integration test, packaging và security scan.
6. So sánh artifact/log trước và sau nâng cấp nếu build có yêu cầu reproducibility.
7. Review diff của lockfile, checksum và workflow action SHA.
8. Ghi rõ lý do nâng cấp, version cũ/mới và kết quả kiểm thử.
9. Merge thay đổi sau khi các kiểm tra CI đạt yêu cầu.
10. Duy trì lịch kiểm tra release và security advisory để không bỏ lỡ bản vá quan trọng.

Có thể dùng Dependabot hoặc Renovate để tạo pull request cập nhật. Bot giúp phát hiện bản mới; nhóm phát triển vẫn phải review compatibility, changelog, checksum/digest và kết quả test trước khi chấp nhận.

## 13. Kiểm tra tool version trong pipeline

In version ngay đầu build để log có đủ dữ liệu chẩn đoán:

~~~sh
java -version
javac -version
./mvnw --version
./gradlew --version
~~~

Nếu workflow chỉ dùng Maven, không cần chạy lệnh Gradle và ngược lại. Trên Windows:

~~~powershell
java -version
javac -version
.\mvnw.cmd --version
.\gradlew.bat --version
~~~

Có thể kiểm tra các vị trí executable đang được chọn:

~~~sh
command -v java
command -v javac
command -v mvn
command -v gradle
~~~

PowerShell:

~~~powershell
Get-Command -All java
Get-Command -All javac
Get-Command -All mvn
Get-Command -All gradle
~~~

Nếu build chạy trong Docker, ghi lại image digest. Nếu chạy trên GitHub Actions, giữ action SHA trong workflow. Đừng chỉ ghi Java 21 nếu release cần biết patch, vendor hoặc architecture cụ thể.

## 14. Ví dụ Java kiểm tra runtime thực tế

Tạo ToolchainProbe.java để in version, vendor, VM và kiến trúc runtime:

~~~java
public class ToolchainProbe {
    public static void main(String[] args) {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.vm.name=" + System.getProperty("java.vm.name"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("java.home=" + System.getProperty("java.home"));
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~sh
javac --release 17 ToolchainProbe.java
java ToolchainProbe
~~~

Chương trình này xác nhận runtime đang chạy. Nó không tự chứng minh Maven, Gradle hoặc CI action đã được pin; hãy đối chiếu output với cấu hình Wrapper/toolchain/image và log pipeline.

## 15. Troubleshooting khi tool version không được pin

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Build local và CI cho kết quả khác | JDK hoặc build tool trên PATH khác nhau | Dùng Wrapper, khai báo toolchain và in version |
| Build hôm qua chạy, hôm nay lỗi | Plugin, action, image tag hoặc dependency động đã đổi | Pin version/digest/SHA và review thay đổi |
| Gradle chọn JDK 21 khác patch mong muốn | languageVersion chỉ chọn major version | Provision patch JDK cố định và xác minh runtime |
| Maven dùng compiler khác JDK mặc định | Maven toolchain hoặc JAVA_HOME khác terminal | Kiểm tra mvnw --version, toolchains.xml và JDK path |
| Plugin Maven thay đổi giữa hai lần build | Plugin không khai báo version | Khai báo version trong pluginManagement |
| Gradle Wrapper tải file khác dự kiến | URL trôi nổi hoặc thiếu checksum | Pin distribution URL và distributionSha256Sum |
| Wrapper chạy nhưng checksum mismatch | ZIP/JAR khác nội dung đã duyệt hoặc checksum sai | Dừng build, xác minh nguồn và checksum độc lập |
| GitHub Action thay đổi dù tag giữ nguyên | Tag có thể được di chuyển | Pin full commit SHA từ repository chính thức |
| Docker image thay đổi sau rebuild | Tag image là mutable | Pin digest và cập nhật digest qua PR |
| Lockfile báo version conflict | Khai báo dependency đã đổi nhưng lock state chưa cập nhật | Review dependency change rồi chạy --write-locks |
| Dependency verification thất bại | Artifact mới chưa có checksum/chữ ký được duyệt | Xác minh artifact rồi cập nhật verification metadata |
| Artifact khác byte dù tool đã pin | Timestamp, environment hoặc đầu vào khác | Kiểm tra reproducible build settings và provenance |

## 16. Checklist chống gọi tool không pin version

- [ ] Đã chọn JDK vendor, feature release và patch/build cần thiết.
- [ ] Đã dùng Gradle/Maven toolchain thay vì phụ thuộc hoàn toàn vào PATH.
- [ ] Đã hiểu --release chỉ khóa target API/bytecode, không khóa compiler JDK.
- [ ] Đã commit Maven Wrapper hoặc Gradle Wrapper.
- [ ] Đã pin chính xác Maven/Gradle distribution version.
- [ ] Đã xác minh checksum Wrapper JAR và distribution khi hỗ trợ.
- [ ] Đã khai báo version cho tất cả Maven build plugin.
- [ ] Đã pin Gradle plugin và quản lý version tập trung.
- [ ] Đã tránh latest, 1.+, version range và SNAPSHOT trong release build.
- [ ] Đã bật dependency locking và commit lockfile nếu dùng Gradle.
- [ ] Đã xác minh checksum/chữ ký dependency quan trọng.
- [ ] Đã pin GitHub Actions bằng full commit SHA.
- [ ] Đã pin container image bằng digest.
- [ ] Đã pin version cho CLI/script cài tool phụ trợ.
- [ ] Đã ghi tool versions vào log CI.
- [ ] Đã có quy trình review và kiểm thử khi nâng version.
- [ ] Đã lưu provenance đủ để tái hiện artifact.

Gọi tool không pin version làm môi trường build phụ thuộc vào trạng thái bên ngoài repository tại thời điểm chạy. Dùng Wrapper cho Maven/Gradle, khai báo JDK toolchain, pin plugin/action/image, khóa dependency graph và xác minh checksum hoặc chữ ký. Cập nhật version qua thay đổi có review và kiểm thử để build vừa ổn định vừa nhận được bản vá bảo mật.

## Tài liệu tham khảo

- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/)
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [GitHub — Secure Use Reference for GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use)
- [Docker — Building Best Practices: Pin Base Image Versions](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions)