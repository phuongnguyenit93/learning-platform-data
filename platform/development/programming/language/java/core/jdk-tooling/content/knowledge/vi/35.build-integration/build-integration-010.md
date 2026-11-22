# Đồng bộ JDK giữa máy phát triển và CI

## 1. Mục tiêu của việc đồng bộ JDK

Một dự án Java thường được build trên nhiều môi trường: máy của lập trình viên, IDE, máy CI, container và máy chạy production. Nếu các môi trường dùng JDK hoặc build tool khác nhau, cùng một commit có thể tạo ra kết quả khác nhau hoặc chỉ build thành công ở một số máy.

**Đồng bộ JDK build** là xác định rõ JDK nào chạy build tool, JDK nào biên dịch source, JDK nào chạy test và JDK nào chạy ứng dụng. Các lựa chọn này phải được khai báo, kiểm tra và áp dụng nhất quán.

Một cấu hình build đáng tin cậy cần kiểm soát ít nhất:

- JDK chạy Maven hoặc Gradle.
- JDK toolchain được dùng cho compile, test và javadoc.
- Java language level và API platform mục tiêu.
- Phiên bản Maven hoặc Gradle được dùng qua Wrapper.
- Phiên bản plugin, annotation processor và công cụ build liên quan.
- JDK runtime trong container hoặc môi trường triển khai.

Không nên chỉ đặt JAVA_HOME rồi giả định mọi công cụ đều dùng cùng JDK. IDE, Maven Toolchains và Gradle Java Toolchains có thể chọn JDK khác với JDK đang chạy build process.

## 2. Phân biệt các lớp Java version

| Lớp | Câu hỏi | Cách kiểm soát |
|---|---|---|
| Build JVM | Maven hoặc Gradle chạy trên JDK nào? | JAVA_HOME, PATH, IDE build JVM, Enforcer hoặc Gradle daemon JVM criteria. |
| Compiler toolchain | javac nào biên dịch source? | Maven Toolchains hoặc Gradle Java Toolchains. |
| Compile release | Source được phép dùng cú pháp và API Java đến phiên bản nào? | javac --release, Maven compiler release, Gradle options.release. |
| Test runtime | JVM nào chạy unit/integration test? | Toolchain-aware Surefire/Failsafe hoặc Gradle Test javaLauncher. |
| Application runtime | JVM nào chạy artifact sau khi deploy? | Container image, VM image hoặc runtime package được chọn. |
| Build tool | Phiên bản Maven/Gradle nào chạy lifecycle? | Maven Wrapper hoặc Gradle Wrapper. |

Các lớp này liên quan nhưng không thay thế nhau.

Ví dụ, Maven có thể chạy trên JDK 24, dùng Maven Toolchains để gọi javac 17 và tạo bytecode Java 17. Maven Wrapper có thể cố định Maven 3.9.12, nhưng không tự cài hoặc chọn JDK 17. Compiler release 17 giới hạn API và bytecode, nhưng không quyết định compiler executable nằm ở đâu.

## 3. Chọn baseline Java cho dự án

Trước khi cấu hình, nhóm cần thống nhất:

1. Java major version tối thiểu mà source được phép sử dụng.
2. JDK dùng để compile và chạy test.
3. JDK runtime tối thiểu của artifact.
4. Vendor và patch version có cần cố định hay chỉ cần cùng major version.
5. Maven/Gradle version và các plugin cần thiết.
6. Chính sách nâng cấp JDK và thời gian duy trì các phiên bản cũ.

Ví dụ trong bài này dùng Java 17 làm baseline để minh họa. Dự án có thể chọn 21 hoặc một phiên bản khác tùy yêu cầu sản phẩm và dependency.

Java major version và patch version giải quyết hai vấn đề khác nhau. Toolchain languageVersion=17 thường chỉ yêu cầu major version 17. Nếu cần đúng vendor hoặc patch release, phải kiểm soát thêm vendor, bản cài JDK hoặc image CI.

Không nâng JDK production chỉ vì máy phát triển đã cài JDK mới. Hãy kiểm tra dependency, framework, plugin, bytecode target và runtime support trước khi thay đổi baseline.

## 4. Kiểm tra JDK hiện đang được sử dụng

Trên Windows PowerShell:

~~~powershell
java -version
javac -version
mvn -version
gradle --version
where.exe java
where.exe javac
Write-Output $env:JAVA_HOME
~~~

Trên Linux hoặc macOS:

~~~bash
java -version
javac -version
mvn -version
./gradlew --version
which java
which javac
echo "$JAVA_HOME"
~~~

Maven -version cho biết Maven version và Java runtime đang chạy Maven. Gradle --version cho biết Gradle version, launcher JVM và daemon JVM.

java -version chỉ cho biết lệnh java đầu tiên được tìm thấy trong PATH. javac -version cho biết compiler executable đang được shell tìm thấy. Hai lệnh có thể trỏ tới JDK khác nhau nếu PATH được cấu hình sai.

Trên Windows, có thể tạm đổi JDK cho terminal hiện tại:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
mvn -version
~~~

Trên Linux:

~~~bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
java -version
javac -version
mvn -version
~~~

Thay đường dẫn ví dụ bằng nơi JDK thực tế được cài. Mở terminal mới hoặc khởi động lại IDE nếu cần áp dụng thay đổi môi trường.

## 5. Cố định Maven bằng Maven Wrapper

Maven Wrapper cung cấp script mvnw và mvnw.cmd để mọi người dùng cùng một Maven distribution. Người dùng không cần tự cài đúng Maven version trước khi build; wrapper tải distribution được chỉ định trong project nếu máy chưa có.

Tạo hoặc cập nhật wrapper:

~~~bash
mvn org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.12 -Dtype=only-script
~~~

Các file được đưa vào source control thường gồm:

~~~text
mvnw
mvnw.cmd
.mvn/
  wrapper/
    maven-wrapper.properties
~~~

Sau khi tạo wrapper, build bằng:

~~~bash
./mvnw clean verify
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd clean verify
~~~

File maven-wrapper.properties chứa distributionUrl để chỉ định Maven distribution. Ví dụ:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.12/apache-maven-3.9.12-bin.zip
~~~

Wrapper pin Maven version, không pin JDK runtime. Vẫn cần cấu hình JAVA_HOME, toolchain hoặc CI image để thống nhất JDK.

Nên cấu hình distributionSha256Sum bằng SHA-256 chính thức của Maven distribution đang dùng. Nếu dùng wrapper binary, có thể cấu hình wrapperSha256Sum cho wrapper JAR. Không tự tạo checksum; lấy giá trị từ nguồn phát hành đáng tin cậy và xác minh trước khi commit.

## 6. Dùng Maven Compiler Plugin và --release

Trong Maven, thuộc tính maven.compiler.release xác định Java release mà compiler phải tuân theo.

Ví dụ:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

javac --release 17 kiểm soát source language, target class file và API platform Java 17. Điều này giúp tránh biên dịch thành công trên JDK mới nhưng vô tình gọi API chỉ có ở JDK mới hơn.

source và target riêng lẻ không cung cấp cùng mức bảo vệ API như --release. Với JDK 9 trở lên, ưu tiên release khi cần cross-compile cho một Java platform cụ thể.

--release không chọn JDK executable. Compiler vẫn có thể là javac từ JDK 24, nhưng được yêu cầu tạo output tương thích Java 17. Muốn chọn chính xác JDK compiler, hãy dùng Maven Toolchains hoặc Gradle Java Toolchains.

## 7. Cấu hình Maven Toolchains trên từng máy

Maven Toolchains cho phép các plugin tương thích sử dụng một JDK khác với JDK đang chạy Maven.

Thông thường, mô tả toolchain nằm tại:

- Linux/macOS: ~/.m2/toolchains.xml
- Windows: %USERPROFILE%\.m2\toolchains.xml

Ví dụ toolchains.xml cho JDK 17:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
    </provides>
    <configuration>
      <jdkHome>C:/Java/jdk-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Thay C:/Java/jdk-17 bằng đường dẫn JDK 17 trên máy đó. Mỗi developer và CI có thể có đường dẫn cài đặt khác nhau, vì vậy không commit file toolchains.xml chứa đường dẫn máy cá nhân vào repository.

Nếu cần dùng một file toolchain khác với vị trí mặc định, Maven hỗ trợ option -t:

~~~bash
mvn -t ./ci/toolchains.xml clean verify
~~~

Trong CI, có thể tạo toolchains.xml từ JAVA_HOME sau khi cài JDK. Cách này giữ cùng một cấu hình version trong project và lấy đường dẫn thực tế từ môi trường CI.

## 8. Yêu cầu toolchain trong pom.xml

Thêm Maven Toolchains Plugin vào build:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-toolchains-plugin</artifactId>
      <version>3.3.0</version>
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
            <version>17</version>
          </jdk>
        </toolchains>
      </configuration>
    </plugin>

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>17</release>
        <fork>true</fork>
        <encoding>UTF-8</encoding>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Maven Toolchains Plugin đọc danh sách toolchain trên máy và tìm một JDK phù hợp với yêu cầu version 17 trong POM.

Compiler plugin nhận toolchain đã chọn. fork=true yêu cầu compiler plugin gọi javac executable của toolchain. Nếu bỏ fork, compiler plugin có thể dùng Java compiler API của JVM đang chạy Maven, vì vậy cần kiểm tra hành vi theo phiên bản plugin và cấu hình dự án.

Khi không tìm thấy toolchain phù hợp, build phải dừng với thông báo không có JDK matching. Đây là tín hiệu hữu ích: máy chưa cài JDK cần thiết hoặc toolchains.xml mô tả sai version/path.

Toolchain descriptor có thể chứa các thuộc tính provides khác như vendor. Các thuộc tính này là thông tin để plugin đối chiếu. Đường dẫn jdkHome vẫn phải trỏ tới JDK đúng vendor/version; hãy xác minh bằng java -version và javac -version tại chính đường dẫn đó.

## 9. Phân biệt Maven Enforcer với Maven Toolchains

Maven Enforcer Plugin có thể kiểm tra phiên bản Maven và Java runtime đang chạy Maven.

Ví dụ:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-enforcer-plugin</artifactId>
  <version>3.7.0</version>
  <executions>
    <execution>
      <id>enforce-build-runtime</id>
      <goals>
        <goal>enforce</goal>
      </goals>
      <configuration>
        <rules>
          <requireMavenVersion>
            <version>[3.9.12,4.0)</version>
          </requireMavenVersion>
          <requireJavaVersion>
            <version>[17,18)</version>
          </requireJavaVersion>
        </rules>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

Trong ví dụ, Maven phải chạy trên Maven 3.9.12 trở lên nhưng thấp hơn Maven 4, và JVM chạy Maven phải là Java 17.

**RequireJavaVersion kiểm tra Java runtime của Maven**, không kiểm tra compiler toolchain đã chọn. Nếu Maven chạy trên JDK 24 nhưng compiler toolchain là JDK 17, rule [17,18) vẫn thất bại. Khi đó hãy đặt runtime policy đúng với JDK mà Maven được phép chạy, hoặc không dùng rule này nếu build chủ động cho phép nhiều Maven runtime.

Maven Toolchains kiểm soát JDK mà plugin tương thích sử dụng. Enforcer kiểm tra điều kiện của build process. Hai công cụ bổ sung cho nhau và cần cấu hình theo mục tiêu riêng.

Có thể thêm RequireMavenVersion, RequireJavaVersion, RequireJavaVendor hoặc RequirePluginVersions theo chính sách dự án. Pin version của plugin giúp build không âm thầm thay đổi hành vi khi plugin mặc định được nâng cấp.

## 10. Đồng bộ Maven trong multi-module project

Với Maven multi-module, đặt các property và plugin version ở parent POM để module con kế thừa.

Các giá trị nên tập trung ở parent:

- maven.compiler.release.
- project.build.sourceEncoding.
- maven-toolchains-plugin version và yêu cầu JDK.
- maven-compiler-plugin version và configuration.
- maven-surefire-plugin và maven-failsafe-plugin version.
- Enforcer rules.

Đặt plugin version và configuration dùng chung trong pluginManagement. Đặt Maven Toolchains Plugin trong build/plugins của parent nếu muốn goal chọn toolchain chạy trong lifecycle của các module.

Các module không nên tự đặt release hoặc toolchain khác nhau nếu chúng thuộc cùng một sản phẩm và cần được build cùng baseline. Nếu module thực sự có yêu cầu Java khác, hãy khai báo ngoại lệ rõ ràng và kiểm thử riêng.

Khi nâng baseline, kiểm tra tất cả module, annotation processor, plugin và test runtime. Một module dùng JDK 17 không đảm bảo mọi plugin chạy trong cùng build đều tương thích JDK 17.

## 11. Cố định Gradle bằng Gradle Wrapper

Gradle Wrapper cung cấp gradlew và gradlew.bat để cả nhóm dùng cùng Gradle distribution.

Tạo wrapper:

~~~bash
gradle wrapper --gradle-version 9.2.1
~~~

Các file cần commit:

~~~text
gradlew
gradlew.bat
gradle/
  wrapper/
    gradle-wrapper.jar
    gradle-wrapper.properties
~~~

Chạy build bằng:

~~~bash
./gradlew clean check
~~~

Trên Windows:

~~~powershell
.\gradlew.bat clean check
~~~

File gradle-wrapper.properties có distributionUrl, ví dụ:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.2.1-bin.zip
~~~

Gradle Wrapper pin Gradle distribution, không tự pin JDK dùng để chạy Gradle daemon hoặc JDK toolchain biên dịch. Cần kiểm soát hai lớp đó riêng.

Có thể cấu hình distributionSha256Sum bằng checksum chính thức của Gradle distribution để wrapper xác minh file tải về. Giữ wrapper scripts, properties và checksum đồng bộ khi nâng Gradle.

## 12. Dùng Gradle Java Toolchains

Trong build.gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Java toolchain yêu cầu Gradle tìm một JDK 17 phù hợp cho các task Java. JavaCompile dùng compiler của toolchain; các task Test và Javadoc cũng sử dụng toolchain mặc định do Java plugin cấu hình.

Có thể giới hạn vendor nếu dự án yêu cầu một nhà cung cấp cụ thể:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Chỉ đặt vendor khi đó là yêu cầu thật của dự án. Vendor filter không thay thế kiểm tra patch version. Nếu cần đúng patch release, hãy cài hoặc provision đúng JDK và xác nhận metadata.

Có thể chọn runtime riêng cho một task Test:

~~~groovy
tasks.register('testsOn17', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Gradle Toolchains tách JDK compile/test khỏi JDK chạy Gradle daemon. Gradle có thể chạy trên JDK 24 trong khi compile và test dùng JDK 17.

## 13. Gradle auto-detection và auto-provisioning

Gradle tự phát hiện JDK ở các vị trí phổ biến như JAVA_HOME, package manager và một số thư mục cài đặt chuẩn.

Liệt kê toolchain đã phát hiện:

~~~bash
./gradlew -q javaToolchains
~~~

Nếu JDK nằm ở một thư mục riêng, có thể thêm đường dẫn vào gradle.properties của user:

~~~properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17
~~~

Trên Windows, dùng đường dẫn Windows phù hợp hoặc dấu gạch chéo xuôi trong property. Đường dẫn riêng của một máy nên đặt trong user-level Gradle configuration, không commit vào project nếu các developer có cấu trúc thư mục khác nhau.

Gradle có thể tự tải toolchain khi đã cấu hình toolchain download repository/resolver phù hợp. Ví dụ có thể dùng Foojay toolchain resolver convention plugin trong settings.gradle.kts:

~~~kotlin
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention").version("1.0.0")
}
~~~

Việc tải tự động giúp onboarding nhưng vẫn cần kiểm soát nguồn JDK, vendor, version và checksum theo chính sách tổ chức. Nếu thay đổi đường dẫn hoặc danh sách JDK, có thể cần dừng daemon:

~~~bash
./gradlew --stop
~~~

## 14. Phân biệt Gradle daemon JVM với compiler toolchain

Gradle --version hiển thị Launcher JVM và Daemon JVM. Launcher JVM khởi động Gradle client; daemon JVM chạy phần lớn build logic. Java toolchain lại quyết định compiler/launcher mà các task sử dụng.

Ví dụ:

~~~text
Gradle 9.2.1
Launcher JVM: 24.0.2
Daemon JVM: 24.0.2
Compiler home: /opt/jdks/jdk-17
Compiler language version: 17
~~~

Đây là cấu hình hợp lệ nếu Gradle version hỗ trợ chạy trên JDK 24 và project yêu cầu compile bằng JDK 17.

Nếu Gradle chạy trên một JDK không được Gradle version đó hỗ trợ, build có thể thất bại trước khi Java toolchain được áp dụng. Vì vậy, kiểm tra cả Gradle compatibility và project toolchain.

IDE cũng có thể cấu hình Gradle JVM riêng. Khi command line build thành công nhưng IDE thất bại, hãy kiểm tra Gradle JVM trong IDE và so sánh với gradlew --version.

## 15. Cấu hình CI cho Maven

CI nên cài JDK theo cùng baseline, gọi Maven Wrapper và tạo toolchains.xml nếu POM yêu cầu Maven Toolchains.

Ví dụ GitHub Actions:

~~~yaml
name: Java build

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Configure Maven toolchain
        shell: bash
        run: |
          mkdir -p "$HOME/.m2"
          cat > "$HOME/.m2/toolchains.xml" <<EOF
          <toolchains>
            <toolchain>
              <type>jdk</type>
              <provides>
                <version>17</version>
              </provides>
              <configuration>
                <jdkHome>$JAVA_HOME</jdkHome>
              </configuration>
            </toolchain>
          </toolchains>
          EOF

      - name: Verify build environment
        run: |
          java -version
          javac -version
          ./mvnw -version

      - name: Build and test
        run: ./mvnw -B -ntp clean verify
~~~

actions/setup-java cài JDK và cấu hình JAVA_HOME. Bước tạo toolchains.xml giúp Maven Toolchains tìm được JDK đã cài. Maven Wrapper chọn Maven distribution của project.

Nếu POM có Enforcer requireJavaVersion [17,18), setup-java phải thực sự chạy Maven trên JDK 17. Nếu CI chủ động chạy Maven trên một JDK khác nhưng compile toolchain17, hãy đặt rule đúng với runtime policy.

Trong tổ chức cần kiểm soát supply chain nghiêm ngặt, pin GitHub Actions theo commit SHA và dùng runner/container image đã được quản lý.

## 16. Cấu hình CI cho Gradle

Ví dụ GitHub Actions cho Gradle:

~~~yaml
name: Gradle build

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle

      - name: Verify JDK
        run: |
          java -version
          javac -version
          ./gradlew --version
          ./gradlew -q javaToolchains

      - name: Build and test
        run: ./gradlew --no-daemon clean check
~~~

Nếu build.gradle yêu cầu toolchain 17, Gradle sẽ tìm JDK 17 đã cài. Nếu không có toolchain phù hợp và auto-provisioning được cấu hình, Gradle có thể tải JDK theo resolver đã chọn.

Giữ Gradle Wrapper và Java toolchain declaration trong repository. CI chỉ cần cài JDK theo policy và gọi wrapper; không nên có một command CI khác biệt với cách developer build local.

## 17. Đồng bộ IDE với command line

IDE thường có nhiều trường cấu hình JDK khác nhau:

| IDE/công cụ | Cấu hình cần kiểm tra |
|---|---|
| IntelliJ IDEA | Project SDK, language level, Maven Runner JRE và Gradle JVM. |
| Eclipse | Installed JREs, compiler compliance và execution environment. |
| VS Code Java | Java runtime configuration và build tool wrapper. |
| Maven CLI | JAVA_HOME, PATH, mvnw và Maven Toolchains. |
| Gradle CLI | JAVA_HOME, Gradle Wrapper và Java Toolchains. |

Project SDK của IntelliJ không nhất thiết là JDK chạy Maven hoặc Gradle. Nếu build tool có khai báo toolchain, task compile/test có thể dùng JDK khác với Project SDK.

Sau khi thay đổi JDK trong IDE, kiểm tra lại bằng terminal:

~~~bash
./mvnw -version
./gradlew --version
./gradlew -q javaToolchains
~~~

Một build chạy thành công bằng wrapper trong terminal là tín hiệu quan trọng vì CI cũng thường chạy wrapper thay vì cấu hình riêng của IDE.

## 18. Multi-module Gradle và convention plugin

Với Gradle multi-project, nên đặt Java toolchain và release policy trong convention plugin hoặc build logic dùng chung. Điều này tránh module A dùng Java 17 còn module B vô tình dùng JDK mặc định của daemon.

Ví dụ đơn giản trong convention plugin:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Áp dụng convention plugin cho các module Java cần cùng baseline. Không áp dụng Java plugin cho module chỉ chứa tài liệu hoặc script nếu không cần.

Nếu một module có yêu cầu Java khác, khai báo riêng và thêm test matrix để xác nhận artifact của module đó tương thích với runtime dự kiến.

## 19. Kiểm tra bytecode và JDK thực sự được chọn

Không chỉ nhìn cấu hình; hãy kiểm tra build output.

Với Maven:

~~~bash
mvn -version
mvn -X -DskipTests compile
~~~

Trong log debug, tìm các dòng tương tự:

~~~text
Required toolchain: jdk [ version='17' ]
Found matching toolchain for type jdk: JDK[/opt/jdks/jdk-17]
Toolchain in maven-compiler-plugin: JDK[/opt/jdks/jdk-17]
Compiling 1 source file with javac [forked debug release 17]
~~~

Với Gradle:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew --info compileJava
~~~

Có thể kiểm tra class file bằng javap:

~~~bash
javap -verbose target/classes/example/BuildInfo.class
~~~

Java 17 class file có major version 61. Nếu source dùng release 17, class file phải tương thích Java 17.

Chạy artifact bằng đúng runtime mục tiêu để xác nhận:

~~~bash
java -cp target/classes example.BuildInfo
~~~

Trong bài kiểm chứng, chạy bằng JDK 17 cho output:

~~~text
runtime.feature=17
compiled.release=17
~~~

Chỉ kiểm tra major version chưa đủ để xác nhận toàn bộ ứng dụng chạy được. Cần chạy unit test, integration test và smoke test trên runtime mục tiêu.

## 20. Kiểm thử trên nhiều runtime version

Có dự án compile một lần bằng JDK 17 nhưng phải chạy trên nhiều runtime được hỗ trợ. Khi đó cần tách compile toolchain khỏi test runtime matrix.

Với Gradle, có thể tạo nhiều Test task, mỗi task chọn một JavaLauncher riêng:

~~~groovy
tasks.register('testOn21', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Với Maven, các plugin Surefire/Failsafe có hỗ trợ toolchains có thể dùng JDK được chọn cho test. Hãy kiểm tra log plugin để xác nhận JVM thực sự chạy test.

Ma trận test có thể gồm Java 17, 21 và runtime production. Không nên chỉ compile trên một JDK rồi suy ra mọi runtime đều tương thích.

## 21. Annotation processor và công cụ ngoài compiler

Một build có thể dùng thêm annotation processor, Kotlin, Scala, Groovy, Javadoc, JNI, GraalVM Native Image hoặc công cụ sinh code.

Không phải plugin nào cũng tự động sử dụng Maven/Gradle Java toolchain. Hãy kiểm tra tài liệu plugin và cấu hình riêng nếu plugin có compiler hoặc launcher độc lập.

Annotation processor chạy trong môi trường compiler. Một processor cũ có thể không tương thích JDK mới dù source project vẫn compile được. Ngược lại, plugin sinh source có thể yêu cầu JDK riêng.

Với multi-language build, ghi rõ toolchain cho từng task và xác minh executable trong log. Không giả định một khai báo Java toolchain sẽ điều khiển mọi executable bên ngoài build system.

## 22. Pin plugin, dependency và build configuration

JDK đồng bộ chỉ là một phần của reproducible build. Cần pin thêm:

- Maven plugin version trong POM.
- Gradle plugin version trong plugins block hoặc version catalog.
- Maven/Gradle Wrapper distribution.
- Dependency version và repository policy.
- Annotation processor và code generator version.
- JVM arguments và encoding nếu chúng ảnh hưởng kết quả build.
- Container image hoặc runner version khi cần tái lập chính xác.

Tránh dùng LATEST, RELEASE hoặc dynamic dependency version trong build production. Với Gradle, có thể dùng dependency locking và dependency verification. Với Maven, dùng version cụ thể và Enforcer rules để phát hiện plugin/dependency drift.

Maven local repository và Gradle cache giúp build nhanh hơn nhưng không thay thế việc pin phiên bản. Cache không thể sửa khác biệt giữa JDK, compiler release hoặc runtime.

## 23. Cố định patch version và vendor

Java toolchain languageVersion=17 thường cho phép mọi JDK major 17 thỏa mãn điều kiện. Maven toolchain yêu cầu version 17 cũng thường thể hiện major version.

Nếu chỉ cần cùng Java API level, major version 17 và release 17 có thể đủ. Nếu cần tái lập chính xác, ví dụ vì khác biệt vendor patch, hãy kiểm soát:

- Vendor JDK.
- Patch release cụ thể.
- CPU architecture.
- OS hoặc container base image.
- JDK distribution checksum.
- Native library và system dependency.

Có thể dùng container image được pin theo digest hoặc CI image nội bộ đã cài sẵn JDK cụ thể. Trong pipeline, in java -version và javac -version để lưu bằng chứng.

Không ghi đường dẫn JDK cá nhân vào POM hoặc build.gradle. Dùng toolchain criteria và để mỗi máy cung cấp installation path phù hợp.

## 24. Các lỗi đồng bộ JDK thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Maven chạy bằng JDK khác mong muốn | JAVA_HOME hoặc PATH trỏ tới JDK khác. | Kiểm tra mvn -version và cấu hình JAVA_HOME. |
| Maven báo không tìm thấy toolchain | Thiếu toolchains.xml hoặc provides không khớp POM. | Kiểm tra file toolchains và version yêu cầu. |
| Maven dùng javac của Maven JVM | Compiler plugin chưa nhận toolchain hoặc không fork theo cấu hình. | Kiểm tra maven-toolchains-plugin, compiler plugin và log debug. |
| Build báo release version not supported | Compiler JDK quá cũ so với release yêu cầu. | Cài toolchain phù hợp hoặc hạ release theo policy. |
| Artifact chạy lỗi UnsupportedClassVersionError | Runtime thấp hơn bytecode target. | Kiểm tra major version và runtime deploy. |
| IDE build khác CLI | IDE SDK, Maven Runner JRE hoặc Gradle JVM khác. | Chạy wrapper và đồng bộ cấu hình IDE. |
| Gradle báo không tìm thấy JDK | Toolchain chưa cài hoặc Gradle không phát hiện được. | Chạy javaToolchains, cấu hình installation path hoặc resolver. |
| Gradle vẫn dùng daemon cũ | Daemon giữ metadata toolchain trước đó. | Chạy gradlew --stop rồi build lại. |
| Unit test chạy trên JDK không mong muốn | Test plugin hoặc launcher chưa nhận toolchain. | Kiểm tra Surefire/Failsafe hoặc Gradle Test javaLauncher. |
| CI thành công nhưng local thất bại | JDK, vendor, Maven/Gradle hoặc environment khác. | So sánh version output, toolchain selection và wrapper. |
| Một module dùng release khác | Cấu hình con ghi đè parent hoặc convention plugin. | Tập trung release/toolchain ở parent hoặc convention plugin. |
| Build mới thất bại sau khi nâng JDK | Plugin hoặc annotation processor chưa hỗ trợ JDK mới. | Nâng plugin có kiểm soát và kiểm tra compatibility. |

## 25. Quy trình đồng bộ JDK có thể lặp lại

1. Chọn Java baseline và runtime tối thiểu.
2. Chọn JDK vendor/patch policy theo yêu cầu sản phẩm.
3. Cố định Maven hoặc Gradle bằng Wrapper.
4. Khai báo compiler release trong Maven hoặc Gradle.
5. Cấu hình Maven Toolchains hoặc Gradle Java Toolchains.
6. Cấu hình build JVM policy bằng Enforcer hoặc CI runtime setup khi cần.
7. Đưa cấu hình chung vào parent POM hoặc Gradle convention plugin.
8. Cài đúng JDK trên developer machine và CI.
9. Tạo Maven toolchains.xml trên CI nếu POM yêu cầu.
10. Cấu hình IDE dùng đúng project SDK và build JVM.
11. Chạy wrapper build, unit test và integration test.
12. Kiểm tra log toolchain, javac version và class file major version.
13. Lưu JDK, Maven/Gradle, plugin và OS version trong build report.
14. Chạy lại build trên runtime production hoặc test matrix.
15. Chỉ nâng baseline sau khi dependency và plugin đã được xác nhận tương thích.

## 26. Kết quả kiểm chứng trên JDK 24.0.2

Một project Maven độc lập đã được build với Maven 3.9.12 chạy trên Azul JDK 24.0.2. Maven Toolchains Plugin 3.3.0 chọn Corretto JDK 17.0.15; Maven Compiler Plugin 3.13.0 sử dụng javac từ toolchain với release 17.

Log xác nhận:

~~~text
Required toolchain: jdk [ version='17' ]
Found matching toolchain for type jdk: JDK[...corretto-17.0.15]
Toolchain in maven-compiler-plugin: JDK[...corretto-17.0.15]
Compiling 1 source file with javac [forked debug release 17]
BUILD SUCCESS
~~~

Một project Gradle độc lập cũng build thành công với Gradle 9.2.1 chạy trên Azul JDK 24.0.2 và compiler toolchain Corretto 17.0.15:

~~~text
Compiler language version: 17
BUILD SUCCESSFUL
~~~

Với cả hai project, javap báo major version 61 và chạy class bằng JDK 17 cho output:

~~~text
runtime.feature=17
compiled.release=17
~~~

Maven Enforcer Plugin 3.7.0 đã xác nhận thành công RequireMavenVersion và RequireJavaVersion đối với Maven runtime trong lần kiểm thử. Maven Wrapper Plugin 3.3.4 tạo wrapper pin Maven 3.9.12 và mvnw.cmd -version chạy thành công. Gradle Wrapper tạo wrapper pin Gradle 9.2.1 và gradlew.bat --version chạy thành công.

Các lần kiểm thử này xác nhận cơ chế chọn toolchain và wrapper hoạt động. Chúng không chứng minh mọi plugin hoặc dependency của một ứng dụng thực tế tương thích JDK 17; dự án cần chạy bộ test và kiểm tra dependency riêng.

## 27. Checklist trước khi coi build đã đồng bộ

- [ ] Đã thống nhất Java baseline cho source và runtime.
- [ ] Đã biết JDK chạy Maven/Gradle.
- [ ] Đã biết JDK toolchain dùng để compile.
- [ ] Đã đặt --release hoặc maven.compiler.release.
- [ ] Đã cố định Maven/Gradle bằng Wrapper.
- [ ] Đã pin plugin version.
- [ ] Đã cấu hình Maven Toolchains hoặc Gradle Java Toolchains.
- [ ] Đã không commit đường dẫn JDK cá nhân.
- [ ] Đã cấu hình CI cài JDK theo cùng policy.
- [ ] Đã cấu hình toolchains.xml trong CI nếu dùng Maven Toolchains.
- [ ] Đã kiểm tra test runtime.
- [ ] Đã đồng bộ Project SDK và build JVM trong IDE.
- [ ] Đã kiểm tra javac version và class file major version.
- [ ] Đã chạy test trên runtime production.
- [ ] Đã lưu JDK, build tool, plugin và environment version.
- [ ] Đã xác minh checksum nếu pin distribution hoặc container image.

## 28. Tài liệu tham khảo

- Apache Maven Toolchains Plugin — Usage: https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html
- Apache Maven Compiler Plugin — compiler:compile: https://maven.apache.org/components/plugins/maven-compiler-plugin/compile-mojo.html
- Apache Maven Enforcer — Built-in Rules: https://maven.apache.org/enforcer/enforcer-rules/index.html
- Apache Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Maven Wrapper Plugin — Usage: https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html
- Gradle — Toolchains for JVM projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — The Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- GitHub Actions setup-java: https://github.com/actions/setup-java

Đồng bộ JDK cần kiểm soát build JVM, compiler toolchain, release, test runtime và deployment runtime như các lớp riêng biệt. Maven/Gradle Wrapper cố định build tool; Toolchains chọn JDK cho compile/test; --release giới hạn API và bytecode; Enforcer kiểm tra điều kiện build process. Khi các lớp này được khai báo và xác minh trong cả máy lập trình lẫn CI, build sẽ nhất quán và dễ tái lập hơn.