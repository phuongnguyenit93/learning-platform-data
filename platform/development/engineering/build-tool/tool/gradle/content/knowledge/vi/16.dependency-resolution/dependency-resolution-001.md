# Quá trình phân giải dependency trong Gradle: từ khai báo đến component, variant và artifact

## 1. Mục tiêu bài học

Khi viết một dòng như:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

bạn **chưa** chỉ định một file JAR cụ thể. Bạn đang khai báo một **yêu cầu phụ thuộc** (dependency request) trên một configuration. Từ yêu cầu ấy, Gradle cần xác định phiên bản component, các phụ thuộc bắc cầu, cách sử dụng phù hợp (variant) và cuối cùng là những file đầu vào thực tế (artifacts) cho compiler hoặc runtime.

Để hiểu đúng, hãy phân biệt các khái niệm:

- **Dependency declaration / dependency request:** yêu cầu cần một module/project và những điều kiện đi kèm (version, constraint, attributes, capability, exclusions...).
- **Module:** đơn vị được định danh bằng `group:name` trong kho Maven/Ivy; một module có nhiều version.
- **Component:** một phiên bản cụ thể của module, chẳng hạn `org.apache.commons:commons-lang3:3.17.0`; component còn có thể là project component trong multi-project/composite build.
- **Variant:** một cách mà component có thể được tiêu thụ, ví dụ Java API để compile, Java runtime để chạy, platform, debug/release, source/javadoc hoặc target hệ điều hành. Variant có **attributes**, có thể có **capabilities**, dependencies và artifacts riêng.
- **Artifact:** một file cụ thể như JAR, AAR, ZIP, thư mục class, metadata output, hoặc một artifact đã được transform.
- **Configuration:** mô hình Gradle xác định chỗ khai dependency, nơi consumer yêu cầu tập files, hoặc nơi producer xuất bản variants.
- **Resolution result:** kết quả Gradle chọn được component/variant và sau đó các artifact cần thiết, không đồng nghĩa với chuỗi ký tự khai trong `dependencies`.

**Mục tiêu kiểm chứng:** Giải thích được vì sao cùng `project(':engine')` nhưng `compileClasspath` có thể chọn `apiElements` còn `runtimeClasspath` chọn `runtimeElements`, và vì sao hai configuration có thể cho **tập file cũng như tập dependency bắc cầu khác nhau**.

Bài dùng Gradle **Groovy DSL** (`settings.gradle`, `build.gradle`), ví dụ Java 17+ và Gradle Wrapper. Trên Linux/macOS chạy `./gradlew`; Windows PowerShell dùng `.\gradlew.bat`. Các phiên bản thư viện trong ví dụ chỉ được dùng để minh họa, không hàm ý phiên bản mới nhất.

## 2. Bức tranh tổng thể: có hai giai đoạn resolution chính

Theo mô hình chính thức của Gradle, dependency resolution gồm hai nhóm công việc lớn:

1. **Graph resolution:** dựng đồ thị từ yêu cầu dependency, đọc metadata, giải quyết phiên bản/component, chọn những variants tương thích theo attributes và duyệt các dependency của variants đó.
2. **Artifact resolution:** từ các component/variants đã chọn, chọn đúng artifact set và lấy các file thực sự cần cho tác vụ đang tiêu thụ chúng; đôi khi Gradle sử dụng **artifact transforms** để tạo dạng artifact được yêu cầu.

~~~text
build.gradle / settings.gradle / plugin
          |
          v
dependencies { implementation 'g:n:v' }
          |
          v
Resolvable configuration
(compileClasspath / runtimeClasspath / testRuntimeClasspath / ...)
          |
          v
GRAPH RESOLUTION
  + repository + module metadata
  + component/version selection, constraints, conflicts
  + variant selection: attributes, capabilities
  + transitive dependencies của từng variant
          |
          v
Resolved component + selected variants graph
          |
          v
ARTIFACT RESOLUTION
  + chọn artifact set phù hợp với requested attributes
  + thực hiện transform chain nếu cần và được đăng ký
  + download/đọc cached artifacts hoặc lấy outputs project
          |
          v
FileCollection / ArtifactCollection
          |
          +--> JavaCompile
          +--> Test / JavaExec
          +--> Jar, Copy, analysis tool, custom task...
~~~

Điểm đáng lưu ý:
- **Chọn component không phải chọn file.** Gradle có thể biết component/version và graph mà chưa tải tất cả JAR.
- **Chọn variant là một phần của graph resolution.** Artifact resolution có thể lựa chọn **artifact set / secondary variants** thích hợp trên node đã được chọn.
- **Cùng một module/version** có thể cung cấp artifact và dependency set khác cho các nhu cầu khác nhau.
- **Resolution có thể lazy.** Khai báo dependency không nhất thiết lập tức gọi mạng; việc resolve xảy ra khi một resolvable configuration được tiêu thụ (ví dụ compiler cần classpath).
- **Mỗi resolvable configuration là một ngữ cảnh riêng.** `compileClasspath` và `runtimeClasspath` có thể giải ra graph khác, không nên hiểu dependency graph duy nhất dùng cho mọi task.

## 3. Configuration: khai báo, yêu cầu và công bố variant

Trước khi thảo luận về component, cần biết **configuration có ba vai trò**:

| Vai trò | Ý nghĩa | Ví dụ Java |
| --- | --- | --- |
| **Declarable (dependency scope)** | Nơi bạn **khai báo** dependency/constraint | `api`, `implementation`, `compileOnly`, `runtimeOnly`, `testImplementation` |
| **Resolvable (consumer)** | Nơi Gradle **resolve** các yêu cầu thành graph và files; mang requested attributes | `compileClasspath`, `runtimeClasspath`, `testCompileClasspath`, `testRuntimeClasspath` |
| **Consumable (producer)** | Nơi project **cung cấp** variant cho project/consumer khác | `apiElements`, `runtimeElements` |

Với Gradle hiện đại, mỗi configuration nên có **một vai trò chủ đạo**. Những flags liên quan là `canBeDeclared`, `canBeResolved` và `canBeConsumed`. Gradle đã cung cấp các configuration phù hợp qua Java/Java Library plugin; không tự đặt flags lên standard configurations nếu chưa hiểu mô hình.

### 3.1. `implementation` không phải `compileClasspath`

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.apache.commons:commons-lang3:3.17.0'
    implementation 'org.slf4j:slf4j-api:2.0.13'
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.13'
}
~~~

Đoạn này là **snippet** cần `repositories { mavenCentral() }` để resolve external dependencies và một build có Java plugin phù hợp.

- `api` và `implementation` là những **địa điểm khai báo** dependencies.
- `compileClasspath` có thể yêu cầu `api` và `implementation` của chính project để **compile** mã project.
- `runtimeClasspath` cần dependencies dùng khi chạy, kể cả `runtimeOnly`.
- Khi **project khác tiêu thụ** library này, `apiElements` công bố dependency API cần cho consumer compile, còn `runtimeElements` công bố các dependency cần cho consumer runtime.
- Dependency ở `implementation` của library **không lan** vào compile classpath của consumer như API, nhưng được dùng khi consumer chạy và vì vậy xuất hiện trong runtime graph khi thích hợp.

**Không được chạy `configurations.implementation.resolve()` chỉ vì bạn khai dependency tại đó.** `implementation` mang vai trò khai báo; hãy inspect `compileClasspath` hoặc `runtimeClasspath`.

### 3.2. Mô hình quan hệ quan trọng

~~~text
Producer (:engine, java-library)
    api ----------------------+
    implementation ---------+ |
    runtimeOnly -----------+| |
                           || |
    apiElements <----------+? |  chỉ lan api dependencies sang consumer compile
    runtimeElements <--------+--+  lan runtime-required deps sang consumer runtime

Consumer (:app)
    implementation project(':engine')
          |
          +--> compileClasspath: yêu cầu java-api
          |        -> chọn :engine apiElements
          |
          +--> runtimeClasspath: yêu cầu java-runtime
                   -> chọn :engine runtimeElements
~~~

Sơ đồ biểu thị **quy tắc chung**, không phải log nội bộ chính xác của Gradle; variants còn có attributes/artifact sets và dependencies khác do plugin quyết định. Để hiểu được hoạt động thực tế, phải quan sát **requested attributes** từ consumer và **offered attributes** từ producer.

## 4. Từ dependency declaration đến yêu cầu module/project

Trong Groovy DSL, nhiều kiểu dependency đều là **yêu cầu**:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    implementation project(':engine')
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}
~~~

- **External module dependency:** `group:name:version` được tra qua các repository và metadata. Một module có thể không có đủ metadata hoặc artifact, làm resolution thất bại.
- **Project dependency:** `project(':engine')` yêu cầu sản phẩm do một project khác trong build cung cấp; Gradle cần chọn **variant** từ những consumable configurations của project đó.
- **Platform/BOM dependency:** quy định constraints hoặc alignment thay vì nhất thiết cung cấp JAR; thường viết `implementation platform('g:bom:v')`.
- **File dependency:** tham chiếu trực tiếp file, ví dụ `implementation files('libs/local.jar')`; cách này có ít metadata hơn và không tự biết transitive dependencies như module metadata. Tránh coi nó hoàn toàn tương đương một external module.
- **Constraint:** tác động đến lựa chọn version của module xuất hiện trong graph nhưng không phải luôn tự kéo module vào graph như một dependency thông thường.

### 4.1. Module khác component

| Tên | Ví dụ | Điều nó cho biết |
| --- | --- | --- |
| Module | `org.slf4j:slf4j-api` | Thư viện theo group/name, chưa xác định version |
| Dependency selector | `org.slf4j:slf4j-api:2.0.13` | Version được yêu cầu ở một cạnh graph |
| Selected component | `org.slf4j:slf4j-api:2.0.17` | Version cuối cùng được Gradle chọn sau khi xét các yêu cầu và rules (ví dụ minh họa) |
| Selected variant | `runtimeElements` hoặc variant suy ra từ metadata | Phần của component đáp ứng nhu cầu consumer |
| Resolved artifact | `slf4j-api-2.0.17.jar` | Một file thực tế được sử dụng sau artifact resolution |

Không lấy số version minh họa ở bảng làm kết quả mặc định cho bất kỳ build nào. Gradle chỉ có thể chọn version đã có/được phép theo repository metadata, version constraints, resolution strategy và trạng thái graph. Lệnh báo cáo sẽ cho **selected version thực tế**.

### 4.2. Một dependency có thể tạo nhiều cạnh graph

Giả sử:
~~~text
:app
  ├── org.example:feature-a:1.0 -> org.example:shared:1.2
  └── org.example:feature-b:1.0 -> org.example:shared:1.4
~~~

Cùng module `org.example:shared` được yêu cầu hai version. Gradle giải **version conflict** theo các quy tắc version selection; với các yêu cầu version thông thường không có ràng buộc đặc biệt, thường chọn version cao hơn tương thích. Nhưng rich versions, `strictly`, constraints, platforms, rejection/force/rules và module availability có thể thay đổi hoặc khiến resolution **thất bại**.

Khi Gradle chọn một version, graph có thể hiển thị các cạnh được chuyển hướng `1.2 -> 1.4`. **Không hiểu từng cạnh là một JAR riêng**. Một graph thường thống nhất selected component cho module trong một ngữ cảnh resolution, nhưng có những cơ chế variants/capabilities riêng cần quan sát đầy đủ.

## 5. Metadata: nguồn thông tin để dựng component và variants

Gradle cần metadata để biết component có những dependencies, variants, attributes và artifacts nào.

| Metadata | Nơi thường gặp | Khả năng mô tả |
| --- | --- | --- |
| **Gradle Module Metadata** (`.module`) | Module/project được publish có metadata Gradle | Variants, attributes, capabilities, dependencies/constraints, artifacts theo từng variant |
| **Maven POM** (`.pom`) | Maven repositories | Dependencies với Maven scopes, optional/exclusions, parent/BOM; **không biểu diễn đầy đủ variants Gradle** |
| **Ivy descriptor** (`ivy.xml`) | Ivy repositories | Configurations, artifacts/dependencies theo Ivy model |
| **Artifact-only metadata** | Repo hoặc nguồn files thiếu descriptor | Ít thông tin hơn, khó suy ra đầy đủ transitive graph và variants |

Khi có metadata chi tiết, Gradle dùng nó để xác định **những variant thực sự có sẵn**. Với một POM truyền thống, Gradle có thể **suy ra synthetic compile/runtime variants** từ Maven scopes; không có nghĩa POM đã publish `apiElements`/`runtimeElements` đầy đủ như GMM.

### 5.1. Cấu trúc component có ý nghĩa gì?

~~~text
Component: group:name:version
    |
    +-- Variant A: apiElements
    |      attributes: usage=java-api, category=library, ...
    |      dependencies: api dependencies
    |      artifacts: có thể là JAR/classes hoặc artifact set tương ứng
    |
    +-- Variant B: runtimeElements
           attributes: usage=java-runtime, category=library, ...
           dependencies: api + implementation + runtimeOnly cần thiết
           artifacts: JAR hoặc các artifact sets khác
~~~

Một variant có thể **có không, một hoặc nhiều artifact** và **có không hoặc nhiều dependency**. Ví dụ platform variant thường cung cấp constraints mà không phải JAR binary thông thường. Vì vậy đừng giả định “1 component = 1 variant = 1 JAR”.

### 5.2. Repository selection và “đến từ đâu”

Với module/version cố định, Gradle xét những repository đủ điều kiện theo **thứ tự khai báo và content filters**, tra metadata và chọn nguồn module. Khi tìm được metadata của module tại một repository, Gradle duy trì tính nhất quán nguồn cho artifacts của module đó; nó không tùy tiện lấy JAR của cùng component từ kho khác chỉ vì kho sau có file.

Với **dynamic version** như `1.+` hoặc `latest.release`, Gradle có thể phải tổng hợp metadata version từ nhiều repository để tìm version thỏa điều kiện. Đây là cơ chế khác với việc bạn đã yêu cầu một version cụ thể.

**Hai loại cache dễ nhầm:**
- **Dependency cache**: metadata, các artifact đã tải và thông tin repository/versions giúp resolution nhanh, hỗ trợ `--offline`.
- **Build cache**: output của **task execution** cacheable, chẳng hạn kết quả compile. Dependency cache không phải nơi lưu trực tiếp mọi output custom task.

Repo không chứa module/version, metadata thiếu, credentials sai hoặc repository content filters loại group đều có thể khiến resolution thất bại **trước khi** compiler chạy.

## 6. Graph resolution chi tiết: Gradle làm gì trước khi có file?

Một cách hình dung hợp lý theo logic Gradle:

1. Một task cần `:app:compileClasspath` hoặc `:app:runtimeClasspath`.
2. Gradle lấy **root dependencies** và requested **attributes** của resolvable configuration đó.
3. Với external module, Gradle xác định version/component candidate qua repository metadata; với project dependency, nó tìm project component trong build.
4. Gradle xét **version conflicts**, constraints, rejects, capabilities/conflicts và những rules liên quan.
5. Với selected component, nó xem các variants do metadata/producer công bố và chọn variant **tương thích** với consumer.
6. Nó thêm dependencies của selected variant vào graph, rồi tiếp tục xử lý chúng (có thể bao gồm module đã xuất hiện từ một nhánh khác).
7. Sau khi những cạnh và lựa chọn tương ứng được giải quyết, nó có **resolved graph**; artifact download/selection là bước tiếp theo khi cần files.

Vì mỗi variant có dependency set riêng, việc chọn variant **thay đổi chính các cạnh bắc cầu**. Đây là lý do `:app:compileClasspath` của một Java library consumer không nhất thiết thấy tất cả dependencies mà `:app:runtimeClasspath` thấy.

### 6.1. Conflict ở version khác conflict ở capability

- **Version conflict**: hai cạnh yêu cầu các version khác nhau của **cùng module** (`g:n`); Gradle cần một lựa chọn version phù hợp theo constraints/rules.
- **Capability conflict**: nhiều components/variants cung cấp **cùng một khả năng**. Có thể là hai implementation khác nhau của cùng API; Gradle cần quyết định một provider hợp lệ hoặc báo lỗi nếu không đủ thông tin lựa chọn.

Không đồng nhất capability với group/name. Một capability có danh tính riêng do producer hoặc metadata/rules khai báo. Việc hai JAR cùng chứa một package Java **không có nghĩa Gradle tự nhận ra capability conflict** nếu chúng không công bố capability tương ứng.

### 6.2. Các cơ chế can thiệp version selection

| Cơ chế | Vai trò trong graph |
| --- | --- |
| `constraints` | Đưa yêu cầu version/điều kiện vào graph cho module khi module được tham gia |
| `platform(...)` / BOM | Dùng tập constraints/alignment mà platform công bố |
| `strictly(...)` | Đặt version requirement chặt hơn, có thể làm conflict dẫn đến lỗi |
| `prefer(...)` / `require(...)` | Thể hiện version intent theo rich version DSL |
| `reject(...)` | Loại những version không được phép |
| Dependency locking | Ghi nhận và áp version đã giải, giúp build lặp lại được |
| Dependency substitution | Thay selector bằng project/module khác theo rules (nếu dùng) |
| Component metadata rules | Bổ sung/sửa metadata của component, variants, capabilities theo policy |

**Không dùng `force` như thuốc chữa mọi conflict.** Một conflict có thể phản ánh API không tương thích hoặc metadata thiếu; forced version không làm Java binary compatibility tự đúng.

## 7. Variant-aware resolution: không chọn theo tên task mà theo attributes

Hãy tưởng tượng producer `:engine` có hai variants:

~~~text
apiElements:
  org.gradle.usage = java-api
  org.gradle.category = library
  org.gradle.jvm.version = 17
  artifacts: API-facing output

runtimeElements:
  org.gradle.usage = java-runtime
  org.gradle.category = library
  org.gradle.jvm.version = 17
  artifacts: runtime-facing output
~~~

Bộ attributes thật có thể bổ sung `org.gradle.libraryelements`, `org.gradle.dependency.bundling`, target environment hoặc attributes do plugin định nghĩa. Ví dụ trên chỉ là minh họa ý nghĩa những thuộc tính chính.

Consumer `compileClasspath` thường yêu cầu `Usage = java-api`; `runtimeClasspath` thường yêu cầu `Usage = java-runtime`. Gradle xét các **variants ứng viên có attributes tương thích**, sau đó dùng quy tắc **disambiguation** nếu có nhiều ứng viên tương thích.

### 7.1. Bảng attributes cốt lõi trong JVM

| Attribute | Ví dụ giá trị | Thể hiện điều gì |
| --- | --- | --- |
| `org.gradle.usage` | `java-api`, `java-runtime` | Cần API compile hay runtime |
| `org.gradle.category` | `library`, `platform`, `documentation` | Loại component/variant |
| `org.gradle.jvm.version` | `8`, `11`, `17` | Mức JVM target/compatibility tương ứng |
| `org.gradle.libraryelements` | `jar`, `classes`, `resources` | Hình thức library/secondary artifact |
| `org.gradle.dependency.bundling` | `external`, `embedded`, `shadowed` | Dependencies là external hay được gộp vào artifact |
| Attributes của plugin khác | Android build type/flavor, native OS/architecture | Context build chuyên biệt |

### 7.2. Compatible không nhất thiết giống hệt

Một producer tạo bytecode target Java 8 thường có thể được consumer Java 17 sử dụng theo các quy tắc compatibility JVM phù hợp. Ngược lại, consumer yêu cầu Java 11 không thể mặc nhiên dùng library chỉ có variant target Java 17.

Quá trình có thể gồm:
1. **Compatibility rules** lọc variants không thể tiêu thụ.
2. **Disambiguation rules** chọn ứng viên phù hợp nhất khi còn nhiều variants.
3. Nếu không có ứng viên phù hợp, báo **No matching variant**.
4. Nếu không phân biệt được các ứng viên tương thích, có thể báo **ambiguous variants**.

Không “sửa” lỗi bằng cách đổi tên `implementation` sang `api` một cách mù quáng; phải so sánh attributes mà consumer yêu cầu với attributes producer công bố. Lệnh `outgoingVariants` và `dependencyInsight --all-variants` giúp quan sát.

### 7.3. Phân biệt feature variant với source set hoặc classifier

Feature variants/variants có thể có **capability riêng**, dependencies riêng, artifact riêng. Việc xuất bản một classifier như `sources` hoặc `javadoc` không tự tạo đầy đủ một variant-aware model tương đương. Gradle Module Metadata cho phép producer công bố nhiều thông tin hơn Maven POM thuần.

Với Android và Kotlin Multiplatform, cùng nguyên lý attributes/capabilities áp dụng nhưng tập variants thường lớn hơn (build type, flavor, target, native architecture). Đừng lấy ví dụ `apiElements`/`runtimeElements` trong Java rồi kết luận mọi plugin đều có đúng hai variants như thế.

## 8. Artifact resolution: từ resolved variants đến files

Sau khi graph đã chọn component và variant, consumer thực sự cần **files** cho task.

Ví dụ:
- `JavaCompile` cần compile classpath dưới dạng class directories/JARs phù hợp.
- `Test` hoặc `JavaExec` cần runtime classpath.
- IDE/documentation tool có thể muốn sources/Javadoc artifacts.
- Android tool cần AAR/classes/resources/native libs tùy attributes.
- Một plugin có thể yêu cầu artifact transformed sang format khác.

### 8.1. Variant selection khác artifact-set selection

Một selected variant có thể công bố **nhiều dạng artifact** (secondary variants/artifact sets). Chẳng hạn selected Java API variant của project producer có thể cấp **classes directory** thay cho JAR khi Gradle/plugin/consumer chọn cách tiêu thụ phù hợp; trong runtime có thể lấy JAR hoặc output khác tùy cơ chế và yêu cầu.

Do vậy, câu “`compileClasspath` chọn `apiElements`” **không bảo đảm** tập files compile luôn chứa file `engine.jar` cụ thể. Bạn phải xem artifact selection thực tế.

### 8.2. Artifact transforms

Nếu artifact set không đáp ứng attributes mà consumer muốn, Gradle có thể tìm một **chuỗi artifact transform đã đăng ký** để tạo dạng đích.

~~~text
Selected component / selected variant
        |
        v
Available artifact: foo.jar
        |
        | transform đã được đăng ký, phù hợp attributes
        v
Derived artifact: transformed/foo-processed.jar
        |
        v
Consumer task nhận derived artifact
~~~

**Không được hiểu transform là bộ chọn lại version/component**. Transform thường hoạt động ở tầng **artifacts** sau khi graph resolution đã quyết định node. Nó không tự tạo ra một dependency bắc cầu mới hoặc sửa phiên bản module theo ý bạn.

Nếu không có artifact set phù hợp và không có transform chain hợp lệ, artifact resolution có thể thất bại. Một custom transform cũng cần công bố input/output và attributes chính xác để Gradle biết cách dùng/caching phù hợp.

### 8.3. Những API chính khi cần kiểm tra programmatically

| API | Vai trò |
| --- | --- |
| `Configuration.getIncoming().getResolutionResult()` | Truy cập resolved graph/components/variants; không bắt buộc tải artifacts để có graph |
| `ResolvedComponentResult` | Thông tin một selected component và quan hệ graph |
| `ResolvedVariantResult` | Thông tin selected variant và attributes |
| `ArtifactView` | Tùy chỉnh artifact selection, có thể cung cấp requested attributes/lenient/filter |
| `ArtifactCollection` | Metadata/objects của những resolved artifacts |
| `FileCollection` | Tập file đầu vào thực tế của task, có dependency metadata/wiring tùy nguồn |

Các API cũ như `ResolvedConfiguration`/`ResolvedArtifact` thuộc nhánh maintenance; trong build logic mới ưu tiên `ResolutionResult`, `ArtifactView` và Provider/FileCollection APIs thích hợp.

**Một lưu ý quan trọng về lifecycle:** Đừng tự resolve mọi configuration ở top-level `build.gradle` chỉ để `println`. Việc này có thể gây network I/O sớm, chốt dependency graph quá trước thời điểm thích hợp, làm build chậm và gây lỗi an toàn khi một project resolve configuration của project khác. Hãy dùng các CLI report tasks sẵn có hoặc code task/plugin có wiring đúng.

## 9. Phòng thực hành hoàn chỉnh: bốn project Java 17, không cần kho Maven

Ví dụ này dùng **project dependencies** để quan sát variant graph mà không phải tải thư viện ngoài. Các module:

- `:contract` — định nghĩa API `Greeting`.
- `:support` — chi tiết xử lý nội bộ `Formatter`.
- `:engine` — Java library; công bố `contract` ở `api`, giấu `support` sau `implementation`.
- `:app` — Java application; chỉ khai trực tiếp `implementation project(':engine')`.

Tập file được tạo từ các project khác nhau có thể khác theo task/phiên bản Gradle (classes dirs hoặc JAR). Bài thực hành tập trung vào **graph và variants**, không giả định mọi compile classpath đều chứa JAR.

### 9.1. Cấu trúc đầy đủ

~~~text
resolution-lab/
├── settings.gradle
├── contract/
│   ├── build.gradle
│   └── src/main/java/demo/contract/Greeting.java
├── support/
│   ├── build.gradle
│   └── src/main/java/demo/support/Formatter.java
├── engine/
│   ├── build.gradle
│   └── src/main/java/demo/engine/Greeter.java
├── app/
│   ├── build.gradle
│   └── src/main/java/demo/app/App.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'resolution-lab'
include 'contract', 'support', 'engine', 'app'
~~~

Giả định Gradle Wrapper tương thích JDK 17 và máy có JDK 17 được Gradle toolchain discovery tìm thấy; nếu chưa có Wrapper, dùng Gradle đã cài để chạy `gradle wrapper` một lần rồi giữ các file Wrapper trong repository.

### 9.2. Producer API: `:contract`

**`contract/build.gradle`:**

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**`contract/src/main/java/demo/contract/Greeting.java`:**

~~~java
package demo.contract;

public interface Greeting {
    String message();
}
~~~

`:contract` có Java library variants như `apiElements`/`runtimeElements` để project khác tiêu thụ. Vì class `Greeting` là public API, việc cho consumer nhìn thấy nó khi compile có ý nghĩa.

### 9.3. Module implementation helper: `:support`

**`support/build.gradle`:**

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**`support/src/main/java/demo/support/Formatter.java`:**

~~~java
package demo.support;

public final class Formatter {
    private Formatter() {
    }

    public static String greeting(String name) {
        return "Hello " + name;
    }
}
~~~

`Formatter` là class hỗ trợ cho `:engine`. Trong ví dụ, API public của engine **không** dùng `Formatter` trong method signature; vì vậy nó không cần lan sang compile classpath của `:app`.

### 9.4. Library dùng cả `api` lẫn `implementation`: `:engine`

**`engine/build.gradle`:**

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    api project(':contract')
    implementation project(':support')
}
~~~

**`engine/src/main/java/demo/engine/Greeter.java`:**

~~~java
package demo.engine;

import demo.contract.Greeting;
import demo.support.Formatter;

public final class Greeter implements Greeting {
    @Override
    public String message() {
        return Formatter.greeting("Gradle");
    }
}
~~~

Lý do khai dependency:
- `Greeting` xuất hiện trong **public API** của `Greeter`, vì nó là interface mà `Greeter` implement. Project consumer cần `:contract` khi compile với kiểu `Greeting`; đó là dependency `api`.
- `Formatter` chỉ dùng **bên trong method body** của `Greeter`. Consumer không cần compile trực tiếp với `Formatter`; `:support` là `implementation`.
- Runtime của ứng dụng cần `Formatter` để `Greeter.message()` thực thi thành công. Vì vậy `:support` thuộc nhánh runtime graph khi consumer chạy engine.

### 9.5. Consumer: `:app`

**`app/build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':engine')
}

application {
    mainClass = 'demo.app.App'
}
~~~

**`app/src/main/java/demo/app/App.java`:**

~~~java
package demo.app;

import demo.contract.Greeting;
import demo.engine.Greeter;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        Greeting greeting = new Greeter();
        System.out.println(greeting.message());
    }
}
~~~

`app` không khai trực tiếp dependency vào `contract` hoặc `support`. Những gì có trên classpath phụ thuộc vào selected variant của `:engine` và các dependency bắc cầu của nó.

### 9.6. Chạy ứng dụng

Từ root:

~~~bash
./gradlew :app:run --quiet
~~~

**Stdout chính xác của ứng dụng Java:**

~~~text
Hello Gradle
~~~

Dòng trên do `App.main` in. Nếu Gradle download JDK toolchain hoặc có log môi trường khác, có thể có thông báo ngoài phần stdout của chương trình; ở ví dụ không có plugin bên ngoài và không khai external dependency.

Nếu `:app:compileJava` không tìm `Greeting`, kiểm tra `api project(':contract')` ở engine và source path/package. Nếu runtime báo thiếu `Formatter`, kiểm tra `implementation project(':support')` ở engine và `runtimeClasspath` của app.

## 10. Quan sát graph và selected variants của ví dụ

Các lệnh sau chỉ dùng các task báo cáo do Gradle/Java plugin cung cấp; không cần tự tạo task debug xâm nhập model.

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath

./gradlew :engine:outgoingVariants
./gradlew :engine:outgoingVariants --variant apiElements
./gradlew :engine:outgoingVariants --variant runtimeElements

./gradlew :app:resolvableConfigurations
./gradlew :app:dependencyInsight --configuration compileClasspath --dependency engine --all-variants
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency engine --all-variants
~~~

### 10.1. Dự đoán hai graph

**Graph logic `:app:compileClasspath` (sơ đồ giản lược, không phải log nguyên văn):**

~~~text
:app:compileClasspath  [consumer usage=java-api]
    |
    +-- project :engine  [selected apiElements]
             |
             +-- project :contract  [api dependency]
             
Không có project :support trong compile classpath của app.
~~~

**Graph logic `:app:runtimeClasspath`:**

~~~text
:app:runtimeClasspath  [consumer usage=java-runtime]
    |
    +-- project :engine  [selected runtimeElements]
             |
             +-- project :contract   [api dependency, cần cả runtime]
             |
             +-- project :support    [implementation dependency, cần runtime]
~~~

Các báo cáo Gradle thật có thể thêm tên configuration, deduplication markers, variant details hoặc task outputs; nội dung chính bạn cần xác minh là:
1. `compileClasspath` của app **có `contract`** nhưng **không có `support`** do engine `api`/`implementation` separation.
2. `runtimeClasspath` của app **có cả `contract` và `support`**.
3. Engine cung cấp variants có requested/offered attributes tương ứng cho hai ngữ cảnh.
4. `:app:run` thành công vì runtime có đủ implementation dependency.

### 10.2. `outgoingVariants` và `resolvableConfigurations` xem hai đầu hợp đồng

- `:engine:outgoingVariants` là góc nhìn **producer**: component `:engine` sẵn sàng cung cấp những variants nào, attributes, capabilities và artifacts gì.
- `:app:resolvableConfigurations` là góc nhìn **consumer**: configurations nào được phép resolve, requested attributes, nguồn dependency scope.
- `dependencyInsight --all-variants` giúp so sánh selected variant với những variants khác khi lệnh/Gradle version hỗ trợ đầy đủ report.

Cách này hiệu quả hơn so với việc chỉ đọc `dependencies` rồi kết luận selected artifact là loại file nào. Graph CLI thường cho thấy dependency edges, còn `outgoingVariants` cho thêm thông tin producer variants/artifacts.

### 10.3. Thử đổi `api` thành `implementation`

Trong `engine/build.gradle`, tạm đổi:

~~~groovy
dependencies {
    implementation project(':contract')
    implementation project(':support')
}
~~~

Sau đó chạy:

~~~bash
./gradlew :app:compileJava
~~~

**Kết quả được mong đợi về cơ chế:** `:app` vẫn dùng kiểu `Greeting` và `Greeter`, nhưng `Greeting` không còn được engine công bố qua API dependency. Vì thế consumer compile classpath **không còn `contract`** từ đường phụ thuộc engine; compile có thể thất bại do không tìm thấy `demo.contract.Greeting`. Đây là tình huống minh họa vì sao một public API type phải được export bằng `api`. Khôi phục `api project(':contract')` để bài thực hành chạy thành công.

Lưu ý: lỗi cụ thể của javac và file/line phụ thuộc bản Java và cách nó báo missing supertype, nên không cố định một chuỗi lỗi từng chữ.

## 11. Mở rộng: cùng cơ chế với external Maven module

Ví dụ bốn project ở trên giúp cô lập quyết định variant **không có network**. Với Maven module thật, hãy thêm **repository** và một dependency ngoài vào app.

**Chỉ là phần thêm vào `app/build.gradle`:**

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation project(':engine')
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Ở đây:
- Gradle sẽ tìm metadata cho module `org.apache.commons:commons-lang3` từ Maven Central khi configuration tương ứng được resolve.
- Component version `3.17.0` được yêu cầu; Gradle có thể chọn version khác nếu có conflict/rules khác, nhưng project thực hành không đặt những constraint như vậy.
- POM/GMM (nếu module publish) mô tả dependencies/variants hoặc cho phép Gradle suy ra compile/runtime variants; không mặc định “dòng dependency chọn trực tiếp file JAR”.
- `compileClasspath`/`runtimeClasspath` của app có thể chọn những variants hoặc inferred variants khác nhau theo usage.
- `:app:run` vẫn in `Hello Gradle` vì mã `App` không sử dụng Commons Lang; JAR được khai để học metadata/resolution, không nên giữ dependency không dùng trong dự án thật.

Dùng:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
./gradlew :app:compileJava --info
~~~

**Cảnh báo:** Cần network hoặc cache sẵn có để tải external dependency. File JAR thực tế, quá trình tải và log có thể thay đổi theo Gradle version, repository metadata và trạng thái cache. Không coi `dependencies` là lệnh bắt buộc phải tải mọi artifact; nó chủ yếu yêu cầu graph/report.

### 11.1. Project component và external module component

| Tiêu chí | `project(':engine')` | `org.apache.commons:commons-lang3:3.17.0` |
| --- | --- | --- |
| Danh tính | Project path/component identifier | Group/name/version đã chọn |
| Metadata | Model biến thể do plugin của project tạo | GMM/POM/Ivy metadata từ repository |
| Nguồn artifact | Task outputs của project trong build | Repository, dependency cache và/hoặc transform |
| Dependency bắc cầu | `api`/`implementation`/`runtimeOnly` theo chosen variant | Các dependencies được publish/suy ra theo selected variant/metadata |
| Lỗi thường gặp | No matching variant, sai plugin, sai target JVM | Could not find module, credential/repo issue, conflict, missing artifact |

Cùng “graph/variant/artifact pipeline” áp dụng cho cả hai, nhưng nguồn metadata và nơi lấy files khác nhau.

## 12. Các trường hợp variant matching gây bất ngờ

### 12.1. JVM target không tương thích

Một project library xuất bản variant target Java 17, nhưng consumer yêu cầu target Java 11:

~~~text
Consumer request: org.gradle.jvm.version = 11
Producer offers:  org.gradle.jvm.version = 17
~~~

Theo quy tắc JVM compatibility, consumer target thấp hơn không thể mặc nhiên dùng producer target cao hơn. Gradle có thể báo `No matching variant` trước khi Java compiler nhận được classpath.

**Cách kiểm tra:** xem `java.toolchain`/target compatibility của cả hai project, requested attributes của configuration và `outgoingVariants` ở producer. Không đổi tùy tiện `sourceCompatibility` chỉ để tắt lỗi nếu bytecode/API thật sự cần Java 17.

### 12.2. Sai category

Một consumer yêu cầu platform variant (`org.gradle.category=platform`) nhưng producer chỉ cung cấp library binary variant. Gradle có thể không tìm ra variant phù hợp. Cần phân biệt:

~~~groovy
dependencies {
    implementation 'com.example:library:1.0'
    implementation platform('com.example:platform-bom:1.0')
}
~~~

Đây là **snippet minh họa**, dùng tọa độ giả định: `platform(...)` thể hiện nhu cầu tiêu thụ **platform constraints**, không phải JAR library. Cấu hình cần repository/module tồn tại để chạy được.

### 12.3. Capability conflict

Hai modules có thể công bố cùng capability `com.example:logging-provider`. Nếu graph đồng thời yêu cầu hai implementations mà rules không giải quyết được, Gradle có thể báo conflict. Phải chọn một implementation hoặc cấu hình capability resolution phù hợp; không thể chữa bằng cách xóa ngẫu nhiên một JAR khỏi `runtimeClasspath` sau khi graph đã resolve.

### 12.4. Ambiguous variants

Một plugin tự định nghĩa hai consumable configurations cùng attributes mà không có quy tắc disambiguation. Consumer có thể nhận lỗi không chọn được một variant duy nhất. **Tên variant khác nhau không tự đủ** để quyết định. Cần công bố attributes/capabilities rõ ràng và chỉ những variants có ý nghĩa với consumer.

### 12.5. Artifact transform không có

Consumer yêu cầu một artifact type khác dạng producer có sẵn, nhưng không có transform được đăng ký để đi từ nguồn đến đích. Khi đó artifact selection có thể thất bại **sau** khi component/variant đã được chọn. Đừng nhầm thông báo này với “không tìm thấy module trên Maven Central”.

## 13. Trình tự chẩn đoán khi Gradle không giải ra classpath mong muốn

### 13.1. Bộ lệnh hữu ích

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency engine --all-variants
./gradlew :engine:outgoingVariants
./gradlew :app:resolvableConfigurations
./gradlew :app:compileJava --info
./gradlew :app:run --info
~~~

Nếu đang xử lý external dependencies:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath --offline
./gradlew :app:dependencies --configuration runtimeClasspath --refresh-dependencies
~~~

- `--offline` chỉ dùng cached metadata/artifacts mà Gradle có thể dùng; nếu thiếu dữ liệu cần thiết, lệnh có thể thất bại. Nó **không** bỏ qua dependency resolution.
- `--refresh-dependencies` yêu cầu kiểm tra lại trạng thái resolution/metadata theo quy tắc Gradle; nó không vô hiệu hóa constraints, không mở khóa exclusive repository policy và không nhất thiết tải lại bytes không thay đổi.
- `--info` cung cấp thêm giải thích resolution/task; chỉ dùng `--debug` có kiểm soát vì log có thể chứa URL nội bộ hoặc dữ liệu nhạy cảm.
- `dependencyInsight` chỉ báo về **một dependency trong một configuration**; xem đúng scope thay vì kết luận từ `compileClasspath` rồi suy ra `runtimeClasspath`.
- `outgoingVariants` xem producer; nó không tự đảm bảo một consumer bất kỳ có thể tiêu thụ variant đó.

### 13.2. Bảng từ triệu chứng đến pha lỗi

| Triệu chứng | Pha nên điều tra trước | Kiểm tra |
| --- | --- | --- |
| `Could not find g:n:v` | Repository/metadata lookup | Tọa độ, repositories, content filters, credentials, metadata source |
| Version được chọn khác version khai | Graph/version selection | `dependencyInsight`, constraints, platforms, conflicts, locking |
| `No matching variant` | Graph/variant selection | Consumer attributes so với producer attributes, JVM version, category, usage |
| `Cannot choose between variants` | Graph/variant disambiguation | Hai biến thể có attributes/capabilities mơ hồ |
| Capability conflict | Graph/component implementation selection | Những component công bố cùng capability và resolution rules |
| Graph đúng nhưng thiếu JAR/classes | Artifact selection / task input wiring | Selected variant, artifacts, artifact transforms, publication |
| `compileClasspath` không có implementation dependency của library khác | **Có thể là hành vi đúng** | Phân biệt `api` và `implementation` của producer |
| `runtimeClasspath` có nhiều modules hơn compile classpath | **Có thể là hành vi đúng** | `runtimeElements` và runtime-only dependencies |
| `NoClassDefFoundError` lúc chạy | Runtime graph hoặc packaging | `runtimeClasspath`, `runtimeOnly`, thiếu library, shadow/classloader |
| Metadata có module nhưng artifact tải lỗi | Artifact resolution/repository | Repository source, artifact existence, checksum, cache |
| Build chạy local nhưng CI thiếu dependency | Repository/cache/toolchain | `mavenLocal`, offline mode, credentials, platform compatibility |

### 13.3. “Debug theo thứ tự”, không thay đổi 5 thứ cùng lúc

1. **Xác định consumer configuration đang lỗi**: `compileClasspath`, `testRuntimeClasspath`, Android `debugRuntimeClasspath`...
2. **Kiểm tra declaration**: module/project selector, version, `api`/`implementation`/`runtimeOnly`, constraints.
3. **Nếu external module:** kiểm tra repository, metadata và version được chọn.
4. **Nếu variant error:** dùng `outgoingVariants` ở producer và report attributes ở consumer.
5. **Nếu artifact error:** xác định graph đã chọn component/variant chưa, loại files nào task muốn, có artifact set/transform không.
6. **Nếu runtime error:** kiểm tra runtime graph/packaging; đừng chỉ xem compile.
7. **Kiểm tra dependencyInsight** về version/conflicts và thử build với môi trường sạch/locked dependencies khi cần tái lập.
8. **Sửa đúng lớp lỗi**. Không vội tắt transitive dependencies, ép version, thêm `mavenLocal()`, xóa cache hay đổi plugin chỉ để tạm hết lỗi.

## 14. Tái lập và bảo mật của resolution

Khi team dùng CI hoặc publish library, một “build chạy được trên laptop” chưa đủ. Resolution cần nhất quán:

- **Version locking:** giúp cố định selected versions của dynamic/transitive dependencies theo build policy.
- **Dependency verification:** xác minh hash/signatures artifacts/metadata được tải theo cơ chế Gradle hỗ trợ; repository tin cậy không có nghĩa mọi artifact tự an toàn.
- **Repository control:** quản lý nguồn được phép bằng settings, content filters và exclusive content khi phù hợp, tránh dependency confusion.
- **Gradle Module Metadata:** publish thông tin variant/capability phong phú khi consumers cần phân biệt API/runtime hoặc target.
- **Không lạm dụng dynamic versions** như `1.+` hoặc `latest.release` trong release builds nếu chưa có locking.
- **Không tùy tiện dùng `mavenLocal()` trong CI** vì module có thể khác giữa máy.
- **Không coi artifact classifier là đủ** để đại diện cho variant model.
- **Đọc graph bằng APIs/report tasks** thay vì hardcode đường dẫn bên trong `~/.gradle/caches`.

Dù có build cache, Gradle vẫn cần xác định input dependency graph và artifacts đúng để tính task inputs. Artifact được tải từ dependency cache và output lấy từ task build cache là **hai cơ chế khác nhau**.

## 15. Bài tập có đáp án

### Bài 1 — Nhận diện tầng

`implementation 'g:n:1.0'` là gì: component, variant hay artifact?

**Đáp án:** Đó là **dependency request** được khai trên một configuration. Sau resolution mới có selected component/version, selected variant và các artifact files tương ứng.

### Bài 2 — Phân loại configuration

Trong Java library, `implementation`, `compileClasspath` và `runtimeElements` đóng vai trò nào?

**Đáp án:** `implementation` là declarable dependency scope; `compileClasspath` là resolvable consumer configuration; `runtimeElements` là consumable producer variant.

### Bài 3 — API và implementation

Trong `:engine`, `api project(':contract')` và `implementation project(':support')`. Project `:app` chỉ khai `implementation project(':engine')`. `:app:compileClasspath` có hai project bắc cầu nào?

**Đáp án:** `:contract` xuất hiện vì engine công bố API dependency; `:support` **không** cần trên compile classpath của app. Runtime classpath của app có cả hai khi engine cần support.

### Bài 4 — Chọn variant

Vì sao cùng component `:engine` nhưng app compile thường dùng `apiElements`, app runtime thường dùng `runtimeElements`?

**Đáp án:** Hai **resolvable configurations** yêu cầu usage attributes khác nhau, nên Gradle chọn variant producer tương thích. Mỗi variant công bố dependencies/artifact sets khác nhau.

### Bài 5 — Metadata

Maven POM có luôn mô tả chính xác Gradle variants, capabilities và attributes không?

**Đáp án:** Không. Maven POM biểu diễn Maven dependency model; Gradle có thể suy ra compile/runtime variants. GMM (`.module`) mô tả variant-aware metadata chi tiết hơn.

### Bài 6 — Component khác artifact

Gradle chọn đúng `org.example:tool:2.0` nhưng task báo không tìm được file input. Điều đó mâu thuẫn không?

**Đáp án:** Không. Component selection thuộc graph resolution, còn artifact selection/download/transform thuộc artifact resolution. Graph đúng chưa bảo đảm file mong muốn có sẵn.

### Bài 7 — Version conflict

Module A yêu cầu `common:1.2`, module B yêu cầu `common:1.4`. Có nhất thiết tải hai JAR riêng không?

**Đáp án:** Không. Gradle giải version conflict theo graph/configuration, thường chọn một version phù hợp thay vì mỗi cạnh tạo một JAR. Constraints/strict/force có thể thay đổi kết quả hoặc gây lỗi.

### Bài 8 — JVM target

App yêu cầu Java 11, library chỉ công bố variant Java 17. Có thể lỗi ở đâu?

**Đáp án:** Variant compatibility trong graph resolution. Compiler của app không nhất thiết được chạy để phát hiện lỗi này; nên xem `outgoingVariants` và requested JVM attributes.

### Bài 9 — Artifact transform

Một component có JAR, consumer cần processed artifact type, Gradle có transform được đăng ký. Điều gì xảy ra?

**Đáp án:** Sau khi chọn graph/variant, Gradle có thể chọn transform chain để biến artifact có sẵn thành dạng consumer cần. Transform không tự quyết định lại version/component.

### Bài 10 — Thực hành

1. Chạy project phần 9 và dự đoán stdout.
2. Chạy `:app:dependencies` cho compile và runtime, vẽ hai graph.
3. Chạy `:engine:outgoingVariants` để xác định API/runtime variants.
4. Đổi `api project(':contract')` thành `implementation`, quan sát lỗi compile app và giải thích.
5. Khôi phục `api`, chạy lại app.
6. Thêm external module từ Maven Central vào `:app` rồi dùng `dependencyInsight` để kiểm tra version/selection.

**Đạt bài học** khi bạn có thể trả lời liên tục bốn câu: **(1) khai báo gì, (2) selected component nào và vì sao, (3) selected variant nào theo attributes/capabilities, (4) những artifact files cuối cùng nào được consumer nhận?**

## 16. Tài liệu chính thức

- [Gradle — Dependency Resolution](https://docs.gradle.org/current/userguide/dependency_resolution_basics.html): tổng quan graph resolution và artifact resolution.
- [Gradle — Graph Resolution](https://docs.gradle.org/current/userguide/graph_resolution.html): component selection, metadata, variant selection, conflicts và graph traversal.
- [Gradle — Variant Selection and Attribute Matching](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): compatibility, disambiguation, attributes và variant diagnostics.
- [Gradle — Artifact Resolution](https://docs.gradle.org/current/userguide/artifact_resolution.html): artifact sets, files và APIs.
- [Gradle — Artifact Views](https://docs.gradle.org/current/userguide/artifact_views.html): artifact selection nâng cao và alternative variants.
- [Gradle — Artifact Transforms](https://docs.gradle.org/current/userguide/artifact_transforms.html): chuyển dạng artifacts theo attributes.
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): declarable/resolvable/consumable roles.
- [Gradle — Metadata Formats](https://docs.gradle.org/current/userguide/supported_metadata_formats.html): POM, Ivy và Gradle Module Metadata.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight` và các flags.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`, `implementation` và API/runtime variants.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): cố định selected dependency versions.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): kiểm tra integrity/nguồn dependency.
