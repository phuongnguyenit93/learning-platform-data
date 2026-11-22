# Capabilities và xử lý xung đột nhiều thư viện cùng chức năng trong Gradle

Một ứng dụng Java có thể kéo vào **hai thư viện khác tọa độ Maven nhưng cùng đảm nhiệm một chức năng**: hai SLF4J providers, hai cầu nối logging, hai backend cho cùng một SPI, hoặc một thư viện cũ và module thay thế mới. Vì có **group/name khác nhau**, cơ chế chọn version thông thường không tự kết luận chúng loại trừ nhau. Kết quả có thể là nhiều provider, class trùng, thứ tự nạp khó đoán hoặc hành vi runtime không nhất quán.

Gradle giải quyết bài toán bằng **capability**: một định danh cho biết một component/variant **cung cấp chức năng gì**. Nếu hai components hoặc variants trong cùng đồ thị phân giải cùng tuyên bố cung cấp **một capability** mà không có quy tắc chọn hợp lệ, Gradle phát hiện xung đột và thường **dừng resolution với lỗi** thay vì âm thầm giữ cả hai.

Bài này nằm trong phần *Variant và capability*: tập trung vào ý nghĩa capability, cách gắn capability cho project hoặc external module, cách Gradle nhận biết xung đột, cách chọn một implementation, sự khác nhau với attributes/variants/version conflict, thực hành **Gradle Kotlin DSL + Java 17** không phụ thuộc thư viện ngoài và quy trình chẩn đoán.

## 1. Vấn đề: trùng chức năng nhưng không trùng module

Xét dependency graph giả định:

```text
:app
├── org.example:logging-api:1.0
├── com.vendor:console-backend:2.0
└── org.other:file-backend:3.0
```

Hai backend có thể đều cung cấp `org.example:logging-backend`, dù tên module khác nhau. Nếu chỉ dựa vào tọa độ, Gradle không thể tự suy rằng console backend và file backend **phải chọn một**. Việc chúng cùng nằm trên runtime classpath có thể gây xung đột service provider hoặc hành vi không được ứng dụng thiết kế hỗ trợ.

Một **capability chung** có thể biểu diễn quy tắc:

```text
console-backend ─┐
                 ├── provides org.example:logging-backend
file-backend ────┘

=> cùng một resolved dependency graph chỉ được giữ
   một provider cho capability được khai báo chung
```

Đây là một **ràng buộc logic về chức năng**, không phải luật rằng mọi thư viện cùng category đều bắt buộc loại trừ nhau. Nếu một ứng dụng thực sự được thiết kế để sử dụng **hai database drivers cho hai loại cơ sở dữ liệu**, chúng **không nên** bị gán một capability độc quyền chỉ vì cùng có tên “driver”.

### Bốn khái niệm cần phân biệt

| Khái niệm | Câu hỏi giải quyết | Ví dụ |
| --- | --- | --- |
| **Module coordinate (GAV)** | Đây là module nào và version gì? | `org.slf4j:slf4j-api:2.0.17` |
| **Version conflict** | Hai đường phụ thuộc yêu cầu **cùng một module** ở version khác nhau | `com.acme:core:1.0` và `com.acme:core:2.0` |
| **Variant/attributes** | Cần **phiên bản biến thể nào** của một component theo usage/Java version/feature? | `java-api` so với `java-runtime` |
| **Capability conflict** | Hai **provider khác nhau** cùng cung cấp chức năng phải độc quyền | `simple-backend` và `advanced-backend` cùng cung cấp `org.acme:logging-backend` |

**Không nên dùng “version conflict” để gọi mọi lỗi dependencies.** Version conflict thường được Gradle xử lý theo version selection rules; capability conflict lại yêu cầu chọn **provider** (hoặc variant) phù hợp, không thể chỉ nâng version bừa.

## 2. Định danh capability và capability mặc định

Một capability có bộ ba **(group, name, version)**, chẳng hạn:

```text
group   = org.example
name    = formatter-backend
version = 1.0
```

Trong Gradle, tên group/name cho biết **loại chức năng được cung cấp**, version mô tả **phiên bản của capability**. Nó không bắt buộc trùng với tên artifact hay version của thư viện; nhưng nên có quy ước rõ và nhất quán khi nhiều nhóm cùng mô hình hóa một chức năng.

Mỗi component thông thường có **capability mặc định (implicit/default)** gắn với tọa độ của nó, ví dụ module `org.apache.commons:commons-lang3:3.17.0` mặc định có capability cùng group/name/version đó. Điều này giúp Gradle nhận dạng các variants của cùng component.

Khi muốn khai báo **capability bổ sung**, ví dụ `org.example:formatter-backend:1.0`, có thể gắn vào các **outgoing variants** của project producer. Chú ý: **một khi bạn định nghĩa capability tường minh cho outgoing configuration, hãy khai báo lại capability mặc định nếu muốn giữ nó**. Nếu quên, người tiêu thụ có thể không lựa chọn variant theo capability GAV mặc định như bạn mong đợi.

### Capability không phải annotation Java

Capability không sinh interface, không tự tìm implementation bằng reflection và không đảm bảo hai nhà cung cấp có cùng Java API. Nó là **metadata để Gradle quyết định dependency resolution**.

Để thay thế được nhau ở runtime, các implementation phải **thực sự tương thích** với chức năng tiêu thụ: cùng SPI/API, cấu hình thống nhất và không dựa vào class tên riêng chỉ có trong backend bị loại. Capability giúp **phát hiện/lựa chọn**, nhưng không tự sửa code Java.

## 3. Một component, nhiều variants; một variant, nhiều capabilities

Gradle chọn dependency theo *variant-aware resolution*. Ví dụ Java library thường công bố:

```text
Component: org.example:codec:1.0
  ├── apiElements      [usage=java-api, capability mặc định]
  └── runtimeElements  [usage=java-runtime, capability mặc định]
```

Consumer compile thường chọn `apiElements`; consumer runtime thường chọn `runtimeElements`. Các variants này không phải hai library độc lập được trộn tùy ý trong cùng một resolution graph.

Một component cũng có thể công bố **feature variants**, chẳng hạn một feature `postgresSupport` hoặc `testFixtures` có capability riêng để consumer yêu cầu khi cần. Từ Gradle API, **capabilities nằm trên variants**, không chỉ trên tên project.

| Thứ cần quyết định | Cơ chế chính |
| --- | --- |
| Cần API JAR hay runtime JAR? | Attribute matching, thường `org.gradle.usage` |
| Cần feature `test-fixtures` hoặc `postgres-support`? | Consumer **requireCapability** của feature variant |
| Hai thư viện khác tên cùng cung cấp backend độc quyền? | Cùng capability trên các variants + **capability conflict resolution** |
| Cần bản thư viện Java phù hợp với JVM? | Variant attributes, toolchain/compatibility metadata |
| Muốn chọn một version của cùng module? | Version selection/constraints/platforms |

**Điểm mấu chốt:** `requireCapability` để yêu cầu **variant có capability nhất định** khác với `resolutionStrategy.capabilitiesResolution.withCapability` để **giải quyết cuộc xung đột giữa nhiều candidates**.

## 4. Khi nào thực sự nên tuyên bố capability chung?

Các trường hợp hợp lý:

- **Một backend duy nhất của cùng một SPI**, ví dụ hệ thống quy định mỗi tiến trình chỉ có một formatter backend.
- **Hai cầu nối thay thế nhau** và không thể cùng được nạp mà vẫn giữ ngữ nghĩa, như một số logging bridge modules.
- **Old/new module cùng cung cấp API tương đương** sau khi module được đổi tên hoặc relocate, khi cần phát hiện hai tọa độ cùng lọt vào graph.
- **Feature variants loại trừ nhau**, ví dụ `standard` và `fips` khi tiêu chuẩn của thư viện chỉ cho phép một variant.
- Một library có **nhiều classifiers/feature modes** và consumer cần chọn chế độ cụ thể.

Các trường hợp không nên tự động loại trừ:

- Hai JDBC drivers phục vụ **hai loại database khác nhau** trong cùng ứng dụng.
- Hai logger APIs không chia cùng contract; library tiêu thụ có thể cần cả hai API.
- Hai JSON libraries mà code thực sự sử dụng độc lập cho những use case khác nhau.
- Hai plugin Gradle thực hiện những nhiệm vụ bổ sung cho nhau, không phải provider thay thế.

**Tính “cùng chức năng” phải được xác định bởi hợp đồng kiến trúc**, không chỉ vì tên artifact có chữ `logging` hay `db`. Gán sai capability có thể buộc Gradle loại bỏ một dependency đang cần, dẫn đến lỗi runtime hoặc build không đúng.

## 5. Chu trình giải quyết capability conflict

```text
1. Consumer yêu cầu dependency cho runtimeClasspath
2. Gradle nhận metadata của modules/projects và chọn variants
3. Gradle xây dependency graph + theo dõi capabilities
4. Phát hiện A và B cung cấp cùng capability X
5. Không có rule hợp lệ: resolution FAIL
6. Có rule: chọn một candidate phù hợp
7. Tính lại graph liên quan, loại candidate không được chọn
8. Task tiêu thụ nhận resolved classpath
```

Điều này xảy ra **lúc dependency resolution**, không có nghĩa `build.gradle.kts` được Java compiler đọc như một file mã Java, và cũng không đồng nghĩa với task dependency cycle.

Một dependency graph khác nhau (ví dụ `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`) có thể có **những candidates khác nhau**. Một rule chỉ áp dụng cho `runtimeClasspath` không mặc nhiên áp dụng cho `testRuntimeClasspath` hoặc mọi custom configuration.

Khi không có capability metadata chung, Gradle **có thể không biết** hai library thay thế nhau. Lúc đó cần bổ sung metadata hoặc sửa upstream publication; chỉ gọi `withCapability` mà không có variant nào công bố capability tương ứng sẽ không tự tạo ra xung đột.

## 6. Ví dụ hoàn chỉnh: hai provider Java cùng một SPI

Ví dụ này **không dùng external dependencies**. Nó minh họa Gradle tự phát hiện hai providers trùng capability, sau đó chọn một nhà cung cấp. Java chạy được với Java 17.

Bốn subprojects:

- `:spi`: chỉ công bố interface `MessageFormatter`.
- `:upper`: một implementation đưa text sang chữ hoa.
- `:bracket`: implementation thay thế đặt text trong `[...]`.
- `:app`: chỉ compile với `:spi`, dùng `ServiceLoader` để lấy implementation ở runtime.

Hai implementations **chủ ý loại trừ nhau theo thiết kế bài tập**. Chúng cùng công bố capability `org.example.capdemo:formatter-backend:1.0`. Khi app yêu cầu cả hai, Gradle sẽ báo xung đột cho tới khi thêm resolution rule.

### 6.1. Cấu trúc thư mục

```text
capability-demo/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── spi/
│   ├── build.gradle.kts
│   └── src/main/java/demo/spi/MessageFormatter.java
├── upper/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/demo/provider/UpperFormatter.java
│       └── main/resources/META-INF/services/demo.spi.MessageFormatter
├── bracket/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/demo/provider/BracketFormatter.java
│       └── main/resources/META-INF/services/demo.spi.MessageFormatter
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
```

Bài tập yêu cầu **Gradle Wrapper hợp lệ** và JDK/toolchain 17 thích hợp với Gradle version đang sử dụng. Các file `META-INF/services` là **text files** chứa tên implementation class; chúng rất quan trọng để `ServiceLoader` tìm được provider.

### 6.2. `settings.gradle.kts`

```kotlin
rootProject.name = "capability-demo"
include("spi", "upper", "bracket", "app")
```

Mỗi project có `build.gradle.kts` riêng. Build này không cần repositories vì dependencies đều là project dependencies.

### 6.3. `spi/build.gradle.kts`

```kotlin
plugins {
    `java-library`
}

group = "org.example.capdemo"
version = "1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

### 6.4. `spi/src/main/java/demo/spi/MessageFormatter.java`

```java
package demo.spi;

public interface MessageFormatter {
    String format(String input);
}
```

Đây là public SPI. `:app` biên dịch với `:spi`, nhưng không tham chiếu các class của `:upper` hay `:bracket` trong source Java.

### 6.5. `upper/build.gradle.kts`

```kotlin
plugins {
    `java-library`
}

group = "org.example.capdemo"
version = "1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":spi"))
}

// Hai variants được consumer Java thường sử dụng.
listOf("apiElements", "runtimeElements").forEach { variant ->
    configurations.named(variant) {
        // Giữ capability mặc định của component :upper.
        outgoing.capability("org.example.capdemo:upper:1.0")

        // Cho biết :upper là một formatter backend.
        outgoing.capability("org.example.capdemo:formatter-backend:1.0")
    }
}
```

**Vì sao cần cả hai dòng `outgoing.capability`?**

- Dòng `org.example.capdemo:upper:1.0` giữ **implicit/default identity capability** của project khi chúng ta đã cấu hình capabilities tường minh.
- Dòng `org.example.capdemo:formatter-backend:1.0` là **chức năng chung** sẽ xung đột với `:bracket`.
- Gắn capability vào **cả `apiElements` và `runtimeElements`** giúp compiler/runtime consumers nhìn thấy thông tin đúng ở những variants tương ứng.

Các dòng `outgoing.capability` không tự tạo JAR hoặc class Java; nhiệm vụ đó vẫn do Java plugin và source code thực hiện.

### 6.6. `upper/src/main/java/demo/provider/UpperFormatter.java`

```java
package demo.provider;

import demo.spi.MessageFormatter;
import java.util.Locale;

public final class UpperFormatter implements MessageFormatter {
    @Override
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

### 6.7. File dịch vụ trong module `:upper`

Tạo **`upper/src/main/resources/META-INF/services/demo.spi.MessageFormatter`**, nội dung **chính xác**:

```text
demo.provider.UpperFormatter
```

Tên file phải khớp tên fully qualified của interface `demo.spi.MessageFormatter`. Nội dung phải khớp tên class implementation đã biên dịch. Đây là giao ước của Java `ServiceLoader`.

### 6.8. `bracket/build.gradle.kts`

```kotlin
plugins {
    `java-library`
}

group = "org.example.capdemo"
version = "1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":spi"))
}

listOf("apiElements", "runtimeElements").forEach { variant ->
    configurations.named(variant) {
        // Giữ capability riêng theo component GAV.
        outgoing.capability("org.example.capdemo:bracket:1.0")

        // Cùng capability với :upper => mutual exclusion.
        outgoing.capability("org.example.capdemo:formatter-backend:1.0")
    }
}
```

Khác biệt giữa hai modules là **capability mặc định** (`upper` so với `bracket`); capability chung (`formatter-backend`) hoàn toàn giống nhau về group/name, với version `1.0`.

### 6.9. `bracket/src/main/java/demo/provider/BracketFormatter.java`

```java
package demo.provider;

import demo.spi.MessageFormatter;

public final class BracketFormatter implements MessageFormatter {
    @Override
    public String format(String input) {
        return "[" + input + "]";
    }
}
```

### 6.10. File dịch vụ trong module `:bracket`

Tạo **`bracket/src/main/resources/META-INF/services/demo.spi.MessageFormatter`**:

```text
demo.provider.BracketFormatter
```

Hai modules `:upper` và `:bracket` có thể cùng tồn tại **trong repository** và cùng được biên dịch độc lập. Xung đột chỉ xảy ra khi **cùng resolved dependency graph** cố chọn cả hai providers có cùng capability.

### 6.11. `app/build.gradle.kts`: cố tình yêu cầu cả hai

```kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.app.Main")
}

dependencies {
    // Chỉ có hợp đồng SPI trên compile classpath của ứng dụng.
    implementation(project(":spi"))

    // Hai provider thay thế nhau được yêu cầu ở runtime.
    runtimeOnly(project(":upper"))
    runtimeOnly(project(":bracket"))
}
```

**Tại sao dùng `runtimeOnly`?** `:app` không import `UpperFormatter` hoặc `BracketFormatter`; nó chỉ dùng `MessageFormatter`. Các providers được nạp ở runtime bằng `ServiceLoader`, vì vậy không cần có trên main compile classpath của app.

### 6.12. `app/src/main/java/demo/app/Main.java`

```java
package demo.app;

import demo.spi.MessageFormatter;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        MessageFormatter formatter = ServiceLoader
                .load(MessageFormatter.class)
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("No formatter provider"));

        System.out.println("Result: " + formatter.format("gradle"));
    }
}
```

`Main.java` có thể compile chỉ nhờ `:spi`. Khi thực thi, `ServiceLoader` dùng service configuration resources để tìm implementation. Nếu không có provider runtime hợp lệ, code sẽ ném lỗi `No formatter provider`.

**Không dựa vào thứ tự `findFirst()` khi có hai providers.** Bài tập cố tình dùng API này để dễ xem sự khác biệt, nhưng trong ứng dụng thực, thứ tự classpath/service lookup không phải cơ sở đáng tin để quyết định provider nghiệp vụ. Đó là lý do capability bắt buộc chọn một implementation.

## 7. Bước 1 của thực hành: quan sát lỗi capability conflict

Từ root project, chạy trên Linux/macOS:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:run --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat :app:dependencies --configuration runtimeClasspath
.\gradlew.bat :app:run --console=plain
```

Khi Gradle giải `:app:runtimeClasspath`, nó phát hiện:

```text
project :upper   provides org.example.capdemo:formatter-backend:1.0
project :bracket provides org.example.capdemo:formatter-backend:1.0

=> Cannot choose both candidates for the same capability
```

Khối trên là **diễn giải ý nghĩa lỗi**, không phải cam kết chuỗi thông báo đúng từng ký tự. Trong báo cáo `dependencies`, Gradle có thể hiện `FAILED` và thông tin capability conflict; lệnh `:app:run` thường thất bại khi giải classpath, **trước khi Java main chạy**. Vì vậy không có stdout `Result: ...` từ chương trình ở bước này.

**Chú ý:** Task `dependencies` là công cụ báo cáo: có trường hợp nó hiển thị các dependency `FAILED` thay vì trả exit code failure giống task `run`. Hãy đọc nội dung báo cáo, không chỉ xem exit code.

### Kiểm tra producer variants

```bash
./gradlew :upper:outgoingVariants --variant runtimeElements
./gradlew :bracket:outgoingVariants --variant runtimeElements
```

Trong phần `Capabilities` của mỗi `runtimeElements`, bạn cần thấy capability riêng của project **và** capability chung `formatter-backend`. Lệnh `outgoingVariants` không sửa project; nó cho biết những variants/capabilities mà project sẵn sàng xuất cho consumers.

## 8. Bước 2: chỉ định provider được chọn

Để **chọn `:upper`** khi có xung đột, thêm đoạn sau vào **cuối file `app/build.gradle.kts`** (các phần khác giữ nguyên):

```kotlin
import org.gradle.api.artifacts.component.ProjectComponentIdentifier

// Chỉ áp dụng cho runtimeClasspath của :app ở ví dụ.
configurations.named("runtimeClasspath") {
    resolutionStrategy.capabilitiesResolution
        .withCapability("org.example.capdemo:formatter-backend") {
            val winner = candidates.firstOrNull { candidate ->
                val component = candidate.id
                component is ProjectComponentIdentifier &&
                    component.projectPath == ":upper"
            }

            if (winner != null) {
                select(winner)
                because("Use one formatter backend: :upper")
            }
        }
}
```

**Lưu ý về `import`:** trong `build.gradle.kts`, dòng import phải đặt **trên cùng**, trước `plugins`. Khi thêm đoạn này, di chuyển `import org.gradle.api.artifacts.component.ProjectComponentIdentifier` lên đầu file; chỉ đặt **khối `configurations.named(...)`** ở cuối.

Giải thích:

- `withCapability("org.example.capdemo:formatter-backend")`: áp dụng policy **cho capability có group/name đó**, không cần ghi version trong đối số.
- `candidates`: tập variants/components thực sự đang tranh cùng capability trong graph.
- `ProjectComponentIdentifier` và `projectPath == ":upper"`: nhận diện đúng project provider, không so sánh chuỗi log khó kiểm soát.
- `select(winner)`: chọn một candidate **đang tồn tại trong conflict candidates**.
- `because(...)`: ghi lý do có ý nghĩa để người đọc báo cáo dependency hiểu vì sao chọn provider này.
- Nếu `:upper` không có trong candidates, ví dụ **không chọn bừa** `:bracket`; conflict sẽ tiếp tục yêu cầu chính sách xử lý đúng.

Sau khi thêm policy, chạy:

```bash
./gradlew :app:run --console=plain --quiet
```

Nếu các file Java và service descriptors chính xác, stdout **của Java main**:

```text
Result: GRADLE
```

`UpperFormatter` dùng `toUpperCase(Locale.ROOT)`, nên `"gradle"` trở thành `"GRADLE"`. `:bracket` không được chọn trên app runtimeClasspath cho capability độc quyền này.

Với Gradle Wrapper, JDK và plugins chuẩn phù hợp, build sẽ nạp provider Java đúng. Output **console của Gradle** có thể chứa log riêng dù có `--quiet`; khối trên là dòng ứng dụng in ra.

### Cách thử chọn `:bracket`

Đổi điều kiện:

```kotlin
component.projectPath == ":bracket"
```

và đổi `because` tương ứng. Chạy `:app:run`, stdout chương trình sẽ là:

```text
Result: [gradle]
```

Đây là kiểm chứng rằng **capability resolution đổi library trên runtime classpath**, không phải đổi source code `Main.java`.

## 9. Đừng nhầm `select`, `selectHighestVersion` và `requireCapability`

| API | Ý nghĩa | Trường hợp hợp lý |
| --- | --- | --- |
| `resolutionStrategy.capabilitiesResolution.withCapability("g:n") { select(candidate) }` | Có conflict: chọn **một ứng viên cụ thể** | Muốn logger/backend được phê duyệt |
| `withCapability("g:n") { selectHighestVersion() }` | Có conflict: chọn ứng viên có **capability version cao nhất** | Old/new library là các bản thay thế tương thích và version scheme đáng tin |
| `capabilities { requireCapability("g:n") }` trong một dependency declaration | Yêu cầu **variant có capability đã chỉ định** ở component đó | Chọn feature `test-fixtures`, `db-support`... |
| `components.withModule<Rule>("g:m")` hoặc `components.all<Rule>()` | Sửa/hoàn thiện metadata variants trước resolution | External modules thiếu thông tin capability |

**`selectHighestVersion()` không đồng nghĩa chọn module có artifact version cao nhất theo mọi trường hợp.** Capability version là dữ liệu riêng và có thể không phản ánh chất lượng/khả năng tương thích giữa hai implementations. Ví dụ chọn logging provider theo version `4.0` thay vì provider đã được kiến trúc phê duyệt phiên bản `2.0` có thể là lựa chọn sai.

Nếu mục tiêu là **loại trừ chính xác một implementation không được phép**, hãy chọn candidate bằng API và ghi `because`. Không đặt một rule `selectHighestVersion()` toàn cục cho mọi capability conflict nếu không hiểu hậu quả.

### `requireCapability` phục vụ yêu cầu feature variant

Ví dụ **mảnh ghép** tiêu thụ một feature do producer publish:

```kotlin
dependencies {
    implementation("org.example:client:1.0") {
        capabilities {
            requireCapability("org.example:client-json-support")
        }
    }
}
```

Đoạn trên chỉ chạy khi artifact/variant tương ứng có tồn tại thật; tọa độ `org.example:client:1.0` là **giả định minh họa**. Nó yêu cầu một feature đặc biệt từ component, **không tự chọn** giữa hai external modules khác nhau chỉ vì có chung chức năng.

## 10. Capability conflict và version conflict không phải một

Hai yêu cầu:

```text
org.demo:core:1.0
org.demo:core:2.0
```

là **hai version của cùng module**. Gradle có version conflict resolution riêng (constraints, platforms, strict versions, selection rules).

Hai yêu cầu:

```text
org.vendor:logging-backend-A:1.0
org.other:logging-backend-B:3.0
```

là **hai modules khác tên**, và sẽ không tự được nhận dạng là mutually exclusive nếu thiếu capability metadata chung.

Phải phân biệt cách sửa:

- **Version conflict**: kiểm tra `dependencyInsight`, constraints/BOM, rich versions và compatibility.
- **Capability conflict**: kiểm tra những components công bố capability nào, chọn đúng **implementation/variant** hoặc sửa metadata.
- **Classpath duplicate classes nhưng không có capability conflict**: có thể cần gắn capability phù hợp cho external modules hoặc xử lý duplicated/shaded artifacts theo bản chất.
- **Task dependency cycle**: hoàn toàn khác; dùng task graph/`--dry-run`, không dùng capability resolution để sửa.

Không dùng `force("module:version")` để giả vờ giải quyết hai **modules khác tên** cung cấp cùng functionality: force version của một module không xác định component provider thay thế nào cần loại bỏ.

## 11. External modules thiếu capability metadata: Component Metadata Rules

Không phải tất cả thư viện xuất bản qua Maven POM đều khai báo capabilities. Maven POM có thể mô tả group/name/version và dependencies nhưng **không có trường tương đương đầy đủ cho Gradle capabilities**. Một thư viện có thể bị phát hành từ trước khi Gradle feature metadata được hỗ trợ.

Gradle cho phép **component metadata rule** bổ sung capability vào các variants của external modules **sau khi tải metadata nhưng trước khi resolve**.

Một ví dụ nổi tiếng: hai thư viện `log4j:log4j` và `org.slf4j:log4j-over-slf4j` thay nhau cung cấp bridge/API Log4j 1.x. Nếu cả hai được đưa vào graph, chúng có thể cạnh tranh cùng lớp/hợp đồng thay vì hoạt động độc lập. Ta có thể đánh dấu capability `org.example.legacy:log4j-bridge` cho cả hai để Gradle phát hiện.

### Ví dụ rule Kotlin DSL minh họa (không phải chương trình Java)

```kotlin
import org.gradle.api.artifacts.ComponentMetadataContext
import org.gradle.api.artifacts.ComponentMetadataRule

abstract class LegacyLog4jBridgeRule : ComponentMetadataRule {
    override fun execute(context: ComponentMetadataContext) {
        val id = context.details.id
        val legacy = id.group == "log4j" && id.name == "log4j"
        val bridge = id.group == "org.slf4j" &&
            id.name == "log4j-over-slf4j"

        if (legacy || bridge) {
            context.details.allVariants {
                withCapabilities {
                    addCapability(
                        "org.example.legacy",
                        "log4j-api-bridge",
                        id.version
                    )
                }
            }
        }
    }
}
```

Đăng ký rule trong build script Java project, **sau `plugins`**, với `imports` ở đầu:

```kotlin
dependencies {
    components {
        withModule<LegacyLog4jBridgeRule>("log4j:log4j")
        withModule<LegacyLog4jBridgeRule>("org.slf4j:log4j-over-slf4j")
    }
}
```

Ở đây capability group/name `org.example.legacy:log4j-api-bridge` chỉ là tên **do bài học quy ước**, không phải một capability có sẵn được Gradle tự áp dụng cho mọi phiên bản của hai thư viện. Rule **không thêm dependency**; nó chỉ gắn capability vào metadata của các modules **nếu chúng thực sự được yêu cầu** trong resolved graph.

Nếu graph có cả hai providers và chúng công bố cùng capability sau khi sửa metadata, Gradle phát hiện conflict. Bạn có thể dùng `capabilitiesResolution.withCapability("org.example.legacy:log4j-api-bridge") { ... }` để chọn provider được chấp thuận.

**Không chạy các thư viện Log4j 1.x cũ trong production để học khả năng này.** Ví dụ là một trường hợp lịch sử về metadata và tương thích API; project thực tế phải chọn logging stack và phiên bản đang được hỗ trợ, giải quyết lỗ hổng an toàn theo chính sách dự án.

### Lưu ý thiết kế metadata rule

- Hạn chế phạm vi bằng `withModule` cho module cụ thể; không áp dụng `components.all<Rule>()` toàn cục nếu không cần.
- Chỉ dùng rule khi **metadata thiếu hoặc sai**; ưu tiên sửa/upstream publish đúng metadata nếu bạn sở hữu thư viện.
- Rules thay đổi **variant metadata**, nên ảnh hưởng cả selection và diagnostics, không chỉ thay tên một dòng.
- Đảm bảo metadata rule **không phụ thuộc trạng thái ngẫu nhiên**, và dùng dạng isolated/cacheable phù hợp với phiên bản Gradle nếu đưa vào build lâu dài.
- Sửa metadata không tự kiểm tra hai JAR có thực sự tương đương ABI hay compatible behavior; đội phát triển chịu trách nhiệm về mô hình chức năng.

Các bản Gradle hiện đại cung cấp `@CacheableRule` cho component metadata rules được thiết kế đúng; với bài thực hành, trước tiên cần hiểu tính đúng đắn của rule và không thêm logic side effect.

## 12. Gắn capability cho chính project/library bạn phát triển

Với một Java library producer, Gradle docs đưa ra mẫu khai báo trên **outgoing configurations**:

```kotlin
configurations {
    named("apiElements") {
        outgoing.capability("com.example:my-library:1.0")
        outgoing.capability("com.example:shared-service:1.0")
    }
    named("runtimeElements") {
        outgoing.capability("com.example:my-library:1.0")
        outgoing.capability("com.example:shared-service:1.0")
    }
}
```

Đây là **mảnh ghép Gradle Kotlin DSL** dành cho một Java library có `group/name/version` tương ứng; không phải file độc lập nếu chưa khai báo plugin, source và project. Ký hiệu `com.example:my-library:1.0` là **capability riêng**; `com.example:shared-service:1.0` là capability thêm.

Đặt capability lên `apiElements` và `runtimeElements` vì đây là hai variants consumer Java thường lựa chọn. Nếu chỉ đặt trên `runtimeElements`, conflict có thể được phát hiện khi resolve runtimeClasspath nhưng không phát hiện giống vậy ở compileClasspath — điều đó có thể đúng hoặc sai tùy contract. Với backend **chỉ tồn tại ở runtime**, có thể chủ động gắn capability vào runtime variants khi muốn giữ các provider artifacts trên compile graphs; với library thay thế toàn diện, thường cần xem xét cả API và runtime variants.

**Khả năng khác:** có thể dùng `java.registerFeature(...)` để đăng ký feature variant với capability khác (ví dụ `java-test-fixtures`), khi API/feature độc lập thực sự được publish. Không phải mọi tính năng nên được tạo thành một module riêng.

### Capabilities khi publish

Capabilities được Gradle Module Metadata biểu diễn giàu thông tin, còn **Maven POM không có cơ chế tương đương đầy đủ**. Vì thế nếu consumer chỉ đọc POM/Ivy metadata, có thể **mất thông tin capability** và không được bảo vệ khỏi conflict như Gradle-to-Gradle resolution có metadata.

Nếu một thư viện hỗ trợ nhiều build tools, cần test publication trong bối cảnh consumer thực. Khi cần, áp dụng metadata rules ở phía Gradle consumer để khôi phục thông tin exclusivity phù hợp.

## 13. Quy tắc chọn: global hay theo từng configuration?

Ví dụ ở phần 8 chỉ áp dụng cho `:app:runtimeClasspath`. Bạn có thể có **`testRuntimeClasspath`** chứa các providers khác hoặc config riêng cho integration tests.

Một quy tắc rộng hơn trong project:

```kotlin
configurations.configureEach {
    resolutionStrategy.capabilitiesResolution
        .withCapability("org.example.capdemo:formatter-backend") {
            // Chọn candidate theo chính sách kiến trúc.
            // Không gọi select nếu không có ứng viên hợp lệ.
        }
}
```

Đây là **minh họa phạm vi**, không phải policy có thể chạy độc lập vì thiếu logic chọn. Nếu muốn áp dụng trên nhiều configurations, hãy **lặp lại cùng tiêu chí chọn đã kiểm tra** và hiểu rằng candidates của compile/test/runtime có thể khác nhau. Nếu đẩy rule vào convention plugin dùng chung, viết test đảm bảo nó không vô tình loại bỏ provider trong các source sets khác.

Các cách chọn:

1. **Theo project/module đã được phê duyệt**: `select(candidate)` khi candidate nằm trong `candidates`.
2. **Theo capability version**: `selectHighestVersion()` khi semver/versioning của **chính capability** có ý nghĩa so sánh giữa providers.
3. **Không tự chọn**: giữ lỗi conflict và yêu cầu người tiêu thụ chủ động quyết định; thường là lựa chọn an toàn cho libraries đa mục đích.

Chỉ nên `select("group:artifact")` với notation mà Gradle chấp nhận và **đúng candidate hiện diện**. Một string không có trong graph **không tự thêm dependency mới**. Để giảm nhầm lẫn giữa external modules và project components, dùng `candidates` và `select(candidate)` theo API, như ví dụ bài thực hành.

## 14. Xung đột capability và `exclude`/substitution

Khi hai providers cùng hiện diện, có vài lựa chọn khác nhau:

| Phương án | Thực hiện việc gì? | Khi nào phù hợp? | Hạn chế |
| --- | --- | --- | --- |
| **Capability conflict + select** | Diễn tả 2 modules mutually exclusive, chọn một candidate | Policy có ý nghĩa về provider thay thế | Cần metadata capability và lựa chọn đúng |
| **Exclude transitive dependency** | Bỏ một module trên một đường dependency | Dependency thật sự thừa hoặc metadata upstream sai | Dễ bị kéo lại qua đường khác; có thể loại module cần thiết |
| **Dependency substitution** | Thay một module bằng module/project khác | Di chuyển module hoặc thay hẳn implementation | Là thay identity của dependency, không mô tả chức năng chung |
| **Force version** | Ép version của một module | Vấn đề version của **cùng module** | Không giải quyết cạnh tranh hai modules khác tên |
| **Chỉ khai báo một provider** | Tránh conflict từ đầu | Bạn kiểm soát tất cả dependencies và không có transitive khác | Không phát hiện nếu một dependency khác sau này kéo provider thứ hai |

Trong bài thực hành, phương án đúng và có tính giảng dạy là **khai báo chung capability rồi chọn một candidate**. Trong dự án thực, nếu chỉ một provider được yêu cầu và không có đường transitive thứ hai, bạn có thể không cần rule. Tuy nhiên, metadata vẫn có ích như “guardrail” phát hiện khi cấu hình thay đổi.

**Không dùng `exclude(group = ..., module = ...)` để giấu một lỗi chưa hiểu.** Exclusion không thay thế contract: nếu code cần class từ module bị loại, build có thể compile fail hoặc runtime `NoClassDefFoundError`. Lựa chọn provider phải dựa trên **tính thay thế được** của các implementations.

## 15. Chẩn đoán khi Gradle báo conflict

Các công cụ chính:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency upper
./gradlew :upper:outgoingVariants --variant runtimeElements
./gradlew :bracket:outgoingVariants --variant runtimeElements
./gradlew :app:run --info
```

Chạy trên Windows PowerShell bằng `.\gradlew.bat` thay cho `./gradlew`.

- `dependencies --configuration runtimeClasspath`: xem **resolved dependency graph** và các module FAIL do conflict.
- `dependencyInsight`: nếu graph giải được hoặc báo cáo có thông tin đủ, xem module đến từ đường nào, variant/selection reason. Với graph đang conflict chưa resolve, một số báo cáo có thể không đủ và cần xem lỗi chính.
- `outgoingVariants`: cách trực tiếp để kiểm tra **capabilities do một project producer công bố**.
- `--info`: thêm chi tiết task/resolution, nhưng không tự sửa lỗi.
- `--stacktrace`: hữu ích khi lỗi xuất hiện qua plugins/CI và bạn cần xác định nơi exception phát sinh.

**Đừng dùng `./gradlew tasks --all` để kết luận capability conflict:** lệnh đó liệt kê tasks, không phản ánh classpath cụ thể; nhiều configurations chỉ được resolve khi task cần file.

### Quy trình 7 bước

1. **Tái hiện** bằng đúng Gradle Wrapper, module, configuration và lệnh CI/IDE đang dùng.
2. **Đọc lỗi**: phân biệt capability conflict với version conflict, no matching variant, missing artifact hoặc duplicate class runtime.
3. **Xem graph** `dependencies --configuration ...` để thấy hai providers đến trực tiếp hay qua transitive dependencies.
4. **Kiểm tra metadata** producer (`outgoingVariants`) hoặc external component metadata rule/published Gradle Module Metadata.
5. **Xác nhận exclusivity**: hai artifacts có thật sự cùng API/SPI hoặc mutually exclusive không? Nếu không, phải sửa capability modelling, không ép chọn một.
6. **Chọn giải pháp**: sửa upstream metadata, bỏ dependency thừa, `withCapability { select(...) }` hoặc redesign feature usage.
7. **Kiểm thử đầy đủ**: compile, unit/integration tests, runtime startup, packaging và classpath ở các configurations liên quan; tránh kết luận chỉ từ resolution PASS.

Sau khi giải quyết xung đột trong `:app:runtimeClasspath`, hãy thử các đường khác cần provider, ví dụ `:app:testRuntimeClasspath`, để tránh khác biệt giữa test và production. Nếu application có worker processes/CLI riêng, kiểm tra cả distribution thực tế.

## 16. Thông báo lỗi có thể nói gì?

Một lỗi mô tả:

```text
Cannot select module A because it conflicts with capability
'org.example.capdemo:formatter-backend:1.0'
also provided by module B.
```

đã cho ba thông tin:

1. Có **các providers khác nhau** đang cạnh tranh một capability.
2. Capability group/name/version nào xuất hiện trong metadata.
3. Gradle cần một quyết định: sửa graph hoặc **chọn provider**.

Đây là **bản mô phỏng nội dung chẩn đoán**, không phải output nguyên văn cho mọi phiên bản Gradle. Nếu lỗi là `No matching variant`, không nên ngay lập tức dùng `selectHighestVersion` vì có thể chính attributes hoặc Java version mismatch, không phải capability conflict.

Một lỗi runtime kiểu:

```text
ServiceConfigurationError: Provider ... not found
```

thường cần kiểm tra các file `META-INF/services`, class names và runtime artifacts. Nó khác capability conflict: Gradle có thể đã chọn đúng provider nhưng JAR của provider bị đóng gói thiếu resource hoặc class.

## 17. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Hai backends vẫn cùng xuất hiện dù chúng xung đột về chức năng | Chưa có shared capability metadata | Gắn capability phù hợp vào variants hoặc dùng component metadata rule |
| Ngay khi thêm capability, project consumer mất khả năng resolve variant mặc định | Khi khai báo explicit capability, đã quên capability mặc định | Khai báo lại GAV capability của producer cùng capability bổ sung |
| `withCapability` được viết nhưng xung đột vẫn không phát hiện | Providers không thực sự công bố capability đó | Kiểm tra `outgoingVariants`/metadata rules và graph đang resolve |
| `selectHighestVersion` chọn backend không mong muốn | Version capability không phản ánh provider ưu tiên | Chọn module/candidate được phê duyệt, ghi `because` |
| `select("A")` không có ứng viên A trong graph | Resolution chỉ chọn giữa candidates có thật | Xem candidates; bổ sung dependency đúng nơi hoặc xử lý conflict khác |
| `requireCapability` không tìm thấy feature | Producer không công bố capability theo group/name đó | Xem feature variant metadata và đúng capability name |
| App compile được nhưng runtime vẫn có hai providers | Capability có trên API variant nhưng thiếu runtime variant | Gắn capability ở variants dùng trong runtime graph |
| Test dùng một backend khác production | Quy tắc chỉ áp dụng `runtimeClasspath`, không áp dụng test runtime | Chủ động cấu hình `testRuntimeClasspath`/test source sets |
| Runtime lỗi `ClassNotFoundException` sau khi chọn một provider | Selected provider không thay thế được module bị loại | Xem SPI/ABI/đường chạy thực tế; sửa modelling hoặc dependency graph |
| Gradle không nhận metadata capability từ Maven POM | POM không biểu diễn đầy đủ Gradle capabilities | Publish Gradle Module Metadata hoặc thêm component metadata rules ở consumer |
| Conflicting `log4j` bridges dù Gradle báo PASS | Chưa mô hình hóa alternative function | Xác định các JAR incompatible và thêm metadata phù hợp, không dựa vào classpath order |
| `force` không giải quyết hai backend | Force chỉ chọn version của cùng module | Dùng capability selection/substitution khi đúng |
| Chạy `dependencies` không thấy task execution order | Dependency graph khác task graph | Dùng `--dry-run` cho tasks, `dependencies` cho libraries |
| App chạy `:upper` nhưng source import `BracketFormatter` | App dùng implementation-specific type ở compile time | Thiết kế lại theo shared SPI hoặc giữ dependency phù hợp, không coi providers interchangeable tùy ý |

## 18. Capabilities không thay thế test runtime và kiểm tra an toàn

Gradle có thể chọn một provider mà build **vẫn lỗi về chức năng**. Một chiến lược kiểm chứng tối thiểu cần gồm:

- **Compile test**: mã client không phụ thuộc implementation-specific classes khi có khả năng thay backend.
- **Service discovery test**: `ServiceLoader` tìm đúng một implementation mong muốn.
- **Behavior test**: hai implementations tuân thủ chung SPI contract với cùng các trường hợp biên.
- **Runtime classpath test**: không còn class trùng hoặc bridges nguy hiểm.
- **Distribution test**: file ZIP/TAR/JAR/launcher thực tế không bỏ sót selected provider.
- **Migration test**: khi đổi provider/version, kết quả tương thích với cấu hình và dữ liệu cũ.

**Gradle capability không phải container bảo mật**: nó không sandbox code, không đánh giá vulnerabilities, không bảo đảm binary compatibility và không kiểm chứng license. Nếu selected provider có lỗi bảo mật, việc chọn đúng capability không làm lỗi đó biến mất.

Khi một library **được người khác tiêu thụ** qua Maven/Gradle, tốt hơn là công bố chuẩn metadata cùng tài liệu “mutually exclusive implementations”, thay vì ép tất cả consumers chọn một implementation bằng một quy tắc không được thảo luận.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `org.example:backend-a:1.0` và `org.other:backend-b:2.0` cùng xử lý một SPI. Gradle tự phát hiện chúng là mutually exclusive chỉ vì tên có chữ `backend` không?

**Đáp:** Không. Gradle cần metadata capability chung hoặc một quy tắc giải quyết khác. Tên module không diễn tả đầy đủ chức năng.

**Câu 2.** Capability khác version conflict thế nào?

**Đáp:** Version conflict là nhiều yêu cầu version của cùng module. Capability conflict là nhiều providers/variants cùng tuyên bố một chức năng, có thể khác cả group/name.

**Câu 3.** Vì sao khi thêm `outgoing.capability("org.example:formatter:1.0")` có thể cần khai báo lại capability GAV mặc định?

**Đáp:** Khi đã định nghĩa capabilities tường minh trên outgoing configuration, capability implicit không còn được giữ tự động theo cách trước đó. Muốn consumer vẫn có thể chọn project theo capability identity mặc định, phải khai báo lại.

**Câu 4.** `requireCapability("org.example:library-extra")` có dùng để giải quyết xung đột giữa hai backend tự do không?

**Đáp:** Không theo nghĩa chính. Nó yêu cầu một **variant/feature capability** ở dependency được chỉ định. Khi nhiều candidates đã cùng capability và gây xung đột, dùng capability resolution strategy để chọn provider.

**Câu 5.** Có nên dùng `selectHighestVersion()` để chọn giữa hai SLF4J providers do hai hãng khác nhau phát hành?

**Đáp:** Không nên mặc định như vậy. Capability versions có thể không đại diện cho mức ưu tiên chức năng, tương thích hoặc chính sách an toàn; nên chọn provider được phê duyệt.

**Câu 6.** Trong bài thực hành, vì sao `:app` có thể compile trước khi resolve runtime conflict?

**Đáp:** App chỉ import `MessageFormatter` từ `:spi`; hai providers là `runtimeOnly`, nên chúng không bắt buộc xuất hiện trên compileClasspath của app.

**Câu 7.** Xung đột trên `:app:runtimeClasspath` đã được xử lý. `testRuntimeClasspath` có tự chắc chắn dùng cùng provider không?

**Đáp:** Không. Mỗi resolvable configuration có graph và rules riêng; cần kiểm tra test runtime và áp dụng policy nhất quán khi cần.

**Câu 8.** Một external POM không có capability metadata. Có thể dùng API nào để gắn capability vào từng variant khi Gradle resolve?

**Đáp:** Component metadata rule với `context.details.allVariants { withCapabilities { addCapability(...) } }`, đăng ký cho các modules liên quan qua `components.withModule`.

**Câu 9.** Tại sao `exclude` toàn bộ backend B để sửa lỗi capability có thể nguy hiểm?

**Đáp:** Nếu B còn cung cấp classes/behavior khác mà A không thay thế được, runtime có thể lỗi. Cần xác nhận tính thay thế và dependency graph thật trước khi loại provider.

**Câu 10.** Lệnh nào cho thấy một project Java công bố capability gì trên runtime variant?

**Đáp:** `./gradlew :project:outgoingVariants --variant runtimeElements`. Để xem consumers đã chọn dependencies ra sao, xem `dependencies --configuration runtimeClasspath` và `dependencyInsight` phù hợp.

## 20. Tóm tắt áp dụng trong thực tế

**Capability là hợp đồng “component/variant này cung cấp chức năng X”.** Hai providers mutually exclusive có cùng capability là một cách giúp Gradle chủ động **từ chối classpath sai**. Sau đó, người cấu hình có thể chọn provider theo chính sách dự án.

Khi làm việc với ứng dụng Java nhiều modules:

1. Thiết kế **API/SPI** chung trước, tránh compile trực tiếp với implementation class nếu muốn thay backend.
2. Xác định **chức năng nào thật sự chỉ được có một provider** trong từng runtime graph.
3. Kiểm tra capability có sẵn trong Gradle Module Metadata; nếu không, bổ sung cho outgoing variants hoặc external metadata rule.
4. Chạy dependency reports để tái hiện và xác minh conflict; không chỉ suy từ build file.
5. Giải quyết bằng một candidate có trong graph với lý do rõ ràng; tránh dùng highest version cho những provider không thể so sánh.
6. Kiểm thử **runtime behavior** ngoài việc resolution thành công và rà cả test/runtime/distribution classpaths.

## Tài liệu chính thức

- [Gradle — Capabilities](https://docs.gradle.org/current/userguide/component_capabilities.html): cơ chế, capability mặc định, outgoing capabilities, external metadata và selection.
- [Gradle — Dependency Constraints and Conflict Resolution](https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html): khác biệt version conflicts và capability conflicts.
- [Gradle — Modifying Dependency Metadata](https://docs.gradle.org/current/userguide/component_metadata_rules.html): component metadata rules, `allVariants`, `withCapabilities`, `addCapability`.
- [Gradle — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): attributes, API/runtime variants, `outgoingVariants`, dependency selection.
- [Gradle — Feature Variants](https://docs.gradle.org/current/userguide/how_to_create_feature_variants_of_a_library.html): `registerFeature`, `capability`, `requireCapability`.
- [Gradle — Using Resolution Rules](https://docs.gradle.org/current/userguide/resolution_rules.html): excludes/substitution và khả năng dùng capabilities.
- [Gradle Kotlin DSL — CapabilitiesResolution](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.artifacts/-capabilities-resolution/index.html): `withCapability` và scope giải quyết.
- [Gradle Kotlin DSL — CapabilityResolutionDetails](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.artifacts/-capability-resolution-details/index.html): `candidates`, `select`, `because`, `selectHighestVersion`.
- [Java 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): cơ chế nạp implementation theo SPI trên classpath.
