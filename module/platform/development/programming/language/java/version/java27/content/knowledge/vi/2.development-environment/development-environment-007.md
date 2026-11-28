# Tái lập môi trường bằng toolchain và cấu hình dự án

Khi nhiều người cùng phát triển một ứng dụng Java, cùng một lệnh build cần dùng cùng phiên bản công cụ, cùng JDK và cùng tập dependency đã được xác định. Nếu máy lập trình viên dùng một JDK, máy CI dùng JDK khác, hoặc mỗi máy tự chọn một phiên bản Gradle/Maven, kết quả build có thể khác nhau dù mã nguồn giống nhau.

Tái lập môi trường phát triển là việc khai báo các yêu cầu quan trọng ngay trong cấu hình dự án, để thành viên mới, IDE và CI có thể thiết lập và chạy build theo cùng một quy ước. Với Java 27, cần phân biệt phiên bản JDK dùng để chạy build tool, JDK dùng để biên dịch và phiên bản Java mà sản phẩm cần hỗ trợ.

## 1. Những thành phần cần được cố định

Một môi trường Java có nhiều lớp. Mỗi lớp giải quyết một vấn đề riêng và cần được cấu hình đúng nơi.

| Thành phần | Vai trò | Cấu hình thường dùng |
| --- | --- | --- |
| Build tool | Xác định phiên bản Gradle hoặc Maven thực thi các tác vụ build | Gradle Wrapper hoặc Maven Wrapper |
| JVM chạy build tool | JVM chạy Gradle Daemon hoặc tiến trình Maven | Gradle Daemon JVM criteria; JVM khởi chạy Maven |
| JDK toolchain | JDK cung cấp `javac`, `java`, `javadoc` cho compile, test và tác vụ liên quan | Java Toolchains của Gradle hoặc Maven Toolchains |
| Phiên bản Java mục tiêu | Giới hạn cú pháp, bytecode và API Java mà mã nguồn được phép sử dụng | `--release` hoặc `maven.compiler.release` |
| Dependency và plugin | Xác định thư viện và plugin tham gia build | Phiên bản khai báo rõ ràng, dependency lock và verification |
| Môi trường hệ điều hành | Ảnh hưởng đến công cụ native, kiến trúc CPU, đường dẫn, locale và biến môi trường | CI image/container và cấu hình môi trường |

Wrapper cố định build tool. Toolchain chọn JDK cho các tác vụ Java. `--release` giới hạn phiên bản Java mà mã nguồn hướng tới. Ba cấu hình này bổ sung cho nhau, không thay thế nhau.

Ví dụ, một dự án có thể dùng Gradle 9.9.2 chạy trên JDK 27, dùng Java Toolchain 27 để compile và test, đồng thời đặt `options.release` thành 27. Nếu sản phẩm cần chạy trên Java 25, có thể vẫn dùng JDK 27 để build nhưng đặt phiên bản mục tiêu là 25, miễn là mã nguồn không dùng tính năng hoặc API chỉ có từ Java 26/27.

## 2. Chọn JDK chạy build và JDK của dự án

### JDK chạy build tool

Đây là JVM khởi chạy Gradle hoặc Maven. JVM này phải đáp ứng yêu cầu của phiên bản build tool đang dùng. Với Gradle, cần phân biệt JVM của client và JVM của Daemon: client khởi chạy wrapper, còn Daemon thực thi build và duy trì trạng thái giữa các lần chạy.

Từ Gradle 9.8.0, JDK 27 được hỗ trợ để chạy Gradle và làm Java Toolchain. Khi xây dựng dự án Java 27, hãy chọn một bản Gradle còn được hỗ trợ và kiểm tra ma trận tương thích trước khi nâng cấp. Tài liệu tương thích hiện hành liệt kê Java 27 từ Gradle 9.8.0.

Maven được khởi chạy bằng JVM trong môi trường của tiến trình, thường được chọn qua `JAVA_HOME` hoặc `PATH`. Maven Toolchains có thể chọn một JDK khác cho các plugin có hỗ trợ toolchain. Vì vậy, việc Maven đang chạy trên JDK 21 không có nghĩa compiler bắt buộc phải dùng JDK 21.

### JDK toolchain của dự án

Toolchain mô tả JDK mà các tác vụ cần sử dụng. Với Java, compiler dùng `javac`, test và tác vụ chạy chương trình dùng `java`, còn Javadoc dùng `javadoc`. Khai báo toolchain ở cấp dự án giúp build tool chọn đúng JDK mà không phải ghi đường dẫn cài đặt riêng của từng máy vào file build.

Nếu cần ràng buộc thêm nhà cung cấp JDK, có thể khai báo vendor. Ví dụ, một nhóm có thể thống nhất dùng Eclipse Temurin hoặc một bản phân phối đã được tổ chức phê duyệt. Chỉ đặt vendor khi có yêu cầu tương thích hoặc chính sách cụ thể; nếu không, ràng buộc vendor làm giảm số JDK có thể đáp ứng cấu hình.

Một toolchain chỉ khai báo major version 27 chưa khóa toàn bộ bản vá và build number. Nếu cần mọi máy dùng cùng một bản phân phối và cùng bản cập nhật JDK, hãy quản lý JDK qua image/container đã khóa digest hoặc qua kho công cụ nội bộ, rồi xác minh phiên bản đầy đủ trong CI.

### Phiên bản Java mục tiêu

Toolchain và phiên bản mục tiêu giải quyết hai câu hỏi khác nhau:

- Toolchain trả lời: compiler và các tác vụ Java sẽ chạy bằng JDK nào?
- `--release` trả lời: mã nguồn được phép dùng cú pháp và API của phiên bản Java nào, và bytecode được tạo cho phiên bản nào?

Dùng `--release` khi cần kiểm soát chặt khả năng tương thích. Chỉ đặt toolchain thành JDK 27 không tự ngăn mã nguồn sử dụng API mới hơn phiên bản runtime mà sản phẩm hỗ trợ. Ngược lại, đặt `--release 25` không tự chọn JDK 25 để chạy build.

## 3. Cấu hình dự án dùng Gradle

### Khóa phiên bản Gradle bằng Wrapper

Đưa Gradle Wrapper vào repository để mọi người dùng cùng một bản Gradle mà dự án đã chọn. Wrapper gồm các script chạy build và cấu hình trong `gradle/wrapper/gradle-wrapper.properties`.

Ví dụ cấu hình dùng Gradle 9.9.2:

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.2-bin.zip
distributionSha256Sum=<SHA-256-cua-goi-Gradle-9.9.2>
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

Lấy checksum từ trang checksum chính thức của Gradle, không tự tính từ một gói vừa tải rồi coi đó là nguồn xác thực độc lập. Khi thay đổi Wrapper, kiểm tra cả URL, checksum của distribution và checksum của file `gradle-wrapper.jar`. Wrapper JAR chạy trước build script nên cần được xem là một phần quan trọng của chuỗi cung ứng phần mềm.

Dùng script Wrapper thay vì gọi một bản Gradle cài toàn cục:

```bash
./gradlew clean build
```

Trên Windows:

```powershell
.\gradlew.bat clean build
```

### Khóa JVM chạy Gradle Daemon

Nếu muốn mọi máy và CI dùng cùng major version cho Gradle Daemon, hãy tạo file tiêu chí JVM trong repository:

```bash
./gradlew updateDaemonJvm --jvm-version=27
```

Lệnh tạo hoặc cập nhật `gradle/gradle-daemon-jvm.properties`. Commit file này cùng dự án để Gradle client tìm JVM phù hợp và khởi chạy Daemon theo tiêu chí đã khai báo. Có thể thêm vendor nếu nhóm cần thống nhất nhà cung cấp JDK.

Tính năng này cần cấu hình nơi tải toolchain nếu muốn Gradle tự provision JDK khi máy chưa cài sẵn. Một lựa chọn được tài liệu Gradle hướng dẫn là Foojay Toolchains Resolver Convention Plugin trong `settings.gradle`:

```groovy
plugins {
    id 'org.gradle.toolchains.foojay-resolver-convention' version '1.0.0'
}
```

Chỉ bật tải JDK tự động khi repository và nguồn tải phù hợp chính sách của dự án. Trong môi trường doanh nghiệp, có thể dùng kho nội bộ hoặc cài JDK sẵn trên runner. Nếu không cấu hình resolver, hãy bảo đảm JDK phù hợp đã được cài trên từng máy.

### Khai báo Java Toolchain và release

Với dự án Gradle dùng Groovy DSL, cấu hình trong `build.gradle`:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 27
}
```

Khai báo toolchain ở cấp Java project giúp các tác vụ compile, test và Javadoc do Java plugin tạo ra dùng JDK phù hợp. `options.release` đặt giới hạn Java API và bytecode cho các tác vụ compile.

Nếu dự án dùng JDK 27 nhưng phải phát hành bytecode tương thích Java 25, có thể đặt `options.release = 25`. Khi đó không được sử dụng cú pháp hoặc API chỉ có từ Java 26/27. Cần cấu hình nhất quán cho mọi source set và tác vụ compile bổ sung do plugin khác tạo ra.

Có thể xem các JDK mà Gradle phát hiện được bằng:

```bash
./gradlew -q javaToolchains
```

Kết quả hiển thị phiên bản, vendor, kiến trúc, đường dẫn cài đặt và nguồn phát hiện. Nếu vừa thay đổi cấu hình toolchain mà Daemon vẫn giữ trạng thái cũ, dừng Daemon rồi chạy lại build:

```bash
./gradlew --stop
./gradlew clean check
```

### Khóa dependency và xác minh artifact

Cấu hình toolchain không cố định phiên bản thư viện. Hãy khai báo phiên bản dependency và plugin rõ ràng, quản lý phiên bản tập trung bằng version catalog khi phù hợp, và tránh các selector thay đổi theo thời gian như `1.+`, `latest.release` hoặc dependency snapshot trong build phát hành.

Gradle hỗ trợ dependency locking. Có thể bật cho toàn bộ configuration trong `build.gradle`:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Sau đó chạy các tác vụ làm phát sinh resolution để tạo hoặc cập nhật lock state:

```bash
./gradlew dependencies --write-locks
```

Đưa `gradle.lockfile` vào source control và cập nhật có chủ đích khi nâng phiên bản dependency. Với dự án cần kiểm tra tính toàn vẹn artifact, có thể tạo metadata xác minh:

```bash
./gradlew --write-verification-metadata sha256
```

File `gradle/verification-metadata.xml` ghi lại checksum cần kiểm tra trong những lần build sau. Xem xét kỹ kết quả bootstrap trước khi commit; checksum được sinh từ repository hiện tại không tự chứng minh artifact ban đầu là đáng tin cậy.

## 4. Cấu hình dự án dùng Maven

### Khóa phiên bản Maven bằng Maven Wrapper

Maven Wrapper đưa phiên bản Maven cần dùng vào cấu hình dự án. Các file wrapper nằm trong `.mvn/wrapper`, còn script chạy build là `mvnw` và `mvnw.cmd`.

Tạo hoặc cập nhật Wrapper bằng Maven Wrapper Plugin:

```bash
mvn wrapper:wrapper -Dtype=bin
```

Trong `.mvn/wrapper/maven-wrapper.properties`, khai báo URL của một bản Maven cụ thể và checksum tương ứng:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/<maven-version>/apache-maven-<maven-version>-bin.zip
distributionSha256Sum=<SHA-256-cua-goi-Maven>
wrapperSha256Sum=<SHA-256-cua-maven-wrapper.jar>
```

Lệnh tạo Wrapper ở trên chọn kiểu `bin`, vì vậy dự án có Wrapper JAR và có thể xác minh cả hai checksum. Nếu dự án dùng kiểu mặc định `only-script`, không có Wrapper JAR nên bỏ thuộc tính `wrapperSha256Sum`. Thay placeholder bằng phiên bản và checksum đã được nhóm phê duyệt. Khi dùng repository mirror nội bộ, cấu hình URL mirror theo chính sách tổ chức và kiểm tra nguồn artifact.

Chạy build bằng Wrapper:

```bash
./mvnw clean verify
```

Trên Windows:

```powershell
.\mvnw.cmd clean verify
```

### Chọn JDK bằng Maven Toolchains

Maven Toolchains cho phép dự án yêu cầu một JDK cho các plugin hỗ trợ toolchain, độc lập với JDK đang chạy Maven. Maven Toolchains Plugin 3.3.0 có goal `select-jdk-toolchain` để phát hiện JDK đã cài và chọn bản phù hợp.

Trong `pom.xml`, khai báo phiên bản Java mục tiêu và yêu cầu toolchain:

```xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <toolchain.jdk.version>27</toolchain.jdk.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.3.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>select-jdk-toolchain</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
        </plugin>
    </plugins>
</build>
```

Goal `select-jdk-toolchain` chọn JDK phù hợp từ các JDK phát hiện được và toolchain đã khai báo. Có thể bổ sung thuộc tính `toolchain.jdk.vendor` nếu cần giới hạn vendor. Các plugin Maven có hỗ trợ JDK toolchain, như Compiler, Surefire, Failsafe và Javadoc, có thể sử dụng JDK được chọn.

Nếu cơ chế tự phát hiện không tìm được JDK, có thể khai báo đường dẫn cài đặt theo từng máy trong `~/.m2/toolchains.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>27</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/path/to/jdk-27</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Đường dẫn trong file này là đường dẫn cục bộ, vì vậy mỗi máy có thể cần một giá trị khác nhau. Không ghi đường dẫn tuyệt đối của máy cá nhân vào `pom.xml`. POM chỉ nên mô tả yêu cầu JDK; file toolchains trên máy chịu trách nhiệm ánh xạ yêu cầu đó tới nơi cài JDK.

### Phân biệt Maven JVM và JDK compiler

Maven Wrapper cố định phiên bản Maven. `JAVA_HOME` xác định JVM khởi chạy Maven. Maven Toolchains chọn JDK cho các plugin tương thích. `maven.compiler.release` giới hạn phiên bản Java mà compiler tạo ra.

Với dự án Java 27, có thể đặt `toolchain.jdk.version` và `maven.compiler.release` cùng là 27. Nếu cần phát hành cho Java 25, dùng JDK 27 để build nhưng đặt `maven.compiler.release` thành 25. Hãy bảo đảm plugin compiler và JDK đang chọn hỗ trợ release đó.

Nên khóa phiên bản plugin trong `pluginManagement` hoặc khai báo trực tiếp tại POM. Dependency nên dùng phiên bản cụ thể hoặc BOM đã được quản lý. Không phụ thuộc vào phiên bản plugin mặc định ngầm định của môi trường Maven trên từng máy.

## 5. Đồng bộ IDE và CI

Cấu hình trong POM hoặc Gradle build file là nguồn yêu cầu của dự án. IDE vẫn có các lựa chọn JVM riêng, vì vậy cần kiểm tra để thao tác chạy trong IDE có cùng kết quả với lệnh chạy từ terminal.

Với dự án Gradle:

- Mở phần cài đặt Gradle của IDE và chọn Gradle JVM tương thích với tiêu chí Daemon của dự án.
- Đặt Project SDK và mức ngôn ngữ Java theo yêu cầu dự án.
- Import dự án bằng Gradle Wrapper, sau đó chạy cùng tác vụ `check` hoặc `build` như CI.

Với dự án Maven:

- Chọn Maven Runner JRE phù hợp với yêu cầu chạy Maven.
- Chọn JDK cho Maven importer phù hợp để quá trình import và đồng bộ không sử dụng một JVM ngoài dự kiến.
- Dùng Maven Wrapper và giữ `pom.xml` làm nơi khai báo compiler/toolchain.

Trong CI, dùng cùng Wrapper và JDK đã được quy định. Ví dụ, một job Gradle có thể chạy:

```bash
./gradlew --version
./gradlew clean check
```

Một job Maven có thể chạy:

```bash
./mvnw --version
./mvnw -B -ntp clean verify
```

Đưa bước kiểm tra phiên bản vào log CI để khi build lỗi có thể xác định runner đã dùng Maven/Gradle và JVM nào. Nếu dự án phụ thuộc thư viện native, công cụ C/C++, browser driver hoặc image xử lý theo kiến trúc, cần cố định thêm hệ điều hành, kiến trúc CPU và các công cụ tương ứng. Có thể dùng container image đã khóa theo digest để kiểm soát lớp hệ điều hành.

Các file cấu hình dự án nên được commit gồm Wrapper, build file, version catalog, lockfile, metadata xác minh dependency và Gradle Daemon JVM criteria nếu dự án sử dụng. Không commit cache, mật khẩu, token, file cấu hình cá nhân hoặc đường dẫn cài JDK chỉ đúng trên một máy. Thông tin đăng nhập repository cần được truyền qua secret của CI hoặc cơ chế quản lý bí mật của tổ chức.

## 6. Quy trình thiết lập một môi trường mới

Có thể áp dụng quy trình sau khi một thành viên mới clone repository hoặc khi tạo CI runner mới:

1. Đọc hướng dẫn dự án để xác định build tool, JDK major version, vendor và phiên bản Java mục tiêu.
2. Cài JDK theo yêu cầu hoặc cấu hình nguồn provision đã được dự án chấp nhận.
3. Chạy `java --version` và `javac --version` để xác minh JDK cục bộ.
4. Chạy Wrapper để kiểm tra phiên bản build tool; không cần dựa vào bản Gradle/Maven cài toàn cục.
5. Kiểm tra toolchain được phát hiện và xác nhận compiler/test dùng đúng JDK.
6. Chạy build và test từ terminal.
7. Mở dự án trong IDE, đồng bộ JVM của IDE với cấu hình dự án và chạy lại một tác vụ kiểm tra.
8. Chạy cùng lệnh build trong CI và so sánh log phiên bản, dependency resolution và kết quả test.

Một số lệnh chẩn đoán hữu ích:

| Mục tiêu | Gradle | Maven |
| --- | --- | --- |
| Kiểm tra build tool và JVM chạy build | `./gradlew --version` | `./mvnw --version` |
| Xem JDK toolchain đã phát hiện | `./gradlew -q javaToolchains` | `./mvnw org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains` |
| Chạy kiểm tra chính | `./gradlew clean check` | `./mvnw -B -ntp clean verify` |

Nếu lệnh terminal thành công nhưng IDE thất bại, kiểm tra JVM của IDE, importer và runner. Nếu IDE thành công nhưng CI thất bại, so sánh phiên bản Wrapper, JDK vendor/build, kiến trúc runner, biến môi trường và repository mirror.

## 7. Lỗi thường gặp và cách xử lý

### Build chạy bằng JDK khác với JDK compile

Nguyên nhân thường là nhầm JVM chạy build tool với toolchain. Kiểm tra `--version` của Wrapper, log chọn toolchain và cấu hình `JAVA_HOME`. Với Gradle, xem cả Daemon JVM criteria; với Maven, kiểm tra yêu cầu toolchain trong POM và kết quả phát hiện JDK.

### Gradle không tìm thấy JDK 27

Kiểm tra JDK đã được cài đúng và có thể thực thi `bin/java`. Chạy `./gradlew -q javaToolchains` để xem Gradle nhận diện được gì. Nếu muốn tự tải JDK, cấu hình toolchain download resolver; nếu dùng JDK cài sẵn, khai báo nguồn hoặc đường dẫn theo tài liệu Gradle. Kiểm tra thêm phiên bản Gradle: cần Gradle 9.8.0 trở lên để chạy trên JDK 27.

### Maven không chọn được toolchain

Chạy goal `display-discovered-jdk-toolchains` để xem Maven phát hiện được JDK nào. Đảm bảo version và vendor trong POM khớp với JDK cài trên máy. Nếu không dùng discovery, kiểm tra `~/.m2/toolchains.xml` và giá trị `jdkHome`. Xác nhận các plugin cần dùng có hỗ trợ Maven Toolchains.

### Build đúng trên máy cá nhân nhưng sai trên CI

Kiểm tra xem CI có dùng Wrapper của repository hay gọi build tool cài sẵn. So sánh JDK major, vendor, build number, hệ điều hành, kiến trúc, biến môi trường và nguồn repository. Nếu cần khóa chính xác hơn major version, dùng JDK image hoặc kho công cụ đã được quản lý và xác minh.

### Cùng mã nguồn nhưng dependency thay đổi

Kiểm tra version catalog, phiên bản plugin, BOM và lockfile. Loại bỏ selector thay đổi theo thời gian khỏi build phát hành. Bật dependency verification nếu dự án cần xác minh checksum hoặc chữ ký artifact. Khi cập nhật thư viện, review thay đổi lockfile và metadata xác minh như một phần của thay đổi mã nguồn.

### Wrapper tải xuống thất bại vì checksum

Không xóa checksum để bỏ qua lỗi. Kiểm tra URL, phiên bản distribution và checksum được công bố từ nguồn chính thức. Nếu dùng mirror, xác minh mirror đã đồng bộ artifact đúng với bản phát hành đã phê duyệt. Chỉ cập nhật Wrapper sau khi kiểm tra script, JAR và file properties.

## 8. Giới hạn của tính tái lập

Toolchain và Wrapper giúp thống nhất công cụ build, nhưng không tự bảo đảm mọi file đầu ra giống nhau từng byte. Kết quả vẫn có thể phụ thuộc vào hệ điều hành, kiến trúc CPU, thư viện native, locale, timezone, timestamp trong archive, biến môi trường, dữ liệu tải từ mạng và mã build không xác định.

Đối với build cần tái lập ở mức artifact, cần kiểm soát thêm timestamp, thứ tự đóng gói, nguồn dependency, công cụ native và image hệ điều hành. Mọi dependency hoặc plugin được tải trong build cũng cần có nguồn tin cậy và phiên bản ổn định. Khi dự án cần mức bảo đảm cao hơn, hãy đưa các yếu tố này vào pipeline kiểm tra thay vì chỉ dựa vào cấu hình JDK.

## 9. Tài liệu tham khảo chính thức

- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Gradle Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle Daemon và Daemon JVM criteria](https://docs.gradle.org/current/userguide/gradle_daemon.html)
- [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Securing the Gradle Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Gradle Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/)
- [Apache Maven Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/)
- [Apache Maven Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html)
- [Apache Maven Available Plugins](https://maven.apache.org/plugins/)
