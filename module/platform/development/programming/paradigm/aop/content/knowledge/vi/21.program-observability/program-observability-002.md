# Tạo mã tương quan và gắn ngữ cảnh theo lời gọi trong AOP

## 1. Mục tiêu của bài

Khi một thao tác nghiệp vụ đi qua nhiều phương thức, nhiều lớp hoặc nhiều tác vụ bất đồng bộ, log đơn lẻ thường không cho biết các sự kiện nào thuộc cùng một lần xử lý. **Mã tương quan** (correlation ID) giúp nối các sự kiện liên quan thành một chuỗi; **ngữ cảnh lời gọi** (call context) bổ sung thông tin về từng lần thực thi; **aspect** áp dụng quy tắc gắn, đọc và dọn dẹp ngữ cảnh tại các điểm được chọn bằng pointcut.

Ví dụ một thao tác “xử lý đơn hàng” lần lượt kiểm tra tồn kho, tính phí và ghi nhận kết quả. Nếu từng phương thức in log riêng, muốn tra cứu toàn bộ thao tác phải có một khóa chung. Trong AOP, thay vì viết thao tác lấy/gắn mã lặp lại trong từng phương thức nghiệp vụ, ta có thể đặt advice tại các join point thích hợp.

Sau bài này, cần phân biệt được:

- Mã tương quan dùng để gom các sự kiện thuộc cùng một luồng xử lý logic.
- Mã lời gọi dùng để nhận diện **một lần** đi qua join point, kể cả khi một phương thức được gọi nhiều lần.
- Quan hệ cha–con giữa các lời gọi giúp tái dựng đường đi, nhưng không đồng nghĩa mọi phương thức con phải có mã tương quan mới.
- Advice phải **khôi phục ngữ cảnh cũ** khi rời scope, kể cả khi xảy ra ngoại lệ, callback hoặc lời gọi lồng nhau.
- Ranh giới thread, tác vụ bất đồng bộ và hệ thống từ xa đòi hỏi một cơ chế truyền ngữ cảnh rõ ràng.

Bài trình bày AOP ở mức khái niệm và kỹ thuật tổng quát. Ví dụ Java thuần minh họa logic mà một around advice có thể thực hiện; không cần một thư viện AOP cụ thể để chạy.

## 2. Phân biệt các mã và dữ liệu ngữ cảnh

| Thành phần | Phạm vi định danh | Thường thay đổi khi nào? | Vai trò |
| --- | --- | --- | --- |
| Correlation ID | Một luồng xử lý logic mà hệ thống định nghĩa | Khi bắt đầu luồng mới không có mã được chấp nhận | Tìm toàn bộ log và sự kiện cùng nghiệp vụ |
| Call ID | Một lần đi qua join point đã chọn | Mỗi lần advice tạo một scope lời gọi mới | Phân biệt các lần gọi, kể cả đệ quy và retry |
| Parent call ID | Lời gọi cha trực tiếp trong mô hình scope đang quan sát | Khi chuyển sang một lời gọi con | Tái dựng quan hệ cha–con |
| Operation name | Loại thao tác, chẳng hạn validateOrder | Theo pointcut hoặc join point | Hiểu hành vi đang được quan sát |
| Trace ID | Một trace theo hợp đồng truy vết được sử dụng | Theo quy tắc hệ thống tracing | Ghép các span của một trace |
| Span ID | Một span cụ thể | Mỗi span mới | Phân biệt đơn vị công việc được trace |

**Correlation ID không mặc nhiên là trace ID**, và **Call ID không mặc nhiên là Span ID**. Một hệ thống có thể thiết kế chúng trùng nhau ở những ranh giới nhất định, nhưng phải mô tả rõ sự ánh xạ đó. Trong tracing phân tán, trace và span còn có ngữ nghĩa riêng về quan hệ cha–con và truyền qua ranh giới tiến trình.

Một ngữ cảnh lời gọi tối thiểu có thể được hình dung như sau:

~~~text
CallContext
  correlationId = "corr-8b29"
  callId        = "call-f17a"
  parentCallId  = "call-a803"
  operation     = "reserveInventory"
~~~

Có thể bổ sung mốc thời gian bắt đầu, thông tin chẩn đoán hoặc dữ liệu nghiệp vụ **được phép** ghi nhận. Không nên biến ngữ cảnh thành một “túi” chứa tùy ý toàn bộ request, mật khẩu, token truy cập hoặc thông tin cá nhân.

## 3. Mã tương quan được tạo ở ranh giới nào?

Điểm quan trọng nhất là xác định thế nào là **một luồng xử lý logic**. Có nhiều lựa chọn hợp lệ:

- Ở biên nhận yêu cầu: tạo một correlation ID cho mỗi yêu cầu mới; các lời gọi con thừa kế ID.
- Khi tiêu thụ một sự kiện từ hàng đợi: nhận ID theo hợp đồng thông điệp, hoặc tạo ID mới nếu đây thực sự là thao tác độc lập.
- Khi bắt đầu một công việc theo lịch: tạo ID cho từng lần chạy, không dùng một ID cố định cho mọi lần chạy.
- Khi xử lý một phần riêng của giao dịch: có thể dùng thêm mã con để phân biệt nhánh nhưng vẫn giữ mã gốc để truy vết quan hệ.

Không phải mọi phương thức match pointcut đều sinh **correlation ID mới**. Nếu advice thực hiện như vậy tại mọi lời gọi, log bên trong cùng một nghiệp vụ bị tách thành những nhóm khác nhau, làm mất mục đích tương quan.

Quy tắc thông dụng:

1. Nếu đã có correlation ID hợp lệ trong scope hiện tại, **kế thừa** mã đó.
2. Nếu chưa có, chọn/khởi tạo correlation ID tại ranh giới đầu vào thích hợp.
3. Với mỗi lần join point được instrument, tạo **call ID riêng** nếu cần phân tích chi tiết.
4. Ghi parentCallId bằng callId của scope hiện tại trước khi bước vào join point con.
5. Khi rời join point, **khôi phục scope cũ** thay vì xóa sạch toàn bộ ngữ cảnh.

Điều số 5 đặc biệt quan trọng: một lời gọi con kết thúc không được làm mất correlation ID hoặc call ID của lời gọi cha vẫn đang chạy.

## 4. Ngữ cảnh sống trong scope của lần gọi, không sống mãi trên thread

Giả sử join point xử lý việc đặt hàng kích hoạt một lời gọi con kiểm tra kho:

~~~text
Thread T1
  enter checkout    correlation=corr-01, call=call-01, parent=-
    enter inventory correlation=corr-01, call=call-02, parent=call-01
    exit  inventory -> khôi phục call=call-01
    enter payment   correlation=corr-01, call=call-03, parent=call-01
    exit  payment   -> khôi phục call=call-01
  exit  checkout    -> khôi phục ngữ cảnh trước checkout
~~~

Lời gọi con giữ cùng correlation ID, nhưng có call ID mới. Sau khi inventory kết thúc, context quay về checkout; không được giữ call-02 trên thread khi bắt đầu payment.

Sự khác biệt giữa **scope lời gọi** và **thread** thường bị bỏ qua:

- Một thread có thể lần lượt xử lý nhiều tác vụ độc lập. Nếu context không được xóa/khôi phục, tác vụ sau có thể mang mã của tác vụ trước.
- Một thao tác logic có thể chuyển qua nhiều thread. ThreadLocal của thread khởi tạo không tự xuất hiện trên thread thực thi tiếp theo.
- Một thao tác bất đồng bộ có thể sống lâu hơn thời gian phương thức gốc còn nằm trên call stack. Giữ ngữ cảnh trong ThreadLocal đến khi future hoàn tất bằng cách trì hoãn dọn dẹp thường là thiết kế sai.

Context theo lời gọi nên là một **giá trị có vòng đời rõ ràng**, còn ThreadLocal (nếu dùng) chỉ là cơ chế truy cập context trong đoạn thực thi đồng bộ trên một thread.

## 5. Vai trò của pointcut, join point và advice

Trong AOP, **pointcut** chọn các join point cần quan sát; **advice** xử lý tại các điểm ấy. Một around advice phù hợp cho bài toán này vì có thể bao quanh việc gọi hành vi đích:

~~~text
around(joinPoint):
    previous = currentContext()
    context  = createChildOrRootContext(previous, joinPoint)
    bind(context)
    try:
        logStart(context, joinPoint)
        result = proceed()
        return result
    catch error:
        recordFailure(context, error)
        throw error
    finally:
        recordExit(context)
        restore(previous)
~~~

Đây là **thuật toán khái niệm**, không phải cú pháp của một framework. Tên và khả năng của proceed, join point và lời khuyên trước/sau phụ thuộc cơ chế AOP đang dùng.

Điểm cần kiểm soát:

- **Lựa chọn phạm vi:** chọn các hàm tạo ranh giới nghiệp vụ hoặc kỹ thuật thực sự cần đo. Instrument toàn bộ hàm nhỏ có thể tạo quá nhiều sự kiện, chi phí cao và cây lời gọi khó đọc.
- **Thứ tự advice:** nếu nhiều aspect cùng bao quanh một join point, aspect nào thiết lập correlation ID trước sẽ quyết định advice còn lại có nhìn thấy context hay không. Phải quy định thứ tự khi cơ chế AOP hỗ trợ nhiều advice.
- **Mỗi lần kích hoạt:** lời gọi đệ quy và lặp nhiều lần cần một call ID riêng cho mỗi lần vào scope. Không dùng chung một biến mutable của đối tượng aspect làm trạng thái của từng lượt gọi.
- **Đường lỗi:** nếu proceed ném lỗi, advice vẫn dọn ngữ cảnh bằng finally và giữ nguyên ngoại lệ nghiệp vụ, trừ khi hợp đồng đã chủ đích quy định biến đổi nó.
- **Bảo toàn kết quả:** chỉ để ghi log/correlation, advice không cần thay đổi giá trị trả về, ngoại lệ hay luồng điều khiển của hành vi đích.

Advice ghi log có thể thất bại độc lập với nghiệp vụ. Trong hệ thống thật, logic telemetry nên được bảo vệ để sự cố ghi log không vô tình che mất ngoại lệ gốc hoặc khiến giao dịch thành công bị biến thành lỗi.

## 6. Ví dụ Java 17+ chạy được: tạo, kế thừa, truyền và khôi phục context

Ví dụ dùng một hàm around(...) để **mô phỏng** hành vi của advice trên các join point. ThreadLocal lưu scope hiện hành trên từng thread; một Context bất biến làm snapshot; hàm propagate(...) chụp scope hiện tại rồi gắn tạm vào tác vụ chuyển sang thread khác.

Để đầu ra kiểm chứng được, mã demo dùng bộ đếm tuần tự; **không dùng bộ đếm này tạo ID trong ứng dụng phân tán thực tế**, vì mỗi tiến trình có thể phát sinh mã trùng nhau. Phần tiếp theo trình bày chính sách ID phù hợp cho production.

Tạo tệp **CallContextDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public final class CallContextDemo {
    record Context(
            String correlationId,
            String callId,
            String parentCallId) {}

    private static final ThreadLocal<Context> CURRENT = new ThreadLocal<>();
    private static final AtomicInteger IDS = new AtomicInteger();

    static void log(String event) {
        Context ctx = CURRENT.get();
        if (ctx == null) {
            System.out.println(event + " context=none");
        } else {
            System.out.println(event
                    + " corr=" + ctx.correlationId()
                    + " call=" + ctx.callId()
                    + " parent=" + ctx.parentCallId());
        }
    }

    static <T> T around(String operation, Supplier<T> proceed) {
        Context previous = CURRENT.get();

        int number = IDS.incrementAndGet();
        String callId = "call-%03d".formatted(number);
        String correlationId = previous == null
                ? "corr-%03d".formatted(number)
                : previous.correlationId();
        String parentId = previous == null ? "-" : previous.callId();

        Context current = new Context(correlationId, callId, parentId);
        CURRENT.set(current);
        try {
            log("enter " + operation);
            return proceed.get();
        } finally {
            log("exit " + operation);
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }

    static Runnable propagate(Runnable task) {
        // Capture scope ở thread đang lập lịch.
        Context captured = CURRENT.get();

        return () -> {
            // Thread thực thi có thể đang mang scope riêng.
            Context previous = CURRENT.get();
            try {
                if (captured == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(captured);
                }
                task.run();
            } finally {
                // Trả thread thực thi về trạng thái ban đầu.
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
            }
        };
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            around("checkout", () -> {
                log("business checkout");

                around("inventory", () -> {
                    log("business inventory");
                    return null;
                });

                CompletableFuture.runAsync(
                        propagate(() -> around("shipment", () -> {
                            log("business shipment");
                            return null;
                        })),
                        pool
                ).join();

                log("back checkout");
                return null;
            });

            System.out.println("main context clean="
                    + (CURRENT.get() == null));

            CompletableFuture.runAsync(
                    () -> System.out.println("worker context clean="
                            + (CURRENT.get() == null)),
                    pool
            ).join();

            try {
                around("failing", () -> {
                    throw new IllegalStateException("boom");
                });
            } catch (IllegalStateException expected) {
                System.out.println("caller received=" + expected.getMessage());
            }

            System.out.println("main after exception clean="
                    + (CURRENT.get() == null));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac CallContextDemo.java
java CallContextDemo
~~~

Đầu ra:

~~~text
enter checkout corr=corr-001 call=call-001 parent=-
business checkout corr=corr-001 call=call-001 parent=-
enter inventory corr=corr-001 call=call-002 parent=call-001
business inventory corr=corr-001 call=call-002 parent=call-001
exit inventory corr=corr-001 call=call-002 parent=call-001
enter shipment corr=corr-001 call=call-003 parent=call-001
business shipment corr=corr-001 call=call-003 parent=call-001
exit shipment corr=corr-001 call=call-003 parent=call-001
back checkout corr=corr-001 call=call-001 parent=-
exit checkout corr=corr-001 call=call-001 parent=-
main context clean=true
worker context clean=true
enter failing corr=corr-004 call=call-004 parent=-
exit failing corr=corr-004 call=call-004 parent=-
caller received=boom
main after exception clean=true
~~~

Giải thích:

1. checkout là scope gốc nên sinh corr-001 và call-001.
2. inventory là lời gọi lồng nhau: correlation ID vẫn là corr-001, call ID đổi thành call-002 và parent trỏ tới call-001.
3. propagate chụp context của checkout **khi tạo Runnable**; thread trong pool nhận ngữ cảnh đó trước khi chạy shipment. Shipment vì vậy dùng corr-001, tạo call-003 và nhận call-001 làm parent.
4. Cuối mỗi scope, finally khôi phục context trước đó. Sau checkout, thread main không còn scope; sau shipment, thread pool không còn scope. Kiểm tra một tác vụ mới trên thread pool xác nhận không rò context.
5. failing ném ngoại lệ; finally vẫn chạy, sau đó người gọi vẫn nhận IllegalStateException như bình thường.

**Giới hạn của demo:** wrapper quanh Supplier/Runnable chỉ cho thấy thuật toán của advice và context propagation. Nó không dệt mã tại join point, không tự áp dụng cho mọi lời gọi trong chương trình và không thực hiện tracing phân tán. Khi dùng AOP thật, lựa chọn join point và phương thức proceed phải tuân theo ngữ nghĩa của công cụ dệt tương ứng.

## 7. Thiết kế mã tương quan thực tế

Trong môi trường nhiều tiến trình, mã tương quan phải đủ khó trùng lặp trong phạm vi quan sát dự kiến. Có thể dùng UUID phiên bản ngẫu nhiên do thư viện chuẩn Java cung cấp:

~~~java
import java.util.UUID;

String correlationId = UUID.randomUUID().toString();
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. Đầu ra là một giá trị UUID thay đổi qua mỗi lần chạy.

Các nguyên tắc tạo và dùng mã:

- **Tạo một lần ở ranh giới gốc phù hợp**, sau đó kế thừa cho các lời gọi thuộc cùng luồng xử lý.
- **Không lấy ID theo thread ID**, vì thread pool tái sử dụng thread cho nhiều yêu cầu và một yêu cầu có thể đi qua nhiều thread.
- **Không dùng đồng hồ đơn thuần** làm mã duy nhất: nhiều tiến trình hoặc nhiều lời gọi đồng thời có thể tạo cùng giá trị.
- **Không dựa vào tính bí mật của ID** để kiểm soát truy cập. Correlation ID là khóa quan sát; nó không xác thực người gọi.
- **Định dạng dễ vận hành:** giới hạn độ dài, tập ký tự, chuẩn hóa cách đọc/ghi và nhãn log. Nếu nhận ID từ bên ngoài, xác thực giá trị theo chính sách trước khi giữ nguyên.
- **Phạm vi đủ rõ:** một yêu cầu, một tác vụ, một job run hoặc một luồng liên quan có thể là đơn vị khác nhau. Không dùng một correlation ID vĩnh viễn cho tất cả hành động của một người dùng.

Khi có ID từ phía gọi đến, có thể chấp nhận nếu ID hợp lệ theo hợp đồng và mức tin cậy của biên hệ thống. Nếu trống, sai định dạng hoặc vượt giới hạn, tạo mã mới và ghi nhận việc chuẩn hóa theo chính sách. Không giả định bất kỳ header do client cung cấp đều đáng tin.

Để tái dựng cây lời gọi, call ID cũng cần chính sách uniqueness thích hợp. Bộ đếm per-process có thể đủ cho một trace ngắn nếu ghép với process ID hoặc correlation ID theo hợp đồng, nhưng không nên xem call-001 là định danh toàn cục. Việc định dạng trong demo chỉ phục vụ học tập.

## 8. Lựa chọn cách giữ context

Một số chiến lược phổ biến trong Java và AOP:

### 8.1. Truyền context tường minh bằng tham số

~~~text
processOrder(context, order)
    -> reserveInventory(context, order)
    -> chargePayment(context, order)
~~~

Ưu điểm là phụ thuộc hiện rõ ở chữ ký, dễ kiểm thử và không phụ thuộc thread. Nhược điểm là cần thay đổi API và truyền qua nhiều tầng, đôi khi xâm lấn các phương thức nghiệp vụ.

### 8.2. Giữ context hiện hành trong ThreadLocal

Around advice thiết lập giá trị trong thời gian join point chạy, sau đó restore/remove trong finally. Ưu điểm là giảm việc chuyển tham số trong call stack đồng bộ; nhược điểm là rủi ro rò rỉ trên thread pool và không tự truyền sang thread khác.

Nếu trong context chứa đối tượng mutable được nhiều task cùng chia sẻ, việc copy tham chiếu sang thread khác **không biến nó thành thread-safe**. Ưu tiên snapshot bất biến và dữ liệu vừa đủ. Không giữ cả HTTP request, session hay đồ thị đối tượng lớn nếu chỉ cần một số ID.

### 8.3. Context carrier theo cơ chế runtime

Một số runtime cung cấp context scope hoặc cơ chế lan truyền riêng. Dù triển khai ra sao, cần đảm bảo ba tính chất:

1. Có thể xác định ngữ cảnh nào đang hoạt động tại join point.
2. Có thể truyền ngữ cảnh qua ranh giới thực thi cần thiết.
3. Có thể kết thúc scope và khôi phục ngữ cảnh trước đó một cách chắc chắn.

Không nên trộn nhiều cơ chế giữ context mà không xác định thứ tự ưu tiên và nguồn dữ liệu chuẩn; hai bản context khác nhau có thể khiến log cùng một tác vụ mang ID khác nhau.

## 9. Lời gọi lồng nhau, đệ quy, retry và fan-out

### 9.1. Lồng nhau và đệ quy

Một phương thức gọi chính nó ba lần có thể tạo ba call ID khác nhau trên cùng correlation ID, với quan hệ parent nối tiếp. Nếu mỗi lượt đệ quy tạo correlation ID mới, rất khó liên kết về lời gọi gốc.

Khôi phục ngữ cảnh theo nguyên tắc stack:

~~~text
before call A:  context=null
inside call A:  context=A
inside call B:  context=B (parent=A)
after call B:   context=A
after call A:   context=null
~~~

Việc restore đặc biệt cần thiết khi cùng thread đang xử lý lồng nhau; gọi remove() vô điều kiện ở cuối B sẽ làm mất A.

### 9.2. Retry

Một thao tác có thể retry ba lần. Có ít nhất hai mô hình hợp lý:

- **Một correlation ID cho yêu cầu logic**, thêm attempt number và call ID riêng cho từng lần thử.
- **Một correlation ID cho mỗi lần thử độc lập**, nhưng có một mã gốc liên kết tất cả lần thử.

Chọn theo câu hỏi vận hành cần trả lời. Nếu theo mô hình đầu, một lỗi trong attempt 1 không nhất thiết là kết quả cuối của request. Advice và metric phải phân biệt **attempt failed** với **operation failed**.

### 9.3. Fan-out sang nhiều tác vụ

Một join point có thể khởi tạo nhiều tác vụ nền. Tất cả tác vụ thuộc cùng luồng logic có thể kế thừa correlation ID chung, nhưng mỗi tác vụ/nhánh cần call ID riêng nếu có instrument. Không chia sẻ một đối tượng mutable và để các nhánh đồng thời ghi đè callId hiện tại.

~~~text
corr-42 / parent=call-01
    ├── task A -> call-02
    ├── task B -> call-03
    └── task C -> call-04
~~~

Khi hợp nhất kết quả, hãy mô tả rõ ranh giới hoàn tất: chỉ callback của task A xong không có nghĩa tất cả task B/C đã hoàn tất. Mã tương quan phục vụ liên kết sự kiện; nó **không tự cung cấp** cơ chế join hoặc đồng bộ các tác vụ.

### 9.4. Công việc độc lập được khởi tạo trong scope hiện tại

Không phải tác vụ nào được spawn từ một request cũng phải giữ cùng correlation ID. Ví dụ, gửi một công việc độc lập để chạy sau nhiều giờ có thể cần correlation ID riêng, cộng với liên kết “originating request”. Cần chọn theo ý nghĩa nghiệp vụ và chính sách giữ dữ liệu.

## 10. Lan truyền context qua ranh giới bất đồng bộ

**ThreadLocal không tự chuyển ngữ cảnh qua executor, future hoặc callback.** Nếu advice lưu ID vào ThreadLocal tại thread gọi, callback trên thread khác có thể đọc null hoặc dữ liệu cũ còn sót lại.

Một cách truyền đúng theo scope:

~~~text
Thread gọi:
    current = requestContext
    snapshot = capture(current)
    submit(wrap(task, snapshot))

Thread worker:
    old = currentContext
    install(snapshot)
    try:
        execute(task)
    finally:
        restore(old)
~~~

Trong đoạn Java ở trên, propagate(...) thực hiện đúng trình tự này. Cần capture trước khi context của thread gọi kết thúc; nếu capture quá muộn, snapshot có thể null hoặc thuộc lời gọi khác.

Có các trường hợp đáng lưu ý:

**CompletionStage/CompletableFuture.** Callback có thể chạy trên thread hoàn tất future, thread gọi hoặc executor được cấu hình, tùy API và kiểu callback. Không dựa vào ThreadLocal hiện hành của một thread cụ thể. Với callback cần context, hãy bọc callback bằng một scope snapshot riêng hoặc dùng carrier do runtime hỗ trợ. Việc lời gọi gốc trả về CompletableFuture không làm cho advice tự động bao phủ phần xử lý sau khi hoàn tất.

**Future được trả về ngay.** Advice quanh lời gọi tạo future chỉ bao quanh thời gian tạo/lấy handle. Nếu muốn log trạng thái cuối, phải quan sát completion theo hợp đồng; nếu muốn context trong callback, cần truyền context đến callback theo cách rõ ràng.

**Publisher hoặc API nhiều lượt tiêu thụ.** Việc tạo một publisher khác với việc có người subscribe. Một đối tượng publisher có thể có nhiều subscription, mỗi subscription nên có scope quan sát riêng. Kế thừa context lúc tạo publisher hay lúc subscribe là quyết định thiết kế phải được mô tả theo tính chất hot/cold và hợp đồng dữ liệu.

**Chuyển thread qua nhiều bước.** Mỗi bước có thể chuyển sang executor khác. Chỉ bọc Runnable ở bước đầu không đảm bảo toàn bộ callback về sau đều có context; cần propagation tại mọi ranh giới mà ngữ cảnh còn được dùng.

**Hủy và timeout.** Nếu callback cuối không chạy theo đường thông thường, cơ chế dọn ngữ cảnh không được phụ thuộc vào một sự kiện duy nhất chưa chắc được kích hoạt. Scope của worker phải được restore trong finally khi worker rời phần việc của nó; lifecycle kết quả bất đồng bộ được theo dõi riêng.

Không nên giữ ThreadLocal của thread gọi tồn tại đến khi tác vụ nền hoàn tất: thread gọi có thể đã được giao nhiệm vụ khác. Thay vào đó, giữ một snapshot bất biến để truyền theo từng đoạn thực thi.

## 11. Truyền mã giữa các tiến trình

Khi luồng xử lý vượt qua HTTP, hàng đợi hoặc giao thức RPC, ThreadLocal trong một tiến trình không có tác dụng ở tiến trình khác. Cần **đưa thông tin tương quan vào metadata trên thông điệp** theo hợp đồng đã thống nhất.

Ví dụ minh họa về ý tưởng, không phải một chuẩn header bắt buộc:

~~~text
Service A:
  correlationId=corr-8b29
  outgoing request:
    X-Correlation-ID: corr-8b29

Service B:
  nhận header và kiểm tra định dạng/chính sách tin cậy
  gắn correlationId=corr-8b29 trong scope xử lý
  tạo call/span mới tùy nhu cầu quan sát
  truyền tiếp khi gọi Service C
~~~

Nếu hệ thống đã sử dụng chuẩn truy vết phân tán như **W3C Trace Context**, cần tuân thủ ngữ nghĩa và định dạng các trường của chuẩn (ví dụ traceparent/tracestate) bằng công cụ tương thích. Đừng tự coi một chuỗi X-Correlation-ID là traceparent, hoặc tự lắp một trace ID không hợp lệ rồi gọi nó là dữ liệu tracing chuẩn.

Ở các ranh giới không tin cậy, hãy giới hạn độ dài, lọc ký tự điều khiển/ngắt dòng, xác định được nguồn gốc ID và có chính sách tạo mới. Không cho phép metadata tương quan thay thế kiểm tra quyền truy cập hoặc xác thực người dùng.

Với thông điệp được retry hoặc xử lý lại nhiều lần, correlation ID có thể giữ nguyên nhưng **lần xử lý** cần ID riêng. Điều này giúp phân biệt việc nhận một message nhiều lần với việc nghiệp vụ tạo nhiều message khác nhau.

## 12. Ghi log có cấu trúc và tránh gây nghẽn hệ thống quan sát

Log nên ghi các trường riêng thay vì nối tất cả metadata vào một chuỗi khó phân tích:

~~~text
timestamp=... level=INFO event=inventory.reserved
correlation_id=corr-8b29
call_id=call-f17a
parent_call_id=call-a803
operation=reserveInventory
outcome=success
duration_ms=12
~~~

Đây là **minh họa định dạng log**, không phải stdout của ví dụ Java. Tùy hệ thống, có thể dùng JSON hoặc bộ ghi log hỗ trợ thuộc tính có cấu trúc.

Nên phân biệt:

- **Log:** ghi correlationId, callId và operation để truy vấn chính xác.
- **Trace:** dùng trace/span theo mô hình tracing, lưu quan hệ cha–con và các mốc thời gian.
- **Metric:** đếm số lần gọi, độ trễ và lỗi theo nhãn có tập giá trị giới hạn như operation/outcome.

Không đưa correlation ID, call ID hoặc user ID có số lượng giá trị gần như vô hạn vào **label của metric có cardinality cao**, vì có thể làm tăng đột biến số time series và chi phí lưu trữ. ID cá biệt phù hợp hơn với log hoặc trace, trong khi metric tổng hợp nên có nhãn ổn định.

Advice quan sát cũng tạo overhead: sinh ID, tạo context, lưu log, đo thời gian, propagate callback. Hãy lựa chọn pointcut có chủ đích; có thể giảm số sự kiện thông qua lọc, sampling và tối ưu exporter. Dù sampling, vẫn phải thống nhất chính sách tạo/lan truyền ID nếu các thành phần phụ thuộc vào đó để liên kết sự kiện.

## 13. Quy tắc an toàn dữ liệu khi gắn ngữ cảnh

Không sử dụng context như một kênh truyền dữ liệu nhạy cảm không kiểm soát. Các nguyên tắc thực hành:

1. Dùng **ít trường cần thiết**: mã tương quan, mã lời gọi, tên thao tác, một vài thông tin chẩn đoán đã được phê duyệt.
2. Không ghi password, secret, access token, khóa riêng, nội dung định danh cá nhân hoặc toàn bộ payload vào log chỉ vì aspect có thể truy cập chúng.
3. Xem ID nhận từ client là dữ liệu bên ngoài. Trước khi cho vào log/header, xác thực độ dài và ký tự để tránh log injection và header injection.
4. Không dùng correlation ID để quyết định quyền truy cập, tenant hoặc người dùng đang đăng nhập; đây là dữ liệu quan sát.
5. Nếu cần tenant hoặc thông tin bảo mật để chạy nghiệp vụ, lấy từ nguồn đã được xác thực và truyền theo chính sách riêng, không tin giá trị metadata do bên gửi tự khai.
6. Xác định thời gian lưu dữ liệu log và quy tắc chia sẻ ID trên các ranh giới tổ chức.

Một ID trông ngẫu nhiên vẫn có thể được dùng để tra cứu hoạt động của người dùng. Do đó, việc công khai hay giữ ID trong log/tracing cũng cần chính sách dữ liệu phù hợp.

## 14. Những lỗi triển khai thường gặp

### 14.1. Tạo correlation ID mới tại mọi join point

**Hậu quả:** các log của checkout và inventory có ID khác nhau, không tìm được cùng một yêu cầu.

**Sửa:** chỉ tạo ở root nếu chưa có mã, các scope con kế thừa cùng correlation ID; dùng call ID riêng cho từng lượt gọi.

### 14.2. Chỉ xóa ThreadLocal ở cuối lời gọi con

**Hậu quả:** parent scope biến mất dù vẫn đang chạy.

**Sửa:** lưu previous trước khi set, cuối cùng restore previous; remove khi previous thực sự null.

### 14.3. Quên finally khi proceed ném lỗi

**Hậu quả:** thread pool tiếp tục chạy tác vụ khác trong context cũ; log bị gắn sai ID, có thể lộ dữ liệu giữa các yêu cầu.

**Sửa:** mọi đường ra khỏi scope đều đi qua finally, bao gồm ngoại lệ đồng bộ. Với callback và worker, từng đoạn thực thi cũng cần finally riêng.

### 14.4. Dùng biến instance của aspect làm currentCorrelationId

**Hậu quả:** nhiều thread/requests có thể ghi đè lẫn nhau nếu aspect được dùng chung.

**Sửa:** không đặt dữ liệu per-call vào state mutable dùng chung không đồng bộ; dùng context được scope hóa hoặc truyền tường minh. Khi có nhiều thread cùng chia sẻ context, tránh mutable state không an toàn.

### 14.5. Nghĩ rằng CompletableFuture tự lan truyền ThreadLocal

**Hậu quả:** callback chạy ở thread khác thiếu correlation ID.

**Sửa:** capture và bind context tại callback/task boundary; luôn restore context trước đó khi xong. Không giả định một executor tự truyền context nếu hợp đồng của nó không nói vậy.

### 14.6. Trộn lẫn correlation ID với call/span ID

**Hậu quả:** sơ đồ lời gọi không thể hiện đúng quan hệ cha–con, hoặc các lời gọi con bị tách thành trace không liên quan.

**Sửa:** xác định rõ mô hình ID, khi nào kế thừa và khi nào tạo mới; nếu có hệ thống tracing thì dùng đúng API/chuẩn của hệ thống đó.

### 14.7. Ghi ID vào metric labels

**Hậu quả:** số lượng chuỗi thời gian tăng theo số request, khiến metric khó vận hành.

**Sửa:** đưa ID vào log/tracing và dùng metric labels có cardinality giới hạn.

### 14.8. Chấp nhận mọi correlation ID đầu vào không kiểm tra

**Hậu quả:** giá trị quá dài hoặc có ký tự điều khiển có thể làm hỏng log, metadata hoặc truyền qua hệ thống khác.

**Sửa:** thiết lập giới hạn độ dài, ký tự hợp lệ, xử lý invalid và chính sách trust boundary; ID không mang quyền bảo mật.

### 14.9. Tạo context sau khi log bắt đầu hoặc kết thúc scope quá sớm

**Hậu quả:** một phần log đầu/cuối của thao tác không có cùng ID hoặc task nền bắt đầu sau khi context bị xóa mà không được capture.

**Sửa:** bind trước khi ghi sự kiện có ý nghĩa đầu tiên, capture trước khi lập lịch task, restore khi **đoạn thực thi hiện tại** kết thúc. Việc đo thời điểm hoàn tất logic của tác vụ async là trách nhiệm của observer riêng.

### 14.10. Ghi “operation success” khi join point chỉ vừa trả về handle

**Hậu quả:** future có thể hoàn tất lỗi sau đó nhưng log đã báo thành công.

**Sửa:** đặt tên sự kiện rõ ràng, chẳng hạn invocation-returned và async-completed. Callback hoàn tất phải phân biệt success, failure, cancel và timeout theo hợp đồng API.

## 15. Bảng kiểm trước khi triển khai một aspect tương quan

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Root của luồng xử lý nằm ở đâu? | Có ranh giới tạo/nhận correlation ID rõ ràng |
| Join point nào được theo dõi? | Pointcut đủ chính xác; tránh lặp quá mức |
| Lời gọi con được định danh thế nào? | Giữ correlation ID, tạo call ID, ghi parent phù hợp |
| Khi lời gọi con kết thúc? | Khôi phục đúng context của cha |
| Khi có throw đồng bộ? | Không mất ngoại lệ gốc; finally dọn scope |
| Khi chuyển thread? | Capture, bind, execute và restore theo mỗi boundary |
| Khi lời gọi trả về future/publisher? | Phân biệt kết thúc invocation với hoàn tất logic |
| Khi đi qua dịch vụ khác? | Có metadata propagation, validate nguồn vào và đúng chuẩn tracing nếu dùng |
| Khi nhiều lời gọi chạy đồng thời? | Không có mutable per-call state dùng chung gây race |
| Khi ghi log/tracing/metric? | Tên trường thống nhất; ID không thành nhãn metric cardinality cao |
| Khi dữ liệu nhạy cảm có trong request? | Chỉ đưa metadata được phép, tránh secret/payload |
| Khi test? | Có nested, concurrent, async, exception, retry và khôi phục sau khi kết thúc |

## 16. Bài tập tự kiểm tra

**Tình huống 1.** Yêu cầu gốc có corr-A, lần gọi checkout là call-01. Nó gọi inventory hai lần nối tiếp. Hai log inventory cần những mã nào?

**Trả lời:** cả hai cùng corr-A, nhưng có hai call ID khác nhau; parentCallId có thể đều là call-01 nếu mỗi lần được gọi trực tiếp từ checkout.

**Tình huống 2.** Lời gọi inventory kết thúc và advice gọi CURRENT.remove(), trong khi checkout vẫn đang chạy. Điều gì sai?

**Trả lời:** checkout mất context của nó. Advice phải restore giá trị previous đã lưu khi bắt đầu inventory, không xóa vô điều kiện.

**Tình huống 3.** Checkout lập lịch một Runnable lên thread pool. Advice khôi phục ThreadLocal ở thread checkout ngay sau khi Runnable được submit. Làm thế nào để worker vẫn có mã tương quan?

**Trả lời:** chụp snapshot trước khi lập lịch, gắn snapshot trong scope của Runnable khi worker chạy, sau đó restore ThreadLocal của worker bằng finally. Dọn context ở thread checkout vẫn phải diễn ra đúng thời điểm.

**Tình huống 4.** Một future được trả về thành công nhưng hoàn tất bằng ngoại lệ sau 100 ms. Có nên log nghiệp vụ thành công ở after-returning advice không?

**Trả lời:** không. Đó chỉ là return của join point. Nếu cần outcome của tác vụ logic, theo dõi completion và ghi failure khi future hoàn tất ngoại lệ.

**Tình huống 5.** Hệ thống dùng UUID correlation ID và đưa ID đó làm label cho histogram latency. Có vấn đề gì?

**Trả lời:** mỗi yêu cầu có thể tạo một time series mới, gây cardinality rất cao. Thay bằng nhãn operation/outcome có tập giá trị nhỏ; giữ correlation ID trong log hoặc trace.

**Tình huống 6.** Một request có ba nhánh xử lý song song. Có nên chia sẻ cùng một đối tượng Context mutable để các nhánh cập nhật callId?

**Trả lời:** không, nếu các nhánh cùng sửa callId thì dễ xảy ra race và gắn log sai. Chia sẻ trường correlation ID bất biến; mỗi nhánh tạo scope và call ID riêng hoặc dùng cơ chế context propagation tương đương.

## 17. Ghi nhớ

Cách xây dựng aspect tương quan đáng tin cậy là: **nhận/tạo correlation ID tại ranh giới luồng xử lý, kế thừa ID xuống các lời gọi con, tạo call ID theo từng join point cần quan sát, gắn context trong scope, rồi luôn khôi phục context cũ**. Khi đi qua thread, callback hoặc dịch vụ khác, cần truyền context theo hợp đồng riêng. Khi quan sát future hoặc publisher, phải tách sự kiện trả về của lời gọi với việc hoàn tất công việc bất đồng bộ.

Mã tương quan giúp trả lời “những sự kiện này thuộc cùng một luồng xử lý nào?”, còn ngữ cảnh lời gọi giúp trả lời “sự kiện này diễn ra ở lượt thực thi nào và có quan hệ gì với các lượt khác?”. Aspect phát huy tác dụng khi áp dụng hai quy tắc đó nhất quán, đúng ranh giới và không làm đổi hành vi nghiệp vụ.