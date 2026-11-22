# Cache key, khả năng dùng lại giữa máy và tính ổn định đầu ra

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Các lớp cache

## Mục tiêu học tập

Sau khi hoàn thành bài học, bạn có thể:

1. Phân biệt **UP-TO-DATE**, **FROM-CACHE**, **EXECUTED**, **NO-SOURCE** và **SKIPPED**, không dùng một nhãn để kết luận nhầm về nhãn khác.
2. Giải thích **task output build cache** lưu gì, **local build cache** khác **remote build cache** như thế nào, và phân biệt chúng với **dependency cache** cùng **Configuration Cache**.
3. Trình bày cách Gradle hình thành **build cache key** từ task implementation, task actions, tên output properties và tên/giá trị những inputs đã được khai báo; hiểu task path **không** mặc định là một thành phần của cache key.
4. Biết vì sao cùng source nhưng cache key vẫn có thể khác: plugin/task implementation thay đổi, classpath, JDK/toolchain, compiler options, file snapshots, dynamic versions, environment được mô hình hóa hoặc đường dẫn input chưa normalize.
5. Thiết kế một **cacheable task** có output ổn định: mọi input ảnh hưởng bytes đều được khai báo, không dùng thời gian/ngẫu nhiên/absolute path/locale ngầm, không ghi ra các files ngoài output contract.
6. Phân biệt **repeatable/reproducible output** với **cache key ổn định**, và **relocatability** với **cùng đường dẫn thư mục**.
7. Dùng **@PathSensitive(PathSensitivity.NONE / RELATIVE / NAME_ONLY / ABSOLUTE)** đúng ngữ nghĩa; hiểu default ABSOLUTE có thể làm mất khả năng tái sử dụng giữa hai checkout khác path.
8. Viết và chạy dự án **Gradle Groovy DSL + Java 17** có custom **@CacheableTask** trong buildSrc, nhận một input file và một scalar property, sinh output UTF-8 với nội dung chính xác.
9. Dùng **./gradlew clean renderGreeting --build-cache**, **--no-build-cache**, **--rerun-tasks** và **--info** để quan sát thực thi thật, UP-TO-DATE và FROM-CACHE.
10. Kiểm tra khả năng dùng chung cache giữa hai checkout khác thư mục, giữa máy developer và CI, biết khi nào remote cache cần thiết.
11. Cấu hình **local/remote HttpBuildCache**, chọn mô hình **CI trusted push, developer read-only**, giữ HTTPS/credentials và không gửi secret vào artifact.
12. Chẩn đoán false cache hit do input thiếu, cache miss do input không ổn định, non-relocatable paths, output overlap, archive timestamps, Java toolchain/plugin thay đổi, network availability và khác biệt giữa build cache với dependency cache.
13. Lập checklist đo lường và kiểm chứng trước khi tuyên bố một task/plugin tương thích build cache trên CI nhiều máy.

**Kết luận:** Cache key là lời hứa có điều kiện: **nếu những gì task cần thực sự được mô tả đủ trong inputs/implementation và task luôn tạo cùng outputs cho cùng inputs, Gradle mới có thể tái sử dụng output một cách an toàn**. Một cache key trùng nhau chưa chứng minh kết quả đúng nếu build logic quên khai báo input; một task deterministic vẫn không được reuse giữa hai máy nếu paths, toolchains hoặc implementation bị tính khác.

## 1. Bốn lớp trạng thái thường bị nhầm

Một build Gradle Java có thể dùng nhiều cơ chế tránh làm lại công việc:

| Cơ chế | Lưu gì? | Phạm vi | Biểu hiện/việc tránh làm lại |
|---|---|---|---|
| **Up-to-date checks** | Fingerprints của inputs/outputs trong trạng thái build local | Thường trong cùng project checkout | Task **UP-TO-DATE**, không chạy action |
| **Build Cache** | Output artifacts của cacheable task hoặc artifact transform, theo cache key | Local machine hoặc shared remote cache | Task **FROM-CACHE**, outputs được phục hồi |
| **Configuration Cache** | Kết quả configuration, configured task graph/state | Project/build invocation tương thích | Bỏ qua phần configuration, **không** tự quyết định task FROM-CACHE |
| **Dependency Cache** | Resolved modules, POMs, JARs và resolution metadata | Gradle User Home, nguồn repository | Tránh tải dependency lặp lại, **không** chứng minh task output cache hit |

**UP-TO-DATE** và **FROM-CACHE** là hai outcome khác nhau:
- UP-TO-DATE: Gradle xác định outputs đang có trong workspace đã khớp inputs/states; không cần lấy từ cache.
- FROM-CACHE: Gradle lấy outputs đã tạo từ một invocation/task khác có cache key phù hợp; task action không được gọi lần này.
- EXECUTED: task action chạy nếu task được chọn, cần chạy và không được skip; không có nghĩa mọi child-process luôn thực hiện đúng việc nếu task custom có logic bỏ qua.
- NO-SOURCE: Task không có nguồn cần xử lý, ví dụ source set trống; không đồng nghĩa cache hit.
- SKIPPED: Task không chạy do điều kiện khác, như onlyIf false; không đồng nghĩa task đã thực thi thành công.

**Mọi task FROM-CACHE đều là task không thực thi action ở lượt đó**, nhưng output có thể đã được tạo/kiểm tra ở máy khác. Đừng báo “tests vừa chạy trên CI này” khi Test task nhận FROM-CACHE.

### 1.1. Phân biệt “cache” trong thư mục

Một checkout thường có:

~~~text
project/
├── .gradle/
│   ├── configuration-cache/       # cấu hình được cache, nếu bật
│   └── <gradle-version>/...       # trạng thái build/up-to-date
├── build/                         # outputs của project
├── build.gradle
└── settings.gradle

GRADLE_USER_HOME (~/.gradle mặc định)/
└── caches/
    ├── build-cache-1/             # local task output build cache
    ├── modules-2/                 # dependency download/metadata cache
    └── ...                        # những caches nội bộ khác
~~~

Tên thư mục cache và layout có thể thay theo Gradle version. **Không dùng một đường dẫn nội bộ để thao tác xóa cache bằng tay như chiến lược thường lệ**; ưu tiên các command-line flags và cơ chế cleanup của Gradle.

### 1.2. Bật Build Cache

Theo Gradle mặc định, task output build cache không được bật cho invocation nếu chưa cấu hình. Bật cho một lần:

~~~bash
./gradlew build --build-cache
~~~

Hoặc đặt trong **gradle.properties** của project:

~~~properties
org.gradle.caching=true
~~~

Tắt cho một invocation để chẩn đoán:

~~~bash
./gradlew build --no-build-cache
~~~

**--no-build-cache không tắt up-to-date checks.** Nếu task có outputs hợp lệ và inputs không đổi, nó vẫn có thể UP-TO-DATE.

## 2. Cache key thực sự được tạo từ gì?

Gradle xác định một cache key cho mỗi **cacheable task** khi build cache đang được sử dụng. Theo Gradle 9.9 Build Cache Concepts, các thành phần quan trọng:

1. **Task implementation**: loại task và implementation classpath liên quan.
2. **Task action implementations**: code/implementation của những actions thực thi.
3. **Tên các output properties**: ví dụ outputFile.
4. **Tên và giá trị của task inputs**: scalar inputs, file snapshots/normalized paths/contents, classpaths, nested inputs và properties được Gradle task model theo dõi.

Tài liệu Gradle về build cache nhắc thêm tác động của Gradle distribution, buildSrc và plugin classpath cùng build script implementation khi nó thay đổi task action. Tên/path task **không** là một input của build cache key theo mặc định.

~~~text
                    CACHEABLE TASK
                         |
          +--------------+--------------+
          |              |              |
    task/action code  names of outputs  declared inputs
    /classpath        outputFile         recipient="Mai"
                                       template bytes
                                       normalized path
                                       compiler/options...
          |              |              |
          +--------------+--------------+
                         |
                         v
                  BUILD CACHE KEY
                         |
                 local lookup -> remote lookup
                         |
              +----------+-----------+
              |                      |
          matching entry         cache miss
              |                      |
       restore task outputs     execute task action
              |                      |
          FROM-CACHE             optionally store outputs
~~~

**Không thể suy ra key chỉ bằng SHA256 của một source file.** Gradle tính cả task implementation, những inputs đã được model hóa, các đường chuẩn hóa và những metadata có liên quan.

### 2.1. Cùng task name không đủ để hit

Hai projects đều có task renderGreeting nhưng:
- project A dùng implementation class Version1,
- project B dùng implementation class Version2,
- hoặc classpath/plugin code khác,

thì cache key có thể khác dù task names và input file bytes giống nhau.

### 2.2. Task paths khác nhau vẫn có thể cùng cache key

Nếu hai tasks khác paths nhưng:
- Có cùng implementation/task actions,
- Tên output properties phù hợp,
- Các input properties cùng tên và value/fingerprint,
- Đều cacheable, không có điều kiện khiến caching bị vô hiệu hóa,

thì có thể reuse cùng cache entry. Ví dụ hai subprojects có tương đương JavaCompile inputs/implementation có thể dùng chung output cache dù tên task paths khác.

**Không tự đặt project.path làm @Input để “phân biệt task” nếu path không ảnh hưởng bytes.** Việc đó tạo cache miss không cần thiết khi di chuyển project và làm giảm cross-project reuse.

### 2.3. Output destination và output-property name khác nhau

Giả sử task có:

~~~java
@OutputFile
public abstract RegularFileProperty getOutputFile();
~~~

**outputFile** là tên property mà Gradle biết. File có thể đặt tại build/generated/greeting.txt ở checkout A và đường dẫn tương đương trong checkout B.

Với task đã khai báo outputs đúng, Gradle có thể phục hồi cached outputs vào **destination được cấu hình ở workspace hiện tại**; không nhất thiết cần cùng absolute output path. Vì vậy **output path thường không là một thành phần của key như một task input**, còn **tên output property** là một thành phần.

**Cạm bẫy:** Nếu task action ghi **absolute path của output destination vào chính nội dung file**, thì hai workspace có cùng key nhưng **khác bytes mong đợi**. Đó là vi phạm repeatability/relocatability, không phải một thành công của cache.

### 2.4. Những inputs bị ẩn rất nguy hiểm

~~~java
@TaskAction
public void generate() {
    // Anti-pattern: đọc clock nhưng không khai báo input.
    String text = "buildTime=" + System.currentTimeMillis();
}
~~~

Nếu task output thực sự chứa timestamp ở execution, nhưng cache key không biết về timestamp, Gradle có thể:
- Reuse file cũ cho một lượt được người dùng kỳ vọng timestamp hiện tại.
- Lưu một output không deterministic dưới key trông ổn định.
- Tạo kết quả khác nhau giữa execute và FROM-CACHE.

**Phải thiết kế lại yêu cầu.** Nếu timestamp chỉ là thông tin hiển thị không cần trong artifact, bỏ nó khỏi output. Nếu thật sự là business input, mô hình hóa nó rõ và chấp nhận rằng cache reuse sẽ kém; hoặc không cache task có side effect/behavior không thích hợp.

### 2.5. Inputs quá rộng cũng gây cache miss

Một custom task chỉ dùng file README.md nhưng khai báo **cả thư mục project** làm @InputFiles sẽ bị invalidate bởi nhiều file không liên quan. Tương tự, đưa git commit hash/timestamp vào manifest của mọi JAR có thể làm cache key đổi theo mỗi commit dù bytecode logic không đổi.

**Mô hình hóa đủ nhưng tối thiểu:** Mỗi data item ảnh hưởng output cần được khai báo; mỗi value không ảnh hưởng output nên tránh đưa vào input contract. Điều này vừa đúng về correctness vừa giúp cache hit rate.

## 3. Cacheable task và up-to-date task khác nhau

Task có @Input/@Output declarations có thể được Gradle đánh giá UP-TO-DATE trong cùng workspace; tuy nhiên **custom task types không tự động được cacheable**. Với custom task tạo output ổn định, bạn có thể opt-in:

~~~java
@CacheableTask
public abstract class RenderGreetingTask extends DefaultTask {
    // @Input, @InputFile, @OutputFile...
}
~~~

Khi @CacheableTask hiện diện, Gradle xem task type đủ điều kiện cache **nếu** các điều kiện thực tế cho phép; không phải mọi task của project đều phải dùng annotation này.

### 3.1. Đừng gắn @CacheableTask cho mọi thứ

| Loại task | Cân nhắc caching |
|---|---|
| JavaCompile | Có cơ chế cache tích hợp của Gradle |
| Javadoc, một số code quality/report tasks | Có cache support tùy task type và version |
| Code generator deterministic, tốn thời gian | Ứng viên tốt |
| Task tạo file schema snapshot với input rõ | Ứng viên tốt |
| Copy/Sync chỉ di chuyển file rẻ | Caching thường không tiết kiệm |
| Task upload artifact lên remote | Có network side effect, không nên coi cache hit là đã upload |
| Task gửi email hoặc deploy | Không phải pure deterministic output |
| Task đọc thời gian hiện tại/random/external mutable API | Cần thiết kế lại trước khi cache |
| Task không tạo outputs | Cache outputs không có ích |
| Task ghi chung output directory với task khác | Dễ bị Gradle disable caching do overlapping outputs |

**Quan trọng:** Gradle có **@DisableCachingByDefault** cho những task types mà caching không phù hợp theo mặc định. Không dùng @CacheableTask để che một task được thiết kế với side effects hoặc inputs không theo dõi đầy đủ.

## 4. Dùng lại cache giữa hai máy: điều kiện cần

Một local build cache chỉ ở máy developer A không tự xuất hiện trên máy B. Để dùng kết quả giữa máy:
- Cả hai machines cần truy cập **một remote cache chung** (hoặc đồng bộ cache artifacts theo cơ chế được hỗ trợ).
- Task bên B phải được **cacheable và có cùng key** với task bên A.
- Cache entry phải tồn tại, hợp lệ và có thể đọc.
- Outputs bên A phải **đúng và có thể tái sử dụng** ở môi trường B.

~~~text
                    Trusted CI
                        |
               execute cacheable task
                        |
                  PUSH output
                        v
             HTTPS remote build cache
                   /          \
                  /            \
             READ               READ
               v                 v
         Developer A        Developer B
         workstation        fresh CI agent
               |                 |
          FROM-CACHE          FROM-CACHE
~~~

Dùng cache chung **không** khiến Java toolchain, dependencies, environment hoặc compiler options tự biến thành giống nhau. Gradle vẫn dựa trên task fingerprints/implementation để quyết định key.

### 4.1. Hai máy cùng source commit vẫn có thể miss

Các nguyên nhân thường gặp:
- Gradle Wrapper versions khác.
- JDK/toolchain vendor/version/target configuration khác làm inputs hoặc implementation fingerprint khác.
- Plugin, buildSrc hoặc annotation processor version khác.
- Thứ tự input classpath khác, nếu task coi thứ tự là có ý nghĩa.
- Compiler options hoặc source encoding khác.
- File contents khác do line endings CRLF/LF hoặc generated sources không đồng nhất.
- Absolute file paths bị đưa vào @Input String hoặc @InputFile với ABSOLUTE path sensitivity.
- Một môi trường có generated build info/timestamp khác.
- Remote cache chưa có entry hoặc credentials/network không cho tải.
- Cache entry đã được eviction.
- Gradle có khác normalization rules/toolchain behavior ở các versions.

**Đừng tự động kết luận “cache server hỏng” khi cache miss.** Trước hết phải xem cache key/input differences.

### 4.2. Khả năng relocate không phụ thuộc project folder name

Ví dụ:
- Checkout A: /home/ci/builds/service.
- Checkout B: /Users/dev/work/service.
- Source code và template input bytes giống nhau.

Nếu task dùng đúng path normalization, không nhúng absolute locations vào scalar inputs và outputs không tham chiếu path môi trường, chúng **có thể** dùng chung build cache entry. Nếu task có @Input String getProjectRootPath() chứa absolute path, key sẽ khác. Nếu task dùng @InputFile nhưng không có @PathSensitive, default ABSOLUTE có thể làm mất relocatability.

### 4.3. Relocatable không đồng nghĩa identical machines

Relocatability chỉ xử lý việc thay đổi **vị trí filesystem** không ảnh hưởng output. Các yếu tố khác vẫn quan trọng:
- OS-specific native tools và binary formats.
- Java version/toolchain.
- File encoding/newline/locale/timezone.
- CPU architecture/native dependencies.
- Environment variables thực sự ảnh hưởng output.
- Plugin implementation versions.
- External state hoặc network responses.

Nếu task **thực sự phụ thuộc hệ điều hành**, hãy đưa platform vào input hoặc dùng task modeling phân biệt platform, không normalize sự khác biệt đó đi để ép cache hit sai.

### 4.4. Rủi ro khi nhiều máy push vào cùng remote cache

Một máy developer có thể chỉnh source file trong lúc Gradle đang thực thi (IDE auto-save), hoặc có process khác ghi đè output directory. Khi push những bytes chưa phản ánh đúng input fingerprint, shared cache có thể bị ô nhiễm và ảnh hưởng người dùng khác.

Gradle documentation gợi ý topology an toàn:
- **Trusted CI clean builds** được quyền push.
- **Developer machines** được quyền read nhưng **không push**.
- Các agents chỉ push khi build environment được kiểm soát và validation phù hợp.
- Remote cache có HTTPS/authentication, access control và cleanup policy.

**Không xem remote build cache là một public artifact repository hoặc nguồn dữ liệu không cần tin cậy.** Cache có thể ảnh hưởng binary outputs, nên quyền ghi là quyền có tác động lớn đến supply-chain integrity.

## 5. Input normalization và @PathSensitive

Với file inputs, Gradle thường xem xét **file contents và path fingerprints**. Thuộc tính path sensitivity quyết định phần nào của đường dẫn là semantically meaningful.

| PathSensitivity | Đường dẫn được xem xét | Kết quả thực tế |
|---|---|---|
| **ABSOLUTE** | Absolute path | Giảm relocatability: checkout A/B khác path có key khác |
| **RELATIVE** | Path tương đối với input root thích hợp | Thích hợp khi cấu trúc thư mục tương đối ảnh hưởng output |
| **NAME_ONLY** | Chỉ tên cuối của file | Thích hợp khi directory hierarchy không ảnh hưởng behavior |
| **NONE** | Không dùng path làm input fingerprint; tập trung contents | Thích hợp khi task chỉ dùng bytes, không dùng file name/location |

**Không tồn tại một “giá trị tốt nhất” cho mọi file input.** Chọn theo behavior thật của task.

### 5.1. Ví dụ chỉ dùng nội dung file

Một task đọc template text, ghép recipient và ghi output, **không in tên file hoặc directory path**. File path là vị trí lấy bytes, không ảnh hưởng nội dung kết quả. Dùng:

~~~java
@InputFile
@PathSensitive(PathSensitivity.NONE)
public abstract RegularFileProperty getTemplateFile();
~~~

**Nếu template file chuyển từ src/template/greeting.txt sang config/greeting.txt nhưng có cùng bytes**, task có thể hợp lệ để reuse output. Đây là ví dụ cho bài lab.

### 5.2. Khi tên file ảnh hưởng output

Một generator lấy tên file để đặt class name hoặc ghi filename vào report:
- Nếu chỉ basename quan trọng, cân nhắc **NAME_ONLY**.
- Nếu relative path dùng xác định package hoặc resource key, dùng **RELATIVE**.
- Nếu absolute path thật sự là một phần output contract (hiếm với build portable), **ABSOLUTE** có thể đúng về semantics nhưng cache khó reuse giữa máy.

**Không đặt NONE một cách mù quáng** nếu task thật sự dùng filename/path trong output. Khi đó Gradle có thể dùng chung key cho hai inputs mà task sinh **hai output khác nhau** — false hit nguy hiểm.

### 5.3. Classpath normalization khác path sensitivity

Một input JAR classpath có thể chứa metadata không ảnh hưởng ABI/behavior:
- Một JavaCompile task có thể dùng compile classpath normalization để chỉ quan tâm thay đổi API ABI trong những tình huống thích hợp.
- Runtime classpath/resource normalization có cơ chế riêng trong Gradle.
- Một custom Java task nhận classpath nên dùng **@Classpath/@CompileClasspath** khi semantics phù hợp, không mặc định @InputFiles.

**Đừng áp @CompileClasspath cho data files ngẫu nhiên** vì nó có thể bỏ qua thay đổi quan trọng đối với task không phải Java compilation.

## 6. Tính ổn định đầu ra: có cùng input phải có cùng bytes

Một cacheable task phải có **repeatable outputs**. Với cùng implementation và declared inputs tương đương về semantics, thực thi ở hai nơi phải tạo **cùng tập file và cùng nội dung cần thiết**.

Một output không ổn định có thể đến từ:
- Date/time/UUID/random nằm trong file.
- Absolute checkout path hoặc username/hostname nhúng vào output.
- System default charset khác giữa OS.
- System default line separator CRLF/LF.
- Map/Set hoặc filesystem iteration order không ổn định.
- ZIP/JAR entries với timestamps hoặc thứ tự không deterministic.
- Build number/commit hash được đưa vào manifest mọi lúc không cần thiết.
- Service call không được mô hình hóa làm input.
- Network downloading latest metadata ở execution time.
- Tool khác versions hoặc sử dụng default locale/timezone.
- Parallel writers ghi chung file/directory.
- Incremental task bỏ lại stale generated files từ lần trước.

### 6.1. Ví dụ output không ổn định

~~~java
// Anti-pattern, không dùng trong cacheable task:
String output = "generatedAt=" + java.time.Instant.now();
~~~

Hai lần chạy cùng template/recipient có outputs khác nhau. Nếu generatedAt không khai báo input, key có thể trùng nhưng output không repeatable.

**Sửa theo nhu cầu:**
- Bỏ generatedAt nếu không phục vụ behavior của artifact.
- Nếu là release metadata cần thiết, lấy một **explicit releaseTimestamp** từ build input và chấp nhận giá trị khác cho cache key.
- Nếu task luôn phải gọi API ngoài và kết quả không thể model hóa đầy đủ, thường **không cacheable**.

### 6.2. Java charset và newline

~~~java
Files.writeString(
    outputPath,
    content + "\n",
    StandardCharsets.UTF_8
);
~~~

Chọn UTF-8 và LF một cách tường minh. Nếu dùng FileWriter mặc định encoding hoặc System.lineSeparator(), file bytes có thể khác giữa Windows/Linux và làm giảm output repeatability.

### 6.3. Collections deterministic

Nếu task tạo metadata từ một Map<String,String>, sắp xếp keys:

~~~java
Map<String, String> sorted = new TreeMap<>(metadata);
for (Map.Entry<String, String> entry : sorted.entrySet()) {
    // append theo thứ tự đã xác định
}
~~~

Thao tác này không thay đổi business meaning của metadata, chỉ làm serialization ổn định hơn. Tương tự, tập input files có thể cần sorted ordering **nếu thứ tự làm thay đổi output bytes**.

### 6.4. Reproducible ZIP/JAR

Khi tạo archives có sự tham gia của timestamps/entry ordering, Gradle cung cấp các thuộc tính của AbstractArchiveTask:

~~~groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Đây là **snippet bổ sung cho project dùng Jar/Zip tasks**, không phải điều kiện bắt buộc của renderGreeting task. Nó giúp ổn định timestamps và file order trong archive nhưng không tự sửa code generator hoặc external tools không deterministic.

### 6.5. Output overlap và side effects

Nếu :taskA và :taskB cùng khai báo **build/generated/** là @OutputDirectory và ghi nhiều files chồng lấn, Gradle khó xác định file nào thuộc task nào. Caching có thể bị vô hiệu hóa cho những tasks có overlapping outputs để tránh phục hồi/snapshot sai.

Đề xuất:
- Task A: build/generated/a/.
- Task B: build/generated/b/.
- Mỗi task sở hữu output không chồng lấn.
- Producer/consumer khai báo Provider/artifact dependency.
- Không ghi ngoài @OutputFile/@OutputDirectory, đặc biệt trong @CacheableTask.

## 7. Bài lab hoàn chỉnh: Gradle Groovy DSL + Java 17

Bài lab tạo một **custom cacheable task** dùng Java 17, có:
- @InputFile templateFile với PathSensitivity.NONE.
- @Input Property<String> recipient.
- @OutputFile outputFile.
- UTF-8 và LF cố định.
- Không có clock/random/environment ẩn.
- Thực thi tại đúng Gradle task action.

Bài học chọn **buildSrc** để class custom task có sẵn trên build script classpath, không phải để khuyến nghị buildSrc là lựa chọn tối ưu cho mọi multi-project build. Với plugin dùng lại lâu dài, có thể chuyển class thành một binary/convention plugin trong included build **build-logic**.

### 7.1. Yêu cầu

- JDK 17 được cài hoặc Gradle Java toolchain có thể tìm thấy.
- Gradle Wrapper tương thích Java 17 (ví dụ Gradle 9.x theo tài liệu hiện hành).
- Không cần third-party Java dependencies.
- Nếu chưa có Wrapper, dùng Gradle đã cài chạy gradle wrapper một lần rồi sử dụng ./gradlew hoặc .\gradlew.bat.
- Internet có thể cần cho việc tải Gradle distribution lần đầu, **không** phải cho logic template của lab.

### 7.2. Cấu trúc thư mục

~~~text
cache-key-lab/
├── settings.gradle
├── build.gradle
├── gradlew                       # nếu đã có Wrapper
├── gradlew.bat
├── gradle/wrapper/...
├── src/
│   ├── template/greeting.txt
│   └── main/java/demo/ReadGreeting.java
└── buildSrc/
    ├── build.gradle
    └── src/main/java/demo/
        └── RenderGreetingTask.java
~~~

**Không có Gradle project :core/:app** trong lab này; mục tiêu là tập trung cache key của một task riêng, không phải project dependency.

### 7.3. settings.gradle

~~~groovy
rootProject.name = 'cache-key-lab'
~~~

Không có remote cache trong lab mặc định. Một local build cache sẽ được sử dụng khi chạy với --build-cache, giúp thử **clean → FROM-CACHE** trong cùng máy.

### 7.4. buildSrc/build.gradle

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation gradleApi()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

buildSrc tự được Gradle build và đưa output lên classpath của main build. **gradleApi()** là dependency tới Gradle API đi cùng distribution, không cần tải một third-party JAR. Trong môi trường Gradle mà buildSrc đã tự đưa Gradle API vào classpath, explicit dependency ở đây có thể dư nhưng vẫn có ý nghĩa rõ ràng.

### 7.5. RenderGreetingTask.java

**buildSrc/src/main/java/demo/RenderGreetingTask.java**

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.InputFile;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.PathSensitive;
import org.gradle.api.tasks.PathSensitivity;
import org.gradle.api.tasks.TaskAction;

@CacheableTask
public abstract class RenderGreetingTask extends DefaultTask {

    @Input
    public abstract Property<String> getRecipient();

    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    public abstract RegularFileProperty getTemplateFile();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();

    @TaskAction
    public void render() throws IOException {
        // Chỉ đọc những giá trị đã khai báo là inputs.
        String recipient = getRecipient().get();
        Path input = getTemplateFile().get().getAsFile().toPath();

        String greeting = Files.readString(
                input, StandardCharsets.UTF_8
        ).strip();

        String result = greeting + ", " + recipient + "!\n";

        // Chỉ tạo output đã khai báo.
        Path output = getOutputFile().get().getAsFile().toPath();
        Files.createDirectories(output.getParent());
        Files.writeString(
                output, result, StandardCharsets.UTF_8
        );

        getLogger().lifecycle(
                "Rendered greeting for {}", recipient
        );
    }
}
~~~

**Phân tích:**
- Task là abstract Gradle-managed type, không tự tạo Property objects.
- @Input recipient mang giá trị String thực sự ảnh hưởng nội dung.
- @InputFile templateFile mang **file bytes**; @PathSensitive(NONE) chính xác vì nội dung output **không** phụ thuộc tên/path file.
- @OutputFile chỉ rõ file mà task sở hữu.
- @CacheableTask opt-in cacheability; task pure file generation và deterministic.
- @TaskAction thực thi khi cần; không gọi Project.getExtensions hoặc đọc các biến môi trường ẩn.
- String.strip() chuẩn hóa khoảng trắng đầu/cuối của template, có từ Java 11 và hợp lệ với Java 17.
- Output cố định một dòng kết thúc bằng LF và UTF-8.
- Task log có thể khác giữa những Gradle versions, nhưng **file output** có thể so byte-for-byte.

**Giới hạn minh họa:** String.strip() bỏ cả khoảng trắng đầu/cuối của template. Nếu template whitespace có ý nghĩa nghiệp vụ, thiết kế output phải bảo toàn theo một quy tắc mới, đồng thời cập nhật tests/expected bytes.

### 7.6. build.gradle

~~~groovy
import demo.RenderGreetingTask

tasks.register('renderGreeting', RenderGreetingTask) {
    recipient.set(
        providers.gradleProperty('recipient').orElse('Mai')
    )
    templateFile.set(
        layout.projectDirectory.file('src/template/greeting.txt')
    )
    outputFile.set(
        layout.buildDirectory.file('generated/greeting.txt')
    )
}
~~~

Ở đây:
- **tasks.register** giữ configuration lazy.
- Scalar recipient có thể đổi bằng -Precipient=Lan.
- File được tạo trong project build directory qua RegularFileProperty Provider.
- Task không cần Java Plugin cho root project: custom task class đã được buildSrc cung cấp.
- Không cần afterEvaluate, doLast/anonymous action hoặc tự đọc template file ở configuration phase.

**Không copy task action vào build.gradle làm closure** nếu mục tiêu học cache key/Task implementation thật sự; class có @Input/@Output và @CacheableTask giúp modeling rõ.

### 7.7. src/template/greeting.txt

Tạo file UTF-8:

~~~text
Hello
~~~

Nội dung dòng đầu chính xác là Hello. File có newline cuối hoặc không đều cho cùng greeting sau String.strip().

### 7.8. Chạy lần đầu

Linux/macOS:

~~~bash
./gradlew renderGreeting --build-cache --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat renderGreeting --build-cache --console=plain
~~~

Nếu chưa có matching cache entry, task được thực thi. Nó tạo:

~~~text
build/generated/greeting.txt
~~~

**Nội dung file chính xác, với LF cuối dòng:**

~~~text
Hello, Mai!
~~~

Đừng lấy việc terminal in “Rendered greeting for Mai” làm phép xác minh duy nhất: dòng ấy chỉ xuất hiện khi task action thật sự chạy, không khi FROM-CACHE/UP-TO-DATE. Nội dung file và task outcome mới là cặp bằng chứng quan trọng.

### 7.9. Chạy lần hai trong cùng workspace

~~~bash
./gradlew renderGreeting --build-cache --console=plain
~~~

Với inputs/outputs không đổi và không có tác động ngoài:
- Task **có thể UP-TO-DATE**.
- Task action không chạy lại.
- File vẫn chứa Hello, Mai!.

Không kỳ vọng chắc chắn FROM-CACHE ở lượt này vì output đang tồn tại và up-to-date checks thường tránh cả cache retrieval.

### 7.10. Xóa build outputs nhưng giữ Build Cache

~~~bash
./gradlew clean renderGreeting --build-cache --console=plain
~~~

**Lưu ý quan trọng:** Root build.gradle lab **chưa áp plugin base/java**, nên Gradle không bảo đảm có task clean mặc định. Trước lệnh này, thêm vào **đầu root build.gradle**:

~~~groovy
plugins {
    id 'base'
}
~~~

Sau đó giữ nguyên import demo.RenderGreetingTask và tasks.register block như mục 7.6. **Để tránh nhầm, cấu hình root build.gradle hoàn chỉnh sau khi bổ sung base plugin là:**

~~~groovy
import demo.RenderGreetingTask

plugins {
    id 'base'
}

tasks.register('renderGreeting', RenderGreetingTask) {
    recipient.set(
        providers.gradleProperty('recipient').orElse('Mai')
    )
    templateFile.set(
        layout.projectDirectory.file('src/template/greeting.txt')
    )
    outputFile.set(
        layout.buildDirectory.file('generated/greeting.txt')
    )
}
~~~

**Tại sao cần base plugin?** Nó cung cấp lifecycle task clean để xóa project buildDirectory. Nếu không muốn sửa build.gradle, có thể xóa riêng build/generated output bằng filesystem command, nhưng không nên diễn giải “clean” là có sẵn trong mọi Gradle project không áp plugin lifecycle.

Sau khi thêm plugin base, lần đầu chạy lại renderGreeting với --build-cache nếu task implementation/model đổi làm cache key khác. Khi một cache entry tồn tại:
- **clean** xóa project build output.
- **renderGreeting** có thể **FROM-CACHE** và phục hồi output mà không chạy render().
- **local build cache trong GRADLE_USER_HOME vẫn còn**, vì clean không xóa nó.
- Nếu cache entry không tồn tại hoặc không hợp lệ, task sẽ thực thi và có thể lưu entry mới.

**Không khẳng định mọi lượt clean renderGreeting đều FROM-CACHE**: key/entry/cache enablement quyết định.

### 7.11. Tắt Build Cache để chứng minh task thực thi

~~~bash
./gradlew clean renderGreeting --no-build-cache --console=plain
~~~

Nếu output đã bị clean, task phải tạo output mới. Lúc này không thể FROM-CACHE vì cache disabled. Quan sát dòng logger “Rendered greeting for Mai” nếu task action chạy.

Để ép chạy mà không cần clean:

~~~bash
./gradlew renderGreeting --rerun-tasks --no-build-cache --console=plain
~~~

**--rerun-tasks** yêu cầu chạy lại tasks kể cả khi input/output không đổi; **--no-build-cache** tránh load cache. Đây là chế độ debug/QA, không cần áp mặc định cho mọi build.

### 7.12. Đổi scalar input để xem cache key thay đổi

~~~bash
./gradlew renderGreeting \
  -Precipient=Lan \
  --build-cache --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat renderGreeting -Precipient=Lan --build-cache --console=plain
~~~

**File mới:**

~~~text
Hello, Lan!
~~~

recipient là @Input Property<String>. Thay Mai → Lan làm input fingerprint đổi; cache key đổi nếu những yếu tố khác giữ nguyên. Task có thể thực thi hoặc FROM-CACHE nếu cache entry cho Lan đã từng được lưu.

### 7.13. Đổi file input để xem cache key thay đổi

Trong **src/template/greeting.txt**, đổi:

~~~text
Hello
~~~

thành:

~~~text
Welcome
~~~

Chạy task với recipient Mai:

~~~bash
./gradlew renderGreeting -Precipient=Mai --build-cache
~~~

**File mới:**

~~~text
Welcome, Mai!
~~~

Dù @PathSensitive(NONE) bỏ path khỏi fingerprint, **nội dung file vẫn được tính vào cache key**. NONE không có nghĩa file bị bỏ qua; nó chỉ bỏ qua path component. Trả template về Hello trước khi làm các thí nghiệm relocatability có so sánh đầu ra.

### 7.14. Xem thông tin nguyên nhân cache miss

~~~bash
./gradlew renderGreeting --build-cache --info --console=plain
~~~

Gradle có thể in thông tin về task up-to-date/cacheability, cache key và lý do không dùng cache, tùy phiên bản và verbosity. Nếu muốn chẩn đoán sâu:
- Dùng build cache debugging guide chính thức.
- So sánh hai builds bằng build scan/Develocity nếu tổ chức có quyền.
- Xem task inputs/implementation classpath và normalized file paths.
- Không cần grep một câu log cố định rồi coi đó là API ổn định.

## 8. Kiểm chứng output bằng Java 17 độc lập

Ta tạo một chương trình Java chỉ đọc file kết quả. Nó **không cần Gradle API**.

**src/main/java/demo/ReadGreeting.java**

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReadGreeting {
    private ReadGreeting() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Expected one output file path"
            );
        }
        String text = Files.readString(
                Path.of(args[0]),
                StandardCharsets.UTF_8
        );
        System.out.print(text);
    }
}
~~~

### 8.1. Linux/macOS

Đảm bảo template hiện là Hello và recipient không có -P override:

~~~bash
./gradlew renderGreeting --build-cache
mkdir -p build/manual-classes
javac -encoding UTF-8 -d build/manual-classes \
  src/main/java/demo/ReadGreeting.java
java -cp build/manual-classes demo.ReadGreeting \
  build/generated/greeting.txt
~~~

**Stdout chính xác của Java Reader:**

~~~text
Hello, Mai!
~~~

### 8.2. Windows PowerShell

~~~powershell
.\gradlew.bat renderGreeting --build-cache
New-Item -ItemType Directory -Force build\manual-classes | Out-Null
javac -encoding UTF-8 -d build\manual-classes src\main\java\demo\ReadGreeting.java
java -cp build\manual-classes demo.ReadGreeting build\generated\greeting.txt
~~~

Reader in cùng một dòng với LF cuối. **Chương trình này kiểm tra bytes/text artifact**, không chứng minh nguồn artifact đến từ execution mới hay cache. Muốn biết provenance, phải xem task outcome.

### 8.3. Hash file để kiểm chứng byte-for-byte

Linux/macOS:

~~~bash
sha256sum build/generated/greeting.txt
~~~

Trên macOS có thể dùng:

~~~bash
shasum -a 256 build/generated/greeting.txt
~~~

Windows PowerShell:

~~~powershell
Get-FileHash build\generated\greeting.txt -Algorithm SHA256
~~~

Kết quả là một digest hexadecimal phụ thuộc bytes thực tế. **Không cần memorise digest**; hãy so sánh digests giữa hai checkout/CI machines. Khi bytes giống hệt, SHA-256 sẽ giống hệt (bỏ qua xác suất va chạm không đáng kể); nếu khác, điều tra line endings, encoding và output generation.

**Đừng nhầm hash của file output với Gradle build cache key.** Cache key còn tính task implementation và inputs, không chỉ hash output.

## 9. Thử relocatability giữa hai checkout khác path

Một task **relocatable** có thể dùng cached output dù root directory thay đổi. Thử theo bước:

1. Chuẩn bị checkout A và checkout B chứa **chính xác cùng sources và build logic**, gồm build.gradle, settings.gradle, buildSrc và src/template/greeting.txt. **Không copy build/ hoặc .gradle/** từ A sang B.
2. Dùng **cùng Gradle Wrapper/JDK** trên cả hai. Nếu cùng một máy, cả hai mặc định chia sẻ GRADLE_USER_HOME và local build cache.
3. Trong A, chạy **./gradlew clean renderGreeting --build-cache** để tạo/populate cache entry.
4. Trong B, chạy **./gradlew renderGreeting --build-cache --info**.
5. Quan sát xem renderGreeting của B có **FROM-CACHE** không. Nếu có, so file output/hash.
6. Nếu không có, đối chiếu task inputs, buildSrc implementation classpath, template bytes, wrapper/toolchain và cache configuration.

**Một cache miss không tự phủ định việc task relocatable**: có thể cache entry chưa được push, bị eviction hoặc có implementation/environment khác. Ngược lại, cache hit **không thay kiểm thử** rằng output được tạo đúng khi execution thực sự xảy ra.

### 9.1. Bài thử với hai máy khác nhau

Nếu A/B ở hai máy khác nhau:
- Local caches thông thường là riêng biệt.
- Cần một shared remote build cache hoặc cơ chế chia sẻ cache được hỗ trợ.
- Cả hai dùng cùng credentials đọc.
- A/CI phải push một cache entry hợp lệ lên server.
- B tải entry khi có cùng key.

**Không copy ~/.gradle nguyên thư mục từ máy này sang máy khác** như phương pháp chuẩn. Nó chứa nhiều caches và metadata khác nhau; dùng remote cache được hỗ trợ sẽ có hợp đồng rõ hơn.

### 9.2. Vì sao @PathSensitive(NONE) được chọn?

RenderGreetingTask chỉ dùng **bytes nội dung của template**; output không ghi tên file hoặc đường dẫn. Nếu template cùng bytes ở A/B, NONE cho phép bỏ khác biệt absolute checkout paths khỏi fingerprint.

Nếu task cần in tên file vào output, phải đổi sang NAME_ONLY hoặc RELATIVE và thêm filename vào logic đúng; không được giữ NONE chỉ để ép cache hit.

### 9.3. Tránh thêm absolute checkout path vào @Input

~~~java
// Anti-pattern: projectRootPath thay đổi giữa hai machines.
@Input
public abstract Property<String> getProjectRootPath();
~~~

Nếu task không cần project root path để tạo output, property này gây cache miss không cần thiết. Nếu output thật phụ thuộc vào path, chỉ loại @Input là **sai correctness**; phải thay đổi output design để portable hoặc chấp nhận non-relocatable.

### 9.4. File input hierarchy và RELATIVE

Nếu task xử lý một cây source:
- Relative path có thể xác định package/resource path.
- Với @InputFiles FileCollection/@InputDirectory DirectoryProperty, dùng **@PathSensitive(PathSensitivity.RELATIVE)** khi cấu trúc bên trong input root có ý nghĩa.
- Không dùng NONE nếu hai files có cùng contents nhưng khác paths phải tạo hai outputs khác nhau.

**Path normalization phải phản ánh semantics của task**, không phải một công cụ để tăng hit rate bằng mọi giá.

## 10. Cấu hình local và remote Build Cache

Gradle hỗ trợ cấu hình local và remote build cache trong **settings.gradle**. Local cache mặc định có sẵn và enabled, nhưng Gradle **chỉ dùng build cache khi caching đã được bật** qua flag/property.

### 10.1. Local cache

Một cấu hình tùy chọn:

~~~groovy
buildCache {
    local {
        enabled = true
        push = true
    }
}
~~~

Thông thường không cần khai báo khi dùng mặc định:
- Local cache được cấu hình sẵn.
- Push local enabled theo mặc định khi cache được dùng.
- Location nằm trong Gradle User Home và được Gradle quản lý.

### 10.2. HTTP remote cache

**Mẫu cấu hình minh họa trong settings.gradle**, không gắn vào lab mặc định nếu bạn chưa có server thật:

~~~groovy
import org.gradle.caching.http.HttpBuildCache

buildCache {
    remote(HttpBuildCache) {
        url = 'https://cache.example.invalid/cache/'
        push = providers.environmentVariable('CI')
                .map { it == 'true' }
                .getOrElse(false)
    }
}
~~~

**.invalid là placeholder cố ý không phải server thực.** Để dùng thật phải thay URL bằng endpoint đã được tổ chức cấp, xác minh HTTPS/certificate/credentials. Mẫu này chỉ minh họa cách cho CI với CI=true được push; cần thêm policy/trust controls trước khi triển khai production.

Gradle remote HTTP cache có thể đọc bằng HTTP GET theo cache key và ghi bằng PUT theo cache key khi push enabled. Không nên nhầm endpoint ấy với **Maven repository**: Maven modules có group/artifact/version/metadata; build cache entries có key của task inputs.

### 10.3. Credentials cho remote cache

Một cấu hình khác khi remote server yêu cầu Basic authentication:

~~~groovy
import org.gradle.caching.http.HttpBuildCache

buildCache {
    remote(HttpBuildCache) {
        url = 'https://cache.example.invalid/cache/'
        push = providers.environmentVariable('CI')
                .map { it == 'true' }
                .getOrElse(false)

        credentials {
            username = providers.gradleProperty('cacheUsername')
                    .orElse('')
                    .get()
            password = providers.gradleProperty('cachePassword')
                    .orElse('')
                    .get()
        }
    }
}
~~~

Đây là **mẫu thay thế** cho phần remote ở mục 10.2, không nên đặt cả hai remote(HttpBuildCache) blocks cùng lúc. Mật khẩu không xuất hiện trong build script; nó lấy từ Gradle property **cachePassword** do CI secret manager hoặc người dùng cung cấp.

Một cách truyền qua environment variables:

~~~text
ORG_GRADLE_PROJECT_cacheUsername
ORG_GRADLE_PROJECT_cachePassword
~~~

Không commit token thật trong gradle.properties của repository, không in credentials trong console, và không tắt TLS verification để chữa lỗi authentication.

**Lưu ý:** Nếu credentials là required, nên để build fail rõ ràng khi thiếu secret thay vì gọi một endpoint bằng empty username/password; .orElse('') ở snippet chỉ để minh họa nguồn value và tránh đọc property vắng mặt ở configuration, không phải best practice bắt buộc cho production. Trong hệ thống thật, dùng provider configuration/validation phù hợp với chính sách bảo mật.

### 10.4. Push/read policies

| Nguồn | Quyền khuyến nghị | Lý do |
|---|---|---|
| Trusted CI clean builds | Read + push | Tạo cache entries đã được validate |
| Developer machines | Read-only | Hạn chế poisoning do workspace bị sửa trong lúc build |
| Public/untrusted PR builds | Thường read-only, cách ly theo chính sách | Không để code chưa được tin cậy ghi vào shared cache |
| Release pipeline | Read và push theo policy, có thêm verification | Cần provenance và integrity |
| Local developer cache | Read + push local | Tăng tốc những lượt build trên cùng máy |

**Không coi cache output là bằng chứng test vừa chạy trên machine hiện tại.** Với high-assurance release/integration checks, có thể yêu cầu test execution fresh và cache policy riêng.

## 11. Cache hit rate và chi phí

Cache không phải lúc nào cũng nhanh hơn thực thi:
- Cache entry có thể lớn và tải qua mạng chậm.
- Task rẻ như Copy có thể nhanh hơn restore.
- Outputs nén lớn có I/O và CPU overhead.
- Remote latency, congestion và authentication failure gây chậm.
- Nếu inputs không ổn định, chi phí lookup cao nhưng hiếm hit.
- Nếu Gradle phải evaluate build logic/toolchain khác trước khi lookup, configuration overhead vẫn tồn tại.

Ưu tiên cache các tasks **tốn CPU, deterministic, có outputs vừa phải** như compilation, code generation và reports phù hợp.

### 11.1. Thước đo cần theo dõi

| Metric | Câu hỏi |
|---|---|
| Cache eligible task count | Bao nhiêu tasks đủ điều kiện dùng cache? |
| Cache hit count/rate | Bao nhiêu eligible tasks nhận FROM-CACHE? |
| Avoided execution time | Tổng công việc được tránh là bao nhiêu? |
| Remote download time/bytes | Cache retrieval có rẻ hơn execute không? |
| Remote upload time/bytes | Push có đáng giá không? |
| Miss reasons | Inputs hay implementation nào liên tục đổi? |
| Relocation success | Hai paths/CI agents có cùng key khi đáng ra phải có không? |
| Repeatability | Cùng inputs có output hashes giống nhau không? |
| False-hit audit | Có hidden inputs khiến output sai mà key không đổi? |

**Đừng tối ưu hit rate bằng cách bỏ khai báo input thật.** Một cache miss đúng còn tốt hơn false cache hit trả binary sai.

## 12. Chiến lược kiểm thử cache cho custom task

Để chứng minh một task thực sự cacheable, nên test ít nhất bốn đặc tính độc lập:

1. **Correctness:** Lần execute đầu tạo outputs đúng với inputs.
2. **Up-to-date:** Không đổi inputs/outputs, lượt sau UP-TO-DATE.
3. **Cache reuse:** Xóa outputs hoặc chạy workspace khác, FROM-CACHE nếu entry có.
4. **Relocatability + repeatability:** Với cùng semantic inputs ở hai roots, output có cùng bytes, có thể dùng chung key; nếu task thực thi lại, bytes vẫn giống.

### 12.1. Ma trận QA

| Thí nghiệm | Input thay đổi? | Cache entry sẵn? | Kết quả kỳ vọng |
|---|---|---|---|
| Fresh workspace, empty cache | Không | Không | Task EXECUTED |
| Chạy lại cùng workspace | Không | Có thể | UP-TO-DATE |
| clean + --build-cache | Không | Có | FROM-CACHE nếu eligible |
| clean + --no-build-cache | Không | Không được dùng | EXECUTED |
| --rerun-tasks --no-build-cache | Không | Không được dùng | EXECUTED |
| recipient Mai→Lan | Có | Có thể chưa | EXECUTED hoặc FROM-CACHE với key Lan |
| template Hello→Welcome | Có | Có thể chưa | EXECUTED hoặc FROM-CACHE với key Welcome |
| Checkout B cùng source, remote shared | Không | Có | FROM-CACHE nếu key khớp |
| Khác plugin/task class bytecode | Implementation đổi | Key khác | MISS trừ entry mới đã có |
| Input path ABSOLUTE khác checkout | Path fingerprint đổi | Key khác | MISS thường gặp |
| Output chứa timestamp ẩn | Input khai báo có thể không đổi | Key có thể trùng | **Sai thiết kế** dù cache hit |

Các outcomes là **điều kiện/kỳ vọng**, không phải lời hứa cố định nếu cache đã có nhiều entries, Gradle đổi implementation hoặc tasks bị disabled.

### 12.2. Tạo test không phụ thuộc trạng thái ẩn

Nếu muốn đo chắc chắn một cache miss:
- Dùng một **isolated Gradle User Home/cache** tạm cho thí nghiệm, hoặc namespace test được kiểm soát.
- Tránh xóa ~/.gradle toàn máy trong môi trường làm việc thật.
- Chạy clean build và ghi lại Gradle Wrapper/JDK version.
- Đừng copy build/ và .gradle từ producer checkout sang consumer checkout nếu đang test cache cross-directory.
- Đừng chỉnh sửa template giữa lúc task đang chạy.
- Kiểm tra file hashes, không chỉ sự tồn tại.
- Dùng --info hoặc Develocity Build Scan khi cần so sánh key/input fingerprints.

### 12.3. Gradle TestKit cho plugin task

Một custom task plugin có thể dùng **Gradle TestKit/GradleRunner** để chạy cùng plugin trong hai thư mục tạm:
- Test 1: tạo project A, chạy task với --build-cache, kiểm tra output và TaskOutcome.SUCCESS.
- Test 2: chạy lại A, kiểm tra TaskOutcome.UP_TO_DATE nếu environment ổn định.
- Test 3: tạo B với source/config tương đương, dùng shared cache directory, kiểm tra TaskOutcome.FROM_CACHE khi hệ thống cho phép.
- Test 4: đổi input/property, assert expected bytes và cache miss/hit tương ứng.
- Test 5: chạy A/B với path khác và so output hashes; không để output chứa checkout path.

**TestKit test cần kiểm soát GradleUserHome/classpath** khi kiểm thử cross-build cache. Không chỉ gọi GradleRunner một lần rồi tuyên bố relocatability đã được kiểm chứng.

## 13. Những lỗi thường gặp và cách xử lý

### Lỗi 1 — Chạy task hai lần, lượt hai UP-TO-DATE chứ không FROM-CACHE

**Nguyên nhân:** Workspace vẫn có outputs đúng với inputs, Gradle không cần load cache.

**Cách sửa:** Đây thường là hành vi đúng. Muốn kiểm tra build cache retrieval, dùng clean/isolated checkout và --build-cache, giữ cache entry.

### Lỗi 2 — Chạy clean xong task vẫn FROM-CACHE

**Nguyên nhân:** clean xóa build outputs, không xóa local build cache trong Gradle User Home.

**Cách sửa:** Không cần sửa nếu đúng. Nếu cần fresh execution, dùng --no-build-cache cùng clean hoặc --rerun-tasks để ép chạy, tùy mục đích.

### Lỗi 3 — --no-build-cache nhưng task UP-TO-DATE

**Nguyên nhân:** Up-to-date checks độc lập với build cache.

**Cách sửa:** Nếu cần rerun, dùng --rerun-tasks; nếu chỉ cần output hợp lệ, UP-TO-DATE là chính xác.

### Lỗi 4 — Hai máy source giống nhau nhưng cache key khác

**Nguyên nhân:** Normalized input paths, buildSrc/plugin implementation, toolchain, dependency versions, compiler flags hoặc environment inputs có thể khác.

**Cách sửa:** So sánh cache keys và input fingerprints bằng --info/Build Scan; không đoán rằng cache server bị lỗi.

### Lỗi 5 — File input ở đường dẫn khác gây miss

**Nguyên nhân:** @InputFile chưa cấu hình @PathSensitive nên dùng ABSOLUTE normalization hoặc một @Input String chứa absolute path.

**Cách sửa:** Chọn NONE/NAME_ONLY/RELATIVE nếu behavior cho phép; không loại thông tin đường dẫn có ảnh hưởng output.

### Lỗi 6 — Cache hit nhưng output sai

**Nguyên nhân:** Hidden input không khai báo: environment, clock, external API, system property hoặc input file không được mô hình hóa; cũng có thể cache poisoning.

**Cách sửa:** Audit mọi dependency của task action, khai báo input thật và kiểm soát trusted cache writers. Bật fresh execution/so hashes để chẩn đoán.

### Lỗi 7 — Task được @CacheableTask nhưng không dùng cache

**Nguyên nhân:** Build cache off, task type có cacheability restrictions, outputs overlap, validation error hoặc task không có outputs.

**Cách sửa:** Xem --info, task annotations/outputs, cache settings và task status; không chỉ thêm một @CacheableTask.

### Lỗi 8 — Thay toolchain/JDK khiến cache misses

**Nguyên nhân:** Compiler toolchain và implementation inputs có thể ảnh hưởng cache key hoặc output semantics.

**Cách sửa:** Pin Gradle Wrapper/JDK/toolchain theo policy; không ép dùng cache bytes từ toolchain khác nếu không tương thích.

### Lỗi 9 — JAR thay đổi hash dù source không đổi

**Nguyên nhân:** Timestamps, file order, manifest build number, archive metadata hoặc tool output không deterministic.

**Cách sửa:** Cấu hình reproducible archives, kiểm tra manifest values và generated resources, không dựa vào timestamps.

### Lỗi 10 — @PathSensitive(NONE) tạo false hit

**Nguyên nhân:** Task thực sự dùng filename/path trong output nhưng đã bảo Gradle rằng path không ảnh hưởng.

**Cách sửa:** Dùng NAME_ONLY/RELATIVE/ABSOLUTE đúng behavior; thêm tests đổi đường dẫn nhưng giữ bytes.

### Lỗi 11 — Cache hit rate thấp do dynamic versions

**Nguyên nhân:** -SNAPSHOT, '+' version, artifact metadata thay đổi hoặc dependencies không ổn định.

**Cách sửa:** Pin versions/lock dependencies khi hợp lý; xác nhận resolution trước khi phân tích task caching.

### Lỗi 12 — --refresh-dependencies không làm task execute fresh

**Nguyên nhân:** --refresh-dependencies quản lý dependency resolution, không tắt up-to-date checks/build cache.

**Cách sửa:** Dùng flags đúng vấn đề: --rerun-tasks, --no-build-cache, --refresh-dependencies có chức năng khác nhau.

### Lỗi 13 — Remote cache có entry nhưng machine B không hit

**Nguyên nhân:** Credential/network/permissions, key không khớp, server entry bị eviction hoặc Gradle version khác.

**Cách sửa:** Kiểm tra GET access và build cache debug logs, so normalized inputs và toolchain. Không bật insecure HTTP/TLS để né lỗi.

### Lỗi 14 — Developers được push làm cache chứa outputs không tin cậy

**Nguyên nhân:** Shared cache writers thiếu kiểm soát hoặc build inputs bị chỉnh sửa khi task đang chạy.

**Cách sửa:** Trusted CI push, developers read-only; dùng HTTPS, auth, access control và CI validation.

### Lỗi 15 — Gradle cache chứa JAR nhưng lệnh test FROM-CACHE không chạy JUnit mới

**Nguyên nhân:** Cached Test outputs được phục hồi. Build cache phục vụ reuse, không đảm bảo fresh test execution.

**Cách sửa:** Nếu chính sách yêu cầu test chạy ở CI job hiện tại, dùng --rerun-tasks --no-build-cache cho Test task phù hợp; kiểm tra test events.

### Lỗi 16 — Một task ghi cùng output folder với task khác

**Nguyên nhân:** Overlapping output files làm Gradle khó quản lý snapshots/cache và có thể gây race.

**Cách sửa:** Chia output ownership rõ và khai báo @OutputFile/@OutputDirectory không chồng lấn.

### Lỗi 17 — Task rất rẻ nhưng cache load chậm hơn execute

**Nguyên nhân:** I/O/network/compression overhead vượt giá trị công việc được tránh.

**Cách sửa:** Không cache task đó hoặc tối ưu phạm vi tasks cần cache; đo latency/bytes thực tế.

### Lỗi 18 — Lẫn Configuration Cache với Build Cache

**Nguyên nhân:** Hai cơ chế đều có từ cache, nhưng dữ liệu và key khác nhau.

**Cách sửa:** Configuration Cache cho configured task graph; Build Cache cho task outputs. Hai flags và locations riêng.

### Lỗi 19 — Test relocatability bằng hai checkout nhưng copy luôn build/ và .gradle/

**Nguyên nhân:** Các outputs và local state cũ che sự thật, có thể UP-TO-DATE mà không dùng cache chung.

**Cách sửa:** Tạo checkout B sạch, chỉ copy sources/build logic/Wrapper và giữ shared remote/local build cache theo bài thử.

### Lỗi 20 — Dùng @Input Property<String> chứa full absolute output path

**Nguyên nhân:** Output destination path không nên tự động được xem là input nếu không ảnh hưởng bytes. Đưa nó vào scalar key khiến cache khác giữa máy.

**Cách sửa:** Dùng @OutputFile RegularFileProperty; đừng stringify output path để lưu trong @Input chỉ vì cần vị trí file.

### Lỗi 21 — Generated output nhúng hostname/user home

**Nguyên nhân:** Output không repeatable giữa machines, có thể còn tạo false cache hits.

**Cách sửa:** Loại machine-specific metadata hoặc khai báo input có chủ đích; test byte-for-byte across machines.

### Lỗi 22 — CI cache hit nhưng team kết luận code đã được biên dịch lại hôm nay

**Nguyên nhân:** FROM-CACHE là reuse compiled outputs, không phải compiler invocation mới.

**Cách sửa:** Ghi đúng task outcomes; dùng fresh-build policy khi cần binary provenance khác với reuse.

## 14. Checklist để review một cacheable Gradle task

1. Task type có thực sự phù hợp cache output không?
2. @CacheableTask có được áp đúng trên type, và cache có bật khi dùng không?
3. Task implementation và task actions có được Gradle track ổn định?
4. Mọi scalar values ảnh hưởng output có @Input hoặc TaskInputs đúng không?
5. Mọi input files có @InputFile/@InputFiles phù hợp?
6. File paths có @PathSensitive phù hợp với semantics?
7. Classpath input có @Classpath/@CompileClasspath khi thích hợp?
8. Task outputs có @OutputFile/@OutputDirectory không?
9. Có output files bị thiếu hoặc thừa ngoài contract không?
10. Có tasks khác ghi đè/overlap output folder không?
11. Có dùng clock/random/network/username/hostname ẩn không?
12. Có đúng charset UTF-8 và newline policy không?
13. Có sắp xếp collections/files theo thứ tự deterministic không?
14. Archives có reproducible timestamps/file order khi cần không?
15. Output có nhúng absolute checkout path không?
16. Build logic/plugin/JDK/Gradle Wrapper versions có nhất quán không?
17. Dependency versions có được pin hoặc quản lý ổn định không?
18. Two clean checkouts có cùng output SHA-256 khi execute thật không?
19. Same workspace rerun có thể UP-TO-DATE không?
20. clean + cached entry có thể FROM-CACHE không?
21. Remote cache có TLS/auth và trusted push policy không?
22. Developer machines có chỉ read remote cache khi phù hợp không?
23. Có phân biệt cache misses hợp lý với false hits nguy hiểm không?
24. Có log/build scan giải thích vì sao key khác không?
25. Có test negative case đổi template, recipient, tool version không?
26. Có test relocation giữa directories/machines không?
27. Có kiểm tra task outputs correctness chứ không chỉ hit rate không?
28. Có tránh coi FROM-CACHE là fresh test/compiler execution không?

## 15. Bài tập tự kiểm tra

**Bài 1.** Vì sao task UP-TO-DATE khác FROM-CACHE dù cả hai không gọi @TaskAction?

**Bài 2.** Cache key của Gradle có chỉ gồm SHA256 source file không?

**Bài 3.** Tên task path :app:compileJava có bắt buộc nằm trong build cache key không?

**Bài 4.** Vì sao cùng source nhưng đổi plugin/task implementation có thể làm cache miss?

**Bài 5.** @CacheableTask có tự bật build cache không?

**Bài 6.** Vì sao Custom task với @Input/@Output vẫn có thể UP-TO-DATE nhưng không được load FROM-CACHE?

**Bài 7.** Tại sao build cache có thể hoạt động giữa hai checkout path khác nhau trong cùng máy?

**Bài 8.** Nếu user home A và B khác nhau, có cần remote cache để hai máy khác nhau chia sẻ outputs không?

**Bài 9.** Với templateFile của lab, vì sao PathSensitivity.NONE có thể đúng?

**Bài 10.** Nếu task đưa basename của template vào output, có còn được dùng NONE mà không thay thiết kế không?

**Bài 11.** Vì sao một output chứa Instant.now() nhưng thiếu @Input có thể gây false cache hit?

**Bài 12.** Khi nào nên dùng RELATIVE thay ABSOLUTE?

**Bài 13.** @OutputFile nhận đường dẫn ở build/ có nên được tự ghi thêm vào @Input String để key “đầy đủ” không?

**Bài 14.** Task custom compile code trên JDK khác nhau có nhất thiết an toàn reuse binary cache không?

**Bài 15.** clean xóa những gì và không xóa những gì liên quan build cache?

**Bài 16.** --no-build-cache có bảo đảm một task execute mới không?

**Bài 17.** --refresh-dependencies có cùng chức năng với --rerun-tasks không?

**Bài 18.** Map output serialize theo thứ tự bất định ảnh hưởng điều gì?

**Bài 19.** Vì sao overlapping output directories nguy hiểm cho caching?

**Bài 20.** Task remote upload có nên được cacheable chỉ vì nó có @Input URL không?

**Bài 21.** Vì sao trusted CI push, developer remote read-only là chính sách hợp lý?

**Bài 22.** Trình bày bốn phép thử để xác minh cacheability/relocatability.

**Bài 23.** Nếu template Hello→Welcome nhưng Gradle vẫn FROM-CACHE của Hello, khả năng sai ở đâu?

**Bài 24.** Hai machines có FROM-CACHE và same output SHA-256, có thể tuyên bố JUnit tests mới chạy trên cả hai không?

### Gợi ý đáp án

1. UP-TO-DATE dùng outputs đang có trong workspace; FROM-CACHE phục hồi cached outputs từ key phù hợp.
2. **Không.** Key còn task/action implementation, output property names và mọi declared inputs.
3. **Không.** Task path không mặc định là một phần build cache key.
4. Task implementation/classpath được tính trong key để tránh reuse output của code khác.
5. **Không.** Phải bật --build-cache hoặc org.gradle.caching=true, và task đủ điều kiện.
6. Custom task type không cacheable mặc định; phải opt in đúng cùng với đầy đủ inputs/outputs.
7. Hai checkout cùng Gradle User Home có thể dùng chung local cache, nếu key đúng và task relocatable.
8. **Thông thường có**, vì local caches nằm riêng từng máy; dùng remote cache được hỗ trợ.
9. Task chỉ dùng bytes template, không dùng path hoặc filename.
10. **Không.** Phải dùng normalization phản ánh filename semantics, như NAME_ONLY hoặc RELATIVE.
11. Cùng declared inputs tạo key giống nhau nhưng task thực thi thực tế cho bytes khác.
12. Khi relative hierarchy quan trọng nhưng absolute checkout location không quan trọng.
13. **Không**, trừ khi absolute output path thật sự ảnh hưởng bytes; dùng @OutputFile.
14. **Không chắc.** Compiler/toolchain/platform semantics phải phù hợp và được model hóa.
15. clean xóa project build outputs; không tự xóa local build cache trong Gradle User Home.
16. **Không.** Up-to-date checks vẫn có thể bỏ qua task; dùng --rerun-tasks khi cần.
17. **Không.** --refresh-dependencies quản lý resolution, --rerun-tasks quản lý task execution.
18. Làm output nondeterministic, gây byte differences và cache invalidation/poisoning.
19. Gradle khó xác định ownership, có thể disable caching, gây stale outputs/races.
20. **Không.** Remote side effects không được bảo đảm xảy ra nếu task action bị bỏ qua.
21. Hạn chế cache poisoning từ untrusted workspaces, giữ một nguồn có thể audit.
22. Correctness, up-to-date, clean cached reuse, two-directory relocation/byte-for-byte comparison.
23. Input templateFile chưa được khai báo/fingerprinted đúng, cache entry sai hoặc có side effect/poisoning.
24. **Không.** FROM-CACHE có nghĩa task action được bỏ qua ở lượt hiện tại.

## 16. Tài liệu chính thức

- [Gradle User Manual — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): build cache enablement, local/remote caches, cache key, built-in cacheable tasks và HTTP cache.
- [Gradle User Manual — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): cache key constituents, repeatable outputs, stable inputs, relocatability, input normalization và overlapping outputs.
- [Gradle User Manual — Build Cache Use Cases](https://docs.gradle.org/current/userguide/build_cache_use_cases.html): cache reuse giữa branches/developers, CI-populated remote cache và shared-cache safety.
- [Gradle User Manual — Debugging Build Cache Misses](https://docs.gradle.org/current/userguide/build_cache_debugging.html): cache key diagnostic và testing relocation giữa hai checkouts.
- [Gradle User Manual — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): task input/output snapshots, up-to-date checks và annotations.
- [Gradle User Manual — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): Configuration Cache khác Build Cache.
- [Gradle User Manual — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): modules cache và --refresh-dependencies.
- [Gradle User Manual — Best Practices for Performance](https://docs.gradle.org/current/userguide/best_practices_performance.html): reproducible encoding, build caching và performance.
- [Gradle User Manual — Task Input/Output Annotations](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): @CacheableTask, @InputFile, @PathSensitive, @OutputFile.
- [Gradle API — PathSensitivity](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/PathSensitivity.html): ABSOLUTE, RELATIVE, NAME_ONLY, NONE.
- [Gradle API — CacheableTask](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/CacheableTask.html): điều kiện opt-in cacheability.
- [Gradle API — HttpBuildCache](https://docs.gradle.org/current/javadoc/org/gradle/caching/http/HttpBuildCache.html): remote HTTP build cache credentials/security.

**Ghi nhớ:** **Build Cache key** phụ thuộc vào task implementation/actions, tên output properties và những inputs đã được khai báo; nó **không chỉ là tên task hoặc hash của source**. Để reuse giữa máy, cần cùng semantic inputs, toolchain/plugin/build logic phù hợp và **path normalization chính xác**. Để reuse **an toàn**, task phải tạo cùng bytes cho cùng inputs, không đọc hidden environment/time/random và không ghi outputs chồng lấn. **UP-TO-DATE** khác **FROM-CACHE**; **Configuration Cache** và **dependency cache** là lớp khác. Hãy ưu tiên trusted CI push, developers remote read-only, và chứng minh correctness bằng output hashes cùng tests trước khi tối ưu cache hit rate.