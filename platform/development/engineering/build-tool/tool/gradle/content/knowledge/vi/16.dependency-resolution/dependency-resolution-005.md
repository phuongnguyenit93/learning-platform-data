# Dependency substitution và component selection rules trong Gradle

## 1. Hai quyết định khác nhau khi Gradle phân giải dependency

Một project Gradle có thể khai báo dependency trực tiếp, ví dụ `implementation 'org.example:lib:1.0'`. Nhưng khi Gradle thực sự lập compile classpath hoặc runtime classpath, nó phải xử lý cả các phụ thuộc bắc cầu, phiên bản, repository, metadata, constraint và variant. Thành phần được sử dụng cuối cùng có thể khác với yêu cầu ban đầu.

Hai cơ chế quan trọng trong `ResolutionStrategy` là:

- **Dependency substitution:** thay **yêu cầu về một component** bằng một component khác. Ví dụ thay module Maven `org.demo:message-lib` bằng project `:message-lib` đang phát triển cục bộ.
- **Component selection rules:** kiểm tra **những phiên bản ứng viên** của một module và từ chối các ứng viên không đáp ứng điều kiện. Ví dụ khi yêu cầu dải `1.+`, bỏ qua bản `1.5` đã được xác nhận lỗi và chọn bản được chấp nhận khác nếu có.

Điểm khác nhau nằm ở **đối tượng bị điều chỉnh**:

```text
dependency declaration (selector)
             |
             v
dependency substitution
  "yêu cầu thành phần nào thay cho thành phần nào?"
             |
             v
repository + metadata + các yêu cầu trong graph
             |
             v
component selection rules
  "ứng viên version này có được chấp nhận không?"
             |
             v
version/variant resolution
             |
             v
component đã resolve -> classpath -> task Java/Gradle
```

Sơ đồ mô tả cách tư duy, không cam kết thứ tự mọi bước nội bộ của Gradle. Conflict resolution, dependency constraints, capabilities và cache còn có thể tác động đến kết quả. Cả substitution và selection rules đều là những **quy tắc can thiệp trực tiếp vào bộ giải dependency**; chỉ sử dụng khi declaration/constraint/platform thông thường không biểu đạt được nhu cầu.

**Mục tiêu học:** phân biệt hai cơ chế, viết được Groovy DSL và Kotlin DSL, thử một ứng dụng Java 17 hai module, đọc dependency graph trước/sau khi đặt rule, hiểu giới hạn với version cố định và dynamic version, tránh đưa rule debug vào CI/production mà không kiểm soát.

## 2. Thuật ngữ cần biết

| Thuật ngữ | Giải thích | Ví dụ |
| --- | --- | --- |
| Requested dependency | Thành phần được yêu cầu trước khi resolution hoàn tất | `org.demo:message-lib:1.0.0` |
| Selected component | Module hoặc project thực sự được chọn sau resolution | `project :message-lib` |
| Module selector | Yêu cầu external module bằng group, name, version | `org.apache.commons:commons-lang3:3.14.0` |
| Project selector | Yêu cầu project thuộc build | `project(':message-lib')` |
| Candidate version | Một version được xem xét khi chọn module | `3.14.0` trong một version range |
| Configuration | Tập dependency có mục đích/thuộc tính cụ thể | `compileClasspath`, `runtimeClasspath` |
| ResolutionStrategy | API cấu hình lựa chọn, force và quy tắc resolution | `configurations.configureEach { resolutionStrategy ... }` |
| Variant | Biến thể producer đáp ứng mục đích compile/runtime | `apiElements`, `runtimeElements` |
| Dependency graph | Quan hệ giữa direct/transitive dependencies đã được giải quyết | App → thư viện A → thư viện B |
| Repository | Nguồn có thể cung cấp metadata và artifact cho module | `mavenCentral()` |

**Project dependency không phải Maven dependency.** `project(':message-lib')` trỏ tới project được `include` trong `settings.gradle`. Nó không tự tìm project cùng tên ở Maven Central. Một yêu cầu module như `org.demo:message-lib:1.0.0` là external module selector; nếu không có substitution, cần repository có artifact tương ứng.

Không phải configuration nào cũng có thể được resolve. Trong Java plugin, `implementation` thường là **bucket để khai báo dependency**, còn `compileClasspath` và `runtimeClasspath` là những configuration được resolve để cung cấp classpath cho task.

## 3. Cú pháp dependency substitution: module → project

Ví dụ Groovy DSL trong `app/build.gradle`:

```groovy
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute module('org.demo:message-lib') using project(':message-lib')
    }
}
```

Đây là rule: những yêu cầu module `org.demo:message-lib` nằm trong configuration chịu quy tắc sẽ được thay bằng project `:message-lib`. Cú pháp không ghi version cho module đang bị thay có thể dùng để nhắm group/name đó; nếu chỉ cần một version, có thể ghi đủ version.

Kotlin DSL tương đương:

```kotlin
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute(module("org.demo:message-lib"))
            .using(project(":message-lib"))
            .because("Thu source library trong build hien tai")
    }
}
```

Trong Kotlin, `substitute(...)`, `using(...)` và `because(...)` là method calls. `because` lưu lý do cho người đọc dependency graph; nên nêu lý do kỹ thuật thực, không phải bình luận mơ hồ.

### 3.1. Thay phiên bản chính xác thay vì cả module

```groovy
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute module('org.demo:message-lib:1.0.0') using project(':message-lib')
    }
}
```

Khác với selector không có version, rule này có phạm vi được nhắm tới **yêu cầu cụ thể**. Lựa chọn giữa selector rộng và hẹp phải có chủ đích. Không nên để bản vá dành cho `1.0.0` vô tình đổi cả những dependency mà ứng dụng cần ở bản `2.0.0`.

### 3.2. Vì sao project phải được include?

Trong `settings.gradle`:

```groovy
rootProject.name = 'dependency-rules-demo'
include 'app', 'message-lib'
```

Đây là cơ sở để `project(':message-lib')` tồn tại. Rule substitution **không** tạo project, không download source và không tự thêm project vào settings. Nếu thiếu `include`, Gradle có thể báo không tìm thấy project path.

Với một **build độc lập** nằm bên ngoài project hiện tại, Gradle có composite build `includeBuild(...)`; không đánh đồng cơ chế đó với `project(':...')` của multi-project build.

### 3.3. Tác động đến task graph

Nếu app nhận external Maven module, Gradle thường lấy artifact đã được publish để đưa vào classpath. Nếu app nhận project `:message-lib`, Gradle có thể phải đưa những task tạo classes/artifact của project đó vào kế hoạch trước task tiêu thụ. Gradle sẽ kết nối các task theo mô hình producer–consumer và variant phù hợp.

Điều đó cũng có nghĩa substitution có thể **làm configuration được resolve sớm hơn trong lúc xác định task graph**, vì Gradle cần biết liệu một dependency ban đầu là module có được đổi thành project và cần task producer hay không. Đừng mutate configuration sau khi nó đã được resolve. Đây là điểm khác với việc chỉ đổi tên chuỗi trong dependency declaration.

## 4. Những hình thức substitution khác

### 4.1. Project → module: dùng bản release thay source

```groovy
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute project(':message-lib') using module('org.demo:message-lib:1.2.0')
    }
}
```

Trong trường hợp này, consumer yêu cầu project local nhưng Gradle chuyển sang external module đã phát hành. **Target module cần có version**, đồng thời repository phải chứa nó. Project local vẫn có trong build nếu được include, nhưng các task tạo output của project ấy không cần được kéo vào **chỉ vì dependency đã thay bằng module external**.

Ứng dụng thực tế: khi tập trung làm việc với app, nhóm muốn dùng một release ổn định của thư viện nội bộ thay vì build source hiện tại. Nhưng phải kiểm tra API, bytecode, JVM target, transitive dependencies và metadata của artifact đã publish. Module và project khác nhau không đảm bảo tương thích.

Kotlin DSL:

```kotlin
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute(project(":message-lib"))
            .using(module("org.demo:message-lib:1.2.0"))
            .because("Dung ban release de build app")
    }
}
```

### 4.2. Module → module: chuyển sang tên mới

```groovy
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute module('org.legacy:old-api') using module('org.newco:new-api:2.0.0')
    }
}
```

Điều này thay thành phần được resolve, **không tự đổi import Java, package hoặc method signature**. Nếu hai module không tương thích, code vẫn không biên dịch hoặc chạy lỗi.

Nếu tình huống thật là một module đã đổi tên chính thức, đồng thời module cũ/mới xuất hiện trong dependency graph, hãy cân nhắc cơ chế **module replacement** thích hợp. Không nên dùng substitution cho mọi kiểu thay đổi tên mà không biết ý nghĩa.

### 4.3. Giới hạn cấu hình chịu tác động

`configurations.configureEach` có thể áp dụng tới nhiều configuration trong **project chứa rule**. Nếu chỉ muốn áp dụng cho một configuration:

```groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.dependencySubstitution {
        substitute module('org.demo:message-lib') using project(':message-lib')
    }
}
```

Cách giới hạn này có rủi ro nếu compile và runtime dùng hai thành phần với API khác nhau. Ví dụ `compileJava` biên dịch với JAR release nhưng `run` dùng source project đã thay đổi method: bạn có thể gặp `NoSuchMethodError`. Khi thử code mới, thường nên giữ compile/runtime resolution nhất quán.

Quy tắc trong `app/build.gradle` không tự áp dụng cho mọi project khác. Nếu muốn chính sách chung, hãy đặt trong convention plugin/build logic được quản lý, tránh rải những đoạn rule mâu thuẫn ở nhiều script.

## 5. Component selection rules: từ chối một phiên bản ứng viên

Một rule `componentSelection` nhận đối tượng `ComponentSelection`. Nó có `candidate` chứa thông tin như `group`, `module`, `version` và phương thức `reject(reason)`.

Ví dụ Groovy DSL:

```groovy
import org.gradle.api.artifacts.ComponentSelection

configurations.configureEach {
    resolutionStrategy.componentSelection {
        all { ComponentSelection selection ->
            if (selection.candidate.group == 'org.demo' &&
                selection.candidate.module == 'shared-utils' &&
                selection.candidate.version == '1.5.0') {
                selection.reject('Ban 1.5.0 co loi da duoc xac nhan')
            }
        }
    }
}
```

Rule có ý nghĩa: nếu candidate đúng module/version, **không chấp nhận** phiên bản này. Nó không nói “hãy dùng 1.4.0”. Nếu selector hoặc constraint không cho phép version khác, resolution có thể thất bại.

### 5.1. `all` và `withModule`

`all` kiểm tra rộng, cần tự lọc group/name. `withModule('group:name')` nhắm một module rõ ràng:

```groovy
import org.gradle.api.artifacts.ComponentSelection

configurations.configureEach {
    resolutionStrategy.componentSelection {
        withModule('org.demo:shared-utils') { ComponentSelection selection ->
            if (selection.candidate.version == '1.5.0') {
                selection.reject('Khong dung version 1.5.0')
            }
        }
    }
}
```

**`withModule` nhận `group:module`, không phải `group:module:version`.** Version cụ thể được so sánh bằng `candidate.version`.

Kotlin DSL:

```kotlin
configurations.configureEach {
    resolutionStrategy.componentSelection {
        withModule("org.demo:shared-utils") {
            if (candidate.version == "1.5.0") {
                reject("Khong dung version 1.5.0")
            }
        }
    }
}
```

Đoạn Kotlin có receiver `ComponentSelection`, nên dùng `candidate` và `reject(...)` trực tiếp. Không chép cú pháp Groovy `ComponentSelection selection ->` vào Kotlin.

### 5.2. Dynamic version: còn ứng viên khác để chọn

Ví dụ dependency:

```groovy
dependencies {
    implementation 'org.demo:shared-utils:1.+'
}
```

Nếu metadata của repository chứa `1.3.0`, `1.4.0` và `1.5.0`, Gradle có thể xét các ứng viên theo mức phiên bản thích hợp:

```text
Selector: 1.+
Các ứng viên: 1.3.0, 1.4.0, 1.5.0

1.5.0 -> reject("...")   (không hợp lệ)
1.4.0 -> được phép         (có thể được chọn)
1.3.0 -> được phép         (không cần chọn nếu 1.4.0 đã phù hợp)
```

Kết quả minh họa là `1.4.0`, **nếu không có constraint/force/version lock hoặc yêu cầu khác làm thay đổi kết quả**. Component selection là cơ chế lọc trong quá trình resolution, không phải bằng chứng mọi graph luôn chọn phiên bản cao nhất theo thứ tự đơn giản.

### 5.3. Static version: từ chối có thể làm build thất bại

Nếu dependency ghi:

```groovy
dependencies {
    implementation 'org.demo:shared-utils:1.5.0'
}
```

và rule từ chối `1.5.0`, không nên mong Gradle tự thay bằng `1.4.0` vì selector **chỉ yêu cầu 1.5.0**. Có thể resolution thất bại nếu không có thay đổi yêu cầu hoặc quy tắc khác được thiết kế phù hợp.

Đây là khác biệt quan trọng giữa **“lọc ứng viên trong một dải”** và **“ép đổi version”**. Muốn dùng `1.4.0` một cách ổn định, cập nhật dependency declaration, constraint hoặc chính sách version là phương án rõ ràng hơn.

## 6. Metadata-based component selection

Trong một số trường hợp, rule cần metadata ngoài chuỗi version. `ComponentSelection` có thể cung cấp metadata status hoặc descriptor tùy loại module/repository.

Ví dụ minh họa bằng Groovy DSL:

```groovy
import org.gradle.api.artifacts.ComponentSelection

configurations.configureEach {
    resolutionStrategy.componentSelection {
        withModule('org.demo:shared-utils') { ComponentSelection selection ->
            if (selection.metadata?.status == 'experimental') {
                selection.reject('Khong chon artifact experimental')
            }
        }
    }
}
```

Dấu `?.` tránh lỗi nếu `metadata` không có. **Không phải mọi module hay Maven repository đều cung cấp status với ý nghĩa giống nhau**. Hãy kiểm tra metadata thực tế, đừng giả định một module có `version` không chứa `-rc` thì status chắc chắn là `release` hoặc an toàn.

Component selection rule hữu ích khi có chính sách phiên bản đáng tin, nhưng **không thay thế quy trình đánh giá lỗ hổng, dependency verification, dependency locking hoặc phân tích giấy phép**.

## 7. Bảng so sánh theo nhu cầu

| Tình huống | Công cụ phù hợp | Vì sao |
| --- | --- | --- |
| Thử module đang phát triển trong source thay vì JAR Maven | `dependencySubstitution` module → project | Thay target component và kết nối task của project |
| Dùng bản release ngoài thay cho project local | `dependencySubstitution` project → module | Dùng artifact đã publish thay source |
| Một module đổi tên, cần chuyển yêu cầu sang module khác | Substitution hoặc module replacement, tùy quan hệ | Thay identity, xem xét conflict và metadata |
| Từ chối version gây lỗi trong dải `1.+` | `componentSelection` + `reject` | Loại ứng viên không được phép |
| Muốn cố định cùng một version cho nhiều project | Version constraint/platform/locking | Mô tả chính sách version hơn là thay component |
| Có module conflict theo capability | Capabilities resolution | Điều phối các module cung cấp cùng capability |
| Cần cập nhật metadata bất thường của module | Component metadata rules | Sửa thông tin producer được đọc bởi resolution |
| Chỉ muốn đổi version của dependency | Sửa declaration/constraint hoặc giải pháp phù hợp | Không cần substitution module→project |

Các công cụ này có thể được dùng chung nhưng đòi hỏi hiểu rõ tương tác. Ví dụ nếu một module external đã bị thay bằng project local, **component selection rule nhắm version external không còn đơn giản áp dụng như trước**; đó là một dependency identity khác trong graph.

## 8. Project thực hành Java 17: dùng cả hai cơ chế

Để có bằng chứng thực tế, ta tạo hai project trong cùng build:

- `:message-lib` chứa Java class `MessageTemplate`.
- `:app` yêu cầu external module `org.training:message-lib:1.0.0` nhưng được substitution thành `project(':message-lib')`.
- `:app` đồng thời yêu cầu `org.apache.commons:commons-lang3` trong range `[3.12.0,3.14.0]` và component selection reject `3.14.0`.

**Đây là một bài học minh họa, không phải khuyến nghị bảo mật đối với version `3.14.0`.** Mục đích là dùng một module công khai thực sự có các bản `3.12.0`, `3.13.0` và `3.14.0` để quan sát cách reject hoạt động. Muốn chạy từ đầu phải có Internet hoặc đã cache được module, cùng một bản Gradle hỗ trợ Java 17.

### 8.1. Cây file

```text
dependency-rules-demo/
├── settings.gradle
├── message-lib/
│   ├── build.gradle
│   └── src/main/java/demo/message/MessageTemplate.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'dependency-rules-demo'
include 'message-lib', 'app'
```

**File `message-lib/build.gradle`:**

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

**File `message-lib/src/main/java/demo/message/MessageTemplate.java`:**

```java
package demo.message;

public final class MessageTemplate {
    private MessageTemplate() {
    }

    public static String text() {
        return "hello from local project";
    }
}
```

**File `app/build.gradle`:**

```groovy
import org.gradle.api.artifacts.ComponentSelection

plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // External module giả định: rule thay thành project local.
    implementation 'org.training:message-lib:1.0.0'

    // Version range có nhiều ứng viên.
    implementation 'org.apache.commons:commons-lang3:[3.12.0,3.14.0]'
}

configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute module('org.training:message-lib') using project(':message-lib')
    }

    resolutionStrategy.componentSelection {
        withModule('org.apache.commons:commons-lang3') { ComponentSelection selection ->
            if (selection.candidate.version == '3.14.0') {
                selection.reject('Loai 3.14.0 de minh hoa quy tac')
            }
        }
    }
}

application {
    mainClass = 'demo.app.Main'
}
```

**File `app/src/main/java/demo/app/Main.java`:**

```java
package demo.app;

import demo.message.MessageTemplate;
import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
                StringUtils.capitalize(MessageTemplate.text())
        );
    }
}
```

Đây là **bộ file đầy đủ** của ví dụ dùng plugin tích hợp `java-library` và `application`. Plugin `application` cung cấp task `run`. Thư viện `commons-lang3` được lấy từ Maven Central, còn `MessageTemplate` được cung cấp bởi project `:message-lib`, không cần artifact `org.training:message-lib:1.0.0` thật trên Maven.

### 8.2. Chạy ứng dụng

Nếu project có Gradle Wrapper, dùng Wrapper. Nếu mới tạo chỉ từ các file ở trên, cần một phiên bản Gradle tương thích đã được cài trên máy để tạo Wrapper một lần:

```bash
gradle wrapper
```

Trên Linux/macOS:

```bash
./gradlew :app:run --quiet
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat :app:run --quiet
```

Nếu giải quyết dependency thành công và có Java 17 toolchain phù hợp, stdout do `Main.main` in là:

```text
Hello from local project
```

`StringUtils.capitalize` viết hoa chữ cái đầu của chuỗi `hello from local project`. Đừng lẫn output của ứng dụng với những dòng log tùy môi trường do Gradle/Wrapper tải distribution hoặc in thông báo.

### 8.3. Hai bằng chứng cần phân tích

**Substitution:** yêu cầu ban đầu của app là module `org.training:message-lib:1.0.0`, nhưng component được chọn là project `:message-lib` vì rule. Nếu bỏ rule, Gradle sẽ thử tìm module external đó ở repository phù hợp và thường thất bại vì tọa độ được dùng trong bài là giả định, không được publish bởi ví dụ.

**Component selection:** yêu cầu `commons-lang3` theo range cho phép một số version, nhưng rule reject `3.14.0`. Trong điều kiện các phiên bản công khai được tìm thấy và không có constraint khác, version `3.13.0` là ứng viên được phép cao nhất dưới `3.14.0`.

Hai kết quả độc lập: substitution tác động thư viện `message-lib`, còn selection rule tác động phiên bản `commons-lang3`. Không có điều kiện nào đòi hỏi chúng phải cùng target một module.

## 9. Đọc dependency graph để kiểm chứng

Chạy trong thư mục gốc:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency message-lib --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Hãy đọc:

1. **Requested:** ban đầu project yêu cầu tọa độ gì?
2. **Selected:** Gradle dùng module/version/project nào?
3. **Why selected:** do substitution, rule, conflict resolution hay constraint?
4. **Configuration:** kết quả ở compile classpath có tương ứng runtime classpath hay không?

Với ví dụ trên, graph có thể trình bày dependency module `org.training:message-lib:1.0.0` đổi thành `project :message-lib`. Phần `commons-lang3` có thể hiển thị range và version được chọn. Hình thức log khác nhau giữa các bản Gradle và cache; không nên coi một bản in cụ thể là stdout chuẩn bắt buộc của mọi phiên bản.

Khi cần thêm chi tiết:

```bash
./gradlew :app:compileJava --info --console=plain
./gradlew :app:run --console=plain
```

`--info` giúp thấy thêm thông tin resolution, task state và cache khi có. `--console=plain` giúp log dễ so sánh. Đừng chỉ xem `BUILD SUCCESSFUL` để khẳng định substitution đã dùng đúng project; hãy xem graph và hành vi ứng dụng.

### 9.1. Thử bỏ substitution

Trong **bản sao** ví dụ, xóa hoặc comment riêng khối:

```groovy
resolutionStrategy.dependencySubstitution {
    substitute module('org.training:message-lib') using project(':message-lib')
}
```

Giữ nguyên dependency `org.training:message-lib:1.0.0`, rồi chạy:

```bash
./gradlew :app:compileJava --console=plain
```

Với repository duy nhất trong bài là Maven Central, module giả định thường không tồn tại, nên resolution thất bại. Điều đó chứng minh rule đang **thay đổi thật component được dùng**, không chỉ sửa tên trong báo cáo.

Khôi phục rule trước khi thực hành tiếp.

### 9.2. Thử bỏ component-selection rule

Giữ range `[3.12.0,3.14.0]` nhưng bỏ riêng khối `componentSelection`. Nếu không có constraint khác, phiên bản cao nhất trong range có thể được chọn là `3.14.0`. Bật lại rule để xem ứng viên bị loại và version khác được chọn.

Không nên hiểu thao tác bỏ/đặt rule là “phá cache” hoàn toàn. Nếu có nghi ngờ metadata dynamic version đã cache không còn phù hợp, đọc `--info` hoặc dùng `--refresh-dependencies` khi cần, thay vì xóa tùy tiện toàn bộ Gradle cache.

### 9.3. Thử selector phiên bản cố định

Giữ rule reject `3.14.0`, nhưng thay dependency thành:

```groovy
implementation 'org.apache.commons:commons-lang3:3.14.0'
```

Khi chạy `:app:compileJava`, có thể thấy lỗi resolution vì ứng viên duy nhất theo selector cố định bị loại. Gradle không được yêu cầu tự chuyển xuống `3.13.0`.

Một số task báo cáo như `dependencies` có thể trình bày dependency thất bại trong report mà không luôn kết thúc lỗi cho cả task báo cáo. Vì vậy dùng `compileJava`, vốn thật sự cần classpath, để xác minh kết quả thất bại.

Sau thử nghiệm, khôi phục version range trước khi chạy lại thành công.

## 10. Kotlin DSL: tương đương đầy đủ

Các file Java không thay đổi. Nếu chọn Kotlin DSL, hãy dùng những script sau thay cho bản Groovy, không chạy đồng thời hai script có cùng vai trò trong một project.

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "dependency-rules-demo"
include("message-lib", "app")
```

**`message-lib/build.gradle.kts`:**

```kotlin
plugins {
    id("java-library")
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}
```

**`app/build.gradle.kts`:**

```kotlin
plugins {
    application
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.training:message-lib:1.0.0")
    implementation("org.apache.commons:commons-lang3:[3.12.0,3.14.0]")
}

configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute(module("org.training:message-lib"))
            .using(project(":message-lib"))
            .because("Dung project local thay module minh hoa")
    }

    resolutionStrategy.componentSelection {
        withModule("org.apache.commons:commons-lang3") {
            if (candidate.version == "3.14.0") {
                reject("Loai 3.14.0 de minh hoa quy tac")
            }
        }
    }
}

application {
    mainClass.set("demo.app.Main")
}
```

Đừng cố viết `using project(':message-lib')` theo cú pháp Groovy vào Kotlin DSL; phải dùng `.using(project(":message-lib"))`. Cũng không cần khai báo kiểu `ComponentSelection` làm tham số lambda Kotlin trong ví dụ trên vì receiver đã được suy ra từ DSL.

## 11. Khi cần rule động có điều kiện

Đôi khi một workspace có nhiều project cùng tên với các module công ty. Có thể chỉ substitute các module thuộc một group xác định và **chỉ khi project local tồn tại**. Ví dụ Kotlin DSL minh họa, đặt ở project có đầy đủ model đã được include:

```kotlin
import org.gradle.api.artifacts.component.ModuleComponentSelector

configurations.configureEach {
    resolutionStrategy.dependencySubstitution.all {
        val selector = requested

        if (selector is ModuleComponentSelector &&
            selector.group == "org.training") {
            val local = findProject(":" + selector.module)
            if (local != null) {
                useTarget(local)
            }
        }
    }
}
```

Điều kiện group tránh đổi nhầm một thư viện của bên khác trùng tên. `findProject` **không tạo project mới**; nó chỉ tìm project đã có trong build. Rule này vẫn có thể thay nhiều dependency bắc cầu nếu tên module khớp. Nếu chỉ cần thay một module, hãy dùng một rule tường minh vì dễ kiểm tra hơn.

Một cách khác là bật substitution chỉ khi có tham số phát triển local:

```groovy
def useLocal = providers.gradleProperty('useLocalMessage').orNull == 'true'

if (useLocal) {
    configurations.configureEach {
        resolutionStrategy.dependencySubstitution {
            substitute module('org.training:message-lib') using project(':message-lib')
        }
    }
}
```

Nhớ rằng **khi tắt rule**, external module phải thật sự tồn tại trong repository hoặc cache phù hợp. Trong bài này, tọa độ `org.training:message-lib` chỉ là ví dụ, không được publish. Đây không phải cấu hình release hoàn chỉnh để bỏ rule rồi chạy CI ngay.

## 12. Component selection và những công cụ resolution khác

| API/cơ chế | Mục đích | Không nên nhầm |
| --- | --- | --- |
| `dependencySubstitution` | Thay identity của yêu cầu module/project | Không phải bộ lọc candidate version đơn thuần |
| `componentSelection` | Reject phiên bản ứng viên không phù hợp | Không chỉ định một project thay thế |
| `resolutionStrategy.force` | Ép một version theo chính sách mạnh | Có thể che yêu cầu xung đột của dependency |
| `eachDependency` | Can thiệp yêu cầu dependency/version lúc resolution | Không giống kiểm tra từng candidate |
| Dependency constraints | Biểu đạt version yêu cầu hoặc giới hạn được phép | Thường phù hợp hơn rule mạnh khi chỉ quản lý version |
| Platform/BOM | Quản lý tập phiên bản nhất quán | Không tạo project dependency |
| Dependency locking | Ghi lại phiên bản resolved để tái lập | Không sửa API library |
| Component metadata rules | Bổ sung/sửa metadata producer | Không tự thay requested project/module |
| Capabilities resolution | Giải quyết những module có capability tương đương | Không thay bằng blacklist version tùy tiện |
| Module replacement | Diễn tả module cũ được thay bởi module khác trong graph | Có ngữ nghĩa khác thay selector đơn giản |

Ví dụ: nếu team muốn chuyển `org.example:util:1.0` sang `1.1`, việc sửa declaration hoặc constraint thường dễ hiểu hơn một substitution rule. Nếu team muốn thay source module để debug, đó mới là ứng dụng đúng trọng tâm của dependency substitution.

Component selection có thể là cách **chặn tạm thời một bản lỗi** trong dải version, nhưng dùng dynamic version lâu dài cần đánh giá tính tái lập và chính sách update. Với release nghiêm ngặt, dependency locking/verification và phiên bản xác định thường dễ kiểm soát hơn.

## 13. Transitive dependency và conflict resolution

Một app có thể có graph:

```text
:app
  +-- org.demo:feature:1.0
  |      \-- org.demo:shared-utils:1.5
  |
  \-- org.demo:shared-utils:1.4
```

Nếu rule component selection reject `1.5`, kết quả còn phụ thuộc selector/constraint khác. Nếu chỉ cho phép `1.5`, resolution có thể thất bại thay vì chọn `1.4`. Đừng ghi nhớ một quy tắc máy móc “Gradle luôn chọn cao nhất sau khi lọc” cho mọi graph.

Substitution có thể tác động cả **dependency bắc cầu** khi selector của nó khớp trong configuration đang resolve. Đặt một rule module → project có thể thay thành phần không được khai báo trực tiếp trong app nhưng được thư viện khác kéo vào. Do đó cần giới hạn group/name/version và quan sát graph toàn cục.

Khi nhiều rule cùng tác động cùng một selector, việc chúng được áp dụng và thứ tự khai báo có thể ảnh hưởng kết quả. Tránh chồng rule mâu thuẫn ở script project, convention plugin và init script mà không có kiểm thử. Đừng coi `dependencyInsight` sau khi đã sửa graph là bằng chứng đủ để xác nhận mọi runtime behavior; cần chạy test và ứng dụng.

## 14. Composite build và substitution tự động

Gradle còn hỗ trợ **composite builds** với `includeBuild(...)` trong settings. Một build có thể dùng component của build khác thay cho module đã phát hành theo cơ chế substitution tự động hoặc rule tường minh.

Ví dụ sơ đồ:

```text
application-build/
  settings.gradle -> includeBuild('../library-build')

library-build/
  settings.gradle
  build.gradle

app yêu cầu org.example:library:1.0
           |
           v
Gradle có thể tìm project trong included build
tương ứng với group/name của module
```

Đây là trường hợp **hai build độc lập**, khác với `include 'message-lib'` của multi-project. Không nên tự giả định mọi included build đều match mọi module: group/name, publication, variant và cấu hình còn quyết định kết quả. Nếu cần thay rõ một module có tên artifact khác project name, cấu hình substitution tường minh là lựa chọn đáng xem xét.

## 15. Rủi ro trong CI và production

### 15.1. API/ABI của project local khác module đã publish

Một module phát hành có thể chứa method `methodA()` trong khi source project đã đổi thành `methodB()`. Substitution vẫn có thể chọn project thành công nhưng ứng dụng gặp lỗi compile/runtime. Những khác biệt khác gồm:

- JVM target và Java toolchain.
- Public class/method signatures.
- Transitive dependencies và variant metadata.
- Test fixtures hoặc capability do plugin công bố.
- Phiên bản chưa được review hoặc chưa chạy integration tests.

Vì thế hãy chạy `compileJava`, `test`, `run` và kiểm thử tích hợp thích hợp sau khi substitution, không chỉ xác nhận graph có tên project.

### 15.2. Không làm build chỉ hoạt động trên máy một người

Một rule module → project local bật vô điều kiện có thể thất bại khi CI thiếu project tương ứng. Khi dùng override để phát triển, nên có:

1. Điều kiện bật rõ ràng.
2. Project đích có mặt khi rule bật.
3. Artifact remote chính thức khi rule tắt.
4. Cấu hình repository/credential chuẩn cho CI.
5. Kiểm thử cả hai đường chạy.

Không dùng `mavenLocal()` như cách sửa chung cho trường hợp thiếu artifact chính thức; nó có thể khiến CI và laptop dùng nội dung khác nhau dù tọa độ trùng.

### 15.3. Rule quá rộng hoặc quá cũ

Rule `all` reject mọi version có suffix `-rc` có thể loại cả những dependency testing cần RC. Rule substitution không giới hạn group có thể thay sai module của tổ chức khác. Một rule “tạm” giữ nhiều năm có thể ẩn sự cố đã được sửa trong release mới.

Hãy ghi lý do, phạm vi, thời điểm/điều kiện gỡ bỏ, owner và có test cho dependency graph. Khi nâng cấp version, rà soát rule thay vì giữ nguyên mặc định.

## 16. Caching và khả năng tái lập

| Tùy chọn/cơ chế | Tác động chính |
| --- | --- |
| `--refresh-dependencies` | Yêu cầu Gradle kiểm tra lại trạng thái dependency/metadata theo cơ chế cache |
| `--offline` | Không truy cập repository từ xa; cần dữ liệu phù hợp đã có |
| `--no-build-cache` | Tắt build output cache, không phải version selection |
| `clean` | Xóa output build project, không xóa toàn bộ dependency cache |
| Dependency locking | Giữ bản ghi các version đã resolve trong những configuration được quản lý |
| Dependency verification | Kiểm tra tính toàn vẹn nguồn artifact theo chính sách được cấu hình |

Khi dùng dynamic versions, metadata từ repository có thể được cache trong một khoảng thời gian. Không nên kỳ vọng hai lần build với cùng `1.+` luôn chọn cùng version vào hai thời điểm khác nhau nếu repository có bản mới. Component selection rule cũng không tự đóng băng toàn bộ graph. Dùng locking/constraint/version pinning nếu tính tái lập quan trọng.

Không xóa toàn bộ `~/.gradle/caches` chỉ vì rule không như dự kiến; trước hết đọc `dependencyInsight`, xác định configuration, requested và selected. Nếu cần kiểm tra metadata mới, sử dụng `--refresh-dependencies` phù hợp.

## 17. Lỗi thường gặp và chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `Project with path ':message-lib' could not be found` | Project chưa include, path sai | Xem `settings.gradle`, chạy `./gradlew projects` |
| Module vẫn được tải từ Maven thay vì project | Rule không khớp selector hoặc sai configuration | Đọc `dependencyInsight` và vị trí rule |
| Một dependency bắc cầu bị thay ngoài ý muốn | Rule module quá rộng | Thu hẹp group/name/version |
| Code compile nhưng run lỗi `NoSuchMethodError` | Compile/runtime có component khác ABI | Thống nhất resolution, kiểm tra variant/API |
| Version bị reject nhưng không chọn version cũ hơn | Selector cố định hoặc constraint không cho phép | Chọn range hợp lý hay sửa declaration/constraint |
| Mọi candidate đều bị reject | Rule quá chặt hoặc không có bản hợp lệ | Thu hẹp rule hoặc cập nhật dependency |
| `withModule` không chạy | Sai group:name hoặc module đã bị thay thành project | Kiểm tra requested/selected component |
| Metadata status null | Repository không có thông tin được kỳ vọng | Không dùng status như tín hiệu bắt buộc |
| CI không tìm thấy project substitution | Local project không có trong checkout | Chỉnh điều kiện bật rule, repo/build setup |
| Configuration báo lỗi thay đổi sau resolution | Có code mutate quá muộn, substitution ảnh hưởng thời điểm resolution | Cấu hình dependency/rule sớm, không sửa sau resolve |
| Kotlin DSL lỗi cú pháp ở `using` | Dùng cú pháp Groovy trong Kotlin | Dùng `.using(project("..."))` |
| `dependencies` báo mục FAILED nhưng command vẫn kết thúc | Task báo cáo có thể hiển thị failure trong graph | Chạy `compileJava` hay task cần classpath |
| Dynamic version thay đổi kết quả giữa các máy | Repository/metadata cache/lock khác nhau | Pin version, dùng locking và kiểm tra repository |
| Module thay thế build được nhưng API không hợp | Project local không tương đương artifact phát hành | Chạy compile/test và so sánh public contract |

Quy trình chẩn đoán:

1. Đọc **module/project được yêu cầu** ở dependency declaration.
2. Kiểm tra `settings.gradle` nếu target là project.
3. Xác định **configuration đang resolve**: `compileClasspath` hay `runtimeClasspath`?
4. Xem **rule có áp dụng ở đúng project/configuration** không.
5. Kiểm tra selector, group/module/version và condition reject.
6. Dùng `:app:dependencies`, `:app:dependencyInsight`.
7. Chạy task thật, ví dụ `:app:compileJava` và `:app:run`.
8. Nếu vẫn khó giải thích, thêm `--info`, đối chiếu constraint/locking/metadata.
9. Đảm bảo đường build bình thường trên CI không ngầm cần source local.

## 18. Bài tập tự luyện

**Bài tập A — module → project.** Dùng ví dụ mục 8, chạy `dependencyInsight` cho `message-lib`. Ghi lại requested `org.training:message-lib:1.0.0` và selected project. Vì sao không phải publish library lên Maven?

**Bài tập B — bỏ substitution.** Trong bản sao, bỏ rule nhưng giữ external module giả định. Chạy `:app:compileJava`. Dự đoán lỗi, rồi khôi phục rule. Đây là bằng chứng thay component hay chỉ thay tên log?

**Bài tập C — lọc version.** Giữ range `commons-lang3`, xem `dependencyInsight` trước/sau khi bỏ rule `withModule`. Giải thích ý nghĩa `reject("...")`.

**Bài tập D — fixed version.** Đổi từ version range sang `3.14.0` cố định rồi giữ rule reject. Vì sao Gradle không buộc phải chọn `3.13.0`? Cách cấu hình rõ hơn nếu muốn dùng `3.13.0` là gì?

**Bài tập E — `all` so với `withModule`.** Viết rule `all` chỉ reject khi cả group, module và version trùng `org.apache.commons:commons-lang3:3.14.0`. So sánh mức độ dễ đọc với `withModule`.

**Bài tập F — bật/tắt khi phát triển local.** Dùng project property `useLocalMessage` ở mục 11 để bật substitution. Giải thích vì sao đường tắt cần external artifact thực, trong khi đường bật cần project đã include.

**Bài tập G — scope của rule.** Chỉ đặt substitution vào `runtimeClasspath`, dự đoán khác biệt với compile classpath. Tại sao code có thể build bằng API khác với API dùng khi chạy? Sau đó phục hồi cấu hình nhất quán.

**Bài tập H — chọn công cụ.** Với các nhu cầu: dùng source local, loại một bản lỗi trong range, ghim version cho nhiều project, xử lý capability conflict, thay metadata module — hãy chọn lần lượt substitution, selection, constraints/platform/locking, capabilities, metadata rules.

### Câu hỏi kiểm tra kiến thức

1. Dependency substitution thay selector hay chỉ lọc candidate version?
2. `ComponentSelection.reject` có tự chuyển external module thành project không?
3. Tại sao `project(':message-lib')` cần được include trong settings?
4. Trong module → project substitution, tại sao task graph có thể cần biết project producer sớm?
5. `withModule('group:name')` khác `all` như thế nào?
6. `candidate.version` là version của thành phần nào?
7. Nếu version `1.5.0` bị reject trong range `1.+` thì Gradle có thể chọn gì?
8. Nếu version cố định `1.5.0` bị reject thì sao?
9. Vì sao `org.training:message-lib:1.0.0` không cần tồn tại trên Maven Central trong bài thực hành?
10. Rule đặt trong `:app` có tự áp dụng cho `:message-lib` không?
11. Vì sao compile và runtime classpath phải được kiểm tra riêng?
12. Khi nào nên dùng version constraint thay vì substitution?
13. Component selection có thay thế dependency verification không?
14. Tại sao cần đọc dependency graph thay vì chỉ nhìn `BUILD SUCCESSFUL`?
15. Dynamic version và dependency cache ảnh hưởng tính tái lập như thế nào?
16. Composite build `includeBuild` và multi-project `include` khác nhau ở đâu?
17. Vì sao việc thay module bằng project local có thể gây lỗi API/ABI?
18. Một rule mạnh được giữ quá lâu có thể che giấu vấn đề gì?

**Tài liệu chính thức:** [Gradle — Using Resolution Rules](https://docs.gradle.org/current/userguide/resolution_rules.html); [Gradle — ResolutionStrategy API](https://docs.gradle.org/current/dsl/org.gradle.api.artifacts.ResolutionStrategy.html).

**Ghi nhớ:** `dependencySubstitution` thay **thành phần được yêu cầu**, còn `componentSelection` từ chối **những phiên bản ứng viên** không được phép. Chọn đúng configuration, hạn chế phạm vi rule, công bố lý do, kiểm tra graph requested/selected và chạy task Java thực tế để xác minh kết quả.