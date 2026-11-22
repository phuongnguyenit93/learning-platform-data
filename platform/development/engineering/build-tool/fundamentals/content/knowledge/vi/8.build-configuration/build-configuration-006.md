# Tham số hóa cấu hình theo môi trường mà không nhân bản quy trình

Một dự án Java thường được build và chạy trong nhiều môi trường: máy lập trình viên, môi trường kiểm thử, CI, staging và production. Mỗi môi trường có thể dùng endpoint, tên artifact, thông tin kết nối hoặc một số tùy chọn khác nhau. Nếu tạo một bộ script riêng cho từng môi trường, quy trình sẽ nhanh chóng bị phân nhánh: sửa bước compile ở môi trường này nhưng quên sửa ở môi trường khác, hoặc một môi trường chạy thêm bước kiểm tra mà môi trường còn lại không có.

**Tham số hóa cấu hình** là cách giữ một quy trình build chung, đồng thời cung cấp giá trị đầu vào khác nhau theo môi trường. Build script định nghĩa các bước cần làm một lần; mỗi lần chạy chỉ truyền hoặc đọc các giá trị cấu hình tương ứng.

Ví dụ, cùng một lệnh build có thể dùng cấu hình `local` trên máy cá nhân và `ci` trong pipeline. Tác vụ vẫn là `build`, `test`, `package`; các giá trị như tên môi trường, endpoint hoặc tùy chọn kiểm tra được cung cấp từ bên ngoài.

## 1. Vì sao cần tham số hóa cấu hình?

Giả sử dự án có ba môi trường:

| Môi trường | Mục đích | Một số giá trị có thể khác |
|---|---|---|
| `local` | Lập trình viên chạy trên máy cá nhân | Endpoint localhost, log chi tiết, dữ liệu thử nghiệm |
| `ci` | Build và kiểm thử tự động | Chạy kiểm tra nghiêm ngặt, endpoint mock, không cần thao tác thủ công |
| `staging` | Kiểm tra trước khi phát hành | Endpoint staging, cấu hình tích hợp staging |
| `production` | Phục vụ người dùng thật | Endpoint production, thông tin xác thực do hệ thống triển khai cung cấp |

Một cách tổ chức kém linh hoạt là tạo các script riêng:

```text
build-local.gradle
build-ci.gradle
build-staging.gradle
build-production.gradle
```

Mỗi script có thể dần chứa những bản sao của cùng một quy trình. Khi thêm bước kiểm tra hoặc sửa cách đóng gói, phải cập nhật tất cả bản sao và bảo đảm chúng không lệch nhau.

Một cách dễ bảo trì hơn là giữ một build script và truyền cấu hình:

```text
                 targetEnvironment
                         |
             +-----------+-----------+
             |           |           |
           local         ci        staging
             |           |           |
             +-----------+-----------+
                         |
                 Cùng task graph
                         |
               compile -> test -> package
```

Build script có thể dùng một giá trị cấu hình để chọn endpoint hoặc mức kiểm tra. Các task và thứ tự thực hiện vẫn được khai báo một lần.

## 2. Phân biệt cấu hình build với cấu hình runtime

Trước khi tham số hóa, cần xác định giá trị đó thuộc về quá trình build hay thuộc về ứng dụng khi chạy.

**Cấu hình build** điều khiển cách build tool làm việc, ví dụ:

- Phiên bản hoặc đường dẫn công cụ cần dùng.
- Có bật một bước kiểm tra đặc biệt hay không.
- Thư mục hoặc tên artifact đầu ra.
- Thông số của code generator.
- Endpoint của dịch vụ mà một task build cần gọi.
- Thông tin xác thực để publish artifact.

**Cấu hình runtime** điều khiển hành vi ứng dụng sau khi JVM khởi chạy, ví dụ:

- URL database mà ứng dụng kết nối.
- Port HTTP.
- Mức log của ứng dụng.
- Feature flag.
- Tên hàng đợi hoặc dịch vụ mà ứng dụng sử dụng.

Hai loại có thể liên quan nhưng không nên tự động trộn lẫn. Nếu ứng dụng có thể dùng cùng một JAR ở staging và production, thường nên cung cấp cấu hình runtime khi triển khai thay vì build hai JAR khác nhau chỉ vì endpoint hoặc mật khẩu khác nhau.

Ví dụ, một ứng dụng Spring Boot có thể đọc `SPRING_DATASOURCE_URL` khi chạy. Giá trị đó không nhất thiết phải được truyền vào Gradle. Build tool chỉ cần biên dịch và đóng gói ứng dụng; hệ thống triển khai cung cấp endpoint database cho tiến trình JVM.

Ngược lại, nếu một task Gradle cần endpoint để tải schema trước khi sinh source, endpoint đó là input của task build và cần được truyền cho task theo cách có thể quan sát, kiểm soát và kiểm tra.

## 3. Tham số hóa bằng Gradle project properties

Gradle hỗ trợ project property để truyền giá trị cấu hình vào build. Có thể khai báo giá trị mặc định và cho phép người chạy ghi đè bằng tùy chọn `-P`.

Ví dụ:

```groovy
def targetEnvironment = providers.gradleProperty('targetEnvironment')
    .orElse('local')

tasks.register('showBuildEnvironment') {
    inputs.property('targetEnvironment', targetEnvironment)

    doLast {
        println "Build environment: ${targetEnvironment.get()}"
    }
}
```

Trong đó:

- `providers.gradleProperty('targetEnvironment')` tạo một `Provider` đọc project property có tên `targetEnvironment`.
- `orElse('local')` cung cấp giá trị mặc định khi property chưa được truyền.
- `inputs.property(...)` khai báo giá trị là input của task.
- `get()` lấy giá trị khi task action thực thi.

Chạy với mặc định:

```bash
./gradlew showBuildEnvironment
```

Chạy với môi trường staging:

```bash
./gradlew showBuildEnvironment -PtargetEnvironment=staging
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat showBuildEnvironment -PtargetEnvironment=staging
```

Build script không cần bản sao riêng cho staging. Người chạy chỉ thay đổi giá trị đầu vào.

### 3.1. Dùng project property trong nhiều task

Một property có thể được dùng bởi nhiều task trong cùng project. Ví dụ, generator và task tạo metadata có thể cùng cần biết môi trường mục tiêu.

```groovy
def targetEnvironment = providers.gradleProperty('targetEnvironment')
    .orElse('local')

tasks.register('generateBuildMetadata') {
    inputs.property('targetEnvironment', targetEnvironment)

    doLast {
        def environment = targetEnvironment.get()
        println "Generating metadata for ${environment}"
    }
}

tasks.register('verifyBuildConfiguration') {
    inputs.property('targetEnvironment', targetEnvironment)

    doLast {
        println "Verifying ${targetEnvironment.get()} configuration"
    }
}
```

Hai task dùng cùng một nguồn cấu hình, vì vậy không phải truyền một biến riêng cho từng task hoặc sao chép logic theo môi trường.

### 3.2. Lưu giá trị mặc định trong `gradle.properties`

Có thể đặt project property mặc định trong `gradle.properties`:

```properties
targetEnvironment=local
```

Gradle có thể đọc `gradle.properties` ở những vị trí cấu hình được hỗ trợ, trong đó thường dùng file ở project root hoặc Gradle User Home. File ở project root phù hợp với cấu hình mặc định không nhạy cảm và có thể chia sẻ trong repository.

Khi chạy:

```bash
./gradlew showBuildEnvironment -PtargetEnvironment=ci
```

giá trị truyền từ command line được dùng cho lần chạy đó. Không cần sửa file mặc định để chuyển qua lại giữa các môi trường.

Không nên lưu mật khẩu, token hoặc private key vào `gradle.properties` được commit. Nếu cần giá trị bí mật, dùng secret store của CI hoặc biến môi trường được bảo vệ.

## 4. Đọc biến môi trường bằng Provider API

Một số cấu hình được cung cấp bởi hệ điều hành, container hoặc CI. Gradle có thể đọc chúng qua `providers.environmentVariable(...)`.

Ví dụ:

```groovy
def deploymentRegion = providers.environmentVariable('DEPLOYMENT_REGION')
    .orElse('local')

tasks.register('showDeploymentRegion') {
    inputs.property('deploymentRegion', deploymentRegion)

    doLast {
        println "Deployment region: ${deploymentRegion.get()}"
    }
}
```

Trên Linux/macOS:

```bash
DEPLOYMENT_REGION=ap-southeast-1 ./gradlew showDeploymentRegion
```

Trên PowerShell:

```powershell
$env:DEPLOYMENT_REGION = 'ap-southeast-1'
.\gradlew.bat showDeploymentRegion
```

Trên Windows CMD:

```bat
set DEPLOYMENT_REGION=ap-southeast-1
gradlew.bat showDeploymentRegion
```

Biến môi trường được truyền vào tiến trình Gradle. Build script dùng Provider API để đọc nó khi cần.

### 4.1. Project property và environment variable khác nhau

| Nguồn | Cách đọc trong Gradle | Cách truyền thường gặp | Dùng khi nào |
|---|---|---|---|
| Gradle project property | `providers.gradleProperty('name')` | `-Pname=value`, `gradle.properties`, hoặc `ORG_GRADLE_PROJECT_name` | Tham số build do dự án định nghĩa |
| Environment variable | `providers.environmentVariable('NAME')` | Shell, CI, container hoặc hệ điều hành | Giá trị được môi trường tiến trình cung cấp |
| JVM system property | `providers.systemProperty('name')` | `-Dname=value` | Tùy chọn dành cho JVM/tiến trình Gradle hoặc hệ thống Java liên quan |

Không nên chọn nguồn chỉ vì cú pháp ngắn. Hãy xác định ai sở hữu giá trị và cách triển khai cung cấp nó. Project property thường tiện cho tùy chọn build; environment variable phù hợp với cấu hình do hệ thống hoặc CI quản lý; system property nên dùng khi API hoặc công cụ cụ thể yêu cầu.

Gradle cũng hỗ trợ biến môi trường có tiền tố `ORG_GRADLE_PROJECT_` để cung cấp project property. Ví dụ, `ORG_GRADLE_PROJECT_targetEnvironment=ci` có thể được đọc bằng `providers.gradleProperty('targetEnvironment')`. Cách này hữu ích trong CI khi muốn cấu hình project property mà không phải đưa giá trị vào command line.

### 4.2. Tránh đọc môi trường tùy tiện trong build script

Trong build script cũ có thể gặp:

```groovy
def target = System.getenv('TARGET_ENVIRONMENT') ?: 'local'
```

Đoạn này đọc biến môi trường trực tiếp trong configuration phase. Với build hiện đại, nên ưu tiên Provider API:

```groovy
def target = providers.environmentVariable('TARGET_ENVIRONMENT')
    .orElse('local')
```

Provider giúp trì hoãn việc lấy giá trị và tích hợp tốt hơn với mô hình cấu hình lazy của Gradle. Khi dùng giá trị làm input của task, hãy truyền provider vào input property để Gradle biết task phụ thuộc vào giá trị đó.

## 5. Kết hợp mặc định, lựa chọn môi trường và xác thực

Một property có thể được truyền sai, ví dụ `stagin` thay vì `staging`. Nếu build script âm thầm dùng giá trị không hợp lệ, artifact có thể được tạo với cấu hình ngoài dự kiến.

Nên xác thực giá trị trước khi thực hiện tác vụ phụ thuộc vào nó.

```groovy
def targetEnvironment = providers.gradleProperty('targetEnvironment')
    .orElse('local')

def allowedEnvironments = ['local', 'ci', 'staging', 'production']

tasks.register('validateTargetEnvironment') {
    inputs.property('targetEnvironment', targetEnvironment)

    doLast {
        def selected = targetEnvironment.get()

        if (!allowedEnvironments.contains(selected)) {
            throw new GradleException(
                "Unsupported targetEnvironment '${selected}'. " +
                "Allowed values: ${allowedEnvironments.join(', ')}"
            )
        }

        println "Using target environment: ${selected}"
    }
}
```

Task sử dụng `GradleException` để dừng build với thông báo rõ ràng khi giá trị không hợp lệ. Có thể nối nó vào task cần cấu hình đã được xác thực:

```groovy
tasks.named('build') {
    dependsOn(tasks.named('validateTargetEnvironment'))
}
```

Nếu chỉ một task cần giá trị đó, nên nối validation vào task đó thay vì bắt mọi tác vụ không liên quan đều phải chạy validation.

### 5.1. Ánh xạ môi trường thành cấu hình

Thay vì viết một nhánh build script cho mỗi môi trường, có thể ánh xạ tên môi trường thành một tập giá trị cấu hình.

```groovy
def targetEnvironment = providers.gradleProperty('targetEnvironment')
    .orElse('local')

def environmentSettings = [
    local: [apiBaseUrl: 'http://localhost:8080'],
    ci: [apiBaseUrl: 'http://mock-service:8080'],
    staging: [apiBaseUrl: 'https://staging-api.example.test'],
    production: [apiBaseUrl: 'https://api.example.com']
]

def apiBaseUrl = targetEnvironment.map { name ->
    def settings = environmentSettings[name]
    if (settings == null) {
        throw new GradleException("Unknown targetEnvironment: ${name}")
    }
    settings.apiBaseUrl
}

tasks.register('showApiTarget') {
    inputs.property('targetEnvironment', targetEnvironment)
    inputs.property('apiBaseUrl', apiBaseUrl)

    doLast {
        println "Environment: ${targetEnvironment.get()}"
        println "API base URL: ${apiBaseUrl.get()}"
    }
}
```

Ở đây, quy trình task không thay đổi. Chỉ có giá trị `apiBaseUrl` được ánh xạ từ tên môi trường. Bảng cấu hình chỉ chứa giá trị không nhạy cảm; thông tin xác thực cần được lấy từ nguồn bí mật riêng.

Với dự án lớn, có thể đặt phần ánh xạ trong convention plugin hoặc một lớp cấu hình dùng chung. Tránh để nhiều module tự định nghĩa những bảng môi trường gần giống nhau vì chúng có thể lệch theo thời gian.

## 6. Dùng một task graph chung cho nhiều môi trường

Mục tiêu của tham số hóa là giữ một luồng công việc thống nhất. Ví dụ, cùng một task `verifyDeploymentInputs` có thể kiểm tra cấu hình cho môi trường local, staging hoặc production:

```groovy
def targetEnvironment = providers.gradleProperty('targetEnvironment')
    .orElse('local')

tasks.register('verifyDeploymentInputs') {
    inputs.property('targetEnvironment', targetEnvironment)

    doLast {
        def environment = targetEnvironment.get()
        println "Verifying deployment inputs for ${environment}"
        // Kiểm tra các giá trị phù hợp với môi trường đã chọn.
    }
}

tasks.named('check') {
    dependsOn(tasks.named('verifyDeploymentInputs'))
}
```

Các lệnh sau dùng cùng task và cùng task graph:

```bash
./gradlew check -PtargetEnvironment=local
./gradlew check -PtargetEnvironment=ci
./gradlew check -PtargetEnvironment=staging
```

Điều khác nhau là input cấu hình. Task graph không cần được nhân bản thành `checkLocal`, `checkCi` và `checkStaging` nếu các bước công việc về bản chất giống nhau.

### 6.1. Khi nào được phép có điều kiện theo môi trường?

Tham số hóa không có nghĩa mọi môi trường bắt buộc phải thực hiện chính xác mọi thao tác. Ví dụ, chỉ môi trường production mới có bước ký artifact, hoặc chỉ CI mới tạo báo cáo coverage. Tuy nhiên, điều kiện nên được thể hiện rõ và tập trung.

Ví dụ một task có thể được bật có điều kiện:

```groovy
def targetEnvironment = providers.gradleProperty('targetEnvironment')
    .orElse('local')

tasks.register('signReleaseArtifact') {
    onlyIf {
        targetEnvironment.get() == 'production'
    }

    doLast {
        println 'Signing release artifact'
    }
}
```

`onlyIf` quyết định task action có được thực hiện hay không khi task đã nằm trong graph. Nó không thay thế dependency và không tự bảo đảm rằng các input bắt buộc đã tồn tại. Với tác vụ nhạy cảm như ký hoặc publish, cần kiểm tra thêm credential và điều kiện phát hành.

Nếu các môi trường có quy trình thực sự khác nhau, có thể có task chuyên biệt cho từng thao tác. Nhưng hãy giữ các bước chung ở một nơi và chỉ phân nhánh ở điểm có khác biệt thực chất. Không sao chép toàn bộ build pipeline chỉ vì một vài tham số khác nhau.

## 7. Đưa cấu hình vào task input để hỗ trợ build chính xác

Gradle dùng input và output để quyết định task có cần chạy lại không. Nếu task sử dụng một property nhưng không khai báo nó là input, Gradle có thể không nhận ra rằng kết quả cần được tạo lại khi giá trị thay đổi.

Ví dụ task tạo file metadata theo môi trường:

```groovy
def targetEnvironment = providers.gradleProperty('targetEnvironment')
    .orElse('local')

def metadataFile = layout.buildDirectory.file('generated/build-info.txt')

tasks.register('generateBuildMetadata') {
    inputs.property('targetEnvironment', targetEnvironment)
    outputs.file(metadataFile)

    doLast {
        def output = metadataFile.get().asFile
        output.parentFile.mkdirs()
        output.text = "environment=${targetEnvironment.get()}\n"
    }
}
```

Chạy:

```bash
./gradlew generateBuildMetadata -PtargetEnvironment=local
./gradlew generateBuildMetadata -PtargetEnvironment=staging
```

Khi giá trị input thay đổi, Gradle có thể xác định task không còn up-to-date và cần thực thi lại. Nếu task không khai báo `targetEnvironment` là input, việc thay đổi giá trị có thể không được phản ánh đúng trong up-to-date check.

Với task type riêng, nên dùng property có kiểu và annotation tương ứng:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class GenerateEnvironmentMetadata extends DefaultTask {
    @Input
    abstract Property<String> getTargetEnvironment()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.text = "environment=${targetEnvironment.get()}\n"
    }
}

def targetEnvironmentProvider = providers.gradleProperty('targetEnvironment')
    .orElse('local')

tasks.register('generateEnvironmentMetadata', GenerateEnvironmentMetadata) {
    targetEnvironment.set(targetEnvironmentProvider)
    outputFile.set(layout.buildDirectory.file('generated/environment.txt'))
}
```

Ví dụ task type trên cho thấy cách mô tả cấu hình bằng `@Input` và file tạo ra bằng `@OutputFile`. Trong build logic thực tế, nên đặt task type trong convention plugin hoặc build logic dùng chung thay vì khai báo nhiều class task trong các build script rời rạc.

## 8. Tham số hóa thông tin bí mật an toàn

Các giá trị như API token, mật khẩu repository, signing key và credential không nên được lưu trong file build được commit hoặc ghi trực tiếp vào log.

Có thể đọc secret từ environment variable:

```groovy
def publishToken = providers.environmentVariable('PUBLISH_TOKEN')

tasks.register('publishInternalArtifact') {
    doLast {
        def token = publishToken.orNull

        if (token == null || token.isBlank()) {
            throw new GradleException('PUBLISH_TOKEN is required for publishing')
        }

        // Truyền token cho API/client publish theo cách an toàn.
        // Không in token ra console.
        println 'Publishing with configured credentials'
    }
}
```

Hệ thống CI nên lưu `PUBLISH_TOKEN` trong secret store và chỉ cấp cho job cần publish. Trên máy cá nhân, có thể cấu hình biến môi trường trong phiên shell hoặc cơ chế quản lý credential của tổ chức.

Không nên:

- Commit token hoặc mật khẩu vào `gradle.properties`, `build.gradle` hay file YAML công khai.
- Truyền secret trực tiếp trong lệnh `-Ptoken=...` nếu command line có thể xuất hiện trong shell history hoặc process listing.
- In toàn bộ environment hoặc toàn bộ project properties ra log để debug.
- Đưa secret vào artifact, generated source hoặc metadata được phân phối.
- Dùng một credential production cho mọi task hoặc mọi môi trường khi không cần thiết.

Nếu dùng biến `ORG_GRADLE_PROJECT_publishToken`, Gradle có thể cung cấp nó như project property. Tuy nhiên, việc lưu trữ và cấp biến vẫn phải tuân theo chính sách bảo vệ secret của CI hoặc môi trường triển khai.

## 9. Phân biệt tham số hóa với việc nhân bản task

Khi môi trường khác nhau, đôi khi người viết build script tạo nhiều task:

```groovy
tasks.register('buildLocal') {
    // Quy trình build local
}

tasks.register('buildStaging') {
    // Bản sao quy trình build staging
}

tasks.register('buildProduction') {
    // Bản sao quy trình build production
}
```

Nếu ba task chỉ khác nhau ở endpoint, tên môi trường hoặc một vài flag, cấu hình trên làm tăng số lượng logic cần bảo trì.

Thay vào đó, có thể dùng một task và một property:

```groovy
def targetEnvironment = providers.gradleProperty('targetEnvironment')
    .orElse('local')

tasks.register('buildForTarget') {
    inputs.property('targetEnvironment', targetEnvironment)

    doLast {
        println "Building for ${targetEnvironment.get()}"
        // Cùng quy trình, sử dụng giá trị cấu hình đã chọn.
    }
}
```

Chạy:

```bash
./gradlew buildForTarget -PtargetEnvironment=local
./gradlew buildForTarget -PtargetEnvironment=staging
./gradlew buildForTarget -PtargetEnvironment=production
```

Task graph vẫn được khai báo một lần. Nếu cần task chuyên biệt cho thao tác publish hoặc deploy, hãy giữ chúng riêng nhưng tái sử dụng logic và cấu hình chung, thay vì sao chép toàn bộ quy trình build.

## 10. Cấu hình theo môi trường trong Maven

Maven hỗ trợ property và profile để thay đổi một phần cấu hình theo điều kiện.

### 10.1. Dùng property

Trong `pom.xml`:

```xml
<properties>
  <target.environment>local</target.environment>
</properties>
```

Có thể ghi đè property khi chạy Maven:

```bash
mvn verify -Dtarget.environment=staging
```

Property có thể được dùng trong cấu hình plugin hoặc những vị trí Maven hỗ trợ interpolation.

### 10.2. Dùng profile

Profile gom một nhóm cấu hình được kích hoạt theo điều kiện hoặc theo tên:

```xml
<profiles>
  <profile>
    <id>staging</id>
    <properties>
      <target.environment>staging</target.environment>
      <api.base.url>https://staging-api.example.test</api.base.url>
    </properties>
  </profile>

  <profile>
    <id>production</id>
    <properties>
      <target.environment>production</target.environment>
      <api.base.url>https://api.example.com</api.base.url>
    </properties>
  </profile>
</profiles>
```

Kích hoạt profile:

```bash
mvn verify -Pstaging
```

Hoặc:

```bash
mvn verify -Pproduction
```

Profile cho phép gom những khác biệt cần thiết. Tuy nhiên, nếu mỗi profile chứa một bản sao đầy đủ của plugin executions hoặc dependency graph, dự án vẫn có nguy cơ phân nhánh quy trình. Nên giữ các bước chung ở phần cấu hình chung và chỉ đặt các giá trị khác biệt trong profile.

### 10.3. So sánh Gradle và Maven

| Nhu cầu | Gradle | Maven |
|---|---|---|
| Truyền tham số build | `-Pname=value` | `-Dname=value` |
| Giá trị mặc định | `gradle.properties`, `Provider.orElse(...)` | `<properties>` trong POM |
| Đọc biến môi trường | `providers.environmentVariable(...)` | `${env.NAME}` trong các vị trí Maven hỗ trợ |
| Cấu hình theo profile | Có thể ánh xạ property sang cấu hình | Maven profile |
| Giữ quy trình chung | Task graph và task dùng chung | Lifecycle/plugin executions dùng chung |
| Khai báo input để kiểm tra output | Task input/output properties | Plugin goal parameters và cơ chế incremental của plugin |

Gradle và Maven có cách mô hình hóa build khác nhau, nhưng nguyên tắc giống nhau: giữ logic chung ở một nơi, truyền giá trị khác nhau từ môi trường, và chỉ tạo nhánh khi quy trình thực sự khác.

## 11. Tránh để môi trường làm build mất tính tái lập

Một build có thể cho ra artifact khác nhau nếu cùng source code nhưng nhận các tham số khác nhau. Điều đó đôi khi là chủ đích, nhưng cần được kiểm soát.

Ví dụ, nếu task tạo metadata ghi tên môi trường vào JAR, artifact staging và production sẽ khác nhau. Nếu mục tiêu là build một artifact duy nhất rồi promote qua các môi trường, không nên nhúng endpoint hoặc tên môi trường vào bytecode/resource của artifact. Hãy truyền runtime configuration khi triển khai.

Các nguyên tắc cần cân nhắc:

- Khai báo rõ những property nào ảnh hưởng đến output của task.
- Dùng giá trị mặc định xác định được, tránh phụ thuộc ngầm vào trạng thái máy cá nhân.
- Không đọc thời gian hiện tại, hostname hoặc biến môi trường tùy tiện để tạo output nếu chúng không được khai báo là input.
- Giữ dependency và toolchain được kiểm soát để cùng đầu vào tạo ra kết quả nhất quán.
- Không đưa secret vào output hoặc log.
- Ghi nhận tham số build quan trọng trong log an toàn hoặc metadata không nhạy cảm khi cần truy vết.

### 11.1. Cấu hình thay đổi có thể làm task chạy lại

Nếu task tạo output dựa trên `targetEnvironment`, property đó phải được khai báo là input. Khi staging chuyển sang production, Gradle cần biết đây là một đầu vào khác để không tái sử dụng output không phù hợp.

Ngược lại, nếu một giá trị chỉ dùng khi ứng dụng chạy và không ảnh hưởng đến build artifact, không cần đưa nó thành input của task build. Việc phân biệt đúng build-time và runtime giúp giữ cache hiệu quả và artifact có thể tái sử dụng.

### 11.2. Configuration cache và Provider API

Gradle configuration cache lưu kết quả configuration phase để giảm chi phí cấu hình ở những lần chạy sau. Đọc môi trường trực tiếp hoặc truy cập trạng thái bên ngoài trong configuration phase theo cách không được Gradle quản lý có thể làm build không tương thích với configuration cache.

Provider API giúp biểu diễn giá trị cấu hình một cách lazy và rõ nguồn. Nên tránh đọc trực tiếp `System.getenv()` hoặc `System.getProperty()` trong các đoạn cấu hình tùy tiện; dùng `providers.environmentVariable`, `providers.gradleProperty` và `providers.systemProperty` khi phù hợp.

Ví dụ chạy thử configuration cache:

```bash
./gradlew build --configuration-cache
```

Nếu Gradle báo task hoặc build script chưa tương thích, đọc thông báo cụ thể và điều chỉnh cách truy cập dữ liệu. Không phải mọi plugin hoặc task cũ đều hỗ trợ configuration cache ngay lập tức.

## 12. Không nhầm profile môi trường với source set hoặc variant

Một số dự án có `main`, `test`, `integrationTest` hoặc các variant do plugin tạo ra. Đây là các cấu trúc tổ chức mã nguồn và sản phẩm build, không đồng nghĩa với môi trường triển khai như local, staging hay production.

| Khái niệm | Ví dụ | Mục đích |
|---|---|---|
| Environment | `local`, `staging`, `production` | Giá trị cấu hình cho một nơi chạy hoặc triển khai |
| Source set | `main`, `test` | Tổ chức source/resource và classpath trong Gradle |
| Build variant | Một biến thể artifact do plugin hoặc mô hình build định nghĩa | Tạo sản phẩm khác nhau theo thuộc tính build |
| Task | `compileJava`, `test`, `jar` | Thực hiện một công việc trong build |

Không nên tạo source set riêng cho staging và production chỉ vì endpoint khác nhau. Source set phù hợp khi có mã nguồn hoặc classpath thực sự khác nhau. Nếu chỉ khác giá trị cấu hình, property hoặc runtime configuration thường đơn giản hơn.

## 13. Quy trình triển khai cấu hình đa môi trường

Khi đưa tham số hóa vào một dự án, có thể thực hiện theo các bước:

1. **Liệt kê các môi trường cần hỗ trợ:** xác định local, CI, staging, production và mục đích từng môi trường.
2. **Phân loại giá trị:** xác định giá trị thuộc build-time hay runtime; đánh dấu secret và dữ liệu không nhạy cảm.
3. **Chọn nguồn cấu hình:** project property, environment variable, system property, file cấu hình hoặc secret store.
4. **Đặt mặc định hợp lý:** ví dụ local cho phát triển, nhưng không dùng mặc định production cho thao tác có tác dụng phụ.
5. **Xác thực đầu vào:** từ chối tên môi trường hoặc giá trị không hợp lệ với thông báo rõ ràng.
6. **Tái sử dụng task và logic chung:** chỉ thay đổi tham số, không nhân bản toàn bộ quy trình.
7. **Khai báo input/output:** bảo đảm Gradle biết cấu hình nào ảnh hưởng đến output và cache.
8. **Bảo vệ secret:** lấy credential từ CI hoặc môi trường an toàn, không commit và không ghi log.
9. **Kiểm thử từng môi trường:** chạy cùng task với các giá trị khác nhau và xác nhận output/behavior đúng.
10. **Xem xét khả năng promote artifact:** nếu có thể, build một artifact rồi cung cấp cấu hình runtime theo môi trường triển khai.

## 14. Ví dụ sử dụng cùng một quy trình cho local và CI

Giả sử dự án có task kiểm tra metadata và chạy test. Máy lập trình viên dùng `local`; pipeline truyền `ci`. Build script có thể được tổ chức như sau:

```groovy
plugins {
    id 'java'
}

def targetEnvironment = providers.gradleProperty('targetEnvironment')
    .orElse('local')

def strictChecks = targetEnvironment.map { it == 'ci' }

tasks.register('verifyEnvironmentConfiguration') {
    inputs.property('targetEnvironment', targetEnvironment)
    inputs.property('strictChecks', strictChecks)

    doLast {
        println "Environment: ${targetEnvironment.get()}"

        if (strictChecks.get()) {
            println 'Running strict CI checks'
            // Bật các kiểm tra cần thiết cho CI.
        } else {
            println 'Running local checks'
            // Cùng quy trình, với mức kiểm tra phù hợp.
        }
    }
}

tasks.named('check') {
    dependsOn(tasks.named('verifyEnvironmentConfiguration'))
}
```

Chạy local:

```bash
./gradlew check
```

Chạy CI:

```bash
./gradlew check -PtargetEnvironment=ci
```

Pipeline có thể truyền `targetEnvironment=ci` qua project property hoặc biến môi trường `ORG_GRADLE_PROJECT_targetEnvironment`. Cả hai lần chạy dùng cùng build script và cùng task lifecycle. Task đọc giá trị đầu vào và thực hiện phần cấu hình phù hợp.

Trong dự án thật, các kiểm tra CI nghiêm ngặt nên được biểu diễn bằng task riêng có output/input rõ ràng khi phù hợp, thay vì chỉ in thông báo. Ví dụ này tập trung minh họa cách một tham số điều khiển hành vi mà không cần nhân bản pipeline.

## 15. Những lỗi thường gặp khi tham số hóa

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Gradle luôn dùng giá trị mặc định | Tên property sai, truyền sai cú pháp hoặc đọc nhầm nguồn | Kiểm tra `-P`, tên biến môi trường và Provider API |
| Môi trường staging bị chọn thành `stagin` | Không xác thực giá trị đầu vào | Dùng danh sách giá trị được phép và báo lỗi rõ ràng |
| Task không chạy lại khi property thay đổi | Giá trị cấu hình chưa được khai báo là task input | Thêm `inputs.property` hoặc `@Input` |
| Mỗi môi trường có một bản build script riêng | Quy trình và cấu hình bị trộn lẫn | Tách logic chung khỏi tham số môi trường |
| Secret xuất hiện trong log | In property/environment hoặc truyền secret trên command line | Dùng secret store và tránh log giá trị bí mật |
| Artifact production chứa endpoint staging | Giá trị môi trường bị nhúng vào output không đúng mục đích | Phân biệt build-time và runtime configuration |
| Configuration cache không dùng được | Truy cập trạng thái môi trường trực tiếp trong configuration phase | Ưu tiên Provider API và xử lý theo chẩn đoán Gradle |
| Máy cá nhân build được nhưng CI thiếu cấu hình | Giá trị chỉ tồn tại trong shell hoặc file local | Khai báo biến/project property trong CI job |
| Profile Maven làm thay đổi quá nhiều bước | Plugin executions hoặc dependency bị sao chép giữa các profile | Đưa phần chung ra ngoài profile, chỉ giữ khác biệt cần thiết |

## 16. Những nguyên tắc cần ghi nhớ

- Giữ một quy trình build chung và truyền giá trị khác nhau từ bên ngoài.
- Dùng `providers.gradleProperty`, `providers.environmentVariable` hoặc `providers.systemProperty` để đọc đúng loại cấu hình.
- Đặt mặc định rõ ràng và xác thực tên môi trường trước khi thực hiện thao tác quan trọng.
- Khai báo property ảnh hưởng đến output là task input để Gradle kiểm tra up-to-date và cache chính xác.
- Tách build-time configuration khỏi runtime configuration; ưu tiên dùng cùng một artifact nếu khác biệt chỉ là endpoint hoặc credential khi ứng dụng chạy.
- Không commit hoặc ghi log secret; lấy credential từ hệ thống quản lý bí mật của CI/môi trường triển khai.
- Không nhân bản task graph hoặc build script chỉ vì vài giá trị khác nhau.
- Chỉ tạo nhánh quy trình khi môi trường thực sự có công việc khác biệt.
- Với Maven, giữ plugin execution chung và dùng property/profile cho những khác biệt cần thiết.

Tham số hóa giúp build script mô tả quy trình một lần, còn môi trường cung cấp dữ liệu phù hợp cho lần chạy đó. Khi nguồn cấu hình, mặc định, input/output và ranh giới secret được xác định rõ, dự án có thể hỗ trợ nhiều môi trường mà không tạo ra nhiều bản sao của cùng một quy trình.
