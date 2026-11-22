# Đo thời gian khởi động và bộ nhớ khi có nhiều tiến trình với AppCDS

> **Java 10 — Vận hành AppCDS.** AppCDS (Application Class-Data Sharing), được giới thiệu bằng **JEP 310 trong Java 10**, có thể giúp ứng dụng Java khởi động nhanh hơn và chia sẻ một phần metadata lớp giữa **nhiều tiến trình JVM** cùng dùng archive tương thích. Muốn đánh giá hiệu quả, cần đo **từ lúc tạo tiến trình tới READY**, **thời điểm cả nhóm tiến trình sẵn sàng** và **bộ nhớ thực sự sử dụng của nhóm**, không chỉ xem một JVM hoặc cộng chỉ số RSS một cách máy móc. Bài hướng dẫn quy trình có đối chứng, các công cụ đang dùng trên JDK hiện đại, ví dụ Java tính toán đã kiểm thử và một harness Linux thu thập số đo thực. Nội dung không dựa vào tùy chọn, chính sách cấp phép hay hành vi legacy chỉ đúng với JDK 10 cũ.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **CDS mặc định**, **application archive của AppCDS** và trạng thái tắt CDS bằng `-Xshare:off`.
2. Giải thích vì sao nhiều JVM cùng memory-map một archive có thể tiết kiệm physical memory mà tổng **RSS của các tiến trình** không giảm tương ứng.
3. Định nghĩa chính xác **per-process startup**, **group readiness** và điểm lấy mẫu bộ nhớ khi N JVM cùng khởi động.
4. Đọc đúng các chỉ số Linux `Rss`, `Pss`, `Private_Clean`, `Private_Dirty` trong `/proc/<PID>/smaps_rollup`; hiểu giới hạn của từng chỉ số.
5. Tổ chức baseline công bằng: **CDS mặc định** so với **CDS + archive ứng dụng** trên cùng bản JDK, ứng dụng, heap, GC, CPU quota và số lượng JVM.
6. Tạo một dynamic archive bằng `-XX:ArchiveClassesAtExit`, nạp bằng `-XX:SharedArchiveFile` và xác minh bằng `-Xlog:cds=info` trên HotSpot được hỗ trợ.
7. Thu thập startup bằng **đồng hồ monotonic từ ngoài JVM**, không nhầm thời gian bắt đầu `main` với thời điểm spawn tiến trình.
8. Phân biệt đo startup **từng JVM**, đo **N JVM khởi động đồng thời** và đo **N JVM khởi động tuần tự**.
9. Biết khi nào dùng `jcmd VM.native_memory` để chẩn đoán, và vì sao Native Memory Tracking (NMT) **không thay thế PSS/RSS từ OS**.
10. Trình bày median, p95, độ biến thiên, tổng PSS và các giới hạn về file cache/cgroup/permissions thay vì kết luận từ một lần đo.
11. Chạy Java lab độc lập với **22 dòng stdout xác định** và dùng harness thực nghiệm không có output cố định trên Linux.
12. Kết luận rõ lợi ích **startup/footprint** mà không tự khẳng định AppCDS làm tăng steady-state throughput.

## 2. Cơ chế AppCDS và điều kiện chia sẻ giữa các JVM

### 2.1. Archive class metadata là gì?

**Class Data Sharing (CDS)** cho phép HotSpot tạo/sử dụng một archive chứa dữ liệu liên quan tới những lớp Java. JVM có thể **memory-map** các vùng dữ liệu phù hợp từ archive, thay vì lặp lại toàn bộ công việc đọc/xử lý metadata của những lớp đó. Các trang chỉ đọc được ánh xạ từ cùng một archive tương thích có thể được **nhiều tiến trình cùng chia sẻ** theo cơ chế quản lý bộ nhớ của OS.

**AppCDS** mở rộng phạm vi tới các lớp ứng dụng được archive. Động cơ chính trong **JEP 310**:
- giảm một phần công việc tải/xử lý class ở lúc khởi động;
- giảm footprint khi nhiều JVM chạy cùng tập class;
- có hiệu quả đặc biệt khi các tiến trình dùng chung archive và lớp được thực sự nạp từ archive.

**Đây không phải:** snapshot heap, backup database, bản biên dịch native của toàn bộ ứng dụng, cơ chế tự chia sẻ object heap giữa các JVM hoặc bảo đảm sẵn sàng phục vụ tức thì.

### 2.2. Một archive chung không biến nhiều JVM thành một JVM

```text
                        app.jsa (archive phù hợp)
                                 |
             +-------------------+-------------------+
             |                   |                   |
          JVM A                JVM B                JVM C
       class maps          class maps          class maps
       private heap        private heap        private heap
       threads/stack       threads/stack       threads/stack
       code cache          code cache          code cache
       app objects         app objects         app objects

           Các trang metadata phù hợp có thể dùng chung
           Heap, thread stack, kết nối và phần lớn runtime
           state vẫn tách biệt theo tiến trình.
```

Nếu có bốn JVM với mỗi JVM dùng 500 MiB heap thì AppCDS không tự biến bốn heap ấy thành một heap 500 MiB. Lợi ích bộ nhớ chủ yếu đến từ metadata lớp/shared mappings phù hợp, trong khi các vùng private vẫn cần thiết cho mỗi tiến trình.

### 2.3. Default CDS đã bật trong nhiều JDK hiện đại

Theo tài liệu **Oracle JDK 25**, bản phân phối Oracle JDK từ JDK 12 có một **default CDS archive** được đóng gói; JVM có thể dùng archive mặc định ở điều kiện tương thích và `-Xshare:off` sẽ tắt CDS.

Để đo **lợi ích bổ sung của AppCDS** cần so sánh:

| Nhóm | Cách chạy | Ý nghĩa |
| --- | --- | --- |
| **A — Baseline** | Chạy ứng dụng bình thường với CDS mặc định | Trạng thái sản phẩm đang sử dụng |
| **B — Candidate** | Cùng JDK, cùng ứng dụng và flags, nhưng thêm archive ứng dụng | Chênh lệch có thể quy cho AppCDS khi kiểm soát nhiễu |
| **C — Diagnostic** | `-Xshare:off` | Tắt **cả CDS** để chẩn đoán tổng ảnh hưởng của chia sẻ lớp; **không phải baseline tương đương A** |

Không nên so **C với B** rồi tuyên bố toàn bộ chênh lệch là phần lợi ích riêng của archive ứng dụng. Cấu hình B có thể còn hưởng CDS cho các lớp nền tảng, vốn đã có ở baseline A.

## 3. Đo chính xác “khởi động nhanh hơn” nghĩa là gì?

### 3.1. Ba mốc thời gian khác nhau

Một phép đo hữu ích cần định nghĩa:

- **`t_launch`:** thời điểm bộ đo bắt đầu yêu cầu OS spawn tiến trình Java, ghi bằng đồng hồ monotonic của **harness ngoài JVM**.
- **`t_ready_i`:** thời điểm JVM thứ i được xác nhận đủ điều kiện phục vụ bằng readiness marker/probe.
- **`t_all_ready`:** thời điểm **JVM cuối cùng** trong nhóm được xác nhận READY.

Đặt:

\[
T_i = t_{\mathrm{ready},i}-t_{\mathrm{launch},i}
\]

\[
T_{\mathrm{group}} =
\max_i(t_{\mathrm{ready},i})-\min_i(t_{\mathrm{launch},i})
\]

`T_i` là **thời gian khởi động của tiến trình i**. `T_group` là **thời gian từ lần spawn đầu tới khi toàn nhóm sẵn sàng**, hữu ích khi tăng scale từ 0 lên N replica.

**Không được gộp hai số này:** nhóm bốn JVM có thể có median startup nhanh nhưng một JVM rất chậm khiến `T_group` vẫn lớn. Ngược lại, nếu spawn lần lượt, `T_group` còn chứa khoảng trễ do chính chương trình khởi tạo các tiến trình.

### 3.2. READY phải phản ánh hợp đồng ứng dụng

Với HTTP microservice, READY có thể là:
- socket đã mở;
- health/readiness endpoint trả thành công;
- dependency thiết yếu như database/cache sẵn sàng;
- một request nghiệp vụ tối thiểu được phục vụ thành công.

Với CLI/batch, READY có thể là “tác vụ đầu tiên bắt đầu được xử lý” hoặc “toàn bộ batch đã hoàn thành”. **Chọn trước một mốc phù hợp với mục tiêu đo.**

`System.nanoTime()` đặt ở đầu `main` **không** đo toàn bộ process launch → ready vì thời gian JVM bootstrap trước `main` đã trôi qua. Các sự kiện trước `main` có thể chính là nơi CDS/AppCDS có tác động, nên dùng đồng hồ ngoài là rất quan trọng.

### 3.3. Đồng hồ monotonic và độ phân giải

Ở Python, `time.perf_counter_ns()` hoặc `time.monotonic_ns()` cung cấp đồng hồ monotonic thích hợp đo khoảng thời gian. Ở Java, `System.nanoTime()` thích hợp đo elapsed time **trong cùng tiến trình**; nó không giúp tự quan sát mốc trước khi JVM bắt đầu.

Một harness đo READY qua HTTP polling mỗi 500 ms có thể tạo sai số rất lớn nếu thay đổi kỳ vọng chỉ 20–50 ms. Dùng interval phù hợp, ghi độ phân giải và sử dụng cách đồng bộ marker/pipe nếu test application cho phép.

**Lưu ý:** Nếu một tiến trình in `READY` rồi harness đọc dòng này qua pipe, mốc `t_ready` phản ánh thời điểm **harness nhận thông điệp**, không phải tuyệt đối thời điểm dòng code in marker. Độ trễ scheduling/pipe là một phần sai số và cần giữ tương đương giữa A/B.

### 3.4. Khởi động đồng thời khác khởi động tuần tự

Với N=4, có hai kịch bản hữu ích:

**Concurrent scale-out:** spawn bốn JVM trong thời gian ngắn, mỗi JVM bắt đầu chạy trong khi những JVM khác đang startup. Cần đo:
- median/max `T_i`;
- `T_group`;
- CPU quota/CPU throttling trong cả đợt;
- băng thông disk/page cache và contention khi nhiều JVM đọc archive;
- xác suất JVM thất bại hoặc timeout.

**Sequential startup:** chờ JVM thứ i READY rồi mới spawn JVM i+1. Điều này giảm CPU/IO contention nhưng làm thời gian cả nhóm READY cộng dồn, nên không thể so trực tiếp với scale-out đồng thời.

Cần làm rõ câu hỏi vận hành: **rollout từng pod, autoscale nhiều pod cùng lúc, hay khởi động hàng loạt worker ngắn hạn?** Các kịch bản khác nhau sẽ cho những lợi ích AppCDS khác nhau.

## 4. Đo bộ nhớ nhiều JVM: RSS, PSS và private memory

### 4.1. Vì sao cộng RSS dễ đếm trùng?

**RSS (Resident Set Size)** của một tiến trình bao gồm những trang bộ nhớ resident mà tiến trình đang map, gồm cả trang private và shared. Nếu bốn JVM cùng map một trang từ `app.jsa`, trang ấy có thể xuất hiện trong RSS của **cả bốn**.

Vì thế:

\[
\sum_i RSS_i
\]

có thể **đếm lại các trang vật lý chung nhiều lần**, không phải tổng RAM duy nhất mà nhóm JVM dùng.

**PSS (Proportional Set Size)** phân chia chi phí của mỗi trang resident giữa các tiến trình cùng sử dụng trang. Nếu một trang được chia đều giữa bốn tiến trình thì mỗi tiến trình ghi nhận **1/4 trang vào PSS** của mình. Tổng PSS của nhóm là thước đo thực tế hơn để so các workload nhiều JVM **trong các điều kiện được kiểm soát**.

Lưu ý: Nếu các trang cũng được chia sẻ với **tiến trình ngoài nhóm**, tổng PSS của nhóm chỉ nhận **phần tỷ lệ của nhóm**; nó không phải một đồng hồ đếm toàn bộ physical RAM đang cấp cho node. Cách diễn giải phải nói rõ ranh giới đo.

### 4.2. Ví dụ chia sẻ 80 MiB giữa bốn JVM

Giả định:
- 4 tiến trình JVM.
- Mỗi JVM có **100 MiB private resident**.
- Có **80 MiB trang resident shared** dùng chung chính xác bởi 4 JVM này.
- Bỏ qua mọi vùng khác để minh họa.

Với mỗi JVM:

\[
RSS_{\mathrm{mỗi\ JVM}}=100+80=180\ \mathrm{MiB}
\]

\[
PSS_{\mathrm{mỗi\ JVM}}=100+\frac{80}{4}=120\ \mathrm{MiB}
\]

Tổng nhóm:

| Chỉ số | Giá trị |
| --- | ---: |
| Tổng private resident | 4 × 100 = **400 MiB** |
| Shared resident thực sự | **80 MiB** |
| Tổng RSS đọc ở bốn JVM | 4 × 180 = **720 MiB** |
| Tổng PSS đọc ở bốn JVM | 4 × 120 = **480 MiB** |
| Số MiB shared bị đếm trùng trong tổng RSS | **240 MiB** |

Ví dụ này giả định **không có tiến trình ngoài nhóm chia sẻ các trang đó**. Nó chỉ minh họa cách RSS/PSS hạch toán shared pages, **không phải đo thực tế một JDK**.

### 4.3. USS và vùng private

**USS (Unique Set Size)** thường được diễn giải là các trang resident private của tiến trình. Trên Linux, có thể xấp xỉ qua tổng `Private_Clean + Private_Dirty` trong `smaps`/`smaps_rollup` của thời điểm đọc; cần chú ý thêm các field liên quan swap và những khác biệt phiên bản kernel/tool.

- `Private_Clean`: trang private không bị đánh dấu dirty.
- `Private_Dirty`: trang private bị thay đổi.
- `Shared_Clean`, `Shared_Dirty`: các trang shared được kernel phân loại tại thời điểm lấy mẫu.

**Không suy từ một giá trị USS bằng tổng chi phí bộ nhớ của JVM.** Nó không bao gồm phần chia sẻ mà tiến trình thực sự sử dụng, và không phải phép đo dung lượng heap. Với nhóm nhiều JVM, thường nên báo ít nhất **RSS, PSS, private resident** và **tổng PSS của nhóm**.

### 4.4. `/proc/<PID>/smaps_rollup` trên Linux

Linux kernel cung cấp:

```text
/proc/<PID>/smaps
/proc/<PID>/smaps_rollup
```

`smaps` mô tả theo từng memory mapping; `smaps_rollup` tổng hợp một số liệu cho **toàn bộ mapping của tiến trình**, thường nhanh hơn và phù hợp cho phép đo nhiều JVM.

Các trường thường gặp:

```text
Rss:           <number> kB
Pss:           <number> kB
Private_Clean: <number> kB
Private_Dirty: <number> kB
```

Ở đây `kB` là nhãn đơn vị mà kernel hiển thị cho các số liệu bộ nhớ, thường tính theo 1024 byte. Trong bảng báo cáo hãy thống nhất **MiB = KiB / 1024**, không trộn ký hiệu `MB` thập phân với số đo vừa chia cho 1024.

Trên Linux, có thể xem:

```bash
cat /proc/12345/smaps_rollup
grep -E '^(Rss|Pss|Private_Clean|Private_Dirty):' /proc/12345/smaps_rollup
```

**Thay `12345` bằng PID thật** của một JVM đang còn sống. Đọc các trường này có thể cần quyền tương ứng; container hoặc security policy có thể chặn truy cập. Nếu không đọc được, báo thiếu quyền/thiếu dữ liệu thay vì tự điền số 0.

### 4.5. Snapshot và peak khác nhau

`smaps_rollup` đọc được trạng thái **ở một thời điểm**. Nó không tự cung cấp:
- peak RSS từ lúc tiến trình sinh ra;
- tổng memory allocation qua cả vòng đời;
- lượng memory vật lý một file JSA chiếm trên disk;
- số memory một JVM đã dùng từ startup đến lúc sample.

Để đo **memory at READY**, lấy mẫu ngay khi nhóm READY; để đo **warm-state memory**, chờ theo policy rồi sample; để đo peak cần lấy mẫu định kỳ hoặc dùng công cụ/cgroup phù hợp. **Không trộn snapshot warm-state với peak startup** rồi coi chúng là cùng một metric.

## 5. Native Memory Tracking (NMT) có giúp đánh giá AppCDS không?

Có, **nhưng chỉ làm công cụ bổ trợ**.

HotSpot hỗ trợ NMT, ví dụ bật:

```text
-XX:NativeMemoryTracking=summary
```

Sau đó kiểm tra JVM đang chạy:

```bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
```

Theo tài liệu Oracle Java SE 25:
- NMT **tắt mặc định**; phải bật khi khởi động.
- NMT theo dõi một phần cấu trúc bộ nhớ nội bộ của HotSpot, **không theo dõi mọi thư viện native bên thứ ba**.
- **NMT không cung cấp hình ảnh đầy đủ về CDS archive**, nên không lấy `VM.native_memory summary` làm phép đo thay thế tổng PSS.
- Bật NMT có overhead hiệu năng, tài liệu Oracle ghi nhận khoảng **5–10%** trong một số trường hợp; phải kiểm soát chuyện này khi so benchmark.
- `reserved` khác `committed`, và cả hai **không tự đồng nghĩa resident physical memory**.

Quy tắc thực hành:
- Nếu KPI chính là **startup**, đo với **NMT tắt ở cả A/B** để hạn chế nhiễu, sau đó chạy pha chẩn đoán NMT riêng nếu cần.
- Nếu muốn so NMT trong A/B, **bật cùng mức NMT ở cả hai nhóm** và ghi rõ overhead.
- Khi KPI là **memory footprint của N JVM**, ưu tiên OS-level PSS/private/cgroup metrics và dùng NMT để giải thích một số phần chênh lệch ở VM.

Đừng bật NMT ở candidate nhưng để baseline tắt rồi quy số đo memory/CPU khác nhau cho AppCDS.

## 6. Thiết kế thí nghiệm A/B có tính so sánh

### 6.1. Tất cả điều kiện phải được giữ đồng nhất

| Nhóm điều kiện | Cần giữ nhất quán |
| --- | --- |
| JVM | JDK distribution, version/build, kiến trúc CPU, JDK flags khác CDS |
| Ứng dụng | Cùng bytecode/JAR, libraries, classpath/module path, config |
| Runtime memory | `-Xms`, `-Xmx`, metaspace/GC flags nếu dùng |
| Tài nguyên | CPU quota, số core thực, RAM, cgroup limits, swap policy |
| Nhiều tiến trình | Cùng N, cùng lịch spawn, cùng shared archive, cùng isolation |
| Readiness | Cùng marker/probe và timeout, cùng dependencies |
| Workload | Cùng startup path, class loading path, dataset và traffic |
| Cache | Ghi trạng thái OS page cache/JIT warmup; có chiến lược lặp và đảo thứ tự |
| Bộ đo | Cùng timer, poll interval, công cụ snapshot và quyền truy cập |
| Lỗi | Ghi số startup fail, bị timeout, archive rejected; không âm thầm loại khỏi phân phối |

Nếu baseline chạy trên JDK 21 còn candidate chạy JDK 25, bạn đã thay nhiều biến (JIT, GC, archive/AOT cơ chế), không thể kết luận chênh lệch do riêng AppCDS Java 10.

### 6.2. Đo hai workload riêng

**Thử nghiệm A — Startup/restart:**
1. Tạo một nhóm N JVM từ trạng thái đã biết.
2. Đo launch → READY theo từng JVM.
3. Đo thời điểm tất cả đã READY.
4. Lặp nhiều trial, có cả baseline và candidate, đảo hoặc ngẫu nhiên hóa thứ tự.
5. Thống kê median, p95 hoặc distribution phù hợp, cùng số lần fail/timeout.

**Thử nghiệm B — Memory at stable state:**
1. Tạo N JVM và để **toàn nhóm READY**.
2. Chạy workload giống nhau đủ thời gian để đạt trạng thái cần đo.
3. Chụp RSS/PSS/private của toàn bộ N PID **trong khoảng thời gian tương đồng**.
4. Tổng hợp, ghi số lượng JVM, tuổi tiến trình và dữ liệu cgroup/host khi có.
5. Lặp nhiều lần để thấy độ biến thiên và kiểm tra ảnh hưởng cache, GC.

Chỉ đo bộ nhớ của **một JVM** có thể bỏ sót lợi ích sharing ở kịch bản bốn, tám hoặc hàng chục JVM. Ngược lại, chỉ đo **tổng node memory** khi node chạy workload khác có thể bị nhiễu đáng kể.

### 6.3. Đừng so snapshot ở các trạng thái khác nhau

Nếu candidate READY sớm hơn baseline, lấy mẫu cả hai “ở giây thứ 1 kể từ launch” có thể khiến:
- candidate đã chạy application logic và cấp phát cache;
- baseline còn đang class loading.

Đó không phải cùng trạng thái nghiệp vụ. Nên công bố rõ snapshot thuộc loại **at READY**, **N giây sau READY**, hay **after steady warmup**, và giữ nguyên quy tắc cho hai nhóm. Thông thường cần **nhiều snapshot** để hiểu memory profile thay vì một mẫu đơn lẻ.

### 6.4. Thống kê để tránh kết luận từ nhiễu

Với từng trial, ghi:
- N JVM được yêu cầu spawn, số đã READY và số thất bại.
- `median(T_i)` và `max(T_i)` của N tiến trình.
- `T_group`, thời gian từ đợt launch đầu tới lần READY cuối.
- Tổng RSS, PSS, private resident (MiB), và PSS trên mỗi replica.
- CPU/time, error messages, page faults và archive coverage nếu đo.
- Trial ID, JDK version, flags, thứ tự A/B, cấu hình tài nguyên.

Khi N=4, **median startup trong một trial** chỉ phản ánh bốn tiến trình ở trial đó; không phải một phân phối đáng tin để suy ra p95 startup của mọi lượt deploy. Hãy làm nhiều trial và tính p95 trên bộ mẫu phù hợp, báo số lượng mẫu thật.

## 7. Quy trình AppCDS trên HotSpot hiện đại

Các ví dụ dưới đây dành cho **HotSpot** với những option đã được Oracle JDK 25 tài liệu hóa, không phải contract của mọi JVM provider.

### 7.1. Chuẩn bị một ứng dụng nhỏ cho ví dụ

Tạo file **`CdsWorker.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Map;

public final class CdsWorker {
    private static void loadRepresentativeClasses() {
        String formatted = LocalDate.of(2030, 1, 2)
                .format(DateTimeFormatter.ISO_LOCAL_DATE);

        Map<String, Integer> data = new HashMap<>();
        data.put(formatted, 1);
        if (data.get(formatted) != 1) {
            throw new IllegalStateException("wrong data");
        }
    }

    public static void main(String[] args) throws Exception {
        loadRepresentativeClasses();

        // Training phải kết thúc bình thường để JVM ghi archive.
        if (args.length > 0 && "--train".equals(args[0])) {
            return;
        }

        System.out.println("READY");
        System.out.flush();

        // Giữ JVM sống để harness lấy snapshot memory.
        Thread.sleep(60_000L);
    }
}
```

Biên dịch trên đúng JDK đang dùng cho thí nghiệm:

```bash
javac CdsWorker.java
```

`CdsWorker` cố tình đơn giản để người học thấy rõ quy trình. **Archive của ứng dụng nhỏ có thể giúp rất ít hoặc không giúp**, vì phần lớn lớp được dùng đã có trong CDS mặc định; mục tiêu ở đây là luyện cách đo, không phải hứa cải thiện có thể thấy rõ với 4 JVM toy.

### 7.2. Tạo dynamic application archive

Trong thư mục có `CdsWorker.class`:

```bash
java -XX:ArchiveClassesAtExit=app.jsa -cp . CdsWorker --train
```

Tác vụ training chạy đường code mẫu, sau đó kết thúc bình thường để HotSpot có thể ghi `app.jsa`. Không tính thời gian **training/dump** này như mỗi lần startup của production **nếu** archive được tạo sẵn ở build pipeline.

Xác minh sử dụng archive bằng một run chẩn đoán:

```bash
java -Xlog:cds=info -XX:SharedArchiveFile=app.jsa -cp . CdsWorker --train
```

Xem log để xác nhận archive được map/chấp nhận; nếu bị từ chối do JDK, classpath, nội dung ứng dụng, option hoặc platform mismatch, thí nghiệm candidate không hợp lệ. Có thể sử dụng các tag class-load thích hợp để kiểm tra lớp nào được load từ archive ở pha diagnosis; không dựa vào sự tồn tại của file `app.jsa` mà khẳng định nó đã được sử dụng.

**Không chạy log rất chi tiết trong chỉ một nhánh của benchmark chính:** logging tạo I/O và overhead. Chỉ dùng run chẩn đoán riêng, hoặc bật cùng mức logging cho cả A/B.

### 7.3. Các lệnh baseline và candidate

```bash
# Baseline: JVM thường với default CDS.
java -Xms64m -Xmx256m -cp . CdsWorker

# Candidate: cùng JVM/heap/app, thêm archive ứng dụng.
java -Xms64m -Xmx256m \
  -XX:SharedArchiveFile=app.jsa \
  -cp . CdsWorker
```

Dấu `\` nối dòng trong ví dụ dành cho **shell POSIX**. Trên PowerShell, hãy đặt toàn bộ lệnh trên một dòng hoặc dùng cú pháp nối dòng của PowerShell.

**Không dùng `-Xshare:off` làm baseline cho phép đo incremental AppCDS**. Tùy bản phân phối JDK, việc dùng dynamic archive có điều kiện tương thích với static default archive; làm theo tài liệu `java` launcher của phiên bản đang chạy.

### 7.4. Tương thích archive và bảo mật

Archive CDS là artifact liên quan chặt tới JDK/application:
- Không tự đổi JDK major/minor/update, classpath hay class binaries rồi giả định archive cũ vẫn dùng được.
- Tạo archive bằng đúng runtime và đường class loading đại diện ứng dụng thật.
- Lưu archive có provenance/checksum và không cho user không tin cậy sửa nội dung archive.
- Xác nhận việc dùng archive ở mỗi vòng cập nhật JDK/JAR.
- Có quy trình fallback/rollback nếu archive không tương thích hoặc load bị lỗi.
- Nếu nhu cầu dựa vào tính năng mới của JDK 24/25 **AOT Cache**, báo đúng tên cơ chế và flags thay vì gọi tất cả là AppCDS Java 10.

**`-Xshare:on` dành chủ yếu cho testing**; Oracle cảnh báo nó có thể làm JVM thoát nếu archive không dùng được, không nên áp dụng rộng trong production.

## 8. Harness Linux đo N JVM thật bằng Python 3 tiêu chuẩn

Phần này dành riêng cho **Linux**, vì dùng `/proc/PID/smaps_rollup`. Nó là ví dụ vận hành có thể chạy khi máy có Java, Python 3, quyền đọc `/proc` và file `CdsWorker.class`/`app.jsa` chuẩn bị ở trên. **Output phụ thuộc hoàn toàn máy và lần chạy**; không có một stdout “chính xác” cho phép đo thật.

### 8.1. Ý tưởng

- Chạy **N** child JVM gần đồng thời từ một Python parent.
- Parent bắt đầu `perf_counter_ns()` **ngay trước** khi spawn từng JVM.
- Mỗi child in duy nhất dòng `READY` rồi giữ tiến trình sống.
- Parent dùng `selectors` để nhận READY từ mọi child, tránh phải chờ theo thứ tự tạo và làm lệch mốc READY của child sau.
- Sau khi tất cả READY, chờ một khoảng có chủ đích trước snapshot.
- Đọc `smaps_rollup` từng PID để lấy RSS/PSS/private (KiB), cộng toàn nhóm, hiển thị MiB.
- Dọn dẹp toàn bộ JVM trong `finally`, kể cả khi xảy ra timeout/lỗi.
- Không bật NMT hoặc logging CDS chi tiết trong thời gian đo.

### 8.2. Mã `bench_multi.py`

```python
#!/usr/bin/env python3
"""Linux-only demonstration: startup and /proc memory for N JVMs."""
import pathlib
import selectors
import statistics
import subprocess
import sys
import time

TIMEOUT_SECONDS = 30.0
MEMORY_SAMPLE_DELAY_SECONDS = 1.0


def read_memory_kib(pid):
    """Return RSS, PSS and private resident KiB from Linux smaps_rollup."""
    path = pathlib.Path(f"/proc/{pid}/smaps_rollup")
    required = {"Rss", "Pss", "Private_Clean", "Private_Dirty"}
    found = {}

    for line in path.read_text(encoding="ascii").splitlines():
        key, colon, tail = line.partition(":")
        if colon and key in required:
            found[key] = int(tail.strip().split()[0])

    missing = required.difference(found)
    if missing:
        raise RuntimeError(
            f"missing /proc fields for PID {pid}: {sorted(missing)}"
        )

    found["Private"] = (
        found["Private_Clean"] + found["Private_Dirty"]
    )
    return found


def run(mode, replicas):
    if mode not in ("baseline", "archive"):
        raise ValueError("mode must be baseline or archive")
    if replicas < 1:
        raise ValueError("replicas must be >= 1")
    if mode == "archive" and not pathlib.Path("app.jsa").is_file():
        raise RuntimeError("app.jsa is missing; run the training step")

    vm_flags = ["-Xms64m", "-Xmx256m"]
    if mode == "archive":
        vm_flags.append("-XX:SharedArchiveFile=app.jsa")

    children = []
    launched_ns = {}
    ready_ns = {}
    selector = selectors.DefaultSelector()

    try:
        for _ in range(replicas):
            command = [
                "java", *vm_flags, "-cp", ".", "CdsWorker"
            ]
            started = time.perf_counter_ns()
            child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            children.append(child)
            launched_ns[child.pid] = started
            selector.register(
                child.stdout, selectors.EVENT_READ, child
            )

        deadline = time.perf_counter() + TIMEOUT_SECONDS
        while len(ready_ns) < replicas:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise TimeoutError("not all JVMs became READY")

            events = selector.select(remaining)
            for key, _ in events:
                child = key.data
                line = key.fileobj.readline()
                received = time.perf_counter_ns()

                if line != b"READY\n":
                    detail = line[:200].decode(
                        "utf-8", errors="replace"
                    )
                    raise RuntimeError(
                        f"PID {child.pid} did not say READY: {detail!r}"
                    )

                ready_ns[child.pid] = received
                selector.unregister(key.fileobj)

        # Snapshot at a specified offset after last READY, not at peak.
        time.sleep(MEMORY_SAMPLE_DELAY_SECONDS)
        memory = [read_memory_kib(p.pid) for p in children]

        startup_ms = [
            (ready_ns[p.pid] - launched_ns[p.pid]) / 1e6
            for p in children
        ]
        group_ms = (
            max(ready_ns.values()) - min(launched_ns.values())
        ) / 1e6

        total_rss_kib = sum(m["Rss"] for m in memory)
        total_pss_kib = sum(m["Pss"] for m in memory)
        total_private_kib = sum(m["Private"] for m in memory)

        print(f"mode: {mode}, replicas: {replicas}")
        print(
            f"per-JVM startup median ms: "
            f"{statistics.median(startup_ms):.2f}"
        )
        print(f"per-JVM startup max ms: {max(startup_ms):.2f}")
        print(f"group all-ready ms: {group_ms:.2f}")
        print(f"aggregate RSS MiB: {total_rss_kib / 1024:.2f}")
        print(f"aggregate PSS MiB: {total_pss_kib / 1024:.2f}")
        print(
            f"aggregate private resident MiB: "
            f"{total_private_kib / 1024:.2f}"
        )

    finally:
        selector.close()
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            if child.stdout:
                child.stdout.close()
            if child.stderr:
                child.stderr.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python3 bench_multi.py baseline|archive N")
    run(sys.argv[1], int(sys.argv[2]))
```

### 8.3. Chạy thí nghiệm

Với Linux và Python 3:

```bash
# Chuẩn bị:
javac CdsWorker.java
java -XX:ArchiveClassesAtExit=app.jsa -cp . CdsWorker --train

# Đối chứng A:
python3 bench_multi.py baseline 4

# Candidate B:
python3 bench_multi.py archive 4
```

Kết quả ví dụ định dạng, **các số sau dấu hai chấm chỉ là MINH HỌA**:

```text
mode: baseline, replicas: 4
per-JVM startup median ms: 245.70
per-JVM startup max ms: 272.13
group all-ready ms: 290.82
aggregate RSS MiB: 284.90
aggregate PSS MiB: 214.32
aggregate private resident MiB: 183.21
```

Ở nhóm archive, cùng định dạng nhưng số liệu có thể lớn hơn, nhỏ hơn hoặc gần bằng baseline. Các số bên trên **không phải một phép đo đã thực hiện** và không được trình bày như kết quả thật của AppCDS.

### 8.4. Những giới hạn của harness

1. Parent nhận `READY` qua pipe; có sai số scheduling/pipe; không tương đương HTTP readiness của service thật.
2. Harness spawn các JVM trong vòng lặp nhanh, **không đồng thời đúng cùng một nanosecond**. `T_group` bao gồm cả thời gian tạo lần lượt những process.
3. Mỗi child chỉ chạy `loadRepresentativeClasses` và sleep; không có request/traffic hoặc JIT warmup thực tế.
4. Chụp bộ nhớ **1 giây sau khi READY cuối**; đây là snapshot tĩnh, không phải startup peak.
5. Chỉ chạy trên Linux có `smaps_rollup` và quyền truy cập; nếu không có dữ liệu, **phải báo lỗi**, không dùng 0 giả.
6. 4 child có thể dùng shared pages với JVM khác trên máy; PSS tổng nhóm bị ảnh hưởng bởi các tiến trình ngoài thí nghiệm.
7. Python parent cũng tiêu thụ bộ nhớ/CPU, chưa được tính vào số tổng các JVM; nếu đo chi phí **toàn hệ thống**, phải đo cả node/container/pod theo hợp đồng.
8. Kernel page cache, numa, CPU throttling, antivirus/scanning, background load và JDK flags có thể làm kết quả khác giữa trial.
9. `stderr` được nối pipe để tránh làm rối stdout, nhưng ví dụ không trình bày đầy đủ log khi child thất bại; trong hệ thống vận hành nên lưu stderr vào file riêng theo trial với giới hạn kích thước.
10. Chỉ có một lần chạy baseline và candidate là chưa đủ. Cần **nhiều trial và đảo thứ tự** để đánh giá nhiễu.
11. Nếu JVM chạy hết `Thread.sleep(60_000L)` trước khi lấy mẫu, script có thể báo lỗi đọc `/proc`; thực nghiệm phải bảo đảm tiến trình còn sống ở thời điểm chụp.
12. Không chạy trên môi trường production đang xử lý dữ liệu quan trọng chỉ để kiểm thử demo; cần workload/test account và resource limit dành riêng.

Nếu không có quyền đọc `smaps_rollup`, vẫn có thể đo startup và dùng bộ đo memory OS khác, nhưng **không được gọi số RSS đó là PSS**. Trên Windows/macOS, dùng công cụ native và diễn giải đơn vị theo tài liệu hệ điều hành; không có đường dẫn `/proc/PID/smaps_rollup` portable.

### 8.5. Điểm nâng cấp cho benchmark nghiêm túc

Một harness sản xuất nên:
- Lặp 20–50 trial hoặc số trial do thống kê/độ nhiễu quyết định, xen kẽ A/B.
- Lưu raw measurements theo trial: mỗi PID, mốc launch/ready, RSS/PSS, exit status.
- Có deadline chung, bắt lỗi và **không loại những trial thất bại khỏi phân phối mà không báo**.
- Warmup phụ thuộc workload thật, không chỉ sleep 1 giây.
- Đo memory theo chuỗi thời gian để lấy peak và steady snapshots.
- Thu thập cgroup memory (đúng container), CPU throttling, page faults và NUMA nếu cần.
- Công bố phiên bản JDK, SHA artifact/JS archive, tất cả JVM flags và cấu hình máy.

Bài tập ở đây làm rõ cách đo; không biến một harness demo thành công cụ benchmark chính thức khi chưa đánh giá các nhiễu và điều kiện thất bại.

## 9. Java lab độc lập: phân tích nhiều JVM bằng số liệu giả định

Trước khi đo thật, hãy hiểu số liệu nên được tính và báo như thế nào. Chương trình này dùng **một bộ dữ liệu giả định** để có stdout chính xác trên mọi JDK 17+; nó **không nạp hoặc benchmark AppCDS**.

### 9.1. Mã nguồn Java

Lưu thành **`MultiJvmAppCdsMetricsLab.java`**:

```java
import java.util.Arrays;
import java.util.Locale;

public class MultiJvmAppCdsMetricsLab {
    record Observations(
            long[] readyMs,
            long rssMiBEach,
            long pssMiBEach) {
    }

    static double median(long[] values) {
        if (values.length == 0) {
            throw new IllegalArgumentException("empty samples");
        }
        long[] sorted = values.clone();
        Arrays.sort(sorted);
        int middle = sorted.length / 2;

        return sorted.length % 2 == 1
                ? sorted[middle]
                : sorted[middle - 1] / 2.0
                        + sorted[middle] / 2.0;
    }

    static double decrease(long before, long after) {
        if (before <= 0 || after < 0) {
            throw new IllegalArgumentException("invalid inputs");
        }
        return (before - after) * 100.0 / before;
    }

    public static void main(String[] args) {
        Observations baseline = new Observations(
                new long[]{1230, 1170, 1290, 1250},
                186,
                150);

        Observations appcds = new Observations(
                new long[]{910, 870, 960, 900},
                183,
                136);

        long replicas = baseline.readyMs().length;

        long baseRss =
                Math.multiplyExact(baseline.rssMiBEach(), replicas);
        long cdsRss =
                Math.multiplyExact(appcds.rssMiBEach(), replicas);
        long basePss =
                Math.multiplyExact(baseline.pssMiBEach(), replicas);
        long cdsPss =
                Math.multiplyExact(appcds.pssMiBEach(), replicas);

        System.out.println("workers: " + replicas);
        System.out.printf(Locale.ROOT,
                "baseline median startup ms: %.1f%n",
                median(baseline.readyMs()));
        System.out.printf(Locale.ROOT,
                "appcds median startup ms: %.1f%n",
                median(appcds.readyMs()));
        System.out.printf(Locale.ROOT,
                "median startup saved ms: %.1f%n",
                median(baseline.readyMs())
                        - median(appcds.readyMs()));
        System.out.printf(Locale.ROOT,
                "median startup reduction percent: %.1f%n",
                (median(baseline.readyMs())
                        - median(appcds.readyMs()))
                        * 100.0 / median(baseline.readyMs()));

        System.out.println("baseline aggregate RSS MiB: " + baseRss);
        System.out.println("appcds aggregate RSS MiB: " + cdsRss);
        System.out.println("baseline aggregate PSS MiB: " + basePss);
        System.out.println("appcds aggregate PSS MiB: " + cdsPss);
        System.out.println("aggregate PSS saved MiB: "
                + (basePss - cdsPss));
        System.out.printf(Locale.ROOT,
                "aggregate PSS reduction percent: %.1f%n",
                decrease(basePss, cdsPss));

        long privateMiB = 100;
        long sharedMiB = 80;
        long perProcessRss = privateMiB + sharedMiB;
        long perProcessPss = privateMiB + sharedMiB / replicas;

        System.out.println(
                "illustrative private per-process MiB: " + privateMiB);
        System.out.println(
                "illustrative shared physical MiB: " + sharedMiB);
        System.out.println(
                "illustrative per-process RSS MiB: " + perProcessRss);
        System.out.println(
                "illustrative per-process PSS MiB: " + perProcessPss);
        System.out.println(
                "illustrative aggregate RSS MiB: "
                        + perProcessRss * replicas);
        System.out.println(
                "illustrative aggregate PSS MiB: "
                        + perProcessPss * replicas);
        System.out.println(
                "RSS shared double-count MiB: "
                        + (perProcessRss - perProcessPss) * replicas);
        System.out.println(
                "closed-group shared counted once: "
                        + (perProcessPss * replicas
                            == privateMiB * replicas + sharedMiB));

        System.out.println(
                "steady throughput proven higher: false");
        try {
            median(new long[0]);
        } catch (IllegalArgumentException ex) {
            System.out.println("empty sample rejected: true");
        }
        System.out.println(
                "synthetic data, not measured AppCDS: true");
    }
}
```

### 9.2. Biên dịch và chạy

```bash
javac MultiJvmAppCdsMetricsLab.java
java MultiJvmAppCdsMetricsLab
```

### 9.3. Stdout xác định (22 dòng)

```text
workers: 4
baseline median startup ms: 1240.0
appcds median startup ms: 905.0
median startup saved ms: 335.0
median startup reduction percent: 27.0
baseline aggregate RSS MiB: 744
appcds aggregate RSS MiB: 732
baseline aggregate PSS MiB: 600
appcds aggregate PSS MiB: 544
aggregate PSS saved MiB: 56
aggregate PSS reduction percent: 9.3
illustrative private per-process MiB: 100
illustrative shared physical MiB: 80
illustrative per-process RSS MiB: 180
illustrative per-process PSS MiB: 120
illustrative aggregate RSS MiB: 720
illustrative aggregate PSS MiB: 480
RSS shared double-count MiB: 240
closed-group shared counted once: true
steady throughput proven higher: false
empty sample rejected: true
synthetic data, not measured AppCDS: true
```

Dữ liệu **100/80/120/180 MiB** ở phần chia sẻ là một ví dụ tách biệt với bộ dữ liệu **600/544 MiB tổng PSS** phía trên. Cả hai đều **giả lập**, không nên cộng chéo chúng như các phép đo cùng một nhóm JVM.

### 9.4. Diễn giải chính xác các kết quả

**Startup:** median baseline 1.240 ms, candidate 905 ms, giảm **335 ms** hay khoảng **27,0%** trong tập dữ liệu giả định. Điều này đo **median thời gian các tiến trình READY** chứ không đo thời gian cả nhóm READY; muốn tính `T_group` cần cả mốc launch và ready của từng tiến trình.

**RSS:** tổng baseline 744 MiB, candidate 732 MiB. Đó là **tổng RSS**, có khả năng double-count shared pages; không được coi chênh lệch 12 MiB là toàn bộ bộ nhớ vật lý tiết kiệm.

**PSS:** tổng baseline 600 MiB và candidate 544 MiB; giảm **56 MiB**, tương ứng **9,3%**. Chỉ trong bối cảnh các JVM/OS/khoảng thời gian được kiểm soát, đây mới là một loại bằng chứng về footprint. Không suy ra tỉ lệ này cho JDK khác.

**Mô hình trang chia sẻ:** bốn JVM cùng dùng 80 MiB shared resident và mỗi JVM có 100 MiB private, nên tổng RSS=720 MiB còn tổng PSS=480 MiB. Chênh 240 MiB là phần bị tính nhiều lần khi cộng RSS.

**Throughput:** mọi phép tính trên **không có yêu cầu thực tế nào**, nên dòng `steady throughput proven higher: false` nhắc rằng startup/PSS không chứng minh requests/second đã tăng.

## 10. Đọc kết quả đo và ra quyết định

### 10.1. Báo cáo phải phân biệt các đại lượng

Một bảng thực nghiệm nên có dạng:

| Chỉ số | Baseline (CDS mặc định) | Candidate (AppCDS) | Cần ghi chú |
| --- | --- | --- | --- |
| Số replica N | N | N | Cùng thời điểm/cách spawn |
| Median startup per-JVM | ms | ms | Đo launch → readiness |
| P95 startup per-JVM | ms | ms | Nhiều trial, có số mẫu |
| Group all-ready | ms | ms | Từ launch đầu đến READY cuối |
| Startup failures/timeouts | count | count | Không loại bỏ thất bại |
| Aggregate RSS | MiB | MiB | Có thể cộng trùng trang chung |
| Aggregate PSS | MiB | MiB | Thực tế hơn cho nhóm JVM |
| Aggregate private resident | MiB | MiB | `Private_Clean+Private_Dirty` nếu Linux |
| Host/container memory | MiB | MiB | Có thể gồm page cache/sidecars khác |
| Steady RPS/P99 (nếu đo) | metric riêng | metric riêng | Không suy từ startup/PSS |
| Archive verified | default | yes/no | Log chẩn đoán độc lập |

Kết luận mẫu **có điều kiện**:

> “Trên N=4 JVM cùng JDK/cấu hình, application archive làm median startup giảm X ms (Y%) và tổng PSS sau READY giảm Z MiB so với default CDS. Tổng RSS khác biệt theo W MiB nhưng có thể đếm trang shared nhiều lần. Không đưa ra kết luận về steady throughput vì chưa có thí nghiệm tải ổn định.”

Không điền X/Y/Z/W nếu chưa đo được; không dùng số từ **Java lab giả lập** làm benchmark sản phẩm.

### 10.2. Khi nào kết luận AppCDS thực sự có ích?

Giá trị phụ thuộc hệ thống:
- **CLI và job ngắn:** vài trăm mili-giây giảm khi startup có thể chiếm phần lớn thời gian end-to-end.
- **Serverless/scale-to-zero:** giảm cold start có thể giảm latency request đầu và chi phí scale-out.
- **Microservice có nhiều replica:** memory sharing có thể giảm footprint trên node và giúp tăng mật độ triển khai.
- **Service sống nhiều ngày:** startup được amortize, nhưng footprint nhiều JVM vẫn có thể đáng giá.
- **Batch có throughput CPU-bound:** nếu thời gian xử lý sau warmup chiếm gần hết thì startup cải thiện có thể ít ảnh hưởng tổng thời gian.

**Không hứa tăng peak requests/second** chỉ dựa trên CDS. Để khẳng định throughput/latency cần load test riêng, cùng dataset, concurrency, GC và CPU quota.

### 10.3. Chi phí vận hành archive cũng cần tính

Ứng dụng có thể phải:
- chạy training để tạo archive;
- lưu file `.jsa` hoặc cache AOT;
- tái tạo khi JDK, classpath và application version thay đổi;
- bảo đảm archive có nguồn gốc đáng tin cậy;
- kiểm tra archive được nạp ở mỗi deployment;
- xử lý rollback/fallback nếu archive không tương thích.

Đặc biệt với **một ứng dụng rất nhỏ**, công sức duy trì archive có thể lớn hơn lợi ích startup/memory đo được. Quyết định dựa trên dữ liệu và SLO, không chỉ vì feature có sẵn.

## 11. JDK 24/25 và AOT cache: ghi đúng công nghệ được đo

JDK 24/25 bổ sung các cải thiện **Ahead-of-Time (AOT) cache** bên cạnh CDS/AppCDS:
- **JDK 24 / JEP 483:** Ahead-of-Time Class Loading & Linking.
- **JDK 25 / JEP 514:** đơn giản hóa lệnh tạo AOT cache.
- **JDK 25 / JEP 515:** Ahead-of-Time Method Profiling.

Các cơ chế AOT mới có thể lưu **nhiều loại công việc trước startup** hơn archive class dữ liệu truyền thống, và có thể cải thiện warmup. Không thể đo bằng việc đổi JDK 21 default CDS → JDK 25 AOT cache rồi quy toàn bộ chênh lệch cho **AppCDS Java 10**.

Nếu mục tiêu là so AppCDS riêng:
1. Giữ **cùng một JDK**.
2. Thay **chỉ** trạng thái application archive.
3. Xác minh archive chấp nhận.
4. Đo startup và PSS nhóm JVM theo cùng điều kiện.

Nếu mục tiêu là tối ưu cả CDS/AOT trên JDK 25:
- Nêu rõ AOT cache và các flags theo tài liệu JDK cụ thể;
- báo separate trial cho cải thiện startup/warmup;
- không gọi mọi lợi ích là tác động duy nhất của JEP 310.

## 12. Những lỗi vận hành hay gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Đo mỗi một JVM rồi suy ra tiết kiệm RAM cho 10 JVM | Sharing thay đổi theo số tiến trình và tập lớp | Test đúng số replica |
| Cộng RSS và gọi đó là physical memory tổng | Shared pages bị tính nhiều lần | Dùng PSS, private và host/cgroup metrics |
| Đọc `/proc/PID/status` rồi gọi VmRSS là PSS | `VmRSS` là resident, không phải proportional share | Dùng `smaps_rollup` khi có quyền |
| Coi reserved heap = resident RAM | Reserved/committed/resident khác nhau | Chọn chỉ số đúng |
| Chỉ đọc NMT rồi kết luận toàn bộ CDS memory | NMT không đầy đủ cho CDS archive | OS-level PSS và xác nhận maps/archive |
| Bật NMT ở B nhưng không bật ở A | Tạo sai khác overhead | Dùng đối chứng ngang hoặc chẩn đoán riêng |
| Bỏ qua default CDS trong baseline | Đo sai phần lợi ích bổ sung của AppCDS | So default CDS với custom archive |
| So ứng dụng đã warm với ứng dụng mới start | Trạng thái không tương đương | Đồng bộ snapshot theo readiness/warm-state |
| Đo ở đầu `main` | Bỏ thời gian JVM bootstrap | Timer ngoài process |
| Bắt đầu N JVM lần lượt nhưng báo all-ready như concurrent | Thời gian group chứa scheduling khác | Ghi kịch bản spawn |
| Không ghi số JVM failed/timeout | Kết quả chỉ từ các sample thành công bị thiên lệch | Báo mọi trial |
| Không xác nhận archive được nạp | Candidate thực tế có thể fallback | Diagnostic `-Xlog:cds=info` |
| Training tải không đủ class | Archive chưa đại diện ứng dụng | Chạy đường khởi động và tải tiêu biểu |
| Chỉ benchmark một vòng | OS cache/CPU noise tác động mạnh | Lặp, đảo A/B, báo phân phối |
| Đổi JDK/GC/heap/CPU quota cùng lúc | Không cô lập nguyên nhân | Thay một biến trong thử nghiệm |
| Kết luận tăng steady throughput từ startup giảm | Khác định nghĩa | Benchmark throughput riêng |
| Coi số MiB từ `smaps` là MB thập phân | Hệ đơn vị có thể lệch 1000/1024 | Báo đúng KiB/MiB |
| Cho rằng mọi OS có `smaps_rollup` | Linux-specific, quyền có thể hạn chế | Công cụ OS tương ứng và ghi phạm vi |
| Nhiều JVM cùng node có nghĩa PSS nhóm bao trọn RAM node | Có process ngoài nhóm/cgroup/page cache | Báo ranh giới đo và số liệu bổ sung |
| Không tái tạo archive sau cập nhật JDK | Có thể bị từ chối hoặc không còn tương thích | Regenerate và verify |
| Có file `app.jsa` nên tin đã dùng | File tồn tại không chứng minh JVM đã nạp | Kiểm tra log và class loading |

## 13. Bài tập có đáp án

### Bài 1 — Ý nghĩa của AppCDS

**Hỏi:** AppCDS từ Java 10 chủ yếu giảm startup/memory hay tăng throughput steady-state?

**Đáp án:** Chủ yếu giảm một phần chi phí class loading/startup và footprint metadata khi nhiều JVM dùng chung archive. Không mặc nhiên tăng throughput steady-state; muốn xác nhận RPS phải benchmark riêng.

### Bài 2 — Tổng RSS của bốn JVM

Bốn JVM mỗi JVM có 100 MiB private resident, cùng chia sẻ 80 MiB resident. Hỏi tổng RSS và tổng PSS của nhóm?

**Đáp án:** Mỗi RSS = 180 MiB, tổng RSS = 720 MiB. Mỗi PSS = 100 + 80/4 = 120 MiB, tổng PSS = 480 MiB (giả định trang shared chỉ thuộc bốn JVM này).

### Bài 3 — Group readiness

Ba JVM có `t_launch` lần lượt 0, 20, 40 ms và `t_ready` lần lượt 700, 650, 900 ms. `T_group` là bao nhiêu?

**Đáp án:** `max(700,650,900)−min(0,20,40)=900 ms`. Cần tách nó khỏi median `T_i` vì các JVM bắt đầu ở thời điểm khác nhau.

### Bài 4 — Per-process startup

Với dữ liệu bài 3, thời gian startup từng JVM bằng bao nhiêu?

**Đáp án:** `700−0=700 ms`, `650−20=630 ms`, `900−40=860 ms`. Median là `700 ms`; group all-ready là `900 ms`.

### Bài 5 — Baseline CDS

Tại sao so `-Xshare:off` với `-XX:SharedArchiveFile=app.jsa` không cô lập lợi ích riêng AppCDS?

**Đáp án:** `-Xshare:off` tắt cả CDS mặc định. Candidate dùng application archive và có thể hưởng dữ liệu nền tảng. Phải so **default CDS** với **default CDS + app archive** để quan sát phần bổ sung.

### Bài 6 — Ý nghĩa của PSS

Hai JVM cùng map một trang 4 KiB và không có tiến trình khác dùng trang này. Trang đó đóng góp bao nhiêu PSS cho mỗi JVM?

**Đáp án:** Mỗi JVM có 2 KiB PSS cho trang ấy; hai JVM cộng lại 4 KiB. RSS của mỗi JVM có thể tính đủ 4 KiB cho cùng trang, nên cộng RSS ra 8 KiB.

### Bài 7 — USS

Có thể lấy PSS làm chính xác “private memory” của một JVM không?

**Đáp án:** Không. PSS gồm private resident **và phần tỷ lệ shared**. USS/private resident thường được ước lượng qua `Private_Clean + Private_Dirty` ở Linux; xác nhận cách diễn giải theo kernel/tool.

### Bài 8 — NMT và CDS

`jcmd VM.native_memory summary` có thay phép đo tổng bộ nhớ CDS của nhiều JVM không?

**Đáp án:** Không. NMT không cung cấp đầy đủ thông tin CDS archive; nó còn có overhead nếu bật. Dùng PSS/RSS/private OS-level cho footprint toàn nhóm và NMT bổ trợ phân tích JVM internals.

### Bài 9 — Time-to-ready

Vì sao `System.nanoTime()` ở `main` không phải startup wall time toàn tiến trình?

**Đáp án:** Nó bắt đầu sau một phần quá trình khởi tạo JVM. Dùng đồng hồ monotonic ngoài process từ mốc spawn tới READY, hoặc cơ chế tracing đồng bộ tương đương.

### Bài 10 — Snapshot memory

Baseline được đo 5 phút sau READY còn candidate được đo ngay tại READY. Có nên kết luận candidate sử dụng ít memory hơn?

**Đáp án:** Chưa. Hai ứng dụng ở trạng thái khác nhau, có thể khác cache/heap/threads. Chụp cùng mốc trạng thái, tốt nhất cả memory at READY và after warmup, rồi so.

### Bài 11 — Archive tồn tại nhưng không nạp được

File `app.jsa` có trên disk; JVM báo mismatch và fallback. Có coi candidate là phép thử AppCDS hợp lệ không?

**Đáp án:** Không. Phải xác minh archive đã thực sự dùng bằng log, class loading/diagnostic và smoke test. Nếu không dùng được, kết luận về candidate vô nghĩa.

### Bài 12 — Nhiều process bên ngoài nhóm

Một trang shared của một JVM benchmark còn được hai JVM không thuộc thử nghiệm sử dụng. Tổng PSS của riêng nhóm thử nghiệm có tính toàn bộ trang không?

**Đáp án:** Không. PSS chia chi phí giữa **tất cả** tiến trình đang share, kể cả ngoài nhóm. Báo ranh giới đo hoặc cách ly workload để giảm sai lệch.

### Bài 13 — Tạo archive có nên tính vào startup?

Nếu archive được tạo **một lần ở build pipeline**, có nên cộng thời gian training vào **mỗi** production startup?

**Đáp án:** Không. Báo training/build overhead riêng; đo startup production với archive đã tồn tại. Nếu hệ thống tạo archive trong mỗi lần chạy, cách tính tổng chi phí sẽ khác.

### Bài 14 — Đọc số liệu giả lập Java

Lab có median startup baseline 1240 ms, AppCDS 905 ms. Tỷ lệ giảm là bao nhiêu?

**Đáp án:** `(1240−905)/1240×100≈27,0%`. Đây là số liệu giả định để luyện tính, không phải mức giảm chuẩn của AppCDS trên JDK 25.

### Bài 15 — Tổng PSS của nhóm

Bốn JVM baseline mỗi JVM 150 MiB PSS, candidate 136 MiB. Nhóm tiết kiệm bao nhiêu MiB và bao nhiêu %?

**Đáp án:** Baseline 600 MiB, candidate 544 MiB; tiết kiệm 56 MiB, khoảng 9,3% tổng PSS của baseline.

### Bài 16 — Thay đổi CPU quota

Baseline chạy trong 1 CPU quota, candidate 4 CPU quota. Candidate READY nhanh hơn 40%. Có thể quy toàn bộ cho AppCDS không?

**Đáp án:** Không. CPU quota thay đổi, nên phải thử lại cùng CPU quota và điều kiện khác để xem phần thực sự liên quan archive.

### Bài 17 — Chỉ số steady-state

AppCDS giúp 4 JVM READY sớm hơn, nhưng sau 10 phút warmup cả hai cấu hình đều xử lý 1000 RPS. Điều gì đã được cải thiện?

**Đáp án:** Startup/time-to-ready và có thể số request sớm trong cửa sổ cold start; **không** có dữ liệu chứng minh peak/steady RPS tăng. Cần kết luận theo metric.

### Bài 18 — Quyền đọc `smaps_rollup`

Harness báo `PermissionError` khi mở `/proc/PID/smaps_rollup`. Có thể thay bằng 0 MiB để hoàn thành báo cáo không?

**Đáp án:** Không. Đây là dữ liệu thiếu do quyền truy cập, không phải bộ nhớ bằng 0. Cần cấp quyền hợp lệ, dùng công cụ được phép hoặc báo phép đo memory không thực hiện được.

## 14. Checklist trước khi chốt hiệu năng AppCDS

- [ ] Xác định phiên bản JDK hiện đại đang được hỗ trợ, đúng HotSpot flags và application artifact.
- [ ] Biết AppCDS được bổ sung trong Java 10; CDS mặc định có thể đã hoạt động trên JDK mới.
- [ ] Đặt baseline default CDS, candidate cùng cấu hình + archive ứng dụng.
- [ ] Chạy một pha diagnosis để chứng minh app archive được nạp.
- [ ] Định nghĩa READY theo ứng dụng chứ không chỉ `main`.
- [ ] Đo từng JVM bằng monotonic timer ngoài tiến trình.
- [ ] Báo median/max per-JVM startup và group all-ready riêng.
- [ ] Chạy đúng số replica và chiến lược spawn của production.
- [ ] Có nhiều trial, có thứ tự A/B xen kẽ, cùng điều kiện CPU/memory.
- [ ] Báo startup failures/timeouts, không chỉ những lần thành công.
- [ ] Đọc `smaps_rollup` khi Linux cho phép; không gọi RSS là PSS.
- [ ] Báo aggregate RSS, aggregate PSS và private resident với đơn vị MiB.
- [ ] Hiểu shared pages có thể được tính nhiều lần trong RSS.
- [ ] Ghi rõ thời điểm chụp memory, snapshots vs peak, warmup state.
- [ ] Biết PSS nhóm bị ảnh hưởng nếu có tiến trình ngoài nhóm cùng share pages.
- [ ] Không dùng NMT làm phép đo đầy đủ của CDS archive.
- [ ] Nếu bật NMT, kiểm soát overhead và bật đều A/B.
- [ ] Không cộng training/dump cost vào mỗi startup trừ khi deployment thực sự làm vậy.
- [ ] Không quy cải thiện JDK 25 AOT profiling cho AppCDS Java 10 thuần túy.
- [ ] Không mặc định AppCDS làm tăng thông lượng sau warmup.
- [ ] Có quyết định cuối dựa trên SLO: startup, cold latency, memory density và chi phí vận hành.
- [ ] Chạy `MultiJvmAppCdsMetricsLab.java` để kiểm tra **22 dòng stdout giả lập**, sau đó mới đọc số đo thật với harness Linux.

## 15. Kết luận

**Với AppCDS, phải đo ít nhất hai nhóm độc lập: thời gian từ spawn tới READY của từng JVM/nhóm JVM và bộ nhớ của nhiều JVM khi cùng chạy.** AppCDS có thể giúp load class nhanh hơn và tạo shared archive mappings, nhưng **RSS cộng dồn có thể đếm trùng**; trên Linux, tổng PSS và các chỉ số private thường phù hợp hơn để khảo sát footprint của một nhóm tiến trình.

Thử nghiệm có giá trị phải so **default CDS** với **AppCDS** trên cùng JDK và workload, xác nhận archive thực sự được dùng, đo nhiều lần với đồng hồ monotonic, ghi rõ thời điểm chụp `smaps_rollup` và mọi giới hạn về OS/process sharing/cgroup. **Không tự suy ra thông lượng steady-state tăng** từ startup hoặc PSS tốt hơn. Đây là cách tiếp cận còn áp dụng trên các JDK hiện đại dù các cơ chế CDS/AOT tiếp tục được cải tiến.

## 16. Tài liệu tham khảo chính thức

- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): mục tiêu giảm startup và memory footprint, chia sẻ metadata của lớp ứng dụng từ Java 10.
- [Oracle Java SE 25 VM Guide — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): default CDS, memory-mapped archive, nhiều JVM dùng chung metadata, `-Xshare:off` và `-Xshare:on`.
- [Oracle Java SE 25 — The java Command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#application-class-data-sharing): `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile`, dynamic archive, tùy chọn log.
- [Oracle Java SE 25 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): `-XX:NativeMemoryTracking`, `jcmd VM.native_memory`, chi phí tracking và giới hạn đối với CDS archive.
- [Linux Kernel Documentation — The /proc Filesystem](https://docs.kernel.org/filesystems/proc.html): `/proc/PID/smaps`, `smaps_rollup`, PSS/RSS, shared/private và ý nghĩa các trường thống kê.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): JDK 24 AOT class loading và linking.
- [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): JDK 25 tạo cache thuận tiện hơn.
- [OpenJDK JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): JDK 25 lưu method profiles trong AOT cache, hữu ích cho warmup.