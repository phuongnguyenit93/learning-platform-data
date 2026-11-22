# Chẩn đoán lỗi không có variant phù hợp hoặc có nhiều variant phù hợp trong Gradle

## 1. Vấn đề cần giải quyết

Trong Gradle, hai dependency có **cùng tọa độ module** chưa chắc được tiêu thụ theo cùng cách. Một thư viện có thể công bố các **variant** khác nhau cho biên dịch API, runtime, JVM version, hệ điều hành, artifact format hoặc một feature tùy chỉnh. Gradle so sánh điều consumer yêu cầu với điều producer cung cấp để chọn **một variant thích hợp**.

Hai loại lỗi chính khi so khớp:

1. **No matching variant** — không có variant nào của producer tương thích với các thuộc tính/capability mà consumer yêu cầu.
2. **Ambiguous variants** — có từ hai variant trở lên vẫn tương thích mà Gradle không có đủ quy tắc hoặc giá trị để quyết định chọn cái nào.

Ví dụ dạng thông báo (câu chữ cụ thể tùy Gradle Wrapper, plugin và metadata):

```text
No matching variant of project :producer was found.
The consumer was configured to find ...
...
Variant '...': incompatible because ...
```

Hoặc:

```text
Cannot choose between the following variants of project :producer:
  - eastElements
  - westElements
...
All of them match the consumer attributes ...
```

**Không sửa lỗi bằng cách đoán tên file JAR, đổi version tùy tiện hoặc tắt transitive dependencies.** Hãy so sánh: **consumer requests → producer variants → compatibility → disambiguation → capability/artifact**.

Sau bài học bạn có thể:

- Đọc được `org.gradle.usage`, `org.gradle.category`, `org.gradle.jvm.version`, `org.gradle.libraryelements` và custom attributes.
- Biết khác biệt giữa **configuration dùng để khai báo dependency**, **resolvable configuration của consumer** và **consumable configuration của producer**.
- Dùng `outgoingVariants`, `resolvableConfigurations`, `dependencies` và `dependencyInsight --all-variants` đúng mục đích.
- Tự tạo và sửa hai lỗi đối lập bằng một Gradle multi-project demo không cần plugin bên ngoài.
- Phân biệt **variant selection failure**, **capability conflict**, **version conflict**, **artifact download failure** và **toolchain failure**.
- Chọn đúng nơi sửa: attributes consumer, variants/metadata producer, plugin compatibility, capability requirement hoặc resolution rules.

## 2. Các khái niệm nền tảng

### 2.1. Component và variant

**Component** là một đơn vị được resolve, ví dụ module `com.example:library:1.0` hoặc project `:library`. Component có thể cung cấp nhiều variants. Mỗi variant có:

- **Attributes**: các cặp key/value typed mô tả cách sử dụng hoặc đặc điểm artifact.
- **Capabilities**: một hoặc nhiều chức năng module cung cấp, dùng để nhận diện các provider tương đương hoặc đối nghịch.
- **Artifacts**: file JAR, classes directory, ZIP hoặc các output khác.
- **Dependencies/constraints**: có thể khác nhau giữa API và runtime variants.

Tên `apiElements`, `runtimeElements`, `eastElements` thường dùng để đọc/debug, **không phải tiêu chí ưu tiên**. Gradle lựa chọn dựa trên attributes, capabilities và rules, không tự hiểu “tên có chữ runtime thì phù hợp hơn”.

### 2.2. Consumer so với producer

| Vai trò | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Consumer resolvable configuration | `compileClasspath`, `runtimeClasspath`, custom `incomingPayload` | Chứa attributes **yêu cầu**, resolution chọn dependency variants |
| Producer consumable configuration | `apiElements`, `runtimeElements`, custom `eastElements` | Công bố attributes, capabilities, artifacts, dependencies |
| Dependency scope / bucket | `implementation`, `api`, `testImplementation` | Nơi khai báo dependencies; **không nhất thiết tự resolve** |
| Artifact selection sau graph selection | File JAR hoặc classes directory | Chọn artifact phù hợp sau khi graph/component variant được chọn |

Gradle hiện đại phân biệt ba vai trò `canBeDeclared`, `canBeResolved`, `canBeConsumed`. Với configuration tự tạo, nên chọn **một vai trò rõ ràng**, không bật tất cả. Trong ví dụ `java-library`:

- `implementation` là bucket để **khai báo** dependencies.
- `compileClasspath` là configuration có thể **resolve** cho compile.
- `apiElements` là một variant có thể **consume** của library.

Do đó **không dùng `implementation` làm tên configuration khi chạy `dependencyInsight`** nếu plugin cho biết đó là bucket không resolvable; hãy chọn `compileClasspath`/`runtimeClasspath` hay một resolvable configuration phù hợp.

### 2.3. Attributes tiêu biểu của JVM ecosystem

| Attribute | Ví dụ producer | Ví dụ consumer | Dấu hiệu cần xem |
| --- | --- | --- | --- |
| `org.gradle.usage` | `java-api`, `java-runtime` | Compile cần API; runtime cần runtime | Đang cố dùng artifact runtime như API hay ngược lại? |
| `org.gradle.category` | `library`, `platform`, `verification` | Library hoặc platform được yêu cầu | Có dùng `platform(...)`/BOM sai mục đích? |
| `org.gradle.jvm.version` | `8`, `11`, `17`, `21` | Consumer đòi chạy trên JDK/JVM version cụ thể | Producer yêu cầu Java mới hơn mức consumer cho phép? |
| `org.gradle.libraryelements` | `jar`, `classes` | File/format phù hợp compile | Có plugin/artifact type tương thích không? |
| `org.gradle.dependency.bundling` | `external`, `embedded` | Cách đóng gói dependencies | Có mismatch khi consumer cần một kiểu bundling? |
| `org.gradle.jvm.environment` | `standard-jvm`, `android` | Môi trường JVM | Đừng suy rằng mọi giá trị luôn bất tương thích; Gradle có rules |
| Custom `com.example.flavor` | `east`, `west` | `east`, `west` hoặc không chỉ định | Thiếu giá trị phân biệt hoặc giá trị không tồn tại? |

Đừng đoán **mọi attribute khác nhau** là không tương thích: Gradle áp dụng **compatibility rules**. Ví dụ ở JVM version, library target Java 11 thông thường có thể dùng từ consumer Java 17; hướng ngược lại (library yêu cầu 21, consumer chỉ cho 17) thường không phù hợp. Nếu có nhiều phiên bản JVM target tương thích, rules của JVM ecosystem thường ưu tiên phiên bản **cao nhất vẫn tương thích**.

## 3. Gradle chọn variant theo trình tự nào?

Ở mức khái niệm:

```text
Consumer resolvable configuration
  attributes, required capabilities
                |
                v
Producer component có các consumable variants
                |
                v
Lọc variants theo compatibility rules
       |                         |
       | 0 candidates            | >=1 candidates
       v                         v
NO MATCHING VARIANT     Ưu tiên mức khớp và
                        chạy disambiguation rules
                                   |
                         +---------+---------+
                         |                   |
                       1 còn                >1 còn
                         |                   |
                         v                   v
                  SELECTED VARIANT    AMBIGUOUS VARIANTS
                         |
                         v
             Resolve artifact/dependencies của variant
```

Gradle có thuật toán nhiều bước hơn sơ đồ này: xét những attributes consumer nêu, cách xử lý attributes bổ sung của producer, precedence và disambiguation rules do ecosystem/plugin định nghĩa. Không phải cứ đếm số trường khác nhau rồi chọn variant có tên ngắn nhất hoặc version cao nhất.

**Từ khóa để phân tích lỗi:**

- `incompatible`: một variant bị loại vì yêu cầu không tương thích.
- `compatible` / `matches`: variant có thể dùng nhưng chưa chắc được chọn nếu còn ứng viên khác.
- `disambiguation`: quy tắc chọn một trong nhiều variants tương thích.
- `capability`: chức năng được cung cấp; có thể dùng để yêu cầu feature hoặc phát hiện conflict giữa modules.
- `attribute`: key/value typed; **đúng kiểu cũng quan trọng**, không chỉ string hiển thị.

## 4. Chẩn đoán bằng CLI: xem hai phía trước khi sửa

Giả sử build có `:consumer` và `:producer`. Các lệnh sau dùng Gradle Wrapper; đặt đường dẫn đầy đủ để không nhầm project.

```bash
# Gradle version và JVM thực tế của build
./gradlew --version

# Producer đang cung cấp những variants, capabilities, artifacts nào?
./gradlew :producer:outgoingVariants
./gradlew :producer:outgoingVariants --all
./gradlew :producer:outgoingVariants --variant apiElements

# Consumer đang yêu cầu attributes gì ở một resolvable configuration?
./gradlew :consumer:resolvableConfigurations
./gradlew :consumer:resolvableConfigurations --configuration compileClasspath

# Dependency graph của một configuration có thể resolve:
./gradlew :consumer:dependencies --configuration compileClasspath

# Với một module dependency cụ thể:
./gradlew :consumer:dependencyInsight --dependency producer \
  --configuration compileClasspath --all-variants
```

Lệnh `--variant apiElements` ở trên **chỉ hợp lệ khi producer thật sự có variant tên `apiElements`** (ví dụ áp dụng `java-library`). Trong demo custom ở phần 7, tên đúng là `eastElements` hoặc `westElements`; dùng `--variant eastElements` thay thế. Lệnh `compileClasspath` chỉ đúng khi consumer có plugin JVM tạo configuration này; demo custom ở phần 7 dùng `incomingPayload`.

Trên Windows PowerShell thay `./gradlew` bằng `.\gradlew.bat`. Không copy ký tự nối dòng `\` của Bash vào PowerShell; chạy mỗi lệnh trên một dòng khi thử nghiệm Windows.

### 4.1. `outgoingVariants` nhìn phía producer

Report này cho biết:

- **Primary variants** tiêu thụ được, ví dụ `apiElements` và `runtimeElements`.
- **Attributes** từng variant công bố.
- **Capabilities** mặc định hoặc bổ sung.
- **Artifacts** mà variant mang.
- Một số **secondary variants** có thể phục vụ artifact selection như classes directory.

Có thể dùng `--all` để hiện legacy/configurations không có attributes. Những dòng không có attributes được báo ký hiệu riêng, thường không phải variant được chọn trong variant-aware selection. Nếu producer có **nhiều consumable configurations cùng attributes và capabilities**, Gradle hiện đại có thể báo cấu hình variant không hợp lệ ngay trong producer; đây **khác** trường hợp consumer còn hai variants có attributes khác nhau nhưng không đủ tiêu chí phân biệt.

### 4.2. `resolvableConfigurations` nhìn phía consumer

Report này thể hiện:

- Configuration nào thực sự `canBeResolved`.
- Attributes consumer yêu cầu.
- Các configurations mà nó `extendsFrom`.
- Thông tin attribute compatibility/disambiguation rules khi Gradle cung cấp.

Lệnh `--configuration <name>` giúp chỉ xem đúng configuration gây lỗi. Đừng lẫn `compileClasspath` với `runtimeClasspath`: hai cái thường có `org.gradle.usage` khác nhau, nên cùng module có thể chọn variant khác hoặc một cái pass, một cái fail.

### 4.3. `dependencyInsight --all-variants` có giới hạn

`dependencyInsight` giúp xem **module được yêu cầu bởi đường dependency nào**, version được chọn và thông tin variant selection. Flag `--all-variants` yêu cầu hiển thị tất cả variants liên quan, nhưng theo Gradle API, nó chỉ có tác dụng khi configuration **chưa bị resolve trước khi task chạy**. Với build có plugin resolve eager, report có thể không cho đủ dữ liệu.

Nếu dependency resolution **thất bại trước khi report tạo xong**, đừng kết luận lỗi không tồn tại chỉ vì `dependencyInsight` không in đầy đủ. Quay về **hai report producer/consumer + thông báo lỗi gốc**, rồi dùng `--info`/`--stacktrace` khi cần.

### 4.4. Không sửa dữ liệu trước khi biết loại lỗi

| Triệu chứng | Thứ cần kiểm tra đầu tiên |
| --- | --- |
| `No matching variant` | Attribute nào của consumer loại hết producer variants? Producer có variant phù hợp không? |
| `Cannot choose between variants` | Những variants còn lại khác nhau ở attribute nào? Consumer có thiếu giá trị chọn lựa không? |
| `No variants exist` | Producer đã tạo **consumable** configuration và attributes hợp lệ chưa? |
| `Conflict found for capability` | Hai module/variants trong graph có cung cấp cùng một capability không? |
| `Could not find group:name:version` | Repository, module coordinates, metadata hoặc quyền truy cập; chưa chắc là matching |
| `Could not download artifact` | Artifact/network/credentials/checksum sau selection; không đồng nghĩa variant ambiguity |
| `No matching toolchains found` | JDK/toolchain provisioning; cần phân biệt với JVM variant incompatibility |

## 5. Lỗi **không có variant phù hợp**: đọc chỗ bất tương thích

Một ví dụ JVM phổ biến:

```text
Consumer yêu cầu:
  org.gradle.usage       = java-runtime
  org.gradle.jvm.version = 17

Producer công bố:
  runtimeElements:
    org.gradle.usage       = java-runtime
    org.gradle.jvm.version = 21
```

Consumer chỉ được dùng binary tương thích Java 17, còn producer runtime yêu cầu Java 21. Với JVM compatibility rules thông thường, variant target 21 **không tương thích** với consumer target 17. Kết quả: `No matching variant` nếu không có variant khác phù hợp.

**Phân biệt:** JVM đang chạy Gradle daemon, **Java toolchain** để compile/test và `org.gradle.jvm.version` **trong metadata của variant** có thể là những con số khác nhau. Đừng cố “sửa” bằng cách đổi `JAVA_HOME` ngẫu nhiên. Hãy xác minh:

1. `./gradlew --version`: JVM dùng chạy Gradle.
2. `./gradlew javaToolchains` nếu project/plugin có task này: JDK đã nhận diện.
3. `outgoingVariants` của producer: JVM version nó thực sự công bố.
4. `resolvableConfigurations` của consumer: version consumer yêu cầu.
5. Source/bytecode/runtime yêu cầu phiên bản nào theo hợp đồng sản phẩm.

**Hướng giải quyết hợp lệ** là build/publish variant tương thích Java 17, hoặc nâng runtime/toolchain requirement của ứng dụng lên Java 21 **nếu** ứng dụng/hạ tầng cho phép. Không sửa attribute consumer thành 21 chỉ để qua resolution khi production thực sự chỉ chạy Java 17.

### 5.1. Mismatch `usage`, `category` và format

Ví dụ khác:

- Consumer yêu cầu `java-api` để compile, nhưng producer chỉ publish một artifact đặc thù cho `verification`.
- Consumer yêu cầu `category=platform` vì dùng `platform("g:n:v")`, producer chỉ có `category=library`.
- Consumer cần một artifact/library format đặc biệt nhưng producer không có variant tương thích.
- Custom attribute `com.example.flavor=north` trong consumer trong khi producer chỉ có `east`/`west` và không có compatibility rule.

Không phải tất cả chênh lệch đều chắc chắn fail: ecosystem có rules, và producer có thể có nhiều variants với các giá trị được chấp nhận. Hãy đọc **dòng giải thích incompatible của từng variant** thay vì suy từ tên.

### 5.2. Nếu producer không có consumable variant đúng nghĩa

Một Gradle project có thể chỉ tạo configuration để **resolve input** mà không công bố output có attributes/capability. Consumer `project(":producer")` không tự biến bất kỳ `files(...)` hoặc task output tùy ý nào thành outgoing variant. Với custom artifacts, producer cần một **consumable configuration** rõ ràng, đặt attributes, capability và artifact output. Nếu công bố code Java, ưu tiên plugin `java-library`/`java` tạo `apiElements`, `runtimeElements` chuẩn.

Dòng `No variants exist` thường hướng bạn tới **producer publishing/configuration roles**, không phải “module không được tải từ Maven Central”.

## 6. Lỗi **nhiều variant phù hợp**: thiếu thông tin phân biệt

Giả sử producer có hai variants:

| Variant | `com.example.kind` | `com.example.flavor` |
| --- | --- | --- |
| `eastElements` | `payload` | `east` |
| `westElements` | `payload` | `west` |

Consumer chỉ yêu cầu:

```text
com.example.kind = payload
```

Cả hai variants đều thỏa `kind=payload`. Consumer chưa nói cần `flavor=east` hay `west`, và với custom string attribute này **không có quy tắc mặc định chọn một flavor tốt hơn**. Nếu Gradle không có tiêu chí khác phá hòa, selection thất bại vì **ambiguity**.

Tại sao tên `eastElements` không quyết định? Vì tên variant chỉ để hiển thị trong log; engine so attributes, capability và rules. Đừng dựa vào thứ tự khai báo producer hoặc tên viết trước/sau.

**Hướng sửa thường tốt nhất:** chỉ định thuộc tính còn thiếu ở consumer nếu nhu cầu rõ ràng, ví dụ `com.example.flavor=east`, hoặc thiết kế producer chỉ công bố các variants thực sự mang ý nghĩa và có attributes đầy đủ. Nếu nhiều consumers đều cần một default hợp lý, có thể đăng ký **AttributeDisambiguationRule** cho một custom attribute, nhưng rule cần được thiết kế/test trong convention/binary plugin thay vì thêm workaround ngẫu nhiên ở mọi project.

## 7. Demo đa project: tạo cả hai lỗi, rồi sửa

Demo sử dụng **Gradle Kotlin DSL hiện đại**, chỉ dùng **core Gradle plugin** và một file văn bản. Không cần Java source, Maven Central hoặc network để resolve một dependency bên ngoài. Một Gradle Wrapper phải có sẵn; nếu tạo project mới từ đầu, dùng Gradle cài tạm để tạo Wrapper, rồi giữ lại bốn file Wrapper chuẩn.

Cấu trúc:

```text
variant-diagnostics-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── producer/
│   ├── build.gradle.kts
│   └── payload.txt
├── consumer/
│   └── build.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
```

`settings.gradle.kts`:

```kotlin
rootProject.name = "variant-diagnostics-lab"
include("producer", "consumer")
```

Root `build.gradle.kts`:

```kotlin
plugins {
    base
}
```

`producer/payload.txt`:

```text
example payload
```

### 7.1. Producer công bố hai consumable variants khác flavor

Toàn bộ `producer/build.gradle.kts`:

```kotlin
import org.gradle.api.attributes.Attribute

plugins {
    base
}

group = "com.example"
version = "1.0"

val kind = Attribute.of("com.example.kind", String::class.java)
val flavor = Attribute.of("com.example.flavor", String::class.java)

listOf("east", "west").forEach { selectedFlavor ->
    configurations.create("${selectedFlavor}Elements") {
        isCanBeDeclared = false
        isCanBeResolved = false
        isCanBeConsumed = true

        attributes {
            attribute(kind, "payload")
            attribute(flavor, selectedFlavor)
        }

        outgoing.artifact(layout.projectDirectory.file("payload.txt"))
    }
}
```

Giải thích:

- `eastElements` và `westElements` là **hai primary consumable variants**, không phải secondary artifact variants.
- Cả hai có `kind=payload`, nhưng `flavor` khác nhau nên có hai bộ attributes riêng biệt.
- Cả hai cùng expose **file payload.txt** để bài demo tập trung vào **variant selection**, không cần build artifact từ source.
- Gradle có capability mặc định của project (định danh theo group, name và version) nếu không khai báo capability tùy chỉnh.
- `isCanBeDeclared=false` / `isCanBeResolved=false` / `isCanBeConsumed=true` thể hiện đúng vai trò. Sử dụng Gradle Wrapper mới có hỗ trợ `canBeDeclared` và Kotlin DSL phù hợp; không copy nguyên vào build Gradle cũ không có API này.

Kiểm tra producer:

```bash
./gradlew :producer:outgoingVariants
./gradlew :producer:outgoingVariants --variant eastElements
```

Trong report, bạn cần nhìn thấy **hai variants `eastElements` và `westElements`**, cả hai có `com.example.kind=payload`, nhưng `com.example.flavor=east/west`. Những dòng Gradle in kèm capability và path thực tế có thể khác theo phiên bản; **không coi báo cáo này là một stdout cố định**.

### 7.2. Consumer chỉ yêu cầu kind — lỗi ambiguous

Toàn bộ `consumer/build.gradle.kts` (trạng thái ban đầu):

```kotlin
import org.gradle.api.attributes.Attribute
import org.gradle.api.tasks.Copy

plugins {
    base
}

val kind = Attribute.of("com.example.kind", String::class.java)

val incomingPayload = configurations.create("incomingPayload") {
    isCanBeDeclared = false
    isCanBeResolved = true
    isCanBeConsumed = false

    attributes {
        attribute(kind, "payload")
    }
}

dependencies {
    add(incomingPayload.name, project(":producer"))
}

tasks.register<Copy>("resolvePayload") {
    from(incomingPayload)
    into(layout.buildDirectory.dir("selected"))
}
```

Vì `incomingPayload` chỉ yêu cầu `kind=payload`, Gradle không có lý do chọn `eastElements` thay `westElements`. Chạy từ root:

```bash
./gradlew :consumer:resolvableConfigurations --configuration incomingPayload
./gradlew :producer:outgoingVariants
./gradlew :consumer:resolvePayload
```

Hai lệnh report đầu giúp quan sát hai phía. Lệnh `resolvePayload` cố resolve project dependency để copy file, nên **dự kiến build FAILED do ambiguous variants**. Thông báo có thể nêu rằng không chọn được giữa `eastElements` và `westElements`. **Không khẳng định nguyên văn mọi câu lỗi**, vì format thay đổi theo Gradle version.

Điểm cần đối chiếu:

```text
Consumer:
  com.example.kind = payload
Producer candidates:
  eastElements: kind=payload, flavor=east
  westElements: kind=payload, flavor=west
Result: hai candidates còn lại -> ambiguity
```

### 7.3. Sửa ambiguous bằng consumer attribute

Trong **cùng file `consumer/build.gradle.kts`**, thêm một attribute definition bên dưới `kind`:

```kotlin
val flavor = Attribute.of("com.example.flavor", String::class.java)
```

Và thay block `attributes` bên trong `incomingPayload` bằng:

```kotlin
attributes {
    attribute(kind, "payload")
    attribute(flavor, "east")
}
```

Đây là **các đoạn sửa**, không dán thêm một `incomingPayload` thứ hai vào build script. Bây giờ:

- `eastElements` khớp `kind=payload` và `flavor=east`.
- `westElements` không tương thích với `flavor=east` theo mặc định của custom String attribute không có compatibility rule.
- Chỉ còn `eastElements`, nên Gradle có thể chọn file `payload.txt`.

Chạy lại:

```bash
./gradlew :consumer:resolvePayload
```

Khi build thành công, file được copy đến:

```text
consumer/build/selected/payload.txt
```

Nội dung (do `payload.txt` tạo, không phải stdout của Gradle):

```text
example payload
```

Lệnh kiểm tra Linux/macOS:

```bash
cat consumer/build/selected/payload.txt
```

PowerShell:

```powershell
Get-Content consumer\build\selected\payload.txt
```

Đây là ví dụ chỉ có **một file output**; nếu dùng file cùng tên cho cả hai variants trong production thì không có giá trị nhận biết flavor từ nội dung. Khi muốn phân phối binaries thực, mỗi variant cần artifact và dependencies đúng với chức năng mà attribute công bố.

### 7.4. Cố ý tạo lỗi no matching bằng `flavor=north`

Chỉ đổi consumer attribute từ `east` thành `north`:

```kotlin
attributes {
    attribute(kind, "payload")
    attribute(flavor, "north")
}
```

Producer chỉ có `east` và `west`, không có `north`. Chạy:

```bash
./gradlew :consumer:resolvePayload
```

Kết quả dự kiến: build **FAILED với thông báo không có variant phù hợp**. Report giải thích mỗi candidate khác `com.example.flavor`. Không phải lỗi Maven repository hay thiếu file: file `producer/payload.txt` vẫn tồn tại, nhưng **không variant nào được phép cung cấp nó cho yêu cầu hiện tại**.

Hai cách sửa hợp lệ:

1. Nếu consumer **thực sự muốn east/west**, thay `north` bằng giá trị đã được publisher hỗ trợ.
2. Nếu cần **north như một sản phẩm mới**, producer phải công bố variant `northElements` với artifact/dependencies đúng, rồi consumer mới yêu cầu nó.

Không nên thêm rule “north tương thích với mọi flavor” khi các payload có tính năng khác nhau; làm vậy khiến build pass nhưng nhận artifact sai.

### 7.5. Windows và giới hạn của demo

Trên Windows, thay `./gradlew` bằng `.\gradlew.bat`:

```powershell
.\gradlew.bat :producer:outgoingVariants
.\gradlew.bat :consumer:resolvableConfigurations --configuration incomingPayload
.\gradlew.bat :consumer:resolvePayload
```

Không dùng Bash line continuation trong PowerShell. Demo chỉ minh họa **attributes/candidate selection**; không chạy Java compiler hay tải third-party dependency. Các API configuration roles theo tài liệu Gradle hiện đại; nếu dự án còn Wrapper cũ, cần kiểm tra phiên bản API và nâng theo chính sách thay vì bỏ flags tùy tiện. Không chạy demo trong workspace sản xuất.

## 8. Phân tích ba trạng thái của demo bằng một bảng

| Producer có gì? | Consumer đòi gì? | Các candidate còn tương thích | Kết quả |
| --- | --- | --- | --- |
| east/west, cùng kind=payload | kind=payload; không yêu cầu flavor | east + west | **Ambiguous**, thiếu tiêu chí |
| east/west | kind=payload, flavor=east | east | **Chọn eastElements** |
| east/west | kind=payload, flavor=west | west | **Chọn westElements** |
| east/west | kind=payload, flavor=north | Không có | **No matching variant** |
| Không có consumable variant đúng role/attributes | kind=payload | Không có outgoing variant hợp lệ | **No variants exist** hoặc failure tương ứng |
| Hai consumable variants **trùng cả attributes/capabilities** | kind=payload | Producer model không hợp lệ | Có thể **fail khi kiểm tra outgoing variant model**, khác lỗi ambiguous thông thường |

Bài học rút ra: số variant nhiều **không tự gây lỗi**. Gradle có thể chọn đúng khi attributes hoặc disambiguation rules đủ rõ. Một module có cả `apiElements` và `runtimeElements` là hoàn toàn bình thường nếu consumer và ecosystem phân biệt đúng `org.gradle.usage`.

## 9. Tình huống JVM: producer Java 21, consumer chỉ hỗ trợ Java 17

Đây là **tình huống phân tích** để học cách đọc Gradle error, không phải phần mở rộng bắt buộc của demo phần 7.

```text
Consumer compileClasspath/runtimeClasspath:
  org.gradle.jvm.version = 17
Producer runtimeElements:
  org.gradle.jvm.version = 21
```

Nếu consumer phải chạy được trên Java 17, library đòi JVM 21 không tương thích. Những hướng xử lý:

- **Producer:** nếu code thực sự tương thích Java 17, dùng Java toolchain/release target và publish lại artifact/metadata đúng; cần kiểm chứng bằng test/runtime chứ không chỉ đổi attribute khai báo.
- **Consumer:** nếu business/runtime cho phép, nâng target Java lên 21, cập nhật môi trường CI/server và compatibility Gradle/Java/plugins, rồi kiểm chứng.
- **Dependency choice:** tìm phiên bản library hoặc variant được publisher hỗ trợ cho Java 17; xem `dependencyInsight` để biết version thực sự được chọn.
- **Không sửa giả:** đặt `org.gradle.jvm.version=21` vào consumer nhưng vẫn deploy trên Java 17, hoặc sửa file `.module` để nói bytecode Java 21 là 17. Cách đó chỉ làm Gradle chọn artifact không chạy được.

Một lỗi tương tự có thể xảy ra với **Gradle plugin**: plugin đã publish variant yêu cầu Gradle Plugin API version mới hơn version Gradle Wrapper trong build. Lỗi này khác Java toolchain mismatch. Kiểm tra `./gradlew --version`, Gradle plugin compatibility matrix và thông báo `org.gradle.plugin.api-version` nếu có; chọn plugin version hỗ trợ Wrapper hoặc nâng Wrapper theo quy trình.

## 10. Khi nào sửa ở consumer, khi nào sửa ở producer?

| Quan sát | Nơi sửa ưu tiên | Ví dụ |
| --- | --- | --- |
| Consumer thiếu custom flavor để chọn một trong nhiều variants | Consumer resolvable configuration/dependency attributes | Yêu cầu `flavor=east` |
| Consumer yêu cầu feature/JVM/usage không được producer hỗ trợ | Nhu cầu consumer **hoặc** producer publication tùy hợp đồng thật | Chọn variant được hỗ trợ hoặc publish variant mới |
| Producer chỉ tạo `canBeResolved`, không tạo `canBeConsumed` | Producer build logic | Tạo consumable configuration đúng role |
| Producer công bố hai variants trùng attributes/capabilities | Producer | Tách attributes có ý nghĩa hoặc bỏ variant dư |
| Producer publish thiếu Gradle Module Metadata về variants | Publisher hoặc metadata rule có kiểm chứng | Sửa `maven-publish`/`java-library`; rule cho legacy module |
| Consumer yêu cầu sai `category=platform`/`library` | Consumer dependency notation | Dùng `platform(...)` đúng khi module thực sự là BOM/platform |
| Multiple compatible variants có default nghiệp vụ nhất quán | Attribute schema/convention plugin | `AttributeDisambiguationRule` có kiểm thử |
| Hai modules trong graph cùng cấp một capability | Consumer graph/policy | Chọn đúng implementation hoặc capabilities resolution rule |
| Plugin không chạy trên Gradle Wrapper hiện có | Build tools/versioning | Nâng Wrapper hoặc chọn plugin version hỗ trợ |

Đừng sửa cả hai phía cùng lúc khi chưa biết nguyên nhân: bạn sẽ không xác định được thay đổi nào thực sự giải quyết vấn đề.

## 11. Compatibility rules và disambiguation rules: không lạm dụng

### 11.1. Compatibility nghĩa là gì?

`AttributeCompatibilityRule<T>` quyết định liệu một value producer có được chấp nhận cho một request value consumer hay không. Nó **không có nhiệm vụ chọn** giữa hai candidate đã cùng tương thích.

Ví dụ nghiệp vụ **chỉ là mô hình**: consumer `flavor=stable` có thể cho phép producer `stable` và `lts`. Nếu khai báo compatibility rule cho phép cả hai, bạn lại cần một cách chọn **một trong hai** khi cả hai tồn tại.

### 11.2. Disambiguation nghĩa là gì?

`AttributeDisambiguationRule<T>` quy định preference khi đã có nhiều giá trị ứng viên tương thích. Ví dụ, nếu một tổ chức luôn ưu tiên `lts` cho consumers không yêu cầu flavor, một rule có thể làm default lựa chọn. Nhưng:

- Rule phải áp dụng trên **attribute được đăng ký trong attributes schema** của đúng resolution context.
- Rule phải có policy nghiệp vụ rõ và kiểm chứng rằng không phá nhu cầu của consumers khác.
- Rule không thể làm một variant **vốn không tương thích** bỗng phù hợp nếu không có compatibility rule.
- Không nên sửa JVM compatibility rules chuẩn chỉ để chọn JAR mà build hiện đang fail.
- Khi producer và consumer kiểm soát được, yêu cầu attribute tường minh thường dễ đọc, dễ audit hơn custom global rules.

### 11.3. Custom attribute có thể bị quên hoặc khai báo sai kiểu

Một attribute key có tên và kiểu, ví dụ:

```kotlin
val flavor = Attribute.of("com.example.flavor", String::class.java)
```

Nếu một plugin khai báo `String` mà plugin khác khai báo cùng tên với kiểu `Named`, bạn có thể gặp lỗi schema/attribute type chứ không đơn thuần “no matching variant”. Chuẩn hóa attribute definitions trong một convention/binary plugin dùng chung, không viết nhiều bản tự phát của cùng một key. Với attribute kiểu `Named`, tạo value bằng `ObjectFactory.named(...)` theo API thích hợp; không truyền string trực tiếp như mọi trường hợp.

## 12. Capability: khi lỗi trông giống variant mismatch nhưng bản chất khác

**Capability** mô tả chức năng mà một component/variant cung cấp. Hai module khác GAV có thể cung cấp **cùng một capability**, ví dụ hai logging implementations. Gradle có thể fail vì **capability conflict** nếu graph chứa cả hai implementation cùng chức năng.

Đây **không phải cùng lỗi** với “hai variants tương thích của cùng một producer mà Gradle không chọn được”.

| Trường hợp | Ý nghĩa | Biện pháp đúng |
| --- | --- | --- |
| Hai variants cùng module, đều matching attributes | Ambiguous variant selection | Thêm yêu cầu attribute, disambiguation rule hoặc sửa publication |
| Consumer `requireCapability(...)` nhưng variant không cung cấp | Capability requirement không được thỏa | Yêu cầu đúng capability hoặc publisher công bố đúng feature |
| Hai modules trong graph cùng capability | Capability conflict | Chọn implementation hoặc dùng capabilities resolution theo policy |
| Hai consumable variants có attributes/capabilities giống hệt | Producer model không phân biệt hợp lệ | Sửa attributes/capability hoặc xóa variant thừa |

Với capability conflict thực sự, Gradle có API `capabilitiesResolution.withCapability(...)` và `select(...)`/`selectHighestVersion()`. Nhưng **không dùng `selectHighestVersion()` vô điều kiện**: với logging frameworks, phiên bản cao nhất chưa chắc là implementation đúng. Quyết định cần dựa vào ứng dụng/consumer, kiểm tra runtime và tránh nhiều binding cùng classpath.

Nếu feature được publisher biểu diễn bằng capability riêng, consumer có thể viết `requireCapability("group:feature")` trên dependency theo API Gradle tương ứng. Tuy nhiên, **capability không thay thế attributes** mô tả target JVM, usage hoặc artifact format. Một variant có capability đúng vẫn có thể bị loại vì attributes không tương thích.

## 13. Gradle Module Metadata và giới hạn Maven POM/Ivy

Các variants có attributes/capabilities phong phú được thể hiện tốt nhất trong **Gradle Module Metadata**. Maven POM chủ yếu diễn đạt Maven scopes và dependencies; Gradle có thể **derive variants** từ metadata Maven, nhưng không thể giả định POM chứa đầy đủ custom attribute `com.example.flavor` hoặc mọi feature variant đã publish.

Vì vậy nếu project dependency `project(":producer")` chạy được nhưng consumer bên ngoài tải GAV từ Maven repository lại không chọn được variant:

1. Xem producer đã publish `.module`/POM như thế nào.
2. Kiểm tra repository có phục vụ đúng metadata và Gradle consumer có đọc nó không.
3. Đảm bảo version/artifact được publish đồng bộ, không còn bản legacy stale.
4. Nếu module legacy không thể sửa, cân nhắc **component metadata rules** để bổ sung attribute/capability có căn cứ; nhớ những rules này là logic của consumer, không phải sửa metadata tại nhà phát hành.
5. Không ép `@jar` hoặc file dependency để “bỏ qua lỗi variant” mà không xét transitive dependencies, vì artifact-only notation có thể bỏ metadata và chọn sai behavior.

**Cẩn thận:** error report về một file thiếu không đồng nghĩa attribute mismatch. Nếu variant đã được chọn nhưng artifact URL 404, đó là **artifact retrieval**; kiểm tra repository, checksum, credentials và publication, không chỉnh attribute.

## 14. Các lỗi dễ gặp khi cấu hình tùy chỉnh

### 14.1. Consumer không có attribute nào

Một custom `resolvable` configuration trống attributes có thể gây ra selection không được định hướng hoặc không tham gia variant-aware resolution như bạn kỳ vọng. Hãy khai báo **ít nhất một attribute có ý nghĩa** để nói loại artifact cần lấy; Gradle best practices khuyến nghị cả consumable và resolvable configurations phải có attributes.

Không khắc phục bằng cách gọi trực tiếp `configurations.getByName("...").files` trong configuration để “thử xem có file không”; hành động eager resolution gây lỗi thứ tự cấu hình và làm diagnostics khó hơn.

### 14.2. Producer khai báo nhầm role

Cấu hình được đánh dấu `canBeResolved=true` nhưng `canBeConsumed=false` chỉ để giải quyết input của producer, không phải variant consumable cho project khác. Với custom publication, phải bật đúng `canBeConsumed`, tắt các role không cần, khai báo attributes/artifacts. Nếu producer có output nhưng consumer không thấy, chạy `outgoingVariants` **trên producer**, không dò thư mục build bằng mắt.

### 14.3. Producer có hai consumable configs trùng hết attributes/capabilities

Gradle hiện đại yêu cầu variants đủ khác biệt. Hai configurations có **cùng attributes + capabilities** có thể bị báo lỗi mô hình, trước khi consumer selection diễn ra. Hãy bổ sung **thuộc tính có ý nghĩa thật** thay vì tạo dummy key `com.example.random` chỉ để vượt validator; hoặc hợp nhất publication nếu hai artifacts thực chất là cùng một variant.

### 14.4. Sai tên configuration hoặc gọi report sai project

`./gradlew :producer:outgoingVariants` và `./gradlew :consumer:resolvableConfigurations` khác nhau. Nếu chạy `outgoingVariants` ở root không chứa variants cần xem, sẽ không thấy producer data. Nếu gọi `--configuration implementation` trên Java project, đó không phải configuration resolve mặc định. Dùng `./gradlew projects` và `./gradlew :consumer:tasks --all` để xác nhận đường dẫn task/configuration.

### 14.5. Chỉ sửa version làm thay lỗi này bằng lỗi khác

`force("group:module:version")` hoặc dependency constraints điều khiển **version selection**. Nó không trực tiếp sinh variant với `org.gradle.usage`/`org.gradle.jvm.version` thích hợp. Chỉ đổi version nếu release khác có variant thực sự cần; dùng report giải thích selected version và xem metadata release đó.

### 14.6. Tùy ý tắt transitivity hoặc dùng file dependency

`transitive=false`, `files("library.jar")` và `@jar` có thể khiến Gradle không còn nhìn thấy một số metadata/variants/dependencies, nhưng việc “build qua bước resolve” không chứng minh classpath đúng. Đặc biệt với feature/capability và Java runtime, có thể chuyển lỗi selection thành `ClassNotFoundException` ở runtime. Đừng coi chúng là cách chữa mặc định.

## 15. Quy trình điều tra trong một build thực

**Bước 1 — giữ nguyên thông báo đầu tiên.** Chạy lại với Gradle Wrapper và configuration chính xác. Lưu đoạn nêu **consumer was configured to find**, từng variant **incompatible because** hay **cannot choose between**. Không chỉ giữ hai dòng `BUILD FAILED` cuối.

**Bước 2 — xác định consumer configuration.** Đó là `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`, một custom resolvable config hay classpath của Gradle plugin? Sai configuration dẫn đến đọc sai attributes.

**Bước 3 — xác định producer.** Nó là `project(":lib")`, external module GAV hay Gradle plugin? Với project dependency, dùng `:lib:outgoingVariants`; với external module, dùng `dependencyInsight`/metadata từ repository.

**Bước 4 — lập bảng so sánh.** Ghi mỗi attribute consumer yêu cầu, từng candidate của producer và lý do bị loại. Không gộp khả năng tương thích của một thuộc tính với khả năng tương thích tổng thể.

**Bước 5 — phân loại:**

- Không có variant nào tương thích ⇒ sửa **mismatch attribute/capability** hoặc producer publication.
- Còn nhiều variant ⇒ bổ sung **disambiguation** bằng thuộc tính/quy tắc thích hợp.
- Không có outgoing variant ⇒ kiểm tra **producer canBeConsumed/attributes**.
- Capability conflict của hai modules ⇒ chọn implementation theo policy.
- Artifact download fail ⇒ sửa repository/artifact metadata.
- Toolchain fail ⇒ sửa Java toolchain provisioning/version, không chỉ attributes.

**Bước 6 — chọn bản sửa nhỏ và có thể giải thích.** Ví dụ sửa đúng `com.example.flavor` của consumer thay vì đổi attributes toàn bộ configurations hoặc bật một compatibility rule rộng cho mọi library.

**Bước 7 — kiểm chứng hai mức.** Chạy lại lệnh resolution/task đã fail, rồi chạy compile/test/runtime thực tế. Với Java 17 consumer, đừng chỉ nhìn `BUILD SUCCESSFUL` nếu runtime class được publish cho Java 21.

**Bước 8 — kiểm tra publish/CI.** Nếu producer publish bên ngoài, dùng consumer build tách biệt để thử GAV, metadata và variants tải từ Maven repository, không dựa vào local project dependency. Ghi nhận version Gradle Wrapper, Java/toolchain, plugin version và selected graph.

## 16. Bảng troubleshooting nhanh

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng/sửa |
| --- | --- | --- |
| `No matching variant ... Java 17` | Producer chỉ công bố bytecode/JVM target 21 | Xem `org.gradle.jvm.version`, publish Java 17 compatible hoặc nâng runtime có kiểm chứng |
| `Cannot choose between east/west` | Consumer thiếu `flavor` | Thêm attribute rõ ràng hoặc rule có policy |
| `No variants exist` | Producer không có consumable configuration hợp lệ | Kiểm tra `canBeConsumed`, attributes và outgoing artifact |
| `Variant ... incompatible usage` | `java-api` vs `java-runtime`/custom usage sai | Kiểm tra consumer compile/runtime purpose và producer usage |
| `Variant ... incompatible category` | `library` vs `platform`/`verification` | Dùng đúng dependency notation/plugin publication |
| Nhiều variants trùng attributes | Publisher model không phân biệt variants | Sửa attributes/capabilities hoặc gộp variant |
| `No matching capability` | Consumer yêu cầu feature mà producer không cung cấp | Kiểm tra capabilities và metadata publish |
| `Capability conflict` giữa modules | Hai providers cùng cung cấp một chức năng | Chọn đúng implementation, tránh classpath trùng |
| Gradle plugin incompatibility | Plugin yêu cầu Gradle API version cao hơn Wrapper | Kiểm tra `org.gradle.plugin.api-version` và compatibility matrix |
| `No matching toolchains found` | JDK cần cho task chưa cài/provision | Sửa toolchain resolver/setup Java, không đánh đồng variant error |
| Variant match rồi download 404 | Artifact thiếu trên repository | Sửa publishing/repository, không sửa attributes |
| Project dependency pass, Maven GAV fail | Metadata `.module`/POM xuất bản thiếu/khác | Kiểm tra publication và consumer test độc lập |
| `dependencyInsight --all-variants` thiếu dữ liệu | Configuration đã resolve sớm hoặc resolution fail | Dùng producer/consumer reports, kiểm tra plugin eager resolution |
| Hậu quả xuất hiện ở runtime sau `@jar` | Đã bỏ module metadata/transitives | Quay về normal module dependency và publish variants đúng |
| CI fail nhưng local pass | Wrapper/plugin/JDK/metadata repository hoặc init scripts khác | Pin Wrapper, kiểm chứng từ clean runner |
| `outgoingVariants` không hiện variant | Sai project, chưa có consumable config hoặc thiếu attributes | Chạy đúng path, kiểm tra role và producer model |
| `resolvableConfigurations` không có `implementation` | `implementation` thường là bucket, không resolvable | Dùng `compileClasspath`/`runtimeClasspath` |
| Thêm rule làm chọn variant sai | Rule compatibility/disambiguation quá rộng | Giới hạn cho attribute cụ thể, viết test nhiều consumers |

## 17. Checklist nghiệm thu

- [ ] Đã biết **configuration đang resolve** và **producer component đang được chọn**.
- [ ] Có log **consumer requested attributes** và **producer offered variants/capabilities**.
- [ ] Đã phân biệt **no match** với **ambiguity**, không xem cả hai là lỗi “thiếu JAR”.
- [ ] Không dùng variant **name** hoặc thứ tự khai báo làm tiêu chí chọn.
- [ ] Đã dùng `outgoingVariants` đúng project và `resolvableConfigurations` đúng consumer.
- [ ] Đã thử `dependencyInsight --all-variants` khi phù hợp, hiểu giới hạn configuration resolved sớm.
- [ ] Custom configurations có roles `canBeDeclared/canBeResolved/canBeConsumed` và attributes rõ ràng.
- [ ] Nếu sửa Java compatibility, bytecode thực và target runtime/CI cùng phù hợp.
- [ ] Nếu sửa `category`/`usage`/`libraryelements`, không phá semantics của plugin.
- [ ] Capability conflict (nhiều modules) không bị nhầm với ambiguous variants của cùng component.
- [ ] Nếu sửa publisher, metadata/artifacts/variants được publish lại và test bằng consumer bên ngoài.
- [ ] Không dùng `@jar`, `files(...)` hoặc `transitive=false` để giấu lỗi variant selection.
- [ ] Đã chạy lại task thật, compile/test/runtime và CI sạch, không chỉ sửa để report trông đẹp.

## 18. Ghi nhớ

- **Không variant nào phù hợp**: cần tìm **thuộc tính/requirement loại hết candidates**, hoặc producer chưa công bố variant phù hợp.
- **Nhiều variant phù hợp**: cần **thông tin hoặc quy tắc phân biệt**; không chọn theo tên hay dựa vào thứ tự.
- **`outgoingVariants` xem producer**, **`resolvableConfigurations` xem consumer**, **`dependencyInsight --all-variants` giúp giải thích dependency/variant selection**.
- **JVM/usage/category/libraryelements** có quy tắc ecosystem; custom attributes phải được mô hình hóa nhất quán.
- **Capability conflict** thường liên quan nhiều providers cùng chức năng; khác với hai variants của một producer cùng matching.
- **Producer và consumer đều có trách nhiệm**: producer publish đúng variants/metadata; consumer yêu cầu đúng usage/target và capability.
- Đừng đổi attributes cho “pass build” nếu artifact đã chọn không chạy đúng trên môi trường thật.

## Tài liệu chính thức

- [Gradle — Variant Selection and Attribute Matching](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): cơ chế compatibility, disambiguation và reports của hai phía.
- [Gradle — Variants and Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html): JVM attributes và cách khai báo custom attributes/rules.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencyInsight` và `--all-variants`.
- [Gradle — Best Practices for Dependencies](https://docs.gradle.org/current/userguide/best_practices_dependencies.html): vai trò configuration, attributes bắt buộc và anti-pattern.
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): `canBeDeclared`, `canBeResolved`, `canBeConsumed`.
- [Gradle — Capabilities](https://docs.gradle.org/current/userguide/component_capabilities.html): xung đột cùng capability và giải pháp.
- [Gradle — Supported Metadata Formats](https://docs.gradle.org/current/userguide/supported_metadata_formats.html): POM, Ivy và Gradle Module Metadata.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): Java runtime/toolchain configuration.
