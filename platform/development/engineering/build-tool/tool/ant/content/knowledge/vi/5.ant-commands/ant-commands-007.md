# Ghi nhật ký bằng -logfile và điều khiển nhập liệu bằng -noinput

Khi chạy Apache Ant từ terminal, hai tùy chọn `-logfile` và `-noinput` giúp kiểm soát cách build ghi lại thông tin và xử lý những bước cần người dùng trả lời. Chúng đặc biệt hữu ích khi build chạy trong CI, script tự động hoặc trên máy chủ không có người theo dõi trực tiếp.

- `-logfile` chỉ định tệp nhận phần nhật ký do Ant ghi trong lần chạy đó.
- `-noinput` yêu cầu Ant không chờ dữ liệu nhập tương tác trong quá trình build.

Hai tùy chọn giải quyết hai vấn đề khác nhau. Ghi log giúp xem lại điều gì đã xảy ra; tắt nhập liệu giúp một build tự động không bị treo chờ câu trả lời. Khi dùng chung, chúng tạo ra một lệnh build thuận tiện cho môi trường không tương tác.

## 1. Cú pháp lệnh Ant và vị trí của tùy chọn

Cấu trúc lệnh tổng quát:

```text
ant [options] [target [target2 [target3] ...]]
```

Các tùy chọn được đặt trong phần `options`, trước tên target. Ví dụ:

```text
ant -noinput -logfile logs/build.log clean jar
```

Trong lệnh này:

1. `-noinput` yêu cầu Ant không nhận nhập liệu tương tác.
2. `-logfile logs/build.log` chỉ định tệp ghi nhật ký.
3. `clean` và `jar` là hai target được yêu cầu chạy theo thứ tự đã nêu, cùng với các target phụ thuộc của chúng.

Ant đọc `build.xml` từ thư mục hiện tại, trừ khi bạn chỉ định build file khác bằng tùy chọn tương ứng. Vì vậy, hãy chạy lệnh ở thư mục gốc dự án hoặc chủ động chuyển tới đúng thư mục trước khi chạy.

## 2. Ghi nhật ký vào tệp bằng -logfile

### 2.1. Công dụng

Mặc định, Ant hiển thị thông tin của quá trình build trên terminal. Khi dùng:

```text
ant -logfile logs/build.log jar
```

Ant ghi nhật ký của lần build vào `logs/build.log`. Điều này hữu ích khi:

- Build có nhiều output và bạn muốn xem lại sau khi lệnh kết thúc.
- CI cần lưu log làm bằng chứng cho một lần build.
- Một lỗi chỉ xuất hiện thỉnh thoảng và cần giữ thông tin để phân tích.
- Bạn muốn gửi log cho thành viên khác để cùng tìm nguyên nhân.
- Build chạy nền hoặc chạy theo lịch, không có người quan sát terminal.

Tùy chọn viết tắt của `-logfile` là `-l`. Hai cách viết sau có cùng ý nghĩa:

```text
ant -logfile logs/build.log jar
ant -l logs/build.log jar
```

Tên tệp có thể là đường dẫn tương đối hoặc tuyệt đối. Đường dẫn tương đối được hiểu theo thư mục làm việc khi khởi chạy Ant. Nếu đường dẫn chứa dấu cách, hãy đặt nó trong dấu ngoặc kép:

```text
ant -noinput -logfile "logs/nightly build.log" clean jar
```

### 2.2. Tạo thư mục chứa log trước khi chạy

Ant có thể tạo tệp log, nhưng không nên giả định nó tự tạo toàn bộ thư mục cha chưa tồn tại. Hãy tạo thư mục trước:

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
ant -noinput -logfile logs/build.log clean jar
```

Trên Linux hoặc macOS:

```bash
mkdir -p logs
ant -noinput -logfile logs/build.log clean jar
```

Nếu thư mục `logs` chưa tồn tại, việc mở tệp log có thể thất bại trước khi build bắt đầu. Khi build chạy trong CI, hãy thêm bước tạo thư mục vào script hoặc cấu hình pipeline.

### 2.3. Nội dung và vòng đời tệp log

Log thường ghi lại các thông tin như:

- Tên project và target đang được thực thi.
- Các task được gọi và thông báo do task phát ra.
- Thông báo lỗi, cảnh báo và kết quả kết thúc build.
- Thông tin chi tiết hơn nếu chọn mức log tương ứng.

Tệp được chỉ định là nơi Ant ghi log cho lần chạy. Không nên coi `-logfile` là cơ chế tự động lưu lịch sử nhiều lần chạy vào cùng một tệp; nội dung cũ có thể bị ghi đè khi chạy lại. Nếu cần giữ lịch sử, hãy đặt tên log riêng cho từng lần chạy, ví dụ theo ngày, số build hoặc mã job:

```text
logs/
├── build-2026-11-12-001.log
├── build-2026-11-12-002.log
└── build-2026-11-13-001.log
```

Trong CI, có thể dùng biến môi trường của hệ thống CI để tạo tên tệp duy nhất. Cú pháp biến phụ thuộc nền tảng, vì vậy hãy đưa giá trị đó vào script của pipeline thay vì giả định mọi CI dùng cùng một tên biến.

### 2.4. -logfile không phải tùy chọn tăng độ chi tiết

`-logfile` chọn nơi ghi nhật ký; nó không tự thay đổi mức độ chi tiết. Mức log được điều khiển bằng các tùy chọn khác, chẳng hạn:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-quiet` hoặc `-q` | Giảm lượng thông tin hiển thị theo mức quiet |
| `-verbose` hoặc `-v` | Hiển thị thông tin chi tiết hơn |
| `-debug` hoặc `-d` | Bật thông tin gỡ lỗi chi tiết |
| `-logfile file` hoặc `-l file` | Chỉ định tệp nhận log |

Ví dụ lưu log chi tiết hơn để điều tra:

```text
ant -verbose -noinput -logfile logs/build-verbose.log clean jar
```

Khi build lỗi mà log thông thường chưa đủ thông tin, có thể chạy lại với `-verbose` hoặc `-debug` để thu thập thêm chi tiết. Các mức log chi tiết có thể tạo tệp lớn hơn và chứa nhiều thông tin về đường dẫn, cấu hình hoặc lệnh được gọi; chỉ bật khi cần.

### 2.5. Phân biệt log của Ant với output của chương trình bên ngoài

`-logfile` cấu hình nơi ghi nhật ký của Ant. Một build có thể gọi chương trình ngoài bằng task như `<exec>`, chạy script hoặc khởi động một công cụ khác. Cách các chương trình đó ghi stdout và stderr còn phụ thuộc vào cách task gọi chúng và cấu hình của chính chương trình.

Nếu log thiếu thông tin từ một lệnh bên ngoài, hãy kiểm tra cấu hình task `<exec>`, đặc biệt các thuộc tính điều khiển output, error và việc chuyển output thành property. Cũng cần kiểm tra chương trình đó có ghi log riêng sang một tệp khác hay không. Không nên kết luận rằng mọi output của mọi tiến trình con đều được xử lý giống hệt thông báo do Ant phát ra.

## 3. Điều khiển nhập liệu bằng -noinput

### 3.1. Vì sao cần tắt nhập liệu tương tác?

Một số build có bước cần hỏi người chạy, chẳng hạn:

- Chọn môi trường triển khai.
- Xác nhận có tiếp tục một thao tác hay không.
- Chọn một cấu hình hoặc biến thể build.
- Cung cấp giá trị mà build chưa nhận được từ cấu hình.

Trong terminal tương tác, người chạy có thể đọc câu hỏi và nhập câu trả lời. Nhưng trong CI hoặc script chạy tự động, thường không có người trả lời. Nếu build chờ nhập liệu, job có thể đứng vô thời hạn hoặc kết thúc với lỗi khi không có dữ liệu đầu vào.

Tùy chọn:

```text
ant -noinput jar
```

yêu cầu Ant không cho phép nhập liệu tương tác trong quá trình build. Đây là lựa chọn phù hợp khi muốn phát hiện sớm những target vẫn phụ thuộc vào thao tác thủ công.

### 3.2. -noinput không tự cung cấp giá trị cho build

Tắt nhập liệu không đồng nghĩa với việc Ant tự chọn một câu trả lời. Nếu target cần một property, bạn phải cung cấp giá trị đó bằng một cơ chế không tương tác, chẳng hạn:

- Thuộc tính dòng lệnh với `-Dname=value`.
- Tệp properties được nạp bởi build.
- Giá trị mặc định được định nghĩa trong `build.xml`.
- Biến môi trường được build đọc theo cách đã cấu hình.

Ví dụ, giả sử target triển khai cần biết môi trường đích. Có thể truyền giá trị khi gọi Ant:

```text
ant -noinput -Ddeploy.environment=staging -logfile logs/deploy.log deploy
```

Trong build file, property này có thể được dùng để chọn cấu hình:

```xml
<target name="deploy">
    <echo message="Deploy environment: ${deploy.environment}" />
    <!-- Các task triển khai sử dụng cấu hình của môi trường đã chọn -->
</target>
```

Nếu property bắt buộc nhưng không được truyền vào và không có giá trị mặc định, build cần báo lỗi rõ ràng. Không nên âm thầm dùng một môi trường triển khai khác chỉ vì không có người nhập dữ liệu.

### 3.3. Làm việc với task <input>

Ant có task `<input>` để yêu cầu người chạy nhập giá trị. Ví dụ:

```xml
<target name="choose-environment">
    <input message="Nhap moi truong (dev/staging/prod):"
           addproperty="deploy.environment"
           validargs="dev,staging,prod" />
    <echo message="Selected: ${deploy.environment}" />
</target>
```

Khi chạy target này trong terminal tương tác, task có thể yêu cầu người dùng nhập một giá trị hợp lệ. Nếu chạy cùng target với `-noinput`, build không thể dựa vào việc người dùng gõ câu trả lời. Hành vi cụ thể khi thiếu dữ liệu phụ thuộc input handler và cách task được cấu hình; không nên giả định Ant sẽ tự chọn một môi trường.

Nếu muốn chạy tự động, hãy truyền property từ dòng lệnh:

```text
ant -noinput -Ddeploy.environment=staging choose-environment
```

Khi property đã được cung cấp trước, task `<input>` có thể dùng giá trị đó thay vì yêu cầu nhập lại. Đây là cách giúp cùng một build file hoạt động trong cả môi trường phát triển và pipeline tự động.

Với giá trị bắt buộc, có thể kiểm tra property trước khi thực hiện bước tiếp theo. Ví dụ:

```xml
<target name="validate-environment">
    <fail unless="deploy.environment"
          message="Missing required property: deploy.environment" />
</target>

<target name="deploy" depends="validate-environment">
    <echo message="Deploy environment: ${deploy.environment}" />
    <!-- Các task triển khai -->
</target>
```

Khi gọi target `deploy`, nếu chưa cung cấp property, task `<fail>` dừng build với thông báo dễ hiểu. Trong môi trường tự động, lỗi cấu hình rõ ràng thường dễ xử lý hơn một job chờ nhập liệu.

### 3.4. -noinput không thay thế chế độ non-interactive của công cụ bên ngoài

Phạm vi của `-noinput` là nhập liệu do Ant quản lý. Nếu target gọi một chương trình ngoài, chẳng hạn Git, trình quản lý package, script shell hoặc công cụ triển khai, chương trình đó có thể có cơ chế prompt riêng.

Ví dụ, một script được gọi bằng `<exec>` vẫn có thể chờ đọc stdin hoặc mở prompt của riêng nó. Tùy chọn `-noinput` của Ant không bảo đảm mọi chương trình con tự chuyển sang chế độ không tương tác.

Hãy dùng tùy chọn non-interactive hoặc batch mode do chính công cụ bên ngoài cung cấp, truyền đủ tham số cần thiết và cấu hình thông tin xác thực theo cơ chế an toàn của môi trường chạy. Nếu script tự viết có lệnh đọc stdin, hãy sửa script để nhận tham số hoặc biến môi trường và xử lý trường hợp thiếu dữ liệu.

## 4. Kết hợp -logfile và -noinput trong một lệnh

Trong CI hoặc script chạy theo lịch, thường nên dùng cả hai tùy chọn:

```text
ant -noinput -logfile logs/build.log clean jar
```

Lệnh này có hai mục đích:

- Log của Ant được lưu vào tệp để có thể kiểm tra sau khi job kết thúc.
- Ant không chờ người dùng trả lời câu hỏi tương tác.

Một ví dụ khác khi build cần chọn môi trường:

```text
ant -noinput -Ddeploy.environment=staging -logfile logs/deploy-staging.log deploy
```

Trong đó, giá trị `staging` được cung cấp rõ ràng qua property. Log được đặt tên theo môi trường để người vận hành dễ xác định lần triển khai tương ứng.

Nếu cần log chi tiết:

```text
ant -verbose -noinput -Ddeploy.environment=staging -logfile logs/deploy-staging.log deploy
```

Không nên bật `-debug` cho mọi lần build thường ngày nếu không cần thiết. Log quá chi tiết có thể khó đọc và làm tăng dung lượng lưu trữ.

## 5. Kiểm tra log và mã thoát của build

Khi Ant kết thúc, hãy kiểm tra cả nội dung log và mã thoát của tiến trình. Log cho biết task nào đã chạy và lỗi xuất hiện ở đâu; mã thoát cho biết lệnh có thành công theo góc nhìn của shell hoặc CI hay không.

Trên PowerShell:

```powershell
ant -noinput -logfile logs/build.log clean jar

if ($LASTEXITCODE -ne 0) {
    Get-Content logs/build.log -Tail 80
    exit $LASTEXITCODE
}
```

Trên Linux hoặc macOS:

```bash
ant -noinput -logfile logs/build.log clean jar
status=$?
tail -n 80 logs/build.log
exit "$status"
```

Các ví dụ giả định thư mục `logs` đã được tạo trước. Trong pipeline, hãy cấu hình bước lưu artifact log kể cả khi build thất bại; nếu chỉ tải log sau job thành công, thông tin hữu ích nhất có thể bị mất đúng lúc cần điều tra.

Khi đọc log, nên tìm thông báo lỗi đầu tiên có liên quan thay vì chỉ xem dòng cuối cùng. Dòng cuối thường chỉ báo build thất bại; nguyên nhân có thể nằm ở một task trước đó. Đối chiếu target, tên tệp, đường dẫn và thông báo exception để xác định bước gây lỗi.

## 6. Các tình huống sử dụng thường gặp

| Tình huống | Cách gọi gợi ý | Mục đích |
|---|---|---|
| Build trên máy cá nhân và cần giữ log | `ant -logfile logs/local.log jar` | Có thể xem lại log sau khi build |
| CI chạy build không cần nhập liệu | `ant -noinput -logfile logs/ci.log clean jar` | Tránh Ant chờ câu trả lời tương tác |
| Build cần chọn môi trường rõ ràng | `ant -noinput -Ddeploy.environment=staging -logfile logs/deploy.log deploy` | Truyền cấu hình trước khi chạy |
| Điều tra lỗi khó tái hiện | `ant -verbose -noinput -logfile logs/verbose.log jar` | Thu thập thêm thông tin |
| Build chạy theo lịch | `ant -noinput -logfile logs/nightly.log clean jar` | Có log để kiểm tra sau lần chạy tự động |

Không nên dùng một lệnh triển khai production với giá trị mặc định tùy tiện chỉ để tránh prompt. Môi trường đích và các thông số ảnh hưởng đến thao tác quan trọng cần được xác định rõ từ cấu hình được kiểm soát.

## 7. Các lỗi và cách xử lý

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Ant không tạo được log | Thư mục cha chưa tồn tại hoặc tiến trình không có quyền ghi | Tạo thư mục trước và kiểm tra quyền ghi |
| Log của lần chạy trước biến mất | Lần chạy mới ghi vào cùng tên tệp | Dùng tên log riêng theo lần chạy hoặc lưu trữ log trước khi chạy lại |
| Log quá ít thông tin | Đang dùng mức log mặc định hoặc quiet | Thử `-verbose`; chỉ dùng `-debug` khi cần điều tra sâu |
| Build lỗi khi dùng `-noinput` | Target vẫn cần dữ liệu nhập mà chưa có giá trị cung cấp | Truyền property bằng `-D`, property file hoặc cấu hình mặc định rõ ràng |
| Build vẫn bị treo dù có `-noinput` | Một chương trình con hoặc script có prompt riêng | Cấu hình chế độ non-interactive của chương trình đó và kiểm tra cách nó đọc stdin |
| Build chạy sai môi trường | Property môi trường bị thiếu hoặc dùng giá trị mặc định không phù hợp | Truyền rõ `-Ddeploy.environment=...` và xác thực trước target triển khai |
| Log không có output mong đợi từ lệnh ngoài | Task `<exec>` hoặc chương trình con đang chuyển output sang nơi khác | Kiểm tra cấu hình output/error của task và log riêng của chương trình |
| CI báo thành công dù log có lỗi nghiệp vụ | Script không kiểm tra mã thoát hoặc target không dừng khi gặp lỗi | Kiểm tra mã thoát, dùng `<fail>` cho điều kiện bắt buộc và cấu hình pipeline dừng khi lệnh thất bại |

## 8. Lưu ý khi lưu trữ log

Log là dữ liệu vận hành. Nó có thể chứa tên máy, đường dẫn workspace, tên người dùng, tham số lệnh, thông tin môi trường và nội dung do task in ra. Vì vậy:

- Không in mật khẩu, access token, private key hoặc thông tin xác thực vào log.
- Giới hạn quyền đọc đối với log của các job có thông tin nội bộ.
- Xác định thời gian lưu log phù hợp với nhu cầu điều tra và dung lượng lưu trữ.
- Dùng tên tệp có thể liên kết với lần chạy, commit hoặc mã job.
- Nếu log được tải lên hệ thống CI, áp dụng chính sách lưu artifact và quyền truy cập của hệ thống đó.
- Khi chia sẻ log để nhờ hỗ trợ, loại bỏ thông tin bí mật và dữ liệu cá nhân không cần thiết.

Không nên dựa vào việc che thông tin trên giao diện terminal để bảo vệ secret. Nếu task đã ghi secret ra log, nội dung đó vẫn có thể nằm trong tệp và artifact được lưu trữ.

## 9. Quy trình đề xuất cho build tự động

Một quy trình đơn giản cho CI có thể thực hiện theo thứ tự:

1. Tạo thư mục chứa log.
2. Chuẩn bị các property bắt buộc từ cấu hình pipeline hoặc property file.
3. Chạy Ant với `-noinput` và `-logfile`.
4. Kiểm tra mã thoát của tiến trình Ant.
5. Lưu log làm artifact để có thể xem lại khi thành công hoặc thất bại.
6. Nếu build lỗi, dùng log để xác định target và task gây lỗi.

Ví dụ lệnh cốt lõi:

```text
ant -noinput -Dbuild.environment=ci -logfile logs/ci-build.log clean jar
```

Tên property trong ví dụ chỉ là quy ước của dự án; Ant không tự hiểu ý nghĩa của `build.environment`. Build file phải khai báo và sử dụng property đó nếu cần.

Khi một target cần người dùng quyết định, hãy thiết kế để giá trị có thể được truyền từ bên ngoài và kiểm tra trước khi chạy. Khi một target phát sinh thông tin cần lưu, hãy bảo đảm log được giữ lại và không chứa secret. Hai thói quen này giúp lệnh Ant hoạt động ổn định trong terminal cá nhân, script tự động và hệ thống CI.

