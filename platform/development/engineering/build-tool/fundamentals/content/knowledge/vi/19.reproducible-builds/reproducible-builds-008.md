# Build từ bản checkout sạch trên một máy khác

Một dự án Java có thể build thành công trên máy của người viết nhưng thất bại khi đồng đội checkout trên máy mới hoặc khi CI chạy trong môi trường sạch. Nguyên nhân thường nằm ở những đầu vào ẩn: JDK cài toàn cục, dependency đã có trong cache, file cấu hình local chưa được commit, biến môi trường riêng, output còn sót từ lần build trước hoặc thiết lập mà IDE tự bổ sung.

Kiểm tra build từ một checkout sạch giúp xác nhận repository mô tả đủ những gì cần để tạo lại artifact. Người kiểm tra lấy đúng source revision, chuẩn bị đúng toolchain, dùng build wrapper, phân giải dependency từ repository được khai báo, chạy test và xác nhận output.

Cần phân biệt hai mức độ:

- **Build có thể chạy lại (repeatable build):** cùng đầu vào và môi trường được kiểm soát tạo ra kết quả tương đương.
- **Build tái lập nghiêm ngặt (reproducible build):** cùng đầu vào được xác định tạo ra artifact giống hệt ở mức byte.

Build thành công trên máy khác chưa chứng minh artifact giống hệt về byte. Ngược lại, checksum giống nhau cũng chưa chứng minh ứng dụng đáp ứng yêu cầu chức năng. Tính tái lập cần được xem cùng tính đúng đắn, kiểm thử và khả năng truy vết.

    Repository / commit đã xác định
                 |
                 v
           Fresh checkout
                 |
                 v
       Chuẩn bị JDK + wrapper
                 |
                 v
    Kiểm tra cấu hình và dependency
                 |
                 v
          Clean build + tests
                 |
                 v
       So sánh output / checksum
                 |
                 v
    Ghi nhận môi trường và kết quả

## 1. Vì sao cần kiểm tra trên một máy khác?

Máy phát triển thường tích lũy trạng thái mà repository không thể hiện đầy đủ:

- JDK hoặc Maven/Gradle được cài toàn cục.
- Dependency đã có sẵn trong cache hoặc local repository.
- Biến môi trường như JAVA_HOME, proxy hoặc token repository.
- File cấu hình riêng không được commit.
- File .class, generated source hoặc resource còn lại từ build trước.
- IDE tự chọn JDK, thêm annotation processor hoặc cấu hình run riêng.
- Thư viện native hoặc công cụ bên ngoài đã được cài trên máy.
- Cache build che giấu một dependency đầu vào chưa được khai báo.

Những trạng thái này có thể khiến build trên máy cá nhân thành công dù repository chưa mô tả đầy đủ yêu cầu. Checkout mới giúp kiểm tra xem các đầu vào cần thiết đã được khai báo và hướng dẫn hay chưa.

Trước khi bắt đầu, cần trả lời:

1. Commit hoặc tag nào cần kiểm tra?
2. Dự án yêu cầu phiên bản JDK nào?
3. Có Gradle Wrapper hoặc Maven Wrapper không?
4. Dependency được tải từ repository nào và cần xác thực gì?
5. Có biến môi trường hoặc file cấu hình local bắt buộc không?
6. Có công cụ ngoài như Docker, Node.js, protoc hoặc native compiler không?
7. Lệnh build chuẩn và lệnh test/package chuẩn là gì?
8. Artifact, báo cáo và checksum được tạo ở đâu?

Nếu các câu hỏi này không có câu trả lời trong repository hoặc tài liệu onboarding, cần bổ sung thông tin để người khác có thể tái hiện quy trình.

## 2. Xác định chính xác source revision

Muốn so sánh hai lần build, trước tiên phải bảo đảm chúng dùng cùng đầu vào mã nguồn. Không nên so sánh một máy đang có thay đổi chưa commit với máy khác đang checkout commit cũ.

### Kiểm tra trạng thái Git trên máy ban đầu

Chạy:

    git status --short
    git rev-parse HEAD
    git branch --show-current

- git status --short cho biết file đang sửa, file chưa được theo dõi hoặc trạng thái index.
- git rev-parse HEAD in commit hiện tại.
- git branch --show-current in nhánh đang checkout.

Nếu build phụ thuộc vào thay đổi chưa commit, hãy commit chúng hoặc ghi lại rõ các thay đổi trước khi so sánh. Commit SHA là mốc tốt hơn tên nhánh vì nhánh có thể di chuyển theo thời gian.

### Clone mới trên máy khác

Ví dụ:

    git clone https://example.com/team/java-app.git
    cd java-app
    git checkout <commit-sha>

Nếu repository dùng SSH hoặc hệ thống nội bộ, thay URL bằng địa chỉ được tổ chức cung cấp. Sau khi checkout, xác nhận:

    git rev-parse HEAD
    git status --short

Commit SHA phải khớp mốc đã ghi nhận. Working tree nên sạch trước khi build.

### Dùng worktree hoặc clone riêng

Nếu không muốn ảnh hưởng thư mục đang phát triển, có thể tạo clone riêng hoặc Git worktree:

    git worktree add ../java-app-clean <commit-sha>

Worktree dùng chung object database với repository gốc nhưng có working directory riêng. Nó hữu ích để kiểm tra một commit mà không phải đổi nhánh trong thư mục đang làm việc. Nếu mục tiêu là kiểm tra hành vi trên máy mới, vẫn cần clone độc lập trên máy đó vì worktree không mô phỏng được môi trường máy khác.

### Không xóa dữ liệu làm việc tùy tiện

Lệnh git clean -xfd có thể xóa file chưa được Git theo dõi, bao gồm file cấu hình local hoặc dữ liệu không thể tạo lại. Đừng chạy lệnh này chỉ để làm sạch nếu chưa kiểm tra nội dung. Có thể xem trước những file sẽ bị xóa bằng:

    git clean -ndx

Một clone mới thường là cách an toàn và rõ ràng hơn để kiểm tra build từ trạng thái sạch.

## 3. Kiểm tra cấu trúc và tài liệu repository

Sau khi checkout, xem các file gốc để nhận diện build tool và hướng dẫn.

Cấu trúc Gradle thường gặp:

    java-app/
    ├── .gitignore
    ├── README.md
    ├── CONTRIBUTING.md
    ├── gradlew
    ├── gradlew.bat
    ├── gradle/
    │   └── wrapper/
    ├── settings.gradle
    ├── build.gradle
    └── src/

Dự án Maven thường có pom.xml, mvnw, mvnw.cmd và thư mục .mvn/wrapper/.

Tài liệu nên chỉ rõ:

- JDK hoặc toolchain cần dùng.
- Lệnh wrapper chuẩn.
- Biến môi trường bắt buộc và cách lấy giá trị an toàn.
- Repository dependency cần truy cập.
- Cách chạy test và tạo artifact.
- Công cụ ngoài cần cài đặt.
- Các profile hoặc thuộc tính build đặc biệt.
- Vị trí output và cách xác nhận build thành công.

Không nên yêu cầu thành viên mới tự suy luận lệnh build từ IDE. Wrapper và tài liệu trong repository nên là nguồn hướng dẫn chính.

## 4. Dùng Gradle Wrapper thay vì Gradle cài toàn cục

Gradle Wrapper gồm script khởi chạy và cấu hình xác định phiên bản Gradle của project. Khi chạy wrapper, nó tải và dùng phiên bản đã khai báo trong gradle/wrapper/gradle-wrapper.properties nếu máy chưa có.

Ví dụ cấu hình:

    distributionUrl=https://services.gradle.org/distributions/gradle-8.10.2-bin.zip

Giá trị trên chỉ là ví dụ; phải dùng phiên bản thực tế được repository chỉ định.

Linux/macOS:

    ./gradlew --version
    ./gradlew clean test

Nếu file wrapper chưa có quyền thực thi sau khi checkout, kiểm tra mode được Git lưu. Có thể cấp quyền thực thi trong working tree:

    chmod +x gradlew

Nếu thiếu executable bit xảy ra thường xuyên, cần sửa mode của file trong Git để các checkout tiếp theo nhận đúng quyền.

Windows PowerShell:

    .\gradlew.bat --version
    .\gradlew.bat clean test

Wrapper giúp tránh trường hợp máy A dùng Gradle 8.x còn máy B dùng Gradle 7.x được cài toàn cục. Nó không tự cố định JDK, dependency repository, biến môi trường hay mọi plugin; những phần đó vẫn cần được quản lý riêng.

Repository Gradle thường cần các file:

    gradlew
    gradlew.bat
    gradle/wrapper/gradle-wrapper.jar
    gradle/wrapper/gradle-wrapper.properties

Wrapper JAR và script là một phần của build bootstrap. Hãy giữ chúng trong version control theo khuyến nghị của Gradle. Có thể xác minh cấu hình distribution và checksum nếu dự án sử dụng thuộc tính kiểm tra distribution.

## 5. Dùng Maven Wrapper

Maven Wrapper giúp project chỉ định phiên bản Maven mà thành viên và CI cần sử dụng, thay vì dựa vào Maven cài toàn cục.

Các file thường gặp:

    mvnw
    mvnw.cmd
    .mvn/
    └── wrapper/
        ├── maven-wrapper.properties
        └── maven-wrapper.jar

Tùy kiểu wrapper được tạo, một số file bootstrap có thể khác nhau.

Ví dụ maven-wrapper.properties:

    distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip

Đây chỉ là ví dụ về cách chỉ định Maven distribution. Hãy dùng phiên bản đã được dự án xác nhận.

Linux/macOS:

    ./mvnw --version
    ./mvnw clean verify

Windows:

    .\mvnw.cmd --version
    .\mvnw.cmd clean verify

Maven Wrapper cố định phiên bản Maven, nhưng JDK vẫn phải phù hợp. Maven có thể chạy bằng một JDK khác với phiên bản bytecode mục tiêu nếu cấu hình compiler/toolchain cho phép; hãy xác định rõ JDK được yêu cầu cho build.

## 6. Cố định phiên bản JDK và toolchain

Build Java phụ thuộc cả phiên bản compiler lẫn runtime. Chỉ ghi “cần Java” trong README là chưa đủ. Nên chỉ rõ phiên bản JDK, nhà cung cấp nếu cần và cách build tool chọn toolchain.

### Kiểm tra JDK đang được dùng

Chạy:

    java -version
    javac -version

Đối với Gradle, xem thêm thông tin JVM mà Gradle daemon sử dụng:

    ./gradlew --version

Kết quả cho biết phiên bản Gradle và JVM liên quan đến tiến trình build. java -version của Terminal và JVM mà Gradle daemon dùng có thể khác nếu JAVA_HOME, daemon JVM criteria hoặc cấu hình toolchain được thiết lập khác nhau.

### Khai báo Java toolchain trong Gradle

Ví dụ:

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

Khai báo này yêu cầu Gradle dùng toolchain Java 21 cho các task Java được hỗ trợ. Máy mới cần có JDK phù hợp hoặc được cấu hình để Gradle tìm/tải toolchain theo chính sách dự án. Không nên giả định toolchain tự được tải nếu chưa cấu hình resolver và quyền truy cập tương ứng.

### Khai báo compiler release

Nếu build dùng JDK mới nhưng cần bytecode/API mục tiêu cũ hơn, có thể cấu hình:

    tasks.withType(JavaCompile).configureEach {
        options.release = 17
        options.encoding = 'UTF-8'
    }

options.release kiểm soát mức ngôn ngữ, bytecode và API Java chuẩn mục tiêu. Nó không có nghĩa task nhất thiết chạy bằng JDK 17; compiler toolchain được chọn vẫn cần hỗ trợ release đó.

### Maven compiler/toolchain

Trong Maven, có thể cấu hình compiler plugin:

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

maven.compiler.release chọn API và bytecode mục tiêu. Nếu muốn kiểm soát JDK compiler khác với JVM chạy Maven, có thể dùng Maven Toolchains Plugin và toolchains.xml ở môi trường local/CI. File toolchains chứa đường dẫn cài đặt JDK của từng máy nên thường được cấu hình riêng, còn yêu cầu phiên bản được tài liệu hóa trong project.

### Không nhầm JDK chạy build với Java mục tiêu

Một dự án có thể chạy Maven/Gradle bằng JDK 21 nhưng biên dịch ứng dụng với release 17. Ngược lại, một plugin build có thể yêu cầu JDK mới hơn ngay cả khi ứng dụng chạy trên Java cũ. Hãy kiểm tra cả:

- JDK chạy build tool.
- JDK/compiler toolchain dùng để biên dịch.
- Java version của runtime image hoặc server triển khai.
- Phiên bản API/bytecode mà artifact nhắm đến.

## 7. Kiểm soát dependency và repository

Máy mới thường không có dependency cache. Đây là phép thử tốt để phát hiện dependency chưa được khai báo hoặc repository không được cấu hình đúng.

### Dùng version cụ thể

Ưu tiên version cụ thể hoặc cơ chế dependency locking/BOM được quản lý. Version động như 1.+, latest.release hoặc range có thể phân giải thành version khác theo thời gian và metadata repository.

Gradle có thể bật dependency locking:

    dependencyLocking {
        lockAllConfigurations()
    }

Sau đó tạo/cập nhật lock state theo quy trình của dự án và commit lock files. Locking giúp giữ version đã phân giải; nó không tự bảo đảm nội dung artifact từ repository bất biến nếu repository cho phép ghi đè cùng tọa độ.

Maven thường quản lý version tập trung qua dependencyManagement, BOM và version cụ thể trong POM. Có thể dùng công cụ bổ sung để tạo dependency lock nếu dự án yêu cầu. Điều quan trọng là xác định dependency graph và cách cập nhật version có kiểm soát.

### Local repository không phải nguồn chân lý

Maven thường lưu dependency trong ~/.m2/repository; Gradle có cache dependency trong thư mục người dùng. Một build có thể thành công vì máy cũ đã có một JAR được cài thủ công hoặc cache từ repository không còn truy cập được.

Để kiểm tra, clone mới và chạy build với cache trống hoặc cache riêng. Không cần xóa cache toàn cục của người dùng; có thể dùng thư mục cache tạm cho lần kiểm tra.

Ví dụ Gradle trên Linux/macOS:

    GRADLE_USER_HOME=/tmp/gradle-home-clean ./gradlew clean build

Trên PowerShell:

    $env:GRADLE_USER_HOME = Join-Path $env:TEMP 'gradle-home-clean'
    .\gradlew.bat clean build

Maven có thể dùng local repository riêng:

    mvn -Dmaven.repo.local=/tmp/m2-repository-clean clean verify

Trên Windows, thay đường dẫn bằng một thư mục tạm phù hợp. Wrapper distribution và dependency sẽ cần được tải lại; máy phải có quyền truy cập repository. Cache riêng giúp kiểm tra dependency resolution nhưng có thể làm build chậm hơn.

### Repository riêng và credentials

Nếu dependency nằm trong repository nội bộ, máy mới cần biết URL và cách xác thực. Không nên commit token hoặc password vào build.gradle, pom.xml hay file cấu hình dùng chung.

Gradle có thể lấy credentials từ biến môi trường hoặc Gradle properties bên ngoài repository. Maven thường dùng server trong settings.xml với id khớp repository id trong POM/settings profile. Tài liệu onboarding cần mô tả:

- Repository nào cần truy cập.
- Credential được cấp từ đâu.
- Tên biến môi trường hoặc server id cần cấu hình.
- Cách kiểm tra quyền đọc dependency.
- Cách xử lý khi máy mới không truy cập được VPN/proxy.

Nếu build cần secret để tải dependency hoặc thực hiện tác vụ, hãy dùng secret store của CI hoặc cơ chế credential được tổ chức phê duyệt.

## 8. Kiểm soát biến môi trường và cấu hình local

Build có thể phụ thuộc vào biến môi trường như:

    JAVA_HOME
    GRADLE_USER_HOME
    MAVEN_OPTS
    HTTP_PROXY / HTTPS_PROXY
    ARTIFACT_REPOSITORY_USER
    ARTIFACT_REPOSITORY_TOKEN

Đây chỉ là ví dụ; tên biến thực tế do project và công cụ quy định. Cần phân biệt:

- **Cấu hình bắt buộc:** thiếu thì build không thể hoàn thành, ví dụ credentials cho repository private.
- **Cấu hình tùy chọn:** có thể dùng giá trị mặc định, ví dụ log level local.
- **Secret:** không được commit hoặc ghi vào log, ví dụ token và mật khẩu.
- **Cấu hình theo môi trường:** thay đổi giữa local, CI, staging và production.

### Cung cấp file mẫu

Nếu dự án cần file cấu hình local, có thể commit file mẫu:

    config/
    ├── application.example.yml
    └── application.local.yml

File local có thể chứa dữ liệu riêng và cần được loại khỏi Git nếu có secret. README hướng dẫn copy file mẫu và điền giá trị cần thiết. Build nên báo lỗi rõ ràng khi thiếu cấu hình bắt buộc thay vì âm thầm dùng giá trị giả.

### Không phụ thuộc vào IDE

Nếu dự án chỉ build được sau khi import vào IDE, hãy kiểm tra xem IDE có đang:

- Tự thêm JDK hoặc annotation processor.
- Dùng profile/VM option không có trong wrapper command.
- Đặt working directory khác.
- Thêm file resource hoặc classpath từ cấu hình run.
- Cung cấp biến môi trường riêng.

Mục tiêu là đưa các yêu cầu cần thiết vào build script, wrapper, tài liệu hoặc cấu hình môi trường có kiểm soát để Terminal và CI có thể thực hiện cùng quy trình.

## 9. Phát hiện đầu vào không được khai báo

Một nguyên nhân phổ biến khiến build không tái lập là task đọc file hoặc công cụ bên ngoài mà build script không khai báo.

Ví dụ task tùy chỉnh đọc config/version.txt nhưng không khai báo input. Gradle có thể không biết output phụ thuộc vào file đó. Khi file thay đổi hoặc máy mới thiếu file, kết quả có thể sai hoặc task không chạy như mong đợi.

Task tùy chỉnh nên khai báo:

- File, thư mục, property và toolchain làm đầu vào.
- File/thư mục được tạo làm đầu ra.
- Dependency task nếu output cần kết quả từ task khác.
- Working directory và environment của tiến trình con khi chúng ảnh hưởng kết quả.

Đối với Maven, plugin goal cũng cần khai báo và nhận các đầu vào cần thiết thông qua cấu hình tường minh. Không dựa vào file được tạo thủ công trong target/ hoặc trong thư mục home.

### Generated source và annotation processor

Nếu dự án sinh mã nguồn, hãy xác định:

- Task/plugin nào tạo mã nguồn.
- Output được ghi vào thư mục build nào.
- Compiler có phụ thuộc task sinh mã trước khi biên dịch không.
- Công cụ sinh mã và version của nó có được khóa không.
- Output có chứa timestamp, đường dẫn máy local hoặc thông tin không ổn định không.

Không commit output generated nếu quy ước dự án yêu cầu build tool tạo lại. Ngược lại, nếu file generated là đầu vào chính thức được commit, phải bảo đảm quy trình cập nhật và kiểm tra chúng được tài liệu hóa.

## 10. Khác biệt hệ điều hành và môi trường

Build trên Windows và Linux/macOS có thể khác nhau dù cùng commit. Một số khác biệt thường gặp:

- Dấu phân cách path và classpath.
- Quyền thực thi của script.
- Chữ hoa/chữ thường trong tên file.
- Line ending CRLF/LF.
- Encoding mặc định.
- Shell và cách truyền argument.
- Native library và kiến trúc CPU.
- Timezone, locale và định dạng số/ngày.
- Path có khoảng trắng hoặc ký tự Unicode.

### Encoding

Nên lưu mã nguồn và resource text theo UTF-8, đồng thời khai báo encoding trong build tool. Maven có thể dùng:

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

Gradle Java compile có thể đặt:

    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }

Nếu test so sánh output text, cần xác định encoding khi đọc/ghi file thay vì phụ thuộc charset mặc định của máy.

### Line endings và executable bit

File .gitattributes có thể chuẩn hóa line ending, ví dụ:

    *.java text eol=lf
    *.gradle text eol=lf
    *.xml text eol=lf
    *.sh text eol=lf
    *.bat text eol=crlf

Quy tắc thực tế cần phù hợp với repository và loại file. Script shell cần LF và executable bit trên Unix-like systems. File batch trên Windows thường dùng CRLF. Khi file wrapper hoặc script có line ending sai, build có thể thất bại ngay ở bước khởi động.

### Chữ hoa/chữ thường

Windows thường dùng filesystem không phân biệt chữ hoa/chữ thường theo mặc định; Linux thường phân biệt. Import hoặc đường dẫn Config/app.yml có thể chạy trên Windows nhưng thất bại trên Linux nếu tên thật là config/app.yml. Dùng đúng casing trong source và kiểm tra trên hệ thống phân biệt casing.

### Locale, timezone và thời gian

Test phụ thuộc timezone hoặc locale của máy có thể cho kết quả khác nhau. Nếu logic cần timezone cụ thể, hãy truyền rõ ZoneId hoặc cấu hình test. Tránh so sánh chuỗi ngày giờ dựa trên locale mặc định. Với build tạo archive hoặc file có timestamp, thời gian hệ thống cũng có thể làm checksum khác nhau.

## 11. Cache và build sạch

Cache giúp build nhanh hơn, nhưng cache có thể che giấu dependency hoặc đầu vào bị khai báo thiếu. Khi điều tra khả năng tái lập, hãy phân biệt:

- **Build sạch:** xóa output của project và tạo lại.
- **Dependency cache sạch:** không dùng lại cache artifact/dependency đã tải trước.
- **Build cache sạch:** không khôi phục output task từ build cache.
- **Checkout sạch:** source revision mới trong working directory mới.

Đây là các phạm vi khác nhau. clean không nhất thiết xóa dependency cache của người dùng. Ngược lại, dùng cache dependency mới không tự xóa output cũ trong project.

### Gradle

Chạy build sạch:

    ./gradlew clean build

Không dùng build cache cho lần chạy:

    ./gradlew clean build --no-build-cache

Làm mới dependency resolution:

    ./gradlew build --refresh-dependencies

Các tùy chọn này giải quyết những việc khác nhau. --no-build-cache không đồng nghĩa xóa dependency cache. --refresh-dependencies yêu cầu Gradle làm mới resolution; nó không đảm bảo tải lại mọi byte nếu artifact/metadata được xác nhận không đổi.

### Maven

Chạy lifecycle từ đầu:

    mvn clean verify

Maven clean xóa output project, thường là target/. Nó không xóa toàn bộ local repository ~/.m2/repository. Có thể dùng -Dmaven.repo.local=<path> để kiểm tra với local repository riêng.

### Không đánh đồng build sạch với build tái lập

Một lần clean build trên máy cá nhân vẫn có thể dùng JDK, biến môi trường và dependency cache riêng. Muốn kiểm tra khả năng tái lập, cần checkout sạch trên môi trường khác và kiểm soát cả đầu vào ngoài thư mục build.

## 12. Xây dựng đường dẫn độc lập với thư mục làm việc hiện tại

Build script nên giải quyết đường dẫn dựa trên project directory thay vì giả định người dùng luôn chạy lệnh từ một thư mục cụ thể.

Trong Gradle, dùng layout.projectDirectory, rootProject và layout.buildDirectory cho file nội bộ. Trong Maven, dùng project.basedir và project.build.directory.

Không nên viết task phụ thuộc vào đường dẫn như C:/Users/Alice/project/config.yml. Hãy tham chiếu file cấu hình nằm trong repository hoặc nhận vị trí công cụ ngoài qua biến môi trường được tài liệu hóa.

Nếu task gọi chương trình bên ngoài, đặt working directory tường minh khi cần. Ví dụ Gradle Exec task:

    tasks.register('runGenerator', Exec) {
        workingDir = layout.projectDirectory.asFile
        commandLine 'java', '-jar', 'tools/generator.jar',
            'src/schema', layout.buildDirectory.dir('generated').get().asFile
    }

Ví dụ giả định tools/generator.jar có trong repository và java có thể tìm thấy qua PATH. Với dự án thực tế, cần khai báo tool/dependency và output rõ ràng, tránh phụ thuộc vào công cụ được cài thủ công mà không có version.

## 13. Kiểm tra dependency và artifact sau build

Sau khi build trên máy mới, cần xác nhận không chỉ exit code mà cả artifact đã được tạo.

### Gradle

    ./gradlew clean test jar

Kiểm tra output:

    find build/libs -maxdepth 1 -type f

Trên PowerShell:

    Get-ChildItem build/libs -File

Xem nội dung JAR:

    jar tf build/libs/my-app-1.0.0.jar

### Maven

    mvn clean verify

Kiểm tra output:

    find target -maxdepth 1 -type f

Trên PowerShell:

    Get-ChildItem target -File

Tên artifact phải khớp group, artifactId, version và packaging theo cấu hình. Nếu output không có, hãy kiểm tra lifecycle, profile và plugin execution.

### Dependency tree

Gradle:

    ./gradlew dependencies --configuration runtimeClasspath

Maven:

    mvn dependency:tree

So sánh dependency graph giữa máy ban đầu và máy mới nếu nghi ngờ version được chọn khác nhau. Khác biệt có thể đến từ version động, profile, repository metadata, lock state hoặc thuộc tính môi trường.

## 14. So sánh checksum giữa hai lần build

Nếu muốn kiểm tra artifact có giống hệt về byte hay không, có thể tính SHA-256 trên cả hai máy.

Linux/macOS:

    sha256sum build/libs/my-app-1.0.0.jar

Windows PowerShell:

    Get-FileHash build/libs/my-app-1.0.0.jar -Algorithm SHA256

Nếu checksum giống nhau, hai file có nội dung byte giống hệt. Nếu checksum khác nhau, chưa thể kết luận ngay build sai. Hãy xem archive có chứa timestamp, thứ tự entry, build metadata, generated file hoặc thông tin phụ thuộc thời gian hay không.

### Nguyên nhân checksum khác nhau

- Timestamp trong ZIP/JAR entry.
- Manifest hoặc resource chứa thời gian build.
- Generated source có đường dẫn tuyệt đối của máy.
- Build number hoặc commit metadata thay đổi.
- Dependency động phân giải sang version khác.
- Base image hoặc tool/plugin được cập nhật.
- Encoding hoặc line ending khác nhau.
- Archive entry order hoặc compression khác nhau.
- File không được khai báo làm input của task.

Để đạt reproducible archive, build tool/plugin cần hỗ trợ chuẩn hóa timestamp và thứ tự file. Gradle archive tasks có thể cấu hình:

    tasks.withType(AbstractArchiveTask).configureEach {
        isPreserveFileTimestamps = false
        isReproducibleFileOrder = true
    }

Thiết lập này giúp loại bỏ một số nguồn không ổn định trong archive. Nó không tự bảo đảm toàn bộ build reproducible nếu nội dung file bên trong vẫn chứa timestamp, đường dẫn máy hoặc dữ liệu thay đổi khác.

### So sánh đúng loại kết quả

Hai lần build chỉ có thể so sánh có ý nghĩa nếu cùng:

- Commit source.
- Version wrapper và plugin.
- JDK/toolchain.
- Dependency graph và repository metadata.
- Thuộc tính/profile build.
- Các file đầu vào và cấu hình được cung cấp.
- Kiến trúc/OS nếu build có native output.

Nếu những yếu tố này khác nhau, checksum khác có thể là kết quả hợp lệ của đầu vào khác nhau. Hãy ghi lại điều kiện trước khi so sánh.

## 15. Build trong CI như một máy mới

CI runner thường là môi trường sạch hơn máy phát triển, nhưng vẫn có thể dùng cache, image runner tùy chỉnh hoặc công cụ cài sẵn. Một pipeline tốt nên thể hiện rõ các bước:

1. Checkout commit cụ thể.
2. Cài hoặc chọn JDK/toolchain theo project.
3. Khởi chạy wrapper.
4. Cấp credentials/repository configuration an toàn.
5. Chạy build và test.
6. Lưu report và artifact khi cần, kể cả khi test thất bại.
7. Ghi nhận commit, version và checksum.

Ví dụ workflow Gradle trên Linux:

    git rev-parse HEAD
    java -version
    ./gradlew --version
    ./gradlew --no-daemon clean test jar
    sha256sum build/libs/*.jar

Đối với Maven:

    git rev-parse HEAD
    java -version
    ./mvnw --version
    ./mvnw --batch-mode clean verify
    sha256sum target/*.jar

sha256sum phù hợp với runner Linux; trên Windows cần dùng Get-FileHash hoặc công cụ tương ứng. Pipeline thực tế cũng cần upload artifact và test reports theo cấu hình hệ thống CI.

### Cache CI phải có khóa phù hợp

Cache Gradle/Maven có thể giúp pipeline nhanh hơn. Tuy nhiên, cache key nên phản ánh các yếu tố ảnh hưởng đến dependency/build output, chẳng hạn wrapper version, lock files, build script và JDK. Cache cũ không nên trở thành nguồn đầu vào bí mật khiến build chỉ thành công trên một runner cụ thể.

Nên có ít nhất một lần chạy định kỳ hoặc một job kiểm tra cache lạnh để xác nhận project vẫn có thể tải dependency và build từ đầu. Không nhất thiết vô hiệu hóa cache trong mọi build CI vì điều đó làm tăng thời gian và tải repository.

## 16. Build container image từ checkout sạch

Nếu dự án tạo container image, cần kiểm tra cả artifact Java lẫn image.

### Mô hình build artifact trước

    ./gradlew clean test jar
    docker build -t example/my-app:commit-a1b2c3d .

Dockerfile copy JAR đã tạo. Khi dùng mô hình này, build context phải chứa đúng artifact và .dockerignore không được loại bỏ file mà Dockerfile cần.

### Mô hình multi-stage

Dockerfile có thể thực hiện cả build Java lẫn tạo runtime image. Khi đó cần:

- Copy đủ wrapper scripts và wrapper configuration.
- Cấp executable bit cho wrapper trên Linux stage.
- Copy build files và source cần thiết.
- Cấp credentials cho private dependency bằng build secret mechanism, không ghi vào image layer.
- Dùng runtime base image tương thích với JDK/compiler release.
- Copy đúng artifact và runtime dependencies cần thiết.

Build image từ checkout sạch:

    docker build --pull -t example/my-app:clean-checkout .

--pull yêu cầu kiểm tra/cập nhật base image theo tag được chỉ định. Nếu muốn tái lập nghiêm ngặt, cần pin base image bằng digest và quản lý thời điểm cập nhật có chủ đích; tag base image có thể trỏ đến nội dung mới theo thời gian.

### Build context và .dockerignore

Build context là tập file Docker client gửi cho builder. .dockerignore có thể loại build/, target/, .git, file secret hoặc cache. Nếu Dockerfile copy artifact đã build từ host, không được loại output cần copy. Nếu Dockerfile tự build trong multi-stage, có thể loại output cũ để build stage tạo lại từ source.

Một clone sạch giúp phát hiện Dockerfile đang phụ thuộc vào file không được commit hoặc file output chỉ tồn tại trên máy cá nhân.

## 17. Kiểm tra build trên một hệ điều hành khác

Nếu ứng dụng cần hỗ trợ nhiều hệ điều hành, chỉ chạy build hai lần trên cùng một máy không đủ. Nên có ma trận CI theo OS/architecture khi chi phí cho phép.

| Môi trường | Mục tiêu kiểm tra |
|---|---|
| Linux x86_64 | Build chuẩn và runtime server phổ biến. |
| Windows x86_64 | Wrapper, path, line ending, script batch. |
| macOS ARM64 | Toolchain và native dependency trên kiến trúc ARM. |
| Linux ARM64 | Image và thư viện native cho node ARM. |

Không phải dự án nào cũng cần tất cả môi trường. Chọn ma trận theo nơi artifact được build và triển khai.

### Kiểm tra native dependency

Một thư viện Java có thể gọi native library qua JNI/JNA hoặc phụ thuộc binary bên ngoài. Khi đó, artifact Java giống nhau nhưng runtime behavior có thể khác theo OS/CPU. Cần quản lý binary tương ứng, kiến trúc và ABI; không thể giả định một JAR chứa native code cho mọi nền tảng.

### Kiểm tra shell và script

Nếu dự án có script .sh, hãy chạy trên shell/OS mục tiêu. Nếu có .bat hoặc PowerShell script, kiểm tra riêng trên Windows. Không nên coi một script Bash chạy thành công trong Git Bash là bằng chứng nó chạy được trong PowerShell hoặc Command Prompt.

## 18. Ghi nhận bằng chứng build

Để người khác có thể kiểm tra lại, lưu thông tin tối thiểu cho mỗi build quan trọng:

- Repository URL và commit SHA.
- Branch/tag và trạng thái working tree.
- Phiên bản JDK và vendor nếu có yêu cầu.
- Phiên bản Gradle/Maven Wrapper.
- Phiên bản OS và architecture.
- Dependency lock state hoặc dependency tree.
- Các profile/property được truyền vào build (không lưu secret).
- Lệnh build chính xác.
- Trạng thái test và đường dẫn report.
- Tên artifact, kích thước và SHA-256.
- Base image tag/digest nếu có container image.

Không đưa password, token hoặc nội dung secret vào build log hoặc metadata. Chỉ ghi tên secret/secret reference và nguồn cấp nếu cần truy vết.

### Build metadata

Có thể tạo file metadata đi kèm artifact hoặc image label để liên hệ sản phẩm với source revision. Ví dụ thông tin:

    application.version=1.0.0
    source.revision=a1b2c3d
    build.tool=Gradle 8.x
    java.version=21

Giá trị thực tế nên được tạo tự động từ CI hoặc build configuration, không nhập tay. Nếu metadata chứa timestamp, artifact có thể không còn byte-identical giữa hai lần build; hãy cân nhắc tách metadata thời gian khỏi nội dung cần tái lập.

## 19. Những lỗi thường gặp khi build từ checkout sạch

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Wrapper không chạy trên Linux | Thiếu executable bit hoặc line ending sai. | Kiểm tra mode trong Git, LF và quyền thực thi. |
| Build dùng Gradle/Maven khác máy cũ | Dùng lệnh cài toàn cục thay wrapper. | Dùng gradlew hoặc mvnw đã commit. |
| Không tìm thấy compiler hoặc JDK | JAVA_HOME, toolchain hoặc JDK version chưa đúng. | Kiểm tra java -version, wrapper JVM và toolchain. |
| Dependency không tải được | Repository private, credentials, proxy hoặc VPN chưa cấu hình. | Kiểm tra URL, quyền và secret configuration. |
| Build cũ thành công nhưng checkout mới thất bại | Dependency được cài thủ công hoặc file local chưa commit. | Tìm nguồn dependency/file, khai báo đúng trong project hoặc tài liệu hóa đầu vào. |
| Test khác kết quả giữa hai máy | Timezone, locale, clock, random seed hoặc dữ liệu external khác nhau. | Cố định input test và cấu hình môi trường rõ ràng. |
| Build chỉ chạy trong IDE | IDE bổ sung cấu hình hoặc classpath không có trong wrapper build. | Đưa cấu hình cần thiết vào build script và kiểm tra bằng Terminal. |
| JAR checksum khác | Timestamp, metadata, dependency hoặc tool khác nhau. | So sánh commit, toolchain, dependency graph và archive settings. |
| Build container thiếu JAR | .dockerignore loại output hoặc Dockerfile copy sai đường dẫn. | Kiểm tra build context và đường dẫn COPY. |
| Linux báo không tìm thấy resource nhưng Windows chạy được | Sai chữ hoa/thường hoặc dùng path separator không phù hợp. | Chuẩn hóa tên file và dùng API đường dẫn. |
| Build thất bại do generated source | Task sinh mã chưa khai báo dependency hoặc tool không có trên máy mới. | Khai báo task/input/output và version công cụ. |
| Build treo khi tải dependency | Proxy, DNS, repository rate limit hoặc network. | Kiểm tra kết nối và cấu hình mirror/proxy. |

## 20. Quy trình kiểm tra trên máy mới

### Trước khi chạy

- [ ] Checkout đúng commit SHA.
- [ ] Working tree sạch.
- [ ] Đọc README/onboarding và các yêu cầu môi trường.
- [ ] Kiểm tra JDK và architecture.
- [ ] Dùng đúng Gradle/Maven Wrapper.
- [ ] Cấp cấu hình local và credentials qua kênh an toàn.
- [ ] Xác nhận repository dependency truy cập được.
- [ ] Kiểm tra tool ngoài và quyền thực thi script.

### Trong khi chạy

- [ ] Chạy lệnh build/test chuẩn từ tài liệu.
- [ ] Ghi lại command và exit code.
- [ ] Lưu log và test report.
- [ ] Xác nhận dependency graph nếu có khác biệt.
- [ ] Không bỏ qua test chỉ để làm build thành công.

### Sau khi chạy

- [ ] Xác nhận artifact được tạo đúng vị trí.
- [ ] Kiểm tra nội dung JAR/WAR hoặc image.
- [ ] Tính checksum nếu cần so sánh.
- [ ] Ghi nhận JDK, wrapper, OS, commit và dependency state.
- [ ] Thử chạy artifact trong runtime tương ứng.
- [ ] Ghi lại mọi bước thủ công chưa được tự động hóa.

Checklist này giúp không bỏ sót đầu vào môi trường. Nó không thay thế kiểm thử chức năng hoặc review chất lượng.

## 21. Bài thực hành

Thực hiện với một project Java có Gradle hoặc Maven:

1. Ghi lại commit SHA và trạng thái Git trên máy đang phát triển.
2. Clone repository vào một thư mục hoàn toàn mới hoặc tạo worktree tại commit đó.
3. Kiểm tra README, wrapper files, JDK version và các biến môi trường cần thiết.
4. Chạy wrapper --version để xác nhận đúng phiên bản build tool.
5. Tạo cache dependency riêng hoặc local Maven repository riêng để kiểm tra việc tải dependency từ đầu.
6. Chạy clean test với Gradle hoặc clean verify với Maven.
7. Xác nhận test report và artifact được tạo.
8. In dependency tree hoặc xác nhận lock state nếu dự án sử dụng dependency locking.
9. Tính SHA-256 của artifact và so sánh với lần build trên máy đầu tiên khi hai môi trường đã được kiểm soát tương đương.
10. Nếu checksum khác, so sánh commit, JDK, wrapper, dependency, timestamp, generated file và metadata trước khi kết luận.
11. Nếu dự án tạo image, build image từ checkout sạch, kiểm tra base image và chạy container thử nghiệm.
12. Viết lại những bước môi trường cần thiết để một thành viên mới có thể tái hiện quy trình mà không cần hỏi người đã tạo dự án.

Sau bài thực hành, bạn cần giải thích được vì sao checkout sạch quan trọng, wrapper kiểm soát phần nào của môi trường, JDK và dependency được cố định ra sao, cache khác output như thế nào, và cách so sánh artifact bằng checksum. Bạn cũng cần phân biệt build thành công, build có thể chạy lại và reproducible build ở mức byte.

## 22. Tiêu chí hoàn tất một lần kiểm tra build từ máy khác

Một lần xác minh có thể được xem là hoàn tất khi:

1. Máy mới checkout đúng source revision.
2. Môi trường build đáp ứng yêu cầu được tài liệu hóa.
3. Wrapper chạy đúng phiên bản công cụ.
4. Dependency được giải quyết từ repository đã khai báo, không dựa vào cài đặt thủ công không được ghi nhận.
5. Build và các test bắt buộc hoàn tất thành công.
6. Artifact mong muốn được tạo và có thể kiểm tra.
7. Những khác biệt về checksum hoặc runtime được giải thích bằng đầu vào cụ thể.
8. Các bước thủ công còn thiếu được ghi lại để cải thiện onboarding hoặc build automation.

Nếu build thất bại, kết quả vẫn hữu ích: nó cho biết một đầu vào hoặc giả định chưa được quản lý. Hãy ghi lại commit, môi trường, command và lỗi đầu tiên để nhóm có thể sửa đúng nguyên nhân. Mục tiêu là để bất kỳ thành viên nào có repository, quyền truy cập và môi trường đã công bố đều có thể tạo lại artifact theo cùng một quy trình.

