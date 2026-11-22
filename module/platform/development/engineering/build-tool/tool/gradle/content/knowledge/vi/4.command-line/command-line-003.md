# Chọn task bằng project path và tránh gọi nhầm task trùng tên trong Gradle

## 1. Vấn đề cần giải quyết

Trong **multi-project build** (dự án Gradle có nhiều module/subproject), các project khác nhau thường cùng có task mang tên `build`, `test`, `check`, `clean` hoặc một task tùy chỉnh như `report`. Nếu chạy lệnh quá chung chung, Gradle có thể chọn **nhiều task cùng tên** trong cây project; nếu viết tắt tên, Gradle có thể chọn nhầm hoặc báo tên không đủ rõ. Điều này dễ dẫn đến chạy kiểm thử ở nhiều module, build nhầm dịch vụ, hoặc kích hoạt tác vụ nặng khi chỉ muốn thao tác trên một module.

Cách kiểm soát chính là dùng **task path đầy đủ**: kết hợp `project path` với `task name`, bắt đầu bằng dấu hai chấm `:` tại root của build.

~~~text
:app:test                 Task "test" của project ":app"
:lib:test                 Task "test" của project ":lib"
:services:api:build       Task "build" của project ":services:api"
:clean                    Task "clean" của root project, nếu root có task này
~~~

Dấu `:` phân cách các **thành phần Gradle project path**, không phải dấu `/` phân cách thư mục của hệ điều hành. Mỗi task thuộc về một project; `task.path` (ví dụ `:app:test`) định danh duy nhất task đó trong một build Gradle. `:` một mình là đường dẫn project gốc; `:test` là task `test` thuộc project gốc. Tên project lấy từ cấu hình build, chủ yếu ở `settings.gradle.kts` hoặc `settings.gradle`; đường dẫn project thường trùng vị trí thư mục nhưng có thể được ánh xạ sang thư mục khác.

**Quy tắc làm việc:** khi muốn một task ở một module cụ thể, hãy ưu tiên lệnh `./gradlew :ten-module:tenTask`. Khi muốn cố ý thực thi task cùng tên trên nhiều module, có thể dùng task selector không có `:`.

## 2. Phân biệt tên task, project path và task path

Giả sử có project gốc và hai subproject `:app`, `:lib`, mỗi project đều định nghĩa task `report`:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Project gốc | `:` | Root project của build hiện tại. |
| Project path | `:app`, `:lib` | Địa chỉ project trong cây Gradle. |
| Task name | `report` | Tên task trong **một** project; tên này có thể lặp ở project khác. |
| Task path đầy đủ | `:app:report` | Task `report` thuộc đúng `:app`. |
| Task ở root | `:report` | Task `report` của root project. |
| Task ở project lồng nhau | `:services:api:report` | Task `report` thuộc project `:services:api`, khi project này tồn tại. |

So sánh các lệnh gọi **từ thư mục root của build**:

| Lệnh | Gradle chọn gì? |
| --- | --- |
| `./gradlew report` | Task selector: chọn các task tên `report` trong root và các project con thuộc phạm vi selector. Nếu nhiều project có task này, **có thể chạy nhiều task**, không mặc nhiên báo trùng tên. |
| `./gradlew :report` | Chọn đúng task `report` ở root (và các task phụ thuộc của nó). |
| `./gradlew :app:report` | Chọn đúng task `report` ở `:app` (và các task phụ thuộc). |
| `./gradlew :lib:report` | Chọn đúng task `report` ở `:lib` (và các task phụ thuộc). |
| `./gradlew app:report` | Từ root, thường tương đương `:app:report`; viết dấu `:` ở đầu giúp thể hiện rõ đường dẫn tuyệt đối và tránh phụ thuộc ngữ cảnh. |
| `./gradlew :app:report :lib:report` | Yêu cầu hai task đã nêu rõ bằng path; các task phụ thuộc có thể được chạy thêm. |

**Hai lưu ý quan trọng:**

- `./gradlew report` từ root **không tương đương** `./gradlew :report`. Lệnh đầu là selector tìm task cùng tên theo phân cấp project; lệnh sau chỉ định task ở root.
- `./gradlew :app:build` chỉ chọn task `build` ở `:app` làm đích. Các dependency task của nó **vẫn có thể** nằm ở project khác. “Chọn đúng một task đích” không có nghĩa mọi task được thực thi đều phải nằm trong `:app`.

Một số task báo cáo/tiện ích, như `help` và `dependencies`, có quy tắc selector đặc biệt nhằm hạn chế số output; đừng suy luận rằng mọi tên task không có `:` luôn chạy trên tất cả project. Với hành động cần kiểm soát chặt, hãy dùng path đầy đủ.

## 3. Ví dụ Kotlin DSL có thể thực hành

Tạo một dự án nhỏ, dùng **Gradle Wrapper** sẵn có để tái hiện rõ tình huống task trùng tên. Thư mục:

~~~text
task-path-lab/
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── settings.gradle.kts
├── build.gradle.kts
├── app/
│   └── build.gradle.kts
└── lib/
    └── build.gradle.kts
~~~

Nội dung `settings.gradle.kts`:

~~~kotlin
rootProject.name = "task-path-lab"
include("app", "lib")
~~~

Nội dung `build.gradle.kts` ở **root**:

~~~kotlin
tasks.register("report") {
    group = "verification"
    description = "In báo cáo ở root project"
    doLast {
        println("REPORT root")
    }
}
~~~

Nội dung `app/build.gradle.kts`:

~~~kotlin
tasks.register("report") {
    group = "verification"
    description = "In báo cáo của app"
    doLast {
        println("REPORT app")
    }
}

tasks.register("checkApi") {
    group = "verification"
    doLast {
        println("CHECK API")
    }
}

tasks.register("checkApp") {
    group = "verification"
    doLast {
        println("CHECK APP")
    }
}
~~~

Nội dung `lib/build.gradle.kts`:

~~~kotlin
tasks.register("report") {
    group = "verification"
    description = "In báo cáo của lib"
    doLast {
        println("REPORT lib")
    }
}
~~~

Các task `report` được đăng ký trong **ba project khác nhau**, vì thế ba đường dẫn `:report`, `:app:report` và `:lib:report` là ba task khác nhau, dù cùng có phần tên cuối `report`. Không cần áp dụng plugin Java để chạy ví dụ này.

Đứng ở thư mục `task-path-lab`, thử lần lượt:

~~~bash
# Linux/macOS: đúng một task đích ở app
./gradlew -q :app:report

# Chỉ task ở root
./gradlew -q :report

# Cố ý chọn report trên cây project
./gradlew -q report

# Chọn hai task đích bằng đường dẫn đầy đủ
./gradlew -q :app:report :lib:report
~~~

Với script mẫu, stdout **chính xác của lệnh thứ nhất** là:

~~~text
REPORT app
~~~

Stdout **chính xác của lệnh thứ hai** là:

~~~text
REPORT root
~~~

Lệnh thứ ba in ba dòng `REPORT root`, `REPORT app`, `REPORT lib`, mỗi dòng một lần; không nên dựa vào thứ tự các dòng vì cách lập lịch task và quan hệ phụ thuộc có thể làm thứ tự thay đổi. Lệnh thứ tư in `REPORT app` và `REPORT lib`, mỗi dòng một lần, và không gọi task `:report` của root. Tùy Gradle/terminal, cảnh báo môi trường hoặc logging không thuộc hành động task có thể xuất hiện riêng.

Trên Windows PowerShell, dùng:

~~~powershell
.\gradlew.bat -q :app:report
.\gradlew.bat --dry-run :app:report
~~~

Đừng nhập cú pháp file Kotlin DSL vào shell: các khối `tasks.register(...)` phải nằm trong các file `build.gradle.kts` tương ứng. Nếu dự án đã có Wrapper, các file `gradlew`, `gradlew.bat` và `gradle/wrapper` được giữ/commit cùng dự án; ví dụ trên chỉ liệt kê chúng, không yêu cầu tự viết lại Wrapper.

## 4. Vì sao tên task trùng nhau **không** nhất thiết gây lỗi?

Gradle phân biệt rõ hai cơ chế:

**A. Task selector theo tên không có dấu phân tách project**, ví dụ `./gradlew report` hoặc `./gradlew test`:

- Gradle tìm các task tên đó trong phạm vi project tương ứng với nơi thực thi và các project con.
- Nếu nhiều project có task tên `report`, Gradle có thể **chạy tất cả task khớp**. Đây là hành vi chọn nhiều task theo thiết kế, không phải lỗi “ambiguous task name”.
- Khi chạy từ root, phạm vi thường gồm root và các subproject; khi chạy ở thư mục của subproject, selector bắt đầu từ project đó và các project con của nó. Vì thế **working directory** có thể đổi kết quả.
- Nếu không có task tên đó trong phạm vi được xét, Gradle sẽ báo không tìm thấy task phù hợp.

**B. Chọn một task bằng task path đầy đủ**, ví dụ `./gradlew :app:report`:

- Gradle nhận địa chỉ chính xác của project `:app`, sau đó tên task `report` ở project đó.
- Các project khác cũng có `report` không ảnh hưởng lựa chọn.
- Nếu project path sai, hoặc project đó không có task được yêu cầu, Gradle sẽ báo lỗi thay vì tự động chuyển sang task cùng tên ở module khác.

Một ví dụ thực tế: cả `:app` và `:lib` áp dụng Java plugin nên đều có `test`. Lệnh `./gradlew test` từ root có thể chạy kiểm thử của cả hai; lệnh `./gradlew :app:test` chỉ chọn `test` của app, rồi Gradle chạy các dependency cần thiết trong task graph. Đây là lựa chọn hữu ích để giảm phạm vi chạy khi cần kiểm tra một module cụ thể.

### Working directory và đường dẫn tuyệt đối

Ở thư mục root:

~~~bash
./gradlew :app:report
./gradlew app:report
~~~

Hai lệnh trên chỉ cùng task trong ví dụ. Nhưng nếu đổi vào thư mục `app/` rồi chạy `../gradlew report`, selector không có `:` được hiểu trong ngữ cảnh project `:app`. Đường dẫn tuyệt đối `:app:report` vẫn chỉ định cùng một project bất kể nơi bạn gọi Wrapper trong build:

~~~bash
cd app
../gradlew -q report
../gradlew -q :app:report
~~~

Hai lệnh cuối đều in `REPORT app` trong ví dụ này. **Cần gọi đúng đường dẫn đến script Wrapper** từ thư mục hiện tại: `../gradlew` nếu Wrapper nằm ở root; `./gradlew` trong thư mục `app` sẽ không có sẵn trừ khi bạn tự đặt script ở đó. Trên Windows, sử dụng `..\gradlew.bat` và `.\gradlew.bat` theo vị trí thực.

## 5. Task path của project lồng nhiều cấp

Trong dự án lớn, project có thể lồng nhau như `:services:api`, `:services:worker`, `:shared:core`. Nếu file settings khai báo:

~~~kotlin
rootProject.name = "platform"
include("services:api", "services:worker", "shared:core")
~~~

Các ví dụ đường dẫn task tương ứng (giả sử task đó được plugin/build script đăng ký):

~~~text
:services:api:test
:services:worker:build
:shared:core:jar
~~~

Chạy riêng task kiểm thử của API:

~~~bash
./gradlew :services:api:test
~~~

Dấu `:` đầu tiên neo đường dẫn vào root của build; các đoạn `services`, `api` xác định thứ bậc project; `test` cuối là task name. Không thay bằng `services/api/test` hay `:services/api:test`. Trong Gradle 9+, những thư mục project được khai báo trong settings phải tồn tại và có quyền thích hợp; cấu trúc ví dụ chỉ minh họa cách định danh project, không tạo ra các file build cho những project này.

Nếu một subproject được đổi thư mục vật lý bằng `project(":services:api").projectDir = file("backend/http-api")`, task path vẫn là `:services:api:test`. **Project path là định danh Gradle**, không phải đường dẫn đến file `build.gradle.kts`.

## 6. Viết tắt tên project/task: tiện nhưng dễ gọi nhầm

Gradle hỗ trợ **name abbreviation** ở dòng lệnh khi phần tên rút gọn định danh được duy nhất. Ví dụ `gradle che` có thể được mở rộng thành `check`; `gradle lib:che` có thể chọn `:library:check` nếu không có tên xung đột. Gradle cũng nhận dạng chữ hoa theo **camelCase** và dấu gạch nối theo **kebab-case**: tài liệu chính thức minh họa `mAL:cT` có thể được mở rộng thành `:my-awesome-library:compileTest`.

Hệ quả: thêm module mới, plugin mới hoặc task mới có tên gần giống có thể làm bản viết tắt **trở nên mơ hồ**. Ví dụ, `app/build.gradle.kts` trong phần 3 có cả `checkApi` và `checkApp`:

~~~bash
# Không an toàn: 'checkAp' có thể khớp cả checkApi và checkApp
./gradlew :app:checkAp

# Rõ ràng: gọi đúng task
./gradlew :app:checkApi
./gradlew :app:checkApp
~~~

Ở ví dụ này, `checkAp` chưa đủ phân biệt nên Gradle báo lỗi chọn task mơ hồ; thông báo cụ thể khác nhau giữa các phiên bản. Lệnh ghi đủ `checkApi` thì chạy hành động và in `CHECK API` (nếu dùng thêm `-q`). Một chữ gõ thiếu cũng có thể bất ngờ tạo ra **một** tên rút gọn hợp lệ khác với ý định ban đầu, nên không nên dùng abbreviation trong CI hoặc script triển khai.

Phân biệt:

- **Task trùng tên ở các project khác nhau**: `:app:report` và `:lib:report` đều hợp lệ; `./gradlew report` có thể chọn cả hai.
- **Viết tắt mơ hồ trong lúc phân giải tên**: `:app:checkAp` khớp nhiều tên task ở chính project được chọn và có thể bị từ chối.
- **Project path viết tắt** cũng có thể mơ hồ, ví dụ `:a:report` nếu build có cả `:app` và `:admin`. Dùng tên project đầy đủ.

Khi cần kiểm tra vì sao abbreviation được mở rộng thành tên nào, thêm `--info` để xem các thông điệp phân giải tên từ Gradle, nhưng quy tắc an toàn nhất là bỏ viết tắt và dùng full task path.

## 7. Tìm đúng task trước khi chạy

Bốn lệnh hữu ích từ **root project**:

~~~bash
# 1. Xem cây project và đường dẫn chính xác
./gradlew projects

# 2. Xem các task của app, kể cả task không hiện ở danh sách ngắn
./gradlew :app:tasks --all

# 3. Xem task report: các path, mô tả, kiểu task và options (nếu có)
./gradlew help --task report

# 4. Xem task graph dự kiến mà không chạy actions của task
./gradlew :app:report --dry-run --console=plain
~~~

Cách đọc kết quả:

- `projects` giúp kiểm tra project thực sự được khai báo ở path nào. Đừng đoán tên project theo tên thư mục trong IDE.
- `:app:tasks --all` giúp kiểm tra `:app` có task nào và tên đầy đủ là gì. Lệnh `tasks` thông thường có thể chỉ hiển thị các task được nhóm; `--all` cho danh sách chi tiết hơn.
- `help --task report` trả thông tin task, có thể liệt kê **nhiều full paths** khi cùng tên tồn tại ở các module. Lệnh này **không chạy action của report**.
- `--dry-run` in các task Gradle dự định chạy nhưng bỏ qua các action của task; vẫn có giai đoạn cấu hình build, nên không coi nó là cam kết tuyệt đối rằng bất kỳ script cấu hình nào cũng không có side effect.

Trong ví dụ đã tạo, chạy:

~~~bash
./gradlew :app:report --dry-run --console=plain
~~~

Bạn sẽ thấy task được chọn có path `:app:report` và trạng thái `SKIPPED` trong kế hoạch dry-run; không có dòng `REPORT app` vì `doLast` không chạy. Dùng `--console=plain` làm log dễ đọc hơn trong terminal/CI. Với dự án có plugin hoặc dependency phức tạp, dry-run có thể hiển thị thêm các task phụ thuộc: điều cần xem là **task nào được chọn làm đích và các task nào đi cùng nó**.

Nếu không chắc hai task cùng tên có đến từ plugin hay script, `help --task tenTask` và `tasks --all` là điểm khởi đầu tốt; trong dự án lớn, bổ sung tìm kiếm chỗ `tasks.register`/`tasks.named` ở các build script sau khi đã xác định project liên quan.

## 8. Tình huống thực tế và cách chọn lệnh

| Nhu cầu | Lệnh gợi ý | Vì sao |
| --- | --- | --- |
| Chạy test chỉ cho module app | `./gradlew :app:test` | Khóa vào task `test` của app; giả định app có task `test`. |
| Chạy test cho app và lib | `./gradlew :app:test :lib:test` | Nêu rõ hai task đích; dễ đưa vào script. |
| Chạy mọi `test` phù hợp trong build từ root | `./gradlew test` | Dùng task selector có chủ đích. |
| Build riêng service API | `./gradlew :services:api:build` | Định danh đủ project lồng nhau. |
| Clean chỉ root | `./gradlew :clean` | Tránh vô tình chọn `clean` ở các subproject. |
| Clean mọi project có `clean` | `./gradlew clean` | Dùng selector toàn cây một cách cố ý. |
| Kiểm tra đường chạy trước khi thật sự chạy | `./gradlew :app:build --dry-run` | Xem task graph và các dependency dự kiến. |
| Chạy task tùy chỉnh cùng tên của lib | `./gradlew :lib:report` | Tránh trùng `report` ở root và app. |
| Kiểm tra tên task dài không nhớ chính xác | `./gradlew :app:tasks --all` | Tra tên đầy đủ, tránh viết tắt. |

Với CI, Jenkinsfile, GitHub Actions hoặc script nội bộ, nên lưu nguyên văn command với project path tuyệt đối, ví dụ:

~~~bash
./gradlew --no-daemon :app:test :lib:test --console=plain
~~~

`--no-daemon` là tùy chọn môi trường chạy, không ảnh hưởng cách phân giải path; có thể bỏ hoặc thêm tùy nhu cầu CI. Nếu chỉ cần test app, để nguyên `:app:test`; đừng viết `test` rồi kỳ vọng Gradle tự chọn module đúng theo tên job của CI. Trong log, tên task hiển thị dạng `> Task :app:test` giúp xác nhận task thực sự đã tham gia task graph.

## 9. Quy trình chọn task an toàn

1. **Xác định mục tiêu:** cần chạy task trên một module hay trên nhiều module? Nếu chỉ một, hãy dùng đường dẫn đầy đủ `:module:task`.
2. **Xác nhận project path:** chạy `./gradlew projects`, nhất là sau khi đổi cấu trúc multi-project hoặc đổi file settings.
3. **Xác nhận task name:** chạy `./gradlew :module:tasks --all` hoặc `./gradlew help --task taskName`; chọn tên đầy đủ, đúng chữ hoa/thường.
4. **Xem kế hoạch:** chạy `./gradlew :module:task --dry-run` nếu task có tác động lớn hoặc chưa chắc dependency graph.
5. **Thực thi bằng Wrapper:** chạy `./gradlew :module:task` từ root; trên Windows dùng `.\gradlew.bat :module:task`.
6. **Đọc log theo full path:** xem task được chạy và các dependency task; nếu có task ngoài dự kiến, kiểm tra selector, dependency, working directory hoặc cài đặt task.
7. **Cố định command trong automation:** tránh abbreviation và tránh task selector chung nếu thực ra chỉ muốn một project.

Quy trình này giải quyết cả hai nguy cơ: **selector chạy nhiều task cùng tên** và **tên viết tắt dẫn đến nhầm/mơ hồ**.

## 10. Lỗi thường gặp và hướng xử lý

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Chạy `./gradlew test` nhưng thấy `:app:test` và `:lib:test` | Dùng task selector không chỉ rõ project. | Nếu chỉ muốn app, dùng `./gradlew :app:test`; nếu muốn tất cả, đây là hành vi bình thường. |
| Chạy `./gradlew :test` báo không tìm thấy dù `:app:test` tồn tại | `:test` chỉ tìm task `test` **của root**. | Dùng `:app:test`, không bỏ phần project path. |
| Lệnh rút gọn báo task ambiguous | Nhiều task hoặc project khớp một abbreviation. | Mở `projects`/`tasks --all`, nhập đủ tên từng thành phần. |
| Chạy lệnh không có `:` từ hai thư mục khác nhau ra tập task khác nhau | Task selector phụ thuộc project context của working directory. | Chạy từ root và dùng `:module:task` tuyệt đối để rõ ngữ cảnh. |
| `Project 'api' not found` | Project path khai báo khác dự đoán; module lồng hoặc đổi tên. | Xem `settings.gradle.kts` và `./gradlew projects`, dùng path thực tế như `:services:api`. |
| `Task 'deploy' not found in project ':app'` | Task `deploy` chưa được đăng ký ở app, hoặc plugin không được áp dụng cho app. | Chạy `./gradlew :app:tasks --all`, kiểm tra build script/plugin của app. |
| Đã chỉ định `:app:build` nhưng log vẫn có task ở `:lib` | Task app có dependency vào task hoặc artifact ở lib. | Xem graph với `--dry-run`; phân biệt **task đích** với **task phụ thuộc**. |
| Chạy `./gradlew :app:tasks` thấy ít task hơn dự kiến | Danh sách mặc định tập trung vào task có nhóm hoặc task cơ bản. | Thử `./gradlew :app:tasks --all`; kiểm tra plugin/task registration. |
| Command trong CI chạy khác khi developer gõ bằng tay | Khác working directory, dùng Gradle toàn cục hoặc abbreviation. | Chuẩn hóa chạy từ root bằng Wrapper, path đầy đủ, cùng tham số. |
| Gõ `app/test` hoặc `:app/test` bị coi là task path sai | Dùng dấu `/` kiểu filesystem thay vì phân cách Gradle project path. | Sửa thành `:app:test`. |

## 11. Bài tập tự kiểm tra

Dùng đúng ví dụ ở mục 3 và tự xác định kết quả trước khi chạy:

1. Lệnh nào chỉ in `REPORT lib`? **`./gradlew -q :lib:report`**.
2. Lệnh nào chỉ in `REPORT root`? **`./gradlew -q :report`**.
3. Lệnh nào sẽ gọi đủ ba task `report` của root, app, lib từ root? **`./gradlew -q report`** (không cần giả định thứ tự in).
4. `./gradlew :app:checkAp` có an toàn không? **Không**. `checkApi` và `checkApp` cùng khớp tiền tố này; nên gọi trọn `:app:checkApi` hoặc `:app:checkApp`.
5. Lệnh nào cho biết `:app` thực sự có những task gì? **`./gradlew :app:tasks --all`**.
6. `./gradlew :app:report --dry-run` có in `REPORT app` từ `doLast` không? **Không**. Nó cho xem kế hoạch thực thi, không chạy action của task.
7. Có thể khẳng định chạy `:app:build` sẽ không chạy bất kỳ task nào của lib không? **Không**. Dependency graph của app có thể chứa task lib.

## Tài liệu tham khảo chính thức

- [Gradle Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): gọi task trong multi-project build, task selector, name abbreviation, `--dry-run`, `--info`, `tasks` và `help --task`.
- [Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html): project path, task name, task path đầy đủ và phạm vi gọi task theo tên.
- [Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): khai báo subproject, `include(...)` và ánh xạ đường dẫn project.
- [Gradle Task API](https://docs.gradle.org/current/dsl/org.gradle.api.Task.html): mỗi task thuộc một project và có path định danh.
