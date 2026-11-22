# Phân biệt cache cấu hình với cache đầu ra tác vụ

Gradle có nhiều cơ chế giúp build nhanh hơn khi chạy lặp lại. Hai cơ chế thường được nhắc tới là **Configuration Cache** và **Build Cache**. Tên gọi gần nhau nhưng chúng lưu những loại dữ liệu khác nhau và tối ưu những giai đoạn khác nhau của build.

Configuration Cache lưu trạng thái cấu hình của build, bao gồm đồ thị tác vụ đã được cấu hình, để Gradle có thể bỏ qua phần lớn giai đoạn configuration ở lần chạy sau. Build Cache lưu đầu ra của các task có thể cache, để Gradle có thể tái sử dụng kết quả thay vì thực hiện lại task. Ngoài hai cơ chế này, Gradle còn có up-to-date checking để xác định đầu ra hiện có trong workspace có còn hợp lệ hay không.

Phân biệt ba cơ chế này giúp đọc log chính xác, cấu hình build đúng và tránh kỳ vọng sai, chẳng hạn nghĩ rằng bật Configuration Cache sẽ tự động tránh biên dịch lại, hoặc nghĩ rằng Build Cache sẽ giúp Gradle bỏ qua toàn bộ giai đoạn cấu hình.

## 1. Ba cơ chế thường gặp khi chạy build lặp lại

Một lần build Gradle có thể trải qua các giai đoạn:

    Khởi tạo build
          |
          v
    Cấu hình project và task
          |
          v
    Tạo task graph
          |
          v
    Thực thi task
          |
          v
    Tạo hoặc cập nhật đầu ra

Ba cơ chế tối ưu tác động vào những phần khác nhau:

| Cơ chế | Dữ liệu được tái sử dụng | Công việc có thể tránh |
| --- | --- | --- |
| Configuration Cache | Trạng thái cấu hình và task graph đã được lưu | Đánh giá lại build scripts và cấu hình task khi đầu vào cấu hình không đổi |
| Up-to-date checking | Đầu ra đã có trong workspace cùng trạng thái đầu vào/đầu ra đã ghi nhận | Thực thi task khi đầu vào không đổi và đầu ra hiện tại còn hợp lệ |
| Build Cache | Đầu ra của task cacheable từ một lần build trước | Thực thi task khi có cache entry phù hợp; Gradle khôi phục đầu ra từ cache |

Configuration Cache giúp giảm thời gian chuẩn bị build. Up-to-date checking và Build Cache giúp giảm công việc trong giai đoạn thực thi task. Một lần build có thể dùng cả ba cơ chế trong cùng một lần chạy.

## 2. Configuration Cache lưu gì?

Configuration Cache lưu kết quả của giai đoạn cấu hình build để Gradle có thể dùng lại trong lần chạy tiếp theo. Trạng thái này bao gồm thông tin cần thiết để tiếp tục với task graph đã được cấu hình, cùng dữ liệu cấu hình mà Gradle cần khôi phục.

Khi chạy lần đầu với Configuration Cache:

1. Gradle khởi tạo build và đọc settings.
2. Gradle đánh giá build scripts và cấu hình project/task.
3. Gradle tạo task graph cho các task được yêu cầu.
4. Gradle lưu trạng thái cấu hình nếu build tương thích và không có vấn đề ngăn cản việc lưu.
5. Gradle thực thi task như bình thường.

Khi chạy lại cùng yêu cầu và các đầu vào cấu hình vẫn phù hợp, Gradle có thể nạp trạng thái đã lưu thay vì thực hiện lại toàn bộ giai đoạn configuration.

Configuration Cache không lưu nội dung JAR được biên dịch, báo cáo kiểm thử hoặc thư mục build/classes như một bản sao đầu ra task. Những dữ liệu đó thuộc phạm vi up-to-date checking hoặc Build Cache.

### Cấu hình được lưu có liên quan tới yêu cầu task

Configuration Cache gắn với yêu cầu build và trạng thái cấu hình cần thiết để thực hiện yêu cầu đó. Ví dụ, cấu hình cho:

    ./gradlew :app:build

có thể khác cấu hình cho:

    ./gradlew :app:test

Vì task selector và cấu hình liên quan có thể khác, không nên giả định một entry duy nhất luôn phục vụ mọi lệnh build. Gradle quản lý các entry phù hợp với những yêu cầu và đầu vào cấu hình.

## 3. Bật và sử dụng Configuration Cache

Có thể bật Configuration Cache cho một lần chạy:

    ./gradlew build --configuration-cache

Trên Windows:

    gradlew.bat build --configuration-cache

Lần đầu, Gradle thực hiện cấu hình rồi lưu cache. Lần chạy sau:

    ./gradlew build --configuration-cache

nếu các đầu vào cấu hình không thay đổi và build tương thích, log có thể hiển thị thông báo tương tự:

    Reusing configuration cache.

Có thể bật lâu dài trong gradle.properties:

    org.gradle.configuration-cache=true

Khi cần tắt cho một lần chạy:

    ./gradlew build --no-configuration-cache

Tên tùy chọn là --configuration-cache và --no-configuration-cache. Việc bật cache không có nghĩa Gradle sẽ luôn tái sử dụng entry; nó còn phụ thuộc vào tính hợp lệ của trạng thái đã lưu và các đầu vào cấu hình hiện tại.

## 4. Khi nào Configuration Cache được tái sử dụng?

Gradle cần xác định những đầu vào ảnh hưởng đến giai đoạn cấu hình. Nếu một đầu vào liên quan thay đổi, trạng thái đã lưu có thể không còn phù hợp và Gradle cần cấu hình lại.

Những thay đổi có thể làm Configuration Cache phải được tạo lại gồm:

- Build scripts như build.gradle hoặc build.gradle.kts thay đổi.
- settings.gradle hoặc settings.gradle.kts thay đổi.
- Build logic, convention plugin hoặc plugin được dùng trong cấu hình thay đổi.
- Gradle version hoặc một số thành phần môi trường cấu hình thay đổi.
- Giá trị property, system property hoặc biến môi trường được đọc trong giai đoạn cấu hình thay đổi.
- Nội dung file được build script đọc để quyết định cấu hình thay đổi.
- Task selector hoặc yêu cầu build cần một trạng thái cấu hình khác.
- Các đối tượng hoặc hành động cấu hình không thể được lưu/khôi phục theo yêu cầu của Configuration Cache.

Ví dụ:

    val useCloud = providers.gradleProperty("useCloud").orNull == "true"

    if (useCloud) {
        // Cấu hình dependency hoặc task dành cho môi trường cloud
    }

Nếu giá trị useCloud thay đổi, cấu hình có thể thay đổi theo. Gradle cần một entry tương ứng với giá trị mới.

Ngược lại, thay đổi một tệp Java thông thường thường không bắt buộc phải cấu hình lại toàn bộ build nếu tệp đó chỉ là đầu vào của task biên dịch và không được build script đọc trong giai đoạn configuration. Task biên dịch vẫn có thể phải chạy lại hoặc được kiểm tra up-to-date riêng.

## 5. Những điều kiện khiến build chưa tương thích Configuration Cache

Để lưu và khôi phục trạng thái cấu hình, Gradle cần build logic tuân thủ các quy tắc về configuration cache. Một số cách viết build script hoặc custom task cũ có thể truy cập trạng thái project ở thời điểm thực thi, giữ tham chiếu không thể tuần tự hóa hoặc đọc dữ liệu bên ngoài mà không khai báo đúng.

Ví dụ, custom task không nên giữ đối tượng Project để sử dụng tùy ý trong action. Thay vào đó, hãy truyền dữ liệu cần thiết qua task properties và Provider API.

Ví dụ minh họa một kiểu viết nên tránh:

    tasks.register("printVersion") {
        doLast {
            println(project.version)
        }
    }

Task action truy cập trực tiếp Project trong giai đoạn thực thi có thể không tương thích với Configuration Cache. Có thể lấy giá trị trong giai đoạn cấu hình và truyền vào property của task:

    abstract class PrintVersion : DefaultTask() {
        @get:Input
        abstract val versionText: Property<String>

        @TaskAction
        fun printVersion() {
            println(versionText.get())
        }
    }

    tasks.register<PrintVersion>("printVersion") {
        versionText.set(project.version.toString())
    }

Ví dụ cho thấy dữ liệu cần dùng được chuyển thành property rõ ràng. Trong dự án thực tế, task type thường được đặt trong build logic hoặc convention plugin thay vì định nghĩa trực tiếp trong build script.

Khi chạy với --configuration-cache, Gradle có thể báo các vấn đề tương thích. Hãy đọc báo cáo được tạo và sửa từng vấn đề theo API được khuyến nghị. Một số phiên bản Gradle có tùy chọn cấu hình mức xử lý vấn đề như warning hoặc fail; cần dùng tài liệu tương ứng với Gradle Wrapper của dự án.

Không nên bỏ qua cảnh báo bằng cách ép build tiếp tục nếu mục tiêu là bảo đảm cache được lưu và tái sử dụng ổn định. Cần xác nhận lần chạy sau thực sự hiển thị cache được tái sử dụng.

## 6. Build Cache lưu gì?

Build Cache lưu đầu ra của task có thể cache. Khi một task cacheable đã chạy với một tập đầu vào cụ thể, Gradle có thể lưu đầu ra tương ứng. Nếu một lần build khác có cùng khóa đầu vào và task có thể cache, Gradle có thể khôi phục đầu ra đó thay vì chạy lại action.

Ví dụ task biên dịch Java:

    src/main/java/com/example/Main.java
                |
                v
            compileJava
                |
                v
    build/classes/java/main/com/example/Main.class

Task compileJava có đầu vào như mã nguồn, classpath và tùy chọn compiler. Khi đầu vào được khai báo và tạo khóa giống một lần build trước, Gradle có thể lấy các tệp .class từ Build Cache.

Build Cache có thể gồm:

- **Local build cache:** cache trên máy hiện tại.
- **Remote build cache:** cache dùng chung qua máy chủ hoặc dịch vụ được cấu hình.

Nhờ remote cache, một máy CI hoặc máy phát triển có thể tái sử dụng đầu ra được tạo bởi một máy khác, miễn là task cacheable và khóa đầu vào phù hợp.

Build Cache không lưu toàn bộ task graph đã cấu hình. Nó lưu kết quả đầu ra của task.

## 7. Bật và sử dụng Build Cache

Có thể bật Build Cache cho một lần chạy:

    ./gradlew build --build-cache

Trên Windows:

    gradlew.bat build --build-cache

Hoặc bật trong gradle.properties:

    org.gradle.caching=true

Tắt cho một lần chạy:

    ./gradlew build --no-build-cache

Khi Build Cache được bật, task cacheable có thể lấy kết quả từ cache. Log thường hiển thị trạng thái:

    FROM-CACHE

Điều này cho biết Gradle đã khôi phục đầu ra từ cache thay vì thực thi task trên workspace hiện tại.

Build Cache không buộc mọi task phải cacheable. Một task cần được thiết kế và khai báo đúng để có thể lưu đầu ra an toàn. Một số task có tác dụng phụ, phụ thuộc trạng thái ngoài hoặc tạo kết quả không ổn định không nên được cache.

## 8. Điều kiện để đầu ra task được tái sử dụng từ Build Cache

Gradle xác định cache key từ thông tin liên quan tới task và các đầu vào đã khai báo. Những yếu tố có thể tham gia gồm:

- Kiểu task và implementation của task.
- Action và classpath của task implementation.
- Giá trị các input properties.
- Nội dung các input files hoặc file collections.
- Classpath và các thuộc tính compiler liên quan.
- Output/cache configuration và các thuộc tính ảnh hưởng kết quả.

Khi cache key khớp với một entry có sẵn và task có thể cache, Gradle có thể khôi phục đầu ra.

Điều này phụ thuộc vào việc khai báo đầu vào đầy đủ. Nếu task đọc một biến môi trường, file cấu hình hoặc dữ liệu ngoài nhưng không khai báo nó là input, Gradle có thể tính cache key không phản ánh toàn bộ công việc thực tế. Khi đó, đầu ra được tái sử dụng có thể sai.

Ngược lại, nếu khai báo đầu vào không ổn định hoặc chứa dữ liệu thay đổi không cần thiết, cache key có thể thay đổi liên tục và làm giảm tỷ lệ cache hit.

## 9. @CacheableTask và task custom

Với custom task, Gradle không thể tự đoán mọi đầu vào và đầu ra mà action sử dụng. Task cần khai báo properties phù hợp.

Ví dụ task tạo tệp thông tin từ một tệp đầu vào:

    @CacheableTask
    abstract class GenerateInfo : DefaultTask() {
        @get:InputFile
        @get:PathSensitive(PathSensitivity.RELATIVE)
        abstract val sourceFile: RegularFileProperty

        @get:OutputFile
        abstract val outputFile: RegularFileProperty

        @TaskAction
        fun generate() {
            val input = sourceFile.get().asFile
            val output = outputFile.get().asFile
            output.parentFile.mkdirs()
            output.writeText(input.readText().trim())
        }
    }

    tasks.register<GenerateInfo>("generateInfo") {
        sourceFile.set(layout.projectDirectory.file("version.txt"))
        outputFile.set(layout.buildDirectory.file("generated/info.txt"))
    }

Trong ví dụ:

- @CacheableTask cho biết task được thiết kế để hỗ trợ output caching.
- @InputFile khai báo tệp đầu vào.
- @OutputFile khai báo tệp đầu ra.
- PathSensitivity xác định cách đường dẫn tệp tham gia nhận diện input.

Nếu version.txt thay đổi, cache key thay đổi và đầu ra cũ không còn phù hợp. Nếu đầu vào không đổi, Gradle có thể tái sử dụng đầu ra từ cache.

Task thực tế cần khai báo mọi input property có ảnh hưởng kết quả. Nếu task còn đọc một cờ chế độ, locale hoặc một file cấu hình khác, những giá trị đó cũng phải được khai báo. Không khai báo đủ input có thể tạo cache hit sai.

## 10. Up-to-date checking khác Build Cache như thế nào?

Up-to-date checking là cơ chế kiểm tra đầu ra task đã có trong workspace hiện tại. Gradle so sánh trạng thái đầu vào và đầu ra với lần thực thi trước.

Nếu đầu vào không thay đổi và đầu ra vẫn tồn tại, task có thể được đánh dấu:

    UP-TO-DATE

Task không cần chạy lại vì đầu ra trong workspace đã hợp lệ.

Build Cache hoạt động khác: nếu đầu ra không có sẵn trong workspace nhưng có entry phù hợp trong cache, Gradle có thể khôi phục đầu ra và đánh dấu:

    FROM-CACHE

Bảng so sánh:

| Tình huống | Up-to-date checking | Build Cache |
| --- | --- | --- |
| Đầu ra hiện có trong workspace và còn hợp lệ | Bỏ qua task, dùng đầu ra hiện tại | Không cần lấy cache |
| Đầu ra bị xóa nhưng cache có entry phù hợp | Không thể dùng đầu ra thiếu | Khôi phục đầu ra từ cache |
| Đầu vào thay đổi và cache có kết quả cho đầu vào mới | Đầu ra hiện tại không up-to-date | Có thể khôi phục entry tương ứng nếu đã được tạo trước |
| Đầu vào thay đổi và chưa có cache entry | Chạy task | Chạy task rồi có thể lưu đầu ra |

Up-to-date checking thường hoạt động dựa trên trạng thái local của task. Build Cache có thể chia sẻ kết quả giữa các workspace. Hai cơ chế bổ sung cho nhau.

## 11. Ba trạng thái thường thấy trong log

Khi đọc output Gradle, cần phân biệt:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **UP-TO-DATE** | Đầu ra đã có trong workspace và đầu vào không thay đổi theo cơ chế kiểm tra. |
| **FROM-CACHE** | Đầu ra được khôi phục từ Build Cache. |
| **EXECUTED** hoặc task không có trạng thái reuse | Task đã thực hiện action trong lần build hiện tại. |

Configuration Cache không phải trạng thái của task theo cùng cách. Nó thường được thể hiện bằng thông báo ở phần cấu hình, ví dụ:

    Reusing configuration cache.

Một lần build có thể hiển thị cả:

    Reusing configuration cache.
    :compileJava UP-TO-DATE
    :test FROM-CACHE
    :jar

Điều này có nghĩa Gradle đã tái sử dụng trạng thái cấu hình; compileJava dùng đầu ra local còn hợp lệ; test khôi phục kết quả từ Build Cache; jar vẫn thực thi vì cần cập nhật đầu ra hoặc không có cache entry phù hợp.

## 12. Configuration Cache và Build Cache có thể dùng độc lập

Hai cache giải quyết hai vấn đề khác nhau. Có thể bật một cache mà không bật cache còn lại.

| Configuration Cache | Build Cache | Hành vi |
| --- | --- | --- |
| Tắt | Tắt | Gradle cấu hình build mỗi lần; task dùng up-to-date checking nhưng không lấy output từ Build Cache. |
| Bật | Tắt | Có thể bỏ qua configuration khi entry hợp lệ; task vẫn thực thi hoặc up-to-date theo workspace. |
| Tắt | Bật | Gradle vẫn cấu hình build; task cacheable có thể lấy output từ Build Cache. |
| Bật | Bật | Có thể tái sử dụng cả trạng thái cấu hình và đầu ra task. |

Ví dụ bật cả hai:

    ./gradlew build --configuration-cache --build-cache

Hoặc trong gradle.properties:

    org.gradle.configuration-cache=true
    org.gradle.caching=true

Không nên suy luận rằng một cache đã bật thì cache kia cũng tự bật. Cần kiểm tra tùy chọn và log riêng.

## 13. Ví dụ một lần build đầu và lần build sau

Giả sử project có task compileJava, processResources, test và jar.

### Lần đầu

Chạy:

    ./gradlew build --configuration-cache --build-cache

Gradle chưa có Configuration Cache entry và chưa có output cache cho task:

    Configuration phase: executed
    compileJava: executed
    processResources: executed
    test: executed
    jar: executed

Sau lần chạy, Gradle có thể lưu configuration state và output của những task cacheable.

### Lần thứ hai, không có thay đổi

Chạy lại:

    ./gradlew build --configuration-cache --build-cache

Có thể nhận:

    Configuration Cache: reused
    compileJava: UP-TO-DATE
    processResources: UP-TO-DATE
    test: UP-TO-DATE
    jar: UP-TO-DATE

Gradle tái sử dụng cấu hình và dùng đầu ra local còn hợp lệ. Build Cache không cần thiết nếu mọi output đã có trong workspace.

### Sau khi xóa thư mục build

Chạy:

    ./gradlew clean
    ./gradlew build --configuration-cache --build-cache

Task output đã bị xóa. Nếu Build Cache có entry phù hợp, Gradle có thể khôi phục output:

    Configuration Cache: reused
    compileJava: FROM-CACHE
    processResources: FROM-CACHE
    test: FROM-CACHE
    jar: FROM-CACHE

Configuration Cache vẫn có thể được tái sử dụng vì việc clean output không nhất thiết làm thay đổi đầu vào cấu hình. Build Cache cung cấp lại đầu ra task.

Đây là ví dụ minh họa; trạng thái thực tế phụ thuộc task có cacheable hay không, output có được khai báo đúng, cache entry có tồn tại và cấu hình clean của dự án.

## 14. Remote Build Cache

Local Build Cache chỉ có lợi khi máy hiện tại đã tạo ra kết quả tương ứng trước đó. Remote Build Cache cho phép nhiều máy dùng chung output cache.

Một build có thể:

1. Chạy trên máy CI A và tạo output của task compileJava.
2. Lưu output vào remote cache.
3. Chạy trên máy CI B với cùng input và task implementation.
4. Khôi phục output từ remote cache mà không phải biên dịch lại.

Gradle có thể cấu hình remote cache trong settings.gradle:

    buildCache {
        remote(HttpBuildCache) {
            url = "https://cache.example.com/"
            enabled = true
            push = false
        }
    }

Ví dụ này minh họa remote HTTP cache chỉ đọc. Một máy build đáng tin cậy có thể được cấu hình push:

    buildCache {
        remote(HttpBuildCache) {
            url = "https://cache.example.com/"
            enabled = true
            push = true
        }
    }

Trong thực tế, cần cấu hình xác thực và quyền truy cập phù hợp. Chỉ những máy hoặc pipeline đáng tin cậy mới nên có quyền ghi cache dùng chung, vì đầu ra cache có thể được các build khác tái sử dụng.

Remote Build Cache không phải Configuration Cache từ xa. Nó lưu đầu ra task. Configuration Cache có cơ chế lưu trạng thái cấu hình riêng trong workspace Gradle.

## 15. Clean ảnh hưởng đến các cache ra sao?

Lệnh:

    ./gradlew clean

thường xóa thư mục build của project, tức các đầu ra task nằm trong build directory. Nó không đồng nghĩa với việc xóa toàn bộ Configuration Cache hoặc Build Cache.

Sau clean:

- Đầu ra local của task có thể bị xóa.
- Up-to-date checking không thể dùng đầu ra đã mất.
- Build Cache vẫn có thể chứa output phù hợp và khôi phục chúng.
- Configuration Cache có thể vẫn còn hợp lệ nếu đầu vào cấu hình không đổi.

Vì vậy, clean build không nhất thiết là build hoàn toàn không dùng cache. Nó thường có nghĩa đầu ra build trong workspace được tạo lại hoặc khôi phục từ Build Cache.

Muốn kiểm tra một lần build không dùng Build Cache:

    ./gradlew clean build --no-build-cache

Muốn kiểm tra không dùng Configuration Cache:

    ./gradlew clean build --no-configuration-cache

Nếu cần kiểm tra thật sự trên môi trường sạch, hãy cân nhắc workspace mới và Gradle User Home riêng, vì cache có thể nằm ngoài thư mục project. Không xóa cache toàn cục tùy tiện trên máy dùng chung.

## 16. Vì sao Configuration Cache có thể bị vô hiệu hóa?

Một số thay đổi không nhất thiết làm task output mất hiệu lực nhưng lại làm trạng thái cấu hình không còn hợp lệ.

Ví dụ:

- Thay đổi build.gradle hoặc settings.gradle.
- Thay đổi version plugin.
- Thay đổi một file được đọc trong giai đoạn cấu hình.
- Thay đổi Gradle property dùng để chọn module hoặc cấu hình task.
- Thay đổi biến môi trường được build script đọc trực tiếp.
- Thay đổi task selector hoặc cấu hình liên quan.

Khi đó, Gradle có thể cấu hình lại build và tạo Configuration Cache entry mới. Task vẫn có thể được đánh dấu UP-TO-DATE hoặc FROM-CACHE nếu đầu vào task và cache key không đổi.

Đây là một khác biệt quan trọng: cache cấu hình bị miss không có nghĩa tất cả task output cache cũng bị miss.

## 17. Vì sao Build Cache có thể bị miss?

Một task có thể không tìm thấy cache entry vì:

- Input file thay đổi.
- Input property thay đổi.
- Compiler option hoặc classpath thay đổi.
- Task implementation hoặc plugin implementation thay đổi.
- Cache key khác do đường dẫn hoặc thuộc tính input được khai báo.
- Task không được đánh dấu cacheable.
- Task đọc dữ liệu không được khai báo hoặc không xác định output.
- Cache entry không có trong local hoặc remote cache.
- Remote cache không truy cập được hoặc bị từ chối quyền.

Nếu task được thực thi thay vì FROM-CACHE, không có nghĩa Build Cache bị lỗi. Có thể đầu vào thực sự đã thay đổi hoặc task chưa từng tạo cache entry tương ứng.

Hãy dùng log và build scan nếu tổ chức có cấu hình để xem lý do task không được cache. Không nên thêm @CacheableTask cho một task chỉ để tăng cache hit khi chưa bảo đảm tính xác định và khai báo đầu vào/đầu ra đúng.

## 18. Task không cacheable và tác dụng phụ

Một số task không phù hợp với output caching:

- Task gửi email hoặc gọi API bên ngoài.
- Task triển khai ứng dụng lên môi trường.
- Task ghi dữ liệu vào hệ thống ngoài.
- Task phụ thuộc vào thời gian hiện tại hoặc dữ liệu mạng không được khai báo.
- Task tạo output không xác định theo đầu vào.
- Task có tác dụng phụ cần thực hiện mỗi lần, không chỉ tạo file đầu ra.

Nếu cache một task có tác dụng phụ, Gradle có thể bỏ qua action khi có cache hit. Điều đó có thể khiến thao tác bên ngoài không xảy ra dù build vẫn thành công.

Task cacheable nên là phép biến đổi có thể tái lập từ input đã khai báo sang output đã khai báo. Những tác vụ deploy hoặc publish thường không nên được coi như tác vụ tạo artifact thuần túy có thể tái sử dụng.

## 19. Configuration Cache và configuration avoidance

Gradle có API configuration avoidance như:

    tasks.register("generateReport") {
        // Cấu hình task khi cần
    }

    tasks.named("test") {
        // Cấu hình task đã được đăng ký
    }

Configuration avoidance trì hoãn việc tạo/cấu hình task không cần thiết. Configuration Cache lưu trạng thái cấu hình đã thực hiện để tái sử dụng ở lần chạy sau.

Hai cơ chế bổ sung nhưng không giống nhau:

- Configuration avoidance giảm lượng công việc cấu hình ngay trong một lần build.
- Configuration Cache giảm việc lặp lại giai đoạn cấu hình giữa nhiều lần build.

Một build nên dùng API register/named và Provider API đúng cách, ngay cả khi chưa bật Configuration Cache. Điều đó giúp build hiệu quả hơn và dễ tương thích với các cơ chế mới.

## 20. Chẩn đoán cache cấu hình không được tái sử dụng

Nếu mỗi lần build đều thấy Gradle cấu hình lại, hãy kiểm tra:

1. Lệnh có bật --configuration-cache hoặc org.gradle.configuration-cache=true không?
2. Lần trước có lưu cache thành công không?
3. Log có thông báo Configuration Cache entry được lưu hay có vấn đề ngăn lưu?
4. Build scripts, settings, plugin hoặc build logic có thay đổi không?
5. Property, biến môi trường hoặc file cấu hình nào được đọc trong giai đoạn configuration?
6. Có task hoặc plugin truy cập API không tương thích không?
7. Lệnh hiện tại có cùng task selector và yêu cầu cấu hình không?
8. Gradle có đang dùng workspace hoặc Gradle User Home khác không?

Chạy với:

    ./gradlew build --configuration-cache --configuration-cache-problems=warn

Tùy chọn problems=warn có thể hữu ích trong giai đoạn chuyển đổi ở các phiên bản Gradle hỗ trợ. Hãy kiểm tra tài liệu đúng phiên bản wrapper và không coi warning mode là bằng chứng build đã hoàn toàn tương thích.

Đọc báo cáo Configuration Cache mà Gradle cung cấp để tìm vị trí build script, plugin hoặc task gây vấn đề. Sau khi sửa, chạy lại và xác nhận lần tiếp theo có thông báo tái sử dụng.

## 21. Chẩn đoán Build Cache không có hit

Nếu task luôn thực thi mà không hiển thị FROM-CACHE, hãy kiểm tra:

1. Build Cache đã bật chưa?
2. Task có cacheable không?
3. Task đã khai báo đầy đủ input và output chưa?
4. Các input có thật sự giống lần build trước không?
5. Task implementation hoặc compiler/plugin version có thay đổi không?
6. Local/remote cache có entry tương ứng không?
7. Remote cache có được truy cập và có quyền đọc không?
8. Task có tạo output không xác định hoặc đọc dữ liệu ngầm không?

Lệnh:

    ./gradlew build --build-cache --info

có thể cung cấp thêm thông tin về cache key và lý do task thực thi tùy phiên bản Gradle. Nếu task có output bị xóa nhưng không được cache, task phải chạy lại để tạo output.

Đối với custom task, hãy kiểm tra annotation và property input/output. Một task thiếu khai báo input có thể cho cache hit sai; một task thiếu output declaration có thể không hỗ trợ output caching như mong muốn.

## 22. Cách thử riêng từng cơ chế

Để hiểu build đang được tăng tốc ở giai đoạn nào, có thể thử các cấu hình riêng biệt trên một project mẫu hoặc workspace thử nghiệm.

### Chỉ bật Configuration Cache

    ./gradlew clean build --configuration-cache --no-build-cache
    ./gradlew build --configuration-cache --no-build-cache

Lần đầu Gradle cấu hình và thực thi task. Lần sau có thể tái sử dụng cấu hình, còn task dựa vào up-to-date checking tại workspace.

### Chỉ bật Build Cache

    ./gradlew clean build --no-configuration-cache --build-cache
    ./gradlew clean build --no-configuration-cache --build-cache

Configuration vẫn được thực hiện lại. Do clean xóa output, task cacheable có thể khôi phục đầu ra từ Build Cache.

### Bật cả hai

    ./gradlew clean build --configuration-cache --build-cache
    ./gradlew build --configuration-cache --build-cache

Lần sau có thể tái sử dụng configuration state và các đầu ra task phù hợp.

Khi thử nghiệm, hãy ghi lại thời gian, trạng thái task và log. Không so sánh thời gian của một lần build với cache nóng với một lần build cache lạnh mà không ghi rõ điều kiện.

## 23. Các hiểu lầm thường gặp

### Nghĩ Configuration Cache lưu JAR hoặc class file

Không đúng. Nó lưu trạng thái cấu hình và task graph. Đầu ra task thuộc up-to-date checking hoặc Build Cache.

### Nghĩ Build Cache bỏ qua giai đoạn configuration

Không đúng. Gradle vẫn cần khởi tạo và cấu hình build để xác định task và đầu vào. Configuration Cache mới là cơ chế giảm công việc ở giai đoạn đó.

### Nghĩ clean xóa mọi loại cache

Không đúng. clean thường xóa output trong build directory. Configuration Cache và Build Cache có thể nằm ở Gradle User Home và tiếp tục tồn tại.

### Nghĩ UP-TO-DATE và FROM-CACHE giống nhau

Không đúng. UP-TO-DATE dùng output hiện có trong workspace; FROM-CACHE khôi phục output từ cache.

### Nghĩ task nào cũng cache được

Không đúng. Task cần có tính chất phù hợp và khai báo đúng input/output. Task có tác dụng phụ hoặc đầu vào không xác định có thể không an toàn khi cache.

### Nghĩ cache hit chứng minh output đúng

Cache hit chỉ cho biết Gradle tìm thấy entry theo cache key và khôi phục nó. Tính đúng đắn phụ thuộc vào việc khai báo input, task implementation, độ tin cậy của cache và quy trình xác minh.

### Nghĩ hai máy có cùng source là có cùng build

Không nhất thiết. Plugin, toolchain, dependency graph, property, repository, task configuration và môi trường có thể khác. Cần kiểm soát các đầu vào này để build có thể tái lập.

## 24. Bảng so sánh tổng hợp

| Tiêu chí | Configuration Cache | Build Cache | Up-to-date checking |
| --- | --- | --- | --- |
| Mục tiêu | Tăng tốc cấu hình | Tái sử dụng đầu ra task | Tránh chạy lại task khi output local còn hợp lệ |
| Dữ liệu lưu | Trạng thái cấu hình/task graph | Output của task cacheable | Lịch sử/trạng thái input-output local |
| Phạm vi | Yêu cầu build đã cấu hình | Task và cache key | Task trong workspace hiện tại |
| Có thể chia sẻ qua máy? | Không phải cơ chế chia sẻ output task | Có, qua remote build cache | Không theo cơ chế chia sẻ output |
| Thay đổi build script | Có thể làm entry không còn hợp lệ | Chỉ ảnh hưởng nếu thay task implementation/input tương ứng | Không trực tiếp quyết định nếu input/output task không đổi |
| Xóa thư mục build | Thường không xóa entry cấu hình | Cache entry có thể vẫn còn | Output local bị mất nên task không còn up-to-date |
| Dấu hiệu trong log | Reusing configuration cache | FROM-CACHE | UP-TO-DATE |

## 25. Nguyên tắc sử dụng trong dự án thực tế

- Bật Configuration Cache để giảm thời gian cấu hình khi build tương thích.
- Dùng configuration avoidance và Provider API để viết build logic hiện đại.
- Sửa các vấn đề tương thích thay vì che giấu cảnh báo.
- Bật Build Cache cho task có thể tái lập và khai báo input/output đầy đủ.
- Dùng remote Build Cache cho CI hoặc nhóm nhiều người khi có hạ tầng phù hợp.
- Không cache task có tác dụng phụ cần thực hiện mỗi lần.
- Phân biệt output local còn hợp lệ với output được khôi phục từ cache.
- Không dùng clean như cách hiểu rằng mọi cache đã bị xóa.
- Ghi log và đo thời gian riêng cho configuration và task execution.
- Kiểm tra kết quả task, test report và artifact sau khi bật cache.

## 26. Kết luận

Configuration Cache và Build Cache giải quyết hai phần khác nhau của build Gradle. Configuration Cache lưu trạng thái cấu hình để giảm việc đánh giá lại build scripts và tạo task graph. Build Cache lưu đầu ra của task cacheable để tái sử dụng khi input và task implementation tạo ra cùng cache key. Up-to-date checking là cơ chế thứ ba, dùng đầu ra đã có trong workspace khi trạng thái đầu vào và đầu ra vẫn hợp lệ.

Một build có thể tái sử dụng Configuration Cache, bỏ qua compileJava vì UP-TO-DATE, và khôi phục test output từ Build Cache trong cùng một lần chạy. Hiểu đúng nguồn của từng trạng thái giúp xác định build đang tiết kiệm thời gian ở đâu, điều tra cache miss và thiết kế task an toàn. Hiệu quả chỉ đáng tin cậy khi build logic tương thích, đầu vào/đầu ra được khai báo đầy đủ và task tạo kết quả ổn định.
