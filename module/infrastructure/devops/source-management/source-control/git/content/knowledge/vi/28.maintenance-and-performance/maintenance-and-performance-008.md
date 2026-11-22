# Chẩn đoán thao tác chậm bằng các cơ chế trace của Git

Khi một lệnh Git chạy chậm, cảm giác “Git bị treo” chưa cho biết thời gian đang được dùng ở đâu. `git status` có thể mất thời gian quét working tree; `git fetch` có thể chờ mạng, máy chủ hoặc xử lý packfile; `git push` có thể chờ xác thực, truyền dữ liệu hoặc hook. Git cung cấp nhiều cơ chế trace để ghi lại hoạt động nội bộ và thời gian thực thi, giúp xác định giai đoạn gây chậm trước khi thay đổi cấu hình hoặc hạ tầng.

Các biến môi trường thường dùng gồm `GIT_TRACE`, `GIT_TRACE_SETUP`, `GIT_TRACE_PERFORMANCE`, nhóm Trace2 (`GIT_TRACE2`, `GIT_TRACE2_PERF`, `GIT_TRACE2_EVENT`), cùng trace chuyên biệt cho packet, HTTP, packfile và refs. Hãy bắt đầu bằng trace hiệu năng tổng quát, sau đó bật trace chuyên biệt phù hợp với triệu chứng. Trace là công cụ quan sát; bản thân nó không tối ưu repository hoặc sửa lỗi.

## 1. Trace giúp trả lời câu hỏi gì?

Một thao tác Git thường gồm nhiều bước. Ví dụ, `git fetch` có thể thực hiện:

1. Đọc cấu hình repository và remote.
2. Khởi chạy transport như SSH hoặc HTTP.
3. Thương lượng protocol và xác định ref cần cập nhật.
4. Nhận packfile hoặc dữ liệu object.
5. Kiểm tra, giải nén và ghi object vào object database.
6. Cập nhật refs và metadata liên quan.

Nếu chỉ đo tổng thời gian, bạn biết lệnh mất bao lâu nhưng chưa biết bước nào chậm. Trace giúp quan sát tiến trình con, hoạt động giao thức, vùng xử lý nội bộ và thời gian của các giai đoạn.

Một số câu hỏi có thể điều tra:

- Git đang chạy lệnh con nào và lệnh con đó mất bao lâu?
- Thời gian nằm ở bước khởi tạo repository, đọc index hay xử lý object?
- Fetch/push đang chờ packet từ remote hay đang truyền dữ liệu qua HTTP?
- Git có truy cập packfile quá nhiều hoặc thực hiện nhiều thao tác refs không?
- Một lệnh chậm vì Git hay vì SSH, credential helper, hook, mạng hoặc máy chủ?

Trace giúp thu hẹp nguyên nhân. Để đo CPU, I/O đĩa, DNS, độ trễ mạng hoặc hoạt động của tiến trình bên ngoài ở mức hệ điều hành, có thể cần thêm profiler và công cụ giám sát riêng.

## 2. Bắt đầu bằng GIT_TRACE và GIT_TRACE_PERFORMANCE

### GIT_TRACE: xem hoạt động tổng quát

`GIT_TRACE` bật trace tổng quát của Git. Nó hữu ích để xem alias được mở rộng, lệnh con được gọi và một số bước thực thi nội bộ.

Trên macOS/Linux hoặc Git Bash:

```bash
GIT_TRACE=1 git status
GIT_TRACE=1 git fetch origin
```

Giá trị `1` (hoặc `true`) thường gửi trace ra standard error. Có thể chỉ định đường dẫn file để lưu trace:

```bash
GIT_TRACE=/tmp/git-trace.log git fetch origin
```

Trên PowerShell:

```powershell
$env:GIT_TRACE = "1"
git fetch origin
Remove-Item Env:GIT_TRACE
```

Nếu muốn ghi ra file:

```powershell
$env:GIT_TRACE = "$env:TEMP\git-trace.log"
git fetch origin
Remove-Item Env:GIT_TRACE
```

Trace tổng quát phù hợp để kiểm tra Git đang gọi chương trình nào, ví dụ `ssh`, `git-remote-https`, credential helper hoặc hook. Nếu một tiến trình con xuất hiện trong trace nhưng Git chờ nó lâu, hãy điều tra tiến trình đó thay vì chỉ tập trung vào Git core.

### GIT_TRACE_PERFORMANCE: xem thời gian thực thi

`GIT_TRACE_PERFORMANCE` ghi các thông tin thời gian của lệnh Git và một số vùng xử lý. Ví dụ:

```bash
GIT_TRACE_PERFORMANCE=1 git status
GIT_TRACE_PERFORMANCE=1 git log --all --oneline -100
```

Output thường có thời lượng theo giây và mô tả lệnh hoặc giai đoạn được đo. Đây là cách nhanh để xác định một lệnh đang mất thời gian tổng thể hoặc một bước nội bộ cụ thể.

Có thể ghi ra file:

```bash
GIT_TRACE_PERFORMANCE=/tmp/git-performance.log git status
```

Trên PowerShell:

```powershell
$env:GIT_TRACE_PERFORMANCE = "$env:TEMP\git-performance.log"
git status
Remove-Item Env:GIT_TRACE_PERFORMANCE
```

Nếu chỉ cần trả lời “lệnh này mất bao lâu và Git báo giai đoạn nào tốn thời gian”, hãy bắt đầu với `GIT_TRACE_PERFORMANCE` trước khi bật các trace giao thức chi tiết hơn.

## 3. Trace2: quan sát hoạt động theo cấu trúc

Trace2 là hệ thống trace hiện đại của Git. Nó bổ sung thông tin có cấu trúc về tiến trình, luồng, sự kiện, vùng xử lý và thời lượng. Trace2 hữu ích khi lệnh phức tạp, có nhiều tiến trình con hoặc cần phân tích log bằng công cụ tự động.

Git cung cấp ba đích trace2 thường dùng:

| Biến môi trường | Dạng dữ liệu | Khi nào dùng |
|---|---|---|
| `GIT_TRACE2` | Trace2 tổng quát | Xem luồng thực thi và sự kiện ở dạng trace2 thông thường |
| `GIT_TRACE2_PERF` | Trace hiệu năng dạng văn bản | Đọc thời lượng, vùng xử lý và quan hệ tiến trình trực tiếp |
| `GIT_TRACE2_EVENT` | Các sự kiện JSON | Phân tích bằng script, jq hoặc hệ thống log |

### Trace2 performance

Ví dụ trên Unix-like shell:

```bash
GIT_TRACE2_PERF=/tmp/fetch-perf.log git fetch origin
```

Trên PowerShell:

```powershell
$env:GIT_TRACE2_PERF = "$env:TEMP\fetch-perf.log"
git fetch origin
Remove-Item Env:GIT_TRACE2_PERF
```

Trace2 performance có thể cho biết thời điểm bắt đầu/kết thúc tiến trình, thời lượng, vùng xử lý được mở/đóng và hoạt động của tiến trình con. Các dòng trace có thông tin tiến trình và luồng, hữu ích khi nhiều tác vụ Git chạy lồng nhau.

### Trace2 event JSON

Khi cần dữ liệu có cấu trúc:

```bash
GIT_TRACE2_EVENT=/tmp/fetch-events.json git fetch origin
```

Trên PowerShell:

```powershell
$env:GIT_TRACE2_EVENT = "$env:TEMP\fetch-events.json"
git fetch origin
Remove-Item Env:GIT_TRACE2_EVENT
```

File event chứa các bản ghi JSON, mỗi bản ghi mô tả một sự kiện. Tùy thao tác và phiên bản Git, bạn có thể gặp các loại sự kiện như `start`, `cmd_name`, `child_start`, `child_exit`, `region_enter`, `region_leave`, `data` và `exit`.

Các sự kiện này giúp dựng lại trình tự thực thi. Ví dụ, cặp `child_start`/`child_exit` cho biết một tiến trình con được gọi và kết thúc; `region_enter`/`region_leave` biểu diễn một vùng xử lý; `exit` ghi nhận kết thúc tiến trình Git. Không phải mọi lệnh đều phát ra đầy đủ mọi loại sự kiện.

### Chọn Trace2 hay trace truyền thống?

- Dùng `GIT_TRACE_PERFORMANCE` để kiểm tra nhanh thời gian.
- Dùng `GIT_TRACE2_PERF` để quan sát sâu hơn các vùng xử lý và tiến trình con.
- Dùng `GIT_TRACE2_EVENT` khi cần phân tích JSON hoặc thu thập dữ liệu trong CI.
- Dùng `GIT_TRACE` để xem hoạt động gọi lệnh tổng quát.

Không cần bật tất cả cùng lúc ngay từ đầu. Bật từng nhóm theo câu hỏi cần trả lời sẽ giúp log dễ đọc và ít nhiễu hơn.

## 4. Kiểm tra Git đang nhận diện repository nào bằng GIT_TRACE_SETUP

Đôi khi lệnh chậm hoặc hoạt động sai vì Git tìm thấy repository, worktree hoặc index khác với dự kiến. `GIT_TRACE_SETUP` ghi thông tin setup của Git, chẳng hạn thư mục hiện tại, Git directory, working tree và prefix.

Ví dụ:

```bash
GIT_TRACE_SETUP=1 git status
```

Hoặc ghi vào file:

```bash
GIT_TRACE_SETUP=/tmp/git-setup.log git status
```

Trên PowerShell:

```powershell
$env:GIT_TRACE_SETUP = "1"
git status
Remove-Item Env:GIT_TRACE_SETUP
```

Trace này hữu ích khi:

- Chạy lệnh từ thư mục con nhưng Git nhận diện nhầm repository.
- Dùng linked worktree và muốn kiểm tra Git directory/common directory.
- Script đặt `GIT_DIR`, `GIT_WORK_TREE` hoặc `GIT_INDEX_FILE` khiến lệnh dùng ngữ cảnh khác.
- IDE hoặc công cụ gọi Git từ working directory không như dự kiến.

Nếu cần xác minh nhanh bằng lệnh độc lập, có thể kết hợp:

```bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
```

## 5. Trace packet khi fetch hoặc push chậm

Git dùng giao thức trao đổi packet-line khi làm việc với remote. `GIT_TRACE_PACKET` ghi lại hoạt động packet ở mức giao thức, giúp xem quá trình thương lượng capability, quảng bá ref và trao đổi thông điệp.

Ví dụ:

```bash
GIT_TRACE_PACKET=1 git ls-remote origin
GIT_TRACE_PACKET=1 git fetch origin
```

Output thường phân biệt dữ liệu gửi và nhận, đồng thời hiển thị nội dung packet-line hoặc thông tin protocol tương ứng. Trace này hữu ích khi:

- Fetch/push mất thời gian ở giai đoạn thương lượng.
- Server trả ref hoặc capability không như mong đợi.
- Có vấn đề tương thích protocol giữa client và server.
- Cần xác định client đang chờ phản hồi ở bước nào.

Packet trace khá chi tiết và có thể tạo log lớn. Nó cũng có thể chứa tên branch, tag, URL hoặc metadata repository. Chỉ bật trong khoảng thời gian cần chẩn đoán và kiểm tra log trước khi chia sẻ.

## 6. Trace HTTP(S) bằng GIT_TRACE_CURL

Khi remote dùng HTTP hoặc HTTPS, Git sử dụng lớp transport dựa trên libcurl. `GIT_TRACE_CURL` bật trace request/response và các thông tin kết nối HTTP hữu ích khi fetch hoặc push chậm.

Ví dụ:

```bash
GIT_TRACE_CURL=1 GIT_TRACE_CURL_NO_DATA=1 git fetch origin
```

`GIT_TRACE_CURL_NO_DATA=1` yêu cầu bỏ phần dữ liệu payload khỏi curl trace để log tập trung vào thông tin kết nối và header. Tùy phiên bản và loại request, trace vẫn có thể chứa metadata nhạy cảm.

Trên PowerShell:

```powershell
$env:GIT_TRACE_CURL = "1"
$env:GIT_TRACE_CURL_NO_DATA = "1"
git fetch origin
Remove-Item Env:GIT_TRACE_CURL
Remove-Item Env:GIT_TRACE_CURL_NO_DATA
```

Trace curl giúp điều tra:

- DNS, kết nối TCP hoặc TLS có chậm không.
- Server trả mã HTTP nào.
- Có redirect, retry hoặc xác thực lặp lại không.
- Thời gian chờ phản hồi và trao đổi header.
- Vấn đề proxy hoặc cấu hình HTTP.

Không nên bật trace curl rồi đăng nguyên log công khai. Hãy rà soát URL nội bộ, tên người dùng, header, cookie, thông tin proxy và mọi dữ liệu nhận dạng trước khi chia sẻ. Dù Git có thể che một số header nhạy cảm ở một số phiên bản, không nên dựa vào điều đó như bảo đảm log không chứa bí mật.

## 7. Trace truy cập packfile và refs

Khi thao tác local chậm, vấn đề có thể liên quan đến object database, packfile hoặc ref storage.

### GIT_TRACE_PACK_ACCESS

`GIT_TRACE_PACK_ACCESS` ghi thông tin khi Git truy cập packfile, thường bao gồm packfile và offset được đọc. Ví dụ:

```bash
GIT_TRACE_PACK_ACCESS=1 git log --all --oneline -200
```

Trace này hữu ích khi nghi ngờ một thao tác đọc lịch sử hoặc object phải truy cập packfile nhiều lần. Nó cung cấp manh mối về hoạt động đọc pack, nhưng không tự xác định blob nào lớn nhất hoặc chứng minh đĩa đang chậm.

### GIT_TRACE_REFS

`GIT_TRACE_REFS` ghi hoạt động liên quan đến ref database, hữu ích khi branch/tag operation hoặc cập nhật ref có vẻ chậm:

```bash
GIT_TRACE_REFS=1 git branch --all --verbose
GIT_TRACE_REFS=1 git show-ref
```

Nếu số lượng ref lớn hoặc repository dùng backend ref đặc thù, trace có thể giúp nhận diện bước đọc/ghi refs. Không nên kết luận chỉ từ số dòng trace; cần đối chiếu thời gian thực thi và cấu trúc repository.

## 8. Chọn trace theo triệu chứng

Không có một biến trace duy nhất phù hợp với mọi sự cố. Bảng sau gợi ý điểm bắt đầu:

| Triệu chứng | Trace nên thử trước | Điều cần quan sát |
|---|---|---|
| `git status` hoặc `git log` chậm | `GIT_TRACE_PERFORMANCE`, `GIT_TRACE2_PERF` | Tổng thời gian và vùng xử lý nội bộ |
| Git gọi sai chương trình hoặc alias | `GIT_TRACE` | Lệnh được mở rộng và tiến trình con |
| Git nhận diện sai repository/worktree | `GIT_TRACE_SETUP` | Git directory, worktree, prefix và ngữ cảnh hiện tại |
| `fetch`/`push` chậm ở protocol | `GIT_TRACE_PACKET` | Trao đổi packet và giai đoạn thương lượng |
| Remote HTTPS chậm hoặc lỗi HTTP | `GIT_TRACE_CURL` | Kết nối, TLS, HTTP status, redirect và thời gian phản hồi |
| Đọc object/lịch sử local chậm | `GIT_TRACE_PACK_ACCESS` | Truy cập packfile và offset |
| Đọc/ghi branch hoặc tag chậm | `GIT_TRACE_REFS` | Hoạt động ref database |
| Lệnh phức tạp, nhiều tiến trình con | `GIT_TRACE2_EVENT` | Trình tự event và thời lượng tiến trình con |

Hãy chọn trace theo triệu chứng thay vì bật toàn bộ. Nếu trace hiệu năng cho thấy Git chờ một tiến trình con, bật thêm trace phù hợp cho transport hoặc hook; nếu thời gian nằm trong vùng xử lý nội bộ, chuyển sang trace pack/ref hoặc profiler sâu hơn.

## 9. Quy trình điều tra một lệnh Git chậm

Một quy trình nhất quán giúp tránh thay đổi cấu hình khi chưa biết nguyên nhân.

### Bước 1: Ghi nhận lệnh và điều kiện tái hiện

Ghi lại:

- Lệnh đầy đủ và tham số.
- Repository, branch và remote liên quan.
- Phiên bản Git bằng `git --version`.
- Hệ điều hành, loại filesystem và kết nối mạng nếu liên quan.
- Thời gian chạy bình thường và thời gian chạy khi có vấn đề.

Thử lại cùng lệnh trong điều kiện tương đương. Một lần chạy đầu có thể chịu ảnh hưởng của cache lạnh, trong khi lần sau nhanh hơn vì object hoặc metadata đã nằm trong cache hệ điều hành.

### Bước 2: Đo tổng thời gian bằng performance trace

Ví dụ:

```bash
GIT_TRACE_PERFORMANCE=1 git status
```

Hoặc dùng Trace2:

```bash
GIT_TRACE2_PERF=/tmp/git-status.perf git status
```

Xác định thời gian tổng thể và vùng xử lý có thời lượng đáng chú ý.

### Bước 3: Xem Git có gọi tiến trình con không

```bash
GIT_TRACE=1 GIT_TRACE2_PERF=/tmp/git-command.perf git fetch origin
```

Nếu trace cho thấy Git gọi SSH, credential helper, hook hoặc chương trình khác, kiểm tra thời gian của tiến trình đó và cấu hình tương ứng.

### Bước 4: Bật trace chuyên biệt

- Nếu nghi vấn protocol, dùng `GIT_TRACE_PACKET`.
- Nếu dùng HTTP(S), dùng `GIT_TRACE_CURL` và cân nhắc `GIT_TRACE_CURL_NO_DATA`.
- Nếu nghi vấn packfile, dùng `GIT_TRACE_PACK_ACCESS`.
- Nếu nghi vấn refs, dùng `GIT_TRACE_REFS`.

Chỉ bật trace cần thiết để giữ log ngắn và dễ đọc.

### Bước 5: Đưa ra giả thuyết và kiểm chứng

Ví dụ, nếu `fetch` chậm và trace cho thấy phần lớn thời gian nằm ở chờ phản hồi HTTP, giả thuyết có thể là mạng, proxy hoặc server. Nếu thời gian nằm ở xử lý pack sau khi dữ liệu đã nhận, hãy xem dung lượng pack, CPU, I/O và object database. Mỗi thay đổi cấu hình nên được kiểm chứng bằng cách chạy lại cùng lệnh trong điều kiện tương đương.

### Bước 6: Tắt trace và lưu kết quả cần thiết

Sau khi thu thập xong, xóa các biến môi trường đã đặt trong shell hiện tại. Giữ lại log cần thiết ở vị trí ngoài repository và loại bỏ thông tin nhạy cảm trước khi gửi cho nhóm hỗ trợ.

## 10. Ví dụ thực tế: điều tra fetch chậm

Giả sử `git fetch origin` mất vài phút. Bắt đầu bằng đo hiệu năng và ghi Trace2:

```bash
GIT_TRACE2_PERF=/tmp/fetch-perf.log git fetch origin
```

Nếu thấy thời gian lớn ở tiến trình transport, bật packet trace:

```bash
GIT_TRACE_PACKET=1 GIT_TRACE2_PERF=/tmp/fetch-protocol.perf git fetch origin
```

Nếu remote dùng HTTPS, thêm curl trace:

```bash
GIT_TRACE_CURL=1 GIT_TRACE_CURL_NO_DATA=1 \
GIT_TRACE2_PERF=/tmp/fetch-http.perf git fetch origin
```

Đọc kết quả theo thứ tự:

1. Trace2 cho biết tổng thời gian và tiến trình con nào chiếm thời gian.
2. Packet trace cho biết giai đoạn thương lượng và trao đổi với remote.
3. Curl trace giúp xem kết nối HTTP, TLS, status code, redirect hoặc retry.
4. Nếu dữ liệu đã về nhưng xử lý vẫn lâu, chuyển sang kiểm tra pack/object, CPU và I/O.

Không nên kết luận “Git chậm” chỉ vì tổng thời gian fetch dài. Nguyên nhân có thể nằm ở DNS, proxy, VPN, server hosting, xác thực, dung lượng dữ liệu hoặc tốc độ đĩa local.

## 11. Ví dụ thực tế: điều tra git status chậm

`git status` cần so sánh index, HEAD và working tree. Trong repository có rất nhiều tệp, filesystem chậm hoặc antivirus quét thư mục, thao tác này có thể tốn thời gian.

Đo trước:

```bash
GIT_TRACE_PERFORMANCE=1 git status
```

Nếu cần phân tích sâu:

```bash
GIT_TRACE2_PERF=/tmp/status.perf git status
GIT_TRACE_SETUP=1 git status
```

Trace setup giúp xác nhận Git đang kiểm tra đúng working tree. Trace hiệu năng giúp xem thời gian có nằm trong khâu đọc index, refresh trạng thái hoặc các vùng xử lý khác mà phiên bản Git phát ra hay không.

Nếu nghi ngờ vấn đề liên quan đến filesystem, tiếp tục kiểm tra số lượng tệp, filesystem/network drive, antivirus/indexer và cấu hình monitor phù hợp. Trace Git giúp xác định phần Git đang chờ; nó không thay thế phép đo hệ điều hành về thời gian truy cập tệp.

## 12. Lưu log và đọc dữ liệu Trace2 JSON

Khi log dài, nên ghi vào thư mục tạm bên ngoài repository để không vô tình stage hoặc commit log chẩn đoán.

Unix-like shell:

```bash
GIT_TRACE2_EVENT=/tmp/git-trace.json git status
```

PowerShell:

```powershell
$traceFile = Join-Path $env:TEMP "git-trace.json"
$env:GIT_TRACE2_EVENT = $traceFile
git status
Remove-Item Env:GIT_TRACE2_EVENT
Get-Item $traceFile
```

Trace2 event là JSON theo từng dòng (*JSON Lines*), nên có thể lọc bằng công cụ xử lý JSON. Ví dụ nếu đã cài `jq`, xem các sự kiện khởi chạy và kết thúc tiến trình con:

```bash
jq 'select(.event == "child_start" or .event == "child_exit")' /tmp/git-trace.json
```

Tên trường chi tiết phụ thuộc loại event. Hãy đọc cấu trúc thực tế trước khi viết bộ phân tích cố định. Khi cần so sánh nhiều lần chạy, lưu riêng log cho từng lần và ghi kèm phiên bản Git, lệnh, branch cùng điều kiện thử nghiệm.

## 13. Bảo mật và giới hạn của trace

Trace có thể chứa thông tin mà bạn không muốn công khai:

- URL remote, hostname, đường dẫn repository và tên branch.
- Metadata packet/protocol hoặc tên ref.
- Thông tin HTTP, header, cookie, proxy hoặc chi tiết xác thực.
- Đường dẫn local, tên người dùng và thông tin môi trường.
- Tên tiến trình, tham số dòng lệnh hoặc hook đang chạy.

Một số trace có thể chứa dữ liệu rất lớn hoặc thông tin nhạy cảm tùy transport và phiên bản Git. Không đăng nguyên log lên issue công khai trước khi rà soát và che thông tin riêng. Không đưa token hoặc mật khẩu vào command line để trace chúng; dùng credential helper và cơ chế xác thực phù hợp.

Trace cũng tạo thêm chi phí ghi log và xử lý. Bật nhiều biến cùng lúc có thể làm log lớn, tăng overhead và khiến thời gian đo khác với lúc chạy bình thường. Hãy dùng trace ngắn, tái hiện có kiểm soát và tắt ngay sau khi thu thập đủ thông tin.

Trace nội bộ của Git không phải profiler toàn hệ thống. Nếu cần tìm CPU hotspot, syscall, page fault, I/O latency hoặc DNS timing chi tiết, hãy kết hợp profiler của hệ điều hành, công cụ mạng và log từ server.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `GIT_TRACE=1` cho biết đầy đủ nguyên nhân mọi lệnh chậm | Nó cung cấp trace tổng quát; cần chọn trace hiệu năng hoặc trace chuyên biệt theo triệu chứng |
| `GIT_TRACE_PERFORMANCE` tự tối ưu Git | Nó chỉ ghi số liệu thời gian, không thay đổi hiệu năng |
| Trace2 event JSON luôn có cùng tập event | Event phụ thuộc lệnh, phiên bản Git và các nhánh thực thi |
| Packet trace chỉ chứa thông tin vô hại | Nó có thể tiết lộ ref, URL hoặc metadata giao thức; cần rà soát trước khi chia sẻ |
| Curl trace chỉ dùng cho SSH | `GIT_TRACE_CURL` dành cho transport HTTP(S); SSH cần kiểm tra tiến trình SSH và trace phù hợp |
| Trace pack access xác định chính xác blob lớn nhất | Nó ghi hoạt động truy cập packfile, không phải báo cáo xếp hạng dung lượng object |
| Mọi hook đều xuất hiện giống nhau trong trace | Hook chỉ xuất hiện khi được gọi; cần kiểm tra tên hook, `core.hooksPath` và tiến trình con |
| Trace chậm chứng minh Git core là nguyên nhân | Thời gian có thể nằm ở mạng, filesystem, credential helper, hook hoặc chương trình bên ngoài |

## 15. Ghi nhớ

Hãy bắt đầu chẩn đoán bằng `GIT_TRACE_PERFORMANCE` hoặc `GIT_TRACE2_PERF` để tìm giai đoạn mất thời gian. Dùng `GIT_TRACE` để xem lệnh con, `GIT_TRACE_SETUP` để xác minh repository context, `GIT_TRACE_PACKET` cho giao thức, `GIT_TRACE_CURL` cho HTTP(S), `GIT_TRACE_PACK_ACCESS` cho packfile và `GIT_TRACE_REFS` cho ref database. Khi cần phân tích tự động hoặc nhiều tiến trình, `GIT_TRACE2_EVENT` cung cấp dữ liệu JSON có cấu trúc.

Chỉ bật trace cần thiết, lưu log ngoài repository, tắt biến môi trường sau khi đo và rà soát thông tin nhạy cảm trước khi chia sẻ. Dùng kết quả để hình thành giả thuyết rồi kiểm chứng bằng lần chạy tương đương. Trace cho biết Git đang làm gì và dành thời gian ở đâu; quyết định tối ưu cần dựa trên nguyên nhân đã được xác nhận.
