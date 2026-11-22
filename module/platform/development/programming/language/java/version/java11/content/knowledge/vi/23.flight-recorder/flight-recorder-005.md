# JDK Flight Recorder — jcmd JFR.start, JFR.check, JFR.dump, JFR.stop (Java 11+)

## Mục tiêu

**JDK Flight Recorder (JFR)** là cơ chế thu thập sự kiện (event) nằm trong JVM, phục vụ quan sát CPU, allocation, GC, thread, I/O, exception, class loading và các sự kiện do ứng dụng tự định nghĩa. Với ứng dụng **Java 11+**, JFR là công cụ chuẩn hiện hành để chẩn đoán một JVM đang chạy mà không cần khởi động lại chỉ để bật một recording thông thường. JFR được đưa vào OpenJDK qua **JEP 328**, có API thuộc module `jdk.jfr` và công cụ dòng lệnh `jcmd`.

Bài học này tập trung trực tiếp vào **bốn diagnostic commands**:

- `JFR.start` — bắt đầu một *recording* với tên/cấu hình cụ thể.
- `JFR.check` — kiểm tra những recording đang tồn tại và trạng thái của chúng.
- `JFR.dump` — xuất dữ liệu hiện đã được ghi thành tệp `.jfr` **mà không dừng recording**.
- `JFR.stop` — **dừng** recording được chỉ định; có thể ghi ra file khi cấu hình thích hợp.

Sau bài học, bạn có thể tìm đúng JVM, chạy một luồng start → check → dump → stop, kiểm tra tệp kết quả, phân biệt snapshot và dừng thu thập, chọn `settings=default`/`profile`, giới hạn tài nguyên bằng `maxage`/`maxsize`, tránh làm lộ dữ liệu khi dùng JFR trong production và khắc phục các lỗi thường gặp.

**Special Note:** Chỉ sử dụng kiến thức còn áp dụng ở JDK hiện đại. Từ Java 11, JFR đã được open-source; **không dùng các hướng dẫn cũ** yêu cầu `-XX:+UnlockCommercialFeatures` hoặc coi JFR là công cụ thương mại chỉ được bật bằng giấy phép lịch sử. Một số tùy chọn/tính năng `jfr` và `jcmd` thay đổi theo bản JDK; hãy tra cứu bằng `jcmd <PID> help JFR.start` trên **JVM thực tế**.

## 1. Phân biệt JVM, recording, event và tệp JFR

Một JVM Java có thể có **nhiều recording** với tên, thời điểm bắt đầu, bộ event và chính sách lưu trữ khác nhau.

```text
Máy đang chạy
  |
  +-- JVM A (PID 12345)
  |     |
  |     +-- Recording name=OpsBaseline (default.jfc)
  |     |      +-- event: CPU, GC, thread, I/O ...
  |     |
  |     +-- Recording name=IncidentProfile (profile.jfc)
  |            +-- event chi tiết hơn, sampling ...
  |            |
  |            +-- JFR.dump --> snapshot.jfr
  |            |                (recording vẫn RUNNING)
  |            |
  |            +-- JFR.stop --> recording STOPPED
  |
  +-- JVM B (PID 23456) -- recording riêng, không bị thao tác ở trên
```

Các thuật ngữ:

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **JVM/PID** | Tiến trình Java đích mà jcmd gắn vào | PID `12345` |
| **JFR recording** | Một lần thu thập event có tên/ID và settings | `IncidentProfile` |
| **Event** | Bản ghi có timestamp, duration/metadata và payload | `jdk.CPULoad`, `jdk.GarbageCollection` |
| **Settings file** | Cấu hình loại event, threshold, sampling | `default.jfc`, `profile.jfc` |
| **Repository/buffer** | Nơi JFR tạm lưu dữ liệu trước khi xuất | Memory buffers / disk chunks |
| **Dump/snapshot** | Tệp `.jfr` được tạo từ dữ liệu đã thu | `snapshot.jfr` |
| **JFR analysis** | Đọc/summarize/visualize dữ liệu trong tệp | `jfr summary`, JDK Mission Control |

**JFR.dump không phải Java heap dump.** Dù có event về allocation/GC, tệp `.jfr` không phải HPROF chứa toàn bộ object graph. Để điều tra heap dump thật có các diagnostic commands khác với mức chi phí và rủi ro riêng. Không coi JFR như bản sao đầy đủ của heap hoặc trace mọi method invocation.

### Những giới hạn cần hiểu

- Một recording mới không chứa toàn bộ lịch sử JVM **trước khi start**; các sự kiện được ghi từ lúc thu thập theo cấu hình.
- Ring-buffer/retention có thể làm mất dữ liệu cũ khi vượt `maxage` hoặc `maxsize`.
- `settings=default` cố gắng thu thập thông tin chi phí thấp; `profile` thường ghi nhiều chi tiết hơn và có thể tăng overhead.
- Một số event cần threshold/sampling; không có event trong output **không chứng minh** ứng dụng không có vấn đề.
- JFR events có thể chứa stack traces, tên file, host, class/method, thread name hoặc payload do bạn tự thêm; **coi file JFR là dữ liệu vận hành có thể nhạy cảm**.

## 2. Chuẩn bị: phiên bản JDK, quyền attach và PID đúng

`jcmd` là công cụ nằm trong **JDK**, dùng để gửi diagnostic commands tới JVM đang chạy. Thường cần:

1. Công cụ `jcmd` từ JDK có thể tương tác với target JVM (ưu tiên cùng distribution/major version hoặc version được xác nhận tương thích).
2. Target phải là JVM hỗ trợ lệnh JFR; trong bài là HotSpot/OpenJDK có module `jdk.jfr`.
3. Lệnh phải được chạy trên **cùng host/không gian attach phù hợp** và có quyền OS phù hợp (thường cùng user/effective UID/GID), không mặc định có thể attach vào mọi container/JVM.
4. JVM không bị cấu hình chặn attach hoặc môi trường bảo mật hạn chế công cụ chẩn đoán.
5. Có đủ dung lượng/permission để ghi tệp `.jfr` vào đường dẫn thuộc JVM target.

**Kiểm tra công cụ:**

```bash
java -version
javac -version
jcmd -l
```

Từ `jcmd -l`, tìm đúng tiến trình Java đang chạy bằng PID và main class/command line. Không tự động dùng PID 0 khi bạn chỉ muốn thao tác một service — tùy diagnostic command, PID 0 có thể gửi đến **nhiều JVM** và gây tác động ngoài ý muốn.

Ví dụ output **minh họa**, PID thay đổi mỗi lần chạy:

```text
12345 JfrTargetDemo
23456 com.example.application.Main
```

Trong các lệnh bên dưới, **`12345` là PID mẫu**. Khi thực hành phải thay bằng PID thật vừa lấy từ `jcmd -l`; không copy một PID có thể đã thuộc tiến trình khác.

Kiểm tra lệnh được JVM cụ thể hỗ trợ:

```bash
jcmd 12345 help
jcmd 12345 help JFR.start
jcmd 12345 help JFR.check
jcmd 12345 help JFR.dump
jcmd 12345 help JFR.stop
```

**Nên ưu tiên `jcmd PID help <command>`** thay cho việc đoán option từ tutorial viết cho một JDK khác. Command names trong bài được hỗ trợ rộng rãi từ Java 11 tới JDK hiện đại, nhưng một số option mở rộng hoặc cách mô tả argument có thể thay đổi qua phiên bản.

### Lệnh jcmd được gửi tới JVM nào?

`jcmd 12345 JFR.start ...` gửi yêu cầu tới **JVM có PID 12345**, không phải tới process `jcmd`. Khi chạy `JFR.dump filename=...`, đường dẫn **thường được hiểu theo môi trường/working directory của target JVM**, không phải mặc định thư mục mà terminal hiện tại đang đứng. Đường dẫn tuyệt đối hoặc file path có dấu cách cần xử lý quotation theo shell/JDK thực tế.

Khi target chạy trong container, PID bên ngoài có thể khác PID bên trong namespace. Đừng suy từ PID do monitoring server hiển thị là chắc chắn `jcmd` nhìn thấy được; kiểm tra user namespace, filesystem visibility và permission attach.

## 3. Bốn lệnh JFR: ý nghĩa, cú pháp và vòng đời

| Lệnh | Tác dụng | Thay đổi recording? | Sinh file? |
| --- | --- | --- | --- |
| `JFR.start` | Tạo recording mới, áp dụng settings, đặt tên và retention | **Có**, bắt đầu/schedule | Có thể sinh file về sau theo `filename/duration/stop` |
| `JFR.check` | Liệt kê recording và trạng thái | **Không**, chỉ xem | Không |
| `JFR.dump` | Tạo một bản chụp dữ liệu thành `.jfr` | **Không dừng**, tiếp tục thu thập | **Có** |
| `JFR.stop` | Kết thúc một recording cụ thể | **Có**, dừng | Có thể ghi file nếu được chỉ định; nếu không, dữ liệu chưa dump có thể bị bỏ |

**Quy tắc nhớ nhanh:** `dump = snapshot`, `stop = kết thúc`. Có thể dump nhiều lần cùng một recording đang chạy, nhưng không thể mong nhận thêm sự kiện sau khi recording đã bị stop.

### 3.1. JFR.start

Cú pháp tổng quát:

```bash
jcmd 12345 JFR.start name=IncidentProfile settings=profile disk=true maxage=10m maxsize=64m
```

Giải thích:

- `name=IncidentProfile`: tên để xác định recording trong các lệnh sau. Chọn tên **không trùng hoặc gây nhầm** với recording đang chạy.
- `settings=profile`: bộ sự kiện phục vụ phân tích chi tiết ngắn hạn.
- `disk=true`: JFR có thể dùng disk repository; cùng `maxage` và `maxsize` để kiểm soát giữ dữ liệu.
- `maxage=10m`: giới hạn thời gian các chunk dữ liệu được giữ trong repository.
- `maxsize=64m`: giới hạn dung lượng dữ liệu được giữ theo recording. Với JDK hiện đại, giới hạn phải phù hợp kích thước chunk; nếu quá nhỏ, lệnh có thể bị từ chối.
- Không đặt `duration` thì recording có thể tiếp tục tới khi stop/JVM thoát hoặc chính sách khác áp dụng.

Các option thông dụng hiện vẫn có giá trị:

| Option | Dùng để làm gì | Ví dụ |
| --- | --- | --- |
| `name` | Nhận diện recording | `name=IncidentProfile` |
| `settings` | Chọn `default`, `profile` hoặc file `.jfc` | `settings=default` |
| `delay` | Chờ một khoảng rồi mới bắt đầu | `delay=5s` |
| `duration` | Tự giới hạn thời gian recording | `duration=2m` |
| `filename` | Đường dẫn tệp kết quả khi recording được dừng/hoàn tất | `filename=incident.jfr` |
| `disk` | Dùng disk repository | `disk=true` |
| `maxage` | Giữ tối đa bao lâu dữ liệu trong repository | `maxage=10m` |
| `maxsize` | Dữ liệu tối đa được giữ | `maxsize=64m` |
| `dumponexit` | Dump dữ liệu khi JVM thoát nếu phù hợp cấu hình | `dumponexit=true` |
| `path-to-gc-roots` | Thêm thông tin đường đi tới GC roots khi dump/kết thúc ở môi trường hỗ trợ | Chi phí có thể cao, **không bật tùy tiện** |

**Không hứa tác động luôn bằng 0.** Default JFR thường có overhead thấp, nhưng không cố định cho mọi workload/JDK. `profile` và event settings tùy chỉnh, đặc biệt stack traces hoặc các sự kiện rất thường xuyên, có thể làm chi phí cao hơn.

**Phân biệt `settings=default` và `settings=profile`:**

- `default` phù hợp quan sát liên tục hoặc tạo baseline với chi phí thấp hơn.
- `profile` thu thập chi tiết hơn, phù hợp phiên đo **ngắn** khi điều tra CPU, allocation và hotspot, cần kiểm soát thời gian/dung lượng.
- Bộ settings là file JFC có thể được tùy chỉnh; không khẳng định tất cả event được bật trong mọi bản JDK. Các event enabled/threshold/period cần xem trong file profile/runtime.

### 3.2. JFR.check

```bash
jcmd 12345 JFR.check
```

Ví dụ output **minh họa**, không phụ thuộc cụ thể PID hoặc thời điểm:

```text
12345:
Recording 1: name=IncidentProfile maxsize=64.0MB maxage=10m (running)
```

Thông tin có thể gồm recording ID, name, state, duration và retention. Một JVM có thể có **nhiều recordings**, nên `JFR.check` giúp bạn tránh dump/stop nhầm recording.

**Đừng nhầm `JFR.check` với việc xác thực tệp kết quả.** Check chỉ thấy trạng thái recording trong JVM. Muốn biết file `.jfr` đọc được và chứa event nào, cần `JFR.dump`, sau đó kiểm tra bằng `jfr summary`/`jfr print` hoặc JDK Mission Control.

### 3.3. JFR.dump

```bash
jcmd 12345 JFR.dump name=IncidentProfile filename=snapshot.jfr
```

Tác dụng:

1. Chọn đúng recording bằng tên, không phải tất cả nếu môi trường có nhiều recording.
2. Xuất dữ liệu đã ghi thành file `snapshot.jfr`.
3. **Không dừng** recording: event tiếp theo vẫn có thể được thu thập theo settings.
4. Cho phép điều tra hiện trạng mà vẫn giữ một recording baseline đang hoạt động.

**Chú ý output location:** nếu `filename=snapshot.jfr` là tên tương đối, file được tạo theo working directory của **JVM đích** ở môi trường đã thử. Với production, ưu tiên một path tuyệt đối nằm trong thư mục có quyền ghi và quản lý retention rõ ràng; nhớ escape/quote path chứa dấu cách, nhất là trên Windows.

Trong JDK có hỗ trợ, `JFR.dump` còn có thể nhận `maxage`/`maxsize` để giới hạn phạm vi dữ liệu xuất, hoặc `begin/end` cho thời gian. Những option này được áp dụng **lúc dump**, không đồng nghĩa thay `maxage/maxsize` của recording đang chạy. Kiểm tra `jcmd PID help JFR.dump` để xác minh sự hỗ trợ và cú pháp trên runtime thật.

**Không dump vô hạn** hoặc quá thường xuyên vì mỗi file có chi phí I/O và cần bảo mật; lên lịch và xóa/luân chuyển files theo chính sách vận hành.

### 3.4. JFR.stop

```bash
jcmd 12345 JFR.stop name=IncidentProfile
```

Lệnh này dừng recording tên `IncidentProfile`. Nếu đã `JFR.dump` trước đó, file snapshot vẫn tồn tại và có thể phân tích độc lập.

Khi muốn **dừng và lưu dữ liệu ra một file mới**, có thể dùng:

```bash
jcmd 12345 JFR.stop name=IncidentProfile filename=final.jfr
```

**Quan trọng:** hành vi của `JFR.stop` không có `filename` có thể khiến dữ liệu chưa ghi ra file **bị bỏ**. Đừng dựa vào suy nghĩ “stop luôn tự tạo .jfr”. Trong ví dụ chính, ta **dump trước, stop sau**, nên đã có `snapshot.jfr` để lưu.

Nếu recording được bắt đầu bằng `duration=2m filename=...`, JVM có thể tự hoàn thành và ghi file; lúc đó một lệnh stop thủ công gửi sau khi recording đã kết thúc không còn tên recording chạy để dừng. Đừng coi đó là lỗi nghiêm trọng nếu lifecycle dự kiến là auto-stop.

## 4. Quy trình tiêu chuẩn trên một JVM đang chạy

**Cửa sổ terminal A:** ứng dụng Java vẫn chạy.

**Cửa sổ terminal B:** gắn vào đúng PID. Các con số và đường dẫn sau đây là **ví dụ**, thay PID bằng lệnh `jcmd -l` thực tế.

```bash
# Bước 0: xác định đúng Java process
jcmd -l

# Bước 1: bắt đầu recording
jcmd 12345 JFR.start name=OpsSnapshot settings=default disk=true maxage=10m maxsize=64m

# Bước 2: kiểm tra recording đang chạy
jcmd 12345 JFR.check

# Bước 3: tạo snapshot nhưng không dừng recording
jcmd 12345 JFR.dump name=OpsSnapshot filename=ops-snapshot.jfr

# Bước 4: dừng recording
jcmd 12345 JFR.stop name=OpsSnapshot
```

Nếu mục tiêu là ghi thêm dữ liệu sau snapshot, **đừng gọi stop ngay**: hãy tiếp tục theo dõi, rồi dump lần tiếp theo hoặc stop khi kết thúc ca điều tra.

### Sơ đồ vòng đời

```text
NOT_STARTED
    |
    | JFR.start
    v
RUNNING <-------------------------+
    |                              |
    | JFR.check (chỉ xem)          |
    | JFR.dump (xuất snapshot) ----+
    |
    | JFR.stop
    v
STOPPED

Snapshot .jfr: file độc lập, có thể đem phân tích
```

Nếu một recording đã dừng, muốn tiếp tục thu thập bạn phải start một recording mới; không có khái niệm dump tiếp những sự kiện mới từ recording đã ngừng.

## 5. Ví dụ Java 11 hoàn chỉnh: tạo event để thử bốn lệnh

Để bài thực hành có dữ liệu **xác minh được** thay vì chỉ hy vọng có event CPU/GC ngẫu nhiên, ứng dụng sẽ tự phát sự kiện JFR tên `demo.LessonPulse` đều đặn.

Mã chỉ sử dụng API **Java 11** của module `jdk.jfr`:

- `@Name`: tên sự kiện có cấu trúc dễ lọc.
- `@Label`: nhãn hiển thị.
- `@Category`: nhóm sự kiện.
- `Event.commit()`: gửi sự kiện vào recorder nếu được enable.
- Một vòng lặp chờ 45 giây để bạn kịp chạy `jcmd` trong cửa sổ khác.

**Tệp `JfrTargetDemo.java`:**

```java
import java.util.concurrent.TimeUnit;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

public final class JfrTargetDemo {
    @Name("demo.LessonPulse")
    @Label("Lesson pulse")
    @Category({"Demo", "Health"})
    static final class LessonPulse extends Event {
        long sequence;
    }

    public static void main(String[] args) throws Exception {
        long until = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(45);
        long count = 0;

        System.out.println("jfr-target-ready");
        System.out.flush();

        while (System.nanoTime() < until) {
            LessonPulse event = new LessonPulse();
            event.sequence = count++;
            event.commit();
            Thread.sleep(100);
        }
    }
}
```

Ở ví dụ này, event không chứa dữ liệu cá nhân hoặc secret; chỉ có bộ đếm `sequence`. Trong ứng dụng thật, custom event có thể chứa thông tin nhạy cảm nên phải thiết kế schema event và retention theo chính sách.

### Biên dịch và khởi động

Trong thư mục trống, lưu đúng file `JfrTargetDemo.java`:

```bash
javac --release 11 -encoding UTF-8 JfrTargetDemo.java
java JfrTargetDemo
```

**Stdout của chương trình Java** ở thời điểm khởi động:

```text
jfr-target-ready
```

Chương trình giữ JVM sống khoảng **45 giây**, rồi tự thoát; bạn cần chạy lệnh JFR khi JVM còn sống. Khi thực hành thủ công chậm hơn, có thể đổi `45` thành `180` trong `TimeUnit.SECONDS.toNanos(...)`, biên dịch lại và chạy lại để có thêm thời gian. **Bản kiểm thử được mô tả bên dưới dùng đúng 45 giây.**

### Chạy jcmd ở terminal thứ hai

```bash
jcmd -l
```

Giả sử PID thực đang thấy là `12345`:

```bash
jcmd 12345 JFR.start name=Lesson274 settings=profile disk=true maxage=5m maxsize=32m
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=Lesson274 filename=snapshot.jfr
jcmd 12345 JFR.stop name=Lesson274
```

**Tệp `snapshot.jfr` nằm trong working directory của JVM demo** khi dùng tên tương đối. Terminal B có thể đang đứng ở thư mục khác; hãy xác định working directory/đường dẫn trong thông báo của `JFR.dump`.

Kiểm tra tệp (từ đúng thư mục chứa file):

```bash
jfr summary snapshot.jfr
jfr print --events demo.LessonPulse snapshot.jfr
```

`jfr summary` trả về thống kê loại sự kiện và số lượng trong recording. Trong `jfr print`, bạn có thể nhìn thấy các sự kiện với trường `sequence`; **số lượng và timestamp thay đổi** theo thời điểm bắt đầu, dump và scheduler.

### Kết quả kiểm thử thực tế

Chương trình đã được:

1. Biên dịch với `javac --release 11 -encoding UTF-8`.
2. Chạy trong một JVM cục bộ bằng JDK Zulu 24.0.2 (runtime hiện đại hỗ trợ classfile 11).
3. Điều khiển bằng đúng các lệnh `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
4. Tạo thành công `snapshot.jfr`, kích thước **253.759 byte** trong lần đo.
5. Xác minh bằng `jfr summary` rằng có **24 event `demo.LessonPulse`** trong file.

Các dòng kiểm tra ở cấp harness:

```text
compile=PASS javac --release 11
JFR.start=PASS
JFR.check=PASS
JFR.stop=PASS
jfrBytes=253759
JFR_COMMAND_FLOW=PASS
```

Đây là tóm tắt từ bài kiểm thử thực tế, **không phải stdout cố định của công cụ jcmd/JFR**. Kích thước file, số event và PID chắc chắn có thể khác khi tự chạy. `JFR.dump` cũng đã báo tạo thành công snapshot. Lần chạy đầu trên Windows có đường dẫn chứa khoảng trắng nên lệnh dump với path tuyệt đối không được quote chính xác; sau khi cấu hình **working directory của JVM target** và dùng `filename=snapshot.jfr`, toàn bộ quy trình thành công. Điều này minh họa tầm quan trọng của quoting/path trong môi trường thật.

### Vì sao không in chính xác output của jcmd?

`jcmd` thường in PID, recording ID, tên, trạng thái, size/age và file path phụ thuộc môi trường. Chúng **không phải contract cố định** để bạn copy thành snapshot assertion. Một test tự động nên kiểm tra **tín hiệu có ý nghĩa**: recording xuất hiện sau start, file được tạo sau dump, file đọc được và có expected event, recording biến mất/đã stop sau stop.

**Không dùng số lượng `demo.LessonPulse=24` làm assertion tổng quát.** Đếm event phụ thuộc khoảng thời gian giữa start và dump; với vòng lặp 100ms và thời gian 2–3s, con số có thể dao động.

## 6. Dùng `settings=default`, `profile` và file .jfc đúng nhu cầu

Hai cấu hình có sẵn thường nằm tại `JAVA_HOME/lib/jfr/`:

- `default.jfc`: tập sự kiện thông dụng với mức chi phí thấp, phù hợp baseline/quan sát lâu hơn.
- `profile.jfc`: tăng chi tiết một số event, có thể tăng CPU, allocation và lượng file; thích hợp đo ngắn hạn có giám sát.

Ví dụ:

```bash
jcmd 12345 JFR.start name=Baseline settings=default disk=true maxage=30m maxsize=128m
```

hoặc:

```bash
jcmd 12345 JFR.start name=CpuInvestigation settings=profile duration=2m filename=cpu-profile.jfr
```

**Hai lệnh trên là hai tình huống độc lập**, không yêu cầu chạy cả hai cùng lúc. Với recording có `duration=2m`, JVM tự kết thúc sau khoảng thời gian đó; file kết quả được ghi theo policy `filename` đã cấu hình.

File `.jfc` cho phép tùy chỉnh event types, thresholds, periods và stack trace collection. Đừng cho rằng bật `profile` sẽ thu **mọi allocation** theo từng đối tượng; một số event dùng sampling/threshold, và số lượng trường dữ liệu tùy JDK.

### Sử dụng recording trong production

Một runbook an toàn có thể gồm:

1. Bắt đầu với `settings=default` và retention/disk limit phù hợp.
2. Nếu cần drill-down, tạo **một profile recording có thời hạn** thay vì bật cấu hình chi phí cao vô hạn.
3. Tạo snapshot `JFR.dump` khi có biểu hiện CPU spike, GC pause hoặc latency.
4. Kiểm tra file JFR bằng công cụ phân tích, gắn mốc incident thời gian phù hợp.
5. Dừng profile recording sau điều tra, giữ baseline nếu chính sách yêu cầu.
6. Giới hạn quyền truy cập/tải file, encryption-at-rest và retention theo chính sách.
7. Đo overhead thay vì giả định một con số phần trăm cố định cho mọi service.

**Không dùng `path-to-gc-roots=true` tùy tiện.** Việc tìm reference paths đến GC roots có thể tốn kém, gây pause đáng kể tùy heap/workload. Chỉ bật khi thật sự điều tra memory leak và đã dự liệu tác động.

## 7. File path, disk repository và cơ chế giới hạn dữ liệu

### `filename` của JFR.start không giống việc dump ngay

Khi gọi:

```bash
jcmd 12345 JFR.start name=Capture settings=default filename=capture.jfr duration=60s
```

đây là khai báo nơi ghi file khi recording **kết thúc** theo policy. Nó **không có nghĩa** ngay lúc start đã xuất ra file đầy đủ với dữ liệu mới nhất. Nếu cần bản chụp khi đang ghi, dùng `JFR.dump`.

### Relative path cần chú ý

- `filename=snapshot.jfr`: tên tương đối, thường được JVM target diễn giải theo working directory của chính nó.
- `filename=/var/diagnostics/snapshot.jfr`: ví dụ absolute path trên Unix; path phải có quyền ghi và đủ disk.
- Trên Windows: path có khoảng trắng có thể bị shell/JVM chia thành nhiều tokens nếu quote sai. Kiểm thử lệnh trên shell thật, hoặc dùng working directory không cần path tuyệt đối.
- Nếu target chạy trong container, path thuộc **filesystem mà JVM nhìn thấy**. File có thể tồn tại bên trong container nhưng không hiển thị ngay trên host bên ngoài.

**Không khẳng định file nằm ở thư mục terminal B** chỉ vì lệnh `jcmd` được gõ ở đó.

### Cách hiểu `maxage` và `maxsize`

Khi `disk=true`, JFR dùng repository để chứa các dữ liệu/chunk. Với giới hạn như `maxage=5m maxsize=32m`, các phần cũ có thể được loại bỏ theo retention, giúp recording chạy dài nhưng không giữ vô hạn lịch sử. Khi dump sau nhiều giờ, file snapshot có thể chỉ chứa **phần còn được giữ**, không phải toàn bộ từ lúc recording bắt đầu.

Đừng dùng `maxsize` quá nhỏ so với chunk size/giới hạn của JFR runtime, vì có thể gặp lỗi tham số. Đừng dùng file output path nằm trên ổ đĩa sắp đầy; writing .jfr có thể thêm I/O và thất bại khi thiếu chỗ. Với môi trường production, cần policy tự động dọn file đã dump thay vì chỉ giới hạn repository.

## 8. Nhiều recording đồng thời: chọn đúng tên để tránh lẫn dữ liệu

Một JVM có thể có hai recording:

```text
Recording 1: name=Baseline     (running)
Recording 2: name=IncidentCpu  (running)
```

Nếu thao tác:

```bash
jcmd 12345 JFR.dump filename=all.jfr
```

trên nhiều JDK, việc bỏ `name` có thể khiến dump dữ liệu từ **tất cả recording**; đây không phải luôn là điều bạn mong muốn. Khi biết recording mục tiêu, hãy chỉ định rõ:

```bash
jcmd 12345 JFR.dump name=IncidentCpu filename=cpu-snapshot.jfr
jcmd 12345 JFR.stop name=IncidentCpu
```

Sau đó `Baseline` vẫn có thể tiếp tục chạy. Không dùng `JFR.stop` không có name rồi mong nó chọn “recording gần nhất”. Trong JDK hiện đại, không đưa name thì không recording nào bị stop, hoặc báo lỗi/cần tham số theo runtime. **An toàn nhất là luôn chỉ định tên đã xác nhận bằng JFR.check.**

### Recording ID so với name

`JFR.check` có thể hiển thị cả số ID và name. Tên dễ dùng trong runbook, nhưng nếu có nhiều người/operator cùng start recording, cần chính sách đặt tên đủ duy nhất và lưu lại thông tin PID/start time. Không dùng name mà không kiểm tra để tránh stop nhầm recording của nhóm khác.

## 9. Trình tự dump–stop so với stop–dump

**Đúng nếu cần snapshot trước khi dừng:**

```bash
jcmd 12345 JFR.dump name=IncidentProfile filename=incident.jfr
jcmd 12345 JFR.stop name=IncidentProfile
```

**Đúng nếu muốn một bước dừng và lưu:**

```bash
jcmd 12345 JFR.stop name=IncidentProfile filename=incident-final.jfr
```

**Sai kỳ vọng:**

```bash
jcmd 12345 JFR.stop name=IncidentProfile
jcmd 12345 JFR.dump name=IncidentProfile filename=too-late.jfr
```

Lúc này recording đã dừng, nên không thể dump như thể nó vẫn đang chạy. Nếu dữ liệu không được lưu tại thời điểm stop, bạn có thể đã mất phần dữ liệu chưa xuất file.

### Khi cần ghi tiếp sau dump

```bash
jcmd 12345 JFR.dump name=IncidentProfile filename=first.jfr
# Điều tra thêm trong khi recording vẫn chạy.
jcmd 12345 JFR.dump name=IncidentProfile filename=second.jfr
jcmd 12345 JFR.stop name=IncidentProfile filename=final.jfr
```

Các tệp snapshot có thể chứa **vùng thời gian chồng lặp**, không phải mỗi file là một phần dữ liệu độc lập không trùng nhau. Khi hợp nhất báo cáo, cần tránh đếm đôi event nếu phân tích nhiều snapshot cùng recording.

## 10. Phân tích tệp JFR sau dump

Công cụ dòng lệnh `jfr` có trong JDK và dùng để đọc/kiểm tra các file `.jfr`.

```bash
jfr summary snapshot.jfr
jfr print --events demo.LessonPulse snapshot.jfr
```

- `jfr summary`: thống kê loại event, count và thông tin cơ bản về recording.
- `jfr print`: hiển thị các event được lọc để kiểm tra trường dữ liệu.
- Một số JDK hiện đại có các chế độ phân tích bổ sung; **không lấy những tùy chọn mới làm yêu cầu của Java 11**.
- JDK Mission Control (JMC) là giao diện phù hợp cho phân tích CPU, memory, GC, thread và thời gian; cách mở file có thể thay đổi theo bản JMC.

### Các câu hỏi có thể trả lời từ JFR

| Vấn đề | Loại event/tín hiệu nên xem | Lưu ý |
| --- | --- | --- |
| CPU spike | Execution sampling, CPU load, thread states | Sampling không phải 100% lời gọi method |
| GC pause | GC events, heap summary, allocation data | Phân biệt pause time và object allocation |
| Thread blocking | Java monitor, thread park, lock-related events | Event có threshold và có thể không đầy đủ |
| I/O chậm | File read/write, socket read/write events | Kiểm tra threshold, host/path nhạy cảm |
| Exception tăng | Exception throw/error events nếu bật | Tăng overhead nếu bật nhiều |
| Class loading bất thường | Class load/unload events | Cần xem cấu hình JFR và startup |
| Business latency | Custom JFR event với duration | Không ghi token, PII hoặc request payload nhạy cảm |

Không suy từ “JFR không thấy event X” thành “X không xảy ra”: event có thể bị tắt, threshold lớn, sampling bỏ qua hoặc retention đã loại dữ liệu.

## 11. Lệnh hỗ trợ và hướng dẫn tra cứu trong JVM thật

### Những lệnh nên biết

```bash
jcmd -l
jcmd 12345 help
jcmd 12345 help JFR.start
jcmd 12345 help JFR.check
jcmd 12345 help JFR.dump
jcmd 12345 help JFR.stop
```

**Không sử dụng các tùy chọn không có trong output help của JVM đích.** JDK 11 khác JDK 25 ở một số tính năng bổ sung. Ngay cả khi tài liệu web hiển thị một option mới, runtime cụ thể mới quyết định khả năng thực thi.

### Tài liệu hiện hành và tài liệu Java 11

Một số tài liệu online cũ về Java Flight Recorder đề cập commercial licensing, flags mở khóa hoặc bộ công cụ recorder lịch sử. Những hướng dẫn đó **không còn là lộ trình thông thường của OpenJDK 11+** và không nên làm theo.

Các API từ Java 11:

- `jdk.jfr.Event`, `@Name`, `@Label`, `@Category` và `Recording`.
- `jdk.jfr.consumer.RecordingFile` để đọc các recording files bằng code khi cần.
- `jcmd PID JFR.start/check/dump/stop`, cùng `jfr summary/print`.

Bạn không bắt buộc viết mã Java API để làm những thao tác vận hành cơ bản này; `jcmd` đủ để bật, xem, xuất và dừng một recording trên JVM đã chạy.

## 12. Tối ưu overhead và mức chi tiết của sự kiện

Không có một cấu hình JFR tốt nhất cho tất cả workload. Cần quyết định theo **mục tiêu điều tra**:

| Mục tiêu | Gợi ý recording | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Baseline toàn ngày | `settings=default`, maxage/maxsize phù hợp | Dung lượng repository, retention và thông tin nhạy cảm |
| CPU hotspot 2 phút | `settings=profile duration=2m` | Sampling/stack traces làm tăng overhead |
| GC spike bất chợt | Baseline rolling + `JFR.dump` khi có sự kiện | Dump cần I/O, có thể thiếu khoảng thời gian đã bị evict |
| Memory leak | Profile ngắn và event phù hợp, cân nhắc GC roots | GC root path rất tốn tài nguyên trên heap lớn |
| Custom business metric | JFR Event API với schema hạn chế | Payload nhạy cảm và event tần suất cao |
| Tải file debug cho nhóm hỗ trợ | Snapshot có quyền truy cập có kiểm soát | Dữ liệu JFR không tự ẩn PII/credentials |

**Mức overhead phụ thuộc cấu hình**, tần suất event, số thread, workload, JDK và phân tích đang bật. Không lấy một con số cố định từ bài viết khác làm đảm bảo SLA production.

### Vì sao `duration` và retention khác nhau?

- `duration=2m`: recording tự kết thúc sau khoảng thời gian đó.
- `maxage=10m`: giới hạn **thời gian giữ dữ liệu** trong repository khi recording đang thu thập.
- `maxsize=64m`: giới hạn **dung lượng giữ dữ liệu**.
- `dumponexit=true`: cố gắng xuất khi JVM thoát theo khả năng và cấu hình, không thay thế file dump có kiểm chứng khi ứng dụng crash hoặc bị kill cứng.

Đừng nghĩ `maxage=10m` sẽ tự **stop** recording sau 10 phút. Đây là giới hạn retention, không phải timeout của recording.

## 13. Bảo mật và vận hành production

File JFR có thể chứa:

- Tên class/method, thread names, stack traces và đường dẫn file.
- Hostnames, sockets/ports và metadata I/O.
- Event payload do ứng dụng tự định nghĩa.
- Thông tin tương quan với workload, transaction hoặc một người dùng cụ thể nếu bạn đã thiết kế sự kiện như vậy.

**Không mặc định JFR tự redact các thông tin đó.** Đối với production:

1. Phân quyền attach `jcmd` cho đúng operator/service account.
2. Không dùng PID 0 để thao tác mọi JVM nếu không có chủ đích.
3. Ghi file vào thư mục giới hạn truy cập, tránh `/tmp` chung không kiểm soát nếu nội dung nhạy cảm.
4. Dùng mã hóa lưu trữ/truyền tải, giới hạn người được mở hoặc tải file.
5. Định nghĩa retention và quy trình xóa file khi kết thúc incident.
6. Thiết kế custom JFR Event **không chứa credential, request body, PII** không cần thiết.
7. Kiểm soát overhead, memory/disk repository và số recording đồng thời.
8. Với container, kiểm tra mount, disk pressure, user namespace và chính sách attach.
9. Ghi lại PID, hostname/node, thời gian bắt đầu/kết thúc và JDK version khi lưu artifact.
10. Khi gửi file cho bên thứ ba, thực hiện kiểm tra nội dung và quyền chia sẻ trước.

Một recording không nên được duy trì vô hạn mà không có ownership, retention và giám sát dung lượng. **Bật recording là thao tác chẩn đoán trên JVM thật**, cần quản trị như thay đổi vận hành khác.

## 14. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| `jcmd -l` không thấy JVM | Khác user, namespace/container hoặc process không hỗ trợ attach | Kiểm tra PID/OS user, container PID namespace và attach policy |
| `Could not attach` / permission denied | Quyền OS hoặc JVM chặn attach | Chạy đúng account/host, xem chính sách bảo mật |
| `Unknown diagnostic command` | JVM/provider không hỗ trợ lệnh hoặc sai tên | `jcmd PID help`, đúng JDK |
| `JFR.start` báo name trùng hoặc thông số không hợp lệ | Recording name/options xung đột | `JFR.check` và đổi name/settings |
| `JFR.start maxsize=...` lỗi | Giá trị nhỏ hơn giới hạn chunk hoặc sai suffix | Xem `help JFR.start` và tăng size phù hợp |
| `JFR.check` không thấy recording | JVM sai PID, recording đã stop/auto-finish hoặc start chưa thành công | Kiểm tra đúng target/tiến trình và `duration` |
| `JFR.dump` không tạo file | Path sai, quyền ghi thiếu, ổ đĩa đầy, quoting shell bị tách | Dùng path phù hợp, kiểm tra thông báo của jcmd |
| File xuất hiện ở thư mục khác | Relative filename được JVM target diễn giải | Xem file path trả về; dùng absolute path đúng |
| `JFR.dump` thành công nhưng ít event | Event tắt, sampling/threshold, start quá muộn hoặc retention | Xem settings, thời điểm start và JFR summary |
| `JFR.stop` xong không thấy file | Không cấu hình filename và chưa dump | Dump trước hoặc stop với filename |
| Dump sau stop thất bại | Recording không còn chạy | Dump trước stop hoặc lưu file trong bước stop |
| `jfr summary` không đọc được | File rỗng/cắt/không hợp lệ, JDK tool khác/không tương thích | Kiểm tra size, format, dùng tool JDK phù hợp |
| Custom event không xuất hiện | Recording chưa start, event không enable hoặc dump quá sớm | Kiểm tra settings và thời gian ghi |
| Overhead cao | `profile`, events quá nhiều, stack trace/GC roots | Giảm scope, threshold, duration và đo thực tế |
| JFR ghi nhiều file làm đầy disk | Repository/exports không được quản lý | maxage/maxsize + xóa export theo retention |
| Operator stop nhầm recording | Nhiều recordings, name không rõ | `JFR.check` rồi stop đúng name |
| Trường hợp Windows path có dấu cách | Shell tách argument của filename | Quote/escape hợp lệ hoặc dùng relative path ở JVM target |
| JFR không ghi đủ các sự kiện trước incident | Không record lúc đó hoặc dữ liệu cũ đã bị evict | Baseline rolling, retention và trigger dump phù hợp |

**Không dùng workaround lỗi thời** như yêu cầu commercial unlock flag trên Java 11+; hãy kiểm tra JDK/provider và command help thực tế.

## 15. Kịch bản vận hành thực tế

### Kịch bản A — baseline rolling, dump khi incident

Bạn có một Java service chạy dài và muốn giữ vài phút dữ liệu:

```bash
jcmd 12345 JFR.start name=Baseline settings=default disk=true maxage=15m maxsize=128m
```

Khi incident xảy ra:

```bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=Baseline filename=incident-snapshot.jfr
```

Sau snapshot, Baseline vẫn tiếp tục nếu bạn chưa stop. Đây là cách thu thập bối cảnh gần sự cố mà không cần restart chỉ để chẩn đoán.

### Kịch bản B — profile CPU ngắn hạn

```bash
jcmd 12345 JFR.start name=CpuSpike settings=profile duration=2m filename=cpu-spike.jfr
```

Kết thúc duration, recording tự dừng; bạn có thể đọc file. Nếu muốn dump sớm trước khi hết hạn, dùng `JFR.dump name=CpuSpike filename=partial-cpu.jfr` khi recording vẫn còn chạy.

### Kịch bản C — một snapshot rồi dừng và lưu

```bash
jcmd 12345 JFR.start name=Investigate settings=profile disk=true maxage=5m maxsize=64m
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=Investigate filename=before-stop.jfr
jcmd 12345 JFR.stop name=Investigate filename=final.jfr
```

Hai tệp có thể có những khoảng sự kiện trùng nhau. Không cộng tổng số event của chúng như hai thời kỳ độc lập nếu không đối chiếu timestamps.

## 16. Bài tập và đáp án

**Bài 1.** Lệnh nào khởi tạo một recording mới trên JVM đang chạy? **`jcmd PID JFR.start`**, kết hợp settings/name nếu cần.

**Bài 2.** `JFR.check` có dừng hoặc xuất file không? **Không**. Nó xem trạng thái recording.

**Bài 3.** `JFR.dump` có dừng recording không? **Không**; chỉ tạo snapshot. Recording vẫn tiếp tục nếu không stop.

**Bài 4.** Muốn dừng và lưu dữ liệu trong một lệnh thì làm gì? Dùng **`JFR.stop name=... filename=...`** nếu runtime hỗ trợ cú pháp đó.

**Bài 5.** Vì sao `JFR.stop name=Demo` có thể không tạo file? Nếu không chỉ định filename hoặc chưa dump trước đó, dữ liệu có thể bị bỏ.

**Bài 6.** `settings=default` hay `settings=profile` thường phù hợp với baseline dài hạn hơn? **default**, vì hướng tới overhead thấp; vẫn phải đo trên workload.

**Bài 7.** `maxage=10m` có tự stop recording sau 10 phút không? **Không**; đó là retention window, không phải duration.

**Bài 8.** Một JVM có recording Baseline và Incident. Muốn dump chỉ Incident, bạn nên viết gì? **`JFR.dump name=Incident filename=incident.jfr`**.

**Bài 9.** Bạn chạy `jcmd` từ thư mục khác JVM và không thấy `snapshot.jfr` ở terminal của mình. Vì sao? Relative path có thể được target JVM xử lý theo **working directory của target**, xem output jcmd.

**Bài 10.** `JFR.dump` tạo file hợp lệ nhưng custom event không xuất hiện. Có khẳng định ứng dụng chưa phát event không? **Không**; có thể event chưa được bật, nằm ngoài recording interval hoặc bị retention lọc mất.

**Bài 11.** Có nên dùng `-XX:+UnlockCommercialFeatures` để bật JFR trên JDK 11+ hiện đại không? **Không**; đó là hướng dẫn lịch sử đã lỗi thời.

**Bài 12.** Một file `.jfr` có được coi là dữ liệu hoàn toàn không nhạy cảm để đăng lên ticket công khai không? **Không**; phải kiểm tra nội dung, quyền truy cập, retention và bảo vệ thông tin.

### Checklist trước khi thao tác trên production

1. Đã xác minh **đúng host, user, JVM và PID** chưa?
2. Có đọc `jcmd PID help JFR.start/check/dump/stop` trên runtime thật?
3. Có đặt **name duy nhất** và ghi lại recording ID/time?
4. `settings=default` hay `profile` đã phù hợp mục tiêu?
5. Có giới hạn `duration/maxage/maxsize` và đo overhead?
6. Có biết rõ `JFR.dump` **không dừng**, còn `JFR.stop` **dừng**?
7. Đã lên kế hoạch **đường dẫn file** và quyền ghi của JVM target?
8. Sau dump đã kiểm tra file bằng `jfr summary`/JMC?
9. Có tránh các event quá chi tiết, GC root path và overhead không cần thiết?
10. File JFR được bảo vệ, mã hóa, phân quyền và xóa theo retention?
11. Có chạy kiểm tra với **JDK 11** nếu cần cam kết runtime 11, ngoài kiểm tra `javac --release 11`?
12. Không dùng hướng dẫn/flag thương mại đã lỗi thời?

## Tài liệu chính thức và nguồn nên tra cứu

- [Oracle Java SE 11 — jcmd Tool](https://docs.oracle.com/en/java/javase/11/tools/jcmd.html): các diagnostic commands JFR và cú pháp Java 11.
- [Oracle Java SE 25 — jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): JFR.start/check/dump/stop và các option hiện hành.
- [Oracle Java SE 25 — jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): đọc và phân tích file recording.
- [Oracle Java SE 11 — jdk.jfr Package](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html): API Event/Recording cho JFR.
- [Oracle Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): custom event, `commit()`, metadata.
- [Oracle Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): điều khiển recording bằng Java API.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): tích hợp JFR vào OpenJDK 11.
- [dev.java — Introduction to JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/intro/): cách dùng JFR, model dữ liệu event và đặc điểm vận hành.
- [JDK Mission Control](https://openjdk.org/projects/jmc/): công cụ đồ họa để phân tích recording.

**Kết luận:** `JFR.start` bắt đầu thu sự kiện; `JFR.check` xem các recording đang có; `JFR.dump` tạo bản chụp **mà không dừng**; `JFR.stop` kết thúc recording và nên được dùng cùng chiến lược lưu dữ liệu rõ ràng. Trên Java 11+, đây vẫn là quy trình JFR chuẩn hiện hành. Quan trọng nhất là **đúng PID, đúng recording name, chọn settings phù hợp, kiểm soát thời gian/dung lượng và bảo vệ file .jfr**.