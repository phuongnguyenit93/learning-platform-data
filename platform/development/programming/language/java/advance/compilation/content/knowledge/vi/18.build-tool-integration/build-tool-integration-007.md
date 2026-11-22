# Xác định đầu vào của build cache và tránh dùng kết quả sai cấu hình

## 1. Build cache giải quyết vấn đề gì?

Trong build Java, các bước biên dịch, sinh mã, kiểm thử, đóng gói hoặc tạo tài liệu có thể mất nhiều thời gian. Build cache cho phép Gradle sử dụng lại **đầu ra đã có** của một task khi những đầu vào có liên quan không đổi. Tuy nhiên, cache chỉ đúng khi ta mô tả đầy đủ quan hệ:

> **Cùng dữ liệu đầu vào, cùng công cụ và cùng cấu hình có ảnh hưởng thì phải tạo cùng nội dung đầu ra.**

Hình dung `output = f(source, dependencies, toolchain, options, task configuration, external inputs)`. Cache key được xây từ những đầu vào Gradle biết. Nếu một yếu tố **ảnh hưởng đầu ra** nhưng **không được khai báo**, cache có thể trả về kết quả sinh bởi cấu hình khác. Đó là một *cache hit sai*. Nếu khai báo cả yếu tố **không ảnh hưởng đầu ra**, cache sẽ miss không cần thiết, gây lãng phí thời gian.

Ví dụ, một task tạo file cấu hình sản phẩm từ `-Pedition=community` hay `-Pedition=enterprise`. Nếu action đọc giá trị này trực tiếp từ project nhưng task không công bố nó là input, việc đổi edition có thể không làm đổi cache key. Một bản build enterprise có thể vô tình nhận artifact community. Đây là lỗi correctness chứ không đơn thuần là vấn đề tối ưu.

Mục tiêu của bài là xác định input thật, khai báo metadata chuẩn của Gradle, so sánh kết quả khi đổi cấu hình và thiết kế task đủ tái lập để dùng build cache an toàn.

## 2. Phân biệt up-to-date, build cache và configuration cache

| Cơ chế | Trả lời câu hỏi nào? | Trạng thái thường thấy |
|---|---|---|
| **Up-to-date check** | Task đã chạy trong workspace này và input/output có còn khớp không? | `UP-TO-DATE` |
| **Build cache** | Có artifact của một lần chạy tương đương để khôi phục mà không thực thi action không? | `FROM-CACHE` |
| **Configuration cache** | Có thể tái sử dụng trạng thái *cấu hình build* để bỏ qua bước cấu hình không? | Log tái sử dụng configuration cache |

Ba cơ chế liên quan nhưng không đồng nhất. Build cache lưu **task outputs**, còn configuration cache lưu **trạng thái cấu hình build**. Một task chạy lại và tạo output mới không có nghĩa là configuration cache không hiệu quả. Dòng `FROM-CACHE` chỉ chứng minh Gradle tìm được entry ứng với fingerprint **đã khai báo**; nó không chứng minh fingerprint đã bao gồm *mọi* yếu tố ảnh hưởng.

Trong Gradle, có thể dùng `--build-cache` khi chạy lệnh hoặc đặt `org.gradle.caching=true` trong `gradle.properties` để bật sử dụng build cache. Task phải đủ điều kiện để cache: task tích hợp được Gradle hỗ trợ theo hợp đồng của nó; task tùy biến cần khai báo đúng input, output và thường được đánh dấu `@CacheableTask` sau khi bảo đảm tính quyết định.

## 3. Xác định đầy đủ đầu vào của một task

Điểm xuất phát nên là **mọi thứ action và công cụ mà nó gọi thực sự đọc**, bao gồm dữ liệu gián tiếp. Sau đó xác định kiểu khai báo:

| Nguồn | Ví dụ thực tế | Cách biểu diễn |
|---|---|---|
| Source và resource | `.java`, schema, config, template, processor descriptor | `@InputFile`, `@InputFiles` và chính sách path |
| Classpath | JAR của thư viện, code generator, annotation processor | `@Classpath`, một số trường hợp `@CompileClasspath` |
| Tham số | debug, edition, target release, feature flag, tên package | `@Input` / properties có kiểu |
| Toolchain và tool version | JDK, Java compiler, compiler plugin, generator | Gradle toolchain/task API hoặc input version rõ ràng |
| Hệ thống | biến môi trường, system property, locale, timezone, encoding | Chuyển giá trị được sử dụng thành input hoặc chuẩn hóa |
| Dữ liệu ngoài | git SHA, API schema từ server, network response, clock | Snapshot/version/hash ổn định hoặc không cache |
| Output | class files, JAR, generated source, report | `@OutputFile` / `@OutputDirectory` |

**Input trực tiếp** là dữ liệu action truy cập. **Input gián tiếp** là dữ liệu ảnh hưởng công cụ mà action gọi: chẳng hạn tệp mà shell script đọc, JDK chạy compiler, hoặc biến môi trường truyền vào code generator. Các input có **giá trị mặc định** cũng quan trọng. Ví dụ, giá trị mặc định `targetRelease=17` phải tham gia vào hợp đồng đầu vào nếu nó thay đổi bytecode.

Một cách rà soát hiệu quả: vẽ từng đường đọc dữ liệu từ nguồn đến output. Nếu đổi nguồn đó có thể thay đổi bất kỳ byte output nào, nguồn phải xuất hiện trong fingerprint hoặc task không được tái sử dụng qua cache.

Với Gradle `JavaCompile`, hãy cấu hình qua `java.toolchain`, `options.release`, compiler arguments và dependency declarations chuẩn. Gradle đã có cơ chế theo dõi nhiều input của task này; không tự thay thế bằng `Exec` gọi `javac` rồi chỉ khai báo mỗi thư mục source. Phân biệt **version của JDK thực thi compiler** với **mục tiêu bytecode**: cả hai đều có thể ảnh hưởng kết quả.

## 4. Task cacheable mẫu bằng Gradle Groovy DSL

Ví dụ này có thể đặt trực tiếp vào `build.gradle` của một dự án Gradle thử nghiệm. Nó sinh một file metadata từ đúng hai property. Class chứa hợp đồng input/output tách khỏi action; action không đọc nguồn ẩn.

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

@CacheableTask
abstract class GenerateBuildDescriptor extends DefaultTask {
    @Input
    abstract Property<String> getEdition()

    @Input
    abstract Property<String> getSchemaVersion()

    @OutputFile
    abstract RegularFileProperty getDestination()

    @TaskAction
    void generate() {
        File target = destination.get().asFile
        target.parentFile.mkdirs()

        String content = "edition=" + edition.get() + "\n" +
                         "schemaVersion=" + schemaVersion.get() + "\n"
        target.setText(content, "UTF-8")
    }
}

tasks.register("generateBuildDescriptor", GenerateBuildDescriptor) {
    edition.set(providers.gradleProperty("edition").orElse("community"))
    schemaVersion.set(providers.gradleProperty("schemaVersion").orElse("1"))
    destination.set(layout.buildDirectory.file("generated/build-descriptor.properties"))
}
~~~

Chạy tại root dự án có Gradle Wrapper:

~~~bash
./gradlew generateBuildDescriptor --build-cache --info
./gradlew generateBuildDescriptor -Pedition=enterprise --build-cache --info
~~~

Trên Windows dùng `gradlew.bat` thay cho `./gradlew`. Khi chạy mặc định, file `build/generated/build-descriptor.properties` có nội dung:

~~~properties
edition=community
schemaVersion=1
~~~

Khi truyền `-Pedition=enterprise`, giá trị đầu tiên chuyển thành `edition=enterprise`, tạo kết quả khác và cache key phải phản ánh khác biệt. Khi chạy cùng input lần thứ hai mà output còn tồn tại, có thể thấy `UP-TO-DATE`. Để kiểm tra **phục hồi từ cache**, xóa output của bài thử rồi chạy lại cùng tham số với `--build-cache --info`; Gradle có thể báo `FROM-CACHE` nếu cache chứa entry hợp lệ. Không suy luận rằng lần chạy đầu tiên phải hit cache.

Vì file đầu ra được xác định hoàn toàn bởi `edition` và `schemaVersion`, task phù hợp để cache. `@CacheableTask` là cam kết về việc **có thể tái lập đầu ra**; annotation này không khiến một task có nguồn đọc ngầm trở nên đúng.

## 5. Các lỗi cấu hình làm cache trả sai kết quả

### 5.1. Đọc biến môi trường hoặc project property ngoài hợp đồng input

**Sai:** action gọi `System.getenv("BUILD_PROFILE")` rồi nhúng kết quả vào file nhưng không khai báo giá trị này là input. Hai lần chạy với profile khác nhau có thể dùng chung khóa.

**Sửa:** thêm property và nối provider tương ứng. Đoạn sau là **mảnh code bổ sung** vào class và đoạn `tasks.register` ở mục 4; trong action cũng phải chuyển sang đọc `profile.get()` thay cho `System.getenv(...)`:

~~~groovy
// Trong class GenerateBuildDescriptor:
@Input
abstract Property<String> getProfile()

// Trong tasks.register("generateBuildDescriptor", ...):
profile.set(providers.environmentVariable("BUILD_PROFILE").orElse("dev"))
~~~

Nếu profile không thực sự ảnh hưởng output, không cần đưa nó vào input. Tránh nhét toàn bộ biến môi trường vào cache key vì các biến không liên quan sẽ làm cache miss quá mức và có thể lộ metadata nhạy cảm.

### 5.2. Khai báo tên file nhưng quên nội dung file

**Sai:** task có `@Input String getTemplatePath()`, sau đó mở file ở đường dẫn ấy và dùng nội dung để sinh mã. Nội dung template đổi nhưng chuỗi đường dẫn vẫn giữ nguyên: Gradle có thể cho phép reuse sai.

**Sửa:** khai báo file input và normalization đường dẫn. Đây là đoạn **trong class task tùy biến**, cần các import tương ứng từ `org.gradle.api.tasks`:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
abstract RegularFileProperty getTemplateFile()
~~~

`@InputFile` xác định nội dung file được theo dõi, còn `PathSensitivity.RELATIVE` làm cho vị trí **tương đối** trở thành phần đường dẫn có ý nghĩa. Với nhiều file, dùng `@InputFiles` và file collection phù hợp. Không tùy tiện chọn `PathSensitivity.NONE` chỉ để tăng hit: nếu tên thư mục hoặc đường dẫn tương đối ảnh hưởng cách ghép output, chúng phải tham gia khóa.

### 5.3. Áp dụng sai classpath normalization

`@Classpath` dành cho dữ liệu được hiểu là classpath, ví dụ JAR chứa implementation cần chạy bởi code generator. `@CompileClasspath` có thể bỏ qua những thay đổi implementation không ảnh hưởng **ABI** của dependency khi đầu ra chỉ phụ thuộc vào API dùng để biên dịch. Không dùng `@CompileClasspath` cho task cần đọc method body, resource hay chạy mã của dependency. Sai normalization có thể làm Gradle coi hai input khác nhau về mặt hành vi là tương đương.

Đối với compilation thông thường, ưu tiên task Gradle tích hợp và dependency/toolchain API của nó để tránh mô tả thủ công classpath không đầy đủ.

### 5.4. Đầu ra và dữ liệu bất định

Task ghi `report.json` và `manifest.txt` nhưng chỉ khai báo `report.json` là output có nguy cơ không khôi phục đầy đủ. Task thêm `Instant.now()`, random UUID, hostname hoặc đường dẫn tuyệt đối vào artifact thì hai lần chạy cùng fingerprint có thể ra byte khác nhau. Hướng sửa là công bố đủ outputs; loại bỏ hoặc chuẩn hóa dữ liệu bất định; hoặc khai báo những giá trị thực sự cần dùng thành input. Nếu không bảo đảm deterministic, không đánh dấu task cacheable.

### 5.5. Công cụ và service ngoài

Một task `Exec` chạy compiler/generator có thể phụ thuộc vào executable version, command-line flags, file config công cụ tự mở, biến môi trường, locale và resource ngoài. Một task tải schema từ server phụ thuộc vào response từng thời điểm. Hãy dùng task tích hợp có metadata đúng, hoặc cung cấp snapshot schema có version/hash làm file input. Nếu nguồn ngoài không cố định được thì tránh cache task đó. Không lấy giá trị endpoint URL làm đại diện cho **nội dung trả về** có thể đổi ở cùng URL.

## 6. Quy tắc chọn annotation và normalization

| Annotation / property | Ý nghĩa | Cạm bẫy |
|---|---|---|
| `@Input` | Chuỗi, số, boolean, option, version hoặc property thuần | Path string không đại diện cho nội dung file |
| `@InputFile`, `@InputFiles` | Nội dung tệp được task đọc | Phải chọn path sensitivity phù hợp |
| `@Classpath` | Classpath đầu vào theo ngữ nghĩa classpath | Đừng coi mọi resource như source file |
| `@CompileClasspath` | Dependency chỉ ảnh hưởng ABI mà task sử dụng | Không phù hợp khi phụ thuộc implementation |
| `@Nested` | Object chứa các property input/output khác | Property con vẫn cần metadata đầy đủ |
| `@OutputFile`, `@OutputDirectory` | File hoặc directory task tạo | Tránh nhiều task ghi chung output |
| `@Internal` | Property nội bộ thực sự không ảnh hưởng kết quả | Dùng sai có thể che input quan trọng |

Dùng đường dẫn tương đối giúp tái sử dụng cache giữa checkout khác thư mục, **chỉ khi đường dẫn tuyệt đối không ảnh hưởng output**. Nếu file name quan trọng, policy phải bảo tồn file name; nếu vị trí tương đối quan trọng, dùng `RELATIVE`. Với các input thật sự không phân biệt CRLF/LF, có thể dùng `@NormalizeLineEndings` kết hợp metadata phù hợp. Chuẩn hóa cả encoding để file output không đổi giữa OS.

Thứ tự cũng có thể là một phần input: ví dụ classpath hoặc command-line arguments. Nếu task tự duyệt file system nhưng thứ tự không có ý nghĩa, hãy sắp xếp đầu vào hoặc xử lý ổn định; đừng để thứ tự tùy tiện ảnh hưởng output.

## 7. Quy trình kiểm chứng cache đúng theo cấu hình

Thực hiện thử nghiệm trên dự án có thể xóa output an toàn, ghi lại phiên bản Gradle, JDK, plugin và dependency khi so sánh:

1. **Liệt kê input/output thật:** xác định từng file, option, toolchain, biến môi trường và output. Chọn file hoặc SHA-256 để chứng minh kết quả đúng.
2. **Tạo baseline A:** build với profile A, mở artifact và kiểm tra nội dung đúng A. Lưu lại input đầy đủ, không chỉ log trạng thái task.
3. **Đổi một input có ý nghĩa:** ví dụ edition A→B, template, classpath API hoặc release target. Output phải được tạo/cấp đúng cho B, không mang dữ liệu A.
4. **Đổi một yếu tố vô can:** ví dụ chuyển checkout sang thư mục khác khi task không phụ thuộc đường dẫn tuyệt đối. Cache có thể tái sử dụng nếu metadata path normalization đúng; output vẫn phải giống hệt.
5. **Khôi phục output sạch:** xóa output ở workspace thử nghiệm rồi chạy cùng input với `--build-cache --info`; khi có entry hợp lệ, kiểm tra `FROM-CACHE` và so sánh nội dung file khôi phục với baseline.
6. **Kiểm thử A→B→A:** đảm bảo artifact của hai cấu hình không lẫn nhau, dù cache đã có kết quả cả hai.
7. **So sánh đối chứng:** tạo output với `--no-build-cache` và đối chiếu nội dung với bản khôi phục. Có thể dùng `--rerun-tasks` để ép chạy lại cho chẩn đoán; việc ép chạy tự nó không chứng minh cache key đúng.
8. **Thử môi trường khác:** trên CI/agent khác, kiểm tra toolchain, OS, đường dẫn checkout, locale, filesystem và dependency resolution khi chúng có thể ảnh hưởng output.

Lệnh quan sát thường dùng: `./gradlew generateBuildDescriptor --build-cache --info`. Log có thể hiển thị `UP-TO-DATE`, `FROM-CACHE` hoặc việc task thực thi; giải thích dựa trên trạng thái thật, không tự giả định máy đã có cache entry.

## 8. Chẩn đoán các triệu chứng

**Đổi flag nhưng output không đổi hoặc mang cấu hình cũ:** tìm code đọc `System.getenv`, `project.findProperty`, system property, file cấu hình và command line ngay trong action. Biến nguồn thật thành Gradle property/file input; kiểm tra trường hợp A→B→A. Với artifact từng được cache sai, cần loại bỏ entry lỗi trong môi trường thử nghiệm hoặc thay đổi khóa sau khi sửa hợp đồng input.

**Liên tục cache miss:** tìm input quá rộng, path tuyệt đối, file được cập nhật theo timestamp, generated version thay đổi không cần thiết, classpath/toolchain thay đổi, hoặc task chưa đủ điều kiện cache. Xem `--info` để phân biệt không cacheable, không tìm thấy entry và input đổi.

**Cache hit trên máy khác nhưng artifact lỗi:** xem có binary phụ thuộc hệ điều hành, đường dẫn JDK, hostname, file encoding hoặc môi trường ngoài chưa khai báo không. Cache liên máy chỉ an toàn nếu output tương thích giữa những môi trường được coi là tương đương.

**Bytecode đổi sau nâng JDK/compiler plugin:** kiểm tra Java toolchain, `options.release`, compiler args, annotation processors, version dependency. Không mô tả compiler “cùng nguồn” khi compilation chịu ảnh hưởng thêm toolchain và processors.

**Remote cache trả artifact đáng ngờ:** kiểm soát ai có quyền ghi. Chỉ cho nguồn build tin cậy đẩy artifact vào remote cache dùng chung; không cache secret, credential hoặc output được tạo từ dữ liệu không nên chia sẻ. Integrity của cache và tính đúng đắn của khai báo input đều cần thiết.

## 9. Checklist áp dụng trước khi đánh dấu task cacheable

- [ ] Tất cả nguồn ảnh hưởng output, kể cả công cụ/processor, env, config gián tiếp, được khai báo đúng kiểu.
- [ ] Có khai báo mọi output; các task không ghi đè chung thư mục output.
- [ ] Action không phụ thuộc thời gian, random, hostname, filesystem order hoặc network không có snapshot/version ổn định.
- [ ] Path sensitivity, classpath normalization, line ending, encoding phản ánh đúng ngữ nghĩa output.
- [ ] Thay đổi input có ý nghĩa tạo output mới chính xác; thay đổi input vô can không gây cache miss thừa.
- [ ] Đã thử build có cache, không cache, restore sau khi xóa output và đổi qua lại hai cấu hình A/B.
- [ ] Remote cache có chính sách tin cậy phù hợp, không xuất bản artifact chứa bí mật hoặc phụ thuộc máy.

**Điểm cần nhớ:** build cache chỉ an toàn khi khóa của nó đại diện đầy đủ cho **hợp đồng tạo artifact**. Thiếu input tạo cache hit sai, thừa input tạo cache miss thừa. Hãy chứng minh bằng cách đổi từng cấu hình và so sánh nội dung output thực tế, thay vì chỉ dựa vào trạng thái `FROM-CACHE`.
