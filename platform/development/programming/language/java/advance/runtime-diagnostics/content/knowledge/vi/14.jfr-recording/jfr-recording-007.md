# 14.7 Quản lý duration, maxage, maxsize, repository và dump khi tiến trình thoát

## 1. Bức tranh tổng thể: vòng đời của một bản ghi JFR

**Java Flight Recorder (JFR)** thu thập các sự kiện về hoạt động JVM và ứng dụng với cấu hình được chọn. Trong HotSpot JDK 17+, có thể bắt đầu bản ghi ngay khi khởi động JVM hoặc điều khiển JVM đang chạy bằng `jcmd`. Muốn thu dữ liệu hữu ích mà không để đĩa tăng vô hạn, cần hiểu năm khái niệm khác nhau:

1. **`duration`:** bản ghi chạy trong bao lâu trước khi tự dừng.
2. **`maxage`:** giữ lại lịch sử trên đĩa tối đa bao xa về quá khứ.
3. **`maxsize`:** giới hạn lượng dữ liệu của bản ghi được giữ lại trong repository trên đĩa.
4. **`repository`:** thư mục tạm lưu các *chunk* trong quá trình thu thập; khác tệp `.jfr` xuất ra để phân tích.
5. **`dumponexit`:** thử xuất dữ liệu của bản ghi **còn đang chạy** khi JVM tắt theo đường kết thúc bình thường.

Đây là các cơ chế thuộc **những lớp quản lý khác nhau**, không phải năm tên khác nhau cho cùng một giới hạn. Một bản ghi dài hạn có thể chạy không xác định thời gian nhưng chỉ giữ lại 30 phút gần nhất; bản ghi điều tra 2 phút có thể tự dừng và xuất thành một tệp; bản ghi bật dump-on-exit có thể xuất khi ứng dụng kết thúc dù chưa tới lịch dừng.

### Hai tầng lưu trữ cần phân biệt

```text
Events sinh ra trong JVM
         |
         v
Bộ đệm JFR trong bộ nhớ
         |
         | disk=true: ghi dần các chunk
         v
Repository tạm của JVM  <--- maxage / maxsize giới hạn lịch sử lưu
         |
         | JFR.dump / JFR.stop filename=...
         | hoặc auto-stop / dumponexit + filename=...
         v
Tệp .jfr đã xuất      <--- cần kiểm tra, sao lưu và quản lý riêng
         |
         v
jfr summary / JDK Mission Control / công cụ phân tích
```

**Điểm quan trọng:** `maxage` và `maxsize` của bản ghi tác động vào **dữ liệu được giữ trong repository**, không tự đặt vòng đời hay dung lượng tối đa cho tất cả các tệp `.jfr` đã xuất trước đó. Nếu chunk cũ đã bị loại bỏ thì một lần `JFR.dump` về sau không thể khôi phục nó.

## 2. Bảng tra nhanh: tham số nào kiểm soát việc gì?

| Tùy chọn | Phạm vi | Giá trị ví dụ | Ý nghĩa khi sử dụng |
| --- | --- | --- | --- |
| `duration` | Một recording, lúc `JFR.start` hoặc `-XX:StartFlightRecording` | `2m` | Tự kết thúc sau hai phút thu thập. `0s`: chạy không giới hạn thời lượng. |
| `maxage` | Lịch sử **trong repository** của một recording khi `disk=true` | `30m` | Giữ tối đa khoảng 30 phút dữ liệu gần nhất, xét theo chunk; `0s`: không giới hạn tuổi. |
| `maxsize` | Lịch sử **trong repository** của một recording khi `disk=true` | `256m` | Giữ lượng dữ liệu khoảng giới hạn byte cấu hình; `0`: không giới hạn kích thước. |
| `disk` | Một recording | `true` | Cho phép dữ liệu liên tục được lưu vào repository; mặc định của `JFR.start` là `true`. |
| `repositorypath` | Cấu hình JFR của JVM qua `JFR.configure` | `/tmp/jfr-repo` | Thư mục tạm chứa chunk. |
| `repository` | Cấu hình JVM lúc khởi động qua `-XX:FlightRecorderOptions` | `/tmp/jfr-repo` | Cùng vai trò thư mục tạm, nhưng cú pháp flag khác. |
| `filename` | Đích xuất khi recording dừng / dump-on-exit hoặc khi gọi `JFR.dump` | `/tmp/jfr-out/incident.jfr` | Tệp kết quả, cần có quyền ghi; đường dẫn được hiểu từ **JVM mục tiêu**. |
| `dumponexit` | Một recording | `true` | Xuất khi JVM tắt theo đường xử lý shutdown, **nếu recording vẫn chạy**; mặc định `false`. |
| `JFR.dump maxage/maxsize` | Một lần **xuất** | `maxage=10m` | Chọn phần dữ liệu được đưa vào tệp xuất từ dữ liệu vẫn còn; **không thay đổi retention policy** của recording đang chạy. |
| `preserve-repository` | Cấu hình JFR của JVM | `true`/`false` | Kiểm soát giữ các chunk tạm sau JVM exit; mặc định `false`. **Không thay thế một tệp export được xác minh.** |

Theo tài liệu `jcmd` của JDK 21, `JFR.start` mặc định `duration=0s`, `maxage=0s` và `maxsize=0`, tức **không giới hạn ba đại lượng** nếu bạn không đặt rõ. Khi duy trì recording dài hạn, nên chủ động cấu hình giới hạn lưu trữ.

**Đơn vị hợp lệ trong các ví dụ:**

- Khoảng thời gian thường có hậu tố `s` (giây), `m` (phút), `h` (giờ); chọn kiểu mà phiên bản lệnh thực tế hỗ trợ. Ví dụ `duration=90s`, `maxage=1h`.
- `maxsize=256m` sử dụng hậu tố kích thước `m/M`; `g/G` cho dung lượng lớn hơn. Không dùng nhầm `256ms` (đơn vị thời gian mili giây) cho kích thước.
- `maxsize` phải **không nhỏ hơn `maxchunksize`** mà JFR đã cấu hình; `maxchunksize` mặc định của JDK 21 là khoảng `12M` và có thể tùy chỉnh. Không đặt vòng lưu dữ liệu `maxsize=1m` và kỳ vọng hoạt động.

## 3. Phân biệt ba kiểu recording theo yêu cầu thực tế

### 3.1. Recording hữu hạn để điều tra một hiện tượng

Muốn đo trong hai phút, rồi tự xuất thành `.jfr`:

```bash
jcmd 12345 JFR.start name=incident settings=profile duration=2m disk=true filename=/tmp/jfr-out/incident-%p-%t.jfr
```

- `duration=2m`: hai phút sau khi recording thực sự bắt đầu, nó tự dừng. Không cần đợi ứng dụng kết thúc.
- `settings=profile`: thu nhiều sự kiện hơn `default`, phù hợp điều tra có chủ đích nhưng có thể gây overhead lớn hơn.
- `filename`: nơi ghi tệp khi recording dừng. Mẫu `%p` và `%t` được HotSpot thay bằng PID và timestamp theo tài liệu; đặt tên riêng để tránh ghi đè.
- `disk=true`: cho phép lưu chunk trên đĩa. **Khả năng ghi tệp vẫn phụ thuộc thư mục/quyền/dung lượng của JVM mục tiêu.**

Nếu tiến trình thoát **trước khi hết 2 phút**, câu lệnh phía trên chưa bật `dumponexit`. Muốn thu lại dữ liệu khi tiến trình kết thúc sớm theo đường shutdown, dùng thêm `dumponexit=true`:

```bash
jcmd 12345 JFR.start name=incident_early_exit settings=profile duration=2m disk=true dumponexit=true filename=/tmp/jfr-out/incident-exit-%p-%t.jfr
```

Không nên khởi chạy đồng thời cả hai ví dụ với cùng mục đích trong ứng dụng thật; đây là hai **cách cấu hình thay thế**. Khi bản ghi đã tự hết `duration`, nó **không còn chạy** để chờ dump-on-exit ở một thời điểm xa hơn.

### 3.2. Recording liên tục dạng lịch sử cuộn

Muốn tiến trình hoạt động nhiều giờ hoặc nhiều ngày, nhưng chỉ giữ một phần lịch sử gần nhất:

```bash
jcmd 12345 JFR.start name=service_ring settings=default disk=true duration=0s maxage=30m maxsize=256m dumponexit=true filename=/tmp/jfr-out/service-exit-%p-%t.jfr
```

Đây là lựa chọn phù hợp cho giám sát lâu dài:

- `duration=0s`: recording **tiếp tục chạy** cho tới khi được stop hoặc JVM kết thúc.
- `maxage=30m`: ưu tiên giữ dữ liệu gần nhất trong khoảng 30 phút.
- `maxsize=256m`: hạn chế lượng dữ liệu được giữ cho recording này; khi cần chỗ cho dữ liệu mới, các chunk cũ nhất bị loại bỏ.
- `settings=default`: cấu hình ít overhead hơn `profile`, được khuyến nghị cho ghi liên tục.
- `dumponexit=true`: nếu ứng dụng tắt có xử lý shutdown và bản ghi còn chạy, JFR có thể xuất dữ liệu còn giữ.

**Không suy luận:** “`maxage=30m` nghĩa recording chỉ chạy 30 phút”. Recording vẫn chạy cho tới khi dừng; dữ liệu quá cũ được loại theo chính sách retention. Cũng không suy luận “`maxsize=256m` nghĩa tổng đĩa JVM không thể vượt 256 MB”: nhiều recording, chunk đang được ghi, metadata và **tệp export** có thể làm mức sử dụng đĩa tổng thể lớn hơn.

### 3.3. Recording chỉ trong bộ nhớ

```bash
jcmd 12345 JFR.start name=brief_memory disk=false duration=30s settings=default filename=/tmp/jfr-out/brief-memory.jfr
```

Với `disk=false`, dữ liệu không được liên tục đẩy xuống repository; nó bị giới hạn bởi **bộ đệm trong bộ nhớ**, nên có thể mất các sự kiện cũ. `maxage` và `maxsize` **không có ý nghĩa quản lý đĩa** trong trường hợp này và tài liệu `jcmd` yêu cầu dùng chúng với `disk=true`. Nếu mục tiêu là giữ một “cửa sổ lịch sử” dài để dump khi sự cố xảy ra, thường phải dùng `disk=true`.

## 4. Repository là thư mục tạm, không phải file export

Khi `disk=true`, JVM ghi các chunk JFR vào một **repository tạm**. Mặc định repository thường nằm dưới thư mục temp của hệ điều hành. Trong môi trường container, temp directory có thể nằm trên storage ngắn hạn hoặc bị giới hạn dung lượng.

Có hai cách **khác nhau về thời điểm/cú pháp** để chọn thư mục:

**Cấu hình JVM đang chạy** qua `jcmd`, lý tưởng thực hiện trước khi bắt đầu recording cần thu:

```bash
jcmd 12345 JFR.configure repositorypath=/tmp/jfr-repo
jcmd 12345 JFR.configure
```

Lệnh không có tham số hiển thị cấu hình JFR hiện tại. Nếu thay repositorypath khi JVM đã ghi chunk, không giả định các chunk cũ đã được tự động di chuyển. Kiểm tra lại trạng thái thực tế của JVM đang chạy.

**Cấu hình ngay khi JVM khởi động**:

```bash
java -XX:FlightRecorderOptions=repository=/tmp/jfr-repo JfrLifecycleDemo
```

Chú ý tên option **khác nhau**:

- `jcmd <PID> JFR.configure repositorypath=...`
- `java -XX:FlightRecorderOptions=repository=...`

Cả hai đều nhắm tới nơi JVM lưu **dữ liệu tạm**. Một `filename=/tmp/jfr-out/...jfr` trong `JFR.start` hoặc `JFR.dump` là **đích xuất bản ghi**, không phải tham số đổi repository.

### Vị trí thư mục và quyền truy cập

Trong môi trường Linux, chuẩn bị trước:

```bash
mkdir -p /tmp/jfr-repo /tmp/jfr-out
```

Đây chỉ là thư mục ví dụ cho môi trường học tập. Với môi trường vận hành thật:

1. Cả hai thư mục phải **tồn tại** và có quyền ghi với **user của tiến trình Java**, không chỉ user chạy terminal `jcmd`.
2. Đường dẫn được giải quyết theo **filesystem của JVM mục tiêu**. Nếu JVM chạy trong container, `/tmp/jfr-out` bên trong container không tự động xuất hiện trên máy host; dùng volume phù hợp nếu cần giữ tệp sau khi container dừng.
3. Repository và export có thể đặt ở vùng lưu trữ khác để tránh tranh chấp dung lượng. Một lần dump thường cần **dung lượng riêng cho tệp đích** trong lúc repository vẫn còn giữ chunk.
4. Không dùng file repository tạm như nơi lưu trữ lâu dài của chứng cứ. Theo mặc định, JFR có thể **xóa các chunk repository khi JVM thoát** nếu `preserve-repository=false`. Các tệp `.jfr` đã export phải được quản lý, kiểm tra và chuyển tới nơi lưu giữ được phép.
5. Giới hạn disk quota, inode, quyền truy cập, rotation và lịch xóa file export cần được giám sát ở cấp hệ thống. `maxsize` của một recording không thay thế các kiểm soát đó.

Có thể cấu hình `preserve-repository=true` qua JFR configuration/flight recorder options khi cần điều tra dữ liệu tạm. Đây là cờ **giữ lại chunk repository**, không bảo đảm tạo ra một `.jfr` hoàn chỉnh, hợp lệ trên mọi kiểu shutdown; cách quản lý chính vẫn là xuất bản ghi rõ ràng.

## 5. Thực hành đầy đủ trên JVM Java 17+

Dùng một chương trình đơn giản chạy đủ lâu để thao tác `jcmd`. Lưu file **`JfrLifecycleDemo.java`**:

```java
public final class JfrLifecycleDemo {
    public static void main(String[] args) throws InterruptedException {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("Shutdown hook executed")));

        long pid = ProcessHandle.current().pid();
        System.out.println("PID=" + pid);

        long checksum = 0;
        for (int second = 1; second <= 240; second++) {
            byte[] bytes = new byte[64 * 1024];
            bytes[0] = (byte) second;
            checksum += bytes[0];

            if (second % 15 == 0) {
                System.out.println("t=" + second + "s checksum=" + checksum);
            }
            Thread.sleep(1_000);
        }
        System.out.println("Finished normally");
    }
}
```

Biên dịch và chạy trong **terminal A**:

```bash
javac JfrLifecycleDemo.java
java JfrLifecycleDemo
```

Dòng đầu có dạng `PID=12345`, trong đó PID là con số thực tế của JVM và **khác nhau giữa các lần chạy**. Sau 15 giây, chương trình in một dòng `t=15s checksum=...`; dấu ba chấm ở đây chỉ số checksum phụ thuộc vòng lặp, không phải output nguyên văn. Chương trình chạy khoảng 240 giây, lâu hơn nếu máy chịu tải hoặc JFR thao tác mất thời gian.

Trong **terminal B**, thay `12345` bằng PID thực tế và chuẩn bị thư mục theo mục 4.

### Bước 1 — xác định JVM và repository

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 JFR.configure repositorypath=/tmp/jfr-repo
jcmd 12345 JFR.configure
```

Lệnh `jcmd -l` liệt kê các JVM thấy được trong cùng môi trường attach, nhưng không nhất thiết nhìn thấy JVM chạy trong container/namespace khác. Phải bảo đảm đúng PID, đúng Java process và quyền truy cập.

### Bước 2 — khởi động recording dạng vòng

```bash
jcmd 12345 JFR.start name=demo_ring settings=default disk=true maxage=2m maxsize=128m dumponexit=true filename=/tmp/jfr-out/demo-exit-%p-%t.jfr
jcmd 12345 JFR.check
```

Recording này liên tục chạy theo mặc định vì không đặt `duration` (tương đương `0s`). Giới hạn `maxsize=128m` được chọn lớn hơn kích thước chunk mặc định khoảng `12M`. `JFR.check` cho phép kiểm tra recording đang chạy và xác nhận tên `demo_ring`.

### Bước 3 — xuất snapshot thủ công trong lúc recording vẫn chạy

```bash
jcmd 12345 JFR.dump name=demo_ring filename=/tmp/jfr-out/snapshot-%p-%t.jfr
jcmd 12345 JFR.check
```

`JFR.dump` **ghi tệp nhưng không dừng recording**. Nó phù hợp khi có hiện tượng spike/latency bất thường và muốn “chốt” cửa sổ dữ liệu ở thời điểm đó trong khi hệ thống vẫn tiếp tục chạy.

Muốn chỉ xuất phần gần nhất trong dữ liệu còn giữ:

```bash
jcmd 12345 JFR.dump name=demo_ring filename=/tmp/jfr-out/last-30s-%p-%t.jfr maxage=30s
```

`maxage=30s` trong lệnh **`JFR.dump`** giới hạn thời gian **của lần xuất đó**, không thay đổi `maxage=2m` của recording đã khởi động. Nếu không còn đủ 30 giây dữ liệu (mới chạy 10 giây, hoặc chunk cũ đã bị loại), tệp chỉ có dữ liệu thực sự còn khả dụng.

### Bước 4 — kiểm tra tệp export

Khi đã có file thực tế tại đường dẫn mà `jcmd` báo, dùng công cụ `jfr` của JDK **trên máy/namespace có thể truy cập file**:

```bash
jfr summary /tmp/jfr-out/snapshot-12345-2026_10_29_17_00_00.jfr
```

Tên trên là **đường dẫn minh họa**, không phải tên tệp đảm bảo sinh ra; hãy thay bằng tên thật. Lệnh `jfr summary` cho biết thời gian ghi, số lượng/loại sự kiện và các thống kê khác. Có thể mở tệp trong **JDK Mission Control** để xem timeline, CPU, allocation, GC và thread events mà cấu hình `.jfc` đã bật.

Nếu `JFR.dump` báo thành công nhưng bên host không thấy file, kiểm tra **filesystem của JVM** và volume mount trước khi cho rằng JFR không ghi dữ liệu.

### Bước 5 — kiểm chứng dump-on-exit

Khi `demo_ring` vẫn chạy, cho JVM thoát **theo đường shutdown bình thường** (để chương trình chạy hết hoặc yêu cầu dừng mềm phù hợp hệ điều hành). Sau khi tiến trình kết thúc:

- Xác nhận có file khớp mẫu `demo-exit-%p-%t.jfr` trong `/tmp/jfr-out` theo đường nhìn từ JVM.
- Chạy `jfr summary` trên **file thật** rồi ghi thời điểm bắt đầu/kết thúc và số lượng event.
- So sánh file xuất ở bước 3 với file khi thoát; file mới chỉ chứa dữ liệu còn giữ tính tới thời điểm shutdown, có thể đã loại phần đầu vì `maxage/maxsize`.

Nếu **chủ động chạy**:

```bash
jcmd 12345 JFR.stop name=demo_ring filename=/tmp/jfr-out/stopped-%p-%t.jfr
```

thì đây là **một nhánh thực hành khác**: lệnh stop kết thúc và xuất bản ghi ngay. Khi JVM thoát sau đó, `demo_ring` **không còn chạy** để xuất thêm lần nữa do `dumponexit`. Không vừa stop vừa chờ dump-on-exit cho cùng recording.

## 6. Khởi động JVM kèm cấu hình JFR từ đầu

Khi ứng dụng chạy dưới service manager, container hoặc script deploy, có thể chuẩn bị repository, retention và dump-on-exit ngay khi JVM được tạo. Ví dụ một lệnh Linux cho chương trình thực hành:

```bash
java -XX:FlightRecorderOptions=repository=/tmp/jfr-repo -XX:StartFlightRecording=name=boot_ring,settings=default,disk=true,maxage=2m,maxsize=128m,dumponexit=true,filename=/tmp/jfr-out/boot-%p-%t.jfr JfrLifecycleDemo
```

Chú ý cú pháp:

- Với `jcmd PID JFR.start`, các cặp `key=value` **cách nhau bằng khoảng trắng**.
- Với `-XX:StartFlightRecording=...`, các cặp `key=value` được **phân cách bằng dấu phẩy** trong cùng JVM option.
- Với `-XX:FlightRecorderOptions=repository=...`, `repository` là option JVM; không chuyển nguyên văn `repositorypath` từ `JFR.configure` sang đây.
- `-XX:StartFlightRecording` mặc định không giới hạn `duration`. Có thể thêm `duration=2m` khi cần bản ghi hữu hạn.
- Tên recording `boot_ring` chỉ là định danh để dùng với `jcmd PID JFR.check` / `JFR.dump name=boot_ring`.

Các đường dẫn trong ví dụ được dùng bên trong filesystem nơi tiến trình Java chạy; cần tạo và cấp quyền trước. Trong container orchestration, việc JVM bị buộc dừng sau thời gian grace quá ngắn có thể khiến dump-on-exit không hoàn tất.

### Ví dụ khởi động hữu hạn sau giai đoạn warm-up

```bash
java -XX:StartFlightRecording=name=startup_triage,delay=20s,duration=60s,settings=profile,filename=/tmp/jfr-out/startup.jfr JfrLifecycleDemo
```

Ở đây `delay=20s` đợi 20 giây sau khi chạy JVM mới bắt đầu recording; sau **60 giây thu thập**, JFR dừng và xuất tệp nếu quá trình hoàn tất. `delay` không được nhầm với `duration`: tổng thời gian kể từ lúc ứng dụng khởi động đến khi tự dừng khoảng 80 giây trong điều kiện bình thường.

## 7. `duration` và retention: vì sao chúng không thay thế nhau?

Giả sử một service chạy **8 giờ**, dùng:

```text
duration = 0s      # chạy liên tục cho tới khi stop/exit
maxage   = 30m     # chỉ giữ lịch sử gần nhất theo tuổi
maxsize  = 256m    # hạn mức dung lượng retained trên đĩa
disk     = true
```

Ở phút 10, dữ liệu còn từ lúc bắt đầu nếu chưa vượt `maxsize`. Ở giờ 8, lịch sử giữ có thể chỉ phủ tối đa 30 phút gần nhất, **thậm chí ngắn hơn** nếu tốc độ sinh event làm chạm giới hạn 256m trước. Không có cam kết “luôn lấy được 30 phút” chỉ vì đã đặt `maxage=30m`.

Ví dụ tính nhẩm đơn giản, **không phải số đo JFR thực tế**:

- Nếu dữ liệu ghi vào repository trung bình `2 MB/phút`, lịch sử 30 phút cần cỡ `60 MB`, nên `maxage` có thể là ràng buộc chặt hơn `maxsize=256m`.
- Nếu trung bình `20 MB/phút`, 30 phút cần cỡ `600 MB`, vượt `256m`; khi đó cửa sổ giữ được theo dung lượng có thể chỉ vào khoảng **12–13 phút**, trước khi tính chunk overhead.
- Nếu `duration=5m`, recording tự dừng sau 5 phút dù `maxage=1h` và `maxsize=1g`. Hai giới hạn sau không kéo dài tuổi thọ recording.

JFR lưu và loại dữ liệu theo **chunk**; ranh giới chunk, tốc độ event và nhiều recording đồng thời làm dung lượng/thời gian thực tế khác công thức tuyến tính. `maxsize` nên được xem là **ngân sách retention cho một recording**, không phải cam kết byte-by-byte rằng cả filesystem không thể vượt giới hạn. Chọn dung lượng trống đủ cho repository, các chunk đang hoạt động, file export và overhead.

### Điều gì xảy ra khi đủ chỗ rồi vẫn có sự kiện mới?

Với `disk=true`, JFR có thể loại **chunk cũ** để giữ dữ liệu mới hơn khi vượt giới hạn. Nếu chưa kịp xuất một incident, sự kiện ở cửa sổ quá cũ có thể bị loại vĩnh viễn. Khi phát hiện sự cố, **dump ngay** để chốt bằng chứng thay vì chờ tới lúc vòng retention xoay qua; tệp dump đã xuất cần có chính sách lưu trữ riêng.

## 8. Khi nào dump-on-exit hoạt động và khi nào không?

`dumponexit=true` là cơ chế best-effort dựa trên **vòng đời JVM**. Nó hữu ích nhưng không phải “bảo hiểm” cho mọi sự cố.

| Tình huống | Có thể trông đợi gì? | Cách kiểm chứng |
| --- | --- | --- |
| `main()` kết thúc bình thường trong khi recording vẫn chạy | JVM thực hiện shutdown; JFR có cơ hội xuất file | Kiểm tra file `filename` và chạy `jfr summary` |
| `System.exit(...)` trong điều kiện shutdown bình thường | Shutdown hooks có cơ hội chạy; JFR có cơ hội dump | Xác minh file hoàn chỉnh; không suy ra thành công chỉ từ log |
| Yêu cầu dừng mềm từ service manager / `SIGTERM` trên HotSpot Unix | Thường JVM bắt đầu quy trình shutdown, **nếu** được cấp đủ thời gian | Đối chiếu grace period, quyền ghi, log và file |
| `JFR.stop name=...` trước khi JVM tắt | Recording đã dừng, dump-on-exit của recording đó không còn tác dụng | Đọc file từ `JFR.stop filename`, không chờ file exit |
| `duration` đã hết và recording đã tự dừng | Không còn recording chạy để dump-on-exit sau đó | Xác nhận file đã xuất lúc tự dừng |
| `SIGKILL` / kill cưỡng bức / container bị cưỡng chế chấm dứt | Không có quy trình shutdown bảo đảm để dump | Chỉ tin file đã xuất trước đó; không trông chờ exit dump |
| JVM crash / bị mất điện / ổ đĩa đầy / file path không ghi được | Dump-on-exit **không được bảo đảm** | Kiểm tra file, dung lượng, lỗi I/O; có thể thiếu hoặc không có dữ liệu |

**Không đồng nhất** “shutdown hook của demo đã in ra” với “tệp `.jfr` chắc chắn hoàn chỉnh”. File phải thực sự tồn tại, mở đọc được và có events ở cửa sổ quan tâm.

Đặc biệt, trên container/Kubernetes, thư mục temp có thể bị xóa sau khi container mất; cần volume đủ bền và graceful termination hợp lý để thu được file. `dumponexit` không biến repository tạm thành lưu trữ bền vững.

### Chiến lược khi cần giảm nguy cơ mất dữ liệu

- Với hệ thống chạy lâu: `disk=true`, `maxage/maxsize` hữu hạn, `settings=default` và dung lượng đĩa đã tính toán.
- Khi phát hiện incident: gọi `JFR.dump` để tạo **bản xuất ngay**, không làm dừng recording.
- Khi cần kết thúc quản lý: `JFR.stop name=... filename=...` để xuất và dừng chủ động.
- Khi muốn dữ liệu cuối đời JVM: bật `dumponexit=true` từ trước, đặt `filename` nằm trong filesystem bền và kiểm chứng bằng `jfr summary` sau shutdown.
- Với crash/kill cưỡng bức: không bảo đảm thu được file mới; bản dump đã xác minh từ trước là chứng cứ đáng tin cậy hơn.

## 9. Quản lý nhiều recording và điều chỉnh cách xuất

Một JVM có thể có **nhiều recording**, ví dụ một bản ghi vòng liên tục `service_ring` và một bản ghi ngắn `incident`. Khi đó:

```bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=service_ring filename=/tmp/jfr-out/ring-snapshot.jfr
jcmd 12345 JFR.dump name=incident filename=/tmp/jfr-out/incident-snapshot.jfr
```

Tham số `name` xác định recording. Theo tài liệu `jcmd`, nếu `JFR.dump` **không** cung cấp `name` thì có thể xuất dữ liệu từ **tất cả** các recording, không phù hợp khi cần phân lập một nguồn. Mỗi recording có retention/đích xuất riêng; chi phí ghi và sức chứa tổng thể vẫn cộng dồn.

Các thao tác không tương đương:

| Thao tác | Recording còn chạy? | Dữ liệu xuất ra |
| --- | --- | --- |
| `JFR.check` | Không thay đổi | Không tạo file; xem trạng thái |
| `JFR.dump name=... filename=...` | **Có**, nếu đang chạy trước đó | Snapshot của dữ liệu còn giữ tại thời điểm dump |
| `JFR.dump ... maxage=10m` | **Có** | Phần dữ liệu gần nhất trong giới hạn xuất |
| `JFR.stop name=... filename=...` | **Không** | Ghi dữ liệu còn giữ rồi dừng recording |
| Recording đạt `duration` và có `filename` | **Không** | Tự dừng và ghi file theo cấu hình |
| JVM shutdown với `dumponexit=true`, recording còn chạy | JVM kết thúc | Cố gắng ghi file vào `filename` hoặc tên tự sinh |

Đừng nhầm `JFR.configure` (cấu hình chung JFR của JVM, như repository path) với `JFR.start` (các tùy chọn riêng recording) hoặc `JFR.dump` (tham số riêng của **một lần xuất**). Cũng không nhầm `JFR.dump` với `GC.heap_dump`: hai công cụ tạo định dạng/loại bằng chứng khác nhau.

## 10. Kiểm tra nhanh từ ghi nhận đến kết luận

Trước khi thu:

1. **JDK/collector/PID:** `java -version`, `jcmd -l`, `jcmd PID VM.version`; dùng `jcmd` tương thích và quyền truy cập phù hợp.
2. **Mục tiêu:** đo sự cố 1–5 phút hay giữ vòng 1–6 giờ? Chọn `duration` riêng với `maxage`.
3. **Retention:** đặt cả `maxage` và `maxsize` nếu cần giới hạn cả **tuổi** và **dung lượng**. Bảo đảm `maxsize >= maxchunksize`.
4. **Thư mục:** repository và output có cùng filesystem với JVM, có quyền ghi, có dung lượng và volume mount phù hợp.
5. **Cấu hình sự kiện:** `default` cho continuous, `profile` cho khoảng điều tra ngắn nếu cần dữ liệu chuyên sâu hơn.
6. **Khi thoát:** nếu bật `dumponexit`, xác định chính xác file đích và grace period của service manager.

Trong lúc thu:

1. `jcmd PID JFR.check` để thấy recording đang chạy; không chỉ dựa vào việc lệnh start đã được gửi.
2. Nếu cần khóa dữ liệu gần thời điểm sự cố, `JFR.dump` và lưu lại **tên file mà JVM báo**.
3. Quan sát dung lượng repository, số recording đang chạy, disk space, biến động event rate và chi phí CPU/latency.
4. Khi cấu hình retention thay đổi giữa phiên, ghi lại thời điểm và giá trị để tránh so sánh sai.

Sau khi thu:

1. `jfr summary file.jfr`; xác minh file mở đọc được, có các loại event và khoảng thời gian đúng.
2. Đối chiếu số phút thực sự có dữ liệu với `maxage`/`maxsize` đã chọn; nếu ngắn hơn dự tính, xem event rate và chunk retention.
3. Mở bằng JDK Mission Control khi cần phân tích profile và timeline.
4. Lưu file theo chính sách của hệ thống vì các event có thể chứa tên thread, method, path, tham số hoặc thông tin ứng dụng cần kiểm soát truy cập.
5. Xóa/rotate **các tệp đã export** bằng cơ chế quản lý lưu trữ riêng; đừng kỳ vọng `maxsize` của repository tự dọn tất cả file đó.

## 11. Tình huống thực tế và cách lựa chọn

### Tình huống A — service production chạy cả tuần

**Yêu cầu:** khi có sự cố, có thể lấy khoảng 30 phút gần nhất; không muốn repository giữ dữ liệu vô hạn.

Cấu hình mẫu:

```bash
jcmd 12345 JFR.start name=prod_ring settings=default disk=true duration=0s maxage=30m maxsize=256m dumponexit=true filename=/tmp/jfr-out/prod-exit-%p-%t.jfr
```

Khi incident vừa xảy ra:

```bash
jcmd 12345 JFR.dump name=prod_ring filename=/tmp/jfr-out/prod-incident-%p-%t.jfr
```

**Điều phải kiểm chứng:** “khoảng 30 phút” là mục tiêu, không phải bảo đảm nếu `maxsize` bị chạm sớm. Dữ liệu xuất sẽ chỉ gồm những chunk còn lại.

### Tình huống B — CPU spike đúng lúc startup

**Yêu cầu:** bỏ qua 20 giây warm-up, ghi chi tiết 1 phút rồi tự xuất.

```bash
java -XX:StartFlightRecording=name=startup_spike,delay=20s,duration=60s,settings=profile,filename=/tmp/jfr-out/startup-spike.jfr JfrLifecycleDemo
```

Giải thích: recording bắt đầu sau `delay=20s` và **chạy 60 giây**. `maxage` và `maxsize` không phải cách đặt khoảng bắt đầu/kết thúc của recording.

### Tình huống C — container thường bị kill do timeout

**Yêu cầu:** không mất bằng chứng khi quá trình shutdown có thể bị cưỡng bức.

Giải pháp vận hành: dùng repository trên volume phù hợp, đặt giới hạn retention, **dump chủ động** trước các lần thay đổi/thu hồi instance khi có thể, kiểm tra `jfr summary`, đồng thời vẫn bật `dumponexit=true` như một đường thu bổ sung. Không tuyên bố dump-on-exit chắc chắn chạy khi `SIGKILL` hoặc container bị xóa ngay.

### Tình huống D — ổ đĩa đầy dù đã đặt `maxsize=256m`

Các câu hỏi cần xác minh:

- Có nhiều recording chạy đồng thời không?
- Các tệp `.jfr` export cũ có bị để lại không?
- Repository và export có nằm cùng partition/volume không?
- Có chunk tạm, dữ liệu ứng dụng hoặc log khác sử dụng đĩa không?
- Tốc độ event có tăng dẫn đến ghi/rotate chunk nhanh bất thường không?

**Kết luận đúng:** `maxsize` là giới hạn của dữ liệu retention cho một recording, **không phải quota toàn bộ JVM, filesystem hay thư mục xuất**.

## 12. Sai lầm phổ biến

1. **Dùng `maxage=30m` như `duration=30m`:** dữ liệu cũ bị loại, còn recording vẫn chạy.
2. **Dùng `duration=0s` nhưng không giới hạn disk retention:** service hoạt động lâu có thể tạo nhu cầu lưu trữ lớn.
3. **Đặt `maxsize` nhỏ hơn `maxchunksize`:** cấu hình không hợp lệ.
4. **Cho rằng `maxage/maxsize` giới hạn cả tệp `.jfr` đã export:** file kết quả cần quản lý riêng.
5. **Đặt `maxage/maxsize` với `disk=false`:** không đáp ứng mục tiêu giữ lịch sử repository; kiểm tra tài liệu/đầu ra command.
6. **Nhầm repository với filename:** chunk tạm khác file dùng để chuyển cho JMC.
7. **Dùng tên tham số `repositorypath` trong `-XX:FlightRecorderOptions`:** tên option khi khởi động là `repository`.
8. **Nhập dấu phẩy giữa tham số `jcmd JFR.start`:** dấu phẩy dành cho JVM flag `-XX:StartFlightRecording`, còn `jcmd` dùng khoảng trắng.
9. **Chạy `JFR.dump` rồi tưởng recording đã ngừng:** nó vẫn tiếp tục, kiểm tra bằng `JFR.check`.
10. **Gọi `JFR.stop` trước shutdown rồi chờ dump-on-exit:** không còn recording chạy để dump.
11. **Tin chắc dump-on-exit khi crash/kill cưỡng bức:** không có bảo đảm thực thi shutdown.
12. **Không kiểm tra tên file thực tế có `%p/%t`:** dễ nhìn nhầm vị trí hoặc phiên recording.
13. **Không kiểm tra volume/container path:** file có thể nằm bên trong container thay vì filesystem của người chạy `jcmd`.
14. **Không lưu timestamp/workload:** mất tương quan với thời điểm xuất hiện sự cố; có file JFR nhưng không biết cần tìm đâu.
15. **Không kiểm tra file bằng `jfr summary`:** log “Started recording” chỉ chứng minh đã bắt đầu, không chứng minh đã xuất file.
16. **Dùng `profile` liên tục mà không đo overhead:** profile chứa nhiều dữ liệu hơn default; cân nhắc tải và mục tiêu.

## 13. Bài tập tự kiểm tra

**Câu 1.** Một recording chạy 12 giờ với `duration=0s, maxage=1h, maxsize=512m, disk=true`. Sau 12 giờ, có thể dump đủ 12 giờ dữ liệu không?

**Trả lời:** Không thể kỳ vọng. Chỉ có các chunk còn được giữ theo hai giới hạn; cửa sổ lịch sử tối đa khoảng một giờ và có thể ngắn hơn vì chạm `maxsize`.

**Câu 2.** Recording có `duration=2m` và `dumponexit=true`. JVM còn sống 5 giờ. Khi JVM thoát sau 5 giờ, bản ghi sẽ ghi thêm 5 giờ dữ liệu không?

**Trả lời:** Không. Recording tự dừng sau 2 phút; dump-on-exit không kéo dài hay tự khởi động lại bản ghi.

**Câu 3.** Sau `JFR.dump name=prod_ring filename=...`, có cần dùng `JFR.start` để tiếp tục vòng lịch sử không?

**Trả lời:** Không. `JFR.dump` không stop recording; xác minh bằng `JFR.check`.

**Câu 4.** `dumponexit=true` nhưng JVM bị `SIGKILL`. Có bảo đảm tạo tệp mới không?

**Trả lời:** Không. Cần xem những export đã tạo trước đó và kiểm tra khả năng đọc của chúng; không phụ thuộc vào shutdown hook.

**Câu 5.** JVM chạy trong container; `jcmd` báo export `/tmp/jfr-out/test.jfr` thành công nhưng host không thấy. Lỗi do JFR?

**Trả lời:** Chưa đủ cơ sở. Đường dẫn do JVM/container giải quyết; kiểm tra namespace, volume mount và file thực tế bên trong container.

**Thực hành cuối bài:** Dùng `JfrLifecycleDemo`, tạo một recording hữu hạn `duration=30s` và một recording liên tục `maxage=2m maxsize=128m` trong các lần chạy riêng. Với recording liên tục, chụp `JFR.dump` khi đang chạy rồi để JVM tự kết thúc. Ghi tên tệp, số liệu `jfr summary` và giải thích rõ **điểm dừng**, **cửa sổ retention**, **nơi chứa chunk tạm** và **đường xuất tệp cuối**. Hoàn thành khi có thể dự đoán và kiểm chứng cả năm khái niệm mà không nhầm lẫn.

## 14. Nguồn tài liệu chính thức

- [Oracle JDK 21 — `jcmd`: JFR.configure / JFR.start / JFR.dump / JFR.stop / JFR.check](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `java`: `-XX:StartFlightRecording` và `-XX:FlightRecorderOptions`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle JDK 21 — `jfr`: `summary`, `print` và xử lý tệp](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [Oracle JDK 21 — `jdk.jfr.Recording`: duration, retention, dump-on-exit](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Oracle — Flight Recorder Configurations: default.jfc và profile.jfc](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html).

**Nguyên tắc ghi nhớ:** `duration` quyết định *khi nào recording dừng*; `maxage/maxsize` quyết định *lịch sử còn giữ*; `repository` quyết định *chunk tạm nằm ở đâu*; `JFR.dump` quyết định *lúc nào xuất một bản sao*; và `dumponexit` là *cơ hội xuất cuối khi JVM shutdown bình thường*, cần kiểm chứng bằng file thực tế.
