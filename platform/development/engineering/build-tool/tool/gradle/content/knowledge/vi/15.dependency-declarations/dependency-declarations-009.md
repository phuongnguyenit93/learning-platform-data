# Lựa chọn phiên bản cố định, động, snapshot và changing module trong Gradle

Một dependency được khai báo bằng `group:name:version` chưa chắc mang ý nghĩa “mỗi lần build sẽ dùng cùng một JAR”. Với Gradle, phải tách **cách chọn phiên bản** khỏi **khả năng nội dung của phiên bản ấy bị thay đổi**. Ví dụ, `3.14.0` là một phiên bản viết rõ ràng, `3.+` là một bộ chọn động, còn `1.2-SNAPSHOT` là một tọa độ có thể được publish lại với nội dung mới. Đặc biệt, một module tên `1.2.0` bình thường vẫn có thể được Gradle xem là **changing** nếu bạn chủ động gắn `changing = true`.

Bài thuộc nhóm **Khai báo dependency** của **Build Tool Gradle**, giúp bạn hiểu và quyết định:

1. Khi nào nên dùng phiên bản **cố định (fixed/static)**.
2. Khi nào dùng phiên bản **động (dynamic)** như `1.+`, khoảng `[1.0, 2.0)`, `latest.release` và `latest.integration`.
3. Maven **`-SNAPSHOT`** hoạt động ra sao và vì sao cùng tọa độ có thể trỏ tới bản build mới.
4. Khái niệm **changing module**, kể cả bản không có đuôi `-SNAPSHOT`.
5. Hai TTL cache độc lập `cacheDynamicVersionsFor` và `cacheChangingModulesFor`, mặc định **24 giờ**.
6. Cách kiểm tra phiên bản cuối cùng được chọn, làm mới cache, quản lý lockfile và bảo vệ tính tái lập trên CI.
7. Ví dụ **Gradle Wrapper + Java 17** chạy được với một thư viện thực tế; các ví dụ dùng kho giả sẽ được đánh dấu rõ là *minh họa*, không phải dự án chạy ngay.

## 1. Hai câu hỏi khác nhau: chọn tọa độ nào, và nội dung có bất biến không?

Khi khai báo:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

ta có:

- `org.apache.commons`: **group**.
- `commons-lang3`: **module/artifact**.
- `3.14.0`: **version selector**, ở đây là một chuỗi version cố định.
- `implementation`: **dependency configuration** của Java plugin để đưa thư viện vào compile/runtime classpath theo semantics của plugin.

Nhưng trong Gradle, một **version selector cố định** không phải luôn là mệnh lệnh tuyệt đối “phải chọn đúng bản này”. Nếu trong toàn bộ dependency graph có yêu cầu khác cho cùng module, Gradle còn áp dụng **version conflict resolution**, constraints, platform, dependency locking và các quy tắc liên quan. Muốn bắt buộc chính xác một phiên bản, cân nhắc **rich version `strictly`** hoặc lock state tùy mục tiêu, không chỉ nhìn chuỗi `3.14.0`.

Mặt khác, ngay cả khi cuối cùng giải quyết ra **đúng một tọa độ** như `com.example:internal-api:1.4.0-SNAPSHOT`, nội dung artifact vẫn có thể đổi nếu nhà phát hành publish snapshot mới. Đó là vấn đề **changing module** chứ không phải dynamic selector.

| Câu hỏi | Ví dụ | Cơ chế chính |
| --- | --- | --- |
| “Chọn số phiên bản nào?” | `3.14.0`, `3.+`, `[3.12,4.0)` | Version selector, graph conflict resolution, constraints, lockfile. |
| “Một tọa độ có thể có nội dung mới không?” | `1.4-SNAPSHOT`, `changing = true` | Changing module, metadata/artifact caching, repository semantics. |
| “Khi nào Gradle kiểm tra remote lại?” | `cacheDynamicVersionsFor`, `cacheChangingModulesFor` | TTL của dependency cache, `--refresh-dependencies`, `--offline`. |
| “Lần chạy sau có đúng version như hôm nay không?” | `dependencyLocking`, version constraints | Khóa kết quả **version resolution**, không đóng băng byte của changing artifact. |

**Điểm cốt lõi:** *dynamic* và *changing* là **hai trục độc lập**. Một selector động có thể chọn module release có nội dung bất biến; một selector cố định vẫn có thể trỏ tới changing module.

## 2. Bốn nhóm lựa chọn phổ biến

| Kiểu | Cú pháp ví dụ | Chọn version lúc resolve | Nội dung có thể thay đổi dù cùng version? | Phù hợp |
| --- | --- | --- | --- | --- |
| **Fixed/static** | `org.slf4j:slf4j-api:2.0.16` | Selector nêu một version cụ thể, nhưng graph có thể áp constraints/conflicts | Thông thường **không nên** bị publish lại; Gradle không bảo đảm chính sách server | Production, release, kiểm thử tái lập. |
| **Dynamic** | `org.slf4j:slf4j-api:2.0.+`, `[2.0,3.0)` | Gradle chọn một version phù hợp hiện có ở repository và quy tắc resolution | Tùy module được chọn | Tích hợp sớm, kiểm tra tương thích với bản mới. |
| **Maven SNAPSHOT** | `com.example:lib:1.3-SNAPSHOT` | Selector có tọa độ được chỉ rõ; repository có thể trỏ tới artifact snapshot mới | **Có**, đây là đặc điểm thiết kế của snapshot | Phát triển giữa các nhóm, thử nghiệm trước release. |
| **Changing module đánh dấu tường minh** | `implementation('com.example:lib:1.3.0') { changing = true }` | Version selector có thể fixed; Gradle coi nội dung module là mutable | **Có** theo khai báo của consumer | Tương tác hệ thống publish lại cùng version, thường là nội bộ. |

Một thư viện có tên `1.3-SNAPSHOT` vừa mang một *chuỗi phiên bản cụ thể* vừa được xử lý theo mô hình **changing** trong quy ước Maven. Vì vậy “SNAPSHOT” không phải một kiểu selector thứ năm đối lập hoàn toàn với “fixed”.

Hãy dùng bốn nhóm trên để quyết định hành vi mong muốn, thay vì xem mọi dependency đều chỉ là một chuỗi version được thay bằng `+` khi muốn mới hơn.

## 3. Phiên bản cố định (fixed/static): an toàn hơn, nhưng chưa phải khóa tuyệt đối

Khai báo thông thường trong **Groovy DSL**:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

**Kotlin DSL**:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Ưu điểm:

- Người đọc biết **version được yêu cầu** mà không cần truy vấn repository.
- Dễ review khi nâng version; một diff cho thấy bạn đã chủ động thay đổi dependency.
- Tránh tình huống `3.+` tự chọn phiên bản mới ngay sau khi TTL hết hạn.
- Thuận lợi cho kiểm thử, quét lỗ hổng, SBOM và kiểm soát chuỗi cung ứng.

Nhưng phải tránh kết luận sai: **“ghi `3.14.0` là chắc chắn toàn graph dùng đúng `3.14.0`.”** Ví dụ giả định:

```text
app ───────► commons-lang3:3.14.0  (khai báo trực tiếp)
  └► lib-x ─► commons-lang3:3.15.0  (transitive)
```

Nếu không có strict constraint, platform hoặc quy tắc khác, cơ chế giải quyết xung đột mặc định của Gradle thường có thể chọn bản **cao hơn**, tức `3.15.0`. Số version cố định của dependency trực tiếp là một **yêu cầu** trong graph; nó không nhất thiết là toàn bộ kết quả cuối cùng.

Để kiểm tra thực tế:

```bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Lệnh cho thấy version được chọn và những lý do liên quan (tùy graph). **Không suy đoán version cuối chỉ từ dòng `implementation`.**

### 3.1. Khi thật sự muốn đúng một version: rich version `strictly`

Ví dụ Groovy:

```groovy
dependencies {
    implementation('org.apache.commons:commons-lang3') {
        version {
            strictly '3.14.0'
        }
    }
}
```

Kotlin DSL:

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3") {
        version {
            strictly("3.14.0")
        }
    }
}
```

`strictly` là constraint mạnh: những version khác không được chấp nhận cho yêu cầu đó; nếu graph có constraint khác không tương thích, Gradle có thể **báo lỗi resolution** thay vì âm thầm chọn phiên bản mới. Chỉ dùng strict khi có lý do về tương thích/bảo mật và đã hiểu tác động đến dependencies bắc cầu.

**`strictly` không ngăn người phát hành publish lại byte của artifact cùng tọa độ.** Nó khóa lựa chọn *version*, không thay thế quy trình kiểm tra tính bất biến nội dung.

## 4. Phiên bản động (dynamic): chọn bản mới theo quy tắc, không phải “luôn mới nhất mọi lúc”

Gradle cho phép các version selector có thể khớp **nhiều version**, thường gặp:

```groovy
dependencies {
    // Mỗi dòng là một ví dụ độc lập; không cần khai báo tất cả cho cùng module.
    implementation 'org.apache.commons:commons-lang3:3.+'
}
```

Kotlin:

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.+")
}
```

`3.+` có nghĩa chọn một version trong họ `3.x` phù hợp với các phiên bản có thể được giải quyết, repository metadata và những constraints còn lại; nó **không bảo đảm** là version mới nhất vừa được publish ở thời điểm chạy do dependency cache.

### Các dạng selector động cần nhận biết

| Selector | Ý nghĩa |
| --- | --- |
| `3.+` | Khớp các version bắt đầu theo tiền tố `3.` phù hợp. |
| `3.14.+` | Khớp nhánh version có tiền tố `3.14.`, nếu publisher thực sự có các bản dạng đó. |
| `+` | Có thể chấp nhận mọi version phù hợp, rủi ro cao về breaking changes. |
| `[3.12, 4.0)` | Khoảng từ `3.12` **bao gồm** đến `4.0` **không bao gồm**. |
| `[3.12, 4.0]` | Bao gồm cả hai cận, nếu tồn tại và các constraints cho phép. |
| `latest.release` | Chọn version cao nhất với status `release` theo metadata/trạng thái Gradle nhìn thấy. |
| `latest.integration` | Chọn version cao nhất với status `integration` hoặc thỏa quy tắc status tương ứng; thường rộng hơn release. |

**Cẩn thận với range syntax:** dấu `[` / `]` là cận **bao gồm**, dấu `(` / `)` là cận **loại trừ**. Vì vậy `[1.0, 2.0)` loại `2.0`, không phải lấy cả hai cận.

### 4.1. Dynamic selector có thể chọn SNAPSHOT

Trong một ví dụ giả định một repository có:

```text
1.0
1.1
1.2-SNAPSHOT
2.0
```

Với selector `1.+` hoặc khoảng `[1,2)`, Gradle có thể chọn `1.2-SNAPSHOT` vì phiên bản đó khớp và đứng cao theo quy tắc version ordering; đừng nghĩ dynamic selector tự động loại mọi prerelease/snapshot.

Muốn chỉ chọn release, cần dùng metadata/status hoặc policy khác phù hợp, ví dụ `latest.release` và quy tắc trạng thái được repository cung cấp. **`latest.release` không phải một phép so sánh chuỗi đơn giản với hậu tố `-SNAPSHOT`**: nó phụ thuộc metadata về status và semantics của kho.

### 4.2. Version động thường dùng khi nào?

Có giá trị khi:

- Một pipeline chuyên theo dõi **version mới nhất trong nhánh** để phát hiện lỗi tương thích sớm.
- Nhóm muốn thử nghiệm với prerelease của thư viện nội bộ.
- Bài kiểm thử tương thích thư viện chạy song song với build release đã khóa.
- Một ứng dụng mẫu/POC chấp nhận dependency thay đổi theo thời gian.

Không nên dùng dynamic như mặc định cho production release, thư viện có nhiều consumer, môi trường regulated hoặc build cần tái lập tuyệt đối. Một lệnh `./gradlew build` giống nhau có thể giải quyết ra version khác sau một ngày hoặc trên runner có cache khác.

**Quyết định tốt:** dùng dynamic **có chủ đích** cho một luồng cập nhật, đồng thời khóa/ghi lại resolved versions của luồng phát hành.

## 5. Maven SNAPSHOT: cùng tọa độ nhưng artifact có thể được thay mới

Maven dùng hậu tố `-SNAPSHOT` cho bản phát triển chưa phát hành ổn định. Ví dụ:

```groovy
dependencies {
    implementation 'com.example.platform:billing-client:2.1.0-SNAPSHOT'
}
```

Dòng này mang một **tọa độ logic** `com.example.platform:billing-client:2.1.0-SNAPSHOT`. Repository Maven snapshot có thể được cập nhật sau mỗi lần nhóm producer publish. Tùy cấu hình Maven repository, bản snapshot có thể được lưu với timestamp/build number và metadata ánh xạ từ logical SNAPSHOT tới artifact cụ thể.

```text
Consumer khai báo
    com.example.platform:billing-client:2.1.0-SNAPSHOT
                               │
                               ▼
Kho Maven snapshot có metadata/version của bản publish mới
                               │
             ┌─────────────────┴──────────────────┐
             ▼                                    ▼
   Bản publish sáng nay                    Bản publish buổi chiều
   API/bytecode phiên bản A                API/bytecode phiên bản B
   Cùng logical -SNAPSHOT                  Cùng logical -SNAPSHOT
```

Vì vậy:

- Một build chạy sáng nay và chiều nay có thể sử dụng **nội dung khác** mặc dù chuỗi version không đổi.
- Gradle dùng cơ chế **changing dependency** để quản lý metadata/artifact cache cho Maven SNAPSHOT.
- Ngay cả khi lockfile ghi `2.1.0-SNAPSHOT`, nó chỉ khóa tọa độ/version logic, **không đóng băng nội dung của bản SNAPSHOT**.
- Nếu producer publish lại bản SNAPSHOT nhưng consumer chưa refresh cache, consumer có thể vẫn dùng JAR/metadata cũ.

### 5.1. Cần repository có snapshot thật

Đây là **mẫu cấu hình minh họa**, không phải lệnh có thể chạy với URL giả:

```groovy
repositories {
    mavenCentral()

    maven {
        name = 'companySnapshots'
        url = uri('https://repo.example.invalid/maven-snapshots')
        mavenContent {
            snapshotsOnly()
        }
    }
}

dependencies {
    implementation 'com.example.platform:billing-client:2.1.0-SNAPSHOT'
}
```

- `mavenCentral()` dành cho thư viện public được publish lên Maven Central.
- `companySnapshots` phải là **endpoint Maven thật** có module snapshot tương ứng.
- `mavenContent { snapshotsOnly() }` hạn chế kho này cho snapshot version trong phạm vi Gradle hiểu; giúp tránh hỏi nhầm kho snapshots cho releases.
- `com.example.platform:billing-client` là tên minh họa; bạn phải thay bằng tọa độ tổ chức thực sự publish.
- Nếu kho private yêu cầu credentials, cung cấp qua Gradle properties/CI secrets và HTTPS, **không hard-code password** trong file commit.

Nếu project dùng `dependencyResolutionManagement.repositories` tập trung ở `settings.gradle`, hãy đặt kho snapshot ở **đúng block repository của settings** theo `repositoriesMode`, không tùy tiện thêm ở `build.gradle` khi `FAIL_ON_PROJECT_REPOS` đang bật.

### 5.2. SNAPSHOT khác bản pre-release bất biến

Một version như `2.1.0-rc1` hoặc `2.1.0-beta.2` có thể là bản phát hành thử **có tọa độ riêng và nội dung bất biến**, tùy chính sách publisher. Sự xuất hiện của hậu tố `beta` hoặc `rc` **không tự đồng nghĩa** Gradle phải coi module là changing.

Ngược lại, hậu tố `-SNAPSHOT` trong Maven biểu thị convention snapshot có thể đổi nội dung. Hãy đánh giá theo **cách repository publish và metadata**, không chỉ nhìn chuỗi có chữ “alpha/beta”.

## 6. Changing module: phiên bản không đổi nhưng Gradle cần kiểm tra artifact mới

Ngoài Maven SNAPSHOT, Gradle có thể được chỉ thị xem **bất kỳ external module dependency** nào là changing:

**Groovy DSL:**

```groovy
dependencies {
    implementation('com.example.platform:billing-client:2.1.0') {
        changing = true
    }
}
```

**Kotlin DSL:**

```kotlin
dependencies {
    implementation("com.example.platform:billing-client:2.1.0") {
        isChanging = true
    }
}
```

Hai đoạn đều là **minh họa cho module giả định**. Không thể chạy nếu module không được publish trong một repository thực tế.

Cách hiểu:

- `2.1.0` vẫn là **một version selector cụ thể**, không biến thành `2.+`.
- `changing = true` chỉ báo cho Gradle rằng metadata/artifact của **tọa độ này có thể đổi**.
- Gradle dùng **changing module cache policy** cho module đó, thay vì giả định một version thông thường bất biến.
- Phương pháp này không khiến producer tự phát hành file; bạn vẫn cần một kho cung cấp artifact hợp lệ.

Tình huống sử dụng là một nhóm nội bộ **chủ động publish lại cùng GAV** trong vòng phát triển ngắn, hoặc tương tác với repository không dùng `-SNAPSHOT` nhưng có semantics tương tự. Trong production, nên tránh publish lại một release version; version bất biến mới là nền tảng để audit và debug.

### 6.1. Changing và dynamic có thể cùng xuất hiện

Hai cờ diễn đạt hai loại biến động:

- **Dynamic selector:** yêu cầu một tập phiên bản, ví dụ `2.+`. Sau TTL, Gradle có thể chọn bản `2.5` thay vì `2.4`.
- **Changing module:** sau khi chọn `2.4-SNAPSHOT` hoặc module được đánh dấu `changing`, Gradle còn có thể thấy **artifact mới của cùng tọa độ** sau TTL khác.

Trong một graph có dynamic selector trỏ đến SNAPSHOT, **cả hai quy tắc cache** có thể cùng quan trọng: cache của phép chọn số version và cache của metadata/nội dung module changing.

## 7. Hai TTL cache trong Gradle: mặc định đều 24 giờ

Gradle lưu thông tin resolution tại Gradle User Home cache, không cần tải lại mọi artifact ở mỗi lần chạy. Điều này tăng tốc và giảm phụ thuộc mạng, nhưng khiến một dependency động hoặc changing không lập tức nhận giá trị mới.

Theo Gradle Dependency Caching/ResolutionStrategy, mặc định:

| Cache | Mục tiêu | TTL mặc định | Ví dụ |
| --- | --- | --- | --- |
| **Dynamic version cache** | Kết quả ánh xạ selector động → version đã được chọn | **24 giờ** | `3.+` → `3.18.0` |
| **Changing module cache** | Metadata và artifact của module được xem là changing | **24 giờ** | `2.1-SNAPSHOT` có artifact mới trên server |

Các con số ở hàng ví dụ chỉ là minh họa; phiên bản thực tế tùy repository tại thời điểm resolve.

### 7.1. Điều chỉnh TTL qua `ResolutionStrategy`

**Groovy DSL — mảnh cấu hình `build.gradle`:**

```groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
    resolutionStrategy.cacheChangingModulesFor 30, 'minutes'
}
```

**Kotlin DSL:**

```kotlin
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor(10, "minutes")
    resolutionStrategy.cacheChangingModulesFor(30, "minutes")
}
```

Ý nghĩa:

- `cacheDynamicVersionsFor 10, 'minutes'`: sau TTL dynamic, Gradle có thể truy vấn lại metadata để chọn version phù hợp từ kho.
- `cacheChangingModulesFor 30, 'minutes'`: sau TTL changing, Gradle có thể kiểm tra lại metadata và artifact của **cùng module/version**.
- `configurations.configureEach`: áp dụng chính sách cho các configuration của project khi được cấu hình, tránh phải gọi logic eager cho từng configuration.
- Hai TTL có thể chọn **khác nhau** vì mục tiêu khác nhau.
- Đây là **ví dụ cấu hình thay đổi chính sách cache của project**, không phải một yêu cầu bắt buộc cho mọi dự án.

Với một môi trường test chuyên tích hợp snapshot, bạn có thể thử `cacheChangingModulesFor 0, 'seconds'` để kiểm tra thường xuyên. Nhưng TTL quá ngắn gây thêm request, chậm build, tăng tải kho và làm kết quả dễ thay đổi giữa các lần chạy; không nên bật trên mọi máy/CI theo phản xạ.

### 7.2. TTL không phải lịch chạy tự động

“Cache 24 giờ” **không có nghĩa** Gradle tự tải mới đúng sau 24 giờ. Nó có nghĩa khi một lần resolve tương ứng xảy ra sau khi entry hết hiệu lực, Gradle có thể kiểm tra lại nguồn. Nếu không có build được chạy, sẽ không có việc refresh tự động. Nếu không có version/artifact mới trên kho, kết quả có thể giữ nguyên dù đã hết TTL.

Đối với môi trường doanh nghiệp có proxy/mirror, repository cũng có chính sách cache riêng. Một lệnh refresh ở Gradle client không thể làm xuất hiện artifact nếu mirror chưa đồng bộ hoặc server trả metadata lỗi.

## 8. `--refresh-dependencies` và `--offline`: hai lệnh đối lập về mục đích

Muốn kiểm tra nguồn remote lại trong một lần chạy:

```bash
./gradlew dependencies --configuration runtimeClasspath --refresh-dependencies
```

Hoặc chạy task cần resolution:

```bash
./gradlew compileJava --refresh-dependencies
```

**`--refresh-dependencies`** yêu cầu Gradle kiểm tra lại metadata/version/artifact theo repository được cấu hình, thay vì dùng nguyên thông tin đã cache theo TTL. Nó **không cam kết tải lại từng byte**: Gradle có thể dùng checksum và HTTP HEAD để xác nhận file đang cache không đổi, rồi tái sử dụng artifact hợp lệ.

Đừng hiểu lệnh này là “xóa toàn bộ Gradle cache”, “nâng toàn bộ module lên bản mới nhất” hoặc “chữa mọi lỗi phiên bản”. Với version cố định và không có change/graph override, selected version có thể vẫn như cũ.

Ngược lại:

```bash
./gradlew compileJava --offline
```

**`--offline`** dùng dependency cache hiện có và **không truy cập mạng để resolution**. Nếu module/metadata cần thiết chưa được cache, build có thể fail ngay cả khi repository remote có artifact hợp lệ. Với dynamic/changing, cache cũ có thể được sử dụng trong offline mode mà không kiểm tra version mới trên server.

| Tình huống | Lệnh phù hợp | Giới hạn |
| --- | --- | --- |
| Muốn dùng kết quả cache trong điều kiện bình thường | `./gradlew build` | Dynamic/changing có TTL riêng; cache có thể stale. |
| Muốn kiểm tra remote ngay lần này | `./gradlew build --refresh-dependencies` | Không tạo module chưa được publish; không sửa credentials. |
| Phải làm việc không có mạng | `./gradlew build --offline` | Chỉ có thể dùng module/metadata đã cache. |
| Muốn xem version được chọn | `./gradlew dependencyInsight --dependency module --configuration runtimeClasspath` | Chỉ kiểm tra một configuration cụ thể. |
| Muốn danh sách graph | `./gradlew dependencies --configuration runtimeClasspath` | Output tùy repository/constraints và version tại thời điểm resolve. |

**Không nên kết hợp `--offline` với mong muốn buộc lấy snapshot mới**: hai mục đích đó mâu thuẫn. Nếu cần artifact mới, phải có mạng/kho hoặc một cách cung cấp artifact được quản lý.

## 9. Ví dụ Gradle + Java 17 đầy đủ: bắt đầu bằng fixed version

Mục tiêu thực hành là tạo một ứng dụng Java 17 dùng thư viện có **version cố định** để có output đáng tin cậy, sau đó sửa *chính selector* để quan sát dynamic resolution. Chúng ta dùng Apache Commons Lang 3 đã phát hành trên Maven Central, không phụ thuộc kho snapshot nội bộ.

Thư mục:

```text
version-selectors-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
```

Yêu cầu:

- JDK 17 có thể dùng cho Java toolchain.
- Gradle Wrapper được cấu hình cho một Gradle 8.x tương thích, ví dụ **8.10.2**, hoặc phiên bản Wrapper hiện có của nhóm hỗ trợ Java 17.
- Có kết nối Maven Central cho lần tải đầu, hoặc dependency đã có trong cache.
- Các lệnh Unix dùng `./gradlew`; trên Windows dùng `gradlew.bat`.

Nếu chưa có Wrapper, trên máy đã cài Gradle thích hợp, có thể tạo một lần bằng:

```bash
gradle wrapper --gradle-version 8.10.2
```

Sau đó commit các file Wrapper vào repository khi làm trong nhóm. Không dùng lệnh tạo Wrapper để thay phiên bản dự án production mà chưa kiểm tra tương thích.

**`settings.gradle`:**

```groovy
rootProject.name = 'version-selectors-lab'
```

**`build.gradle` — bản đầy đủ, Groovy DSL:**

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}

application {
    mainClass = 'demo.Main'
}

// Chỉ phục vụ thực hành javac/java thủ công trong mục 9.2.
tasks.register('copyRuntimeDeps', Copy) {
    from(configurations.runtimeClasspath)
    into(layout.buildDirectory.dir('runtime-libs'))
}
```

**`src/main/java/demo/Main.java`:**

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Capitalize: " + StringUtils.capitalize("gradle"));
        System.out.println("Blank: " + StringUtils.isBlank("  \t  "));
    }
}
```

Giải thích:

- `application` là core Gradle plugin, cung cấp task `run` và Java support phù hợp.
- `repositories { mavenCentral() }` nói nơi lấy Commons Lang, **không tự chọn version**.
- `implementation '...:3.14.0'` yêu cầu version cụ thể.
- `java.toolchain.languageVersion = 17` yêu cầu JDK 17 cho các task Java liên quan.
- `Main.java` sử dụng trực tiếp `StringUtils` của thư viện ngoài, nên nếu dependency không resolve/không có trên classpath, Java compilation sẽ fail.
- Task `copyRuntimeDeps` chỉ để đưa các JAR runtime về thư mục dễ truy cập khi gọi `javac`/ `java` thủ công.

Chạy:

```bash
./gradlew --version
./gradlew -q run
```

Khi Maven Central truy cập được và không có cấu hình môi trường khác phá ví dụ, stdout **do Java in ra** là:

```text
Capitalize: Gradle
Blank: true
```

Đây là output của `Main.main`, không phải output cố định của toàn bộ Gradle console. Nếu dùng `-q`, log Gradle được giảm bớt nhưng lỗi resolution/compilation vẫn được báo.

### 9.1. Xem version thực sự được giải quyết

Dùng:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Trong ví dụ đơn giản chỉ khai báo Commons Lang 3.14.0, bản được chọn kỳ vọng là **3.14.0**. Nếu sửa build để có constraints hoặc dependency khác, kết quả có thể thay đổi; hãy đọc dependency insight thay vì coi version ở dòng `implementation` là kết quả cuối.

### 9.2. Biên dịch và chạy bằng `javac`/`java` sau khi Gradle đã tải thư viện

Vì `Main.java` import `org.apache.commons.lang3.StringUtils`, gọi thẳng `javac Main.java` **không đủ**: cần Commons Lang JAR trên classpath.

Từ root trên Unix:

```bash
./gradlew copyRuntimeDeps
mkdir -p manual-classes
javac -cp "build/runtime-libs/*" -d manual-classes src/main/java/demo/Main.java
java -cp "manual-classes:build/runtime-libs/*" demo.Main
```

Với `javac`/ `java` của JDK 17 và thư viện đã được copy, Java in:

```text
Capitalize: Gradle
Blank: true
```

Trên Windows CMD/PowerShell, tạo thư mục bằng `mkdir manual-classes` nếu chưa có; dấu phân cách classpath của Windows là **`;`**, ví dụ:

```powershell
.\gradlew.bat copyRuntimeDeps
mkdir manual-classes
javac -cp "build/runtime-libs/*" -d manual-classes src/main/java/demo/Main.java
java -cp "manual-classes;build/runtime-libs/*" demo.Main
```

`javac` và `java` chạy **mã Java**, còn Gradle quyết định dependency/version và đưa các JAR cần thiết về máy. Đây là cách phân biệt build tool/dependency management với Java compiler thực tế.

## 10. Thử dynamic version với cùng ứng dụng

Trong **một bản copy của project lab**, đổi đúng dòng dependency thành:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.+'
}
```

Lúc này không nên cam kết trong README rằng Gradle “sẽ luôn chọn 3.14.0” hay “sẽ luôn chọn bản cao nhất hiện có ngay bây giờ”. Phiên bản được chọn phụ thuộc metadata ở repository, các rules/constraints của graph và **dynamic version cache** trên máy.

Kiểm tra:

```bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath --refresh-dependencies
```

Hai lần resolution có thể cho cùng kết quả nếu không có version mới, hoặc kết quả khác nếu repository đã publish version phù hợp mới và không có ràng buộc khác. Lần hai chủ động kiểm tra lại nguồn thay vì đợi TTL cache mặc định.

Nếu bản Commons Lang 3.x được chọn vẫn cung cấp `StringUtils.capitalize` và `StringUtils.isBlank` tương thích Java 17, `./gradlew run` có thể chạy như trước. Nhưng dynamic selection có rủi ro bản mới thay yêu cầu JDK hoặc API. Khi build fail sau khi đổi selector, kiểm tra version thực tế và release notes trước khi thay code một cách mù quáng.

**Thử giới hạn bằng khoảng:**

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:[3.12,4.0)'
}
```

Selector này nêu khoảng được chấp nhận, nhưng **không tự bảo đảm chỉ chọn release đã qua kiểm thử**. Dùng dynamic để thử tương thích và **lock/pin** kết quả cho pipeline release khi phù hợp.

## 11. Thực hành mô hình SNAPSHOT/changing: phần minh họa có điều kiện

Vì Maven Central không phải kho để tự ý publish SNAPSHOT của tổ chức, những đoạn sau giả định bạn có **kho Maven snapshot nội bộ hợp lệ**. Đây là cấu hình minh họa để áp dụng vào một project thật sau khi thay repository URL, credentials và GAV:

```groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/snapshots')
        mavenContent {
            snapshotsOnly()
        }
    }
}

dependencies {
    implementation 'com.example.platform:billing-client:2.1.0-SNAPSHOT'
}
```

Muốn quan sát thay đổi nội dung:

1. Nhóm producer publish SNAPSHOT lần A.
2. Consumer resolve `2.1.0-SNAPSHOT` và lưu cache metadata/artifact.
3. Nhóm producer publish SNAPSHOT lần B **với cùng logical version**.
4. Consumer chạy lại trước khi changing cache hết TTL; có thể vẫn dùng bản A.
5. Sau TTL hoặc với `--refresh-dependencies`, nếu server/mirror trả metadata và artifact mới, consumer có thể lấy bản B.
6. Dùng kiểm tra tích hợp/giá trị artifact thực tế để xác minh, không chỉ nhìn chuỗi `2.1.0-SNAPSHOT`.

Nếu tổ chức publish lại version **không có `-SNAPSHOT`**, consumer có thể đánh dấu:

```groovy
dependencies {
    implementation('com.example.platform:billing-client:2.1.0') {
        changing = true
    }
}
```

Như vậy Gradle biết cần dùng **changing module TTL**. Tuy nhiên thay vì dùng việc publish lại release version lâu dài, tốt hơn nên thay quy trình phát hành thành **version bất biến** (mỗi build có version/commit identity riêng), nhất là với production.

**Không coi project lab ở mục 9 và snippet kho `.invalid` này là một build duy nhất có thể copy nguyên rồi chạy.** Cần một artifact snapshot thật và quyền truy cập đúng thì ví dụ snapshot mới resolve được.

## 12. Dependency locking: ổn định version động, không “đóng băng” SNAPSHOT

**Dependency locking** lưu lại **những version thực sự được giải quyết** cho configuration, bao gồm dependency bắc cầu, để lần chạy sau kiểm tra và giữ cùng tập version. Đây là cách quan trọng để sử dụng dynamic selector trong một môi trường cần tái lập.

Ví dụ trong `build.gradle`:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Kotlin DSL:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Sau khi bật locking, thực hiện một lệnh có resolution các configuration phù hợp:

```bash
./gradlew dependencies --write-locks
```

Gradle tạo/cập nhật **`gradle.lockfile`** theo project/configuration đã được resolve. Commit file đó vào version control sau khi kiểm tra kết quả. Một lần chạy sau vẫn có thể khai báo `3.+`, nhưng lockfile giữ version đã chọn khi locking áp dụng.

### 12.1. Một vòng đời cập nhật version động an toàn

1. Đội phát triển khai báo selector `3.+` nhằm chấp nhận bản Commons Lang mới trong nhánh được duyệt.
2. Chạy resolution với `--write-locks`, kiểm tra version được chọn.
3. Chạy `./gradlew test` / integration tests và kiểm tra các cảnh báo compatibility.
4. Review thay đổi `gradle.lockfile`, commit cùng source/config liên quan.
5. CI chạy với lock state để tránh tự nâng version sau mỗi TTL.
6. Khi muốn nâng lại, chủ động cập nhật lock file và kiểm thử, không sửa cache thủ công.

Muốn cập nhật một số module cụ thể, Gradle hỗ trợ:

```bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3
```

Cập nhật module có thể tác động các module bắc cầu theo các constraints. Review toàn bộ lock diff, không chỉ dòng dependency trực tiếp. Tùy multi-project và configuration nào được resolve, lock state có thể chỉ ghi những configuration thực sự tham gia; dùng đúng lệnh/task cho project cần khóa.

### 12.2. Không dùng locking để chứng minh changing version có nội dung bất biến

Gradle khuyến cáo **không dùng dependency locking như cách xử lý changing modules**, ví dụ `-SNAPSHOT`. Lockfile chứa logical version `2.1.0-SNAPSHOT`, nhưng artifact đằng sau version đó có thể đổi và Gradle cảnh báo khi lưu lock state có changing dependency.

Cần tái lập byte-for-byte thì phải:

- Dùng **version bất biến**, tốt nhất được publish một lần với metadata rõ ràng.
- Có thể kết hợp **dependency verification** (checksum/signature) để kiểm tra tính toàn vẹn artifact, nhưng không xem verification thay cho chính sách version immutable.
- Với môi trường đòi audit chặt, lưu tọa độ, checksum, nguồn repository và kết quả build/CI phù hợp.

Đây là điểm phân biệt quan trọng nhất: **locking giữ số version**, không khiến repository không thể publish lại file dưới cùng số version.

## 13. Version catalog giúp tập trung khai báo, không tự là lockfile

Với Gradle hỗ trợ version catalogs, bạn có thể đặt version ở `gradle/libs.versions.toml`:

```toml
[versions]
commonsLang = "3.14.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang" }
```

Và dùng trong `build.gradle`:

```groovy
dependencies {
    implementation libs.commons.lang3
}
```

Kotlin DSL:

```kotlin
dependencies {
    implementation(libs.commons.lang3)
}
```

Catalog giúp nhiều module dùng **cùng một yêu cầu version** và giảm lặp. Nó **không tự khóa resolved transitive graph** và không tự làm một `SNAPSHOT` trở thành immutable. Nếu trong catalog ghi `"3.+"`, đó vẫn là **selector động** và có rủi ro như khi ghi trực tiếp trong `implementation`.

Có thể dùng version catalog **cùng với** dependency locking và dependency verification: mỗi cơ chế giải quyết một vấn đề khác nhau. Đừng nhầm một danh sách version ở TOML với trạng thái resolution đã chốt trong lockfile.

## 14. Kiểm tra vì sao Gradle chọn một version khác mong đợi

Một dependency có thể xuất hiện ở nhiều nơi: trực tiếp trong module, transitive qua thư viện khác, trong platform/BOM hoặc do plugin thêm configuration. Vì thế xem `build.gradle` là chưa đủ.

Lệnh hữu ích cho Java project:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Những điều cần đọc:

- **Requested**: selector mà một cạnh dependency trong graph yêu cầu.
- **Selected**: version/component cuối mà Gradle chọn sau resolution.
- **Selection reasons**: nguyên nhân có thể bao gồm conflict resolution, constraint, forced version, rule hoặc dependency locking.
- **Repository/metadata**: khi artifact không tìm thấy hoặc version động không có lựa chọn hợp lệ, cần kiểm tra kho và metadata.

Ví dụ minh họa output của `dependencies`:

```text
+--- org.example:client:1.0
|    \--- org.apache.commons:commons-lang3:3.15.0
\--- org.apache.commons:commons-lang3:3.14.0 -> 3.15.0
```

Đây là **đồ thị giả định**, không phải stdout từ project lab ở mục 9. Mũi tên `3.14.0 -> 3.15.0` cho thấy yêu cầu trực tiếp một version nhưng graph chọn version khác. Thực tế các quy tắc constraint/platform/metadata có thể tạo kết quả khác.

**Không áp dụng duy nhất một kết quả cho mọi configuration:** `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath` và các configuration khác có thể có dependency graph khác nhau. Khi muốn debug một task compile/test cụ thể, kiểm tra configuration mà task ấy dùng.

## 15. Bài toán “cùng code, local chạy được nhưng CI fail”

Một tình huống phổ biến:

```groovy
dependencies {
    implementation 'com.example.platform:billing-client:2.+'
}
```

Local đã giải quyết version `2.4.0` và còn cache trong TTL, CI sạch thấy `2.5.0` mới publish. CI thất bại vì `2.5.0` đổi API, trong khi local vẫn compile được. Chưa chắc người nào “cấu hình Gradle sai”: đây là hệ quả có thể dự đoán của selector động cùng trạng thái cache khác nhau.

Tình huống khác:

```groovy
dependencies {
    implementation 'com.example.platform:billing-client:2.4.0-SNAPSHOT'
}
```

Local đang dùng artifact A, CI resolve artifact B đã publish lại cùng version. **Số version hiển thị có thể giống nhau**, nhưng bytecode khác. Đổi TTL cache có thể khiến local và CI “đồng bộ” nhất thời, nhưng không chữa được **tính biến đổi nội dung**.

Quy trình phân tích:

1. Chạy `./gradlew --version` để xem cùng Gradle Wrapper/JDK hay không.
2. Dùng `dependencyInsight` cho configuration thực sự liên quan, ghi lại requested và selected version.
3. Kiểm tra selector `+`, version range, `latest.*`, `-SNAPSHOT`, `changing = true`.
4. Kiểm tra `gradle.lockfile` nếu build có locking; xem lock state còn phù hợp không.
5. Xác nhận repository URL/mirror, metadata và quyền truy cập; cùng version không có nghĩa mọi mirror có cùng artifact mới nhất.
6. So sánh điều kiện cache: local/User Home, CI cache restore, thời điểm expire, `--offline`, `--refresh-dependencies`.
7. Nếu là changing module, so sánh checksum/artifact thực tế và quy trình publish, **không chỉ chuỗi version**.
8. Quyết định có chấp nhận nâng SNAPSHOT/dynamic cho nhánh này hay không, rồi cập nhật selector/lockfile bằng review và kiểm thử.

Tránh xóa `~/.gradle` của mọi người hoặc bật TTL bằng 0 vĩnh viễn chỉ để chữa một trường hợp. Những biện pháp đó có thể tạo nhiều yêu cầu mạng và che giấu lỗi của repository policy.

## 16. Rủi ro bảo mật và tái lập build

### 16.1. Dynamic version có rủi ro supply-chain

Khi selector tự chấp nhận bản mới, build có thể nhận artifact bạn chưa review. Việc nâng version tự động là một **quyết định quản lý rủi ro**: cần giới hạn repository được tin cậy, kiểm thử, quét dependency và có chiến lược rollback.

Nên dùng:

- Repository có chính sách quản lý (Maven Central, private mirror được duyệt).
- Dependency locking hoặc công cụ update dependency tạo PR để review.
- Version constraints khi API/JDK compatibility quan trọng.
- Dependency verification khi phù hợp để phát hiện artifact bị thay ngoài dự kiến.

Không dùng `latest.integration` trong release CI chỉ vì muốn “được cập nhật nhanh”. Nó có thể chấp nhận phiên bản chưa ổn định tùy metadata/status của repository.

### 16.2. SNAPSHOT có rủi ro khó tái hiện sự cố

Ngay cả khi commit cùng mã và cùng `gradle.lockfile`, người khác có thể không tìm được artifact SNAPSHOT cũ nếu repository chỉ giữ các bản mới. Khi release, ưu tiên **promote** artifact bất biến sang version phát hành hoặc lưu artifact theo build identity/checksum để truy xuất có kiểm soát.

### 16.3. Dependency cache không phải nguồn sự thật của release

Một máy phát triển có thể giữ JAR từ lần build cũ. Không nên coi “máy tôi có file trong cache” là xác nhận artifact đã được publish đúng repository, đúng version và đúng quyền. Build release cần được thử từ môi trường có thể dựng lại được và có lock/verification phù hợp.

## 17. Khi nào nên chọn phương án nào?

| Mục tiêu | Khuyến nghị | Tránh nhầm |
| --- | --- | --- |
| Release có yêu cầu tái lập | Version cụ thể, artifact bất biến, locking/verification khi cần | “Ghi `3.14.0` nên mọi bản bắc cầu cũng cố định”. |
| POC hoặc mẫu học Gradle | Fixed version đã biết tồn tại | Dùng `+` rồi ghi một stdout phụ thuộc bản mới nhất không kiểm soát. |
| CI kiểm tra tương thích với bản mới | Dynamic selector có giới hạn, pipeline kiểm thử riêng | Dùng chung một pipeline như release mà không kiểm soát version. |
| Hai nhóm đang phát triển tích hợp liên tục | Maven `-SNAPSHOT` trên kho phù hợp | Mong lockfile đóng băng byte của snapshot. |
| Kho nội bộ publish lại cùng version không snapshot | `changing = true` như biện pháp thích nghi tạm thời | Coi đó là quy trình phát hành release chuẩn. |
| Cần cập nhật module mới ngay hôm nay | `--refresh-dependencies` trong một lần chạy | Tưởng Gradle phải tải lại mọi JAR dù checksum như cũ. |
| Làm việc không có mạng | `--offline` với cache đủ | Mong nhận được snapshot mới từ server. |
| Nhiều module dùng chung version | Version catalog / constraints / platform | Nghĩ catalog tự đóng băng toàn dependency graph. |
| Cần tăng tần suất kiểm tra remote | Điều chỉnh TTL cho đúng mục tiêu, đo tác động | Đặt TTL 0 trên mọi configuration theo mặc định. |

**Quy tắc thiết kế:** càng gần môi trường production/release, bạn càng nên chuyển từ **“version thay đổi tự động”** sang **“version được chọn có chủ đích, có bằng chứng kiểm thử và có thể truy xuất lại artifact”**.

## 18. Lỗi thường gặp và cách sửa

| Lỗi/hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| `3.+` không lấy bản mới vừa publish | Dynamic selector mapping còn cache trong TTL hoặc mirror chưa đồng bộ | Dùng `--refresh-dependencies` có chọn lọc; xem repository metadata. |
| `2.0-SNAPSHOT` vẫn dùng bản cũ | Changing cache còn hiệu lực, proxy/mirror trả nội dung cũ | Refresh changing dependency; kiểm tra timestamp/metadata và checksum thực tế. |
| `--offline` báo module không tồn tại | Chưa cache module/metadata cần thiết | Chạy online một lần với đúng repo hoặc cung cấp artifact đã duyệt. |
| Ghi `3.14.0` nhưng selected thành `3.15.0` | Conflict resolution/constraints/platform | Dùng `dependencyInsight`, xem version graph và rich constraints nếu cần. |
| `latest.release` chọn bản không mong đợi | Module status metadata hoặc repository policy khác giả định | Kiểm tra status/metadata, repository filter và selector; pin bản release đã duyệt. |
| Snapshot không tìm thấy | Kho chỉ chứa release, sai GAV, credentials/URL hoặc metadata | Khai báo đúng snapshot repository, xác nhận publish và quyền truy cập. |
| Release build chọn artifact khác máy CI | Repo/mirror/cache thay đổi, artifact mutable | Dùng version bất biến, locking/verification, ghi lại nguồn/đầu ra. |
| Lockfile có SNAPSHOT vẫn khác byte | Lock chỉ khóa version logic, không khóa nội dung | Đừng dựa vào locking cho changing module; publish bản bất biến. |
| Thay `cacheDynamicVersionsFor` nhưng snapshot vẫn cũ | Đang cần `cacheChangingModulesFor` cho cùng tọa độ | Điều chỉnh đúng TTL theo loại thay đổi. |
| Đặt `changing=true` trên mọi dependency | Làm Gradle kiểm tra remote không cần thiết, tăng thời gian build | Chỉ đánh dấu module biết chắc mutable; sửa quy trình publish. |
| Dynamic chọn version không tương thích Java 17 | Bản mới yêu cầu JDK/API khác | Pin/strict đúng version, kiểm thử compatibility, xem release notes. |
| Gradle cache làm test “qua” trên máy cá nhân | Local artifact/metadata còn tồn tại, release remote đã khác | Thử trên CI/build sạch có kiểm soát, kiểm tra resolved version. |

### Hai phản xạ không nên có

- **“Cứ xóa hết cache là hết lỗi.”** Không chắc: nếu server vẫn publish SNAPSHOT sai, credentials sai hoặc metadata không nhất quán, lỗi sẽ tái xuất.
- **“Cứ ghi `strictly` là không cần kiểm thử.”** Sai: strict kiểm soát lựa chọn version chứ không chứng minh artifact an toàn, không đổi hay tương thích ứng dụng.

## 19. Bài tập tự kiểm tra

**Câu 1.** `implementation 'org.example:api:2.+'` có nghĩa version chắc chắn sẽ đổi ở mọi lần chạy Gradle không?

**Đáp án:** Không. Đây là selector động; Gradle có thể dùng kết quả cached trong TTL, và repository có thể chưa publish version mới.

**Câu 2.** `implementation 'org.example:api:2.4.0'` có chắc chắn selected version cuối luôn là `2.4.0` không?

**Đáp án:** Không trong mọi graph. Gradle có thể giải quyết xung đột/constraints để chọn version khác; cần `dependencyInsight` và nếu thật sự cần có thể dùng `strictly` hoặc locking.

**Câu 3.** `2.4.0-SNAPSHOT` có phải tự động mang ý nghĩa “luôn lấy bản mới bất kể cache” không?

**Đáp án:** Không. Maven SNAPSHOT có thể đổi nội dung nhưng Gradle vẫn cache changing modules (mặc định 24 giờ).

**Câu 4.** `cacheDynamicVersionsFor` và `cacheChangingModulesFor` khác nhau ra sao?

**Đáp án:** Cái đầu kiểm soát thời gian cache ánh xạ **selector động → resolved version**; cái sau kiểm soát metadata/artifact của **module changing**.

**Câu 5.** Một module `org.example:api:2.4.0` được publish lại với cùng GAV nhưng không có `-SNAPSHOT`. Có thể thông báo Gradle rằng module ấy changing không?

**Đáp án:** Có. Khai báo dependency với `changing = true` (Groovy) hoặc `isChanging = true` (Kotlin). Tuy nhiên publish lại release version không phải thực hành tốt cho production.

**Câu 6.** `--refresh-dependencies` có bắt buộc tải lại từng JAR dù remote checksum giống cache không?

**Đáp án:** Không. Gradle có thể xác minh metadata/checksum rồi dùng lại artifact nếu nội dung không đổi.

**Câu 7.** Một lockfile ghi `api:2.4-SNAPSHOT`. Nó có bảo đảm JAR SNAPSHOT không đổi giữa hai ngày không?

**Đáp án:** Không. Lock giữ version được chọn, không giữ byte của một changing module; Gradle còn cảnh báo về changing dependencies trong lock state.

**Câu 8.** Khi đã khai báo `libs.versions.toml` với `2.+`, bạn có dùng được version catalog để tự khóa bản chọn không?

**Đáp án:** Không. Catalog tập trung khai báo, còn dynamic resolution vẫn diễn ra; muốn khóa resolved versions cần dependency locking.

**Câu 9.** Trong ví dụ Java 17 ở mục 9, điều gì làm `StringUtils` compile được?

**Đáp án:** `implementation 'org.apache.commons:commons-lang3:3.14.0'` đưa JAR vào compile classpath sau khi Gradle resolve từ Maven Central; Gradle gọi compiler phù hợp với Java toolchain.

**Câu 10.** Muốn biết version nào được chọn sau conflict resolution, dùng `dependencies` hay `dependencyInsight`?

**Đáp án:** Cả hai giúp quan sát graph, nhưng `dependencyInsight --dependency ... --configuration ...` tập trung vào một module và nguyên nhân được chọn.

**Câu 11.** `latest.release` có nghĩa “bỏ qua cache và dùng đúng release vừa xuất bản cách một giây” không?

**Đáp án:** Không. Đây là version selector dựa trên status/metadata, vẫn chịu dynamic version caching và khả năng truy cập repository.

**Câu 12.** Vì sao không nên bật `cacheChangingModulesFor 0, 'seconds'` trên toàn bộ CI release?

**Đáp án:** Nó có thể làm build chậm, tăng request mạng và dễ lấy nội dung thay đổi giữa các invocation, trong khi release cần version/artifact bất biến và quy trình phê duyệt.

**Câu 13.** `[1.0, 2.0)` có chứa `2.0` không?

**Đáp án:** Không. Cận trái `[` bao gồm `1.0`; cận phải `)` loại `2.0`.

**Câu 14.** Nếu dynamic selector đã chọn bản `2.5.0` nhưng sau đó producer publish lại chính `2.5.0` với byte khác, dynamic TTL có giải quyết mọi vấn đề không?

**Đáp án:** Không. Đây còn là thay đổi **nội dung cùng tọa độ**; cần xem changing semantics và, tốt hơn, bảo đảm release artifact bất biến.

## 20. Nguồn đọc thêm

- [Gradle — Declaring Versions and Ranges](https://docs.gradle.org/current/userguide/dependency_versions.html): fixed, version range, `latest.release`, dynamic và changing modules.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): default TTL 24 giờ, `cacheDynamicVersionsFor`, `cacheChangingModulesFor`, `--refresh-dependencies`, `--offline`.
- [Gradle — Locking Versions](https://docs.gradle.org/current/userguide/dependency_locking.html): tạo/duy trì lockfile, khóa resolved versions, giới hạn với changing dependencies.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): đọc dependency graph và `dependencyInsight`.
- [Gradle — Declaring Rich Versions](https://docs.gradle.org/current/userguide/rich_versions.html): `strictly`, `require`, `prefer`, constraints.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): khai báo version tập trung, phân biệt catalog với resolution lock.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum/signature và yêu cầu tin cậy đối với artifact.

**Tóm tắt cần nhớ:** **Fixed** chọn một version cụ thể nhưng vẫn phải xét toàn graph; **dynamic** cho Gradle chọn version theo quy tắc có thể thay đổi; **Maven SNAPSHOT** là tọa độ phát triển có thể đổi artifact; **changing module** là cơ chế tổng quát để thông báo cùng tọa độ có nội dung mới. Hai TTL cache **dynamic/changing** đều mặc định **24 giờ** nhưng theo dõi hai việc khác nhau. Với release, ưu tiên **version và artifact bất biến**, kiểm thử, lockfile cho resolved versions và verification khi cần — không dựa vào cache hoặc lockfile để giả định SNAPSHOT không đổi.