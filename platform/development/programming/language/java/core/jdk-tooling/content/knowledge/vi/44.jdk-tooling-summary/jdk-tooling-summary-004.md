# Checklist toolchain cho dự án Java

## 1. Mục đích và phạm vi

Toolchain Java là tập hợp công cụ và cấu hình biến source code thành artifact có thể kiểm thử, chạy và phân phối. Một toolchain thường gồm:

- JDK và Java runtime.
- Compiler, archive, documentation và diagnostic tools.
- Build tool như Maven hoặc Gradle.
- Dependency repositories và version policy.
- IDE/editor và cấu hình project.
- Test framework và quality checks.
- CI runner, cache và artifact storage.
- Runtime/container/installer khi dự án cần phân phối ứng dụng.

Checklist này dùng khi thiết lập máy developer mới, kiểm tra máy đã có Java, chuẩn hóa dự án hoặc rà soát trước khi phát hành. Mỗi mục nên có trạng thái và bằng chứng kiểm tra. Đánh dấu hoàn tất khi có kết quả thực tế, không chỉ vì một công cụ đã được cài.

## 2. Xác định yêu cầu trước khi cài đặt

Trước khi chọn JDK hoặc build tool, ghi rõ:

- Phiên bản Java tối thiểu mà ứng dụng phải hỗ trợ.
- JDK dùng để chạy compiler và build tool.
- Hệ điều hành và CPU architecture được hỗ trợ.
- Maven hay Gradle; phiên bản nào được dự án pin.
- Artifact cần tạo: library JAR, executable JAR, WAR, ZIP, container image hay installer.
- IDE/editor và test framework mà nhóm sử dụng.
- Dependency repository, proxy và chứng chỉ nội bộ nếu có.
- Quality gate bắt buộc: compile, unit test, integration test, static analysis, vulnerability scan, license, signing.
- Cách lưu artifact và báo cáo build.

Phân biệt ba phiên bản Java:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Build JDK | JDK chạy Maven/Gradle và compiler | JDK 21 |
| Target release | Java API và bytecode mà source hướng tới | Java 17 |
| Runtime JDK | Java chạy ứng dụng thực tế | Java 17 hoặc mới hơn |

Một máy có thể chạy Gradle bằng JDK 21, compile source bằng Java 17 API và chạy artifact trên Java 17. Ba giá trị này cần được kiểm soát riêng.

## 3. Chọn JDK distribution phù hợp

JDK gồm Java runtime và các công cụ phát triển như javac, jar, javadoc, jshell và jdeps. Cài JDK đầy đủ trên máy developer và build runner.

Một số distribution phổ biến gồm Eclipse Temurin, Amazon Corretto, Azul Zulu, Oracle JDK và Microsoft OpenJDK. Khi chọn, kiểm tra:

- Nhà cung cấp và nguồn tải chính thức.
- Phiên bản Java và lịch cập nhật bảo mật.
- Hệ điều hành, architecture và loại package.
- Chính sách license và hỗ trợ của tổ chức.
- Khả năng cung cấp bản cập nhật trong vòng đời sản phẩm.
- Quy định nội bộ về vendor consistency nếu có.

Không cần mọi dự án đều dùng cùng vendor, nhưng một dự án nên xác định rõ vendor/version cho build CI để kết quả dễ tái hiện. Nếu runtime production khác vendor với build JDK, đưa runtime đó vào compatibility test.

**Checklist**

- [ ] Đã xác định Java baseline và các runtime được hỗ trợ.
- [ ] Đã chọn JDK distribution từ nguồn chính thức.
- [ ] Đã chọn đúng OS và architecture, ví dụ Windows x64 hoặc Linux ARM64.
- [ ] Đã xác nhận license và policy cập nhật của vendor.
- [ ] Đã ghi lại vendor, version và nguồn cài đặt.
- [ ] Đã phân biệt JDK cho phát triển với runtime tối thiểu để chạy sản phẩm.

## 4. Cài đặt JDK và kiểm tra thư mục

Sau khi cài đặt, xác định thư mục gốc JDK. Thư mục này thường có các thư mục con như bin, conf, include, jmods và lib. Không đặt JAVA_HOME trỏ thẳng vào thư mục bin.

Ví dụ:

~~~text
C:\Program Files\Java\jdk-21\
├── bin\
├── conf\
├── include\
├── jmods\
└── lib\
~~~

Trên Linux/macOS, JDK thường nằm trong thư mục do package manager hoặc vendor installer quản lý. Không di chuyển thư mục JDK sau khi đã cấu hình JAVA_HOME nếu chưa cập nhật lại các đường dẫn liên quan.

**Checklist**

- [ ] JDK được cài ở đường dẫn ổn định, có quyền đọc và execute.
- [ ] Thư mục bin có java và javac.
- [ ] Không giải nén nhiều JDK vào cùng một thư mục.
- [ ] Không trộn file của hai vendor/version trong một JDK directory.
- [ ] Đã ghi lại đường dẫn JDK để cấu hình IDE và build tool.

## 5. Cấu hình JAVA_HOME và PATH

JAVA_HOME nên trỏ tới thư mục gốc JDK. PATH cần chứa thư mục bin để shell tìm được executable.

Windows PowerShell, chỉ cho terminal hiện tại:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
~~~

Linux/macOS:

~~~bash
export JAVA_HOME=/opt/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Các lệnh trên chỉ thay đổi environment của terminal hiện tại và process con. Muốn cấu hình lâu dài, dùng Environment Variables của Windows hoặc shell profile phù hợp như ~/.bashrc, ~/.zshrc. Trên macOS có thể dùng /usr/libexec/java_home để chọn một bản JDK đã cài.

Không đặt JAVA_HOME thành đường dẫn có hậu tố /bin. Không thêm nhiều thư mục JDK vào PATH mà không xác định thứ tự ưu tiên. Không đặt CLASSPATH toàn cục để giải quyết dependency của từng project.

**Checklist**

- [ ] JAVA_HOME trỏ đúng JDK root.
- [ ] PATH chứa JAVA_HOME/bin.
- [ ] JDK mong muốn xuất hiện trước các bản Java cũ trong PATH.
- [ ] Đã mở terminal mới sau khi đổi environment lâu dài.
- [ ] Không dùng CLASSPATH toàn cục để quản lý dependency project.

## 6. Kiểm tra đúng Java executable đang chạy

Chạy:

~~~bash
java --version
javac --version
jar --version
~~~

Windows PowerShell:

~~~powershell
Get-Command java, javac, jar -All | Select-Object Name, Source
$env:JAVA_HOME
~~~

Windows Command Prompt:

~~~cmd
where.exe java
where.exe javac
~~~

Linux/macOS:

~~~bash
command -v java
command -v javac
type -a java
echo "$JAVA_HOME"
~~~

Đảm bảo java và javac đến từ JDK dự kiến. Nếu java trả về JDK 21 nhưng javac đến từ JDK 17, PATH có thể chứa nhiều JDK theo thứ tự không mong muốn.

Có thể xem thông tin runtime chi tiết:

~~~bash
java -XshowSettings:properties -version
~~~

Kiểm tra java.home, java.version, java.vendor, os.name, os.arch, file.encoding và user.dir. Không đưa toàn bộ output vào log nếu môi trường có đường dẫn nội bộ hoặc thông tin không cần thiết.

**Checklist**

- [ ] java --version đúng phiên bản.
- [ ] javac --version đúng compiler dự kiến.
- [ ] java và javac cùng thuộc một JDK khi không chủ ý dùng toolchain khác.
- [ ] java.home và java.vendor đúng với môi trường.
- [ ] Không có Java executable cũ che khuất JDK mong muốn.

## 7. Xác nhận các công cụ đi kèm JDK

Ngoài java và javac, kiểm tra các công cụ cần cho dự án:

| Công cụ | Công dụng | Khi cần |
|---|---|---|
| jar | Tạo và đọc JAR | Package/inspect JAR |
| javadoc | Sinh API documentation | Library hoặc project cần docs |
| jshell | REPL thử Java expression | Học tập, khám phá API |
| jdeps | Phân tích dependency và module | Kiểm tra dependency, chuẩn bị jlink |
| jlink | Tạo custom runtime image | Phân phối runtime tối giản |
| jpackage | Tạo application package/installer | Phân phối desktop/native package |
| keytool | Quản lý keystore và certificate | TLS, signing, truststore |
| jarsigner | Ký và xác minh JAR | Release cần chữ ký |

Kiểm tra phiên bản:

~~~bash
jar --version
javadoc --version
jshell --version
jdeps --version
jlink --version
jpackage --version
keytool -help
jarsigner -help
~~~

Không phải mọi dự án đều cần jlink hoặc jpackage. Nếu tool không nằm trong scope, ghi rõ không áp dụng thay vì coi thiếu nó là lỗi của JDK.

**Checklist**

- [ ] jar hoạt động.
- [ ] javadoc hoạt động nếu cần phát hành API docs.
- [ ] jshell hoạt động nếu nhóm dùng REPL.
- [ ] jdeps hoạt động nếu cần phân tích dependency.
- [ ] jlink/jpackage/keytool/jarsigner có sẵn khi mục tiêu yêu cầu.

## 8. Chọn Java release và compiler settings

Đặt Java release rõ ràng để build không vô tình dùng API mới hơn runtime tối thiểu.

Lệnh javac:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/main/java/com/example/App.java
~~~

Maven:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Nếu dự án dùng preview features, cần cấu hình compile và runtime nhất quán với đúng JDK release; preview bytecode không phải cách tạo artifact tương thích với mọi runtime.

Không chỉ đặt sourceCompatibility/targetCompatibility hoặc source/target nếu mục tiêu là giới hạn cả API Java. Dùng --release khi phù hợp và test trên runtime tối thiểu được hỗ trợ.

**Checklist**

- [ ] Java release đã được thống nhất trong project.
- [ ] Compiler dùng --release hoặc cấu hình tương đương.
- [ ] Source encoding được đặt rõ ràng là UTF-8 nếu đó là chuẩn của project.
- [ ] Preview features chỉ được bật khi có yêu cầu rõ ràng.
- [ ] Có test runtime trên phiên bản Java thấp nhất được hỗ trợ.

## 9. Cài và pin Maven hoặc Gradle

Chọn một build tool chính cho mỗi project. Không bắt developer cài đúng phiên bản global nếu project đã cung cấp wrapper.

Maven Wrapper:

~~~bash
./mvnw --version
~~~

Windows:

~~~powershell
.\mvnw.cmd --version
~~~

Gradle Wrapper:

~~~bash
./gradlew --version
~~~

Windows:

~~~powershell
.\gradlew.bat --version
~~~

Commit các wrapper files vào repository. Pin distribution version trong wrapper properties và kiểm tra checksum distribution nếu policy yêu cầu. Wrapper giúp mọi developer và CI dùng cùng phiên bản build tool.

Không nên để build release phụ thuộc phiên bản Maven/Gradle bất kỳ đang có trên PATH.

**Checklist**

- [ ] Project đã chọn Maven hoặc Gradle.
- [ ] Wrapper files được commit.
- [ ] Build tool distribution version được pin.
- [ ] Wrapper checksum được cấu hình/kiểm tra khi phù hợp.
- [ ] CI và local đều chạy wrapper thay vì lệnh global.
- [ ] Không có build script yêu cầu phiên bản tool không được ghi lại.

## 10. Cấu hình JDK toolchain trong Maven và Gradle

Build JVM và compiler JDK có thể khác nhau. Build tool có thể chạy bằng JDK 21 nhưng compiler dùng JDK 17 thông qua toolchain.

Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Gradle toolchain chọn JDK cho task cần Java tool. Gradle daemon vẫn có JVM chạy riêng; xem output gradle --version để biết Launcher JVM và Daemon JVM.

Maven có thể dùng Maven Toolchains. File toolchains.xml khai báo JDK được cài, sau đó Maven Compiler Plugin hoặc plugin hỗ trợ toolchain chọn đúng JDK. Ví dụ phần cấu hình trong POM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
~~~

Đường dẫn JDK trong toolchains.xml là cấu hình riêng của máy/runner, không nên commit đường dẫn cá nhân vào POM. CI phải cài hoặc cung cấp JDK phù hợp và xác minh toolchain được resolve.

**Checklist**

- [ ] Build JVM version đã được xác định.
- [ ] Compiler JDK/toolchain version đã được xác định.
- [ ] Target release thống nhất với yêu cầu runtime.
- [ ] Gradle daemon JVM và compiler toolchain được kiểm tra riêng.
- [ ] Maven toolchains.xml được cấu hình ở từng môi trường cần thiết.
- [ ] CI có đúng JDK toolchain và không phụ thuộc JDK ngẫu nhiên trên runner.

## 11. Cấu hình IDE và editor

IDE có thể sử dụng JDK khác với terminal. Kiểm tra các cấu hình riêng:

- Project SDK/JDK.
- Language level hoặc Java compiler compliance.
- Bytecode target/release.
- Maven importer/runner JDK.
- Gradle JVM và Gradle toolchain.
- JRE/JDK trong Run Configuration.
- Test runner và working directory.
- Annotation processor và generated sources nếu project cần.

Với IntelliJ IDEA, kiểm tra Project Structure, Maven/Gradle settings và Run Configuration. Với Eclipse, kiểm tra Installed JREs, Java Compiler compliance và Build Path. Với VS Code, kiểm tra Java runtime được extension chọn và Maven/Gradle project import.

Chạy cùng một lệnh từ terminal và IDE để tìm khác biệt nếu build chỉ lỗi ở một môi trường.

**Checklist**

- [ ] IDE nhận diện đúng JDK.
- [ ] Project language level khớp target release.
- [ ] Maven/Gradle runner dùng đúng JVM.
- [ ] Run Configuration dùng đúng classpath/module path.
- [ ] Working directory và environment variables được đặt rõ.
- [ ] Không dùng output class cũ từ một JDK hoặc build configuration khác.

## 12. Chuẩn hóa encoding, locale và line endings

Đặt encoding rõ ràng trong build để tránh phụ thuộc máy developer.

Maven:

~~~xml
<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
~~~

Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Có thể dùng .gitattributes:

~~~gitattributes
* text=auto
*.java text eol=lf
*.gradle text eol=lf
*.xml text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
~~~

Nếu ứng dụng format ngày/số hoặc parse dữ liệu máy đọc, chỉ định Locale và timezone thay vì dựa vào default của máy. Kiểm tra các fixture có tiếng Việt, Unicode và line ending LF/CRLF nếu ứng dụng xử lý file.

**Checklist**

- [ ] Source encoding được đặt rõ ràng.
- [ ] Line ending policy được lưu trong repository.
- [ ] Test có dữ liệu Unicode khi ứng dụng hỗ trợ.
- [ ] Locale/timezone được chỉ định cho dữ liệu có định dạng ổn định.
- [ ] Không có file cấu hình chỉ chạy được do encoding mặc định trên một máy.

## 13. Quản lý dependency và repositories

Dependency là một phần của toolchain vì build phải resolve đúng phiên bản thư viện và plugin.

- Khai báo dependency trực tiếp trong Maven POM hoặc Gradle build file.
- Pin plugin và dependency version; dùng BOM hoặc version catalog khi phù hợp.
- Tránh version động và snapshot không ổn định trong release.
- Dùng dependency locking khi cần kiểm soát phiên bản bắc cầu.
- Xác định repository được phép truy cập.
- Kiểm tra proxy, TLS certificate và authentication theo policy.
- Không đưa token/password vào source code hoặc build file.
- Không tải JAR từ nguồn không xác định.
- Lưu dependency report khi cần điều tra.

Maven và Gradle có thể dùng cache cục bộ. Cache giúp build nhanh nhưng không thay thế kiểm tra repository và dependency version. Khi chẩn đoán lỗi resolve, thử build với refresh/dependency insight phù hợp và ghi lại repository/error thực tế.

**Checklist**

- [ ] Dependency trực tiếp và plugin đã có version rõ ràng.
- [ ] Repository policy được xác định.
- [ ] Proxy/TLS/authentication hoạt động nếu cần.
- [ ] Không có secret trong POM, build.gradle hoặc log.
- [ ] Dependency locking/BOM/version catalog được dùng theo nhu cầu.
- [ ] Không có snapshot hoặc dynamic version trong release nếu policy cấm.

## 14. Kiểm tra compile, test và package

Một toolchain chỉ được xem là sẵn sàng khi có thể đi hết vòng build của dự án.

Maven thường dùng:

~~~bash
./mvnw -B clean verify
~~~

Windows:

~~~powershell
.\mvnw.cmd -B clean verify
~~~

Gradle thường dùng:

~~~bash
./gradlew --no-daemon clean build
~~~

Windows:

~~~powershell
.\gradlew.bat --no-daemon clean build
~~~

Phân biệt các mục tiêu:

- Compile: source và test source biên dịch được.
- Test: unit test và các test task đã cấu hình chạy được.
- Package/assemble: tạo artifact.
- Verify/check: chạy các quality gate đã được khai báo.
- Install: cài artifact vào local Maven repository hoặc thao tác tương ứng.
- Deploy/publish: đẩy artifact tới remote repository theo cấu hình.

Maven verify không tự chạy mọi loại static/security scan nếu project chưa cấu hình plugin tương ứng. Gradle check cũng chỉ chạy các verification task được nối vào task graph.

**Checklist**

- [ ] Clean build thành công.
- [ ] Unit test bắt buộc pass.
- [ ] Integration test chạy trong môi trường đã chuẩn bị.
- [ ] Test skip có lý do được ghi nhận.
- [ ] Package/assemble tạo đúng artifact.
- [ ] Verification task cần thiết đã được cấu hình và thực sự chạy.
- [ ] Build trả exit code 0 và báo cáo test có thể truy cập.

## 15. Xác minh artifact đầu ra

Sau khi build, kiểm tra artifact thay vì chỉ nhìn dòng BUILD SUCCESSFUL.

Liệt kê JAR:

~~~bash
jar --list --file target/app.jar
~~~

Kiểm tra manifest:

~~~bash
jar --extract --file target/app.jar META-INF/MANIFEST.MF
~~~

Chạy executable JAR nếu đó là mục tiêu:

~~~bash
java -jar target/app.jar
~~~

Phân tích dependency/module:

~~~bash
jdeps --multi-release 17 --print-module-deps target/app.jar
~~~

Tính checksum trên Windows PowerShell:

~~~powershell
Get-FileHash .\target\app.jar -Algorithm SHA256
~~~

Linux:

~~~bash
sha256sum target/app.jar
~~~

Library JAR cần kiểm tra coordinates, POM/module metadata và việc consumer project resolve được dependency. Executable JAR cần kiểm tra Main-Class và runtime dependencies. Application distribution cần kiểm tra launcher script, config, permissions và cấu trúc thư mục.

**Checklist**

- [ ] Artifact được tạo ở đúng thư mục.
- [ ] Tên/version/coordinates đúng.
- [ ] Manifest hoặc module metadata đúng với loại artifact.
- [ ] JAR có thể được liệt kê và đọc.
- [ ] Smoke test chạy trên runtime tối thiểu.
- [ ] Dependency cần thiết được phân phối đầy đủ.
- [ ] Checksum được tạo nếu quy trình yêu cầu.

## 16. Cấu hình CI cùng toolchain với local

CI phải dùng wrapper và JDK đã được chỉ định trong build contract. Ví dụ GitHub Actions cho Maven:

~~~yaml
name: Java toolchain

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Show toolchain
        run: |
          java --version
          javac --version
          ./mvnw --version

      - name: Verify
        run: ./mvnw -B clean verify
~~~

Ví dụ này chạy trên JDK 21. Nếu cần kiểm tra nhiều JDK hoặc OS, dùng matrix và đảm bảo step setup-java thật sự nhận giá trị từ matrix. Không chỉ khai báo matrix rồi vô tình cố định một version trong step cài đặt.

Với Gradle, dùng cache: gradle và chạy ./gradlew --no-daemon clean build. Trong môi trường có yêu cầu bảo mật cao, pin GitHub Actions về commit SHA đã được kiểm duyệt thay vì chỉ dựa vào mutable version tag.

**Checklist**

- [ ] CI checkout đúng source revision.
- [ ] CI cài đúng JDK vendor/version.
- [ ] CI gọi Maven/Gradle Wrapper.
- [ ] CI hiển thị version của runtime, compiler và build tool.
- [ ] CI chạy cùng các quality gate đã định nghĩa.
- [ ] Test report và artifact được upload khi cần.
- [ ] Matrix thực sự sử dụng các giá trị OS/JDK đã khai báo.
- [ ] Release publication tách khỏi pull request verification.

## 17. Container và runtime distribution

Nếu build hoặc chạy ứng dụng trong container, xác định rõ image chứa JDK hay chỉ runtime. Multi-stage build thường dùng JDK ở build stage và runtime image nhỏ hơn ở execution stage.

Ví dụ cần kiểm tra:

- Base image đến từ registry đáng tin cậy.
- Tag hoặc digest được pin theo policy.
- OS/architecture của image phù hợp với artifact.
- Java runtime trong image đúng baseline.
- Container memory limit được tính đến khi chọn heap.
- User trong container không chạy root nếu không cần.
- Certificate/TLS và timezone data có đủ khi ứng dụng yêu cầu.
- Native library có đúng ABI và architecture.

jlink có thể tạo custom runtime image từ module closure. Chỉ dùng khi dependency/module đã được phân tích và test trên image cuối cùng. Không giả định một runtime image tối giản có đủ mọi provider hoặc native component.

**Checklist**

- [ ] Base image và Java runtime version được pin.
- [ ] Build stage và runtime stage có vai trò rõ.
- [ ] Runtime image chạy smoke test thành công.
- [ ] Heap phù hợp memory limit.
- [ ] User, permissions, certificates và native libraries được kiểm tra.
- [ ] Image scan được thực hiện theo security policy.

## 18. Security và supply-chain checks

Toolchain là một phần của chuỗi cung ứng phần mềm. Kiểm tra các điểm sau:

- Cài JDK và build tool từ nguồn chính thức hoặc mirror nội bộ đã duyệt.
- Xác minh checksum/signature của distribution khi nhà cung cấp công bố.
- Pin dependency, plugin và wrapper version.
- Scan dependency vulnerability và license theo policy.
- Quét secret trong repository và artifact.
- Không in credential, token hoặc private key trong build log.
- Tạo SBOM nếu quy trình phát hành yêu cầu.
- Ký artifact và xác minh chữ ký nếu sản phẩm cần.
- Cập nhật JDK/build plugin theo security advisory.
- Giới hạn quyền của CI token và signing credentials.

Không bỏ qua TLS certificate validation để xử lý lỗi download. Nếu dùng proxy hoặc certificate nội bộ, cấu hình truststore đúng theo hướng dẫn quản trị của tổ chức.

**Checklist**

- [ ] Nguồn JDK/build tool được phê duyệt.
- [ ] Checksum/signature distribution được xác minh khi có.
- [ ] Dependency vulnerability và license scan đã chạy.
- [ ] Secret không xuất hiện trong source, artifact hoặc log.
- [ ] SBOM/signing được thực hiện nếu release policy yêu cầu.
- [ ] CI credentials có quyền tối thiểu cần thiết.

## 19. Reproducibility và traceability

Reproducible build hướng tới việc tạo cùng artifact từ cùng source và đầu vào đã xác định. Traceability giúp biết artifact đến từ source revision và quy trình nào.

Để tăng khả năng tái lập:

- Pin JDK, Maven/Gradle, plugin và dependency.
- Dùng wrapper và dependency locking khi phù hợp.
- Chuẩn hóa encoding, locale và timezone.
- Tránh timestamp, absolute path và username không cần thiết trong artifact.
- Kiểm soát generated sources/resources.
- Lưu source commit, build run ID và toolchain version.
- So sánh checksum khi kiểm tra byte-for-byte reproducibility.

Hai build có thể chạy cùng logic nhưng tạo JAR khác hash do timestamp hoặc metadata. Nếu mục tiêu là reproducibility byte-for-byte, cần cấu hình archive timestamp và các nguồn metadata động, sau đó build hai lần từ cùng source trong môi trường sạch để kiểm chứng.

**Checklist**

- [ ] Source commit được ghi nhận.
- [ ] JDK/build tool/plugin/dependency version được pin.
- [ ] Build inputs và generated files được kiểm soát.
- [ ] Locale/timezone/encoding ổn định.
- [ ] Checksum được lưu cùng artifact.
- [ ] Reproducibility được test nếu đó là yêu cầu release.

## 20. Hiệu năng, cache và trải nghiệm developer

Một toolchain tốt cung cấp feedback nhanh mà vẫn giữ quality gates.

- Dùng incremental build cho vòng lặp local.
- Dùng clean build trong CI/release để tránh phụ thuộc output cũ.
- Dùng Maven/Gradle cache theo cách an toàn.
- Chạy test song song khi test độc lập và thread-safe.
- Tách unit test nhanh khỏi integration/E2E test nặng.
- Đo task/build phase trước khi tối ưu.
- Tránh cache secret hoặc artifact không đáng tin giữa các job.
- Ghi lại thời gian build và tỷ lệ cache hit khi cần.

Không tắt test bắt buộc chỉ để build nhanh. Tối ưu cache, test selection hoặc task graph sau khi có số liệu.

**Checklist**

- [ ] Thời gian build local và CI được theo dõi.
- [ ] Cache không làm mất tính đúng đắn.
- [ ] Test song song không dùng chung mutable state.
- [ ] Unit/integration/E2E có lịch chạy phù hợp.
- [ ] Clean build vẫn thành công.

## 21. Kiểm tra môi trường mạng và chứng chỉ

Build tool thường phải tải dependency, plugin hoặc JDK distribution. Khi gặp lỗi resolve:

- Kiểm tra DNS, proxy và kết nối tới repository.
- Xác nhận repository URL và credentials.
- Kiểm tra thời hạn certificate và truststore.
- Phân biệt lỗi authentication, authorization, timeout và artifact không tồn tại.
- Xem log Maven/Gradle ở mức chi tiết phù hợp.
- Không tắt TLS verification hoặc dùng HTTP không an toàn để né lỗi.

Maven có thể dùng settings.xml để cấu hình mirror, proxy và server credentials. Gradle có thể lấy repository credentials từ environment/secret store. Không commit settings.xml cá nhân hoặc token vào repository.

**Checklist**

- [ ] Repository được truy cập qua HTTPS hoặc mirror nội bộ được duyệt.
- [ ] Proxy/DNS hoạt động.
- [ ] TLS trust chain hợp lệ.
- [ ] Credentials được cấp ngoài source code.
- [ ] Lỗi download được phân loại theo nguyên nhân thực tế.

## 22. Smoke test tối thiểu cho JDK và runtime

Có thể kiểm tra compile, package và chạy Java 17 bằng một chương trình nhỏ.

File ToolchainProbe.java:

~~~java
package com.example;

/**
 * Minimal program used to verify the local Java toolchain.
 */
public final class ToolchainProbe {
    private ToolchainProbe() {
    }

    /**
     * Prints the runtime version and the requested verification target.
     *
     * @param args optional target label
     */
    public static void main(String[] args) {
        String runtime = System.getProperty("java.version");
        String target = args.length == 0 ? "local" : args[0];
        System.out.println("Toolchain probe passed");
        System.out.println("runtime=" + runtime);
        System.out.println("target=" + target);
    }
}
~~~

Từ thư mục chứa source, compile:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/com/example/ToolchainProbe.java
~~~

Tạo executable JAR:

~~~bash
jar --create --file build/toolchain-probe.jar --main-class com.example.ToolchainProbe -C build/classes .
~~~

Chạy:

~~~bash
java -jar build/toolchain-probe.jar ci
~~~

Output trên runtime Java 17.0.15:

~~~text
Toolchain probe passed
runtime=17.0.15
target=ci
~~~

Nếu build bằng JDK mới hơn, dòng runtime phản ánh JDK đang chạy. Chạy cùng JAR trên runtime Java 17 để kiểm tra target compatibility.

Có thể tạo Javadoc và phân tích module dependency:

~~~bash
javadoc -Xdoclint:all -d build/docs src/com/example/ToolchainProbe.java
jdeps --multi-release 17 --print-module-deps build/toolchain-probe.jar
~~~

Với chương trình này, jdeps xác định dependency module là java.base. Đây là smoke test cho JDK tools; nó không thay thế build và test suite của project thật.

## 23. Checklist theo từng thời điểm

### Khi thiết lập máy developer

- [ ] Cài JDK đúng vendor/version và architecture.
- [ ] Cấu hình JAVA_HOME và PATH.
- [ ] Kiểm tra java, javac, jar và các công cụ cần dùng.
- [ ] Cài IDE/editor và chọn đúng project SDK.
- [ ] Kiểm tra Maven/Gradle Wrapper.
- [ ] Resolve dependency từ repository được phép.
- [ ] Chạy clean build và unit test.
- [ ] Chạy ứng dụng hoặc smoke test artifact.
- [ ] Ghi nhận toolchain version vào tài liệu nhóm.

### Khi tạo hoặc thay đổi project

- [ ] Ghi Java baseline và target release.
- [ ] Pin build tool qua wrapper.
- [ ] Cấu hình compiler/toolchain.
- [ ] Cấu hình encoding và line endings.
- [ ] Khai báo dependency/plugin version.
- [ ] Cấu hình unit/integration test.
- [ ] Định nghĩa artifact và naming.
- [ ] Cấu hình CI dùng cùng build contract.
- [ ] Kiểm tra README có lệnh build/run chính xác.

### Trước khi release

- [ ] Build sạch từ source revision đã xác định.
- [ ] Dùng JDK/build tool version được phê duyệt.
- [ ] Toàn bộ test và quality gate bắt buộc pass.
- [ ] Test trên runtime tối thiểu và OS được hỗ trợ.
- [ ] Artifact có tên/version/manifest/module metadata đúng.
- [ ] Dependency và license scan đạt policy.
- [ ] SBOM, checksum và signature được tạo nếu yêu cầu.
- [ ] Artifact được lưu ở nơi phát hành đã định.
- [ ] Lưu build log, test report và provenance.
- [ ] Xác minh artifact đã phát hành có thể tải và chạy.

## 24. Chẩn đoán lỗi toolchain thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| java không được nhận diện | JDK chưa cài hoặc PATH sai | Kiểm tra JAVA_HOME, PATH và mở terminal mới. |
| java và javac khác version | Có nhiều JDK trong PATH | Xem Get-Command/where.exe hoặc command -v. |
| Maven/Gradle dùng JDK khác | Build JVM/daemon khác terminal | Xem mvn --version, gradle --version và cấu hình toolchain. |
| IDE compile khác terminal | Project SDK hoặc runner JDK sai | Đồng bộ SDK, language level và runner. |
| UnsupportedClassVersionError | Runtime thấp hơn bytecode | Dùng runtime đủ mới hoặc compile với --release phù hợp. |
| Dependency không resolve | Repository, proxy, TLS hoặc version sai | Kiểm tra URL, credentials, truststore và dependency metadata. |
| Test pass local nhưng fail CI | Environment, timezone, path hoặc service khác | So sánh JDK/OS/env và chạy matrix. |
| JAR không chạy sau package | Main-Class hoặc runtime dependency thiếu | Kiểm tra manifest, classpath và smoke test. |
| Build khác hash | Timestamp hoặc metadata động | Kiểm soát archive metadata nếu cần reproducibility. |
| OutOfMemoryError trong CI | Heap/container limit hoặc test song song | Đo memory, điều chỉnh heap và concurrency. |
| Javadoc fail | Thiếu comment, doclint hoặc source issue | Xem warning/error cụ thể và sửa API docs. |
| TLS handshake fail | Certificate/proxy/truststore | Cấu hình trust chain hợp lệ; không tắt verification. |

Khi chẩn đoán, thu thập tối thiểu java --version, javac --version, JAVA_HOME, đường dẫn executable, Maven/Gradle version, OS/architecture và lệnh build đã chạy. Không đưa secret vào log đính kèm.

## 25. Mẫu báo cáo toolchain của dự án

Có thể lưu kết quả kiểm tra trong README, wiki hoặc build report:

~~~text
Project:
Source revision:
OS and architecture:
JDK distribution:
JDK vendor/version:
JAVA_HOME:
java executable:
javac version:
Target Java release:
Runtime versions tested:
Maven/Gradle wrapper version:
IDE and project SDK:
Dependency repository:
Build command:
Test command:
Artifact path and version:
Smoke test result:
Security/quality gate result:
CI run:
Known limitations:
Last verified:
~~~

Mẫu này giúp phân biệt máy đã cài Java với toolchain đã được kiểm chứng. Một danh sách phiên bản không có build/test evidence chưa đủ để khẳng định dự án sẵn sàng.

## 26. Kết quả kiểm chứng trên môi trường mẫu

Checklist smoke test đã chạy trên Windows 11 x64 với:

| Thành phần | Phiên bản/kết quả |
|---|---|
| JDK hiện tại | Azul Zulu 24.0.2 |
| Runtime tương thích | Amazon Corretto 17.0.15 |
| Maven | 3.9.12 |
| Gradle | 9.2.1 |
| javac --release 17 | PASS |
| javadoc -Xdoclint:all | PASS |
| jar create và list | PASS |
| jdeps --multi-release 17 | PASS |
| JAR trên Java 24 | PASS |
| JAR trên Java 17 | PASS |

JAR được compile bằng JDK 24 với --release 17 và chạy thành công trên cả runtime Java 24.0.2 lẫn Corretto 17.0.15. jdeps báo module dependency java.base. Javadoc được tạo với doclint đầy đủ và không có warning sau khi source có comment cho class và main method.

Kết quả này xác nhận bộ smoke test trên môi trường Windows được nêu. Mỗi dự án vẫn cần chạy test riêng trên các OS, JDK vendor và runtime nằm trong support matrix của chính sản phẩm.

## 27. Tài liệu tham khảo

- [Java Platform, Standard Edition Documentation](https://docs.oracle.com/en/java/javase/25/)
- [The java Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [The javac Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [Maven Wrapper](https://maven.apache.org/wrapper/)
- [Maven Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [GitHub Actions: Building and Testing Java](https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-java-with-maven)

Một toolchain sẵn sàng khi developer và CI dùng đúng JDK/build tool, compile đúng Java baseline, resolve dependency ổn định, chạy test và tạo artifact có thể kiểm chứng. Hãy giữ checklist cùng repository, cập nhật khi nâng JDK hoặc build tool, và lưu bằng chứng build/test cho mỗi lần thay đổi toolchain.