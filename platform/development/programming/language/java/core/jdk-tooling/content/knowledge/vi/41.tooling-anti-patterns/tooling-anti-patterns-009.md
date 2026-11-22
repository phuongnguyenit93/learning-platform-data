# Script phụ thuộc máy cá nhân trong Java tooling

## 1. Anti-pattern này là gì?

**Script phụ thuộc máy cá nhân** là script chỉ chạy đúng trên máy của người viết vì nó âm thầm dựa vào cấu hình, phần mềm, đường dẫn, quyền truy cập hoặc trạng thái riêng của máy đó.

Ví dụ thường gặp:

- Gọi mvn từ PATH và vô tình dùng phiên bản Maven chỉ có trên máy người viết.
- Ghi cứng C:/Users/An/..., /Users/an/... hoặc /home/an/....
- Giả định thư mục hiện tại luôn là thư mục gốc repository.
- Dựa vào JDK được IDE chọn, trong khi CI lại dùng JDK khác.
- Đọc file cấu hình từ Desktop, home directory hoặc thư mục ngoài repository mà không khai báo.
- Dùng biến môi trường có trên máy cá nhân nhưng không được cấu hình ở CI.
- Phụ thuộc vào shell profile, alias, global package hoặc executable cài thủ công.
- Dựa vào cache, file tạm, service hoặc credential còn sót lại từ lần chạy trước.

Script có thể chạy thành công nhiều tháng trên một máy và thất bại ngay khi đồng đội clone repository, CI tạo runner mới hoặc dự án chuyển sang Windows/Linux khác.

Mục tiêu của việc sửa anti-pattern là làm cho đầu vào, công cụ, đường dẫn và điều kiện chạy được khai báo rõ ràng, có thể kiểm tra và tái tạo.

## 2. Dấu hiệu nhận biết

Một script có nguy cơ phụ thuộc máy cá nhân nếu xuất hiện một trong các dấu hiệu sau:

| Dấu hiệu | Vì sao rủi ro |
|---|---|
| Đường dẫn chứa tên user | Máy khác có home directory khác. |
| Gọi mvn, java hoặc node mà không kiểm tra version | PATH có thể chọn executable khác. |
| Dùng đường dẫn tương đối từ current directory | Kết quả thay đổi theo nơi gọi script. |
| Đọc file ngoài repository | File có thể không tồn tại trên máy mới hoặc CI. |
| Dựa vào ~/.m2/settings.xml để có thông tin bắt buộc | CI hoặc máy khác không có cùng cấu hình. |
| Không khai báo encoding, timezone hoặc locale | Output có thể khác theo hệ điều hành và môi trường. |
| Chạy được chỉ sau khi đã build một lần | Có thể đang dựa vào output/cache cũ. |
| Cần chạy bằng quyền Administrator/root | Có thể đang ghi vào thư mục hệ thống hoặc dùng quyền quá rộng. |
| Dùng secret trong file local | Máy khác không có secret hoặc secret bị lộ khi commit. |

Một dấu hiệu mạnh là câu trả lời cho câu hỏi: “Nếu xóa sạch cache, clone repository vào một thư mục mới có khoảng trắng trong tên và chạy trên runner mới, script có còn hoạt động không?”

## 3. Những loại phụ thuộc ẩn

| Loại phụ thuộc | Ví dụ | Hướng xử lý |
|---|---|---|
| User identity | user.name, home directory | Không dùng để định vị source hoặc output cố định. |
| Working directory | . hoặc ../config | Xác định project root từ vị trí script hoặc truyền tham số. |
| Tool installation | Maven/JDK cài global | Maven Wrapper, JDK version policy và Toolchains. |
| PATH precedence | Nhiều bản java | Kiểm tra JAVA_HOME, version và executable được chọn. |
| Shell | Bash, PowerShell, cmd | Chọn shell rõ ràng và có script phù hợp. |
| Operating system | Windows/Linux/macOS | Dùng API path và kiểm thử theo OS. |
| Encoding | ANSI, UTF-8, default charset | Chỉ định UTF-8 ở source, build và file I/O. |
| Locale/timezone | Dấu thập phân, ngày tháng, UTC offset | Dùng locale và timezone tường minh. |
| File system | Case sensitivity, permissions | Chuẩn hóa tên file và kiểm thử trên OS. |
| Network | Proxy, repository credentials | Khai báo mirror và inject credential. |
| Local state | Cache, file tạm, daemon | Cache chỉ tối ưu; build phải chạy được từ trạng thái sạch. |

## 4. Kiểm kê môi trường trước khi sửa

Trước tiên, ghi lại những gì script thực sự sử dụng. Không đoán từ máy của người viết.

Trên Windows PowerShell:

~~~powershell
$PSVersionTable.PSVersion
Get-Command java, javac, mvn, git -ErrorAction SilentlyContinue |
    Select-Object Name, Source
java -version
javac -version
if ($env:JAVA_HOME) { Write-Output $env:JAVA_HOME }
Get-Location
Get-Culture
Get-TimeZone
~~~

Trên Bash:

~~~bash
printf 'shell=%s\n' "$SHELL"
command -v java
command -v javac
command -v mvn
java -version
javac -version
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
pwd
locale
date +%Z
~~~

Trong Java, có thể in những system properties hữu ích khi chẩn đoán:

~~~java
System.out.println("java.version=" + System.getProperty("java.version"));
System.out.println("java.vendor=" + System.getProperty("java.vendor"));
System.out.println("os.name=" + System.getProperty("os.name"));
System.out.println("os.arch=" + System.getProperty("os.arch"));
System.out.println("user.dir=" + System.getProperty("user.dir"));
System.out.println("user.home=" + System.getProperty("user.home"));
System.out.println("file.separator=" + System.getProperty("file.separator"));
System.out.println("path.separator=" + System.getProperty("path.separator"));
~~~

Chỉ ghi log những thông tin không nhạy cảm. Không dump toàn bộ environment vì có thể làm lộ token hoặc credential.

## 5. Không ghi cứng home directory và tên user

Ví dụ không portable:

~~~powershell
$project = "C:/Users/An/source/payment-service"
$java = "C:/Program Files/Java/jdk-17/bin/java.exe"
$config = "C:/Users/An/Desktop/release.properties"
~~~

Trên Linux, các đường dẫn tương tự có thể là /home/an/...; trên macOS có thể là /Users/an/.... Không có lý do để repository phụ thuộc vào các giá trị đó.

Hãy phân biệt ba loại đường dẫn:

- **Project path:** lấy từ vị trí repository hoặc script.
- **User configuration path:** lấy từ biến môi trường hoặc thư mục home khi đó thực sự là cấu hình riêng của user.
- **Temporary path:** lấy từ API hoặc biến môi trường của hệ điều hành.

Không thay một đường dẫn cá nhân bằng một đường dẫn tuyệt đối khác rồi coi là portable. C:/Java/jdk-17 hoặc /opt/jdk-17 vẫn là giả định riêng của một máy nếu được ghi vào POM hoặc script dùng chung.

## 6. Xác định project root từ vị trí script

Current working directory là nơi process được gọi, không nhất thiết là nơi script nằm.

Một Bash script có thể được gọi từ bất kỳ thư mục nào. Xác định thư mục chứa script rồi suy ra project root:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

"$PROJECT_ROOT/mvnw" -B -ntp -f "$PROJECT_ROOT/pom.xml" clean verify
~~~

Trong ví dụ, build.sh nằm ở scripts/, còn pom.xml nằm ở thư mục cha.

Các biến đều được đặt trong dấu nháy để đường dẫn có khoảng trắng vẫn là một đối số. CDPATH= tránh shell profile thay đổi kết quả của cd.

Nếu script có thể được gọi qua symbolic link, hãy xác định rõ có cần resolve link về vị trí thật hay không. Không nên mặc định mọi repository đều được gọi qua cùng một kiểu path.

## 7. Dùng $PSScriptRoot trong PowerShell

PowerShell cung cấp $PSScriptRoot để lấy thư mục chứa file script.

~~~powershell
$ErrorActionPreference = "Stop"

$scriptDirectory = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDirectory
$pom = Join-Path $projectRoot "pom.xml"
$wrapper = Join-Path $projectRoot "mvnw.cmd"

if (-not (Test-Path -LiteralPath $pom)) {
    throw "POM not found: $pom"
}

Push-Location $projectRoot
try {
    & $wrapper -B -ntp clean verify
    if ($LASTEXITCODE -ne 0) {
        throw "Maven failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
~~~

Join-Path tạo path theo hệ điều hành. Push-Location và Pop-Location bảo đảm thư mục hiện tại được khôi phục kể cả khi build thất bại.

$ErrorActionPreference = "Stop" giúp PowerShell dừng với lỗi cmdlet. Lệnh native như java.exe hoặc mvnw.cmd có exit code riêng; phải kiểm tra $LASTEXITCODE.

## 8. Phân biệt project path, user home và current directory trong Java

Java cung cấp các system properties khác nhau:

| Property | Ý nghĩa |
|---|---|
| user.dir | Working directory của process. |
| user.home | Home directory của user đang chạy. |
| user.name | Tên account của process. |
| java.home | Runtime home của JVM. |
| file.separator | Dấu phân cách thành phần path. |
| path.separator | Dấu phân cách các phần tử classpath. |
| line.separator | Dấu xuống dòng của môi trường. |
| os.name, os.arch | Hệ điều hành và kiến trúc. |

user.dir có thể thay đổi giữa terminal, IDE, service và CI. Vì vậy, không nên giả định file project luôn nằm dưới user.dir.

user.home thích hợp cho dữ liệu cấu hình/cache riêng của user khi ứng dụng thực sự cần lưu ở đó. Không dùng nó để tìm source code hoặc file bắt buộc của project.

Nếu ứng dụng cần file cấu hình, hãy nhận đường dẫn qua CLI option hoặc environment variable. Nếu tài nguyên được đóng gói trong JAR, hãy đọc từ classpath bằng getResource thay vì tìm file bên cạnh thư mục chạy.

## 9. Dùng Path và Files thay cho nối chuỗi đường dẫn

Không tạo path bằng cách cộng chuỗi:

~~~java
String output = System.getProperty("user.home") + "/build/output.txt";
~~~

Cách này phụ thuộc dấu phân cách và home directory.

Dùng Java NIO:

~~~java
import java.nio.file.Path;

Path project = Path.of("project");
Path output = project.resolve("build").resolve("output.txt");
Path normalized = output.toAbsolutePath().normalize();
~~~

Path.resolve kết hợp các path component theo quy tắc của file system. normalize loại bỏ các phần tử . và .. dư thừa về mặt từ vựng; nó không thay thế việc kiểm tra quyền hoặc symbolic link.

Với file I/O, chỉ định charset:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("build", "result.txt");
Files.createDirectories(file.getParent());
Files.writeString(file, "Build complete\n", StandardCharsets.UTF_8);

String content = Files.readString(file, StandardCharsets.UTF_8);
System.out.println(content);
~~~

Trong ứng dụng thật, path đầu vào cần được kiểm tra theo phạm vi được phép ghi. Không cho phép user-controlled path thoát khỏi thư mục output dự kiến.

## 10. Maven Wrapper pin phiên bản Maven

Không nên yêu cầu mỗi developer tự cài Maven rồi thêm một bản bất kỳ vào PATH.

Maven Wrapper đặt phiên bản Maven trong repository và cung cấp script cho Unix và Windows. Khi chưa có distribution tương ứng, wrapper tải và cài nó vào cache của user.

Khởi tạo wrapper bằng Maven Wrapper Plugin:

~~~bash
mvn org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.12 -Dtype=only-script
~~~

Các file quan trọng:

~~~text
.mvn/
  wrapper/
    maven-wrapper.properties
mvnw
mvnw.cmd
~~~

File .mvn/wrapper/maven-wrapper.properties có thể chứa:

~~~properties
wrapperVersion=3.3.4
distributionType=only-script
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.12/apache-maven-3.9.12-bin.zip
~~~

Dùng:

~~~bash
./mvnw -B -ntp clean verify
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd -B -ntp clean verify
~~~

only-script dùng wrapper scripts để tải Maven distribution. Các kiểu phân phối khác có thể đóng gói wrapper JAR hoặc downloader source.

Maven Wrapper pin Maven, không tự cài JDK. Máy chạy build vẫn phải có một JDK phù hợp. Distribution URL và checksum cần được quản lý như dependency đầu vào; có thể khai báo distributionSha256Sum trong wrapper properties sau khi lấy SHA-256 chính thức của distribution.

## 11. Kiểm tra JDK thay vì tin vào PATH

Trên một máy có nhiều JDK, java và javac có thể đến từ các thư mục khác nhau.

Windows:

~~~powershell
Get-Command java, javac | Select-Object Name, Source
$env:JAVA_HOME
java -version
javac -version
.\mvnw.cmd -version
~~~

Bash:

~~~bash
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
java -version
javac -version
./mvnw -version
~~~

JAVA_HOME nên trỏ tới JDK được chọn. PATH nên đưa thư mục bin của JDK đó lên trước những bản khác.

Không ghi cứng đường dẫn JDK của một developer vào script. Mỗi máy hoặc CI runner có thể cài JDK ở vị trí khác nhau.

## 12. Dùng Maven Enforcer để báo lỗi sớm

Nếu project yêu cầu JDK 17 trở lên, hãy khai báo yêu cầu trong POM thay vì để lỗi compiler xuất hiện ở giữa build.

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-enforcer-plugin</artifactId>
      <version>3.5.0</version>
      <executions>
        <execution>
          <id>require-supported-java</id>
          <goals>
            <goal>enforce</goal>
          </goals>
          <configuration>
            <rules>
              <requireJavaVersion>
                <version>[17,)</version>
              </requireJavaVersion>
            </rules>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

[17,) chấp nhận JDK 17 trở lên. Nếu build phải chạy đúng compiler JDK 17, dùng khoảng [17,18) và cấu hình Toolchains ở phần tiếp theo.

maven.compiler.release điều khiển ngôn ngữ, bytecode target và Java platform API mà compiler cho phép sử dụng. Nó không có nghĩa Maven đang chạy bằng JDK 17.

## 13. Dùng Maven Toolchains khi cần compiler JDK cụ thể

Maven có thể chạy bằng một JDK nhưng giao compiler và các plugin hỗ trợ toolchain cho một JDK khác.

Trong POM, khai báo yêu cầu logic:

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
      <configuration>
        <toolchains>
          <jdk>
            <version>[17,18)</version>
          </jdk>
        </toolchains>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

Mỗi máy khai báo vị trí JDK trong file riêng ~/.m2/toolchains.xml:

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

jdkHome là đường dẫn cài đặt thực tế trên máy cụ thể. File này nằm ngoài repository; không commit đường dẫn local vào POM.

Trong CI, action cài JDK có thể tạo Maven Toolchains entry cho JDK vừa cài. Nếu không tìm được toolchain phù hợp, build nên dừng sớm với lỗi rõ ràng.

## 14. Pin dependency và Maven plugin

Script có thể chạy khác nhau nếu Maven tự resolve phiên bản dependency hoặc plugin khác nhau.

Các quy tắc:

- Khai báo version rõ ràng cho plugin dùng trong build.
- Dùng pluginManagement ở parent POM để quản lý version thống nhất.
- Dùng dependencyManagement để kiểm soát version dependency.
- Tránh version range, LATEST, RELEASE và SNAPSHOT trong stable release.
- Dùng Maven Wrapper để pin Maven distribution.
- Kiểm tra repository/mirror được dùng để resolve dependency.
- Cập nhật version có review và chạy lại CI.

Ví dụ pin compiler plugin:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>17</release>
    <encoding>UTF-8</encoding>
  </configuration>
</plugin>
~~~

Không dựa vào plugin đã cài global trong thư mục Maven local. Build phải resolve được plugin từ repository đã cấu hình.

## 15. Tách cấu hình ứng dụng khỏi source code

Không nhúng endpoint, đường dẫn output, account name hoặc credential vào Java source và script.

Dùng CLI option hoặc environment variable:

~~~powershell
$env:APP_MESSAGE = "portable build"
.\mvnw.cmd -B -ntp clean verify
java -jar target\portable-script-demo-1.0.0.jar build-output
~~~

~~~bash
export APP_MESSAGE="portable build"
./mvnw -B -ntp clean verify
java -jar target/portable-script-demo-1.0.0.jar build-output
~~~

Ứng dụng cần kiểm tra biến bắt buộc ngay khi khởi động. Nếu thiếu, thông báo tên biến cần cấu hình và thoát với mã lỗi khác 0.

Environment variable phù hợp với cấu hình runtime và secret được inject. Với cấu hình phức tạp, có thể dùng file cấu hình được truyền bằng CLI option như --config; không tự tìm file ở Desktop hoặc thư mục home.

## 16. Quản lý secret đúng cách

Không commit:

- Password, API token hoặc private key.
- File settings.xml có credential thật.
- .env cá nhân.
- Certificate/private signing key.
- Dump toàn bộ environment.

Dùng secret manager của CI hoặc hệ thống quản lý secret của tổ chức. Cấp quyền theo job và chỉ truyền secret tới bước cần sử dụng.

Ví dụ GitHub Actions:

~~~yaml
- name: Publish package
  run: ./mvnw -B -ntp deploy
  env:
    PUBLISH_TOKEN: ${{ secrets.PUBLISH_TOKEN }}
~~~

Trong script, đọc PUBLISH_TOKEN từ environment và kiểm tra nó có giá trị. Không in token ra log và không đưa token vào command-line argument nếu process list có thể hiển thị argument.

Nếu cần Maven credentials, sinh settings.xml trong workspace tạm của CI hoặc dùng action hỗ trợ cấu hình Maven settings. Không đưa credential vào POM.

## 17. Không giả định current working directory

Đoạn sau dễ lỗi:

~~~bash
mvn -f ../pom.xml clean verify
cp config/app.properties target/
~~~

Kết quả phụ thuộc thư mục gọi lệnh.

Hãy xác định project root một lần và dùng path rõ ràng:

~~~bash
PROJECT_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
"$PROJECT_ROOT/mvnw" -B -ntp -f "$PROJECT_ROOT/pom.xml" clean verify
cp "$PROJECT_ROOT/config/app.properties" "$PROJECT_ROOT/target/"
~~~

Trong GitHub Actions, có thể khai báo working-directory cho từng bước hoặc toàn job. Dù vậy, script dùng lại ngoài CI vẫn nên tự tìm project root hoặc nhận path rõ ràng.

## 18. Encoding, locale và timezone

Một script chạy trên máy cá nhân có thể dựa vào encoding mặc định, locale hoặc timezone hiện tại.

Với Java 17, encoding mặc định có thể phụ thuộc môi trường. Hãy chỉ định UTF-8 trong POM:

~~~xml
<properties>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Khi đọc/ghi file, dùng StandardCharsets.UTF_8:

~~~java
Files.writeString(path, content, StandardCharsets.UTF_8);
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

Khi parse/format dữ liệu không dành cho người dùng, dùng Locale.ROOT thay vì locale mặc định. Với timestamp dùng trong log hoặc artifact metadata, ưu tiên UTC và Instant/ZoneOffset.UTC.

Không so sánh chuỗi ngày giờ đã format theo locale của máy. Dùng ISO-8601 hoặc một định dạng được quy định rõ.

## 19. Xử lý temporary files và permissions

Không ghi vào một thư mục cố định như /tmp/my-build, C:/temp/build hoặc Desktop của user. Hai lần chạy song song có thể ghi đè lẫn nhau và máy khác có thể không có thư mục đó.

Java cung cấp API tạo temporary directory:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

Path temporaryDirectory = Files.createTempDirectory("java-build-");
Path temporaryFile = Files.createTempFile(temporaryDirectory, "report-", ".txt");
~~~

Dùng try/finally hoặc cơ chế cleanup phù hợp để xóa file tạm khi hoàn thành. Nếu file phải tồn tại sau khi process kết thúc, hãy lưu trong output directory được truyền vào và công bố vị trí đó.

Không yêu cầu quyền Administrator/root nếu không cần. Build nên ghi vào workspace, target/ hoặc thư mục được cấp quyền rõ ràng.

## 20. Quoting và truyền tham số giữa shell

Shell có quy tắc parse khác nhau. Đường dẫn có khoảng trắng, dấu ngoặc hoặc ký tự đặc biệt dễ bị tách thành nhiều argument.

Bash:

~~~bash
java -jar "$PROJECT_ROOT/target/app.jar" "$APP_MESSAGE"
~~~

PowerShell:

~~~powershell
& java -jar $jarPath $Message
~~~

PowerShell dùng call operator & để gọi executable bằng path trong biến. Khi cần nhiều option động, truyền argument dưới dạng array thay vì ghép một command string rồi chạy qua Invoke-Expression.

Tránh eval, Invoke-Expression và string-built command nếu input có thể chứa ký tự đặc biệt. Luôn quote biến trong Bash và dùng Join-Path cho Windows path.

## 21. Line endings và executable bit

Git có thể checkout file với line ending khác nhau theo cấu hình. Script Bash thường cần LF; file .cmd và .ps1 thường được xử lý theo chuẩn Windows.

Có thể thêm .gitattributes:

~~~gitattributes
* text=auto
*.sh text eol=lf
*.cmd text eol=crlf
*.ps1 text eol=crlf
~~~

Trên Unix, script wrapper cần executable bit:

~~~bash
chmod +x mvnw
git update-index --chmod=+x mvnw
~~~

Dùng mvnw.cmd trong Windows PowerShell và ./mvnw trong Bash. Nếu script Bash báo lỗi bad interpreter hoặc ^M, kiểm tra line endings và executable bit trước khi sửa nội dung script.

## 22. Khác biệt file system và kiến trúc

Windows thường không phân biệt chữ hoa/chữ thường trong filename theo cấu hình mặc định, trong khi Linux thường phân biệt.

Ví dụ import hoặc resource lookup tới Config.properties có thể chạy trên Windows nhưng thất bại trên Linux nếu file thật là config.properties.

Ngoài ra, cần chú ý:

- Path separator khác nhau.
- File permissions và executable bit khác nhau.
- Symlink có thể cần quyền hoặc cấu hình riêng trên Windows.
- Tên file có thể chứa ký tự không được hỗ trợ trên một số file system.
- Native library phải khớp OS và architecture.
- Case-only rename có thể không được ghi nhận như mong muốn trên file system không phân biệt case.

Java bytecode thường chạy trên nhiều hệ điều hành, nhưng JNI/native executable và tool ngoài Java vẫn có thể phụ thuộc platform. Nếu có native dependency, kiểm thử đúng OS và architecture mục tiêu.

## 23. Network, proxy và dependency repository

Một script có thể chỉ chạy trên máy cá nhân vì máy đó đã có proxy, VPN, credential hoặc cache dependency.

Cần xác định:

- Maven Central hay internal mirror là nguồn dependency.
- Proxy có bắt buộc không.
- Repository credential được inject ở đâu.
- Build có cần internet trong mọi lần chạy không.
- Dependency nào phải mirror nội bộ để build lâu dài.
- Có kiểm tra checksum/signature cho tool download không.

Không hard-code proxy hostname, token hoặc repository password vào script. Dùng Maven settings.xml, environment variable hoặc secret manager.

Build offline chỉ thành công nếu toàn bộ dependency và plugin đã có trong local repository. mvn -o không phải cách sửa build thiếu dependency; nó chỉ hữu ích sau khi đã chuẩn bị đủ input.

## 24. Cache là tối ưu, không phải điều kiện bắt buộc

Maven local repository thường nằm trong ~/.m2/repository; Gradle cache thường nằm trong ~/.gradle/caches.

Cache có thể được xóa, thay đổi hoặc khác giữa máy. Vì vậy:

- Build sạch phải resolve được dependency từ repository đã khai báo.
- Cache key nên phụ thuộc OS, architecture, POM/Gradle files và wrapper properties.
- Cache miss chỉ làm build chậm hơn, không làm thay đổi kết quả.
- Không lưu output release duy nhất trong cache.
- Không dùng file cũ trong target/ để che lỗi build.

Để kiểm tra độc lập với cache, chạy clean build trên runner mới hoặc local repository trống. Có thể dùng Maven option -Dmaven.repo.local=<temporary-path> trong một lượt kiểm thử riêng.

## 25. Container và Dev Container

Khi nhóm cần cùng một OS image, JDK, Maven và system packages, có thể dùng container hoặc Dev Container.

Container giúp đóng gói user-space tools và dependencies hệ thống. Nó không tự bảo đảm build reproducible nếu image tag trôi, dependency không pin hoặc build script vẫn đọc file từ host.

Thực hành tốt:

- Pin base image bằng version và digest.
- Ghi rõ JDK/Maven version.
- Không copy credential vào image layer.
- Mount source workspace theo cấu trúc rõ ràng.
- Không phụ thuộc file riêng nằm trên host.
- Cấp quyền tối thiểu cho container.
- Giữ cache ở volume riêng có thể xóa và tạo lại.
- Test container build trong CI.

Nếu dùng Dev Container, devcontainer.json nên được commit để cả nhóm chia sẻ cấu hình. Machine-specific credential vẫn được cung cấp bên ngoài repository.

## 26. CI matrix để phát hiện phụ thuộc máy cá nhân

Một build chỉ chạy trên Windows chưa đủ để chứng minh script Bash hoặc path Linux hoạt động. Hãy dùng CI matrix theo hệ điều hành và JDK cần hỗ trợ.

Ví dụ GitHub Actions:

~~~yaml
name: Portable Java build

on:
  push:
  pull_request:

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Build on Unix
        if: runner.os != 'Windows'
        shell: bash
        env:
          APP_MESSAGE: portable build from CI
        run: ./scripts/build.sh

      - name: Build on Windows
        if: runner.os == 'Windows'
        shell: pwsh
        env:
          APP_MESSAGE: portable build from CI
        run: ./scripts/build.ps1
~~~

Ví dụ dùng version tag để dễ đọc. Workflow production nên pin action theo full commit SHA đã review. Có thể thêm matrix JDK nếu sản phẩm hỗ trợ nhiều Java release.

GitHub Actions có thể cấu hình shell và working-directory tường minh. Default shell trên Windows và Unix khác nhau; không dựa vào hành vi mặc định khi script cần chạy trên nhiều hệ điều hành.

## 27. Ví dụ project Maven portable

Cấu trúc project:

~~~text
portable-script-demo/
  .mvn/
    wrapper/
      maven-wrapper.properties
  scripts/
    build.sh
    build.ps1
  src/
    main/
      java/
        example/
          PortableDemo.java
  .gitattributes
  .gitignore
  mvnw
  mvnw.cmd
  pom.xml
~~~

POM mẫu:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.portable</groupId>
  <artifactId>portable-script-demo</artifactId>
  <version>1.0.0</version>

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
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>example.PortableDemo</mainClass>
            </manifest>
          </archive>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-enforcer-plugin</artifactId>
        <version>3.5.0</version>
        <executions>
          <execution>
            <id>require-supported-java</id>
            <goals>
              <goal>enforce</goal>
            </goals>
            <configuration>
              <rules>
                <requireJavaVersion>
                  <version>[17,)</version>
                </requireJavaVersion>
              </rules>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
~~~

POM pin compiler, JAR và Enforcer plugin. maven.compiler.release xác định target Java 17; Enforcer kiểm tra JDK chạy Maven đáp ứng yêu cầu tối thiểu.

## 28. Java program dùng environment và path được truyền vào

File src/main/java/example/PortableDemo.java:

~~~java
package example;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class PortableDemo {
    public static void main(String[] args) throws IOException {
        String message = System.getenv("APP_MESSAGE");
        if (message == null || message.isBlank()) {
            throw new IllegalStateException("APP_MESSAGE is required");
        }
        if (args.length != 1 || args[0].isBlank()) {
            throw new IllegalArgumentException("Pass an output directory");
        }

        Path outputDirectory = Path.of(args[0]).toAbsolutePath().normalize();
        Files.createDirectories(outputDirectory);
        Path outputFile = outputDirectory.resolve("build-info.txt");

        String expected = message + System.lineSeparator();
        Files.writeString(outputFile, expected, StandardCharsets.UTF_8);

        String saved = Files.readString(outputFile, StandardCharsets.UTF_8);
        if (!expected.equals(saved)) {
            throw new IOException("Output verification failed");
        }

        System.out.println("message=" + message);
        System.out.println("output=" + outputFile.getFileName());
    }
}
~~~

Chương trình nhận message qua environment và output directory qua CLI argument. Path xử lý path theo OS; Files tạo directory và file; UTF-8 được chỉ định rõ.

Nó không tìm output trong Desktop, home directory hoặc current working directory. Script gọi chương trình sẽ truyền đường dẫn output dựa trên project root.

## 29. Bash script hoàn chỉnh

File scripts/build.sh:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

if ! printenv APP_MESSAGE >/dev/null; then
  echo "Set APP_MESSAGE before running this script." >&2
  exit 2
fi

"$PROJECT_ROOT/mvnw" -B -ntp -f "$PROJECT_ROOT/pom.xml" clean verify

java -jar \
  "$PROJECT_ROOT/target/portable-script-demo-1.0.0.jar" \
  "$PROJECT_ROOT/build-output"
~~~

Chạy:

~~~bash
APP_MESSAGE="portable build" ./scripts/build.sh
~~~

Nếu shell không nhận cú pháp gán biến trước command, có thể export trước:

~~~bash
export APP_MESSAGE="portable build"
./scripts/build.sh
~~~

Script tìm project root từ chính vị trí của nó, gọi Maven Wrapper bằng absolute path, quote các argument và dừng nếu build hoặc Java process thất bại.

## 30. PowerShell script hoàn chỉnh

File scripts/build.ps1:

~~~powershell
param(
    [Parameter()]
    [string]$Message = $env:APP_MESSAGE
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Message)) {
    throw "Set APP_MESSAGE or pass -Message before running this script."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$wrapper = Join-Path $projectRoot "mvnw.cmd"
$jar = Join-Path $projectRoot "target\portable-script-demo-1.0.0.jar"
$outputDirectory = Join-Path $projectRoot "build-output"

if (-not (Test-Path -LiteralPath $wrapper)) {
    throw "Maven Wrapper is missing: $wrapper"
}

Push-Location $projectRoot
try {
    & $wrapper -B -ntp clean verify
    if ($LASTEXITCODE -ne 0) {
        throw "Maven Wrapper build failed with exit code $LASTEXITCODE"
    }

    $env:APP_MESSAGE = $Message
    & java -jar $jar $outputDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Java application failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
~~~

Chạy:

~~~powershell
$env:APP_MESSAGE = "portable build"
.\scripts\build.ps1
~~~

Hoặc truyền trực tiếp:

~~~powershell
.\scripts\build.ps1 -Message "portable build"
~~~

Script sử dụng $PSScriptRoot, Join-Path, Push-Location và Pop-Location. Exit code của native process được kiểm tra rõ ràng.

## 31. Git attributes và ignore rules

File .gitattributes:

~~~gitattributes
* text=auto
*.sh text eol=lf
*.cmd text eol=crlf
*.ps1 text eol=crlf
~~~

File .gitignore có thể chứa:

~~~gitignore
target/
build-output/
.env
.env.*
!.env.example
*.log
~~~

Không ignore .mvn/wrapper, mvnw, mvnw.cmd, POM hoặc các script build cần thiết. Wrapper files và cấu hình version phải được commit để người khác có thể dùng cùng build tool.

## 32. Kiểm thử trong môi trường sạch

Một bộ kiểm thử tốt nên kiểm tra nhiều điều kiện thay vì chỉ chạy trên máy phát triển:

1. Clone repository vào thư mục mới.
2. Đặt tên thư mục có khoảng trắng.
3. Gọi script từ một thư mục làm việc khác.
4. Dùng đúng JDK version được khai báo.
5. Dùng Maven Wrapper, không dùng Maven global.
6. Chạy clean verify để loại output cũ.
7. Xóa cache trong một lượt thử riêng.
8. Kiểm tra script dừng đúng khi thiếu environment variable.
9. Chạy trên OS/architecture được hỗ trợ.
10. Xác minh file output, encoding, permissions và exit code.
11. Chạy lại để phát hiện phụ thuộc trạng thái từ lần trước.
12. Ghi tool versions và commit SHA vào CI log.

Một lần build thành công khi cache đầy đủ chỉ chứng minh môi trường đó đang chạy được. Clean runner và cache miss mới giúp phát hiện nhiều phụ thuộc ẩn.

## 33. Chẩn đoán lỗi “works on my machine”

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| mvn chạy nhưng CI không tìm thấy | Maven chỉ được cài global trên máy cá nhân. | Commit Maven Wrapper và gọi mvnw. |
| Sai Java version | PATH hoặc JAVA_HOME trỏ tới JDK khác. | java -version, javac -version, mvnw -version. |
| File không tìm thấy | Script giả định current working directory. | In pwd/Get-Location; dùng script root. |
| Chạy trên Windows, lỗi trên Linux | Path, case sensitivity, permissions hoặc shell. | Test OS matrix và chuẩn hóa file name. |
| Tiếng Việt bị lỗi | Encoding mặc định không thống nhất. | UTF-8 trong POM và file I/O. |
| Thời gian khác nhau | Timezone hoặc locale mặc định. | Dùng UTC và Locale.ROOT. |
| CI không tải được dependency | Proxy, mirror hoặc credential chỉ có local. | Kiểm tra Maven settings và secret injection. |
| Build chỉ chạy lần thứ hai | Dựa vào output/cache cũ. | clean verify trên runner sạch. |
| Bash báo bad interpreter | CRLF hoặc thiếu executable bit. | Kiểm tra .gitattributes, LF và chmod +x. |
| Output bị ghi sai thư mục | Path dựa trên . hoặc user.dir. | Truyền output path rõ ràng. |
| Windows chọn nhầm executable | Nhiều bản tool trong PATH. | Get-Command, kiểm tra JAVA_HOME. |
| Build phụ thuộc IDE | IDE tự cấu hình JDK hoặc profile. | Chạy wrapper từ terminal sạch và CI. |

## 34. Checklist loại bỏ phụ thuộc máy cá nhân

- [ ] Không có username hoặc home path cá nhân trong source/POM/script.
- [ ] Script xác định project root từ vị trí của nó hoặc nhận path rõ ràng.
- [ ] Đường dẫn có khoảng trắng được quote đúng.
- [ ] Maven Wrapper và Maven version đã được pin.
- [ ] JDK version tối thiểu được kiểm tra bằng Enforcer.
- [ ] Compiler JDK được chọn bằng Toolchains khi cần.
- [ ] Dependency và plugin version được khai báo rõ.
- [ ] JAVA_HOME và PATH được kiểm tra khi chẩn đoán.
- [ ] Cấu hình runtime được truyền qua CLI/environment.
- [ ] Secret lấy từ secret manager, không commit.
- [ ] Path được tạo bằng Path/Files hoặc Join-Path.
- [ ] Encoding UTF-8 được chỉ định.
- [ ] Locale và timezone được kiểm soát.
- [ ] Temp file được tạo qua API hoặc temp directory của OS.
- [ ] Shell, line endings và executable bit được cấu hình.
- [ ] Build không yêu cầu quyền admin/root ngoài nhu cầu thực tế.
- [ ] Network, proxy và repository được khai báo.
- [ ] Cache có thể xóa mà build vẫn thành công.
- [ ] CI chạy trên các OS/JDK mục tiêu.
- [ ] Clean build từ thư mục mới tạo output như mong đợi.

## 35. Kết quả kiểm chứng project mẫu

Project mẫu được tạo trong thư mục tạm có khoảng trắng trong tên. Maven Wrapper được tạo bằng Maven Wrapper Plugin 3.3.4 và pin distribution Maven 3.9.12.

Kiểm tra wrapper:

~~~text
Apache Maven 3.9.12
Java version 17.0.15
~~~

Project được build với Amazon Corretto JDK 17.0.15, Maven Compiler Plugin 3.13.0, Maven JAR Plugin 3.4.2 và Maven Enforcer Plugin 3.5.0. maven.compiler.release được đặt là 17.

Cả PowerShell và Git Bash đều gọi script từ một working directory khác với project root. Hai script tìm đúng project root, chạy Maven Wrapper, tạo JAR và chạy Java program thành công.

Kết quả PowerShell:

~~~text
BUILD SUCCESS
message=portable build on Java 17
output=build-info.txt
~~~

Kết quả Git Bash:

~~~text
BUILD SUCCESS
message=portable bash build on Java 17
output=build-info.txt
~~~

Class file có major version 61, tương ứng Java 17. JAR được chạy bằng Amazon Corretto 17.0.15 và tạo file build-info.txt bằng UTF-8. Đường dẫn project có khoảng trắng và không làm hỏng việc truyền argument.

Đây là kiểm thử thực tế trên Windows 11 với PowerShell và Git Bash, cùng JDK 17.0.15. Nó xác nhận hai script mẫu hoạt động trong môi trường đó; CI vẫn cần chạy trên Linux/macOS nếu các hệ điều hành đó thuộc phạm vi hỗ trợ của dự án.

## 36. Tài liệu tham khảo

- Apache Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Maven Wrapper Plugin Usage: https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html
- Apache Maven Toolchains Guide: https://maven.apache.org/guides/mini/guide-using-toolchains
- Maven Toolchains Plugin Usage: https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html
- Java SE 17 System Properties: https://docs.oracle.com/en/java/javase/17/docs/api/system-properties.html
- Java SE 17 Path API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html
- Java SE 17 Files API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17 StandardCharsets: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html
- GitHub Actions Workflow Syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Actions setup-java: https://github.com/actions/setup-java
- Git Attributes: https://git-scm.com/docs/gitattributes

Một script portable phải mô tả rõ công cụ, cấu hình, path và điều kiện thực thi. Hãy pin Maven/JDK phù hợp, xác định project root từ script, truyền cấu hình qua environment hoặc CLI, dùng Java NIO cho file system và xác nhận build bằng CI trên môi trường sạch.