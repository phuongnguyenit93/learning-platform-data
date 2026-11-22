# Chế độ batch, giảm log tải xuống và lưu log vào tệp trong Maven

## 1. Vấn đề thực tế: chạy Maven ổn định và đọc được log

Khi chạy Maven bằng terminal, ta thường gặp ba nhu cầu khác nhau:

1. **Chạy tự động, không chờ người nhập**: đặc biệt trong CI/CD, container, script kiểm tra trước khi commit.
2. **Giữ log dễ đọc**: Maven có thể hiển thị tiến độ tải từng dependency và plugin; trên terminal hoặc CI, những dòng tiến độ làm log dài và khó tìm lỗi.
3. **Lưu chứng cứ build**: khi một job thất bại, đội phát triển cần mở lại toàn bộ log sau khi tiến trình đã kết thúc.

Apache Maven hỗ trợ trực tiếp ba tùy chọn dòng lệnh:

```text
-B,   --batch-mode            Chạy không tương tác
-ntp, --no-transfer-progress  Ẩn tiến độ download/upload artifact
-l,   --log-file <file>       Ghi output của Maven vào tệp
```

Có thể kết hợp:

```bash
mvn -B -ntp -l build-logs/verify.log clean verify
```

Lệnh ví dụ dùng một dự án Maven có `pom.xml` và giả định **thư mục `build-logs` đã tồn tại**. Maven chạy các pha build đến `verify`, trong chế độ batch; phần hiển thị tiến độ chuyển artifact bị ẩn; output build được ghi vào `build-logs/verify.log`.

**Ba cờ giải quyết ba vấn đề độc lập.** `-B` không có nghĩa là tắt tất cả log. `-ntp` không có nghĩa là ngừng tải dependency. `-l` không có nghĩa là build chắc chắn thành công.

## 2. Cấu trúc chung của một lệnh Maven

Một cách đọc lệnh thường gặp:

```text
mvn [tùy-chọn] [pha-lifecycle/goal]
```

Ví dụ:

```bash
mvn -B -ntp clean test
mvn --batch-mode --no-transfer-progress verify
mvn -B -ntp --log-file build-logs/maven.log package
```

- `mvn` là chương trình khởi động Maven trên máy.
- `-B`, `-ntp` và `-l` là **tùy chọn của Maven CLI**, không phải các goal.
- `clean`, `test`, `verify` và `package` là những pha/vòng đời build được yêu cầu thực hiện. Trong ví dụ `clean test`, Maven thực hiện vòng đời clean rồi chạy default lifecycle đến pha test.
- `--log-file` và `-l` là cách viết dài/ngắn của cùng một tùy chọn. Đường dẫn tệp phải theo ngay sau cờ.

Nếu repository có **Maven Wrapper**, có thể dùng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trên PowerShell/Windows thay `mvn`. Wrapper giúp thống nhất phiên bản Maven giữa máy cá nhân và CI; các tùy chọn CLI nêu ở đây vẫn truyền cho Maven được khởi chạy.

**Trước khi thao tác**, mở terminal tại thư mục chứa `pom.xml` hoặc chỉ rõ POM bằng `-f` nếu cần. Ví dụ `mvn -f project/pom.xml -B -ntp validate`. Không chạy lệnh từ thư mục tùy ý rồi mặc định Maven sẽ tự tìm đúng project.

## 3. Chế độ batch: `-B` và `--batch-mode`

`-B` yêu cầu Maven chạy **non-interactive/batch mode**. Điều này đặc biệt quan trọng khi script được chạy bởi runner CI không có người ngồi trả lời câu hỏi.

```bash
mvn -B clean verify
```

Hiệu quả chính:

- Maven hoạt động theo chế độ **không tương tác**; các thao tác Maven cần input từ người dùng không thể trông chờ một prompt có người trả lời.
- Tính ổn định của job tự động tốt hơn vì không vô tình đứng đợi nhập liệu.
- Trong Maven 3.9.x, chế độ batch cũng **vô hiệu hóa màu output mặc định** ở phía Maven, giúp log tệp/CI bớt chứa ký tự điều khiển màu.
- Build vẫn có `INFO`, `WARNING` và `ERROR` theo mức log thông thường; muốn bớt tiến độ tải, cần thêm `-ntp`.

**Giới hạn quan trọng:** `-B` không biến mọi plugin hoặc chương trình con thành tự động. Nếu plugin, bài test hoặc công cụ được gọi trong build đòi nhập mật khẩu, câu trả lời hay xác nhận theo cách riêng, nó vẫn có thể lỗi hoặc chờ input. Hãy cấu hình những bước đó theo cách không tương tác, dùng biến môi trường/secret và tùy chọn chính thức của công cụ tương ứng.

Maven cũng không mặc định bỏ qua test chỉ vì có `-B`. Ví dụ `mvn -B verify` vẫn thực hiện những bước và test tương ứng với lifecycle, POM và plugin của dự án.

### Khi nào cần `-B`?

| Tình huống | Có nên dùng? | Lý do |
| --- | --- | --- |
| CI/CD tự động | Có | Tránh phụ thuộc tương tác, log ổn định hơn |
| Script build trong container | Có | Dễ kiểm soát kết quả khi không có terminal tương tác |
| Chạy lệnh hằng ngày trên máy cá nhân | Tùy nhu cầu | Hữu ích nếu muốn hành vi giống CI |
| Goal cần input do plugin tùy chỉnh | Chưa đủ | Phải cấu hình plugin/tiến trình để không chờ người dùng |

## 4. Giảm log chuyển dữ liệu: `-ntp` và `--no-transfer-progress`

Maven thường phải tải plugin, dependency, metadata hoặc đẩy artifact lên repository. Trong những bản Maven hỗ trợ tùy chọn này, quá trình transfer có thể hiển thị tiến độ theo byte/phần trăm, làm log CI dài và lặp.

Dùng:

```bash
mvn -ntp clean verify
```

Hoặc:

```bash
mvn --no-transfer-progress clean verify
```

`-ntp` **không hiển thị tiến độ chuyển dữ liệu (transfer progress)** khi download hoặc upload. Nó **không**:
- cấm Maven kết nối mạng;
- chuyển sang chế độ offline;
- bỏ qua tải dependency/plugin chưa có;
- tắt log lỗi, cảnh báo hoặc thông báo build thông thường;
- làm bài test chạy nhanh hơn một cách được bảo đảm.

Khi cần build offline, Maven có tùy chọn khác là `-o`/`--offline`. Chế độ offline chỉ phù hợp khi cache cục bộ đã có đủ các thành phần build; nó có thể thất bại nếu thiếu artifact. **Không nhầm `-ntp` với `-o`.**

Ví dụ chạy Maven với thông tin build thường gặp mà không có thanh tiến độ tải:

```bash
mvn -B -ntp clean verify
```

Đây là lựa chọn hợp lý cho nhiều CI job vì vẫn giữ các dòng `INFO`, `WARNING` và `ERROR` để điều tra.

### Phân biệt `-ntp` với `-q` và `-X`

| Tùy chọn | Mục tiêu | Tác động tới thông tin chẩn đoán |
| --- | --- | --- |
| `-ntp` / `--no-transfer-progress` | Bỏ tiến độ download/upload | Vẫn giữ log build thông thường |
| `-q` / `--quiet` | Giảm mạnh log, chủ yếu còn lỗi | Có thể mất thông tin bối cảnh, tóm tắt pha và build |
| `-e` / `--errors` | Hiển thị chi tiết lỗi thực thi | Hữu ích khi cần stack trace lỗi |
| `-X` / `--debug` | Bật log debug rất chi tiết | Log lớn, có thể chứa dữ liệu nhạy cảm hoặc cấu hình nội bộ |

Thông thường, **hãy bắt đầu từ `-B -ntp`**, chỉ dùng `-q` khi thực sự muốn log rất ít. Khi điều tra lỗi khó, bỏ `-q` và cân nhắc `-e` hoặc `-X` cho lần chạy chẩn đoán có kiểm soát.

## 5. Lưu log vào tệp với `-l` / `--log-file`

Tùy chọn Maven CLI `-l` nhận **đường dẫn tệp log**:

```bash
mvn -B -ntp -l build-logs/verify.log clean verify
```

Tương đương:

```bash
mvn --batch-mode --no-transfer-progress --log-file build-logs/verify.log clean verify
```

Theo tài liệu Maven CLI, `--log-file` chuyển **build output** sang tệp và tắt màu output của Maven. Trong triển khai Maven 3.9.x, phần xử lý CLI chuyển cả stdout và stderr của tiến trình Maven sang file được chỉ định; vì vậy terminal thường không còn hiển thị những dòng log Maven thông thường sau khi chuyển hướng.

Điểm cần chú ý:

- `build-logs/verify.log` là **đường dẫn tệp**; Maven có thể tạo/ghi đè tệp, nhưng **không nên trông đợi Maven tự tạo mọi thư mục cha**. Tạo `build-logs` trước.
- Khi chạy nhiều lần với cùng tên, nội dung log cũ có thể bị **thay thế**. Dùng tên theo job/build nếu cần giữ lịch sử.
- Không nên ghi dưới `target/` nếu lệnh có pha `clean`: `mvn clean` có thể xóa toàn bộ thư mục `target` trong lúc tiến trình đang chạy, làm mất hoặc phá hỏng log đã mở trước đó.
- `-l` là cơ chế log của **tiến trình Maven**. Những dòng do shell, launcher, CI runner hoặc công cụ ngoài Maven phát ra **trước khi Maven khởi động** có thể không nằm trong tệp.
- Log được tạo **không chứng minh build thành công**; phải kiểm tra exit code và thông báo kết quả.

### Ví dụ Linux/macOS với Maven đã cài

```bash
mkdir -p build-logs
mvn -B -ntp --log-file build-logs/verify.log clean verify
```

Xem cuối file sau khi chạy:

```bash
tail -n 60 build-logs/verify.log
```

Nếu cần dùng Wrapper đã commit trong dự án:

```bash
mkdir -p build-logs
./mvnw -B -ntp -l build-logs/verify.log clean verify
```

Không cần thêm `> build-logs/verify.log 2>&1` vào chính lệnh đã dùng `-l`, vì hai cơ chế cùng ghi một tệp có thể gây nội dung khó đoán.

### Ví dụ Windows PowerShell với Maven Wrapper

```powershell
New-Item -ItemType Directory -Force -Path .\build-logs | Out-Null
.\mvnw.cmd -B -ntp --log-file .\build-logs\verify.log clean verify
$exitCode = $LASTEXITCODE

Get-Content .\build-logs\verify.log -Tail 60
Write-Host "Maven exit code: $exitCode"
```

Ví dụ giả định dự án có `mvnw.cmd` ở gốc. Trong PowerShell, biến `$LASTEXITCODE` giữ mã thoát của chương trình native vừa chạy; hãy lấy ngay sau lệnh Maven, trước khi chạy thêm chương trình native khác có thể thay đổi giá trị đó.

Nếu không dùng Wrapper, thay `.\mvnw.cmd` bằng `mvn` (hoặc `mvn.cmd` phù hợp `PATH`). Nếu `Get-Content` báo không có file, hãy kiểm tra đường dẫn, quyền ghi và lỗi khởi động trước khi kết luận Maven không có log.

## 6. Cách khác: chuyển hướng stdout và stderr bằng shell

Maven có `-l`, nhưng shell cũng có thể lưu output của bất kỳ chương trình nào.

Ví dụ Bash (Linux/macOS), **không sử dụng `-l`**:

```bash
mkdir -p build-logs
./mvnw -B -ntp clean verify > build-logs/verify.log 2>&1
```

Giải thích chính xác:
- `> build-logs/verify.log` chuyển **stdout (file descriptor 1)** sang tệp, thay thế nội dung cũ.
- `2>&1` chuyển **stderr (file descriptor 2)** sang cùng nơi mà stdout đang hướng tới.
- Thứ tự quan trọng: `> file 2>&1` là cách thông dụng để gộp hai stream của lệnh vào **một tệp**.
- `>> file 2>&1` là **append** thay vì overwrite; hữu ích khi muốn nối log, nhưng các lần build có thể lẫn nhau nếu không thêm tiêu đề/định danh.
- Lệnh vẫn trả exit code của Maven; việc chuyển hướng không tự biến thất bại thành thành công.

Với lựa chọn `-l`, Maven tự xử lý output log. Với chuyển hướng shell, shell quản lý các stream của tiến trình. Hai cách đều hữu ích; chọn **một cơ chế chính** phù hợp mục tiêu của script.

### Vừa xem trên màn hình vừa lưu file: `tee`

Nếu cần log xuất hiện trong console CI **và** có file để tải về, dùng `tee` trong Bash:

```bash
mkdir -p build-logs
set -o pipefail
./mvnw -B -ntp clean verify 2>&1 | tee build-logs/verify.log
```

- `2>&1` gộp stderr vào stdout.
- `tee` sao chép stream ra màn hình và lưu file.
- `set -o pipefail` khiến pipeline báo lỗi nếu Maven thất bại, thay vì chỉ nhìn exit code của `tee`. Dòng này dành cho **Bash và các shell hỗ trợ `pipefail`**, không phải cú pháp POSIX `sh` phổ quát.

Trong script CI chạy Bash, đây là một mô hình tốt khi muốn log trực tiếp kèm file artifact. **Đừng bỏ `pipefail`** nếu kết quả pipeline phải phản ánh lỗi Maven. Nếu dùng PowerShell, có thể dùng `Tee-Object` nhưng cần kiểm soát mã thoát chương trình native riêng; `--log-file` thường đơn giản hơn cho việc lưu file và chẩn đoán.

## 7. Tập thực hành nhỏ có thể tự kiểm chứng

Bài thực hành dưới đây tập trung vào CLI, nên chỉ cần một POM cơ bản. Tạo thư mục `maven-cli-log-demo` và file `pom.xml` như sau:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>maven-cli-log-demo</artifactId>
    <version>1.0.0</version>
</project>
```

Mở terminal tại thư mục này. Để kiểm tra khả năng đọc POM, **không cần thêm Java source**: pha `validate` chỉ cần mô hình Maven hợp lệ.

Bước 1 — Chạy thông thường:

```bash
mvn validate
```

Bước 2 — Bật batch và ẩn tiến độ transfer:

```bash
mvn -B -ntp validate
```

Bước 3 — Lưu output vào tệp:

```bash
mkdir -p build-logs
mvn -B -ntp -l build-logs/validate.log validate
```

Bước 4 — Mở file để xem nội dung:

```bash
cat build-logs/validate.log
```

Trong một môi trường Maven hoạt động bình thường, log thường có thông tin về project, goal/phase và kết quả build. **Không giả định số dòng, thời gian chạy hoặc các thông báo luôn giống nhau** vì chúng thay đổi theo phiên bản Maven, plugin, cache, hệ điều hành và cài đặt. Nếu phải tải plugin lần đầu, lệnh vẫn cần mạng dù đã có `-ntp`.

Bước 5 — Thử tình huống lỗi: cố ý chạy một goal không tồn tại (chỉ trên project thực hành), ví dụ:

```bash
mvn -B -ntp --log-file build-logs/failure.log definitely-not-a-goal
```

Lệnh trên dự kiến thất bại do yêu cầu goal/phase không hợp lệ. Kiểm tra **exit code khác 0** và mở `build-logs/failure.log` để xem nguyên nhân chính xác. Không cần đoán trước toàn bộ nội dung exception.

**Kết quả tự kiểm tra:** `-B` khiến Maven không chờ tương tác; `-ntp` giảm thông báo tiến độ chuyển artifact nếu có transfer; `-l` ghi log vào một tệp có thể mở lại; lỗi vẫn làm lệnh Maven trả về mã thất bại.

## 8. Giữ nguyên trạng thái thành công/thất bại trong script và CI

Một file log tồn tại có thể chứa **BUILD FAILURE**. Vì vậy CI phải kiểm tra mã thoát, thay vì chỉ kiểm tra sự tồn tại của tệp.

Quy ước phổ biến của Maven CLI: **exit code 0** là build thành công; **exit code khác 0** báo thất bại/không thể hoàn tất theo yêu cầu.

### Bash: lưu log và trả đúng mã lỗi

Ví dụ một script Bash được CI gọi:

```bash
#!/usr/bin/env bash
set -euo pipefail
mkdir -p build-logs

if ./mvnw -B -ntp --log-file build-logs/verify.log clean verify; then
  echo "Maven build completed successfully"
else
  exit_code=$?
  echo "Maven build failed (exit=$exit_code); inspect build-logs/verify.log" >&2
  exit "$exit_code"
fi
```

Dùng `if ...; then ... else ...` giúp đọc mã lỗi ngay cả khi script bật `set -e`. Ví dụ trên đòi có Maven Wrapper và môi trường Bash; nếu dự án không có Wrapper, thay bằng `mvn` đã cài.

### PowerShell: lưu log và truyền lỗi ra CI

```powershell
New-Item -ItemType Directory -Force -Path .\build-logs | Out-Null
.\mvnw.cmd -B -ntp -l .\build-logs\verify.log clean verify
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Error "Maven build failed. See build-logs\verify.log"
    exit $exitCode
}
Write-Host "Maven build succeeded"
```

Trong môi trường CI, đặt những lệnh này vào job/step thích hợp. Cơ chế lưu và tải log của từng nền tảng CI khác nhau, nhưng **file chỉ nên được công bố như build artifact khi cấu hình truy cập và retention phù hợp**.

### Tránh vô hiệu hóa thất bại

Không dùng `-fn`/`--fail-never` để “giúp CI xanh”: tùy chọn đó có thể khiến Maven không trả lỗi như mong muốn khi các module thất bại. Nếu cần chạy những module khác rồi báo lỗi tổng thể, hãy nghiên cứu `-fae`/`--fail-at-end` và xác minh cơ chế báo lỗi phù hợp. Tùy chọn về chính sách thất bại là vấn đề riêng với `-B`, `-ntp` và `-l`.

## 9. Log hữu ích cần chứa gì? Quản lý file ra sao?

Một log đủ khả năng điều tra nên giúp trả lời:

1. **Đang build project/module nào?** Ghi nhận tên và đường dẫn project hoặc thông tin reactor trong log.
2. **Đang chạy pha/goal gì?** Ví dụ `clean verify` hay `test`.
3. **Build thành công/thất bại ra sao?** Kiểm tra mã thoát và dòng kết quả Maven, nếu có.
4. **Lỗi đầu tiên là gì?** Khi thất bại, lần theo đoạn `ERROR` và thông báo nguyên nhân gần nó, không chỉ đọc dòng cuối.
5. **Đang dùng Maven/Java nào?** Nếu vấn đề liên quan môi trường, chạy `mvn -version` hoặc `./mvnw -version` như một bước chẩn đoán riêng.

Một quy ước lưu log thực tế:

```text
project-root/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── build-logs/
│   ├── validate.log
│   ├── verify.log
│   └── verify-debug.log
└── target/
```

**Cây trên mang tính minh họa**; những file log chỉ xuất hiện khi bạn chạy lệnh tương ứng. Đặt thư mục log tách khỏi `target` nếu build có `clean`; cân nhắc lưu chúng ngoài workspace trong CI.

Nếu log chỉ là sản phẩm chạy cục bộ, có thể thêm vào `.gitignore` của dự án:

```gitignore
/build-logs/
```

Log là dữ liệu vận hành, có thể chứa URL repository nội bộ, đường dẫn máy, exception stack trace, tên người dùng hoặc nội dung do test/plugin in ra. Không commit log ngẫu nhiên lên Git; khi chia sẻ trên CI, đặt quyền xem và thời hạn lưu hợp lý.

### Giữ file log theo từng lượt chạy

Vì ghi cùng một đường dẫn có thể thay thế nội dung lần trước, nên tránh nhiều job đồng thời ghi chung `build-logs/verify.log`. Mỗi job nên dùng **đường dẫn duy nhất**: thêm ID build hoặc tên job do CI cung cấp sau khi kiểm tra chuỗi dùng làm tên file, hoặc ghi vào thư mục riêng của từng job. Nếu muốn lưu nhiều phiên bản theo thời gian, dùng chức năng artifact/log retention của CI thay vì để log tích tụ vô hạn trong repository.

## 10. Xử lý lỗi khi dùng `-B`, `-ntp` và `-l`

| Dấu hiệu | Nguyên nhân có thể gặp | Cách xác minh và xử lý |
| --- | --- | --- |
| CI đứng chờ dù đã có `-B` | Một plugin, test hoặc subprocess yêu cầu input riêng | Xem tiến trình đang chờ gì; cấu hình plugin/secret để không tương tác |
| Log vẫn có nhiều dòng tải dependency | `-ntp` chỉ ẩn **progress**, không triệt tiêu mọi thông báo về download | Giữ `-ntp`, đánh giá mức log thực tế trước khi cân nhắc `-q` |
| Maven không thấy dependency khi offline | Dùng `-o` nhưng cache chưa đủ | Cho phép tải từ repository ở lượt build phù hợp; `-ntp` không gây offline |
| Không tạo được `build-logs/verify.log` | Thư mục cha chưa tồn tại hoặc thiếu quyền ghi | Tạo thư mục, kiểm tra quyền/path; tránh lưu trong thư mục bị xóa bởi `clean` |
| Không thấy output Maven trên console | Đã bật `-l` nên output vào tệp | Mở log sau build hoặc dùng `tee` nếu cần cả hai |
| Log bị mất khi `mvn clean` | Đặt log dưới `target` rồi pha clean xóa target | Chuyển log ra ngoài `target` |
| CI xanh dù log báo thất bại | Pipeline `tee` không bật `pipefail`, hoặc script nuốt mã lỗi | Kiểm tra exit code của Maven; bật `pipefail` cho Bash pipeline |
| Mất thông tin lỗi quan trọng | Dùng `-q` hoặc chỉ giữ vài dòng cuối log | Bỏ `-q`, lưu đầy đủ log; thêm `-e`/`-X` khi cần |
| File log lớn hoặc có dữ liệu nhạy cảm | `-X`, test in nhiều dữ liệu, tool ghi secrets | Giảm debug, lọc dữ liệu nhạy cảm, giới hạn chia sẻ và retention |
| Log nhiều build trộn với nhau | Nhiều job ghi chung một file hoặc dùng append tùy tiện | Tên file riêng theo lượt chạy/job và giới hạn lưu trữ |

### Cách điều tra có thứ tự

Khi build lỗi trong CI, thường nên:

1. Xác minh lệnh thật sự chạy bằng Maven hay Maven Wrapper, đúng thư mục có POM và đúng JDK.
2. Kiểm tra **exit code** của lệnh hoặc pipeline.
3. Mở file log được tạo bởi `-l` hoặc `tee`; tìm `[ERROR]`, `BUILD FAILURE` và những dòng trước đó.
4. Nếu chỉ có thông báo rất ngắn, bỏ `-q`. Chạy lại với `-e` để xem stack trace, hoặc `-X` khi thực sự cần debug sâu.
5. Nếu nghi lỗi mạng, proxy hay repository, xem thông báo HTTP/TLS và cấu hình `settings.xml`; `-ntp` không khiến dependency biến mất hoặc tự tải ngoại tuyến.
6. Khi đã sửa, chạy lại build bình thường với `-B -ntp` và xác minh exit code cùng log mới.

## 11. Lệnh mẫu cần nhớ

| Nhu cầu | Lệnh |
| --- | --- |
| Chạy test theo batch, ít tiến độ tải | `mvn -B -ntp test` |
| Verify bằng Wrapper trên Linux/macOS | `./mvnw -B -ntp clean verify` |
| Verify bằng Wrapper trên Windows | `.\mvnw.cmd -B -ntp clean verify` |
| Lưu toàn bộ output build của Maven | `mvn -B -ntp -l build-logs/verify.log clean verify` |
| Kiểm tra cấu hình POM và lưu log | `mvn -B -ntp --log-file build-logs/validate.log validate` |
| Bật thông tin lỗi chi tiết | `mvn -B -ntp -e verify` |
| Debug sâu sau khi lỗi | `mvn -B -ntp -X verify` |
| Ghi file và hiện console bằng Bash | `set -o pipefail` rồi `./mvnw -B -ntp verify 2>&1 | tee build-logs/verify.log` |

Ở hai dòng dùng `build-logs/`, hãy **tạo thư mục cha trước khi chạy**. Dòng cuối dùng ký hiệu pipe Bash `|` (sẽ thay bằng `|` thực tế) để mô tả pipeline; khi thực thi, dùng khối mã `tee` đầy đủ ở mục 6.

**Kiến thức cốt lõi:** `-B` định nghĩa **cách Maven tương tác**; `-ntp` định nghĩa **cách trình bày tiến độ chuyển artifact**; `-l` định nghĩa **đích lưu output**. Kết hợp đúng các cờ này giúp job Maven chạy tự động, log gọn và còn bằng chứng để điều tra thất bại; exit code vẫn là tín hiệu quan trọng để CI quyết định thành công hay thất bại.

## Tài liệu tham khảo chính thức

- [Apache Maven 3.9.x — CLI Options Reference](https://maven.apache.org/ref/3.9.16/maven-embedder/cli.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/)
