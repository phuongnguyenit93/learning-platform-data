# Tối ưu pipeline theo module bị ảnh hưởng và dependency thực tế

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Hiệu năng build

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **chỉ build module có file thay đổi** là chưa đủ khi module đó có **các module phụ thuộc phía sau (downstream consumers)**.
2. Phân biệt đồ thị **project dependencies** với đồ thị **task execution dependencies**, và hai chiều **dependencies (upstream)**, **dependents (downstream)**.
3. Tính **tập module bị ảnh hưởng** bằng cách kết hợp files thay đổi, module sở hữu files và **reverse transitive closure** của đồ thị phụ thuộc.
4. Hiểu vì sao khi chạy **:app:check**, Gradle có thể xây outputs của thư viện upstream nhưng **không tự chạy mọi bài test của các thư viện đó**; pipeline phải chọn đúng check/test tasks.
5. Phân biệt **api** và **implementation** trong java-library, **compile avoidance** và **incremental compilation** với việc chọn module để chạy regression tests.
6. Thiết kế chính sách **fail closed** cho thay đổi toàn cục: settings.gradle, root Gradle config, buildSrc/build-logic, Gradle Wrapper, version catalogs, dependency locks, CI scripts, generated code và các file ngoài bản đồ modules.
7. Tạo một **multi-project Gradle Groovy DSL + Java 17** với năm module: :contracts, :billing, :notifications, :app và :tools độc lập; chạy ứng dụng và kiểm tra các module bằng task thật.
8. Viết một script Python 3 chỉ dùng standard library để chọn **Gradle task paths** cần chạy từ Git diff và đồ thị phụ thuộc, hỗ trợ xóa/đổi tên file và fallback an toàn.
9. Chạy pipeline bằng một shell script có xử lý lỗi đúng, không bỏ qua failure của impact analyzer và không tạo false-green khi kết quả chọn task rỗng bất thường.
10. Phối hợp lựa chọn module với **--parallel**, **Build Cache**, **Configuration Cache**, up-to-date checks, Java toolchains, các tests và chất lượng build.
11. Thiết kế kiểm thử ở nhiều lớp: fast PR impacted checks, smoke/integration tests của downstream consumers, full scheduled/regression build và release gates.
12. Đo **độ đúng trước thời gian tiết kiệm**: false negatives, số tasks được chọn, cache hit, thời gian critical path, chi phí phân tích diff và tốc độ feedback.
13. Nhận diện những tình huống bắt buộc chọn thêm modules hoặc chạy full: API change, runtime behavior, public resources, dependency substitution, testFixtures, annotation processors, schema contracts, plugin/settings changes.

**Nguyên tắc:** Gradle có khả năng chỉ thực thi những task outputs thật sự cần thiết bên trong một graph đã được yêu cầu, nhờ dependency graph, up-to-date checks, incremental compilation và Build Cache. **Pipeline chọn phạm vi QA** lại là một lớp quyết định khác: bạn phải chọn các module có khả năng chịu tác động, không chỉ những thư mục chứa file thay đổi. Một chiến lược impact sai có thể chạy rất nhanh nhưng bỏ sót regression.

## 1. Hai câu hỏi khác nhau trong một pipeline

Khi có thay đổi Git, hãy tách hai câu hỏi:

**Câu hỏi A — Module nào có thể bị ảnh hưởng về behavior?**

Ví dụ thư viện :contracts thay đổi một loại dữ liệu public được :billing và :notifications dùng. :app sử dụng hai module này. Như vậy :billing, :notifications và :app đều có thể chịu tác động, dù Git diff chỉ có files dưới contracts/.

**Câu hỏi B — Task nào Gradle phải chạy để hoàn thành check đã chọn?**

Sau khi pipeline yêu cầu :app:check, Gradle tự tính những compilation/processing outputs upstream cần để biên dịch/chạy các kiểm tra của :app. Chúng được nối bằng task dependencies hoặc variant-aware project dependency. Tuy nhiên điều đó **không đồng nghĩa** :contracts:check hoặc :billing:check cũng đã được yêu cầu.

~~~text
Git diff
    |
    v
Changed files
    |
    v
Owners: :contracts, :billing, ...
    |
    v
Reverse dependency closure  ─────→ Impacted modules
                                     |
                                     v
                   Select :module:check tasks
                                     |
                                     v
                     Gradle task dependency graph
                                     |
                         +-----------+-----------+
                         |                       |
                   Upstream outputs        Tests/checks của
                   cần để tiêu thụ       các module đã chọn
                         |                       |
                         +-----------+-----------+
                                     |
                                     v
                        Actual QA / task outcomes
~~~

**Đừng nhầm một lớp thay cho lớp kia.** Gradle task graph không tự biết team muốn chạy regression tests của mọi downstream consumer; Git diff theo thư mục lại không tự biết hệ thống phụ thuộc thực tế.

### 1.1. Bốn khái niệm dễ nhầm

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Changed module | File thay đổi thuộc module nào? | contracts/src/main/java/... |
| Upstream dependency | Module đang xét cần module nào? | :billing cần :contracts |
| Downstream dependent | Module nào cần module đang xét? | :app cần :billing |
| Task dependency | Task nào phải hoàn thành trước task đã chọn? | :app:compileJava cần classes/variant của :billing |

**Ví dụ không chính xác:** “Thay file trong :contracts thì chỉ cần :contracts:check vì Gradle tự build mọi thứ liên quan.” Gradle chỉ chạy những tasks nằm trong graph được yêu cầu, không tự chọn mọi regression suite ở downstream.

### 1.2. “Bị ảnh hưởng” có nhiều cấp độ

1. **Compile affected:** Đổi public API/ABI, classpath, type signature hoặc annotation có thể làm consumer phải recompile.
2. **Runtime affected:** Không đổi ABI nhưng đổi method behavior, kết quả/side effects hoặc runtime resources.
3. **Test affected:** Consumer tests kiểm tra behavior tích hợp hoặc assumptions có thể thất bại.
4. **Packaging affected:** Thay manifest, assets, service loader files, native libraries, dependency versions.
5. **Build configuration affected:** Đổi plugin, settings, Gradle properties, task wiring, generated sources hoặc CI scripts.
6. **Deployment/release affected:** Artifact coordinates, publication metadata, container image, migration scripts và quality gates.

Một thay đổi có thể không làm Gradle recompile consumer nhờ **compile avoidance**, nhưng vẫn làm **consumer integration tests cần chạy** vì runtime behavior đã thay.

## 2. Đồ thị module: đọc đúng chiều

Xét năm modules:

~~~text
:contracts
    |
    +----------> :billing --------+
    |                             |
    +----------> :notifications --+--> :app

:tools                            (độc lập)
~~~

Mũi tên **producer → consumer**. Trong build.gradle, chiều khai báo ngược:

~~~groovy
// billing/build.gradle
dependencies {
    api project(':contracts')
}

// notifications/build.gradle
dependencies {
    implementation project(':contracts')
}

// app/build.gradle
dependencies {
    implementation project(':billing')
    implementation project(':notifications')
}
~~~

Vì vậy:

- **upstream(:app)** gồm :billing, :notifications và qua chúng là :contracts.
- **downstream(:contracts)** gồm :billing, :notifications và :app.
- **downstream(:billing)** gồm :app.
- **downstream(:notifications)** gồm :app.
- **downstream(:app)** không có project consumer nào trong ví dụ.
- **:tools** không liên quan những module trên.

### 2.1. Reverse transitive closure

Giả sử:

~~~text
DEPENDS_ON[:billing]       = {:contracts}
DEPENDS_ON[:notifications] = {:contracts}
DEPENDS_ON[:app]           = {:billing, :notifications}
DEPENDS_ON[:contracts]     = {}
DEPENDS_ON[:tools]         = {}
~~~

Nếu changed modules là **C = {:contracts}**, impacted modules an toàn theo mô hình conservative:

~~~text
I = C ∪ downstream(C)
  = {:contracts, :billing, :notifications, :app}
~~~

Đây là **reverse transitive closure**. Nó tính cả module tự thay đổi và mọi module sử dụng trực tiếp/gián tiếp nó.

Nếu changed modules là {:billing, :tools}:

~~~text
I = {:billing, :app, :tools}
~~~

Không chạy :notifications:check chỉ vì cùng repo nếu giả định đồ thị đầy đủ, không có thay đổi global và tests/behavior độc lập. Nhưng các producer tasks upstream có thể vẫn xuất hiện trong Gradle task graph để :billing/:app compile/run.

### 2.2. Ma trận tác động của lab

| Files/module thay đổi | Module cần kiểm tra | Module có thể chỉ cần build output upstream |
|---|---|---|
| :contracts source | contracts, billing, notifications, app | Không cần tools |
| :billing source | billing, app | contracts có thể cần để compile/chạy |
| :notifications source | notifications, app | contracts có thể cần để compile/chạy |
| :app source | app | billing, notifications, contracts là upstream producers |
| :tools source | tools | Không cần app graph |
| :billing và :tools | billing, app, tools | Upstream của billing/app nếu cần |
| Root settings/plugin/wrapper thay đổi | **Full suite** | Toàn bộ modules |
| Không xác định owner hoặc graph không đáng tin | **Full suite** | Toàn bộ modules |

**Lưu ý:** Cột kiểm tra nói về **QA task selection**, không hứa module không được nhắc đến sẽ không bị Gradle cấu hình. Chọn tasks hẹp không đồng nghĩa Gradle chỉ cấu hình những projects đó trong mọi Gradle mode.

## 3. Gradle task graph không phải bản đồ kiểm thử downstream

Nếu chạy:

~~~bash
./gradlew :app:check --console=plain
~~~

Gradle sẽ chạy task **:app:check** và prerequisites. Nếu :app có tests, những tests này cần outputs thư viện từ :billing/:notifications/:contracts qua classpath. Nhưng task **:billing:check** và **:notifications:check** không nhất thiết nằm trong graph, vì Java plugin không tự chuyển mọi project dependency thành dependency đến *test suite của producer*.

**Đó là lý do pipeline phải chủ động chọn:**

~~~bash
./gradlew \
  :contracts:check \
  :billing:check \
  :notifications:check \
  :app:check \
  --console=plain
~~~

Các tasks này có thể chia sẻ compilation dependencies; Gradle quản lý để producer outputs không bị xây lặp vô ích.

### 3.1. Task selector khác task path tuyệt đối

Trong một Gradle multi-project build:

~~~bash
./gradlew check
~~~

Tên task **không có dấu : đầu** là **task selector**: từ root, Gradle chọn các tasks có tên check trong root và các subprojects phù hợp. Nó thường là cách thuận tiện để chạy **full-module check suite**.

Nhưng:

~~~bash
./gradlew :check
~~~

là **task path của riêng root project**. Nếu root không có check task, lệnh có thể không tìm được. Kể cả khi root có check, nó không mặc nhiên là aggregator cho mọi child check.

Và:

~~~bash
./gradlew :app:check
~~~

chỉ chọn check của :app cùng task prerequisites, **không có nghĩa test của mọi dependency modules cũng chạy**.

**Trong CI:** Ghi rõ bạn muốn full task selector hay một danh sách absolute task paths. Không thay **check** bằng **:check** tùy tiện.

### 3.2. --dry-run không chạy test

~~~bash
./gradlew :app:check --dry-run --console=plain
./gradlew :app:check :billing:check --dry-run --console=plain
~~~

--dry-run hiển thị graph/tasks dự kiến, **không thực thi actions**. Nó hữu ích để xác nhận scope nhưng **không phải QA PASS**. Cần chạy lệnh thật, kiểm tra reports/outcomes.

### 3.3. --continue vẫn fail CI nếu tests fail

~~~bash
./gradlew :billing:check :app:check \
  --continue --console=plain
~~~

Nếu một task fail, --continue cho Gradle thử chạy những tasks còn lại **không phụ thuộc vào task đã fail**. Nó không biến failure thành success; build vẫn failed nếu có failure. Điều này giúp thu thêm feedback từ những modules độc lập.

## 4. api và implementation: tối ưu compile, không tự thay thế regression QA

Gradle **java-library** phân biệt:

~~~groovy
dependencies {
    api project(':contracts')
    implementation project(':internal-helper')
}
~~~

- **api**: dependency types cần có trên compile classpath của consumers vì public API của library expose chúng.
- **implementation**: dependency phục vụ nội bộ library; consumer thông thường không nhìn thấy trên compile classpath qua dependency này, nhưng runtime variant có thể cần.
- **runtimeOnly**: chỉ runtime.
- **compileOnly**: cần lúc compile riêng, không mặc nhiên runtime.

Ví dụ :billing công khai method trả kiểu Invoice của :contracts:

~~~java
public static Invoice invoice(String sku, int cents) {
    return new Invoice(sku, cents);
}
~~~

Do public signature có **Invoice**, :billing nên dùng **api project(':contracts')**. :app có thể compile code dùng Invoice qua public API của Billing.

Ngược lại, :notifications chỉ dùng **RecipientNames** của :contracts bên trong method body. Public API chỉ trả String, vì vậy **implementation project(':contracts')** phù hợp.

### 4.1. Compile avoidance và ABI

Gradle Java compile avoidance có thể tránh recompile downstream consumers nếu **ABI** của dependency không đổi, ví dụ sửa logic trong body của một method nhưng giữ nguyên public method signature/return types. Đây là một tối ưu task compilation.

Tuy nhiên:
- Consumer runtime behavior có thể đổi dù ABI giữ nguyên.
- Integration tests dùng public behavior vẫn có thể fail.
- Generated resources/annotation processors có thể làm dependency rộng hơn ABI thường thấy.
- Public constants, annotations, records, sealed types, generated clients và reflection có các tình huống đặc biệt.
- Một public API change có thể tác động sâu đến modules downstream.

**Quy tắc an toàn:** ABI-based compile avoidance là việc Gradle giúp giảm compiler work; pipeline impact analyzer **không nên tự bỏ downstream tests chỉ vì source diff có vẻ nằm trong method body**.

### 4.2. Không suy luận dependency chỉ từ import statements

Một module có thể phụ thuộc:
- API classes qua compileClasspath.
- Runtime service providers qua ServiceLoader.
- Reflection/class names trong config.
- JSON schemas, SQL migrations hoặc protocol definitions.
- Generated sources từ annotation processors.
- Resources được copy/package.
- Native libraries.
- Test fixtures và integration test setups.
- Shared test utilities, Gradle plugins, version catalogs.
- External published modules hoặc composite builds.

Nếu impact graph chỉ quét Java imports, nó dễ bỏ sót **runtime-only hoặc resource dependencies**. Hãy dùng Gradle dependency declarations/variants, cộng thêm các quan hệ non-code được tổ chức ghi rõ.

### 4.3. Test fixtures và test-only changes

Một thay đổi dưới module/src/test có thể chỉ ảnh hưởng tests của module ấy. Nhưng nếu module công bố **test fixtures** cho consumers, test fixture API/runtime behavior có thể làm downstream tests bị ảnh hưởng.

Chính sách đơn giản nhất cho PR ban đầu: **mọi thay đổi trong thư mục module đều chọn module đó và downstream**. Sau khi đo dữ liệu đủ tốt, có thể tối ưu riêng test-only changes với rules được kiểm chứng; không nên mặc định loại downstream quá sớm.

## 5. Thiết kế pipeline theo nhiều lớp chất lượng

Một pipeline thực tế cần cân bằng latency và confidence:

| Lớp | Trigger | Phạm vi | Mục tiêu |
|---|---|---|---|
| Lint/format/secret scanning | Mọi PR | Thay đổi tương ứng, policy chung | Phản hồi sớm |
| **Impacted module checks** | Mọi PR | Changed + reverse downstream closure | Phát hiện nhanh các regression liên quan |
| Integration/contract tests | PR có giao diện hoặc subsystem liên quan | Consumer scenarios, DB/API/service contracts | Đảm bảo hành vi xuyên module |
| Full checks | Scheduled, main branch, release hoặc policy | **./gradlew check** | Bắt false negatives của impact rules |
| Build artifact/release | Main/release | Các artifacts cần công bố | Reproducibility/provenance |
| Deployment smoke/end-to-end | Staging/release | Hệ thống thực hoặc môi trường gần thật | Phát hiện hỏng khi tích hợp thực tế |

**Không thể thay các gates liên quan security, database migration và release bằng một phép chọn source modules đơn giản.** Những gates có phạm vi ngoài Gradle project dependency graph cần giữ policy riêng.

### 5.1. Fail closed khi không chắc

Một impact analyzer nên ưu tiên **full checks** khi:
- Không lấy được Git diff/merge-base.
- Có file ngoài bản đồ modules mà policy chưa phân loại.
- Đổi settings.gradle, root build.gradle hoặc gradle.properties.
- Đổi Wrapper/plugin versions/version catalogs/dependency locking.
- Đổi code buildSrc, build-logic, convention plugins hoặc init scripts.
- Đổi CI pipeline hoặc impact analyzer chính nó.
- Đổi file cấu hình shared có thể ảnh hưởng nhiều projects.
- Thêm project mới hoặc thay dependency edges mà đồ thị tĩnh chưa cập nhật.
- Gặp branch lịch sử khó so sánh hoặc cơ chế checkout thiếu lịch sử.

**Fail closed** ở đây nghĩa là chạy full checks hoặc làm CI fail có thông báo cần cập nhật graph, **không** im lặng chọn zero tasks.

### 5.2. Global change khác module-local change

Ví dụ:

~~~text
settings.gradle                          -> FULL
gradle/libs.versions.toml                -> FULL
gradle/wrapper/gradle-wrapper.properties -> FULL
buildSrc/src/main/java/...               -> FULL
build-logic/src/main/...                  -> FULL
ci/impacted_tasks.py                     -> FULL
.github/workflows/build.yml              -> FULL
billing/build.gradle                     -> FULL (policy conservative)
billing/src/main/java/...                -> billing + downstream
billing/src/test/java/...                -> billing + downstream (conservative)
tools/src/main/java/...                  -> tools
unknown-new-module/src/main/...          -> FULL
~~~

Vì một thay đổi build.gradle trong module có thể sửa **dependency declarations**, script ở bài lab sẽ chọn full khi gặp *.gradle hoặc *.gradle.kts bất cứ nơi đâu. Một hệ thống mature có thể làm tinh vi hơn nếu chứng minh được graph metadata chính xác, nhưng không nên ưu tiên tốc độ khi graph chưa đáng tin.

## 6. Bài lab chạy được: năm module Gradle + Java 17

Ta tạo một ứng dụng nhỏ có đúng đồ thị ở mục 2. Mỗi module sở hữu một task **smokeTest** chạy một class Java có phương thức main và assertions thuần JDK; task **check** của module dependsOn smokeTest. Điều này giúp bài lab **không cần tải JUnit dependencies**, nhưng vẫn có real verification tasks thay vì một bộ tests NO-SOURCE.

**Lưu ý:** Đây là smoke checks bằng JavaExec, **không phải JUnit Test task**. Trong production nên dùng test suites JUnit/Jupiter/TestNG cùng integration/contract tests phù hợp; các smoke checks ở đây chỉ giúp kiểm chứng được pipeline bằng Java 17 và Gradle core plugins.

### 6.1. Yêu cầu

- JDK 17 để chạy Gradle/JVM hoặc Java toolchain 17 được cài; nên đặt Gradle runtime trên JDK 17+.
- Gradle Wrapper tương thích với JDK 17. Các ví dụ dùng Groovy DSL và Gradle APIs lâu đời, phù hợp các phiên bản Gradle hiện hành.
- Git và Python 3 để chạy impact script ở mục 8 (Gradle/Java lab vẫn chạy không cần Python).
- POSIX shell cho ci/check-impacted.sh; Windows dùng PowerShell hoặc chạy trong Git Bash/WSL/CI Linux.
- Không cần mạng để tải library Java ngoài JDK; cần tải Gradle distribution lần đầu nếu Wrapper chưa có trong cache.

### 6.2. Cây thư mục

~~~text
impact-pipeline-lab/
├── settings.gradle
├── gradlew                           # Gradle Wrapper nếu có
├── gradlew.bat
├── gradle/wrapper/...
├── ci/
│   ├── impacted_tasks.py
│   └── check-impacted.sh
├── contracts/
│   ├── build.gradle
│   ├── src/main/java/demo/contracts/
│   │   ├── Invoice.java
│   │   └── RecipientNames.java
│   └── src/test/java/demo/contracts/ContractsCheck.java
├── billing/
│   ├── build.gradle
│   ├── src/main/java/demo/billing/Billing.java
│   └── src/test/java/demo/billing/BillingCheck.java
├── notifications/
│   ├── build.gradle
│   ├── src/main/java/demo/notifications/Notifier.java
│   └── src/test/java/demo/notifications/NotificationsCheck.java
├── app/
│   ├── build.gradle
│   ├── src/main/java/demo/app/Main.java
│   └── src/test/java/demo/app/AppCheck.java
└── tools/
    ├── build.gradle
    ├── src/main/java/demo/tools/AuditLabel.java
    └── src/test/java/demo/tools/ToolsCheck.java
~~~

**Trong cấu trúc này, :tools thực sự độc lập**, giúp minh họa không chạy nhầm modules khi thay đổi :billing. Cần tạo đúng tên class/file/path, kể cả chữ hoa.

### 6.3. settings.gradle

~~~groovy
rootProject.name = 'impact-pipeline-lab'

include 'contracts', 'billing', 'notifications', 'app', 'tools'
~~~

Không cần root subprojects { ... } để âm thầm áp plugin cho mọi module. Ví dụ viết rõ build.gradle của từng module nhằm quan sát ownership; trong repo lớn, có thể chia sẻ cấu hình Java toolchain/smokeTest thông qua convention plugins được áp trực tiếp ở từng module.

### 6.4. contracts/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.register('smokeTest', JavaExec) {
    group = 'verification'
    description = 'Runs plain-JDK contracts smoke checks'
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'demo.contracts.ContractsCheck'
}

tasks.named('check') {
    dependsOn tasks.named('smokeTest')
}
~~~

**Ý nghĩa:** java-library tạo Java component. JavaExec lấy **test source set runtimeClasspath**, gồm classes test và những runtime dependencies cần thiết; Gradle biết các tasks compile classes để chuẩn bị. check lifecycle task bao gồm smokeTest vì explicit dependsOn.

### 6.5. contracts/src/main/java/demo/contracts/Invoice.java

~~~java
package demo.contracts;

import java.util.Locale;

/**
 * A public contract shared between billing and its consumers.
 */
public record Invoice(String sku, int cents) {

    public Invoice {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (cents < 0) {
            throw new IllegalArgumentException("cents must be nonnegative");
        }
        sku = sku.strip();
    }

    public String label() {
        return sku.toUpperCase(Locale.ROOT) + ":" + cents;
    }
}
~~~

Java **record** là tính năng chuẩn trong Java 17. Public API của :billing sẽ trả một Invoice, vì vậy dependency :billing→:contracts phải được phân loại **api**.

### 6.6. contracts/src/main/java/demo/contracts/RecipientNames.java

~~~java
package demo.contracts;

/**
 * A helper used internally by notifications.
 */
public final class RecipientNames {
    private RecipientNames() {
    }

    public static String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("recipient is blank");
        }
        return raw.strip();
    }
}
~~~

Class này chỉ được :notifications dùng bên trong implementation, không hiện trong public signature của :notifications.Notifier.

### 6.7. contracts/src/test/java/demo/contracts/ContractsCheck.java

~~~java
package demo.contracts;

public final class ContractsCheck {
    private ContractsCheck() {
    }

    public static void main(String[] args) {
        String invoice = new Invoice("book", 120).label();
        String name = RecipientNames.normalize(" Mai ");

        if (!"BOOK:120".equals(invoice) || !"Mai".equals(name)) {
            throw new AssertionError("contracts behavior changed");
        }

        System.out.println("check=contracts-pass");
    }
}
~~~

**Nếu assertion fail**, JavaExec task trả lỗi và :contracts:check thất bại. Đây là một smoke check không dùng JUnit runner, nhưng có exit status và điều kiện kiểm tra thực.

### 6.8. billing/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // Invoice xuất hiện trong public method return type.
    api project(':contracts')
}

tasks.register('smokeTest', JavaExec) {
    group = 'verification'
    description = 'Runs billing API smoke checks'
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'demo.billing.BillingCheck'
}

tasks.named('check') {
    dependsOn tasks.named('smokeTest')
}
~~~

**api** là cần thiết vì method public Billing.invoice trả Invoice thuộc :contracts. Consumer :app có thể compile khi tham chiếu Invoice qua export compile classpath của :billing.

### 6.9. billing/src/main/java/demo/billing/Billing.java

~~~java
package demo.billing;

import demo.contracts.Invoice;

public final class Billing {
    private Billing() {
    }

    public static Invoice invoice(String sku, int cents) {
        return new Invoice(sku, cents);
    }
}
~~~

### 6.10. billing/src/test/java/demo/billing/BillingCheck.java

~~~java
package demo.billing;

public final class BillingCheck {
    private BillingCheck() {
    }

    public static void main(String[] args) {
        String actual = Billing.invoice("book", 120).label();

        if (!"BOOK:120".equals(actual)) {
            throw new AssertionError("billing invoice mismatch");
        }

        System.out.println("check=billing-pass");
    }
}
~~~

### 6.11. notifications/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // RecipientNames chỉ được dùng trong method body.
    implementation project(':contracts')
}

tasks.register('smokeTest', JavaExec) {
    group = 'verification'
    description = 'Runs notifications smoke checks'
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'demo.notifications.NotificationsCheck'
}

tasks.named('check') {
    dependsOn tasks.named('smokeTest')
}
~~~

**implementation** phù hợp vì API công khai của Notifier chỉ dùng java.lang.String, không expose Invoice hay RecipientNames trong public parameters/return types.

### 6.12. notifications/src/main/java/demo/notifications/Notifier.java

~~~java
package demo.notifications;

import demo.contracts.RecipientNames;

public final class Notifier {
    private Notifier() {
    }

    public static String hello(String rawRecipient) {
        return "Hello, "
                + RecipientNames.normalize(rawRecipient) + "!";
    }
}
~~~

### 6.13. notifications/src/test/java/demo/notifications/NotificationsCheck.java

~~~java
package demo.notifications;

public final class NotificationsCheck {
    private NotificationsCheck() {
    }

    public static void main(String[] args) {
        String actual = Notifier.hello(" Mai ");

        if (!"Hello, Mai!".equals(actual)) {
            throw new AssertionError("notification greeting mismatch");
        }

        System.out.println("check=notifications-pass");
    }
}
~~~

### 6.14. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation project(':billing')
    implementation project(':notifications')
}

tasks.register('smokeTest', JavaExec) {
    group = 'verification'
    description = 'Runs end-to-end app smoke checks'
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'demo.app.AppCheck'
}

tasks.named('check') {
    dependsOn tasks.named('smokeTest')
}
~~~

### 6.15. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.billing.Billing;
import demo.contracts.Invoice;
import demo.notifications.Notifier;

public final class Main {
    private Main() {
    }

    public static String report() {
        Invoice invoice = Billing.invoice("book", 120);
        String greeting = Notifier.hello(" Mai ");

        return "invoice=" + invoice.label()
                + "\nnotification=" + greeting;
    }

    public static void main(String[] args) {
        System.out.println(report());
    }
}
~~~

App imports Invoice dù không khai báo trực tiếp implementation project(':contracts'). Điều này hợp lệ trong lab vì :billing xuất public API dependency **api project(':contracts')**.

### 6.16. app/src/test/java/demo/app/AppCheck.java

~~~java
package demo.app;

public final class AppCheck {
    private AppCheck() {
    }

    public static void main(String[] args) {
        String expected =
                "invoice=BOOK:120\nnotification=Hello, Mai!";

        if (!expected.equals(Main.report())) {
            throw new AssertionError("app report mismatch");
        }

        System.out.println("check=app-pass");
    }
}
~~~

App smoke test kiểm tra một hành vi xuyên module **Billing + Notifier + Contracts**, nên thay đổi behavior ở :contracts có thể làm test này fail dù :app không có file source thay đổi.

### 6.17. tools/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.register('smokeTest', JavaExec) {
    group = 'verification'
    description = 'Runs independent tools smoke checks'
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'demo.tools.ToolsCheck'
}

tasks.named('check') {
    dependsOn tasks.named('smokeTest')
}
~~~

### 6.18. tools/src/main/java/demo/tools/AuditLabel.java

~~~java
package demo.tools;

public final class AuditLabel {
    private AuditLabel() {
    }

    public static String status() {
        return "audit:ready";
    }
}
~~~

### 6.19. tools/src/test/java/demo/tools/ToolsCheck.java

~~~java
package demo.tools;

public final class ToolsCheck {
    private ToolsCheck() {
    }

    public static void main(String[] args) {
        if (!"audit:ready".equals(AuditLabel.status())) {
            throw new AssertionError("tools status mismatch");
        }

        System.out.println("check=tools-pass");
    }
}
~~~

Không module nào phụ thuộc :tools, nên khi sửa riêng :tools/src/main/java, pipeline có thể chọn **:tools:check** mà không yêu cầu tests của :app/:billing/:notifications.

### 6.20. Chạy ứng dụng

Từ project root trên Linux/macOS:

~~~bash
./gradlew :app:run --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run --quiet
~~~

**Stdout do Main.main in, chính xác hai dòng:**

~~~text
invoice=BOOK:120
notification=Hello, Mai!
~~~

Nếu Gradle Java toolchain 17 không khả dụng, build sẽ lỗi trước khi chạy Main. Cần cài JDK/toolchain hoặc cho phép toolchain provisioning theo policy; không sửa dependency graph để né lỗi môi trường.

### 6.21. Chạy toàn bộ checks

~~~bash
./gradlew check --console=plain
~~~

Đây là task selector gọi những **check tasks của các modules** trong multi-project build. Các smokeTest tasks in những dòng marker như:

~~~text
check=contracts-pass
check=billing-pass
check=notifications-pass
check=app-pass
check=tools-pass
~~~

**Không cam kết thứ tự console line** khi --parallel hoặc log buffering được bật. Lỗi ở một task làm build fail; marker chỉ được in nếu class main của task ấy chạy tới đoạn System.out.println.

Nếu bạn chỉ gọi:

~~~bash
./gradlew :app:check --console=plain
~~~

thì có thể chỉ thấy **check=app-pass**; upstream Java compilation vẫn được xử lý khi cần, nhưng **check=contracts-pass** hoặc **check=billing-pass** không được bảo đảm xuất hiện.

### 6.22. Kiểm tra dependency graph thực

~~~bash
./gradlew projects --console=plain
./gradlew :billing:dependencies --configuration compileClasspath
./gradlew :notifications:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:check --dry-run --console=plain
./gradlew :contracts:outgoingVariants --console=plain
~~~

Quan sát:
- :billing compileClasspath có :contracts như API dependency.
- :notifications compileClasspath có :contracts để module tự compile.
- :app compileClasspath nhận :contracts thông qua API variant của :billing.
- Runtime variant truyền những implementation dependencies cần chạy.
- :app:check graph có producers cần thiết, **không tự có toàn bộ upstream :module:smokeTest**.
- outgoingVariants cho thấy các variants Gradle cung cấp cho Java library.

## 7. Kiểm thử trực tiếp bằng javac/java không dùng Gradle

Để kiểm chứng mã Java 17 và thứ tự classpath một cách độc lập, có thể compile các Java source files bằng JDK. Đoạn sau **không thay thế Gradle dependency/variant resolution**, nhưng là bài thực hành hữu ích.

### 7.1. Linux/macOS, từ project root

~~~bash
mkdir -p build/manual/contracts build/manual/billing \
  build/manual/notifications build/manual/app

javac --release 17 -d build/manual/contracts \
  contracts/src/main/java/demo/contracts/Invoice.java \
  contracts/src/main/java/demo/contracts/RecipientNames.java

javac --release 17 -cp build/manual/contracts \
  -d build/manual/billing \
  billing/src/main/java/demo/billing/Billing.java

javac --release 17 -cp build/manual/contracts \
  -d build/manual/notifications \
  notifications/src/main/java/demo/notifications/Notifier.java

javac --release 17 \
  -cp "build/manual/contracts:build/manual/billing:build/manual/notifications" \
  -d build/manual/app \
  app/src/main/java/demo/app/Main.java

java -cp "build/manual/contracts:build/manual/billing:build/manual/notifications:build/manual/app" \
  demo.app.Main
~~~

**Stdout:**

~~~text
invoice=BOOK:120
notification=Hello, Mai!
~~~

Lưu ý cách dùng **-cp** ở đây tự chuyển classpath thủ công; với Gradle build thực, Gradle quản lý classpath qua api/implementation và variants.

### 7.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build\manual\contracts,build\manual\billing,build\manual\notifications,build\manual\app | Out-Null
javac --release 17 -d build\manual\contracts contracts\src\main\java\demo\contracts\Invoice.java contracts\src\main\java\demo\contracts\RecipientNames.java
javac --release 17 -cp build\manual\contracts -d build\manual\billing billing\src\main\java\demo\billing\Billing.java
javac --release 17 -cp build\manual\contracts -d build\manual\notifications notifications\src\main\java\demo\notifications\Notifier.java
javac --release 17 -cp "build\manual\contracts;build\manual\billing;build\manual\notifications" -d build\manual\app app\src\main\java\demo\app\Main.java
java -cp "build\manual\contracts;build\manual\billing;build\manual\notifications;build\manual\app" demo.app.Main
~~~

Windows classpath entries được ngăn bằng **dấu chấm phẩy**, Linux/macOS dùng **dấu hai chấm**. Đây là sự khác biệt của java -cp, không liên quan Gradle project graph.

## 8. Script chọn impacted Gradle checks từ Git diff

Một impact analyzer trong CI không nên chỉ hardcode một danh sách changed directory rồi chạy tests ở đó. Cần **reverse transitive closure** và fallback an toàn cho global/unknown changes.

**Mục tiêu script ở đây:** Không dùng third-party Python packages, không gọi Gradle trong lúc phân tích diff, và chỉ phát task names an toàn:
- **:contracts:check**, **:billing:check**, ...
- Hoặc **check** (task selector cho full suite) khi không chắc.

**Giới hạn minh bạch:** Dependency graph dưới đây là một **snapshot tĩnh được duy trì cùng source**; nó không tự parse Gradle project dependencies. Vì vậy cần review/drift checks khi module dependencies đổi. Để bảo toàn correctness, script chọn full suite khi có bất kỳ *.gradle, *.gradle.kts, gradle.properties hoặc gradle.lockfile thay đổi.

### 8.1. ci/impacted_tasks.py

~~~python
#!/usr/bin/env python3
"""Print safe Gradle check task selectors from a Git diff.

Usage:
  python3 ci/impacted_tasks.py BASE_REF HEAD_REF

Stdout: exactly one Gradle task per line.
Unknown/global changes trigger 'check' (full selector).
"""

import subprocess
import sys

MODULES = (
    "contracts",
    "billing",
    "notifications",
    "app",
    "tools",
)

# consumer -> direct upstream dependencies
DEPENDS_ON = {
    "contracts": set(),
    "billing": {"contracts"},
    "notifications": {"contracts"},
    "app": {"billing", "notifications"},
    "tools": set(),
}


def all_checks():
    # Unqualified 'check' selects matching tasks across subprojects.
    return ["check"]


def changed_paths(base_ref, head_ref):
    try:
        merge_base = subprocess.check_output(
            ["git", "merge-base", base_ref, head_ref],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()

        # --no-renames reports rename as delete + add, so changes
        # from both old and new module paths are considered.
        raw = subprocess.check_output(
            [
                "git",
                "diff",
                "--name-only",
                "-z",
                "--no-renames",
                merge_base,
                head_ref,
                "--",
            ],
            stderr=subprocess.PIPE,
        )
        return [
            p for p in raw.decode("utf-8", "surrogateescape").split("\0")
            if p
        ]
    except (subprocess.CalledProcessError, OSError) as exc:
        print(
            "impact analysis unavailable, selecting full suite: " + str(exc),
            file=sys.stderr,
        )
        return None


def requires_full_suite(path):
    name = path.rsplit("/", 1)[-1]

    # These files may change dependency edges, build behavior
    # or quality gates, even when they live under one module.
    if name.endswith((".gradle", ".gradle.kts")):
        return True

    if name in ("gradle.properties", "gradle.lockfile"):
        return True

    # Any path outside known module roots is conservative FULL.
    root = path.split("/", 1)[0]
    if root not in MODULES:
        return True

    return False


def impacted_tasks(paths):
    if paths is None:
        return all_checks()

    if not paths:
        # A valid diff with no changes does not need module checks.
        return []

    if any(requires_full_suite(path) for path in paths):
        return all_checks()

    changed = {path.split("/", 1)[0] for path in paths}

    # Reverse graph: producer -> downstream consumers
    downstream = {module: set() for module in MODULES}

    for consumer, upstreams in DEPENDS_ON.items():
        for producer in upstreams:
            if producer not in downstream:
                return all_checks()
            downstream[producer].add(consumer)

    impacted = set(changed)
    pending = list(changed)

    while pending:
        producer = pending.pop()
        for consumer in downstream[producer]:
            if consumer not in impacted:
                impacted.add(consumer)
                pending.append(consumer)

    # Stable order improves logs and configuration cache reuse.
    return [
        ":" + module + ":check"
        for module in MODULES
        if module in impacted
    ]


def main():
    if len(sys.argv) != 3:
        print(
            "usage: impacted_tasks.py BASE_REF HEAD_REF",
            file=sys.stderr,
        )
        return 2

    paths = changed_paths(sys.argv[1], sys.argv[2])
    for task in impacted_tasks(paths):
        print(task)

    return 0


if __name__ == "__main__":
    sys.exit(main())
~~~

### 8.2. Tại sao dùng git merge-base?

Giả sử một PR branch tách từ main ở commit M; main tiến thêm commit khác sau đó. Khi xét thay đổi của PR, ta thường muốn so **merge-base(M) → head của PR**, thay vì chỉ diff hai HEAD trực tiếp và vô tình bao gồm những commits mới trên main.

Do đó:

~~~bash
git merge-base BASE_REF HEAD_REF
git diff --name-only -z --no-renames MERGE_BASE HEAD_REF --
~~~

là hướng tiếp cận phù hợp cho diff của PR. Trong pipeline push hoặc release, policy diff có thể khác; phải xác định base cần so theo ngữ cảnh.

**Lưu ý:** CI checkout cần đủ Git history để tìm merge-base. Với shallow clone không có merge-base, script ở trên chọn **full suite** thay vì bỏ qua tests.

### 8.3. Vì sao --no-renames?

Khi rename/move file:
- Nếu chỉ nhìn path mới, module cũ có thể bị bỏ sót.
- **--no-renames** làm Git báo old path như deletion và new path như addition.
- **-z** dùng NUL separators, xử lý file names có spaces/newlines chính xác hơn line-separated diff.

Trên hệ thống thực, rename giữa modules có thể thay cả public API ownership, nên lựa chọn **tập union của module cũ và mới** là conservative.

### 8.4. Vì sao unknown file → check?

Ví dụ có file:

~~~text
schema/contracts/payment.json
~~~

Dù không nằm dưới contracts/src, nó có thể được app/code generator dùng. Nếu script mặc định skip unknown path, CI có thể xanh giả.

Trong script, unknown root sẽ in:

~~~text
check
~~~

Từ root Gradle build, lệnh **./gradlew check** là full task selector cho các subprojects. Nếu repo có thêm service integration tests ngoài Gradle, pipeline phải chạy những gates đó riêng.

### 8.5. Script mô hình hóa downstream transitive như thế nào?

Nếu changed set chỉ có contracts:
- reverse[contracts] = billing, notifications.
- billing dẫn đến app.
- notifications cũng dẫn đến app, nhưng set loại trùng.
- tools không được thêm.

Stdout sẽ là:

~~~text
:contracts:check
:billing:check
:notifications:check
:app:check
~~~

Nếu chỉ thay tools:

~~~text
:tools:check
~~~

Nếu chỉ thay billing:

~~~text
:billing:check
:app:check
~~~

Nếu sửa settings.gradle hoặc ci/impacted_tasks.py:

~~~text
check
~~~

**Đây là kỳ vọng của thuật toán với đồ thị đã khai báo**, không phải kết quả được đọc từ Git repository thật của người học.

## 9. Script chạy Gradle không nuốt lỗi phân tích impact

Một script pipeline thiếu cẩn thận có thể tạo false-green:
- Git diff fail nhưng danh sách tasks rỗng và job exit 0.
- Analyzer stdout chứa log hoặc thông báo, bị truyền thành task name.
- Không dùng quote khi có arguments.
- Pipeline chạy check selector sai path.
- Gradle fail nhưng shell tiếp tục và cuối cùng exit 0.

Để giảm rủi ro, tạo **ci/check-impacted.sh**:

~~~bash
#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: ci/check-impacted.sh BASE_REF HEAD_REF" >&2
    exit 2
fi

base_ref="$1"
head_ref="$2"

tasks_file="$(mktemp)"
trap 'rm -f "$tasks_file"' EXIT HUP INT TERM

# Nếu Python exit khác 0, 'set -e' làm CI fail.
python3 ci/impacted_tasks.py "$base_ref" "$head_ref" > "$tasks_file"

# Build danh sách positional args mà không dùng eval.
set --
while IFS= read -r task || [ -n "$task" ]; do
    if [ -n "$task" ]; then
        set -- "$@" "$task"
    fi
done < "$tasks_file"

if [ "$#" -eq 0 ]; then
    echo "No changed files in valid PR diff; no impacted Gradle checks"
    exit 0
fi

echo "Running selected Gradle check tasks: $*"

# Cần thực thi với Gradle Wrapper và Java 17+.
./gradlew "$@" --parallel --build-cache --continue --console=plain
~~~

**Giải thích:**
- **set -eu**: lỗi lệnh được quản lý, biến chưa gán báo lỗi.
- Python stderr hiển thị diagnostics; stdout chỉ có task names.
- **mktemp/trap** tránh để file tạm tồn tại lâu.
- **set --** xây arguments an toàn; không dùng eval.
- **"$@"** giữ mỗi task selector thành một argument.
- **--continue** thu nhiều failures nhưng không biến status thành success.
- Nếu diff hợp lệ thực sự không có changed files, script có thể skip; CI policy có thể yêu cầu vẫn chạy cheap smoke checks hoặc full gates cho empty/metadata-only pipeline tùy tính chất repo.

**Chú ý thực tế:** File shell script này chạy từ **project root**. Nếu CI đang đứng ở thư mục khác, cần cd đúng root trước. Nếu chạy Windows, dùng Git Bash/WSL hoặc chuyển logic sang PowerShell tương đương, không dùng cmd.exe trực tiếp với syntax POSIX.

### 9.1. Cấp quyền chạy shell script

Unix:

~~~bash
chmod +x ci/check-impacted.sh
~~~

Chạy ví dụ sau khi đã có hai Git refs hợp lệ và đủ history:

~~~bash
./ci/check-impacted.sh origin/main HEAD
~~~

Lệnh không nên giả định origin/main luôn tồn tại trong mọi CI provider. Nếu đang ở GitHub Actions, hãy cấu hình checkout fetch-depth đủ để có base commit/merge-base và truyền base SHA/head SHA chính xác từ event payload, không dựa mù quáng vào PR merge checkout HEAD.

### 9.2. Kiểm tra analyzer bằng Git diff thật

Khi có commit changes phù hợp, chạy:

~~~bash
python3 ci/impacted_tasks.py origin/main HEAD
~~~

Lệnh chỉ in task names; muốn chạy thật, dùng wrapper shell. Bạn có thể dùng **git diff --name-only** để xác định Git thấy files nào, rồi so với selected modules dự kiến.

### 9.3. Kiểm thử thuật toán độc lập với Git

Trong Python, có thể import module và đưa danh sách paths giả định:

~~~bash
python3 -c "from ci.impacted_tasks import impacted_tasks; print(impacted_tasks(['contracts/src/main/java/demo/contracts/Invoice.java']))"
~~~

**Stdout:**

~~~text
[':contracts:check', ':billing:check', ':notifications:check', ':app:check']
~~~

Ví dụ tools:

~~~bash
python3 -c "from ci.impacted_tasks import impacted_tasks; print(impacted_tasks(['tools/src/main/java/demo/tools/AuditLabel.java']))"
~~~

**Stdout:**

~~~text
[':tools:check']
~~~

Ví dụ global:

~~~bash
python3 -c "from ci.impacted_tasks import impacted_tasks; print(impacted_tasks(['settings.gradle']))"
~~~

**Stdout:**

~~~text
['check']
~~~

Đây là unit-like kiểm tra hàm selection, **không** phải Gradle task execution. Python import dạng namespace package trong Python 3 có thể dùng thư mục ci không có __init__.py khi project root nằm trong sys.path; nếu môi trường import đặc biệt, tạo một ci/__init__.py rỗng. Việc thêm file ci/__init__.py cũng được script xếp global change trong Git diff — phù hợp chính sách fail closed.

### 9.4. Production cần chống graph drift

Script dùng DEPENDS_ON tĩnh. Nếu một developer thêm:

~~~groovy
// tools/build.gradle, về sau:
dependencies {
    implementation project(':contracts')
}
~~~

mà quên cập nhật DEPENDS_ON, lần PR **thêm** dòng này được fallback full vì build.gradle đổi. Nhưng những PR **sau đó** chỉ sửa contracts source có thể bỏ :tools nếu map vẫn sai.

Vì vậy, trong pipeline thật cần một kiểm thử **graph integrity**:
- Đọc/thu thập project dependency edges từ Gradle model/variants bằng một report task có hợp đồng rõ.
- So sánh edges với impact mapping đã check-in.
- Hoặc sinh mapping tự động từ model đáng tin cậy trong một bước có kiểm soát.
- Fail job nếu mapping stale/thiếu module mới, không âm thầm tiếp tục chọn nhỏ.
- Scheduled full checks vẫn cần để bắt những quan hệ non-declarative hoặc graph analysis bugs.

**Đừng coi bài lab script là một plugin phân tích Gradle tổng quát**. Nó mô hình hóa chính xác đồ thị của ví dụ; production nhiều included builds, flavors/variants/testFixtures, dynamic includes sẽ cần model mạnh hơn.

## 10. Tối ưu task execution sau khi chọn module

Một impact analyzer chỉ quyết định **cần chạy QA ở đâu**. Sau đó hãy để Gradle tối ưu những công việc thật sự cần thiết.

### 10.1. --parallel

~~~bash
./gradlew \
  :billing:check :notifications:check :app:check \
  --parallel --console=plain
~~~

Gradle có thể chạy tasks từ những projects độc lập song song nếu dependency graph cho phép. Nhưng :app vẫn phải đợi outputs upstream mà nó cần; --parallel **không bỏ qua dependencies**.

Độ lợi phụ thuộc:
- Số modules độc lập.
- CPU/memory/disk throughput và worker count.
- Số test forks và external service contention.
- Gradle build script/custom tasks có shared state hay không.
- Network dependency resolution/remote cache latency.

**Không đặt --max-workers quá lớn** rồi mong build luôn nhanh; quá nhiều Java compilers/test JVMs có thể làm máy swap và tăng latency.

### 10.2. Build Cache

~~~bash
./gradlew :app:check --build-cache --console=plain
~~~

Build Cache lưu outputs của những cacheable tasks theo cache key, có thể dùng lại trong checkout/machine khác nếu inputs, implementation và normalization phù hợp.

**Build Cache khác chọn impact modules.** Có thể bạn chọn cả bốn module downstream nhưng Gradle phục hồi nhiều compile/test outputs FROM-CACHE hoặc đánh dấu UP-TO-DATE. Đây là cách **conservative QA selection** vẫn đạt tốc độ tốt mà không loại bỏ checks cần thiết.

### 10.3. Configuration Cache

~~~bash
./gradlew :app:check --configuration-cache --console=plain
~~~

Configuration Cache lưu configured task graph khi build/configuration inputs phù hợp. Nếu CI luôn yêu cầu một tập task thay đổi theo từng PR, số cache entries có thể phân tán; cần đo khả năng reuse. Không coi Configuration Cache là cách tự động biết impacted modules.

**Trong Gradle 9.9, Configuration Cache là chế độ được khuyến nghị nhưng vẫn có các yêu cầu tương thích plugin/build logic**. Hãy bật có kiểm soát, kiểm tra violations và benchmark thực tế trước khi dùng rộng trong pipeline.

### 10.4. Incremental compilation/compile avoidance

JavaCompile task có thể:
- Chỉ recompile những sources thật sự chịu tác động.
- Tránh recompile downstream khi upstream ABI không đổi.
- Dùng cached outputs khi inputs/implementation tương đương.
- Bỏ qua work khi outputs UP-TO-DATE.

Nhưng cần phân biệt:
- **Không recompile :app** không đồng nghĩa **không chạy :app tests**.
- **Thay implementation code của :contracts** có thể làm runtime behavior thay đổi ở :app.
- **api vs implementation** giảm compile classpath exposure, không thay đổi contract kiểm thử business.
- Nếu có annotation processors/generation, compile avoidance có thể bị hạn chế và cần cấu hình processor đúng.

### 10.5. --continue

~~~bash
./gradlew :contracts:check :billing:check :notifications:check :app:check \
  --continue --parallel --console=plain
~~~

Nếu billing smokeTest fail nhưng tools độc lập cũng được chọn, Gradle có thể vẫn chạy tools checks rồi báo tổng failures. Tuy nhiên các tasks phụ thuộc vào task đã fail không thể chạy đầy đủ. **Không xem --continue là “ignore failures”.**

### 10.6. Tránh clean trong every PR pipeline

Lệnh:

~~~bash
./gradlew clean check
~~~

có thể làm mất nhiều up-to-date benefits do xóa outputs. Nếu team không có lý do cần clean, thường chạy:

~~~bash
./gradlew check --build-cache --parallel
~~~

sẽ có cơ hội reuse local outputs/build cache hơn. Dù vậy, CI với ephemeral runners có thể vốn là clean checkout; remote cache vẫn hữu ích. Scheduled/release jobs có thể chủ động chạy clean để phát hiện hidden state.

**Chọn chính sách theo mục tiêu QA**, không đặt clean mặc định chỉ vì thói quen.

## 11. Tối ưu CI mà không bỏ sót kiểm thử

### 11.1. PR fast checks

Đầu vào:
- Merge-base/main/head chính xác.
- Git diff có cả deletes/renames.
- Impact mapping được verify.
- Risk policy cho global changes.

Đầu ra:
- Absolute task paths :module:check hoặc full selector **check**.
- Logs công bố changed paths/selected modules.
- Lưu task outcomes và summary, không chỉ status BUILD SUCCESSFUL.

### 11.2. Scheduled full check

Chạy:

~~~bash
./gradlew check --parallel --build-cache --continue --console=plain
~~~

Mục tiêu là bắt:
- Mapping drift.
- Runtime dependencies ngoài static graph.
- Platform-specific failures.
- Tests bỏ sót trong PR selection.
- Shared resources/configuration changes.
- Non-deterministic tests và CI environment issues.

**Scheduled full suite không thay release QA**, nhưng là vòng phản hồi quan trọng để đo độ chính xác của impact selector.

### 11.3. Main/release gates

Main/release nên có policies rõ:
- Build và test theo phạm vi mà tổ chức yêu cầu, thường full hoặc mandatory core gates.
- Integration/contract/E2E tests đối với hệ thống tích hợp.
- Dependency vulnerability/license policies.
- Signing/publication, binary provenance, SBOM khi cần.
- Artifact consistency và clean environment.
- Không sử dụng PR impact selection để tự bỏ qua các mandatory release checks.

Một release có thể fail dù impacted module checks trước đó PASS; điều này không nhất thiết chứng minh script sai, vì release có phạm vi kiểm thử rộng hơn.

### 11.4. Dữ liệu quan sát phải thể hiện scope

Một báo cáo QA có ích nêu:
- Git base/head và merge-base.
- Changed files/module owners.
- Impact policy version/graph version.
- Chọn **module check tasks** nào, vì sao.
- Full fallback trigger nếu có.
- Gradle Wrapper/JDK versions.
- Task outcomes executed, UP-TO-DATE, FROM-CACHE, NO-SOURCE.
- Test counts/failures và reports.
- Duration, cache hit rate, CPU/resources.
- Whether full suite/scheduled run also passed.

**Đừng chỉ ghi “all tests passed” nếu thực tế chỉ chạy một tập impacted modules**. Hãy ghi rõ phạm vi QA.

## 12. Những trường hợp đặc biệt cần xem xét

### 12.1. Version catalog hoặc dependency lock đổi

Dù chỉ thay một dòng trong gradle/libs.versions.toml hoặc gradle.lockfile:
- Một dependency version có thể phục vụ nhiều modules.
- Plugin version có thể đổi behavior task registration/configuration.
- Runtime transitive dependencies có thể đổi.
- Bản đồ source module có thể không phản ánh ảnh hưởng.

**Policy conservative:** full suite cho shared version catalog hoặc lockfile; sau này có thể phân loại cụ thể nếu trace dependencies đáng tin.

### 12.2. Shared schema, resources và generated code

File schema ngoài module root có thể được consumer codegen tasks ở nhiều modules dùng. Nếu impact analyzer chỉ nhìn src/main/java, nó sẽ bỏ sót.

Đưa schema vào:
- Một producer Gradle project với outgoing artifact/variant.
- Hoặc dependency mapping theo tài nguyên rõ ràng.
- Hoặc fallback full khi thay schema root.

**Không định nghĩa unknown file = safe to skip**.

### 12.3. Composite builds và included builds

Một included build build-logic cung cấp Gradle convention plugin hoặc custom task types. Nếu nó thay đổi, nhiều projects trong main build có thể bị ảnh hưởng dù không có project dependency declaration đến build-logic bằng implementation project('...').

Do đó:
- buildSrc/build-logic changes → full suite.
- Plugin dependency/Gradle init scripts → full suite hoặc policy riêng đầy đủ.
- Nếu production có nhiều included builds, impact graph phải thể hiện cả build-tree dependencies, không chỉ subproject paths của main build.

### 12.4. Monorepo có shared E2E tests ngoài Gradle

Nếu repo còn:
- Node frontend,
- Python backend,
- Container Dockerfiles,
- Database migration,
- Terraform,
- Mobile app,

thì Gradle project graph không mô hình hóa hết các quan hệ. CI impact engine cần phối hợp các đồ thị/tasks ngoài Gradle hoặc giữ mandatory E2E/integration gates.

Không vì Gradle script chạy nhanh mà tuyên bố hệ thống end-to-end đã được kiểm tra.

### 12.5. Files chỉ sửa comment/docs

Có thể tối ưu riêng docs-only changes **sau khi** phân biệt:
- README nội bộ không được package/run.
- Code examples trong documentation có tests hoặc không.
- Generated API docs thay đổi artifact.
- Release notes có ảnh hưởng publication.
- License/security policy ảnh hưởng release.

Bài lab chọn conservative fallback cho path không nằm trong modules. Có thể sau này thêm allowlist docs-only có owner reviews; phải có tests chứng minh nó không che functional changes.

### 12.6. Test-only changes trong module

Nếu chỉ sửa :billing/src/test:
- Ít nhất phải chạy :billing checks.
- Trong lab conservative selector cũng chạy :app checks.
- Nếu suite dùng testFixtures/shared testing libs, downstream có thể cần thật.
- Nếu test hoàn toàn private và không thay product behavior, một analyzer trưởng thành có thể chỉ chọn billing tests.

**Không mặc định tối ưu sâu hơn khi chưa xác minh coupling.**

### 12.7. Dynamic runtime integration

Một dependency có thể chỉ xuất hiện qua:
- Reflection,
- Classpath scanning,
- Environment-based module loading,
- Configuration file,
- Database schema,
- Feature flags.

Nó có thể không nằm trong compileClasspath graph. Hãy duy trì **runtime/contract dependency edges** cho impact analyzer hoặc dùng full/integration fallback.

## 13. Đo hiệu quả một cách đáng tin

### 13.1. Phép đo

| Metric | Ý nghĩa |
|---|---|
| PR feedback latency P50/P95 | Developer nhận QA nhanh đến đâu |
| Analyzer time | Git diff + graph lookup tốn bao lâu |
| Selected modules/tasks | Có chọn quá nhiều hoặc quá ít không |
| Full fallback rate | Bao nhiêu PR bị mở rộng scope |
| False-negative incidents | Có lỗi mà impacted check không phát hiện nhưng full check có không |
| Gradle config time | Chi phí cấu hình cho các task sets |
| Task execution critical path | Đường phụ thuộc dài nhất giới hạn duration |
| Parallel CPU utilization | Có thật sự tận dụng workers không |
| Build cache hit ratio | Bao nhiêu tasks eligible nhận cached outputs |
| Avoided recompile | Downstream compilation nào được bỏ do ABI ổn định |
| Test duration by module | Modules nào là bottleneck |
| Flake rate | Rerun failures/noise có làm phép đo sai lệch không |
| Full suite delta | Impacted pipeline tiết kiệm bao nhiêu so với full |
| Defect escape rate | Lỗi nào vẫn lọt qua PR selection |

**Một pipeline rất nhanh nhưng false-negative rate cao là tối ưu thất bại.** Hãy đo correctness và confidence, không chỉ số tasks bỏ qua.

### 13.2. Kịch bản đo thực tế

Chọn các PR samples:
- Thay một method body trong :contracts.
- Thay public return type của :billing.
- Thay :notifications internal helper.
- Chỉ sửa :tools.
- Sửa version catalog.
- Thêm dependency project mới.
- Di chuyển file source giữa modules.
- Sửa shared resource hoặc buildSrc plugin.

Với mỗi trường hợp:
1. Dự đoán impacted modules theo policy.
2. Chạy impact analyzer.
3. Xem Gradle selected task graph.
4. Chạy impacted checks.
5. Chạy full check trong controlled comparison.
6. So failures/task outcomes/outputs.
7. Nếu full fail mà impacted pass do scope, sửa mapping/policy ngay.
8. Đo duration trên cùng loại CI agents, cùng Gradle/JDK/cache conditions khi có thể.

Đừng so một impacted run warm cache với full run cold cache rồi kết luận tỷ lệ tiết kiệm chỉ do impact selection.

### 13.3. Quan sát CPU và critical path

Nếu :contracts:check mất 4 phút còn :billing và :notifications mỗi module mất 1 phút, tổng wall time phụ thuộc task graph và resources; --parallel không thể làm một upstream bottleneck biến mất. Có thể tối ưu:
- Test sharding của module lớn nếu tool/framework hỗ trợ.
- Tránh expensive project configuration và dependency resolution sớm.
- Build Cache và remote caches cho CI.
- Tách codegen tasks quá lớn thành inputs/outputs rõ hơn.
- Giảm unnecessary dependencies và compile classpath size.
- Tối ưu test forks, heap và Docker startup.
- Không tăng số CI jobs quá nhiều nếu startup/cache warmup overhead lớn.

## 14. Troubleshooting

### Lỗi 1 — PR sửa :contracts nhưng CI chỉ chạy :contracts:check

**Nguyên nhân:** Selector chỉ lấy changed module, không tính downstream reverse closure.

**Cách xử lý:** Từ project graph, thêm :billing, :notifications, :app vào impacted set; kiểm tra mapping drift.

### Lỗi 2 — :app:check thành công dù :billing:check đang fail

**Nguyên nhân:** :app:check không tự phụ thuộc vào :billing:check; Gradle chỉ cần producers của billing để chạy app checks.

**Cách xử lý:** Chọn :billing:check riêng trong CI khi policy yêu cầu.

### Lỗi 3 — :tools:check không chạy khi sửa :contracts

**Giải thích:** Trong lab, :tools độc lập. Nếu graph đúng, đó là tối ưu an toàn; không phải thiếu task.

**Cách xử lý:** Nếu thực tế tools mới phụ thuộc contracts, cập nhật DEPENDS_ON và graph validation.

### Lỗi 4 — Thay build.gradle nhưng selector không chạy full suite

**Nguyên nhân:** Impact filter phân loại build.gradle như source file thông thường, không phát hiện dependency graph/tool change.

**Cách xử lý:** Global fallback cho Gradle scripts/locks, hoặc hệ thống graph diff có kiểm thử chính xác.

### Lỗi 5 — Thêm module mới rồi impact script bỏ qua nó

**Nguyên nhân:** MODULES constant chưa cập nhật. Script chỉ biết mô hình cũ.

**Cách xử lý:** Fail closed cho settings.gradle/unknown paths, và thêm CI contract test so list MODULES với Gradle projects thực tế. Full selector **check** tốt hơn một full list hardcode vì tự chọn check của module mới nếu nó khai báo task.

### Lỗi 6 — CI shallow checkout không tìm thấy merge-base

**Nguyên nhân:** Git history thiếu base commit.

**Cách xử lý:** Fetch đủ refs/history; khi chưa đủ, full fallback hoặc fail có diagnostics, không silently select empty tasks.

### Lỗi 7 — Rename file giữa modules chỉ chọn module mới

**Nguyên nhân:** Diff parser chỉ đọc destination path.

**Cách xử lý:** --no-renames để xét deletion + addition, hoặc parse name-status -z đúng cặp old/new.

### Lỗi 8 — app không compile được vì Invoice class missing

**Nguyên nhân:** billing khai implementation project(':contracts') nhưng public Billing.invoice trả Invoice, không export compile API dependency cho app.

**Cách xử lý:** Dùng **api project(':contracts')** tại billing, không thêm Project.tasks hack.

### Lỗi 9 — Đổi code body của contracts, app compile không chạy lại

**Giải thích:** Nếu ABI không đổi, Gradle compile avoidance có thể tránh downstream compile. Không tự suy rằng :app tests được skip an toàn.

**Cách xử lý:** Chọn downstream checks, để Gradle quyết định tasks thực sự cần chạy.

### Lỗi 10 — Chạy ./gradlew :check nhưng không có các subproject tests

**Nguyên nhân:** :check là path chỉ root project, không phải multi-project task selector.

**Cách xử lý:** Dùng **./gradlew check** từ root hoặc danh sách absolute :module:check tasks.

### Lỗi 11 — Chạy ./gradlew :app:check chỉ in check=app-pass

**Giải thích:** Expected trong lab: app checks không bao gồm smokeTest của các producer modules.

**Cách xử lý:** Chọn impacted closure checks như bảng.

### Lỗi 12 — Script impact in danh sách trống dù diff tool lỗi

**Nguyên nhân:** Lỗi subprocess bị nuốt, hoặc shell process substitution không kiểm tra exit code analyzer.

**Cách xử lý:** Phân biệt diff hợp lệ empty và error; error → full fallback hoặc fail CI. Script lab đã làm vậy.

### Lỗi 13 — Impacted tasks có đúng nhưng Gradle vẫn cấu hình nhiều projects

**Nguyên nhân:** Gradle mode, plugin application và configuration model không đồng nghĩa with selected task scope.

**Cách xử lý:** Đo config time, dùng Configuration Cache và chia sẻ build logic đúng cách; không hứa chỉ cấu hình modules được chọn trong mọi mode.

### Lỗi 14 — --parallel không giúp tăng tốc

**Nguyên nhân:** Graph critical path dài, CPU/memory bottleneck, tasks tranh tài nguyên hoặc runner quá nhỏ.

**Cách xử lý:** Phân tích timeline/critical path, điều chỉnh workers/test forks, tách tasks độc lập và cache outputs.

### Lỗi 15 — --continue làm một số tasks không chạy

**Nguyên nhân:** Các tasks đó phụ thuộc vào prerequisite đã fail; --continue không thể chạy chúng an toàn.

**Cách xử lý:** Xem Gradle failure graph; không coi --continue là ignore dependencies.

### Lỗi 16 — Dùng Configuration Cache nhưng cache hit thấp

**Nguyên nhân:** Tập selected tasks đổi thường xuyên, build logic/configuration inputs đổi hoặc plugin không tương thích.

**Cách xử lý:** Đo config cache entries, ổn định task groupings khi có ý nghĩa, xử lý violations; không bật/tắt mù quáng.

### Lỗi 17 — Tests local pass nhưng CI fail do JDK khác

**Nguyên nhân:** JDK/toolchain/Gradle Wrapper/locale/environment khác, hoặc dependency resolution khác.

**Cách xử lý:** Pin Gradle Wrapper, Java 17 toolchain, versions/locks, charset và CI environment; dùng same toolchains cho so sánh.

### Lỗi 18 — Build Cache FROM-CACHE bị hiểu là test chạy hôm nay

**Nguyên nhân:** Task output được restore, task action không thực thi trong invocation đó.

**Cách xử lý:** Báo đúng outcomes; nếu policy yêu cầu fresh execution, dùng flags phù hợp với những tasks cần.

### Lỗi 19 — Thay schema nhưng không module nào bị chọn

**Nguyên nhân:** Schema nằm ngoài mapped module directories; impact script default skip unknown.

**Cách xử lý:** Unknown/global fallback như lab, hoặc khai báo schema producer/dependency graph có kiểm thử.

### Lỗi 20 — Một module có nhiều variants/platforms nhưng graph chỉ có project name

**Nguyên nhân:** Static graph mất thông tin variant-specific dependencies.

**Cách xử lý:** Tăng độ chính xác ở mức variant/configuration hoặc chọn superset an toàn; không bỏ variants chưa rõ.

### Lỗi 21 — Task test của module fail nhưng shell script vẫn exit 0

**Nguyên nhân:** Shell pipeline nuốt exit code, đặt || true, hoặc một lệnh echo chạy cuối mà không propagate Gradle status.

**Cách xử lý:** set -e, không ignore Gradle failure, giữ command cuối là Gradle như script lab.

### Lỗi 22 — Mọi PR đều chạy full vì unknown paths quá nhiều

**Nguyên nhân:** Chính sách conservative đúng về correctness nhưng chưa phân loại tài nguyên/docs.

**Cách xử lý:** Thu thập telemetry, thêm verified mappings/allowlist theo module owners từng loại file, test policy bằng mutation scenarios, không xóa fallback hàng loạt.

### Lỗi 23 — CI mất nhiều thời gian compile upstream hơn chạy module QA

**Nguyên nhân:** Upstream producer outputs chưa có cache, compile classpath quá rộng, Gradle Wrapper/toolchain khác, hoặc remote Build Cache miss.

**Cách xử lý:** Pin toolchain, bật Build Cache, giảm unnecessary dependencies và đo critical path; không tự loại upstream producer tasks khỏi graph.

### Lỗi 24 — Full scheduled suite fail nhưng PR impacted suite pass

**Nguyên nhân có thể:** Impact mapping thiếu runtime edge, test-only fixture dependency, resource relationship hoặc flakiness.

**Cách xử lý:** Reproduce với same SHA/env, so selected tasks, xác định root cause; sửa graph/policy nếu false negative, điều tra flake nếu nondeterministic.

## 15. Checklist CI impact analysis trước khi dùng production

1. Đã phân biệt changed module và downstream dependents chưa?
2. Project dependency graph có phản ánh api/implementation/runtime/testFixtures/generation quan trọng?
3. Reverse transitive closure đã bao gồm module tự thay đổi?
4. Selected modules có chạy **check/test của chính chúng**, không chỉ compile?
5. Root task selector **check** khác **:check** đã được hiểu đúng?
6. Git diff base/head/merge-base được xác định theo workflow PR/push đúng?
7. Có đủ Git history để tìm merge-base?
8. Renames/deletions được xét cả old/new owners?
9. Files ngoài known module roots có safe fallback?
10. Settings/Wrapper/buildSrc/build-logic/CI scripts/dependency locks có full fallback?
11. Các file .gradle/.gradle.kts được coi là graph-affecting trừ khi đã có validated diff?
12. Graph mapping có CI integrity test với actual Gradle model?
13. New modules/configurations/variants được phát hiện?
14. Test fixture và runtime-only edges có được kiểm tra?
15. Non-Gradle E2E/contract/deploy gates không bị skip?
16. Analyzer failure không biến thành empty list và PASS?
17. Chọn task args mà không dùng eval/injection?
18. Gradle Wrapper/JDK pinned và môi trường consistent?
19. --parallel không tạo race/shared resources?
20. Build Cache/Configuration Cache đã được đo và xử lý compatibility?
21. Task outcome reports phân biệt executed/UP-TO-DATE/FROM-CACHE?
22. Có scheduled full checks và release gates?
23. Có log selected modules và lý do full fallback?
24. Có so impacted vs full failures trên sample PRs?
25. Có đo false-negative rate, task duration, cache misses, P95 latency?
26. Khi phát hiện graph drift, pipeline fail closed?
27. Có runbook cho “module bị bỏ sót” và “CI false green”?
28. Mỗi tối ưu thêm vào impact selection có tests trước khi triển khai rộng?

## 16. Bài tập

**Bài 1.** Trong đồ thị lab, thay code :contracts/src/main/java nên chọn các module check nào?

**Bài 2.** Thay riêng :tools/src/main/java cần chọn app checks không? Giải thích.

**Bài 3.** Vì sao :app:check không tự chứng minh :billing:check đã chạy?

**Bài 4.** Nếu chỉ đổi :billing, impacted set conservative là gì?

**Bài 5.** Thay settings.gradle được chọn impacted closure của một module hay full suite?

**Bài 6.** Đổi version catalog tại gradle/libs.versions.toml nên xử lý ra sao?

**Bài 7.** Vì sao đổi một method body mà ABI không đổi vẫn có thể yêu cầu :app integration tests?

**Bài 8.** Billing.invoice trả Invoice của :contracts; dependency phải dùng api hay implementation?

**Bài 9.** Notifier.hello chỉ dùng RecipientNames bên trong body; dependency nên dùng gì?

**Bài 10.** Trong multi-project build, ./gradlew check và ./gradlew :check khác nhau thế nào?

**Bài 11.** Task selector check có tự kiểm thử những service E2E ngoài Gradle không?

**Bài 12.** Khi Git merge-base fail do shallow clone, lựa chọn an toàn là gì?

**Bài 13.** Rename source file từ contracts/ sang tools/ có nên xét cả owner cũ và owner mới?

**Bài 14.** Vì sao dùng --no-renames trong script lab?

**Bài 15.** Script impact có nên skip file root không xác định không?

**Bài 16.** CI dùng --continue, vậy nếu billing:check fail thì job có thành công không?

**Bài 17.** --parallel có thể chạy app compile trước khi billing producer output được tạo không?

**Bài 18.** Build Cache có tự chọn impacted modules theo Git diff không?

**Bài 19.** Configuration Cache có đồng nghĩa chỉ cấu hình impacted projects không?

**Bài 20.** Nếu :contracts internal implementation đổi và Gradle tránh recompile app, pipeline có thể bỏ app checks luôn không?

**Bài 21.** Khi thêm tools implementation project(':contracts') nhưng quên đổi impact map, rủi ro lâu dài là gì?

**Bài 22.** Vì sao cần scheduled full suite dù impact selector đã có unit tests?

**Bài 23.** Nếu CI checkout HEAD là PR merge commit, tham số base/head cần xác định thế nào?

**Bài 24.** Nếu chỉ sửa comments trong Java source, có thể bỏ mọi checks không?

**Bài 25.** Vì sao fail-closed fallback làm pipeline chậm hơn nhưng vẫn là lựa chọn tốt khi không có owner?

**Bài 26.** Hãy đề xuất ba metrics để chứng minh tối ưu không làm giảm chất lượng.

### Gợi ý đáp án

1. **contracts, billing, notifications, app**; không cần tools trong đồ thị lab.
2. **Không**, :tools độc lập và không có downstream consumers theo model.
3. Project dependency truyền compile/runtime outputs, không mặc định truyền producer check/test tasks.
4. **billing, app**.
5. **Full suite**, vì project graph/configuration có thể đổi.
6. **Full suite** hoặc policy có graph resolution đủ mạnh để chứng minh scope; lab chọn full.
7. Runtime behavior/integration contract có thể thay dù public signatures không đổi.
8. **api project(':contracts')**, vì Invoice nằm trong public return type.
9. **implementation project(':contracts')**, vì đó là internal helper.
10. check không qualified là multi-project task selector; :check chỉ root task path.
11. **Không**, phải có CI gates riêng cho tests ngoài Gradle.
12. Fetch đủ lịch sử; nếu không thể, full fallback hoặc CI failure, không skip.
13. **Có**, vì cả module cũ/mới có thể chịu ảnh hưởng.
14. Để diff ghi delete+add và nhận cả old/new paths.
15. **Không**, unknown path thường dẫn đến full fallback.
16. **Không**, --continue thu failures khác nhưng build vẫn fail.
17. **Không**, Gradle task graph giữ producer prerequisites.
18. **Không**, Build Cache reuse outputs theo inputs/cache key.
19. **Không**, nó tối ưu configuration state reuse, không phân tích Git module impact.
20. **Không tự động**, vì runtime regression tests có thể vẫn liên quan.
21. PR sau này đổi contracts có thể bỏ tools checks; cần graph integrity verification.
22. Để phát hiện graph drift, non-code dependencies, test policy bugs và defects escape.
23. Dùng base/head SHAs của PR event đúng ngữ cảnh và merge-base; không mù quáng lấy HEAD.
24. Có thể tối ưu khi có analysis chứng minh nonfunctional, nhưng conservative baseline vẫn chạy scope; không mặc định skip.
25. Nó tránh false-green nghiêm trọng hơn chi phí chạy thêm tests.
26. Ví dụ **P95 latency**, **false-negative incidents**, **cache hit/avoided tasks**; phải đọc cùng test outcomes.

## 17. Tài liệu chính thức

- [Gradle User Manual — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): project paths, project dependency và task selection.
- [Gradle User Manual — Declaring Dependencies Between Subprojects](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): dependency edges, variant-aware resolution và module outputs.
- [Gradle User Manual — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api/implementation, ABI, consumer compileClasspath và compile avoidance.
- [Gradle User Manual — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): multi-project task selectors, task paths và execution flags.
- [Gradle User Manual — Gradle Command Line](https://docs.gradle.org/current/userguide/gradle_command_line.html): --continue, --dry-run, --parallel, --build-cache và --rerun-tasks.
- [Gradle User Manual — Improving Gradle Performance](https://docs.gradle.org/current/userguide/performance.html): parallelism, Build Cache, Configuration Cache, dependency resolution và Java compilation.
- [Gradle User Manual — Best Practices for Performance](https://docs.gradle.org/current/userguide/best_practices_performance.html): giảm configuration time/IO, cache và incremental build.
- [Gradle User Manual — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): input/output snapshots và task avoidance.
- [Gradle User Manual — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): local/remote task output reuse.
- [Gradle User Manual — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration model reuse và limitations.
- [Gradle User Manual — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): Test tasks, test suites và việc tổ chức unit/integration tests.
- [Gradle User Manual — Testing JVM Projects](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): JVM Test Suite Plugin cho test topology nhiều suite.
- [Gradle User Manual — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html): failure diagnostics, --continue và task reports.
- [Git Documentation — git-diff](https://git-scm.com/docs/git-diff): --name-only, --no-renames, -z, diff ranges.
- [Git Documentation — git-merge-base](https://git-scm.com/docs/git-merge-base): merge-base của hai refs trong PR workflows.

**Ghi nhớ:** Tối ưu pipeline không phải “chỉ build thư mục có Git diff”. Hãy tính **changed modules + downstream transitive consumers**, chọn **check tasks của chính những modules ấy**, để Gradle xây upstream producers cần thiết theo task graph, rồi tận dụng **parallelism, incremental compilation, UP-TO-DATE và Build Cache**. **Compile avoidance không thay thế runtime tests**. Khi graph/configuration không chắc, chạy **full selector check** và giữ scheduled/release full gates. Một pipeline nhanh chỉ có ý nghĩa khi không làm giảm khả năng phát hiện regression.