# Ảnh hưởng của ghi nhật ký và tuần tự hóa tham số trong Aspect (AOP)

## Mục tiêu và phạm vi

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), một **aspect** có thể chèn hành vi ghi nhật ký vào nhiều **join point** như lúc gọi phương thức, lúc vào/ra phương thức hoặc khi phát sinh ngoại lệ, tùy khả năng của cơ chế weaving. Nhờ tách mối quan tâm quan sát hệ thống khỏi nghiệp vụ, logging dễ áp dụng đồng nhất; đồng thời, một lời gọi rất rẻ trước đó có thể phải trả thêm chi phí lấy metadata, tạo chuỗi, tuần tự hóa tham số và chuyển bản ghi tới nơi lưu trữ.

Sau bài này, bạn cần phân biệt được **chi phí của cơ chế AOP**, **chi phí tạo nội dung log**, **chi phí tuần tự hóa**, và **chi phí phát log**; xác định nguyên nhân tăng độ trễ, CPU, bộ nhớ hoặc lưu lượng I/O; biết cách giảm tác động mà vẫn giữ thông tin chẩn đoán hữu ích.

Bài viết nói về AOP theo nghĩa chung. Cách một join point được nhận diện và mã advice được chèn phụ thuộc vào cơ chế weaving và công cụ AOP cụ thể.

## 1. Logging nằm ở đâu trong luồng AOP?

Các khái niệm cần phân biệt:

- **Join point**: vị trí trong quá trình thực thi mà hành vi bổ sung có thể được áp dụng.
- **Pointcut**: điều kiện chọn những join point cần quan tâm. Pointcut quá rộng sẽ làm advice chạy trên cả các thao tác rất nhỏ, thường xuyên.
- **Advice**: mã chạy trước, sau hoặc bao quanh hành vi được chọn. Around advice có thể đo thời gian, ghi nhận kết quả và ngoại lệ.
- **Weaving**: quá trình gắn advice vào luồng thực thi, có thể xảy ra tại thời điểm biên dịch, nạp lớp hoặc lúc chạy tùy công nghệ.

Ví dụ luồng một advice ghi nhật ký:

```text
Lời gọi nghiệp vụ
    ↓
Điểm chặn / mã đã được weave
    ↓
Kiểm tra mức log, chính sách lấy mẫu
    ↓
[Nếu cần] lấy metadata + chọn trường an toàn + tuần tự hóa tham số
    ↓
Gửi bản ghi đến logger / hàng đợi / sink
    ↓
Thực thi nghiệp vụ
    ↓
[Nếu cần] ghi kết quả, thời gian, ngoại lệ
    ↓
Trả kết quả hoặc ném ngoại lệ gốc
```

Ngay cả khi ghi log bị tắt, vẫn có thể tồn tại chi phí của kiểm tra điều kiện, chuyển hướng lời gọi, lấy thời gian, tạo đối tượng advice hoặc tìm metadata. Phần chi phí cụ thể khác nhau đáng kể giữa weaving tĩnh, weaving lúc nạp lớp và cơ chế chặn lời gọi động. Không thể kết luận một loại luôn nhanh hơn mọi loại còn lại: cần đo trên đúng thao tác, tải và bản triển khai.

Một mô hình để *phân rã* độ trễ của một lời gọi đồng bộ:

\[
T_{\text{observed}} \approx T_{\text{business}} + T_{\text{interception}} + T_{\text{format}} + T_{\text{serialization}} + T_{\text{enqueue/write}} + T_{\text{contention}}
\]

Đây là mô hình tư duy, không phải đẳng thức đo lường phổ quát: cache, JIT, GC, tranh chấp tài nguyên và các thao tác bất đồng bộ khiến các thành phần tác động qua lại. Nếu sink ghi không đồng bộ thì thời gian ghi xuống đĩa có thể nằm ngoài đường thực thi của lời gọi, nhưng CPU để tạo payload và cấp phát hàng đợi vẫn có thể xảy ra trước khi trả kết quả.

## 2. Ghi nhật ký ảnh hưởng đến hiệu năng như thế nào?

### 2.1. Chi phí trước khi phát một bản ghi

Một advice tưởng như chỉ có một câu lệnh log có thể làm nhiều việc:

1. Xác định tên phương thức, tham số, kết quả hoặc ngoại lệ; tra cứu chữ ký và annotation bằng reflection nếu cần.
2. Tạo thông điệp qua nối chuỗi, định dạng ngày giờ, stack trace hoặc thu thập context.
3. Chuyển object sang dạng ký tự; gọi `toString()` cũng có thể thực thi logic tốn kém hoặc có tác dụng phụ.
4. Mã hóa thông điệp, cấp phát buffer, thực hiện khóa hoặc đẩy vào hàng đợi.
5. Gửi đến console, tệp, mạng hoặc bộ thu log, có thể chặn thread gọi khi nguồn nhận chậm.

Với một phương thức nghiệp vụ chỉ mất vài microgiây, ngay cả vài microgiây cho advice cũng làm tỷ lệ overhead đáng kể. Với một thao tác mạng mất hàng trăm mili giây, cùng một chi phí tuyệt đối có thể ít đáng kể hơn, nhưng số lời gọi lớn vẫn làm tăng CPU và lưu lượng log.

### 2.2. Log đồng bộ và không đồng bộ

| Cách phát log | Chi phí trên luồng gọi | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Ghi đồng bộ | Có thể phải chờ khóa, flush, I/O hoặc sink | Độ trễ đuôi (`p95/p99`) tăng khi đĩa hoặc mạng chậm |
| Đẩy vào hàng đợi để ghi bất đồng bộ | Thường giảm phần thời gian chờ sink | Chi phí tạo payload vẫn còn; hàng đợi có thể đầy, gây drop hoặc backpressure |
| Bỏ qua khi log bị tắt | Rẻ nếu kiểm tra sớm và không tạo payload | Vẫn có chi phí chặn lời gọi nếu advice được kích hoạt |
| Lấy mẫu một phần lời gọi | Giảm số bản ghi ở lưu lượng lớn | Có thể bỏ sót ca hiếm; cần giữ đường ghi lỗi quan trọng phù hợp |

“Bất đồng bộ” không đồng nghĩa “không tốn tài nguyên”. Nếu request thread đã tuần tự hóa toàn bộ tham số thành JSON trước khi enqueue thì nó vẫn chịu phần lớn chi phí CPU và cấp phát. Một queue không giới hạn có thể biến đợt tăng đột biến thành nguy cơ cạn bộ nhớ; queue có giới hạn cần chính sách rõ ràng khi đầy: chờ, từ chối hoặc bỏ log ít quan trọng, kèm metric đếm số bản ghi bị mất.

### 2.3. Khối lượng bản ghi tích lũy

Giả sử một pointcut khớp **1.000 lời gọi/giây**, mỗi lời gọi tạo **2 bản ghi**, và trung bình mỗi bản ghi là **1.000 byte**:

- Thông lượng dữ liệu log: `1.000 × 2 × 1.000 = 2.000.000 byte/giây`, tức **2 MB/giây** theo đơn vị thập phân.
- Sau một ngày: `2.000.000 × 86.400 = 172.800.000.000 byte`, tức **172,8 GB/ngày** trước metadata, index, replication và chính sách lưu trữ.

Vì vậy, log tại join point gọi rất thường xuyên có thể gây tác động lớn ngay cả khi thời gian tạo từng bản ghi trông nhỏ.

## 3. Tuần tự hóa tham số có những chi phí nào?

**Tuần tự hóa** là chuyển dữ liệu từ dạng object trong bộ nhớ sang một biểu diễn như JSON, XML hoặc byte stream. Trong logging AOP, mục đích thường là giúp đọc, tìm kiếm hoặc chuyển tiếp dữ liệu. Cần phân biệt ba thao tác:

- **Lấy mảng tham số** tại join point: có thể chỉ là truy cập tham chiếu, chưa sao chép đồ thị object.
- **Tạo bản tóm tắt tham số**: chọn vài trường nhỏ, ví dụ loại dữ liệu, kích thước, số phần tử hoặc định danh đã được cho phép.
- **Tuần tự hóa toàn bộ object**: duyệt cấu trúc lồng nhau, lấy giá trị, escape chuỗi, xử lý kiểu dữ liệu và tạo buffer/ký tự đầu ra. Thao tác này thường tốn kém nhất.

### 3.1. CPU, allocation và kích thước dữ liệu

Để tuần tự hóa một đồ thị object, bộ mã hóa có thể cần kiểm tra kiểu, truy cập trường/getter, duyệt collection/map, xử lý `null`, escape ký tự và mở rộng buffer. Nếu có \(n\) phần tử phải duyệt và \(b\) byte đầu ra, độ phức tạp thường phụ thuộc ít nhất vào lượng dữ liệu đã duyệt và xuất ra; không có công thức `O(n)` chung cho mọi serializer vì cách xử lý reflection, tham chiếu, vòng lặp hay adapter tùy triển khai.

Một payload sâu hoặc rất lớn có thể tạo nhiều object trung gian, tăng allocation rate và khiến GC chạy thường xuyên hơn. Việc đọc object đang bị thread khác sửa có thể tạo snapshot không nhất quán hoặc phát sinh lỗi, tùy cấu trúc dữ liệu và serializer. Getters cũng có thể tính toán, truy cập trạng thái lazy hoặc ném ngoại lệ.

### 3.2. Những ca thường gây vấn đề

| Dữ liệu tại join point | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Object chứa nhiều collection lồng nhau | CPU, chuỗi lớn, GC và dung lượng log | Giới hạn độ sâu, số phần tử, kích thước byte |
| Đồ thị có tham chiếu vòng (`A → B → A`) | Lặp vô hạn hoặc lỗi nếu serializer thiếu cơ chế nhận diện | Dùng biểu diễn tóm tắt, giới hạn độ sâu hoặc cơ chế xử lý identity |
| Stream, file, iterator, lazy data | Đọc có thể tiêu thụ dữ liệu, gây I/O hay thay đổi hành vi | Chỉ ghi loại, kích thước đã biết hoặc metadata an toàn |
| Byte array, nội dung ảnh/tệp | Payload tăng mạnh khi mã hóa dạng văn bản | Chỉ ghi độ dài hoặc checksum được cho phép |
| Exception/stack trace lớn | Tạo chuỗi tốn kém và nhiều log trùng nhau | Ghi loại lỗi, mã lỗi, stack trace khi cần |
| Tham số có bí mật/dữ liệu cá nhân | Rò rỉ thông tin qua log và hệ thống tập trung | Allowlist trường, che hoặc loại bỏ trước khi serialize |

Không nên xem `Object.toString()`, `Arrays.deepToString(...)` hoặc “serialize tất cả tham số” là mặc định an toàn: kết quả có thể lộ dữ liệu, sinh nhiều ký tự hoặc kích hoạt mã không mong muốn. Một object tùy biến có thể viết `toString()` theo cách tốn thời gian hoặc không bảo đảm thread safety.

### 3.3. Lọc dữ liệu trước khi mã hóa

Quy trình phù hợp hơn cho log có cấu trúc là:

```text
Join point
  → quyết định có cần log không
  → kiểm tra sampling / hạn mức
  → chọn các trường được phép (allowlist)
  → che/mã hóa định danh khi được phê duyệt
  → giới hạn độ sâu, số phần tử và kích thước
  → serialize một bản ghi nhỏ, có cấu trúc
  → enqueue hoặc ghi
```

Nếu đã tạo JSON đầy đủ rồi mới dùng biểu thức chính quy để che một vài giá trị thì **chi phí tuần tự hóa đầy đủ vẫn xảy ra** và rủi ro lộ trường không được nhận diện vẫn còn. Các trường như password, token, khóa truy cập, cookie, thông tin thanh toán và nội dung yêu cầu riêng tư cần bị loại khỏi dữ liệu đầu ra ngay từ bước chọn trường. Với dữ liệu nhạy cảm, ngay cả độ dài hoặc định danh hash cũng cần đánh giá xem có thể tiết lộ thông tin hay không.

## 4. Sai lầm thường gặp: tạo payload dù không cần log

**Ví dụ phản diện**, mã minh họa (các hàm do ứng dụng tự định nghĩa):

```java
// Minh họa, không phải chương trình Java độc lập.
String payload = serializeAllArguments(args); // Luôn chạy!
if (debugEnabled) {
    writeLog(payload);
}
```

Khi `debugEnabled == false`, quá trình duyệt object, cấp phát và tạo chuỗi vẫn diễn ra. Với lời gọi thường xuyên, đây có thể là nguồn CPU/GC đáng kể dù người vận hành tin rằng đã tắt debug log.

**Cách tổ chức tốt hơn**:

```java
// Minh họa, không phải chương trình Java độc lập.
if (debugEnabled && shouldSample(callContext)) {
    SafeFields fields = selectAllowedFields(args);
    writeLog(serializeBounded(fields));
}
```

Trong đó `selectAllowedFields` chủ động bỏ trường nhạy cảm; `serializeBounded` có giới hạn độ sâu/số phần tử/dung lượng; `shouldSample` quyết định lấy mẫu trước khi tạo payload. Tránh gọi hàm định dạng như một đối số được tính háo hức cho logger mà không biết logger có hỗ trợ trì hoãn đánh giá hay không.

Bên cạnh điều kiện bật log, nên giới hạn **độ phủ của pointcut** theo mục tiêu quan sát: chọn nghiệp vụ hoặc ranh giới hệ thống có giá trị chẩn đoán thay vì ghi mọi getter, constructor hay phương thức nhỏ. Nếu cùng một thao tác khớp nhiều aspect, kiểm soát thứ tự và tránh ghi trùng thông tin tại các tầng lồng nhau.

## 5. Ví dụ Java 17+: advice mô phỏng bằng Dynamic Proxy

Java hỗ trợ `java.lang.reflect.Proxy` để chặn lời gọi thông qua **interface**. Đây là ví dụ minh họa tác động của logic chặn lời gọi và điều kiện logging; một proxy như vậy không đại diện cho toàn bộ khả năng join point hoặc mọi chiến lược weaving của AOP.

Tạo tệp `AspectLoggingImpactDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class AspectLoggingImpactDemo {
    interface Worker {
        int process(String token, int count);
    }

    static final class DefaultWorker implements Worker {
        @Override
        public int process(String token, int count) {
            return token.length() * count;
        }
    }

    static final class LoggingAdvice implements InvocationHandler {
        private final Worker target;
        private final boolean enabled;

        LoggingAdvice(Worker target, boolean enabled) {
            this.target = target;
            this.enabled = enabled;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            if (enabled) {
                System.out.println("[before] " + method.getName()
                        + " args=" + safeSummary(args));
            }

            try {
                Object result = method.invoke(target, args);
                if (enabled) {
                    System.out.println("[after] " + method.getName());
                }
                return result;
            } catch (InvocationTargetException exception) {
                // Giữ nguyên nguyên nhân nghiệp vụ, tránh bọc thêm một tầng.
                throw exception.getCause();
            }
        }

        private static String safeSummary(Object[] args) {
            if (args == null || args.length == 0) {
                return "[]";
            }

            List<String> parts = new ArrayList<>();
            for (Object arg : args) {
                if (arg == null) {
                    parts.add("null");
                } else if (arg instanceof String text) {
                    // Không ghi nội dung chuỗi, chỉ ghi độ dài trong demo.
                    parts.add("String(length=" + text.length() + ")");
                } else if (arg instanceof Integer || arg instanceof Boolean) {
                    parts.add(String.valueOf(arg));
                } else {
                    // Không tự động gọi toString() trên object tùy ý.
                    parts.add(arg.getClass().getSimpleName());
                }
            }
            return parts.toString();
        }
    }

    private static Worker wrap(Worker target, boolean enabled) {
        return (Worker) Proxy.newProxyInstance(
                Worker.class.getClassLoader(),
                new Class<?>[]{Worker.class},
                new LoggingAdvice(target, enabled)
        );
    }

    public static void main(String[] args) {
        Worker target = new DefaultWorker();

        Worker logged = wrap(target, true);
        Worker quiet = wrap(target, false);

        System.out.println("loggedResult=" + logged.process("secret", 2));
        System.out.println("quietResult=" + quiet.process("secret", 2));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac AspectLoggingImpactDemo.java
java AspectLoggingImpactDemo
```

Kết quả chuẩn:

```text
[before] process args=[String(length=6), 2]
[after] process
loggedResult=12
quietResult=12
```

Trong ví dụ, cùng một phương thức nghiệp vụ trả về `12` ở cả hai trường hợp. Khi bật log, chương trình phải tạo danh sách tóm tắt và ghi hai dòng; khi tắt log, hai thao tác đó được bỏ qua. Tuy nhiên, `quiet` vẫn đi qua proxy và một lời gọi phản chiếu `method.invoke(...)`, nên đây **không phải phép đo chứng minh chi phí AOP bằng không khi tắt logging**. `safeSummary` chỉ là bản giản lược để học: chính sách thật có thể phải bỏ cả độ dài chuỗi, số nguyên hoặc tên kiểu, tùy mức độ nhạy cảm.

Code in thông điệp `[after]` chỉ khi gọi nghiệp vụ thành công. Nếu nghiệp vụ ném ngoại lệ, handler chuyển tiếp nguyên nhân gốc; một advice ghi lỗi thực tế nên ghi loại lỗi/mã lỗi an toàn nhưng **không thay đổi ngoại lệ nghiệp vụ**. Logging phụ trợ cũng cần được thiết kế để lỗi formatter/sink không vô tình che mất ngoại lệ gốc hoặc làm hỏng kết quả nghiệp vụ.

## 6. Đo lường tác động một cách đáng tin

Một con số đo thời gian riêng lẻ, nhất là trong vòng lặp nhỏ, không đủ để kết luận mức overhead. JIT compilation, warm-up, inlining, GC, caching, buffering của sink và số thread đồng thời có thể làm kết quả khác xa tải thực tế.

Nên so sánh **cùng một nghiệp vụ, cùng dữ liệu và cùng tải** trong các cấu hình:

| Cấu hình | Điều cần cô lập |
| --- | --- |
| A. Không có interception | Thời gian nền của nghiệp vụ |
| B. Có interception, advice gần như rỗng | Chi phí chặn lời gọi/weaving |
| C. Có advice, log tắt và guard đặt sớm | Chi phí kiểm tra và đường đi khi tắt |
| D. Log bật, chỉ ghi trường scalar đã chọn | Chi phí tạo bản ghi nhỏ |
| E. Log bật, payload lớn/nhiều object | Chi phí tuần tự hóa, allocation và GC |
| F. Log bất đồng bộ với queue hữu hạn | Tác động lên latency, queue, drop và sink |

Thu thập đồng thời:

- **Latency** `p50`, `p95`, `p99`; nếu ghi log trên luồng request, chú ý phần đuôi phân phối.
- **Throughput** (lời gọi/giây), CPU, allocation (byte/lời gọi), tốc độ và thời gian GC.
- **Kích thước bản ghi**, byte/giây, thời gian chờ sink, mức chiếm hàng đợi, số log bị drop hoặc bị chặn.
- **Độ phủ advice**: số lần mỗi pointcut khớp, có chặn cả lời gọi lồng nhau hoặc cùng một thông tin nhiều lần không.

Với microbenchmark Java, nên dùng công cụ đo chuyên dụng như JMH và cấu hình warm-up/iteration phù hợp; với mục tiêu vận hành, cần thêm load test ở mức hệ thống cùng loại sink, thiết bị lưu trữ và concurrency gần thực tế. Không dùng việc in liên tục ra console trong vòng lặp làm benchmark chuẩn của chi phí interception: phần console I/O dễ áp đảo mọi phần còn lại.

Ví dụ khi báo cáo kết quả, cần nêu rõ **chi phí tuyệt đối** và **tỷ lệ overhead**: `overhead = (latency_with_advice - latency_baseline) / latency_baseline × 100%` ở điều kiện đo tương ứng. So sánh cùng percentile phải cẩn thận vì các percentile của tổng thời gian không cộng tuyến tính từ percentile từng thành phần. Không ngoại suy kết quả đo trên một thread sang môi trường có nhiều thread tranh chấp hàng đợi hoặc thiết bị I/O.

## 7. Những nguy cơ về tính đúng đắn và bảo mật

Logging là hành vi quan sát, nên về nguyên tắc không được thay đổi kết quả hoặc side effect của phương thức được quan sát. Các tình huống phải phòng tránh:

1. **Duyệt object có side effect**: getter tính toán, stream một lần, iterator hoặc `toString()` có thể đọc/tiêu thụ dữ liệu hoặc ném lỗi. Ưu tiên dữ liệu tóm tắt đã biết an toàn.
2. **Dữ liệu thay đổi đồng thời**: serialize một collection đang sửa có thể không ổn định. Tránh sao chép sâu tùy tiện trên đường nóng; dùng snapshot được thiết kế rõ ràng khi thực sự cần.
3. **Log injection**: tham số có newline/ký tự điều khiển có thể làm bản ghi văn bản giả dạng nhiều dòng. Đầu ra cấu trúc cần escape đúng và có giới hạn kích thước.
4. **Rò rỉ dữ liệu**: không phát tán credential, token, cookie, bí mật nghiệp vụ hay toàn bộ request/response sang sink và hệ thống lưu trữ tập trung. Kiểm soát quyền truy cập và thời hạn lưu trữ log.
5. **Đệ quy logging**: aspect áp dụng rộng có thể chặn cả chính hàm logger/formatter, gây vòng lặp hoặc tạo thêm bản ghi. Loại trừ đường logging và đặt ranh giới rõ ràng.
6. **Lỗi trong advice**: ngoại lệ từ serializer, formatter, queue hoặc sink không nên che khuất lỗi nghiệp vụ. Chính sách fail-open/fail-closed phải theo yêu cầu hệ thống; metric lỗi logging phải độc lập, tránh tự gọi vòng lại cơ chế logging lỗi.
7. **Context qua luồng/bất đồng bộ**: correlation ID, trace ID hoặc ngữ cảnh gắn với thread cần được truyền đúng khi công việc chuyển thread; không giả định mọi cơ chế lưu context theo thread tự động theo sang nơi thực thi khác.

Ở join point có lưu lượng lớn, **cardinality** cũng quan trọng: không gắn dữ liệu không giới hạn như ID duy nhất hay payload dài làm nhãn metric. Log và metric có mục đích khác nhau; định danh dùng để truy vết nên nằm trong trường log có kiểm soát thay vì tạo vô số chuỗi thời gian metric.

## 8. Tối ưu theo thứ tự ưu tiên

1. **Chọn đúng join point/pointcut**: ưu tiên ranh giới có giá trị quan sát; loại phương thức gọi dày đặc không cần log chi tiết.
2. **Kiểm tra mức log và lấy mẫu trước khi làm việc nặng**: đặt guard trước reflection không cần thiết, formatter và serializer; dành chính sách riêng cho lỗi nghiêm trọng.
3. **Chọn trường bằng allowlist**: ghi tên thao tác, trạng thái, thời lượng, correlation ID, mã lỗi an toàn; thường không cần toàn bộ object.
4. **Giới hạn payload**: giới hạn byte, độ sâu, số phần tử, chiều dài chuỗi; áp dụng che dữ liệu trước serialization.
5. **Tái sử dụng metadata ổn định khi thích hợp**: cache tên/chữ ký phương thức hoặc schema nếu công nghệ hỗ trợ, nhưng không cache dữ liệu nhạy cảm hay tham số theo lời gọi.
6. **Chọn sink và queue theo SLO**: đánh giá ghi đồng bộ/bất đồng bộ, backpressure, khả năng mất bản ghi và nhu cầu audit. Dữ liệu audit bắt buộc có yêu cầu độ bền khác log debug tùy chọn.
7. **Theo dõi chính đường logging**: đo số lần advice chạy, tỷ lệ lấy mẫu, thời gian format/serialize, độ dài queue, log drop và lỗi sink.
8. **Kiểm chứng dưới tải thật**: xem throughput, `p99`, CPU, GC và byte log sau từng thay đổi; điều chỉnh dựa trên mục tiêu hệ thống.

### Chọn mức chi tiết theo tình huống

| Tình huống | Logging phù hợp để bắt đầu |
| --- | --- |
| Hàm nhỏ chạy hàng triệu lần | Tắt log từng lời gọi; dùng tổng hợp hoặc lấy mẫu rất thấp |
| Ranh giới gọi dịch vụ ngoài | Tên thao tác, trạng thái, thời lượng, correlation ID, mã lỗi |
| Lỗi hiếm, khó tái hiện | Log lỗi có cấu trúc, stack trace có kiểm soát và trường an toàn |
| Object lớn hoặc chứa bí mật | Chỉ log metadata được phép, kích thước đã kiểm soát hoặc mã định danh an toàn |
| Hệ thống cần audit | Thiết kế luồng audit có yêu cầu độ bền/đúng đủ riêng và đánh giá chi phí rõ ràng |

## 9. Những kết luận cần nhớ

- **Interception, formatting, serialization và ghi log là các nhóm chi phí khác nhau.** Tắt sink chưa chắc đã loại bỏ chi phí nếu payload được tạo trước.
- **Serialize toàn bộ tham số tại mọi join point thường là quyết định tốn kém và nhiều rủi ro.** Chọn dữ liệu an toàn, giới hạn kích thước rồi mới mã hóa.
- **Bất đồng bộ chuyển bớt I/O khỏi đường gọi nhưng không làm mất chi phí CPU, allocation hay vấn đề queue.**
- **Đo theo tải và percentile thực tế.** Thay đổi phải được đánh giá đồng thời về tính đúng đắn, bảo mật, tài nguyên và khả năng chẩn đoán.
- **Aspect tốt phải phục vụ quan sát mà không làm thay đổi ngữ nghĩa nghiệp vụ.** Chính sách logging, thứ tự advice, xử lý lỗi và phạm vi pointcut cần được thiết kế có chủ đích.
