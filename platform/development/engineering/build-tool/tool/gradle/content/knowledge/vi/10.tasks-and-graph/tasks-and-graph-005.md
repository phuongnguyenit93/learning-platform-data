# `dependsOn`, `mustRunAfter`, `shouldRunAfter` và `finalizedBy` trong Gradle

## 1. Mục tiêu và tình huống thực tế

Trong Gradle, **task graph (đồ thị công việc)** xác định những task nào phải được đưa vào một lần chạy, task nào cần hoàn thành trước task nào và task nào sẽ dọn dẹp sau công việc chính. Bốn API rất dễ bị nhầm lẫn:

- `dependsOn` — **task A cần task B**: chọn A thì Gradle đưa B vào đồ thị và chạy B trước A.
- `mustRunAfter` — **nếu cả A lẫn B cùng được chọn, A nhất định chạy sau B**; nhưng chọn A **không tự chọn B**.
- `shouldRunAfter` — **nếu cả hai cùng được chọn, ưu tiên A sau B**; là thứ tự mềm, Gradle có thể bỏ qua trong những điều kiện xác định.
- `finalizedBy` — **khi task A được lên lịch, thêm task F để kết thúc/dọn dẹp sau A**; F vẫn được thực thi trong những trường hợp A thất bại hoặc `UP-TO-DATE`.

Bốn API này không tương đương với viết bốn dòng lệnh theo thứ tự trong một shell. Gradle xây **đồ thị có hướng**, phân giải dependency, tránh vòng lặp không hợp lệ, lập lịch song song khi có thể, rồi thực thi task hoặc bỏ qua task đã `UP-TO-DATE`.

Sau bài này bạn sẽ biết cách khai báo quan hệ đúng mục đích, dự đoán tập task được chọn và thứ tự kết quả, nhận diện lỗi graph cycle, đồng thời dùng `tasks.register` / `TaskProvider` để không ép cấu hình task sớm.

## 2. Phân biệt hai loại cạnh trong task graph

Hãy tưởng tượng hai task `prepare` và `packageDemo`. Nếu việc đóng gói **thực sự cần** kết quả chuẩn bị, đồ thị cần cạnh dependency:

```text
Chạy packageDemo
      |
      v
  prepare  --->  packageDemo
 (bắt buộc)       (được yêu cầu)
```

Còn hai task `audit` và `publishDemo` có thể được chạy độc lập nhưng nếu người dùng chọn cả hai, `audit` phải đi trước:

```text
Khi CHỈ chọn publishDemo:    publishDemo

Khi chọn CẢ HAI:
    audit  - - - ->  publishDemo
          ordering only
```

Cạnh thứ hai không tạo dependency. Đó là khác biệt quan trọng nhất giữa `dependsOn` và `mustRunAfter`/`shouldRunAfter`.

| API trên task A | Có thêm task B vào lần chạy khi chỉ chọn A? | Ràng buộc thứ tự | Trường hợp dùng |
| --- | --- | --- | --- |
| `A.dependsOn(B)` | **Có** | B trước A, nếu B đã hoàn tất hợp lệ | A cần output/công việc của B |
| `A.mustRunAfter(B)` | **Không** | B trước A nếu cả hai đã được chọn | Hai task độc lập nhưng yêu cầu thứ tự nghiêm ngặt |
| `A.shouldRunAfter(B)` | **Không** | Ưu tiên B trước A; được phép bỏ qua khi cần | Thứ tự mong muốn nhưng không thiết yếu |
| `A.finalizedBy(F)` | **Có**, F được thêm khi A được lên lịch | F chạy sau A để hoàn tất/dọn dẹp | Giải phóng resource, đóng service, cleanup |

**Độ mạnh của quan hệ:** Gradle gọi `dependsOn` và `finalizedBy` là **strong relationships** vì có thể đưa task liên quan vào graph. `mustRunAfter` và `shouldRunAfter` là **soft relationships** theo nghĩa không buộc task còn lại được chọn/cấu hình chỉ bởi quan hệ thứ tự; tuy nhiên hai ordering rule khác nhau về độ nghiêm ngặt. “Soft relationship” không đồng nghĩa `mustRunAfter` là tùy chọn.

**Không nhầm dependency giữa tasks với dependency thư viện:** `dependsOn(tasks.named("prepare"))` chỉ điều khiển **Gradle task graph**. `dependencies { implementation("...") }` hoặc `implementation(project(":lib"))` điều khiển **phụ thuộc mã/artifact**; chúng có thể dẫn đến task dependencies gián tiếp, nhưng là API và mô hình khác.

## 3. Demo hoàn chỉnh: một `build.gradle.kts`, bốn loại quan hệ

Dự án tối giản dùng **Gradle Kotlin DSL**, không cần Java source hoặc plugin bên ngoài. Tạo thư mục với các file:

```text
task-graph-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
```

Nếu đã có repository với Wrapper, dùng Wrapper hiện có và tạo hai script trong một project demo riêng. Nếu chưa có, cần Gradle cài tạm để khởi tạo Wrapper (`gradle wrapper`), rồi commit đủ bốn file Wrapper khi đưa vào Git.

`settings.gradle.kts`:

```kotlin
rootProject.name = "task-graph-demo"
```

`build.gradle.kts` — **đầy đủ, thay cho mọi đoạn code rời sau nếu muốn chạy nguyên bài demo**:

```kotlin
// 1. Hai task có dependency thực sự:
val prepare = tasks.register("prepare") {
    group = "learning"
    doLast { println("prepare") }
}

tasks.register("packageDemo") {
    group = "learning"
    dependsOn(prepare)
    doLast { println("packageDemo") }
}

// 2. Hai task có thể chạy độc lập nhưng yêu cầu thứ tự:
val audit = tasks.register("audit") {
    group = "learning"
    doLast { println("audit") }
}

tasks.register("publishDemo") {
    group = "learning"
    mustRunAfter(audit)
    doLast { println("publishDemo") }
}

// 3. Hai task kiểm thử độc lập, chỉ ưu tiên thứ tự:
val quickTest = tasks.register("quickTest") {
    group = "learning"
    doLast { println("quickTest") }
}

val slowTest = tasks.register("slowTest") {
    group = "learning"
    shouldRunAfter(quickTest)
    doLast { println("slowTest") }
}

tasks.register("checkAll") {
    group = "learning"
    dependsOn(quickTest, slowTest)
    doLast { println("checkAll") }
}

// 4. Một task có bước cấp phát và bước dọn dẹp:
val acquireResource = tasks.register("acquireResource") {
    group = "learning"
    doLast { println("acquireResource") }
}

val releaseResource = tasks.register("releaseResource") {
    group = "learning"
    doLast { println("releaseResource") }
}

tasks.register("runScenario") {
    group = "learning"
    dependsOn(acquireResource)
    finalizedBy(releaseResource)
    doLast { println("runScenario") }
}
```

**Các dòng quan trọng:**

- `tasks.register("name")` trả về một `TaskProvider` để **đăng ký task lazy**; đoạn code không cần `tasks.getByName` hay `tasks.create`.
- `dependsOn(prepare)` và `mustRunAfter(audit)` có thể nhận provider, không cần gọi `prepare.get()` để force-realize task.
- `checkAll` chủ động chọn **hai task kiểm thử**, còn `shouldRunAfter` chỉ cung cấp lời khuyên thứ tự giữa chúng.
- `runScenario` vừa **phụ thuộc** vào việc cấp phát, vừa có **finalizer** để giải phóng tài nguyên sau khi chính nó chạy.
- Chỉ có task actions `doLast` in stdout; đăng ký quan hệ trong configuration **không tự chạy những action này**.

Các task `packageDemo`, `publishDemo` và `runScenario` là ví dụ in chuỗi, không thực sự đóng gói, phát hành hay mở service. Điều này cố ý giúp phân biệt **task scheduling** mà không cần network, credentials hoặc resource bên ngoài.

**Quy ước lệnh:** Linux/macOS dùng `./gradlew`; Windows PowerShell dùng `.\gradlew.bat`; Command Prompt dùng `gradlew.bat`. Lệnh chạy từ root của demo. `-q` giảm log Gradle; các dòng stdout được mô tả bên dưới là những dòng do task `println` tạo ra, không nhất thiết là toàn bộ console output nếu môi trường có cảnh báo.

## 4. `dependsOn` — ràng buộc công việc bắt buộc

### 4.1. Khi chọn A, Gradle chọn cả B

Lệnh:

```bash
./gradlew -q packageDemo
```

Với `build.gradle.kts` phần 3, stdout do tasks in ra **chính xác theo thứ tự**:

```text
prepare
packageDemo
```

Vì `packageDemo.dependsOn(prepare)`, Gradle phải đưa `prepare` vào graph và hoàn thành `prepare` trước `packageDemo`. Nếu chỉ chạy:

```bash
./gradlew -q prepare
```

Thì chỉ thấy:

```text
prepare
```

Dependency có hướng: A phụ thuộc B không có nghĩa B phụ thuộc A.

### 4.2. Dependency bắc cầu (transitive)

Khi:

```kotlin
val cleanInput = tasks.register("cleanInput") {
    doLast { println("cleanInput") }
}

val generateData = tasks.register("generateData") {
    dependsOn(cleanInput)
    doLast { println("generateData") }
}

tasks.register("consumeData") {
    dependsOn(generateData)
    doLast { println("consumeData") }
}
```

Đây là **một đoạn Kotlin DSL riêng** để thêm vào demo. Nếu gọi `./gradlew -q consumeData`, Gradle đưa cả ba task vào graph và stdout liên quan theo thứ tự:

```text
cleanInput
generateData
consumeData
```

Không cần viết thêm `consumeData.dependsOn(cleanInput)` vì cạnh phụ thuộc qua `generateData` đã ràng buộc thứ tự.

### 4.3. Nhiều dependency không có thứ tự anh em mặc định

Nếu viết:

```kotlin
tasks.register("assembleDocs") {
    dependsOn("generateHtml", "generatePdf")
}
```

Thì cả `generateHtml` và `generatePdf` phải xong trước `assembleDocs`. **Thứ tự giữa `generateHtml` và `generatePdf` không tự được bảo đảm** chỉ vì tên của chúng xuất hiện trước/sau trong `dependsOn(...)`. Nếu hai task độc lập, Gradle có thể chạy chúng theo thứ tự khác hoặc song song. Nếu thật sự cần `generateHtml` trước `generatePdf`, quan hệ đó phải được mô tả riêng bằng dependency hoặc `mustRunAfter`, tùy chúng có **cần dữ liệu** của nhau hay chỉ cần thứ tự.

`dependsOn` là nơi đặt **mối quan hệ cần thiết để có kết quả đúng**. Không dùng `mustRunAfter` thay thế nó khi output của B là đầu vào bắt buộc của A.

### 4.4. Không nhầm `dependsOn` với luồng dữ liệu

`dependsOn(B)` chỉ nói B phải hoàn thành trước A. Nó **không khai báo A đọc file nào** do B tạo, file phải được fingerprint ra sao hoặc task nào có thể `UP-TO-DATE`. Khi làm task tạo/tiêu thụ file, nên kết nối **`RegularFileProperty`/`DirectoryProperty`/`Provider`** của producer và consumer, kèm `@OutputFile` và `@InputFile` thích hợp.

Một Provider của output task thường tạo **dependency suy luận (inferred task dependency)** khi đưa vào input của task khác, giúp Gradle hiểu cả luồng dữ liệu và thứ tự. Tránh truyền chuỗi path có cùng tên rồi mong Gradle tự đoán producer. Nếu cần chỉ định một task chạy trước vì side effect không được biểu diễn bằng file/provider, `dependsOn` tường minh phù hợp hơn một ordering rule.

## 5. `mustRunAfter` — thứ tự cứng, nhưng không kéo task vào graph

Trong demo:

```kotlin
val audit = tasks.register("audit") {
    doLast { println("audit") }
}

tasks.register("publishDemo") {
    mustRunAfter(audit)
    doLast { println("publishDemo") }
}
```

Đây là **trích đoạn của cấu hình chính**, không cần dán lại nếu đã dùng file phần 3.

### 5.1. Chỉ chạy task phía sau

```bash
./gradlew -q publishDemo
```

Stdout:

```text
publishDemo
```

**Không có** `audit`, vì `mustRunAfter` không yêu cầu Gradle tự thêm `audit`.

### 5.2. Chọn cả hai, bất kể thứ tự gõ lệnh

```bash
./gradlew -q publishDemo audit
```

Stdout:

```text
audit
publishDemo
```

Dù gõ `publishDemo` trước, task `audit` phải hoàn thành trước `publishDemo`. Nếu gõ ngược:

```bash
./gradlew -q audit publishDemo
```

Kết quả do task in vẫn như trên.

**Sử dụng phù hợp:** muốn đảm bảo tác vụ xác minh `audit` chạy trước tác vụ `publishDemo` **khi cả hai đều được yêu cầu**, nhưng vẫn cho phép gọi riêng từng task. Nếu phát hành **tuyệt đối không được xảy ra thiếu xác minh**, chỉ `mustRunAfter(audit)` là không đủ: phải khai báo `dependsOn(audit)` hoặc thiết kế workflow/policy chặn release khi thiếu kết quả.

### 5.3. Khác biệt khi task trước thất bại

Thứ tự không tạo dependency thành công/thất bại. Với `--continue`, Gradle có thể tiếp tục các task **không phụ thuộc vào task lỗi** sau khi task đứng trước theo `mustRunAfter` thất bại.

Giả sử thêm hai task riêng:

```kotlin
val deliberateFailure = tasks.register("deliberateFailure") {
    doLast {
        println("deliberateFailure")
        throw GradleException("Lỗi demo")
    }
}

tasks.register("afterFailure") {
    mustRunAfter(deliberateFailure)
    doLast { println("afterFailure") }
}
```

Khi chạy:

```bash
./gradlew -q --continue afterFailure deliberateFailure
```

Task `deliberateFailure` sẽ in `deliberateFailure` rồi ném lỗi. Với `--continue`, task `afterFailure` có thể vẫn chạy và in `afterFailure` vì hai task **không có quan hệ dependsOn**. Toàn bộ build **vẫn FAILED**; `--continue` không chuyển lỗi thành thành công. Không nên dùng `mustRunAfter` để che một điều kiện bắt buộc cho việc phát hành.

## 6. `shouldRunAfter` — thứ tự mềm, có ngoại lệ

Ví dụ demo:

```kotlin
val quickTest = tasks.register("quickTest") {
    doLast { println("quickTest") }
}

val slowTest = tasks.register("slowTest") {
    shouldRunAfter(quickTest)
    doLast { println("slowTest") }
}
```

Gọi riêng `slowTest`:

```bash
./gradlew -q slowTest
```

Stdout:

```text
slowTest
```

Gọi cả hai:

```bash
./gradlew -q slowTest quickTest
```

Trong build đơn giản, không chạy song song và không có cycle, Gradle ưu tiên `quickTest` trước `slowTest`:

```text
quickTest
slowTest
```

**Hai ngoại lệ quan trọng theo Gradle:**

1. Nếu tuân theo `shouldRunAfter` sẽ tạo **vòng thứ tự**, Gradle có thể bỏ qua quan hệ mềm để giải được graph.
2. Khi **parallel execution**, nếu các dependency bắt buộc khác đã được thỏa mãn và chờ quan hệ mềm làm mất cơ hội chạy, Gradle có thể cho task chạy mà **không đợi** task `shouldRunAfter`.

Vì vậy `shouldRunAfter` chỉ phù hợp cho **ưu tiên có tính gợi ý**, ví dụ muốn các kiểm thử nhanh chạy trước kiểm thử lâu để có feedback sớm. Nó không phải cách đồng bộ hóa truy cập tài nguyên chung hoặc bảo đảm một bước phải hoàn thành trước bước tiếp theo.

Nếu `slowTest` cần artifact do `quickTest` tạo ra, dùng `dependsOn` hoặc input/output provider; không dùng `shouldRunAfter`.

## 7. `finalizedBy` — task dọn dẹp đi theo task chính

`finalizedBy` tạo liên kết **task chính → finalizer**. Khi task chính được lên lịch, Gradle cũng thêm finalizer vào graph và chạy nó **sau task chính**.

Trong demo:

```kotlin
val acquireResource = tasks.register("acquireResource") {
    doLast { println("acquireResource") }
}

val releaseResource = tasks.register("releaseResource") {
    doLast { println("releaseResource") }
}

tasks.register("runScenario") {
    dependsOn(acquireResource)
    finalizedBy(releaseResource)
    doLast { println("runScenario") }
}
```

Chạy:

```bash
./gradlew -q runScenario
```

Stdout do task in:

```text
acquireResource
runScenario
releaseResource
```

Giải nghĩa:

- `acquireResource` được kéo vào do `dependsOn` và chạy trước `runScenario`.
- `releaseResource` được kéo vào do `finalizedBy` và chạy sau `runScenario`.
- Nếu chỉ gọi `./gradlew -q acquireResource`, Gradle **không tự gọi** `runScenario` hay `releaseResource`, vì finalizer gắn với `runScenario` chứ không gắn với `acquireResource`.
- Có thể chạy `releaseResource` độc lập nếu yêu cầu; quan hệ finalizer không cấm điều đó.

### 7.1. Khi task chính thất bại

Theo Gradle, finalizer vẫn chạy khi **chính task được finalize thực thi rồi thất bại**. Bạn có thể thêm đoạn sau vào `build.gradle.kts` của demo:

```kotlin
tasks.register("runScenarioFails") {
    finalizedBy(tasks.named("releaseResource"))
    doLast {
        println("runScenarioFails")
        throw GradleException("Lỗi có chủ đích để kiểm tra cleanup")
    }
}
```

Chạy:

```bash
./gradlew -q runScenarioFails
```

Phần dòng do task in theo thứ tự:

```text
runScenarioFails
releaseResource
```

Gradle còn in lỗi, báo `BUILD FAILED` và trả **exit code khác 0**. Finalizer chạy **không làm lỗi của task chính biến mất**.

### 7.2. Khi task chính `UP-TO-DATE`

Nếu task chính có inputs/outputs hợp lệ và được đánh dấu `UP-TO-DATE`, Gradle vẫn có thể thực thi finalizer đã gắn. Lý do: tác vụ cleanup không bị loại chỉ vì artifact của task chính đã có sẵn. Trong ví dụ chỉ có `println`, các task không khai báo outputs nên không thể dùng ví dụ này để kiểm thử trạng thái `UP-TO-DATE`; để kiểm tra hành vi đó hãy dùng task thực sự khai báo output và không thay đổi input giữa hai lần gọi.

**Cảnh báo giới hạn:** `finalizedBy` **không phải** bảo đảm kiểu hệ điều hành/transaction. Nó không chạy trong mọi tình huống: nếu task chính chưa bắt đầu do dependency thất bại và Gradle dừng trước đó, hoặc tiến trình/host bị kill, hoặc runner mất điện, không nên coi cleanup đã chắc chắn xảy ra. Với resource bên ngoài, bổ sung timeout, logic cleanup độc lập, idempotency và `finally`/resource-management ở **bên trong task action** nếu cần.

### 7.3. Đừng dùng `finalizedBy` cho mọi bước hậu xử lý

- Nếu `publish` bắt buộc cần file package trước, dùng `dependsOn(package)`.
- Nếu muốn dọn resource của `integrationTest` ngay cả khi bài test lỗi, `integrationTest.finalizedBy(stopServer)` là một thiết kế có cơ sở.
- Nếu `report` chỉ nên tạo khi test **thành công**, không mặc định `test.finalizedBy(report)` vì finalizer còn chạy khi test fail. Thường báo cáo kiểm thử được chính test task/plugin tạo ra, hoặc xây task orchestration phù hợp.
- Nếu có **nhiều finalizer**, đừng giả định thứ tự giữa các finalizer trừ khi được khai báo riêng.

## 8. Đồ thị trực quan: bốn trường hợp đặt cạnh nhau

```text
(A) Dependency
    prepare ----> packageDemo
    Chọn packageDemo: chạy prepare, rồi packageDemo.

(B) Hard ordering
    audit - - -> publishDemo
    Chọn publishDemo: CHỈ publishDemo.
    Chọn cả audit, publishDemo: audit trước.

(C) Soft ordering
    quickTest - ~ -> slowTest
    Chọn slowTest: CHỈ slowTest.
    Chọn cả hai: ưu tiên quickTest trước; có ngoại lệ.

(D) Finalizer
    acquireResource ----> runScenario =====> releaseResource
            dependsOn         finalizedBy
    Chọn runScenario: cả ba có mặt, cleanup sau runScenario.
```

Ký hiệu `---->` ở (A) là thứ tự do dependency tạo ra, `- - ->` chỉ thứ tự không kéo task, `- ~ ->` là thứ tự mềm và `=====>` tượng trưng finalizer. Đây là sơ đồ khái niệm; không phải định dạng graph chính thức của Gradle.

## 9. Mối quan hệ mạnh/yếu và chi phí cấu hình

Trong một build lớn, task có thể được đăng ký **lazily**:

```kotlin
val compile = tasks.register("compileDemo") {
    doLast { println("compileDemo") }
}

tasks.register("packageArchive") {
    dependsOn(compile)
    doLast { println("packageArchive") }
}
```

Hãy tránh:

```kotlin
// Ví dụ anti-pattern khi chỉ cần tham chiếu:
val compile = tasks.getByName("compileDemo")
```

`getByName` lấy task object trực tiếp, có thể ép task bị realize sớm. `tasks.register`, `tasks.named`, `TaskProvider` và `configureEach` giúp cấu hình tránh công việc không cần thiết.

**Cách Gradle phân biệt quan hệ khi lập graph:**

- `dependsOn` và `finalizedBy` là **strong**: nếu task chính được chọn, task liên quan phải được resolve/realize để xây graph (trừ các điều kiện khác của build).
- `mustRunAfter` và `shouldRunAfter` là **soft** theo nghĩa không làm Gradle kéo task còn lại vào graph chỉ để tạo thứ tự.
- Các quan hệ không cần `TaskProvider.get()` để khai báo; truyền provider trực tiếp giúp giữ cấu hình lazy.

**Điều quan trọng:** `mustRunAfter` mạnh về **thứ tự thực thi**, nhưng mềm về **việc chọn thêm task**. Từ “strong/soft relationship” trong task configuration avoidance nói về khả năng buộc task liên quan được tạo/chọn; khác với chữ “cứng/mềm” dùng để phân biệt `mustRunAfter` và `shouldRunAfter`.

## 10. Vòng lặp trong task graph và cách xử lý

### 10.1. Vòng dependency là lỗi thực sự

```kotlin
val alpha = tasks.register("alpha")
val beta = tasks.register("beta")

alpha.configure {
    dependsOn(beta)
}
beta.configure {
    dependsOn(alpha)
}
```

Đoạn này **minh họa lỗi, không thêm vào demo chính**. Khi Gradle cố tạo graph để chạy `alpha` hoặc `beta`, các cạnh tạo vòng: `alpha → beta → alpha`. Gradle sẽ báo lỗi circular dependency, chứ không tự chọn một thứ tự tùy ý.

Cần sửa **mô hình nghiệp vụ**: tách dữ liệu chung, chia task thành bước nhỏ, loại dependency sai hoặc chuyển một cạnh sang ordering rule **chỉ nếu** task không thật sự cần output của nhau. Không dùng `shouldRunAfter` để che dependency vòng vốn cần một chu trình dữ liệu rõ ràng.

### 10.2. Vòng thứ tự mềm có thể bị bỏ qua

```kotlin
val one = tasks.register("one")
val two = tasks.register("two")
val three = tasks.register("three")

one.configure { dependsOn(two) }
two.configure { dependsOn(three) }
three.configure { shouldRunAfter(one) }
```

Trong chuỗi bắt buộc `three → two → one`, việc `three.shouldRunAfter(one)` sẽ tạo vòng ngược. Gradle có thể **bỏ qua `shouldRunAfter`** để tuân thủ các dependency, thay vì làm build thất bại. Kết quả hành động vẫn cần ba task theo thứ tự dependency, nếu chúng được chọn đúng. Nếu thay bằng `mustRunAfter`, bạn đã đặt ràng buộc cứng xung đột, Gradle có thể báo không lập được graph.

**Bài học:** dùng `shouldRunAfter` khi phá bỏ ưu tiên thứ tự vẫn **đúng về dữ liệu**. Không dùng nó cho task cần file được tạo từ task khác.

## 11. `--parallel`, `--continue` và `UP-TO-DATE` ảnh hưởng thế nào?

### 11.1. Chạy song song

```bash
./gradlew checkAll --parallel
```

Trong một **single-project build** như demo, `--parallel` không nhất thiết tạo song song cho các task tùy chỉnh: Gradle thường dùng khả năng parallel scheduling qua nhiều project, còn các task trong một project không nên mặc định coi là chạy song song. Tùy phiên bản, tính năng và build, mức độ song song khác nhau. Dù vậy:

- `dependsOn` phải bảo đảm prerequisite hoàn thành trước dependent.
- `mustRunAfter` yêu cầu thứ tự nếu cả hai task cùng xuất hiện.
- `shouldRunAfter` có thể bị bỏ qua để không làm mất parallelism.
- `finalizedBy` bảo đảm finalizer được xếp sau task nó kết thúc, theo quy tắc của Gradle.

Không dùng `shouldRunAfter` hoặc hy vọng thứ tự command-line để khóa shared file/port; nếu có resource chung, dùng dependency chính xác, Gradle Build Service với `maxParallelUsages` hoặc thiết kế task inputs/outputs/locking phù hợp.

### 11.2. `--continue`

Khi một task lỗi, Gradle thường dừng các công việc chưa bắt đầu và báo thất bại. `--continue` cho phép thử các task **không bị chặn bởi dependency thất bại**, để gom nhiều lỗi trong một lần chạy:

```bash
./gradlew test integrationTest --continue
```

Lệnh trên chỉ hợp lệ khi build thực sự có `test` và `integrationTest` (không phải core tasks tự có ở mọi build). Nếu `integrationTest.dependsOn(test)` và `test` fail, `integrationTest` không thể coi prerequisite đã thành công. Nếu chỉ có `integrationTest.mustRunAfter(test)`, `integrationTest` có thể vẫn chạy dưới `--continue`. Đây là lý do phải chọn **dependency** cho điều kiện bắt buộc.

### 11.3. Up-to-date, skip và cache

`dependsOn` làm prerequisite xuất hiện trong graph, **không bảo đảm mọi `doLast` thực thi lại**. Task có output hợp lệ có thể `UP-TO-DATE` hoặc nhận kết quả từ build cache. Điều cần bảo đảm là **điều kiện kết quả/đầu vào đã thỏa mãn**, không phải số lần in log.

`finalizedBy` được Gradle thiết kế để vẫn thực thi finalizer ngay cả khi task chính `UP-TO-DATE`, nhưng finalizer cũng có logic riêng về skip/up-to-date nếu được cấu hình. Các task demo không khai báo file output nên hành vi thực thi lại/skip của chúng khác task biên dịch Java.

`--dry-run` (hoặc `-m`) cho phép **xem những task dự định có mặt trong graph và thứ tự dự kiến** mà không chạy actions:

```bash
./gradlew packageDemo --dry-run
./gradlew publishDemo audit --dry-run
./gradlew runScenario --dry-run
```

Khi dry-run, Gradle vẫn có thể **configure build**, tải plugin hoặc kiểm tra một số đầu vào cấu hình; nó không chứng minh task action sẽ thành công. Đừng dùng `--dry-run` để kiểm thử cleanup thật, bởi vì cleanup action không chạy.

## 12. Tác động trên multi-project build

Task path đầy đủ có dạng `:project:task`, chẳng hạn `:app:test` hoặc `:lib:jar`. Tên task ngắn như `test` có thể chọn task cùng tên trong nhiều project; khi muốn quan hệ giữa hai module, cần hiểu project nào sở hữu task đó.

Ví dụ **mô hình**:

```text
:lib:generateSchema -> :app:verifySchema -> :app:publish
```

Nếu `:app:verifySchema` cần file mà `:lib:generateSchema` tạo ra, cách tốt là **xuất artifact/Provider qua mô hình Gradle** hoặc khai báo project dependency phù hợp. Tham chiếu trực tiếp task khác project bằng path có thể giải quyết tình huống nhỏ, nhưng lạm dụng cross-project configuration làm khó Isolated Projects và configuration cache.

Trong script Groovy DSL của project `:app`, khi cần một task path cụ thể, có thể gặp:

```groovy
tasks.named('verifySchema') {
    dependsOn(':lib:generateSchema')
}
```

Đây là **đoạn minh họa trong build có đủ các project/task tương ứng**, không phải demo độc lập. Dùng path tuyệt đối từ root để tránh nhầm task của `:app` với project `:lib`. Tuy nhiên nếu nhiệm vụ là **tiêu thụ output có kiểu**, nên dùng quan hệ producer/consumer và mô hình artifacts thay vì path string hardcode giữa các module.

Khi nhiều task không cùng tên nhưng chia sẻ đầu ra, không chỉ thêm `mustRunAfter` để “chữa” file race. Cần sửa thiết kế để outputs không trùng và task inputs/outputs được khai báo; thứ tự có thể che lỗi trong một số lần chạy nhưng vẫn tạo build khó cache/tái lập.

## 13. Kotlin DSL và Groovy DSL: cùng ý nghĩa, khác cú pháp

Kotlin DSL trong `build.gradle.kts`:

```kotlin
val scan = tasks.register("scan") {
    doLast { println("scan") }
}
val report = tasks.register("report") {
    dependsOn(scan)
    doLast { println("report") }
}
```

Groovy DSL trong `build.gradle`, **là file thay thế**, không dán chung vào `build.gradle.kts`:

```groovy
def scan = tasks.register('scan') {
    doLast { println 'scan' }
}
def report = tasks.register('report') {
    dependsOn(scan)
    doLast { println 'report' }
}
```

Cả hai cùng biểu đạt `report` cần `scan`. Với các phương thức còn lại:

| Kotlin DSL | Groovy DSL |
| --- | --- |
| `dependsOn(otherTask)` | `dependsOn(otherTask)` |
| `mustRunAfter(otherTask)` | `mustRunAfter(otherTask)` |
| `shouldRunAfter(otherTask)` | `shouldRunAfter(otherTask)` |
| `finalizedBy(cleanupTask)` | `finalizedBy(cleanupTask)` |
| `tasks.named("test") { ... }` | `tasks.named('test') { ... }` |

Trong Groovy có các dạng không ngoặc được DSL cho phép, nhưng thống nhất dùng **có ngoặc** giúp đọc và chuyển đổi giữa hai DSL dễ hơn. Các ví dụ của bài không yêu cầu áp dụng Java plugin, vì task tự tạo bằng `tasks.register`; `test`, `jar`, `build` trong dự án thật phụ thuộc plugin đã apply.

## 14. Tình huống quyết định: chọn API nào?

### Tình huống A — Sinh source trước khi compile

Task `compileGeneratedSources` **cần** source do `generateSources` tạo ra. Dùng `dependsOn` (tốt hơn nữa là wire output Provider vào source inputs để Gradle suy luận dependency). `mustRunAfter` không đủ vì khi chỉ gọi compile, task generate sẽ không tự được chọn.

### Tình huống B — Unit test nên chạy trước integration test để phát hiện lỗi sớm

Hai test độc lập, CI muốn phản hồi sớm mà không bắt buộc làm theo thứ tự. Dùng `integrationTest.shouldRunAfter(test)`. Nếu integration test **bắt buộc** cần database snapshot từ một setup task thì snapshot setup phải nằm trong `dependsOn` riêng.

### Tình huống C — Migration không được chạy đồng thời với import, nhưng mỗi task có thể chạy riêng

Nếu cả hai task được chọn trong một build và có yêu cầu thứ tự nghiêm ngặt, dùng `importTask.mustRunAfter(migrationTask)`. **Không đủ** nếu hệ thống cần khóa giữa hai **build khác nhau** chạy đồng thời trên hai CI runners: dùng database lock/transaction hoặc orchestration bên ngoài, không chỉ Gradle task ordering.

### Tình huống D — Server phải dừng sau integration test

`integrationTest.dependsOn(startServer)` và `integrationTest.finalizedBy(stopServer)`. Thiết kế finalizer giúp cleanup ngay cả khi test task báo lỗi. Khi có khả năng server startup thất bại trước khi test bắt đầu, cần cơ chế cleanup trong server launcher hoặc CI `always()` tương ứng; finalizer gắn vào test chưa chắc được chạy nếu test chưa tới lượt.

### Tình huống E — Release phải trải qua security scan

Nếu release chỉ hợp lệ sau security scan, dùng `release.dependsOn(securityScan)`, không dùng `release.mustRunAfter(securityScan)`. Cái thứ hai cho phép gọi release riêng và bỏ hẳn scan.

### Tình huống F — Tạo báo cáo cuối một task thất bại

Nếu task `summarizeFailures` cần chạy **bất kể** task test bị fail để đọc kết quả đã có, có thể dùng `test.finalizedBy(summarizeFailures)`. Nhưng nếu report logic **không xử lý được khi test fail** thì không nên dùng finalizer như một “catch all”; kiểm tra report task đúng input/output và có xử lý file thiếu. Khả năng ra báo cáo cuối pipeline trên CI cũng có thể cần `if: always()` hoặc giải pháp tương đương.

### Tình huống G — Hai task dùng chung một thư mục output

Không nên chọn bừa `mustRunAfter` để biến shared output thành an toàn. Gradle có thể không hiểu task input/output, build cache và incremental build sẽ không tin cậy. Chỉnh tasks để ghi output riêng, khai báo file property và dependency luồng dữ liệu; chỉ thêm ordering nếu vẫn có tài nguyên chung không thể tránh.

## 15. Các lỗi phổ biến và hướng điều tra

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Chạy `publishDemo` nhưng `audit` không chạy | Chỉ khai báo `mustRunAfter` | Nếu audit bắt buộc, đổi sang `dependsOn`; nếu độc lập thì đây là hành vi đúng |
| Chạy `slowTest` nhưng `quickTest` không chạy | `shouldRunAfter` không kéo task vào graph | Chọn cả hai qua CLI/aggregate task, hoặc đổi sang dependency nếu bắt buộc |
| Chạy một aggregate task nhưng các prerequisite đảo thứ tự | `dependsOn(A, B)` không định thứ tự A/B | Nếu cần thứ tự cứng, khai báo dependency hoặc `mustRunAfter` phù hợp |
| Thứ tự `shouldRunAfter` bị đảo khi `--parallel` | Ordering mềm có thể bị bỏ qua vì parallel scheduling | Nếu không thể đảo, dùng `mustRunAfter` (thứ tự) hoặc `dependsOn` (yêu cầu chạy) |
| Gradle báo circular dependency | `dependsOn` có vòng hoặc ordering rule cứng xung đột | Vẽ graph nhỏ, bỏ cạnh sai, tách task, dùng provider output đúng hướng |
| Task cleanup không chạy khi task setup fail | Task được finalize chưa thực thi vì prerequisite fail | Đặt cleanup tại đúng owner resource; thiết kế cleanup ở launcher/CI |
| Cleanup chạy khi test `UP-TO-DATE` | `finalizedBy` còn gọi finalizer | Đây có thể là đúng; kiểm tra finalizer có side effect cần giới hạn không |
| Task `UP-TO-DATE`, không in log như lần đầu | Task action được skip vì output/input đã hợp lệ | Đọc Gradle task outcome; đừng dùng log action làm bằng chứng graph mất dependency |
| Task A và B cùng chạy nhưng B thấy file thiếu | Chỉ đặt ordering, chưa có dependency/typed input | Wire output của producer vào input consumer; khai báo annotations |
| Task trở nên chậm lúc configuration | Sử dụng `getByName`, `create`, gọi `TaskProvider.get()` | `register`, `named`, `configureEach`; không realize task sớm |
| CLI gọi `:test` sai | Root không sở hữu task `test` | `./gradlew projects` và `:app:tasks --all` để tìm path thật |
| Thay đổi quan hệ task trong `taskGraph.whenReady` không ổn định | Chỉnh graph sau khi Gradle đã lập kế hoạch | Khai báo `dependsOn`/ordering/`finalizedBy` trong configuration |
| Chạy `--dry-run` rồi tin cleanup thành công | Dry run chỉ hiển thị graph dự kiến | Thử action thực tế trong sandbox; tránh resource production |
| Build dùng `--continue` vẫn FAIL | `--continue` chỉ cố chạy thêm tác vụ độc lập | Xem các task fail, giải quyết lỗi; không coi `--continue` là bỏ qua lỗi |

## 16. Quy trình kiểm chứng task graph trước khi đưa vào CI

**Bước 1 — xác định cần chạy ai.** Viết rõ mỗi task: input/output, side effect, prerequisite, có được chọn độc lập hay không. Phân biệt yêu cầu dữ liệu bắt buộc với thứ tự mong muốn.

**Bước 2 — chọn quan hệ mạnh/yếu.** Với input bắt buộc, dùng `dependsOn` hoặc inferred dependency. Với thứ tự nhưng không bắt buộc chạy, chọn `mustRunAfter` hoặc `shouldRunAfter` tùy độ nghiêm ngặt. Với cleanup sau chính task, chọn `finalizedBy`.

**Bước 3 — chạy dry-run:**

```bash
./gradlew packageDemo --dry-run
./gradlew publishDemo audit --dry-run
./gradlew runScenario --dry-run
```

Kiểm tra các task có mặt trong graph và thứ tự dự kiến. Đừng nhầm `SKIPPED` do dry-run với `UP-TO-DATE` trong một lần chạy thật.

**Bước 4 — chạy thật trong môi trường an toàn:**

```bash
./gradlew -q packageDemo
./gradlew -q publishDemo
./gradlew -q publishDemo audit
./gradlew -q runScenario
```

Đối chiếu stdout với phần 4, 5, 7. Tập trung vào **tập task được chọn** và quan hệ thứ tự, không đoán số lần Gradle đánh giá build script.

**Bước 5 — thử failure path.** Với demo `runScenarioFails` hoặc `deliberateFailure`, xác nhận task finalizer có chạy trong trường hợp failure và `--continue` không bỏ qua lỗi. Không dùng tài khoản/repository production cho thử nghiệm lỗi.

**Bước 6 — kiểm tra môi trường CI.** Task paths phải chính xác, không phụ thuộc thứ tự gõ tên, không dựa vào task tự tạo tại máy người viết. Với parallel/đa module, rà soát shared resource, task outputs và API lazy configuration.

**Bước 7 — kiểm tra hiệu năng và khả năng cache.** Với task tạo artifact, khai báo `@Input`/`@OutputFile`/`@InputFile`; thử một lần chạy thứ hai để xem `UP-TO-DATE` hoặc build cache khi đủ điều kiện. `dependsOn` không thay thế phần này.

## 17. Bài tập tự kiểm tra

1. Với `A.dependsOn(B)`, gọi A có gọi B không? **Có**; B là prerequisite. Gọi B có gọi A không? **Không**, dependency chỉ một chiều.
2. Với `A.mustRunAfter(B)`, gọi riêng A có gọi B không? **Không**. Gọi cả A và B thì sao? **B phải đi trước A**.
3. Với `A.shouldRunAfter(B)`, thứ tự B → A có luôn tuyệt đối không? **Không**; có thể bị bỏ qua do cycle hoặc parallel scheduling.
4. Với `A.finalizedBy(F)`, gọi A khi A thất bại ở chính task action thì F có chạy không? **Theo quy tắc finalizer của Gradle, có**, dù toàn build vẫn failed.
5. Nếu task B đã `UP-TO-DATE` nhưng A phụ thuộc B, A có bắt buộc phải chạy action của B một lần nữa không? **Không**; B được xét trong graph, action có thể skip hợp lệ.
6. Muốn test `checkAll` kéo cả `quickTest` và `slowTest` vào graph thì dùng gì? **`checkAll.dependsOn(quickTest, slowTest)`**. Còn `slowTest.shouldRunAfter(quickTest)` chỉ ưu tiên thứ tự.
7. Có thể dùng `mustRunAfter` để buộc security scan chạy trong release không? **Không**; dùng dependency thực sự.
8. `finalizedBy` có bảo đảm cleanup khi CI runner bị kill đột ngột không? **Không**; cần thêm hạ tầng cleanup độc lập.
9. Khi nào nên dùng `TaskProvider`? **Ngay khi đăng ký/tham chiếu task** để không ép realize; `dependsOn(provider)` là hợp lệ.
10. Nếu hai task cùng ghi một file nhưng luôn chạy đúng thứ tự, build đã portable/cacheable chưa? **Chưa chắc**; cần mô hình producer/consumer và inputs/outputs rõ ràng.

## 18. Ghi nhớ

- **`dependsOn` = cần B để làm A**: B được chọn và phải hoàn tất trước A.
- **`mustRunAfter` = nếu cùng chọn thì B trước A**: không kéo B vào graph.
- **`shouldRunAfter` = mong B trước A**: không kéo B vào graph, có ngoại lệ do cycle/parallel.
- **`finalizedBy` = chạy F sau A để dọn dẹp/hoàn tất**: finalizer có thể chạy dù A fail hoặc `UP-TO-DATE`, nhưng không thay thế cleanup cấp hệ thống.
- **Chọn đúng quan hệ từ dữ liệu và yêu cầu nghiệp vụ**, không dùng thứ tự mềm để che dependency thật.
- Dùng **`tasks.register` và `TaskProvider`** để liên kết task lazy; dùng **Provider inputs/outputs** khi task tạo và tiêu thụ dữ liệu.
- Kiểm chứng bằng `--dry-run`, chạy thực tế, thử failure path, `--continue` và trường hợp `UP-TO-DATE` trước khi chuyển workflow sang CI.

## Tài liệu chính thức

- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): dependency, `mustRunAfter`, `shouldRunAfter`, finalizer, task skip.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): strong/soft task relationships và cách dùng `TaskProvider`.
- [Gradle — Task API (Javadoc)](https://docs.gradle.org/current/javadoc/org/gradle/api/Task.html): chữ ký và ngữ nghĩa của bốn phương thức.
- [Gradle — Task Basics](https://docs.gradle.org/current/userguide/task_basics.html): task graph và thứ tự thực thi.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): inputs/outputs, up-to-date và dependency suy luận.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): ranh giới configuration/execution và khả năng tái sử dụng graph.
