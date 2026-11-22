# Groovy DSL và Kotlin DSL: cách lựa chọn và đọc tài liệu

## 1. Hai DSL giải quyết cùng một bài toán

Gradle là công cụ tự động hóa build: áp dụng plugin, khai báo nơi lấy thư viện, quản lý dependency, cấu hình task, chạy kiểm thử và đóng gói ứng dụng. **Groovy DSL** và **Kotlin DSL** là hai cách viết *build script* để điều khiển cùng mô hình Gradle và cùng hệ thống plugin/API; chúng không quyết định chương trình được viết bằng Java, Groovy hay Kotlin.

- **Groovy DSL:** script dùng cú pháp Groovy, thường nằm ở `build.gradle`, `settings.gradle`.
- **Kotlin DSL:** script dùng cú pháp Kotlin, thường nằm ở `build.gradle.kts`, `settings.gradle.kts`. Đuôi `.gradle.kts` biểu thị Kotlin script của Gradle; không có nghĩa ứng dụng phải dùng Kotlin.
- **Gradle Wrapper:** `gradlew` / `gradlew.bat` giúp cả nhóm dùng phiên bản Gradle được khai báo ở `gradle/wrapper/gradle-wrapper.properties`. Phiên bản này ảnh hưởng cú pháp và API thực tế có thể dùng.

Trong một dự án nhiều module, một số module có thể dùng Groovy DSL và module khác dùng Kotlin DSL. Tuy vậy, mỗi thư mục dự án nên duy trì **một build script chính rõ ràng** (`build.gradle` hoặc `build.gradle.kts`), tránh hai tập tin cùng vai trò gây nhầm lẫn.

## 2. Khác biệt cần nhớ khi đọc cú pháp

| Khía cạnh | Groovy DSL | Kotlin DSL | Điều cần hiểu |
| --- | --- | --- | --- |
| Khai báo plugin Java | `id 'java'` | `id("java")` hoặc `java` | Cùng plugin ID; Kotlin có accessor ngắn cho một số plugin lõi. |
| Chuỗi | `'abc'` hoặc `"abc"` | `"abc"` | Kotlin không dùng dấu nháy đơn để biểu diễn chuỗi. |
| Gọi hàm | `mavenCentral()`, `implementation 'g:a:v'` | `mavenCentral()`, `implementation("g:a:v")` | Groovy cho phép lược dấu ngoặc trong nhiều lời gọi. |
| Gán thuộc tính | `group = 'org.demo'` | `group = "org.demo"` | Đối chiếu đúng kiểu thuộc tính; với Gradle `Property<T>`, `.set(...)` thường là cách tường minh và tương thích. |
| Named arguments | `exclude group: 'g', module: 'm'` | `exclude(group = "g", module = "m")` | Cú pháp Kotlin có dấu `=`; không sao chép dấu `:` của Groovy. |
| Khai báo biến | `def message = 'hi'` | `val message = "hi"` | Kotlin phân biệt `val` (tham chiếu không gán lại) và `var`. |
| Cấu hình bằng block | `tasks.register('hello') { ... }` | `tasks.register("hello") { ... }` | Groovy dùng closure; Kotlin dùng lambda với receiver/DSL API. |
| Kiểm tra tên/kiểu | Linh hoạt, có tra cứu động lúc chạy script | Có kiểm tra kiểu và gợi ý API khi biên dịch script | Kotlin có thể phát hiện lỗi tên/kiểu sớm hơn, nhưng còn phụ thuộc plugin và cách khai báo. |

Trong cả hai DSL, **tên plugin, configuration, task và tọa độ Maven** thường không đổi. Ví dụ `implementation` vẫn chỉ configuration dùng để khai báo dependency; chỉ cách viết lời gọi khác nhau.

## 3. Một ví dụ chạy được với hai cách viết

Tạo một thư mục dự án Gradle có Wrapper, chọn **một** trong hai script sau để đặt ở thư mục gốc. Ví dụ dùng plugin `java` và một task đơn giản, không yêu cầu có mã nguồn Java.

**Phương án A — `build.gradle` (Groovy DSL)**

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

tasks.register('chao') {
    group = 'learning'
    description = 'Ví dụ một task Gradle'
    doLast {
        println 'Xin chào Gradle!'
    }
}
```

**Phương án B — `build.gradle.kts` (Kotlin DSL)**

```kotlin
plugins {
    id("java")
}

repositories {
    mavenCentral()
}

tasks.register("chao") {
    group = "learning"
    description = "Ví dụ một task Gradle"
    doLast {
        println("Xin chào Gradle!")
    }
}
```

Chạy từ thư mục chứa Wrapper:

```bash
# Linux/macOS
./gradlew chao --console=plain
```

```powershell
# Windows PowerShell
.\gradlew.bat chao --console=plain
```

Ở cả hai phương án, task in đúng dòng `Xin chào Gradle!` (ngoài dòng này, Gradle có thể hiển thị tên task và thông tin build). `tasks.register(...)` đăng ký task theo cơ chế cấu hình trì hoãn; `doLast { ... }` là hành động được thực thi khi task chạy. Viết Groovy hay Kotlin không thay đổi mục tiêu của task.

Khi cần dependency và kiểm thử Java với JUnit 5, có thể **bổ sung** các đoạn tương đương sau vào script tương ứng (giả định plugin Java và `mavenCentral()` như ở trên):

**Groovy DSL**

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Kotlin DSL**

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

Hai ví dụ vừa bổ sung cùng dependency và cấu hình task `test` dùng JUnit Platform. Chúng chưa chứa lớp kiểm thử; cần tạo test trong `src/test/java` mới có bài kiểm thử thực tế để chạy. Phiên bản dependency chỉ mang tính minh họa: khi áp dụng vào dự án, ưu tiên phiên bản đã được kiểm tra và quản lý tập trung.

## 4. Cách lựa chọn DSL

| Bối cảnh | Lựa chọn thực dụng | Vì sao |
| --- | --- | --- |
| Dự án đang ổn định với `build.gradle` và nhiều script/plugin dựa vào hành vi động của Groovy | Tiếp tục Groovy DSL khi chưa có lý do chuyển đổi rõ ràng | Hạn chế chi phí chuyển đổi, rủi ro plugin tương tác với closure và kiến thức đội ngũ. |
| Dự án mới, thành viên quen Kotlin/IDE hỗ trợ tốt, muốn gợi ý tên API và kiểm tra kiểu | Cân nhắc Kotlin DSL | Hỗ trợ tự hoàn thành, điều hướng API và refactor tốt trong IDE có tích hợp Gradle. |
| Dự án mới nhưng nhóm chỉ quen Groovy hoặc tài liệu plugin chủ yếu viết Groovy | Groovy DSL vẫn hợp lý | Thời gian học và khả năng bảo trì quan trọng hơn lựa chọn ngôn ngữ script. |
| Dự án nhiều module, muốn chuyển dần | Chuyển từng script/module sau khi kiểm thử | Gradle cho phép kết hợp cả hai DSL trong cùng build; không cần đổi đồng loạt. |
| Plugin cũ cung cấp API chủ yếu qua Groovy closure hoặc cấu hình động | Thử plugin với Kotlin DSL trước khi quyết định | Kotlin DSL có thể cần gọi API theo kiểu tường minh hoặc xử lý tương tác Groovy–Kotlin. |

**Tiêu chí ưu tiên:** mức độ phù hợp với codebase hiện tại, khả năng của plugin và Gradle Wrapper, kinh nghiệm nhóm, trải nghiệm IDE, khối lượng script cần duy trì và thời gian kiểm thử chuyển đổi. Không có quy tắc “Kotlin DSL luôn nhanh hơn” hay “Groovy DSL luôn dễ hơn”. Tốc độ cấu hình/build còn do plugin, cache, tác vụ và cách viết script; việc biên dịch Kotlin script có thể tăng thời gian ở một số lần build đầu hoặc khi cache bị vô hiệu.

Một quy tắc dễ áp dụng: **đọc và sửa theo DSL mà dự án đang dùng**, chỉ đề xuất chuyển DSL nếu lợi ích dài hạn bù được chi phí chuyển đổi và đã xác nhận plugin tương thích.

## 5. Đọc tài liệu Gradle đúng cách

**Bước 1 — Xác định ngữ cảnh trước khi sao chép code.** Mở `build.gradle` hoặc `build.gradle.kts` và `settings.gradle` hoặc `settings.gradle.kts`; xem `gradle/wrapper/gradle-wrapper.properties` để biết phiên bản Gradle. Phân biệt file cấu hình toàn build (`settings`), file cấu hình project/module (`build`) và `gradle.properties` (properties), vì cùng một block không phải lúc nào cũng đặt được ở mọi file.

**Bước 2 — Chọn đúng tab ngôn ngữ trong ví dụ.** Gradle User Manual thường có đoạn “Groovy” và “Kotlin”. Lấy đoạn tương ứng với đuôi script. Nếu trang chỉ có Groovy, cần chuyển đổi *cú pháp và kiểu API*, không thay dấu nháy một cách máy móc.

**Bước 3 — Đọc cấu trúc của đoạn mã.** Chú ý:

- `plugins { ... }`: plugin cung cấp task, extension và configuration nào?
- `repositories { ... }`: lấy artifact ở đâu?
- `dependencies { ... }`: `implementation`, `testImplementation` là configuration nào, được tạo bởi plugin nào?
- `java { ... }`, `application { ... }`: cấu hình extension do plugin cung cấp.
- `tasks.register(...)` và `tasks.named(...)`: tạo mới task hay cấu hình task đã tồn tại?
- `settings.gradle(.kts)`: điều khiển danh sách project với `include`, plugin management và các thiết lập cấp build.

**Bước 4 — Tra ngược từ khái niệm sang API.** Nếu tài liệu nói đến “task”, “extension”, “configuration” hay “Provider”, hãy tìm cùng tên trong Gradle User Manual và API reference, rồi kiểm tra kiểu nhận vào. Ví dụ `tasks.named<Test>("test")` trong Kotlin dùng generic để truy cập các phương thức riêng của `Test`; Groovy có thể biểu diễn gần tương đương là `tasks.named('test', Test)`.

**Bước 5 — Kiểm tra điều kiện sinh type-safe accessor.** Kotlin DSL sinh accessor cho nhiều phần tử mô hình được plugin khai báo sớm trong `plugins { }`. Nếu plugin chỉ được `apply(plugin = "...")` ở thân script, hoặc configuration được tạo sau bước sinh accessor, tên như `implementation(...)` hay `myCustomConfiguration(...)` có thể không tồn tại dưới dạng hàm Kotlin. Khi đó dùng API tường minh, ví dụ `dependencies.add("implementation", "g:a:v")` **nếu** configuration đó thực sự có tồn tại, hoặc tìm extension/task qua container và kiểu tương ứng. Không “sửa” bằng cách đoán tên hàm.

**Bước 6 — Đối chiếu phiên bản và chạy lệnh xác nhận.** Chọn trang tài liệu tương ứng phiên bản Gradle Wrapper khi cú pháp/API có thay đổi; kiểm tra plugin bên thứ ba có tài liệu theo phiên bản riêng. Dùng:

```bash
./gradlew --version
./gradlew tasks --all
./gradlew help --task test
./gradlew help
```

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`. Lệnh `help --task test` giúp xem thông tin task tên `test` khi task đó có trong project. Nếu ví dụ mới đưa vào làm script lỗi biên dịch/cấu hình, đọc thông báo lỗi và so lại Gradle version, plugin, import, vị trí block trước khi kết luận Gradle không hỗ trợ tính năng.

## 6. Tự chuyển một ví dụ Groovy sang Kotlin khi chỉ có một bản tài liệu

Giả sử tài liệu plugin/Gradle đưa ví dụ Groovy:

```groovy
plugins {
    id 'java'
}

group = 'com.example'

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

tasks.register('thongBao') {
    doLast { println 'Da cau hinh xong' }
}
```

Bản Kotlin DSL tương ứng, dùng cùng plugin, group, dependency và tên task:

```kotlin
plugins {
    id("java")
}

group = "com.example"

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}

tasks.register("thongBao") {
    doLast { println("Da cau hinh xong") }
}
```

Để áp dụng ví dụ này cần có `repositories { mavenCentral() }` (hoặc một repository phù hợp) khi thực sự resolve dependency. Cách chuyển: giữ nguyên ngữ nghĩa và tên API; đổi chuỗi thành `"..." `, thêm dấu ngoặc khi gọi hàm, dùng `=` cho tham số có tên, kiểm tra kiểu và import nếu Kotlin yêu cầu. Đừng dịch nguyên xi mọi cú pháp Groovy: biểu thức động, `ext`, `Closure` và các plugin custom có thể đòi hỏi cách cấu hình khác.

## 7. Lỗi phổ biến và hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Kotlin báo `Unexpected tokens` tại `implementation '...'` | Sao chép cú pháp Groovy vào `.gradle.kts` | Dùng `implementation("...")`. |
| Kotlin báo `Unresolved reference: implementation` | Chưa có configuration từ plugin, plugin áp dụng quá muộn hoặc accessor chưa có | Xem `plugins { }`, danh sách configuration, rồi dùng đúng accessor/API container. |
| Kotlin không hiểu `exclude group: ..., module: ...` | Named arguments của Groovy khác Kotlin | Dùng `exclude(group = "...", module = "...")`. |
| Task hiện có nhưng truy cập thuộc tính riêng bị lỗi kiểu | Kotlin chỉ suy luận kiểu tổng quát `Task` | Dùng `tasks.named<Test>("test")` hoặc kiểu task thực, tìm bằng `help --task`. |
| Plugin chạy với Groovy nhưng Kotlin báo lỗi closure/overload | API plugin dùng cơ chế Groovy động, thiếu overload Kotlin thuận tiện | Tra tài liệu plugin/Gradle API, dùng cấu hình có kiểu hoặc cân nhắc giữ phần script Groovy. |
| Ví dụ trong tài liệu không chạy trên dự án | Khác phiên bản Gradle/plugin, thiếu repository, block đặt sai file hoặc thiếu plugin | Đối chiếu Wrapper, plugin ID/version, file `settings` hay `build`, rồi chạy task nhỏ để kiểm chứng. |
| Lạm dụng `tasks.create` / `tasks.getByName` | Tạo/cấu hình task sớm không cần thiết | Khi phù hợp dùng `tasks.register` / `tasks.named` để Gradle có thể trì hoãn cấu hình. |

## 8. Tự kiểm tra kiến thức

1. Dự án có `build.gradle.kts` nhưng toàn bộ mã ứng dụng là Java. Có gì sai không? **Không:** DSL của build và ngôn ngữ ứng dụng độc lập.
2. Gặp snippet Groovy `testImplementation 'g:a:1.0'` trong khi dự án dùng Kotlin DSL. Trước tiên cần kiểm tra gì? **Plugin tạo ra configuration `testImplementation`**, rồi chuyển thành `testImplementation("g:a:1.0")`.
3. Muốn tìm cách cấu hình một task đã tồn tại mà chưa biết kiểu, tra gì? Dùng `./gradlew help --task <ten-task>` và tài liệu/API của kiểu task.
4. Khi chuyển nhiều module, bắt buộc đổi tất cả file `.gradle` sang `.gradle.kts` cùng lúc không? **Không:** có thể chuyển từng module và kiểm thử từng phần.

**Kết quả cần đạt:** nhận biết chính xác DSL từ đuôi file; chọn theo nhu cầu dự án thay vì xu hướng; đọc được ví dụ ở cả hai DSL; chuyển những cấu hình phổ biến mà không làm thay đổi ngữ nghĩa; và biết tra đúng API, plugin và phiên bản khi gặp đoạn tài liệu khó.

## Tài liệu chính thức để tra cứu thêm

- [Gradle User Manual — Writing Build Scripts](https://docs.gradle.org/current/userguide/writing_build_scripts.html): cấu trúc và vai trò build script.
- [Gradle Kotlin DSL Primer](https://docs.gradle.org/current/userguide/kotlin_dsl.html): type-safe accessors, container API, `Provider` và các khác biệt của Kotlin DSL.
- [Migrating build logic from Groovy to Kotlin](https://docs.gradle.org/current/userguide/migrating_from_groovy_to_kotlin_dsl.html): ví dụ hai ngôn ngữ, lộ trình chuyển đổi và giới hạn tương tác.
- [Gradle User Manual](https://docs.gradle.org/current/userguide/userguide.html): tra plugin, task, dependencies và chọn tài liệu phù hợp phiên bản Wrapper.
