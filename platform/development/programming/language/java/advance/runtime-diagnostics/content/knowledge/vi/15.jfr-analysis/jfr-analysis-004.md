# 15.4. Dùng `jfr view` khi phiên bản công cụ hỗ trợ để xem dữ liệu tổng hợp

Một tệp Java Flight Recorder (JFR) có thể chứa hàng nghìn hoặc hàng triệu sự kiện từ JVM và ứng dụng. In toàn bộ sự kiện bằng `jfr print` thường quá dài để trả lời nhanh những câu hỏi như “GC pause đang tốn bao nhiêu thời gian?”, “những kiểu đối tượng nào có nhiều mẫu cấp phát?” hoặc “những method nào xuất hiện nhiều trong CPU samples?”. **`jfr view`** giúp tạo **bảng tổng hợp có sẵn** từ các sự kiện trong tệp `.jfr` và hiển thị trực tiếp ở terminal.

Điều kiện quan trọng của đề bài là **phiên bản công cụ**: subcommand `jfr view` được bổ sung vào **JDK 21**; `jfr` của JDK 17 có `summary`/`print` nhưng **không có `view`**. Một số nhà cung cấp hoặc bản phân phối có thể backport hay thay đổi tính năng, vì vậy **kiểm tra bản `jfr` thực sự đang chạy và help của nó**, không chỉ nhìn phiên bản ứng dụng tạo recording.

Mục tiêu của bài: kiểm tra khả năng hỗ trợ, tạo/kiểm tra recording, tìm view phù hợp, đọc đúng ý nghĩa bảng tổng hợp, phân biệt dữ liệu vắng mặt với “không có vấn đề”, xử lý lỗi tương thích và biết phương án thay thế trên JDK cũ.

## 1. Phân biệt các công cụ đọc JFR

| Lệnh/công cụ | Kết quả chính | Khi nào nên dùng |
| --- | --- | --- |
| `jfr summary app.jfr` | Thống kê recording và loại sự kiện, số lượng, dung lượng. | **Bước đầu**: file có đọc được, thời gian ghi và event nào xuất hiện? |
| `jfr metadata app.jfr` | Mô tả các event type, field và category. | Muốn kiểm tra schema/field trước khi lọc hoặc phân tích. |
| `jfr print --events ... app.jfr` | In **từng sự kiện** được chọn, có thể ở định dạng văn bản/JSON/XML. | Cần timestamp, stack trace, thông tin chi tiết của một event cụ thể. |
| `jfr view <view> app.jfr` | Bảng thống kê/nhóm/tổng hợp theo **view** có sẵn hoặc cách trình bày cho event type được hỗ trợ. | Cần bức tranh tổng quan nhanh bằng CLI. |
| `jcmd <pid> JFR.view ...` | Hiển thị view từ dữ liệu JFR của JVM đang chạy **nếu diagnostic command được hỗ trợ**. | Muốn xem gần thời gian thực mà không phải mở file dump trước. |
| JDK Mission Control (JMC) | Giao diện đồ họa: timeline, biểu đồ, tương quan nhiều loại sự kiện. | Phân tích sâu, chọn khoảng thời gian, drill-down và đọc stack traces trực quan. |

**`summary` không thay thế `view`.** `summary` chủ yếu cho biết **có bao nhiêu event** và chúng chiếm bao nhiêu dung lượng; một view như `gc-pauses` nhóm dữ liệu theo góc nhìn về pause, trong khi `allocation-by-class` liên quan đến các mẫu cấp phát theo class. Đồng thời, **`view` không thay thế `print`** nếu cần xem một event xảy ra chính xác lúc nào và có những field nào.

`jfr view` **đọc tệp recording đã có**; chạy lệnh này không tự ghi JFR vào ứng dụng. Hãy đảm bảo file `.jfr` thực sự tồn tại và chứa các event phù hợp với câu hỏi đang phân tích.

## 2. Kiểm tra phiên bản và khả năng hỗ trợ trước tiên

Các lệnh sau chạy trên terminal có cài **JDK** (không chỉ runtime tối giản thiếu công cụ):

```bash
java -version
jfr --version
jfr help
jfr help view
```

- `java -version` cho biết `java` mà shell sẽ chạy.
- `jfr --version` cho biết phiên bản của **công cụ `jfr`**; hai chương trình có thể trỏ vào **hai JDK khác nhau** do `PATH` và `JAVA_HOME`.
- `jfr help view` (hoặc `jfr --help view` nếu được help của chính phiên bản đó xác nhận) hiển thị cú pháp và **danh sách view** khả dụng.
- Nếu công cụ báo không nhận ra `view`, không cố chạy lại với một tên view khác. Hãy dùng JDK có hỗ trợ `jfr view` (JDK 21+ theo tài liệu chính thức) hoặc chuyển sang `jfr summary`/`jfr print`/JMC.

Ví dụ một môi trường có **JDK 17 chạy service** và **JDK 21 cài riêng để phân tích** là hoàn toàn hợp lý: cần chạy executable `jfr` từ JDK 21 để dùng `view`. Tuy nhiên, phải xác minh khả năng **đọc file `.jfr` cụ thể** qua `jfr summary` trước khi diễn giải kết quả; đừng mặc định mọi recording của mọi JDK/vendor đều tương thích tuyệt đối.

Trên Linux/macOS, khi có nhiều JDK, có thể chỉ rõ đường dẫn (đường dẫn bên dưới là **ví dụ**, không phải đường dẫn có sẵn ở mọi máy):

```bash
/opt/jdk-21/bin/jfr --version
/opt/jdk-21/bin/jfr help view
/opt/jdk-21/bin/jfr summary recording.jfr
```

Trên Windows, dùng `<JDK21_HOME>\bin\jfr.exe` trong PowerShell/CMD sau khi thay placeholder bằng đường dẫn thực. Không dùng `java -version` làm bằng chứng duy nhất rằng `jfr` trên `PATH` có cùng phiên bản.

## 3. Cú pháp chính của `jfr view`

Theo tài liệu JDK 21:

```text
jfr view [--verbose] [--width <integer>] [--truncate <mode>]
         [--cell-height <integer>] <view> <file>
```

Trong đó:

- `<view>` là tên một **bảng view** (ví dụ `gc-pauses`, `thread-count`, `allocation-by-class`) hoặc một **event type** mà công cụ hỗ trợ hiển thị. Danh sách khả dụng do `jfr help view` cung cấp.
- `<file>` là đường dẫn tệp JFR, ví dụ `recording.jfr`; có thể dùng đường dẫn tuyệt đối.
- `--width N` đặt độ rộng tối đa của bảng (đơn vị ký tự); hữu ích khi tên class, method hoặc path dài.
- `--cell-height N` giới hạn số dòng trình bày bên trong một ô bảng, không phải khoảng thời gian đo.
- `--truncate beginning|end` quyết định giữ phần đầu hay cuối của text vượt quá độ rộng ô; mặc định cắt phần cuối theo tài liệu JDK 21.
- `--verbose` in ra **truy vấn/định nghĩa tạo nên view** để hiểu dữ liệu được lọc/nhóm/tính thế nào. Nó không bật thêm event bị thiếu trong file.

Thứ tự: **options đứng trước tên view**, tên file đứng sau view.

```bash
# Danh sách view và help của đúng JDK đang dùng
jfr help view

# Ví dụ bảng tổng hợp
jfr view gc-pauses recording.jfr
jfr view thread-count recording.jfr
jfr view allocation-by-class recording.jfr

# Tăng độ rộng bảng, xem định nghĩa của view
jfr view --width 120 --verbose gc-pauses recording.jfr

# Chọn cách cắt chuỗi dài và số dòng trong ô
jfr view --width 140 --truncate beginning --cell-height 3 allocation-by-site recording.jfr
```

Tên view có thể thay đổi giữa các phiên bản. Những tên trên được cung cấp trong nhóm view ban đầu của JDK 21; **chỉ dùng khi `jfr help view` của chính executable đang chạy liệt kê tên đó**. Không tự tạo tên như `cpu-hotspots` hoặc `gc-summary` theo trí nhớ rồi coi là cú pháp chuẩn.

Các lệnh đặc biệt trên JDK 21+:

```bash
# Liệt kê những event type có thể đưa trực tiếp vào view theo file
jfr view types recording.jfr

# In lần lượt nhiều view định nghĩa sẵn (có thể rất dài)
jfr view all-views recording.jfr

# Hiển thị tất cả event theo cơ chế view (có thể cực lớn)
jfr view all-events recording.jfr
```

`all-views` và `all-events` thường sinh nhiều dữ liệu và mất thời gian; hãy ưu tiên một view đúng mục đích. `jfr view types` giúp kiểm tra **event type có trong recording**; nó không chứng minh event đã được cấu hình hoặc ghi đủ số mẫu để kết luận mọi hoạt động của chương trình.

## 4. Chuẩn bị một recording phù hợp

### 4.1. Chụp từ JVM đang chạy bằng `jcmd`

Trên một JVM có quyền attach (cùng host/user phù hợp), tạo recording trong cửa sổ hai phút:

```bash
# <pid> phải được thay bằng PID thật
jcmd <pid> JFR.start name=diag_2m settings=profile duration=120s filename=/tmp/diag-2m.jfr

# Chỉ sau khi recording hoàn tất và tệp đã được ghi:
jfr summary /tmp/diag-2m.jfr
jfr view gc-pauses /tmp/diag-2m.jfr
```

`JFR.start` hoạt động trên JVM, còn `jfr summary/view` đọc **tệp**. `duration=120s` yêu cầu recording dừng sau hai phút; khi có `filename`, dữ liệu được ghi vào tệp khi recording dừng. Đường dẫn phải được **JVM đích** truy cập/ghi được. Nếu JVM chạy trong container, `/tmp/diag-2m.jfr` thuộc filesystem của **container/JVM**, không nhất thiết là `/tmp` của máy đang chạy lệnh phân tích.

`settings=profile` có thể bật nhiều sự kiện hơn và tạo overhead/size lớn hơn cấu hình `default`. Chọn khoảng thời gian đủ đại diện, nhưng không ghi profile liên tục một cách vô hạn chỉ để thử các view.

Khi recording đã chạy và cần snapshot trước khi nó dừng:

```bash
jcmd <pid> JFR.dump name=diag_2m filename=/tmp/diag-snapshot.jfr
```

`JFR.dump` ghi snapshot và **recording có thể tiếp tục chạy**. Phân biệt với `JFR.stop` là dừng recording. Kiểm tra `jcmd <pid> help JFR.dump` và quyền ghi tệp nếu câu lệnh báo lỗi; không kỳ vọng file nằm trên máy trạm nếu JVM ở máy khác.

### 4.2. Chụp lúc khởi động

Một ví dụ khác: ghi từ lúc service bắt đầu, tự xuất file khi JVM thoát bình thường:

```bash
java -XX:StartFlightRecording=filename=startup.jfr,settings=profile,dumponexit=true \
  -jar app.jar
```

Không dùng ví dụ này như bảo đảm rằng **mọi kiểu crash/SIGKILL/OOMKilled** đều có file hoàn chỉnh. Nếu cần bảo toàn chứng cứ sự cố, hãy chuẩn bị disk, quyền ghi và quy trình thu thập trước. Sau khi có file, có thể dùng `jfr summary` và `jfr view` trên máy phân tích phù hợp.

### 4.3. Chọn sự kiện trước, rồi mới chọn view

Một view chỉ tổng hợp **những sự kiện đã được ghi**. Nếu recording dùng `default` hoặc `profile` nhưng event mục tiêu bị tắt, chu kỳ ghi quá ngắn, event bị lọc bởi threshold, hoặc sampling bỏ qua hoạt động ngắn, view có thể rỗng.

Ví dụ:
- `allocation-by-class` dựa trên các event cấp phát/sampling được cấu hình, **không phải bảng toàn bộ từng object** của Java heap.
- `hot-methods` thường dựa vào samples, **không phải phép đo thời gian CPU chính xác ở từng dòng code**.
- `file-reads-by-path` không nhất thiết ghi mọi lần đọc file ngắn nếu cấu hình threshold/sampling không bao phủ.
- `gc-pauses` chỉ có ý nghĩa khi khoảng recording có những GC event phù hợp; một recording ngắn có thể chưa có GC.

Do đó khi view trống, kiểm tra **event name**, `jfr summary`, `jfr metadata` và cấu hình recording trước khi nhận xét hoạt động thực tế bằng 0.

## 5. Bài thực hành Java 17+ — tạo recording có sự kiện biết trước

Để thực hành `jfr view` mà không phụ thuộc một ứng dụng lớn, ví dụ sau dùng **JFR API có từ Java 17** để tạo năm event `demo.BatchStep`, rồi lưu tệp `view-demo.jfr`. Phần **tạo recording** có thể chạy bằng JDK 17; phần **`jfr view`** cần executable có hỗ trợ, ví dụ JDK 21+.

Lưu tệp `JfrViewDemo.java`:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class JfrViewDemo {
    @Name("demo.BatchStep")
    @Label("Batch step")
    @Category({"Demo", "Batch"})
    public static final class BatchStepEvent extends Event {
        @Label("Items processed")
        public int items;
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.enable(BatchStepEvent.class)
                    .withThreshold(Duration.ZERO);
            recording.start();

            for (int i = 1; i <= 5; i++) {
                BatchStepEvent event = new BatchStepEvent();
                event.items = i * 10;
                event.begin();
                Thread.sleep(50);
                event.commit();
            }

            recording.stop();
            recording.dump(Path.of("view-demo.jfr"));
        }

        System.out.println("Created view-demo.jfr");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên trong thư mục có quyền ghi:

```bash
javac JfrViewDemo.java
java JfrViewDemo
```

**Stdout của chương trình nếu chạy thành công:**

```text
Created view-demo.jfr
```

Chương trình bật rõ loại event `demo.BatchStep` với ngưỡng bằng 0, gọi `begin()/commit()` năm lần rồi `stop()/dump()` recording. Dung lượng file, timestamp, số loại event bổ sung và cách công cụ định dạng bảng có thể thay đổi theo JDK. Chương trình không có mục đích mô phỏng tải CPU/GC thực tế; nó nhằm giúp kiểm tra **đường đi ghi – đọc – xem tổng hợp**.

Trên JDK 21+, đọc file như sau:

```bash
jfr --version
jfr summary view-demo.jfr
jfr view types view-demo.jfr

# Tên event tự định nghĩa, với bản jfr view hỗ trợ event-type view
jfr view demo.BatchStep view-demo.jfr

# Xem các event riêng lẻ để đối chiếu
jfr print --events demo.BatchStep view-demo.jfr
```

Đối với loại event tùy chỉnh này, các trường `items` được phát ra lần lượt **10, 20, 30, 40, 50** và có các timestamp/duration thực tế do JVM ghi. **Không giả định `jfr view` sẽ tự tính “tổng items = 150”** khi dùng tên event: việc nhóm, công thức và cột xuất ra phụ thuộc định nghĩa view/event type. Nếu muốn xác định tổng nghiệp vụ từ năm event trong ví dụ, cộng các field `items` ở từng event hoặc xử lý có chủ đích; không suy diễn từ một nhãn bảng mà không kiểm tra.

Nếu dùng `jfr` của JDK 17 cho cùng tệp, có thể chạy `jfr summary` và `jfr print`, nhưng `jfr view` **không được hỗ trợ** theo tài liệu JDK 17. Bước phân tích với JDK 21+ dùng chính tệp `view-demo.jfr` vừa tạo, không phải một recording mới.

## 6. Chọn đúng view theo câu hỏi chẩn đoán

Những view bên dưới là **ví dụ có trong danh sách view của JDK 21**. Danh sách cụ thể nên xác nhận bằng `jfr help view` trên máy đang dùng.

| Câu hỏi thực tế | View gợi ý | Cách đọc, giới hạn cần nhớ |
| --- | --- | --- |
| GC pause có ảnh hưởng latency? | `gc-pauses`, `gc-pause-phases`, `gc` | Xem count/tổng thời gian/phân bố event và pha; kiểm tra p95/p99 bằng timeline và event cụ thể nếu cần. |
| Bộ nhớ được cấp phát ở đâu? | `allocation-by-class`, `allocation-by-site`, `allocation-by-thread` | Các mẫu theo kiểu, site, thread; dữ liệu sampling và cấu hình event ảnh hưởng kết quả. |
| Code thường xuất hiện trong CPU samples? | `hot-methods` | Gợi ý hotspot; đọc stack samples, không quy trực tiếp số mẫu thành số millisecond chính xác. |
| Có vấn đề thread? | `thread-count`, `thread-cpu-load`, `thread-allocation` | Xem xu hướng/sự phân bố theo event được ghi, liên hệ thread states và workload. |
| IO nào đáng chú ý? | `file-reads-by-path`, `file-writes-by-path`, `socket-reads-by-host` | Các event vượt threshold hoặc được bật; không phải inventory mọi syscall. |
| Lỗi/exception nào lặp lại? | `exception-by-class` **chỉ nếu help liệt kê**; thông dụng hơn là `exception-by-site`, `exception-by-message` | Exception events có thể tốn overhead; xem exception class, nơi xảy ra và cấu hình thu. |
| Class loader hoạt động thế nào? | `class-loaders`, `longest-class-loading` | Đối chiếu số lần nạp/lifecycle; bản thân view không chứng minh loader leak. |
| Khác biệt môi trường? | `jvm-flags`, `container-memory-usage`, `cpu-load` | Cấu hình và mức sử dụng quan sát được; gắn với thời gian recording. |

**Không dùng riêng một bảng để kết luận nguyên nhân gốc.** Ví dụ `hot-methods` có tỷ lệ samples cao ở phương thức A có thể là hậu quả của workload đi qua A nhiều nhất, chứ không đồng nghĩa A đang lỗi hoặc cần tối ưu. `allocation-by-class` thấy nhiều `byte[]` cũng cần kiểm tra ai cấp phát, tuổi đời đối tượng và tác động GC.

### Ví dụ đọc `gc-pauses` theo số liệu giả định

Giả sử một recording kéo dài **120 giây**, event liên quan cho thấy **120 lần pause**, tổng pause time **480 ms**. Các phép tính độc lập:

- **Pause trung bình** = `480 ms / 120 = 4 ms` cho mỗi lần.
- **Tỷ lệ wall-clock dành cho pause** (trong mô hình tổng pause phù hợp không tính trùng) = `0,48 s / 120 s = 0,4%`.

Đây chỉ là dữ liệu **giả định để luyện đọc**, không phải output mặc định của `jfr view` và không phải ngưỡng “tốt/xấu” áp dụng mọi hệ thống. Không thể suy ra **pause dài nhất**, `p95` hay `p99` từ riêng tổng và số lần. Một vài pause kéo dài hàng trăm ms có thể gây tail latency cao dù trung bình 4 ms.

Để biết những pause dài đó xảy ra lúc nào, chuyển sang `jfr print --events jdk.GarbageCollection ...` hoặc JMC và dùng event/pha GC phù hợp. Đối chiếu request latency/traffic cùng khoảng thời gian; tránh đọc percent hoặc duration mà không kiểm tra đơn vị.

### Vì sao “Top 10” cần thận trọng?

Các view hiển thị những mục đứng đầu theo thống kê của **view đó**; có thể là số event, số mẫu, tổng duration hoặc một phép xếp hạng khác. Trước khi đưa ra kết luận:

1. Xem tên cột, đơn vị và mô tả view.
2. Dùng `--verbose` để đọc định nghĩa/truy vấn của view, nhất là cột có nhãn rút gọn.
3. Kiểm tra recording settings, threshold và mẫu.
4. Nếu cần bằng chứng về một lần xảy ra cụ thể, dùng `jfr print` hoặc timeline của JMC.

“Không nằm trong Top 10” **không đồng nghĩa không có vấn đề**: bảng có thể đã giới hạn số dòng, event type không được bật, hay dữ liệu bị sampling bỏ sót.

## 7. Điều chỉnh khả năng đọc của bảng ở terminal

### 7.1. Tên class/method/path bị cắt

```bash
jfr view --width 160 --cell-height 4 allocation-by-site recording.jfr
```

`--width` tăng độ rộng bảng, giúp thấy những stack trace/path dài. `--cell-height` tăng dòng hiển thị trong một ô nhưng không làm tăng số sự kiện được ghi. Nếu terminal vẫn nhỏ, chuyển đầu ra sang file text theo công cụ shell hoặc dùng JMC để mở tương tác; không coi dấu `...` là một phần tên Java.

### 7.2. Chọn giữ phần đầu/cuối chuỗi

```bash
jfr view --width 120 --truncate beginning file-reads-by-path recording.jfr
jfr view --width 120 --truncate end file-reads-by-path recording.jfr
```

Cắt phần đầu có thể giữ **tên file ở cuối path** dễ nhận biết; cắt phần cuối có thể giữ **prefix/thư mục gốc**. Đây là chỉ thay đổi cách hiển thị, không thay đổi recording. Khi làm báo cáo điều tra, đừng sao chép path đã bị cắt rồi coi đó là toàn bộ path.

### 7.3. Xem truy vấn view được dùng

```bash
jfr view --verbose hot-methods recording.jfr
```

`--verbose` giúp quan sát cơ chế lọc/nhóm/thống kê mà view sử dụng ở phiên bản đó. Không nhầm đây là một cách **bật stack traces hoặc thay đổi cấu hình JFR**; file đã ghi xong, cờ hiển thị không thể bổ sung các event thiếu.

## 8. Đọc dữ liệu đang chạy bằng `jcmd JFR.view` khi có hỗ trợ

Bên cạnh lệnh đọc file, trên JDK hỗ trợ diagnostic command tương ứng, có thể xem view trực tiếp từ một JVM đang chạy:

```bash
# Lấy PID từ môi trường thực tế
jcmd -l

# Kiểm tra JVM mục tiêu có hỗ trợ hay không
jcmd <pid> help JFR.view

# Ví dụ xem view từ dữ liệu của JVM, không cần chỉ định file .jfr
jcmd <pid> JFR.view gc-pauses
```

`jcmd` cần quyền attach phù hợp và phải nhắm đúng JVM/PID. **`jfr view` và `jcmd JFR.view` không có cùng giao diện tham số:**

| | `jfr view` | `jcmd JFR.view` |
| --- | --- | --- |
| Nguồn | Một tệp `.jfr` có sẵn. | Dữ liệu JFR của JVM đang chạy. |
| Đầu vào chính | `<view> <file>`. | `<pid> JFR.view <view>`. |
| Quyền | Đọc được tệp từ máy phân tích. | Có quyền attach vào JVM. |
| Cửa sổ thời gian | Nội dung recording file. | Phụ thuộc dữ liệu còn giữ và những tùy chọn như `maxage`/`maxsize` mà JVM hỗ trợ. |
| Kiểm tra hỗ trợ | `jfr help view`. | `jcmd <pid> help JFR.view`. |

Trên những phiên bản hỗ trợ, `JFR.view` thường có tùy chọn như `maxage`, `maxsize`, `width`, `verbose`. Xem help của **JVM đích** trước khi dùng; không tự truyền nguyên cú pháp `--width` của `jfr` sang `jcmd` vì `jcmd` dùng tham số kiểu `key=value`/positionals riêng.

Nếu JVM không hỗ trợ `JFR.view` hoặc không thể attach, vẫn có thể tạo/dump JFR bằng cách được phép rồi phân tích **offline** bằng JDK mới có `jfr view`.

## 9. Phương án an toàn trên JDK 17 hoặc khi `view` không có

Đối với JDK 17, `jfr summary`, `jfr print`, `jfr metadata` vẫn hữu ích:

```bash
# Xác định event nào hiện diện, số lượng và phạm vi recording
jfr summary recording.jfr

# Xem schema event đã ghi
jfr metadata recording.jfr

# Chỉ in các event GC đã ghi (tên event nên kiểm tra với summary)
jfr print --events jdk.GarbageCollection recording.jfr

# Nếu cần xử lý bằng chương trình ngoài, có thể lấy JSON
jfr print --json --events jdk.GarbageCollection recording.jfr
```

`jfr print --json` cho dữ liệu event dạng machine-readable để viết chương trình tổng hợp theo nghiệp vụ; cần xử lý cấu trúc JSON đúng cách, không regex trên output dạng bảng. Với file lớn, `print` tất cả event có thể rất tốn bộ nhớ, thời gian và dung lượng stdout. Hãy lọc theo event type và chỉ thu những field cần thiết.

Một lựa chọn khác là **mở bằng JDK Mission Control**: lọc khoảng thời gian, xem GC timeline, CPU, allocation, thread, I/O, stack traces và drill-down. Nếu cần view cho mục đích nhanh mà service vẫn dùng JDK 17, hãy thử executable `jfr` từ **JDK 21+ trên máy phân tích**, sau khi `summary` xác nhận file tương thích. Không cần nâng Java runtime production chỉ để xem một bảng tổng hợp từ tệp đã có.

## 10. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| `Unrecognized command: view` hoặc help không có `view` | `jfr` quá cũ hoặc bản phân phối khác. | `jfr --version`, đường dẫn executable; dùng JDK 21+ có tính năng hoặc fallback. |
| `jfr: command not found` / không tìm thấy `jfr.exe` | Dùng JRE tối giản, JDK chưa cài hoặc `PATH` sai. | Tìm `<JDK_HOME>/bin/jfr` và chạy bằng đường dẫn đầy đủ. |
| `Unknown view` | Sai tên view hoặc tên không tồn tại ở phiên bản này. | `jfr help view`; phân biệt `gc-pauses` với tên bạn tự nghĩ ra. |
| Không mở được `recording.jfr` | Sai path, file không được tạo/ghi xong, quyền đọc hoặc file hỏng. | `ls -lh`/`dir`, `jfr summary`, kiểm tra log JFR/dung lượng file. |
| View hiển thị ít hoặc không có dòng | Event chưa bật, threshold lọc bỏ, sample hiếm, recording ngắn, view không liên quan. | `jfr summary`, `jfr metadata`, cấu hình `.jfc` và workload thực tế. |
| Nhiều tên dài bị `...` | Bảng hẹp/truncate display. | `--width`/`--cell-height`, thay `--truncate`, xem raw event nếu cần. |
| `all-views` quá nhiều output | Gọi quá rộng trên file lớn. | Chọn từng view theo giả thuyết, chỉ chạy `all-views` khi thật cần. |
| Số thống kê khác dashboard | Khác cửa sổ thời gian, event type, sampling, aggregation hoặc instance. | Đồng bộ timestamp/timezone, scope JVM, threshold, tên event và công thức. |
| `jcmd ... JFR.view` không tồn tại | JVM đích quá cũ, lệnh không được cung cấp hoặc thiếu attach permission. | `jcmd <pid> help`; chuyển sang phân tích file bằng `jfr view`. |
| View có vẻ “không chính xác” về allocation | Sampling khiến con số không phải tổng số allocation thực. | Xem cấu hình event sampling và đối chiếu profiler/metric allocation khác. |

### Bẫy về phiên bản file và tên event

Phiên bản **tạo** recording, phiên bản **đọc** recording và **loại event được ghi** là ba thông tin khác nhau. Một recording từ JDK 17 có thể được mở bằng công cụ JDK 21 để dùng `view`, nhưng bạn vẫn cần kiểm tra file, event type và schema bằng `summary`/`metadata`. Ngược lại, file mới có event type mà tool cũ không biết không nên bị suy diễn là “không có sự kiện”. Tương tự, một view có sẵn trong help không chứng minh recording đã bật event tương ứng.

Nên ghi cả:
- JDK/vendor/version của ứng dụng được record.
- JDK/vendor/version của `jfr` đang phân tích.
- Recording settings (`default`/`profile`/custom), start-end time, duration, kích thước file và instance/PID.
- Tên view được chạy, các tham số display, tên/cột/đơn vị event được diễn giải.

## 11. Mẫu quy trình thực tế khi được giao một file `.jfr`

**Tình huống:** đội vận hành chuyển `incident.jfr` và nghi service có pause GC ảnh hưởng độ trễ.

1. **Xác nhận tool:** `jfr --version` và `jfr help view`; nếu không có `view`, chọn công cụ mới hơn hoặc fallback.
2. **Kiểm tra nguồn:** `jfr summary incident.jfr` để biết recording hợp lệ, thời gian và event GC có xuất hiện.
3. **Chọn view:** `jfr view gc-pauses incident.jfr`; nếu cần pha GC, dùng `gc-pause-phases` khi có trong help.
4. **Đọc đúng phép tính:** phân biệt count, tổng thời gian, trung bình, percent, các phần trăm phân bố, và thời gian của từng event. Nếu bảng chỉ có aggregate, không tự suy ra thời điểm một spike.
5. **Đối chiếu chi tiết:** `jfr print --events jdk.GarbageCollection incident.jfr`, JMC timeline và các GC event liên quan; đồng bộ log request latency/traffic.
6. **Viết kết luận có phạm vi:** “Trong recording 14:00–14:02 trên instance A, nhóm GC pause được ghi có ...” thay vì “GC luôn gây mọi lần chậm của hệ thống”.
7. **Lưu lệnh tái hiện:** ghi rõ version `jfr`, tên view và đường dẫn/tên file để người khác kiểm tra lại cùng dữ liệu.

Với giả thuyết **allocation pressure**, thay các view GC bằng `allocation-by-class`/`allocation-by-site` và xác minh sampling; với giả thuyết **CPU hot path**, dùng `hot-methods` và kiểm tra stack/sample; với vấn đề **thread/IO**, chọn view chuyên biệt rồi mở event chi tiết khi cần.

## 12. Những nhầm lẫn cần tránh

- **“JDK 17 có JFR nên chắc chắn có `jfr view`.”** Sai: `view` được bổ sung ở JDK 21, còn `summary`/`print` đã có ở JDK 17.
- **“`jfr view` tự thu thập dữ liệu đang chạy.”** Sai: lệnh `jfr view` đọc **file**; `jcmd JFR.view` là giao diện khác cho JVM đang chạy khi hỗ trợ.
- **“Một view trống nghĩa là hoạt động bằng 0.”** Sai: có thể recording không bật event/đủ thời gian hoặc threshold lọc bỏ.
- **“Tên view giống tên event type.”** Không nhất thiết: `gc-pauses` là view tổng hợp; `jdk.GarbageCollection` là tên một loại event.
- **“`jfr summary` là báo cáo hiệu năng hoàn chỉnh.”** Sai: summary có count/size theo event, không có đủ chuỗi thời gian và đường gọi để kết luận nguyên nhân.
- **“`allocation-by-class` phản ánh đầy đủ mọi allocation trên heap.”** Sai: thường phụ thuộc samples/sự kiện được bật.
- **“`hot-methods` chính là % CPU tuyệt đối của từng method.”** Sai: thường là quan sát thống kê từ stack samples; cần chú ý độ đại diện.
- **“Thêm `--verbose` sẽ bổ sung stack traces bị thiếu.”** Sai: đó là tùy chọn **hiển thị định nghĩa view**.
- **“Độ rộng bảng lớn hơn đồng nghĩa recording có thêm dữ liệu.”** Sai: `--width`/`--truncate` chỉ thay layout text.
- **“Tên view trong một bài hướng dẫn luôn áp dụng mọi JDK tương lai.”** Sai: đối chiếu help của công cụ thực tế.
- **“Có thể copy thẳng output bảng rồi parse ổn định như JSON.”** Không đảm bảo: view hướng tới người đọc; để tự động hóa ổn định hơn hãy cân nhắc `jfr print --json` hoặc JFR consumer API và xử lý schema.

## 13. Checklist trước khi gửi kết luận từ `jfr view`

- [ ] Đã xác minh executable `jfr` có `view` bằng `jfr help view`.
- [ ] Tệp `.jfr` đọc được qua `jfr summary`, đúng instance và khoảng thời gian.
- [ ] View chọn theo **câu hỏi**, nằm trong help của phiên bản công cụ.
- [ ] Event cần thiết thực sự có trong file; hiểu recording settings/threshold/sampling.
- [ ] Hiểu cột, đơn vị, công thức tổng hợp; dùng `--verbose` nếu nghi ngờ ý nghĩa.
- [ ] Không suy diễn p95/p99 hoặc nguyên nhân gốc từ bảng aggregate không có dữ liệu tương ứng.
- [ ] Nếu cần timestamp, stack trace, thread, path thật: xem `jfr print` hoặc JMC.
- [ ] Khi chia sẻ báo cáo đã ghi rõ JDK tool version, file, view, thời gian và các giới hạn dữ liệu.

**Ghi nhớ:** `jfr view` là lớp **tổng hợp và trình bày** trên những JFR events **đã được thu**; nó giúp từ file lớn rút ra góc nhìn nhanh trong terminal. Điều kiện tiên quyết là **bản công cụ có hỗ trợ (JDK 21+ theo tài liệu chính thức)**, ghi đủ event đúng loại và hiểu phép thống kê của từng view. Trên JDK cũ hoặc khi bảng không đủ chiều sâu, phối hợp `jfr summary`, `jfr print`, `jfr metadata` và JMC để kiểm chứng.

### Tài liệu tham khảo

- [Oracle JDK 21 — The jfr Command, cú pháp và các tùy chọn `jfr view`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 17 — The jfr Command (chưa có `view`)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [Inside Java — JFR View Command, giới thiệu tính năng ở Java 21 và ví dụ view](https://inside.java/2023/09/26/sip082/)
- [Oracle JDK 21 — The jcmd Command, `JFR.start`/`JFR.dump` và `JFR.view`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 17 — API `jdk.jfr.Recording` cho ví dụ Java](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html)