# Quản lý nhiều JDK và đồng bộ phiên bản giữa máy cá nhân, IDE và CI

## 1. Bài toán và mục tiêu

Trong một nhóm phát triển, máy cá nhân có thể cài đồng thời **JDK 17, 21 và 25**. Một dự án vẫn dùng Java 21, còn dự án mới muốn tận dụng Java 25. Cài đủ ba JDK chưa bảo đảm các môi trường chạy đúng: terminal có thể gọi Java 25, Maven dùng Java 21, Gradle chạy bằng Java 17, IDE chọn runtime khác và CI tự lấy JDK mặc định của runner. Lỗi thường chỉ xuất hiện khi compile, test hoặc deploy.

Bài **Quản lý nhiều JDK và đồng bộ phiên bản giữa máy cá nhân, IDE và CI**, thuộc chương **Thiết lập JDK 25**, hướng dẫn thiết lập một hợp đồng phiên bản có thể kiểm chứng. Đây là nền tảng của lộ trình **JAVA_VERSION_JAVA25** để thực hành các khả năng Java 25 còn áp dụng trong phát triển hiện đại như chương trình nguồn gọn, module import, flexible constructor bodies, ScopedValue, API dẫn xuất khóa, AOT cache và JFR. Những chủ đề đó chỉ có ý nghĩa khi xác minh được **compiler và JVM thực thi**.

**Java 25 là dòng LTS** còn được hỗ trợ bởi các nhà cung cấp hiện hành. Java 25 không nhất thiết là bản Java feature release mới nhất tại thời điểm đọc bài; việc chọn bản LTS phải dựa trên yêu cầu ứng dụng và chính sách cập nhật của tổ chức. Bài chỉ sử dụng cách quản lý JDK đang được duy trì; không dựa vào cơ chế riêng của Java 8 hoặc công cụ đã ngừng hỗ trợ.

Sau bài này, bạn sẽ:

1. Phân biệt JDK trên PATH, JAVA_HOME, JVM chạy build tool, toolchain biên dịch, test runtime và deployment runtime.
2. Chọn JDK 25 theo dự án mà không ảnh hưởng dự án Java 17/21.
3. Khai báo Java Toolchains với Gradle hoặc Maven để tránh lệ thuộc máy cá nhân.
4. Đồng bộ Project SDK, Gradle/Maven JVM và Run Configuration trong IDE.
5. Cấu hình GitHub Actions chọn JDK 25 tường minh, có log kiểm tra và không tự chọn major mới hơn.
6. Chẩn đoán các lỗi lệch JDK, class file version và build tool không tương thích.

## 2. Sáu lớp phiên bản cần kiểm soát

| Lớp | Vai trò | Cách kiểm tra |
| --- | --- | --- |
| **JDK đã cài** | Danh sách JDK theo vendor, patch, hệ điều hành và kiến trúc CPU. | Thư mục cài, SDK manager, Gradle javaToolchains. |
| **Shell Java** | Các lệnh java và javac mà terminal tìm thấy. | **java --version**, **javac --version**, lệnh tìm đường dẫn. |
| **Build launcher JVM** | JVM chạy Maven hoặc Gradle daemon. | **./mvnw -version**, **./gradlew --version**. |
| **Compilation toolchain** | JDK thực sự biên dịch và cung cấp API nền tảng. | Gradle Java Toolchains hoặc Maven Toolchains, log compiler. |
| **Test / IDE Run JVM** | JDK thực thi test hoặc application từ IDE/build. | In Runtime.version() và java.home trong tiến trình. |
| **CI / container runtime** | JDK của runner, image build và image triển khai. | Workflow logs, metadata image và log ứng dụng. |

~~~mermaid
flowchart TD
    A["Máy có JDK 17 / 21 / 25"] --> B["Terminal: PATH + JAVA_HOME"]
    A --> C["IDE: SDK / Run JDK"]
    A --> D["Maven / Gradle toolchain"]
    B --> E["Build launcher JVM"]
    D --> F["Compiler + test launcher"]
    E --> F
    C --> G["IDE Run"]
    F --> H["Artifact: JAR / class"]
    H --> I["CI hoặc deployment runtime"]
~~~

**JAVA_HOME không phải hợp đồng duy nhất.** Nó chọn JDK mặc định cho nhiều công cụ nhưng không tự điều khiển Gradle toolchain, Maven toolchain hoặc Run Configuration đã cố định đường dẫn khác. Một JVM dùng để chạy Maven/Gradle có thể khác JVM dùng cho JavaCompile, tests hoặc ứng dụng.

Java 25 sử dụng **class file major version 69**. Nếu compiler tạo bytecode Java 25 rồi chạy trên JVM 21, có thể gặp **UnsupportedClassVersionError**. Muốn chạy trên Java 21 cần compile với API và bytecode tương thích Java 21; chỉ đổi JAVA_HOME ở máy deploy không thể làm bytecode Java 25 tương thích ngược.

## 3. Chốt chính sách JDK 25 cho dự án

Nhóm cần thống nhất một cấu hình rõ ràng:

| Thuộc tính | Ví dụ | Quyết định |
| --- | --- | --- |
| Java feature version | **25** | Mức API/ngôn ngữ dự án muốn sử dụng. |
| Distribution | **Eclipse Temurin** | Vendor JDK được nhóm kiểm chứng. |
| Compiler release | **25** | Ngôn ngữ, API nền tảng và bytecode Java 25. |
| Build tool | Gradle có hỗ trợ Java 25 hoặc Maven với compiler/toolchains phù hợp | Không dựa vào bản Gradle/Maven có sẵn ngẫu nhiên. |
| Patch/build | Bản 25.0.x đã được kiểm thử | Ghi đủ thông tin khi phát hành để truy nguyên. |
| CI | Java 25, vendor tường minh | Runner không được tự chọn latest major. |
| Runtime | JVM tương thích Java 25 | Máy chủ/container không chạy JDK thấp hơn bytecode. |

Đặt **major=25** phù hợp với yêu cầu nền tảng, đồng thời cập nhật **security patch** từ vendor có kiểm soát. Cấu hình **25** dạng floating có thể chọn patch mới ở lần chạy sau; khi cần xây dựng artifact tái hiện chính xác, phải ghi **vendor, version đầy đủ, build, architecture và image digest**. Tránh khóa mãi vào một bản vá cũ vì dễ bỏ lỡ cập nhật bảo mật.

Các distribution OpenJDK khác như Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK, Oracle JDK và BellSoft Liberica có chính sách hỗ trợ, giấy phép và gói triển khai riêng. Cùng Java feature 25 chưa chắc cùng vendor build; nếu production dùng một vendor cụ thể, hãy kiểm thử trên vendor đó.

## 4. Cài song song và chọn JDK trong terminal

### 4.1. Cài từ nguồn được xác thực

Ví dụ dùng **Eclipse Temurin 25 LTS** từ [Adoptium Releases](https://adoptium.net/temurin/releases). Chọn đúng **JDK** theo Windows/macOS/Linux và x64/arm64; kiểm tra checksum/chữ ký theo hướng dẫn của nhà cung cấp hoặc package manager. Có thể giữ JDK 17, 21, 25 trong các thư mục riêng mà không cần gỡ bản đang dùng cho dự án khác.

### 4.2. Windows PowerShell

Giả sử JDK 25 đã được cài tại **C:\Java\jdk-25**. Thay bằng đường dẫn thực tế:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-25'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"

java --version
javac --version
where.exe java
where.exe javac
Get-Command java -All
~~~

**JAVA_HOME** phải trỏ tới thư mục gốc JDK, không trỏ tới **bin**. Thay đổi biến môi trường bằng **$env:** chỉ có hiệu lực cho PowerShell hiện hành và tiến trình con. Nếu PATH vẫn có đường dẫn Java cũ ở phía trước, **where.exe** giúp phát hiện nguyên nhân. Tránh liên tục thêm nhiều thư mục bin vào PATH; dùng quy ước chuyển JDK ổn định theo từng dự án.

### 4.3. Linux và macOS

Ví dụ Bash/Zsh trên Linux:

~~~bash
export JAVA_HOME=/opt/jdks/jdk-25
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
command -v java
~~~

Đối với JDK đã đăng ký vào hệ thống macOS:

~~~bash
/usr/libexec/java_home -V
export JAVA_HOME=$(/usr/libexec/java_home -v 25)
export PATH="$JAVA_HOME/bin:$PATH"
java --version
~~~

Các đường dẫn trên phụ thuộc cách cài. Không áp dụng lệnh **/usr/libexec/java_home** cho Linux. Với máy Linux có **update-alternatives**, thay mặc định hệ thống có thể ảnh hưởng phần mềm khác; chọn JDK theo project/shell thường dễ kiểm soát hơn.

### 4.4. SDKMAN! và file cấu hình theo dự án

Trên hệ Unix, **SDKMAN!** là lựa chọn còn được duy trì để dùng nhiều phiên bản JDK. Ví dụ:

~~~bash
sdk list java
sdk install java ID_JAVA_25_TEMURIN
sdk use java ID_JAVA_25_TEMURIN
sdk current java
~~~

**ID_JAVA_25_TEMURIN** là chỗ giữ chỗ; thay bằng identifier thực được **sdk list java** hiển thị tại thời điểm cài. Tạo file **.sdkmanrc** ở gốc dự án:

~~~properties
java=ID_JAVA_25_TEMURIN
~~~

Khi ở thư mục dự án:

~~~bash
sdk env
java --version
~~~

**sdk use** chọn phiên terminal; **sdk env** đọc cấu hình dự án. Tự động tải/chuyển khi vào thư mục phụ thuộc thiết lập SDKMAN và mức tin cậy đối với repository. File **.sdkmanrc** hữu ích cho người dùng SDKMAN nhưng **không thay thế toolchain của build hoặc thiết lập CI**.

## 5. Kiểm tra Java thực sự được chạy

Trong terminal:

~~~bash
java --version
javac --version
~~~

Với Bash/Zsh xem thêm **echo "$JAVA_HOME"**, với PowerShell xem **$env:JAVA_HOME**. **java** và **javac** nên cùng feature version khi bạn biên dịch trực tiếp bằng shell. Nếu **javac** không tồn tại, máy có thể thiếu gói JDK đầy đủ.

Tạo một chương trình chẩn đoán rất nhỏ để chạy bằng terminal, IDE và CI:

~~~java
public class JdkCheck {
    public static void main(String[] args) {
        System.out.println("version = " + Runtime.version());
        System.out.println("feature = " + Runtime.version().feature());
        System.out.println("java.home = " + System.getProperty("java.home"));
        System.out.println("java.vendor = " + System.getProperty("java.vendor"));
        System.out.println("os.arch = " + System.getProperty("os.arch"));
    }
}
~~~

Lưu thành **JdkCheck.java** trong bài thực hành, chạy:

~~~bash
java JdkCheck.java
~~~

Source-file mode của lệnh **java** là cơ chế hiện vẫn được hỗ trợ. Nếu terminal in **feature=25** nhưng khi chạy bằng nút Run của IDE in **feature=21**, vấn đề nằm ở **Run Configuration/JDK thực thi**. Log của chính tiến trình là bằng chứng tốt hơn suy đoán từ icon JDK trong IDE.

## 6. Gradle: toolchain 25 và JVM chạy Gradle

### 6.1. Chọn Gradle tương thích

Theo [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html), **Java 25 được hỗ trợ chính thức làm toolchain và làm JVM chạy Gradle từ Gradle 9.1.0**. Hãy nâng **Gradle Wrapper** đến bản tương thích với Java 25 và phiên bản plugin (Spring Boot, Kotlin...) trước khi dùng JDK 25 để chạy Gradle. Không nên trông chờ Gradle cũ chạy bình thường chỉ vì lệnh java đã được chuyển sang 25.

Kiểm tra bằng wrapper của dự án:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

Trên Windows dùng **gradlew.bat** nếu shell không gọi được **./gradlew**. **--version** cho biết JVM chạy Gradle; **javaToolchains** liệt kê những JDK Gradle phát hiện làm toolchain. Hai JVM này có thể khác nhau mà vẫn hợp lệ.

### 6.2. build.gradle.kts

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
        // Nếu cần khóa vendor thì có thể thêm:
        // vendor = JvmVendorSpec.ADOPTIUM
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(25)
}
~~~

**Java Toolchains** chọn JDK phù hợp cho các task Java được hỗ trợ như compiler/test/javadoc. **--release 25** yêu cầu compiler tuân theo mức ngôn ngữ, bytecode và public Java API của 25. Nếu cần phát hành thư viện còn chạy trên Java 21, nhóm có thể chọn toolchain 25 nhưng **release=21**; khi đó code không được sử dụng API và cú pháp Java 25 không tương thích Java 21.

Gradle có thể tự phát hiện JDK đang cài. Nếu thiếu JDK 25, việc tự tải chỉ hoạt động khi dự án có cấu hình **toolchain download repository/resolver** phù hợp; không tự giả định một build offline có thể tải JDK. Có thể kiểm tra bằng **./gradlew -q javaToolchains**.

Khi Gradle daemon giữ trạng thái cũ sau khi đổi JDK:

~~~bash
./gradlew --stop
./gradlew --version
./gradlew -q javaToolchains
./gradlew test
~~~

Không dùng **org.gradle.java.home** thay cho compiler toolchain nếu muốn một build có thể chạy trên nhiều máy: thiết lập đó chủ yếu tác động tới JVM chạy Gradle và dễ chứa đường dẫn riêng của người dùng. Một số tác vụ bên thứ ba có thể không tuân theo toolchain tự động; cần kiểm tra plugin thực tế.

### 6.3. build.gradle (Groovy DSL)

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 25
}
~~~

Chỉ chọn **một DSL** đang được dự án sử dụng, không cần tạo cả hai file.

## 7. Maven: compiler release và JDK Toolchains

Kiểm tra JVM chạy Maven:

~~~bash
./mvnw -version
~~~

Trong **pom.xml**, khai báo compiler release cho dự án Java 25:

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>
~~~

**maven.compiler.release=25** chỉ hướng dẫn compiler tạo class/API tương ứng; nó **không tự cài JDK 25**. Nếu Maven chạy bằng JDK 21 mà không chọn toolchain 25, có thể lỗi **release version 25 not supported**.

### 7.1. Tự tìm JDK 25 bằng Maven Toolchains Plugin

Từ Maven Toolchains Plugin **3.2.0**, goal **select-jdk-toolchain** có thể tìm JDK trên máy mà không nhất thiết phải viết thủ công **toolchains.xml**. Ví dụ plugin **3.3.0** (đặt vào POM dự án hiện có):

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
    <toolchain.jdk.version>[25,26)</toolchain.jdk.version>
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
    </plugins>
</build>
~~~

**[25,26)** chọn JDK thuộc nhánh 25, bao gồm các patch của JDK 25. Cần đặt compiler plugin phiên bản có hỗ trợ mục tiêu release này theo build hiện tại. Dùng các lệnh:

~~~bash
./mvnw org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
./mvnw -version
./mvnw verify
~~~

Nếu log **./mvnw -version** hiển thị Java 21 nhưng compiler được Toolchains chọn JDK 25 thì điều đó **có thể hoàn toàn hợp lệ**: một bên là JVM chạy Maven, một bên là JDK build. Phải kiểm tra log toolchain/compiler và JVM của test riêng. Không phải mọi Maven plugin đều tự động sử dụng toolchain đã chọn; các plugin tự fork JVM có thể cần cấu hình riêng.

### 7.2. Khai báo toolchains.xml theo chính sách tổ chức

Khi không dùng discovery hoặc cần kiểm soát thủ công, có thể dùng file **~/.m2/toolchains.xml** trong môi trường từng người dùng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>25</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-25</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Đường dẫn ở trên chỉ là ví dụ; cần khai báo đúng vị trí JDK thật và cấu hình plugin **toolchain** tương ứng trong Maven để tiêu thụ file. **Không commit đường dẫn riêng của máy vào POM chung.** Với dự án mới, cơ chế discovery của plugin hiện hành giúp giảm lệch cấu hình.

## 8. IDE: Project SDK, build JVM và nút Run

### 8.1. IntelliJ IDEA

Các mục cần đối chiếu:

1. **Project Structure → Project SDK**: chọn JDK 25 đã đăng ký; chỉnh language level phù hợp nếu dự án thực sự dùng syntax Java 25.
2. **Project Structure → Modules**: kiểm tra module SDK nếu project có nhiều Java module.
3. **Settings → Build, Execution, Deployment → Build Tools → Gradle → Gradle JVM**: biết JVM chạy Gradle trong IDE. Java toolchain trong build vẫn điều khiển compiler nếu được cấu hình.
4. Với Maven, kiểm tra JVM mà **Maven Runner/Importer** của IDE sử dụng; xem compiler release và toolchain ở POM.
5. **Run/Debug Configurations**: chọn runtime 25 cho ứng dụng/test sử dụng Java 25.
6. Terminal tích hợp IDE: chạy **java --version**, **./gradlew --version** hoặc **./mvnw -version**; đừng mặc định terminal và Run dùng cùng JVM.

**Không cần thay JVM nội bộ chạy chính IntelliJ IDEA** chỉ để dự án dùng Java 25. IDE chỉ cần là phiên bản hỗ trợ Java 25, và Project SDK/Run/build cần được chọn đúng.

### 8.2. Eclipse và VS Code

Với **Eclipse**, kiểm tra **Preferences → Java → Installed JREs**, Project build path và compiler compliance; bảo đảm JDT của phiên bản IDE nhận diện Java 25. Với Maven/Gradle integration, kiểm tra JVM của build tool và test runner.

Với **VS Code**, dùng lệnh **Java: Configure Java Runtime** để xem JDK cho project; khi quản lý nhiều bản có thể cấu hình **java.configuration.runtimes**. Kiểm tra Java extension đã hỗ trợ Java 25, đồng thời xác minh terminal, Maven/Gradle và cấu hình Run/Debug. Language server JDK không tự quyết định mọi JVM build/test.

### 8.3. Bảng nhất quán trong IDE

| Vị trí | Mục tiêu với ứng dụng Java 25 |
| --- | --- |
| Project SDK / language level | Hiểu cú pháp và API Java 25. |
| Compiler toolchain | Dùng JDK 25 và --release 25. |
| Test runner | JVM 25 khi test cần tính năng Java 25. |
| App Run/Debug | Java 25, không phải runtime 21 lưu trong cấu hình cũ. |
| Build tool launcher | JDK được bản Maven/Gradle hỗ trợ, có thể khác toolchain. |
| IDE tự thân | Phiên bản IDE còn được cập nhật và hỗ trợ Java 25. |

## 9. CI: chọn Java 25 rõ ràng thay vì dựa vào runner

**actions/setup-java@v6** đang hỗ trợ Java 25, nhiều distribution, PATH/JAVA_HOME và Maven Toolchains. Ví dụ GitHub Actions cho dự án Maven:

~~~yaml
name: Java 25 CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '25'
          cache: maven
      - name: Verify selected JDK
        run: |
          java --version
          javac --version
          echo "JAVA_HOME=$JAVA_HOME"
          ./mvnw -version
      - name: Build and test
        run: ./mvnw --batch-mode verify
~~~

Với Gradle, dùng cùng step setup-java nhưng chuyển **cache: gradle** và chạy:

~~~yaml
- name: Build and test with Gradle
  run: |
    java --version
    javac --version
    ./gradlew --version
    ./gradlew -q javaToolchains
    ./gradlew test --no-daemon
~~~

Đây là **step thay thế**, không phải workflow Gradle đầy đủ. Khi chạy Gradle bằng JDK 25, wrapper phải là **Gradle 9.1.0+** và tương thích với plugin của dự án. Với self-hosted runner, kiểm tra phiên bản runner hỗ trợ runtime của action.

**java-version: '25'** chọn nhánh 25 và có thể nhận bản vá mới ở lần chạy sau. Nếu cần tái lập một bản release chính xác, ghi hoặc pin build đầy đủ của JDK đã kiểm chứng, và cập nhật theo chu kỳ bảo mật. Không dùng **java-version: latest** vì bản mới nhất có thể thuộc major khác. Trong tổ chức có yêu cầu chuỗi cung ứng chặt chẽ, nên pin GitHub Actions theo **full commit SHA đã xác minh** hoặc chính sách lockfile đáng tin cậy; tag phiên bản trong ví dụ nhằm dễ đọc.

**Không tạo ma trận test Java 17/21/25 tùy tiện.** Nếu artifact compile với **--release 25**, Java 21 không thể chạy artifact đó. Chỉ thêm runtime vào CI matrix khi ứng dụng/thư viện thực sự cam kết hỗ trợ runtime ấy và biên dịch theo mức API tương thích.

## 10. Đồng bộ với container và bản triển khai

Pipeline CI PASS vẫn chưa chứng minh production chạy JDK 25. Hãy kiểm tra:

- **Build image** dùng JDK 25 hoặc toolchain thật sự chọn JDK 25.
- **Runtime image** dùng Java 25 tương thích bytecode; nếu dùng image rút gọn bằng **jlink**, các module cần thiết vẫn phải đầy đủ.
- **OS/architecture** của image đúng CPU của môi trường triển khai, nhất là với native dependencies hoặc multi-architecture builds.
- Base image lấy từ nguồn tin cậy và được cập nhật các patch bảo mật; nếu cần khả năng tái lập thì lưu **image digest** ngoài tag.
- Log khởi động hoặc test trong container ghi **Runtime.version()**, **java.vendor**, **java.home**.

Nếu build tạo class file major 69 rồi runtime image chứa Java 21, lỗi có thể chỉ xuất hiện khi container khởi động. Ngược lại, chạy JVM 25 với bytecode release 21 vẫn có thể hợp lệ, nhưng code được biên dịch với release 21 không được sử dụng API chỉ có ở 25.

Với yêu cầu nâng cấp JDK, lưu **artifact provenance**: source commit, toolchain/release, vendor/version/build, test report, dependency lock/BOM, container digest và cấu hình runtime. Toolchain không tự khóa mọi dependency hoặc phiên bản plugin.

## 11. Chẩn đoán lỗi lệch JDK

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và cách xử lý |
| --- | --- | --- |
| java là 25, javac là 21 | PATH chứa nhiều JDK với thứ tự sai. | where.exe java/javac hoặc command -v; chỉnh JAVA_HOME/PATH. |
| Maven báo **release version 25 not supported** | Compiler dùng JDK cũ; Toolchains chưa chọn JDK 25. | ./mvnw -version, log toolchains và compiler. |
| Gradle không chạy trên Java 25 | Gradle wrapper quá cũ. | Nâng lên Gradle tương thích, từ 9.1.0 cho Java 25. |
| Gradle báo **No matching toolchains found** | Chưa cài JDK 25 hoặc chưa cấu hình resolver auto-provision. | ./gradlew -q javaToolchains; cài/khai báo đúng JDK. |
| IntelliJ hỗ trợ cú pháp nhưng Run bị UnsupportedClassVersionError | Run Configuration dùng JVM 21/17. | In Runtime.version() ngay trong ứng dụng chạy. |
| Terminal build PASS, IDE Build FAIL | IDE dùng JVM/Gradle/Maven toolchain khác. | So setting IDE và --version ở từng môi trường. |
| CI cho kết quả khác sau rerun | java-version 25 nhận bản patch mới hoặc runner image khác. | Ghi full version/build, kiểm soát lịch cập nhật. |
| CI PASS, container FAIL | Runtime image cũ hơn class file của artifact. | java --version trong image và class file major. |
| Code Java 25 không compile dù shell là 25 | Compiler release thấp, IDE/plugin cũ hoặc build tool chọn JDK khác. | Kiểm tra --release, toolchain và hỗ trợ Java 25. |
| Feature preview không chạy | Thiếu cờ preview hoặc khác phiên bản; feature đó chưa finalized. | Chỉ dùng --enable-preview nếu feature cụ thể của Java 25 thực sự còn preview. |

**Bộ bằng chứng nhanh:** java --version, javac --version, Maven/Gradle --version, toolchain được chọn và Runtime.version() của ứng dụng/test. Nếu chỉ kiểm tra một giá trị ở shell thì chưa đủ để kết luận môi trường đã đồng bộ.

## 12. Quy trình nhóm có dự án Java 21 và Java 25

1. **Định nghĩa yêu cầu:** dự án B thực sự cần API/cú pháp Java 25 hay chỉ chạy trên JVM 25? Quyết định này ảnh hưởng compiler release và ma trận runtime.
2. **Chọn distribution:** dùng vendor đã xác minh, nêu rõ major 25 và chính sách cập nhật patch.
3. **Cài song song:** giữ JDK 21 cho dự án A, JDK 25 cho B; chọn theo terminal/dự án bằng công cụ phù hợp.
4. **Đặt build contract:** Gradle Java Toolchain 25 hoặc Maven Toolchains 25; compiler release đúng mục tiêu.
5. **Đồng bộ IDE:** Project SDK, build launcher, test launcher và Run Configuration; thực thi JdkCheck.java.
6. **Quản lý wrapper:** commit Maven/Gradle Wrapper của dự án; kiểm tra bản wrapper với JDK/plugin trước khi nâng.
7. **Chọn JDK trong CI:** khai báo Java 25 và distribution tường minh, in version trước bước test.
8. **Xác minh deployment:** build image, runtime image, CPU và JDK runtime phải tương thích.
9. **Cập nhật bảo mật:** nâng patch có kiểm thử, lưu version/build và phương án rollback.
10. **Kiểm tra lại:** sau nâng JDK, chạy cùng checklist tại local, IDE, CI và container.

### Mẫu checklist cho pull request

| Thành phần | Kỳ vọng | Bằng chứng thực tế |
| --- | --- | --- |
| Local terminal java / javac | Java 25 | Lưu output. |
| Gradle/Maven launcher | JVM được build tool hỗ trợ | Output --version. |
| Compiler toolchain | JDK 25 | Log lựa chọn toolchain. |
| Compiler release | 25 | POM/Gradle task settings. |
| IDE Run và tests | Java 25 | Runtime.version() và test report. |
| GitHub Actions | Java 25, vendor rõ | Workflow log của job. |
| Docker/runtime | Java 25 | Startup log + image digest. |
| Security patch | Bản đã kiểm chứng | Vendor + full version/build. |

Không tự đánh dấu PASS chỉ vì một giá trị nằm trong file cấu hình: phải có **bằng chứng từ tiến trình thực sự chạy**.

## 13. Bài tập và tự kiểm tra

**Bài tập A:** Cài JDK 21 và JDK 25 song song. Cho terminal dùng 25 nhưng tạm chỉnh IDE Run dùng 21. Chạy JdkCheck.java theo hai cách, ghi khác biệt, sửa cấu hình IDE và xác nhận cả hai dùng 25.

**Bài tập B:** Dùng Gradle phiên bản hỗ trợ Java 25, cho Gradle launcher chạy trên một JVM được hỗ trợ và build dùng toolchain 25. So kết quả **./gradlew --version**, **./gradlew -q javaToolchains** và Runtime.version() trong test.

**Bài tập C:** Cấu hình Maven Compiler release=25 và Maven Toolchains chọn **[25,26)**. Thu log compiler/toolchain. Thử bỏ toolchain trong nhánh thử nghiệm dùng Maven launcher JDK cũ để hiểu lỗi và khôi phục cấu hình đúng.

**Bài tập D:** Tạo GitHub Actions chọn Temurin 25, chạy test, lưu Java/Javac/build tool version. So patch/build CI với local; thiết kế kế hoạch cập nhật patch an toàn.

**Bài tập E:** Biên dịch ứng dụng bằng release 25 và chạy trên runtime 25; phân tích vì sao runtime 21 không thể chạy bytecode Java 25. Nếu muốn dùng các tính năng Java 25, chỉ dùng những API/tính năng đã chính thức hỗ trợ ở bản mục tiêu, không bật preview một cách mặc định.

**Câu hỏi:**

1. Vì sao JAVA_HOME=JDK25 không chứng minh IDE và Maven đều đang dùng JDK 25?
2. Khi nào JVM chạy Gradle khác với toolchain JavaCompile?
3. --release giải quyết gì mà sourceCompatibility và targetCompatibility đơn lẻ không bảo đảm?
4. Vì sao Java 25 patch của CI có thể khác máy cá nhân dù hai bên chọn major 25?
5. Maven Toolchains khác maven.compiler.release ra sao?
6. UnsupportedClassVersionError với major 69 cho biết điều gì?
7. Vì sao không nên dùng latest hoặc --enable-preview cho mọi dự án Java 25?
8. Những bằng chứng nào cho phép reviewer xác nhận IDE, CI và production chạy đúng phiên bản?

## 14. Tham khảo chính thức

- [Eclipse Temurin Releases](https://adoptium.net/temurin/releases) — tải JDK 25 LTS, chọn hệ điều hành, kiến trúc và patch.
- [Gradle Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — kiểm tra phiên bản Gradle hỗ trợ Java 25.
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html) — khai báo, phát hiện và cung cấp JDK cho build.
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/) — chọn JDK khác JVM chạy Maven.
- [Maven JDK Discovery](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html) — cách tìm và ràng buộc phiên bản JDK.
- [GitHub Actions setup-java](https://github.com/actions/setup-java) — cấu hình Java 25, PATH/JAVA_HOME và nhiều JDK trong workflow.
- [SDKMAN! Usage](https://sdkman.io/usage/) — chuyển JDK theo terminal và dự án.

Các tài liệu trên được duy trì theo phiên bản; khi nâng JDK/build tool sau này, luôn kiểm tra hướng dẫn phù hợp với bản đang chạy. Không giữ nguyên một bản patch đã quá hạn cập nhật hoặc cách cài đặt dành riêng cho các bản Java cũ.

**Kết quả cần nộp:** danh sách JDK đã cài, cấu hình toolchain Java 25, kết quả kiểm tra terminal/IDE/test, workflow CI chọn JDK rõ ràng và bằng chứng JDK runtime/container. Khi sáu lớp phiên bản được đồng bộ và kiểm chứng, nhóm có thể sử dụng Java 25 trong dự án hiện đại mà vẫn bảo trì các dự án Java khác trên cùng máy.
