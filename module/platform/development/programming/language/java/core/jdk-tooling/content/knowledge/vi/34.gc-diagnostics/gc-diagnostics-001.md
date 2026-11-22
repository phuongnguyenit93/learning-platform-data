# GC log: ghi nhận và phân tích Garbage Collection

**GC log** là nhật ký văn bản do Java Virtual Machine (JVM) phát ra để mô tả hoạt động Garbage Collection (GC), các pha của collector, thay đổi heap, nguyên nhân collection và những lần ứng dụng dừng tại safepoint. Từ Java 9, HotSpot dùng **Unified Logging** với tùy chọn `-Xlog`; Java 17+ tiếp tục sử dụng cú pháp này.

GC log giúp trả lời các câu hỏi vận hành: GC xảy ra lúc nào, loại collection nào chạy, vì sao collection được kích hoạt, pause kéo dài bao lâu, heap thay đổi thế nào và collector mất thời gian ở pha nào. Đây là dữ liệu nền tảng để điều tra latency, throughput, allocation pressure và memory pressure. Cần đọc log cùng workload, metrics và cấu hình JVM; một dòng log đơn lẻ không đủ để kết luận memory leak hoặc quyết định tuning.

## 1. Unified Logging và GC log

Trước Java 9, GC logging thường dùng các cờ riêng như `-XX:+PrintGCDetails`, `-XX:+PrintGCDateStamps` và `-Xloggc`. Unified Logging gom các thông điệp chẩn đoán của JVM vào một hệ thống chung, cho phép chọn nội dung theo **tag**, mức độ chi tiết, nơi ghi và định dạng timestamp.

Cú pháp tổng quát:

```text
-Xlog[:[tag-selection][:[output][:[decorators][:output-options]]]]
```

Các phần:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Tag selection | Chọn nhóm thông điệp và mức log | `gc*=info`, `gc+heap=debug` |
| Output | Chọn nơi ghi | `stdout`, `stderr`, `file=gc.log` |
| Decorators | Chọn thông tin đứng trước thông điệp | `time,uptime,level,tags` |
| Output options | Cấu hình file và rotation | `filesize=20M,filecount=5` |

Kiểm tra chính xác các tag, level, decorator và cú pháp được hỗ trợ bởi JDK đang chạy:

```bash
java -Xlog:help
```

Các tag và chi tiết GC phụ thuộc JDK, JVM vendor và garbage collector. Hãy xem trợ giúp trên chính môi trường cần điều tra trước khi dùng một selector cụ thể.

## 2. Bắt đầu với GC log cơ bản

Ghi các thông điệp GC ở mức `info` ra console:

```bash
java -Xlog:gc -jar app.jar
```

Lệnh này chọn tag set `gc` ở mức `info`. Một số thông điệp có thêm tag như `gc,heap`, `gc,start` hoặc `gc,phases` sẽ cần selector phù hợp để xuất hiện.

Để lấy phần lớn nhóm thông điệp có tag `gc`, dùng wildcard:

```bash
java -Xlog:gc*=info -jar app.jar
```

Muốn xem thêm thông tin heap và các pha GC:

```bash
java -Xlog:gc*=debug -jar app.jar
```

Mức `debug` hữu ích khi điều tra nhưng tạo nhiều log hơn. Chỉ tăng độ chi tiết trong khoảng thời gian cần thiết và theo dõi dung lượng log.

Để đồng thời quan sát GC và safepoint:

```bash
java -Xlog:gc*=info,safepoint=info -jar app.jar
```

Không bật `all=trace` như cấu hình mặc định cho production. Nó có thể tạo lượng log rất lớn và làm tăng I/O.

## 3. Hiểu tag, wildcard và level

Mỗi thông điệp có một tập tag và một level.

**Tag** mô tả thành phần hoặc nội dung log. Các tag GC thường gặp trên HotSpot gồm:

| Tag | Nội dung thường gặp |
| --- | --- |
| `gc` | Sự kiện collection và thông tin tổng quan |
| `heap` | Heap occupancy, region và thay đổi bộ nhớ |
| `phases` | Các pha của collection |
| `start` | Bắt đầu collection hoặc một pha |
| `ergo` | Quyết định và chính sách tự động của collector |
| `age` | Phân bố tuổi object và tenuring |
| `ref` | Xử lý reference |
| `region` | Region của collector như G1 |
| `humongous` | Object lớn trong G1 |
| `cpu` | Thời gian CPU liên quan đến collection |
| `safepoint` | Các lần JVM đưa thread tới safepoint |

Không phải mọi JVM hoặc collector đều có cùng tag. Dùng `java -Xlog:help` để xem danh sách thực tế.

### Dấu cộng và dấu phẩy có ý nghĩa khác nhau

- Dấu `+` kết hợp tag theo phép AND: `gc+heap` chỉ chọn thông điệp có cả hai tag.
- Dấu phẩy phân tách các selector độc lập: `gc,safepoint` chọn thông điệp thuộc tag `gc` hoặc tag `safepoint`.
- Không có wildcard thì chỉ khớp chính xác tag set được nêu.
- Wildcard `*` khớp tag set có chứa các tag đã chỉ định, kể cả khi có thêm tag khác.

Ví dụ:

```bash
# Tag set chính xác là gc và heap
-Xlog:gc+heap=debug

# Mọi tag set có chứa gc
-Xlog:gc*=info

# Mọi tag set có chứa gc và heap
-Xlog:gc+heap*=debug

# GC và safepoint là hai selector riêng
-Xlog:gc*,safepoint=info
```

`gc` và `gc*` không tương đương. `gc` có thể bỏ qua thông điệp mang tag set `gc,heap`; `gc*` bao gồm các tag set chứa `gc`.

### Các mức log

| Level | Mục đích |
| --- | --- |
| `off` | Tắt thông điệp phù hợp |
| `trace` | Chi tiết sâu nhất, thường rất nhiều dòng |
| `debug` | Thông tin chẩn đoán bổ sung |
| `info` | Thông tin vận hành thông thường |
| `warning` | Cảnh báo |
| `error` | Lỗi |

Level là ngưỡng chi tiết. Ví dụ `debug` bao gồm thông điệp ở mức `debug` và các mức quan trọng hơn như `info`, `warning`, `error`. `trace` mở rộng hơn nữa.

## 4. Chọn output và decorator

### Output destination

GC log có thể ghi ra:

- `stdout`: standard output.
- `stderr`: standard error.
- `file=filename`: file văn bản.

Ghi ra file:

```bash
java -Xlog:gc*=info:file=gc.log -jar app.jar
```

Ghi ra console phù hợp với môi trường container đã thu thập stdout/stderr. Ghi file phù hợp khi cần giữ log cục bộ, nhưng phải quản lý rotation, disk space và quyền truy cập.

Có thể thêm PID và timestamp vào tên file để tránh nhiều JVM ghi đè cùng một file:

```bash
java -Xlog:gc*=info:file=gc-%p-%t.log -jar app.jar
```

Trong tên file, `%p` được thay bằng PID và `%t` bằng thời điểm JVM khởi động. Một số JDK còn hỗ trợ `%hn` để chèn hostname.

### Decorators

Decorator là metadata được thêm trước mỗi thông điệp. Mặc định thường gồm `uptime`, `level` và `tags`.

| Decorator | Ý nghĩa |
| --- | --- |
| `time` | Ngày giờ hiện tại theo ISO-8601 |
| `utctime` | Thời gian UTC |
| `uptime` | Thời gian kể từ khi JVM khởi động |
| `timemillis` | Giá trị tương ứng `System.currentTimeMillis()` |
| `uptimemillis` | Millisecond kể từ khi JVM khởi động |
| `timenanos` | Giá trị tương ứng `System.nanoTime()` |
| `uptimenanos` | Nanosecond kể từ khi JVM khởi động |
| `hostname` | Hostname |
| `pid` | Process ID |
| `tid` | Thread ID |
| `level` | Mức log |
| `tags` | Tập tag của thông điệp |

Ví dụ:

```bash
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar app.jar
```

Một dòng log có thể có dạng:

```text
[2026-11-10T20:10:09.178+0700][0.144s][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
```

Cách đọc:

- `2026-11-10T20:10:09.178+0700`: thời gian thực.
- `0.144s`: JVM đã chạy được 0,144 giây.
- `info`: level.
- `gc,start`: tag set.
- `GC(0)`: ID của collection trong tiến trình này.
- Phần sau ID: loại collection và nguyên nhân/mô tả.

Dùng `time` hoặc `utctime` để ghép với log ứng dụng trên nhiều máy. Dùng `uptime` để xem thứ tự sự kiện trong cùng một JVM.

## 5. Ghi GC log ra file có rotation

GC log có thể tăng nhanh, đặc biệt khi bật `debug` hoặc `trace`. Nên cấu hình rotation để giới hạn dung lượng và số file được giữ.

Ví dụ:

```bash
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
```

Ý nghĩa:

- `filecount=5`: giữ tối đa năm file đã rotate, không tính file đang ghi.
- `filesize=20M`: kích hoạt rotation khi file tiến gần kích thước mục tiêu 20 MB.
- Kích thước thực tế chỉ là xấp xỉ, không phải giới hạn byte tuyệt đối.

Một số điểm cần lưu ý:

- `filecount=0` tắt rotation; file cũ có thể bị ghi đè.
- `filesize=0` tắt rotation tự động; có thể rotate thủ công bằng `jcmd`.
- Tên file chứa `%p` và `%t` giúp tránh xung đột giữa các JVM.
- Kiểm tra dung lượng volume và chính sách retention trước khi bật log chi tiết.
- Nếu chạy trong container, chọn stdout/stderr hoặc file trên volume có cơ chế thu thập/retention rõ ràng.

Có thể bật asynchronous logging:

```bash
java -Xlog:async -Xlog:gc*=info:file=gc.log -jar app.jar
```

Chế độ async ghi thông điệp vào buffer trung gian rồi một thread riêng flush ra output. Nó giảm việc ghi log đồng bộ tại log site, nhưng buffer có giới hạn; khi buffer đầy, thông điệp mới có thể bị loại bỏ. Chỉ dùng khi hiểu trade-off giữa overhead và độ đầy đủ của log.

## 6. Các cấu hình GC log thường dùng

Bắt đầu bằng cấu hình gọn:

```bash
-Xlog:gc*=info
```

Khi cần thêm thông tin, tăng độ chi tiết theo câu hỏi cụ thể:

| Mục tiêu | Cấu hình |
| --- | --- |
| GC summary | `-Xlog:gc` |
| Tất cả tag set có `gc` | `-Xlog:gc*=info` |
| Heap trước/sau GC | `-Xlog:gc+heap=debug` |
| Các pha GC | `-Xlog:gc+phases=debug` |
| Quyết định ergonomics | `-Xlog:gc+ergo=debug` |
| Age/tenuring | `-Xlog:gc+age=debug` |
| Reference processing | `-Xlog:gc+ref*=debug` |
| Safepoint | `-Xlog:safepoint=info` |
| GC và safepoint cùng lúc | `-Xlog:gc*,safepoint=info` |
| Chi tiết G1 region | `-Xlog:gc+region=debug` |
| G1 humongous object | `-Xlog:gc+humongous=debug` |

Các tag cụ thể phụ thuộc collector và JDK. Nếu một selector không được hỗ trợ, JVM có thể báo lỗi khi khởi động; kiểm tra `java -Xlog:help` trước.

Không nên bật tất cả selector ở mức `trace` trong thời gian dài. Hãy bắt đầu bằng `info`, sau đó bật `debug` cho đúng nhóm tag và trong khoảng thời gian đủ ngắn để trả lời câu hỏi.

## 7. Cách đọc một GC cycle

Với G1, log thường chứa một số loại thông điệp:

- Bắt đầu collection: `gc,start`.
- Các worker/task: `gc,task`.
- Các pha: `gc,phases`.
- Heap và region: `gc,heap`, `gc,region`.
- Kết quả collection: `gc`.
- CPU time: `gc,cpu`.
- Công việc concurrent: các dòng mô tả `Concurrent Mark Cycle` hoặc pha concurrent tương ứng.

Một ví dụ tổng quát:

```text
[0.047s][info][gc,start] GC(2) Pause Full (System.gc())
[0.047s][info][gc,task] GC(2) Using 2 workers of 20 for full compaction
[0.048s][info][gc,phases] GC(2) Phase 1: Mark live objects 0.758ms
[0.048s][info][gc,phases] GC(2) Phase 2: Prepare compaction 0.066ms
[0.048s][info][gc,phases] GC(2) Phase 3: Adjust pointers 0.283ms
[0.048s][info][gc,phases] GC(2) Phase 4: Compact heap 0.076ms
[0.049s][info][gc,heap] GC(2) Humongous regions: 33->9
[0.049s][info][gc] GC(2) Pause Full (System.gc()) 35M->10M(40M) 1.637ms
```

Đây là một đoạn log thực tế từ HotSpot JDK 24.0.2 trong workload minh họa; GC ID, thời gian, số region và dung lượng thay đổi theo lần chạy.

### Đọc dòng kết quả

Ví dụ:

```text
GC(2) Pause Full (System.gc()) 35M->10M(40M) 1.637ms
```

Có thể diễn giải:

- `GC(2)`: collection ID 2.
- `Pause Full`: một full collection có pause.
- `(System.gc())`: cause được ghi nhận là lời gọi explicit GC.
- `35M`: heap occupancy trước collection.
- `10M`: heap occupancy sau collection.
- `(40M)`: dung lượng heap tại thời điểm log.
- `1.637ms`: thời gian pause được báo cho collection này.

Định dạng cụ thể thay đổi theo collector và JDK. Không so sánh các con số nếu heap size, collector, workload hoặc thời điểm lấy mẫu khác nhau.

### Phân biệt pause và concurrent cycle

Không phải mọi dòng GC đều có nghĩa ứng dụng bị dừng.

- `Pause Young` và `Pause Full` là các collection pause; Java threads bị dừng trong phần pause tương ứng.
- `Concurrent Mark Cycle` mô tả một chu kỳ có công việc chạy concurrent; ứng dụng có thể tiếp tục chạy trong phần lớn thời gian đó.
- Một concurrent cycle có thể chứa một hoặc nhiều pause ngắn.
- `GC(n)` giúp nhóm các thông điệp liên quan tới cùng collection.

Không coi duration của một concurrent cycle là thời gian ứng dụng bị pause. Khi điều tra latency, tìm các dòng `Pause`, các phase pause và safepoint. Khi điều tra CPU/throughput, xem thêm thời gian concurrent và CPU time.

## 8. Heap before/after và dấu hiệu cần điều tra

Các dòng heap log giúp so sánh trạng thái trước/sau collection. Một số log chi tiết có dạng:

```text
[debug][gc,heap] GC(34) Heap before GC invocations=33 (full 0):
[debug][gc,heap] GC(34) garbage-first heap ... used 34321K
[info ][gc,heap] GC(34) Eden regions: 8->0(18)
[info ][gc,heap] GC(34) Old regions: 2->2
[debug][gc,heap] GC(34) Heap after GC invocations=34 (full 0):
[debug][gc,heap] GC(34) garbage-first heap ... used 26129K
```

Khi phân tích:

1. So sánh heap occupancy trước và sau collection.
2. Quan sát Eden/Survivor/Old regions nếu collector cung cấp.
3. Kiểm tra old-gen occupancy qua nhiều collection.
4. Xem promotion và tenuring khi object sống qua nhiều young GC.
5. Ghép với allocation rate, GC cause và workload cùng thời điểm.

Nếu heap sau GC tăng dần qua nhiều chu kỳ dưới workload tương đương, có thể có object retention hoặc live set đang tăng. Nếu heap giảm mạnh nhưng GC xảy ra liên tục, có thể allocation pressure cao. Cả hai tình huống đều cần thêm bằng chứng; GC log không cho biết object nào đang giữ reference.

Để tìm object giữ heap, kết hợp class histogram, heap dump, JFR old-object sampling hoặc Eclipse Memory Analyzer (MAT).

## 9. Safepoint log và thời gian ứng dụng dừng

Safepoint là trạng thái JVM đưa các Java thread tới vị trí an toàn để thực hiện một số thao tác nội bộ. GC là một nguyên nhân quan trọng nhưng không phải nguyên nhân duy nhất khiến JVM đi vào safepoint.

Bật log safepoint:

```bash
java -Xlog:safepoint=info -jar app.jar
```

Hoặc kết hợp với GC:

```bash
java -Xlog:gc*,safepoint=info:file=gc-safepoint.log:time,uptime,level,tags -jar app.jar
```

Safepoint log giúp quan sát:

- Thời gian JVM chờ các thread đi tới safepoint.
- Thời gian thực hiện operation tại safepoint.
- Tổng thời gian dừng liên quan tới safepoint.
- Các safepoint do VM operation khác ngoài GC.

Một pause có thể có thời gian đồng bộ tới safepoint và thời gian thực hiện operation. Vì vậy, nếu GC pause ngắn nhưng application stopped time dài, hãy kiểm tra safepoint synchronization và các VM operation cùng thời điểm.

Không cộng mọi dòng safepoint và GC phase một cách máy móc vì các khoảng thời gian có thể liên quan hoặc lồng nhau. Đọc ngữ cảnh và timestamp của từng event.

## 10. Ghi GC log động bằng jcmd VM.log

Unified Logging có thể thay đổi khi JVM đang chạy; không nhất thiết phải restart chỉ để bật thêm một selector.

Liệt kê JVM:

```bash
jcmd -l
```

Xem trợ giúp của command trên đúng process:

```bash
jcmd 18420 help VM.log
```

Liệt kê cấu hình log hiện tại:

```bash
jcmd 18420 VM.log list
```

Bật thêm heap detail vào một file mới:

```bash
jcmd 18420 VM.log output=file=gc-live.log what=gc+heap=debug decorators=time,uptime,level,tags output_options=filesize=10M,filecount=5
```

Trong đó:

- `output`: chọn file hoặc output đang cấu hình.
- `what`: tag selection và level cần bật.
- `decorators`: metadata cho mỗi dòng.
- `output_options`: file rotation.

Có thể xem lại cấu hình bằng `VM.log list`. Rotate thủ công các file log:

```bash
jcmd 18420 VM.log rotate
```

`VM.log` có Impact thấp trên JDK 24. Lệnh `jcmd` phải chạy trên cùng máy và thường cần cùng effective user/group với JVM đích. PID `18420` chỉ là ví dụ.

Thay đổi động chỉ áp dụng từ thời điểm bật trở đi; nó không tạo lại log cho các collection đã xảy ra. Hãy kiểm tra output path và quyền ghi của JVM trước khi bật file mới. Tránh dùng thao tác disable toàn bộ logging nếu chưa hiểu rằng nó có thể xóa cả cấu hình warning/error hiện tại.

## 11. Chuyển từ GC log flags cũ sang Unified Logging

Trên Java 9+, nên dùng `-Xlog` thay cho các cờ GC logging cũ.

| Cờ cũ | Cấu hình Unified Logging |
| --- | --- |
| `-XX:+PrintGC` | `-Xlog:gc` |
| `-XX:+PrintGCDetails` | `-Xlog:gc*` |
| `-XX:+PrintHeapAtGC` | `-Xlog:gc+heap=trace` |
| `-XX:+PrintGCApplicationStoppedTime` | `-Xlog:safepoint` |
| `-XX:+PrintTenuringDistribution` | `-Xlog:gc+age=debug` |
| `-XX:+PrintReferenceGC` | `-Xlog:gc+ref*=debug` |
| `-Xloggc:gc.log` | `-Xlog:gc:file=gc.log` |

Một số cờ cũ đã deprecated hoặc bị loại bỏ. Không ghép nhiều cấu hình cũ và mới một cách tùy tiện; dùng cú pháp Unified Logging và kiểm tra trợ giúp JDK.

`-Xloggc` được thay thế bằng `-Xlog:gc:file=...` trong JDK hiện đại. Với Java 8, cần dùng cờ tương thích với phiên bản đó vì Unified Logging chưa có.

## 12. Ví dụ thực hành Java 17: tạo GC log và đọc kết quả

Ví dụ này tạo một số byte array tạm thời, sau đó bỏ tham chiếu và yêu cầu explicit GC để tạo log dễ quan sát. Một mảng static được giữ lại để phân biệt object được thu hồi với object vẫn reachable.

Tạo cấu trúc:

```text
project/
  src/
    GcLogDemo.java
  out/
```

Tệp `src/GcLogDemo.java`:

```java
public final class GcLogDemo {
    private static final byte[] RETAINED = new byte[8 * 1024 * 1024];

    private GcLogDemo() {
    }

    public static void main(String[] args) {
        byte[][] temporary = new byte[12][];

        for (int i = 0; i < temporary.length; i++) {
            temporary[i] = new byte[1024 * 1024];
        }

        System.out.println("allocated temporary arrays=" + temporary.length);
        temporary = null;

        System.out.println("requesting explicit GC");
        System.gc();

        System.out.println(
            "GC request completed; retained bytes=" + RETAINED.length
        );
    }
}
```

Biên dịch bằng Java 17:

```bash
mkdir out
javac --release 17 -g -d out src/GcLogDemo.java
```

Chạy với G1, heap giới hạn và GC log chi tiết:

```bash
java -Xms32m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info:file=gc-demo.log:uptime,level,tags:filecount=3,filesize=1m -cp out GcLogDemo
```

Stdout từ lần chạy kiểm thử:

```text
allocated temporary arrays=12
requesting explicit GC
GC request completed; retained bytes=8388608
```

Trong `gc-demo.log`, một đoạn log từ cùng lần chạy có dạng:

```text
[0.047s][info][gc,start] GC(2) Pause Full (System.gc())
[0.047s][info][gc,task] GC(2) Using 2 workers of 20 for full compaction
[0.048s][info][gc,phases] GC(2) Phase 1: Mark live objects 0.758ms
[0.048s][info][gc,phases] GC(2) Phase 2: Prepare compaction 0.066ms
[0.048s][info][gc,phases] GC(2) Phase 3: Adjust pointers 0.283ms
[0.048s][info][gc,phases] GC(2) Phase 4: Compact heap 0.076ms
[0.049s][info][gc,heap] GC(2) Humongous regions: 33->9
[0.049s][info][gc] GC(2) Pause Full (System.gc()) 35M->10M(40M) 1.637ms
```

Kết quả trên là một lần chạy HotSpot JDK 24.0.2, với source tương thích Java 17. ID, thời gian, số region và dung lượng có thể khác ở lần chạy khác.

Điểm cần quan sát:

- `System.gc()` xuất hiện trong cause của Full GC.
- Heap occupancy giảm từ `35M` xuống `10M`.
- Mảng static 8 MiB vẫn reachable.
- `GC(2)` liên kết các phase và dòng kết quả của cùng collection.
- Các phase compaction giải thích công việc collector thực hiện trong pause.

`System.gc()` chỉ dùng để minh họa. Không gọi explicit GC như một chiến lược vận hành thường xuyên; JVM có thể bỏ qua yêu cầu này theo cấu hình, và full GC có thể gây pause.

## 13. Kết hợp GC log với JFR và công cụ khác

GC log là dạng văn bản có ích để xem collection, cause, heap occupancy và các phase. Khi cần phân tích sâu hơn, kết hợp:

| Công cụ | Vai trò |
| --- | --- |
| GC unified log | Timeline văn bản, cause, heap, phases, safepoint |
| JFR | Event có cấu trúc, allocation samples, pause distribution và thread context |
| Java Mission Control | Giao diện phân tích file JFR |
| `jcmd GC.heap_info` | Heap summary tại một thời điểm |
| `jcmd GC.class_histogram` | Số lượng object theo class |
| `jcmd GC.heap_dump` | Tạo HPROF để phân tích object graph |
| Eclipse MAT | Dominator tree, retained size và GC roots |
| OS/container metrics | RSS, CPU throttling, memory limit và process pressure |

Ví dụ:

- GC log cho thấy pause P99 tăng: đối chiếu JFR `GarbageCollection`, `GCPhasePause` và safepoint.
- GC log cho thấy old-gen tăng: dùng histogram hoặc heap dump để tìm object retention.
- Concurrent GC kéo dài: xem JFR GC CPU time, CPU saturation và container throttling.
- GC thường xuyên nhưng heap sau GC ổn định: xem allocation-by-site để tìm allocation pressure.

GC log và JFR bổ sung cho nhau. Không cần bật mức trace cho toàn bộ GC log nếu JFR đã cung cấp dữ liệu chi tiết hơn cho câu hỏi đang điều tra.

## 14. Lỗi thường gặp khi cấu hình và đọc GC log

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không thấy log GC | Chọn tag set quá hẹp hoặc sai selector | Dùng `-Xlog:help`, thử `-Xlog:gc*` |
| Chỉ thấy dòng `gc` tổng quan | Không bật wildcard hoặc tag con | Bật `gc*` hoặc `gc+heap=debug` |
| JVM báo lỗi selector | Tag không tồn tại trên JDK/collector đó | Kiểm tra danh sách tag thực tế |
| Log quá nhiều | Bật `debug`/`trace` cho quá nhiều tag | Giảm về `info`, giới hạn tag và thời lượng |
| File log tăng vô hạn | Chưa cấu hình rotation | Dùng `filesize` và `filecount` |
| Log bị ghi đè | Rotation bị tắt hoặc file name trùng | Dùng PID/timestamp và cấu hình rotation |
| Không ghi được file | JVM không có quyền hoặc thư mục không tồn tại | Kiểm tra owner, quyền và disk space |
| Không thấy log động | `jcmd` sai PID/user hoặc command không được hỗ trợ | Dùng `jcmd -l`, `help VM.log` và cùng tài khoản |
| GC duration dài nhưng pause ngắn | Collector đang làm concurrent work | Phân biệt `Concurrent Mark Cycle` với `Pause` |
| Safepoint time khác GC pause | Safepoint có thể do VM operation khác GC | Ghép timestamp, tag và operation |
| Heap sau GC tăng | Live set tăng hoặc workload khác | So sánh nhiều chu kỳ trong workload tương đương; kiểm tra retention |
| Log không khớp thời gian ứng dụng | Chỉ dùng uptime hoặc đồng hồ máy khác nhau | Bật `time`/`utctime`, `pid` và ghép với timestamp ứng dụng |

## 15. Quy trình điều tra GC bằng log

1. Ghi lại JDK version, JVM vendor, collector, heap min/max và giới hạn container.
2. Bắt đầu bằng `-Xlog:gc*=info` và lưu ra file có rotation.
3. Ghi thêm `time`, `uptime`, `pid` và `tags` để ghép với log ứng dụng.
4. Xác định collection bất thường theo GC ID, cause và thời điểm.
5. So sánh heap before/after và các vùng Eden/Survivor/Old Gen nếu có.
6. Đọc pause duration, concurrent phases và safepoint.
7. Nếu cần, bật `gc+heap=debug`, `gc+phases=debug` hoặc `gc+ergo=debug` trong khoảng ngắn.
8. Dùng `jcmd VM.log list` để xác nhận cấu hình; thay đổi động bằng `VM.log` khi phù hợp.
9. Đối chiếu với JFR, application latency, CPU, container metrics và deployment.
10. Nếu nghi ngờ retention, tạo heap dump và phân tích bằng MAT.
11. Thay đổi một yếu tố GC mỗi lần, chạy lại workload tương đương và so sánh.
12. Lưu log theo retention policy, bảo vệ dữ liệu và tắt các selector chi tiết sau khi điều tra.

Không tuning collector chỉ dựa vào một dòng Full GC hoặc một pause dài. Cần xác định vấn đề đến từ allocation, live set, pause phase, CPU contention hay giới hạn tài nguyên.

## 16. Ghi nhớ

- GC log từ Java 9+ dùng Unified Logging với `-Xlog`.
- `-Xlog:gc` ghi GC summary; `-Xlog:gc*` bao gồm các tag set chứa `gc`.
- Dấu `+` kết hợp tag theo AND; dấu phẩy tách các selector độc lập; wildcard `*` mở rộng tag set phù hợp.
- `info`, `debug` và `trace` có độ chi tiết tăng dần; `trace` có thể tạo log rất lớn.
- Output có thể là stdout, stderr hoặc file; decorator cung cấp thời gian, PID, level và tag.
- `filesize`/`filecount` giới hạn log file; `%p`/`%t` giúp tránh trùng tên.
- `GC(n)` liên kết các thông điệp trong một collection.
- `Pause Young`/`Pause Full` là pause; `Concurrent Mark Cycle` không đồng nghĩa toàn bộ thời gian ứng dụng bị dừng.
- Heap before/after giúp nhận diện xu hướng nhưng không cho biết object nào giữ reference.
- Safepoint log bao gồm cả hoạt động không phải GC.
- `jcmd PID VM.log` cho phép xem và thay đổi cấu hình logging khi JVM đang chạy.
- Kết hợp GC log với JFR, heap dump, MAT và metrics để tìm nguyên nhân gốc.
- Không để debug/trace chạy lâu trên production khi không cần thiết; quản lý disk, rotation và quyền truy cập log.

Hiểu cách chọn tag, đọc GC ID, phân tích heap và pause, cũng như cấu hình rotation giúp bạn dùng GC log để chẩn đoán JVM dựa trên bằng chứng và kiểm soát tác động tới ứng dụng.

## Tài liệu tham khảo

- [The java Command — JDK 24: Unified Logging](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Garbage-First Garbage Collector Tuning — Java SE 24](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html)
- [The java Command — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
