# Bộ nhớ đệm phụ thuộc và bộ nhớ đệm đầu ra build

Gradle có nhiều cơ chế lưu lại dữ liệu để giảm công việc lặp lại giữa các lần build. Khi build một project Java, Gradle có thể tái sử dụng thư viện đã tải từ repository, nhận biết task không cần chạy lại, khôi phục output của task từ build cache hoặc tái sử dụng kết quả cấu hình build.

Các cơ chế này thường bị gọi chung là “cache”, nhưng chúng lưu những loại dữ liệu khác nhau và giải quyết những vấn đề khác nhau. Muốn build nhanh mà vẫn đáng tin cậy, cần phân biệt:

- **Dependency cache**: lưu metadata và artifact dependency đã resolve/tải về.
- **Up-to-date checking**: kiểm tra output hiện có của task có còn phù hợp với input hiện tại không.
- **Build cache**: lưu và khôi phục output của task dựa trên input và implementation của task.
- **Incremental task execution**: cho task biết phần input nào thay đổi để chỉ xử lý phần cần thiết.
- **Configuration cache**: lưu kết quả cấu hình build để giảm thời gian cấu hình ở lần chạy sau.

Mỗi cơ chế có phạm vi và điều kiện tái sử dụng riêng. Một dependency có trong cache không có nghĩa task đã có output; task ở trạng thái up-to-date không có nghĩa output được lấy từ build cache; configuration cache cũng không thay thế build cache.

## 1. Nhìn tổng thể các lớp cache

Một build có thể đi qua nhiều lớp:

~~~text
Build invocation
      |
      v
Configuration phase
      |
      +--> Configuration cache
      |      Reuse configured build model
      |
      v
Task graph
      |
      v
Dependency resolution
      |
      +--> Dependency cache
      |      Reuse metadata and downloaded artifacts
      |
      v
Task execution
      |
      +--> Up-to-date checking
      |      Existing task outputs still valid?
      |
      +--> Build cache
      |      Restore outputs from a previous execution?
      |
      +--> Incremental execution
             Process only changed input items
~~~

| Cơ chế | Lưu hoặc theo dõi gì? | Giúp giảm công việc nào? |
|---|---|---|
| Dependency cache | Metadata module, artifact đã tải và dữ liệu resolution liên quan | Không phải tải lại dependency từ repository khi còn hợp lệ |
| Up-to-date checking | Snapshot input/output của task và trạng thái output hiện có | Không chạy lại task nếu output trong workspace vẫn hợp lệ |
| Build cache | Output của task gắn với cache key | Khôi phục output đã tạo ở build trước hoặc trên máy khác |
| Incremental execution | Thông tin thay đổi của input được khai báo incremental | Chỉ xử lý phần input thay đổi |
| Configuration cache | Kết quả cấu hình build/task graph theo điều kiện tương thích | Giảm thời gian configuration phase |

Một build có thể sử dụng nhiều cơ chế cùng lúc. Ví dụ, Gradle dùng dependency cache để lấy JAR, dùng configuration cache để tái sử dụng build model, sau đó nhận biết task compile đã up-to-date hoặc khôi phục output từ build cache.

## 2. Dependency cache: lưu metadata và artifact đã resolve

Dependency cache là vùng lưu trữ Gradle dùng để tái sử dụng thông tin dependency giữa các lần build. Nó thường nằm trong Gradle User Home, dưới thư mục cache của Gradle.

Dependency cache có thể chứa:

- Metadata của module từ Maven/Ivy repository.
- Thông tin về version và kết quả resolve dependency.
- Artifact như JAR, ZIP hoặc file thư viện đã tải.
- Metadata liên quan đến repository và trạng thái kiểm tra dependency.
- Dữ liệu được tạo trong quá trình xử lý artifact.

Ví dụ khai báo:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.example:service-client:2.0'
}
~~~

Khi Gradle resolve dependency lần đầu, nó tìm metadata và tải artifact cần thiết từ repository. Ở những lần build sau, Gradle có thể dùng dữ liệu đã lưu trong dependency cache thay vì tải lại toàn bộ.

### Dependency cache không phải build output cache

Dependency cache lưu thư viện mà project tiêu thụ. Build cache lưu output mà task tạo ra.

Ví dụ:

- **service-client-2.0.jar** được tải từ Maven repository và nằm trong dependency cache.
- **compileJava** tạo class file trong **build/classes/java/main**.
- Build cache có thể lưu output của **compileJava** để một build tương thích khác khôi phục.

JAR trong dependency cache là input của task compile. Class file được biên dịch là output của task. Hai dữ liệu này có nguồn gốc và quy tắc tái sử dụng khác nhau.

### Dependency cache được chia sẻ qua các project

Các project dùng cùng Gradle User Home có thể tái sử dụng artifact đã tải nếu dependency, repository và metadata phù hợp. Điều này hữu ích khi nhiều project cùng dùng một thư viện.

Nếu project A và project B cùng cần **service-client:2.0**, Gradle thường không cần tải hai bản artifact riêng chỉ vì chúng thuộc hai project khác nhau. Tuy nhiên, việc resolve vẫn phải tuân theo repository, metadata, variant và các quy tắc dependency của từng configuration.

### Cache không có nghĩa dependency sẽ luôn được giữ nguyên mãi mãi

Gradle có chính sách cache cho metadata và module thay đổi. Với dynamic version hoặc changing module, kết quả có thể được kiểm tra lại sau một khoảng thời gian. Vì vậy, việc dependency đã có trong cache không đồng nghĩa Gradle sẽ luôn sử dụng cùng một metadata bất kể thời gian hoặc cấu hình.

## 3. Offline mode và refresh dependency

Dependency cache giúp giảm truy cập mạng, nhưng Gradle vẫn có thể cần liên hệ repository để kiểm tra metadata hoặc lấy artifact chưa có trong cache.

### Offline mode

Có thể yêu cầu Gradle chỉ dùng dữ liệu đã cache:

~~~shell
./gradlew build --offline
~~~

Trong offline mode, Gradle không cố tải dependency mới từ repository. Nếu dependency hoặc metadata cần thiết chưa có trong cache, build có thể thất bại với lỗi không resolve được dependency.

Offline mode hữu ích khi:

- Máy tạm thời không có kết nối mạng.
- Muốn xác nhận build có thể dùng dependency đã cache.
- Môi trường build bị giới hạn truy cập repository.
- Cần tránh truy cập mạng trong một lần chạy có chủ đích.

Offline mode không tạo dependency cache và không bảo đảm build thành công nếu cache chưa đầy đủ.

### Refresh dependencies

Khi cần yêu cầu Gradle kiểm tra lại trạng thái dependency từ repository:

~~~shell
./gradlew build --refresh-dependencies
~~~

Tùy trạng thái metadata và artifact, Gradle có thể kiểm tra lại repository và cập nhật thông tin cần thiết. Tùy chọn này không có nghĩa mọi JAR đều luôn bị tải lại từ đầu; Gradle có thể xác minh dữ liệu đã có và chỉ tải phần thực sự cần.

Dùng tùy chọn này khi nghi ngờ metadata/version cache đã cũ hoặc repository vừa cập nhật module thay đổi. Không nên thêm vào mọi build thường ngày vì nó làm tăng hoạt động kiểm tra repository và có thể làm build chậm hơn.

### Dynamic version và changing module

Dynamic version như **2.+**, **latest.release** hoặc module được đánh dấu changing có thể cần kiểm tra lại theo chính sách cache.

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.example:service-client:2.+'
}
~~~

Dynamic version cho phép Gradle chọn version phù hợp tại thời điểm resolve. Kết quả có thể thay đổi giữa các lần build nếu repository có version mới và chính sách cache cho phép kiểm tra lại.

Đối với build cần tái lập, nên ưu tiên version cụ thể, dependency locking và dependency verification khi phù hợp. Nếu dùng changing module, cần hiểu rõ thời gian cache và quy trình phát hành artifact.

### Không nhầm refresh với clean

**clean** xóa output do build của project tạo ra, thường là thư mục **build**. Nó không có nghĩa toàn bộ dependency cache trong Gradle User Home bị xóa.

**--refresh-dependencies** yêu cầu làm mới việc kiểm tra dependency resolution. Nó không thay thế **clean** và cũng không phải cách xóa build output.

## 4. Up-to-date checking: giữ output hiện có nếu input không đổi

Gradle có thể bỏ qua việc thực thi một task nếu output hiện tại vẫn hợp lệ so với input và cấu hình task.

Ví dụ, task **compileJava** có input là source file, compile classpath và một số tùy chọn compiler; output là class file. Nếu Gradle xác định input không đổi và output hiện tại vẫn tồn tại, task có thể được đánh dấu **UP-TO-DATE**.

~~~text
Lần build thứ nhất
source + dependencies + compiler options
               |
               v
          compileJava
               |
               v
        class files created

Lần build tiếp theo
same inputs + valid existing outputs
               |
               v
          UP-TO-DATE
        không chạy task action
~~~

Up-to-date checking thường dựa trên snapshot input/output và trạng thái của task trong workspace hiện tại. Gradle không cần lấy output từ cache ở trường hợp này vì output đã có sẵn và còn hợp lệ.

### Điều kiện để task có thể up-to-date

Gradle cần biết:

- Những input nào ảnh hưởng kết quả.
- Những output nào task sở hữu.
- Input/output hiện tại có thay đổi hay không.
- Output có còn tồn tại và hợp lệ không.
- Task có side effect hoặc trạng thái nào khiến việc bỏ qua không an toàn không.

Các task do plugin chuẩn của Gradle cung cấp thường đã khai báo input/output phù hợp. Với custom task, developer cần khai báo chính xác các property bằng annotation và managed property tương ứng.

### Output bị xóa thì sao?

Nếu output của task không còn tồn tại, Gradle không thể kết luận task up-to-date chỉ dựa vào input không đổi. Task cần thực thi lại hoặc khôi phục output từ build cache nếu task cacheable và có entry phù hợp.

Ví dụ:

~~~shell
./gradlew clean
./gradlew compileJava
~~~

**clean** xóa output trong thư mục build. Khi chạy **compileJava**, Gradle thường phải tạo lại class file. Nếu build cache được bật và có entry hợp lệ, output có thể được khôi phục thay vì biên dịch lại.

### UP-TO-DATE không phải FROM-CACHE

Hai task outcome này biểu thị hai tình huống khác nhau:

- **UP-TO-DATE**: output hiện có trong workspace vẫn hợp lệ, task không cần thực thi.
- **FROM-CACHE**: output được khôi phục từ build cache, thường vì task chưa có output hợp lệ trong workspace nhưng có cache entry phù hợp.

Cả hai đều có thể tránh chạy task action, nhưng nguồn output khác nhau.

## 5. Build cache: lưu và khôi phục output của task

Build cache cho phép Gradle tái sử dụng output của task từ những lần thực thi trước. Cache entry được gắn với key đại diện cho implementation và input của task.

Nếu một task được cấu hình cacheable, Gradle có thể:

1. Tính cache key từ các thuộc tính task có ảnh hưởng đến output.
2. Tìm entry tương ứng trong local hoặc remote build cache.
3. Nếu có entry phù hợp, khôi phục output.
4. Nếu không có, thực thi task.
5. Lưu output vào cache nếu task và cache được cấu hình cho phép.

~~~text
Task request
     |
     v
Calculate cache key
     |
     v
Look up build cache
     |
     +------ cache hit ------> Restore outputs
     |
     +------ cache miss -----> Execute task
                                  |
                                  v
                             Store outputs
~~~

### Build cache khác up-to-date checking

Up-to-date checking tái sử dụng output đang có trong workspace. Build cache tái sử dụng output được lưu trong cache, kể cả khi output không còn ở workspace hoặc build chạy trên máy khác.

| Tình huống | Kết quả có thể thấy |
|---|---|
| Output hiện có và input không đổi | **UP-TO-DATE** |
| Output thiếu, cache có entry phù hợp | **FROM-CACHE** |
| Output thiếu, cache không có entry phù hợp | Task thực thi |
| Input thay đổi, cache có entry cho input mới | Có thể **FROM-CACHE** |
| Input thay đổi, không có entry phù hợp | Task thực thi và có thể lưu entry mới |

### Build cache có thể dùng giữa nhiều lần build và nhiều máy

Local build cache nằm trên máy. Remote build cache cho phép các máy hoặc CI agent chia sẻ output qua một dịch vụ cache chung.

Ví dụ:

- Developer A build một commit và tạo output.
- CI build cùng source/input và có thể lấy output tương ứng từ remote cache.
- Developer B checkout cùng commit và có thể khôi phục output đã được cache.

Điều này chỉ hoạt động khi task cacheable, input/implementation tương đương và các điều kiện cache key phù hợp. Remote cache không tự làm mọi task trở nên cacheable.

## 6. Bật build cache

Build cache có thể được bật bằng command line:

~~~shell
./gradlew build --build-cache
~~~

Hoặc thông qua Gradle property:

~~~properties
org.gradle.caching=true
~~~

Thuộc tính này có thể được đặt trong **gradle.properties** theo chính sách của project hoặc môi trường. Khi bật, Gradle sử dụng local build cache và remote cache nếu đã được cấu hình.

Tắt cache cho một lần gọi:

~~~shell
./gradlew build --no-build-cache
~~~

Tùy chọn **--no-build-cache** hữu ích để so sánh hành vi hoặc chẩn đoán vấn đề cache. Nó không xóa các cache entry đã lưu.

### Local build cache

Local cache thường được Gradle quản lý trong Gradle User Home. Có thể cấu hình trong settings script:

~~~groovy
buildCache {
    local {
        enabled = true
        removeUnusedEntriesAfterDays = 30
    }
}
~~~

Có thể chọn thư mục khác nếu cần:

~~~groovy
buildCache {
    local {
        directory = new File(rootDir, '.gradle/build-cache')
    }
}
~~~

Vị trí cụ thể cần được chọn theo cách tổ chức repository và chính sách lưu trữ. Cache nằm trong repository có thể làm thư mục làm việc lớn lên nếu không được quản lý; cache trong Gradle User Home thường được chia sẻ giữa các build trên cùng máy.

### Remote build cache

Remote cache phù hợp khi nhiều developer hoặc CI agent cần chia sẻ output. Ví dụ cấu hình HTTP cache trong **settings.gradle**:

~~~groovy
buildCache {
    remote(HttpBuildCache) {
        url = uri('https://cache.example.internal/')
        push = false
    }
}
~~~

Ví dụ này chỉ minh họa endpoint nội bộ; địa chỉ thực tế và cơ chế xác thực phải do tổ chức cung cấp.

Có thể cho phép ghi cache ở môi trường được tin cậy:

~~~groovy
buildCache {
    remote(HttpBuildCache) {
        url = uri('https://cache.example.internal/')
        push = true
    }
}
~~~

Khi dùng cache có xác thực, credential cần được cấp từ secret store hoặc biến môi trường theo cơ chế phù hợp với môi trường. Không ghi username/password/token vào build script hoặc commit vào repository.

### Phân biệt quyền đọc và ghi

Một mô hình thường dùng:

- Developer và CI job thông thường được đọc cache.
- Một số CI job tin cậy được phép ghi cache.
- Job chạy code từ pull request không đáng tin cậy có thể bị hạn chế quyền push.
- Cache server có chính sách xác thực, phân vùng và retention rõ ràng.

Output được khôi phục từ remote cache sẽ tham gia build như output task. Vì vậy, remote cache là một ranh giới tin cậy. Chỉ cho phép nguồn đáng tin cậy ghi vào cache mà build quan trọng sẽ sử dụng.

## 7. Task nào có thể dùng build cache?

Không phải task nào cũng nên cache. Task phù hợp thường có output xác định từ input đã khai báo, không phụ thuộc trạng thái ẩn hoặc side effect ngoài contract.

Ví dụ thường phù hợp:

- Compile source code.
- Tạo archive từ input đã khai báo.
- Sinh mã nguồn từ schema và cấu hình.
- Tạo report hoặc metadata xác định.
- Xử lý resource theo quy tắc xác định.

Ví dụ thường không phù hợp nếu không có thiết kế đặc biệt:

- Task gửi email hoặc thông báo.
- Task publish artifact lên repository.
- Task triển khai lên server.
- Task ghi dữ liệu vào database từ xa.
- Task phụ thuộc thời gian hiện tại hoặc trạng thái dịch vụ bên ngoài mà không khai báo.
- Task tạo output không xác định hoặc có side effect không thể khôi phục.

Nếu task thực hiện side effect bên ngoài, việc khôi phục output từ cache không thể tái thực hiện side effect đó. Ví dụ, cache hit của task publish không thể thay thế thao tác publish lên repository. Những task như vậy thường nên không cache.

### Cacheability của custom task

Với custom task có thể cache, Gradle task type thường cần được đánh dấu bằng **@CacheableTask**. Các input/output phải được khai báo bằng annotation/property phù hợp.

Ví dụ:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

@CacheableTask
abstract class GenerateIndex extends DefaultTask {
    @InputDirectory
    abstract DirectoryProperty getSourceDirectory()

    @OutputFile
    abstract RegularFileProperty getIndexFile()

    @TaskAction
    void generate() {
        def source = sourceDirectory.get().asFile
        def destination = indexFile.get().asFile

        destination.parentFile.mkdirs()
        def names = source.listFiles()
            .findAll { it.isFile() }
            .collect { it.name }
            .sort()

        destination.text = names.join(System.lineSeparator())
    }
}
~~~

Đây là ví dụ đơn giản. Trong task thực tế, cần khai báo đầy đủ input ảnh hưởng kết quả, xử lý thư mục con theo yêu cầu, encoding, tool version và các tham số khác. Không đánh dấu **@CacheableTask** chỉ để ép Gradle tạo cache entry; phải bảo đảm output có thể tái tạo từ input đã khai báo.

### Task không nên cache

Một task có thể được đánh dấu **@DisableCachingByDefault** kèm lý do nếu cacheability không phù hợp. Một số task type của Gradle/plugin đã có chính sách cache riêng.

Nếu task tạo file nhưng output phụ thuộc vào biến môi trường không khai báo, timestamp hoặc dịch vụ bên ngoài, cache entry có thể không đại diện đúng kết quả. Hãy sửa mô hình input/output hoặc giữ task không cache.

## 8. Khai báo input/output chính xác là điều kiện cốt lõi

Build cache và up-to-date checking chỉ đáng tin cậy khi Gradle biết đầy đủ dữ liệu ảnh hưởng đến task.

Các annotation thường gặp:

| Annotation | Ý nghĩa |
|---|---|
| **@Input** | Giá trị scalar/configuration ảnh hưởng output |
| **@InputFile** | Một file input |
| **@InputFiles** | Tập file input |
| **@InputDirectory** | Thư mục input |
| **@Classpath** | Classpath input với normalization phù hợp |
| **@CompileClasspath** | Compile classpath được chuẩn hóa cho mục đích biên dịch |
| **@OutputFile** | File output |
| **@OutputDirectory** | Thư mục output |
| **@Nested** | Object chứa các property input/output được khai báo |
| **@Internal** | Property không được dùng làm input/output fingerprint |
| **@LocalState** | Trạng thái cục bộ không được cache như output task |

Ví dụ, task tạo report từ source file và một option:

~~~groovy
@CacheableTask
abstract class BuildReport extends DefaultTask {
    @InputFiles
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract ConfigurableFileCollection getSourceFiles()

    @Input
    abstract Property<String> getReportTitle()

    @OutputFile
    abstract RegularFileProperty getReportFile()

    @TaskAction
    void createReport() {
        // Generate the report using declared inputs.
    }
}
~~~

Ở đây, report phụ thuộc vào source files và report title. Nếu task còn phụ thuộc vào template, tool version hoặc option khác, chúng cũng phải được khai báo.

### Thiếu input làm cache key sai

Giả sử task đọc thêm file **rules.json** nhưng không khai báo file đó là input. Khi rules thay đổi, Gradle có thể vẫn thấy những input đã khai báo không đổi và tái sử dụng output cũ.

Kết quả là task có thể được đánh dấu up-to-date hoặc cache hit dù output lẽ ra phải thay đổi.

Nguyên tắc: **mọi dữ liệu ảnh hưởng kết quả phải được mô tả trong task inputs**. Không nên dựa vào file path, biến môi trường, system property hoặc trạng thái bên ngoài mà Gradle không biết.

### Khai báo output đầy đủ

Task phải khai báo các output mà nó sở hữu. Nếu task ghi file nhưng không đánh dấu output, Gradle không thể quản lý trạng thái file đó đúng cách.

Output nên nằm trong thư mục build do task/project quản lý. Tránh để hai task cùng ghi một output hoặc để task ghi đè source file của người phát triển.

## 9. Path sensitivity và tính di chuyển của cache

Một task có thể tạo cùng output ở hai workspace khác nhau, nhưng đường dẫn tuyệt đối đến source file khác nhau.

Ví dụ:

~~~text
Máy A: C:\agent\work\shop\src\Main.java
Máy B: D:\runner\checkout\shop\src\Main.java
~~~

Nếu đường dẫn tuyệt đối bị coi là một phần không cần thiết của input fingerprint, hai build tương đương có thể không dùng chung cache entry. Gradle có các cơ chế normalization và path sensitivity để mô tả cách đường dẫn input ảnh hưởng kết quả.

Với file input, có thể dùng:

~~~groovy
@InputFiles
@PathSensitive(PathSensitivity.RELATIVE)
abstract ConfigurableFileCollection getSourceFiles()
~~~

Một số lựa chọn path sensitivity:

- **ABSOLUTE**: đường dẫn tuyệt đối có ý nghĩa đối với task.
- **RELATIVE**: đường dẫn tương đối so với root của input collection có ý nghĩa.
- **NAME_ONLY**: chỉ tên file có ý nghĩa.
- **NONE**: nội dung file được quan tâm, đường dẫn không ảnh hưởng.

Chỉ chọn normalization phù hợp với logic task. Nếu task thật sự cần đường dẫn tuyệt đối để tạo output, không được khai báo **NONE** hoặc **RELATIVE** chỉ để tăng cache hit.

### Classpath normalization

Classpath có quy tắc normalization riêng. **@Classpath** và **@CompileClasspath** giúp Gradle fingerprint classpath theo mục đích sử dụng thay vì coi mọi byte hoặc mọi path giống input file thông thường.

Ví dụ, task compiler thường không cần cache miss chỉ vì metadata hoặc resource không ảnh hưởng đến compile ABI thay đổi. Dùng annotation phù hợp giúp cache key phản ánh đúng những gì task cần.

Tuy nhiên, annotation phải phù hợp với cách task sử dụng classpath. Nếu task đọc resource hoặc metadata trong JAR, normalization compile classpath có thể không thể hiện đầy đủ mọi input cần thiết; cần chọn input model đúng với hành vi thực tế.

### Relocatable task

Task được thiết kế relocatable khi cùng input logic có thể tạo cùng output dù project checkout ở vị trí khác. Để đạt điều đó:

- Tránh nhúng absolute workspace path vào output nếu không cần.
- Dùng path sensitivity phù hợp.
- Dùng Gradle-managed file/property thay cho đọc path từ môi trường.
- Không phụ thuộc current working directory ngầm.
- Khai báo toolchain và dependency ảnh hưởng kết quả.
- Tránh đọc file ngoài input collection.

Relocatability giúp remote cache có ích giữa các máy CI và developer.

## 10. Incremental task execution khác build cache

Incremental execution cho phép task xử lý phần input thay đổi thay vì xử lý lại toàn bộ tập dữ liệu. Task vẫn được thực thi, nhưng nhận thông tin về những file đã thêm, sửa hoặc xóa.

Ví dụ, một task phân tích hàng nghìn file có thể chỉ cần xử lý những file thay đổi kể từ lần trước. Điều này khác với build cache:

- Build cache có thể khôi phục toàn bộ output của task từ cache.
- Incremental execution chạy task action và xử lý phần thay đổi.
- Up-to-date checking có thể bỏ qua task action hoàn toàn nếu không có thay đổi và output còn hợp lệ.

### InputChanges và incremental file input

Trong custom task, có thể khai báo file collection incremental và nhận **InputChanges**:

~~~groovy
import org.gradle.work.InputChanges

@Incremental
@InputDirectory
@PathSensitive(PathSensitivity.RELATIVE)
abstract DirectoryProperty getSourceDirectory()

@TaskAction
void process(InputChanges changes) {
    changes.getFileChanges(sourceDirectory).each { change ->
        switch (change.changeType) {
            case ADDED:
            case MODIFIED:
                // Process the changed file.
                break
            case REMOVED:
                // Remove the derived output for the removed file.
                break
        }
    }
}
~~~

Đoạn này minh họa cơ chế. Task cần thiết kế output tương ứng với từng input và xử lý cả file bị xóa. Nếu chỉ xử lý file mới/sửa mà không xóa output dẫn xuất của file đã xóa, kết quả sẽ bị cũ.

Incremental task vẫn cần hỗ trợ lần chạy đầu tiên, khi Gradle không có lịch sử input phù hợp hoặc task được yêu cầu chạy đầy đủ. Task phải có đường xử lý an toàn cho trường hợp không thể thực hiện incremental update.

### Khi incremental execution có ích?

Phù hợp với công việc:

- Phân tích từng source/resource file.
- Sinh output riêng cho từng input file.
- Xây dựng index từ tập file lớn.
- Chuyển đổi nhiều file độc lập.
- Cập nhật metadata theo thay đổi của từng file.

Không phải mọi task đều hưởng lợi. Nếu output phụ thuộc toàn bộ tập input hoặc chi phí xác định thay đổi lớn hơn việc xử lý lại, full execution có thể đơn giản và nhanh hơn.

## 11. Configuration cache là một cơ chế riêng

Configuration cache lưu kết quả cấu hình build, gồm thông tin cần thiết để tái sử dụng build model và task graph trong lần chạy tương thích tiếp theo.

Bật bằng command line:

~~~shell
./gradlew build --configuration-cache
~~~

Hoặc cấu hình trong **gradle.properties**:

~~~properties
org.gradle.configuration-cache=true
~~~

Configuration cache giúp giảm thời gian configuration phase. Nó không lưu JAR dependency như dependency cache và không lưu output task như build cache.

| Cơ chế | Dữ liệu được tái sử dụng |
|---|---|
| Dependency cache | Metadata và artifact dependency |
| Build cache | Output của task |
| Configuration cache | Kết quả cấu hình build |
| Up-to-date checking | Output hiện có của task khi input không đổi |

Một build có thể bật cả configuration cache và build cache. Tuy nhiên, task/plugin phải tương thích với configuration cache; việc truy cập Project model hoặc trạng thái mutable không phù hợp trong task action có thể khiến build không lưu/tái sử dụng configuration cache được.

### Không dùng configuration cache để giải quyết output thiếu

Nếu task cần file output từ project khác, phải khai báo dependency/input/output đúng. Configuration cache không tự suy ra task producer từ một đường dẫn hard-code và không bảo đảm file đó tồn tại.

### Configuration cache và dependency resolution

Configuration cache có thể lưu một số thông tin cấu hình liên quan đến dependency resolution theo cơ chế Gradle hỗ trợ, nhưng dependency artifacts vẫn thuộc dependency cache. Hai cache có thể phối hợp nhưng có vòng đời và mục đích riêng.

## 12. Clean, rerun và các tùy chọn chẩn đoán

Các tùy chọn dòng lệnh thường dùng:

| Tùy chọn | Tác dụng |
|---|---|
| **--build-cache** | Bật build cache cho lần chạy |
| **--no-build-cache** | Không dùng build cache trong lần chạy |
| **--offline** | Chỉ dùng dependency đã cache, không truy cập repository |
| **--refresh-dependencies** | Kiểm tra/làm mới trạng thái dependency resolution |
| **--rerun-tasks** | Buộc task được chọn thực thi lại, bỏ qua up-to-date checking |
| **--dry-run** | Hiển thị task dự kiến mà không chạy task action thông thường |
| **--info** | Cung cấp thêm thông tin về task execution/cache |
| **--debug** | Log chi tiết hơn để điều tra sâu |

### --rerun-tasks không đồng nghĩa xóa cache

~~~shell
./gradlew build --rerun-tasks
~~~

Tùy chọn này yêu cầu Gradle chạy lại các task được chọn thay vì bỏ qua vì up-to-date. Nó không tự xóa dependency cache hoặc toàn bộ build cache.

Khi build cache bật, hành vi cần được đọc cùng các tùy chọn cache và task. Nếu mục tiêu là xác minh task action thực sự chạy, có thể kết hợp **--rerun-tasks** với **--no-build-cache** để loại trừ việc khôi phục output từ cache.

### clean và build cache

~~~shell
./gradlew clean build --build-cache
~~~

**clean** xóa output của project. Khi các task chạy sau đó, Gradle có thể khôi phục output từ build cache nếu cache entry phù hợp; nếu không, task sẽ thực thi.

Đây là cách thường dùng để kiểm tra khả năng tái sử dụng build cache sau khi output workspace đã bị xóa. Cần nhớ **clean** có thể xóa nhiều output, nên không dùng trong lúc có tiến trình khác đang cần các file đó.

## 13. Cách đọc task outcome và cache log

Gradle hiển thị outcome của task trong console/log. Một số trạng thái quan trọng:

| Outcome | Ý nghĩa |
|---|---|
| **UP-TO-DATE** | Output hiện có còn hợp lệ theo input; task không cần chạy |
| **FROM-CACHE** | Output được khôi phục từ build cache |
| **SUCCESS** | Task đã thực thi thành công |
| **NO-SOURCE** | Task không có source/input phù hợp để xử lý |
| **SKIPPED** | Task bị bỏ qua theo điều kiện hoặc trạng thái |
| **FAILED** | Task thực thi hoặc xử lý thất bại |

Ví dụ:

~~~text
> Task :domain:compileJava UP-TO-DATE
> Task :app:compileJava FROM-CACHE
> Task :app:jar
~~~

Có thể đọc:

- **:domain:compileJava** không cần chạy vì output hiện có hợp lệ.
- **:app:compileJava** lấy output từ build cache.
- **:app:jar** thực thi trong lần build này.

Không nên suy luận rằng mọi task không chạy action đều có cùng nguyên nhân. **UP-TO-DATE**, **FROM-CACHE**, **SKIPPED** và **NO-SOURCE** là những trạng thái khác nhau.

### Dùng --info để xem cache behavior

~~~shell
./gradlew build --build-cache --info
~~~

Log mức info có thể cho biết task được bỏ qua vì up-to-date, có cache key, tìm cache entry, cache hit/miss hoặc không được cache vì lý do cụ thể. Nội dung log chính xác phụ thuộc phiên bản Gradle và task/plugin.

Nếu task không có cache entry, kiểm tra:

- Task type có cacheable không?
- Tất cả input/output đã khai báo chưa?
- Có input không xác định hoặc không thể fingerprint không?
- Task có bị đánh dấu non-cacheable không?
- Input có thay đổi giữa hai lần build không?
- Cache có được bật và truy cập được không?
- Remote cache có quyền đọc/ghi phù hợp không?

## 14. Remote cache và an toàn chuỗi cung ứng

Remote build cache có thể tăng tốc CI đáng kể, nhưng cache server là một nguồn cung cấp output cho build. Nếu một actor không đáng tin cậy có thể ghi output vào cache key mà build tin cậy sử dụng, artifact được khôi phục có thể ảnh hưởng đến kết quả build.

Các nguyên tắc vận hành:

- Chỉ cho phép CI job đáng tin cậy push cache.
- Giới hạn quyền ghi theo branch/repository/environment.
- Developer và job thông thường có thể chỉ cần quyền read.
- Bảo vệ endpoint và credential.
- Không ghi secret vào input, log hoặc cache entry.
- Không chia sẻ cache giữa những build có chính sách tin cậy không tương đương.
- Dùng dependency verification và kiểm soát artifact repository cho dependency bên ngoài.
- Theo dõi cache server, retention và quyền truy cập.

### Build cache không thay thế dependency verification

Build cache lưu output task; dependency verification kiểm tra tính toàn vẹn/xác thực của artifact dependency theo cấu hình verification. Hai cơ chế bảo vệ những đối tượng khác nhau.

Ví dụ, dependency verification có thể kiểm tra checksum hoặc signature của JAR đã tải. Build cache có thể lưu output compile task được tạo từ source và dependency đó.

Một cache hit không có nghĩa Gradle vừa tải và xác minh lại mọi dependency. Cần quản lý dependency verification và cache policy theo yêu cầu bảo mật của tổ chức.

## 15. Vì sao cache miss xảy ra?

Cache miss không nhất thiết là lỗi. Nó có nghĩa Gradle không tìm thấy output có thể tái sử dụng cho task/input hiện tại.

Một số nguyên nhân phổ biến:

| Nguyên nhân | Hệ quả |
|---|---|
| Source hoặc resource thay đổi | Cache key khác |
| Compiler option thay đổi | Output có thể khác nên cần task execution/cache entry khác |
| Dependency/classpath thay đổi | Task input thay đổi |
| Task implementation thay đổi | Cache key có thể thay đổi |
| Một input chưa được khai báo | Có nguy cơ cache sai thay vì cache miss; cần sửa task model |
| Task không cacheable | Không tạo/khôi phục cache entry |
| Output không được khai báo đúng | Gradle không quản lý output theo cách cần thiết |
| Absolute path ảnh hưởng fingerprint | Cache không dùng chung tốt giữa workspace |
| Remote cache không truy cập được | Gradle không thể đọc/ghi remote entry |
| Entry đã bị eviction | Cache miss dù trước đó từng có entry |
| Cache key khác do toolchain/environment | Không thể dùng lại entry trước đó |

### Cache miss do input thay đổi là hành vi đúng

Nếu source code hoặc dependency thực sự thay đổi, task cần thực thi lại hoặc dùng cache entry tương ứng với input mới. Mục tiêu không phải ép mọi task thành **FROM-CACHE**, mà là bảo đảm task chỉ chạy khi cần và output được tái sử dụng khi thực sự tương đương.

### Tránh làm cache key thiếu input

Cache miss làm build chậm hơn nhưng thường an toàn. Cache hit sai vì thiếu input có thể tạo output lỗi mà khó phát hiện. Khi thiết kế custom task, ưu tiên tính đúng đắn và đầy đủ của input trước khi tối ưu cache hit rate.

## 16. Ví dụ luồng build qua nhiều lần chạy

Giả sử build gồm:

~~~text
:domain:compileJava
:domain:jar
:app:compileJava
:app:test
:app:jar
~~~

### Lần đầu trên máy A

- Dependency chưa có trong dependency cache: Gradle tải artifact.
- Task compile chưa có output/cache entry: thực thi.
- Task jar chưa có output/cache entry: thực thi.
- Output của task cacheable có thể được lưu vào local/remote build cache.

### Lần thứ hai trên cùng workspace

- Dependency metadata/artifact được tái sử dụng nếu còn hợp lệ.
- Nếu input không đổi và output còn tồn tại, task có thể **UP-TO-DATE**.
- Task không cần đọc build cache nếu output local vẫn hợp lệ.

### Sau khi clean trên cùng máy

- Output trong project bị xóa.
- Dependency cache vẫn có thể còn nguyên.
- Nếu build cache có entry phù hợp, task cacheable có thể **FROM-CACHE**.
- Task không có cache entry phải thực thi lại.

### Trên máy B với workspace khác

- Dependency cache của máy B có thể đã có hoặc chưa có thư viện.
- Remote build cache có thể cung cấp output của task nếu cache key tương thích.
- Task không relocatable hoặc input path được fingerprint không phù hợp có thể không dùng được entry từ máy A.
- Task không cacheable vẫn phải thực thi.

### Sau khi thay đổi một source file

- Dependency cache thường không cần tải lại chỉ vì source file thay đổi.
- Task compile liên quan có thể cần chạy lại hoặc khôi phục cache entry cho input mới.
- Task downstream có thể chạy lại nếu output upstream thay đổi.
- Task không phụ thuộc output thay đổi có thể vẫn up-to-date.

Luồng này cho thấy dependency cache và build cache có thể cùng hoạt động nhưng không phụ thuộc trực tiếp vào nhau.

## 17. Một số anti-pattern về cache

| Anti-pattern | Vì sao có hại | Hướng xử lý |
|---|---|---|
| Đọc file ngoài input khai báo | Gradle không biết dữ liệu ảnh hưởng output | Khai báo file là input |
| Dùng thời gian hiện tại trong task cacheable | Cùng input có thể tạo output khác | Khai báo giá trị thời gian hoặc không cache task |
| Task ghi vào thư mục project khác | Ownership/output không rõ, dễ xung đột | Ghi output vào vùng task sở hữu |
| Hai task cùng ghi một file | Race condition và cache output không xác định | Mỗi output có một producer |
| Cache task publish/deploy có side effect | Cache hit không thực hiện publish/deploy | Giữ task side effect non-cacheable |
| Đánh dấu cacheable để ép tăng tốc | Output có thể được tái sử dụng sai | Chỉ cache task xác định từ input khai báo |
| Hard-code absolute path | Giảm relocatability | Dùng layout/provider và path sensitivity phù hợp |
| Bỏ qua task cacheability warning | Có thể che giấu input/output không đầy đủ | Đọc lý do và sửa task model |
| Xóa toàn bộ Gradle User Home để xử lý mọi lỗi | Tốn thời gian tải lại và mất cache dùng chung | Chẩn đoán đúng cache layer trước |
| Dùng **--refresh-dependencies** cho lỗi task output | Không xử lý build cache/task input | Kiểm tra task output/cache đúng lớp |

## 18. Quy trình chẩn đoán khi build không dùng cache như mong đợi

Khi một build chậm hoặc task liên tục thực thi, có thể lần theo các bước:

1. **Xác định task chậm**: xem task nào tốn thời gian và nó thuộc project/source set nào.
2. **Xác định cache layer**: vấn đề là dependency tải lại, configuration phase chậm, task chạy lại hay task không lấy được build cache?
3. **Xem outcome**: **UP-TO-DATE**, **FROM-CACHE**, **SUCCESS**, **SKIPPED** hay **NO-SOURCE**.
4. **Bật log phù hợp**: dùng **--info** để quan sát dependency/cache behavior.
5. **Kiểm tra input/output**: xác nhận task đã khai báo mọi dữ liệu ảnh hưởng output.
6. **Kiểm tra cacheability**: task có hỗ trợ build cache không và có lý do disable không?
7. **Kiểm tra relocatability**: input path, absolute path và environment có làm cache key khác giữa máy không?
8. **Kiểm tra cache service**: remote endpoint, credential, network và quyền push/pull.
9. **So sánh hai lần build có kiểm soát**: chạy cùng commit, cùng toolchain và cùng cấu hình để phân biệt cache miss hợp lệ với cấu hình không nhất quán.
10. **Xác minh kết quả**: output khôi phục phải tương đương output task thực thi từ cùng input.

Một số lệnh hữu ích:

~~~shell
./gradlew build --info
./gradlew build --build-cache --info
./gradlew clean build --build-cache --info
./gradlew build --no-build-cache --rerun-tasks
./gradlew build --offline
./gradlew build --refresh-dependencies
~~~

Không chạy tất cả tùy chọn cùng lúc một cách máy móc. Mỗi lệnh kiểm tra một giả thuyết khác nhau; chọn lệnh dựa trên cache layer đang điều tra.

## 19. Bảng so sánh nhanh các cơ chế

| Cơ chế | Dữ liệu | Phạm vi | Khi nào tái sử dụng? | Lệnh/cấu hình thường gặp |
|---|---|---|---|---|
| Dependency cache | Metadata và artifact dependency | Gradle User Home/repository cache | Dependency resolution còn hợp lệ | **--offline**, **--refresh-dependencies** |
| Up-to-date checking | Output hiện có và snapshot input/output | Workspace của project | Input không đổi và output còn hợp lệ | Mặc định; **--rerun-tasks** để buộc chạy |
| Local build cache | Output task | Máy local | Cache key khớp và task cacheable | **--build-cache** |
| Remote build cache | Output task chia sẻ | Nhiều máy/CI | Cache key khớp và quyền truy cập cho phép | **buildCache { remote(...) }** |
| Incremental execution | Thay đổi của input | Task cụ thể | Task hỗ trợ xử lý change set | **InputChanges**, **@Incremental** |
| Configuration cache | Kết quả configuration/build model | Gradle User Home | Build configuration tương thích | **--configuration-cache** |

## 20. Quy trình chọn và cấu hình cache

Khi muốn tăng tốc một build, hãy xác định mục tiêu trước:

- **Tốn thời gian tải thư viện**: xem repository, dependency cache, offline mode, dynamic/changing version và dependency verification.
- **Task lặp lại trên cùng workspace**: kiểm tra up-to-date checking và input/output.
- **Task chạy trên nhiều workspace/CI agent**: xem build cache, remote cache và relocatability.
- **Task xử lý tập file lớn**: cân nhắc incremental execution.
- **Configuration phase chậm**: xem configuration cache và compatibility của plugin/build logic.

Sau đó thực hiện theo thứ tự:

1. Đo thời gian build và xác định phase/task tốn thời gian.
2. Chọn cache layer giải quyết đúng phần chậm.
3. Khai báo input/output đầy đủ trước khi bật cache cho custom task.
4. Bật local build cache và xác nhận cache hit ở lần build sau hoặc sau clean.
5. Nếu nhiều máy cần chia sẻ output, cấu hình remote cache với quyền đọc/ghi rõ ràng.
6. Kiểm tra task có relocatable và không phụ thuộc trạng thái ẩn.
7. Quan sát task outcome và log để hiểu lý do cache hit/miss.
8. Kiểm tra output cache có tương đương với output tạo mới từ cùng input.
9. Tách riêng dependency cache, build cache và configuration cache khi điều tra lỗi.

Cache hiệu quả không chỉ làm build nhanh hơn. Nó cần bảo đảm output được tái sử dụng đúng khi input tương đương, và task được thực thi lại khi dữ liệu ảnh hưởng kết quả thay đổi. Dependency cache giúp Gradle không phải tải lại thư viện không cần thiết; up-to-date checking giữ output local còn hợp lệ; build cache chia sẻ output task; incremental execution xử lý phần input thay đổi; configuration cache giảm chi phí cấu hình.
