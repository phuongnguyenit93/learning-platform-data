# Amdahl's Law và giới hạn tăng tốc khi chạy song song trong Java

## 1. Tại sao thêm thread không có nghĩa chương trình nhanh gấp bấy nhiêu lần?

Một chương trình Java có thể gồm các đoạn độc lập chạy đồng thời, nhưng cũng có những bước **buộc phải tuần tự**: chuẩn bị dữ liệu chung, chờ kết quả cần thiết của bước trước, ghép kết quả, thao tác trên tài nguyên có khóa, hoặc xử lý chỉ có một nơi thực hiện. Phần tuần tự không biến mất khi ta tăng số worker.

**Amdahl's law (định luật Amdahl)** cho biết giới hạn tăng tốc lý tưởng của **cùng một lượng công việc cố định** khi chỉ một phần của công việc được chạy song song. Đây là công cụ để ước lượng lợi ích tối đa của việc tăng mức song song và quyết định nên tối ưu phần nào trước.

Ví dụ một tác vụ mất 100 ms trên một worker, gồm:
- 20 ms bắt buộc tuần tự;
- 80 ms có thể chia đều hoàn hảo cho nhiều worker.

Với 4 worker, thời gian lý tưởng mới là `20 + 80 / 4 = 40 ms`, tức nhanh **2,5 lần** chứ không phải 4 lần. Ngay cả khi có vô hạn worker, phần 20 ms vẫn tồn tại: giới hạn lý tưởng chỉ **5 lần**.

## 2. Công thức, ký hiệu và cách suy ra

Đặt:

| Ký hiệu | Ý nghĩa |
|---|---|
| `T(1)` | Thời gian chạy ban đầu với một đơn vị xử lý, cho một workload cố định. |
| `p` | **Tỷ phần thời gian của baseline** thuộc công việc có thể tăng tốc bằng chạy song song, `0 ≤ p ≤ 1`. |
| `1 - p` | Tỷ phần thời gian bắt buộc tuần tự. |
| `N` | Số đơn vị xử lý song song hiệu dụng trong mô hình lý tưởng, `N ≥ 1`. |
| `S(N)` | Speedup: `T(1) / T(N)`. |

Nếu phần tuần tự mất `(1 - p) × T(1)`, còn phần có thể song song mất `p × T(1) / N` ở điều kiện lý tưởng, thì:

```text
T(N) = T(1) × [(1 - p) + p / N]

S(N) = T(1) / T(N)
     = 1 / [(1 - p) + p / N]
```

Khi `N` rất lớn, `p / N` tiến gần 0:

```text
S(max) = 1 / (1 - p)      nếu p < 1
```

Với `p = 1`, mô hình không còn phần tuần tự, nên `S(N) = N`; mô hình lý tưởng này không tính chi phí đồng bộ, khởi tạo thread, lập lịch, truyền dữ liệu hay tranh chấp tài nguyên.

**Quan trọng:** `p` là tỷ lệ **thời gian thực thi baseline** có thể tăng tốc, không phải tỷ lệ số dòng code, số method có thể gọi đồng thời, số thread hiện có, hay phần trăm CPU hiển thị trong Task Manager. Một method ngắn nhưng chạy hàng triệu lần có thể chiếm phần lớn thời gian; ngược lại một method dài nhưng hiếm gọi có thể đóng góp rất ít.

### Ví dụ tính tay

Giả sử `p = 0,90`, tức 90% thời gian có khả năng song song và 10% là phần tuần tự.

| N (worker hiệu dụng) | Công thức mẫu | Speedup lý tưởng | Hiệu suất trên mỗi worker `E = S/N` |
|---:|---|---:|---:|
| 1 | `1 / (0,10 + 0,90)` | 1,000× | 100,0% |
| 2 | `1 / (0,10 + 0,90/2)` | 1,818× | 90,9% |
| 4 | `1 / (0,10 + 0,90/4)` | 3,077× | 76,9% |
| 8 | `1 / (0,10 + 0,90/8)` | 4,706× | 58,8% |
| 16 | `1 / (0,10 + 0,90/16)` | 6,400× | 40,0% |
| ∞ (giới hạn) | `1 / 0,10` | 10,000× | Không áp dụng |

Nếu `T(1) = 100 s`, thì với 8 worker thời gian lý tưởng là `100 × (0,10 + 0,90/8) = 21,25 s`, tương ứng `100 / 21,25 ≈ 4,706×`. Thêm worker vẫn cải thiện được, nhưng **lợi ích biên nhỏ dần** vì phần 10 s tuần tự không giảm.

## 3. Speedup, efficiency và throughput khác nhau

**Speedup** của một công việc cố định:

```text
speedup = thời gian xử lý bằng 1 worker / thời gian xử lý bằng N worker
```

**Parallel efficiency** là `S(N)/N`, thể hiện mức khai thác tương đối so với tăng tốc tuyến tính lý tưởng `S(N)=N`. Ví dụ `S(8)=4,706` thì hiệu suất bằng `4,706/8≈58,8%`; không có nghĩa CPU của mỗi core đang bận đúng 58,8%.

**Throughput** là số công việc hoàn tất mỗi giây. Nếu chương trình xử lý nhiều request độc lập cùng lúc, tăng số worker có thể tăng throughput ngay cả khi **latency của một request cụ thể gần như không đổi**. Amdahl's law theo công thức trên nói về thời gian một **workload cố định**, không tự động dự đoán throughput, thời gian chờ hàng đợi, hoặc độ trễ đuôi `p95/p99`.

Để sử dụng công thức đúng, cần thống nhất “một công việc” là gì: một batch cố định, một phép tính cố định hay một lần xử lý dữ liệu cố định. Không được đem thời gian xử lý 10.000 bản ghi trên một thread so với 100.000 bản ghi trên nhiều thread rồi gọi tỷ số đó là speedup theo Amdahl.

## 4. Ví dụ Java 17: tính toán giới hạn lý tưởng

Lưu thành tệp `AmdahlCalculator.java`:

```java
import java.util.Locale;

public class AmdahlCalculator {
    static double speedup(double parallelFraction, int workers) {
        if (parallelFraction < 0 || parallelFraction > 1 || workers < 1) {
            throw new IllegalArgumentException("p must be 0..1 and N >= 1");
        }
        return 1.0 / ((1.0 - parallelFraction)
                + parallelFraction / workers);
    }

    public static void main(String[] args) {
        double p = 0.90;

        for (int n : new int[] { 1, 2, 4, 8, 16 }) {
            double s = speedup(p, n);
            System.out.printf(Locale.ROOT,
                    "N=%2d speedup=%.3f efficiency=%.3f%n",
                    n, s, s / n);
        }

        System.out.printf(Locale.ROOT,
                "Gioi han ly tuong: %.1fx%n", 1.0 / (1.0 - p));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AmdahlCalculator.java
java AmdahlCalculator
```

Stdout chính xác:

```text
N= 1 speedup=1.000 efficiency=1.000
N= 2 speedup=1.818 efficiency=0.909
N= 4 speedup=3.077 efficiency=0.769
N= 8 speedup=4.706 efficiency=0.588
N=16 speedup=6.400 efficiency=0.400
Gioi han ly tuong: 10.0x
```

`Locale.ROOT` làm dấu thập phân trong output ổn định (`.`), không phụ thuộc locale của hệ điều hành. Trong mô hình, `N` là số worker có thể thực sự tính song song; **`newFixedThreadPool(16)` không bảo đảm 16 core vật lý** hay tăng tốc tương ứng.

Nếu `p=0,80`, trần lý tưởng chỉ `1/(1-0,80)=5×`. Nếu `p=0,95`, trần tăng lên `20×`, nhưng với 8 worker tốc độ lý tưởng vẫn chỉ `1/(0,05+0,95/8)≈5,926×`. Như vậy cải thiện phần tuần tự hoặc tăng tỷ phần có thể song song đôi khi có ích hơn bổ sung worker.

## 5. Công thức lý tưởng và thời gian thực tế

Ở chương trình thực, thời gian gần đúng có thể viết:

```text
T(N) ≈ Tserial + Tparallel / N + Toverhead(N)
```

`Toverhead(N)` không nhất thiết là hằng số và đôi khi tăng khi số worker tăng:

- **Tạo và quản lý thread:** khởi tạo, chuyển ngữ cảnh, lập lịch và đánh thức task có chi phí.
- **Phân chia/ghép kết quả:** tạo task, đưa vào queue, chờ `Future`, `join()`, merge hoặc reduce dữ liệu.
- **Đồng bộ hóa:** `synchronized`, `Lock`, contention ở counter/queue, tranh chấp critical section.
- **Bộ nhớ và cache:** giới hạn băng thông RAM, cache coherence, false sharing, cache miss; nhiều core không tạo thêm băng thông vô hạn.
- **Giới hạn phần cứng:** số core vật lý, SMT/hyper-threading, các process khác, chế độ tiết kiệm điện và thermal throttling.
- **GC và allocation:** cấp phát nhiều đối tượng trung gian hoặc tăng live set có thể gây áp lực GC.
- **Phụ thuộc dữ liệu:** một task phải chờ kết quả của task khác; không phải cứ tách nhiều task là chúng đồng thời hữu ích.

Một tình huống thực tế: phép tính hoàn thành trong 100 ms với một worker, phần song song lý tưởng là 90%. Với 8 worker, Amdahl dự đoán 21,25 ms. Nếu scheduling, lock và merge cộng thêm 8 ms, thời gian có thể là `29,25 ms`, speedup chỉ `100 / 29,25 ≈ 3,419×`. Đó là lý do không nên xem con số lý tưởng như lời hứa hiệu năng.

Amdahl's law **không phải một định luật cấm mọi speedup vượt con số dự đoán** khi chương trình thực thay đổi thuật toán, dùng cache tốt hơn hoặc thực hiện workload khác; những tình huống đó đã thay đổi giả định của mô hình ban đầu. Nếu số đo vượt dự đoán, cần kiểm tra giả định và phương pháp đo thay vì kết luận Java “vi phạm” Amdahl.

## 6. Ví dụ Java 17: chia một lượng công việc cố định cho ExecutorService

Đoạn dưới minh họa cách chia **cùng một phép tính CPU-bound** thành các khoảng không trùng nhau. Nó xác nhận kết quả đúng trước khi bàn đến nhanh hay chậm, vì tăng tốc bằng cách bỏ sót phần tử là không hợp lệ.

Lưu thành `FixedWorkDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FixedWorkDemo {
    private static long calculate(int fromInclusive, int toExclusive) {
        long sum = 0;
        for (int i = fromInclusive; i < toExclusive; i++) {
            long value = i % 997L;
            sum += (value * value + 7L * value) % 1009L;
        }
        return sum;
    }

    public static void main(String[] args) throws Exception {
        final int items = 8_000_000;
        final int workers = Math.min(4,
                Math.max(1, Runtime.getRuntime().availableProcessors()));

        long sequential = calculate(0, items);
        ExecutorService executor = Executors.newFixedThreadPool(workers);

        try {
            List<Future<Long>> results = new ArrayList<>();

            for (int part = 0; part < workers; part++) {
                int from = (int) ((long) part * items / workers);
                int to = (int) ((long) (part + 1) * items / workers);
                results.add(executor.submit(() -> calculate(from, to)));
            }

            long parallel = 0;
            for (Future<Long> result : results) {
                parallel += result.get();
            }

            System.out.println("Ket qua bang nhau: " + (sequential == parallel));
            System.out.println("So worker hop le: "
                    + (workers >= 1 && workers <= 4));
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(1, TimeUnit.MINUTES)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Chạy:

```bash
javac FixedWorkDemo.java
java FixedWorkDemo
```

Stdout (không phụ thuộc số CPU được báo bởi JVM):

```text
Ket qua bang nhau: true
So worker hop le: true
```

Giải thích:
1. `calculate(0, items)` là baseline tuần tự, dùng cùng thuật toán tính với mỗi task.
2. Chia `[0, items)` thành `workers` khoảng liên tiếp, không giao nhau và bao phủ toàn bộ dữ liệu; ép trung gian sang `long` để tránh tràn khi nhân chỉ số chia.
3. `submit` trả về `Future<Long>`; `get()` đợi task hoàn tất rồi cộng kết quả, tạo một đoạn ghép kết quả tuần tự.
4. Thread pool được `shutdown()` sau khi sử dụng; Java 17 không yêu cầu và cũng không dùng `try-with-resources` cho `ExecutorService`.

Ví dụ này **minh họa phân chia công việc đúng**; nó không tự chứng minh có speedup. Với số lượng phần tử nhỏ, chi phí task và lịch chạy có thể lớn hơn phần thời gian tiết kiệm được.

### Đo speedup thực nghiệm đúng phạm vi

Có thể đo thời gian bằng `System.nanoTime()` trước/sau đoạn tuần tự và trước/sau đoạn song song, rồi tính `speedupObserved = elapsedSequential / elapsedParallel`. Nhưng chỉ đo một lần, chạy baseline trước rồi mới chạy parallel, hay đo cả thời gian tạo pool chỉ ở một bên sẽ dễ đưa ra kết luận sai.

Để benchmark công bằng hơn:
- Dùng **cùng dữ liệu, thuật toán, kết quả đầu ra** và tài nguyên tương đương; quyết định rõ có tính startup/pool creation vào phép đo hay không.
- Warm up để JIT compilation và class loading giảm tác động; đo nhiều lần qua nhiều fork, quan sát phân phối chứ không tin một lần ngẫu nhiên.
- Ngăn dead-code elimination và constant folding; đảm bảo kết quả thực sự được sử dụng/kiểm tra.
- Kiểm soát CPU frequency, số core được phân bổ, tải nền, heap và GC; ghi rõ phiên bản JDK/JVM.
- Benchmark vi mô Java nên cân nhắc **JMH (Java Microbenchmark Harness)** thay vì tự viết một vòng lặp đo thời gian dễ sai. Với cả pipeline, đo end-to-end ở mức workload thực, kể cả phần tuần tự và chờ.

Không thể suy ra `p` chỉ bằng cách đếm số task hoặc thread. Có thể dùng profiler, JFR (Java Flight Recorder), thread dump và CPU profiling để tìm nơi mất thời gian, rồi đo lại sau khi thay đổi. Các số đo tổng hợp có thể dùng để kiểm tra sự phù hợp của mô hình, nhưng `p` thu được chỉ là ước lượng phụ thuộc workload và môi trường.

## 7. Dùng Amdahl để ra quyết định kỹ thuật

### Trường hợp A: tăng worker khi phần tuần tự vẫn lớn

`T(1)=100 ms`, trong đó 30 ms bắt buộc tuần tự. Với `p=0,70`:

```text
N=2  -> T=30+70/2   = 65,00 ms -> S≈1,538x
N=4  -> T=30+70/4   = 47,50 ms -> S≈2,105x
N=8  -> T=30+70/8   = 38,75 ms -> S≈2,581x
N=∞  -> T tiến về 30 ms          -> trần S≈3,333x
```

Nếu mục tiêu là nhanh ít nhất 4 lần với cùng công việc, chỉ tăng số worker **không thể đạt mục tiêu trong mô hình**. Cần giảm phần tuần tự, thay thuật toán, hoặc thay điều kiện bài toán.

### Trường hợp B: tối ưu phần tuần tự trước

Giả sử thời gian baseline 100 ms gồm 20 ms serial và 80 ms parallelizable. Với 8 worker: `T(8)=20+80/8=30 ms` (3,333×). Nếu tối ưu bước serial từ 20 ms xuống 5 ms mà giữ phần parallel 80 ms, tổng thời gian với 8 worker còn `5+80/8=15 ms`. So với baseline **ban đầu** 100 ms, đây là 6,667×. Nhưng sau khi thay đổi code, phần trăm `p` so với baseline mới đã đổi; không được tiếp tục thay `p=0,80` vào mọi phép tính như thể không có gì thay đổi.

### Trường hợp C: tăng N nhưng contention cũng tăng

Giả sử với 4 worker, `T=40 ms`, nhưng 8 worker làm lock/contention và merge tăng 20 ms. Dù phần chia lý tưởng giảm, `T(8)` thực tế có thể **lớn hơn 40 ms**. Cần tìm lock nóng, giảm chia sẻ mutable state, giảm số task quá nhỏ, dùng cấu trúc dữ liệu thích hợp hoặc giảm số worker. Tăng N khi workload đã bão hòa băng thông nhớ thường không giúp ích.

### Trường hợp D: workload I/O-bound

Các tác vụ chờ network/disk có thể hưởng lợi từ concurrency do **che giấu thời gian chờ**, tăng số request đồng thời hoặc throughput. Nhưng tốc độ xử lý một request còn phụ thuộc dịch vụ bên ngoài và giới hạn connection. Không được dùng `N` trong công thức như số lượng thread tùy ý rồi kết luận một request sẽ nhanh theo tỷ lệ ấy. Muốn áp dụng mô hình Amdahl phải xác định phần thực sự có thể overlap hoặc chạy song song, cùng workload và tài nguyên.

## 8. Phân biệt Amdahl với mở rộng khối lượng công việc

Amdahl's law ở đây giả định **fixed-size workload / strong scaling**: tăng tài nguyên, giữ nguyên bài toán. **Weak scaling** lại tăng lượng việc theo tài nguyên, ví dụ mỗi core vẫn xử lý một partition cố định. Khi workload thay đổi, cách đánh giá khác và có thể dùng cách nhìn kiểu Gustafson để hỏi “trong cùng thời gian, xử lý được bài toán lớn hơn bao nhiêu?”.

Vì thế cần nêu rõ mục tiêu trước khi nói “scale tốt”:
- Giảm latency hoàn thành **một batch cố định**? Hãy đo strong-scaling speedup và so với Amdahl.
- Tăng throughput cho **nhiều tác vụ độc lập**? Hãy đo task/s, độ trễ, queue length và mức bão hòa tài nguyên.
- Xử lý dataset lớn hơn trong **cùng khoảng thời gian**? Hãy đo weak scaling, không đưa trực tiếp thời gian của hai dataset khác nhau vào `S(N)=T(1)/T(N)` của Amdahl.

## 9. Lỗi hiểu và áp dụng thường gặp

| Hiểu sai | Điều cần làm |
|---|---|
| “Có 8 thread thì tối đa phải nhanh gấp 8.” | Xác định `p`, core thực, overhead và tranh chấp; 8× chỉ là trường hợp lý tưởng đặc biệt. |
| “90% code song song được nên p=0,90.” | Đo **thời gian**, không đếm dòng code. |
| “N là số thread tạo ra.” | Trong mô hình `N` là khả năng xử lý song song hiệu dụng, không vượt qua giới hạn phần cứng và workload. |
| “Amdahl dự đoán đúng thời gian chạy trên mọi máy.” | Đây là giới hạn/ước lượng lý tưởng với giả định cố định; cần đo overhead và tải thực. |
| “CPU-bound càng nhiều task càng tốt.” | Task quá nhỏ làm overhead lớn; chọn kích thước task đủ lớn và đo. |
| “Speedup 4× nghĩa là throughput mọi request cũng 4×.” | Latency của workload cố định, throughput và concurrency là các metric khác nhau. |
| “Sau khi tối ưu thuật toán vẫn dùng p cũ.” | Mỗi lần thay đổi cấu trúc hoặc workload cần đo lại baseline và tỷ phần thời gian. |

## 10. Bài tập tự kiểm tra

**Bài 1.** Một phép tính có `p=0,75`. Nếu có 4 worker hiệu dụng, speedup lý tưởng là bao nhiêu? Trần khi N rất lớn?

```text
S(4) = 1 / (0,25 + 0,75/4)
     = 1 / 0,4375
     ≈ 2,286x

S(max) = 1 / 0,25 = 4x
```

**Bài 2.** Một batch chạy tuần tự 200 ms, gồm 40 ms serial và 160 ms parallelizable. Với 8 worker và overhead 10 ms, thời gian và speedup thực tế mô hình hóa là bao nhiêu?

```text
T(8) = 40 + 160/8 + 10 = 70 ms
Speedup = 200/70 ≈ 2,857x
```

Nếu bỏ overhead, kết quả lý tưởng chỉ `200/60≈3,333×`; không thể giả định 8×.

**Bài 3.** Khi thêm worker từ 4 lên 16, throughput tăng nhưng latency mỗi request không thay đổi. Có mâu thuẫn Amdahl không? **Không**. Có thể hệ thống đang phục vụ nhiều request độc lập cùng lúc; hãy phân biệt throughput toàn hệ thống với thời gian chạy của một request đơn lẻ.

**Bài 4.** Một chương trình đo được 16 worker chậm hơn 8 worker. Có nên tạo thêm 32 thread? **Chưa có cơ sở**. Trước hết profile CPU, lock, queue, cache/memory và GC; kiểm tra liệu task có quá nhỏ hoặc vượt số core hiệu dụng hay không.

## 11. Tổng kết thực hành

Amdahl's law trả lời câu hỏi: **với một lượng việc không đổi và tỷ lệ thời gian không thể song song còn tồn tại, tăng số worker có thể nhanh hơn đến đâu trong điều kiện lý tưởng?**

```text
Speedup lý tưởng: S(N) = 1 / [(1 - p) + p/N]
Trần với p < 1: S(max) = 1 / (1 - p)
Hiệu suất:       E(N) = S(N) / N
```

Khi tối ưu Java concurrency, hãy xác định workload, đo baseline, tìm phần tuần tự/critical path, chọn mức song song phù hợp với core và chi phí đồng bộ, rồi benchmark đầu-cuối. **Giảm phần serial và overhead thường quan trọng ngang hoặc hơn việc thêm thread.**

### Tài liệu tham khảo

- [Java SE 17 — `ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): vòng đời executor và chờ hoàn tất.
- [Java SE 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): nhận và chờ kết quả tác vụ.
- [Java SE 17 — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): đồng hồ đo khoảng thời gian.
- [OpenJDK — JMH](https://openjdk.org/projects/code-tools/jmh/): công cụ benchmark vi mô cho JVM.
