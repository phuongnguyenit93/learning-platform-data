# Java Platform plugin và khai báo dependency constraints trong Gradle

## 1. Mục tiêu và bối cảnh

Khi một ứng dụng Java lớn được chia thành nhiều module, mỗi module có thể khai báo phiên bản riêng cho Jackson, Guava, Commons Lang, SLF4J, JDBC driver hoặc một tập thư viện nội bộ. Nếu để từng module tự quản lý, phiên bản trực tiếp và bắc cầu dễ lệch nhau: module A dùng `library-x:1.2`, module B dùng `library-x:1.5`, còn module C kéo `library-x:1.4` từ dependency khác. Gradle có cơ chế conflict resolution, nhưng **việc Gradle chọn được một version không chứng minh tổ hợp ấy tương thích về API, ABI hoặc hành vi**.

Plugin **`java-platform`** cho phép tạo một **platform component chuyên công bố dependency constraints**. Những project tiêu thụ platform dùng `platform(project(":platform"))` hoặc `platform("group:module:version")` để kế thừa chính sách phiên bản chung. Platform không sinh JAR hay biên dịch Java; nhiệm vụ của nó là **mô tả yêu cầu/khuyến nghị phiên bản**.

Sau bài học, bạn có thể:

1. Giải thích `java-platform`, platform component, dependency constraints và Gradle conflict resolution.
2. Tạo subproject `:platform` chứa `constraints { api(...) ; runtime(...) }`.
3. Dùng `platform(project(":platform"))` trong project Java tiêu thụ, khai báo dependency **không ghi version** khi đã được platform quản lý.
4. Hiểu vì sao constraint không tự thêm một thư viện vào classpath và vì sao version từ constraint vẫn có thể được nâng lên.
5. Phân biệt `api` và `runtime` constraints, cũng như `apiElements`/`runtimeElements` variants của platform.
6. Dùng rich versions: `require`, `strictly`, `prefer`, `reject`, `because`.
7. Import Maven BOM vào Java Platform bằng `javaPlatform { allowDependencies() }` và `api(platform("..."))`.
8. Xuất bản platform thông qua `maven-publish`, biết sự khác nhau giữa Gradle Module Metadata và Maven BOM/POM.
9. Phân biệt `java-platform` với version catalog và `enforcedPlatform`.
10. Dùng `dependencies`, `dependencyInsight`, dependency locking và các test để kiểm tra kết quả resolution thực tế.

Ví dụ sử dụng **Gradle Kotlin DSL**, Java 17 và một số phiên bản thư viện có thật phục vụ minh họa. Chúng không được trình bày như phiên bản mới nhất hay phù hợp mặc định với mọi môi trường. Trọng tâm nằm trong nhóm **Catalog và platform** của Build Tool Gradle.

## 2. Platform là gì?

Một Gradle Java Platform là **software component không có source/binaries**, chuyên cung cấp dependency constraints để các project khác resolve dependency nhất quán.

Sơ đồ:

~~~text
                  :platform
              (java-platform)
                    |
           constraints:
           commons-lang3 >= 3.14.0
           gson          >= 2.10.1
           slf4j-simple  >= 2.0.9 (runtime)
                    |
          +---------+----------+
          |                    |
          v                    v
      :app (Java)          :service (Java)
          |                    |
     platform(...)         platform(...)
          |                    |
     khai báo module       khai báo module
     không có version      không có version
          |                    |
          +------ Gradle resolve dependency graph
~~~

Các constraints không có nghĩa ba JAR luôn được tải vào mọi project. Chúng chỉ có tác dụng **nếu dependency tương ứng xuất hiện** trong graph, trực tiếp hoặc bắc cầu.

Ví dụ platform có:

~~~kotlin
dependencies {
    constraints {
        api("org.apache.commons:commons-lang3:3.14.0")
    }
}
~~~

Consumer chỉ dùng Gson mà không khai báo hoặc không kéo Commons Lang từ module nào khác thì Commons Lang **không tự xuất hiện**. Muốn dùng Commons Lang, consumer cần dependency:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3")
}
~~~

Ở consumer, việc bỏ version là hợp lệ khi platform hoặc một constraint khác cung cấp yêu cầu phiên bản đủ để resolve.

### 2.1. Constraint so với direct dependency

| Cấu hình | Có đưa module vào graph? | Vai trò |
| --- | --- | --- |
| `implementation("g:m:1.2")` | Có | Dependency trực tiếp, yêu cầu version 1.2 |
| `constraints { implementation("g:m:1.2") }` | Không, trừ khi module đã xuất hiện từ nơi khác | Khai báo yêu cầu version khi module được dùng |
| `implementation(platform(project(":platform")))` | Đưa platform component vào graph, không kéo toàn bộ JAR trong constraints | Áp chính sách version của platform |
| `api("g:m:1.2")` trong `constraints` của Java Platform | Không tự kéo JAR | Constraint được export qua API của platform |
| `runtime("g:m:1.2")` trong `constraints` của Java Platform | Không tự kéo JAR | Constraint cho runtime của platform |

**Không nhầm `api(...)` trong `constraints {}` với `api(...)` ở dependencies thông thường.** Tên configuration có thể giống nhau, nhưng khi nằm trong block `constraints`, ta khai báo constraint chứ không phải một dependency mới.

### 2.2. Vì sao cần một project platform riêng?

Các dự án nhiều module thường có mục tiêu:

- Tập trung những phiên bản thư viện đã được kiểm thử.
- Cho phép thay version ở một nơi và review thay đổi có kiểm soát.
- Tách cấu hình dependency của business module khỏi chính sách chung.
- Công bố “bộ phiên bản được hỗ trợ” để module khác cùng tổ chức có thể sử dụng.
- Tận dụng metadata giàu thông tin của Gradle để truyền constraints sang consumers.

Cần thận trọng: một **regular platform** không tự đảm bảo toàn bộ graph bị khóa cứng ở các version của nó. Dependency khác có thể yêu cầu version cao hơn; Gradle sẽ giải quyết theo các quy tắc version/constraint đang áp dụng.

## 3. Plugin `java-platform` hoạt động thế nào?

Trong **platform/build.gradle.kts**:

~~~kotlin
plugins {
    `java-platform`
}
~~~

Tương đương Groovy DSL:

~~~groovy
plugins {
    id 'java-platform'
}
~~~

Điểm cốt lõi:

1. Tạo những cấu hình cần để khai báo và **export constraints**.
2. Tạo Java Platform component với các variants phục vụ compile/runtime.
3. Có thể xuất bản component như Gradle Module Metadata và Maven BOM.
4. Không tạo các task compile Java hay JAR chứa classes.
5. **Không thể áp dụng cùng `java` hoặc `java-library` trong một project**: một project là platform không có binary, hoặc project sản xuất binary.

Muốn có platform và thư viện Java, tạo **hai project khác nhau**.

### 3.1. `api` và `runtime` là declarable configurations

Trong platform:

~~~kotlin
dependencies {
    constraints {
        api("com.google.code.gson:gson:2.10.1")
        runtime("org.slf4j:slf4j-simple:2.0.9")
    }
}
~~~

- `api`: constraint dùng khi consumer biên dịch dựa trên platform; cũng xuất hiện ở runtime vì runtime configuration kế thừa `api`.
- `runtime`: constraint bổ sung cho graph runtime, không nhất thiết áp vào compile classpath.

Những tên này **không** có nghĩa project platform tự tải Gson hoặc SLF4J. Đây là bộ **declarable configurations** để công bố yêu cầu phiên bản.

### 3.2. Các variants của platform

Plugin cung cấp những outgoing variants tiêu biểu:

| Variant | Ý nghĩa |
| --- | --- |
| `apiElements` | Constraints/dependencies thuộc `api` cho compile-time consumer |
| `runtimeElements` | Constraints thuộc `runtime` và `api` cho runtime consumer |
| `enforcedApiElements` | Biến thể constraints mang ngữ nghĩa enforced cho compile |
| `enforcedRuntimeElements` | Biến thể constraints mang ngữ nghĩa enforced cho runtime |

`runtime` kế thừa `api`, do đó một constraint ở `api` cũng có mặt ở runtime. Với consumer dùng `enforcedPlatform(...)`, Gradle chọn biến thể enforced tương ứng thay vì biến thể regular.

Có thể kiểm tra variants của một project bằng task phù hợp, chẳng hạn:

~~~bash
./gradlew :platform:outgoingVariants --console=plain
~~~

Task/định dạng báo cáo có thể phụ thuộc phiên bản Gradle Wrapper; nếu không có task, xem tài liệu đi kèm Wrapper và không giả định platform thiếu variants.

### 3.3. Vì sao plugin cấm dependencies thông thường mặc định?

Nhiệm vụ chính của platform là khai báo constraints, nên nếu viết:

~~~kotlin
// Ví dụ chưa được phép với java-platform mặc định.
dependencies {
    api("com.google.code.gson:gson:2.10.1")
}
~~~

Gradle sẽ **từ chối** direct dependencies của Java Platform theo mặc định để tránh nhầm constraint với dependency.

Nếu có nhu cầu hợp lý như **import một BOM/platform khác**, phải opt-in:

~~~kotlin
javaPlatform {
    allowDependencies()
}
~~~

Sau đó mới thêm platform dependency như `api(platform("group:bom:version"))`. Không bật `allowDependencies()` chỉ để biến platform thành project thư viện thông thường; platform vẫn không sản xuất bytecode.

## 4. Thực hành đầy đủ: Java Platform + ứng dụng Java 17

Bài thực hành này có đủ file, plugin và lệnh chạy. Không cần tạo publication hay đăng nhập kho riêng. Cần Gradle Wrapper và JDK 17 tương thích; project có thể tải dependency từ Maven Central khi có network.

### 4.1. Cấu trúc project

~~~text
platform-lab/
├── settings.gradle.kts
├── platform/
│   └── build.gradle.kts
├── app/
│   ├── build.gradle.kts
│   └── src/main/java/demo/App.java
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/...
~~~

Nếu project mới chưa có Wrapper, tạo bằng lệnh Gradle theo quy trình được tổ chức cho phép rồi dùng Wrapper cho tất cả lệnh minh họa.

**settings.gradle.kts**

~~~kotlin
rootProject.name = "platform-lab"

include(":platform", ":app")
~~~

### 4.2. platform/build.gradle.kts

~~~kotlin
plugins {
    `java-platform`
}

dependencies {
    constraints {
        // Dependencies mà app dùng ở compile time và runtime.
        api("org.apache.commons:commons-lang3:3.14.0") {
            because("Phiên bản Commons Lang đã kiểm thử")
        }

        api("com.google.code.gson:gson:2.10.1") {
            because("Phiên bản Gson đã kiểm thử")
        }

        // Ràng buộc chỉ cần ở runtime.
        runtime("org.slf4j:slf4j-simple:2.0.9") {
            because("Runtime logging provider của môi trường demo")
        }
    }
}
~~~

Giải thích:

- Plugin `java-platform` cung cấp configurations `api` và `runtime`.
- `constraints { api(...) }` công bố version cho Commons Lang và Gson **mà không tự đưa JAR nào vào classpath**.
- `runtime(...)` minh họa ràng buộc chỉ được dùng khi resolver chọn runtime variant của platform.
- `because(...)` giúp diễn giải lý do trong Gradle dependency reports khi có thể.
- Các version là ví dụ có thật để người đọc tái tạo; không suy ra chúng mới nhất.

### 4.3. app/build.gradle.kts

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

dependencies {
    // Import policy phiên bản do :platform khai báo.
    implementation(platform(project(":platform")))

    // Không cần ghi version lần nữa.
    implementation("org.apache.commons:commons-lang3")
    implementation("com.google.code.gson:gson")

    // Version từ runtime constraint của :platform.
    runtimeOnly("org.slf4j:slf4j-simple")
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

application {
    mainClass.set("demo.App")
}
~~~

Giải thích:

1. `application` áp dụng cơ chế Java application, có task `:app:run`.
2. `implementation(platform(project(":platform")))` đưa platform vào graph.
3. Hai dòng `implementation` chỉ nêu coordinates, version do platform/other constraints cung cấp.
4. `runtimeOnly` đưa SLF4J Simple vào runtime classpath; version đến từ constraint trong `runtime` variant.
5. Nếu bỏ `runtimeOnly(...)`, constraint runtime **không tự thêm SLF4J Simple**.
6. `java.toolchain` dùng Java 17; phải có JDK 17 hoặc một cơ chế cấp phát toolchain được cấu hình tương ứng.
7. `application.mainClass` chỉ tên class chính sẽ chạy.

### 4.4. app/src/main/java/demo/App.java

~~~java
package demo;

import com.google.gson.JsonObject;
import org.apache.commons.lang3.StringUtils;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        String message = StringUtils.capitalize("gradle");

        JsonObject json = new JsonObject();
        json.addProperty("message", message);

        System.out.println(json.toString());
    }
}
~~~

Đây là chương trình Java 17 hợp lệ. `StringUtils.capitalize` từ Apache Commons Lang chuyển `"gradle"` thành `"Gradle"`. `JsonObject` của Gson sinh chuỗi JSON có trường `message`.

### 4.5. Chạy từ thư mục root

Linux/macOS:

~~~bash
./gradlew :app:run --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:run --console=plain
~~~

**Dòng stdout do chương trình Java in ra:**

~~~json
{"message":"Gradle"}
~~~

Gradle sẽ in thêm thông tin về task như `:app:compileJava`, `:app:run` và kết quả build. Đừng coi phần log của Gradle là stdout cố định; chỉ có dòng JSON ở trên là output do code Java của ví dụ tạo ra.

Điều kiện chạy: có JDK/toolchain và truy cập được repository chứa module yêu cầu. Nếu đang offline mà chưa có dependency trong cache, Gradle có thể không resolve được artifact. Đây là vấn đề môi trường, không phải sai cơ chế Java Platform.

### 4.6. Xem selected versions và constraints

~~~bash
./gradlew :app:dependencies \
  --configuration compileClasspath \
  --console=plain

./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:dependencies --configuration compileClasspath --console=plain
.\gradlew.bat :app:dependencies --configuration runtimeClasspath --console=plain
~~~

Tìm những module/constraint liên quan:

~~~text
project :platform
org.apache.commons:commons-lang3:3.14.0
com.google.code.gson:gson:2.10.1
org.slf4j:slf4j-simple:2.0.9
~~~

Đây là những mục cần nhận diện, **không phải bản chép chính xác** của toàn bộ báo cáo: tùy Gradle version, một constraint được đánh dấu `(c)` hoặc node được rút gọn `(*)`.

Hãy quan sát:

- `compileClasspath` có Gson và Commons Lang để compile `App`.
- `runtimeClasspath` có thêm SLF4J Simple do consumer đã khai báo `runtimeOnly(...)`.
- Constraints từ `:platform` áp dụng cho module được dùng mà không tự tải các module khác.

### 4.7. Một bài thử có chủ đích

Trong `app/build.gradle.kts`, thử xóa dòng:

~~~kotlin
runtimeOnly("org.slf4j:slf4j-simple")
~~~

Sau đó xem lại `runtimeClasspath`. Dù platform vẫn có `runtime("org.slf4j:slf4j-simple:2.0.9")`, module SLF4J Simple **không còn được thêm chỉ vì constraint** (trừ khi dependency khác kéo nó vào). Đây là cách kiểm chứng thực nghiệm cho ý nghĩa “constraint không phải dependency”.

Khôi phục dòng nếu muốn giữ ví dụ gốc.

## 5. Cách Gradle dùng constraints khi chọn phiên bản

Giả sử:

~~~text
:platform yêu cầu constraint -> commons-lang3:3.14.0
:app yêu cầu               -> commons-lang3 (không version)
other-library yêu cầu       -> commons-lang3:3.15.0
~~~

Gradle có thể chọn `3.15.0` nếu các yêu cầu khác cho phép. **Một constraint thông thường không phải hard pin**, mà hoạt động như yêu cầu phiên bản (thường ít nhất bằng version nêu ra) trong conflict resolution.

Dù cùng một module có nhiều requested versions, Gradle sẽ chọn một version cho configuration theo các quy tắc áp dụng. Không nên kết luận Gradle đang chạy đồng thời cả 3.14.0 và 3.15.0 chỉ vì cả hai xuất hiện trong graph dưới dạng requested dependency.

### 5.1. Nghiệp vụ cần cân nhắc

- Constraint làm việc ở **configuration được resolve**, ví dụ `compileClasspath`, `runtimeClasspath`.
- Một platform được import ở sai configuration có thể không tác động graph bạn đang xem.
- Một transitive dependency yêu cầu version cao hơn vẫn có thể làm resolved version cao hơn platform constraint.
- Nếu `strictly` hoặc enforced rules tồn tại, version selection có thể bị thu hẹp hoặc fail.
- Thay đổi constraint ảnh hưởng **selected versions**, không sửa code của các thư viện đã publish.
- Version được chọn hợp lệ về quy tắc Gradle vẫn có thể không tương thích với API/runtime kỳ vọng; phải test.

### 5.2. `require` không đồng nghĩa exact pin

Trong Gradle rich versions, `require("3.14.0")` (và bare version declaration mặc định) nhìn chung cho phép một yêu cầu version cao hơn trong graph nâng selected version. Muốn chặn nâng ngoài một khoảng, cân nhắc `strictly("...")`, nhưng chỉ khi có căn cứ về compatibility.

Đây là khác biệt quan trọng giữa **“đề xuất/đòi tối thiểu một version”** và **“giới hạn tập version được chấp nhận”**.

## 6. `api` và `runtime` constraints: chọn đúng scope

Với Java Platform plugin:

~~~kotlin
dependencies {
    constraints {
        api("com.google.code.gson:gson:2.10.1")
        runtime("org.slf4j:slf4j-simple:2.0.9")
    }
}
~~~

Đọc như sau:

- `api`: những constraints mà consumer cần khi biên dịch chống lại các module theo chính sách platform. Chúng còn ảnh hưởng runtime vì `runtime` kế thừa `api`.
- `runtime`: constraints chỉ cần ở runtime của consumer, ví dụ JDBC driver hoặc logging provider không trực tiếp được code compile sử dụng.

Ví dụ platform kiểm soát `org.postgresql:postgresql` ở runtime:

~~~kotlin
dependencies {
    constraints {
        runtime("org.postgresql:postgresql:42.7.3")
    }
}
~~~

Nếu application chỉ dùng JDBC API lúc compile và load PostgreSQL driver ở runtime, consumer có thể khai báo:

~~~kotlin
dependencies {
    implementation(platform(project(":platform")))
    runtimeOnly("org.postgresql:postgresql")
}
~~~

Đây là **mẫu minh họa bổ sung** chứ không nằm trong bài thực hành chạy độc lập ở mục 4; phải cấu hình project/plugin và dependency sử dụng JDBC phù hợp. Nếu driver được yêu cầu trực tiếp trong code compile, cách khai báo scope cần được xem lại.

### 6.1. Không cần ép mọi dependency vào `api`

Một số library chỉ được dùng ở runtime. Đặt tất cả constraints ở `api` có thể làm chính sách phiên bản lan sang compile graph không cần thiết. `runtime` cho phép scope chính xác hơn.

Ngược lại, một API library dùng type `SomeLibraryClass` trong public interface của nó cần dependency được công bố ở `api` của **library project**, không phải chỉ `implementation`. Đây là một khía cạnh khác: phân biệt API exposure của `java-library` consumer với API constraints của `java-platform`.

### 6.2. Cấu hình platform không phải compile classpath

Đừng cố chạy `:platform:compileJava` hoặc tạo `sourceSets` trong platform project. `java-platform` **không có Java source**. Muốn kiểm tra constraints, resolve classpath của consumer hoặc xem published metadata, không chờ output classes của platform.

## 7. Rich version constraints: strictly, require, prefer, reject và because

Khi một bare version không diễn tả đúng yêu cầu, bạn có thể khai báo richer constraints trong `:platform`.

Ví dụ **thay thế/điều chỉnh** constraint cho Commons Lang trong `platform/build.gradle.kts`:

~~~kotlin
dependencies {
    constraints {
        api("org.apache.commons:commons-lang3") {
            version {
                strictly("[3.14,4.0[")
                prefer("3.14.0")
                reject("3.15.0")
            }
            because(
                "Ví dụ chính sách chỉ chấp nhận nhánh 3.x " +
                "và cần loại một candidate đã được xác minh"
            )
        }
    }
}
~~~

**Lưu ý quan trọng:** số version trong `reject("3.15.0")` ở đây **chỉ minh họa cú pháp**, không phải khẳng định phiên bản đó bị lỗi bảo mật hoặc ABI ngoài đời. Trong dự án thực, chỉ reject version có căn cứ và ticket/changelog.

| Thành phần | Ý nghĩa |
| --- | --- |
| `require("3.14.0")` | Yêu cầu version thích hợp; vẫn có thể nâng theo conflict resolution |
| `strictly("[3.14,4.0[")` | Chỉ chấp nhận version trong khoảng này theo cơ chế strict |
| `prefer("3.14.0")` | Nêu version ưu tiên khi các yêu cầu khác không ép chọn khác |
| `reject("3.15.0")` | Loại candidate cụ thể khỏi tập cho phép |
| `because("...")` | Mô tả lý do policy, giúp maintain và chẩn đoán |

Cú pháp khoảng Maven/Gradle `[3.14,4.0[` biểu thị **bao gồm cận dưới, loại trừ cận trên**. Đây là cách giới hạn nhánh major một cách có ý nghĩa, nhưng vẫn cần test các version cụ thể bên trong khoảng.

### 7.1. `strictly` là ràng buộc mạnh, không phải “mặc định nên dùng”

Nếu A yêu cầu `strictly("3.14.0")` và B cần API chỉ có trong 3.16.0, Gradle có thể báo conflict hoặc chọn theo những quy tắc ưu tiên strict ở các mức graph khác nhau. Đừng xem `strictly` là cách sửa mọi warning bằng cách pin một version bất kỳ.

Tài liệu Gradle hiện hành nêu **các strict declarations ở cùng mức có thể lấy giao các khoảng**, còn strict declarations ở độ sâu khác nhau có **quy tắc ưu tiên**. Cần dùng `dependencyInsight` và documentation đúng phiên bản thay vì tự giả định mọi strict chỉ cộng dồn hoặc mọi strict đều tuyệt đối thắng các resolution strategy.

Đặc biệt, `resolutionStrategy.force(...)` hoặc custom resolution rules ở consuming project có thể override constraints. Những cơ chế đó là **ngoại lệ mạnh**, nên tránh nếu platform/rich versions đã mô tả được policy.

### 7.2. Strict version của platform được endorse

Một điểm dễ bị bỏ sót: **`platform(...)` thông thường vẫn endorse các `strictly` constraints do platform công bố**. Nghĩa là “regular platform cho phép upgrade” đúng với constraints thông thường, **không đúng nếu chính platform có strict version không cho upgrade**.

Gradle còn có API `doNotEndorseStrictVersions()` trên platform dependency để thay đổi hành vi này trong trường hợp đặc biệt. Chỉ áp dụng khi hiểu rõ tác động và đã kiểm tra graph, không bật để né một lỗi incompatibility chưa rõ nguyên nhân.

## 8. Platform vs enforcedPlatform

Gradle có hai cách tiêu thụ platform:

~~~kotlin
dependencies {
    implementation(platform(project(":platform")))
}
~~~

và:

~~~kotlin
dependencies {
    implementation(enforcedPlatform(project(":platform")))
}
~~~

Khác nhau:

| Cách | Mục đích | Cần cân nhắc |
| --- | --- | --- |
| `platform(...)` | Áp constraints/recommendations và strict rules đã được platform công bố | Regular constraints vẫn có thể bị upgrade bởi graph |
| `enforcedPlatform(...)` | **Enforce các versions của platform** mạnh hơn | Có thể ép consumer dùng version không đáp ứng API của dependency khác |
| `strictly` tại từng constraint | Giới hạn chỉ module cụ thể hoặc một khoảng | Đọc graph/rules để hiểu conflict và consumer behavior |

`enforcedPlatform` có thể làm downgrade một dependency được module khác yêu cầu, khiến runtime lỗi. Nó cũng có thể **truyền ngữ nghĩa enforced sang consumer** khi bạn publish một library phụ thuộc vào enforced platform.

Thông thường:

- Với **application cuối** đã kiểm thử trọn bộ, enforcedPlatform có thể được cân nhắc khi thực sự cần pin policy.
- Với **thư viện được nhiều consumer sử dụng**, ưu tiên regular platform/constraints, tránh ép toàn bộ dependency graph của consumer.
- Nếu một module cần strict bound, có thể khai báo strict riêng với lý do rõ thay vì enforce cả BOM.

**Enforcement không chứng minh tương thích nhị phân.** Một JAR cũ bị ép dùng có thể thiếu method mà thư viện khác cần; nên kiểm tra runtime/integration tests.

## 9. Nhập Maven BOM vào Java Platform nội bộ

Một tổ chức không nhất thiết tự khai báo lại mọi version của vendor. Nếu có một BOM chính thức, có thể **import** rồi bổ sung constraints riêng.

Ví dụ Java Platform muốn quản lý Jackson bằng BOM:

~~~kotlin
plugins {
    `java-platform`
}

repositories {
    mavenCentral()
}

javaPlatform {
    // Bắt buộc nếu java-platform thêm dependency vào platform khác.
    allowDependencies()
}

dependencies {
    api(
        platform("com.fasterxml.jackson:jackson-bom:2.17.2")
    )

    constraints {
        api("org.apache.commons:commons-lang3:3.14.0")
    }
}
~~~

Đây là **mẫu platform/build.gradle.kts thay thế** cho file ở ví dụ đầu; không áp dụng cả hai bản không suy xét. Các điểm cần nhớ:

1. `api(platform("..."))` là **platform dependency**; nó import các constraints từ Jackson BOM.
2. `javaPlatform { allowDependencies() }` cần vì Java Platform mặc định từ chối **dependencies thông thường**, kể cả một platform dependency.
3. `constraints { api(...) }` bổ sung policy riêng.
4. `repositories { mavenCentral() }` cần nếu phải resolve BOM từ Maven Central; tổ chức có thể dùng mirror nội bộ thay thế.
5. Consumer tiếp tục dùng `implementation(platform(project(":platform")))` và khai báo các module Jackson không có version riêng nếu BOM quản lý chúng.

Ví dụ consumer:

~~~kotlin
dependencies {
    implementation(platform(project(":platform")))
    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("org.apache.commons:commons-lang3")
}
~~~

Đây là **mảnh dependencies** cần Java plugin và repositories ở consumer. Đừng dùng một file Maven POM làm JAR thông thường khi mục đích là lấy constraints — `platform(...)` mới biểu đạt đúng variant.

### 9.1. Gradle Native Platform và Maven BOM

Maven BOM truyền phiên bản chủ yếu qua `dependencyManagement`. Gradle Platform có thêm sự phân biệt API/runtime variants và rich constraints. Khi chuyển qua Maven POM, **một số chi tiết metadata Gradle không có biểu diễn đầy đủ**.

Do đó nếu đội ngũ có cả consumer Maven và Gradle, phải kiểm tra kết quả publish và version policy mà mỗi công cụ nhìn thấy. Không giả định Maven POM sẽ giữ nguyên mọi `strictly`, `reject`, scope của Gradle.

## 10. Platform constraints giữa các subprojects nội bộ

Một Java Platform không chỉ quản lý dependency từ Maven Central. Nó còn có thể khai báo constraints cho các **project modules** thuộc cùng build, ví dụ:

~~~text
:platform
:core
:api
:app
~~~

Trong `platform/build.gradle.kts`:

~~~kotlin
plugins {
    `java-platform`
}

dependencies {
    constraints {
        api(project(":core"))
        api(project(":api"))
    }
}
~~~

Đây là **mẫu platform khác**, không thể dùng nếu `:core`/`:api` chưa được khai báo trong `settings.gradle.kts`. Khi publish, Gradle có thể chuyển project constraints sang tọa độ `group:name:version` trong metadata Maven/Gradle theo quy tắc publish.

**Không nhầm project constraints với project dependencies:** khai báo constraint không làm `:core` được thêm vào app. App vẫn cần:

~~~kotlin
dependencies {
    implementation(platform(project(":platform")))
    implementation(project(":core"))
}
~~~

Đoạn này dành cho app project có Java plugin. `:core` sẽ được sử dụng vì **dependency trực tiếp**, còn platform policy tác động lên version/các ràng buộc được công bố khi cần.

### 10.1. Một số ràng buộc

- Nếu các project nội bộ không cùng release train, không ép version chung chỉ vì cùng organization.
- Project module cần có `group`, `version` và publication metadata hợp lý khi xuất bản.
- Không tạo vòng phụ thuộc `:platform -> :core -> :platform` theo kiểu dependency thực khiến graph không thể giải quyết.
- Trong multi-project build, xem cơ chế project dependency và variant-aware resolution thay vì hard-code JAR path từ một module khác.

## 11. Xuất bản Java Platform thành Maven BOM

Nếu nhiều repository khác nhau cần dùng chung chính sách version, có thể **publish platform project**.

Ví dụ `platform/build.gradle.kts`:

~~~kotlin
import org.gradle.api.publish.maven.MavenPublication

plugins {
    `java-platform`
    `maven-publish`
}

group = "org.example.build"
version = "1.0.0"

dependencies {
    constraints {
        api("org.apache.commons:commons-lang3:3.14.0")
        api("com.google.code.gson:gson:2.10.1")
        runtime("org.slf4j:slf4j-simple:2.0.9")
    }
}

publishing {
    publications {
        create<MavenPublication>("javaPlatformBom") {
            from(components["javaPlatform"])
        }
    }
}
~~~

Đây là **file thay thế** cho `platform/build.gradle.kts` của bài thực hành: mục tiêu là minh họa publication, không yêu cầu tự động ghi đè file gốc. Plugin `maven-publish` tạo các publish tasks.

Để thử cục bộ, dùng Gradle Wrapper:

~~~bash
./gradlew :platform:publishToMavenLocal --console=plain
~~~

Lệnh này xuất bản vào **Maven local repository** (thường dưới `~/.m2/repository`), không upload ra server từ xa. Nếu project thật cần publish lên remote, phải cấu hình `publishing.repositories` và xác thực phù hợp, có approval theo quy trình.

Khi publish đúng:

- **Gradle Module Metadata (`.module`)** có thể giữ những thông tin đầy đủ hơn như variants/rich constraints.
- **Maven POM** của Java Platform là dạng BOM, chứa `<dependencyManagement>` biểu diễn các constraints theo khả năng Maven hỗ trợ.
- Khác biệt về scope/variant/rich constraint có thể làm consumer Maven nhìn một policy **không hoàn toàn giống** consumer Gradle.
- Publication component phải là `components["javaPlatform"]`, **không** phải `components["java"]`. Platform không có Java JAR component.

### 11.1. Tạo phiên bản platform có ý nghĩa

`group`, `version` và artifact name (thường theo tên project `platform`) tạo ra tọa độ publication, ví dụ `org.example.build:platform:1.0.0`.

Phiên bản platform nên đại diện cho **policy được kiểm thử** của bộ dependencies, không mặc định trùng version của mọi library. Một lần đổi nhiều constraints có thể là một lần phát hành platform mới.

### 11.2. Consumer ngoài multi-project build

Khi platform đã xuất bản ra repository phù hợp và quyền truy cập đã được cấp:

~~~kotlin
dependencies {
    implementation(
        platform("org.example.build:platform:1.0.0")
    )
    implementation("org.apache.commons:commons-lang3")
}
~~~

Đây là **mảnh consumer**. Phải có repository phù hợp trong `repositories` hoặc `dependencyResolutionManagement` để Gradle tìm được platform và thư viện. Không phải chỉ publish local là tự động khả dụng trên server của tổ chức.

### 11.3. Groovy DSL publishing tương đương

~~~groovy
plugins {
    id 'java-platform'
    id 'maven-publish'
}

group = 'org.example.build'
version = '1.0.0'

dependencies {
    constraints {
        api 'org.apache.commons:commons-lang3:3.14.0'
    }
}

publishing {
    publications {
        javaPlatformBom(MavenPublication) {
            from components.javaPlatform
        }
    }
}
~~~

Trong project Groovy thực, cần Gradle API `MavenPublication` khả dụng trong DSL. Đây là **mẫu Gradle Groovy DSL** tương ứng về nguyên tắc; bản Kotlin DSL trước đó là ví dụ chính.

## 12. Version catalog không thay thế Java Platform

Hai công cụ đều giúp tập trung version, nhưng **hoạt động ở những tầng khác nhau**.

| Thuộc tính | Version catalog | Java Platform |
| --- | --- | --- |
| Nguồn cấu hình | Thường là `gradle/libs.versions.toml` | Một Gradle project dùng `java-platform` hoặc platform module đã publish |
| Cách tiêu thụ | `implementation(libs.gson)` | `implementation(platform(project(":platform")))` |
| Vai trò | Alias để khai báo dependency/version tại source | Constraints ảnh hưởng **resolution graph**, gồm transitive modules |
| Có tự thêm JAR? | Chỉ khi alias được dùng trong dependency declaration | Không; platform policy không đưa mọi JAR vào graph |
| Xuất bản policy qua Maven BOM | Không tự động | Có qua `maven-publish` |
| Quản lý API/runtime constraints | Không phải cơ chế mặc định | Có `api` và `runtime` của Java Platform |
| Rich versions | Có thể khai báo version và constraints qua aliases | Native dependency constraints có thể dùng `strictly`/`prefer`/`reject` |

Một version catalog giúp mọi project viết `libs.gson`, nhưng **không bảo đảm** transitive dependency từ nơi khác không đưa Gson version khác. Java Platform thêm constraints vào graph để quản lý tình huống đó.

### 12.1. Kết hợp catalog và platform

File `gradle/libs.versions.toml`:

~~~toml
[versions]
gson = "2.10.1"
commons-lang = "3.14.0"

[libraries]
gson = { module = "com.google.code.gson:gson", version.ref = "gson" }
commons-lang = { module = "org.apache.commons:commons-lang3", version.ref = "commons-lang" }
~~~

Trong `platform/build.gradle.kts`, có thể dùng alias khi version catalog được cấu hình và Gradle sinh `libs` accessors:

~~~kotlin
plugins {
    `java-platform`
}

dependencies {
    constraints {
        api(libs.gson)
        api(libs.commons.lang)
    }
}
~~~

Trong consumer, vẫn cần **import platform**:

~~~kotlin
dependencies {
    implementation(platform(project(":platform")))
    implementation("com.google.code.gson:gson")
}
~~~

Đây là **mẫu tích hợp bổ sung**, khác với file thực hành chính; không cần đồng thời duy trì hai nguồn version mâu thuẫn. Nếu catalog và platform cùng định nghĩa một module với version khác nhau, cần làm rõ source-of-truth và kiểm tra graph.

### 12.2. Alias không tự “pin” classpath

`implementation(libs.gson)` tạo một dependency version từ catalog. Constraint từ platform có thể nâng version thực tế khi có requirements khác, và ngược lại một alias không tự tạo transitive policy cho các module mà consumer không khai báo.

Sử dụng `dependencyInsight` để quan sát **selected version**, không kết luận từ alias string.

## 13. Phân biệt direct dependency constraint và Java Platform

Đối với một project đơn lẻ, Gradle cho phép khai báo constraint ngay trong project:

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.google.code.gson:gson")

    constraints {
        implementation("com.google.code.gson:gson:2.10.1") {
            because("Ứng dụng đã được kiểm thử với Gson này")
        }
    }
}
~~~

Đây là **file minh họa độc lập** về syntax; không tạo `java-platform` project. Constraint có tác dụng trong phạm vi configuration phù hợp.

### Khi nào dùng cách nào?

- **Một app nhỏ, ít dependencies:** constraint trực tiếp có thể đơn giản hơn tạo subproject platform.
- **Nhiều subproject cùng dùng bộ version:** Java Platform tập trung, dễ chia sẻ.
- **Có BOM vendor đáng tin:** import BOM bằng `platform(...)`, không nhất thiết cần platform tự tạo.
- **Muốn policy chung thêm vào BOM vendor:** Java Platform với `allowDependencies()` và import BOM.
- **Chỉ muốn alias có gợi ý trong IDE:** Version catalog.

Không tạo platform chỉ để quản lý một dependency trong một app đơn giản nếu việc đó làm cấu trúc phức tạp không cần thiết.

## 14. Xem dependency graph và hiểu ký hiệu

Với bài thực hành đa module, chạy:

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --console=plain
~~~

Một đoạn output Gradle có thể dùng các ký hiệu:

~~~text
+--- project :platform
|    +--- org.apache.commons:commons-lang3:3.14.0 (c)
|    +--- com.google.code.gson:gson:2.10.1 (c)
|    \--- org.slf4j:slf4j-simple:2.0.9 (c)
+--- org.apache.commons:commons-lang3 -> 3.14.0
+--- com.google.code.gson:gson -> 2.10.1
\--- org.slf4j:slf4j-simple -> 2.0.9
~~~

**Đây chỉ là output minh họa cấu trúc**, không cam kết vị trí, toàn bộ dependencies hoặc indent chính xác; các dependency bắc cầu của SLF4J và các node rút gọn có thể được hiển thị thêm.

Ký hiệu thường gặp:

- `versionA -> versionB`: Gradle chọn `versionB` thay cho version được request.
- `(c)`: một **constraint**, không phải dependency artifact độc lập.
- `(*)`: subtree đã được in ở nơi khác, nên không lặp.
- `FAILED`: một dependency/variant không resolve được.
- Các selection reasons có thể bao gồm `By constraint`, `By conflict resolution`, `Forced`, `Selected by rule`.

Khi version hiển thị khác platform constraint, đừng đoán: dùng `dependencyInsight` tìm nguồn ảnh hưởng.

## 15. `dependencyInsight`: vì sao Gradle chọn version này?

Từ project root:

~~~bash
./gradlew :app:dependencyInsight \
  --dependency com.google.code.gson:gson \
  --configuration runtimeClasspath \
  --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:dependencyInsight --dependency com.google.code.gson:gson --configuration runtimeClasspath --console=plain
~~~

`dependencyInsight` cho biết:

1. **Selected version** của module.
2. Những **requested versions** từ dependencies khác nhau.
3. **Selection reason** như “By constraint” hoặc “By conflict resolution”.
4. Đường đi dependency transitive dẫn đến module đó.
5. Một số attributes/variants của selected component.

Nếu đã có một direct dependency request version khác, bạn có thể thấy:

~~~text
com.google.code.gson:gson:2.9.0 -> 2.10.1
~~~

Điều đó diễn tả một yêu cầu cũ được nâng lên `2.10.1` trong graph, **không phải hai JAR Gson đều được tải cho cùng module**.

### 15.1. Những câu hỏi trước khi sửa conflict

- Module nào thực sự **đòi** version mới/cũ?
- Platform có đang áp vào **đúng configuration** không?
- Constraint nào là `strictly`/`reject`, constraint nào chỉ `require`?
- Có `force(...)`/resolution rules ghi đè policy không?
- Metadata của artifact có thiếu version/capability/variant không?
- Thư viện có tương thích nhị phân khi đổi version không?
- Đã chạy tests trên runtimeClasspath thật chưa?

Giải thích graph trước, đổi version sau.

### 15.2. Compile và runtime khác nhau

Một task Java có thể compile với phiên bản thư viện X nhưng runtime graph lấy Y do runtimeOnly dependency hoặc constraint khác. Khi gặp `NoSuchMethodError` hay `NoClassDefFoundError`, kiểm tra cả:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Platform không phải công cụ chứng minh binary compatibility. Nó quản lý **version policy**, còn correctness phụ thuộc tests, ABI và classpath khi chạy.

## 16. Không tương thích và conflict: những lỗi dễ gặp

### 16.1. `NoSuchMethodError` dù build compile thành công

Một thư viện đã compile với API mới có thể gọi một method không tồn tại trong JAR cũ được nạp ở runtime. Nếu platform/enforcedPlatform ép version quá thấp, build có thể vẫn tạo artifact nhưng runtime lỗi.

Cách xử lý:

1. Xác định JAR/class chứa method trong stack trace.
2. Xem `runtimeClasspath`, version được chọn và dependencyInsight.
3. Đối chiếu BOM release notes/vendor compatibility matrix.
4. Nâng platform/BOM và những module liên quan khi cần.
5. Chạy integration/smoke tests; đừng chỉ sửa version trong một chỗ.

### 16.2. `NoClassDefFoundError`

Có thể là dependency thiếu ở runtime, exclusion không phù hợp, variant sai hoặc classloader khác. Constraint trên module **không tự thêm module đó**; nếu dependency runtime chưa được khai báo, thêm constraint không giải quyết việc thiếu class.

### 16.3. Hai provider logging cùng classpath

Hai module khác nhau cùng cung cấp một capability hoặc class có thể gây xung đột, dù version của SLF4J API đã được platform thống nhất. Không có BOM nào bảo đảm project chỉ đưa một logging provider vào runtime nếu metadata không nói rõ. Cần xem graph, capabilities hoặc loại bỏ provider không mong muốn.

### 16.4. Gradle chọn version cao hơn constraint

Đó có thể là hành vi bình thường của regular constraints khi dependency khác yêu cầu version cao hơn. Dùng `dependencyInsight` trước khi gán `strictly` hoặc `enforcedPlatform`. Những cơ chế mạnh có thể giải quyết một version drift cụ thể nhưng tạo incompatibility ở chỗ khác.

### 16.5. `Unresolved reference: api` trong platform script

Kiểm tra:

- Đã apply `plugins { \`java-platform\` }` chưa?
- Code nằm trong đúng `dependencies { constraints { api(...) } }` chưa?
- Có vô tình apply Java plugin thay vì Java Platform plugin không?
- Kotlin DSL script/IDE đã được sync sau thay plugin chưa?

Ở Java Platform, `api` và `runtime` được plugin cung cấp; không dùng một task class Kotlin hay build logic khác scope rồi giả định generated accessors đã tồn tại.

## 17. Nâng cấp một platform có kiểm soát

Một workflow thay đổi version nên đi theo quy trình:

1. Xác nhận vulnerability/feature/compatibility requirement bằng tài liệu vendor.
2. Sửa platform constraints hoặc version của BOM import.
3. Chạy `:app:dependencyInsight` cho các module bị ảnh hưởng.
4. So sánh **compileClasspath và runtimeClasspath** trước/sau.
5. Chạy unit/integration/smoke tests.
6. Nếu dùng dependency locking, cập nhật và review `gradle.lockfile`.
7. Nếu platform được publish, nâng platform version và phát hành metadata/POM đúng quy trình.
8. Với consumer Maven, kiểm tra BOM POM và các version được quản lý; với Gradle kiểm tra `.module`.
9. Không tự “force” một version để CI xanh khi chưa xác minh các thư viện khác yêu cầu API nào.
10. Ghi lại lý do dùng `because(...)` hoặc changelog của platform.

### 17.1. Dependency locking và platform giải quyết hai bài toán khác nhau

- Java Platform: **định nghĩa yêu cầu/khuyến nghị phiên bản**.
- Dependency locking: **ghi những resolved versions cuối cùng** của các configurations được lock.
- Version catalog: alias dễ quản lý trong code.
- Dependency verification: kiểm tra integrity của artifact theo hash/signature.
- Tests: xác minh tổ hợp module thực sự hoạt động.

Có thể dùng chung. Ví dụ khi nâng platform constraint làm graph chọn version mới, `gradle.lockfile` cần được cập nhật theo quy trình, không nên giữ khóa cũ mà hiểu nhầm platform không có hiệu lực.

Mẫu bật locking trong **consumer project**:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó tạo/cập nhật locks đối với những configuration đã resolve:

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --write-locks
~~~

Đây là workflow riêng cần review và commit lockfile theo policy. Không bắt buộc cho mọi project demo, cũng không thay thế BOM/platform.

## 18. Một số lỗi thiết kế cần tránh

| Lỗi | Vì sao sai hoặc nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Dùng `java-platform` cùng `java`/`java-library` trong một project | Plugin không tương thích, platform không sản xuất JAR | Tách `:platform` và `:app`/`:lib` |
| Viết `dependencies { api("g:m:1.0") }` mà quên `constraints` | Platform từ chối dependency thường mặc định | Đặt trong `constraints { api(...) }` |
| Bật `allowDependencies()` chỉ để thêm mọi JAR vào platform | Nhầm mục tiêu platform và library | Giữ constraints, opt-in chỉ khi cần import platform/BOM khác |
| Cho rằng constraint tự tải thư viện | Constraint không thêm module | Consumer phải khai báo dependency trực tiếp/bắc cầu |
| Chỉ thêm `api` constraint rồi giả định module luôn có | Cần dependency thật | Kiểm tra consumer `dependencies` |
| Dùng `implementation` trong platform script | Java Platform dùng `api`/`runtime` cho constraints | Dùng `constraints { api(...) }` |
| Bỏ `platform(...)` ở consumer | Không chọn đúng platform variant | Import platform rõ ràng |
| Nhầm catalog với platform | Catalog không điều khiển graph transitive tự động | Dùng platform để công bố constraints |
| Dùng version cứng ở mọi consumer bên cạnh platform | Duplicate source-of-truth, dễ drift | Cho module được quản lý không ghi version riêng nếu phù hợp |
| Nghĩ regular platform pin cứng tất cả | Bare constraints vẫn có thể upgrade | Xem graph, dùng strict/enforced khi có căn cứ |
| Bật enforcedPlatform cho library publish chung | Có thể ép graph của consumer | Ưu tiên regular platform và kiểm tra policy |
| Khai báo `strictly` không có rationale | Dễ gây resolution failure khi nâng cấp | Dùng range/because và tests |
| Cho rằng `runtime` constraint áp lên compile | Phạm vi runtime riêng | Khai báo `api` nếu compile cần |
| Đọc sai `(c)` trong dependency tree | Constraint không phải artifact JAR | Dùng dependencyInsight |
| Chỉ chạy `:platform:build` để kiểm tra Java code | Platform không biên dịch source | Chạy consumer tests và dependency reports |
| Publish bằng `components["java"]` | Platform có component riêng `javaPlatform` | Dùng `components["javaPlatform"]` |
| Nghĩ Maven POM giữ đủ rich versions | Maven format giới hạn hơn Gradle Module Metadata | Kiểm tra consumer Maven/Gradle riêng |
| Đổi constraint nhưng không đổi lockfile | Lock state có thể cũ | Regenerate/review lockfile |
| Kiểm tra mỗi compileClasspath khi runtime lỗi | Classpath có thể khác | Xem runtimeClasspath và packaging |
| Dùng `force` để che incompatibility | Có thể hạ dependency dưới API required | Tìm nguyên nhân và nâng BOM/platform |
| Lặp lại BOM vendor bằng tay | Tăng công sức bảo trì và lệch releases | Import vendor BOM với allowDependencies nếu cần |

## 19. Bài tập tự kiểm tra

**Câu 1.** Một Java Platform có constraint `api("org.apache.commons:commons-lang3:3.14.0")`, nhưng consumer không khai báo Commons Lang và không thư viện nào kéo nó vào. JAR có trong classpath không?

**Đáp án:** Không. Constraint chỉ tham gia version selection **nếu module xuất hiện trong graph**.

**Câu 2.** Project platform đã apply `java-platform`. Có thể apply thêm `java-library` để tạo một JAR từ platform luôn không?

**Đáp án:** Không. Một project platform không sản xuất binary. Tách subproject platform và library.

**Câu 3.** Cú pháp nào chuẩn khi project `:app` muốn dùng policy của `:platform`?

**Đáp án:**

~~~kotlin
dependencies {
    implementation(platform(project(":platform")))
}
~~~

Sau đó khai báo các module app cần; không phải tất cả module có trong constraints tự được thêm.

**Câu 4.** Muốn có ràng buộc version của một logging provider chỉ ở runtime, nên viết gì trong Java Platform?

**Đáp án:**

~~~kotlin
dependencies {
    constraints {
        runtime("org.slf4j:slf4j-simple:2.0.9")
    }
}
~~~

Consumer vẫn cần `runtimeOnly("org.slf4j:slf4j-simple")` nếu muốn thực sự dùng provider ấy.

**Câu 5.** Vì sao không thể đưa BOM của vendor bằng `api(platform("..."))` vào platform project mặc định?

**Đáp án:** Java Platform mặc định từ chối **dependencies** thường, kể cả platform dependency. Bật `javaPlatform { allowDependencies() }` có chủ đích.

**Câu 6.** `platform(...)` có luôn bỏ qua các `strictly` constraints của platform không?

**Đáp án:** Không. Gradle regular platform **endorse strict versions** được platform công bố theo mặc định. Chỉ bare constraints thường mới có thể bị upgrade một cách linh hoạt.

**Câu 7.** Muốn xuất bản Java Platform thành Maven BOM, dùng component nào?

**Đáp án:** `from(components["javaPlatform"])` trong `MavenPublication` với `maven-publish`.

**Câu 8.** `libs.gson` trong version catalog có thay cho `implementation(platform(project(":platform")))` không?

**Đáp án:** Không. Catalog giúp khai báo alias cho direct dependencies; platform cung cấp constraints ảnh hưởng graph.

**Câu 9.** Vì sao Gradle chọn version 2.0 dù platform ghi 1.8?

**Đáp án:** Một regular constraint có thể cho phép graph chọn phiên bản cao hơn theo yêu cầu khác. Dùng `dependencyInsight` xem source request/rules, không tự đoán.

**Câu 10.** Khi nào nên dùng `enforcedPlatform`?

**Đáp án:** Khi application cuối có lý do enforce và đã test toàn bộ stack; tránh dùng mặc định cho library có consumers riêng.

**Câu 11.** `because(...)` có làm thay đổi version selection không?

**Đáp án:** Không trực tiếp. Nó ghi lý do của ràng buộc để maintainer và dependency reports dễ giải thích policy.

**Câu 12.** Nếu artifact thật trong Maven repository bị thay byte mà version không đổi, platform có tự phát hiện không?

**Đáp án:** Không. Platform quản lý versions; cần integrity checks/dependency verification và repository security.

## 20. Checklist hoàn thiện trước khi áp dụng vào dự án thật

1. Chọn module nào nên được quản lý **tập trung** và module nào do vendor BOM quản lý.
2. Tạo `:platform` với `java-platform`, không apply thêm Java/JAR plugin.
3. Đặt bare constraints ở `api` hoặc `runtime` theo phạm vi thực tế.
4. Dùng `strictly`/`reject` chỉ khi có bằng chứng, ghi `because(...)`.
5. Consumer import `platform(project(":platform"))` trong configuration phù hợp và chỉ thêm module thật sự dùng.
6. Nếu có BOM bên ngoài, import bằng `javaPlatform.allowDependencies()` rồi `api(platform(...))`.
7. Xem `compileClasspath`/`runtimeClasspath` và dùng `dependencyInsight` để xác định selected versions.
8. Chạy test và smoke test khi nâng version, đặc biệt với modules cùng release train.
9. Nếu muốn chia sẻ cho nhiều repository, publish `javaPlatform` component cùng metadata/POM và test compatibility.
10. Phân biệt platform với version catalog và lockfile; không dùng một công cụ để thay toàn bộ công cụ khác.
11. Kiểm soát repo URL/TLS/credentials nếu platform hoặc BOM nằm ở kho riêng.
12. Đối chiếu **phiên bản Gradle Wrapper** trước khi dùng API đặc biệt; không mặc định tài liệu `current` khớp một build cũ.

**Quy tắc nhớ nhanh:**

~~~text
PLATFORM PROJECT
    plugins { `java-platform` }
    dependencies { constraints { api("g:m:v"); runtime("g:n:v") } }

CONSUMER
    implementation(platform(project(":platform")))
    implementation("g:m")

IMPORT VENDOR BOM
    javaPlatform { allowDependencies() }
    api(platform("g:bom:v"))

PUBLISH
    from(components["javaPlatform"])

VERIFY
    :app:dependencies
    :app:dependencyInsight
    + unit/integration/smoke tests
~~~

## 21. Tài liệu chính thức

1. Gradle — The Java Platform Plugin: https://docs.gradle.org/current/userguide/java_platform_plugin.html
2. Gradle — Platforms: https://docs.gradle.org/current/userguide/platforms.html
3. Gradle — Declaring Dependency Constraints: https://docs.gradle.org/current/userguide/dependency_constraints.html
4. Gradle — Declaring Rich Versions: https://docs.gradle.org/current/userguide/dependency_versions.html
5. Gradle — Centralizing Dependencies: https://docs.gradle.org/current/userguide/centralizing_dependencies.html
6. Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
7. Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
8. Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
9. Gradle — Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
10. Gradle — Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html

Các đường dẫn `current` cập nhật theo phiên bản Gradle hiện hành. Khi áp dụng trong repository thật, hãy dùng tài liệu tương ứng với **Gradle Wrapper đang chạy**, kiểm tra repository thực tế, Gradle Module Metadata và Maven BOM được publish, cũng như compatibility matrix của thư viện liên quan.