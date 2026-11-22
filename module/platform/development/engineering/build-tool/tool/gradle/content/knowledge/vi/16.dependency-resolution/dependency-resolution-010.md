# Chẩn đoán dependency không tìm thấy, sai phiên bản hoặc thiếu artifact trong Gradle

## 1. Mục tiêu: tìm đúng nguyên nhân trước khi sửa build.gradle

Khi chạy `./gradlew build`, `compileJava`, `test` hoặc một task dùng dependency, Gradle có thể báo:

- `Could not find group:module:version`.
- `Could not resolve all files for configuration ':app:runtimeClasspath'`.
- `Could not find ...jar`, `...zip`, hoặc `Could not download ...`.
- `No matching variant of ... was found`.
- Version trong dependency tree không giống version mà bạn khai báo.
- Đã thêm repository nhưng build vẫn không tìm thấy module.
- Local build thành công, CI báo `No cached version ... available for offline mode` hoặc không thể xác thực private repository.

Không nên sửa bằng cách thêm repository ngẫu nhiên, chọn phiên bản mới nhất, xóa cache toàn máy, bật HTTP không bảo mật, hay thêm `resolutionStrategy.force` trước khi đọc log. Cùng một triệu chứng “không tải được dependency” có nhiều nguyên nhân và nhiều điểm sửa khác nhau.

**Sau bài học, bạn có thể:**

1. Phân biệt **graph resolution** (chọn component/version/variant) với **artifact resolution** (tìm và tải JAR/AAR/ZIP).
2. Xác định đúng `project` và `configuration` đang gặp lỗi.
3. Dùng `dependencies`, `dependencyInsight`, `--info` và `--stacktrace` đúng mục đích.
4. Phân loại lỗi module không có metadata, sai tọa độ/version, repository không phù hợp, thiếu artifact, xung đột/rule/constraint, variant mismatch, lỗi mạng/xác thực/cache.
5. Thiết kế thử nghiệm tái hiện an toàn: một build Java chạy được, rồi lần lượt mô phỏng **missing module**, **version khác kỳ vọng** và **missing artifact**.
6. Kiểm chứng việc sửa bằng báo cáo trước/sau và test; không biến một lỗi phân giải thành rủi ro chuỗi cung ứng.

> Phạm vi: **Gradle Groovy DSL** (`build.gradle`/`settings.gradle`) và dependency của project Java. Kotlin DSL có cú pháp khác. Các ví dụ chạy bằng Gradle Wrapper và Java 17+ trên Gradle tương thích; cần mạng ở lần đầu lấy thư viện từ Maven Central.

## 2. Hình dung hai bước phân giải

Giả sử project khai báo:

```groovy
dependencies {
    implementation 'commons-codec:commons-codec:1.16.0'
}
```

Đây là một **requested module dependency** với tọa độ Maven:

```text
group                 : commons-codec
module/artifact name  : commons-codec
version               : 1.16.0
```

Gradle không đơn giản lấy chuỗi này và tải một JAR theo tên đoán sẵn. Nó thực hiện các giai đoạn:

```text
Requested dependency + configuration attributes
                     |
                     v
        1. GRAPH RESOLUTION
        - Chọn repository phù hợp
        - Tìm metadata (.module, .pom, ivy.xml...)
        - Khám phá transitive dependencies
        - Áp dụng version constraints, BOM, conflicts, rules
        - Chọn component/version và matching variant
                     |
                     v
        2. ARTIFACT RESOLUTION
        - Xác định artifact mà variant công bố
        - Tìm/tải file từ repository nguồn
        - Kiểm tra download/verification/cache
                     |
                     v
       Classpath gồm các file thật (JAR, ...)
```

Đồ thị giải quyết được không bảo đảm file artifact tải thành công. Ví dụ, metadata của một module có thể tồn tại trong repository nhưng JAR mà metadata công bố bị thiếu, bị lỗi quyền truy cập hoặc sai checksum.

### 2.1. Ba câu hỏi định vị nhanh

| Câu hỏi | Nếu câu trả lời là không | Nơi tập trung |
| --- | --- | --- |
| **Gradle có thấy module và version được yêu cầu?** | `Could not find group:name:version` hoặc `No versions available`. | Tọa độ, repository, metadata, filter, release/snapshot. |
| **Gradle có chọn đúng component và variant?** | `requested 1.0 -> selected 2.0`, `No matching variant`, conflict/strict constraint. | `dependencyInsight`, constraints/BOM, rules, attributes. |
| **Gradle có lấy được file tương ứng?** | Artifact URL 404, `Could not download`, checksum mismatch, `@zip` không tồn tại. | Artifact publication, classifier/extension, authentication, network, cache. |

Cần phân biệt `NoClassDefFoundError` khi **chạy Java** với lỗi **Gradle không resolve được module**. Trường hợp đầu có thể do runtime dependency bị thiếu khỏi classpath dù Gradle đã resolve thành công một số thư viện; hãy điều tra `runtimeClasspath` và cách code được chạy.

## 3. Chọn đúng project và configuration

Một build có nhiều classpaths. Với plugin `java`:

| Triệu chứng | Configuration nên đọc |
| --- | --- |
| `compileJava` không có module/API | `compileClasspath` |
| Ứng dụng chạy lỗi classpath hoặc `run` thất bại | `runtimeClasspath` |
| `compileTestJava` không tìm thấy JUnit/Mockito | `testCompileClasspath` |
| Test chạy lỗi engine/driver | `testRuntimeClasspath` |
| Annotation processor không tải được | `annotationProcessor` (tuỳ plugin/version) |
| Plugin hoặc buildscript classpath gặp lỗi | `buildEnvironment` và `pluginManagement`, không chỉ app runtime. |

`implementation`, `runtimeOnly`, `testImplementation` thường là **declarable buckets** — nơi bạn khai báo. `compileClasspath` và `runtimeClasspath` là configuration **resolvable** — nơi bạn quan sát kết quả.

Ví dụ multi-project có `:app` và `:shared`:

```bash
./gradlew -q :app:dependencies --configuration runtimeClasspath
./gradlew -q :app:dependencyInsight --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec
```

Hai lệnh chỉ dùng được khi `:app` thực sự tồn tại. Với single-project, bỏ `:app:`. Khi không rõ configuration nào resolvable, xem:

```bash
./gradlew -q resolvableConfigurations
```

Không nhìn đồ thị ở root rồi kết luận lỗi của subproject đã được giải quyết; repository/constraint/configuration có thể khác nhau theo project và plugin.

## 4. Lệnh chẩn đoán cốt lõi

### 4.1. Đọc lỗi gốc, không chỉ dòng cuối cùng

Chạy lại chính task đã thất bại, yêu cầu Gradle hiển thị ngữ cảnh:

```bash
./gradlew compileJava --info --stacktrace --console=plain
```

- `--info` cho thêm log về quá trình cấu hình/phân giải và các bước Gradle thực hiện.
- `--stacktrace` cho chuỗi exception và nguyên nhân lồng nhau.
- `--console=plain` giúp log dễ lưu và tìm kiếm.
- `--debug` chi tiết hơn nhưng có thể tạo log rất lớn; tránh chia sẻ nguyên log nếu có URL nội bộ, thông tin xác thực hay metadata nhạy cảm.

**Cách đọc:** bắt đầu ở exception chính như `Could not resolve all files for configuration ...`, rồi đi xuống các phần `Caused by`, `Could not find ...`, `Searched in the following locations` hoặc thông báo HTTP/TLS. Đường dẫn URL mà Gradle thử phản ánh **repository layout thực sự**, rất hữu ích để phát hiện sai địa chỉ hoặc version.

### 4.2. Xem cây dependencies

```bash
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencies --configuration compileClasspath
```

Đọc các ký hiệu:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `+---` / `\---` | Các nhánh component trong dependency tree. |
| `1.0 -> 2.0` | Yêu cầu 1.0 nhưng selected component là 2.0 trong configuration này. |
| `(*)` | Subtree đã xuất hiện ở nơi khác nên chỉ nhắc lại node; không có nghĩa dependency bị loại. |
| `(c)` | Dependency **constraint**, không phải một artifact tự được tải bởi chính dòng đó. |
| `(n)` | Dependency hoặc configuration **không thể được resolved** trong ngữ cảnh report; không coi là version đã chọn. |
| `FAILED` | Có nhánh không giải quyết thành công; đọc exception và các locations đã thử. |

Khi resolution thất bại nặng, report cũng có thể lỗi hoặc không cung cấp toàn bộ tree; khi đó **log lỗi gốc có giá trị ưu tiên**, không cố lấy `dependencyInsight` làm “bằng chứng phải có”.

### 4.3. Hỏi vì sao một version được chọn

```bash
./gradlew -q dependencyInsight \
  --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec
```

Báo cáo cho thấy **selected version**, các đường yêu cầu (*dependency paths*) và **Selection reasons** như:

- `By conflict resolution`: nhiều version được yêu cầu và Gradle xử lý xung đột.
- `By constraint`: constraint/BOM tham gia lựa chọn.
- `Forced`: force hoặc enforced platform áp đặt version.
- `Selected by rule`: resolution rule can thiệp.
- `By ancestor`: yêu cầu rich version `strictly` từ nhánh cha.
- `Was requested`: yêu cầu thông thường, có thể kèm `because`.

Cờ `--single-path` chỉ giữ một đường dẫn để đọc gọn; **không dùng để kết luận chỉ có một nguồn**. Cờ `--all-variants` giúp xem thêm thông tin về variants khi metadata hỗ trợ. Nếu module hoàn toàn không tồn tại và graph không thể resolve, dependencyInsight có thể báo failure; tra message chứa repository URLs trước.

### 4.4. Ghi baseline

Trước khi sửa, lưu những thông tin sau trong ghi chú của bạn:

```text
Project path:
Task bị lỗi:
Configuration:
Requested group:name:version:
Selected group:name:version (nếu có):
Dòng lỗi gốc / cause:
Repository URL đã được thử:
Metadata tìm thấy? Artifact được tải?
Mạng/credentials/SSL/offline?
Constraints/BOM/lockfiles/rules liên quan:
Gradle Wrapper version và JDK:
```

Lưu log bằng redirect nếu cần:

```bash
./gradlew dependencies --configuration runtimeClasspath \
  > deps-before.txt

./gradlew dependencyInsight --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec \
  > insight-before.txt
```

Các file log có thể chứa tên repository nội bộ; không công khai nguyên bản. Ở Windows PowerShell, chạy mỗi lệnh trên một dòng với `.\gradlew.bat`; toán tử `>` hoạt động nhưng encoding phụ thuộc phiên bản PowerShell.

## 5. Nhóm lỗi A — Không tìm thấy module hoặc version

Ví dụ thông báo (minh họa, đường dẫn và wording phụ thuộc Gradle):

```text
Could not find invalid.example:missing-module-demo:0.0.0.
Searched in the following locations:
    https://repo.maven.apache.org/maven2/invalid/example/...
Required by:
    project :
```

Hãy lần lượt xác minh các lớp:

### 5.1. Tọa độ phải chính xác

Định dạng Maven:

```text
group : artifact/module : version
```

Phân biệt:

- `group`: namespace xuất bản; không mặc định trùng Java package.
- `artifact/module`: tên module trong repository, không nhất thiết trùng tên JAR do người dùng tự suy đoán.
- `version`: chuỗi release đã **thực sự được publish**, không phải số version ghi trong README mới nhất của một framework.
- `classifier`/extension`: chỉ định artifact khác mặc định, có thể không tồn tại.

Sai group, gạch nối, chữ hoa/thường, `SNAPSHOT`, classifier hay version chưa phát hành đều có thể gây `Could not find`. Tọa độ Maven thường được kiểm tra tại Maven Central hoặc repository chính thức của nhà xuất bản, không dựa vào suy đoán từ tên package import.

### 5.2. Đúng repository và đúng scope chưa?

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'commons-codec:commons-codec:1.16.0'
}
```

Đây là đoạn cấu hình **project dependencies** của Groovy DSL. Đừng nhầm với:

- `pluginManagement { repositories { ... } }` trong `settings.gradle`: phục vụ **plugin resolution** của `plugins { }`.
- `buildscript { repositories { ... } }`: phục vụ các dependency của **buildscript classpath**.
- `dependencyResolutionManagement { repositories { ... } }` trong `settings.gradle`: cấu hình tập trung cho **project dependencies**.
- `publishing { repositories { ... } }`: đích **upload/publish**, không tự trở thành nguồn tải dependency khi compile.

Dự án tập trung repository trong `settings.gradle` có thể dùng:

```groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}
```

Đoạn này là **một mô hình thay thế** cho cấu hình `repositories` ở `build.gradle`, không dán cả hai nếu `FAIL_ON_PROJECT_REPOS` đã được bật. Khi repository mode là `FAIL_ON_PROJECT_REPOS`, mọi khai báo project repository (kể cả do plugin thêm) có thể khiến build fail; sửa tại nguồn settings thay vì thêm tiếp repository vào project.

**Không giả định thêm `mavenCentral()` luôn chữa được vấn đề**: một library private cần kho nội bộ, snapshot có thể cần snapshot repository, plugin ID cần plugin repositories, còn content filter có thể chặn một group dù URL repository hoàn toàn chính xác.

### 5.3. Repository filters và thứ tự

Gradle hỗ trợ `content { includeGroup ...; excludeGroup ... }` và `exclusiveContent`. Ví dụ một private group bị giới hạn vào nội bộ:

```groovy
dependencyResolutionManagement {
    repositories {
        maven {
            url = uri('https://repo.example.invalid/releases')
            content {
                includeGroup 'com.mycompany'
            }
        }
        mavenCentral()
    }
}
```

**Đây là sơ đồ cấu hình**, URL `repo.example.invalid` cố ý không có thật, không phải lệnh runnable. Một filter `includeGroup 'com.mycompany'` trên repository đó sẽ không cho Gradle tìm `commons-codec` ở kho này. Với `exclusiveContent`, nhóm được chỉ định còn có thể bị **cấm** resolve ở các repository khác. Kiểm tra rules và group chính xác trước khi thêm repository.

**Thứ tự repository quan trọng**: Gradle tìm metadata qua các repositories theo thứ tự; khi đã tìm thấy metadata trong một repository, artifact được lấy từ **repository gắn với metadata đó**, không tự trộn JAR từ repository sau. Với private cache/mirror hoặc `mavenLocal()` chứa POM thiếu JAR, project có thể gặp “missing artifact” dù Maven Central có file; đừng mặc định đảo thứ tự ngẫu nhiên sẽ an toàn, mà phải sửa publication hoặc phân luồng repository có chủ đích.

### 5.4. Release, snapshot, dynamic version

Một version `1.2.3-SNAPSHOT` có thể chỉ tồn tại trong kho snapshot. Repository có thể khai báo:

```groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/snapshots')
        mavenContent {
            snapshotsOnly()
        }
    }
}
```

URL trên là **minh họa**, thay bằng kho snapshot HTTPS hợp lệ của tổ chức. `snapshotsOnly()` loại release khỏi kho đó, còn `releasesOnly()` làm ngược lại. Đừng xóa suffix `-SNAPSHOT` để “sửa” nếu chưa có release tương ứng.

Các version động như `1.+` hoặc `latest.release` phụ thuộc repository metadata và chính sách cache; nhiều dự án ưu tiên version cố định, kiểm thử và dependency locking để tạo build có thể tái lập.

## 6. Nhóm lỗi B — Chọn sai version hoặc version bị áp đặt

Ví dụ:

```groovy
dependencies {
    implementation 'commons-codec:commons-codec:1.15'
    implementation 'commons-codec:commons-codec:1.16.0'
}
```

Hai yêu cầu cùng `group:name` nhưng khác version. Nếu không có constraint/force/rule khác, Gradle thường chọn `1.16.0` trong cùng configuration.

Báo cáo minh họa:

```text
runtimeClasspath
+--- commons-codec:commons-codec:1.15 -> 1.16.0
\--- commons-codec:commons-codec:1.16.0
```

Mũi tên `1.15 -> 1.16.0` **không** có nghĩa hai JAR được dùng song song; nó diễn tả **requested → selected**. Khi nghi ngờ version sai, chạy:

```bash
./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec
```

Đọc chính xác **Selection reasons** và mọi đường đến module. Các nguồn có thể quyết định selected version:

| Cơ chế | Cần tìm ở đâu? | Điểm thận trọng |
| --- | --- | --- |
| Conflict resolution | Các yêu cầu trực tiếp và bắc cầu trong dependency tree. | Chọn version cao hơn không bảo đảm tương thích API/ABI. |
| Dependency constraint | `constraints { }`, platform/BOM. | Constraint không tự thêm module; nó ảnh hưởng lựa chọn khi module có mặt. |
| Version catalog | `gradle/libs.versions.toml`. | Catalog định nghĩa requested version, **không bảo đảm selected version**. |
| `strictly`/`reject` | Rich version constraints. | Có thể làm resolution fail khi không còn version chung hợp lệ. |
| `resolutionStrategy.force` | Build logic/convention plugin. | Che nguyên nhân, nguy cơ chọn bản không tương thích. |
| Dependency substitution | Settings/build logic/composite build. | Module có thể bị thay bằng project khác. |
| Dependency locking | Lockfiles theo configuration. | Có thể giữ version được khóa hoặc báo lỗi khi yêu cầu không tương thích. |

**Chọn hướng sửa nhỏ nhất** sau khi biết nguyên nhân: xóa khai báo trùng không cần thiết, nâng dependency cha, điều chỉnh constraint/BOM có lý do, hoặc cập nhật lockfiles **theo quy trình được kiểm soát**. Đừng thêm `force` chỉ để log đẹp.

### 6.1. Nếu phiên bản không tồn tại thì khác conflict

Một yêu cầu cố định `commons-codec:commons-codec:9999.0` có thể đơn giản là **version chưa được publish**. Không gọi đó là xung đột nếu báo cáo không chọn được component. Kiểm tra repository và version trước, sau đó mới xét constraints.

Nếu một version đã tồn tại nhưng Gradle không chọn vì attributes/capabilities hoặc strict constraint, hãy đọc error thực tế. Không mặc định “không tìm thấy” đồng nghĩa version đó chưa từng phát hành.

## 7. Nhóm lỗi C — Metadata tìm thấy nhưng thiếu artifact

### 7.1. Component và file khác nhau

Một Maven module có thể chứa `.pom` và một hoặc nhiều `.jar`, hoặc có packaging `pom` cho BOM và **không có JAR mặc định**. Một Gradle Module Metadata `.module` có thể công bố variants với artifact riêng. Khi thiếu file, Gradle có thể đã chọn **đúng component** nhưng không lấy được artifact của variant đã chọn.

Các trường hợp:

1. Repository chứa POM hoặc `.module` mô tả `module:version`, nhưng JAR được tham chiếu chưa upload.
2. Người dùng yêu cầu classifier như `sources` hoặc `tests` nhưng nhà phát hành không công bố artifact đó.
3. Người dùng yêu cầu extension `@zip` trong khi repository chỉ có `.jar`.
4. Repository đầu tiên chứa metadata nhưng thiếu artifact; Gradle không tự ghép metadata từ kho A với JAR từ kho B.
5. Metadata công bố artifact cho **variant khác** với nhu cầu của consumer.
6. HTTP 401/403, proxy/SSL, timeout hoặc verification failure khiến file **có tồn tại** nhưng không tải/không chấp nhận được.

**Đừng đổi version khi log chỉ rõ thiếu classifier hoặc extension**. Xem metadata/POM và URL Gradle đang truy cập trước.

### 7.2. Artifact-only notation dùng có chủ đích

Ví dụ **chỉ để phân tích**, không phải khuyến nghị khai báo phổ thông:

```groovy
dependencies {
    implementation 'commons-codec:commons-codec:1.16.0@zip'
}
```

Cú pháp `@zip` yêu cầu file ZIP tương ứng, **bỏ qua metadata-based dependency resolution** cho dependency này. Maven Central bình thường công bố Commons Codec 1.16.0 dưới dạng JAR, không phải ZIP cùng tọa độ, vì vậy lệnh compile dùng dependency này được kỳ vọng thất bại ở artifact lookup.

**Quan trọng:** `@jar`, `@zip` và dạng `@extension` làm mất transitive dependency graph, variant-aware resolution và capabilities mà metadata thường cung cấp. **Không** thêm `@jar` làm cách “sửa” mọi module thiếu metadata; đây chỉ là cơ chế cần thiết khi làm việc với kho/định dạng đặc biệt được kiểm soát.

Nếu cần artifact với classifier, có cú pháp `group:name:version:classifier@extension` cho tình huống phù hợp. Chỉ định classifier mà không kiểm tra publication sẽ tạo thêm lỗi không có file.

### 7.3. Metadata sources: không bật artifact() bừa bãi

Gradle có `metadataSources` cho Maven/Ivy repositories; các lựa chọn gồm `gradleMetadata()`, `mavenPom()`, `ivyDescriptor()` và `artifact()` ở repository hỗ trợ.

Ví dụ dưới đây **chỉ minh họa kho nội bộ không có metadata**:

```groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/artifacts-only')
        metadataSources {
            mavenPom()
            artifact()
        }
    }
}
```

Tùy chọn `artifact()` cho phép nhận diện module chỉ dựa vào file tồn tại, ngay cả khi thiếu POM/Module Metadata; nó có thể bỏ qua thông tin transitive dependencies, variants và kiểm chứng metadata. **Không bật rộng trên repository public/untrusted** chỉ để hết lỗi 404: nên sửa quá trình xuất bản POM/metadata đúng, hoặc dùng repo nội bộ tin cậy kèm chính sách rõ ràng. URL `example.invalid` cố tình không truy cập được.

### 7.4. Phân biệt BOM với missing JAR

Ví dụ:

```groovy
dependencies {
    implementation platform('org.junit:junit-bom:5.11.4')
}
```

BOM thường được publish dưới dạng POM chứa constraints, không phải thư viện class có JAR. Việc không thấy JAR `junit-bom` là **bình thường**, không phải lỗi, vì `platform(...)` yêu cầu platform metadata. Trái lại, nếu khai báo một BOM như thư viện implementation thông thường rồi chờ nó cung cấp Java classes, cấu hình đó đang sai mục đích. Dùng loại dependency phù hợp với publication.

## 8. Nhóm lỗi D — Variant không khớp

Khi Gradle báo:

```text
No matching variant of project :library was found.
The consumer was configured to find ...
```

có thể module/version vẫn tồn tại; vấn đề là **attributes của consumer** không khớp các variants producer cung cấp.

Ví dụ các thuộc tính thường gặp:

- `org.gradle.usage`: `java-api` hay `java-runtime`.
- `org.gradle.jvm.version`: mức Java tương thích yêu cầu.
- `org.gradle.libraryelements`: `jar`, `classes` hoặc loại khác.
- `org.gradle.category`: library, platform, documentation...
- Capabilities, native target, Android flavor hoặc các attributes do plugin thêm.

Lệnh đọc thêm thông tin:

```bash
./gradlew -q resolvableConfigurations
./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec --all-variants
```

Trong multi-project có `:library`, có thể dùng:

```bash
./gradlew -q :library:outgoingVariants
```

Nếu module không resolve được, `dependencyInsight` có thể không cung cấp full variant report; **đọc error về requested/provided attributes** trước. Sửa đúng là cấu hình Java toolchain/usage/capability/variant publication phù hợp, không phải luôn nâng hoặc hạ module version. Đừng đổi `java-runtime` sang `java-api` chỉ để che một ràng buộc thực sự về compatibility.

## 9. Nhóm lỗi E — Mạng, credentials, SSL, proxy và repository không sẵn sàng

Một URL HTTP trong log không đủ để kết luận module “không tồn tại”:

| Thông tin từ log | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `404 Not Found` | Sai URL/group/version/artifact, hoặc private server cố ý trả 404 khi thiếu xác thực. | Xem URL layout, xác minh publication và access rules. |
| `401 Unauthorized` | Chưa cấp credentials hoặc cơ chế xác thực không khớp. | Kiểm tra credentials/secret store, không ghi mật khẩu vào log. |
| `403 Forbidden` | Tài khoản thiếu quyền đọc repository/artifact. | Xin cấp quyền hoặc dùng identity phù hợp. |
| `407 Proxy Authentication Required` | Proxy yêu cầu authentication. | Cấu hình proxy theo chính sách tổ chức. |
| `Connection timed out`/`UnknownHostException` | DNS, VPN, firewall, proxy hoặc repository đang lỗi. | Kiểm tra mạng từ **môi trường đang build** (CI/runner/container). |
| `SSLHandshakeException`/certificate path | TLS trust chain, CA công ty, proxy TLS interception. | Cấu hình trust store/CA tin cậy, không tắt TLS verification. |
| `checksum mismatch`/verification failure | Artifact bị thay đổi, metadata xác minh sai hoặc supply-chain risk. | Dừng và đối chiếu checksum/PGP từ publisher chính thức; không vô hiệu hóa verification để né lỗi. |
| `429 Too Many Requests` | Repository rate limit. | Giảm tải, dùng mirror/cache được cấp phép, xử lý retry theo chính sách. |
| `5xx` | Server hoặc mirror không sẵn sàng. | Kiểm tra service và repository status, retry có kiểm soát. |

### 9.1. Credentials cho kho nội bộ

Mẫu minh họa cấu hình repository riêng:

```groovy
repositories {
    maven {
        name = 'internal'
        url = uri('https://repo.example.invalid/maven')
        credentials(PasswordCredentials)
    }
}
```

Khi dùng `PasswordCredentials` với repository tên `internal`, Gradle có thể lấy `internalUsername` và `internalPassword` từ các nguồn Gradle property hỗ trợ. Dùng private user-home `gradle.properties` hoặc CI secret provider; không commit mật khẩu trong repository. Một số server phản hồi 404 trước khi có authentication challenge, vì thế chẩn đoán 404 ở private repo phải xem cả chính sách xác thực.

**Đừng dùng URL HTTP chỉ để “dễ tải”**. Gradle mặc định từ chối HTTP không an toàn; bật `allowInsecureProtocol = true` là hạ cấp bảo mật và không phải giải pháp chuẩn. Hãy yêu cầu HTTPS hoặc một proxy TLS đáng tin cậy.

### 9.2. CI khác máy local

Nếu local thành công nhưng CI fail:

1. Đảm bảo cùng Gradle Wrapper/JDK.
2. So sánh `settings.gradle`, repository mode, init scripts, mirror rules và credentials của runner.
3. Kiểm tra VPN, proxy, firewall, DNS, CA trust store trong môi trường CI.
4. Xem CI có đang chạy `--offline` hoặc dùng cache khác.
5. Kiểm tra artifact ở repository được phép, không chỉ trên máy local.
6. Không copy toàn bộ `~/.gradle/caches` từ một máy sang máy khác như “cách sửa” mặc định; cache và metadata gắn với repository/Gradle behavior.

Gradle có metadata cache theo repository (URL, type, layout), có cả negative cache khi module/artifact không tồn tại. Khi đã chọn metadata từ một repository, artifact có quan hệ với nguồn đó (**repository stickiness**). Đây là lý do việc thêm một kho mới không luôn giải quyết lỗi thiếu JAR từ kho cũ.

## 10. Hiểu đúng --offline, --refresh-dependencies và cache

| Cờ | Tác dụng | Không làm được gì? |
| --- | --- | --- |
| `--offline` | Không truy cập mạng; chỉ dùng metadata/artifacts sẵn có trong cache. | Không tải dependency chưa từng có trong cache; không chứng minh artifact không được publish. |
| `--refresh-dependencies` | Buộc Gradle kiểm tra trạng thái dependency metadata/artifacts với repositories theo cơ chế cache. | Không đổi tọa độ sai, không tự chọn version khác nếu constraint/lock áp đặt, không bảo đảm redownload mọi JAR byte-for-byte. |
| `--info` | Cho nhiều thông tin về resolution/thao tác. | Không tự sửa lỗi. |
| `--stacktrace` | Hiển thị exception chain. | Không phải bằng chứng rằng version ở repository tồn tại. |
| `--debug` | Log rất chi tiết, có thể chứa thông tin nhạy cảm. | Không nên chia sẻ công khai log thô. |

Thử lại có kiểm soát nếu nghi cache/metadata cũ:

```bash
./gradlew compileJava --refresh-dependencies --info --console=plain
```

Nếu sau refresh vẫn báo `Could not find ...` với cùng URL, hãy kiểm tra publication và tọa độ. Nếu trong `--offline` báo “No cached version”, chạy online (nếu được phép) để tải; không xóa toàn bộ cache như bước đầu tiên.

**Không nhầm cache dependency với build cache**: cache dependency lưu metadata/artifacts tải từ repository; build cache lưu output của các task đủ điều kiện. Xóa `build/` hoặc chạy `clean` không sửa dependency coordinates. Xóa toàn bộ Gradle cache có thể làm tăng traffic, mất dữ liệu cần dùng ở chế độ offline và che nguyên nhân ban đầu.

## 11. Lab thực hành: một project Java và ba dạng lỗi

Để học mà không làm hỏng dự án thật, tạo **thư mục thực hành riêng** với Gradle Wrapper/JDK đã hoạt động. Các ví dụ lỗi dưới đây là **những lần sửa độc lập trên một bản lab**, không áp dụng đồng thời.

### 11.1. Project baseline: phụ thuộc hợp lệ

Cấu trúc:

```text
dependency-diagnosis-lab/
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── settings.gradle
├── build.gradle
└── src/main/java/example/HexDemo.java
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'dependency-diagnosis-lab'
```

**File `build.gradle`:**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'commons-codec:commons-codec:1.16.0'
}

application {
    mainClass = 'example.HexDemo'
}
```

Plugin `application` bao gồm chức năng Java, tạo `compileJava` và task `run`. Thư viện Commons Codec 1.16.0 là một bản phát hành cố định dùng làm lab, không phải khẳng định phiên bản mới nhất.

**File `src/main/java/example/HexDemo.java`:**

```java
package example;

import org.apache.commons.codec.binary.Hex;

public final class HexDemo {
    private HexDemo() {
    }

    public static void main(String[] args) {
        byte[] data = {0x61, 0x62};
        System.out.println(Hex.encodeHexString(data));
    }
}
```

Java 17+ có thể biên dịch class này khi classpath chứa Commons Codec. Chạy trên Linux/macOS:

```bash
./gradlew -q run --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat -q run --console=plain
```

**Stdout của ứng dụng** (khi không có thông điệp lỗi từ Gradle):

```text
6162
```

Hai byte `0x61` và `0x62` là ASCII `a` và `b`; `Hex.encodeHexString` trả `6162`. Task `run` tải dependency (nếu chưa có cache), biên dịch source và chạy chương trình. Cờ `-q` chỉ làm log Gradle gọn, không tắt stdout của ứng dụng.

Kiểm tra baseline:

```bash
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencyInsight \
  --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec
```

Trong report, bạn phải tìm thấy module `commons-codec:commons-codec:1.16.0`. Nếu baseline đã không chạy được, **không tiếp tục mô phỏng lỗi**: trước hết xử lý Java/Wrapper, mạng, repository và Maven Central theo thông báo thật.

### 11.2. Tình huống A — Module không tìm thấy

**Thay đúng dòng `implementation` trong lab** bằng tọa độ cố ý không tồn tại:

```groovy
dependencies {
    implementation 'invalid.example:missing-module-demo:0.0.0'
}
```

Đây là **đầu vào lỗi có chủ đích**. Chạy:

```bash
./gradlew compileJava --console=plain
```

Kỳ vọng `compileJava` **FAIL**, vì compiler cần resolution của `compileClasspath` nhưng module giả không có trong Maven Central. Dạng message thường chứa:

```text
Could not resolve all files for configuration ':compileClasspath'.
Could not find invalid.example:missing-module-demo:0.0.0.
Required by:
    root project :
```

Đây là **trích đoạn minh họa**, không phải toàn bộ stderr. Tùy phiên bản Gradle, đường repository sẽ xuất hiện trong phần `Searched in the following locations` hoặc thông tin mở rộng.

**Bài phân tích:** xác minh group/artifact/version trước; xem Maven Central có đúng tọa độ hay không. Không đổi `repository` sang một URL tùy tiện để làm module giả trở nên “tồn tại”. Sau thử nghiệm, **khôi phục** `commons-codec:commons-codec:1.16.0`.

### 11.3. Tình huống B — Version được chọn khác kỳ vọng

**Chỉ trong bản lab đã khôi phục**, thay block dependencies bằng:

```groovy
dependencies {
    implementation 'commons-codec:commons-codec:1.15'
    implementation 'commons-codec:commons-codec:1.16.0'
}
```

Chạy:

```bash
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencyInsight \
  --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec
```

Với hai yêu cầu cố định trên và không có constraint khác, Gradle thường chọn `1.16.0`; cây minh họa:

```text
runtimeClasspath
+--- commons-codec:commons-codec:1.15 -> 1.16.0
\--- commons-codec:commons-codec:1.16.0
```

`dependencyInsight` sẽ cho biết conflict selection và các đường yêu cầu. **Không đánh đồng version đang khai báo với version trên classpath**. Nếu cả hai khai báo thực tế do nhầm lẫn, loại bỏ dòng cũ là một biện pháp sửa có thể review. Sau khi sửa, xem lại resolved graph thay vì chỉ kiểm tra file `build.gradle` đã thay đổi.

### 11.4. Tình huống C — Yêu cầu artifact không được xuất bản

**Khôi phục một dependency duy nhất trước**, rồi đổi nó thành:

```groovy
dependencies {
    // Chỉ là ví dụ cố tình lỗi: Commons Codec publish JAR, không phải ZIP này.
    implementation 'commons-codec:commons-codec:1.16.0@zip'
}
```

Chạy:

```bash
./gradlew compileJava --console=plain
```

Kỳ vọng **FAIL do không tìm thấy ZIP artifact**, không nhất thiết vì module/version Maven “không tồn tại”. Tìm phần log chứa URL file `commons-codec-1.16.0.zip` hoặc message artifact lookup tương đương.

**Điểm học:** hậu tố `@zip` thay đổi thứ bạn yêu cầu tải và bỏ qua resolution metadata của module đó. **Sửa bằng cách trở lại dependency tọa độ chuẩn**:

```groovy
dependencies {
    implementation 'commons-codec:commons-codec:1.16.0'
}
```

Không cần bật `metadataSources { artifact() }` hay `--refresh-dependencies` chỉ vì mình đã chủ động yêu cầu sai extension.

### 11.5. Kiểm tra kết quả sau khi khôi phục

```bash
./gradlew -q run --console=plain
./gradlew -q dependencies --configuration runtimeClasspath
```

Ứng dụng lại in chính xác `6162`; cây dependency chỉ có một requested version Commons Codec trong build mẫu. Khi làm việc với dự án thật, ngoài compile/run cần chạy `test`, integration tests và kiểm tra phiên bản đã resolve trong configuration tương ứng.

## 12. Chẩn đoán thực tế theo cây quyết định

```text
Build không resolve được dependency?
|
+-- Lỗi ở plugins { } / buildscript?
|      -> pluginManagement / buildscript.repositories / plugin versions.
|
+-- Lỗi ở project compilation/test/runtime?
       |
       +-- Chọn đúng project + resolvable configuration.
       |
       +-- Could not find group:name:version?
       |      -> Tọa độ + version publish?
       |      -> Repository URL/scope/order/filter?
       |      -> release/snapshot/private auth/offline?
       |
       +-- Resolved nhưng version không đúng kỳ vọng?
       |      -> dependencies / dependencyInsight.
       |      -> conflict, constraint/BOM, force, strict, rule, lockfile?
       |
       +-- Missing JAR/ZIP/classifier/artifact?
       |      -> Metadata có chưa? Artifact publication chính xác?
       |      -> @extension/classifier/variant, sticky repository?
       |
       +-- No matching variant?
       |      -> usage, JVM target, attributes, capabilities?
       |
       +-- Network / auth / verification?
              -> HTTP status, proxy, TLS CA, checksum/PGP.
```

### 12.1. Tại sao không nên “sửa đồng thời tất cả”?

Nếu cùng lúc bạn thêm ba repositories, nâng bốn module, bật artifact metadata fallback, đổi Java version và force version, build có thể pass nhưng bạn **không biết thay đổi nào đã chữa nguyên nhân**, và có thể để lại rủi ro supply-chain. Quy trình có thể kiểm toán:

1. Lưu log lỗi gốc và requested coordinates.
2. Xác định đúng configuration, task và repository attempted.
3. Đặt một giả thuyết cụ thể: ví dụ “repo A chứa POM nhưng không có JAR” hoặc “constraint đang ép version”.
4. Áp dụng **một thay đổi nhỏ** tại nguồn.
5. Chạy lại đúng lệnh tái hiện.
6. So sánh `dependencies`/`dependencyInsight` trước và sau.
7. Chạy compile/test/integration phù hợp.
8. Review thay đổi về bảo mật, reproducibility và lockfiles rồi mới đưa vào CI.

## 13. Một số mẫu sửa đúng và mẫu sửa sai

| Tình huống | Nên làm | Tránh |
| --- | --- | --- |
| Gõ sai `group:name:version` | Tra tọa độ chính thức, sửa đúng khai báo. | Tự chế một version gần giống và cho rằng sẽ resolve. |
| Chưa khai báo nơi tải dependency | Thêm đúng `repositories` hoặc `dependencyResolutionManagement.repositories` theo chính sách build. | Thêm Maven Central vào `publishing.repositories` hoặc `pluginManagement` và nghĩ đã sửa app dependencies. |
| Dependency private | Dùng HTTPS, cấu hình credentials qua secret store, content filters đúng. | Hardcode token và bật HTTP không bảo mật. |
| POM có nhưng JAR thiếu | Sửa publication/mirror của repository đã cung cấp metadata, hoặc policy repository có chủ đích. | Ghép thủ công JAR từ URL khác rồi giữ metadata sai không giải thích. |
| Version khác requested | Đọc selection reasons và mọi path; cập nhật constraint/BOM/khai báo tại nguồn. | `force` mù quáng. |
| `No matching variant` | Đọc attributes consumer/producer, Java toolchain/capabilities. | Đổi version ngẫu nhiên. |
| Chỉ lỗi ở test | Xem `testRuntimeClasspath`/`testCompileClasspath`. | Chỉnh production `implementation` không cần thiết. |
| Offline missing cache | Chạy online khi cho phép; prefetch dependency cho CI có chính sách. | Xóa cache trong khi vẫn chạy `--offline`. |
| Artifact checksum mismatch | Xác minh checksum/PGP và nguồn publication, chặn artifact đáng ngờ. | Tắt dependency verification chỉ để qua build. |
| Dynamic version thay đổi theo thời gian | Pin version, dùng dependency locking nếu phù hợp, kiểm tra update. | Dùng `--refresh-dependencies` làm “fix” dài hạn. |

### 13.1. Lưu ý về lockfiles và dependency verification

`--write-locks` và `--update-locks` có thể **thay đổi lock state** nếu build đã bật dependency locking. Không dùng chúng chỉ để xem lỗi; nên có pull request và review khi cần thay version đã khóa.

Dependency verification (SHA-256/PGP) có thể từ chối artifact **dù đã tải được**. Đây là lỗi integrity, khác với “module không tìm thấy”. Khi gặp mismatch, cần xác minh publisher, repository, version và metadata đã phê duyệt; **không** tắt `--dependency-verification` hoặc sửa checksum để chấp nhận artifact chưa được tin cậy.

## 14. Bài tập tự luyện

**Bài 1 — Đọc thông điệp:** Với log:

```text
Could not find org.demo:engine:9.9.
Searched in the following locations: ...
Required by: project :app
```

Nêu ít nhất bốn nguyên nhân có thể (tọa độ, version, repository scope, filter, snapshot, auth). Lệnh nào giúp xác định configuration gây lỗi? Có được kết luận `9.9` chưa từng được publish chỉ dựa trên dòng đầu không?

**Bài 2 — Xung đột:** Trong lab mục 11.3, vì sao `1.15 -> 1.16.0` không có nghĩa hai JAR cùng classpath? Chạy `dependencyInsight` và ghi selection reason cùng mọi path. Nếu xóa yêu cầu 1.15, selected version có thay đổi không?

**Bài 3 — Thiếu artifact:** Đổi `@zip` trong lab thành dependency chuẩn. Vì sao yêu cầu `@zip` khác với một artifact JAR mặc định? Việc thêm `metadataSources { artifact() }` ở public repository có phải giải pháp tốt không?

**Bài 4 — Repository scoping:** Phân biệt nguồn tải cho `plugins { }`, `buildscript { }`, `implementation` và đích `publishing.repositories`. Nếu Gradle báo lỗi ở plugin ID, nơi nên kiểm tra đầu tiên là gì?

**Bài 5 — CI offline:** Local chạy online thành công, CI chạy `--offline` nhưng chưa có artifact. Tại sao CI lỗi? Nêu quy trình prefetch và lưu cache đúng chính sách mà không tắt các cơ chế xác minh.

**Bài 6 — POM nhưng thiếu JAR:** Repo A có metadata cho `x:y:1.0` nhưng artifact chưa upload; repo B có artifact. Gradle có tự lấy POM từ A và JAR từ B không? Trình bày cách sửa publication/routing hợp lý.

**Bài 7 — Runtime-only:** Mã compile được nhưng chạy báo `NoClassDefFoundError`. Vì sao cần xem `runtimeClasspath` và vị trí launcher/test runner trước khi đổi compiler options?

**Bài 8 — Tóm tắt trước/sau:** Lập báo cáo review với các trường:

| Trường | Trước | Sau |
| --- | --- | --- |
| Project và task | ... | ... |
| Resolvable configuration | ... | ... |
| Requested coordinate | ... | ... |
| Selected version/variant | ... | ... |
| Repository và URL đã thử | ... | ... |
| Graph resolution pass/fail | ... | ... |
| Artifact resolution pass/fail | ... | ... |
| Lý do thay đổi | ... | ... |
| Compile/test/runtime checks | ... | ... |

### Câu hỏi nhanh

1. **Không tìm thấy JAR có luôn đồng nghĩa không tìm thấy module?** Không. Metadata có thể tồn tại nhưng artifact thiếu.
2. **`--refresh-dependencies` có sửa tọa độ sai không?** Không.
3. **`--offline` có tự lấy artifact còn thiếu từ mạng không?** Không.
4. **`dependencyInsight` dùng để làm gì?** Xem selected version, selection reasons và dependency paths trong một configuration.
5. **`(c)` trong dependency tree là JAR độc lập?** Không, đó là constraint.
6. **Repo đã cung cấp POM nhưng thiếu JAR: Gradle tự lấy JAR ở repo kế tiếp?** Thông thường không; source của metadata/artifact được giữ nhất quán.
7. **`@zip` có giữ nguyên metadata, transitive và variant-aware resolution?** Không, artifact-only notation bỏ qua chúng.
8. **`No matching variant` có luôn sửa bằng nâng version?** Không, cần phân tích attributes/compatibility.
9. **401, 403 hoặc timeout có chứng minh version không tồn tại?** Không.
10. **Checksum sai có nên tắt verification?** Không, phải điều tra nguồn/integrity trước.

## 15. Tài liệu chính thức

- **Gradle — Dependency Resolution Basics** (graph resolution và artifact resolution): https://docs.gradle.org/current/userguide/dependency_resolution_basics.html
- **Gradle — Viewing and Debugging Dependencies** (`dependencies`, `dependencyInsight`, reason): https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- **Gradle — Graph Resolution** (thứ tự repositories, metadata, artifact source): https://docs.gradle.org/current/userguide/graph_resolution.html
- **Gradle — Artifact Resolution / Specific Artifacts** (artifact-only notation, classifier): https://docs.gradle.org/current/userguide/resolving_specific_artifacts.html
- **Gradle — Supported Metadata Formats** (`.module`, POM, Ivy, metadataSources): https://docs.gradle.org/current/userguide/supported_metadata_formats.html
- **Gradle — Repository Content Filtering** (include/exclude/exclusive, snapshot/release): https://docs.gradle.org/current/userguide/filtering_repository_content.html
- **Gradle — Centralizing Repository Declarations** (settings và repository modes): https://docs.gradle.org/current/userguide/centralizing_repositories.html
- **Gradle — Dependency Caching** (metadata cache, negative caching, repository stickiness): https://docs.gradle.org/current/userguide/dependency_caching.html
- **Gradle — Variant-aware Resolution** (consumer/producers attributes): https://docs.gradle.org/current/userguide/variant_aware_resolution.html
- **Gradle — Repository Protocols and Authentication**: https://docs.gradle.org/current/userguide/supported_repository_protocols.html
- **Gradle — Securing Repositories / Dependencies**: https://docs.gradle.org/current/userguide/securing_repositories.html và https://docs.gradle.org/current/userguide/dependency_verification.html
- **Gradle — Declaring Versions and Ranges / Locking**: https://docs.gradle.org/current/userguide/dependency_versions.html và https://docs.gradle.org/current/userguide/dependency_locking.html
- **Gradle — Command-Line Interface** (offline, refresh, info, stacktrace): https://docs.gradle.org/current/userguide/command_line_interface.html

**Ghi nhớ:** hãy truy đúng `project → resolvable configuration → requested coordinates → selected component/variant → repository/metadata → artifact file__. Một phiên bản được chọn khác yêu cầu là vấn đề **graph resolution**; metadata tồn tại nhưng JAR/ZIP không tải được là vấn đề **artifact resolution**. Đọc lỗi gốc, kiểm tra repository và nguồn gốc, chỉ sửa nguyên nhân được chứng minh, rồi so sánh report và chạy lại tests.