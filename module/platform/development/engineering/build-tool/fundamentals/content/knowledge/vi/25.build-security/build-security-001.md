# Rủi ro từ thư viện, plugin và script được thực thi khi build

Build Java không chỉ là quá trình biên dịch source code. Maven và Gradle còn đọc build script, nạp plugin, chạy annotation processor, thực thi code generator, gọi task tùy chỉnh, chạy test và có thể khởi chạy shell command. Những thành phần này thường chạy với quyền của tài khoản đang thực hiện build. Trong CI, tài khoản đó có thể đọc source nội bộ, lấy secret, truy cập mạng, ghi artifact và sử dụng cache dùng chung.

Vì vậy, một thư viện hoặc plugin được thêm vào build có thể tạo ra rủi ro lớn hơn việc thêm một thư viện chỉ được ứng dụng gọi khi chạy. Plugin, build extension, annotation processor và script có thể thực thi code ngay trong quá trình build. Nếu thành phần đó bị xâm nhập, build script độc hại có thể đọc biến môi trường, sửa artifact, lấy credential hoặc gửi dữ liệu ra ngoài.

Bài này giải thích bề mặt thực thi của build, các kiểu tấn công chuỗi cung ứng phần mềm, cách kiểm soát plugin và dependency, bảo vệ credential, cô lập CI và xác minh artifact. Các ví dụ tập trung vào Maven và Gradle.

## 1. Vì sao build cần được xem là một môi trường thực thi code?

Một build tool nhận đầu vào từ nhiều nguồn:

- Build file và script do dự án quản lý.
- Plugin được tải từ plugin portal hoặc artifact repository.
- Dependency của plugin và build extension.
- Annotation processor và compiler plugin.
- Script shell, PowerShell hoặc executable được task gọi.
- Test code và integration test.
- Code generator, formatter, linter và công cụ phân tích.
- Init script, Maven extension và cấu hình toàn cục trên máy build.

Những thành phần này có thể chạy code trong lúc build. Ví dụ, Gradle plugin có thể khai báo task và thực thi logic của task; Maven plugin có thể chạy Mojo trong lifecycle; annotation processor chạy trong tiến trình compiler; test chạy code của test và code được test gọi.

Sơ đồ khái quát:

~~~text
CI runner / máy developer
        |
        v
Maven hoặc Gradle
        |
        +--> Build script, settings, extension
        |
        +--> Plugin và dependency của plugin
        |
        +--> Compiler, annotation processor, generator
        |
        +--> Test và integration test
        |
        +--> Shell command / executable được task gọi
        |
        v
Source, artifact, cache, credentials, network
~~~

Một plugin có thể truy cập những tài nguyên mà build process được cấp quyền truy cập. Nếu build chạy bằng tài khoản có quyền đọc private repository, cloud credentials hoặc signing key, code plugin có thể tìm cách sử dụng những quyền đó. Build tool không tự biến mọi plugin thành code an toàn chỉ vì plugin được khai báo trong file cấu hình.

## 2. Phân biệt dependency dùng lúc chạy và dependency chạy trong build

Không phải mọi dependency đều có cùng thời điểm thực thi hoặc cùng mức rủi ro.

| Thành phần | Thời điểm được sử dụng | Khả năng thực thi code trong build |
|---|---|---|
| Thư viện runtime của ứng dụng | Khi ứng dụng chạy | Thường không chạy chỉ vì được resolve; có thể được nạp bởi test hoặc task |
| Thư viện compile API | Khi compile hoặc khi code tham chiếu API | Bản thân JAR thường được đọc để kiểm tra type; annotation/processor liên quan có thể chạy |
| Maven/Gradle plugin | Khi build tool nạp hoặc gọi plugin | Có; plugin code chạy trong môi trường build |
| Build extension | Khi build tool khởi tạo | Có; có thể chạy rất sớm |
| Annotation processor | Trong quá trình compile | Có; processor là code chạy trong tiến trình compiler |
| Test dependency và test code | Khi chạy test | Có; test và thư viện test được thực thi |
| Code generator | Khi task/giai đoạn generate chạy | Có; generator có thể đọc/ghi file và truy cập hệ thống |
| Shell script/task command | Khi task được gọi | Có; command chạy theo quyền của runner |

Một dependency chỉ nằm trong runtime classpath không đồng nghĩa nó tự động được chạy trong build. Tuy nhiên, test, plugin hoặc generator có thể chủ động nạp nó. Ngược lại, plugin và annotation processor thường được thực thi dù ứng dụng cuối cùng không chứa chúng.

Khi đánh giá rủi ro, cần biết thành phần được resolve vào configuration/classpath nào, task nào sử dụng nó và quyền mà tiến trình đó đang có.

## 3. Plugin và build extension có quyền lực lớn

Plugin thường được tin cậy để tự động hóa compile, test, packaging, deployment hoặc kiểm tra chất lượng. Để làm công việc đó, plugin có thể đọc build model, truy cập file, khởi chạy process, gọi network API hoặc tạo task khác.

Ví dụ, một plugin có thể:

- Đọc source và resource.
- Đọc cấu hình build, dependency graph và environment variables.
- Ghi file vào build directory hoặc vị trí khác mà process có quyền.
- Chạy compiler, test runner hoặc shell command.
- Gọi repository hoặc dịch vụ bên ngoài.
- Thực hiện upload artifact.
- Đọc credential được cấp cho build.

Quyền thực tế phụ thuộc operating system, container, tài khoản, sandbox và cấu hình runner. Không nên giả định plugin chỉ được phép sửa thư mục build.

### 3.1. Maven plugin và extension

Maven plugin được gọi trong lifecycle hoặc bằng goal trực tiếp. Ví dụ Compiler Plugin, Surefire Plugin, JAR Plugin, Shade Plugin và Deploy Plugin đều là code chạy trong tiến trình Maven.

Maven còn có extension được nạp trong quá trình khởi tạo, ví dụ:

- Build extension khai báo trong POM qua cơ chế extension.
- Core extension trong thư mục .mvn/extensions.xml.
- Extension được cung cấp qua Maven distribution hoặc cấu hình toàn cục.

Extension có thể ảnh hưởng cách Maven xây dựng project model, resolve dependency hoặc thực thi lifecycle. Vì được nạp sớm, extension cần được xem xét cẩn thận như một thành phần có quyền thực thi cao.

### 3.2. Gradle plugin và init script

Gradle plugin được nạp từ plugin DSL, buildscript classpath hoặc convention plugin. Plugin có thể đăng ký task, cấu hình project và thực thi logic trong task action.

Ngoài build file của repository, Gradle còn có init script. Init script có thể được đặt trong thư mục cấu hình người dùng hoặc được truyền qua command line. Nó có thể thay đổi repository, inject plugin, cấu hình enterprise service hoặc tác động đến nhiều build trên máy đó.

Một init script không được review có thể khiến build chạy khác với những gì source repository thể hiện. Khi chẩn đoán build trên máy lạ hoặc runner dùng image tùy chỉnh, cần kiểm tra cả init script và cấu hình Gradle toàn cục.

## 4. Các kiểu tấn công chuỗi cung ứng build

### 4.1. Dependency confusion

Dependency confusion xảy ra khi build lấy package cùng tên từ nguồn không mong muốn. Ví dụ, tổ chức có module nội bộ tên com.example:payments-core nhưng cấu hình repository cho phép tải một module cùng tọa độ từ public repository. Nếu resolution policy hoặc thứ tự repository không được kiểm soát, attacker có thể phát hành package trùng tên với version được chọn cao hơn hoặc lợi dụng quy tắc lookup.

Biện pháp giảm thiểu:

- Quy định repository nào được phép phục vụ group nội bộ.
- Dùng exclusive content hoặc content filter phù hợp.
- Không cho package nội bộ rơi về public repository.
- Tập trung repository qua repository manager của tổ chức.
- Theo dõi tọa độ, version và nguồn của module được resolve.

### 4.2. Typosquatting và package giả mạo

Attacker có thể phát hành package có tên gần giống dependency phổ biến hoặc tên nội bộ, hy vọng developer gõ sai group/artifact. Package giả có thể chứa code đánh cắp credential hoặc sửa artifact.

Hãy kiểm tra tọa độ từ tài liệu chính thức hoặc source repository của nhà cung cấp. Với dependency mới, xác minh publisher, lịch sử phát hành, repository chính thức và checksum/signature nếu có. Không thêm dependency chỉ dựa trên một kết quả tìm kiếm hoặc tên gần giống.

### 4.3. Maintainer hoặc tài khoản phát hành bị xâm nhập

Một package hợp pháp có thể bị phát hành phiên bản độc hại nếu tài khoản maintainer, token publish hoặc pipeline release bị chiếm quyền. Tọa độ vẫn đúng và version vẫn có vẻ hợp lệ, nhưng nội dung artifact đã thay đổi.

Các biện pháp hữu ích gồm:

- Xác minh checksum/signature theo nguồn tin cậy.
- Pin version và khóa dependency graph.
- Theo dõi thay đổi bất thường ở version mới.
- Kiểm tra provenance và nguồn phát hành.
- Giới hạn quyền publish và bảo vệ tài khoản maintainer.
- Không tự động nâng tất cả dependency lên version mới mà không có kiểm soát.

### 4.4. Plugin hoặc build script độc hại

Một plugin có thể thực hiện hành vi ngoài mục đích được quảng cáo. Build script cũng có thể chứa task gọi shell, tải executable hoặc thực thi code được lấy từ network.

Ví dụ rủi ro:

- Task gửi environment variables đến endpoint bên ngoài.
- Plugin sửa file JAR sau khi ký.
- Script thay đổi repository để tải dependency từ nguồn khác.
- Task thu thập source code hoặc thông tin hệ thống.
- Build step thêm backdoor vào generated source hoặc resource.

Đây là lý do phải review thay đổi build file, plugin version, init script và script CI như review source code thông thường.

### 4.5. Compromised transitive dependency

Plugin có thể kéo theo nhiều dependency khác. Một dependency bắc cầu có thể bị xâm nhập dù plugin trực tiếp có vẻ đáng tin. Vì vậy, chỉ kiểm tra tên plugin cấp cao nhất chưa đủ.

Hãy xem dependency graph của plugin/build logic khi công cụ hỗ trợ, giới hạn repository nguồn, pin version và dùng dependency verification. Đối với plugin quan trọng, theo dõi cả transitive dependencies và cập nhật có kiểm soát.

## 5. Annotation processor và code generator cũng là code thực thi

Annotation processor chạy trong quá trình biên dịch để đọc annotation, phân tích type và sinh source/resource. Processor có thể chạy code Java với quyền của compiler process.

Một processor đáng tin có thể giúp sinh mapper, metamodel hoặc boilerplate. Processor độc hại có thể đọc file, truy cập network hoặc ghi dữ liệu không mong muốn.

Tương tự, code generator có thể là:

- Plugin Maven/Gradle.
- Java application được task khởi chạy.
- Executable bên ngoài.
- Script tải hoặc sinh code.
- Công cụ sinh client từ OpenAPI/Protocol Buffers/schema.

Các câu hỏi cần trả lời khi thêm processor/generator:

1. Ai phát hành công cụ và source code ở đâu?
2. Version nào được dùng và có pin version không?
3. Công cụ được tải từ repository nào?
4. Nó được chạy trong process nào và có quyền gì?
5. Nó đọc những input nào và ghi vào output directory nào?
6. Có thể chạy offline hoặc trong sandbox không?
7. Generated output có được review và kiểm tra trong CI không?

Đừng coi generated source là vô hại chỉ vì nó được sinh tự động. Nó sẽ được compile và có thể đi vào artifact cuối cùng.

## 6. Script trong build và CI

Script thường được xem là glue code, nhưng nó có thể chạy với toàn bộ quyền của runner. Các lệnh shell, PowerShell, Exec task, npm command hoặc executable tùy chỉnh đều là bề mặt thực thi.

Ví dụ Gradle Exec task:

~~~kotlin
tasks.register<Exec>("generateNativeResources") {
    commandLine("tools/generate-resources", "--input", "schema")
}
~~~

Ví dụ Maven có thể gọi executable qua plugin chuyên dụng. Khi review, cần biết executable đến từ đâu, checksum/version của nó, tham số truyền vào và output mà nó có thể sửa.

Các script CI cũng có thể:

- Checkout source từ pull request.
- Tải tool hoặc action/plugin bên ngoài.
- Khởi chạy test và build.
- Đọc secret để publish.
- Đóng gói, ký và upload artifact.

Nếu untrusted contribution có thể thay đổi script rồi chạy trong job có release secret, attacker có thể lấy secret trước khi artifact được tạo. Tách job kiểm thử pull request khỏi job phát hành có quyền cao.

## 7. Repository và nguồn tải plugin/dependency

Repository configuration quyết định build lấy code từ đâu. Một repository được thêm vào có thể trở thành nguồn cung cấp code chạy trong build.

### 7.1. Maven

Maven phân biệt:

- repositories cho dependency của project.
- pluginRepositories cho Maven plugin.
- mirrors trong settings.xml để chuyển request qua repository khác.
- distributionManagement cho publication.

Credential thường được cấu hình trong settings.xml và ghép theo server ID. Nếu repository mirror thay thế endpoint ban đầu, hãy xác định credential ID nào được Maven sử dụng.

Tổ chức nên ưu tiên một repository manager có kiểm soát upstream, quyền truy cập, cache và audit. Không nên cho phép mỗi project tùy ý thêm public repository không được review, đặc biệt khi project có dependency nội bộ.

### 7.2. Gradle

Gradle có các nguồn repository khác nhau:

- pluginManagement.repositories cho plugin DSL.
- dependencyResolutionManagement.repositories hoặc project repositories cho dependency.
- buildscript.repositories cho classpath của build script kiểu cũ.
- publishing.repositories cho upload.

Plugin marker artifact có thể được resolve trước implementation module. Nếu dùng repository nội bộ, cần đảm bảo cả marker lẫn implementation có thể được tìm thấy hoặc có mapping rõ ràng.

Gradle có content filter và exclusive content để giới hạn group/module nào được phép đến từ repository nào. Dùng các rule này để tách namespace nội bộ và public.

### 7.3. HTTP không bảo đảm nguồn tải

Không dùng HTTP không mã hóa cho repository chứa plugin hoặc dependency. HTTPS bảo vệ kết nối và xác thực server qua certificate, nhưng không tự chứng minh package an toàn. Cần kết hợp TLS với xác minh artifact, kiểm soát repository và provenance.

## 8. Pin version và quản lý dependency graph

Version động như latest, plus version hoặc range rộng có thể khiến build resolve nội dung khác nhau theo thời gian. Điều đó làm khó tái hiện build và tăng nguy cơ nhận một release độc hại mới mà không có thay đổi source rõ ràng.

Ví dụ dependency Gradle có version cố định:

~~~kotlin
dependencies {
    implementation("com.example:customer-api:2.4.1")
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>customer-api</artifactId>
    <version>2.4.1</version>
</dependency>
~~~

Pin version giúp xác định version mong muốn nhưng chưa đảm bảo artifact tại tọa độ đó không bị thay đổi. Kết hợp pin version với release immutability, checksum/signature verification và repository policy.

### 8.1. Maven dependency management

Maven BOM và dependencyManagement giúp tập trung version để các module dùng cùng một bộ dependency. Plugin version nên được quản lý trong pluginManagement, không để version plugin thay đổi ngầm theo môi trường.

Ví dụ:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Khi dùng parent POM, kiểm tra effective POM để biết plugin version cuối cùng. Không phải mọi plugin đều được khai báo trực tiếp trong POM con.

### 8.2. Gradle version catalog và dependency locking

Version catalog giúp tập trung tọa độ/version:

~~~toml
[versions]
jackson = "2.17.2"

[libraries]
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind", version.ref = "jackson" }
~~~

Dependency locking giúp ghi nhận version được resolve cho các configuration được khóa:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó tạo/cập nhật lock state bằng task thích hợp của Gradle, review các thay đổi lockfile và commit chúng. Locking làm cho version được chọn có thể tái lập; nó không xác minh nội dung JAR nếu repository thay thế file tại cùng tọa độ.

## 9. Dependency verification và checksum

Gradle dependency verification có thể xác minh checksum hoặc chữ ký của dependency đã được khai báo trong verification metadata. Khi artifact thay đổi ngoài dự kiến, build có thể thất bại thay vì âm thầm chấp nhận nội dung mới.

Một quy trình thường gặp:

1. Bật dependency verification trong Gradle.
2. Tạo metadata ban đầu từ dependency đã được xác minh qua nguồn đáng tin cậy.
3. Review checksum/signature được ghi nhận.
4. Commit verification metadata.
5. Khi nâng dependency, xác minh thay đổi rồi cập nhật metadata có chủ đích.

Không nên chấp nhận mọi checksum mới chỉ vì Gradle đề xuất cập nhật. Nếu artifact đã thay đổi, cần xác minh lý do, nguồn và release trước khi tin cậy.

Maven cũng có thể được tích hợp với quy trình kiểm tra checksum, chữ ký hoặc repository manager policy. Cơ chế cụ thể phụ thuộc công cụ và hạ tầng; việc bật HTTPS đơn thuần không thay thế xác minh tính toàn vẹn.

### 9.1. Checksum và chữ ký chứng minh điều gì?

Checksum cho biết nội dung file có khớp với digest được tin cậy hay không. Nếu attacker thay được cả artifact và checksum trên cùng nguồn không được bảo vệ, checksum không chứng minh publisher.

Chữ ký số gắn nội dung với private key của signer. Consumer vẫn cần tin cậy public key/certificate và kiểm tra trạng thái/chuỗi tin cậy theo policy.

Không dùng một digest lấy từ chính nguồn đáng ngờ làm bằng chứng độc lập. Hãy lấy checksum/signature metadata từ nguồn phát hành đáng tin cậy hoặc quy trình verification đã được tổ chức quản lý.

## 10. Bảo vệ credential và secret trong build

Build có thể cần credential để tải private dependency, publish artifact, ký JAR hoặc truy cập cloud. Secret thường được cung cấp qua environment variables, settings file hoặc CI secret store.

Nếu plugin hoặc script độc hại chạy trong cùng process/job, nó có thể đọc secret mà process đó được phép truy cập. Việc lưu secret trong biến môi trường không tự cô lập secret khỏi plugin.

### 10.1. Tách quyền theo job

Nên phân chia pipeline:

~~~text
Pull request từ nhánh không tin cậy
        |
        v
Build + test không có release secret
        |
        v
Review / merge vào nhánh được bảo vệ
        |
        v
Release job với quyền publish tối thiểu
        |
        v
Ký và upload artifact
~~~

Không cấp signing key, publish token hoặc cloud administrator credential cho job chạy code tùy ý từ pull request bên ngoài. Nếu test cần credential để truy cập dịch vụ, hãy dùng credential riêng có quyền hạn thấp và dữ liệu thử nghiệm.

### 10.2. Không ghi secret vào build file

Không viết credential thật trong:

- pom.xml.
- build.gradle hoặc build.gradle.kts.
- settings.gradle hoặc settings.gradle.kts.
- gradle.properties được commit.
- Script shell/PowerShell.
- Source code hoặc resource.
- URL repository có username/password.

Dùng secret store của CI hoặc file cấu hình riêng không được commit. Với Maven, settings.xml có thể đặt ở vị trí người dùng/CI và dùng server ID. Với Gradle, có thể đọc từ environment variable hoặc cơ chế credential injection của CI.

Ví dụ Gradle:

~~~kotlin
publishing {
    repositories {
        maven {
            url = uri("https://repo.example.com/releases")
            credentials {
                username = providers.environmentVariable("REPO_USER").orNull
                password = providers.environmentVariable("REPO_TOKEN").orNull
            }
        }
    }
}
~~~

Đoạn cấu hình cho thấy cách đọc secret từ environment; pipeline phải bảo đảm biến được cấp đúng lúc publish. Không in giá trị credential để chẩn đoán.

### 10.3. Giới hạn phạm vi và thời hạn secret

Một build test thông thường không cần quyền xóa package, quản trị repository hoặc phát hành production. Dùng token riêng cho từng mục đích:

- Read-only dependency access.
- Publish snapshot.
- Publish release.
- Signing.
- Deploy môi trường thử nghiệm.

Ưu tiên token có thời hạn ngắn, quyền hẹp và có thể thu hồi. Khi nghi ngờ plugin/script đã đọc secret, thu hồi hoặc xoay vòng credential liên quan và kiểm tra log/audit theo quy trình tổ chức.

## 11. Cô lập build và giảm quyền của runner

Build nên chạy trong môi trường có quyền tối thiểu cần thiết. Cô lập giúp giới hạn thiệt hại nếu plugin hoặc script bị xâm nhập.

Các lớp kiểm soát có thể gồm:

- Chạy bằng user riêng không có quyền administrator/root.
- Dùng container hoặc ephemeral VM cho job.
- Giới hạn filesystem mount ở mức cần thiết.
- Không mount home directory hoặc SSH key cá nhân vào job không tin cậy.
- Giới hạn network egress nếu build không cần truy cập tùy ý.
- Tách cache giữa dự án/nhóm tin cậy và untrusted pull request.
- Hủy runner sau job hoặc làm sạch workspace theo chính sách.
- Không chia sẻ daemon hoặc process state giữa trust boundary khác nhau.
- Cấp quyền publish chỉ trong job release được bảo vệ.

Container không phải sandbox tuyệt đối. Nếu container chạy privileged, mount Docker socket, mount host filesystem hoặc có credential mạnh, code bên trong vẫn có thể ảnh hưởng host/hạ tầng. Hãy đánh giá cấu hình thực tế.

### 11.1. Không chạy build bằng quyền cao

Tránh chạy Maven/Gradle bằng tài khoản administrator/root chỉ để giải quyết lỗi permission. Sửa quyền trên workspace, cache hoặc output directory theo nguyên tắc tối thiểu.

Nếu build cần ghi vào thư mục hệ thống hoặc sửa global tool installation, hãy xem lại thiết kế pipeline. Build thông thường nên ghi vào workspace và thư mục cache riêng của user.

### 11.2. Network egress

Plugin có thể mở kết nối ra ngoài nếu runner cho phép. Hạn chế outbound network đến các repository/service cần thiết giúp giảm khả năng exfiltration và tải executable không được phê duyệt.

Một mô hình thường dùng là chỉ cho phép runner truy cập repository manager nội bộ, còn repository manager chịu trách nhiệm proxy upstream đã được phê duyệt. Với job cần gọi dịch vụ khác, mở quyền truy cập theo hostname/port cụ thể và theo dõi.

## 12. Cache và nguy cơ nhiễm bẩn giữa các build

Cache giúp tăng tốc build nhưng có thể tạo rủi ro nếu nhiều trust boundary dùng chung cache.

Ví dụ:

- Một job không tin cậy ghi dữ liệu vào cache mà job release tin cậy dùng lại.
- Dependency cache giữ artifact bị thay thế hoặc metadata không mong muốn.
- Build cache remote cho phép một bên không tin cậy ghi output mà bên khác tin cậy đọc.
- Workspace còn lại file được tạo bởi job trước.
- Gradle init script hoặc Maven settings toàn cục làm thay đổi resolution.

Biện pháp:

- Phân vùng cache theo project hoặc mức độ tin cậy.
- Giới hạn quyền ghi remote build cache.
- Chỉ cho job đáng tin ghi cache dùng chung.
- Không dùng output từ untrusted job cho release nếu chưa tái tạo/xác minh.
- Làm sạch workspace hoặc dùng runner ephemeral.
- Review cấu hình cache và init script.

Dependency cache và build output cache là hai khái niệm khác nhau. Cần bảo vệ cả artifact đã tải lẫn output task được chia sẻ.

## 13. Wrapper và build tool distribution

Maven Wrapper và Gradle Wrapper giúp dự án chọn phiên bản build tool thống nhất. Tuy nhiên, wrapper script và distribution URL cũng là đầu vào cần tin cậy.

### 13.1. Gradle Wrapper

Các file thường có:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Wrapper properties xác định distribution URL và có thể khai báo distributionSha256Sum để xác minh checksum của distribution tải về.

Khi nâng Gradle:

1. Dùng quy trình nâng version đã review.
2. Kiểm tra distribution URL là nguồn chính thức hoặc mirror được tổ chức tin cậy.
3. Xác minh checksum theo nguồn độc lập đáng tin cậy.
4. Review thay đổi wrapper scripts/JAR/properties.
5. Chạy build trên CI sạch trước khi merge.

Không chỉ thay version string mà bỏ qua wrapper JAR hoặc script bất thường. Wrapper là code được thực thi trước khi build script dự án chạy.

### 13.2. Maven Wrapper

Maven Wrapper cũng chứa script, wrapper properties và có thể có wrapper JAR tùy chế độ phân phối. Cần kiểm tra distribution URL, wrapper configuration và nguồn của wrapper components.

Khi cập nhật Maven Wrapper, dùng plugin/command chính thức theo quy trình dự án, review diff và xác nhận Maven distribution được tải từ nguồn tin cậy. Nếu tổ chức mirror Maven distribution, endpoint phải được quản trị và bảo vệ tương ứng.

## 14. Review thay đổi build file như thay đổi mã nguồn

Pull request thay đổi build configuration có thể thay đổi code được thực thi hoặc nguồn tải dependency. Các thay đổi đáng chú ý:

- Thêm hoặc đổi plugin.
- Nâng plugin version.
- Thêm repository hoặc thay repository URL.
- Thay đổi mirror, content filter hoặc exclusive content.
- Thêm annotation processor.
- Thêm Gradle init script hoặc Maven extension.
- Thêm task Exec hoặc shell script.
- Thay đổi wrapper version/distribution URL.
- Thay đổi dependency verification/lockfile.
- Thêm bước upload, ký hoặc đọc secret.

Review cần hỏi:

1. Vì sao cần thay đổi này?
2. Plugin/tool đến từ đâu và ai duy trì?
3. Version có pin không?
4. Thành phần nào sẽ chạy trong build?
5. Nó cần quyền filesystem, network hoặc credential nào?
6. Nó có thêm repository hoặc thay nguồn dependency không?
7. Có thay đổi output artifact hoặc publication không?
8. Có test/CI xác nhận hành vi mới không?

Không merge thay đổi build script chỉ vì nó làm build qua được. Hãy hiểu code và quyền mà thay đổi đó đưa vào pipeline.

## 15. Maven: các điểm kiểm soát thực tế

### 15.1. Pin plugin version

Dùng pluginManagement để quản lý version tập trung và khai báo version cụ thể cho plugin. Tránh để plugin tự chọn version ngầm hoặc cập nhật ngoài quy trình review.

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

### 15.2. Giới hạn repository bằng settings và mirror

Tổ chức có thể buộc dependency/plugin đi qua repository manager nội bộ bằng mirror trong settings.xml. Điều này giúp kiểm soát upstream, audit và cache. Cấu hình phải bao gồm những repository thực sự cần thiết và không vô tình chuyển mọi request đến endpoint thiếu plugin.

Không đặt secret trực tiếp trong POM. Dùng server ID và credential trong settings file được bảo vệ.

### 15.3. Kiểm soát extension

Review file .mvn/extensions.xml và cấu hình extension trong POM. Extension được nạp sớm và có thể tác động toàn bộ build. Chỉ dùng extension có nguồn gốc/version rõ ràng và cần thiết.

### 15.4. Kiểm tra plugin graph và effective configuration

Maven có thể hiển thị dependency tree của project bằng Dependency Plugin. Plugin dependency graph có thể cần công cụ hoặc log chuyên biệt tùy plugin. Dùng effective POM/settings để xác định plugin, repository và profile thực tế.

Không phải mọi Maven plugin đều có cơ chế lockfile toàn diện tương đương Gradle dependency locking. Do đó, pin plugin version, kiểm soát repository và xác minh artifact là các biện pháp quan trọng.

## 16. Gradle: các điểm kiểm soát thực tế

### 16.1. Pin plugin và dependency version

Khai báo version plugin rõ trong plugin DSL hoặc convention plugin được quản lý. Dùng version catalog cho dependency và dependency locking để cố định version đã resolve.

### 16.2. Centralize repository

Đặt repository policy trong settings khi phù hợp. Dùng repositoriesMode để ngăn project con tùy tiện thêm repository. Dùng content filter/exclusive content cho namespace nội bộ.

### 16.3. Bật dependency verification

Quản lý verification metadata trong source repository. Khi cập nhật dependency, xác minh digest/signature từ nguồn tin cậy trước khi cập nhật file metadata.

### 16.4. Review init script và convention plugin

Convention plugin thường giúp chuẩn hóa build trong tổ chức nhưng cũng là code chạy trong build. Review source, version, repository và quyền phát hành của convention plugin. Kiểm tra init script trên runner và user home, nhất là khi build local và CI có hành vi khác nhau.

### 16.5. Bảo vệ remote build cache

Nếu dùng remote build cache, giới hạn quyền ghi cho build tin cậy và giới hạn quyền đọc theo policy. Không để pull request không tin cậy ghi cache mà release pipeline tin cậy sử dụng như nguồn output đã xác minh.

## 17. SBOM, provenance và attestations

SBOM (Software Bill of Materials) liệt kê các thành phần phần mềm trong sản phẩm. Nó giúp đội bảo mật biết artifact chứa dependency nào, version nào và hỗ trợ đánh giá tác động khi có lỗ hổng.

Provenance mô tả artifact được tạo như thế nào, từ source/commit nào, bằng builder nào và qua quy trình nào. Attestation có thể gắn các thông tin provenance với artifact theo cách có thể xác minh.

Các thông tin hữu ích trong release:

- Source repository và commit/tag.
- JDK và build tool version.
- Plugin và dependency version.
- Build workflow/runner identity.
- Artifact digest.
- SBOM.
- Chữ ký hoặc attestation.

SBOM không tự chứng minh dependency an toàn. Nó giúp kiểm kê và truy vết. Provenance không tự bảo đảm source không độc hại; nó giúp kiểm tra nguồn và quy trình tạo artifact. Cần kết hợp với review, verification, vulnerability scanning và quyền phát hành.

## 18. Quét lỗ hổng và theo dõi dependency

Dependency vulnerability scanner có thể so sánh tọa độ/version với cơ sở dữ liệu lỗ hổng. Công cụ có thể chạy trong CI, báo cáo CVE hoặc policy violation.

Quét lỗ hổng không phát hiện được mọi hành vi độc hại. Một package có thể không có CVE nhưng vẫn bị xâm nhập hoặc cố ý chứa hành vi không mong muốn. Ngược lại, một dependency có CVE không có nghĩa mọi cách sử dụng đều khai thác được.

Nên kết hợp:

- Vulnerability scanning.
- License policy nếu dự án cần.
- Dependency verification.
- SBOM và provenance.
- Theo dõi security advisory từ upstream.
- Review thay đổi dependency.
- Cập nhật có kiểm soát và kiểm thử tương thích.

Đối với plugin chạy trong build, ưu tiên xem cả security posture của plugin và dependency graph mà nó kéo theo.

## 19. Quy trình nâng cấp plugin/dependency an toàn

Khi cần thêm hoặc nâng plugin/thư viện:

1. Xác định chức năng thực sự cần và liệu có thể dùng công cụ đã được tổ chức phê duyệt.
2. Xác minh tọa độ chính xác, nhà phát hành, repository chính thức và lịch sử release.
3. Kiểm tra plugin có chạy code trong build hay dependency chỉ dùng lúc runtime.
4. Đọc release notes và security advisory.
5. Pin version cụ thể; cập nhật lockfile nếu dự án dùng dependency locking.
6. Xác minh checksum/signature hoặc dependency verification metadata.
7. Review transitive dependencies và repository nguồn.
8. Chạy trong CI không có release secret trước.
9. Kiểm tra generated source, task output và artifact diff.
10. Chỉ cấp quyền publish/signing trong job release được bảo vệ.

Nếu dependency mới cần truy cập mạng hoặc filesystem rộng, xác định lý do và giới hạn quyền của runner theo nhu cầu.

## 20. Điều tra khi nghi ngờ plugin hoặc script độc hại

Nếu build có hành vi bất thường, hãy giữ bằng chứng và cô lập trước khi chạy lại trong môi trường có quyền cao.

Các dấu hiệu đáng chú ý:

- Build bắt đầu gọi hostname lạ.
- Plugin/task mới đọc nhiều file ngoài workspace.
- Artifact có file hoặc bytecode không được giải thích.
- Environment variable hoặc credential xuất hiện trong log.
- Wrapper, init script hoặc Maven extension thay đổi không rõ lý do.
- Dependency version hoặc repository thay đổi ngoài pull request.
- Build task tải executable không được khai báo.
- Runner tạo process/network connection bất thường.

Quy trình điều tra:

1. Lưu log, commit hash, artifact digest và runner/job identity.
2. Tạm ngừng job release hoặc thu hồi quyền phát hành nếu có dấu hiệu credential bị lộ.
3. Không chạy lại build đáng ngờ với signing key hoặc production secret.
4. So sánh build file, wrapper, init script, extension và dependency lock/verification metadata với commit tin cậy.
5. Xác định plugin/task nào được thực thi và network/filesystem access tương ứng.
6. Kiểm tra repository audit log, CI log và secret access audit nếu có.
7. Xoay vòng credential có khả năng bị truy cập.
8. Tái tạo artifact từ source commit tin cậy trong runner sạch.
9. Xác minh digest, signature, SBOM và provenance trước khi phát hành lại.

Nếu chưa xác định được thành phần gây ra hành vi, không nên tiếp tục phát hành artifact từ pipeline đó.

## 21. Ví dụ mô hình pipeline có quyền tối thiểu

Một pipeline có thể tách thành các giai đoạn:

~~~text
Pull request validation
  - Checkout source
  - Resolve dependency read-only
  - Compile và test
  - Static analysis
  - Không có signing/release secret
          |
          v
Protected branch build
  - Source từ commit đã review
  - Runner sạch
  - Dependency verification
  - Build artifact
  - Generate SBOM/provenance
          |
          v
Release approval / policy gate
          |
          v
Release job
  - Credential publish tối thiểu
  - Signing key qua secure service
  - Sign artifact
  - Verify signature/checksum
  - Publish immutable version
          |
          v
Archive logs, SBOM, provenance, digests
~~~

Mô hình này giúp code không tin cậy từ pull request không chạy trong job có quyền ký hoặc publish release. Cách triển khai cụ thể tùy CI provider, nhưng nguyên tắc phân quyền theo giai đoạn vẫn áp dụng.

## 22. Những lỗi cấu hình bảo mật thường gặp

| Cấu hình hoặc hành vi | Rủi ro | Hướng xử lý |
|---|---|---|
| Plugin version không được pin | Build có thể nạp code khác theo thời gian | Pin version và review nâng cấp |
| Repository public có thể phục vụ group nội bộ | Dependency confusion | Dùng exclusive content/repository policy |
| Secret release có mặt trong pull request job | Script/plugin độc hại có thể lấy secret | Tách job và quyền |
| Dùng chung cache ghi được giữa job không tin cậy và release | Cache poisoning | Phân vùng cache và giới hạn quyền ghi |
| Không kiểm tra wrapper distribution | Build tool bootstrap có thể bị thay thế | Review wrapper và xác minh checksum |
| Tắt TLS hoặc checksum verification | Không xác minh nguồn/nội dung | Khôi phục verification và sửa trust chain |
| Dùng init script không được quản lý | Build bị thay đổi ngoài repository | Quản lý và audit init script |
| Chạy build bằng root/admin | Tăng phạm vi thiệt hại | Dùng user riêng, quyền tối thiểu |
| Task tải và chạy executable tùy ý | Thực thi code ngoài dependency graph đã review | Pin nguồn/version/digest và giới hạn network |
| Không khóa dependency graph | Version được chọn có thể thay đổi | Lock dependency và review thay đổi |
| Không lưu SBOM/provenance | Khó truy vết thành phần và nguồn build | Tạo và lưu metadata release |

## 23. Checklist thực hành cho nhóm phát triển

Trước khi merge thay đổi build:

- [ ] Plugin, extension, processor và generator có nguồn gốc rõ ràng.
- [ ] Version plugin/tool được pin.
- [ ] Repository mới được review và có policy phù hợp.
- [ ] Dependency graph/lockfile/verification metadata được cập nhật có chủ đích.
- [ ] Không thêm secret vào source hoặc build file.
- [ ] Script/task chỉ đọc và ghi các đường dẫn cần thiết.
- [ ] Không tải và chạy executable không xác minh.
- [ ] Wrapper changes được review.
- [ ] Test/build chạy được trên runner sạch.

Trước khi phát hành:

- [ ] Source commit và release tag được xác định.
- [ ] Build chạy trên runner được bảo vệ.
- [ ] Job từ pull request không có quyền release.
- [ ] Dependency verification và policy scan đã chạy.
- [ ] Artifact digest, SBOM và provenance được lưu.
- [ ] Artifact được ký bằng quy trình bảo vệ key.
- [ ] Signature/checksum được xác minh trước publish.
- [ ] Release version được publish theo policy bất biến.
- [ ] Log và metadata không chứa secret.

Checklist là công cụ hỗ trợ review. Mức kiểm soát cần thiết phụ thuộc độ nhạy của source, quyền của pipeline và cách sản phẩm được phân phối.

## 24. Những điều cần ghi nhớ

- Plugin, build extension, annotation processor, generator, test và shell task có thể thực thi code trong lúc build.
- Build code thường có quyền của tài khoản runner; quyền đó có thể bao gồm source, network, cache và credential.
- Runtime dependency và build-time executable dependency có thời điểm thực thi khác nhau; cần phân biệt configuration/classpath.
- Dependency confusion, typosquatting, maintainer compromise và plugin độc hại đều là rủi ro chuỗi cung ứng.
- Maven plugin/extension và Gradle plugin/init script cần được review như code thực thi.
- Pin version, lock dependency graph và xác minh checksum/signature giúp kiểm soát thay đổi artifact.
- Repository policy và content filter giúp ngăn package nội bộ bị lấy từ nguồn công khai không mong muốn.
- Không cấp signing key hoặc release token cho job chạy code không tin cậy.
- Cô lập runner, giới hạn quyền filesystem/network và phân vùng cache để giảm phạm vi ảnh hưởng.
- Wrapper distribution, script CI và generated source cũng thuộc bề mặt cần bảo vệ.
- SBOM và provenance hỗ trợ kiểm kê/truy xuất nhưng không thay thế review và xác minh.
- Khi nghi ngờ build bị xâm nhập, giữ bằng chứng, bảo vệ/thu hồi credential và tái tạo artifact trong môi trường sạch.

Build tool có thể thực thi nhiều loại code trước khi ứng dụng được chạy. Vì thế, bảo vệ build đồng nghĩa với việc kiểm soát ai cung cấp plugin/script, code đó được chạy ở đâu, được cấp quyền gì, tải dependency từ nguồn nào và artifact cuối được xác minh ra sao. Khi pin version, quản lý repository, bảo vệ secret, cô lập runner và lưu provenance được áp dụng nhất quán, pipeline sẽ giảm đáng kể khả năng một thành phần bị xâm nhập làm ảnh hưởng đến source, credential hoặc bản phát hành.
