# Sao chép bằng Copy, đồng bộ bằng Sync và xóa bằng Delete trong Gradle

## 1. Hiểu đúng ba thao tác trên file và tài nguyên

Trong dự án Java hoặc các ứng dụng khác dùng Gradle, việc build không chỉ gồm biên dịch mã. Ta còn cần gom tài liệu, sao chép tài nguyên, tạo thư mục staging cho bản phát hành, làm mới bản phân phối và dọn output không cần giữ lại. Gradle có ba task tích hợp sẵn thường được dùng cho việc này: `Copy`, `Sync` và `Delete`.

- **`Copy`** sao chép những file phù hợp từ nguồn sang đích. Nó không có nhiệm vụ xóa tất cả file cũ chỉ có trong thư mục đích.
- **`Sync`** sao chép theo bộ quy tắc tương tự `Copy`, sau đó làm cho thư mục đích phản ánh bộ file được đồng bộ: những file thừa trong đích có thể bị xóa.
- **`Delete`** xóa những file/thư mục được chỉ định. Nó không phải task sao chép; không cần cặp `from`–`into`.

Hãy hình dung file nguồn có `a.txt` và `b.txt`, còn thư mục đích ban đầu có `a.txt` và `old.txt`:

```text
Nguồn: [a.txt, b.txt]               Đích trước: [a.txt, old.txt]

Copy -> [a.txt, b.txt, old.txt]      (giữ file dư)
Sync -> [a.txt, b.txt]               (loại file dư)
Delete(đích) -> [không còn thư mục]  (xóa mục tiêu)
```

Mô hình minh họa giả định hai file nguồn đều được bộ lọc chọn, các task thực thi thành công và không có quy tắc đặc biệt can thiệp. Ý nghĩa của `Sync` và `Delete` khiến **đường dẫn đích trở thành quyết định an toàn quan trọng nhất**. Nên giới hạn chúng vào những thư mục output có thể tái tạo, chẳng hạn một nhánh riêng dưới `build/`.

## 2. Bảng so sánh để chọn đúng task

| Tiêu chí | `Copy` | `Sync` | `Delete` |
| --- | --- | --- | --- |
| Nhiệm vụ | Sao chép/cập nhật file | Đồng bộ nội dung thư mục đích | Xóa đường dẫn mục tiêu |
| Khai báo đầu vào | `from(...)` | `from(...)` | Không dùng `from` theo mô hình copy |
| Khai báo nơi tác động | `into(...)` | `into(...)` | `delete(...)` |
| Dùng `include`/`exclude` | Có, qua `CopySpec` | Có, qua `CopySpec` | Không dùng cùng cơ chế CopySpec |
| File chỉ có ở đích | Thường giữ nguyên | Có thể bị loại bỏ | Bị xóa nếu nằm trong mục tiêu |
| File nguồn trùng tên file đích | Có thể thay thế bản ở đích | Có thể thay thế bản ở đích | Không liên quan |
| Rủi ro chính | Ghi đè file, giữ file lỗi thời | Xóa dữ liệu không thuộc tập đồng bộ | Xóa nhầm cả cây thư mục |
| Trường hợp sử dụng | Gom tài liệu/assets vào staging | Chuẩn bị bản mirror phát hành nhất quán | Dọn một thư mục sinh tự động |

**Không nhầm:** `Copy` “không xóa file thừa” không có nghĩa “không ghi đè file cùng tên”. File nguồn có đường dẫn trùng một file tại đích vẫn có thể cập nhật nội dung của file đích.

`Sync` **không phải** công cụ đồng bộ hai chiều như dịch vụ đồng bộ tài liệu: nó lấy **nguồn đã khai báo** làm trạng thái mong muốn của đích. File người dùng sửa trực tiếp trong đích không tự được gửi ngược về nguồn.

## 3. CopySpec: mô hình chung của Copy và Sync

Task `Copy` và `Sync` nhận tập quy tắc sao chép thông qua **`CopySpec`**. Bạn sẽ thường gặp:

| API | Tác dụng |
| --- | --- |
| `from(source)` | Đặt nguồn là file, thư mục, file collection hoặc nguồn được Gradle hỗ trợ |
| `into(destination)` | Đặt vị trí thư mục đích |
| `include('**/*.txt')` | Chọn những file có đường dẫn khớp pattern |
| `exclude('**/draft-*')` | Loại file khớp pattern khỏi bộ file được chọn |
| `rename { name -> ... }` | Đổi tên **bản sao** khi đưa vào đích |
| `eachFile { details -> ... }` | Điều chỉnh cách xử lý từng file |
| `duplicatesStrategy` | Chọn cách xử lý nhiều nguồn cùng ánh xạ vào một đường dẫn đích |
| `filter` / `expand` | Tùy chọn biến đổi nội dung văn bản khi sao chép |

Các pattern thường có ý nghĩa kiểu Ant, không phải regex chung. `**/*.txt` dùng để chọn file `.txt` ở nhiều cấp thư mục. Nguồn là một **thư mục** thì việc copy theo quy ước đưa **nội dung bên trong** thư mục đó vào đích, giữ đường dẫn tương đối nếu không cấu hình đổi tên/chuyển đường dẫn.

Ví dụ:

```groovy
tasks.register('copyText', Copy) {
    from('src/handouts') {
        include '**/*.txt'
        exclude '**/draft-*'
    }
    into(layout.buildDirectory.dir('text'))
}
```

Với `src/handouts/hello.txt` và `src/handouts/notes/steps.txt`, hai file được copy lần lượt thành `build/text/hello.txt` và `build/text/notes/steps.txt`. Nếu có thêm `draft-work.txt`, file này bị loại bởi `exclude` dù có phần mở rộng `.txt`.

Các quy tắc có thể lồng nhau. Một task có nhiều `from`, mỗi nguồn có `include`, `exclude` hoặc `into` con riêng. `into` ở mức task đặt gốc đích; `into` bên trong một khối `from` chỉ điều chỉnh nhóm file thuộc khối ấy.

## 4. Bài thực hành đầy đủ, an toàn và có thể chạy

Ví dụ này dùng **Gradle Groovy DSL**, chỉ tạo output dưới `build/lab/`. Không cần JDK riêng để biên dịch mã Java, vì ba task xử lý file là chức năng của Gradle. Máy vẫn cần JVM và một phiên bản Gradle tương thích để chạy Gradle/Wrapper.

### 4.1. Cây file đầu vào

```text
file-task-lab/
├── settings.gradle
├── build.gradle
└── src/
    └── handouts/
        ├── welcome.txt
        ├── draft-work.txt
        └── notes/
            └── steps.txt
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'file-task-lab'
```

**File `src/handouts/welcome.txt`:**

```text
Welcome to Gradle file tasks.
```

**File `src/handouts/notes/steps.txt`:**

```text
1. Copy
2. Sync
3. Delete
```

**File `src/handouts/draft-work.txt`:**

```text
This draft should not be distributed.
```

**File `build.gradle` — toàn bộ:**

```groovy
import org.gradle.api.file.DuplicatesStrategy

plugins {
    id 'base'
}

def handouts = layout.projectDirectory.dir('src/handouts')
def copiedDir = layout.buildDirectory.dir('lab/copied')
def syncedDir = layout.buildDirectory.dir('lab/synced')

// Task Copy: không dọn file thừa đã có trong thư mục đích.
tasks.register('copyHandouts', Copy) {
    group = 'learning'
    description = 'Sao chep cac handout hop le'

    from(handouts) {
        include '**/*.txt'
        exclude '**/draft-*'
    }

    into(copiedDir)
    duplicatesStrategy = DuplicatesStrategy.FAIL
}

// Task Sync: đồng bộ một đích riêng, được phép loại file dư.
tasks.register('syncHandouts', Sync) {
    group = 'learning'
    description = 'Dong bo ban mirror handout'

    from(handouts) {
        include '**/*.txt'
        exclude '**/draft-*'
    }

    into(syncedDir)
    duplicatesStrategy = DuplicatesStrategy.FAIL
}

// Task Delete: xóa đúng một nhánh output, không xóa source.
tasks.register('deleteCopiedDir', Delete) {
    group = 'learning'
    description = 'Xoa build/lab/copied'

    delete(copiedDir)
}

// Task tổng hợp: yêu cầu Copy và Sync, không yêu cầu Delete.
tasks.register('prepareHandouts') {
    group = 'learning'

    dependsOn(
        tasks.named('copyHandouts'),
        tasks.named('syncHandouts')
    )

    doLast {
        println '[DONE] Handouts prepared'
    }
}
```

Lựa chọn này có chủ đích:

1. `src/handouts` là đầu vào do người phát triển quản lý. Không task nào ghi hoặc xóa nó.
2. `copiedDir` và `syncedDir` khác nhau. Hai task không tranh quyền quản lý cùng một thư mục output.
3. `deleteCopiedDir` chỉ xóa `build/lab/copied`. Nó không phải dependency của `prepareHandouts`.
4. `DuplicatesStrategy.FAIL` báo lỗi nếu có hai file nguồn trùng đường dẫn đích trong cùng thao tác copy.
5. Plugin `base` cung cấp task `clean` để dọn build output chung, nhưng ta còn có Delete chuyên dụng để so sánh phạm vi.

### 4.2. Chạy bằng Gradle Wrapper

Nếu project đã có Gradle Wrapper, sử dụng nó. Nếu tạo thư mục mới chỉ có các file trên, cần một bản Gradle tương thích cài sẵn để sinh Wrapper lần đầu:

```bash
gradle wrapper
```

Sau khi tạo `gradlew`, `gradlew.bat` và `gradle/wrapper`, trên Linux/macOS:

```bash
./gradlew --console=plain prepareHandouts
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --console=plain prepareHandouts
```

Nếu thành công, dòng do **chính task tổng hợp** in ra là:

```text
[DONE] Handouts prepared
```

Các dòng log Gradle bổ sung như tên task, `UP-TO-DATE` hoặc thời gian xử lý thay đổi theo từng lần chạy. Vì `copyHandouts` và `syncHandouts` là hai dependency độc lập, không nên giả định task nào luôn xuất hiện trước task kia trong log.

Kết quả file mong đợi:

```text
build/
└── lab/
    ├── copied/
    │   ├── welcome.txt
    │   └── notes/
    │       └── steps.txt
    └── synced/
        ├── welcome.txt
        └── notes/
            └── steps.txt
```

`draft-work.txt` không được đưa vào vì quy tắc exclude. Các file `welcome.txt` và `steps.txt` vẫn giữ nội dung gốc.

### 4.3. Thử xem Copy và Sync đối xử với file cũ như thế nào

Thêm một file `old.txt` vào **mỗi đích**, không thêm vào nguồn. Trên Linux/macOS:

```bash
mkdir -p build/lab/copied build/lab/synced
printf 'old\n' > build/lab/copied/old.txt
printf 'old\n' > build/lab/synced/old.txt
./gradlew --console=plain copyHandouts syncHandouts
```

Trên Windows PowerShell, viết hai lệnh tạo thư mục riêng để tránh phụ thuộc cú pháp xuống dòng:

```powershell
New-Item -ItemType Directory -Force build/lab/copied | Out-Null
New-Item -ItemType Directory -Force build/lab/synced | Out-Null
Set-Content build/lab/copied/old.txt -Value old
Set-Content build/lab/synced/old.txt -Value old
.\gradlew.bat --console=plain copyHandouts syncHandouts
```

Sau khi các task thực sự xử lý thành công:

| Đường dẫn | Kỳ vọng | Giải thích |
| --- | --- | --- |
| `build/lab/copied/old.txt` | Còn | Copy không dọn file dư |
| `build/lab/synced/old.txt` | Không còn | Sync loại file không thuộc tập nguồn |
| `build/lab/copied/welcome.txt` | Còn | Nguồn hợp lệ |
| `build/lab/synced/notes/steps.txt` | Còn | Nguồn hợp lệ và giữ đường dẫn tương đối |
| `src/handouts/welcome.txt` | Không đổi | Không task nào ghi vào nguồn |

Có thể tự kiểm tra trên Linux/macOS:

```bash
test -f build/lab/copied/old.txt && echo "Copy kept old.txt"
test ! -e build/lab/synced/old.txt && echo "Sync removed old.txt"
```

Nếu đúng, hai dòng do `echo` in ra là:

```text
Copy kept old.txt
Sync removed old.txt
```

Trên Windows PowerShell:

```powershell
Test-Path build/lab/copied/old.txt
Test-Path build/lab/synced/old.txt
```

Kết quả dự kiến lần lượt là `True` và `False`. Nếu bạn đã tùy chỉnh script, hãy đọc đường dẫn nguồn và đích thực tế trước khi so sánh.

**Đây là khác biệt thực hành quan trọng nhất:** khi yêu cầu “đích chứa đúng tập file vừa chọn”, chọn `Sync` và trao cho nó một thư mục đích chuyên dụng. Nếu chỉ muốn thêm/cập nhật một số file mà không xóa file khác, `Copy` là lựa chọn phù hợp hơn.

### 4.4. Thử task Delete

Chạy riêng:

```bash
./gradlew --console=plain deleteCopiedDir
```

Task sẽ xóa nhánh `build/lab/copied` nếu tồn tại. Nó **không** xóa `build/lab/synced` và **không** xóa `src/handouts`. Chạy `./gradlew prepareHandouts` sau đó có thể tạo lại nhánh copied từ source.

Một lệnh Delete chỉ an toàn vì trong ví dụ **đích chính xác đã được cố định dưới `build/lab/copied`**. Không được suy luận rằng Delete an toàn với bất kỳ file nào chỉ vì lệnh Gradle chạy thành công.

## 5. Copy: nguồn, đích, đường dẫn tương đối và file trùng tên

### 5.1. Nguồn thư mục không bị đưa nguyên tên thư mục vào đích

Ví dụ:

```groovy
tasks.register('copyAssets', Copy) {
    from('src/assets')
    into(layout.buildDirectory.dir('assets'))
}
```

Nếu nguồn chứa `src/assets/icon.svg` và `src/assets/theme/dark.css`, đích thường chứa `build/assets/icon.svg` và `build/assets/theme/dark.css` — không phải `build/assets/src/assets/icon.svg`. Gradle bảo toàn **đường dẫn tương đối dưới source root** nếu không có quy tắc chuyển đường dẫn bổ sung.

Khi `from` nhận trực tiếp một file, tên file đó được dùng ở đích. Khi `from` nhận nhiều nguồn, chúng được gom theo copy specs và có thể va chạm tên đích.

### 5.2. Hai nguồn cùng đường dẫn đích

Giả sử:

```text
src/source-a/config.txt
src/source-b/config.txt
                |
                v
build/combined/config.txt   (xung đột)
```

Nếu khai báo hai nguồn mà không đưa vào thư mục con riêng, cả hai có thể muốn chiếm đường dẫn `config.txt` ở đích. Một số chiến lược:

| `DuplicatesStrategy` | Ý nghĩa |
| --- | --- |
| `FAIL` | Báo lỗi khi có file nguồn trùng đường dẫn đích |
| `EXCLUDE` | Bỏ qua bản trùng xuất hiện sau |
| `INCLUDE` | Cho phép xử lý các bản cùng đường dẫn, kết quả còn phụ thuộc loại đích/thứ tự |
| `WARN` | Cho phép xử lý nhưng có cảnh báo trùng |
| `INHERIT` | Nhận quy tắc từ copy spec cha khi có |

Với thư mục chứa file thực, không thể đồng thời lưu **hai file khác nhau ở cùng một đường dẫn**. Vì vậy nên chọn `FAIL` để phát hiện lỗi, hoặc tách nguồn vào các thư mục con có tên ổn định. `duplicatesStrategy` giải quyết xung đột **giữa các mục được copy**, không phải chính sách xóa file stale từ lần build trước.

### 5.3. Nhiều nguồn và cấu trúc đích con

```groovy
tasks.register('assembleDocs', Copy) {
    from('docs/manual') {
        include '**/*.md'
    }

    from('docs/legal') {
        include 'LICENSE.txt'
        into('legal')
    }

    into(layout.buildDirectory.dir('assembled-docs'))
}
```

File Markdown từ `docs/manual` được đặt dưới gốc `build/assembled-docs`; file `LICENSE.txt` từ `docs/legal` được đặt dưới `build/assembled-docs/legal`. Quy tắc `into('legal')` chỉ áp dụng trong nhánh copy spec của `docs/legal`.

Không nên coi thứ tự viết hai khối `from` là một hợp đồng đủ mạnh để xử lý trùng tên. Nếu hai nguồn có đường dẫn trùng, sửa cấu trúc hoặc đặt chiến lược rõ ràng.

## 6. Sync: nguy cơ xóa dữ liệu và điều kiện sử dụng

Cấu hình Sync tối thiểu:

```groovy
tasks.register('syncPackage', Sync) {
    from('src/distribution') {
        include '**/*.txt'
    }
    into(layout.buildDirectory.dir('distribution-text'))
}
```

Nếu đích có `welcome.txt` và `custom.js`, còn bộ nguồn được lọc chỉ có `welcome.txt`, thao tác Sync có thể xóa `custom.js` ở đích. File đó không phải nguồn do task quản lý, dù có thể một người từng chép nó vào bằng tay.

**Một thư mục Sync phải là vùng output của riêng task**, hoặc phải có quy tắc bảo toàn file đặc biệt được thiết kế và kiểm tra rõ. Không đưa Sync vào một thư mục dùng chung cho:

- nguồn trong `src/main/resources`;
- tài liệu nguồn quản lý bằng Git;
- file người dùng tải lên hoặc chỉnh sửa thủ công;
- dữ liệu ngoài phạm vi project;
- output đang được task khác ghi độc lập.

Nếu nguồn của Sync bị thu hẹp (xóa file nguồn, thay đổi `include`/`exclude`), bản mirror có thể bị thu hẹp tương ứng. Đừng dựa vào giả định “nguồn không có file thì Sync chắc chắn không xóa gì”: điều đúng phải được quyết định từ hợp đồng task và quan sát lần chạy thực tế, không từ suy đoán.

**Sync không đồng bộ hai chiều.** Nó không gửi file xuất hiện ở đích về lại nguồn, không giải quyết conflict và không thay thế cơ chế backup cho dữ liệu người dùng.

### 6.1. Tại sao không nên cho Copy và Sync dùng chung đích?

Giả sử task Copy đưa `preview.txt` vào `build/site`, còn task Sync đưa các file tài liệu khác vào cùng `build/site`. Nếu `preview.txt` không thuộc bộ file nguồn của Sync, lần Sync kế tiếp có thể xóa nó. Kết quả tùy thứ tự hai task, đặc biệt khó dự đoán khi chúng độc lập.

Giải pháp: cho từng task một thư mục output riêng rồi tạo một task lắp ghép kết quả có chủ đích; hoặc chuyển mọi nguồn cần có vào **cùng một Sync task** để nó quản lý trọn bộ file mong muốn.

## 7. Delete: xóa đúng mục tiêu, không tác động vào lúc configuration

Task `Delete` nhận danh sách mục tiêu từ `delete(...)`:

```groovy
tasks.register('removeScratch', Delete) {
    delete(layout.buildDirectory.dir('scratch'))
}
```

Khi chạy `./gradlew removeScratch`, Gradle xóa đường dẫn `build/scratch` được khai báo (cùng các file con nếu nó là thư mục). Nếu đường dẫn không tồn tại, thông thường việc dọn dẹp vẫn hoàn tất mà không cần tạo dữ liệu nguồn.

Có thể xóa nhiều nhánh output rõ ràng:

```groovy
tasks.register('removeTemporaryOutputs', Delete) {
    delete(
        layout.buildDirectory.dir('scratch'),
        layout.buildDirectory.dir('temporary-reports')
    )
}
```

**Ví dụ nguy hiểm — không thực thi:**

```groovy
tasks.register('unsafeDelete', Delete) {
    delete(projectDir)
}
```

`projectDir` là thư mục project chứa source và build script; xóa toàn bộ nó có thể làm mất tài liệu không thể tái tạo. Đoạn trên chỉ để nhận diện lỗi thiết kế, tuyệt đối không thêm task này vào dự án thật.

Không viết công việc xóa ở cấp cao nhất của `build.gradle`:

```groovy
// Không nên: thực hiện ngay khi build script được đánh giá.
delete(layout.buildDirectory.dir('scratch'))
```

Lệnh cấp cao nhất có thể thực hiện ngay cả khi bạn chỉ chạy `help`. Task `Delete` đưa công việc vào giai đoạn xử lý task, chỉ chạy khi được chọn hoặc có quan hệ phụ thuộc phù hợp.

### 7.1. `Delete` chuyên dụng khác `clean`

Với plugin `base` hoặc Java plugin, `clean` thường xóa **toàn bộ thư mục build output được project quản lý**. Ngược lại, `removeScratch` chỉ xóa `build/scratch`. Nếu muốn dọn một nhánh tạm mà không làm mất báo cáo và artifact khác, task Delete có phạm vi hẹp dễ kiểm soát hơn.

Không lưu dữ liệu quan trọng duy nhất bên trong `build`, vì cả `clean` lẫn các task dọn output hợp lệ có thể xóa nội dung đó.

### 7.2. Không chọn Delete và Copy cùng đích mà thiếu quan hệ thứ tự

Nếu chạy một lệnh chọn cả `deleteCopiedDir` và `copyHandouts`, đừng dựa vào thứ tự các tên task trên dòng lệnh để thiết kế kết quả cuối. Hai task độc lập cùng đụng một đường dẫn là một thiết kế dễ lỗi. Khi muốn “xóa rồi sao chép lại”, hãy dùng một chuỗi công việc có quan hệ hợp lệ hoặc lựa chọn `Sync` trong đích chuyên dụng nếu hợp đồng thật là tạo bản mirror.

Một task bị gắn `finalizedBy` để xóa output cũng cần thận trọng: nếu report vừa tạo đã bị xóa ngay sau task chính, người dùng không còn file để kiểm tra.

## 8. Các kỹ thuật CopySpec nâng cao

### 8.1. Đổi tên bản sao bằng `rename`

```groovy
tasks.register('renameHandout', Copy) {
    from('src/handouts') {
        include '**/*.txt'
        exclude '**/draft-*'
        rename { String name ->
            name == 'steps.txt' ? 'guide.txt' : name
        }
    }

    into(layout.buildDirectory.dir('lab/renamed'))
}
```

File nguồn `src/handouts/notes/steps.txt` được sao chép thành `build/lab/renamed/notes/guide.txt`. Thư mục `notes` được giữ; tên file nguồn trong `src` không bị đổi.

Đây cũng là **thư mục đích thứ ba độc lập**, không chồng lấn với `copied` và `synced` trong ví dụ chính.

### 8.2. Can thiệp từng file bằng `eachFile`

```groovy
tasks.register('copyWithDetails', Copy) {
    from('src/handouts') {
        include '**/*.txt'
        exclude '**/draft-*'
        eachFile { details ->
            if (details.name == 'welcome.txt') {
                details.name = 'introduction.txt'
            }
        }
    }

    into(layout.buildDirectory.dir('lab/details'))
}
```

`eachFile` phù hợp khi quyết định dựa trên từng mục, ví dụ đổi tên hoặc đường dẫn tương đối. Nếu chỉ muốn đổi tên đơn giản, `rename` dễ đọc hơn. Chỉ cấu hình một chiến lược rõ ràng khi kết hợp `rename`, `eachFile` và `duplicatesStrategy` vì chúng có thể cùng ảnh hưởng một đường dẫn đích.

### 8.3. Biến đổi nội dung tài nguyên

CopySpec cũng có thể lọc/thay thế nội dung văn bản bằng `filter` hoặc `expand`. Điều này khác với bản sao byte-for-byte: output đã qua biến đổi có thể không còn giống nguồn.

Thực hành an toàn đòi hỏi phân biệt file văn bản và file nhị phân, chỉ rõ encoding khi cần và không nhúng token/mật khẩu thật vào file được đóng gói. Nếu một file mẫu được sinh từ cấu hình, hãy bảo đảm những giá trị cấu hình ảnh hưởng output được Gradle biết đến và xử lý phù hợp.

## 9. Copy và Sync trong quy trình tài nguyên Java

Java plugin đã có sẵn task phục vụ sao chép tài nguyên:

```text
src/main/resources ----> processResources ----> build/resources/main
src/test/resources ----> processTestResources -> build/resources/test
```

Vì thế, với project Java thông thường, không cần tự tạo một task Copy để làm lại toàn bộ hành vi chuẩn của `processResources`. Nếu muốn bổ sung nguồn tài nguyên khác, có thể cấu hình task xử lý resource.

Trong **một project Java riêng**, ví dụ có `shared-resources/labels.txt`:

```groovy
plugins {
    id 'java'
}

tasks.named('processResources', Copy) {
    from('shared-resources') {
        include '**/*.txt'
    }
}
```

Khối này bổ sung các file văn bản từ `shared-resources` vào output resource của `main`; nó không xóa `src/main/resources` theo quy ước. Khi chạy `classes`, resource tương ứng thường nằm ở `build/resources/main/labels.txt`.

Java 17 có thể đọc file đó qua classpath:

**File `src/main/java/demo/ResourceDemo.java`:**

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ResourceDemo {
    private ResourceDemo() {
    }

    public static void main(String[] args) throws IOException {
        try (InputStream in =
                ResourceDemo.class.getResourceAsStream("/labels.txt")) {
            if (in == null) {
                throw new IllegalStateException("Missing labels.txt");
            }
            System.out.println(
                    new String(in.readAllBytes(), StandardCharsets.UTF_8)
                            .strip()
            );
        }
    }
}
```

**File `shared-resources/labels.txt`:**

```text
Gradle resources ready
```

Sau khi cấu hình Java plugin, chuẩn bị JDK 17 phù hợp và dùng Gradle Wrapper:

```bash
./gradlew classes
java -cp "build/classes/java/main:build/resources/main" demo.ResourceDemo
```

Trên Windows PowerShell, ký tự ngăn cách classpath là dấu chấm phẩy:

```powershell
.\gradlew.bat classes
java -cp "build\classes\java\main;build\resources\main" demo.ResourceDemo
```

Stdout do chương trình Java tạo:

```text
Gradle resources ready
```

Cần phân biệt: `processResources` đưa file vào **output của main source set**, còn mã Java đọc theo classpath. Không dựa vào `Path.of("src/main/resources/...")` khi chạy ứng dụng đã đóng gói; resource có thể nằm bên trong JAR.

Không dùng task `Sync` để đồng bộ ngược vào `src/main/resources`. Đó là thư mục **nguồn**, không phải thư mục output do task được phép xóa file thừa. Nếu cần sinh resource, nên tạo trong vùng `build/generated` rồi kết nối đầu ra của task tạo file với `processResources` bằng quan hệ input/output phù hợp.

## 10. Task graph, provider và theo dõi file

Việc khai báo task không tự chạy nó. Khi cấu hình:

```groovy
tasks.register('packageHandouts') {
    dependsOn(tasks.named('copyHandouts'))
    doLast {
        println '[PACKAGE] Copy completed'
    }
}
```

task `packageHandouts` yêu cầu Gradle xử lý `copyHandouts` trước. `dependsOn` mô tả **quan hệ công việc**, nhưng không tự mô tả mọi file consumer sử dụng. Nếu `packageHandouts` thật sự đọc một file output, task còn nên khai báo input tương ứng và kết nối với output producer để Gradle theo dõi thay đổi.

Các giá trị `copiedDir` và `syncedDir` trong ví dụ chính đến từ `layout.buildDirectory.dir(...)`, tức provider của thư mục thuộc build output. Dùng `ProjectLayout` tốt hơn nối chuỗi path tùy ý vì build directory có thể được cấu hình khác mặc định.

Để hai task cùng ghi một file hoặc một thư mục mà không có quan hệ rõ ràng là **overlapping output**. Điều này khiến Gradle khó đánh giá up-to-date/cache và có thể sinh kết quả không xác định. Vì vậy các task trong bài thực hành dùng hai output độc lập, còn task đổi tên dùng nhánh `lab/renamed` riêng.

Các lệnh chẩn đoán:

```bash
./gradlew --console=plain tasks --all
./gradlew --console=plain prepareHandouts --dry-run
./gradlew --console=plain --info copyHandouts
./gradlew --console=plain --info syncHandouts
```

`--dry-run` chỉ hiển thị kế hoạch task, **không thực hiện copy hoặc xóa**. `--info` giúp tìm nguyên nhân task được chạy/bỏ qua. Việc task báo `UP-TO-DATE` có thể là tối ưu hợp lệ khi input/output không đổi; không nên ép mọi task chạy lại chỉ để thấy dòng log.

Không nên tự suy ra từ `--build-cache` rằng mọi Copy/Sync đều `FROM-CACHE`: chỉ task hỗ trợ caching và có cache hit theo chính sách phù hợp mới khôi phục được output. Build cache và up-to-date check là hai cơ chế khác nhau.

## 11. Checklist an toàn trước khi dùng Sync và Delete trong dự án thật

1. **Xác nhận source và output.** Source như `src`, tài liệu và file trong Git không được coi là vùng output có thể xóa tùy tiện.
2. **Kiểm tra đường dẫn đích.** Đọc `into(...)` hoặc `delete(...)`; bảo đảm đích nằm dưới một nhánh output chuyên dụng và không phải root project, home directory hay nguồn.
3. **Không đặt dữ liệu không thể phục hồi trong đích Sync.** Mọi file trong đích phải thuộc quyền quản lý của thao tác đồng bộ.
4. **Kiểm tra pattern.** `include`, `exclude` và `rename` quyết định những file nào được chọn và do đó file nào có nguy cơ bị loại ở đích.
5. **Kiểm tra các task cùng ghi đích.** Không cho Copy, Sync và Delete độc lập tác động cùng một thư mục trong cùng task graph mà không thiết kế rõ trách nhiệm và thứ tự.
6. **Thử trên dữ liệu giả.** Vùng `build/lab` của bài thực hành là nơi phù hợp để xác minh hành vi với file `old.txt`.
7. **Không lạm dụng lệnh dry-run như kiểm chứng dữ liệu.** Dry-run chỉ cho biết kế hoạch; cần chạy thật ở vùng an toàn rồi kiểm tra output.
8. **Sử dụng backup nếu đích không thể tái tạo.** Tác vụ xóa là thao tác có tác động thực, có thể không khôi phục được qua Gradle.
9. **Không xóa ở configuration phase.** Tác vụ dọn dẹp phải được đăng ký và xử lý như task, không chạy ngay khi đánh giá build script.
10. **Cẩn trọng với symlink và đường dẫn do tham số tạo.** Không giả định path có vẻ thuộc `build` luôn được xử lý an toàn khi có liên kết tượng trưng hoặc đường dẫn đã cấu hình lại; xem xét môi trường thực và quyền truy cập.

## 12. Lỗi phổ biến và hướng khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Copy không có file đích | Sai source root hoặc bộ lọc chọn rỗng | Kiểm tra `from`, `include`, `exclude` và file nguồn |
| File `.png` không được đưa vào output | Chỉ include `**/*.txt` | Bổ sung pattern đúng với nhu cầu |
| File cũ vẫn còn sau Copy | Copy không dọn file dư | Dùng Sync với thư mục mirror riêng nếu cần |
| File tự tạo ở đích biến mất sau Sync | Không có trong tập file đồng bộ | Đừng lưu dữ liệu người dùng trong đích Sync |
| File nguồn bị thay đổi ngoài ý muốn | Task khác đang ghi vào nguồn hoặc đích trùng nguồn | Tách input/output, kiểm tra toàn bộ task graph |
| Delete không làm gì | Đường dẫn mục tiêu không tồn tại hoặc task không được chọn | Kiểm tra tên task, đường dẫn và trạng thái |
| Delete xóa quá rộng | Mục tiêu là thư mục cha/root hoặc path bị suy diễn sai | Dùng đường dẫn output hẹp, kiểm tra trước khi chạy |
| Duplicate path gây lỗi | Nhiều nguồn muốn tạo cùng tên đích | Đặt `FAIL` rồi đổi tên hoặc nested `into` |
| Chạy `--dry-run` mà không thấy file mới | Chế độ này không thực hiện action | Bỏ dry-run, chạy thật ở vùng thử |
| Copy và Sync cùng đích cho kết quả không ổn định | Chồng lấn output, thiếu quan hệ task | Tách đích và phân định task sở hữu |
| Task lần hai `UP-TO-DATE` | Đầu vào/đầu ra vẫn hợp lệ | Đây thường là tối ưu đúng, không phải lỗi |
| Resource Java đọc được trong IDE nhưng không có trong JAR | Dùng đường dẫn nguồn thay vì classpath hoặc thiếu cấu hình `processResources` | Kiểm tra `build/resources/main` và JAR |
| `clean` làm mất file cần giữ | Lưu file duy nhất trong `build` | Đưa file nguồn sang nơi quản lý dài hạn |
| Source bị Sync xóa mất | Đặt `into` nhầm vào thư mục nguồn | Không bao giờ Sync vào `src`; hạn chế đích về build output |

## 13. Bài tập vận dụng

**Bài tập A — đọc kết quả file stale.** Sau lần chạy `prepareHandouts`, tạo `old.txt` trong hai thư mục copied và synced như mục 4. Dự đoán kết quả rồi chạy lại hai task. Vì sao không nên đưa file tự viết vào đích Sync?

**Bài tập B — thay bộ lọc.** Thêm `src/handouts/notes/draft-private.txt`. Chạy `prepareHandouts`. File này có xuất hiện trong output không? Giải thích kết hợp `include '**/*.txt'` và `exclude '**/draft-*'`.

**Bài tập C — thử đổi tên.** Thêm task `renameHandout` ở mục 8 rồi chạy. Tìm `build/lab/renamed/notes/guide.txt`. File nguồn `steps.txt` còn ở đâu, và vì sao?

**Bài tập D — phân biệt Delete và clean.** Chạy `deleteCopiedDir`, xác nhận vùng synced còn. Sau đó dùng `clean` và quan sát nhánh output nào còn. Giải thích vì sao `clean` có phạm vi rộng hơn trong ví dụ có plugin `base`.

**Bài tập E — xung đột nhiều nguồn.** Tạo hai nguồn có `config.txt` và một Copy task gom chúng chung vào `build/lab/combined`. Dùng `DuplicatesStrategy.FAIL` để quan sát lỗi, rồi sửa bằng nested `into('source-a')`/`into('source-b')`.

**Bài tập F — task graph.** Chạy `prepareHandouts --dry-run`. Vì sao `copyHandouts` và `syncHandouts` đều được chọn nhưng `deleteCopiedDir` không được chọn? Liệu bạn có thể dự đoán chắc chắn thứ tự giữa Copy và Sync chỉ từ script không?

**Bài tập G — Java resources.** Trong một project Java khác, tạo `shared-resources/labels.txt`, cấu hình `processResources` và chạy `classes`. Kiểm tra file trong `build/resources/main`, rồi chạy lớp Java 17 ở mục 9 và đọc stdout.

### Câu hỏi tự kiểm tra

1. Tại sao Copy không đủ khi yêu cầu “đích phải giống chính xác tập file nguồn”?
2. Sync xử lý file chỉ có ở đích ra sao? Điều gì khiến nó nguy hiểm hơn Copy?
3. Delete nhận mục tiêu bằng API nào? Có cần khai báo nguồn không?
4. `from('src/handouts')` có tự đưa tên thư mục `src/handouts` vào đường dẫn output không?
5. Bộ lọc `include` và `exclude` tương tác thế nào?
6. `DuplicatesStrategy.FAIL` kiểm tra trùng từ nguồn hay xóa file stale ở đích?
7. Đặt `into('legal')` trong nested `from` khác gì `into` ở mức task?
8. `rename` đổi tên bản gốc hay bản sao?
9. Vì sao không nên sử dụng một thư mục output chung cho nhiều task Copy/Sync độc lập?
10. `--dry-run` cho biết điều gì và không xác minh được điều gì?
11. Với Java plugin, task nào xử lý resource của `main`?
12. Vì sao resource nên đọc từ classpath khi chương trình được đóng gói?
13. Khi nào dùng Delete hẹp, khi nào dùng `clean`?
14. Việc xóa output có đồng nghĩa file trong Git hoặc thư mục nguồn cũng bị xóa không? Khi nào cấu hình sai có thể gây ra tình huống đó?

**Ghi nhớ:** `Copy` **thêm/cập nhật file được chọn nhưng giữ file dư**, `Sync` **làm mới thư mục đích chuyên dụng và có thể xóa file dư**, `Delete` **xóa đúng đường dẫn mục tiêu**. Hãy luôn tách nguồn khỏi output, quản lý một đích bằng một trách nhiệm rõ ràng, khai báo bộ lọc và dependency minh bạch, rồi xác minh trên file thực tế trước khi dùng thao tác xóa trong dự án quan trọng.