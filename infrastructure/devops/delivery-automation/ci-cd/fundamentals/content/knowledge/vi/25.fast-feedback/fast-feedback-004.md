# Tận dụng cache mà vẫn bảo toàn tính đúng

Cache giúp CI/CD phản hồi nhanh hơn bằng cách tái sử dụng dữ liệu hoặc kết quả đã được tính trước. Thay vì tải lại toàn bộ dependency, biên dịch mọi module hoặc dựng lại từng layer của container image, pipeline có thể khôi phục nội dung từ cache khi các đầu vào liên quan chưa thay đổi.

Tuy nhiên, cache chỉ là một tối ưu hóa. Một cache hit không chứng minh kết quả đúng, còn cache miss không phải lỗi build. Nếu cache key thiếu một đầu vào quan trọng, pipeline có thể tái sử dụng kết quả cũ cho source hoặc toolchain mới. Nếu cache được chia sẻ giữa các mức độ tin cậy khác nhau, pull request không đáng tin có thể ghi nội dung độc hại vào cache mà release pipeline sử dụng. Nếu cache chứa secret hoặc artifact phát hành, việc tái sử dụng có thể làm lộ dữ liệu hoặc khiến pipeline triển khai sai nội dung.

Nguyên tắc thiết kế là: **cache có thể bị xóa bất kỳ lúc nào mà pipeline vẫn phải build đúng; cache hit phải tương đương về ngữ nghĩa với việc tính lại từ các đầu vào hiện tại**. Muốn đạt điều đó, cần định danh đầu vào đầy đủ, kiểm soát nguồn ghi cache, xác minh tính toàn vẹn và kiểm tra định kỳ bằng cold build.

## 1. Cache là gì và giúp CI/CD nhanh hơn ở đâu?

Cache là vùng lưu trữ có thể tái sử dụng dữ liệu hoặc kết quả tính toán trong một khoảng thời gian. Trong pipeline, cache thường giảm các công việc lặp lại giữa nhiều lần chạy:

- Tải dependency từ package registry.
- Tải compiler, SDK hoặc toolchain.
- Biên dịch module có đầu vào không đổi.
- Tái sử dụng layer của Docker/OCI image.
- Tái sử dụng dữ liệu build trung gian.
- Tái sử dụng kết quả của task nếu hệ thống build xác định được đầy đủ inputs/outputs.
- Tái sử dụng dữ liệu phân tích hoặc test fixture được tạo từ nguồn tin cậy.

Ví dụ một dự án Java có thể mất nhiều thời gian tải Gradle dependencies ở mỗi lần CI chạy. Cache Gradle có thể giữ các dependency đã tải và một phần dữ liệu build. Lần chạy sau chỉ tải những dependency còn thiếu hoặc thay đổi, giúp giảm thời gian chờ.

Cache có thể nằm ở nhiều nơi:

- **Local cache:** thư mục trên runner hoặc máy build.
- **CI cache:** cache service do GitHub Actions, GitLab CI hoặc nền tảng khác cung cấp.
- **Remote build cache:** cache dùng chung cho nhiều runner, thường theo content key.
- **Registry cache:** Docker/BuildKit layer cache lưu trong container registry.
- **Package manager cache:** npm, pnpm, Maven, Gradle hoặc NuGet lưu package đã tải.
- **Tool cache:** SDK, runtime, compiler và executable đã cài đặt.

Không phải cache nào cũng có cùng semantics. Cache dependency thường lưu package đã tải; build cache lưu output của task; Docker layer cache lưu kết quả từng bước build image. Cách tạo key, invalidation và mức rủi ro khác nhau.

## 2. Cache hit không phải bằng chứng về tính đúng

Một cache hit chỉ nói rằng hệ thống tìm được entry khớp với key hoặc quy tắc restore. Nó không tự chứng minh:

- Key chứa mọi input có ảnh hưởng đến kết quả.
- Entry được tạo từ source và dependency đáng tin cậy.
- Entry không bị thay đổi hoặc hỏng.
- Toolchain hiện tại tương thích với entry.
- Entry không chứa dữ liệu từ một môi trường khác.
- Task có thể tái sử dụng kết quả mà không bỏ qua side effect cần thực hiện.

Ví dụ build task phụ thuộc vào biến môi trường FEATURE_SET nhưng cache key chỉ dùng commit SHA. Hai job có cùng source nhưng khác FEATURE_SET có thể nhận cùng cache entry dù output cần khác nhau.

Một ví dụ khác: cache được tạo từ pull request bên ngoài và lưu trong phạm vi mà workflow release có thể restore. Nếu contributor có thể kiểm soát nội dung cache, release pipeline có thể nhận output đã bị thay đổi.

Vì vậy cần tách hai câu hỏi:

1. Cache entry có thể được tìm thấy và khôi phục không?
2. Cache entry có thực sự hợp lệ cho các đầu vào, môi trường và mức độ tin cậy hiện tại không?

Chỉ câu hỏi thứ hai liên quan trực tiếp đến tính đúng.

## 3. Phân loại cache trước khi thiết kế

| Loại cache | Nội dung thường lưu | Lợi ích | Rủi ro chính |
|---|---|---|---|
| Dependency cache | Package đã tải, metadata và checksum | Giảm thời gian tải dependency | Dependency mutable, lockfile thiếu, cache poisoning |
| Toolchain cache | SDK, compiler, runtime, wrapper | Giảm thời gian cài công cụ | Phiên bản hoặc kiến trúc không khớp |
| Build cache | Output của task/module theo inputs | Tránh biên dịch lại | Khai báo input thiếu hoặc task không deterministic |
| Docker layer cache | Layer đã tạo từ instruction và build context | Giảm thời gian build image | Layer key sai, build context không đầy đủ, cache từ nguồn không tin cậy |
| Test/result cache | Kết quả hoặc dữ liệu kiểm thử có thể tái sử dụng | Giảm công việc lặp | Bỏ qua test cần chạy hoặc tái sử dụng kết quả không còn hợp lệ |
| Analysis cache | Dữ liệu phân tích tĩnh, index, metadata | Giảm thời gian phân tích | Source/config/plugin thay đổi nhưng cache không invalidated |
| Artifact/release storage | Binary/image/package dùng để deploy | Giữ output phát hành | Đây là artifact store, không nên xử lý như cache có thể tự ý xóa/ghi đè |

Một nguyên tắc hữu ích: cache là dữ liệu có thể tái tạo; artifact phát hành là đầu ra cần lưu giữ, định danh và kiểm toán. Không dùng cache làm nguồn duy nhất để triển khai production.

## 4. Xác định đầy đủ inputs ảnh hưởng đến cache key

Cache key phải thay đổi khi bất kỳ input nào có thể làm thay đổi kết quả cache thay đổi. Một key thường cần xem xét:

- Hệ điều hành và kiến trúc runner.
- Phiên bản runtime, compiler, SDK và build tool.
- Dependency lockfile hoặc file mô tả dependency.
- Build script, plugin và cấu hình có ảnh hưởng đến output.
- Source/config được task sử dụng.
- Feature flags hoặc build profile tại thời điểm build.
- Target platform, architecture và runtime.
- Phiên bản schema hoặc định dạng cache nếu format thay đổi.
- Mức độ tin cậy hoặc phạm vi cache nếu tách theo trust domain.

Một mô hình key khái quát:

~~~text
cache_key = hash(
    cache_format_version,
    operating_system,
    architecture,
    toolchain_versions,
    dependency_lockfiles,
    build_configuration,
    relevant_task_inputs
)
~~~

Không phải cache nào cũng cần tất cả thành phần trên. Dependency download cache có thể không cần commit SHA vì package được định danh bởi coordinates, version và checksum. Build output cache cần inputs chi tiết hơn vì output phụ thuộc source, toolchain và cấu hình task.

### 4.1. Key quá rộng và key quá hẹp

| Cách thiết kế | Hệ quả |
|---|---|
| Key chỉ có tên nhánh | Các commit khác nhau có thể dùng chung output không tương thích |
| Key chỉ có commit SHA | Có thể thiếu toolchain, architecture hoặc build flags |
| Key có mọi file trong repository | Cache miss quá thường xuyên khi tài liệu hoặc file không liên quan thay đổi |
| Key có lockfile và toolchain cần thiết | Thường phù hợp cho dependency cache |
| Key theo task inputs thực tế | Phù hợp cho build cache nếu task khai báo inputs đầy đủ |
| Key chứa random run ID | Hầu như mỗi lần chạy đều cache miss |
| Key không có cache format version | Entry cũ có thể được đọc bởi logic mới không tương thích |

Key cần cân bằng độ chính xác và tỷ lệ tái sử dụng. Đừng tối ưu cache hit bằng cách bỏ input cần thiết; một cache hit sai nguy hiểm hơn cache miss.

## 5. Dependency lockfile và tính toàn vẹn package

Dependency cache chỉ giúp tái sử dụng package đã tải. Tính đúng vẫn phải được bảo đảm bởi cách dự án định danh và xác minh dependency.

### 5.1. Dùng lockfile cho dependency graph

Các hệ sinh thái thường có cơ chế khóa phiên bản:

- Gradle dependency locking.
- Maven dependency version được quản lý qua POM/BOM và quy tắc version rõ ràng.
- npm package-lock.json.
- pnpm-lock.yaml.
- Yarn lockfile.
- NuGet packages.lock.json hoặc cơ chế khóa tương ứng.

Lockfile giúp xác định dependency graph và giảm việc mỗi lần build resolve ra một phiên bản khác. Cache key nên thay đổi khi lockfile thay đổi.

### 5.2. Xác minh checksum và nguồn package

Nếu package manager hỗ trợ integrity/checksum verification, hãy bật và tuân thủ. Với Gradle có thể dùng dependency verification metadata để xác minh checksum hoặc chữ ký. npm lockfile chứa integrity metadata cho package tương ứng. Maven repository có thể cung cấp checksum/signature; chính sách xác minh cần được cấu hình phù hợp.

Cache không thay thế xác minh package. Nếu cache entry hỏng hoặc bị thay thế, package manager cần phát hiện nội dung không khớp với integrity metadata và tải lại từ nguồn tin cậy hoặc dừng build.

### 5.3. Cẩn trọng với dependency mutable

Các dependency như SNAPSHOT, floating version, latest, branch URL hoặc package tag có thể trỏ đến nội dung thay đổi theo thời gian. Cache có thể giữ bản cũ lâu hơn dự kiến.

Ưu tiên version cố định và lockfile. Nếu bắt buộc dùng dependency mutable, cần chính sách freshness, refresh interval và kiểm tra checksum/version thực tế. Không coi cache hit là bằng chứng dependency vẫn là phiên bản mới nhất.

## 6. Phân biệt dependency cache với build cache

Hai loại cache này thường bị nhầm:

**Dependency cache** lưu package đã tải để lần sau không phải tải lại. Ví dụ Gradle modules cache, Maven local repository hoặc npm content cache.

**Build cache** lưu output của task đã chạy. Nếu inputs của task giống nhau, hệ thống có thể khôi phục output mà không thực thi task lần nữa.

Dependency cache thường ít rủi ro hơn nếu package được pin và xác minh checksum. Build cache đòi hỏi task inputs/outputs được khai báo đầy đủ và task có thể tái sử dụng kết quả.

Một task đọc file source, compiler version và build flags nhưng không khai báo biến môi trường ảnh hưởng output có thể tạo cache key thiếu. Khi đó build cache trả output cũ cho cấu hình mới.

### 6.1. Task cần khai báo input/output chính xác

Với Gradle, task custom nên khai báo input/output bằng annotation hoặc property phù hợp. Ví dụ minh họa:

~~~kotlin
abstract class GenerateConfig : DefaultTask() {
    @get:Input
    abstract val environmentName: Property<String>

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val templateFile: RegularFileProperty

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val template = templateFile.get().asFile.readText()
        val rendered = template.replace(
            "{{environment}}",
            environmentName.get()
        )
        outputFile.get().asFile.writeText(rendered)
    }
}
~~~

Ví dụ này cho thấy environmentName và templateFile là input, còn outputFile là output. Nếu task còn phụ thuộc locale, timezone, environment variable, tool binary hoặc file khác, những input đó cũng cần được khai báo hoặc loại bỏ khỏi logic task.

Không đánh dấu task cacheable nếu task tạo side effect bên ngoài, phụ thuộc trạng thái không được khai báo hoặc không thể tái tạo output ổn định.

### 6.2. Không cache task chỉ vì muốn build nhanh

Các task như publish package, gửi notification, deploy, cập nhật database hoặc gọi API bên ngoài thường không nên được xem như task tạo output thuần túy để cache. Nếu cache hit khiến task bị bỏ qua, side effect cần thực hiện có thể không xảy ra. Nếu cache miss làm task chạy lại, side effect có thể lặp.

Tách task tính toán output khỏi task thực hiện side effect. Cache phần tính toán; quản lý publish/deploy bằng operation ID, idempotency và trạng thái riêng.

## 7. Cache key cho Gradle

Một dự án Gradle thường có thể hưởng lợi từ dependency cache và build cache. Hai cơ chế có cấu hình và mục đích khác nhau.

Ví dụ bật build cache trong gradle.properties:

~~~properties
org.gradle.caching=true
org.gradle.parallel=true
~~~

Dependency cache của Gradle lưu module artifacts và metadata trong Gradle User Home. Để giữ tính đúng:

- Commit Gradle Wrapper và khóa version Gradle.
- Khóa dependency version khi dự án cần dependency graph ổn định.
- Dùng dependency verification metadata cho checksum/signature.
- Đảm bảo task custom khai báo input/output chính xác.
- Không cache output phụ thuộc vào biến môi trường không được khai báo.
- Không chia sẻ build cache giữa trust domains không tương thích.
- Định kỳ chạy clean build để phát hiện khai báo input thiếu.

Ví dụ khóa dependency:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Lệnh tạo/cập nhật lockfile phụ thuộc cấu hình dự án; chỉ cập nhật lock khi có thay đổi dependency được review. Không tự động ghi lockfile mới trong mọi CI run rồi coi đó là kết quả chuẩn.

## 8. Cache cho Maven, npm và pnpm

### 8.1. Maven

Maven thường lưu dependency đã tải trong local repository, mặc định là .m2/repository. CI có thể cache thư mục này dựa trên POM, parent POM, BOM và các file cấu hình dependency phù hợp.

Cần chú ý:

- Dependency version cố định và BOM được quản lý rõ.
- Snapshot/floating versions có chính sách refresh.
- Không cache credentials hoặc file settings.xml chứa secret.
- Xác minh checksum/signature theo chính sách repository.
- Không dùng local repository từ runner không tin cậy làm nguồn package cho release mà không kiểm tra integrity.

### 8.2. npm

npm có content cache; lockfile là nguồn quan trọng để tái tạo dependency graph. Lệnh npm ci cài theo package-lock và xóa node_modules hiện có trước khi cài.

Ví dụ:

~~~bash
npm ci
npm test
npm run build
~~~

CI có thể cache npm download cache để giảm thời gian tải. Không nên dựa vào cache node_modules thiếu kiểm soát giữa các OS, Node version hoặc native module khác nhau.

### 8.3. pnpm

pnpm dùng content-addressable store và hardlink/reflink để tạo node_modules. Có thể cache pnpm store theo OS, kiến trúc, pnpm version và lockfile. Dùng frozen lockfile trong CI để bảo đảm pipeline không tự cập nhật dependency graph.

Ví dụ:

~~~bash
pnpm install --frozen-lockfile
pnpm test
pnpm build
~~~

Cache store vẫn cần integrity verification của package manager. Không cho job từ fork ghi vào cache dùng cho release nếu không có ranh giới tin cậy phù hợp.

## 9. Cache trong GitHub Actions

GitHub Actions cache thường được định danh bằng key và có thể dùng restore keys để tìm cache gần khớp khi exact key không tồn tại.

Ví dụ cache Gradle theo hệ điều hành, kiến trúc, JDK và hash của các file dependency/toolchain:

~~~yaml
- name: Set up JDK
  uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: '21'

- name: Cache Gradle data
  uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches
      ~/.gradle/wrapper
    key: gradle-linux-x64-jdk21-LOCKFILE_AND_TOOLCHAIN_HASH
    restore-keys: |
      gradle-linux-x64-jdk21-
      gradle-linux-x64-

- name: Verify
  run: ./gradlew --no-daemon check
~~~

Ví dụ là cấu trúc minh họa; placeholder HASH cần được thay bằng giá trị hash được tính từ các file dependency, wrapper, verification metadata và cấu hình phù hợp. Trong workflow thực tế cần pin action theo full commit SHA theo chính sách tổ chức và xác định rõ phiên bản Gradle/JDK.

Nếu restore key rộng hơn exact key, cache được khôi phục có thể không khớp toàn bộ dependency input; Gradle vẫn phải xác minh và tải phần cần thiết. Không dùng restore key rộng để tái sử dụng compiled outputs nếu không có cơ chế xác định tính hợp lệ của chúng.

### 9.1. Exact key và restore key khác nhau

- Exact key khớp toàn bộ key, phù hợp khi cần cache tương ứng chính xác với input.
- Restore key là prefix fallback để tìm cache gần nhất.
- Restore key rộng làm tăng cache hit nhưng có thể khôi phục nội dung cũ.
- Khi cache miss, workflow có thể tạo cache mới sau khi job hoàn tất thành công tùy action/platform behavior.

Chỉ dùng restore key rộng cho nội dung có thể được xác minh hoặc tái tạo an toàn. Với dependency cache, package manager và lockfile/integrity cần kiểm soát việc sử dụng package. Với build outputs, cần tránh fallback làm dùng output từ input khác.

### 9.2. Cache scope và pull request

Cache scope của nền tảng có quy tắc riêng theo branch, repository và event. Cần đọc đúng semantics của nền tảng. Đặc biệt, không giả định pull request từ fork có thể ghi cache của default branch, hoặc cache do fork tạo không thể được release workflow đọc. Hãy thiết kế trust boundary tường minh và kiểm tra quyền thực tế.

## 10. Cache trong GitLab CI

GitLab CI hỗ trợ khai báo cache key và paths. Ví dụ:

~~~yaml
build:
  image: gradle:8.10-jdk21
  cache:
    key:
      files:
        - gradle.lockfile
        - gradle/wrapper/gradle-wrapper.properties
      prefix: gradle-jdk21-linux
    paths:
      - .gradle/caches/
      - .gradle/wrapper/
  script:
    - ./gradlew --no-daemon check
~~~

Đây là ví dụ đơn giản; cần điều chỉnh file lock thực tế và đường dẫn Gradle User Home theo image/runner. Nếu nhiều job dùng cùng cache, cần hiểu cache upload/download và chính sách policy của GitLab. Job chỉ cần đọc cache có thể dùng policy pull; job được chọn làm nơi cập nhật cache có thể dùng pull-push.

Không để mọi job đồng thời ghi một cache key chung nếu nội dung có thể không nhất quán hoặc runner có thể upload một trạng thái chưa hoàn tất. Có thể tách job warm-cache hoặc dùng remote build cache có cơ chế content-addressed và write-once.

## 11. Docker BuildKit layer cache

Docker build chia quá trình thành các layer. Một instruction và build context không đổi có thể tái sử dụng layer đã tạo. Sắp xếp Dockerfile hợp lý giúp thay đổi source code không làm mất cache của bước tải dependency.

Ví dụ:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace

COPY gradlew .
COPY gradle/ gradle/
COPY settings.gradle.kts build.gradle.kts ./
COPY */build.gradle.kts ./

RUN ./gradlew --no-daemon dependencies

COPY . .
RUN ./gradlew --no-daemon clean build

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/app/build/libs/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Đây là cấu trúc khái niệm; lệnh dependencies và cách copy build scripts cần điều chỉnh theo multi-module layout. Các điểm chính:

- Copy file dependency/build configuration trước source để giữ layer dependency khi source thay đổi.
- Dùng .dockerignore để loại .git, build outputs, local caches và file không cần thiết khỏi build context.
- Pin base image theo version/digest nếu yêu cầu reproducibility.
- Không COPY secret hoặc file credentials vào image.
- Không dùng build argument để truyền secret.
- Kiểm tra layer cache có nguồn tin cậy và tương thích với platform.

### 11.1. Registry cache với BuildKit

BuildKit có thể xuất/nhập cache qua registry:

~~~bash
docker buildx build \
  --cache-from type=registry,ref=registry.example.com/cache/orders:buildkit \
  --cache-to type=registry,ref=registry.example.com/cache/orders:buildkit,mode=max \
  --tag registry.example.com/orders:3.2.0 \
  --push .
~~~

Cú pháp cần điều chỉnh theo builder, registry và nền tảng. Cache registry không phải artifact phát hành. Phân quyền push cache nên giới hạn; không cho workflow không tin cậy ghi cache mà release pipeline sử dụng. Có thể tách cache ref theo branch hoặc trust domain, sau đó chỉ promote/cache từ nguồn đã kiểm chứng.

## 12. Cache poisoning và ranh giới tin cậy

Cache poisoning xảy ra khi nội dung cache bị ghi hoặc thay đổi bởi nguồn không đáng tin cậy, sau đó pipeline khác sử dụng nội dung đó như thể nó đáng tin.

Tình huống ví dụ:

1. Một pull request từ fork chạy workflow và được phép ghi cache key chung.
2. Job tạo cache chứa dependency hoặc build output đã bị can thiệp.
3. Workflow trên nhánh release khôi phục cùng cache.
4. Build/release sử dụng nội dung độc hại mà không nhận ra nguồn tạo cache.

Các biện pháp bảo vệ:

- Tách cache theo trust domain: fork/untrusted PR, branch nội bộ, protected branch và release.
- Không cho workflow từ fork ghi cache mà release pipeline có thể restore.
- Không dùng cache của branch không được bảo vệ cho production publish/deploy.
- Giới hạn quyền ghi cache và registry cache.
- Dùng exact key và verify content/integrity.
- Không cache executable hoặc build output từ nguồn không tin cậy rồi chạy trong job có secret.
- Không để cache trở thành kênh truyền secret giữa các job hoặc repository.
- Theo dõi nguồn tạo cache và version của cache format.

### 12.1. Cache scope không phải ranh giới bảo mật tuyệt đối

Một key có tiền tố main- không tự bảo đảm chỉ main có thể ghi. Cần xem quyền ghi, quyền đọc và scope thực tế của cache service. Cũng không nên coi cache được lưu trong repository riêng là an toàn nếu workflow không tin cậy có quyền push vào đó.

### 12.2. Cache và untrusted code

Pull request có thể thay đổi build script, test code, plugin hoặc dependency. Nếu job chạy mã không tin cậy đồng thời được cấp secret hoặc quyền ghi cache dùng chung, mã đó có thể lấy secret hoặc đầu độc cache. Cần tách job validation không có secret khỏi job publish/deploy có quyền cao; dùng runner và cache scope tương ứng.

## 13. Không cache secret và dữ liệu nhạy cảm

Cache có thể được lưu lâu hơn vòng đời job và được khôi phục bởi những job khác trong phạm vi cho phép. Vì vậy không đưa vào cache:

- Access token, private key, cloud credential hoặc registry password.
- File cấu hình có chứa secret.
- .env production hoặc kubeconfig nhạy cảm.
- Database dump có dữ liệu cá nhân thật nếu không có kiểm soát phù hợp.
- Log chứa token, request body hoặc thông tin khách hàng.
- Workspace đầy đủ nếu không biết chính xác nội dung bên trong.

Với Docker BuildKit, dùng secret mount chuyên dụng cho bước cần xác thực thay vì ARG, ENV hoặc COPY secret vào layer. Secret mount được thiết kế để không trở thành một phần của image layer nếu Dockerfile sử dụng đúng cách; vẫn cần bảo đảm lệnh build không in hoặc copy nội dung secret ra output.

Cache cần được coi là vùng lưu trữ có quyền truy cập và retention riêng. Nếu nghi cache đã chứa secret, xóa/thu hồi cache theo phạm vi và rotate credential liên quan; chỉ xóa file nguồn không loại bỏ bản sao đã lưu.

## 14. Invalidation: khi nào cần làm cache mất hiệu lực?

Cache cần được invalidated khi input hoặc semantics thay đổi khiến entry cũ không còn hợp lệ.

Các trường hợp thường gặp:

- Lockfile hoặc dependency coordinates thay đổi.
- JDK, Node.js, compiler, SDK hoặc build tool version thay đổi.
- OS/architecture hoặc target platform thay đổi.
- Build script, plugin hoặc compiler flags thay đổi.
- Cache serialization format thay đổi.
- Task input mới được thêm hoặc logic task thay đổi.
- Base image hoặc Dockerfile instruction thay đổi.
- Dependency verification metadata hoặc policy thay đổi.
- Cache bị nghi nhiễm độc, hỏng hoặc tạo từ nguồn không tin cậy.
- Một lỗi cho thấy cache key trước đây thiếu input.

### 14.1. Version prefix cho cache format

Khi cấu trúc cache thay đổi, thêm version vào key:

~~~text
gradle-cache-v3-linux-x64-jdk21-<dependency-hash>
docker-cache-v2-orders-<build-input-hash>
frontend-cache-v4-node22-<lockfile-hash>
~~~

Version prefix cho phép chuyển đổi có chủ đích mà không cần đoán cache cũ có tương thích hay không. Không dùng prefix mới như cách che giấu một key sai mà không xác định input bị thiếu.

### 14.2. Invalidate có mục tiêu

Không nên xóa toàn bộ cache mỗi khi build lỗi. Trước tiên xác định lỗi đến từ dependency, toolchain, task output, registry hoặc source. Invalidate cache liên quan, giữ lại cache hợp lệ để tránh tăng tải package registry và thời gian build.

Nếu nghi cache poisoning hoặc integrity violation, phạm vi xóa cần đủ rộng để ngăn tái sử dụng entry bị ảnh hưởng. Sau đó chạy clean build từ nguồn tin cậy và kiểm tra lại.

## 15. Cache miss và fallback phải an toàn

Cache có thể không tồn tại do hết hạn, eviction, runner mới hoặc key thay đổi. Pipeline vẫn phải chạy đúng bằng cách tải/calculate lại từ nguồn chuẩn.

Một pipeline an toàn nên:

- Không thất bại chỉ vì cache miss.
- Không phụ thuộc vào cache để chứa file nguồn duy nhất.
- Có fallback tải dependency từ registry tin cậy.
- Có thể rebuild output từ source và inputs đã khóa.
- Xác minh checksum/signature sau khi tải.
- Không dùng stale cache nếu không thể chứng minh tương thích.
- Báo cache hit/miss để quan sát, nhưng không coi miss là lỗi chất lượng.

Cache là tối ưu hóa thời gian; source, lockfile, toolchain và artifact store mới là nguồn chuẩn.

## 16. Cache và tính reproducible của build

Reproducible build nghĩa là cùng source và các đầu vào được kiểm soát có thể tạo ra output tương đương hoặc giống hệt theo tiêu chí đã định nghĩa. Cache không tự tạo reproducibility, nhưng có thể che giấu việc build không reproducible nếu pipeline luôn restore output cũ.

Để build có thể tái tạo:

- Ghim dependency và toolchain.
- Ghi nhận OS, architecture, locale/timezone và build flags khi chúng ảnh hưởng output.
- Loại bỏ timestamp/randomness không cần thiết hoặc kiểm soát seed.
- Không tải binary không versioned từ URL mutable.
- Dùng build script xác định input/output.
- Lưu source revision và artifact digest.
- Định kỳ chạy clean build không dùng cache.
- So sánh checksum hoặc metadata khi mục tiêu yêu cầu byte-for-byte reproducibility.

Một số artifact chứa timestamp hoặc metadata biến thiên nên không nhất thiết có digest giống nhau giữa hai lần build dù ngữ nghĩa tương đương. Khi đó cần định nghĩa rõ tiêu chí so sánh: byte-level, package content, API behavior hoặc test outcome. Không tuyên bố reproducible chỉ vì cache hit.

## 17. Cache concurrency và ghi cache an toàn

Nhiều job có thể cùng tính toán một key hoặc cập nhật cache trong thời gian gần nhau. Nếu cache service cho phép ghi đè, job chậm có thể ghi một entry cũ sau khi job mới đã ghi entry mới. Nếu cache được upload khi task chưa hoàn tất, entry có thể thiếu file.

Các nguyên tắc:

- Dùng key bất biến theo input; tránh nhiều job ghi cùng key với nội dung không đồng nhất.
- Ưu tiên content-addressed cache hoặc write-once key.
- Chỉ publish cache sau khi bước tạo cache hoàn tất và xác minh.
- Dùng lock/atomic publish khi backend cần cập nhật index hoặc manifest.
- Tách cache read-only và cache writer nếu nền tảng hỗ trợ.
- Không để job bị hủy upload cache dở dang.
- Dùng cache version/schema để ngăn reader cũ đọc format mới.

Với cache phân tán, metadata và content cần được ghi theo cách nguyên tử hoặc có manifest xác nhận hoàn tất. Một entry chưa hoàn chỉnh nên bị bỏ qua và tính lại.

## 18. Kiểm tra tính đúng bằng cold build

Một trong những cách phát hiện cache key thiếu input là chạy định kỳ một build không sử dụng cache. Cold build giúp xác nhận dự án vẫn có thể được dựng từ source và dependency chuẩn.

Có thể áp dụng:

- Mỗi ngày hoặc mỗi tuần chạy một pipeline clean build.
- Với release quan trọng, chạy validation trên runner mới hoặc cache namespace mới.
- So sánh test result, artifact metadata và digest theo tiêu chí phù hợp.
- Nếu cache hit và cold build cho kết quả khác nhau, coi là lỗi tính đúng cần điều tra.
- Sau khi thay toolchain hoặc build script, chạy cold build trước khi mở cache mới cho release.
- Giữ lại log và input manifest của cả hai lần để đối chiếu.

Cold build không cần chạy trên mọi commit nếu chi phí cao. Có thể chọn lịch, release candidate hoặc thay đổi nhạy cảm. Điều quan trọng là cache không được che giấu việc build sạch đã hỏng.

## 19. Đo hiệu quả cache mà không đánh đổi độ tin cậy

Các chỉ số hữu ích:

- Cache hit rate theo loại cache và key namespace.
- Cache miss rate và nguyên nhân miss.
- Thời gian tải dependency trước/sau cache.
- Build duration p50/p95.
- Kích thước cache và thời gian restore/save.
- Tỷ lệ lỗi integrity hoặc checksum.
- Số lần invalidation thủ công.
- Số cold build phát hiện khác biệt với cached build.
- Tỷ lệ cache entry đến từ nguồn tin cậy.
- Chi phí lưu trữ và egress.

Không tối ưu chỉ theo cache hit rate. Một cache có hit rate 99% nhưng thỉnh thoảng trả output sai có thể nguy hiểm hơn cache 70% nhưng luôn xác định đúng input. Đo cả thời gian tiết kiệm và chất lượng đầu ra.

Ví dụ so sánh:

| Chỉ số | Không cache | Có cache |
|---|---:|---:|
| Dependency download | 4 phút | 25 giây |
| Build task không đổi | 6 phút | 1 phút |
| Tổng CI duration | 12 phút | 5 phút |
| Clean build verification | Đạt | Đạt |
| Integrity checks | Bật | Bật |
| Kết luận | Baseline | Nhanh hơn và giữ kết quả xác minh |

Số liệu trong bảng chỉ minh họa cách đánh giá, không phải benchmark chung.

## 20. Quy trình thiết kế cache cho một pipeline

1. **Xác định mục tiêu:** muốn giảm thời gian tải dependency, compile, build image hay phân tích?
2. **Chọn loại cache:** dependency, toolchain, build output, Docker layer hoặc analysis.
3. **Xác định nguồn chuẩn:** lockfile, source, toolchain manifest, registry và build config.
4. **Liệt kê inputs:** OS, architecture, tool version, lockfile, task input và feature flags liên quan.
5. **Thiết kế key/version:** key đổi khi input hoặc cache format đổi; tránh key dựa vào nhánh đơn thuần.
6. **Đặt trust boundary:** ai được đọc/ghi cache; tách fork, internal branch, protected branch và release.
7. **Bật integrity verification:** checksum/signature, lockfile, provenance hoặc metadata phù hợp.
8. **Thiết kế fallback:** cache miss thì tải hoặc tính lại từ nguồn tin cậy.
9. **Tách side effect:** không cache publish/deploy/migration/notification như task tính toán thuần.
10. **Quan sát:** hit/miss, duration, size, source, integrity và cold-build result.
11. **Diễn tập invalidation:** đổi toolchain, lockfile hoặc cache format để xác nhận key thay đổi.
12. **Kiểm tra định kỳ:** clean build và so sánh với kết quả cached build.

## 21. Anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách làm tốt hơn |
|---|---|---|
| Key chỉ theo branch | Dùng output của commit khác | Key theo inputs và toolchain |
| Cache node_modules giữa mọi môi trường | Native binary hoặc dependency không tương thích | Key theo OS, architecture, runtime và lockfile; cân nhắc cache package store |
| Restore build output từ prefix quá rộng | Output cũ không khớp inputs hiện tại | Dùng exact key hoặc build cache có input tracking |
| Dùng cache làm artifact release | Cache có thể bị eviction hoặc ghi đè | Publish artifact bất biến vào registry |
| Cho fork ghi cache release | Cache poisoning | Tách trust domain và quyền ghi |
| Cache toàn workspace | Có thể lưu secret, output cũ và file không liên quan | Chỉ cache paths cần thiết |
| Không dùng lockfile/checksum | Dependency thay đổi nhưng cache vẫn hit | Pin version và verify integrity |
| Cache task có side effect | Hit bỏ qua tác vụ hoặc miss chạy lặp | Tách task tính toán và side effect |
| Dùng tag mutable làm nguồn build | Base image có thể đổi mà key không đổi | Pin version/digest |
| Không chạy cold build | Cache key thiếu input bị che giấu | Cold-build verification định kỳ |
| Xóa mọi cache khi có lỗi | Tăng thời gian và tải registry | Điều tra rồi invalidate có mục tiêu |
| Không version cache format | Reader mới dùng entry cũ sai cách | Thêm cache namespace/version |

## 22. Checklist bảo toàn tính đúng khi dùng cache

### Inputs và key

- [ ] Đã phân loại cache là dependency, toolchain, build output, Docker layer hay loại khác.
- [ ] Key chứa mọi input có ảnh hưởng đến nội dung cache.
- [ ] Key tính đến OS/architecture/toolchain khi cần.
- [ ] Lockfile và build configuration được dùng làm input/version signal.
- [ ] Có cache format version và quy tắc invalidation.
- [ ] Không dùng random run ID hoặc branch name thay cho input identity.

### Integrity và trust

- [ ] Dependency được pin/lock và checksum/signature được xác minh.
- [ ] Cache writer/reader được giới hạn theo trust domain.
- [ ] Fork/untrusted PR không ghi cache được release pipeline sử dụng.
- [ ] Cache không chứa secret, token hoặc dữ liệu nhạy cảm ngoài ý muốn.
- [ ] Artifact release được lưu riêng, có digest và provenance.
- [ ] Cache entry lỗi hoặc không xác minh được sẽ bị bỏ qua và tính lại.

### Build và side effect

- [ ] Task có input/output khai báo đầy đủ nếu dùng build cache.
- [ ] Task không deterministic hoặc có side effect không bị cache sai semantics.
- [ ] Publish, deploy, migration và notification được quản lý bằng operation state riêng.
- [ ] Cache miss có fallback tải/tính lại từ nguồn chuẩn.
- [ ] Restore key rộng chỉ dùng cho nội dung có thể xác minh an toàn.
- [ ] Cache concurrency không tạo entry thiếu hoặc ghi đè ngoài ý muốn.

### Verification và vận hành

- [ ] Có cold build định kỳ hoặc trước release quan trọng.
- [ ] Cached build và clean build được so sánh theo tiêu chí rõ.
- [ ] Theo dõi hit/miss, duration, integrity failures và cache source.
- [ ] Có quy trình invalidate khi đổi toolchain, lockfile, task input hoặc cache format.
- [ ] Có thể xóa toàn bộ cache mà pipeline vẫn build và phát hành đúng.
- [ ] Runbook chỉ rõ cache nào được phép restore trong job có secret/deploy permission.

Cache làm CI/CD nhanh hơn khi tái sử dụng đúng dữ liệu cho đúng đầu vào. Tính đúng đến từ lockfile, toolchain được kiểm soát, input/output khai báo đầy đủ, checksum/provenance và ranh giới tin cậy; cache chỉ giúp tránh tính lại những gì đã được xác minh. Hãy coi cache là dữ liệu có thể mất và phải tái tạo được, tách cache khỏi artifact phát hành, không cache side effect, và dùng cold build để kiểm tra rằng tối ưu hóa không che giấu lỗi.
