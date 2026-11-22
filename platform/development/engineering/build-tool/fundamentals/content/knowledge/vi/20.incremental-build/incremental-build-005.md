# Khóa cache và điều kiện tái sử dụng kết quả an toàn

Build tăng dần giúp Gradle tránh làm lại những công việc mà kết quả vẫn còn hợp lệ. Khi một task đã chạy và tạo output, Gradle có thể nhận ra đầu vào không đổi để giữ nguyên output hiện tại, hoặc lấy output tương ứng từ build cache. Trong một nhóm phát triển, nhiều Gradle process còn có thể cùng truy cập cache dùng chung. Gradle cần cơ chế khóa để bảo vệ dữ liệu cache khỏi các thao tác ghi/đọc đồng thời không an toàn.

“Cache” trong Gradle không phải một nơi duy nhất và cũng không phải mọi dữ liệu được lưu đều có thể tái sử dụng theo cùng một quy tắc. Cần phân biệt:

- **Up-to-date checking:** xác định task có thể bỏ qua lần thực thi vì đầu vào và output hiện tại vẫn khớp với lần chạy trước trong workspace.
- **Build cache:** lưu output của task theo danh tính task và các đầu vào đã khai báo để có thể khôi phục kết quả ở build khác hoặc workspace khác.
- **Configuration cache:** lưu trạng thái cấu hình và task graph để bỏ qua một phần công việc configuration ở invocation tiếp theo.
- **Dependency cache:** lưu metadata và artifact dependency đã resolve từ repository để tránh tải và phân tích lại không cần thiết.
- **Cache locking:** đồng bộ truy cập vào những cache dùng chung để nhiều Gradle process không làm hỏng trạng thái cache.

Điều kiện cốt lõi để tái sử dụng kết quả an toàn là Gradle phải biết đầy đủ những yếu tố ảnh hưởng tới kết quả. Nếu task đọc thêm file, biến môi trường, thời gian, dữ liệu mạng hoặc trạng thái máy mà không khai báo, cache có thể trả về output cũ dù kết quả đúng lẽ ra đã thay đổi.

## 1. Cache giúp build tăng dần như thế nào?

Giả sử project có các task:

~~~text
compileJava
    |
    v
processResources
    |
    v
test
    |
    v
jar
~~~

Ở lần build đầu, Gradle thực hiện các task cần thiết. Ở lần sau, nếu source, resource, cấu hình và dependency liên quan không đổi, Gradle có thể bỏ qua một số task hoặc khôi phục output đã được cache.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Task được đưa vào task graph"] --> B["Xác định implementation và inputs"]
    B --> C{"Output hiện tại còn up-to-date?"}
    C -->|Có| D["UP-TO-DATE: bỏ qua thực thi"]
    C -->|Không| E{"Task cacheable và build cache bật?"}
    E -->|Không| F["Thực thi task"]
    E -->|Có| G{"Có cache entry phù hợp?"}
    G -->|Có| H["FROM-CACHE: khôi phục outputs"]
    G -->|Không| F
    F --> I["Tạo outputs"]
    I --> J{"Có thể lưu cache?"}
    J -->|Có| K["Lưu kết quả vào build cache"]
    J -->|Không| L["Giữ output trong workspace"]
~~~

Sơ đồ thể hiện cách suy nghĩ ở mức khái niệm. Chi tiết kiểm tra và thứ tự nội bộ phụ thuộc loại task và Gradle version. Một task có thể được bỏ qua vì không có source, bị skip theo điều kiện, hoặc không nằm trong task graph.

Build tăng dần không chỉ là “lưu file để dùng lại”. Gradle cần một hợp đồng rõ ràng giữa task và hệ thống build: task nhận đầu vào nào, tạo đầu ra nào, và khi nào những đầu ra đó còn đại diện cho kết quả đúng.

## 2. Phân biệt các loại cache và trạng thái liên quan

Các cơ chế sau có mục tiêu khác nhau. Dùng nhầm tên sẽ dẫn tới cấu hình sai hoặc chẩn đoán lỗi sai.

| Cơ chế | Lưu gì? | Phạm vi tái sử dụng | Điều kiện chính |
|---|---|---|---|
| Up-to-date checking | Execution state và snapshots của task trong workspace | Cùng workspace/build directory | Inputs không đổi và outputs hiện tại vẫn hợp lệ |
| Build cache | Outputs của task đã cache | Workspace khác hoặc máy khác nếu dùng chung remote cache | Task cacheable, inputs/outputs khai báo đầy đủ, cache key khớp |
| Configuration cache | Trạng thái configuration và task graph | Invocation sau của build tương ứng | Configuration phase tuân thủ yêu cầu configuration cache |
| Dependency cache | Module metadata và artifact từ repositories | Nhiều build dùng cùng Gradle User Home | Dependency identity/repository và cache policy phù hợp |
| Daemon/JVM caches | Một số dữ liệu phục vụ tiến trình và hiệu năng | Theo vòng đời daemon/process | Được Gradle quản lý nội bộ |

### 2.1. Up-to-date checking không phải build cache

Up-to-date checking trả lời: “Trong workspace này, task có cần chạy lại không?”

Ví dụ, task compile đã tạo class files. Nếu các source file, classpath và tùy chọn compiler liên quan không đổi, Gradle có thể đánh dấu task là UP-TO-DATE và không gọi compiler lần nữa.

Cơ chế này thường dựa trên execution history và snapshot của inputs/outputs trong workspace. Nếu xóa thư mục output hoặc chạy trong một workspace mới, Gradle không thể chỉ dựa vào output cũ tại workspace đó.

### 2.2. Build cache có thể khôi phục output

Build cache trả lời: “Đã có task tương đương chạy với cùng đầu vào ở nơi khác chưa?”

Nếu task cacheable và cache có entry khớp, Gradle có thể khôi phục output thay vì thực thi task. Điều này hữu ích khi:

- Developer chuyển branch rồi quay lại một trạng thái source đã build.
- Nhiều project có task giống nhau và đầu vào tương đương.
- CI build trên agent mới nhưng remote cache đã có kết quả.
- Một task được thực hiện trong workspace khác với cùng các đầu vào có ý nghĩa.

Một task được khôi phục từ cache thường có outcome FROM-CACHE. Đây là dấu hiệu khác với UP-TO-DATE.

### 2.3. Configuration cache không lưu output task

Configuration cache lưu trạng thái đã cấu hình của build, bao gồm thông tin cần thiết để tái sử dụng task graph trong invocation sau. Nó nhằm giảm thời gian configuration, đặc biệt với build có nhiều plugin và project.

Configuration cache không thay thế build cache:

- Configuration cache giúp tránh cấu hình lại build.
- Build cache giúp tránh thực thi task bằng cách khôi phục output.
- Một build có thể dùng cả hai.
- Một build có thể dùng configuration cache nhưng task vẫn phải chạy.
- Một task có thể được khôi phục từ build cache dù configuration cache không được sử dụng.

Có thể bật bằng:

~~~bash
./gradlew build --configuration-cache
~~~

Gradle sẽ kiểm tra các thao tác configuration có tương thích với cơ chế này hay không và báo các vấn đề cần xử lý.

### 2.4. Dependency cache không phải build output cache

Dependency cache lưu thông tin về module metadata và artifact được tải từ repository. Nó giúp Gradle tránh tải lại hoặc phân tích lại dependency trong những lần resolve sau.

Ví dụ, nếu build cần một module Maven đã được tải trước đó, Gradle có thể dùng metadata và artifact trong cache dependency theo chính sách cache tương ứng.

Dependency cache không lưu kết quả của task compile/test/jar. Build cache mới là cơ chế lưu output task.

## 3. Cache locking bảo vệ dữ liệu dùng chung

Một Gradle build có thể chạy đồng thời với build khác. Ví dụ developer chạy một build ở terminal, IDE khởi chạy build riêng, và một script CI local cũng resolve dependency. Các process có thể cùng truy cập những cache nằm trong Gradle User Home.

Nếu nhiều process cùng sửa metadata hoặc trạng thái cache mà không đồng bộ, dữ liệu có thể bị ghi đè hoặc đọc ở trạng thái chưa hoàn chỉnh. Gradle quản lý khóa cho các cache dùng chung để điều phối việc truy cập đồng thời.

### 3.1. Khóa cache giải quyết vấn đề gì?

Khóa cache là cơ chế đồng bộ giữa các process. Ở mức khái niệm, một process cần truy cập vùng dữ liệu được bảo vệ sẽ lấy lock phù hợp; process khác phải chờ hoặc dùng vùng cache khác theo cơ chế của Gradle.

Mục tiêu là bảo đảm các thao tác cập nhật cache có tính nhất quán. Cơ chế lock được Gradle quản lý tự động; người dùng không cần tự viết file lock cho cache Gradle.

Một số ví dụ về nơi có thể cần đồng bộ:

- Dependency metadata được dùng bởi nhiều build.
- Cache chung trong Gradle User Home.
- Dữ liệu nội bộ của cache mà nhiều Gradle process cùng truy cập.
- Một số thao tác quản lý cache khi process kết thúc hoặc cập nhật dữ liệu.

Cách triển khai khóa cụ thể khác nhau giữa các cache subsystem và Gradle version. Điều cần nhớ là cache lock bảo vệ dữ liệu cache theo cơ chế Gradle, không phải một khóa nghiệp vụ mà project cần tự quản lý.

### 3.2. Gradle User Home và cache dùng chung

Gradle User Home thường chứa wrapper distributions, dependency caches, build cache local, daemon state và một số dữ liệu Gradle khác. Vị trí mặc định có thể được thay đổi bằng biến môi trường GRADLE_USER_HOME hoặc cấu hình tương ứng.

Nhiều build trên cùng máy có thể dùng chung Gradle User Home. Gradle có cơ chế quản lý truy cập để các process cùng sử dụng dữ liệu cache an toàn.

Điều này khác với việc nhiều build cùng ghi vào một project directory. Cache trong Gradle User Home được Gradle quản lý theo lock; thư mục output của project như build/classes hoặc build/libs không tự động trở thành an toàn khi hai invocation cùng ghi vào đó.

### 3.3. Không xóa lock file khi Gradle đang chạy

Khi gặp thông báo chờ lock hoặc cache lock timeout, không nên xóa file lock ngay lập tức.

Trước tiên hãy xác định:

- Có Gradle process nào khác đang chạy không?
- IDE có đang sync hoặc build project không?
- Có CI job khác dùng chung Gradle User Home không?
- Process giữ lock còn hoạt động hay đã kết thúc?
- Cache nằm trên local disk hay network/shared filesystem?
- Có lỗi quyền truy cập hoặc filesystem không hỗ trợ locking đúng cách không?

Lock file có thể còn tồn tại trên disk sau khi process đã kết thúc; điều đó không tự chứng minh khóa vẫn đang bị giữ. Trạng thái khóa do cơ chế file lock/process quản lý. Xóa file khi một process còn dùng cache có thể làm tình hình tệ hơn hoặc gây hỏng cache.

### 3.4. Cache locking không bảo vệ output directory của project

Giả sử hai CI job cùng chạy trên một checkout:

~~~text
workspace/
└── orders-service/
    └── build/
        ├── classes/
        ├── resources/
        └── libs/
~~~

Cả hai job có thể cùng xóa hoặc ghi các file trong build directory. Cache lock ở Gradle User Home không điều phối mọi thao tác trên output directory này. Một job có thể xóa output mà job kia đang tạo.

Để chạy song song an toàn:

- Dùng workspace/checkout riêng cho từng job hoặc từng worker.
- Không cho nhiều invocation cùng ghi vào cùng project output directory nếu build không được thiết kế cho điều đó.
- Dùng build cache local/remote để chia sẻ kết quả task thay vì chia sẻ trực tiếp thư mục build.
- Nếu buộc phải dùng chung workspace, cần serialize các thao tác có thể ghi đè output.

Đây là ranh giới quan trọng: **cache locking bảo vệ cache; nó không biến một working tree dùng chung thành môi trường build đồng thời an toàn.**

## 4. Build cache hoạt động dựa trên task inputs và outputs

Gradle chỉ có thể tái sử dụng output nếu biết những yếu tố nào quyết định kết quả task. Một task cacheable cần khai báo đầy đủ inputs và outputs.

Ví dụ một task tạo file báo cáo từ source:

~~~groovy
abstract class GenerateReport extends DefaultTask {
    @InputFiles
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract ConfigurableFileCollection getSourceFiles()

    @Input
    abstract Property<String> getReportTitle()

    @OutputFile
    abstract RegularFileProperty getReportFile()

    @TaskAction
    void generate() {
        def files = sourceFiles.files.sort { it.path }
        def content = files.collect { it.text }.join('\n')

        reportFile.get().asFile.text =
            reportTitle.get() + '\n' + content
    }
}
~~~

Ví dụ chỉ minh họa ý tưởng khai báo task properties. Trong task thực tế, cần xử lý encoding, lỗi I/O và thứ tự dữ liệu có chủ đích. Nếu nội dung phụ thuộc vào một input khác, task phải khai báo input đó.

### 4.1. Inputs phải bao gồm mọi thứ có ảnh hưởng đến kết quả

Inputs có thể gồm:

- Source files hoặc resource files.
- Compiler flags và tool options.
- Classpath hoặc tool classpath.
- Version của compiler/generator/tool.
- Giá trị property và command-line argument.
- Environment variable có ảnh hưởng tới output.
- System property có ảnh hưởng tới output.
- File cấu hình, schema, template hoặc dữ liệu đầu vào.
- Target platform, architecture hoặc toolchain nếu kết quả phụ thuộc chúng.

Ví dụ, task tạo code từ schema có thể cần khai báo schema files, generator version, package name và các option sinh code. Nếu task đọc thêm biến môi trường để quyết định package nhưng không khai báo biến đó là input, cache có thể trả về code sinh theo môi trường trước.

### 4.2. Outputs phải được khai báo chính xác

Outputs thường là file hoặc directory do task tạo:

- @OutputFile cho một file.
- @OutputDirectory cho một thư mục.
- Các output property phù hợp khác cho task có nhiều loại kết quả.

Khi output được khai báo, Gradle biết phần nào cần theo dõi, khôi phục và kiểm tra. Task ghi file vào một vị trí không khai báo sẽ tạo side effect ngoài hợp đồng cache.

Một task có thể khai báo nhiều outputs. Nếu một output ảnh hưởng tới task khác, cần thể hiện quan hệ producer/consumer qua task properties hoặc provider thay vì dựa vào thứ tự ngẫu nhiên.

### 4.3. Inputs không đầy đủ làm cache sai

Giả sử task tạo file cấu hình dựa trên:

- File template.
- Giá trị API endpoint.
- Biến môi trường chọn profile.

Nếu chỉ khai báo template là input, Gradle có thể thấy cache key không đổi dù endpoint hoặc profile đã đổi. Khi đó output được khôi phục có thể chứa giá trị của môi trường cũ.

Ví dụ sai về mặt ý tưởng:

~~~groovy
@InputFile
abstract RegularFileProperty getTemplate()

@OutputFile
abstract RegularFileProperty getGeneratedFile()

@TaskAction
void generate() {
    def endpoint = System.getenv('API_ENDPOINT')
    // Dùng endpoint để ghi generatedFile
}
~~~

Biến môi trường được đọc trực tiếp trong action nhưng không được mô hình hóa thành task input. Task cần đưa giá trị này qua property được khai báo input:

~~~groovy
@Input
abstract Property<String> getApiEndpoint()
~~~

Và khi cấu hình task, cung cấp giá trị qua Provider phù hợp:

~~~groovy
tasks.register('generateConfig', GenerateConfig) {
    apiEndpoint.set(providers.environmentVariable('API_ENDPOINT'))
}
~~~

Nhờ đó, thay đổi endpoint được phản ánh trong input snapshot/cache key.

## 5. Task cacheable phải có kết quả xác định

Một task có kết quả xác định (deterministic) tạo cùng output khi nhận cùng inputs và cùng môi trường thực thi đã được mô hình hóa.

Ví dụ task compile thường phù hợp với build cache vì compiler nhận source, classpath, options và toolchain rồi tạo class files. Gradle có thể quản lý inputs và outputs của task compile qua task type do plugin cung cấp.

Ngược lại, một task tạo báo cáo chứa timestamp hiện tại hoặc gọi API trả dữ liệu thay đổi liên tục có thể không an toàn để cache nếu những yếu tố đó không được khai báo và kiểm soát.

### 5.1. Những nguồn không xác định thường gặp

Các yếu tố sau có thể làm kết quả thay đổi dù inputs được khai báo không đổi:

- Thời gian hiện tại hoặc timestamp.
- Số ngẫu nhiên.
- Hostname hoặc username của máy.
- Absolute path của workspace.
- Nội dung file ngoài danh sách inputs.
- Biến môi trường hoặc system property không khai báo.
- Nội dung tải từ network không có version/identity ổn định.
- Thứ tự duyệt file không được sắp xếp khi thứ tự ảnh hưởng output.
- Locale, timezone hoặc encoding khác nhau.
- Phiên bản tool thực tế khác với tool được mô hình hóa.
- Trạng thái service hoặc database bên ngoài.
- File được sửa trong lúc task đang đọc.

Nếu một yếu tố có ảnh hưởng tới kết quả, cần khai báo nó là input, chuẩn hóa nó hoặc không cache task đó.

### 5.2. Timestamp trong output

Một task tạo file có dòng:

~~~text
Generated at 2026-11-13T08:30:00Z
~~~

Nếu timestamp thay đổi theo mỗi lần chạy nhưng không phải input, kết quả cache có thể chứa thời điểm của lần chạy cũ. Cần quyết định timestamp có thực sự cần trong artifact hay không.

Nếu timestamp là dữ liệu cần thiết, nó phải tham gia vào input identity; khi đó mỗi lần timestamp thay đổi sẽ tạo kết quả khác và giảm khả năng cache hit. Nếu timestamp chỉ phục vụ log, nên ghi ra log thay vì đưa vào output được cache.

### 5.3. Network và external services

Task gọi endpoint để lấy dữ liệu mới mỗi lần thường không nên cache như một task thuần biến đổi file. Dữ liệu mạng có thể đổi mà không có file input nào thay đổi.

Có thể cache an toàn hơn nếu task sử dụng một snapshot bất biến có version/checksum rõ ràng và khai báo identity của snapshot là input. Nếu task cần dữ liệu realtime, hãy cân nhắc không cache hoặc thiết kế một bước fetch có output/version được kiểm soát.

Không nên đánh dấu một task gọi network là cacheable chỉ để làm build nhanh hơn mà không có quy tắc freshness rõ ràng.

## 6. Path sensitivity và tính relocatable

Một task có thể chạy ở các workspace khác nhau. Nếu cache key phụ thuộc absolute path không cần thiết, kết quả ở workspace A có thể không được dùng lại ở workspace B.

Gradle cung cấp các cơ chế path sensitivity để mô tả mức độ đường dẫn có ý nghĩa đối với task.

~~~groovy
@InputFiles
@PathSensitive(PathSensitivity.RELATIVE)
abstract ConfigurableFileCollection getSources()
~~~

Các lựa chọn path sensitivity phổ biến gồm:

- ABSOLUTE: absolute path là một phần ý nghĩa của input.
- RELATIVE: đường dẫn tương đối trong input structure có ý nghĩa.
- NAME_ONLY: tên file có ý nghĩa, các phần path phía trên được bỏ qua.
- NONE: đường dẫn không có ý nghĩa đối với kết quả.

Không nên chọn NONE hoặc NAME_ONLY chỉ để tăng cache hit. Hãy chọn mức chuẩn hóa phản ánh đúng cách task sử dụng file.

### 6.1. Khi nào dùng RELATIVE?

Nếu task xử lý source files và kết quả chỉ phụ thuộc nội dung cùng vị trí tương đối của chúng trong source tree, RELATIVE thường phù hợp hơn ABSOLUTE. Nhờ đó, cùng source tree được checkout ở hai đường dẫn khác nhau có thể tạo cache key tương thích.

### 6.2. Khi nào path thật sự là input?

Một task có thể sinh nội dung chứa đường dẫn tuyệt đối hoặc gọi công cụ mà hành vi phụ thuộc vị trí file. Khi đó path có thể ảnh hưởng kết quả thật. Nếu task cần path tuyệt đối, không được giả vờ rằng path không quan trọng.

Cách tốt hơn có thể là thiết kế output relocatable bằng cách ghi relative path hoặc chuẩn hóa workspace root. Nếu không thể, khai báo path sensitivity đúng hoặc tránh cache task đó.

### 6.3. Reproducible archives

Task đóng gói archive có thể tạo output khác nhau do timestamp file entries, thứ tự entry hoặc metadata archive. Các plugin Gradle thường cung cấp thuộc tính để tạo archive reproducible, ví dụ kiểm soát thứ tự file và timestamp. Hãy dùng cấu hình phù hợp để archive có thể tái tạo khi inputs giống nhau.

Tính reproducible không chỉ giúp build cache mà còn hỗ trợ checksum ổn định, so sánh artifact và kiểm tra provenance.

## 7. Đánh dấu task có thể cache

Với custom task, Gradle yêu cầu task được thiết kế để cache an toàn. Một task type có thể dùng annotation @CacheableTask khi các inputs/outputs được khai báo và action tạo kết quả xác định.

Ví dụ:

~~~groovy
@CacheableTask
abstract class GenerateApiSources extends DefaultTask {
    @InputFiles
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract ConfigurableFileCollection getSchemas()

    @Input
    abstract Property<String> getPackageName()

    @Input
    abstract Property<String> getGeneratorVersion()

    @OutputDirectory
    abstract DirectoryProperty getOutputDirectory()

    @TaskAction
    void generate() {
        // Gọi generator với schemas, packageName và generatorVersion.
        // Chỉ ghi kết quả vào outputDirectory đã khai báo.
    }
}
~~~

Ví dụ minh họa các property cần mô hình hóa; implementation thực tế phải bảo đảm generator không đọc thêm state ẩn.

### 7.1. @CacheableTask

Annotation này cho Gradle biết task type được thiết kế để tham gia build cache. Chỉ dùng khi:

- Inputs được khai báo đầy đủ.
- Outputs được khai báo đầy đủ.
- Task không có side effect không thể tái sử dụng.
- Cùng inputs và implementation tạo cùng outputs.
- Output có thể được khôi phục ở workspace khác theo path normalization đã chọn.

Không phải mọi task đều nên cache. Task deploy, gửi email, upload release, cập nhật database hoặc xóa tài nguyên bên ngoài thường có side effect và không nên được cache như task tạo file thuần túy.

### 7.2. @DisableCachingByDefault

Một số task type được thiết kế để không cache mặc định, đặc biệt khi tính đúng đắn phụ thuộc hành vi mà Gradle không thể giả định. Task có thể yêu cầu người dùng bật cache có chủ đích sau khi đánh giá.

Nếu task không an toàn để cache, hãy giữ trạng thái disable caching. Không nên thêm @CacheableTask chỉ để loại bỏ task khỏi danh sách chạy lại.

### 7.3. Điều kiện cache theo task instance

Gradle cho phép điều kiện cache theo task instance, chẳng hạn chỉ cache khi một điều kiện được thỏa mãn hoặc chủ động từ chối cache trong trường hợp đặc biệt. Các cơ chế như cacheIf/doNotCacheIf cần được dùng nhất quán với inputs.

Nếu output phụ thuộc một điều kiện, thông thường nên biểu diễn điều kiện đó như input của task. Dùng điều kiện cache không khai báo input có thể khiến cache policy thay đổi mà cache key không phản ánh đầy đủ lý do thay đổi.

## 8. Build cache local và remote

Gradle có thể sử dụng local build cache và remote build cache.

- **Local build cache:** lưu trên máy hoặc Gradle environment hiện tại.
- **Remote build cache:** một cache service dùng chung qua mạng, giúp nhiều developer hoặc CI agent chia sẻ kết quả task.

Bật build cache bằng command line:

~~~bash
./gradlew build --build-cache
~~~

Hoặc bật trong gradle.properties:

~~~properties
org.gradle.caching=true
~~~

### 8.1. Cấu hình remote cache

Một cấu hình minh họa trong settings script:

~~~groovy
buildCache {
    local {
        enabled = true
    }

    remote(HttpBuildCache) {
        url = uri('https://cache.example.com/')
        push = false
    }
}
~~~

Trong ví dụ này, build đọc được cache remote nhưng không upload kết quả lên remote cache. Cấu hình thực tế cần theo loại cache server, authentication, TLS và chính sách push của tổ chức.

Không nên đưa credential trực tiếp vào file build được commit. Dùng biến môi trường, secret store hoặc cơ chế credential an toàn của môi trường CI.

### 8.2. Read-only và write access

Một chính sách thường dùng:

- Developer và pull request build được phép đọc cache.
- Chỉ CI trên nhánh tin cậy hoặc pipeline release được phép ghi remote cache.
- Cache service yêu cầu xác thực và chỉ cấp quyền push cho agent được tin cậy.
- Cache key và namespace được tổ chức để tránh chia sẻ giữa các build có môi trường không tương thích.

Chính sách cụ thể phụ thuộc hệ thống. Điều quan trọng là không để code từ nguồn không tin cậy tùy ý ghi output vào cache mà build phát hành tin cậy sẽ sử dụng.

### 8.3. Remote cache không phải artifact repository

Remote build cache lưu output task theo cache key. Artifact repository lưu module đã publish theo tọa độ/version và metadata dependency.

| Remote build cache | Artifact repository |
|---|---|
| Lưu task outputs | Lưu artifact phát hành |
| Tra cứu theo cache key | Tra cứu theo group/name/version và metadata |
| Phục vụ tăng tốc build | Phục vụ phân phối dependency/release |
| Output có thể được tái tạo từ source | Artifact là sản phẩm đã publish |
| Không thay thế publication contract | Không thay thế task output cache |

Không nên dùng remote build cache làm nơi phát hành library cho consumer.

## 9. Khi nào một task được tái sử dụng?

Một cache hit thường cần nhiều điều kiện đồng thời:

1. Build cache được bật.
2. Task type hoặc task instance được phép cache.
3. Task có inputs và outputs được khai báo đúng.
4. Gradle tính được cache key tương ứng.
5. Cache chứa entry có key khớp.
6. Cache entry có thể truy cập và tải được.
7. Chính sách task/cache không từ chối sử dụng entry.
8. Môi trường thực thi được mô hình hóa đủ để output vẫn hợp lệ.

Nếu thiếu một điều kiện, Gradle có thể phải thực thi task. Điều đó không nhất thiết là lỗi; có thể đơn giản là cache chưa có entry hoặc task không phù hợp để cache.

### 9.1. Cache key phản ánh điều gì?

Ở mức khái niệm, cache key phụ thuộc vào task implementation và những inputs Gradle đã nhận diện, bao gồm các file/property và classpath liên quan. Thay đổi một input có ý nghĩa sẽ tạo key khác.

Vì vậy, các thay đổi sau có thể làm task cần chạy lại hoặc tìm cache entry khác:

- Source file thay đổi.
- Compiler option thay đổi.
- Dependency classpath thay đổi.
- Tool implementation/version thay đổi.
- Input property hoặc generator option thay đổi.
- File được thêm/bớt trong input collection.
- Path thay đổi theo sensitivity được khai báo.

Không nên tự tạo cache key bên ngoài dựa trên tên task và Git commit rồi giả định nó tương đương Gradle. Gradle có quy tắc fingerprint riêng để bảo đảm correctness.

### 9.2. Cache miss không có nghĩa cache hỏng

Cache miss có thể xảy ra vì:

- Chưa từng có build tạo entry.
- Inputs khác nhau.
- Task implementation khác.
- Path sensitivity làm key khác.
- Cache entry đã bị dọn theo retention policy.
- Remote cache không truy cập được.
- Task không cacheable.
- Cache policy không cho phép đọc/ghi.

Khi task chạy lại, hãy kiểm tra lý do trước khi kết luận cache có lỗi.

## 10. Quan sát task outcome và chẩn đoán cache

Gradle hiển thị outcome của task trong console. Một số trạng thái thường gặp:

| Outcome | Ý nghĩa khái quát |
|---|---|
| SUCCESS | Task đã thực thi và hoàn thành |
| UP-TO-DATE | Inputs/outputs hiện tại khớp execution history nên không cần chạy lại |
| FROM-CACHE | Outputs được khôi phục từ build cache |
| NO-SOURCE | Không có input source phù hợp để xử lý |
| SKIPPED | Task bị bỏ qua theo điều kiện hoặc cơ chế khác |

Ví dụ chạy với build cache và log chi tiết:

~~~bash
./gradlew clean build --build-cache --info
~~~

Log có thể giúp nhận biết task nào được lấy từ cache và task nào chạy thật. Dùng --info khi cần điều tra; không cần bật log chi tiết trong mọi build thường ngày.

### 10.1. Phân biệt UP-TO-DATE và FROM-CACHE

Ví dụ:

- Lần build đầu: task chạy và tạo output.
- Lần build tiếp theo trong cùng workspace: output vẫn tồn tại, inputs không đổi; task có thể là UP-TO-DATE.
- Xóa output hoặc chạy trong workspace mới: Gradle không còn output local để giữ nguyên. Nếu cache entry phù hợp tồn tại, task có thể là FROM-CACHE.
- Nếu cache entry không có hoặc key khác: task thực thi lại.

Đây là cách phân biệt nhanh giữa up-to-date checking và build cache.

### 10.2. Thử nghiệm cache trong workspace sạch

Có thể kiểm tra build cache bằng cách:

1. Bật build cache.
2. Build một lần để tạo cache entry.
3. Dùng workspace/checkout khác với cùng source và build inputs.
4. Build lại với cache bật.
5. Quan sát task outcome và log.
6. So sánh output được khôi phục với output kỳ vọng.

Không nên dùng hai process cùng ghi vào một build directory để thử nghiệm. Hai workspace riêng giúp kiểm tra khả năng tái sử dụng xuyên workspace mà không tạo race trên output files.

## 11. Configuration cache có điều kiện an toàn riêng

Configuration cache có thể giúp build nhanh hơn khi Gradle tái sử dụng task graph đã cấu hình. Nhưng build logic cần tuân thủ các yêu cầu của configuration cache.

Một số pattern dễ gây vấn đề:

- Build script truy cập trực tiếp mutable state bên ngoài task.
- Task action giữ reference tới Project hoặc model chỉ hợp lệ trong configuration phase.
- Plugin thực hiện side effect trong quá trình configuration.
- Dùng API không tương thích với configuration cache.
- Truy cập file hoặc environment theo cách không được Gradle quản lý qua Provider/task properties.

Nên ưu tiên Provider API, lazy configuration và khai báo task properties rõ ràng. Plugin cần tránh giữ state cấu hình không an toàn giữa các invocation.

Ví dụ bật configuration cache:

~~~bash
./gradlew build --configuration-cache
~~~

Lần đầu Gradle có thể tạo cache entry và báo vấn đề tương thích. Các lần sau có thể tái sử dụng configuration state nếu inputs liên quan không đổi.

### 11.1. Configuration cache không phải nơi lưu output của task

Một task vẫn có thể thực thi lại khi configuration cache được reuse. Ví dụ source file đổi nhưng build configuration không đổi: Gradle có thể tái sử dụng task graph, sau đó xác định compile task cần chạy lại hoặc lấy output từ build cache.

Do đó, một build có thể hiển thị cả thông tin configuration cache reused và task outcome FROM-CACHE/UP-TO-DATE/SUCCESS trong cùng invocation.

## 12. Dependency cache và khóa truy cập

Dependency cache có mục tiêu riêng: quản lý metadata và artifact lấy từ repository. Gradle có thể cache:

- Module metadata.
- Thông tin về repository/module đã resolve.
- Artifact đã tải về.
- Trạng thái cache và thông tin liên quan tới dependency resolution.

Gradle quản lý việc cập nhật các cache này và sử dụng file locking để bảo vệ truy cập đồng thời theo cơ chế của nó.

### 12.1. Dependency cache có thể chia sẻ giữa nhiều build

Nếu nhiều build trên cùng máy dùng chung Gradle User Home, chúng có thể tái sử dụng dependency đã tải. Điều này giảm số lần tải artifact và giảm công việc metadata resolution.

Tuy nhiên, cache dependency không bảo đảm dependency luôn mới nhất. Gradle áp dụng cache policy cho dynamic versions, changing modules và metadata. Nếu cần refresh theo yêu cầu, có thể dùng:

~~~bash
./gradlew build --refresh-dependencies
~~~

Tùy chọn này yêu cầu Gradle kiểm tra lại trạng thái dependency theo cơ chế resolution; nó không phải lệnh xóa toàn bộ mọi cache và cũng không thay thế dependency locking.

### 12.2. Offline mode

Nếu dependency cần thiết đã có trong cache, có thể chạy:

~~~bash
./gradlew build --offline
~~~

Offline mode ngăn Gradle truy cập mạng để resolve dependency. Nếu module hoặc metadata cần thiết chưa có trong cache, build sẽ thất bại.

Offline mode không làm build cache tự nhiên có thêm task output. Nó chủ yếu ảnh hưởng dependency resolution và khả năng truy cập repository.

### 12.3. Dependency locking khác cache locking

Hai khái niệm có tên gần nhau nhưng mục đích khác hẳn:

- **Cache locking:** khóa đồng bộ nội bộ để nhiều process truy cập cache an toàn.
- **Dependency locking:** ghi nhận các version dependency đã resolve để build có thể tái tạo cùng graph theo lock state.

Dependency locking được cấu hình trong build logic và lock state được quản lý trong source control theo workflow của project. Cache locking do Gradle quản lý nội bộ; người dùng không cần tạo lockfile dependency để thay thế nó.

## 13. Dùng cache an toàn trong CI và nhiều developer

Cache có thể giúp CI nhanh hơn đáng kể, nhưng cách chia sẻ cần theo trust boundary và filesystem boundary.

### 13.1. Mỗi job có workspace riêng

Khi chạy nhiều job đồng thời, nên tạo checkout/workspace riêng. Mỗi job có thể dùng local cache riêng hoặc Gradle User Home được chia sẻ trên cùng agent theo cơ chế locking được hỗ trợ.

Không nên cho nhiều job cùng chạy clean/build trên một checkout. Task có thể xóa output của job khác ngay cả khi cache metadata được khóa đúng.

### 13.2. Remote cache dùng để chia sẻ task outputs

Trong CI nhiều agent, remote build cache thường phù hợp hơn việc chia sẻ trực tiếp một thư mục cache local qua network filesystem. Remote cache server có thể cung cấp giao thức đọc/ghi có kiểm soát, authentication và retention.

Hãy xác minh remote cache service hỗ trợ concurrency và durability theo nhu cầu. Gradle client không thể bù cho một cache server lưu trữ dữ liệu không nhất quán.

### 13.3. Giới hạn quyền ghi

Một quy tắc thường dùng:

- Pull request từ fork: chỉ đọc cache.
- Build trên nhánh phát triển được bảo vệ: có thể đọc và ghi theo policy.
- Release pipeline: đọc cache và ghi entry đã được xác minh.
- Local developer: đọc cache chung; quyền push tùy chính sách.

Điều này giúp tránh cache poisoning, trong đó một build không tin cậy ghi output sai hoặc có chủ ý vào cache rồi build tin cậy dùng lại.

### 13.4. Cache entry không thay thế kiểm tra bảo mật

Build cache là cơ chế tối ưu hiệu năng, không phải cơ chế kiểm tra malware, license hoặc provenance. Một cache hit không chứng minh output an toàn về mặt bảo mật. Hãy kiểm soát quyền ghi, bảo vệ transport, quản lý dependency verification và thực hiện security checks ở pipeline phù hợp.

### 13.5. Tránh dùng chung Gradle User Home qua network filesystem không đáng tin

File locking phụ thuộc hành vi filesystem. Một network/shared filesystem không cung cấp semantics locking nhất quán có thể gây vấn đề khi nhiều host cùng truy cập một Gradle User Home.

Với CI nhiều máy, ưu tiên remote build cache qua dịch vụ được thiết kế cho truy cập đồng thời. Nếu buộc phải chia sẻ một cache directory qua filesystem, cần xác nhận filesystem hỗ trợ locking và visibility semantics mà Gradle yêu cầu; không giả định mọi NFS/SMB mount đều tương đương local disk.

## 14. Các nguyên nhân khiến kết quả cache không an toàn

Một task có thể tạo cache hit nhưng output vẫn sai nếu task khai báo sai inputs hoặc có side effect ẩn. Một số nguyên nhân điển hình:

| Vấn đề | Hậu quả | Cách khắc phục |
|---|---|---|
| Không khai báo environment variable | Cache key không đổi dù cấu hình môi trường thay đổi | Đưa giá trị vào task input |
| Đọc file ngoài input collection | File đổi nhưng task vẫn dùng output cũ | Khai báo file là input hoặc chuyển thành provider/input property |
| Dùng absolute workspace path không cần thiết | Cache hit thấp giữa các workspace | Chuẩn hóa path và chọn PathSensitivity phù hợp |
| Output chứa timestamp hiện tại | Cùng input có thể tạo output khác nhau | Loại timestamp khỏi output hoặc mô hình hóa nó thành input |
| Task gọi network không có snapshot identity | Dữ liệu remote thay đổi ngoài cache key | Dùng input snapshot bất biến hoặc không cache task |
| Task có side effect bên ngoài | Cache hit bỏ qua hành động lẽ ra phải xảy ra | Không cache task side effect; tách task tạo artifact khỏi task deploy |
| Không khai báo tool version | Kết quả generator/compiler có thể đổi mà key không đổi | Khai báo tool classpath/version/toolchain |
| Duyệt file theo thứ tự không ổn định | Output thay đổi giữa các lần chạy | Sắp xếp input trước khi xử lý |
| Nhiều job ghi chung build directory | Output bị xóa/ghi đè giữa các invocation | Dùng workspace riêng hoặc serialize |
| Remote cache cho phép push không kiểm soát | Build tin cậy có thể nhận output không đáng tin | Giới hạn quyền ghi và tách trust boundary |

## 15. Quy trình thiết kế một task cacheable

Khi viết custom task, có thể làm theo các bước:

1. **Xác định kết quả:** task tạo ra file/directory nào? Có side effect ngoài filesystem không?
2. **Liệt kê inputs:** source, config, tool version, flags, environment, platform và mọi dữ liệu ảnh hưởng output.
3. **Khai báo properties:** dùng annotation phù hợp như Input, InputFile, InputFiles, Classpath, Nested và các output annotations.
4. **Chọn path sensitivity:** xác định absolute/relative path có thực sự ảnh hưởng kết quả không.
5. **Thiết kế action xác định:** cùng inputs phải tạo cùng outputs; tránh thời gian, random và trạng thái ẩn.
6. **Kiểm tra relocatability:** task có thể chạy ở workspace khác mà output vẫn hợp lệ không?
7. **Chỉ bật cache khi đúng:** dùng CacheableTask sau khi task đáp ứng các điều kiện.
8. **Thử cache hit:** build lần đầu, build ở workspace khác và quan sát FROM-CACHE.
9. **So sánh output:** xác nhận output cache khôi phục giống output được tạo mới.
10. **Kiểm tra môi trường CI:** remote cache access, concurrency, workspace isolation và quyền push.

### 15.1. Tách task tạo artifact khỏi task triển khai

Ví dụ một pipeline web có hai bước:

- Task A: đóng gói WAR từ source và resources.
- Task B: upload WAR lên server hoặc triển khai vào môi trường.

Task A có thể cache nếu inputs/outputs được khai báo đầy đủ và archive reproducible. Task B có side effect bên ngoài nên không nên được xem như task tạo output có thể cache để bỏ qua lần deploy tiếp theo.

Nếu cache nhầm task deploy, Gradle có thể khôi phục trạng thái output mà không thực hiện hành động triển khai. Tách hai trách nhiệm giúp cache an toàn và pipeline dễ hiểu hơn.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Cache locking và dependency locking là một | Một bên đồng bộ truy cập cache; một bên khóa version dependency |
| UP-TO-DATE có nghĩa output được lấy từ remote cache | UP-TO-DATE dùng execution history/output hiện tại; FROM-CACHE mới là khôi phục cache |
| Configuration cache lưu class files | Nó lưu configuration state/task graph, không phải task outputs |
| Dependency cache lưu kết quả compile | Nó lưu metadata/artifact dependency |
| Bật build cache là mọi task đều được cache | Task phải cacheable và khai báo inputs/outputs đúng |
| Cùng tên task thì dùng cùng cache entry | Cache key còn phụ thuộc implementation và inputs |
| Cache hit chứng minh task được thiết kế đúng | Task khai báo thiếu input vẫn có thể tạo cache hit sai |
| Cache lock bảo vệ mọi file trong project | Nó bảo vệ cache theo cơ chế Gradle; output directory vẫn cần quản lý concurrency |
| Hai job có thể dùng chung checkout nếu Gradle User Home có lock | Cùng build directory có thể bị clean/ghi đè; dùng workspace riêng |
| Xóa file lock là cách sửa lock timeout | Trước hết phải xác định process và filesystem đang giữ lock |
| Remote build cache thay artifact repository | Cache task output và repository phát hành module là hai hệ thống |
| Offline mode bật build cache | Offline mode chủ yếu giới hạn truy cập repository/network |
| Task gọi network luôn có thể cache | Chỉ an toàn khi dữ liệu remote có identity/freshness được mô hình hóa |
| Cache hit có nghĩa artifact an toàn và đã được kiểm tra | Cache là tối ưu hiệu năng, không thay thế security/provenance checks |

## 17. Checklist tái sử dụng kết quả an toàn

Trước khi bật cache cho một task hoặc chia sẻ cache trong CI, hãy xác định:

- [ ] Task có tạo output có thể tái tạo hay thực hiện side effect bên ngoài?
- [ ] Mọi file và property ảnh hưởng kết quả đã khai báo là input chưa?
- [ ] Tool version, classpath, flags và toolchain đã được phản ánh chưa?
- [ ] Environment/system properties có ảnh hưởng output đã được khai báo chưa?
- [ ] Outputs có được khai báo đầy đủ và không ghi ra vị trí ẩn không?
- [ ] Cùng inputs có luôn tạo cùng outputs không?
- [ ] Timestamp, random, hostname, locale và network state đã được xử lý chưa?
- [ ] Path sensitivity có phản ánh đúng ý nghĩa đường dẫn không?
- [ ] Task có thể chạy ở workspace khác mà output vẫn hợp lệ không?
- [ ] Task có thực sự phù hợp với CacheableTask không?
- [ ] Build cache local/remote đã được bật đúng phạm vi chưa?
- [ ] Remote cache có quyền đọc/ghi và authentication phù hợp không?
- [ ] Chỉ pipeline tin cậy mới được push cache dùng chung?
- [ ] Mỗi CI job có workspace riêng khi chạy song song không?
- [ ] Cache locking và dependency locking đã được phân biệt?
- [ ] Đã thử build lần đầu, build lại và build ở workspace khác?
- [ ] Output khôi phục từ cache đã được so sánh với output tạo mới?
- [ ] Configuration cache và dependency cache được hiểu đúng mục đích riêng?

## Kết luận

Gradle có nhiều cơ chế cache phục vụ những phần khác nhau của build. Up-to-date checking giúp bỏ qua task khi output trong workspace vẫn hợp lệ. Build cache lưu và khôi phục task outputs theo task identity cùng inputs. Configuration cache tái sử dụng trạng thái cấu hình và task graph. Dependency cache lưu metadata và artifact từ repository. Cache locking bảo vệ dữ liệu cache dùng chung khi nhiều Gradle process truy cập đồng thời.

Tái sử dụng kết quả chỉ an toàn khi task khai báo đầy đủ inputs/outputs, tạo kết quả xác định, xử lý path và môi trường đúng cách, đồng thời không che giấu side effect. Với CI, nên tách workspace cho các job chạy song song, dùng remote cache có quyền truy cập được kiểm soát và chỉ cho pipeline tin cậy ghi cache dùng chung. Cache giúp build nhanh hơn khi hợp đồng đầu vào/đầu ra đúng; nếu hợp đồng sai, cache có thể làm lỗi trở nên khó phát hiện hơn.
