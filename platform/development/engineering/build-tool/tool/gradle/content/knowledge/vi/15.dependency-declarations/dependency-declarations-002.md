# `implementation`, `api` và ranh giới API của thư viện Java trong Gradle

Khi xây dựng một thư viện Java có người sử dụng ở module khác, Gradle cần phân biệt hai tập dependency: **những thư viện mà module của bạn dùng để triển khai bên trong** và **những thư viện có kiểu xuất hiện trong giao diện công khai để consumer phải thấy khi biên dịch**. Plugin `java-library` hỗ trợ sự phân biệt này bằng `implementation` và `api`.

Nếu một thư viện công khai method trả về `com.google.gson.JsonObject` nhưng bên trong dùng `org.apache.commons.lang3.StringUtils`, lựa chọn thông thường là:

```kotlin
plugins {
    `java-library`
}

dependencies {
    api("com.google.code.gson:gson:2.13.1")
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Lúc này project tiêu thụ thư viện sẽ nhận Gson trên **compile classpath** theo API contract, nhưng không tự nhận Commons Lang trên compile classpath chỉ vì thư viện dùng nó bên trong. Tuy nhiên, **runtime classpath** của consumer vẫn thường chứa Commons Lang vì mã thư viện cần nó khi chạy.

Bài học này trình bày rõ nguyên lý, các API/ABI boundaries, classpath và Gradle variants, một ví dụ **hai module chạy được với Java 17+ và Gradle Kotlin DSL**, cách thử sai để hiểu tác động, quy tắc xuất bản metadata và các bước chẩn đoán.

## 1. Hai câu hỏi quyết định dependency scope

Với mỗi dependency `X` của một library, hỏi:

1. **Source code của chính library** cần `X` ở lúc biên dịch hoặc lúc thực thi không?
2. **Public contract của library** có sử dụng một kiểu từ `X` mà compiler của consumer cần nhìn thấy không?

Nếu `X` chỉ hỗ trợ method body hoặc internal helper thì thông thường dùng `implementation`. Nếu public method, constructor, superclass, interface, generic signature hay public annotation khiến consumer compiler phải biết một kiểu từ `X`, thì cân nhắc `api` hoặc `compileOnlyApi` nếu chỉ cần compile-time.

### Ví dụ đối chiếu

```java
package demo.catalog;

import com.google.gson.JsonObject;
import org.apache.commons.lang3.StringUtils;

public final class CatalogService {
    // Gson là một phần của public API:
    public JsonObject create(String name) {
        String formatted = StringUtils.capitalize(name);
        JsonObject result = new JsonObject();
        result.addProperty("label", formatted);
        return result;
    }
}
```

- `JsonObject` nằm trong **return type của public method**: Gson là API dependency.
- `StringUtils` nằm trong **method body**: Commons Lang là implementation dependency.
- Không thể quyết định scope chỉ bằng các dòng `import`, mức độ phổ biến của thư viện hay việc thư viện được dùng bao nhiêu lần.

Một dependency có thể thuộc public API dù chỉ xuất hiện một lần trong chữ ký, và vẫn là implementation dependency dù được gọi hàng trăm lần trong private code.

## 2. `java` khác `java-library` ở đâu?

| Gradle plugin | Kotlin DSL | Chức năng |
| --- | --- | --- |
| Java | `plugins { java }` | Source sets, `compileJava`, `test`, `jar`, `implementation`, `compileOnly`, `runtimeOnly`… |
| Java Library | `plugins { `java-library` }` | Bao gồm các khả năng của Java plugin và bổ sung `api`, `compileOnlyApi`, API/runtime variants cho library |

Với một ứng dụng chỉ cần chạy, `application` hoặc `java` thường đã phù hợp. Với một module **công bố thư viện Java** để module/project khác biên dịch dựa trên nó, `java-library` là lựa chọn chuẩn.

`api` **không phải một hàm Kotlin có sẵn ở mọi build script**. Accessor `api("group:module:version")` được Gradle Kotlin DSL cung cấp khi plugin tạo ra configuration `api`. Nếu dùng `plugins { java }` và gọi `api(...)`, có thể gặp lỗi `Unresolved reference: api`; lúc đó cần kiểm tra plugin trước khi kiểm tra Maven Central.

**`java-library` không tự xác định API class dựa trên package name.** Việc đặt lớp vào package `internal` là quy ước thiết kế; không có nghĩa Gradle mặc định ẩn class đó. Ranh giới dependency được mô tả qua public ABI và variants.

## 3. Classpath của chính library và của consumer không giống nhau

Giả sử `:catalog-lib` có:

```kotlin
dependencies {
    api("com.google.code.gson:gson:2.13.1")
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Bảng dưới đây mô tả mô hình Gradle Java Library thông thường khi một consumer dùng `implementation(project(":catalog-lib"))`.

| Nơi dependency được dùng | Gson, khai báo `api` | Commons Lang, khai báo `implementation` |
| --- | --- | --- |
| Compile classpath **của library** | Có | Có |
| Runtime classpath **của library** | Có | Có |
| Compile classpath **của consumer** | **Có** qua API variant | **Không tự xuất hiện** qua library API |
| Runtime classpath **của consumer** | Thông thường có | Thông thường có |

`implementation` **không có nghĩa “chỉ cần lúc biên dịch”**; điều đó gần với `compileOnly`. Nó cũng **không có nghĩa “consumer không bao giờ nhìn thấy JAR”**. Nó che dependency nội bộ khỏi **consumer compile API**, nhưng runtime của consumer vẫn cần những implementation libraries để gọi được code thư viện.

### Vì sao khác nhau?

```text
:catalog-lib (java-library)
    api ---------> Gson
    implementation -> Commons Lang
             |
             |  consumer dùng project(":catalog-lib")
             v
:consumer.compileClasspath
    catalog-lib API variant + Gson

:consumer.runtimeClasspath
    catalog-lib runtime variant + Gson + Commons Lang
```

Đây là sơ đồ **logic**, không phải bản in chính xác của mọi artifact. Một dependency khác của consumer có thể mang Commons Lang vào compile classpath theo đường riêng. Nếu gặp kết quả khác, dùng `dependencies` và `dependencyInsight` để xem dependency graph sau resolution.

## 4. API và ABI: những vị trí làm lộ dependency

ABI (*Application Binary Interface*) là thông tin trong class files mà compiler cần để biên dịch hoặc liên kết code tiêu thụ. Trong Java, public/protected signatures và một số thông tin type/annotation có thể là một phần của ABI.

| Cách dùng kiểu `ExternalType` | Có thể là API dependency? | Lý do |
| --- | --- | --- |
| `public ExternalType get()` | Có | Kiểu trả về public |
| `public void put(ExternalType value)` | Có | Kiểu tham số public |
| `public Api(ExternalType value)` | Có | Constructor public |
| `public List<ExternalType> all()` | Có | Generic argument trong signature |
| `public class Api extends ExternalBase` | Có | Superclass cần cho compiler |
| `public interface Api extends ExternalInterface` | Có | Public superinterface |
| Public field/bound/annotation dùng external type | Có thể có | Compiler cần thấy type metadata |
| ExternalType chỉ dùng trong private method body | Thông thường không | Consumer không phải biên dịch method body |
| ExternalType chỉ dùng làm internal parser/formatter | Thông thường không | Chi tiết triển khai |

**Không nên đơn giản hóa thành “chỉ nhìn chữ public”.** Một số trường hợp Java compiler vẫn cần class file nằm trong dependency mà bạn cho là private, chẳng hạn type annotations trên private members hoặc overload resolution. Tài liệu `java-library` của Gradle nêu rõ ngoại lệ này. Nếu consumer compiler thực sự cần class file đó, đặt dependency vào compile API variant bằng `api` hoặc `compileOnlyApi` khi hợp lý.

Một kiểu bên ngoài xuất hiện trong public contract thường kéo theo **coupling lâu dài**: thay Gson thành Jackson có thể trở thành breaking change nếu người dùng đã compile code dựa vào Gson types.

## 5. Ví dụ hoàn chỉnh: `:catalog-lib` và `:consumer`

Ví dụ dùng **Java 17**, Gradle Kotlin DSL và hai thư viện từ Maven Central. Nó không dùng Spring hay annotation processor, để kết quả phản ánh đúng sự khác biệt giữa hai configuration scopes.

### 5.1. Cấu trúc thư mục

```text
api-boundary-demo/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── catalog-lib/
│   ├── build.gradle.kts
│   └── src/main/java/demo/catalog/CatalogService.java
└── consumer/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
```

Project cần Gradle Wrapper tương thích Java 17 và network hoặc cache để tải dependencies. Nếu chưa có Wrapper, có thể tạo từ Gradle installation phù hợp theo tài liệu chính thức; không nên tự viết các file Wrapper bằng tay.

### 5.2. `settings.gradle.kts`

```kotlin
rootProject.name = "api-boundary-demo"
include("catalog-lib", "consumer")
```

`include` xác định hai subproject paths là `:catalog-lib` và `:consumer`. File settings không khai báo `api` hay `implementation`; dependencies thuộc build scripts/plugins của project.

### 5.3. `catalog-lib/build.gradle.kts`

```kotlin
plugins {
    `java-library`
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    // Gson xuất hiện trong public return type.
    api("com.google.code.gson:gson:2.13.1")

    // Commons Lang chỉ dùng bên trong implementation.
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Đây là library module. Việc cả hai dependency có mặt khi compile library là bình thường; khác biệt nằm ở **consumer-facing compile API**.

### 5.4. `catalog-lib/src/main/java/demo/catalog/CatalogService.java`

```java
package demo.catalog;

import com.google.gson.JsonObject;
import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class CatalogService {
    public JsonObject create(String rawName) {
        String trimmed = StringUtils.trimToEmpty(rawName);
        String label = StringUtils.capitalize(
                trimmed.toLowerCase(Locale.ROOT));

        JsonObject result = new JsonObject();
        result.addProperty("label", label);
        return result;
    }
}
```

- `JsonObject` của Gson xuất hiện trong public method `create`.
- `StringUtils` của Commons Lang chỉ được gọi trong method body.
- `Locale.ROOT` giúp lowercasing không phụ thuộc locale máy chạy.
- `CatalogService` tạo JSON object nhưng việc convert thành output text là do `:consumer`.

### 5.5. `consumer/build.gradle.kts`

```kotlin
plugins {
    application
}

repositories {
    mavenCentral()
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
    // Consumer không tự khai báo Gson hay Commons Lang.
    implementation(project(":catalog-lib"))
}
```

`application` tạo task `run` và áp dụng Java capabilities. Module consumer lấy API dependency thông qua metadata của `:catalog-lib`.

### 5.6. `consumer/src/main/java/demo/app/Main.java`

```java
package demo.app;

import com.google.gson.JsonObject;
import demo.catalog.CatalogService;

public final class Main {
    public static void main(String[] args) {
        CatalogService service = new CatalogService();
        JsonObject item = service.create("  HELLO  ");
        System.out.println(item.get("label").getAsString());
    }
}
```

Consumer **import trực tiếp `com.google.gson.JsonObject`**, dù file `consumer/build.gradle.kts` chỉ khai báo project dependency đến `:catalog-lib`. Đây là hành vi đúng vì Gson thuộc API dependency của producer.

### 5.7. Chạy và kiểm tra

Linux/macOS:

```bash
./gradlew :consumer:compileJava
./gradlew :consumer:run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat :consumer:compileJava
.\gradlew.bat :consumer:run --quiet
```

Khi dependencies có thể được tải và project cấu hình như trên, **stdout do Java `Main` tạo ra** là:

```text
Hello
```

`StringUtils.trimToEmpty("  HELLO  ")` trả `"HELLO"`; `toLowerCase(Locale.ROOT)` trả `"hello"`; `StringUtils.capitalize` trả `"Hello"`. Console Gradle có thể thêm output riêng tùy settings/version, nên không kết luận cả terminal chỉ có đúng một dòng.

Nếu chạy `./gradlew :consumer:jar`, JAR của consumer **không tự đóng gói mọi dependency JAR bên trong**. `run` của Application plugin được cấp runtime classpath; khi phân phối độc lập cần dùng Application distribution hoặc packaging được thiết kế phù hợp. Không dùng điều này để đánh giá sai `api`/`implementation`.

## 6. Thử nghiệm 1: đặt sai Gson vào `implementation`

Trong **`catalog-lib/build.gradle.kts`**, tạm sửa:

```kotlin
api("com.google.code.gson:gson:2.13.1")
```

thành:

```kotlin
implementation("com.google.code.gson:gson:2.13.1")
```

Giữ nguyên Java source và chạy:

```bash
./gradlew :consumer:compileJava
```

Trong project demo không có Gson ở dependency khác:

- `:catalog-lib:compileJava` vẫn có thể thành công: library có Gson trong **compileClasspath của chính nó**.
- `:consumer:compileJava` sẽ thất bại khi compiler cần `JsonObject`, vì Gson **không được công bố trong compile API variant** của library.
- Thông báo lỗi có thể là `package com.google.gson does not exist`, `cannot access JsonObject` hoặc lỗi class file liên quan. Không giả định chuỗi error message giống mọi JDK.

**Sửa đúng:** khôi phục `api("com.google.code.gson:gson:2.13.1")` ở module sở hữu public method signature. Bắt mọi consumer khai báo Gson trực tiếp chỉ để che lỗi API metadata của producer không phải giải pháp tốt cho một library được thiết kế công khai Gson.

## 7. Thử nghiệm 2: consumer tự dùng Commons Lang

Giữ Commons Lang là `implementation` của library, rồi thử thêm trong `Main.java`:

```java
// Mảnh ghép lỗi có chủ đích: thêm import và gọi class này trong Main.
import org.apache.commons.lang3.StringUtils;
```

Nếu consumer trực tiếp gọi `StringUtils` mà chỉ phụ thuộc `:catalog-lib`, compiler của consumer sẽ **không tự nhận Commons Lang thông qua API của catalog-lib**. Khi muốn consumer thật sự dùng thư viện này, consumer phải khai báo **dependency của chính nó**:

```kotlin
dependencies {
    implementation(project(":catalog-lib"))
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Việc consumer cần Commons Lang **không đồng nghĩa** public API của `:catalog-lib` phải lộ Commons Lang. Hãy giữ scope `implementation` ở library nếu Commons Lang không nằm trong public contract của library.

Điểm phân biệt rất quan trọng: Commons Lang có thể vẫn **xuất hiện ở runtimeClasspath** của consumer để `CatalogService` chạy, nhưng việc nó xuất hiện ở runtime không cho consumer quyền **compile** source import `StringUtils` khi dependency chưa được công bố/khai báo cho compiler.

## 8. Bốn configuration roles thường bị nhầm

Gradle Java Library plugin tạo nhiều configurations với những vai trò khác nhau:

| Vai trò | Ví dụ | Cách sử dụng |
| --- | --- | --- |
| **Declarable** | `api`, `implementation`, `compileOnly`, `runtimeOnly` | Khai báo dependency trong `dependencies { ... }` |
| **Resolvable** | `compileClasspath`, `runtimeClasspath` | Gradle phân giải thành dependencies/files cho compiler và JVM |
| **Consumable** | `apiElements`, `runtimeElements` | Library công bố các variants để consumer lựa chọn |

Khi một consumer biên dịch dựa trên Java library:

```text
Consumer compileClasspath
    yêu cầu Java API usage
        |
        v
Producer apiElements
    gồm library artifact/API
    và dependency đã công bố qua api / compileOnlyApi
```

Khi consumer chạy:

```text
Consumer runtimeClasspath
    yêu cầu Java runtime usage
        |
        v
Producer runtimeElements
    gồm library runtime artifact
    và dependencies runtime phù hợp từ api,
    implementation, runtimeOnly
```

Đây là sơ đồ khái niệm; Gradle còn xét attributes (usage, category, Java version, library elements...), constraints và capabilities. Không nên thêm dependency trực tiếp vào `apiElements` hoặc gọi `implementation.resolve()` như thể chúng là các configuration dành cho resolution. Muốn nhìn thực tế, dùng `compileClasspath` và `runtimeClasspath`.

**Project dependency là một declaration, không phải một danh sách JAR cố định.** `implementation(project(":catalog-lib"))` có thể dẫn đến variants khác nhau theo mục đích compile/runtime.

## 9. Phân biệt `api`, `implementation`, `compileOnlyApi` và các scope khác

| Scope của Java library | Library compile? | Consumer compile? | Consumer runtime? | Ý định |
| --- | --- | --- | --- | --- |
| `api` | Có | Có | Có | Public compile API và runtime |
| `implementation` | Có | Không tự phơi bày | Có | Implementation nội bộ nhưng cần chạy |
| `compileOnly` | Có | Không tự phơi bày | Không | Chỉ compile của library |
| `compileOnlyApi` | Có | Có | Không tự đưa vào | Public compile-only contract |
| `runtimeOnly` | Không tự là compile dependency | Không | Có | Chỉ cần khi chạy |
| `testImplementation` | Dành cho compile/test | Không phải public main API | Không thuộc main production runtime | Chỉ test |

### Khi nào dùng `compileOnlyApi`?

Có những kiểu mà consumer compiler cần biết do public contract, nhưng không phải dependency cần được đưa vào runtime. Ví dụ các **compile-time annotations** hoặc contract được môi trường khác cung cấp riêng. Khi đó `compileOnlyApi` có thể đúng:

```kotlin
plugins {
    `java-library`
}

dependencies {
    // Tên artifact sau chỉ là placeholder minh họa:
    compileOnlyApi("com.example:contract-annotations:1.0")
}
```

**Không chạy snippet trên với placeholder**; chọn artifact thực tế đúng dự án. `compileOnlyApi` không phải cách che thư viện runtime. Nếu code cần class lúc chạy, bạn phải bảo đảm runtime có nó bằng cơ chế thích hợp.

### `compileOnly` khác `compileOnlyApi`

- `compileOnly`: **chính library** cần type lúc compile, consumer không tự nhận compile API dependency.
- `compileOnlyApi`: **library và consumer compiler** cần type, nhưng runtime không tự được cung cấp.

Với một Java annotation processor, cần thêm `annotationProcessor` riêng cho processor code chạy bởi compiler; annotation classpath và processor path không phải một. Tuy nhiên, **annotation processing không tự biến annotation thành `api`**. Scope vẫn phụ thuộc types xuất hiện trong public contract hay chỉ dùng nội bộ.

## 10. API boundary ảnh hưởng đến tái biên dịch và compile avoidance

Một lợi ích của `implementation` là giảm **compile classpath** của các module tiêu thụ và tránh accidental dependencies. Điều này còn giúp Gradle đưa ra các quyết định *compile avoidance* tốt hơn.

Ví dụ, library chỉ thay một thuật toán format nội bộ nhưng method vẫn là:

```java
public JsonObject create(String rawName);
```

Nếu **ABI không thay đổi**, consumer về lý thuyết không cần biên dịch lại chỉ vì method body hoặc một implementation library đổi. Gradle Java compile avoidance và ABI snapshots có thể tận dụng ranh giới này.

Nhưng đừng suy diễn quá mức:

- Thay đổi public signature, generic bound, superclass, annotations compiler cần… có thể làm ABI thay đổi.
- Changes ở nguồn compiler options, annotation processor, task inputs, Gradle version hoặc build caching vẫn có thể yêu cầu compile lại.
- Một số thay đổi implementation vẫn làm consumer compiler cần class files (ví dụ type annotations trong private metadata).
- **Runtime dependency vẫn phải đúng**. Không recompile consumer không có nghĩa chạy được với runtime artifacts thiếu hoặc sai version.

Kết quả thường mong muốn: **consumer compile nhanh hơn và có ít dependency hơn**, đồng thời lỗi accidental reliance on transitive libraries được phát hiện sớm.

## 11. Rò rỉ API qua generics, inheritance và annotations

Một số ví dụ dễ phân loại sai:

```java
// Generic type argument vẫn là một phần public signature:
public java.util.List<ExternalType> findAll();
```

```java
// Kiểu superclass cũng là dependency của public binary contract:
public class PublicAdapter extends ExternalBase {
}
```

```java
// Public method parameter:
public void submit(ExternalRequest request);
```

Nếu `ExternalType`, `ExternalBase` hoặc `ExternalRequest` đến từ thư viện khác, consumer compiler có thể cần dependency đó. Không thể giấu chúng chỉ bằng việc dùng `implementation`.

Ngược lại:

```java
public String label() {
    return ExternalStringHelper.normalize(source);
}
```

Nếu `ExternalStringHelper` chỉ được gọi trong implementation body và consumer compiler không cần type của nó, scope phù hợp thường là `implementation`.

**Ngoại lệ:** Java compiler đôi lúc cần class file của kiểu xuất hiện ở vị trí tưởng là private; Gradle docs nêu các ví dụ về type annotations và overload metadata. Khi compiler của consumer báo `class file for ... not found`, hãy kiểm tra thực tế dependency ABI requirements trước khi chọn `api` hoặc `compileOnlyApi`.

## 12. Thiết kế API không phụ thuộc trực tiếp vào third-party type

Không phải cứ public API dùng Gson thì việc đó sai. Nhưng nếu muốn tự do đổi serialization library sau này, có thể công bố **DTO/record** do chính thư viện sở hữu.

**Cách công bố kiểu Gson:**

```java
public com.google.gson.JsonObject find(String id);
```

Consumer bị ghép với Gson ở compile time. Khi đổi sang Jackson, public signature thay đổi, có thể đòi consumer sửa code và là một breaking API change.

**Cách dùng public DTO do library sở hữu:**

```java
package demo.catalog;

public record CatalogItem(String id, String label) {
}
```

Và:

```java
package demo.catalog;

public interface CatalogReader {
    CatalogItem find(String id);
}
```

Implementation vẫn có thể dùng Gson, nhưng không xuất hiện trong public method signature:

```kotlin
dependencies {
    implementation("com.google.code.gson:gson:2.13.1")
}
```

Phân tách này có chi phí mapping và thêm types; lựa chọn phù hợp tùy public API contract. Không tạo DTO chỉ để thỏa một quy tắc máy móc, nhưng nên **chủ động quyết định độ coupling** trước khi publish.

**`implementation` không phải cơ chế bảo mật.** Consumer có thể tự thêm Gson/Commons Lang vào project của mình. Đây là cơ chế **compile/runtime dependency exposure**, không phải JVM access control hoặc mã hóa JAR.

## 13. Ranh giới API khi xuất bản Java library

Với multi-project build, Gradle biết trực tiếp public/runtime variants của `:catalog-lib`. Khi thư viện được publish ra Maven repository, cách dependency được công bố phụ thuộc metadata:

- **Gradle Module Metadata** có thể giữ nhiều variants/attributes và thông tin dependency phong phú.
- **Maven POM** có các scopes compile/runtime đơn giản hơn. Java library publication thông thường ánh xạ `api` thành compile dependency và `implementation` thành runtime dependency phù hợp.
- Với thư viện **ngoài hệ sinh thái Gradle**, POM có thể không thể hiện chính xác public API/implementation separation như tác giả mong muốn. Consumer cần quan sát graph đã resolve.

Một snippet **bổ sung**, không phải phần cần thiết của project demo:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "demo.catalog"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
```

Đây là cách publish Java component; nó chưa chỉ định repository và credentials thật. Để kiểm tra metadata trước khi gửi lên registry, có thể chạy task sinh POM, ví dụ `./gradlew generatePomFileForMavenJavaPublication` khi cấu hình này đã tồn tại.

**Không nên nâng toàn bộ `implementation` thành `api` chỉ để POM nhìn đơn giản.** Làm vậy công bố những dependency nội bộ thành compile-time API cho consumers.

## 14. Liên hệ với Java Module System (JPMS)

Gradle scopes và Java 9+ `module-info.java` **không phải một cơ chế**. Nhưng khi sử dụng Java modules, một ánh xạ theo ý định thường là:

| JPMS declaration | Gradle configuration tương ứng |
| --- | --- |
| `requires com.example.module;` | `implementation` |
| `requires transitive com.example.module;` | `api` |
| `requires static com.example.module;` | `compileOnly` |
| `requires static transitive com.example.module;` | `compileOnlyApi` |

Một minh họa dạng `module-info.java`:

```java
module demo.catalog {
    requires transitive com.google.gson;
    requires org.apache.commons.lang3;

    exports demo.catalog;
}
```

Tên module và việc dependency có được coi là named/automatic module phải **xác minh từ artifact/version thật**, không suy luận máy móc từ Maven coordinates. Đoạn này minh họa mapping và chỉ biên dịch trong project đã cấu hình Java module path phù hợp.

Gradle **không tự đồng bộ** `module-info.java` với `api`/`implementation`; người viết build chịu trách nhiệm giữ chúng nhất quán. JPMS `exports` giới hạn package visibility ở module system, còn Gradle dependency scopes giới hạn **tập JAR của consumer compile/runtime classpaths**, không tự ngăn truy cập public class theo package.

## 15. Lệnh Gradle để xem public compile/runtime boundaries

Từ root project hoàn chỉnh ở mục 5:

```bash
./gradlew :catalog-lib:dependencies --configuration compileClasspath
./gradlew :catalog-lib:dependencies --configuration runtimeClasspath
./gradlew :consumer:dependencies --configuration compileClasspath
./gradlew :consumer:dependencies --configuration runtimeClasspath
```

Đọc kết quả theo mục đích:

| Lệnh | Điều cần quan sát |
| --- | --- |
| Library `compileClasspath` | Gson **và** Commons Lang vì library tự dùng cả hai |
| Library `runtimeClasspath` | Gson và Commons Lang vì code library cần ở runtime |
| Consumer `compileClasspath` | Project dependency đến catalog-lib, và Gson từ API; Commons Lang không mặc định xuất hiện qua library |
| Consumer `runtimeClasspath` | Project dependency và runtime dependencies, gồm Gson và Commons Lang |

Để điều tra **vì sao** một module xuất hiện:

```bash
./gradlew :consumer:dependencyInsight --configuration compileClasspath --dependency gson
./gradlew :consumer:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
```

Trong PowerShell:

```powershell
.\gradlew.bat :consumer:dependencyInsight --configuration compileClasspath --dependency gson
.\gradlew.bat :consumer:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
```

Các báo cáo hiển thị **dependency graph đã resolve** và có thể có transitive paths, selected versions, variants hoặc conflict reasons. Không tự giả định thứ tự JAR/indent/version từ DSL; Gradle có thể giải version theo constraints/metadata.

**Không dùng `configurations.implementation.get().resolve()`** để xem compile classpath. `implementation` là scope dùng để **khai báo**, không phải resolvable configuration. Hãy xem `compileClasspath`/`runtimeClasspath`.

### Dùng `javap` quan sát chữ ký công khai

Sau khi compile:

```bash
./gradlew :catalog-lib:classes
javap -public -classpath catalog-lib/build/classes/java/main demo.catalog.CatalogService
```

Trong class output, bạn sẽ thấy thông tin tương tự:

```text
public final class demo.catalog.CatalogService {
  public demo.catalog.CatalogService();
  public com.google.gson.JsonObject create(java.lang.String);
}
```

Đây là **trích đoạn minh họa**, định dạng `javap` có thể khác theo JDK. Điều đáng xem là `JsonObject` có mặt trong public signature, còn `StringUtils` không phải return type, parameter hay superclass công khai của class.

## 16. Những lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Unresolved reference: api` trong Kotlin DSL | Chỉ dùng Java plugin hoặc API configuration không tồn tại | Với library, áp dụng `java-library` |
| Library compile PASS, consumer compile FAIL vì thiếu external class | Public API dùng kiểu chỉ khai báo `implementation` | Đổi sang `api` hoặc `compileOnlyApi` nếu compile-only |
| Consumer import được thư viện nội bộ ở local nhưng CI fail | Transitive compile classpath bị lệch hoặc consumer không khai báo direct dependency | Khai báo đúng dependency ở consumer và dùng Wrapper |
| Consumer compile classpath quá lớn | Lạm dụng `api` | Rà soát public ABI, chuyển internal libs sang `implementation` |
| Consumer runtime lỗi `NoClassDefFoundError` | Thiếu runtime dependency, sai artifact/distribution hoặc binary incompatibility | Xem runtimeClasspath và cách đóng gói |
| Consumer compile được nhưng `java -jar` thiếu Commons Lang | JAR mặc định không tự đóng gói dependencies | Dùng Application distribution/runtime classpath đúng |
| External type có trong generic signature nhưng không thấy dependency | Generic arguments vẫn thuộc public contract | Xem `List<ExternalType>` và `api` |
| `compileOnlyApi` cho dependency runtime cần | Compile API đúng nhưng JVM thiếu class | Chọn `api` hoặc runtime contract phù hợp |
| Runtime version khác compile version | Variant, constraint hoặc version conflict | Dùng `dependencyInsight` riêng từng configuration |
| Đổi implementation dependency khiến consumer rebuild | Có thể có ABI/task inputs khác, plugin hoặc compiler option đổi | Kiểm tra build logic và ABI snapshots, không suy luận lỗi ngay |
| Module descriptor không khớp API scope | `requires`/JPMS và Gradle DSL chưa đồng bộ | Xem `requires transitive`, `exports` và Gradle variants |
| Tutorial cũ dùng configuration `compile` | Configuration cũ đã bị loại bỏ trong Gradle 7+ | Chuyển sang `implementation` hoặc `api` đúng nghĩa |

Khi một consumer không biên dịch được, **không vội thêm mọi dependency vào `api` để vượt lỗi**. Xác định kiểu nào thực sự thuộc public contract, dependency nào chỉ cần runtime và dependency nào consumer đang sử dụng trực tiếp.

## 17. Checklist khi review dependency của Java library

- [ ] Module thực sự là Java library đã áp dụng `java-library`.
- [ ] Public method/constructor/field/supertype/generic signatures đã được rà soát.
- [ ] Third-party types thật sự xuất hiện trong public ABI được khai báo scope phù hợp.
- [ ] Library implementation-only dependencies dùng `implementation` thay vì `api`.
- [ ] Các type cần cho consumer compile nhưng không cần runtime đã được xem xét `compileOnlyApi`.
- [ ] Consumer sử dụng thư viện bên ngoài trực tiếp đã khai báo dependency của chính nó.
- [ ] Đã kiểm tra cả `:consumer:compileClasspath` **và** `:consumer:runtimeClasspath`.
- [ ] Chạy `:consumer:compileJava`/tests để phát hiện API dependencies thiếu.
- [ ] Nếu library publish, đã kiểm tra metadata/POM có đúng compile/runtime scopes.
- [ ] Nếu dùng `module-info.java`, đã đối chiếu `requires transitive` với API exposures.
- [ ] Không dùng `api` như biện pháp bảo mật hay giải pháp thay thế public API design.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `:lib` gọi Commons Lang `StringUtils` trong private helper, không nhắc nó trong public API. Nên dùng `api` hay `implementation`?

**Đáp:** Thường dùng `implementation`. Library vẫn compile/run với Commons Lang nhưng không tự công bố nó cho compiler của consumer.

**Câu 2.** `:lib` có public method `JsonObject parse(String)`. Vì sao consumer compile có thể thất bại nếu Gson chỉ là `implementation`?

**Đáp:** Public return type chứa `JsonObject`, nhưng dependency từ implementation không được đưa vào consumer compile API variant. Nếu Gson là public contract, dùng `api`.

**Câu 3.** Consumer muốn import `StringUtils` để tự xử lý text. Có cần nâng Commons Lang thành `api` ở library không?

**Đáp:** Không nhất thiết. Consumer nên khai báo Commons Lang trực tiếp vì đây là nhu cầu của chính consumer.

**Câu 4.** `api` và `implementation` có cùng xuất hiện trong runtime classpath của consumer không?

**Đáp:** Thông thường có, qua runtime variant của Java library. Khác biệt quan trọng nhất là **compile API exposure**.

**Câu 5.** `List<ExternalType>` ở public return type có tính là lộ external dependency không?

**Đáp:** Có thể có. Compiler có thể cần `ExternalType` vì nó thuộc generic method signature, dù outer type là `List` của JDK.

**Câu 6.** `compileOnlyApi` khác `api` thế nào?

**Đáp:** Cả hai đưa type cần thiết đến compiler consumer, nhưng `compileOnlyApi` không tự mang dependency đó vào runtime variant.

**Câu 7.** Vì sao một `implementation` dependency vẫn có thể dẫn tới `NoClassDefFoundError` khi chạy consumer?

**Đáp:** Nếu runtime distribution thiếu artifact, library code có thể không tìm được class lúc thực thi dù compiler consumer không cần thấy class đó.

**Câu 8.** Đổi một implementation library nhưng không đổi public ABI có luôn khiến consumer `compileJava` được bỏ qua?

**Đáp:** Không bảo đảm. Gradle có thể tránh recompilation theo ABI, nhưng các input khác, plugin configuration và compiler conditions vẫn có thể thay đổi.

**Câu 9.** Trong `module-info.java`, `requires transitive` thường tương ứng scope nào?

**Đáp:** `api`; nhưng JPMS descriptor và Gradle dependencies không được Gradle tự giữ đồng bộ.

**Câu 10.** Muốn xem Commons Lang có mặt ở runtime nhưng không có ở compile API của consumer, dùng lệnh gì?

**Đáp:** So `:consumer:dependencies --configuration compileClasspath` với `--configuration runtimeClasspath`, sau đó dùng `dependencyInsight` theo configuration khi cần lần nguyên nhân.

## 19. Tài liệu chính thức

- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): API/implementation separation, ABI, các ngoại lệ compiler và `compileOnlyApi`.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html): declarable, resolvable và consumable configurations.
- [Gradle — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): API/runtime variants, attributes và consumer selection.
- [Gradle — Dependency Management for Java Projects](https://docs.gradle.org/current/userguide/dependency_management_for_java_projects.html): configuration scopes trong Java library.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): project dependencies.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): xuất bản Java components và metadata.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies` và `dependencyInsight`.
