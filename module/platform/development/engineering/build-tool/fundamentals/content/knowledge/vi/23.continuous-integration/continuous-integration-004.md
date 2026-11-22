# Build trên máy chạy CI sạch và xử lý đầu vào bị thiếu

Một build chạy thành công trên máy lập trình viên chưa chứng minh rằng dự án có thể build trong CI. Máy cá nhân thường đã có JDK, dependency cache, file cấu hình local, biến môi trường và công cụ được cài từ trước. Một CI runner sạch thường bắt đầu từ workspace mới, checkout source revision được chỉ định rồi thực hiện các bước build theo pipeline. Những đầu vào mà dự án vô tình mượn từ máy cá nhân sẽ không còn sẵn có.

Vì vậy, build trong CI cần mô tả rõ tất cả đầu vào: source code, build wrapper, JDK/toolchain, dependency, cấu hình, credentials, công cụ bên ngoài, dịch vụ tích hợp và tài nguyên cần thiết. Khi thiếu một đầu vào, pipeline nên phát hiện sớm, báo chính xác thứ còn thiếu và hướng dẫn cách cung cấp an toàn.

Bài học này giải thích cách tổ chức build trên máy CI sạch, cách phân loại đầu vào, cách xử lý thiếu cấu hình hoặc dependency, cách kiểm soát cache và dịch vụ ngoài, cùng phương pháp chẩn đoán lỗi chỉ xuất hiện trên CI.

~~~text
Source revision
      |
      v
Fresh CI workspace
      |
      v
Checkout + toolchain
      |
      v
Validate required inputs
      |
      v
Resolve dependencies
      |
      v
Compile + test + package
      |
      v
Verify outputs + reports
      |
      v
Publish artifacts / next pipeline stage
~~~

Một CI job đáng tin cậy phải có thể giải thích được nó lấy đầu vào từ đâu, dùng công cụ nào, tạo ra output nào và thất bại ở bước nào khi điều kiện chưa được đáp ứng.

## 1. CI runner sạch có ý nghĩa gì?

CI runner là môi trường thực thi pipeline. Tùy hệ thống, runner có thể là máy ảo tạm thời, container, máy vật lý hoặc self-hosted agent được tái sử dụng.

**Runner sạch (clean runner)** thường có nghĩa job bắt đầu trong workspace mới, không dựa vào output còn sót từ lần chạy trước. Tuy nhiên, sạch workspace không nhất thiết đồng nghĩa toàn bộ máy hoặc cache đều mới. Một runner có thể dùng image được cài sẵn JDK, Docker, Maven, Gradle hoặc có cache dependency được phục hồi.

Cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Fresh checkout | Source được checkout vào working directory mới hoặc được làm sạch theo chính sách CI. |
| Clean build | Output của lần build trước trong project được xóa hoặc không được tái sử dụng. |
| Cold dependency cache | Dependency cache không có artifact cần dùng và phải tải từ repository. |
| Build cache disabled | Build không khôi phục output task từ build cache. |
| Ephemeral runner | Môi trường được tạo cho job rồi bị hủy sau khi hoàn tất. |
| Self-hosted runner | Máy do tổ chức quản lý, có thể giữ cache, cấu hình hoặc file giữa các job nếu không được dọn đúng cách. |

Một job có fresh checkout nhưng dùng cache dependency vẫn có thể hợp lệ. Một job chạy trên self-hosted runner cũng có thể tạo workspace sạch. Điều quan trọng là xác định trạng thái nào được giữ lại và trạng thái nào phải được tạo lại.

### Vì sao build local và CI có thể khác nhau?

Máy phát triển có thể đã:

- Cài một JDK phù hợp dù project không khai báo rõ version.
- Cài một artifact nội bộ vào local Maven repository bằng tay.
- Có file .env hoặc cấu hình không được commit.
- Đã chạy generator để tạo source file nhưng task tạo file chưa được khai báo.
- Có Docker image hoặc database container còn chạy.
- Dùng proxy, VPN hoặc credentials được cấu hình ngoài repository.
- Có biến môi trường mà pipeline không thiết lập.
- Chạy từ thư mục làm việc khác với thư mục CI.
- Dùng hệ điều hành hoặc kiến trúc CPU khác.

CI làm lộ những phụ thuộc ẩn này. Khi sửa đúng nguồn đầu vào, cả local build và CI build sẽ dễ tái hiện hơn.

## 2. Phân loại đầu vào của một Java build

Trước khi xử lý lỗi, hãy phân loại đầu vào mà build cần.

| Nhóm đầu vào | Ví dụ | Nguồn cung cấp |
|---|---|---|
| Source | Java, resource, build script, wrapper | Git checkout |
| Toolchain | JDK, Gradle, Maven, compiler | Runner image, wrapper, toolchain |
| Dependency | JAR, plugin, BOM, parent POM | Maven/Gradle repository |
| Build configuration | Profile, property, feature flag | Repository hoặc pipeline variables |
| Secret/credential | Token, password, signing key | CI secret store hoặc identity |
| External tool | Docker, Node.js, protoc, native compiler | Runner image hoặc setup step |
| External service | Database, message broker, API | Service container hoặc môi trường test |
| Runtime configuration | Port, endpoint, profile, resource limit | Deployment environment |
| Generated input | Source sinh từ schema, OpenAPI, protobuf | Task/plugin generator |
| Artifact output | JAR, WAR, test report, checksum | Workspace hoặc artifact storage |

Một build không nên phụ thuộc vào file hoặc công cụ chỉ tồn tại trên máy cá nhân mà không được tài liệu hóa. Nếu đầu vào là bắt buộc, pipeline cần kiểm tra và báo rõ khi thiếu. Nếu đầu vào có thể tạo tự động, build phải khai báo task hoặc bước tạo nó.

## 3. Checkout đúng source revision

CI phải biết chính xác source revision nào đang được build. Pipeline thường checkout commit gắn với push, pull request, tag hoặc release.

Trong log, nên ghi lại commit SHA:

~~~shell
git rev-parse HEAD
git status --short
~~~

Commit SHA giúp truy vết chính xác source. Tên branch không đủ để tái hiện lâu dài vì branch có thể di chuyển.

### Shallow checkout và lịch sử Git

Một số pipeline dùng shallow clone để giảm thời gian checkout. Điều này thường đủ cho compile/test, nhưng có thể gây lỗi nếu build script lấy version từ Git tag, đếm commit, đọc lịch sử hoặc dùng plugin versioning dựa trên SCM.

Nếu build cần tag hoặc lịch sử đầy đủ, cấu hình checkout depth phù hợp. Không nên giả định mọi CI checkout đều có toàn bộ Git history.

### Submodule và Git LFS

Nếu repository sử dụng Git submodule, pipeline cần khởi tạo và checkout đúng commit submodule. Nếu sử dụng Git LFS, runner cần tải nội dung file thực thay vì chỉ checkout pointer.

Một build có thể thất bại vì schema, binary hoặc tài nguyên được quản lý ngoài Git tree chính chưa được tải. Hãy ghi rõ các thành phần đó trong quy trình checkout.

### Pull request từ fork

Pipeline của pull request đến từ fork có thể không được cấp secret của repository gốc. Đây là chính sách bảo vệ thông tin xác thực. Nếu build cần dependency private hoặc ký artifact, hãy thiết kế job kiểm tra pull request không cần secret hoặc dùng một quy trình phê duyệt riêng cho tác vụ nhạy cảm.

Không nên cố vượt qua giới hạn secret của CI bằng cách ghi credential vào repository hoặc log.

## 4. Dùng Gradle Wrapper và Maven Wrapper

Build nên gọi wrapper được commit cùng repository thay vì dựa vào phiên bản build tool cài toàn cục trên runner.

Gradle:

~~~shell
./gradlew --version
./gradlew clean test
~~~

Windows:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test
~~~

Maven:

~~~shell
./mvnw --version
./mvnw --batch-mode clean verify
~~~

Windows:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd --batch-mode clean verify
~~~

Wrapper chọn phiên bản Gradle/Maven theo cấu hình của project. Nó không tự cố định JDK, plugin, dependency repository, biến môi trường hoặc các công cụ bên ngoài.

### Kiểm tra wrapper trong repository

Với Gradle, kiểm tra script wrapper, wrapper JAR và gradle-wrapper.properties. Trên Linux, script gradlew cần có executable bit và line ending phù hợp.

Với Maven, kiểm tra mvnw, mvnw.cmd và cấu hình trong .mvn/wrapper. Wrapper cần tải đúng distribution từ URL được khai báo.

Nếu runner không có mạng để tải wrapper distribution, bước bootstrap sẽ thất bại trước khi build bắt đầu. Trong môi trường hạn chế mạng, cần cấu hình mirror hoặc phân phối tool theo chính sách nội bộ.

### Ghi nhận phiên bản thực tế

Trong log CI, nên ghi:

~~~shell
java -version
./gradlew --version
~~~

Hoặc với Maven:

~~~shell
java -version
./mvnw --version
~~~

Những thông tin này giúp phân biệt lỗi do JDK với lỗi do build tool. Không nên chỉ ghi phiên bản Java mục tiêu trong POM/build script mà bỏ qua JDK thực tế chạy build.

## 5. Cung cấp JDK và toolchain đúng cách

Một runner sạch cần JDK phù hợp với build. Có thể cung cấp JDK qua runner image, setup action/task của CI hoặc toolchain resolver đã được cấu hình.

Cần phân biệt ba phiên bản:

1. JDK dùng để chạy Gradle/Maven.
2. JDK/compiler toolchain dùng để biên dịch mã nguồn.
3. Java runtime dùng để chạy artifact hoặc container image.

Các phiên bản này có thể khác nhau nếu dự án chủ động cấu hình. Chúng cần tương thích với plugin và bytecode/API mục tiêu.

### Gradle toolchain

Ví dụ:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Khai báo này yêu cầu Gradle dùng Java 21 cho các task Java được hỗ trợ. Runner cần có toolchain phù hợp hoặc có resolver được cấu hình để tải toolchain. Không nên giả định Gradle tự tải JDK trên mọi CI.

### Maven compiler release

Ví dụ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Release 17 xác định mức API và bytecode mục tiêu. Nó không tự cài JDK 17 lên runner. Máy chạy Maven vẫn cần JDK phù hợp với Maven, compiler plugin và toolchain đã cấu hình.

### Thiếu JDK phải được phát hiện sớm

Nếu build yêu cầu Java 21 nhưng runner chỉ có Java 17, pipeline nên dừng ở bước xác minh toolchain với thông báo rõ. Không nên để lỗi xuất hiện muộn dưới dạng lỗi compiler khó hiểu.

Có thể thêm bước kiểm tra version trước khi chạy build. Tuy nhiên, kiểm tra phải phù hợp với chính sách toolchain: nếu build dùng Gradle toolchain khác JDK của shell, hãy xác minh cả hai.

## 6. Dependency phải được phân giải từ repository đã khai báo

Máy local có thể đã tải dependency từ trước. Runner sạch cần lấy dependency từ repository mà project cấu hình.

Các nguồn phổ biến:

- Maven Central hoặc repository công khai khác.
- Maven/Gradle repository nội bộ.
- Repository proxy/cache do tổ chức quản lý.
- Artifact được publish bởi một pipeline trước.
- Dependency được tạo trong cùng multi-project build.

### Không cài dependency bằng tay trên runner

Nếu project cần một JAR nội bộ nhưng artifact đó chưa được publish, cài thủ công vào local repository của runner sẽ tạo một phụ thuộc ẩn. Job khác hoặc runner khác không có artifact đó sẽ thất bại.

Cách xử lý đúng thường là:

- Publish artifact vào repository nội bộ trước khi project tiêu thụ nó.
- Dùng project dependency nếu các module thuộc cùng build.
- Dùng composite build hoặc cơ chế build orchestration phù hợp.
- Khai báo repository và dependency rõ ràng.

### Maven local repository

Maven mặc định sử dụng local repository trong thư mục home, thường là ~/.m2/repository. Trên runner mới, repository có thể trống.

Có thể chạy Maven với repository riêng:

~~~shell
./mvnw -Dmaven.repo.local=/tmp/m2-ci clean verify
~~~

Đường dẫn ví dụ dành cho runner Linux. Với Windows, chọn thư mục tạm phù hợp. Local repository riêng hữu ích để kiểm tra cold dependency resolution và tránh phụ thuộc vào cache dùng chung.

### Gradle dependency cache

Gradle lưu dependency cache trong Gradle User Home. Có thể dùng một thư mục riêng trong CI để xác nhận dependency được tải lại:

~~~shell
GRADLE_USER_HOME=/tmp/gradle-ci-clean ./gradlew clean build
~~~

Trên PowerShell:

~~~powershell
$env:GRADLE_USER_HOME = Join-Path $env:TEMP 'gradle-ci-clean'
.\gradlew.bat clean build
~~~

Lần đầu chạy sẽ chậm hơn vì cần tải distribution, plugin và dependency. Điều này hữu ích khi kiểm tra khả năng build trên runner không có cache.

## 7. Cache CI: tăng tốc mà không che giấu đầu vào

Cache giúp giảm thời gian tải dependency và thực hiện build. Nhưng cache không nên trở thành điều kiện bí mật để build thành công.

Cần phân biệt:

- **Dependency cache:** lưu artifact và metadata đã tải.
- **Build cache:** lưu output task có thể tái sử dụng.
- **Workspace cache:** giữ file trong thư mục làm việc giữa các job.
- **Tool cache:** lưu JDK, Gradle, Maven hoặc công cụ đã cài.

### Cache key nên phản ánh đầu vào

Cache dependency nên được khóa theo các yếu tố có thể thay đổi nội dung cần tải, ví dụ:

- Hệ điều hành/kiến trúc khi cache chứa thành phần phụ thuộc nền tảng.
- Phiên bản Gradle/Maven Wrapper.
- Dependency lock files.
- Build scripts và repository configuration.
- JDK/toolchain khi nội dung cache phụ thuộc môi trường.

Không nên dùng một cache key quá chung khiến các branch hoặc cấu hình không tương thích dùng chung trạng thái.

### Cache miss phải vẫn build được

Một quy tắc hữu ích: nếu cache không có, pipeline vẫn phải có khả năng tải và tạo mọi đầu vào cần thiết từ các nguồn được khai báo.

Nếu cache bị xem như nơi duy nhất chứa một JAR nội bộ chưa publish, pipeline không còn độc lập. Hãy publish artifact đó hoặc tạo nó như một bước upstream có thể truy vết.

### Khi nào nên kiểm tra cold cache?

Không nhất thiết tắt cache trong mọi lần build. Có thể tạo một job định kỳ hoặc job release kiểm tra:

- Workspace mới.
- Dependency cache trống.
- Build cache không được dùng.
- Dependency tải từ repository được cấu hình.
- Artifact và test report được tạo đầy đủ.

Job cold-cache giúp phát hiện lỗi mà các build thường ngày có cache che giấu.

### Không xóa cache toàn cục tùy tiện

Trên self-hosted runner, xóa toàn bộ cache có thể ảnh hưởng job khác hoặc làm mất dữ liệu dùng chung. Dùng cache namespace riêng hoặc cache key mới để kiểm tra. Chỉ xóa cache theo chính sách quản trị runner.

## 8. Xử lý repository private và credentials

Một build có thể cần credential để tải dependency, truy cập plugin repository hoặc publish artifact. Runner mới thường không có thông tin xác thực từ máy lập trình viên.

Credentials nên được cung cấp qua CI secret store, workload identity hoặc cơ chế credential được tổ chức phê duyệt.

### Gradle

Có thể đọc credential từ environment hoặc Gradle properties được cấp ngoài repository. Ví dụ:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.com/maven')
        credentials {
            username = providers.environmentVariable('REPO_USER').orNull
            password = providers.environmentVariable('REPO_TOKEN').orNull
        }
    }
}
~~~

Ví dụ này minh họa cách lấy giá trị từ environment. Build thực tế cần xử lý trường hợp thiếu credential rõ ràng, và không được in giá trị secret vào log.

### Maven

Maven thường cấu hình server credentials trong settings.xml. Giá trị id phải khớp repository id mà POM hoặc profile sử dụng.

~~~xml
<settings>
    <servers>
        <server>
            <id>company-releases</id>
            <username>...</username>
            <password>...</password>
        </server>
    </servers>
</settings>
~~~

Dấu ba chấm là chỗ được điền bởi cơ chế secret của môi trường; không commit password thật vào repository. CI có thể tạo settings.xml tạm từ secret store hoặc dùng cơ chế cấu hình bảo mật của hệ thống quản lý artifact.

### Không đưa secret vào Docker layer hoặc log

Tránh:

- Ghi token trong build.gradle hoặc pom.xml.
- Truyền password như một argument có thể bị ghi vào log.
- Echo toàn bộ environment.
- Copy settings.xml có credential vào image.
- Để secret trong file artifact hoặc test report.

Nếu Docker build cần tải dependency private, dùng build secret mechanism của builder hoặc build artifact ở bước CI trước rồi copy artifact vào image. Secret chỉ nên tồn tại trong bước cần thiết và không trở thành một lớp image.

### Thiếu credential cần báo rõ

Thông báo lỗi nên nói credential nào cần được cấu hình và repository nào cần truy cập, nhưng không in giá trị credential. Ví dụ:

~~~text
Missing required CI secret REPO_TOKEN for repository company-releases.
Configure the secret in the CI project settings and rerun the job.
~~~

Thông báo này nêu tên secret và cách xử lý mà không tiết lộ nội dung.

## 9. Biến môi trường và cấu hình theo pipeline

Build có thể cần property để chọn profile, version, feature hoặc endpoint.

Ví dụ Gradle property:

~~~shell
./gradlew build -PreleaseVersion=2.4.0
~~~

Ví dụ Maven property:

~~~shell
./mvnw -Drevision=2.4.0 clean verify
~~~

Không nên để giá trị bắt buộc chỉ tồn tại trong terminal profile của một lập trình viên. Pipeline phải khai báo chúng rõ ràng.

### Giá trị bắt buộc và giá trị mặc định

Phân loại cấu hình:

| Loại | Ví dụ | Hành vi khi thiếu |
|---|---|---|
| Required | Repository token, schema input | Dừng sớm với thông báo rõ |
| Optional | Log verbosity, local report detail | Dùng default an toàn |
| Environment-specific | API endpoint, database host | Lấy từ cấu hình môi trường |
| Secret | Password, signing key | Lấy từ secret store, không ghi log |
| Derived | Version từ Git tag hoặc commit | Tạo tự động từ source metadata |

Đừng đặt default giả cho một giá trị bắt buộc. Ví dụ, nếu thiếu database URL mà build tự dùng localhost, test có thể vô tình kết nối vào dịch vụ không đúng hoặc thất bại với lỗi khó hiểu.

### Kiểm tra cấu hình trước khi dùng

Có thể thêm một bước validate trong build hoặc pipeline. Ví dụ Java:

~~~java
String repositoryToken = System.getenv("REPO_TOKEN");
if (repositoryToken == null || repositoryToken.isBlank()) {
    throw new IllegalStateException(
        "Missing required environment variable REPO_TOKEN"
    );
}
~~~

Đối với build script, dùng provider/API tương ứng và kiểm tra trước khi task cần giá trị đó thực thi. Không đọc secret quá sớm nếu cấu hình cache hoặc configuration cache có thể lưu giá trị nhạy cảm vào trạng thái build.

### Tránh log toàn bộ environment

Không chạy env, printenv hoặc Get-ChildItem Env: trong CI nếu output có thể chứa secret. Nếu cần chẩn đoán, chỉ in tên biến cần thiết và trạng thái đã được cấu hình hay chưa, không in giá trị.

## 10. Đầu vào được sinh tự động

Một build có thể cần source file được tạo từ:

- OpenAPI/Swagger schema.
- Protocol Buffers.
- Avro schema.
- Annotation processor.
- SQL migration metadata.
- Code generator riêng.
- Template hoặc file cấu hình được tạo từ pipeline.

Nếu máy phát triển đã chạy generator trước đó, file output có thể còn trong thư mục build. CI sạch không có file đó nên compiler báo thiếu class hoặc package.

### Khai báo task generator đúng cách

Với Gradle, task generator nên khai báo input và output, và task compile phải nhận output thông qua source set hoặc provider/task dependency.

Ví dụ khái niệm:

~~~groovy
def generatedDir = layout.buildDirectory.dir('generated/sources/schema')

tasks.register('generateSchemaSources') {
    inputs.dir(layout.projectDirectory.dir('src/schema'))
    outputs.dir(generatedDir)

    doLast {
        def output = generatedDir.get().asFile
        output.mkdirs()
        // Gọi generator và ghi source vào output
    }
}

sourceSets {
    main {
        java.srcDir(generatedDir)
    }
}

tasks.named('compileJava') {
    dependsOn tasks.named('generateSchemaSources')
}
~~~

Ví dụ minh họa cấu trúc dependency; trong build thực tế, nên dùng task type và provider output chuyên biệt thay vì chỉ tạo thư mục trong doLast. Generator cần được khai báo như tool/dependency có version xác định.

### Không dựa vào generated file còn sót

Nếu source generated là output của build, nó nên được tạo lại từ input đã quản lý. Nếu file generated được commit như source chính thức, phải có quy trình cập nhật và kiểm tra consistency. Đừng để cùng một file vừa được tạo thủ công vừa được generator ghi đè không có quy tắc.

### Maven generated sources

Maven plugin sinh source cần được gắn vào phase phù hợp trước compiler goal. Cấu hình plugin và version cần được commit. CI phải chạy lifecycle đủ xa để goal generator thực thi trước compile.

Nếu gọi trực tiếp một goal riêng thay vì lifecycle, các phase trước đó có thể không chạy. Hãy dùng lifecycle command chuẩn hoặc khai báo goal execution phù hợp.

## 11. Công cụ bên ngoài và native dependencies

Không phải mọi đầu vào đều là dependency Java. Build có thể gọi:

- Docker CLI hoặc container builder.
- Node.js/npm để build frontend.
- protoc hoặc compiler cho schema.
- C/C++ compiler cho JNI/native library.
- Git hoặc công cụ versioning.
- CLI để upload artifact hoặc ký release.

Máy lập trình viên có thể đã cài chúng, nhưng CI runner mới thì chưa.

Tài liệu build cần nêu:

- Tên công cụ.
- Version tối thiểu hoặc version được hỗ trợ.
- Cách cài đặt trên runner.
- Cách xác minh version.
- Task nào sử dụng công cụ.
- Có thể dùng container/tool image cố định hay không.

Ví dụ kiểm tra Docker:

~~~shell
docker version
docker build --version
~~~

Ví dụ kiểm tra Node:

~~~shell
node --version
npm --version
~~~

Nếu công cụ không bắt buộc cho mọi build, hãy tách task hoặc pipeline stage để unit test Java không thất bại chỉ vì một công cụ chỉ cần cho frontend release chưa được cài.

### Native dependency và kiến trúc

Một số JAR chứa native library hoặc tải binary theo OS/CPU. Runner Linux x86_64 có thể không dùng được binary được tạo cho Windows hoặc ARM64. Cần xác định platform classifier, ABI và architecture trong dependency graph.

Không nên dùng một artifact native duy nhất cho mọi môi trường nếu nhà cung cấp không hỗ trợ. Với native build, có thể cần ma trận CI theo OS và kiến trúc.

## 12. Dịch vụ ngoài cần cho integration test

Integration test có thể cần database, message broker, cache, HTTP mock server hoặc service khác. Máy local có thể đã chạy Docker Compose hoặc dịch vụ dùng chung; CI sạch không có chúng.

Có ba cách phổ biến:

1. Dùng service container do CI cung cấp.
2. Khởi chạy dependency bằng Docker Compose hoặc Testcontainers trong job.
3. Kết nối đến môi trường test được quản lý riêng.

### Service container

Một pipeline có thể khởi động PostgreSQL hoặc Redis làm service cho job. Cần xác định hostname, port, database name, username và password mà test sử dụng.

Không nên giả định service đã sẵn sàng ngay sau khi container process được tạo. Cần health check hoặc bước readiness polling trước khi chạy test.

### Testcontainers

Testcontainers có thể tạo container dependency trong lúc test. Runner cần hỗ trợ Docker hoặc container runtime tương thích, quyền truy cập daemon và network phù hợp. Nếu CI chạy trong container, cấu hình Docker socket hoặc remote daemon cần được quản lý rõ ràng.

### Chờ service sẵn sàng

Một cách đơn giản là retry kết nối trong khoảng thời gian giới hạn. Không dùng sleep cố định quá ngắn rồi giả định service đã sẵn sàng. Hãy kiểm tra health/readiness và đặt timeout rõ ràng.

~~~text
deadline = current time + 60 seconds
repeat:
    try connect to database
    if connection succeeds:
        continue build
    wait briefly
until deadline
fail with clear service/host diagnostic
~~~

Nếu timeout, báo hostname/service và trạng thái kiểm tra, không in credential.

### Dữ liệu test

CI job nên tạo dữ liệu test có thể tái lập và dọn dẹp sau khi hoàn tất. Tránh dùng chung database/schema giữa các job chạy song song nếu test có thể xóa hoặc sửa dữ liệu của nhau.

## 13. Network, proxy và repository availability

Build sạch thường cần tải wrapper distribution, plugin và dependency. Vì vậy, network là một đầu vào của build.

Lỗi có thể do:

- DNS không phân giải được repository host.
- Proxy chưa được cấu hình.
- TLS certificate hoặc CA trust thiếu.
- Repository private không truy cập được từ runner.
- Rate limit hoặc repository outage.
- Firewall/network policy chặn kết nối.
- Timeout quá ngắn hoặc artifact lớn.
- Repository metadata không nhất quán.

### Phân biệt lỗi mạng với lỗi dependency

Nếu log nói artifact không tồn tại, có thể tọa độ dependency sai hoặc repository không chứa artifact. Nếu log cho biết timeout, DNS hoặc TLS handshake, vấn đề có thể nằm ở network/credential/certificate.

Đừng thay version dependency chỉ vì một lần tải bị timeout. Hãy xác định lỗi đầu tiên trong log và thử xác nhận repository availability theo chính sách của tổ chức.

### Retry có giới hạn

Retry có thể xử lý lỗi mạng tạm thời, nhưng không nên retry vô hạn hoặc che giấu lỗi xác thực/404. Chỉ retry những lỗi có thể phục hồi, đặt số lần và khoảng chờ giới hạn, rồi kết thúc với thông báo rõ.

### Proxy và certificate

Runner trong mạng doanh nghiệp có thể cần proxy và CA certificate riêng. Cấu hình proxy nên được cấp qua môi trường CI. Không tắt TLS verification để “sửa nhanh” lỗi chứng chỉ; hãy cài trust chain đúng cách hoặc cấu hình mirror được tổ chức quản lý.

## 14. Path, working directory và quyền file

Một build chạy local có thể dựa vào current working directory, trong khi CI gọi command từ thư mục khác.

Trong Gradle, dùng Project Layout API hoặc project directory cho file thuộc project. Trong Maven, dùng basedir/build directory property tương ứng. Khi task gọi process bên ngoài, đặt working directory tường minh nếu command dùng relative path.

### Đường dẫn và khoảng trắng

Workspace CI có thể nằm trong path có khoảng trắng hoặc ký tự đặc biệt. Shell script phải quote biến path đúng cách. Tránh tự ghép dấu phân cách Windows/Linux; dùng API file/path của Java hoặc build tool.

### Quyền thực thi

Trên Linux, wrapper hoặc script cần executable bit. Một lỗi thường gặp là file script chạy được trên Windows nhưng CI Linux báo permission denied. Kiểm tra mode trong Git và line ending.

### Case sensitivity

Linux thường phân biệt chữ hoa/chữ thường trong tên file. Import Java hoặc resource path sai casing có thể chạy trên máy Windows nhưng thất bại trên runner Linux. Hãy dùng đúng tên file trong repository.

### File tạm và thư mục home

Không ghi đầu ra bắt buộc vào thư mục home của runner nếu file đó không được lưu hoặc truyền sang job khác. Dùng workspace hoặc thư mục tạm được xác định rõ. Nếu nhiều job cần cùng một file, publish nó thành artifact hoặc truyền qua cơ chế output của CI.

## 15. Thiết kế bước validate đầu vào

Một pipeline tốt kiểm tra đầu vào bắt buộc trước khi chạy công việc tốn thời gian.

Ví dụ shell kiểm tra biến môi trường và file cấu hình:

~~~shell
set -eu

if [ -z "$REPO_TOKEN" ]; then
  echo "Missing required secret REPO_TOKEN"
  exit 1
fi

if [ ! -f config/build-settings.yml ]; then
  echo "Missing required file: config/build-settings.yml"
  exit 1
fi

java -version
./gradlew --version
~~~

Cú pháp trên là ví dụ cho shell POSIX. Với PowerShell hoặc CI YAML, dùng cú pháp kiểm tra tương ứng.

Không in giá trị của REPO_TOKEN. Kiểm tra biến có tồn tại là đủ cho bước prerequisite; repository authentication vẫn cần được kiểm tra ở bước resolve dependency.

### Validate theo từng nhóm

Có thể chia validation thành các bước:

1. Source revision và working tree.
2. JDK/build wrapper.
3. Dependency repository và credentials.
4. Required files/configuration.
5. External tools.
6. External services.
7. Output directories và permissions.

Khi một bước thất bại, thông báo nên nói rõ nhóm đầu vào, cách cung cấp và nơi xem log. Không nên trả một lỗi chung như “Build failed” khi có thể xác định thiếu JDK hoặc secret.

### Fail fast nhưng không kiểm tra thừa

Chỉ kiểm tra những điều kiện thật sự cần cho pipeline hoặc stage hiện tại. Ví dụ unit test không cần database production, vì vậy không nên bắt buộc production DB credentials trong job unit test. Integration test mới cần service test tương ứng.

Chia pipeline thành stage giúp mỗi job có tập đầu vào nhỏ và quyền truy cập tối thiểu.

## 16. Pipeline nên tách build, test và publish

Một pipeline có thể tổ chức thành các giai đoạn:

~~~text
Checkout
   |
   v
Validate toolchain and inputs
   |
   v
Compile
   |
   v
Unit tests
   |
   v
Package JAR/WAR
   |
   v
Integration tests
   |
   v
Archive reports and artifacts
   |
   v
Publish artifact / build image
~~~

Không phải dự án nào cũng cần các stage riêng. Nhưng tách stage có lợi khi chúng có đầu vào, quyền hoặc tài nguyên khác nhau.

Ví dụ:

- Compile/unit test có thể không cần secret.
- Integration test cần database test.
- Publish cần credential ghi vào artifact repository.
- Deploy cần quyền triển khai và secret môi trường.
- Image scan cần image artifact và scanner.

Không cấp toàn bộ secret cho mọi job. Hãy chỉ cấp quyền ở stage cần thiết.

### Chuyển artifact giữa các job

Nếu build JAR ở job A và tạo image ở job B, job B cần nhận đúng JAR từ job A qua artifact storage hoặc cơ chế truyền file của CI. Không nên giả định workspace giữa hai job giống nhau.

Khi tải artifact, xác nhận version, tên file và checksum. Đừng build lại cùng source trong job B nếu mục tiêu là đóng gói chính artifact đã được test ở job A.

## 17. Lưu test report và artifact ngay cả khi build thất bại

Một pipeline thất bại vẫn cần giữ bằng chứng để điều tra.

Các output thường cần lưu:

- Gradle test report và test result XML.
- Maven Surefire/Failsafe reports.
- JAR/WAR nếu package đã hoàn thành.
- Build log.
- Dependency tree hoặc lock state khi cần.
- Checksum và metadata source revision.
- Container image scan report.

Cấu hình CI nên cho phép upload report trong bước luôn chạy hoặc trong nhánh xử lý failure. Nếu chỉ upload artifact khi job thành công, test report có thể bị mất đúng lúc cần nhất.

Không phải mọi file output đều nên lưu lâu dài. Chọn retention phù hợp và tránh upload file chứa secret, dữ liệu test nhạy cảm hoặc thông tin cá nhân.

## 18. Build trên runner sạch nhưng vẫn dùng cache an toàn

Một mô hình thực tế là workspace sạch, wrapper/toolchain được kiểm soát và dependency cache có thể được phục hồi. Điều đó giữ tốc độ mà vẫn tránh phụ thuộc vào output cũ của project.

Để xác nhận build không phụ thuộc cache:

1. Chạy một job với cache lạnh theo lịch.
2. Chạy build từ source checkout mới.
3. Dùng wrapper đã commit.
4. Tải dependency từ repository được khai báo.
5. Chạy test và tạo artifact.
6. So sánh dependency graph và kết quả với job có cache.

Nếu job cold-cache thất bại vì thiếu artifact nội bộ, hãy publish artifact upstream hoặc sửa dependency declaration. Không nên xử lý bằng cách cố giữ một cache không rõ nguồn gốc.

## 19. Chẩn đoán lỗi chỉ xuất hiện trên CI

Bắt đầu từ bước đầu tiên thất bại, không chỉ đọc dòng “BUILD FAILED” cuối cùng.

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Wrapper không tải được | Network, proxy, distribution URL hoặc certificate | Kiểm tra wrapper properties, DNS, TLS và quyền truy cập |
| Java version không đúng | Runner image hoặc JAVA_HOME sai | In java -version và wrapper version |
| Dependency không tìm thấy | Repository thiếu artifact hoặc tọa độ sai | Xem dependency declaration và repository |
| Unauthorized khi tải dependency | Secret/server credentials thiếu hoặc sai | Kiểm tra secret presence và repository id, không in secret |
| Generated class không tồn tại | Generator chưa chạy hoặc output chưa được nối vào compile | Kiểm tra task graph, source set và task dependency |
| File cấu hình không tồn tại | File local chưa commit hoặc chưa được cấp từ pipeline | Kiểm tra source tree và required-input validation |
| Permission denied | Script thiếu executable bit hoặc quyền thư mục | Kiểm tra file mode và runner user |
| Test timeout | Service chưa sẵn sàng, tài nguyên thấp hoặc timeout quá ngắn | Kiểm tra health check, log và resource usage |
| Chỉ lỗi trên Linux | Case sensitivity, line ending, shell hoặc native dependency | Kiểm tra tên file, script và architecture |
| Artifact không được tạo | Task/phase chưa chạy hoặc output path khác | Kiểm tra command, task/goal và output directory |
| Job sau không thấy artifact | Workspace không được chia sẻ giữa jobs | Upload/download artifact tường minh |
| Build chỉ thành công khi có cache | Dependency hoặc generated output chưa được quản lý | Chạy cold-cache và xác định đầu vào thiếu |
| Container không khởi động | Image thiếu runtime, command hoặc cấu hình | Kiểm tra image, entrypoint, environment và logs |

### Đọc log theo thứ tự

Một lỗi cuối như compilation failed có thể là hệ quả của dependency resolution hoặc generated source thất bại trước đó. Hãy tìm lỗi đầu tiên có nguyên nhân rõ, xem task/goal nào đang chạy và đầu vào nào nó cần.

Nếu log bị cắt, lưu log đầy đủ thành artifact hoặc tăng giới hạn output của CI theo chính sách. Không đưa credential vào log khi bật debug.

## 20. Ví dụ pipeline shell tổng quát

Ví dụ dưới đây minh họa các bước cốt lõi trên Linux runner. Cú pháp CI YAML cụ thể sẽ khác giữa các hệ thống, nhưng thứ tự công việc có thể giữ nguyên.

~~~shell
set -eu

echo "Source revision:"
git rev-parse HEAD

echo "Java toolchain:"
java -version

echo "Build wrapper:"
./gradlew --version

if [ -z "$REPO_TOKEN" ]; then
  echo "Missing required CI secret REPO_TOKEN"
  exit 1
fi

if [ ! -f config/build-settings.yml ]; then
  echo "Missing required file config/build-settings.yml"
  exit 1
fi

./gradlew --no-daemon clean test jar

mkdir -p ci-output
cp build/libs/*.jar ci-output/
sha256sum ci-output/*.jar > ci-output/SHA256SUMS
~~~

Ví dụ này giả định project có file cấu hình được commit, repository private cần REPO_TOKEN và JAR được tạo trong build/libs. Nếu project không có các yêu cầu đó, bỏ bước tương ứng. Pipeline thật cần cấp secret cho bước resolve dependency và lưu test report/artifact bằng cơ chế của CI.

### Maven tương đương

~~~shell
set -eu

git rev-parse HEAD
java -version
./mvnw --version

if [ -z "$REPO_TOKEN" ]; then
  echo "Missing required CI secret REPO_TOKEN"
  exit 1
fi

./mvnw --batch-mode clean verify

mkdir -p ci-output
cp target/*.jar ci-output/
sha256sum ci-output/*.jar > ci-output/SHA256SUMS
~~~

Ví dụ Maven cũng chỉ mang tính minh họa. Nếu project tạo WAR, nhiều artifact hoặc output ở module con, cần điều chỉnh đường dẫn. Nếu token được Maven settings.xml sử dụng, pipeline phải tạo/cấp settings theo cơ chế secret an toàn trước khi chạy wrapper.

## 21. Tránh những cách xử lý đầu vào thiếu gây lỗi về sau

Khi build thất bại vì thiếu đầu vào, có một số cách sửa tưởng nhanh nhưng làm pipeline kém tin cậy:

- Commit password hoặc token để runner có thể truy cập repository.
- Tạo file cấu hình giả với giá trị production hoặc giá trị không hợp lệ.
- Tắt test để pipeline chuyển xanh.
- Dùng dependency version động nhằm né lỗi artifact không tồn tại.
- Dựa vào cache của self-hosted runner mà không quản lý.
- Cài thủ công JAR vào local repository trên runner.
- Tắt TLS verification khi repository certificate lỗi.
- Bỏ qua generated source hoặc dùng file output cũ.
- Cho mọi job quyền truy cập tất cả secrets.
- Retry vô hạn khi dependency repository không tồn tại hoặc credential sai.

Cách xử lý đúng là xác định đầu vào thuộc loại nào, ai sở hữu nó, nguồn cung cấp được kiểm soát ra sao và job nào thực sự cần nó. Nếu đầu vào không thể được cung cấp trong môi trường hiện tại, pipeline nên dừng với thông báo rõ ràng.

## 22. Thiết kế build để tự mô tả yêu cầu

Một project dễ build trên CI nên có tài liệu và build logic thể hiện:

- JDK/toolchain version.
- Gradle/Maven Wrapper version.
- Dependency repository và cách xác thực.
- Required environment variables và file cấu hình.
- External tools/services cần thiết.
- Lệnh build/test/package chuẩn.
- Vị trí artifact và test reports.
- Cách tạo generated sources.
- Cách chạy cold-cache build.
- Các khác biệt theo OS/architecture.

Build script cũng cần khai báo input/output của task, tránh dựa vào current directory, file home cá nhân hoặc trạng thái không được quản lý.

### Thông báo lỗi có thể hành động được

Thông báo tốt trả lời ba câu hỏi:

1. Đầu vào nào đang thiếu?
2. Đầu vào đó được cung cấp ở đâu?
3. Sau khi cung cấp, cần chạy lại bước nào?

Ví dụ:

~~~text
Missing required environment variable ARTIFACT_REPO_TOKEN.
Add this secret to the CI environment for the dependency-resolution job.
The value is intentionally not printed.
~~~

Thông báo không chứa secret và chỉ rõ nơi cấu hình. Đây là cách giúp người vận hành xử lý nhanh mà không cần đọc toàn bộ build script.

## 23. Checklist cho một Java build trên CI sạch

### Source và checkout

- [ ] Pipeline checkout đúng commit SHA.
- [ ] Submodule/LFS được tải nếu project sử dụng.
- [ ] Không phụ thuộc file local chưa được quản lý.
- [ ] Working directory và source revision được ghi nhận.

### Toolchain

- [ ] JDK phù hợp được cài hoặc chọn.
- [ ] Gradle/Maven Wrapper có trong repository và chạy được.
- [ ] Toolchain compiler/runtime được xác định.
- [ ] Công cụ ngoài có version được ghi nhận.

### Dependency và cấu hình

- [ ] Dependency được khai báo và tải từ repository xác định.
- [ ] Repository private có credentials được cấp an toàn.
- [ ] Không phụ thuộc artifact cài thủ công vào local repository.
- [ ] Required environment variables được validate.
- [ ] File cấu hình bắt buộc có nguồn cung cấp rõ ràng.
- [ ] Secret không bị in log hoặc đóng gói vào artifact/image.

### Test và dịch vụ

- [ ] Unit test chạy trong job phù hợp.
- [ ] Integration service được khởi tạo và readiness được kiểm tra.
- [ ] Test data được cô lập giữa các job chạy song song.
- [ ] Timeout và retry có giới hạn.
- [ ] Test reports được lưu khi build thất bại.

### Output và truy vết

- [ ] Artifact được tạo ở đúng vị trí.
- [ ] Artifact được liên hệ với commit/version.
- [ ] Checksum hoặc metadata được lưu khi cần.
- [ ] Job downstream tải artifact tường minh.
- [ ] Cold-cache build có thể hoàn tất.
- [ ] Log không chứa thông tin nhạy cảm.

## 24. Bài thực hành

Thực hành trên một dự án Java dùng Gradle hoặc Maven:

1. Xác định commit SHA và chạy build local bằng wrapper.
2. Tạo một CI job với workspace mới và checkout cùng commit.
3. Chọn JDK đúng yêu cầu, ghi lại java version và wrapper version.
4. Chạy build với dependency cache riêng hoặc cache lạnh.
5. Xác nhận mọi dependency được tải từ repository đã khai báo.
6. Tạm bỏ một biến môi trường bắt buộc trong môi trường thử nghiệm và quan sát thông báo lỗi.
7. Cấp biến đó qua secret store, chạy lại và xác nhận giá trị không xuất hiện trong log.
8. Tạo một file cấu hình local chưa được commit, xác định vì sao CI không có file đó và quyết định nên commit file mẫu hay tạo file từ pipeline.
9. Nếu project có generator, xác nhận task tạo source được nối vào compile graph.
10. Nếu project có integration test, khởi chạy service dependency và kiểm tra readiness trước khi chạy test.
11. Lưu test report, JAR/WAR và checksum thành artifact của job.
12. Tạo một job downstream tải artifact và kiểm tra checksum thay vì tự build lại.
13. Chạy một lần cold-cache định kỳ và ghi lại các bước còn phụ thuộc vào môi trường.
14. Cập nhật README/onboarding để một thành viên mới có thể tái hiện quy trình.

Sau bài thực hành, bạn cần phân biệt được workspace sạch với cache lạnh, biết wrapper kiểm soát phần nào của toolchain, xác định nguồn cung cấp dependency/secret/configuration, và chẩn đoán lỗi thiếu đầu vào theo đúng giai đoạn. Bạn cũng cần tổ chức được pipeline mà mỗi job chỉ nhận những đầu vào và quyền truy cập cần thiết.

## 25. Tiêu chí hoàn tất một lần build trên CI sạch

Một lần build có thể được xem là hoàn tất khi:

1. Source revision được xác định và checkout đúng.
2. Runner đáp ứng yêu cầu JDK, build wrapper và công cụ ngoài.
3. Required inputs được cung cấp từ nguồn đã quản lý.
4. Dependency được phân giải từ repository được khai báo.
5. Không có file local hoặc cache không rõ nguồn gốc là điều kiện bắt buộc để build thành công.
6. Build và các test bắt buộc hoàn tất.
7. Artifact và report được tạo, lưu và truy vết.
8. Secret không bị lộ trong log hoặc output.
9. Job downstream nhận đúng artifact đã được tạo.
10. Những đầu vào thiếu hoặc bước thủ công còn lại được tài liệu hóa.

Nếu build thất bại, hãy ghi lại commit, runner image/OS, JDK, wrapper version, command, bước đầu tiên thất bại và đầu vào còn thiếu. Một lỗi CI được mô tả rõ là thông tin hữu ích để cải thiện build. Mục tiêu là để pipeline có thể tạo lại kết quả từ source và các đầu vào đã công bố, không cần dựa vào trạng thái riêng trên máy của một lập trình viên.

