# Đồng bộ JDK giữa máy cá nhân, IDE và máy chạy CI

## 1. Mục tiêu và tình huống thực tế

Một dự án Spring Boot có thể build thành công trong terminal của lập trình viên, hiện lỗi đỏ trong IDE, rồi thất bại trên CI dù cùng một commit. Nguyên nhân phổ biến là **các môi trường đang dùng các JDK khác nhau**, hoặc đang nhầm JDK dùng để chạy công cụ build với JDK dùng để biên dịch và chạy ứng dụng.

Sau bài học, bạn có thể:

1. Phân biệt `JAVA_HOME`, JDK chạy Gradle/Maven, JDK biên dịch (toolchain), phiên bản Java mục tiêu và JDK chạy ứng dụng.
2. Chọn một phiên bản JDK phù hợp với Spring Boot, Gradle Wrapper hoặc Maven Wrapper hiện có, rồi khai báo rõ ràng trong project.
3. Kiểm tra và đồng bộ JDK trên máy Windows/Linux, trong IntelliJ IDEA hoặc IDE khác và trên GitHub Actions CI.
4. Đọc bằng chứng từ lệnh/nhật ký build, phát hiện lệch JDK và sửa đúng tầng cấu hình.
5. Phân biệt **tái lập bản dựng theo phiên bản Java** với **tái lập tuyệt đối từng byte** của artifact.

**Ví dụ xuyên suốt:** một nhóm chọn **Eclipse Temurin JDK 21** làm phiên bản chuẩn để xây dựng ứng dụng. Số `21` và nhà cung cấp Temurin là lựa chọn minh họa; khi áp dụng, ưu tiên phiên bản trong yêu cầu của **dự án thật**, không mặc định nâng dự án lên 21.

## 2. Bốn tầng phiên bản phải hiểu trước khi đồng bộ

| Tầng | Vai trò | Ai quyết định? | Cách kiểm tra |
| --- | --- | --- | --- |
| JDK của terminal / `JAVA_HOME` | JVM và `javac` được shell tìm thấy; thường dùng để khởi chạy Wrapper | Môi trường máy, `PATH`, `JAVA_HOME` | `java -version`, `javac -version`, đường dẫn thực tế |
| JVM chạy công cụ build | JVM chạy Gradle client/daemon hoặc Maven; có thể khác JDK biên dịch | Wrapper, cấu hình Gradle daemon, `JAVA_HOME`, IDE hoặc CI | `./gradlew --version` / `./mvnw --version` |
| JDK biên dịch và phiên bản `--release` | `javac` thực thi quá trình compile và phiên bản Java/API mà bytecode nhắm tới | Gradle Java toolchain, Maven Toolchains, Maven Compiler Plugin | Cấu hình build, thông tin toolchain, log compiler, class file |
| JDK chạy chương trình | JVM thực thi JAR, test, ứng dụng Spring Boot | Run configuration, container image, server, CI test runtime | `java -version`, log khởi động, `java.home` của tiến trình |

**Không được đồng nhất các giá trị trên.** Ví dụ máy có `JAVA_HOME` trỏ tới JDK 17 nhưng Gradle dùng **toolchain JDK 21** để biên dịch. Một dự án Maven đặt `maven.compiler.release=21` vẫn cần trình biên dịch hỗ trợ release 21; riêng thuộc tính `release` không cài JDK 21 giúp bạn.

`--release 17` trên một compiler mới hơn quy định ngôn ngữ, thư viện chuẩn và class file tương thích Java 17; nó không có nghĩa bản build đang chạy bằng JDK 17. Ngược lại, Java 21 bytecode thông thường có **class file major version 65**, còn Java 17 là **61**. Nếu đem class version 65 chạy trên JVM 17, bạn có thể nhận `UnsupportedClassVersionError`.

**Gradle còn có hai JVM riêng:** JVM client khởi chạy Wrapper và JVM daemon thực thi build. Daemon có thể chịu điều khiển của IDE, `org.gradle.java.home` hoặc Gradle Daemon JVM criteria. Vì thế chỉ xem `java -version` chưa đủ để chứng minh Gradle thực sự đang dùng JDK nào.

## 3. Quyết định chuẩn JDK cho cả nhóm

Trước khi chỉnh IDE/CI, cần thống nhất một **hợp đồng phiên bản** được ghi trong cấu hình dự án và tài liệu nhóm:

- **Phiên bản Java chính:** ví dụ Java 21, dùng cho compile/test và môi trường runtime được hỗ trợ.
- **Bản phân phối JDK:** ví dụ Eclipse Temurin; đây là cách giảm khác biệt về nhà cung cấp, không phải điều kiện bắt buộc của Java nếu dự án không yêu cầu.
- **Build tool và Wrapper:** dự án dùng Gradle hay Maven, phiên bản Wrapper đang được commit cùng source.
- **Mức Java mục tiêu:** thường bằng JDK chuẩn; nếu cần chạy ứng dụng bằng Java 17 thì phải thiết kế và kiểm thử mục tiêu 17 một cách chủ động.
- **Kiểm tra trên CI:** các bước build/test phải chạy với phiên bản đã chọn, không phụ thuộc Java mặc định của runner.

### Kiểm tra tương thích trước khi chọn JDK

1. Xem **phiên bản Spring Boot hiện tại của chính dự án** và yêu cầu Java/Gradle/Maven từ tài liệu chính thức của phiên bản đó. Ví dụ Spring Boot 3.3 yêu cầu ít nhất Java 17; không lấy yêu cầu của một bản Spring Boot mới hơn áp dụng máy móc cho dự án cũ.
2. Kiểm tra Gradle Wrapper trong `gradle/wrapper/gradle-wrapper.properties`. Để **chạy Gradle trên Java 21**, Gradle hỗ trợ chính thức từ **8.5**; hỗ trợ Java 21 như một *compile/test toolchain* bắt đầu từ Gradle **8.4**. Plugin Spring Boot và plugin khác có thể yêu cầu mức Gradle cao hơn.
3. Với Maven, kiểm tra `pom.xml`, Maven Wrapper, phiên bản compiler plugin và JDK dùng chạy Maven. Không suy ra compiler plugin hỗ trợ một release chỉ vì hệ điều hành đã cài JDK mới.
4. Nếu tổ chức còn chạy ứng dụng bằng JDK 17, không tùy tiện build target 21. Chọn ngưỡng runtime thực tế và chứng minh bằng test trên JDK đó.

**Nguyên tắc:** nâng JDK, nâng Gradle/Maven và nâng Spring Boot là ba thay đổi có rủi ro tương thích khác nhau. Chỉ thay từng phần khi đã xác nhận ma trận tương thích, không chỉnh nhiều phiên bản để chữa một lỗi chưa phân loại.

## 4. Kiểm tra JDK trên máy cá nhân (Windows và Linux)

Thực hiện trong thư mục gốc dự án, nơi có `gradlew[.bat]` hoặc `mvnw[.cmd]` và `build.gradle[.kts]` hoặc `pom.xml`.

### Windows PowerShell

~~~powershell
java -version
javac -version
$Env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

`java -version` và `javac -version` cho biết bản Java trong `PATH`. `Get-Command` cho biết tập tin thực thi được gọi đến, rất hữu ích nếu máy cài nhiều JDK hoặc còn bản `java.exe` cũ. `JAVA_HOME` nên trỏ đến **thư mục gốc JDK**, không trỏ vào `bin`.

Kiểm tra thêm Wrapper tương ứng, **chỉ chọn một**:

~~~powershell
# Dự án Gradle
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains

# Hoặc dự án Maven
.\mvnw.cmd --version
~~~

Task `javaToolchains` của Gradle hiển thị các Java installation đã phát hiện và khả năng của chúng; có thể không có JDK được yêu cầu nếu quá trình dò tìm hoặc tải toolchain chưa được cấu hình đúng.

Nếu máy Windows dùng `cmd.exe`, dùng `echo %JAVA_HOME%`, `where java`, `where javac`, `gradlew.bat --version` hoặc `mvnw.cmd --version`. Hai dạng cú pháp shell khác nhau; không sao chép nguyên lệnh PowerShell vào cmd.

### Linux (bash)

~~~bash
java -version
javac -version
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
~~~

Nếu cần biết đường dẫn cuối sau symbolic link trên Linux:

~~~bash
readlink -f "$(command -v java)"
~~~

Kiểm tra Wrapper:

~~~bash
# Chỉ dùng nếu là dự án Gradle
./gradlew --version
./gradlew -q javaToolchains

# Hoặc nếu là dự án Maven
./mvnw --version
~~~

Nếu báo `Permission denied` khi chạy Wrapper trên Linux, kiểm tra quyền thực thi của script. Với repository được quản lý bằng Git, cần commit executable bit đúng cho `gradlew` hoặc `mvnw` để CI Linux cũng chạy được; `chmod +x` trên máy cá nhân chưa tự bảo đảm metadata Git đã được cập nhật.

### Cách diễn giải

- `java -version` là 21 nhưng `javac -version` là 17: `PATH` hoặc nhiều bản JDK đang được trộn; sửa trước khi kết luận build dùng 21.
- `JAVA_HOME` là 21 nhưng `Get-Command java` / `command -v java` chỉ tới bản khác: kiểm tra thứ tự `PATH` và terminal hiện tại.
- Shell dùng 21 nhưng `./gradlew --version` cho thấy Gradle daemon dùng 17: kiểm tra cấu hình daemon JVM, `org.gradle.java.home`, cài đặt IDE và cấu hình criteria của phiên bản Gradle đang dùng.
- `./mvnw --version` cho thấy Maven chạy bằng 17: Maven có thể vẫn chạy bằng 17 dù project yêu cầu compile 21 bằng Toolchains; phải kiểm tra phần toolchain riêng. Nếu không dùng Toolchains thì cần Maven chạy trên JDK hỗ trợ release 21.

Sau khi sửa biến môi trường, **mở terminal mới** rồi kiểm tra lại. IDE đang mở trước lúc sửa có thể vẫn giữ môi trường cũ: cần cập nhật cài đặt hoặc khởi động lại IDE nếu cần.

## 5. Khai báo chuẩn JDK trong dự án Gradle

Các cấu hình dưới đây là **đoạn để thêm vào file build đang tồn tại**, không phải bản thay thế toàn bộ file. Chúng yêu cầu dự án có plugin Java/Java Library tương ứng và Gradle Wrapper hỗ trợ toolchain đã chọn.

### Groovy DSL: `build.gradle`

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

### Kotlin DSL: `build.gradle.kts`

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

Cấu hình này yêu cầu các task Java chuẩn sử dụng JDK 21 phù hợp để compile, chạy test hoặc tạo Javadoc (tùy task hỗ trợ). Gradle tự phát hiện JDK đã cài; **khả năng tự tải JDK không tự động được bảo đảm** vì còn phụ thuộc cấu hình toolchain repository/resolver và phiên bản Gradle. Khi thiếu toolchain, cài JDK tương ứng hoặc cấu hình resolver đúng theo hướng dẫn Gradle.

**Phân biệt toolchain với bytecode target:** khi dùng JDK 21 nhưng cần tạo Java 17 bytecode/API, có thể bổ sung trong `build.gradle`:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Đoạn này chỉ minh họa trường hợp **có chủ đích hỗ trợ runtime Java 17**; không thêm nó nếu chuẩn dự án là Java 21 toàn bộ. Các dependency và framework cũng phải tương thích Java 17; riêng `options.release` không thể làm một dependency biên dịch cho Java 21 tự chạy trên Java 17.

### Wrapper và JDK chạy Gradle

Commit các file Wrapper theo cấu trúc dự án, gồm `gradlew`, `gradlew.bat` và các file trong `gradle/wrapper/`. Chính `distributionUrl` ở `gradle-wrapper.properties` xác định phiên bản Gradle được tải, không phải phiên bản Gradle cài sẵn trên máy.

Nếu nhóm muốn Gradle **daemon** luôn yêu cầu JDK cụ thể, các phiên bản Gradle hiện đại có cơ chế **Daemon JVM criteria** lưu trong `gradle/gradle-daemon-jvm.properties`. Đây là cấu hình JVM *chạy Gradle*, khác với `java.toolchain` *biên dịch dự án*. Khi chưa dùng criteria, cần khớp `JAVA_HOME` và Gradle JVM của IDE; không được mặc định rằng một đoạn `java.toolchain` đã đổi JVM chạy Gradle.

Kiểm tra thực tế:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean build
~~~

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`. `BUILD SUCCESSFUL` chỉ xác nhận chuỗi task đã chạy xong; đọc thông tin JVM/compile toolchain riêng để chứng minh đồng bộ JDK.

## 6. Khai báo chuẩn JDK trong dự án Maven

### Maven Compiler và Spring Boot Parent

Nếu dự án dùng `spring-boot-starter-parent`, `pom.xml` thường có thể chỉ định phiên bản Java bằng thuộc tính:

~~~xml
<properties>
    <java.version>21</java.version>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

`java.version` là quy ước quan trọng của Spring Boot Parent cho cấu hình build. `maven.compiler.release` nói với Maven Compiler Plugin nhắm tới Java 21 về cú pháp, API chuẩn và bytecode. Một POM **không kế thừa Spring Boot Parent** cần cấu hình compiler plugin phù hợp một cách tường minh; không giả định mọi POM đều hiểu `java.version`.

Hai thuộc tính này **không cài JDK 21** và không tự đổi JVM đang chạy Maven. Khi chạy:

~~~bash
./mvnw --version
./mvnw --batch-mode clean verify
~~~

hãy đối chiếu phần `Java version` và `Java home` trong `--version`. Trên Windows PowerShell dùng `.\mvnw.cmd --version` và `.\mvnw.cmd --batch-mode clean verify`.

### Khi Maven chạy bằng JDK khác JDK compile: Maven Toolchains

Khi một máy có nhiều JDK hoặc build cần biên dịch bằng JDK 21 dù Maven đang được khởi chạy bằng JDK khác, dùng **Maven Toolchains**. Một trích đoạn plugin trong `pom.xml`:

~~~xml
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
                <version>21</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

Đoạn `plugin` này nằm trong `<build><plugins>...</plugins></build>` của POM; không chèn trực tiếp ở cấp gốc POM. Máy build phải có JDK phù hợp và khai báo cho Maven thấy, chẳng hạn file **cục bộ** `~/.m2/toolchains.xml` (trên Windows tương ứng thư mục `.m2` trong user home):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

**Đường dẫn `/opt/jdks/temurin-21` ở đây là ví dụ:** thay bằng đường dẫn JDK 21 thực sự trên từng máy; không commit đường dẫn riêng của một người vào POM. Toolchains plugin tìm bản phù hợp, còn các plugin *toolchain-aware* như Maven Compiler sẽ sử dụng compiler từ toolchain. Nếu Maven đang chạy bằng JDK 21 và không cần nhiều JDK, cấu hình `JAVA_HOME` + compiler release thường đã đủ cho dự án đơn giản.

Một số cách cài Toolchains mới có thể dò JDK tự động; cách trên minh họa rõ hợp đồng giữa POM và máy. Trong GitHub Actions, `actions/setup-java` cũng có khả năng tạo cấu hình Maven Toolchains; vẫn phải kiểm tra requirement và nhãn version/vendor thực sự khớp.

## 7. Thiết lập IDE để không dùng nhầm JDK

IDE thường có ít nhất ba cấu hình **độc lập**: **Project SDK** (phân tích code/editor), **JDK chạy Gradle/Maven** (import và build) và **JDK của Run/Debug configuration** (chạy app/test). Thay một mục không bảo đảm những mục còn lại đã đổi.

### IntelliJ IDEA

1. Vào **Project Structure → Project** để xem và chọn Project SDK là JDK 21 (hoặc phiên bản chuẩn của dự án). Kiểm tra language level phù hợp, đặc biệt nếu IDE có cấu hình khác mức compiler trong build.
2. Với Gradle: vào **Settings/Preferences → Build, Execution, Deployment → Build Tools → Gradle**, chọn phân phối **Gradle Wrapper** và **Gradle JVM** phù hợp. Nếu dự án có Gradle Daemon JVM criteria, đối chiếu chính criteria thay vì giả định Gradle JVM thủ công luôn là nguồn ưu tiên.
3. Với Maven: xem cài đặt **Maven Runner/Importer JDK** hoặc cấu hình Maven liên quan của phiên bản IDE; đối chiếu kết quả `mvnw --version` chạy từ terminal IDE với terminal bên ngoài.
4. Trong **Run/Debug Configurations**, kiểm tra JRE/JDK đang chạy Spring Boot app, test hoặc ứng dụng Java thông thường. Có thể project SDK 21 nhưng một run configuration vẫn chọn Java 17.
5. **Reload/reimport Gradle hoặc Maven project**, rồi chạy task build qua Wrapper trong terminal để so sánh với CI. Tùy cài đặt, nút **Build Project** của IDE có thể dùng compiler nội bộ thay vì đúng Gradle/Maven lifecycle.

### Eclipse hoặc VS Code

- **Eclipse:** kiểm tra **Preferences → Java → Installed JREs** (chọn một JDK phù hợp), **Project → Properties → Java Compiler** và JRE của **Run Configurations**. Với dự án Gradle dùng Buildship, kiểm tra riêng Gradle JDK và khả năng dùng Wrapper.
- **VS Code Java:** dùng lệnh **Java: Configure Java Runtime** để kiểm tra runtime cho dự án Java, đồng thời đối chiếu JDK được extension/build tool sử dụng. Terminal tích hợp có môi trường riêng theo cách VS Code được mở; vẫn phải chạy Wrapper và `--version` để có bằng chứng.

Không sửa **SDK của toàn bộ IDE** nếu chỉ một dự án yêu cầu Java khác. Ưu tiên cấu hình theo dự án và các toolchain/Wrapper nằm trong source control.

## 8. Đồng bộ JDK trên CI: ví dụ GitHub Actions

CI phải **cấp JDK rõ ràng trước bước build**. Không dựa vào Java có sẵn tình cờ trên image runner vì nó có thể được cập nhật mà không có thay đổi code. Một workflow thường nằm ở `.github/workflows/build.yml`.

### Dự án Gradle

Ví dụ workflow độc lập sau sử dụng Temurin 21, Gradle Wrapper và GitHub-hosted Ubuntu runner:

~~~yaml
name: Gradle build
on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle

      - name: Verify Java and Gradle
        run: |
          java -version
          javac -version
          ./gradlew --version
          ./gradlew -q javaToolchains

      - name: Build and test
        run: ./gradlew clean build
~~~

`actions/setup-java` chuẩn bị JDK, cập nhật `JAVA_HOME`/`PATH` và có thể cache dependency; `checkout` lấy các file Wrapper từ repository. Lệnh `./gradlew` dùng **phiên bản Gradle do Wrapper quản lý**, không cài một bản Gradle ngẫu nhiên trên runner. Với `ubuntu-latest`, script `gradlew` phải có quyền thực thi trong Git; nếu không, CI có thể báo `Permission denied`.

### Dự án Maven

Đây là workflow **thay thế** cho ví dụ Gradle ở trên; chọn workflow phù hợp với công cụ build của dự án:

~~~yaml
name: Maven build
on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Verify Java and Maven
        run: |
          java -version
          javac -version
          ./mvnw --version

      - name: Build and test
        run: ./mvnw --batch-mode clean verify
~~~

Hai ví dụ dùng các major version action được tài liệu `actions/setup-java` hiện hành mô tả; khi triển khai thực tế hãy kiểm tra phiên bản action được GitHub hỗ trợ ở thời điểm của dự án và chính sách ghim SHA của tổ chức.

**Giải thích các lựa chọn:**

- `java-version: '21'` ghim **feature/major version** và chọn bản JDK 21 phù hợp từ phân phối, có thể khác patch version giữa các lần chạy. Khi cần cố định cả patch version để điều tra lỗi hoặc tái lập chính xác, dùng version cụ thể và quy trình cập nhật có kiểm soát.
- `distribution: temurin` làm rõ JDK vendor. Các vendor tuân chuẩn Java nhưng lỗi vendor-specific/native tooling vẫn có thể xuất hiện.
- `cache: gradle` hoặc `cache: maven` giúp tiết kiệm thời gian tải dependency; **cache không thay thế việc khai báo JDK hoặc Wrapper**.
- `./gradlew clean build` và `./mvnw clean verify` đều thực thi build/test theo cấu hình thực tế. Nếu project có integration test, profile hoặc bước quality gate riêng, CI cần chạy đúng task/goal được dự án quy định.
- Nếu project là monorepo, thiết lập `working-directory` tới đúng thư mục chứa Wrapper, hoặc gọi Wrapper bằng đường dẫn thích hợp. Không giả định mọi repository chỉ có một ứng dụng tại root.

Với Windows CI runner, sử dụng `.\gradlew.bat` / `.\mvnw.cmd` trong PowerShell và chọn runner Windows phù hợp. Nền tảng OS có thể làm khác đường dẫn, line ending, permission và dependency native; **đồng bộ JDK không bảo đảm mọi khác biệt OS sẽ biến mất**.

## 9. Thực hành đối chiếu ba môi trường

Giả sử repository đã khai báo phiên bản Java 21 trong Gradle toolchain hoặc Maven `release`, và đã chọn Wrapper tương ứng.

| Bước kiểm tra | Máy cá nhân | IDE | CI |
| --- | --- | --- | --- |
| 1. Java hiện tại | `java -version`, `javac -version`, `JAVA_HOME` | Project SDK / cấu hình Java runtime | Log của `setup-java`, `java -version` |
| 2. JVM chạy build | `gradlew --version` hoặc `mvnw --version` | Gradle JVM/daemon criteria hoặc Maven Runner | Wrapper `--version` trong job |
| 3. Compiler thực tế | Gradle `javaToolchains`, cấu hình Java; hoặc Maven release/Toolchains | Reimport project rồi chạy build qua Wrapper | Log task/goal build và toolchain |
| 4. Kết quả build | Gradle `clean build` / Maven `clean verify` | Cùng task/goal qua Wrapper | Job hoàn tất với exit code 0 |
| 5. Runtime phù hợp | JDK dùng cho `java -jar` hoặc test | JDK của Run/Debug configuration | JDK test, container/deploy nếu có |

Khi mọi bên cùng chọn JDK 21, mong đợi thấy Java 21 ở JVM được dùng để compile/test và ở runtime có chủ đích. Nếu **Gradle daemon dùng Java 17 nhưng compiler toolchain dùng Java 21**, đó chưa chắc là lỗi; cần ghi nhận rõ thiết kế này, xác minh Gradle bản đang chạy hỗ trợ JVM 17 và toolchain 21, rồi kiểm tra CI có cùng khả năng. Nếu **dự án yêu cầu tất cả đều dùng JDK 21**, hãy đồng bộ daemon/runtime thật sự thay vì chỉ nhìn thông báo compile 21.

### Bài tập kiểm chứng độ tương thích runtime

Chạy một bản JAR Spring Boot thực thi do build tạo ra trên **JDK runtime được dự án cam kết hỗ trợ**; không phải bất kỳ JDK nào sẵn có. Nếu biên dịch class file mức 21 rồi chạy bằng JDK 17, lỗi tương thích class file là kết quả có thể dự đoán. Chỉ đổi `JAVA_HOME` ở terminal trong khi IDE vẫn khởi động app bằng JDK khác sẽ làm phép thử sai lệch.

Có thể dùng `javap -verbose` trên một file `.class` do dự án biên dịch để xem dòng `major version`, nhưng hãy chọn class **do chính project tạo**: `65` cho Java 21, `61` cho Java 17. Thông tin đó cho thấy mức class file, **không cho biết JDK nào đã chạy Gradle/Maven** và không chứng minh mọi dependency cũng tương thích runtime đích.

## 10. Lỗi phổ biến và cách sửa đúng nguyên nhân

| Dấu hiệu | Diễn giải đúng | Hành động |
| --- | --- | --- |
| Terminal thấy Java 21, IntelliJ Gradle build báo JVM 17 | IDE/daemon đang chọn JVM khác terminal | Kiểm tra Gradle JVM/daemon criteria, `org.gradle.java.home` và Gradle Wrapper; reload project |
| `error: release version 21 not supported` | `javac` thực tế quá cũ, thường là JDK 17 | Kiểm tra `javac -version`, Maven `--version`, toolchain/IDE compiler; dùng JDK hỗ trợ release 21 |
| `No matching toolchains found` hoặc `No Java installation matching` | JDK được yêu cầu chưa có hoặc không được tool nhận diện/cấp phát | Kiểm tra JDK cài đặt, Gradle toolchain resolver hay Maven `toolchains.xml`; không đổi release để né lỗi |
| `Unsupported class file major version 65` trong Gradle/plugin | Một thành phần dùng để đọc bytecode không hỗ trợ Java 21 | Xem stack trace để nhận diện Gradle/plugin/processor; nâng đúng thành phần có ma trận hỗ trợ |
| `UnsupportedClassVersionError`: runtime tới 61, class tới 65 | Artifact Java 21 chạy bằng Java 17 | Dùng JDK runtime 21 hoặc biên dịch lại phù hợp với runtime được cam kết và dependency hỗ trợ |
| CI lỗi ngay khi gọi `./gradlew`/`./mvnw` | Wrapper thiếu file hoặc script không có executable bit | Commit đầy đủ file Wrapper và permission trên Git, kiểm tra `working-directory` |
| `java -version` khác `javac -version` | PATH trộn nhiều bộ cài Java | Kiểm tra đường dẫn thực tế của hai lệnh, `JAVA_HOME`, mở terminal mới |
| Maven Toolchains báo không tìm thấy JDK 21 | Requirement ở POM không khớp file Toolchains của máy | Kiểm tra version/vendor được khai báo và `jdkHome` thực; cấu hình CI tương ứng |
| CI compile được nhưng test fail; local pass | Khác runtime, timezone, locale, dependency bên ngoài hoặc trạng thái test | So sánh JDK trước, sau đó kiểm tra test report và toàn bộ môi trường; không quy mọi lỗi test cho Java |
| IDE đỏ nhưng Wrapper build thành công | IDE đang dùng SDK/import/compiler model khác hệ build | Chỉnh Project SDK, language level, JDK import và reload project; lấy Wrapper build làm bằng chứng chính |

Đừng xóa cache hoặc nâng hàng loạt dependency ngay khi thấy lỗi. Đầu tiên ghi lại **lệnh, phiên bản JDK, JVM chạy build, toolchain biên dịch, dòng lỗi đầu tiên và hệ điều hành**. Với lỗi không liên quan phiên bản JDK (proxy, repository, secret, cấu hình database, cổng mạng), tiếp tục xử lý ở tầng tương ứng.

## 11. Danh sách xác nhận trước khi nhóm chấp nhận CI

- [ ] Nhóm đã chọn Java version và, nếu cần, JDK vendor phù hợp với Spring Boot/Gradle/Maven và môi trường triển khai.
- [ ] Version Java được thể hiện trong `build.gradle[.kts]` hoặc `pom.xml`; các file Wrapper phù hợp được lưu trong Git.
- [ ] Máy Windows/Linux truy cập được JDK, `javac` và Wrapper; không có lệch `PATH`/`JAVA_HOME` ngoài ý muốn.
- [ ] IDE chọn Project SDK, Gradle JVM/Maven Runner và Run/Debug JDK phù hợp; build qua Wrapper đồng nhất với terminal.
- [ ] CI dùng `setup-java` hoặc bước cấp JDK tương đương, không dựa vào JDK mặc định của runner.
- [ ] Build/test trên CI thành công; log `--version` và toolchain cho thấy đúng JDK mà project yêu cầu.
- [ ] Runtime production hoặc container dùng Java có thể chạy bytecode và dependency của artifact.
- [ ] Nếu yêu cầu tái lập nghiêm ngặt, cả patch JDK, plugin/dependency, Wrapper, hệ điều hành và môi trường build cũng được quản lý có chủ đích.

Bạn hoàn thành bài khi giải thích được tại sao **`java -version` đúng vẫn chưa đủ**, chỉ ra chính xác JDK của compiler và JVM chạy Gradle/Maven, rồi tự đối chiếu được kết quả giữa máy cá nhân, IDE và CI trên cùng một commit.

## Tài liệu chính thức

- [Gradle – Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle – Gradle Daemon và các JVM chạy Gradle](https://docs.gradle.org/current/userguide/gradle_daemon.html)
- [Gradle – Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Apache Maven – Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven Compiler Plugin – Compiler Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [GitHub Actions – actions/setup-java](https://github.com/actions/setup-java)
- [Spring Boot – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [IntelliJ IDEA – Gradle settings](https://www.jetbrains.com/help/idea/gradle-settings.html)
