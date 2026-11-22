# Quản lý cấu hình dùng chung, baseline và ngoại lệ có giải thích trong chất lượng mã Gradle

## 1. Mục tiêu và bối cảnh

Trong một dự án Java nhỏ, mỗi module có thể tự đặt vài quy tắc chất lượng mã. Nhưng khi codebase có hàng chục subprojects, việc để mỗi nơi dùng **phiên bản công cụ, ruleset, mức độ nghiêm khắc và danh sách ngoại lệ khác nhau** tạo ra nhiều vấn đề:

- Module A dùng Checkstyle 10.x, module B dùng bản khác nên cùng một file Java có thể được đánh giá khác nhau.
- Một nhóm vô tình bật `ignoreFailures = true` để build xanh, trong khi CI không còn chặn lỗi mới.
- Một ruleset mới phát hiện hàng nghìn lỗi cũ; nếu bật fail toàn bộ ngay, nhóm không thể nâng cấp dần.
- Một suppression được thêm mà không có lý do hoặc người chịu trách nhiệm, rồi tồn tại vĩnh viễn.
- PR cải tiến code ở module mới bị làm khó, nhưng những đoạn legacy nguy hiểm lại được miễn trừ quá rộng.
- Một rule bị tắt trên toàn repository chỉ vì một package cũ chưa sẵn sàng sửa.

Để giải quyết, cần kết hợp ba lớp quản trị:

1. **Cấu hình dùng chung (shared configuration)**: một nguồn chuẩn cho tool version, rules, Gradle tasks, reports và chính sách CI.
2. **Baseline (đường cơ sở)**: ảnh chụp hoặc danh mục **những vi phạm đã tồn tại và được chấp nhận tạm thời** tại thời điểm bắt đầu áp dụng chính sách; từ đó theo dõi không tăng thêm nợ kỹ thuật.
3. **Ngoại lệ có giải thích (documented exceptions)**: suppression/exclusion có **phạm vi nhỏ, lý do, chủ sở hữu, ticket và điều kiện xem xét/xóa**; không phải tắt kiểm tra vô thời hạn.

Bài học thuộc chủ đề **Chất lượng mã** của Build Tool Gradle. Các ví dụ dùng **Groovy DSL**, Java 17, core plugins `java`, `checkstyle`, `pmd` và các lệnh Gradle Wrapper. Phần thực hành chính là **project Java 17 chạy được** với Checkstyle: một file legacy cố tình vi phạm `AvoidStarImport`, suppression chỉ nhắm file/rule đó và một test JUnit Jupiter. Những ví dụ convention plugin và PMD được ghi rõ là **mẫu mở rộng cho multi-project**, không phải thành phần bắt buộc của project demo.

Sau bài, bạn sẽ biết quản lý một bộ quy tắc nhất quán cho nhiều modules, tạo và thu hẹp baseline, review một ngoại lệ, vận hành CI chặn lỗi mới và phân biệt baseline ở cấp tổ chức với khả năng kỹ thuật thật sự của từng công cụ.

## 2. Các công cụ chất lượng mã trong Gradle

| Công cụ | Mục đích | Tích hợp Gradle | Những gì không nên nhầm |
| --- | --- | --- | --- |
| **Checkstyle** | Kiểm tra Java coding conventions, imports, formatting/rules cú pháp | Core plugin `id 'checkstyle'` | Không thay Java compiler hoặc tests |
| **PMD** | Phát hiện code smells, error-prone patterns, maintainability issues | Core plugin `id 'pmd'` | Không mặc định biết mọi bug runtime |
| **SpotBugs** | Phân tích bytecode để tìm bug patterns | Plugin cộng đồng `com.github.spotbugs` với version được pin | Không phải core Gradle plugin; cần cấu hình riêng |
| **JaCoCo** | Thu thập code coverage từ test executions | Core plugin `id 'jacoco'` | Coverage cao không chứng minh logic đúng |
| **SonarQube/SonarCloud** | Tổng hợp nhiều chỉ số và quality gates, có khái niệm new code | Plugin/dịch vụ bên ngoài | Không đồng nhất quality gate server với task `check` |
| **JUnit Jupiter** | Kiểm tra hành vi bằng automated tests | Java `test` task + JUnit dependencies | Test pass không tự chứng minh code tuân coding style |

Một code-quality pipeline thường gồm:

~~~text
Java source changes
       |
       +-- Java compiler -----------------> compileJava
       |
       +-- Checkstyle --------------------> checkstyleMain
       |
       +-- PMD ---------------------------> pmdMain
       |
       +-- Tests -------------------------> test
       |
       +-- Optional coverage/security ----> tool-specific tasks
                                                |
                                                v
                                        CI quality decision
                                                |
                             +------------------+------------------+
                             |                                     |
                        Gate passes                         Gate fails
                             |                                     |
                        Merge eligible                 Fix / explain exception
~~~

Sơ đồ thể hiện các bước **mang tính khái niệm**, không khẳng định mọi plugin tự áp dụng hoặc mọi task đều chạy song song. Theo Gradle Java plugin, `check` là lifecycle task để tập hợp verification; Checkstyle/PMD core plugins gắn các task tương ứng vào `check` khi được áp dụng. Nếu dùng SpotBugs hoặc dịch vụ khác, cần kiểm tra cách plugin cụ thể nối vào task graph.

### 2.1. Checkstyle và PMD có task nào?

Khi áp dụng `java`, `checkstyle` và `pmd`:

~~~groovy
plugins {
    id 'java'
    id 'checkstyle'
    id 'pmd'
}
~~~

thường có các task sau:

| Task | Phạm vi | Quan hệ |
| --- | --- | --- |
| `checkstyleMain` | Java sources thuộc `main` | Checkstyle plugin đăng ký và gắn vào `check` |
| `checkstyleTest` | Java sources thuộc `test` | Tương tự |
| `pmdMain` | Java sources thuộc `main` | PMD plugin đăng ký và gắn vào `check` |
| `pmdTest` | Java sources thuộc `test` | Tương tự |
| `test` | Chạy unit tests | Java plugin gắn vào `check` |
| `check` | Verification lifecycle | Gọi những kiểm tra được nối vào graph |
| `build` | `assemble` + `check` | Build thường có cả packaging và verification |

Checkstyle `checkstyleMain` theo Java plugin phụ thuộc `classes`, `checkstyleTest` phụ thuộc `testClasses`. PMD tasks có mô hình riêng; không tự giả định các mối quan hệ hoàn toàn giống Checkstyle ở mọi version. Hãy xem `./gradlew check --dry-run` trong chính build.

**Không có một tác vụ Gradle core tên `baseline` dùng chung cho tất cả công cụ.** Checkstyle dùng suppression XML; PMD dùng rulesets và suppression/exclusion cơ chế riêng; SpotBugs dùng exclude filter; các hệ thống khác có snapshot, issue history hoặc new-code baseline. Cần xác định chính xác tool và version trước khi thiết kế baseline.

## 3. Cấu hình dùng chung gồm những gì?

Một **quality policy** có thể được biểu diễn như sau:

| Lớp | Dữ liệu nên được chuẩn hóa | Nơi lưu |
| --- | --- | --- |
| Công cụ | Checkstyle/PMD/SpotBugs/plugin versions | Convention plugin hoặc Gradle build configuration |
| Ruleset | Quy tắc nào bật, severity, threshold | `config/checkstyle/checkstyle.xml`, `config/pmd/ruleset.xml` |
| Task wiring | Source sets nào được quét, report formats, failure policy | Convention plugin hoặc shared Gradle logic |
| Ngoại lệ | File/rule được miễn, lý do, owner, issue, kỳ xem xét | `suppressions.xml` hoặc tool-specific config |
| Baseline | Danh mục findings cũ và mốc đo, số lỗi theo rule/module | File quản trị có review hoặc issue tracker |
| CI | Commands thực thi, fail condition, review diff | CI workflow trong Git |
| Review | Ai có quyền approve thay đổi policy và suppression | CODEOWNERS/pull request policy |

**Nguyên tắc:** code và quality configuration cần cùng phiên bản trong Git. Nếu PR thay một rule, mọi người phải thấy rule diff và tác động đến modules trong cùng review. Không dùng một đường dẫn cá nhân trên máy developer làm nguồn mặc định cho ruleset ở CI.

### 3.1. Pin cả phiên bản công cụ và ruleset

Checkstyle/PMD có thể thay đổi default rules hoặc cách phát hiện lỗi qua các releases. Khi tool version trôi độc lập với code và rules, cùng một commit có thể pass hôm nay nhưng fail sau khi CI nâng tool.

Ví dụ Groovy DSL:

~~~groovy
checkstyle {
    toolVersion = '10.24.0'
}

pmd {
    toolVersion = '7.16.0'
}
~~~

Đây là **trích đoạn mở rộng** yêu cầu đã áp dụng hai plugins. Hai version là ví dụ **được chọn có chủ đích** để tương thích Java 17, không phải tuyên bố chúng là bản mới nhất ở mọi thời điểm.

Nên kiểm tra ba thay đổi riêng trong PR update tool:

1. Tool/plugin version thay đổi gì?
2. Rule IDs, messages hoặc engine behavior có đổi?
3. Những findings mới nào do **công cụ mới** phát hiện thay vì do **code mới** gây ra?

Không đổ mọi finding mới cho người sửa code nếu chính policy đã thay. Nhưng cũng không tự động chấp nhận findings mới mà không review mức độ rủi ro.

### 3.2. Quy tắc fail phải rõ ràng

Trong Checkstyle, `ignoreFailures = false` có nghĩa không âm thầm bỏ qua violations. Có thể dùng `maxErrors`/`maxWarnings` để đặt ngưỡng cho reporting level. Không nên đặt `ignoreFailures = true` trên toàn build chỉ để baseline một vài lỗi legacy.

Trong PMD, cũng có `ignoreFailures`. Khi có nhiều tool, phải hiểu **mỗi plugin có failure policy riêng**; đặt nghiêm ở Checkstyle không tự buộc PMD hoặc test coverage tuân cùng quy tắc.

Baseline được thiết kế để quản lý **nợ chất lượng cũ**, chứ không phải tắt khả năng phát hiện và báo lỗi trong code mới.

## 4. Dùng chung file rules qua nhiều modules

Một monorepo Java có thể có cấu trúc:

~~~text
quality-monorepo/
├── settings.gradle
├── build.gradle
├── config/
│   ├── checkstyle/
│   │   ├── checkstyle.xml
│   │   └── suppressions.xml
│   └── pmd/
│       └── ruleset.xml
├── build-logic/
│   ├── build.gradle
│   └── src/main/groovy/
│       └── company.java-quality.gradle
├── app/
│   └── build.gradle
└── library/
    └── build.gradle
~~~

Các file rules được giữ **một bản ở root của repository**. Một convention plugin dùng chung khai báo plugin versions, ruleset location và task policy, rồi mỗi Java module chỉ áp dụng convention plugin tương ứng.

Với Checkstyle, config directory có thể được chỉ định theo root:

~~~groovy
checkstyle {
    toolVersion = '10.24.0'
    configDirectory = rootProject.layout.projectDirectory.dir('config/checkstyle')
    ignoreFailures = false
}
~~~

Checkstyle plugin của Gradle dùng `checkstyle.xml` trong `configDirectory` theo quy ước, đồng thời cung cấp biến `config_loc` để file XML tìm `suppressions.xml` cùng thư mục. Cách này giúp `:app` và `:library` dùng đúng **cùng một ruleset và suppression policy**, không phụ thuộc working directory của mỗi module.

Với PMD, một trích đoạn cấu hình tương ứng:

~~~groovy
pmd {
    toolVersion = '7.16.0'
    consoleOutput = true
    ignoreFailures = false
    ruleSets = []
    ruleSetFiles = files(rootProject.file('config/pmd/ruleset.xml'))
}
~~~

Đây là trích đoạn **khi plugin `pmd` đã được áp dụng**. `ruleSets = []` bỏ các built-in rulesets mặc định nếu muốn chỉ dùng custom ruleset; `ruleSetFiles` trỏ đến file ruleset được version-control. Không paste đoạn này vào dự án chưa có `config/pmd/ruleset.xml`.

### 4.1. Ví dụ ruleset PMD riêng

Một file PMD ruleset tối giản (mẫu cho PMD 7.x):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<ruleset name="Team Java rules"
         xmlns="http://pmd.sourceforge.net/ruleset/2.0.0">
    <description>Common error-prone rules approved by the team.</description>
    <rule ref="category/java/errorprone.xml/EmptyCatchBlock"/>
</ruleset>
~~~

Nếu PMD chạy với ruleset này, nó kiểm tra catch block rỗng trong Java source. PMD rules khác cũng có thể được thêm sau khi thử trên codebase, xem mức độ nhiễu và quyết định scope phù hợp. Đừng giả định XML Checkstyle và XML PMD có chung schema: cùng là XML, nhưng là **hai hệ thống rule khác nhau**.

### 4.2. Nên dùng convention plugin thay vì sao chép block ở mọi module

Sao chép các block `checkstyle { }`/`pmd { }` vào 30 file `build.gradle` gây drift: một module thiếu rule, một module đổi version, một module bật ignore failures. Một **convention plugin** đóng gói thiết lập chung thành một plugin ID và áp dụng ở từng Java project.

Trong Gradle, có thể dùng included build `build-logic` với precompiled script plugins. Ví dụ **kiến trúc multi-project minh họa**, không phải phần runnable single-project ở mục 8:

`settings.gradle` của root:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'quality-monorepo'
include 'app', 'library'
~~~

`build-logic/build.gradle`:

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
}
~~~

`build-logic/src/main/groovy/company.java-quality.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'checkstyle'
    id 'pmd'
}

checkstyle {
    toolVersion = '10.24.0'
    configDirectory = rootProject.layout.projectDirectory.dir('config/checkstyle')
    ignoreFailures = false
}

pmd {
    toolVersion = '7.16.0'
    consoleOutput = true
    ruleSets = []
    ruleSetFiles = files(rootProject.file('config/pmd/ruleset.xml'))
    ignoreFailures = false
}

tasks.withType(Checkstyle).configureEach {
    reports {
        xml.required = true
        html.required = true
    }
}
~~~

`app/build.gradle`:

~~~groovy
plugins {
    id 'company.java-quality'
}

dependencies {
    implementation project(':library')
}
~~~

`library/build.gradle`:

~~~groovy
plugins {
    id 'company.java-quality'
}
~~~

**Giới hạn của ví dụ:** đây là bộ khung convention plugin. Để chạy thành một monorepo thực sự, phải tạo modules `app`/`library` hợp lệ, file PMD/Checkstyle thật, settings cần thiết, Java source và test configuration tương ứng. Phần này minh họa **nơi đặt policy** và **cách apply**, không cam kết một vài snippet riêng lẻ có thể chạy khi thiếu thư mục/file đi kèm.

Lưu ý khi tách convention plugin thành included build: `rootProject` trong script plugin được apply vào một project thuộc **main build** là root của main build đó. Nếu hệ thống áp dụng convention này cho nhiều builds khác nhau, mỗi build cần cung cấp ruleset đúng đường dẫn/quy ước; không nên dùng absolute path của máy tác giả.

### 4.3. Khi nào không dùng `subprojects { }` ở root?

Một lối viết nhanh:

~~~groovy
subprojects {
    apply plugin: 'checkstyle'
}
~~~

không phải lúc nào sai, nhưng **cross-project configuration** có thể làm build logic khó module hóa và kém phù hợp với isolated projects, configuration cache hoặc mô hình build lớn. Với Java modules có policy thống nhất, convention plugin thường rõ ownership, dễ test và dễ áp dụng từng module hơn.

Nếu một module chứa generated Java source hoặc code từ bên thứ ba, không nhất thiết áp cùng mọi quy tắc như source nội bộ; nhưng ngoại lệ cần được mô tả tại policy/convention plugin thay vì âm thầm vô hiệu hóa toàn bộ quality checks.

## 5. Baseline là gì và vì sao không có cờ baseline chung?

**Baseline** là **tập những vấn đề đã tồn tại trước khi bật/siết policy**, được ghi nhận có kiểm soát để đội phát triển có thể:

- Chặn **vi phạm mới** ngay từ hôm nay.
- Vẫn build được khi code legacy có những vi phạm đã được phân loại.
- Nhìn thấy số lượng nợ chất lượng cũ thay vì giấu nó.
- Thu hẹp số lượng/độ rộng ngoại lệ theo từng sprint.
- Chuyển dần sang kiểm tra strict toàn bộ codebase.

Nhưng các tools khác nhau có khả năng khác nhau:

| Công cụ | Có sẵn một file baseline thống nhất của Gradle không? | Cách triển khai có thể |
| --- | --- | --- |
| Checkstyle | **Không** có baseline universal do Gradle cung cấp | Snapshot XML reports và suppression XML scoped |
| PMD | **Không** có cờ Gradle `--baseline` dùng chung | Snapshot reports, rule exclusions hoặc PMD-specific suppressions; có thể dùng job so sánh delta |
| SpotBugs | Không có cùng cơ chế với Checkstyle | Exclude filter và reports của plugin cụ thể |
| SonarQube/SonarCloud | Dịch vụ có khái niệm new-code period/gate | Cấu hình trên dịch vụ theo project/branch |
| JaCoCo | Coverage metric khác violation list | Threshold có lý do hoặc target tăng dần; task verification cần được nối phù hợp |

Không được trình bày `--baseline` hoặc `baselineFile` như một API chung của `checkstyle` và `pmd` Gradle core plugins. Phải đọc tài liệu tool thực tế trước khi dùng một tính năng baseline.

### 5.1. Quy trình tạo baseline lần đầu

Ví dụ một Java repository đã có 700 Checkstyle findings. Quy trình an toàn:

1. **Pin Checkstyle version và ruleset** để phép đo có thể lặp lại.
2. Chạy phân tích trên một commit xác định, lưu XML/HTML reports cùng commit SHA, tool version, ruleset hash/phiên bản và scope của modules.
3. Phân loại findings: lỗi quan trọng cần sửa ngay, lỗi có thể sửa tự động, lỗi legacy tạm chấp nhận.
4. Tạo danh mục baseline những findings tạm chấp nhận, gắn issue, owner và mục tiêu xử lý.
5. Chỉ tạo suppression/exclusion thật sự cần để **giữ strict gate cho lỗi mới**.
6. Chạy strict check sau khi baseline đã tạo; đảm bảo code mới không được che bởi ngoại lệ quá rộng.
7. Review baseline theo lịch, xóa ngoại lệ ngay khi vấn đề được sửa.

Một bảng baseline **minh họa**:

| Module/file | Rule | Findings ban đầu | Owner | Issue | Kỳ xem lại |
| --- | --- | ---: | --- | --- | --- |
| `:legacy:src/main/java/demo/legacy/LegacyAdapter.java` | `AvoidStarImport` | 1 | Team Legacy | `QUAL-142` | 2027-03-31 |
| `:backend:.../OldParser.java` | `EmptyBlock` | 2 | Team Backend | `QUAL-193` | 2027-02-28 |

Những tên/issue/ngày trên chỉ là **ví dụ minh họa policy**, không phải dữ liệu nội bộ hay ticket có thật. Trong repository thực tế, baseline phải dựa trên reports được tạo và kiểm chứng trên đúng commit.

### 5.2. Baseline khác suppression

- **Baseline** là thông tin về **những lỗi đã tồn tại**, có thể lưu ở báo cáo/CSV/issue tracker. Mục tiêu là quan sát và quản lý nợ kỹ thuật.
- **Suppression** là rule kỹ thuật **không phát ra/fail một tập violations khớp điều kiện**. Nó có thể làm findings bị ẩn khỏi report.
- **Exclusion** bỏ qua một số source files/package/task hoặc rules.
- **Quality gate** quyết định build/PR có pass không theo rule và tiêu chí tổ chức.

Không có bảo đảm “tôi đã tạo file baseline” sẽ tự làm Checkstyle chấp nhận violations. Ngược lại, nếu bạn suppress cả package, công cụ có thể không còn quan sát các lỗi mới trong package đó. Vì vậy baseline nên **độc lập** với thông số suppression và có phép đo định kỳ để biết debt còn bao nhiêu.

### 5.3. Khi nào chấp nhận baseline?

Thường phù hợp khi đang áp dụng công cụ mới vào **legacy codebase lớn**, và việc sửa toàn bộ findings ngay lập tức có chi phí/rủi ro cao. Baseline phải có kế hoạch giảm dần.

Không nên baseline một lỗi nghiêm trọng mới xuất hiện chỉ vì “build đang đỏ”, nhất là lỗi có thể gây rò rỉ dữ liệu, unsafe deserialization, lỗi bảo mật hoặc API behavior nguy hiểm. Những trường hợp rủi ro cao nên có đánh giá/exception approval nghiêm ngặt hơn theo policy bảo mật.

### 5.4. Baseline nên được đối chiếu thế nào?

Một số cách:

- **Diff theo identities ổn định**: tool, rule ID, file path, vị trí gần đúng, hoặc fingerprint do analyzer phát ra. Chú ý line number có thể trôi khi thêm code.
- **Per-rule/per-module budget**: số findings mới không vượt mức baseline; phải lưu baseline theo từng rule/module để tránh lỗi nghiêm trọng mới được “bù” bằng việc sửa lỗi nhẹ khác.
- **Scope theo new/changed code**: PR gate kiểm tra chặt file/hunk mới, đồng thời job định kỳ phân tích toàn repo để tránh nợ tăng ở files khác.
- **Suppression theo file/rule**: phù hợp một số legacy findings, nhưng thường che cả violations mới cùng rule trong cùng file; cần kết hợp review và kế hoạch loại bỏ.

Một phép so sánh thô `totalViolations <= baselineCount` có lỗ hổng: bạn có thể sửa 5 lỗi định dạng nhưng thêm 5 bug patterns mới và tổng vẫn không đổi. Do đó cần kiểm **delta theo mức độ/rule/identity**, không chỉ so một số tổng.

## 6. Ngoại lệ có giải thích: quy tắc bắt buộc

Mỗi ngoại lệ cần trả lời:

1. **Áp vào đâu?** Module, file, package, rule ID, và nếu tool hỗ trợ thì dòng/ID chính xác.
2. **Vì sao?** Chẳng hạn legacy protocol, generated code, API compatibility, false positive đã xác minh.
3. **Ai chịu trách nhiệm?** Người/nhóm ownership rõ ràng.
4. **Có bằng chứng không?** Link issue/PR, phân tích false positive, report mẫu.
5. **Bao giờ xem lại?** Kỳ hạn review hoặc điều kiện xóa suppression.
6. **Rủi ro là gì?** Lỗi mới nào sẽ có thể bị che bởi suppression.
7. **Điều kiện đóng ngoại lệ?** Refactor hoàn thành, upstream analyzer fix hoặc generated code chuyển scope.

Một lý do kiểu “CI đỏ, bỏ qua” không đủ. Một exception thiếu owner và không có review date thường biến thành nợ kỹ thuật vô hạn.

### 6.1. Thứ tự xử lý trước khi suppress

Thường nên ưu tiên:

1. **Sửa code** nếu lỗi thực, dễ sửa và rủi ro thấp.
2. **Điều chỉnh rule configuration** nếu chính sách chung thật sự sai cho cả codebase.
3. **Xác minh false positive** bằng example cụ thể, tool version/changelog.
4. **Scope ngoại lệ tối thiểu**: một rule/file/line thay vì toàn project.
5. **Đưa về baseline có kiểm soát** khi nợ cũ chưa thể xử lý ngay.
6. **Đặt lịch loại bỏ ngoại lệ**, kiểm tra lại sau khi tool upgrade hoặc code refactor.

Không dùng `ignoreFailures = true` hoặc `exclude '**/*.java'` để thay cho một suppression đúng scope.

### 6.2. Những kiểu ngoại lệ dễ gây rủi ro

| Cách làm | Rủi ro | Phương án tốt hơn |
| --- | --- | --- |
| Disable `checkstyleMain` toàn module | Code mới không được kiểm tra | File/rule-scoped suppression |
| `ignoreFailures = true` mọi modules | Gate fail-open | Strict gate và exception được review |
| Suppress toàn bộ `.*` rules | Che mọi violation | Chỉ rule thực sự có false positive/legacy debt |
| Suppress cả package lớn | Lỗi mới trong package được che | Giảm scope theo file hoặc vị trí |
| Dựa vào số dòng cứng | Chèn vài dòng làm suppression lệch | Stable identifier/path hoặc review khi line changes |
| Không có thời hạn | Nợ tồn tại mãi | Review date và owner |
| Chỉ dùng tổng số violation | Một lỗi mới có thể được bù bằng lỗi đã sửa | Delta theo rule/severity/fingerprint |
| Không lưu config trong Git | Máy dev và CI khác policy | Version control và code review |

## 7. Checkstyle suppression XML: một baseline kỹ thuật có giới hạn

Gradle Checkstyle plugin sử dụng Checkstyle config ở `config/checkstyle/checkstyle.xml` và có thể tham chiếu file `suppressions.xml` bằng biến **`config_loc`**.

Một `SuppressionFilter` hoạt động bằng cách loại bỏ Checkstyle audit events khớp thuộc tính của `suppress`, ví dụ `files`, `checks`, `lines`, `columns` hoặc `id`. Không nhất thiết phải khai hết thuộc tính; càng ít điều kiện thì suppression thường càng rộng.

**Điều quan trọng:** Checkstyle suppression XML không tự chứa các trường nghiệp vụ “owner”, “issue”, “expiry” dưới dạng attributes chuẩn. Nếu muốn lưu giải thích, hãy dùng **XML comment** và issue tracker/baseline inventory; không tự thêm attributes tùy ý vào `suppress` rồi hy vọng Checkstyle hiểu.

### 7.1. Cấu hình Checkstyle minh họa

`config/checkstyle/checkstyle.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <property name="charset" value="UTF-8"/>

    <module name="SuppressionFilter">
        <property name="file" value="${config_loc}/suppressions.xml"/>
        <property name="optional" value="false"/>
    </module>

    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
        <module name="UnusedImports"/>
    </module>
</module>
~~~

Khi nạp qua Gradle Checkstyle plugin, `${config_loc}` trong ví dụ trên được hiểu là **biến cấu hình Checkstyle có ký hiệu dollar-braces** (sẽ được thể hiện đúng ở Markdown được lưu). `optional=false` có chủ đích: nếu file suppression bị thiếu, check phải báo lỗi thay vì âm thầm bỏ qua rule filter.

`AvoidStarImport` phát hiện Java wildcard import như `import java.util.*;`. `UnusedImports` phát hiện import không sử dụng theo rule của Checkstyle. Đây là ruleset nhỏ để làm thí nghiệm; project thật thường cần nhiều rules hơn sau khi thảo luận và kiểm chứng.

### 7.2. File suppression thật

`config/checkstyle/suppressions.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE suppressions PUBLIC
    "-//Checkstyle//DTD SuppressionFilter Configuration 1.2//EN"
    "https://checkstyle.org/dtds/suppressions_1_2.dtd">
<suppressions>
    <!-- Legacy baseline: AvoidStarImport in LegacyAdapter.java only.
         Reason: adapter maintained for an older integration;
         Owner: Team Legacy; Issue: QUAL-142 (illustrative);
         Review by: 2027-03-31.
         Remove when wildcard import is replaced. -->
    <suppress files=".*LegacyAdapter[.]java"
              checks="AvoidStarImport"/>
</suppressions>
~~~

Rule này chỉ loại bỏ `AvoidStarImport` findings ở file có basename `LegacyAdapter.java` khớp regex. Nó **không loại bỏ** `UnusedImports` ở file đó và không cho phép wildcard imports ở files khác.

**Giới hạn quan trọng:** vì regex được thiết kế theo basename, một module khác cũng có tên `LegacyAdapter.java` có thể khớp khi được Checkstyle quét với cùng policy. Trong monorepo, nên cân nhắc regex khớp đường dẫn package/module chính xác hơn, hoặc đặt exclusions theo task/module với review, để không vô tình mở ngoại lệ cho file khác. XML comment cung cấp lý do nhưng Checkstyle **không tự hết hạn** suppression khi tới review date; CI/owner phải kiểm và xóa.

### 7.3. Tránh suppression dựa vào message locale

Checkstyle `SuppressionFilter` có thể lọc theo `message`, nhưng message thường phụ thuộc ngôn ngữ runtime/phiên bản tool. Khi có thể, dùng **rule ID/check name** và file scope ổn định hơn. Với suppression theo `lines`, chú ý chỉ cần chèn một đoạn code trước đó là số dòng có thể lệch; cần kiểm lại sau refactor.

### 7.4. Vì sao suppression không phải baseline hoàn hảo?

Khi `AvoidStarImport` được suppress toàn file legacy, **một wildcard import mới trong cùng file cũng có thể bị che**. Baseline lý tưởng chỉ chấp nhận các **findings cũ đã ghi nhận**, không chấp nhận findings mới. Do đó:

- Không mở scope lớn hơn cần thiết.
- Dùng review file diff và bot/CI chuyên biệt nếu cần so exact findings.
- Theo dõi một inventory riêng; so raw reports định kỳ khi giảm debt.
- Khi có thể, sửa violation cũ thay vì giữ exception.
- Không tự động thêm mọi finding mới vào suppression sau mỗi build đỏ.

## 8. Demo hoàn chỉnh Java 17 + Checkstyle + documented exception

Đây là project nhỏ **chạy được** khi đã có Gradle Wrapper thật, JDK 17 phù hợp và truy cập Maven Central (cho Checkstyle/JUnit dependencies khi chưa cached). Demo có **một lỗi legacy có chủ đích**, được suppress theo rule/file, và một class main/test hoàn toàn bình thường.

### 8.1. Cây thư mục

~~~text
quality-baseline-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── config/
│   └── checkstyle/
│       ├── checkstyle.xml
│       └── suppressions.xml
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           ├── QualityApp.java
    │           └── legacy/
    │               └── LegacyAdapter.java
    └── test/
        └── java/
            └── demo/
                └── QualityAppTest.java
~~~

Các file Wrapper không thể thay bằng placeholder; chúng phải là Gradle Wrapper distribution scripts/JAR/properties hợp lệ. Ví dụ dùng Java toolchain 17 và Checkstyle 10.24.0; các phiên bản được nêu là **phiên bản mục tiêu đã chọn**, không phải công bố latest.

### 8.2. `settings.gradle`

~~~groovy
rootProject.name = 'quality-baseline-demo'
~~~

### 8.3. `build.gradle` hoàn chỉnh

~~~groovy
plugins {
    id 'java'
    id 'checkstyle'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

checkstyle {
    toolVersion = '10.24.0'
    configDirectory = layout.projectDirectory.dir('config/checkstyle')
    ignoreFailures = false
    maxErrors = 0
}

tasks.withType(Checkstyle).configureEach {
    reports {
        xml.required = true
        html.required = true
    }
}
~~~

Từng khối có vai trò khác nhau:

- `java` tạo source sets và Java compile/test lifecycle.
- `checkstyle` đăng ký `checkstyleMain`/`checkstyleTest`, và bổ sung chúng vào `check`.
- `testImplementation`/`testRuntimeOnly` chỉ dành cho JUnit test runtime, không đưa JUnit vào production JAR.
- `java.toolchain` yêu cầu JDK 17 cho các Java tasks thích hợp; Checkstyle cũng có cơ chế chọn JVM/toolchain của Gradle plugin tương ứng.
- `checkstyle.toolVersion` pin Checkstyle engine.
- `configDirectory` chỉ đến rules/suppressions lưu trong Git.
- `ignoreFailures = false` và `maxErrors = 0` yêu cầu lỗi quality không bị lờ đi.
- Báo cáo XML và HTML thuận tiện cho CI và người review.

**Không kết hợp `ignoreFailures=true` để làm baseline.** Demo sẽ pass vì **duy nhất lỗi được chấp nhận đã có suppression có scope**, không phải vì tắt quality gate.

### 8.4. `config/checkstyle/checkstyle.xml`

Dùng chính nội dung ở mục 7.1, với biến `config_loc` chuẩn của Checkstyle Gradle plugin. Dù file chính có thuộc tính XML và DTD, người học không cần khai báo một task Groovy mới để nạp file; Checkstyle Gradle plugin nhận diện `checkstyle.xml` từ `configDirectory`.

### 8.5. `config/checkstyle/suppressions.xml`

Dùng nội dung mục 7.2. Rule dành cho `LegacyAdapter.java` được review theo mẫu issue/owner/review date. Nếu xóa entry `<suppress .../>` mà không sửa legacy code, `checkstyleMain` sẽ phát hiện `AvoidStarImport` và fail. Đó là cách xác nhận tool đang thực sự kiểm tra, không phải được tắt toàn cục.

### 8.6. `src/main/java/demo/legacy/LegacyAdapter.java`

~~~java
package demo.legacy;

import java.util.*;

public final class LegacyAdapter {
    private LegacyAdapter() {
    }

    public static int count() {
        return List.of("alpha", "beta").size();
    }
}
~~~

Đây là Java 17 code hợp lệ: `List.of` tạo list hai phần tử và `count()` trả `2`. Nhưng `import java.util.*;` vi phạm rule `AvoidStarImport`.

**Vì sao chấp nhận tạm thời?** Trong demo, ta mô phỏng một file legacy được tổ chức quản lý. Khi học xong, nên sửa thành `import java.util.List;` và **xóa suppression**, bởi đây là việc đơn giản và có rủi ro thấp. Không lấy ví dụ này làm lý do giữ wildcard import trong production vĩnh viễn.

### 8.7. `src/main/java/demo/QualityApp.java`

~~~java
package demo;

import demo.legacy.LegacyAdapter;

public final class QualityApp {
    private QualityApp() {
    }

    public static void main(String[] args) {
        System.out.println("quality-ok:" + LegacyAdapter.count());
    }
}
~~~

Class này import đúng loại, không vi phạm hai rules của demo. Stdout của `main` là một dòng xác định: `quality-ok:2`. Không cần Maven runtime library để chạy class chính, vì nó chỉ dùng Java standard library và `LegacyAdapter`.

### 8.8. `src/test/java/demo/QualityAppTest.java`

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import demo.legacy.LegacyAdapter;
import org.junit.jupiter.api.Test;

class QualityAppTest {
    @Test
    void countsTwoItems() {
        assertEquals(2, LegacyAdapter.count());
    }
}
~~~

`QualityAppTest` là test JUnit Jupiter hoàn chỉnh; `compileTestJava` cần JUnit API và compiled `LegacyAdapter`. `test` mới thực thi `@Test`. Checkstyle `checkstyleTest` cũng sẽ quét Java test source khi Checkstyle plugin được bật.

### 8.9. Các lệnh thực hiện

Linux/macOS:

~~~bash
./gradlew --version
./gradlew checkstyleMain
./gradlew checkstyleTest
./gradlew test
./gradlew check
./gradlew build
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat checkstyleMain
.\gradlew.bat test
.\gradlew.bat check
~~~

Với đủ 5 file config/source/test trong demo và Checkstyle/JUnit downloads thành công, các checks sẽ pass nhờ suppression **chỉ** cho violation trong `LegacyAdapter.java`. Đây là ví dụ học tập: kết quả cụ thể phụ thuộc việc bạn có tạo đúng các file và không thêm source vi phạm khác.

**`check` kéo tasks quality vào graph** theo plugin; `build` kéo `assemble` và `check`. `checkstyleMain` là Checkstyle analysis cho main sources, không chạy JUnit. `test` chạy JUnit, không thay thế Checkstyle.

### 8.10. Chạy Java main và kiểm stdout

Sau khi compiled classes sẵn:

~~~bash
./gradlew classes
java -cp build/classes/java/main demo.QualityApp
~~~

Stdout chính xác:

~~~text
quality-ok:2
~~~

Có thể thử Java 17 độc lập, vì hai main classes không cần thư viện thứ ba:

~~~bash
javac -encoding UTF-8 -d out \
    src/main/java/demo/legacy/LegacyAdapter.java \
    src/main/java/demo/QualityApp.java
java -cp out demo.QualityApp
~~~

Trên Unix shell, `\` cuối dòng trong command là continuation; nếu dùng Windows PowerShell, có thể đặt `javac` và hai file arguments trên một dòng rồi gọi `java -cp out demo.QualityApp`.

Output vẫn là `quality-ok:2`. Lệnh `javac` **không chạy Checkstyle**. Đây là điểm học tập quan trọng: mã có wildcard import vẫn biên dịch được, nhưng quality gate có thể coi nó là violation.

### 8.11. Reports ở đâu?

Với Gradle Checkstyle plugin và report configuration trên:

~~~text
build/
├── reports/
│   └── checkstyle/
│       ├── main.xml
│       ├── main.html
│       ├── test.xml
│       └── test.html
└── classes/
    └── java/
        ├── main/
        └── test/
~~~

Tên/thư mục report phụ thuộc Gradle version/report settings, nhưng `build/reports/checkstyle` là convention thông dụng. Báo cáo sau suppression thường **không còn hiển thị violations đã bị filter**. Nếu cần đánh giá lượng nợ legacy thực tế, phải lưu baseline inventory hoặc thực hiện **raw scan có kiểm soát** mà không dùng suppression rồi lưu report riêng.

### 8.12. Chứng minh gate bắt lỗi mới

Tạo thêm **file mới, không nằm trong suppression scope**:

`src/main/java/demo/NewCode.java`:

~~~java
package demo;

import java.util.*;

public final class NewCode {
    private NewCode() {
    }

    public static List<String> names() {
        return List.of("new");
    }
}
~~~

Lệnh:

~~~bash
./gradlew checkstyleMain
~~~

sẽ báo `AvoidStarImport` cho `NewCode.java` vì suppression chỉ khớp `LegacyAdapter.java`. Build có thể fail, báo cáo chỉ rõ file/rule. Đây là dấu hiệu gate đang hoạt động cho code mới.

Sửa đúng cách:

~~~java
package demo;

import java.util.List;

public final class NewCode {
    private NewCode() {
    }

    public static List<String> names() {
        return List.of("new");
    }
}
~~~

Chạy lại `./gradlew checkstyleMain` để xác nhận violation mới được giải quyết. **Không thêm `NewCode.java` vào suppression** chỉ để đạt trạng thái xanh.

### 8.13. Thu hẹp và xóa baseline legacy

Sau khi cả nhóm đồng ý sửa file legacy, thay:

~~~java
import java.util.*;
~~~

bằng:

~~~java
import java.util.List;
~~~

Sau đó **xóa entry `<suppress files=".*LegacyAdapter[.]java" .../>`** khỏi `suppressions.xml`, giữ nguyên file XML hợp lệ và chạy:

~~~bash
./gradlew clean check
~~~

Nếu project chỉ còn những file code sạch, Checkstyle và tests sẽ pass. Đây là **thước đo tiến bộ thực**: một ngoại lệ đã bị xóa, chứ không phải chỉ giảm số lỗi bằng cách mở rộng suppressions.

## 9. Chia sẻ chính sách Checkstyle/PMD qua build-logic trong Git

Trong project lớn, convention plugin là một cách tránh lặp code và đảm bảo các modules cùng được review. Những file nên commit:

- `build-logic/src/main/groovy/company.java-quality.gradle`: tool versions, plugin application, shared reports, gate behavior.
- `config/checkstyle/checkstyle.xml` và `config/checkstyle/suppressions.xml`.
- `config/pmd/ruleset.xml`, nếu dùng PMD.
- Quality baseline inventory (nếu chính sách yêu cầu lưu tại Git).
- CI workflow và CODEOWNERS/review policy.
- Gradle Wrapper để dev/CI dùng Gradle distribution nhất quán.

Những thứ **không nên commit**: `.gradle/`, `build/`, downloaded analyzer JARs, local reports tùy máy, credentials, private tokens.

### 9.1. Tránh lệch policy giữa main và test sources

Nếu tổ chức muốn Checkstyle quét cả tests, nên chạy cả `checkstyleMain`/`checkstyleTest` trong CI, hoặc gọi `check` đã được gắn đúng tasks. Không mặc định disable `checkstyleTest` vì “test code ít quan trọng”. Nhưng nếu một số generated sources hoặc framework fixtures có coding conventions riêng, ghi rõ exceptions theo scope/rules.

### 9.2. Không bắt mọi module giống nhau bất kể mục đích

Shared policy không có nghĩa cấm tùy chỉnh. Ví dụ:

- Module Java library có public API nghiêm khắc hơn internal tooling.
- Generated Java source cần scope riêng hoặc không được sửa tay; loại trừ generated directory được tạo có kiểm soát.
- Ứng dụng legacy có baseline riêng, trong khi module mới strict hoàn toàn.
- Test fixtures có rule khác khi có lý do chính đáng.

Giải pháp là **convention variants** hoặc policy override được review, không phải để mỗi module tự ý copy rồi chỉnh file ruleset kín đáo.

## 10. CI và pull request: thực thi chính sách mới

Một CI job đơn giản dùng Wrapper:

~~~bash
./gradlew --version
./gradlew check
./gradlew build
~~~

Trong Java project có Checkstyle và PMD, `check` có thể chạy quality tasks, tests và verification tasks khác đã được nối. `build` đã phụ thuộc `check`, nên nếu chỉ muốn một lệnh đầy đủ thường có thể dùng `./gradlew build`. Gọi cả hai ở ví dụ trên là để thấy hai mục tiêu; Gradle sẽ tránh làm lại task outputs phù hợp.

**Không nên biến CI thành chỉ chạy `compileJava`:** compiler có thể chấp nhận code vi phạm Checkstyle/PMD. Cũng không mặc định `./gradlew test` thay `check`, bởi tests xác minh hành vi chứ không chạy mọi static analysis tool.

### 10.1. Một pull request thay policy cần những gì?

Người review nên thấy:

1. Tool version cũ và mới, lý do nâng.
2. Ruleset diff: rule nào bật/tắt, severity thay đổi ra sao.
3. Trích report trước/sau, số findings theo module/rule.
4. Baseline entries thêm/xóa và vì sao.
5. Ngoại lệ mới có **owner, issue, review date và phạm vi nhỏ**.
6. Tests/quality tasks được chạy trên CI và Gradle version nào.
7. Tác động tới developers: có cần autoformatter, IDE config, compiler upgrade hoặc migration?
8. Kế hoạch rollback nếu ruleset mới gây false positive trên quy mô lớn.

Nếu PR chỉ chỉnh logic sản phẩm nhưng thêm suppression không liên quan, nên yêu cầu giải thích riêng hoặc tách PR policy để review minh bạch.

### 10.2. Review tác động trên code mới và code cũ

Một mô hình vận hành thực tế:

| Loại code/finding | Quy tắc mặc định | Ngoại lệ có thể xét |
| --- | --- | --- |
| Java file mới | Quality gate nghiêm | False positive thật sự, có bằng chứng |
| Java file đã sửa | Không tạo thêm vi phạm; ưu tiên sửa cả đoạn liên quan | Legacy debt ngoài phạm vi được ghi nhận rõ |
| Legacy file không sửa | Chấp nhận đúng baseline đã review | Theo lịch giảm nợ và kiểm định định kỳ |
| Generated code | Không bắt buộc cùng formatting rules | Cần quy tắc generated scope, owner và tooling |
| Security-critical finding | Ưu tiên sửa/đánh giá ngay | Chỉ qua quy trình exception bảo mật riêng |

Đừng giả định mọi công cụ tự nhận biết “new lines” hay “new issues”. CI hoặc dịch vụ phân tích cần cơ chế tính diff/new-code riêng; Checkstyle suppression XML chỉ dựa trên những điều kiện matching của Checkstyle.

### 10.3. Tránh fail-open trong CI

Một số anti-pattern:

~~~groovy
// Chỉ minh họa các cấu hình KHÔNG nên dùng làm chính sách chung:
checkstyle {
    ignoreFailures = true
}
pmd {
    ignoreFailures = true
}
~~~

Hoặc:

~~~bash
# Không phù hợp để xác nhận quality gate:
./gradlew build -x checkstyleMain -x checkstyleTest
~~~

Các cách đó có thể làm pipeline xanh trong khi findings không được xử lý. Khi tool có false positives, hãy sửa rule hoặc thêm exception có review thay vì mặc định bỏ qua toàn bộ tasks.

## 11. Theo dõi baseline như một chỉ số kỹ thuật có thể hành động

Một inventory có thể ghi:

~~~text
Policy version: 2026.11
Analyzer: Checkstyle 10.24.0
Ruleset: config/checkstyle/checkstyle.xml
Scope: Java main and test sources
Baseline commit: <commit SHA được lấy từ repository thực>
Owner: Code Quality Team
Review cadence: monthly
~~~

Các giá trị trên **minh họa cấu trúc ghi chép**, không phải dữ liệu thật của một repository cụ thể. Trong quy trình thực, thay commit SHA bằng giá trị từ Git, không để placeholder trong file được phê duyệt.

Một bảng theo dõi công nợ:

| Thời điểm | Baseline đang còn | Lỗi mới bị chặn | Ngoại lệ đã xóa |
| --- | ---: | ---: | ---: |
| Lần khởi tạo | 120 | 0 | 0 |
| Review 1 | 100 | 3 | 4 |
| Review 2 | 74 | 2 | 6 |

Đây là **số liệu minh họa**, không phải metric thực của dự án. Đánh giá tiến bộ theo chất lượng lỗi, scope và remediation, không chạy theo số lượng đơn thuần. Xóa một suppression nhưng di chuyển nó sang rule global disable **không phải** cải thiện chất lượng.

### 11.1. Khi số lượng baseline tăng bất ngờ

Hãy hỏi:

- Tool version hoặc ruleset có vừa đổi không?
- Scan scope có mở rộng sang test/generated sources?
- Có module mới được thêm vào monorepo?
- Có duplicate findings do cách thu thập report?
- Có violation mới thực sự chưa được chặn?
- Có exception đã hết hạn hoặc không còn phù hợp?
- CI có thực sự chạy `check` hay đã vô tình bỏ qua `checkstyleMain`/`pmdMain`?

Không tự chốt “nợ tăng do developer viết code kém” khi nguyên nhân có thể là thay đổi độ nhạy của analyzer hoặc phạm vi quét.

### 11.2. “Fail on new issues” cần xác định danh tính issue

Nếu chỉ so raw số lượng, bạn có thể xóa hai issues cũ nhưng thêm hai issues mới. Tổng bằng nhau không chứng minh compliance. Một gate dựa vào new findings cần ít nhất danh tính theo **tool + rule + file + fingerprint/vị trí ổn định**, xử lý việc line numbers thay đổi, renamed files và analyzer version changes.

Với những tool không có fingerprint ổn định, có thể dùng quy trình kiểm thận trọng: report diff kèm manual review khi đổi file/path, và kết hợp strict rule scope cho code mới. Đừng tự quảng cáo một script `count(findings) <= baseline` là giải pháp toàn diện.

## 12. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `checkstyleMain` không tồn tại | Chưa áp dụng `checkstyle` trong module Java | Kiểm plugin scope và `tasks --all` |
| `check` không chạy Checkstyle | Plugin chưa apply hoặc tasks bị disable/exclude | Kiểm `check --dry-run` |
| Rule XML không được nạp | Sai `configDirectory`/`checkstyle.xml` | Kiểm paths từ root và file có trong Git |
| `suppressions.xml` không được tìm thấy | `config_loc` hoặc file path sai | Dùng built-in variable và `optional=false` |
| Suppression không có hiệu lực | Regex `files`/`checks` không khớp event | Xem report rule ID và actual file path |
| Suppression che quá nhiều lỗi | Regex quá rộng hoặc `checks=".*"` | Thu hẹp file/rule; kiểm new-code gate |
| Violation mới trong file legacy không bị bắt | File-level suppression che cùng rule | Dùng detailed report comparison/review hoặc sửa debt cũ |
| Tool upgrade làm hàng loạt violations đổi | New rules/semantics/Java support | Pin version, tạo impact report rồi approve change |
| PMD không thấy ruleset | `ruleSetFiles` path sai | Trỏ đến root config file và kiểm tồn tại |
| PMD chạy nhưng không report rule muốn thấy | `ruleSets`/`ruleSetFiles` hoặc priority config chưa đúng | Kiểm applied rules và PMD version |
| Checkstyle fail do DTD/config parse | XML invalid, DTD/module name sai, load policy | Kiểm XML và Checkstyle docs, không bật external DTD tùy tiện |
| Gradle không tải được tool | Offline cache chưa có, repository/credentials thiếu | Chuẩn bị cache hoặc dùng repository có quyền |
| Java 17 code compile nhưng Checkstyle fail startup | Analyzer version cần JDK khác JVM chạy task | Chọn compatible toolVersion/javaLauncher |
| `ignoreFailures=true` khiến PR pass dù lỗi | Fail-open policy | Chuyển strict, tạo exception thật sự |
| Build pass trên máy dev nhưng CI fail | Khác Wrapper/tool versions/ruleset/JDK | Pin versions và commit config |
| Generated sources có nhiều false positives | Plugin quét generated directories | Tách source set/exclude scope có review |
| Checkstyle report rỗng sau suppress | Audit events bị filter khỏi report | Giữ baseline inventory và raw scans định kỳ |
| `build` xanh nhưng coverage chưa được kiểm | `jacocoTestCoverageVerification` chưa wire vào `check` | Thiết kế coverage gate và task dependency cụ thể |
| Lỗi security mới bị baseline hóa | Quy trình không phân cấp mức rủi ro | Yêu cầu security review riêng, đừng auto-suppress |

### 12.1. Chuỗi chẩn đoán gợi ý

~~~text
Tool/plugin đã apply đúng module?
            |
            v
Gradle tasks --all / check --dry-run có quality tasks?
            |
            v
ToolVersion/ruleset/configDirectory đúng?
            |
            v
Report cho biết file/rule/violation gì?
            |
            v
Violation là lỗi mới, nợ cũ hay false positive?
            |
            v
Có baseline/exception scope và owner hợp lệ?
            |
            v
Sửa code / rule / suppression tối thiểu
            |
            v
Chạy lại check và review Git diff + CI
~~~

Đừng xóa toàn bộ `~/.gradle` khi Checkstyle báo vi phạm kiểu import. Dependency cache không phải nguyên nhân gốc của một rule violation hợp lệ.

## 13. Bài tập có đáp án gợi ý

### Bài A — baseline khác suppression

**Câu hỏi:** baseline có tự làm Checkstyle pass không? **Không.** Baseline là inventory của findings cũ; muốn Gradle strict gate pass khi còn violations cũ cần cơ chế hỗ trợ như narrowly scoped suppression hoặc new-issue comparison gate. Suppression có thể che findings khỏi report, nên baseline inventory vẫn cần được quản lý riêng.

### Bài B — người mới viết wildcard import

Thêm `src/main/java/demo/NewCode.java` với `import java.util.*;`. Với suppression chỉ nhắm `LegacyAdapter.java`, `checkstyleMain` phải báo `AvoidStarImport`. Sửa thành `import java.util.List;`; không mở rộng suppression sang file mới.

### Bài C — sao không dùng `ignoreFailures=true`?

Vì nó cho phép build tiếp tục khi analyzer phát hiện violations, làm CI khó phân biệt baseline cũ và lỗi mới. Chọn strict gate cộng exception có reason/owner/review date.

### Bài D — Checkstyle 10.24.0 có phù hợp Java 17?

Đây là một phiên bản có thể dùng trong demo Java 17. Tuy nhiên phiên bản Checkstyle mới hơn có thể đòi JDK cao hơn; khi nâng tool, đọc requirement của chính version đó và chọn Java launcher/toolchain tương ứng. Đừng suy JDK của compiler luôn giống JVM chạy analyzer.

### Bài E — ngoại lệ nào đáng review?

Một suppression chỉ có `files=".*" checks=".*"` **không đủ**. Nó che mọi lỗi. Một ngoại lệ tốt chỉ nhắm `LegacyAdapter.java` và `AvoidStarImport`, có comment và issue/owner/review date, đồng thời có kế hoạch xóa.

### Bài F — tên file trùng ở hai module

Với regex `.*LegacyAdapter[.]java`, file trùng basename ở module khác cũng có thể bị suppress. Giải pháp là tăng độ chính xác của regex dựa trên package/path, đặt suppression trong scope module thích hợp hoặc chuyển sang mechanism theo ID/line khi ổn định.

### Bài G — Checkstyle và PMD có chung baseline flag?

Không. Đây là hai engines với rulesets, reports, exception capabilities khác nhau. Gradle core plugins không cung cấp một cờ `--baseline` dùng chung cho cả hai. Muốn chung policy, xây inventory/report comparison và cấu hình riêng từng tool.

### Bài H — vì sao convention plugin hữu ích?

Nó gom Checkstyle/PMD versions, ruleset locations, failure policy và reports vào một nơi, áp dụng thống nhất cho modules. Khi thay rule, một PR có thể review tác động toàn repo. Nếu dùng snippets lặp lại ở nhiều modules, drift dễ xuất hiện.

### Bài I — sửa nợ legacy

Sửa `LegacyAdapter.java` từ wildcard import thành `java.util.List`. Sau đó xóa entry suppression, chạy `./gradlew check`. Baseline debt giảm mà không làm gate yếu đi.

### Bài J — gate “tổng violation không tăng” có đủ?

Không. Nếu sửa một lỗi nhẹ và thêm một lỗi nặng, tổng vẫn bằng nhau. Nên so delta theo rule/severity/file/fingerprint và review code mới, không chỉ số tổng.

## 14. Checklist áp dụng cho dự án thực tế

1. Đã phân biệt **shared quality policy**, **baseline** và **exception**?
2. Checkstyle/PMD/SpotBugs versions có được pin và được test với JDK/toolchains?
3. Ruleset/configurations có được lưu trong Git và dùng chung giữa modules?
4. Có convention plugin thay vì copy policy thủ công vào mọi build.gradle?
5. `check`/`build` có thực sự kéo quality tasks cần thiết vào graph?
6. Có dùng `ignoreFailures=false` với exception riêng, tránh fail-open toàn cục?
7. Baseline có commit/tool version/scan scope/rule IDs và inventory có thể đối chiếu?
8. Ngoại lệ có file/rule cụ thể, reason, owner, issue và review/expiry?
9. Có kế hoạch xóa suppressions sau khi sửa legacy debt?
10. Có cơ chế phát hiện findings mới không bị che bởi baseline quá rộng?
11. Code mới và code đã sửa có quality gate đủ nghiêm?
12. Generated/external code có exclusions có lý do, không lạm dụng exclude cả package?
13. CI chạy chính xác cùng Gradle Wrapper, JDK và analyzer configuration đã commit?
14. PR thay policy có report trước/sau, rule changes và tác động tới các modules?
15. Có phân biệt quality analysis với JUnit tests, JaCoCo coverage và dependency verification?
16. Khi tool nâng version, đã xem breaking changes và baseline drift trước khi merge?

## 15. Tài liệu chính thức

- [Gradle — Checkstyle Plugin](https://docs.gradle.org/current/userguide/checkstyle_plugin.html): `checkstyleMain`, `checkstyleTest`, `check` wiring, `configDirectory`, `config_loc`, tool versions, reports.
- [Gradle — PMD Plugin](https://docs.gradle.org/current/userguide/pmd_plugin.html): `pmdMain`, `pmdTest`, `ruleSets`/`ruleSetFiles`, failure/report settings.
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): convention plugins, precompiled script plugins và build logic reuse.
- [Gradle — Organizing Gradle Projects](https://docs.gradle.org/current/userguide/multi_project_builds.html): root/subproject settings và plugin application.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): Java compiler/analyzer launcher requirements.
- [Gradle — Base Plugin](https://docs.gradle.org/current/userguide/base_plugin.html): verification lifecycle `check` và `build`.
- [Checkstyle — SuppressionFilter](https://checkstyle.sourceforge.io/filters/suppressionfilter.html): cấu hình `suppressions.xml`, `files`/`checks` và giới hạn suppression.
- [Checkstyle — Configuration](https://checkstyle.sourceforge.io/config.html): XML module configuration, checks và properties.
- [PMD — Rule References](https://docs.pmd-code.org/latest/pmd_rules_java.html): các rule groups và ruleset syntax.
- [Gradle — JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html): phân biệt coverage data và coverage verification tasks.
