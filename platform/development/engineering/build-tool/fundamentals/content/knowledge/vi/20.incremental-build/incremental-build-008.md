# Tính khả chuyển của cache giữa thư mục, máy và hệ điều hành

Build cache giúp tái sử dụng output của task khi các đầu vào tương đương. Lợi ích lớn nhất xuất hiện khi một task có thể dùng lại kết quả từ lần build trước, kể cả khi source được checkout ở thư mục khác hoặc build chạy trên một máy khác. Tuy nhiên, cache chỉ an toàn khi task được thiết kế để kết quả không phụ thuộc vào những khác biệt không được khai báo.

Ví dụ, hai lập trình viên checkout cùng commit vào:

```text
Máy A: /home/linh/work/order-service
Máy B: /workspace/ci/job-42/order-service
```

Nếu task chỉ đọc source và tạo một file index chứa đường dẫn tương đối, kết quả có thể giống nhau và được chia sẻ qua build cache. Nếu task ghi đường dẫn tuyệt đối của workspace vào output, hai lần build sẽ tạo nội dung khác nhau. Nếu task biên dịch native library, output còn có thể phụ thuộc hệ điều hành và kiến trúc CPU.

Tính khả chuyển của cache phụ thuộc vào ba điều:

- **Input được mô tả đầy đủ:** mọi giá trị ảnh hưởng đến output đều phải được khai báo.
- **Input được chuẩn hóa đúng:** đường dẫn và nội dung file được fingerprint theo mức cần thiết, không phụ thuộc vị trí checkout nếu vị trí đó không có ý nghĩa.
- **Output thực sự tương thích:** task không tạo output phụ thuộc máy/hệ điều hành mà cache key lại không phân biệt các môi trường đó.

## 1. Build cache là gì?

Gradle build cache lưu output của các task có thể cache. Khi một task được yêu cầu chạy, Gradle tính toán key dựa trên task implementation, action, input properties, file inputs đã chuẩn hóa và các thông tin liên quan. Nếu cache có output cho key đó, Gradle có thể khôi phục output thay vì thực thi lại task.

Luồng khái quát:

```text
Task được yêu cầu
       |
       v
Thu thập task implementation và input
       |
       v
Fingerprint / build cache key
       |
       v
Tìm output trong cache
       |
       +---- Có entry ----> Khôi phục output (FROM-CACHE)
       |
       +---- Không có ----> Thực thi task
                               |
                               v
                         Lưu output vào cache
```

Cache key chỉ hữu ích nếu phản ánh đúng mọi thứ có thể làm output thay đổi. Nếu task âm thầm đọc hostname, biến môi trường, đường dẫn tuyệt đối hoặc file ngoài mà không khai báo, Gradle có thể dùng lại output cũ cho một môi trường khác và tạo kết quả sai.

### 1.1. `UP-TO-DATE` khác `FROM-CACHE`

Gradle có hai cơ chế thường bị nhầm:

| Trạng thái | Ý nghĩa |
|---|---|
| `UP-TO-DATE` | Output hiện có trong project vẫn khớp với input đã ghi nhận; task không cần chạy lại |
| `FROM-CACHE` | Output được khôi phục từ build cache vì cache key phù hợp |
| `SUCCESS` | Task đã thực thi và hoàn thành thành công trong lần chạy này |
| `NO-SOURCE` | Task không có source input phù hợp để xử lý |

`UP-TO-DATE` thường dùng output đã có trong workspace hiện tại. `FROM-CACHE` có thể lấy output từ cache cục bộ hoặc cache từ xa, kể cả khi workspace mới chưa có output.

Lệnh `clean` xóa output trong thư mục build của project, nhưng không xóa toàn bộ Gradle build cache trong Gradle User Home. Sau `clean`, task vẫn có thể được khôi phục từ cache.

## 2. Phân biệt các loại cache của Gradle

Gradle có nhiều loại cache phục vụ các mục đích khác nhau.

| Loại cache | Lưu gì? | Có chia sẻ output task giữa workspace/máy không? |
|---|---|---|
| Build cache | Output của task cacheable | Có thể, qua local cache dùng chung hoặc remote build cache |
| Dependency cache | Metadata và artifact dependency đã phân giải | Có thể tái sử dụng trong Gradle User Home của máy; CI cũng có thể lưu/khôi phục thư mục này |
| Configuration cache | Trạng thái configuration để tránh cấu hình lại build | Không phải cache output task; không thay thế remote build cache |
| Wrapper distribution cache | Bản Gradle distribution đã tải | Có thể tái sử dụng trên máy có cùng Gradle User Home |
| Project `.gradle/` state | Trạng thái build riêng của project | Thường gắn với project/build và không phải nơi chia sẻ output task tổng quát |

Trong bài này, “cache khả chuyển” chủ yếu nói về Gradle build cache. Dependency cache có thể giúp không tải lại JAR, nhưng không có nghĩa task compile/package được tái sử dụng. Configuration cache lưu trạng thái cấu hình, không lưu output của `compileJava` hay task archive.

## 3. Cache giữa các thư mục checkout

Một task có thể chạy ở thư mục khác nhưng vẫn tạo cùng output nếu nó chỉ phụ thuộc vào nội dung và cấu trúc tương đối của input.

Ví dụ cùng source tree:

```text
Workspace A:
/home/linh/work/order-service/src/main/resources/app.yml

Workspace B:
/agent/work/order-service/src/main/resources/app.yml
```

Nếu task chỉ cần biết file `src/main/resources/app.yml` và nội dung của nó, đường dẫn tương đối từ project root giống nhau. Task có thể được thiết kế để cache key không phụ thuộc absolute workspace path.

Ngược lại, nếu task ghi `/home/linh/work/order-service` vào output hoặc dùng absolute path làm input có ý nghĩa, cache entry có thể không dùng được ở workspace khác hoặc thậm chí được dùng sai nếu đường dẫn không được fingerprint phù hợp.

### 3.1. Không để absolute path trở thành nội dung output

Ví dụ task không khả chuyển:

```groovy
tasks.register('writeBuildLocation') {
    def outputFile = layout.buildDirectory.file('generated/location.txt')
    outputs.file(outputFile)

    doLast {
        def target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.text = project.projectDir.absolutePath
    }
}
```

Task trên tạo output khác nhau ở từng checkout path. Nếu mục tiêu chỉ là định danh project, hãy ghi dữ liệu logic ổn định:

```groovy
tasks.register('writeBuildLocation') {
    def outputFile = layout.buildDirectory.file('generated/location.txt')
    outputs.file(outputFile)

    doLast {
        def target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.text = project.path + '\n'
    }
}
```

`project.path` là định danh logic của project trong build, không phải vị trí filesystem. Nếu task thực sự cần đường dẫn tuyệt đối để thực hiện một thao tác, hãy dùng nó nội bộ nhưng tránh ghi vào output hoặc khai báo nó như input nếu output phụ thuộc vào nó. Việc khai báo absolute path sẽ làm cache phụ thuộc vị trí đó và giảm khả năng chia sẻ giữa workspace.

### 3.2. Dùng project-relative path

Khi tạo danh sách file, hãy chuyển đường dẫn thành relative path từ một root đã xác định:

```groovy
def root = layout.projectDirectory.dir('src/main/resources').asFile

def relativeNames = fileTree(root).files.collect { file ->
    root.toPath().relativize(file.toPath()).toString()
}
```

Nếu nội dung output phải giống giữa Windows và Linux, cần chuẩn hóa dấu phân cách thành `/` trước khi ghi. `Path.toString()` dùng dấu phân cách của hệ điều hành, vì vậy không nên ghi trực tiếp nếu định dạng output yêu cầu thống nhất.

## 4. Path sensitivity và chuẩn hóa file input

Gradle cần fingerprint file input để xác định task có thể tái sử dụng output hay không. Với file input, đường dẫn có thể là một phần của fingerprint. Annotation `@PathSensitive` xác định Gradle nên xem xét đường dẫn ở mức nào.

Các lựa chọn chính:

| Path sensitivity | Gradle xem xét gì? | Khi nào dùng? |
|---|---|---|
| `ABSOLUTE` | Đường dẫn tuyệt đối cùng nội dung file | Khi vị trí tuyệt đối thực sự ảnh hưởng kết quả |
| `RELATIVE` | Đường dẫn tương đối với root input cùng nội dung file | Khi cấu trúc tương đối có ý nghĩa nhưng checkout root có thể đổi |
| `NAME_ONLY` | Tên file và nội dung, bỏ qua các thư mục cha | Khi chỉ tên file có ý nghĩa và tên không bị trùng theo cách gây mơ hồ |
| `NONE` | Nội dung file, không xem đường dẫn là input | Khi task chỉ quan tâm bytes và không phụ thuộc vị trí/tên file |

Không nên chọn `NONE` chỉ để tăng cache hit nếu task thực sự dùng tên hoặc cấu trúc thư mục để quyết định output. Path sensitivity phải mô tả đúng ngữ nghĩa của task.

### 4.1. Dùng `@PathSensitive(PathSensitivity.RELATIVE)`

Ví dụ task cacheable đọc một thư mục resource và tạo index từ đường dẫn tương đối:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

@CacheableTask
abstract class GenerateResourceIndex extends DefaultTask {
    @InputDirectory
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract DirectoryProperty getSourceDirectory()

    @OutputFile
    abstract RegularFileProperty getIndexFile()

    @TaskAction
    void generate() {
        File root = sourceDirectory.get().asFile
        List<String> paths = []

        root.eachFileRecurse { File file ->
            if (file.isFile()) {
                String relative = root.toPath()
                    .relativize(file.toPath())
                    .toString()
                    .replace(File.separatorChar, '/' as char)
                paths.add(relative)
            }
        }

        Collections.sort(paths)

        File target = indexFile.get().asFile
        target.parentFile.mkdirs()
        target.setText(paths.join('\n') + '\n', 'UTF-8')
    }
}

tasks.register('generateResourceIndex', GenerateResourceIndex) {
    sourceDirectory.set(layout.projectDirectory.dir('src/main/resources'))
    indexFile.set(layout.buildDirectory.file('generated/resource-index.txt'))
}
```

Task này:

- Khai báo source directory là input.
- Dùng relative path sensitivity để workspace root không ảnh hưởng fingerprint.
- Khai báo file index là output.
- Sắp xếp danh sách file trước khi ghi.
- Chuẩn hóa dấu phân cách thành `/` và encoding UTF-8.
- Không ghi absolute path hoặc timestamp của máy vào output.

Nếu cùng task implementation và cùng input tree được build ở hai checkout path khác nhau, Gradle có thể dùng lại output từ build cache.

### 4.2. Khi nào cần `ABSOLUTE`?

Một task có thể thực sự cần vị trí tuyệt đối. Ví dụ, task tạo cấu hình cho một công cụ chỉ hoạt động với một installation path cố định hoặc tạo file chứa đường dẫn triển khai cụ thể. Khi vị trí đó ảnh hưởng đến output, hãy khai báo nó là input và dùng path sensitivity phù hợp.

Đổi sang `RELATIVE` trong trường hợp này có thể làm Gradle coi hai input khác nhau là tương đương và khôi phục output sai. Cache hit cao hơn không có ý nghĩa nếu kết quả không đúng.

## 5. Chuẩn hóa classpath input

Task compile hoặc công cụ phân tích bytecode thường nhận một classpath gồm nhiều JAR. Gradle cung cấp annotation chuyên biệt:

- `@Classpath`: fingerprint classpath theo quy tắc chuẩn hóa classpath, phù hợp khi task cần nội dung runtime classpath.
- `@CompileClasspath`: chuẩn hóa classpath theo thông tin có ý nghĩa cho compile, giúp tránh cache miss do thay đổi implementation không ảnh hưởng API compile.

Ví dụ:

```groovy
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.tasks.Classpath

abstract class AnalyzeLibraries extends DefaultTask {
    @Classpath
    abstract ConfigurableFileCollection getLibraries()
}
```

Không nên thay `@Classpath` bằng `@InputFiles` với `ABSOLUTE` chỉ vì dễ viết hơn. Path tuyệt đối của JAR trong Gradle cache có thể khác giữa máy; annotation classpath giúp Gradle áp dụng chuẩn hóa phù hợp với ý nghĩa của classpath.

Nếu task cần phân biệt thứ tự classpath, cần bảo đảm API/annotation và implementation mô tả đúng ngữ nghĩa đó. Không tự sắp xếp classpath nếu thứ tự có thể ảnh hưởng class loading.

## 6. Cache giữa các máy

Local build cache thường nằm trong Gradle User Home của một người dùng. Hai checkout trên cùng máy có thể dùng chung cache cục bộ nếu chúng chạy với cùng Gradle User Home và build cache được bật.

Để chia sẻ giữa nhiều máy hoặc giữa developer và CI, có thể dùng **remote build cache**. Remote cache là dịch vụ lưu output task theo cache key; máy build có thể tải output đã có hoặc đẩy output mới lên nếu được cấp quyền.

```text
Developer A                 CI worker                 Developer B
    |                           |                           |
    | push/read                 | read/push                  | read
    +---------------------------+---------------------------+
                                |
                                v
                       Remote build cache
                         task key -> outputs
```

Remote build cache hữu ích khi nhiều build dùng cùng task implementation và input. Ví dụ, CI đã compile và tạo code generation output; developer checkout cùng revision có thể lấy output đó thay vì thực thi lại task.

### 6.1. Cấu hình remote build cache trong Gradle

Trong `settings.gradle` (Groovy DSL), có thể cấu hình:

```groovy
buildCache {
    local {
        enabled = true
    }

    remote(HttpBuildCache) {
        url = uri('https://cache.example.com/')
        push = System.getenv('CI') != null
    }
}
```

URL trên là ví dụ. Cần thay bằng endpoint build cache tương thích với Gradle và cấu hình authentication/TLS theo dịch vụ thực tế. `push` chỉ cho phép build đẩy entry lên remote cache; build vẫn có thể đọc entry nếu quyền đọc được cấp.

Một chính sách phổ biến:

- CI đáng tin cậy được phép push output đã tạo.
- Máy lập trình viên được phép read để tăng tốc nhưng không nhất thiết được push.
- Job từ fork hoặc pull request không đáng tin cậy không được push vào cache dùng chung của release.

### 6.2. Bật build cache

Có thể bật bằng command line:

```bash
./gradlew build --build-cache
```

Hoặc trong `gradle.properties`:

```properties
org.gradle.caching=true
```

Nếu không bật build cache, Gradle vẫn có up-to-date checking cho task phù hợp, nhưng không sử dụng build cache theo cách thông thường.

### 6.3. Cache remote cần chính sách tin cậy

Remote build cache chứa output được một build khác tạo ra. Nếu một build không đáng tin cậy có quyền push, nó có thể đưa output không an toàn hoặc không đúng vào cache dùng chung. Build khác có thể khôi phục output đó khi cache key khớp.

Vì vậy:

- Chỉ cấp quyền push cho CI/job đáng tin cậy.
- Dùng HTTPS và authentication.
- Tách cache cho branch/release hoặc trust boundary nếu cần.
- Không cấp credential push cho mã từ fork không đáng tin cậy.
- Xác định retention và cách xóa entry sai.
- Theo dõi task nào được cache và nguồn output được khôi phục khi điều tra lỗi.

Cache không thay thế kiểm tra nguồn gốc artifact hoặc dependency verification. Nó là cơ chế tối ưu build; quyền ghi cache cần được bảo vệ như quyền cung cấp đầu vào cho các build khác.

## 7. Điều kiện để task cache được an toàn

Gradle không thể tự biết mọi thứ mà task đọc hoặc mọi tác dụng phụ task thực hiện. Một task chỉ nên cache khi output có thể được xác định từ các input được khai báo.

Task cacheable cần:

- Khai báo đầy đủ input bằng `@Input`, `@InputFile`, `@InputFiles`, `@InputDirectory`, `@Classpath` hoặc property phù hợp.
- Khai báo output bằng `@OutputFile`, `@OutputDirectory` hoặc output property tương ứng.
- Không đọc trạng thái bên ngoài mà không khai báo, như current time, hostname, username hoặc file tùy ý ngoài project.
- Không tạo tác dụng phụ không thể khôi phục chỉ bằng output task, như publish ra server hoặc gửi email.
- Tạo output xác định cho cùng input.
- Dùng path normalization phù hợp.
- Không phụ thuộc thứ tự iteration không xác định.

Task custom có thể được đánh dấu `@CacheableTask` khi thỏa các điều kiện. Nếu task không an toàn để cache, không đánh dấu cacheable hoặc dùng cơ chế tắt caching phù hợp.

### 7.1. Input bị thiếu làm cache trả kết quả sai

Giả sử task tạo file cấu hình dựa trên biến môi trường `DEPLOYMENT_REGION`, nhưng chỉ khai báo source file là input. Khi region thay đổi từ `ap-southeast-1` sang `eu-west-1`, cache key có thể không thay đổi vì Gradle không biết biến đó ảnh hưởng output.

Khi đó, Gradle có thể khôi phục file cấu hình của region trước. Cách đúng là biểu diễn region thành task input:

```groovy
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input

abstract class GenerateRegionConfig extends DefaultTask {
    @Input
    abstract Property<String> getRegion()

    // Các input/output khác...
}
```

Đăng ký task với giá trị provider phù hợp:

```groovy
tasks.register('generateRegionConfig', GenerateRegionConfig) {
    region.set(providers.environmentVariable('DEPLOYMENT_REGION').orElse('local'))
}
```

Nếu region không nên ảnh hưởng đến artifact chung, hãy chuyển cấu hình đó sang runtime thay vì đưa vào task build.

### 7.2. Output không xác định làm cache trở nên nguy hiểm

Nếu task ghi timestamp hiện tại, random UUID hoặc absolute workspace path nhưng các giá trị đó không được khai báo, cache có thể trả output được tạo ở môi trường khác. Kết quả có thể chứa timestamp hoặc đường dẫn không phù hợp với máy hiện tại.

Giải pháp tốt nhất thường là loại bỏ thông tin không cần thiết khỏi output. Nếu giá trị thực sự là một phần hợp đồng output, hãy khai báo nó là input; điều này có thể làm cache key khác nhau giữa các môi trường.

## 8. Khả chuyển giữa các hệ điều hành

Khác biệt giữa Windows, Linux và macOS có thể ảnh hưởng output:

| Khác biệt | Ảnh hưởng có thể xảy ra |
|---|---|
| Path separator | Output chứa `\\` trên Windows và `/` trên Unix-like |
| Case sensitivity | `Config.yml` và `config.yml` có thể là hai file trên Linux nhưng trùng tên trên filesystem Windows mặc định |
| Line ending | CRLF và LF làm nội dung text khác byte |
| File permission | Executable bit và mode có thể khác hoặc không được bảo toàn giống nhau |
| Symlink | Cách tạo/đọc symbolic link và quyền tạo link khác nhau |
| Native binary | DLL, `.so`, `.dylib` và kiến trúc CPU không tương thích lẫn nhau |
| Toolchain | JDK vendor/version, compiler hoặc công cụ hệ thống có thể tạo output khác |
| Locale/timezone | Format ngày, số và tên tháng có thể thay đổi |
| Filesystem ordering | Thứ tự duyệt file có thể khác |

Một task tạo file text chuẩn hóa UTF-8/LF có thể dùng chung output giữa hệ điều hành nếu nội dung không chứa dữ liệu platform-specific. Một task biên dịch native executable thường không thể dùng output Linux trên Windows.

### 8.1. Không phải cache nào cũng nên dùng chung giữa OS

Build cache key phản ánh các input mà task khai báo và cách chúng được chuẩn hóa. Nếu task output phụ thuộc OS nhưng OS không được khai báo, Gradle có thể xem hai lần chạy là tương đương và trả output không phù hợp.

Ví dụ task tạo script:

```text
Windows output: launch.bat
Linux output:   launch.sh
```

Nếu cùng một task key được dùng trên cả hai OS nhưng task không khai báo platform là input, cache có thể trả output của OS khác. Có hai hướng:

1. Tạo output đa nền tảng giống nhau, ví dụ script portable hoặc hai file script luôn được tạo cùng một cấu trúc.
2. Khai báo OS/architecture/toolchain là input để cache key phân biệt output theo platform.

Không nên thêm OS vào mọi task một cách máy móc. Chỉ thêm khi platform thực sự ảnh hưởng output. Nếu task tạo một file index UTF-8/LF độc lập OS, thêm OS không cần thiết sẽ làm giảm cache hit giữa các máy.

### 8.2. Khai báo platform là input

Ví dụ task tạo output khác nhau theo hệ điều hành:

```groovy
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input

abstract class GenerateLaunchFiles extends DefaultTask {
    @Input
    abstract Property<String> getTargetOs()

    // Input/output properties và TaskAction được khai báo ở đây.
}

tasks.register('generateLaunchFiles', GenerateLaunchFiles) {
    targetOs.set(providers.systemProperty('os.name').orElse('unknown'))
}
```

`targetOs` là input nên cache key có thể phân biệt Windows, Linux và macOS. Với native compilation, thường cần khai báo thêm architecture, ABI, compiler version và các flag có ảnh hưởng output.

Nếu dùng toolchain API, hãy để task nhận compiler/toolchain được cấu hình và khai báo input classpath/tool version theo đúng task type thay vì chỉ dựa vào `os.name`.

### 8.3. Case sensitivity và tên file

Một source tree có hai file:

```text
src/main/resources/Config.yml
src/main/resources/config.yml
```

Trên filesystem phân biệt hoa/thường, hai file có thể cùng tồn tại. Trên filesystem không phân biệt hoa/thường, chúng có thể xung đột hoặc một file không thể checkout đúng. Nếu archive chứa cả hai entry, consumer giải nén trên Windows có thể gặp vấn đề.

Đối với sản phẩm cần chạy đa nền tảng, nên tránh tên file chỉ khác chữ hoa/thường và kiểm tra cấu trúc archive trên filesystem đích.

## 9. Cache giữa máy developer và CI

Chia sẻ cache giữa developer và CI có thể giảm đáng kể thời gian build, nhưng cần kiểm soát khác biệt môi trường.

Một cấu hình thường gặp:

```text
Developer laptop
  - đọc remote build cache
  - dùng local build cache
  - thường không push vào cache release

Trusted CI
  - đọc remote build cache
  - chạy test và verification
  - push output đã xác minh

Untrusted pull request
  - có thể đọc cache công khai/được phép
  - không được push vào cache tin cậy
```

### 9.1. Cùng source revision và cùng task inputs

Cache hit giữa developer và CI có khả năng cao khi:

- Cùng commit/source tree.
- Cùng build logic và plugin implementation.
- Cùng dependency versions và normalized classpath.
- Cùng task properties và toolchain cần thiết.
- Task được thiết kế relocatable và không phụ thuộc máy.

Nếu CI dùng JDK khác developer, task compile có thể có input/toolchain khác và không nên buộc dùng output cache từ môi trường khác khi kết quả không tương thích.

### 9.2. CI cache của Gradle User Home khác remote build cache

Nhiều CI platform có chức năng lưu thư mục như `~/.gradle/caches` giữa các job. Đây là **CI workspace cache**: pipeline lưu/khôi phục thư mục local của Gradle để giảm tải dependency và các dữ liệu khác.

Remote build cache là dịch vụ chuyên lưu task outputs theo build cache key. Hai cơ chế có thể cùng được dùng nhưng không thay thế nhau.

| Cơ chế | Cách hoạt động | Dữ liệu chính |
|---|---|---|
| CI cache Gradle User Home | CI lưu rồi khôi phục thư mục cache | Dependency cache, wrapper distribution, local build cache và một số state khác |
| Gradle remote build cache | Gradle trao đổi task output theo cache key | Output của task cacheable |

CI cache thường cần key dựa trên OS, Gradle version, JDK hoặc lockfile tùy dữ liệu được lưu. Không nên khôi phục một Gradle User Home tùy tiện từ một OS khác nếu cache chứa dữ liệu phụ thuộc nền tảng.

## 10. Cấu hình cache remote và chính sách push/pull

Một số dự án cho phép mọi developer đọc cache nhưng chỉ CI đáng tin cậy được push. Ví dụ trong `settings.gradle`:

```groovy
buildCache {
    local {
        enabled = true
    }

    remote(HttpBuildCache) {
        url = uri('https://cache.example.com/')
        push = System.getenv('CI') == 'true'
    }
}
```

Đoạn cấu hình minh họa chính sách push khi biến `CI` có giá trị `true`. Mỗi nền tảng CI có cách đặt biến khác nhau; trong hệ thống thực tế nên dùng một biến được kiểm soát và xác thực nguồn job trước khi cho phép push.

Khi cần credential, cấu hình authentication theo loại cache server và Gradle version. Không ghi username/password trực tiếp vào file settings được commit. Dùng secret store hoặc cơ chế credential của tổ chức.

## 11. Kiểm tra cache portability bằng build ở hai workspace

Một cách kiểm tra thực tế là build cùng revision trong hai thư mục khác nhau và quan sát trạng thái task.

Ví dụ:

```text
Workspace A: /tmp/project-a
Workspace B: /tmp/project-b
```

Quy trình:

1. Checkout cùng commit vào hai workspace.
2. Dùng cùng Gradle Wrapper và toolchain.
3. Bật build cache.
4. Build task trong workspace A để tạo cache entry.
5. Xóa output project ở workspace B hoặc dùng checkout mới.
6. Chạy cùng task ở workspace B.
7. Kiểm tra log xem task có trạng thái `FROM-CACHE` hay không.
8. So sánh output được khôi phục với output mong đợi.

Lệnh ví dụ:

```bash
./gradlew clean generateResourceIndex --build-cache --info
```

Sau đó ở workspace thứ hai:

```bash
./gradlew generateResourceIndex --build-cache --info
```

Nếu remote cache được cấu hình đúng, task có thể khôi phục output. Với local cache, hai workspace phải dùng chung Gradle User Home hoặc cache directory. `--info` giúp quan sát trạng thái task và thông tin cache.

### 11.1. Kiểm tra output sau cache restore

Không chỉ nhìn dòng `FROM-CACHE`. Hãy kiểm tra file được khôi phục:

- Nội dung có đúng không?
- File path nằm trong workspace hiện tại hay còn chứa path cũ?
- Line ending/encoding có phù hợp không?
- File permission có đúng trên OS đích không?
- Ứng dụng/test có dùng output đó thành công không?

Một cache hit không chứng minh task đã khai báo input đúng. Nếu task bỏ sót input, cache có thể trả một output cũ nhưng không phù hợp. Cần kiểm tra hành vi và tính đúng đắn của task.

## 12. Kiểm tra khả chuyển giữa các hệ điều hành

Để kiểm tra cross-OS cache, cần xác định task output có thực sự tương thích giữa các hệ điều hành.

Ví dụ task sinh một file JSON UTF-8 với key được sắp xếp và line ending LF có thể tạo output giống nhau trên Windows và Linux. Nếu task sinh script `.bat` hoặc `.sh`, native binary, symlink hay file mode, output có thể phụ thuộc OS.

Ma trận kiểm tra:

| Nguồn cache | Máy nhận | Có thể chia sẻ? | Điều kiện |
|---|---|---|---|
| Linux x86_64 | Linux x86_64 | Thường có | Cùng task implementation/input/toolchain tương thích |
| Linux x86_64 | Windows x86_64 | Có điều kiện | Output phải độc lập OS hoặc platform phải được đưa vào cache key |
| Windows x86_64 | macOS ARM64 | Có điều kiện | Native output/toolchain/architecture phải tương thích hoặc được phân biệt |
| Developer laptop | CI cùng OS/JDK | Thường thuận lợi | Cùng input, build logic và cache policy |
| CI trusted | Developer | Có thể | Developer có quyền read và output được tạo từ input tương đương |

Không nên kết luận rằng remote build cache luôn có thể chia sẻ mọi task giữa mọi OS. Gradle hỗ trợ remote cache giữa các máy, nhưng tính đúng đắn của việc dùng lại output vẫn phụ thuộc task và môi trường.

## 13. Khi nào nên tắt cache cho task?

Một task không nên cache nếu output không thể được mô tả đầy đủ bằng input hoặc có tác dụng phụ không thể tái tạo an toàn.

Ví dụ task:

- Publish artifact lên repository.
- Gửi email/thông báo.
- Deploy ứng dụng lên server.
- Gọi API bên ngoài để thay đổi trạng thái.
- Tạo output chứa dữ liệu bí mật hoặc phụ thuộc trạng thái không thể khai báo.
- Tạo native output mà task không khai báo target platform/toolchain.

Với task custom, có thể không đánh dấu `@CacheableTask` hoặc dùng annotation `@DisableCachingByDefault` để thể hiện task không nên cache theo mặc định. Nếu chỉ một số điều kiện cho phép cache, có thể dùng `outputs.cacheIf(...)` với điều kiện rõ ràng.

Không nên tắt cache cho mọi task chỉ vì một task có vấn đề. Hãy sửa input/output model hoặc giới hạn caching đúng task.

## 14. Cache và output path

Task cần khai báo output property bằng Gradle `DirectoryProperty`, `RegularFileProperty` hoặc annotation output phù hợp. Gradle khôi phục output vào vị trí được cấu hình của task hiện tại.

Ví dụ output:

```groovy
@OutputDirectory
abstract DirectoryProperty getGeneratedDirectory()
```

Nếu task ghi thêm file ngoài output directory đã khai báo, file đó không được quản lý đầy đủ bởi Gradle. Điều này có thể gây:

- Output cũ còn sót lại sau cache restore.
- Build khác nhau tùy trạng thái workspace.
- Task bị đánh giá `UP-TO-DATE` dù có file ngoài chưa được cập nhật.
- Cache entry không chứa đủ file cần thiết.

Hãy ghi toàn bộ output vào các vị trí đã khai báo và tránh thay đổi file source hoặc file ngoài build directory trong task action.

## 15. Maven và khả năng chia sẻ cache

Maven có local repository để cache dependency và plugin đã tải. Nó giúp nhiều build trên cùng máy không phải tải lại cùng artifact. CI cũng có thể lưu/khôi phục local repository giữa các job.

Tuy nhiên, Maven core không cung cấp một remote task output build cache tổng quát tương đương Gradle build cache theo cùng mô hình `@CacheableTask` và cache key. Maven có incremental behavior của compiler/plugin và có thể dùng extension/plugin bên thứ ba cho các nhu cầu build cache cụ thể.

Điều này có nghĩa:

- Dùng Maven local repository trên hai máy giúp tái sử dụng dependency đã tải nếu cache được chia sẻ/copy phù hợp.
- Nó không tự động chia sẻ output `target/classes` hoặc kết quả của mọi plugin giữa các máy.
- `mvn clean` xóa output project trong `target/`, không xóa toàn bộ `~/.m2/repository`.
- Remote Maven repository chủ yếu lưu artifact đã publish và metadata, không phải một task output cache chung cho mọi lần build.

Nếu dùng plugin/extension cache cho Maven, cần đọc hợp đồng cache của công cụ đó: input nào được fingerprint, có hỗ trợ relocation không, có phân biệt OS/JDK không và cache được bảo vệ thế nào.

## 16. Phân biệt cache portability với dependency portability

Một dependency có thể tải được trên nhiều máy nhưng task sử dụng dependency đó chưa chắc có output cache portable.

Ví dụ:

- Cùng một JAR Java thuần có thể được tải trên Windows và Linux.
- Task biên dịch Java có thể tạo class file tương thích giữa các hệ điều hành nếu toolchain và input tương đương.
- Task tạo native executable cần output riêng theo OS/architecture.
- Task package script có thể cần line ending và permission khác nhau theo nền tảng.

Dependency cache trả lời câu hỏi “có artifact dependency nào để build dùng không?”. Build cache trả lời “có output task đã tạo từ input tương đương để dùng lại không?”. Hai câu hỏi khác nhau.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Build ở workspace khác không có cache hit | File input fingerprint dùng absolute path hoặc task không relocatable | Dùng `@PathSensitive(RELATIVE)` nếu cấu trúc tương đối có ý nghĩa |
| Cache hit nhưng output chứa đường dẫn workspace cũ | Task ghi absolute path vào output mà không khai báo như input | Loại absolute path khỏi output hoặc khai báo nó nếu thực sự cần |
| Windows nhận script Linux từ cache | OS ảnh hưởng output nhưng không được khai báo là input | Khai báo platform input hoặc tạo output đa nền tảng ổn định |
| Native binary bị khôi phục sai máy | Thiếu OS/architecture/compiler input hoặc cache key không phân biệt target | Phân biệt target platform và toolchain; tách cache khi cần |
| Task không cache dù input không đổi | Task không cacheable, thiếu output declaration hoặc input fingerprint khác | Kiểm tra annotation, task properties và log `--info` |
| Cache trả output cũ sau khi đổi biến môi trường | Biến môi trường ảnh hưởng output nhưng chưa khai báo là input | Đưa giá trị vào `@Input` hoặc Provider property |
| `clean` xong task vẫn `FROM-CACHE` | `clean` chỉ xóa project output, build cache vẫn còn | Đây là hành vi bình thường; dùng `--no-build-cache` khi cần kiểm tra thực thi lại |
| Cache remote bị ghi output không tin cậy | Job không đáng tin cậy có quyền push | Chỉ cấp push cho CI đáng tin cậy và bảo vệ credential |
| CI cache Gradle User Home không dùng được trên OS khác | Cache chứa dữ liệu phụ thuộc nền tảng hoặc version | Chọn cache key CI theo OS/Gradle/JDK và kiểm soát dữ liệu được lưu |
| Maven build trên máy khác vẫn compile lại | Local repository chỉ cache dependency, không phải remote task output cache tổng quát | Dùng CI cache dependency hoặc công cụ build-cache chuyên biệt nếu cần |

## 18. Quy trình thiết kế task cacheable và relocatable

Khi viết một task có thể chia sẻ giữa nhiều thư mục/máy, hãy thực hiện theo trình tự:

1. **Xác định mọi input:** file, directory, property, classpath, toolchain, environment và platform có ảnh hưởng output.
2. **Khai báo input có kiểu:** dùng `@Input`, `@InputDirectory`, `@InputFiles`, `@Classpath` hoặc annotation phù hợp.
3. **Chọn path sensitivity:** dùng `RELATIVE` khi root checkout không có ý nghĩa; dùng `ABSOLUTE` khi vị trí thật sự ảnh hưởng; dùng `NAME_ONLY`/`NONE` chỉ khi ngữ nghĩa cho phép.
4. **Khai báo output:** dùng output property và ghi tất cả output vào vị trí được quản lý.
5. **Chuẩn hóa output:** sắp xếp file, chuẩn hóa path separator, encoding, line ending, timestamp và locale.
6. **Loại bỏ trạng thái ngầm:** không đọc current time, hostname, username hoặc biến môi trường tùy tiện.
7. **Phân biệt platform:** nếu OS/architecture/JDK làm output thay đổi, khai báo chúng là input hoặc không chia sẻ task output giữa các nền tảng.
8. **Xác nhận task cacheable:** chỉ bật cache khi output xác định từ input và không có side effect không thể khôi phục.
9. **Kiểm tra relocation:** build cùng input ở hai checkout path khác nhau và quan sát `FROM-CACHE`.
10. **Kiểm tra cross-machine/OS:** xác nhận output được khôi phục vẫn đúng và chạy được trên máy nhận.
11. **Bảo vệ remote cache:** giới hạn quyền push, dùng TLS/authentication và tách trust boundary.
12. **Theo dõi cache behavior:** dùng `--info` và build scan nếu tổ chức sử dụng để hiểu cache hit/miss.

## 19. Ví dụ cấu hình kiểm tra cache portability

Giả sử đã đăng ký task `generateResourceIndex` như phần trước. Có thể kiểm tra theo hai workspace:

```bash
# Workspace A: tạo output và cache entry
./gradlew clean generateResourceIndex --build-cache --info

# Workspace B: cùng commit, cùng Gradle User Home hoặc remote cache
./gradlew clean generateResourceIndex --build-cache --info
```

Ở workspace B, nếu task được cacheable, input normalized giống nhau và cache có entry, log có thể cho thấy `FROM-CACHE`.

Để thử khi không muốn lấy cache:

```bash
./gradlew clean generateResourceIndex --no-build-cache --rerun-tasks
```

Lệnh này giúp xác nhận task có thực sự thực thi và tạo output mới. Có thể so sánh nội dung với output đã được khôi phục từ cache.

Với cross-OS, chạy cùng quy trình trên runner Windows và Linux. Nếu output khác do platform, cần quyết định task có nên dùng cache riêng theo platform hay chuẩn hóa output để dùng chung. Không ép cache hit bằng cách bỏ qua input platform khi output không tương thích.

## 20. Nguyên tắc cần ghi nhớ

- Build cache lưu output của task; dependency cache lưu dependency đã tải; configuration cache lưu trạng thái configuration.
- Task chỉ portable khi mọi input ảnh hưởng output được khai báo và fingerprint phù hợp.
- Absolute path thường làm giảm khả năng chia sẻ giữa workspace; dùng relative path nếu root checkout không có ý nghĩa.
- `@PathSensitive(RELATIVE)` phù hợp với input file/directory có cấu trúc tương đối quan trọng.
- `@Classpath` và `@CompileClasspath` cung cấp chuẩn hóa phù hợp cho classpath input.
- Output không được chứa timestamp, hostname, username hoặc path máy nếu những giá trị đó không phải input có chủ đích.
- Khác biệt OS, architecture, JDK, line ending, permission và native binary có thể yêu cầu cache key riêng.
- Remote cache có thể chia sẻ output giữa developer và CI nhưng cần kiểm soát quyền push và nguồn tin cậy.
- `clean` không xóa build cache; `FROM-CACHE` là hành vi bình thường khi task có output phù hợp.
- Maven local repository cache dependency; Maven core không có remote task output cache tổng quát tương đương Gradle build cache.
- Kiểm tra cache hit phải đi kèm xác nhận output đúng và chạy được trên môi trường nhận.

Cache khả chuyển giúp nhiều workspace và máy build tận dụng cùng kết quả, nhưng chỉ khi task được mô hình hóa đúng. Hãy khai báo input/output đầy đủ, chuẩn hóa đường dẫn và nội dung, phân biệt khác biệt nền tảng, rồi kiểm tra output sau khi khôi phục. Khi đó build cache vừa tăng tốc vừa giữ được tính đúng đắn của artifact.
