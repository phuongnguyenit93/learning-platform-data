# Quản lý nhiều phiên bản JDK trên máy phát triển

Một máy phát triển thường cần nhiều phiên bản Java cùng lúc. Dự án đang bảo trì có thể yêu cầu JDK 17 hoặc 21, dự án mới có thể dùng JDK 25 LTS, còn một nhánh thử nghiệm cần JDK 27 để kiểm tra tính năng mới. Cài đặt nhiều JDK không khó; phần cần quản lý cẩn thận là **chọn đúng JDK cho từng dự án và từng công cụ**, đồng thời bảo đảm nhóm phát triển và máy CI dùng cùng cấu hình.

Trong bài này, JDK 25 được dùng làm ví dụ cho dòng LTS hiện hành và JDK 27 cho dòng feature release hiện hành tại thời điểm biên soạn (tháng 11/2026). JDK 27 đã phát hành chính thức nhưng không phải LTS; vòng đời hỗ trợ của các bản feature release ngắn hơn. Vì vậy, hãy dùng phiên bản mà dự án yêu cầu, và cân nhắc LTS cho hệ thống cần duy trì lâu dài. Lịch phát hành và thời gian hỗ trợ còn phụ thuộc nhà cung cấp JDK.

## 1. Hiểu những thành phần đang được quản lý

### JDK, JRE và JVM

- **JVM (Java Virtual Machine)** thực thi bytecode Java.
- **JRE (Java Runtime Environment)** cung cấp môi trường chạy ứng dụng Java.
- **JDK (Java Development Kit)** gồm môi trường chạy và các công cụ phát triển như `javac`, `jar`, `javadoc`, `jshell` và `jlink`.

Khi phát triển ứng dụng, hãy cài **JDK**. Một bản JRE riêng có thể đủ để chạy ứng dụng, nhưng không có trình biên dịch `javac` và các công cụ phát triển cần thiết.

### Phiên bản, nhà cung cấp và bản phân phối

Hai bộ cài cùng số phiên bản Java vẫn có thể đến từ các nhà cung cấp khác nhau. Một số bản phân phối JDK phổ biến hiện nay gồm:

| Nhà cung cấp / bản phân phối | Khi nào nên cân nhắc |
| --- | --- |
| Eclipse Temurin | Bản dựng OpenJDK phổ biến, miễn phí và có lịch cập nhật rõ ràng |
| Oracle JDK | Khi tổ chức cần bản phân phối và điều khoản hỗ trợ của Oracle |
| Amazon Corretto | Khi cần bản phân phối do AWS duy trì hoặc muốn đồng nhất với môi trường AWS |
| Azul Zulu | Khi tổ chức đã chuẩn hóa theo Azul hoặc cần các lựa chọn nền tảng của nhà cung cấp này |
| Microsoft Build of OpenJDK | Khi tổ chức muốn dùng bản dựng OpenJDK do Microsoft cung cấp |

Hãy chọn nhà cung cấp dựa trên chính sách hỗ trợ, nền tảng đích, yêu cầu chứng nhận, giấy phép và quy trình cập nhật bảo mật của tổ chức. Không nên đổi nhà cung cấp tùy tiện giữa các máy trong cùng một quy trình build nếu dự án phụ thuộc vào hành vi hoặc thành phần đặc thù của một bản phân phối.

### Phiên bản LTS và feature release

Java phát hành theo chu kỳ sáu tháng. Bản LTS nhận thời gian hỗ trợ dài hơn theo chính sách của từng nhà cung cấp; các bản feature release nằm giữa những mốc LTS thường có thời gian hỗ trợ ngắn hơn.

| Dòng Java | Vai trò tại thời điểm biên soạn | Cách sử dụng phù hợp |
| --- | --- | --- |
| JDK 25 | LTS hiện hành | Nền tảng phù hợp cho dự án mới cần thời gian duy trì dài |
| JDK 27 | Feature release mới nhất | Thử nghiệm, học tập, đánh giá tính năng và dự án chủ động theo nhịp phát hành mới |
| JDK 21, 17 | Các mốc LTS trước đó | Duy trì và phát triển các hệ thống còn yêu cầu những phiên bản này |

Không suy ra phiên bản Java mà một dự án cần chỉ từ phiên bản mới nhất đang có. Hãy kiểm tra yêu cầu của dự án, framework, thư viện, plugin build, môi trường triển khai và chính sách hỗ trợ trước khi nâng cấp.

## 2. Phân biệt các lớp chọn JDK

Máy tính có thể cài nhiều JDK nhưng mỗi tiến trình chỉ sử dụng một môi trường Java cụ thể tại thời điểm chạy. Có một số lớp cấu hình độc lập:

1. **Cấu hình hệ điều hành và terminal:** lệnh `java` được tìm theo thứ tự thư mục trong `PATH`. `JAVA_HOME` thường được các công cụ build và script đọc trực tiếp.
2. **Trình quản lý phiên bản:** công cụ như mise hoặc SDKMAN có thể đổi JDK theo shell hoặc thư mục dự án.
3. **IDE:** IntelliJ IDEA, Eclipse và VS Code có thể chọn JDK cho project, compiler hoặc tiến trình build riêng.
4. **Build tool:** Gradle và Maven có cơ chế toolchain để chỉ định JDK biên dịch, chạy test và tạo tài liệu.
5. **CI/container:** pipeline hoặc image build có thể chỉ định JDK độc lập với máy phát triển.

Các lớp này có thể không trùng nhau. Ví dụ, `java -version` trong terminal có thể hiển thị JDK 25, nhưng IntelliJ IDEA vẫn dùng JDK 21 cho Gradle; một task Gradle khác lại biên dịch bằng JDK 17 theo cấu hình toolchain. Vì thế, khi gặp lỗi khác biệt giữa terminal, IDE và CI, hãy kiểm tra từng lớp thay vì chỉ nhìn một kết quả `java -version`.

`JAVA_HOME` cũng không tự làm cho lệnh `java` đổi phiên bản. Terminal chỉ chạy đúng JDK nếu thư mục `bin` của JDK đó được đưa vào `PATH` ở vị trí ưu tiên, hoặc nếu trình quản lý phiên bản đã cấu hình lệnh shim tương ứng.

## 3. Cài đặt và quản lý nhiều JDK

Có hai cách chính: cài các JDK riêng rồi tự chọn đường dẫn, hoặc dùng trình quản lý phiên bản để cài đặt và chuyển đổi tự động. Với nhóm làm việc trên nhiều hệ điều hành, một công cụ quản lý phiên bản giúp giảm khác biệt cấu hình giữa các máy.

### 3.1. Dùng mise để quản lý theo dự án

[mise](https://mise.jdx.dev/) hỗ trợ Windows, macOS và Linux. Công cụ này có thể cài JDK từ nhiều nhà cung cấp, đặt `JAVA_HOME` theo phiên bản mà dự án chọn và lưu cấu hình trong file `mise.toml`.

Sau khi cài mise theo hướng dẫn chính thức cho hệ điều hành và kích hoạt shell tương ứng, mở terminal tại thư mục dự án rồi chạy:

```bash
# Cài và chọn bản Temurin mới nhất thuộc dòng Java 25 cho dự án.
mise use java@temurin-25

# Kiểm tra Java và trình biên dịch đang được mise chọn.
mise exec -- java -version
mise exec -- javac -version

# Xem các bản Java đã cài.
mise ls java
```

Để chọn JDK 27 cho một dự án khác, chạy lệnh trong thư mục dự án đó:

```bash
mise use java@temurin-27
```

Lệnh `mise use` cài phiên bản còn thiếu và ghi yêu cầu phiên bản vào cấu hình dự án. Có thể commit `mise.toml` vào Git để các thành viên dùng chung yêu cầu phiên bản. Việc ghi rõ nhà cung cấp, chẳng hạn `temurin`, giúp tránh trường hợp mỗi máy tự chọn một bản phân phối khác nhau.

Muốn đặt JDK mặc định cho tài khoản người dùng thay vì cho riêng dự án:

```bash
mise use --global java@temurin-25
```

Một số lệnh hữu ích:

| Lệnh | Tác dụng |
| --- | --- |
| `mise ls java` | Liệt kê các phiên bản Java đã cài |
| `mise where java` | In đường dẫn cài đặt của JDK đang được chọn |
| `mise current java` | Hiển thị phiên bản đang có hiệu lực trong thư mục hiện tại |
| `mise doctor` | Kiểm tra cấu hình và tích hợp shell |
| `mise exec -- java -version` | Chạy lệnh Java trong môi trường mise |

Mise cần được kích hoạt trong shell để các lệnh Java thông thường và biến môi trường được cập nhật theo thư mục hiện tại. Nếu lệnh chạy qua `mise exec` đúng nhưng `java` trực tiếp vẫn ra phiên bản cũ, hãy kiểm tra shell activation, `PATH` và các dòng tự đặt `JAVA_HOME` trong file cấu hình shell. IDE đọc biến môi trường lúc khởi động có thể cần khởi động lại sau khi đổi JDK.

### 3.2. Dùng SDKMAN trên Linux, macOS hoặc WSL

[SDKMAN!](https://sdkman.io/) phù hợp với Bash và Zsh trên Linux, macOS và Windows Subsystem for Linux (WSL). SDKMAN yêu cầu môi trường Bash; không cài trực tiếp trong PowerShell hoặc Command Prompt của Windows. Nếu dùng Windows, có thể cài SDKMAN bên trong một bản phân phối WSL.

Liệt kê các bản Java SDKMAN có thể cài:

```bash
sdk list java
```

Chọn mã phiên bản cụ thể trong danh sách rồi cài đặt, ví dụ:

```bash
sdk install java <version-identifier>
```

Thay `<version-identifier>` bằng mã chính xác hiển thị từ `sdk list java`; mã thường chứa số phiên bản và hậu tố nhà cung cấp. Không nên sao chép một mã phiên bản cũ từ bài hướng dẫn khác vì danh sách bản dựng thay đổi theo thời gian.

Chuyển JDK trong terminal hiện tại:

```bash
sdk use java <version-identifier>
```

Đặt JDK mặc định cho các terminal mới:

```bash
sdk default java <version-identifier>
```

Kiểm tra phiên bản đang dùng:

```bash
sdk current java
java -version
javac -version
```

Để lưu yêu cầu JDK theo dự án, vào thư mục dự án và tạo file `.sdkmanrc`:

```bash
sdk env init
```

File được tạo sẽ chứa phiên bản SDK đang sử dụng. Sau khi chỉnh giá trị `java` thành mã phiên bản mà dự án yêu cầu, nạp cấu hình bằng:

```bash
sdk env install
sdk env
```

`sdk env install` cài các SDK còn thiếu được khai báo trong `.sdkmanrc`; `sdk env` chuyển shell hiện tại sang các phiên bản đó. Có thể bật `sdkman_auto_env=true` trong cấu hình SDKMAN để tự chuyển đổi khi đi vào hoặc rời thư mục dự án. Chỉ commit `.sdkmanrc` khi nhóm đã thống nhất cách quản lý và mã phiên bản.

JDK cài bên trong WSL thuộc môi trường Linux của WSL. Ứng dụng Windows như IntelliJ IDEA chạy bên ngoài WSL không tự động dùng được đường dẫn JDK Linux đó; hãy cấu hình IDE chạy trong WSL hoặc cài thêm một JDK dành cho Windows.

### 3.3. Cài JDK trực tiếp và chọn bằng biến môi trường

Nếu máy chỉ cần một vài JDK hoặc tổ chức đã có quy trình cài đặt tập trung, có thể cài từng bản từ trang chính thức của nhà cung cấp. Đặt chúng trong các thư mục riêng, dễ nhận diện theo nhà cung cấp và phiên bản, ví dụ:

```text
C:\Java\temurin-25\
C:\Java\temurin-27\
```

Trên macOS hoặc Linux, đường dẫn có thể tương tự:

```text
/opt/jdks/temurin-25/
/opt/jdks/temurin-27/
```

Các đường dẫn trên chỉ là ví dụ; hãy dùng đường dẫn thực tế của bộ cài trên máy.

**Windows PowerShell — đổi JDK tạm thời trong cửa sổ terminal hiện tại:**

```powershell
$env:JAVA_HOME = 'C:\Java\temurin-25'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
```

Để chuyển sang JDK 27 trong cùng cửa sổ:

```powershell
$env:JAVA_HOME = 'C:\Java\temurin-27'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
```

Đây là cấu hình theo phiên terminal. Muốn đặt mặc định lâu dài trên Windows, mở **Edit the system environment variables → Environment Variables**, đặt `JAVA_HOME` trỏ đến thư mục gốc của JDK và đặt `%JAVA_HOME%\bin` trong `Path`. Mở terminal mới sau khi thay đổi để nhận cấu hình. Tránh dùng `setx PATH` để nối thêm đường dẫn một cách tùy tiện vì có thể tạo giá trị `Path` sai hoặc làm mất các mục đã có.

**Linux hoặc macOS — đổi JDK tạm thời trong shell hiện tại:**

```bash
export JAVA_HOME=/opt/jdks/temurin-25
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
```

Để dùng JDK 27, đổi đường dẫn trong `JAVA_HOME` sang thư mục JDK 27 rồi cập nhật `PATH`. Có thể đặt cấu hình mặc định trong file khởi tạo shell, nhưng không nên thêm nhiều đường dẫn JDK cố định vào `PATH` ở nhiều vị trí. Những mục cũ có thể đứng trước JDK vừa chọn và khiến terminal chạy nhầm phiên bản.

Trên macOS, có thể xem các JDK được hệ điều hành nhận diện bằng:

```bash
/usr/libexec/java_home -V
```

Chọn một JDK đã được đăng ký theo major version:

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 25)
export PATH="$JAVA_HOME/bin:$PATH"
```

Không phải mọi bộ JDK do công cụ quản lý phiên bản cài đều tự động được đăng ký để mọi ứng dụng macOS tìm thấy qua `java_home`. Nếu IDE hoặc ứng dụng đồ họa không thấy JDK, hãy kiểm tra cách ứng dụng đó phát hiện JDK và hướng dẫn tích hợp của công cụ đang dùng.

## 4. Chọn JDK riêng cho từng dự án

Đổi `JAVA_HOME` toàn máy là cách đơn giản nhưng không đủ tin cậy khi nhiều dự án yêu cầu các JDK khác nhau. Hãy lưu yêu cầu phiên bản ở cấp dự án bằng trình quản lý phiên bản, sau đó cấu hình build tool để xác định JDK biên dịch và chạy test.

### 4.1. Cấu hình Java toolchain trong Gradle

Gradle Java Toolchains cho phép khai báo phiên bản JDK mà các task biên dịch, test và tạo Javadoc cần dùng. Ví dụ với Groovy DSL trong `build.gradle`:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}
```

Với Kotlin DSL trong `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}
```

Đổi `25` thành `27` khi dự án thực sự yêu cầu JDK 27. Gradle sẽ tìm JDK phù hợp đã cài trên máy; nếu không tìm thấy, Gradle có thể tải JDK tự động khi dự án đã cấu hình toolchain download repository. Không nên giả định mọi dự án đều bật sẵn khả năng tải tự động.

Phiên bản JDK chạy Gradle và phiên bản JDK dùng để biên dịch là hai lựa chọn có liên quan nhưng không đồng nhất. Có thể xem phiên bản JVM mà Gradle đang chạy bằng:

```bash
./gradlew --version
```

Trên Windows dùng:

```powershell
.\gradlew.bat --version
```

Nếu cần chạy Gradle bằng một JDK khác, kiểm tra cấu hình Gradle JVM, `org.gradle.java.home` hoặc Daemon JVM criteria. Daemon JVM criteria, khi đã cấu hình, được ưu tiên hơn `JAVA_HOME` và `org.gradle.java.home`. Luôn đối chiếu ma trận tương thích của phiên bản Gradle Wrapper đang dùng. Theo ma trận hiện hành tại thời điểm biên soạn, cần Gradle 9.8 trở lên để hỗ trợ JDK 27 làm toolchain; Gradle 9.8 trở lên cũng hỗ trợ chạy trên JVM 27.

### 4.2. Phân biệt toolchain và `--release`

Toolchain quyết định JDK thực sự được dùng để biên dịch. Còn tùy chọn `--release` giới hạn ngôn ngữ, bytecode và API Java mà mã nguồn được phép sử dụng. Khi cần biên dịch bằng JDK mới nhưng vẫn phát hành ứng dụng cho một phiên bản Java thấp hơn, có thể kết hợp cả hai.

Ví dụ, dùng JDK 25 để biên dịch nhưng chỉ cho phép API và bytecode của Java 21:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

`sourceCompatibility` và `targetCompatibility` chỉ đặt mức tương thích nguồn và bytecode; chúng không tự chọn JDK cài trên máy và không thay thế đầy đủ cho toolchain. Với build mới, ưu tiên toolchain và dùng `--release` khi cần khóa API mục tiêu.

### 4.3. Cấu hình JDK toolchain trong Maven

Maven Toolchains cho phép dự án chọn JDK để các plugin tương thích sử dụng, độc lập với JDK đang chạy Maven. Cách này cần hai phần: cấu hình `maven-toolchains-plugin` trong `pom.xml` và khai báo đường dẫn JDK trên máy build trong `toolchains.xml`.

Ví dụ phần cấu hình plugin trong `pom.xml` để yêu cầu Temurin 25:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.16.0</version>
</plugin>
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
                <version>25</version>
                <vendor>temurin</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

Tạo file `toolchains.xml` trong thư mục `${user.home}/.m2/` trên từng máy phát triển hoặc máy CI:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>25</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/path/to/temurin-25</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Thay `/path/to/temurin-25` bằng đường dẫn thực tế của JDK trên máy. Trên Windows, dùng đường dẫn JDK Windows tương ứng. Không commit đường dẫn cá nhân vào kho mã nguồn vì mỗi máy có thể cài JDK ở vị trí khác nhau.

Maven Toolchains Plugin từ phiên bản 3.2.0 còn có thể tự phát hiện JDK đã cài qua goal `toolchains:select-jdk-toolchain`. Nếu sử dụng cơ chế này, hãy cấu hình tiêu chí phiên bản và nhà cung cấp rõ ràng, sau đó kiểm tra JDK thực tế được chọn. Không giả định mọi Maven plugin đều hỗ trợ toolchain; hãy kiểm tra tài liệu của plugin đang dùng.

`mvn -version` cho biết JVM chạy Maven. Kết quả này có thể khác JDK được toolchain chọn để biên dịch. Khi cần xác minh cấu hình Maven, hãy kiểm tra cả phiên bản Maven, toolchains plugin, `toolchains.xml` và output của build.

## 5. Cấu hình JDK trong IDE

IDE có thể duy trì nhiều JDK và gán chúng cho từng project. Đây là cấu hình riêng của IDE, vì vậy cần đồng bộ với build tool.

### IntelliJ IDEA

1. Mở **File → Project Structure → Project** và chọn **Project SDK** phù hợp.
2. Kiểm tra **Project language level** để bảo đảm mức cú pháp Java phù hợp với mã nguồn.
3. Nếu dự án dùng Gradle, mở **Settings → Build, Execution, Deployment → Build Tools → Gradle** và chọn **Gradle JVM** phù hợp với phiên bản Gradle Wrapper.
4. Giữ cấu hình Java toolchain trong build script để build từ terminal và CI cũng chọn đúng JDK.

Project SDK, language level và Gradle JVM giải quyết các mục đích khác nhau. Chọn Project SDK không tự bảo đảm Gradle dùng cùng JDK nếu Gradle JVM hoặc toolchain đã được cấu hình riêng.

### Eclipse

1. Mở **Window → Preferences → Java → Installed JREs** để thêm các JDK đã cài.
2. Chọn JDK mặc định cho workspace nếu cần.
3. Với từng project, mở **Properties → Java Build Path** để kiểm tra JRE System Library.
4. Kiểm tra **Java Compiler** để đặt mức tuân thủ ngôn ngữ phù hợp.
5. Nếu dự án dùng Maven hoặc Gradle, kiểm tra cấu hình JDK của build integration.

### Visual Studio Code

Với Extension Pack for Java, VS Code có thể phát hiện các JDK đã cài và cho phép cấu hình runtime Java trong `settings.json`. Dùng lệnh **Java: Configure Java Runtime** để xem các runtime được phát hiện và chọn cấu hình cho project. Nếu terminal tích hợp hoặc Maven/Gradle chạy một JDK khác, hãy kiểm tra riêng `JAVA_HOME`, `PATH` và cấu hình toolchain của build.

## 6. Xác minh JDK đang thực sự được sử dụng

Sau khi cài hoặc chuyển đổi phiên bản, hãy kiểm tra cả đường dẫn lẫn phiên bản. Một máy có thể có nhiều executable `java` trên `PATH`.

**Windows PowerShell:**

```powershell
$env:JAVA_HOME
java -version
javac -version
Get-Command java -All
Get-Command javac -All
```

`Get-Command ... -All` liệt kê các lệnh có thể được PowerShell tìm thấy, giúp nhận diện một JDK cũ đang đứng trước JDK mong muốn.

**Linux và macOS:**

```bash
echo "$JAVA_HOME"
java -version
javac -version
command -v java
command -v javac
type -a java
```

`command -v` cho biết executable được shell phân giải đầu tiên; `type -a` liệt kê các kết quả cùng tên trong môi trường shell.

**Kiểm tra build tool:**

```bash
mvn -version
./gradlew --version
```

Trên Windows, dùng `mvn -version` và `.\gradlew.bat --version` trong PowerShell. Nếu dùng Gradle toolchain, có thể chạy build với log chi tiết để xem Gradle phát hiện và chọn JDK nào. Nếu dùng Maven Toolchains, kiểm tra cấu hình plugin và `toolchains.xml`.

## 7. Xử lý các lỗi thường gặp

### Terminal vẫn chạy phiên bản Java cũ

Nguyên nhân thường là thư mục `bin` của JDK cũ đứng trước trong `PATH`, hoặc shell chưa nạp cấu hình mới. Hãy xem `Get-Command java -All` trên PowerShell hoặc `type -a java` trên Bash/Zsh; sau đó sửa thứ tự `PATH`, kiểm tra `JAVA_HOME` và mở terminal mới. Nếu dùng mise hoặc SDKMAN, xác nhận shell đã kích hoạt công cụ và dự án đang nằm trong đúng thư mục cấu hình.

### `java -version` đúng nhưng `javac` không tồn tại

Máy có thể đang trỏ đến runtime không chứa bộ công cụ biên dịch, hoặc `java` và `javac` đến từ hai đường dẫn khác nhau. Cài JDK đầy đủ, đặt `JAVA_HOME` vào thư mục gốc JDK và kiểm tra `PATH` trỏ đến `JAVA_HOME/bin`.

### IDE dùng JDK khác terminal

IDE có thể đã lưu Project SDK hoặc Gradle JVM riêng, hoặc được mở trước khi thay đổi biến môi trường. Kiểm tra cấu hình JDK trong IDE, sau đó khởi động lại IDE nếu ứng dụng đọc biến môi trường khi khởi động. Kiểm tra thêm toolchain trong build script.

### Gradle báo không hỗ trợ phiên bản Java

Gradle phải chạy trên một JVM được phiên bản Gradle đó hỗ trợ. JDK được dùng làm toolchain để biên dịch cũng cần nằm trong phạm vi hỗ trợ của Gradle Wrapper và plugin. Đối chiếu ma trận tương thích chính thức, cập nhật Gradle Wrapper và plugin theo kế hoạch nâng cấp của dự án. Không chỉ cài JDK mới rồi kỳ vọng một Gradle Wrapper cũ sẽ chạy được trên đó.

### Maven biên dịch bằng JDK không mong muốn

`JAVA_HOME` có thể chỉ điều khiển JVM chạy Maven, trong khi toolchain trong `pom.xml` chọn JDK khác cho compiler hoặc test plugin. Kiểm tra `mvn -version`, cấu hình `maven-toolchains-plugin`, các entry trong `toolchains.xml` và phiên bản plugin có hỗ trợ toolchain hay không.

### Máy chạy được nhưng CI thất bại

Máy cá nhân có thể đang dùng JDK đã cài sẵn hoặc cấu hình IDE riêng mà pipeline không có. Hãy khai báo phiên bản JDK trong cấu hình build, cấu hình cài JDK rõ ràng trong CI/container và dùng cùng Gradle Wrapper hoặc Maven Wrapper. Không dựa vào phiên bản Java mặc định tình cờ có trên runner.

## 8. Nguyên tắc quản lý lâu dài

- **Chọn phiên bản theo yêu cầu dự án:** ghi rõ phiên bản Java mục tiêu, mức tương thích framework và thời hạn hỗ trợ.
- **Ưu tiên LTS cho hệ thống duy trì dài hạn:** dùng feature release như JDK 27 khi có lý do kỹ thuật cụ thể và kế hoạch cập nhật phù hợp.
- **Chuẩn hóa nhà cung cấp:** nhóm nên thống nhất một bản phân phối JDK, trừ khi đang kiểm thử tính tương thích giữa các nhà cung cấp.
- **Khai báo JDK ở cấp dự án:** dùng `mise.toml`, `.sdkmanrc` hoặc cơ chế tương đương để mô tả môi trường phát triển; dùng Gradle/Maven toolchain để mô tả môi trường build.
- **Không commit đường dẫn máy cá nhân:** các đường dẫn cài đặt như `C:\Java\...` hoặc `/opt/jdks/...` nên nằm trong cấu hình cục bộ.
- **Cập nhật bản vá bảo mật:** theo dõi thông báo của nhà cung cấp, kiểm thử bản cập nhật trong CI rồi nâng cấp định kỳ. Pin major version không có nghĩa là giữ mãi một bản vá cũ.
- **Kiểm tra cả IDE và CI:** chạy build bằng wrapper của dự án và bảo đảm kết quả không phụ thuộc JDK mặc định trên máy.
- **Gỡ phiên bản hết nhu cầu một cách có kiểm soát:** trước khi xóa JDK, kiểm tra dự án, IDE, service và pipeline còn tham chiếu đến nó hay không.

## 9. Quy trình mẫu cho một nhóm phát triển

Giả sử nhóm đang bảo trì một dịch vụ Java 21, phát triển dịch vụ mới trên Java 25 LTS và có một nhánh thử nghiệm Java 27. Có thể tổ chức môi trường như sau:

1. Cài JDK 21, 25 và 27 từ nhà cung cấp đã được nhóm thống nhất.
2. Mỗi repository khai báo phiên bản và nhà cung cấp JDK trong file cấu hình trình quản lý phiên bản, chẳng hạn `mise.toml`.
3. Gradle hoặc Maven khai báo toolchain tương ứng để compiler và test dùng đúng JDK.
4. Thành viên chọn đúng Project SDK và Gradle JVM trong IDE.
5. CI cài hoặc tải đúng JDK, sử dụng wrapper đã commit và chạy cùng bộ kiểm thử.
6. Khi nâng cấp JDK, nhóm kiểm tra plugin build, framework, thư viện, test, image triển khai và thời hạn hỗ trợ trước khi thay đổi cấu hình chung.

Với cách tổ chức này, một máy có thể phục vụ nhiều dự án Java mà không cần liên tục thay đổi JDK mặc định toàn hệ thống. Mỗi dự án có yêu cầu rõ ràng, còn build tool và CI chịu trách nhiệm thực thi yêu cầu đó.

## Tài liệu tham khảo

- [Oracle — JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Oracle — Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
- [OpenJDK — Java Release Timeline](https://ops.java/releases/?lang=en)
- [mise — Java](https://mise.jdx.dev/lang/java.html)
- [mise — Installation](https://mise.jdx.dev/installing-mise.html)
- [SDKMAN! — Installation](https://sdkman.io/install/)
- [SDKMAN! — Usage and project environments](https://sdkman.io/usage/)
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Java compatibility matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [Apache Maven — JDK toolchain selection](https://maven.apache.org/plugins/maven-toolchains-plugin/select-jdk-toolchain-mojo.html)
- [Microsoft Learn — Get started with Java on Windows](https://learn.microsoft.com/en-us/windows/dev-environment/java)
