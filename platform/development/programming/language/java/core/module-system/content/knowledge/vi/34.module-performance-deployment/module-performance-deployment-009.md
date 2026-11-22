# Reproducible module image và cache build

## 1. Reproducible build là gì?

Một build được xem là reproducible khi cùng một source revision và cùng tập hợp input đã khai báo tạo ra output tương đương theo tiêu chí đã chọn. Với artifact có thể đóng gói, mục tiêu mạnh nhất là tạo ra cùng nội dung byte-for-byte khi build lại trong môi trường được kiểm soát.

Đối với Java Platform Module System (JPMS), reproducibility cần bao phủ cả module JAR và runtime image được tạo bằng \`jlink\`. Kết quả phụ thuộc vào nhiều yếu tố:

- Source code, resource, \`module-info.java\` và generated source.
- Phiên bản JDK, vendor, compiler và công cụ \`jlink\`.
- Phiên bản Gradle/Maven, build plugins và dependency artifacts.
- Module path, dependency graph, service provider và các tùy chọn linker.
- Hệ điều hành, kiến trúc CPU, thư viện native và môi trường build.
- Timestamp, thứ tự file, locale, timezone và các biến môi trường được dùng trong quá trình build.

Nếu một trong các input này thay đổi mà build không ghi nhận, hai lần build có thể cho ra image khác nhau dù source revision giống nhau. Khi đó, cache có thể trả lại output cũ hoặc CI tạo ra artifact khác với máy developer.

**Reproducible** không chỉ có nghĩa là build chạy thành công hai lần. Cần xác định tiêu chí so sánh: cùng dependency graph, cùng module list, cùng nội dung class/resource, cùng manifest hash hay cùng toàn bộ bytes của gói phát hành.

## 2. Phân biệt các loại cache của Gradle

Gradle có nhiều cơ chế cache với mục đích khác nhau. Không nên gọi chung tất cả là build cache.

| Cơ chế | Nội dung được lưu | Tác dụng |
| --- | --- | --- |
| Dependency cache | Metadata và artifact dependency đã tải | Tránh tải lại dependency từ repository. |
| Build cache | Output của task dựa trên input và task implementation | Có thể khôi phục output của task đã chạy trước đó. |
| Configuration cache | Kết quả cấu hình build và task graph | Giảm thời gian cấu hình ở lần chạy tiếp theo. |
| Incremental build | Trạng thái input/output của task trong workspace | Bỏ qua task khi input/output chưa thay đổi. |

### 2.1. Dependency cache

Gradle lưu metadata và artifact tải từ Maven/Ivy repositories. Khi chạy offline:

~~~bash
./gradlew --offline build
~~~

Gradle chỉ sử dụng dependency đã có trong cache cục bộ. Nếu artifact hoặc metadata cần thiết chưa được cache, build sẽ thất bại. Offline mode không khôi phục output của task đã chạy trước đó; nó chỉ hạn chế truy cập repository.

Dependency cache không thay thế dependency locking hoặc verification. Nếu khai báo dependency bằng version động như \`1.+\`, kết quả resolve có thể thay đổi theo thời điểm và metadata repository.

### 2.2. Build cache

Build cache lưu output của các task cacheable. Khi một task có cùng implementation và cùng input đã khai báo, Gradle có thể lấy output từ cache thay vì thực thi task.

Bật build cache:

~~~bash
./gradlew --build-cache build
~~~

Hoặc cấu hình trong \`gradle.properties\`:

~~~properties
org.gradle.caching=true
~~~

Build cache hữu ích cho các task compile, test hoặc tạo artifact khi task được mô hình hóa đúng và output có thể tái tạo từ input đã khai báo.

Một task chỉ chạy nhanh hơn khi cache hit. Nếu input thay đổi, task implementation thay đổi hoặc task không cacheable, Gradle phải thực thi task.

### 2.3. Configuration cache

Configuration cache lưu kết quả cấu hình build để giảm thời gian thực hiện các bước cấu hình ở lần chạy tiếp theo:

~~~bash
./gradlew --configuration-cache build
~~~

Configuration cache không lưu output của task. Build cache lưu output của task. Hai cơ chế có thể được dùng cùng lúc:

~~~bash
./gradlew --configuration-cache --build-cache build
~~~

Nếu build script hoặc custom task không tương thích configuration cache, Gradle sẽ báo vấn đề khi lưu hoặc tái sử dụng configuration state. Cần xử lý các vấn đề đó theo hướng dẫn của Gradle thay vì giả định configuration cache sẽ sửa được task không xác định input/output.

## 3. Khóa toolchain và dependency

Muốn build tái lập, phải kiểm soát phiên bản công cụ và dependency trước khi tối ưu cache.

### 3.1. Gradle Wrapper

Commit các file Wrapper vào repository và cố định phiên bản Gradle. Trong \`gradle/wrapper/gradle-wrapper.properties\`, khai báo distribution cụ thể và checksum:

~~~properties
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.5-bin.zip
distributionSha256Sum=<verified-sha256-of-the-distribution>
~~~

Thay placeholder bằng checksum chính thức đã xác minh của distribution được chọn. Không tự tạo hoặc đoán checksum. Wrapper giúp developer và CI dùng cùng phiên bản Gradle, còn checksum bảo vệ tính toàn vẹn của file distribution tải về.

### 3.2. Java toolchain và release target

Khai báo toolchain thay vì phụ thuộc vào Java đang nằm trong PATH:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        // Có thể chỉ định vendor nếu tổ chức yêu cầu một JDK vendor cụ thể.
    }
}
~~~

Đặt release target cho compiler:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

Toolchain chọn JDK thực thi compile/test theo cấu hình. \`options.release\` giới hạn API và bytecode target. Hai thiết lập phục vụ mục đích khác nhau; không nên chỉ dựa vào \`JAVA_HOME\` trên máy developer.

Nếu build tạo runtime image, phải khóa cả JDK chứa \`jlink\` và các file module trong \`jmods\`. Cùng major version 21 vẫn chưa đảm bảo byte-for-byte giống nhau nếu vendor hoặc patch release khác nhau.

### 3.3. Khóa dependency version

Tránh dynamic version và version range cho dependency phát hành. Dùng dependency locking để ghi lại phiên bản đã resolve:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Tạo hoặc cập nhật lock state bằng:

~~~bash
./gradlew dependencies --write-locks
~~~

Commit lockfiles do Gradle tạo ra. Khi dependency graph thay đổi có chủ đích, cập nhật lock state trong một thay đổi được review.

### 3.4. Xác minh dependency artifacts

Dependency locking kiểm soát version được resolve; dependency verification kiểm tra nội dung artifact tải về. Có thể khởi tạo metadata checksum:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Review \`gradle/verification-metadata.xml\` rồi commit file đó. Không tự động tin mọi checksum mới nếu chưa xác minh nguồn và thay đổi dependency. CI nên thực thi verification để phát hiện artifact bị thay đổi ngoài dự kiến.

Với plugin Gradle, cũng cố định version plugin trong \`plugins { }\` hoặc version catalog. Build logic và plugin là input của quá trình tạo artifact, vì vậy không nên để version plugin trôi theo repository.

## 4. Làm cho archive output có tính xác định

JAR là archive. Nếu thứ tự entry hoặc timestamp thay đổi, hai JAR có thể khác bytes dù class/resource giống nhau.

Với Gradle archive tasks:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Cấu hình này loại bỏ timestamp gốc của file khỏi archive và yêu cầu thứ tự entry ổn định. Nó giúp các JAR/ZIP do các archive task hỗ trợ tạo ra có thể so sánh ổn định hơn.

Tuy nhiên, đây không phải bảo đảm duy nhất cho reproducibility. Manifest, generated resource, build metadata, plugin, JDK và các task tùy biến vẫn có thể ghi timestamp hoặc nội dung phụ thuộc môi trường vào output.

Không ghi thời gian hiện tại, absolute path hoặc tên máy build vào resource được đóng gói nếu các giá trị đó không phải input có chủ đích. Nếu cần build version hoặc commit id, hãy đưa chúng thành input rõ ràng và thống nhất cách tạo.

## 5. Tạo runtime image bằng jlink

Ví dụ tạo image từ module ứng dụng và các module phụ thuộc:

~~~bash
jlink \\
  --module-path "$JAVA_HOME/jmods:build/mods" \\
  --add-modules com.acme.app \\
  --bind-services \\
  --launcher app=com.acme.app/com.acme.app.Main \\
  --output build/runtime-image
~~~

Các input quan trọng cần kiểm soát:

- JDK distribution chứa \`jlink\` và thư mục \`jmods\`.
- Tất cả modular JAR/exploded modules trên module path.
- Module gốc trong \`--add-modules\`.
- Service declarations và lựa chọn \`--bind-services\`.
- Launcher name, main module/class và các tùy chọn linker.
- OS, CPU architecture và môi trường native của target.

\`jlink\` tạo image phụ thuộc nền tảng. Không dùng một runtime image Linux để thay cho image Windows hoặc image của kiến trúc CPU khác. Hãy tạo image trên JDK phù hợp với target và kiểm thử image đó trong môi trường tương ứng.

Có thể giảm kích thước bằng các tùy chọn như:

~~~bash
--strip-debug
--no-header-files
--no-man-pages
--compress=2
~~~

Chỉ bật các tùy chọn sau khi xác định yêu cầu runtime và test xác nhận ứng dụng vẫn hoạt động. Nếu ứng dụng dùng locale data, font, service provider hoặc module được nạp động, phải bảo đảm image vẫn chứa đủ thành phần cần thiết.

### 5.1. Khóa module set

Dùng \`--add-modules\` với tập module gốc có chủ đích và để linker resolve dependency. Khi ứng dụng dùng service provider, kiểm tra module consumer có \`uses\` và provider có \`provides\`; \`--bind-services\` giúp liên kết provider quan sát được trên module path.

Không lấy danh sách module từ một lần chạy ngẫu nhiên rồi hard-code mà không hiểu lý do. Module được dùng qua reflection, JDBC driver, logging provider hoặc plugin có thể không xuất hiện trong dependency graph tĩnh theo cách dễ nhận biết. Hãy kiểm thử các luồng chức năng và cấu hình thực tế.

### 5.2. Kiểm tra image

Sau khi link:

~~~bash
build/runtime-image/bin/java -version
build/runtime-image/bin/java --list-modules
~~~

Dùng Java executable bên trong image. Nếu gọi \`java\` từ PATH, có thể đang kiểm tra JDK khác trên máy build.

Kiểm tra launcher:

~~~bash
build/runtime-image/bin/app
~~~

Kiểm tra cả module resolution, service discovery, cấu hình, native dependency và luồng nghiệp vụ tối thiểu. Build image thành công chỉ chứng minh linker đã tạo được output; nó không chứng minh image đã đủ điều kiện production.

## 6. Reproducibility của runtime image

Để hai lần tạo runtime image có thể so sánh, phải cố định mọi input của linker và bước chuẩn bị module path.

Một bộ input nên ghi nhận:

| Input | Cách kiểm soát |
| --- | --- |
| Source revision | Ghi commit SHA và trạng thái working tree. |
| Gradle distribution | Dùng Wrapper version cố định và checksum đã xác minh. |
| JDK | Cố định vendor, version/update và platform. |
| Dependencies | Dùng lockfiles và dependency verification. |
| Module artifacts | Ghi hash của từng modular JAR hoặc artifact đầu vào. |
| jlink arguments | Quản lý trong build logic, không nhập thủ công tùy môi trường. |
| OS/architecture | Tách cache/image theo target platform. |
| Environment | Cố định các biến có ảnh hưởng tới generated content. |
| Output | Sinh vào thư mục sạch và so sánh manifest hash. |

Không nên khẳng định mọi output \`jlink\` đều byte-for-byte giống nhau giữa các JDK vendor, patch release hoặc OS khác nhau. Hãy xác định reproducibility trong cùng toolchain/platform trước; nếu cần so sánh cross-platform, so sánh các thuộc tính có ý nghĩa như module list, version, cấu hình và behavior thay vì kỳ vọng toàn bộ bytes giống nhau.

### 6.1. Tạo manifest hash

Có thể tạo danh sách file và SHA-256 để so sánh hai image. Ví dụ trên Linux:

~~~bash
find build/runtime-image -type f -print0 \\
  | sort -z \\
  | xargs -0 sha256sum > runtime-image.sha256
~~~

Manifest này ghi nhận nội dung file. Nếu cần kiểm tra cả file mode, symbolic link hoặc metadata khác, bổ sung các thuộc tính đó vào manifest theo quy ước của dự án.

Để so sánh hai image, tạo manifest theo cùng quy trình và so sánh:

~~~bash
diff -u image-a.sha256 image-b.sha256
~~~

Nếu hash khác, tìm file đầu tiên khác nhau và xác định input tạo ra file đó. Đừng chỉ so sánh kích thước thư mục vì hai image có thể cùng kích thước nhưng nội dung khác.

Với Windows, dùng PowerShell để liệt kê file và \`Get-FileHash -Algorithm SHA256\`; chuẩn hóa đường dẫn tương đối và thứ tự trước khi tạo manifest.

## 7. Đưa jlink task vào Gradle build cache

Gradle chỉ có thể cache output một cách an toàn nếu task khai báo đầy đủ input và output. Với custom task tạo runtime image, cần mô hình hóa tối thiểu:

- Module artifacts và JDK \`jmods\` là file inputs.
- Executable \`jlink\` hoặc toolchain identity là input.
- Module names, launcher, linker arguments, OS/architecture và các tùy chọn là scalar inputs.
- Runtime image directory là output.
- Task implementation và logic build là một phần của cache key.

Một custom task có thể dùng \`@CacheableTask\` khi output thực sự chỉ phụ thuộc vào những input đã khai báo. Các property file inputs nên khai báo path sensitivity phù hợp; thường dùng relative paths khi absolute workspace path không ảnh hưởng kết quả.

Ví dụ về hợp đồng input/output của task:

~~~kotlin
@CacheableTask
abstract class LinkRuntimeImage : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val moduleArtifacts: ConfigurableFileCollection

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val jlinkExecutable: RegularFileProperty

    @get:Input
    abstract val jlinkArguments: ListProperty<String>

    @get:Input
    abstract val targetPlatform: Property<String>

    @get:OutputDirectory
    abstract val imageDirectory: DirectoryProperty
}
~~~

Đây là phần khai báo contract; task implementation phải thực thi đúng executable, dùng đúng module artifacts và tạo output trong \`imageDirectory\`. Nếu toolchain phụ thuộc vào các file JDK khác như \`jmods\`, phải khai báo chúng là inputs hoặc mô hình hóa một toolchain input tương đương đủ để cache key thay đổi khi JDK thay đổi.

Không khai báo executable path hoặc JDK version bằng một chuỗi cố định rồi bỏ qua nội dung toolchain. Hai JDK có cùng version string nhưng khác vendor/build có thể tạo output khác nhau.

### 7.1. Khi nào task không nên cache?

Không cache task nếu nó có side effect không được biểu diễn trong output, ví dụ:

- Gửi request hoặc ghi dữ liệu vào hệ thống bên ngoài.
- Đọc trạng thái thời gian thực mà không khai báo input.
- Tạo output phụ thuộc vào random value hoặc current timestamp.
- Ghi vào một thư mục ngoài output directory đã khai báo.
- Dựa vào biến môi trường hoặc file cấu hình không được khai báo.
- Tạo image khác nhau theo máy build nhưng cache key không phân biệt platform/toolchain.

Một cache hit có nghĩa Gradle bỏ qua action và khôi phục output đã lưu. Nếu task còn có side effect cần xảy ra mỗi lần chạy, cache có thể làm hành vi sai. Hãy tách task tạo artifact thuần túy khỏi task deploy/publish có side effect.

## 8. Tránh cache key sai hoặc cache miss không cần thiết

### 8.1. Khai báo đầy đủ input

Mỗi giá trị có thể làm thay đổi output phải được khai báo. Với task tạo image, không được bỏ qua:

- Nội dung module JAR và resource.
- Module path order nếu thứ tự có ý nghĩa.
- JDK executable và JDK modules.
- Linker arguments.
- Environment variables ảnh hưởng tới output.
- OS/architecture nếu output phụ thuộc nền tảng.

Nếu thiếu input, Gradle có thể trả output cũ cho một build có kết quả đáng lẽ phải khác. Đây là cache correctness bug, nguy hiểm hơn cache miss vì build vẫn có vẻ thành công.

### 8.2. Tránh input không ổn định

Không đưa absolute path của workspace, thời gian build hoặc tên máy vào input nếu chúng không ảnh hưởng nội dung output. Dùng relative path normalization thích hợp để cùng source checkout ở các thư mục khác nhau vẫn có thể tái sử dụng cache.

Tuy nhiên, không được loại bỏ một path khỏi cache key nếu output thật sự phụ thuộc vào vị trí đó. Path sensitivity phải phản ánh đúng semantics của task.

### 8.3. Output phải được tạo xác định

Task cần ghi output vào vị trí được khai báo, xóa hoặc thay thế output cũ theo quy tắc rõ ràng và không để lại file stale. Không ghi thêm log, temporary file hoặc generated artifact ngoài output directory mà Gradle không biết.

Nếu task sử dụng thư mục output, hãy bảo đảm nội dung cuối cùng phản ánh chính xác input của lần chạy. Một file cũ còn sót lại có thể làm image trông đầy đủ dù task hiện tại không tạo ra nó.

## 9. Local và remote build cache

Local build cache hữu ích cho developer build lại trên cùng máy. Remote build cache cho phép CI và nhiều developer chia sẻ output task đã cache.

Ví dụ cấu hình remote HTTP cache trong \`settings.gradle\`:

~~~groovy
buildCache {
    remote(HttpBuildCache) {
        url = uri("https://cache.example.internal/cache/")
        push = false
    }
}
~~~

CI đáng tin cậy có thể được cấu hình push:

~~~groovy
buildCache {
    remote(HttpBuildCache) {
        url = uri("https://cache.example.internal/cache/")
        push = System.getenv("CI") == "true"
    }
}
~~~

Đây chỉ là minh họa; endpoint, authentication và quyền push/pull phải theo hệ thống cache của tổ chức. Không hard-code credential vào repository. Dùng secret store hoặc cơ chế authentication được build infrastructure hỗ trợ.

Một mô hình thường dùng:

- CI trên branch tin cậy build và push cache.
- Pull request có thể đọc cache nhưng không được ghi cache dùng chung nếu contributor chưa được tin cậy.
- Developer đọc remote cache và dùng local cache cho output riêng.
- Cache được quản lý retention và dung lượng, tránh tăng vô hạn.
- Cache key chứa platform/toolchain nên image Linux và Windows không dùng nhầm output của nhau.

Remote cache là một nguồn artifact build. Chỉ cho phép writer đáng tin cậy; nếu một actor không đáng tin cậy có thể ghi output tùy ý vào cache dùng chung, build khác có thể khôi phục artifact không mong muốn.

## 10. Kiểm chứng cache có hoạt động đúng

Chạy build lần đầu:

~~~bash
./gradlew --build-cache clean build
~~~

Chạy lại:

~~~bash
./gradlew --build-cache build
~~~

Gradle có thể hiển thị task được khôi phục từ cache với trạng thái \`FROM-CACHE\`. Task \`UP-TO-DATE\` có nghĩa output hiện tại vẫn hợp lệ trong workspace; nó không đồng nghĩa với cache hit.

Để kiểm tra cache correctness, thay đổi lần lượt từng input quan trọng và xác nhận task phải chạy lại:

- Thay đổi một class/resource trong module input.
- Thay đổi linker argument.
- Thay JDK/toolchain.
- Thay module set hoặc service provider.
- Thay target OS/architecture.

Sau mỗi thay đổi, kiểm tra task không khôi phục output của input cũ. Khi khôi phục về input ban đầu, cache có thể hit lại nếu key và output tương ứng còn tồn tại.

Không đánh giá cache chỉ bằng việc build nhanh hơn. Cần xác nhận output sau cache hit giống output của một lần thực thi thật với cùng input.

## 11. Kiểm thử reproducibility trong CI

Một pipeline có thể tạo hai output độc lập từ cùng commit trong hai workspace sạch:

1. Resolve dependency bằng lockfiles và verification.
2. Dùng đúng Gradle Wrapper và JDK toolchain.
3. Build module JAR.
4. Tạo runtime image từ cùng module set và jlink arguments.
5. Tạo manifest hash của JAR và runtime image.
6. So sánh hai manifest.
7. Nếu khác, lưu manifest và log toolchain để xác định input bị bỏ sót.
8. Chạy smoke/integration tests trên image sau khi kiểm tra nội dung.

Có thể dùng hai runner cùng OS/architecture và cùng toolchain để kiểm tra bit-for-bit. Nếu runner khác nhau, cần xác định trước thuộc tính nào phải giống và thuộc tính nào được phép khác.

CI cũng nên có một job build không dùng build cache định kỳ để đối chiếu output thật với output được cache. Điều này giúp phát hiện task khai báo thiếu input hoặc cache entry không còn phù hợp. Không cần tắt cache trong mọi build; chỉ cần có một đường kiểm chứng độc lập.

## 12. Chẩn đoán lỗi reproducibility và cache

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Hai JAR khác hash nhưng class giống nhau | Timestamp, archive order hoặc manifest khác | Cố định archive timestamp/order và kiểm tra resource metadata. |
| Hai runtime image có module list khác nhau | JDK/module path hoặc service binding khác | So sánh JDK, module artifacts, \`--add-modules\`, \`--bind-services\`. |
| Cache hit nhưng output không đúng | Task thiếu input hoặc output có side effect | Kiểm tra task annotations, inputs/outputs và cache key. |
| Task luôn chạy lại | Input path/metadata thay đổi hoặc task không cacheable | Xem build scan/task outcome và chuẩn hóa input hợp lý. |
| Developer hit cache, CI miss | Toolchain, OS, absolute path hoặc plugin khác | So sánh cache key inputs và build environment. |
| Build offline thất bại | Dependency chưa có trong dependency cache | Chạy online để tải dependency đã khóa và xác minh. |
| Configuration cache không được tái sử dụng | Build logic chưa tương thích hoặc configuration input thay đổi | Đọc configuration cache problems và sửa build logic. |
| Runtime image thiếu provider | Module/provider không được link hoặc module path khác | Kiểm tra \`uses\`, \`provides\`, \`--bind-services\` và module list. |
| Image chỉ chạy trên máy build | Image khác OS/architecture hoặc thiếu native dependency | Build/test trên platform target. |
| Remote cache có output không tin cậy | Quyền push cache quá rộng | Giới hạn writer, xác thực nguồn và tách cache theo trust boundary. |

## 13. Quy trình đề xuất cho module image có cache

1. Khóa Gradle Wrapper, plugin, JDK vendor/version và dependency versions.
2. Bật dependency verification và commit lockfiles.
3. Cấu hình archive tasks để loại bỏ timestamp không cần thiết và sắp xếp entry ổn định.
4. Xác định module roots, module path, service binding và jlink arguments.
5. Tạo runtime image trong output directory sạch.
6. Nếu muốn cache jlink task, khai báo đầy đủ JDK, jmods, module artifacts, arguments, target platform và output.
7. Bật build cache; cấu hình remote cache với quyền push/pull phù hợp.
8. Bật configuration cache riêng và xử lý các vấn đề tương thích.
9. Build hai lần trong workspace sạch trên cùng platform, so sánh manifest hash.
10. Kiểm thử runtime image bằng chính executable trong image và trong container target.
11. Lưu toolchain identity, commit SHA, dependency verification state và artifact hashes cùng bản phát hành.

Build cache tăng tốc việc tạo lại output; reproducible build giúp xác định output có thực sự được tạo từ cùng input. Hai mục tiêu hỗ trợ nhau nhưng không thay thế nhau. Cache chỉ an toàn khi task có input/output contract đầy đủ, còn reproducibility cần khóa toàn bộ toolchain, dependency, môi trường và quy tắc tạo artifact.
