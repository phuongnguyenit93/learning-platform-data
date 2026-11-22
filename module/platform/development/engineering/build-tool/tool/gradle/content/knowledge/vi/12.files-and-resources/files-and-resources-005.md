# Dùng CopySpec để tái sử dụng quy tắc bố trí tệp trong Gradle

## 1. Vấn đề thực tế: nhiều task cần cùng một bố cục tệp

Giả sử một dự án Gradle cần làm hai việc:

- Chép các tài liệu Markdown sang thư mục staging để xem trước.
- Đóng gói chính những tài liệu ấy thành file ZIP để phát hành.

Nếu hai task khai báo lại nhiều lần danh sách nguồn, bộ lọc, tên file và vị trí bên trong gói, rất dễ xảy ra lệch nhau: task chép file A nhưng archive bỏ sót A, hoặc một bên còn chứa file tạm. **`CopySpec`** giải quyết bài toán này bằng cách đóng gói **quy tắc chọn, xử lý và bố trí file** thành một cấu hình có thể gắn vào nhiều tác vụ copy/archive.

Hiểu đúng vai trò:

- **`CopySpec`** là *bản đặc tả*: file đến từ đâu, lọc theo mẫu nào, đổi tên hoặc đổi vị trí tương đối ra sao.
- **`Copy` / `Sync` / `Zip` / `Tar`** là những *task* có thể sử dụng các đặc tả ấy để tạo output khi được thực thi.
- Hàm **`copySpec { ... }`** tạo đối tượng đặc tả, **không tự chép file** hoặc tạo ZIP.
- Hàm **`with(sharedSpec)`** gắn một đặc tả đã có vào một task/spec khác, giúp dùng lại cùng quy tắc mà không sao chép logic.

**Mục tiêu học:** viết được một `CopySpec` dùng chung, đọc được cấu trúc cha–con của `from`/`into`, tái sử dụng cho `Copy` và `Zip`, phân biệt trường hợp nên dùng `CopySpec` với trường hợp chỉ cần một `Action<CopySpec>`, và tránh lỗi đường dẫn hoặc file trùng đích.

## 2. Các khái niệm cần phân biệt

| Thành phần | Ví dụ | Chức năng |
| --- | --- | --- |
| `CopySpec` | `copySpec { from("docs") { ... } }` | Tập quy tắc lấy, lọc, đổi tên, đổi vị trí file |
| `from(...)` | `from("docs/common")` | Định nghĩa file/directory nguồn; có thể thêm child specification |
| `into(...)` | `into(layout.buildDirectory.dir("stage"))` | Chỉ định thư mục output cấp gốc khi cấu hình task `Copy` |
| `into("manual")` trong child spec | `from("docs") { into("manual") }` | Đưa file nguồn vào thư mục con `manual`, tương đối với đích gốc |
| `include(...)` / `exclude(...)` | `include("**/*.md")` | Chọn/bỏ file theo pattern |
| `rename(...)` | `rename("(.+)-draft(.+)", "$1$2")` | Đổi tên file trong lúc copy |
| `with(spec)` | `with(docsLayout)` | Nhúng một spec đã tạo vào spec/task hiện tại |
| `Copy` | `tasks.register<Copy>("stageDocs")` | Sao chép nội dung ra thư mục |
| `Sync` | `tasks.register<Sync>("syncDocs")` | Sao chép rồi loại các file đích không thuộc tập kết quả |
| `Zip` | `tasks.register<Zip>("bundleDocs")` | Tạo ZIP với các entry có cấu trúc đã chọn |

Một điểm quan trọng: cấu hình `CopySpec` **không phải danh sách file đã được sao chép**. Nó mô tả quy tắc cho task thực thi sau; nếu nguồn chưa có file ở thời điểm thực thi, task có thể không có gì để xử lý.

Đường dẫn trong `from` thường được giải quyết dựa trên ngữ cảnh project cung cấp cấu hình. Khi chuyển cấu hình sang project/subproject khác, đừng mặc định chuỗi `"docs"` luôn trỏ về cùng một thư mục. Với file được task khác sinh ra, nên dùng output provider từ task tạo file để Gradle theo dõi dependency.

## 3. Ví dụ hoàn chỉnh: một CopySpec dùng chung cho Copy và Zip

Bắt đầu bằng dự án có **Gradle Wrapper**, với thư mục nguồn sau:

~~~text
gradle-copy-spec-demo/
├── build.gradle.kts
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── docs/
    ├── common/
    │   ├── intro.md
    │   └── notes.txt
    └── local/
        ├── setup.md
        └── cache.tmp
~~~

Tạo các file với nội dung bất kỳ, ví dụ `intro.md` ghi `# Introduction` và `setup.md` ghi `# Setup`. Mục tiêu là chỉ lấy file Markdown và bố trí chung như sau:

~~~text
manual/
├── common/
│   └── intro.md
└── local/
    └── setup.md
~~~

### 3.1. Cấu hình Kotlin DSL chạy được

**File `build.gradle.kts`:**

~~~kotlin
import org.gradle.api.file.CopySpec
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.tasks.Copy
import org.gradle.api.tasks.bundling.Zip

val docsLayout: CopySpec = copySpec {
    from("docs/common") {
        include("**/*.md")
        into("manual/common")
    }

    from("docs/local") {
        include("**/*.md")
        into("manual/local")
    }

    exclude("**/*.tmp")
}

tasks.register<Copy>("stageDocs") {
    group = "documentation"
    description = "Stage selected Markdown files"
    into(layout.buildDirectory.dir("staged-docs"))
    duplicatesStrategy = DuplicatesStrategy.FAIL
    with(docsLayout)
}

tasks.register<Zip>("bundleDocs") {
    group = "documentation"
    description = "Package the same Markdown layout"
    archiveFileName.set("docs.zip")
    destinationDirectory.set(layout.buildDirectory.dir("archives"))
    duplicatesStrategy = DuplicatesStrategy.FAIL
    with(docsLayout)
}
~~~

Cả `Copy` lẫn `Zip` nhận đúng cùng một đối tượng `docsLayout`. Chỉ **đích ngoài cùng** khác nhau:

- `stageDocs` dùng `into(layout.buildDirectory.dir("staged-docs"))`, nghĩa là chép ra thư mục trên filesystem.
- `bundleDocs` dùng `destinationDirectory` và `archiveFileName`, nghĩa là tạo một ZIP trong thư mục `build/archives` (theo build directory mặc định). Bố cục bên trong ZIP được quyết định bởi child `into` của `docsLayout`.
- `duplicatesStrategy = DuplicatesStrategy.FAIL` cho build báo lỗi rõ nếu hai file cố chiếm cùng đường dẫn đích, thay vì âm thầm chọn một file hoặc tạo entry trùng.

### 3.2. Chạy và kiểm tra kết quả

Linux/macOS:

~~~bash
./gradlew stageDocs bundleDocs
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat stageDocs bundleDocs
~~~

Nếu nguồn đúng như sơ đồ, vị trí output dự kiến (khi build directory chưa tùy chỉnh):

~~~text
build/
├── staged-docs/
│   └── manual/
│       ├── common/
│       │   └── intro.md
│       └── local/
│           └── setup.md
└── archives/
    └── docs.zip
~~~

Bên trong `docs.zip` có các entry:

~~~text
manual/common/intro.md
manual/local/setup.md
~~~

`notes.txt` bị loại vì không khớp `include("**/*.md")` của từng nguồn; `cache.tmp` vừa không khớp include vừa thuộc mẫu exclude ở spec cha. Những sơ đồ trên là **cấu trúc tệp/kết quả trong archive**, không phải stdout cố định của Gradle. Console có thể in trạng thái task như `UP-TO-DATE` tùy lần chạy.

Bạn có thể mở ZIP bằng công cụ nén của hệ điều hành, hoặc dùng lệnh `unzip -l build/archives/docs.zip` nếu máy có `unzip`. Kết quả liệt kê thường có thêm ngày, kích thước và header riêng.

### 3.3. Vì sao một CopySpec lại dùng được ở hai task?

`CopySpec` **độc lập với task**, đồng thời có cấu trúc phân cấp. Bản `docsLayout` mô tả nguồn, quy tắc chọn và đường dẫn tương đối `manual/...`. Lúc thực thi, mỗi task kết hợp spec được gắn qua `with` với đích riêng của nó:

~~~text
                 docsLayout (CopySpec)
              /        |           \
      from docs/common |     from docs/local
      into manual/common     into manual/local
              \        |           /
                    with(...)
                   /        \
                  v          v
              stageDocs   bundleDocs
               Copy           Zip
                 |             |
    build/staged-docs/   build/archives/docs.zip
~~~

Khi muốn thêm `docs/common/faq.md` vào cả thư mục staging và ZIP, chỉ cần đặt file vào nguồn phù hợp. Nếu muốn thay đổi một mẫu lọc, chỉnh một nơi trong `docsLayout`; cả hai task dùng chung quy tắc ấy.

**Không gán cùng một root destination filesystem cho hai task một cách tùy tiện.** Bố cục file chung là hợp lý, nhưng output thực tế của task nên có ownership riêng; hai task cùng ghi một thư mục có thể gây lỗi incremental, cache và race condition.

## 4. Cấu trúc cha–con của CopySpec: hiểu đường dẫn tương đối

Mỗi `CopySpec` có thể có **child specs**. Các lời gọi `from(source) { ... }` và `into("subpath") { ... }` có thể tạo nhánh con với các quy tắc riêng. Quy tắc của spec cha thường được **kế thừa** xuống nhánh con: destination tương đối, includes/excludes, copy actions, name mappings và filters. Child spec bổ sung hoặc thu hẹp cách xử lý theo nhánh.

Ví dụ trong `build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.Copy

tasks.register<Copy>("prepareSite") {
    into(layout.buildDirectory.dir("site"))
    exclude("**/*.tmp")

    from("website/pages") {
        include("**/*.html")
    }

    from("website/scripts") {
        include("**/*.js")
        into("js")
    }

    into("assets") {
        from("website/images") {
            include("**/*.png")
        }
    }
}
~~~

Với cây nguồn:

~~~text
website/
├── pages/index.html
├── pages/draft.tmp
├── scripts/app.js
└── images/logo.png
~~~

Output dự kiến:

~~~text
build/site/
├── index.html
├── js/app.js
└── assets/logo.png
~~~

Cách đọc từng phần:

- `into(layout.buildDirectory.dir("site"))` ở **task gốc** thiết lập destination trên filesystem.
- `from("website/pages") { include("**/*.html") }` chỉ mang HTML từ nguồn pages vào root destination.
- `from("website/scripts") { into("js") }` đưa JS vào thư mục con `js` tính từ root destination.
- `into("assets") { from("website/images") ... }` tạo nhánh spec cho thư mục con `assets` rồi thêm nguồn images.
- `exclude("**/*.tmp")` ở cấp cha áp dụng cho các nhánh con; file tạm không lọt vào output.

**Quy tắc quan trọng:** với copy ra filesystem, thường có **một đích root** dạng `into(layout.buildDirectory.dir(...))` cho toàn task. Các `into("relative/path")` trong child spec điều chỉnh **đường dẫn tương đối** bên dưới root đó, không nhằm ghi ra một thư mục độc lập bên ngoài.

### 4.1. Phân biệt hai dạng into

~~~kotlin
tasks.register<Copy>("a") {
    from("src/docs")
    into(layout.buildDirectory.dir("docs-out"))
}
~~~

`into` ở task gốc là **destination của cả thao tác**.

~~~kotlin
tasks.register<Copy>("b") {
    into(layout.buildDirectory.dir("docs-out"))
    from("src/docs") {
        into("manual")
    }
}
~~~

`into("manual")` là **đường dẫn con** cho nguồn `src/docs`, nên file `src/docs/readme.md` (nếu có) ra `build/docs-out/manual/readme.md`.

Thư mục nguồn `src/docs` không tự xuất hiện như một cấp thư mục mới ở output: khi `from` nhận directory, Gradle thường chép **nội dung bên trong** thư mục ấy. Muốn giữ tên `docs` làm thư mục con phải khai báo child `into("docs")` tương ứng.

### 4.2. Phạm vi include/exclude và bộ lọc

Đặt `include` ở root spec sẽ ảnh hưởng mọi nhánh; đặt trong `from(...) { ... }` thì chỉ áp dụng cho nhánh tương ứng, có xét các quy tắc kế thừa. Vì vậy:

~~~kotlin
tasks.register<Copy>("onlyDocs") {
    from("docs")
    into(layout.buildDirectory.dir("docs-only"))
    include("**/*.md")
}
~~~

chỉ lấy Markdown từ nguồn. Nhưng khi hai loại file cần hai quy tắc khác nhau, tách child specs:

~~~kotlin
tasks.register<Copy>("mixedDocs") {
    into(layout.buildDirectory.dir("mixed-docs"))

    from("docs") {
        include("**/*.md")
        into("manual")
    }

    from("images") {
        include("**/*.png")
        into("images")
    }
}
~~~

Không đưa `include("**/*.md")` lên root trong ví dụ thứ hai: nó có thể khiến nhánh ảnh PNG cũng bị lọc, làm output sai. **Vị trí đặt rule quyết định phạm vi tác động**.

## 5. Tái sử dụng quy tắc theo hai kiểu: shared CopySpec và shared Action

Không phải lúc nào cũng nên chia sẻ **nguồn file**. Có hai nhu cầu khác nhau:

| Nhu cầu | Cách làm | Đặc điểm |
| --- | --- | --- |
| Nhiều task dùng **cùng nguồn và cùng layout** | `val common = copySpec { from(...) { ... } }` rồi `with(common)` | Tái sử dụng cả source lẫn cách xử lý |
| Nhiều task dùng **nguồn khác nhau**, chỉ trùng rules | `val rules = Action<CopySpec> { ... }` rồi `from("nguon", rules)` | Mỗi task giữ nguồn riêng, chỉ tái sử dụng pattern/rename/filter |

### 5.1. CopySpec dùng chung khi nguồn giống nhau

Đây là cách đã dùng ở mục 3. Một ví dụ tối giản:

~~~kotlin
import org.gradle.api.file.CopySpec
import org.gradle.api.tasks.Copy

val sharedSources: CopySpec = copySpec {
    from("handbook") {
        include("**/*.md")
        into("manual")
    }
}

tasks.register<Copy>("copyHandbook") {
    into(layout.buildDirectory.dir("handbook-copy"))
    with(sharedSources)
}
~~~

Spec đứng ngoài task định nghĩa **đồng thời** thư mục nguồn `handbook` và cách đặt vào `manual`. Trong thực tế, một spec độc lập thường nên có ít nhất một `from`; nếu chỉ có các pattern, action có thể là mô hình chia sẻ phù hợp hơn.

### 5.2. Action<CopySpec> dùng chung khi nguồn khác nhau

**File `build.gradle.kts` độc lập:**

~~~kotlin
import org.gradle.api.Action
import org.gradle.api.file.CopySpec
import org.gradle.api.tasks.Copy
import org.gradle.api.tasks.bundling.Zip

val markdownRules = Action<CopySpec> {
    include("**/*.md")
    exclude("**/draft/**")
}

tasks.register<Copy>("copyHandbook") {
    from("handbook", markdownRules)
    into(layout.buildDirectory.dir("handbook-output"))
}

tasks.register<Zip>("zipExamples") {
    from("examples", markdownRules)
    archiveFileName.set("examples.zip")
    destinationDirectory.set(layout.buildDirectory.dir("archives"))
}
~~~

Ở đây:

- `copyHandbook` lấy nguồn `handbook`, còn `zipExamples` lấy nguồn `examples`.
- Cả hai đều chỉ chọn Markdown và loại thư mục `draft` theo rule được chia sẻ.
- `Action<CopySpec>` là một hàm cấu hình được tái sử dụng, không phải task, không chứa danh sách nguồn cố định.
- Lời gọi `from("handbook", markdownRules)` áp dụng action vào **child spec** của riêng source `handbook`, giúp tránh làm thay đổi các nguồn không liên quan của task.

Nếu tách rules-only thành một `copySpec` nhưng không khai báo `from`, bạn sẽ có một spec không sở hữu source. Thay vì gắn spec trống về nguồn vào các task rồi cố hiểu hành vi, dùng `Action<CopySpec>` như trên khi chỉ muốn chia sẻ logic cấu hình.

## 6. Ví dụ Groovy DSL tương đương

Nếu dự án dùng `build.gradle` thay vì `build.gradle.kts`, có thể áp dụng cùng ý tưởng.

**File `build.gradle`:**

~~~groovy
def docsLayout = copySpec {
    from('docs/common') {
        include '**/*.md'
        into 'manual/common'
    }
    from('docs/local') {
        include '**/*.md'
        into 'manual/local'
    }
}

tasks.register('stageDocs', Copy) {
    into layout.buildDirectory.dir('staged-docs')
    with docsLayout
}

tasks.register('bundleDocs', Zip) {
    archiveFileName = 'docs.zip'
    destinationDirectory = layout.buildDirectory.dir('archives')
    with docsLayout
}
~~~

**Lưu ý:** đây là ví dụ độc lập theo **Groovy DSL**, không trộn chung với file Kotlin DSL của mục 3. Groovy thường cho phép bỏ dấu ngoặc khi gọi hàm và dùng nháy đơn; Kotlin DSL yêu cầu cú pháp Kotlin với generic type và dấu ngoặc tương ứng.

Để tái sử dụng chỉ quy tắc mà không cố định source trong Groovy, dùng closure cấu hình truyền vào `from`:

~~~groovy
def markdownRules = {
    include '**/*.md'
    exclude '**/draft/**'
}

tasks.register('copyHandbook', Copy) {
    from 'handbook', markdownRules
    into layout.buildDirectory.dir('handbook-output')
}
~~~

Cơ chế chia sẻ rules của hai DSL tương tự nhau, nhưng Groovy dùng closure còn Kotlin dùng `Action<CopySpec>`/lambda có kiểu. Khi copy ví dụ từ tài liệu Gradle, chọn đúng tab Groovy/Kotlin tương ứng với đuôi file build script đang sử dụng.

## 7. Đổi tên, lọc nội dung, xung đột file và khả năng lặp lại

`CopySpec` không chỉ quản lý bố cục directory; nó còn hỗ trợ một số phép biến đổi.

### 7.1. Rename: thống nhất tên file trong mọi output

Ví dụ file nguồn có hậu tố `-staging` cần được bỏ khi copy:

~~~kotlin
import org.gradle.api.file.CopySpec

val webSpec: CopySpec = copySpec {
    from("web")
    include("**/*.html")
    rename("(.+)-staging(.+)", "$1$2")
}
~~~

Ví dụ `web/index-staging.html` có thể thành `index.html` trong output. Biểu thức `rename(pattern, replacement)` đổi **tên file** theo pattern; hãy kiểm tra tình huống mà hai tên khác nhau sau đổi lại trùng một tên đích.

Khi dùng regex replacement của Gradle, viết pattern theo cú pháp Kotlin DSL cho chuỗi, không lẫn biểu thức nội suy string của build script. Có thể dùng callback/transformer để áp dụng quy tắc phức tạp nếu cần.

### 7.2. include/exclude và pattern Ant-style

Một số mẫu phổ biến:

| Mẫu | Ý nghĩa thường gặp |
| --- | --- |
| `**/*.md` | File Markdown ở các cấp thư mục |
| `**/*.html` | File HTML |
| `**/*.tmp` | File tạm có đuôi `.tmp` |
| `**/draft/**` | Nội dung nằm dưới thư mục tên `draft` trong cấu trúc liên quan |
| `assets/**` | Mọi nội dung trong `assets` tính từ gốc nguồn phù hợp |

Các mẫu được áp dụng trên **đường dẫn tương đối trong source tree**, không phải tên đường dẫn tuyệt đối của máy. Nếu pattern không khớp như kỳ vọng, hãy kiểm tra root `from` và số cấp thư mục. Ví dụ `from("docs/manual")` đã bỏ tiền tố `docs/manual` khỏi đường dẫn tương đối khi so pattern.

Gradle hỗ trợ các hình thức include/exclude linh hoạt hơn string pattern; chỉ dùng chúng khi thực sự cần logic phức tạp và hiểu ảnh hưởng tới tính dự đoán của build.

### 7.3. Xử lý file trùng đích với DuplicatesStrategy

Hai source có thể chứa cùng `config.json`, hoặc một quy tắc rename có thể biến hai file khác nhau thành cùng `index.html`. Nếu không quyết định trước, kết quả có thể gây nhầm lẫn hoặc phụ thuộc kiểu output.

Các chiến lược:

| Giá trị | Hành vi chính |
| --- | --- |
| `DuplicatesStrategy.FAIL` | Báo lỗi khi nhiều file định ghi vào cùng đường dẫn đích |
| `DuplicatesStrategy.EXCLUDE` | Giữ file đầu tiên, bỏ những file trùng sau |
| `DuplicatesStrategy.INCLUDE` | Không ngăn file trùng; archive có thể chứa entry trùng, filesystem có thể bị ghi đè |
| `DuplicatesStrategy.WARN` | Giống INCLUDE nhưng thêm cảnh báo |
| `DuplicatesStrategy.INHERIT` | Child dùng chính sách được kế thừa từ spec cha |

Ví dụ Kotlin DSL:

~~~kotlin
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.tasks.Copy

tasks.register<Copy>("copySafe") {
    from("assets/common")
    from("assets/extra")
    into(layout.buildDirectory.dir("assets-output"))
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

`FAIL` phù hợp với bố cục phát hành cần phát hiện xung đột sớm. `EXCLUDE` hợp lý khi quy tắc “ưu tiên file đầu tiên” có chủ đích và thứ tự nguồn được quản lý rõ. Không dựa vào thứ tự copy ngẫu nhiên để giải quyết những file cùng tên quan trọng.

### 7.4. Expand và filter: không áp dụng bừa cho binary

`CopySpec` có thể lọc/biến đổi nội dung như template substitution hoặc text filters. Nhưng nếu bạn dùng `expand(...)` hoặc `filter(...)` trên mọi file gồm PNG, PDF hay JAR, nội dung binary có thể bị biến đổi sai. Hãy giới hạn phạm vi ở child spec chỉ bao gồm file text thích hợp.

Không truyền password/API key qua `expand` rồi đóng gói vào ZIP hoặc lưu vào Build Cache nếu output được phát hành/chia sẻ. Secret phải được cấp khi chạy ứng dụng hoặc qua cơ chế bảo mật tương ứng; không dùng copy templating để đưa bí mật vào artifact công khai.

## 8. So sánh Copy, Sync và Zip khi áp dụng cùng CopySpec

Cùng `docsLayout`, nhưng task có semantics khác nhau:

| Task | Kết quả | Khi dùng | Lưu ý |
| --- | --- | --- | --- |
| `Copy` | Chép file vào thư mục | Staging, copy resource, tập hợp tài liệu | Không tự xóa mọi file lạ còn trong thư mục đích |
| `Sync` | Làm thư mục đích khớp với tập file được spec chọn | Đồng bộ vùng staging riêng của task | Có thể **xóa file đích thừa**, nguy hiểm nếu đích chứa dữ liệu người dùng |
| `Zip` | Tạo file archive ZIP với entries theo spec | Đóng gói để phân phối | Cần quản lý duplicates, đường dẫn entry và archive metadata |
| `Tar` | Tạo archive TAR với entries theo spec | Đóng gói hệ thống có yêu cầu TAR | Kiểm tra compression/format và hành vi archive của task |

Ví dụ thay `Copy` bằng `Sync` khi bạn **muốn loại file cũ** trong staging:

~~~kotlin
import org.gradle.api.file.CopySpec
import org.gradle.api.tasks.Sync

val docsSpec: CopySpec = copySpec {
    from("docs") {
        include("**/*.md")
    }
}

tasks.register<Sync>("syncDocs") {
    with(docsSpec)
    into(layout.buildDirectory.dir("docs-sync"))
}
~~~

**Cảnh báo bắt buộc:** `Sync` có thể loại những file trong `build/docs-sync` không thuộc tập nguồn hiện tại. Chỉ dùng với thư mục đích mà task **sở hữu hoàn toàn**. Không sử dụng `Sync` để cập nhật thư mục chứa tài liệu người dùng hoặc bản sao dữ liệu quan trọng chưa backup.

`Zip` cũng sử dụng `CopySpec` nhưng root destination chính là archive được xác định qua `destinationDirectory` và `archiveFileName`; child `into` quyết định **đường dẫn bên trong ZIP**, không tạo một directory output độc lập trên filesystem.

## 9. CopySpec trong dự án Java: resource, distributions và generated files

`CopySpec` có ích vượt xa ví dụ tài liệu:

- Đưa static files vào staging cho một web app.
- Đóng gói file cấu hình mặc định, script và documentation vào distribution archive.
- Chọn nhóm resource cho `processResources` với quy tắc include/exclude rõ.
- Sao chép artifact do các task khác tạo ra, khi dependency và output đã được khai báo đúng.
- Thống nhất file layout giữa bản directory exploded và bản ZIP/TAR phát hành.

### 9.1. Không nhầm source layout với output layout

Ví dụ một Java project có:

~~~text
src/main/resources/
├── config/defaults.properties
└── public/index.html
~~~

Plugin Java thường đã quản lý việc xử lý resources theo `sourceSets` và task `processResources`. Nếu chỉ cần loại một nhóm file resources, trước tiên nên cấu hình task/plugin hiện có thay vì tạo một Custom Copy task rồi tự nối vào classpath.

Ví dụ **snippet** để cấu hình task `processResources` đã có sau khi áp dụng Java plugin:

~~~kotlin
import org.gradle.language.jvm.tasks.ProcessResources

plugins {
    java
}

tasks.named<ProcessResources>("processResources") {
    exclude("**/*.bak")
}
~~~

Đoạn này chỉ minh họa một phép lọc trên task loại `ProcessResources`; việc Gradle tự đưa resources vào output/classes là trách nhiệm của Java plugin. Cần cân nhắc liệu việc loại `*.bak` có làm thay đổi nội dung bắt buộc của ứng dụng không.

### 9.2. Khi source là output của task khác

Nếu nguồn file được task generate ra trong build directory, không nên mặc định đường dẫn một cách vô danh:

~~~kotlin
// Minh hoa, gia su "generateDocs" la TaskProvider<SomeTask>
// va SomeTask co property outputDirectory: DirectoryProperty.
tasks.register<Copy>("stageGeneratedDocs") {
    from(generateDocs.flatMap { it.outputDirectory })
    into(layout.buildDirectory.dir("generated-docs-stage"))
}
~~~

Đây là **snippet cần task generateDocs có thật**, không phải script độc lập. Lợi ích của provider là liên kết tới output có thể giúp Gradle suy ra dependency thích hợp và tránh yêu cầu Gradle đọc file chưa được tạo ở pha cấu hình.

Tương tự, khi cần đưa output của task vào một `CopySpec` dùng chung, có thể cấu hình `from(providerOutput)` nếu API cung cấp output provider phù hợp. Không chạy `tasks.getByName` hoặc `provider.get()` sớm chỉ để lấy đường dẫn. Với provider và task dependencies phức tạp, kiểm tra actual graph và up-to-date behavior.

## 10. Vì sao nên dùng Task<Copy> thay vì tự gọi Project.copy trong doLast?

Gradle có API `Project.copy { ... }` để thực hiện thao tác copy từ logic của project, nhưng việc gọi nó bên trong một `doLast` tùy ý có nhiều hạn chế:

~~~kotlin
tasks.register("copyImperative") {
    doLast {
        // Minh hoa cach KHONG Uu tien cho build logic moi:
        copy {
            from("docs")
            into(layout.buildDirectory.dir("copy-output"))
        }
    }
}
~~~

Đoạn minh họa trên **không phải mẫu khuyên dùng**: nó thường không cho Gradle biết input/output của task bọc bên ngoài để thực hiện up-to-date checks; dependency với task tạo source cũng không tự được suy ra đúng trong mọi trường hợp. Việc truy cập `Project.copy` ở giai đoạn action còn không tương thích với Configuration Cache.

Nên viết:

~~~kotlin
import org.gradle.api.tasks.Copy

tasks.register<Copy>("copyDeclarative") {
    from("docs")
    into(layout.buildDirectory.dir("copy-output"))
}
~~~

Với nhu cầu tái sử dụng quy tắc, dùng `copySpec` rồi `with` như mục 3. Task `Copy` có API và cơ chế tracking đầu vào/đầu ra được tích hợp, phù hợp hơn với mô hình Gradle.

Nếu **custom task type** thật sự cần copy file như một phần của thuật toán phức tạp, nên tìm hiểu `FileSystemOperations.copy` được inject vào task thay vì truy cập `Project.copy` trong execution. Task custom vẫn phải khai báo inputs/outputs và hợp đồng cache riêng. Đừng tạo một task imperative chỉ để gọi lại chức năng mà task type có sẵn đã cung cấp.

## 11. Vòng đời build và cách CopySpec tương tác với Gradle

Ở pha configuration, Gradle đánh giá các build scripts và đăng ký/cấu hình tasks, CopySpecs. Tại đây:

- `val docsLayout = copySpec { ... }` tạo bản mô tả việc lấy/chọn/sắp xếp file.
- `tasks.register<Copy>("stageDocs") { ... }` đăng ký một task, thường chưa cần realize ngay.
- `with(docsLayout)` gắn spec vào cấu hình của task khi task được realize.
- Các lời gọi `from`, `into`, `include`, `exclude` và `rename` mô tả hoạt động, **không tự copy file ngay tại dòng cấu hình**.

Khi task được chọn chạy, Gradle đánh giá nguồn theo mô hình hiện tại, quyết định task có cần thực thi hay không, rồi thực hiện copy/archive:

~~~text
Configuration
    |
    v
CopySpec: from + includes + child into + rename
    |
    v
Copy / Sync / Zip task configured
    |
    v
Task execution (if needed)
    |
    +--> Chọn file đầu vào
    +--> Xây dựng đường dẫn tương đối tại đích
    +--> Kiểm tra duplicates, áp dụng rules
    +--> Ghi output directory / archive
~~~

Task có thể được đánh dấu `UP-TO-DATE` khi inputs/outputs không đổi và đủ điều kiện; `Zip` cũng có thể tái sử dụng output qua cache theo cấu hình phù hợp. CopySpec giúp **không lặp logic**, không đồng nghĩa nó tự bật remote Build Cache hay bảo đảm cache hit.

Với Configuration Cache, tránh để callback biến đổi file hoặc action capture đối tượng Project/script không phù hợp khi execution. Sử dụng task types có sẵn, provider và DSL đúng là bước khởi đầu tốt; vẫn phải kiểm tra build/plugin thật theo tài liệu phiên bản Gradle đang dùng.

## 12. Lỗi thường gặp khi tái sử dụng CopySpec

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `copySpec { ... }` đã khai báo nhưng không có output | CopySpec chỉ là đặc tả; chưa gắn vào task | Tạo task `Copy`/`Zip` và dùng `with(spec)` |
| Task copy ra đúng file nhưng thiếu thư mục `manual` | Chưa khai báo child `into("manual")` | Thêm child `into` phù hợp |
| Output bị lồng thư mục lặp như `manual/manual/...` | Cả parent và child cùng đặt tiền tố | Đọc cây `into` ở từng tầng, chỉ đặt đường dẫn tương đối cần thiết |
| Quy tắc `include("**/*.md")` làm mất PNG ở nhánh khác | Đặt include ở parent quá rộng | Đưa include xuống `from` tương ứng |
| File trùng tên âm thầm ghi đè hoặc archive có duplicates | Nhiều nguồn/rename về một đích | Đặt `DuplicatesStrategy.FAIL`, rà lại rules |
| ZIP có cấu trúc khác staging | Mỗi task có rules riêng hoặc thêm `into` khác nhau | Dùng một shared `CopySpec` và phân biệt root destination |
| Hai task cùng ghi vào một thư mục output | Không phân định ownership | Dùng mỗi task một output riêng hoặc pipeline rõ |
| Tệp được sinh ra chưa tồn tại khi copy | Source phụ thuộc task generate nhưng dependency không khai báo | Dùng provider từ output task nguồn hoặc dependency đúng |
| `Sync` xóa file người dùng ngoài ý muốn | Destination không dành riêng cho Sync | Dùng `Copy` hoặc staging directory riêng |
| Tập nguồn trống nhưng task báo thành công | `from` trỏ sai thư mục hoặc patterns loại hết file | Kiểm tra project root, relative path, include/exclude và inputs |
| Rename tạo đuôi sai hoặc tên trùng | Regex/replacement hoặc callback không đúng | Thử trên vài filename, áp dụng `FAIL` để bắt xung đột |
| Build script Kotlin lỗi `Unresolved reference: CopySpec` | Thiếu import hoặc dùng Groovy syntax | Import `org.gradle.api.file.CopySpec` và dùng đúng Kotlin DSL |
| `Project.copy` trong `doLast` gây Configuration Cache violation | Gọi API project lúc execution | Chuyển sang task `Copy` hoặc custom task với `FileSystemOperations` |
| Dùng `expand` trên ảnh/JAR khiến file hỏng | Filter text áp dụng cả file binary | Giới hạn filter trong child spec chỉ chọn text |
| `with(spec)` xuất hiện nhiều lần và output trùng | Gắn cùng spec hoặc nguồn giao nhau nhiều lần | Tìm các lần `with` và `from`; loại trùng và chọn policy phù hợp |

## 13. Quy trình gỡ lỗi một bố cục file không đúng

1. **Xác định root output:** đối với `Copy`/`Sync` là task root `into(...)`; đối với `Zip` là archive destination/name, còn đường dẫn entry đến từ specs.
2. **Đọc cây nguồn:** ghi lại từng `from(...)` và root của file tree.
3. **Đọc child `into` từ ngoài vào trong:** cộng các thư mục tương đối theo nhánh; tránh tính cả tên source directory nếu Gradle đang copy contents.
4. **Áp dụng filter theo phạm vi:** kiểm tra quy tắc `include`/`exclude` từ parent đến child; nhớ `exclude` trên parent được kế thừa.
5. **Kiểm tra rename và duplicates:** mỗi file cuối cùng có tên và đích gì? Dùng `DuplicatesStrategy.FAIL` khi cần phát hiện trùng sớm.
6. **Đối chiếu output riêng của từng task:** file trong `build/staged-docs` khác với đường dẫn entries trong `docs.zip` nhưng layout tương đối nên giống.
7. **Chạy task với log phù hợp:** có thể dùng `--info` để hiểu tình trạng task, nhưng xem trước log có nhạy cảm không; đọc kết quả output thật thay vì suy từ stdout.

Các lệnh hữu ích trong demo mục 3:

~~~bash
./gradlew stageDocs --info --console=plain
./gradlew bundleDocs --info --console=plain
./gradlew stageDocs bundleDocs --rerun-tasks --console=plain
~~~

`--rerun-tasks` yêu cầu Gradle bỏ qua kiểm tra up-to-date thông thường để chạy lại tasks nếu hợp lệ; nó không sửa đường dẫn hoặc file trùng tự động. Trạng thái `UP-TO-DATE` không phải lỗi. Nếu task không có source, hãy kiểm tra xem file nguồn và include patterns có khớp không.

Trong dự án lớn, nếu thấy rules lặp ở nhiều module, trích thành shared CopySpec/Action hoặc cấu hình trong convention plugin để tránh mỗi module sửa một kiểu. Cần chú ý đường dẫn relative và phạm vi Project khi chia sẻ giữa các subprojects.

## 14. Bài tập tình huống và đáp án

**Bài 1 — Một source, hai output.** Bạn cần copy `docs` thành thư mục `build/preview` và ZIP `build/archives/docs.zip` với cùng quy tắc lọc và phân cấp. Nên trùng lặp hai đoạn `from`/`include`/`into` không?  
**Đáp án:** tạo `copySpec` có source, filters và layout tương đối; gắn vào cả `Copy` lẫn `Zip` bằng `with(spec)`; đặt root destination riêng.

**Bài 2 — Hai source, một quy tắc.** `handbook` và `examples` đều chỉ lấy file `.md`, nhưng không nên trộn thư mục nguồn. Chọn `copySpec` hay `Action<CopySpec>`?  
**Đáp án:** chia sẻ `Action<CopySpec>` chứa `include/exclude`, rồi truyền action vào `from("handbook", rules)` và `from("examples", rules)`.

**Bài 3 — Đường dẫn child.** Với `into("build/site")` ở task gốc và `from("scripts") { into("js") }`, file `scripts/main.js` sẽ nằm ở đâu?  
**Đáp án:** trong `build/site/js/main.js` (giả sử root path resolve như mô tả), không phải `build/site/scripts/js/main.js`.

**Bài 4 — Filter đặt sai tầng.** Root spec có `include("**/*.md")` và một child lấy `images/*.png`. Vì sao ảnh biến mất?  
**Đáp án:** include ở parent ảnh hưởng child; đặt bộ lọc Markdown ở riêng child docs thay vì toàn bộ spec.

**Bài 5 — Xử lý file trùng.** `src/one/config.json` và `src/two/config.json` cùng được đưa vào root archive. Muốn build fail khi trùng, dùng gì?  
**Đáp án:** đặt `duplicatesStrategy = DuplicatesStrategy.FAIL`.

**Bài 6 — Sync hay Copy?** Bạn cần bảo toàn các file do người dùng đặt thêm vào thư mục đích, chỉ chép thêm file mới. `Sync` có phù hợp không?  
**Đáp án:** không nên; `Sync` có thể xóa file đích không có trong nguồn. `Copy` phù hợp hơn.

**Bài 7 — Rename.** Quy tắc `rename("(.+)-staging(.+)", "$1$2")` biến `index-staging.html` thành gì?  
**Đáp án:** `index.html`, theo nhóm capture trong regex.

**Bài 8 — Một spec nhưng không task.** Chỉ khai báo `val x = copySpec { ... }` rồi chạy `./gradlew help`. File có được chép không?  
**Đáp án:** không. CopySpec chỉ là cấu hình; phải có task sử dụng spec và task đó thực thi.

**Bài 9 — Source do task khác sinh ra.** Vì sao nên truyền `TaskProvider`/output provider vào `from` thay vì hardcode file trong `build/`?  
**Đáp án:** provider giúp mô hình hóa quan hệ với task nguồn, tránh đọc file quá sớm và giảm nguy cơ dùng output cũ/thiếu.

**Bài 10 — Bố cục staging/ZIP khác nhau.** Cả hai dùng chung spec nhưng task ZIP thêm `into("docs")` ở cấp khác. Nên làm gì?  
**Đáp án:** kiểm tra đường dẫn ở từng tầng; để layout tương đối được quản lý nhất quán trong shared CopySpec, tránh thêm tiền tố khác không chủ ý.

**Bài 11 — Một bản sao bị lẫn file tmp.** Spec con chỉ khai báo `include("**/*.md")`, spec cha `exclude("**/*.tmp")`. File `notes.tmp` có được chép không?  
**Đáp án:** không, vì không khớp include và cũng thuộc exclude kế thừa.

**Bài 12 — Imperative copy.** Một task thường gọi `copy { ... }` trong `doLast` mà không khai báo inputs/outputs. Điều gì kém hơn `Copy`?  
**Đáp án:** Gradle khó theo dõi incremental/up-to-date và task dependency; `Project.copy` trong action còn gây vấn đề với Configuration Cache. Dùng `Copy` task khi công việc chỉ là sao chép.

## 15. Checklist khi thiết kế CopySpec dùng chung

- [ ] Đã phân biệt **source**, **layout tương đối**, **root output** chưa?
- [ ] Nhiều task dùng cùng source hay chỉ trùng rules? Chọn `copySpec` hoặc `Action<CopySpec>` phù hợp.
- [ ] `copySpec` có nguồn `from` thực sự hay đang là rules-only?
- [ ] Các child `into("...")` là đường dẫn tương đối đúng, không lặp tiền tố?
- [ ] Include/exclude có được đặt ở đúng cấp để không vô tình loại file của nhánh khác?
- [ ] Có quy tắc `rename`/`filter` không, và nó chỉ áp dụng file text/filename phù hợp?
- [ ] Đã quyết định `DuplicatesStrategy` nếu nhiều file có thể cùng đích?
- [ ] Các task khác nhau có output ownership riêng, không tranh ghi cùng thư mục?
- [ ] Nếu dùng `Sync`, destination có phải thư mục staging riêng và có thể xóa file thừa an toàn?
- [ ] Nếu lấy source từ task khác, đã sử dụng output provider/dependency hợp lý?
- [ ] Có tránh gọi `Project.copy` trong action chỉ để thay task `Copy`?
- [ ] Có kiểm tra output filesystem và archive entries thực tế thay vì chỉ tin task stdout?
- [ ] Có xem lại plugin/Gradle version và Configuration Cache khi đưa vào build lớn?

## 16. Tài liệu chính thức

- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): trọng tâm về `CopySpec`, shared specs, child specs, rename, filter, Sync và Copy.
- [Gradle API — CopySpec](https://docs.gradle.org/current/javadoc/org/gradle/api/file/CopySpec.html): các phương thức `from`, `into`, `include`, `exclude`, `with` và các thuộc tính.
- [Gradle API — DuplicatesStrategy](https://docs.gradle.org/current/javadoc/org/gradle/api/file/DuplicatesStrategy.html): chính sách xử lý file trùng đích.
- [Gradle — Copy Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.Copy.html): cách cấu hình task sao chép file.
- [Gradle — Sync Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.Sync.html): tác dụng đồng bộ và xóa file đích thừa.
- [Gradle — Zip Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.Zip.html): tạo archive và cấu hình file entries.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named` và lazy task configuration.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): ranh giới configuration/execution và API hợp lệ trong task action.

**Ghi nhớ:** `CopySpec` tách **quy tắc bố trí và xử lý tệp** khỏi **task sử dụng**. Dùng `copySpec { from(...) { ... } }` + `with(spec)` khi nguồn và layout dùng chung; dùng `Action<CopySpec>` khi chỉ muốn tái sử dụng bộ lọc/quy tắc trên các nguồn độc lập. Giữ một root destination cho mỗi tác vụ copy, sử dụng child `into` để tạo cấu trúc tương đối, và quản lý duplicates/output ownership rõ ràng.