# Build khai báo, đồ thị công việc và khả năng mở rộng bằng mã trong Gradle

## 1. Bức tranh tổng thể: Gradle biến mô tả dự án thành các công việc có thứ tự

Khi xây dựng ứng dụng Java, ta thường cần biên dịch mã nguồn, chạy kiểm thử, đóng gói JAR, tạo tài liệu hoặc chuẩn bị bản phân phối. Nếu viết một chuỗi lệnh thủ công, người thực hiện phải tự nhớ bước nào cần chạy trước, bước nào có thể bỏ qua và cách lặp lại quy trình ở máy khác.

Gradle giải bài toán này bằng ba ý tưởng gắn với nhau:

| Ý tưởng | Câu hỏi được giải quyết | Biểu hiện trong Gradle |
| --- | --- | --- |
| **Build khai báo** (declarative build) | Dự án cần thành phần, cấu hình và kết quả gì? | Khối `plugins`, `repositories`, `dependencies`; đăng ký và cấu hình task bằng DSL |
| **Đồ thị công việc** (task graph) | Với mục tiêu được yêu cầu, task nào cần chạy và task nào phải đi trước? | `Task` và các quan hệ như `dependsOn`, `mustRunAfter`, `finalizedBy` |
| **Mở rộng bằng mã** (programmable extensibility) | Làm sao định nghĩa quy tắc build mới và tái sử dụng chúng? | Groovy/Kotlin DSL, task tùy chỉnh, lớp task, plugin, convention plugin |

Có thể hình dung luồng xử lý:

```text
Người dùng yêu cầu một mục tiêu build
                |
                v
Build script + plugin khai báo mô hình dự án
                |
                v
Gradle chọn task và dựng đồ thị phụ thuộc
                |
                v
Gradle quyết định thứ tự, trạng thái cần chạy/bỏ qua
                |
                v
Task action thực hiện công việc thực tế
```

Điểm quan trọng: Gradle **không chỉ chạy tuần tự từng dòng trong `build.gradle`**. Build script được dùng để cấu hình mô hình build; các hành động bên trong task được thực thi khi task đó thuộc kế hoạch chạy.

## 2. “Khai báo” trong Gradle nghĩa là gì?

Một cấu hình mang tính khai báo nói với Gradle **điều gì cần có** và **những quan hệ nào tồn tại**, rồi để Gradle lập kế hoạch thực thi. Ví dụ, áp dụng plugin `java` có nghĩa là dự án muốn dùng các quy ước xây dựng Java; Gradle bổ sung các task như `compileJava`, `test` và `jar`.

```groovy
// build.gradle (Groovy DSL)
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Ở đây:

- `plugins` khai báo khả năng build mà dự án sử dụng. Plugin `java` tạo các cấu hình, nguồn đầu vào, task và quan hệ task theo quy ước.
- `repositories` khai báo nơi Gradle tìm các thư viện bên ngoài.
- `dependencies` khai báo thư viện cần cho phạm vi `testImplementation`. Đây là **quan hệ phụ thuộc thư viện**, khác với quan hệ phụ thuộc giữa các task.
- `tasks.named('test', Test)` cấu hình task kiểm thử đã có; `useJUnitPlatform()` chọn nền tảng chạy kiểm thử JUnit 5.

Tuy nhiên, “khai báo” **không có nghĩa** `build.gradle` chỉ là dữ liệu tĩnh. Groovy DSL và Kotlin DSL đều là mã có thể thực thi. Lập trình viên vẫn có thể dùng biến, điều kiện, hàm, lớp và gọi API Gradle. Giá trị của cách tiếp cận khai báo là xây dựng mô hình mà Gradle hiểu được; nên ưu tiên khai báo thuộc tính, quan hệ và đầu vào/đầu ra hơn là tự thực hiện mọi công việc ngay trong quá trình cấu hình.

So sánh hai cách tư duy:

- **Dễ sai:** “Hễ Gradle đọc file build thì gọi trình biên dịch ngay, rồi sao chép file ngay.” Cách này tạo tác dụng phụ trong giai đoạn cấu hình, kể cả khi người dùng chỉ muốn xem trợ giúp.
- **Phù hợp hơn:** “Có một task biên dịch; task đóng gói phụ thuộc vào kết quả biên dịch; chỉ thực hiện hành động khi task thực sự được chọn.” Gradle có thể bỏ qua công việc không cần thiết, kiểm tra đầu vào/đầu ra và tái sử dụng kết quả khi thích hợp.

## 3. Ví dụ chạy được: định nghĩa mục tiêu và để Gradle dựng task graph

Tạo một thư mục dự án nhỏ với hai file:

```text
gradle-graph-demo/
├── settings.gradle
└── build.gradle
```

Nội dung `settings.gradle`:

```groovy
rootProject.name = 'gradle-graph-demo'
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'base'
}

tasks.register('prepareDocs') {
    group = 'documentation'
    description = 'Chuẩn bị nội dung tài liệu'

    doLast {
        println '1. Chuẩn bị tài liệu'
    }
}

tasks.register('renderDocs') {
    group = 'documentation'
    description = 'Tạo tài liệu từ nội dung đã chuẩn bị'
    dependsOn('prepareDocs')

    doLast {
        println '2. Kết xuất tài liệu'
    }
}

tasks.register('publishPreview') {
    group = 'documentation'
    description = 'Tạo bản xem trước của tài liệu'
    dependsOn('renderDocs')

    doLast {
        println '3. Tạo bản xem trước'
    }
}
```

Giải thích:

- `tasks.register` **đăng ký** một task; đây là cách khai báo phù hợp với cơ chế cấu hình theo nhu cầu (configuration avoidance) của Gradle.
- `group` và `description` giúp task dễ tìm khi xem danh sách hoặc trợ giúp.
- `dependsOn('prepareDocs')` tạo cạnh phụ thuộc: muốn chạy `renderDocs` thì phải xử lý `prepareDocs` trước.
- `doLast { ... }` là **hành động thực thi** của task. Phần `println` không chạy chỉ vì Gradle đọc `build.gradle`.

Nếu dự án đã có Gradle Wrapper, chạy trong thư mục dự án:

```bash
./gradlew -q publishPreview
```

Trên Windows PowerShell dùng `.\gradlew.bat -q publishPreview`. Nếu đây là dự án mới chưa có Wrapper, có thể dùng lệnh `gradle -q publishPreview` khi máy đã cài Gradle, rồi chạy `gradle wrapper` để tạo Wrapper. Wrapper nên được đưa vào quản lý phiên bản để các thành viên dùng cùng phiên bản Gradle.

Với nội dung trên, kết quả chuẩn khi dùng `-q` là:

```text
1. Chuẩn bị tài liệu
2. Kết xuất tài liệu
3. Tạo bản xem trước
```

Dù người dùng chỉ yêu cầu `publishPreview`, Gradle tự tìm hai task cần thiết. Đồ thị là:

```text
prepareDocs ──> renderDocs ──> publishPreview
       (mũi tên biểu thị "phải hoàn thành trước")
```

Chạy riêng `./gradlew -q prepareDocs` sẽ chỉ in dòng thứ nhất. Các task không nằm trong kế hoạch chạy không bị thực thi chỉ vì đã được khai báo.

## 4. Task graph: Gradle thực sự lập kế hoạch gì?

**Task** là một đơn vị công việc có tên trong một project Gradle, ví dụ `:compileJava` hoặc `:publishPreview`. Task có thể chứa hành động, có phụ thuộc và có thông tin đầu vào/đầu ra. Tên đầy đủ như `:subproject:test` gồm đường dẫn project và tên task.

**Task graph** là đồ thị có hướng gồm các task được chọn cho lần chạy đó và các ràng buộc phụ thuộc/thứ tự liên quan. Với phụ thuộc thông thường, đồ thị cần không có chu trình: nếu A cần B, B cần C, C lại cần A thì không thể xác định một thứ tự hợp lệ; Gradle báo lỗi.

Đồ thị **không nhất thiết bao gồm mọi task đã đăng ký**. Nó được xác định từ các mục tiêu người dùng yêu cầu, quan hệ mà plugin/build script khai báo và cấu hình hiện hành. Với một đồ thị hợp lệ, Gradle có thể thực thi các task theo thứ tự thỏa điều kiện phụ thuộc; các task độc lập không có cam kết về thứ tự nếu ta chưa đặt ràng buộc phù hợp.

Phân biệt các quan hệ hay gặp:

| API | Ý nghĩa | Có kéo task kia vào kế hoạch chạy không? |
| --- | --- | --- |
| `dependsOn('x')` | Task này cần task `x` được xử lý trước | **Có** |
| `mustRunAfter('x')` | Nếu cả hai cùng được chọn, task này phải chạy sau `x` | **Không** |
| `shouldRunAfter('x')` | Ưu tiên chạy sau `x` nếu Gradle có thể thực hiện | **Không** |
| `finalizedBy('x')` | Đăng ký task `x` làm bước kết thúc (finalizer) của task này | **Có**, khi task được kết thúc theo cơ chế finalizer |
| `onlyIf { ... }` | Điều kiện để chạy hành động của chính task | Không tạo phụ thuộc mới |

Ví dụ bổ sung vào cuối `build.gradle` của mục 3:

```groovy
tasks.register('auditDocs') {
    group = 'documentation'
    mustRunAfter('prepareDocs')

    doLast {
        println 'Kiểm tra tài liệu'
    }
}
```

Chạy `./gradlew -q auditDocs` **không** tự chạy `prepareDocs`: `mustRunAfter` chỉ quy định thứ tự nếu cả hai hiện diện. Ngược lại, khi chạy `./gradlew -q auditDocs prepareDocs`, Gradle sẽ xử lý `prepareDocs` trước `auditDocs`. Muốn việc kiểm tra **bắt buộc** có bước chuẩn bị, phải khai báo `dependsOn('prepareDocs')`.

`finalizedBy` phù hợp cho thao tác dọn dẹp/báo cáo kết thúc; nó khác `dependsOn` về mục đích và cách Gradle sắp lịch. Đừng dùng `mustRunAfter` để thay thế một phụ thuộc dữ liệu thật sự.

Một điểm dễ nhầm: **đồ thị phụ thuộc thư viện** (ví dụ JUnit phụ thuộc những JAR nào) và **đồ thị task** (ví dụ `test` cần `testClasses` trước) là hai vấn đề khác nhau. Plugin có thể kết nối chúng bằng cách cấu hình classpath và task đầu vào, nhưng không nên dùng hai khái niệm như một.

## 5. Ba giai đoạn của một lần chạy Gradle

Để hiểu vì sao khai báo và thực thi tách nhau, cần nắm vòng đời build:

1. **Khởi tạo (initialization):** Gradle xác định build và các project tham gia, đọc cấu hình như `settings.gradle`.
2. **Cấu hình (configuration):** Gradle đánh giá các build script/plugin cần thiết, tạo hoặc đăng ký mô hình task và cấu hình quan hệ. Việc chọn mục tiêu và xây dựng kế hoạch task diễn ra dựa trên mô hình này.
3. **Thực thi (execution):** Gradle xử lý các task được chọn theo ràng buộc của đồ thị và quyết định task có cần chạy hành động không.

Trong ví dụ, các lời gọi `tasks.register(...)` và cấu hình `dependsOn` thuộc về mô hình build; những câu `println` bên trong `doLast` thuộc về hành động của task trong giai đoạn thực thi.

Vì thế, đoạn mã sau là một lỗi thiết kế thường gặp:

```groovy
// Không nên đặt tác dụng phụ này ở cấp cao nhất build.gradle.
println 'Tôi chạy trong lúc cấu hình dự án'
```

Ngay cả `./gradlew help` cũng có thể in dòng trên khi script được đánh giá, dù người dùng không yêu cầu tác vụ tạo tài liệu nào. Khi cần tạo file, gọi công cụ bên ngoài hoặc kết nối dịch vụ, hãy đặt hành vi đó trong task thích hợp và khai báo rõ đầu vào/đầu ra.

**Lưu ý về hiệu năng:** Gradle có các cơ chế như configuration avoidance và configuration cache, vì vậy không phải lần chạy nào cũng đánh giá lại đầy đủ mọi phần cấu hình. Mô hình ba giai đoạn vẫn là cách tư duy cơ bản; cần viết task tương thích với cơ chế cấu hình theo nhu cầu và cấu hình được lưu đệm.

## 6. Sức mạnh của plugin: từ vài khai báo đến cả quy trình build

Trong dự án Java thật, ta thường không tự viết `compileJava`, `processResources`, `classes`, `jar` hoặc `test`. Plugin `java` cung cấp task, cấu hình dependency và quan hệ đã được chuẩn hóa.

Ví dụ một `build.gradle` tối giản cho ứng dụng/thư viện Java:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Ý nghĩa chính:

- `java.toolchain` yêu cầu trình biên dịch/JDK tương thích Java 21 cho các task thích hợp; môi trường phải có toolchain hoặc được cấu hình để Gradle cấp phát một toolchain phù hợp.
- `java` plugin biết thư mục nguồn theo quy ước như `src/main/java`, `src/test/java`.
- `jar` cần các lớp/nguồn lực đã xử lý để đóng gói; `test` dùng mã biên dịch phục vụ kiểm thử. Plugin tự khai báo phần lớn quan hệ thay cho người học.
- Từ lệnh `./gradlew build`, Gradle sẽ chọn thêm những task cần cho vòng kiểm tra/đóng gói theo cấu hình plugin. Không được hiểu rằng mọi task trong danh sách đều bắt buộc chạy hành động ở mỗi lần build.

Các tên mục tiêu quen thuộc:

| Lệnh | Mục đích thông thường khi dùng plugin `java` |
| --- | --- |
| `./gradlew tasks` | Xem các task được giới thiệu theo nhóm |
| `./gradlew compileJava` | Biên dịch Java nguồn chính |
| `./gradlew test` | Chạy kiểm thử được cấu hình |
| `./gradlew jar` | Tạo JAR từ output phù hợp |
| `./gradlew build` | Thực hiện chuỗi kiểm tra và đóng gói mà plugin thiết lập |

Cấu trúc thực tế của task graph có thể đổi khi thêm plugin, project con hoặc cấu hình mới; hãy xem các task thay vì ghi nhớ một danh sách cạnh phụ thuộc cố định cho mọi dự án.

## 7. Khả năng mở rộng bằng mã: khai báo task mới và phát triển kiểu task mới

Gradle cho phép mở rộng theo nhiều mức độ:

1. **Cấu hình task sẵn có:** Dùng plugin và điều chỉnh thuộc tính của task, ví dụ `tasks.named('test', Test)`.
2. **Đăng ký task tùy chỉnh:** Dùng `tasks.register` và `doLast` để biểu diễn một bước riêng của dự án.
3. **Định nghĩa kiểu task:** Tạo lớp kế thừa `DefaultTask` với thuộc tính đầu vào/đầu ra và phương thức gắn `@TaskAction`.
4. **Đóng gói thành plugin:** Khi nhiều project cần cùng quy tắc, đưa logic vào plugin hoặc convention plugin để tái sử dụng thay vì chép mã.

Dưới đây là ví dụ **độc lập có thể chạy** về kiểu task. Đặt toàn bộ mã sau vào `build.gradle` của một thư mục Gradle mới (có `settings.gradle` như mục 3):

```groovy
plugins {
    id 'base'
}

// Dùng tên lớp đầy đủ để ví dụ đặt trực tiếp trong build.gradle.
abstract class WriteBanner extends org.gradle.api.DefaultTask {
    @org.gradle.api.tasks.Input
    abstract org.gradle.api.provider.Property<String> getBanner()

    @org.gradle.api.tasks.OutputFile
    abstract org.gradle.api.file.RegularFileProperty getDestination()

    @org.gradle.api.tasks.TaskAction
    void writeBanner() {
        File target = destination.get().asFile
        target.parentFile.mkdirs()
        target.setText(banner.get() + '\n', 'UTF-8')
    }
}

tasks.register('writeBanner', WriteBanner) {
    banner.set('Gradle là công cụ build')
    destination.set(layout.buildDirectory.file('generated/banner.txt'))
}
```

Chạy:

```bash
./gradlew -q writeBanner
```

Task tạo file `build/generated/banner.txt` với nội dung:

```text
Gradle là công cụ build
```

Ở Windows, có thể đọc file bằng `Get-Content build/generated/banner.txt`; trên hệ Unix dùng `cat build/generated/banner.txt`.

Ở đây, `@Input` giúp Gradle biết nội dung cần sinh phụ thuộc vào giá trị `banner`; `@OutputFile` khai báo file kết quả; `@TaskAction` chỉ rõ phương thức thực hiện công việc. Đường dẫn output được cấp qua `layout.buildDirectory.file(...)`, thay cho việc ghép đường dẫn cứng, giúp phối hợp với mô hình provider của Gradle.

Khi đầu vào và đầu ra không đổi, lần chạy tiếp theo có thể được đánh dấu `UP-TO-DATE` và bỏ qua hành động. **Khai báo input/output không tự động đảm bảo task có thể dùng build cache**: task tùy chỉnh phải đáp ứng các điều kiện bổ sung, thường bao gồm khai báo `@CacheableTask` và hành vi tạo kết quả ổn định, không phụ thuộc trạng thái ẩn. Cũng không nên hiểu `UP-TO-DATE` là task không nằm trong task graph; task có thể nằm trong kế hoạch nhưng hành động bị bỏ qua.

Lưu ý thiết kế: ví dụ đặt lớp task ngay trong `build.gradle` để dễ thử. Với build lớn, nên đưa lớp và plugin vào nơi quản lý build logic riêng (chẳng hạn `buildSrc` hoặc một included build dành cho convention plugins), dùng kiểm thử phù hợp và giữ file `build.gradle` chủ yếu để khai báo cấu hình.

## 8. Từ task riêng lẻ đến plugin và quy ước dùng chung

Một plugin Gradle có thể:

- Tạo hoặc cấu hình task và kiểu task.
- Bổ sung extension để dự án tự khai báo các lựa chọn bằng DSL.
- Thêm cấu hình dependency, quy tắc sử dụng plugin khác và mối quan hệ trong task graph.
- Chuẩn hóa quy trình giữa nhiều module, chẳng hạn tất cả thư viện Java đều dùng cùng toolchain, kiểm thử và cách đóng gói.

Ví dụ, thay vì sao chép một khối cấu hình Java/test dài vào năm module, nhóm phát triển có thể viết một convention plugin, rồi mỗi module chỉ cần khai báo plugin đó và những phần riêng của module. Các task thực tế vẫn được Gradle điều phối theo đồ thị.

**Khi nào chọn cách nào?** Một thao tác nhỏ chỉ có ở một project có thể dùng `tasks.register`. Khi cần xác định rõ input/output và kiểm thử hành vi, nên tạo kiểu task. Khi cùng quy tắc áp dụng cho nhiều project, nên đóng gói thành plugin. Tránh lạm dụng mã tùy biến nếu plugin chuẩn đã cung cấp giải pháp tốt.

Vì Groovy/Kotlin DSL là mã thực thi, Gradle linh hoạt hơn các bộ cấu hình chỉ nhận dữ liệu. Đi cùng sức mạnh đó là trách nhiệm giữ logic build rõ ràng, xác định được đầu vào/đầu ra và tránh tác dụng phụ không kiểm soát.

## 9. Quan sát và kiểm tra thay vì đoán Gradle sẽ chạy gì

Dùng các lệnh sau trong ví dụ ở mục 3:

```bash
./gradlew tasks --all
./gradlew help --task publishPreview
./gradlew publishPreview --dry-run
./gradlew -q publishPreview
```

- `tasks --all` liệt kê các task mà Gradle có thể công bố, hữu ích để tìm tên task đã đăng ký và task từ plugin.
- `help --task ...` cho biết mô tả và thông tin về một task cụ thể.
- `--dry-run` hiển thị các task dự kiến được xử lý mà **không chạy các hành động của task**; những dòng `SKIPPED` ở chế độ này là do dry-run, không đủ để kết luận task bình thường đã `UP-TO-DATE`.
- Bỏ `--dry-run` để quan sát hành động thật. Với ví dụ mục 3, `-q` chỉ để lại ba dòng `println` đã nêu.

Nếu muốn tìm hiểu hiệu năng, có thể quan sát trạng thái `UP-TO-DATE`, `FROM-CACHE` hoặc `NO-SOURCE` trong log khi điều kiện tương ứng tồn tại. Không suy luận rằng mọi task đều được cache: một số task không khai báo output, có tác dụng phụ hoặc chưa được cấu hình để có thể cache.

Khi xử lý build nhiều module, chạy `./gradlew :ten-module:tenTask` để chọn chính xác task thuộc project tương ứng. Gradle vẫn có thể thêm task ở project khác nếu đồ thị phụ thuộc yêu cầu.

## 10. Lỗi phổ biến và cách sửa

| Triệu chứng hoặc cách hiểu sai | Nguyên nhân | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Lệnh `help` cũng sửa file hoặc gọi dịch vụ ngoài | Đặt tác dụng phụ ở cấp cao nhất của build script | Đưa công việc vào `@TaskAction`/`doLast` của task được khai báo |
| Chạy task B nhưng task A bắt buộc lại không chạy | Chỉ dùng `mustRunAfter('A')` | Dùng `dependsOn('A')` nếu B thực sự cần A |
| Task chạy nhưng kết quả cũ không được nhận diện | Không khai báo chính xác input/output hoặc công việc có tác dụng phụ | Dùng kiểu task có thuộc tính được gắn annotation phù hợp; tránh trạng thái ẩn |
| Lần thứ hai task không in gì và tưởng lỗi | Gradle xác định task không cần chạy lại | Xem trạng thái task/log, phân biệt `UP-TO-DATE` với thất bại |
| Build script phình to, lặp giữa module | Chép cùng một quy tắc vào nhiều file | Tạo lớp task hoặc plugin quy ước dùng chung |
| Phụ thuộc task nhưng chương trình không đọc được file mong muốn | `dependsOn` chỉ sắp thứ tự, không tự truyền dữ liệu | Khai báo rõ file đầu vào/đầu ra và kết nối các provider phù hợp |
| Thứ tự hai task độc lập thay đổi | Chưa có ràng buộc thứ tự | Khai báo phụ thuộc thật hoặc `mustRunAfter` khi chỉ cần thứ tự |
| Đăng ký task khiến cấu hình chậm | Cấu hình/nhận task theo cách háo hức, làm nhiều việc lúc cấu hình | Ưu tiên `tasks.register`, `tasks.named` và provider; đo lường trước khi tối ưu |

## 11. Tự thực hành và kiểm tra hiểu bài

**Bài tập 1 — dự đoán đồ thị.** Dựa trên ba task `prepareDocs`, `renderDocs` và `publishPreview` ở mục 3, hãy dự đoán output khi chạy `./gradlew -q renderDocs`. Đáp án: chỉ có hai dòng “1. Chuẩn bị tài liệu” và “2. Kết xuất tài liệu”, theo đúng thứ tự vì `renderDocs` phụ thuộc `prepareDocs`.

**Bài tập 2 — thử quan hệ thứ tự.** Thêm `auditDocs` ở mục 4. So sánh `./gradlew -q auditDocs` với `./gradlew -q auditDocs prepareDocs`. Giải thích vì sao lệnh đầu không gọi `prepareDocs` dù có `mustRunAfter`.

**Bài tập 3 — kiểm tra khả năng bỏ qua công việc.** Chạy hai lần `./gradlew writeBanner` với cùng giá trị `banner` và cùng đường dẫn `destination`. Quan sát trạng thái của task. Sau đó sửa `banner` và chạy lại; giải thích vì sao thay đổi đầu vào có thể khiến task phải tạo lại file.

**Câu hỏi tự kiểm tra:**

1. Phần nào của build script tạo mô hình task và phần nào thực hiện hành động của task?
2. Vì sao `dependsOn` và `mustRunAfter` không thể thay thế cho nhau?
3. Một task có thể thuộc task graph nhưng không thực thi hành động trong lần chạy đó không?
4. Khi nào nên viết một task riêng, một lớp task hoặc một plugin dùng chung?
5. Muốn Gradle bỏ qua được công việc lặp lại một cách đáng tin cậy, task cần mô tả những gì?

**Ghi nhớ:** Build khai báo giúp Gradle hiểu **mục tiêu và cấu hình**; task graph giúp Gradle biết **công việc cần chọn và ràng buộc thứ tự**; khả năng mở rộng bằng mã giúp dự án mô tả **cách thực hiện những công việc đặc thù**. Kết hợp cả ba đúng cách sẽ tạo build dễ đọc, tái sử dụng được, ít làm thừa và dễ kiểm chứng.