# Phát hiện chu trình và chẩn đoán task chạy ngoài dự kiến trong Gradle

Một lệnh như `./gradlew :app:build` có thể kéo theo hàng chục task ở nhiều project. Phần lớn là hành vi đúng: Gradle tự lập **đồ thị task** từ các quan hệ phụ thuộc để bảo đảm đầu vào sẵn sàng trước khi task tiêu thụ chạy. Nhưng khi cấu hình sai, build có thể thất bại vì **chu trình phụ thuộc** (*circular task dependency*) hoặc lên lịch các task mà người viết build không hề dự định.

Muốn xử lý chính xác, phải trả lời **hai câu hỏi khác nhau**:

1. **Tại sao task này có mặt trong đồ thị?** Do người dùng yêu cầu trực tiếp, `dependsOn`, liên kết input/output, `finalizedBy`, lifecycle task hay một plugin nào đó?
2. **Task có thực thi hành động thật không?** Một task **được chọn** có thể vẫn `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` hoặc `SKIPPED`; nó xuất hiện trong log nhưng không chạy action.

Bài học áp dụng cho Gradle Groovy/Kotlin DSL, dùng ví dụ **Kotlin DSL (`build.gradle.kts`)** và chỉ rõ những công cụ chẩn đoán hoạt động trên các phiên bản Gradle khác nhau.

## 1. Đồ thị task: đọc đúng chiều phụ thuộc

Giả sử task `packageApp` **phụ thuộc** `compileCode`, còn `compileCode` **phụ thuộc** `generateSource`:

```text
generateSource ──> compileCode ──> packageApp
     hoàn tất            hoàn tất         hoàn tất
       trước               trước
```

Trong Gradle Kotlin DSL:

```kotlin
tasks.register("generateSource")
tasks.register("compileCode") {
    dependsOn("generateSource")
}
tasks.register("packageApp") {
    dependsOn("compileCode")
}
```

Khi yêu cầu `packageApp`, Gradle sẽ chọn cả `compileCode` và `generateSource` nếu các quan hệ còn hiệu lực. Đó là **task dependency graph** — một đồ thị có hướng mà Gradle phải tổ chức theo thứ tự hợp lệ.

- Cạnh diễn đạt `A.dependsOn(B)` có nghĩa **B phải được xử lý trước A**.
- Các task không có quan hệ thứ tự bắt buộc có thể chạy theo thứ tự khác nhau; nếu cấu hình cho phép, Gradle có thể xử lý chúng song song.
- Một task có thể được chọn nhiều lần qua các đường phụ thuộc khác nhau nhưng thông thường chỉ có **một task node** trong đồ thị của một lần build, không tự chạy action hai lần chỉ vì hai task cùng phụ thuộc nó.
- Các task được **đăng ký** trong build script không mặc định được **chọn** để thực thi. Chỉ task CLI chọn và các quan hệ liên quan mới quyết định những node phải có.

**Đồ thị task không phải đồ thị dependency thư viện.** Ví dụ `implementation("org.example:library:1.0")` xác định dependency cho classpath; task graph có thể chịu ảnh hưởng bởi cách plugin thực hiện dependency resolution hoặc project artifact wiring, nhưng hai đồ thị có mục đích và công cụ chẩn đoán riêng.

### Chu trình là gì?

Chu trình hình thành khi một task phải chờ chính nó qua một chuỗi cạnh:

```text
A dependsOn B
B dependsOn C
C dependsOn A

Yêu cầu A:
A cần B → B cần C → C lại cần A → không có điểm bắt đầu hợp lệ
```

Trong kiểu sơ đồ “B chạy trước A”, nó tương ứng vòng khép kín:

```text
A → C → B → A
```

Không thể sắp thứ tự ba node để tất cả các điều kiện “phải chạy trước” đều đúng. Gradle xây đồ thị trước khi thực thi actions và **báo lỗi**; nó không âm thầm chọn một node để phá vòng.

## 2. Những quan hệ dễ gây nhầm lẫn

| Quan hệ/API | Tự thêm task khác vào đồ thị khi task nguồn được chọn? | Ý nghĩa chính | Ảnh hưởng đến điều tra |
| --- | --- | --- | --- |
| `dependsOn(B)` trên task A | **Có**, thêm B | B là điều kiện tiên quyết của A | Tìm cạnh A → B, kể cả dependencies gián tiếp |
| Nối input của A từ output của B qua `Provider` | **Có thể có**, Gradle suy ra dependency B | A tiêu thụ artifact do B tạo | Tìm provenance của input property/provider |
| `finalizedBy(B)` trên A | **Có**, thêm B khi A được lên lịch | B chạy sau A để dọn dẹp/kết thúc | Task B có thể xuất hiện dù không có `dependsOn(B)` |
| `mustRunAfter(B)` trên A | **Không** tự đưa B vào | Nếu cả A và B được chọn, A phải sau B | Điều kiện thứ tự nghiêm ngặt; có thể tham gia mâu thuẫn thứ tự |
| `shouldRunAfter(B)` trên A | **Không** tự đưa B vào | Ưu tiên A sau B nếu có thể | Gradle có thể bỏ qua khi gây vòng thứ tự hoặc để tránh trì hoãn với parallel execution |
| Task lifecycle `build`, `check`, `assemble` | Task được chọn sẽ kéo theo dependencies đã khai báo | Kết hợp nhiều công đoạn build | Task nhỏ lẻ xuất hiện vì thành phần lifecycle |
| Một lệnh CLI chọn nhiều task | **Có**, vì người dùng trực tiếp yêu cầu | Một lời gọi có thể gồm nhiều task | Kiểm tra đầy đủ CLI/IDE invocation, không chỉ tên đầu tiên |

**Điểm quan trọng:** `mustRunAfter` và `shouldRunAfter` là **ordering rules**, không phải dependency. Nếu chỉ chạy `A`, việc A có `mustRunAfter(B)` không tự làm B chạy. Ngược lại, `finalizedBy` là quan hệ mạnh: finalizer có thể được đưa vào đồ thị khi task nguồn được lên lịch, ngay cả khi task nguồn cuối cùng fail hoặc `UP-TO-DATE`.

### Ví dụ minh họa phân biệt ba loại

Đây là một file `build.gradle.kts` tối thiểu:

```kotlin
val prepare = tasks.register("prepare") {
    doLast { println("prepare") }
}

val compile = tasks.register("compileSample") {
    dependsOn(prepare)
    doLast { println("compileSample") }
}

val cleanUp = tasks.register("cleanUp") {
    doLast { println("cleanUp") }
}

tasks.register("packageSample") {
    dependsOn(compile)
    finalizedBy(cleanUp)
    doLast { println("packageSample") }
}

tasks.register("audit") {
    mustRunAfter(compile)
    doLast { println("audit") }
}
```

Chạy từ root một Gradle build hợp lệ:

```bash
./gradlew packageSample --no-configuration-cache --console=plain -q
```

Khi các task actions được thực thi lần đầu, stdout là:

```text
prepare
compileSample
packageSample
cleanUp
```

`audit` **không** có trong graph chỉ vì `mustRunAfter(compile)`, còn `cleanUp` được thêm bởi `finalizedBy`. Nếu chạy riêng `./gradlew audit -q`, chỉ `audit` được yêu cầu và task `compileSample` không bắt buộc chạy.

Dòng `doLast` cho `prepare` và `compileSample` chỉ chạy ở giai đoạn **Execution**. Nếu một task được viết với outputs/inputs và sau này bị đánh dấu `UP-TO-DATE`, action có thể không in nữa; điều đó không đổi quan hệ phụ thuộc.

## 3. Tái hiện một chu trình thật sự

Tạo `settings.gradle.kts` trong project Gradle thử nghiệm:

```kotlin
rootProject.name = "task-cycle-demo"
```

Tạo `build.gradle.kts`:

```kotlin
tasks.register("alpha") {
    dependsOn("beta")
    doLast { println("alpha executed") }
}

tasks.register("beta") {
    dependsOn("gamma")
    doLast { println("beta executed") }
}

tasks.register("gamma") {
    dependsOn("alpha")
    doLast { println("gamma executed") }
}
```

Chạy bằng Gradle Wrapper của project:

```bash
./gradlew alpha --dry-run --console=plain
```

Gradle phải dựng graph để biết tasks nào sẽ được chọn. Nó thấy:

```text
:alpha → :beta → :gamma → :alpha
```

Vì vậy **build thất bại trước khi chạy bất kỳ `doLast` nào**. Thông điệp lỗi thường có nội dung tương tự:

```text
Circular dependency between the following tasks:
:alpha
\--- :beta
     \--- :gamma
          \--- :alpha (*)
```

Đây là **minh họa cách đọc lỗi**, không phải cam kết từng ký tự dấu nối/indent giống mọi phiên bản Gradle. Dấu `(*)` có thể được dùng để chỉ node lặp lại. Kết quả chắc chắn của ví dụ là **không có dòng** `alpha executed`, `beta executed`, `gamma executed` trong stdout của task actions, vì graph không hợp lệ.

**Tại sao `--dry-run` vẫn lỗi?** `--dry-run` bỏ qua task actions, nhưng Gradle **vẫn phải cấu hình, xác định và kiểm tra đồ thị**. Nó không thể “chạy thử” một đồ thị bất khả thi.

### Sửa đúng nguyên nhân

Quyết định task nào thực sự phụ thuộc dữ liệu từ task nào. Trong ví dụ giả định `alpha` cần `beta`, `beta` cần `gamma`, còn `gamma` không cần `alpha`; bỏ cạnh ngược `gamma.dependsOn("alpha")`.

File `build.gradle.kts` sau sửa:

```kotlin
tasks.register("alpha") {
    dependsOn("beta")
    doLast { println("alpha executed") }
}

tasks.register("beta") {
    dependsOn("gamma")
    doLast { println("beta executed") }
}

tasks.register("gamma") {
    doLast { println("gamma executed") }
}
```

Chạy:

```bash
./gradlew alpha --no-configuration-cache --console=plain -q
```

Stdout chính xác của các actions trong ví dụ này:

```text
gamma executed
beta executed
alpha executed
```

**Nguyên tắc sửa:** chỉ xóa hoặc đổi một cạnh khi quan hệ giữa các đầu vào/đầu ra thực sự cho phép. Nếu `gamma` cần output từ `alpha`, không được xóa dependency chỉ để build chạy. Khi đó phải **thiết kế lại pipeline**: tách bước chuẩn bị dữ liệu chung, tách producer/consumer, hoặc loại quan hệ vòng trong sản phẩm được tạo ra.

## 4. Chu trình do wiring gián tiếp và plugin

Chu trình trong build thật thường không rõ như ba dòng `dependsOn` cạnh nhau. Nó có thể hình thành khi các thành phần khác nhau cùng sửa task graph:

```text
Project :api
   :api:generateSpec
        dependsOn :core:compileJava

Project :core
   :core:compileJava
        cần mã sinh từ :api:generateSpec

⇒ :api:generateSpec → :core:compileJava → :api:generateSpec
```

Đây là sơ đồ **giả định**, không khẳng định Gradle Java plugin mặc định tạo quan hệ như vậy. Nó minh họa tình huống hai module tạo dependency ngược chiều thông qua nguồn sinh và classpath.

Một số nguồn cạnh cần truy tìm:

- `dependsOn` trực tiếp trong `build.gradle(.kts)`, root script hoặc convention plugin.
- Task được plugin Java, Kotlin, Spring, code generation, packaging, publishing hay quality checks đăng ký và nối tự động.
- Input của task trỏ tới **provider output của task khác**, ví dụ `consumer.inputFile.set(producer.flatMap { it.outputFile })`.
- `ConfigurableFileCollection.from(taskProvider)`, `builtBy` hoặc `Configuration` chứa artifacts do task khác sinh.
- `finalizedBy` cùng những dependencies/order constraints liên quan.
- Cấu hình liên project, task `:lib:jar`, `:app:compileJava`, hoặc task artifact transform.

**Chú ý:** Không phải mọi quan hệ nêu trên đều tự gây chu trình, nhưng chúng là các vị trí cần kiểm tra khi Gradle cho biết một cạnh xuất hiện ngoài dự kiến.

### Bẫy: đọc output bằng đường dẫn chuỗi làm mất dependency

Đoạn sau là một lỗi thiết kế thường gặp:

```kotlin
// Ví dụ không hoàn chỉnh, chỉ minh họa cách sai:
val guessedPath = layout.buildDirectory.file("generated/spec.json")
tasks.register("readSpec") {
    doLast {
        println(guessedPath.get().asFile.readText())
    }
}
```

Task `readSpec` đã biết **đường dẫn**, nhưng chưa hề được nối đến task **thực sự sản xuất** file đó. Nó có thể chạy khi file chưa tồn tại hoặc dùng dữ liệu cũ. Không phải vì đường dẫn giống output của task khác mà Gradle tự luôn suy ra quan hệ.

Nếu producer khai báo `@OutputFile abstract val specFile: RegularFileProperty`, consumer khai báo `@InputFile abstract val inputFile: RegularFileProperty`, nên nối:

```kotlin
// Trong closure cấu hình consumer task type có inputFile:
inputFile.set(producer.flatMap { it.specFile })
```

Đây là **mảnh ghép API**, không phải file `build.gradle.kts` độc lập vì các task types chưa được khai báo. Nối provider output giúp Gradle suy ra task dependency. Việc đoán path rồi bổ sung `dependsOn` thủ công không thể hiện rõ **file nào** đang tạo ra quan hệ phụ thuộc.

## 5. Tình huống có vẻ chu trình nhưng là ordering rule

`mustRunAfter` và `shouldRunAfter` không kéo task khác vào graph. Khi hai task **đã được chọn**, chúng điều chỉnh thứ tự:

```kotlin
val lint = tasks.register("lintSample") {
    doLast { println("lint") }
}

tasks.register("packageSample") {
    mustRunAfter(lint)
    doLast { println("package") }
}
```

Chạy `./gradlew packageSample -q` chỉ thực thi `packageSample`; `lintSample` không tự chạy. Chạy cả hai `./gradlew packageSample lintSample -q` khiến Gradle tôn trọng ràng buộc `lintSample` trước `packageSample`.

**`shouldRunAfter` mềm hơn `mustRunAfter`.** Gradle có thể bỏ qua `shouldRunAfter` nếu nó tạo vòng thứ tự hoặc nếu chạy song song mà các dependency khác đã thỏa và task đang chờ ưu tiên thứ tự mềm. Vì vậy:

- Dùng `dependsOn` hoặc provider wiring khi **A thật sự cần B được tạo/chạy**.
- Dùng `mustRunAfter` khi chỉ cần thứ tự nghiêm ngặt **nếu cả hai task được chọn**.
- Dùng `shouldRunAfter` khi đó chỉ là một ưu tiên, không phải yêu cầu bắt buộc.

Không “sửa” một dependency cần thiết bằng cách đổi `dependsOn` thành `shouldRunAfter` chỉ để tránh vòng: thao tác đó có thể khiến task thiếu input hoặc chạy không đúng dữ liệu.

### Một trường hợp của `shouldRunAfter` bị bỏ qua

```kotlin
tasks.register("a") { dependsOn("b") }
tasks.register("b") { dependsOn("c") }
tasks.register("c") { shouldRunAfter("a") }
```

Để chạy `a`, thứ tự dependency bắt buộc là `c` rồi `b` rồi `a`. Ràng buộc `c.shouldRunAfter(a)` mâu thuẫn với thứ tự đó nên Gradle **có thể bỏ qua** yêu cầu ưu tiên mềm này, thay vì xem nó như một `dependsOn` cứng và báo chu trình. Đây là lý do phải đọc loại cạnh trong DSL trước khi kết luận.

## 6. Task “ngoài dự kiến”: trước tiên xác định có thật sự chạy không

Khi console xuất hiện:

```text
> Task :app:compileJava UP-TO-DATE
> Task :app:processResources NO-SOURCE
> Task :app:classes
> Task :app:jar
> Task :app:test FROM-CACHE
> Task :app:check
```

Có nhiều trạng thái khác nhau:

| Kết quả task | Ý nghĩa thường gặp | Action có nhất thiết chạy? |
| --- | --- | --- |
| Không có nhãn hoặc `EXECUTED` | Gradle đã thực hiện action (nếu task có action) | Có, khi task thực sự có action |
| `UP-TO-DATE` | Inputs/outputs không đổi theo theo dõi của Gradle | Thường **không** chạy action |
| `FROM-CACHE` | Output được phục hồi từ build cache | **Không** chạy action bình thường |
| `NO-SOURCE` | Task được thiết kế xử lý source nhưng không có nguồn phù hợp | Thường không thực hiện công việc |
| `SKIPPED` | Task bị bỏ qua do `onlyIf`, disabled, `--dry-run` hoặc quy tắc khác | **Không** thực hiện action tương ứng |
| `FAILED` | Task hoặc build action lỗi | Phải xem stacktrace/log để biết nguyên nhân |

Một lifecycle task như `build`, `assemble`, `check` nhiều khi **không có action tự thân**; nó có mặt để gom dependencies. Thấy `:app:check` trong console không đồng nghĩa Gradle chạy một bước kiểm tra độc lập ngoài các task được nối vào nó.

**Đừng dùng số dòng `> Task` làm thước đo “task được chạy thực sự”.** Hãy phân biệt *selected/scheduled* với *action executed*.

## 7. Chẩn đoán bước đầu bằng CLI

Trước hết xác định **phiên bản Gradle Wrapper**, vị trí dự án và câu lệnh thực sự được IDE/CI/terminal yêu cầu. Các lệnh bên dưới dùng Linux/macOS; trên Windows PowerShell thay `./gradlew` bằng `.\gradlew.bat`.

```bash
./gradlew --version
./gradlew projects
./gradlew :app:tasks --all
./gradlew help --task :app:build
./gradlew :app:build --dry-run --console=plain
./gradlew :app:build --info --console=plain
```

Cách hiểu:

1. `--version` cho biết bản Gradle thực chạy, để quyết định flag nào hỗ trợ.
2. `projects` hiển thị cây project, giúp xác định `:app` có tồn tại và path có đúng không.
3. `:app:tasks --all` liệt kê task được cung cấp/đăng ký cho project, **không phải** toàn bộ task graph của `:app:build`.
4. `help --task :app:build` giúp kiểm tra task, group và mô tả khi plugin có cung cấp.
5. `--dry-run` cho biết **những task được lên lịch**, theo thứ tự Gradle định dùng, và bỏ qua task actions. Nó vẫn cấu hình/giải graph nên có thể phát hiện chu trình trước khi làm việc tốn kém.
6. `--info` cho biết nhiều chi tiết hơn về configuration, task selection, nguyên nhân up-to-date hoặc việc task bị bỏ qua. Chỉ bật `--debug` khi thật cần vì log rất lớn và có thể chứa thông tin nhạy cảm.

Từ **Gradle 9.1**, CLI còn có `--task-graph`, in **đồ thị task dependencies** trong khi vô hiệu hóa task actions:

```bash
# Chỉ áp dụng khi Wrapper sử dụng Gradle 9.1 trở lên
./gradlew :app:build --task-graph --console=plain
```

Với Gradle cũ (ví dụ 8.x), `--task-graph` **chưa có**; hãy dùng `--dry-run`, log `--info` và kiểm tra cấu hình task. Đừng xem `./gradlew dependencies` là lệnh in task graph: task `dependencies` chủ yếu hiển thị **dependency configurations/thư viện** của project.

### `--dry-run` không chứng minh nguyên nhân của từng cạnh

Ví dụ output (tập task thực tế tùy plugins):

```text
:app:compileJava SKIPPED
:app:classes SKIPPED
:app:jar SKIPPED
:app:assemble SKIPPED
:app:check SKIPPED
:app:build SKIPPED
```

Nó cho biết `compileJava` có mặt trong lịch chạy, nhưng chưa trả lời chính xác **cạnh nào** dẫn đến `compileJava`. Tại Gradle hỗ trợ `--task-graph`, xem graph; nếu không, tìm các cấu hình `dependsOn`, task outputs và plugin wiring. `SKIPPED` ở `--dry-run` là vì action bị tắt có chủ đích, không phải bằng chứng rằng build thực sẽ bỏ qua tác vụ đó.

## 8. Task selectors trong multi-project: một nguyên nhân rất phổ biến

Giả sử build có:

```text
root
├── :api
├── :web
└── :worker
```

Và ba subproject đều có task `test`. Từ root, lệnh:

```bash
./gradlew test
```

có thể chọn **mọi task tên `test` trong cây project ở dưới vị trí chạy**, vì Gradle hỗ trợ **task selector theo tên** cho multi-project build. Nếu chỉ muốn kiểm thử `:api`, hãy chỉ định đầy đủ:

```bash
./gradlew :api:test
```

Phân biệt:

| CLI | Ý định và phạm vi |
| --- | --- |
| `./gradlew test` từ root | Chọn những task `test` phù hợp theo quy tắc task selection của cây project |
| `./gradlew :api:test` | Chỉ định **task mục tiêu** `:api:test` (kèm dependencies của nó) |
| `./gradlew :api:build` | Chọn task build của `:api` và **các prerequisites cần thiết**, có thể liên quan project khác |
| `./gradlew :test` | Path tuyệt đối của task `test` ở **root Project**; không giống bare selector `test` |

Một số task giúp chẩn đoán (`help`, `dependencies`) có cách chọn phạm vi riêng. Vì vậy cần đối chiếu đúng CLI, Project path và bản Gradle thực tế trước khi kết luận lỗi. Dùng tên đầy đủ `:module:task` thường loại bỏ sự mơ hồ khi tái hiện lỗi.

**Cần phân biệt:** chỉ định `:api:build` không bảo đảm mọi task được lên lịch đều thuộc project `:api`. Nếu `:api:compileJava` cần artifact do `:core:jar` tạo, Gradle vẫn có thể đưa task thuộc `:core` vào graph nhờ dependency thực.

## 9. Plugin và lifecycle task có thể thêm công việc mà bạn không khai báo trực tiếp

Ví dụ project dùng Java plugin:

```kotlin
plugins {
    java
}
```

Plugin tạo nhiều task và các quan hệ chuẩn như:

- `classes` liên quan đến các bước compile Java và xử lý resources.
- `jar` đóng gói đầu ra main source set.
- `test` chạy test source set mặc định và cần test classes.
- `assemble` gom những artifact được cấu hình.
- `check` gom các nhiệm vụ verification thích hợp.
- `build` gom `assemble` và `check`.

Các plugin bổ sung có thể thêm task lint, coverage, integration test, generate resources, publish, code quality... qua `dependsOn` hoặc thông qua task properties. Vì vậy một task có thể xuất hiện **đúng theo hợp đồng của plugin** dù không có từ khóa `dependsOn` ngay trong `app/build.gradle.kts`.

Một ví dụ bổ sung công việc vào lifecycle task:

```kotlin
plugins {
    java
}

tasks.register("generateDocs") {
    doLast {
        println("generateDocs")
    }
}

tasks.named("check") {
    dependsOn("generateDocs")
}
```

Khi chạy `./gradlew check`, task `generateDocs` được thêm vì dòng `dependsOn` mở rộng `check`. Nếu đồng đội chỉ nhìn lệnh `check`, họ có thể cho rằng `generateDocs` “tự chạy”; thực tế đó là dependency do build script cấu hình.

**Không mặc định xóa plugin vì thấy task lạ.** Xác định plugin hoặc convention nào đã thêm task, lý do nó cần thiết, task có tạo artifact hay kiểm tra policy gì, sau đó mới sửa wiring phù hợp.

## 10. Phát hiện task chạy ngoài dự kiến: quy trình 7 bước

Giả sử yêu cầu `:web:build` nhưng log chứa `:worker:publish`. Cách điều tra có hệ thống:

1. **Ghi chính xác invocation**: Wrapper version, CLI đầy đủ, thư mục làm việc, profile, `-P`, biến môi trường, Gradle flags, IDE/CI invocation.
2. **Chọn path cụ thể** `:web:build`; chạy `--dry-run --console=plain` để tái hiện graph mà không chạy actions.
3. **Xem graph** bằng `--task-graph` nếu Gradle 9.1+, hoặc đọc `--info` và tìm quan hệ task trong code build.
4. **Phân loại task lạ**: được yêu cầu từ CLI; dependency `dependsOn`; input/output provider; finalizer; plugin/lifecycle; multi-project task selector.
5. **Lần theo chuỗi ngược từ task lạ đến task mục tiêu**: “Ai kéo task B vào? Task nào đã kéo A vào?”. Một đường có thể dài hơn một cấp và qua project khác.
6. **Kiểm tra trạng thái thực thi**: `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED` hay action thật sự chạy. Nếu `finalizedBy`, xem task nguồn có được lên lịch và finalizer có được kích hoạt đúng hợp đồng hay không.
7. **Sửa đúng cạnh/wiring gây ra** rồi lặp lại `--dry-run` và chạy task liên quan trong môi trường thích hợp, kiểm tra output/test. Không xóa một dependency chỉ vì nó tốn thời gian nếu task khác thật sự cần đầu ra của nó.

Nếu source code có thể tìm bằng terminal, các từ khóa cần xem trong **các build scripts và convention plugins liên quan**:

```text
dependsOn
finalizedBy
mustRunAfter
shouldRunAfter
builtBy
tasks.named(...)
tasks.register(...)
tasks.withType(...)
@InputFile / @OutputFile / @InputFiles / @OutputDirectory
```

Đừng chỉ tìm `dependsOn`. Task wiring có thể nằm ở một convention plugin, `buildSrc`, included build `build-logic`, cấu hình root project hoặc một plugin nhị phân. Nếu `--task-graph` hiển thị quan hệ nhưng nguồn không rõ, lần theo output property của producer và input của consumer.

## 11. Cách tìm cạnh gây chu trình và sửa theo bản chất

Một thông báo lỗi như:

```text
Circular dependency between the following tasks:
:api:generateClient
:core:compileJava
:api:generateClient (*)
```

cho thấy vòng cần điều tra, **không tự kết luận task nào sai**. Có thể có nhiều cách làm hỏng thiết kế; chọn hướng sửa dựa trên luồng dữ liệu thực.

### Trường hợp A: Cạnh thừa

Task `:api:generateClient` không cần đầu ra `:core:compileJava`, nhưng build script vô tình thêm `dependsOn` từ việc copy cấu hình. Gỡ **cạnh thừa** nếu không làm sai input contract. Chạy lại `--dry-run` để xác nhận graph hợp lệ.

### Trường hợp B: Hai task cần dữ liệu lẫn nhau

Nếu A cần output của B và B cũng cần output của A, không tồn tại thứ tự hợp lệ để tạo cả hai từ đầu. Cần **tách một dữ liệu đầu vào chung**, đổi kiến trúc producer/consumer hoặc chia thành các bước có hướng rõ:

```text
sharedSchema
    ├──> generateClient
    └──> compileCore
              └──> assemble
```

Sơ đồ trên là một phương án thiết kế ví dụ. Điều cần giữ là **mỗi bước có đầu vào đã tồn tại trước khi tạo output**. Không được đổi thành `mustRunAfter` để né lỗi nếu thật ra hai task đang cần output của nhau.

### Trường hợp C: Finalizer gây quan hệ ngược

Task `runIntegration` `finalizedBy(stopService)` nhưng một plugin lại làm `stopService.dependsOn(runIntegration)` hoặc thêm các thứ tự khác không tương thích, tạo vòng logic. Kiểm tra lại mục đích: task cleanup thường phải chạy **sau** task sử dụng service, trong khi task start/setup thường phải chạy **trước**. Biểu diễn bằng quan hệ có hướng phù hợp; tránh để cleanup vừa là prerequisite của task mà nó cleanup.

### Trường hợp D: Implicit dependency được nối ngược

Task A khai báo output, task B tiêu thụ output của A; plugin khác lại cấu hình A tiêu thụ output của B. Cả hai providers đều hợp lệ riêng lẻ, nhưng tổng graph vô lý. Chọn một chiều producer → consumer; nếu cần kết quả phản hồi, thiết kế thành các giai đoạn với artifact tách biệt.

### Trường hợp E: Ordering constraint không tương thích

Nếu là `shouldRunAfter`, Gradle có thể bỏ qua để phá vòng ưu tiên. Nếu là `mustRunAfter` hoặc các điều kiện thứ tự cứng, cần kiểm tra lý do đặt thứ tự và sửa cho thống nhất với dependencies. Một bước đã **phụ thuộc** task B thì đương nhiên phải chờ B; không nên đồng thời yêu cầu B chạy sau nó.

## 12. Các cờ CLI hữu ích, và giới hạn của chúng

| Lệnh/cờ | Dùng để | Giới hạn/cảnh báo |
| --- | --- | --- |
| `--dry-run` (`-m`) | Xem những tasks được chọn, bỏ qua actions | Vẫn build graph; không chỉ ra nguồn mọi cạnh |
| `--task-graph` | In graph và bỏ qua actions | **Chỉ Gradle 9.1+**; không dùng cho Wrapper 8.x |
| `--info` | Xem log chẩn đoán task execution, skip, configuration | Output dài; không phải tree của task dependencies |
| `--stacktrace` | Xem chi tiết nơi lỗi được ném | Hữu ích khi thông báo cycle/validation quá ít context |
| `tasks --all` | Liệt kê task có sẵn trong project | Không cho biết task nào sẽ chạy theo invocation |
| `projects` | Xem cấu trúc multi-project | Không hiển thị task edges |
| `help --task <path>` | Xem task metadata | Thông tin phụ thuộc vào task và phiên bản |
| `--continue` | Tiếp tục các task độc lập có thể làm sau khi một task fail | **Không giải quyết chu trình**; không ép task bị lỗi chạy lại |
| `--rerun-tasks` | Buộc Gradle không dùng kết quả up-to-date thông thường | **Không đổi graph**; có thể tốn thời gian |
| `--exclude-task <name>` (`-x`) | Tạm loại một task để khoanh vùng, khi phù hợp | Có thể tạo build không đầy đủ; không nên dùng làm cách sửa lâu dài |
| `--scan` | Báo cáo phân tích build khi hạ tầng cho phép | Có thể cần đồng ý chia sẻ/upload thông tin build; xem chính sách nhóm trước khi dùng |

**Phân biệt `--dry-run` và `--task-graph`:** đều không chạy task actions, nhưng option thứ hai (Gradle 9.1+) hướng tới hiển thị cấu trúc dependency graph. Đối với project dùng Gradle 8.x, đừng viết tài liệu dựa trên một flag chưa được hỗ trợ.

Một lệnh tự kiểm tra tốt khi không chắc build có side effect (deploy/publish) là chạy bản **dry-run** trước rồi kiểm tra graph. Tuy vậy, Gradle **vẫn đánh giá configuration** và các plugin có thể có side effect ở configuration time nếu được viết sai; dry-run không phải sandbox tuyệt đối.

## 13. Vì sao thay đổi không đúng có thể che lỗi?

Một số “cách sửa nhanh” tưởng hiệu quả nhưng nguy hiểm:

### 13.1. Dùng `-x` bỏ task gây vòng

Ví dụ `./gradlew build -x generateSource` có thể khiến graph nhìn gọn hơn. Nhưng nếu `compileJava` cần source do `generateSource` tạo, build sẽ dùng file cũ, thiếu source hoặc tạo kết quả không tái lập. Chỉ dùng exclude khi hiểu rõ task đang bỏ qua và đang phục vụ mục đích **chẩn đoán**.

### 13.2. Đổi `dependsOn` thành `mustRunAfter`

`mustRunAfter` **không đưa prerequisite vào graph**. Nếu run task A một mình, B có thể không chạy. Cách đổi này chỉ đúng khi task A **không cần** output của B và thứ tự là điều kiện duy nhất cần biểu diễn.

### 13.3. Di chuyển công việc từ task action sang configuration

Viết code tạo file ngay ở top-level `build.gradle.kts` để “chuẩn bị cho task” có thể làm file tồn tại trước khi graph được tính, nhưng làm build thiếu input/output tracking, khó tương thích Configuration Cache và chạy cả khi chỉ gọi `help`. Cách đúng là khai báo producer task với output property và nối consumer qua provider.

### 13.4. Gọi task bằng code Kotlin bên trong `doLast`

Các task trong Gradle là node của đồ thị được sắp xếp trước Execution. Không tự gọi `Task.execute()`, không gọi task action của task khác trực tiếp trong `doLast`, và không đợi đến Execution mới thêm `dependsOn`. Nếu có prerequisite, khai báo khi Configuration.

### 13.5. Giả định cứ thấy task là nó thực thi lại

Một task được chọn nhưng `UP-TO-DATE` có thể không chạy actions. Nếu thấy output không như mong đợi, hãy kiểm tra khai báo inputs/outputs và logic task, không vội thêm `--rerun-tasks` như một fix cố định.

## 14. Configuration Cache, parallel execution và CI

**Configuration Cache** có thể tái sử dụng task graph từ lần trước khi cấu hình phù hợp. Vì vậy các `println` ở top-level build script hoặc một số lifecycle callbacks không chắc được gọi lại trên cache hit. Khi tạo ví dụ chẩn đoán cấu hình từ đầu, dùng `--no-configuration-cache` (nếu Wrapper hỗ trợ) để quan sát đường đi chuẩn:

```bash
./gradlew :app:build --dry-run --no-configuration-cache --console=plain
```

Với build thật, cần phân biệt sự khác nhau giữa **sự kiện cấu hình không chạy lại** và **task action không chạy** do up-to-date/build cache.

**Parallel execution** có thể thay thứ tự quan sát các task độc lập. Chỉ coi thứ tự là hợp đồng khi có dependency/ordering rule tương ứng. Nếu thực sự cần lặp lại việc chẩn đoán trong một thứ tự dễ đọc, có thể tạm dùng `--no-parallel` khi phù hợp, nhưng không xem thứ tự tạo ra bởi `--no-parallel` là lý do để bỏ dependencies cần thiết.

**CI và IDE** có thể truyền nhiều task hoặc init script/plugin khác terminal. Khi local chỉ chạy `:app:build` nhưng CI chạy `clean :app:build :app:publish`, một số task “ngoài dự kiến” có thể do chính lệnh CI chọn. Luôn so sánh **invocation thực tế** trước khi sửa build scripts.

## 15. Checklist điều tra trong một pull request

Trước khi thay đổi task wiring, hãy xác nhận:

- [ ] Đã ghi lại đúng Wrapper version và CLI/IDE/CI invocation.
- [ ] Đã phân biệt task **được chọn** với action **được thực thi** qua trạng thái console.
- [ ] Đã dùng `--dry-run` trước khi chạy task có thể publish/deploy.
- [ ] Đã dùng `--task-graph` chỉ khi Gradle 9.1+ hỗ trợ.
- [ ] Đã kiểm tra task selector ở multi-project và thử path chính xác `:module:task`.
- [ ] Đã lần theo `dependsOn`, `finalizedBy`, ordering rules và input/output provider wiring.
- [ ] Đã xem plugin/convention task wiring, không chỉ một file build script.
- [ ] Đã xác định cạnh gây vòng bằng **nhu cầu dữ liệu thực tế**, không chỉ dựa trên tên task.
- [ ] Đã sửa nguồn quan hệ thừa hoặc tái cấu trúc producer/consumer khi có phụ thuộc hai chiều.
- [ ] Đã chạy lại graph và các task/test phù hợp, kiểm tra artifact đầu ra đúng.
- [ ] Không dùng `-x`, `--continue` hoặc `--rerun-tasks` làm biện pháp che lỗi lâu dài.

## 16. Tự kiểm tra kiến thức

**Câu 1.** A `dependsOn(B)`, B `dependsOn(C)`, C `dependsOn(A)`. Chạy `A --dry-run` có chạy được không?

**Đáp:** Không. Gradle vẫn phải dựng và xác minh task graph khi dry-run; vòng A → B → C → A khiến build thất bại trước khi actions chạy.

**Câu 2.** A `mustRunAfter(B)`, chỉ yêu cầu `A`. B có tự chạy không?

**Đáp:** Không. `mustRunAfter` chỉ áp dụng thứ tự nếu cả hai task đã được chọn. Muốn B là prerequisite thật, cần dependency hoặc output/input wiring phù hợp.

**Câu 3.** A `finalizedBy(cleanUp)`. Chỉ yêu cầu A và A bị fail. Vì sao `cleanUp` vẫn xuất hiện?

**Đáp:** `finalizedBy` thêm finalizer vào graph khi A được lên lịch, cho phép cleanup chạy sau A ngay cả khi A thất bại, theo cơ chế finalizer của Gradle.

**Câu 4.** Task `compileJava` xuất hiện trong log với `UP-TO-DATE`. Có nghĩa compiler đã biên dịch lại toàn bộ Java không?

**Đáp:** Không. Nó nằm trong graph nhưng Gradle đánh giá inputs/outputs còn phù hợp nên thường bỏ qua task action.

**Câu 5.** Chạy `./gradlew test` ở root có ba subproject và thấy ba task test. Điều gì cần kiểm tra đầu tiên?

**Đáp:** Quy tắc task selector theo tên trong multi-project. Nếu chỉ muốn kiểm thử một subproject, dùng `./gradlew :subproject:test` (kèm các dependencies cần thiết).

**Câu 6.** Task B đọc file do A tạo. Đâu là cách nối tốt hơn: `dependsOn(A)` với path tự ghép hay input B nhận output provider của A?

**Đáp:** Khi có typed properties, nên nối **input property của B** tới **output provider của A** để Gradle hiểu cả đường đi dữ liệu và task dependency, giảm hard-coded paths.

**Câu 7.** `shouldRunAfter` gây một vòng ưu tiên thứ tự. Gradle có luôn báo circular dependency như `dependsOn` không?

**Đáp:** Không. Đây là ordering rule mềm; Gradle có thể bỏ qua khi nó gây ordering cycle. Một vòng của hard dependencies vẫn phải được xử lý ở cấu hình graph.

**Câu 8.** `--continue` hoặc `--rerun-tasks` có tự gỡ một chu trình task không?

**Đáp:** Không. `--continue` xử lý cách tiếp tục sau failure; `--rerun-tasks` tác động đến quyết định dùng kết quả trước, cả hai đều không thay đổi cạnh của graph.

**Câu 9.** Tại sao `./gradlew dependencies` không giúp tìm ngay quan hệ `:app:build → :lib:jar`?

**Đáp:** Task `dependencies` mô tả dependency configurations/artifacts, không phải toàn bộ **task execution graph**. Cần `--dry-run`, `--task-graph` khi hỗ trợ, và xem cách file/task providers được nối.

## Tài liệu chính thức

- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): Configuration/Execution và vai trò của task graph.
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): `dependsOn`, `mustRunAfter`, `shouldRunAfter`, `finalizedBy`, skip/exclude.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): task registration và strong/soft task relationships.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--dry-run`, `--task-graph` (từ 9.1), `--continue`, `--rerun-tasks`.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds_intermediate.html): task selectors theo tên và task paths.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): nối task inputs/outputs thay vì dependency thô.
- [Gradle — Understanding Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html): trạng thái `UP-TO-DATE`, `FROM-CACHE`, `SKIPPED`, `NO-SOURCE`.
- [Gradle — Task API](https://docs.gradle.org/current/javadoc/org/gradle/api/Task.html): hợp đồng các task relationships và task dependencies.
