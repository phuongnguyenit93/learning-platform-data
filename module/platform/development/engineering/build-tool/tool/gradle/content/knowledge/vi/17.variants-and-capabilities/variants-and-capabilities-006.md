# Feature variants và công bố tính năng tùy chọn trong Gradle

## 1. Vấn đề: một thư viện có nhiều tính năng, nhưng không phải ai cũng cần tất cả

Giả sử bạn phát triển thư viện Java tên `library` gồm một API cốt lõi và một tính năng mở rộng `jsonSupport`. Ứng dụng A chỉ cần API cốt lõi; ứng dụng B muốn bật tính năng JSON và các dependency riêng của nó. Nếu dồn mọi class và dependency vào `main`, người dùng không cần JSON vẫn phải nhận thêm các thư viện đi kèm. Nếu tách hoàn toàn thành nhiều module độc lập, đôi khi build/publication phức tạp hơn mức cần thiết.

**Gradle feature variants** giải quyết trường hợp này: một **Java library component** có thể công bố **nhiều biến thể tính năng** với source set, artifact, dependency graph và **capability** riêng. Consumer yêu cầu feature qua capability để chỉ lấy phần họ cần.

Mục tiêu bài học:

- Hiểu **component**, **variant**, **attribute**, **capability** và sự khác nhau giữa feature variant với một Maven optional dependency.
- Tạo feature bằng `java { registerFeature("jsonSupport") { usingSourceSet(...) } }` trong `build.gradle.kts`.
- Dùng đúng các configuration như `jsonSupportApi`, `jsonSupportImplementation` và `jsonSupportRuntimeOnly`.
- Để consumer chọn **main library** và **optional feature** thông qua `requireCapability(...)`.
- Phân biệt feature chỉ cần lúc chạy (runtime-only) với feature có API mà mã nguồn consumer import trực tiếp.
- Publish bằng `maven-publish`/`ivy-publish`, hiểu tại sao **Gradle Module Metadata (`.module`)** giữ đầy đủ feature model còn **Maven POM** chỉ biểu diễn một phần.
- Kiểm tra variants/capabilities/artifacts và xử lý các lỗi `No matching variant`, capability không tồn tại, xung đột capability, thiếu feature JAR và dependency bắc cầu.
- Thiết kế feature tùy chọn có khả năng tái lập và test trong project cùng build lẫn consumer ngoài build.

Các ví dụ chạy bằng **Gradle Kotlin DSL**, JDK 17+ và Gradle Wrapper. Để độc lập với Internet, ví dụ chính dùng **Java chuẩn, không tải thư viện ngoài**; một ví dụ riêng cho thấy cách gắn Jackson khi thực sự cần JSON serialization.

## 2. Năm khái niệm cốt lõi

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Component** | `org.example:library:1.0` | Một thư viện/phần mềm với danh tính module hoặc project component. |
| **Variant** | `apiElements`, `runtimeElements`, `jsonSupportApiElements`, `jsonSupportRuntimeElements` | Cách component cung cấp API/runtime/artifact/dependencies cho những nhu cầu tiêu thụ khác nhau. |
| **Attribute** | `org.gradle.usage=java-api` hoặc `java-runtime` | Đặc tính giúp Gradle so khớp variant với consumer. |
| **Capability** | `org.example:library-json-support:1.0` | Khả năng/tính năng mà variant cung cấp; consumer có thể yêu cầu một capability cụ thể. |
| **Artifact** | JAR chính, JAR feature với classifier | File vật lý được Gradle cung cấp sau khi chọn variant. |

Một feature không đơn thuần là một JAR có classifier. **Feature variant bao gồm cả khả năng được yêu cầu, dependency graph, attributes và artifact.** Nếu chỉ gắn `artifact(extraJar)` vào Maven publication, Gradle có thể publish file đó mà **không có metadata feature** cho consumer chọn đúng theo capability.

Một variant API/runtime của feature cũng khác với **hai phiên bản thư viện**: `jsonSupportApiElements` và `jsonSupportRuntimeElements` đại diện cho mục đích sử dụng khác nhau của **cùng feature**, không phải hai version độc lập.

### Có hai câu hỏi mà Gradle phải trả lời

1. **Consumer cần tính năng nào?** Capability làm rõ điều đó: main mặc định hay `library-json-support`.
2. **Consumer cần dùng tính năng ra sao?** Attributes như `java-api`/`java-runtime` giúp chọn đúng API hoặc runtime variant.

Capability **không thay thế** attributes; attributes cũng **không tự chỉ định** “bật tính năng JSON”. Hai cơ chế phối hợp trong variant-aware dependency resolution.

## 3. Capability mặc định và capability của feature

Mỗi module/component Gradle thường có **default capability** trùng tọa độ GAV chính:

~~~text
Main component:
  group    = org.example
  module   = library
  version  = 1.0

Main capability:
  org.example:library:1.0
~~~

Khi khai báo:

~~~kotlin
java {
    registerFeature("jsonSupport") {
        usingSourceSet(sourceSets.create("jsonSupport"))
    }
}
~~~

Gradle theo quy ước tạo capability cho feature:

~~~text
Feature name:       jsonSupport
Kebab-case name:    json-support
Feature capability: org.example:library-json-support:1.0
~~~

**Điều kiện của ví dụ:** project cung cấp phải có `group = "org.example"`, `version = "1.0"` và tên project là `library`. Nếu tên project, group, version hoặc capability explicit thay đổi, tọa độ phải thay tương ứng.

Gradle tạo tên capability mặc định cho feature theo dạng **group : project/module-name + "-" + kebab-case-feature-name : version**. Đừng nhầm `jsonSupport` trong tên source set với `json-support` trong capability name.

Consumer có thể yêu cầu:

~~~kotlin
implementation(project(":library")) {
    capabilities {
        requireCapability("org.example:library-json-support")
    }
}
~~~

Ở đây `requireCapability` chấp nhận notation `group:name` không ghi version; Gradle so khớp capability phù hợp từ producer đã được chọn. Đây là API ổn định, phù hợp cho ví dụ đào tạo. Ở các phiên bản Gradle mới còn có `requireFeature("jsonSupport")` trên capabilities handler, nhưng API đó được đánh dấu **incubating** trong tài liệu Gradle, vì vậy bài dùng `requireCapability` khi cần tính tương thích và kiểm soát tên cụ thể.

## 4. Đăng ký feature bằng Java Library plugin

Feature variants theo cơ chế `java.registerFeature` được **hỗ trợ bởi các Java plugins**; không mặc định áp dụng nguyên API này cho mọi hệ sinh thái native/Android hay plugin tùy biến khác. Cấu hình phổ biến:

~~~kotlin
plugins {
    `java-library`
}

group = "org.example"
version = "1.0"

java {
    registerFeature("jsonSupport") {
        usingSourceSet(sourceSets.create("jsonSupport"))
    }
}
~~~

Trong đoạn mã trên, `java-library` phải được đặt bằng **Kotlin backticks**. Plugin cung cấp extension `java`. `registerFeature` đưa feature mới vào model của Java component. `usingSourceSet` liên kết một **source set riêng** cho code/tài nguyên của feature.

### Tại sao cần source set riêng?

Source set định nghĩa source files, resources, compile classpath, runtime classpath và tasks liên quan. Mặc định:

~~~text
src/main/java/                 code cốt lõi
src/main/resources/            resources cốt lõi

src/jsonSupport/java/          code tùy chọn
src/jsonSupport/resources/     resources tùy chọn
~~~

Đây là các đường dẫn **mặc định gắn với source set tên `jsonSupport`**. Bạn có thể cấu hình một thư mục khác qua `sourceSets { ... }` nếu dự án cần, nhưng hãy giữ tách biệt main/feature khi mới bắt đầu.

Gradle tự cung cấp thêm các configuration cho feature, ví dụ:

| Configuration | Vai trò |
| --- | --- |
| `jsonSupportApi` | Thư viện được dùng trong public API của feature. |
| `jsonSupportImplementation` | Thư viện chỉ phục vụ chi tiết triển khai của feature. |
| `jsonSupportCompileOnly` | Chỉ cần khi compile feature, không tự đưa lên runtime. |
| `jsonSupportRuntimeOnly` | Chỉ cần khi runtime feature. |
| `jsonSupportApiElements` | Outgoing API variant để consumer compile với feature. |
| `jsonSupportRuntimeElements` | Outgoing runtime variant để consumer thực thi feature. |

Không gắn tất cả dependencies của feature vào `implementation` của **main** nếu muốn tính năng thật sự tùy chọn. Nếu JSON library chỉ cần cho `jsonSupport`, hãy khai báo đúng ở `jsonSupportImplementation`/`jsonSupportApi`. Ví dụ có Jackson:

~~~kotlin
dependencies {
    "jsonSupportImplementation"(
        "com.fasterxml.jackson.core:jackson-databind:2.17.2"
    )
}
~~~

Đây là **mảnh cấu hình có dependency ngoài**, không phải phần bắt buộc của ví dụ chạy offline ở dưới. Chọn phiên bản Jackson phù hợp JDK và chính sách cập nhật; ví dụ không khẳng định `2.17.2` là phiên bản mới nhất. Nếu API công khai của feature lộ các kiểu Jackson, cân nhắc `jsonSupportApi` thay cho `jsonSupportImplementation`, vì consumer cần đúng kiểu ở compile classpath.

### Đừng dùng source set `main` làm feature

Một số cấu hình cũ cố gắng:

~~~kotlin
java {
    registerFeature("jsonSupport") {
        usingSourceSet(sourceSets["main"])
    }
}
~~~

Đây là **đoạn phản ví dụ**. Tài liệu Gradle khuyến cáo **không dùng source set main khi đăng ký feature**, vì hành vi này sẽ bị deprecate trong phiên bản tương lai. Nó cũng phá ranh giới code cốt lõi/tùy chọn và dễ khiến JAR được công bố thiếu ý nghĩa. Hãy dùng một source set riêng hoặc tách module độc lập.

## 5. Ví dụ hoàn chỉnh: một Java library và một ứng dụng consumer

Bài thực hành này **không cần download dependency ngoài**. Chúng ta tạo:

- `:library` chứa API chính `CoreApi` và optional feature class `JsonFeature` nằm ở source set riêng.
- `:app` luôn dùng main library, và **tùy chọn** thêm runtime feature bằng `requireCapability`.
- App phát hiện feature bằng reflection để chương trình **vẫn compile khi feature vắng mặt**. Reflection chỉ dùng trong demo để chứng minh opt-in; production nên dùng interface/service-provider rõ ràng hoặc compile-time feature API khi có yêu cầu.

### 5.1. Cấu trúc thư mục

~~~text
feature-variant-lab/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── library/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/example/library/CoreApi.java
│       └── jsonSupport/java/example/library/json/JsonFeature.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/example/app/App.java
~~~

Các file Java cần giữ đúng package và đường dẫn. Gradle Wrapper phải hoạt động với JDK 17 trở lên; nếu Gradle/JDK hiện có không hỗ trợ cách cấu hình, xem compatibility matrix của Gradle đang dùng.

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "feature-variant-lab"

include("library", "app")
~~~

### 5.2. Producer: `library/build.gradle.kts`

Đây là **toàn bộ file** cho thư viện, bao gồm phần publish để dùng tiếp ở mục 10:

~~~kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "org.example"
version = "1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }

    registerFeature("jsonSupport") {
        usingSourceSet(sourceSets.create("jsonSupport"))
    }
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }

    repositories {
        maven {
            name = "demo"
            url = uri(layout.buildDirectory.dir("published-repo"))
        }
    }
}
~~~

Lý do:

1. `java-library` tạo mô hình Java component cùng API/runtime variants.
2. `group`, `version` và tên project `library` quyết định main GAV và capability feature theo quy ước.
3. `registerFeature("jsonSupport")` tạo thêm source set/feature variants, khi `usingSourceSet` được khai báo.
4. Gradle tạo task `Jar` liên quan feature và đưa feature artifact vào Java component publication (theo cơ chế Java Library plugin).
5. `maven-publish` cùng `from(components["java"])` tạo publication từ **Java component**. Việc này giữ model variant tốt hơn so với việc chỉ publish một JAR tự gắn bằng `artifact(...)`.
6. Repository `demo` trỏ tới thư mục `library/build/published-repo` để thử, **không** phải một kho tập trung dùng chung hay Maven Central.

Không cần `repositories { mavenCentral() }` ở thư viện trong ví dụ này vì không có dependency ngoài. Nếu thêm Jackson theo `jsonSupportImplementation`, phải thêm một dependency repository phù hợp cho việc resolve library ở bước build.

### 5.3. Main source của library

`library/src/main/java/example/library/CoreApi.java`:

~~~java
package example.library;

public final class CoreApi {
    private CoreApi() {
    }

    public static String status() {
        return "core-ready";
    }
}
~~~

`CoreApi` hoàn toàn độc lập với code JSON. Người chỉ tiêu thụ main capability nhận được API cơ bản này.

### 5.4. Optional feature source

`library/src/jsonSupport/java/example/library/json/JsonFeature.java`:

~~~java
package example.library.json;

public final class JsonFeature {
    private JsonFeature() {
    }

    public static String status() {
        return "json-ready";
    }
}
~~~

Trong ví dụ, `JsonFeature` dùng JDK thuần để demo khả năng được phân phối độc lập; nó **không phải một JSON serializer thực tế**. Nếu cần JSON thật, dùng thư viện đã kiểm thử (ví dụ Jackson) qua `jsonSupportImplementation` và đưa code tương ứng vào source set này.

Feature source set tách biệt có thể có compile classpath khác main. **Đừng giả định class của main tự nằm trong compile classpath của mọi source set tùy biến**; bài demo giữ `JsonFeature` độc lập với `CoreApi`. Nếu feature cần import class từ main, phải cấu hình classpath/dependency giữa các source sets hoặc thiết kế lại source ownership đúng cách.

### 5.5. Consumer: `app/build.gradle.kts`

Đây là **file độc lập hoàn chỉnh**. Main library luôn được dùng; feature được chọn như một dependency runtime bổ sung:

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("example.app.App")
}

dependencies {
    // Main capability của :library.
    implementation(project(":library"))

    // Optional feature capability của cùng :library.
    runtimeOnly(project(":library")) {
        capabilities {
            requireCapability("org.example:library-json-support")
        }
    }
}
~~~

Vì main và feature cung cấp **capabilities khác nhau**, consumer có thể yêu cầu cả hai từ cùng component bằng **hai dependency declarations**. Lời gọi `runtimeOnly` thích hợp vì `App` không import `JsonFeature` lúc compile; chỉ kiểm tra feature có mặt khi chạy.

**Đừng xóa dependency main rồi nghĩ feature thay thế hoàn toàn main library:** trong ví dụ này `App` import `CoreApi`, nên phải giữ main dependency. Tùy một feature được thiết kế thế nào, nó có thể có những dependency riêng; không mặc định mọi feature artifact tự chứa mọi class main.

### 5.6. Consumer Java source

`app/src/main/java/example/app/App.java`:

~~~java
package example.app;

import example.library.CoreApi;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws Exception {
        System.out.println("MAIN=" + CoreApi.status());

        try {
            Class<?> feature = Class.forName(
                "example.library.json.JsonFeature"
            );

            Object result = feature.getMethod("status").invoke(null);
            System.out.println("FEATURE=" + result);
        } catch (ClassNotFoundException ignored) {
            System.out.println("FEATURE=absent");
        }
    }
}
~~~

Mã này dùng Java Reflection để **không có import `JsonFeature` tại compile time**. Nó in trạng thái main, sau đó thử tìm class feature ở runtime. Nếu class không có, nó báo absent; nếu class có và method chạy thành công, in giá trị trả về.

Trong ứng dụng thật, không nên dùng reflection như một “cơ chế plugin” nếu có nhu cầu lớn: hãy cân nhắc `ServiceLoader`, API interface ổn định, DI hoặc một module integration rõ ràng. Demo chỉ chứng minh khác biệt runtime classpath khi consumer yêu cầu capability.

### 5.7. Chạy feature đang bật

Từ root, với dòng `runtimeOnly(project(":library")) { capabilities { ... } }` còn nguyên:

~~~bash
./gradlew --version
./gradlew -q :app:run
~~~

Stdout **do `main` in ra** là:

~~~text
MAIN=core-ready
FEATURE=json-ready
~~~

Thông tin Gradle bên ngoài stdout của main có thể thay đổi do version/toolchain/daemon; hai dòng trên là kết quả logic Java khi build thành công.

### 5.8. Chạy feature đang tắt

Để chứng minh opt-in, **chỉ ở bản thử** hãy tạm bỏ **toàn bộ block** sau khỏi `app/build.gradle.kts`:

~~~kotlin
runtimeOnly(project(":library")) {
    capabilities {
        requireCapability("org.example:library-json-support")
    }
}
~~~

Giữ nguyên `implementation(project(":library"))`. Chạy lại:

~~~bash
./gradlew -q :app:run
~~~

Stdout của main:

~~~text
MAIN=core-ready
FEATURE=absent
~~~

Điều này chứng minh consumer chính **không tự nhận feature runtime** nếu không yêu cầu capability. Mã Java đã được viết để hỗ trợ absence; nếu nó import/truy cập trực tiếp `JsonFeature` lúc compile, việc bỏ feature dependency sẽ làm **compile fail**, chứ không phải in absent.

**Không cố dùng cả bản “bật” và bản “tắt” trong cùng script:** đây là hai trạng thái cấu hình khác nhau để kiểm thử.

## 6. Khi consumer cần compile trực tiếp với API của feature

Nếu consumer muốn dùng:

~~~java
import example.library.json.JsonFeature;
~~~

thì `JsonFeature` phải có trên **compileClasspath**, không chỉ runtimeClasspath. Khi ấy dùng:

~~~kotlin
dependencies {
    implementation(project(":library"))

    implementation(project(":library")) {
        capabilities {
            requireCapability("org.example:library-json-support")
        }
    }
}
~~~

Đây là **phương án thay thế block `dependencies` ở mục 5.5**, không bổ sung đồng thời một declaration feature giống hệt ở cả `implementation` và `runtimeOnly` trừ khi có chủ đích.

Với cấu hình trên, code Java có thể gọi:

~~~java
System.out.println(JsonFeature.status());
~~~

Khi đặt câu lệnh này vào một Java class có import tương ứng và main method, stdout là `json-ready`. Đây là **mảnh code minh họa**, không thay thế file `App.java` hoàn chỉnh ở mục 5.6.

**Phân biệt:** `implementation(feature)` cần khi code compile tham chiếu API feature; `runtimeOnly(feature)` cần khi feature chỉ được tải/dùng khi chạy (plugin/service provider/reflection). Nếu feature có dependency API ngoài, khai báo ở `jsonSupportApi` để consumer compile nhận được type của dependency; nếu dependency chỉ dùng trong implementation, `jsonSupportImplementation` phù hợp hơn.

## 7. Feature dependencies phải được khai báo trên đúng scope

Ví dụ producer có feature tên `jsonSupport`:

~~~kotlin
dependencies {
    // Ví dụ khi thực sự thêm JSON library (cần mavenCentral hoặc repo khác).
    "jsonSupportImplementation"(
        "com.fasterxml.jackson.core:jackson-databind:2.17.2"
    )
}
~~~

Đây là **mảnh build script riêng**, không phải phần của demo offline. Khi consumer không yêu cầu feature, dependency Jackson riêng của feature **không cần** bị kéo theo do main capability. Khi consumer yêu cầu feature runtime, những dependencies của runtime variant được đưa vào graph để feature chạy.

Một số lựa chọn:

| Scope | Khi nào dùng? | Consumer nhận gì? |
| --- | --- | --- |
| `jsonSupportApi` | Public method/field của feature lộ kiểu của dependency. | Dependency có thể cần trên compile classpath khi consumer chọn API feature. |
| `jsonSupportImplementation` | JSON engine chỉ dùng bên trong feature implementation. | Tham gia runtime graph của feature, không nhất thiết lộ trên compile API của consumer. |
| `jsonSupportRuntimeOnly` | Provider/engine chỉ được load lúc chạy. | Được chọn khi consumer lấy runtime variant của feature. |
| `jsonSupportCompileOnly` | Class chỉ cần lúc compile feature, runtime được cung cấp từ nơi khác. | Không tự đưa vào runtime của consumer, cần hiểu contract. |

Ví dụ cấu hình có cả API/implementation khác nhau (các tọa độ **minh họa**, chỉ dùng nếu thư viện/phiên bản thật sự có trong repo):

~~~kotlin
dependencies {
    "jsonSupportApi"("com.fasterxml.jackson.core:jackson-core:2.17.2")
    "jsonSupportImplementation"(
        "com.fasterxml.jackson.core:jackson-databind:2.17.2"
    )
}
~~~

Đừng chuyển các dòng này vào `api`/`implementation` của **main** chỉ để compiler hết báo unresolved: như vậy tính năng JSON mất đi tính tùy chọn. Hãy sửa đúng feature source set và dependency scope.

**Lưu ý:** khi bạn đưa public types từ main vào API feature hoặc ngược lại, cần thiết kế rõ ranh giới source/classpath, tránh phụ thuộc vòng tròn giữa feature và main. Feature variant không tự biến cấu trúc Java code sai thành modularity đúng.

## 8. Feature artifact và các outgoing variants

Khi gọi `registerFeature("jsonSupport")`, Java plugins tự tạo các task/configurations liên quan feature và Gradle sẽ có outgoing variants như:

~~~text
Main:
  apiElements
  runtimeElements
  -> capability org.example:library:1.0

Feature:
  jsonSupportApiElements
  jsonSupportRuntimeElements
  -> capability org.example:library-json-support:1.0
~~~

Đây là **mô hình khái niệm**, không phải toàn bộ output `outgoingVariants`. Một feature thường có JAR riêng với **classifier theo tên feature**; tên file thực tế có thể chịu ảnh hưởng base name/version và quy ước/thiết lập của plugin.

Kiểm tra producer:

~~~bash
./gradlew :library:outgoingVariants
./gradlew :library:outgoingVariants --all
./gradlew :library:tasks --all
./gradlew :library:assemble
~~~

Task `outgoingVariants` cho biết mỗi variant cung cấp capability nào, attributes nào và artifact nào. Với Gradle hiện đại, flag `--all` giúp thấy cả legacy/configurations không có attributes vốn có thể bị ẩn trong report mặc định. Không cần in toàn bộ graph ra clipboard chỉ để xem feature; hãy tìm những mục bắt đầu bằng `jsonSupport`.

Nếu muốn xem một variant cụ thể và phiên bản Gradle hỗ trợ:

~~~bash
./gradlew :library:outgoingVariants --variant jsonSupportRuntimeElements
~~~

Bạn nên thấy capability feature và đường dẫn artifact tương ứng, không chỉ một file JAR được gắn vào publication “ngoài ngữ cảnh”.

### API vs runtime variant

Một Java consumer chọn `java-api` ở compileClasspath và `java-runtime` ở runtimeClasspath. Khi nó yêu cầu capability `library-json-support`, Gradle sẽ tìm variant của **feature** phù hợp với attributes của configuration đang resolve. Đừng ép người dùng chọn tên `jsonSupportRuntimeElements` bằng string một cách tùy tiện: để Gradle so khớp bằng attributes/capabilities sẽ ít gắn chặt vào chi tiết producer.

### Không nên publish một “extra JAR” mà không có feature model

Chỉ làm:

~~~kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            // artifact(someJar) chỉ gắn thêm một file, không tự tạo
            // feature capability và metadata dependency cho file đó.
        }
    }
}
~~~

là **mảnh minh họa khác biệt**. `artifact(...)` tự nó không cung cấp outgoing feature API/runtime variants, dependency graph hay capability. Nếu mục tiêu là một optional capability mà Gradle consumer có thể yêu cầu, hãy dùng `registerFeature`, sau đó publish `components["java"]`.

## 9. Capability tùy chỉnh và quy tắc exclusivity

Gradle cho phép tùy chỉnh capability bằng:

~~~kotlin
java {
    registerFeature("jsonSupport") {
        usingSourceSet(sourceSets.create("jsonSupport"))
        capability("org.example", "library-json-support", "1.0")
    }
}
~~~

Đây là **phương án thay thế declaration feature của mục 5**, không đăng ký cùng tên hai lần. Khi gọi `capability(group, name, version)`, Gradle **bỏ default capability được tạo bởi `registerFeature`**, nên bạn phải khai báo lại nếu còn muốn feature có capability theo quy ước.

Ví dụ nếu muốn thêm **một capability phụ** và **giữ lại capability convention**:

~~~kotlin
java {
    registerFeature("jsonSupport") {
        usingSourceSet(sourceSets.create("jsonSupport"))
        capability("org.example", "library-json-support", "1.0")
        capability("org.example", "json-writer", "1.0")
    }
}
~~~

Nếu bỏ dòng `library-json-support`, consumer dùng `requireCapability("org.example:library-json-support")` sẽ không tìm thấy capability ấy. Đừng tự sáng chế tên capability rồi quên sửa tất cả consumer.

### Capability là cơ chế chặn hai implementation không tương thích

Giả sử thư viện có hai feature loại trừ nhau: `mysqlSupport` và `postgresSupport`. Mỗi feature có capability riêng để consumer yêu cầu, **đồng thời** cả hai khai báo một capability chung `org.example:library-db-driver:1.0`. Khi cả hai bị kéo vào cùng một graph, Gradle có thể báo **capability conflict** vì hai variants tuy khác feature nhưng cùng tuyên bố cung cấp một chức năng độc quyền.

Mẫu **minh họa producer**, giả định bạn đã tạo source set tương ứng:

~~~kotlin
java {
    registerFeature("mysqlSupport") {
        usingSourceSet(sourceSets.create("mysqlSupport"))
        capability("org.example", "library-mysql-support", "1.0")
        capability("org.example", "library-db-driver", "1.0")
    }
    registerFeature("postgresSupport") {
        usingSourceSet(sourceSets.create("postgresSupport"))
        capability("org.example", "library-postgres-support", "1.0")
        capability("org.example", "library-db-driver", "1.0")
    }
}
~~~

Đây là **thiết kế minh họa**, không phải file hoàn chỉnh có code DB. Vì `capability(...)` thay default, chúng ta khai báo capability riêng **và** capability chung. Consumer yêu cầu cả hai có thể gặp conflict thay vì vô tình lắp hai DB drivers cạnh tranh. Khi một ứng dụng muốn lựa chọn một implementation, hãy chọn một feature rõ ràng; không tự thêm resolution rule để “hòa giải” xung đột mà chưa xác định đúng yêu cầu nghiệp vụ.

**Phân biệt hai loại khác nhau:** main `apiElements` và main `runtimeElements` cùng capability đại diện cho **các usages khác nhau**, nên trong một configuration Gradle chọn variant hợp lệ theo attributes. Hai feature cung cấp **capability độc quyền giống nhau** thể hiện cạnh tranh thực sự. Không thiết kế conflict capability chỉ để thay thế các package mà ứng dụng vốn có thể cần đồng thời.

## 10. Công bố feature bằng `maven-publish`

Ví dụ `library/build.gradle.kts` ở mục 5 đã có:

~~~kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "org.example"
version = "1.0"

java {
    registerFeature("jsonSupport") {
        usingSourceSet(sourceSets.create("jsonSupport"))
    }
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
    repositories {
        maven {
            name = "demo"
            url = uri(layout.buildDirectory.dir("published-repo"))
        }
    }
}
~~~

Đây là **bản cấu hình publish tối thiểu thay thế** khi chỉ cần tập trung công bố (mục 5 chứa thêm toolchain); tránh dán trùng cả hai khối vào cùng một file.

Với `maven-publish` (hoặc `ivy-publish`), Gradle có thể publish các additional feature variants của Java component. Trong Maven repository, publication có thể chứa:

- JAR chính của library.
- JAR tương ứng với `jsonSupport` (thường có classifier).
- Maven POM cho module chính.
- **Gradle Module Metadata** (`.module`) mô tả variants, capabilities, dependencies và artifact mapping.

Chạy:

~~~bash
./gradlew :library:generatePomFileForMavenJavaPublication
./gradlew :library:generateMetadataFileForMavenJavaPublication
./gradlew :library:publishMavenJavaPublicationToDemoRepository
~~~

Task cuối được tạo theo tên publication `mavenJava` và repository `demo`; kiểm tra `./gradlew :library:tasks --all` nếu dự án dùng tên khác. Repository trong bài nằm dưới `library/build/published-repo` và có thể bị xóa khi chạy `clean`; đây là nơi thử nghiệm, **không phải kho phát hành ổn định**.

Ví dụ layout dưới Maven repository (tên classifier/path cụ thể do Gradle quyết định):

~~~text
library/build/published-repo/
└── org/example/library/1.0/
    ├── library-1.0.jar
    ├── library-1.0.pom
    ├── library-1.0.module
    └── library-1.0-<feature-classifier>.jar
~~~

**Chú ý:** trong sơ đồ này, phần trong dấu ngoặc nhọn của tên file là **ký hiệu giải thích**, không phải tên artifact chính xác để copy vào build. Xem file thực tế sau publish hoặc `outgoingVariants`.

### Vì sao phải `from(components["java"])`?

Đó là cách publish **software component** đã được Java Library plugin cấu hình, bao gồm feature variants. Nếu chỉ publish một file tự chọn bằng `artifact(...)` mà không dựa trên Java component, publication có thể thiếu thông tin những variant nào cung cấp capability nào, dependency nào chỉ có ở feature, và consumer sẽ không thể chọn feature qua model của Gradle.

### Sources/Javadoc của feature

Nếu muốn công bố nguồn và tài liệu riêng cho feature:

~~~kotlin
java {
    registerFeature("jsonSupport") {
        usingSourceSet(sourceSets.create("jsonSupport"))
        withSourcesJar()
        withJavadocJar()
    }
}
~~~

Đây là **phương án thay thế khối `registerFeature`**, không đăng ký feature trùng. Gradle sẽ bổ sung artifacts/variants cho source và Javadoc tương ứng theo API Java feature. Tránh suy từ classifier “sources” rằng đó là binary feature JAR; chúng có mục đích khác nhau.

## 11. Gradle Module Metadata khác Maven POM và Ivy metadata

Đây là phần đặc biệt quan trọng trong cụm đề **“công bố tính năng tùy chọn”**.

### Với Gradle Module Metadata

Gradle `.module` có thể mô tả **đầy đủ** feature variants:

- Capability của main vs capability của `jsonSupport`.
- API/runtime attributes và các artifact cho từng feature.
- Dependency của feature tách khỏi dependency của main.
- Rich constraints/variants/capabilities khi publisher cung cấp.
- Consumer Gradle có thể yêu cầu `requireCapability(...)` để chỉ chọn phần mở rộng.

Khi `maven-publish` tạo publication theo chuẩn Gradle, `.module` thường được publish cùng POM. Gradle consumer dùng metadata này để hiểu đầy đủ variant-aware graph.

### Với Maven POM

Maven POM **không có native concept tương đương Gradle feature variants/capabilities**. Theo cách Gradle ánh xạ publication:

- Artifact của feature được upload như **artifacts có classifier**.
- Dependencies của feature có thể được biểu diễn là **Maven optional dependencies**.
- POM không mô tả capability và API/runtime feature variants đầy đủ. Maven consumer không thể viết `requireCapability`; nó phải cấu hình classifier/dependencies theo cơ chế Maven nếu muốn dùng phần tùy chọn.

Vì Maven optional dependencies không tự đi transitively tới consumer khác, việc chỉ thấy một dependency với `<optional>true</optional>` không đảm bảo Maven consumer đã nhận đúng binary feature và mọi dependency runtime của nó. **Không hứa cùng một behavior giữa Gradle và Maven khi metadata khả dụng khác nhau.**

### Với Ivy metadata

Ivy có configurations và có thể biểu diễn một số cấu hình feature như các configuration phụ. Nhưng Ivy metadata **không bảo toàn đầy đủ Gradle capabilities**; consumer phải lựa chọn configuration tương ứng thay vì dùng Gradle capability như trên. Một số phần dependency mapping khi publish có thể bị mất hoặc không tương đương. Hãy kiểm chứng bằng consumer thật.

| Thông tin | Gradle `.module` | Maven `pom.xml` | Ivy `ivy.xml` |
| --- | --- | --- | --- |
| Main artifact | Có | Có | Có |
| Feature artifact | Có, gắn với variant | Có thể upload với classifier | Có thể upload |
| Feature dependency graph | Giữ theo variant | Map thành optional dependencies; mất ngữ nghĩa variant | Theo configurations/mapping, không tương đương hoàn toàn |
| Capability riêng của feature | **Có** | **Không** | **Không** |
| Consumer tự chọn feature bằng `requireCapability` | **Có**, nếu có metadata đúng | Không dựa trên POM đơn thuần | Không như metadata Gradle |
| Rich version/attribute semantics | Hỗ trợ đầy đủ hơn | Giới hạn/lossy | Giới hạn/lossy |

**Không tắt Gradle Module Metadata chỉ để không thấy compatibility warnings.** Cảnh báo có thể chính là dấu hiệu Maven/Ivy không biểu diễn đủ features/constraints. Nếu bạn thật sự phải hỗ trợ consumer Maven, hãy viết tài liệu riêng về classifier, dependencies và chạy integration tests với Maven consumer, thay vì chỉ bỏ qua warning.

## 12. Consumer ngoài build: cần metadata đã được publish thật

Một multi-project Gradle build với `implementation(project(":library"))` có thể tiêu thụ feature mà **không phải publish artifact trước**. Gradle có Java component model của producer trực tiếp.

Nhưng nếu consumer là **dự án Gradle khác**, producer phải publish metadata và artifacts vào repository mà consumer truy cập được.

Ví dụ sau là **mảnh `build.gradle.kts` của một consumer khác**, giả định `org.example:library:1.0` đã được publish đúng và repository URL trỏ đến nơi có cả `.pom`/`.module` và các JAR:

~~~kotlin
plugins {
    application
}

repositories {
    maven {
        url = uri("/absolute/path/to/published-repo")
    }
}

dependencies {
    implementation("org.example:library:1.0")

    runtimeOnly("org.example:library:1.0") {
        capabilities {
            requireCapability("org.example:library-json-support")
        }
    }
}
~~~

Path absolute là **điểm cần thay bằng path thực tế của repository đã publish**. Đoạn này chưa phải file runnable độc lập vì còn thiếu `application.mainClass`, source và path thật; cách lấy Gradle published feature được minh họa chính xác. Không đặt kho local `library/build/published-repo` làm nguồn dài hạn của CI: chỉ dùng trong demo, vì `clean` có thể xóa nó.

Khi consumer dùng repository chỉ chứa POM mà **không có Gradle Module Metadata**, nó có thể **không tìm thấy capability** mà producer đã công bố trong build gốc. Hãy kiểm tra có file `.module`, POM có metadata marker, artifact classifier và dependency rules phù hợp.

### Một phép kiểm chứng nghiêm ngặt

1. Trong producer build, chạy `publish...Repository`.
2. Xem thư mục repository có JAR chính, JAR feature, `.pom` và `.module`.
3. Tạo một consumer project **độc lập** không dùng `project(":library")`.
4. Khai báo module `org.example:library:1.0` từ repository đã publish.
5. Khi chỉ yêu cầu main, feature class không được xuất hiện chỉ vì POM/metadata có đề cập feature.
6. Khi yêu cầu `library-json-support`, runtime classpath phải có feature artifact và những dependencies riêng của feature.
7. Kiểm tra compile/runtime behavior thay vì suy từ việc publish task trả `BUILD SUCCESSFUL`.

## 13. Không muốn publish feature thì làm gì?

`FeatureSpec` có API `disablePublication()`. Nó được dùng khi bạn muốn một feature có thể hoạt động trong build nhưng **không cần đưa feature đó ra external repositories**.

Ví dụ **mảnh cấu hình**, thay thế declaration feature:

~~~kotlin
java {
    registerFeature("internalDiagnostics") {
        usingSourceSet(sourceSets.create("internalDiagnostics"))
        disablePublication()
    }
}
~~~

Với lựa chọn này, feature vẫn có thể tồn tại trong model của project để các project khác **trong cùng build** tiêu thụ khi phù hợp, nhưng Gradle **không publish feature variant ra external repositories**. Vì vậy, một Gradle consumer bên ngoài **không thể mong** có capability/artifact đó từ module publish.

**Đừng nhầm** `disablePublication()` với việc không gọi `publish`: cái đầu là lựa chọn chính sách publication của feature; cái sau chỉ là chưa chạy task publish. Cũng không nhầm với việc “ẩn source code” trong Git; code vẫn tồn tại trong repository và build artifact có thể được tạo trong nội bộ.

Nếu muốn publish main và một số feature nhưng không publish vài variant phụ (ví dụ sources/Javadoc riêng), có các API `AdhocComponentWithVariants.withVariantsFromConfiguration(...).skip()` cho những tình huống nâng cao; nhưng không dùng tùy tiện nếu sẽ làm producer/consumer không nhất quán. Với nhu cầu đơn giản, `disablePublication` rõ ý định hơn.

## 14. Feature tùy chọn khác Maven optional dependency như thế nào?

**Maven `<optional>true</optional>`** chủ yếu diễn tả dependency không nên tự lan qua graph consumer. Nhưng nó không cho consumer biết **tính năng nào yêu cầu dependency đó**, cũng không xác định class/artifact đặc thù và API/runtime variant riêng.

**Gradle feature variant** diễn tả đúng mô hình:

~~~text
Main library:
  capability org.example:library:1.0
  API/core classes
  main dependencies

Optional jsonSupport:
  capability org.example:library-json-support:1.0
  separate Java source set + feature JAR
  optional feature dependencies (e.g. Jackson)
  API/runtime variants

Consumer:
  require main only  -> core classes
  require main + json capability -> core + feature and its deps
~~~

Nhờ capability, Gradle consumer có thể thể hiện rõ “tôi cần JSON support”. Nếu publisher chỉ thêm dependency Jackson vào main bằng `runtimeOnly`, thì **mọi consumer runtime của main có thể nhận Jackson**, trái với mục tiêu optional. Nếu publisher chỉ thêm dependency vào Maven POM dưới dạng optional mà không có feature variant/extra artifact model, consumer Gradle không tự biết cần chọn capability nào.

### Trường hợp nên chọn module riêng thay vì feature variant

Feature variants tốt khi mở rộng nhỏ có quan hệ chặt với thư viện chính, muốn chung version/publication lifecycle, và consumer Gradle là nhóm chính.

Nên cân nhắc **module riêng** (ví dụ `library-core` và `library-json`) nếu:

- Feature có vòng đời release/version khác main.
- Người dùng chủ yếu là Maven/Gradle xen kẽ và cần tương thích POM đơn giản.
- Feature có dependency graph rất lớn, build/publish/test cần độc lập.
- Cần một artifact độc lập được phần lớn ecosystem hiểu mà không dựa vào Gradle `.module`.
- Có nhiều sản phẩm chỉ cùng dùng API chung, không thực sự là một feature của một component duy nhất.

Gradle feature variants không có nghĩa mọi tính năng plugin đều nên gộp vào một artifact Maven; thiết kế theo khả năng tiêu thụ thực tế.

## 15. Đọc dependency graph và giải quyết lỗi variant

Các lệnh cần nhớ:

~~~bash
# Producer: tên outgoing variants, capability, attributes, artifact
./gradlew :library:outgoingVariants --all

# Consumer: dependencies ở compile/runtime
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath

# Điều tra vì sao library được chọn ở runtime
./gradlew :app:dependencyInsight --dependency library --configuration runtimeClasspath

# Nhận các task build và publish hiện có
./gradlew :library:tasks --all

# Build toàn bộ, kể cả project library và app
./gradlew build
~~~

Đối với tình huống nhiều variant, `dependencyInsight --all-variants` có thể hiện thêm các variants và selection reasons ở phiên bản Gradle hỗ trợ; `resolvableConfigurations` có thể giúp xem consumer attributes của classpath.

~~~bash
./gradlew :app:dependencyInsight --dependency library --configuration runtimeClasspath --all-variants
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath
~~~

**Thứ tự chẩn đoán:**
1. `:library:outgoingVariants` có feature `jsonSupportRuntimeElements` và capability mong đợi không?
2. Group/name/version của capability có đúng không? `jsonSupport` được chuyển thành `json-support`.
3. App có khai báo hai dependencies cho main và feature không? `runtimeOnly` có đi vào `runtimeClasspath` không?
4. Variants có attributes phù hợp `java-api`/`java-runtime`/JVM target không? Nếu không, Gradle có thể báo `No matching variant`.
5. Nếu consumer ngoài build, repository có `.module` không? POM đơn lẻ không giữ capabilities.
6. Nếu feature class tồn tại nhưng Jackson (hoặc dependency feature) bị thiếu, xem `jsonSupportRuntimeElements`/`jsonSupportImplementation`, không sửa bằng cách kéo Jackson vào main một cách vội vàng.
7. Nếu có capability conflict, tìm hai providers của cùng capability và quyết định consumer cần một hay cả hai.
8. Khi đã sửa, kiểm thử **artifact thực**, class loading và behavior lúc chạy; không chỉ xem `BUILD SUCCESSFUL`.

## 16. Bảng lỗi thường gặp

| Dấu hiệu | Nguyên nhân hay gặp | Cách sửa |
| --- | --- | --- |
| `Could not find ... capability library-json-support` | Sai tên capability, feature chưa register, custom capability làm mất default, hoặc thiếu `.module`. | Xem `outgoingVariants` và metadata; sửa `requireCapability`/tên feature. |
| `No matching variant` | Consumer attributes không khớp Java API/runtime/JVM target/feature. | Xem outgoing/resolvable variants, Java toolchain và yêu cầu consumer. |
| `JsonFeature` có lúc compile, runtime lại thiếu | Khai báo nhầm scope `compileOnly` hoặc runtime variant không được yêu cầu. | Dùng `implementation(feature)` nếu import API; `runtimeOnly(feature)` nếu chỉ runtime; giữ main dependency. |
| Feature bị kéo vào app dù không muốn | Feature dependencies đặt ở main `implementation`/`runtimeOnly`, hoặc build logic auto-require feature. | Đưa dependency vào `jsonSupportImplementation`/`jsonSupportRuntimeOnly` và chỉ opt-in khi consumer cần. |
| Consumer chỉ lấy main nhưng source import `JsonFeature` | Feature chưa trên compileClasspath. | Chuyển sang `implementation(project(":library")) { capabilities { ... } }`. |
| App dùng `runtimeOnly(feature)` và Java import feature trực tiếp | Scope không cung cấp feature API lúc compile. | Dùng `implementation(feature)` hoặc bỏ compile-time import. |
| Kotlin DSL `Unresolved reference: jsonSupportImplementation` | Generated accessor cho configuration không có/được tạo sau thời điểm tạo accessor. | Dùng `"jsonSupportImplementation"("g:n:v")` hoặc `add("jsonSupportImplementation", "...")`. |
| `Could not resolve all ... capability conflict` | Hai variants/modules cùng cung cấp capability độc quyền. | Chọn một feature đúng nhu cầu hoặc thiết kế capability lại; không tắt conflict rule bừa bãi. |
| JAR feature publish nhưng consumer không chọn được | Chỉ gắn `artifact(extraJar)` hoặc thiếu `.module`/feature metadata. | Publish `from(components["java"])` kèm feature variants, xác minh metadata. |
| Maven consumer không có dependencies của optional feature | Maven POM không diễn tả đầy đủ Gradle feature model, optional không transitively tự thêm. | Hướng dẫn classifier/dependency cho Maven hoặc tách module riêng. |
| `JsonFeature` không được đóng JAR | Source code đặt sai source set path hoặc feature task không chạy. | Kiểm tra `src/jsonSupport/java`, `tasks --all`, feature JAR output. |
| Runtime classpath thiếu thư viện ngoài của feature | Dependency đặt nhầm main/feature bucket hoặc scope `compileOnly`. | Dùng `jsonSupportImplementation`/`jsonSupportRuntimeOnly` đúng vai trò. |
| Consumer ngoài build khác consumer dùng `project(":library")` | Publication thiếu feature metadata, POM only, repository không có .module. | Test consumer độc lập với Gradle Module Metadata đã publish. |
| `disablePublication` rồi không tìm thấy feature ở Maven repo | Feature cố ý không được publish. | Bỏ `disablePublication` nếu contract public cần feature. |
| Đặt `usingSourceSet(sourceSets["main"])` và code lẫn lộn | Dùng main source set cho feature trái khuyến cáo. | Tách source set và xác định dependencies/output riêng. |
| Consumer lẫn main/feature version khác nhau | Module tọa độ và capability/version bị hard-code không thống nhất. | Chọn convention group/name/version hoặc quản lý version thống nhất, kiểm tra graph. |

## 17. Kiểm thử tối thiểu trước khi publish

Một checklist test giúp phát hiện vấn đề trước khi thư viện ra môi trường ngoài:

### Producer tests

- [ ] `:library:compileJava` thành công cho main.
- [ ] Task compile Java của source set `jsonSupport` thành công.
- [ ] `:library:outgoingVariants` hiển thị main và feature capability đúng.
- [ ] Feature artifact có class riêng, không dựa vào việc class được tình cờ đóng vào main JAR.
- [ ] Phần dependencies tùy chọn nằm trong feature buckets, không nằm trong main `implementation` khi không cần.
- [ ] Nếu tính năng là mutual exclusive, shared capability được khai báo nhất quán giữa variants.

### Consumer tests

- [ ] Consumer chỉ main chạy được mà không cần feature và không vô tình nhận dependencies feature.
- [ ] Consumer có `runtimeOnly` feature chạy được theo cơ chế optional runtime.
- [ ] Consumer import API feature compile được khi dùng `implementation` feature.
- [ ] Các dependency riêng của feature được resolve khi feature được chọn.
- [ ] Tắt feature không làm main library bị vỡ do phụ thuộc ngược vào feature.
- [ ] Vùng `compileClasspath`/`runtimeClasspath` và selected variants đúng như contract.

### Publication tests

- [ ] `maven-publish`/`ivy-publish` cấu hình đúng; publication lấy Java component.
- [ ] Đã tạo và kiểm tra `.module`, POM, feature artifact và checksums.
- [ ] Gradle consumer **ngoài build** chọn được feature bằng capability.
- [ ] Nếu hỗ trợ Maven/Ivy consumer, có hướng dẫn riêng và test dependency/classifier thực.
- [ ] Không bỏ qua metadata compatibility warnings mà không hiểu những gì bị mất.
- [ ] Không để `disablePublication` trên feature phải công khai.
- [ ] Repository, artifact coordinates và versions phù hợp chính sách CI/release.

## 18. Câu hỏi tự kiểm tra

1. **Feature variant có phải chỉ là một JAR classifier không?** Không. Nó gồm capability, attributes, dependencies và artifact tương ứng.
2. **Tên `jsonSupport` tạo capability nào trong `org.example:library:1.0`?** Theo convention là `org.example:library-json-support:1.0`.
3. **Tại sao cần `registerFeature(...)` trên Java Library plugin?** Để Gradle tạo outgoing feature variants và model mà consumer có thể chọn.
4. **Consumer chỉ cần main có nhận JSON feature mặc định không?** Không, nếu producer giữ đúng ranh giới và consumer không yêu cầu capability feature.
5. **Main và feature có thể được tiêu thụ cùng nhau không?** Có, khi chúng cung cấp capabilities khác nhau và consumer khai báo cả hai dependencies.
6. **`runtimeOnly(feature)` có cho phép Java source import class feature không?** Không. Import ở compile time cần dependency feature trong compileClasspath như `implementation(feature)`.
7. **Nếu feature dùng Jackson chỉ bên trong, đặt dependency vào đâu?** Thường `jsonSupportImplementation`, không phải main `implementation`.
8. **`requireCapability` chọn điều gì?** Yêu cầu capability của variant; attributes của consumer vẫn quyết định API/runtime variant phù hợp.
9. **Nếu gọi custom `capability(...)`, Gradle còn giữ default feature capability không?** Không tự động; cần khai báo lại nếu muốn giữ.
10. **Hai feature cùng tuyên bố capability `library-db-driver` có thể đồng thời nằm trên classpath không?** Gradle có thể báo conflict; đó là cách mô hình hóa mutual exclusion.
11. **Vì sao Maven POM không giữ đầy đủ feature model?** Maven không có native Gradle capabilities/variants; Gradle map dependencies thành optional và artifacts qua classifier.
12. **Dùng gì để consumer Gradle ngoài build thấy feature đầy đủ?** Module đã publish kèm Gradle Module Metadata và artifacts tương ứng.
13. **`disablePublication()` có làm feature biến mất trong project cùng build không?** Không nhất thiết; nó chủ yếu tắt external feature publication.
14. **Lệnh nào cho biết producer công bố capability/attributes/artifact gì?** `./gradlew :library:outgoingVariants`.
15. **Lỗi `No matching variant` có thể đến từ đâu?** Capability/attributes/JVM target không tương thích hoặc metadata thiếu, cần đọc outgoing/resolvable reports.
16. **Có nên dùng `sourceSets["main"]` làm source set feature không?** Không, Gradle khuyến cáo dùng source set riêng.
17. **Nếu người dùng chủ yếu dùng Maven, lúc nào nên cân nhắc module riêng?** Khi cần hỗ trợ feature như artifact/module độc lập với metadata POM rõ ràng.

## 19. Checklist thực hành cuối cùng

- [ ] Feature là khả năng tùy chọn thật, không phải một nhãn tùy tiện cho cùng API main.
- [ ] Producer dùng Java plugin hỗ trợ `registerFeature` và source set riêng.
- [ ] Group, version, project/module name được xác định trước khi chuẩn hóa capability.
- [ ] Dependencies feature đặt trong đúng `featureNameApi`/`featureNameImplementation`/`featureNameRuntimeOnly`.
- [ ] Consumer chọn main riêng và yêu cầu capability của feature khi cần.
- [ ] Phân biệt `implementation` của feature API và `runtimeOnly` của feature runtime.
- [ ] Nếu tự định nghĩa capability, kiểm tra default capability bị thay và thêm lại khi cần.
- [ ] Không thiết kế shared capability cho các feature có thể tồn tại đồng thời.
- [ ] Publication dùng Java component; `.module` và feature artifacts được kiểm tra.
- [ ] Maven/Ivy consumer được kiểm thử riêng vì metadata chuyển đổi có thể mất thông tin.
- [ ] `outgoingVariants`, `dependencies`, `dependencyInsight` được dùng để chẩn đoán thay vì đoán tên JAR.
- [ ] Có test main-only, feature opt-in, API feature compilation và external consumer.
- [ ] Tránh hard-code version/feature capability không nhất quán giữa module và consumer.
- [ ] Giữ khả năng tái lập bằng Gradle Wrapper, pinned dependencies và CI checks.

## Nguồn tham khảo chính thức

- [Gradle — How to Create Feature Variants for a Library](https://docs.gradle.org/current/userguide/how_to_create_feature_variants_of_a_library.html): `registerFeature`, `usingSourceSet`, naming convention, capabilities, feature dependency scopes, publish/consume và mutual exclusion.
- [Gradle — Capabilities](https://docs.gradle.org/current/userguide/component_capabilities.html): nghĩa của capability và conflict resolution.
- [Gradle — Variant-Aware Dependency Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): API/runtime attributes, `outgoingVariants` và diagnostics.
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html): capability/feature mapping sang Maven POM, Ivy, compatibility warnings.
- [Gradle — Publishing Setup](https://docs.gradle.org/current/userguide/publishing_setup.html): publication với `from(components["java"])` và repository.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): `MavenPublication`, metadata và task publish.
- [Gradle Java API — FeatureSpec](https://docs.gradle.org/current/javadoc/org/gradle/api/plugins/FeatureSpec.html): `usingSourceSet`, `capability`, `disablePublication`, `withSourcesJar`, `withJavadocJar`.
- [Gradle Java API — ModuleDependencyCapabilitiesHandler](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/ModuleDependencyCapabilitiesHandler.html): `requireCapability` và `requireFeature`.
- [Gradle — Viewing/Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight`, `--all-variants`.
- [Gradle — Migrating from Maven](https://docs.gradle.org/current/userguide/migrating_from_maven.html): optional dependencies và feature variants.
