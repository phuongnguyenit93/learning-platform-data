# Tra cứu `help`, `tasks`, `projects`, `properties` và tên task đầy đủ trong Gradle

## 1. Mục tiêu và bức tranh chung

Khi tiếp nhận một Gradle build, trước khi chạy `build`, `test` hoặc thay đổi build script, cần trả lời được năm câu hỏi:

1. **Có thể dùng những tùy chọn Gradle nào?** → `--help`; muốn biết một task làm gì và nhận tham số nào → `help --task ...`.
2. **Build có những task nào?** → `tasks`, `tasks --all` và `tasks --group=...`.
3. **Build gồm các project/subproject nào?** → `projects`.
4. **Project đang mang những thuộc tính nào?** → `properties` và `properties --property=...`.
5. **Muốn gọi chính xác task thuộc đúng project nào?** → dùng **đường dẫn task đầy đủ** như `:app:test` hoặc `:lib:build`.

Bốn tên `help`, `tasks`, `projects` và `properties` là **task báo cáo có sẵn** của Gradle. Chúng khác với tùy chọn CLI `--help` và `--version`. Phần lớn thao tác dưới đây chủ yếu phục vụ tra cứu, nhưng Gradle vẫn có thể **khởi tạo/configure build và tải plugin** để có dữ liệu báo cáo; vì vậy, lỗi môi trường hoặc plugin vẫn có thể xuất hiện trước khi in kết quả.

**Quy ước lệnh trong bài:** ví dụ chính dùng `./gradlew` từ thư mục gốc của repository trên Linux/macOS. Trên Windows PowerShell thay bằng `.\gradlew.bat`; trong Command Prompt thay bằng `gradlew.bat`. Dùng Gradle Wrapper đã được repository commit để tránh mỗi máy dùng một phiên bản Gradle khác nhau.

## 2. Tra cứu nhanh từ terminal

| Cần biết | Linux/macOS | Ý nghĩa |
| --- | --- | --- |
| Tùy chọn CLI chung | `./gradlew --help` | Danh sách cờ/option của Gradle, chẳng hạn `--offline` và `--console` |
| Thông tin trợ giúp cơ bản | `./gradlew help` | Chạy task `help` trong build |
| Thông tin một task | `./gradlew help --task greet` | Task path, kiểu task, mô tả và tùy chọn task khi có |
| Các project | `./gradlew projects` | Cấu trúc root project/subproject |
| Các task thường dùng | `./gradlew tasks` | Chủ yếu task được gán group |
| Danh sách mở rộng | `./gradlew tasks --all` | Hiện thêm task không thuộc group và các task liên quan |
| Task thuộc một group | `./gradlew tasks --group=learning` | Lọc group tên `learning` |
| Các project properties | `./gradlew properties` | Báo cáo thuộc tính của project được chọn |
| Chỉ một property | `./gradlew properties --property=version` | Truy vấn key cụ thể |
| Task của subproject | `./gradlew :app:tasks --all` | Xem task trong ngữ cảnh project `:app` |
| Chạy đúng một task | `./gradlew :app:greet` | Chạy task `greet` thuộc `:app` |

Một câu lệnh Gradle thường có dạng:

```text
./gradlew [đường-dẫn-task-hoặc-tên-task ...] [--tùy-chọn ...]
```

Dấu `:` phân tách các đoạn của **Gradle project path/task path**, không phải dấu phân tách thư mục Windows hoặc Unix. Dùng `--console=plain` nếu cần log thuần văn bản dễ đọc trong terminal hoặc CI; `-q`/`--quiet` giảm phần lớn log cấp lifecycle khi chỉ muốn xem báo cáo/`println`.

## 3. Dự án minh họa thực hành được

Để hiểu vì sao phải dùng tên task đầy đủ, hãy xét **một build nhiều project**, với root `:` và hai subproject `:app`, `:lib`. Đây là các file Groovy DSL độc lập, có thể tạo trong thư mục demo có Gradle Wrapper hoạt động.

```text
cli-lookup-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── app/
│   └── build.gradle
└── lib/
    └── build.gradle
```

`settings.gradle`:

```groovy
rootProject.name = 'cli-lookup-lab'
include 'app', 'lib'
```

`build.gradle` ở root:

```groovy
tasks.register('rootReport') {
    group = 'learning'
    description = 'In nhãn task tại root project'
    doLast {
        println 'Hello from :rootReport'
    }
}
```

`app/build.gradle`:

```groovy
ext.moduleRole = 'application'

tasks.register('greet') {
    group = 'learning'
    description = 'In lời chào từ app'
    doLast {
        println 'Hello from :app:greet'
    }
}
```

`lib/build.gradle`:

```groovy
ext.moduleRole = 'library'

tasks.register('greet') {
    group = 'learning'
    description = 'In lời chào từ lib'
    doLast {
        println 'Hello from :lib:greet'
    }
}
```

**Giải thích:** `include 'app', 'lib'` khai báo hai subproject. Root có task `rootReport`; `app` và `lib` đều có task cùng tên `greet`, nhưng vì chúng thuộc hai project khác nhau nên **đường dẫn task không trùng nhau**. `group` và `description` là metadata làm báo cáo `tasks`/`help` dễ đọc; `ext.moduleRole` là thuộc tính tự khai báo để kiểm tra bằng `properties`. Ví dụ này không cần source Java hay plugin Java vì chỉ đăng ký task có hành động `println`.

Nếu thư mục demo chưa có Wrapper, trước hết tạo Wrapper bằng Gradle đã cài tạm, ví dụ `gradle wrapper`; sau đó dùng script Wrapper trong mọi lệnh phía dưới. Với repository thực tế đã có Wrapper, bỏ qua bước tạo này. Không chép đè `settings.gradle` và `build.gradle` của một dự án đang làm việc chỉ để chạy demo.

## 4. `--help` và task `help`: cùng chữ nhưng khác mục đích

### 4.1. `--help`: tra cứu tùy chọn của lệnh Gradle

```bash
./gradlew --help
./gradlew --version
```

- `--help` (hoặc `-h`) hiển thị cách gọi và các tùy chọn chung của Gradle rồi thoát.
- `--version` (hoặc `-v`) hiển thị phiên bản Gradle và thông tin môi trường JVM/HĐH; không chạy task.
- Đây là các **CLI options**, không phải các task cần định nghĩa trong `build.gradle`.

Ví dụ: muốn hiểu `--offline`, `--stacktrace`, `--info`, `--console=plain`, tra `--help` trước.

### 4.2. `help`: task hỗ trợ trong một Gradle build

```bash
./gradlew help
./gradlew -q help
```

Lệnh đầu chạy task `help`; lệnh sau dùng `-q` để giảm các dòng log Gradle. Đây là điểm bắt đầu khi bạn chỉ biết đường dẫn repository và muốn xác nhận Gradle nạp được cấu hình build. Nó không phải báo cáo danh sách task của dự án; để tìm task dùng `tasks`.

### 4.3. `help --task <tên>`: tra cứu thông tin của task cụ thể

```bash
./gradlew -q help --task greet
./gradlew -q help --task rootReport
```

Với build minh họa, `help --task greet` giúp tìm thông tin cho cả `:app:greet` và `:lib:greet`. Báo cáo task thường có các phần:

- **Paths**: các đường dẫn task đầy đủ phù hợp với tên đang tra cứu.
- **Type**: lớp/kiểu task.
- **Options**: tùy chọn mà task hỗ trợ; một số task do plugin cung cấp có tùy chọn riêng.
- **Description** và **Group**: mô tả/ngóm dùng để tổ chức task.

Ví dụ **cấu trúc trích đoạn minh họa**, các dòng chi tiết còn phụ thuộc phiên bản Gradle và plugin:

```text
Detailed task information for greet

Paths
    :app:greet
    :lib:greet

Description
    ...
Group
    learning
```

Vì tên `greet` không chỉ thuộc một project, **không nên suy ra project đích chỉ từ tên ngắn**. Dựa vào phần `Paths` và gọi `:app:greet` hoặc `:lib:greet` khi muốn xác định chính xác.

**Lưu ý về thứ tự tham số:** `--task` ở đây là tùy chọn của task báo cáo `help`, nên viết sát phía sau task: `help --task greet`. Tùy chọn riêng của những task khác cũng nên đặt ngay sau task mà chúng áp dụng. Chẳng hạn task Java `test` có `--tests`, nhưng `--tests` không phải tùy chọn chung của mọi task.

## 5. `projects`: xem cấu trúc nhiều project

```bash
./gradlew projects
./gradlew -q projects
```

Với build minh họa, bạn sẽ tìm thấy root project `cli-lookup-lab` cùng hai project có path `:app` và `:lib`. Sơ đồ tương ứng:

```text
:                    root project "cli-lookup-lab"
├── :app             subproject app
└── :lib             subproject lib
```

Đây là **sơ đồ cấu trúc**, không phải bản chép nguyên văn toàn bộ stdout; cách trình bày báo cáo thay đổi giữa các phiên bản Gradle. Quan trọng nhất là phân biệt:

| Ký hiệu | Là gì? |
| --- | --- |
| `:` | Gradle project path của root |
| `:app` | Gradle project path của subproject app |
| `:lib` | Gradle project path của subproject lib |
| `:app:greet` | Gradle **task path** của task `greet` trong project `:app` |

`projects` giúp trả lời “Có những subproject nào?” nhưng không liệt kê mọi task chi tiết. Nếu thiếu `:app`, kiểm tra khai báo `include` trong `settings.gradle`/`settings.gradle.kts` và tên project thực tế. Với build lồng nhau, có thể gặp `:services:payment`; khi đó task tương ứng có dạng `:services:payment:build`.

**Project path không bắt buộc trùng tên thư mục vật lý:** Gradle có thể ánh xạ `projectDir` khác hoặc đổi tên project. Khi phân giải câu lệnh, tin vào các **path mà Gradle báo cáo**, không tự suy đoán từ tên folder.

## 6. `tasks`: tìm task hiện có và phạm vi của báo cáo

### 6.1. Danh sách thông thường

```bash
./gradlew tasks
./gradlew :app:tasks
./gradlew :lib:tasks
```

Báo cáo `tasks` nhóm các task theo `group`, kèm `description` nếu có. Với demo, các task tùy biến ở group `learning`. Các plugin thường bổ sung group như `build`, `verification`, `help`; **task `test` không luôn có sẵn**, vì nó phụ thuộc plugin mà build đã áp dụng.

`./gradlew tasks` tập trung vào ngữ cảnh root và việc liệt kê trong build; `./gradlew :app:tasks` yêu cầu báo cáo trong ngữ cảnh subproject `:app`. Cách liệt kê task của subproject liên quan trong báo cáo có thể khác tùy loại task/Gradle version, nên khi muốn hiểu một project cụ thể, luôn chỉ rõ project path.

### 6.2. `tasks --all`: mở rộng báo cáo

```bash
./gradlew tasks --all
./gradlew :app:tasks --all
```

Theo mặc định, `tasks` chủ yếu hiển thị task được gán group. `--all` hiển thị thêm các task không được phân nhóm và thông tin task mở rộng, giúp tìm các task kỹ thuật/ẩn khỏi danh sách mặc định. Dù vậy, danh sách có thể rất dài trong build lớn. Hãy chọn project trước bằng `:app:tasks --all` để giảm phạm vi.

`tasks --all` **không có nghĩa mọi task trên toàn bộ build đều có thể gọi bằng tên ngắn mà chỉ chạy một bản**. Tên task có thể xuất hiện ở nhiều project và hành vi task selector cần được phân biệt với task path đầy đủ.

### 6.3. `tasks --group=<group>`: lọc đúng nhóm

```bash
./gradlew tasks --group=learning
./gradlew :app:tasks --group=learning
```

Tùy chọn này lọc theo **giá trị `group` của task**, không phải tên package Java hay project. Ví dụ `group = 'learning'` ở các build script trong phần 3 giúp nhóm `learning` hiện trong báo cáo. Nếu group có dấu cách, cần quote giá trị:

```bash
./gradlew tasks --group="build setup"
```

Nhãn group được định nghĩa bởi task/plugin nên **không có một danh mục cố định dùng được cho mọi build**. Đừng coi `--group=verification` là bộ lọc “mọi test” nếu plugin chưa gán task vào group đó.

### 6.4. Tại sao thiếu task đang tìm?

Trước khi kết luận task không tồn tại, kiểm tra theo thứ tự:

1. Đã chọn đúng project chưa? `:app:tasks` và `:lib:tasks` có thể khác.
2. Có cần `--all` vì task chưa được gán group không?
3. Plugin tạo task đã được áp dụng chưa? Task `test` thường do Java plugin tạo.
4. Task chỉ được đăng ký theo điều kiện, profile, môi trường hoặc plugin riêng?
5. Task name/case có đúng không? Tên phân biệt chữ hoa/thường; đừng dựa vào tên gần giống khi cần câu lệnh ổn định.

Nếu cần biết task nhận **option** nào, `help --task tênTask` thường phù hợp hơn so với đọc nguyên danh sách `tasks`.

## 7. `properties`: xem thuộc tính của project

```bash
./gradlew properties
./gradlew :app:properties
./gradlew :lib:properties
```

Task `properties` in ra danh sách thuộc tính của **project được chọn**, gồm nhiều thuộc tính hệ thống của Gradle và những thuộc tính do build script/plugin khai báo. Báo cáo có thể dài và chứa giá trị đối tượng ở dạng biểu diễn nội bộ; nó **không phải** lệnh liệt kê file trong thư mục.

Với demo `app/build.gradle` đã khai báo `ext.moduleRole = 'application'`. Truy vấn riêng một property:

```bash
./gradlew -q :app:properties --property=moduleRole
./gradlew -q :lib:properties --property=moduleRole
```

Phần thông tin mong đợi trong hai báo cáo lần lượt là:

```text
moduleRole: application
```

```text
moduleRole: library
```

Đây là **dòng giá trị liên quan**, không phải toàn bộ stdout: Gradle thường in thêm tiêu đề project và đường phân cách. Có thể tra các property có sẵn như `name`, `path`, `group` và `version`:

```bash
./gradlew -q :app:properties --property=path
./gradlew -q :app:properties --property=version
```

Đừng nhầm các khái niệm:

- `properties` là **task báo cáo project properties**.
- `gradle.properties` là **file cấu hình Gradle/build**, có thể góp phần tạo giá trị property.
- `-Pkey=value` hoặc `--project-prop=key=value` là **CLI option để cung cấp project property khi chạy lệnh**, ví dụ `./gradlew properties --property=environment -Penvironment=local`.
- `-Dkey=value` truyền **Java system property** và có ngữ nghĩa khác; đừng thay `-P` bằng `-D` tùy tiện.

**Bảo mật:** `properties` có thể phơi bày thông tin nhạy cảm nếu dự án lưu token/password dưới dạng project property. Không công khai toàn bộ stdout hoặc đưa vào issue/CI artifact khi chưa rà soát. Ưu tiên `--property=...` cho key cần kiểm tra; một property đơn lẻ vẫn có thể là bí mật.

## 8. Tên task, task path đầy đủ và task selector

### 8.1. Cách hình thành đường dẫn đầy đủ

Công thức:

```text
:<project-1>:<project-2>:...:<taskName>
```

Với demo:

| Lệnh hoặc path | Đích/ý nghĩa |
| --- | --- |
| `:rootReport` | Task `rootReport` được định nghĩa tại root `:` |
| `:app:greet` | Task `greet` trong project `:app` |
| `:lib:greet` | Task `greet` trong project `:lib` |
| `greet` | **Task selector**: có thể chọn các task `greet` phù hợp trong phạm vi build |
| `app:greet` từ root | Dạng bỏ dấu `:` đầu; thường trỏ đến `:app:greet`, nhưng phụ thuộc project hiện tại |
| `:services:payment:test` | Task `test` của project lồng `:services:payment`, nếu project/task đó tồn tại |

Dấu `:` ở đầu chỉ đường dẫn tuyệt đối từ root Gradle build. Dùng đường dẫn đầy đủ trong CI/script cần tính xác định, nhất là khi nhiều module có cùng task `build` hoặc `test`.

### 8.2. Chạy đúng một task: kết quả kiểm chứng rõ ràng

```bash
./gradlew -q :rootReport
./gradlew -q :app:greet
./gradlew -q :lib:greet
```

Với đúng các script mẫu phần 3, **phần stdout do từng task tự in** lần lượt là:

```text
Hello from :rootReport
```

```text
Hello from :app:greet
```

```text
Hello from :lib:greet
```

Mỗi khối kết quả là của **một lần gọi riêng**. `-q` giúp giảm log không thiết yếu của Gradle; thông báo lỗi/cảnh báo hoặc việc tải plugin phụ thuộc môi trường vẫn có thể xuất hiện.

### 8.3. Gõ `greet` khác gì gõ `:app:greet`?

```bash
./gradlew greet
./gradlew :app:greet
```

Trong ví dụ này, khi gọi từ **root**, `greet` là **task selector**: Gradle có thể thực thi cả `:app:greet` lẫn `:lib:greet` vì cả hai project đều đăng ký task cùng tên. Ngược lại `:app:greet` chỉ chọn task thuộc `:app` (và các dependency của task đó, nếu có).

Ví dụ thường gặp ở project Java nhiều module:

```bash
./gradlew test
./gradlew :app:test
./gradlew :lib:test
```

- `test` từ root có thể lựa chọn các task `test` ở nhiều subproject.
- `:app:test` chọn đúng task thuộc project `:app`.
- Nếu root **không có** task `test`, `:test` là sai trong khi `test` hoặc `:app:test` có thể vẫn hợp lệ.

**Không có quy tắc “tên ngắn luôn chạy task ở root”.** Cần biết ngữ cảnh project và cách Gradle task selector hoạt động. Một task được chỉ định cũng có thể chạy các prerequisite thông qua `dependsOn`; “chọn một task” không đồng nghĩa chỉ thấy một task trong log.

### 8.4. Tên viết tắt được hỗ trợ, nhưng nên thận trọng

Gradle hỗ trợ rút gọn tên project/task khi phần viết tắt đủ phân biệt; ví dụ các tên dài dạng camelCase có thể dùng chữ viết hoa đầu từ để match. Khi nhiều tên trùng hoặc gần giống, viết tắt có thể trở nên mơ hồ hoặc đổi nghĩa khi thêm task/plugin.

```bash
./gradlew :app:greet
./gradlew :app:greet --info
```

`--info` cung cấp thêm thông tin khi phân giải tên và cấu hình build. Với CI hoặc tài liệu hướng dẫn, **ưu tiên tên đầy đủ** để người đọc và công cụ tự động cùng hiểu một đích.

## 9. Quy trình khám phá một repository chưa quen

Giả sử vừa clone repository có Gradle Wrapper. Không biết project nào chứa task cần chạy.

**Bước 1 — xác nhận công cụ và các tùy chọn:** 

```bash
./gradlew --version
./gradlew --help
./gradlew help
```

**Bước 2 — xem sơ đồ project:**

```bash
./gradlew projects
```

Ghi lại project path chính xác được báo cáo, chẳng hạn `:app`, `:lib`.

**Bước 3 — tra task tại project cần làm:**

```bash
./gradlew :app:tasks
./gradlew :app:tasks --all
```

Nếu biết group do build tự định nghĩa, lọc `:app:tasks --group=learning`. Với ứng dụng Java, tìm trong nhóm build/verification nếu plugin đã tạo task tương ứng.

**Bước 4 — tra thông tin, option của task:**

```bash
./gradlew help --task greet
```

Đối chiếu phần `Paths`, `Description`, `Options`. Khi có nhiều task trùng tên, chọn đường dẫn đầy đủ mong muốn.

**Bước 5 — xem thuộc tính cần biết:**

```bash
./gradlew :app:properties --property=moduleRole
```

Đây chỉ là ví dụ khi project có property `moduleRole`; với repository khác, chọn key tồn tại. Không cần in mọi property nếu chỉ muốn kiểm tra một key.

**Bước 6 — chạy task có địa chỉ chính xác:**

```bash
./gradlew :app:greet
```

Nếu chỉ muốn kiểm tra Gradle **sẽ chọn task nào** trước khi thực thi hành động, dùng:

```bash
./gradlew :app:greet --dry-run
```

`--dry-run` bỏ qua task actions và hiển thị các task dự định chạy; nó vẫn có thể thực hiện công việc cấu hình build, vì vậy không thay thế được một lần chạy thực tế. Nếu phải đưa vào CI, gọi task path đầy đủ và kiểm tra exit code của tiến trình.

## 10. Sử dụng từ Windows, Linux, macOS

Các task và path sau dấu tên script là **cùng nhau**, khác nhau chủ yếu ở cách gọi script:

| Chức năng | Bash/zsh Linux, macOS | PowerShell | Command Prompt |
| --- | --- | --- | --- |
| Danh sách project | `./gradlew projects` | `.\gradlew.bat projects` | `gradlew.bat projects` |
| Task tại app | `./gradlew :app:tasks --all` | `.\gradlew.bat :app:tasks --all` | `gradlew.bat :app:tasks --all` |
| Task help | `./gradlew help --task greet` | `.\gradlew.bat help --task greet` | `gradlew.bat help --task greet` |
| Property tại app | `./gradlew :app:properties --property=moduleRole` | `.\gradlew.bat :app:properties --property=moduleRole` | `gradlew.bat :app:properties --property=moduleRole` |
| Chạy task cụ thể | `./gradlew :app:greet` | `.\gradlew.bat :app:greet` | `gradlew.bat :app:greet` |

Mở terminal tại **root Gradle build** để dùng các lệnh này nguyên dạng. Nếu mở terminal trong `app/`, cần chỉ định đường dẫn tương đối đến Wrapper, chẳng hạn `../gradlew` trên Linux/macOS. Tên project/task path vẫn dùng dấu `:` như nhau ở cả ba OS; đừng thay `:app:greet` thành `app\greet` hoặc `app/greet`.

## 11. Lỗi dễ gặp và cách xác minh

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Task 'greet' not found` | Chọn sai project, gõ sai tên hoặc task chưa được tạo | `projects` → `:app:tasks --all` → `help --task greet`; kiểm tra plugin/cấu hình |
| `Project 'app' not found` | `:app` chưa được include hoặc path thực tế khác | `./gradlew projects` rồi dùng project path mà báo cáo hiển thị |
| `:test` thất bại nhưng `test` có thể chạy | Root thiếu `test`, còn subproject có task `test` | Dùng `:app:test` cho một module; nếu muốn chọn nhiều module thì hiểu rõ task selector `test` |
| `tasks` không thấy task mong đợi | Task không được gán group, hoặc đang tra root thay vì subproject | `:app:tasks --all`; kiểm tra build script/plugin |
| `help --task greet` liệt kê nhiều path | Cùng tên task trong nhiều project | Gọi `:app:greet` hoặc `:lib:greet` một cách rõ ràng |
| `properties --property=...` không trả giá trị cần tìm | Property không tồn tại trong project đang chọn, hoặc tên/case sai | Kiểm tra đúng project, key và nguồn cấu hình; đừng giả định property từ project khác |
| Chạy `gradle tasks` ra kết quả khác đồng đội | Gradle cài toàn cục khác phiên bản Wrapper | Dùng `./gradlew` hoặc `.\gradlew.bat` của repository |
| `./gradlew: Permission denied` | Unix script thiếu execute bit | `chmod +x gradlew`; bảo đảm Git commit executable bit |
| PowerShell báo không nhận `gradlew` | Gọi thiếu tiền tố `.\` hoặc không có script Windows | Tại root chạy `.\gradlew.bat tasks` |
| Báo cáo `properties` bị dán vào issue và lộ thông tin nhạy cảm | In toàn bộ project properties có chứa dữ liệu bí mật | Giới hạn truy vấn bằng `--property`, ẩn/redact giá trị trước khi chia sẻ |

**Lưu ý:** tùy Gradle/plugin, một task có thể chỉ được đăng ký sau bước cấu hình hoặc yêu cầu điều kiện nhất định. Báo cáo là ảnh chụp **build đang được cấu hình** trên máy của bạn, không bảo đảm task đó tồn tại ở mọi branch hoặc môi trường.

## 12. Bài tập tự kiểm tra

Trên build `cli-lookup-lab` phần 3, thực hiện:

1. Dùng một lệnh xem root có những subproject nào. Đáp án: `./gradlew projects`, tìm `:app` và `:lib`.
2. Liệt kê các task thuộc group `learning` trong project app. Đáp án: `./gradlew :app:tasks --group=learning`.
3. Tìm các đường dẫn có task `greet` và mô tả liên quan. Đáp án: `./gradlew -q help --task greet`; so sánh `:app:greet` với `:lib:greet`.
4. Chỉ lấy property `moduleRole` của lib. Đáp án: `./gradlew -q :lib:properties --property=moduleRole`; giá trị `library`.
5. In lời chào đúng một project app mà không chạy task cùng tên ở lib. Đáp án: `./gradlew -q :app:greet`; stdout do task in ra là `Hello from :app:greet`.
6. So sánh `./gradlew greet` với `./gradlew :app:greet`. Lệnh thứ nhất là task selector từ root có thể chọn cả app và lib; lệnh thứ hai chỉ rõ project app.
7. Muốn xem những task chưa được đặt group? Đáp án: `./gradlew :app:tasks --all`.
8. Muốn tra các CLI flags (khác với metadata của task)? Đáp án: `./gradlew --help`.

Tự kiểm bằng cách **đọc phần Paths trong `help --task` và project path trong `projects`**, không chỉ nhìn tên hiển thị trong IDE.

## 13. Ghi nhớ dùng trong dự án thật

- **`--help`**: xem option chung của Gradle. **`help --task X`**: xem metadata và option của task X.
- **`projects`**: tìm project path. **`tasks`/`tasks --all`**: tìm task. **`properties`/`--property`**: đọc project properties cần kiểm tra.
- **Task path tuyệt đối** có dạng `:project:subproject:task`; `:task` là task của root. Tên task không có `:` có thể hoạt động như task selector và chọn nhiều task phù hợp.
- Trong build nhiều module, thao tác lặp lại trong CI hoặc hướng dẫn chính thức nên gọi **đường dẫn task đầy đủ** để tránh vô tình chạy module khác.
- Dùng Wrapper có sẵn để các môi trường gọi cùng phiên bản Gradle; cẩn thận khi chia sẻ stdout của `properties` vì có thể chứa thông tin nhạy cảm.

## Tài liệu chính thức

- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): task selector, multi-project task path, project reporting, `help --task`, `tasks`, `projects`, `properties`.
- [Gradle — Command-Line Interface Basics](https://docs.gradle.org/current/userguide/command_line_interface_basics.html): cú pháp lệnh và tùy chọn.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): khai báo subproject, Gradle project path.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): sử dụng Wrapper nhất quán giữa các máy.
