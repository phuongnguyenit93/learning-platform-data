# Tránh đường dẫn tuyệt đối, tác dụng phụ và đầu ra chồng lấn khi xử lý tệp, tài nguyên trong Gradle

## 1. Mục tiêu và vấn đề thực tế

Một custom task Gradle có thể chạy thành công trên máy lập trình nhưng thất bại trên CI, không thể dùng build cache sau khi đổi thư mục checkout hoặc khiến hai task ghi đè/xóa sản phẩm của nhau. Ba nguyên nhân thường gặp liên quan chặt chẽ với nhau:

1. **Đường dẫn tuyệt đối được viết cứng:** mã giả định mọi máy đều có `C:\Users\alice\project` hoặc `/home/alice/work/app`; đôi khi nó còn ghi đường dẫn máy vào file artifact.
2. **Tác dụng phụ không được mô tả:** build script ghi file ngay ở configuration phase, task sửa source, gọi mạng, đọc env/thời gian hoặc ghi file ngoài những output mà Gradle biết.
3. **Đầu ra chồng lấn (overlapping outputs):** nhiều task cùng sở hữu một file/thư mục, hoặc một task khai cả thư mục lớn làm output trong khi task khác khai file nằm bên trong. Task chạy song song, kiểm tra up-to-date, cache và dọn file cũ đều có thể bị ảnh hưởng.

**Nguyên tắc thiết kế:** *Mỗi task nên khai báo đầy đủ input, có vùng output riêng do nó sở hữu, không thay đổi input và chỉ thực hiện side effect đã mô tả khi task được chạy.* Đường dẫn nên đến từ API `layout`/property/provider của Gradle thay vì vị trí tuyệt đối của máy. <u>Một file có đường dẫn tuyệt đối ở runtime là bình thường; hard-code vị trí đó trong build logic hoặc ghi nó vào artifact khi không cần mới là vấn đề.</u>

Sau bài này, bạn có thể:
- Dùng `layout.projectDirectory`, `layout.buildDirectory`, `RegularFileProperty`, `DirectoryProperty` và `Provider` cho input/output.
- Phân biệt đường dẫn **tương đối, có thể cấu hình** với đường dẫn **tuyệt đối bị hard-code**, và phân biệt portability với yêu cầu sandbox/bảo mật.
- Đặt việc ghi file vào `@TaskAction`/task action, không ghi khi Gradle đang cấu hình build.
- Khai báo `@InputFile`, `@Input`, `@OutputFile` hoặc `@OutputDirectory` đúng phạm vi và tránh input ngầm.
- Chỉ ra lỗi khi hai task cùng ghi một destination, đặc biệt khi sử dụng `Copy`/`Sync`.
- Tổ chức quy trình **generate riêng → stage/merge riêng** và quan sát `UP-TO-DATE`, `FROM-CACHE`, configuration cache.
- Áp dụng quy tắc tương tự cho `processResources`, artifact và build nhiều project.

**Bối cảnh:** Ví dụ dùng **Gradle Groovy DSL** (`build.gradle`). Một bài thực hành đầy đủ dùng các API Java được hỗ trợ trên JDK 17+, có mã và kết quả mẫu được chỉ rõ. Lệnh `./gradlew` dành cho Linux/macOS, trên Windows PowerShell dùng `.\gradlew.bat`.

## 2. Mô hình Gradle cần hiểu trước khi viết file

Gradle không chỉ chạy từng task theo thứ tự xuất hiện trong `build.gradle`. Nó tạo **task graph**, xác định các input/output, kiểm tra điều kiện chạy, trạng thái up-to-date/cache rồi thực thi action của những task cần thiết.

~~~text
Project directory (nguồn được version-control)
       |
       | khai báo input: @InputFile / @InputDirectory / @Input
       v
 Task A: generate       Task B: generate
       |                      |
       | output A riêng       | output B riêng
       v                      v
 build/generated/a       build/generated/b
       \                      /
        \   input có nguồn   /
         \  gốc từ task    /
          v               v
            Task C: stage
                  |
                  v
           build/staged/...
~~~

Mô hình tốt ở trên cho phép Gradle biết task nào tạo output và task khác tiêu thụ output nào. Nếu A và B cùng ghi vào `build/staged` hoặc C sửa file trong `build/generated/a`, ranh giới sở hữu bị phá.

### 2.1. Ba khái niệm phải tách biệt

| Khái niệm | Câu hỏi cần trả lời | Trạng thái/khả năng liên quan |
| --- | --- | --- |
| **Task input/output đúng** | Gradle có biết mọi dữ liệu tác động kết quả và chính xác task nào sở hữu file nào? | Tính đúng của up-to-date/build cache |
| **Tính di động (portable/relocatable)** | Di chuyển checkout sang máy/thư mục khác có làm logic và fingerprint khác vô lý không? | Reuse giữa máy, CI, workspace |
| **Đầu ra tái lập (reproducible)** | Cùng input logic có tạo output giống nhau không? | Build cache tin cậy, kiểm tra artifact |

Một task dùng đường dẫn tương đối vẫn có thể **không tái lập** nếu nó ghi `Instant.now()` hoặc random ID. Ngược lại, một task sinh bytes xác định nhưng ghi đường dẫn home của lập trình viên vào report sẽ khó di chuyển sang workspace khác.

## 3. Tránh hard-code absolute path: dùng Gradle layout và provider

### 3.1. Phân biệt đường dẫn cứng với đường dẫn được xác định theo project

**Không nên**:

~~~groovy
tasks.register('copyConfiguration', Copy) {
    from 'C:/Users/alice/work/my-service/config'
    into '/home/alice/output/config'
}
~~~

Hai đường dẫn trên là **ví dụ sai có chủ đích**: chúng gắn với cấu trúc máy cụ thể và thậm chí khác hệ điều hành. Script sẽ khó chạy được ở CI, máy đồng nghiệp hoặc checkout khác.

**Nên dùng**:

~~~groovy
tasks.register('copyConfiguration', Copy) {
    from(layout.projectDirectory.dir('config'))
    into(layout.buildDirectory.dir('staged/config'))
}
~~~

- `layout.projectDirectory.dir('config')` định vị nguồn theo **project đang cấu hình**, không phụ thuộc đường dẫn tuyệt đối của máy.
- `layout.buildDirectory.dir('staged/config')` tạo provider đến thư mục đầu ra nằm bên trong **build directory đã cấu hình**.
- Nếu build directory đổi, task dùng giá trị mới từ provider thay vì tiếp tục ghi vào `build/` hard-code.
- `Copy` sẽ đọc nguồn khi task thực thi theo hành vi Gradle, không cần tự gọi `project.copy` trong configuration phase.

**Lưu ý:** API layout vẫn phải chuyển ra đường dẫn thật trên máy khi copy/đọc/ghi. Mục tiêu là **không đóng đinh cấu trúc filesystem của máy** vào build script và không biến absolute path không liên quan thành dữ liệu logic của artifact.

### 3.2. Các API thường dùng

| API | Kết quả/ý nghĩa | Nên dùng khi |
| --- | --- | --- |
| `layout.projectDirectory` | `Directory` đại diện thư mục gốc của project hiện tại | Lấy nguồn/configuration được quản lý trong project |
| `layout.projectDirectory.file('data/input.txt')` | `RegularFile` theo project | Chọn file input ổn định |
| `layout.projectDirectory.dir('assets')` | `Directory` theo project | Chọn thư mục input resources |
| `layout.buildDirectory` | `DirectoryProperty`, root output có thể cấu hình | Làm gốc cho output |
| `layout.buildDirectory.file('reports/result.txt')` | `Provider<RegularFile>` | Cấp vị trí output file của task |
| `layout.buildDirectory.dir('generated/resources')` | `Provider<Directory>` | Cấp vị trí output directory |
| `RegularFileProperty` | Task property có kiểu cho một file | `@InputFile`/`@OutputFile` |
| `DirectoryProperty` | Task property có kiểu cho một directory | `@InputDirectory`/`@OutputDirectory` |
| `ConfigurableFileCollection` | Tập file input được cấu hình | Task xử lý nhiều file |
| `providers.gradleProperty('name')` | Provider đọc project property | Cho phép người dùng/CI thay tham số không sửa script |

Ví dụ custom task có đường dẫn tùy biến nhưng **không** hard-code:

~~~groovy
def exportFolder = providers.gradleProperty('exportFolder')
    .orElse('exports/default')

tasks.register('copyAssets', Copy) {
    from(layout.projectDirectory.dir('assets'))
    into(layout.buildDirectory.dir(exportFolder.get()))
}
~~~

Đoạn trên **chỉ là snippet minh họa** dùng với `build.gradle` có thư mục `assets`. `get()` resolve provider khi task được cấu hình. Trong build lớn, nếu có thể, nên giữ giá trị dưới dạng Provider đến lúc API nhận được, tránh resolve sớm.

**Cẩn thận với `exportFolder`:** Nếu giá trị đến từ nguồn không tin cậy, không chấp nhận chuỗi có `..`, đường dẫn tuyệt đối hoặc path thoát khỏi output root một cách mù quáng. Chỉ đưa tham số đã được kiểm tra vào `layout.buildDirectory.dir(...)`; API này không thay cho chính sách security sandbox riêng.

### 3.3. Không dùng `new File('relative/path')` tùy tiện

~~~groovy
def input = new File('config/settings.properties')
~~~

`new File(...)` với đường dẫn tương đối dùng **working directory của JVM**, không có cam kết nó luôn trùng thư mục chứa `build.gradle` của subproject. Trong multi-project build, IDE hoặc CI có thể khởi chạy Gradle với working directory khác.

Để trỏ vào project đang cấu hình:

~~~groovy
def input = layout.projectDirectory.file('config/settings.properties')
~~~

Khi task cần truy cập dữ liệu thật, dùng `input.asFile` (với `RegularFile`) hoặc `fileProperty.get().asFile` bên trong task action. **Không nên dùng `System.getProperty('user.dir')` để đoán project root.**

### 3.4. Output của từng subproject phải độc lập

Trong multi-project build:

~~~text
root/
├── settings.gradle
├── app/build.gradle
└── core/build.gradle
~~~

Mỗi subproject thường có `layout.buildDirectory` riêng, ví dụ `app/build` và `core/build`. Tạo output của `:app` qua `app`'s `layout.buildDirectory` sẽ rõ sở hữu hơn việc cả `:app` và `:core` ghi vào một đường dẫn toàn cục `root/build/generated.txt`.

Nếu thật sự cần artifact tổng hợp ở root, hãy tạo **một task root duy nhất** tiêu thụ output của các subproject; đừng cho mọi subproject trực tiếp ghi cùng file chung.

## 4. Input file path sensitivity: đường dẫn nào thực sự quan trọng?

Ngay cả khi script dùng API layout, **fingerprint** của file input còn chịu ảnh hưởng cách bạn khai báo đường dẫn.

Trong custom task type:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
abstract RegularFileProperty getSourceFile()
~~~

Ý nghĩa: nội dung file vẫn được snapshot, nhưng phần path được tính theo relative path, tránh buộc các checkout khác nhau có cùng absolute path.

### 4.1. Các giá trị `PathSensitivity`

| Giá trị | Phần path được tính trong fingerprint | Khi hợp lý |
| --- | --- | --- |
| `ABSOLUTE` | Đường dẫn tuyệt đối | Output thực sự cần vị trí tuyệt đối (thường hạn chế reuse giữa máy) |
| `RELATIVE` | Đường dẫn tương đối bên trong root của input | Output phụ thuộc cấu trúc thư mục/tên file nhưng không phụ thuộc checkout root |
| `NAME_ONLY` | Chỉ tên file cuối path | Output cần basename, không cần vị trí thư mục |
| `NONE` | Không dùng path trong fingerprint | Output chỉ cần nội dung, không dùng cả tên file |

**`NONE` không có nghĩa bỏ qua nội dung file.** Nếu thay bytes của file, Gradle vẫn phải coi input thay đổi.

Một nhiệm vụ tạo sitemap `docs/api/start.md` và `docs/guide/start.md` cần **`RELATIVE`**, vì hai file có cùng basename nhưng cấu trúc path khác nhau. Một nhiệm vụ chuyển nội dung **một file** thành Markdown mà không ghi tên nguồn có thể dùng `NONE`.

**Bẫy nghiêm trọng:** Khai `@PathSensitive(NONE)` nhưng action ghi `sourceFile.get().asFile.absolutePath` vào report. Gradle có thể coi hai checkout là cùng input, trong khi bytes output khác nhau. Khi đó cache có nguy cơ trả output sai. Phải sửa logic không ghi absolute path hoặc dùng normalization phản ánh dependency thật.

### 4.2. Đường dẫn tương đối không đồng nghĩa sandbox

Khi nhận một tên file từ người dùng, phép nối như:

~~~groovy
def target = layout.buildDirectory.dir('reports')
    .get()
    .asFile
    .toPath()
    .resolve(userProvidedName)
    .normalize()
~~~

**Chỉ là ví dụ API, không phải biện pháp bảo mật hoàn chỉnh.** `userProvidedName` chưa được định nghĩa/kiểm tra; dữ liệu như `../../outside.txt` hoặc đường dẫn tuyệt đối có thể thoát khỏi `reports`. Nếu đầu vào không tin cậy, cần từ chối absolute paths, `..` không hợp lệ, kiểm tra normalized path nằm trong output root, xét symlink và các race conditions trước khi ghi. `Path.normalize()` thuần túy không xử lý symlink hay đảm bảo confinement.

Với build script thông thường, đơn giản nhất là chỉ dùng **tên output cố định do build logic kiểm soát** và chứa bên trong `layout.buildDirectory`.

## 5. Tác dụng phụ: ghi file, mạng, env và thay đổi trạng thái ngoài task

**Side effect** ở đây là thay đổi hoặc đọc trạng thái ngoài hợp đồng inputs/outputs của một task: sửa source, tạo file ngoài vùng output, thay đổi repository, gọi API mạng, cập nhật cơ sở dữ liệu, ghi log chứa secret, đổi biến hệ thống...

Không phải mọi side effect đều sai: task `Copy` đương nhiên ghi file, task `Publish` đương nhiên tải artifact. Vấn đề là **thời điểm, mức kiểm soát và khả năng Gradle theo dõi kết quả**.

### 5.1. Không ghi file trong configuration block

**Sai:**

~~~groovy
tasks.register('generateInfo') {
    def file = layout.buildDirectory.file('info.txt').get().asFile
    file.parentFile.mkdirs()
    file.text = 'generated too early'
}
~~~

Đoạn này ghi file **khi closure cấu hình task được chạy** (thời điểm task được realize/configure), không phải hành động execution của task. Chỉ yêu cầu `help` hoặc một plugin khác truy cập task cũng có thể gây side effect không mong muốn; `tasks.register` lazy khiến thời điểm đó càng khó suy ra.

**Tối thiểu đúng:**

~~~groovy
def infoFile = layout.buildDirectory.file('info.txt')

tasks.register('generateInfo') {
    outputs.file(infoFile)

    doLast {
        File target = infoFile.get().asFile
        target.parentFile.mkdirs()
        target.setText('generated at execution time\n', 'UTF-8')
    }
}
~~~

`outputs.file` khai báo file đầu ra và `doLast` chỉ ghi lúc task thực thi. Đây là snippet giúp phân biệt pha; để tái sử dụng lâu dài, **typed task** với `@OutputFile` và `@TaskAction` như phần 8 thường tốt hơn.

### 5.2. Không sửa source hoặc tệp kiểm soát đầu vào trong task tạo artifact

**Sai:**

~~~groovy
tasks.register('generateConfigUnsafe') {
    doLast {
        file('src/main/resources/config.properties').text = 'mode=prod'
    }
}
~~~

Vấn đề:
- Source trong `src/main/resources` thường được quản lý bằng VCS; task làm repository bị “dirty”.
- Java plugin's `processResources` có thể đã đọc file đó làm input trong cùng build; đổi nó sau khi snapshot có thể khiến output không nhất quán.
- Task không khai output nào, không rõ sở hữu file nào.
- `file(...)` là Project API được gọi trong task action; kiểu truy cập Project từ execution không tương thích với cách cấu hình configuration cache hiện đại.
- Build song song có thể gặp race khi task khác đọc resource cùng lúc.

**Đúng hướng:** Sinh file vào `layout.buildDirectory.file('generated/resources/config.properties')` bằng task có output khai báo, rồi **nối output đó** vào quá trình tiêu thụ resources. Không ghi ngược vào `src`.

### 5.3. Đọc input ngầm có thể làm cache sai

**Không nên** đối với task tạo artifact cần cache:

~~~groovy
tasks.register('makeHeader') {
    doLast {
        println System.getenv('RELEASE_CHANNEL')
        println new Date()
    }
}
~~~

Ví dụ trên chỉ in log và không có output, nhưng minh họa hai nguồn phụ thuộc ngầm. Nếu dùng `RELEASE_CHANNEL` và thời gian hiện tại để **sinh file** mà không khai chúng thành inputs, Gradle có thể dùng lại output cũ dù giá trị thay đổi.

Nên dùng Provider khai báo đầu vào:

~~~groovy
def channel = providers.environmentVariable('RELEASE_CHANNEL')
    .orElse('dev')

tasks.register('announceChannel') {
    inputs.property('channel', channel)

    doLast {
        println 'channel=' + channel.get()
    }
}
~~~

Đoạn này không tạo artifact; nó chỉ minh họa `inputs.property`. Với output thật, hãy thêm `@Input`/`@OutputFile` hoặc input/output DSL đầy đủ. Nếu bắt buộc có thời gian trong artifact, cần mô hình thời gian như một input có chủ đích, hoặc không đánh dấu task cacheable; không giả vờ output deterministic.

### 5.4. Mạng và thao tác bên ngoài

Task gọi HTTP, ghi database, push image hoặc publish ra server không giống task tạo file thuần:
- Kết quả có thể phụ thuộc response từ server, quyền truy cập, trạng thái remote và thời gian.
- Mô hình caching output trên đĩa không biểu diễn đầy đủ side effect ngoài hệ thống.
- Lặp lại hoặc bỏ qua task vì cache có thể gây hành vi bất ngờ nếu bạn đặt publish/deploy vào lifecycle `build`.

Giải pháp: dùng plugin/task chuyên dụng, phân tách `build` khỏi `publish`/`deploy`, áp dụng idempotency, xác thực credentials và điều kiện CI. Với tải artifact, ưu tiên dependency resolution có version/checksum thay vì `curl` tùy tiện ở configuration phase.

### 5.5. Configuration cache khác build cache

- **Configuration cache:** lưu trạng thái build sau configuration để không cần cấu hình lại khi đầu vào cấu hình không thay đổi.
- **Build cache:** lưu **output của task execution** đủ điều kiện, phục hồi khi fingerprint phù hợp.

Không ghi file trong configuration giúp tránh side effects khi configuration được thực hiện hoặc bỏ qua. Không truy cập `Project`, `Settings` hay script object từ task action cũng quan trọng với configuration cache; nên để task type truy cập các **typed properties** và service được Gradle hỗ trợ thay vì gọi `project.file(...)` bên trong action.

**Một task build-cache được không mặc nhiên configuration-cache compatible**, và ngược lại. Hãy kiểm tra riêng.

## 6. Đầu ra chồng lấn: rủi ro kỹ thuật và biểu hiện

**Overlapping outputs** xảy ra khi hai task tuyên bố hoặc ghi vào những vùng filesystem giao nhau.

### 6.1. Hai task cùng ghi đúng một file

~~~groovy
def shared = layout.buildDirectory.file('reports/summary.txt')

tasks.register('makeA') {
    outputs.file(shared)
    doLast {
        shared.get().asFile.text = 'A'
    }
}

tasks.register('makeB') {
    outputs.file(shared)
    doLast {
        shared.get().asFile.text = 'B'
    }
}
~~~

Đây là **ví dụ sai có chủ đích**: cùng một output file `reports/summary.txt` có hai chủ sở hữu. Nếu cả hai nằm trong graph, nội dung cuối có thể bị ghi đè theo thứ tự chạy; `dependsOn` đơn thuần chỉ áp một thứ tự nhất định chứ **không giải quyết quyền sở hữu**.

### 6.2. Hai task cùng output directory

~~~groovy
tasks.register('copyOne', Copy) {
    from(layout.projectDirectory.dir('assets/one'))
    into(layout.buildDirectory.dir('package'))
}

tasks.register('syncTwo', Sync) {
    from(layout.projectDirectory.dir('assets/two'))
    into(layout.buildDirectory.dir('package'))
}
~~~

Đây cũng là **cấu hình không an toàn**:
- Cả hai task sở hữu `build/package`.
- `Sync` đồng bộ và **xóa các file trong destination không thuộc nguồn của nó**, nên có thể xóa file do `copyOne` tạo.
- Nếu Gradle chạy task ở thứ tự khác nhau, nội dung cuối có thể khác. `--parallel` khiến rủi ro khó chẩn đoán hơn.
- Gradle khó phân biệt task nào chịu trách nhiệm cho output, nên kiểm tra stale output và caching bị ảnh hưởng.

### 6.3. Overlap không chỉ khi path y hệt

Ví dụ:
- Task A khai `@OutputDirectory` = `build/reports`.
- Task B khai `@OutputFile` = `build/reports/quality/result.json`.
- Task C khai `@OutputDirectory` = `build/reports/quality`.

Cả ba vùng chồng lấn theo quan hệ **cha–con**. Ngay cả khi A trên thực tế chỉ sinh một file riêng, việc khai output quá rộng khiến Gradle xem phạm vi sở hữu lớn hơn cần thiết.

**Sai lầm rất phổ biến:** Task sinh một file duy nhất nhưng khai `build/` hoặc `build/reports/` làm toàn bộ `@OutputDirectory`, trong khi các task khác cũng ghi vào đó. Với một file output duy nhất, thường nên dùng **`@OutputFile` trỏ đúng file**, hoặc cho task một subdirectory riêng độc quyền.

### 6.4. Hậu quả không chỉ là ghi đè

Tài liệu Gradle về build cache nhấn mạnh: output overlap làm khó xác định output thuộc task nào, không thể dọn file cũ an toàn và **output caching tự động bị vô hiệu hóa đối với trường hợp các task có output directory chồng lấn**. Ngoài ra:
- Task có thể chạy lại vì thấy output directory thay đổi bởi task khác.
- Task có thể bị đánh dấu không up-to-date dù chính input của nó không đổi.
- Task song song có thể ghi/xóa cùng vùng.
- Một bản build chạy được trên máy bạn vẫn có thể không ổn định trên CI.
- `clean` có thể tạm che triệu chứng nhưng không sửa hợp đồng ownership.

Không nên khẳng định **mọi** overlap đều luôn ném một exception giống nhau ở mọi Gradle version. Kiểm tra `--info`, build scan nếu có và output declarations để xác định loại conflict.

## 7. Cách thiết kế output không chồng lấn

### 7.1. Một task — một file hoặc một thư mục con riêng

**Nên:**

~~~text
build/
├── generated/
│   ├── api/
│   │   └── api.json             <-- task generateApi sở hữu
│   └── docs/
│       └── docs.json            <-- task generateDocs sở hữu
└── staged/
    └── bundle/                  <-- task assembleBundle sở hữu
        ├── api.json
        └── docs.json
~~~

Mỗi task tạo nguồn có output riêng. Một task khác **tiêu thụ** output của chúng và ghi vào một vùng staging khác. Không task nào sửa output mà task khác tuyên bố sở hữu.

### 7.2. Ghép đầu ra bằng task riêng

~~~groovy
def generateApi = tasks.named('generateApi')
def generateDocs = tasks.named('generateDocs')

tasks.register('stageBundle', Sync) {
    from(generateApi)
    from(generateDocs)
    into(layout.buildDirectory.dir('staged/bundle'))
}
~~~

Đây là **snippet mô tả pattern**, chỉ chạy khi project đã có `generateApi` và `generateDocs` khai đúng output. `from(TaskProvider)` lấy output của producer và Gradle có thể suy ra quan hệ task dependency. Destination của `stageBundle` phải **không nằm trong** output directory do producer sở hữu.

**Chú ý trùng basename:** Nếu cả producer cùng sinh `report.txt`, `Sync` có thể gặp trùng đường dẫn trong staging. Hãy đặt tên output khác nhau hoặc cấu hình đường dẫn/subdirectory/duplicate strategy có chủ đích; **duplicate strategy không sửa được việc hai producer cùng sở hữu một vùng nguồn**.

### 7.3. `Copy` khác `Sync`

| Task type | Công việc | Cảnh báo |
| --- | --- | --- |
| `Copy` | Sao chép các file từ nguồn đến destination | Nếu hai task copy cùng destination, file có thể bị ghi đè; không biến shared directory thành vùng an toàn |
| `Sync` | Sao chép rồi loại các file đích không thuộc nguồn, để destination khớp tập nguồn | Chỉ dùng cho **directory riêng mà một task hoàn toàn sở hữu**; không sync chung vào source hoặc thư mục của task khác |
| `Delete` | Xóa file/directory được chỉ định | Phải chỉ đúng vùng cần xóa; không xóa thư mục nguồn hoặc output chung bừa bãi |

Nếu muốn gộp nhiều nguồn, thường dùng **một** `Copy`/`Sync` task với nhiều `from(...)` thay vì hai task cạnh tranh cùng destination.

### 7.4. Đừng khai báo output quá rộng để “cho tiện”

**Không nên:**

~~~groovy
outputs.dir(layout.buildDirectory)
~~~

Dòng này khai **toàn bộ build directory** làm output của một task, dễ chồng với `classes`, `test-results`, `libs` và nhiều task khác.

**Nên:** Nếu task sinh một file, khai `outputs.file(layout.buildDirectory.file('reports/custom.txt'))`. Nếu sinh nhiều file độc quyền, khai một subdirectory riêng như `outputs.dir(layout.buildDirectory.dir('generated/custom'))`. Độ rộng của output declaration phải đúng với vùng task thực sự sở hữu.

## 8. Bài thực hành hoàn chỉnh: hai producer an toàn và một Sync task để gộp

Bài này dùng **Groovy DSL + Java 17 standard-library APIs**, không cần plugin bên ngoài hoặc thư viện runtime. Chúng ta sinh hai report văn bản từ một resource, sau đó stage chúng vào thư mục chung **do một task Sync duy nhất sở hữu**.

### 8.1. Tạo cấu trúc

~~~text
resource-ownership-lab/
├── settings.gradle
├── build.gradle
├── data/
│   └── message.txt
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Nếu chưa có Wrapper, dùng Gradle đã cài để chạy `gradle wrapper` một lần, sau đó lưu bộ Wrapper trong version control. Build cần JDK 17+ để chạy mã action sử dụng `Files.readString`/`Files.writeString`.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'resource-ownership-lab'
~~~

**`data/message.txt`** (UTF-8):

~~~text
Hello Gradle
~~~

### 8.2. `build.gradle` — toàn bộ script

~~~groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files

import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id 'base'
}

abstract class RenderResource extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    abstract RegularFileProperty getSourceFile()

    @Input
    abstract Property<String> getLabel()

    @OutputFile
    abstract RegularFileProperty getDestinationFile()

    @TaskAction
    void render() {
        String sourceText = Files.readString(
            sourceFile.get().asFile.toPath(),
            StandardCharsets.UTF_8
        ).strip()

        String result = label.get() + ': ' + sourceText + '\n'
        def target = destinationFile.get().asFile.toPath()

        Files.createDirectories(target.getParent())
        Files.writeString(target, result, StandardCharsets.UTF_8)

        println 'created=' + target.getFileName()
    }
}

def alpha = tasks.register('reportAlpha', RenderResource) {
    group = 'documentation'
    description = 'Sinh report Alpha ở thư mục riêng'

    sourceFile.set(layout.projectDirectory.file('data/message.txt'))
    label.set('alpha')
    destinationFile.set(
        layout.buildDirectory.file('generated/alpha/report-alpha.txt')
    )
}

def beta = tasks.register('reportBeta', RenderResource) {
    group = 'documentation'
    description = 'Sinh report Beta ở thư mục riêng'

    sourceFile.set(layout.projectDirectory.file('data/message.txt'))
    label.set('beta')
    destinationFile.set(
        layout.buildDirectory.file('generated/beta/report-beta.txt')
    )
}

def staging = tasks.register('stageReports', Sync) {
    group = 'distribution'
    description = 'Gom kết quả vào một staging directory riêng'

    from(alpha)
    from(beta)
    into(layout.buildDirectory.dir('staged/reports'))
}

tasks.named('assemble') {
    dependsOn staging
}
~~~

### 8.3. Phân tích hợp đồng task

- `RenderResource` là một **typed custom task** có action `@TaskAction`, không ghi file khi Gradle đang cấu hình build.
- `@InputFile` mô tả nguồn `data/message.txt`; `@PathSensitive(NONE)` hợp lý ở đây vì output chỉ sử dụng **nội dung source**, không sử dụng tên/path của file.
- `@Input` cho `label`: Alpha và Beta có cùng source nhưng output khác vì `label` khác, nên Gradle phải theo dõi nó.
- `@OutputFile` chỉ đích danh output của mỗi producer, không nhận toàn bộ `build/` hoặc shared `staged/`.
- Hai destination khác nhau: `build/generated/alpha/report-alpha.txt` và `build/generated/beta/report-beta.txt`.
- `Sync` lấy `from(alpha)`/`from(beta)` nên tiêu thụ các **task outputs** do Gradle quản lý. Task staging là **chủ sở hữu duy nhất** của `build/staged/reports`.
- `assemble` là lifecycle task; nối vào `stageReports` để lệnh `assemble` cũng tạo thư mục staging.
- Kết quả dùng UTF-8 rõ ràng, LF ở cuối. Không đọc username, absolute path, thời gian, env hoặc dữ liệu ngầm.

**Một điểm tinh tế:** Class `RenderResource` **không đánh dấu `@CacheableTask`**, nên task không được hứa là có build-cache reuse; dù vậy, khai input/output đúng vẫn giúp Gradle thực hiện up-to-date check. Chỉ opt-in caching khi kiểm chứng task phù hợp hợp đồng cache, không có phụ thuộc ngầm và kết quả thực sự tái lập.

### 8.4. Chạy và kiểm tra

~~~bash
./gradlew tasks --all
./gradlew assemble --dry-run
./gradlew clean assemble --quiet
~~~

Trong lần **task actions thật sự chạy** (chưa up-to-date), sẽ có hai dòng do producer in:

~~~text
created=report-alpha.txt
created=report-beta.txt
~~~

**Thứ tự hai dòng không phải cam kết**: Alpha và Beta là hai nhánh producer độc lập, Gradle có thể chọn thứ tự khác. `Sync` không in thêm dòng trong ví dụ. `--quiet` giảm log Gradle, vẫn cho phép `println` của task hiển thị.

Các file kỳ vọng:

| File | Nội dung text UTF-8 |
| --- | --- |
| `build/generated/alpha/report-alpha.txt` | `alpha: Hello Gradle` + LF |
| `build/generated/beta/report-beta.txt` | `beta: Hello Gradle` + LF |
| `build/staged/reports/report-alpha.txt` | Bản sao Alpha |
| `build/staged/reports/report-beta.txt` | Bản sao Beta |

Nếu mở file bằng text editor, bạn thấy:

**`report-alpha.txt`**

~~~text
alpha: Hello Gradle
~~~

**`report-beta.txt`**

~~~text
beta: Hello Gradle
~~~

Không có file nào tên `report.txt` dùng chung giữa hai producer, và stage không ghi trở lại đường dẫn output của producer.

### 8.5. Kiểm nghiệm incremental behavior

~~~bash
./gradlew assemble --info
./gradlew reportAlpha --info
./gradlew reportBeta --info
~~~

Nếu không đổi source, label, output và không có yếu tố khác buộc chạy lại, các producer có thể báo `UP-TO-DATE`. Task `Sync` cũng có thể up-to-date nếu các nguồn/đích của nó không đổi. **Không được coi việc không in lại `created=...` là lỗi**.

Đổi `data/message.txt` thành:

~~~text
Hello from Gradle
~~~

Rồi chạy `./gradlew assemble`. Vì `sourceFile` đã được khai là input, hai task producer cần cập nhật hoặc lấy đúng kết quả tương ứng. Task stage nhận outputs mới qua quan hệ dependency và cập nhật bản sao ở destination.

### 8.6. Thử thêm file lạ vào staging

Sau khi build, tạo thêm file **`build/staged/reports/old.txt`**, rồi chạy:

~~~bash
./gradlew stageReports
~~~

`Sync` bảo đảm destination phản ánh tập nguồn. Vì `old.txt` **không thuộc output do alpha/beta cung cấp**, nó sẽ bị xóa khi sync được thực hiện. Đây là hành vi chủ đích của `Sync` và lý do không nên trỏ `Sync` vào một folder có output do task khác sở hữu.

Để thử **không phá dữ liệu quan trọng**, chỉ tạo `old.txt` bên trong thư mục build/staging của bài thực hành. Không dùng source directory hoặc home folder làm destination của `Sync`.

## 9. Tệp tài nguyên Java: phối hợp với `processResources`

Trong project Java thông thường:

~~~text
src/main/resources/
└── app.properties

build/resources/main/
└── app.properties
~~~

Java plugin tạo task `processResources` để lấy resources từ source set và tạo output dưới build directory. **Không nên** tự có một task thứ hai ghi trực tiếp `build/resources/main/app.properties`, bởi task `processResources` vốn sở hữu vùng output đó.

### 9.1. Thêm resource vào process đúng cách

Nếu có thêm folder `extra-resources` trong project, đoạn sau có thể **thêm vào `build.gradle` có Java plugin**:

~~~groovy
plugins {
    id 'java'
}

tasks.named('processResources', Copy) {
    from(layout.projectDirectory.dir('extra-resources'))
}
~~~

Đây là **script ví dụ** áp dụng Java plugin, sau đó cấu hình `processResources` — **cùng task đang sở hữu destination**. Bạn không tạo thêm một task cạnh tranh để copy vào `build/resources/main`.

Lưu ý: nếu `extra-resources` có cùng đường dẫn resource với `src/main/resources`, phải chủ động quyết định xử lý duplicates; Gradle có thể báo lỗi duplicate tùy cấu hình. Không dùng `duplicatesStrategy = INCLUDE` một cách mù quáng để che hai cấu hình sinh cùng resource.

### 9.2. Nếu resource phải được sinh từ mã

Mô hình đúng:

~~~text
generateResources (output: build/generated/resources/main)
          |
          v
processResources (input: generated resource directory + src/main/resources)
          |
          v
build/resources/main   (output do processResources quản lý)
~~~

Tạo một task `GenerateResources` với `@OutputDirectory DirectoryProperty` riêng; sau đó **kết nối output TaskProvider** vào source/CopySpec của `processResources` hoặc source set theo Gradle API, thay vì ghi trực tiếp vào `src/main/resources` hay `build/resources/main`.

Ví dụ **chỉ là đoạn wiring**, giả định `generateResources` đã được đăng ký và khai báo output directory đúng:

~~~groovy
tasks.named('processResources', Copy) {
    from(tasks.named('generateResources'))
}
~~~

`from(TaskProvider)` cho phép Gradle xác định output producer và quan hệ task dependency. Với generator sinh nhiều output types hoặc CopySpec phức tạp, cần kiểm tra task outputs thực tế, đường dẫn relative, duplicates và nội dung cuối. Đừng dùng `doLast` để sửa resource của `processResources` sau khi task đó hoàn tất.

### 9.3. Sinh Java source cũng tuân theo cùng quy tắc

Nếu task tạo mã Java, không ghi vào `src/main/java`. Tạo source dưới `build/generated/sources/...` với `@OutputDirectory` riêng, nối TaskProvider vào `sourceSets.main.java.srcDir(...)` theo API phù hợp. `compileJava` cần biết dependency vào producer và nhận folder chứa source được sinh.

**Kinh nghiệm:** “Generated source/resource” là output của generator, sau đó **trở thành input của compiler/resource processor**; nó không phải file thứ hai được một task khác tùy tiện chỉnh sửa.

## 10. Các tình huống khó trong multi-project và CI

### 10.1. Root và subprojects cùng ghi vào một file

**Sai:**

~~~groovy
// Trong nhiều subproject, tất cả đều chọn cùng một output tuyệt đối:
def shared = rootProject.layout.buildDirectory.file('reports/report.txt')
~~~

Nếu mỗi subproject đăng ký task ghi vào `shared`, task output của chúng chồng lấn. Thứ tự hay số lượng subproject có thể thay đổi giữa build local/CI.

**Đúng hướng:** Mỗi subproject tạo `layout.buildDirectory.file('reports/module-report.txt')` của chính nó, rồi tạo một **aggregator ở root** có input là TaskProvider/output của từng project và output root riêng, chẳng hạn `root/build/aggregated-reports`.

### 10.2. Hai task không cùng tên vẫn có thể overlap

`:app:generateA` và `:core:generateB` là hai task path khác nhau, nhưng nếu cùng ghi `/tmp/reports/output.json` hoặc một shared folder thì vẫn conflict. Gradle không bảo đảm task path khác nhau đồng nghĩa output filesystem khác nhau.

### 10.3. CI checkout khác root path

Máy local có checkout dưới `/home/dev/project`, CI có `/agent/_work/123/project`. Task dùng `layout.projectDirectory.file('config/input.txt')` thường không cần sửa build script khi đổi root. Tuy nhiên:

- Nếu action in absolute path vào artifact, output không còn giống nhau.
- Nếu fingerprint tính absolute path, cache reuse giữa checkout có thể giảm.
- Nếu tool ngoài đọc biến môi trường hoặc JDK version ảnh hưởng output, phải khai báo yếu tố đó hoặc dùng toolchain/tool version ổn định.
- Nếu thư mục ngoài project được dùng làm input, hãy coi nó là **dependency bên ngoài thực sự**, không dùng giả định rằng mọi CI agent đều có giống nhau.

### 10.4. Symlink và filesystem khác OS

Tính di động không chỉ là thay `\` bằng `/`. Symlinks, case-sensitive vs case-insensitive filesystem, permissions, line endings và thứ tự duyệt directory có thể thay đổi. Với task tạo danh sách files, cần **sort theo relative path ổn định**; với text output, dùng encoding/line endings tường minh nếu định dạng cho phép. Nếu kết quả phụ thuộc symlink target hoặc quyền file, phải kiểm tra/khai báo hành vi phù hợp.

### 10.5. Gradle chạy song song

~~~bash
./gradlew assemble --parallel --info
~~~

Lệnh này không “tạo” bug overlap, mà khiến các rủi ro task độc lập cùng ghi một vùng dễ lộ. **Không chữa bằng cách tắt `--parallel`** nếu cấu hình output vẫn sai. Quan hệ `mustRunAfter` hoặc `dependsOn` có thể áp thứ tự nhưng **không biến hai task cùng output thành hai chủ sở hữu an toàn**. Sửa ownership mới là giải pháp nền tảng.

## 11. Đọc trạng thái để chẩn đoán

| Hiện tượng | Cách hiểu đúng |
| --- | --- |
| `UP-TO-DATE` | Gradle nhận thấy input/output không thay đổi theo khai báo, có thể bỏ qua action |
| `FROM-CACHE` | Output lấy từ build cache phù hợp, action không cần chạy |
| `NO-SOURCE` | Không có nguồn phù hợp cho task kiểu source |
| `SKIPPED` | Task bỏ qua do điều kiện/đường chạy hoặc `--dry-run` |
| `FAILED` | Một task thất bại; cần đọc nguyên nhân và task path |
| `BUILD SUCCESSFUL` | Đồ thị được yêu cầu hoàn tất; không chứng minh mọi output độc lập hay có cache |

Lệnh điều tra:

~~~bash
./gradlew tasks --all
./gradlew assemble --dry-run
./gradlew assemble --info
./gradlew clean assemble --info
./gradlew assemble --build-cache --info
./gradlew assemble --configuration-cache
~~~

**Cách diễn giải:**
1. `--dry-run` xem task graph nhưng **không** chạy tác vụ ghi file.
2. `--info` giúp thấy lý do task chạy hoặc bỏ qua, input/output và cache trạng thái theo mức Gradle hỗ trợ.
3. `clean` xóa output của project (theo cấu hình), **không** giải quyết overlap hoặc missing input.
4. `--build-cache` bật dùng output cache, không đảm bảo mọi task cache được. `Copy`/`Sync` là loại thao tác I/O thường không đem lại lợi ích khi lưu vào build cache, và không cacheable mặc định.
5. `--configuration-cache` thử khả năng reuse phần configuration, tách biệt với output caching.

Đặc biệt, nếu task hiện `NOT-CACHEABLE`/`Caching disabled` hoặc không thấy `FROM-CACHE`, hãy kiểm tra task type, input/output declarations và **overlap** trước khi nghĩ đến xóa cache.

## 12. Checklist trước khi đưa custom task vào CI

### A. Đường dẫn

- [ ] Không hard-code thư mục home, workspace CI, drive letter hoặc absolute checkout path nếu không phải yêu cầu nghiệp vụ.
- [ ] Input được cấp qua `layout.projectDirectory` hoặc typed property; output qua `layout.buildDirectory`.
- [ ] Không dùng working directory của JVM (`new File('...')`, `user.dir`) để suy ra root project/subproject.
- [ ] Các file input có `@PathSensitive` phù hợp với ý nghĩa path trong output; không khai `NONE` khi output phụ thuộc tên/path.
- [ ] Tên file do user cấp được kiểm tra; không cho `..`/absolute path thoát output root theo ngoài ý muốn.

### B. Tác dụng phụ

- [ ] Không ghi file, gọi mạng, sửa VCS/source hoặc đổi dữ liệu ngoài hệ thống trong configuration block.
- [ ] Action của task dùng typed properties và tránh truy cập `Project` không tương thích configuration cache.
- [ ] Tất cả file/giá trị/env/tool version ảnh hưởng output đã được mô tả như input.
- [ ] File task tạo được khai đúng output và nằm trong build directory hoặc vùng được cấu hình an toàn.
- [ ] Không ghi trực tiếp vào `src/main/resources`, `src/main/java` hay output do plugin khác sở hữu.
- [ ] Task publish/deploy có ranh giới riêng, không đưa thành side effect ẩn trong `build`.

### C. Ownership và reuse

- [ ] Mỗi file output có **một task sở hữu**; không có hai task cùng destination.
- [ ] Nếu dùng `@OutputDirectory`, directory đó đủ hẹp và độc quyền.
- [ ] Không có output directory là cha của output task khác.
- [ ] `Sync` chỉ thao tác trên destination mà **chính task đó sở hữu hoàn toàn**.
- [ ] Producer → consumer được nối qua TaskProvider/output provider để Gradle suy ra dependency.
- [ ] Multi-project không cùng ghi vào root global report; có aggregator riêng nếu cần.
- [ ] Chạy hai lần để kiểm tra up-to-date; chạy ở checkout khác/cache khi cần kiểm tra relocatability.

## 13. Bài tập có đáp án

### Bài 1. Hard-coded path

Một task có `from('/home/alice/project/assets')` và `into('C:/dist')`. Vì sao không portable?

**Đáp án:** Nó phụ thuộc thư mục/OS của hai máy cụ thể. Dùng `layout.projectDirectory.dir('assets')` và `layout.buildDirectory.dir('dist')` hoặc output property có thể cấu hình rõ ràng.

### Bài 2. Task nào sở hữu output?

Task A khai `@OutputDirectory` là `build/reports`, Task B khai `@OutputFile` là `build/reports/check.json`. Hai output có chồng lấn không?

**Đáp án:** Có, vì `check.json` nằm trong output directory A tuyên bố sở hữu. Thu hẹp A vào subdirectory riêng hoặc khai đúng output file; không để hai vùng giao nhau.

### Bài 3. `Sync` có xóa file bất ngờ không?

Task `prepareA` tạo `build/stage/a.txt`; task `prepareB` dùng `Sync` từ nguồn chỉ có `b.txt` vào `build/stage`. Có thể mất `a.txt` không?

**Đáp án:** Có. `Sync` xóa những file đích không thuộc source set. Sửa bằng cách cho hai producer output riêng, task `Sync` thứ ba tổng hợp từ cả hai vào một destination độc quyền.

### Bài 4. Configuration time hay execution time?

~~~groovy
tasks.register('makeMarker') {
    file('build/marker.txt').text = 'MARKER'
}
~~~

Mã ghi file chạy khi nào?

**Đáp án:** Khi configuration closure của `makeMarker` được thực hiện (task được realize/configure), **không** phải action khi task thực thi. Cần đưa logic sang `@TaskAction` hoặc `doLast` và khai báo output.

### Bài 5. Biến môi trường ẩn

Task tạo artifact từ `System.getenv('REPORT_MODE')` nhưng không khai input. Điều gì có thể sai?

**Đáp án:** Đổi `REPORT_MODE` có thể không làm fingerprint task thay đổi, dẫn đến output cũ được dùng lại. Nên nối `providers.environmentVariable('REPORT_MODE')` vào task property `@Input`.

### Bài 6. PathSensitivity

Task tạo sitemap có link `guide/start.md` và `api/start.md`. Dùng `@PathSensitive(NONE)` có phù hợp không?

**Đáp án:** Không nếu tên/path có trong output. Dùng `RELATIVE` và sinh logical paths ổn định, tránh absolute checkout path.

### Bài 7. Hai task producer chạy theo thứ tự nào?

Trong bài thực hành, `reportAlpha` và `reportBeta` không phụ thuộc lẫn nhau. `./gradlew stageReports` có luôn in Alpha rồi Beta không?

**Đáp án:** Không có ràng buộc thứ tự trực tiếp giữa hai producer. Chỉ chắc cả hai phải hoàn thành (hoặc output hợp lệ được reuse) để `stageReports` có thể tổng hợp. Không viết test dựa vào thứ tự log của hai task độc lập.

### Bài 8. Tài nguyên Java

Bạn muốn sinh `config.properties` từ project version. Nên ghi thẳng vào `src/main/resources` hay `build/resources/main`?

**Đáp án:** Không nên. Sinh vào output directory riêng dưới `build/generated/resources/...`, khai `@OutputDirectory`/`@OutputFile`, nối task producer vào `processResources` hoặc source set để output sinh ra được tiêu thụ đúng.

### Bài 9. Cache miss dù file giống nhau

Local checkout `/users/dev/app` và CI checkout `/workspace/ci/app` cùng source. Task nhận input giống bytes nhưng fingerprint hoặc output khác. Cần điều tra gì?

**Đáp án:** Absolute paths trong input normalization/output, tool/JDK version, env, timestamp, file ordering, encoding, output declarations và shared build cache. Không dùng `@PathSensitive(NONE)` mù quáng nếu task thực sự phụ thuộc path.

### Bài 10. Output không thay đổi nhưng task cứ chạy lại

Task A khai `outputs.dir(layout.buildDirectory)`, trong khi nhiều task khác ghi vào `build/`. Vì sao?

**Đáp án:** A tuyên bố sở hữu cả build directory nên thay đổi do task khác có thể khiến A không còn up-to-date. Thu hẹp output tới file/subdirectory A thật sự tạo ra.

**Tiêu chí hoàn thành:** Bạn có thể giải thích “vị trí input/output ở đâu, ai sở hữu, khi nào action chạy, những input nào được snapshot, vì sao cache có/không dùng lại được”; đồng thời sửa một thiết kế hai task cùng ghi output thành mô hình producer độc lập và một consumer/staging task duy nhất.

## 14. Nguồn chính thức để đối chiếu

- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): Project Layout, Copy, Sync, file collections và đường dẫn trong build script.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): dùng file/output directory riêng cho từng task và tránh overlap.
- [Gradle — Build Cache: Important Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): overlapping outputs, cache correctness, tái sử dụng output.
- [Gradle — Common Caching Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html): side effects, volatile/undeclared input, overlapping output, task cấu hình task khác.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_builds.html): khai input/output và nối dependency bằng TaskProvider.
- [Gradle — Task Output Caching](https://docs.gradle.org/current/userguide/build_cache.html): điều kiện cacheable và giới hạn build cache.
- [Gradle — Writing Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html): custom task type, typed properties, `@TaskAction`.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): tránh truy cập Project trong task action và side effects cấu hình.
