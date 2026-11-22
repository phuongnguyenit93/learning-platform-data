# 1.1 Chẩn đoán lúc chạy là gì và khác gì với sửa lỗi từ mã nguồn

## Mục tiêu

Sau bài này, bạn có thể giải thích **runtime diagnostics (chẩn đoán lúc chạy)** trong ứng dụng Java, phân biệt nó với việc **gỡ lỗi dựa trên mã nguồn**, chọn bằng chứng phù hợp cho một sự cố và đi từ triệu chứng đến giả thuyết có thể kiểm chứng. Hai cách tiếp cận bổ sung cho nhau; chúng không phải hai hoạt động loại trừ nhau.

## 1. Chẩn đoán lúc chạy là gì?

**Chẩn đoán lúc chạy** là quá trình thu thập, đối chiếu và phân tích bằng chứng về hành vi của một chương trình **khi chương trình đang thực thi** hoặc từ dữ liệu được ghi nhận trong thời gian thực thi. Với Java, hành vi quan sát được đến từ nhiều lớp cùng lúc:

- **Mã và bản build:** thuật toán, luồng điều khiển, bytecode, phiên bản thư viện và bản triển khai.
- **JVM:** heap, garbage collection (GC), các luồng, JIT, class loading, tham số khởi động.
- **Cấu hình và dữ liệu:** system properties, biến môi trường, feature flags, input, tải công việc.
- **Hệ thống bên ngoài:** CPU, bộ nhớ máy, mạng, cơ sở dữ liệu, dịch vụ phụ thuộc, container và giới hạn tài nguyên.

Câu hỏi trọng tâm là: **“Điều gì thực sự xảy ra trong lần chạy này, ở điều kiện này, và bằng chứng nào giải thích được hiện tượng?”**

Ví dụ: cùng một bản mã nguồn, dịch vụ có thể phản hồi nhanh trên máy phát triển nhưng chậm ở production. Sự khác biệt có thể đến từ lượng request, kích thước heap, GC, kết nối cơ sở dữ liệu, cấu hình timeout, độ trễ mạng hoặc lỗi logic chỉ xuất hiện với dữ liệu thật. Chỉ đọc mã nguồn thường không đủ để kết luận nguyên nhân.

Kết quả mong muốn của chẩn đoán không đơn thuần là “có log”, mà là **một kết luận hoặc giả thuyết có bằng chứng**, chỉ rõ ảnh hưởng, điều kiện kích hoạt, nguyên nhân đã được xác nhận hay còn nghi vấn và cách kiểm chứng biện pháp khắc phục.

## 2. Khác gì với sửa lỗi từ mã nguồn?

Ở đây, “sửa lỗi từ mã nguồn” là hướng điều tra tập trung vào câu lệnh, thuật toán, trạng thái biến, điều kiện biên và đường đi của chương trình: đọc code, viết test, dùng breakpoint, step into/over, xem call stack và sửa logic.

| Tiêu chí | Chẩn đoán lúc chạy | Gỡ lỗi/sửa lỗi dựa trên mã nguồn |
| --- | --- | --- |
| Câu hỏi đầu tiên | “Trong tiến trình đang chạy, triệu chứng xảy ra khi nào, với tải, cấu hình và tài nguyên nào?” | “Nhánh code, giá trị biến hay thuật toán nào tạo ra kết quả sai?” |
| Điểm xuất phát | Sự cố quan sát được: lỗi tăng, độ trễ tăng, treo luồng, heap tăng, crash, khác biệt môi trường | Test thất bại, kết quả sai có thể tái hiện, exception gắn với đoạn code, lỗi điều kiện/thuật toán |
| Bằng chứng thường dùng | Logs, metrics, traces, stack/thread dumps, JFR, heap histogram/dump, cấu hình, bản build | Mã nguồn, unit/integration tests, debugger, giá trị biến, assertion, stack trace |
| Phạm vi | Chương trình **cùng** JVM, OS, tài nguyên, input, tải và hệ thống phụ thuộc | Chủ yếu logic và trạng thái của chương trình; cũng có thể chạy chương trình trong debugger |
| Đầu ra | Mô tả điều kiện gây lỗi, nguyên nhân/giả thuyết được kiểm chứng, mức độ ảnh hưởng, hướng xử lý | Bản sửa code và test chứng minh hành vi đúng |

**Điểm giao nhau rất quan trọng:** debugger của IDE cũng quan sát một chương trình đang chạy; stack trace vừa là dữ liệu runtime vừa dẫn tới dòng source. Khác biệt nằm ở **câu hỏi và phạm vi bằng chứng**, không phải ở việc có chạy chương trình hay không. Một lỗi runtime cuối cùng vẫn có thể đòi hỏi sửa code; ngược lại, không phải mọi sự cố runtime đều do code sai.

Ba ví dụ giúp phân biệt:

1. Một hàm cộng nhầm phần tử vì điều kiện vòng lặp là `i <= count`: kiểm tra code, viết test và sửa điều kiện là con đường ngắn nhất.
2. Sau khi triển khai, p99 latency tăng dù commit không đổi, cùng lúc thời gian GC hoặc độ trễ database tăng: cần bằng chứng runtime để xác định nút thắt trước khi chọn sửa code, cấu hình hay hạ tầng.
3. Một `NullPointerException` xuất hiện ở production: đọc stack trace để khoanh vùng code, nhưng vẫn cần xác định input, dữ liệu hoặc thay đổi cấu hình nào làm nhánh đó xuất hiện.

## 3. Triệu chứng, tín hiệu, nguyên nhân và cách sửa là bốn thứ khác nhau

Ví dụ người dùng báo “API thỉnh thoảng mất 4 giây”:

- **Triệu chứng:** request chậm, vượt mục tiêu độ trễ.
- **Tín hiệu:** biểu đồ p95/p99 tăng, trace ghi nhận một dependency mất 3,5 giây, thread dump có nhiều luồng đang chờ I/O.
- **Giả thuyết nguyên nhân:** dependency chậm hoặc pool kết nối bão hòa.
- **Kiểm chứng và xử lý:** đối chiếu timestamp, request ID, metric dependency và pool; điều chỉnh hoặc sửa đúng nguyên nhân; đo lại dưới tải tương đương.

Không được đồng nhất “thread đang WAITING” với “deadlock”, hay thấy CPU/GC tăng rồi mặc định đó là nguyên nhân. **Tương quan theo thời gian chỉ giúp tạo giả thuyết**; cần bằng chứng bổ sung hoặc phép thử có kiểm soát để xác nhận.

Một **stack trace** cho biết đường gọi dẫn tới điểm ném exception, nhưng dòng ném exception không nhất thiết là nơi lỗi bắt đầu: input sai hoặc trạng thái không hợp lệ có thể được tạo từ bước trước đó.

## 4. Thu thập bằng chứng gì trong Java?

| Nguồn | Trả lời tốt câu hỏi nào? | Giới hạn cần nhớ |
| --- | --- | --- |
| **Application logs** (timestamp, level, request/correlation ID, stack trace) | Request nào lỗi, luồng nghiệp vụ đi tới đâu, exception gì? | Thiếu ngữ cảnh hoặc log không đồng bộ có thể gây hiểu lầm; tránh log thông tin nhạy cảm |
| **Metrics** (error rate, throughput, p95/p99, CPU, heap, GC, thread/pool) | Sự cố bắt đầu lúc nào, rộng đến đâu, thay đổi theo tải ra sao? | Metric tổng hợp không tự chỉ ra dòng code gây lỗi |
| **Distributed tracing** | Thời gian được dùng ở bước và dịch vụ nào trong một request? | Cần propagate trace context; sampling có thể bỏ sót request |
| **Thread dump / `jcmd Thread.print`** | Luồng đang RUNNABLE, BLOCKED, WAITING ở đâu; có dấu hiệu chờ khóa hay deadlock không? | Chỉ là ảnh chụp thời điểm; thường cần nhiều mẫu để thấy xu hướng |
| **JDK Flight Recorder (JFR), profiler, GC logs** | CPU được dùng ở đâu, allocation/GC và một số sự kiện JVM diễn ra thế nào? | Cấu hình thời gian ghi, chi phí quan sát và tính đại diện của mẫu đều quan trọng |
| **Heap histogram / heap dump** | Loại đối tượng nào chiếm chỗ và được giữ tham chiếu bởi đâu? | Heap dump có thể lớn và chứa dữ liệu nhạy cảm; chỉ thu khi có quyền và cần thiết |
| **Build, JDK, JVM flags, cấu hình, dependency** | Hai môi trường có thật sự chạy cùng artifact/điều kiện không? | “Cùng source” chưa chắc “cùng binary, flags, input và dependency” |

Chọn công cụ theo triệu chứng. Ví dụ: điều tra timeout bắt đầu từ error rate, latency, trace và tình trạng dependency; điều tra treo/lock bắt đầu từ thread dumps; điều tra heap tăng kéo dài bắt đầu từ biểu đồ heap sau GC, tốc độ allocation rồi mới quyết định có cần heap dump.

Nên ghi **thời điểm có múi giờ**, phạm vi ảnh hưởng, service/instance, phiên bản build và khoảng thời gian xảy ra lỗi. So sánh “trước–sau” phải giữ điều kiện đủ tương đồng về tải và input.

## 5. Ví dụ Java 17+: cùng mã nguồn, khác hành vi lúc chạy

Ví dụ sau **mô phỏng quyết định timeout** theo cấu hình và thời gian xử lý được cung cấp. Nó không thực hiện network call, không đo đồng hồ thực và không tạo timeout thật; mục đích là chứng minh phải kiểm tra giá trị **thực sự dùng ở runtime** trước khi quy lỗi cho thuật toán.

Tạo tệp `RuntimeDiagnosisDemo.java`:

```java
public class RuntimeDiagnosisDemo {
    public static void main(String[] args) {
        int timeoutMs = Integer.parseInt(
                System.getProperty("app.timeout.ms", "100"));
        int downstreamMs = Integer.parseInt(
                System.getProperty("downstream.duration.ms", "80"));

        System.out.printf("timeout=%dms, downstream=%dms%n",
                timeoutMs, downstreamMs);

        if (downstreamMs > timeoutMs) {
            System.out.println("KET_QUA=TIMEOUT");
        } else {
            System.out.println("KET_QUA=OK");
        }
    }
}
```

Biên dịch một lần bằng JDK 17 trở lên:

```bash
javac RuntimeDiagnosisDemo.java
java -Dapp.timeout.ms=100 -Ddownstream.duration.ms=80 RuntimeDiagnosisDemo
```

Stdout chính xác:

```text
timeout=100ms, downstream=80ms
KET_QUA=OK
```

Giữ nguyên tệp `.java` và tệp `.class`, chỉ thay thuộc tính JVM truyền vào:

```bash
java -Dapp.timeout.ms=100 -Ddownstream.duration.ms=180 RuntimeDiagnosisDemo
```

Stdout chính xác:

```text
timeout=100ms, downstream=180ms
KET_QUA=TIMEOUT
```

**Phân tích:** cùng mã nhưng kết quả khác vì `downstream.duration.ms` khác. Bước chẩn đoán là kiểm tra cấu hình, input và số đo runtime nào đã thay đổi; bước sửa tùy nguyên nhân có thể là chỉnh cấu hình, tối ưu dependency hoặc sửa logic xử lý timeout. Nếu chỉ mở IDE tìm một dòng “sai” trong `if` mà không đối chiếu giá trị thực tế, ta có thể sửa nhầm chỗ.

Trong dịch vụ thực, không nên dùng giá trị mô phỏng để kết luận timeout. Hãy đo độ trễ thực bằng instrumentation/trace và so với timeout của đúng client, đồng thời cân nhắc queueing, retry và deadline. Ví dụ này dùng system properties để dễ chạy và dễ tái hiện; một ứng dụng thực tế cũng cần kiểm tra tính hợp lệ của giá trị cấu hình.

## 6. Ví dụ đối lập: lỗi logic nằm trong mã nguồn

Bài toán là tính tổng **`count` phần tử đầu** của mảng. Tạo tệp `SourceLogicBugDemo.java`:

```java
public class SourceLogicBugDemo {
    static int sumFirst(int[] values, int count) {
        int sum = 0;
        for (int i = 0; i <= count; i++) {
            sum += values[i];
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println(sumFirst(new int[]{2, 3, 5}, 2));
    }
}
```

Chạy:

```bash
javac SourceLogicBugDemo.java
java SourceLogicBugDemo
```

Stdout:

```text
10
```

Kết quả đúng theo đặc tả phải là `5` (`2 + 3`). Debugger hoặc unit test nhỏ sẽ chỉ ra vòng lặp đã lấy thêm `values[2]`. Sửa điều kiện thành `i < count` (và trong code thực, kiểm tra `0 <= count <= values.length`) rồi biên dịch/chạy lại sẽ in `5`.

Ở đây, bằng chứng rất rõ và có thể tái hiện với input cố định: **sửa logic mã nguồn và thêm test hồi quy** là giải pháp chính. Thêm dashboard CPU, heap hay thread dump sẽ không giúp tìm lỗi `<=` nhanh hơn.

## 7. Quy trình chẩn đoán thực tế: từ “bị chậm” đến nguyên nhân

1. **Xác định hiện tượng và tác động.** Mô tả cái gì sai, bắt đầu lúc nào, tần suất, request/instance bị ảnh hưởng và mức độ nghiêm trọng. Phân biệt “lỗi 500 tăng” với “người dùng thấy chậm”.
2. **Đóng băng ngữ cảnh so sánh.** Ghi build/version, JDK/JVM, cấu hình có liên quan, lượng tải, input, dependency, vùng triển khai và thay đổi gần thời điểm phát sinh. Đồng bộ múi giờ/timestamp.
3. **Chọn tín hiệu theo giả thuyết.** Ví dụ timeout → trace, latency, connection pool và dependency; crash → exception, exit reason, JVM/OS logs; hang → thread dumps và tình trạng lock; memory → heap/GC/allocation.
4. **Khoanh vùng và kiểm chứng.** Dùng request ID nối logs/traces; so sánh instance lỗi với instance khỏe; lập một giả thuyết có thể bác bỏ. Chạy thử trên môi trường kiểm soát hoặc tái hiện với cùng input/cấu hình nếu phù hợp. Chỉ attach debugger hoặc lấy dump khi cần và có thể thực hiện an toàn.
5. **Sửa đúng lớp và đo lại.** Sửa code kèm test hồi quy nếu là logic; sửa cấu hình/dependency/tài nguyên nếu bằng chứng chỉ vào đó. So sánh metric/error/latency với baseline dưới điều kiện tương đương, theo dõi tác dụng phụ và ghi nhận kết luận.

Ví dụ điều tra “request chậm”:

```text
Triệu chứng: p99 /checkout tăng từ ~250 ms lên ~4 s
    ↓
Metric: lỗi tập trung ở một khoảng thời gian và nhóm instance
    ↓
Trace: phần lớn thời gian nằm trong lời gọi database
    ↓
Đối chiếu: pool connection bão hòa cùng lúc với lượng query tăng
    ↓
Giả thuyết: số kết nối khả dụng không đáp ứng tải
    ↓
Kiểm chứng: đo wait time của pool + số kết nối đang dùng,
            so sánh dưới tải tương đương
    ↓
Hành động: sửa nguyên nhân phù hợp, rồi theo dõi p99 và error rate
```

Đây là **kịch bản minh họa**, không phải kết luận mặc định rằng mọi request chậm đều do pool. Một trace cho thấy thời gian nằm ở database cũng chưa chứng minh query, lock, network hay pool là nguyên nhân cuối cùng.

## 8. Khi nào bắt đầu bằng runtime, khi nào bắt đầu bằng source?

- **Có sự cố trên môi trường đang chạy; khó tái hiện; chỉ xảy ra dưới tải hoặc trên một nhóm instance:** bắt đầu từ quan sát runtime và điều kiện môi trường, sau đó đi vào source của đoạn nghi ngờ.
- **Một unit test đỏ, thuật toán cho kết quả sai ổn định với input nhỏ:** bắt đầu từ đặc tả, test và mã nguồn.
- **Exception có stack trace:** dùng trace để tìm đường code, đồng thời xác minh input/trạng thái đã dẫn tới exception; đừng kết luận chỉ theo dòng cuối.
- **Lỗi chỉ xuất hiện sau deploy:** đối chiếu artifact, JDK, flags, cấu hình, dependency, dữ liệu và tải, kể cả khi diff source nhỏ.
- **Sự cố không có exception:** vẫn kiểm tra metrics, traces, thread state và thời gian chờ; chậm, nghẽn hay rò rỉ có thể xảy ra mà không ném exception.

Một quy tắc hữu ích: **Nếu chưa biết “hệ thống đang làm gì”, quan sát runtime trước. Nếu đã có trường hợp tái hiện chắc chắn và chỉ ra logic sai, kiểm tra source/test trước.** Trong sự cố phức tạp, chuyển qua lại giữa hai hướng nhiều lần là bình thường.

## 9. Sai lầm phổ biến và cách tránh

- **Nhầm triệu chứng với nguyên nhân:** “heap lớn” không tự chứng minh memory leak; “nhiều thread WAITING” không tự chứng minh deadlock. Tìm chuỗi bằng chứng và kiểm chứng.
- **Chỉ đọc source rồi đoán production:** có thể bỏ sót JVM flags, cấu hình, tải, mạng, dữ liệu và dependency. Xác minh điều kiện thực thi thực tế.
- **Chỉ nhìn một ảnh chụp:** CPU, thread dump hay heap tại một thời điểm có thể không đại diện. Đối chiếu xu hướng và nhiều mẫu khi cần.
- **Thêm log tùy tiện:** log dày gây nhiễu, tăng chi phí và có thể lộ token, dữ liệu cá nhân. Ưu tiên request ID, ngữ cảnh có cấu trúc, sampling và che dữ liệu nhạy cảm.
- **Bật profiler/dump không cân nhắc:** công cụ chẩn đoán cũng tiêu tốn tài nguyên; heap dump có thể lớn và nhạy cảm. Chọn thời gian/phạm vi phù hợp, quản lý quyền truy cập và lưu trữ an toàn.
- **Sửa trước khi có baseline:** nếu không đo trước–sau, khó biết thay đổi đã xử lý đúng nguyên nhân hay chỉ che triệu chứng.
- **Không thêm test sau khi tìm ra lỗi code:** lỗi có thể quay lại. Giữ một test hồi quy với đúng input/điều kiện kích hoạt.

## 10. Tự kiểm tra hiểu bài

1. Cùng artifact Java chạy ổn trên staging nhưng timeout trên production. Bạn sẽ ghi lại những điều kiện và tín hiệu nào **trước khi** sửa thuật toán?
2. Một stack trace trỏ đến `NullPointerException` ở dòng 42. Vì sao dòng 42 có thể chỉ là nơi lỗi biểu hiện, chưa phải nguyên nhân gốc?
3. Trong ví dụ `RuntimeDiagnosisDemo`, điều gì thực sự thay đổi giữa hai lần chạy? Vì sao đó là minh họa của việc phải đọc cấu hình runtime?
4. Trong ví dụ `SourceLogicBugDemo`, một test với input `[2, 3, 5]` và `count = 2` giúp chứng minh điều gì mà dashboard JVM không thể chứng minh trực tiếp?
5. Nếu sau một thay đổi p99 giảm, cần đối chiếu thêm những điều kiện nào để tránh nhầm tương quan với quan hệ nhân quả?

**Điểm cần nhớ:** runtime diagnostics dùng bằng chứng từ chương trình trong điều kiện thực thi để tìm *điều gì đã xảy ra và vì sao*; source debugging đi sâu vào logic và trạng thái code để tìm *dòng/nhánh nào tạo hành vi sai*. Chọn điểm bắt đầu theo triệu chứng và liên tục kiểm chứng giả thuyết bằng bằng chứng phù hợp.