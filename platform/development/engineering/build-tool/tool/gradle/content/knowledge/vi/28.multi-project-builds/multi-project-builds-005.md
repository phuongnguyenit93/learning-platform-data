# Chia sẻ cấu hình bằng allprojects, subprojects và các giới hạn trong Gradle

## 1. Vì sao một multi-project build cần chia sẻ cấu hình?

Một ứng dụng Java có thể được chia thành nhiều module: `:core` chứa domain model, `:app__ chứa chương trình chính, `:data` truy cập cơ sở dữ liệu. Các module thường có vài quy ước chung: `group`, `version`, Java release, repositories và cấu hình kiểm thử. Sao chép nguyên một block cấu hình vào từng `build.gradle` làm tăng nguy cơ lệch phiên bản, khó sửa hàng loạt và dễ gây lỗi khi thêm module.

Gradle cung cấp API lâu đời để cấu hình nhiều Project từ một chỗ:

- **`allprojects { ... }`**: áp dụng action cho **Project nhận lệnh** và **mọi subproject bên dưới nó**.
- **`subprojects { ... }`**: áp dụng action cho **các subproject bên dưới Project nhận lệnh**, **không** áp dụng cho chính Project đó.

Đây là hình thức **cross-project configuration** (cấu hình chéo từ một Project khác). Nó tiện cho project nhỏ và để đọc những build script cũ, nhưng có **giới hạn về coupling, thứ tự cấu hình, tính tái sử dụng, Isolated Projects và khả năng mở rộng**. Tài liệu Gradle hiện hành **ưu tiên convention plugins** thay cho các block `allprojects`/`subprojects` khi chia sẻ build logic có tính lâu dài.

**Kết quả học tập:** sau bài học, bạn có thể phân biệt phạm vi hai API; chạy một multi-project Gradle Java 17+ với `:core` và `:app`; biết khi nào callback plugin là cần thiết; giải thích vì sao `repositories` hoặc `implementation` không phải thứ có thể đưa bừa vào mọi project; xác định các lỗi cross-project; và chuyển cấu hình sang một **precompiled convention plugin bằng Groovy DSL** có thể tái sử dụng.

> Bài dùng Gradle Groovy DSL (`settings.gradle`, `build.gradle`), Java 17+ và Gradle Wrapper. Các fragment mang nhãn “phương án thay thế” không được dán chồng lên ví dụ chính. Để giữ ví dụ độc lập, phần Java baseline không cần thư viện bên ngoài.

## 2. Hiểu cấu trúc Project trước khi nói allprojects

Một **Gradle build** có root project và các subprojects được khai báo bằng `include` trong `settings.gradle`. Ví dụ:

```groovy
rootProject.name = 'sharing-config-lab'
include 'core', 'app'
```

Đồ thị Project logic:

```text
:                 root project: sharing-config-lab
├── :core         child project
└── :app          child project
```

Các **project paths** là `:`, `:core`, `:app`. Chúng **khác** với paths của task, ví dụ `:core:compileJava` hay `:app:run`.

Root project không phải “một cấu hình toàn cục không có project”. Nó cũng có `Project`, `build.gradle`, tasks, extensions và có thể có source code; tuy nhiên nhiều multi-project builds chỉ dùng root để điều phối, không biên dịch Java tại root.

### 2.1. Phạm vi chính xác

Giả sử block được đặt trong **root `build.gradle`**:

| API | Root `:` | `:core` | `:app` |
| --- | --- | --- | --- |
| `allprojects { ... }` | Có | Có | Có |
| `subprojects { ... }` | Không | Có | Có |
| Cấu hình trực tiếp không nằm trong block | Có | Không | Không |

Nếu chỉ có **single-project build** không có subproject, `allprojects` vẫn chạy cho project hiện tại; `subprojects` không có project nào để áp dụng.

**Lưu ý:** đây là phạm vi **Project nhận lệnh**. Nếu gọi `subprojects { ... }` từ một project trung gian, nó chỉ chọn các descendants của project đó, không tự chọn các nhánh anh em hoặc root. Thuộc tính `childProjects` trả về **con trực tiếp**, khác `subprojects` (tập subprojects bên dưới project được nói đến).

### 2.2. Với project lồng nhau

```groovy
rootProject.name = 'nested-example'
include 'services:api', 'services:worker', 'libraries:common'
```

Một phần cây project:

```text
:
├── :services
│   ├── :services:api
│   └── :services:worker
└── :libraries
    └── :libraries:common
```

Từ root, `subprojects` bao gồm các projects bên dưới, kể cả project cấp trung gian `:services` và cấp sâu `:services:api`; root `:` không thuộc tập đó. `allprojects` cộng thêm root. Không đồng nhất tên thư mục với quan hệ Project nếu `projectDir` đã được remap.

### 2.3. Multi-project khác composite build

`include 'core', 'app'` tạo subprojects trong một build. Còn `includeBuild('build-logic')` hoặc `includeBuild('../shared-lib')` đưa vào **included build** riêng. Một block `allprojects { ... }` trong root build **không tự lan sang các projects của included build**, vì chúng thuộc build boundary khác.

Đây là khác biệt quan trọng khi team tách build logic vào `build-logic`: cấu hình shared phải được đóng gói thành plugin và được apply, không trông chờ root `subprojects` chạm vào included build.

## 3. API allprojects: root và toàn bộ descendants

Ví dụ trong root `build.gradle`:

```groovy
allprojects {
    group = 'org.example.school'
    version = '1.0.0'
}
```

Gradle thiết lập `group`, `version` cho **root** và **mọi subprojects** trong build tree thuộc root. Đây là một ví dụ “ngắn và chạy được” phù hợp để đọc hiểu API.

**Mỗi closure được thực thi với project đích làm delegate/target.** `group = ...` ở đây gán thuộc tính của project đang được cấu hình, không phải một biến global và cũng không phải luôn là root group.

Khi subproject đặt lại:

```groovy
// File: app/build.gradle, sau khi root đã đặt quy ước.
version = '2.0.0'
```

`:app` có thể có version riêng. Tuy nhiên logic thay đổi từ nhiều project scripts dễ gây nhầm về thứ tự và ownership. Hãy có chính sách rõ: shared value là **default** hay **bắt buộc**, module nào được override và tại đâu.

### 3.1. Allprojects không tự biết plugin nào phù hợp

Một anti-pattern:

```groovy
// PHẢN VÍ DỤ: áp Java lên cả root và mọi module.
allprojects {
    apply plugin: 'java'
}
```

Điều này làm root (dù chỉ đóng vai trò aggregator) cũng có `compileJava`, `jar`, `test`...; một module `:docs` chỉ chứa tài liệu cũng bị biến thành Java module. Build có thể xuất hiện tasks và output không cần thiết.

**Phân biệt:** `allprojects` chỉ quyết định **phạm vi**. Nó **không** tự lọc loại module; nếu bên trong có `apply plugin: 'java'` thì Gradle áp plugin cho từng target project.

### 3.2. Cấu hình có điều kiện dựa trên plugin

Để tác động JavaCompile chỉ ở nơi **đã có Java plugin**:

```groovy
allprojects {
    plugins.withId('java') {
        tasks.withType(JavaCompile).configureEach {
            options.release = 17
        }
    }
}
```

`plugins.withId('java')` chạy callback khi plugin `java` được apply, kể cả thông qua `application` hoặc `java-library`. Như vậy không giả định extension/task `java` có sẵn trước khi plugin được áp dụng.

Tuy nhiên **dù dùng callback**, block vẫn là **cross-project configuration** khi root cấu hình subprojects. Nó khắc phục rủi ro **plugin-order**, **không** xóa coupling hay khiến code tự động tương thích với **Isolated Projects**.

## 4. API subprojects: tất cả subprojects nhưng không gồm root

Ví dụ đặt trong root `build.gradle`:

```groovy
subprojects {
    repositories {
        mavenCentral()
    }

    plugins.withId('java') {
        tasks.withType(JavaCompile).configureEach {
            options.release = 17
        }
    }
}
```

Chỉ `:core` và `:app` nhận cấu hình nếu build có hai module đó. Root không bị tạo repository/project JavaCompile rules bởi block này.

**Ưu điểm khi mới học:** dễ thấy sự khác biệt root so với subprojects; ít lặp cú pháp cho một build nhỏ. **Đổi lại:** mỗi module phải biết root đã inject rule gì, quá trình đọc build script của riêng nó không còn cho thấy toàn bộ hành vi.

### 4.1. Không ép mọi module đều dùng plugin giống nhau

Một dạng root script dễ viết nhưng có hệ quả:

```groovy
// PHẢN VÍ DỤ khi các module khác loại nhau.
subprojects {
    apply plugin: 'java'
    apply plugin: 'maven-publish'
}
```

Hành vi:

- Module dùng `application` hoặc `java-library` có Java plugin được apply nhiều lần (Gradle xử lý plugin apply idempotent ở mức plugin), nhưng root vẫn đang **đưa quyết định plugin vào nơi khác**.
- Module chỉ có docs, Gradle platform/BOM, native hoặc plugin build riêng bị thêm capability không cần thiết.
- Module publishing có thể bị cấu hình publication ngoài ý muốn hoặc logic chưa sẵn sàng.
- Plugin nào áp trước/callback nào chạy trước trở thành một vấn đề trong việc theo dõi bugs.

**Khuyến nghị:** để subproject **tự công bố plugin** trong `plugins { }`, hoặc dùng một convention plugin có tên rõ và apply ở những modules phù hợp. Root không cần kiểm soát ngầm mọi plugin.

### 4.2. Cú pháp plugins { } khác apply plugin

Trong file `app/build.gradle`:

```groovy
plugins {
    id 'application'
}
```

Đây là **Plugin DSL** chạy ở phần được Gradle quy định của script. Bạn **không thể** đặt tùy tiện một `plugins { id 'java' }` bên trong `subprojects { }` ở root và giả định nó hoạt động như top-level plugin block.

Trong root cross-project configuration, cú pháp imperative thường thấy là:

```groovy
subprojects {
    apply plugin: 'java'
}
```

Nhưng đây chính là injection mà bài cần hiểu các giới hạn, không phải hướng mặc định cho dự án dài hạn.

## 5. Lab đầy đủ: root chia sẻ cấu hình cho core và app

Đây là một multi-project build **runnable trên Java 17+**. Root **không** apply Java plugin; core dùng `java-library`, app dùng `application`. Mỗi module khai báo plugin rõ; root chỉ thiết lập group/version/repositories và Java release cho những module đã apply Java plugin.

### 5.1. Cây thư mục

```text
sharing-config-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── core/
│   ├── build.gradle
│   └── src/main/java/example/core/Greeting.java
└── app/
    ├── build.gradle
    └── src/main/java/example/app/Main.java
```

`gradlew`/`gradlew.bat` và `gradle/wrapper/...` phải có từ project init hoặc tạo bằng `gradle wrapper` với Gradle tương thích; chúng không tự sinh ra khi chỉ tạo `settings.gradle`. Dùng Gradle Wrapper đã pin cho team/CI và JDK 17+ hỗ trợ bản Gradle đó.

### 5.2. Root settings.gradle

```groovy
rootProject.name = 'sharing-config-lab'
include 'core', 'app'
```

`include` **xác định thành viên build**. Nó **khác** `subprojects { }`: block trong `build.gradle` không tự tạo `:core` nếu settings chưa include project đó.

### 5.3. Root build.gradle

```groovy
allprojects {
    group = 'org.example.school'
    version = '1.0.0'
}

subprojects {
    repositories {
        mavenCentral()
    }

    plugins.withId('java') {
        tasks.withType(JavaCompile).configureEach {
            options.release = 17
        }
    }
}
```

Đây là **root build.gradle hoàn chỉnh** của lab:

- `allprojects` đặt group/version cho root, core và app.
- `subprojects` đưa repository `mavenCentral()` tới core/app, không tới root.
- `plugins.withId('java')` chỉ cấu hình `JavaCompile` **sau khi Java plugin hiện diện**, tránh truy cập task/extension quá sớm.
- `tasks.withType(JavaCompile).configureEach` cấu hình lazy cho các JavaCompile tasks trong project đích, bao gồm source set main/test nếu có.
- `options.release=17` nhắm Java 17 language level, bytecode và exposed Java SE APIs; nó **không tự provision đúng JDK 17**, nên cần compiler đủ mới để hiểu `--release 17`.
- Không có `plugins { id 'java' }` tại root: root không tự có `:jar` hoặc `:compileJava`.

Trong lab này không có external Maven library, nên cấu hình Maven Central chưa được dùng để tải JAR ngoài; vẫn minh họa chính xác nơi repository áp dụng.

### 5.4. File core/build.gradle

```groovy
plugins {
    id 'java-library'
}
```

`java-library` mang Java plugin; vì thế callback `plugins.withId('java')` của root sẽ cấu hình tasks JavaCompile cho `:core`. Core là một thư viện, không có `main()` và không cần Application plugin.

### 5.5. File core/src/main/java/example/core/Greeting.java

```java
package example.core;

public record Greeting(String recipient) {
    public String text() {
        return "Hello, " + recipient + "!";
    }
}
```

`record` là feature chính thức từ Java 16, hợp lệ trên Java 17. Đặt file đúng source root `src/main/java` để `:core:compileJava` tạo bytecode `example/core/Greeting.class`.

### 5.6. File app/build.gradle

```groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':core')
}

application {
    mainClass = 'example.app.Main'
}
```

`implementation project(':core')` là **dependency giữa các Gradle projects**. Nó làm `:app` compile/runtime thấy classes/artifact tương ứng của `:core`, và Gradle biết các task cần chạy theo dependency graph. Đây là cách **liên kết modules** đúng, không cần root tự thiết lập task order bằng `evaluationDependsOn`.

### 5.7. File app/src/main/java/example/app/Main.java

```java
package example.app;

import example.core.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String who = args.length == 0 ? "Gradle" : args[0];
        System.out.println(new Greeting(who).text());
    }
}
```

App dùng class `Greeting` từ core qua declared project dependency. Mã **không phụ thuộc vào đường dẫn output build/** hay việc root chạy trước. Nó dùng chính Java classes từ classpath đã được Gradle tổ chức.

### 5.8. Lệnh build và stdout

Linux/macOS:

```bash
./gradlew projects --console=plain
./gradlew :core:compileJava --console=plain
./gradlew :app:run --quiet
./gradlew :app:run --args="Team" --quiet
./gradlew :app:build --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat projects --console=plain
.\gradlew.bat :core:compileJava --console=plain
.\gradlew.bat :app:run --quiet
.\gradlew.bat :app:run --args="Team" --quiet
.\gradlew.bat :app:build --console=plain
```

**Stdout chính xác của Java program khi chạy riêng hai lệnh `:app:run`:**

Không truyền argument:

```text
Hello, Gradle!
```

Truyền `--args="Team"`:

```text
Hello, Team!
```

Đó là **hai lần chạy riêng**, không phải một lần in hai dòng. Lệnh `projects` liệt kê project structure; `:app:build` và `:core:compileJava` in Gradle task logs tùy phiên bản/caches, không có stdout Java tương tự.

**Điều kiện chạy:** Gradle Wrapper hợp lệ, JDK dùng cho compile hỗ trợ `--release 17`, cấu trúc file/package đúng. Nếu Gradle chạy bằng JDK 17 hoặc mới hơn được hỗ trợ, lab không đòi dependency Maven nên cũng có thể chạy offline sau khi Wrapper distribution đã sẵn sàng.

### 5.9. Xác minh phạm vi áp dụng

- Chạy `./gradlew :app:tasks`: vì có Application plugin, thấy task `run`.
- Chạy `./gradlew :core:tasks`: có tasks Java-library nhưng **không** tự có `run`.
- Chạy `./gradlew :tasks` ở root: không có root `:run` hoặc `:jar` do root không apply Java/Application plugin.
- `allprojects` đặt `group='org.example.school'` và `version='1.0.0'` cho cả ba projects, nhưng output Java riêng của mỗi module vẫn thuộc `core/build` hoặc `app/build`, không dồn vào root.
- `:app:run` tự dùng project dependency `:core`, không phải do `subprojects` tạo dependency.

Một đoạn print project metadata để học có thể thêm **tạm thời** vào root `build.gradle`:

```groovy
tasks.register('showRootCoordinates') {
    def rootGroup = project.group.toString()
    def rootVersion = project.version.toString()
    doLast {
        println "root: " + rootGroup + ":" + rootVersion
    }
}
```

Lệnh `./gradlew -q showRootCoordinates` in:

```text
root: org.example.school:1.0.0
```

Task chỉ dùng **hai String đã lấy trong configuration** vào action; không truy cập project/rootProject trong `doLast`. Fragment này là **mở rộng độc lập để quan sát**, không cần cho hai lệnh Java.

## 6. Điểm dễ nhầm: task selector không giống API subprojects

Từ root, câu lệnh:

```bash
./gradlew test
```

có thể chọn task `test` ở những subprojects có task đó, theo **quy tắc task selector** của Gradle. Đây không phải vì root `subprojects { }` tự tạo task test; Java plugin trong các subprojects mới là thứ tạo `test`.

Khi cần chính xác module:

```bash
./gradlew :core:test
./gradlew :app:test
./gradlew :app:run
```

`./gradlew :app:run` vẫn có thể kéo các task cần thiết của core theo **task dependency**, nhưng không vô cớ chạy tất cả tasks của core. `./gradlew :core:build` không tự build app vì app phụ thuộc core; hướng dependency là app → core, không phải ngược lại.

Đừng dùng `subprojects { task 'test' ... }` chỉ để chạy toàn bộ tests: Java plugins đã có test tasks, và Gradle task selectors/lifecycle giúp bạn lựa chọn đúng.

## 7. Giới hạn thứ nhất: project coupling và cấu hình xuyên project

**Project coupling** xảy ra khi cấu hình của một project đọc hoặc thay đổi trạng thái build model của project khác thay vì để mỗi project tự định nghĩa nó. Root inject:

```groovy
subprojects {
    repositories {
        mavenCentral()
    }
}
```

là một dạng đơn giản của coupling: logic của `:core` thực tế nằm ở root. Khi dự án lớn, các ví dụ rủi ro hơn:

```groovy
// PHẢN VÍ DỤ: root cấu hình tasks của một project cụ thể.
project(':app') {
    tasks.named('run') {
        // Khó theo dõi khi plugin chưa áp dụng / task chưa tồn tại.
    }
}
```

Vấn đề không phải mọi thao tác cross-project luôn sai hoặc bị Gradle cấm trong chế độ truyền thống. Vấn đề là chúng tạo **dependency ngầm** giữa thời điểm evaluate root, child plugin application, subproject scripts và những callbacks khác. Project không còn thật sự độc lập.

Hệ quả:

1. **Khó đọc build script:** chỉ xem `app/build.gradle` không thấy mọi rule đang tác động đến app.
2. **Khó sửa cục bộ:** thay root có thể làm tất cả subprojects cấu hình lại và phát sinh lỗi ở module không liên quan.
3. **Khó chuyển plugin theo loại module:** một block lớn chứa nhiều điều kiện `if (project.name == ...)` rất dễ trở thành cấu hình đặc biệt hóa theo tên.
4. **Giảm khả năng tối ưu:** Gradle khó song song cấu hình projects và khó cô lập chúng trong các chế độ build hiện đại.
5. **Khó kiểm thử build logic:** logic phụ thuộc root/other projects hơn là một plugin độc lập có thể test, version và reuse.

### 7.1. Đừng lấy data của project khác trong task action

Phản ví dụ có rủi ro với **Configuration Cache**:

```groovy
// PHẢN VÍ DỤ: task action giữ/đọc live Project state.
tasks.register('showOtherVersion') {
    doLast {
        println project(':core').version
    }
}
```

Đọc `project(':core')` từ execution-time task action sử dụng live Gradle Project model và không đáp ứng cách Gradle Configuration Cache serialize/restore task state. Nếu một task cần thông tin version, hãy mô hình hóa input bằng `Property` / `Provider` hoặc lấy immutable String trong configuration, không dùng project object trong task action.

Trong lab mục 5, `showRootCoordinates` lấy Strings trước `doLast` để tránh lỗi rõ ràng này.

### 7.2. Subproject dependency không phải coupling xấu tương tự

```groovy
dependencies {
    implementation project(':core')
}
```

là một **declared project dependency**, hoàn toàn khác việc root sửa trực tiếp task/extension của `:core`. Nó cho Gradle đủ thông tin tạo classpath và thứ tự task; đó là mô hình multi-project được khuyến nghị. **Không loại bỏ các declared project dependencies chỉ vì muốn tránh cross-project configuration.**

## 8. Giới hạn thứ hai: plugin lifecycle và thứ tự đánh giá

### 8.1. Extension java chưa tồn tại nếu plugin chưa apply

Phản ví dụ:

```groovy
// PHẢN VÍ DỤ: không bảo đảm mọi module đã có Java extension.
subprojects {
    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(17)
        }
    }
}
```

Nếu một module `:docs` không apply Java plugin hoặc root action chạy khi Java extension chưa được tạo, đoạn trên có thể lỗi dạng `Could not find method java()` hoặc missing extension.

**Giải pháp ngắn hạn khi vẫn giữ cross-project configuration:**

```groovy
subprojects {
    plugins.withId('java') {
        java {
            toolchain {
                languageVersion =
                    JavaLanguageVersion.of(17)
            }
        }
    }
}
```

Callback đợi Java plugin, vì vậy Java extension hiện diện. Nhưng cấu hình này thực sự yêu cầu một **JDK 17 toolchain** cho modules có Java plugin; nếu không có matching JDK và provisioning source, build có thể fail. Nó là **phương án thay thế** cho `options.release = 17` của lab, không tự đồng nghĩa Java release option.

### 8.2. afterEvaluate thường không phải cách sửa tốt

Một số build cũ viết:

```groovy
// PHẢN VÍ DỤ: trì hoãn mọi thứ để né plugin order.
subprojects {
    afterEvaluate {
        tasks.named('compileJava') {
            options.release = 17
        }
    }
}
```

Nếu project không có `compileJava`, task lookup fail. Nếu project được evaluate trong thứ tự khác, callback có thể đăng ký quá muộn. Với Configuration Cache/Isolated Projects, các listener/callback phụ thuộc state toàn build có thêm rủi ro và chi phí.

Ưu tiên:

- `plugins.withId('java')` khi thực sự cần cấu hình sau plugin apply.
- `tasks.withType(JavaCompile).configureEach` để cấu hình lazy theo task type.
- **Convention plugin** apply trong project đích để vừa làm rõ dependency vào plugin vừa tránh root inject state.

### 8.3. Plugin DSL không phải tập lệnh imperative tùy chỗ

Trong `app/build.gradle`, `plugins { id 'application' }` là top-level plugin declaration. Trong root `subprojects { ... }`, bạn **không** đặt một top-level `plugins { }` của từng child. Chọn project plugin bằng cách khai báo trong build script tương ứng hoặc apply một convention plugin riêng tại đó.

## 9. Giới hạn thứ ba: Configuration Cache khác Isolated Projects

Đây là phần dễ bị mô tả quá đơn giản. **Configuration Cache** và **Isolated Projects** có quan hệ, nhưng không phải một tính năng duy nhất.

| Khía cạnh | Configuration Cache | Isolated Projects |
| --- | --- | --- |
| Mục tiêu | Lưu/cung cấp lại cấu hình task graph giữa các lần build để tránh chạy configuration phase. | Cô lập trạng thái Project, cho phép cấu hình nhiều projects an toàn và song song hơn. |
| Vi phạm phổ biến | Task action bắt `Project`/`Gradle`/`Settings` hoặc live mutable state; build listeners không phù hợp. | Project A cấu hình/đọc mutable state của Project B, ví dụ root `allprojects`/`subprojects` injection. |
| Cấu hình xuyên project | **Không tự kết luận mọi block này luôn bị từ chối bởi Configuration Cache thông thường.** Cần test build logic thực tế. | Root injection vào child projects là **không tương thích** với yêu cầu cô lập project. |
| Cách sửa ưu tiên | Lazy Providers/Properties, task inputs/outputs, tránh giữ Project khi execute. | Convention plugins apply tại mỗi target project; state-isolating lifecycle callbacks cho trường hợp đặc biệt. |

Tài liệu Gradle về **Isolated Projects** nêu rõ block root `allprojects { ... }` hoặc `subprojects { ... }` cấu hình các subprojects không hợp lệ theo mô hình này. Thay bằng convention plugin giải quyết vấn đề do **mỗi project tự apply plugin lên chính nó**.

**Đừng khẳng định “bật --configuration-cache là mọi allprojects đều lỗi”**: kiểm tra thực tế bằng command và error report. Tuy nhiên, ngay cả khi configuration cache vẫn hoạt động, root injection còn có nhược điểm về coupling và khả năng mở rộng.

### 9.1. Kiểm thử Configuration Cache

Trong lab:

```bash
./gradlew :app:run --configuration-cache --quiet
./gradlew :app:run --configuration-cache --quiet
```

Cả hai lần chương trình in `Hello, Gradle!` nếu Gradle/task plugins hỗ trợ Configuration Cache. Lần đầu Gradle có thể tính/lưu cache, lần sau có thể reuse nếu các inputs không đổi. Kết quả cache hit không phải một “bảo đảm tuyệt đối” cho mọi môi trường hoặc Gradle version.

Nếu có error/warnings, đọc report của Gradle; không “sửa” bằng cách đặt warning mode một cách mù quáng hoặc tắt các safeguards khi CI cần dùng Configuration Cache.

### 9.2. Isolated Projects đòi cách tổ chức khác

Đây là **mô tả kiến trúc**, không khuyên bạn bật chế độ đó cho lab cross-project và mặc định mong PASS. Tài liệu Gradle chỉ ra:

- Root `allprojects` / `subprojects` cấu hình child project gây vi phạm cô lập.
- Giải pháp mặc định: **đóng gói logic thành project convention plugin**, apply plugin từ chính build.gradle của module.
- Một số trường hợp settings-level injection có thể dùng `gradle.lifecycle.beforeProject` **state-isolating callback** thay cho root config, nhưng cần hiểu plugin resolution/classpath và hành vi cụ thể của Gradle version.
- Isolated Projects đang có các giới hạn triển khai riêng; không tự suy luận rằng mọi plugin bên thứ ba đã hỗ trợ.

Vì vậy migration sang convention plugins là **quyết định thiết kế lâu dài**, không chỉ workaround khi một flag mới xuất hiện.

## 10. Giới hạn thứ tư: repositories và dependency management

### 10.1. Project repositories không phải plugin repositories

Root injection truyền thống:

```groovy
subprojects {
    repositories {
        mavenCentral()
    }
}
```

thêm **repository cho dependencies của subprojects**. Nó **không** thay thế `pluginManagement.repositories` dùng cho `plugins { }`, không đổi repositories của included build và không tự thêm Maven Central cho root.

Nếu tổ chức muốn mọi module dùng cùng danh sách repository **và cấm thêm repository cục bộ**, Gradle hỗ trợ **settings-level** `dependencyResolutionManagement`.

Phương án **thay thế phần repository injection ở root**:

```groovy
// settings.gradle
dependencyResolutionManagement {
    repositoriesMode.set(
        org.gradle.api.initialization.resolve.RepositoriesMode.FAIL_ON_PROJECT_REPOS
    )
    repositories {
        mavenCentral()
    }
}
```

Ở đây đoạn code được chèn vào `settings.gradle` (giữ các lệnh `include` và `rootProject.name` đã có), đồng thời **xóa** `repositories { mavenCentral() }` ra khỏi root `subprojects` block. Nếu giữ cả hai, chế độ `FAIL_ON_PROJECT_REPOS` sẽ báo lỗi khi project/plugin thêm repository, đúng mục tiêu enforcement.

Các lựa chọn khác của `RepositoriesMode` có hành vi ưu tiên settings hoặc project repositories; hãy chọn theo policy thay vì mặc định ép mọi build giống nhau. **Đừng coi `dependencyResolutionManagement` là cơ chế tự phân phối toàn bộ `implementation` dependencies**: nó chỉ cung cấp nơi tìm, không tự khai báo thư viện nào cần dùng.

### 10.2. Không inject implementation vào mọi project

Phản ví dụ:

```groovy
// PHẢN VÍ DỤ: không phải module nào cũng cần cùng library.
subprojects {
    dependencies {
        implementation 'com.google.guava:guava:33.3.1-jre'
    }
}
```

Có ít nhất hai vấn đề:

1. Configuration `implementation` **chỉ tồn tại khi plugin phù hợp** tạo nó; docs-only hoặc Java-platform module có thể không có.
2. Cả khi cấu hình tồn tại, ép dependency vào mọi module làm classpath phình to, che giấu module nào thực sự sử dụng library và tăng mức phụ thuộc.

Tốt hơn:

- Các dependencies cần theo **loại module** nằm trong convention plugin tương ứng (ví dụ `java-library-conventions`, `application-conventions`).
- Dependencies đặc thù khai báo ngay trong `app/build.gradle`/`core/build.gradle`.
- Versions thống nhất bằng **version catalog** hoặc dependency constraints/platform/BOM; việc quản lý version **không bắt buộc** phải inject dependency vào tất cả projects.

## 11. Giới hạn thứ năm: sửa cấu hình project không phải cách điều khiển task graph

Có người cố tạo một task root để “build hết mọi subprojects” bằng cách mò tasks ở configuration phase, hoặc chạy task khác bên trong `doLast`. Điều đó khó đúng khi build có nhiều modules.

Tránh:

```groovy
// PHẢN VÍ DỤ: gọi task/Gradle build bằng tay trong task action.
tasks.register('runEverything') {
    doLast {
        // Không invoke Gradle task graph bằng cách gọi action của task khác.
    }
}
```

Hãy dùng **declared dependencies/lifecycle tasks**. Ví dụ khi cần tập hợp build cho các module Java, Gradle task selector từ root:

```bash
./gradlew build --console=plain
```

thường sẽ chọn `build` ở các projects có task phù hợp trong phạm vi selector. Hoặc chạy cụ thể:

```bash
./gradlew :core:build :app:build --console=plain
```

Nếu cần một root aggregate task mang tên riêng, có thể khai báo dependency bằng **task paths** ở root:

```groovy
tasks.register('assembleProduct') {
    group = 'build'
    description = 'Builds core and app artifacts.'
    dependsOn ':core:assemble', ':app:assemble'
}
```

Đoạn này là **một mở rộng** cho lab, không phải nguồn cấu hình dùng chung. Nó tạo dependency rõ trên tasks, không yêu cầu root trực tiếp đọc/modifying mutable subproject tasks. Khi run `:assembleProduct`, Gradle thực hiện các task cần thiết theo graph, không vì subprojects nằm trong một vòng for.

**Lưu ý:** `dependsOn` không bảo đảm một thứ tự ngang hàng cố định giữa core và app nếu không có graph dependency. Trong lab, `:app` đã khai báo `implementation project(':core')`, nên các artifacts cần dùng từ core được wire đúng.

## 12. Giải pháp hiện đại: convention plugin thay vì root injection

Với một nhóm nhiều Java modules, tạo **convention plugin** để mỗi project **chủ động áp dụng** các quy tắc chung. Gradle tài liệu chính thức khuyến nghị convention plugins thay vì `allprojects`/`subprojects` để tổ chức shared build logic.

Hai nơi phổ biến:

- `buildSrc/`: đơn giản, tự có trên classpath của build; thay đổi ở đây có thể ảnh hưởng nhiều project configurations.
- Một **included build** `build-logic/`: phù hợp cho multi-project build lớn, phân ranh giới build logic rõ hơn và có thể tách thành các plugins dùng lại.

Ví dụ tiếp theo là **một migration hoàn chỉnh** từ lab mục 5 sang `build-logic` sử dụng **precompiled Groovy script plugin**, không cần module Java library bên ngoài.

### 12.1. Cấu trúc sau migration

```text
sharing-config-lab/
├── settings.gradle
├── build.gradle                   (root: không còn injection)
├── gradlew
├── gradle/wrapper/...
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/
│       └── java-conventions.gradle
├── core/
│   ├── build.gradle
│   └── src/main/java/example/core/Greeting.java
└── app/
    ├── build.gradle
    └── src/main/java/example/app/Main.java
```

Giữ nguyên **hai file Java** ở mục 5.5 và 5.7. Sau migration, các build scripts phải được **thay đúng chỗ**, không chồng root injection cũ và convention plugin mới, nếu không bạn sẽ khó biết rule nào cuối cùng có hiệu lực.

### 12.2. Thay root settings.gradle

```groovy
pluginManagement {
    includeBuild('build-logic')
}

rootProject.name = 'sharing-config-lab'
include 'core', 'app'
```

`pluginManagement.includeBuild('build-logic')` làm các plugins do included build cung cấp khả dụng qua `plugins { id '...' }` trong subprojects. Nó **không** gộp `build-logic` thành subproject `:build-logic` và không khiến root `allprojects` tự cấu hình included build.

### 12.3. File build-logic/settings.gradle

```groovy
rootProject.name = 'build-logic'
```

### 12.4. File build-logic/build.gradle

```groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
```

`groovy-gradle-plugin` hỗ trợ **precompiled Groovy script plugins**. File `java-conventions.gradle` trong `src/main/groovy/` sẽ được compile thành plugin có ID **`java-conventions`**. Với core Gradle plugins, không cần dependency plugin riêng trong build-logic.

Nếu convention cần một **third-party plugin**, hãy đưa plugin artifact vào dependencies của `build-logic` và áp dụng nó trong precompiled plugin theo hướng dẫn Gradle; đừng chỉ ném một versioned `plugins { id ... version ... }` vào precompiled script.

### 12.5. File build-logic/src/main/groovy/java-conventions.gradle

```groovy
plugins {
    id 'java'
}

group = 'org.example.school'
version = '1.0.0'

repositories {
    mavenCentral()
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Đây là **nội dung đầy đủ** của precompiled convention plugin cho lab:

- Nó apply **Java plugin** vào project nào **chủ động apply `java-conventions`**.
- Nó đặt group/version trên project đó.
- Nó thêm Maven Central cho project đó, không đụng root và không sửa config của project khác.
- Nó đặt Java release cho JavaCompile tasks của project đó qua lazy `configureEach`.
- Không dùng `rootProject { }`, `subprojects { }`, đọc `project(':core')` hoặc các callbacks xuyên project.

Nếu sau này dùng `dependencyResolutionManagement { repositoriesMode = FAIL_ON_PROJECT_REPOS }` ở settings, **bỏ block `repositories { mavenCentral() }` trong convention plugin** và khai báo repository duy nhất tại settings. Đây là **hai lựa chọn quản lý repository khác nhau**, không được áp dụng cùng lúc trong strict mode.

### 12.6. Thay root build.gradle

Root build script không còn các block `allprojects`/`subprojects`. Có thể giữ trống (chỉ một dòng comment) hoặc chứa root-only lifecycle tasks. Ví dụ:

```groovy
// Root project intentionally has no cross-project configuration.
```

Root bây giờ không nhận `group/version` từ convention plugin. Nếu publishing root artifact thật sự cần các giá trị đó, cấu hình root riêng hoặc tạo một root-specific plugin. Không giả định việc thay injection giữ nguyên mọi metadata của root.

### 12.7. Thay core/build.gradle

```groovy
plugins {
    id 'java-library'
    id 'java-conventions'
}
```

`java-library` thêm library-specific behavior (ví dụ `api` dependency bucket), còn `java-conventions` áp dụng Java conventions chung. Áp `java` qua convention trong khi `java-library` đã apply Java không tạo hai Java compilers; Gradle plugin application idempotent.

### 12.8. Thay app/build.gradle

```groovy
plugins {
    id 'application'
    id 'java-conventions'
}

dependencies {
    implementation project(':core')
}

application {
    mainClass = 'example.app.Main'
}
```

App vẫn giữ project dependency và entry point của chính nó, trong khi shared Java release/repo/coordinates đến từ convention plugin. Mỗi module chỉ apply plugin mình cần. Nếu thêm module `:docs` không có Java, chỉ cần **không apply `java-conventions`** là module không bị “Java hóa”.

### 12.9. Run và xác minh output sau migration

```bash
./gradlew :app:run --quiet
./gradlew :app:run --args="Team" --quiet
./gradlew :core:compileJava --console=plain
./gradlew :app:build --console=plain
```

Kết quả của hai lệnh `:app:run` vẫn lần lượt là:

```text
Hello, Gradle!
Hello, Team!
```

Với cấu hình đúng, behavior ứng dụng không đổi, nhưng build logic bây giờ được **apply ở từng module**. Việc cần QA thêm khi migration: group/version của project, repository policy, các task flags và compatibility trên CI. Không tuyên bố mọi migration giữ nguyên behavior nếu cấu hình gốc từng dựa vào thứ tự hoặc root-specific settings.

## 13. Khi nào vẫn dùng allprojects/subprojects?

Không phải mọi `allprojects`/`subprojects` trong một build cũ đều cần xóa ngay lập tức. Chúng có ích khi:

- Đọc/duy trì legacy multi-project build trước khi có kế hoạch migration.
- Thử nghiệm nhanh một thay đổi tạm thời trong một build nhỏ, hiểu rõ phạm vi và không có yêu cầu Isolated Projects.
- Có vài immutable coordinates/defaults đơn giản với một owner rõ ràng; chi phí tạo plugin có thể tạm vượt lợi ích.

Nhưng hãy cân nhắc migrate khi:

- Có nhiều loại module (Java library, application, platform, Android, Kotlin, docs...).
- Các block bắt đầu chứa `project.name` conditionals, `afterEvaluate`, tasks cross-lookup hoặc dependencies theo module.
- Một module không thể đọc build script của chính nó mà hiểu nó dùng những plugins/compilers gì.
- Muốn build logic reusable/versioned/testable.
- Cần Isolated Projects hoặc muốn tối ưu cấu hình nhiều projects.
- Repositories/security policy yêu cầu settings-level enforcement.
- IDE/CI thường xuyên gặp lỗi plugin order hoặc invalid task/extension.

**Nguyên tắc thực dụng:** shared default ngắn và rõ có thể là bước khởi đầu; logic lâu dài nên trở thành plugin áp dụng rõ ràng. Tránh “micro-plugin cho mọi một dòng” chỉ vì hình thức, nhưng cũng đừng để root trở thành một build script hàng nghìn dòng điều khiển ngầm mọi module.

## 14. Bảng so sánh các lựa chọn

| Tiêu chí | `allprojects` | `subprojects` | Convention plugin |
| --- | --- | --- | --- |
| Root nhận cấu hình? | Có, nếu gọi từ root. | Không, nếu gọi từ root. | Chỉ nếu root tự apply. |
| Chọn module nhận logic? | Mọi project trong phạm vi. | Mọi descendants trong phạm vi. | Những project apply plugin. |
| Dễ dùng lúc bắt đầu? | Rất dễ. | Rất dễ. | Cần thiết lập build-logic/buildSrc trước. |
| Tách rõ trách nhiệm? | Thấp khi có nhiều rules. | Thấp khi có nhiều rules. | Cao; tên plugin thể hiện capability. |
| Hỗ trợ nhiều loại module? | Phải tự viết conditions. | Phải tự viết conditions. | Có thể tách Java/application/publishing conventions. |
| Coupling giữa Project models? | Có khi root inject child. | Có khi root inject child. | Không bắt buộc; plugin tự cấu hình target project. |
| Isolated Projects | Root injection vào child không tương thích. | Root injection vào child không tương thích. | Cách tiếp cận được Gradle khuyến nghị. |
| Reuse giữa builds | Root script khó chuyển nguyên xi. | Root script khó chuyển nguyên xi. | Có thể đưa plugin vào included build và dùng lại. |
| Kiểm thử build logic | Khó cô lập. | Khó cô lập. | Có thể test/version logic như plugin. |
| Rủi ro plugin-order | Dễ gặp nếu truy cập extension sớm. | Dễ gặp nếu truy cập extension sớm. | Thường rõ hơn khi plugin tự apply dependencies. |

## 15. Troubleshooting: lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xác minh và sửa |
| --- | --- | --- |
| Root có `:jar` không mong muốn | Đặt `apply plugin: 'java'` trong `allprojects`. | Cấu hình Java ở subprojects thích hợp; root không cần Java thì không apply. |
| `Could not find method java()` | `java` extension chưa được tạo hoặc module không có Java plugin. | Đảm bảo plugin apply; dùng `plugins.withId('java')` hoặc convention plugin. |
| `Could not find method implementation()` | Dependency bucket chưa được plugin tạo hoặc module khác loại. | Đừng inject vào mọi module; khai báo đúng scope sau plugin apply. |
| Task `compileJava` không tồn tại | Module không apply Java plugin. | Kiểm tra `:module:tasks`; đừng tạo assumption ở root. |
| `allprojects` làm docs module có Java tasks | Apply Java plugin quá rộng. | Chuyển sang opt-in convention plugin. |
| Module mới không nhận cấu hình | Chưa `include` trong settings, hoặc nằm ở included build riêng. | Đọc `./gradlew projects` và build boundary. |
| `:app` import class `Greeting` bị lỗi | Thiếu `implementation project(':core')` hoặc file/package sai. | Kiểm tra `app/build.gradle`, source layout, `:core:compileJava`. |
| `--release 17 not supported` | Compiler quá cũ. | Dùng JDK đủ mới hoặc cấu hình toolchain/resolver hợp lệ. |
| `repositoriesMode FAIL_ON_PROJECT_REPOS` fail | Root/subproject/convention plugin còn thêm project repository. | Chuyển repo thành settings-level và bỏ injection. |
| Build fail với `--configuration-cache` | Task action giữ live Project, listeners hoặc plugins chưa hỗ trợ. | Xem report, sửa đúng incompatibility; đừng khẳng định chỉ do `allprojects`. |
| Isolated Projects báo coupling | Root chạm state child qua `subprojects`/`allprojects`. | Dùng convention plugins hoặc state-isolating callbacks được hỗ trợ. |
| `java-conventions` plugin not found | Chưa `pluginManagement.includeBuild('build-logic')`, sai file path/ID, build-logic plugin chưa compile. | Kiểm tra cấu trúc mục 12, plugin ID từ filename, xem settings. |
| `groovy-gradle-plugin` không tạo plugin | Đặt file sai `src/main/groovy` hoặc build-logic chưa là included plugin build. | Đặt đúng file và plugin block, chạy lại Gradle. |
| App `run` được nhưng build fail ở JDK | Java release/toolchain khác nhau giữa modules. | Xem plugin convention, `options.release`, toolchain và actual compiler. |
| Root group/version khác trước sau migration | Trước đó allprojects đặt root metadata; convention chỉ apply ở children. | Đặt metadata root riêng nếu có nhiệm vụ cần. |
| Gradle configure mọi module chậm | Root cross config/afterEvaluate/eager task realization và plugins nặng. | Đo profile/build scan; migrate logic, dùng `configureEach`, Providers. |
| Included build không nhận root repo/version | Included build có settings/projects riêng. | Cấu hình included build hoặc apply conventions ở đúng boundary. |
| Version trùng nhưng dependency khác | Shared group/version không tự quản lý dependency graph. | Dùng version catalogs, platform/BOM, constraints; khai báo dependencies cụ thể. |

### 15.1. Lệnh debug có mục đích

```bash
./gradlew projects --console=plain
./gradlew :core:tasks --all --console=plain
./gradlew :app:tasks --all --console=plain
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:run --info --console=plain
./gradlew :app:run --configuration-cache --quiet
```

- `projects` xác định modules thực sự được include.
- `:module:tasks` xác nhận plugin đã tạo task nào; không suy luận từ tên folder.
- `dependencies` xem project dependency `:core` trong graph app.
- `--info` giúp điều tra Java compiler/runtime classpath và task graph khi build lỗi.
- `--configuration-cache` kiểm tra cấu hình thực tế; đọc report nếu có incompatibility.
- Không dùng `--offline` như một cách “kiểm thử isolation”; nó chỉ ảnh hưởng external resolution/caches.

## 16. Bài tập thực hành và đáp án

**Bài 1 — Phạm vi.** Lab có root, core, app. Root `allprojects { version='1.0.0' }` áp dụng cho bao nhiêu projects? **Ba**: root, core, app.

**Bài 2 — Loại trừ root.** Thay `allprojects` bằng `subprojects` cho `group/version`. Project nào không được đặt metadata bởi block mới? **Root**.

**Bài 3 — Java plugin.** Đặt `allprojects { apply plugin: 'java' }` và so sánh root `./gradlew :tasks`. Vì sao có root jar/compile tasks? **Vì Java plugin bị apply lên root**.

**Bài 4 — Java plugin timing.** Thêm module `:docs` không apply Java. Vì sao `subprojects { java { ... } }` dễ lỗi? **Vì Java extension không tồn tại ở module đó**. Sửa bằng plugin callback hoặc convention plugin chỉ apply trên modules Java.

**Bài 5 — CLI.** Chạy `./gradlew :app:run --args="Alice" --quiet`. Stdout? **Hello, Alice!**. Vì sao `:core:compileJava` có thể chạy trước app? **Declared project dependency**.

**Bài 6 — Build boundary.** `includeBuild('build-logic')` có khiến `subprojects` của root cấu hình plugin build? **Không**, included build có Project tree riêng.

**Bài 7 — Plugin DSL.** Vì sao `plugins { id 'java-library' }` của core nên nằm ở chính `core/build.gradle` thay vì root inject một plugin cho mọi module? **Vì capability của module rõ ràng và không tạo plugin ở docs/root**.

**Bài 8 — Cache vs isolation.** Một build có root `subprojects { ... }` chạy được với Configuration Cache. Kết luận nó tương thích Isolated Projects được không? **Không**; hai bộ constraints khác nhau, root injection vẫn là cross-project coupling.

**Bài 9 — Settings repositories.** Bật `RepositoriesMode.FAIL_ON_PROJECT_REPOS` nhưng root `subprojects` còn thêm `mavenCentral()`. Kết quả? **Fail vì project-level repository vi phạm mode**. Sửa bằng cách xóa injection và đặt repo ở settings.

**Bài 10 — Version catalog.** Vì sao shared `version='1.0.0'` không thay thế version catalog cho dependencies? **Project version và external dependency versions là các khái niệm khác nhau**.

**Bài 11 — Migration.** Áp dụng phần `build-logic`, giữ source Java, bỏ root injection. Chạy `:app:run`. Vì sao stdout không đổi? **Module logic và project dependency vẫn đúng; shared rule chỉ chuyển từ root sang plugin tự apply**.

**Bài 12 — Plugin opt-in.** Thêm `:docs` nhưng không apply `java-conventions`. Có JavaCompile tasks không? **Không, trừ khi docs tự apply plugin Java khác**.

**Bài 13 — Task dependencies.** So sánh `dependsOn ':core:assemble'` với `evaluationDependsOn(':core')`. Cái nào thể hiện công việc cần chạy để tạo artifact? **dependsOn**; evaluationDependsOn chỉ ràng buộc thứ tự cấu hình project.

**Bài 14 — Gradle 9+.** Vì sao nên ưu tiên `tasks.withType(JavaCompile).configureEach` thay vì loop qua `tasks.all` và xử lý ngay? **Lazy task configuration**, tránh realize task không cần thiết.

### Tự kiểm tra nhanh

1. `allprojects` từ root có gồm root? **Có.**
2. `subprojects` từ root có gồm root? **Không.**
3. `subprojects` có chỉ gồm con trực tiếp? **Không; bao gồm descendants trong hierarchy.**
4. `settings.gradle` làm gì? **Định nghĩa project structure bằng include.**
5. `allprojects` có tự tạo module? **Không.**
6. `allprojects` có tự apply Java plugin? **Không, chỉ chạy code được viết bên trong.**
7. `plugins.withId('java')` dùng làm gì? **Đợi plugin apply trước khi cấu hình.**
8. `configureEach` hữu ích thế nào? **Cấu hình lazily các tasks theo type.**
9. `implementation project(':core')` có phải cấu hình chéo root injection? **Không, là declared project dependency.**
10. `rootProject.group` có tự là `app.group` không? **Không phải cơ chế inherit tự động; trong lab allprojects đặt giá trị lên mỗi project.**
11. `includeBuild` có phải `include` không? **Không.**
12. Configuration Cache có đồng nghĩa Isolated Projects? **Không.**
13. Root `subprojects` injection có tương thích Isolated Projects không? **Không theo mô hình hiện hành.**
14. Convention plugin phải apply ở đâu? **Ở project muốn nhận logic.**
15. Convention plugin bằng Groovy có dùng `groovy-gradle-plugin` không? **Có.**
16. Plugin ID trong lab lấy từ file nào? **java-conventions.gradle**.
17. App dùng core bằng API Gradle nào? **implementation project(':core')**.
18. Root chỉ điều phối có cần Java plugin không? **Không.**
19. Settings-level repository strict mode có cho phép project-level repo không? **Không.**
20. Có cần xóa ngay mọi root cross config trong build cũ? **Cần đánh giá và migration có kiểm chứng, không sửa mù.**

## 17. Nguồn tài liệu chính thức

- **Gradle — Project DSL/API:** giải thích `allprojects`, `subprojects`, `childProjects`, `project()`: https://docs.gradle.org/current/dsl/org.gradle.api.Project.html
- **Gradle — Structuring Multi-Project Builds:** `include`, project paths, root/subprojects, task selectors và dependencies: https://docs.gradle.org/current/userguide/multi_project_builds_intermediate.html
- **Gradle — Multi-Project Builds:** bố trí root và modules, `settings.gradle` ownership: https://docs.gradle.org/current/userguide/multi_project_builds.html
- **Gradle — Configuration on Demand:** decoupled projects, cross-project configuration injection, parallelism: https://docs.gradle.org/current/userguide/configuration_on_demand.html
- **Gradle — Isolated Projects:** lý do root `allprojects`/`subprojects` không được dùng trong mode này, convention plugins và state-isolating lifecycle callbacks: https://docs.gradle.org/current/userguide/isolated_projects.html
- **Gradle — Configuration Cache:** task state isolation, serialization và requirement không giữ Project trong task action: https://docs.gradle.org/current/userguide/configuration_cache.html
- **Gradle — Convention Plugins:** Gradle khuyến nghị convention plugins hơn root injection; `buildSrc`/`build-logic`: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html
- **Gradle — Precompiled Script Plugins:** `groovy-gradle-plugin`, plugin ID từ file, plugin DSL/implementation: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html
- **Gradle — Sharing Build Logic Between Subprojects:** ví dụ chuyển lặp cấu hình sang reusable plugins: https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html
- **Gradle — Centralized Repositories:** `dependencyResolutionManagement` và repository mode: https://docs.gradle.org/current/userguide/centralizing_repositories.html
- **Gradle — Lazy Configuration:** `TaskProvider`, `configureEach` và cách tránh eager realization: https://docs.gradle.org/current/userguide/task_configuration_avoidance.html
- **Gradle — Application Plugin:** `application.mainClass` và `run` trong lab: https://docs.gradle.org/current/userguide/application_plugin.html

**Kết luận:** `allprojects { }` cấu hình **project hiện tại và toàn bộ descendants**; `subprojects { }` cấu hình **descendants nhưng không gồm project hiện tại**. Hai API đơn giản để học và duy trì build nhỏ, song cấu hình xuyên project tạo coupling, rủi ro plugin-order và không hợp với Isolated Projects. Khi shared logic tăng, hãy dùng **convention plugins** apply tại từng module; để settings quản lý **project structure/repositories**, để module khai báo **plugins/dependencies cụ thể**, và để Gradle task graph xử lý **dependency/thứ tự thực thi**. Migration tốt phải giữ behavior, kiểm tra group/version, Java release, dependencies và runtime output, thay vì chỉ chuyển các dòng code cho đẹp.