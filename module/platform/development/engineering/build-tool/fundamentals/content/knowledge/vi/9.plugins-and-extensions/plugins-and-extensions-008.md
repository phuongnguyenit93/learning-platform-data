# Ranh giới giữa logic build, script tiện ích và nghiệp vụ ứng dụng

Một repository Java thường chứa nhiều loại mã phục vụ những thời điểm và mục đích khác nhau. Có mã cấu hình cách project được biên dịch và đóng gói; có script hỗ trợ lập trình viên hoặc CI thực hiện các thao tác lặp lại; và có mã xử lý nghiệp vụ khi ứng dụng chạy. Ba nhóm này có thể cùng xuất hiện trong một repository, nhưng chúng có vòng đời, môi trường thực thi, người sử dụng và yêu cầu kiểm thử khác nhau.

Phân biệt đúng ranh giới giúp tránh việc build script trở thành một ứng dụng thứ hai, tránh nhúng nghiệp vụ vào plugin Gradle, đồng thời giúp các công cụ tự động hóa có thể tái sử dụng mà không làm ứng dụng phụ thuộc vào môi trường build.

## 1. Ba nhóm logic phục vụ ba mục đích khác nhau

Có thể bắt đầu bằng câu hỏi: **đoạn mã này tồn tại để tạo ra phần mềm, hỗ trợ người phát triển, hay thực hiện chức năng của phần mềm?**

| Nhóm | Mục tiêu chính | Thời điểm chạy | Người hoặc hệ thống sử dụng |
|---|---|---|---|
| Logic build | Cấu hình và điều phối quá trình tạo, kiểm tra, đóng gói sản phẩm | Khi Gradle cấu hình hoặc thực thi build | Gradle, plugin, task và CI |
| Script tiện ích | Hỗ trợ thao tác phát triển, quản trị repository hoặc điều phối công cụ | Khi người dùng hoặc pipeline gọi script | Lập trình viên, maintainer, CI |
| Nghiệp vụ ứng dụng | Thực hiện quy tắc và chức năng mà sản phẩm cung cấp | Khi ứng dụng hoặc dịch vụ chạy | Người dùng, API client, hệ thống nghiệp vụ |

Ba nhóm có thể phối hợp với nhau theo một luồng:

~~~text
Lập trình viên / CI
        |
        +----------------------+
        |                      |
        v                      v
Script tiện ích           Gradle Wrapper
        |                      |
        |                      v
        |                Logic build
        |                - plugins
        |                - tasks
        |                - dependencies
        |                - packaging
        |                      |
        +----------------------+
                               |
                               v
                         Application artifact
                               |
                               v
                         Ứng dụng chạy
                               |
                               v
                      Nghiệp vụ ứng dụng
~~~

Script tiện ích có thể gọi Gradle; Gradle tạo artifact; artifact được triển khai và thực thi nghiệp vụ. Quan hệ đó không có nghĩa ba nhóm phải được viết trong cùng một ngôn ngữ, cùng module hoặc cùng tiến trình.

### Logic build trả lời câu hỏi về việc tạo phần mềm

Ví dụ:

- Project cần plugin nào?
- Dùng JDK/toolchain nào để biên dịch?
- Dependency nào cần có trên compile classpath hoặc runtime classpath?
- Task nào chạy trước task nào?
- Làm sao tạo JAR, WAR, ZIP hoặc tài liệu?
- Điều kiện nào khiến task được chạy lại hoặc lấy output từ cache?
- Làm sao xác thực cấu trúc, chất lượng hoặc artifact trước khi publish?

Những câu hỏi này thuộc build system vì chúng mô tả cách tạo và kiểm tra sản phẩm.

### Script tiện ích trả lời câu hỏi về thao tác xung quanh repository

Ví dụ:

- Làm sao kiểm tra máy đã cài đúng công cụ trước khi chạy build?
- Làm sao chuẩn bị thư mục làm việc hoặc tạo dữ liệu mẫu?
- Làm sao gọi nhiều lệnh theo một trình tự của CI?
- Làm sao đóng gói, đổi tên hoặc thu thập artifact sau một thao tác?
- Làm sao hỗ trợ maintainer thực hiện một tác vụ quản trị repository?

Script tiện ích có thể gọi Gradle, Git, Docker hoặc công cụ khác. Nó là lớp điều phối bên ngoài, thường không cần trở thành một phần của ứng dụng.

### Nghiệp vụ ứng dụng trả lời câu hỏi về hành vi sản phẩm

Ví dụ:

- Khách hàng có được áp dụng mức giảm giá hay không?
- Đơn hàng chuyển sang trạng thái nào sau khi thanh toán?
- Người dùng có quyền truy cập tài nguyên nào?
- Cách tính phí, hạn mức hoặc điểm thưởng là gì?
- API cần trả về kết quả nào khi một điều kiện nghiệp vụ xảy ra?

Những quy tắc này thuộc ứng dụng vì chúng quyết định hành vi của sản phẩm khi chạy. Chúng cần được kiểm thử bằng test nghiệp vụ và có thể được gọi từ nhiều giao diện hoặc adapter khác nhau.

## 2. Logic build gồm những gì?

Trong Gradle, logic build thường xuất hiện ở các lớp sau:

- **Settings script**: xác định cấu trúc build, project tham gia và included build.
- **Build script**: áp dụng plugin, cấu hình dependency, task và các quy ước của project.
- **Plugin**: đóng gói khả năng hoặc quy ước để áp dụng cho một hay nhiều project.
- **Task type**: mô tả một loại công việc có input, output và action.
- **Task configuration**: chọn giá trị cụ thể cho task trong project.
- **Build convention**: thiết lập thống nhất như Java toolchain, test, compiler options hoặc quy tắc đóng gói.

Ví dụ, một project Java có thể cấu hình:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đoạn này xác định cách build biên dịch và kiểm thử project. Nó không định nghĩa cách ứng dụng tính giá sản phẩm hoặc xử lý đơn hàng.

Một task có thể tạo dữ liệu được ứng dụng sử dụng, chẳng hạn sinh mã nguồn, copy resource hoặc tạo file metadata. Đây vẫn là logic build nếu công việc đó phục vụ quá trình tạo artifact và được thực hiện trước hoặc trong build. Cần phân biệt **dữ liệu được tạo lúc build** với **quy tắc nghiệp vụ được thực thi lúc ứng dụng chạy**.

### Build script là nơi cấu hình, không phải nơi chứa mọi thuật toán

Một build script có thể dùng biểu thức và logic điều kiện để chọn cấu hình. Tuy nhiên, khi script ngày càng chứa nhiều hàm xử lý, truy cập mạng, thao tác file tùy ý hoặc quy tắc khó kiểm thử, nó trở nên khó bảo trì.

Ví dụ, đoạn cấu hình sau phù hợp với vai trò của build script:

~~~groovy
tasks.named('test') {
    maxParallelForks = 2
}
~~~

Ngược lại, việc đặt toàn bộ thuật toán phân tích dữ liệu, gọi nhiều dịch vụ từ xa và xử lý hàng nghìn bản ghi trực tiếp trong build.gradle khiến cấu hình project trở thành một chương trình lớn. Khi công việc đó là một phần của build, nên đóng gói nó thành task type hoặc plugin; nếu nó chỉ điều phối công cụ ngoài repository, cân nhắc script tiện ích.

### Phân biệt configuration phase và task execution

Gradle đánh giá settings/build script để cấu hình project và chuẩn bị task graph. Sau đó, các task action mới thực thi. Vì vậy:

- Khai báo plugin, dependency và task thuộc logic cấu hình build.
- Khai báo input/output và điều kiện task thuộc cấu hình task.
- Đọc input, xử lý và ghi output thuộc task action.
- Thao tác không liên quan đến task nhưng đặt trực tiếp ở cấp build script có thể chạy trong configuration phase, kể cả khi task liên quan không được chọn.

Ví dụ, đọc file hoặc gọi một process trực tiếp trong lúc cấu hình có thể khiến mọi lệnh Gradle đều phải thực hiện thao tác đó. Nếu công việc chỉ cần chạy khi một task được yêu cầu, hãy đặt nó trong task action và khai báo input/output phù hợp.

## 3. Script tiện ích là lớp hỗ trợ bên ngoài

Script tiện ích thường là shell script, PowerShell script, Python script hoặc một chương trình nhỏ phục vụ người phát triển và CI. Nó có thể điều phối nhiều công cụ mà không cần đưa tất cả vào Gradle.

Ví dụ, một script kiểm tra môi trường trước khi build:

~~~powershell
$ErrorActionPreference = 'Stop'

if (-not $env:JAVA_HOME) {
    throw 'JAVA_HOME is not configured.'
}

$javaCommand = Get-Command java -ErrorAction SilentlyContinue
if (-not $javaCommand) {
    throw 'Java executable was not found on PATH.'
}

java -version
.\gradlew.bat --version
.\gradlew.bat build
~~~

Script này kiểm tra một điều kiện môi trường cơ bản, hiển thị Java/Gradle version rồi gọi build. Nó không nên chứa logic tính giá đơn hàng hoặc kiểm tra quyền truy cập của người dùng trong sản phẩm.

Script tiện ích có thể phù hợp khi:

- Công việc phụ thuộc vào shell hoặc công cụ của hệ điều hành.
- Cần điều phối nhiều repository hoặc nhiều công cụ độc lập.
- Công việc phục vụ thao tác maintainer, bootstrap hoặc CI.
- Không cần Gradle quản lý từng bước như một task có input/output.
- Công việc đơn giản và không có nhu cầu tái sử dụng như một khả năng build.

Tuy nhiên, nếu script thực hiện một công việc cốt lõi của build, cần cân nhắc đưa công việc đó vào Gradle task. Khi task là một phần của graph, Gradle có thể hiểu dependency, thứ tự, input/output, trạng thái up-to-date và build cache.

### Script tiện ích và Gradle task có thể gọi lẫn nhau

Một script có thể gọi Gradle:

~~~shell
./gradlew clean build
~~~

Một Gradle task cũng có thể gọi công cụ ngoài qua API như Exec, nếu công cụ đó là một phần có chủ đích của công việc build. Điểm quyết định không phải là ngôn ngữ được sử dụng mà là **ai sở hữu công việc và cần quản lý nó ở cấp nào**.

Nếu pipeline cần nhìn thấy công việc như một node trong task graph, cần dependency rõ ràng và output được quản lý, Gradle task thường là lựa chọn phù hợp. Nếu chỉ cần chuẩn bị môi trường, chọn runner, checkout repository hoặc gọi nhiều hệ thống ngoài, script hoặc workflow CI có thể là lớp điều phối thích hợp.

### Script không tự động có tính di động

Một script tiện ích có thể phụ thuộc vào:

- Shell cụ thể, ví dụ Bash hoặc PowerShell.
- Lệnh được cài trên máy, ví dụ git, docker, curl hoặc tar.
- Quyền thực thi, quyền ghi thư mục và current working directory.
- Biến môi trường, proxy, credential và cấu hình mạng.
- Cách xử lý đường dẫn, dấu phân cách, encoding và line ending.

Nếu repository hỗ trợ nhiều hệ điều hành, cần xác định rõ script hỗ trợ shell nào và cung cấp cách gọi tương ứng. Không nên giả định một file .sh có thể chạy trực tiếp trong PowerShell hoặc mọi runner đều cài sẵn cùng công cụ.

## 4. Nghiệp vụ ứng dụng thuộc mã nguồn runtime

Mã nghiệp vụ thường nằm trong source set của ứng dụng hoặc thư viện, ví dụ:

~~~text
src/
  main/
    java/
      com/example/orders/
        domain/
        application/
        infrastructure/
        web/
    resources/
  test/
    java/
~~~

Tên package và cách chia tầng phụ thuộc kiến trúc ứng dụng. Điều quan trọng là nghiệp vụ nằm trong thành phần được biên dịch thành ứng dụng/thư viện và được thực thi khi runtime cần xử lý yêu cầu.

Ví dụ, một dịch vụ tính giá:

~~~java
public final class PriceCalculator {
    public Money calculate(Order order, Customer customer) {
        if (customer.isEligibleForDiscount()) {
            return order.total().multiply(0.9);
        }
        return order.total();
    }
}
~~~

Đây là ví dụ khái niệm; kiểu Money, Order và Customer được giả định là các kiểu của ứng dụng. Quy tắc áp dụng giảm giá là nghiệp vụ vì nó quyết định kết quả của sản phẩm khi xử lý một đơn hàng.

Nếu đặt quy tắc này trong Gradle plugin, ứng dụng sẽ phải phụ thuộc vào build tooling để thực hiện một hành vi vốn cần chạy trong production. Điều đó làm sai chiều phụ thuộc và khiến nghiệp vụ khó dùng ngoài build.

### Dấu hiệu nhận biết logic thuộc ứng dụng

Một đoạn logic thường thuộc runtime nếu:

- Nó quyết định kết quả nghiệp vụ mà người dùng/API nhận được.
- Nó cần dữ liệu giao dịch, người dùng, đơn hàng hoặc trạng thái miền nghiệp vụ.
- Nó cần chạy khi có request, message, schedule hoặc event của ứng dụng.
- Nó cần được triển khai cùng ứng dụng và có vòng đời theo phiên bản ứng dụng.
- Nó cần được kiểm thử độc lập với Gradle hoặc CI.
- Nó có thể được gọi từ nhiều adapter, chẳng hạn REST API, message consumer hoặc batch endpoint.

Build có thể biên dịch và kiểm tra mã nghiệp vụ, nhưng không nên sở hữu chính sách nghiệp vụ đó.

## 5. Ranh giới phụ thuộc và classpath

Một cách kiểm tra ranh giới là xem thành phần nào phải phụ thuộc vào thành phần nào.

~~~text
              Build system
       (Gradle scripts / plugins)
                  |
                  | builds
                  v
          Application artifact
                  |
                  v
          Application runtime
       (domain / use cases / adapters)

Utility scripts ---> invoke Gradle / Git / Docker / CI tools
~~~

Build system có thể đọc metadata của project, cấu hình dependency và tạo artifact. Ứng dụng không nên cần Gradle API để xử lý nghiệp vụ lúc chạy.

Ví dụ về các nhóm dependency:

| Dependency | Nơi thường dùng | Lý do |
|---|---|---|
| Gradle API | Plugin hoặc build logic | Đăng ký/cấu hình task, truy cập build model |
| Gradle TestKit | Kiểm thử plugin/task | Chạy build mẫu và quan sát hành vi |
| Java/Jakarta/Spring API | Mã nguồn ứng dụng | Xây dựng chức năng runtime |
| JUnit hoặc test framework | Test của ứng dụng hoặc build logic | Kiểm thử hành vi tương ứng |
| CLI tool | Script tiện ích hoặc task gọi process | Thực hiện thao tác ngoài JVM |

Nếu class của ứng dụng import org.gradle.api.* chỉ để xử lý nghiệp vụ, đó thường là dấu hiệu phụ thuộc sai chiều. Nếu plugin cần import các class runtime của ứng dụng để tính toán một quy tắc nghiệp vụ, cần xem xét chuyển quy tắc về module ứng dụng hoặc một thư viện domain độc lập phù hợp.

### Không nhầm dependency build-time với dependency runtime

Một thư viện có thể cần để chạy Gradle plugin nhưng không cần trong artifact của ứng dụng. Ngược lại, thư viện ứng dụng có thể cần trong runtime nhưng không nên được đưa vào classpath của build logic chỉ vì hai phần nằm trong cùng repository.

Hãy khai báo dependency trong đúng build hoặc source set sở hữu nó. Điều này giúp classpath rõ ràng và tránh đóng gói nhầm công cụ build vào sản phẩm.

## 6. Đặt logic build ở đâu trong Gradle?

Gradle có nhiều cách tổ chức build logic. Lựa chọn phụ thuộc vào mức độ tái sử dụng, số project, độ phức tạp và nhu cầu kiểm thử.

### Build script của project

Dùng build.gradle hoặc build.gradle.kts cho cấu hình ngắn gọn, gắn trực tiếp với project:

~~~groovy
plugins {
    id 'java'
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đây là nơi phù hợp để áp dụng plugin, khai báo dependency và cấu hình task hiện có. Nếu một build script chứa nhiều lớp, nhiều thuật toán hoặc logic lặp lại giữa các project, nên tách phần đó ra.

### Script plugin

Script plugin là một file script được áp dụng từ build script khác. Nó có thể gom cấu hình dùng chung nhưng vẫn là script được đánh giá trong ngữ cảnh build.

Ví dụ:

~~~groovy
// gradle/common-java.gradle
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Áp dụng:

~~~groovy
apply from: "$rootDir/gradle/common-java.gradle"
~~~

Script plugin phù hợp với việc chia nhỏ cấu hình đơn giản. Khi cần API rõ ràng, type-safe, versioning, test độc lập hoặc tái sử dụng rộng, binary/convention plugin thường là hướng phù hợp hơn.

### buildSrc

buildSrc là một build đặc biệt mà Gradle tự nhận diện trong root project. Nó có thể chứa source code của custom task, plugin và thư viện hỗ trợ build logic. Các lớp ở đó có thể được dùng trong build script của build chính.

Cấu trúc thường gặp:

~~~text
buildSrc/
  build.gradle
  src/
    main/
      groovy/
        ...
    test/
      groovy/
        ...
~~~

buildSrc thuận tiện khi bắt đầu trích xuất build logic khỏi script. Tuy nhiên, thay đổi trong buildSrc có thể làm mất hiệu quả cache/cấu hình của build chính vì build logic này được build như một phần liên quan chặt chẽ. Với build lớn hoặc cần ranh giới module rõ, included build riêng cho build logic thường dễ quản lý hơn.

### Included build dành cho build logic

Một included build có thể đóng gói convention plugin và custom task. Ví dụ, repository tổ chức:

~~~text
repository/
  settings.gradle
  build.gradle
  build-logic/
    settings.gradle
    build.gradle
    src/
      main/
        groovy/
          ...
      test/
        groovy/
          ...
  app/
    build.gradle
~~~

Root settings có thể kết nối included build:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}
~~~

Trong included build, có thể định nghĩa plugin dùng chung. Cấu trúc và cách khai báo cụ thể tùy convention plugin được viết bằng Groovy hay Kotlin DSL.

Included build giúp build logic có cấu trúc và dependency riêng, có thể kiểm thử và phát triển độc lập hơn. Nó cũng tạo một ranh giới rõ ràng giữa cấu hình project và phần triển khai plugin.

### Init script

Init script là script Gradle được áp dụng cho một lần chạy hoặc một môi trường người dùng, thường để thiết lập hành vi dùng chung ngoài repository, chẳng hạn cấu hình nội bộ của tổ chức hoặc quan sát build.

Init script thường không phải nơi thích hợp để lưu quy tắc build bắt buộc của một project, vì người clone repository có thể không có init script trên máy của họ. Nếu build cần một cấu hình để tạo artifact đúng, cấu hình đó nên được version-control trong repository hoặc dependency/plugin đã được quản lý rõ ràng.

## 7. Khi nào nên dùng custom task hoặc plugin?

Không phải mọi đoạn code trong build script đều cần trở thành plugin. Hãy chọn mức tổ chức phù hợp.

| Nhu cầu | Cách tổ chức thường phù hợp |
|---|---|
| Cấu hình một vài property của task hiện có | Build script |
| Chia sẻ vài dòng cấu hình giữa một số project | Convention hoặc script plugin tùy độ phức tạp |
| Có một công việc build mới với input/output cụ thể | Custom task |
| Tái sử dụng task và quy ước trên nhiều project | Convention/binary plugin |
| Build logic lớn, có test và dependency riêng | Included build cho build logic |
| Thiết lập cá nhân hoặc chính sách môi trường ngoài repository | Init script hoặc cấu hình môi trường |
| Điều phối checkout, cài công cụ và nhiều dịch vụ CI | CI workflow hoặc script tiện ích |
| Quy tắc xử lý đơn hàng, giá hoặc quyền người dùng | Module nghiệp vụ của ứng dụng |

### Ví dụ: convention plugin

Giả sử nhiều project Java trong repository cần cùng quy tắc:

- Dùng Java toolchain 21.
- Compile với UTF-8.
- Chạy test bằng JUnit Platform.
- Bật một số compiler warning.

Đây là quy ước build lặp lại. Có thể đóng gói trong plugin, chẳng hạn plugin có id example.java-conventions. Các project chỉ cần áp dụng plugin:

~~~groovy
plugins {
    id 'example.java-conventions'
}
~~~

Như vậy, mỗi project không cần sao chép cùng một khối cấu hình. Plugin sở hữu quy ước build; project chỉ chọn áp dụng quy ước đó.

### Ví dụ: custom task

Giả sử build cần tạo một file phiên bản từ metadata của source tree. Đây là công việc build có input và output xác định, có thể đóng gói thành task type GenerateVersionFile. Task nhận metadata làm input, tạo file trong build/generated/ làm output và được nối vào task cần file đó.

Task nên khai báo các property input/output bằng Gradle managed properties và annotation tương ứng. Không nên đọc một biến môi trường ngầm hoặc truy cập mạng mà không khai báo chúng là input nếu các giá trị đó ảnh hưởng đến kết quả.

### Ví dụ: nghiệp vụ không phải custom task

Giả sử ứng dụng cần tính phí giao hàng theo khu vực, trọng lượng và loại khách hàng. Quy tắc này được gọi khi xử lý đơn hàng, nên nằm trong module nghiệp vụ và có unit test. Gradle chỉ biên dịch, chạy test và đóng gói module đó.

Không nên tạo task calculateShippingFee để ứng dụng gọi trong runtime. Task thuộc build lifecycle; nó không phải API nghiệp vụ của ứng dụng.

## 8. Thiết kế custom task có ranh giới rõ

Một custom task tốt nên thể hiện rõ:

1. **Mục đích**: task tạo ra hoặc kiểm tra kết quả gì?
2. **Input**: dữ liệu nào ảnh hưởng đến kết quả?
3. **Output**: file hoặc trạng thái nào task tạo ra?
4. **Dependencies**: task cần output hoặc công việc nào khác?
5. **Execution**: action thực hiện công việc gì?
6. **Environment**: task cần công cụ, mạng hoặc biến môi trường nào?
7. **Failure behavior**: lỗi nào cần làm task thất bại và thông báo ra sao?

Ví dụ, task kiểm tra metadata:

~~~groovy
abstract class ValidateModuleMetadata extends DefaultTask {
    @InputFile
    abstract RegularFileProperty getMetadataFile()

    @TaskAction
    void validateMetadata() {
        def file = metadataFile.get().asFile
        if (!file.isFile()) {
            throw new GradleException("Metadata file does not exist: " + file)
        }

        if (file.length() == 0) {
            throw new GradleException("Metadata file is empty: " + file)
        }
    }
}
~~~

Task này kiểm tra điều kiện kỹ thuật của file metadata trong build. Nó không nên quyết định một chính sách nghiệp vụ như khách hàng nào được phép mua sản phẩm.

Trong ví dụ thực tế, cần đảm bảo property input bắt buộc được cấu hình, thông báo lỗi có ích và task không thay đổi file nguồn. Nếu task chỉ kiểm tra input, có thể không cần khai báo output. Nếu task tạo report, khai báo output file/directory tương ứng.

### Giữ action độc lập với Project model

Trong thiết kế task hiện đại, nên đưa dữ liệu cần thiết vào task properties và dùng Gradle-managed types. Action tập trung vào xử lý các property đã được cấu hình.

Tránh để action truy cập tùy ý vào Project, Settings, hoặc các đối tượng model Gradle khác. Điều đó có thể làm task khó kiểm thử, khó cache và không tương thích với configuration cache.

Task action cũng nên hạn chế side effect ngoài output đã khai báo. Nếu task tự ý ghi vào source tree, gọi dịch vụ từ xa hoặc sửa file ngoài thư mục build, Gradle khó xác định kết quả và quyết định khi nào có thể tái sử dụng output.

### Không để plugin sở hữu dữ liệu của project

Plugin nên cung cấp khả năng và quy ước; project cung cấp giá trị cấu hình. Ví dụ, plugin có thể tạo task kiểm tra metadata nhưng đường dẫn file, phiên bản hoặc chế độ kiểm tra nên được cấu hình thông qua extension hoặc task property phù hợp.

Tránh hard-code đường dẫn của một máy cá nhân, username, thư mục tuyệt đối hoặc credential vào plugin. Điều đó khiến plugin khó dùng trong project khác và gây lỗi trên CI.

## 9. Kiểm thử từng nhóm logic ở đúng tầng

Ranh giới mã nguồn cũng nên thể hiện trong cách kiểm thử.

| Nhóm | Loại kiểm thử phù hợp | Điều cần xác nhận |
|---|---|---|
| Logic build | Unit test cho lớp thuần; Gradle TestKit cho plugin/task | Plugin áp dụng được, task được tạo đúng, input/output và kết quả build đúng |
| Script tiện ích | Kiểm thử hàm/script hoặc integration test trên môi trường hỗ trợ | Exit code, thông báo lỗi, file tạo ra, cách xử lý tham số và môi trường |
| Nghiệp vụ ứng dụng | Unit test domain/use case, integration test adapter | Quy tắc nghiệp vụ và kết quả runtime đúng với các tình huống |

### Kiểm thử plugin và task với Gradle TestKit

Gradle TestKit cho phép test plugin bằng cách tạo một project mẫu, áp dụng plugin và chạy build thử. Test có thể kiểm tra:

- Plugin được áp dụng thành công.
- Task mong đợi xuất hiện.
- Task nhận đúng cấu hình.
- Build thành công hoặc thất bại theo điều kiện.
- Output được tạo đúng.
- Task có trạng thái up-to-date hoặc lấy từ cache khi phù hợp.

Ví dụ ý tưởng kiểm thử:

~~~java
BuildResult result = GradleRunner.create()
    .withProjectDir(testProjectDir)
    .withArguments("generateGreeting")
    .withPluginClasspath()
    .build();

assertTrue(result.getOutput().contains("BUILD SUCCESSFUL"));
~~~

Đây là đoạn minh họa sử dụng Gradle TestKit trong test của plugin; cần chuẩn bị project test và plugin classpath theo cấu trúc của module. TestKit kiểm tra hành vi plugin qua một Gradle build thật, thay vì chỉ gọi trực tiếp một phương thức Java.

### Kiểm thử nghiệp vụ độc lập

Ví dụ, PriceCalculatorTest nên kiểm tra các trường hợp giảm giá, khách hàng không đủ điều kiện, tổng tiền bằng không và các giới hạn liên quan. Test không cần khởi chạy Gradle plugin để gọi logic tính giá. Gradle chỉ là công cụ chạy test đó.

Sự độc lập này giúp nghiệp vụ có thể được kiểm thử từ IDE, Maven hoặc một hệ thống build khác nếu dự án thay đổi công cụ build.

### Kiểm thử script tiện ích

Script cần kiểm tra các nhánh thành công và thất bại: thiếu executable, thiếu biến môi trường, tham số sai, quyền ghi bị từ chối hoặc công cụ con trả exit code khác 0. Với script điều phối, nên kiểm tra rằng lỗi từ lệnh con được truyền lên và pipeline không báo thành công giả.

## 10. Quản lý cấu hình và secret đúng nơi

Các giá trị cấu hình có thể xuất hiện ở build time và runtime, nhưng ý nghĩa khác nhau.

| Giá trị | Nơi quản lý phù hợp |
|---|---|
| Phiên bản Gradle Wrapper | Repository |
| Java toolchain cần cho compile/test | Build logic của repository |
| Quy tắc compiler và test | Build script hoặc convention plugin |
| Đường dẫn công cụ riêng của runner | CI configuration hoặc environment |
| Token truy cập repository riêng | Secret store/credential store |
| Database URL của ứng dụng | Runtime configuration |
| Mật khẩu database | Secret manager hoặc cơ chế secret của môi trường chạy |
| Mức giảm giá hoặc chính sách nghiệp vụ | Mô hình/quy tắc nghiệp vụ, có nguồn cấu hình được kiểm soát |

Một số task có thể cần credential để publish artifact. Credential đó phục vụ build/publish và nên được cấp từ secret store hoặc Gradle credential mechanism, không ghi vào script hoặc log.

Ứng dụng runtime có thể cần một credential khác, chẳng hạn kết nối database. Không nên đóng gói secret runtime vào artifact trong quá trình build. Artifact nên nhận cấu hình và secret từ môi trường triển khai.

Nếu một giá trị ảnh hưởng đến output của task, hãy xác định nó như input theo cách phù hợp. Nếu giá trị là secret, không đưa nội dung bí mật vào log, task path, tên artifact hoặc cache key công khai. Cần chọn chính sách cache phù hợp cho task xử lý dữ liệu nhạy cảm.

## 11. Những dấu hiệu ranh giới đang bị đặt sai

Một số dấu hiệu thường gặp cho thấy logic đang nằm sai nơi:

| Dấu hiệu | Vấn đề có thể có | Hướng tổ chức lại |
|---|---|---|
| build.gradle chứa hàng trăm dòng thuật toán và thao tác file | Build script khó đọc và cấu hình có side effect | Trích xuất thành task type hoặc plugin |
| Nhiều project sao chép cùng cấu hình | Quy ước build bị phân tán | Tạo convention plugin |
| Plugin Gradle chứa logic tính giá hoặc quyền người dùng | Build tooling sở hữu nghiệp vụ runtime | Chuyển logic vào module domain/application |
| Ứng dụng import Gradle API để chạy nghiệp vụ | Runtime phụ thuộc build system | Loại bỏ dependency build khỏi application classpath |
| Script tiện ích chứa cùng một đoạn lệnh bị sao chép ở nhiều nơi | Khó sửa và khó đồng bộ | Tạo script dùng chung hoặc task/plugin phù hợp |
| Task tự sửa source file hoặc gọi mạng ngầm | Input/output và side effect không rõ | Khai báo input/output, làm rõ dependency và môi trường |
| Init script chứa cấu hình bắt buộc của project | Build phụ thuộc máy người dùng | Đưa cấu hình bắt buộc vào repository |
| Task dùng credential runtime của ứng dụng | Trộn trách nhiệm build và vận hành | Tách secret theo môi trường và mục đích |

Không phải cứ có nhiều dòng trong build script là phải tạo plugin. Mục tiêu là chọn ranh giới giúp người đọc hiểu công việc thuộc về đâu, có thể kiểm thử ở đâu và ai chịu trách nhiệm cho vòng đời của nó.

## 12. Ví dụ tổng hợp: từ mã nguồn đến ứng dụng chạy

Giả sử một dịch vụ đặt hàng cần build, kiểm tra và triển khai.

### Cấu trúc minh họa

~~~text
order-service/
  settings.gradle
  build.gradle
  build-logic/
    ...
  scripts/
    check-environment.ps1
    package-release.ps1
  src/
    main/
      java/
        com/example/order/
          domain/
          application/
          infrastructure/
          web/
    test/
      java/
~~~

Trong cấu trúc này:

- build.gradle áp dụng plugin và cấu hình project.
- build-logic/ có thể là included build chứa convention plugin và task type dùng chung.
- scripts/ chứa script hỗ trợ môi trường hoặc điều phối release.
- src/main/java/ chứa mã nguồn ứng dụng, bao gồm nghiệp vụ đặt hàng.
- src/test/java/ chứa test của ứng dụng.

Tên thư mục chỉ có ý nghĩa khi settings/build script thực sự kết nối included build và plugin được cấu hình. Một thư mục tên build-logic tự nó không tự động trở thành Gradle included build.

### Luồng thực hiện

1. CI cấp runner và checkout source.
2. Script tiện ích có thể kiểm tra công cụ hoặc chuẩn bị môi trường.
3. Gradle Wrapper khởi chạy Gradle.
4. Convention plugin cấu hình Java toolchain, compiler và test.
5. Các task biên dịch mã nguồn và chạy test.
6. Task đóng gói tạo artifact.
7. Script hoặc workflow CI lưu artifact và thực hiện bước triển khai theo quyền được cấp.
8. Ứng dụng khởi chạy ở runtime, nhận cấu hình môi trường và xử lý nghiệp vụ đặt hàng.

Build có thể kiểm tra rằng file cấu hình tồn tại hoặc artifact có đúng cấu trúc. Nghiệp vụ ứng dụng mới quyết định một đơn hàng có hợp lệ, tổng tiền là bao nhiêu hoặc trạng thái nào được phép chuyển tiếp.

### Khi thay đổi yêu cầu

- Đổi Java version để compile: thay đổi toolchain/convention build.
- Thêm task sinh file metadata: thay đổi custom task/plugin.
- Thay cách kiểm tra môi trường CI: thay đổi script hoặc workflow.
- Thay quy tắc tính tổng đơn hàng: thay đổi mã nghiệp vụ và test ứng dụng.
- Thay secret database production: thay đổi cấu hình/secret của môi trường runtime.

Phân loại theo mục đích giúp xác định đúng module cần thay đổi và giới hạn phạm vi ảnh hưởng.

## 13. Cách quyết định đặt một đoạn logic ở đâu

Khi chưa rõ một đoạn logic thuộc nhóm nào, hãy tự hỏi theo trình tự:

1. **Nó quyết định hành vi sản phẩm khi chạy không?** Nếu có, đó thường là nghiệp vụ ứng dụng.
2. **Nó tạo, kiểm tra hoặc đóng gói artifact?** Nếu có, đó thường là logic build.
3. **Nó điều phối công cụ hoặc thao tác repository/môi trường bên ngoài build?** Nếu có, script tiện ích hoặc CI workflow thường phù hợp.
4. **Nhiều project cần dùng cùng quy ước build?** Cân nhắc convention plugin.
5. **Công việc có input/output rõ và cần tham gia task graph?** Cân nhắc custom task.
6. **Logic thuần có thể dùng độc lập với Gradle không?** Nếu có, giữ nó trong thư viện hoặc module độc lập phù hợp, rồi để build logic gọi qua API cần thiết thay vì buộc domain phụ thuộc Gradle.

Bảng quyết định nhanh:

| Câu hỏi về đoạn code | Vị trí nên xem xét |
|---|---|
| Có quyết định nghiệp vụ khi request/event đến? | Application/domain code |
| Có cấu hình compiler, dependency hoặc task? | Build script/convention plugin |
| Có tạo hoặc kiểm tra output của build? | Custom task/task type |
| Có lặp lại quy ước trên nhiều project? | Convention plugin |
| Có chuẩn bị máy, gọi CLI hoặc điều phối nhiều hệ thống? | Utility script/CI workflow |
| Có cấu hình cá nhân ngoài repository? | Init script hoặc môi trường người dùng |

Một số công việc nằm ở ranh giới. Ví dụ, sinh mã nguồn có thể dùng thuật toán phức tạp nhưng vẫn là build logic nếu nó chuyển input của source tree thành output được biên dịch. Ngược lại, việc kiểm tra một chính sách nghiệp vụ không trở thành build logic chỉ vì người phát triển muốn chạy nó trước khi publish. Hãy nhìn vào mục đích và thời điểm sử dụng, không chỉ nhìn vào độ phức tạp hoặc ngôn ngữ lập trình.

## 14. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| Mọi mã trong repository đều là mã ứng dụng | Repository có thể chứa build logic, script tiện ích, test, tài liệu và mã runtime |
| Build script là nơi viết mọi automation | Build script cấu hình build; công việc build phức tạp nên nằm trong task/plugin |
| Script tiện ích và Gradle task là một | Script điều phối bên ngoài; task tham gia task graph và có input/output do Gradle quản lý |
| Custom task là nơi đặt quy tắc nghiệp vụ | Task phục vụ quá trình build; nghiệp vụ thuộc application/domain |
| Plugin phải chứa toàn bộ logic của project | Plugin nên cung cấp khả năng và quy ước có thể tái sử dụng, project cung cấp cấu hình |
| build-logic/ tự động được Gradle nhận diện | Included build cần được kết nối từ settings; tên thư mục không tạo quan hệ đó |
| buildSrc và included build luôn giống nhau | Chúng đều có thể chứa build logic nhưng có cơ chế tích hợp và ranh giới build khác nhau |
| Mọi cấu hình đều nên nằm trong init script | Cấu hình bắt buộc để build project đúng cần được version-control cùng project |
| Build cache có thể lưu mọi task tùy ý | Task cần khai báo input/output và đáp ứng yêu cầu cacheability |
| Secret có thể ghi vào build script cho tiện | Secret nên được cấp từ credential/secret store theo đúng môi trường và mục đích |

Ranh giới tốt giúp mỗi thành phần có một trách nhiệm dễ giải thích: Gradle quyết định cách tạo sản phẩm; script tiện ích hỗ trợ con người và pipeline thao tác với môi trường; ứng dụng thực hiện chức năng mà sản phẩm cam kết. Khi đặt logic đúng chỗ, từng phần có thể được kiểm thử, thay đổi và tái sử dụng theo vòng đời của chính nó.
