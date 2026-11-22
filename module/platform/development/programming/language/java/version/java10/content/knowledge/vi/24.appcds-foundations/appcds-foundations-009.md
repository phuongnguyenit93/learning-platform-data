# Phân biệt giảm chi phí khởi động với tối ưu thông lượng sau khởi động khi dùng AppCDS

> **Java 10 — Nền tảng AppCDS.** Application Class-Data Sharing (**AppCDS**, JEP 310) giúp JVM sử dụng lại dạng dữ liệu lớp đã xử lý và có thể chia sẻ một phần metadata giữa nhiều tiến trình. **Mục tiêu trực tiếp là giảm công việc tải lớp, thời gian khởi động và memory footprint; không có bảo đảm tự động rằng tốc độ xử lý request/giây khi ứng dụng đã warm up sẽ tăng.** Bài này hướng dẫn tách **startup**, **warmup**, **steady-state throughput**, **latency** và **memory sharing**, thiết kế phép đo có đối chứng và đánh giá trên JDK hiện đại. Không dùng hướng dẫn chỉ áp dụng cho JDK 10 đã cũ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `CDS` và `AppCDS`, cơ chế archive chứa dữ liệu lớp, mục tiêu khởi động và chia sẻ bộ nhớ.
2. Phân biệt rõ ba đại lượng dễ bị nhầm: **time to ready**, **time to peak performance** và **steady-state throughput**.
3. Chỉ ra vì sao giảm thời gian class loading không đồng nghĩa cải thiện tốc độ code đã được JIT tối ưu.
4. Biết một ứng dụng khởi động nhanh hơn có thể hoàn tất **nhiều tác vụ hơn trong một cửa sổ ngắn** dù thông lượng ổn định không đổi.
5. Tổ chức so sánh A/B giữa **CDS mặc định** và **AppCDS archive của ứng dụng**, không vô tình thay đổi cả JDK, heap, garbage collector hoặc workload.
6. Dùng các tùy chọn HotSpot còn được tài liệu hóa, chẳng hạn `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile`, `-Xshare:off` và `-Xlog:cds=info`, đúng mục đích.
7. Hiểu sự khác biệt giữa **AppCDS truyền thống** và các khả năng **Ahead-of-Time cache trên JDK 24/25**, tránh suy diễn tác động warmup/JIT của một công nghệ sang công nghệ khác.
8. Đọc đúng RSS, PSS, USS hoặc shared mappings khi khảo sát memory footprint, nhất là khi chạy nhiều JVM.
9. Viết báo cáo benchmark với đơn vị, điều kiện và giới hạn đo lường rõ ràng.
10. Chạy một chương trình Java độc lập có **16 dòng stdout xác định** để kiểm tra phép tính và phân biệt tác động khởi động với thông lượng.

## 2. Tóm tắt trọng tâm trước khi đi sâu

| Câu hỏi | AppCDS thường nhắm đến điều gì? | Không được mặc định kết luận |
| --- | --- | --- |
| JVM mất bao lâu để khởi động ứng dụng? | Có thể giảm thời gian xử lý/tải nhiều lớp đã archive | Mọi ứng dụng đều nhanh hơn cùng một tỷ lệ |
| Bao lâu ứng dụng nhận được request đầu tiên? | Có thể giảm một phần thời gian trước khi sẵn sàng | Toàn bộ thời gian init, DB connection và network đều được loại bỏ |
| Bao lâu đạt hiệu năng tối đa sau khi nhận tải? | Có thể ảnh hưởng gián tiếp phần class loading/warmup | Mọi mã nóng đã được JIT tối ưu trước |
| Sau 30 phút ổn định, mỗi giây xử lý bao nhiêu request? | **Không phải mục tiêu trực tiếp** của việc archive class metadata | QPS tăng tương ứng với tỷ lệ giảm startup |
| Nhiều JVM giống nhau cần bao nhiêu bộ nhớ? | Các trang metadata chỉ đọc có thể được memory-map/chia sẻ | Tổng RSS của các tiến trình bằng đúng RAM vật lý sử dụng |
| Một đợt batch chạy vài giây hoàn thành bao nhiêu tác vụ? | Có thể có lợi do mất ít thời gian khởi tạo | Throughput steady-state đã tăng |
| Có cần tối ưu GC/JIT/SQL và mạng nữa không? | Có: AppCDS không thay mọi khâu tối ưu | AppCDS có thể sửa toàn bộ bottleneck runtime |

**Quy tắc nhớ:** “**Khởi động nhanh**” đo một **thời điểm hoặc khoảng thời gian trước khi nhận tải đầy đủ**; “**Thông lượng cao**” đo **số đơn vị công việc thành công trên một khoảng thời gian đang xử lý tải**. Hai câu hỏi khác nhau, không thể lấy một số thay cho số kia.

## 3. AppCDS là gì trong bối cảnh Java 10 và JDK hiện đại?

### 3.1. Từ CDS đến AppCDS

**Class Data Sharing (CDS)** là tính năng HotSpot giúp chuẩn bị dữ liệu các lớp dưới dạng **shared archive**. Khi khởi động, JVM có thể memory-map những phần phù hợp của archive, tiết kiệm việc lặp lại một số công đoạn xử lý metadata của class so với đi từ lớp đóng gói ban đầu. Vùng metadata chỉ đọc cũng có thể được **chia sẻ ở mức trang bộ nhớ** giữa nhiều tiến trình JVM dùng archive tương thích.

**Application Class-Data Sharing (AppCDS)** mở rộng ý tưởng đó tới **các lớp ứng dụng** ngoài lớp nền tảng. **JEP 310** đưa AppCDS vào Java 10 để giúp quá trình khởi động ứng dụng và bộ nhớ của nhiều JVM tốt hơn.

Một đường đi khái niệm:

```text
Không có archive ứng dụng:
JVM start
  -> tìm class trên classpath/module path
  -> đọc dữ liệu class/JAR
  -> parse/xử lý metadata cần thiết
  -> link/initialize theo nhu cầu
  -> khởi tạo framework và dịch vụ
  -> READY
  -> ứng dụng nhận tải và JIT/GC tiếp tục hoạt động


Với archive phù hợp:
JVM start
  -> truy cập dạng lớp đã lưu trong shared archive
  -> bớt một phần công việc chuẩn bị/tải lớp
  -> link/initialize phần vẫn cần làm
  -> khởi tạo framework và dịch vụ
  -> READY sớm hơn nếu các chi phí còn lại không chi phối
  -> ứng dụng nhận tải và JIT/GC tiếp tục hoạt động
```

Sơ đồ chỉ là **mô hình khái niệm**, không phải danh sách từng bước JVM bắt buộc theo đúng thứ tự ở mọi bản JDK. Từng class có thể được tải khác thời điểm và archive có thể không chứa hoặc không dùng được một số class.

### 3.2. Cơ chế có giới hạn: archive không thay toàn bộ startup

Ví dụ một service có thời gian trước READY gồm:

| Thành phần thời gian | Không có application archive | Với application archive | Có phải AppCDS trực tiếp kiểm soát toàn bộ? |
| --- | ---: | ---: | --- |
| Bắt đầu JVM, xử lý/tải lớp | Có | Có thể giảm | Chỉ một phần; tùy archive và VM |
| Tạo đối tượng, dependency injection | Có | Có | Không |
| Chạy static initializers và logic ứng dụng | Có | Có, trừ tối ưu khác của JDK | Không tự biến mọi initializer thành archive data |
| Đọc config/tệp/secrets | Có | Có | Không |
| Kết nối DB/cache/dịch vụ khác | Có | Có | Không |
| Xây index, warm cache nghiệp vụ | Có | Có | Không |
| Khởi động server và readiness | Có | Có | Không |
| Biên dịch JIT tối ưu các hot methods | Có trong quá trình chạy | Vẫn là nhiệm vụ của runtime/JIT nếu chỉ dùng AppCDS truyền thống | Không tự tương đương AOT compiled code |

Nếu thời gian mở kết nối database chiếm phần lớn startup, giảm công việc class loading có thể chỉ tiết kiệm một phần nhỏ trong tổng thời gian. Vì vậy **tỷ lệ lợi ích tùy workload**, không có con số “AppCDS luôn giảm x%”.

### 3.3. Chức năng đang có trên JDK hiện đại

Theo tài liệu **Oracle Java SE 25**, CDS được bật mặc định trong điều kiện tương thích; Oracle JDK từ JDK 12 có archive CDS mặc định được đóng gói. AppCDS vẫn được mô tả trong `java` launcher và JVM guide; các cơ chế tạo **dynamic CDS archive** qua `-XX:ArchiveClassesAtExit` và dùng archive qua `-XX:SharedArchiveFile` vẫn có tài liệu.

Do vậy:
- Không dùng bài thực hành dựa vào yêu cầu license/tham số chỉ còn đúng ở giai đoạn Java 10.
- Không khuyên luôn phải tạo archive chứa toàn bộ JDK base classes trước khi chạy một ứng dụng.
- Nếu không cấu hình application archive, JVM **vẫn có thể sử dụng CDS archive mặc định**; đừng gọi đó là “CDS hoàn toàn tắt”.
- Với bản JDK mới, công nghệ **AOT cache (Project Leyden)** đã bổ sung khả năng ngoài archive class truyền thống; phải nêu rõ đang đánh giá công nghệ/flag nào.

## 4. Bốn giai đoạn hiệu năng phải tách riêng

### 4.1. Khởi động JVM và ứng dụng (startup)

Khái niệm:
- **Process launch → main:** từ khi hệ điều hành bắt đầu tiến trình JVM đến khi `main` thực thi. Đo thời gian này bằng đồng hồ **bên ngoài tiến trình**, không thể đo đủ chỉ với `System.nanoTime()` đặt bên trong `main`.
- **Process launch → application ready:** từ khi khởi tạo tiến trình cho tới khi ứng dụng có thể phục vụ tác vụ hữu ích theo hợp đồng, ví dụ health/readiness endpoint sẵn sàng, listener hoạt động và các dependency bắt buộc đã OK.
- **Time to first successful request:** từ lúc launch cho tới phản hồi thành công đầu tiên theo một kịch bản xác định. Có thể khác READY nếu request còn kích hoạt lazy initialization.

AppCDS thường có cơ hội giúp khi phần **nạp/xử lý class** đáng kể trong các giai đoạn đó. Không chỉ nhìn dòng log “started” của framework rồi bỏ qua việc service thực sự chưa đủ điều kiện tiếp nhận tải.

**Mẫu định nghĩa tốt:** “cold start time = wall-clock từ khi spawn tiến trình đến khi readiness HTTP trả 200 và truy vấn nghiệp vụ kiểm tra kết nối cache/DB thành công”.

### 4.2. Warmup (từ READY tới lúc ổn định)

JVM có thể bắt đầu phục vụ request khi một số method vẫn chạy trong interpreter hoặc compiled code chưa đạt tối ưu cuối. Profile từ workload giúp JIT biên dịch method nóng, inline những lời gọi có lợi, và thực hiện các tối ưu khác theo điều kiện runtime. Đồng thời:
- Framework có thể lazy-load class còn lại.
- Kết nối pool được tạo và sử dụng.
- Bộ nhớ/cache nghiệp vụ dần nóng lên.
- Garbage collector ổn định với pattern allocation.

**Time to peak throughput** là thời gian để ứng dụng đạt và giữ gần mức thông lượng ổn định theo một định nghĩa phép đo. Đừng đồng nhất nó với **time to ready**.

AppCDS truyền thống không phải một lệnh “đã JIT toàn bộ method”. Tuy vậy, khi giảm chi phí tải lớp trong các đợt đầu, nó **có thể làm các quan sát warmup thay đổi gián tiếp**. Phải đo, không mặc định warmup không thay đổi hoặc chắc chắn tăng.

### 4.3. Steady-state throughput (thông lượng ổn định)

Thông lượng thường được đo:

\[
\mathrm{Throughput}=\frac{\text{số tác vụ thành công}}{\text{số giây quan sát}}
\]

Ví dụ:
- **HTTP service:** requests/second thành công (RPS/QPS), kèm mã lỗi và giới hạn concurrency.
- **Message processor:** messages/second xử lý và ACK thành công.
- **Batch compute:** items/second sau warmup, theo định nghĩa một item.
- **Tác vụ CPU:** operations/second với workload được kiểm soát.

Đo thông lượng sau khi warmup đủ, dưới cùng tải đầu vào, độ đồng thời, dataset và giới hạn tài nguyên. Một phép đo thu được **nhiều request hơn trong khoảng 5 giây tính từ lúc launch** không tự chứng minh **steady RPS tăng**: thời gian sẵn sàng phục vụ có thể là nguyên nhân.

Yếu tố thường chi phối steady-state throughput:
- Thuật toán và độ phức tạp xử lý.
- JIT optimization, compiler/code cache.
- GC, allocation rate, heap và memory locality.
- CPU quota, CPU throttling, contention.
- Database/query plan, connection pool, cache.
- Network, disk I/O, backpressure và độ đồng thời của client.
- Batching, synchronization/lock contention và hệ thống bên ngoài.

CDS lưu class metadata, **không tự sửa thuật toán chậm hay truy vấn SQL thiếu index**.

### 4.4. Latency và tail latency

Một hệ thống có thể có thông lượng giống nhau nhưng:
- First-request latency tốt hơn.
- P50/P95/P99 ở steady state khác nhau.
- Số lần timeout hoặc retry khác nhau.
- CPU/heap/memory footprint khác nhau.

**QPS không thay thế latency.** Tại cùng offered load, một cấu hình có thể giảm p99 do không còn một số work khởi tạo ở thời điểm đầu mà không đổi thông lượng peak. Ngược lại, cấu hình có QPS cao hơn vẫn có tail latency xấu ở mức tải bão hòa.

Báo cáo nên tách:
- cold p50/p95/p99 của startup (qua nhiều launches),
- first-request latency,
- warmup duration,
- steady throughput,
- steady p50/p95/p99 latency,
- error rate,
- CPU/memory.

Không trộn percentile của cold requests với percentile sau warmup rồi trình bày như một chỉ số latency chung.

## 5. Ví dụ định lượng: khởi động nhanh hơn nhưng thông lượng **không đổi**

Giả sử có hai cấu hình chạy cùng một ứng dụng, trên cùng máy:

| Chỉ số giả định | Baseline: CDS mặc định | AppCDS application archive |
| --- | ---: | ---: |
| Thời gian launch → READY | 1.200 ms | 780 ms |
| Thông lượng sau warmup | 1.000 request/giây | 1.000 request/giây |
| P95 latency sau warmup | 20 ms | 20 ms |
| Thời gian một cửa sổ đếm từ lúc launch | 5.000 ms | 5.000 ms |
| Khoảng thời gian còn nhận request trong cửa sổ | 3.800 ms | 4.220 ms |
| Số request tối đa theo mô hình lý tưởng | 3.800 | 4.220 |

**Đây là số liệu minh họa, không phải benchmark AppCDS thực tế.** Mô hình giả định tải sẵn sàng ngay từ lúc app READY, năng lực steady-state đạt ngay lập tức và không có lỗi, queue, warmup hay thay đổi công suất trong khoảng quan sát.

### 5.1. Mức giảm thời gian startup

\[
\mathrm{StartupReduction} =
\frac{1200-780}{1200}\times 100\%=35\%
\]

Tức ứng dụng **sẵn sàng sớm hơn 420 ms**, tương đương giảm **35% thời gian khởi động**.

### 5.2. Mức thay đổi throughput steady state

\[
\mathrm{SteadyQpsChange} =
\frac{1000-1000}{1000}\times100\%=0\%
\]

Tốc độ xử lý ổn định **không đổi**. AppCDS có ích cho startup trong ví dụ nhưng **không làm một request CPU-bound chạy nhanh hơn** trong steady state.

### 5.3. Vì sao lại có thêm 420 request trong 5 giây đầu?

Với baseline:
- Cửa sổ 5.000 ms.
- 1.200 ms đầu ứng dụng chưa READY.
- Còn 3.800 ms × 1.000 request/s = **3.800 request**.

Với archive:
- Chỉ mất 780 ms trước READY.
- Còn 4.220 ms × 1.000 request/s = **4.220 request**.

Số request hơn là **420**, tức hơn khoảng **11,1%** trong **cửa sổ tính từ lúc launch**. Nhưng **steady throughput vẫn 1.000 request/s**.

Chính xác hơn, đây là **năng lực phục vụ tích lũy từ thời điểm khởi động**, không phải mức tăng tốc độ xử lý ổn định. Khi bài toán là lambda-like short-lived job, batch nhỏ, CI task hoặc server scale-to-zero, lợi ích tổng thời gian có thể đáng kể. Khi một service chạy nhiều tuần, chi phí startup được phân bổ trên thời gian dài và tốc độ ổn định có thể quan trọng hơn.

### 5.4. Một bảng báo cáo trung thực phải dùng đúng tên đại lượng

**Không nên viết:** “AppCDS tăng throughput 11,1%”.

**Nên viết:** “Với mô hình thời gian 5 giây kể từ launch, số tác vụ hoàn tất tăng 11,1% nhờ READY sớm hơn 420 ms; throughput sau warmup không đổi, 1.000 req/s”.

Nếu benchmark thực tế có warmup và queue, cần báo thêm các giả định: một lần launch không đủ để suy ra phân phối, và **tỷ lệ % phụ thuộc cửa sổ đo**. Trong 60 phút chạy ổn định, khác biệt 420 ms đóng góp rất ít vào tổng số request nếu steady QPS thực sự bằng nhau.

## 6. Chương trình Java 17+ minh họa phép tính, có thể chạy độc lập

Bài lab này **không giả vờ tự kích hoạt AppCDS**. Nó kiểm tra logic đọc chỉ số của hai cấu hình bằng một bộ dữ liệu **giả định rõ ràng**, tránh in các con số benchmark tình cờ từ một JVM. Các phép đo thật và cờ AppCDS nằm ở phần 7–9.

### 6.1. Lưu file và biên dịch

Dùng JDK 17+ còn được hỗ trợ (chẳng hạn JDK 21/25 theo chính sách tổ chức). Tạo file **`AppCdsPhasesLab.java`**:

```java
import java.util.Locale;

public class AppCdsPhasesLab {
    record Measurements(
            long readyMs,
            long steadyQps,
            long steadyP95Ms) {
    }

    static double reductionPercent(long before, long after) {
        if (before <= 0 || after < 0) {
            throw new IllegalArgumentException(
                    "invalid measurements");
        }
        return (before - after) * 100.0 / before;
    }

    static long completedRequestsInWindow(
            long windowMs, Measurements m) {
        if (windowMs < 0 || m.readyMs() < 0
                || m.steadyQps() < 0) {
            throw new IllegalArgumentException(
                    "invalid inputs");
        }

        long operatingMs = Math.max(0, windowMs - m.readyMs());
        return (operatingMs * m.steadyQps()) / 1_000L;
    }

    public static void main(String[] args) {
        // DỮ LIỆU GIẢ ĐỊNH minh họa, không phải kết quả đo.
        Measurements baseline =
                new Measurements(1200, 1000, 20);
        Measurements archive =
                new Measurements(780, 1000, 20);

        long windowMs = 5000;
        long before =
                completedRequestsInWindow(windowMs, baseline);
        long after =
                completedRequestsInWindow(windowMs, archive);

        System.out.println(
                "startup baseline ms: " + baseline.readyMs());
        System.out.println(
                "startup archive ms: " + archive.readyMs());
        System.out.printf(Locale.ROOT,
                "startup reduction percent: %.1f%n",
                reductionPercent(
                        baseline.readyMs(), archive.readyMs()));

        System.out.println(
                "steady baseline qps: " + baseline.steadyQps());
        System.out.println(
                "steady archive qps: " + archive.steadyQps());
        System.out.printf(Locale.ROOT,
                "steady qps change percent: %.1f%n",
                (archive.steadyQps() - baseline.steadyQps())
                        * 100.0 / baseline.steadyQps());

        System.out.println("steady baseline p95 ms: "
                + baseline.steadyP95Ms());
        System.out.println("steady archive p95 ms: "
                + archive.steadyP95Ms());

        System.out.println("fixed window ms: " + windowMs);
        System.out.println("fixed window baseline requests: "
                + before);
        System.out.println("fixed window archive requests: "
                + after);
        System.out.printf(Locale.ROOT,
                "fixed window gain percent: %.1f%n",
                -reductionPercent(before, after));

        System.out.println("steady throughput unchanged: "
                + (baseline.steadyQps() == archive.steadyQps()));
        System.out.println(
                "cold window improves despite same steady qps: "
                + (after > before
                        && baseline.steadyQps()
                            == archive.steadyQps()));

        try {
            reductionPercent(0, 0);
            System.out.println(
                    "invalid baseline rejected: false");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "invalid baseline rejected: true");
        }

        System.out.println(
                "sample is modeled, not benchmark: true");
    }
}
```

Biên dịch và chạy:

```bash
javac AppCdsPhasesLab.java
java AppCdsPhasesLab
```

### 6.2. Stdout chính xác (16 dòng)

```text
startup baseline ms: 1200
startup archive ms: 780
startup reduction percent: 35.0
steady baseline qps: 1000
steady archive qps: 1000
steady qps change percent: 0.0
steady baseline p95 ms: 20
steady archive p95 ms: 20
fixed window ms: 5000
fixed window baseline requests: 3800
fixed window archive requests: 4220
fixed window gain percent: 11.1
steady throughput unchanged: true
cold window improves despite same steady qps: true
invalid baseline rejected: true
sample is modeled, not benchmark: true
```

Đã thử các kết quả tính toán trên JDK hiện đại, với `Locale.ROOT` để cách in dấu thập phân ổn định. Các số là **fixtures** trong code, không dùng làm khẳng định tốc độ AppCDS thực tế trên máy của người đọc.

### 6.3. Những điều bài lab chứng minh và không chứng minh

**Chứng minh về phép tính:**
- Thời gian từ launch tới READY giảm 35%.
- Steady QPS và P95 giữ nguyên.
- Số request trong cửa sổ giả định từ launch tăng khoảng 11,1% vì có nhiều thời gian để phục vụ.
- Không thể tính phần trăm reduction nếu baseline bằng 0; helper từ chối input đó.

**Không chứng minh về VM:**
- Lab mặc định không tạo archive `.jsa`.
- Nó không đo thời gian class loading trên thiết bị.
- Nó không đo JIT, GC hoặc CPU thật.
- Nó không chứng minh một ứng dụng cụ thể sẽ giảm 35%.
- Nó không loại trừ khả năng AppCDS ảnh hưởng warmup/steady metrics ở những workload thực tế khác.

Để trả lời câu hỏi thực nghiệm, cần benchmark AppCDS thật với baseline công bằng.

## 7. Thiết lập một thí nghiệm AppCDS thực tế trên JDK hiện đại

### 7.1. Xác định baseline đúng

Trên nhiều bản phân phối HotSpot hiện đại, JVM thường chạy với **CDS archive mặc định** trừ khi cấu hình ngăn cản. Do vậy có ít nhất ba trạng thái cần phân biệt:

1. **CDS off:** `-Xshare:off`. Đây là công cụ đối chứng/chẩn đoán để thấy lợi ích của **CDS nói chung**, nhưng không phải baseline tốt nhất để tách riêng tác động của **AppCDS**.
2. **Default CDS:** chạy ứng dụng bình thường, không chỉ định archive ứng dụng; dùng archive có sẵn của runtime khi tương thích.
3. **Application archive:** giữ nguyên runtime/application nhưng nạp thêm archive chứa các class ứng dụng phù hợp.

**Để đo phần lợi ích riêng của AppCDS:** so **2 ↔ 3**. Nếu so **1 ↔ 3**, bạn đo gộp hiệu ứng bật lại CDS core classes và ứng dụng, khiến báo cáo khó xác định phần nào thật sự do AppCDS.

### 7.2. Tạo và dùng dynamic CDS archive

Trên một bản **HotSpot JDK có hỗ trợ các option đang được tài liệu hóa** (chẳng hạn JDK 21 theo tài liệu `java` launcher, và một số cấu hình JDK mới), có thể dùng quy trình mẫu sau. Các lệnh yêu cầu **ứng dụng thật** có `app.jar` trên classpath và class main `com.example.App`; `--train`/`--one-shot` là **tham số ví dụ do ứng dụng tự định nghĩa**, không phải option JVM có sẵn:

```bash
# Bước 1: chạy ứng dụng đủ để tải những class tiêu biểu,
# rồi ứng dụng tự thoát bình thường để archive được ghi.
java -XX:ArchiveClassesAtExit=app.jsa \
     -cp app.jar com.example.App --train

# Bước 2: chạy một lần để CHẨN ĐOÁN archive có được dùng.
java -Xlog:cds=info \
     -XX:SharedArchiveFile=app.jsa \
     -cp app.jar com.example.App --one-shot

# Bước 3: baseline có default CDS, không thêm app archive.
java -cp app.jar com.example.App --one-shot

# Bước 4: candidate có application archive.
java -XX:SharedArchiveFile=app.jsa \
     -cp app.jar com.example.App --one-shot
```

**Lưu ý lệnh nhiều dòng với dấu `\` là cách viết cho shell POSIX**; trong Windows PowerShell hãy viết mỗi lệnh trên **một dòng** hoặc dùng cú pháp nối dòng riêng của PowerShell. Không copy dấu `\` cuối dòng vào PowerShell rồi kỳ vọng nó hoạt động như Bash.

Có thể viết dạng một dòng cross-shell khi các tệp đã tồn tại:

```text
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar com.example.App --train
java -Xlog:cds=info -XX:SharedArchiveFile=app.jsa -cp app.jar com.example.App --one-shot
java -cp app.jar com.example.App --one-shot
java -XX:SharedArchiveFile=app.jsa -cp app.jar com.example.App --one-shot
```

Các lệnh trên là **template tích hợp vào ứng dụng thật**, không phải một phần của chương trình `AppCdsPhasesLab.java`. Phải thay tên main class, args và artifact đúng của dự án. Nếu ứng dụng là fat JAR/nested JAR framework, modular launch hoặc custom class loader, dùng quy trình được framework và HotSpot phiên bản đó hỗ trợ; **không giả định copy một lệnh `-cp app.jar` sẽ archive được mọi class**.

### 7.3. Tránh đo thời gian tạo archive như thời gian startup production

Bước tạo archive là **training/dump**. Nó có thể:
- Nạp thêm class.
- Tiêu thụ CPU/IO/bộ nhớ.
- Tạo tệp archive.
- Phụ thuộc đường dẫn JAR và runtime.

Nếu deployment thực tế **tạo archive ở build time**, thời gian training **không thuộc mỗi lần production startup**. Nếu hệ thống **tạo archive mỗi lần khởi động**, lợi ích amortization và chi phí cần tính riêng. Đừng dùng kết quả chạy training để kết luận candidate trong production khởi động nhanh.

### 7.4. Xác minh archive thực sự được sử dụng

Một phép thử tốt không chỉ kiểm tra “lệnh có flag”:
- Xem thông tin `-Xlog:cds=info` / các tag class load phù hợp phiên bản JVM.
- Xác nhận archive đã được map và các lớp mục tiêu được dùng từ archive khi cần.
- Kiểm tra cảnh báo về classpath, JDK mismatch hoặc archive bị từ chối.
- So sánh số class xuất hiện trong archive với các class được load trong đường chạy tiêu biểu.
- Chạy smoke tests để bảo đảm behavior không khác.

**Không đưa log chẩn đoán rất nhiều dòng vào chính các lần đo thời gian** nếu logging làm tăng I/O và thay đổi baseline. Có một pha verification riêng, rồi tắt hoặc cân bằng logging cho các benchmark chính.

`-Xshare:on` có thể giúp test rằng CDS bắt buộc phải hoạt động, nhưng tài liệu Oracle lưu ý **chỉ dùng cho mục đích kiểm thử, không nên dùng production**: nếu archive không dùng được, JVM có thể dừng startup. Với vận hành thông thường, hãy chọn cấu hình fallback và chính sách lỗi phù hợp phiên bản JDK.

### 7.5. Archive là artifact gắn với ứng dụng và môi trường

Không đưa archive tạo trên JDK/hệ điều hành/kiến trúc khác vào production rồi coi việc tái sử dụng là an toàn. Với nhiều hình thức archive/AOT cache, có điều kiện tương thích về JDK release, app artifact, đường dẫn/classpath, platform và JVM flags.

Một quy trình build/deploy tốt:
- Tạo archive từ đúng ứng dụng và JDK được dùng để triển khai.
- Tự động cập nhật khi thay JAR/library/JDK.
- Lưu checksum và provenance của archive.
- Đặt archive ở vị trí read-only với quyền truy cập phù hợp.
- Có fallback/rollback nếu candidate gây lỗi khởi động.
- Xác minh archive được dùng thực tế, không chỉ được khai báo trên command line.

## 8. Quy trình benchmark để không nhầm startup với steady-state

### 8.1. Định nghĩa câu hỏi trước khi chạy

Ví dụ một mục tiêu hợp lệ:

> “Trên cùng container image, CPU quota và heap, AppCDS có giảm P95 thời gian process launch → HTTP readiness thành công không, khi không làm suy giảm throughput và P99 latency sau 10 phút warmup?”

Câu hỏi này có:
- **Metric chính:** P95 startup.
- **Metric guardrail:** steady RPS và p99 latency.
- **Điều kiện:** cùng image, JDK, CPU/memory, workload và chiến lược warmup.
- **Điểm đo rõ:** readiness endpoint đáp ứng tiêu chuẩn của ứng dụng.

Đừng bắt đầu benchmark với câu “cấu hình nào nhanh hơn?” nhưng không định nghĩa “nhanh” là launch time, full run completion time hay QPS.

### 8.2. Bộ ba run tối thiểu

| Run | JVM options | Vai trò |
| --- | --- | --- |
| A — Normal | Cấu hình chuẩn, default CDS có thể bật | **Baseline thực tế** |
| B — AppCDS | Cùng cấu hình A + archive ứng dụng đã xác thực | **Candidate để đo AppCDS** |
| C — CDS off (tùy chọn) | Cùng app/JDK nhưng `-Xshare:off` | Đối chứng khám phá hiệu ứng CDS rộng hơn, **không thay thế A** |

Không đổi GC, `-Xms`, `-Xmx`, JDK distribution, container CPU limit hoặc classpath ở run B nếu mục tiêu là đo **duy nhất** tác động archive. Nếu những cấu hình đó thay đổi, phải ghi thành một thử nghiệm khác và không quy toàn bộ kết quả cho AppCDS.

### 8.3. Đo startup bằng đồng hồ từ ngoài JVM

Một dạng script shell có thể tạo tiến trình rồi hỏi readiness:

```text
t0 = monotonic clock ngay trước khi spawn process
spawn java <flags> ...
repeat probe readiness với khoảng lấy mẫu có giới hạn
tReady = monotonic clock tại lần đầu readiness thành công
startupDuration = tReady - t0
nếu timeout hoặc process chết -> đánh dấu STARTUP_FAILED
```

Đây là **pseudocode của test harness**, không phải lệnh cần nhập vào Java. Dùng monotonic clock giúp không bị tác động bởi chỉnh giờ hệ thống, còn poll interval cần đủ nhỏ so với khác biệt mục tiêu. Ví dụ nếu chỉ thăm dò mỗi 1 giây thì khó kết luận chắc chắn một thay đổi 100 ms.

Khi service có warm cache hoặc phụ thuộc external DB, bảo đảm các điều kiện phụ thuộc giữa các lần chạy công bằng. “Cold start” của ứng dụng **không nhất thiết** đồng nghĩa OS page cache cũng lạnh: phải công bố trạng thái cache được kiểm soát hay không.

Không dùng mỗi `System.nanoTime()` đầu `main` làm startup end-to-end vì nó **bỏ qua JVM bootstrap và hoạt động trước `main`**. Time-to-ready phải được đo từ bên ngoài hoặc bằng hệ thống tracing phối hợp có mốc launch chuẩn.

### 8.4. Đo warmup riêng

Sau READY, phát sinh tải tiêu biểu:
1. Giữ dataset và request mix cố định.
2. Phát request trong nhiều cửa sổ liên tiếp, chẳng hạn mỗi 1–5 giây.
3. Ghi throughput, CPU, GC, latency, lỗi cho từng cửa sổ.
4. Định nghĩa điều kiện **ổn định** trước, ví dụ 5 cửa sổ liên tiếp nằm trong ±5% thông lượng tham chiếu và không có lỗi.
5. Báo `time-to-stable` từ một mốc rõ (launch hoặc READY).

Quy tắc ±5%/5 cửa sổ chỉ là **chính sách ví dụ của benchmark harness**; không phải đặc điểm AppCDS hoặc định nghĩa kỹ thuật JDK về “warmup done”. Nếu workload có drift, cần dùng cách phát hiện ổn định phù hợp hơn.

### 8.5. Đo steady-state throughput đúng cách

Sau warmup:
- Chạy load generator ở một hoặc nhiều mức offered load đã xác định.
- Ghi **số response thành công** và thời gian đo (giây).
- Ghi concurrency, error/timeout, CPU utilization, GC pauses và DB latency.
- Tách cold requests/lazy initialization khỏi cửa sổ steady.
- So P50/P95/P99 latency tại **cùng offered load** hoặc trên toàn đường cong tải, không chỉ ở một số request ngẫu nhiên.
- Không đẩy load generator tới mức nó tự CPU-bound rồi kết luận server không cải thiện.
- Không đo QPS bằng số request được **gửi** nếu nhiều request bị timeout; đếm request được xử lý thành công.

Nếu throughput baseline/candidate gần nhau hơn độ biến thiên run-to-run, kết luận hợp lý là “**không thấy cải thiện đáng tin cậy** trong điều kiện thử”, không khẳng định “hai bản luôn bằng nhau ở mọi ứng dụng”.

### 8.6. Lặp lại và báo cáo phân phối

Khởi động chịu ảnh hưởng file cache, JIT thread scheduling, CPU throttling, I/O và các dịch vụ bên ngoài. Nên thực hiện **nhiều lần launch** cho mỗi cấu hình, đảo hoặc ngẫu nhiên hóa thứ tự A/B để tránh lợi thế của bản chạy sau.

Báo:
- Số lần lặp `N`.
- Median, p95, min/max nếu phù hợp, khoảng biến thiên và số thất bại.
- Công cụ/harness, thời gian timeout, tần suất poll.
- Build JDK, vendor, OS, CPU quota, memory limit, GC, JVM flags.
- Mức coverage archive, đường chạy dùng khi training.
- Dataset, load generator và concurrency.

**Không** dùng một mẫu duy nhất `900 ms vs 850 ms` làm bằng chứng mạnh cho một cải thiện 5,6% nếu độ nhiễu hệ thống lớn hơn chênh lệch ấy.

## 9. Một báo cáo ví dụ tách đúng chỉ số

Bảng sau là **mẫu kết quả giả định** để luyện cách diễn giải, không phải đo đạc một dự án thật:

| Metric | Baseline A | AppCDS B | Diễn giải |
| --- | ---: | ---: | --- |
| Startup median | 1.200 ms | 780 ms | B nhanh hơn 420 ms (35%) |
| Startup p95 | 1.380 ms | 930 ms | P95 startup giảm; cần N và điều kiện đo |
| Time from READY to steady | 6,0 s | 5,9 s | Gần tương đương; không thể quy khẳng định tăng JIT peak |
| Steady throughput | 1.000 RPS | 995 RPS | Chênh 0,5%, cần xét độ nhiễu |
| Steady P95 latency | 20 ms | 20 ms | Không thay đổi trong mẫu |
| Steady error rate | 0,0% | 0,0% | Không có lỗi quan sát |
| PSS của một nhóm 4 JVM | 1.600 MiB | 1.460 MiB | Có thể ít physical memory hơn; phải biết cách đo shared pages |
| Cold-window 5 giây | 3.800 request | 4.220 request | Số lượng có thể tăng do thời gian trước READY giảm |

Với bộ số giả định này, kết luận phù hợp:

> “AppCDS cải thiện thời gian khởi động và có thể giảm memory footprint của nhiều JVM; trong phép đo steady-state, chưa có bằng chứng cải thiện throughput đáng kể. Lợi ích số request trong cửa sổ 5 giây đến từ việc READY sớm hơn, không phải tốc độ xử lý request đã tăng.”

Không tuyên bố “AppCDS tăng tốc toàn bộ ứng dụng 35%”, vì 35% chỉ là **tỷ lệ giảm một metric**: startup.

### 9.1. Vì sao cần ghi cả CPU và GC?

Nếu candidate dùng ít CPU hơn trong giai đoạn startup, một cụm Kubernetes có thể khởi động nhiều replica cùng lúc mà ít đụng quota hơn. Điều đó có thể gián tiếp cải thiện thời gian hoàn tất rollout. Nhưng nếu CPU steady-state đã bão hòa vì SQL hoặc thuật toán, ứng dụng có thể không nhận thêm QPS.

Ngược lại, heap hoặc GC khác nhau giữa A/B có thể ảnh hưởng steady throughput mạnh hơn CDS. Nếu không giữ ổn định chúng, kết quả mất ý nghĩa nhân quả.

### 9.2. Ưu tiên của workload quyết định giá trị

| Workload | Startup benefit đáng giá thế nào? | Steady throughput đáng giá thế nào? |
| --- | --- | --- |
| CLI tool chạy vài trăm ms đến vài giây | Rất đáng quan tâm | Có thể kém quan trọng vì runtime ngắn |
| Serverless/scale-to-zero | Thường quan trọng cho cold starts | Vẫn quan trọng với invocation dài/nhiều request |
| Microservice quay vòng pod thường xuyên | Quan trọng cho rollout/autoscaling | Quan trọng khi tải kéo dài |
| Service chạy liên tục nhiều tuần | Chi phí startup được phân bổ rất lâu | Thường là KPI chính, cùng latency và chi phí |
| Batch job xử lý 10.000 records | Tùy độ dài job; time-to-first-work có thể quan trọng | Chi phối khi phần xử lý records là phần lớn tổng thời gian |
| Nhiều JVM cùng node | Startup và shared metadata có lợi | Tùy CPU/GC và mức đồng thời toàn node |

Một quyết định tối ưu đúng phải bám **SLO** của ứng dụng thay vì mặc định tối ưu mọi dự án bằng cùng một cờ JVM.

## 10. Bộ nhớ chia sẻ: dấu hiệu cần đo và bẫy dễ gặp

### 10.1. CDS chia sẻ gì?

Archive chứa dữ liệu các lớp có thể memory-map thành những trang chỉ đọc hoặc vùng metadata có thể chia sẻ giữa các JVM tương thích. Khi nhiều JVM dùng chung archive, hệ thống có thể tiết kiệm physical memory so với việc mỗi tiến trình tự giữ tất cả metadata tương tự.

Nhưng:
- Mỗi JVM vẫn có heap, stack, JIT code cache, native allocations, connection pools và dữ liệu runtime riêng.
- Ứng dụng có thể cấp phát nhiều heap hơn số metadata đã tiết kiệm.
- Không phải mọi class đều có trong archive.
- Không phải mọi memory mapping đều được chia sẻ vật lý ở mọi tình huống.

### 10.2. RSS, PSS, USS cần được hiểu đúng

- **RSS (Resident Set Size):** số trang resident được quy về một tiến trình; các trang shared có thể được tính trong RSS của **mỗi** tiến trình, nên cộng RSS của nhiều JVM có thể double-count physical memory.
- **PSS (Proportional Set Size):** phân bổ chi phí shared pages theo tỷ lệ; thường hữu ích trên Linux khi đánh giá tổng physical-memory footprint của các tiến trình chia sẻ.
- **USS (Unique Set Size)/private pages:** xấp xỉ những trang chỉ thuộc tiến trình đó; hữu ích khi cần biết riêng từng JVM tiêu bao nhiêu tài nguyên không chia sẻ.

Tên/khả năng số đo tùy OS/tool; không có một API Java tiêu chuẩn duy nhất bảo đảm một bảng PSS/USS portable. Windows Task Manager, Linux `/proc`, cgroup memory và công cụ container có thể cho số khác nhau về phạm vi. Đọc định nghĩa của tool dùng thay vì chỉ nhìn một con số “memory”.

### 10.3. Vì sao RSS có thể không giảm dù AppCDS có lợi?

Khi archive được memory-map, nhiều trang có thể thuộc working set của từng process. Tổng RSS hiển thị qua các process có thể **trông không giảm nhiều**, thậm chí tăng, trong khi trang chung chỉ cần một bản vật lý.

Vì vậy để đánh giá mục tiêu giảm footprint của nhiều JVM:
1. Chạy cùng số replica trên cùng một node/OS.
2. Đo tổng memory thực tế từ OS/cgroup và nếu có PSS/USS.
3. Ghi shared/private pages và archive mappings.
4. Giữ heap, load, GC, số thread và cache ứng dụng như nhau.
5. Đừng so một JVM AppCDS với bốn JVM baseline rồi kết luận.

## 11. JIT, GC và AOT cache: không gộp tất cả thành AppCDS

### 11.1. AppCDS truyền thống không phải AOT native-image hoặc JIT compiler

AppCDS tập trung vào việc tái sử dụng thông tin class đã chuẩn bị; nó **không thay thế** cơ chế JIT tối ưu mã nóng khi ứng dụng chạy. Các phương pháp khác có những mục tiêu riêng:

| Công nghệ/đòn bẩy | Mục tiêu chính | Đừng lẫn với |
| --- | --- | --- |
| CDS/AppCDS | Dữ liệu class, startup và chia sẻ metadata | Mã máy optimized của toàn bộ hot path |
| JIT tiered compilation | Tối ưu method dựa trên profile | Nạp class từ archive |
| GC tuning | Điều chỉnh throughput, pause, heap behavior | Tăng tốc class parsing bằng archive |
| Cải thiện algorithm/SQL/cache | Giảm chi phí nghiệp vụ mỗi request | JVM startup |
| JDK 24+ AOT cache (Leyden) | Lưu thêm kết quả công việc ahead of time, có thể giảm startup/warmup | Tự động đồng nghĩa cờ AppCDS truyền thống hoặc native-image |
| JDK 25 AOT method profiling | Cho JIT dùng profile từ training sớm hơn, cải thiện warmup | Bảo đảm steady QPS tăng theo tỷ lệ cố định |

Đây là khác biệt về **cơ chế**, không phải lời khẳng định hai công nghệ hoàn toàn không ảnh hưởng tới metric của nhau. Chúng có thể tác động chung tới latency sớm, memory, CPU và năng lực phục vụ của cluster.

### 11.2. Các khả năng hiện đại của JDK 24/25

Theo các tài liệu công bố về JDK:
- **JDK 24 — JEP 483:** *Ahead-of-Time Class Loading & Linking* xây dựng trên công nghệ CDS, lưu trạng thái class đã load/link trong **AOT cache** để giảm thêm công việc trước startup.
- **JDK 25 — JEP 514:** làm đơn giản thao tác tạo cache bằng `-XX:AOTCacheOutput=...` trong tình huống phù hợp.
- **JDK 25 — JEP 515:** AOT method profiling đưa profile method từ training vào cache để JIT có thể tối ưu sớm hơn, đặc biệt hữu ích cho **warmup**.
- Các phiên bản JDK có thể tiếp tục cải thiện cơ chế; hãy xem đúng JDK đang triển khai khi chọn cờ.

Ví dụ template **dành cho JDK 25 với AOT Cache**, khác với lệnh `ArchiveClassesAtExit` truyền thống:

```text
# Training run tạo AOT cache khi ứng dụng kết thúc:
java -XX:AOTCacheOutput=app.aot -cp app.jar com.example.App --train

# Deployment run dùng cache:
java -XX:AOTCache=app.aot -cp app.jar com.example.App --one-shot
```

Hai dòng này **không chạy độc lập** vì cần ứng dụng `app.jar` và các tham số tự định nghĩa. Chúng thể hiện workflow được tài liệu hóa cho JDK 25, không phải cú pháp được bảo đảm trên mọi JDK 17/21. Xem tài liệu JDK/GC/OS cụ thể và tái tạo cache khi JDK hoặc application build thay đổi.

**Điểm cần giữ khi đọc kết quả:** nếu dùng AOT Cache với **method profiles**, một cải thiện warmup có thể liên quan **AOT profiling** chứ không thuần túy do AppCDS class metadata. Báo cáo benchmark phải ghi toàn bộ flags và JDK version để người đọc biết nguyên nhân có thể xảy ra.

### 11.3. Đừng so AppCDS/JDK21 với AOT/JDK25 rồi quy chênh lệch cho archive

Nếu so:
- Baseline Java 21, default CDS.
- Candidate Java 25, AOT cache.

thì bạn đã thay đổi cùng lúc:
- JDK version, JIT, GC và các tối ưu JVM khác.
- Cơ chế archive/cache.
- Khả năng runtime/libraries và class path behavior.

Khi candidate nhanh hơn, **không thể quy toàn bộ chênh lệch cho AppCDS**. Để tách riêng tác động:
- So hai trạng thái có/không một tối ưu trên **cùng JDK**.
- Có thí nghiệm khác riêng cho nâng cấp JDK.
- Nếu dùng kết hợp CDS/AOT, thiết kế matrix factorial với các cấu hình hợp lệ theo JDK.

## 12. Bẫy benchmark thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Đo chạy một batch 5 giây rồi gọi số jobs/5s là “steady throughput” | Phần đầu chứa startup | Tách startup và cửa sổ sau warmup |
| Khẳng định AppCDS “tăng thông lượng 35%” từ startup giảm 35% | Hai đại lượng khác nhau | Báo startup reduction và steady QPS riêng |
| Chỉ đo từ đầu `main` | Bỏ phần JVM bootstrap trước `main` | Dùng timer ngoài tiến trình |
| Dùng log “started” làm READY dù DB/health chưa sẵn sàng | Chọn sai mốc | Readiness có kiểm tra chức năng cần thiết |
| So `-Xshare:off` với custom archive rồi nói đó là phần đóng góp riêng của AppCDS | Baseline tắt cả CDS mặc định | So default CDS với custom app archive |
| Không biết archive có được JVM dùng không | JVM có thể fallback hoặc bỏ qua | Kiểm tra `-Xlog:cds=info` và class load |
| Dùng log `-Xlog:class+load=trace` trong một bên của benchmark chính | Logging tạo overhead không cân xứng | Chẩn đoán riêng hoặc bật đều như nhau |
| Tạo archive bằng workload chỉ gọi `main` không load luồng chính | Coverage không đủ, hiệu quả thấp | Training đại diện các đường startup/requests |
| Tính time tạo archive vào từng startup | Sai mô hình chi phí nếu archive tạo lúc build | Báo training cost và deployment startup riêng |
| Thay JDK, GC hoặc heap cùng lúc với archive | Không cô lập nguyên nhân | Giữ đối chứng tương đương |
| Dùng một run duy nhất | Nhiễu CPU/page cache/lịch tải | Nhiều lần, đảo A/B, báo phân phối |
| So RPS tại mức tải thấp hơn năng lực cả hai | Có thể không nhìn thấy giới hạn | Đo cả load curve, p95/p99 và error rate |
| Chỉ so tổng request gửi, không đếm thành công | Timeout/5xx làm số liệu sai | Đếm successful completions |
| Dùng `System.currentTimeMillis()` cho timer cần monotonic | Clock wall có thể đổi | Harness monotonic clock |
| Khẳng định JIT code đã AOT-compile chỉ vì có AppCDS | AppCDS không tương đương AOT compiled code | Phân biệt JIT, CDS và AOT cache mới |
| Cộng RSS của các process làm chi phí RAM thực tế | Shared pages bị cộng nhiều lần | Xem PSS/USS và cgroup totals |
| Dùng archive cũ sau cập nhật JAR/JDK | Archive/cache có thể không tương thích | Regenerate và verify tại mỗi build |
| Bật `-Xshare:on` trong production để ép archive | JVM có thể dừng nếu archive không dùng được | Dùng phù hợp policy; `-Xshare:on` cho testing |
| Coi kết quả benchmark cũ là cam kết performance | JVM/app/workload thay đổi | Re-benchmark trên bản phát hành thật |

## 13. Câu hỏi tự kiểm tra

### 13.1. AppCDS có thể làm thời gian launch → READY giảm nhưng steady RPS không đổi không?

**Có.** AppCDS có thể loại một phần chi phí class loading lúc đầu, nhưng tốc độ thực thi sau warmup có thể vẫn bị giới hạn bởi cùng mã tối ưu, CPU, GC hay I/O. Không có bất biến nào bắt steady throughput tăng tương ứng.

### 13.2. Nếu một ứng dụng chỉ sống 3 giây, AppCDS có thể có lợi không?

**Có thể rất có lợi**, vì startup chiếm tỷ trọng lớn của toàn bộ vòng đời. Nhưng phải đo end-to-end task completion; không khẳng định tất cả thao tác đều nhanh hơn do archive.

### 13.3. Nếu P99 steady-state tốt hơn, có chắc do AppCDS không?

**Chưa chắc.** Có thể do khác GC, tải, số CPU, cache, cgroup throttling hoặc thay đổi lịch chạy. Cần A/B trên cùng điều kiện và kết quả lặp lại để xem tính ổn định.

### 13.4. Nếu RSS không giảm, AppCDS không có tác dụng bộ nhớ phải không?

**Không đủ cơ sở.** Shared pages có thể được tính trong RSS của nhiều process. Khi mục tiêu là physical memory trên host, xem PSS/USS, private/shared mappings, tổng cgroup và tài liệu công cụ.

### 13.5. Nếu JVM đã có default CDS archive, có còn cần AppCDS archive không?

Tùy nhu cầu. Default CDS thường đã giúp classes của JDK; application archive có thể chứa thêm classes của ứng dụng, giảm thêm công việc startup. Chi phí tạo/vận hành archive và compatibility phải được cân nhắc. Không phải app nào cũng có lợi ích đủ lớn.

### 13.6. Có được dùng `-Xshare:off` trên production để đo “không AppCDS” không?

Có thể dùng ở môi trường benchmark có kiểm soát, nhưng `-Xshare:off` tắt **toàn bộ CDS**, làm baseline khác về nhiều thành phần hơn. Khi mục tiêu là đo incremental AppCDS, nên so default CDS với custom application archive. Không âm thầm thay chính sách production cho một phép thử.

### 13.7. Startup 35% nhanh hơn có nghĩa CPU cost lâu dài giảm 35% không?

**Không.** Có thể tiết kiệm CPU lúc khởi động nhưng steady CPU cost mỗi request không đổi. Cần đo CPU-seconds của startup và resource cost ổn định riêng.

### 13.8. Warmup có thể giảm dù peak throughput không đổi không?

**Có.** Ứng dụng đạt peak sớm hơn nhưng giới hạn peak vẫn như trước. Tính năng AOT method profiling trên JDK 25 minh họa lý do phải đo time-to-peak tách với peak QPS.

## 14. Bài tập thực hành có lời giải

### Bài 1 — Phân tích startup và throughput

Baseline READY sau 1.200 ms, AppCDS READY sau 780 ms. Cả hai đạt 1.000 RPS sau warmup. Tỷ lệ giảm startup và tăng steady QPS là bao nhiêu?

**Đáp án:** Startup giảm `(1200−780)/1200×100=35%`. Steady QPS tăng `0%`. Không có lý do gọi hai đại lượng ấy là một.

### Bài 2 — Cửa sổ tính từ launch

Với mô hình lý tưởng không có warmup, 5 giây từ launch có bao nhiêu thời gian phục vụ nếu READY sau 1,2 giây so với 0,78 giây?

**Đáp án:** 3,8 giây và 4,22 giây. Ở 1.000 RPS, lần lượt tối đa 3.800 và 4.220 request, tăng 11,1% trong cửa sổ, **không phải RPS steady-state**.

### Bài 3 — Phân biệt hai cách đo

Một benchmark bắt đầu đếm từ lúc ứng dụng nhận request đầu tiên, kết thúc 30 giây sau warmup. Một benchmark khác bắt đầu từ lúc spawn process và kết thúc sau 30 giây. Chúng đo cùng một đại lượng không?

**Đáp án:** Không. Thí nghiệm thứ hai trộn startup với thời gian xử lý; cả hai phải ghi tên/điểm bắt đầu, kết thúc cụ thể. Chỉ số thu được không được gắn chung nhãn “steady throughput”.

### Bài 4 — Baseline không đúng

Đội kỹ thuật so `java -Xshare:off ...` với `java -XX:SharedArchiveFile=app.jsa ...` rồi báo “mức tăng thuần AppCDS”. Điều gì sai?

**Đáp án:** A tắt cả default CDS; B có thể dùng default và app archive. Chênh lệch không cô lập incremental effect của application classes. Dùng baseline default CDS với cùng JVM/app để đo phần ứng dụng.

### Bài 5 — Time-to-ready từ `main`

Tại sao gọi `System.nanoTime()` ở dòng đầu `main` rồi trừ thời gian ở cuối init chưa chắc là launch-to-READY?

**Đáp án:** Không tính thời gian trước `main` như việc tạo process và JVM bootstrap. Cần timer ngoài tiến trình hoặc tracing/harness có mốc launch.

### Bài 6 — Thông lượng và p95

Candidate có P95 latency request đầu tốt hơn nhưng RPS ở steady không đổi. Có được coi AppCDS vô ích không?

**Đáp án:** Không. Với cold-start-sensitive workload, cải thiện first request có giá trị. Nhưng phải báo metric đúng và xác nhận chênh lệch qua nhiều lần đo.

### Bài 7 — JIT và CDS

AppCDS đã lưu nhiều class trong archive. Có nghĩa method tính toán nóng nhất được biên dịch thành native code tối ưu trước khi app khởi động không?

**Đáp án:** Không phải đặc tính được bảo đảm bởi **AppCDS truyền thống**. JIT và các cơ chế AOT profiling/cache mới có nhiệm vụ khác; cần xác định phiên bản và cờ thật sự đang dùng.

### Bài 8 — Memory sharing

Bốn JVM cùng dùng archive; tổng RSS giảm ít nhưng tổng PSS giảm rõ. Có mâu thuẫn không?

**Đáp án:** Không. Trang shared có thể bị đếm trong RSS mỗi tiến trình, còn PSS phân bổ lại shared pages. Cần đọc cách tính của công cụ và quan sát tổng host/cgroup.

### Bài 9 — Archive không được dùng

Ứng dụng chạy với `-XX:SharedArchiveFile=app.jsa` nhưng log cho thấy archive bị từ chối. Có nên ghi “đã thử AppCDS thành công” không?

**Đáp án:** Không. Trước khi diễn giải benchmark cần xác minh archive thực sự được sử dụng, không chỉ xuất hiện ở command line. Nếu bị từ chối, sửa cấu hình/training trong phạm vi được phép và thử lại như một thí nghiệm mới.

### Bài 10 — Thử nghiệm thay JDK

Baseline dùng JDK 21, candidate dùng JDK 25 có AOT method profiling. Có thể quy mức warmup tốt hơn cho AppCDS Java 10 không?

**Đáp án:** Không. JDK/JIT/GC và công nghệ cache cùng thay đổi. Cần một đối chứng cùng JDK, và nếu muốn so JDK, báo đó là phép thử nâng cấp runtime.

### Bài 11 — Tác dụng trong service dài hạn

Một service chạy 7 ngày, tiết kiệm 400 ms khi khởi động nhưng peak QPS không đổi. Cải thiện lớn nhất kỳ vọng ở đâu?

**Đáp án:** Chủ yếu ở restart/rollout/cold-start và có thể ở shared-memory footprint. Trong 7 ngày steady load, 400 ms startup có tỷ trọng rất nhỏ. Vẫn phải đo để quyết định có đáng chi phí vận hành archive hay không.

### Bài 12 — Cấu hình khác nhau

AppCDS B được cấp CPU quota 4 cores, baseline A chỉ có 2 cores. Kết quả B tăng peak RPS 30%. Kết luận gì?

**Đáp án:** Không thể quy mức tăng cho AppCDS. CPU quota là biến gây nhiễu. Phải giữ CPU quota và các điều kiện chính bằng nhau rồi đo lại.

### Bài 13 — Con số tăng 11,1% ở ví dụ mô hình

Tại sao việc 4.220 request so với 3.800 request ở cùng cửa sổ launch-to-5s không chứng minh thông lượng steady tăng?

**Đáp án:** Vì phần thời gian READY khác nhau. Mỗi cấu hình đều xử lý ở 1.000 RPS khi hoạt động; chỉ tổng số giây được phục vụ trong cửa sổ khác.

### Bài 14 — Kiểm tra tài liệu hiện hành

Khi chạy trên JDK 25 và muốn tối ưu warmup theo Project Leyden, nên nhầm `-XX:AOTCacheOutput` với `-XX:ArchiveClassesAtExit` không?

**Đáp án:** Không. Chúng thuộc cơ chế/workflow được tài liệu hóa ở các giai đoạn khác nhau của CDS/AOT. Cần dùng đúng cờ được phiên bản HotSpot hỗ trợ, kiểm tra tính tương thích và ghi rõ cấu hình trong báo cáo.

## 15. Checklist code review và performance review

- [ ] Bài toán đã chọn đúng metric: startup, first response, warmup, steady QPS, tail latency hay footprint.
- [ ] Nhớ AppCDS từ Java 10 chủ yếu hỗ trợ class archive, startup và memory sharing.
- [ ] Không hứa steady-state throughput tăng chỉ vì class loading nhanh hơn.
- [ ] Dùng metric time-to-ready tính từ **process launch**, không chỉ từ đầu `main`.
- [ ] Nếu quan tâm warmup, định nghĩa cách xác nhận đã đạt trạng thái ổn định.
- [ ] Nếu quan tâm throughput, đo successful operations/second sau warmup, có offered load và error rate.
- [ ] Không trộn cold-window completed requests với steady QPS.
- [ ] So baseline **default CDS** với candidate **AppCDS archive** nếu cần cô lập lợi ích ứng dụng.
- [ ] Chỉ dùng `-Xshare:off` như một đối chứng có ghi chú rõ khi cần.
- [ ] Cùng JDK, vendor, application artifact, classpath, CPU quota, GC, heap, OS và dependency.
- [ ] Xác minh archive được dùng qua log ở một run chẩn đoán; không tự suy từ flag.
- [ ] Tạo archive bằng training workload đại diện, không chỉ nạp lớp không dùng.
- [ ] Không đưa thời gian tạo archive vào mỗi startup nếu archive được tạo ở build time.
- [ ] Regenerate archive/cache khi thay JDK, application build hoặc điều kiện tương thích quan trọng.
- [ ] Đo nhiều lần launch, thay đổi thứ tự A/B, báo phân phối và độ nhiễu.
- [ ] Không đo steady throughput trên load generator bị quá tải.
- [ ] Báo CPU, GC, p95/p99 latency, error rate và memory cùng metric chính.
- [ ] Đánh giá PSS/USS/shared mappings khi quan tâm footprint nhiều JVM, không chỉ cộng RSS.
- [ ] Phân biệt AppCDS truyền thống với AOT Cache JDK 24/25 và JEP 515 AOT profiling.
- [ ] Không dùng `-Xshare:on` trên production chỉ để ép archive hoạt động.
- [ ] Dùng `AppCdsPhasesLab.java` để xác minh 16 dòng **kết quả mô hình**, không dùng chúng làm benchmark thực tế.
- [ ] Kết luận cuối cùng theo **SLO và dữ liệu đã đo** của ứng dụng cụ thể.

## 16. Kết luận

**AppCDS có thể giúp JVM khởi động và sẵn sàng phục vụ sớm hơn, đồng thời chia sẻ một phần class metadata giữa các JVM. Điều đó không tương đương với tối ưu thông lượng khi code đã warm up.** Lợi ích trong một cửa sổ thời gian ngắn có thể tăng nhờ bớt thời gian chờ startup, dù **requests/second steady state không đổi**.

Khi đánh giá, tách riêng startup → warmup → steady state, dùng đối chứng với default CDS, kiểm chứng archive thực sự được dùng và đo nhiều lần trên cùng môi trường. Với JDK mới, còn có khả năng **AOT class loading/linking và AOT method profiling** — những cơ chế có thể giảm warmup theo cách khác với AppCDS truyền thống. Đừng gộp tất cả vào một câu “AppCDS tăng throughput”; hãy nêu **metric được cải thiện, mức cải thiện và điều kiện đo**.

## 17. Tài liệu tham khảo chính thức và thực hành

- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): động cơ và phạm vi AppCDS từ Java 10.
- [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): CDS/AppCDS, khởi động, footprint, archive mặc định và `-Xshare`.
- [Oracle Java SE 25 — The java Command / Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#application-class-data-sharing): `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile`, CDS archive, classpath restrictions và logging.
- [Oracle Java SE 25 — The java Command / Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#ahead-of-time-cache): cơ chế AOT cache và điều kiện tương thích của JDK/platform/application.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): lớp đã load/link trong AOT cache từ JDK 24.
- [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): giảm thao tác tạo AOT cache trên JDK 25.
- [OpenJDK JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): chuyển profile ban đầu sang AOT cache để cải thiện warmup.
- [Inside Java (Oracle, 2026) — Run Into the New Year with Java’s AOT Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/): workflow training/assembly/deployment và lưu ý khi đo startup/warmup.
- [Oracle Java SE 25 — JVM Performance Tuning Examples](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#performance-tuning-examples): phân biệt mục tiêu throughput và response time trong HotSpot.
- [Red Hat Developer — Speed up Java application startup time with AppCDS](https://developers.redhat.com/articles/2024/01/23/speed-java-application-startup-time-appcds): ví dụ thực tế về khả năng cải thiện startup, số liệu chỉ có ý nghĩa với workload đã đo.