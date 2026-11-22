# 13.10 Chi phí NMT, dữ liệu cần giữ và giới hạn bật lại sau khi đã tắt

> **Bối cảnh:** Java 21 / HotSpot, chủ đề **bộ nhớ native**. Native Memory Tracking (NMT) là công cụ của HotSpot để theo dõi một phần bộ nhớ do chính JVM quản lý. Bài này tập trung vào **chi phí khi bật NMT**, **bằng chứng cần thu và lưu trước khi tắt**, và **giới hạn không thể bật lại trong cùng tiến trình sau `shutdown`**. Đây là quyết định vận hành cần lên kế hoạch từ lúc khởi động JVM, đặc biệt khi chẩn đoán hệ thống production.

## 1. Kết quả học tập

Hoàn thành bài này, bạn cần giải thích và thực hiện được:

1. Phân biệt ba trạng thái cấu hình lúc khởi động `off`, `summary`, `detail`; hiểu NMT thu thập dữ liệu gì, bỏ sót gì và mức chi phí vận hành.
2. Đọc `reserved`/`committed`, dùng `baseline`, `summary.diff` và `detail.diff` đúng cấp độ đã bật; không nhầm chênh lệch tức thời với bằng chứng chắc chắn của memory leak.
3. Thu đủ snapshot, baseline/diff, phiên bản/cấu hình JVM, thời điểm và chỉ số hệ điều hành **trước khi** chạy `VM.native_memory shutdown`.
4. Giải thích vì sao `jcmd` **không thể bật hoặc bật lại NMT** sau khi nó đã `off`/`shutdown` và cách tổ chức khởi động lại có kiểm soát khi cần chẩn đoán tiếp.
5. Đánh giá chi phí NMT bằng thử nghiệm đại diện và thiết kế runbook lưu bằng chứng có phân quyền.

## 2. NMT theo dõi những gì và giới hạn đến đâu?

NMT (Native Memory Tracking) thuộc **HotSpot JVM**. Nó ghi nhận nhiều phân bổ bộ nhớ và vùng ánh xạ do JVM nội bộ quản lý, trình bày theo nhóm như `Java Heap`, `Class`, `Thread`, `Code`, `GC`, `Compiler`, `Internal`, `Symbol`, `Native Memory Tracking`... Tên nhóm có thể khác theo phiên bản/build và cấu hình. NMT cũng ghi nhận phần bộ nhớ dùng **cho chính hoạt động theo dõi**.

Nhưng NMT **không phải** trình phân tích toàn bộ RAM của tiến trình:

- NMT theo dõi bộ nhớ bên trong **HotSpot**, không bao quát mọi phân bổ của **native library bên thứ ba, JNI**, thư viện lớp JDK hoặc ứng dụng native theo cách tài liệu JDK 21 giới hạn.
- NMT không liệt kê đối tượng Java sống trên heap theo retained size. Dòng `Java Heap` thể hiện vùng nhớ JVM quản lý, không thay cho heap dump khi cần tìm object giữ tham chiếu.
- NMT không bảo đảm giải thích chênh lệch giữa số liệu của JVM và **RSS** do hệ điều hành hoặc memory usage của container báo cáo. RSS, page cache, vùng ánh xạ và các phân bổ ngoài phạm vi NMT cần công cụ OS/container riêng.
- Ngay cả khi NMT có dữ liệu, một vài phân bổ rất sớm hoặc cơ chế quản lý như arena có thể không được bóc tách thành từng allocation. `detail` cũng không phải bộ ghi **mọi** lệnh `malloc`/stack trace ứng dụng.

**`reserved` và `committed` không đồng nghĩa:** `reserved` là không gian địa chỉ ảo JVM dành trước, `committed` là phần đã cam kết sử dụng trong không gian ảo đó. `committed` **không tự động bằng RSS đang resident**; không nên cộng `reserved` các hạng mục rồi gọi đó là bộ nhớ vật lý đã tiêu thụ.

Ví dụ đọc số liệu giả định:

```text
Total: reserved=4096MB, committed=950MB
- Java Heap (reserved=3072MB, committed=700MB)
- Thread    (reserved=256MB,  committed=18MB)
```

Các dòng trên **chỉ minh họa ý nghĩa**, không phải stdout cố định của một JDK hay một lệnh cụ thể. Chúng không chứng minh tiến trình đang dùng đúng 950 MB RSS hoặc 256 MB bộ nhớ stack vật lý.

## 3. Chọn cấp độ NMT và đo chi phí

### 3.1. Cấp độ chỉ có thể chọn khi khởi động

```bash
java -XX:NativeMemoryTracking=off -jar app.jar
java -XX:NativeMemoryTracking=summary -jar app.jar
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Đây là **ba cách khởi động thay thế**, không phải chạy cả ba cùng lúc. Thay `app.jar` bằng ứng dụng thực tế và kiểm tra Java runtime/flags của tiến trình đích.

| Cấp độ | Dữ liệu hiện có | Đánh đổi |
| --- | --- | --- |
| `off` (mặc định) | Không có snapshot/baseline/diff NMT | Không có chi phí riêng của tracking; không thể gọi `jcmd` để bật NMT về sau |
| `summary` | Tổng `reserved`/`committed` theo subsystem, phân tách các loại phân bổ mà NMT báo cáo | Đủ để tìm nhóm bộ nhớ tăng; vẫn có thêm CPU và metadata tracking |
| `detail` | Dữ liệu `summary` cùng vùng địa chỉ và tổng hợp theo allocation call site HotSpot | Hỗ trợ khoanh vùng sâu hơn, nhưng cần chuẩn bị trước; báo cáo lớn hơn, thu thập/ghi file và việc theo dõi có thể tốn thêm tài nguyên |

Không nên suy diễn rằng `jcmd <PID> VM.native_memory detail` **nâng cấp** tiến trình đã chạy `summary`. Cấp độ được thiết lập **lúc JVM khởi động**; để có dữ liệu call-site của `detail`, khởi chạy JVM mới với `-XX:NativeMemoryTracking=detail`.

### 3.2. Chi phí CPU, bộ nhớ và thao tác chẩn đoán

Theo tài liệu **Oracle JDK 21**, bật NMT có thể gây **sụt hiệu năng khoảng 5–10%** trong các điều kiện tài liệu nêu. Đây là **ước lượng tham khảo**, không phải hệ số cộng thêm cố định cho mọi dịch vụ. Java 21 cũng mô tả metadata khoảng **hai machine words cho mỗi phân bổ `malloc` được NMT theo dõi**; chi phí thực tế phụ thuộc tần suất và loại phân bổ, số lượng thread, JVM build, hardware và workload. NMT tự báo cáo một phần overhead của chính nó.

Phân biệt ba khoản chi phí:

1. **Tracking liên tục:** xử lý cập nhật thống kê khi HotSpot cấp phát/giải phóng vùng native; thêm metadata và có thể làm giảm throughput.
2. **Truy vấn qua `jcmd`:** `VM.native_memory` được JDK 21 phân loại **Impact: Medium**; đặc biệt output `detail` có thể dài, tiêu thụ thời gian xử lý và I/O.
3. **Lưu/luân chuyển bằng chứng:** file output, công cụ parse, truy xuất từ container và việc giữ nhiều snapshot cũng tiêu thụ lưu trữ, băng thông và công sức vận hành.

Không coi `5–10%` là mức tối đa, mức tối thiểu hay dự báo chính xác. Phải **đo trực tiếp** trên workload có đại diện. Các tình huống nhiều native allocations hoặc yêu cầu độ trễ nghiêm ngặt có thể phản ứng khác.

### 3.3. Cách đo overhead có ý nghĩa

Trên staging hoặc canary được phép, so sánh ba lần triển khai có cùng JDK 21 build, heap/GC flags, máy hoặc giới hạn container, dữ liệu đầu vào, tần suất request, concurrency và warmup:

- **Baseline không NMT:** `-XX:NativeMemoryTracking=off`.
- **Nhóm theo dõi:** `-XX:NativeMemoryTracking=summary`.
- **Nhóm phân tích sâu:** `-XX:NativeMemoryTracking=detail` nếu thực sự có nhu cầu call site.

Ghi **throughput**, latency p50/p95/p99, CPU usage, GC frequency/pause, RSS và memory limit của container, số thread, errors, NMT committed khi có. Lặp phép đo để tránh quyết định từ một lần chạy, ghi rõ điều kiện và sự sai lệch. Dùng tải có quy mô đủ lớn; bài thử khởi động ứng dụng vài giây không thể dự báo overhead dài hạn.

Có thể tính phần trăm thay đổi của thông lượng trong một bài đo:

```text
Throughput change (%) =
    (throughput_with_NMT - throughput_without_NMT)
    / throughput_without_NMT × 100
```

Chẳng hạn 1.000 requests/s giảm còn 940 requests/s là **-6% throughput** trong điều kiện đo đó. Điều này **không có nghĩa** CPU luôn tăng chính xác 6% hay mọi hệ thống đều chậm 6%. Với latency, nên báo cáo **độ chênh lệch mili giây lẫn phần trăm** của cùng percentile.

Nếu chỉ cần dự phòng điều tra native memory ở production, `summary` có thể là mức hợp lý ban đầu sau khi thử tải; nếu cần call site liên tục, `detail` phải được chứng minh là chấp nhận được. Không bật `detail` bằng thói quen trên mọi replica.

## 4. Thu thập bằng chứng khi NMT đang bật

### 4.1. Kiểm tra đúng JVM

`jcmd` phải chạy trên cùng máy với JVM và có effective UID/GID thích hợp; PID namespace của container có thể khiến `jcmd -l` từ host không thấy JVM mục tiêu. Hãy xác minh JVM đích qua service manager, pod/host và PID trước khi thu dữ liệu. Tránh `jcmd 0` vì PID `0` có thể gửi lệnh cho nhiều JVM.

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> VM.command_line
jcmd <PID> help VM.native_memory
```

`<PID>` là placeholder phải thay bằng PID thật. **`VM.command_line` có thể chứa bí mật cấu hình** nếu hệ thống đưa token/password trong arguments; lưu và chia sẻ kết quả theo chính sách phân quyền, che/redact phần nhạy cảm trong bản dành cho nhiều người.

Thông thường không cần lệnh gây thay đổi để kiểm tra NMT: khi NMT bật, thử truy vấn:

```bash
jcmd <PID> VM.native_memory summary scale=KB
```

Nếu NMT không hoạt động, lệnh sẽ không có dữ liệu tracking hữu ích. Đừng nhầm JVM không attach được vì quyền/namespace với NMT bị tắt: đây là hai nguyên nhân độc lập.

### 4.2. Snapshot, baseline và diff

Một **baseline** là mốc so sánh được giữ **trong tiến trình đang chạy**, không phải file bằng chứng tồn tại mãi. Đặt baseline sau warmup và khi tải ở trạng thái có thể so sánh; nếu đặt ngay lúc startup, nhiều delta là tăng trưởng bình thường do class loading, JIT và thread pools.

```bash
# JVM đã khởi động với -XX:NativeMemoryTracking=summary hoặc detail
jcmd <PID> VM.native_memory summary scale=KB
jcmd <PID> VM.native_memory baseline
# Cho workload thực tế chạy qua một khoảng có ý nghĩa
jcmd <PID> VM.native_memory summary.diff scale=KB
jcmd <PID> VM.native_memory summary scale=KB
```

Với JVM **đã khởi động bằng `detail`**, có thể thu thêm:

```bash
jcmd <PID> VM.native_memory detail scale=KB
jcmd <PID> VM.native_memory detail.diff scale=KB
```

- `summary`: trạng thái tuyệt đối của các nhóm tại thời điểm hỏi.
- `baseline`: đặt mốc so sánh trong JVM. Baseline mới thay đổi mốc mà các phép `*.diff` tiếp theo dùng; **hãy xuất bản ghi cũ ra file trước khi đặt lại mốc**.
- `summary.diff`: chênh lệch theo subsystem so với baseline gần nhất; dấu âm là giảm, dấu dương là tăng.
- `detail` và `detail.diff`: chỉ có dữ liệu call-site tương ứng khi startup ở `detail`. Không thể tái dựng lịch sử call-site nếu trước đó chỉ chạy `summary`.

Một delta tăng không đồng nghĩa leak: số class tăng, JIT warmup, thread stack reserve, metaspace growth hoặc memory caching đều có thể hợp lệ. Phải so theo tải và thời gian. NMT cung cấp ảnh chụp **cumulative state**, không trực tiếp chỉ ra object hay phương thức Java “đáng trách”.

### 4.3. Những gì cần giữ lại — trước cả khi cân nhắc `shutdown`

| Nhóm bằng chứng | Nên lưu | Vì sao |
| --- | --- | --- |
| **Định danh JVM** | Service, hostname/pod, process PID **và thời gian khởi động**, JDK 21 vendor/build, container image, GC, `-Xmx`, cấu hình NMT | PID có thể được tái sử dụng; restart tạo chuỗi quan sát khác |
| **Ngữ cảnh phép đo** | Timestamp có timezone, uptime, workload, concurrency/QPS, phiên bản ứng dụng, thời điểm warmup hoặc deploy | Giúp phân biệt thay đổi do hoạt động bình thường với tăng trưởng bất thường |
| **NMT đầu kỳ** | Output `summary` ở thời điểm baseline, thông báo baseline đã được đặt; nếu `detail` đang bật thì bản `detail` đầu kỳ | Lưu trạng thái tuyệt đối không phụ thuộc baseline sống trong JVM |
| **NMT cuối kỳ và các mốc giữa** | `summary`, `summary.diff`; nếu mức `detail`, thêm `detail`, `detail.diff` | Có cả giá trị tuyệt đối lẫn chênh lệch, điều tra được nhóm tăng và call site |
| **Chỉ số hệ điều hành/container** | RSS, memory.current/working set theo môi trường, limit, swap, số thread, maps/smaps nếu được phép, lỗi OOM | Đối chiếu vùng ngoài phạm vi NMT và tác động thực tế |
| **Kiểm soát toàn vẹn và truy cập** | Tên file, checksum, nơi cất, owner, ACL, retention, ghi nhận ai được quyền xem | Dữ liệu native diagnostics có thể lộ tên thư viện, đường dẫn và địa chỉ bộ nhớ |

**Giữ nguyên output thô** với đơn vị đã ghi (`scale=KB` là lựa chọn dễ so sánh), đính kèm timestamp vào metadata; có thể tạo bảng/biểu đồ từ bản sao nhưng **không chỉ giữ screenshot** hoặc một con số tổng. Bản `summary.diff` riêng lẻ không đủ tái hiện trạng thái trước/sau; nếu JVM chết hoặc NMT bị shutdown thì baseline nội bộ không còn dùng để hỏi lại.

### 4.4. Ví dụ lưu dữ liệu ra thư mục hạn chế quyền

Ví dụ dưới đây dùng shell Linux, minh họa một phiên chẩn đoán; người thực hiện phải **điền đúng PID** và chỉ làm khi có quyền attach/lưu file:

```bash
umask 077
mkdir -p "$HOME/nmt-evidence"
chmod 700 "$HOME/nmt-evidence"

# Điền PID chính xác của JVM cần điều tra, ví dụ:
TARGET_PID=12345
EVIDENCE_DIR="$HOME/nmt-evidence"

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$EVIDENCE_DIR/00-time-before.txt"
jcmd "$TARGET_PID" VM.version > "$EVIDENCE_DIR/01-vm-version.txt"
jcmd "$TARGET_PID" VM.uptime > "$EVIDENCE_DIR/02-uptime-before.txt"
jcmd "$TARGET_PID" VM.native_memory summary scale=KB > "$EVIDENCE_DIR/03-summary-before.txt"
jcmd "$TARGET_PID" VM.native_memory baseline > "$EVIDENCE_DIR/04-baseline.txt"
```

Sau khoảng quan sát có tải đại diện:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$EVIDENCE_DIR/05-time-after.txt"
jcmd "$TARGET_PID" VM.native_memory summary.diff scale=KB > "$EVIDENCE_DIR/06-summary-diff.txt"
jcmd "$TARGET_PID" VM.native_memory summary scale=KB > "$EVIDENCE_DIR/07-summary-after.txt"
jcmd "$TARGET_PID" VM.uptime > "$EVIDENCE_DIR/08-uptime-after.txt"
```

Nếu đã bật `detail`, thực hiện và lưu `detail`, `detail.diff` **trước khi shutdown**. Kiểm tra từng exit code và nội dung file: shell redirect vẫn có thể tạo file rỗng khi `jcmd` lỗi. Ví dụ trên không tự thu RSS; số liệu OS/container cần được thu và đặt tên cùng thời điểm bằng công cụ hệ điều hành tương ứng.

Không dùng đường dẫn mẫu `$HOME/nmt-evidence` khi môi trường có policy thư mục riêng; thư mục bằng chứng của production nên có chính sách **encryption, audit, rotation và retention**. Không đẩy output có đường dẫn/địa chỉ nội bộ lên ticket công khai hay repository.

## 5. `shutdown`: bước một chiều trong cùng JVM

Đây là giới hạn vận hành quan trọng nhất của bài.

### 5.1. Các chuyển trạng thái được hỗ trợ

```text
Khởi động JVM với -XX:NativeMemoryTracking=off
    -> NMT off -> không thể bật NMT qua jcmd

Khởi động JVM với -XX:NativeMemoryTracking=summary
    -> NMT summary -> có thể lấy summary/baseline/diff
                   -> jcmd ... VM.native_memory shutdown -> NMT off
                   -> không thể bật lại trong cùng JVM

Khởi động JVM với -XX:NativeMemoryTracking=detail
    -> NMT detail -> có thể lấy detail và summary/baseline/diff
                  -> jcmd ... VM.native_memory shutdown -> NMT off
                  -> không thể bật lại trong cùng JVM
```

Theo **Oracle JDK 21**, `jcmd` **có thể dừng NMT nhưng không thể khởi động hoặc khởi động lại NMT**. Không có quy trình chuẩn gọi `VM.native_memory enable`, cũng không thể dùng `VM.set_flag` để biến một JVM đã khởi động `off` thành `summary/detail`.

Để dừng NMT có chủ đích trên JVM đang bật:

```bash
# CHỈ làm sau khi đã lưu đủ dữ liệu cần giữ:
jcmd <PID> VM.native_memory shutdown
```

Đây là lệnh **thay đổi trạng thái runtime**, khác hẳn lệnh `summary` chỉ đọc. Không chạy trong production như một bài test vô tình. Sau `shutdown`:

- Không thu thêm snapshot `summary`/`detail` hay diff NMT từ chính tiến trình đó được.
- Baseline và dữ liệu tracking sống trong JVM không thể được dùng để truy xuất “bù” phần lịch sử chưa xuất.
- NMT sẽ không ghi nhận những phân bổ xảy ra sau thời điểm tắt, nên bộ bằng chứng thu trước đó chỉ mô tả cửa sổ quá khứ.
- Nếu cần tracking tiếp, phải **khởi động JVM mới** với `-XX:NativeMemoryTracking=summary` hoặc `detail`; tạo **baseline mới** và đánh dấu chuỗi đo mới, không nối như thể cùng phiên liên tục.

Việc `shutdown` NMT **không đồng nghĩa shutdown ứng dụng Java**. Đừng nhầm `VM.native_memory shutdown` với `jcmd` kết thúc tiến trình. Tuy vậy, khôi phục NMT đòi hỏi restart JVM, kéo theo chi phí availability và khả năng mất trạng thái; cần phương án triển khai thích hợp.

### 5.2. Có nên tắt để giảm overhead?

Khi đã có đủ bằng chứng, người vận hành có thể muốn tắt tracking để giảm phần overhead đang phát sinh. Trước khi quyết định:

1. Xác nhận giai đoạn điều tra **đã kết thúc**, mọi snapshot cần thiết và raw diff đã lưu và truy xuất được.
2. Xác nhận có thể chấp nhận **không còn NMT** trên JVM này; nếu lỗi tái phát trước lần restart kế tiếp sẽ phải dựa vào telemetry khác.
3. Định rõ ngưỡng nào buộc thực hiện **rolling restart** để bật NMT lại, ai được phép làm, và việc restart có làm mất bằng chứng/trạng thái không.
4. Nếu mục tiêu là tiết kiệm overhead lâu dài, đánh giá trên phép đo thay vì mặc định coi `shutdown` sẽ trả lại chính xác 5–10% throughput. Metadata đã cấp phát, trạng thái JVM và workload còn ảnh hưởng.
5. Không xóa file bằng chứng ở cùng bước tắt; giữ theo retention và quyền đã thống nhất.

Với ứng dụng nhiều replica, cân nhắc giữ `summary` trên một canary đã đo overhead hoặc sử dụng một cửa sổ chẩn đoán có lịch. Với dịch vụ bắt buộc liên tục, tính đến khả năng điều tra bằng công cụ OS khi NMT vắng mặt.

### 5.3. Khi NMT vốn đã tắt hoặc mức tracking quá thấp

**Tình huống A — JVM khởi động `off`:** `jcmd` không thể làm phát sinh dữ liệu NMT quá khứ. Muốn có NMT, đưa cờ startup vào cấu hình triển khai và **restart** JVM có kiểm soát. Trước đó hãy dùng RSS, cgroup memory, thread count, `/proc/<PID>/smaps_rollup`/`pmap` nếu phù hợp và có quyền; những công cụ này không thay thế các breakdown HotSpot của NMT.

**Tình huống B — JVM khởi động `summary`, nay cần call sites:** Không thể nâng lên `detail` bằng một lệnh `jcmd` trên cùng JVM. Xuất toàn bộ `summary`/diff trước, sau đó triển khai JVM mới với `detail`, tạo baseline mới và thu call-site theo cửa sổ đại diện.

**Tình huống C — vừa chạy `shutdown`:** Nếu chưa lưu output, các snapshot NMT đã bỏ lỡ không thể lấy lại từ cùng JVM. Có thể giữ các OS metrics/log ngoài tiến trình; để theo dõi NMT cần restart với cờ đã chuẩn bị từ đầu.

**Tình huống D — JVM crash:** Cần phân biệt crash, `OutOfMemoryError`, container kill và graceful exit. `-XX:+UnlockDiagnosticVMOptions -XX:+PrintNMTStatistics` có thể in thống kê NMT khi JVM **thoát theo đường hỗ trợ** nếu đã bật tracking từ startup; nó không bảo đảm có báo cáo khi bị kill đột ngột, và không giúp hồi phục tracking đã shutdown.

## 6. Bài thực hành an toàn trên Java 21

Mục tiêu lab: thấy khác biệt giữa **ảnh chụp tuyệt đối**, **mốc baseline**, **diff**, và **giới hạn shutdown** bằng việc tăng số platform threads có kiểm soát. Không dùng dữ liệu production và không cố tạo memory leak.

Tạo file **`NmtLab.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class NmtLab {
    public static void main(String[] args) throws Exception {
        BufferedReader input = new BufferedReader(new InputStreamReader(System.in));
        System.out.println("BASELINE READY");
        System.out.println("Press ENTER to start 12 platform threads");
        input.readLine();

        CountDownLatch ready = new CountDownLatch(12);
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> workers = new ArrayList<>();

        for (int i = 0; i < 12; i++) {
            Thread worker = new Thread(() -> {
                ready.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "nmt-worker-" + i);
            workers.add(worker);
            worker.start();
        }

        ready.await();
        System.out.println("WORKERS READY: " + workers.size());
        System.out.println("Press ENTER to release workers");
        input.readLine();

        release.countDown();
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("DONE");
    }
}
```

Trong **terminal A** dùng JDK 21, chạy tương tác:

```bash
javac NmtLab.java
java -XX:NativeMemoryTracking=summary -Xms32m -Xmx128m NmtLab
```

Khi thấy `BASELINE READY`, **đừng nhấn ENTER vội**. Sang **terminal B** cùng máy và user phù hợp:

```bash
jcmd -l
jcmd <LAB_PID> VM.native_memory summary scale=KB
jcmd <LAB_PID> VM.native_memory baseline
```

Thay `<LAB_PID>` bằng PID chính xác của `NmtLab`. Quay lại terminal A, nhấn ENTER **một lần**. Khi thấy `WORKERS READY: 12`, đừng nhấn ENTER lần hai; trở về terminal B:

```bash
jcmd <LAB_PID> VM.native_memory summary.diff scale=KB
jcmd <LAB_PID> VM.native_memory summary scale=KB
```

Theo dõi `Thread` và các nhóm liên quan. Việc tạo 12 **platform threads** thường làm tăng bộ nhớ thread-stack được reserve, nhưng **delta chính xác và committed** phụ thuộc OS/JVM và cách cấp phát stack; không đặt một con số kỳ vọng cố định hay xem một diff bằng 0 là chắc chắn code sai.

Sau khi **đã lưu output** trên môi trường lab, có thể thử:

```bash
jcmd <LAB_PID> VM.native_memory shutdown
jcmd <LAB_PID> VM.native_memory summary
```

Lệnh thứ hai không còn trả dữ liệu NMT đang tracking. Đừng đoán một chuỗi thông báo lỗi cố định vì văn bản có thể khác theo build. Cuối cùng trở lại terminal A, nhấn ENTER lần hai để giải phóng và `join()` các worker.

**Stdout ứng dụng** trên terminal A (bỏ qua prompt shell và output của `jcmd`) là:

```text
BASELINE READY
Press ENTER to start 12 platform threads
WORKERS READY: 12
Press ENTER to release workers
DONE
```

`Thread`, `CountDownLatch` và `BufferedReader` dùng API Java có sẵn, chương trình không cần tính năng preview. Lab tạo platform threads thay vì virtual threads để quan sát bộ nhớ stack native rõ hơn; số lượng `Thread` NMT có thể gồm cả JVM internal threads, không đồng nhất với 12 worker vừa tạo.

### 6.1. So sánh `summary` với `detail`

Chạy **lượt lab mới** (JVM mới), thay cờ startup bằng:

```bash
java -XX:NativeMemoryTracking=detail -Xms32m -Xmx128m NmtLab
```

Tại hai mốc như trên, có thể lưu `detail` và `detail.diff`:

```bash
jcmd <LAB_PID> VM.native_memory detail scale=KB
jcmd <LAB_PID> VM.native_memory baseline
# Sau khi khởi tạo 12 platform threads
jcmd <LAB_PID> VM.native_memory detail.diff scale=KB
```

Lượt `detail` phải là **JVM mới** với PID và baseline mới. Không so số call-site trong lượt `detail` với các giá trị `summary` của JVM cũ như thể chúng là một chuỗi đo liên tục. Một nhóm tăng cho biết **nơi HotSpot ghi nhận tăng**, chưa xác nhận leak nếu không có xu hướng/điều kiện tái hiện.

## 7. Cách diễn giải khi NMT và OS memory không khớp

| Quan sát | Khả năng cần kiểm tra | Kết luận không được vội đưa ra |
| --- | --- | --- |
| NMT `committed` tăng, RSS gần ổn định | Reserved/committed khác resident, trang chưa resident, thay đổi hoạt động JVM | “JVM chắc chắn rò rỉ native memory” |
| RSS tăng mạnh, NMT `committed` không tăng tương ứng | Native allocations ngoài HotSpot, mmap của thư viện, cgroup/page cache, memory accounting | “NMT hỏng” hoặc “chắc chắn không có leak” |
| NMT `Thread` tăng | Số platform threads, stack reserve/commit, thread lifecycle | “Tất cả thread đã leak” chỉ dựa trên một snapshot |
| `Class`/`Code` tăng sau khởi động | Class loading, metaspace, JIT compilation và cache | “Leak” khi chưa ổn định warmup |
| `summary.diff` giảm sau GC hoặc load giảm | Vùng được uncommit/free, thay đổi workload, baseline ban đầu ở thời điểm khác | “Đã hết leak” nếu chuỗi thời gian còn tăng về lâu dài |
| `detail.diff` trỏ tới một HotSpot call site | Allocation site JVM liên quan tới tăng trưởng | “Đã biết Java business method gây leak” nếu chưa kiểm tra code path |
| Không có data sau `shutdown` | Tracking đã dừng; jcmd không restart được | “Có thể bật ngay bằng `VM.set_flag`” |

Làm rõ việc phân tích **xu hướng**: thu ít nhất hai mốc có workload/điều kiện so sánh được, đánh dấu deploy, traffic, GC, class loading và thời điểm thay baseline. Nếu dữ liệu mới mâu thuẫn với giả thuyết leak, cập nhật giả thuyết. Với tăng trưởng ngoài phạm vi NMT, dùng OS native memory profiling, allocator telemetry hoặc công cụ phù hợp của nền tảng trong môi trường được phép.

## 8. Runbook quyết định ở production

### Trước khi bật NMT

- [ ] Xác định câu hỏi: cần tổng theo subsystem (`summary`) hay call site (`detail`)?
- [ ] Xác định **JDK vendor/build**, JVM image và lệnh startup sẽ dùng. NMT phải được bật **trước khi JVM chạy**.
- [ ] Đo cost ở workload đại diện: CPU, throughput, p95/p99, RSS, limits và lỗi.
- [ ] Xác định thời gian theo dõi, cadence snapshot, nơi lưu, quota, owner, quyền xem và retention.
- [ ] Lập cửa sổ deploy/rolling restart nếu phải đổi cấp tracking; thông báo tác động dự kiến và phương án khôi phục.

### Trong khi điều tra

- [ ] Xác minh PID + startup time, NMT level và quyền `jcmd`; không gửi lệnh tới nhiều JVM.
- [ ] Thu snapshot sau warmup **trước khi** đặt baseline; ghi UTC timestamp/uptime.
- [ ] Thu `summary.diff`/`summary` theo cùng workload; nếu `detail` thì thu thêm raw call-site reports.
- [ ] Lưu RSS, cgroup/OS memory, thread count và các sự kiện deploy/GC cùng timeline.
- [ ] Bảo vệ dữ liệu lưu; kiểm tra exit code, file không rỗng và checksum nếu chuyển sang kho dài hạn.

### Trước khi `VM.native_memory shutdown`

- [ ] Đã lưu đủ raw snapshots, baseline time, diff và version/flags/JVM identity.
- [ ] Đã ghi lại thời điểm tracking kết thúc và ai quyết định tắt.
- [ ] Đã chấp nhận mất khả năng tiếp tục NMT trên JVM hiện tại.
- [ ] Có phương án bật lại **bằng restart JVM mới**, không yêu cầu `jcmd` tái bật.
- [ ] Nếu còn nghi ngờ hoặc đang có incident, hoãn shutdown và xin quyết định từ người phụ trách vận hành.

### Sau khi tắt

- [ ] Duy trì OS/container metrics; đánh dấu khoảng không còn NMT.
- [ ] Nếu cần điều tra tiếp, triển khai JVM với NMT startup flag, đặt baseline và tạo chuỗi dữ liệu mới.
- [ ] Xác nhận không dùng chung PID/ảnh chụp giữa các lần restart khi so sánh.
- [ ] Xóa/luân chuyển file theo TTL, bảo toàn bằng chứng theo chính sách sự cố.

## 9. Những nhầm lẫn cần tránh

**“NMT tắt rồi có thể bật lại bằng `jcmd`.”** Sai theo Java 21. `jcmd` có thể `shutdown`, nhưng không `start`/`restart` NMT. Cần restart JVM mới với flag.

**“`summary` có thể nâng cấp lên `detail` trong lúc chạy.”** Không. Call-site tracking cần chọn từ startup; không có cách truy ngược các phân bổ đã qua từ dữ liệu summary.

**“`shutdown` xong vẫn có thể hỏi lại số liệu NMT cũ.”** Không nên dựa vào điều này. Snapshot/baseline tồn tại trong JVM không thay bản xuất ra file. Hãy **xuất dữ liệu trước khi tắt**.

**“Bật NMT luôn chỉ tốn 5% CPU.”** Không chính xác. Tài liệu nêu **5–10% performance overhead**, nhưng chỉ phép đo với workload thật mới cho mức ảnh hưởng tại dịch vụ và percentile cụ thể.

**“`reserved` bằng RAM sử dụng.”** Sai. Đừng so tổng reserved trực tiếp với RSS hoặc container memory limit.

**“NMT bao phủ mọi native code.”** Sai. JNI, third-party libs và nhiều phân bổ ngoài HotSpot không được NMT bao quát. Khi NMT không lý giải được RSS, cần đối chiếu công cụ OS/native profiler.

**“Chỉ cần lưu `summary.diff`.”** Thiếu bối cảnh. Luôn lưu absolute snapshot, baseline time, cấu hình JVM và metric môi trường trước khi tắt.

## 10. Tài liệu đối chiếu (Java 21)

1. [Oracle JDK 21 — Native Memory Tracking: levels, overhead, shutdown và giới hạn restart](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html)
2. [Oracle JDK 21 — Diagnostic Tools: cách đọc reserved/committed, NMT overhead, baseline/diff và phạm vi tracking](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
3. [Oracle JDK 21 — `jcmd` specification: `VM.native_memory` và mức tác động của lệnh](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
4. [Oracle JDK 21 — Troubleshoot Memory Leaks: phạm vi NMT và native code nằm ngoài JVM](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html)
