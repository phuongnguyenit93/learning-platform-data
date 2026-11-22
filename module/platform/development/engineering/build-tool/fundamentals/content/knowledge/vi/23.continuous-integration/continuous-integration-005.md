# Thiết kế khóa cache theo công cụ, môi trường và tập phụ thuộc

Cache trong CI giúp giảm thời gian tải dependency, cấu hình build, biên dịch và tạo artifact. Tuy nhiên, cache chỉ an toàn khi dữ liệu được khôi phục đúng với công cụ, môi trường và đầu vào đã tạo ra nó. Một cache key quá rộng có thể khiến build nhận dữ liệu không tương thích hoặc cũ; key quá hẹp lại tạo nhiều cache entry gần như giống nhau và làm giảm tỷ lệ cache hit.

Thiết kế cache key cần bắt đầu từ câu hỏi **đang cache loại dữ liệu nào**. Cache dependency download, Gradle task output, Maven local repository, configuration cache và Docker layer có quy tắc hợp lệ khác nhau. Không nên dùng một key duy nhất cho mọi loại cache.

Một key thường cần kết hợp các nhóm thông tin sau:

- Công cụ và phiên bản công cụ tạo dữ liệu.
- Môi trường có ảnh hưởng đến nội dung hoặc cách phân giải dependency.
- Tập manifest, lockfile và cấu hình quyết định dependency graph.
- Các input thực sự ảnh hưởng đến output nếu đang cache kết quả build.
- Phiên bản schema hoặc namespace để chủ động vô hiệu hóa cache khi thay đổi chính sách.

## 1. Cache key là gì?

Cache key là định danh mà CI hoặc build tool dùng để tìm dữ liệu đã lưu. Khi một job chạy, nó tạo key từ các thuộc tính đã chọn. Nếu tìm thấy cache entry tương ứng, job khôi phục dữ liệu thay vì tải hoặc tính toán lại. Nếu không có entry phù hợp, job thực hiện công việc bình thường và có thể lưu kết quả mới.

Ví dụ tổng quát:

```text
<purpose>-<tool>-<tool-version>-<platform>-<runtime>-<dependency-fingerprint>
```

Một key cho cache dependency của Gradle có thể chứa Gradle Wrapper version, hệ điều hành, kiến trúc và hash của các file quản lý dependency. Một key cho Maven local repository có thể chứa Maven Wrapper version và hash các POM, BOM hoặc extension. Một cache cho output biên dịch cần phản ánh cả source, compiler, classpath và các tùy chọn làm thay đổi bytecode.

Cache key không phải chỉ là tên thư mục. Nó là tuyên bố về điều kiện mà dữ liệu trong cache được xem là có thể tái sử dụng.

## 2. Phân biệt các loại cache trước khi thiết kế key

Các cache trong một Java CI pipeline thường phục vụ những mục đích khác nhau:

| Loại cache | Dữ liệu được lưu | Cơ chế xác định hợp lệ |
|---|---|---|
| Wrapper/distribution cache | Gradle hoặc Maven distribution đã tải. | Phiên bản distribution và wrapper configuration. |
| Dependency/download cache | JAR, POM, module metadata và artifact đã resolve. | Tọa độ/version, repository metadata, lockfile và chính sách resolution của công cụ. |
| Task/build output cache | Class files, generated files, reports hoặc output task. | Input/output fingerprint do build tool tính. |
| Configuration cache | Kết quả cấu hình build và trạng thái task graph phù hợp. | Build logic, settings, task request và configuration inputs mà Gradle theo dõi. |
| Compiler/tool cache | Dữ liệu trung gian của compiler hoặc công cụ. | Tool version, compiler options, source và dependency inputs. |
| Container/layer cache | Layer được tạo từ Dockerfile và build context. | Layer instruction cùng các file được copy hoặc tham chiếu. |

Một CI cache action thường chỉ lưu và khôi phục thư mục theo key. Nó không tự hiểu dependency graph, classpath hoặc ý nghĩa của file bên trong. Build tool mới là thành phần có thể xác định dependency/task output có còn hợp lệ hay không.

### 2.1. Dependency cache không phải build output cache

Dependency cache lưu những artifact đã tải từ repository, chẳng hạn JUnit, Jackson, Gradle plugin hoặc Maven compiler plugin. Khi build cần cùng artifact, công cụ có thể dùng bản local thay vì tải lại.

Build output cache lưu kết quả do task tạo ra, chẳng hạn class files sau compile hoặc generated sources. Dữ liệu này chỉ dùng được khi các input của task tương ứng khớp.

Hai cache có vòng đời khác nhau:

- Dependency cache có thể dùng lại giữa nhiều commit nếu dependency graph không đổi.
- Build output cache cần xét cả source, compiler/toolchain, classpath và cấu hình task.
- Thay đổi source thường không nên làm mất hiệu lực toàn bộ dependency download cache.
- Thay đổi lockfile thường cần tạo một dependency cache key mới hoặc ít nhất một fingerprint mới cho tập dependency.

Không nên cache toàn bộ thư mục `build/` bằng key chỉ dựa trên lockfile. Source thay đổi có thể khiến output cũ không còn đúng. Hãy dùng cơ chế build cache của Gradle hoặc một hệ thống task cache hiểu input/output.

## 3. Những thành phần nên cân nhắc trong cache key

Không phải cache nào cũng cần mọi thành phần. Hãy thêm một chiều vào key khi nó có thể làm dữ liệu cache khác đi hoặc không tương thích.

### 3.1. Cache purpose và namespace

Nên phân biệt tên cache theo mục đích:

```text
gradle-dependencies-...
gradle-wrapper-...
gradle-build-cache-...
maven-repository-...
```

Điều này tránh khôi phục nhầm một thư mục được tạo cho mục đích khác. Có thể thêm schema version như `v2` khi thay đổi cấu trúc cache, đường dẫn, chính sách lọc hoặc quy tắc tương thích.

### 3.2. Build tool và phiên bản

Gradle và Maven có cấu trúc cache, metadata và hành vi resolution riêng. Không dùng chung cache namespace cho hai công cụ.

Với Gradle, lấy phiên bản từ `gradle/wrapper/gradle-wrapper.properties`, không hardcode một phiên bản khác trong key. Với Maven Wrapper, lấy phiên bản distribution từ `.mvn/wrapper/maven-wrapper.properties`.

Phiên bản tool có thể ảnh hưởng:

- Định dạng hoặc vị trí cache nội bộ.
- Cách phân giải variant và metadata.
- Phiên bản plugin hoặc extension được tải.
- Cách compiler/test task tạo output.
- Tính tương thích của configuration/build cache entry.

Vì vậy, cache dependency hoặc tool state nên có namespace theo tool version khi cần bảo đảm cách ly. Với task output cache, ưu tiên cache key do build tool tính thay vì tự suy diễn toàn bộ thành phần nội bộ.

### 3.3. Hệ điều hành và kiến trúc

Các artifact Java thuần thường dùng được trên nhiều nền tảng, nhưng dependency graph có thể chứa native library, platform classifier hoặc công cụ phụ thuộc hệ điều hành. Compiler plugin, JNI, browser driver, protoc binary hoặc native image tool có thể tạo dữ liệu riêng cho từng nền tảng.

Nếu cache chứa dữ liệu có phụ thuộc môi trường, key nên chứa:

- Hệ điều hành, ví dụ Linux, Windows hoặc macOS.
- Kiến trúc CPU, ví dụ x64 hoặc arm64.
- ABI/libc khi native artifact phụ thuộc, ví dụ glibc so với musl.
- Phiên bản runtime hoặc toolchain nếu nó ảnh hưởng đến artifact.

Không nên loại OS/architecture chỉ vì phần lớn dependency là JAR thuần. Hãy xác định cache path có chứa native/platform-specific artifacts hay không. Nếu không có dữ liệu phụ thuộc nền tảng, key dùng chung có thể tăng hit rate; nếu có, chia cache theo platform để tránh khôi phục sai.

### 3.4. JDK và toolchain

Java version có thể ảnh hưởng dependency variant được chọn, compiler behavior, bytecode target, annotation processor và plugin. Nếu một cache lưu output compile, JDK/compiler version thường là chiều quan trọng.

Với dependency download cache, JDK chỉ cần nằm trong key khi dependency resolution hoặc cache content phụ thuộc vào nó, ví dụ build dùng attribute JVM version, profile theo JDK hoặc tải tool artifact theo runtime. Không phải mọi thư viện JAR đều khác nhau giữa JDK 17 và JDK 21.

Với task output cache, không tự giả định Gradle sẽ biết mọi environment variable hoặc binary tool bên ngoài mà task action gọi. Nếu kết quả phụ thuộc vào JDK/tool version, task cần khai báo input phù hợp hoặc dùng API toolchain để build engine nhận biết toolchain.

### 3.5. Manifest, lockfile và cấu hình dependency

Đây thường là thành phần quan trọng nhất của dependency cache key. Hash các file mô tả dependency graph giúp tạo key mới khi tập thư viện hoặc plugin thay đổi.

Với Gradle, có thể cân nhắc:

- `settings.gradle` hoặc `settings.gradle.kts`.
- `build.gradle`/`build.gradle.kts` của root và subprojects.
- `gradle/wrapper/gradle-wrapper.properties`.
- `gradle/libs.versions.toml` nếu dùng version catalog.
- `gradle.lockfile` hoặc các lockfile theo configuration.
- `gradle/verification-metadata.xml` nếu dùng dependency verification.
- `build-logic/**` hoặc `buildSrc/**` nếu chúng ảnh hưởng plugin/dependency resolution.
- Các file cấu hình repository/plugin management có liên quan.

Với Maven, có thể cân nhắc:

- Tất cả `pom.xml` trong reactor.
- Parent POM/BOM được khai báo hoặc import.
- Plugin version và plugin management.
- `.mvn/wrapper/maven-wrapper.properties`.
- `.mvn/extensions.xml`.
- `.mvn/maven.config` nếu chứa profile hoặc tùy chọn làm thay đổi dependency graph.
- Các cấu hình mirror/profile không bí mật được workflow sử dụng.

Không nhất thiết phải hash mọi file trong repository. Chọn các file thực sự có thể thay đổi dependency graph hoặc nội dung cache.

### 3.6. Environment variables và build profiles

Một số build thay đổi dependency theo profile, property hoặc biến môi trường. Ví dụ build có thể bật native driver cho Linux, chọn profile integration test hoặc tải một implementation riêng cho JDK.

Nếu biến đó ảnh hưởng nội dung cache, hãy đưa giá trị không nhạy cảm hoặc một identifier ổn định vào key. Không đưa token, password, signing key hoặc secret trực tiếp vào cache key. Key thường được ghi trong log và có thể hiển thị cho người có quyền đọc workflow/cache metadata.

Tốt hơn là chuyển các lựa chọn build quan trọng thành property rõ ràng, có versioning và có thể kiểm soát trong CI, thay vì để task đọc môi trường ngầm.

## 4. Cấu trúc key: đủ phân biệt nhưng không quá chi tiết

Một key tốt cân bằng hai rủi ro:

- **False hit:** hai trạng thái không tương thích dùng cùng key, có thể khôi phục dữ liệu sai.
- **False miss:** hai trạng thái tương thích dùng key khác nhau, làm cache bị bỏ lỡ và tăng chi phí tải/tính toán.

Ví dụ key quá rộng:

```text
java-build-cache
```

Key này không phân biệt Gradle/Maven, JDK, OS, dependency hoặc cấu hình. Nó chỉ an toàn nếu cache service và build tool bên trong tự quản lý key đầy đủ cho từng entry; không an toàn nếu CI dùng nó để khôi phục trực tiếp một thư mục output build chung.

Ví dụ key quá hẹp cho dependency cache:

```text
gradle-deps-linux-jdk21-commit-<full-git-sha>
```

Mỗi commit tạo key mới dù dependency không đổi. Cache sẽ có nhiều bản giống nhau, giảm tỷ lệ reuse và tăng dung lượng.

Ví dụ key hợp lý hơn cho dependency cache:

```text
gradle-deps-v2-linux-x64-gradle8.10-jdk21-<hash-dependency-inputs>
```

Key này phân biệt mục đích, schema, platform/toolchain có liên quan, Gradle version và tập file quản lý dependency. Source code thông thường không cần nằm trong hash dependency.

## 5. Thiết kế cache key cho Gradle dependency cache

Gradle lưu dependency metadata và artifact trong Gradle User Home, thường dưới `~/.gradle/caches`. Gradle Wrapper distribution thường nằm dưới `~/.gradle/wrapper/dists`.

Khi CI muốn giữ dependency download cache giữa các job, có thể cache các thư mục thích hợp trong Gradle User Home. Tuy nhiên, không nên cache mù toàn bộ Gradle User Home vì nơi đó có thể chứa daemon state, native state, init script hoặc thông tin không cần thiết.

### 5.1. Những file nên hash

Ví dụ cho build multi-project dùng version catalog và lockfile:

```text
settings.gradle(.kts)
build.gradle(.kts)
**/build.gradle(.kts)
gradle/wrapper/gradle-wrapper.properties
gradle/libs.versions.toml
gradle.lockfile
**/gradle.lockfile
gradle/verification-metadata.xml
build-logic/**
buildSrc/**
```

Các file này có thể thay đổi plugin version, repository, dependency declaration, version constraint, lock state hoặc build logic. Với repository lớn, nên điều chỉnh glob để không hash source code hoặc file generated không liên quan.

Nếu dùng dependency locking, lockfile là tín hiệu quan trọng để key thay đổi khi resolved versions được cập nhật. Nếu không dùng lockfile, cần hash các file build/configuration có thể làm dependency graph thay đổi và chấp nhận rằng dynamic version/changing module vẫn cần cơ chế refresh riêng.

### 5.2. Key ví dụ cho GitHub Actions

Ví dụ minh họa dùng `actions/cache` để lưu Gradle dependency cache:

```yaml
- name: Cache Gradle dependencies
  uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches/modules-2
    key: gradle-deps-v2-${{ runner.os }}-${{ runner.arch }}-gradle-${{ hashFiles('gradle/wrapper/gradle-wrapper.properties') }}-jdk-${{ matrix.java }}-${{ hashFiles('settings.gradle*', 'build.gradle*', '**/build.gradle*', 'gradle/libs.versions.toml', 'gradle.lockfile', '**/gradle.lockfile', 'gradle/verification-metadata.xml', 'build-logic/**', 'buildSrc/**') }}
    restore-keys: |
      gradle-deps-v2-${{ runner.os }}-${{ runner.arch }}-gradle-${{ hashFiles('gradle/wrapper/gradle-wrapper.properties') }}-jdk-${{ matrix.java }}-
```

Nếu muốn cache Gradle Wrapper distribution, tách thành cache riêng để thay đổi lockfile không làm lưu lại cả bộ Gradle distribution:

```yaml
- name: Cache Gradle distribution
  uses: actions/cache@v4
  with:
    path: ~/.gradle/wrapper/dists
    key: gradle-wrapper-v1-${{ runner.os }}-${{ hashFiles('gradle/wrapper/gradle-wrapper.properties') }}
```

Đây là cấu hình minh họa; cần thay `matrix.java` bằng tên biến matrix thực tế của workflow. Nếu không có matrix, dùng JDK version cố định được thiết lập trong job. Cần xác nhận các glob khớp đúng file build của repository.

Ý nghĩa:

- `gradle-deps-v2` tách mục đích và schema cache.
- `runner.os` và `runner.arch` cách ly cache khi môi trường có thể chứa artifact native/platform-specific.
- Hash wrapper properties phân biệt Gradle distribution version.
- JDK dimension phân biệt môi trường khi dependency resolution/profile có thể thay đổi theo JDK; có thể bỏ nếu đã xác nhận không ảnh hưởng cache content.
- Hash build/settings/version catalog/lockfile/build logic thay đổi khi dependency graph hoặc plugin resolution thay đổi.
- `restore-keys` chỉ fallback trong cùng platform, Gradle wrapper và JDK namespace, rồi để Gradle tự resolve/kiểm tra dependency và tải phần còn thiếu.

Với GitHub Actions, cache entry đã lưu thường là immutable. Khi dependency inputs thay đổi, exact key mới được tạo; restore prefix có thể lấy một cache cũ hơn để giảm lượt tải, sau đó job có thể lưu cache theo exact key mới nếu workflow và action cho phép. Hãy kiểm tra cache hit/miss trong log để xác nhận hành vi thực tế.

### 5.3. Tránh cache nhầm dữ liệu không cần thiết

Không nên mặc định cache:

- `~/.gradle/daemon`: process/daemon state không phải dependency artifact.
- `~/.gradle/notifications`: thông báo không giúp resolve dependency.
- Toàn bộ `~/.gradle`: có thể chứa init scripts, native state hoặc dữ liệu không nên chia sẻ.
- `build/` hoặc output project bằng key chỉ dựa trên lockfile.

Nếu muốn cache wrapper distribution riêng, có thể cache `~/.gradle/wrapper/dists` với key phụ thuộc wrapper properties và platform nếu cần. Dependency cache và wrapper distribution có vòng đời khác nhau nên có thể tách riêng để quan sát hit rate và invalidation rõ hơn.

## 6. Gradle task output cache: để Gradle tính key

Gradle Build Cache có cơ chế tính cache key cho từng task cacheable dựa trên task implementation, actions, input properties, file inputs và các thông tin liên quan đến output. Gradle xử lý normalization theo loại input, ví dụ path sensitivity và classpath normalization.

Vì vậy, với task output, cách an toàn là khai báo input/output đầy đủ và dùng Gradle Build Cache. Không nên tự tạo một CI key theo Git commit rồi cache nguyên thư mục `build/`.

Ví dụ bật build cache:

```properties
org.gradle.caching=true
```

Hoặc chạy:

```bash
./gradlew build --build-cache
```

Gradle có thể lấy output từ local/remote build cache khi task cacheable và key khớp. Task outcome `FROM-CACHE` cho biết output đã được khôi phục.

### 6.1. Input của task phải phản ánh tool và môi trường

Một task tự định nghĩa gọi công cụ bên ngoài, ví dụ `protoc`, OpenAPI generator hoặc native compiler, cần khai báo version/tool executable và option nếu chúng ảnh hưởng output.

Ví dụ về ý tưởng:

```groovy
abstract class GenerateApiTask extends DefaultTask {
    @InputFile
    abstract RegularFileProperty getSchemaFile()

    @Input
    abstract Property<String> getGeneratorVersion()

    @Input
    abstract Property<String> getTargetPlatform()

    @OutputDirectory
    abstract DirectoryProperty getOutputDirectory()
}
```

Nếu output khác nhau theo generator version hoặc target platform, các giá trị đó phải tham gia input fingerprint. Tốt hơn nữa, dùng Gradle toolchain hoặc managed tool dependency nếu plugin/tool integration hỗ trợ để Gradle có thể quản lý executable một cách rõ ràng.

Không nên đưa toàn bộ environment variable vào input một cách máy móc. Chỉ khai báo những giá trị có thể ảnh hưởng đến output. Ngược lại, nếu task đọc biến `TARGET_ARCH` nhưng không khai báo, cache có thể trả về output cho kiến trúc khác.

### 6.2. Không đưa Git commit vào mọi task key

Nếu task output chỉ phụ thuộc vào nội dung source và các input đã khai báo, Gradle có thể tái sử dụng output giữa hai commit có cùng input liên quan. Thêm full Git SHA vào key sẽ làm giảm cache reuse dù nội dung task không đổi.

Chỉ đưa revision vào cache key khi revision thực sự là input của kết quả, ví dụ generated build metadata cố ý ghi commit hash vào artifact. Khi đó, commit hoặc version string cần được khai báo như input property của task.

### 6.3. Remote build cache trong CI

Gradle remote build cache cho phép nhiều runner chia sẻ task output. CI có thể đọc cache từ mọi branch nhưng chỉ cho nhánh tin cậy ghi cache, tùy chính sách bảo mật.

Ví dụ cấu hình minh họa trong build logic:

```groovy
buildCache {
    local {
        enabled = true
    }

    remote(HttpBuildCache) {
        url = uri('https://cache.example.com/gradle/')
        credentials {
            username = providers.environmentVariable('GRADLE_CACHE_USER').orNull
            password = providers.environmentVariable('GRADLE_CACHE_TOKEN').orNull
        }
        push = System.getenv('CI_TRUSTED_BRANCH') == 'true'
    }
}
```

Đây là ví dụ cấu hình minh họa; endpoint, authentication và quyền push phải phù hợp với remote cache server của tổ chức. Secret phải được cấp từ CI secret store và không commit vào repository.

Remote cache không cần một GitHub Actions key do người dùng tự tạo cho từng task. Gradle tính key riêng cho từng task. CI cache key bên ngoài chỉ nên quản lý thư mục dependency/download cache hoặc dữ liệu khác mà CI action thực sự sở hữu.

## 7. Thiết kế cache key cho Maven

Maven thường dùng local repository, mặc định là `~/.m2/repository`, để lưu artifact và plugin đã tải. Đây là dependency/download cache, không phải cache tổng quát cho output của mọi Maven goal.

### 7.1. Các file ảnh hưởng Maven dependency graph

Trong multi-module Maven build, key nên phản ánh các file có thể thay đổi dependency/plugin resolution:

- `pom.xml` ở root và mọi module.
- Parent POM/BOM được khai báo hoặc import.
- Plugin version và plugin management.
- `.mvn/wrapper/maven-wrapper.properties`.
- `.mvn/extensions.xml`.
- `.mvn/maven.config` nếu chứa profile/property ảnh hưởng resolution.
- Các cấu hình mirror/profile không bí mật được workflow sử dụng.

Maven profile có thể bật dependency khác theo JDK, OS, property hoặc environment. Nếu CI chạy profile khác nhau, key hoặc cache namespace phải phân biệt khi profile làm thay đổi tập artifact cần dùng.

### 7.2. Key ví dụ cho Maven local repository

Ví dụ GitHub Actions:

```yaml
- name: Cache Maven repository
  uses: actions/cache@v4
  with:
    path: ~/.m2/repository
    key: maven-repo-v1-${{ runner.os }}-${{ runner.arch }}-maven-${{ hashFiles('.mvn/wrapper/maven-wrapper.properties') }}-jdk-${{ matrix.java }}-${{ hashFiles('**/pom.xml', '.mvn/extensions.xml', '.mvn/maven.config') }}
    restore-keys: |
      maven-repo-v1-${{ runner.os }}-${{ runner.arch }}-maven-${{ hashFiles('.mvn/wrapper/maven-wrapper.properties') }}-jdk-${{ matrix.java }}-
```

Thay `matrix.java` theo workflow thật. Nếu JDK không ảnh hưởng dependency resolution, có thể bỏ chiều đó để tăng khả năng dùng lại cache. Nếu Maven build có profile chọn artifact theo OS/JDK, cần giữ dimension tương ứng.

`~/.m2/repository` chứa cả dependency và plugin artifact đã tải. Không nên cache `target/` cùng key này. Thư mục `target/` là output của project và phụ thuộc source/compiler/plugin/task state; Maven không có một cơ chế output cache phổ quát tương đương Gradle Build Cache trong core.

### 7.3. Maven Wrapper distribution

Maven Wrapper tải distribution theo cấu hình trong `.mvn/wrapper/maven-wrapper.properties`. Có thể cache distribution riêng nếu muốn tránh tải Maven binary lặp lại. Key nên dựa trên wrapper distribution URL/version và platform nếu đường dẫn/cache content có khác biệt.

Không dùng một cache key dependency để cache Maven distribution và ngược lại. Khi nâng Maven Wrapper, cache distribution cần được phân biệt; khi dependency thay đổi nhưng Maven version giữ nguyên, local repository cache có thể vẫn được tái sử dụng.

### 7.4. SNAPSHOT và dynamic/changing dependencies

Một POM không đổi không có nghĩa artifact SNAPSHOT hoặc metadata remote không đổi. `1.0-SNAPSHOT` có thể trỏ đến nội dung mới theo thời gian. Cache CI theo hash POM có thể khôi phục artifact cũ.

Để giảm bất ngờ:

- Ưu tiên release version bất biến cho build phát hành.
- Dùng dependency management và version pin rõ ràng.
- Cấu hình snapshot update policy phù hợp.
- Dùng `-U` khi chủ động muốn kiểm tra snapshot/update mới, hiểu rằng lệnh này có thể làm mới metadata và tải lại artifact.
- Không coi hash POM là bằng chứng artifact remote bất biến.

Nếu cần tái lập build, nên hạn chế SNAPSHOT/dynamic dependency hoặc dùng repository quản lý artifact bất biến. Dependency verification/checksum có thể bổ sung kiểm tra nội dung artifact.

## 8. Restore key và fallback policy

Nhiều CI cache service hỗ trợ exact key và restore prefix. Exact key được tìm trước; nếu không có, service có thể khôi phục cache gần nhất khớp một restore prefix.

Ví dụ:

```text
Exact key:
gradle-deps-v2-linux-x64-gradle8.10-jdk21-<lock-hash>

Restore prefixes:
gradle-deps-v2-linux-x64-gradle8.10-jdk21-
gradle-deps-v2-linux-x64-gradle8.10-
```

Restore prefix càng rộng, khả năng hit càng cao nhưng dữ liệu được khôi phục càng có thể cũ hoặc không phù hợp. Vì vậy:

- Giữ tool version và platform trong mọi restore prefix nếu chúng ảnh hưởng tính tương thích.
- Không fallback giữa Linux và Windows nếu cache chứa native/platform-specific files.
- Không fallback giữa các Gradle/Maven major version nếu cache format/tool state có thể khác.
- Không dùng restore prefix rộng cho task output build cache tự quản lý.
- Sau khi restore cache dependency cũ, để build tool resolve lại và tải phần thiếu theo metadata/lockfile hiện tại.

Restore key là chiến lược tối ưu hiệu năng, không phải chính sách xác minh tính đúng đắn. Tính đúng đắn vẫn phải do dependency resolution, lockfile, verification và task input model đảm bảo.

## 9. Invalidation: khi nào phải tạo key mới?

Cache key cần thay đổi khi một yếu tố làm cache content không còn tương thích. Ví dụ:

| Thay đổi | Dependency cache | Task output cache |
|---|---|---|
| Nâng Gradle Wrapper | Nên đổi namespace/key theo tool version. | Gradle quản lý task cache key; kiểm tra tương thích khi nâng tool. |
| Nâng Maven Wrapper | Nên đổi namespace/key cho Maven local/tool cache nếu cần cách ly. | Output `target/` không nên dùng cache key dependency. |
| Sửa lockfile | Đổi dependency fingerprint. | Task key thay đổi nếu resolved classpath thay đổi. |
| Sửa version catalog/BOM/POM | Đổi dependency fingerprint. | Task key thay đổi theo dependency inputs sau resolution. |
| Sửa source Java | Không cần đổi dependency cache key. | Compile/test task key phải phản ánh source change. |
| Đổi JDK/toolchain | Đổi key nếu dependency resolution hoặc cache data phụ thuộc JDK; thường ảnh hưởng task output key. | Task output cần nhận diện compiler/toolchain thay đổi. |
| Đổi OS/architecture | Đổi key nếu cache chứa native/platform-specific artifacts. | Task output cần phản ánh target platform nếu output phụ thuộc nó. |
| Đổi repository URL/mirror | Xem xét đổi key hoặc namespace khi nguồn artifact/metadata có thể khác. | Không thay task key thủ công; đảm bảo dependency inputs/verification đúng. |
| Đổi secret token nhưng không đổi artifact | Thường không cần đổi dependency content key. | Không đưa secret vào task key; chỉ đưa identity/version không nhạy cảm nếu nó thực sự ảnh hưởng output. |
| Đổi code task/plugin | Dependency cache chỉ đổi nếu plugin dependency/resolution thay đổi. | Task implementation change phải được build tool phản ánh trong task cache key. |

Không phải mọi thay đổi repository/credential đều cần invalidate artifact cache. Nếu chỉ token đọc repository được xoay vòng nhưng artifact và dependency graph không đổi, cache content vẫn có thể hợp lệ. Ngược lại, nếu mirror trỏ sang một repository có nội dung khác cho cùng tọa độ, cần kiểm soát nguồn và verification, không dựa vào key cũ.

## 10. Lockfile, verification và cache là ba cơ chế bổ trợ

Ba cơ chế thường bị nhầm:

| Cơ chế | Câu hỏi được trả lời |
|---|---|
| Dependency locking | Phiên bản nào đã được resolve và cần giữ ổn định? |
| Dependency verification | Artifact tải về có đúng checksum/chữ ký được tin cậy không? |
| CI/dependency cache | Có thể tái sử dụng artifact đã tải để giảm network/time không? |

Cache không khóa version và không xác minh nội dung artifact. Lockfile không đảm bảo artifact trong repository không bị thay đổi. Verification không làm dependency resolution trở nên deterministic nếu version declaration vẫn dynamic.

Với Gradle, nên cân nhắc dependency locking và verification metadata cho build cần tái lập. Với Maven, có thể dùng dependency management, Enforcer và checksum/signature policy của repository/tooling. Cache chỉ là lớp tăng tốc phía trên chính sách dependency.

## 11. Bảo mật cache trong CI

Cache có thể chứa JAR nội bộ, plugin riêng, generated output hoặc dữ liệu build. Nếu job không đáng tin có quyền ghi cache dùng chung, nó có thể đưa dữ liệu độc hại vào cache và làm job tin cậy khôi phục dữ liệu đó.

Một số nguyên tắc:

- Không cache credential, token, private key hoặc file chứa secret.
- Không lưu toàn bộ Gradle User Home hoặc Maven settings cá nhân nếu chúng có thể chứa thông tin xác thực.
- Tách cache theo mức độ tin cậy: fork/PR không tin cậy và branch phát hành.
- Chỉ cho nhánh tin cậy ghi remote build cache hoặc cache được dùng trong release.
- Có thể cho PR đọc cache đã được tạo từ nhánh tin cậy, nhưng không cho PR ghi đè cache tin cậy.
- Dùng quyền đọc/ghi tối thiểu cho repository và cache service.
- Kết hợp dependency verification và kiểm soát repository nguồn.
- Không đưa secret value vào cache key hoặc log.
- Xóa/rotate namespace khi nghi ngờ cache bị nhiễm hoặc artifact bị thay đổi.

Đặc biệt với Gradle remote build cache, task phải khai báo input/output đúng và không có side effect ẩn. Nếu một task cacheable tạo output không xác định hoặc bỏ sót input, một cache entry sai có thể được chia sẻ cho nhiều CI job.

## 12. Cache key và concurrency

Nhiều job có thể chạy đồng thời cho cùng dependency set. Một số cache service dùng cache entry immutable: job đầu tiên lưu key sẽ tạo entry, job sau không thể ghi đè cùng key. Điều này giảm race khi ghi cache nhưng cũng có nghĩa một entry cũ không được sửa tại chỗ.

Thiết kế tốt nên:

- Dùng key xác định từ inputs, không thêm timestamp ngẫu nhiên.
- Dùng schema version để tạo namespace mới khi cần thay đổi nội dung.
- Cho phép job cùng key đọc chung cache.
- Chỉ lưu cache sau khi quá trình cài dependency/build hoàn tất thành công theo policy.
- Không để job PR ghi cache có thể được release job tin cậy sử dụng.
- Theo dõi cache size/retention để tránh tạo quá nhiều key gần giống nhau.

Không thêm run ID hoặc build number vào key dependency cache trừ khi muốn cố ý cô lập từng run. Làm vậy thường phá hủy khả năng reuse giữa các run.

## 13. Ví dụ workflow Gradle và Maven tách cache

Một workflow có thể có job riêng hoặc bước riêng cho từng tool. Ví dụ sau chỉ minh họa cấu trúc key; version action và matrix cần được đồng bộ với repository thực tế.

**Gradle dependency cache:**

```yaml
- name: Set up JDK
  uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: '21'

- name: Cache Gradle dependencies
  uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches/modules-2
    key: gradle-deps-v2-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('gradle/wrapper/gradle-wrapper.properties') }}-jdk21-${{ hashFiles('settings.gradle*', 'build.gradle*', '**/build.gradle*', 'gradle/libs.versions.toml', 'gradle.lockfile', '**/gradle.lockfile', 'gradle/verification-metadata.xml', 'build-logic/**', 'buildSrc/**') }}
    restore-keys: |
      gradle-deps-v2-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('gradle/wrapper/gradle-wrapper.properties') }}-jdk21-

- name: Cache Gradle distribution
  uses: actions/cache@v4
  with:
    path: ~/.gradle/wrapper/dists
    key: gradle-wrapper-v1-${{ runner.os }}-${{ hashFiles('gradle/wrapper/gradle-wrapper.properties') }}

- name: Build
  run: ./gradlew build --build-cache
```

**Maven local repository cache:**

```yaml
- name: Set up JDK
  uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: '21'

- name: Cache Maven repository
  uses: actions/cache@v4
  with:
    path: ~/.m2/repository
    key: maven-repo-v1-${{ runner.os }}-${{ runner.arch }}-maven-wrapper-${{ hashFiles('.mvn/wrapper/maven-wrapper.properties') }}-jdk21-${{ hashFiles('**/pom.xml', '.mvn/extensions.xml', '.mvn/maven.config') }}
    restore-keys: |
      maven-repo-v1-${{ runner.os }}-${{ runner.arch }}-maven-wrapper-${{ hashFiles('.mvn/wrapper/maven-wrapper.properties') }}-jdk21-

- name: Verify
  run: ./mvnw -B verify
```

Không dùng cùng cache key hoặc cùng cache path cho Gradle và Maven. Mỗi tool có cấu trúc và quy tắc resolution riêng. Nếu dùng `actions/setup-java` với tùy chọn cache tích hợp cho Maven/Gradle, hãy kiểm tra key/path mà action tạo và tránh cache trùng lặp bằng một `actions/cache` khác nếu không có lý do.

Các ví dụ trên dùng JDK 21 làm giá trị minh họa. Nếu workflow có matrix nhiều JDK, hãy dùng biến matrix thực tế và quyết định có cần tách cache theo JDK dựa trên dependency resolution/platform attributes.

## 14. Tránh một số lỗi thiết kế cache key thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Một key chung cho mọi tool | Có thể khôi phục dữ liệu sai cấu trúc hoặc sai phiên bản. | Namespace theo mục đích và build tool. |
| Key chỉ theo branch | Dependency hoặc tool thay đổi nhưng cache vẫn được dùng không có kiểm soát. | Hash manifest/lockfile và tool configuration. |
| Key theo full commit SHA cho dependency cache | Mỗi commit tạo cache mới dù dependency không đổi. | Hash file dependency/build configuration. |
| Bỏ OS/architecture khi cache có native artifact | Có thể khôi phục binary không chạy được trên runner. | Phân biệt platform/ABI khi cần. |
| Hash toàn bộ source cho dependency cache | Cache bị invalidated sau mỗi thay đổi code. | Chỉ hash file quản lý dependency. |
| Cache `build/` bằng key lockfile | Class/output cũ có thể được dùng với source mới. | Dùng Gradle Build Cache hoặc task cache hiểu input/output. |
| Dùng restore prefix quá rộng | Có thể khôi phục cache không tương thích. | Giữ tool/platform/runtime namespace trong prefix. |
| Không hash build logic/plugin declaration | Plugin hoặc resolution rule thay đổi nhưng cache key không đổi. | Bao gồm settings, plugin management và build logic. |
| Không dùng lockfile với dynamic version | Cùng key có thể resolve dependency khác theo thời gian. | Pin/lock version và kiểm soát changing modules. |
| Cache cả settings/credentials | Có nguy cơ lộ secret hoặc cấu hình riêng của máy. | Chỉ cache thư mục artifact; cấp secret qua CI. |
| Mọi PR đều được ghi remote cache tin cậy | Cache poisoning từ code không tin cậy. | Tách trust boundary và chỉ cho nhánh tin cậy push. |

## 15. Đo hiệu quả cache

Không nên chỉ nhìn thấy cache directory được khôi phục rồi kết luận pipeline nhanh hơn. Cần đo cả hit rate và chi phí restore.

Các số liệu hữu ích:

- Exact cache hit/miss rate.
- Restore-key fallback rate.
- Thời gian tải cache archive.
- Kích thước cache được tải/lưu.
- Thời gian dependency resolution và network download.
- Số task `FROM-CACHE`, `UP-TO-DATE`, `SUCCESS` trong Gradle.
- Tỷ lệ cache hit theo OS/JDK/branch.
- Số lần cache bị invalidated bởi lockfile/tool version.
- Thời gian build tổng thể trước và sau khi bật cache.

Một cache lớn có thể tốn thời gian tải/giải nén nhiều hơn thời gian tải dependency lẻ. Nếu hit rate thấp hoặc archive quá lớn, cần chia cache theo mục đích hoặc loại bỏ dữ liệu ít dùng.

Khi so sánh trước/sau, giữ cùng source, runner, JDK, tool version và task request. Kiểm tra task outcomes để bảo đảm build không nhanh hơn chỉ vì test/task bị bỏ qua.

## 16. Quy trình thiết kế và cập nhật cache key

1. **Xác định mục đích:** dependency download, wrapper distribution, task output, configuration cache hay container layer.
2. **Chọn thư mục:** chỉ lưu dữ liệu thuộc cache đó; loại credential, daemon state và output không được quản lý.
3. **Liệt kê input quyết định:** tool version, platform, JDK, lockfile, manifest, plugin/build logic và profile.
4. **Chọn dimension cần thiết:** chỉ đưa vào key các thuộc tính ảnh hưởng tính tương thích hoặc nội dung cache.
5. **Tạo exact key:** có namespace/schema version, tool/environment và fingerprint dependency.
6. **Thiết kế fallback:** chỉ fallback trong cùng vùng tương thích; để build tool resolve và xác minh nội dung sau khi restore.
7. **Kiểm soát trust:** xác định job nào được đọc/ghi cache và tách cache PR không tin cậy khỏi release cache.
8. **Kiểm chứng invalidation:** đổi lockfile, tool version, JDK hoặc platform theo từng trường hợp và xác nhận key thay đổi đúng lúc.
9. **Đo hit rate/restore cost:** so sánh thời gian và dung lượng trước khi mở rộng cache.
10. **Ghi lại policy:** mô tả file được hash, đường dẫn cache, restore prefix, retention và người sở hữu.

## 17. Mẫu chính sách cache cho repository Java

Một repository Java có thể định nghĩa chính sách như sau:

| Cache | Path | Key dimensions | Fallback |
|---|---|---|---|
| Gradle wrapper | `~/.gradle/wrapper/dists` | Wrapper distribution version, schema | Cùng wrapper version. |
| Gradle dependencies | `~/.gradle/caches/modules-2` | Gradle version, platform khi cần, JDK khi resolution phụ thuộc, settings/build scripts/version catalog/lockfiles | Cùng Gradle/platform/runtime namespace, có thể bỏ dependency hash. |
| Gradle task outputs | Gradle local/remote build cache | Gradle task input fingerprint do Gradle tính | Không tự dùng CI restore prefix cho output directory. |
| Maven dependencies/plugins | `~/.m2/repository` | Maven Wrapper version, platform/profile nếu cần, POM/BOM/extensions | Cùng Maven/platform namespace, có thể bỏ POM hash. |
| Maven project outputs | Không cache nguyên `target/` bằng dependency key | Dùng cơ chế cache chuyên dụng nếu plugin/tool hỗ trợ và hiểu input/output | Theo cache key của công cụ chuyên dụng. |

Policy này giúp các cache có ranh giới rõ ràng. Nếu repository dùng cả Gradle và Maven, chúng có thể chia sẻ một số dependency repository ở tầng server, nhưng local cache và key CI vẫn nên tách theo tool.

## 18. Nguyên tắc cần nhớ

- Cache key phải mô tả dữ liệu đang cache và điều kiện dữ liệu đó có thể tái sử dụng.
- Tách dependency/download cache khỏi task/build output cache.
- Namespace theo tool và version; thêm OS/architecture/JDK khi chúng ảnh hưởng nội dung hoặc resolution.
- Hash manifest, lockfile, version catalog, settings, plugin declaration và build logic liên quan.
- Không hash source cho dependency cache nếu source không ảnh hưởng dependency graph.
- Để Gradle tính key cho task output bằng input/output model và Build Cache.
- Không dùng cache key dependency để khôi phục thư mục `build/` hoặc `target/`.
- Restore prefix chỉ là fallback hiệu năng; tool vẫn phải kiểm tra dependency và task inputs.
- Lockfile, verification và cache giải quyết ba vấn đề khác nhau.
- Không cache secret và không cho job không tin cậy ghi cache dùng cho release.
- Theo dõi hit rate, kích thước, restore time và task outcomes để đánh giá hiệu quả.

Thiết kế cache key tốt là xác định đúng ranh giới tương thích của từng loại dữ liệu. Dependency cache thường cần tool version, môi trường có ảnh hưởng đến resolution và fingerprint của manifest/lockfile; task output cache cần fingerprint đầy đủ của input và nên do build tool quản lý. Khi tách cache theo mục đích, chọn dimension có căn cứ, dùng restore prefix có giới hạn và kiểm soát quyền ghi, CI có thể tận dụng cache hiệu quả mà vẫn giữ build tái lập, an toàn và đúng với source revision đang chạy.
