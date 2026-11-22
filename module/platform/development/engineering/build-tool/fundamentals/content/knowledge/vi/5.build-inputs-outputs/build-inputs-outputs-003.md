# Đầu vào tường minh và đầu vào ẩn từ môi trường máy

Một build task có thể được xem như một hàm biến đầu vào thành đầu ra. Nếu cùng một tập đầu vào được cung cấp, task nên tạo ra cùng một kết quả. Build tool dựa trên nguyên tắc này để biết khi nào có thể bỏ qua một task đã hoàn thành hoặc tái sử dụng kết quả từ build cache.

Vấn đề xuất hiện khi task đọc thêm dữ liệu từ môi trường máy mà cấu hình build không khai báo. Gradle có thể thấy các đầu vào đã khai báo vẫn giữ nguyên và kết luận task còn hợp lệ, trong khi kết quả thực tế đã phải thay đổi. Đây là lỗi do **đầu vào ẩn (hidden input)**. Hiểu và khai báo đúng đầu vào giúp build có thể dự đoán, chạy nhanh và cho kết quả nhất quán giữa máy cá nhân với CI.

## 1. Đầu vào và đầu ra quyết định trạng thái của task

### 1.1. Mô hình đầu vào và đầu ra

Hãy hình dung một task tạo file cấu hình từ template:

```text
Template + tên môi trường
             |
             v
      GenerateConfig
             |
             v
       config.txt
```

Task có hai đầu vào: nội dung template và tên môi trường. Đầu ra là file `config.txt`. Có thể biểu diễn mối quan hệ này bằng công thức:

\[
\text{output} = f(\text{template}, \text{environment})
\]

Nếu template hoặc tên môi trường thay đổi, đầu ra có thể thay đổi. Nếu cả hai giữ nguyên và task có tính xác định, kết quả cũ vẫn có thể được sử dụng.

Trong Gradle, task cần mô tả các dữ liệu mà nó đọc và các file mà nó tạo ra. Những dữ liệu được mô tả trong task được gọi là **đầu vào tường minh (declared inputs)**. File hoặc thư mục được tạo và quản lý bởi task được khai báo là **đầu ra (outputs)**.

### 1.2. Gradle dùng đầu vào và đầu ra để làm gì?

Gradle chụp trạng thái đầu vào và đầu ra của task để quyết định có cần thực thi lại hay không. Khi một task có đầu vào và đầu ra đã khai báo, Gradle có thể so sánh trạng thái hiện tại với trạng thái của lần chạy trước:

- Nếu đầu vào không thay đổi và đầu ra vẫn tồn tại, task có thể được đánh dấu `UP-TO-DATE`.
- Nếu đầu vào thay đổi hoặc đầu ra không còn hợp lệ, task cần được thực thi lại.
- Nếu task được cấu hình để dùng build cache và các điều kiện cache được đáp ứng, Gradle có thể lấy lại đầu ra đã lưu thay vì thực thi task.

Build cache dựa trên khóa được tính từ những yếu tố như implementation của task và trạng thái đầu vào đã chuẩn hóa. Khi tìm thấy kết quả tương ứng, Gradle có thể khôi phục các đầu ra đã lưu. Điều này đặc biệt hữu ích khi nhiều máy hoặc nhiều lần chạy build cần cùng một kết quả.

Điểm quan trọng là Gradle chỉ có thể theo dõi những dữ liệu mà task hoặc plugin khai báo, cùng các thông tin mà Gradle tự quản lý. Nó không tự động hiểu mọi thứ mà một đoạn mã tùy ý đọc từ hệ điều hành, thư mục cá nhân hay mạng Internet.

## 2. Đầu vào tường minh trong Gradle

### 2.1. Khai báo các loại đầu vào

Gradle cung cấp annotation để mô tả loại dữ liệu mà task sử dụng. Một số annotation thường gặp:

| Annotation | Dữ liệu được mô tả | Ví dụ |
|---|---|---|
| `@Input` | Giá trị đơn hoặc giá trị cấu hình ảnh hưởng đến kết quả | Tên môi trường, chế độ xử lý, phiên bản định dạng |
| `@InputFile` | Một file đầu vào | Template, schema, file cấu hình nguồn |
| `@InputFiles` | Tập hợp file đầu vào | Nhiều file dữ liệu cần xử lý |
| `@InputDirectory` | Một thư mục đầu vào | Thư mục chứa template hoặc tài nguyên nguồn |
| `@Classpath` | Classpath dùng để chạy hoặc xử lý | Các thư viện cần cho một công cụ xử lý |
| `@CompileClasspath` | Classpath phục vụ biên dịch | Các kiểu và API cần thiết khi biên dịch |
| `@Nested` | Một đối tượng cấu hình lồng nhau có các thuộc tính đầu vào riêng | Nhóm tùy chọn xử lý |
| `@Optional` | Đánh dấu một thuộc tính đầu vào có thể không được cung cấp | File cấu hình bổ sung tùy chọn |

Các kiểu property như `Property<T>`, `RegularFileProperty`, `DirectoryProperty` và `ConfigurableFileCollection` giúp Gradle quản lý giá trị một cách lười (lazy), có thể kết hợp với provider và kiểm tra trạng thái phù hợp.

Với file đầu vào, cần cân nhắc cách Gradle nhận diện đường dẫn. `@PathSensitive` kết hợp với `PathSensitivity` xác định mức độ đường dẫn ảnh hưởng đến fingerprint:

- `ABSOLUTE`: cả đường dẫn tuyệt đối được tính đến.
- `RELATIVE`: đường dẫn tương đối trong phạm vi được khai báo được tính đến, không phụ thuộc vào vị trí tuyệt đối của project.
- `NAME_ONLY`: chỉ tên file được tính đến.
- `NONE`: chỉ nội dung file được tính đến, đường dẫn không ảnh hưởng.

Chọn mức phù hợp với cách task sử dụng file. Nếu task cần biết cấu trúc đường dẫn tương đối, không nên bỏ qua thông tin đường dẫn. Nếu chỉ xử lý nội dung file và vị trí file không có ý nghĩa, có thể dùng mức chuẩn hóa phù hợp để tăng khả năng tái sử dụng cache.

Với classpath, nên dùng `@Classpath` hoặc `@CompileClasspath` khi đúng mục đích thay vì mô tả cả thư mục JAR như một tập file thông thường. Các annotation này cho phép Gradle chuẩn hóa classpath theo ngữ nghĩa của dependency và tránh làm mất tính tái sử dụng vì những khác biệt không ảnh hưởng đến kết quả.

### 2.2. Khai báo đầu ra

Đầu ra cũng phải được mô tả đầy đủ. Các annotation phổ biến gồm:

| Annotation | Ý nghĩa |
|---|---|
| `@OutputFile` | Task tạo hoặc cập nhật một file |
| `@OutputFiles` | Task tạo một tập hợp file |
| `@OutputDirectory` | Task tạo hoặc quản lý một thư mục đầu ra |

Đầu ra nên nằm trong thư mục `build/` của project nếu đó là artifact được tạo trong quá trình build. Khi chạy `clean`, Gradle có thể xóa các sản phẩm build trong thư mục này theo quy ước của plugin.

Không khai báo nhầm file nguồn là output. Nếu một task vừa đọc vừa ghi đè lên cùng một file, cần xem xét lại thiết kế để tách dữ liệu đầu vào và đầu ra. Việc mô tả sai có thể làm Gradle tính trạng thái task không chính xác.

### 2.3. Ví dụ: task tạo file từ template và tên môi trường

Giả sử dự án có file `src/descriptor.template`:

```text
application.environment=${environment}
application.name=sample-service
```

Ta muốn tạo `build/generated/descriptor.txt`. Nội dung file phụ thuộc vào template và tên môi trường. Có thể khai báo một task như sau trong `build.gradle` (Groovy DSL):

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

@CacheableTask
abstract class GenerateDescriptor extends DefaultTask {
    @Input
    abstract Property<String> getTargetEnvironment()

    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getTemplateFile()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        File template = templateFile.get().asFile
        File output = outputFile.get().asFile

        output.parentFile.mkdirs()
        String content = template.getText('UTF-8')
        output.setText(
            content.replace('${environment}', targetEnvironment.get()),
            'UTF-8'
        )
    }
}

tasks.register('generateDescriptor', GenerateDescriptor) {
    targetEnvironment.set(
        providers.gradleProperty('targetEnv').orElse('dev')
    )
    templateFile.set(
        layout.projectDirectory.file('src/descriptor.template')
    )
    outputFile.set(
        layout.buildDirectory.file('generated/descriptor.txt')
    )
}
```

Trong ví dụ:

- `targetEnvironment` là đầu vào dạng giá trị, được đánh dấu `@Input`.
- `templateFile` là file đầu vào, được đánh dấu `@InputFile`.
- `outputFile` là file đầu ra, được đánh dấu `@OutputFile`.
- `@PathSensitive(PathSensitivity.RELATIVE)` cho biết đường dẫn template được xét theo vị trí tương đối, giúp kết quả không phụ thuộc vào đường dẫn tuyệt đối của thư mục checkout.
- `@CacheableTask` cho phép task tham gia build cache. Điều này chỉ đúng vì task được thiết kế để tạo kết quả xác định từ những đầu vào đã khai báo.

Có thể chạy task với môi trường mặc định:

```bash
./gradlew generateDescriptor
```

Hoặc truyền một giá trị khác bằng Gradle project property:

```bash
./gradlew generateDescriptor -PtargetEnv=staging
```

Khi `targetEnv` thay đổi từ `dev` sang `staging`, giá trị `@Input` thay đổi. Gradle nhận ra task có đầu vào mới và tạo lại file đầu ra tương ứng.

## 3. Đầu vào ẩn từ môi trường máy

### 3.1. Đầu vào ẩn là gì?

Đầu vào ẩn là dữ liệu mà task thực sự sử dụng nhưng không được khai báo trong mô hình đầu vào của task. Dữ liệu đó có thể nằm ngoài project hoặc đến từ trạng thái hiện tại của máy.

Ví dụ, task đọc biến môi trường trực tiếp:

```groovy
@TaskAction
void generate() {
    String environment = System.getenv('APP_ENV') ?: 'dev'
    // Dùng environment để tạo file đầu ra
}
```

Gradle nhìn thấy mã nguồn task, nhưng nếu `APP_ENV` không được biểu diễn thành một thuộc tính `@Input`, trạng thái biến môi trường không trở thành đầu vào được khai báo của task. Khi giá trị biến môi trường thay đổi, Gradle có thể vẫn thấy các đầu vào đã khai báo không đổi và đánh dấu task `UP-TO-DATE`, hoặc tìm thấy một cache entry được tạo từ giá trị môi trường trước đó.

Đây là lý do một task có thể cho kết quả đúng trên máy lập trình viên nhưng sai trên CI, hoặc đúng ở lần chạy đầu rồi giữ kết quả cũ sau khi môi trường thay đổi.

### 3.2. Những nguồn đầu vào ẩn thường gặp

| Nguồn dữ liệu | Ví dụ | Rủi ro nếu không được khai báo |
|---|---|---|
| Biến môi trường | `APP_ENV`, `LANG`, `PATH`, `JAVA_HOME` | Kết quả phụ thuộc vào cấu hình shell hoặc máy chạy |
| System property | `user.timezone`, `file.encoding`, thuộc tính truyền bằng `-D` | Cùng mã nguồn nhưng kết quả khác giữa các lần chạy |
| Thời gian hệ thống | `new Date()`, `Instant.now()` | Nội dung file thay đổi theo thời điểm thực thi |
| Locale và timezone | `Locale.getDefault()`, `TimeZone.getDefault()` | Định dạng số, ngày tháng hoặc văn bản khác nhau |
| Hệ điều hành và kiến trúc | Windows/Linux, x86_64/ARM64 | Đường dẫn, lệnh và kết quả phụ thuộc nền tảng |
| Công cụ cài trên máy | JDK, Node.js, compiler hoặc CLI lấy từ `PATH` | Phiên bản công cụ khác nhau làm thay đổi đầu ra |
| Thư mục người dùng | `user.home`, file trong thư mục home | Build phụ thuộc vào cấu hình riêng của tài khoản |
| Thư mục làm việc | `user.dir`, đường dẫn checkout | Kết quả hoặc cache phụ thuộc vị trí project |
| Dữ liệu bên ngoài | HTTP API, database, file nằm ngoài project | Nội dung có thể thay đổi mà fingerprint không đổi |
| Trạng thái Git | Branch, commit id, tag | Artifact thay đổi theo trạng thái repository |
| Số ngẫu nhiên | `Random`, UUID ngẫu nhiên | Cùng đầu vào nhưng tạo ra đầu ra khác nhau |

Danh sách này không có nghĩa mọi task đều phải khai báo lại tất cả các giá trị trên. Plugin hoặc task tích hợp có thể đã mô hình hóa một số đầu vào, ví dụ Java compile task quản lý compiler và classpath theo cấu hình toolchain. Chỉ cần bổ sung những dữ liệu mà logic riêng của task thực sự sử dụng và chưa được Gradle theo dõi.

### 3.3. Vì sao đầu vào ẩn gây lỗi `UP-TO-DATE`?

Giả sử task tạo file chứa tên môi trường bằng cách đọc `APP_ENV` trực tiếp trong action:

```text
Lần chạy thứ nhất:
APP_ENV=dev
Đầu vào được khai báo: template-v1
Đầu ra: environment=dev

Lần chạy thứ hai:
APP_ENV=prod
Đầu vào được khai báo: template-v1
Đầu ra đúng cần có: environment=prod
```

Vì `APP_ENV` bị bỏ sót, Gradle chỉ nhìn thấy `template-v1` vẫn giữ nguyên và file đầu ra trước đó vẫn tồn tại. Task có thể bị bỏ qua, để lại nội dung `environment=dev` dù lần chạy hiện tại yêu cầu `prod`.

Vấn đề nghiêm trọng hơn khi dùng build cache. Nếu cache key không chứa dữ liệu ảnh hưởng đến kết quả, hai môi trường khác nhau có thể dùng chung một cache entry. Gradle có thể khôi phục đầu ra đã tạo trong môi trường trước, dù đầu ra đó không phù hợp với môi trường hiện tại.

Một task có đầu vào khai báo đầy đủ cần bảo đảm quan hệ sau:

```text
Mọi dữ liệu ảnh hưởng đến kết quả
              |
              v
      Được mô hình hóa thành input
              |
              v
       Task input fingerprint
              |
              v
       UP-TO-DATE / cache
              |
              v
      Đầu ra đúng với đầu vào hiện tại
```

## 4. Đưa dữ liệu môi trường vào mô hình đầu vào

### 4.1. Dùng Provider thay vì đọc trực tiếp trong task action

Gradle cung cấp `ProviderFactory` để lấy giá trị từ project property, system property và biến môi trường. Ta có thể gắn provider vào một property được đánh dấu `@Input`.

Ví dụ, nếu CI cung cấp `APP_ENV`, có thể cấu hình:

```groovy
tasks.register('generateDescriptor', GenerateDescriptor) {
    targetEnvironment.set(
        providers.environmentVariable('APP_ENV').orElse('dev')
    )
    templateFile.set(
        layout.projectDirectory.file('src/descriptor.template')
    )
    outputFile.set(
        layout.buildDirectory.file('generated/descriptor.txt')
    )
}
```

Ở đây, biến môi trường được chuyển thành giá trị của `targetEnvironment`. Vì property có `@Input`, giá trị được Gradle theo dõi như một phần của trạng thái task. Nếu `APP_ENV` thay đổi, Gradle có thể phát hiện thay đổi đó.

Một số nguồn giá trị thường dùng:

```groovy
// Gradle project property: -PtargetEnv=staging
providers.gradleProperty('targetEnv')

// Biến môi trường của tiến trình
providers.environmentVariable('APP_ENV')

// JVM system property: -Duser.timezone=UTC
providers.systemProperty('user.timezone')
```

Có thể dùng `orElse(...)` để đặt giá trị mặc định. Hãy chọn mặc định có ý nghĩa và thống nhất giữa local với CI; không nên âm thầm dùng một giá trị mặc định khiến build tạo nhầm cấu hình triển khai.

### 4.2. Dùng Gradle property cho cấu hình build

Với giá trị cấu hình không bí mật, Gradle project property thường là một lựa chọn dễ kiểm soát. Giá trị có thể đến từ `gradle.properties`, tham số `-P` hoặc cơ chế cấu hình của CI.

Ví dụ:

```properties
# gradle.properties
targetEnv=dev
```

Trong CI, có thể ghi đè bằng lệnh:

```bash
./gradlew generateDescriptor -PtargetEnv=staging
```

Lợi ích là lệnh build cho thấy rõ cấu hình nào được sử dụng. Khi cần điều tra một artifact, nhóm có thể kiểm tra tham số build thay vì suy đoán giá trị ẩn từ shell của máy.

### 4.3. Cố định toolchain và phiên bản công cụ

Nếu task phụ thuộc vào JDK, compiler hoặc một công cụ ngoài, hãy dùng cơ chế toolchain hoặc plugin phù hợp để chọn công cụ một cách có chủ đích.

Ví dụ cấu hình Java toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Toolchain giúp Gradle lựa chọn JDK theo phiên bản yêu cầu thay vì phụ thuộc hoàn toàn vào `JAVA_HOME` hoặc JDK mặc định của shell. Các task Java tích hợp có thể sử dụng thông tin toolchain để quản lý đầu vào compiler. Với task tự viết gọi một chương trình bên ngoài, cần xem xét cách khai báo executable, phiên bản và các tham số có ảnh hưởng đến kết quả.

Không nên chỉ ghi nhận đường dẫn `PATH` rồi cho rằng đã khóa được phiên bản công cụ. Hai máy có thể có cùng tên lệnh nhưng thực thi hai phiên bản binary khác nhau. Nếu phiên bản công cụ ảnh hưởng đến artifact, hãy quản lý phiên bản công cụ bằng toolchain, plugin hoặc một dependency có thể xác định và kiểm tra được.

### 4.4. Xử lý thời gian, locale và số ngẫu nhiên

Một task tạo tài liệu có timestamp hiện tại sẽ cho kết quả khác nhau ở mỗi lần chạy. Có ba cách tiếp cận tùy mục đích:

- Nếu timestamp không cần thiết, bỏ nó khỏi artifact để kết quả có thể tái lập.
- Nếu timestamp phải được giữ lại, truyền nó thành một `@Input` rõ ràng, chẳng hạn một mốc thời gian do CI cung cấp. Khi giá trị thay đổi, task sẽ được xem là có đầu vào mới.
- Nếu cần một build tái lập từ cùng một mã nguồn, dùng một nguồn thời gian cố định được quản lý trong quy trình phát hành, thay vì đọc đồng hồ máy ở bên trong task.

Locale và timezone cũng nên được cố định nếu định dạng đầu ra phải nhất quán. Với số ngẫu nhiên, truyền seed thành `@Input` để cùng seed tạo cùng chuỗi kết quả. Nếu mỗi lần chạy cần kết quả mới, task phải thể hiện rõ tính chất đó và không giả vờ rằng đầu ra có thể tái sử dụng từ cache cũ.

### 4.5. File bên ngoài project và dữ liệu từ mạng

Nếu task đọc file ở ngoài thư mục project, file đó vẫn là đầu vào dù không nằm trong `src/`. Hãy khai báo file bằng `@InputFile` hoặc `@InputFiles` và cung cấp đúng đường dẫn. Cần cân nhắc path sensitivity để fingerprint phản ánh chính xác ý nghĩa của đường dẫn.

Với dữ liệu lấy từ HTTP API hoặc database, nội dung phản hồi có thể thay đổi dù URL và mã nguồn không đổi. Có thể tách quy trình thành hai phần:

1. Một bước lấy dữ liệu có phiên bản hoặc checksum xác định, lưu thành file đầu vào.
2. Một task xử lý file đã lấy, khai báo file đó là input và tạo đầu ra xác định.

Cách này giúp phần xử lý dữ liệu có thể dùng incremental build và build cache. Nếu task trực tiếp truy vấn một dịch vụ luôn thay đổi, hãy coi đó là một thao tác bên ngoài có trạng thái riêng, không mặc định rằng nó là task thuần có thể cache an toàn.

## 5. Những trường hợp không nên cache hoặc đánh dấu `UP-TO-DATE`

Không phải mọi task đều tạo ra kết quả thuần từ các file và property. Một số task gửi thông báo, triển khai ứng dụng, cập nhật database, phát hành artifact hoặc thay đổi trạng thái của hệ thống bên ngoài. Những thao tác này có tác dụng phụ mà Gradle không thể khôi phục chỉ bằng cách sao chép một thư mục output.

Với task có tác dụng phụ:

- Không đánh dấu task là cacheable nếu việc khôi phục file đầu ra không tái tạo được tác dụng phụ.
- Nếu thao tác cần được thực hiện mỗi lần được gọi, có thể tắt kiểm tra up-to-date bằng `outputs.upToDateWhen { false }`.
- Tách việc tạo artifact xác định khỏi việc triển khai hoặc gửi dữ liệu ra ngoài.
- Chỉ thực hiện thao tác bên ngoài khi người dùng hoặc pipeline yêu cầu rõ ràng.

Ví dụ, task tạo JAR là một ứng viên phù hợp cho incremental build và build cache khi đầu vào được khai báo đầy đủ. Task triển khai JAR lên máy chủ cần được xem là thao tác có tác dụng phụ; chỉ khôi phục một file log từ cache không thể thay thế việc triển khai thật.

### 5.1. Không dùng `@Internal` để che một đầu vào ảnh hưởng đến kết quả

`@Internal` dùng cho thuộc tính không tham gia vào fingerprint đầu vào/đầu ra của task. Nếu một giá trị thực sự ảnh hưởng đến nội dung được tạo ra, đánh dấu nó là `@Internal` sẽ làm mất thông tin mà Gradle cần để kiểm tra tính hợp lệ của đầu ra.

Ví dụ, nếu `targetEnvironment` quyết định nội dung file, nó phải được mô hình hóa như `@Input`. Không nên đánh dấu `@Internal` chỉ để tránh task chạy lại.

Thông tin bí mật như token hoặc mật khẩu cần được xử lý riêng. Không ghi bí mật vào file đầu ra, log hay artifact có thể chia sẻ. Nếu bí mật chỉ dùng để xác thực một thao tác bên ngoài và không làm thay đổi nội dung artifact, có thể thiết kế bước xác thực/triển khai riêng, không cache và không đánh dấu up-to-date. Nếu giá trị bí mật thực sự quyết định nội dung đầu ra, cần xem lại thiết kế dữ liệu và bảo mật trước khi biến nó thành một input được fingerprint hoặc lưu trong cache.

## 6. Phân biệt đầu vào do task tự khai báo và đầu vào plugin đã quản lý

Không cần tự viết lại mọi chi tiết môi trường vào từng task. Các plugin Gradle chuẩn đã mô hình hóa nhiều thông tin cần thiết. Chẳng hạn:

- Java compile task quản lý source files, compile classpath, compiler options và thông tin compiler/toolchain theo cấu hình tương ứng.
- Task xử lý resource quản lý tập resource và các quy tắc lọc được cấu hình.
- Dependency configurations quản lý các artifact được phân giải từ repository.
- Các task do plugin cung cấp có thể đã khai báo output directory hoặc output file.

Khi dùng task có sẵn, hãy đọc tài liệu của task và plugin trước khi bổ sung input hoặc output. Khi viết task riêng, hãy liệt kê mọi dữ liệu mà action thực sự đọc. Tránh khai báo dư thừa những giá trị không ảnh hưởng đến kết quả vì chúng làm task chạy lại không cần thiết và giảm khả năng dùng chung cache.

## 7. Điều tra một task có đầu vào ẩn

Khi thấy task không chạy lại dù kết quả đáng lẽ phải thay đổi, hoặc máy CI nhận được output khác máy cá nhân, hãy điều tra theo thứ tự:

1. Xác định task tạo ra file hoặc tác dụng phụ đang gặp vấn đề.
2. Kiểm tra task khai báo những input và output nào.
3. Tìm trong task action và các hàm được gọi xem có đọc `System.getenv`, `System.getProperty`, thời gian hệ thống, locale, file ngoài project, trạng thái Git hoặc dữ liệu mạng không.
4. Xác định plugin có tự quản lý dữ liệu đó hay chưa.
5. Nếu dữ liệu ảnh hưởng đến output và chưa được quản lý, chuyển nó thành property có annotation phù hợp hoặc thiết kế lại task để loại bỏ sự phụ thuộc.
6. Chạy lại task và kiểm tra output khi giá trị input thay đổi.

Một số lệnh hỗ trợ điều tra:

```bash
# Hiển thị thông tin chi tiết về các task
./gradlew generateDescriptor --info

# Bắt buộc chạy lại task để so sánh hành vi
./gradlew generateDescriptor --rerun-tasks

# Tắt build cache trong một lần chạy để khoanh vùng vấn đề cache
./gradlew generateDescriptor --no-build-cache

# Xóa đầu ra build rồi tạo lại
./gradlew clean generateDescriptor
```

`--rerun-tasks` và `--no-build-cache` là công cụ chẩn đoán. Chúng có thể giúp xác nhận rằng kết quả cũ đến từ trạng thái up-to-date hoặc cache, nhưng không sửa được mô hình input bị thiếu. Sau khi điều tra, cần sửa khai báo đầu vào hoặc cách task lấy dữ liệu.

## 8. Nguyên tắc xây dựng task có thể tái lập

Một task tốt nên tuân theo các nguyên tắc sau:

- **Khai báo mọi dữ liệu ảnh hưởng đến kết quả.** Giá trị, file, classpath và cấu hình môi trường phải được mô hình hóa rõ ràng nếu task sử dụng chúng.
- **Khai báo đầy đủ đầu ra.** Gradle cần biết task tạo file hoặc thư mục nào để quản lý trạng thái và dọn dẹp.
- **Giữ action xác định.** Cùng một tập input nên tạo cùng một output. Tránh đọc đồng hồ, số ngẫu nhiên hoặc dịch vụ thay đổi liên tục nếu không có chủ đích.
- **Quản lý công cụ.** Cố định JDK/toolchain và phiên bản công cụ ngoài khi chúng ảnh hưởng đến artifact.
- **Chọn quy tắc chuẩn hóa file phù hợp.** Đường dẫn tuyệt đối, tương đối hay chỉ nội dung file chỉ nên được tính đến theo đúng ý nghĩa của input.
- **Tách tác vụ có tác dụng phụ.** Tạo artifact và triển khai artifact là hai công việc có đặc tính khác nhau.
- **Không cache dữ liệu nhạy cảm.** Bí mật không nên trở thành nội dung của artifact hoặc được phát tán qua build cache.
- **Kiểm tra trên CI.** Dùng cùng phiên bản công cụ và cùng quy tắc cấu hình để phát hiện sự phụ thuộc vào máy cá nhân.

## 9. Bài tập tình huống

Một task `generateVersionInfo` tạo file `build/generated/version.txt`. Trong action, task đọc:

```groovy
String branch = 'git branch --show-current'.execute().text.trim()
String user = System.getProperty('user.name')
String timestamp = new Date().toString()
```

Sau đó ghi ba giá trị này vào file. Hãy phân tích:

1. Những dữ liệu nào là đầu vào thực sự của task?
2. Dữ liệu nào có thể thay đổi giữa hai máy dù mã nguồn giống nhau?
3. Nếu branch thay đổi nhưng task vẫn được đánh dấu `UP-TO-DATE`, nguyên nhân có thể là gì?
4. Nếu timestamp thay đổi ở mọi lần chạy, task có thể tận dụng up-to-date check và build cache hiệu quả không?
5. Có thể thay `user.name` bằng một thuộc tính cấu hình tường minh không?
6. Nếu file này chỉ phục vụ hiển thị thông tin build, có nên đưa tên người dùng cá nhân vào artifact phân phối không?

Một hướng thiết kế tốt là xác định rõ giá trị nào thực sự cần xuất hiện trong artifact. Branch hoặc commit id có thể được cung cấp từ CI dưới dạng project property hoặc biến môi trường rồi đưa vào `@Input`. Timestamp có thể lấy từ một mốc phát hành cố định nếu cần build tái lập. Tên người dùng cá nhân thường không cần thiết trong artifact và nên được loại bỏ.

Khi đọc hoặc viết một Gradle task, hãy thử diễn đạt nó thành câu: “Task này đọc những dữ liệu nào, tạo ra những file nào, và có phụ thuộc vào trạng thái bên ngoài nào?”. Nếu có dữ liệu ảnh hưởng đến kết quả nhưng không thể chỉ ra nơi nó được khai báo, đó là dấu hiệu cần xem lại mô hình input/output trước khi bật incremental build hoặc build cache.
