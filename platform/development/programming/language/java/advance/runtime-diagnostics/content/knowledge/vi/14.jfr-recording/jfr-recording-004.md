# 14.4. JFR.check, JFR.dump, JFR.stop và quản lý nhiều recording

Trong Java Flight Recorder (JFR), **recording** là một phiên ghi các sự kiện về hoạt động của JVM và ứng dụng: CPU, thread, garbage collection, allocation, I/O hoặc sự kiện do ứng dụng tự định nghĩa. Khi một dịch vụ đang chạy, người vận hành thường cần ba thao tác: **xem phiên nào còn hoạt động**, **xuất dữ liệu đã ghi ra file**, và **kết thúc đúng phiên**. Bộ lệnh `jcmd` phục vụ ba việc đó bằng `JFR.check`, `JFR.dump` và `JFR.stop`.

Tình huống quan trọng là một JVM có thể có **nhiều recording đồng thời**. Ví dụ: một recording nền chạy lâu với `settings=default`, trong khi một recording điều tra ngắn bật `settings=profile`. Dùng sai `name` có thể xuất nhầm dữ liệu, vô tình trộn dữ liệu từ nhiều phiên, hoặc dừng recording đang dùng để giám sát.

Mục tiêu của bài:
- Phân biệt chính xác hành vi và vòng đời của `JFR.check`, `JFR.dump` và `JFR.stop`.
- Thực hiện được thao tác trên **một PID Java cụ thể** và chọn đúng recording bằng `name`.
- Hiểu các tham số `verbose`, `filename`, `maxage`, `maxsize`, `begin` và `end` khi cần.
- Quản lý hai recording song song, biết khi nào xuất snapshot và khi nào kết thúc để lưu artifact.
- Kiểm tra file `.jfr` bằng công cụ của JDK và xử lý lỗi phổ biến trên host/container.

## 1. Mô hình vòng đời: ghi, quan sát, chụp snapshot, kết thúc

Một luồng thao tác điển hình:

~~~text
JVM đang chạy
    |
    +-- JFR.start name=baseline ------> [baseline: RUNNING] ----+
    |                                                         |
    +-- JFR.start name=incident ------> [incident: RUNNING] --+ |
    |                                                       | |
    +-- JFR.check --------------------> chỉ xem trạng thái  | |
    |                                                       | |
    +-- JFR.dump name=incident -------> ghi incident.jfr   | |  (incident vẫn RUNNING)
    |                                                       | |
    +-- JFR.stop name=incident -------> [incident kết thúc] + |
    |                                                         |
    +-- JFR.check --------------------> baseline vẫn RUNNING --+
    |
    +-- JFR.stop name=baseline -------> [baseline kết thúc]
~~~

| Lệnh | Tác dụng | Có chấm dứt recording không? | File được tạo khi nào? |
| --- | --- | --- | --- |
| `JFR.start` | Tạo/bắt đầu một recording | Không; khởi đầu phiên | Có thể chỉ định đích ghi khi kết thúc hoặc dump |
| `JFR.check` | Xem danh sách và trạng thái/thiết lập recording | **Không** | Không |
| `JFR.dump` | Ghi bản sao dữ liệu đã thu thập ra file `.jfr` | **Không**; recording tiếp tục chạy | Ngay khi dump thành công |
| `JFR.stop` | Dừng một recording đã chỉ định | **Có**, cho riêng recording được chọn | Nếu truyền `filename` để lưu dữ liệu lúc dừng |

Phân biệt hai sản phẩm: **recording** là một phiên có vòng đời trong JVM; **file `.jfr`** là artifact của một lần dump/stop. Một recording có thể tạo nhiều file snapshot khác nhau mà vẫn hoạt động. Ngược lại, một file đã ghi không tự động là một recording đang chạy.

JFR thường có overhead thấp với cấu hình phù hợp, nhưng không phải không có chi phí: `settings=profile` và các sự kiện chi tiết có thể phát sinh overhead cao hơn `default`. Hãy xác nhận bản phân phối JDK/HotSpot đích hỗ trợ lệnh nào qua chính JVM đó.

## 2. Chuẩn bị: đúng JVM, đúng quyền, đúng thư mục

Trong ví dụ bên dưới, PID minh họa là **12345**. Bạn **phải thay** bằng PID của tiến trình thực tế; lệnh không dùng được trên một PID không tồn tại. Trên máy có JDK:

~~~bash
jcmd -l
jcmd 12345 help JFR.check
jcmd 12345 help JFR.dump
jcmd 12345 help JFR.stop
~~~

- `jcmd -l` liệt kê những Java process mà công cụ hiện có thể quan sát; không cam kết liệt kê JVM ở mọi process namespace/container.
- `jcmd 12345 help ...` hiển thị cú pháp chính xác của **JVM đích**; tên tùy chọn có thể thay đổi giữa các JDK/JVM.
- Thao tác attach thường cần chạy trên cùng máy, với user/group và điều kiện attach phù hợp. Nếu attach bị tắt, PID không nhìn thấy hoặc quyền khác, `jcmd` có thể không kết nối được.
- Trên Linux/container, nên dùng đường dẫn tuyệt đối có thư mục đã tồn tại, ví dụ `/var/tmp/jfr/`. `filename` được JVM đích diễn giải trong filesystem **nơi tiến trình Java chạy**, không nhất thiết là filesystem của terminal gọi `jcmd`.
- File JFR có thể chứa class/method names, stack traces, system properties, đường dẫn và thông tin nhạy cảm của ứng dụng. Bảo vệ quyền đọc, phương thức truyền và thời hạn lưu trữ.

**Chuẩn bị thư mục** theo quyền của user chạy JVM, có dung lượng dự phòng và tên file riêng biệt từng lần chụp. Ví dụ các lệnh sau giả định thư mục `/var/tmp/jfr/` đã tồn tại, writable. Với Windows dùng đường dẫn tương ứng như `C:/jfr/incident.jfr` (sau khi tạo thư mục).

## 3. `JFR.check`: xem recording nào đang hoạt động

Cú pháp cơ bản:

~~~bash
jcmd 12345 JFR.check
~~~

Khi không có tham số, HotSpot JDK 21 hiển thị thông tin các recording đang hoạt động. Kết quả thường có **recording ID**, **name**, trạng thái và những thông tin cấu hình/thời gian liên quan. Giá trị cụ thể tùy JDK và thời điểm, nên không dùng một ví dụ stdout cố định để suy ra PID/name.

Chỉ kiểm tra một recording:

~~~bash
jcmd 12345 JFR.check name=baseline
~~~

Kiểm tra cùng các **thiết lập event**:

~~~bash
jcmd 12345 JFR.check name=baseline verbose=true
~~~

Tham số `verbose` mặc định `false`; bật `true` để xem cấu hình sự kiện chi tiết, rất hữu ích khi thắc mắc tại sao một loại event có/không xuất hiện. Đầu ra có thể khá dài. Lệnh chỉ đọc trạng thái, **không phải yêu cầu JVM tạo file `.jfr` hoặc dừng phiên**.

Một chiến lược an toàn khi có nhiều recording: **luôn gọi `JFR.check` ngay trước `dump` hoặc `stop`**, xác nhận chính xác `name`; sau khi `stop`, gọi lại để kiểm tra recording khác vẫn chạy.

Nếu hiện “No available recordings” thì không có recording đang hoạt động mà lệnh có thể liệt kê trên JVM này. Đây không phải lỗi của lệnh `check` và cũng không chứng minh ứng dụng chưa từng có file `.jfr` trước đó.

## 4. `JFR.dump`: xuất dữ liệu mà vẫn tiếp tục thu thập

Lệnh để xuất một recording có tên:

~~~bash
jcmd 12345 JFR.dump name=baseline filename=/var/tmp/jfr/baseline-snapshot.jfr
~~~

Khi thành công, JVM ghi dữ liệu recording đang có vào file. **`baseline` vẫn RUNNING sau lệnh này**. Bạn có thể chụp nhiều snapshot tại các thời điểm khác nhau, mỗi lần dùng tên file mới, rồi tiếp tục thu event.

Lệnh không chỉ định `name`:

~~~bash
jcmd 12345 JFR.dump filename=/var/tmp/jfr/all-recordings.jfr
~~~

Theo tài liệu HotSpot JDK 21, khi **không có `name`**, `JFR.dump` xuất dữ liệu từ **tất cả recordings**. Đây là hành vi có chủ đích của công cụ nhưng thường gây bất ngờ nếu mục tiêu chỉ là một phiên. Với nhiều phiên đồng thời, hãy **chỉ định `name`** để xác định scope của lần xuất. Ngay cả khi đã lọc theo tên, cấu hình event của các recording chạy song song có thể tác động đến dữ liệu được thu toàn JVM; đừng giả định chúng hoàn toàn độc lập về overhead và tập event.

### 4.1. `filename` và định danh artifact

`filename` có thể là đường dẫn file hoặc thư mục để JVM tự tạo tên. Không truyền `filename`, JVM cũng có thể tự sinh tên từ PID/thời điểm theo tài liệu JDK 21, nhưng vận hành dễ kiểm soát hơn khi chỉ định đường dẫn đầy đủ. JDK 21 hỗ trợ token `%p` (PID) và `%t` (timestamp) trong tên file; chúng do lệnh JFR xử lý.

Ví dụ:

~~~bash
jcmd 12345 JFR.dump name=baseline filename=/var/tmp/jfr/baseline-%p-%t.jfr
~~~

Đây là snapshot mới, **không phải thêm dữ liệu vào một file `.jfr` đã có**. Không lặp các lần dump vào cùng tên file nếu cần giữ lịch sử; tên theo thời gian cũng giúp so sánh.

### 4.2. `maxage` và `maxsize`: lọc dung lượng dump, khác giới hạn lưu trữ

Ví dụ chỉ lấy tối đa năm phút gần nhất từ dữ liệu **còn được giữ lại**:

~~~bash
jcmd 12345 JFR.dump name=baseline maxage=5m filename=/var/tmp/jfr/baseline-last5m.jfr
~~~

Ví dụ thêm giới hạn lượng dữ liệu dump:

~~~bash
jcmd 12345 JFR.dump name=baseline maxsize=64m filename=/var/tmp/jfr/baseline-bounded.jfr
~~~

- `JFR.dump maxage=5m` giới hạn phạm vi thời gian xuất, **không kéo dài thời gian lưu của recording**.
- `JFR.dump maxsize=64m` là giới hạn cho dữ liệu được xuất trong lần dump, **khác** `JFR.start maxsize=...` dùng cho chính sách dữ liệu được giữ trong recording.
- Nếu recording chỉ giữ dữ liệu của 10 phút gần đây, việc yêu cầu dump 1 giờ **không khôi phục** dữ liệu đã bị loại khỏi vùng lưu trữ.
- Các giới hạn và chunk boundary có thể ảnh hưởng lượng dữ liệu thực tế; không dùng `maxsize` như cam kết file sau khi ghi phải có chính xác số byte đó.

### 4.3. `begin` và `end`: chọn khoảng thời gian

JDK 21 còn cho phép lọc theo điểm bắt đầu/kết thúc của **timestamp event** trong dữ liệu:

~~~bash
jcmd 12345 JFR.dump name=baseline begin=-15m filename=/var/tmp/jfr/baseline-15m.jfr
~~~

`begin`/`end` hỗ trợ thời gian theo các kiểu có thể parse bởi `LocalTime`, `LocalDateTime`, `Instant`, hoặc cách viết tương đối bằng số âm với hậu tố `s`, `m`, `h`, ví dụ `begin=-30s`. Khi cần một khoảng tuyệt đối, kiểm tra timezone và thời gian máy đích; mốc `end` cũng phải phù hợp với dữ liệu thực tế.

**Không hiểu sai:** `begin=-15m` không yêu cầu “khởi động recording từ 15 phút trước”. Nó chỉ **chọn phần lịch sử vẫn còn sẵn** trong recording đang chạy.

### 4.4. Tác động khi dump

`JFR.dump` được tài liệu JDK 21 phân loại impact thấp ở chế độ thông thường, nhưng nó vẫn tạo I/O và có thể chiếm dung lượng đĩa. Tùy chọn `path-to-gc-root=true` yêu cầu thông tin đường tới GC roots khi dump, có thể làm ứng dụng tạm dừng; chỉ bật khi đang điều tra leak cụ thể và hiểu chi phí. Không biến thao tác định kỳ thông thường thành dump liên tục không giới hạn file.

## 5. `JFR.stop`: dừng đúng recording và lưu dữ liệu cuối cùng

Dùng `name` để chọn recording cần kết thúc và `filename` để lưu artifact cuối:

~~~bash
jcmd 12345 JFR.stop name=incident filename=/var/tmp/jfr/incident-final.jfr
~~~

Sau khi thành công, phiên `incident` ngừng ghi. Recording khác (ví dụ `baseline`) **không bị dừng theo**. Một recording đã dừng không được khởi động lại như cùng một phiên; nếu cần tiếp tục thu dữ liệu thì tạo recording mới qua `JFR.start`.

Tài liệu `jcmd` JDK 21 nêu rõ **nếu không truyền `name` thì không recording nào bị stop**. Đồng thời `filename` xác định nơi lưu dữ liệu khi stop; tài liệu cảnh báo trường hợp không có đường dẫn thì dữ liệu recording có thể bị bỏ. Vì vậy, **khi cần giữ bằng chứng, luôn ghi rõ cả `name` và `filename`**, kể cả trước đó đã dump một snapshot.

Ví dụ không nên dùng khi bạn muốn lưu bằng chứng cuối:

~~~bash
jcmd 12345 JFR.stop name=incident
~~~

Lệnh trên vẫn nhằm kết thúc `incident` nhưng không chỉ định file xuất tại thời điểm stop; đừng trông chờ có artifact mới. Những file `.jfr` do các lần `dump` trước tạo ra vẫn là artifact riêng và không bị “hoàn tác” chỉ vì recording đã dừng.

**Dừng recording ≠ dừng JVM.** `JFR.stop` quản lý phiên quan sát, không kết thúc tiến trình Java. Chạy `JFR.check` để xác minh sau thao tác, thay vì chỉ dựa vào việc lệnh trả về không có lỗi.

## 6. Kịch bản hai recording đồng thời: baseline và điều tra

Một phương án hợp lý là giữ recording nền ít chi tiết, đồng thời chạy một recording `profile` trong khoảng ngắn. Kịch bản dưới đây mô tả **một JVM duy nhất** với PID 12345; mọi lệnh đều tác động đến PID đó.

### Bước A — khởi tạo hai recording với tên riêng biệt

~~~bash
jcmd 12345 JFR.start name=baseline settings=default disk=true maxage=1h maxsize=256m
jcmd 12345 JFR.start name=incident settings=profile disk=true maxage=15m maxsize=128m
~~~

- `name=baseline` và `name=incident` là định danh dùng cho các lệnh quản trị sau. Tên rõ nghĩa và duy nhất giúp tránh chọn nhầm.
- `settings=default` là cấu hình cân bằng để theo dõi lâu; `profile` thu chi tiết hơn, có thể tăng overhead và dữ liệu. Chọn cấu hình theo mục tiêu, đừng mặc nhiên để profile chạy không giới hạn.
- `disk=true` cho phép ghi dữ liệu liên quan xuống disk khi recording; `maxage` và `maxsize` giới hạn lượng dữ liệu được giữ để không tích lũy vô hạn. Đây là thông số **retention**, không đồng nghĩa “sau đúng một giờ recording tự dừng”.
- Nếu chủ động muốn recording tự dừng sau một khoảng thời gian, `JFR.start` có `duration=...`; đừng dùng `duration` trong kịch bản mà bạn cần chủ động điều khiển `JFR.stop` ở các bước sau.

### Bước B — xác nhận cả hai

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.check name=incident verbose=true
~~~

Kỳ vọng logic: hai recording đang hoạt động, mỗi recording có name/ID và cấu hình riêng. Đầu ra JFR được JVM sinh theo runtime nên số ID, thời điểm và dung lượng là **động**, không sao chép một kết quả cứng từ ví dụ.

### Bước C — xuất hai snapshot độc lập theo tên

~~~bash
jcmd 12345 JFR.dump name=baseline maxage=5m filename=/var/tmp/jfr/baseline-5m.jfr
jcmd 12345 JFR.dump name=incident filename=/var/tmp/jfr/incident-snapshot.jfr
jcmd 12345 JFR.check
~~~

Sau khi dump thành công, **cả hai recording vẫn có thể tiếp tục RUNNING**. Tên output tách biệt giúp so sánh các mục tiêu điều tra. Không dùng `JFR.dump` không kèm name nếu yêu cầu chỉ lấy `incident`.

### Bước D — stop riêng recording điều tra

~~~bash
jcmd 12345 JFR.stop name=incident filename=/var/tmp/jfr/incident-final.jfr
jcmd 12345 JFR.check
~~~

Ở lần kiểm tra kế tiếp, `incident` đã kết thúc; `baseline` vẫn được duy trì. File `incident-snapshot.jfr` và `incident-final.jfr` đều có thể tồn tại, nhưng chúng **không đồng nghĩa hai phiên**: đó là hai artifact trong vòng đời của một recording.

### Bước E — khi thực sự không cần baseline nữa

~~~bash
jcmd 12345 JFR.dump name=baseline maxage=5m filename=/var/tmp/jfr/baseline-last5m.jfr
jcmd 12345 JFR.stop name=baseline filename=/var/tmp/jfr/baseline-final.jfr
jcmd 12345 JFR.check
~~~

Đây là bước **tùy mục tiêu vận hành**; trong nhiều hệ thống, recording nền nên tiếp tục hoạt động để phục vụ điều tra sau này. Nếu dừng cả hai, `JFR.check` có thể báo không còn recording nào.

### Quan trọng: nhiều recording không đồng nghĩa hai JVM độc lập

Mỗi recording có **tên, vòng đời, thiết lập và phạm vi dump riêng**, nhưng tất cả chạy **trên cùng JVM** và chia sẻ cơ chế thu thập event của JFR. Khi các recording có thiết lập khác nhau, một event được bật bởi một recording có thể ảnh hưởng dữ liệu có sẵn/chi phí thu thập trong bối cảnh recording khác. Không lấy `settings=default` của baseline để đảm bảo tuyệt đối rằng file baseline chỉ chứa đúng những event được liệt kê trong profile đó khi recording `profile` hoạt động song song. Kiểm tra file thực tế bằng `jfr summary`/`jfr print`.

## 7. Kiểm tra file `.jfr` sau `dump` và `stop`

Trên máy/volume nơi JVM tạo artifact:

~~~bash
ls -lh /var/tmp/jfr/incident-snapshot.jfr
ls -lh /var/tmp/jfr/incident-final.jfr
jfr summary /var/tmp/jfr/incident-final.jfr
~~~

`jfr summary`, thuộc JDK, đọc thống kê file `.jfr` như thời gian ghi, loại event và số lượng/kích thước event. Nếu công cụ không mở được file, hãy xác minh đúng đường dẫn, quyền, file size, tính toàn vẹn và phiên bản parser. Đừng kết luận thành công chỉ vì tên file xuất hiện nếu file rỗng hoặc hỏng.

Có thể lọc sự kiện theo tên:

~~~bash
jfr print --events jdk.CPULoad /var/tmp/jfr/incident-final.jfr
~~~

Lưu ý: dữ liệu chỉ xuất hiện nếu loại event đó được bật, thực sự phát sinh, còn nằm trong khoảng ghi giữ và có trong artifact đã xuất. Một dòng `jfr print` trống **không tự chứng minh JVM không có hoạt động CPU**.

Ngoài CLI, có thể mở artifact bằng **Java Mission Control (JMC)** để xem biểu đồ theo thời gian, thread, GC, CPU hoặc allocation events. Khi so hai file, nhớ đối chiếu recording name/ID, time window và settings; khác nhau về file size có thể do duration hoặc event settings, không nhất thiết do workload.

**JFR không phải heap dump HPROF.** File `.jfr` là bản ghi event theo thời gian, còn `.hprof` là snapshot đồ thị đối tượng trên heap. `JFR.dump` và `GC.heap_dump` khác dữ liệu, độ nặng và mục tiêu phân tích; không thay thế lẫn nhau.

## 8. Ví dụ Java 17+ để luyện tập với `jcmd`

Chương trình dưới đây cố tình tồn tại khoảng hai phút, tạo một **custom JFR event** mỗi giây để người học có thể attach vào tiến trình và thực hành quản lý hai recording. Nó là mã độc lập, biên dịch được trên **JDK 17+ có module `jdk.jfr`**.

Lưu nguyên chương trình vào **`JfrRecordingLab.java`**:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

public class JfrRecordingLab {
    @Name("lab.WorkUnit")
    @Label("Work Unit")
    static class WorkUnit extends Event {
        @Label("Iteration")
        int iteration;
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());
        for (int i = 1; i <= 120; i++) {
            WorkUnit event = new WorkUnit();
            event.iteration = i;
            event.begin();
            Thread.sleep(1_000L);
            event.end();
            event.commit();

            if (i % 30 == 0) {
                System.out.println("Completed=" + i);
            }
        }
        System.out.println("Done");
    }
}
~~~

**Terminal A** — biên dịch, chạy chương trình:

~~~bash
javac JfrRecordingLab.java
java JfrRecordingLab
~~~

Ví dụ các dòng do chương trình tự in:

~~~text
PID=<PID thực tế của lần chạy>
Completed=30
Completed=60
Completed=90
Completed=120
Done
~~~

Dòng `PID=...` chứa số nguyên do hệ điều hành cấp và thay đổi ở mỗi lần chạy. Các dòng `Completed=...` xuất hiện mỗi 30 lần lặp; nếu bạn stop chương trình sớm hoặc tiến trình bị gián đoạn, một số dòng sẽ không xuất hiện.

**Terminal B** — trong lúc chương trình còn chạy, thay `12345` bằng PID đã in. Dùng directory có thể ghi:

~~~bash
jcmd 12345 JFR.start name=lab-baseline settings=default disk=true maxage=5m maxsize=64m
jcmd 12345 JFR.start name=lab-incident settings=profile disk=true maxage=5m maxsize=64m
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=lab-incident filename=/var/tmp/jfr/lab-incident.jfr
jcmd 12345 JFR.stop name=lab-incident filename=/var/tmp/jfr/lab-incident-final.jfr
jcmd 12345 JFR.check
jcmd 12345 JFR.stop name=lab-baseline filename=/var/tmp/jfr/lab-baseline-final.jfr
~~~

Chạy các lệnh này **trước khi chương trình in `Done`**; nếu chương trình đã kết thúc thì PID không còn attach được. Nếu muốn thử lặp lại, chạy Java lần nữa và lấy PID mới.

Sau đó:

~~~bash
jfr summary /var/tmp/jfr/lab-incident-final.jfr
jfr print --events lab.WorkUnit /var/tmp/jfr/lab-incident-final.jfr
~~~

Nếu recording đang chạy trong khi `WorkUnit` được commit và custom event có hiệu lực, file có thể chứa các event mang tên `lab.WorkUnit`, kèm trường `iteration`. Số lượng event **phụ thuộc thời điểm start/dump/stop**; không có stdout số cố định của `jcmd` hay `jfr`. Cấu hình nào thực sự kích hoạt event có thể kiểm tra bằng `JFR.check name=lab-incident verbose=true` và metadata trong file.

## 9. Những lỗi thao tác rất dễ gặp

| Hiện tượng / nhầm lẫn | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| `JFR.check` báo không có recording | Recording chưa start, đã stop, hoặc đang hỏi sai PID | Kiểm tra đúng PID và start khi được phép |
| `JFR.dump` xong mà check vẫn thấy recording | **Đây là hành vi đúng**: dump không stop | Nếu muốn dừng, gọi `JFR.stop name=...` |
| File chứa event không mong muốn | Dump không chỉ định `name` hoặc nhiều recording làm thay đổi tập event thu thập | Chọn `name`; xem `verbose=true`, thống kê file và các recording chạy đồng thời |
| Không còn dữ liệu cũ trong dump | `maxage`/`maxsize` khi start đã loại dữ liệu cũ; dump muộn | Tăng retention cho lần thu sau, chụp kịp thời; không thể phục hồi dữ liệu đã mất |
| `JFR.stop` không dừng recording nào | Không truyền `name` hoặc chọn sai name | Gọi `JFR.check`, dùng đúng `name` |
| Dừng xong không thấy artifact cuối | Không chỉ định `filename` hoặc nhầm filesystem | Dùng `JFR.stop name=... filename=/đường/dẫn/...jfr` và kiểm tra file ở JVM đích |
| `jcmd` attach lỗi | Sai PID, thiếu quyền, process đã thoát, khác process namespace hoặc attach bị tắt | Xác minh host/user/PID/runtime; thao tác trong đúng namespace |
| File ghi thất bại | Thư mục không tồn tại, sai quyền, disk/quota thiếu hoặc tên đụng file cũ | Tạo directory có quyền ghi, chọn tên file mới, theo dõi dung lượng |
| `JFR.dump` có dữ liệu ít hơn dự kiến | Khoảng thời gian lọc, event settings hoặc recording mới start | So timestamps, `maxage`, `begin`, loại event và thời điểm start |
| JFR làm tăng tải | Profile/sự kiện chi tiết, nhiều recording hoặc dump quá thường xuyên | Giới hạn duration/retention, quan sát overhead và giảm mức chi tiết |
| Nhiều phiên nhưng chỉ muốn dừng một phiên | Nhầm recording name/ID, automation chọn sai phiên | Dùng tên duy nhất, check trước và sau stop, không stop theo suy đoán |

Một số lệnh có tham số theo phiên bản JVM; hãy dùng `jcmd <PID> help JFR.dump` và các biến thể `JFR.check`/`JFR.stop` để xác nhận trên runtime cụ thể. Tài liệu tại đây đối chiếu **HotSpot JDK 21**; các JVM hoặc JDK khác có thể khác nhau.

## 10. Thực hành lựa chọn thao tác theo yêu cầu

**Tình huống A:** Dịch vụ có baseline đang chạy; bạn cần file sự kiện của 5 phút gần nhất và vẫn phải giám sát tiếp. → `JFR.check` xác nhận tên, sau đó **`JFR.dump name=baseline maxage=5m filename=...`**. Không stop.

**Tình huống B:** Đã có baseline và incident; điều tra hoàn tất, cần lưu kết quả cuối của incident nhưng baseline tiếp tục chạy. → **`JFR.stop name=incident filename=...`**, rồi `JFR.check` xác nhận baseline còn hoạt động.

**Tình huống C:** Người vận hành quên tên nhưng muốn xuất riêng incident. → **`JFR.check` trước** để xác nhận recording name. Không tùy tiện chạy `JFR.dump` không có name vì khi đó lệnh có thể xuất dữ liệu từ mọi recording.

**Tình huống D:** Bạn muốn xuất dữ liệu một giờ trước nhưng baseline chỉ cấu hình giữ 10 phút. → Không có lệnh dump nào khôi phục được phần đã bị retention loại bỏ; cần **thiết kế retention và thời điểm chụp trước khi sự cố tái diễn**.

**Checklist trước khi thao tác thật:**
1. Có **đúng PID, đúng JVM, đúng quyền** và lệnh `help` xác nhận cú pháp.
2. Biết rõ **recording name/ID**, trạng thái và cấu hình hiện tại qua `JFR.check`.
3. Với dump, đã chọn đúng **scope**, **khoảng thời gian**, **đường dẫn file mới** và dung lượng còn trống.
4. Với stop, đã xác định recording nào kết thúc và **file cuối cần lưu**; các recording khác có cần giữ không.
5. Sau thao tác đã **check trạng thái**, kiểm tra file bằng `jfr summary`, bảo vệ và gắn metadata thời điểm/PID/settings cho bằng chứng.

**Ghi nhớ:** `JFR.check` = **xem**, `JFR.dump` = **xuất snapshot và tiếp tục ghi**, `JFR.stop` = **kết thúc phiên được chọn**. Trong môi trường nhiều recording, **`name` và kiểm tra trước/sau thao tác** là chìa khóa để giữ đúng dữ liệu và đúng vòng đời.

## Tài liệu tham khảo

- Oracle Java SE 21 — **The jcmd Command**, mô tả `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop` và tùy chọn: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java SE 21 — **The jfr Command**, `jfr summary`, `jfr print`, `jfr view`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java SE 21 — **Recording API**, vòng đời của một recording: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Dev.java — **Getting Started with JDK Flight Recorder**: https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/getting-started/
