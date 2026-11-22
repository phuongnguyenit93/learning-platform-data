# 14.3 Khởi chạy bằng `-XX:StartFlightRecording` hoặc `JFR.start` trên JVM đang chạy

## 1. JFR ghi gì và hai cách bắt đầu khác nhau ở đâu?

**Java Flight Recorder (JFR)** là hệ thống ghi sự kiện chẩn đoán của JVM. Một recording có thể chứa các mẫu CPU, garbage collection (GC), phân bổ bộ nhớ, class loading, thread, lock contention, file/socket I/O và nhiều sự kiện khác tùy **cấu hình event**. Sau khi thu, xuất dữ liệu thành file **`.jfr`** để xem bằng công cụ `jfr` hoặc **JDK Mission Control (JMC)**.

Có hai lối khởi chạy chính:

- **Startup:** `-XX:StartFlightRecording` là JVM option được truyền **trước tên main class hoặc `-jar`**. Dùng để bắt các hiện tượng khi process khởi động, warm-up, class loading, lỗi chỉ xảy ra đầu đời tiến trình hoặc ghi dữ liệu liên tục ngay từ đầu.
- **Runtime:** `jcmd <PID> JFR.start` gửi diagnostic command đến **JVM đang chạy**, bắt đầu một recording mới **không cần restart** nếu runtime hỗ trợ JFR, attach được phép và người gọi có quyền. Dùng khi service đã hoạt động mà mới phát hiện tải cao, chậm, GC hoặc contention.

Cả hai đều cấu hình một recording JFR trong JVM. Sự khác biệt chính là **thời điểm kích hoạt, vị trí truyền option và khả năng quan sát sự kiện trước đó**. Nếu không có recording liên tục được bật từ trước, khởi động `JFR.start` hôm nay không thể lấy lại các sự kiện xảy ra hôm qua.

Các ví dụ dùng **HotSpot/OpenJDK JDK 17+**. Có thể sử dụng JFR trên các JDK khác, nhưng tính năng, câu lệnh và thông tin chẩn đoán nên được xác minh với đúng JDK/vendor đang chạy ứng dụng.

## 2. Bảng chọn đúng cách thu

| Tình huống | Khởi chạy lúc startup | Khởi chạy trên JVM đang chạy |
| --- | --- | --- |
| Lỗi chỉ xảy ra 10–30 giây đầu startup | **Nên dùng** vì có thể thu ngay từ lúc JVM bắt đầu | Bật sau startup có thể bỏ lỡ |
| Service production đã chạy vài ngày, latency vừa tăng | Phải thay startup configuration rồi restart nếu chưa bật | **Nên dùng** `JFR.start`, không phải restart |
| Muốn luôn giữ 2 giờ dữ liệu gần nhất | `settings=default,disk=true,maxage=2h,...` từ startup | Có thể bật continuous recording khi process đang chạy, nhưng không giữ được dữ liệu trước lúc bật |
| Muốn chụp 2 phút profiling | `duration=2m,settings=profile` | `JFR.start ... duration=2m settings=profile` |
| Muốn lưu file ngay trong khi recording vẫn chạy | Gọi `JFR.dump` đến PID của process | Cũng dùng `JFR.dump` |
| Muốn dừng một recording đang chạy | `JFR.stop name=...` | Tương tự |
| Không thể attach vào JVM đang chạy | Flag startup là phương án khi có quyền đổi cấu hình deploy | `JFR.start` sẽ không khả dụng cho tới khi giải quyết quyền/hạn chế attach |

**Cần nhớ:** `-XX:StartFlightRecording` là cấu hình lúc launch Java; `JFR.start` là diagnostic command qua `jcmd`. **Không** đặt `JFR.start` trong các JVM startup flags, và **không** đưa `-XX:StartFlightRecording` vào phần sau tên ứng dụng.

## 3. Cú pháp chuẩn: dấu phẩy và dấu cách

### Startup: `-XX:StartFlightRecording`

```bash
java -XX:StartFlightRecording=name=boot,settings=profile,duration=2m,filename=boot.jfr -jar application.jar
```

Đây là **một JVM option**, các cặp `key=value` phân tách bằng **dấu phẩy**, cờ phải đặt **trước** `-jar`. Nếu Java chạy bằng classpath thì đặt trước tên main class:

```bash
java -XX:StartFlightRecording=name=boot,settings=default,dumponexit=true,filename=boot.jfr -cp classes com.example.Main
```

Sai vị trí:

```bash
java -jar application.jar -XX:StartFlightRecording=filename=boot.jfr
```

Trong dòng sai, `-XX:StartFlightRecording=...` đi vào đối số `main(String[] args)` của ứng dụng chứ không còn là option JVM.

### Runtime: `jcmd <PID> JFR.start`

```bash
jcmd -l
jcmd <PID> JFR.start name=incident settings=profile duration=2m filename=incident.jfr
```

Các cặp `key=value` của `jcmd` ngăn bằng **dấu cách**. `<PID>` là chỗ giữ chỗ; thay bằng PID thật của process đích, không nhập dấu `<` hay `>`. Chọn PID chính xác, đừng dùng `jcmd 0` vì có thể gửi lệnh tới **nhiều JVM**.

Dùng `java -version` để kiểm tra JDK của terminal, và `jcmd <PID> VM.version` để kiểm tra **JDK chạy ứng dụng đích**. Nếu khác nhau, lấy tài liệu và `help` theo runtime đích.

```bash
jcmd <PID> help JFR.start
jcmd <PID> help JFR.check
jcmd <PID> help JFR.dump
jcmd <PID> help JFR.stop
```

Các tham số, giới hạn và công cụ có thể khác nhau giữa các JDK/vendor. Hãy đối chiếu output `help` thay vì sao chép lệnh không tương thích.

## 4. Những option quyết định dữ liệu thu được

| Option | Tác dụng | Lưu ý |
| --- | --- | --- |
| `name=...` | Tên định danh của recording, dùng cho `JFR.check`/`dump`/`stop` | Đặt tên không dấu cách để dễ dùng trong shell. |
| `settings=default` | Template event ít overhead, phù hợp quan sát nền | Không có nghĩa bật mọi event. |
| `settings=profile` | Template thu nhiều thông tin profiling hơn | Thường overhead cao hơn `default`, nên dùng trong khoảng đo có mục tiêu. |
| `delay=20s` | Chờ 20 giây rồi mới bắt đầu ghi | Các event trong 20 giây đầu **không nằm trong recording**. |
| `duration=2m` | Tự dừng sau 2 phút ghi | Không ghi `duration` thường là ghi không thời hạn tới khi stop hoặc JVM kết thúc. |
| `filename=...` | Vị trí file `.jfr` được tạo khi recording kết thúc | File có thể **chưa tồn tại** ngay khi gọi start. |
| `disk=true` | Sử dụng disk repository tạm để giữ dữ liệu JFR | **Không có nghĩa** ghi vào `filename` liên tục từng sự kiện. |
| `maxage=2h` | Chỉ giữ dữ liệu trong giới hạn tuổi 2 giờ | Áp dụng khi `disk=true`; chunks cũ có thể bị xóa. |
| `maxsize=256m` | Giới hạn dung lượng dữ liệu giữ trong repository | Dùng với `disk=true`; giá trị phải phù hợp giới hạn chunk của JVM. |
| `dumponexit=true` | Dump recording khi JVM thoát bình thường | Không bảo đảm khi OOM kill, SIGKILL hoặc host crash. |
| `path-to-gc-roots=true` | Thu đường dẫn tới GC roots phục vụ điều tra memory leak | Có thể tốn chi phí đáng kể, không bật mặc định cho mọi cuộc thu. |

**Default và profile:** hai cấu hình `default.jfc` và `profile.jfc` thường ở `JAVA_HOME/lib/jfr`. `default` cân bằng event và tần suất sampling cho việc ghi dài; `profile` cung cấp thêm dữ liệu để điều tra trong khoảng ngắn. Chọn theo câu hỏi, vì thu nhiều event và stack trace có thể tăng CPU, memory, disk I/O, volume dữ liệu. Muốn bật event đặc thù hoặc chỉnh threshold, dùng file `.jfc` và `jfr configure`; kiểm tra settings thực sự bằng `JFR.check verbose=true`.

**`disk` so với `filename`:** `disk=true` cho phép JVM ghi chunks vào **repository tạm** trong suốt thời gian recording. `filename` là **file kết quả** khi dừng/hết duration; `JFR.dump` có thể xuất snapshot riêng sớm hơn. Không coi thư mục repository là nơi lưu artifact cuối. Nếu `disk=false`, dữ liệu chỉ giữ trong buffer bộ nhớ giới hạn, nên không phù hợp giữ lịch sử nhiều giờ.

## 5. Recipe A: ghi 2 phút từ startup

Cần tìm chỗ startup chậm hoặc mã Java/JVM tải lớp bất thường:

```bash
java -XX:StartFlightRecording=name=startup,settings=profile,duration=2m,filename=/var/log/app/startup.jfr -jar application.jar
```

Bắt đầu ghi ngay khi JVM khởi động, kết thúc sau khoảng 2 phút và ghi file theo `filename`. Directory `/var/log/app` phải tồn tại và user JVM có quyền ghi. Trên Windows, đổi thành đường dẫn hợp lệ của Windows, ví dụ `C:\recordings\startup.jfr`. Dùng đường dẫn tuyệt đối để không nhầm working directory.

Nếu muốn bỏ giai đoạn đầu warm-up và chỉ xem trạng thái gần ổn định:

```bash
java -XX:StartFlightRecording=name=steady,settings=profile,delay=30s,duration=2m,filename=/var/log/app/steady.jfr -jar application.jar
```

`delay` tính từ lúc JVM bắt đầu, **không** tự đồng bộ với readiness probe của service. Các sự kiện trong khoảng delay bị bỏ qua. Nếu vấn đề nằm trong startup thì đừng thêm delay.

Nếu ứng dụng thoát **trước khi hết duration**, tùy cấu hình có thể chưa có file kết quả. Có thể bật `dumponexit=true` để yêu cầu dump lúc JVM thoát bình thường:

```bash
java -XX:StartFlightRecording=name=quick,settings=default,dumponexit=true,filename=quick.jfr -jar application.jar
```

Những trường hợp `SIGKILL`, kernel/container OOM kill hoặc host crash có thể ngăn dump-on-exit; cần cơ chế dump chủ động/continuous nếu muốn giảm nguy cơ mất dữ liệu.

## 6. Recipe B: continuous recording luôn giữ lịch sử gần nhất

Với incident xảy ra ngẫu nhiên, muốn có dữ liệu **trước khi hệ thống phát cảnh báo**, nên bật ghi nền từ lúc deploy:

```bash
java -XX:StartFlightRecording=name=ring,settings=default,disk=true,maxage=2h,maxsize=256m -jar application.jar
```

Đây là **recording liên tục**, không có `duration`, giữ dữ liệu gần nhất trong giới hạn tuổi/dung lượng. Khi có sự cố, mở một terminal khác:

```bash
jcmd -l
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=ring filename=/var/log/app/ring-incident-%p-%t.jfr
```

`JFR.dump` tạo file từ các event còn được giữ, **không dừng recording**. `%p` và `%t` trong filename được JDK hỗ trợ thay bằng PID và thời điểm, hữu ích để không ghi đè các lần dump. Nếu muốn lấy tiếp sau 10 phút, gọi `JFR.dump` lần nữa với filename khác.

`maxage` và `maxsize` là chính sách **retention**. Nếu incident xảy ra từ 3 giờ trước trong khi `maxage=2h`, phần dữ liệu quá cũ đã bị loại; dump bây giờ không hồi phục được. Chọn retention dựa trên độ trễ phát hiện incident, thời gian phản ứng và dung lượng đĩa. Đừng chỉ nhìn `maxsize` mà bỏ qua file dump cuối có thể chiếm thêm dung lượng.

Nếu cần thay nơi chứa repository, HotSpot hỗ trợ tùy chọn JFR riêng, ví dụ:

```bash
java -XX:StartFlightRecording=name=ring,settings=default,disk=true,maxage=2h,maxsize=256m -XX:FlightRecorderOptions=repository=/var/tmp/jfr-repository -jar application.jar
```

`repository` là nơi giữ chunks **tạm**, không phải đầu ra `.jfr` của `JFR.dump`. Tạo thư mục và cấp quyền đúng cho process; kiểm tra các option với runtime cụ thể.

## 7. Recipe C: bật recording trên production JVM đã chạy

Khi service đang hoạt động, chưa có JFR hoặc cần thêm cấu hình `profile` có thời hạn:

### Bước 1 — xác định tiến trình và recording hiện tại

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> JFR.check
```

Nếu JVM đã có recording nền `ring` với dữ liệu phù hợp, có thể **dump ngay recording đó**. Không phải lúc nào cũng cần tạo recording mới. Nếu cần event nhiều hơn cho một cuộc điều tra cụ thể, tạo recording `profile` ngắn, có tên riêng.

### Bước 2 — bắt hiện tượng trong một khoảng hữu hạn

```bash
jcmd <PID> JFR.start name=incident settings=profile duration=120s filename=/var/log/app/incident.jfr
jcmd <PID> JFR.check name=incident
```

Một recording mới bắt đầu sau lệnh `JFR.start`. Khi đủ 120 giây ghi, JVM dừng và xuất file. Không cần restart. Muốn biết event settings đã áp dụng:

```bash
jcmd <PID> JFR.check name=incident verbose=true
```

Nếu `JFR.check` không còn thấy `incident` sau khi duration đã trôi qua, hãy **kiểm tra file kết quả**, bởi recording hết thời hạn sẽ không còn đang chạy.

### Bước 3 — lựa chọn không có duration

```bash
jcmd <PID> JFR.start name=onDemand settings=default disk=true maxage=1h maxsize=256m
jcmd <PID> JFR.check name=onDemand
```

Recording sẽ tiếp tục tới khi có lệnh stop, JVM thoát hoặc chính sách khác kết thúc nó. Có thể chụp snapshot:

```bash
jcmd <PID> JFR.dump name=onDemand filename=/var/log/app/snapshot.jfr
```

Và khi xong mới dừng:

```bash
jcmd <PID> JFR.stop name=onDemand filename=/var/log/app/final.jfr
```

Luôn truyền `name` để không ảnh hưởng recording khác. Với mục tiêu giữ kết quả, truyền `filename` khi `JFR.stop` và xác minh file được tạo. Nếu không chỉ định đường dẫn, tùy lệnh/thiết lập, dữ liệu có thể bị bỏ đi. Có thể dump trước khi stop để chắc chắn đã có một artifact.

## 8. `JFR.check`, `JFR.dump`, `JFR.stop` khác nhau ra sao?

| Lệnh | Công dụng | Recording còn chạy sau lệnh? |
| --- | --- | --- |
| `jcmd <PID> JFR.check` | Hiển thị recording đang chạy; có thể thêm `name`, `verbose=true` | Có, không thay đổi |
| `jcmd <PID> JFR.dump name=... filename=...` | Xuất snapshot sự kiện hiện có ra file | **Có**, recording tiếp tục |
| `jcmd <PID> JFR.stop name=... filename=...` | Kết thúc recording và xuất file nếu yêu cầu | **Không**, recording đó đã dừng |

Một quy trình an toàn và dễ lặp lại:

```bash
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=incident filename=/var/log/app/incident-before-stop.jfr
jcmd <PID> JFR.stop name=incident filename=/var/log/app/incident-final.jfr
```

Dùng `JFR.check` để xác minh đúng tên. Các lệnh JFR cũng có thể làm việc với recording ID; khi có nhiều recording, không dựa vào tên được tự sinh mà chưa kiểm tra.

Trên JVM hỗ trợ, `JFR.dump` còn có tham số `maxage=10m` hoặc `begin`/`end` để lọc khoảng dữ liệu **được xuất**. Đây là lựa chọn cho **lệnh dump**, khác với `maxage` ở lúc `JFR.start` (giới hạn dữ liệu được **giữ trong repository**). Nếu dữ liệu cũ đã bị retention xóa, dùng `JFR.dump maxage=...` cũng không lấy lại được.

## 9. Ví dụ Java 17+ tự chạy cho cả hai phương thức

Tạo file **`JfrCaptureDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;

public class JfrCaptureDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("READY");
        BufferedReader input =
                new BufferedReader(new InputStreamReader(System.in));
        input.readLine(); // Giữ JVM sống tới khi nhấn Enter.
        System.out.println("DONE");
    }
}
```

Biên dịch:

```bash
javac --release 17 JfrCaptureDemo.java
```

Đây là chương trình **độc lập**, chạy được trên JDK 17+ và chờ đầu vào để có thời gian gọi `jcmd`. Khi nhấn Enter **một lần**, chính chương trình sẽ in đúng hai dòng theo thứ tự:

```text
READY
DONE
```

### Thử phương thức startup

Terminal 1:

```bash
java -XX:StartFlightRecording=name=demoBoot,settings=default,dumponexit=true,filename=demo-boot.jfr JfrCaptureDemo
```

Đợi dòng `READY`; nhấn Enter để chương trình thoát. Kiểm tra file ở terminal 2:

```bash
jfr summary demo-boot.jfr
```

Thông báo trạng thái JFR của JVM hoặc output từ `jfr summary` có thể xuất hiện thêm, phụ thuộc phiên bản và lệnh; **không** phải hai dòng do `System.out.println` của chương trình in.

### Thử phương thức runtime

Terminal 1:

```bash
java JfrCaptureDemo
```

Đợi dòng `READY` và **chưa nhấn Enter**. Terminal 2:

```bash
jcmd -l
jcmd <PID> JFR.start name=demoLive settings=profile
jcmd <PID> JFR.check name=demoLive
jcmd <PID> JFR.dump name=demoLive filename=demo-live.jfr
jcmd <PID> JFR.stop name=demoLive filename=demo-final.jfr
```

Quay về terminal 1 nhấn Enter. Kiểm tra:

```bash
jfr summary demo-live.jfr
jfr summary demo-final.jfr
```

Vì ví dụ chỉ chờ nhập liệu, file có thể có **ít CPU samples hoặc allocation events**. Mục tiêu của ví dụ là kiểm tra cú pháp và vòng đời recording; muốn học profiling thì chạy workload có tải, kiểm tra event settings và ghi đủ thời gian.

**Đường dẫn rất quan trọng:** các file `filename` tạo qua `jcmd` được ghi trong filesystem của **JVM đích**, tương đối theo working directory của **process JVM**, không phải nhất thiết là thư mục của terminal chạy `jcmd`. Container host và container app có thể nhìn thấy filesystem khác nhau.

## 10. Đọc và xác nhận file JFR đã thu

Với file kết quả `incident.jfr`:

```bash
jfr summary incident.jfr
jfr print --events jdk.ExecutionSample incident.jfr
jfr print --events jdk.GarbageCollection incident.jfr
```

- `jfr summary` hiển thị khoảng thời gian, loại event và số lượng event. Dùng để xác minh **file tồn tại, đọc được và có dữ liệu** trước khi kết luận.
- `jfr print --events ...` lọc event. Kết quả rỗng không nhất thiết là lỗi: event có thể bị tắt, workload không tạo event hoặc ngưỡng event chưa đạt.
- Dùng **JDK Mission Control (JMC)** để phân tích timeline, thread, CPU, GC, allocation và tương quan các nguồn sự kiện. Chọn phiên bản JMC hỗ trợ JDK/file format đang dùng.

Để tránh nhầm file, đặt tên có service, mốc thời gian và PID, đồng thời lưu thông tin phiên bản Java, GC, workload và khung thời gian xảy ra incident. Khi cần so sánh các bản ghi, dùng cùng cấu hình `.jfc`, tương đương về thời lượng và tải; `settings=default` với `settings=profile` có thể tạo event coverage khác nhau.

## 11. Các tình huống xử lý theo bằng chứng

### A. Thời gian startup tăng đột biến

Bật `-XX:StartFlightRecording=...` **ngay khi khởi động**, không đặt `delay` nếu vấn đề nằm trong startup. Thu đủ các giai đoạn class loading, JIT warm-up, GC và framework initialization. Nếu chỉ `JFR.start` sau health check, bạn đã bỏ lỡ phần cần quan sát.

### B. P99 tăng ở service không thể restart

Dùng `jcmd <PID> JFR.start name=latency settings=profile duration=3m filename=/var/log/app/latency.jfr`. Đảm bảo incident còn đang diễn ra trong ba phút ghi; lưu trace/request IDs và ứng dụng metric để tương quan. Nếu attach lỗi, ghi nhận và khắc phục quyền/hạn chế cho phép, không mặc định JFR không được hỗ trợ.

### C. Lỗi ngẫu nhiên, khi thấy cảnh báo thì đã hết

Dùng **continuous recording** với `settings=default,disk=true,maxage=...` đủ dài. Sau khi phát hiện cảnh báo, `JFR.dump` lấy lịch sử đang còn. Nếu không hề có recording trước incident, không thể “quay ngược thời gian” bằng `JFR.start`.

### D. Nhiều recording đang chạy, không biết nên dump cái nào

Chạy `JFR.check`, xem tên và settings. Nếu `ring` đã có sự kiện cần thiết, dump `ring`. Nếu chỉ `profile` có event mong muốn, tạo recording khác đặt tên riêng và thu ngắn; tránh dừng nhầm recording còn phục vụ giám sát nền.

### E. Tạo file nhưng dung lượng nhỏ hoặc không có CPU samples

Kiểm tra bằng `jfr summary`, `JFR.check verbose=true`, thời lượng thực, tải thực và event settings. Recording có thể mới chạy vài giây hoặc sampling chưa đủ. File nhỏ không tự chứng minh JVM không bị bottleneck, và một CPU profile từ ứng dụng nhàn rỗi không có giá trị để giải thích peak traffic.

## 12. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra / xử lý |
| --- | --- | --- |
| Startup flag không hoạt động | Flag đặt sau `-jar`, sai cú pháp dấu phẩy, launcher không truyền flag | Đặt `-XX:StartFlightRecording=...` trước `-jar`; kiểm tra Java command và JVM logs. |
| `jcmd -l` không thấy process | Khác PID namespace, user không có quyền, tool không có trong image | Chạy với công cụ tương thích và quyền cho phép trên môi trường nhìn thấy PID JVM. |
| `JFR.start` bị từ chối | Hạn chế attach, `-XX:+DisableAttachMechanism`, quyền bảo mật, JVM không hỗ trợ | Kiểm tra runtime/attach policy; chọn startup flag ở lần deploy phù hợp nếu không attach được. |
| File `.jfr` chưa xuất hiện ngay sau start | `filename` là output lúc recording kết thúc | `JFR.check`; dùng `JFR.dump` nếu cần snapshot khi đang chạy. |
| File nằm sai thư mục | Working directory của JVM khác shell `jcmd` | Dùng đường dẫn tuyệt đối **trong filesystem JVM đích**. |
| `JFR.dump` báo lỗi ghi file | Thư mục chưa có, permission hoặc disk đầy | Kiểm tra path và user JVM, dung lượng disk repository và output. |
| Dump không có incident cũ | Recording bật quá muộn hoặc retention đã xóa chunks | Bật continuous từ trước, tăng `maxage/maxsize` hợp lý. |
| File ít event | `settings` thiếu event, threshold cao, workload quá nhẹ | Kiểm tra `JFR.check verbose=true` và `jfr summary`, điều chỉnh `.jfc`. |
| Lỡ stop recording và không có file | Không chỉ định destination, hoặc đọc nhầm path | Dùng `JFR.dump` trước stop; `JFR.stop name=... filename=...`. |
| JVM bị kill không có dump | `dumponexit` chỉ hoạt động khi shutdown có cơ hội thực hiện | Chủ động dump, dùng recording nền và quy trình giám sát/disk retention. |
| `profile` ảnh hưởng latency | Event/sampling quá nhiều, thu quá lâu hoặc nhiều recording | Giảm duration, chuyển `default` cho nền, đo overhead bằng workload tương đương. |
| Tool phân tích không mở được file | File đang ghi dở/không hoàn chỉnh hoặc tool không tương thích | Hoàn tất dump, kiểm tra `jfr summary`, dùng phiên bản JFR/JMC phù hợp. |

JFR thường có overhead thấp với cấu hình phổ thông, nhưng đó **không phải mức overhead cố định**. Những event có stack traces nặng, allocation sampling dày hoặc GC-root path có thể tăng chi phí đáng kể. Với production, chỉ bật những dữ liệu phục vụ câu hỏi và giới hạn thời lượng/retention.

## 13. Cẩn trọng khi chạy trong container và môi trường production

- **Quyền và PID namespace:** `jcmd` thường cần user đủ quyền trên cùng máy/namespace có thể nhìn thấy process JVM; có thể phải chạy bên trong container/app runtime. Dùng PID đích, không dựa vào PID của shell host.
- **Đường dẫn output:** `filename=/some/path/file.jfr` nằm trong filesystem của JVM, không mặc định ở nơi chạy `jcmd`. Thư mục phải tồn tại và user JVM có quyền ghi.
- **Dung lượng:** tính cả chunks tạm của repository, các file dump định kỳ, nhiều recording đồng thời và chính sách dọn artifact. Không nên đặt `maxage=0s/maxsize=0` cho ghi liên tục nếu chưa kiểm soát tăng trưởng dữ liệu.
- **Thông tin nhạy cảm:** một số event có command-line/system properties, đường dẫn, tên thread và stack traces; khả năng che dữ liệu khác theo JDK và cấu hình. Kiểm soát quyền truy cập file `.jfr`, không đăng recording production lên nơi công khai.
- **Đối chiếu thời gian:** giữ múi giờ, clock và timestamp của application metrics, tracing và recording thống nhất; phân tích nhầm cửa sổ sự cố sẽ dẫn tới kết luận sai.
- **Runtime khác nhau:** cú pháp và event/schema có thể thay đổi theo JDK/vendor; đừng suy từ JDK local nếu PID đang chạy bằng bản khác.

## 14. Checklist trước khi coi một cuộc thu JFR hoàn tất

- [ ] Xác định chính xác JVM PID, runtime/vendor/JDK version và vấn đề cần đo.
- [ ] Chọn `-XX:StartFlightRecording` nếu cần startup, hoặc `JFR.start` nếu JVM đã chạy và có quyền attach.
- [ ] Viết option đúng: **dấu phẩy** trong startup flag, **dấu cách** sau `jcmd ... JFR.start`.
- [ ] Chọn `settings=default` cho nền hoặc `profile` cho thu ngắn có mục tiêu; xác nhận event thực sự được bật.
- [ ] Chọn `duration`, `delay`, `filename`, `dumponexit` theo mục đích; biết file có thể chưa xuất hiện khi recording còn chạy.
- [ ] Với continuous recording, dùng `disk=true` cùng `maxage/maxsize` và đủ dung lượng.
- [ ] Kiểm tra `JFR.check` và `JFR.check verbose=true` khi cần; dùng tên recording duy nhất.
- [ ] Lấy `JFR.dump` để có snapshot mà không dừng recording; dùng `JFR.stop name=... filename=...` khi cần kết thúc.
- [ ] Xác nhận đường dẫn, quyền ghi và nơi thực tế chứa file `.jfr` ở process đích.
- [ ] Mở `jfr summary`, kiểm tra thời gian ghi và số lượng sự kiện; lưu workload/incident timestamp.
- [ ] Đối chiếu JFR với GC logs, OS/container metrics, request traces, CPU/latency và biết giới hạn coverage.
- [ ] Ghi lại artifacts, cấu hình JFR, JDK, retention, overhead để người khác có thể tái lập điều tra.

## 15. Nguồn chính thức để tra cứu tiếp

1. Oracle Java 26 `jcmd` manual — `JFR.start`, `JFR.check`, `JFR.dump` và `JFR.stop`: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html
2. Oracle JDK 24 Troubleshooting Guide — sử dụng `-XX:StartFlightRecording` từ startup và `jcmd` trên process đang chạy: https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf
3. Oracle JDK 26 Troubleshooting Guide — ví dụ flight recordings trên runtime production: https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf
4. OpenJDK `java` manual — options `-XX:StartFlightRecording`: https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md
5. Dev.java, Configuring the JDK Flight Recorder — khác biệt delimiter, settings, recording options và event settings: https://dev.java/learn/jvm/jfr/configure/
6. Oracle Java 26, Troubleshoot Performance Issues Using Flight Recorder: https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html
7. Java SE 26 API `jdk.jfr.Recording` — retention, lifecycle và destination: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html

**Kết luận thực hành:** cần thấy startup thì bật JFR từ JVM launch; cần điều tra service đang chạy thì dùng `jcmd <PID> JFR.start`. Chọn đúng `settings`, lưu đủ dữ liệu bằng `duration` hoặc `maxage/maxsize`, dùng `JFR.dump` để lấy file khi recording đang chạy và kiểm tra `jfr summary` trước khi phân tích.
