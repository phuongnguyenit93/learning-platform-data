# Đọc báo cáo outgoingVariants và resolvableConfigurations trong Gradle

## 1. Mục tiêu bài học

Gradle không chỉ chọn “một file JAR theo tên”. Với dependency hiện đại, Gradle lựa chọn **variant** của một component dựa trên yêu cầu của bên tiêu thụ và thông tin do bên cung cấp công bố. Khi project `:app` phụ thuộc project `:lib`, bên `:app` có thể cần dạng API để **compile** và dạng runtime để **chạy**. Project `:lib` có thể công bố những biến thể khác nhau cho các nhu cầu ấy.

Hai reporting tasks rất hữu ích:

- **`outgoingVariants`:** Nhìn từ **producer** — project này đang **cung cấp** những variant nào, với capabilities, attributes và artifacts gì?
- **`resolvableConfigurations`:** Nhìn từ **consumer** — project này đang có những configuration **được phép resolve** nào, chúng **yêu cầu attributes** gì và kế thừa những configuration nào?

Hai báo cáo đặt cạnh nhau giúp trả lời câu hỏi: “Vì sao Gradle chọn `apiElements` khi compile, nhưng `runtimeElements` khi chạy?” hoặc “Vì sao project dependency báo *No matching variant* / *Cannot choose between variants*?”.

Kết thúc bài, bạn có thể:

1. Chạy hai báo cáo ở đúng project/subproject bằng Gradle Wrapper.
2. Giải thích các mục `Variant`, `Configuration`, `Capabilities`, `Attributes`, `Artifacts`, `Secondary Variants` và `Extended Configurations`.
3. Hiểu các cặp attribute thường gặp như `org.gradle.usage=java-api`/`java-runtime`, `org.gradle.libraryelements=jar`/`classes` và `org.gradle.jvm.version`.
4. Sử dụng `--variant`, `--configuration`, `--all`, `--recursive` đúng report.
5. Phân biệt variant có thể **được công bố** với configuration có thể **được resolve**.
6. Biết rằng tên configuration **không phải thuật toán chọn variant**; Gradle chủ yếu dựa trên attributes, capabilities và compatibility rules.
7. Chạy ví dụ Java 17 gồm `:lib` và `:app`, xem output đáng tin và đối chiếu hai báo cáo.
8. Kết hợp `dependencyInsight` và `dependencies` để chẩn đoán lựa chọn thực tế sau khi hai báo cáo đã cho thấy các khả năng và yêu cầu.

> **Phạm vi:** Bài giải thích cách **đọc và sử dụng hai báo cáo** trong Gradle, không yêu cầu tự viết thuật toán variant selection hoặc phát hành một plugin Maven. Các ví dụ tập trung Java 17 và Kotlin DSL; có bảng đối chiếu Groovy DSL.

## 2. Mô hình nền tảng: producer, consumer, variant

Một component (module/project) có thể cung cấp nhiều variant. Mỗi variant mô tả một cách sử dụng component và có thể gắn với artifacts và dependencies khác nhau.

~~~text
                  PROJECT :lib (PRODUCER)
          +--------------------------------------+
          | apiElements       runtimeElements    |
          | usage=java-api     usage=java-runtime|
          | artifact=JAR      artifact=JAR       |
          | attributes, capabilities, deps       |
          +------------------+-------------------+
                             |
                variant-aware resolution
                             |
          +------------------+-------------------+
          | PROJECT :app (CONSUMER)              |
          | compileClasspath   runtimeClasspath  |
          | wants java-api     wants java-runtime |
          +--------------------------------------+
~~~

Các thành phần cốt lõi:

| Thuật ngữ | Cách hiểu |
| --- | --- |
| **Producer** | Project/module đang **công bố** thứ để người khác sử dụng, ví dụ `:lib` |
| **Consumer** | Project/configuration đang **yêu cầu** dependency, ví dụ `:app:compileClasspath` |
| **Component** | Thực thể có thể chứa nhiều variants; ví dụ project `:lib` hoặc module `group:name:version` |
| **Variant** | Một lựa chọn sử dụng component, có attributes, capabilities, artifacts và dependencies |
| **Attribute** | Cặp khóa–giá trị biểu đạt đặc tính/yêu cầu, ví dụ `org.gradle.usage=java-api` |
| **Capability** | Khả năng mà component/variant cung cấp; giúp xác định lựa chọn thay thế hoặc xung đột |
| **Artifact** | File/thư mục đầu ra được variant cung cấp, ví dụ JAR hoặc thư mục class |
| **Configuration** | Đơn vị Gradle quản lý dependency declarations, resolution hoặc variants, tùy vai trò |

**Quan trọng:** `apiElements` và `runtimeElements` là các tên variant/configuration tiêu biểu của Java Library plugin. Tên này chủ yếu giúp đọc và debug. **Tên variant tự nó không phải điều kiện quyết định lựa chọn**. Gradle so sánh các attributes được yêu cầu với attributes mà producer cung cấp, áp dụng compatibility/disambiguation rules và các quy tắc liên quan.

### 2.1. API và runtime không nhất thiết có cùng dependencies

Trong thư viện Java, dependency khai báo ở `api` thường là phần cần thiết cho API compile của bên sử dụng; dependency chỉ nằm ở `implementation` là chi tiết nội bộ compile của thư viện và có thể xuất hiện trong runtime variant.

Ví dụ minh họa cú pháp (tọa độ giả, **không dùng trực tiếp để chạy**):

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api("example:public-api:1.0")
    implementation("example:internal-engine:1.0")
}
~~~

Consumer compile và runtime có thể nhận graph/artifacts khác nhau. Đừng suy luận chỉ từ việc `:lib` tạo một JAR rằng dependency API và runtime của nó phải giống hệt nhau.

## 3. Trước hết, phân biệt ba vai trò configuration

Gradle hiện đại khuyến nghị tách ba trách nhiệm:

| Vai trò | Cờ đặc trưng | Công dụng |
| --- | --- | --- |
| **Declarable / dependency scope** | `canBeDeclared=true` | Nơi **khai báo** dependency, như `implementation`, `api`, `runtimeOnly` |
| **Resolvable** | `canBeResolved=true` | Nơi **giải quyết** graph để nhận dependencies/artifacts như `compileClasspath`, `runtimeClasspath` |
| **Consumable** | `canBeConsumed=true` | Nơi **công bố** một variant cho project/module khác như `apiElements`, `runtimeElements` |

Các cờ nói trên là đặc điểm của từng configuration; trong mô hình được khuyến nghị, một configuration nên có một vai trò rõ ràng. Những configuration legacy có thể kiêm vai trò và xuất hiện khác trong report, đặc biệt khi dùng `--all`.

Trong Java plugin:

~~~text
KHAI BÁO:             RESOLVE:                 CÔNG BỐ:
implementation -----> compileClasspath         apiElements
runtimeOnly --------> runtimeClasspath         runtimeElements
compileOnly --------> compileClasspath         (do Java Library plugin tạo)
~~~

Mũi tên chỉ mang tính minh họa các nguồn dependency declaration; `compileClasspath` thực tế kế thừa `compileOnly` và `implementation`, còn `runtimeClasspath` kế thừa `runtimeOnly` và `implementation`. `extendsFrom` giúp tái sử dụng dependency-related declarations **không biến declarable scope thành resolvable** và không tự sao chép attributes.

Điểm nhiều người mới học nhầm:

- `implementation` không phải tên task và không phải chỗ nên gọi `.files` để resolve.
- `compileClasspath` là *resolvable configuration* của consumer, không phải biến thể JAR được công bố.
- `apiElements` là *consumable configuration/variant* của producer; không nên cố resolve nó như một classpath thông thường.
- `outgoingVariants` **không** dùng để in full resolved dependency tree.
- `resolvableConfigurations` **không** tự chứng minh phiên bản module cuối cùng đã được chọn.

## 4. outgoingVariants là báo cáo gì?

`outgoingVariants` là reporting task hiển thị những **variants mà project có thể đưa cho consumer lựa chọn**. Với `java-library`, bạn thường thấy `apiElements` và `runtimeElements`; tùy plugin/Gradle version có thể có thêm `mainSourceElements` hoặc các variant khác.

Lệnh cơ bản từ root của một build có project `:lib`:

~~~bash
./gradlew :lib:outgoingVariants
~~~

Windows:

~~~bat
gradlew.bat :lib:outgoingVariants
~~~

Nếu bạn dùng Gradle đã cài thay vì Wrapper:

~~~bash
gradle :lib:outgoingVariants
~~~

**Lưu ý:** Câu lệnh `:lib:outgoingVariants` chạy báo cáo của **project `:lib`**, không phải project root hoặc consumer `:app`. Nếu project chỉ có một module, thường chạy `gradle outgoingVariants` ngay tại root.

### 4.1. Cấu trúc tiêu biểu

Ví dụ định dạng đầu ra rút gọn của một Java library:

~~~text
--------------------------------------------------
Variant apiElements
--------------------------------------------------
API elements for the 'main' feature.

Capabilities
    - demo.report:lib:1.0 (default capability)

Attributes
    - org.gradle.category            = library
    - org.gradle.dependency.bundling = external
    - org.gradle.jvm.version         = 17
    - org.gradle.libraryelements     = jar
    - org.gradle.usage               = java-api

Artifacts
    - build/libs/lib-1.0.jar (artifactType = jar)

--------------------------------------------------
Variant runtimeElements
--------------------------------------------------
Runtime elements for the 'main' feature.

Capabilities
    - demo.report:lib:1.0 (default capability)

Attributes
    - org.gradle.category            = library
    - org.gradle.dependency.bundling = external
    - org.gradle.jvm.version         = 17
    - org.gradle.libraryelements     = jar
    - org.gradle.usage               = java-runtime

Artifacts
    - build/libs/lib-1.0.jar (artifactType = jar)
~~~

Đây là **trích đoạn minh họa đã rút gọn**, không cam kết stdout nguyên văn: tên project, group/version, JVM target, đường dẫn và các variant phụ thuộc cấu hình, plugin và phiên bản Gradle. Trong ví dụ chạy được ở mục 10, ta sẽ dùng `group="demo.report"`, `version="1.0"` và Java 17 để dễ đối chiếu.

### 4.2. Dòng `Variant apiElements`

Ý nghĩa: producer có một variant dành cho **API**. Consumer muốn compile Java code thường yêu cầu `org.gradle.usage=java-api`. Variant mang Usage phù hợp thường được Gradle cân nhắc cho compile graph.

**Không nhầm:** tên `apiElements` là định danh hữu ích cho report; lý do chính để match là tập attributes tương thích, **không** phải Gradle so sánh chuỗi `"apiElements"` với `"compileClasspath"`.

### 4.3. Dòng `Variant runtimeElements`

Ý nghĩa: producer công bố một variant cho **runtime**. Consumer resolve runtimeClasspath thường yêu cầu `org.gradle.usage=java-runtime`; Gradle chọn variant phù hợp với yêu cầu này.

Có thể có cùng một artifact JAR ở cả hai variants, nhưng **dependencies truyền tới consumer** hoặc metadata variant khác nhau. Việc hai dòng `Artifacts` trỏ cùng file **không** có nghĩa api/runtime variants không có khác biệt.

### 4.4. Capabilities

Ví dụ:

~~~text
Capabilities
    - demo.report:lib:1.0 (default capability)
~~~

Capability mặc định thường mang tọa độ `group:name:version` của component. Với library được cấu hình `group="demo.report"`, tên project `lib` và version `1.0`, kết quả là `demo.report:lib:1.0`.

Capability không phải một file JAR, không phải một class Java và cũng không phải property `canBeConsumed`. Nó mô tả **khả năng** một variant cung cấp. Nếu nhiều components/variants cung cấp **cùng capability** trong một graph không tương thích, Gradle có thể báo conflict và cần một cơ chế selection có chủ đích.

Một variant có thể cung cấp capabilities tùy biến do plugin/build logic định nghĩa. `outgoingVariants` giúp bạn biết bên producer **quảng bá capability nào**, thay vì phỏng đoán từ tên artifact.

### 4.5. Attributes

Ví dụ:

~~~text
Attributes
    - org.gradle.category            = library
    - org.gradle.dependency.bundling = external
    - org.gradle.jvm.version         = 17
    - org.gradle.libraryelements     = jar
    - org.gradle.usage               = java-api
~~~

Nên đọc từng dòng như:

- `org.gradle.category=library`: variant thuộc loại thư viện, khác các dạng tài liệu/verification.
- `org.gradle.dependency.bundling=external`: mô tả cách variant đóng gói dependencies; không có nghĩa JAR đã chứa tất cả dependencies bên trong.
- `org.gradle.jvm.version=17`: JVM target/minimum compatible version được producer công bố; phải so với yêu cầu JVM của consumer.
- `org.gradle.libraryelements=jar`: variant/artifact chính dùng dạng JAR.
- `org.gradle.usage=java-api`: variant dành cho việc sử dụng như API của Java.
- `org.gradle.usage=java-runtime` ở runtimeElements: variant dành cho chạy.

Các attributes thuộc metadata lựa chọn variant, **không phải bằng chứng** rằng Java source đã thực sự được biên dịch thành công. Một báo cáo có thể liệt kê artifact dự kiến trước khi task `jar` được thực thi.

### 4.6. Artifacts

~~~text
Artifacts
    - build/libs/lib-1.0.jar (artifactType = jar)
~~~

Đây là artifact producer công bố cho variant. Report liệt kê đường dẫn/artifact dự kiến; **không nhất thiết tạo JAR ngay khi bạn chạy báo cáo**. Nếu muốn xác minh artifact tồn tại và đọc được, hãy chạy task `jar`/`build` hoặc tác vụ tiêu thụ nó, rồi kiểm tra file.

## 5. Secondary Variants — phần rất dễ đọc sai

Trong Java plugin, ngoài variant chính như `apiElements`, report có thể hiển thị:

~~~text
Secondary Variants (*)

    --------------------------------------------------
    Secondary Variant classes
    --------------------------------------------------
    Directories containing compiled class files for main.

    Attributes
        - org.gradle.category            = library
        - org.gradle.libraryelements     = classes
        - org.gradle.usage               = java-api

    Artifacts
        - build/classes/java/main (artifactType = java-classes-directory)
~~~

Đây là **trích đoạn rút gọn**: report thật có thể in thêm attributes. Các secondary variants hay *secondary artifact sets* cung cấp thêm **kiểu artifact** cho variant đã được chọn. Ví dụ consumer cần class files có thể dùng thư mục `build/classes/java/main` thay vì đợi/đọc JAR.

**Hai bước cần phân biệt:**

1. **Dependency graph variant selection:** chọn thành phần API/runtime phù hợp dựa trên requirements; dependencies của variant chính đóng vai trò trong graph.
2. **Artifact selection:** chọn artifact set phù hợp (JAR, classes directory, resources directory...), có thể qua secondary variants/artifact transforms.

Secondary variant **không tạo một graph dependency độc lập** như một variant chính. Vì vậy đừng suy ra “producer có classes secondary variant nên có thêm một module dependency tên classes”.

Bạn cũng có thể thấy secondary variant `resources` của `runtimeElements`, gắn với `build/resources/main`. Điều này giúp Gradle cấp resource directories khi thích hợp.

### 5.1. Dấu `(*)` trong `Secondary Variants (*)`

Dấu sao ở heading này thuộc cách report chú giải secondary variants, **không** phải marker `(*)` dùng trong `gradle dependencies` để rút gọn subtree dependency lặp. Các report khác nhau có quy ước chú thích khác nhau; hãy đọc theo tiêu đề và ngữ cảnh.

### 5.2. Điều dễ gây bối rối: producer jar, consumer classes

`outgoingVariants` có thể cho `apiElements`:

~~~text
org.gradle.libraryelements = jar
~~~

nhưng `resolvableConfigurations --configuration compileClasspath` lại hiển thị:

~~~text
org.gradle.libraryelements = classes
~~~

Đó **không tự động là lỗi không khớp variant**. Gradle có quy tắc tương thích và bước lựa chọn artifact; Java plugin có thể dùng secondary `classes` artifact set phục vụ compile nhanh hơn. Hãy xem thêm `dependencyInsight` và bản thân task compile, không kết luận “jar và classes khác nhau nên chắc chắn No matching variant”.

## 6. Các tùy chọn CLI của outgoingVariants

| Lệnh | Kết quả |
| --- | --- |
| `./gradlew :lib:outgoingVariants` | Liệt kê các outgoing variants được report mặc định |
| `./gradlew :lib:outgoingVariants --variant apiElements` | Chỉ xem variant `apiElements` |
| `./gradlew :lib:outgoingVariants --variant runtimeElements` | Chỉ xem variant `runtimeElements` |
| `./gradlew :lib:outgoingVariants --all` | Bao gồm thêm legacy/deprecated/attributeless configurations |
| `./gradlew :lib:outgoingVariants --no-all` | Loại phần mở rộng `--all` khỏi report |

Ví dụ:

~~~bash
./gradlew :lib:outgoingVariants --variant apiElements
./gradlew :lib:outgoingVariants --variant runtimeElements
./gradlew :lib:outgoingVariants --all
~~~

**Lưu ý:** `--variant` chọn một **variant để hiển thị**, không ép consumer thực sự resolve variant đó. Để giải quyết variant selection, cần xem consumer requirements, attributes và `dependencyInsight`.

### 6.1. Dùng `--all` khi nào?

Ở các bản Gradle hiện đại, đặc biệt từ thay đổi trong dòng Gradle 9.x, report mặc định có thể ẩn những configuration **không có attributes**, vì chúng không tham gia được vào lựa chọn variant-aware. `--all` cho thấy thông tin legacy/deprecated và những entry không attributes được ghi dấu `(n)`.

Nếu một custom configuration bạn vừa tạo **không xuất hiện**, đừng vội kết luận plugin không tạo nó. Chạy:

~~~bash
./gradlew :lib:outgoingVariants --all
~~~

Rồi tìm entry bị đánh dấu `(n)`. Nhưng việc xuất hiện trong `--all` **không bảo đảm** nó có thể được chọn bằng variant-aware dependency resolution. Entry không có attributes thường không phải một public variant đúng nghĩa; cần xác định vai trò và attributes của nó trước khi định dùng.

### 6.2. Một số marker khác

- `(n)`: entry không có attributes, không thể được chọn qua variant-aware matching thông thường.
- `(i)`: tùy bản Gradle, có thể đánh dấu entry/incubating feature.
- Thông tin legacy/deprecated có thể được bổ sung bằng `--all`.
- `Secondary Variants (*)` là nhóm artifact variants phụ trợ, không phải một loạt task mới.

Không coi marker là trạng thái lỗi nếu thiếu thông điệp lỗi. Đọc chính mô tả, attributes, capabilities và đường dẫn artifact.

## 7. resolvableConfigurations là báo cáo gì?

`resolvableConfigurations` cho biết các **configurations mà project có thể resolve** để nhận dependencies. Nếu `outgoingVariants` mô tả “tôi có thể cung cấp gì?”, báo cáo này mô tả “tôi cần gì khi resolve?”.

Với Java/Application plugin, các tên phổ biến là:

- `compileClasspath` — các dependency được resolve cho compile mã Java chính.
- `runtimeClasspath` — các dependency được resolve khi chạy ứng dụng.
- `testCompileClasspath` — compile test.
- `testRuntimeClasspath` — chạy test.
- `annotationProcessor` — classpath riêng cho annotation processors.
- Những configuration tùy chỉnh do plugin/project tạo.

Từ root multi-project build:

~~~bash
./gradlew :app:resolvableConfigurations
~~~

Lệnh này nói về **consumer `:app`**. Nếu bạn chạy `:lib:resolvableConfigurations`, bạn đang xem **điều `:lib` cần khi consume dependency**, không phải những variants mà `:lib` công bố cho app.

### 7.1. Ví dụ một mục của report

~~~text
--------------------------------------------------
Configuration compileClasspath
--------------------------------------------------
Description = Compile classpath for source set 'main'.

Attributes
    - org.gradle.category            = library
    - org.gradle.dependency.bundling = external
    - org.gradle.jvm.environment     = standard-jvm
    - org.gradle.jvm.version         = 17
    - org.gradle.libraryelements     = classes
    - org.gradle.usage               = java-api

Extended Configurations
    - compileOnly
    - implementation
~~~

Đây là **trích đoạn minh họa rút gọn**, phù hợp với Java 17 toolchain trong ví dụ của bài; không cam kết thứ tự dòng/attributes ở mọi Gradle version/plugin.

Ý nghĩa:

- `Configuration compileClasspath` là **resolvable configuration**.
- `Description` là mô tả do plugin cấu hình.
- `Attributes` biểu đạt yêu cầu khi compile: Java API, JVM version, library elements phù hợp.
- `Extended Configurations` liệt kê những **dependency scopes mà configuration này kế thừa** thông qua `extendsFrom`.

**Chú ý:** `compileOnly` và `implementation` trong `Extended Configurations` là những scopes khai báo dependency. Chúng **không** phải hai project được build, không phải hai artifact riêng và cũng không phải variants đã được chọn.

### 7.2. Runtime classpath

~~~text
--------------------------------------------------
Configuration runtimeClasspath
--------------------------------------------------
Description = Runtime classpath of source set 'main'.

Attributes
    - org.gradle.category            = library
    - org.gradle.dependency.bundling = external
    - org.gradle.jvm.environment     = standard-jvm
    - org.gradle.jvm.version         = 17
    - org.gradle.libraryelements     = jar
    - org.gradle.usage               = java-runtime

Extended Configurations
    - implementation
    - runtimeOnly
~~~

Phần khác biệt dễ thấy so với `compileClasspath`:

- `org.gradle.usage=java-runtime` thay vì `java-api`.
- `org.gradle.libraryelements=jar` thay vì `classes` (tùy plugin/Gradle).
- Kế thừa `runtimeOnly` thay vì `compileOnly`.

Do đó cùng một direct project dependency `implementation(project(":lib"))` vẫn có thể được resolve theo **variant khác nhau** trong compile và runtime. Consumer không cần viết hai project dependency chỉ để “yêu cầu lib API rồi lib runtime”.

### 7.3. Extended Configurations có ý nghĩa gì?

Quan hệ:

~~~text
compileOnly       implementation
     \             /
      \           /
       compileClasspath

runtimeOnly       implementation
     \             /
      \           /
       runtimeClasspath
~~~

Các mũi tên có nghĩa `compileClasspath.extendsFrom(compileOnly, implementation)` và `runtimeClasspath.extendsFrom(runtimeOnly, implementation)` ở mức mô hình. Nhờ đó dependency declarations trong `implementation` tham gia cả hai graph, còn `compileOnly` hoặc `runtimeOnly` chỉ áp dụng cho phạm vi thích hợp.

**`extendsFrom` không tự sao chép attributes.** Resolvable configuration có attributes riêng để chọn variant. Đừng diễn giải phần `Extended Configurations` như thể nó là danh sách attributes được thừa hưởng.

### 7.4. Compatibility và disambiguation rules

Báo cáo có thể có phần tóm tắt những attributes chịu tác động bởi **compatibility rules** hoặc **disambiguation rules**. Ý nghĩa:

- **Compatibility rule** quyết định hai giá trị attribute khác nhau có thể xem là tương thích không.
- **Disambiguation rule** giúp Gradle chọn giữa những ứng viên còn tương thích.
- Một số rules do Java ecosystem/plugin cung cấp, một số do plugin/build logic tự định nghĩa.

Không cần thuộc thuật toán cụ thể để bắt đầu. Khi thấy Java target 17 và consumer target 11, hãy kiểm tra **JVM compatibility**; khi thấy hai variants tương tự cùng đáp ứng yêu cầu, hãy kiểm tra rules/attributes phân biệt.

## 8. Các tùy chọn CLI của resolvableConfigurations

| Lệnh | Ý nghĩa |
| --- | --- |
| `./gradlew :app:resolvableConfigurations` | Xem các resolvable configurations mặc định |
| `./gradlew :app:resolvableConfigurations --configuration compileClasspath` | Xem duy nhất `compileClasspath` |
| `./gradlew :app:resolvableConfigurations --configuration runtimeClasspath` | Xem duy nhất `runtimeClasspath` |
| `./gradlew :app:resolvableConfigurations --recursive` | Hiển thị cả các configuration ancestor được kế thừa bắc cầu |
| `./gradlew :app:resolvableConfigurations --no-recursive` | Không mở rộng quan hệ extendsFrom bắc cầu |
| `./gradlew :app:resolvableConfigurations --all` | Thêm legacy/deprecated/attributeless entries |
| `./gradlew :app:resolvableConfigurations --no-all` | Giới hạn về tập report mặc định |

Lệnh thực hành:

~~~bash
./gradlew :app:resolvableConfigurations --configuration compileClasspath
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath --recursive
./gradlew :app:resolvableConfigurations --all
~~~

**Khác `outgoingVariants`:**

- `--configuration` chỉ dùng để lọc **consumer configuration** trong `resolvableConfigurations`.
- `--variant` chỉ dùng để lọc **producer variant** trong `outgoingVariants`.
- `--recursive` liên quan **Extended Configurations** của `resolvableConfigurations`, không phải option bắt buộc của `outgoingVariants`.
- `--all` mở rộng thông tin report; **không** phải yêu cầu “tải tất cả dependencies”.

Nếu báo cáo không xuất hiện configuration bạn kỳ vọng, kiểm tra plugin có tạo configuration ấy không và dùng `--all` nếu nghi nó thiếu attributes/thuộc legacy scope. Đừng tạo tùy tiện một configuration tên `compileClasspath` khi Java plugin đã quản lý nó.

### 8.1. Entry không có attributes

Theo hành vi report Gradle mới hơn, entry không attributes có thể ẩn theo mặc định và xuất hiện với marker `(n)` khi `--all` được dùng. Không thể suy ra từ việc nó ẩn rằng “Gradle không biết configuration này”; có thể nó không phù hợp cho variant-aware selection.

Một configuration custom được đánh dấu có thể vẫn mang một tập dependencies, nhưng để chọn đúng variant của producer một cách an toàn thường cần **consumer attributes** thích hợp. Đặc biệt với project dependency có nhiều variants, một custom resolvable configuration thiếu thông tin có thể tạo ambiguity.

## 9. Đặt hai báo cáo cạnh nhau: xác định yêu cầu và khả năng

Cách làm hiệu quả nhất là **xem một project producer và một project consumer trong cùng build**.

| Điều cần biết | Producer `:lib` | Consumer `:app` |
| --- | --- | --- |
| Task báo cáo | `:lib:outgoingVariants` | `:app:resolvableConfigurations` |
| Thứ cần xem | `apiElements`, `runtimeElements` | `compileClasspath`, `runtimeClasspath` |
| Usage cho compile | `java-api` | `java-api` |
| Usage cho runtime | `java-runtime` | `java-runtime` |
| Category thường gặp | `library` | `library` |
| JVM version | JVM target producer | JVM target yêu cầu consumer |
| Capability | Module/capability được công bố | Yêu cầu capability qua dependency/selection |
| Artifacts | JAR, classes/resources artifact sets | Consumer cần loại artifact nào, được chọn khi resolve |
| Extended Configurations | Không phải trọng tâm `outgoingVariants` | `compileOnly`/`implementation`, `runtimeOnly`/`implementation` |

Dùng một “bảng đối chiếu” tối giản:

~~~text
:app compileClasspath: org.gradle.usage = java-api
    :lib apiElements: org.gradle.usage = java-api
    => ứng viên phù hợp cho compile graph

:app runtimeClasspath: org.gradle.usage = java-runtime
    :lib runtimeElements: org.gradle.usage = java-runtime
    => ứng viên phù hợp cho runtime graph
~~~

Đây là **mô hình khái niệm**. Gradle còn xem category, JVM compatibility, library elements, capabilities và các rules/attributes khác. Không chỉ so sánh mỗi usage rồi tuyên bố chắc chắn đã match trong mọi hệ plugin.

### 9.1. Attributes của hai phía có cần giống tuyệt đối?

**Không nhất thiết.** Có những rules cho phép các giá trị tương thích không trùng ký tự. Ví dụ Java consumer yêu cầu dạng class directory nhưng producer chính có JAR và secondary artifact set cung cấp classes, nên lựa chọn artifact có thể vẫn hợp lệ.

Tuy nhiên, có trường hợp thực sự không tương thích:

~~~text
Consumer :app:runtimeClasspath cần chạy trên Java 11.
Producer :lib:runtimeElements yêu cầu JVM target 17.
~~~

Trong tình huống đó, nếu không có variant producer tương thích Java 11, Gradle có thể báo **No matching variant** khi dùng project dependency — Java 17 class files không thể giả định chạy trên JVM 11.

### 9.2. Tên variant khác nhau không nhất thiết gây lỗi

Giả sử plugin tùy chỉnh đặt tên variant là `optimizedRuntime`, nhưng attributes vẫn phù hợp yêu cầu runtime của consumer. Gradle không cần tên `runtimeElements` để match. Ngược lại, một variant **tên** `runtimeElements` mà thiếu attributes đúng có thể không được chọn.

**Nguyên tắc:** Xác minh **attributes và capabilities**, không “chữa lỗi” bằng cách đổi tên configuration cho giống nhau.

## 10. Dự án Java 17 hoàn chỉnh gồm producer và consumer

Ví dụ này có thể **chạy được** với JDK 17 và Gradle tương thích (ưu tiên Wrapper của dự án). Không cần tải dependency bên ngoài vì `:app` chỉ phụ thuộc vào `:lib`. Cả hai dùng Gradle Kotlin DSL.

### 10.1. Cấu trúc thư mục

~~~text
variant-report-lab/
├── settings.gradle.kts
├── lib/
│   ├── build.gradle.kts
│   └── src/
│       └── main/
│           └── java/
│               └── demo/
│                   └── lib/
│                       └── Greeting.java
└── app/
    ├── build.gradle.kts
    └── src/
        └── main/
            └── java/
                └── demo/
                    └── app/
                        └── Main.java
~~~

Không cần root `build.gradle.kts` cho ví dụ đơn giản này; Gradle settings xác định root và hai subprojects. Bạn có thể tạo thêm root build script rỗng nếu tổ chức dự án yêu cầu, nhưng nó không cần thiết để chạy bài học.

### 10.2. settings.gradle.kts

~~~kotlin
rootProject.name = "variant-report-lab"

include(":lib", ":app")
~~~

`:lib` và `:app` là project paths, không phải tên variants.

### 10.3. lib/build.gradle.kts

~~~kotlin
plugins {
    id("java-library")
}

group = "demo.report"
version = "1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Giải thích:

- `java-library` áp dụng Java support và công bố API/runtime variants cho bên tiêu thụ.
- `group`, project name `lib` và `version` cho ra capability mặc định dạng `demo.report:lib:1.0`.
- Toolchain Java 17 giúp target JVM được công bố trong JVM attributes phù hợp với build này.
- Không cần repository hoặc module bên ngoài vì chỉ build source Java nội bộ.
- Các task báo cáo do Gradle cung cấp; **không cần tự `tasks.register("outgoingVariants")`**.

### 10.4. lib/src/main/java/demo/lib/Greeting.java

~~~java
package demo.lib;

public final class Greeting {
    private Greeting() {
    }

    public static String sayHello() {
        return "Hello from library";
    }
}
~~~

Mã Java 17 hợp lệ. Public API `sayHello()` trả về một chuỗi; đây là class mà consumer sẽ sử dụng khi compile và chạy.

### 10.5. app/build.gradle.kts

~~~kotlin
plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":lib"))
}

application {
    mainClass.set("demo.app.Main")
}
~~~

Ý nghĩa:

- `application` tạo task `run` cùng Java compile/run configurations.
- `implementation(project(":lib"))` mô tả **project dependency**; Gradle sẽ chọn variant của `:lib` theo requirements của `:app`.
- `mainClass` phải khớp với tên đầy đủ của `Main.java` bên dưới.
- Không cần viết `implementation(project(":lib", configuration = "apiElements"))`. Cách chọn variant theo tên explicit làm mất lợi ích variant-aware matching thông thường và không phải lựa chọn mặc định.

### 10.6. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.lib.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.sayHello());
    }
}
~~~

### 10.7. Kiểm tra Java 17 runtime

Từ root `variant-report-lab`:

~~~bash
gradle --quiet :app:run
~~~

Stdout chính xác do chương trình Java tạo ra:

~~~text
Hello from library
~~~

Gradle tự lập quan hệ cần thiết để compile Java source của library trước khi app sử dụng nó. Dòng `implementation(project(":lib"))` cung cấp project dependency; bạn không cần copy thủ công JAR vào thư mục app.

Nếu đã tạo Wrapper, dùng:

~~~bash
# macOS/Linux
./gradlew --quiet :app:run

# Windows PowerShell/cmd
gradlew.bat --quiet :app:run
~~~

Không giả định Wrapper đã tồn tại trong project mới. Nếu chưa có, dùng một Gradle tương thích đã cài và có thể tạo Wrapper bằng `gradle wrapper` để chia sẻ phiên bản Gradle.

### 10.8. Bước 1: xem producer :lib

~~~bash
gradle :lib:outgoingVariants
gradle :lib:outgoingVariants --variant apiElements
gradle :lib:outgoingVariants --variant runtimeElements
~~~

Tìm hai khối:

~~~text
Variant apiElements
  Capabilities
    - demo.report:lib:1.0 (default capability)
  Attributes
    - org.gradle.usage = java-api
    - org.gradle.jvm.version = 17
  Artifacts
    - build/libs/lib-1.0.jar

Variant runtimeElements
  Capabilities
    - demo.report:lib:1.0 (default capability)
  Attributes
    - org.gradle.usage = java-runtime
    - org.gradle.jvm.version = 17
  Artifacts
    - build/libs/lib-1.0.jar
~~~

Trích đoạn ở trên **cố tình bỏ các dòng khác** như category, bundling và library elements để tập trung vào Usage/JVM/capability. Report thực tế có thể thêm `Secondary Variants`, `mainSourceElements` hoặc các marker khác.

### 10.9. Bước 2: xem consumer :app

~~~bash
gradle :app:resolvableConfigurations --configuration compileClasspath
gradle :app:resolvableConfigurations --configuration runtimeClasspath
~~~

Đọc hai phần dự kiến:

~~~text
Configuration compileClasspath
  Attributes
    - org.gradle.usage = java-api
    - org.gradle.jvm.version = 17
  Extended Configurations
    - compileOnly
    - implementation

Configuration runtimeClasspath
  Attributes
    - org.gradle.usage = java-runtime
    - org.gradle.jvm.version = 17
  Extended Configurations
    - implementation
    - runtimeOnly
~~~

Đây là **tóm tắt kết quả**, không phải stdout chính xác. Từ đó giải thích:

- Khi `:app:compileJava` cần `:lib`, consumer compileClasspath muốn Java API.
- Khi `:app:run` cần `:lib`, consumer runtimeClasspath muốn Java runtime.
- Producer cung cấp hai variants khác nhau; Gradle có đủ thông tin để chọn cho mỗi ngữ cảnh.
- Tên dependency ở `app/build.gradle.kts` vẫn chỉ có **một dòng** `implementation(project(":lib"))`.

### 10.10. Bước 3: dùng dependencyInsight để kiểm chứng variant được chọn

~~~bash
gradle :app:dependencyInsight --dependency lib --configuration compileClasspath
gradle :app:dependencyInsight --dependency lib --configuration runtimeClasspath
~~~

Theo phiên bản Gradle, report có thể liệt kê **variant được chọn** và bảng requested/provided attributes. Với project dependency, tên được hiển thị có thể là `project :lib` thay vì module coordinate Maven. Đọc **variant name**, attribute table và selection reasons để xác nhận nó phù hợp với giải thích ở trên.

Nếu cần xem cả các variants ứng viên khi Gradle hỗ trợ:

~~~bash
gradle :app:dependencyInsight --dependency lib --configuration compileClasspath --all-variants
~~~

`--all-variants` hiển thị thông tin nhiều variant hơn khi tính năng được hỗ trợ và configuration chưa bị resolve trước đó trong cùng build; đây là lệnh hỗ trợ phân tích, **không thay thế** hai báo cáo chính.

### 10.11. Bước 4: xem dependency tree

~~~bash
gradle :app:dependencies --configuration compileClasspath
gradle :app:dependencies --configuration runtimeClasspath
~~~

Với project không có external dependencies, những báo cáo này chủ yếu cho thấy `project :lib` cùng graph tương ứng. Chúng trả lời câu hỏi **“dependency nào được giải quyết?”**, còn `outgoingVariants`/`resolvableConfigurations` trả lời **“producer cung cấp gì và consumer yêu cầu gì?”**.

### 10.12. Kiểm tra riêng mã Java bằng javac/java

Nếu chỉ muốn xác minh source Java, không dùng Gradle:

~~~bash
# macOS/Linux
mkdir -p out-lib out-app
javac -d out-lib lib/src/main/java/demo/lib/Greeting.java
javac -cp out-lib -d out-app app/src/main/java/demo/app/Main.java
java -cp out-lib:out-app demo.app.Main
~~~

Stdout:

~~~text
Hello from library
~~~

Trên Windows PowerShell/cmd:

~~~bat
mkdir out-lib
mkdir out-app
javac -d out-lib lib\src\main\java\demo\lib\Greeting.java
javac -cp out-lib -d out-app app\src\main\java\demo\app\Main.java
java -cp "out-lib;out-app" demo.app.Main
~~~

Nếu thư mục đã tồn tại, lệnh `mkdir` có thể báo tồn tại; khi đó bỏ qua bước tạo và dùng lại output directory phù hợp. Phân cách classpath `:` áp dụng cho Unix, `;` cho Windows.

**Giới hạn kiểm tra:** `javac`/`java` trực tiếp chỉ xác minh source Java. Nó **không chứng minh Gradle đã chọn `apiElements` hay `runtimeElements`**. Để kiểm tra variant selection cần báo cáo và một lần build Gradle thực sự.

## 11. Groovy DSL: vẫn đọc cùng hai báo cáo

Nếu project dùng `build.gradle` thay vì `build.gradle.kts`, tên reporting tasks không đổi.

Ví dụ `lib/build.gradle` tương đương:

~~~groovy
plugins {
    id 'java-library'
}

group = 'demo.report'
version = '1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Ví dụ `app/build.gradle`:

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
    implementation project(':lib')
}

application {
    mainClass = 'demo.app.Main'
}
~~~

Hai đoạn này là **phiên bản thay thế** cho Kotlin build scripts của mục 10; không nên đặt đồng thời cả hai dạng script trong cùng một project mà không hiểu cơ chế chọn script. `settings.gradle` tương đương:

~~~groovy
rootProject.name = 'variant-report-lab'
include ':lib', ':app'
~~~

Các class Java `Greeting.java` và `Main.java` giữ nguyên. Commands vẫn:

~~~bash
gradle :lib:outgoingVariants
gradle :app:resolvableConfigurations --configuration compileClasspath
gradle --quiet :app:run
~~~

Sự khác biệt Kotlin/Groovy chỉ là **DSL dùng để khai báo**. Attributes, capabilities, variants và task report vẫn dựa trên cùng Gradle model.

## 12. Đọc capability để hiểu xung đột implementation

Một capability mô tả khả năng mà variant cung cấp, không phải tên task hoặc class. Ví dụ `demo.report:lib:1.0` là default capability. Plugin có thể công bố capability tùy biến cho một tính năng.

Tình huống khái niệm:

~~~text
Project :app
  +-- library-A provides capability com.example:json-engine
  +-- library-B provides capability com.example:json-engine
~~~

Nếu hai implementations cùng cung cấp capability được xem là cạnh tranh, Gradle có thể báo conflict khi cả hai xuất hiện và cần rule/selection rõ ràng. **Đừng sửa bằng cách đổi tên variant**; tên không phải giải pháp. Cần xem producer capabilities, dependency graph và nhu cầu ứng dụng, rồi chọn implementation phù hợp.

Trong `outgoingVariants`, nhìn `Capabilities` để xác nhận capability thực tế. Trong `resolvableConfigurations`, không nhất thiết có phần riêng “Selected capabilities” cho mọi dependency; report đó tập trung **consumer configuration và attributes**. Muốn hiểu một dependency cụ thể đã được chọn hay conflict ra sao, dùng `dependencyInsight` cùng graph.

### 12.1. Default capability và custom capability

- Default capability thường được tạo từ `group:name:version`.
- Custom capability được định nghĩa bởi build logic/plugin để biểu đạt chức năng cụ thể.
- Một producer variant có thể công bố hơn một capability tùy cấu hình.
- Đọc đúng tọa độ của capability để biết implementation nào đang quảng bá cùng khả năng.
- Hai modules có tên khác nhau **vẫn có thể xung đột** nếu cung cấp cùng capability.
- Không dùng `exclude` vô tội vạ nếu vấn đề là capability conflict; nên xác định nhà cung cấp muốn dùng.

## 13. Cách đọc Java version compatibility

Một nguyên nhân phổ biến của `No matching variant` là không tương thích JVM target.

Giả sử:

~~~text
:app consumer compileClasspath:
  org.gradle.usage = java-api
  org.gradle.jvm.version = 11

:lib producer apiElements:
  org.gradle.usage = java-api
  org.gradle.jvm.version = 17
~~~

Nếu chỉ có producer Java 17, consumer muốn một thư viện chạy được trên Java 11 sẽ **không thể giả định** sử dụng class files Java 17. Gradle có thể từ chối variant, vì class compiled cho 17 không tương thích JVM 11.

Khi người học gặp lỗi tương tự:

1. Xem `:lib:outgoingVariants --variant apiElements` để biết JVM target phía producer.
2. Xem `:app:resolvableConfigurations --configuration compileClasspath` để biết JVM yêu cầu phía consumer.
3. So sánh `org.gradle.jvm.version`, `org.gradle.usage`, category và library elements.
4. Kiểm tra Java toolchain/sourceCompatibility/targetCompatibility/release thực tế của từng project.
5. Chọn một toolchain/target phù hợp hoặc cung cấp một variant tương thích, thay vì tắt kiểm tra variant.
6. Chạy lại compile/test/runtime sau khi sửa.

### 13.1. Toolchain không bảo đảm mọi dependency hỗ trợ cùng version

Cấu hình:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

yêu cầu công cụ Java 17 cho task thích hợp. Nó **không** biến một JAR build cho Java 21 thành JAR Java 17. Nếu dependency bên ngoài chỉ cung cấp Java 21 bytecode, consumer Java 17 có thể bị chặn trong variant selection hoặc lỗi class loading tùy metadata/kiểu artifact.

Ngoài ra, Gradle có yêu cầu JDK riêng **để chạy chính Gradle**. Toolchain cho project và JVM khởi động Gradle là hai vấn đề cần kiểm tra riêng.

## 14. No matching variant và Cannot choose between variants

### 14.1. No matching variant

Đây là trường hợp **không có variant producer tương thích** với yêu cầu consumer. Ví dụ:

~~~text
Consumer requests:
  org.gradle.usage = java-api
  org.gradle.jvm.version = 11

Producer offers only:
  org.gradle.usage = java-runtime
  org.gradle.jvm.version = 17
~~~

Không có ứng viên compile API/JVM phù hợp. Những báo cáo cần xem:

~~~bash
gradle :lib:outgoingVariants --all
gradle :app:resolvableConfigurations --configuration compileClasspath
~~~

Kiểm tra producer có consumable variant với attributes và artifacts đúng, consumer có yêu cầu hợp lệ, plugin đã áp dụng đúng, target JVM có tương thích không.

### 14.2. Cannot choose between variants / Ambiguous variants

Nếu **nhiều** variants có attributes/capabilities tương thích nhưng Gradle không đủ thông tin để chọn, build có thể báo ambiguity.

Ví dụ khái niệm:

~~~text
Consumer asks: org.gradle.usage = java-runtime
Producer offers:
    runtimeStandard: usage=java-runtime, flavor=standard
    runtimeOptimized: usage=java-runtime, flavor=optimized
Consumer does not specify flavor and no rule can disambiguate.
~~~

Cần xác định **attribute phân biệt**, quy tắc compatibility/disambiguation và mục tiêu consumer. Không khắc phục bằng cách tự ý xóa một variant hoặc thêm `dependsOn` giữa các task.

### 14.3. Duplicated outgoing variants

Nếu producer công bố nhiều consumable configurations có **cùng attributes và capabilities**, có thể có lỗi hoặc cảnh báo về variants không phân biệt được. Gradle có thể vẫn cho `outgoingVariants` hiển thị thông tin ở chế độ lenient để bạn xác định cấu hình gây mâu thuẫn.

Hãy xem:

- Tên những variants tương tự.
- Attributes/capabilities thực tế giống hoặc khác nhau ở đâu.
- Plugin nào tạo chúng.
- Liệu configuration chỉ dành cho nội bộ có bị đánh dấu `canBeConsumed` sai.
- Có nên loại một variant thừa khỏi mô hình công bố hoặc thêm attribute phân biệt có ý nghĩa thật không.

Không đặt attribute tùy ý chỉ để “lừa” variant selection. Attributes cần biểu đạt đặc tính thực sự của artifact.

## 15. Đừng suy luận sai từ báo cáo

### Hiểu lầm 1: “outgoingVariants in ra JAR nên file đã được tạo”

Không nhất thiết. Report liệt kê artifact **được công bố/dự kiến**. Muốn biết JAR đã tồn tại, chạy `:lib:jar` hoặc `:lib:build` và kiểm tra `lib/build/libs`.

### Hiểu lầm 2: “resolvableConfigurations liệt kê compileClasspath nên compiler đã chạy”

Không. Nó mô tả configuration được phép resolve và attributes; task `compileJava` chỉ chạy khi được lên lịch và thực thi.

### Hiểu lầm 3: “compileClasspath hiển thị classes còn apiElements hiển thị jar: sai cấu hình”

Chưa chắc. Secondary classes artifact set và compatibility/artifact selection có thể làm hai thông tin cùng đúng.

### Hiểu lầm 4: “Tên giống nhau mới match”

Không. Variant matching chủ yếu theo attributes và capabilities. Tên variant là nhãn hữu ích để debug.

### Hiểu lầm 5: “api và implementation đều là outgoing variants”

Trong Java Library plugin, `api` và `implementation` chủ yếu là **dependency declaration scopes**; `apiElements` và `runtimeElements` mới là outgoing variants tiêu biểu.

### Hiểu lầm 6: “--all nghĩa là dùng tất cả variants để build”

Không. `--all` chỉ mở rộng **báo cáo**. Nó không ép consumer resolve mọi variant hoặc tải mọi artifact.

### Hiểu lầm 7: “--variant runtimeElements ép app dùng runtimeElements”

Không. `--variant` chỉ lọc output của task `outgoingVariants`. Consumer selection vẫn diễn ra theo dependency requirements.

### Hiểu lầm 8: “resolvableConfigurations đã cho biết module/version được chọn”

Nó cho biết **configuration và attributes**, không phải full resolved dependency graph. Dùng `dependencies`/`dependencyInsight` khi cần module/version/path.

### Hiểu lầm 9: “Capabilities là tên file”

Capability là thuộc tính chức năng/identity của component variant, không phải artifact file. Default capability dạng `group:name:version` có thể trông giống module coordinate nhưng mang vai trò trong resolution.

### Hiểu lầm 10: “Một project có variants thì project khác tự thấy hết”

Producer phải công bố consumable variants phù hợp; consumer phải có dependency declaration và yêu cầu tương thích. Có outgoing variants không tự thêm project dependency vào `:app`.

## 16. Khi report không xuất hiện hoặc khác ví dụ

Một số nguyên nhân:

- Không áp dụng `java-library`: project chỉ dùng plugin khác có thể công bố variants khác.
- Chạy nhầm task ở **root** thay vì `:lib`.
- Không có `compileClasspath` vì project chưa áp dụng Java/JVM plugin.
- Dùng Gradle cũ không có `resolvableConfigurations` (task này được giới thiệu từ Gradle 7.5).
- Một custom configuration không có attributes nên **bị ẩn theo mặc định** ở Gradle mới; chạy `--all`.
- Version/group chưa khai báo nên default capability hoặc JAR path khác.
- Target JVM không phải 17 do toolchain/compatibility settings khác.
- Plugin bên ngoài tạo thêm variants/artifact sets/capabilities.
- Báo cáo phiên bản hiện tại có format khác tài liệu hoặc ví dụ cũ.
- Lỗi build script ở configuration phase ngăn report chạy.
- Custom configurations được tạo nhưng vai trò `canBeResolved`/`canBeConsumed` không đúng.
- Một entry là **legacy configuration**, chỉ hiện khi dùng `--all`.

Thứ tự xử lý:

1. Xem `gradle --version` và `gradle tasks --all` tại project.
2. Kiểm tra plugin đã áp dụng.
3. Chạy `:lib:outgoingVariants --all` và `:app:resolvableConfigurations --all`.
4. Lọc đúng variant/configuration thay vì đọc output dài.
5. So sánh attributes và capabilities.
6. Nếu vẫn lỗi resolution, dùng `dependencyInsight`/`dependencies` với classpath thích hợp.
7. Chạy `:app:compileJava` hoặc `:app:run` để xác minh end-to-end.

Đừng tự ý sửa configuration roles hoặc attributes chỉ vì một đoạn trích báo cáo không giống ví dụ; xác định khác biệt theo version/plugin trước.

## 17. Thực hành đọc báo cáo theo tình huống

### Tình huống A: app compile được, chạy lỗi

`:app:compileClasspath` có `java-api`; `:app:runtimeClasspath` có `java-runtime`. Producer `:lib` có hai variants với dependency sets khác nhau.

Cách làm:

1. Chạy `:lib:outgoingVariants --variant apiElements` và `--variant runtimeElements`.
2. Chạy `:app:resolvableConfigurations --configuration compileClasspath`/`runtimeClasspath`.
3. So sánh Usage, JVM, Category, artifacts và capabilities.
4. Chạy `:app:dependencies --configuration runtimeClasspath` để xem runtime module graph.
5. Chạy `:app:run` hoặc test gần production để tìm missing class/module.

Đừng mặc định “compile qua thì runtime phải đúng” khi các graph/variants có thể khác nhau.

### Tình huống B: một dependency bị chọn version bất ngờ

Hai báo cáo chính có thể cho thấy variant yêu cầu/cung cấp, nhưng **không** giải thích vì sao module version 1.5 được chọn thay 1.2. Dùng:

~~~bash
gradle :app:dependencyInsight --dependency ten-module --configuration runtimeClasspath
~~~

Trong build thật, thay `ten-module` bằng module cụ thể trong graph. Report insight giải thích conflict resolution, constraints hoặc selection reasons. Không nhầm vấn đề **version resolution** với vấn đề **variant selection**.

### Tình huống C: thư viện có secondary classes variant

Producer `apiElements` công bố main artifact JAR và secondary classes directory. Consumer compileClasspath hỏi `libraryelements=classes`.

Đây có thể là cơ chế **artifact selection bình thường**. Nếu biên dịch thành công, không cần ép consumer chuyển về JAR chỉ để bảng attributes trông giống nhau.

### Tình huống D: custom variant không xuất hiện

Dùng `outgoingVariants --all`; nếu thấy marker `(n)`, kiểm tra có attributes cần thiết và vai trò consumable đúng không. Một configuration chỉ declarable không phải variant cần được công bố.

### Tình huống E: hai thư viện có cùng capability

Chạy outgoingVariants cho từng producer, so sánh `Capabilities`. Nếu cùng capability xuất hiện trong graph của consumer và Gradle báo conflict, xác định implementation thật sự mong muốn và cấu hình capability selection phù hợp. Không giải quyết bằng cách chỉnh `mainClass` hoặc thứ tự task.

## 18. Quy trình đọc và chẩn đoán 10 bước

1. **Xác định producer/consumer.** Thường producer là thư viện, consumer là ứng dụng hoặc thư viện khác phụ thuộc nó.
2. **Xác định task/path đúng.** `:lib:outgoingVariants`, `:app:resolvableConfigurations`.
3. **Xem producer variants.** Tìm API/runtime, features, verification variants.
4. **Đọc Capabilities.** Default/custom capability có tên gì, có trùng các implementation khác không?
5. **Đọc Attributes producer.** Usage, Category, LibraryElements, JVM, bundling và attributes plugin-specific.
6. **Đọc Artifacts.** Producer công bố JAR, thư mục classes, resources hay artifact tùy chỉnh?
7. **Xem consumer configuration.** `compileClasspath`/`runtimeClasspath` hoặc configuration thật của task lỗi.
8. **Đọc Attributes và Extended Configurations consumer.** Yêu cầu gì, nhận declarations từ scopes nào?
9. **Đối chiếu và xác minh kết quả.** Dùng `dependencyInsight` để xem variant thực sự được chọn; `dependencies` để xem module graph; chạy compile/run/test.
10. **Chỉ sửa cấu hình có chứng cứ.** Điều chỉnh plugin, JVM toolchain, dependency declaration, capabilities hoặc attributes theo nhu cầu thật, không vô tình thay cả project.

Các lệnh tra cứu nhanh:

~~~bash
./gradlew :lib:outgoingVariants
./gradlew :lib:outgoingVariants --variant apiElements
./gradlew :lib:outgoingVariants --variant runtimeElements
./gradlew :lib:outgoingVariants --all

./gradlew :app:resolvableConfigurations
./gradlew :app:resolvableConfigurations --configuration compileClasspath
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath --recursive
./gradlew :app:resolvableConfigurations --all

./gradlew :app:dependencyInsight --dependency lib --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew --quiet :app:run
~~~

Đây là các lệnh **đọc/report/chạy**; reporting tasks không sửa source code hay file `build.gradle.kts`. Tuy nhiên quá trình chạy Gradle vẫn có thể thực hiện configuration, truy cập cache hoặc khởi chạy tasks cần thiết tùy command/plugin. Không đồng nhất “report” với bảo đảm không có side effects từ plugin.

## 19. Bài tập tự kiểm tra có đáp án

### Bài 1. Chọn đúng báo cáo

Bạn muốn biết `:lib` công bố JAR/capabilities/attributes nào để `:app` sử dụng. Chạy lệnh nào?

**Đáp án:**

~~~bash
gradle :lib:outgoingVariants
~~~

Lý do: đây là **producer report**. `:app:resolvableConfigurations` mô tả requirements của app, không phải artifacts của lib.

### Bài 2. Chỉ xem compile classpath

Muốn đọc requirements của `:app:compileClasspath`:

~~~bash
gradle :app:resolvableConfigurations --configuration compileClasspath
~~~

**Đáp án:** Đúng. Report cho biết compile classpath attributes và Extended Configurations; không liệt kê đầy đủ resolved module graph.

### Bài 3. Variant nào phù hợp java-api?

Producer cung cấp:

~~~text
apiElements: org.gradle.usage=java-api
runtimeElements: org.gradle.usage=java-runtime
~~~

Consumer muốn `java-api`. Variant nào là ứng viên phù hợp nhất trong mô hình Java cơ bản?

**Đáp án:** `apiElements`, giả sử các attributes/capabilities khác cũng tương thích. Tên variant không phải nguyên nhân duy nhất; usage và các rules/attributes mới quyết định.

### Bài 4. Existence vs execution

`outgoingVariants` hiển thị:

~~~text
Artifacts
  - build/libs/lib-1.0.jar
~~~

Điều này có chứng minh file đang tồn tại không?

**Đáp án:** Không. Đây là artifact **được công bố**. Cần chạy `:lib:jar` hoặc tác vụ build tiêu thụ artifact và kiểm tra file output để xác nhận sự tồn tại.

### Bài 5. Classes vs JAR

Producer `apiElements` ghi `org.gradle.libraryelements=jar`, consumer `compileClasspath` ghi `classes`. Có phải lỗi chắc chắn?

**Đáp án:** Không. Java ecosystem có compatibility/artifact selection và secondary classes variant. Đọc `Secondary Variants`, kiểm tra `dependencyInsight` và compile thực tế.

### Bài 6. Extended Configurations

Report `compileClasspath` ghi:

~~~text
Extended Configurations
  - compileOnly
  - implementation
~~~

Điều đó nghĩa là app đã chọn variants của hai producer tên `compileOnly` và `implementation`?

**Đáp án:** Không. Đó là **dependency declaration scopes** được compileClasspath kế thừa, không phải tên producer variants đã chọn.

### Bài 7. --all hiển thị thêm gì?

Custom outgoing configuration không có attributes nên không thấy trong report mặc định của Gradle mới. Lệnh nào giúp kiểm tra?

**Đáp án:**

~~~bash
gradle :lib:outgoingVariants --all
~~~

Nếu entry xuất hiện với marker `(n)`, nó thiếu attributes và không thể tham gia variant-aware selection thông thường; chỉ “đã xuất hiện trong report” chưa đủ để coi đó là outgoing variant dùng được.

### Bài 8. JVM mismatch

`:app` yêu cầu JVM 11, `:lib` chỉ cung cấp Java 17 variant. Vì sao có thể `No matching variant`?

**Đáp án:** Java 17 class files không tương thích JVM 11. Kiểm tra `org.gradle.jvm.version` ở cả hai report, sửa target/toolchain hoặc cung cấp variant tương thích.

### Bài 9. Capability conflict

Hai modules A và B cùng công bố capability `com.example:engine` và đều có trong consumer graph. Nên xem gì?

**Đáp án:** So sánh `Capabilities` trong outgoingVariants của A/B, dùng dependency report của consumer rồi chọn implementation theo cơ chế capability selection phù hợp. Không chỉ đổi tên JAR hoặc task.

### Bài 10. Tên variant khác nhau

Producer có variant `fastRuntime`, usage `java-runtime`; consumer runtimeClasspath yêu cầu `java-runtime`. Có thể match không?

**Đáp án:** Có thể, nếu các attributes/capabilities/rules khác phù hợp. Gradle không đòi tên phải là `runtimeElements`.

### Bài 11. Muốn biết version được chọn

Hai versions khác nhau của cùng module cùng xuất hiện trong dependency graph. Dùng một trong hai report chính để biết version cuối chắc chắn được chọn?

**Đáp án:** Không đủ. Dùng `gradle :app:dependencyInsight --dependency ten-module --configuration runtimeClasspath` hoặc `gradle :app:dependencies --configuration runtimeClasspath`.

### Bài 12. Chạy Java 17

Trong project mục 10, mã `Greeting.sayHello()` trả `Hello from library`, Main in giá trị đó. Chạy `gradle --quiet :app:run` sẽ in gì?

**Đáp án:**

~~~text
Hello from library
~~~

Nếu project không compile, kiểm tra source path/package, plugin, JDK/toolchain và project dependency trước khi kết luận lỗi variant.

## 20. Tờ ghi nhớ

| Bạn muốn biết | Lệnh / nơi đọc |
| --- | --- |
| Project `:lib` cung cấp variants nào? | `gradle :lib:outgoingVariants` |
| Capabilities của `apiElements`? | `gradle :lib:outgoingVariants --variant apiElements` |
| Attributes/artifacts của `runtimeElements`? | `gradle :lib:outgoingVariants --variant runtimeElements` |
| Legacy/attributeless outgoing entries? | `gradle :lib:outgoingVariants --all` |
| `:app` có resolvable configurations nào? | `gradle :app:resolvableConfigurations` |
| Compile consumer yêu cầu attributes gì? | `gradle :app:resolvableConfigurations --configuration compileClasspath` |
| Runtime consumer yêu cầu attributes gì? | `gradle :app:resolvableConfigurations --configuration runtimeClasspath` |
| Xem cả extended configurations bắc cầu? | `gradle :app:resolvableConfigurations --recursive` |
| Legacy/attributeless resolvable entries? | `gradle :app:resolvableConfigurations --all` |
| Module/variant nào cuối cùng được chọn? | `gradle :app:dependencyInsight --dependency lib --configuration compileClasspath` |
| Toàn bộ resolved dependency graph? | `gradle :app:dependencies --configuration runtimeClasspath` |
| Kiểm tra ứng dụng Java thật? | `gradle --quiet :app:run` |

**Kết luận:** Dùng `outgoingVariants` để đọc **khả năng bên producer cung cấp** (variants, capabilities, attributes, artifacts). Dùng `resolvableConfigurations` để đọc **yêu cầu của consumer** (resolvable configurations, attributes, hierarchy). Đặt hai báo cáo cạnh nhau để hiểu *vì sao một variant có thể tương thích*, rồi dùng `dependencyInsight`/`dependencies` và một lần compile/run/test để kiểm tra **lựa chọn thực tế**. Đừng suy đoán từ tên configuration hoặc đường dẫn JAR duy nhất.

## Tài liệu chính thức của Gradle

- [Variant Selection and Attribute Matching](https://docs.gradle.org/current/userguide/variant_aware_resolution.html) — cách chọn variants, phần **Visualizing Variant Information**, `outgoingVariants` và `resolvableConfigurations`.
- [Variants and Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html) — các attribute thông dụng và consumer/producer matching.
- [Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html) — declarable/resolvable/consumable roles và configuration inheritance.
- [Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html) — `api`/`implementation`, `apiElements`/`runtimeElements`.
- [Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) — `dependencies` và `dependencyInsight`, bao gồm `--all-variants`.
- [Upgrading within Gradle 9.x](https://docs.gradle.org/current/userguide/upgrading_version_9.html) — thay đổi mặc định ẩn configurations không có attributes trong các báo cáo ở các bản Gradle 9.x mới.
