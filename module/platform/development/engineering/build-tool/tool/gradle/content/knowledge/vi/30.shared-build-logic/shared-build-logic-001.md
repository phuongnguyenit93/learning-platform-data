# Nhận diện cấu hình lặp và lựa chọn mức tái sử dụng phù hợp trong Gradle

Trong một dự án Java có nhiều module, bạn thường nhìn thấy các đoạn `build.gradle` hoặc `build.gradle.kts` na ná nhau: mọi thư viện đều chọn Java 17, dùng UTF-8, cấu hình `JavaCompile`, chạy JUnit 5, dùng chung plugin kiểm tra chất lượng và đặt một vài convention cho JAR. Khi dự án còn nhỏ, sao chép một đoạn cấu hình có thể giúp thử nghiệm nhanh. Khi số module tăng, cùng một quy tắc tồn tại ở năm hoặc mười nơi sẽ dễ bị **configuration drift**: sửa một chỗ nhưng bỏ sót chỗ khác, mỗi module dùng phiên bản/behavior không thống nhất.

Tuy nhiên, **không phải mọi dòng giống nhau đều cần được trừu tượng hóa**. Một ứng dụng `application`, một thư viện công khai `java-library` và một công cụ sinh mã có thể cần chính sách Java khác nhau. Nếu dồn tất cả vào một `subprojects {}` khổng lồ hoặc một plugin “everything”, việc thay đổi một quy tắc chung có thể vô tình ảnh hưởng hàng chục module.

Bài Knowledge này thuộc nhóm **Build logic dùng chung** trong **Build Tool Gradle**, với chủ đề **“Nhận diện cấu hình lặp và lựa chọn mức tái sử dụng phù hợp”**. Trọng tâm không phải chỉ biết viết một convention plugin, mà là **nhận diện đúng loại trùng lặp, chọn mức tái sử dụng tương xứng, kiểm chứng hiệu quả và giữ rõ ranh giới sở hữu**.

Bạn sẽ học:

1. Phân biệt **cấu hình giống cú pháp** với **quy tắc kỹ thuật thật sự dùng chung**.
2. Nhận diện lặp về toolchain, compiler, testing, repositories, plugin versions, dependencies, publications, generated tasks và CI.
3. Chọn giữa **không trừu tượng hóa**, cấu hình cục bộ, **version catalog**, `apply from`, `buildSrc`, **included build `build-logic`**, **precompiled convention plugin** và **binary plugin**.
4. Hiểu vì sao Gradle khuyên tránh lạm dụng **`allprojects {}` / `subprojects {}` / `afterEvaluate {}`** để cấu hình xuyên project.
5. Thực hiện một lab Java 17 đầy đủ: trích cấu hình chung từ hai module thư viện sang **Groovy precompiled convention plugin** trong included build, nhưng giữ riêng cấu hình ứng dụng.
6. So sánh với Kotlin DSL, hiểu Provider API, lazy configuration, configuration cache, isolated projects và các giới hạn của tái sử dụng.
7. Có checklist ra quyết định, migration và chẩn đoán khi một refactor build logic bị lỗi.

**Thông điệp chính:** tái sử dụng ở **đúng cấp của một policy** — không phải ở cấp “hai đoạn code trông giống nhau”. Một convention plugin có giá trị khi nó mô tả một **vai trò project** rõ ràng, được áp dụng tường minh và có thể kiểm thử độc lập.

## 1. Nhìn đúng vấn đề: lặp cú pháp hay lặp chính sách?

Giả sử hai thư viện Java đều có:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
```

Đây là dấu hiệu của **một policy Java chung**: library modules phải được biên dịch bằng Java 17, với source encoding UTF-8 và target API/bytecode Java 17. Nếu nhóm quyết định chuyển lên Java 21, có khả năng phải sửa **cả hai**. Từ đó có thể cân nhắc trích thành `company.java-library-conventions`.

Nhưng nếu hai module đều có:

```groovy
dependencies {
    implementation 'org.example:some-library:1.2.3'
}
```

thì cần hỏi: **cả hai module dùng cùng thư viện vì cùng một chức năng**, hay chỉ vô tình cần thư viện đó? Nếu thư viện là dependency sản phẩm thực sự, việc áp dụng nó bắt buộc lên mọi library module qua convention plugin có thể tạo coupling và làm artifact lớn không cần thiết. **Trùng một dependency declaration chưa đủ để kết luận nó phải là shared convention.**

### Ba dạng lặp cần phân biệt

| Dạng | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| **Lặp chính sách** | Nhiều module cùng buộc Java 17, encoding, test runner/quality gates | Convention plugin theo project role. |
| **Lặp dữ liệu phiên bản** | Cùng khai báo versions của JUnit/Guava/SLF4J ở nhiều nơi | Version catalog, BOM/platform hoặc dependency constraints theo mục tiêu. |
| **Lặp ngẫu nhiên** | Hai module có cùng vài dòng vì yêu cầu tạm thời nhưng có thể thay đổi độc lập | Giữ cấu hình cục bộ, tránh abstraction sớm. |

Một dạng thứ tư là **lặp quy trình**: nhiều module đều định nghĩa task chuyển file, generate code, ký artifact hoặc gọi tool ngoài. Nếu task có inputs/outputs/behavior phức tạp, convention plugin đơn thuần chưa chắc đủ; có thể cần **typed custom task + binary plugin** để bảo đảm correctness, cacheability và testability.

### Đừng đánh giá qua số dòng בלבד

Một đoạn ba dòng như `test { useJUnitPlatform() }` có thể là shared policy quan trọng hơn một block 60 dòng chỉ phục vụ riêng một loại module. Dấu hiệu quyết định là:

- **Cùng lý do thay đổi?**
- **Cùng owner/người phê duyệt?**
- **Cùng phạm vi project được áp dụng?**
- **Cùng vòng đời release?**
- **Một thay đổi phải được đồng bộ ở mọi nơi hay không?**

Đó là cách tránh trừu tượng hóa theo hình thức.

## 2. Kiểm kê các lớp cấu hình trước khi refactor

Một cuộc khảo sát build logic nên phân loại cấu hình theo chức năng, không chỉ tìm kiếm văn bản giống nhau.

| Loại cấu hình | Ví dụ | Điểm nên tái sử dụng |
| --- | --- | --- |
| **Gradle distribution** | Wrapper version | `gradle-wrapper.properties`, không copy `gradle` command vào từng module. |
| **Project graph** | `include ':core', ':app'` | `settings.gradle(.kts)`, không phải convention plugin trên mỗi Project. |
| **Plugin resolution** | Repositories/plugin IDs | `pluginManagement {}`, plugin aliases hoặc plugin management policy. |
| **External repositories** | Maven Central/corporate mirror | `dependencyResolutionManagement {}` trong settings, theo repository mode. |
| **Dependency versions** | JUnit 5, Jackson, Guava | Version catalog, BOM hoặc platform/constraints. |
| **Compiler/build policy** | Java 17 toolchain, UTF-8, `--release` | Convention plugin, phân loại thư viện/ứng dụng. |
| **Testing policy** | JUnit Platform, test logging, JVM args | Convention plugin theo test suite/project role. |
| **Quality policy** | Checkstyle, Spotless, Jacoco | Convention plugin hoặc plugin chuyên dụng, áp dụng có chọn lọc. |
| **Packaging policy** | Jar manifest, archives reproducible | Convention plugin cho modules đóng gói tương ứng. |
| **Module-specific deps** | JDBC driver, HTTP client cho một module | Giữ trong build script của module. |
| **Custom task logic** | Sinh source/resource, kiểm tra schema | Typed task; plugin nếu cần dùng ở nhiều module. |
| **Organization-wide behavior** | Plugin nội bộ dùng nhiều repository | Binary/published plugin với versioning và tests. |

**Lưu ý:** Version catalog giúp **chuẩn hóa tên và version declaration** nhưng **không ép mọi module sử dụng dependency** hoặc tự áp dụng `JavaCompile` options. Ngược lại, convention plugin có thể **áp dụng behavior** cho module dùng nó, chứ không chỉ khai báo data. Hai công cụ không thay thế nhau.

## 3. Bộ câu hỏi nhận diện “lặp thật”

Trước khi tạo shared build logic, trả lời:

1. **Lặp ở bao nhiêu module?** Hai là dấu hiệu, không phải ngưỡng tuyệt đối. Một policy sắp áp dụng cho mười module cũng đáng trích sớm.
2. **Có chung semantic contract không?** “Mọi Java library biên dịch theo Java 17” rõ hơn “mọi thư mục tên bắt đầu bằng `api`”.
3. **Thay đổi có phải đi đồng thời?** Nếu một module cần Java 21 còn module kia phải Java 17, cùng cú pháp hôm nay chưa chắc shared policy.
4. **Phạm vi áp dụng là gì?** Toàn build, thư viện, ứng dụng, generated tool, publishable artifact hay chỉ một feature?
5. **Có sở hữu rõ không?** Team build platform có quyền thay quy tắc chung, còn module owners chịu trách nhiệm deps riêng?
6. **Cấu hình có phụ thuộc loại plugin khác không?** Ví dụ `test` task chỉ hiện diện khi Java plugin được áp dụng; convention phải quản lý plugin relationship.
7. **Cần tùy biến gì?** Một policy có 1–2 tham số hợp lý hay sẽ phát triển thành 30 flags khó hiểu?
8. **Có tác dụng phụ khi áp dụng không?** Tự thêm dependencies, mở network, tạo tasks, thay archives?
9. **Có thể test độc lập không?** Dùng Gradle TestKit hoặc một fixture project để xác minh plugin.
10. **Phạm vi sử dụng ra ngoài một build không?** Nếu nhiều repositories, cần versioning/publishing rõ.
11. **Có ảnh hưởng performance không?** Eager task creation, cross-project configuration hoặc classpath invalidation?
12. **Cấu hình có dùng Provider và tương thích configuration cache không?**
13. **Có khác nhau giữa CI và IDE không?** Một abstraction chỉ chạy trên một máy không phải giải pháp.
14. **Cần metadata phụ trợ nào?** Repository policy nên ở settings, không giấu vào một convention không có đúng lifecycle scope.
15. **Nếu policy thay đổi, ai review migration?** Một dòng dùng chung có blast radius lớn hơn một dòng local.

Câu hỏi quan trọng nhất là **“nếu một rule đổi, mọi nơi có phải đổi theo không?”**. Câu trả lời *có* gợi ý một abstraction chung; *không* gợi ý local configuration hoặc chia thành các capability nhỏ.

## 4. Bảng quyết định: chọn mức tái sử dụng nào?

| Tình huống | Lựa chọn thường phù hợp | Vì sao | Điều không nên làm |
| --- | --- | --- | --- |
| Một module có cờ biên dịch riêng | Giữ ở `module/build.gradle` | Chính sách cục bộ, ownership rõ | Tạo plugin chỉ vì một dòng. |
| Hai đoạn gần giống nhưng khác lifecycle | Giữ riêng hoặc helper nhỏ | Tránh coupling giả | Ép dùng chung một plugin lớn. |
| Cùng library version dùng ở nhiều modules | `libs.versions.toml` version catalog | Một tên/version declaration | Thêm dependency ấy tự động vào mọi module. |
| Nhiều libraries cần cùng BOM/constraints | Java platform/BOM, dependency constraints | Điều phối dependency graph | Dùng convention plugin thay cho semantics của platform. |
| Một số modules dùng cùng compilation/test policy | **Precompiled convention plugin** | Behavior tái sử dụng, áp dụng tường minh | `subprojects {}` áp vào tất cả. |
| Hai build scripts cũ dùng một đoạn tạm | Applied script `apply from` (có điều kiện) | Migration nhẹ, ít setup | Xem đây là kiến trúc dài hạn cho hệ thống lớn. |
| Build mới có vài convention thử nghiệm | `buildSrc` có thể đủ | Setup nhanh, script/plugin classpath tự nhận | Bỏ qua invalidation/classloader tradeoffs. |
| Monorepo nhiều modules/team | Included `build-logic` + convention plugins | Ranh giới build logic rõ, dễ kiểm thử | Cấu hình mọi child từ root bằng `allprojects`. |
| Plugin có task type/extension phức tạp | **Binary plugin** + typed tasks | API mạnh, testing/publishing tốt | Giấu mọi logic vào các closure dài. |
| Nhiều repositories dùng một policy | Published versioned plugin / platform | Versioning, compatibility, governance | Copy file script theo thủ công. |
| Repositories/plugin resolution cấp settings | `settings.gradle(.kts)` / Settings plugin | Đúng lifecycle và scope | Áp dụng `Project` plugin rồi mong đổi được settings đã chạy. |

Đừng đọc bảng như một thang “càng nâng cấp càng tốt”. **Mức abstraction đúng** là nơi code ít hơn **và** người đọc vẫn hiểu điều gì xảy ra ở module; không phải mức có nhiều lớp nhất.

## 5. Các dấu hiệu cấu hình lặp có thể đo được

Khi review multi-project Gradle repo, quan sát:

- Nhiều `build.gradle(.kts)` có cùng `java { toolchain { ... } }`.
- Cùng `tasks.withType(JavaCompile).configureEach` lặp lại.
- Cùng cấu hình `Test.useJUnitPlatform()` và test logging được copy nhiều lần.
- Versions của một dependency/plugin bị chép nhiều nơi và không cùng value.
- Có nhiều `plugins { id 'checkstyle' }` đi kèm cùng file rules và task wiring.
- Một module có test coverage threshold, module khác quên.
- Lệnh `tasks.register('generateSomething', Exec)` ở nhiều module khác tên nhưng cùng behavior/argument contract.
- Nhiều scripts dùng `System.getenv`, `new File` và build time ngay lúc configuration thay cho Gradle Provider APIs.
- Root `subprojects {}` rẽ nhánh theo `project.name` để áp dụng từng rule.
- Nhiều modules phải sửa đồng thời mỗi khi thay Java version/JUnit/quality policy.

### Nhưng không phải cái nào cũng cần plugin

Ví dụ có hai module đều dùng:

```groovy
dependencies {
    implementation 'com.example:request-model:1.0.0'
}
```

Nếu đó là **module-specific business dependency**, nên để module tự công bố dependency và chỉ đưa alias/version vào catalog. Một convention plugin cần mô tả **build behavior**, không nên biến mọi project thành “import toàn bộ thư viện của công ty”.

Một dấu hiệu xấu là convention plugin tên **`common`** áp dụng 20 plugins và 30 dependencies nhưng không ai nói được “common của vai trò nào”. Tên có nghĩa như `acme.java-library-conventions`, `acme.java-application-conventions`, `acme.integration-tests` và `acme.publishing` tốt hơn vì ranh giới rõ.

## 6. Điểm khởi đầu: local build scripts không phải luôn sai

Khi mới có một module:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
```

Đây là cấu hình rõ và dễ đọc. Tạo một `build-logic` included build, plugin DSL, TestKit và release process chỉ vì **một module** có thể khiến onboarding khó hơn.

Nên **giữ local** khi:

- Điều kiện kỹ thuật là ngoại lệ thật.
- Thử nghiệm cần thay nhanh và chưa hình thành policy.
- Một module dùng Java version khác với phần còn lại.
- Có rất ít dòng và người sửa không phải chạm nhiều nơi.
- Logic thật sự không có consumer thứ hai.
- Sự khác biệt giữa modules có khả năng lớn hơn sự tương đồng.

Có thể trích **hàm/helper cục bộ** khi nhiều task trong **chính một project** dùng cùng cách tính đường dẫn hoặc format string; vẫn phải dùng Gradle Provider/File APIs phù hợp và khai báo inputs/outputs. Đừng vội đưa một helper local ra plugin chung khi nó không có consumer khác.

## 7. Version catalog: chia sẻ tọa độ và versions, không tự áp dụng behavior

Ví dụ `gradle/libs.versions.toml`:

```toml
[versions]
junit = "5.10.2"
guava = "33.2.1-jre"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
junit-launcher = { module = "org.junit.platform:junit-platform-launcher", version = "1.10.2" }
guava = { module = "com.google.guava:guava", version.ref = "guava" }

[plugins]
spotless = { id = "com.diffplug.spotless", version = "6.25.0" }
```

Đây là **snippet minh họa alias/version**, không thuộc lab Java không phụ thuộc thư viện ngoài ở phần dưới. Versions được pin để giải thích cú pháp; trước khi dùng thật phải kiểm tra compatibility và policy cập nhật/security của tổ chức.

Trong Groovy module script:

```groovy
dependencies {
    testImplementation libs.junit.jupiter
    testRuntimeOnly libs.junit.launcher
}
```

Trong Kotlin DSL:

```kotlin
dependencies {
    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.launcher)
}
```

Version catalog:

- Giúp **tham chiếu cùng một module/version** qua alias ổn định.
- Có thể chứa aliases cho plugins.
- **Không tự động inject** dependency vào mọi project.
- **Không tự áp dụng** `useJUnitPlatform()`, Java toolchain hay code quality tasks.
- Không phải cơ chế **ép selected version tuyệt đối** khi Gradle gặp conflict; muốn dependency governance chặt có thể cần platforms, locking/constraints/verification.
- Không bảo đảm catalog của root build tự hiển thị trong `build-logic` included build: đó là build độc lập, có settings/catalog scope riêng.

Nếu vấn đề thực chất chỉ là **cùng version được chép ở mười nơi**, version catalog có thể đủ; nếu cùng với version còn có behavior `useJUnitPlatform()` phải luôn bật, hãy cân nhắc **catalog + convention plugin** hoặc một policy được tổ chức phù hợp.

## 8. Applied script: phương án nhẹ nhưng có giới hạn

Một cách tái sử dụng lâu đời:

```groovy
// gradle/java-compile.gradle
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
```

Các module Groovy DSL có Java plugin:

```groovy
plugins {
    id 'java-library'
}

apply from: rootProject.file('gradle/java-compile.gradle')
```

**Đây là snippet minh họa**; file `gradle/java-compile.gradle` phải tồn tại và module đã có `JavaCompile` tasks. `apply from` cho phép chia sẻ cấu hình nhanh mà chưa cần plugin build.

Ưu điểm:

- Ít file setup, dễ chuyển từ copy/paste trong dự án legacy.
- Dùng được khi có vài scripts đơn giản và chưa kịp migrate.
- Có thể làm bước chuyển tạm thời.

Nhược điểm:

- Applied script không có cùng trải nghiệm **plugin ID/capability/typed API** như precompiled/binary plugin.
- Khó quản lý và test hơn khi script lớn, nhiều implicit assumptions.
- Plugin DSL, lifecycle, accessors và IDE support có giới hạn so với convention plugin.
- Các consumer có thể cần hiểu thứ tự áp dụng plugins và script.
- Dễ biến thành một file khổng lồ với logic phụ thuộc mọi project names.

Gradle docs hiện đại ưu tiên **convention plugins** cho shared build behavior, nhất là khi repo lớn. **Đừng viết lại một plugin phức tạp thành applied script** chỉ vì muốn tránh tạo `build-logic`.

## 9. Vì sao `allprojects {}` và `subprojects {}` thường không phải lời giải tốt?

Một mẫu legacy hay gặp ở root:

```groovy
subprojects {
    apply plugin: 'java-library'

    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
        options.release = 17
    }
}
```

Đoạn này có thể hoạt động trong nhiều Gradle versions, nhưng có nhược điểm:

1. **Cấu hình xuyên project:** root Project tác động trực tiếp lên child Project.
2. **Implicit behavior:** mở `api/build.gradle` chưa thấy ngay nó đã được apply Java plugin từ root.
3. **Áp dụng sai vai trò:** ứng dụng hoặc project chỉ để packaging có thể bị áp `java-library` không cần.
4. **Thứ tự cấu hình:** thay tên/di chuyển project hoặc thêm plugin có thể làm assumptions về evaluation order sai.
5. **Performance:** cross-project configuration có thể hạn chế khả năng caching/parallelization/isolated projects.
6. **Debugging:** lỗi task/plugin xuất hiện ở child nhưng nguyên nhân nằm trong root block cách xa.
7. **Ownership:** một thay đổi root có blast radius lớn, khó review theo scope module.

Gradle khuyên dùng convention plugins để mô tả behavior và **được áp dụng tường minh trong project cần nó**. Điều đó tạo project isolation tốt hơn và làm build scripts dễ hiểu hơn.

### Tại sao `afterEvaluate {}` không nên là công cụ mặc định?

```groovy
subprojects {
    afterEvaluate {
        // tùy điều kiện project/plugin đã xuất hiện...
    }
}
```

Đây là anti-pattern minh họa: deferred mutation của project configuration dựa vào thời điểm evaluation. Nó làm reasoning và configuration cache khó hơn, đặc biệt khi một plugin chờ sự kiện của plugin khác.

Thay bằng:

- `plugins { id 'acme.java-library-conventions' }` trong modules phù hợp.
- `pluginManager.withPlugin('java') { ... }` khi plugin cần phản ứng lúc Java plugin được áp dụng.
- `tasks.withType(JavaCompile).configureEach { ... }` để cấu hình task một cách lazy.
- **Gradle Property/Provider API** cho values được tính trì hoãn và khai báo input.
- Convention plugin composition để tách capabilities theo vai trò.

Không có nghĩa mọi `subprojects {}` hiện hữu đều phải xóa ngay lập tức; khi migrate, cần biết nó cấu hình những modules nào và xác minh không làm mất policy. Nhưng **đừng chọn root cross-project blocks làm kiến trúc mặc định cho build logic mới**.

## 10. `buildSrc` hay included build `build-logic`?

Gradle có hai cách phổ biến để đặt reusable logic trong repository.

| Tiêu chí | `buildSrc` | Included build `build-logic` |
| --- | --- | --- |
| Cách tham gia main build | Gradle tự nhận diện tại root | Root settings khai báo `includeBuild('build-logic')` hoặc trong `pluginManagement`. |
| Có settings/build scripts riêng? | Là một build đặc biệt; có thể có file config riêng | Là independent Gradle build rõ ràng. |
| Build logic trên classpath | BuildSrc outputs tự được thêm cho main build scripts | Plugin/artifact được resolve qua included build. |
| Khởi đầu | Thuận tiện cho prototype | Thêm ít setup, ranh giới rõ. |
| Invalidation | Thay `buildSrc` có thể ảnh hưởng phần lớn main build classpath/configuration | Isolation theo từng logic project/plugin có cơ hội giảm invalidation. |
| Reuse ngoài repository | Khó hơn nếu chỉ là buildSrc implicit | Dễ chuyển sang publish plugin/artifact hơn. |
| Khuyến nghị cho monorepo lớn | Không phải ưu tiên mặc định | **Gradle hiện khuyên dùng trong đa số trường hợp.** |

**Lưu ý quan trọng:** không nên coi `buildSrc` là “deprecated” hoặc “không chạy trên Gradle 9”. Nó vẫn là tính năng được hỗ trợ và hữu ích khi prototype nhỏ. Lý do thường chọn `build-logic` là khả năng modularization, testability, boundary rõ và performance ở repo lớn, không phải vì `buildSrc` sai cú pháp.

Một caveat khi số lượng convention plugins quá nhiều: mỗi tổ hợp plugin khác nhau có thể dẫn tới **script classpath** khác nhau, phát sinh chi phí hoặc các vấn đề Build Services; vì vậy không nên tạo hàng trăm plugins nhỏ tùy tiện. Chọn kích thước capability sao cho ứng dụng của chúng rõ và không sinh quá nhiều combination không cần thiết.

### Included build có catalog/repositories độc lập

Nếu root có `gradle/libs.versions.toml`, `build-logic` không mặc nhiên có mọi alias `libs` như main build. Khi cần reuse, phải khai báo catalog ở **build-logic/settings.gradle(.kts)** hoặc quản lý versions khác một cách tường minh. Plugin dependencies ngoài cũng cần repositories/classpath của **build-logic**, không chỉ repositories của root project.

## 11. Convention plugin: reuse hành vi theo project role

**Convention plugin** là plugin chứa conventions do nhóm tự chọn. Nó có thể:

- Apply core/community plugins.
- Thiết lập default Java toolchain, compiler/test/packaging behavior.
- Cấu hình tasks theo type hoặc theo tên qua lazy APIs.
- Định nghĩa extension/typed input để project consumers điều chỉnh có kiểm soát.
- Tổ chức dependencies chung **nếu đó là policy thật**.
- Áp dụng một convention plugin khác để ghép các capabilities.

Ví dụ tên theo vai trò:

```text
acme.java-library-conventions
acme.java-application-conventions
acme.integration-tests
acme.quality-gates
acme.publishing
```

Một module có thể dùng:

```groovy
plugins {
    id 'acme.java-library-conventions'
}
```

Thay vì phải biết bốn khối boilerplate compiler/test/packaging, module nói: **“Tôi là Java library theo convention của nhóm.”** Nó vẫn tự khai báo những dependencies/behavior riêng.

### Precompiled script hay binary plugin?

- **Precompiled script plugin**: file `.gradle` hoặc `.gradle.kts` nằm trong `src/main/groovy` hoặc `src/main/kotlin` của plugin build. Gradle biên dịch nó thành plugin; ID thường được dẫn xuất từ filename. Phù hợp **cấu hình conventions** tương đối đơn giản.
- **Binary plugin**: class implements `Plugin<Project>` (Java/Groovy/Kotlin), dùng typed tasks, extensions, services. Phù hợp **logic phức tạp**, API lâu dài, nhiều tests và publishing ra nhiều repositories.
- Có thể **kết hợp**: precompiled convention plugin apply một binary plugin rồi thiết lập defaults cho type của nó.

**Không chọn binary plugin chỉ vì muốn chia sẻ ba dòng JavaCompile options.** Cũng không nhồi custom code generator phức tạp vào một precompiled script 500 dòng khi cần Task properties, work avoidance và functional tests.

## 12. Lab hoàn chỉnh: trích Java library policy vào included `build-logic`

Ta xây một project Gradle **8.10.2 + Java 17** gồm:

- `:core`: Java library chứa một `record Greeting`.
- `:format`: Java library sử dụng `:core`, format một thông báo.
- `:app`: Java application sử dụng `:format` và in stdout.
- `build-logic`: **independent included build** định nghĩa `acme.java-library-conventions` bằng **Groovy precompiled script plugin**.
- `:core` và `:format` áp dụng cùng convention plugin.
- `:app` **không dùng java-library convention**, vì ứng dụng có role khác; nó dùng Application plugin và cấu hình Java 17 riêng. Nếu nhiều ứng dụng xuất hiện, đó sẽ là tín hiệu tạo thêm application convention.

Tại sao đây là ví dụ của **lựa chọn mức tái sử dụng**, chứ không chỉ “đổi chỗ code”? Vì ta chủ động **giới hạn** policy áp dụng vào những modules có cùng semantic role.

### 12.1. Yêu cầu chạy lab

- Gradle Wrapper **8.10.2**, được commit đầy đủ (`gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, `gradle/wrapper/gradle-wrapper.properties`).
- JDK 17 được Gradle tìm thấy hoặc toolchain Java 17 được provision bằng resolver hợp lệ.
- Không cần third-party application libraries; chỉ Gradle core plugins `java-library`, `application` và `groovy-gradle-plugin` cho build logic.
- Nếu Gradle/plugin resolution phải truy cập repository, môi trường cần mạng hoặc cache hợp lệ. Bài không yêu cầu kết nối Maven Central cho app code.
- Chạy từ root chứa `settings.gradle`.

### 12.2. Cây thư mục

```text
reuse-level-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/
│       └── acme.java-library-conventions.gradle
├── core/
│   ├── build.gradle
│   └── src/main/java/demo/core/Greeting.java
├── format/
│   ├── build.gradle
│   └── src/main/java/demo/format/Formatter.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
```

**Tất cả file trong cây là file thật cần tạo**; riêng Wrapper phải sinh qua Gradle `wrapper` task, không tạo một `gradle-wrapper.jar` giả. `build-logic` là **một Gradle build độc lập**, không được khai báo bằng `include ':build-logic'` như một ordinary subproject.

### 12.3. Root `settings.gradle`

```groovy
pluginManagement {
    includeBuild('build-logic')
}

rootProject.name = 'reuse-level-lab'

include ':core', ':format', ':app'
```

`pluginManagement { includeBuild('build-logic') }` cho phép Gradle resolve **plugin IDs** được build bên trong included build khi các modules dùng `plugins {}`.

`include ':core', ':format', ':app'` đăng ký ba subprojects thông thường. Chúng là product/source projects, còn `build-logic` có settings riêng. Đừng trộn `include ':build-logic'` vào danh sách đó.

### 12.4. Root `build.gradle`

```groovy
// Root chỉ chứa build-level entry point.
// Không áp dụng java-library cho mọi subproject từ đây.
```

Root script không buộc phải có `subprojects {}`, `allprojects {}` hoặc eager configure tasks. Mỗi module áp dụng plugin theo vai trò.

### 12.5. `build-logic/settings.gradle`

```groovy
rootProject.name = 'build-logic'
```

Included build có tên/identity riêng. Root settings không tự thay thế `build-logic/settings.gradle`.

### 12.6. `build-logic/build.gradle`

```groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
}
```

`groovy-gradle-plugin` là plugin hỗ trợ phát triển **Groovy precompiled script plugins**. Nó xử lý việc biên dịch script trong `src/main/groovy` thành plugin có ID phù hợp. `gradlePluginPortal()` tạo nguồn resolution khi build logic sau này có dependencies/plugin requirements ngoài; lab không khai báo một third-party library cụ thể.

**Không nhầm `groovy-gradle-plugin` với `groovy` plugin dùng để compile ứng dụng viết bằng Groovy**. Đây là plugin phục vụ **plugin development** trong included build.

### 12.7. `build-logic/src/main/groovy/acme.java-library-conventions.gradle`

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

tasks.register('printJavaPolicy') {
    group = 'verification'
    description = 'Print the shared Java compilation policy'

    doLast {
        println 'java-policy=17;encoding=UTF-8'
    }
}
```

Đây là **toàn bộ convention plugin** của lab. File tên `acme.java-library-conventions.gradle` được Gradle chuyển thành plugin có ID **`acme.java-library-conventions`** (không khai báo Groovy package). Script thực hiện:

1. Apply `java-library` cho project consumer.
2. Chọn Java **17** toolchain.
3. Đặt JavaCompile source encoding `UTF-8`.
4. Đặt Java `--release 17` để hạn chế language/API/bytecode target.
5. Đăng ký một task nhỏ `printJavaPolicy` để chứng minh plugin đã được áp dụng và policy văn bản được công bố.

**Task `printJavaPolicy` chỉ in một chuỗi hằng**, nên **không tự chứng minh compiler đã được chạy với Java 17**. Kiểm tra thực tế bằng `compileJava`, `javaToolchains` và `javap -verbose` ở phần sau. Dùng `tasks.register` và `configureEach` giúp tránh eager task realization không cần thiết.

**Không thêm dependencies sản phẩm vào convention plugin** của lab, vì `:core` và `:format` có vai trò library giống nhau nhưng business dependencies của chúng không nhất thiết giống nhau.

### 12.8. `core/build.gradle`

```groovy
plugins {
    id 'acme.java-library-conventions'
}
```

Chỉ còn **tuyên bố vai trò project**. Không lặp khối Java toolchain/encoding/release nữa.

### 12.9. `core/src/main/java/demo/core/Greeting.java`

```java
package demo.core;

public record Greeting(String name) {
    public String render() {
        return "Hello, " + name + "!";
    }
}
```

Đây là source Java 17 sử dụng `record`; qua compiler/toolchain policy, `:core` tạo class `demo.core.Greeting`.

### 12.10. `format/build.gradle`

```groovy
plugins {
    id 'acme.java-library-conventions'
}

dependencies {
    implementation project(':core')
}
```

**Điểm quan trọng:** convention plugin chia sẻ **Java compilation policy**, còn dependency `implementation project(':core')` là **quyết định riêng của module format**. Nếu đưa project dependency đó vào convention chung, `:core` có thể vô tình phụ thuộc chính nó hoặc tất cả libraries bị thêm một dependency không cần.

### 12.11. `format/src/main/java/demo/format/Formatter.java`

```java
package demo.format;

import demo.core.Greeting;
import java.util.Locale;

public final class Formatter {
    private Formatter() {
    }

    public static String uppercase(String name) {
        String value = new Greeting(name).render();
        return value.toUpperCase(Locale.ROOT);
    }
}
```

`Locale.ROOT` giúp chuyển chữ hoa không phụ thuộc locale mặc định của OS. Public method chỉ trả về `String`; vì thế `:format` có thể giữ `:core` ở `implementation` thay vì buộc `api` cho kiểu `Greeting` trong public signature.

### 12.12. `app/build.gradle`

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

dependencies {
    implementation project(':format')
}

application {
    mainClass = 'demo.app.Main'
}
```

Tại sao cấu hình Java 17 của app **còn lặp một phần**? Đó là quyết định có chủ đích:

- `:app` là **application**, không phải Java library.
- Một plugin `acme.java-library-conventions` áp lên app có thể làm role/semantics sai.
- Lab chỉ có **một app**, nên giữ Java policy cục bộ để minh họa điểm không nên abstraction quá sớm.
- Nếu xuất hiện nhiều apps với cùng rules, hãy tách **`acme.java-base`** cho compiler policy và `acme.java-application-conventions` cho application behavior, hoặc tạo role-specific convention tương ứng.

Đây là tình huống “một ít duplicate vẫn hợp lý”. Mục tiêu không phải đưa về **zero repeated lines** bằng mọi giá, mà là giữ ranh giới kỹ thuật rõ.

### 12.13. `app/src/main/java/demo/app/Main.java`

```java
package demo.app;

import demo.format.Formatter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Formatter.uppercase("Gradle"));
        System.out.println("Modules=core,format,app");
    }
}
```

`Main` không biết `build-logic` nằm ở đâu. Compiler và runtime classpath được Gradle tổ chức dựa trên project dependencies: app → format → core.

### 12.14. Tạo Gradle Wrapper

Nếu project mới chưa có Wrapper và máy đã cài Gradle tương thích:

```bash
gradle wrapper --gradle-version 8.10.2 --distribution-type bin
```

Hãy **commit đủ bốn file Wrapper**, gồm `gradlew`, `gradlew.bat`, `gradle-wrapper.jar`, `gradle-wrapper.properties`. Những file đó cho phép local/CI dùng **Gradle distribution đã pin** mà không cài Gradle toàn hệ thống mỗi lần.

Đây là bước **khởi tạo Wrapper**, không phải lệnh phải chạy lại trước mỗi build. Nếu repository đã có Wrapper, dùng bản được commit theo team policy.

### 12.15. Chạy lab và kiểm tra kết quả

Linux/macOS:

```bash
./gradlew --version
./gradlew projects
./gradlew :core:compileJava :format:compileJava :app:classes
./gradlew -q :core:printJavaPolicy
./gradlew -q :format:printJavaPolicy
./gradlew -q :app:run
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :core:compileJava :format:compileJava :app:classes
.\gradlew.bat -q :core:printJavaPolicy
.\gradlew.bat -q :format:printJavaPolicy
.\gradlew.bat -q :app:run
```

Stdout của **`:core:printJavaPolicy`**:

```text
java-policy=17;encoding=UTF-8
```

Stdout của **`:format:printJavaPolicy`**:

```text
java-policy=17;encoding=UTF-8
```

Stdout **chính xác do Java `Main.main` in** khi chạy **`:app:run`**:

```text
HELLO, GRADLE!
Modules=core,format,app
```

Đây là stdout của application. Gradle vẫn có thể in `BUILD SUCCESSFUL`, task statuses hoặc Gradle/plugin warnings khi chạy các lệnh khác; không hard-code chúng vì phụ thuộc version/cache.

Kiểm tra modules trong `./gradlew projects`: root, `:core`, `:format`, `:app` xuất hiện trong project graph. `build-logic` **không là ordinary subproject `:build-logic`**, mà là included build cung cấp plugin qua plugin resolution.

### 12.16. Biên dịch/run độc lập bằng `javac` và `java`

Vì Java source của lab không có external libraries, bạn cũng có thể compile ba file bằng JDK 17 ở terminal để phân biệt **Java language behavior** với **Gradle plugin policy**.

Linux/macOS:

```bash
mkdir -p manual-classes
javac --release 17 -encoding UTF-8 -d manual-classes \
    core/src/main/java/demo/core/Greeting.java \
    format/src/main/java/demo/format/Formatter.java \
    app/src/main/java/demo/app/Main.java
java -cp manual-classes demo.app.Main
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force manual-classes | Out-Null
javac --release 17 -encoding UTF-8 -d manual-classes core/src/main/java/demo/core/Greeting.java format/src/main/java/demo/format/Formatter.java app/src/main/java/demo/app/Main.java
java -cp manual-classes demo.app.Main
```

Stdout:

```text
HELLO, GRADLE!
Modules=core,format,app
```

**Giới hạn của phép thử thủ công:** `javac` không đọc `build-logic`, `settings.gradle` hoặc convention plugin. Nó chỉ xác nhận các Java classes có thể compile/run với classpath được truyền. Để chứng minh convention plugin đã áp dụng đúng cho **Gradle build**, phải chạy các task `:core:compileJava`, `:format:compileJava` và/hoặc kiểm tra compiler options/task model.

### 12.17. Kiểm tra bytecode target

Sau `./gradlew :core:compileJava`, dùng `javap` của một JDK tương thích:

```bash
javap -verbose core/build/classes/java/main/demo/core/Greeting.class
```

Tìm:

```text
major version: 61
```

Class file major version **61** tương ứng Java 17. Nó giúp xác nhận Java compiler output phù hợp target, thay vì chỉ tin vào `printJavaPolicy` task in một chuỗi.

**Không nhầm `--release 17` với việc Gradle daemon nhất thiết chạy JDK 17.** Gradle JVM và Java toolchain là hai trách nhiệm khác nhau; với JavaCompile, toolchain mới xác định compiler được chọn theo cấu hình.

## 13. Bài học từ lab: abstraction giới hạn theo vai trò

Ở trạng thái ban đầu, `:core` và `:format` đều có cùng:

```groovy
plugins { id 'java-library' }

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
```

Sau khi trích:

```groovy
plugins {
    id 'acme.java-library-conventions'
}
```

Đó là refactor tốt vì:

- **Hai modules có cùng role** là Java libraries.
- **Cùng chính sách compiler** cần thay đồng thời.
- **Dependencies riêng** vẫn nằm ở module.
- **Consumer plugin ID** nói rõ behavior sẽ được áp dụng.
- **Không cấu hình xuyên project** từ root.
- Có thể test convention plugin bằng fixture builds.
- Khi thêm library module `:analytics`, áp dụng plugin cùng ID và tự hưởng policy.

Nhưng app vẫn có một chút cấu hình giống. Việc ấy **không làm refactor thất bại**, bởi plugin tái sử dụng lý tưởng phải phản ánh **conceptual boundaries**, không chỉ đo số dòng bị loại bỏ.

### Khi có nhiều applications

Bạn có thể tách một base convention plugin đặt Java compiler policy, rồi composition:

```text
acme.java-base
├── Java 17 toolchain
└── UTF-8 / --release 17

acme.java-library-conventions
├── apply acme.java-base
└── apply java-library

acme.java-application-conventions
├── apply acme.java-base
└── apply application
```

Đây là **sơ đồ kiến trúc**, không phải file plugin bổ sung đã được tạo trong lab. Khi có đủ consumers, cần định nghĩa các plugin này thực tế, áp dụng đúng logic và test composition. Tránh tách thành nhiều plugins quá nhỏ chỉ vì một flag đơn lẻ.

## 14. Kotlin DSL: cùng cách chọn mức reuse

Với Kotlin DSL, nên dùng **precompiled script convention plugin** trong `build-logic/src/main/kotlin`, do `kotlin-dsl` plugin hỗ trợ. Để chuyển **toàn bộ lab sang Kotlin DSL**, thay các file Groovy tương ứng, giữ nguyên Java source.

### 14.1. Root `settings.gradle.kts`

```kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "reuse-level-lab"
include(":core", ":format", ":app")
```

### 14.2. `build-logic/settings.gradle.kts`

```kotlin
rootProject.name = "build-logic"
```

### 14.3. `build-logic/build.gradle.kts`

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
```

### 14.4. `build-logic/src/main/kotlin/acme.java-library-conventions.gradle.kts`

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.register("printJavaPolicy") {
    group = "verification"
    description = "Print the shared Java compilation policy"

    doLast {
        println("java-policy=17;encoding=UTF-8")
    }
}
```

Tên file cho plugin ID `acme.java-library-conventions` theo precompiled script plugin conventions. Không cần viết một `class AcmePlugin` bằng Kotlin cho ví dụ chỉ cấu hình defaults.

### 14.5. `core/build.gradle.kts`

```kotlin
plugins {
    id("acme.java-library-conventions")
}
```

### 14.6. `format/build.gradle.kts`

```kotlin
plugins {
    id("acme.java-library-conventions")
}

dependencies {
    implementation(project(":core"))
}
```

### 14.7. `app/build.gradle.kts`

```kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

dependencies {
    implementation(project(":format"))
}

application {
    mainClass.set("demo.app.Main")
}
```

Root `build.gradle.kts` có thể chỉ chứa comment. Các Java sources `Greeting.java`, `Formatter.java`, `Main.java` không thay đổi. Chạy `./gradlew -q :app:run` vẫn kỳ vọng:

```text
HELLO, GRADLE!
Modules=core,format,app
```

**Đừng giữ cả `build.gradle` và `build.gradle.kts` ở cùng một project chỉ để Gradle “kết hợp” logic.** Hãy chọn rõ một DSL. Việc chuyển Groovy → Kotlin có thể cần đổi cú pháp Property API, plugins block, type-safe accessors và dependencies; điều đó không liên quan trực tiếp đến việc chọn mức tái sử dụng.

### Cảnh báo về catalog trong precompiled plugin

Alias `libs` của root không phải luôn có sẵn trong plugin sources của included build. Nếu đưa `libs.junit.jupiter` vào precompiled plugin, hãy khai báo catalog trong settings của **build-logic** hoặc dùng một version-management mechanism phù hợp. Với external plugins trong precompiled plugin, build-logic cần thêm plugin artifact vào **implementation classpath**, và plugin script áp dụng plugin theo ID không kèm `version` trong `plugins {}` của precompiled script.

## 15. Binary plugin: khi reusable logic đã trở thành API

Giả sử nhiều modules cần một generator:

- Nhận file JSON schema theo `@InputFile`.
- Nhận output directory `@OutputDirectory`.
- Dùng Worker API hoặc ExecOperations để tạo code.
- Tham số cấu hình qua một extension có `Property<T>`.
- Có tests, incremental build và configuration cache requirements.
- Được chia sẻ qua nhiều builds và repositories.

Một precompiled script chỉ dùng vài `tasks.register` closure có thể trở nên khó bảo trì. Lúc ấy cân nhắc **binary plugin** với class `Plugin<Project>`, custom task type và typed extension.

Ví dụ Java API tối thiểu về cơ chế plugin:

```java
package demo.buildlogic;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class GreetingPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getTasks().register("greetBuild", task ->
            task.doLast(action ->
                System.out.println("build-policy=hello"))
        );
    }
}
```

**Đây là Java snippet, không phải một plugin runnable độc lập.** Để dùng nó cần project plugin development (`java-gradle-plugin`), Gradle API classpath, plugin ID registration qua `gradlePlugin { plugins { ... } }` và build/test/publish setup. Nó không nằm trong lab `build-logic` ở mục 12.

Nếu một plugin cần cung cấp các typed task outputs, code production phải đi xa hơn snippet: định nghĩa `DefaultTask` subclass, `@Input`, `@InputFile`, `@OutputFile`, lazy `Property`/`Provider` wiring và task actions không truy cập mutable Project model sai thời điểm.

**Đừng chọn binary plugin chỉ vì có nhiều dòng script.** Chọn khi behavior thực sự cần API/typed abstractions/test coverage/publishing.

## 16. Bố trí responsibilities: một convention plugin không nên làm tất cả

Một kiến trúc convention logic dễ phát triển:

```text
build-logic/
└── convention plugins
    ├── acme.java-base
    ├── acme.java-library
    ├── acme.java-application
    ├── acme.test-junit
    ├── acme.quality
    └── acme.publish-library
```

Nhưng đó chỉ là **mẫu thiết kế**. Trong repo có 3 modules, tạo sáu plugins ngay có thể là over-engineering.

### Cách xác định boundary

**Java base** — có thể dùng chung:
- Toolchain version, compiler encoding/`--release`.
- Compiler warnings theo policy, shared test defaults khi phù hợp.
- Reproducible archives nếu mọi archive consumer cùng policy.

**Java library** — dành cho thư viện:
- `java-library` plugin.
- `api` vs `implementation` discipline.
- Publishing convention chỉ nếu module được publish.

**Java application** — dành cho ứng dụng:
- `application` plugin, main class conventions.
- Distribution/start scripts/runtime flags.
- Không tự áp dụng `maven-publish` nếu chỉ chạy app.

**Quality** — áp dụng theo role:
- Checkstyle/Spotless tasks.
- Rule files và quality gates.
- Không ép một generator module không có Java sources chạy Java source analyzer.

**Publishing** — kiểm soát quyền:
- Maven repositories/credentials.
- Signing/version policy.
- Không bật publish cho mọi internal module.

Điều quan trọng là một plugin **được áp dụng ở những nơi có cùng lifecycle/contract**, không phải mỗi plugin đại diện cho một property riêng lẻ.

## 17. “Convention” khác “policy bắt buộc tuyệt đối”

Một convention có thể định nghĩa default:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Nó cung cấp policy mặc định nhưng không tự động bảo đảm mọi consumer **không thể override** version sau khi plugin được áp dụng. Nếu tổ chức yêu cầu **enforcement** tuyệt đối, cần:

- Có governance và tests phát hiện override sai.
- Phân biệt `convention(...)`, `set(...)`, `finalizeValue()`, `disallowChanges()` theo property/API khi thiết kế typed extensions.
- Xây validation task/hợp đồng có thông báo lỗi rõ.
- Không cứng hóa mọi setting khi dự án cần ngoại lệ được phê duyệt.

**Đừng coi cấu hình trong convention plugin là kiểm soát bảo mật bất khả thay đổi.** Module build scripts vẫn có thể chỉnh một số properties hoặc áp dụng plugin khác; yêu cầu policy compliance cần cơ chế kiểm tra cụ thể.

### Ngoại lệ nên được thiết kế ra sao?

Giả sử một module cần Java 21 trong khi đa số module dùng Java 17. Những lựa chọn:

1. Giữ module ấy ở convention role khác.
2. Cho phép một typed extension có phiên bản Java policy được validate.
3. Thiết kế plugin `acme.java-21-tool` riêng nếu có nhiều consumers.
4. Chấp nhận local override có lý do, comment và bài test, nếu policy cho phép.

**Không thêm 15 cờ `skipX`, `useY`, `onlyZ` vào một plugin chung** chỉ để mọi loại project cùng sử dụng nó. Đó thường là dấu hiệu abstraction đã vượt quá boundary tự nhiên.

## 18. Settings-level policy không nên bị giấu trong Project plugin

Một số cấu hình có scope khác:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
```

Đây là **settings scope**. Nó chi phối plugin resolution và external repository policy cho build. Một convention plugin kiểu `Plugin<Project>` được áp dụng sau khi settings quyết định project graph/plugin resolution, nên không phải nơi thích hợp để trộn tất cả settings-level rules.

Nếu repo có nhiều subprojects, thống nhất repositories nên được xử lý bằng settings và các `RepositoriesMode` policy khi phù hợp; không dùng:

```groovy
allprojects {
    repositories {
        mavenCentral()
    }
}
```

làm giải pháp duy nhất chỉ vì trông gọn. Settings-based policy làm rõ nguồn resolution và giảm nguy cơ từng module tự thêm repository khó kiểm soát.

### Settings convention plugin cũng có tradeoff

Gradle hỗ trợ Settings plugins, nhưng chúng phải có mặt đúng lúc để apply lên `Settings`; `pluginManagement.includeBuild` có thể được dùng để resolve Settings plugin từ included build. Với hệ thống lớn, một **minimal settings-plugin build riêng** có thể giảm tác động lên build cache/performance so với trộn toàn bộ Project plugin logic vào Settings classpath.

Không tạo Settings plugin chỉ để đặt một `rootProject.name`. Mục tiêu là **đúng lifecycle scope**, không phải biến mọi settings line thành plugin.

## 19. Lazy configuration, Provider API và task graph

Một shared plugin có thể chạm hàng chục modules. Vì vậy hiệu năng cấu hình quan trọng:

**Nên làm:**

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

```groovy
tasks.register('verifyRules') {
    group = 'verification'
    doLast {
        println 'verified-policy=defined'
    }
}
```

Các đoạn trên dùng `configureEach` và `register` để không hiện thực hóa mọi tasks quá sớm.

**Cần cân nhắc:**

```groovy
tasks.all { task ->
    // Có thể cấu hình nhiều task không cần thiết.
}
```

```groovy
tasks.create('eagerTask') {
    // Tạo task eager, không phải lựa chọn mặc định.
}
```

Không phải mọi lệnh `tasks.all` đều luôn sai, nhưng với convention plugin lớn, nên ưu tiên lazy registration/configuration.

### Provider/property thay vì đọc quá sớm

Khi một task tiêu thụ đường dẫn hoặc option được tính từ build properties, ưu tiên `Provider`, `RegularFileProperty`, `DirectoryProperty`, `Property<T>` và task inputs/outputs. Đừng đọc biến môi trường ở top-level build script rồi nhét vào mutable global state nếu có API dành cho lazy input tracking.

Ví dụ ý niệm:

```groovy
def labelProvider = providers.gradleProperty('buildLabel')
    .orElse('local')
```

Đây là một **Provider**, chưa phải một task đầy đủ. Custom typed task có thể nhận `labelProvider` qua `Property<String>` và khai báo `@Input`. Nếu chỉ gọi `.get()` ở configuration time rồi in trong `println`, bạn mất phần lợi ích lazy/provider input modeling.

### Configuration cache

Một plugin áp dụng chung có thể làm mọi module chịu tác động nếu nó:

- Truy cập `Project` mutable model trong task actions không phù hợp.
- Gọi process/network trong configuration phase.
- Capture `Project`, `Configuration` hay objects không được hỗ trợ vào task closures.
- Đọc files/env mà không khai báo là task input hoặc configuration input.
- Dựa vào `afterEvaluate` và thứ tự cross-project configuration.
- Tạo task không khai báo outputs nhưng lại giả định có thể cache.

Khi migrate, kiểm thử với:

```bash
./gradlew :core:build :format:build --configuration-cache
```

Đọc các warnings/errors thật, không vội tắt configuration cache cho toàn repo. Shared plugin nên **tương thích với tối ưu hóa Gradle**, không làm build chậm đi chỉ để loại vài chục dòng boilerplate.

### Isolated projects

Gradle có các cơ chế isolation của project configuration nhằm hỗ trợ performance/parallelization. Root `subprojects {}` và configuration của Project khác thường là trở ngại. Convention plugin được **apply tại chính project đang cấu hình** giúp giảm cross-project coupling và phù hợp hơn với hướng dẫn mới.

Không tuyên bố rằng chuyển mọi dòng từ root sang một plugin tự động “isolated-projects compatible”; plugin vẫn phải tránh cross-project access và sử dụng Gradle APIs đúng thời điểm.

## 20. Thử nghiệm policy bằng Gradle TestKit và fixture projects

Một convention plugin đáng tin nên có tests cho **behavior**, không chỉ chứa các constants.

Các câu hỏi có thể kiểm tra:

1. Áp dụng `acme.java-library-conventions` có tạo `compileJava`, `jar` không?
2. JavaCompile có `options.release=17` và UTF-8 không?
3. Java toolchain 17 có được chọn không?
4. `printJavaPolicy` có in đúng một dòng đã định không?
5. Module không áp plugin có bị tác động ngầm không?
6. Plugin có chạy với configuration cache theo policy không?
7. Build qua Wrapper ở clean checkout có cần user-specific `init.gradle` hoặc mavenLocal không?
8. Khi nâng Gradle version, plugin API và DSL còn tương thích không?
9. Khi project là `application`, plugin có bị apply nhầm `java-library` không?
10. Khi shared plugin có dependency bên ngoài, build-logic repositories/catalog có resolve đúng không?

**Gradle TestKit** cho phép chạy Gradle builds của fixture trong tests, kiểm tra task outcomes/stdout/error. Đây là gợi ý kiến trúc; lab hiện tại không có test project cho build-logic vì mục tiêu chính là **chọn mức reuse**, không phải hướng dẫn toàn bộ test infrastructure.

Một smoke test thực tế trong repo là:

```bash
./gradlew clean :core:compileJava :format:compileJava :app:run
```

Sau đó có thể dùng `javap` để xác nhận Java 17 target và đối chiếu stdout của app. Với CI, thêm `test` tasks khi dự án có tests thực, lưu reports và không chỉ dựa vào một task in policy string.

## 21. Kế hoạch migration không phá vỡ build

Đừng chuyển 30 modules sang convention plugin trong một PR lớn mà chưa có baseline. Một kế hoạch incremental:

### Giai đoạn A — xác định phạm vi

1. Liệt kê modules theo **role**: Java library, app, integration test, plugin, packaging-only.
2. Ghi tất cả shared configurations có cùng nghĩa.
3. Phân biệt versions/dependencies với task/plugin behavior.
4. Tìm sự khác biệt thật; làm rõ các ngoại lệ.
5. Xác định owner và review policy cho shared build logic.

### Giai đoạn B — chọn pilot

1. Chọn hai libraries giống nhau nhưng nhỏ.
2. Ghi baseline `./gradlew :module:build`, tests, artifacts.
3. Tạo included `build-logic`.
4. Tạo một convention plugin có tên rõ.
5. Áp dụng vào hai modules; giữ dependencies riêng.
6. Kiểm tra task graph, compiler options, tests và outputs.

### Giai đoạn C — mở rộng có kiểm soát

1. Chuyển từng nhóm module cùng role, không chuyển tất cả vô điều kiện.
2. Mỗi PR so sánh behavior trước/sau và kiểm tra trên clean build.
3. Nếu phát sinh nhiều override, xem lại plugin boundary thay vì thêm cờ liên tục.
4. Đưa JUnit/catalog/publishing rules vào tầng phù hợp.
5. Thêm tests cho build-logic và đo configuration time.

### Giai đoạn D — ổn định

1. Document plugin IDs và assumptions.
2. Ghi nơi thay policy cho Java/toolchain/dependency resolution.
3. Kiểm tra configuration cache và Gradle version compatibility.
4. Không để cả root `subprojects {}` và convention plugin vô tình áp cùng rule hai lần.
5. Giữ plugin API đơn giản, có owner và change log khi cần.

**Không đổi đồng thời** Java version, Gradle Wrapper version, dependency versions và build logic structure nếu mục tiêu PR chỉ là loại bỏ cấu hình lặp. Thay đổi quá nhiều yếu tố sẽ khó xác định regressions.

## 22. Những lựa chọn dễ sai: tình huống và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Một library vẫn dùng Java 11 sau khi “chia sẻ” policy | Module chưa áp convention plugin hoặc có override | Kiểm tra `plugins {}` của chính module và compiler options thực. |
| App bỗng có tasks như Java library | Root `subprojects {}` apply `java-library` hàng loạt | Chuyển sang role-specific plugin, áp dụng tường minh. |
| `Plugin [id: 'acme.java-library-conventions'] was not found` | Root settings chưa include build-logic cho plugin resolution hoặc plugin file name/scope sai | Kiểm tra `pluginManagement.includeBuild`, `groovy-gradle-plugin`, file under `src/main/groovy`. |
| `build-logic` không thấy alias `libs` | Included build có catalog/settings riêng | Khai báo/import catalog tại build-logic hoặc dùng dependency version policy rõ. |
| Plugin chỉ có một module dùng nhưng rất phức tạp | Trừu tượng hóa sớm | Cân nhắc đưa về local task/script cho đến khi contract ổn định. |
| Tất cả modules bị thêm JUnit/runtime deps | Convention plugin nhét business/test deps vào mọi consumer | Chọn plugin test role hoặc để module tự khai báo. |
| Script plugin dùng `plugins {}` không chạy như mong đợi | Giới hạn applied scripts và plugin DSL | Chuyển thành precompiled convention plugin phù hợp. |
| Plugin bị gọi trước plugin nó cần | Giả định plugin application order | Để convention apply plugin cần thiết hoặc dùng `pluginManager.withPlugin`. |
| Build chỉ chạy được khi `afterEvaluate` | Deferred mutation và lifecycle assumptions | Dùng lazy task/provider/configuration conventions. |
| `subprojects {}` sửa tất cả projects nhưng IDE khó trace | Implicit cross-project behavior | Áp convention plugin tại module. |
| `buildSrc` thay đổi làm cấu hình nhiều modules bị invalidated | Build logic classpath chung | Cân nhắc move sang included `build-logic` để modularize. |
| Configuration cache fail sau refactor | Shared plugin truy cập Project model trong task action | Viết typed task, Provider, injected services đúng scope. |
| Root version catalog đã pin nhưng selected version vẫn khác | Version catalog không ép toàn bộ resolution conflicts | Dùng constraints/platform/locking/verification nếu cần governance. |
| Binary plugin dùng chung hai repos nhưng không có version | Copy/paste plugin source và release không quản lý | Publish versioned artifact/plugin và kiểm thử compatibility. |
| Một change build-logic phá nhiều modules | Shared plugin blast radius lớn, thiếu tests | Test fixture, pilot migration, PR review theo owners. |
| `:app:run` fail vì class `Formatter` thiếu | Module-specific project dependency chưa khai báo | Giữ `implementation project(':format')` tại app build script. |
| Core Java record không compile bằng Gradle | Toolchain 17 chưa có, plugin không apply hoặc compiler flag khác | Kiểm tra `javaToolchains`, plugin apply, `javap` và Gradle logs. |
| CI tải plugin khác máy local | Plugin resolution/catalog/repositories/Wrapper không đồng nhất | Pin Wrapper/plugin versions và repository policy. |
| Build chậm hơn sau “dọn lặp” | Eager tasks, plugin classpath hoặc too many conventions | Đo configuration time, dùng `register`/`configureEach`, đơn giản hóa plugin graph. |

## 23. Một số anti-pattern điển hình

### 23.1. “Một plugin common cho mọi module”

```groovy
subprojects {
    apply plugin: 'java-library'
    apply plugin: 'maven-publish'
    // và hàng chục dependencies/tasks khác...
}
```

Vấn đề: không phân biệt library/application/tool/packaging, mở publishing vô tình, kéo mọi dependency vào mọi project và làm khó isolation.

**Thay thế:** role-specific convention plugins; app, library và publishing được chọn độc lập theo nhu cầu. Có thể áp dụng cùng nhiều plugins ở project thật sự cần chúng.

### 23.2. “Mọi dependency trong catalog đều là policy”

```toml
[libraries]
http = { module = "example:http", version = "1.0" }
```

Alias chỉ là **tên tham chiếu**. Nó không có nghĩa mọi module phải dùng thư viện `http`. Phải nhìn dependency graph thực sự.

### 23.3. “Nhét exception vào convention để ai cũng dùng chung”

```text
commonConvention:
  useJava17=true
  skipTest=false
  skipCoverage=true
  isAndroid=false
  isServer=true
  useLegacyCompiler=false
  enablePublishSometimes=true
  ...
```

Đây là **mô tả anti-pattern**, không phải DSL hợp lệ. Khi số lượng flags tăng nhanh, plugin đã trở thành một abstraction không có semantic boundary. Nên tách theo roles/capabilities hoặc giữ exceptions local.

### 23.4. “Thay `dependsOn` bằng thứ tự configuration”

Nếu một task cần output của task khác, không đủ để nó “được khai báo sau” trong script. Shared plugin cần **wiring qua task dependency và Provider outputs**, không dựa vào thứ tự lines trong build.gradle. Đặc biệt với code generation, sai task wiring có thể khiến build chỉ thành công khi outputs cũ còn trên đĩa.

### 23.5. “Chạy process lúc configuration để kiểm tra tool”

Nếu convention plugin gọi `git --version` hoặc tải file ngay lúc apply, **mọi module áp plugin** có thể gây side effects ngay cả khi chỉ chạy `help`. Nên chuyển vào typed task/ExecOperations action hoặc dùng Provider APIs và validation có lifecycle phù hợp.

## 24. Quy tắc phối hợp giữa catalog, platform và convention plugins

Ba công cụ có vai trò khác nhau:

- **Version catalog**: đặt **alias** và **requested version** được dùng trong dependency/plugin declarations.
- **Java platform/BOM/constraints**: mô hình hóa **version alignment/constraints trong dependency graph**.
- **Convention plugin**: áp **build behavior/configuration** lên một Project.

Ví dụ kiến trúc:

```text
settings.gradle
  ├── pluginManagement / dependencyResolutionManagement
  └── include builds/projects

gradle/libs.versions.toml
  └── alias + versions của dependencies/plugins

build-logic/
  └── acme.java-library-conventions
       ├── apply java-library
       ├── compiler/toolchain/test policies
       └── optional quality conventions

core/build.gradle
  ├── apply acme.java-library-conventions
  └── dependencies riêng theo domain
```

Không phải mọi trường hợp cần cả ba. Một project chỉ dùng Java core không có external deps như lab có thể **không cần catalog/platform**. Đừng xây hạ tầng version governance vô ích chỉ để có đầy đủ các khái niệm.

## 25. Chi phí của tái sử dụng: blast radius, versioning và debugging

Trích logic chung giảm số chỗ sửa, nhưng đổi lại:

1. **Blast radius tăng:** sửa plugin có thể ảnh hưởng mọi module sử dụng.
2. **Classpath/build-logic compilation:** code shared phải được biên dịch/resolve trước consumer builds.
3. **Upgrade compatibility:** Gradle/Kotlin DSL/Groovy APIs có thể thay đổi theo phiên bản.
4. **Testing responsibility:** quy tắc chung cần fixture/functional tests thay vì tin vào một module.
5. **Debugging path dài hơn:** khi `:format:compileJava` fail, nguyên nhân có thể ở build-logic thay vì `format/build.gradle`.
6. **Ownership cần minh bạch:** ai duyệt thay Java version/quality policy?
7. **Plugin graph có thể phức tạp:** quá nhiều convention composition làm behavior khó nhìn.
8. **Quá ít granularity:** một “mega-plugin” lại gắn nhiều behavior không liên quan.
9. **Publishing/versioning:** nếu chia sẻ nhiều repositories, version và compatibility phải rõ.
10. **Security:** build-logic có quyền chạy mã trên máy developer và CI; review plugins/dependencies như code production.

**Đánh giá hiệu quả đúng** bằng số lỗi cấu hình giảm, thời gian thêm module mới, độ dễ đọc của build scripts, build performance, tính testability và việc thay policy có kiểm soát — không chỉ bằng số dòng bị xóa.

## 26. Mẫu đánh giá cho một đề xuất refactor

Khi một đồng nghiệp đề nghị “gom mọi cấu hình lặp vào plugin”, reviewer có thể dùng mẫu:

```text
Tên policy:          Java library compilation
Consumers hiện tại:  :core, :format, :shared
Consumers dự kiến:   Các module java-library mới
Quy tắc dùng chung:  Java 17 / UTF-8 / --release 17
Quy tắc giữ riêng:   implementation dependencies, publishing
Owner:               Nhóm build/platform
Abstraction chọn:    acme.java-library-conventions
Vị trí:              build-logic included build
Lý do không dùng:    subprojects {} / apply from
Khả năng tùy biến:   Ngoại lệ Java 21 qua role khác / review
Kiểm chứng:          Gradle tasks + javap + clean CI
Rủi ro:              Thay plugin ảnh hưởng mọi library consumer
Rollback:            Khôi phục cấu hình cục bộ trong module pilot
```

Đây là **mẫu biên bản**, không phải file Gradle executable. Giá trị của nó là làm rõ lý do lựa chọn và blast radius trước khi sửa repository.

### Checklist hoàn tất

- Đã phân loại module roles.
- Đã xác nhận repetition là **semantic policy**, không phải copy tình cờ.
- Đã chọn đúng scope: Settings/catalog/Project convention/custom task.
- Đã thử pilot ít modules trước.
- Đã để project-specific dependencies ở module.
- Đã kiểm chứng compiler/runtime/test behavior, không chỉ task in một chuỗi.
- Đã kiểm tra clean Wrapper build/CI và configuration cache khi cần.
- Đã kiểm tra `build-logic` plugin resolution/catalog scope.
- Đã tránh eager/cross-project mutation.
- Đã document plugin ID, ownership và ngoại lệ.

## 27. Bài tập tự kiểm tra có đáp án

**Câu 1.** Hai `build.gradle` đều dùng Java 17. Có bắt buộc phải tạo convention plugin ngay không?

**Đáp án:** Không. Cần xác định hai modules có cùng **policy và vòng đời thay đổi** hay chỉ trùng tạm thời. Một module Java 21 trong tương lai có thể nên giữ riêng.

**Câu 2.** Nhiều modules cùng dùng version JUnit. Version catalog có đủ để chia sẻ `useJUnitPlatform()` không?

**Đáp án:** Không. Catalog quản lý aliases/versions; Test task behavior cần cấu hình riêng hoặc convention plugin.

**Câu 3.** Khi nào `subprojects {}` là giải pháp kém hơn convention plugin?

**Đáp án:** Khi root cấu hình xuyên project, khó thấy implicit behavior, áp dụng sai project role và gây trở ngại cho isolation/configuration performance.

**Câu 4.** Vì sao `acme.java-library-conventions` rõ hơn `common`?

**Đáp án:** Tên nói rõ capability và consumer role; `common` dễ biến thành tập hợp policy không liên quan.

**Câu 5.** `buildSrc` có bị loại bỏ/deprecated không?

**Đáp án:** Không. Nó vẫn hỗ trợ; included `build-logic` thường được khuyên dùng cho monorepo lớn vì isolation, lifecycle và testing/reuse rõ hơn.

**Câu 6.** Trong lab, vì sao `:app` không áp dụng `acme.java-library-conventions`?

**Đáp án:** App dùng Application plugin và có role khác; áp library convention chỉ để xóa thêm vài dòng lặp là abstraction sai boundary.

**Câu 7.** File nào khai báo included build cung cấp convention plugin?

**Đáp án:** Root `settings.gradle` với `pluginManagement { includeBuild('build-logic') }`.

**Câu 8.** File `acme.java-library-conventions.gradle` của Groovy precompiled plugin đặt ở đâu?

**Đáp án:** `build-logic/src/main/groovy/acme.java-library-conventions.gradle`.

**Câu 9.** Plugin ID của file đó là gì?

**Đáp án:** `acme.java-library-conventions`.

**Câu 10.** Stdout của `:core:printJavaPolicy` trong lab là gì?

**Đáp án:**

```text
java-policy=17;encoding=UTF-8
```

**Câu 11.** Dòng trên có tự chứng minh compiled bytecode Java 17 không?

**Đáp án:** Không. Đó là chuỗi hằng; cần compile thật và có thể dùng `javap` xem major version 61.

**Câu 12.** Stdout chuẩn của Java `:app:run` là gì?

**Đáp án:**

```text
HELLO, GRADLE!
Modules=core,format,app
```

**Câu 13.** Vì sao `implementation project(':core')` vẫn ở `format/build.gradle`?

**Đáp án:** Nó là dependency thuộc tính năng của format; không phải policy cho mọi Java library.

**Câu 14.** Khi một plugin cần `@InputFile`/`@OutputDirectory`, Worker API và typed extension, lựa chọn gì hợp lý hơn?

**Đáp án:** Binary plugin/typed custom task có API và tests rõ, có thể được convention plugin cấu hình.

**Câu 15.** Một included build có tự thấy version catalog của root không?

**Đáp án:** Không mặc nhiên. Build-logic có settings/catalog scope riêng; phải cấu hình reuse có chủ đích.

**Câu 16.** `apply from` có phải luôn sai không?

**Đáp án:** Không. Nó có thể hữu ích cho script nhỏ/legacy migration; convention plugin thường phù hợp hơn với shared policy lâu dài.

**Câu 17.** Khi nào tạo thêm `acme.java-application-conventions`?

**Đáp án:** Khi nhiều application modules có cùng behavior ổn định và một owner policy chung; không phải vì lab có một app.

**Câu 18.** Việc thay plugin dùng chung có rủi ro gì?

**Đáp án:** Blast radius tới mọi consumer, nên cần tests/gradual migration và owner review.

**Câu 19.** Task register trong convention nên dùng gì thay eager `tasks.create`?

**Đáp án:** `tasks.register`, kết hợp `tasks.withType(...).configureEach` cho shared task policies.

**Câu 20.** Settings-level Maven repository policy có nên nhét vào một Project convention plugin không?

**Đáp án:** Thường không; dùng `dependencyResolutionManagement` ở settings để đúng scope.

**Câu 21.** `--configuration-cache` build fail sau refactor plugin chứng minh điều gì?

**Đáp án:** Có thể plugin đang dùng API/capture/configuration không tương thích; cần đọc lỗi và sửa, không mặc định bỏ cache.

**Câu 22.** Tại sao không áp dụng `maven-publish` cho mọi project qua root `subprojects`?

**Đáp án:** Không phải module nào cũng xuất bản artifact; áp dụng sai có thể tạo tasks/config và quyền publishing không cần thiết.

**Câu 23.** Một version catalog có ép được mọi dependency selected version chính xác như requested không?

**Đáp án:** Không tự bảo đảm. Gradle dependency graph resolution và constraints/locking/verification cần được hiểu riêng.

**Câu 24.** `javac` thủ công chạy được lab có chứng minh Gradle convention plugin được resolve đúng không?

**Đáp án:** Không. `javac` không đọc Gradle build scripts; phải chạy Wrapper tasks để kiểm chứng plugin resolution/configuration.

**Câu 25.** Tiêu chí chọn abstraction quan trọng nhất là gì?

**Đáp án:** Các consumers có cùng **semantic contract và lý do phải thay đổi đồng thời**; tránh trừu tượng hóa chỉ vì text giống nhau.

## 28. Nguồn tham khảo chính thức

- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): convention plugins, ưu tiên `build-logic` included build, giới hạn `buildSrc` và project roles.
- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html): cấu hình build logic chung bằng convention plugin, tránh root cross-project configuration.
- [Gradle — Precompiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html): Groovy/Kotlin script plugins, plugin IDs từ filenames, external plugin classpath.
- [Gradle — Sharing Build Logic using buildSrc](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): cách `buildSrc` hoạt động, precompiled conventions và consumer modules.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): `includeBuild`, independent settings/repositories và task/build boundaries.
- [Gradle — General Best Practices](https://docs.gradle.org/current/userguide/best_practices_general.html): không giả định plugin application order và tránh lạm dụng `allprojects`/`subprojects`/`afterEvaluate`.
- [Gradle — Isolated Projects](https://docs.gradle.org/current/userguide/isolated_projects.html): tác động của cross-project configuration và hướng dùng conventions.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): aliases, versions, separate catalogs và version management.
- [Gradle — Implementing Gradle Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): lựa chọn applied script, precompiled script và binary plugin.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `configureEach` và hiệu năng cấu hình.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): inputs/configuration requirements cho shared logic.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): JavaCompile, toolchain Java 17.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`/`implementation` và project dependencies.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): Java app `run`, mainClass, distribution.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): pin Gradle distribution cho local/CI.
- [Gradle — TestKit](https://docs.gradle.org/current/userguide/test_kit.html): functional tests cho Gradle plugins.

**Kết luận:** nhận diện cấu hình lặp bằng **ý nghĩa và nguyên nhân thay đổi**, không bằng số dòng giống nhau. Chọn **local configuration** cho ngoại lệ và dự án nhỏ, **version catalog/platform** cho dependency data/governance, **convention plugins** cho project behavior lặp có ranh giới rõ, **binary plugins** cho logic phức tạp có API/typed tasks, và **included `build-logic`** cho build logic chung quy mô lớn. Đặt các policy cấp Settings ở Settings; tránh áp mọi thứ vào mọi project bằng `subprojects {}`. Quan trọng nhất là kiểm chứng **behavior thật** qua Wrapper, Java 17 compilation, tasks, tests và CI — không chỉ nhìn số dòng cấu hình được xóa.