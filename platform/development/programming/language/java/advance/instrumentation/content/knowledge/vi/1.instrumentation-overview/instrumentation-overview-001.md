# Instrumentation là gì và vì sao công cụ cần chèn mã quan sát vào chương trình?

> **Mục tiêu:** Hiểu instrumentation trong Java/JVM, lý do cần đặt mã quan sát (probe) tại các điểm thực thi, cơ chế Java agent và bytecode transformation, dữ liệu thu được, chi phí và giới hạn. Bài này giải thích bản chất và cách đọc luồng hoạt động; không yêu cầu tự viết một thư viện biến đổi bytecode.

## 1. Bài toán: chương trình chạy đúng nhưng ta không nhìn thấy bên trong

Giả sử dịch vụ xử lý đơn hàng có luồng `HTTP request → controller → service → database → response`. Khi người dùng báo “đôi khi chậm”, chỉ biết tổng thời gian HTTP 2 giây là chưa đủ. Cần trả lời:

- Thời gian nằm ở service, truy vấn SQL, gọi API khác hay lúc chờ thread?
- Lỗi xảy ra ở request nào, phương thức nào và đi qua những thành phần nào?
- Một nhánh mã đã được chạy trong bài kiểm thử hay chưa?
- Khi ứng dụng đang chạy trong môi trường thực, điểm nóng CPU hoặc số lần gọi một phương thức tăng ra sao?

Business code thường chỉ thể hiện **phải làm gì**. Công cụ quan sát cần thêm thông tin **đã thực thi như thế nào**. Nếu mọi nhà phát triển đều tự chèn `println`, đồng hồ đo thời gian và mã ghi metric vào hàng nghìn phương thức, việc bảo trì vừa tốn công vừa thiếu nhất quán. Đó là lý do có instrumentation.

## 2. Định nghĩa và các khái niệm cần phân biệt

**Instrumentation** là việc bổ sung các điểm quan sát vào quá trình thực thi để thu thập dữ liệu phục vụ giám sát, chẩn đoán, kiểm thử hoặc phân tích. Một điểm quan sát (*probe*) có thể chạy trước/sau một lời gọi hàm, tại nhánh điều kiện, khi phát sinh ngoại lệ hoặc khi nhận sự kiện runtime.

Probe có thể ghi nhận thời điểm bắt đầu/kết thúc, số lần gọi, trạng thái lỗi, tên hoạt động, quan hệ cha–con của các thao tác, hoặc dấu hiệu một dòng/nhánh đã được thực thi. Nơi thu dữ liệu không nhất thiết là nơi hiển thị dữ liệu: probe thường gửi bản ghi tới bộ gom/đệm rồi mới xuất ra log, metric backend hoặc hệ thống tracing.

Trong Java cần phân biệt ba cách:

| Cách | Điểm đặt probe | Đặc điểm |
| --- | --- | --- |
| **Thủ công** | Lập trình viên viết `log`, `Timer`, span hoặc counter trực tiếp trong source | Rõ ý nghĩa nghiệp vụ, kiểm soát tốt, nhưng phải sửa từng điểm |
| **Tự động qua bytecode** | Agent hoặc bước build bổ sung lệnh vào `.class` tại những điểm được chọn | Bao phủ nhiều phương thức/thư viện, không cần sửa từng source; phải quản lý chi phí và tương thích |
| **Quan sát bằng sự kiện/sampling của runtime** | JFR, profiler, sự kiện JVM/OS, bộ đếm có sẵn | Có thể thu thông tin mà **không cần chèn bytecode vào mọi phương thức**; loại dữ liệu và độ chi tiết khác nhau |

Vì vậy câu “công cụ cần chèn mã quan sát” áp dụng rõ nhất cho **instrumentation dùng probe trực tiếp**, đặc biệt là tracing theo lời gọi, đo từng phương thức và coverage. Không phải mọi profiler hay hệ thống monitoring đều hoạt động bằng bytecode injection.

**Instrumentation** là cơ chế thu tín hiệu; **observability** là khả năng dùng các tín hiệu đó (cùng log, metric, trace, thông tin môi trường) để hiểu trạng thái hệ thống. Hai khái niệm có liên quan nhưng không đồng nghĩa.

## 3. Vì sao phải chèn mã vào điểm thực thi?

### 3.1. Nhìn thấy những thời điểm mà bên ngoài không thể biết

Một bộ giám sát đặt ngoài process có thể biết CPU, RAM hoặc tổng thời gian của request. Nhưng nếu muốn biết *đúng thời điểm* bắt đầu/kết thúc `OrderService.placeOrder()`, ngoại lệ được ném tại đó hay nhánh `if` nào đã đi qua, cần một tín hiệu nằm đủ gần vị trí mã thực thi.

Hình dung một phép đo:

```text
[probe: method entry]
        ↓
[logic nghiệp vụ gốc]
        ↓
[probe: return hoặc throw]
        ↓
[ghi duration / outcome / trace context]
```

Để đo khoảng thời gian đã trôi qua, probe có thể lấy `System.nanoTime()` khi vào và trừ tại lúc ra; để phân loại kết quả phải phân biệt đường `return` và đường ném ngoại lệ. Không thể suy ra chính xác các chi tiết đó chỉ từ tên phương thức hoặc từ log tổng của HTTP.

### 3.2. Bao phủ nhiều đường đi mà không sửa mã nghiệp vụ

Ứng dụng có hàng nghìn điểm cần quan sát, kể cả thư viện JDBC, HTTP client, executor hoặc framework không thuộc quyền chỉnh sửa source của nhóm dự án. Công cụ tự động có thể chọn các điểm chuẩn rồi bổ sung probe khi lớp được nạp. Cách này hữu ích để:

- Đo thời gian và tần suất của các thao tác phổ biến.
- Tạo span cho một request, liên kết các span qua service/database/HTTP client.
- Đếm dòng/nhánh được thực thi trong coverage.
- Thu sự kiện ở điểm bắt đầu/kết thúc phương thức hoặc đường lỗi mà không sửa từng lớp.

Các công cụ thường **lọc** lớp/phương thức cần theo dõi. Chèn vào mọi nơi một cách vô điều kiện dễ gây quá tải và tạo dữ liệu nhiễu.

### 3.3. Giữ logic nghiệp vụ tập trung

Instrumentation cố gắng tách trách nhiệm quan sát khỏi xử lý chính. Thí dụ, thay vì rải bộ đếm vào mọi lời gọi HTTP client, một Java agent có thể chèn probe vào những implementation được hỗ trợ. Tuy nhiên “không sửa source” **không có nghĩa** “không ảnh hưởng chương trình”: probe vẫn tiêu thụ CPU/bộ nhớ, có thể làm thay đổi timing, và agent viết sai vẫn có thể phá hành vi.

Instrumentation tự động cũng không thay thế hoàn toàn instrumentation thủ công. Các metric như “số đơn hàng được chấp nhận” hoặc “tổng tiền giao dịch hợp lệ” mang ý nghĩa nghiệp vụ nên thường phải do chính ứng dụng chủ động ghi nhận.

## 4. Điểm chèn trong JVM: từ `.class` tới mã chạy

Source Java được biên dịch thành **bytecode** trong file `.class`. JVM dùng class loader nạp định nghĩa lớp, kiểm tra tính hợp lệ rồi thực thi (thông dịch hoặc JIT biên dịch thành mã máy). Java cho phép agent đăng ký `ClassFileTransformer` để nhận bytecode tại các thời điểm phù hợp.

```text
App / library JAR chứa .class
            │
            ▼
       Class loader
            │
            ▼
   ClassFileTransformer
     ├─ không thay: trả null
     └─ thay: trả byte[] .class hợp lệ có thêm probe
            │
            ▼
   JVM kiểm tra / định nghĩa class
            │
            ▼
 Phương thức được gọi; probe chạy
            │
            ▼
 Sự kiện → buffer/exporter → log, metrics, traces, coverage
```

**Không phải** cứ khai báo transformer là đã chèn mã: transformer trả `null` nghĩa là giữ nguyên bytes. Muốn thêm lệnh thật sự cần tạo bytecode hợp lệ, thường nhờ thư viện như **ASM** hoặc **Byte Buddy**. Java agent có thể biến đổi bytecode lúc nạp lớp; trong các cấu hình được hỗ trợ nó còn có thể yêu cầu biến đổi lại lớp đã nạp (`retransformClasses`).

Ở mức bytecode, việc chèn lệnh phải xử lý các đường `return`, `throw`, stack/local variables, exception handlers và thông tin kiểm chứng stack frame. Chỉ thêm chuỗi lệnh tuỳ tiện vào `.class` có thể dẫn đến `VerifyError` hoặc `ClassFormatError`.

### Khi nào probe chạy?

- **Khi lớp được nạp:** transformer được gọi để quyết định có biến đổi bytecode hay không. Việc biến đổi xảy ra trước những lần thực thi phương thức của định nghĩa mới.
- **Khi phương thức được gọi:** nếu bytecode chứa probe thì probe thực thi trong luồng chạy bình thường của phương thức; Java có thể JIT biên dịch cả probe.
- **Khi lớp đã nạp từ trước:** muốn thêm probe sau đó có thể cần retransformation/redefinition, nếu JVM và agent cho phép. Không được giả định mọi class đều sửa được.

Mốc “chèn code” và mốc “thu dữ liệu” là hai việc khác nhau: transformation thực hiện khi nạp/biến đổi lớp; probe thu dữ liệu vào những lần gọi thực tế.

## 5. Minh hoạ trước và sau instrumentation

Giả sử logic gốc là:

```java
String placeOrder(String sku) {
    validate(sku);
    return repository.save(sku);
}
```

Khi muốn đo một lần gọi, ý tưởng của mã sau instrumentation là:

```text
start = monotonicClock()
markMethodEntered()
try:
    result = originalBody()
    recordSuccess()
    return result
catch error:
    recordError(error)
    throw error
finally:
    recordElapsed(monotonicClock() - start)
```

Khối `text` trên là **giả mã**, nhằm mô tả các nhánh kiểm soát. Nó không phải Java biên dịch độc lập. Công cụ bytecode phải đảm bảo lời gọi nghiệp vụ chỉ chạy một lần, ngoại lệ vẫn được truyền đúng và probe kết thúc được gọi trên cả đường thành công lẫn lỗi. Trên thực tế có thể tối ưu hoặc thay đổi chỗ đặt probe theo framework, kiểu hàm và mục tiêu quan sát.

Dữ liệu của một lần gọi có thể có dạng:

```text
operation=OrderService.placeOrder
elapsedMs=17
outcome=success
traceId=...            # giá trị tương quan được tạo ở runtime
```

`elapsedMs=17` chỉ là **dữ liệu minh hoạ**, không phải kết quả cố định của chương trình. `traceId` giúp ghép nhiều span trong cùng một hoạt động; tên operation và ID phải có chính sách cardinality/bảo mật phù hợp.

## 6. Java agent: cơ chế chuẩn để tham gia vào quá trình nạp class

JDK cung cấp package `java.lang.instrument`:

- `premain(String, Instrumentation)`: JVM gọi khi khởi động ứng dụng với `-javaagent:...`; agent có thể cài transformer **trước khi** ứng dụng vào `main`.
- `agentmain(String, Instrumentation)`: điểm vào cho agent gắn vào JVM đang chạy, **nếu** JVM/cấu hình hỗ trợ dynamic loading.
- `Instrumentation.addTransformer(...)`: đăng ký transformer để xử lý các định nghĩa lớp thích hợp.
- `ClassFileTransformer.transform(...)`: nhận tên nội bộ của lớp và bytecode đầu vào, trả `null` để không đổi hoặc trả `byte[]` đã biến đổi.
- `Instrumentation.isRetransformClassesSupported()` và `retransformClasses(...)`: khả năng biến đổi lại lớp đã nạp; cần capability phù hợp, thường khai báo `Can-Retransform-Classes: true` trong manifest và kiểm tra từng class có sửa được không.

Agent khởi động bằng `-javaagent` cần một JAR có thuộc tính manifest `Premain-Class`. Agent gắn khi đang chạy cần `Agent-Class` và điều kiện cho dynamic attach. Chính sách dynamic agent loading thay đổi theo JDK/cấu hình; đừng mặc định attach luôn được phép. Khi học cơ chế ban đầu, `-javaagent` lúc startup dễ lặp lại và kiểm chứng hơn.

### Ví dụ Java 17+: agent quan sát việc nạp class

Ví dụ dưới đây **có thể biên dịch và chạy bằng JDK 17+**, giúp nhìn thấy chuỗi `premain → transformer → class loading`. Nó chỉ ghi một thông báo khi nạp lớp mục tiêu; `return null` nghĩa là **chưa chèn thêm bytecode vào phương thức**. Đây là bước tối thiểu để hiểu hook trước khi dùng ASM/Byte Buddy thực hiện injection thật.

**Tệp `App.java`:**

```java
public final class App {
    static final class OrderService {
        String placeOrder(String sku) {
            System.out.println("business: " + sku);
            return "ORDER-" + sku;
        }
    }

    public static void main(String[] args) {
        String result = new OrderService().placeOrder("P01");
        System.out.println("result: " + result);
    }
}
```

**Tệp `ObserveAgent.java`:**

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ObserveAgent {
    public static void premain(String agentArgs, Instrumentation instrumentation) {
        System.out.println("agent: premain");

        ClassFileTransformer transformer = (
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer
        ) -> {
            if ("App$OrderService".equals(className)) {
                System.out.println("agent: loading " + className);
            }
            return null; // Chỉ quan sát class load; không thay bytecode.
        };

        instrumentation.addTransformer(transformer);
    }
}
```

Tên nội bộ của lớp lồng nhau là `App$OrderService`. Với package, tên nhận ở callback có dạng như `com/example/OrderService` (dấu `/` thay vì `.`). Transformer phải xử lý tên `null` ở những trường hợp JVM có thể cung cấp, và trong ứng dụng thực phải hạn chế thao tác nặng ngay trong callback.

**Tệp `agent.mf`** (kết thúc bằng ký tự xuống dòng; có thể thêm một dòng trống):

```text
Manifest-Version: 1.0
Premain-Class: ObserveAgent

```

**Biên dịch, đóng JAR agent và chạy** tại thư mục chứa ba tệp:

```bash
javac -encoding UTF-8 App.java ObserveAgent.java
jar --create --file observe-agent.jar --manifest agent.mf ObserveAgent.class
java -javaagent:observe-agent.jar App
```

**Stdout dự kiến của ví dụ:**

```text
agent: premain
agent: loading App$OrderService
business: P01
result: ORDER-P01
```

Nếu chạy `java App` không có agent, chỉ còn hai dòng `business: P01` và `result: ORDER-P01`. Quan sát được lớp được nạp chứng minh hook của agent hoạt động; **chưa** chứng minh có mã mới bên trong `placeOrder`. Muốn đo từng lời gọi `placeOrder`, transformer phải trả bytecode đã chèn probe ở entry/exit hoặc dùng cách hook khác phù hợp.

### Vì sao không tự sửa mảng `byte[]` trong ví dụ?

Một file class chứa constant pool, bảng method, thuộc tính và cấu trúc bytecode theo đặc tả JVM. Thêm lệnh có thể làm thay đổi offset nhánh, bảng exception và stack maps. Thư viện như ASM/Byte Buddy giúp xây dựng bytecode hợp lệ, nhưng vẫn đòi hỏi chọn đúng lớp/method, tránh tự instrument agent, xử lý tương thích và xác minh trên JVM mục tiêu.

## 7. Instrumentation thu được những gì?

| Tín hiệu | Probe thường đặt ở đâu? | Dùng để trả lời câu hỏi gì? |
| --- | --- | --- |
| **Metrics** | Điểm bắt đầu/kết thúc thao tác; nơi xảy ra sự kiện | Bao nhiêu request, bao nhiêu lỗi, độ trễ phân phối ra sao? |
| **Traces / spans** | Ranh giới request, RPC, SQL, message, method được chọn | Request này đi qua những bước nào, bước nào chậm? |
| **Logs / events** | Nhánh lỗi, sự kiện vòng đời, thay đổi trạng thái quan trọng | Điều gì đã xảy ra tại thời điểm đó? |
| **Coverage** | Điểm thực thi của dòng/nhánh hoặc phương thức | Test đã chạy qua những đoạn mã nào? |
| **Profiling** | Probe trên những điểm được chọn hoặc lấy mẫu stack/CPU | CPU/thời gian tập trung ở đâu? |

Một công cụ có thể dùng đồng thời nhiều cơ chế. Chẳng hạn profiler sampling có thể quan sát stack mà không chèn lệnh vào mọi method; ngược lại coverage thường cần probe ở những vị trí rất cụ thể. Tín hiệu thô còn cần được đặt tên, tổng hợp, lọc và liên kết để có ích khi điều tra.

### Ví dụ cùng một request

```text
HTTP GET /orders/42       span A, 120 ms
  ├─ OrderService.load    span B, 105 ms
  │   └─ JDBC SELECT      span C, 98 ms
  └─ serialize response   span D, 5 ms
```

Đây là dữ liệu **minh hoạ**. Nếu chỉ biết request mất 120 ms thì chưa phân biệt được DB hay business logic. Probe ở ranh giới HTTP/service/JDBC làm lộ ra quan hệ thời gian; trace context giúp gắn các bước thuộc cùng request. Đo tổng thời gian từng span không đồng nghĩa cộng tất cả span con thành tổng: các khoảng có thể lồng nhau hoặc chạy song song.

## 8. Những điều probe cần giữ đúng

**Tính đúng đắn:** Mục tiêu của instrumentation quan sát là giữ nguyên kết quả, tác dụng phụ và đường truyền ngoại lệ của business code. Cần đo cả đường `return`, `throw` và `finally`. Probe lỗi nên được cách ly hợp lý để không làm hỏng nghiệp vụ; có trường hợp bắt buộc tắt instrumentation thay vì bỏ qua lỗi một cách âm thầm.

**Chi phí:** Mỗi probe có chi phí chạy và chi phí ghi/xuất dữ liệu. Đừng log từng phần tử của vòng lặp nóng hoặc đồng bộ gửi network ngay trên request thread. Cân nhắc sampling, giới hạn số điểm chèn, batch/buffer và kiểm soát backpressure.

**Context:** Trace phải được truyền qua thread pool, `CompletableFuture`, messaging và ranh giới mạng. Một method trả `CompletionStage` rất nhanh không có nghĩa công việc bất đồng bộ đã hoàn tất: muốn đo toàn bộ operation cần kết thúc span theo tín hiệu completion phù hợp. Với virtual threads, vẫn phải kiểm tra cơ chế truyền context của thư viện đang dùng.

**Dữ liệu nhạy cảm:** Không tự động đưa password, token, payload cá nhân hoặc toàn bộ tham số SQL vào log/span. Tên metric/tag có cardinality thấp và ổn định; tránh dùng trực tiếp `userId`, URL có ID động hoặc giá trị input bất kỳ làm label metric.

**Tương thích:** Class loader, module access, thứ tự nhiều agent, thay đổi JDK, cấu trúc bytecode, thư viện đã shading và framework có proxy có thể ảnh hưởng transformer. Không phải mọi lớp đều modifiable; không thể giả định retransform cho phép đổi cấu trúc lớp tùy ý (như thêm/xóa field hay method).

**Tránh lặp vô hạn:** Nếu probe gọi logger/HTTP client mà chính các lớp đó lại bị instrument, có thể tạo recursion hoặc ghi trùng sự kiện. Agent thực tế cần danh sách loại trừ, guard và quy tắc chọn điểm chèn.

## 9. Những hiểu nhầm thường gặp

1. **“Có agent nghĩa là đã instrument mọi method.”** Không đúng. Agent có thể chỉ quan sát class loading, thu metadata, hoặc chỉ biến đổi lớp thuộc tập được hỗ trợ.
2. **“Không sửa source nên không ảnh hưởng chương trình.”** Không đúng. Probe là mã chạy thật, có overhead và có thể thay đổi thứ tự/timing hoặc sinh lỗi.
3. **“`ClassFileTransformer` tự đo thời gian cho tôi.”** Không. Nó là hook để quyết định sửa bytes; việc đo thực tế do probe được cài vào luồng gọi đảm nhiệm.
4. **“Đã load lớp rồi thì chắc chắn chèn được probe.”** Không. Cần capability, quyền và điều kiện của retransformation; một số loại thay đổi bị cấm.
5. **“Chỉ cần thêm log là có distributed trace.”** Không. Cần tạo/tiếp nhận span context, truyền context qua ranh giới bất đồng bộ và liên kết ID giữa các service.
6. **“Đo càng chi tiết càng tốt.”** Không. Nhiều probe làm tăng overhead và dữ liệu; nên bắt đầu từ điểm có giá trị chẩn đoán cao.
7. **“AOP, proxy và Java agent là cùng một cơ chế.”** Không. Proxy/AOP có thể chặn lời gọi ở ranh giới đối tượng hoặc trong bước weaving; Java agent tác động tới định nghĩa lớp/bytecode. Khả năng bao phủ và giới hạn khác nhau.

## 10. Khi chọn cách nào?

- **Cần số liệu nghiệp vụ** (đơn thành công, trạng thái quy trình): ghi metric/span **thủ công** tại nơi hiểu nghiệp vụ.
- **Cần quan sát HTTP, JDBC, RPC, framework phổ biến trên diện rộng:** cân nhắc **automatic instrumentation** được framework/JDK hỗ trợ, với phạm vi loại trừ và đo overhead.
- **Cần biết đường chạy test:** dùng **coverage instrumentation**, vốn chèn probe theo dòng/nhánh có ý nghĩa.
- **Cần điều tra CPU/GC/thread mà không muốn probe vào từng method:** ưu tiên **JFR, thread dump, profiler sampling hoặc các sự kiện runtime** tùy câu hỏi.
- **Cần đo chính xác một hotspot hoặc thư viện đặc biệt:** chọn probe ở đúng điểm, rồi so sánh overhead/tác dụng phụ với baseline trước khi mở rộng.

Khi đưa agent vào môi trường chạy thật, nên kiểm tra: điểm chèn có đúng lớp/method không; tín hiệu có được gắn đúng request không; thành công/lỗi có được đếm đủ không; chi phí CPU/bộ nhớ/độ trễ là bao nhiêu; có phát sinh recursion, leak context hoặc dữ liệu nhạy cảm không; có cơ chế giảm/tắt mức quan sát khi tải cao không.

## 11. Tự kiểm tra kiến thức

**Hỏi:** Nếu một transformer luôn trả `null`, nó đã chèn probe vào phương thức chưa?  
**Đáp:** Chưa. Nó có thể quan sát sự kiện nạp lớp, nhưng bytecode được giữ nguyên.

**Hỏi:** Vì sao cùng một probe ở đầu phương thức không đủ để tính duration và lỗi?  
**Đáp:** Phải quan sát điểm kết thúc và các đường `return`/`throw`, đồng thời giữ đúng ngoại lệ và luồng thực thi.

**Hỏi:** Instrumentation có thay thế logging, metrics và tracing không?  
**Đáp:** Không. Nó tạo điểm thu tín hiệu; các hệ thống logging/metrics/tracing còn chịu trách nhiệm cấu trúc, truyền, lưu trữ, truy vấn và hiển thị dữ liệu.

**Hỏi:** Vì sao nên kết hợp automatic và manual instrumentation?  
**Đáp:** Automatic bao phủ kỹ thuật chuẩn; manual diễn đạt sự kiện và nhãn nghiệp vụ mà công cụ chung khó tự suy ra.

## Tài liệu tham khảo chính thức

- [JDK 21 — Package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): cơ chế `-javaagent`, manifest, `premain`/`agentmain`.
- [JDK 21 — Interface `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer, retransform và capability.

**Ghi nhớ:** Công cụ chèn mã quan sát để đặt điểm đo **ngay tại những vị trí thực thi cần thấy**. Cơ chế tự động giảm sửa đổi source và giúp bao phủ thư viện/luồng kỹ thuật, nhưng tính đúng đắn, chi phí, dữ liệu nhạy cảm và khả năng tương thích vẫn là trách nhiệm phải kiểm chứng.