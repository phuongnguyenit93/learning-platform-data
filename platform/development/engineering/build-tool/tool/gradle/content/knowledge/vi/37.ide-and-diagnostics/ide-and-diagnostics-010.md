# Tránh dùng clean hoặc xóa toàn bộ cache như cách sửa lỗi mặc định trong Gradle

## 1. Vấn đề: vì sao “xóa cache là hết lỗi” thường là chẩn đoán sai?

Một lỗi Gradle vừa xuất hiện trong IntelliJ IDEA hoặc terminal. Người học có thể phản xạ bằng:

~~~bash
./gradlew clean build
~~~

hoặc xóa `build/`, `.gradle/`, thậm chí cả `~/.gradle`. Sau đó build chạy lại thành công, nhưng chưa ai giải thích được vì sao. Cách xử lý này **không phải bản sửa kỹ thuật** nếu lỗi thực ra là custom task thiếu khai báo input, Gradle JVM sai, repository thiếu quyền, IDE model cũ hay plugin đọc trạng thái không được theo dõi.

Với chủ đề **IDE và chẩn đoán** thuộc **Build Tool Gradle**, đề bài là **“Tránh dùng clean hoặc xóa toàn bộ cache như cách sửa lỗi mặc định”**. Mục tiêu không phải cấm `clean`; mục tiêu là dùng nó **đúng thời điểm, đúng phạm vi và có giả thuyết kiểm chứng**.

Những tác hại của thói quen xóa mọi thứ:

- **Mất bằng chứng:** file đầu ra lỗi, task history, Configuration Cache problems report, log và kết quả có thể dùng để so sánh bị xóa.
- **Tăng thời gian:** xóa output làm compiler/test chạy lại hoặc phải restore; xóa dependency cache có thể tải lại JAR, plugin và metadata.
- **Che lỗi input tracking:** task tạo file sai vì thiếu `@InputFile` vẫn có thể chạy đúng ngay sau clean nhưng sẽ sai ở incremental build tiếp theo.
- **Không sửa nguyên nhân:** `clean` không thể biến một Java class không tồn tại thành hợp lệ, không khắc phục repository `403` hoặc chứng chỉ TLS sai.
- **Gây lỗi mới:** xóa Wrapper distributions và caches khiến một môi trường offline không còn đủ dependencies, làm quá trình CI/developer khó lặp lại.
- **Tăng rủi ro bảo mật:** `GRADLE_USER_HOME` có thể chứa init scripts, daemon logs, metadata và user configuration nhạy cảm; thao tác xóa đại trà có thể ảnh hưởng nhiều projects.
- **Đánh đồng IDE với Gradle:** editor báo đỏ do SDK/index/sync khác với `compileJava` thật sự fail.

**Nguyên tắc:** *Tái hiện → phân loại → thu bằng chứng → tắt/ép đúng một cơ chế để thử → sửa gốc → kiểm lại incremental behavior*. `clean` hoặc targeted invalidation chỉ là một bước sau khi đã xác định nó sẽ giúp trả lời câu hỏi nào.

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt build outputs, project-local Gradle state, dependency cache, Build Cache, Configuration Cache, Gradle Wrapper, Daemon và IDE index.
2. Đọc `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED` và `FAILED` đúng nghĩa.
3. Dùng `--info`, `--stacktrace`, `--rerun-tasks`, `--no-build-cache`, `--no-configuration-cache`, `--refresh-dependencies`, `--offline` và `--stop` để kiểm từng giả thuyết.
4. Phân biệt một dependency resolution error với task output stale hoặc IDE project import lỗi.
5. Hiểu vì sao `clean build --build-cache` vẫn có thể lấy output từ Build Cache.
6. Viết task có inputs/outputs rõ ràng và kiểm việc thay input **không cần clean**.
7. Chạy một ví dụ Java 17 + Gradle Groovy DSL + JUnit Jupiter đầy đủ, gồm lệnh `javac`, `java` và stdout chính xác.
8. Xây runbook khôi phục có mục tiêu, không phá những caches không liên quan.
9. Biết lúc nào một clean build trên môi trường tin cậy là cần thiết cho reproducibility hoặc artifact phát hành.
10. Dùng Gradle TestKit và CI để bắt lỗi incremental thay vì đòi mọi người luôn xóa cache.

## 2. Trước khi xóa, phải biết Gradle đang lưu dữ liệu ở đâu

Nhiều thành phần được gọi chung là “cache” nhưng chúng khác hoàn toàn về mục đích.

| Thành phần | Vị trí thường gặp | Công dụng | Nếu xóa sẽ ra sao? |
| --- | --- | --- | --- |
| Build outputs | `<project>/build/` ở root/subproject | Classes, JAR, test reports, generated resources | Outputs mất; tasks chạy lại hoặc restore từ Build Cache |
| Project-local Gradle state | `<root>/.gradle/` | Configuration Cache, execution history, VFS/bookkeeping tùy version | Mất một số trạng thái incremental/config |
| Configuration Cache | `<root>/.gradle/configuration-cache/` | Configured task graph và state | Phải cấu hình lại lần sau; không xóa dependencies |
| Dependency cache | `<GRADLE_USER_HOME>/caches/modules-2/` | JARs, POMs, dependency metadata/repository resolution | Tải/resolve lại; `--offline` có thể fail |
| Local Build Cache | Thường `<GRADLE_USER_HOME>/caches/build-cache-1/` | Task output cache entries | Cache miss, task phải chạy hoặc lấy remote |
| Artifact transform cache | Các thư mục transform trong Gradle User Home | Cached transformed artifacts | Tính transforms lại |
| Wrapper distributions | `<GRADLE_USER_HOME>/wrapper/dists/` | Gradle distributions đã tải | Wrapper có thể phải tải lại distribution |
| Gradle Daemon | Process + logs trong `<GRADLE_USER_HOME>/daemon/<version>/` | JVM build engine, diagnostic logs | Dừng/xóa có thể mất trạng thái/log |
| IDE indexes/model | IDE user data, project metadata | Code indexes, classpath/source roots/import model | Chỉ ảnh hưởng IDE; không giống Gradle Build Cache |
| Remote Build Cache | Server được tổ chức quản lý | Task outputs dùng giữa machines | Không bị xóa bởi local `clean` |
| Published Maven repository | Artifact registry | Released JAR/POM | Không phải Gradle build cache |

`GRADLE_USER_HOME` mặc định thường là `~/.gradle` trên Linux/macOS và đường dẫn tương ứng trong home của user trên Windows. Nó **có thể được tùy chỉnh** qua môi trường/CLI, đặc biệt trong CI. Vì vậy không đoán path rồi dùng thao tác xóa hàng loạt.

### 2.1. `clean` xóa những gì?

Khi Java/Application/Base plugin cung cấp `clean` task, nó thường là `Delete` task xóa **build directory đã được định nghĩa** cho project tương ứng.

~~~bash
./gradlew clean
~~~

không tự xóa toàn bộ:

- `GRADLE_USER_HOME` hoặc dependency metadata/artifacts.
- Local hay remote Build Cache entries.
- Gradle Wrapper distribution.
- IDE indexes.
- Mọi daemon logs.
- Files tạo ở vị trí không do `clean` quản lý.

Trong multi-project build, phạm vi phụ thuộc task selection. Khi chỉ cần dọn output của module `:app`, nếu task đó tồn tại, dùng:

~~~bash
./gradlew :app:clean
~~~

**Không đồng nhất:** `clean` có thể làm output trên workspace mất, nhưng `./gradlew clean assemble --build-cache` vẫn có thể báo `FROM-CACHE` cho `compileJava`. Điều đó nghĩa output được khôi phục từ Build Cache chứ không phải compiler action thực sự chạy lại.

### 2.2. Xóa `.gradle` của project không giống xóa `~/.gradle`

Project-local `.gradle/configuration-cache` thường chỉ lưu configuration state của build cụ thể. Gradle User Home có repositories resolution caches, Build Cache entries, wrapper dists, daemon logs và user configuration.

Nếu nghi **một Configuration Cache entry hỏng**, xóa cả Gradle User Home làm thay đổi nhiều thứ không liên quan. Nếu Maven `401`, xóa `modules-2` cũng không thay server credentials. Phải biết lỗi thuộc lớp nào.

### 2.3. Không xóa trước khi thu bằng chứng

Trước khi can thiệp vào file state:

1. Ghi lệnh Gradle cụ thể và nguyên văn lỗi.
2. Ghi `./gradlew --version` và build task path.
3. Lưu stacktrace/log `--info` hoặc Configuration Cache HTML problems report.
4. Ghi Java toolchain, Gradle JVM, OS, plugin versions và commit.
5. Xác định đường dẫn/cached entry nào có bằng chứng bất thường.
6. Kiểm xem Gradle/IDE process còn đang ghi vào đó không.
7. Có backup/rollback cho thư mục nhỏ nhất cần đổi.
8. Nêu trước kết quả kỳ vọng của phép thử.

**Nếu không trả lời được “vì sao xóa path này có thể giúp?” thì chưa nên xóa.**

## 3. Hiểu task outcomes để không chữa nhầm tối ưu thành lỗi

| Task outcome | Nghĩa của Gradle | Hành động phù hợp |
| --- | --- | --- |
| `UP-TO-DATE` | Inputs/outputs chưa đổi so với local history | Bình thường nếu artifact đúng |
| `FROM-CACHE` | Output restored từ local/remote Build Cache | Kiểm đúngness và trust khi nghi ngờ |
| `NO-SOURCE` | Không có source files phù hợp | Xem source sets nếu bất ngờ |
| `SKIPPED` | Bỏ task do điều kiện, ví dụ `onlyIf` | Kiểm điều kiện/test filters |
| `FAILED` | Có lỗi trong task | Thu stacktrace/root cause |
| Không có label | Task action thường đã chạy | Không kết luận về hiệu năng |
| `BUILD SUCCESSFUL` | Invocation không trả lỗi | Không chứng minh không có output sai nếu input tracking thiếu |

Ví dụ:

~~~text
> Task :compileJava UP-TO-DATE
> Task :processResources NO-SOURCE
> Task :test UP-TO-DATE
BUILD SUCCESSFUL
~~~

không có dấu hiệu buộc phải chạy `clean`. `UP-TO-DATE` là tối ưu quan trọng khi task inputs/outputs được khai đầy đủ.

### 3.1. Các cơ chế cache khác nhau

**Task up-to-date:** kiểm inputs/outputs và execution history trong workspace, thường tránh chạy action.

**Build Cache:** lấy output artifacts của task cacheable theo cache key; có thể từ local hoặc remote cache. `FROM-CACHE` không có nghĩa output tự động trusted.

**Configuration Cache:** lưu configured task graph, giúp bỏ qua configuration phase; vẫn có thể compile/test khi inputs đổi.

**Dependency cache:** lưu dependency downloads/metadata; phục vụ resolution. Không quyết định một JUnit test pass.

Ví dụ `Configuration Cache hit` và `:compileJava` thực thi lại có thể cùng xuất hiện khi sửa source; đó là behavior đúng. Một lỗi dependency `Could not resolve` không được chữa bằng cách xóa Configuration Cache vô tội vạ.

### 3.2. Một clean build pass vẫn có thể che task bug

Giả sử một task sinh `build/generated/report.txt` từ `templates/report.txt`, nhưng không khai template là input:

~~~text
Template A -> task chạy -> report A
Template B -> task UP-TO-DATE vì declared inputs không đổi -> report A (sai)
clean      -> output biến mất -> task chạy -> report B (đúng tạm)
Template C -> task lại UP-TO-DATE -> report B (sai)
~~~

Nếu chỉ hướng dẫn team chạy `clean` khi báo cáo cũ, task sẽ tiếp tục sai ở mọi incremental build. Sửa đúng là khai `@InputFile`/`inputs.file` và output của task.

## 4. Bộ lệnh chẩn đoán đúng phạm vi

### 4.1. Bước đầu tiên: tái hiện task nhỏ nhất

Nếu lỗi ở `:app:test`:

~~~bash
./gradlew :app:test --console=plain --stacktrace --info
~~~

Nếu ở `:core:compileJava`:

~~~bash
./gradlew :core:compileJava --stacktrace --info
~~~

`--console=plain` giúp log ổn định; `--stacktrace` cho exception chain; `--info` cung cấp lý do task execute/cache decision. Nếu chỉ có một project root (như demo mục 10), dùng `./gradlew test` thay `:app:test`.

**Không chạy full `clean build` để tìm một lỗi compiler ở một task đã biết** trừ khi có lý do riêng.

### 4.2. Cờ và mục đích chính xác

| Lệnh/cờ | Cần kiểm gì? | Không giải quyết điều gì? |
| --- | --- | --- |
| `./gradlew --version` | Wrapper Gradle/JVM version | Không tự sửa JDK |
| `--stacktrace` | Lỗi Java/Gradle bắt đầu từ đâu | Không đổi cache |
| `--info` | Vì sao task chạy, dependency/cache details | Không xóa output |
| `--warning-mode all` | Các deprecations có thể ảnh hưởng plugin | Không chữa API usage |
| `--debug` | Log sâu khi thật sự cần | Rất lớn, có thể có thông tin nhạy cảm |
| `--rerun-tasks` | Ép selected task và prerequisites thực thi | Không xóa toàn bộ outputs trước |
| `--no-build-cache` | Tắt load/store task outputs từ Build Cache invocation này | Không tắt up-to-date checks |
| `--no-configuration-cache` | Tạm không reuse Configuration Cache | Không tắt Build Cache |
| `--refresh-dependencies` | Revalidate dependency resolution/cache metadata | Không ép tải mọi JAR |
| `--offline` | Chỉ dùng modules đã có trong dependency cache | Không tải artifact thiếu |
| `--status` | Xem Gradle Daemon status | Không xóa dữ liệu |
| `--stop` | Dừng daemons thuộc Gradle version đang dùng | Không chữa code sai |
| `--dry-run` | Xem task plan mà không chạy task actions | Không chạy JUnit/compiler |
| `:app:clean` | Xóa outputs của module được clean quản lý | Không xóa remote cache |
| `--no-daemon` | Không reuse long-lived daemon, khi khả dụng | Có thể có single-use daemon |
| `--scan` | Timeline/build data qua service được cho phép | Cần kiểm chính sách dữ liệu |

Theo Gradle Configuration Cache Adoption docs, `--rerun-tasks` bỏ qua up-to-date checks **và Build Cache restoration** cho tasks được thực thi; cách này bộc lộ task action chỉ bị che bởi `UP-TO-DATE`/`FROM-CACHE`. Không nhầm nó với `clean`.

### 4.3. Thay một biến tại một thời điểm

Một trình tự có mục đích khi thấy output nghi sai:

~~~bash
./gradlew :app:compileJava --info
./gradlew :app:compileJava --no-build-cache --info
./gradlew :app:compileJava --rerun-tasks --info
~~~

Kết quả khác nhau giúp phân loại:
- `--no-build-cache` vẫn có thể `UP-TO-DATE`: local history chứ không phải Build Cache.
- `--rerun-tasks` có thể làm compiler chạy thật: cho phép so output.
- Nếu output sai cả khi rerun, nguyên nhân có thể là source/dependency/toolchain/task implementation.
- Nếu chỉ cache restore cho output sai, kiểm task input tracking và cache producer/entry.

**Đừng ghép tất cả flags cùng lúc trong phép thử đầu tiên**, vì mất khả năng xác định lớp gây sai.

### 4.4. Log có thể chứa dữ liệu nhạy cảm

`--debug` và một số build scans có thể in repository URLs, environment/config values hoặc đường dẫn nội bộ. Redact credentials trước khi chia sẻ. Không upload build scan lên service ngoài tổ chức nếu policy không cho phép.

---

## 5. Trường hợp dependency: dùng refresh, đừng xóa `modules-2`

### 5.1. Triệu chứng và những nguyên nhân thường gặp

~~~text
Could not resolve all files for configuration
Could not find group:library:version
Received status code 401
Received status code 403
PKIX path building failed
Read timed out
Could not resolve plugin
~~~

Các nguyên nhân thường là GAV không tồn tại, sai repository, credentials/permission, TLS/trust store, proxy, mạng, dynamic/changing version metadata hoặc plugin repository riêng.

### 5.2. Xem dependency graph

~~~bash
./gradlew :app:dependencies \
    --configuration runtimeClasspath
~~~

Để biết vì sao một module/version được chọn:

~~~bash
./gradlew :app:dependencyInsight \
    --dependency guava \
    --configuration runtimeClasspath
~~~

`guava` chỉ là tên ví dụ, thay bằng module thực tế. Nếu lỗi compilation, kiểm `compileClasspath` thay vì chỉ `runtimeClasspath`. Một dependency không có mặt vì khai nhầm `testImplementation` thay vì `implementation` không được chữa bằng xóa cache.

### 5.3. `--refresh-dependencies` làm gì?

~~~bash
./gradlew :app:dependencies --refresh-dependencies
~~~

Gradle revalidate dependency resolution, module metadata và artifacts theo repository. Nó có thể dùng HTTP HEAD/checksum để tránh tải lại JAR không đổi; **không có nghĩa “force redownload everything”**. Với dynamic versions hoặc changing modules như SNAPSHOT, nó hữu ích để xác minh metadata stale sau repository/publishing changes.

Nó không sửa:
- Sai group/name/version.
- Repository trả 401/403 do thiếu quyền.
- TLS certificate sai hoặc proxy không cho kết nối.
- Artifact chưa được publish.
- Dependency lock đang pin version không mong muốn.

Không để `--refresh-dependencies` trong mọi run của CI/IDE. Nó tăng network lookups và làm chậm workflow mà chưa chắc xử lý vấn đề.

### 5.4. `--offline` không chứng minh cache bị hỏng

~~~bash
./gradlew :app:test --offline
~~~

Gradle chỉ dùng dependencies đã cache. Nếu module chưa từng được tải hoặc cache chưa có bản cần thiết, build fail theo thiết kế. Offline fail không có nghĩa “phải xóa Gradle User Home”; ngược lại, xóa `modules-2` làm offline càng không chạy được.

### 5.5. Khi nào mới chạm một artifact cache?

Nếu có bằng chứng file JAR/ZIP/metadata cụ thể hỏng (checksum/CRC mismatch, truncated download không được Gradle tự xử lý), làm:

1. Xác định đúng GAV, repository và artifact.
2. Thu logs/checksum evidence.
3. Đảm bảo repository đáng tin còn cung cấp artifact.
4. Dừng writer processes.
5. Chỉ invalidate **đúng entry/path** được xác minh nếu Gradle không thể tự revalidate.
6. Rerun task nhỏ nhất, kiểm checksum/content.

Không xóa toàn `~/.gradle/caches/modules-2` chỉ vì một `403` hoặc module không tồn tại.

---

## 6. Trường hợp generated output cũ: sửa task input/output model

### 6.1. Một anti-pattern có thể bị clean che

~~~groovy
// ĐOẠN SAI: chỉ dùng để nhận diện lỗi, không đưa vào build thật.
tasks.register('badReport') {
    outputs.file(layout.buildDirectory.file('report.txt'))

    doLast {
        def text = new File('templates/input.txt').getText('UTF-8')
        def region = System.getenv('REPORT_REGION') ?: 'local'
        def output = layout.buildDirectory.file('report.txt').get().asFile
        output.parentFile.mkdirs()
        output.setText(text + region, 'UTF-8')
    }
}
~~~

Đoạn này sai vì task action đọc file/env quyết định output nhưng không khai `@InputFile`/`@Input`; closure còn có nguy cơ capture Gradle Project/script state ở execution, không phù hợp Configuration Cache. Gradle chỉ biết một output, không biết mọi nguồn làm thay đổi nó.

`clean` xóa output, khiến task chạy lại, nhưng **lỗi khai thiếu input vẫn còn**.

### 6.2. Thiết kế đúng bằng typed Gradle task

~~~groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files

import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

abstract class RenderReportTask extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getTemplateFile()

    @Input
    abstract Property<String> getRegion()

    @OutputFile
    abstract RegularFileProperty getReportFile()

    @TaskAction
    void render() {
        def input = templateFile.get().asFile.toPath()
        def output = reportFile.get().asFile.toPath()

        String contents = Files.readString(input, StandardCharsets.UTF_8)
        String result = contents + region.get() + '\n'

        Files.createDirectories(output.parent)
        Files.writeString(output, result, StandardCharsets.UTF_8)
    }
}

tasks.register('renderReport', RenderReportTask) {
    templateFile.set(
        layout.projectDirectory.file('templates/input.txt')
    )
    region.set(
        providers.environmentVariable('REPORT_REGION')
            .orElse('local')
    )
    reportFile.set(
        layout.buildDirectory.file('reports/report.txt')
    )
}
~~~

**Đây là đoạn custom task minh họa**, cần tạo file `templates/input.txt` và đặt trong Gradle Groovy plugin/build script có imports thích hợp; không phải một phần bắt buộc của demo Java chính ở mục 10.

Khi file template đổi hoặc env `REPORT_REGION` đổi, Gradle có task input snapshot tương ứng; task action chỉ đọc typed inputs và viết declared output. Không truy cập `project` từ `@TaskAction`.

### 6.3. Chưa nên gắn `@CacheableTask` ngay

Một custom task không trở thành Build Cache cacheable chỉ vì có inputs/outputs. Chỉ thêm `@CacheableTask` khi đã xác minh implementation/inputs/outputs đầy đủ, output deterministic, path normalization/relocatability phù hợp, và không có side effects. Nếu sai input model, cache hit có thể phân phối output sai đến nhiều developers/CI.

### 6.4. Đúng regression test phải dùng build không clean

1. Run task một lần → kiểm đúng output.
2. Run lại không đổi inputs → thường `UP-TO-DATE`.
3. Thay template file → output phải đổi đúng.
4. Thay `REPORT_REGION` → output phải đổi đúng.
5. Run với `--rerun-tasks` → kết quả phải cùng nội dung với cùng inputs.
6. Test Configuration Cache hai lần nếu task/plugin dự định hỗ trợ.
7. Nếu chia sẻ remote cache, test relocatability ở workspace khác.

Nếu chỉ chạy `clean` trước từng phép thử, bạn không kiểm được input tracking regression.

---

## 7. Trường hợp Configuration Cache: xem report thay vì xóa state

### 7.1. Lỗi do code, không phải file cache

Ví dụ Gradle báo:

~~~text
1 problem was found storing the configuration cache
invocation of 'Task.project' at execution time is unsupported
~~~

Hãy mở **Configuration Cache HTML problems report** được link trong console. Có thể là task action truy cập `Project`, closure capture build script, non-serializable object hoặc configuration input thay đổi mỗi lần.

Thử:

~~~bash
./gradlew :app:test --configuration-cache --stacktrace
./gradlew :app:test --no-configuration-cache --stacktrace
~~~

Nếu chỉ fail khi bật Configuration Cache, điều tra plugin/task implementation. `--no-configuration-cache` chỉ là **phép khoanh vùng**, không sửa logic. Nếu build còn bật Isolated Projects vốn yêu cầu Configuration Cache, hãy điều chỉnh chế độ Isolated Projects cho phép thử; đừng bật hai flags mâu thuẫn.

### 7.2. Configuration Cache miss không tự là lỗi

Gradle phải cấu hình lại khi build scripts/plugins hoặc tracked configuration inputs (file, environment, system property) thay đổi. Một log:

~~~text
Calculating task graph as configuration cache cannot be reused
because system property 'someDestination' has changed
~~~

là nguyên nhân invalidation có thể hoàn toàn hợp lệ. Nếu input đổi mọi lần do script đọc PID/current time, nên sửa dùng lazy Provider hoặc tránh eager configuration reads khi thích hợp. Xóa `.gradle/configuration-cache` chỉ khiến cache miss lần tiếp theo, không sửa nguồn input volatile.

### 7.3. Thử hai lần để biết Configuration Cache tương thích thật

~~~bash
./gradlew test --configuration-cache --info
./gradlew test --configuration-cache --info
~~~

Lần đầu có thể store, lần sau có thể reuse nếu state/inputs không đổi. Gradle TestKit docs khuyến nghị chạy ít nhất hai lần: có vấn đề chỉ xuất hiện lúc **deserialize/reuse**, không phải khi store.

### 7.4. Khi nào invalidation có mục tiêu là hợp lý?

Tài liệu Gradle 9.9 mô tả Configuration Cache state ở:

~~~text
<build-root>/.gradle/configuration-cache/
~~~

Nếu có bằng chứng state bị corrupt hoặc cache entry được lưu sai không tự invalidated như mong đợi:

- Thu stacktrace và report trước.
- Thử `--no-configuration-cache` để xác nhận.
- Kiểm build logic/plugin/Wrapper version, sửa lỗi API nếu có.
- Dừng Gradle/IDE writers.
- Backup/đổi tên **riêng** `.gradle/configuration-cache` nếu cần kiểm lại clean configuration.
- Không xóa toàn Gradle User Home.
- Rerun một task nhỏ, xác nhận mới store/reuse được; nếu lỗi quay lại thì root cause chưa được sửa.

Một targeted invalidation *có điều kiện* trong PowerShell ở root project:

~~~powershell
$cache = Join-Path (Get-Location) '.gradle\configuration-cache'
if (Test-Path -LiteralPath $cache) {
    Rename-Item -LiteralPath $cache -NewName 'configuration-cache.saved'
}
~~~

Chỉ thực hiện sau khi chắc root đúng, không có process đang ghi và tên backup chưa tồn tại; không overwrite. Đổi tên giúp còn chứng cứ, không biến thành lệnh xóa hàng loạt. Trên POSIX, có thể dùng một thao tác đổi tên tương đương sau khi kiểm path. Không thực hiện nếu vẫn đang điều tra một plugin code error.

---

## 8. Trường hợp Build Cache: `--no-build-cache` khác `--rerun-tasks`

### 8.1. Khi output từ Build Cache bị nghi sai

~~~bash
./gradlew :app:compileJava --no-build-cache --info
~~~

Cờ này tạm tắt việc load/store Build Cache cho invocation, **nhưng local up-to-date checks vẫn hoạt động**. Vì vậy `:compileJava UP-TO-DATE` vẫn có thể xuất hiện.

Nếu muốn bắt compiler action chạy thật:

~~~bash
./gradlew :app:compileJava --rerun-tasks --info
~~~

Cờ này ép selected tasks và prerequisites thực thi mà không xóa toàn bộ generated outputs trước.

So sánh:

- Compiler chạy thật vẫn tạo lỗi → xem source/toolchain/dependency.
- Compiler chạy thật đúng, restore từ cache sai → kiểm cache key, producer trust và missing inputs.
- Output cũ nhưng status `UP-TO-DATE` → kiểm input/output contract và local history.
- Cache miss nhưng output đúng → performance matter, không phải correctness failure.

### 8.2. `clean build --build-cache` không bảo đảm pure rebuild

~~~bash
./gradlew clean assemble --build-cache
~~~

có thể restore `JavaCompile` output qua Build Cache. Đó là behavior documented. Nếu security/release policy yêu cầu artifact được tạo từ trusted pristine environment, dùng fresh runner và `--no-build-cache` theo policy; không coi `clean` trong workspace cũ là bằng chứng supply-chain integrity.

### 8.3. Cache poisoning và sai kết quả

Gradle remote Build Cache nhận outputs từ producers khác. Nếu cache entry nghi bị thao túng, không chỉ xóa `build/`; remote vẫn chứa entry. Dùng cache-off/fresh trusted environment để tái tạo, báo quản trị remote cache, phân quyền read/write và cách ly namespace nghi vấn. Một `FROM-CACHE` là status reuse, **không phải chữ ký xác minh ai đã sinh output**.

### 8.4. Bật debug không có nghĩa luôn nhanh hơn

Nếu task cache miss nhiều, đọc `--info` hoặc Build Cache Debugging docs để xem inputs/implementation/path sensitivity. Dynamic inputs, absolute paths, OS line endings, compiler versions hoặc `buildSrc` change có thể gây key khác. Không xóa cache để “tăng hit rate”; xóa có thể làm **giảm** cache hit rate.

---

## 9. Trường hợp IDE và Daemon: xử lý đúng tầng

### 9.1. IDE editor đỏ nhưng Gradle CLI xanh

Ví dụ IntelliJ IDEA báo import đỏ, nhưng:

~~~bash
./gradlew :app:compileJava --info
~~~

pass. Khi ấy nghi:

- IDE dùng Gradle distribution khác Wrapper.
- Gradle JVM, Java toolchain, Project SDK hay language level không khớp.
- IDE chưa sync source sets/dependencies/generated sources.
- IDE cache/index bị stale.
- Plugin IDE/Gradle integration hoặc annotation processing config chưa đúng.

**Thứ tự hợp lý:** đối chiếu Gradle Wrapper/JVM → Gradle CLI compile thật → Gradle tool window **Sync All Gradle Projects** trong IntelliJ → xem Sync logs → kiểm source roots/SDK → cân nhắc IDE-specific index invalidation **chỉ khi đã có bằng chứng**, không xóa Gradle cache bừa.

Với Eclipse Buildship, dùng `Gradle > Refresh Gradle Project` hoặc refresh từ Gradle Tasks view. Không xóa `.project`/`.classpath` hoặc `.idea` trước khi biết những file nào thuộc cấu hình IDE/VCS của nhóm.

### 9.2. Gradle JVM khác Java toolchain

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

cho Java tasks dùng JDK 17 toolchain. Nó không bảo đảm IDE Project SDK cũng là 17 hoặc Gradle Daemon JVM đang là JDK 17. Cần kiểm:

- `./gradlew --version`: Gradle version và JVM của Gradle.
- IDE Settings → Gradle JVM/distribution.
- `JAVA_HOME` của shell/CI.
- Project SDK/language level.
- `java.toolchain` trong build scripts.

`clean` không khiến JDK cũ hỗ trợ API Java mới.

### 9.3. Daemon vấn đề không phải Build Cache

Chẩn đoán:

~~~bash
./gradlew --status
./gradlew --version
~~~

Nếu build fail vì daemon connection, memory leak, stale long-lived process hoặc lock, có thể dùng:

~~~bash
./gradlew --stop
~~~

Theo Gradle docs, lệnh dừng các daemons thuộc **cùng Gradle version** mà wrapper invocation sử dụng. Nó **không xóa dependency cache hoặc build outputs**, nhưng có thể ảnh hưởng build khác cùng version đang chạy; chỉ làm khi thích hợp.

### 9.4. `--no-daemon` là một phép thử riêng

~~~bash
./gradlew test --no-daemon --info
~~~

có thể dùng single-use Daemon tùy JVM arguments; không có nghĩa Gradle chắc chắn chạy hoàn toàn trong client process. Nếu build pass khi không reuse daemon, điều tra Gradle JVM, `org.gradle.jvmargs`, toolchains, IDE setting và plugin giữ state. Không chạy `--no-daemon` cho mọi dev build để né việc sửa cấu hình.

### 9.5. File locks, disk full, permissions

Lỗi như:

~~~text
Permission denied
No space left on device
Access is denied
Failed to move temporary workspace
Cannot delete file because it is in use
~~~

cần kiểm process giữ lock, disk/inodes/quota, filesystem ownership, antivirus, path length/case sensitivity. Nếu `clean` xóa thất bại vì IDE/test process đang mở JAR, xóa toàn Gradle User Home càng không giải quyết nguyên nhân.

---

## 10. Demo hoàn chỉnh: Java 17 + Gradle Groovy DSL + JUnit Jupiter

Mục tiêu demo là **chứng minh Gradle tự nhận input change không cần clean**. Đây là project một module để cú pháp/đầu ra dễ tái hiện.

### 10.1. Cấu trúc

~~~text
diagnostic-gradle-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/
    │   ├── Greeting.java
    │   └── Main.java
    └── test/java/demo/
        └── GreetingTest.java
~~~

**Gradle Wrapper** phải được tạo hợp lệ từ Gradle distribution đáng tin; không giả lập `gradle-wrapper.jar` bằng file rỗng. Cần JDK 17 toolchain và JUnit dependencies từ Maven Central khi lần đầu chưa có cache.

### 10.2. `settings.gradle`

~~~groovy
rootProject.name = 'diagnostic-gradle-lab'
~~~

### 10.3. `build.gradle`

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.Main'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Application plugin áp Java plugin và cung cấp `run`, `compileJava`, `test`. JUnit Jupiter dependencies phục vụ tests; `useJUnitPlatform()` không tự tải JUnit.

### 10.4. `src/main/java/demo/Greeting.java`

~~~java
package demo;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String rawName) {
        String name = rawName == null ? "" : rawName.strip();
        if (name.isEmpty()) {
            name = "bạn";
        }
        return "Xin chào, " + name + "!";
    }
}
~~~

### 10.5. `src/main/java/demo/Main.java`

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Gradle" : args[0];
        System.out.println(Greeting.message(name));
    }
}
~~~

### 10.6. `src/test/java/demo/GreetingTest.java`

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void greetsName() {
        assertEquals("Xin chào, Linh!", Greeting.message("Linh"));
    }

    @Test
    void trimsWhitespace() {
        assertEquals("Xin chào, Mai!", Greeting.message(" Mai "));
    }

    @Test
    void usesFallbackForBlank() {
        assertEquals("Xin chào, bạn!", Greeting.message("   "));
    }

    @Test
    void usesFallbackForNull() {
        assertEquals("Xin chào, bạn!", Greeting.message(null));
    }
}
~~~

Bốn JUnit 5 tests; Java production code chỉ dùng standard library.

### 10.7. Chạy lần đầu và chạy lại không clean

~~~bash
./gradlew compileJava --info
./gradlew test --info
./gradlew -q run
./gradlew -q run --args="Linh"
~~~

Java application stdout cho `run` không có args:

~~~text
Xin chào, Gradle!
~~~

Cho args `Linh`:

~~~text
Xin chào, Linh!
~~~

Log tasks có thể khác tùy cache state/Gradle version; stdout của Java source mới là expected text chính xác.

Chạy:

~~~bash
./gradlew test --info
./gradlew test --info
~~~

với inputs/outputs không đổi thường thấy các action tasks có outputs là `UP-TO-DATE`. Không cần clean. Nếu không, đọc `--info` để tìm input nào đổi; Gradle có thể có điều kiện khác nên không cam kết mọi task luôn skip.

### 10.8. Ép test chạy lại mà không xóa outputs

~~~bash
./gradlew test --rerun-tasks --info
~~~

Task `test` và prerequisites sẽ được thực thi lại theo cơ chế rerun; không phải bước “xóa toàn bộ cache”. Đây là cách kiểm liệu assertions thực sự pass khi action chạy, thay vì chỉ nhận kết quả work avoidance.

### 10.9. Thay đổi source có chủ đích

Trong `Greeting.java`, tạm sửa:

~~~java
return "Xin chào, " + name + "!";
~~~

thành:

~~~java
return "Chào, " + name + "!";
~~~

Chạy:

~~~bash
./gradlew test --info
~~~

Các tests đang kỳ vọng `Xin chào` nên chúng **phải fail** do assertion mismatch (giả định không có lỗi môi trường khác). Việc thay source làm JavaCompile/Test nhận biết thay đổi mà **không cần clean**.

Chạy:

~~~bash
./gradlew -q run --args="Linh"
~~~

Java stdout lúc này:

~~~text
Chào, Linh!
~~~

Khôi phục dòng Java cũ rồi chạy `./gradlew test`; tests lại pass. Đó là bằng chứng input tracking hoạt động khi chỉnh code.

### 10.10. Kiểm cùng source bằng `javac`/`java` độc lập

Từ root trên Linux/macOS:

~~~bash
mkdir -p manual-classes
javac -encoding UTF-8 -d manual-classes \
    src/main/java/demo/Greeting.java \
    src/main/java/demo/Main.java
java -cp manual-classes demo.Main Linh
~~~

Sau khi đã khôi phục source ban đầu, stdout chính xác:

~~~text
Xin chào, Linh!
~~~

Trên PowerShell, dùng `New-Item -ItemType Directory -Force manual-classes` và đặt lệnh `javac` trên một dòng hoặc continuation phù hợp. `javac`/`java` không dùng Gradle caches; chúng chỉ kiểm Java code, **không chứng minh Gradle task input tracking**.

### 10.11. Kiểm hai cache flags riêng rẽ

~~~bash
./gradlew test --no-build-cache --info
./gradlew test --no-configuration-cache --info
~~~

Lệnh đầu vẫn có thể `UP-TO-DATE`; lệnh sau vẫn có thể lấy task outputs từ Build Cache nếu được bật riêng. Nếu muốn kiểm action phải chạy thực, dùng `--rerun-tasks`. Không suy “tắt cache” là một lệnh duy nhất cho mọi lớp.

### 10.12. Thử Configuration Cache hai lần

~~~bash
./gradlew test --configuration-cache --info
./gradlew test --configuration-cache --info
~~~

Nếu build logic và inputs cho phép, lần sau có thể reuse configuration. Nếu fail do task closure serialization, đọc HTML problems report; đừng xóa cả Gradle User Home.

### 10.13. Một lần clean chỉ để minh họa

~~~bash
./gradlew compileJava --build-cache --info
./gradlew clean compileJava --build-cache --info
~~~

`compileJava` là built-in cacheable task; lần sau **có thể** `FROM-CACHE` nếu cache entry hợp lệ tồn tại. Nếu không, Gradle chạy Java compiler. `clean` chỉ xóa output, không ép remote/local Build Cache mất entry.

### 10.14. Revalidate dependencies khi thực sự cần

~~~bash
./gradlew test --refresh-dependencies --info
~~~

Với JUnit fixed version ở Maven Central, Gradle có thể revalidate mà không tải lại JAR nếu không đổi. Không cần cờ này mỗi lần test hoặc mỗi lần IDE sync.

### 10.15. Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat test --info --stacktrace
.\gradlew.bat test --rerun-tasks --info
.\gradlew.bat test --no-build-cache --info
.\gradlew.bat test --no-configuration-cache --info
.\gradlew.bat -q run --args="Linh"
~~~

Expected stdout của Java application ở lệnh cuối:

~~~text
Xin chào, Linh!
~~~

Không dùng Windows recursive delete các thư mục người dùng chỉ để sửa file lock hoặc IDE index.

---

## 11. Bài thực hành bổ sung: custom task chứng minh thay đổi scalar input

Bổ sung đoạn này vào cuối `build.gradle` của demo, để thấy thay task input có thể làm output đổi mà không cần xóa `build/`:

~~~groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files

import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class WriteBannerTask extends DefaultTask {
    @Input
    abstract Property<String> getBanner()

    @OutputFile
    abstract RegularFileProperty getDestination()

    @TaskAction
    void writeBanner() {
        def path = destination.get().asFile.toPath()
        Files.createDirectories(path.parent)
        Files.writeString(
            path,
            banner.get() + '\n',
            StandardCharsets.UTF_8
        )
    }
}

tasks.register('writeBanner', WriteBannerTask) {
    banner.set(
        providers.gradleProperty('bannerText')
            .orElse('Xin chào')
    )
    destination.set(
        layout.buildDirectory.file('generated/banner.txt')
    )
}
~~~

Lệnh:

~~~bash
./gradlew writeBanner --info
./gradlew writeBanner --info
./gradlew writeBanner -PbannerText=Hello --info
~~~

Sau lệnh thứ ba, nội dung `build/generated/banner.txt` là:

~~~text
Hello
~~~

với một LF cuối file. Vì task có `@Input Property<String>` và `@OutputFile`, Gradle có đủ model để nhận ra `bannerText` thay đổi. Task này minh họa up-to-date checks; **chưa đánh dấu `@CacheableTask`**. Muốn chia sẻ Build Cache outputs, cần xác minh all inputs/outputs, deterministic behavior, relocatable paths và opt-in task type đúng cách.

### 11.1. Khi nào dùng `@InputFile`?

Nếu task phụ thuộc nội dung template file, đừng chỉ khai đường dẫn dưới `@Input Property<String>`; file content đổi mà path giữ nguyên sẽ không làm scalar input đổi. Dùng:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
abstract RegularFileProperty getTemplateFile()
~~~

Đây là **trích đoạn thuộc custom task class**, cần imports và khai báo task đầy đủ như mục 6.2. `PathSensitivity.RELATIVE` thích hợp khi relative file location/content có ý nghĩa và giúp cache relocatability. Không dùng `@Internal` để che một giá trị thực sự làm đổi output.

### 11.2. Vì sao `outputs.upToDateWhen { false }` không là bản sửa mặc định?

Nó làm task không được coi up-to-date, nhưng không bổ sung missing inputs, không bảo đảm đúng remote Build Cache và làm giảm performance. Nếu task có side effects quan trọng hoặc output không thể track, có trường hợp non-cacheable là đúng. Với generator/compilation, sửa input/output modeling mới là giải pháp.

---

## 12. TestKit và CI: chứng minh không cần clean

Một plugin hoặc custom task dùng chung cho team nên có **Gradle TestKit functional tests**. Bài kiểm quan trọng không phải “first build after deleting everything passes” mà là:

1. First run tạo output chính xác.
2. Second run unchanged: `UP-TO-DATE` khi phù hợp.
3. Thay một input file: task phản ứng, output mới đúng.
4. Thay scalar input/env: output mới đúng.
5. Xóa đúng output của task: task tạo/restore được.
6. Chạy `--no-build-cache` và `--build-cache`: cùng inputs phải cho same output bytes.
7. Chạy `--configuration-cache` hai lần: không có serialization problems.
8. Trong workspace khác, output vẫn đúng nếu task được thiết kế relocatable.
9. Không có `clean` ở trước mọi assertion, vì như vậy không test incremental behavior.

### 12.1. Mẫu Java TestKit helper

Đây là helper minh họa dành cho **plugin development project** đã khai `gradleTestKit()` và JUnit 5; để compile/run cần tạo fixture build thật và plugin-under-test classpath. Không đặt nó thẳng vào demo Java app rồi coi là standalone test.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.File;
import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.gradle.testkit.runner.TaskOutcome;

class UpToDateCheck {
    static BuildResult run(File projectDir) {
        return GradleRunner.create()
            .withProjectDir(projectDir)
            .withArguments("writeBanner", "--stacktrace")
            .withPluginClasspath()
            .build();
    }

    static void assertSecondRunUpToDate(File projectDir) {
        BuildResult first = run(projectDir);
        assertNotNull(first.task(":writeBanner"));

        BuildResult second = run(projectDir);
        assertEquals(
            TaskOutcome.UP_TO_DATE,
            second.task(":writeBanner").getOutcome()
        );
    }
}
~~~

TestKit `TaskOutcome` hữu ích hơn chỉ parser console text. Nhưng **assert output contents sau khi input đổi** vẫn bắt buộc: một task khai thiếu input có thể cho `UP-TO-DATE` sai. Với plugin project dùng Configuration Cache, thêm testcase chạy cùng invocation hai lần để kiểm store và reuse.

### 12.2. CI không nên “clean hết” mọi job

- Developer feedback CI có thể dùng Build Cache/up-to-date/Configuration Cache đúng contract.
- Với PR/untrusted forks, bảo vệ remote cache write permissions và secrets.
- Có regression tests kiểm no-clean input changes.
- Có bài test fresh workspace riêng để xác minh reproducibility.
- Release artifact pipeline có thể yêu cầu trusted ephemeral environment và `--no-build-cache` theo security policy.
- Storage cleanup thuộc retention/quota policy, không tự xóa `~/.gradle` khi job fail.

**Một CI luôn clean có thể che bug incremental** mà developers gặp hàng ngày. Tách correctness verification và release artifact generation thay vì dùng `clean` làm mẹo chữa chung.

---

## 13. Khi nào clean hoặc targeted cache invalidation là hợp lý?

### 13.1. Trường hợp clean đúng nghĩa

- Muốn so **clean vs incremental** để xác định bug.
- Một stale compiled resource/output ở **module cụ thể** đã được phát hiện.
- Cần fresh output folder cho packaging/thử nghiệm.
- Đo cold build hiệu năng riêng biệt.
- Trusted release build yêu cầu clean/fresh workspace để bảo đảm provenance.
- Task implementation đã đổi output layout, cần kiểm dọn stale files không còn được quản lý.

Thử nhỏ:

~~~bash
./gradlew :app:clean :app:test
~~~

chỉ khi tasks đó tồn tại và scope đáp ứng giả thuyết. Nếu có Build Cache bật, tasks sau clean có thể restore outputs, không nhất thiết execute.

### 13.2. Trường hợp không phải lý do clean

- Dependency repository trả `401/403`.
- Java import sai hoặc API không có.
- JUnit assertions fail vì business logic đổi.
- Gradle Daemon JVM không tương thích.
- IDE chưa sync model/SDK.
- Configuration Cache report chỉ ra `Project` access trong `@TaskAction`.
- Task input file bị khai thiếu.
- Có nhiều `UP-TO-DATE` và build pass.
- Remote Build Cache nghi poisoned.
- Network timeout hoặc proxy settings sai.

Những lỗi này cần xử lý ở **nguồn gốc**.

### 13.3. Điều kiện khi muốn invalidate một cache nhỏ

- Có bằng chứng specific corruption/serialization state.
- Đã dùng cờ diagnostic phân biệt lớp cache.
- Thu log/report/metadata cần giữ.
- Xác nhận đúng directory, owner và mức quyền.
- Không có active Gradle/IDE writers.
- Có đường rollback/backup.
- Chỉ invalidate **phạm vi liên quan**.
- Sau đó kiểm build đầu lẫn no-clean input-change behavior.

Không dùng dòng sau như một bước thực hành:

~~~text
rm -rf ~/.gradle
~~~

Dòng đó là **anti-pattern**, có thể làm mất nhiều lớp cache, user settings/logs và offline artifacts. Không áp dụng vào Gradle User Home dùng chung hoặc máy không có quyền quản lý.

---

## 14. Bảng tra cứu nhanh theo triệu chứng

| Triệu chứng | Trước tiên kiểm | Cách sửa thật |
| --- | --- | --- |
| `cannot find symbol` | `compileJava --stacktrace`, imports, compileClasspath | Source/API/dependency/toolchain |
| `package ... does not exist` | Dependencies configuration | Khai dependency đúng scope |
| `Could not resolve` | Repository, GAV, network, credentials | Sửa resolution; refresh khi metadata stale |
| Maven `401/403` | Auth/ACL | Cấp đúng quyền, không xóa modules-2 |
| `PKIX path building failed` | TLS cert/JDK trust store | Sửa trust store |
| `NO-SOURCE` bất ngờ | Source sets/source dirs | Sửa source layout/plugin |
| `SKIPPED` bất ngờ | `onlyIf`/task conditions | Sửa conditions |
| `UP-TO-DATE` nhưng output cũ | Task input contract | `@Input`/`@InputFile` đầy đủ |
| `FROM-CACHE` với output nghi sai | Producer/trust/input model | Cache-off/rerun, điều tra cache |
| Config Cache problems | HTML report, task action/closure | Sửa unsupported API |
| Config Cache miss mỗi invocation | Volatile config input | Lazy Provider/tracked inputs |
| IDE đỏ, CLI pass | Gradle JVM/SDK/sync model | Sync/IDE configuration |
| Daemon không connect | `--status`, JVM, logs | `--stop` khi phù hợp, sửa root cause |
| Disk full/file lock | OS storage/process | Targeted cleanup, dừng process |
| `--offline` thiếu module | Dependency cache chưa có artifact | Resolve online từ repository tin cậy |
| `clean build` pass, incremental fail | Hidden input/state | No-clean regression tests |
| Wrapper không tải được | URL/TLS/proxy | Sửa Wrapper/mạng |
| Plugin không tương thích | Gradle/plugin versions | Nâng/hạ có kiểm, đọc release notes |
| Remote cache rủi ro | Backend ACL/provenance | Quarantine, rebuild trusted |

## 15. Bài tập và đáp án

### Bài 1 — `clean` có xóa dependency cache không?

**Không mặc định.** `clean` chỉ xóa những outputs được task quản lý, thường là build directory; dependency cache ở Gradle User Home.

### Bài 2 — `clean assemble --build-cache` có thể `FROM-CACHE` không?

**Có.** Build output đã xóa, nhưng Build Cache entries vẫn tồn tại. Đây là hành vi đúng.

### Bài 3 — `--no-build-cache` có bảo đảm task action chạy?

**Không.** Task vẫn có thể `UP-TO-DATE` theo workspace local history. Dùng `--rerun-tasks` khi cần action thật.

### Bài 4 — `--refresh-dependencies` có tải lại mọi JAR không?

**Không.** Gradle revalidate module/artifacts và tránh tải lại nếu chúng vẫn hợp lệ. Không phải phép xóa caches hàng loạt.

### Bài 5 — `--offline` fail vì JUnit chưa tải có phải corruption?

**Không.** Missing cached module là lỗi expected trong offline mode. Xóa dependency cache khiến offline còn tệ hơn.

### Bài 6 — `UP-TO-DATE` nhưng generated file sai sau sửa template?

**Nghi task thiếu input**. Thêm `@InputFile`/`inputs.file` và kiểm lại no-clean input change. Không buộc clean mọi lần.

### Bài 7 — IDE editor đỏ, Gradle compile pass thì sao?

Kiểm IDE Gradle distribution, Gradle JVM, Project SDK/source roots và Sync All Gradle Projects; không xóa `~/.gradle` trước.

### Bài 8 — `--stop` có xóa cache không?

**Không.** Nó dừng Gradle daemons thuộc version liên quan. Phù hợp khi process/JVM state nghi vấn.

### Bài 9 — Configuration Cache miss sau đổi build.gradle là lỗi?

**Không.** Build logic là configuration input; cần reconfiguration sau thay đổi là bình thường.

### Bài 10 — Khi nào xóa `.gradle/configuration-cache` có cơ sở?

Khi có bằng chứng state cụ thể hỏng sau khi xem report và thử `--no-configuration-cache`; phải dừng writers, backup và chỉ chạm đúng path.

### Bài 11 — Vì sao xóa `~/.gradle` nguy hiểm?

Nó có thể xóa downloaded libraries, Wrapper distributions, Build Cache, daemon logs và user settings, làm offline build fail và mất chứng cứ.

### Bài 12 — Chạy `java -cp ...` có kiểm Gradle cache không?

**Không.** Nó kiểm compiled Java program, không gọi Gradle task/caching. Dùng Gradle CLI/TestKit để kiểm build behavior.

### Bài 13 — Một TestKit test chỉ chạy sau clean đủ không?

**Không.** Phải có second run unchanged, input-change run và output assertion **không clean**, để bắt lỗi incremental tracking.

### Bài 14 — Vì sao `--debug` không phải mặc định?

Log quá lớn, khó đọc và có thể chứa thông tin nhạy cảm. Bắt đầu với `--info --stacktrace`.

### Bài 15 — `NO-SOURCE` có nghĩa xóa outputs để source xuất hiện?

**Không.** Nó thường nghĩa task không thấy source files; kiểm source sets và paths.

### Bài 16 — Compiler đổi output khi chạy rerun nhưng không đổi khi UP-TO-DATE?

Kiểm task khai thiếu inputs, toolchain state hoặc output bị task khác ghi đè. Đừng coi `--rerun-tasks` là bản sửa lâu dài.

### Bài 17 — Cùng source mà Java output khác Windows/Linux?

Có thể do encoding, line endings, locale, timezone hoặc Java/tool versions. Khai input hoặc cố định output format trước khi dùng remote cache.

### Bài 18 — Một remote cache entry nghi không đáng tin thì clean có đủ?

**Không.** Cache remote vẫn có thể phục vụ entry sau clean. Cần tắt reuse, kiểm với trusted workspace và xử lý server ACL/provenance.

### Bài 19 — Tại sao phân biệt project .gradle và Gradle User Home?

Vì Configuration Cache project-local và dependency artifacts/user settings/Wrapper caches ở User Home phục vụ phạm vi khác nhau. Xóa sai chỗ làm hỏng môi trường khác.

### Bài 20 — Khi nào clean có giá trị thật?

Khi kiểm stale output cụ thể, đối chiếu clean/incremental correctness, benchmark cold build hoặc làm trusted release artifact theo policy. Đó là thí nghiệm có mục tiêu.

## 16. Checklist trước khi đề nghị xóa cache

1. Đã biết task path và lỗi thực tế chưa?
2. Đã dùng `./gradlew --version` thay đoán Gradle trên PATH?
3. Có `--stacktrace --info` và original logs?
4. Đã tách IDE-only problem khỏi Gradle CLI failure?
5. Đã kiểm Gradle JVM, toolchain, SDK, environment?
6. Đã hiểu task outcome trước khi can thiệp?
7. Nếu dependency lỗi, đã kiểm GAV/configuration/repository/quyền/TLS?
8. Có cần `--refresh-dependencies` vì metadata stale thật?
9. `--offline` có đủ dependencies cached?
10. Nếu output sai, đã khai đủ inputs/outputs?
11. Có dùng `--rerun-tasks` để kiểm task action không?
12. Có hiểu `--no-build-cache` không tắt up-to-date?
13. Có đọc Configuration Cache problems report khi liên quan?
14. Có thử `--no-configuration-cache` đúng trường hợp?
15. Có phân biệt project-local `.gradle` với Gradle User Home?
16. Có Gradle Daemon/File lock/permission/disk issue?
17. Nếu dùng `--stop`, đã cân nhắc ảnh hưởng daemons khác?
18. Có ghi giả thuyết và kết quả mong đợi của mỗi phép thử?
19. Nếu clean, có giới hạn chỉ module/task cần thiết?
20. Có giữ logs và file/output bất thường trước khi xóa?
21. Có quyền/backup khi targeted invalidation?
22. Không dùng `rm -rf ~/.gradle` làm giải pháp mặc định?
23. Có test build không clean sau khi sửa input?
24. Có Gradle TestKit regression test cho custom task?
25. CI vẫn dùng cache an toàn và có release policy sạch?
26. Có thể giải thích **nguyên nhân gốc** thay vì chỉ kể “clean giúp hết lỗi”?

## 17. Tài liệu Gradle chính thức

- [Gradle — Troubleshooting](https://docs.gradle.org/current/userguide/troubleshooting.html): logs, daemon failures, IDE refresh, build error workflow.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--rerun-tasks`, `--offline`, `--refresh-dependencies`, task selection, `clean`.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): task inputs/outputs, up-to-date checks và correctness.
- [Gradle — Incremental Builds and Caching](https://docs.gradle.org/current/userguide/gradle_optimizations.html): `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` và `SKIPPED`.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): local/remote task output caches và `FROM-CACHE` sau clean.
- [Gradle — Build Cache Debugging](https://docs.gradle.org/current/userguide/build_cache_debugging.html): missing/extraneous inputs, cache misses và repeatability.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): offline mode, dynamic/changing modules, `--refresh-dependencies`.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration reuse, invalidation semantics.
- [Gradle — Enabling Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_enabling.html): `--no-configuration-cache` và project-local Configuration Cache location.
- [Gradle — Configuration Cache Debugging](https://docs.gradle.org/current/userguide/configuration_cache_debugging.html): HTML problems report và TestKit two-run verification.
- [Gradle — Configuration Cache Adoption](https://docs.gradle.org/current/userguide/configuration_cache_adoption.html): `--rerun-tasks` để bộc lộ execution-time errors.
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): `--status`, `--stop`, JVM mismatch và daemon logs.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): Gradle JVM/Java compilation toolchain.
- [Gradle — Testing Build Logic with TestKit](https://docs.gradle.org/current/userguide/test_kit.html): GradleRunner và TaskOutcome.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): pin distribution/JDK compatibility.

**Kết luận:** Gradle tối ưu bằng cách **không làm lại những việc không cần thiết**. Một build đáng tin phải đúng khi incremental và khi cache hit, không chỉ đúng sau khi xóa output. Thu bằng chứng, chọn đúng công cụ khoanh vùng, sửa input/model/IDE/environment, và chỉ clean hoặc invalidate đúng phạm vi khi có lý do kiểm chứng được.
