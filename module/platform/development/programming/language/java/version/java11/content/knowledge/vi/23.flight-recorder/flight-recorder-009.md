# Java Flight Recorder: Giới hạn chi phí, dữ liệu nhạy cảm và thời gian lưu (Java 11+)

## 1. Mục tiêu bài học

**Java Flight Recorder (JFR)** là bộ ghi nhận sự kiện chẩn đoán của JVM, cung cấp thông tin về CPU, thread, GC, I/O, allocation và những sự kiện do ứng dụng định nghĩa. Từ Java 11, module **`jdk.jfr`** và các công cụ quản trị JVM cho phép thu thập, cấu hình, xuất và đọc dữ liệu JFR bằng các API chuẩn đang còn được sử dụng hiện nay.

Mặc dù JFR thường có chi phí thấp hơn nhiều công cụ profiling liên tục khác, một hệ thống vận hành tốt phải trả lời ba câu hỏi độc lập:

1. **Chi phí:** ghi những sự kiện gì, tần suất bao nhiêu, có thu stack trace không, gây ảnh hưởng thế nào đến CPU/GC/latency và có chiếm hết disk không?
2. **Dữ liệu nhạy cảm:** file `.jfr` có thể chứa tên phương thức, stack trace, đường dẫn, hostname, exception metadata, thông tin cấu hình hoặc dữ liệu ứng dụng tùy event. Ai được phép xem và có cần giảm/mask thông tin ngay khi tạo event không?
3. **Thời gian lưu:** `maxAge`/`maxSize` giới hạn dữ liệu **trong disk repository của recording**, nhưng ai xóa **file dump**, bản sao đã upload và backup ngoài JFR?

**Trọng tâm:** tạo chính sách JFR an toàn và đo được. Không chạy mọi event chi tiết vô hạn; không ghi thông tin khách hàng hoặc credential không cần thiết; không nhầm retention của repository với retention của file xuất.

Bài gồm giải thích hiện hành của API Java 11, ví dụ `jcmd`, ví dụ Java 11 chạy được, output đã kiểm thử, checklist vận hành và bài tập.

## 2. Luồng dữ liệu: từ JVM đến repository và file .jfr

```text
             JVM và custom events
                       |
                  Event payload
            (thời gian, thread, fields,
                 tùy chọn stack)
                       |
                  JFR buffers
                       |
            +----------+----------+
            |                     |
     recording.disk=true    recording.disk=false
            |                     |
       Disk repository         Memory buffers
          (chunks)           (lịch sử hữu hạn)
            |
       maxAge / maxSize
       giới hạn dữ liệu
       còn lưu trong repo
            |
            +------------ dump(Path), JFR.dump
                                     |
                                     v
                             diagnosis.jfr
                                     |
                           +---------+---------+
                           |         |         |
                       tải về     upload     backup
                           |         |         |
                           +---------+---------+
                                     |
                          Retention & access
                          phải quản lý riêng
```

Các tầng thường bị nhầm:

| Tầng | JFR quản lý gì? | Điều JFR **không** tự bảo đảm |
| --- | --- | --- |
| Buffer trong bộ nhớ | Tiếp nhận và xử lý event trước khi xuất | Không bảo đảm giữ đủ mọi event nếu buffer không đáp ứng |
| JFR disk repository | Chứa những chunk của recording khi `disk=true`, có thể áp dụng `maxAge`/`maxSize` | Không phải quota tuyệt đối cho tổng dung lượng mọi file trên máy |
| Dump `.jfr` | Snapshot/ghi dữ liệu còn giữ được ra file | Không tự xóa file dump theo `maxAge` của repository |
| Storage thứ cấp | Tệp đã chuyển cho người phân tích, object storage, ticket, backup | JFR không điều khiển quyền và TTL của tất cả bản sao |

**Kết luận quan trọng:** `recording.setMaxAge(Duration.ofMinutes(30))` không có nghĩa mọi file `.jfr` sẽ tự biến mất sau 30 phút. Nó là chính sách của **dữ liệu repository**, không phải chính sách quản trị dữ liệu toàn hệ thống.

## 3. Chi phí JFR: không áp một con số cho mọi ứng dụng

JFR được thiết kế để thu event với overhead tương đối thấp, nhưng chi phí phụ thuộc workload và settings. Một chương trình phát event custom hàng trăm nghìn lần mỗi giây, thu stack trace hoặc payload lớn có thể gây overhead khác hẳn một ứng dụng chỉ ghi những event mẫu định kỳ.

### 3.1. Các loại chi phí cần đo

| Nguồn | Tác động | Cách giảm |
| --- | --- | --- |
| Tạo event và thu timestamp | CPU, allocation | Hạn số sự kiện và payload không cần thiết |
| Stack traces | CPU, dung lượng, có thể lộ tên hàm | Chỉ bật stack khi thật sự cần |
| Duration event threshold quá thấp | Nhiều sự kiện ngắn được ghi | Đặt threshold theo câu hỏi chẩn đoán |
| Sampling/period dày | CPU/metadata/disk tăng | Nới chu kỳ lấy mẫu khi phù hợp |
| Kết cấu event nhiều trường String | Format/serialize và độ nhạy cảm dữ liệu | Giữ schema tối giản, trường enum/bucket |
| Memory buffers | Sử dụng bộ nhớ và áp lực vận hành | Chọn bộ đệm phù hợp, đo thực tế |
| Disk chunks | Ghi đọc đĩa, tốn dung lượng | `setMaxAge`, `setMaxSize`, giám sát disk |
| File dump/parse/upload | I/O, CPU, network, lưu nhiều bản sao | Giới hạn kích thước, tần suất dump, TTL |
| Thu sự kiện phân tích rất sâu | Có thể tăng pause hoặc load đáng kể tùy event | Bật trong thời gian ngắn, có rollback |

Không có bảo đảm **“JFR luôn dưới X% CPU/latency”** cho mọi JDK và workload. Chọn **ngân sách quan sát** theo SLO của dịch vụ, kiểm thử trước và theo dõi sau khi triển khai.

### 3.2. `default` và `profile` phục vụ mục đích khác nhau

JFR thường cung cấp hai cấu hình có sẵn:

- **`default`:** phù hợp làm điểm bắt đầu cho ghi nhẹ hoặc ghi liên tục, nhưng vẫn phải kiểm tra danh mục sự kiện và đo overhead trên dịch vụ của mình.
- **`profile`:** thu dữ liệu chi tiết hơn phục vụ điều tra performance; có thể tăng chi phí CPU/I/O và lộ nhiều metadata hơn, nên ưu tiên thời gian ghi có giới hạn và giám sát.

Có thể dùng `Configuration.getConfiguration("default")` trong API Java hoặc `settings=default` với `jcmd`. Không tự động dùng `profile` 24/7 chỉ vì thu nhiều thông tin hơn.

### 3.3. Chỉ bật event cần trả lời câu hỏi

Ví dụ một đoạn cấu hình Java:

```java
recording.enable("jdk.CPULoad")
         .withPeriod(Duration.ofSeconds(1));

recording.enable("jdk.FileWrite")
         .withThreshold(Duration.ofMillis(20))
         .withoutStackTrace();
```

Đây là **mảnh mã minh họa bên trong phương thức**, giả định có `Recording recording` và import `java.time.Duration`. `withPeriod` phù hợp với sự kiện periodic, còn `withThreshold` áp dụng cho loại event duration hỗ trợ threshold. Không phải mọi event chấp nhận mọi setting với cùng ý nghĩa.

Nếu đang điều tra blocking, ngưỡng ghi của một event monitor có thể giúp giảm nhiễu: 20ms khác rất xa 1ms khi số lượng tương tác lớn. Việc thay đổi threshold phải đo lượng event/s, CPU và dung lượng file.

### 3.4. `shouldCommit()` tránh xây payload không dùng đến

Một custom JFR event có thể có payload đắt như JSON, chuỗi stack, query, mapping phức tạp. Đừng thực hiện formatting tốn kém rồi mới phát hiện event không được ghi.

```java
SafeWork event = new SafeWork();
event.begin();
doWork();
event.end();

if (event.shouldCommit()) {
    event.operationGroup = "catalog-read";
    event.latencyBucket = "10-50ms";
    event.outcome = "OK";
    event.commit();
}
```

Đoạn trên là **mảnh mã minh họa**, cần định nghĩa `SafeWork` và `doWork()` trong ứng dụng. Nó cho thấy nên tạo payload không nhạy cảm và đắt chi phí **sau** `shouldCommit()`, nếu có thể. Nhưng việc cấp phát event, gọi begin/end và làm việc thật vẫn tiêu tốn tài nguyên; `shouldCommit()` **không triệt tiêu toàn bộ overhead**. Có thể dùng `isEnabled()` để tránh công việc chuẩn bị sớm khi event bị tắt.

## 4. Cách đo overhead có cơ sở

So sánh cùng ứng dụng trên workload gần production, đủ warm-up và nhiều lượt đo:

1. **Baseline:** không có recording trong pha đo, hoặc cấu hình đối chứng được xác định rõ.
2. **Light JFR:** `default` + event quan trọng và giới hạn repository.
3. **Detail JFR:** `profile` hoặc event bổ sung trong cửa sổ đo ngắn.

Chỉ số phải quan sát:

- **CPU:** process CPU time và utilization trong cùng throughput.
- **Latency:** p50, p95, p99, đặc biệt tail latency.
- **Throughput:** request/s, batch jobs/s hoặc số tác vụ hoàn tất.
- **GC/allocation:** pause, số GC, allocation rate, memory.
- **I/O:** disk writes/s, IOPS, thời gian ghi/đọc dump.
- **JFR event rate:** event/s, byte/phút, tốc độ tăng repository, file sizes.
- **Độ ổn định:** timeout/error rate, back-pressure và tình trạng full disk.

Công thức chỉ để trình bày mức chênh:

```text
relative_change_% = 100 * (observed_with_jfr - observed_baseline) / observed_baseline
```

Với p99 latency và CPU, tăng thường là dấu hiệu cần đánh giá. Với throughput, giảm có thể là tác động xấu. **Không lấy một benchmark micro không có warm-up để kết luận JFR an toàn cho production.**

Quy trình kiểm tra hợp lý: so sánh cùng tải, nhiều lượt, cùng resources, cùng version JDK, tách giai đoạn startup và steady state; kiểm tra cả thời điểm `dump` vì dump cũng có thể tạo I/O burst.

## 5. Dữ liệu nhạy cảm trong JFR đến từ đâu?

Sự kiện JFR có thể chứa tên class, package, method, thread, thời điểm, stack trace, duration, byte count, tên file, network endpoint, exception metadata, JVM arguments/system properties tùy event type và template. Với event tùy chỉnh, ứng dụng có thể ghi thêm bất kỳ trường nào JFR hỗ trợ.

**Không mặc định JFR tự ẩn thông tin người dùng hoặc bí mật**. Ngay cả khi không lưu raw request body, metadata cũng có thể tiết lộ:
- Đường dẫn có username, tenant hoặc tên dự án.
- Host/IP nội bộ, endpoint dịch vụ, topology.
- Exception message chứa URL/query/customer identifier.
- Thread names có request/customer ID.
- Custom event fields như email, session ID, access token, cookie, số điện thoại.
- Tên package/method thể hiện thông tin nghiệp vụ không muốn chia sẻ rộng rãi.

### 5.1. Data minimization phải bắt đầu từ schema

| Trường thường an toàn hơn khi phù hợp | Trường nên tránh ghi raw |
| --- | --- |
| Nhóm thao tác được phép: `catalog-read`, `search` | Header `Authorization`, cookie, API key |
| Kết quả `OK`/`ERROR` | Password, refresh token, session token |
| Latency bucket `10-50ms` | Request/response body, thông tin đăng nhập |
| Error code từ danh mục an toàn | `Throwable.getMessage()` nguyên văn |
| Số lượng kết quả, kích thước dữ liệu đã tổng hợp | Email, số điện thoại, địa chỉ, số định danh |
| Component name đã duyệt | URL đầy đủ có query nhạy cảm |
| ID quan sát ngẫu nhiên, ngắn hạn có chính sách riêng | Customer ID/tenant ID lưu lâu không cần thiết |

Hãy ưu tiên **không thu** dữ liệu có rủi ro thay vì thu tất cả rồi cố redact sau. Một số dữ liệu tưởng không nhạy cảm vẫn có thể được kết hợp với nguồn khác để xác định người dùng.

Đặc biệt, **hash không salt** của email/ID không tự bảo đảm ẩn danh vì có thể bị dictionary attack. Khi cần correlation theo cá nhân hoặc tenant, hãy đánh giá chính sách pseudonymization, vòng đời khóa, TTL và quyền truy cập phù hợp, thay vì tự động coi mọi chuỗi hash là an toàn.

### 5.2. Stack trace là một thành phần, không phải toàn bộ privacy

`recording.enable(MyEvent.class).withoutStackTrace()` hoặc `@StackTrace(false)` **chỉ điều chỉnh stack trace của event tương ứng**. Nó không:
- Xóa những trường String của event.
- Tắt stack trace cho toàn bộ built-in JVM events.
- Thay đổi quyền của file `.jfr`.
- Mã hóa metadata hoặc xóa bản sao.
- Bảo đảm không có dữ liệu nhạy cảm ở những event khác trong cùng recording.

Nếu cần thu stack để điều tra, hãy giới hạn thời gian và người xem; nếu không cần, tắt cho những event có tần suất cao để giảm overhead và exposure.

### 5.3. Tránh ghi exception nguyên văn

**Không nên:**

```java
// Phản ví dụ — không thêm những field này vào JFR event:
// event.requestBody = rawBody;
// event.accessToken = bearerToken;
// event.errorText = exception.toString();
```

**Nên dùng metadata được phân loại:**

```java
event.operationGroup = "catalog-read";
event.outcome = "ERROR";
event.latencyBucket = "50-100ms";
```

Đây là các mảnh mã minh họa, giả định đã định nghĩa event schema phù hợp. Nếu cần giải thích lỗi, dùng code/category từ danh mục đã xem xét. Chỉ cho phép thông điệp exception được lưu khi đã đánh giá khả năng chứa PII, credential hoặc dữ liệu doanh nghiệp.

## 6. Giới hạn thời gian lưu và dung lượng repository

`jdk.jfr.Recording` trong Java 11 có những API:

```java
recording.setToDisk(true);
recording.setMaxAge(Duration.ofMinutes(30));
recording.setMaxSize(128L * 1024 * 1024);
```

Đây là mảnh mã minh họa trong phương thức, giả định `recording` còn hoạt động và đã import `Duration`. Mỗi cài đặt phục vụ một giới hạn khác nhau.

### 6.1. `setToDisk(true)` và `setToDisk(false)`

- **`true`:** JFR có thể ghi các chunk vào **disk repository**; có thể giữ một cửa sổ lịch sử để dump khi xảy ra sự cố.
- **`false`:** dữ liệu bị giới hạn trong **memory buffers**, không liên tục ghi dữ liệu của recording xuống repository. Lịch sử có thể ngắn và dữ liệu cũ có thể bị ghi đè.

**Không hiểu `disk=false` là “JFR sẽ không bao giờ tạo file”**. Các thao tác dump khác và các công cụ quản trị có thể tạo hiện vật độc lập. `maxAge`/`maxSize` nói về disk repository và không thay thế chính sách memory buffer khi không dùng disk.

### 6.2. `setMaxAge(Duration)`

`setMaxAge(Duration.ofMinutes(30))` giới hạn độ tuổi dữ liệu còn được recording giữ **trong disk repository**; JFR loại dữ liệu cũ theo cơ chế quản lý chunk.

- `getMaxAge()` trả cấu hình đang sử dụng.
- `setMaxAge(null)` có nghĩa không đặt giới hạn tuổi ở cấp recording.
- Không mặc định chunk bị xóa đúng đến từng mili giây, hoặc mọi byte cũ biến mất khỏi ổ đĩa vật lý ngay lập tức.
- Nếu sự cố được phát hiện sau khi dữ liệu bị loại, có thể không còn đủ thông tin để dump.

Giới hạn tuổi của repository **không áp dụng cho file dump đã copy ra đường dẫn khác**.

### 6.3. `setMaxSize(long)`

`setMaxSize(128L * 1024 * 1024)` đặt mức dung lượng dữ liệu recording trong repository tính bằng **byte**, không phải số event.

- `getMaxSize()` trả số byte cấu hình.
- `setMaxSize(0)` nghĩa **không giới hạn** dung lượng bằng tham số này.
- `setMaxSize(-1)` không hợp lệ và ném `IllegalArgumentException`.
- Khi vượt ngưỡng, JVM loại những **chunk cũ** để nhường chỗ cho dữ liệu mới.
- Vì quản lý theo chunk, không nên coi `maxSize` là **hard quota tức thời** của toàn ổ đĩa; nhiều recording, dump, log, core/heap dumps vẫn làm disk đầy.
- Với CLI/JVM options, `maxsize` phải phù hợp kích thước chunk tối đa được cấu hình (`maxchunksize`).

Khi cả `maxAge` lẫn `maxSize` không đặt giới hạn hữu hạn, repository có thể tiếp tục tăng theo thời gian. Nên đặt cả **giới hạn tuổi** và **giới hạn dung lượng** cho ghi dài hạn, cùng cảnh báo filesystem/quota ở mức OS.

### 6.4. `setDuration(Duration)` không phải `setMaxAge(Duration)`

```java
recording.setDuration(Duration.ofMinutes(5));
```

**`duration`** trả lời “recording chạy trong bao lâu?”. **`maxAge`** trả lời “giữ bao xa về quá khứ trong repository?”. **`maxSize`** trả lời “giữ bao nhiêu byte dữ liệu repository?”. Chúng không thể thay thế nhau.

Ví dụ:
- Ghi 5 phút rồi tự dừng: `duration=5m`.
- Ghi liên tục nhưng giữ khoảng 30 phút dữ liệu gần đây: `maxAge=30m`.
- Giới hạn kích thước data repository: `maxSize=128m`.

Khi dump file ra ngoài, file `.jfr` vẫn có thể tồn tại nhiều ngày dù `duration=5m` hoặc `maxAge=30m`.

### 6.5. `setDumpOnExit(false)` không phải một chính sách chống dump

`setDumpOnExit(false)` tránh tự động dump khi JVM thoát **cho recording được cấu hình**. Nó không ngăn người có quyền gọi `recording.dump(path)` hoặc `jcmd JFR.dump` trong lúc JVM đang chạy; cũng không thu hồi file đã tạo trước đó.

Trong môi trường phải hạn chế dữ liệu, cần quản trị ai được phép dùng diagnostic interface và theo dõi file xuất, thay vì chỉ đổi một boolean.

## 7. Vòng đời Recording và vòng đời file

| API | Ý nghĩa | Lưu ý retention |
| --- | --- | --- |
| `new Recording(Configuration...)` | Tạo recording với preset JFR | Chưa bắt đầu ghi cho recording này |
| `enable/disable` | Chọn event types và settings | Bật event nhiều/chi tiết làm tăng cost/privacy |
| `start()` | Bắt đầu thu dữ liệu | Tốt nhất cấu hình trước `start()` |
| `stop()` | Dừng ghi recording | Không đồng nghĩa xóa mọi file |
| `dump(Path)` | Ghi dữ liệu còn lưu vào file `.jfr` | File đầu ra phải có quyền/TTL riêng |
| `setDestination(Path)` | Chọn nơi dump khi recording stop | Có thể tự close recording khi xuất thành công theo API |
| `setDumpOnExit(boolean)` | Chính sách dump khi JVM thoát | Không cấm dump thủ công hoặc bởi công cụ khác |
| `close()` | Giải phóng tài nguyên/data gắn recording | Không xóa toàn bộ file/copies ngoài repository |

**Phải tách ba trạng thái:**

```text
Recording RUNNING
       |
       v
Recording STOPPED
       |
       +---- dump(path) ----> file .jfr độc lập
       |
       v
Recording CLOSED             file .jfr vẫn tồn tại
                                   |
                              TTL/cleanup riêng
```

`Recording.dump(Path)` cũng có thể dùng khi recording **đã bắt đầu nhưng vẫn đang chạy**; không bắt buộc `stop()` trước khi dump. Cần tính chi phí dump và file size, tránh tạo file quá lớn hoặc dump tần suất cao.

**`close()` không có nghĩa xóa an toàn tất cả bản sao.** Nếu file đã upload lên object storage hoặc đính kèm vào ticket, Java Recording API không có quyền quản lý những nơi lưu đó.

## 8. Dùng jcmd để ghi có giới hạn trên JVM đang chạy

Trước tiên phải có quyền vận hành với tiến trình Java tương ứng:

```bash
jcmd -l
jcmd <PID> help JFR.start
jcmd <PID> help JFR.dump
```

`<PID>` chỉ là placeholder; cần thay PID thực của ứng dụng. `jcmd` chạy trong môi trường có quyền phù hợp, thường cùng host/user theo cơ chế attach của JVM.

### 8.1. Ghi liên tục nhẹ, giữ cửa sổ gần đây

```bash
jcmd <PID> JFR.start name=ops-window settings=default disk=true maxage=30m maxsize=128m dumponexit=false
```

Ý nghĩa:
- `name` cho phép chọn recording khi check/dump/stop.
- `settings=default` là cấu hình phổ biến cho ghi nhẹ hơn, cần đo trên workload thật.
- `disk=true` dùng disk repository.
- `maxage=30m` chỉ giữ cửa sổ lịch sử phù hợp trong repository.
- `maxsize=128m` giới hạn dữ liệu repository theo kích thước/chunk.
- `dumponexit=false` tránh dump tự động của recording này lúc JVM exit.

Nếu dự định ghi liên tục, không cần `duration`. Với mỗi JVM/JDK, dùng `jcmd <PID> help JFR.start` để xác minh cú pháp và những giới hạn option đúng phiên bản. Không cố dùng giá trị `maxsize` nhỏ hơn yêu cầu chunk size.

### 8.2. Kiểm tra, dump, dừng

```bash
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=ops-window filename=/secure/jfr/ops-window.jfr
jcmd <PID> JFR.stop name=ops-window
```

`/secure/jfr` là **đường dẫn ví dụ trên Unix**. Với Windows cần dùng đường dẫn/quoting phù hợp và một thư mục có quyền truy cập hạn chế.

**Sau khi `JFR.dump` tạo file**, nội dung đó **không tự bị xóa** khi recording mất dữ liệu cũ do `maxage`, khi `JFR.stop`, hoặc khi JVM thoát. Trước khi upload, xem file như một hiện vật có phân loại dữ liệu và TTL.

### 8.3. Ghi `profile` ngắn hạn

```bash
jcmd <PID> JFR.start name=incident-profile settings=profile disk=true duration=5m maxsize=128m dumponexit=false
```

Đây là ví dụ profiling 5 phút để điều tra một sự cố cụ thể. Trước và trong thời gian ghi phải đo CPU, p95/p99 latency, disk I/O, JFR event rate. Khi xong phải dừng/giao file đúng nhóm và dọn theo retention.

Đừng để việc “ghi cho chắc” trở thành một tiến trình lưu dữ liệu nhạy cảm vô hạn.

## 9. Chương trình Java 11 đầy đủ: event tối giản, giới hạn repository, dump và đọc lại

Ví dụ tự chứa sau đây dùng **`jdk.jfr`** và **`jdk.jfr.consumer.RecordingFile`**, không kết nối Internet. Nó:

1. Tạo recording từ `Configuration.getConfiguration("default")`.
2. Đặt `disk=true`, `maxAge=5 phút`, `maxSize=32 MiB`, `duration=1 phút` và `dumponexit=false`.
3. Định nghĩa custom event chỉ với ba trường đã được duyệt: `operationGroup`, `latencyBucket`, `outcome`.
4. Tắt stack trace **riêng custom event** và dùng threshold 1 ms.
5. Phát ba event duration có thời gian thử nghiệm đủ vượt ngưỡng.
6. Stop, dump ra file, đọc lại các event qua streaming API, kiểm tra schema và giá trị.
7. In thông số và xóa file `.jfr` minh họa.

**Cảnh báo quan trọng:** chương trình kiểm tra schema của **custom event** và các trường đã ghi, không thực hiện kiểm toán bảo mật cho **mọi built-in event** trong file. Vì dùng cấu hình `default`, file vẫn có thể chứa những event JVM khác. `sensitiveFieldPresent=false` **không chứng minh toàn bộ file JFR không chứa dữ liệu nhạy cảm**.

### 9.1. Tệp JfrRetentionPrivacyDemo.java

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.HashSet;
import java.util.Set;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrRetentionPrivacyDemo {
    @Name("lesson.SafeWork")
    @Label("Safe work summary")
    @Category({"Application", "Operations"})
    @StackTrace(false)
    public static class SafeWork extends Event {
        @Label("Operation group")
        public String operationGroup;

        @Label("Latency bucket")
        public String latencyBucket;

        @Label("Outcome")
        public String outcome;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected trusted .jfr output path");
        }
        Path output = Path.of(args[0]);
        int recorded = 0;
        boolean sensitiveFieldPresent = false;

        try (Recording recording =
                new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("bounded-safe-demo");
            recording.setToDisk(true);
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setMaxSize(32L * 1024 * 1024);
            recording.setDuration(Duration.ofMinutes(1));
            recording.setDumpOnExit(false);
            recording.enable(SafeWork.class)
                    .withThreshold(Duration.ofMillis(1))
                    .withoutStackTrace();

            System.out.println("toDisk=" + recording.isToDisk());
            System.out.println("maxAgeMinutes=" + recording.getMaxAge().toMinutes());
            System.out.println("maxSizeMiB=" + recording.getMaxSize() / (1024 * 1024));
            System.out.println("dumpOnExit=" + recording.getDumpOnExit());

            recording.start();
            for (int i = 0; i < 3; i++) {
                SafeWork event = new SafeWork();
                event.begin();
                Thread.sleep(12);
                event.end();
                if (event.shouldCommit()) {
                    event.operationGroup = "catalog-read";
                    event.latencyBucket = "10-50ms";
                    event.outcome = "OK";
                    event.commit();
                }
            }
            recording.stop();
            recording.dump(output);
        }

        try (RecordingFile rf = new RecordingFile(output)) {
            while (rf.hasMoreEvents()) {
                RecordedEvent event = rf.readEvent();
                if (!event.getEventType().getName().equals("lesson.SafeWork")) {
                    continue;
                }
                recorded++;
                Set<String> names = new HashSet<>();
                event.getEventType().getFields()
                        .forEach(f -> names.add(f.getName()));

                if (names.contains("password") || names.contains("accessToken")
                        || names.contains("customerId")
                        || names.contains("requestBody")) {
                    sensitiveFieldPresent = true;
                }

                if (!"catalog-read".equals(event.getString("operationGroup"))
                        || !"10-50ms".equals(event.getString("latencyBucket"))
                        || !"OK".equals(event.getString("outcome"))) {
                    throw new AssertionError("Unexpected event payload");
                }
            }
        }

        System.out.println("safeEvents=" + recorded);
        System.out.println("sensitiveFieldPresent=" + sensitiveFieldPresent);
        System.out.println("dumpCreated=" + (Files.size(output) > 0));

        Files.delete(output);
        System.out.println("demoDumpDeleted=" + !Files.exists(output));

        if (recorded != 3 || sensitiveFieldPresent) {
            throw new AssertionError("Missing or sensitive demo events");
        }
    }
}
```

### 9.2. Lệnh chạy

Chạy **trong thư mục test riêng** với file đích mới, không dùng đường dẫn file quan trọng vì ví dụ xóa `demo.jfr` sau khi xác minh:

```bash
javac -encoding UTF-8 --release 11 JfrRetentionPrivacyDemo.java
java JfrRetentionPrivacyDemo demo.jfr
```

**Đầu ra được kiểm chứng thực tế trên JDK 24 khi biên dịch bằng `--release 11`:**

```text
toDisk=true
maxAgeMinutes=5
maxSizeMiB=32
dumpOnExit=false
safeEvents=3
sensitiveFieldPresent=false
dumpCreated=true
demoDumpDeleted=true
```

### 9.3. Phân tích kết quả

- `toDisk=true`: recording được cấu hình sử dụng disk repository.
- `maxAgeMinutes=5` và `maxSizeMiB=32`: JFR đã nhận các giá trị cấu hình; test ngắn **không chứng minh** việc loại các chunk cũ khi thật sự chạm giới hạn.
- `dumpOnExit=false`: recording không bật tính năng dump tự động khi JVM thoát; program vẫn gọi `dump(output)` có chủ đích.
- `safeEvents=3`: ba event `lesson.SafeWork` có payload phù hợp đã được ghi và đọc lại. Các event JVM khác không được đếm.
- `sensitiveFieldPresent=false`: bốn tên trường `password`, `accessToken`, `customerId`, `requestBody` không xuất hiện trong schema custom event mà chương trình kiểm tra. Nó **không phải kết luận an toàn cho toàn file**.
- `dumpCreated=true`: file đích có dữ liệu.
- `demoDumpDeleted=true`: code xóa file dump thử nghiệm. `Files.delete` không đồng nghĩa secure erase trên disk vật lý, và không xóa các bản sao/backups khác.

Ở production, đường dẫn cần được cấp từ cấu hình tin cậy và kiểm tra ownership, file existence, ACL và chính sách cleanup. Ví dụ được thiết kế cho **một file tạm mới**, không cho nhập đường dẫn tùy ý rồi xóa.

### 9.4. Vì sao đọc event theo luồng?

`RecordingFile.readAllEvents(path)` có thể tiện với một file nhỏ nhưng lưu danh sách event trong bộ nhớ. Với file lớn, ưu tiên:

```java
try (RecordingFile rf = new RecordingFile(path)) {
    while (rf.hasMoreEvents()) {
        RecordedEvent event = rf.readEvent();
        // Chỉ phân loại/đếm và giữ trường đã được cho phép.
    }
}
```

Đây là mảnh mã minh họa cần có `Path path` và import `RecordingFile`, `RecordedEvent`. Tài liệu Java 11 khuyến nghị chỉ đọc **recording từ nguồn tin cậy**. Không đưa file không rõ nguồn gốc vào hệ thống parser production mà thiếu giới hạn size và quy trình kiểm tra.

## 10. Giữ dữ liệu ngoài repository: TTL và bản sao

Ngay khi file được dump, nơi lưu trữ bên ngoài phải có **chính sách riêng**:

| Nơi chứa | Việc phải thiết lập |
| --- | --- |
| JFR repository | `maxAge`, `maxSize`, monitor, quota disk |
| Dump directory cục bộ | Hạn thời gian lưu, giới hạn số lượng/dung lượng, ACL, cleanup có audit |
| Máy laptop phân tích | Chính sách lưu tạm, mã hóa, xóa khi xong, không đồng bộ cloud không kiểm soát |
| Ticket/incident system | Quyền truy cập tối thiểu, hạn giữ attachment, log truy cập |
| Object storage | Private bucket, encryption-at-rest, lifecycle/TTL, kiểm soát versioning |
| Backup/snapshot | Backup retention và xử lý xóa khi dữ liệu hết hạn |
| Nhóm bên ngoài | Thỏa thuận mục đích, phạm vi được gửi, hạn dùng và quy trình dọn dữ liệu |

**Không xóa hàng loạt tất cả file `*.jfr` trên máy không rõ sở hữu**. Một tiến trình cleanup tốt cần thư mục riêng, metadata về người tạo/incident, TTL rõ và xử lý ngoại lệ có thẩm quyền.

### 10.1. Retention không phải secure deletion

Việc JFR loại chunk cũ, hoặc gọi `Files.delete(path)`, không chứng minh mọi dữ liệu đã bị xóa khỏi SSD, filesystem snapshot, backup hoặc bên nhận. Nếu có yêu cầu xóa dữ liệu theo quy định/tổ chức, phải áp dụng giải pháp retention và tiêu hủy **ở tầng lưu trữ thực tế**, có log xác nhận và quy trình xử lý backup.

### 10.2. Điều gì xảy ra khi dữ liệu quá cũ?

Nếu recording liên tục giữ dữ liệu gần nhất 30 phút và lỗi chỉ được phát hiện sau nhiều giờ, dữ liệu trước đó có thể đã bị loại khỏi repository. Vì vậy phải đánh đổi **chiều sâu lịch sử** và **chi phí tài nguyên/dữ liệu nhạy cảm**. Có thể giảm sự kiện, giữ cửa sổ dài hơn theo budget, hoặc dùng nguồn telemetry đã được tổng hợp để hỗ trợ phát hiện sớm; không đơn giản đặt `maxsize=0` vô hạn.

### 10.3. Disk đầy mặc dù maxSize đã được đặt?

Nguyên nhân có thể là:
- Nhiều recordings dùng chung JVM hoặc repository.
- Chunk granularity và cách quản lý repo.
- File dump độc lập được tạo nhiều lần.
- Heap dumps, logs, backups hoặc các file khác trên cùng volume.
- Không có quota/alert ở cấp OS.

Hãy đo **tổng dung lượng thực** theo directory và filesystem, không chỉ đọc `recording.getMaxSize()` rồi kết luận disk an toàn.

## 11. Quyền truy cập và chia sẻ file JFR

JFR là công cụ chẩn đoán mạnh nên có rủi ro lộ dữ liệu nếu quyền quá rộng. Những kiểm soát còn phù hợp:

- Chỉ cho tài khoản/vai trò được phép truy cập `jcmd`, JFR API, management endpoints hoặc remote tools của tiến trình.
- Hạn quyền đọc thư mục repository và thư mục dump. Không đặt `.jfr` ở public webroot hoặc bucket public.
- Áp dụng **encryption at rest** cho volume/storage và truyền file bằng kênh được bảo vệ; định dạng `.jfr` tự nó **không phải cơ chế mã hóa bảo mật**.
- Chỉ lưu ở nơi đã được phê duyệt; không upload lên ticket/chat công khai.
- Không dùng tên file mang email, customer ID, token hoặc query nhạy cảm.
- Ghi nhận ai bắt đầu recording, ai dump, ai tải/xem và ai xóa file.
- Đặt thời hạn xóa rõ, xử lý riêng bản copy, object versions và backup.
- Không để người dùng cuối tự điều khiển toàn bộ tham số JFR hoặc đường dẫn dump của backend.

**Chỉ giảm retention không sửa được một rò rỉ đã xảy ra.** Nếu phát hiện credential trong recording đã được chia sẻ, phải xác định và hạn chế các bản sao, xử lý dữ liệu theo quy trình incident và có thể rotate/revoke secrets tương ứng.

## 12. Các kịch bản triển khai thực tế

### 12.1. Dịch vụ 24/7 muốn điều tra 30 phút gần nhất

Cấu hình khởi điểm:
- `settings=default` và chỉ các built-in/custom events thực sự cần.
- `disk=true`, `maxage=30m`, `maxsize=128m` hoặc giá trị từ benchmark.
- Dump chỉ khi có sự cố/nhận diện bất thường, vào thư mục hạn chế.
- Giới hạn số file và TTL từng file sau dump, có owner và audit.
- CPU, p99 latency, disk I/O, disk free space, event rate có alert.

Nếu throughput rất lớn, cửa sổ 30 phút có thể cần dung lượng cao hơn hoặc giảm mật độ event. Cần ưu tiên dữ liệu đủ giá trị chẩn đoán thay vì lưu toàn bộ.

### 12.2. Phân tích allocation/lock contention trong 5 phút

- Chỉ bật `profile`/event chi tiết trong **thời gian có kiểm soát**, không chạy vô thời hạn.
- Hạ threshold của event cần thiết sau khi xem tác động.
- Ghi lại baseline p95/p99 và throughput; rollback nếu vượt budget.
- Dump file vào vị trí an toàn; chỉ gửi đúng nhóm.
- Sau điều tra, dừng chế độ chi tiết và dọn các file theo policy.

### 12.3. Phát hiện custom event chứa dữ liệu khách hàng

- Dừng event có rủi ro và sửa schema **không phát** dữ liệu nhạy cảm.
- Rà soát các recordings và file dump đã tồn tại, cả bản copy ngoài hệ thống.
- Hạn quyền tải/xem, báo đội an toàn dữ liệu theo quy trình.
- Nếu có credential, thực hiện đánh giá thu hồi/rotate.
- Thêm kiểm thử/đánh giá schema để ngăn hồi quy.

Không coi `withoutStackTrace()` hay rút `maxAge` xuống 5 phút là biện pháp đầy đủ nếu payload đã ghi raw token.

## 13. Lỗi hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “JFR luôn có overhead bằng 0.” | Vẫn phải tạo event, buffer, xử lý và ghi. | Đo CPU, p95/p99, throughput, GC, I/O. |
| “Bật profile liên tục cho nhiều dữ liệu hơn.” | Có thể tăng load và dữ liệu nhạy cảm. | Chỉ profile trong cửa sổ cần điều tra. |
| “Threshold càng nhỏ càng tốt.” | Có thể sinh số lượng event lớn. | Dựa trên nhu cầu và load test. |
| “Tắt stack trace nghĩa là không có PII.” | Payload/host/path/event khác vẫn chứa thông tin. | Kiểm toán event schema và file. |
| “Đã hash ID thì luôn ẩn danh.” | Có thể đoán/ngược/liên kết từ từ điển. | Không lưu ID nếu không cần, quản trị pseudonymization. |
| “`maxAge` tự xóa file dump.” | Nó là retention repository. | TTL/cleanup cho mỗi nơi xuất file. |
| “`maxSize` là quota tuyệt đối toàn máy.” | Chunk, nhiều recordings, file dump/log ngoài JFR. | Quota/monitor filesystem. |
| “`duration` và `maxAge` giống nhau.” | Một bên thời gian chạy, bên kia chiều sâu lịch sử. | Đặt cả hai theo mục đích. |
| “`disk=false` sẽ không xuất hiện `.jfr`.” | Vẫn có cơ chế dump/copy. | Kiểm soát quyền, file đích và retention. |
| “`dumponexit=false` cấm mọi người dump.” | Nó chỉ tắt dump-on-exit của recording này. | Phân quyền các công cụ chẩn đoán. |
| “`stop()`/`close()` xóa mọi file đã export.” | API không quản lý tất cả bản sao. | Theo dõi/xóa artifact từng nơi. |
| “Demo `sensitiveFieldPresent=false` chứng minh toàn file không có secrets.” | Nó chỉ kiểm tra tên trường custom event đã định. | Audit tất cả event types/value theo policy. |
| “File JFR ai gửi cũng đọc an toàn.” | File có thể không tin cậy/khổng lồ. | Chỉ parse nguồn tin cậy, có giới hạn. |
| “`readAllEvents` luôn tốt hơn.” | Có thể gây memory spike với file lớn. | Đọc theo luồng bằng `RecordingFile`. |
| “Hết hạn retention nghĩa là secure erase.” | Snapshot/backup có thể vẫn tồn tại. | Policy ở tầng storage và xác nhận cleanup. |

## 14. Checklist trước, trong và sau khi thu thập

**Trước khi bắt đầu**
- [ ] Có mục đích chẩn đoán, owner và khung thời gian.
- [ ] Chọn `default`/`profile`, event types, period và threshold hợp lý.
- [ ] Review trường custom events và metadata có thể nhạy cảm.
- [ ] Không ghi token/password/request body/email/ID không cần thiết.
- [ ] Chọn `disk`, `maxAge`, `maxSize`, `duration` theo budget.
- [ ] Repository và dump directory có ACL, encryption, quota/alert.
- [ ] Có TTL, owner, xử lý backup và quy trình dọn file ngoài JFR.
- [ ] Đã xác định cách đo p95/p99, CPU, GC và I/O so với baseline.

**Khi đang ghi**
- [ ] Theo dõi event rate, disk growth, latency và CPU.
- [ ] Không tùy ý mở thêm mọi event có stack trace.
- [ ] Kiểm tra `JFR.check` hoặc API recording state.
- [ ] Hạn quyền dump và phân loại nơi lưu file.
- [ ] Có kế hoạch dừng nếu overhead vượt ngưỡng.

**Sau khi phân tích**
- [ ] Tắt/chuyển về cấu hình phù hợp.
- [ ] Chỉ chia sẻ file cho người có quyền cần thiết.
- [ ] Xóa local dump, bản sao và version ngoài hệ thống theo retention.
- [ ] Lưu audit về tác vụ dump và cleanup.
- [ ] Rút kinh nghiệm về cost, schema và chất lượng dữ liệu.

## 15. Bài tập tự kiểm tra và đáp án

**Câu 1.** `setMaxAge(Duration.ofMinutes(30))` có tự xóa file `incident.jfr` đã upload lên cloud không?

**Đáp án:** Không. Đây là giới hạn **dữ liệu trong disk repository** của recording. Object storage cần lifecycle/TTL riêng.

**Câu 2.** `setMaxSize(0)` có nghĩa không thu event?

**Đáp án:** Không. `0` nghĩa không đặt giới hạn dung lượng data repository ở mức option này.

**Câu 3.** `duration=5m` khác `maxAge=5m` thế nào?

**Đáp án:** Duration giới hạn **thời gian ghi**; maxAge giới hạn **cửa sổ dữ liệu giữ trong repository**.

**Câu 4.** Vì sao một file JFR có thể nhạy cảm dù không có trường `password`?

**Đáp án:** Có thể chứa path, host, stack trace, exception messages, thread names và những dữ liệu khác đủ để nhận diện hệ thống hoặc người dùng.

**Câu 5.** `@StackTrace(false)` có loại bỏ mọi thông tin nhạy cảm không?

**Đáp án:** Không. Nó chỉ điều chỉnh stack trace của event được gắn annotation.

**Câu 6.** Vì sao `shouldCommit()` hữu ích?

**Đáp án:** Cho phép tránh tính payload đắt nếu event không được ghi, nhưng không xóa toàn bộ overhead tạo event hoặc công việc ứng dụng.

**Câu 7.** Có nên dùng `profile` vô hạn để bắt mọi lỗi bất thường?

**Đáp án:** Không nên mặc định. Phải xem cost/privacy, đặt thời gian ghi hữu hạn, kiểm tra SLO và lựa chọn event thật sự cần.

**Câu 8.** Vì sao một giới hạn 128 MiB không bảo đảm tổng disk dùng bởi JFR nhỏ hơn chính xác 128 MiB?

**Đáp án:** Vì có chunk granularity, nhiều recordings, disk repository, file dump và tài nguyên khác; cần monitor/quota cấp filesystem.

**Câu 9.** Sau `recording.close()`, file `demo.jfr` mà `recording.dump` đã tạo có bị xóa không?

**Đáp án:** Không tự động. Code ví dụ gọi `Files.delete` riêng.

**Câu 10.** Khi `disk=false` thì còn lưu được đủ 24 giờ dữ liệu không?

**Đáp án:** Không có bảo đảm; lịch sử bị giới hạn bởi memory buffers. Phải chọn chế độ phù hợp với yêu cầu điều tra.

**Câu 11.** Tại sao demo in `sensitiveFieldPresent=false` không chứng minh toàn bộ recording đã sạch?

**Đáp án:** Vì phép kiểm tra chỉ xem một số **tên trường custom event**, không rà toàn bộ built-in event và giá trị metadata khác.

**Câu 12.** Các chỉ số nào cần đo để xác định overhead?

**Đáp án:** CPU, p95/p99 latency, throughput, allocation/GC, I/O, event rate và disk usage trên workload tương đương.

**Câu 13.** Nên xử lý thế nào nếu dump chứa access token?

**Đáp án:** Hạn chế quyền và bản sao, xử lý theo quy trình bảo mật, xem xét rotate/revoke token và sửa event schema để không thu token.

**Câu 14.** `RecordingFile.readAllEvents` có phù hợp file rất lớn?

**Đáp án:** Không nên dùng mặc định vì giữ tất cả event trong memory; đọc bằng `hasMoreEvents()/readEvent()` theo luồng.

**Câu 15.** Cách nào tốt hơn: lưu raw user ID rồi hash sau hay chỉ lưu operation group không định danh?

**Đáp án:** Khi không cần identity, chỉ lưu operation group không định danh. Giảm dữ liệu ngay từ nguồn thường giảm rủi ro nhiều nhất.

**Câu 16.** `dumponexit=false` có bảo đảm không ai có thể xuất file JFR?

**Đáp án:** Không. Người có quyền dùng `JFR.dump` hoặc `Recording.dump(Path)` vẫn có thể xuất; cần phân quyền vận hành.

## 16. Tổng kết và tài liệu chính thức

- JFR là công cụ chẩn đoán Java 11+ có chi phí thường tương đối thấp, nhưng chi phí thực phụ thuộc workload, event rate, sampling, threshold, stack traces và I/O. **Đo thay vì suy đoán.**
- **Tối thiểu hóa dữ liệu**: không đưa credential/PII/raw body vào custom event; xem xét built-in events và stack traces. `withoutStackTrace()` không phải cơ chế redact toàn bộ file.
- **`setMaxAge`, `setMaxSize`, `setToDisk`** điều khiển dữ liệu recording trong repository; **`setDuration`** điều khiển thời gian chạy recording.
- `dump(Path)` tạo file độc lập. `stop()`, `close()` và repository retention **không tự quản lý mọi bản dump, bản sao và backup**.
- Mọi file `.jfr` phải có ACL, encryption, owner, TTL, audit và quy trình xóa phù hợp với mục đích sử dụng.
- Mẫu Java 11 đã kiểm thử tạo ba custom events tối giản, đọc file bằng `RecordingFile` và xóa file thử nghiệm. Đây không phải bằng chứng mọi built-in event đều không nhạy cảm hoặc giới hạn repository đã được chạm trong test ngắn.

Tài liệu chính thức còn áp dụng:
- [Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html).
- [Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html).
- [Java SE 11 — Configuration](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Configuration.html).
- [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- [Java SE 11 — Package jdk.jfr](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- [Java SE 11 — jcmd](https://docs.oracle.com/en/java/javase/11/tools/jcmd.html).
- [Java SE 11 — java launcher, JFR options](https://docs.oracle.com/en/java/javase/11/tools/java.html).
- [Java SE 11 — FlightRecorderMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management.jfr/jdk/management/jfr/FlightRecorderMXBean.html).
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328).