# Bộ nhớ đệm cục bộ và bộ nhớ đệm dùng chung từ xa

Build một dự án Java nhiều lần có thể tốn thời gian vì compiler, test, generator, formatter và các task khác phải xử lý lại những đầu vào đã gặp trước đó. Khi nhiều lập trình viên cùng làm một repository hoặc nhiều CI job build các commit gần nhau, một số công việc còn bị lặp lại giữa các máy. Build cache giúp tái sử dụng kết quả của task khi các đầu vào liên quan không thay đổi.

Gradle hỗ trợ cả **local build cache** trên máy hiện tại và **remote build cache** dùng chung qua mạng. Local cache giúp một máy tái sử dụng output từ những lần build trước; remote cache cho phép máy khác hoặc CI job khác tải lại output đã được tạo và lưu bởi một build trước đó. Khi cấu hình đúng, build có thể nhanh hơn đáng kể mà vẫn tạo kết quả tương đương.

Để dùng cache an toàn, cần phân biệt build cache với dependency cache, incremental build và up-to-date checking. Cache chỉ đáng tin cậy khi task khai báo đầy đủ input/output, có hành vi xác định và không phụ thuộc vào trạng thái ẩn. Remote cache còn cần chính sách quyền ghi/đọc, bảo vệ dữ liệu và quản lý vòng đời cache.

## 1. Build cache giải quyết vấn đề gì?

Giả sử một dự án có các task sinh mã Java từ schema, biên dịch source, chạy static analysis, tạo JAR và sinh báo cáo. Khi source và cấu hình không thay đổi, một số task có thể tạo lại đúng output đã tạo ở lần build trước. Nếu task đủ điều kiện cache và cache có kết quả tương ứng, Gradle có thể lấy output đã lưu thay vì thực thi lại action.

~~~mermaid
flowchart TD
    A["Task cần chạy"] --> B["Tính cache key từ task và inputs"]
    B --> C{"Có output trong cache?"}
    C -->|Có| D["Khôi phục outputs"]
    C -->|Không| E["Thực thi task"]
    E --> F["Lưu outputs vào cache"]
    D --> G["Tiếp tục task graph"]
    F --> G
~~~

Cache không lưu một kết quả chung cho mọi task. Mỗi task có cache key được tính từ implementation và các đầu vào mà Gradle nhận biết. Nếu key khớp và có entry hợp lệ, output có thể được tái sử dụng.

### 1.1. Lợi ích của local cache

Local build cache phù hợp khi một lập trình viên chuyển qua lại giữa các branch, chạy lại build sau khi chỉ thay đổi một phần source, build nhiều module trong cùng repository hoặc chạy các task có output đắt đỏ như compile, code generation và analysis. Local cache tránh tính toán lại trên một máy; nó không tự chia sẻ kết quả với máy đồng đội hoặc CI runner khác.

### 1.2. Lợi ích của remote cache

Remote cache tạo một kho output dùng chung. CI có thể build commit mới và lưu output của các task cacheable; một lập trình viên sau đó checkout cùng commit có thể tải output tương ứng về máy. Một CI job khác cũng có thể tái sử dụng output đó.

Remote cache đặc biệt hữu ích khi nhiều CI job build các nhánh hoặc commit có phần lớn input giống nhau, nhiều lập trình viên cùng làm một monorepo lớn, hoặc build được phân tán trên nhiều runner ngắn hạn không giữ local cache giữa các lần chạy. Remote cache giảm công việc lặp lại giữa các máy, nhưng không thay thế dependency repository và cũng không thay thế việc chạy các task không cacheable.

## 2. Phân biệt build cache, dependency cache và incremental build

Ba khái niệm thường bị gọi chung là “cache”, nhưng chúng giữ những dữ liệu khác nhau.

| Cơ chế | Dữ liệu được tái sử dụng | Mục đích |
|---|---|---|
| Dependency cache | Dependency artifact và metadata đã resolve/tải | Tránh tải lại thư viện từ repository |
| Up-to-date checking | Output của task trong workspace hiện tại khi input/output không đổi | Bỏ qua task đã hoàn thành và vẫn còn hợp lệ |
| Incremental execution | Một phần công việc bên trong task khi có thể xác định phần thay đổi | Chỉ xử lý phần dữ liệu bị ảnh hưởng |
| Build cache | Output của task được lưu theo cache key | Khôi phục output từ lần build trước, có thể từ máy khác |
| Configuration cache | Kết quả cấu hình Gradle build | Giảm thời gian configuration phase |

### 2.1. Dependency cache

Dependency cache lưu các file thư viện và metadata mà Gradle/Maven đã resolve. Ví dụ, một JAR từ Maven Central có thể được lưu trong Gradle User Home hoặc local Maven repository để build sau không cần tải lại. Dependency cache trả lời câu hỏi “Thư viện và metadata nào đã được tải về?”. Nó không phải output của task compile hoặc test.

### 2.2. Up-to-date checking

Gradle so sánh trạng thái input/output của task với lần chạy trước trong workspace. Nếu task được đánh giá là up-to-date, Gradle bỏ qua action và giữ output hiện có. Trạng thái này thường xuất hiện trong log dưới dạng UP-TO-DATE.

Up-to-date checking phụ thuộc vào output vẫn còn trong workspace. Nếu xóa thư mục build hoặc chuyển sang workspace sạch, output không còn để dùng; Gradle có thể phải chạy task hoặc lấy output từ build cache nếu cache được bật.

### 2.3. Incremental execution

Một task incremental có thể chỉ xử lý phần input thay đổi thay vì xử lý lại toàn bộ. Ví dụ compiler có thể chỉ biên dịch những source file bị ảnh hưởng và các source phụ thuộc liên quan. Incremental execution là cách task thực hiện công việc hiệu quả hơn; nó không đồng nghĩa với việc khôi phục toàn bộ output từ cache.

### 2.4. Build cache

Build cache lưu output của task gắn với cache key. Khi một workspace khác cần cùng task với cùng input, Gradle có thể khôi phục output từ local hoặc remote cache. Trong log, task được phục hồi từ cache thường hiển thị FROM-CACHE.

### 2.5. Configuration cache

Configuration cache lưu kết quả cấu hình build để Gradle không phải cấu hình lại toàn bộ build ở mỗi lần chạy. Nó khác build cache: configuration cache không lưu JAR hoặc output của task compile để chia sẻ giữa các máy.

Có thể bật hai cơ chế độc lập:

    ./gradlew build --build-cache --configuration-cache

Mỗi cơ chế có điều kiện tương thích và giới hạn riêng. Một build có configuration cache không có nghĩa task outputs đã được cache, và ngược lại.

## 3. Local build cache của Gradle

Gradle có local build cache dựa trên Gradle User Home. Khi build cache được bật, các task cacheable có thể đọc và ghi output vào cache cục bộ.

### 3.1. Bật local build cache

Có thể bật bằng command-line option:

    ./gradlew build --build-cache

Hoặc đặt trong gradle.properties:

    org.gradle.caching=true

Thiết lập trong gradle.properties của project có thể được commit để áp dụng cho cả nhóm. Thiết lập trong Gradle User Home chỉ tác động đến máy người dùng đó. Nên chọn nơi đặt cấu hình theo chính sách của dự án.

Local build cache mặc định của Gradle thường nằm trong Gradle User Home, dưới thư mục caches/build-cache-1. Có thể cấu hình vị trí local cache trong settings khi cần.

### 3.2. Cấu hình local cache trong settings.gradle

Ví dụ:

    buildCache {
        local {
            directory = new File(rootDir, '.gradle/build-cache')
            removeUnusedEntriesAfterDays = 14
        }
    }

Ví dụ này đặt cache trong thư mục dự án. Trong thực tế, không phải lúc nào cũng nên đặt cache trong repository checkout: cache có thể lớn, tạo nhiều file và không nên được commit. Thông thường dùng vị trí thuộc Gradle User Home là phù hợp hơn. Chỉ cấu hình thư mục trong workspace khi có lý do rõ ràng và đã loại nó khỏi version control.

### 3.3. Cache tồn tại qua các lần build

Local cache có ích khi workspace được giữ lại. Nếu CI runner bị hủy sau mỗi job, local cache cũng có thể mất. Có thể giữ Gradle User Home qua job, dùng CI cache action để lưu/khôi phục thư mục cache hoặc dùng remote build cache.

Không nên cache toàn bộ Gradle User Home một cách tùy tiện nếu không hiểu nội dung và tính tương thích. Gradle User Home chứa dependency cache, Wrapper distribution, daemon state, transforms và các dữ liệu khác; mỗi loại có chính sách vòng đời riêng.

### 3.4. Xem task có được cache không

Khi chạy:

    ./gradlew build --build-cache

Log có thể hiển thị các trạng thái:

- FROM-CACHE: output được lấy từ build cache.
- UP-TO-DATE: output hiện có trong workspace vẫn hợp lệ.
- SUCCESS: task đã thực thi và thành công.
- NO-SOURCE: task không có source phù hợp để xử lý.
- SKIPPED: task bị bỏ qua theo điều kiện hoặc cấu hình.

Không phải task nào cũng được cache. Một số task có side effect, phụ thuộc vào trạng thái bên ngoài hoặc không khai báo input/output đủ chính xác sẽ không phù hợp để cache.

## 4. Task cacheable và cache key

Build cache chỉ an toàn khi output có thể được xác định từ các input đã khai báo. Gradle cần biết task thực sự đọc gì, tạo gì và implementation nào tạo ra kết quả.

### 4.1. Cache key

Cache key là định danh của một lần thực thi task với một bộ input/implementation cụ thể. Các yếu tố có thể tham gia gồm task implementation và implementation classpath, các action của task, tên và giá trị của input properties, nội dung file/directory input sau normalization, tên và loại output properties, classpath snapshot hoặc các thuộc tính đặc thù của task, phiên bản Gradle và các thông tin cần thiết khác trong cơ chế cache.

Nếu một input được khai báo đúng và thay đổi, cache key sẽ thay đổi. Entry cũ không còn được xem là kết quả phù hợp cho bộ input mới.

### 4.2. Input phải được khai báo đầy đủ

Giả sử task tạo file Java từ schema. Nếu task đọc schema nhưng không khai báo schema là input, Gradle có thể không nhận ra schema đã thay đổi. Khi đó, task có thể bị đánh dấu up-to-date hoặc lấy output cache cũ.

Một task type nên mô tả input/output bằng các annotation/property phù hợp:

    abstract class GenerateSources extends DefaultTask {
        @InputFile
        abstract RegularFileProperty getSchemaFile()

        @Input
        abstract Property<String> getGeneratorVersion()

        @OutputDirectory
        abstract DirectoryProperty getOutputDirectory()

        @TaskAction
        void generate() {
            // Đọc schemaFile, dùng generatorVersion và ghi outputDirectory.
        }
    }

Đây là ví dụ minh họa cấu trúc task type. Implementation thật cần dùng API generator, xử lý lỗi và đảm bảo ghi output một cách xác định.

### 4.3. Output phải được khai báo chính xác

Nếu task ghi một file nhưng không khai báo file đó là output, Gradle không thể quản lý đầy đủ trạng thái output. Điều này làm giảm khả năng up-to-date checking và cache.

Ngược lại, không khai báo một thư mục rộng hơn mức cần thiết. Nếu output directory chứa cả file do người dùng tạo hoặc file của task khác, cache restore có thể ghi đè hoặc làm mất dữ liệu không thuộc task.

### 4.4. Task phải có hành vi xác định

Với cùng implementation và cùng input, task cacheable nên tạo cùng output. Nếu task đọc thời gian hiện tại, số ngẫu nhiên, hostname, trạng thái mạng hoặc dữ liệu remote mà không khai báo các giá trị đó là input, cache có thể trả kết quả không còn đúng.

Ví dụ không phù hợp:

    tasks.register('writeBuildTime') {
        outputs.file(layout.buildDirectory.file('build-info.txt'))
        doLast {
            def now = new Date()
            // Ghi thời gian hiện tại vào file.
        }
    }

Task này tạo output thay đổi theo thời điểm chạy, dù các input được khai báo không đổi. Không nên cache nó như một task thuần nếu timestamp là yêu cầu của output. Có thể khai báo timestamp như input có chủ đích, hoặc tách metadata thời gian khỏi output cần tái sử dụng.

### 4.5. Side effect không nên bị cache

Task gửi email, publish artifact, deploy service, ghi database hoặc thay đổi trạng thái hệ thống bên ngoài thường không phù hợp với build cache. Nếu cache hit, Gradle có thể khôi phục output mà không chạy side effect; hành vi đó không tương đương với việc thực hiện hành động publish/deploy.

Chỉ cache task tạo output xác định. Các hành động có side effect nên là task riêng và không được coi là output thuần có thể tái sử dụng.

## 5. Cacheability trong Gradle task

Task built-in của Gradle và plugin có thể được đánh dấu cacheable. Với task custom, có thể dùng @CacheableTask khi task đáp ứng điều kiện.

Ví dụ:

    @CacheableTask
    abstract class NormalizeSchema extends DefaultTask {
        @InputFile
        @PathSensitive(PathSensitivity.RELATIVE)
        abstract RegularFileProperty getInputSchema()

        @OutputFile
        abstract RegularFileProperty getOutputSchema()

        @TaskAction
        void normalize() {
            // Đọc inputSchema và ghi outputSchema.
        }
    }

@CacheableTask cho Gradle biết output của task có thể được lưu và tái sử dụng. Annotation không tự làm task an toàn; developer vẫn phải khai báo đầy đủ input/output và bảo đảm action xác định.

### 5.1. @DisableCachingByDefault

Một số task có thể được đánh dấu không cache theo mặc định vì Gradle/plugin không thể bảo đảm tính xác định hoặc cần người dùng chủ động quyết định. Nếu task có annotation @DisableCachingByDefault, cần hiểu lý do trước khi ghi đè chính sách.

Không nên bật cache chỉ để tăng số task FROM-CACHE. Mục tiêu là kết quả đúng và build nhanh hơn, không phải tỷ lệ cache hit cao bằng mọi giá.

### 5.2. Input normalization và path sensitivity

Hai workspace có thể nằm ở đường dẫn khác nhau, ví dụ một runner ở /home/runner/work/project còn máy lập trình viên ở /Users/dev/project. Nếu task chỉ cần nội dung file tương đối với input root, absolute path không nên làm cache key khác nhau.

Gradle hỗ trợ normalization và PathSensitivity để xác định cách đường dẫn tham gia input fingerprint. Các mức thường gặp gồm:

- ABSOLUTE: đường dẫn tuyệt đối là một phần của input.
- RELATIVE: đường dẫn tương đối trong input root được dùng.
- NAME_ONLY: chỉ tên file được xem xét.
- NONE: đường dẫn không tham gia, chỉ nội dung file.

Chọn normalization theo ý nghĩa thật của task. Nếu task sử dụng cấu trúc thư mục, dùng NONE hoặc NAME_ONLY có thể làm cache key bỏ qua thông tin cần thiết và trả output sai. Nếu task phụ thuộc vào absolute path, dùng RELATIVE có thể khiến cache tái sử dụng output không hợp lệ.

### 5.3. Classpath normalization

Với task nhận classpath, thứ tự hoặc nội dung JAR có thể ảnh hưởng kết quả. Gradle có cơ chế classpath normalization/snapshot để tránh cache miss không cần thiết khi thay đổi không ảnh hưởng đến kết quả theo cách task xử lý. Không tự bỏ qua metadata hoặc file classpath nếu task thực sự cần chúng.

## 6. Remote build cache hoạt động như thế nào?

Remote build cache là một dịch vụ hoặc backend lưu cache entries và cho phép nhiều Gradle client truy cập.

~~~mermaid
flowchart TD
    A["Developer workstation"] --> B["Local cache"]
    C["CI runner A"] --> D["Remote build cache"]
    E["CI runner B"] --> D
    A <--> D
    B --> A
    D --> F["Task outputs đã lưu"]
~~~

Một client có thể kiểm tra local cache trước; nếu không tìm thấy entry phù hợp, Gradle có thể truy vấn remote cache. Khi task thực thi thành công và được phép ghi cache, output có thể được lưu lên remote để client khác sử dụng.

### 6.1. Đọc cache và ghi cache là hai quyền khác nhau

Không phải client nào cũng nên được phép ghi remote cache. Một CI job chạy từ pull request không đáng tin cậy có thể tạo output không an toàn hoặc cố tình đầu độc cache. Nhiều tổ chức cấu hình:

- Developer workstation: đọc remote cache; ghi local cache.
- CI cho branch tin cậy: đọc và ghi remote cache.
- CI cho fork/untrusted pull request: chỉ đọc cache hoặc không truy cập cache dùng chung.
- Release pipeline: đọc cache đã tin cậy, có thể ghi theo policy riêng.

Remote cache nên có quyền read/write riêng biệt. Nếu backend hỗ trợ, hãy cấp credentials tối thiểu cần thiết cho từng loại runner.

### 6.2. Remote cache không thay thế local cache

Local cache giúp giảm request mạng và lưu output gần client. Remote cache giúp chia sẻ kết quả giữa các client. Một build có thể dùng cả hai: local cache được kiểm tra trước, remote cache là nguồn bổ sung.

Khi remote không truy cập được, build có thể tiếp tục bằng local cache và thực thi task còn thiếu, tùy cấu hình/error policy. Cần xác định rõ tổ chức muốn build fail khi cache server lỗi hay muốn fallback để build vẫn hoàn tất.

### 6.3. Cache key giúp client khác nhau dùng chung output

Một runner khác có thể có workspace path khác, nhưng nếu task implementation và normalized inputs tương đương thì cache key có thể giống nhau. Đây là nền tảng để remote cache chia sẻ output qua nhiều máy.

Nếu task đưa absolute path, hostname hoặc environment không ổn định vào input, cache key có thể khác giữa các runner và làm giảm cache hit. Nếu bỏ qua một input thực sự quan trọng, cache hit có thể trả output sai. Cần cân bằng relocatability và tính đúng đắn.

## 7. Cấu hình remote build cache trong Gradle

Gradle có API cấu hình remote build cache trong settings file. Backend phổ biến có thể là HTTP cache server hoặc dịch vụ tích hợp với nền tảng build như Develocity. Cấu hình chính xác phụ thuộc backend và plugin được sử dụng.

### 7.1. Cấu hình HTTP remote cache

Ví dụ Groovy DSL trong settings.gradle:

    buildCache {
        local {
            enabled = true
        }
        remote(HttpBuildCache) {
            url = 'https://build-cache.example.com/cache/'
            enabled = true
            push = false
        }
    }

Ở ví dụ này, client có thể đọc remote cache nhưng không ghi. Điều này phù hợp với máy lập trình viên hoặc job không được tin cậy. URL là placeholder; backend thật cần hỗ trợ giao thức Gradle HTTP Build Cache.

### 7.2. Cho CI tin cậy quyền push

CI tin cậy có thể được cấu hình để ghi remote cache:

    buildCache {
        local {
            enabled = true
        }
        remote(HttpBuildCache) {
            url = 'https://build-cache.example.com/cache/'
            enabled = true
            push = System.getenv('CI') == 'true'
        }
    }

Đây là ví dụ đơn giản. Trong hệ thống thực tế, không nên chỉ dựa vào một biến CI có thể bị giả mạo bởi job không tin cậy. Hãy dùng điều kiện branch/event/identity được bảo vệ trong pipeline và cấp credential write chỉ cho runner tin cậy.

### 7.3. Cấu hình credentials

HTTP remote cache có thể cần xác thực. Có thể lấy username/password từ biến môi trường hoặc secret store:

    remote(HttpBuildCache) {
        url = 'https://build-cache.example.com/cache/'
        credentials {
            username = System.getenv('BUILD_CACHE_USER')
            password = System.getenv('BUILD_CACHE_TOKEN')
        }
        push = false
    }

Ví dụ minh họa cách cấp credentials; cần xác nhận backend và Gradle version hỗ trợ kiểu xác thực này. Không commit token vào settings.gradle hoặc gradle.properties được chia sẻ. Không in secret vào log. Nên tách read token và write token nếu backend hỗ trợ.

### 7.4. Tách cấu hình theo môi trường

Một số nhóm muốn bật remote cache ở CI nhưng không bắt buộc trên máy cá nhân. Có thể dùng biến môi trường hoặc Gradle property để điều khiển remote cache, nhưng cần bảo đảm điều kiện không làm thay đổi nội dung artifact.

Ví dụ:

    def cacheUrl = System.getenv('BUILD_CACHE_URL')

    buildCache {
        local {
            enabled = true
        }
        if (cacheUrl != null) {
            remote(HttpBuildCache) {
                url = uri(cacheUrl)
                enabled = true
                push = false
            }
        }
    }

Nếu settings được cấu hình theo môi trường, ghi nhận cấu hình cache được dùng để chẩn đoán. Remote cache nên là tối ưu hóa; việc thiếu cache URL không nên làm thay đổi logic sản phẩm hoặc khiến task trả output khác.

## 8. Chiến lược cache trong CI

CI runner thường được tạo mới hoặc tái sử dụng trong thời gian ngắn. Local cache trên runner có thể mất sau job, vì vậy remote cache có thể cải thiện tốc độ đáng kể.

### 8.1. CI producer và CI consumer

Một pipeline có thể được chia thành:

1. CI producer chạy trên branch tin cậy, thực thi build và push task outputs.
2. CI consumer chạy trên branch khác hoặc pull request, đọc outputs đã cache.
3. Consumer chỉ push nếu event/branch được tin cậy theo policy.

Remote cache có thể giúp consumer bỏ qua compile/generation/analysis đã có output tương ứng. Những task phụ thuộc source thay đổi vẫn phải chạy.

### 8.2. Ví dụ GitHub Actions

Ví dụ workflow rút gọn:

    jobs:
      build:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-java@v4
            with:
              distribution: temurin
              java-version: '21'
          - name: Build
            run: ./gradlew clean build --build-cache

Đoạn trên chỉ bật build cache trong Gradle; để dùng remote cache, settings.gradle cần cấu hình backend và credentials. Nếu dùng local cache của runner, hiệu quả phụ thuộc runner có giữ Gradle User Home qua job hay không.

### 8.3. Không push cache từ untrusted pull request

Một pull request từ fork có thể thay đổi build script, task implementation hoặc mã generator. Nếu job đó có quyền ghi remote cache dùng chung, nó có thể ghi entry được các build tin cậy sử dụng sau này.

Hãy cấp quyền push chỉ cho workflow/branch tin cậy. Job untrusted có thể không sử dụng remote cache, chỉ đọc remote cache với token read-only hoặc dùng cache namespace riêng không được build phát hành tin cậy sử dụng.

Việc kiểm soát quyền cache là một phần của bảo vệ chuỗi cung ứng phần mềm.

### 8.4. Cache namespace và phân vùng

Tổ chức có thể cần tách cache theo project/repository, branch, mức độ tin cậy của source, JDK/OS/architecture nếu các đầu vào đó ảnh hưởng output, hoặc môi trường phát triển/kiểm thử/phát hành.

Gradle cache key đã phản ánh nhiều input của task, nhưng namespace riêng có thể giúp phân tách quyền và vòng đời. Không dùng namespace để che giấu việc task thiếu input declaration.

## 9. Bảo mật và tính toàn vẹn của remote cache

Remote cache chứa output được build từ source và dependency. Nếu một client không đáng tin cậy ghi entry sai, client khác có thể khôi phục output đó mà không thực thi lại task. Vì vậy, remote cache cần được coi là một phần của hạ tầng build quan trọng.

### 9.1. Quyền truy cập tối thiểu

- Tạo credential read-only cho developer và untrusted CI khi phù hợp.
- Chỉ cấp quyền write cho pipeline tin cậy.
- Tách quyền quản trị/xóa cache khỏi quyền build thông thường.
- Luân chuyển token theo chính sách tổ chức.
- Giới hạn network access và audit log nếu backend hỗ trợ.

### 9.2. Không đưa secret vào cache key hoặc output

Task không nên ghi token, password hoặc private key vào output được cache. Cache entry có thể được chia sẻ rộng hơn workspace ban đầu. Nếu output cần cấu hình nhạy cảm, hãy giữ secret ở runtime và không cache file chứa secret.

Secret có thể ảnh hưởng kết quả task, nhưng không nên khai báo giá trị secret như một input thông thường nếu điều đó làm lộ nó trong metadata/log/cache key. Cần thiết kế task để dùng secret an toàn và chỉ cache output không nhạy cảm. Nếu không thể tách, không cache task đó.

### 9.3. Tin cậy output được cache

Remote cache không tự chứng minh output đúng chỉ vì nó được lưu ở backend. Tính đúng đắn phụ thuộc vào task implementation, cache key, input declaration và quyền ghi. Chỉ các build đáng tin cậy nên có quyền tạo entries dùng chung.

Nếu nghi ngờ cache bị đầu độc hoặc có output bất thường, hãy vô hiệu hóa đọc remote cache trong phạm vi bị ảnh hưởng, xóa/invalidate entries qua cơ chế quản trị backend, chạy build sạch từ source tin cậy và điều tra audit log. Không tiếp tục phát hành dựa trên output không xác định nguồn gốc.

## 10. Cache miss, cache hit và các nguyên nhân phổ biến

Cache hit xảy ra khi client tìm thấy entry cho cache key cần thiết và có thể khôi phục output. Cache miss xảy ra khi không có entry phù hợp hoặc entry không thể sử dụng.

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không có FROM-CACHE dù build trước đã chạy | Task không cacheable hoặc cache chưa bật | Kiểm tra task type và --build-cache |
| Cache miss giữa hai máy | Input path/normalization, JDK, plugin hoặc task implementation khác | So sánh cache key inputs và môi trường |
| Task luôn chạy lại | Input thay đổi, output bị xóa hoặc task không khai báo output đúng | Kiểm tra input/output và task action |
| Cache hit nhưng output sai | Input bị bỏ sót hoặc task không xác định | Sửa task contract, vô hiệu hóa cache task bị lỗi và build lại |
| Remote cache không truy cập được | URL, DNS, TLS, auth hoặc backend outage | Kiểm tra kết nối và quyền; xác định fallback policy |
| Developer đọc được nhưng không push | Token read-only hoặc push policy | Kiểm tra quyền ghi của identity tin cậy |
| CI không tái sử dụng cache | Runner mới, namespace khác hoặc remote cache chưa bật | Kiểm tra settings và remote cache endpoint |
| Cache tăng dung lượng nhanh | TTL/cleanup chưa phù hợp hoặc nhiều key không tái sử dụng | Thiết lập retention và dọn entries cũ |

### 10.1. Cache miss không nhất thiết là lỗi

Cache miss có thể xảy ra bình thường khi source hoặc input thay đổi. Task cần chạy lại và tạo output mới. Không nên coi mọi cache miss là vấn đề cần khắc phục; mục tiêu là hit ở những task có input tương đương, không phải ép hit cho mọi task.

### 10.2. Cache hit không phải bằng chứng task đúng

Cache hit chỉ cho biết Gradle tìm thấy output có key tương ứng. Nếu task khai báo thiếu input, key không đại diện đầy đủ cho trạng thái thật. Khi đó, cache hit có thể tái sử dụng output lỗi thời.

### 10.3. Xem log để phân biệt trạng thái

Chạy:

    ./gradlew build --build-cache --info

Log chi tiết có thể cho biết task được đánh giá up-to-date, lấy từ cache hay thực thi. Khi cần điều tra sâu hơn, bật mức log phù hợp và xem cache backend log nếu có quyền. Tránh chia sẻ log chứa credentials hoặc đường dẫn nhạy cảm.

## 11. Relocatability: chia sẻ cache giữa các workspace khác đường dẫn

Một lợi ích lớn của remote cache là tái sử dụng output trên máy có workspace path khác. Ví dụ, một runner build ở /home/runner/work/project còn máy lập trình viên build ở /Users/dev/project.

Nếu task đưa absolute path vào cache key hoặc ghi absolute path vào output, entry có thể không tái sử dụng được hoặc output được khôi phục có thể trỏ sai vị trí.

### 11.1. Dùng đường dẫn tương đối khi phù hợp

Với input file, chọn PathSensitivity phù hợp. Nếu task chỉ quan tâm nội dung và cấu trúc tương đối, khai báo relative sensitivity giúp cache key không phụ thuộc root workspace.

Ví dụ:

    @InputFiles
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract ConfigurableFileCollection getSourceFiles()

Đây là minh họa cho task type. Cần chọn sensitivity đúng với cách task sử dụng đường dẫn.

### 11.2. Không ghi workspace absolute path vào output

Generated file hoặc manifest có thể vô tình chứa đường dẫn máy build. Nếu output đó được cache, máy khác nhận lại file chứa đường dẫn không hợp lệ.

Nếu đường dẫn cần thiết cho runtime, hãy xác định nó là cấu hình runtime hoặc input thực sự. Nếu chỉ dùng để log/debug, cân nhắc loại khỏi output được cache hoặc chuẩn hóa thành đường dẫn tương đối.

### 11.3. Hệ điều hành và kiến trúc khác nhau

Output có thể phụ thuộc OS hoặc architecture, đặc biệt khi task tạo native binary, file có line ending khác nhau hoặc sử dụng công cụ hệ thống. Những thuộc tính ảnh hưởng output phải được thể hiện trong input/cache key hoặc cache namespace.

Không nên chia sẻ cùng output giữa Linux và Windows nếu task không được thiết kế để tạo output tương đương trên cả hai. Có thể dùng cache namespace hoặc input property mô tả platform khi cần.

## 12. Cache cho task sinh mã, compile, test và đóng gói

Không phải task nào cũng có cùng đặc tính cache.

### 12.1. Code generation

Task sinh mã từ schema là ứng viên cache tốt nếu schema và tất cả file tham chiếu được khai báo là input, generator version/options/template được khai báo, output directory được khai báo chính xác, generator không đọc dữ liệu mạng hoặc thời gian hiện tại một cách ẩn, và output không chứa đường dẫn máy hoặc dữ liệu ngẫu nhiên không kiểm soát.

Nếu generator lấy schema từ URL thay đổi theo thời gian, hãy tải schema thành file có version/checksum trước, rồi dùng file đó làm input.

### 12.2. Java compilation

Gradle JavaCompile task có thể cache output khi input source, classpath, compiler/toolchain và options được quản lý. JDK/compiler version, annotation processor và compiler arguments có thể ảnh hưởng output.

Nếu task tùy chỉnh sửa class file sau compile mà không khai báo đúng, cache của compile không thể đại diện cho kết quả cuối cùng. Hãy để mỗi bước có task riêng và input/output rõ ràng.

### 12.3. Unit test

Test có thể cache trong một số trường hợp, nhưng cần cẩn trọng. Test đọc database bên ngoài, thời gian hiện tại, random data, network response hoặc trạng thái dùng chung có thể không xác định. Một cache hit có thể bỏ qua việc thực thi test trên môi trường hiện tại.

Nếu test là kiểm tra integration cần xác nhận trạng thái hệ thống hiện tại, không nên cache kết quả một cách mù quáng. Cần đánh giá test task, inputs và side effects trước khi bật caching.

### 12.4. Static analysis

Analyzer có thể cache report nếu source, classpath, rule set, analyzer version và options được khai báo đầy đủ. Nếu rule profile tải từ server hoặc phụ thuộc trạng thái server, cần version hóa/cố định profile hoặc khai báo input thích hợp.

### 12.5. Archive và packaging

Task đóng gói có thể cache nếu file đầu vào, manifest, version, timestamp policy, permissions và archive options được khai báo. Nếu archive nhúng build timestamp hiện tại, output không còn ổn định trừ khi timestamp được cố định như input.

### 12.6. Publish và deploy

Publish/deploy có side effect ra ngoài nên không nên cache như task tạo output thuần. Một lần cache hit không được làm cho artifact mới tự động xuất hiện trên remote repository. Hãy để task publish thực thi khi được yêu cầu và dùng cache cho các bước compile/package đứng trước nó.

## 13. Remote cache và Maven

Maven có local repository cache cho dependency/artifact đã tải hoặc cài. Cơ chế này khác với remote task-output build cache của Gradle.

Maven core lifecycle truyền thống không cung cấp cùng một mô hình build cache task-output tích hợp như Gradle. Có thể dùng các extension hoặc dịch vụ build cache bên ngoài tùy hệ sinh thái, nhưng cần đánh giá rõ plugin/extension, phiên bản Maven, phạm vi goal được cache và các điều kiện an toàn.

### 13.1. Local repository không phải remote build cache

Thư mục ~/.m2/repository lưu dependency và artifact theo tọa độ Maven. Nó giúp Maven tránh tải lại JAR/POM, nhưng không có nghĩa Maven có thể lấy output compile/test của project khác từ một cache dùng chung.

### 13.2. CI cache cho Maven

CI thường cache local Maven repository để giảm thời gian tải dependency. Ví dụ workflow có thể lưu ~/.m2/repository giữa các job. Đây là dependency cache; compiler/test/package goals vẫn được thực thi theo lifecycle nếu không có extension build cache riêng.

Khi chia sẻ local repository cache giữa job, cần cân nhắc snapshot update policy, file lock/concurrency, dung lượng và tính an toàn của artifact. Không để cache từ một job untrusted trở thành nguồn artifact đáng tin cậy mà không có verification.

### 13.3. Extension build cache

Nếu dự án Maven dùng build cache extension, hãy đọc tài liệu của extension đang cài và xác định goal nào có thể cache, cách tính key và input fingerprint, cache local/remote backend nào được hỗ trợ, cách cấu hình read/write và authentication, cách xử lý file ngoài/environment/side effect và cách invalidate cache khi thay đổi plugin/extension.

Không suy ra hành vi của một extension từ Gradle. Mỗi giải pháp có mô hình cache, giới hạn và cách cấu hình riêng.

## 14. Quản lý dung lượng và vòng đời cache

Cache có thể tăng dung lượng theo số task, version, branch và input combinations. Cần chính sách cleanup để giữ chi phí lưu trữ và thời gian truy cập hợp lý.

### 14.1. Local cache retention

Gradle local cache có thể dọn entries không dùng trong một khoảng thời gian. Tham số removeUnusedEntriesAfterDays có thể được cấu hình cho local cache. Không nên đặt retention quá ngắn khiến các branch thường xuyên mất cache; cũng không nên giữ mọi entry vô hạn.

### 14.2. Remote cache retention

Remote backend thường có chính sách TTL, cleanup hoặc quota riêng. Có thể giữ entries lâu hơn cho branch chính và release build, nhưng dọn cache thử nghiệm hoặc branch đã xóa sớm hơn.

Nếu backend hỗ trợ namespace, quota và audit, hãy dùng chúng để quản lý theo project/branch/trust level. Cần theo dõi dung lượng tổng và tốc độ tăng, cache hit/miss rate, số lượng entry cũ không được dùng, request latency/lỗi backend và chi phí lưu trữ/truyền dữ liệu.

### 14.3. Invalidate cache có chủ đích

Khi task implementation sai, input declaration thay đổi hoặc cache bị nghi ngờ, có thể cần invalidate entries. Hãy ưu tiên namespace/retention hoặc công cụ quản trị backend thay vì xóa toàn bộ cache cho mọi project.

Thay đổi task implementation thường làm cache key đổi nếu implementation fingerprint được Gradle nhận diện. Tuy vậy, nếu task logic phụ thuộc external input không khai báo, key có thể không đổi. Khi sửa lỗi cacheability, cần xem xét invalidate entries cũ để tránh output sai tiếp tục được tái sử dụng.

## 15. Đo hiệu quả cache

Không nên đánh giá cache chỉ bằng số task FROM-CACHE. Hãy đo thời gian build, thời gian tải cache, cache hit/miss theo task và ảnh hưởng tới độ ổn định.

Các chỉ số hữu ích gồm tổng thời gian build trước/sau khi bật cache, thời gian configuration và execution, cache hit rate theo nhóm task, kích thước dữ liệu tải lên/tải xuống, số lần remote cache request lỗi/timeout, thời gian task thực thi so với thời gian restore output và số build phải chạy lại do cache output không hợp lệ.

Một task nhỏ có thể tốn ít thời gian thực thi hơn thời gian tải output từ remote. Trong trường hợp đó, cache task có thể không đem lại lợi ích. Một task compile lớn hoặc generator đắt đỏ thường có giá trị cache cao hơn.

### 15.1. Bắt đầu bằng task đắt đỏ và xác định

Hãy bật cache cho task built-in hoặc custom task đã được kiểm tra input/output. Đo kết quả trước khi mở rộng. Nếu cache hit thấp, kiểm tra task có thực sự cacheable không, input có thay đổi liên tục không, absolute path hoặc timestamp có làm key khác giữa máy không, plugin/JDK/OS có khác nhau không, task có khai báo thừa input không và output có quá lớn để tải từ remote không.

### 15.2. So sánh cold build và warm build

Cold build là lần chạy chưa có output/cache phù hợp. Warm build là lần chạy sau có thể tái sử dụng output. Cần đo cả hai để hiểu thời gian đầu tiên và các lần chạy tiếp theo.

Khi đánh giá remote cache, thử trên một workspace/runner khác để xác nhận output thật sự được tải qua mạng. Chạy lại trên cùng workspace có thể chỉ cho thấy UP-TO-DATE hoặc local cache hit, chưa chứng minh remote cache đang hoạt động.

## 16. Chẩn đoán khi cache không hoạt động hoặc trả output sai

### 16.1. Task không được cache

Kiểm tra:

1. Build cache đã bật bằng --build-cache hoặc org.gradle.caching=true chưa?
2. Task có cacheable không?
3. Task có khai báo input/output đầy đủ không?
4. Có lý do nào khiến task bị disable caching không?
5. Task có chạy trong configuration/command phù hợp không?

### 16.2. Remote cache không được truy cập

Kiểm tra URL backend, remote cache enabled, quyền read, TLS/DNS/proxy/firewall, credentials và khả năng tương thích backend với Gradle HTTP Build Cache protocol.

### 16.3. Remote cache đọc được nhưng không ghi được

Kiểm tra push, quyền write và identity của runner. Cấu hình read-only có thể hoạt động đúng dù CI không upload entry. Không cấp write token cho mọi job chỉ để tăng cache hit.

### 16.4. Cache hit nhưng kết quả sai

Đây là vấn đề nghiêm trọng hơn cache miss. Hãy dừng sử dụng cache entry/task bị ảnh hưởng nếu cần, chạy task không dùng cache để xác định output thực thi trực tiếp, so sánh input thực tế với input đã khai báo, tìm file/environment/network/time/random dependency chưa được khai báo, sửa task implementation và input/output contract, invalidate entries cũ nếu chúng có thể tiếp tục được chọn, rồi chạy lại từ workspace sạch.

Không khắc phục bằng cách thêm một input giả hoặc xóa cache thường xuyên. Cần sửa nguyên nhân làm cache key không đại diện cho kết quả task.

### 16.5. Cache hit thấp giữa local và CI

So sánh Gradle version, plugin implementation, JDK, compiler toolchain, build properties, path sensitivity, environment inputs và dependency resolution. Khác biệt thật sự trong input phải tạo cache miss; khác biệt không ảnh hưởng kết quả nên được chuẩn hóa nếu task có thể làm điều đó an toàn.

## 17. Những nguyên tắc an toàn khi dùng cache chung

- Chỉ cache task có output xác định từ input đã khai báo.
- Không cache task publish, deploy hoặc task có side effect không thể tái tạo.
- Không đưa secret vào cache entry, task output hoặc log.
- Chỉ cấp quyền push cho CI/source đáng tin cậy.
- Cân nhắc read-only cache cho developer và untrusted pull request.
- Dùng HTTPS và authentication phù hợp cho remote backend.
- Theo dõi backend, quyền truy cập, dung lượng và cache hit rate.
- Có cách invalidate cache khi task implementation hoặc cache data bị lỗi.
- Kiểm tra task cacheability sau khi nâng Gradle/plugin hoặc thay đổi generator.
- Đừng dùng cache để che giấu input/output declaration thiếu chính xác.

## 18. Ví dụ chiến lược local và remote cache cho một nhóm

Giả sử nhóm có repository Gradle nhiều module:

- Developer bật local build cache để tái sử dụng output trên máy.
- Developer đọc remote cache bằng token read-only.
- CI branch chính có quyền đọc và ghi remote cache.
- CI pull request từ fork chỉ đọc cache hoặc không dùng cache chung.
- Task compile, code generation và static analysis được cache khi đã xác nhận input/output.
- Test tích hợp phụ thuộc database hoặc API thật không được cache nếu cần xác nhận trạng thái hiện tại.
- Publish/deploy luôn thực thi theo release pipeline.

Một settings.gradle có thể cấu hình:

    buildCache {
        local {
            enabled = true
        }
        remote(HttpBuildCache) {
            url = 'https://build-cache.example.com/cache/'
            enabled = System.getenv('BUILD_CACHE_ENABLED') == 'true'
            push = System.getenv('TRUSTED_CACHE_WRITER') == 'true'
            credentials {
                username = System.getenv('BUILD_CACHE_USER')
                password = System.getenv('BUILD_CACHE_TOKEN')
            }
        }
    }

Đây là minh họa cấu hình. Các biến TRUSTED_CACHE_WRITER và BUILD_CACHE_ENABLED cần được thiết lập từ pipeline được bảo vệ, không nhận tùy tiện từ input của pull request. Credentials write nên chỉ có mặt ở job tin cậy; job untrusted không nên nhận token write ngay cả khi code build yêu cầu.

Trong CI, có thể chạy:

    ./gradlew clean build --build-cache

Nếu clean chỉ xóa output project mà không xóa Gradle build cache, task vẫn có thể khôi phục output từ local/remote cache. Vì vậy clean build có thể vẫn hiển thị FROM-CACHE; muốn đo cold build thật, cần dùng cache directory/namespace sạch hoặc tạm vô hiệu hóa cache trong môi trường kiểm thử.

## 19. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Dependency cache và build cache là một | Một bên lưu dependency/metadata, một bên lưu task outputs |
| Task UP-TO-DATE nghĩa là lấy từ remote cache | UP-TO-DATE dùng output hiện có trong workspace; FROM-CACHE là output được khôi phục từ build cache |
| Bật --build-cache khiến mọi task được cache | Chỉ task cacheable và có input/output hợp lệ mới có thể dùng |
| Remote cache là nơi lưu JAR dependency | Remote build cache chủ yếu lưu task output; dependency repository có vai trò riêng |
| Cache hit chứng minh task đã chạy trên máy hiện tại | Cache hit có thể bỏ qua action và khôi phục output đã tạo ở build khác |
| Có thể cache mọi test | Test phụ thuộc trạng thái bên ngoài/side effect có thể không an toàn |
| Task có @CacheableTask chắc chắn an toàn | Annotation không thay thế input/output declaration và tính xác định |
| Cache miss luôn là lỗi cấu hình | Input thay đổi hoặc entry chưa tồn tại là cache miss bình thường |
| Xóa cache thường xuyên là cách bảo đảm đúng | Cần sửa task contract; xóa cache không sửa input bị bỏ sót |
| Mọi CI job nên push remote cache | Chỉ source/runner tin cậy mới nên có quyền ghi cache dùng chung |
| Build cache và configuration cache giống nhau | Một bên lưu task outputs, một bên lưu kết quả configuration |
| Maven local repository là remote task cache | Nó chủ yếu lưu dependency/artifact theo tọa độ Maven |

## 20. Checklist triển khai build cache

Trước khi bật cache rộng rãi, hãy xác nhận:

1. Task nào có thời gian thực thi đáng kể và phù hợp để cache?
2. Task đã khai báo đầy đủ input, output, implementation và normalization chưa?
3. Cùng input có luôn tạo cùng output không?
4. Có phụ thuộc ẩn vào thời gian, random, environment, network hoặc filesystem không?
5. Output có chứa absolute path, secret hoặc dữ liệu riêng của runner không?
6. Local cache đặt ở đâu và có retention phù hợp không?
7. Remote backend có TLS, authentication, monitoring và cleanup không?
8. Ai được read, ai được push, job nào được xem là trusted?
9. Có thể kiểm tra cache hit trên workspace/runner khác không?
10. Có quy trình invalidate cache khi phát hiện output sai không?
11. CI có lưu log và report để chẩn đoán cache miss/failure không?
12. Có đo thời gian build và chi phí truyền cache trước/sau khi triển khai không?

Local build cache giúp một máy tái sử dụng task output; remote build cache mở rộng việc tái sử dụng đó giữa nhiều máy và CI job. Hai cơ chế chỉ phát huy hiệu quả khi task có input/output chính xác, hành vi xác định và cache key phản ánh đầy đủ các yếu tố ảnh hưởng kết quả. Cần phân biệt chúng với dependency cache, up-to-date checking, incremental execution và configuration cache. Remote cache còn đòi hỏi phân quyền đọc/ghi, bảo vệ output và quản lý vòng đời. Khi bắt đầu từ các task đắt đỏ, đo cache hit thực tế và chỉ cho pipeline tin cậy quyền push, nhóm có thể rút ngắn build mà vẫn giữ được tính đúng đắn và khả năng truy vết.
