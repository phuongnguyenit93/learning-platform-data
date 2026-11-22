# So sánh build sạch, build tăng dần và build dùng cache

Khi làm việc với dự án Java, cùng một lệnh build có thể mất vài giây ở lần chạy sau nhưng lâu hơn đáng kể khi chạy lần đầu hoặc sau khi dọn output. Sự khác biệt thường đến từ cách build tool sử dụng output hiện có, kiểm tra thay đổi đầu vào và tái sử dụng kết quả đã tạo trước đó.

Ba cách chạy thường được so sánh là **build sạch (clean build)**, **build tăng dần (incremental build)** và **build dùng cache (cached build)**. Chúng có mục tiêu và điều kiện khác nhau. Build sạch giúp xác nhận có thể tạo output từ đầu vào được quản lý; build tăng dần tránh làm lại công việc không cần thiết trong workspace hiện tại; build dùng cache tái sử dụng kết quả tương ứng với inputs đã biết, kể cả khi output cục bộ không còn.

Để so sánh đúng, cần phân biệt cache của task với cache dependency, configuration cache, trạng thái daemon và dữ liệu còn lại trong workspace. Nếu chỉ nhìn thời gian chạy một lệnh `build`, rất dễ kết luận sai về hiệu năng hoặc bỏ sót lỗi correctness.

## 1. Ba kiểu build và mục tiêu của từng kiểu

### 1.1. Build sạch (clean build)

Build sạch xóa output do build trước tạo ra rồi thực hiện lại các bước cần thiết để tạo artifact. Với Gradle, thường dùng:

```bash
./gradlew clean build
```

Với Maven:

```bash
./mvnw clean verify
```

Gradle `clean` thường xóa thư mục output của project như `build/`; Maven `clean` thường xóa `target/`. Sau đó build tool biên dịch, xử lý resource, chạy test và đóng gói theo task/lifecycle được yêu cầu.

Build sạch trả lời câu hỏi: *Nếu không dựa vào output project còn sót lại từ lần build trước, build có thể tạo ra kết quả cần thiết từ các đầu vào hiện tại không?*

Build sạch không nhất thiết là một build hoàn toàn không dùng bất kỳ cache nào. Ví dụ, Gradle `clean build` vẫn có thể dùng local/remote build cache nếu cache được bật; dependency metadata và artifact đã tải cũng có thể còn trong cache người dùng. Vì vậy, phải xác định rõ “sạch” đang nói đến output project, task cache hay cả dependency cache.

### 1.2. Build tăng dần (incremental build)

Build tăng dần tận dụng output đã có và chỉ làm lại công việc bị ảnh hưởng bởi thay đổi đầu vào. Nếu không có gì thay đổi, nhiều task có thể được đánh dấu `UP-TO-DATE` hoặc được bỏ qua theo cơ chế incremental của plugin.

Với Gradle:

```bash
./gradlew build
```

Chạy lại cùng lệnh trong cùng workspace khi source và inputs không đổi thường cho nhiều task `UP-TO-DATE`. Nếu sửa một Java source file, các task phụ thuộc vào source đó có thể chạy lại, trong khi task không bị ảnh hưởng tiếp tục dùng output hiện có.

Với Maven:

```bash
./mvnw verify
```

Maven và các plugin có thể tránh một số công việc dựa trên timestamp, trạng thái output hoặc logic incremental riêng. Tuy nhiên, Maven core không cung cấp một mô hình up-to-date/task-output cache tổng quát tương đương Gradle cho mọi plugin. Hành vi incremental phụ thuộc goal/plugin và cấu hình.

Build tăng dần trả lời câu hỏi: *Trong workspace hiện tại, sau thay đổi này, những phần nào thực sự cần được xử lý lại?*

### 1.3. Build dùng cache (cached build)

Build dùng cache tái sử dụng kết quả đã được lưu từ một lần thực thi trước khi build tool xác định inputs hiện tại tương ứng với cache entry đó. Kết quả có thể đến từ local cache hoặc remote cache.

Với Gradle, task có thể được đánh dấu `FROM-CACHE` khi output được lấy từ build cache. Ví dụ:

```bash
./gradlew build --build-cache
```

Nếu output task bị xóa bởi `clean`, nhưng cache entry còn và task đủ điều kiện cache, Gradle có thể lấy output từ cache thay vì thực thi lại task.

Build dùng cache trả lời câu hỏi: *Kết quả cho đúng tập inputs này đã được tạo và lưu trước đó chưa, để có thể tái sử dụng an toàn không?*

Cache không có nghĩa là dùng output cũ một cách tùy ý. Một cache entry chỉ an toàn khi task khai báo đầy đủ inputs/outputs, thực thi xác định và cache key đại diện đúng mọi yếu tố ảnh hưởng kết quả.

## 2. So sánh tổng quan

| Đặc điểm | Build sạch | Build tăng dần | Build dùng cache |
|---|---|---|---|
| Mục tiêu | Tạo lại output từ đầu trong project workspace. | Chỉ làm lại phần bị ảnh hưởng bởi thay đổi. | Tái sử dụng output đã lưu cho inputs tương ứng. |
| Output cục bộ | Thường bị xóa trước khi build. | Được giữ lại và kiểm tra. | Có thể được khôi phục từ cache nếu output cục bộ thiếu. |
| Thời gian thường gặp | Lâu hơn vì phải tạo lại output. | Nhanh khi thay đổi ít hoặc không đổi. | Nhanh nếu có cache hit phù hợp. |
| Dùng để xác minh | Khả năng build từ trạng thái output sạch. | Độ chính xác của up-to-date/incremental logic. | Tính đúng đắn và khả năng tái sử dụng cache. |
| Rủi ro cần chú ý | Có thể vẫn dùng cache hoặc dependency cache nếu chưa tắt. | Đầu vào ẩn có thể khiến output stale. | Inputs khai báo thiếu có thể làm cache trả output sai. |
| Tình huống điển hình | CI clean verification, trước release, điều tra output cũ. | Developer sửa code thường xuyên. | CI nhiều nhánh, nhiều runner hoặc build lặp lại. |

Ba kiểu này không phải ba lệnh hoàn toàn tách biệt. Một invocation có thể xóa output trước, sau đó dùng build cache để khôi phục một số task output. Một invocation khác có thể dùng up-to-date checking cho task này và cache hit cho task khác.

## 3. Những loại cache cần phân biệt

Trong một build Java có thể có nhiều lớp cache. Chúng lưu những thứ khác nhau và không bị xóa bởi cùng một lệnh.

| Loại cache/trạng thái | Nội dung được giữ | Ví dụ |
|---|---|---|
| Project outputs | Class, resource, JAR và report do build hiện tại tạo. | `build/`, `target/`. |
| Gradle up-to-date history | Thông tin để so sánh task inputs/outputs giữa các invocation trong workspace. | Task `UP-TO-DATE`. |
| Gradle build cache | Output của task cacheable theo cache key. | Local/remote cache, task `FROM-CACHE`. |
| Gradle configuration cache | Kết quả cấu hình build để tránh cấu hình lại toàn bộ. | Configuration cache entry. |
| Dependency cache | Metadata và artifact dependency đã resolve/tải. | Gradle user home hoặc Maven local repository. |
| Gradle Daemon/JVM state | Process JVM đang chạy, class đã nạp, runtime state. | Gradle Daemon còn idle. |
| Maven plugin state | Timestamp, marker hoặc dữ liệu incremental do plugin quản lý. | Plugin compiler/resources/generator. |

### 3.1. Project output không phải build cache

File `.class` trong `build/classes` hoặc `target/classes` là output nằm trong workspace. Nếu task được đánh giá `UP-TO-DATE`, Gradle có thể giữ nguyên output đó và không chạy task.

Build cache là nơi lưu kết quả có thể tái sử dụng. Nếu xóa `build/`, output cục bộ mất nhưng cache entry có thể vẫn còn.

### 3.2. Dependency cache không phải task output cache

Gradle cache và Maven local repository lưu metadata/artifact dependency đã resolve. `clean` thường không xóa chúng.

Ví dụ, build sạch vẫn có thể không cần tải lại `org.example:library:1.2.0` vì dependency artifact đã có trong cache. Điều này không có nghĩa task compile đã lấy output từ build cache.

### 3.3. Configuration cache không phải build cache

Gradle Configuration Cache lưu kết quả cấu hình build. Nó giảm chi phí configuration, không trực tiếp lưu class/JAR output của task.

Một build có thể đồng thời:

- Reuse Gradle Daemon.
- Reuse Configuration Cache.
- Đánh dấu một số task `UP-TO-DATE`.
- Lấy output task khác `FROM-CACHE`.
- Dùng dependency đã có trong dependency cache.

Khi phân tích hiệu năng, cần nhận diện đúng cơ chế nào tạo ra phần tiết kiệm thời gian.

## 4. Gradle: up-to-date checking hoạt động thế nào?

Gradle theo dõi inputs và outputs của task. Khi task được yêu cầu, Gradle so sánh trạng thái hiện tại với execution history trước đó.

Nếu inputs không thay đổi và outputs còn hợp lệ, task có thể được đánh dấu `UP-TO-DATE`. Action của task không cần chạy lại.

Ví dụ:

```text
Lần 1:
  compileJava -> thực thi, tạo class files
  processResources -> thực thi, copy resources
  jar -> thực thi, tạo JAR

Lần 2, không đổi inputs:
  compileJava -> UP-TO-DATE
  processResources -> UP-TO-DATE
  jar -> UP-TO-DATE
```

Nếu sửa `src/main/java/com/example/OrderService.java`, Gradle có thể xác định `compileJava` cần chạy lại. Các task downstream phụ thuộc output compile như `classes` hoặc `jar` cũng có thể cần cập nhật. `processResources` có thể vẫn `UP-TO-DATE` nếu resource inputs không đổi.

### 4.1. Task inputs phải đầy đủ

Task chỉ được kiểm tra chính xác nếu mọi yếu tố ảnh hưởng output đều được khai báo. Inputs có thể là:

- Source files và resource files.
- Configuration properties.
- Environment variables đã được đưa vào Provider/input.
- Tool version hoặc compiler classpath.
- Output của task producer khác.
- File hoặc directory ngoài source root.

Nếu task đọc một environment variable trong `doLast` mà không khai báo nó, Gradle có thể không biết giá trị đã đổi. Khi đó, task có thể `UP-TO-DATE` dù output đúng phải khác.

### 4.2. Task outputs phải được khai báo đúng

Gradle cần biết task sở hữu output nào. Nếu task ghi file nhưng không khai báo output, Gradle không thể quản lý up-to-date state hoặc build cache cho file đó một cách đầy đủ.

Ví dụ:

```groovy
def generatedFile = layout.buildDirectory.file('generated/build-info.txt')
def buildLabel = providers.gradleProperty('buildLabel').orElse('local')

tasks.register('generateBuildInfo') {
    inputs.property('buildLabel', buildLabel)
    outputs.file(generatedFile)

    doLast {
        def output = generatedFile.get().asFile
        output.parentFile.mkdirs()
        output.text = "label=${buildLabel.get()}\n"
    }
}
```

Trong ví dụ, property ảnh hưởng nội dung file được khai báo là input, còn file được tạo là output. Khi `buildLabel` thay đổi, task có thể được đánh giá cần chạy lại.

## 5. Gradle: đọc task outcome

Kết quả Gradle thường hiển thị trạng thái của từng task. Một số outcome phổ biến:

| Outcome | Ý nghĩa |
|---|---|
| `SUCCESS` | Task đã thực thi và hoàn tất. |
| `UP-TO-DATE` | Inputs/outputs được theo dõi không yêu cầu thực thi lại. |
| `FROM-CACHE` | Output được lấy từ build cache. |
| `NO-SOURCE` | Task không có source phù hợp để xử lý. |
| `SKIPPED` | Task bị bỏ qua theo điều kiện/cấu hình. |
| `FAILED` | Task thực thi nhưng thất bại. |

Ví dụ log:

```text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :classes UP-TO-DATE
> Task :jar UP-TO-DATE
```

Điều này thường cho thấy output trong workspace được giữ lại vì Gradle thấy task không cần chạy lại. Nó không cho biết task lấy output từ build cache.

Ví dụ khác:

```text
> Task :compileJava FROM-CACHE
> Task :processResources FROM-CACHE
> Task :jar FROM-CACHE
```

Các output tương ứng được lấy từ cache. Đây là dấu hiệu cache hit, không phải task action đã chạy lại.

## 6. Gradle: bật và tắt build cache

Có thể bật build cache trong `gradle.properties`:

```properties
org.gradle.caching=true
```

Hoặc bật cho một invocation:

```bash
./gradlew build --build-cache
```

Tắt build cache cho một invocation:

```bash
./gradlew build --no-build-cache
```

`--no-build-cache` tắt việc dùng build cache trong invocation đó. Nó không tự xóa project outputs, không dừng Gradle Daemon, không xóa dependency cache và không tắt up-to-date checking.

### 6.1. Task nào có thể dùng build cache?

Không phải mọi task đều tự động cacheable. Task phải được thiết kế với inputs/outputs đầy đủ, có thể tái sử dụng an toàn và được đánh dấu/triển khai phù hợp cho caching. Các task compile hoặc transform resource chuẩn thường có thể tham gia cơ chế này; task custom có side effect thường không phù hợp.

Task publish, deploy, gửi email hoặc cập nhật hệ thống bên ngoài không nên được cache như một tác vụ thuần tạo file, vì cache hit có thể bỏ qua side effect cần thực hiện.

### 6.2. Local cache và remote cache

Gradle có thể dùng local build cache trên máy và remote build cache được chia sẻ giữa developer/CI.

```groovy
// settings.gradle hoặc cấu hình build tương ứng
buildCache {
    local {
        enabled = true
    }
}
```

Remote cache cần cấu hình endpoint và chính sách truy cập phù hợp. Chỉ cho phép các build đáng tin cậy ghi cache; build từ mã không tin cậy có thể tạo output độc hại hoặc làm nhiễm cache dùng chung nếu không có kiểm soát.

Trong môi trường nhóm, remote cache có thể giúp CI lấy output từ build của developer hoặc job trước. Cần bảo đảm cache key phản ánh đúng toolchain, task implementation và mọi input ảnh hưởng output.

## 7. Vì sao `clean build` vẫn có thể là cached build?

Một điểm dễ nhầm là lệnh:

```bash
./gradlew clean build --build-cache
```

`clean` xóa output trong project, nhưng không nhất thiết xóa local/remote build cache. Khi task compile/package chạy sau clean, Gradle có thể tìm thấy cache entry tương ứng và khôi phục output.

Do đó, lệnh này có thể là:

- Clean đối với output cục bộ.
- Cached đối với task outputs được tái sử dụng.
- Warm đối với Gradle Daemon nếu daemon đã hoạt động.
- Warm đối với dependency cache.

Nếu muốn kiểm tra build sạch không dùng build cache task, có thể chạy:

```bash
./gradlew clean build --no-build-cache
```

Lệnh này vẫn có thể dùng dependency cache và daemon. Nếu muốn cold-start daemon, cần dừng daemon trước; nếu muốn thử dependency resolution từ đầu, cần quản lý riêng Gradle user home hoặc cache theo môi trường thử nghiệm. Không nên xóa cache toàn cục trên máy dùng chung chỉ để làm một phép đo.

## 8. Ba thí nghiệm Gradle để hiểu sự khác nhau

Giả sử project có task `build` và Gradle Wrapper.

### Thí nghiệm A: clean build không dùng build cache

```bash
./gradlew clean build --no-build-cache
```

Quan sát:

- Output project bị xóa trước.
- Các task cần thiết thực thi lại.
- Build cache không được dùng cho invocation này.
- Dependency cache và daemon vẫn có thể được tái sử dụng.

Đây là phép thử tốt để kiểm tra khả năng tái tạo output từ đầu vào hiện tại mà không dùng task-output cache.

### Thí nghiệm B: incremental build trong workspace

```bash
./gradlew build --no-build-cache
```

Chạy lệnh lần nữa mà không thay đổi inputs. Nhiều task có thể được đánh dấu `UP-TO-DATE`.

Sau đó sửa một source file và chạy lại. Quan sát task nào chạy lại, task nào tiếp tục up-to-date.

Thí nghiệm này kiểm tra up-to-date/incremental behavior của workspace mà không dùng build cache.

### Thí nghiệm C: build cache sau khi output bị xóa

```bash
./gradlew clean build --build-cache
./gradlew clean build --build-cache
```

Lần đầu tạo output và có thể lưu cache entry cho các task cacheable. Lần thứ hai xóa output project, sau đó có thể lấy task outputs từ cache.

Nếu thấy `FROM-CACHE`, Gradle đã tái sử dụng output. Nếu task vẫn `SUCCESS`, task có thể không cacheable, cache entry không có, inputs khác hoặc cache không được dùng cho task đó.

## 9. Thay đổi đầu vào và quan sát incremental behavior

Để hiểu build tăng dần, không chỉ chạy lại khi không đổi. Hãy thay đổi từng loại input và quan sát phạm vi task bị ảnh hưởng.

| Thay đổi | Task có thể cần chạy lại |
|---|---|
| Sửa Java source | `compileJava` và task downstream phụ thuộc class output. |
| Sửa resource | `processResources` và task đóng gói phụ thuộc resource output. |
| Sửa test source | `compileTestJava`, test-related tasks. |
| Sửa test resource | `processTestResources` và test tasks liên quan. |
| Thay dependency/version | Resolution và các task dùng classpath bị ảnh hưởng. |
| Thay compiler/toolchain | Compile tasks có thể cần tạo output mới. |
| Thay input của task custom | Task custom và downstream consumers cần cập nhật. |
| Xóa output file | Task sở hữu output cần chạy lại hoặc khôi phục từ cache. |

Không phải thay đổi nào cũng làm toàn bộ build chạy lại. Gradle cố gắng theo dõi quan hệ giữa inputs, outputs và task dependencies để chỉ thực hiện phần cần thiết.

## 10. Maven: clean build và build lặp lại

Maven có lifecycle phase và plugin goal. `clean` xóa output project, thường là `target/`; sau đó `verify` hoặc `package` thực hiện các phase cần thiết.

Build sạch:

```bash
./mvnw clean verify
```

Build tiếp theo không clean:

```bash
./mvnw verify
```

Lần chạy thứ hai có thể nhanh hơn nhờ plugin nhận biết output/source không cần xử lý lại, dependency đã được tải, JVM/process đã được chuẩn bị trong cùng invocation hoặc các cơ chế riêng của plugin. Nhưng không nên mặc định mọi Maven goal có up-to-date behavior giống Gradle.

### 10.1. Maven Compiler Plugin

Compiler plugin có thể kiểm tra source và class output để quyết định compile lại. Hành vi chi tiết phụ thuộc phiên bản plugin và cấu hình như incremental compilation, stale source detection hoặc compiler options.

Nếu thay đổi một compiler argument, annotation processor hoặc JDK mà plugin không nhận biết đầy đủ, output cũ có thể còn sót. Hãy kiểm tra cấu hình và thực hiện `clean` khi cần xác minh trạng thái đầy đủ.

### 10.2. Maven Resources Plugin

Resources plugin xử lý resource và filtering. Nếu property filtering thay đổi giữa hai invocation, plugin phải nhận được giá trị mới để cập nhật output. Nếu plugin hoặc build wrapper tùy chỉnh không phát hiện thay đổi property, có thể cần buộc xử lý lại hoặc clean trong quy trình.

### 10.3. Plugin incremental không phải cache tổng quát

Maven plugin có thể tự quản lý timestamp, marker hoặc file output. Điều đó không tương đương với một task-output cache chung có cache key đầy đủ và remote cache dùng chung như Gradle Build Cache.

Maven ecosystem có thể dùng extension hoặc plugin bổ sung để cung cấp caching, nhưng hành vi phụ thuộc thành phần được cài đặt. Khi so sánh, phải ghi rõ có extension/cache layer nào đang hoạt động.

## 11. Maven local repository và dependency cache

Maven local repository thường nằm ở `~/.m2/repository` (có thể đổi bằng cấu hình). Nó lưu artifact và metadata đã resolve/cài đặt.

Lệnh:

```bash
./mvnw clean verify
```

không xóa local repository. Vì vậy build sạch vẫn có thể dùng dependency đã tải trước đó.

Để kiểm tra phụ thuộc vào local repository, có thể dùng một local repository riêng:

```bash
./mvnw -Dmaven.repo.local=/tmp/m2-isolated clean verify
```

Đường dẫn trên là ví dụ cho môi trường Unix-like. Trên Windows, hãy chọn một thư mục tạm riêng phù hợp. Lần đầu có thể chậm vì phải tải dependency. Không nên dùng cách này như phép đo thường xuyên nếu mục tiêu không phải kiểm tra dependency resolution.

Maven local repository cũng có thể chứa artifact nội bộ được `install` từ source khác. Nếu build module bằng `-pl` mà không thêm upstream project vào reactor, Maven có thể resolve artifact đã cài trước đó. Đây là nguồn gây khác biệt giữa clean output và clean dependency environment.

## 12. So sánh ba kiểu build trong Maven

| Kiểu | Lệnh ví dụ | Điều thực sự được kiểm tra |
|---|---|---|
| Clean build | `./mvnw clean verify` | Tạo lại output project sau khi xóa `target/`. |
| Build không clean | `./mvnw verify` | Plugin xử lý trạng thái hiện có và quyết định phần cần thực hiện theo logic riêng. |
| Build với dependency cache ấm | `./mvnw verify` sau khi dependency đã tải | Giảm tải mạng/resolve artifact nhờ local repository; không phải task-output cache tổng quát. |
| Build với Maven caching extension | Tùy extension/cấu hình | Phải đọc tài liệu extension để biết key, output, phạm vi và giới hạn cache. |

Khi nói “Maven cached build”, hãy nói rõ đang chỉ dependency cache, plugin incremental state, daemon reuse qua `mvnd`, hay một caching extension. Nếu không, so sánh với Gradle `FROM-CACHE` sẽ không chính xác.

## 13. Thí nghiệm Maven: clean và non-clean

### Thí nghiệm A: build sạch

```bash
./mvnw clean verify
```

Ghi lại thời gian, số test và output trong `target/`. Xác nhận artifact và report được tạo.

### Thí nghiệm B: chạy lại không clean

```bash
./mvnw verify
```

Quan sát plugin log để biết goal nào xử lý lại và goal nào bỏ qua một phần công việc. Không chỉ dựa vào tổng thời gian để kết luận cache hit.

### Thí nghiệm C: build với local repository riêng

```bash
./mvnw -Dmaven.repo.local=/tmp/m2-isolated clean verify
```

So sánh với lần dùng local repository đã có dependency. Chênh lệch có thể chủ yếu đến từ tải dependency và repository access, không phải compile incremental.

### Thí nghiệm D: kiểm tra clean thật sự

Kiểm tra thư mục `target/` sau `clean`, rồi chạy lại build. Nếu một output cần thiết vẫn tồn tại bên ngoài `target/`, xác định nó đến từ workspace, plugin state hay một cache riêng.

## 14. Tại sao build cache có thể sai?

Cache tăng tốc build bằng cách tránh thực thi lại công việc, nhưng chỉ an toàn nếu build tool nhận diện đúng mọi yếu tố ảnh hưởng kết quả.

### 14.1. Hidden inputs

Task đọc environment variable, system property, file ngoài project, Git revision hoặc nội dung mạng nhưng không khai báo là input. Cache key không phản ánh thay đổi đó, nên output cũ có thể được dùng cho môi trường mới.

### 14.2. Output không được khai báo

Task ghi thêm file ngoài output directory đã khai báo. Cache restore có thể không khôi phục file đó, hoặc task state không mô tả đầy đủ kết quả.

### 14.3. Task không xác định

Task dùng timestamp, random value, thứ tự duyệt file không ổn định hoặc trạng thái máy local. Cùng inputs được khai báo nhưng output có thể khác nhau.

### 14.4. Side effects

Task publish, deploy hoặc cập nhật dịch vụ ngoài không phù hợp để cache như task tạo file thuần túy. Cache hit có thể bỏ qua hành động cần thực hiện.

### 14.5. Toolchain khác nhau

Nếu task không theo dõi đúng compiler/tool version hoặc arguments, output từ JDK/tool khác có thể được tái sử dụng sai.

Trước khi bật cache cho task custom, cần khai báo inputs/outputs đầy đủ, bảo đảm tính xác định và xác nhận cache hit tạo cùng kết quả mong đợi.

## 15. Cách thiết kế một phép so sánh công bằng

So sánh build sạch, incremental và cache chỉ có ý nghĩa khi kiểm soát các yếu tố khác.

### 15.1. Dùng cùng source revision

Mỗi lần đo phải dùng cùng commit hoặc cùng working tree snapshot. Nếu một lần đo có thêm source change, thời gian và task graph sẽ khác vì workload đã thay đổi.

Ghi nhận:

```bash
git rev-parse HEAD
git status --short
```

### 15.2. Dùng cùng toolchain

Giữ cố định:

- JDK chạy build và Java toolchain.
- Gradle/Maven Wrapper version.
- Plugin và extension versions.
- JVM arguments.
- OS/container image.
- CPU/RAM và worker limits.

Nếu một cấu hình thay đổi, ghi nhận nó như một biến của thí nghiệm.

### 15.3. Kiểm soát dependency cache

Nếu mục tiêu là đo task execution, nên giữ dependency cache ấm và ổn định để network không làm nhiễu. Nếu mục tiêu là đo cold dependency resolution, dùng cache riêng và ghi nhận tải mạng.

Không so sánh một build đã tải toàn bộ dependency với một build phải tải lại dependency rồi kết luận build cache nhanh hơn.

### 15.4. Phân biệt daemon cold/warm

Gradle Daemon và Maven Daemon có thể làm thay đổi startup time. Nếu đo build cache, hãy cố định trạng thái daemon hoặc đo riêng cold/warm. Không để một lần đo dùng daemon warm còn lần khác phải khởi động process mới mà không ghi nhận.

### 15.5. Chạy nhiều lần và dùng median

Một lần đo có thể bị ảnh hưởng bởi tải CPU, filesystem cache, network hoặc GC. Chạy nhiều lần trong điều kiện tương đương và so sánh median/percentile. Ghi lại cả lần đầu và các lần sau để thấy warm-up.

## 16. Ma trận thí nghiệm đề xuất

Một ma trận đơn giản cho Gradle:

| Trường hợp | Lệnh/điều kiện | Mục tiêu |
|---|---|---|
| A. Clean, cache off | `clean build --no-build-cache` | Đo tạo output từ đầu mà không dùng task-output cache. |
| B. Incremental, cache off | `build --no-build-cache` hai lần không đổi input | Quan sát `UP-TO-DATE`. |
| C. Incremental sau source change | Sửa một source rồi `build --no-build-cache` | Quan sát task bị ảnh hưởng. |
| D. Cache populate | `clean build --build-cache` | Tạo output và lưu cache entry. |
| E. Cache restore | `clean build --build-cache` lần nữa | Quan sát `FROM-CACHE`. |
| F. Cache off sau populate | `clean build --no-build-cache` | So sánh khi cache không được dùng. |

Ma trận Maven tương ứng:

| Trường hợp | Lệnh/điều kiện | Mục tiêu |
|---|---|---|
| A. Clean build | `clean verify` | Tạo lại output project. |
| B. Non-clean build | `verify` lần tiếp theo | Quan sát plugin incremental behavior. |
| C. Source change | Sửa source rồi `verify` | Xem compiler/plugin xử lý lại phần nào. |
| D. Dependency cache ấm | Chạy lại với local repo đã có dependency | Giảm network/download. |
| E. Dependency cache riêng | Chạy với local repository mới | Quan sát chi phí resolve/download. |
| F. Extension cache | Chỉ khi dự án có caching extension | Đo theo semantics riêng của extension. |

Không nên gọi trường hợp Maven D là “task output cache” nếu chỉ dùng local repository. Hãy đặt tên thí nghiệm đúng với cơ chế thực tế.

## 17. Đo thời gian và đọc kết quả

Tối thiểu nên ghi:

- Wall-clock duration của invocation.
- Thời gian configuration (nếu build tool cung cấp).
- Thời gian task/goal chính.
- Số task `SUCCESS`, `UP-TO-DATE`, `FROM-CACHE`, `SKIPPED`, `FAILED`.
- Số lượng test pass/fail/skip.
- Dependency downloads và network time.
- CPU, peak memory và số process.
- Cache hit/miss hoặc plugin incremental messages.

Ví dụ bảng ghi kết quả:

| Lần đo | Chế độ | Tổng thời gian | Task thực thi | Up-to-date | From-cache | Ghi chú |
|---|---|---:|---:|---:|---:|---|
| 1 | Clean, cache off | 120 s | 42 | 0 | 0 | Baseline tạo output. |
| 2 | Incremental | 18 s | 2 | 40 | 0 | Không đổi inputs. |
| 3 | Cache restore | 24 s | 0 | 0 | 42 | Output được khôi phục. |

Các con số chỉ minh họa cách trình bày, không phải benchmark cho Gradle/Maven. Thời gian thực tế phụ thuộc project, hardware, plugin, test và cache.

### 17.1. Đừng chỉ so sánh tổng thời gian

Một build nhanh hơn có thể vì test bị skip, task không được yêu cầu hoặc dependency đã nằm trong cache. Nếu không kiểm tra task outcomes và test reports, bạn có thể nhầm một build thiếu công việc với một build được tối ưu.

### 17.2. So sánh cả correctness

Thời gian thấp không có giá trị nếu output sai. Với mỗi chế độ, kiểm tra:

- Artifact tồn tại và có nội dung mong đợi.
- Manifest/resource/class đúng.
- Test thực sự được chạy hoặc kết quả được tái sử dụng theo chính sách rõ ràng.
- Digest hoặc normalized content phù hợp với baseline.
- Build không bỏ qua input quan trọng.

## 18. Khi nào dùng từng kiểu build?

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Developer sửa một vài file Java | Incremental build | Tránh compile/resource processing không bị ảnh hưởng. |
| Xác minh không phụ thuộc output cũ | Clean build | Tạo lại output project từ đầu. |
| CI build nhiều branch có task inputs giống nhau | Build cache | Có thể tái sử dụng task output từ cache chia sẻ. |
| Điều tra output stale | Clean build và incremental comparison | Phân biệt output cũ với input tracking sai. |
| Kiểm tra cache correctness | Cache off/on và restore thử nghiệm | Xác nhận cache entry tương ứng inputs. |
| Release candidate | Clean verification theo policy, có thể dùng cache đã tin cậy | Kiểm chứng đầy đủ mà vẫn tối ưu thời gian nếu cache đúng. |
| Kiểm tra dependency repository/network | Dependency cache riêng | Tách chi phí download khỏi task execution. |
| Điều tra plugin incremental behavior của Maven | So sánh `clean verify` với `verify` sau thay đổi | Xem plugin phát hiện source/property changes. |

Không có quy tắc rằng mọi release phải tắt mọi cache. Một cache đáng tin cậy có thể dùng trong CI release. Điều cần thiết là cache key đúng, writer đáng tin cậy, artifact được kiểm tra và có thể tái tạo khi cần.

## 19. Clean build không đồng nghĩa cold build

Các thuật ngữ sau cần được phân biệt:

- **Clean workspace output:** `build/` hoặc `target/` đã bị xóa.
- **Cold task cache:** không dùng task-output cache cho invocation.
- **Cold dependency cache:** dependency artifacts/metadata chưa có trong cache cục bộ.
- **Cold daemon:** chưa có daemon JVM phù hợp đang chạy.
- **Cold filesystem cache:** dữ liệu file chưa được giữ trong OS page cache; thường khó kiểm soát chính xác.

Một lệnh `clean build` có thể là clean workspace output nhưng warm ở bốn khía cạnh còn lại. Khi báo cáo benchmark, hãy nói rõ điều kiện thay vì chỉ ghi “cold build”.

### 19.1. Gradle: tạo điều kiện clean task execution

```bash
./gradlew --stop
./gradlew clean build --no-build-cache
```

Lệnh này dừng daemon trước, sau đó chạy build không dùng build cache task. Dependency cache vẫn có thể được dùng và invocation sẽ khởi động JVM mới.

### 19.2. Gradle: thử cache restore

```bash
./gradlew clean build --build-cache
./gradlew clean build --build-cache --info
```

Lần thứ hai có thể hiển thị `FROM-CACHE` cho task cacheable nếu inputs và task implementation khớp cache entry. Nếu không có cache hit, kiểm tra lý do thay vì giả định cache hỏng.

### 19.3. Maven: clean output nhưng giữ local repository

```bash
./mvnw clean verify
```

Đây là clean project output, dependency cache vẫn warm.

### 19.4. Maven: dùng local repository riêng

```bash
./mvnw -Dmaven.repo.local=/path/to/temp-m2 clean verify
```

Đây là cách tách local repository để kiểm tra dependency resolution. Nó không tương đương tắt một Maven task-output cache tổng quát.

## 20. Các lỗi thường gặp khi so sánh build

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `clean build` vẫn nhanh và có `FROM-CACHE` | `clean` không xóa Gradle build cache. | Dùng `--no-build-cache` nếu mục tiêu là không dùng task cache. |
| Build thứ hai không có `UP-TO-DATE` | Inputs thay đổi, outputs thiếu, task không khai báo outputs hoặc luôn chạy. | Xem `--info`, task inputs/outputs và plugin behavior. |
| Build cache bật nhưng không có `FROM-CACHE` | Task không cacheable, cache miss, inputs khác hoặc cache không được cấu hình. | Xác nhận task eligibility, cache config và key inputs. |
| Output cũ dù task `UP-TO-DATE` | Có hidden input hoặc output declaration sai. | Khai báo mọi input ảnh hưởng output và output task sở hữu. |
| Output sai sau cache restore | Task cacheability không an toàn hoặc cache key thiếu input. | Tạm tắt cache, sửa task model, kiểm tra cache writer và invalidation. |
| Maven `verify` vẫn chạy compiler | Plugin nhận thấy source/output thay đổi hoặc không có incremental skip. | Đọc log plugin và version/configuration; không mặc định đây là lỗi. |
| Maven clean build vẫn tải ít dependency | Local repository đã có artifact. | Dùng local repo riêng nếu đang đo cold dependency resolution. |
| Gradle build nhanh hơn nhưng test không chạy | Test task không nằm trong task graph hoặc bị skip. | Kiểm tra task graph và test report. |
| So sánh thời gian không ổn định | CPU/network/daemon/filesystem cache khác nhau. | Giữ môi trường cố định, lặp nhiều lần và dùng median. |
| Hai artifact khác digest | Timestamp, metadata, toolchain hoặc nội dung thực sự khác. | So sánh archive entries và nội dung đã chuẩn hóa. |

## 21. Tối ưu mà vẫn giữ correctness

Mục tiêu tối ưu là giảm công việc thừa mà không bỏ sót công việc cần thiết.

### 21.1. Khai báo task inputs/outputs đầy đủ

Đây là nền tảng cho up-to-date checking và build cache. Không dùng `@Internal`, bỏ qua environment hoặc hard-code file ngoài build model nếu chúng ảnh hưởng output.

### 21.2. Tách task theo trách nhiệm

Task compile, resource processing, code generation, packaging và publishing nên có inputs/outputs rõ ràng. Task quá lớn khó incremental; task quá nhỏ tạo overhead cấu hình/scheduling. Chia theo ranh giới công việc có ý nghĩa.

### 21.3. Chỉ cache task xác định

Task có side effect hoặc phụ thuộc trạng thái ngoài không nên được cache như task transform file. Với custom task, chỉ bật cache khi có thể tái sử dụng output an toàn.

### 21.4. Quản lý dependency version

Dynamic versions hoặc snapshot thay đổi có thể làm kết quả khác giữa các lần build. Dùng version cố định, dependency locking/constraints và repository policy phù hợp cho build release.

### 21.5. Giữ test và verification trong task graph

Không đánh đổi tốc độ bằng cách bỏ test bắt buộc. Nếu CI dùng cache cho test, phải xác nhận các inputs test được theo dõi và test không phụ thuộc trạng thái bên ngoài không được mô hình hóa.

## 22. Build cache trong CI

Build cache đặc biệt hữu ích khi nhiều CI job xây cùng project hoặc các branch có nhiều task inputs giống nhau. Một remote cache có thể cho phép job sau lấy output đã tạo bởi job trước.

### 22.1. Phân quyền cache writer và reader

Một mô hình thường dùng:

- Trusted main/release build có thể ghi cache.
- Pull request từ fork hoặc source không tin cậy chỉ được đọc cache công khai/được phép, không ghi vào cache dùng chung có độ tin cậy cao.
- Cache namespace và retention được quản lý theo tổ chức.

Điều này giảm nguy cơ build không tin cậy ghi output vào cache mà release build sau đó tái sử dụng.

### 22.2. Cache hit không thay thế release verification

Cache có thể giúp compile/test nhanh hơn, nhưng release vẫn cần các gate bắt buộc và kiểm tra artifact được tạo/publish đúng. Cache không chứng minh artifact đã được ký, publish hoặc kiểm tra bởi workflow được phép.

### 22.3. Cache key và toolchain

Nếu compiler version, plugin implementation, dependency classpath hoặc build parameters thay đổi, cache key cần phản ánh thay đổi đó. Gradle task chuẩn và task cacheable đúng cách xử lý nhiều yếu tố này; custom task phải khai báo đầy đủ.

## 23. Kết hợp các chế độ trong quy trình phát triển

Một workflow thực tế có thể dùng các chế độ khác nhau theo mục tiêu:

```text
Developer chỉnh sửa code
    -> incremental build để phản hồi nhanh

Pull request CI
    -> build cache để tái sử dụng task output phù hợp
    -> chạy các test/verification bắt buộc

Nightly hoặc release rehearsal
    -> clean verification để phát hiện phụ thuộc output cũ
    -> có thể dùng cache đã tin cậy nếu policy cho phép

Điều tra stale output/cache issue
    -> clean + cache off
    -> incremental run sau từng thay đổi input
    -> cache populate/restore có kiểm soát
```

Đây là một cách tổ chức gợi ý. Project cần xác định rõ mức độ xác minh, thời gian CI và trust boundary của cache.

## 24. Checklist quan sát khi chạy từng kiểu build

### Clean build

- Output project đã được xóa đúng phạm vi chưa?
- Build có tái tạo đủ class, resource, report và artifact không?
- Có phụ thuộc vào file generated nằm ngoài output directory không?
- Có dùng build cache hoặc dependency cache mà chưa ghi nhận không?
- Test bắt buộc có thực sự chạy không?

### Incremental build

- Task nào `UP-TO-DATE` và vì sao?
- Khi sửa source/resource/configuration, task liên quan có chạy lại không?
- Khi thêm/xóa file trong input directory, task có nhận biết không?
- Task custom có khai báo đủ inputs/outputs không?
- Có hidden input hoặc shared state không?

### Cached build

- Task nào `FROM-CACHE`?
- Cache là local hay remote?
- Cache key có phản ánh toolchain và mọi input không?
- Cache writer có đáng tin cậy không?
- Output sau restore có đúng với output thực thi mới không?
- Task có side effect nào bị bỏ qua khi cache hit không?

## 25. Ví dụ thực hành: so sánh ba kiểu build Gradle

Trong một project Java nhỏ có Wrapper, thực hiện theo thứ tự sau và ghi lại task outcomes:

1. Chạy `./gradlew --stop` nếu muốn bắt đầu với daemon cold.
2. Chạy `./gradlew clean build --no-build-cache --info` và lưu thời gian/output.
3. Chạy lại `./gradlew build --no-build-cache --info`; quan sát task `UP-TO-DATE`.
4. Sửa một Java source file, chạy lại lệnh trên và quan sát task bị ảnh hưởng.
5. Bật build cache bằng `./gradlew clean build --build-cache --info`.
6. Chạy lại `./gradlew clean build --build-cache --info` và tìm task `FROM-CACHE`.
7. Chạy `./gradlew clean build --no-build-cache` để so sánh khi cache task bị tắt.
8. Kiểm tra artifact, test report và nội dung JAR ở mỗi trường hợp.
9. Nếu có task custom, thay đổi một input đã khai báo và một biến môi trường được task sử dụng; xác nhận task phản ứng đúng.
10. Ghi lại daemon state, dependency cache và toolchain để tránh nhầm nguyên nhân tăng tốc.

## 26. Ví dụ thực hành: so sánh Maven clean và incremental

Trong project Maven có Wrapper:

1. Chạy `./mvnw clean verify` và lưu log/test report.
2. Chạy lại `./mvnw verify` trong cùng workspace.
3. Sửa một Java source file rồi chạy `./mvnw verify`.
4. Sửa một resource được filtering và thay property tương ứng; xác nhận resource output được cập nhật.
5. Chạy `./mvnw -Dmaven.repo.local=/path/to/temp-m2 clean verify` để quan sát chi phí dependency resolution với repository riêng.
6. Đọc log của compiler/resources/test plugins để xác định chúng thực thi hay bỏ qua công việc.
7. Nếu dự án dùng caching extension, thực hiện thí nghiệm riêng theo tài liệu extension và ghi rõ cache nào được dùng.
8. So sánh test count, artifact inventory và nội dung output giữa các lần chạy.

## 27. Những hiểu nhầm thường gặp

### “Clean build nghĩa là xóa mọi cache”

Không. `clean` thường xóa output của project. Gradle build cache, dependency cache, Maven local repository và daemon có thể vẫn còn.

### “Build thứ hai nhanh hơn nghĩa là task cache hit”

Không. Có thể task được `UP-TO-DATE`, dependency đã tải, daemon đã warm hoặc filesystem cache hoạt động. Cần đọc task outcomes và log.

### “`UP-TO-DATE` và `FROM-CACHE` giống nhau”

Không. `UP-TO-DATE` dùng output hiện có trong workspace; `FROM-CACHE` lấy output từ build cache.

### “`--no-build-cache` buộc mọi task chạy lại”

Không. Nó tắt build cache task cho invocation, nhưng up-to-date checking vẫn có thể bỏ qua task có output hiện tại hợp lệ.

### “Maven `verify` lần hai tương đương Gradle `FROM-CACHE`”

Không. Maven plugin có thể có incremental logic, nhưng không nên mặc định đó là task-output cache tổng quát.

### “Build cache luôn làm build nhanh hơn”

Không. Cache lookup, serialization, network và restore output cũng có chi phí. Task rất nhanh hoặc cache entry lớn có thể không có lợi.

### “Có thể cache mọi task”

Không. Task có side effect hoặc hidden input có thể tạo kết quả sai nếu tái sử dụng output.

### “Build nhanh nhất là build tốt nhất”

Không. Build cần tạo đúng artifact và thực hiện đúng verification gates. Tốc độ chỉ có ý nghĩa khi correctness được giữ.

## 28. Kết luận

Build sạch xóa output project trước khi tạo lại; build tăng dần tận dụng output hiện có và chỉ thực hiện lại phần bị ảnh hưởng; build dùng cache tái sử dụng output đã lưu cho đúng inputs. Với Gradle, cần phân biệt `UP-TO-DATE` với `FROM-CACHE`, đồng thời tách build cache khỏi configuration cache, dependency cache và daemon. Với Maven, `clean` xóa `target/`, còn lần chạy không clean phụ thuộc vào incremental behavior của từng plugin; Maven local repository chỉ là dependency cache và không phải task-output cache tổng quát.

Để so sánh công bằng, giữ cùng source revision, toolchain, dependency state, daemon condition và test scope; đo nhiều lần, đọc task/plugin outcomes và kiểm tra artifact/report. Dùng clean build để xác nhận khả năng tái tạo, incremental build để kiểm tra phát hiện thay đổi và build cache để xác minh khả năng tái sử dụng an toàn. Một build chỉ được coi là tối ưu khi nhanh hơn mà vẫn tạo đúng output và giữ đủ các bước kiểm chứng cần thiết.
