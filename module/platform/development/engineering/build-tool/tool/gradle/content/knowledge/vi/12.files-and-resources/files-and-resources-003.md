# Chọn tệp bằng include, exclude và pattern trong Gradle

## 1. Bài học giải quyết vấn đề gì?

Trong một dự án Java/Gradle, thư mục nguồn thường không chỉ chứa những file bạn muốn biên dịch, sao chép hoặc đóng gói. Nó có thể chứa cả tài liệu, file nháp, bản sao lưu, cấu hình theo môi trường, hình ảnh và những file chỉ phục vụ máy lập trình viên. Gradle cung cấp cơ chế **lọc tập tin** bằng `include`, `exclude` và các **Ant-style patterns** (mẫu đường dẫn kiểu Ant), thường được dùng với `Copy`, `Sync`, `FileTree`, `ProcessResources`, `Jar` và một số task khác.

Ví dụ, nếu có:

~~~text
assets/
├── config/
│   ├── app.json
│   └── test-debug.json
├── docs/
│   ├── guide.md
│   └── draft/
│       └── notes.md
├── images/
│   ├── logo.svg
│   └── old/
│       └── old-logo.svg
├── notes.txt
└── tmp/
    └── cache.tmp
~~~

Và yêu cầu: “Sao chép `.md`, `.svg`, `.json`, nhưng bỏ các thư mục `draft`, `old` và các tệp `test-*.json`”, bạn có thể khai báo:

~~~kotlin
tasks.register<Copy>("copySelectedAssets") {
    from("assets") {
        include("**/*.md", "**/*.svg", "**/*.json")
        exclude("**/draft/**", "**/old/**", "**/test-*.json")
    }
    into(layout.buildDirectory.dir("selected-assets"))
    includeEmptyDirs = false
}
~~~

Lệnh `gradle copySelectedAssets` sẽ sao chép **ba file phù hợp** sang `build/selected-assets`, giữ cấu trúc tương đối:

~~~text
build/selected-assets/
├── config/app.json
├── docs/guide.md
└── images/logo.svg
~~~

Đây là **lọc file tại thời điểm chọn nguồn**; nó không chỉnh sửa file gốc. Không nên nhầm với việc **lọc nội dung bên trong file** bằng `filter(...)`, với `exclude` trong dependency resolution, hay với các quy tắc bỏ qua file của Git.

Mục tiêu bài học: hiểu chính xác các mẫu `*`, `?`, `**`, biết file được xét tương đối từ đâu, sử dụng `include`/`exclude` ở đúng phạm vi, viết Gradle Groovy/Kotlin DSL chạy được, và kiểm tra kết quả thay vì đoán.

## 2. Những API nào hỗ trợ chọn file?

### 2.1. CopySpec — khai báo sao chép

Khi dùng `Copy` hoặc `Sync`, Gradle xây dựng một **CopySpec** gồm nguồn `from(...)`, đích `into(...)` và các bộ lọc. Nhiều API này kế thừa `PatternFilterable`, nơi định nghĩa `include(...)` và `exclude(...)`.

~~~kotlin
tasks.register<Copy>("copyDocuments") {
    from("documents")
    include("**/*.md")
    exclude("**/draft/**")
    into(layout.buildDirectory.dir("documents"))
}
~~~

Trong ví dụ, mọi pattern được áp dụng lên các đường dẫn **bên dưới nguồn `documents`**. Kết quả được chép xuống build directory tương đối với gốc nguồn, trừ khi bạn cấu hình đổi đường dẫn đích.

### 2.2. FileTree — tập file có cấu trúc thư mục

`fileTree(...)` tạo một **FileTree** từ một thư mục và hỗ trợ lọc:

~~~kotlin
val markdownFiles = fileTree("documents") {
    include("**/*.md")
    exclude("**/draft/**")
}
~~~

`markdownFiles` không phải một `List<String>` hay một chuỗi đường dẫn đơn. Nó là một file tree, có thể truyền vào `from(markdownFiles)` hoặc làm nguồn của những task khác. Mẫu lựa chọn sẽ được áp dụng khi Gradle xử lý file tree.

### 2.3. Resources, source sets và archive task

Java plugin có source set như `main`, `test`, các task `processResources` và `jar`. Bạn có thể chọn tài nguyên cần sao chép vào classpath hoặc nội dung cần đóng gói.

Các task như `ProcessResources` và `Jar` dùng nguyên lý chọn file tương tự nhưng **không đồng nghĩa cùng phạm vi**. Lọc ở `sourceSets.main.resources` ảnh hưởng tới tập resource nguồn; lọc ở `processResources` ảnh hưởng tới copy task xử lý resource; lọc ở `jar` tác động lên nội dung được xét cho JAR. Chọn tầng đúng theo mục đích và đừng giả định lọc tại một nơi là thay đổi vĩnh viễn file gốc.

## 3. Quy tắc include/exclude — phần phải nhớ

Gradle dùng logic tương đương:

> File được chọn khi nó khớp **ít nhất một include** (nếu có include), và **không khớp bất kỳ exclude nào**.

Cụ thể:

1. **Không khai báo `include`:** Mặc định chọn mọi file trong phạm vi nguồn phù hợp, trừ các loại trừ khác áp dụng (bao gồm những default excludes của cơ chế file tree nếu có).
2. **Có một hay nhiều `include`:** Chỉ file khớp **ít nhất một** include pattern/spec mới là ứng viên. Nhiều include có quan hệ **OR**, không phải AND.
3. **Có một hay nhiều `exclude`:** File khớp **bất kỳ** exclude pattern/spec đều bị loại. Nhiều exclude cũng theo logic **OR** giữa các điều kiện loại trừ.
4. **Vừa khớp include vừa khớp exclude:** **Exclude thắng**. Thứ tự viết `include` trước hay sau `exclude` không phải quy tắc “lệnh cuối thắng”.

Ví dụ:

~~~kotlin
from("assets") {
    include("**/*.json", "**/*.md")
    exclude("**/draft/**", "**/test-*.json")
}
~~~

- `config/app.json`: khớp include `**/*.json` và không khớp exclude → được chọn.
- `config/test-debug.json`: khớp include, nhưng cũng khớp `**/test-*.json` → **bị loại**.
- `docs/guide.md`: khớp `**/*.md` và không bị exclude → được chọn.
- `docs/draft/notes.md`: khớp include nhưng bị `**/draft/**` loại.
- `images/logo.svg`: không khớp include nào → không được chọn.

**Cách đọc như logic Boolean:**

~~~text
selected(file) =
    (no explicit include OR matchesAnyInclude(file))
    AND
    NOT matchesAnyExclude(file)
~~~

Cần nhớ thêm: cơ chế duyệt file tree có thể áp dụng **default excludes** cho một số loại file (ví dụ các tệp hệ thống kiểm soát phiên bản theo danh sách mặc định của Ant). Vì vậy “không khai báo include/exclude” không nên được hiểu là bảo đảm mọi file ẩn và mọi file metadata đều xuất hiện trong mọi API/ngữ cảnh.

## 4. Ant-style pattern: *, ?, ** có nghĩa gì?

Các chuỗi truyền cho `include("...")`, `exclude("...")` không phải biểu thức chính quy Java (`java.util.regex`). Chúng là **Ant-style path patterns**.

| Ký hiệu | Ý nghĩa | Ví dụ điển hình |
| --- | --- | --- |
| `*` | Khớp 0 hoặc nhiều ký tự **trong một phần đường dẫn**; không băng qua dấu phân cách thư mục | `*.json` trong một thư mục, `test-*.json` |
| `?` | Khớp đúng một ký tự **trong một phần đường dẫn** | `data?.csv` khớp `data1.csv` |
| `**` | Khớp nhiều cấp thư mục/đường dẫn, kể cả không cấp nào, theo cú pháp Ant | `**/*.md`, `**/private/**` |
| `/` | Ngăn cách các thành phần đường dẫn trong pattern | `config/*.json` |
| Đường dẫn thư mục kết thúc `/` | Trong mẫu Ant, hậu tố `**` được suy ra | `docs/` tương đương ý định chọn cả cây dưới docs |

**Khác biệt thường gây lỗi:**

- `*.properties`: thường xét tệp `.properties` trực tiếp tại gốc phạm vi matching.
- `**/*.properties`: xét `.properties` cả ở gốc **và** các thư mục con.
- `config/*.json`: chỉ những JSON ở ngay dưới `config`, không tự phủ `config/nested/file.json`.
- `config/**/*.json`: bao gồm JSON dưới `config` ở cả cấp trực tiếp và cấp lồng.
- `**/private/**`: loại các đường dẫn nằm dưới thư mục tên `private` ở bất kỳ độ sâu nào.
- `**/*.tmp`: loại các file đuôi `.tmp` ở mọi cấp, nhưng **không** loại file `.tmp.bak` chỉ vì nó có chuỗi `.tmp` trong tên.
- `report-?.txt` khớp `report-1.txt` nhưng không khớp `report-12.txt`.

Không thay `**/*.md` bằng `.*\.md$` rồi mong Gradle hiểu như regex. Nếu thật sự cần điều kiện phức tạp dựa trên tên/kích thước/nội dung, sử dụng `include(Spec<FileTreeElement>)`/`exclude(Spec<FileTreeElement>)` hoặc API lọc phù hợp (mục 11).

### 4.1. Dấu phân cách và tính phân biệt chữ hoa/thường

Trong pattern Ant của Gradle, nên dùng dấu `/` cho thư mục **kể cả trên Windows** để script nhất quán. API cũng hỗ trợ dấu `\` làm separator trong pattern; nhưng trong chuỗi Kotlin/Groovy, ký tự backslash lại liên quan escape của ngôn ngữ, nên dùng `/` đơn giản hơn.

Ở `Copy`/`CopySpec`, property `caseSensitive` mặc định là `true`. Ví dụ file `README.MD` có thể không khớp `**/*.md` nếu phân biệt chữ hoa. Khi thực sự cần không phân biệt hoa/thường, có thể cấu hình Kotlin DSL:

~~~kotlin
tasks.register<Copy>("copyMarkdownAnyCase") {
    from("documents")
    include("**/*.md")
    isCaseSensitive = false
    into(layout.buildDirectory.dir("markdown-any-case"))
}
~~~

Đoạn này là ví dụ chọn file cho Copy task: muốn thử thì tạo thư mục `documents` và các file `.md`/`.MD`. Mặc định nên đặt extension nhất quán để tránh kết quả khác nhau do case matching hoặc hệ thống file.

## 5. Pattern được tính tương đối từ đâu?

Đây là lỗi xuất hiện thường xuyên nhất: đặt đúng pattern nhưng **sai gốc để match**.

Xét:

~~~text
my-project/
├── build.gradle.kts
└── input/
    ├── config/
    │   └── app.json
    └── docs/
        └── guide.md
~~~

Ví dụ đúng:

~~~kotlin
tasks.register<Copy>("copyJson") {
    from("input")
    include("config/*.json")
    into(layout.buildDirectory.dir("json-output"))
}
~~~

Gradle lấy `input` làm gốc nguồn, nên file có **relative path** `config/app.json`. Pattern `config/*.json` khớp.

Ví dụ sai về mục đích:

~~~kotlin
tasks.register<Copy>("copyJsonWrong") {
    from("input")
    include("input/config/*.json")
    into(layout.buildDirectory.dir("json-wrong"))
}
~~~

Khi `from("input")` đã xác định gốc, relative path **không** còn tiền tố `input/`. Vì vậy `input/config/*.json` không khớp `config/app.json`; trong điều kiện nguồn trên, task không sao chép file JSON mong muốn.

**Đổi gốc nguồn thì pattern phải đổi tương ứng:**

~~~kotlin
tasks.register<Copy>("copyJsonFromRoot") {
    from(layout.projectDirectory)
    include("input/config/*.json")
    into(layout.buildDirectory.dir("json-from-root"))
}
~~~

Lúc này nguồn là toàn project directory và pattern phải có tiền tố `input/`. Tuy nhiên, quét cả project có thể vô tình xét thêm file không liên quan; hãy ưu tiên gốc nguồn hẹp nhất đáp ứng yêu cầu.

### 5.1. Nguồn thư mục không mặc định tự xuất hiện ở đích

~~~kotlin
tasks.register<Copy>("copyDocs") {
    from("input/docs")
    into(layout.buildDirectory.dir("output"))
}
~~~

File `input/docs/guide.md` được đặt thành `build/output/guide.md`, **không phải** `build/output/docs/guide.md`, vì `docs` là một phần của đường dẫn nguồn `from`. Nếu muốn giữ thư mục `docs` trong đích:

~~~kotlin
tasks.register<Copy>("copyDocsWithFolder") {
    from("input") {
        include("docs/**")
    }
    into(layout.buildDirectory.dir("output-with-docs"))
}
~~~

Khi đó đường dẫn tương đối `docs/guide.md` được giữ trong `build/output-with-docs/docs/guide.md`.

### 5.2. Phân biệt đường dẫn tương đối của Gradle và cwd

`file("input")`, `from("input")` trong project script được giải quyết tương đối với **project directory**, không nhất thiết là thư mục shell hiện tại. Tránh tự dùng `new File("input")` hoặc `File("input")` ở nơi Gradle không quản lý đường dẫn nếu code phụ thuộc cwd. Trong build logic hiện đại, ưu tiên `layout.projectDirectory.dir("input")` và `layout.buildDirectory.dir("...")`.

## 6. Chọn file trong Copy task — Kotlin DSL và Groovy DSL

### 6.1. Kotlin DSL

~~~kotlin
tasks.register<Copy>("copyConfigs") {
    from("src/config") {
        include("**/*.properties", "**/*.yaml")
        exclude("**/local/**", "**/*.bak")
    }
    into(layout.buildDirectory.dir("filtered-config"))
    includeEmptyDirs = false
}
~~~

Đây là đoạn cấu hình task, không tạo các file nguồn. Nếu `src/config` tồn tại, chỉ property/YAML phù hợp được sao chép, bỏ mọi file trong các thư mục `local` và các bản sao lưu `.bak`. Tên file và độ sâu được giữ tương đối với `src/config`.

### 6.2. Groovy DSL tương đương

~~~groovy
tasks.register('copyConfigs', Copy) {
    from('src/config') {
        include '**/*.properties', '**/*.yaml'
        exclude '**/local/**', '**/*.bak'
    }
    into layout.buildDirectory.dir('filtered-config')
    includeEmptyDirs = false
}
~~~

Ý nghĩa giống Kotlin DSL. Khác biệt chủ yếu là cú pháp Groovy cho chuỗi và gọi phương thức. Không sao chép `include '**/*.properties'` vào `build.gradle.kts`: Kotlin DSL cần `include("**/*.properties")`.

### 6.3. Nhiều include/exclude gọi riêng vẫn là cộng dồn

~~~kotlin
tasks.register<Copy>("copyTexts") {
    from("input")
    include("**/*.txt")
    include("**/*.md")
    exclude("**/draft/**")
    exclude("**/private/**")
    into(layout.buildDirectory.dir("texts"))
}
~~~

Hai `include` tạo một tập lựa chọn **OR**, không phải file phải vừa kết thúc `.txt` vừa `.md`. Hai `exclude` gộp lại để loại file khớp **một trong hai**. Nếu muốn **thay thế** toàn bộ patterns có sẵn, API `setIncludes(...)`/`setExcludes(...)` có ngữ nghĩa khác với lời gọi `include(...)`/`exclude(...)` cộng dồn.

### 6.4. Lọc ở Copy task hay ở từng nguồn from?

Tất cả nguồn bị lọc:

~~~kotlin
tasks.register<Copy>("copyAllFiltered") {
    from("assets")
    from("documents")
    include("**/*.md")
    into(layout.buildDirectory.dir("all-markdown"))
}
~~~

Chỉ lọc nguồn thứ nhất:

~~~kotlin
tasks.register<Copy>("copyTwoSources") {
    from("assets") {
        include("**/*.md")
    }
    from("documents")
    into(layout.buildDirectory.dir("two-sources"))
}
~~~

Trong ví dụ thứ hai, `from("assets")` có child CopySpec lọc Markdown, nhưng `from("documents")` không nhận bộ lọc riêng của child spec kia. Vì vậy **không suy ra tất cả nguồn đều chỉ còn Markdown**.

Nếu áp dụng `include("**/*.md")` tại **cấp task**, filter được áp lên các nguồn thuộc task. Nếu đặt trong `from(...) { }`, filter chỉ dành cho nhánh CopySpec đó; các exclude chung ở cấp cha vẫn có thể áp dụng xuống dưới.

## 7. Bài thực hành hoàn chỉnh: Java 17 + lọc assets và resources

Bài này có thể tạo lại từ đầu bằng **JDK 17**, một bản Gradle tương thích (hoặc Gradle Wrapper đã chuẩn bị). Không dùng thư viện bên ngoài: chỉ cần Gradle built-in Application plugin và Java Standard Library.

### 7.1. Tạo cây thư mục chính xác

~~~text
file-pattern-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── assets/
│   ├── config/
│   │   ├── app.json
│   │   └── test-debug.json
│   ├── docs/
│   │   ├── guide.md
│   │   └── draft/
│   │       └── notes.md
│   ├── images/
│   │   ├── logo.svg
│   │   └── old/
│   │       └── old-logo.svg
│   ├── notes.txt
│   └── tmp/
│       └── cache.tmp
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── Main.java
        └── resources/
            ├── app.properties
            ├── env/
            │   ├── dev.properties
            │   └── prod.properties
            ├── public/
            │   └── help.txt
            └── docs/
                ├── manual.md
                └── private/
                    └── notes.md
~~~

Hãy tạo đúng các thư mục và file ở cây trên. Nội dung của các file asset (`.json`, `.md`, `.svg`, `.tmp`) có thể là văn bản ngắn đúng định dạng hoặc nội dung mẫu vì task Copy chỉ cần chọn và sao chép chúng, **không parse JSON/SVG**. Riêng `src/main/resources/app.properties` cần nội dung chính xác:

~~~properties
app.name=resource-demo
~~~

`src/main/resources/env/dev.properties`:

~~~properties
environment=dev
~~~

`src/main/resources/env/prod.properties`:

~~~properties
environment=prod
~~~

`src/main/resources/docs/manual.md`:

~~~markdown
# User manual
~~~

`src/main/resources/docs/private/notes.md`:

~~~markdown
# Internal notes
~~~

`src/main/resources/public/help.txt`:

~~~text
Usage information
~~~

### 7.2. settings.gradle.kts

~~~kotlin
rootProject.name = "file-pattern-lab"
~~~

### 7.3. build.gradle.kts — mã hoàn chỉnh

~~~kotlin
import org.gradle.language.jvm.tasks.ProcessResources

plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

// Chỉ đóng tài nguyên cần thiết vào runtime classpath.
tasks.named<ProcessResources>("processResources") {
    include("**/*.properties", "public/**/*.txt", "docs/**/*.md")
    exclude("**/private/**", "**/*.tmp", "env/prod.properties")
    includeEmptyDirs = false
}

// Sao chép tập asset theo pattern từ một nguồn riêng.
tasks.register<Copy>("copySelectedAssets") {
    group = "learning"
    description = "Chọn .md/.svg/.json, bỏ draft, old và test JSON"

    from("assets") {
        include("**/*.md", "**/*.svg", "**/*.json")
        exclude("**/draft/**", "**/old/**", "**/test-*.json")
    }

    into(layout.buildDirectory.dir("selected-assets"))
    includeEmptyDirs = false
}
~~~

**Giải thích:**

1. `plugins { id("application") }` cung cấp Java/Application tasks, gồm `processResources` và `run`.
2. `tasks.named<ProcessResources>("processResources")` cấu hình **task resource processing đã có**, không tạo một task cùng tên khác.
3. `include("**/*.properties", "public/**/*.txt", "docs/**/*.md")` cho phép property file ở mọi cấp, TXT trong `public` và Markdown trong `docs`.
4. `exclude("**/private/**", "**/*.tmp", "env/prod.properties")` loại file ở thư mục `private`, file tạm và cấu hình production. **Exclude thắng** dù `prod.properties` đã khớp include `**/*.properties`.
5. `copySelectedAssets` là task riêng dùng `Copy` để lọc thư mục `assets` và ghi vào `build/selected-assets`.
6. `includeEmptyDirs = false` tránh sao chép thư mục rỗng do các bộ lọc tạo ra; mặc định Copy task thường cho phép thư mục rỗng.

### 7.4. Main.java — Java 17 đọc đúng các tài nguyên được giữ lại

Tạo `src/main/java/demo/Main.java`:

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                 Main.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IOException("Missing app.properties");
            }
            properties.load(input);
        }

        System.out.println("App=" + properties.getProperty("app.name"));
        System.out.println("Dev resource=" +
                (Main.class.getResource("/env/dev.properties") != null));
        System.out.println("Manual resource=" +
                (Main.class.getResource("/docs/manual.md") != null));
        System.out.println("Prod resource=" +
                (Main.class.getResource("/env/prod.properties") != null));
        System.out.println("Private resource=" +
                (Main.class.getResource("/docs/private/notes.md") != null));
    }
}
~~~

Đây là mã Java hợp lệ cho **Java 17**. Khi dùng Application plugin, Gradle xử lý resource theo `processResources` trước khi ứng dụng được chạy qua `run`; ứng dụng kiểm tra resource trên **runtime classpath đã được xử lý**, không phải quét trực tiếp thư mục nguồn `src/main/resources`.

### 7.5. Chạy task lọc assets

Tại thư mục `file-pattern-lab`:

~~~bash
gradle --console=plain copySelectedAssets
~~~

Các file dự kiến ở đầu ra (không có `draft`, `old`, `test-debug.json`, `cache.tmp` và `notes.txt`):

~~~text
build/selected-assets/config/app.json
build/selected-assets/docs/guide.md
build/selected-assets/images/logo.svg
~~~

**Đây là danh sách file dự kiến, không phải stdout cố định của Gradle.** Log Gradle có thể có `UP-TO-DATE` hoặc những task status khác tùy trạng thái build. Trên macOS/Linux có thể xác minh bằng:

~~~bash
find build/selected-assets -type f | sort
~~~

Trên Windows PowerShell:

~~~powershell
Get-ChildItem build/selected-assets -Recurse -File |
    ForEach-Object { $_.FullName }
~~~

Đường dẫn tuyệt đối trên Windows khác danh sách relative path bên trên; đối chiếu ba đường dẫn con trong thư mục `selected-assets`.

### 7.6. Chạy Java qua Gradle và dự đoán output

~~~bash
gradle --quiet run
~~~

Trong trạng thái nguồn như mục 7.1, **stdout do chương trình Java tạo ra** là:

~~~text
App=resource-demo
Dev resource=true
Manual resource=true
Prod resource=false
Private resource=false
~~~

Vì sao?

- `app.properties` khớp `**/*.properties` nên có trên classpath.
- `env/dev.properties` cũng khớp và không bị exclude.
- `docs/manual.md` khớp `docs/**/*.md`.
- `env/prod.properties` khớp include nhưng bị `exclude("env/prod.properties")` loại.
- `docs/private/notes.md` khớp include nhưng bị `exclude("**/private/**")` loại.

`Main.class.getResource(...)` trả về URL nếu resource có trên classpath và `null` nếu không. Đừng lẫn với việc các file bị loại vẫn **tồn tại ở thư mục nguồn**: Gradle chỉ bỏ chúng khỏi tập được xử lý cho đích.

### 7.7. Kiểm tra thư mục resources do Gradle tạo

~~~bash
gradle --console=plain processResources
~~~

Sau khi task thực thi, kiểm tra:

~~~text
build/resources/main/app.properties
build/resources/main/env/dev.properties
build/resources/main/docs/manual.md
build/resources/main/public/help.txt
~~~

Không nên có `build/resources/main/env/prod.properties` hoặc `build/resources/main/docs/private/notes.md` do lần xử lý này.

**Lưu ý khi lặp lại thí nghiệm:** Nếu bạn đã chạy build với cấu hình lọc khác trước đó, đích có thể chứa output cũ tùy task/trạng thái và cơ chế cleanup. Để kiểm tra trên trạng thái sạch mà không phải tự xóa thủ công, chạy `gradle clean processResources` hoặc `gradle clean run` với plugin Java/Application đã áp dụng. `clean` xóa **build directory** của project, không được dùng trên thư mục nguồn có dữ liệu cần giữ.

### 7.8. Sử dụng Gradle Wrapper

Nếu dự án đã có `gradlew`/`gradlew.bat`, nên dùng Wrapper thay lệnh `gradle`:

~~~bash
# macOS / Linux
./gradlew clean copySelectedAssets
./gradlew --quiet run

# Windows PowerShell / cmd
gradlew.bat clean copySelectedAssets
gradlew.bat --quiet run
~~~

Nếu chưa có Wrapper, có thể tạo bằng `gradle wrapper` khi đã cài Gradle tương thích. Để chạy bằng Java 17, máy/CI cần cung cấp Java toolchain phù hợp; cấu hình `languageVersion.set(JavaLanguageVersion.of(17))` không tự cam kết đã có JDK 17.

## 8. Lọc trực tiếp một FileTree

### 8.1. Chọn Markdown trong một cây thư mục

~~~kotlin
val docs = fileTree("assets") {
    include("docs/**/*.md")
    exclude("**/draft/**")
}

tasks.register<Copy>("copyDocsOnly") {
    from(docs)
    into(layout.buildDirectory.dir("docs-only"))
    includeEmptyDirs = false
}
~~~

Đặt đoạn này vào `build.gradle.kts` của project ở mục 7. Khi chạy `gradle copyDocsOnly`, chỉ `assets/docs/guide.md` được sao chép theo lựa chọn đó, với relative path `docs/guide.md` dưới `build/docs-only`. `assets/docs/draft/notes.md` bị loại.

`fileTree("assets")` giúp một bộ chọn file được **tái sử dụng** nếu nhiều task cùng cần tập Markdown đó. Nó không phải `file("assets")` đơn lẻ; `FileTree` chứa nhiều file có cấu trúc phân cấp. Nếu muốn thêm một lớp lọc khác mà không sửa tree gốc, dùng `matching { ... }`.

### 8.2. `matching { }` trên FileTree đã có

~~~kotlin
val allAssets = fileTree("assets")

val filteredAssets = allAssets.matching {
    include("**/*.md", "**/*.svg")
    exclude("**/old/**", "**/draft/**")
}

tasks.register<Copy>("copyFilteredTree") {
    from(filteredAssets)
    into(layout.buildDirectory.dir("filtered-tree"))
}
~~~

`matching` tạo góc nhìn FileTree được lọc; bạn có thể truyền vào task khác. Nó không xóa file trong `assets`. Nếu thêm nhiều bộ lọc ở các tầng khác nhau, file phải đáp ứng cả những ràng buộc thực sự đã được áp dụng; một include ở tầng sau không “hồi sinh” file bị loại bởi tầng nguồn trước đó.

### 8.3. FileCollection khác FileTree thế nào?

| Kiểu | Điểm chính | Khi nào dùng |
| --- | --- | --- |
| `FileCollection` | Tập các file/directory; không tự mang cây đường dẫn matching giống FileTree | Classpath, inputs từ nhiều file, dependency artifacts |
| `FileTree` | Tập file có cấu trúc cây và hỗ trợ `matching`/`include`/`exclude` | Duyệt, copy, lọc cây nguồn |
| `CopySpec` | Đặc tả nguồn, đích, lọc, biến đổi khi sao chép | `Copy`, `Sync`, archive/processing |
| `SourceDirectorySet` | Khai báo thư mục nguồn và pattern của source set | Java source/resources |
| `PatternFilterable` | Giao diện chung của tập pattern/spec include/exclude | Các API hỗ trợ Ant-style filter |

Khi bạn biến `fileTree(...).files` thành tập các `File` cụ thể quá sớm, có thể mất tính lười của việc duyệt tập file và khó theo dõi quan hệ source/output. Ưu tiên giữ `FileTree`/`Provider` rồi nối vào task.

## 9. Source sets và processResources: chọn tài nguyên Java

### 9.1. SourceDirectorySet lọc tập resource nguồn

Ví dụ Java plugin với Kotlin DSL:

~~~kotlin
plugins {
    id("java")
}

sourceSets {
    named("main") {
        resources {
            srcDir("src/main/resources")
            include("**/*.properties", "**/*.json")
            exclude("**/private/**")
        }
    }
}
~~~

Đây là **một phương án riêng**, không ghép nguyên vào ví dụ hoàn chỉnh ở mục 7 nếu bạn vẫn muốn `docs/manual.md` nằm trên classpath: đoạn này chỉ chọn `.properties` và `.json` cho resources.

Các pattern của `resources` trong source set xác định **tập nguồn** được coi là resource của source set đó; Java plugin dùng tập ấy để xử lý resources. Nếu loại một file ở tầng source set, thêm `include` ở `processResources` **không tự đưa file đã loại trở lại**.

### 9.2. ProcessResources lọc lúc sao chép vào classpath

Ở project đã có Java plugin:

~~~kotlin
import org.gradle.language.jvm.tasks.ProcessResources

tasks.named<ProcessResources>("processResources") {
    include("**/*.properties", "**/*.md")
    exclude("**/private/**", "**/*.bak")
}
~~~

Task này dựa trên CopySpec nên dùng cùng quy tắc include/exclude. Nó đưa những resource hợp lệ từ nguồn `main.resources` vào đích của `processResources` (mặc định trong `build/resources/main`).

**Mục đích học:** nếu muốn loại tài nguyên từ runtime classpath, bộ lọc ở đúng giai đoạn xử lý resource có thể phù hợp. Nếu muốn định nghĩa ngay từ đầu tập nguồn hợp lệ cho nhiều task/plugin, cân nhắc lọc ở source set. Không nên tạo hai bộ lọc mâu thuẫn ở hai tầng chỉ để “đảm bảo chắc chắn”.

### 9.3. Package/class không quyết định pattern của resource

Trong Java, `demo.Main` dùng package `demo` và Java classpath. Còn resource `docs/manual.md` nằm trong cây `src/main/resources`, không bắt buộc có package Java tương ứng. Khi gọi `Main.class.getResource("/docs/manual.md")`, dấu `/` đầu là đường dẫn tuyệt đối trong classpath; nó **khác** với cách định nghĩa source-relative pattern `docs/**/*.md` trong Gradle.

Cũng không nên áp dụng `include("**/*.properties")` lên `src/main/java` rồi nghĩ Java compiler tự hiểu đó là resource filter. Các task/source set khác nhau có trách nhiệm khác nhau.

## 10. PatternFilterable và điều kiện lọc phức tạp bằng Spec

### 10.1. Khi glob chưa đủ

Có lúc yêu cầu không thể biểu diễn gọn bằng `*`, `?`, `**`, ví dụ bỏ các file tên `draft.md` bất kể vị trí, hoặc chọn file dựa trên metadata của `FileTreeElement`.

Kotlin DSL:

~~~kotlin
import org.gradle.api.file.FileTreeElement

tasks.register<Copy>("copyReadableDocs") {
    from("assets/docs") {
        include("**/*.md")
        exclude { details: FileTreeElement ->
            details.name == "draft.md"
        }
    }
    into(layout.buildDirectory.dir("readable-docs"))
}
~~~

`exclude { ... }` nhận một **predicate**: trả về `true` nghĩa là **loại** file. Ví dụ này không cần đọc nội dung file, chỉ dựa tên. Với ví dụ thư mục `assets/docs` ở mục 7, file `draft/notes.md` **không** bị loại bởi điều kiện tên `draft.md`; nếu mục đích là bỏ cả thư mục draft, hãy dùng `exclude("**/draft/**")` thay vì predicate tên file.

Groovy DSL tương đương:

~~~groovy
import org.gradle.api.file.FileTreeElement

tasks.register('copyReadableDocs', Copy) {
    from('assets/docs') {
        include '**/*.md'
        exclude { FileTreeElement details ->
            details.name == 'draft.md'
        }
    }
    into layout.buildDirectory.dir('readable-docs')
}
~~~

### 10.2. Predicate include có quan hệ OR với include pattern

Ví dụ:

~~~kotlin
tasks.register<Copy>("chooseByRule") {
    from("assets") {
        include("**/*.md")
        include { details: FileTreeElement ->
            details.name == "logo.svg"
        }
        exclude("**/draft/**")
    }
    into(layout.buildDirectory.dir("rule-selection"))
}
~~~

Cơ chế: file khớp **một trong hai include** sẽ là ứng viên; nếu nằm trong `draft` thì vẫn bị loại. Không hiểu lời gọi `include { ... }` như “bộ lọc AND phụ thêm” lên `include("**/*.md")`; các include cùng tầng về cơ bản tạo tập hợp hợp nhất.

Nếu bạn cần hai điều kiện **đồng thời** (ví dụ vừa `.md` vừa tên không bắt đầu `draft`), nên sử dụng **một include Spec** kiểm tra cả hai, hoặc dùng include cho extension kết hợp exclude cho các trường hợp không mong muốn.

### 10.3. Cân nhắc hiệu năng và caching

Predicate đọc toàn bộ **nội dung từng file** (ví dụ `readText()`) trong khi quét có thể tốn thời gian và gây nhiều I/O trong build. Với điều kiện đơn giản, pattern chuỗi thường dễ hiểu và hiệu quả hơn.

Khi task phải thật sự biến đổi **nội dung** file, cân nhắc `filter(...)`/`expand(...)` của CopySpec hoặc custom task có input/output rõ. Đừng tự viết vòng lặp `File.walkTopDown()` ngay ở top-level build script để copy xong rồi mới “dọn” file; như vậy tách công việc ra khỏi cơ chế theo dõi task của Gradle.

## 11. Copy và Sync: vì sao kết quả đôi khi vẫn còn file cũ?

### 11.1. Copy không đồng nghĩa đồng bộ đích

Giả sử lần 1 bạn copy `config/a.json` và `config/b.json`. Lần 2 thay include để chỉ lấy `a.json`. Một `Copy` task không nhất thiết xóa mọi file không còn thuộc nguồn/selection trong thư mục đích. Vì vậy `b.json` có thể vẫn tồn tại từ lần trước ở đích.

Điều đó **không chứng minh** pattern đã chọn sai. Để kiểm tra kết quả trên trạng thái sạch, dùng một thư mục đích dành riêng trong `layout.buildDirectory`, hoặc chạy `clean` trước khi kiểm tra.

### 11.2. Sync đồng bộ đích theo nguồn được chọn

~~~kotlin
tasks.register<Sync>("syncSelectedDocs") {
    from("assets/docs") {
        include("**/*.md")
        exclude("**/draft/**")
    }
    into(layout.buildDirectory.dir("synced-docs"))
    includeEmptyDirs = false
}
~~~

Về nguyên tắc, `Sync` sao chép các file nguồn được chọn **và loại bỏ nội dung thừa ở đích** để đồng bộ, chịu ảnh hưởng của cấu hình preserve và hành vi task. Điều này có thể **xóa file** nằm trong thư mục đích nếu không còn thuộc tập nguồn. Đó là lý do phải dùng **thư mục đích riêng do build quản lý**, tuyệt đối không trỏ `Sync` vào source directory hay thư mục chứa dữ liệu quan trọng.

Nếu tập nguồn rỗng, hành vi xử lý đích còn phụ thuộc quy tắc task/version như `skipWhenSourceIsEmpty`. Đừng tự suy ra “Sync với nguồn rỗng chắc chắn xóa sạch đích” trong mọi cấu hình. Khi mục tiêu chỉ là **chọn file để copy** và không cần đồng bộ/xóa file cũ, `Copy` đơn giản và an toàn hơn.

### 11.3. IncludeEmptyDirs và duplicatesStrategy

- `includeEmptyDirs = false` ngăn các thư mục trống được đưa vào output copy theo lựa chọn phù hợp. Nó **không phải** thao tác xóa file hay xóa thư mục của nguồn.
- Nếu nhiều `from(...)` chứa các file có cùng đường dẫn đích, đó là **duplicate destination**. Pattern không tự chọn “file mới nhất”. Cần cấu hình `duplicatesStrategy` phù hợp (`INCLUDE`, `EXCLUDE`, `FAIL`, v.v.), hoặc tổ chức lại nguồn/`into` để không đụng tên. Cân nhắc `DuplicatesStrategy.FAIL` nếu trùng file là lỗi logic đáng phát hiện sớm.
- `CopySpec.rename(...)` đổi tên file ở đích, không đổi filter include/exclude ở nguồn. Nếu muốn lọc theo tên mới, phải hiểu rõ thứ tự các bước và chọn phương pháp phù hợp; mặc định nên match theo **tên/relative path nguồn**.

## 12. Khi cần đóng gói vào ZIP hoặc JAR

### 12.1. Lọc nội dung một archive tùy chỉnh

~~~kotlin
tasks.register<Zip>("zipGuides") {
    from("assets") {
        include("docs/**/*.md", "images/**/*.svg")
        exclude("**/draft/**", "**/old/**")
    }
    archiveFileName.set("guides.zip")
    destinationDirectory.set(layout.buildDirectory.dir("archives"))
}
~~~

Task `Zip` cũng chấp nhận CopySpec nên các mẫu lựa chọn tương tự. Thí nghiệm trên dự kiến nén `docs/guide.md` và `images/logo.svg` (không có nội dung `draft`/`old`) vào `build/archives/guides.zip`.

Không coi đoạn này là JAR Java có thể chạy: `Zip` chỉ tạo ZIP chứa các file được chọn. Nếu dùng `Jar` của Java plugin, cần chú ý rằng lọc tại archive có thể làm mất class hoặc resource quan trọng; hãy áp dụng tại phạm vi phù hợp và kiểm tra nội dung bằng công cụ liệt kê archive.

### 12.2. zipTree để chọn một phần file trong archive

~~~kotlin
tasks.register<Copy>("extractDocs") {
    from(zipTree("incoming/docs-bundle.zip")) {
        include("docs/**/*.md")
        exclude("**/draft/**")
    }
    into(layout.buildDirectory.dir("extracted-docs"))
}
~~~

Đây là **đoạn minh họa**, chỉ chạy khi đã có file `incoming/docs-bundle.zip` hợp lệ. `zipTree(...)` xem nội dung ZIP dưới dạng file tree để áp dụng pattern, không phải tải file từ network. Cần bảo đảm archive đến từ nguồn tin cậy và đường dẫn đích được quản lý an toàn.

Trong trường hợp unpack tùy biến đường dẫn, Gradle có thể dùng `eachFile { ... }` hoặc `rename(...)` để biến đổi đường dẫn đích; đây là **bước khác** so với file selection. Đừng dùng `include` để mong tự động “bỏ thư mục cha” khi chép: muốn thay đổi layout đích, hãy dùng CopySpec/`into`/`eachFile`.

## 13. Tránh nhầm với các cơ chế lọc khác

| Cơ chế | Đang chọn cái gì? | Ví dụ |
| --- | --- | --- |
| `CopySpec.include/exclude` | File/relative path được copy/process/package | `include("**/*.md")` |
| `FileTree.matching` | Tập file trong file tree | `fileTree("src").matching { exclude("**/*.tmp") }` |
| `SourceDirectorySet.include/exclude` | File nguồn thuộc source set | `sourceSets.main.resources` |
| `filter(...)` hoặc `expand(...)` | **Nội dung bên trong file được copy** | Thay giá trị trong template text |
| `dependencies { ... }` và dependency exclusions | **Module/artifact dependency** trong dependency graph, không phải file paths | `exclude(group = "...", module = "...")` |
| `.gitignore` | File Git nên bỏ qua khi theo dõi thay đổi | `build/`, `*.log` |
| `onlyIf { ... }` của task | **Toàn bộ task có được chạy không** | Bỏ qua task theo điều kiện |
| Gradle `--exclude-task` | **Task** bị loại khỏi execution graph | `gradle build -x test` |

Một file bị `.gitignore` bỏ qua **vẫn có thể** được Gradle copy nếu nó tồn tại và phù hợp filter. Ngược lại, file được Git theo dõi vẫn có thể bị Gradle `exclude` khỏi bản đóng gói. Chúng giải quyết những bài toán khác nhau.

Không dùng `-x test` với mục đích loại file `Test.java`. `-x` loại **task**, không phải tên file. Nếu muốn thay đổi file nào thuộc một task, dùng bộ lọc của source set/task tương ứng.

## 14. Những lỗi phổ biến và cách sửa

### Lỗi 1. `*.txt` không lấy file trong thư mục con

~~~kotlin
include("*.txt")
~~~

Với nguồn `assets`, đây là mẫu không đệ quy. Nếu bạn muốn cả `assets/a.txt` và `assets/docs/a.txt`, dùng:

~~~kotlin
include("**/*.txt")
~~~

### Lỗi 2. Viết thêm tên thư mục đã nằm trong from

~~~kotlin
from("assets") {
    include("assets/docs/**/*.md")
}
~~~

Nếu file thực tế là `assets/docs/guide.md`, relative path cần match là `docs/guide.md`. Sửa thành:

~~~kotlin
from("assets") {
    include("docs/**/*.md")
}
~~~

### Lỗi 3. Nghĩ exclude được include “ghi đè” lại

~~~kotlin
include("**/*.json")
exclude("**/private/**")
include("private/config.json")
~~~

`private/config.json` vẫn bị loại vì `exclude` thắng; đổi thứ tự không thay đổi điều đó. Nếu thật sự cần một file ngoại lệ, hãy thiết kế lại bộ lọc hoặc tách thành child specs với phạm vi được tính toán rõ ràng; không trông đợi include cuối tự hồi sinh file bị exclude trước.

### Lỗi 4. Dùng regex thay Ant glob

~~~kotlin
include(".*\\.json$")
~~~

Đây là biểu thức regex quen thuộc nhưng không được `include(String)` diễn giải như regex. Sửa thành `include("**/*.json")` hoặc dùng predicate phù hợp.

### Lỗi 5. Nhầm dấu `?` với một chuỗi bất kỳ

`data?.csv` chỉ khớp đúng **một ký tự** ở vị trí dấu hỏi. Nó không khớp `data.csv` (không có ký tự) hoặc `data12.csv` (hai ký tự). Nếu muốn mọi hậu tố, dùng `data*.csv`.

### Lỗi 6. Không để ý chữ hoa/chữ thường

`readme.MD` và `readme.md` có thể không cùng kết quả với `include("**/*.md")` vì case sensitivity. Kiểm tra tên file thực tế; với Copy task có thể đặt `isCaseSensitive = false` khi có yêu cầu rõ.

### Lỗi 7. Lọc sai tầng

Lọc `sourceSets.main.resources` có thể khiến resource biến mất từ nguồn đầu vào của `processResources`. Thêm include ở `processResources` không tự tái tạo file bị loại trước đó. Trước khi sửa, xác định bộ lọc nằm ở source set, Copy/ProcessResources hay Jar.

### Lỗi 8. Nhìn thư mục đích có file cũ và kết luận sai

`Copy` không phải đồng bộ/xóa các file dư ở đích. Thử `gradle clean <task>` khi đích thuộc build directory hoặc dùng đích riêng mới. Chỉ cân nhắc `Sync` nếu hiểu rõ tác động xóa file.

### Lỗi 9. Không kiểm tra duplicate destination

Hai nguồn có thể chứa cùng `config/app.properties`. Nếu chúng được copy vào chung một đích, cần chính sách rõ ràng; chỉ dùng `include` không tự giải quyết xung đột. Kiểm tra task error và cấu hình `duplicatesStrategy` hoặc thay đổi layout đích.

### Lỗi 10. Không xác định đúng output

~~~kotlin
from("assets/docs")
into(layout.buildDirectory.dir("output"))
~~~

`guide.md` sẽ nằm trực tiếp trong `build/output/guide.md`, không tự có thư mục `docs` ở giữa. Đổi `from("assets") { include("docs/**") }` khi cần giữ tiền tố `docs`.

### Lỗi 11. Copy được file nhưng không có trên runtime classpath

Task `copySelectedAssets` của bài thực hành sao chép tới `build/selected-assets`, không tự đưa thư mục này vào Java runtime classpath. Nếu ứng dụng cần đọc tài nguyên như classpath resource, hãy cấu hình source sets hoặc `processResources`/phân phối ứng dụng thích hợp. Việc file tồn tại dưới `build/` không đồng nghĩa `Class.getResource(...)` tìm thấy nó.

### Lỗi 12. Dùng exclude như biện pháp bảo mật duy nhất

`exclude("**/secrets/**")` giúp tránh một số file bị copy, nhưng **không** đảm bảo bí mật không bị build khác/plugin khác đóng gói hoặc log. Bí mật nên được giữ bên ngoài thư mục nguồn được đóng gói, cấp từ môi trường/CI hoặc cơ chế credential phù hợp. Kiểm tra artifact cuối trước khi xuất bản.

## 15. Cách kiểm tra kết quả có hệ thống

Đối với yêu cầu chọn file, hãy xác minh theo hai lớp: **tập nguồn được chọn** và **artifact/output thật**.

1. Viết ra **gốc nguồn**: ví dụ `assets` hay `src/main/resources`.
2. Liệt kê một vài **relative paths** tiêu biểu: `config/app.json`, `docs/draft/notes.md`.
3. Áp dụng quy tắc OR giữa include, sau đó loại theo OR giữa exclude.
4. Chạy task với đích riêng trong `build` để không nhầm file cũ.
5. Dùng `find`, PowerShell `Get-ChildItem`, hoặc trình duyệt file để kiểm tra **file thực tế**; đừng coi output task Gradle là danh sách file đã copy.
6. Với Java resources, kiểm tra `build/resources/main` và chạy chương trình dùng `getResource`.
7. Với ZIP/JAR, kiểm tra **bên trong archive**, không chỉ kiểm tra sự tồn tại của file archive.
8. Khi thay filter, chạy lại trên trạng thái sạch nếu cần so sánh chính xác, nhưng không dùng các lệnh dọn dẹp trên thư mục không thuộc build.

Lệnh thường dùng:

~~~bash
gradle --console=plain tasks --all
gradle --console=plain copySelectedAssets
gradle --console=plain processResources
gradle --quiet run
gradle --console=plain clean copySelectedAssets processResources
~~~

Với Gradle Wrapper đã được lưu trong project, thay `gradle` bằng `./gradlew` hoặc `gradlew.bat`. `--dry-run` có thể giúp xem task được lên lịch nhưng **không chạy action**, nên không xác minh được file nào đã được sao chép. `--info` giúp xem task status và một số chi tiết nhưng không thay thế việc kiểm tra thư mục đích.

Để tránh nondeterministic output, không nên kiểm tra danh sách file theo đúng thứ tự duyệt của `FileTree` khi chưa sắp xếp. Đường dẫn và trạng thái chính xác quan trọng hơn thứ tự log.

## 16. Bài tập và đáp án

### Bài 1. Phân biệt * và **

Cho file:

~~~text
data/a.csv
data/archive/b.csv
data/archive/old/c.csv
~~~

Nguồn là `from("data")`. `include("*.csv")` và `include("**/*.csv")` khác nhau thế nào?

**Đáp án:** `*.csv` chọn `a.csv` ở cấp gốc nguồn; `**/*.csv` chọn `a.csv`, `archive/b.csv`, `archive/old/c.csv`.

### Bài 2. Exclude có thắng include không?

~~~kotlin
include("**/*.json")
exclude("**/private/**")
~~~

File `private/config.json` có được chọn không?

**Đáp án:** Không. File khớp `**/*.json` nhưng cũng khớp exclude, nên bị loại.

### Bài 3. Hai include có phải điều kiện AND không?

~~~kotlin
include("**/*.md")
include("**/*.txt")
~~~

Một file cần đồng thời có hai extension mới được chọn?

**Đáp án:** Không. Các include được thêm có ý nghĩa OR. File khớp một trong hai là ứng viên (sau đó vẫn xét excludes).

### Bài 4. Tìm lỗi gốc pattern

Nguồn `from("assets")`, file `assets/docs/guide.md`. Pattern `include("assets/docs/*.md")` có đúng không?

**Đáp án:** Không. Relative path tại nguồn `assets` là `docs/guide.md`, nên dùng `include("docs/*.md")` hoặc `include("docs/**/*.md")` nếu có thư mục con.

### Bài 5. Chọn toàn bộ YAML trừ local

Hãy viết Kotlin DSL Copy task lấy mọi file `.yaml` từ `configs` nhưng loại thư mục `local` ở bất kỳ cấp nào, sao chép đến `build/yaml`.

**Đáp án:**

~~~kotlin
tasks.register<Copy>("copyYaml") {
    from("configs") {
        include("**/*.yaml")
        exclude("**/local/**")
    }
    into(layout.buildDirectory.dir("yaml"))
    includeEmptyDirs = false
}
~~~

### Bài 6. Vì sao vẫn còn file đã bị exclude?

Bạn thay pattern để bỏ `b.json`, nhưng `build/output/b.json` vẫn tồn tại sau `Copy`. Đâu là khả năng cần kiểm tra trước?

**Đáp án:** Đó có thể là file cũ ở thư mục đích; `Copy` không có ngữ nghĩa đồng bộ xóa file dư. Chạy trên đích sạch, hoặc dùng `Sync` vào thư mục riêng nếu bạn cần đồng bộ (và đã hiểu rủi ro xóa).

### Bài 7. Tác động lên Java resources

`processResources` có:

~~~kotlin
include("**/*.properties")
exclude("env/prod.properties")
~~~

Cho `src/main/resources/env/prod.properties` và `env/dev.properties`. File nào còn trong output?

**Đáp án:** `env/dev.properties` được chọn; `env/prod.properties` bị loại dù khớp include. Cả hai file **vẫn tồn tại ở source directory**.

### Bài 8. Điều kiện phức tạp

Bạn chỉ muốn chọn Markdown nhưng bỏ mọi file có tên bắt đầu `draft-` ở bất kỳ thư mục nào. Hãy dùng pattern.

**Đáp án:**

~~~kotlin
include("**/*.md")
exclude("**/draft-*.md")
~~~

Ví dụ `docs/guide.md` được giữ, `docs/draft-v2.md` bị loại. Nếu muốn bỏ cả thư mục tên `draft`, cần thêm `exclude("**/draft/**")`.

### Bài 9. Giữ thư mục cha trong output

Với `from("input/docs")`, đích `build/output`, bạn muốn output là `build/output/docs/guide.md` thay vì `build/output/guide.md`. Cần làm gì?

**Đáp án:** Đổi nguồn thành `from("input") { include("docs/**") }` hoặc dùng cấu hình `into("docs")` trong một child CopySpec phù hợp. Tên thư mục nằm trong `from` không tự được giữ ở đích.

### Bài 10. Lọc nội dung và lọc file

Muốn thay chuỗi `@version@` bên trong file `app.properties` bằng phiên bản project, chỉ dùng `include("**/*.properties")` có đủ không?

**Đáp án:** Không. `include` chỉ quyết định file có được chọn, không thay nội dung. Cần dùng `expand(...)`, `filter(...)` hoặc cơ chế resource processing phù hợp; đồng thời khai báo đầu vào thay đổi như project version để Gradle theo dõi đúng.

## 17. Tóm tắt

- **`include` và `exclude` là bộ lọc file theo relative path**, không phải lệnh sửa/xóa file gốc.
- **Không có include → mặc định xét mọi file hợp lệ; có nhiều include → OR; có nhiều exclude → OR; exclude thắng nếu trùng.**
- **`*` và `?` áp dụng trong một phần đường dẫn; `**` biểu diễn nhiều cấp**; `**/*.ext` phù hợp cho chọn file đệ quy.
- **Pattern được tính từ gốc phù hợp** của `from(...)` hoặc `fileTree(...)`. Tránh thêm lại tiền tố nguồn.
- **CopySpec ở cấp task ảnh hưởng nhiều nguồn; child CopySpec trong `from { }` chỉ ảnh hưởng nhánh nguồn đó.**
- **`FileTree`, `Copy`, `Sync`, `ProcessResources`, source sets và archive tasks** có thể dùng pattern, nhưng tác động ở những tầng khác nhau.
- **Copy không tự bảo đảm xóa file cũ; Sync có khả năng xóa dữ liệu đích**, nên chỉ dùng đích riêng do build quản lý.
- Với Java 17, tài nguyên cần được giữ trong `processResources`/runtime classpath thì `Class.getResource(...)` mới đọc được chúng như classpath resources.
- Khi đưa artifact ra ngoài, **kiểm tra nội dung output thật**, đặc biệt với cấu hình riêng và dữ liệu nhạy cảm.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — Working With Files](https://docs.gradle.org/current/userguide/working_with_files.html) — Copy, FileTree, Sync và lọc file.
- [Gradle PatternFilterable API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/util/PatternFilterable.html) — ý nghĩa pattern, include/exclude và predicates.
- [Gradle FileTree API](https://docs.gradle.org/current/javadoc/org/gradle/api/file/FileTree.html) — `matching` và file trees.
- [Gradle Copy DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.Copy.html) — CopySpec, case sensitivity, empty directories và duplicates.
- [Gradle ProcessResources DSL](https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html) — resource filtering và copy actions.
