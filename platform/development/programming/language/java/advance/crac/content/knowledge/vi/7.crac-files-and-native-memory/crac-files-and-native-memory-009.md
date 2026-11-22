# Chính sách file descriptor qua `jdk.crac.resource-policies`

Trước khi tạo checkpoint, CRaC cần đưa tiến trình về trạng thái có thể khôi phục an toàn. Trên Linux, file, pipe và socket đang mở được biểu diễn bằng **file descriptor (FD)**. Một FD còn mở có thể khiến checkpoint thất bại vì tài nguyên đó vẫn gắn với môi trường bên ngoài hoặc không thể được khôi phục đúng cách.

Cách ưu tiên là ứng dụng chủ động quản lý vòng đời tài nguyên bằng CRaC `Resource`: đóng hoặc tạm dừng trước checkpoint, sau đó mở lại hoặc xác thực lại sau restore. Tuy nhiên, đôi khi FD được mở bên trong một thư viện mà nhóm phát triển không thể sửa, hoặc thư viện chưa có tích hợp CRaC. Trong những trường hợp đó, một số bản CRaC cung cấp cấu hình `jdk.crac.resource-policies` để chỉ định runtime cần xử lý các FD được mở qua JDK API như thế nào.

Đây là cơ chế hỗ trợ có giới hạn. Nó không thay thế việc quản lý tài nguyên trong ứng dụng và không xử lý FD được tạo trực tiếp từ native code. Muốn dùng an toàn, cần hiểu loại FD, hành động được hỗ trợ, thứ tự rule và hành vi sau restore của đúng bản JDK đang chạy.

## 1. File descriptor là gì và vì sao ảnh hưởng đến checkpoint?

File descriptor là một định danh mà tiến trình dùng để truy cập một tài nguyên do hệ điều hành quản lý. Trên Linux, FD có thể đại diện cho:

- File đang đọc hoặc ghi.
- Directory được mở để duyệt.
- Pipe dùng để truyền dữ liệu giữa các tiến trình hoặc thread.
- Socket TCP, UDP hoặc Unix domain.
- Một tài nguyên khác được mở ở tầng hệ điều hành.

Trong Java, một FD có thể được sở hữu gián tiếp bởi `FileInputStream`, `FileOutputStream`, `RandomAccessFile`, NIO channel, socket hoặc một thư viện cấp cao hơn. Ví dụ, một logger có thể giữ file handle mở trong suốt vòng đời ứng dụng; một HTTP client có thể duy trì socket trong connection pool; một thư viện có thể giữ pipe để giao tiếp với tiến trình con.

Khi checkpoint, tiến trình được lưu lại để tiếp tục ở một thời điểm hoặc môi trường khác. Nếu một file đang mở trỏ đến đường dẫn không còn tồn tại, một socket vẫn gắn với phiên mạng cũ hoặc một pipe có đầu bên kia không còn hợp lệ, việc tiếp tục sử dụng FD sau restore có thể thất bại hoặc tạo hành vi sai.

Vì vậy, CRaC thường yêu cầu ứng dụng đóng các file và kết nối mạng trước checkpoint, ngoại trừ một số tài nguyên được nền tảng xử lý theo quy tắc riêng. Nếu vẫn còn FD không được xử lý, checkpoint có thể bị từ chối với `CheckpointException` và một exception phụ cho biết FD nào còn mở.

## 2. `jdk.crac.resource-policies` giải quyết việc gì?

`jdk.crac.resource-policies` là system property dùng để chỉ định đường dẫn đến file chứa các rule xử lý FD. Runtime đọc file rule khi thực hiện checkpoint và áp dụng hành động tương ứng với từng FD khớp rule.

Cấu hình này hữu ích khi:

- Một thư viện bên thứ ba giữ file handle nhưng không cung cấp callback để đóng/mở theo CRaC.
- Ứng dụng không thể thay đổi mã nguồn của thành phần đang mở FD.
- Có một số file ổn định có thể đóng trước checkpoint và mở lại sau restore.
- Cần giới hạn hoặc phân loại một số FD trong quá trình chuyển đổi ứng dụng sang CRaC.

Ví dụ, một thư viện logging mở file log và không cho phép nhóm phát triển can thiệp vào vòng đời của file handle. Nếu runtime và phiên bản thư viện hỗ trợ, policy có thể yêu cầu đóng file trước checkpoint rồi mở lại file ở vị trí trước đó sau restore.

Property được truyền vào JVM bằng `-D`:

```bash
java \
  -Djdk.crac.resource-policies=/etc/orders/crac-resource-policies.yml \
  -XX:CRaCCheckpointTo=/var/lib/orders/checkpoint \
  -jar orders-service.jar
```

`/etc/orders/crac-resource-policies.yml` là đường dẫn ví dụ. File phải tồn tại, có quyền đọc phù hợp và dùng cú pháp mà bản JDK CRaC hỗ trợ. Tên tùy chọn checkpoint và engine cũng phụ thuộc bản phân phối; hãy kiểm tra hướng dẫn runtime cụ thể trước khi áp dụng lệnh vào môi trường triển khai.

`jdk.crac.resource-policies` không phải một API thay thế `org.crac.Resource`. Policy điều khiển cách runtime xử lý một số FD đã mở. Nó không biết ý nghĩa nghiệp vụ của transaction, request, consumer hoặc connection pool. Nếu ứng dụng sở hữu tài nguyên và có thể sửa mã, nên quản lý tài nguyên rõ ràng trong callback.

## 3. Cấu trúc file policy

File policy gồm nhiều rule. Mỗi rule là một nhóm cặp `key: value`; các rule được phân tách bằng một dòng chứa ba dấu gạch ngang `---`. Dòng bắt đầu bằng `#` là comment. Cú pháp là một tập con của YAML, vì vậy nên dùng file `.yml` hoặc `.yaml` đơn giản, tránh các tính năng YAML phức tạp mà parser của runtime có thể không hỗ trợ.

Hai thuộc tính bắt buộc của mỗi rule là:

- `type`: loại file descriptor cần so khớp.
- `action`: hành động runtime sẽ thực hiện.

Ví dụ:

```yaml
type: file
path: /var/log/orders/application.log
action: reopen
---
# Đóng các file tạm thuộc ứng dụng trước checkpoint.
type: file
path: /tmp/orders/**
action: close
```

Các giá trị của `type` và `action` không phân biệt chữ hoa/chữ thường theo tài liệu triển khai. Nên thống nhất chữ thường để file dễ đọc.

### 3.1. Thứ tự rule có ý nghĩa

Với mỗi FD đang mở, runtime kiểm tra các rule theo thứ tự từ trên xuống. **Rule đầu tiên khớp sẽ được áp dụng; các rule sau không được xét cho FD đó.** Vì vậy, hãy đặt rule cụ thể trước rule tổng quát.

Ví dụ:

```yaml
# File log quan trọng được mở lại sau restore.
type: file
path: /var/log/orders/audit.log
action: reopen
---
# Những file khác trong thư mục log được xử lý theo nhóm.
type: file
path: /var/log/orders/**
action: close
```

Nếu đảo thứ tự, rule `/var/log/orders/**` sẽ khớp cả `audit.log`, khiến rule riêng phía dưới không bao giờ được áp dụng cho file đó.

Nếu không có rule nào khớp, hành vi mặc định là `error`: runtime báo lỗi và checkpoint thất bại. Đây là mặc định có chủ đích để một FD chưa được phân loại không âm thầm đi vào image.

### 3.2. `warn: false`

Với các hành động khác `error`, runtime thường ghi warning khi tìm thấy FD được xử lý theo policy. Có thể thêm:

```yaml
warn: false
```

để tắt warning cho rule đó. Thuộc tính này chỉ kiểm soát thông báo cảnh báo; nó không đổi hành động và không làm một FD trở nên an toàn hơn. Trong giai đoạn thiết lập ban đầu, nên giữ warning để quan sát những FD đang được policy xử lý. Chỉ tắt sau khi đã hiểu và chấp nhận tác động.

## 4. Các loại file descriptor

Policy hỗ trợ bốn loại chính. Mỗi loại có tiêu chí nhận diện và tập hành động phù hợp.

| `type` | Ý nghĩa | Cách nhận diện thường dùng |
|---|---|---|
| `file` | File hoặc directory trên filesystem cục bộ | `path` |
| `pipe` | Anonymous pipe | Loại FD; không có path để phân biệt từng pipe |
| `socket` | Socket TCP, UDP hoặc Unix domain | Family, địa chỉ, port hoặc path |
| `filedescriptor` | FD thô không được nhận diện là file/pipe/socket ở tầng cao hơn | Số FD `value` hoặc mô tả native `regex` |

Tên loại `filedescriptor` được dùng cho FD thô. Không nhầm nó với loại `file`, vốn có thể được nhận diện qua đường dẫn filesystem.

## 5. Policy cho file và directory

### 5.1. Chọn file bằng `path`

Rule loại `file` dùng `path` để xác định file hoặc directory. Có thể dùng đường dẫn cụ thể hoặc glob pattern theo cơ chế `FileSystem.getPathMatcher()` của Java.

Ví dụ:

```yaml
type: file
path: /etc/orders/application.yml
action: reopen
---
type: file
path: /var/log/orders/*.log
action: reopen
---
type: file
path: /tmp/orders/**
action: close
```

Ý nghĩa:

- File cấu hình cụ thể được đóng trước checkpoint và mở lại sau restore.
- Các file log khớp glob được xử lý theo rule thứ hai.
- Các file nằm trong cây thư mục tạm của ứng dụng được đóng; code không được tiếp tục dùng handle đó sau restore.

Glob `*` thường dùng để khớp tên trong một cấp đường dẫn; `**` có thể khớp qua nhiều cấp thư mục theo quy tắc glob của Java. Hãy xác nhận pattern bằng `PathMatcher` và thử trên đúng filesystem, đặc biệt khi đường dẫn có dấu cách, ký tự đặc biệt hoặc khác biệt giữa hệ điều hành.

### 5.2. Các action cho file

| Action | Runtime thực hiện | Hệ quả sau restore |
|---|---|---|
| `error` | Báo lỗi và làm checkpoint thất bại | Không có image hợp lệ từ lần checkpoint đó |
| `ignore` | Để checkpoint/restore engine xử lý FD | Engine có thể xác thực và mở lại file khi restore; kết quả phụ thuộc môi trường |
| `close` | Đóng file trước checkpoint | Nếu code tiếp tục dùng handle cũ sau restore, thao tác sẽ lỗi runtime |
| `reopen` | Đóng file trước checkpoint và thử mở lại sau restore | File được mở lại tại vị trí trước đó nếu việc mở lại thành công |

`reopen` phù hợp với một file có đường dẫn ổn định và ứng dụng có thể tiếp tục dùng cùng handle sau khi nó được mở lại. Nếu file bị xóa, đổi tên, mount khác hoặc quyền truy cập thay đổi trong lúc image được lưu, thao tác reopen có thể thất bại.

`close` chỉ phù hợp khi thành phần sở hữu FD sẽ không sử dụng handle đó sau restore, hoặc ứng dụng có một cơ chế khác để tạo handle mới. Đóng một FD nhưng giữ nguyên object Java đang tham chiếu đến nó không làm object tự động có một FD mới.

`ignore` chuyển trách nhiệm cho engine. Đây không phải cam kết rằng mọi file sẽ luôn được khôi phục thành công. File có thể được kiểm tra theo trạng thái filesystem và điều kiện restore; hãy thử trong môi trường thực tế.

### 5.3. Ví dụ cho log và file tạm

Một cấu hình mẫu có thể là:

```yaml
# Logger cần tiếp tục ghi vào file sau restore.
type: file
path: /var/log/orders/application.log
action: reopen
---
# File tạm chỉ dùng trước checkpoint.
type: file
path: /tmp/orders/**
action: close
---
# Những file log khác để checkpoint engine xử lý.
type: file
path: /var/log/orders/*.log
action: ignore
```

Rule riêng cho `application.log` phải đứng trước glob log chung. Nếu không, rule chung có thể khớp trước và làm thay đổi hành vi mong muốn.

Trong ứng dụng thực tế, nên ưu tiên cấu hình logger có callback đóng/reopen chính thức. Policy glob chỉ nên được dùng khi không thể quản lý resource trực tiếp và đã xác minh rằng logger không giữ thêm FD khác.

## 6. Policy cho pipe

Pipe là kênh truyền dữ liệu. Anonymous pipe không có path hoặc địa chỉ ổn định để phân biệt như file hay socket. Vì vậy, tài liệu CRaC khuyến nghị chỉ nên có tối đa một rule cho anonymous pipe.

Ví dụ:

```yaml
type: pipe
action: close
```

Các action được hỗ trợ cho pipe là:

- `error`: mặc định báo lỗi và làm checkpoint thất bại.
- `ignore`: để checkpoint/restore engine xử lý pipe.
- `close`: đóng pipe trước checkpoint.

Pipe có thể được dùng nội bộ bởi thư viện, executor hoặc tiến trình con. Nếu đóng pipe trong khi một thành phần vẫn chờ đọc/ghi, thread có thể nhận EOF, lỗi I/O hoặc bị kẹt tùy cách thư viện xử lý. Vì vậy, cần xác định chủ sở hữu pipe và trạng thái các thread liên quan trước khi chọn `close`.

Named pipe được nhận diện như loại `file` và xử lý bằng rule `type: file` theo đường dẫn.

## 7. Policy cho socket

Socket đại diện cho kết nối mạng hoặc Unix domain socket. Một rule `socket` có thể được tinh chỉnh bằng các thuộc tính để chỉ áp dụng cho nhóm socket phù hợp.

Các thuộc tính nhận diện thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| `family` | Họ địa chỉ: IPv4, IPv6 hoặc Unix domain |
| `localAddress` | Địa chỉ local; `*` có thể khớp mọi địa chỉ bind |
| `remoteAddress` | Địa chỉ peer ở đầu bên kia; `*` có thể khớp mọi địa chỉ |
| `localPort` | Port local; có thể dùng số hoặc `*` |
| `remotePort` | Port remote; có thể dùng số hoặc `*` |
| `localPath` | Path local của Unix domain socket; hỗ trợ glob |
| `remotePath` | Path remote của Unix domain socket; hỗ trợ glob |
| `listening` | Trong các phiên bản hỗ trợ thuộc tính này, chọn listening/server socket |

Giá trị `family` thường có các alias:

- `ipv6` hoặc `inet6`: socket IPv6.
- `ipv4` hoặc `inet4`: socket IPv4.
- `ip` hoặc `inet`: IPv4 hoặc IPv6.
- `unix`: Unix domain socket.

### 7.1. Ví dụ lọc socket

Ví dụ chọn socket TCP local port 8080:

```yaml
type: socket
family: ipv4
localPort: 8080
action: close
```

Ví dụ chọn Unix domain socket theo path:

```yaml
type: socket
family: unix
localPath: /run/orders/*.sock
action: close
```

Các điều kiện bổ sung giúp policy chỉ tác động đến đúng socket dự kiến. Không nên dùng một rule rộng như `type: socket` và `action: close` nếu ứng dụng còn cần socket đó để phục vụ request hoặc quản lý kết nối sau restore.

### 7.2. Giới hạn của `reopen` với socket

Hành vi `reopen` cho socket phụ thuộc phiên bản JDK/CRaC. Tài liệu triển khai Azul hiện hành hỗ trợ thuộc tính `listening: true` để chọn server socket đang lắng nghe; với các bản hỗ trợ, `action: reopen` đóng listening socket trước checkpoint rồi mở lại socket trên cùng địa chỉ local sau restore.

Socket hai đầu đang kết nối giữa client và server không thể được phục hồi theo cách này; tài liệu Azul ghi rõ `reopen` với loại socket đó sẽ báo lỗi. Tài liệu tham chiếu CRaC cộng đồng cũng mô tả giới hạn socket reopen ở các triển khai chưa hỗ trợ phần mở lại. Do đó, không suy ra rằng mọi JDK CRaC đều hỗ trợ `reopen` cho socket. Hãy kiểm tra đúng phiên bản và nhà cung cấp.

Ví dụ dành cho runtime có hỗ trợ `listening: true`:

```yaml
type: socket
family: inet
localPort: 8080
listening: true
action: reopen
```

Nếu runtime không hỗ trợ thuộc tính `listening` hoặc socket reopen, hãy quản lý server socket bằng CRaC `Resource` hoặc dùng action được tài liệu phiên bản đó cho phép. Với kết nối client, thường cần đóng trước checkpoint và tạo kết nối mới sau restore thông qua logic ứng dụng.

## 8. Policy cho raw file descriptor

Một số FD không có object Java cấp cao tương ứng để runtime nhận diện như file, pipe hoặc socket. Ví dụ, FD được tạo bởi một phần native library hoặc được truyền từ mã native vào JVM. Policy có thể nhận diện FD loại này bằng:

- `value`: số FD cụ thể.
- `regex`: biểu thức chính quy khớp native description của FD, theo cú pháp `java.util.regex.Pattern`.

Ví dụ:

```yaml
type: filedescriptor
value: 123
action: close
---
type: filedescriptor
regex: .*eventfd.*
action: ignore
```

Số FD như `123` có thể thay đổi giữa các lần khởi chạy do thứ tự mở tài nguyên khác nhau. Vì vậy, rule theo số FD dễ trở nên không chính xác nếu môi trường không cố định. Regex theo native description có thể linh hoạt hơn nhưng vẫn phụ thuộc cách kernel và runtime hiển thị mô tả; cần kiểm tra log thực tế.

Với raw FD, chỉ có `error`, `ignore` và `close`; không có `reopen`, vì runtime không có đủ thông tin cấp cao để tái tạo object sở hữu FD.

## 9. Ví dụ cấu hình tổng hợp

Ví dụ dưới đây minh họa cách sắp xếp rule cụ thể trước rule tổng quát và dùng hành động khác nhau cho từng nhóm FD:

```yaml
# 1. File log chính: mở lại sau restore.
type: file
path: /var/log/orders/application.log
action: reopen
---
# 2. File tạm: đóng, ứng dụng không dùng lại handle cũ.
type: file
path: /tmp/orders/**
action: close
---
# 3. Named pipe được biểu diễn như file.
type: file
path: /run/orders/*.pipe
action: close
---
# 4. Anonymous pipe: áp dụng cho pipe không định danh được.
type: pipe
action: close
---
# 5. Listening socket: chỉ dùng trên runtime hỗ trợ thuộc tính này.
type: socket
family: inet
localPort: 8080
listening: true
action: reopen
---
# 6. Raw descriptor: mặc định từ chối nếu chưa có quyết định rõ.
type: filedescriptor
regex: .*eventfd.*
action: error
```

Đây là ví dụ minh họa, không phải policy có thể áp dụng nguyên trạng cho mọi ứng dụng. Đặc biệt, rule socket `reopen` cần runtime hỗ trợ; pipe và raw FD chỉ nên xử lý sau khi đã xác định thành phần sở hữu chúng. Hãy bắt đầu bằng policy hẹp, quan sát log, sau đó bổ sung từng rule khi đã biết FD nào đang mở và vì sao.

## 10. Chẩn đoán FD còn mở khi checkpoint thất bại

Khi checkpoint thất bại, exception có thể cho biết loại FD, số FD và đường dẫn hoặc mô tả tài nguyên. Hãy dùng thông tin đó để tìm component đã mở FD và chọn cách xử lý đúng.

### 10.1. Bật stack trace cho FD mở qua Java API

Một số bản CRaC cung cấp property:

```bash
-Djdk.crac.collect-fd-stacktraces=true
```

Property này giúp ghi lại stack trace tại thời điểm FD được tạo qua Java API. Khi checkpoint báo một FD còn mở, stack trace có thể chỉ ra thread và vị trí trong mã đã mở file hoặc socket.

Ví dụ lệnh khởi chạy chẩn đoán:

```bash
java \
  -Djdk.crac.collect-fd-stacktraces=true \
  -XX:CRaCCheckpointTo=/tmp/orders-checkpoint \
  -jar orders-service.jar
```

Sau khi xác định nguồn mở FD, ưu tiên sửa lifecycle của component hoặc dùng callback CRaC mà thư viện cung cấp. Policy chỉ nên là giải pháp phù hợp cho tài nguyên không thể sửa trực tiếp.

### 10.2. Điều tra FD do native code tạo

`jdk.crac.resource-policies` không xử lý FD được mở trực tiếp từ native code. Khi log chỉ ra một FD native hoặc không có stack Java, cần điều tra syscall tạo FD. Trên Linux, `strace` có thể theo dõi tiến trình và thread:

```bash
strace -f -o /tmp/orders-strace.log java -jar orders-service.jar
```

Có thể lọc các syscall mở tài nguyên như `openat`, `socket`, `pipe2`, `dup` hoặc `dup2` để tìm nơi tạo FD. Tùy bản build và quyền hệ thống, việc thu stack native có thể cần symbol/debug package phù hợp.

Sau khi tìm ra nguồn, hãy dùng API native/library để đóng tài nguyên đúng lúc hoặc bổ sung lifecycle integration. Không cố áp dụng rule Java policy cho FD mà policy không thể quản lý.

### 10.3. Phân biệt policy với lỗi callback Resource

`CheckpointException` có thể tổng hợp nhiều lỗi khác nhau: Resource callback thất bại, FD còn mở hoặc điều kiện nền tảng không đáp ứng. Hãy đọc cả exception chính lẫn suppressed exceptions. Nếu một `Resource.beforeCheckpoint()` không đóng được pool, việc thêm policy cho file không giải quyết được lỗi lifecycle đó.

## 11. Nguyên tắc chọn policy an toàn

Trước khi thêm rule, trả lời các câu hỏi:

1. FD thuộc loại nào: file, pipe, socket hay raw descriptor?
2. Thành phần nào đã mở nó và ai sở hữu vòng đời?
3. FD có thể được đóng bằng API chính thức của thư viện không?
4. Nếu dùng `close`, code có còn sử dụng object cũ sau restore không?
5. Nếu dùng `reopen`, đường dẫn hoặc địa chỉ có còn tồn tại và hợp lệ sau restore không?
6. Nếu dùng `ignore`, engine có thể khôi phục tài nguyên trong môi trường đích không?
7. Rule có vô tình khớp những FD khác do glob hoặc điều kiện quá rộng không?
8. Runtime đang dùng có hỗ trợ chính xác action và thuộc tính trong rule không?

Một số nguyên tắc thực hành:

- Ưu tiên sửa ứng dụng hoặc thư viện để đóng/mở tài nguyên qua `Resource`.
- Dùng policy cho phần không thể can thiệp trực tiếp, không dùng để che giấu FD leak.
- Đặt rule cụ thể trước rule tổng quát.
- Giữ action mặc định `error` cho FD chưa được phân loại.
- Dùng `reopen` cho file khi cần tiếp tục dùng handle và đã kiểm tra đường dẫn/position.
- Dùng `close` khi chắc chắn code không tiếp tục sử dụng handle cũ.
- Chỉ dùng socket `reopen` cho loại socket mà đúng runtime công bố hỗ trợ.
- Không dùng policy Java cho FD được mở từ native code.
- Giữ warning trong giai đoạn quan sát và ghi nhận mọi FD được policy xử lý.
- Kiểm tra checkpoint lẫn restore; một rule chỉ làm checkpoint thành công chưa chứng minh ứng dụng hoạt động đúng sau restore.

## 12. Quy trình triển khai policy

Có thể đưa `jdk.crac.resource-policies` vào dự án theo trình tự:

**Bước 1 — Thu thập FD.** Chạy ứng dụng trên runtime CRaC và ghi lại lỗi checkpoint hoặc danh sách FD còn mở. Bật stack trace nếu FD được tạo qua Java API.

**Bước 2 — Xác định chủ sở hữu.** Tìm class, thư viện, thread hoặc native component đã mở FD. Xác định FD có cần tồn tại sau restore hay không.

**Bước 3 — Ưu tiên lifecycle API.** Nếu có thể sửa ứng dụng hoặc thư viện, đăng ký Resource để đóng trước checkpoint và mở lại sau restore. Nếu không thể, chọn policy phù hợp với FD.

**Bước 4 — Viết rule hẹp.** Chỉ rõ `type`, `path`, socket filter hoặc raw FD matcher và action. Đặt rule cụ thể lên trước. Tránh wildcard quá rộng.

**Bước 5 — Truyền system property.** Đưa `-Djdk.crac.resource-policies=/path/to/policy.yml` vào cấu hình JVM dùng khi checkpoint. Bảo đảm file policy có mặt và được đọc trong môi trường tạo image.

**Bước 6 — Kiểm tra log.** Xem warning và xác nhận đúng FD được áp dụng đúng rule. Nếu policy không khớp, hành vi mặc định `error` sẽ giúp phát hiện FD chưa được xử lý.

**Bước 7 — Kiểm tra restore.** Xác nhận file reopen được, handle close không bị dùng lại, socket/pipe được phục hồi theo hỗ trợ thực tế và ứng dụng đạt readiness.

**Bước 8 — Khóa cấu hình theo runtime.** Ghi lại phiên bản JDK/vendor, policy file, checksum và kết quả kiểm thử. Khi nâng cấp JDK, xác minh lại parser, thuộc tính và hành vi từng action.

## 13. Những sai lầm thường gặp

**Coi policy là cách thay thế hoàn toàn CRaC Resource.** Policy chỉ xử lý FD trong phạm vi hỗ trợ; nó không điều phối transaction, scheduler, thread hay logic nghiệp vụ. Hãy dùng Resource cho lifecycle mà ứng dụng kiểm soát được.

**Nghĩ rằng policy xử lý được native FD.** Cơ chế này chỉ áp dụng cho FD mở qua JDK API. FD do native code tạo cần được xử lý trong native/library hoặc điều tra riêng.

**Đặt rule wildcard trước rule cụ thể.** Rule đầu tiên khớp sẽ thắng. Một rule tổng quát đặt trên đầu có thể khiến rule đặc biệt không bao giờ được chạy.

**Dùng `close` rồi tiếp tục dùng object cũ.** Handle đã đóng không tự được mở lại. Nếu code cần tiếp tục truy cập, dùng `reopen` khi phù hợp hoặc tạo resource mới qua callback.

**Dùng `ignore` mà không kiểm tra engine.** Việc giao cho CRIU/engine không đảm bảo tài nguyên luôn khôi phục được trong môi trường khác. Cần kiểm tra path, mount và điều kiện restore.

**Dùng `reopen` cho mọi socket.** Socket client/server hai đầu không thể được mở lại như file. Chỉ dùng khả năng listening socket reopen khi đúng runtime hỗ trợ.

**Tắt warning quá sớm.** Warning là dấu hiệu quan trọng để biết policy đang xử lý FD nào. Hãy giữ log trong quá trình thiết lập và kiểm thử.

**Không kiểm tra sau restore.** Checkpoint thành công chỉ chứng minh bước tạo image đã qua các điều kiện tại thời điểm đó. Ứng dụng vẫn có thể lỗi khi dùng file handle, pipe hoặc socket sau restore.

## 14. Tự kiểm tra mức độ hiểu

1. **`jdk.crac.resource-policies` nhận giá trị gì?** Đường dẫn đến file rule chứa các chính sách xử lý file descriptor.
2. **Hai thuộc tính bắt buộc của một rule là gì?** `type` và `action`.
3. **Nếu nhiều rule cùng khớp một FD thì rule nào được áp dụng?** Rule đầu tiên theo thứ tự file; các rule sau bị bỏ qua cho FD đó.
4. **Action `reopen` với file thực hiện điều gì?** Đóng file trước checkpoint và thử mở lại ở vị trí trước đó sau restore.
5. **Vì sao `close` có thể gây lỗi sau restore?** Object Java cũ vẫn có thể được code sử dụng dù FD mà nó sở hữu đã đóng.
6. **Policy có xử lý được FD do JNI/native code mở không?** Không. Phải xử lý trong native component hoặc dùng công cụ điều tra syscall.
7. **Có thể dùng `reopen` cho mọi socket không?** Không. Hỗ trợ phụ thuộc runtime; một số bản chỉ hỗ trợ listening socket, còn socket client-server hai đầu không thể reopen theo policy.
8. **Policy có thay thế việc đăng ký `Resource` không?** Không. Resource vẫn là cơ chế chính để ứng dụng quản lý lifecycle; policy là hỗ trợ có giới hạn cho FD khó can thiệp.

## Tài liệu tham khảo

- [CRaC — File descriptor policies](https://crac.org/reference/fd-policies/): cú pháp rule, loại FD và action theo tài liệu dự án CRaC.
- [Azul — File Descriptor Policies](https://docs.azul.com/crac/usage/fd-policies): chi tiết thuộc tính và giới hạn theo các bản Azul Zulu/Zing.
- [CRaC — Debugging failures](https://crac.org/reference/debugging/): chẩn đoán FD còn mở qua Java và native code.
- [Azul — CRaC VM options and system properties](https://docs.azul.com/crac/usage/vm-options): cách truyền `jdk.crac.resource-policies` và các tùy chọn chẩn đoán.

## Kết luận

`jdk.crac.resource-policies` cho phép cấu hình cách CRaC xử lý một số file descriptor còn mở khi checkpoint. File policy gồm các rule có `type` và `action`, phân tách bằng `---`; thứ tự rule quyết định rule đầu tiên khớp sẽ được áp dụng. Các loại FD gồm file, pipe, socket và raw file descriptor; hành động có thể là `error`, `ignore`, `close` hoặc `reopen` tùy loại và phiên bản runtime.

Hãy dùng policy như một giải pháp có kiểm soát cho FD mở qua JDK API mà ứng dụng khó quản lý trực tiếp. Với tài nguyên do ứng dụng sở hữu, vẫn nên dùng CRaC Resource để đóng/mở theo vòng đời. Với native FD, cần xử lý ở tầng native. Luôn kiểm tra đúng phiên bản JDK, log checkpoint, hành vi restore và readiness trước khi đưa policy vào môi trường triển khai.
