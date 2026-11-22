# Phân biệt dependency cache, build cache và configuration cache trong Gradle

## 1. Mục tiêu: hiểu đúng ba câu hỏi mà Gradle cache giải quyết

Khi build một dự án Java bằng Gradle, từ “cache” có thể chỉ **ba cơ chế khác nhau**. Chúng có thể cùng hoạt động trong một lần chạy nhưng lưu **các loại dữ liệu khác nhau**, có điều kiện hit/miss khác nhau và không được “sửa” bằng cùng một câu lệnh.

- **Dependency cache:** “Các metadata và artifact JAR mà build cần lấy từ repositories đã tải/resolve ở lần trước chưa?” Nó giảm download và network round trips khi giải quyết phụ thuộc.
- **Build cache:** “Với cùng inputs, Gradle đã từng tạo **task outputs** này ở một build nào trước đây chưa?” Nó có thể **khôi phục kết quả** thay vì chạy lại task tốn thời gian.
- **Configuration cache:** “Với cùng task request và các configuration inputs tương ứng, Gradle có thể dùng lại **task graph cùng cấu hình** đã tính toán ở lần build trước không?” Nó giảm chi phí **configuration phase**.

Ba lớp giải quyết ba loại công việc khác nhau:

```text
1. Resolve dependencies       -> Dependency cache (metadata/artifacts)
2. Configure build/task graph -> Configuration cache (configured graph/state)
3. Execute/cache task outputs -> Up-to-date checks + Build cache
```

Sơ đồ trên là **mô hình học tập**; trong build thật dependency resolution có thể xảy ra trong configuration hoặc execution tùy API, và configuration cache có thể lưu cả resolved dependency state. Không coi ba bước là một thứ tự cứng tuyệt đối cho mọi Gradle build.

**Bài học này thuộc Build Tool Gradle → Các lớp cache**. Bạn sẽ biết cách dùng ba cache, nhận diện hit/miss từ log, hiểu `UP-TO-DATE` khác `FROM-CACHE`, thiết lập build cache local/remote, phân tích `--offline` và `--refresh-dependencies`, cũng như thử một lab Java 17+ với Groovy DSL và custom `@CacheableTask`.

## 2. Bảng so sánh trong một phút

| Tiêu chí | Dependency cache | Build cache | Configuration cache |
| --- | --- | --- | --- |
| Lưu gì? | Metadata module/version, artifact files và kết quả resolution để tái dùng khi cần. | **Task/artifact transform outputs** được tính từ inputs và implementation. | **Configured task graph/state**, task dependencies, task properties và resolved configurations. |
| Trả lời câu hỏi | “Tôi có cần tải lại thư viện?” | “Tôi có cần chạy lại công việc này?” | “Tôi có cần cấu hình lại build?” |
| Đơn vị chính | Module coordinates, repository identity, metadata/artifacts. | Task output cache key (implementation, inputs, outputs...). | Cache entry cho **task requests** và các configuration inputs. |
| Bật mặc định? | **Có**, Gradle tự cache dependencies. | **Chưa bật mặc định** trong tài liệu Gradle 9.9; bật bằng flag/property. | **Chưa bật mặc định** trong tài liệu Gradle 9.9; bật bằng flag/property. |
| Bật nhanh | Không cần flag riêng. | `--build-cache`. | `--configuration-cache`. |
| Bật thường xuyên | Cấu hình TTL/repository policy khi cần. | `org.gradle.caching=true`. | `org.gradle.configuration-cache=true`. |
| Vị trí phổ biến | `$GRADLE_USER_HOME/caches/modules-2/`. | Local build cache trong `$GRADLE_USER_HOME/caches/` hoặc custom directory; có thể thêm **remote build cache**. | `<root-build>/.gradle/configuration-cache/`. |
| Có thể chia sẻ giữa agents? | Có thể dùng cơ chế dependency cache được cấp phát/copy an toàn; cần chú ý locking/repository provenance. | **Có**, qua remote build cache được cấu hình. | **Không chia sẻ giữa máy** theo tài liệu hiện tại; thường là state cục bộ của build. |
| Biểu hiện | Bớt HTTP/download; `--offline` resolve được khi artifact đã có. | `FROM-CACHE` trên task cacheable. | Log dạng “configuration cache entry stored/reused”; configuration phase có thể được bỏ qua. |
| Khi nguồn Java đổi | Không nhất thiết tải lại thư viện. | Relevant task cache key/input thay đổi → execute hoặc cache hit với output phù hợp. | Có thể vẫn reuse configuration nếu source file chỉ là **task input**, không phải config input. |
| Khi build.gradle đổi | Dependency graph có thể đổi cần resolve. | Build logic/task implementation hoặc task inputs có thể đổi key. | Thường invalidated do configuration input đổi. |

**Chốt phân biệt:** file `commons-lang3-3.17.0.jar` trong dependency cache **không phải** output `CacheDemo.class` của `compileJava`. Tương tự, cache entry của task `compileJava` không thể thay cho việc Gradle biết **task nào** phải chạy và task đã cấu hình thế nào.

## 3. Gradle build lifecycle và cache nằm ở giai đoạn nào?

Gradle chia lifecycle thành **initialization → configuration → execution**.

1. **Initialization:** đọc settings, tạo project hierarchy và xử lý settings plugins/build boundaries.
2. **Configuration:** đánh giá build scripts/plugins, cấu hình tasks và task graph. Trong quá trình này hoặc khi Gradle cần artifact classpath, dependency resolution có thể diễn ra.
3. **Execution:** kiểm tra task inputs/outputs, bỏ qua tasks không cần thiết, tải output từ build cache nếu phù hợp hoặc chạy actions thực.

Đường xử lý khái quát:

```text
Start Gradle invocation
         |
         v
Read settings / build environment
         |
         v
Has reusable configuration cache entry?
       /   \
     Yes    No
      |      |
      |      +--> Configure projects/tasks and store entry
      |                  |
      +------------------+
         |
         v
Scheduled task graph
         |
         v
For each relevant task:
  - no work / NO-SOURCE / skipped?
  - local outputs valid? -> UP-TO-DATE
  - outputs missing and cacheable, key hit? -> FROM-CACHE
  - otherwise execute task action -> SUCCESS / FAILED
         |
         v
Build result
```

Đây là flow giản lược: Gradle có thêm validation, incremental execution, artifact transforms, work avoidance và parallel execution. **Dependency cache không tự là một nhánh “FROM-CACHE”**: dependency download có thể được tránh dù task `compileJava` vẫn chạy thật.

### 3.1. Cache hit không có nghĩa “toàn bộ build không làm gì”

Ví dụ cùng lúc có thể xảy ra:

- Configuration cache **REUSED**: Gradle không phải evaluate lại `build.gradle` theo cách thông thường.
- Dependency cache **HIT**: external JAR đã có; không cần download lại.
- `:compileJava UP-TO-DATE`: bytecode tồn tại trong workspace và các inputs/outputs không đổi.
- `:test FROM-CACHE`: output của một task cacheable khác được khôi phục.
- `:run` vẫn **EXECUTES**: ứng dụng cần chạy để in stdout.

Vì thế câu “Gradle cache rồi, tại sao vẫn có task chạy?” không đủ để chẩn đoán. Cần nêu đúng **lớp cache, task, input và outcome**.

## 4. Dependency cache — cache thư viện và kết quả resolution

### 4.1. Bên trong dependency cache có gì?

Khi một dự án khai báo:

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Gradle cần xác định module `org.apache.commons:commons-lang3:3.17.0`, metadata (POM/Gradle module metadata nếu có), graph dependencies/variants và artifact thích hợp. Cache lưu thông tin để lần sau không phải lặp lại mọi network request và download.

Vị trí thường là:

```text
~/.gradle/caches/modules-2/
    files-2.1/
        org.apache.commons/
            commons-lang3/
                3.17.0/
                    ...
    metadata-.../
        ...
```

Cấu trúc nội bộ, tên thư mục metadata/hash và vị trí chính xác có thể đổi theo Gradle release. Không hardcode `files-2.1` path vào build script hoặc Java application; để Gradle resolve dependency rồi cung cấp classpath.

**Gradle User Home** mặc định là `~/.gradle` trên Unix và thư mục `.gradle` trong user profile trên Windows, trừ khi có `GRADLE_USER_HOME` hoặc `-g`/thiết lập tương ứng. **Đừng nhầm Gradle User Home với root project `.gradle/`**: hai nơi phục vụ mục đích khác.

### 4.2. Cache có metadata và artifacts — không phải chỉ một tập JAR

Gradle có thể đã tải POM/module metadata và dựng graph, nhưng chưa cần JAR bytecode cho task hiện tại. Ví dụ:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Lệnh này giúp thấy dependency graph, **không bảo đảm tất cả binary artifacts đã được tải**. Ngược lại, `compileJava` cần compiler classpath và thường khiến JAR liên quan được resolve/tải. Khi làm bài thực hành `--offline`, hãy **warm** một task thật dùng artifact đó.

### 4.3. Thư viện version cố định vs version động

Có ba trường hợp:

| Khai báo | Đặc điểm |
| --- | --- |
| `implementation 'org.apache.commons:commons-lang3:3.17.0'` | Version cố định. Gradle tái dùng cache nếu dữ liệu phù hợp và không cần revalidation. |
| `implementation 'com.example:library:2.+'` | **Dynamic version**: Gradle cần biết version nào hiện match `2.+`, thường cache kết quả chọn version với TTL. |
| `implementation 'com.example:library:1.0-SNAPSHOT'` | **Changing module**: metadata/artifact có thể đổi dù coordinate không đổi, cần recheck theo TTL/changing status. |

Mặc định Gradle cache **dynamic version selection** và **changing modules** trong khoảng **24 giờ** theo tài liệu dependency caching hiện hành. Có thể điều chỉnh độc lập trong **Groovy DSL**:

```groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
    resolutionStrategy.cacheChangingModulesFor 4, 'hours'
}
```

Đây là **cấu hình tùy chọn**, không có trong lab baseline. Hãy chọn TTL theo yêu cầu và repository policy; TTL quá ngắn khiến builds liên tục check remote, TTL quá dài dễ giữ snapshot/version selection cũ.

Để tự khai báo một module “được publish lại cùng version” là changing:

```groovy
dependencies {
    implementation('com.example:custom-lib:1.0.0') {
        changing = true
    }
}
```

Đây là **fragment minh họa** dùng module giả `com.example:custom-lib`, không chạy riêng được nếu kho không có artifact đó. Với release libraries, nên tránh republish cùng coordinate, sử dụng immutable versions và dependency locking/verification khi cần reproducibility.

### 4.4. Repository identity và nguồn tải

Gradle ghi nhận artifact cùng repository/metadata provenance: các repositories có thể phục vụ bytes khác nhau cho cùng group:name:version. Cache không phải một danh sách file được dùng tùy tiện giữa mọi repository.

Các hệ quả:

- Nếu đổi `mavenCentral()` sang private repository hoặc thứ tự/filter repositories, Gradle có thể cần query lại và không dùng artifact cached từ nguồn khác theo cách bạn kỳ vọng.
- Một private artifact đã cache trên máy A không có nghĩa máy B, dùng repository policy khác, sẽ resolve được trong `--offline`.
- Đừng copy một thư mục JAR từ dependency cache rồi cho consumer tự tham chiếu bằng absolute path; việc đó bỏ qua metadata/variant/security policy và dễ hỏng khi Gradle dọn cache.
- Với CI, dùng artifact repository proxy/mirror được kiểm soát, dependency locking/verification và cache policy rõ ràng.

### 4.5. Lệnh --offline: dùng cache hiện có, không tự tạo artifacts

```bash
./gradlew compileJava --offline --console=plain
```

`--offline` yêu cầu Gradle dependency resolution **không truy cập remote repositories** mà dựa vào những gì đã cache. Nó hữu ích khi ngắt mạng hoặc muốn phát hiện dependencies chưa được chuẩn bị.

Nếu thiếu artifact/metadata cần thiết, build **fail**, dù source Java không đổi. Điều đó **không chứng minh build cache hay configuration cache bị hỏng**.

**Giới hạn quan trọng:** nếu Gradle Wrapper distribution chưa có, chính Wrapper có thể cần tải Gradle trước khi `--offline` được Gradle xử lý. Một custom Gradle task tự gọi HTTP cũng không nhất thiết bị chặn chỉ bởi `--offline`; flag này không phải firewall cho mọi process.

### 4.6. Lệnh --refresh-dependencies: refresh resolution, không xóa mọi cache

```bash
./gradlew compileJava --refresh-dependencies --console=plain
```

Gradle recheck metadata/artifacts qua repositories và recompute dynamic/changing selections phù hợp. Nó **không bắt buộc tải lại mọi bytes**: có thể dùng HTTP HEAD/checksum hoặc cache content nếu server cho biết artifact không đổi.

**Không đồng nhất**:

- `--refresh-dependencies` ≠ `clean`.
- `--refresh-dependencies` ≠ xóa `$GRADLE_USER_HOME/caches`.
- `--refresh-dependencies` ≠ `--rerun-tasks`.
- `--refresh-dependencies` không có nghĩa build cache/task outputs hoặc configuration cache đều bị xóa.

Nếu mục tiêu là quan sát **chính dependency resolution** khi configuration cache đã bật, bạn có thể chạy tách bạch:

```bash
./gradlew compileJava --no-configuration-cache --refresh-dependencies --console=plain
```

Cú pháp này cô lập thí nghiệm khỏi việc reuse configured task graph; nó **không mặc định cần thiết trong mọi dự án**. Khi build thực có configuration cache, Gradle có thể lưu resolved dependency state và thay đổi cách/điểm thực hiện resolution; hãy đọc logs đúng chế độ.

### 4.7. Dependency cache và bảo mật

Dependency cache là **bộ nhớ hiệu năng**, không phải bộ chứng nhận artifact đáng tin. Để giảm rủi ro supply-chain:

- Dùng HTTPS repositories được quản trị; hạn chế repositories thừa, tránh HTTP fallback.
- Pin release versions, hạn chế dynamic versions/changing modules trong CI phát hành.
- Áp dụng **dependency verification** (checksums/signatures theo policy), dependency locking và repository content filters khi phù hợp.
- Không sửa binary cached JAR bằng tay hoặc tắt verification chỉ để “cache hit”.
- Không xóa toàn bộ Gradle User Home khi chỉ một dependency thiếu; xác định coordinate, repository, credentials và lỗi network trước.

## 5. Build cache — cache task outputs, không phải thư viện

### 5.1. Khi nào task output được tái sử dụng?

Gradle có thể biết một task đã từng nhận **cùng inputs và cùng implementation**, và output của task cacheable đã được lưu. Khi output workspace không còn, Gradle lấy bản lưu từ build cache thay vì chạy lại công việc.

Ví dụ với `compileJava`:

```text
src/main/java/example/CacheDemo.java
                  |
                  v
             :compileJava
                  |
                  v
    build/classes/java/main/example/CacheDemo.class
```

Dependency JAR như Commons Lang là **input classpath** cho compilation. Bytecode `CacheDemo.class` là **task output**. Build cache giúp tái sử dụng bytecode đầu ra nếu cache key khớp; nó không thay Maven Central hoặc dependency resolution.

### 5.2. Bật build cache

Chỉ cho một invocation:

```bash
./gradlew compileJava --build-cache --console=plain
```

Hoặc trong `gradle.properties` của project/user:

```properties
org.gradle.caching=true
```

Tắt cho một invocation:

```bash
./gradlew compileJava --no-build-cache --console=plain
```

**Theo tài liệu Gradle 9.9**, build cache **chưa bật mặc định**. Việc local build cache directory đã được cấu hình mặc định **không đồng nghĩa chế độ task output caching đang bật**. Build cache có thể được bật qua CLI hoặc property mà không cần thiết lập remote server.

### 5.3. Cache key gồm những thông tin nào?

Một cacheable task có cache key chịu ảnh hưởng từ:

- Implementation/task action classpath, bao gồm code plugin/build logic liên quan.
- Names/values của **declared task input properties**.
- Input files, normalized paths và file contents theo annotations.
- Names của declared output properties và các yếu tố cần thiết để outputs có thể được tái sử dụng an toàn.
- Những yếu tố trong Gradle input snapshotting/caching rules.

**Không** nghĩ đơn giản rằng cache key chỉ là hash của Java source. Đổi compiler/toolchain, options, plugin implementation, relevant classpath hoặc generated inputs có thể tạo key khác. Task path không phải input trực tiếp vào cache key theo thiết kế, giúp outputs có thể được chia sẻ giữa tasks phù hợp, nhưng cacheability/relocatability và normalization mới quyết định kết quả thực.

Để tái sử dụng output an toàn, task phải:

1. Tạo outputs **deterministic** từ declared inputs.
2. Khai báo đủ inputs (`@Input`, `@InputFiles`, `@Classpath`...) và outputs (`@OutputFile`, `@OutputDirectory`...).
3. Không có hidden inputs như current time/random/environment không được mô hình hóa.
4. Không tạo side effects quan trọng ngoài outputs đã khai báo.
5. Cho phép Gradle xác định task thực sự **cacheable**.

### 5.4. @CacheableTask và built-in tasks

**Không phải mọi task đều cacheable.** Một custom task type thường phải opt in bằng `@CacheableTask` và khai báo inputs/outputs phù hợp. Gradle có các built-in tasks hỗ trợ cache như `JavaCompile`, `Test`, `Javadoc`, `ValidatePlugins` và một số artifact transforms.

Ngược lại, `Copy`/`Jar` thường không nên cache như task tiêu tốn tính toán lớn: việc copy/repack có thể nhanh, và không có nghĩa mọi task loại đó mặc định đọc/ghi build cache.

Một task chỉ ghi console như:

```groovy
tasks.register('sayHi') {
    doLast {
        println 'Hi'
    }
}
```

không có file output được khai báo. **Không nên** giả định `--build-cache` làm task này được cache hay có `FROM-CACHE`.

### 5.5. UP-TO-DATE khác FROM-CACHE

Đây là điểm người học phải phân biệt:

| Gradle outcome | Ý nghĩa |
| --- | --- |
| `SUCCESS` (hoặc task không có label) | Task actions đã thực thi thành công. |
| `UP-TO-DATE` | Workspace hiện có outputs và snapshot inputs/outputs khớp; **không cần thực thi lại**. |
| `FROM-CACHE` | Task outputs được **khôi phục từ build cache** với matching cache key. |
| `NO-SOURCE` | Task có loại source processing nhưng không có source cần xử lý. |
| `SKIPPED` | Task skip do enabled/onlyIf/skip reason. |
| `FAILED` | Task execution không thành công. |

`UP-TO-DATE` **không chứng minh** build cache đang bật: Gradle kiểm tra up-to-date ngay cả khi `--no-build-cache`. `FROM-CACHE` **không có nghĩa** Gradle vừa lấy Maven dependency từ Internet; đó là một task-output restoration.

Nếu workspace đã có output và được xem là up-to-date, Gradle thường **không cần hỏi build cache** cho task đó. Muốn minh họa `FROM-CACHE` cần loại bỏ local output (như `clean`) mà vẫn **giữ build cache**.

### 5.6. Local vs remote build cache

Build cache có:

- **Local cache:** trên máy hiện tại (mặc định nằm trong Gradle User Home). Một Gradle invocation có thể lấy output của build trước cùng máy, kể cả sau `clean`.
- **Remote cache:** HTTP/cache service nội bộ hoặc backend tương thích, có thể chia sẻ cacheable outputs giữa dev/CI machines. Tổ chức thường cho CI **push**, dev **pull only** để hạn chế artifacts không tin cậy.

Khi cả hai cache hoạt động, Gradle ưu tiên tìm local rồi remote; nếu load từ remote, bản đó có thể được lưu local cho lần sau. **Remote cache chỉ hoạt động khi được cấu hình**, không xuất hiện chỉ vì bật `--build-cache`.

### 5.7. Cấu hình local/remote cache bằng settings.gradle

Ví dụ **local-only**:

```groovy
buildCache {
    local {
        enabled = true
        push = true
    }
}
```

Đây là fragment trong `settings.gradle`, dùng khi muốn kiểm soát local cache. Vẫn cần `--build-cache` hoặc `org.gradle.caching=true` để Gradle thật sự bật task output caching.

Ví dụ **remote-only-as-addition** (host minh họa, cần endpoint hợp lệ mới dùng được):

```groovy
buildCache {
    local {
        enabled = true
        push = true
    }
    remote(HttpBuildCache) {
        url = 'https://cache.example.org/cache/'
        push = false
    }
}
```

Fragment này **thay thế** fragment local-only nếu cần remote, không dán cả hai. `https://cache.example.org/cache/` là URL minh họa, **không phải server đang tồn tại được bảo đảm**. Nếu cache riêng yêu cầu authentication, lấy credentials qua Gradle Provider/secrets; không viết plaintext token vào Git. Không tắt certificate validation hoặc dùng HTTP không an toàn để “làm cho cache hoạt động”.

**Phân biệt quyền đọc/ghi**: `enabled` điều khiển liệu cache backend được dùng để đọc; `push` điều khiển có ghi outputs lên backend hay không. Remote cache theo chính sách doanh nghiệp thường `push = false` trên developer machines.

## 6. Configuration cache — cache cấu hình và task graph

### 6.1. Build config có thể rất tốn kém

Mỗi khi chạy `./gradlew test`, Gradle thường đọc settings/build scripts, load plugins, cấu hình projects/tasks, tạo task graph và có thể resolve một phần dependencies. Với hàng trăm modules/convention plugins, phần này có thể tốn nhiều thời gian ngay cả khi mọi task đều `UP-TO-DATE`.

**Configuration cache** lưu **configured task graph và state** để lần sau có cùng task requests/configuration inputs thì Gradle có thể **bỏ qua configuration phase** và restore task graph trực tiếp.

Cách bật cho một lần:

```bash
./gradlew help --configuration-cache --console=plain
```

Cách bật lâu dài trong `gradle.properties`:

```properties
org.gradle.configuration-cache=true
```

Tắt cho invocation cần debug:

```bash
./gradlew help --no-configuration-cache --console=plain
```

Theo tài liệu Gradle **9.9**, configuration cache chưa bật mặc định; nó được định hướng trở thành mặc định ở Gradle 10. Khi dùng một bản Gradle khác trong tương lai, cần kiểm tra chính tài liệu của bản đó.

### 6.2. Configuration cache lưu gì?

Một cache entry bao gồm:

- Tập tasks được chọn và quan hệ task dependencies.
- Task configuration state (inputs, outputs, properties/serialized state).
- Các resolved configurations, artifact metadata và classpath state phù hợp cần cho graph đó.
- Thông tin về **configuration inputs** để kiểm tra entry còn dùng lại được không.

Nó **không lưu toàn bộ results của compile/test tasks để thay build cache**, cũng không chứa một bản sao thư viện Maven Central như dependency cache.

**Vị trí** thông thường:

```text
<root-build>/
└── .gradle/
    └── configuration-cache/
        ...
```

Đây là **project-local state**, không phải directory `$GRADLE_USER_HOME/caches/modules-2` hay remote build cache. Configuration cache hiện không được chia sẻ đơn giản giữa developers/CI machines như HTTP remote build cache. Một số cơ chế phục hồi cache trong CI có thể hỗ trợ đưa state trở lại máy phù hợp theo tài liệu riêng, nhưng không suy ra nó là network service theo giao thức build cache.

### 6.3. Miss/store/reuse

Chạy cùng task request hai lần:

```bash
./gradlew help --configuration-cache --console=plain
./gradlew help --configuration-cache --console=plain
```

Trong điều kiện settings/plugins/environment không đổi và build tương thích:

- Lần đầu là **miss**, Gradle cấu hình build rồi **store** cache entry.
- Lần sau là **hit**, Gradle **reuse** entry, configuration phase được bỏ qua.

Các log thường có thông điệp dạng “Configuration cache entry stored” hoặc “Configuration cache entry reused”; câu chữ có thể thay đổi theo Gradle version, warning mode và console settings. Đừng nhầm message này với outcome `FROM-CACHE` ở task.

### 6.4. Khi nào configuration cache invalidated?

Cache entry cần được cấu hình lại nếu **configuration inputs** mà Gradle theo dõi thay đổi, chẳng hạn:

- `settings.gradle`, `build.gradle`, applied scripts hoặc build logic/plugin classpath đổi.
- Relevant Gradle properties, system properties và environment variables được đọc lúc cấu hình thay đổi.
- Files external được đọc ở configuration phase (và được Gradle track) thay đổi.
- Task request hoặc build configuration parameters ảnh hưởng graph khác.
- Một số Gradle/CI/environment changes khiến cache key/state không còn tương thích.

**Không phải cứ thay một `.java` source file là configuration cache phải invalidated**. Nếu Java source chỉ là `@InputFiles` cho `compileJava`, Gradle có thể reuse configuration cache rồi riêng compileJava bị out-of-date.

**Tại sao phải cẩn thận với configuration inputs?** Nếu plugin đọc network/process một cách không track được trong configuration phase, Gradle có thể reuse stale state. Với build logic hiện đại, dùng `ProviderFactory`, `ValueSource` hoặc file content providers phù hợp thay vì đọc dữ liệu động tùy tiện.

### 6.5. Configuration cache và dependency resolution giao nhau thế nào?

Gradle hiện có thể cache **resolved dependency state** như một phần configuration entry. Khi hit, resolved configurations/files/metadata được khôi phục thay vì resolve lại graph. Điều này **không biến configuration cache thành dependency cache**: JAR bytes vẫn được quản lý theo dependency artifact cache, và Gradle vẫn phải bảo đảm cache entry/configuration inputs phù hợp.

Một ví dụ dễ nhầm:

- Lần đầu cấu hình `compileJava` và resolve Commons Lang.
- Lần sau configuration cache hit: không phải đánh giá lại toàn bộ dependencies như một graph mới.
- Nếu bạn muốn chủ động kiểm tra Maven repository sau thay đổi dependency graph hoặc TTL, dùng chế độ tường minh thích hợp và đọc log resolution; đừng suy đoán chỉ từ chữ “reused”.

### 6.6. Yêu cầu compatibility đối với build logic

Configuration cache đặt các ràng buộc rõ lên task implementations:

**Sai về mô hình:**

```groovy
// PHẢN VÍ DỤ: task action truy cập Project object.
tasks.register('badTask') {
    doLast {
        println project.version
    }
}
```

Trong task action, `project.version` truy cập live Gradle Project model và có thể gây configuration cache problem. Cách tốt hơn là chốt value immutable tại configuration và dùng managed task inputs:

```groovy
def releaseVersion = version.toString()
tasks.register('showVersion') {
    def snapshot = releaseVersion
    doLast {
        println snapshot
    }
}
```

**Đoạn này chỉ minh họa tránh đọc Project lúc execution**; trong plugin production nên định nghĩa typed `@Input Property<String>` như custom task lab bên dưới. Không giữ `Project`, `Gradle`, `Settings`, `Configuration` hoặc live JVM types trong task state. Không dựa vào deprecated `gradle.taskGraph.afterTask` / `buildFinished` listener chạy sau configuration: trên configuration cache hit, các callbacks cấu hình không được đăng ký lại theo cách cũ.

**Không “sửa” các incompatibilities bằng cách luôn dùng `--configuration-cache-problems=warn`**. Cờ warn chỉ là diagnostic aid, có thể che lỗi cần sửa và không bảo đảm build success; default thường fail khi có problems.

### 6.7. Cache state có thể chứa dữ liệu nhạy cảm

Configuration cache serialize task state, có thể bao gồm cấu hình có credentials nếu build logic xử lý sai. Gradle có cơ chế encryption cho state, nhưng vẫn cần kiểm soát access, local disk cleanup và secret handling; đừng đưa tokens/plaintext passwords vào log hoặc cacheable outputs và chia sẻ nguyên directory một cách tùy tiện.

**Khác với remote build cache:** configuration state là dữ liệu nội bộ nhạy cảm gắn với build/Gradle environment. Không copy nguyên `.gradle/configuration-cache` qua máy khác rồi mong tương thích hoặc an toàn như remote task-output cache.

## 7. Lab runnable Java 17+: quan sát cả ba cache trong cùng project

Lab có **một Java application thật** phụ thuộc Apache Commons Lang để thử **dependency cache**, một `JavaCompile` task để thử **build cache**, và một custom `@CacheableTask` viết text file để dễ đọc output/cache key. `--configuration-cache` sẽ cho thấy configured graph được reuse mà task có thể vẫn execute hoặc `UP-TO-DATE`.

### 7.1. Công cụ và cấu trúc thư mục

Chuẩn bị:

- JDK **17+** và Gradle Wrapper tương thích.
- Internet hoặc local cache đã chứa `org.apache.commons:commons-lang3:3.17.0` cho lần đầu resolve.
- Shell Linux/macOS hoặc Windows PowerShell.

Cây file:

```text
cache-layers-lab/
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── settings.gradle
├── build.gradle
└── src/main/java/example/CacheDemo.java
```

Gradle Wrapper phải được tạo bằng `gradle wrapper` hoặc `gradle init` khi đã có Gradle phù hợp; file `build.gradle` không tự tạo wrappers. Một lần wrapper bootstrap có thể tải Gradle distribution nên điều kiện network lần đầu độc lập với dependency caching của build.

### 7.2. File settings.gradle

```groovy
rootProject.name = 'cache-layers-lab'
```

### 7.3. File build.gradle hoàn chỉnh (Groovy DSL)

File này **có import ở đầu**, được phép trước Gradle `plugins { }` block. Phần `WriteGreeting` là một **custom task type viết bằng Groovy trong build script**, không cần `buildSrc` hay plugin build khác.

```groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

plugins {
    id 'application'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

application {
    mainClass = 'example.CacheDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

@CacheableTask
abstract class WriteGreeting extends DefaultTask {
    @Input
    abstract Property<String> getRecipient()

    @OutputFile
    abstract RegularFileProperty getDestination()

    @TaskAction
    void writeGreeting() {
        def path = getDestination().get().asFile.toPath()
        Files.createDirectories(path.getParent())
        Files.writeString(
            path,
            "Hello, " + getRecipient().get() + "!\n",
            StandardCharsets.UTF_8
        )
    }
}

tasks.register('writeGreeting', WriteGreeting) {
    recipient.convention(
        providers.gradleProperty('greetingName').orElse('Gradle')
    )
    destination.convention(
        layout.buildDirectory.file('generated/greeting.txt')
    )
}
```

**Giải thích nhóm cấu hình:**

1. `application` áp Java plugin, cung cấp `compileJava`, `run`, `jar`, `build`, `clean`.
2. `repositories.mavenCentral()` và `implementation` khiến Gradle phải resolve Apache Commons Lang; đây là chất liệu quan sát **dependency cache**.
3. `application.mainClass` dùng cho `run`; Java application code ở dưới sử dụng `StringUtils.capitalize` từ dependency thật.
4. `options.release = 17` xác định Java API/bytecode target; cần JDK compiler hỗ trợ `--release 17`.
5. `WriteGreeting` được đánh dấu **`@CacheableTask`** để task type cho phép cache outputs, khác `Task.doLast` ad-hoc không khai báo output.
6. `@Input Property<String> recipient` bảo Gradle text `recipient` là input có thể thay đổi và phải ảnh hưởng cache key.
7. `@OutputFile RegularFileProperty destination` định nghĩa đúng file output; `Files.createDirectories` chỉ tạo parent của declared output.
8. `@TaskAction` viết **UTF-8 file** có nội dung dựa hoàn toàn trên recipient input; không phụ thuộc current timestamp, random hoặc network.
9. `providers.gradleProperty('greetingName').orElse('Gradle')` là provider lazy. Task sẽ dùng `Gradle` nếu không truyền property, hoặc dùng `Team` khi invocation có `-PgreetingName=Team`.
10. `layout.buildDirectory.file(...)` khai báo output thông qua ProjectLayout tại configuration, rồi trong action chỉ đọc managed property của task. Mô hình này thân thiện hơn với Configuration Cache.
11. Không cấu hình `org.gradle.caching=true` hoặc `org.gradle.configuration-cache=true` ở baseline: chúng ta bật bằng flags riêng để dễ quan sát từng lớp.

**Đừng tự chép class `WriteGreeting` vào một file `.java`**: đó là Groovy custom task class nằm trong `build.gradle`. Phần **Java 17 source hoàn chỉnh** nằm ở file tiếp theo.

### 7.4. File src/main/java/example/CacheDemo.java

```java
package example;

import org.apache.commons.lang3.StringUtils;

public final class CacheDemo {
    private CacheDemo() {
    }

    public static void main(String[] args) {
        String who = args.length == 0 ? "Gradle" : args[0];
        String message = StringUtils.capitalize("hello");
        System.out.println(message + ", " + who + "!");
    }
}
```

`StringUtils.capitalize("hello")` trả `Hello`. Kết quả của ứng dụng **không phụ thuộc vào task `writeGreeting`**. Hai phần minh họa các cache riêng:

- `compileJava`/`run` cần Commons Lang.
- `writeGreeting` chỉ cần Gradle + Java runtime của Gradle, không cần Commons Lang để thực thi text generator, dù Gradle có thể vẫn cấu hình Java project.

### 7.5. Build/run lần đầu

Linux/macOS:

```bash
./gradlew clean run --args="Team" --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat clean run --args="Team" --console=plain
```

**Stdout do Java application in:**

```text
Hello, Team!
```

Đây là kết quả **của Java main method**, không phải full Gradle transcript. Gradle cũng in task logs và success/failure tùy version. Lần đầu, nếu Maven Central chưa có trong cache, Gradle có thể tải metadata/JAR; sau đó dùng lại dependency artifacts theo cơ chế dependency cache.

Không ép người đọc tin task `:compileJava` chắc chắn hiển thị `FROM-CACHE` ở lần chạy đầu: chưa có cache output tương ứng thì Gradle phải compile.

## 8. Thí nghiệm A — Dependency cache với --offline và --refresh-dependencies

### 8.1. Warm dependency thật

Chạy:

```bash
./gradlew clean compileJava --console=plain
```

Vì source import `org.apache.commons.lang3.StringUtils`, compile classpath phải có binary Commons Lang. Khi build thành công, cần có resolved metadata/JAR trong Gradle User Home cache.

Xem dependency graph:

```bash
./gradlew dependencies --configuration compileClasspath --console=plain
```

Trong output sẽ có dependency liên quan `org.apache.commons:commons-lang3:3.17.0` (có thể có thêm transitive metadata). **Đây chỉ là kiểm tra graph**; không dùng lệnh `dependencies` một mình làm bằng chứng JAR bytecode đã được tải.

### 8.2. Thử offline

```bash
./gradlew compileJava --offline --console=plain
```

Với artifact và metadata đã warm, lệnh có thể thành công dù Gradle không được phép truy cập remote dependency repositories. Trên một máy mới không có caches, `--offline` có thể fail.

**Cách giải thích đúng:** offline success chứng minh Gradle đủ dữ liệu cached cho **invocation này**, không chứng minh build cache hit hay configuration cache reused.

### 8.3. Thử refresh có chủ đích

```bash
./gradlew compileJava --refresh-dependencies --info --console=plain
```

Gradle recheck dependencies. Khi không có thay đổi, nó có thể chỉ thực hiện metadata/HTTP conditional checks và tái sử dụng cached bytes; **không bắt buộc download lại JAR**. Chạy `--info` giúp quan sát resolution; output cụ thể phụ thuộc remote repository, cache freshness và Gradle release.

### 8.4. Đổi version để thấy cache miss đúng loại

Thay dependency trong `build.gradle` sang **một version hợp lệ khác** mà repository cung cấp, rồi chạy `compileJava`. Gradle có thể phải resolve module mới, đồng thời JavaCompile cache key thay vì compiler classpath thay đổi.

**Bài học giao nhau:** một thay đổi dependency có thể làm **dependency cache miss** và **build cache miss** cùng lúc, còn `build.gradle` đổi cũng thường invalidates configuration cache. Nhưng đó là **ba nguyên nhân khác nhau**, không phải một cache duy nhất.

## 9. Thí nghiệm B — Build cache với custom task có output

Task `writeGreeting` có declared input `recipient`, declared output `destination`, và `@CacheableTask`. Nó là ví dụ phù hợp để quan sát `UP-TO-DATE` và `FROM-CACHE`.

### 9.1. Lần đầu: execute + store output

```bash
./gradlew clean writeGreeting --build-cache --console=plain
```

Task viết file `build/generated/greeting.txt` với nội dung:

```text
Hello, Gradle!
```

**Đây là nội dung file**, có newline ở cuối; nó **không phải stdout của task**. Xem file trên Unix:

```bash
cat build/generated/greeting.txt
```

Windows PowerShell:

```powershell
Get-Content .\build\generated\greeting.txt
```

Khi task chạy thật, Gradle có thể lưu output vào local build cache vì task type cacheable và inputs/outputs hợp lệ.

### 9.2. Lần hai: UP-TO-DATE chứ không nhất thiết FROM-CACHE

```bash
./gradlew writeGreeting --build-cache --console=plain
```

Vì output file vẫn còn và inputs không đổi, Gradle thường báo:

```text
> Task :writeGreeting UP-TO-DATE
```

Đây là **local work avoidance**. Build cache có bật nhưng Gradle không cần khôi phục output từ cache. Đừng tuyên bố `UP-TO-DATE` là “đã lấy file từ remote cache”.

### 9.3. Sau clean: FROM-CACHE nếu có cache entry tương ứng

```bash
./gradlew clean writeGreeting --build-cache --console=plain
```

`clean` xóa project build outputs, **không tự xóa local build cache trong Gradle User Home**. Nếu lần đầu đã store output, không thay code/inputs/Gradle configuration tương ứng và cache entry còn đó, outcome của `writeGreeting` thường là:

```text
> Task :writeGreeting FROM-CACHE
```

Gradle đã **restored** `build/generated/greeting.txt` mà không chạy `writeGreeting()` action. Nội dung file vẫn là:

```text
Hello, Gradle!
```

**Đây là một kỳ vọng có điều kiện, không phải stdout bảo đảm trên mọi máy.** Nếu cache mới, cache entry bị dọn, task implementation/configuration đổi, remote unavailable hoặc key khác, Gradle sẽ chạy task và hiển thị `SUCCESS`. Cả hai có thể đúng về mặt build correctness.

### 9.4. Đổi declared input: task phải tạo output khác

```bash
./gradlew writeGreeting -PgreetingName=Team --build-cache --console=plain
```

`recipient` chuyển từ `Gradle` sang `Team`, nên task cache key/input snapshot thay đổi. Nếu chưa có matching cached output cho Team, task execute và viết:

```text
Hello, Team!
```

Nếu từng build trước đã lưu đúng output cho Team, Gradle có thể `FROM-CACHE` thay vì execute: **điều quan trọng là file/behavior đúng với input Team**, không phải luôn phải thấy SUCCESS.

Chạy lại với `-PgreetingName=Team`:

```bash
./gradlew writeGreeting -PgreetingName=Team --build-cache --console=plain
```

Nếu file vẫn hiện diện và không đổi, thường `UP-TO-DATE`. Nếu đổi lại default `Gradle`, Gradle phải điều chỉnh output để phản ánh declared input (execute hoặc load matching output từ cache).

### 9.5. So sánh khi tắt build cache

```bash
./gradlew clean writeGreeting --no-build-cache --console=plain
```

Sau `clean`, file output không còn; khi build cache bị tắt cho invocation, task cần chạy action để tạo lại file, dù những output tương đương từng được lưu ở cache. Up-to-date check vẫn tồn tại: nếu bỏ `clean` và chạy lệnh tương tự lần hai, task vẫn có thể `UP-TO-DATE`.

### 9.6. --rerun-tasks có tác dụng khác

```bash
./gradlew writeGreeting --rerun-tasks --console=plain
```

`--rerun-tasks` buộc Gradle thực thi những tasks được chọn và dependencies của chúng, bỏ qua up-to-date check. Nó không có nghĩa “xóa dependency cache” hoặc “xóa configuration cache”. Dùng flag để debug task execution, không phải cách tối ưu builds thường ngày.

## 10. Thí nghiệm C — Configuration cache của cùng project

### 10.1. Lần đầu lưu cấu hình

```bash
./gradlew writeGreeting --configuration-cache --build-cache --console=plain
```

Gradle tạo task graph/cache entry nếu chưa có. Task `writeGreeting` có thể `UP-TO-DATE` vì output từ các thí nghiệm trước đang có. **Điều này không mâu thuẫn:** configuration cache là việc tái dùng **task configuration**, còn task outcome phụ thuộc work avoidance/build cache.

### 10.2. Lần hai reuse cấu hình

```bash
./gradlew writeGreeting --configuration-cache --build-cache --console=plain
```

Nếu configuration inputs và task request không đổi, Gradle thông báo reused entry. Task vẫn có thể `UP-TO-DATE` vì output đã tồn tại. Hai cache hits **được xác định độc lập**.

### 10.3. Đổi property đầu vào của task mà vẫn có thể reuse cấu hình

```bash
./gradlew writeGreeting -PgreetingName=Team \
  --configuration-cache --build-cache --console=plain
```

`providers.gradleProperty('greetingName').orElse('Gradle')` được nối **lazily** vào `@Input Property<String> recipient`. Nếu provider chỉ được đọc làm task input ở execution/serialization theo quy tắc được hỗ trợ, thay `greetingName` không nhất thiết bắt Gradle evaluate lại mọi build script; configured graph có thể reuse, trong khi output/input của task thay đổi và task cần execute hoặc load khác từ build cache.

**Không hứa một console transcript cố định**: Gradle có thể invalidates configuration entry nếu có những configuration-time reads khác của property hoặc flags ảnh hưởng graph. Nếu cần chắc chắn, đọc message stored/reused và report thực tế.

### 10.4. Thay đổi build.gradle thường invalidates entry

Nếu sửa `build.gradle` để đổi repositories, dependencies hoặc định nghĩa `WriteGreeting`, Gradle phải đánh giá lại build config và có thể đổi build cache key tương ứng. Đây là **configuration cache miss do build logic thay đổi**; nếu task outputs vẫn hợp lệ, task có thể up-to-date hoặc hit build cache sau khi cấu hình lại.

### 10.5. Source Java đổi thì sao?

Đổi Java string trong `CacheDemo.java` từ `"hello"` thành `"welcome"` rồi chạy:

```bash
./gradlew compileJava --configuration-cache \
  --build-cache --console=plain
```

Nếu source file không phải một **configuration input**, Gradle có thể reuse task graph; nhưng `compileJava` nhận source mới và phải execute hoặc tìm matching cached class output. Dependency cache vẫn có Commons Lang version cố định, trừ khi repository/cache state có vấn đề riêng.

## 11. Đọc bảng trạng thái kết hợp

| Kịch bản | Dependency cache | Build cache / task outcome | Configuration cache |
| --- | --- | --- | --- |
| Build đầu trên máy mới | Có thể download metadata/JAR. | Tasks thường execute, sau đó có thể store outputs. | Miss/store nếu bật. |
| Build lại không đổi | Reuse metadata/artifacts. | Tasks có outputs thường UP-TO-DATE. | Reuse nếu cùng request/config inputs. |
| `clean` rồi build với `--build-cache` | External JARs thường vẫn cache. | Tasks cacheable có thể FROM-CACHE. | Có thể reuse nếu entry vẫn hợp lệ. |
| `--offline` có đủ artifacts | Resolve từ dependency cache, không truy cập remote repos. | Build cache có thể hit/miss độc lập. | Có thể reuse, nếu input/request tương thích. |
| `--refresh-dependencies` | Recheck resolution/remote metadata. | Task outputs chỉ bị ảnh hưởng nếu relevant inputs thay đổi. | Có thể cần cập nhật resolved state, tùy invocation. |
| Đổi Java source | Dependency cache thường không đổi. | JavaCompile task input thay đổi. | Có thể reuse config entry. |
| Đổi external dependency version | Resolve artifact/version mới. | Compile/test cache key có thể đổi do classpath. | Thường invalidates vì build script/config đổi. |
| Thêm Gradle task/plugin | Không nhất thiết đổi external libraries. | Task implementation/key hoặc graph thay đổi. | Invalidates khi build logic đổi. |
| CI máy mới có remote build cache | Dependency cache có thể cold. | Remote FROM-CACHE nếu outputs/key khớp. | Config cache không tự chia sẻ sang CI máy mới. |

**Đọc đúng “tốc độ chậm”:** compile lại vì source/task input thay đổi là build cache miss; tải lại JAR vì thay repository/version là dependency resolution issue; configure lại do build script/env/property đổi là configuration cache miss. Một build chậm có thể do cả ba hoặc do hoàn toàn khác (tests, disk I/O, daemon warm-up, toolchains).

## 12. Các cờ Gradle cần nhớ

| CLI/property | Lớp liên quan | Ý nghĩa |
| --- | --- | --- |
| `--offline` | Dependency resolution | Không gọi remote dependency repositories; dùng cache hiện có. |
| `--refresh-dependencies` | Dependency resolution | Recheck dependency metadata/artifacts, không bắt buộc redownload bytes không đổi. |
| `--build-cache` | Task output cache | Cho phép dùng build cache cho invocation. |
| `--no-build-cache` | Task output cache | Tắt build cache cho invocation. |
| `org.gradle.caching=true` | Task output cache | Bật dài hạn. |
| `--configuration-cache` | Configuration | Cho phép lưu/reuse configured task graph. |
| `--no-configuration-cache` | Configuration | Tắt cho invocation. |
| `org.gradle.configuration-cache=true` | Configuration | Bật dài hạn. |
| `--configuration-cache-problems=warn` | Configuration diagnostic | Chuyển một số problems thành warnings; không khuyên dùng lâu dài. |
| `--rerun-tasks` | Task execution | Force execute tasks, không xóa caches. |
| `clean` | Task outputs | Xóa project build output theo clean task; không tự xóa Gradle User Home caches. |
| `--info`/`--debug` | Diagnostics | Thêm log về resolution, caching decisions và task execution. |
| `--stacktrace` | Diagnostics | Chi tiết exception khi build fail. |

**Cẩn thận với flag kết hợp:** `--offline` và `--refresh-dependencies` có mục tiêu trái nhau (không mạng vs buộc recheck), không dùng chúng như một công thức “xóa cache sạch” rồi hy vọng kết quả dễ phân tích. Chọn một mục tiêu cho mỗi thí nghiệm.

## 13. Cấu hình/cache isolation trong CI và remote cache

### 13.1. CI có ba loại dữ liệu cần quản lý khác nhau

- **Dependency artifacts:** mirror/caches giúp giảm Maven downloads, nhưng cần credentials, repository provenance và dependency verification.
- **Task outputs:** remote build cache có thể chia sẻ giữa CI/developers nếu tasks cacheable và inputs deterministic; cấu hình pull/push rõ.
- **Configuration state:** thường local cho workspace/Gradle environment; không đơn giản chia sẻ qua remote build cache URL.

Đừng mount một writable Gradle User Home duy nhất cho nhiều container CI không chia sẻ được file locks; Gradle docs có lưu ý cache locking phụ thuộc khả năng các processes giao tiếp. Dùng cache volumes/read-only snapshots/chia sẻ outputs theo hướng dẫn CI/Gradle cụ thể, thay vì nhiều runners tùy tiện viết đồng thời vào cùng `caches/modules-2`.

### 13.2. Phân biệt cold, warm và clean build

| Thuật ngữ | Chính xác nên hiểu |
| --- | --- |
| **Cold dependency cache** | Metadata/artifacts chưa sẵn ở Gradle User Home hiện tại. |
| **Warm dependency cache** | Relevant artifacts/metadata đã có, remote checks có thể vẫn xảy ra theo TTL. |
| **Cold build cache** | Chưa có entry phù hợp với task cache key. |
| **Warm build cache** | Có entry phù hợp; task có thể FROM-CACHE nếu workspace outputs chưa up-to-date. |
| **Clean build** | Project build outputs bị xóa bằng clean task; dependency/build/config caches có thể **vẫn còn**. |
| **Configuration cache miss** | Entry không có/invalid cho task request và config inputs. |
| **Configuration cache reuse** | Task graph được restore; không có nghĩa tasks đã có output. |

**Một điểm dễ bị lừa bởi benchmark:** `./gradlew clean build` không đồng nghĩa “mọi cache đều cold”. Muốn đo download, configuration và task execution riêng, dùng Gradle logs/build scan, giữ nguyên môi trường thử nghiệm và mô tả chính xác bạn đã xóa/cấp phát những directories nào.

### 13.3. Cách đọc kết quả đo hiệu năng

Đừng chỉ đo tổng `BUILD SUCCESSFUL in ...`. Nên quan sát:

1. Download bytes / remote HTTP metadata requests.
2. Configuration time và cache store/reuse status.
3. Tasks executed, UP-TO-DATE, FROM-CACHE, NO-SOURCE.
4. Task duration của compile/test/code generation.
5. Remote cache hit/miss và upload/download costs.
6. Gradle Daemon, JVM/toolchain warm-up, file system/OS cache, annotation processors.
7. Thay đổi về dependency graph và build logic giữa hai lần chạy.

Nếu remote build cache trả output lớn chậm hơn việc execute task ngắn, lợi ích có thể âm. Đừng bật cache mọi task chỉ vì có annotation; đo đúng workload.

### 13.4. Cache correctness quan trọng hơn cache hit rate

Một task **cacheable nhưng thiếu declared input** có thể tái sử dụng **sai output**. Ví dụ task tạo file từ biến môi trường `BUILD_NUMBER` nhưng không khai báo nó là input: Gradle có thể nghĩ inputs giống nhau và load kết quả cũ. Phương án đúng là đưa giá trị đó vào managed `Property<String>`, dùng `providers.environmentVariable('BUILD_NUMBER')` khi hợp lý, hoặc bỏ caching nếu output không deterministic.

Đừng che giấu vấn đề bằng cách buộc `--rerun-tasks` ở mọi CI build; hãy sửa input/output modeling, tasks và caching contract.

## 14. Trường hợp cache miss thường gặp và cách xử lý

| Triệu chứng | Cache liên quan | Giải thích và bước kiểm tra |
| --- | --- | --- |
| Gradle tải Commons Lang lại trên CI | Dependency | CI có Gradle User Home riêng hoặc thiếu artifact, repository/metadata khác. Kiểm tra network/repo/cache persistence. |
| `--offline` fail “could not resolve” | Dependency | Cần artifact/metadata chưa có, hoặc plugin dependency/toolchain chưa cache. Warm đúng task trước; không đổi build cache flags mù quáng. |
| `--refresh-dependencies` vẫn không tải lại JAR | Dependency | Gradle kiểm tra remote checksum/metadata rồi nhận artifact không đổi. Đó có thể là behavior đúng. |
| SNAPSHOT không thấy bản mới | Dependency | Changing module TTL, publication policy hoặc stale repository metadata. Kiểm tra TTL và --refresh-dependencies. |
| Đổi repository làm artifact cached không được dùng | Dependency | Repository stickiness/provenance, credentials hoặc content filters. Xác định repository thực tế. |
| Chạy lại `compileJava` thấy UP-TO-DATE, không FROM-CACHE | Task work avoidance | File outputs vẫn còn; Gradle không cần load cache. Thử clean rồi build-cache khi cần demo. |
| `clean compileJava --build-cache` vẫn SUCCESS | Build cache | Chưa có cache entry, task không cacheable hoặc key khác. Bật --info, kiểm tra task classpath/input state. |
| Task custom không bao giờ FROM-CACHE | Build cache | Thiếu `@CacheableTask`, declared output, cache bật hoặc task có lý do disable caching. |
| Cache hit nhưng output sai | Build cache correctness | Hidden inputs, path sensitivity sai, nondeterministic output. Sửa task contract, kiểm thử clean/relocated build. |
| Remote build cache không kết nối | Build cache | URL, auth, TLS, HTTP status, firewall hoặc cache policy. Kiểm tra remote config và server health. |
| `--build-cache` đã bật mà Gradle vẫn cấu hình tất cả | Configuration | Build cache không cache configuration phase. Dùng `--configuration-cache` nếu compatible. |
| Configuration cache “stored” mỗi lần | Configuration | Build scripts, env/system properties, config files hoặc task request đổi; xem report/config inputs. |
| Configuration cache báo `Project` trong task action | Configuration | Task giữ live Gradle model lúc execute. Dùng managed task properties/providers thay vì `project.*`. |
| Build cache hit nhưng configuration cache miss | Cả hai độc lập | Output cache key match, config inputs/task graph invalidated. Không mâu thuẫn. |
| Configuration cache reused nhưng JavaCompile chạy | Configuration + task | Source/task input thay đổi; task graph reused, task cần execute. |
| Đổi `-PgreetingName` làm output cũ không đổi | Build cache correctness | Kiểm tra property đã wire vào `@Input`, code task thật, cache output và command. |
| `clean` rồi `.gradle/configuration-cache` vẫn còn | Configuration | clean xóa build outputs, không mặc định dọn project configuration cache. |
| Xóa `~/.gradle/caches` khiến Gradle tải lại mọi thứ | Dependency + build cache | Xóa cả dependency/download cache và local build cache là thao tác rộng; không cần khi chỉ debug một task. |
| Gradle 9.x làm code cache cũ báo vấn đề | Configuration/plugin compat | Plugin/build logic có API/lifecycle không compatible; xem report, Gradle/Java support matrix và sửa code. |

## 15. An toàn khi dọn cache: ưu tiên khoanh vùng

### 15.1. Đừng xóa toàn bộ ~/.gradle theo thói quen

Trong Gradle User Home có thể có:

- Cached dependency metadata/artifacts.
- Local build cache/task outputs.
- Wrapper distributions và Gradle toolchains/caches khác.
- Thông tin lock/daemon/Gradle state.

Xóa hết có thể khiến lần build kế tiếp chậm đáng kể, cần lại network và mất ích lợi cache của các projects khác. Đừng làm vậy nếu chưa hiểu thư mục và nguyên nhân.

### 15.2. Khi muốn build lại artifact project

```bash
./gradlew clean build --console=plain
```

`clean` dọn project outputs; dependency cache và local task build cache có thể vẫn tái sử dụng. Nếu bạn **muốn kiểm chứng action thực sự chạy lại**, có thể dùng `--rerun-tasks` hoặc tắt build cache phù hợp với mục tiêu, thay vì xóa mọi thứ.

### 15.3. Khi muốn tạm bỏ configuration cache

```bash
./gradlew build --no-configuration-cache --console=plain
```

Flag này **không xóa entry cũ**; nó chỉ yêu cầu build hiện tại không dùng configuration cache. Theo tài liệu Gradle, configuration cache được lưu ở `.gradle/configuration-cache` của root build; nếu nhất thiết cần invalidation thủ công có thể xóa **đúng thư mục đó** khi build không đang chạy, nhưng phải hiểu tác động đến build và không dùng xóa đệ quy tự động trên path chưa xác minh.

### 15.4. Khi dependency resolution sai version

Kiểm tra:

1. `./gradlew dependencyInsight --dependency <module-name> --configuration compileClasspath`.
2. Repositories trong settings/project (đặc biệt private Maven repository hoặc mirror).
3. Dynamic/changing TTL và constraints/BOM/lockfiles.
4. `--refresh-dependencies` nếu có lý do cần remote recheck.
5. Kiểm tra artifact đã publish thật và credentials/HTTP status.

**Đừng đổi `--build-cache` để sửa version conflict**: build cache không quyết định dependency graph.

## 16. Bài tập thực hành và đáp án định hướng

**Bài 1 — Phân loại output.** `commons-lang3-3.17.0.jar` được Gradle tải từ Maven Central vào cache nào? **Dependency cache**. `CacheDemo.class` sinh từ compileJava được cache ở đâu khi build-cache bật? **Build cache task output**, nếu cacheable/key phù hợp.

**Bài 2 — Chạy lại không đổi.** Sau `./gradlew writeGreeting --build-cache` lần hai, outcome thường là gì? **UP-TO-DATE**, vì file output vẫn ở workspace.

**Bài 3 — Sau clean.** Chạy `./gradlew clean writeGreeting --build-cache` lần tiếp theo với cache warm. Outcome mong đợi? **FROM-CACHE** nếu entry hợp lệ; nếu chưa có cache entry thì task **SUCCESS** sau khi chạy action.

**Bài 4 — Build cache tắt.** Chạy `./gradlew clean writeGreeting --no-build-cache`. Vì sao không FROM-CACHE? Vì flag tắt task output cache cho invocation, dù dependency cache vẫn hoạt động.

**Bài 5 — Đổi input.** Chạy `-PgreetingName=Team`. Tại sao file đổi từ `Hello, Gradle!` sang `Hello, Team!`? Vì recipient là declared `@Input`, ảnh hưởng cache key/task execution.

**Bài 6 — Offline.** Sau khi compileJava đã tải Commons Lang, chạy `./gradlew compileJava --offline`. Vì sao có thể build được? Vì dependency metadata/artifacts sẵn trong dependency cache, không phải vì JavaCompile FROM-CACHE.

**Bài 7 — Máy mới.** CI runner chưa tải Commons Lang, `--offline` fail. Có thể chỉ bật configuration cache để tạo JAR không? **Không**; configuration cache không cung cấp bytes của missing external dependency.

**Bài 8 — Refresh.** Khi chạy `--refresh-dependencies` mà server trả artifact không đổi, Gradle có bắt buộc download lại JAR không? **Không**.

**Bài 9 — Version động.** Khai báo `com.example:library:2.+` và muốn recheck version sau 10 phút. Dùng cấu hình gì? `cacheDynamicVersionsFor 10, 'minutes'` trên relevant resolutionStrategy.

**Bài 10 — SNAPSHOT.** Artifact `1.0-SNAPSHOT` bị republish nhưng Gradle chưa thấy. Cache nào liên quan? **Dependency cache changing-module TTL**; kiểm tra repo metadata và `--refresh-dependencies`.

**Bài 11 — Configuration cache.** Chạy `./gradlew help --configuration-cache` hai lần không đổi. Lần đầu store, lần sau có thể reuse. Điều gì được reuse? **Configured task graph/state**, không phải một file `.class`.

**Bài 12 — Java source thay đổi.** `CacheDemo.java` đổi nội dung; configuration cache có bắt buộc miss không? **Không** nếu file chỉ là task source input và không ảnh hưởng config; compileJava sẽ xét input mới.

**Bài 13 — Config input thay đổi.** `build.gradle` thêm plugin hoặc thay dependency version. Cache nào có khả năng invalidated? **Configuration cache**, và có thể tác động cả dependency/build cache theo nội dung thay đổi.

**Bài 14 — Task output chưa khai báo.** Custom task tạo `build/generated/report.txt` nhưng không có `@OutputFile`. Có nên gắn `@CacheableTask` rồi mong FROM-CACHE không? **Không**; phải sửa inputs/outputs đầy đủ trước.

**Bài 15 — Hidden input.** Task ghi current time vào output nhưng không khai báo time input. Cache có thể lưu sai output không? **Có**; thiết kế determinism hoặc đưa volatile input vào đúng mô hình và cân nhắc không cache.

**Bài 16 — Remote cache.** Vì sao CI có thể FROM-CACHE trên machine cold mà vẫn tải dependency artifacts? Vì **remote build cache** chứa task outputs, còn **dependency cache** của CI đang cold.

**Bài 17 — So sánh cache flags.** `--offline`, `--build-cache`, `--configuration-cache` lần lượt tác động gì? Network resolution; task output reuse; configuration graph reuse.

**Bài 18 — Bảo mật.** Có nên coi file trong `~/.gradle/caches/modules-2` là đã được xác minh chữ ký chưa? **Không**; bật dependency verification/trust policy khi cần.

**Bài 19 — Debug.** Task `writeGreeting` không FROM-CACHE sau clean. Hãy liệt kê ba khả năng: cache chưa warm, task key/input/implementation đổi, cache disabled/entry cleaned.

**Bài 20 — CI benchmark.** Một `clean build` mất 20 giây trên máy A và 5 giây trên máy B. Có thể kết luận configuration cache nhanh hơn gấp 4 không? **Không**; cần tách download, config, output cache, JDK/daemon, disk, network và task durations.

### Tự kiểm tra nhanh

1. **Gradle cache dependencies tự động?** Có.
2. **Build cache bật mặc định ở Gradle 9.9?** Không.
3. **Configuration cache bật mặc định ở Gradle 9.9?** Không.
4. **Dependency cache thường nằm ở đâu?** Gradle User Home `caches/modules-2`.
5. **Configuration cache thường nằm ở đâu?** Root build `.gradle/configuration-cache`.
6. **Build cache dùng cache key của gì?** Task implementation, declared inputs/outputs và các yếu tố snapshotting phù hợp.
7. **`UP-TO-DATE` là build-cache hit?** Không.
8. **`FROM-CACHE` là dependency download hit?** Không.
9. **`clean` có xóa Maven dependency cache không?** Không mặc định.
10. **`clean` có xóa local build cache trong Gradle User Home không?** Không mặc định.
11. **`--offline` có tự tải missing dependency không?** Không.
12. **`--refresh-dependencies` có buộc redownload mọi byte không?** Không.
13. **Dynamic/changing default TTL thường là bao nhiêu?** 24 giờ.
14. **Custom task cần output khai báo để cache đúng không?** Có.
15. **`@CacheableTask` có làm task deterministic không?** Không, developer phải đảm bảo correctness.
16. **Configuration cache có thể reuse dù Java source đổi?** Có, nếu source không được đọc như configuration input.
17. **Configuration cache có thể chia sẻ bằng remote build cache URL không?** Không theo cơ chế remote task build cache hiện hành.
18. **CI cold dependency cache có thể đồng thời warm remote build cache không?** Có.
19. **`--rerun-tasks` có xóa configuration cache không?** Không.
20. **Khi cache hit cho ra output sai, nên tăng hit rate hay sửa task modeling?** Sửa task input/output correctness.

## 17. Tài liệu chính thức và hướng đọc sâu

- **Gradle — Dependency Caching:** repository identity, metadata/artifacts, TTL, offline, refresh, cleanup/locking: https://docs.gradle.org/current/userguide/dependency_caching.html
- **Gradle — Build Cache:** bật/tắt task output caching, local/remote caches, cacheability, HTTP cache config: https://docs.gradle.org/current/userguide/build_cache.html
- **Gradle — Important Concepts of Build Cache:** task cache key, repeatable outputs, snapshots: https://docs.gradle.org/current/userguide/build_cache_concepts.html
- **Gradle — Configuration Cache:** cache entries/inputs, task graph reuse, resolved dependency state, supported features: https://docs.gradle.org/current/userguide/configuration_cache.html
- **Gradle — Enabling and Configuring Configuration Cache:** enable flags/properties, invalidation, warnings, storage: https://docs.gradle.org/current/userguide/configuration_cache_enabling.html
- **Gradle — Configuration Cache Requirements:** Gradle Project objects at execution, providers, task properties, environment, credentials và lifecycle callbacks: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
- **Gradle — Command-Line Interface:** `--offline`, `--refresh-dependencies`, `--build-cache`, `--configuration-cache`, `--rerun-tasks`: https://docs.gradle.org/current/userguide/command_line_interface.html
- **Gradle — Improve Build Performance:** chọn caches và tối ưu đúng nút thắt: https://docs.gradle.org/current/userguide/performance.html
- **Gradle — Working with Files and Tasks:** khai báo task inputs/outputs, `@CacheableTask` và incremental behavior: https://docs.gradle.org/current/userguide/incremental_build.html
- **Gradle — Java Plugin and Application Plugin:** JavaCompile, run, dependencies và source sets: https://docs.gradle.org/current/userguide/java_plugin.html và https://docs.gradle.org/current/userguide/application_plugin.html
- **Gradle — Dependency Verification:** checksum/signature/trust policy khi dùng cached artifacts: https://docs.gradle.org/current/userguide/dependency_verification.html
- **Apache Commons Lang documentation** (ví dụ `StringUtils.capitalize` trong Java lab): https://commons.apache.org/proper/commons-lang/javadocs/api-release/org/apache/commons/lang3/StringUtils.html

**Kết luận:** **Dependency cache** tránh resolve/download lại thư viện, **build cache** tái dùng **task outputs**, và **configuration cache** tái dùng **configured task graph**. Ba lớp có thể hit/miss độc lập. Đừng nhầm `UP-TO-DATE` (đã có output trong workspace) với `FROM-CACHE` (khôi phục output từ build cache), hoặc nhầm `--refresh-dependencies` với `clean`. Khi debug hiệu năng, luôn ghi rõ Gradle/JDK version, flags, task request, file/repository changes và logs của từng lớp; ưu tiên **cache correctness, declared inputs/outputs và dependency trust** hơn việc chạy theo tỷ lệ cache hit cao.