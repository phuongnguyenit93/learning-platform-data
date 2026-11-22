# Cú pháp chạy Gradle Wrapper và cách gọi một hoặc nhiều task

## 1. Mục tiêu: chạy đúng task bằng đúng phiên bản Gradle của dự án

Gradle làm việc thông qua **task**: mỗi task đại diện cho một công việc như biên dịch, kiểm thử, đóng gói, xóa kết quả build hoặc một thao tác tự định nghĩa. Khi làm việc trong một dự án đã có Gradle Wrapper, hãy ưu tiên gọi task bằng script Wrapper của dự án. Wrapper chọn bản phân phối Gradle được khai báo trong `gradle/wrapper/gradle-wrapper.properties`, giúp terminal của thành viên nhóm và CI sử dụng cùng phiên bản công cụ build.

Bài này tập trung vào **cú pháp lệnh**: cách chạy một task, nhiều task trong cùng lệnh, chỉ định đúng project chứa task, đặt tùy chọn và đọc kết quả thực thi.

Điều kiện ban đầu: dự án đã có đủ `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, `gradle/wrapper/gradle-wrapper.properties` và máy có Java tương thích với bản Gradle của dự án. Không cần cài Gradle toàn cục để chạy Wrapper; lần đầu có thể cần mạng để tải bản Gradle đã chọn.

## 2. Lệnh Wrapper trên Linux, macOS và Windows

Đứng tại thư mục gốc của dự án. Tên file chạy tùy theo shell:

| Hệ điều hành/shell | Ví dụ chạy task `help` | Ghi chú |
| --- | --- | --- |
| Linux hoặc macOS, terminal Bash/Zsh | `./gradlew help` | `./` chỉ rõ script ở thư mục hiện tại; script thường cần quyền thực thi |
| Windows Command Prompt | `gradlew.bat help` | Gọi file batch trong thư mục hiện tại |
| Windows PowerShell | `.\gradlew.bat help` | `.\` là đường dẫn tương đối tới file trong thư mục hiện tại |

Hai script là **hai điểm vào của cùng một Wrapper**, không phải hai hệ build khác nhau. Để thống nhất ví dụ, các phần sau dùng `./gradlew`; trên Windows thay bằng `.\gradlew.bat` trong PowerShell hoặc `gradlew.bat` trong Command Prompt.

Ví dụ mở đầu:

```bash
# Linux/macOS, tại thư mục gốc dự án
./gradlew --version
./gradlew help
./gradlew tasks
```

- `--version` cho biết bản Gradle thực sự được Wrapper khởi động.
- `help` gọi task hỗ trợ thông tin về Gradle.
- `tasks` liệt kê task được công bố cho build trong ngữ cảnh hiện tại.

Chú ý: dấu `$` thỉnh thoảng xuất hiện trong tài liệu là **ký hiệu prompt**, không phải phần cần nhập. Lệnh thực tế bắt đầu bằng `./gradlew` hoặc script Windows tương ứng.

## 3. Cấu trúc chung của một câu lệnh

Dạng tổng quát, nhìn từ terminal Unix:

```text
./gradlew [tùy-chọn-Gradle] [task-1] [tùy-chọn-riêng-task-1] [task-2] [tùy-chọn-riêng-task-2] ...
```

Trong đó:

- `./gradlew`: khởi động Gradle theo cấu hình Wrapper.
- `task-1`, `task-2`: tên hoặc đường dẫn task, chẳng hạn `build`, `clean`, `test`, `:app:build`.
- **Các task cách nhau bằng khoảng trắng**, không nối bằng dấu phẩy; một lần gọi Wrapper có thể nhận nhiều task.
- **Tùy chọn toàn cục của Gradle** như `--info`, `--stacktrace` và `--dry-run` nhìn chung có thể xuất hiện trước hoặc sau tên task.
- **Tùy chọn riêng của task** phải đặt ngay sau task mà nó áp dụng; không phải task nào cũng có tùy chọn riêng.

Ví dụ cú pháp hợp lệ:

```bash
./gradlew build
./gradlew clean build
./gradlew --info build
./gradlew build --info
./gradlew --console=plain clean build
```

`--console=plain` yêu cầu dạng log dễ đọc trong terminal/CI; `--info` hiển thị thêm thông tin xử lý. Các tùy chọn nhận giá trị thường có thể viết `--console plain` hoặc `--console=plain`; dùng dạng có `=` giúp rõ ràng.

Nếu **không ghi tên task**, Gradle có thể chạy các default task đã được cấu hình cho build. Để lệnh dễ hiểu và tái lập trong nhóm, nên gọi tên task cụ thể khi muốn một kết quả xác định.

## 4. Cách gọi đúng một task

Ví dụ phổ biến khi dự án đã áp dụng plugin phù hợp:

```bash
./gradlew build
./gradlew test
./gradlew clean
./gradlew :help
```

| Lệnh | Ý nghĩa |
| --- | --- |
| `./gradlew build` | Yêu cầu thực thi task/selector `build` trong ngữ cảnh project đang chạy; thường là chu trình build, nhưng chỉ tồn tại nếu plugin hoặc cấu hình cung cấp |
| `./gradlew test` | Yêu cầu thực thi task/selector `test`; thường chạy kiểm thử ở dự án Java |
| `./gradlew clean` | Yêu cầu task/selector `clean`; thường xóa output build đã tạo |
| `./gradlew :help` | Gọi chính xác task `help` ở root project, ký hiệu `:` là gốc của build |

**Một task được yêu cầu không có nghĩa chỉ một task được thực thi.** Nếu task `build` khai báo phụ thuộc vào các task khác, Gradle thực thi cả những task phụ thuộc cần thiết. Gradle tạo **task graph** rồi lên lịch thực thi các task trong graph; thứ tự và việc có chạy action hay không do dependency, quy tắc thứ tự, trạng thái up-to-date, cache và tùy chọn build quyết định.

Task cũng có thể được đăng ký riêng bằng Kotlin DSL hoặc Groovy DSL; không nên giả định mọi dự án đều có `build`, `test` hoặc task tùy chỉnh nào đó. Kiểm tra bằng `./gradlew tasks` hoặc `./gradlew help --task <tên-task>`.

## 5. Chạy nhiều task trong cùng một lần gọi Wrapper

Viết **các tên task liên tiếp, phân tách bằng dấu cách**:

```bash
# Thường xóa output cũ, sau đó thực hiện chu trình build
./gradlew clean build

# Yêu cầu cả đóng gói và kiểm tra, nếu những task này tồn tại
./gradlew assemble check

# Yêu cầu hai task trên cùng một dòng
./gradlew test jacocoTestReport
```

Ví dụ cuối chỉ chạy khi build có cấu hình task `jacocoTestReport`, thường do plugin JaCoCo cung cấp. Tương tự, `assemble` và `check` là các lifecycle task thường gặp trong build có plugin phù hợp, không phải task mặc định của mọi build trống.

**Điểm khác giữa nhiều task trong một lần gọi và nhiều lần gọi riêng:**

- `./gradlew clean build` tạo một lần khởi động Gradle và một task graph chứa các task được yêu cầu cùng dependency của chúng.
- Chạy `./gradlew clean` rồi mới chạy `./gradlew build` là hai lần gọi Gradle riêng, mỗi lần có bước khởi động/cấu hình và task graph riêng.
- Trong một task graph, một task cụ thể được lên lịch thực thi **tối đa một lần** trong invocation đó, kể cả khi nhiều task được yêu cầu cùng phụ thuộc vào nó.

Thứ tự ở command line thể hiện ý định và Gradle tôn trọng tính an toàn của thứ tự đó, chẳng hạn `clean build` được hiểu là dọn trước khi tạo output mới. Tuy nhiên **không được suy luận rằng mọi dependency của task thứ nhất luôn hoàn thành trước khi bắt đầu bất kỳ task nào của task thứ hai**: Gradle có thể sắp xếp theo dependency graph và xử lý song song khi được phép. Khi công việc cần quan hệ nhân quả bắt buộc, hãy khai báo `dependsOn` hoặc quan hệ thứ tự phù hợp trong build script.

**Không dùng** `./gradlew clean,build`: Gradle không nhận dấu phẩy là dấu phân cách task. Tương tự, dấu `&&` thuộc cú pháp shell để nối **hai lệnh** riêng, không phải cú pháp liệt kê nhiều task của Gradle.

## 6. Ví dụ tự chạy: ba task với dependency rõ ràng

Với một dự án đã có Wrapper, có thể tạo một `build.gradle.kts` tối giản như sau, hoặc thêm vào build script của một dự án thực hành không trùng tên task:

```kotlin
// build.gradle.kts
tasks.register("prepareDemo") {
    doLast {
        println("prepare")
    }
}

tasks.register("compileDemo") {
    dependsOn("prepareDemo")
    doLast {
        println("compile")
    }
}

tasks.register("packageDemo") {
    dependsOn("compileDemo")
    doLast {
        println("package")
    }
}
```

Ở đây, `dependsOn` tạo chuỗi phụ thuộc `prepareDemo → compileDemo → packageDemo`. `doLast` khai báo hành động của task. Các tên chứa chữ "compile" và "package" trong ví dụ chỉ là tên **task minh họa**; chúng không tự biên dịch mã Java hay tạo JAR.

Chạy **một task đích**:

```bash
./gradlew -q packageDemo
```

Các dòng do task in ra:

```text
prepare
compile
package
```

Dù chỉ gõ `packageDemo`, Gradle vẫn chạy các task `compileDemo` và `prepareDemo` mà nó phụ thuộc vào. Tùy chọn `-q` (quiet) giảm log Gradle để dễ quan sát `println`.

Chạy **hai task đích** trong cùng lần gọi:

```bash
./gradlew -q compileDemo packageDemo
```

Output do các task in ra **vẫn là**:

```text
prepare
compile
package
```

`compileDemo` không in hai lần: nó đã nằm trong task graph và không được chạy lặp khi `packageDemo` cũng phụ thuộc vào nó. Có thể kiểm tra graph dự kiến bằng `./gradlew compileDemo packageDemo --dry-run` mà không chạy các hành động `doLast`.

Ví dụ này minh họa chính xác ba điều: tên task là tên được đăng ký trong build script; task phụ thuộc được tự động đưa vào graph; nhiều task trên CLI không khiến một task chung bị lặp lại trong cùng invocation.

## 7. Chỉ định task trong dự án đa module

Một build đa project có thể chứa root project và các subproject như `app`, `library` hoặc `services:api`. Đường dẫn task đầy đủ dùng dấu hai chấm `:` để phân tách các cấp:

```text
:app:build
:library:test
:services:api:check
```

Khi đứng ở thư mục **root project**, dùng các lệnh sau:

```bash
# Task build chỉ ở project :app
./gradlew :app:build

# Task test chỉ ở project :library
./gradlew :library:test

# Hai task cụ thể ở hai project khác nhau, cùng một invocation
./gradlew :app:build :library:test

# Task root project, khi root có task test
./gradlew :test
```

Không có dấu `:` đầu tiên cũng có thể hợp lệ khi gọi từ root, chẳng hạn `./gradlew app:build`; dạng `:app:build` rõ ràng hơn khi viết tài liệu hoặc CI.

**Phân biệt tên trần với đường dẫn tuyệt đối:**

- `./gradlew :app:test`: chọn task `test` của project `:app`, cùng các dependency cần thiết.
- `./gradlew :test`: chọn task `test` ở **root project**, nếu task đó tồn tại.
- `./gradlew test`: là task selector theo tên. Khi gọi tại root của build đa project, nó có thể chạy task `test` ở các project con có task đó, chứ không nhất thiết chỉ ở root.

Một số task báo cáo như `help` hoặc `dependencies` có cơ chế chọn project đặc biệt. Vì vậy, muốn biết chính xác tác động của lệnh trên build đa module, hãy xem `./gradlew projects`, `./gradlew tasks --all` và dùng đường dẫn task cụ thể thay cho phỏng đoán.

Nếu đang đứng trong thư mục `app/`, có thể gọi `../gradlew test` trên Unix; khi cần tránh mơ hồ, dùng `../gradlew :app:test`. Lưu ý vị trí hiện tại và đường dẫn script Wrapper là hai vấn đề khác nhau.

## 8. Các tùy chọn hữu ích khi chạy một hoặc nhiều task

| Tùy chọn | Tác dụng | Ví dụ |
| --- | --- | --- |
| `-m` hoặc `--dry-run` | Hiển thị task nào sẽ được lên lịch; bỏ qua action của task | `./gradlew clean build --dry-run` |
| `--info` | Mở rộng log thực thi | `./gradlew test --info` |
| `--stacktrace` | Hiện stack trace khi có lỗi Gradle | `./gradlew build --stacktrace` |
| `--console=plain` | Dùng output thuần, thuận tiện cho log CI | `./gradlew build --console=plain` |
| `-x test` hoặc `--exclude-task test` | Loại task `test` khỏi việc thực thi theo lựa chọn loại trừ | `./gradlew build -x test` |
| `--continue` | Tiếp tục các task còn có thể chạy sau khi có lỗi; build vẫn thất bại nếu tồn tại lỗi | `./gradlew test check --continue` |
| `--rerun-tasks` | Buộc chạy lại task actions, bỏ qua kiểm tra up-to-date cho các task được chọn | `./gradlew test --rerun-tasks` |
| `--offline` | Yêu cầu Gradle làm việc ngoại tuyến với dependency đã có trong cache | `./gradlew test --offline` |
| `-Pkey=value` | Cung cấp project property khi build có sử dụng thuộc tính đó | `./gradlew build -Penv=dev` |

**Đọc đúng ý nghĩa:**

- `--dry-run` hữu ích để xem task graph trước khi thực thi; nó không chạy action và không xác nhận rằng code/test sẽ thành công. Wrapper vẫn có thể cần khởi động/tải Gradle, còn bước cấu hình build vẫn có thể thực hiện.
- `-x test` có thể **bỏ qua kiểm thử quan trọng**; chỉ dùng khi hiểu hậu quả, không xem đó là cách khắc phục một test bị lỗi.
- `--continue` không biến build có lỗi thành build thành công: các task phụ thuộc vào task thất bại vẫn không thể tiếp tục bình thường; Gradle tổng hợp lỗi vào cuối.
- `--offline` không bảo đảm mọi phụ thuộc đã có sẵn. Lần tải bản phân phối Wrapper hoặc dependency chưa được cache có thể thất bại.

## 9. Tùy chọn riêng của task phải đi sát task đó

Task có thể khai báo command-line option riêng. Ví dụ, với một dự án Java có task `Test` tên `test`, tùy chọn `--tests` lọc test class hoặc method:

```bash
# Java Test task phải tồn tại và có test phù hợp
./gradlew test --tests "com.example.CalculatorTest"

# Task trong subproject cụ thể
./gradlew :app:test --tests "com.example.CalculatorTest"
```

`--tests` là tùy chọn của **task Test** được cung cấp trong ngữ cảnh thích hợp, không phải tùy chọn dùng được cho tất cả task. Nếu chạy nhiều task có tùy chọn riêng, đặt option của từng task ngay sau tên task tương ứng:

```text
./gradlew taskA --optionCuaA=value taskB --optionCuaB=value
```

Ví dụ `taskA`/`taskB` ở trên là **mẫu cú pháp**, chỉ hợp lệ khi build đăng ký các task và option ấy.

Khi tên tùy chọn của task trùng một tùy chọn toàn cục của Gradle (như `--profile`), Gradle cho phép dấu phân cách `--` trước tên task để phân biệt:

```text
./gradlew [tùy-chọn-Gradle] -- tenTask --tùy-chọn-riêng-của-task=value
```

Đây là cú pháp đặc biệt cần dùng khi có xung đột tên option, không cần thêm `--` vào mọi lệnh thông thường. Để xem một task có option nào, dùng `./gradlew help --task tenTask`.

## 10. Kiểm tra task tồn tại và xem lệnh sẽ làm gì

Trước khi chạy lệnh chưa quen hoặc chạy build lớn trên CI, nên xem thông tin trước:

```bash
# Danh sách các project
./gradlew projects

# Các task được công bố
./gradlew tasks

# Liệt kê rộng hơn, có thể gồm task không được hiển thị mặc định
./gradlew tasks --all

# Thông tin của một task cụ thể
./gradlew help --task build

# Xem các task được chọn và dependency mà không chạy action
./gradlew clean build --dry-run
```

Lưu ý `help --task build` có thể hiện nhiều đường dẫn nếu các project khác nhau cùng có task `build`. Khi một lệnh ngắn không chỉ ra rõ module, thông tin này giúp quyết định nên dùng `:app:build`, `:library:build` hay task selector `build`.

Gradle hỗ trợ viết **tên task rút gọn** nếu chuỗi viết tắt xác định được duy nhất task phù hợp, bao gồm một số kiểu camel case. Ví dụ đôi khi `che` có thể được hiểu là `check`. Tuy nhiên cách viết tắt dễ gây mơ hồ khi bổ sung plugin/task, vì vậy trong script, tài liệu và CI nên ghi **đầy đủ tên task và project path**.

## 11. Thứ tự thực thi, lỗi và giá trị trả về

Giả sử người dùng gõ:

```bash
./gradlew clean build
```

Gradle phân tích hai task yêu cầu, giải quyết dependency và xây dựng task graph. `clean`/`build` là những task do plugin phù hợp cung cấp. Những task như compile/test/package có thể được kéo theo bởi `build`; mỗi task chung chỉ được lên lịch tối đa một lần trong invocation. Gradle tôn trọng yêu cầu thứ tự an toàn của command line, nhưng thứ tự chính xác giữa các task phụ thuộc vào graph và các ràng buộc thực thi.

Nếu cần task B **luôn đợi** task A, trong build script có thể biểu diễn dependency `B.dependsOn(A)`. Nếu chỉ cần ưu tiên thứ tự khi cả hai được thực thi, có thể dùng quan hệ `mustRunAfter`. Chúng phục vụ mục đích khác nhau; chỉ viết tên theo thứ tự trên command line không thay thế hoàn toàn cấu hình task.

Theo mặc định, khi một task thất bại, Gradle ngừng phần công việc còn lại có liên quan; dùng `--continue` để tiếp tục những task độc lập còn có thể chạy. Trong terminal hoặc CI, **exit code khác 0** cho biết invocation thất bại. Không đánh giá thành công chỉ vì một vài task đã hoàn tất.

Đừng tự suy luận stdout cố định của các lệnh `build`, `test` hay `clean` từ tên task: output và kết quả phụ thuộc plugin, dependency, hệ điều hành, Java, trạng thái cache và mã nguồn của dự án.

## 12. Các lỗi gõ lệnh thường gặp

| Tình huống | Vấn đề | Cách sửa |
| --- | --- | --- |
| Gõ `gradlew build` trên Linux/macOS và nhận `command not found` | Terminal không tự tìm script ở thư mục hiện tại | Gõ `./gradlew build` |
| Gõ `./gradlew build` và nhận `Permission denied` trên Unix | File `gradlew` chưa có quyền thực thi | Chạy `chmod +x gradlew` và lưu executable bit vào Git |
| Gõ `./gradlew build,test` | Dấu phẩy không phân cách task | Dùng `./gradlew build test` |
| Gõ tên task không tồn tại | Plugin/configuration chưa tạo task ấy hoặc sai chính tả | Xem `./gradlew tasks --all` và `help --task` |
| Gọi `test` ở root và chạy test nhiều module ngoài ý muốn | `test` là selector ở build đa project | Chỉ định `:app:test` hoặc đường dẫn cần thiết |
| Gọi `:test` khi chỉ subproject có task `test` | `:test` chỉ root project | Dùng `:app:test` hoặc task selector phù hợp |
| Task option bị nhận là option của Gradle, hoặc đặt sai vị trí | Nhầm option toàn cục với option riêng của task | Đặt task option sát tên task; khi có xung đột dùng `--` phân cách |
| Dùng `--dry-run` rồi tưởng kiểm thử đã chạy | `--dry-run` không thực thi action | Chạy lại không có `--dry-run` để kiểm chứng thật |
| Chạy `build -x test` rồi kết luận test đã PASS | `-x` loại test khỏi task graph | Chạy `test` thực sự khi cần chứng minh kiểm thử |
| Một task xuất hiện trong nhiều dependency nhưng chỉ chạy một lần | Gradle hợp nhất task chung trong cùng graph | Đây là hành vi đúng; không tách thành nhiều invocation chỉ để ép chạy lặp |

Nếu lệnh thất bại trước cả khi task được lập lịch, xác định tầng gây lỗi: không tìm thấy script → không khởi động được Java/Wrapper → không tải được Gradle → lỗi cấu hình build → lỗi không tìm thấy task → lỗi action/dependency. Chỉ sửa phần thuộc đúng nguyên nhân.

## 13. Quy trình thực hành gợi ý

Với một repository Gradle vừa clone, hãy thực hiện:

1. Ở root repository, xác định script Wrapper phù hợp hệ điều hành và xem bản Gradle bằng `./gradlew --version`.
2. Dùng `./gradlew projects` để hiểu root/subproject, rồi `./gradlew tasks --all` để xác định task thực tế.
3. Chạy thử **một task** đã biết như `./gradlew :app:build` hoặc `./gradlew help` nếu chưa chắc plugin đã có `build`.
4. Dùng `./gradlew clean build --dry-run` để kiểm tra các task sẽ được đưa vào graph, nếu `clean` và `build` tồn tại.
5. Chạy **nhiều task thật** bằng `./gradlew clean build`; kiểm tra exit code và log lỗi nếu có.
6. Khi cần chạy chính xác nhiều module, chỉ định `./gradlew :app:test :library:test` thay vì dùng selector `test` không chủ đích.
7. Đưa các lệnh có tác động kiểm thử/build vào tài liệu dự án hoặc CI với tên task đầy đủ, option đúng vị trí và đường dẫn module rõ ràng.

**Ghi nhớ:** một task được gọi bằng `./gradlew tenTask`; nhiều task bằng `./gradlew task1 task2`; task của module cụ thể bằng `./gradlew :module:tenTask`. Gradle tự giải quyết các dependency để thực thi task graph, hợp nhất task chung trong một invocation. Tùy chọn toàn cục điều khiển Gradle; tùy chọn riêng phải đi sát task mà nó áp dụng.

## Tài liệu chính thức

- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): cú pháp lệnh, nhiều task, thứ tự, option, `--dry-run` và `--continue`.
- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds_intermediate.html): đường dẫn task và task selector ở build đa project.
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): `dependsOn` và các quy tắc thứ tự.
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): cách chạy Wrapper trên các hệ điều hành.
