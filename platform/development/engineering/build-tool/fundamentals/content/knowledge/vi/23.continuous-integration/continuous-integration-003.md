# Sử dụng wrapper và toolchain nhất quán giữa máy cá nhân với CI

Một dự án Java có thể build thành công trên máy lập trình viên nhưng thất bại trên CI, hoặc ngược lại. Nguyên nhân thường không nằm ở mã nguồn mà ở khác biệt môi trường: máy cá nhân dùng Gradle/Maven version khác, JDK khác, compiler khác, dependency được phân giải khác hoặc IDE khởi chạy build bằng một Java runtime khác với terminal.

Để giảm sai lệch, dự án cần quản lý rõ hai nhóm công cụ:

- **Wrapper** cố định phiên bản build tool mà mọi người dùng để thực hiện build.
- **Toolchain** xác định JDK/compiler dùng cho các tác vụ Java như biên dịch, test và tạo tài liệu.

Hai cơ chế này bổ sung cho nhau. Gradle Wrapper không tự quyết định mọi JDK mà project dùng; Java toolchain cũng không tự cố định phiên bản Gradle. Với Maven, Maven Wrapper cố định Maven distribution, còn Maven Toolchains giúp chọn JDK cho plugin hỗ trợ toolchain. Cần cấu hình cả hai lớp và bảo đảm CI chạy đúng wrapper cùng chính sách Java của dự án.

## 1. Vì sao máy cá nhân và CI có thể build khác nhau?

Một lệnh như build hoặc verify phụ thuộc vào nhiều thành phần:

| Thành phần | Ảnh hưởng |
|---|---|
| Gradle/Maven version | Cách đọc build script/POM, task/lifecycle, dependency resolution và hành vi plugin |
| JDK chạy build tool | JVM khởi động Gradle/Maven, các plugin và một số process con |
| JDK compiler/toolchain | Cú pháp Java được hỗ trợ, bytecode và API mục tiêu |
| Java runtime khi test | Khả năng chạy test và dependency đã biên dịch |
| Plugin version | Compiler, test runner, packaging, code generation và các bước build khác |
| Dependency version | API, bytecode và hành vi của thư viện được sử dụng |
| Repository/cache | Artifact nào được tải, metadata nào được dùng và thời gian phân giải |
| IDE/terminal/CI configuration | JDK, properties, profiles, environment variables và working directory |

Ví dụ, máy lập trình viên có Gradle 8.x và JDK 21, còn CI gọi một Gradle cài sẵn cũ hơn với JDK 17. Dù cùng commit, build script có thể dùng API Gradle chưa tồn tại ở version CI hoặc Gradle daemon không chạy được trên JDK được chọn.

Một trường hợp khác: cả hai nơi đều dùng cùng Gradle Wrapper, nhưng máy cá nhân compile bằng JDK 21 trong khi CI dùng JDK 17. Nếu project yêu cầu release 21, CI sẽ báo lỗi compiler. Nếu project yêu cầu release 17, hai nơi có thể compile được nhưng vẫn cần kiểm tra dependency, plugin và test runtime.

## 2. Wrapper là gì?

Wrapper là bộ script và metadata đi kèm repository để khởi chạy một phiên bản build tool đã được dự án chỉ định. Người dùng chạy wrapper của project thay vì dựa vào bản Gradle hoặc Maven cài toàn cục trên máy.

Lợi ích chính:

- Mọi máy dùng cùng phiên bản build tool theo cấu hình được commit.
- CI không cần phụ thuộc vào Gradle/Maven version cài sẵn trên runner.
- Người mới có thể build project sau khi cài Java mà không cần tự cài đúng build tool trước.
- Việc nâng cấp build tool trở thành thay đổi có thể review trong source control.
- Tài liệu, script và CI có thể dùng cùng một command.

Wrapper không cố định JDK, dependency hoặc plugin version. Nó chỉ kiểm soát việc tải và khởi chạy distribution của build tool. Vì vậy, Wrapper là nền tảng của build nhất quán, không phải toàn bộ giải pháp.

## 3. Gradle Wrapper

### 3.1. Các file Gradle Wrapper

Một project Gradle thường có các file:

~~~text
order-service/
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Vai trò của từng file:

- **gradlew:** script khởi chạy trên Linux/macOS và các môi trường Unix tương thích.
- **gradlew.bat:** script khởi chạy trên Windows.
- **gradle-wrapper.jar:** thành phần Java thực hiện việc tải và khởi chạy Gradle distribution.
- **gradle-wrapper.properties:** cấu hình distribution, nơi tải và một số thiết lập Wrapper.

Các file wrapper script, JAR và properties cần được commit vào repository. Không nên yêu cầu mỗi lập trình viên tự tạo Wrapper trên máy của mình.

### 3.2. Cấu hình phiên bản Gradle

Ví dụ gradle/wrapper/gradle-wrapper.properties:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https://services.gradle.org/distributions/gradle-8.10.2-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

Thuộc tính quan trọng nhất là **distributionUrl**. Nó chỉ định Gradle distribution mà Wrapper sẽ tải và dùng. Hậu tố -bin thường chứa những thành phần cần thiết để chạy Gradle; -all còn kèm source và documentation hữu ích cho việc phát triển hoặc tra cứu.

Khi người dùng chạy Wrapper lần đầu, nó kiểm tra distribution trong cache người dùng. Nếu chưa có, nó tải distribution từ URL được cấu hình, giải nén và khởi chạy. Những lần sau có thể dùng bản đã tải.

### 3.3. Chạy build bằng Wrapper

Linux/macOS:

~~~bash
./gradlew build
./gradlew test
./gradlew --version
~~~

Windows:

~~~bat
gradlew.bat build
gradlew.bat test
gradlew.bat --version
~~~

Trong tài liệu dự án, script CI và hướng dẫn phát triển, nên dùng Wrapper của project. Gọi gradle build có thể dùng một bản Gradle cài toàn cục và bỏ qua version được dự án pin.

### 3.4. Tạo hoặc nâng cấp Gradle Wrapper

Khi cần cập nhật Gradle, người quản lý build có thể dùng một Gradle hiện có để tạo Wrapper hoặc dùng Wrapper hiện tại để cập nhật distribution:

~~~bash
gradle wrapper --gradle-version 8.10.2 --distribution-type bin
~~~

Nếu project đã có Wrapper, có thể dùng:

~~~bash
./gradlew wrapper --gradle-version 8.10.2 --distribution-type bin
~~~

Sau đó review các file thay đổi trong gradle/wrapper/ và script wrapper. Không chỉ sửa một URL bằng tay rồi mặc định mọi thành phần Wrapper đều đã được cập nhật đúng.

Nâng cấp Wrapper là thay đổi build infrastructure. Trước khi merge, nên chạy build/test bằng version mới, xác nhận plugin tương thích và kiểm tra yêu cầu JVM của Gradle version đó.

### 3.5. Kiểm tra tính toàn vẹn distribution

Gradle Wrapper hỗ trợ thuộc tính distributionSha256Sum trong gradle-wrapper.properties:

~~~properties
distributionUrl=https://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=<sha256-cua-distribution-da-duoc-xac-minh>
~~~

Giá trị checksum phải được lấy từ nguồn phát hành đáng tin cậy và đối chiếu trước khi commit. Wrapper có thể xác minh distribution tải về khớp checksum được cấu hình. Không điền một giá trị tự đoán hoặc lấy từ một nguồn không đáng tin cậy.

Trong CI, có thể bổ sung kiểm tra wrapper JAR bằng công cụ/action validation phù hợp với nền tảng CI. Việc này giúp phát hiện wrapper JAR bị sửa đổi ngoài ý muốn. Cần kiểm tra kết quả validation và cập nhật wrapper theo quy trình được kiểm soát.

### 3.6. Quyền thực thi và line ending

Trên Linux/macOS, file gradlew cần có quyền thực thi. Nếu sau khi clone script báo Permission denied, kiểm tra executable bit trong Git:

~~~bash
git ls-files --stage gradlew
~~~

Mode thường cần là 100755. Nếu cần sửa quyền:

~~~bash
chmod +x gradlew
git add gradlew
~~~

Trên Windows, dùng gradlew.bat. Nếu script Unix gặp lỗi shell do line ending hoặc file bị chỉnh sửa, kiểm tra .gitattributes và cấu hình checkout.

## 4. Maven Wrapper

### 4.1. Các file Maven Wrapper

Một project Maven có thể chứa:

~~~text
order-service/
├── mvnw
├── mvnw.cmd
└── .mvn/
    └── wrapper/
        ├── maven-wrapper.jar
        └── maven-wrapper.properties
~~~

Tùy loại Wrapper được tạo, một số file hoặc cách triển khai bootstrap có thể khác nhau. Các thành phần cốt lõi là script khởi chạy và cấu hình chỉ định Maven distribution.

### 4.2. Cấu hình Maven distribution

Ví dụ .mvn/wrapper/maven-wrapper.properties:

~~~properties
wrapperVersion=3.3.2
distributionType=only-script
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
~~~

**distributionUrl** chỉ định phiên bản Maven mà Wrapper sẽ tải và chạy. **wrapperVersion** liên quan đến phiên bản implementation của Maven Wrapper; nó khác với Maven distribution version. **distributionType** xác định kiểu Wrapper được tạo theo hỗ trợ của phiên bản Wrapper.

Không nhầm phiên bản Maven Wrapper với phiên bản Maven. Một project có thể dùng Wrapper implementation version 3.x để tải Maven distribution 3.9.x.

### 4.3. Chạy bằng Maven Wrapper

Linux/macOS:

~~~bash
./mvnw --version
./mvnw test
./mvnw verify
~~~

Windows:

~~~bat
mvnw.cmd --version
mvnw.cmd test
mvnw.cmd verify
~~~

CI và hướng dẫn phát triển nên dùng ./mvnw hoặc mvnw.cmd thay vì gọi mvn toàn cục. Wrapper đảm bảo Maven distribution nhất quán theo cấu hình repository.

### 4.4. Tạo hoặc nâng cấp Maven Wrapper

Maven Wrapper có thể được tạo bằng plugin wrapper của Maven. Ví dụ, khi đã có Maven cài trên máy:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

Sau khi tạo, review các file mvnw, mvnw.cmd và .mvn/wrapper/. Cú pháp và các tùy chọn cụ thể phụ thuộc phiên bản Maven Wrapper Plugin; nên dùng phiên bản plugin đã được xác định trong quy trình dự án.

Khi cập nhật Maven distribution, sửa cấu hình Wrapper qua plugin hoặc theo hướng dẫn chính thức của phiên bản đang dùng, sau đó chạy ./mvnw --version để xác nhận đúng Maven distribution.

### 4.5. Xác minh Maven distribution

Maven Wrapper hỗ trợ cấu hình checksum distribution trong các phiên bản Wrapper có hỗ trợ, ví dụ thuộc tính distributionSha256Sum trong maven-wrapper.properties:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=<sha256-cua-maven-distribution-da-duoc-xac-minh>
~~~

Hãy kiểm tra tài liệu của Maven Wrapper version mà project sử dụng để xác nhận thuộc tính và hành vi hỗ trợ. Lấy checksum từ nguồn phát hành tin cậy, lưu đúng giá trị và review thay đổi. Không dùng placeholder trong ví dụ làm giá trị thực tế.

## 5. Wrapper cố định build tool, không cố định Java

Một nhầm lẫn phổ biến là cho rằng commit gradlew hoặc mvnw đã làm build giống nhau trên mọi máy. Wrapper chỉ cố định Gradle/Maven distribution. Build vẫn phụ thuộc vào JVM khởi chạy build tool và compiler/toolchain.

Ví dụ:

~~~text
Developer laptop                  CI runner
----------------                  ---------
Gradle Wrapper 8.10.2             Gradle Wrapper 8.10.2
Gradle JVM: JDK 21                Gradle JVM: JDK 17
Compile toolchain: JDK 21         Compile toolchain: JDK 21
~~~

Hai môi trường dùng cùng Gradle distribution và compiler JDK, nhưng daemon JVM khác nhau. Build chỉ hoạt động nếu Gradle 8.10.2 hỗ trợ cả hai JVM đó và plugin tương thích. Nếu một môi trường dùng JDK không được Gradle hỗ trợ để chạy daemon, build có thể dừng trước khi compile.

Một cấu hình nhất quán cần xác định:

1. Phiên bản Wrapper.
2. JVM tối thiểu/được hỗ trợ để chạy build tool.
3. JDK/toolchain dùng để compile và test.
4. Java release mà artifact cần tương thích.
5. JDK/runtime dùng trong các bước chạy ứng dụng hoặc integration test.

## 6. Java toolchain trong Gradle

### 6.1. Chọn JDK cho compile và test

Với Gradle Java plugin, có thể khai báo toolchain trong build.gradle.kts:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Gradle dùng toolchain phù hợp cho các task Java hỗ trợ toolchain, chẳng hạn compile, test và javadoc. Điều này giúp project yêu cầu JDK 21 cho công việc Java dù Gradle daemon có thể chạy bằng một JDK khác tương thích với Gradle.

### 6.2. Toolchain không nhất thiết tự tải JDK

Gradle có thể phát hiện JDK đã cài trên máy. Việc tự tải/provision JDK cần cấu hình resolver hoặc cơ chế provisioning phù hợp với phiên bản Gradle và chính sách dự án.

Trong CI, cách đơn giản và dễ kiểm soát là cài JDK cần thiết trước khi chạy Wrapper, sau đó để Gradle toolchain chọn JDK đó. Nếu dùng auto-provision, phải cấu hình nguồn tải và checksum/trust policy rõ ràng.

### 6.3. Tách toolchain khỏi Java release mục tiêu

Toolchain xác định JDK/compiler được dùng. options.release xác định Java release mà bytecode và API Java SE cần tương thích.

Ví dụ dùng compiler JDK 21 nhưng tạo artifact hỗ trợ Java 17:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Điều này chỉ giới hạn API Java SE và bytecode theo Java 17. Dependency bên ngoài, annotation processor và runtime library vẫn phải hỗ trợ Java 17. Cần chạy test trên runtime mục tiêu nếu đó là môi trường được cam kết hỗ trợ.

### 6.4. Gradle JVM và toolchain JDK là hai cấu hình khác nhau

Gradle daemon JVM là JVM chạy Gradle. Java toolchain là JDK được chọn cho task Java. Có thể khác nhau:

~~~text
Gradle Wrapper
      |
      v
Gradle daemon (JDK 17)
      |
      +---- JavaCompile toolchain (JDK 21)
      |
      +---- Test task JavaLauncher (JDK 21)
~~~

Nếu Gradle daemon không khởi động được vì JDK không tương thích, toolchain không thể sửa lỗi đó vì toolchain chỉ được chọn sau khi Gradle đã chạy. Phải chọn JVM hỗ trợ cho Gradle trước, rồi chọn toolchain cho task Java.

### 6.5. Kiểm tra toolchain được phát hiện

Với Java plugin, có thể dùng task:

~~~bash
./gradlew javaToolchains
~~~

Task này liệt kê các Java toolchain Gradle phát hiện được. Nếu toolchain mong muốn không xuất hiện, kiểm tra JDK installation path, JAVA_HOME, cấu hình Gradle toolchain resolver và quyền truy cập của CI runner.

## 7. Maven Toolchains

### 7.1. Maven JVM và compiler JDK

Maven Wrapper cố định Maven distribution, nhưng Maven process vẫn cần một JDK để chạy. Mặc định, Maven Compiler Plugin thường dùng compiler thuộc JDK đang chạy Maven. Nếu muốn dùng một JDK khác, có thể cấu hình Maven Toolchains và plugin hỗ trợ toolchain.

Ví dụ Maven process chạy bằng JDK 21, nhưng project muốn compiler JDK 17. Maven Toolchains có thể chọn JDK 17 cho compiler plugin, trong khi Maven vẫn chạy trên JDK 21.

### 7.2. Khai báo JDK trong toolchains.xml

Toolchain installation thường được khai báo trong file người dùng ~/.m2/toolchains.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Đường dẫn /opt/jdks/temurin-17 chỉ là ví dụ. Trên máy lập trình viên, đường dẫn có thể khác; trên Windows, nó có thể nằm ở thư mục cài JDK tương ứng. Không nên commit đường dẫn tuyệt đối của một máy cá nhân vào POM dùng chung.

### 7.3. Chọn toolchain trong POM

Ví dụ cấu hình Maven Toolchains Plugin:

~~~xml
<build>
    <plugins>
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
                        <version>17</version>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Plugin tìm toolchain phù hợp trong cấu hình cục bộ và đặt nó làm toolchain được chọn cho các plugin hỗ trợ. Cần bảo đảm JDK đã được khai báo, version/vendor khớp và các plugin như compiler/test runner thực sự sử dụng toolchain.

### 7.4. Cấu hình Java release cho compiler

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Toolchain chọn JDK compiler; release xác định Java API/bytecode mục tiêu. Nếu compiler JDK không hỗ trợ release được chỉ định, compile sẽ thất bại. Dependency bên ngoài cũng cần tương thích với release đó.

### 7.5. Giới hạn của Maven Toolchains

Không phải mọi Maven plugin đều tự động dùng toolchain. Plugin phải hỗ trợ Maven Toolchains hoặc được cấu hình để dùng JDK/executable phù hợp. Maven process vẫn chạy bằng JVM được chọn qua môi trường/CI. Vì vậy, cần kiểm tra từng plugin quan trọng và test runtime nếu dự án yêu cầu nhiều JDK khác nhau.

## 8. Xây dựng chính sách Java thống nhất cho team

Một dự án nên ghi rõ ba mức Java:

| Mức | Câu hỏi | Ví dụ chính sách |
|---|---|---|
| Build JVM | JDK nào đủ điều kiện chạy Gradle/Maven và plugin? | JDK 17 hoặc JDK 21 theo Gradle/Maven version được chọn |
| Compiler toolchain | JDK nào dùng để compile/test task? | JDK 21 |
| Runtime target | Ứng dụng/thư viện hỗ trợ runtime thấp nhất nào? | Java 17 |

Nếu build và runtime target cùng là Java 21, cấu hình có thể đơn giản hơn. Nhưng vẫn cần xác định build tool có thể chạy trên JDK nào và test đang dùng launcher nào.

### 8.1. Ghi chính sách trong README hoặc tài liệu đóng góp

Hướng dẫn phát triển nên ghi:

- JDK cần cài để chạy build tool.
- JDK/toolchain dùng để compile và test.
- Java release mà artifact hỗ trợ.
- Lệnh Wrapper trên Windows và Unix.
- Cách kiểm tra version.
- Cách cập nhật Wrapper/toolchain.
- Các biến môi trường hoặc cấu hình IDE cần thiết.

Ví dụ:

~~~text
Build tool: Gradle Wrapper (version pinned in gradle-wrapper.properties)
Build JVM: JDK 17 or newer, subject to the selected Gradle version
Java toolchain: JDK 21
Java release target: 17

Linux/macOS: ./gradlew build
Windows:     gradlew.bat build
~~~

Đây là mẫu minh họa. Dự án phải ghi version và yêu cầu tương thích thật của mình, không để cụm newer thay thế một chính sách rõ ràng nếu plugin hoặc runtime cần giới hạn cụ thể.

### 8.2. IDE phải dùng đúng Wrapper và JDK

IDE có thể có Project SDK và Gradle JVM/Maven importer JDK riêng. Khi build bằng IDE:

- Chọn project SDK phù hợp với yêu cầu phát triển.
- Cấu hình IDE dùng Gradle Wrapper của project thay vì Gradle cài toàn cục.
- Chọn Gradle JVM tương thích với Gradle version.
- Với Maven, bật sử dụng Maven Wrapper nếu IDE hỗ trợ và chọn importer/runner JDK phù hợp.
- Đồng bộ lại project sau khi thay đổi Wrapper, toolchain hoặc dependency.
- Nếu IDE chạy compiler riêng, kiểm tra language level và annotation processing có khớp build tool không.

Nếu terminal build thành công nhưng IDE báo lỗi, hãy so sánh cấu hình SDK và build delegation trước khi sửa POM/build script.

## 9. Cấu hình CI sử dụng Wrapper và toolchain

CI nên thực hiện các bước theo thứ tự có thể dự đoán:

1. Checkout đúng commit.
2. Cài JDK dùng để chạy build tool.
3. Cài hoặc cung cấp JDK/toolchain mà project yêu cầu.
4. Kiểm tra wrapper files và quyền thực thi.
5. Chạy wrapper để xác nhận build tool version.
6. Chạy build/test bằng cùng command được tài liệu hóa.
7. Lưu test report và artifact.

### 9.1. Ví dụ pipeline Gradle dạng tổng quát

~~~yaml
steps:
  - name: Checkout source
    run: checkout-current-commit

  - name: Set up build JDK
    run: install-jdk 17

  - name: Set up Java toolchain
    run: install-jdk 21

  - name: Show build environment
    run: |
      java -version
      ./gradlew --version
      ./gradlew javaToolchains

  - name: Verify
    run: ./gradlew build

  - name: Publish test reports
    run: upload-test-reports
~~~

Đây là pseudoconfiguration thể hiện thứ tự và ý nghĩa bước, không phải file YAML có thể chạy trực tiếp trên một nhà cung cấp CI cụ thể. Các lệnh checkout-current-commit, install-jdk và upload-test-reports cần được thay bằng action/task tương ứng của hệ thống CI.

Nếu build JVM và compiler toolchain cùng một JDK, chỉ cần cài một JDK phù hợp. Nếu khác nhau, cài cả hai và xác nhận Gradle toolchain thực sự chọn JDK dự kiến.

### 9.2. Ví dụ pipeline Maven dạng tổng quát

~~~yaml
steps:
  - name: Checkout source
    run: checkout-current-commit

  - name: Set up Maven build JVM
    run: install-jdk 21

  - name: Set up compiler toolchain JDK
    run: install-jdk 17

  - name: Configure Maven toolchain
    run: create-user-toolchains-xml

  - name: Show environment
    run: |
      java -version
      ./mvnw --version

  - name: Verify
    run: ./mvnw -B -ntp verify

  - name: Publish reports
    run: upload-test-reports
~~~

Đây cũng là pseudoconfiguration. Bước tạo toolchains.xml phải ghi đúng đường dẫn JDK trên runner và không đưa đường dẫn riêng của máy cá nhân vào repository.

### 9.3. Chạy đúng wrapper trong CI

Không nên cài Gradle/Maven toàn cục rồi gọi trực tiếp:

~~~bash
gradle build
mvn verify
~~~

Hãy dùng:

~~~bash
./gradlew build
./mvnw -B -ntp verify
~~~

Với Windows runner, dùng gradlew.bat và mvnw.cmd. Việc này bảo đảm CI lấy build tool version từ repository giống máy lập trình viên.

### 9.4. Không tắt test để làm pipeline xanh

Không dùng -x test, -DskipTests hoặc -Dmaven.test.skip=true như cách xử lý mặc định cho lỗi CI. Các tùy chọn đó có thể làm pipeline báo thành công trong khi kiểm thử không được thực hiện hoặc không được biên dịch. Hãy xử lý nguyên nhân test thất bại và chỉ bỏ qua test trong một job được thiết kế rõ ràng, có chính sách kiểm chứng khác.

## 10. Cache trong CI mà vẫn giữ tính nhất quán

Wrapper và toolchain giải quyết version, còn cache giúp giảm thời gian tải distribution, dependency và output build. Cache không nên làm thay đổi yêu cầu build.

### 10.1. Gradle cache

Gradle có các vùng cache khác nhau:

- Gradle distribution do Wrapper tải.
- Dependency cache trong Gradle User Home.
- Build cache cho output task cacheable.
- Configuration cache cho kết quả cấu hình build.

CI có thể lưu cache Gradle User Home hoặc dùng cơ chế cache tích hợp của nền tảng. Cache key nên phản ánh các yếu tố ảnh hưởng như hệ điều hành, Wrapper, JDK hoặc dependency lock/configuration theo chính sách dự án.

Không nên cache thư mục output build một cách tùy tiện nếu chưa hiểu quan hệ input/output và cách task incremental hoạt động. Gradle build cache được thiết kế để tái sử dụng output task theo cache key, khác với việc copy nguyên thư mục build cũ sang runner khác.

### 10.2. Maven cache

Maven thường lưu dependency và plugin đã tải trong local repository, mặc định là ~/.m2/repository. CI có thể cache local repository để giảm tải lại artifact.

Cache key có thể dựa trên hệ điều hành, JDK, POM và các file quản lý dependency/plugin. Nếu dependency thay đổi, cache vẫn cần được kiểm tra qua metadata/repository; không nên coi việc artifact đã có trong cache là bằng chứng version hoặc nội dung luôn đúng.

### 10.3. Cache không thay thế Wrapper/toolchain

Một runner có thể khôi phục dependency cache từ job trước nhưng vẫn phải dùng đúng Wrapper và JDK. Cache chỉ là tối ưu hiệu năng. Nếu cache bị miss, build vẫn phải có thể chạy đúng từ cấu hình và repository đã khai báo.

Khi nghi ngờ cache làm sai kết quả, thử build trong môi trường sạch hoặc tắt cache có chủ đích để chẩn đoán, ghi lại điều kiện và so sánh output. Không xóa cache dùng chung của tổ chức nếu chưa có lý do và quyền phù hợp.

## 11. Ma trận kiểm tra local và CI

Một bảng kiểm tra đơn giản giúp phát hiện sai lệch:

| Thành phần | Máy cá nhân | CI | Cần đồng nhất? |
|---|---|---|---|
| Wrapper distribution | Đọc từ repository | Đọc từ cùng repository | Có |
| Build JVM | JDK đáp ứng yêu cầu build tool | JDK đáp ứng cùng yêu cầu | Phải tương thích; có thể khác vendor/patch nếu chính sách cho phép |
| Compiler toolchain | Theo build configuration | Theo cùng build configuration | Nên cùng version/vendor nếu muốn kết quả ổn định cao |
| Java release target | Theo build file/POM | Theo cùng build file/POM | Có |
| Plugin version | Theo build file/POM | Theo cùng build file/POM | Có |
| Dependency graph | Theo constraints/locks | Theo cùng constraints/locks | Có |
| OS/architecture | Theo máy phát triển | Theo runner | Có thể khác, nhưng phải kiểm tra nếu có native dependency |
| Environment variables | Giá trị local | Giá trị CI | Cần cùng semantics, không nhất thiết cùng giá trị |
| Secrets | Lấy từ cơ chế local an toàn | Lấy từ secret store CI | Không commit hoặc in ra log |

Không phải mọi máy phải có cùng OS hoặc cùng patch level JDK trong mọi dự án. Nhưng mọi khác biệt có thể ảnh hưởng compile, test hoặc artifact cần được hiểu và ghi nhận. Nếu mục tiêu là byte-for-byte reproducibility, cần kiểm soát môi trường chặt hơn so với mục tiêu chỉ cần build/test tương thích.

## 12. Nâng cấp Wrapper và toolchain theo quy trình

Nâng cấp Gradle/Maven hoặc JDK có thể ảnh hưởng plugin, dependency, compiler, test engine và bytecode. Không nên thay nhiều version cùng lúc rồi khó xác định thay đổi nào gây lỗi.

Quy trình đề xuất:

1. Chọn version mục tiêu dựa trên yêu cầu plugin/framework và hỗ trợ JDK.
2. Kiểm tra Gradle/Maven version đó có chạy được trên build JVM dự kiến không.
3. Cập nhật Wrapper files bằng quy trình chuẩn.
4. Cập nhật toolchain và release target nếu có thay đổi.
5. Chạy --version và xác nhận JDK thực tế.
6. Chạy compile, test và verify trên máy cá nhân.
7. Chạy cùng command trên CI.
8. Review warning/deprecation, plugin compatibility và dependency graph.
9. Lưu thay đổi Wrapper/toolchain trong một commit hoặc pull request có mô tả rõ.

Nếu có thể, tách nâng cấp build tool khỏi nâng cấp Java release. Điều đó giúp xác định phạm vi thay đổi và giảm số nguyên nhân có thể gây lỗi.

## 13. Chẩn đoán các lỗi thường gặp

| Thông báo/hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| JAVA_HOME is set to an invalid directory | JAVA_HOME trỏ sai hoặc thư mục không phải JDK hợp lệ | In JAVA_HOME, kiểm tra bin/java và bin/javac |
| Gradle không khởi động trên JDK hiện tại | Gradle Wrapper version không hỗ trợ JVM chạy Gradle | ./gradlew --version, đối chiếu yêu cầu JVM của Gradle |
| invalid source release | Compiler JDK cũ hơn Java release yêu cầu | Kiểm tra toolchain và compiler release |
| Không tìm thấy toolchain phù hợp | JDK chưa cài hoặc Gradle không nhận diện | ./gradlew javaToolchains, kiểm tra installation path/resolver |
| Maven chạy JDK khác với compiler mong muốn | Chưa cấu hình hoặc không tìm thấy Maven toolchain | ./mvnw --version, toolchains.xml, plugin hỗ trợ toolchain |
| Local build được, CI lỗi compiler | CI cài sai JDK hoặc toolchain chưa được provision | In version, kiểm tra setup step và toolchain config |
| IDE build được, terminal lỗi | IDE dùng JDK/build tool khác | So sánh Project SDK, Gradle JVM/Maven importer và Wrapper |
| CI dùng Gradle/Maven khác dự án | Pipeline gọi executable toàn cục | Thay bằng ./gradlew hoặc ./mvnw |
| Wrapper không tải được distribution | URL, proxy, TLS, checksum hoặc network | Kiểm tra distributionUrl, network và checksum nguồn |
| Permission denied với gradlew/mvnw | Thiếu executable bit trên Unix | Kiểm tra Git mode và chmod +x |
| Maven compiler vẫn dùng JDK không mong muốn | Plugin không nhận toolchain hoặc fork executable riêng | Kiểm tra plugin config và toolchain support |
| Cache restore nhưng build vẫn tải lại | Cache key không khớp hoặc cache không chứa artifact cần thiết | Kiểm tra cache key, log cache và dependency resolution |

### 13.1. Quy trình xử lý local/CI khác nhau

Khi local build thành công nhưng CI thất bại:

1. Xác nhận CI checkout đúng commit.
2. Kiểm tra CI gọi Wrapper hay build tool toàn cục.
3. In build tool version bằng ./gradlew --version hoặc ./mvnw --version.
4. In Java version và kiểm tra JDK/toolchain được chọn.
5. So sánh compiler release, plugin version và dependency graph.
6. Kiểm tra profiles, project properties, environment variables và working directory.
7. Kiểm tra network, repository, credentials và cache.
8. Chạy lại đúng command trong môi trường tương đương CI.

Không nên ngay lập tức đổi Java version hoặc xóa cache. Trước tiên hãy thu thập bằng chứng để biết sự khác biệt nằm ở Wrapper, JVM, toolchain hay dependency.

## 14. Ví dụ hoàn chỉnh: Gradle Wrapper và Java toolchain

Giả sử dự án cần Gradle 8.10.2, dùng JDK 21 để compile/test và hỗ trợ runtime Java 17.

### 14.1. Wrapper

gradle/wrapper/gradle-wrapper.properties:

~~~properties
distributionUrl=https://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=<checksum-da-xac-minh>
~~~

Các file gradlew, gradlew.bat và gradle-wrapper.jar được commit cùng repository.

### 14.2. Build configuration

build.gradle.kts:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

### 14.3. Máy cá nhân

Máy lập trình viên cần có JDK tương thích để chạy Gradle 8.10.2 và JDK 21 để toolchain compile/test. Nếu JDK 21 được cài nhưng không được Gradle nhận diện, cần cấu hình installation path hoặc toolchain resolver theo chính sách dự án.

Chạy:

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew build
~~~

### 14.4. CI

Runner cài JDK phù hợp để chạy Gradle và JDK 21 cho toolchain. Sau đó gọi:

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew build
~~~

CI không cần tự cài Gradle 8.10.2 toàn cục vì Wrapper tải đúng distribution. Nếu build JVM cũng là JDK 21, có thể chỉ cần một JDK installation.

Khi build thành công ở cả hai môi trường, vẫn cần xác nhận test và runtime target Java 17 bằng môi trường chạy phù hợp. Toolchain JDK 21 không tự chứng minh ứng dụng chạy được trên Java 17.

## 15. Ví dụ hoàn chỉnh: Maven Wrapper và Maven Toolchains

Giả sử dự án cần Maven 3.9.9, Maven process chạy trên JDK 21, compiler dùng JDK 17 và artifact hỗ trợ Java 17.

### 15.1. Maven Wrapper

.mvn/wrapper/maven-wrapper.properties:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=<checksum-da-xac-minh>
~~~

Các script và file Wrapper cần được commit. Thuộc tính checksum cần được xác nhận là được Wrapper version đang dùng hỗ trợ.

### 15.2. Compiler release

pom.xml:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

### 15.3. Toolchain installation

Trên mỗi máy, cấu hình ~/.m2/toolchains.xml để trỏ đến JDK 17 đã cài. CI tạo file tương ứng từ đường dẫn JDK trên runner. POM chỉ yêu cầu version/vendor, không phụ thuộc đường dẫn tuyệt đối của một máy cụ thể.

### 15.4. Chạy và xác nhận

~~~bash
java -version
./mvnw --version
./mvnw -B -ntp verify
~~~

./mvnw --version xác nhận Maven process đang chạy bằng JDK dự kiến. Cấu hình toolchain và log compiler cần được kiểm tra để xác nhận Maven Compiler Plugin thực sự dùng JDK 17. Sau đó chạy test trên runtime mục tiêu nếu cần bảo đảm khả năng chạy Java 17.

## 16. Bảo mật và độ tin cậy của Wrapper

Wrapper là mã được thực thi trong quá trình bootstrap build. Vì vậy, thay đổi wrapper files cần được review như thay đổi build script hoặc dependency.

Các nguyên tắc:

- Commit wrapper scripts, JAR và properties của project.
- Review thay đổi distributionUrl, Wrapper JAR và các script.
- Dùng HTTPS và nguồn distribution đáng tin cậy.
- Cấu hình checksum khi phiên bản Wrapper hỗ trợ và có checksum chính thức.
- Kiểm tra wrapper JAR bằng validation trong CI nếu tổ chức có quy trình đó.
- Không chạy Wrapper từ một pull request không đáng tin cậy với secrets có quyền cao.
- Giới hạn quyền token CI và tách job build không tin cậy khỏi job phát hành.
- Không in credentials hoặc secret trong log build.

Việc kiểm tra checksum distribution giúp xác nhận file tải về khớp giá trị tham chiếu. Nó không thay thế review source của Wrapper JAR hoặc bảo vệ toàn bộ pipeline nếu nguồn checksum bị xâm phạm. Cần bảo vệ cả repository, nguồn phát hành và quyền CI.

## 17. Những sai lầm thường gặp

- **Gọi gradle/mvn toàn cục trong CI.** Build có thể dùng version khác repository; dùng Wrapper của project.
- **Cho rằng Wrapper cố định JDK.** Wrapper chỉ cố định build tool distribution; cần cấu hình build JVM và compiler toolchain riêng.
- **Cho rằng toolchain chọn JVM chạy Gradle.** Toolchain phục vụ task Java; Gradle daemon cần JVM tương thích riêng.
- **Chỉ kiểm tra java -version.** IDE, daemon, compiler và test worker có thể dùng JDK khác nhau.
- **Đặt source/target mà không xem API mục tiêu.** Dùng --release hoặc cấu hình release phù hợp khi cần tương thích Java SE.
- **Commit đường dẫn JDK tuyệt đối của máy cá nhân.** Dùng toolchain metadata chung và cấu hình installation cục bộ/CI riêng.
- **Giả định Gradle tự tải mọi JDK.** Cần cài sẵn hoặc cấu hình resolver/provisioning.
- **Cho rằng mọi Maven plugin tự dùng toolchain.** Kiểm tra plugin support và executable thực tế.
- **Chỉ cập nhật distributionUrl.** Review toàn bộ Wrapper files và kiểm tra version sau cập nhật.
- **Tắt test để giải quyết lỗi CI.** Điều đó che giấu vấn đề và làm giảm mức kiểm chứng.
- **Coi cache là yêu cầu bắt buộc để build thành công.** Build phải có thể chạy đúng khi cache miss.
- **Dùng checksum placeholder trong cấu hình.** Chỉ commit checksum đã xác minh từ nguồn tin cậy.

## 18. Bài tập vận dụng

Một project Gradle chạy được trên máy cá nhân nhưng CI báo lỗi Unsupported class file major version. Máy cá nhân dùng ./gradlew và JDK 21; CI cài Gradle toàn cục, gọi gradle build và dùng JDK 17. Build file có Java toolchain 21.

Hãy xác định:

1. CI đang bỏ qua cơ chế nào của repository?
2. Wrapper giải quyết vấn đề phiên bản Gradle như thế nào?
3. Vì sao cài JDK 21 cho toolchain chưa chắc đủ nếu Gradle daemon vẫn chạy trên JDK không tương thích?
4. Cần kiểm tra ./gradlew --version và ./gradlew javaToolchains để xác nhận điều gì?
5. Nếu muốn build bằng JDK 21 nhưng hỗ trợ runtime Java 17, cấu hình options.release ra sao?
6. Maven Wrapper và Maven Toolchains giải quyết hai lớp nào?
7. Vì sao không nên commit đường dẫn JDK tuyệt đối trong toolchains.xml hoặc POM?
8. CI cần cài JDK nào nếu Maven process chạy trên JDK 21 nhưng compiler toolchain dùng JDK 17?
9. Những file Gradle Wrapper/Maven Wrapper nào cần commit?
10. Checksum distribution và wrapper validation bảo vệ những thành phần nào?
11. Vì sao cache không thay thế Wrapper và toolchain?
12. Nếu IDE vẫn dùng JDK khác terminal, cần kiểm tra cấu hình nào?

Có thể thực hành bằng một project Gradle nhỏ: commit Wrapper, cấu hình toolchain, in --version và javaToolchains, sau đó chạy cùng lệnh từ terminal và CI. Với Maven, tạo Wrapper, cấu hình compiler release và Maven Toolchains, rồi xác nhận Maven JVM khác compiler JDK như dự định.

## 19. Quy trình chuẩn hóa cho nhóm phát triển

Một quy trình đơn giản có thể áp dụng cho mọi project:

1. Tạo và commit Gradle Wrapper hoặc Maven Wrapper.
2. Chọn build tool version tương thích với plugin/framework và JDK được hỗ trợ.
3. Xác định JDK chạy build tool.
4. Cấu hình toolchain/compiler JDK và Java release target.
5. Ghi hướng dẫn cài JDK, lệnh Wrapper và cấu hình IDE.
6. Cấu hình CI cài đúng JDK, sau đó gọi Wrapper.
7. In build tool version và Java version trong log CI.
8. Kiểm tra dependency/plugin version và cache policy.
9. Chạy cùng task/phase trên máy cá nhân và CI.
10. Nâng cấp Wrapper/JDK bằng thay đổi có review và kiểm thử.

## 20. Nguyên tắc duy trì lâu dài

- Dùng Wrapper đã commit làm entry point chính cho local và CI.
- Pin build tool distribution và xác minh tính toàn vẹn của distribution khi có thể.
- Phân biệt JVM chạy Gradle/Maven với JDK compiler/toolchain.
- Cấu hình Java toolchain hoặc Maven Toolchains để chọn compiler có chủ đích.
- Đặt release target rõ ràng và kiểm tra dependency có hỗ trợ target đó.
- Đồng bộ IDE với Wrapper và chính sách JDK của dự án.
- Cài JDK cần thiết trong CI trước khi chạy build.
- Không commit đường dẫn JDK riêng của máy hoặc bí mật vào repository.
- Dùng cache như tối ưu hiệu năng, không làm điều kiện bắt buộc để build đúng.
- Kiểm tra version, toolchain và dependency graph khi local/CI có kết quả khác nhau.
- Nâng cấp build tool và JDK theo quy trình có review, kiểm thử và ghi nhận.

Build nhất quán bắt đầu từ việc mọi người dùng cùng Wrapper và cùng chính sách Java. Wrapper cố định Gradle/Maven distribution; toolchain chọn JDK cho compiler và các task Java; release target xác định mức Java mà artifact phải hỗ trợ. Khi ba yếu tố này được ghi rõ và CI chạy đúng script của repository, sự khác biệt giữa máy cá nhân và CI sẽ dễ phát hiện, giải thích và kiểm soát hơn.
