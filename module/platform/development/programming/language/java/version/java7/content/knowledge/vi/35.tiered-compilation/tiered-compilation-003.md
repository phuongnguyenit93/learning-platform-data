# JIT phân tầng: quan hệ giữa thời gian khởi động và hiệu năng ổn định

## 1. Vấn đề: nhanh lúc bắt đầu hay nhanh khi chạy lâu?

Một chương trình Java có thể phản hồi rất nhanh sau khi chạy lâu, nhưng những request đầu tiên lại chậm hơn. Ngược lại, cấu hình chạy tốt ngay khi mới khởi động chưa chắc cho throughput tốt nhất sau vài phút. Đó là một trong các bài toán quan trọng mà **tiered compilation (biên dịch JIT phân tầng)** của HotSpot giải quyết.

**Ý chính:** thay vì buộc mọi bytecode phải đi qua một trình tối ưu hóa chuyên sâu ngay từ đầu, HotSpot sử dụng **interpreter**, trình biên dịch **C1** nhanh hơn và trình biên dịch tối ưu sâu **C2** (trên cấu hình HotSpot sử dụng các compiler này), cùng dữ liệu profiling thu thập khi chương trình thực sự chạy. Nhờ đó JVM cân bằng được:

- **Startup:** thời gian từ khi chạy tiến trình đến khi ứng dụng bắt đầu sẵn sàng làm việc.
- **Warm-up:** thời gian/lượng công việc cần thiết để các đường chạy nóng được phát hiện, biên dịch và tối ưu hóa.
- **Steady state:** giai đoạn hành vi hiệu năng tương đối ổn định với cùng loại workload, sau khi những hoạt động như class loading, JIT compilation và khởi tạo cache chính đã lắng xuống.

Tiered compilation vẫn là cơ chế hiện hành, **bật mặc định trong HotSpot Server VM thông dụng**. Mặc dù phần này nằm trong chủ đề Java 7 vì tiered compilation xuất hiện từ giai đoạn đó, kiến thức bên dưới tập trung vào **HotSpot/JDK hiện đại (Java 17+)** và công cụ còn được hỗ trợ.

> **Không có bảo đảm rằng “chạy đủ N vòng” thì mọi method đạt C2 hoặc hiệu năng ổn định.** Một phương thức có thể không được biên dịch, được biên dịch nhiều lần, bị deoptimization hoặc tiếp tục thay đổi hiệu năng khi dữ liệu và môi trường chạy thay đổi.

## 2. Phân biệt ba mốc thời gian thường bị gọi chung là “khởi động”

| Mốc | Điều được đo | Ví dụ và lưu ý |
| --- | --- | --- |
| **Process/JVM startup** | Từ khi tiến trình được tạo và JVM khởi tạo đến một mốc trong chương trình | Khởi tạo VM, load/link class, runtime, module, static initializer; đồng hồ đo từ bên ngoài còn bao gồm overhead tạo process |
| **Application readiness / time to first response** | Đến lúc ứng dụng chấp nhận request hoặc hoàn thành request đầu tiên | Có thể gồm DI container, cấu hình, kết nối DB, HTTP listener, lazy initialization; không đồng nhất với thời gian JIT |
| **Warm-up to stable service** | Đến khi throughput, latency và hành vi tải tương đối ổn định | JIT compilation, profiling, cache, connection pool, GC, CPU scaling đều có thể góp phần |

**Ví dụ:** một service thông báo “Started” sau 2 giây nhưng request đầu tiên mất 400 ms, còn sau 3 phút p95 latency giảm xuống 40 ms. Không thể quy toàn bộ chênh lệch cho JIT nếu chưa tách các yếu tố như đọc cấu hình, TLS, I/O, pool và caching.

**Startup thấp** và **steady-state throughput cao** là hai mục tiêu khác nhau. Tiered compilation tìm cách tránh đánh đổi quá mạnh một mục tiêu lấy mục tiêu kia, nhưng mỗi ứng dụng cần chọn ưu tiên theo vòng đời thật.

## 3. HotSpot làm gì trước khi có code đã tối ưu sâu?

Java source được `javac` biên dịch thành **bytecode** trong file `.class`. Khi JVM chạy, bytecode ban đầu có thể được **interpreter** thực thi; JVM ghi nhận thông tin về tần suất gọi method, tần suất chạy vòng lặp và profile của các nhánh/kiểu đối tượng để quyết định biên dịch.

HotSpot có hai compiler quan trọng trong mô hình tiered truyền thống:

1. **C1:** biên dịch nhanh, tạo native code sớm; một số mức C1 còn chứa instrumentation để thu thập profile.
2. **C2:** tối ưu chuyên sâu hơn, thường tốn CPU/thời gian biên dịch hơn; có thể sử dụng profile đã thu thập để tối ưu những đường chạy thường xảy ra.

Sơ đồ khái quát:

```text
                         Java bytecode
                                |
                                v
                     Interpreter (bắt đầu)
                                |
               quan sát lượt gọi / vòng lặp / kiểu
                                |
                   policy chọn biên dịch
                        /               \
                       v                 v
                   C1 code           trực tiếp C2
                (nhanh hơn để       (tùy policy,
                 có code sớm)        trường hợp)
                       |
           chạy và thu thập thêm profile
                       |
                       v
                  C2 optimized code
                       |
               guard/assumption sai?
                       |
                       v
              deoptimization -> tiếp tục và có thể biên dịch lại
```

Đây là **lược đồ**, không bắt buộc mọi method đi đúng một chuỗi tuyến tính. Bộ chính sách compilation có thể chuyển cấp, biên dịch ở một tier nhất định hoặc không biên dịch nếu method không đủ nóng. Inlining có thể khiến một method “xuất hiện” bên trong code biên dịch của method gọi, thay vì có một bản mã máy riêng dễ thấy trong log.

### Tại sao không dùng C2 ngay cho mọi method?

C2 có thể tạo native code chất lượng cao nhưng cần phân tích và tối ưu. Việc biên dịch tất cả method lúc startup làm tiêu tốn CPU, bộ nhớ/code cache và thời gian, trong khi nhiều method chỉ chạy một vài lần. Dữ liệu profiling thực tế còn giúp C2 biết nhánh/kiểu nào thường gặp để tối ưu hiệu quả hơn.

C1 giúp những method được gọi thường xuyên thoát sớm khỏi tốc độ interpreter, đồng thời cung cấp dữ liệu cho quyết định tối ưu sâu hơn. Như vậy, ứng dụng có thể đạt hiệu năng hữu ích sớm mà vẫn có cơ hội đạt throughput cao khi chạy lâu.

## 4. Các mức biên dịch trong HotSpot tiered

Một sơ đồ **tham khảo cho HotSpot C1/C2** thường dùng năm execution level:

| Level | Engine | Điểm chính |
| ---: | --- | --- |
| **0** | Interpreter | Thực thi bytecode, có thể thu thập dữ liệu thực thi |
| **1** | C1, tối ưu cơ bản, không profiling bổ sung | Native code sớm khi policy không cần thu thêm profile cho đường chạy đó |
| **2** | C1 với profiling giới hạn | Số liệu invocation và backedge; overhead profiling thấp hơn cấp đầy đủ |
| **3** | C1 với profiling đầy đủ hơn | Thu thập profile để hỗ trợ tối ưu sâu |
| **4** | C2 | Native code tối ưu chuyên sâu, có thể dùng profile đã quan sát |

**C1** phụ trách các cấp 1–3, **C2** phụ trách cấp 4 trong mô hình HotSpot truyền thống. Đường đi điển hình có thể là **0 → 3 → 4**, nhưng **không phải quy luật bắt buộc**. Khi hàng đợi C1/C2, thời gian chạy và độ nóng khác nhau, HotSpot có thể chọn đường đi khác. Đây là mô tả của một triển khai JVM: không phải đặc tả Java Language Specification và không có API Java SE để một ứng dụng yêu cầu mọi method phải lên cấp 4.

### Hai dạng “nóng” thường kích hoạt compiler

- **Method invocation:** phương thức được gọi nhiều lần.
- **Loop backedge:** một vòng lặp chạy nhiều lần, ngay cả khi method chỉ được gọi rất ít lần.

Với loop dài, HotSpot có thể sử dụng **on-stack replacement (OSR)** để chuyển phần thực thi của vòng lặp đang chạy từ interpreter/code cũ sang một phiên bản biên dịch tại vị trí phù hợp, thay vì phải chờ method kết thúc và được gọi lại. Việc xuất hiện bản OSR trong compilation log không đồng nghĩa cả method đã luôn chạy bằng C2 từ lúc vào method.

## 5. Quan hệ giữa startup, warm-up và throughput ổn định

### 5.1. Ở những request đầu tiên

JVM vừa khởi động cần load/link class, chạy khởi tạo tĩnh, cấp phát đối tượng và xây dựng dữ liệu runtime. Nhiều đường mã vẫn đang được interpreter thực thi hoặc mới có C1 code. Một số profile chưa đủ để compiler thực hiện các tối ưu dựa trên hành vi thực tế.

Do đó request đầu tiên có thể chịu:

- cost khởi tạo framework và tài nguyên ngoài (database, DNS, TLS, disk);
- công việc class loading và initialization;
- thời gian interpreter/C1 chạy code nóng;
- chi phí CPU của JIT compilation chạy song song;
- cache và pool chưa được điền đủ dữ liệu.

**Kết luận:** C1 giúp tăng tốc giai đoạn sớm, nhưng không có công thức cố định “startup giảm X%” hay “request đầu tiên nhanh Y lần”. Tỷ lệ phụ thuộc workload, bản JDK, CPU, deployment và môi trường.

### 5.2. Khi JVM ấm lên

Khi request/loop lặp lại, JVM thu thập profile, đưa các method nóng vào hàng đợi biên dịch và cài code mới. Những tối ưu thường thấy ở C2 bao gồm:

- **Inlining:** thay call bằng thân method trong những trường hợp được đánh giá có lợi.
- **Loop optimization:** cải thiện cách tổ chức vòng lặp, loại bỏ phần kiểm tra dư thừa khi đủ điều kiện.
- **Escape analysis:** phân tích phạm vi sống của đối tượng để hỗ trợ scalar replacement và loại bỏ một số cấp phát/đồng bộ không cần thiết khi hợp lệ.
- **Speculative optimization:** tận dụng profile kiểu/nhánh thường gặp kèm guard để vẫn duy trì tính đúng đắn nếu giả định thay đổi.

JIT có thể chạy trên compiler threads trong khi application threads vẫn phục vụ request. Điều này tốt cho khả năng phản hồi liên tục, nhưng khiến **CPU utilization lúc warm-up** có thể cao hơn mức steady state. Nếu container bị giới hạn CPU, compiler threads còn tranh CPU với application threads và có thể làm độ trễ request tăng trong một khoảng thời gian.

### 5.3. Khi hệ thống tương đối ổn định

Khi các hot paths đã được biên dịch phù hợp, cache và pool đã ổn định, ứng dụng có thể đạt **throughput cao hơn** và **chi phí CPU trên mỗi request thấp hơn** so với giai đoạn đầu.

Tuy nhiên **steady state không đồng nghĩa JVM đã dừng biên dịch hoàn toàn**. Hot path mới, dữ liệu mới, class mới, class unloading, deoptimization hoặc phương thức vừa trở nên hot có thể làm JIT tiếp tục hoạt động.

Một thay đổi tỷ lệ request từ 90% đọc sang 90% ghi có thể làm giả định về “code đã ấm” không còn đúng với workload mới. Vì thế, throughput ổn định phải được phát biểu **gắn với phân phối workload đang đo**, chứ không phải trạng thái bất biến của toàn JVM.

## 6. Đánh đổi giữa biên dịch sớm và tối ưu sâu

| Chiến lược/hiện tượng | Startup và warm-up | Khi chạy dài | Chi phí/rủi ro |
| --- | --- | --- | --- |
| **Interpreter lâu hơn** | Ít chi phí JIT biên dịch ban đầu | Method nóng thường chậm hơn native code đã tối ưu | Tốn CPU để thực thi bytecode |
| **C1 ra code sớm** | Có thể tăng tốc khi ứng dụng còn đang warm-up | Có thể chưa tối ưu như C2 | Phải biên dịch, có profiling overhead ở các cấp tương ứng |
| **C2 cho hot methods** | Có thể cần thời gian lấy profile/chờ compiler | Có tiềm năng throughput cao hơn và latency trên hot path tốt hơn | CPU biên dịch và code cache lớn hơn |
| **Tiered mặc định** | Tự cân bằng tốc độ có code, dữ liệu profile, tài nguyên compiler | Cho phép tiến đến C2 ở các path đáng đầu tư | Hành vi động, không phải mọi method đi đủ cấp |
| **Chỉ cho chạy C1 trong một thí nghiệm** | Có thể giảm thời gian warm-up ở một số workload | Có thể mất một số tối ưu sâu của C2 | Kết quả tùy workload, bản JVM |
| **Bắt interpreter-only để đối chứng** | Tránh JIT biên dịch | Thường kém rõ trên code CPU-bound | Không đại diện cấu hình production bình thường |

Tùy loại ứng dụng, **thời gian trả về lần đầu** có thể quan trọng hơn throughput sau 10 phút. Ví dụ CLI tồn tại 200 ms khác đáng kể so với backend phục vụ hàng triệu request trong nhiều ngày.

### Ba bối cảnh ứng dụng

**CLI chạy ngắn:** nếu tiến trình chỉ tồn tại 1–2 giây, có thể thoát trước khi một số tối ưu sâu có cơ hội bù lại chi phí JIT. Hãy đo cả *thời gian tiến trình chạy hoàn tất*, trong điều kiện cold/hot OS cache phù hợp.

**API service sống lâu:** startup có thể chiếm tỷ lệ nhỏ trong tổng runtime, còn steady-state throughput, p95/p99 request latency, CPU và GC được ưu tiên. Nhưng deployment rolling hoặc autoscaling vẫn đặt ra yêu cầu mới: pod phải sẵn sàng nhanh, và request đầu tiên sau scale-out không được gây lỗi latency lớn.

**Serverless/scale-to-zero:** cold start xảy ra thường xuyên hơn; giảm class loading, initialization và chuẩn bị sớm tài nguyên có thể hữu ích cùng với tuning JIT. Cần đo thời gian từ request kích hoạt đến response thực, không chỉ thời gian JVM in một dòng “main started”.

## 7. Deoptimization: vì sao đã nhanh vẫn có thể chậm lại?

C2 có thể tối ưu dựa trên profile mà JVM quan sát được. Chẳng hạn trong một giai đoạn, một interface có đúng một loại implementation; trình biên dịch có thể inline nhánh phổ biến và chèn kiểm tra để bảo đảm tính đúng đắn. Khi runtime gặp trường hợp khác giả định, **deoptimization** có thể chuyển việc thực thi về dạng an toàn hơn và JVM có thể biên dịch lại sau đó.

Chuỗi ví dụ:

```text
Warm-up: 99% calls là type A
    -> C2 tối ưu đường A
    -> request chuyển sang 50% type B
    -> guard có thể thất bại, deoptimization/recompile
    -> latency tạm thời tăng rồi ổn định lại
```

Đây là **tình huống minh họa**, không khẳng định JVM sẽ deopt trong mọi lần phân phối kiểu thay đổi. Compilation, OSR và deoptimization là lý do không nên suy luận rằng “ổn định” nghĩa là hiệu năng một chiều tăng mãi.

## 8. Ví dụ Java 17+: quan sát các batch từ sớm đến muộn

Ví dụ chạy độc lập dưới đây gọi lặp lại một method CPU-bound, đo thời gian từng batch bằng `System.nanoTime()` và giữ kết quả trong một biến `volatile` để JVM phải bảo toàn tác động quan sát được. Nó giúp **nhìn sự thay đổi theo thời gian**, nhưng không đủ để kết luận chính xác thời điểm đạt C2 hoặc tạo một microbenchmark khoa học.

Lưu file **`TieredWarmupDemo.java`**:

```java
import java.util.Locale;

public class TieredWarmupDemo {
    private static volatile long observable;

    private static long calculate(int limit) {
        long sum = 0;
        for (int i = 1; i <= limit; i++) {
            sum += (long) i * i;
        }
        return sum;
    }

    public static void main(String[] args) {
        final int batches = 12;
        final int operationsPerBatch = 20_000;

        for (int batch = 1; batch <= batches; batch++) {
            long start = System.nanoTime();
            long checksum = 0;

            for (int op = 0; op < operationsPerBatch; op++) {
                checksum += calculate(100 + op % 25);
            }

            observable = checksum;
            double milliseconds =
                    (System.nanoTime() - start) / 1_000_000.0;

            System.out.printf(Locale.ROOT,
                    "Batch %02d: %.3f ms%n", batch, milliseconds);
        }

        System.out.println("Completed batches: " + batches);
        System.out.println("Result preserved: " + (observable != 0));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TieredWarmupDemo.java
java TieredWarmupDemo
```

Cấu trúc stdout gồm 12 dòng `Batch XX: ... ms`, rồi hai dòng cuối **chính xác**:

```text
Completed batches: 12
Result preserved: true
```

Thời gian trên mỗi batch thay đổi theo CPU, JDK, scheduler, compiler threads, hệ thống và việc JVM đã biên dịch method nào. **Không được bịa một dãy số thời gian cố định** cho máy khác. Một batch sau nhanh hơn batch đầu có thể là kết quả của JIT, cache CPU và nhiều yếu tố khác; không đủ bằng chứng để nói chỉ C2 gây ra thay đổi.

### So sánh ba cách chạy

Để xem đường chạy compilation thực tế, chạy:

```bash
java -XX:+PrintCompilation TieredWarmupDemo
```

Log sẽ có những dòng mô tả method được biên dịch, đôi khi có cấp compiler hoặc đánh dấu OSR (tùy bản HotSpot). Số dòng và thứ tự là **không cố định**, vì JVM có thể biên dịch cả lớp thư viện và chính chương trình.

Đối chứng interpreter-only:

```bash
java -Xint TieredWarmupDemo
```

`-Xint` tắt JIT để chạy bytecode bằng interpreter, thích hợp làm **đối chứng chẩn đoán**. Nó thường làm công việc lặp CPU chậm hơn; không nên dùng mặc định cho môi trường production.

Thử nghiệm chính sách giới hạn cấp compiler (trên HotSpot hỗ trợ cờ này):

```bash
java -XX:TieredStopAtLevel=1 TieredWarmupDemo
```

Cấu hình này hạn chế việc nâng cấp compiler lên tier cao hơn trong HotSpot hỗ trợ `TieredStopAtLevel`. Nó **có thể** giúp một số ứng dụng ngắn hạn giảm chi phí biên dịch, nhưng cũng **có thể** làm giảm hiệu năng ổn định vì không đạt C2. Đây là cờ **triển khai HotSpot**, không được bảo đảm trên mọi JVM; thử và kiểm tra bằng `java -XX:+PrintFlagsFinal -version` cho đúng runtime.

**Lưu ý về thời điểm đo:** chương trình in thời gian batch chỉ sau khi `main` bắt đầu, **không đo thời gian tạo process, JVM startup hay thời gian ứng dụng service thật sẵn sàng**. Vì vậy không dùng các số batch để kết luận “JVM khởi động trong 3 ms”.

## 9. Tách chi phí JVM startup và JIT warm-up trong phép đo

Muốn đánh giá mối quan hệ giữa hai giai đoạn, thiết kế phép đo tách biệt.

### 9.1. Đo cold start

Chạy **nhiều tiến trình mới**, mỗi tiến trình là một lần đo. Với ứng dụng thật, mốc kết thúc là readiness signal hoặc response đầu tiên. Ghi nhận:

- thời gian từ launch đến readiness;
- thời gian từ launch đến first successful request;
- p50/p95 của nhiều cold starts;
- tình trạng page cache, JDK version, CPU/memory limit và kích thước image/heap;
- số class được load, phân tích khi class loading/initialization chiếm nhiều thời gian.

Đối với ứng dụng CLI, công cụ bên ngoài như `/usr/bin/time` trên hệ điều hành có hỗ trợ có thể cho biết tổng wall-clock time:

```bash
/usr/bin/time -p java TieredWarmupDemo
```

Trên Windows PowerShell, có thể sử dụng:

```powershell
Measure-Command { java TieredWarmupDemo | Out-Null }
```

Hai lệnh đo **thời gian tiến trình của chính chương trình demo**, không tự tạo API readiness. Chúng bao gồm toàn bộ thực thi 12 batch, vì vậy không nên đặt tên kết quả là “chỉ thời gian JVM khởi tạo”. Với backend, cần một harness đợi readiness/request cụ thể.

### 9.2. Đo steady-state throughput/latency

Để đo code nóng, chạy **warm-up có kiểm soát** với workload đại diện, sau đó mới đo lường. Đo ít nhất:

- throughput (ops/s hoặc requests/s);
- trung vị và p95/p99 latency;
- CPU usage, quota throttling nếu có, allocation/GC activity;
- compilation activity, code cache và deoptimization nếu nghi ngờ JIT ảnh hưởng;
- throughput khi service đã duy trì tải đủ lâu.

**Đừng chọn “warm-up 10.000 calls” theo cảm tính.** Một method được gọi 10.000 lần có thể trở nên hot, nhưng service còn hàng nghìn đường mã khác; method rất ngắn, không có loop hoặc nhiều request path có thể ấm khác nhau.

### 9.3. Kiểm tra warm-up đã ổn định chưa

Ví dụ, chia tải thành các cửa sổ 30 giây hoặc 1 phút rồi xem:

1. Throughput và latency của các cửa sổ cuối có còn thay đổi đáng kể không?
2. CPU compilation và sự kiện compile/deopt có giảm hay vẫn cao?
3. GC đã đạt chu kỳ tương đối đại diện chưa?
4. Cache và connection pool đã có trạng thái giống production chưa?
5. Khi workload chuyển pha, kết quả có còn đúng không?

Không yêu cầu đường biểu đồ phải hoàn toàn phẳng; luôn có noise. Mục tiêu là **so sánh các phương án dưới cùng điều kiện**, có nhiều lần chạy độc lập và thể hiện sai số/độ biến thiên.

## 10. Dùng JMH để đo method đã warm-up

Tự gọi `System.nanoTime()` trong một vòng lặp dễ sai vì JIT có thể inline, loại bỏ tính toán không quan sát được, constant-fold hoặc thay đổi cách tối ưu qua từng lượt. **Java Microbenchmark Harness (JMH)** là công cụ benchmark mã Java/JVM do OpenJDK duy trì; nó hỗ trợ warm-up iterations, measurement iterations, fork mới và quản lý kết quả.

Đoạn sau là **class benchmark dùng JMH, không phải chương trình độc lập có thể chạy bằng `javac` mà không có dependency JMH**:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 10, time = 1)
@Fork(3)
public class TieredJmhBenchmark {
    @Param({"100", "500"})
    public int limit;

    @Benchmark
    public long sumSquares() {
        long sum = 0;
        for (int i = 1; i <= limit; i++) {
            sum += (long) i * i;
        }
        return sum;
    }
}
```

JMH runner và dependencies (bao gồm annotation processor `jmh-generator-annprocess`) phải được cấu hình đúng theo hướng dẫn của phiên bản JMH sử dụng. Các annotation trên có ý nghĩa:

- `@Warmup`: những iteration chạy trước measurement để JVM có cơ hội biên dịch và ổn định.
- `@Measurement`: những iteration được lấy số liệu chính.
- `@Fork(3)`: dùng các JVM fork độc lập để giảm phụ thuộc vào lịch sử một process.
- `@Param`: thử nhiều kích thước công việc; kết quả của mỗi giá trị cần đọc riêng.
- Giá trị trả về của benchmark được JMH xử lý để hạn chế một số hình thức dead-code elimination.

**Giới hạn:** JMH đo microbenchmark ở steady state theo cấu hình, **không mặc nhiên đo startup của service**. Để đánh giá end-to-end startup, cần harness bên ngoài tạo tiến trình và theo dõi readiness. Không suy luận "method có ns/op thấp" có nghĩa ứng dụng sẽ sẵn sàng nhanh hơn.

## 11. Công cụ quan sát JIT hiện hành

| Công cụ/cờ | Dùng để làm gì | Điều cần nhớ |
| --- | --- | --- |
| `-XX:+PrintCompilation` | In thông tin method compilation | Giúp xem method được biên dịch khi nào/cấp nào; log không phải số liệu throughput |
| `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` | Hiển thị các quyết định inlining | Output lớn, có thể ảnh hưởng phép đo; dùng khi điều tra |
| `-Xlog:class+load=info` | Theo dõi class loading | Hỗ trợ phân biệt startup do load class với JIT warm-up |
| `-Xlog:gc=info` | Theo dõi GC | Độ trễ/throughput cũng bị GC ảnh hưởng |
| `-XX:StartFlightRecording=filename=jit.jfr,settings=profile,dumponexit=true` | Thu Java Flight Recorder (JFR) trên JDK hỗ trợ | Phân tích CPU, allocation, JIT và các event có sẵn bằng JDK Mission Control hoặc công cụ đọc JFR |
| `-XX:+PrintFlagsFinal -version` | Xem cờ JVM hiện hành và giá trị mặc định/thực tế | Xác minh các cờ trước khi benchmark, vì JDK/vendor có thể khác nhau |

Ví dụ khởi động chương trình với JFR:

```bash
java -XX:StartFlightRecording=filename=jit.jfr,settings=profile,dumponexit=true TieredWarmupDemo
```

Kết quả là file `jit.jfr` khi runtime hỗ trợ JFR; bản ghi có thể chứa thông tin nhạy cảm của ứng dụng thật, nên bảo quản theo quy trình nội bộ. Cấu hình `profile` tạo overhead quan sát; khi so sánh hiệu năng, dùng cùng chế độ profiling hoặc tách riêng các lần thu profile với các lần benchmark chính.

JFR, `PrintCompilation` và GC log là nguồn **bổ trợ**: chúng mô tả hành vi hệ thống trong một lần chạy. Nên phối hợp với số liệu p95/p99, throughput, RSS và CPU thì mới kết luận được tối ưu startup có làm xấu steady-state hay không.

## 12. Trình biên dịch JIT và bộ nhớ: code cache

Native code do JIT tạo ra nằm trong **code cache** của HotSpot. Tiered compilation có thể tạo nhiều phiên bản mã máy cho một method qua các cấp khác nhau, kèm profiling data, nên có chi phí bộ nhớ và công việc quản lý code.

HotSpot hỗ trợ **segmented code cache** trên các cấu hình thích hợp, tách phần non-method, profiled và non-profiled code để quản lý hiệu quả hơn. Nếu code cache bị giới hạn và bị áp lực, JVM có thể gặp khó khăn trong việc tiếp tục biên dịch; điều này ảnh hưởng kết quả hiệu năng và cần được chẩn đoán bằng thông tin runtime thực tế.

Không nên áp dụng ngay một giá trị `-XX:ReservedCodeCacheSize` lấy từ bài viết cũ. Xem default và mức sử dụng trên JDK/vendor/heap/workload đang chạy. Tăng code cache có thể giúp một số ứng dụng có nhiều hot methods, nhưng cũng tiêu tốn memory budget của container.

**Compiler threads** tiêu thụ CPU và native memory. Trong môi trường giới hạn CPU, việc quan sát “request chậm lúc vừa triển khai” có thể liên quan compilation contention, nhưng cũng có thể do JIT, GC, throttling và cache cùng xảy ra; cần timeline để phân biệt.

## 13. Tuning: đổi startup có thể làm steady-state thay đổi

### 13.1. Các chế độ cần biết

| Chế độ HotSpot | Mục đích | Cần tránh hiểu sai |
| --- | --- | --- |
| Tiered mặc định | Cân bằng startup/warm-up với khả năng tối ưu lâu dài | Không cam kết mọi method đều C2 |
| `-XX:-TieredCompilation` | Tắt cơ chế biên dịch phân tầng | Không đồng nghĩa tắt tất cả JIT; khác hoàn toàn với `-Xint` |
| `-XX:TieredStopAtLevel=1` | Đối chứng giới hạn cấp compiler trên HotSpot có hỗ trợ | Có thể giảm compiler work nhưng ảnh hưởng tốc độ code nóng |
| `-Xint` | Chạy interpreter-only | Dùng để phân tích/so sánh, không phải tối ưu throughput mặc định |
| `-XX:+PrintCompilation` | Chẩn đoán JIT compilation | In log có overhead, không dùng tùy tiện trong benchmark chính |

Thay đổi một cờ có thể khiến cả **startup**, **warm-up duration**, **steady throughput**, **CPU** và **memory** thay đổi theo những hướng khác nhau. Vì vậy, luôn so sánh đa chỉ số, nhiều lần chạy, giữ nguyên workload/phiên bản Java/máy/container limit.

### 13.2. Khi nào không nên can thiệp JIT?

Nếu số liệu cho thấy startup chậm chủ yếu do chạy migration, kết nối dịch vụ ngoài, tải cấu hình, warm cache DB hoặc disk I/O, chỉnh `TieredStopAtLevel` sẽ không giải quyết đúng nút thắt. Phân tích thời gian theo từng giai đoạn, xác định hoạt động chiếm chi phí thực rồi mới thử thay cờ.

Nếu service chạy dài với latency và CPU tốt, **đừng mặc định tắt tiered compilation** chỉ vì muốn rút ngắn vài trăm ms startup. Có thể phải trả giá trong nhiều giờ hoạt động sau đó.

### 13.3. Kỹ thuật AOT hiện hành bổ trợ startup/warm-up

Trong JDK hiện đại, **Ahead-of-Time (AOT) cache** được bổ sung để lưu một số artifact của quá trình load/link class trước khi chạy ứng dụng; JDK 24 giới thiệu AOT class loading/linking (JEP 483). JDK 25 bổ sung **AOT method profiling** (JEP 515) để sử dụng profile từ một lần training, giúp JVM có thông tin cho tối ưu code sớm hơn.

AOT cache có thể giúp giảm startup và warm-up trong một số workload, nhưng:

- **Không có nghĩa mọi method đều được biên dịch máy đầy đủ trước khi khởi động.** JIT runtime vẫn giữ vai trò tối ưu theo hành vi thực tế.
- Training run cần đại diện cho production; cache có các ràng buộc tương thích theo ứng dụng, bản JDK, OS và CPU.
- Tính năng/flag và hiệu quả thay đổi theo phiên bản JDK, không áp dụng cấu hình AOT hiện đại cho Java 17 nếu runtime không hỗ trợ.
- Luôn benchmark **cùng một bản ứng dụng và cùng điều kiện** có/không cache; kiểm tra cold-start lẫn steady state.

Trọng tâm chủ đề vẫn là **tiered JIT**: AOT là kỹ thuật bổ trợ hữu ích khi mục tiêu là giảm phần khởi tạo/lấy profile, không phải “bộ thay thế” mặc định của C1/C2.

## 14. Thiết kế thí nghiệm đủ tốt để ra quyết định

Giả sử bạn vận hành một API Java thường xuyên scale từ 0 lên 4 instance. Mục tiêu là “request 60 giây đầu không vượt p95 300 ms, nhưng throughput sau 10 phút vẫn cao”.

Cách đánh giá:

1. **Chọn bản baseline:** cùng JDK, container image, quota CPU, heap, ứng dụng và workload.
2. **Định nghĩa cold:** start process mới, readiness từ HTTP probe và request đầu tiên sau readiness.
3. **Định nghĩa warm:** chạy workload có mix route, payload, connection pool, cache và kiểu object giống thực tế.
4. **Định nghĩa steady:** chọn khoảng đo sau khi thông số đã gần ổn định; ghi rõ warm-up duration, không mặc định một con số cho mọi phiên bản.
5. **Ghi cả nhiều chiều:** startup p50/p95; request p50/p95/p99 trong 1–2 phút đầu; steady throughput/latency; CPU và RSS; GC và compiler activity.
6. **Đổi một yếu tố mỗi lần:** ví dụ tiered mặc định và cấu hình C1-only, hoặc AOT cache có/không trên JDK hỗ trợ.
7. **Lặp qua nhiều process/fork độc lập:** phân biệt biến thiên OS/máy và hiệu ứng JIT; điều kiện cold cache cần xác định.
8. **Quyết định theo SLA:** ưu tiên cấu hình đáp ứng cả startup và steady state, chấp nhận trade-off có số liệu.

Bảng kết quả sau **chỉ là template để nhập số đo của bạn**, không phải số liệu Java có sẵn:

| Phương án | Time to readiness | p95 1 phút đầu | p95 steady | Throughput steady | CPU/RSS |
| --- | --- | --- | --- | --- | --- |
| Tiered mặc định | Đo | Đo | Đo | Đo | Đo |
| TieredStopAtLevel=1 | Đo | Đo | Đo | Đo | Đo |
| AOT cache (nếu JVM hỗ trợ) | Đo | Đo | Đo | Đo | Đo |

Đừng tối ưu metric đơn lẻ. Một cấu hình giảm 20% time to readiness nhưng làm mất 30% throughput khi ứng dụng chạy cả ngày có thể không phù hợp dịch vụ sống lâu; với job chỉ chạy vài giây, thứ tự ưu tiên có thể ngược lại. Các tỷ lệ ở đây là **ví dụ giả định**, không phải cam kết hiệu năng.

## 15. Những hiểu lầm và lỗi đo đạc phổ biến

1. **“Startup time chính là warm-up time.”** Startup đến readiness, còn warm-up đến hiệu năng tương đối ổn định; hai khoảng có thể chồng lấp nhưng không đồng nhất.
2. **“Lên C2 chắc chắn nhanh hơn mọi C1 code.”** Thường có cơ hội tối ưu sâu hơn, nhưng kết quả thật còn phụ thuộc workload, compiler assumptions, code size và CPU.
3. **“Tất cả method đi tuần tự level 0, 1, 2, 3, 4.”** HotSpot policy chọn lộ trình tùy tải/độ nóng; có thể bỏ qua cấp.
4. **“Chỉ cần gọi method 10.000 lần để ứng dụng đã nóng.”** Một method không đại diện toàn bộ service; thresholds không phải hằng số bất biến.
5. **“Kết quả batch đầu nhanh/chậm chỉ do tiered compilation.”** Có cả class initialization, OS page cache, GC, frequency scaling và scheduler.
6. **“Tắt tiered nghĩa là tắt JIT.”** `-XX:-TieredCompilation` khác `-Xint`.
7. **“Chạy `-XX:+PrintCompilation` là benchmark chính xác hơn.”** In log có thể tác động thời gian; dùng để quan sát chứ không thay thế phép đo độc lập.
8. **“JMH đo startup service.”** JMH thường đo microbenchmark với warm-up; service startup cần harness ở mức process/request.
9. **“Số nanosecond của một lần chạy đủ kết luận.”** JIT, GC, OS và CPU tạo biến thiên; cần nhiều forks/runs và thống kê.
10. **“Steady-state là mã sẽ không bao giờ bị deopt.”** Workload đổi hoặc assumptions sai có thể buộc JVM deopt/compile lại.
11. **“Càng ít biên dịch càng tốt.”** Ít chi phí JIT có thể đồng thời đánh đổi throughput cao của optimized code.
12. **“Mọi JVM đều có C1/C2, tier 0–4 và cùng flag.”** Đây là mô hình HotSpot; runtime khác có thể có cơ chế và khả năng khác.
13. **“AOT hiện đại có thể copy nguyên flag sang Java 17.”** Cần kiểm tra phiên bản: chức năng AOT cache mới thuộc các JDK sau đó.
14. **“CPU cao lúc warm-up chứng tỏ app chạy logic kém.”** Compiler threads có thể tiêu thụ CPU hợp lệ; cần tách CPU JIT với application.

## 16. Checklist áp dụng thực tế

- [ ] Xác định rõ yêu cầu là **startup/readiness**, **first-request latency**, **warm-up** hay **steady-state throughput**.
- [ ] Ghi lại JDK/vendor/build, JVM flags, heap, code cache, CPU quota, hệ điều hành và workload.
- [ ] Hiểu C1 giúp có native code sớm, C2 dùng profile để tối ưu sâu hơn; không giả định mọi method phải đạt level 4.
- [ ] Đo startup bằng tiến trình mới và readiness thực; đo steady-state trong giai đoạn đủ ổn định.
- [ ] Khi điều tra JIT, dùng `PrintCompilation`/JFR nhưng tách các lần profile khỏi benchmark cần độ chính xác cao.
- [ ] Sử dụng JMH với warm-up, measurement và forks độc lập cho microbenchmark.
- [ ] Quan sát deoptimization, GC, cache, class loading, CPU throttling và traffic mix trước khi quy lỗi cho JIT.
- [ ] Chỉ tuning `TieredStopAtLevel`, `TieredCompilation` hoặc code cache sau khi có phép đo chứng minh lợi ích.
- [ ] Với JDK mới hỗ trợ AOT cache, thử nghiệm có training đại diện và xác minh tính tương thích.
- [ ] Đánh giá **cả độ nhanh lúc đầu và chi phí vận hành lâu dài** trước khi chọn cấu hình.

## 17. Câu hỏi tự kiểm tra

1. Tại sao HotSpot không dùng ngay trình biên dịch tối ưu sâu cho mọi bytecode khi startup?
2. C1 giúp gì cho startup và giai đoạn thu thập profile, còn C2 giúp gì cho hiệu năng lâu dài?
3. Vì sao `-Xint` và `-XX:-TieredCompilation` là hai phép đối chứng khác nhau?
4. Tại sao một benchmark không warm-up có thể đo nhầm tốc độ interpreter/C1 thành “hiệu năng Java ổn định”?
5. Trường hợp nào method đã tối ưu vẫn có thể deopt và cần compile lại?
6. Vì sao p95 của request đầu tiên, throughput sau 10 phút và thời gian process khởi tạo là ba số đo cần tách?
7. Làm sao nhận biết ứng dụng bị chậm do class loading/cache hoặc database thay vì JIT?
8. Khi nào AOT cache hiện đại có thể bổ trợ tiered compilation?

## Tài liệu tham khảo hiện hành

- [Oracle Java SE 27 — Java HotSpot VM Performance Enhancements](https://docs.oracle.com/en/java/javase/27/vm/java-hotspot-virtual-machine-performance-enhancements.html): Tiered Compilation, quan hệ giữa C1/C2 và mục tiêu startup/peak performance.
- [Oracle Java SE 27 — `java` command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `-XX:-TieredCompilation`, `-Xint`, `-XX:+PrintCompilation`, code cache, AOT và JFR flags.
- [Microsoft for Java Developers — How Tiered Compilation Works in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): giải thích level 0–4 và chính sách nâng cấp compiler.
- [OpenJDK — JMH project](https://github.com/openjdk/jmh): harness dùng warm-up, measurement và JVM forks.
- [Inside Java — Performance Improvements in JDK 25](https://inside.java/2025/10/20/jdk-25-performance-improvements/): JEP 515 AOT method profiling và quan hệ startup/warm-up.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache cho tối ưu startup.
- [OpenJDK JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): sử dụng profile từ training để rút ngắn warm-up trên JDK hỗ trợ.
