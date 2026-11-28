# Cô lập thử nghiệm, đo lợi ích và đặt điều kiện chuyển sang tính năng chính thức trong Java 27

Java liên tục đưa ra những cải tiến về ngôn ngữ, thư viện và JVM. Một số cải tiến xuất hiện dưới dạng **preview** hoặc **incubator** để cộng đồng thử nghiệm trước khi thiết kế trở nên ổn định. Các tính năng này giúp nhóm phát triển đánh giá hướng đi mới, nhưng **không có cùng cam kết tương thích** với những API/tính năng chính thức của Java SE.

Câu hỏi kỹ thuật quan trọng không chỉ là “có nên thử tính năng mới không?”, mà là:

1. **Cô lập ở đâu** để tính năng chưa ổn định không rò rỉ vào bản phát hành chính?
2. **Đo lợi ích thế nào** để không nhầm kết quả benchmark tình cờ với cải thiện thực?
3. **Điều kiện nào** cho phép chuyển từ thử nghiệm sang một lựa chọn chính thức trong dự án?
4. **Ai có thẩm quyền tuyên bố tính năng Java đã final?** Đây là quyết định về trạng thái JEP/JDK, không phải do nhóm ứng dụng tự đặt tên.

Bài thuộc chương **Tính năng thử nghiệm có kiểm soát** của module **JAVA_VERSION_JAVA27 — Java 27 và các kiến thức liên quan**. Theo yêu cầu chỉ sử dụng kiến thức **còn áp dụng hiện nay**, mã nền tảng trong bài **chỉ dùng Java SE 27 API ổn định**; những cờ preview/incubator chỉ xuất hiện trong **hướng dẫn chạy thí nghiệm tách biệt**, không phải cấu hình production mặc định.

> **Nguyên tắc:** một thí nghiệm có giá trị khi có **giả thuyết**, **đường chuẩn**, **phạm vi cô lập**, **tiêu chí đo**, **quy tắc dừng** và **quyền quay lại**. “Chạy nhanh hơn trên laptop một lần” chưa đủ để đưa tính năng vào sản phẩm.

## 1. Phân biệt stable, preview, incubator và thí nghiệm nội bộ

| Nhóm | Ai xác định trạng thái? | Mức ổn định | Cách tiếp cận |
| --- | --- | --- | --- |
| **Java SE final/permanent** | Java SE/JDK specification và JEP đã được phát hành chính thức | Có các cam kết tương thích của nền tảng | Có thể đánh giá đưa vào mainline theo compatibility/support policy |
| **Preview language/API** | JDK của release hiện tại và JEP tương ứng | Đã được thiết kế/triển khai đầy đủ để lấy phản hồi nhưng **chưa vĩnh viễn** | Chỉ dùng ở module/runner thí nghiệm, bật opt-in rõ ràng |
| **Incubating API/module** | JEP và module JDK được đánh dấu incubating | API có thể thay đổi lớn hoặc bị rút | Chỉ dùng trong môi trường đo đạc/tách biệt, không mặc định cho sản phẩm |
| **Thí nghiệm nội bộ** | Nhóm dự án | Phụ thuộc vào contract của nhóm; có thể sử dụng hoàn toàn stable Java API | Có feature flag, owner, kết quả đo và tiêu chí chấp nhận |
| **Experimental VM/diagnostic option** | JDK/tooling docs cho từng cờ | Có thể đòi opt-in và khác theo bản JVM | Chỉ bật trong test JVM khi hiểu chính xác tác dụng |

**Không đánh đồng:** “thí nghiệm nội bộ” là **cách làm việc của đội ngũ**, còn “preview/incubator” là **trạng thái tính năng của JDK**. Một thuật toán mới dùng `List` và `ExecutorService` ổn định vẫn có thể là thí nghiệm nội bộ; ngược lại, một API preview không trở nên final chỉ vì nhóm đã benchmark thành công.

### 1.1. Các tính năng còn chưa final ở Java 27

Theo tài liệu **Oracle Java SE 27**, tại bản phát hành Java 27 có các ví dụ:

| Tính năng | Trạng thái trong JDK 27 | Tham chiếu | Hướng thí nghiệm phù hợp |
| --- | --- | --- | --- |
| **Primitive Types in Patterns, instanceof, and switch** | **Fifth Preview** | **JEP 532** | Đánh giá tính rõ ràng, tính đúng đắn của pattern matching |
| **Lazy Constants** | **Third Preview** | **JEP 531** | So sánh chi phí khởi tạo lười, cấu trúc state, race/initialization |
| **Structured Concurrency** | **Seventh Preview** | **JEP 533** | Đánh giá vòng đời task, lỗi/hủy, độ rõ ngữ nghĩa |
| **PEM Encodings of Cryptographic Objects** | **Third Preview** | **JEP 538** | Đánh giá mapping/round-trip, tương thích khóa/chứng chỉ |
| **Vector API** | **Twelfth Incubator** | **JEP 537**, `jdk.incubator.vector` | Benchmark SIMD trên nhiều CPU/kiểu dữ liệu |

Danh sách nhằm **xác định trạng thái hiện hành**, không phải khuyến nghị sử dụng các API đó trong sản phẩm. Có thể có thêm thay đổi final khác trong Java 27; đừng suy ra mọi tính năng mới đều preview. Mỗi lần nâng JDK, hãy kiểm tra **JEP của release**, Javadoc `Preview API` và module được gắn nhãn incubating.

### 1.2. Ví dụ một tính năng đã final

**Virtual threads** đã là tính năng chính thức từ **Java 21** (JEP 444). Trong Java 27, `Executors.newVirtualThreadPerTaskExecutor()` là API ổn định. Một thí nghiệm thay platform threads bằng virtual threads trong hệ thống nội bộ là **thí nghiệm sản phẩm sử dụng tính năng final**, không phải thử preview API.

Điều này tạo sự phân biệt quan trọng: điều kiện Java trở thành *final* đã được đáp ứng, nhưng nhóm vẫn phải đo scalability, memory, request latency và giới hạn database trước khi chuyển implementation đó thành đường mặc định.

## 2. Điều kiện opt-in của preview và incubator

### 2.1. Preview: phải dùng đúng release

Để biên dịch mã **sử dụng preview feature của JDK 27**, dùng `javac` của JDK 27 cùng:

```text
javac --enable-preview --release 27 -d out-experiment PreviewExample.java
```

Chạy mã phụ thuộc preview trên JDK 27:

```text
java --enable-preview -cp out-experiment PreviewExample
```

`PreviewExample.java` là tên ví dụ dành cho **mã đã viết trong nhánh thí nghiệm**; các lệnh không yêu cầu người học sao chép một preview API vào source chính. Theo tài liệu Oracle, `--enable-preview` của compiler kết hợp với `--release 27` hoặc `--source 27`, **không** dùng `--release 21 --enable-preview` để thử tính năng preview của Java 27.

Những điểm dễ bỏ sót:

- Preview **bị tắt theo mặc định**; compiler/runtime không tự cho phép chỉ vì cài JDK 27.
- `--enable-preview` **không bật chọn lọc từng preview feature** của cùng release. Do đó muốn cô lập chỉ một thử nghiệm, phải cô lập code/build/process, không dựa riêng vào flag.
- Các class file **phụ thuộc preview feature** có thể mang version **71.65535** (major 71 của Java 27, minor `65535`), gắn với đúng release. JVM của **release khác** không đảm bảo tải được, kể cả khi bật preview.
- Việc nâng từ JDK 27 lên JDK 28 không bảo đảm mã preview cũ compile/chạy nguyên trạng; API/syntax có thể thay đổi hoặc biến mất.
- Nếu project cần hỗ trợ nhiều Java runtimes, **không để artifact phụ thuộc preview lọt vào thư viện dùng chung**.

Kiểm tra class-file version khi cần:

```text
javap -verbose -classpath out-experiment PreviewExample
```

Tìm `major version` và `minor version`; **không** sử dụng một phép quét class-file duy nhất làm chứng nhận toàn bộ code không tham chiếu preview API. Kết hợp kiểm tra dependency/API với compile **không bật** preview cho mainline.

### 2.2. Incubator: module riêng, flag khác preview

Java 27 Vector API nằm trong **incubating module**:

```text
jdk.incubator.vector
```

Mã *thí nghiệm* sử dụng module này cần khai báo module khi biên dịch/chạy:

```text
javac --add-modules jdk.incubator.vector -d out-vector VectorExperiment.java
java --add-modules jdk.incubator.vector -cp out-vector VectorExperiment
```

Không thay `--add-modules jdk.incubator.vector` bằng `--enable-preview`: đó là **hai cơ chế khác nhau**. `VectorExperiment.java` là tên file minh họa cho một thí nghiệm chuyên biệt, không phải file có sẵn trong bài.

**Cảnh báo:** module incubator không có cam kết tương thích dài hạn. Nếu một module biến mất hoặc đổi API ở JDK mới, nhóm phải cập nhật/bỏ prototype; không để ứng dụng chính bị phụ thuộc vào module chỉ phục vụ nghiên cứu.

### 2.3. Preview khác enable-native-access

Một số Java APIs ổn định vẫn có các **restricted operations** yêu cầu cấu hình quyền riêng, ví dụ native access. Tùy chọn `--enable-native-access` **không phải** tên khác của `--enable-preview`. Không bật tất cả flag “cho chắc”: mỗi flag có mô hình quyền, rủi ro và phạm vi khác nhau.

## 3. Thiết kế thí nghiệm từ giả thuyết có thể bác bỏ

Một thí nghiệm tốt phải xác định cả **lợi ích dự đoán** và **điều kiện khiến ta kết luận nó không đáng dùng**.

Mẫu mô tả:

```text
Hypothesis:
  Thay cách điều phối các task độc lập bằng một hướng mới
  sẽ giảm p99 request latency >= 15% tại tải 500 req/s.

Baseline:
  Implementation đang dùng, ổn định trên Java 27.

Candidate:
  Một adapter thí nghiệm, tách khỏi artifact production.

Constraints:
  Kết quả nghiệp vụ giống nhau.
  Error rate không tăng quá ngưỡng đã công bố.
  Không rò rỉ task, không làm tăng DB concurrency vượt quota.
  CPU/RSS trong ngân sách.

Experiment:
  Cùng JDK build, workload, dữ liệu, CPU quota, GC, network conditions.
  Nhiều lần lặp, warmup và thu metrics.

Decision:
  Giữ nghiên cứu / dừng / chờ JDK final / phát triển stable fallback.
```

### 3.1. Bốn loại giả thuyết thường gặp

| Loại | Câu hỏi | Số liệu/cách kiểm tra |
| --- | --- | --- |
| **Tính đúng đắn** | Candidate có tạo cùng kết quả và side effects hợp lệ? | Differential tests, property-based tests, fuzzing, invariants |
| **Hiệu năng** | Thao tác có nhanh hơn hoặc giảm tài nguyên không? | Throughput, p50/p95/p99, CPU/op, bytes/op, GC pressure |
| **Chất lượng thiết kế** | Code có dễ hiểu/ít lỗi hơn không? | Review checklist, lỗi cancellation, thời gian sửa đổi, coverage |
| **Vận hành** | Triển khai, rollback, security, observability có an toàn? | Canary criteria, failure injection, dependency audit, runbook |

Một API giúp source code ngắn hơn nhưng tăng lỗi timeout hoặc khó vận hành **không mặc nhiên là cải tiến**. Ngược lại, một tính năng giảm tail latency nhưng tăng CPU có thể đáng chọn khi SLO latency quan trọng hơn throughput, **nếu** CPU budget cho phép.

## 4. Cô lập theo source, dependency, artifact và process

Chỉ thêm `if (experimental)` vào code rồi gọi là “cô lập” thường chưa đủ. Mức cô lập phải phù hợp rủi ro.

### 4.1. Cấu trúc project đề xuất

```text
java27-workspace/
├── core-stable/
│   ├── src/main/java/...        (chỉ Java SE 27 final)
│   └── src/test/java/...
├── experiments/
│   ├── structured-scope-jdk27/
│   │   ├── src/main/java/...    (preview, JDK27 only)
│   │   └── src/test/java/...
│   ├── vector-jdk27/
│   │   ├── src/main/java/...    (incubator)
│   │   └── src/test/java/...
│   └── BENCHMARK_SPEC.md        (thông số/thước đo)
└── distribution/
    └── stable-artifact-only/
```

Đây là **sơ đồ minh họa**, không phải yêu cầu thay đổi file ngoài assignment này. Những quy tắc cần áp dụng:

1. `core-stable` **không import** `StructuredTaskScope` preview, `LazyConstant` preview hay `jdk.incubator.vector`.
2. Chỉ module nghiên cứu khai báo flags/dependencies thí nghiệm.
3. Build phát hành mặc định **không phụ thuộc** module nghiên cứu, kể cả transitive dependency.
4. Không public-export các kiểu preview qua API của `core-stable`.
5. Mã và test của prototype có owner, branch, expiry date và một lối loại bỏ rõ.
6. Không ghép preview classes vào thư viện mà hệ thống khác tải theo classpath “cho tiện”.

### 4.2. Tách process/container cho tính năng chưa final

Do `--enable-preview` cho phép preview features trên **toàn JVM**, không thể chỉ dùng một class loader hoặc một biến feature flag để bảo đảm process chính không bị ảnh hưởng về trạng thái enablement.

Nếu cần thử tính năng JDK preview trên workload gần thật, ưu tiên:

```text
Production process (Java 27, không --enable-preview)
        │
        ├─ nhận request thật
        ├─ đường xử lý stable
        └─ xuất dữ liệu đã ẩn danh/giới hạn
                         │
                         ▼
Isolated experiment process / container
 (Java 27 --enable-preview hoặc --add-modules)
                         │
              chạy workload tái tạo
                         │
              chỉ xuất metrics/báo cáo
                         ▼
                  Bảng so sánh
```

Trong thí nghiệm **shadow** dùng bản sao traffic, **không cho prototype thực hiện ghi** vào database/queue/payment/email thật. Dùng stub, sandbox endpoints, snapshot/test data, read-only credentials và quota riêng. Cần xem cả **privacy/legal policy**: không đưa dữ liệu cá nhân/secret vào recording hoặc bản sao request ngoài phạm vi được phép.

**Feature flag không phải security boundary.** Nếu mã preview vẫn được load vào process production, việc flag đang tắt không loại bỏ rủi ro class loading, dependency resolution hay yêu cầu runtime flag.

### 4.3. Cô lập theo mức rủi ro

| Mức | Ví dụ | Cô lập phù hợp |
| --- | --- | --- |
| Thấp | Đổi cách sắp xếp Collection bằng stable API | Branch/source set, unit tests, feature flag |
| Trung bình | Thay đổi parallel execution với stable API | Adapter + staging load test + giới hạn quota |
| Cao | Preview Structured Concurrency | JDK 27 riêng, module/artifact riêng, process không production |
| Cao | Vector incubator phụ thuộc CPU | JDK27/module riêng, benchmark đa CPU, fallback scalar |
| Rất cao | Prototype liên quan crypto/secret | Test vectors, security review, key giả, sandbox không lưu secret thật |

Với **SPECIAL_NOTE** của module, bài này không đề xuất triển khai production dựa trên preview/incubator. Canary production chỉ nên diễn ra sau khi tính năng nền tảng đã **final** hoặc khi toàn bộ candidate dùng API ổn định và qua quy trình phê duyệt thích hợp.

## 5. Định nghĩa stable boundary: mã core không biết kiểu preview

Một cách cô lập là định nghĩa interface ở **Java ổn định**, dùng các kiểu đơn giản và có hợp đồng rõ:

```java
public interface WorkCoordinator {
    Result execute(Request request)
            throws InterruptedException, WorkFailedException;
}
```

Đây là **mẫu interface**, với `Result`, `Request` và `WorkFailedException` là những kiểu nghiệp vụ cần được định nghĩa trong project thực. Cả stable implementation và candidate adapter (nếu được thử) phải trả về đúng loại kết quả và xử lý lỗi theo cùng contract.

Phân rã trách nhiệm:

```text
Stable application
    │
    ├── stable interface (không import preview API)
    │     ├── Stable adapter: ExecutorService/Future
    │     └── Experiment adapter: preview API [isolated build]
    │
    └── timeout, rollback, validation, observability contracts
```

**Cẩn thận:** adapter preview không nên vô tình được load ở production. Cần chặn ở **dependency/build artifact selection** và process/runtime configuration, không chỉ bằng `if`.

## 6. Ví dụ Java 27 tự chạy: một cổng thí nghiệm chỉ dùng stable API

Ví dụ này minh họa **cách bật/tắt candidate bằng một flag có giá trị mặc định an toàn** và **so sánh tính đúng đắn**. Candidate dùng một thuật toán khác nhưng **không** dùng preview hoặc incubator; vì vậy có thể biên dịch/chạy bình thường trên JDK 27. Khi thử một API chưa final thật sự, tách adapter đó vào một module/process khác như mục 4.

Lưu thành `ControlledExperimentDemo.java`:

```java
import java.util.Arrays;

public final class ControlledExperimentDemo {
    private ControlledExperimentDemo() {}

    interface Aggregator {
        long sum(long[] values);
    }

    // Baseline: vòng lặp trực tiếp, phép cộng có kiểm tra tràn số.
    static final class Baseline implements Aggregator {
        @Override
        public long sum(long[] values) {
            long total = 0L;
            for (long value : values) {
                total = Math.addExact(total, value);
            }
            return total;
        }
    }

    // Candidate: một cách hiện thực khác bằng stable Stream API.
    static final class Candidate implements Aggregator {
        @Override
        public long sum(long[] values) {
            return Arrays.stream(values)
                    .reduce(0L, Math::addExact);
        }
    }

    static Aggregator choose(String setting) {
        if (setting == null || setting.equals("off")) {
            return new Baseline(); // Mặc định không thử nghiệm.
        }
        if (setting.equals("on")) {
            return new Candidate();
        }
        throw new IllegalArgumentException(
                "EXPERIMENT_AGGREGATOR must be 'on' or 'off'");
    }

    static void verifyEquivalent() {
        Aggregator baseline = new Baseline();
        Aggregator candidate = new Candidate();

        long[][] samples = {
            {},
            {0L},
            {1L, 2L, 3L},
            {-8L, 5L, 3L},
            {1_000_000L, 2_000_000L},
            {Long.MAX_VALUE - 1L, 1L}
        };

        for (long[] sample : samples) {
            long expected = baseline.sum(sample);
            long actual = candidate.sum(sample);
            if (expected != actual) {
                throw new AssertionError(
                    "Mismatch: " + Arrays.toString(sample));
            }
        }

        // Cả hai phải từ chối tràn long thay vì im lặng wrap.
        long[] overflow = {Long.MAX_VALUE, 1L};
        try {
            baseline.sum(overflow);
            throw new AssertionError("Baseline missed overflow");
        } catch (ArithmeticException expected) {
            // Hợp đồng được giữ.
        }
        try {
            candidate.sum(overflow);
            throw new AssertionError("Candidate missed overflow");
        } catch (ArithmeticException expected) {
            // Hợp đồng được giữ.
        }
    }

    public static void main(String[] args) {
        verifyEquivalent();
        Aggregator selected = choose(
            System.getenv("EXPERIMENT_AGGREGATOR"));

        long[] input = {10L, 20L, 30L, 40L};
        System.out.println("Result = " + selected.sum(input));
        System.out.println("Correctness checks = PASS");
    }
}
```

Biên dịch và chạy trên JDK 27 **không cần flag preview**:

```text
javac --release 27 ControlledExperimentDemo.java
java ControlledExperimentDemo
```

Đầu ra kỳ vọng khi không đặt biến môi trường:

```text
Result = 100
Correctness checks = PASS
```

Có thể thử candidate bằng biến môi trường `EXPERIMENT_AGGREGATOR=on` theo cách đặt environment của shell/CI; chạy không có biến sẽ chọn baseline.

**Giới hạn cố ý của ví dụ:**

- Không có lời khẳng định Stream nhanh hơn vòng lặp. **Phải benchmark**.
- Mẫu input là bước kiểm tra nhỏ, không thay thế property-based/randomized tests.
- Với các giá trị âm/dương, `Math.addExact` có thể báo overflow ở tổng trung gian dù tổng toán học cuối cùng nằm trong khoảng long; cả hai hiện thực ở ví dụ này cộng **theo cùng thứ tự**.
- Flag này chỉ thể hiện **điều phối một candidate ổn định**. Nó **không** làm lớp preview an toàn khi nhúng vào main artifact.
- Trong dịch vụ thật, không dùng environment flag có thể thay đổi tùy tiện làm cơ chế phân quyền; phải có release owner, configuration audit và fallback policy.

## 7. Differential testing: đúng trước khi nhanh

Hai implementation chỉ nên được so sánh hiệu năng khi **hợp đồng nghiệp vụ tương đương**. Các nhóm test cần thiết:

### 7.1. Golden tests

Chuẩn bị input/output đã được kiểm chứng: empty input, giá trị biên, Unicode, null policy, timezone, overflow, dữ liệu duplicate, thứ tự ổn định, lỗi ngoại lệ.

```text
Given   : input X, điều kiện C
Baseline: output Y, trạng thái S
Candidate:
  output phải là Y (hoặc nằm trong tolerance được xác định)
  trạng thái cũng phải thỏa invariant I
```

Với thuật toán số thực, không luôn dùng `==` cho `double`; cần policy về absolute/relative tolerance, `NaN`, infinity, thứ tự cộng và tính tái lập. Với tính toán tiền tệ cần xem độ chính xác, `BigDecimal`/minor units và luật làm tròn.

### 7.2. Property-based, randomized và fuzz tests

Sinh nhiều trường hợp đầu vào theo miền hợp lệ:

- Danh sách rỗng/một phần tử/rất dài.
- Giá trị min/max, negative/positive, trường hợp overflow.
- Dữ liệu lặp, thứ tự đảo, data skew.
- Concurrent requests, timeouts và task bị cancel giữa chừng.
- Bất thường network/DB, partial failure, retry.
- Input lỗi phải được cả hai đường xử lý **từ chối đúng kiểu**.

Nếu candidate thay đổi error semantics, hãy ghi rõ đó là **thay đổi hợp đồng**, không coi là cải thiện hiệu năng thuần túy.

### 7.3. Failure injection

Với thí nghiệm concurrency:

```text
Task A success, Task B failure
Task A blocks forever / deadlock simulation
Caller interrupted while waiting
One task timeout, another still running
External service slow, retry backlog
Partial result and cleanup
Request cancelled before submit completes
Shutdown while tasks remain active
```

Đo cả số task còn chạy sau cancellation, thời gian cleanup, rò rỉ connection và side effects đến muộn. Chỉ nhìn p99 latency của case thành công dễ bỏ qua rủi ro lớn nhất của thay đổi concurrency.

## 8. Chọn thước đo đúng: nhanh hơn ở đâu?

Trước benchmark, phải chọn **đơn vị công việc** và **mục tiêu tối ưu**.

| Chỉ số | Đơn vị | Phù hợp khi |
| --- | --- | --- |
| **Throughput** | ops/s, requests/s, MiB/s | Batch, data processing, khả năng phục vụ |
| **Mean latency** | ms/op | Hiểu chi phí trung bình, chưa nói đủ về đuôi |
| **p95/p99 latency** | ms/request | Service có tail-latency SLO |
| **CPU cost** | CPU-ms/op, % CPU tại cùng throughput | Hiệu quả tài nguyên/chi phí |
| **Allocation rate** | MiB/s, bytes/op | Churn, GC pressure |
| **GC pause distribution** | ms/event và pause frequency | Đánh giá tác động bộ thu gom |
| **RSS/heap/native memory** | MiB/GiB | Container memory budget |
| **Error/timeout/cancel rate** | % hoặc events/1000 req | Độ tin cậy |
| **Startup/warmup time** | ms/s | CLI, serverless, short-lived jobs |
| **Artifact size** | MB | Packaging, cold-start, truyền tải |

### 8.1. Tính mức cải thiện

Với throughput, giá trị lớn hơn thường tốt hơn:

```text
throughput uplift (%)
  = (candidateOpsPerSec - baselineOpsPerSec)
    / baselineOpsPerSec × 100
```

Ví dụ **giả định**, không phải kết quả đã chạy:

```text
Baseline  : 8.000 ops/s
Candidate : 9.200 ops/s
Uplift    : (9200 - 8000) / 8000 × 100 = +15%
```

Với latency, giá trị **nhỏ hơn** thường tốt hơn:

```text
latency reduction (%)
  = (baselineLatency - candidateLatency)
    / baselineLatency × 100
```

Ví dụ minh họa p99 từ `240 ms` xuống `192 ms`: giảm `20%`. Không nên gọi đó là “tăng 20% throughput”: hai thước đo khác nhau và không tỉ lệ nghịch trong mọi workload.

### 8.2. Đo trade-off đa chiều

| Đổi mới | Lợi ích kỳ vọng | Bất lợi có thể có |
| --- | --- | --- |
| SIMD/Vector | Tăng throughput trên CPU có instruction phù hợp | Lợi ích thấp trên input nhỏ, chi phí chuyển đổi, CPU-specific |
| Structured concurrency | Vòng đời/cancellation dễ diễn giải hơn | API preview, migration changes, behavior differences |
| Lazy initialization | Giảm startup hoặc eager allocation | Truy cập lần đầu chậm, contention/lỗi khởi tạo |
| Thay scheduling | Giảm latency một loại task | Tăng CPU, connection concurrency hoặc tail latency |
| Thay parser/encoding | Giảm alloc hoặc thời gian parse | Khác semantics, lỗi bảo mật/compatibility |

Không có một chỉ số duy nhất để đưa ra quyết định. Hãy ưu tiên SLO, correctness và rủi ro; sau đó xem mức cải thiện hiệu năng có đủ **ý nghĩa thực tế** hay không.

## 9. Benchmark JVM: đo đúng trước khi diễn giải

JVM có JIT, adaptive compilation, garbage collection và nhiều yếu tố runtime khác. Chạy `System.nanoTime()` một lần quanh một vòng lặp rồi so thời gian **không phải** microbenchmark đáng tin cậy.

### 9.1. Các yếu tố phải kiểm soát

- **Warmup:** JIT cần thời gian để compile/tối ưu hot paths.
- **Dead-code elimination:** phép tính không được sử dụng có thể bị tối ưu bỏ.
- **Constant folding:** input là hằng số có thể khiến chương trình “đo” một kết quả đã được tính trước.
- **Escape analysis:** object allocation có thể bị loại bỏ hoặc thay thế.
- **GC và allocation:** khác nhau giữa các trường hợp test, cần log/profile.
- **CPU throttling/thermal:** tần số CPU, quota container, noisy neighbor ảnh hưởng lớn.
- **OS/architecture:** Vector API đặc biệt nhạy với CPU SIMD support.
- **Dependency/JDK builds:** cùng tên Java 27 nhưng patch/vendor/JIT flags có thể khác.
- **Dataset:** số phần tử, kiểu phân phối, khả năng cache hit/miss quyết định kết quả.
- **Measurement bias:** chạy candidate sau baseline mà không hoán đổi thứ tự có thể gây drift.

### 9.2. Sử dụng JMH khi đo microbenchmark

**JMH (Java Microbenchmark Harness)** là dự án benchmark được duy trì trong hệ sinh thái OpenJDK, không phải API tích hợp sẵn trong Java SE. Sử dụng một phiên bản JMH được công cụ build hỗ trợ; cấu hình dependency/annotation processor theo hướng dẫn của JMH.

Ví dụ JMH so sánh **hai thuật toán dùng stable API**, không dùng preview:

```java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 10)
@Fork(3)
public class AggregationBenchmark {
    @Param({"32", "1024", "16384"})
    public int length;

    private long[] data;

    @Setup(Level.Trial)
    public void setup() {
        data = new long[length];
        for (int i = 0; i < data.length; i++) {
            data[i] = i % 100;
        }
    }

    @Benchmark
    public long baseline() {
        long total = 0L;
        for (long value : data) {
            total = Math.addExact(total, value);
        }
        return total;
    }

    @Benchmark
    public long candidate() {
        return Arrays.stream(data).reduce(0L, Math::addExact);
    }
}
```

Đoạn code **cần JMH dependencies** và runner JMH theo tài liệu chính thức; nó không biên dịch chỉ với JDK thuần. JMH tiêu thụ kết quả trả về để giảm rủi ro phép tính bị loại bỏ; `@Fork` chạy trên các JVM riêng để giảm nhiễu do state của quá trình đo.

**Không kết luận trước** candidate nhanh hơn. Với một vòng lặp cộng số đơn giản, cách dùng stream có thể **chậm hơn**; chính việc đo mới quyết định.

### 9.3. Microbenchmark không thay end-to-end load test

Một cải thiện `30% ns/op` trong hàm xử lý nhỏ chưa chắc giảm response latency nếu thao tác đó chỉ chiếm `2%` tổng thời gian request. Vì vậy cần:

1. Microbenchmark để xác định performance của cấu phần.
2. Load test/soak test service để đo request/s, p99, error rate và resource footprint.
3. Profiling JFR/JMC để xác nhận bottleneck có thực sự chuyển dịch.
4. Kịch bản failure/cancellation để kiểm chứng đường không thành công.

Không nâng một candidate thành mặc định chỉ dựa trên microbenchmark đẹp.

## 10. Thu thập metrics với JFR, GC log và khả năng quan sát

Java 27 có **Java Flight Recorder (JFR)**, unified GC logging và các công cụ như `jcmd`. Các công cụ này giúp quan sát nguyên nhân chứ không chỉ thu được một số “nhanh hơn”.

Ví dụ một ứng dụng thí nghiệm chạy tối đa một phút:

```text
java -XX:StartFlightRecording=duration=60s,filename=experiment.jfr,settings=profile -Xlog:gc:file=experiment-gc.log:time,uptime,level,tags -cp out-experiment ExperimentRunner
```

Đây là **mẫu lệnh**, `ExperimentRunner` cần được xây trong workspace thí nghiệm. Nếu runner dùng preview API, phải bổ sung `--enable-preview`; nếu dùng incubator, thêm `--add-modules` thích hợp. Không bật các flag đó một cách vô điều kiện cho production.

Kiểm tra recording:

```text
jfr summary experiment.jfr
jfr print --categories GC experiment.jfr
```

Với service đang chạy, `jcmd` có thể tạo recording theo policy:

```text
jcmd <PID> JFR.start name=controlled settings=profile duration=60s filename=controlled.jfr
```

Cần quyền quan sát process và cân nhắc overhead/lưu trữ. JFR recording có thể chứa stack traces, class names, endpoint metadata hoặc thông tin nhạy cảm tùy event/settings; dùng chính sách redaction và quyền truy cập phù hợp.

### 10.1. Bảng thu thập có tính lặp lại

| Metadata | Baseline | Candidate |
| --- | --- | --- |
| Commit và JDK vendor/update | Ghi cụ thể | Ghi cụ thể |
| Flags/GC/heap/container quota | Giữ nguyên hoặc ghi khác biệt cố ý | Tương đương |
| OS/CPU architecture | Cố định | Cố định |
| Dataset/traffic seed | Cùng input | Cùng input |
| Warmup/measurement/forks | Định nghĩa trước | Giống baseline |
| Median và confidence interval | Có dữ liệu | Có dữ liệu |
| p95/p99 end-to-end latency | Có dữ liệu | Có dữ liệu |
| CPU/op, alloc/op, RSS | Có dữ liệu | Có dữ liệu |
| Error/cancellation/timeout | Có dữ liệu | Có dữ liệu |
| Regression/correctness suite | PASS/FAIL | PASS/FAIL |

Một run duy nhất thiếu số mẫu và điều kiện môi trường **không đủ** để báo cáo nâng cấp. Nếu hệ thống có đợt tải không ổn định, nên chạy nhiều lần và báo biến động, ví dụ median ± khoảng tin cậy theo phương pháp thống kê đã xác định.

## 11. Thiết kế A/B, shadow traffic và ngăn tác dụng phụ

Có thể thử candidate trên **dữ liệu đại diện nhưng được kiểm soát**:

### 11.1. Offline replay

Thu một tập dữ liệu test đã cho phép sử dụng, loại bỏ hoặc biến đổi dữ liệu nhạy cảm, sau đó chạy **baseline và candidate trên cùng snapshot**.

Ưu điểm: dễ tái lập, không ảnh hưởng người dùng. Hạn chế: không phản ánh mọi network jitter, concurrency hay trạng thái hệ thống thật.

### 11.2. Shadow traffic

Một worker phụ nhận bản sao request **chỉ để đọc/đo**, không phản hồi cho user và không tạo side effects ở môi trường thật.

```text
                 Real request
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
Stable production         Shadow experiment
(read/write allowed)      (read-only/sandbox)
          │                     │
     response user          metrics only
```

Nếu request là lệnh thanh toán hoặc gửi email, **không replay nguyên trạng** tới endpoint thật. Cần mock, sandbox endpoints hoặc chỉ replay phần computation không gây side effect.

Với preview/incubator, shadow execution nên đặt trong **process/container nghiên cứu tách khỏi production**, không đơn giản load preview JAR vào process thật.

### 11.3. Canary chỉ sau khi đã đủ điều kiện triển khai

Khi implementation đã dựa trên **API final** và vượt qua security/compatibility review, có thể cân nhắc rollout production có giới hạn:

```text
0% (off) -> 1% -> 5% -> 25% -> 100%
              │
              └─ quan sát SLO và có kill switch
```

Đây là **lộ trình minh họa**, không phải tỷ lệ áp dụng cho mọi sản phẩm. Đặt thời gian quan sát, điều kiện rollback và phân bố traffic cho từng giai đoạn. Nếu latency p99, error rate, CPU hoặc dữ liệu nghiệp vụ vượt ngưỡng, tự động hoặc thủ công quay lại baseline theo runbook.

## 12. Tiêu chí để công nhận lợi ích có ý nghĩa

Trước khi bắt đầu, viết rõ **acceptance gates**. Nếu chưa đặt tiêu chí, rất dễ lựa chọn chỉ số đẹp nhất sau khi xem kết quả.

Ví dụ **ngưỡng giả định cho một service**, phải hiệu chỉnh theo SLO thực:

| Cổng | Ngưỡng minh họa | Phương pháp |
| --- | --- | --- |
| **Correctness** | 100% critical tests PASS; không có sai lệch nghiệp vụ chưa giải thích | Golden tests, property-based, integration tests |
| **Performance** | p99 giảm ít nhất 15% **hoặc** throughput tăng ít nhất 15% theo mục tiêu đã đăng ký | Load test và nhiều vòng JMH khi phù hợp |
| **CPU budget** | CPU/op không tăng quá 5% | Profile cùng workload |
| **Memory budget** | Peak RSS tăng không quá 10%; không tăng leak | GC/JFR/soak test |
| **Reliability** | Error rate/cancellation không kém baseline theo SLO | Fault injection, load test |
| **Compatibility** | Chạy trên runtime/OS/CPU đã công bố | CI matrix và smoke tests |
| **Observability** | Có tracing/metrics và cách phân biệt candidate | Dashboard, alarm/runbook |
| **Rollback** | Có thể tắt/triển khai lại bản cũ theo thời hạn của tổ chức | Diễn tập rollback |
| **Upstream status** | Tính năng JDK đã được phát hành **final**, nếu dùng preview/incubator trước đó | JEP/Javadoc/JDK release notes |

Không dùng `15%` hoặc `5%` như **chuẩn ngành**: đây chỉ là các con số để minh họa cách ghi nhận acceptance criteria trước đo. Với module crypto, bảo mật/tính đúng đắn thường quan trọng hơn bất kỳ cải thiện tốc độ nào.

### 12.1. Số liệu phải đi với biến thiên và kích thước mẫu

Giả sử qua nhiều lần chạy:

```text
Thông lượng đo qua các lần chạy:
  8.0k, 8.1k, 7.9k, 8.0k ops/s

Experimental:
  8.2k, 8.3k, 8.0k, 8.1k ops/s
```

Dù trung bình candidate cao hơn một chút, chênh lệch **có thể không đáng kể so với nhiễu**. Cần báo khoảng tin cậy/độ biến động, test dưới workload đại diện, và lặp lại với môi trường kiểm soát trước khi kết luận.

**Tránh p-hacking:** không liên tục thay dataset, warmup, metric và ngưỡng tới khi có một kết quả “đạt”. Ghi lại tất cả run, kể cả run không như kỳ vọng.

## 13. Hai cổng quyết định: Java final và sản phẩm mainline

“Chuyển sang tính năng chính thức” có **hai nghĩa khác nhau**:

1. **Nền tảng Java:** tính năng được OpenJDK/Java SE công bố **final/permanent** trong một release qua JEP/spec/Javadoc. Team ứng dụng **không thể tự làm** một preview API trở thành final.
2. **Dự án:** sau khi upstream đã final và candidate thỏa acceptance criteria, team mới quyết định chuyển code từ prototype sang **đường xử lý mặc định**.

```text
Nghiên cứu
   │
   ▼
Thử nghiệm cô lập [preview/incubator có thể tồn tại]
   │
   ├── thiếu lợi ích / sai semantics -> STOP / REWORK
   ├── API vẫn preview/incubator    -> HOLD, tiếp tục theo dõi JEP
   └── API đã final                 -> REASSESS theo bản JDK final
                                        │
                                    chạy test/benchmark lại
                                        │
                             ┌──────────┴───────────┐
                             ▼                      ▼
                         FAIL -> STOP        PASS -> CANDIDATE
                                                       │
                                         rollout có kill switch
                                                       │
                                                 MAINLINE
```

**Điểm quan trọng:** khi một preview API được final, API cuối **có thể khác** bản preview từng thử. Phải cập nhật code theo Javadoc/spec chính thức và chạy lại correctness/performance/security tests. Kết quả benchmark trên bản preview **không chuyển nguyên xi** thành bằng chứng cho bản final.

### 13.1. Những tín hiệu nguồn cần xác minh

- JEP của tính năng: trạng thái **Preview/Incubator/Final** trong từng release.
- Java SE release notes và API documentation của release target.
- Các annotation/note `PREVIEW` trong Javadoc, `preview-list.html`.
- Tên module incubator còn tồn tại và trạng thái API.
- Compatibility matrix của build plugins/IDE/static analysis/bytecode tools.
- Chính sách hỗ trợ của tổ chức đối với JDK release và cadence cập nhật.

Đừng suy luận “đã preview nhiều lần nên chắc final ở JDK tiếp theo”. Một tính năng có thể được preview thêm, thay đổi hoặc rút đi.

### 13.2. Trạng thái nội bộ đề xuất

| Trạng thái | Ý nghĩa | Có được đưa vào sản phẩm mặc định? |
| --- | --- | --- |
| **PROPOSED** | Có ý tưởng, hypothesis, owner | Không |
| **ISOLATED** | Prototype/runner riêng, không nằm main artifact | Không |
| **MEASURED** | Đã có correctness + benchmark reproducible | Không |
| **HOLD_UPSTREAM** | Có lợi nhưng JDK vẫn preview/incubator | Không |
| **READY_FOR_STABLE_REVIEW** | JDK final, code đã migrate/test lại | Chưa, đợi review |
| **CANARY** | Rollout có giới hạn, kill switch, observability | Tùy approval và policy |
| **MAINLINE** | Đường xử lý mặc định, có owner và test | Có |
| **RETIRED** | Không đạt, quá hạn hoặc được thay thế | Không |

Đây là **quy trình đề xuất**, không phải trạng thái chính thức do JDK quy định.

## 14. Mẫu decision record có thể tái sử dụng

```text
Experiment ID: EXP-027-STRUCTURED
Owner: Platform Team
JDK: 27.x (vendor + build)
Upstream status: Structured Concurrency, JEP 533, seventh preview

Hypothesis:
  Cải thiện cancellation semantics và tail latency của fan-out requests.

Baseline:
  Stable ExecutorService + Future + explicit deadline/cancel.

Candidate:
  Structured concurrency implementation trong isolated runner.

Correctness:
  Same response schema, same timeout policy, same external side effects.
  Tests: success, partial failure, interrupt, timeout, shutdown.

Metrics:
  p50/p95/p99, rps, CPU/op, alloc/op, open connections,
  task lifetime after cancellation, error rate.

Control:
  Same dataset, same CPU quota, same JDK build/GC/heap,
  warmup, >= N repeated runs, JFR/JMH methodology.

Decision criteria:
  No correctness/security regression.
  Measured benefit meets pre-registered threshold.
  Upstream feature FINAL before production adoption.
  Code review + rollback test PASS.

Status: HOLD_UPSTREAM / REWORK / REJECT / APPROVE_AFTER_FINAL
Review date: next JDK feature release or project milestone
Rollback owner: Platform Team
```

Khi gửi báo cáo cho người ra quyết định, không chỉ ghi “candidate nhanh hơn 20%”. Phải ghi **mốc đo**, **bộ dữ liệu**, **confidence/biến thiên**, **chi phí CPU/bộ nhớ**, **hạn chế** và **upstream feature status**.

## 15. Case study A: Structured Concurrency so với ExecutorService

Trong Java 27, `StructuredTaskScope` vẫn là **preview API** (**JEP 533**). Mẫu đánh giá phù hợp là một nghiệp vụ fan-out: một request cần đồng thời đọc hồ sơ và tồn kho từ hai dịch vụ.

Baseline có thể dùng API đã final:

```java
import java.time.Duration;
import java.util.concurrent.*;

public class StableFanOut {
    record Result(String profile, String stock) {}

    static Result fetch()
            throws InterruptedException, ExecutionException, TimeoutException {

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            Future<String> profile = executor.submit(() -> {
                Thread.sleep(Duration.ofMillis(20));
                return "profile";
            });
            Future<String> stock = executor.submit(() -> {
                Thread.sleep(Duration.ofMillis(30));
                return "stock";
            });

            try {
                String p = profile.get(100, TimeUnit.MILLISECONDS);
                String s = stock.get(100, TimeUnit.MILLISECONDS);
                return new Result(p, s);
            } finally {
                profile.cancel(true);
                stock.cancel(true);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(fetch());
    }
}
```

Đây là **ví dụ baseline đơn giản**, dùng JDK 27 stable APIs. Hai lần `get(100ms)` không tạo **deadline chung 100ms**; trong benchmark nghiệp vụ cần dùng một monotonic deadline cho tất cả subtasks và I/O timeouts. `ExecutorService.close()` có thể còn chờ task không hợp tác, nên cũng phải xét lifecycle.

Với candidate preview:

- Cài prototype `StructuredTaskScope` **chỉ trong module thí nghiệm**.
- Biên dịch/chạy bằng `--enable-preview` của đúng JDK 27.
- Đặt chung contract input/output và deadline với baseline.
- Test việc phản hồi `InterruptedException`, xử lý một subtask lỗi, cả hai hoàn tất, timeout, caller cancel, shutdown.
- Đo task vẫn còn chạy sau request, connection usage và cancellation latency.
- Không đưa class preview vào thư viện chính cho đến khi upstream final và nhóm **review lại** API cuối.

**Một kết quả cải thiện code clarity có thể đáng ghi nhận**, nhưng nếu tail latency không cải thiện hoặc cleanup còn lỗi, không thể chỉ dựa vào cảm nhận “code đẹp hơn” để bỏ baseline.

## 16. Case study B: Vector API so với thuật toán scalar

Trong Java 27, Vector API **vẫn incubator** (**JEP 537**, module `jdk.incubator.vector`). Một prototype có thể đo một phép tính trên mảng số lớn với hardware SIMD thích hợp.

Hợp đồng đánh giá:

| Yếu tố | Phải kiểm tra |
| --- | --- |
| **Kiểu dữ liệu** | `int`, `long`, `float`, `double`; overflow/rounding policy |
| **Độ dài mảng** | Nhỏ, trung bình, rất lớn; phần đuôi không đủ vector lanes |
| **CPU** | x64/ARM64 và instruction set thực được hỗ trợ |
| **Workload** | Compute-bound hay memory-bandwidth-bound |
| **Correctness** | Kết quả bằng nhau/tolerance rõ cho floating point |
| **Performance** | Throughput, ns/op, CPU/op, alloc/op |
| **Fallback** | Scalar implementation đã được kiểm chứng |
| **Upstream state** | Không sử dụng incubator trong bản phát hành chính theo policy bài |

Đừng “đo” bằng cách chỉ chạy với input lớn trên một máy có CPU SIMD mạnh rồi kết luận mọi thiết bị sẽ tăng tốc giống nhau. Có thể:

- Input quá nhỏ khiến overhead setup lớn hơn lợi ích.
- Bottleneck là memory bandwidth, không phải phép toán.
- Vector code có sai khác float rounding do thứ tự cộng.
- Runtime/hardware không có vector instruction tương ứng, lợi ích không đạt.

Báo cáo có thể kết luận **“đáng tiếp tục đầu tư nghiên cứu”**, nhưng không đồng nghĩa **“đã final và được release”**.

## 17. Quy tắc rollback và kết thúc thí nghiệm

Mọi experiment phải có **điểm kết thúc**. Nếu không, một module thử nghiệm có thể sống nhiều năm và trở thành dependency ngầm mà không ai sở hữu.

### 17.1. Khi nào dừng sớm?

Dừng/đóng thử nghiệm nếu:

- Correctness có sai khác nghiêm trọng và không có cách kiểm soát.
- Rủi ro bảo mật hoặc dữ liệu nhạy cảm vượt chính sách.
- Không đạt lợi ích tối thiểu đã đặt ra.
- JDK/JEP đã thay đổi hoặc rút tính năng.
- Chi phí bảo trì/CI tăng hơn giá trị có thể thu được.
- Candidate chỉ tăng tốc khi benchmark giả tạo, không cải thiện workload thực.
- Owner không còn hoặc mốc review đã quá hạn.

### 17.2. Rollback trước và sau khi API final

**Trước khi final:** rollback = ngừng chạy prototype, xóa thử nghiệm khỏi distribution/test runtime được công bố, giữ báo cáo benchmark cho lần xem xét sau.

**Sau khi final và canary:** rollback = tắt candidate theo flag/đưa traffic về baseline và nếu cần redeploy bản cũ. Nếu thay đổi có migration dữ liệu, phải chuẩn bị **backward-compatible schema/dual read** hoặc kế hoạch phục hồi; một kill switch đơn giản không thể đảo ngược migration không tương thích.

### 17.3. Không làm bẩn mã production

Khi nghiên cứu kết thúc:

1. Quyết định giữ mã thí nghiệm trong repository riêng, archive hoặc xóa theo policy.
2. Loại flags không cần thiết khỏi default CI/runtime.
3. Kiểm tra dependencies không còn pull preview/incubator modules.
4. Đảm bảo stable artifact build được **không có `--enable-preview` hoặc incubator flags**.
5. Ghi lại lý do dừng/giữ, dữ liệu đo và thời điểm xem xét tiếp.

## 18. Lỗi thường gặp và cách xử lý

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “Preview đã dùng trong PoC nên xem như stable” | JEP/JDK chưa final | Giữ module cô lập, chờ upstream final |
| “Bật `--enable-preview` là chỉ bật một API” | Flag bật preview features của cả release | Cô lập bằng build/process, không chỉ flag |
| “Incubator dùng `--enable-preview`” | Incubator có module access riêng | Dùng `--add-modules` theo Javadoc |
| “Code preview Java 27 sẽ chạy được trên Java 28” | Preview class files tied to release | Recompile/migrate theo JDK mới |
| “Có flag off nên preview JAR trong production vô hại” | Class loading, dependency và JVM option vẫn có rủi ro | Không mang preview artifact vào production |
| “Microbenchmark nhanh hơn thì HTTP p99 sẽ thấp hơn” | Bottleneck khác có thể chi phối | Đo end-to-end workload |
| “Một lần `System.nanoTime()` đủ để kết luận” | JIT/GC/OS noise | JMH, warmup, forks, lặp lại |
| “Không cần baseline” | Không biết lợi ích tương đối | Giữ reference implementation |
| “Candidate khác kết quả một chút cũng được” | Có thể làm sai nghiệp vụ | Ghi tolerance/semantics rõ, test đầy đủ |
| “Vector nhanh ở CPU tôi nghĩa nhanh ở mọi máy” | Hardware-dependent | Benchmark CPU matrix và fallback |
| “JDK final thì ứng dụng tự động được phê duyệt” | Vẫn có vấn đề compatibility, SLO, bảo mật | Review/test/canary riêng |
| “Tối ưu CPU không cần xem RAM” | Candidate có thể tăng allocation/GC | Đo CPU/op, bytes/op, RSS |
| “Shadow requests có thể ghi DB thật” | Gây side effects, duplicate | Read-only/sandbox/stub |
| “Code ngắn hơn nghĩa là ít bug hơn” | Error/cancel semantics có thể xấu đi | Differential/failure tests |
| “Tính năng đã final giống hệt bản preview” | API có thể đổi khi final | Port và đo lại |
| “Canary không cần rollback vì traffic ít” | Vẫn có thể gây side effects | Kill switch/runbook và giới hạn tác động |
| “Dừng thử nghiệm thì không cần dọn CI” | Flag/dependency có thể rò lại | Kiểm tra artifact/CI reproducibility |

## 19. Checklist trước khi chuyển một thử nghiệm vào mainline

1. **Tính năng của JDK đã final?** Xác minh JEP/spec/Javadoc **đúng Java release**; nếu vẫn preview/incubator, giữ cô lập.
2. **Đã có baseline ổn định?** Biết chức năng và behavior hiện tại.
3. **Có owner và giả thuyết đo được?** Không làm prototype vô thời hạn.
4. **Có hợp đồng correctness?** Trường hợp lỗi, null, overflow, cancellation, timeout, side effects.
5. **Có đường rollback?** Chọn stable implementation khi candidate bị tắt.
6. **Core không import preview?** Build stable phải compile không có preview/incubator flag.
7. **Dependency graph sạch?** Không có JAR module/typings chưa final đi vào artifact.
8. **Có test đa loại?** Golden, property-based, integration, fault injection, soak test.
9. **Có đo đúng workload?** Microbenchmark + end-to-end nếu cần; không dùng chỉ số chọn lọc.
10. **Đã warmup/repeat/fork?** Có kiểm soát JIT/GC và môi trường đo.
11. **Có phân tích biến thiên?** Không kết luận từ một run ngẫu nhiên.
12. **Đã đo đủ nguồn lực?** CPU, heap/RSS, allocation, GC, connection quota.
13. **Đã test trên OS/CPU/JDK matrix?** Đặc biệt quan trọng với Vector API và native integration.
14. **Có đánh giá bảo mật?** Dữ liệu shadow, secrets, crypto semantics, quyền môi trường.
15. **Đã đánh giá chi phí bảo trì?** Framework/plugin support, code clarity, docs, đào tạo.
16. **Tính năng final có khác preview?** Port và chạy lại toàn bộ test/benchmark.
17. **Ngưỡng acceptance được đăng ký trước?** Không “tối ưu” tiêu chí sau khi thấy kết quả.
18. **Rollout có quan sát và kill switch?** Canary chỉ khi policy production cho phép.
19. **Có audit trail?** Decision record, dataset, build info, kết quả và người phê duyệt.
20. **Có kế hoạch loại bỏ prototype?** Không để preview flags tồn tại vĩnh viễn.

## 20. Bài tập áp dụng

### Bài tập 1 — Viết hypothesis

Chọn một workload đọc dữ liệu hoặc xử lý mảng. Viết một hypothesis với số đo cụ thể: throughput, p99 hoặc allocations/op; một baseline, một candidate; cùng năm điều kiện kiểm soát môi trường và hai điều kiện dừng sớm.

### Bài tập 2 — Chạy mã stable với feature flag

Lưu `ControlledExperimentDemo.java` và chạy với chế độ mặc định và candidate. Bổ sung ít nhất 100 dữ liệu ngẫu nhiên và kiểm tra cả hai implementation có cùng output/exception. Giải thích vì sao phép so này **không đủ** để chứng minh candidate nhanh hơn.

### Bài tập 3 — Thiết kế benchmark JMH

Dựa trên `AggregationBenchmark`:

- So sánh ba kích thước input.
- Chạy nhiều forks/warmups/measurements.
- Báo kết quả **kèm độ biến thiên**, không chỉ số lớn nhất.
- Kết hợp đo bytes/op hoặc JFR allocation profile khi cần.
- Ghi nhận JDK build, OS/CPU và GC options.

Giải thích vì sao một candidate nhanh hơn trên mảng 16.384 phần tử vẫn có thể **không** thắng trên mảng 32 phần tử.

### Bài tập 4 — Lập quyết định cho preview Java 27

Giả sử một prototype dùng `StructuredTaskScope` (JEP 533) đã giảm p99 20% và không có correctness regression. Hiện tại trong Java 27 JEP vẫn là **preview**. Kết luận phù hợp theo policy của bài: **HOLD_UPSTREAM**, giữ mã trong nghiên cứu; theo dõi JDK release tiếp theo, và khi tính năng final phải port/test/benchmark lại.

### Bài tập 5 — Thiết kế rollback

Tưởng tượng sau khi một tính năng đã final và qua phê duyệt, rollout 5% traffic làm error rate tăng. Hãy viết quy trình dừng rollout, quay về baseline, kiểm tra side effects và lưu nguyên nhân; đừng chỉ ghi “tắt flag” nếu có schema migration.

## 21. Tài liệu tham khảo chính thức

- [Java SE 27 — Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html) — bản chất preview, biên dịch và chạy với `--enable-preview`.
- [Java SE 27 — Preview API List](https://docs.oracle.com/en/java/javase/27/docs/api/preview-list.html) — các API còn preview ở Java 27.
- [Java SE 27 — Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) — JEP 532, 531, 533, 538, 537 và trạng thái trong JDK 27.
- [Java SE 27 — javac Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — `--release`, `--enable-preview` và warnings.
- [Java SE 27 — java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — runtime flags và class loading.
- [Java SE 27 — JVMS Chapter 1](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/jvms-1.html) — preview class-file minor 65535 và tính gắn với release.
- [Java SE 27 — StructuredTaskScope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) — Javadoc xác nhận còn preview.
- [Java SE 27 — Vector API Module](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html) — module incubator và cảnh báo trạng thái.
- [OpenJDK JEP 12 — Preview Features](https://openjdk.org/jeps/12) — mục đích, yêu cầu opt-in, lifecycle.
- [OpenJDK JEP 11 — Incubator Modules](https://openjdk.org/jeps/11) — mục tiêu thử API trong incubating modules.
- [OpenJDK JEP 533 — Structured Concurrency](https://openjdk.org/jeps/533) — trạng thái preview của Structured Concurrency tại JDK 27.
- [OpenJDK JEP 537 — Vector API](https://openjdk.org/jeps/537) — trạng thái incubator và khả năng SIMD.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444) — ví dụ tính năng đã final từ Java 21.
- [OpenJDK Java Microbenchmark Harness](https://github.com/openjdk/jmh) — công cụ đo microbenchmark, warmup và forks.
- [Java SE 27 — JFR Tool](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jfr.html) — phân tích recording.
- [Java SE 27 — jcmd Tool](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html) — bắt đầu JFR recording và diagnostics.
