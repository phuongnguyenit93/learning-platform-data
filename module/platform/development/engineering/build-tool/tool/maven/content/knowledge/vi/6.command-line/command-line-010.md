# Đọc mã thoát thay vì chỉ dựa vào dòng BUILD SUCCESS

Khi chạy Maven trong terminal hoặc CI/CD, nhiều người nhìn dòng `[INFO] BUILD SUCCESS` ở cuối log rồi kết luận rằng tất cả đã thành công. Dòng tổng kết này hữu ích với người đọc, nhưng **chương trình và hệ điều hành giao tiếp với nhau bằng mã thoát (exit code/exit status)**. Shell, script và CI runner cần dùng trạng thái của tiến trình đã chạy để quyết định tiếp tục, dừng hoặc báo lỗi.

**Quy tắc thông thường:** mã thoát `0` nghĩa là tiến trình tự báo thành công; **mã khác `0`** nghĩa là tiến trình báo lỗi hoặc kết thúc bất thường. Với một lần Maven build bình thường, `BUILD SUCCESS` thường đi cùng mã `0`, còn `BUILD FAILURE` thường đi cùng mã khác `0`. Tuy vậy, hai tín hiệu có thể khác nhau khi có script bọc, pipeline, hoặc tùy chọn cố ý bỏ qua lỗi như `--fail-never`.

Bài này hướng dẫn đọc đúng mã thoát trên Linux/macOS, Windows PowerShell và CMD; xử lý các lệnh chuyển log qua `tee`; phân biệt trạng thái Maven với trạng thái script/CI; và xác minh rằng “lệnh thành công” cũng thực sự đáp ứng điều kiện kiểm thử hoặc phát hành.

## 1. Phân biệt log, mã thoát và kết quả nghiệp vụ

Một lần chạy Maven tạo ra ít nhất hai loại thông tin:

```text
       mvn -B clean verify
                |
          tiến trình Maven
            /         \
           /           \
      stdout/stderr   mã thoát
       (văn bản)       (số)
           |             |
     log, nguyên nhân   shell / CI nhận trạng thái
     lỗi, thời gian     để quyết định tiếp tục
```

| Nguồn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Log Maven | `[INFO] BUILD SUCCESS` | Maven ghi thông báo tổng kết build để người đọc theo dõi. |
| Log Maven | `[INFO] BUILD FAILURE` | Maven ghi thông báo tổng kết lỗi, cần xem log chi tiết. |
| Exit code | `0` | Tiến trình gọi trả trạng thái thành công theo quy ước. |
| Exit code | `1` hoặc mã khác `0` | Tiến trình gọi báo thất bại; không nên mặc định mọi lỗi chỉ trả `1`. |
| Báo cáo plugin test | `target/surefire-reports` | Bằng chứng về test đã chạy, thất bại hoặc bị bỏ qua, khi plugin tương ứng được sử dụng. |
| Artifact | `target/*.jar` hoặc đầu ra khác | Bằng chứng về thứ đã được đóng gói; không tự chứng minh mọi điều kiện phát hành đã đạt. |

Một đoạn tổng kết log điển hình có thể trông như sau:

```text
[INFO] ------------------------------------------------------------------------
[INFO] BUILD SUCCESS
[INFO] ------------------------------------------------------------------------
```

Đây là **mẫu log minh họa**, không phải stdout đầy đủ hoặc cố định của lệnh Maven. Nội dung, thời gian, màu sắc và các dòng bổ sung thay đổi theo phiên bản Maven, plugin và môi trường.

Khi công việc được tự động hóa, cần phân biệt ba câu hỏi:

1. **Tiến trình Maven báo gì?** Đọc mã thoát của `mvn` hoặc `mvnw`.
2. **Maven đã làm những gì?** Xem mục tiêu/phase, log và cấu hình plugin.
3. **Công việc đã đạt yêu cầu chưa?** Xem số test thực thi, artifact, checksum, bước upload hoặc những tiêu chí cần thiết của pipeline.

Mã thoát là tín hiệu chính để điều khiển luồng, nhưng nó chỉ có ý nghĩa trong phạm vi những gì lệnh thực tế được cấu hình thực hiện.

## 2. Tại sao không nên chỉ tìm chuỗi BUILD SUCCESS?

Giả sử một script chỉ kiểm tra log:

```bash
mvn clean verify > build.log 2>&1
grep -q 'BUILD SUCCESS' build.log
```

Đây không phải cách tốt để truyền trạng thái Maven cho CI: cuối script, mã thoát có thể là trạng thái **`grep`**. Một số tình huống dễ gây nhầm:

- Log bị **append** nhiều lần, chứa `BUILD SUCCESS` của lần chạy trước hoặc của một lệnh khác.
- Một plugin, script hoặc chương trình con in chuỗi `BUILD SUCCESS` như một phần nội dung văn bản.
- Maven hoàn tất nhưng **bước sau** đó (copy file, đóng gói image, ký artifact, upload) thất bại. Log Maven vẫn có `BUILD SUCCESS`, nhưng cả job không hoàn thành.
- Script gọi Maven, sau đó gọi `echo` và thoát với mã `0` của `echo`, khiến lỗi Maven bị che.
- Một lệnh pipeline như `mvn ... | tee build.log` có thể trả kết quả của `tee` thay cho Maven.
- Maven nhận cờ `-fn` / `--fail-never` và cố tình trả trạng thái thành công đối với lỗi build mà nó đã được yêu cầu bỏ qua.

Vì vậy, **không so sánh log bằng chuỗi để thay thế việc đọc exit code**. Hãy lưu exit code của đúng tiến trình; dùng log để giải thích nguyên nhân, sau đó xác minh các sản phẩm cần có.

## 3. Đọc mã thoát Maven trên Bash (Linux/macOS)

### 3.1. `$?` phải được đọc ngay sau lệnh

Trong Bash, `$?` chứa mã thoát của lệnh hoặc pipeline foreground vừa hoàn tất. Ví dụ:

```bash
mvn -B -ntp clean verify
maven_status=$?

printf 'Maven exit code: %s\n' "$maven_status"
```

`-B` (batch mode) thích hợp cho tác vụ không tương tác; `-ntp` (no transfer progress) giảm log trạng thái tải dependency trên các phiên bản Maven hỗ trợ. `clean verify` yêu cầu dọn đầu ra cũ rồi chạy đến pha `verify` của vòng đời Maven.

**Thứ tự có ý nghĩa.** Trong đoạn sau:

```bash
mvn -B -ntp clean verify
echo 'Đã chạy lệnh Maven'
maven_status=$?
```

`maven_status` đang nhận trạng thái của `echo`, thường là `0`, **không còn là trạng thái Maven**. Đừng chạy thêm lệnh nào trước khi lưu `$?`.

Nếu cần kết thúc script với đúng trạng thái Maven:

```bash
#!/usr/bin/env bash

mvn -B -ntp clean verify
maven_status=$?

printf 'Maven returned: %s\n' "$maven_status"
exit "$maven_status"
```

Ví dụ này giả định script **không bật `set -e`**. Nếu bật `set -e`, Bash có thể dừng sớm khi Maven thất bại và không chạy tới phép gán status. Khi cần thực hiện xử lý lỗi trước khi thoát, dùng mẫu `if`.

### 3.2. Dùng `if` để kiểm tra và giữ mã gốc

```bash
#!/usr/bin/env bash

if mvn -B -ntp clean verify; then
    printf '%s\n' 'Maven trả mã 0'
else
    maven_status=$?
    printf 'Maven thất bại, exit code=%s\n' "$maven_status" >&2
    exit "$maven_status"
fi
```

Lệnh Maven là điều kiện của `if`. Khi nó trả `0`, chạy nhánh `then`; khi trả nonzero, chuyển sang `else`, tại đó `$?` là mã từ lệnh điều kiện vừa thất bại. Cấu trúc này cũng thuận tiện cho script có `set -e` vì lệnh trong điều kiện `if` là một ngoại lệ với cơ chế dừng khi gặp lỗi.

Một bẫy khác là viết:

```bash
if ! mvn -B -ntp verify; then
    printf 'Code: %s\n' "$?"
fi
```

Toán tử `!` **đảo kết quả**. Nếu Maven trả nonzero, biểu thức `! mvn ...` thành công và `$?` trong nhánh `then` thường là `0`. Nếu muốn giữ mã Maven gốc, dùng `if mvn ...; then ... else maven_status=$?; fi`.

### 3.3. Ví dụ minh họa chính xác sự khác biệt

Các lệnh dưới đây **không chạy Maven**; chúng cố ý in nội dung và trả một exit code để thấy hai kênh độc lập.

```bash
(
    printf '%s\n' 'BUILD SUCCESS'
    exit 7
)
printf 'Exit code: %s\n' "$?"
```

**Stdout chính xác:**

```text
BUILD SUCCESS
Exit code: 7
```

Ngược lại:

```bash
(
    printf '%s\n' 'BUILD FAILURE'
    exit 0
)
printf 'Exit code: %s\n' "$?"
```

**Stdout chính xác:**

```text
BUILD FAILURE
Exit code: 0
```

Trong hai ví dụ, subshell chủ động quyết định mã trả về; chuỗi chữ trên màn hình không tự thay đổi mã đó. Kết luận cũng áp dụng khi script của bạn in một thông báo thành công dù chương trình bên trong đã lỗi.

## 4. Ghi log ra file mà vẫn giữ đúng trạng thái

### 4.1. Redirect `stdout` và `stderr`

```bash
mvn -B -ntp clean verify > build.log 2>&1
maven_status=$?

tail -n 30 build.log
printf 'Maven exit code: %s\n' "$maven_status"
exit "$maven_status"
```

`> build.log` tạo/ghi đè log; `2>&1` chuyển cả stderr vào cùng file. Giá trị `maven_status` đã được lưu **trước `tail`**, nên trạng thái cuối cùng vẫn phản ánh Maven. Điều này quan trọng vì `tail` thành công không đồng nghĩa Maven thành công.

Nếu muốn lưu riêng stdout và stderr, có thể redirect ra hai file, nhưng vẫn phải lưu trạng thái ngay sau Maven. Khi dùng CI, cần chú ý nơi lưu trữ log sau khi job kết thúc; file trên runner không tự động trở thành artifact dài hạn.

### 4.2. Cẩn thận với `tee` và pipeline

Một lệnh tiện lợi là:

```bash
mvn -B -ntp clean verify 2>&1 | tee build.log
```

Nó hiển thị log lên màn hình và lưu vào file. Tuy nhiên, **mặc định Bash lấy mã thoát của lệnh cuối cùng trong pipeline**, tức `tee`. Khi Maven lỗi nhưng `tee` ghi file thành công, `$?` của pipeline có thể là `0`.

Trong Bash, dùng `pipefail`:

```bash
#!/usr/bin/env bash

set -o pipefail

mvn -B -ntp clean verify 2>&1 | tee build.log
pipeline_status=$?

printf 'Pipeline exit code: %s\n' "$pipeline_status"
exit "$pipeline_status"
```

Khi bật `pipefail`, pipeline chỉ trả `0` nếu **mọi lệnh trong pipeline thành công**. Nếu có lỗi, trạng thái là mã của lệnh thất bại nằm xa bên phải nhất. Như vậy, lỗi Maven không bị một `tee` thành công che khuất.

Cần phân biệt:

- Muốn runner **thất bại nếu Maven hoặc ghi log lỗi**: `pipefail` là lựa chọn phù hợp.
- Muốn biết **riêng mã Maven và riêng mã `tee`**: dùng mảng `PIPESTATUS` đặc thù của Bash.

Ví dụ dưới đây giả định không bật `set -e` để có thể tiếp tục sau pipeline lỗi:

```bash
mvn -B -ntp clean verify 2>&1 | tee build.log
statuses=("${PIPESTATUS[@]}")

maven_status="${statuses[0]}"
tee_status="${statuses[1]}"

printf 'Maven=%s, tee=%s\n' "$maven_status" "$tee_status"

if (( maven_status != 0 || tee_status != 0 )); then
    exit 1
fi
```

Ngay sau pipeline, `PIPESTATUS[0]` là kết quả Maven, `PIPESTATUS[1]` là kết quả `tee`. **Phải lưu cả mảng ngay sau pipeline**; một lệnh khác có thể làm trạng thái bị thay đổi. `PIPESTATUS` là đặc điểm của Bash, không có cùng cú pháp trong POSIX `sh`.

### 4.3. `set -e` và `pipefail` không thay thế nhau

`set -e` thường làm Bash dừng khi một lệnh lỗi, nhưng có ngoại lệ trong điều kiện `if`, `while`, kết hợp `&&`, `||`, pipeline và một số ngữ cảnh hàm. Với pipeline, nếu thiếu `pipefail`, `set -e` có thể chỉ nhìn thấy status `0` của `tee`.

Một script Bash CI thường dùng:

```bash
#!/usr/bin/env bash
set -e
set -o pipefail

mvn -B -ntp clean verify 2>&1 | tee build.log
printf '%s\n' 'Maven verify completed.'
```

Nếu Maven trả nonzero, pipeline cũng trở thành nonzero và script dừng trước thông báo cuối. Nếu cần cleanup hoặc thu thập log sau lỗi, hãy dùng `if` và lưu status rõ ràng thay vì chỉ dựa vào `set -e`.

### 4.4. Các biểu thức dễ vô tình che lỗi

```bash
mvn -B -ntp verify || true
```

`true` luôn thành công, nên tổ hợp trên thường trả `0` kể cả khi Maven lỗi. Nó chỉ phù hợp khi yêu cầu rõ ràng là **bỏ qua lỗi**.

```bash
mvn -B -ntp verify
echo 'Build completed'
```

Nếu không kiểm tra kết quả ở giữa, mã thoát cuối script thường là trạng thái của `echo`. Khi viết wrapper script, hãy lưu status của Maven và `exit` với status đó hoặc dừng ngay khi phát hiện lỗi.

## 5. Windows PowerShell: dùng `$LASTEXITCODE`

Trong PowerShell, chương trình native như `mvn.cmd` hoặc `mvnw.cmd` trả mã thoát qua biến tự động **`$LASTEXITCODE`**.

Ví dụ file `verify.ps1` ở thư mục dự án có Maven Wrapper:

```powershell
& .\mvnw.cmd -B -ntp clean verify
$mavenCode = $LASTEXITCODE

Write-Host "Maven exit code: $mavenCode"

if ($mavenCode -ne 0) {
    Write-Host "Maven failed."
    exit $mavenCode
}

Write-Host "Maven succeeded."
exit 0
```

`&` là toán tử gọi lệnh; `.\mvnw.cmd` là script Wrapper trên Windows. Nếu Maven được cài ở `PATH`, có thể gọi `mvn.cmd` thay thế.

**Không nhầm `$?` với `$LASTEXITCODE`:**

- `$?` trong PowerShell là giá trị Boolean, cho biết câu lệnh PowerShell gần nhất có được coi là thành công hay không.
- `$LASTEXITCODE` là giá trị số từ chương trình native gần nhất mà PowerShell theo dõi. Nên lưu thành `$mavenCode` ngay sau lệnh Maven.

Các phiên bản PowerShell có điểm khác nhau trong việc chuyển lỗi native thành PowerShell error record. Không nên giả định `try/catch` tự bắt mọi trường hợp Maven trả nonzero. Kiểm tra `$LASTEXITCODE -ne 0` là cách trực tiếp, dễ hiểu và có thể truyền đúng mã thoát bằng `exit`.

Đoạn ví dụ dùng `exit` trong **script**. Nếu gõ `exit` trực tiếp ở cửa sổ PowerShell tương tác, nó có thể kết thúc phiên shell; lúc kiểm tra thủ công chỉ cần in giá trị biến.

## 6. Windows CMD / batch file: dùng `%ERRORLEVEL%`

Trong Windows Command Prompt, mã thoát của chương trình vừa chạy thường được lấy bằng `%ERRORLEVEL%`. Với một file `verify.cmd`:

```bat
@echo off
call mvnw.cmd -B -ntp clean verify
set "mavenCode=%ERRORLEVEL%"

echo Maven exit code: %mavenCode%
exit /b %mavenCode%
```

- `call` giúp batch file gọi `mvnw.cmd` rồi quay về script hiện tại để thực hiện tiếp.
- `set "mavenCode=%ERRORLEVEL%"` lưu kết quả ngay sau Maven.
- `exit /b %mavenCode%` kết thúc batch và trả đúng trạng thái cho caller.

Một điều kiện thường gặp:

```bat
call mvnw.cmd -B -ntp clean verify
if errorlevel 1 (
    echo Maven reported a positive nonzero exit code.
    exit /b 1
)
```

**`if errorlevel N` có nghĩa là “mã thoát lớn hơn hoặc bằng N”**, không phải bằng chính xác N. `if errorlevel 1` phù hợp với nhiều lỗi thông thường có mã dương; nếu muốn xử lý **mọi mã khác `0`**, kể cả các trường hợp đặc biệt, lưu `%ERRORLEVEL%` rồi so sánh giá trị và truyền lại như mẫu đầu.

Trong CMD, `%var%` được mở rộng khi phân tích khối ngoặc. Nếu đặt việc gán và đọc biến trong cùng một khối phức tạp, bạn có thể nhận giá trị cũ. Ví dụ trên cố ý đặt phép gán ngoài khối điều kiện để dễ kiểm soát.

## 7. Maven Wrapper: cùng một nguyên tắc, khác launcher

Maven có thể được khởi chạy bằng `mvn`/`mvn.cmd` cài trên máy hoặc bằng Maven Wrapper (`./mvnw`, `.\mvnw.cmd`) do dự án cung cấp.

Linux/macOS:

```bash
./mvnw -B -ntp clean verify
maven_status=$?
printf 'Wrapper exit code: %s\n' "$maven_status"
```

Windows PowerShell:

```powershell
& .\mvnw.cmd -B -ntp clean verify
$mavenCode = $LASTEXITCODE
Write-Host "Wrapper exit code: $mavenCode"
```

Wrapper chọn bản phân phối Maven theo cấu hình dự án; điều đó giúp đồng nhất phiên bản Maven giữa máy phát triển và CI. Nó **không miễn** trách nhiệm kiểm tra kết quả. Nếu Wrapper chưa tải được Maven, Java chưa phù hợp hoặc script khởi chạy lỗi, bạn vẫn cần dựa vào mã thoát mà tiến trình Wrapper thực sự trả.

Nếu một script gọi Wrapper rồi thực hiện các bước khác, trạng thái cuối của script là trạng thái **của script**, không nhất thiết giữ nguyên trạng thái Maven. Hãy truyền mã Maven lên caller hoặc có cơ chế xác định trạng thái tổng thể của công việc.

## 8. Maven có thể cố ý trả 0 dù build gặp lỗi: `-fn`

Một số cờ Maven thay đổi cách reactor xử lý lỗi khi build nhiều module:

| Cờ | Cách xử lý | Tác động cần nhớ |
| --- | --- | --- |
| `-ff` / `--fail-fast` | Dừng khi gặp project thất bại; là lựa chọn thông thường mặc định. | Lỗi build khiến toàn bộ invocation thất bại. |
| `-fae` / `--fail-at-end` | Tiếp tục những module không bị ảnh hưởng, rồi báo lỗi ở cuối. | Hữu ích để thu thập nhiều lỗi nhưng vẫn báo build thất bại. |
| `-fn` / `--fail-never` | Bỏ qua trạng thái thất bại của các project theo chế độ reactor. | **Có thể in `BUILD FAILURE` nhưng trả exit code `0`.** |

Ví dụ:

```bash
mvn -fn clean verify
```

Khi một module/test làm Maven build thất bại nhưng Maven đang ở chế độ `--fail-never`, log có thể ghi `BUILD FAILURE`, còn tiến trình trả `0`. Điều này là **hành vi được yêu cầu bởi cờ**, không phải lỗi ở Bash. Đừng dùng `-fn` cho cổng chất lượng mà CI bắt buộc phải nhận nonzero khi build hỏng.

Nếu muốn Maven cố gắng build nhiều module trước khi báo lỗi:

```bash
mvn -fae clean verify
```

`--fail-at-end` giúp xem nhiều lỗi hơn và cuối cùng vẫn trả trạng thái thất bại khi build thất bại.

Khi bạn thấy `BUILD FAILURE` nhưng shell lại nhận `0`, hãy kiểm tra `-fn` trong lệnh, `MAVEN_ARGS`, `.mvn/maven.config`, cấu hình IDE hoặc wrapper script. Nếu lệnh không có `-fn` nhưng vẫn trả `0`, tiếp tục tìm `|| true`, pipeline hoặc code bọc làm mất trạng thái.

**Lưu ý:** `--fail-never` điều khiển cách Maven xử lý lỗi build theo chế độ đã chọn; nó không phải bảo đảm rằng mọi sự cố khởi động launcher, quyền truy cập hoặc sự cố hệ điều hành đều luôn trả `0`.

## 9. Exit code 0 chưa chứng minh kiểm thử đã chạy

Ngay cả khi log có `BUILD SUCCESS` và mã thoát là `0`, bạn vẫn cần biết **Maven được yêu cầu làm gì**.

Ví dụ:

```bash
mvn -B -ntp -DskipTests package
```

Tùy chọn `-DskipTests` thường khiến các plugin kiểm thử Maven phổ biến **bỏ qua thực thi test**. Lệnh vẫn có thể kết thúc thành công nếu các bước còn lại không lỗi. Một tùy chọn khác, `-Dmaven.test.skip=true`, có thể yêu cầu bỏ cả việc biên dịch test với các plugin có hỗ trợ.

Một số plugin kiểm thử cũng cho phép bỏ qua trạng thái thất bại của test qua các tùy chọn như `testFailureIgnore`. Kết quả “lệnh Maven thành công” vì thế có thể không bằng “toàn bộ test đã vượt cổng chất lượng”.

Khi mục tiêu của CI là xác nhận mã nguồn sẵn sàng phát hành:

1. Chạy đúng phase, profile và tùy chọn đã phê duyệt, ví dụ `clean verify`.
2. Không dùng `-fn` hoặc cơ chế ignore failure cho bước bắt buộc.
3. Đọc exit code của Maven/Wrapper đúng cách.
4. Kiểm tra báo cáo test và số lượng test được thực thi nếu đây là tiêu chí bắt buộc, ví dụ `target/surefire-reports` hoặc `target/failsafe-reports` khi các plugin liên quan được chạy.
5. Xác nhận artifact và các bước sau build nếu pipeline yêu cầu.

**Exit code trả lời “lệnh thực sự báo thành công không?”.** Việc xác minh test/artifact trả lời “lệnh và cấu hình đó đã đáp ứng yêu cầu chất lượng chưa?”.

## 10. CI/CD: để runner nhận đúng trạng thái

Một runner CI thường coi bước command thất bại khi shell trả mã khác `0`. Vì vậy cần tránh viết script kết thúc bằng lệnh thành công dù Maven đã lỗi.

### 10.1. Một bước GitHub Actions đơn giản

Đây là **đoạn step** minh họa đặt trong `jobs.<job_id>.steps` của workflow; runner được giả định đã có JDK và Maven phù hợp:

```yaml
- name: Maven verify
  shell: bash
  run: |
    mvn -B -ntp clean verify
```

Khi Maven trả nonzero và không có cấu hình bỏ qua lỗi, bước thường được đánh dấu thất bại. Nếu dự án dùng Wrapper, thay `mvn` bằng `./mvnw`.

Nếu cần lưu log qua `tee`:

```yaml
- name: Maven verify with log
  shell: bash
  run: |
    set -o pipefail
    mvn -B -ntp clean verify 2>&1 | tee maven.log
```

Nếu bỏ `pipefail`, một `tee` thành công có thể che lỗi Maven. File log ở workspace runner cần bước upload artifact/log riêng nếu muốn giữ lại sau job.

### 10.2. Cleanup hoặc thu thập báo cáo sau khi Maven lỗi

Đôi khi CI phải thu thập log sau khi build thất bại. Mẫu Bash:

```bash
#!/usr/bin/env bash

if mvn -B -ntp clean verify; then
    maven_status=0
else
    maven_status=$?
fi

# Thu thập báo cáo/log ở bước phù hợp của CI.
# Không thay thế maven_status bằng trạng thái của lệnh cleanup.

exit "$maven_status"
```

Script lưu mã Maven trước khi chạy bước khác, rồi trả lại cho runner. Nếu các bước cleanup cũng có thể lỗi nghiêm trọng, pipeline cần quyết định cách tổng hợp trạng thái theo chính sách riêng.

### 10.3. Thành công của Maven chưa phải thành công của toàn bộ job

Ví dụ một quy trình gồm build, kiểm tra artifact và upload:

```text
Maven verify -> kiểm tra artifact -> ký/đóng gói -> upload
      0               0                0           nonzero
                       |
                  Maven đã thành công
              nhưng cả pipeline vẫn thất bại
```

Khi Maven báo `0` nhưng upload lỗi, **job phải báo lỗi** nếu upload là bước bắt buộc. Đừng dùng dòng `BUILD SUCCESS` xuất hiện giữa log làm căn cứ đánh dấu toàn bộ workflow thành công.

Ngược lại, nếu Maven lỗi, script cần dừng hoặc trả nonzero ngay cả khi các lệnh in log/cleanup thành công. Các cơ chế `continue-on-error` hoặc “allow failure” chỉ nên áp dụng khi chủ đích của quy trình cho phép bước thất bại.

## 11. Đọc mã thoát trong các trường hợp thực tế

| Mã thoát nhận được | Log hiển thị | Điều nên kiểm tra |
| --- | --- | --- |
| `0` | `BUILD SUCCESS` | Lệnh/phase, plugin test, artifact, yêu cầu phát hành. |
| Nonzero | `BUILD FAILURE` | Lỗi dependency, compiler, test, plugin, cấu hình hoặc môi trường trong log. |
| Nonzero | Có `BUILD SUCCESS` | Tiến trình khác trả lỗi, lỗi wrapper/`tee`/bước sau, log cũ hoặc log thuộc lần chạy khác. |
| `0` | Có `BUILD FAILURE` | `-fn`, `|| true`, `continue-on-error` hoặc script không truyền lại status. |
| `0` | Không thấy tổng kết | Log bị redirect, lệnh không thực thi build như mong đợi, plugin thay đổi output hoặc chỉ chạy thao tác khác. |
| Nonzero | Không thấy tổng kết | Có thể Maven/JVM chưa khởi động, tiến trình bị ngắt hoặc script thất bại trước khi Maven in tổng kết. |

Không mặc định mọi lỗi Maven trả đúng mã `1`. Đây là mã phổ biến trong nhiều tình huống, nhưng launcher, script, hệ điều hành hoặc tiến trình bọc có thể trả giá trị khác. Kiểm tra **bằng `== 0` hoặc `!= 0`** là tiêu chí thông dụng để điều khiển luồng.

Trên hệ thống Unix, các mã như `130`, `137`, `143` đôi khi liên quan tới tín hiệu kết thúc tiến trình, nhưng phải dựa vào shell/container và log thực tế để kết luận; một con số riêng lẻ không đủ chứng minh lỗi biên dịch Java.

## 12. Quy trình điều tra khi CI xanh nhưng build đáng ngờ

**Bước 1. Xem lệnh được gọi thật.** Xác định `mvn` hay `mvnw`, POM được chọn, phase, profile, các cờ `-fn`, `-DskipTests` và các cờ ignore failure. Cấu hình có thể đến từ script, `MAVEN_ARGS`, `.mvn/maven.config` hoặc CI.

**Bước 2. Xác định shell hay runner nhận mã nào.** Nếu CI gọi `./build.sh`, nó nhận exit code của script; cần kiểm tra script có bảo toàn trạng thái Maven không.

**Bước 3. Lưu exit code ngay sau Maven.** Bash dùng `$?`, PowerShell dùng `$LASTEXITCODE`, CMD dùng `%ERRORLEVEL%`. Tránh lệnh trung gian trước khi lưu.

**Bước 4. Kiểm tra pipeline và điều kiện.** Với `tee`, bật `pipefail` hoặc dùng `PIPESTATUS` trong Bash. Tìm `|| true`, `-fn` và lệnh `echo` cuối script.

**Bước 5. Đọc log của đúng lần chạy.** Tìm lỗi Maven/plugin thực sự; tránh lấy nhầm kết quả của một build trước đó hoặc của lệnh con.

**Bước 6. Kiểm tra đầu ra mong đợi.** Nếu yêu cầu test, kiểm tra báo cáo test; nếu yêu cầu JAR và publish, xác minh artifact và trạng thái upload. Trạng thái Maven chỉ phản ánh công việc mà Maven đã được cấu hình làm.

**Bước 7. Tái hiện có kiểm soát.** Dùng cùng bản Maven/Wrapper, JDK, POM, lệnh và profile. Lưu cùng lúc log và exit code để có bằng chứng liên quan tới cùng một tiến trình.

## 13. Những lỗi thường gặp

1. **Grep “BUILD SUCCESS” thay vì đọc exit code.** Chuỗi log không thay thế trạng thái tiến trình.
2. **Đọc `$?` sau `echo` hoặc `tail`.** Khi đó đã đọc trạng thái của lệnh khác.
3. **Dùng `if ! mvn` rồi đọc `$?` để lấy mã Maven.** Toán tử phủ định đã đảo trạng thái.
4. **Dùng `mvn | tee` mà không có `pipefail`.** Lỗi Maven có thể bị `tee` che.
5. **Tin rằng `set -e` tự xử lý mọi pipeline.** Nó có ngoại lệ và không thay thế `pipefail`.
6. **Nhầm `$?` của PowerShell là exit code số nguyên.** Dùng `$LASTEXITCODE` cho native process.
7. **Trong batch file, gọi `mvnw.cmd` rồi quên `call`.** Có thể không quay về script để kiểm tra trạng thái.
8. **Dùng `-fn` ở cổng kiểm tra bắt buộc.** Maven có thể trả `0` dù báo build thất bại.
9. **Nhìn exit `0` và cho rằng test đã chạy.** Cờ skip test và cấu hình plugin có thể thay đổi điều đó.
10. **Chỉ kiểm tra Maven mà bỏ qua bước sau.** Artifact publish hoặc deploy lỗi vẫn làm quy trình thất bại.
11. **Hardcode mã lỗi Maven luôn là `1`.** Mã nonzero cụ thể phụ thuộc lệnh và môi trường.
12. **Để script kết thúc bằng lệnh luôn thành công.** Mã thoát cuối script không còn phản ánh Maven nếu không truyền trạng thái đúng.

## 14. Bài tập tự kiểm tra

**Câu 1.** Trong Bash, `mvn clean verify | tee build.log` làm Maven thất bại nhưng `tee` thành công. Nếu không bật `pipefail`, `$?` thường là gì?

**Đáp án:** Thường là `0` vì đó là mã của lệnh cuối pipeline, tức `tee`. Muốn CI phát hiện lỗi Maven, bật `set -o pipefail` hoặc lấy `PIPESTATUS[0]` ngay sau pipeline.

**Câu 2.** Maven in `BUILD FAILURE` nhưng trả `0`. Lệnh có cờ `-fn`. Có nhất thiết là Maven bị lỗi không?

**Đáp án:** Không. `--fail-never` cố ý bỏ qua trạng thái thất bại của project build. Nếu muốn CI báo lỗi, loại cờ này; có thể dùng `-fae` nếu cần thu thập lỗi nhiều module nhưng vẫn thất bại ở cuối.

**Câu 3.** Trên PowerShell, bạn cần biết số mã thoát của `.\mvnw.cmd verify`. Đọc `$?` hay `$LASTEXITCODE`?

**Đáp án:** Dùng `$LASTEXITCODE` và lưu ngay vào biến, chẳng hạn `$mavenCode = $LASTEXITCODE`.

**Câu 4.** `mvn -DskipTests package` trả `0`. Có thể kết luận mọi test đã pass không?

**Đáp án:** Không. Lệnh có thể đã bỏ qua thực thi test. Kiểm tra cấu hình, báo cáo test và điều kiện chất lượng đang được yêu cầu.

**Câu 5.** Script chạy Maven rồi `echo "Done"` và không trả lại trạng thái Maven. Vì sao CI có thể xanh khi Maven lỗi?

**Đáp án:** Exit status cuối của script thường là status lệnh cuối, tức `echo`. Lưu mã Maven rồi trả lại bằng `exit "$maven_status"`, hoặc dùng `if` để dừng khi lỗi.

**Câu 6.** Maven báo `BUILD SUCCESS` và status `0`, nhưng bước upload JAR thất bại. Job nên được xem là gì?

**Đáp án:** Nếu upload là yêu cầu bắt buộc, toàn bộ job phải thất bại. Thành công của Maven chỉ xác nhận bước Maven đã hoàn tất theo cấu hình của bước đó.

## Tài liệu tham khảo chính thức

- [Apache Maven – CLI Options Reference](https://maven.apache.org/ref/current/maven-embedder/cli.html): `-B`, `-ntp`, `-ff`, `-fae`, `-fn` và các lựa chọn xử lý lỗi.
- [Apache Maven – Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): vai trò của `compile`, `test`, `package`, `verify`.
- [Apache Maven – Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor và xử lý thất bại của nhiều module.
- [GNU Bash Manual – Pipelines](https://www.gnu.org/software/bash/manual/html_node/Pipelines.html): exit status của pipeline và `pipefail`.
- [GNU Bash Manual – Bash Variables](https://www.gnu.org/software/bash/manual/html_node/Bash-Variables.html): mảng `PIPESTATUS`.
- [Microsoft Learn – PowerShell automatic variables](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_automatic_variables): `$LASTEXITCODE` và `$?`.
- [Microsoft Learn – CMD if](https://learn.microsoft.com/windows-server/administration/windows-commands/if): điều kiện `if errorlevel N`.
- [GitHub Docs – Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): cách chạy shell command trong CI.
