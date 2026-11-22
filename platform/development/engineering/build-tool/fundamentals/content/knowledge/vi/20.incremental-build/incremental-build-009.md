# Cache mất hiệu lực, cache lỗi và trường hợp cần làm mới

Build tăng dần giúp tiết kiệm thời gian bằng cách bỏ qua công việc chưa cần chạy lại hoặc tái sử dụng kết quả đã tạo. Nhưng cache chỉ hữu ích khi build tool xác định đúng dữ liệu nào đã thay đổi và kết quả nào vẫn còn hợp lệ. Khi cache quá cũ, bị hỏng hoặc được tạo từ một hợp đồng input/output không đầy đủ, build có thể dùng kết quả sai, báo lỗi khó hiểu hoặc hoạt động khác nhau giữa máy phát triển và CI.

Khi gặp vấn đề liên quan cache, trước hết cần xác định **đang nói đến loại cache nào**. Build tool có thể giữ trạng thái của task, kết quả task, dependency đã tải, metadata repository, compiler state hoặc bản phân phối của chính build tool. Những lớp này có cơ chế làm mới khác nhau. Xóa toàn bộ cache thường tốn thời gian tải lại và không sửa được nguyên nhân gốc nếu task khai báo thiếu input hoặc dependency được publish sai.

## 1. Các loại cache và trạng thái thường gặp

Trong một dự án Java dùng Maven hoặc Gradle, từ cache có thể chỉ nhiều cơ chế khác nhau.

| Lớp lưu trữ | Nội dung | Ví dụ | Vấn đề thường gặp |
|---|---|---|---|
| Task up-to-date state | So sánh input/output của task trong build hiện tại | Gradle đánh dấu task UP-TO-DATE | Output bị thiếu hoặc input không được khai báo |
| Build cache | Kết quả task có thể tái sử dụng | Gradle local/remote build cache | Cache key sai, output cache cũ hoặc entry hỏng |
| Dependency cache | Artifact và metadata dependency đã resolve | JAR đã tải từ Maven Central hoặc repository nội bộ | Artifact cũ, metadata chưa cập nhật, file tải lỗi |
| Maven local repository | Artifact đã tải hoặc được cài bằng install | Thư mục .m2/repository | Snapshot cũ, file cục bộ sai hoặc artifact cài nhầm |
| Gradle dependency metadata cache | Thông tin module, version và kết quả resolve | Gradle user home caches | Version động hoặc changing module chưa được kiểm tra lại |
| Wrapper distribution cache | Bản Maven/Gradle được wrapper tải về | Gradle wrapper distributions | Bản tải không đầy đủ hoặc không tương thích |
| Daemon/process state | Trạng thái tiến trình build đang chạy | Gradle daemon | Process giữ trạng thái cũ hoặc môi trường khác dự kiến |

Không phải tất cả các mục trên đều là cache theo cùng một nghĩa. Ví dụ, Gradle đánh dấu task UP-TO-DATE dựa trên output trong workspace; build cache có thể khôi phục output từ một lần build khác; dependency cache lưu thư viện để resolve; daemon là tiến trình lâu dài. Chẩn đoán cần tách riêng chúng.

## 2. Phân biệt cache mất hiệu lực, cache cũ và cache bị hỏng

Ba trạng thái này có biểu hiện khác nhau.

### 2.1. Cache mất hiệu lực hợp lệ

Cache mất hiệu lực (invalidated) khi một input ảnh hưởng kết quả đã thay đổi hoặc output không còn tồn tại. Build tool nhận ra kết quả cũ không thể dùng và chạy lại task hoặc resolve dependency.

Ví dụ:

- sửa file Java;
- thay resource đầu vào;
- thay compiler option;
- thay version dependency;
- thay tham số cấu hình được khai báo là input;
- xóa output file của task;
- thay implementation hoặc classpath của task.

Đây là hành vi mong muốn. Không cần xóa cache chỉ vì build tool quyết định chạy lại task.

### 2.2. Cache cũ (stale)

Cache cũ xảy ra khi dữ liệu đã thay đổi ở nơi khác nhưng build tool chưa biết hoặc chưa kiểm tra lại. Ví dụ:

- một SNAPSHOT được publish lại dưới cùng tọa độ;
- một version động như 1.+ có version mới nhưng metadata chưa được làm mới;
- file cấu hình được đọc bởi task nhưng không khai báo là input;
- repository đã cập nhật artifact nhưng máy vẫn dùng metadata được cache theo update policy;
- một dependency nội bộ được ghi đè dưới cùng version release.

Cache cũ không nhất thiết bị hỏng về mặt file. Nó có thể chứa dữ liệu hoàn toàn đọc được nhưng không còn phản ánh trạng thái mà người dùng mong muốn.

### 2.3. Cache bị hỏng (corrupt)

Cache bị hỏng khi dữ liệu lưu trữ không còn đọc được hoặc không khớp định dạng/giá trị mong đợi. Nguyên nhân có thể là:

- tiến trình bị dừng giữa lúc ghi file;
- ổ đĩa đầy hoặc có lỗi I/O;
- file tải về bị cắt cụt;
- nhiều tiến trình cùng thao tác lên một vị trí không được hỗ trợ;
- phần mềm bảo mật hoặc đồng bộ file can thiệp;
- cache remote lưu trữ sai nội dung;
- artifact được thay thế nhưng metadata/checksum không còn khớp.

Biểu hiện có thể là lỗi giải nén ZIP/JAR, checksum mismatch, lỗi parse metadata, lỗi đọc file hoặc build chỉ hỏng trên một máy cụ thể.

### 2.4. Bảng nhận diện nhanh

| Triệu chứng | Khả năng cao | Hướng kiểm tra đầu tiên |
|---|---|---|
| Task chạy lại sau khi sửa source | Cache/task state bị invalidated hợp lệ | Kiểm tra input thay đổi |
| Task báo UP-TO-DATE dù output mong muốn đã đổi | Input chưa khai báo hoặc task model sai | Kiểm tra input/output của task |
| Task báo FROM-CACHE nhưng output sai | Cache key thiếu input hoặc cache entry sai | Tắt build cache một lần và kiểm tra khai báo task |
| Chỉ một dependency resolve ra version cũ | Dependency metadata/artifact cache | Kiểm tra tọa độ, version, repository và refresh policy |
| JAR tải về không mở được | Artifact download cache hoặc artifact trên repository bị lỗi | Kiểm tra checksum và tải lại đúng artifact |
| Build offline thất bại | Dependency chưa có trong cache | Kiểm tra chế độ offline và dependency cần thiết |
| Build lỗi trên một máy, thành công trên máy khác | Local cache, JDK, daemon hoặc môi trường khác nhau | So sánh wrapper, JDK, logs và cache layer |

## 3. Khi nào cache cần mất hiệu lực?

Cache chỉ an toàn khi build tool có thể xác định kết quả cũ được tạo từ cùng input. Một task nên chạy lại khi bất kỳ dữ liệu nào ảnh hưởng output thay đổi.

### 3.1. Thay đổi file input

Nếu task đọc file schema, template hoặc resource, sửa file đó phải làm task chạy lại. Với Gradle, file cần được khai báo bằng input file property hoặc file collection phù hợp.

Ví dụ khái niệm:

~~~kotlin
abstract class GenerateClient : DefaultTask() {
    @get:InputFile
    abstract val schemaFile: RegularFileProperty

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty
}
~~~

Khi nội dung hoặc thuộc tính path-sensitivity của schema thay đổi, Gradle có thể tính lại task state/cache key.

### 3.2. Thay đổi property hoặc option

Compiler version, target release, locale, tên package, cờ bật/tắt feature hoặc tham số generator đều có thể ảnh hưởng output. Chúng cần được khai báo như input nếu task phụ thuộc chúng.

### 3.3. Thay đổi implementation hoặc classpath

Thay code của task, plugin implementation hoặc classpath dùng để chạy task có thể làm kết quả thay đổi. Gradle tính task implementation/classpath trong quá trình kiểm tra up-to-date và cache key theo loại task.

### 3.4. Output bị xóa hoặc thay đổi

Nếu output file không còn tồn tại, task cần chạy lại. Nếu output bị sửa thủ công, Gradle có thể nhận ra output không khớp với trạng thái trước đó và chạy lại. Tuy nhiên, không nên chỉnh sửa trực tiếp file do task sở hữu.

### 3.5. Dependency graph thay đổi

Nếu version hoặc dependency bắc cầu thay đổi, compile/runtime classpath có thể thay đổi và task phụ thuộc classpath đó cần được thực hiện lại. Với version động hoặc snapshot, cần hiểu khi nào build tool kiểm tra repository để nhận metadata mới.

## 4. Cache sai do khai báo input không đầy đủ

Đây là nguyên nhân quan trọng của kết quả stale trong custom task. Build tool chỉ có thể tính cache key từ những đầu vào mà task mô tả.

Ví dụ task không tốt:

~~~kotlin
tasks.register("generateBuildInfo") {
    doLast {
        val environmentName = System.getenv("DEPLOY_ENV") ?: "local"
        file("build/generated/environment.txt").writeText(environmentName)
    }
}
~~~

Task đọc biến môi trường DEPLOY_ENV nhưng không khai báo biến đó là input. Nếu giá trị đổi từ staging sang production, build tool có thể không nhận ra thay đổi và giữ output cũ.

Một task type tốt hơn mô hình hóa giá trị này:

~~~kotlin
abstract class GenerateBuildInfo : DefaultTask() {
    @get:Input
    abstract val environmentName: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.writeText(environmentName.get())
    }
}
~~~

Sau đó truyền giá trị qua cấu hình build rõ ràng. Với giá trị lấy từ biến môi trường, đọc nó ở configuration boundary và đưa vào property; tránh để task action đọc trạng thái ngoài hợp đồng.

Tương tự, nếu task đọc file ngoài project, system property, thời gian hiện tại, dữ liệu mạng hoặc version generator mà không khai báo, cache có thể trả kết quả không còn đúng.

## 5. Gradle: task UP-TO-DATE và build cache

Gradle có ít nhất hai cơ chế thường bị nhầm:

1. **Up-to-date checking:** kiểm tra output trong workspace hiện tại có còn hợp lệ so với input không.
2. **Build cache:** nếu task cần chạy nhưng có cache key phù hợp, Gradle có thể lấy output đã lưu từ local hoặc remote build cache.

Trạng thái thường thấy:

| Trạng thái | Ý nghĩa |
|---|---|
| SUCCESS | Task đã thực thi thành công |
| UP-TO-DATE | Input/output không thay đổi so với lần trước trong workspace |
| FROM-CACHE | Output được khôi phục từ build cache |
| NO-SOURCE | Không có source/input phù hợp để xử lý |
| SKIPPED | Task bị bỏ qua do điều kiện hoặc cấu hình |
| FAILED | Task thực thi và gặp lỗi |

Task UP-TO-DATE không có nghĩa output được lấy từ remote cache. Task FROM-CACHE cho biết Gradle tìm thấy kết quả cache phù hợp và khôi phục output.

### 5.1. Bật hoặc tắt build cache

Có thể bật build cache qua command line:

~~~bash
./gradlew build --build-cache
~~~

Hoặc cấu hình trong gradle.properties:

~~~properties
org.gradle.caching=true
~~~

Tắt cache cho một lần chạy:

~~~bash
./gradlew build --no-build-cache
~~~

Tắt cache không xóa dependency cache. Nó yêu cầu build không sử dụng build cache để khôi phục kết quả task. Task up-to-date trong workspace vẫn là một cơ chế riêng; nếu muốn buộc task thực thi, cần cân nhắc thêm --rerun-tasks.

### 5.2. Buộc task chạy lại

~~~bash
./gradlew build --rerun-tasks --no-build-cache
~~~

Lệnh này hữu ích để chẩn đoán khi nghi ngờ output task cũ hoặc build cache trả kết quả không đúng. --rerun-tasks bỏ qua up-to-date checks; --no-build-cache ngăn khôi phục task output từ build cache trong lần chạy đó.

Không nên dùng hai cờ này cho mọi build thường ngày vì chúng làm mất lợi ích incremental/cache. Chúng là công cụ chẩn đoán để so sánh hành vi.

### 5.3. Clean có xóa build cache không?

~~~bash
./gradlew clean build
~~~

Task clean xóa output build trong project, thường là thư mục build. Nó không xóa toàn bộ Gradle build cache hoặc dependency cache trong Gradle user home. Sau clean, task có thể:

- thực thi lại từ đầu;
- khôi phục output từ build cache nếu cache được bật và có entry phù hợp.

Vì vậy, clean build chưa chắc có nghĩa mọi task đã được thực thi lại. Nếu muốn kiểm tra thực thi không dùng task cache, có thể chạy:

~~~bash
./gradlew clean build --no-build-cache
~~~

Nếu cần buộc mọi task thực thi, thêm --rerun-tasks. Hãy dùng mức can thiệp nhỏ nhất để kiểm tra đúng giả thuyết.

## 6. Gradle: làm mới dependency cache

Dependency cache chứa artifact đã tải và metadata resolve. Khi nghi ngờ dependency hoặc metadata cũ, Gradle cung cấp tùy chọn --refresh-dependencies.

~~~bash
./gradlew build --refresh-dependencies
~~~

Tùy chọn này yêu cầu Gradle làm mới trạng thái dependency resolution và kiểm tra repository theo cơ chế của Gradle. Nó không đơn giản xóa toàn bộ cache rồi tải mọi file lại. Nếu artifact được xác định vẫn không thay đổi, Gradle có thể tái sử dụng nội dung đã cache.

### 6.1. Khi nào nên dùng?

- version động như 1.+ cần được kiểm tra lại;
- changing module hoặc SNAPSHOT có thể đã được publish lại;
- metadata repository có thể đã cập nhật;
- dependency vừa được publish nhưng máy chưa resolve được bản mới;
- nghi ngờ metadata dependency cache không phản ánh trạng thái repository.

### 6.2. Khi nào không giải quyết được?

--refresh-dependencies không sửa:

- tọa độ dependency sai;
- repository URL sai hoặc không truy cập được;
- credentials thiếu hoặc hết hạn;
- artifact chưa được publish;
- version release bất biến trỏ đến nội dung sai trên repository;
- task custom khai báo thiếu input;
- output task bị tạo sai do bug trong implementation.

Nếu release version bị ghi đè dưới cùng tọa độ, cần xử lý chính sách repository và versioning. Không nên dựa vào refresh để biến một release mutable thành dependency đáng tin cậy.

### 6.3. Xem dependency nào được chọn

Liệt kê dependency của runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Xem vì sao một version được chọn:

~~~bash
./gradlew dependencyInsight --dependency catalog-core --configuration runtimeClasspath
~~~

Hai lệnh này giúp phân biệt build tool đã resolve version nào với version mà người viết build mong đợi.

## 7. Gradle: chế độ offline và cache thiếu dữ liệu

Gradle có thể chạy offline:

~~~bash
./gradlew build --offline
~~~

Ở chế độ này, Gradle không truy cập mạng để tải dependency. Build chỉ thành công nếu các artifact/metadata cần thiết đã có trong cache và có thể được resolve theo trạng thái local.

Nếu build offline báo thiếu dependency, điều đó không nhất thiết là cache bị hỏng. Có thể dependency chưa từng được tải trên máy hoặc configuration mới chưa được resolve.

Khi cần tải dependency mới, chạy lại ở chế độ online và kiểm tra repository/credentials. Không dùng offline mode để kiểm tra xem artifact mới đã được publish hay chưa.

## 8. Gradle: remote build cache

Remote build cache cho phép nhiều workspace hoặc CI runner dùng chung output của task có cache key phù hợp. Nó có thể tiết kiệm đáng kể thời gian trong build lớn, nhưng cần bảo đảm cache key đầy đủ và cache server đáng tin cậy.

Một cấu hình remote cache có thể được đặt trong settings.gradle.kts:

~~~kotlin
buildCache {
    local {
        isEnabled = true
    }
    remote<HttpBuildCache> {
        url = uri("https://build-cache.example.com/cache/")
        isEnabled = true
        isPush = false
    }
}
~~~

Ví dụ trên minh họa endpoint; cấu hình credentials và quyền truy cập cần theo hệ thống thực tế. Thường CI đáng tin cậy có quyền ghi cache, còn developer hoặc job kiểm tra chỉ đọc. Cách phân quyền này giảm nguy cơ một build không tin cậy ghi output sai vào cache chung.

### 8.1. Cache key phải đại diện cho mọi input

Nếu task tạo JAR dựa trên:

- source files;
- resource files;
- compiler arguments;
- JDK/compiler;
- dependency classpath;
- project version;
- build-time properties;

thì các yếu tố ảnh hưởng kết quả phải được tính đến trong task inputs hoặc trong cấu hình toolchain/plugin.

Nếu DEPLOY_ENV thay đổi output nhưng không nằm trong cache key, một runner có thể lấy output được tạo cho môi trường khác.

### 8.2. Remote cache không phải nguồn sự thật cho dependency

Build cache lưu output của task. Dependency repository lưu artifact dependency theo tọa độ/version. Hai hệ thống phục vụ mục đích khác nhau.

Tắt build cache không làm mới dependency. Làm mới dependency không xóa task output cache. Khi chẩn đoán, chọn đúng cờ cho đúng lớp.

### 8.3. Cache poisoning và quyền ghi

Remote cache có thể trở thành nguồn cung cấp output cho nhiều build. Nếu một job không đáng tin cậy có quyền ghi, nó có thể đưa output sai vào cache dùng chung. Cần:

- giới hạn quyền ghi cache cho builder đáng tin cậy;
- tách cache theo trust boundary nếu cần;
- tránh lưu output chứa secret;
- bảo vệ endpoint và credentials;
- ghi nhận cache source trong log khi điều tra bất thường.

Không nên dùng cache remote như một nơi lưu artifact phát hành lâu dài hoặc thay thế repository package.

## 9. Maven: local repository và dependency cache

Maven thường lưu artifact tải về và artifact được cài bằng goal install trong local repository, mặc định thường là:

~~~text
~/.m2/repository
~~~

Trên Windows, thư mục tương ứng thường nằm trong user profile dưới .m2/repository. Có thể thay đổi vị trí bằng cấu hình Maven.

Local repository có hai vai trò liên quan:

- lưu dependency/plugin tải từ remote repository để dùng lại;
- lưu artifact do project cài bằng mvn install.

Nó không phải remote repository chia sẻ của nhóm. Một artifact chỉ có trên máy developer có thể không tồn tại trên CI.

### 9.1. Maven update policy

Maven kiểm soát thời điểm kiểm tra cập nhật repository qua update policy. Với snapshot, policy có thể là:

- always;
- daily;
- interval:X;
- never.

Policy mặc định thường kiểm tra snapshot theo chu kỳ daily. Vì vậy, snapshot mới được publish có thể chưa được tải ngay trong một lần build sau nếu metadata vẫn nằm trong khoảng cache.

Release version được kỳ vọng bất biến. Nếu một release version đã publish bị thay nội dung, đó là vấn đề repository/versioning, không nên coi refresh là giải pháp lâu dài.

### 9.2. Buộc Maven kiểm tra snapshot mới

~~~bash
./mvnw -U verify
~~~

Tùy chọn -U buộc Maven kiểm tra các release bị thiếu và snapshot đã cập nhật trên remote repositories. Nó hữu ích khi cần lấy snapshot mới hoặc metadata mới theo chính sách repository.

Không có nghĩa Maven phải tải lại mọi release dependency ở mỗi lần chạy. Nếu tọa độ release đã resolve và artifact được xem là bất biến, Maven vẫn có thể dùng local repository.

### 9.3. Maven offline mode

~~~bash
./mvnw -o verify
~~~

Offline mode ngăn Maven truy cập remote repository. Build chỉ thành công nếu mọi plugin và dependency cần thiết đã có sẵn trong local repository.

Nếu build offline thất bại với artifact chưa được resolve, hãy chạy online và kiểm tra repository. Không nên xóa local repository khi mục tiêu chỉ là tải một dependency còn thiếu.

## 10. Maven: làm mới hoặc xóa có chọn lọc artifact cục bộ

Nếu nghi ngờ một artifact cụ thể trong local repository bị hỏng, ưu tiên xử lý đúng artifact đó thay vì xóa toàn bộ .m2.

### 10.1. Dùng Maven Dependency Plugin

Có thể dùng goal purge-local-repository của Maven Dependency Plugin để loại bỏ dependency được chọn khỏi local repository và resolve lại:

~~~bash
./mvnw dependency:purge-local-repository -DmanualInclude=com.example:catalog-core -DreResolve=true
~~~

Tùy version plugin và tham số được cấu hình, có thể cần chỉ định version/plugin version hoặc phạm vi purge cụ thể. Kiểm tra help của goal nếu cần:

~~~bash
./mvnw dependency:help -Ddetail=true -Dgoal=purge-local-repository
~~~

Không dùng purge toàn bộ dependency nếu chỉ một artifact gặp lỗi. Việc xóa nhiều dependency sẽ làm build tiếp theo tải lại lượng lớn dữ liệu.

### 10.2. Xóa thư mục version cụ thể khi đã xác định

Một cách khác là dừng build đang chạy và xóa đúng thư mục version của artifact bị hỏng trong local repository, sau đó chạy Maven online để tải lại.

Trước khi xóa:

1. xác định chính xác groupId/artifactId/version;
2. kiểm tra đường dẫn tương ứng trong local repository;
3. bảo đảm không có build khác đang sử dụng file;
4. chỉ xóa thư mục version bị ảnh hưởng;
5. chạy lại lệnh resolve/build và xem log tải artifact.

Không xóa toàn bộ thư mục .m2/repository như phản xạ đầu tiên. Nó chứa cả dependency, plugin và metadata có thể mất nhiều thời gian tải lại.

### 10.3. Maven clean không xóa local repository

~~~bash
./mvnw clean
~~~

Goal clean xóa output của project, thường là target. Nó không xóa dependency đã tải trong local repository. Nếu vấn đề là JAR dependency cũ, clean không làm mới JAR đó.

## 11. Snapshot và changing dependency cần chính sách riêng

Snapshot được thiết kế cho phát triển và có thể được cập nhật dưới cùng version có hậu tố SNAPSHOT. Vì thế, cache metadata và update policy ảnh hưởng trực tiếp đến thời điểm người dùng nhìn thấy bản mới.

### 11.1. Maven SNAPSHOT

Ví dụ:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>catalog-core</artifactId>
    <version>1.5.0-SNAPSHOT</version>
</dependency>
~~~

Khi cần lấy snapshot mới:

~~~bash
./mvnw -U verify
~~~

Nếu vẫn nhận nội dung cũ, kiểm tra:

- snapshot có thực sự được publish thành công không;
- project đang resolve từ repository nào;
- repository có cho phép snapshots không;
- update policy có cho kiểm tra lại không;
- local metadata có bị giữ trong thời gian policy không;
- có mirror hoặc repository manager proxy tới endpoint khác không.

### 11.2. Gradle changing module

Gradle có thể đánh dấu dependency snapshot/changing:

~~~kotlin
dependencies {
    implementation("com.example:catalog-core:1.5.0-SNAPSHOT") {
        isChanging = true
    }
}
~~~

Có thể cấu hình thời gian cache changing module:

~~~kotlin
configurations.all {
    resolutionStrategy.cacheChangingModulesFor(0, "seconds")
}
~~~

Thiết lập zero seconds hữu ích trong một số tình huống phát triển cần kiểm tra lại thường xuyên, nhưng làm tăng truy cập repository và có thể làm build chậm. Không nên áp dụng toàn cục trong mọi môi trường mà không cân nhắc.

### 11.3. Không dùng snapshot làm release contract

Snapshot phù hợp để tích hợp các thay đổi chưa phát hành. Release build nên dùng version cụ thể, bất biến và có thể xác minh. Nếu cần một consumer kiểm thử snapshot mới, hãy ghi rõ version, repository và thời điểm resolve để người khác tái hiện.

## 12. Phân biệt làm mới dependency với chạy lại task

Các lệnh dưới đây tác động đến những lớp khác nhau:

| Lệnh | Tác động chính | Không làm gì |
|---|---|---|
| Gradle clean | Xóa output build trong project | Không xóa toàn bộ dependency cache |
| Gradle --rerun-tasks | Bỏ qua up-to-date checks và yêu cầu task thực thi | Không tự refresh dependency metadata |
| Gradle --no-build-cache | Không khôi phục task output từ build cache | Không xóa dependency cache |
| Gradle --refresh-dependencies | Làm mới dependency resolution/check repository | Không sửa task khai báo thiếu input |
| Gradle --offline | Không truy cập mạng | Không tải dependency mới |
| Maven clean | Xóa target/output của project | Không xóa local repository |
| Maven -U | Kiểm tra release còn thiếu và snapshot cập nhật trên remote | Không xóa toàn bộ local repository |
| Maven -o | Chạy offline | Không tải artifact mới |
| Maven purge-local-repository | Xóa dependency cục bộ theo phạm vi goal được cấu hình | Không sửa lỗi repository hoặc POM sai |

Đừng dùng một lệnh refresh cho mọi loại vấn đề. Hãy xác định task output hay dependency artifact đang stale.

## 13. Quy trình chẩn đoán theo từng lớp

Khi build cho kết quả cũ hoặc báo lỗi liên quan cache, có thể đi theo quy trình sau.

### Bước 1: Ghi lại triệu chứng

Ghi lại:

- lệnh build chính xác;
- task/phase thất bại;
- trạng thái task như UP-TO-DATE, FROM-CACHE hoặc FAILED;
- dependency tọa độ/version liên quan;
- môi trường, wrapper và JDK;
- build có thành công trên máy khác hoặc CI không.

Không xóa cache trước khi thu thập thông tin. Nếu xóa trước, bằng chứng về trạng thái ban đầu có thể mất.

### Bước 2: Xác định lớp cache

Hỏi:

- Output task trong workspace có cũ không?
- Gradle báo FROM-CACHE hay UP-TO-DATE?
- Dependency resolve ra version nào?
- Artifact tải về có đọc được và checksum đúng không?
- Chỉ một máy lỗi hay mọi môi trường đều lỗi?
- Lỗi có xuất hiện ở offline mode không?

### Bước 3: Kiểm tra input và dependency graph

Với Gradle, xem dependency report và task log. Với Maven, xem dependency tree, effective POM và log repository. Kiểm tra version được chọn, repository URL và scope/configuration.

Nếu task custom dùng input chưa khai báo, sửa hợp đồng task trước khi làm mới cache. Nếu không, lần sau cache vẫn có thể trả kết quả sai.

### Bước 4: Thử bypass đúng một lớp

Ví dụ:

- nghi task output cache: chạy Gradle với --rerun-tasks --no-build-cache;
- nghi dependency metadata: chạy Gradle với --refresh-dependencies;
- nghi Maven snapshot: chạy Maven với -U;
- nghi artifact local bị hỏng: purge đúng tọa độ/version hoặc xóa đúng thư mục version sau khi xác định;
- nghi workspace output cũ: chạy clean rồi build lại.

Thay đổi một yếu tố mỗi lần để biết hành động nào làm kết quả thay đổi.

### Bước 5: So sánh kết quả

Nếu build thành công sau khi bypass cache:

- kiểm tra artifact mới có khác nội dung không;
- xác định cache layer nào đã ảnh hưởng;
- kiểm tra tại sao build tool nghĩ kết quả cũ còn hợp lệ;
- xem có input bị bỏ sót hoặc repository metadata không được cập nhật không.

Nếu build vẫn lỗi, nguyên nhân có thể không nằm ở cache. Kiểm tra source, cấu hình, dependency, quyền truy cập, repository hoặc plugin.

### Bước 6: Sửa nguyên nhân gốc

Ví dụ:

- khai báo input property/file đầy đủ;
- dùng version dependency bất biến;
- sửa repository URL hoặc credentials;
- sửa plugin configuration;
- loại bỏ hai task cùng ghi một output;
- sửa artifact publish sai;
- nâng cấp plugin nếu đã xác định lỗi cache của phiên bản đó.

### Bước 7: Kiểm tra lại trong workspace sạch

Chạy build từ trạng thái sạch, quan sát task state và xác nhận artifact đầu ra đúng. Nếu yêu cầu tái lập, build độc lập ở workspace khác và so sánh checksum.

## 14. Các tình huống thực tế

### 14.1. Gradle task báo UP-TO-DATE nhưng output cần thay đổi

Khả năng: task đọc biến môi trường hoặc file ngoài mà không khai báo input.

Cách xử lý:

1. chạy --rerun-tasks để xác nhận task action tạo output mới;
2. kiểm tra output khác với kết quả cũ không;
3. đưa biến/file đó thành task input;
4. chạy lại bình thường để kiểm tra Gradle nhận ra thay đổi.

Nếu chỉ dùng --rerun-tasks mỗi lần, vấn đề khai báo input vẫn tồn tại.

### 14.2. Gradle task báo FROM-CACHE nhưng kết quả không đúng

Khả năng:

- cache key thiếu input;
- task implementation không deterministic;
- remote cache được ghi bởi builder không đáng tin cậy;
- một task khác ghi đè output sau khi khôi phục.

Cách xử lý:

1. chạy một lần với --rerun-tasks --no-build-cache;
2. so sánh output;
3. kiểm tra task annotations và input/output;
4. kiểm tra remote cache permissions và build logs;
5. sửa task/cache policy trước khi bật lại.

Không chỉ xóa local cache nếu remote cache vẫn chứa entry sai và tiếp tục cung cấp nó.

### 14.3. Gradle resolve SNAPSHOT cũ

Khả năng: changing module metadata đang được cache theo thời gian.

Cách xử lý:

1. xác nhận snapshot mới đã publish;
2. xác nhận repository đúng;
3. đánh dấu dependency là changing nếu phù hợp;
4. chạy --refresh-dependencies;
5. kiểm tra runtime/compile dependency insight để xác nhận version/metadata được chọn.

### 14.4. Maven vẫn dùng SNAPSHOT cũ

Khả năng: update policy chưa đến thời điểm kiểm tra lại hoặc repository đang trả metadata cũ.

Cách xử lý:

1. xác nhận snapshot được publish;
2. kiểm tra snapshot repository và mirror;
3. chạy ./mvnw -U verify;
4. xem log resolve và metadata trong local repository;
5. chỉ purge tọa độ cụ thể nếu đã xác định local entry bị lỗi.

### 14.5. Build lỗi khi giải nén dependency JAR

Khả năng: file tải về bị cắt cụt hoặc cache entry bị hỏng; cũng có thể artifact trên remote repository đã publish sai.

Cách xử lý:

1. ghi nhận tọa độ và version;
2. xác minh checksum từ nguồn tin cậy nếu có;
3. kiểm tra artifact trên remote repository;
4. làm mới hoặc purge đúng artifact cục bộ;
5. tải lại và thử mở JAR;
6. nếu file remote cũng hỏng, yêu cầu publish bản sửa bằng version mới theo chính sách repository.

### 14.6. Chỉ CI lỗi, máy developer thành công

Không kết luận ngay cache CI bị hỏng. So sánh:

- JDK/toolchain và wrapper;
- biến môi trường;
- repository/mirror và credentials;
- cache remote có được bật không;
- task state và cache hit;
- file hệ thống, quyền và OS;
- dependency lock/verification state.

Nếu build chỉ lỗi khi dùng remote cache, thử chạy job có --no-build-cache và so sánh. Nếu vẫn lỗi, nguyên nhân có thể ở môi trường CI hoặc dependency chứ không phải build cache.

## 15. Khi nào nên làm mới cache?

Làm mới khi có một giả thuyết cụ thể và thao tác phù hợp với lớp dữ liệu.

| Tình huống | Hành động phù hợp |
|---|---|
| Source thay đổi và task chạy lại | Không cần refresh; đây là invalidation bình thường |
| Task output có vẻ cũ dù input đã thay đổi | Kiểm tra input declaration; tạm bypass up-to-date/build cache |
| Gradle build cache trả output sai | Bypass cache, kiểm tra key/task và remote cache producer |
| Gradle cần kiểm tra dependency snapshot/version động | --refresh-dependencies |
| Maven cần cập nhật snapshot | -U |
| Maven/Gradle offline báo thiếu dependency | Chạy online và resolve dependency cần thiết |
| Một JAR local bị hỏng | Xóa/purge đúng artifact version rồi tải lại |
| Maven target output cũ | mvn clean |
| Gradle build output cũ | gradle clean |
| Daemon giữ trạng thái bất thường | Thử dừng daemon rồi chạy lại |
| Repository trả artifact sai | Sửa/publish lại theo version mới; refresh local không đủ |

Không nên làm mới cache chỉ vì build chậm hoặc task được đánh dấu UP-TO-DATE. Cache hit và incremental skip là hành vi mong muốn khi input/output hợp lệ.

## 16. Khi nào không nên xóa toàn bộ cache?

Xóa toàn bộ cache có thể làm build tiếp theo tải lại hàng trăm hoặc hàng nghìn dependency, plugin và distribution. Nó cũng có thể che mất nguyên nhân gốc mà không sửa được cấu hình.

Tránh xóa toàn bộ:

- Gradle user home caches;
- Maven local repository;
- remote build cache dùng chung;
- wrapper distribution cache;
- cache của mọi project trên máy.

Chỉ cân nhắc thao tác rộng khi:

- đã xác định cache store bị hỏng trên diện rộng;
- lỗi đọc/ghi ảnh hưởng nhiều entry;
- công cụ hoặc vendor hướng dẫn rõ thao tác đó cho một lỗi đã biết;
- có thể tải lại dữ liệu và chấp nhận thời gian/network cost;
- đã dừng build process đang sử dụng cache.

Ngay cả khi cần xóa, ưu tiên khoanh vùng theo project, module, version hoặc cache store cụ thể. Không xóa cache remote dùng chung chỉ vì một workspace có vấn đề.

## 17. Daemon và wrapper không giống dependency cache

### 17.1. Gradle daemon

Gradle daemon là tiến trình lâu dài giúp giảm chi phí khởi động build. Nó giữ trạng thái tiến trình và có thể dùng JVM/environment riêng. Khi nghi ngờ daemon đang giữ trạng thái bất thường, có thể dừng:

~~~bash
./gradlew --stop
~~~

Sau đó chạy lại build. Lệnh này dừng Gradle daemons tương ứng, không xóa dependency cache hoặc build cache.

Nếu lỗi tiếp tục xảy ra sau khi dừng daemon, hãy kiểm tra task, dependency và môi trường thay vì lặp lại thao tác stop.

### 17.2. Wrapper distribution

Maven/Gradle Wrapper tải bản phân phối build tool vào cache riêng. Nếu bản tải bị hỏng hoặc không đúng version, wrapper có thể không khởi động được. Đây là vấn đề wrapper distribution, không phải dependency JAR của ứng dụng.

Kiểm tra wrapper configuration, URL phân phối, checksum nếu được cấu hình và quyền truy cập mạng. Chỉ làm mới bản phân phối cụ thể khi đã xác định nó bị lỗi.

### 17.3. Gradle daemon JVM và toolchain JVM

JDK dùng để chạy Gradle daemon có thể khác JDK toolchain dùng để biên dịch. Khi so sánh build, ghi nhận cả hai. Thay JAVA_HOME có thể ảnh hưởng daemon mới nhưng không nhất thiết thay toolchain được khai báo rõ trong build.

## 18. Cache và bảo mật

Cache có thể chứa artifact nội bộ, file generated, metadata hoặc kết quả task. Khi dùng remote cache, cần xem nó là một phần của hạ tầng build có quyền truy cập và ranh giới tin cậy.

Các nguyên tắc:

- chỉ builder đáng tin cậy được ghi vào cache dùng chung;
- phân quyền đọc/ghi theo nhóm và pipeline;
- không cache output có secret hoặc dữ liệu nhạy cảm;
- bảo vệ endpoint, token và transport;
- không coi cache là nơi lưu artifact release chính thức;
- kiểm tra nguồn cache khi output bất thường;
- giữ provenance để biết output được tạo từ build nào.

Nếu output chứa credential do resource filtering, remote build cache có thể lưu chính file đó. Hãy loại secret khỏi artifact/build output thay vì chỉ hạn chế người đọc cache.

## 19. Ma trận lệnh làm mới cho Maven và Gradle

| Mục tiêu | Gradle | Maven |
|---|---|---|
| Xóa output của project | ./gradlew clean | ./mvnw clean |
| Buộc task chạy lại | ./gradlew build --rerun-tasks | Không có cờ tương đương tổng quát cho mọi plugin; dùng clean hoặc gọi goal phù hợp |
| Không dùng build cache | ./gradlew build --no-build-cache | Maven core không có build cache task output tương đương mặc định |
| Làm mới dependency resolution | ./gradlew build --refresh-dependencies | ./mvnw -U verify, đặc biệt với snapshot/metadata |
| Chạy offline | ./gradlew build --offline | ./mvnw -o verify |
| Xem dependency graph | ./gradlew dependencies --configuration runtimeClasspath | ./mvnw dependency:tree |
| Xem lý do chọn version | ./gradlew dependencyInsight ... | dependency:tree, effective POM và dependency plugin phù hợp |
| Dừng daemon | ./gradlew --stop | Maven thường không có daemon mặc định trong cách chạy wrapper thông thường |
| Xóa dependency cục bộ có chọn lọc | Làm mới resolution hoặc xử lý đúng cache entry theo hướng dẫn Gradle | dependency:purge-local-repository hoặc xóa đúng tọa độ/version |

Maven không có cơ chế task output build cache tích hợp mặc định tương đương Gradle Build Cache. Maven có thể dùng incremental behavior của plugin, local repository và các giải pháp cache ngoài, nhưng cần phân biệt chúng khi chẩn đoán.

## 20. Checklist xử lý sự cố cache

Khi gặp cache issue, hãy tự hỏi:

1. Lỗi xuất hiện ở task nào hoặc lúc resolve dependency nào?
2. Task đang UP-TO-DATE, FROM-CACHE hay thực sự FAILED?
3. Dependency version nào đã được chọn?
4. Input nào thay đổi kể từ lần build tốt gần nhất?
5. Task có đọc file, environment variable hoặc network data chưa khai báo không?
6. Artifact local có đọc được và checksum có đúng không?
7. Repository có chứa version/metadata mới chưa?
8. Build đang ở offline mode không?
9. Máy lỗi có khác JDK, wrapper, OS hoặc credentials không?
10. Bypass đúng lớp cache có làm lỗi biến mất không?
11. Remote cache có thể chứa entry sai hoặc được ghi bởi builder không tin cậy không?
12. Đã sửa nguyên nhân gốc hay chỉ ép build chạy lại?

Một quy trình tốt giữ lại log trước khi làm mới, chỉ tác động lớp cache liên quan, rồi xác nhận kết quả sau khi sửa.

## 21. Bài tập thực hành

### Bài 1 — Quan sát Gradle UP-TO-DATE

Tạo một project Gradle Java, chạy build hai lần. Quan sát task nào được đánh dấu UP-TO-DATE. Sửa một file Java và chạy lại; ghi nhận task nào cần thực hiện lại.

### Bài 2 — Phân biệt UP-TO-DATE và FROM-CACHE

Bật Gradle build cache, build project, sau đó xóa output project bằng clean và build lại. Quan sát task nào có thể được khôi phục FROM-CACHE. Chạy lại với --no-build-cache để so sánh.

### Bài 3 — Mô phỏng input bị khai báo thiếu

Tạo task đọc một property ngoài nhưng không khai báo input. Chạy task với giá trị A, đổi sang B rồi chạy lại. Quan sát trạng thái task và output. Sau đó khai báo property là @Input và kiểm tra lại.

### Bài 4 — Refresh dependency Gradle

Trong môi trường thử nghiệm, dùng một dependency snapshot/changing module. Publish bản cập nhật theo quy trình thử nghiệm, quan sát cache trước và sau --refresh-dependencies. Dùng dependencyInsight để xác nhận version/module được resolve.

### Bài 5 — Refresh snapshot Maven

Tạo dependency SNAPSHOT trong repository thử nghiệm. Resolve một lần, publish bản mới rồi chạy Maven bình thường và với -U. Ghi lại khác biệt về thời điểm cập nhật.

### Bài 6 — Phân biệt clean và purge dependency

Chạy Maven clean hoặc Gradle clean, sau đó build lại trong chế độ offline. Quan sát dependency vẫn có thể được dùng từ local cache. Sau đó chỉ purge một dependency thử nghiệm và xem build online tải lại artifact đó.

### Bài 7 — Phân tích artifact cache bị lỗi

Trong môi trường thử nghiệm riêng, xác định một artifact local có checksum không khớp nguồn tin cậy. Purge đúng tọa độ/version, resolve lại và xác nhận file mới có thể mở/đọc. Không sửa cache của dự án đang sử dụng.

### Bài 8 — Kiểm tra remote build cache trust

Vẽ sơ đồ các builder có quyền đọc/ghi remote cache. Xác định job nào có thể ghi output được các build phát hành tin cậy sử dụng. Đề xuất ranh giới quyền ghi và cách ghi nhận cache source.

## 22. Câu hỏi tự kiểm tra

1. Task UP-TO-DATE khác task FROM-CACHE như thế nào?
2. Cache invalidation hợp lệ xảy ra khi nào?
3. Cache stale khác cache corrupt ở điểm nào?
4. Vì sao task custom khai báo thiếu input có thể trả output cũ?
5. --rerun-tasks khác --no-build-cache như thế nào?
6. Gradle clean có xóa dependency cache không?
7. --refresh-dependencies làm gì và không làm gì?
8. Khi nào nên dùng --offline?
9. Maven -U có tác dụng gì với snapshot và release bị thiếu?
10. Maven clean có xóa local repository không?
11. Vì sao không nên xóa toàn bộ ~/.m2/repository hoặc Gradle user home để xử lý mọi lỗi?
12. Làm thế nào xử lý một JAR local bị hỏng có chọn lọc?
13. Vì sao release version bị ghi đè không thể được giải quyết chỉ bằng refresh?
14. Remote build cache cần kiểm soát quyền ghi như thế nào?
15. Làm thế nào phân biệt lỗi dependency cache với lỗi task output cache?

Khi phân biệt được task state, build cache và dependency cache, bạn có thể chọn đúng thao tác làm mới thay vì xóa dữ liệu hàng loạt. Quan trọng hơn, hãy sửa hợp đồng input/output, versioning hoặc repository policy gây ra cache sai. Khi nguyên nhân được xử lý, build tăng dần sẽ vừa nhanh vừa đáng tin cậy.
