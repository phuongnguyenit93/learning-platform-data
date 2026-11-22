# Khai báo phiên bản JDK và toolchain có thể tái lập

## Mục tiêu

Một build Java đáng tin cậy cần xác định rõ JDK nào được dùng để biên dịch, chạy test và đóng gói artifact. Chỉ đặt `JAVA_HOME` hoặc ghi “dùng Java 21” trong tài liệu chưa đủ: máy developer, CI runner và môi trường release có thể đang dùng các JDK vendor hoặc bản cập nhật khác nhau.

Java 21 cung cấp nền tảng cho các dự án hiện đại, nhưng tính tái lập của build còn phụ thuộc vào build tool, wrapper, compiler options, dependency và cách CI cài đặt JDK. Bài học này trình bày cách khai báo toolchain cho Gradle và Maven, ghim phiên bản build tool, phân biệt JDK chạy build với JDK dùng cho compilation/test và kiểm tra cấu hình thực tế.

## 1. Phân biệt JDK chạy build và JDK toolchain

Một quy trình build có thể sử dụng nhiều JDK với vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| JDK chạy Maven/Gradle | Chạy chính build tool và các plugin của nó |
| Java compiler toolchain | Cung cấp `javac` dùng biên dịch source |
| Java launcher toolchain | Cung cấp JVM chạy test hoặc Java task |
| Runtime triển khai | JVM thực thi artifact trong production |

Các vai trò này có thể cùng dùng một bản JDK, nhưng không nên mặc định chúng luôn giống nhau. Ví dụ, Gradle có thể chạy trên một JDK được CI cài sẵn và dùng Java toolchain 21 để biên dịch, test. Maven cũng có thể chạy trên một JDK và chọn compiler JDK riêng qua Maven Toolchains.

Để build có thể tái lập, cần khai báo rõ:

- Phiên bản Java feature cần dùng, ví dụ 21.
- Vendor hoặc distribution cần dùng nếu tổ chức yêu cầu.
- Phiên bản và distribution của Maven/Gradle.
- Compile release target, ví dụ `--release 21`.
- Cách CI cài đặt và xác minh đúng JDK.
- Dependency và plugin versions được ghim theo chính sách dự án.

## 2. Vì sao chỉ đặt `JAVA_HOME` chưa đủ?

`JAVA_HOME` và `PATH` xác định JDK mà shell thường gọi khi chạy `java`, `javac` hoặc build tool. Chúng không phải khai báo toolchain đầy đủ cho mọi project.

Ví dụ, hai developer cùng đặt `JAVA_HOME` trỏ đến Java 21 nhưng một người dùng Temurin và người kia dùng Oracle JDK. Cả hai có cùng feature version nhưng khác vendor, bản cập nhật, build metadata hoặc cách đóng gói. CI runner cũng có thể tự động đổi JDK mặc định khi image được cập nhật.

Ngoài ra:

- Build tool có thể được khởi chạy bởi một JDK khác với compiler được chọn cho project.
- Một số task có thể dùng Java launcher riêng để chạy test hoặc công cụ.
- `JAVA_HOME` không ghim phiên bản Maven/Gradle.
- `JAVA_HOME` không ghim dependency, plugin hoặc nội dung của container image.

Vì vậy, dùng `JAVA_HOME` để chọn JDK cho tiến trình build là cần thiết, nhưng project vẫn nên khai báo toolchain và wrapper để mô tả yêu cầu một cách tường minh.

## 3. Khai báo Java 21 toolchain trong Gradle

Với Gradle Java Plugin, khai báo toolchain trong `build.gradle.kts`:

```kotlin
import org.gradle.jvm.toolchain.JvmVendorSpec

plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 21
}
```

Trong cấu hình này:

- `languageVersion` yêu cầu JDK có Java feature version 21.
- `vendor` giới hạn vendor theo yêu cầu dự án; ví dụ dùng Eclipse Temurin thông qua Gradle vendor spec `ADOPTIUM`.
- `options.release = 21` giới hạn source language, class-file target và Java SE API ở Java 21.

Nếu dự án không bắt buộc vendor cụ thể, có thể bỏ `vendor` để Gradle chọn một JDK cục bộ phù hợp với toolchain requirement. Dù vậy, CI nên xác định rõ nguồn JDK để tránh mỗi runner chọn một distribution khác nhau ngoài dự kiến.

Java toolchain được Java Plugin sử dụng cho các task Java tiêu chuẩn như compile, test và Javadoc. Với task tự tạo hoặc plugin bên ngoài, hãy kiểm tra task đó có thực sự dùng Gradle toolchain hay đang tự tìm `JAVA_HOME`/`java` trên `PATH`.

## 4. Chọn Java launcher riêng cho test hoặc task cụ thể

Toolchain có thể cung cấp launcher cho task cần chạy JVM. Ví dụ, cấu hình một task `Test` dùng Java 21 rõ ràng:

```kotlin
import org.gradle.api.tasks.testing.Test

tasks.withType<Test>().configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Trong dự án thông thường, cấu hình `java.toolchain` ở phần trước đã đủ để Java Plugin chọn compiler và launcher phù hợp. Chỉ khai báo launcher riêng khi cần một task chạy trên phiên bản Java khác với mặc định của project, hoặc khi cấu hình test cần được thể hiện tường minh.

Không nên cấu hình riêng từng task một cách lặp lại nếu tất cả đều dùng cùng toolchain. Cấu hình tập trung giúp tránh tình trạng compile bằng Java 21 nhưng test lại vô tình chạy trên một runtime khác.

## 5. Phân biệt toolchain feature version với bản cập nhật JDK chính xác

`JavaLanguageVersion.of(21)` ghim Java feature version 21. Nó không nhất thiết ghim chính xác bản cập nhật, ví dụ 21.0.x, build number hoặc vendor patch level.

Nếu yêu cầu chỉ là “dùng Java 21”, feature version có thể đủ. Nếu cần kết quả build nhất quán giữa các runner, hãy kiểm soát cả:

- Vendor/distribution, chẳng hạn Temurin hoặc Oracle JDK.
- Bản cập nhật JDK cụ thể được tổ chức phê duyệt.
- Nguồn tải và checksum của JDK archive, hoặc immutable container image digest.
- Chính sách cập nhật bảo mật và lịch nâng bản JDK.

Không nên ghim một bản JDK cũ vô thời hạn chỉ để có build giống nhau. Hãy cập nhật bản vá bảo mật theo quy trình có kiểm thử, sau đó ghi lại phiên bản mới trong cấu hình CI. Tính tái lập có nghĩa là biết chính xác build dùng gì và có thể dựng lại cùng cấu hình, đồng thời vẫn duy trì chính sách cập nhật an toàn.

Gradle mặc định dò tìm các JDK đã cài trên máy. Việc tự tải một JDK phù hợp khi không tìm thấy toolchain cần cấu hình toolchain resolver/repository tương ứng; chỉ khai báo `languageVersion` không đồng nghĩa Gradle luôn tải JDK từ Internet. Nếu dùng resolver, hãy ghim và quản lý plugin/repository resolver như một phần của build configuration.

## 6. Khai báo toolchain trong Maven

Maven có cơ chế Toolchains để chọn JDK compiler khác với JDK chạy Maven. Thông tin đường dẫn cài JDK thường được khai báo trong file người dùng `~/.m2/toolchains.xml`; không nên commit đường dẫn cài đặt riêng của một máy developer vào repository.

Ví dụ `toolchains.xml` cho JDK 21:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

`jdkHome` phải trỏ đến JDK thực tế trên máy hoặc CI runner. Giá trị `/opt/jdks/temurin-21` chỉ là ví dụ; mỗi môi trường cần provision JDK vào một đường dẫn đã biết rồi tạo toolchain mapping tương ứng.

Trong `pom.xml`, khai báo yêu cầu toolchain và compile release:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <maven-toolchains-plugin.version>3.2.0</maven-toolchains-plugin.version>
    <maven-compiler-plugin.version>3.13.0</maven-compiler-plugin.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>${maven-toolchains-plugin.version}</version>
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
                        <version>21</version>
                        <vendor>temurin</vendor>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>${maven-compiler-plugin.version}</version>
            <configuration>
                <release>${maven.compiler.release}</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Maven Toolchains Plugin chọn JDK phù hợp từ `toolchains.xml`. Maven Compiler Plugin có thể dùng toolchain đã chọn để chạy compiler. `maven.compiler.release` vẫn cần được khai báo để kiểm soát API Java SE và class-file target; chỉ chọn JDK 21 không thay thế cấu hình release.

Các version plugin trong ví dụ cần được quản lý tập trung và cập nhật theo chính sách của dự án. Khi nâng plugin, hãy kiểm tra yêu cầu Maven/JDK và chạy lại pipeline.

## 7. JDK chạy Maven vẫn cần được kiểm soát

Maven Toolchains chọn JDK cho các plugin hỗ trợ toolchain, nhưng Maven core và các plugin khác vẫn chạy trong JVM đã khởi chạy Maven. Vì vậy, `toolchains.xml` không làm cho mọi plugin tự động chạy trên JDK 21.

Kiểm tra Maven runtime bằng:

```bash
./mvnw -version
```

Output cho biết phiên bản Maven và Java runtime đang dùng. Nếu project yêu cầu Maven chạy trên Java 21, CI phải khởi chạy wrapper bằng JDK 21. Nếu compiler toolchain cũng là Java 21, hãy kiểm tra riêng rằng Maven Compiler Plugin đã chọn đúng JDK đó.

Không nhầm `mvn -version` hiển thị Java 21 với bằng chứng duy nhất rằng compiler, test launcher và mọi plugin đều dùng cùng JDK. Hãy kiểm tra log build hoặc cấu hình task/plugin tương ứng.

## 8. Ghim phiên bản build tool bằng Wrapper

Toolchain ghim JDK, còn Wrapper ghim phiên bản build tool. Dự án nên commit các file wrapper cần thiết để developer và CI gọi cùng một phiên bản Maven hoặc Gradle.

Với Gradle, dùng:

```bash
./gradlew --version
./gradlew clean test build
```

Các file wrapper thường được commit gồm `gradlew`, `gradlew.bat`, thư mục `gradle/wrapper/` và `gradle-wrapper.properties`. Trong `gradle-wrapper.properties`, khai báo distribution URL và checksum:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-<approved-version>-bin.zip
distributionSha256Sum=<official-distribution-sha256>
```

Thay placeholder bằng phiên bản Gradle và SHA-256 được phê duyệt từ nguồn phát hành chính thức. Checksum giúp Wrapper xác minh distribution tải về đúng nội dung mong đợi.

Với Maven, dùng Maven Wrapper:

```bash
./mvnw --version
./mvnw clean verify
```

Maven Wrapper lưu phiên bản Maven trong `.mvn/wrapper/maven-wrapper.properties`. Có thể ghim checksum distribution bằng thuộc tính `distributionSha256Sum` nếu Wrapper version của dự án hỗ trợ:

```properties
distributionUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/<approved-version>/apache-maven-<approved-version>-bin.zip
distributionSha256Sum=<official-distribution-sha256>
```

Không dùng lệnh `mvn` hoặc `gradle` cài toàn cục trong CI nếu mục tiêu là bảo đảm mọi runner dùng build tool đã ghim trong repository. Dùng `./mvnw` hoặc `./gradlew` (trên Windows có thể dùng `mvnw.cmd` hoặc `gradlew.bat`).

## 9. Provision JDK trong CI một cách nhất quán

CI cần cài hoặc lấy JDK từ một nguồn xác định trước khi chạy build. Một pipeline có thể thực hiện các bước:

1. Chọn image/runner có JDK distribution và patch level đã phê duyệt.
2. Xác minh `java -version` và `javac -version`.
3. Thiết lập `JAVA_HOME` và `PATH` cho JDK chạy build.
4. Nếu dùng Maven Toolchains, tạo `toolchains.xml` trỏ đến JDK compiler đã cài.
5. Chạy Maven/Gradle Wrapper của repository.
6. Kiểm tra toolchain compiler/launcher mà build tool thực sự chọn.
7. Chạy test và đóng gói artifact.

Với container CI, dùng image digest bất biến khi cần khóa chính xác image, thay vì chỉ dùng tag có thể được cập nhật. Nếu dùng action hoặc task cài JDK, chỉ định distribution và version rõ ràng, không dùng giá trị mặc định thay đổi theo runner.

Không commit secret, credential hoặc đường dẫn cài JDK của máy cá nhân. Các file cấu hình môi trường như `toolchains.xml` có thể được tạo trong CI từ biến môi trường hoặc bước provision JDK.

## 10. Kiểm tra toolchain thực tế

Không chỉ đọc cấu hình mà hãy xác nhận build tool thực sự chọn đúng JDK.

Các lệnh kiểm tra cơ bản:

```bash
java -version
javac -version
./gradlew --version
./mvnw --version
```

Chạy các lệnh phù hợp với build tool của project. Với Gradle, có thể dùng task chẩn đoán hoặc log task compile/test để kiểm tra compiler/launcher được chọn. Với Maven, xem log Maven Toolchains Plugin và compiler plugin để xác nhận JDK được chọn.

Sau khi biên dịch, kiểm tra class-file major version:

```bash
javap -verbose -classpath build/classes/java/main com.example.Main
```

Với Maven, đường dẫn output mặc định thường là `target/classes`; với Gradle Java Plugin thường là `build/classes/java/main`. Thay classpath và tên class theo project. Java 21 tạo class-file major version 65.

Kiểm tra class-file version xác nhận target bytecode, nhưng không chứng minh test đã chạy trên đúng JVM. Cần xác minh launcher riêng và chạy test trong runtime mục tiêu.

## 11. Reproducible build cần nhiều hơn JDK toolchain

Ghim JDK và Wrapper là nền tảng quan trọng, nhưng chưa đủ để bảo đảm hai build tạo ra artifact byte-for-byte giống nhau. Những yếu tố khác có thể làm kết quả thay đổi:

- Dependency hoặc plugin dùng version range, dynamic version hoặc snapshot thay đổi nội dung.
- Repository mirror trả về artifact khác nhau hoặc artifact không được xác minh checksum.
- Build phụ thuộc thời gian hệ thống, timezone, locale hoặc thứ tự file.
- Archive ghi timestamp hoặc metadata thay đổi giữa các lần build.
- Build script đọc biến môi trường hoặc file cục bộ không được khai báo.
- Annotation processor, code generator hoặc native tool không được ghim version.

Để tăng tính tái lập:

1. Ghim version plugin và dependency; tránh dynamic version trong build release.
2. Dùng dependency locking/verification phù hợp với build tool.
3. Ghim Wrapper distribution và xác minh checksum.
4. Provision JDK từ nguồn có version/checksum hoặc image digest rõ ràng.
5. Khai báo encoding, locale và timezone nếu build phụ thuộc chúng.
6. Tránh để build đọc file hoặc tool ngoài danh sách dependency đã quản lý.
7. Nếu cần byte-for-byte reproducibility, cấu hình archive timestamp/ordering và kiểm tra artifact hash giữa hai build độc lập.

Reproducible build là mục tiêu có mức độ. Một build có toolchain được ghim giúp tái tạo môi trường compiler/runtime; muốn artifact giống từng byte còn cần kiểm soát toàn bộ đầu vào build.

## 12. Chọn vendor và chính sách cập nhật

Java toolchain có thể giới hạn vendor. Gradle cung cấp `JvmVendorSpec` để chọn vendor phổ biến; Maven Toolchains dùng các thuộc tính `provides` để khớp yêu cầu với JDK đã đăng ký trong `toolchains.xml`.

Chỉ ghim vendor khi có lý do vận hành hoặc chứng nhận cụ thể, chẳng hạn:

- Tổ chức đã chuẩn hóa một JDK distribution.
- Cần tái hiện hành vi của môi trường production.
- Có yêu cầu support, compliance hoặc kiểm định từ vendor.
- Một provider/tool native phụ thuộc distribution nhất định.

Nếu không có yêu cầu đó, chọn vendor có thể làm giảm tính linh hoạt mà không tăng đáng kể độ tin cậy. Dù chọn vendor nào, hãy duy trì quy trình cập nhật security patch và kiểm tra tương thích trước khi nâng bản.

Không coi “Java 21” là một bản cài đặt duy nhất. Nên ghi nhận đầy đủ output của `java -version`, vendor, runtime build và toolchain compiler trong log CI để truy vết khi có khác biệt.

## 13. Những lỗi cấu hình thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ đặt `JAVA_HOME` | Compiler/test task có thể dùng JDK khác | Khai báo Gradle/Maven toolchain và kiểm tra task thực tế |
| Chỉ khai báo toolchain Java 21 | Không ghim patch level hoặc build tool version | Quản lý JDK distribution và Wrapper riêng |
| Dùng `sourceCompatibility`/`targetCompatibility` mà không đặt release | Có thể dùng API mới hơn runtime tối thiểu | Đặt `options.release` hoặc `maven.compiler.release` |
| Commit `toolchains.xml` có đường dẫn máy cá nhân | Build hỏng trên developer/CI khác | Provision JDK và tạo mapping theo môi trường |
| Dùng `mvn`/`gradle` global trong CI | Build tool version thay đổi theo runner | Dùng Maven/Gradle Wrapper |
| Dùng tag container có thể thay đổi | Cùng pipeline nhưng image có thể khác theo thời gian | Pin image digest hoặc JDK archive checksum |
| Nghĩ mọi Gradle task tự dùng toolchain | Plugin/task tùy chỉnh có thể gọi JDK trên PATH | Kiểm tra implementation và launcher của task |
| Nghĩ Maven Toolchains đổi JVM chạy Maven | Maven core/plugin vẫn chạy trên JVM khởi chạy Maven | Kiểm soát cả JDK chạy Maven và compiler toolchain |
| Ghim JDK cũ mà không cập nhật | Bỏ lỡ security patch | Có lịch cập nhật và chạy compatibility test |

## 14. Checklist build Java 21 có thể tái lập

Trước khi merge hoặc phát hành, hãy xác nhận:

1. Phiên bản JDK chạy build và vendor đã được xác định chưa?
2. Compiler toolchain có yêu cầu Java 21 rõ ràng không?
3. Compile release có được đặt thành `21` nếu artifact chỉ hỗ trợ Java 21 không?
4. Test launcher có chạy trên đúng runtime mục tiêu không?
5. Gradle/Maven Wrapper và distribution checksum đã được commit/cấu hình chưa?
6. Maven Toolchains có chọn đúng JDK trên từng CI runner không?
7. CI có xác minh `java -version`, compiler và build tool version không?
8. JDK patch level hoặc container image digest có được kiểm soát theo yêu cầu không?
9. Dependency, plugin và annotation processor có version được ghim không?
10. Có quy trình cập nhật JDK security patch và xác minh lại build không?
11. Nếu yêu cầu artifact byte-for-byte reproducible, có so sánh hash từ hai build độc lập không?

## Kết luận

Build Java 21 có thể tái lập cần khai báo rõ JDK toolchain, compile release, build tool Wrapper và cách CI provision runtime. Gradle dùng `java.toolchain`; Maven có thể dùng Maven Toolchains để chọn compiler JDK, trong khi JDK chạy Maven vẫn phải được kiểm soát riêng. `JAVA_HOME` là một phần của môi trường, không thay thế toolchain declaration. Hãy ghim version/vendor phù hợp, xác minh checksum hoặc image digest khi cần, kiểm tra compiler và test launcher thực tế, đồng thời duy trì quy trình cập nhật security patch. Những bước này giúp developer và CI tạo build nhất quán, dễ truy vết và có thể tái tạo.
