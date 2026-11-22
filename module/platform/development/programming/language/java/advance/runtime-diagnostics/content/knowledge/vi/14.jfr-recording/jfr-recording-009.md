# 14.9. Đánh giá chi phí ghi, dung lượng và quyền truy cập vào file .jfr

## 1. Vấn đề cần giải quyết

**Java Flight Recorder (JFR)** giúp quan sát hành vi JVM bằng các sự kiện như hoạt động GC, cấp phát, thread, I/O và mẫu thực thi. Một bản ghi `.jfr` có thể rất hữu ích khi truy tìm độ trễ hoặc CPU bất thường; song việc bật ghi dữ liệu cũng tiêu tốn tài nguyên, sử dụng bộ nhớ đệm, tạo I/O và có thể lưu thông tin nội bộ của ứng dụng.

Vì vậy, trước khi bật JFR cho một JVM đang phục vụ người dùng, cần trả lời **ba câu hỏi độc lập**:

1. **Chi phí ghi:** với cấu hình event và tải hiện tại, JFR tác động bao nhiêu đến CPU, throughput, latency, pause, memory và I/O?
2. **Dung lượng:** recording repository nằm ở đâu, dữ liệu tăng bao nhiêu theo thời gian, `maxage`/`maxsize` bảo vệ được phần nào, và khi xuất `.jfr` có cần chỗ trống bổ sung không?
3. **Quyền truy cập:** ai có quyền ra lệnh ghi, tiến trình nào thực sự tạo file, ai đọc được các event, file được truyền đi/lưu giữ/xóa như thế nào?

**Mục tiêu:** biết chọn `default` hoặc `profile` theo mục đích, ước tính ngân sách tài nguyên bằng số đo có căn cứ, thực hiện một phiên ghi có giới hạn, xác minh quyền và khả năng đọc file, rồi đưa ra quyết định có thể triển khai. Đây là bài vận hành và quản trị một bản ghi; phân tích nội dung sự kiện JFR chi tiết thuộc các bài khác.

Ví dụ lệnh bên dưới dùng **HotSpot/OpenJDK 21** làm chuẩn đối chiếu. Các tùy chọn có thể khác ở JVM/JDK khác; luôn kiểm tra `jcmd <pid> help JFR.start` và `JFR.dump` trên JVM mục tiêu.

## 2. Mô hình dữ liệu: bộ đệm, repository và file .jfr là ba lớp khác nhau

JFR được tích hợp trong JVM: event được thu thập trong các buffer, sau đó có thể được ghi thành các **chunk** trong recording repository và xuất thành file `.jfr` có thể mở bằng JDK Mission Control (JMC) hoặc lệnh `jfr`.

~~~text
Ứng dụng / HotSpot
   │  tạo event (tên, thời gian, field, stack trace nếu bật)
   ▼
Bộ đệm JFR trong JVM / native memory
   │
   ├─ disk=true ──> repository chứa các recording chunks
   │                    │  dữ liệu rolling; chịu maxage/maxsize
   │                    │
   │                    └── JFR.dump / JFR.stop(filename=...)
   │                             ▼
   │                        file .jfr được xuất
   │                             ▼
   │                    lưu trữ, phân tích, chuyển giao, xóa
   │
   └─ disk=false ──> phụ thuộc dữ liệu còn trong buffer;
                       lịch sử bị giới hạn, không có kho chunk liên tục
~~~

**Ba hệ quả quan trọng:**

- **Repository** là chỗ lưu chunk trong khi JVM ghi; mặc định thường ở thư mục tạm của hệ điều hành, có thể được cấu hình bằng `JFR.configure repositorypath=...`. Không giả định rằng vì file xuất cuối cùng là `/secure/recordings/x.jfr` thì *mọi* dữ liệu trung gian đã nằm ở thư mục bảo mật đó.
- **File xuất** là sản phẩm khi dùng `JFR.dump`, `JFR.stop filename=...` hoặc các cơ chế dump/đóng phiên. Nó có vòng đời riêng. Xóa/rotate dữ liệu rolling trong repository **không tự động xóa** tất cả file đã dump sang nơi khác, các bản sao hay backup.
- `JFR.dump` có thể ghi một snapshot **khi recording vẫn tiếp tục**. Cần phân biệt “xuất file lúc 12:00” với “dừng ghi lúc 12:00”. Một phiên có thể sinh nhiều file snapshot; chúng cộng thêm dung lượng và rủi ro lộ dữ liệu.

`.jfr` là định dạng nhị phân có metadata và nhiều loại event, không phải file log text. Kích thước file không đơn thuần bằng số event nhân độ dài chuỗi hiển thị; thông tin schema, stack trace, pools và cấu trúc chunk cùng ảnh hưởng đến kích thước.

## 3. Những gì tạo nên chi phí JFR

| Thành phần | Nguồn chi phí | Cần đo gì? |
| --- | --- | --- |
| Tạo event | Thu field, timestamp, context, đôi khi lấy stack trace | CPU theo tiến trình, throughput và latency |
| Event có volume lớn | Nhiều event/giây do I/O, phân bổ object, thread activity... | Số event theo loại qua `jfr summary`, kích thước/s |
| Buffer và xử lý nội bộ | Native/in-JVM buffer, flush, metadata và housekeeping | Resident memory, native memory, GC và CPU |
| Ghi chunk vào repository | Storage throughput, IOPS, áp lực đĩa/overlay filesystem | Write bytes/s, I/O wait, storage quota, free space |
| Dump file | Đọc/chốt dữ liệu, serialize/copy sang output, có thể phát sinh I/O burst | Thời gian dump, peak I/O, dung lượng file và free space |
| Những event đặc biệt | Sự kiện/stack trace quá chi tiết, sampling dày, heap statistics, đường đến GC root | Pause/latency lúc thu, sự kiện GC, throughput |
| Phân tích file | JMC/`jfr` đọc, giải mã, hiển thị dữ liệu | RAM/CPU/disk của máy **phân tích**, tách khỏi JVM ghi |

Tài liệu Oracle JDK 21 mô tả `default.jfc` là cấu hình ít overhead, thích hợp cho ghi liên tục và thường dưới khoảng 1% với tác vụ phù hợp; `profile.jfc` ghi nhiều thông tin hơn nên có thể tốn tài nguyên hơn. **Con số điển hình không phải cam kết cho từng ứng dụng.** Một endpoint nhạy latency, workload I/O dày hoặc cấu hình tùy chỉnh có thể khác đáng kể.

### 3.1. Vì sao đổi event làm overhead tăng?

- **Bật thêm event:** thêm công việc và dữ liệu, nhất là event phát sinh theo mỗi thao tác thay vì định kỳ.
- **Giảm `threshold`:** event thời lượng ngắn trước đây bị bỏ qua bắt đầu được lưu, khiến lượng event tăng.
- **Tăng tần suất sampling (`period`):** có thêm mẫu và nhiều thao tác thu thập hơn; phải cân bằng độ phân giải với chi phí.
- **Bật stack trace hoặc tăng `stackdepth`:** chứa nhiều thông tin về call stack, làm tăng chi phí thu thập và file; lợi ích phụ thuộc mục đích điều tra.
- **Bật `HeapStatistics` hoặc thu đường đến GC root:** có thể kích hoạt công việc nặng, ảnh hưởng pause. Trên JDK 21, tùy chọn diagnostic command viết là `path-to-gc-root` (số ít); đối chiếu help của JVM đang chạy. Không bật như một thiết lập thường trực chỉ vì muốn “thu đủ dữ liệu”.
- **Ghi nhiều recording đồng thời:** cài đặt effective event settings và việc giữ/dump dữ liệu phụ thuộc trạng thái toàn JVM. Cần đo chi phí **tổng** và ngân sách storage cho toàn tiến trình, không nhân máy móc cost của một recording rồi cho rằng đúng tuyệt đối.

**Không suy overhead CPU chỉ từ kích thước .jfr.** Một event có stack trace đắt hơn một event field đơn giản; workload có file nhỏ vẫn có thể chịu pause do tùy chọn chẩn đoán nặng. Ngược lại file khá lớn không tự chứng minh JFR làm ứng dụng chậm.

### 3.2. Lựa chọn cấu hình đúng bài toán

| Mục đích | Cấu hình khởi đầu | Kiểm soát vận hành |
| --- | --- | --- |
| Ghi liên tục để có lịch sử khi sự cố xảy ra | `settings=default` | `disk=true`, giới hạn `maxage` và `maxsize`, giám sát free space |
| Tạm thời điều tra CPU, allocation, I/O sâu hơn | `settings=profile` | `duration` ngắn, giờ ít nhạy cảm, kiểm tra overhead và event volume |
| Điều tra một loại sự kiện cụ thể | Bản sao `.jfc` có chỉnh event/threshold phù hợp | Đối chiếu bộ lọc, thử trên staging; không sửa file `default.jfc` gốc |
| Điều tra nghi rò rỉ nghiêm trọng | Event liên quan allocation/heap và GC-root path khi thật sự cần | Chấp nhận công việc có thể nặng; lập cửa sổ/tiêu chí dừng rõ |

Với JFR tự động khởi động khi chạy JVM, có thể dùng `-XX:StartFlightRecording=...`; với JVM đã chạy, dùng `jcmd` để bật và kiểm tra thực tế. Cả hai cách cuối cùng đều phải giải bài toán cost, disk và quyền truy cập giống nhau.

## 4. Phiên thực hành có giới hạn với jcmd

Giả sử tiến trình HotSpot đang chạy có PID `21891`, thư mục `/srv/app/jfr/` đã được tạo, cấp quyền phù hợp và còn chỗ trống. **PID và path là ví dụ, không phải giá trị lấy từ máy của bạn.**

### 4.1. Xác minh JVM và tham số có thật

~~~bash
jcmd 21891 VM.version
jcmd 21891 help JFR.start
jcmd 21891 help JFR.dump
jcmd 21891 JFR.configure
~~~

Nếu một câu lệnh trả lỗi attach/quyền hoặc không tìm thấy diagnostic command, dừng lại ở bước kiểm tra đó. Đừng mặc định rằng các JVM không phải HotSpot hoặc các bản JDK khác có chính xác cùng tham số.

### 4.2. Ghi liên tục theo cửa sổ rolling

~~~bash
jcmd 21891 JFR.start name=diag-rolling settings=default disk=true maxage=30m maxsize=256m
jcmd 21891 JFR.check name=diag-rolling
~~~

- `name` giúp định danh khi có nhiều recording.
- `settings=default` chọn bộ event ít overhead hơn so với `profile`.
- `disk=true` cho phép ghi chunk vào repository.
- `maxage=30m` giữ dữ liệu rolling trong khoảng thời gian mục tiêu; `maxsize=256m` đặt giới hạn nominal cho dữ liệu giữ lại trên disk của recording này. **Điều kiện nào đến trước sẽ làm dữ liệu cũ bị loại**, nên một lần dump có thể không chứa đủ 30 phút khi event rate quá cao.
- Với JDK 21, `maxsize` phải không nhỏ hơn `maxchunksize` của cấu hình JFR. Cơ chế chunk/flush khiến không nên coi đúng 256 MiB là quota cứng cho toàn bộ filesystem.

**Thiết lập repository riêng:** nếu cần đặt chunk ở phân vùng được kiểm soát, kiểm tra `JFR.configure repositorypath=/srv/app/jfr/repository` trước khi khởi tạo recording và xác minh đường dẫn/quyền phía JVM. Một số tham số JFR chỉ có thể thay đổi trước khi hệ thống JFR được khởi tạo; hãy đối chiếu help và trạng thái VM. Đừng chuyển repository sau khi ghi bằng cách tự move các chunk đang hoạt động.

### 4.3. Xuất snapshot rồi kết thúc có kiểm soát

~~~bash
# File do JVM đích ghi, path được diễn giải trong filesystem của JVM đó
jcmd 21891 JFR.dump name=diag-rolling filename=/srv/app/jfr/diag-rolling.jfr

# Kiểm tra recording vẫn chạy sau thao tác dump
jcmd 21891 JFR.check name=diag-rolling

# Dừng khi không còn cần thu thập
jcmd 21891 JFR.stop name=diag-rolling

# Kiểm tra file đã xuất bằng công cụ đi kèm JDK
jfr summary /srv/app/jfr/diag-rolling.jfr
~~~

`JFR.dump` không ngụ ý stop. Trong ví dụ này, dump đã tạo file trước khi gọi stop. Lệnh `JFR.stop` **không có `filename`** không phải lệnh xuất file cuối cùng; nếu chưa dump mà muốn giữ dữ liệu, chỉ định `filename` khi stop.

Một phiên profiling hữu hạn có thể bắt đầu trực tiếp như sau:

~~~bash
jcmd 21891 JFR.start name=diag-profile settings=profile duration=2m disk=true filename=/srv/app/jfr/profile-2m.jfr
~~~

Lệnh có `duration=2m` là thu theo thời hạn; file `filename` dùng khi recording kết thúc. Khi có lỗi JVM hoặc kill đột ngột, không được mặc định file sẽ hoàn chỉnh hay mọi event đã kịp flush.

### 4.4. Khác nhau giữa maxage/maxsize khi start và khi dump

| Tham số | `JFR.start` với `disk=true` | `JFR.dump` |
| --- | --- | --- |
| `maxage` | Giới hạn lịch sử dữ liệu **giữ trong recording** | Chọn cửa sổ lịch sử cần **xuất** nếu còn dữ liệu |
| `maxsize` | Giới hạn nominal dung lượng dữ liệu **giữ** | Giới hạn lượng dữ liệu dùng để **xuất** |
| `filename` | Đích cuối khi recording dừng (khi có cấu hình) | Đường dẫn xuất snapshot **ngay khi chạy lệnh** |
| `duration` | Thời gian thu trước khi recording tự dừng | Không có cùng ý nghĩa |
| `disk=false` | Không duy trì lịch sử chunk trên disk như `disk=true` | Không thể dùng như cách lưu lịch sử dài hạn |

**Cần tránh hiểu sai:** `maxage=30m` không tự lập lịch xóa file `diag-rolling.jfr` đã xuất và `maxsize=256m` không giới hạn tổng số bản sao từ mọi `JFR.dump` hay backup. Nếu chạy cron dump mỗi 5 phút, phải quản lý số lượng file, thời gian lưu trữ và quota **riêng**.

## 5. Đo overhead bằng thử nghiệm A/B có kiểm soát

Một con số phần trăm từ tài liệu không thay cho measurement trên hệ thống thật. Quy trình tối thiểu:

1. **Baseline:** chạy workload đại diện mà không có recording JFR bổ sung, thu ít nhất vài cửa sổ để biết độ dao động tự nhiên. Ghi JDK/vendor, GC, CPU quota, heap và load.
2. **Default:** cùng môi trường và workload, bật `settings=default` với mục tiêu duration/retention, đo chính xác cùng chỉ tiêu.
3. **Profile hoặc custom:** chỉ khi thật sự cần, lặp lại có giới hạn. Không so một đợt tải cao với một baseline tải thấp rồi kết luận JFR là nguyên nhân.
4. **Tách warmup:** warmup JIT, cache và tải GC ban đầu có thể làm lệch kết quả. Dùng nhiều lượt, giữ thời gian steady-state tương tự; thử nghiệm ngược thứ tự nếu phù hợp.
5. **Tách thời điểm dump:** đo riêng chi phí **ghi liên tục** và burst khi `JFR.dump`/`JFR.stop`; dump cũng có thể bị ảnh hưởng filesystem hoặc network volume.
6. **Thẩm định:** so sánh median và các phân vị quan trọng qua các lượt, ghi độ dao động/noise, không chỉ một sample đẹp.

Bộ metric nên có:

| Nhóm | Metric cần thu | Cách giải thích |
| --- | --- | --- |
| Trải nghiệm | Throughput, p95/p99 latency, error rate | Chỉ tiêu nghiệp vụ quyết định có chấp nhận overhead hay không |
| CPU | Process CPU time, CPU utilization, throttling | Đừng nhầm CPU% cao do load lớn với cost JFR |
| Memory | Heap used/committed, process RSS, native memory khi có công cụ | JFR dùng buffer và metadata; chỉ heap used không đủ |
| GC | Số sự kiện, pause distribution, thời gian GC | Phân biệt thay đổi workload/GC với tác động recording |
| Storage | Disk write bytes/s, IOPS, free bytes, quota | Theo dõi cả repository và đường xuất file |
| File | Byte size `.jfr`, duration, event count theo loại | Dùng để ước tính tốc độ dữ liệu và nhận diện event quá nhiều |
| Dump | Wall-clock duration, peak I/O, thông báo lỗi | Một lần dump lớn có thể gây spike khác với chi phí ghi nền |

### 5.1. Công thức so sánh và ví dụ giả định

Nếu metric “càng thấp càng tốt” (CPU, latency), mức tăng tương đối là:

\[
\text{Tăng chi phí (\%)} =
\frac{\text{Giá trị khi bật JFR} - \text{Baseline}}{\text{Baseline}}\times 100
\]

Nếu metric “càng cao càng tốt” (throughput), mức suy giảm là:

\[
\text{Giảm throughput (\%)} =
\frac{\text{Baseline} - \text{Giá trị khi bật JFR}}{\text{Baseline}}\times100
\]

Bảng dưới là **số liệu giả định để luyện cách tính**, không phải benchmark JFR hay mức chấp nhận chung:

| Metric | Không ghi | `default` | `profile` |
| --- | ---: | ---: | ---: |
| Throughput | 1.000 req/s | 990 req/s | 950 req/s |
| CPU tiêu thụ trung bình | 2,00 cores | 2,04 cores | 2,20 cores |
| p99 latency | 100 ms | 105 ms | 120 ms |

Theo bảng: `default` giảm throughput **1%**, CPU tăng **2%**, p99 tăng **5%**. `profile` giảm throughput **5%**, CPU tăng **10%**, p99 tăng **20%**. Không được dùng kết quả giả định này để dự đoán mọi ứng dụng.

Đặc biệt, nếu CPU bị quota/throttling, một mức tăng CPU nhỏ có thể gây đột biến p99 lớn. Nếu p99 dao động tự nhiên 20 ms, chênh 5 ms trong một lượt chưa đủ kết luận. Cần thử nhiều lượt với cùng điều kiện và tiêu chí dừng do chủ hệ thống quy định.

## 6. Ước tính dung lượng và retention bằng dữ liệu thật

### 6.1. Đo tốc độ sinh dữ liệu

Đối với một snapshot đại diện, ghi:

- **Tổng số byte file:** dùng `stat` hoặc thông tin filesystem; quy ước rõ MB hay MiB.
- **Thời gian chứa trong bản ghi:** tính từ timestamp thực của các event/cửa sổ; không tự lấy thời gian đã bật lệnh nếu recording bị delay, rotate hoặc thiếu đoạn.
- **Event count theo loại:** `jfr summary file.jfr` giúp nhận diện event nào chiếm dung lượng và tổng hợp ở file.
- **Tốc độ:** `rate = bytes / seconds` của cửa sổ quan sát. Thử cả giờ bình thường lẫn giờ cao điểm; rate có thể tăng theo số request, hoạt động GC hoặc I/O.

Công thức ước lượng tuyến tính ban đầu:

\[
B_\mathrm{window}\approx R_\mathrm{bytes/sec}\times T_\mathrm{seconds}
\]

Nếu có `n` JVM hoặc nhiều recording/file dump, tính tổng theo từng nguồn:

\[
B_\mathrm{total}\approx \sum_{i=1}^{n} R_i T_i
+ B_\mathrm{exports}+B_\mathrm{headroom}
\]

Đây là **ước tính ngân sách**, không phải công thức chính xác cho mọi JFR: chunk rotation, dữ liệu nén/mã hóa định dạng, profile, event mix, snapshot và độ trễ flush đều có thể làm rate biến đổi.

**Ví dụ giả định:** một file chứa **96 MiB trong 12 phút**, tốc độ xấp xỉ **8 MiB/phút**. Để có khoảng 30 phút lịch sử với tốc độ tương tự cần khoảng **240 MiB**. Một recording cấu hình `maxage=30m maxsize=256m` sẽ có ngân sách khá sát ở tải này; khi event rate tăng, constraint kích thước có thể khiến mất các phút cũ trước khi đủ 30 phút. Ngoài ra phải dành chỗ cho chunk đang ghi, bản dump đã xuất, file của JVM khác và phần dự phòng filesystem.

Nếu hệ thống cần chắc chắn giữ tối thiểu 30 phút **trong giờ cao điểm**, đo percentile cao của rate rồi đặt `maxsize` và quota filesystem với headroom đủ. **Không đặt một quota bằng đúng dung lượng trung bình rồi cho rằng đã an toàn.**

### 6.2. Dung lượng mà maxsize không quản lý

Giả sử có 8 JVM, mỗi JVM ghi rolling tối đa 256m, tức riêng các recording đã có thể tiêu thụ khoảng 8 × 256m trước khi xét repository overhead, quota chung và các recording khác. Nếu mỗi JVM còn dump file lớn mỗi 10 phút sang thư mục lưu 7 ngày, tổng file xuất có thể nhiều lần vượt ngân sách ghi rolling.

Cần phân biệt ít nhất **bốn khu vực**:

1. JFR buffer và metadata trong JVM.
2. Repository chunks đang được JVM duy trì.
3. Output `.jfr` sau dump/stop, có thể cùng ổ hoặc ổ khác với repository.
4. Bản sao gửi sang object storage, máy phân tích, hệ thống ticket, backup và các artifact CI.

Hạn chế quyền truy cập, quota, thời hạn xóa và monitoring cho **từng khu vực**. File quay vòng ở bước 2 không bảo đảm vòng đời file ở bước 3 hoặc 4.

### 6.3. Gợi ý giám sát dung lượng

- Theo dõi `free bytes` và `free inodes` của filesystem chứa repository và output, chứ không chỉ `du` của thư mục output.
- Cảnh báo khi còn quá ít chỗ cho một lần dump tệ nhất; đừng chờ đến 100% đĩa.
- Xác định ai làm housekeeping các file đã export và xử lý thất bại khi xóa/upload.
- Tăng đột biến `.jfr` size? Dùng `jfr summary` để tìm event count theo loại; so lại với thay đổi settings/workload trước khi quy lỗi.
- Dump có thể thất bại vì disk full, thiếu quyền, path sai, namespace hoặc lỗi ghi. Không gán file 0 byte hay file thiếu thành “không có sự kiện”.

## 7. Quyền truy cập: ra lệnh khác với đọc file

Một ca thu thập thành công cần phân biệt **ba chủ thể**:

| Chủ thể | Quyền cần có | Trường hợp lỗi điển hình |
| --- | --- | --- |
| Người/công cụ gửi `jcmd` | Có thể attach và gửi diagnostic command tới JVM đích theo policy/OS | Không cùng quyền user, JVM không attach được, container PID namespace khác |
| Tiến trình JVM ghi chunk/file | Có quyền ghi **trong filesystem mà JVM nhìn thấy** | `JFR.dump` path ở host nhưng không tồn tại trong container; thư mục không writable |
| Người/công cụ đọc file `.jfr` | Có quyền traverse directory + đọc file; có công cụ JFR tương thích | Có file nhưng JMC/`jfr` không đọc được; ACL hoặc bản sao sai owner |

Người gửi `jcmd` không nhất thiết là người sở hữu file được tạo. Path đích của lệnh được xử lý **bên trong JVM đích**. Ví dụ JVM trong container có thể ghi `/srv/app/jfr/out.jfr` ở mount riêng; cùng đường dẫn chữ đó trên host không nhất thiết trỏ tới cùng đối tượng.

### 7.1. File .jfr có thể chứa dữ liệu nhạy cảm

Tùy cấu hình và event được bật, file có thể hé lộ:

- Tên package/class/method, stack trace, cấu trúc mã, đường dẫn filesystem.
- Tên thread, tiến trình, thông tin host/JVM và thành phần ứng dụng.
- Thông tin file/network, endpoint, thời điểm request, SQL hoặc payload **nếu** ứng dụng/framework/custom JFR event đã ghi các field đó.
- Tên người dùng, mã định danh nghiệp vụ, URL hoặc secret nếu custom event vô tình log chúng.

Không giả định mọi `.jfr` đều chứa mật khẩu hay payload; **nội dung thực tế phụ thuộc event settings**. Nhưng cũng không coi JFR “chỉ là profiling data vô hại”. Hãy duyệt event types và field trước khi chuyển file ra khỏi môi trường được phép.

**Chính sách tối thiểu:** quyền cần thiết ít nhất (least privilege), nơi lưu rõ ràng, hạn sử dụng, mã hóa khi truyền/lưu nếu yêu cầu tổ chức, audit ai được đọc/tải/xóa, hạn chế chia sẻ qua chat/email/ticket không được cấp quyền và xóa bản tạm sau phân tích. Nếu lọc event bằng `jfr scrub`, hãy kiểm tra file kết quả: lọc loại event không tự động ẩn danh mọi chuỗi/field nhạy cảm còn lại.

### 7.2. Ví dụ trên Linux/Unix

Giả sử ứng dụng chạy với user dịch vụ và quản trị viên đã cung cấp thư mục đúng owner. Trước khi khởi động JVM, thiết lập thư mục với quyền giới hạn:

~~~bash
# Thực hiện bằng user dịch vụ hoặc trong provisioning có quyền tương ứng.
install -d -m 700 /srv/app/jfr
install -d -m 700 /srv/app/jfr/repository

# Chỉ có ý nghĩa khi chạy cùng shell khởi động JVM:
umask 077
java -jar app.jar
~~~

`umask 077` của shell gửi `jcmd` sau này **không đổi umask của JVM đang chạy**. Quyền thực tế của repository/output phụ thuộc quyền user JVM, mode thư mục, umask, ACL, triển khai JFR và filesystem. Sau dump, kiểm tra:

~~~bash
ls -ld /srv/app/jfr /srv/app/jfr/repository
stat -c '%U %G %a %s %n' /srv/app/jfr/diag-rolling.jfr
# Nếu môi trường có ACL:
getfacl /srv/app/jfr/diag-rolling.jfr
~~~

Nếu file quá rộng quyền, xử lý theo chính sách owner/ACL của dịch vụ; trên filesystem POSIX thông thường có thể cần `chmod 600` file sau khi tạo, nhưng không dùng `chmod 777` để chữa lỗi ghi file. Cần cấp quyền đi qua **mọi thư mục cha** cho reader hợp lệ.

Cũng đừng cấu hình repository trong `/tmp` dùng chung rồi chủ quan rằng chỉ file exported được bảo vệ. Nếu bắt buộc dùng tạm, kiểm tra quyền thư mục và tiến trình tạo, cleanup khi crash/restart và mount options.

### 7.3. Container, Kubernetes và Windows

**Container/Kubernetes:**

- PID host, PID trong container và quyền attach có thể khác. Sử dụng đúng JVM/PID namespace và bảo đảm tool nhìn được tiến trình.
- `JFR.configure repositorypath` và `JFR.dump filename` phải trỏ tới path có thể ghi trong **container JVM**; nếu muốn lấy file từ ngoài, kiểm tra mount và quyền của volume.
- Ephemeral storage có quota và có thể bị mất sau khi pod kết thúc; đừng chỉ dựa vào việc file tồn tại trong container để coi như đã lưu trữ lâu dài.
- Volume chia sẻ, sidecar, user namespace, securityContext, read-only root filesystem có thể làm thay đổi khả năng ghi và đọc.
- Không lưu file nhạy cảm lâu dài trong image layer, logs hoặc CI artifact công khai.

**Windows:** kiểm tra file/dir ACL bằng `icacls` hoặc công cụ quản trị thích hợp, kiểm tra account chạy JVM (service account), ổ đĩa/đường dẫn và cơ chế cleanup. `chmod`/`umask` ở trên là ví dụ POSIX, không áp dụng nguyên dạng cho NTFS ACL.

### 7.4. Điều gì là bảo mật, điều gì chỉ là vận hành?

- `maxage`/`maxsize` là biện pháp **giới hạn dữ liệu giữ**, không phải tính năng phân quyền hay mã hóa.
- Đổi đuôi `.jfr`, zip hoặc di chuyển file vào thư mục ẩn không bảo vệ dữ liệu; cần access controls thật.
- JFR dump thành công không chứng minh người phân tích được quyền đọc; cần kiểm tra ACL trên **output thực**.
- File đã xóa khỏi repository có thể còn backup/copy. Retention policy phải xử lý cả bản sao và yêu cầu pháp lý của tổ chức.

## 8. Java 17+ thực hành: ghi file .jfr nhỏ, đo kích thước và kiểm tra lại event

Ví dụ sau sử dụng **JFR API chính thức** `jdk.jfr` và `jdk.jfr.consumer` có sẵn trong JDK 17 trở lên. Nó tạo một loại event tùy chỉnh, bật event này, phát 200 sự kiện, dump tệp tạm `.jfr`, đọc lại để xác minh và xóa tệp. Ví dụ minh họa **khả năng đo/kiểm tra**, không phải một benchmark throughput/CPU đáng tin: không nên dùng thời gian của chương trình ngắn này làm % overhead của một dịch vụ production.

Tệp duy nhất `JfrBudgetDemo.java`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import jdk.jfr.consumer.RecordedEvent;

public final class JfrBudgetDemo {
    @Name("training.CostEvent")
    @Label("Cost demo event")
    static final class CostEvent extends Event {
        @Label("Sequence")
        long sequence;
    }

    public static void main(String[] args) throws Exception {
        Path destination = Files.createTempFile("jfr-budget-", ".jfr");
        try {
            try (Recording recording =
                     new Recording(Configuration.getConfiguration("default"))) {
                recording.setName("budget-demo");
                recording.setToDisk(true);
                recording.setMaxAge(Duration.ofMinutes(1));
                recording.setMaxSize(32L * 1024 * 1024);
                recording.enable(CostEvent.class).withoutStackTrace();

                recording.start();
                for (int i = 0; i < 200; i++) {
                    CostEvent event = new CostEvent();
                    event.sequence = i;
                    event.commit();
                }
                recording.stop();
                recording.dump(destination);
            }

            int matchingEvents = 0;
            try (RecordingFile recordingFile = new RecordingFile(destination)) {
                while (recordingFile.hasMoreEvents()) {
                    RecordedEvent event = recordingFile.readEvent();
                    if (event.getEventType().getName()
                             .equals("training.CostEvent")) {
                        matchingEvents++;
                    }
                }
            }

            System.out.println("matchingEvents=" + matchingEvents);
            System.out.println("nonEmpty=" + (Files.size(destination) > 0));
            System.out.println("fileDeletedInFinally=true");
        } finally {
            Files.deleteIfExists(destination);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac JfrBudgetDemo.java
java JfrBudgetDemo
~~~

Stdout của ví dụ đã được kiểm chứng với OpenJDK 24, và logic event tương thích với JDK 17+:

~~~text
matchingEvents=200
nonEmpty=true
fileDeletedInFinally=true
~~~

**Giải thích từng phần:**

- `Configuration.getConfiguration("default")` bắt đầu từ cấu hình JFR mặc định, sau đó `enable(CostEvent.class)` bật rõ custom event. Nếu không bật event thì không thể mặc định rằng 200 lời gọi `commit()` sẽ xuất hiện trong file.
- `withoutStackTrace()` giảm dữ liệu stack cho event của bài lab; khi điều tra call site thật, stack trace có thể cần thiết và có chi phí.
- `setToDisk(true)`, `setMaxAge` và `setMaxSize` giới hạn lịch sử của recording; chúng **không** đặt ACL hay quota cho file xuất.
- `recording.stop()` rồi `recording.dump(destination)` ghi file từ dữ liệu recording đã dừng. Với recording có `toDisk=true`, API cho phép dump sau stop khi recording chưa close.
- `RecordingFile` kiểm tra event trong file, giúp phân biệt “có một file .jfr” với “file thực sự chứa event cần thiết”.
- `Files.size` kiểm tra file không rỗng; **kích thước byte cụ thể sẽ khác giữa JDK/máy/lần chạy** nên ví dụ chỉ in boolean.
- `try/finally` dọn file tạm cả khi một bước phát sinh exception; dòng `fileDeletedInFinally=true` mô tả nhánh cleanup sắp chạy, không phải phép xác nhận sau khi xóa. Trong ứng dụng thật, đường dẫn tạm cũng cần đáp ứng chính sách bảo mật.

**Muốn đo overhead:** giữ workload thật của ứng dụng ổn định và chạy các phiên baseline/default/profile từ phần 5. Không lấy thời gian startup JVM/JFR của chương trình nhỏ này để suy ra cost trên production. **Muốn đo kích thước:** đổi dòng `nonEmpty` thành in `Files.size(destination)`, nhưng hiểu đây là số byte của *một* file và *một* workload, không phải hệ số cố định cho mọi session.

**Muốn giữ file để phân tích:** dùng thư mục đã cấp quyền phù hợp và bỏ cleanup có chủ ý trong một phiên kiểm soát; thay đổi đó phải kèm chính sách giữ và xóa file. Không đặt output production mặc định vào temp công khai.

## 9. Chẩn đoán lỗi thu bản ghi theo từng lớp

| Triệu chứng | Khả năng thường gặp | Bước kiểm chứng |
| --- | --- | --- |
| `jcmd` không tìm thấy PID hoặc attach failed | Sai PID/namespace; khác user; JVM dừng; attach bị chặn | `jcmd -l` trong đúng môi trường, quyền OS, `VM.version` |
| `JFR.start` báo option invalid | JDK/VM khác, tên option sai, `maxsize` dưới `maxchunksize` | `jcmd <pid> help JFR.start` và `JFR.configure` |
| Recording chạy nhưng không có file output | Chưa dump/stop có filename; path mong đợi sai; `disk=false` không lưu lịch sử | `JFR.check`, `JFR.dump`, vị trí mà JVM nhìn thấy |
| Dump báo permission denied | JVM user không ghi được thư mục hoặc không traverse parent | Owner/mode/ACL của cả path, account JVM |
| File đã được tạo nhưng người phân tích không mở được | Reader thiếu ACL, file chưa copy ra volume, file chưa hoàn tất/không hợp lệ | `stat`/`icacls`, `jfr summary`, filesystem mount |
| Dung lượng repository tăng nhanh | Event rate cao, thiếu maxage/maxsize, nhiều recordings | `JFR.check`, settings, disk usage, event count |
| .jfr lớn hơn dự tính | Event type/threshold thay đổi, nhiều stack traces, workload khác | `jfr summary`, so thời điểm cùng workload |
| File .jfr nhỏ nhưng thiếu thời điểm cần điều tra | Retention quá ngắn, `maxsize` đã loại chunk cũ, recording bắt đầu muộn | Timeline, start time, `maxage`, free space, file event timestamps |
| P99 tăng khi dump | I/O burst, GC-root path, shared disk bị bão hòa hoặc concurrency | So thời điểm dump với latency, IOPS, GC/JFR events |
| Dung lượng trong repo giảm nhưng ổ vẫn đầy | File export/snapshot/backup tích tụ hoặc file bị giữ mở | `du`/`df`, quota, file ownership, housekeeping |

Trong dashboard, phân biệt `RECORDING_RUNNING`, `DUMP_SUCCEEDED`, `FILE_VALIDATED` và `FILE_SECURED`. Một trạng thái xanh cho start không thay thế xác minh file đã được tạo, có event cần thiết và được bảo vệ.

## 10. Quy trình vận hành đề xuất và tiêu chí dừng

Trước khi thu: xác định câu hỏi điều tra cụ thể, thời hạn recording, phiên bản JDK, sự kiện cần thu, ai sở hữu dữ liệu, dung lượng còn lại và quyền đọc/ghi. Đặt cơ chế kiểm tra sau khi bật.

Trong lúc thu: quan sát throughput/p99/CPU, free space/quota, event rate và lỗi ghi. Nếu ứng dụng vượt ngưỡng hiệu năng đã phê duyệt hoặc filesystem sắp đầy, dừng theo quy trình ứng cứu; đừng chạy mãi vì “default thường nhẹ”.

Khi kết thúc: chủ động `dump` hoặc `stop filename=...`, kiểm tra exit status, `jfr summary`, khoảng thời gian/event types, kích thước và ACL. Chỉ chuyển file tới người có quyền và giải thích mục đích/độ nhạy của nó. Thu hồi quyền tạm, xóa file không cần thiết và theo dõi các bản sao.

### Checklist quyết định có bật JFR hay không

- [ ] Có câu hỏi chẩn đoán và thời gian cần giữ, thay vì thu tất cả event vô hạn.
- [ ] Đã kiểm tra `jcmd ... help JFR.start` cho JVM cụ thể; biết settings, version và collector.
- [ ] Đã đo hoặc ước tính hợp lý tác động đến CPU/latency và đặt ngưỡng dừng.
- [ ] Đã xác định repository path, output path, volume/mount, filesystem quota và dung lượng dự phòng.
- [ ] Đã chọn `maxage`/`maxsize` hoặc duration thích hợp, hiểu chunk rotation và bản dump không bị chúng xóa.
- [ ] Đã phân biệt quyền attach, quyền JVM ghi file và quyền của người đọc.
- [ ] Đã kiểm tra file có thể chứa dữ liệu nhạy cảm và có chính sách truyền/lưu/xóa.
- [ ] Có lệnh xác minh sau dump (`JFR.check`, `jfr summary`, size, ACL) và có người chịu trách nhiệm cleanup.

## 11. Bài tập tự kiểm tra

**Bài 1 — overhead.** Trên cùng workload, baseline 1.000 req/s và p99 = 100 ms, bật `profile` còn 950 req/s và p99 = 120 ms. Throughput giảm bao nhiêu? **5%**. p99 tăng bao nhiêu? **20%**. Có được kết luận mọi JFR đều tăng p99 20% không? **Không**; đây là dữ liệu của cấu hình, workload và cửa sổ đo cụ thể.

**Bài 2 — retention.** Một recording sinh 8 MiB/phút. Mục tiêu giữ ít nhất 30 phút lịch sử, `maxsize` chỉ 160 MiB. Ở tốc độ ổn định lý tưởng, cửa sổ 160/8 ≈ **20 phút**, trước khi xét chunk và overhead. Tăng `maxage` lên 1h có tự giải quyết không? **Không**; size bound vẫn loại dữ liệu cũ.

**Bài 3 — nhiều bản dump.** Một JVM ghi rolling với `maxsize=256m` nhưng automation dump 100 MiB mỗi 5 phút trong 6 giờ và không dọn file. Khoảng bao nhiêu dữ liệu export? **72 × 100 MiB = 7.200 MiB**, chưa kể repo và các bản sao. `maxsize` không bảo vệ thư mục output khỏi tích tụ này.

**Bài 4 — quyền container.** Operator gửi được `JFR.dump` nhưng JVM báo không tạo được `/mnt/jfr/report.jfr`. Chẩn đoán theo thứ tự: path trong container JVM có tồn tại không, process UID/GID là gì, parent directories có execute/write permission không, mount có read-only/quota không. Việc operator nhìn thấy `/mnt/jfr` trên host không chứng minh container cũng nhìn thấy cùng volume.

**Bài 5 — chia sẻ dữ liệu.** Một bản `.jfr` có custom event chứa URL yêu cầu và user identifier. Có thể công khai chỉ vì đã dùng `jfr scrub` lọc GC event không? **Không**; phải kiểm tra những event/field còn lại, xác nhận policy và quyền người nhận.

**Bài 6 — hiệu năng.** File chỉ 4 MiB nhưng một lần recording làm p99 tăng cao lúc dừng. Có thể kết luận do dung lượng lớn không? **Không**; cần đối chiếu GC-root path, heap statistics, CPU/GC, I/O burst và các công việc JVM diễn ra trong thời điểm dump/stop.

## 12. Các điểm dễ nhớ

1. `default.jfc` là khởi điểm nhẹ cho ghi liên tục, `profile.jfc` phù hợp điều tra sâu có giới hạn; **đo overhead trên tải thật**.
2. **Repository chunks khác output .jfr**. Quota rolling không xóa các file export/copy.
3. `maxage` và `maxsize` giới hạn lịch sử giữ trong recording khi `disk=true`; kích thước đĩa của toàn node còn phụ thuộc số JVM, chunk và bản xuất.
4. Quyền **gửi `jcmd`**, quyền **JVM ghi file** và quyền **đọc file** là ba bài toán độc lập.
5. `.jfr` có thể chứa thông tin nhạy cảm. Phân quyền, kiểm tra nội dung, retention và cleanup phải đi cùng việc thu thập.
6. Một bản ghi chỉ thực sự hữu ích khi có đúng event và khoảng thời gian cần điều tra, không làm vi phạm budget hiệu năng/dung lượng/quyền truy cập.

## Tài liệu tham khảo

- Oracle Java SE 21, [Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html) — `default.jfc`, `profile.jfc` và trade-off overhead.
- Oracle Java SE 21, [The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) — `JFR.configure`, `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`, giới hạn size/age và tên option trên JDK 21.
- Oracle Java SE 21, [The jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html) — `summary`, `print`, `metadata`, `scrub` và phân tích file.
- Oracle Java SE 21, [jdk.jfr.Recording API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html) và [jdk.jfr.consumer](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html) — tạo, dừng, dump, size/age và đọc sự kiện.
- Oracle Java SE 21, [The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html) — `-XX:StartFlightRecording` và tham số JFR lúc khởi động.
