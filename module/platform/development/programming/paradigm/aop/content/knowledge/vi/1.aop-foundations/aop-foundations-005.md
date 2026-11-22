# Tách hành vi cắt ngang khỏi luồng nghiệp vụ bằng AOP

## 1. Vấn đề cần giải quyết

Trong một ứng dụng, **luồng nghiệp vụ** là chuỗi hành động tạo ra kết quả mà người dùng hoặc hệ thống yêu cầu: kiểm tra điều kiện của đơn hàng, tính tiền, đặt chỗ, xác nhận giao dịch, cập nhật trạng thái. Ngoài các bước đó, nhiều thao tác kỹ thuật cần xuất hiện ở nhiều nơi: ghi nhật ký, đo thời gian, kiểm soát truy cập, theo dõi lỗi, gắn mã truy vết, hoặc xác định ranh giới giao dịch.

Những thao tác lặp lại qua nhiều chức năng được gọi là **hành vi cắt ngang (cross-cutting concerns)**. Chẳng hạn, cả `placeOrder()`, `cancelOrder()` và `refund()` đều có thể cần kiểm tra quyền và ghi audit, dù mỗi hàm xử lý một quy tắc nghiệp vụ riêng.

Nếu nhúng mọi hành vi kỹ thuật vào từng hàm nghiệp vụ, chúng ta dễ gặp:

- **Trộn trách nhiệm:** khó nhận ra hàm thực sự làm gì vì mã ghi log, đo thời gian và xử lý lỗi bao quanh mã nghiệp vụ.
- **Phân tán và lặp:** một thay đổi trong chuẩn audit phải sửa nhiều nơi; có chỗ quên ghi hoặc ghi không nhất quán.
- **Ràng buộc không cần thiết:** mã nghiệp vụ phụ thuộc trực tiếp vào công cụ logging, tracing, metrics hoặc cơ chế điều phối kỹ thuật.
- **Khó kiểm thử và bảo trì:** kiểm thử quy tắc đặt hàng bị kéo theo nhiều tác dụng phụ; thêm một chính sách chung có nguy cơ làm hỏng nhiều luồng.
- **Sai lệch chính sách:** mỗi nhóm tự đặt thứ tự kiểm quyền, thực thi, ghi kết quả, khiến cùng một loại hành động được xử lý khác nhau.

**Mục tiêu của AOP (Aspect-Oriented Programming)** là mô-đun hóa những hành vi cắt ngang, định nghĩa *ở đâu* chúng cần áp dụng và *khi nào* chúng chạy, để mã nghiệp vụ tập trung vào nghiệp vụ. AOP bổ sung cho thiết kế hướng đối tượng; nó không thay thế việc chia lớp, phân lớp trách nhiệm hoặc thiết kế miền.

## 2. Nhận diện đúng ranh giới giữa nghiệp vụ và hành vi cắt ngang

| Loại trách nhiệm | Ví dụ | Nơi thường phù hợp |
| --- | --- | --- |
| Nghiệp vụ cốt lõi | Số lượng mua phải dương; kho còn đủ hàng; tính tổng tiền theo chính sách bán hàng | Phương thức, đối tượng và dịch vụ miền |
| Hành vi cắt ngang | Đo độ trễ của lời gọi; ghi sự kiện audit; gắn trace ID; ghi nhận lỗi chung | Aspect hoặc cơ chế bao quanh điểm thực thi |
| Trách nhiệm phối hợp | Chọn bước tiếp theo; gọi nhiều dịch vụ theo thứ tự; quản lý kết quả tác vụ | Lớp điều phối/use case; chỉ dùng aspect nếu thực sự là chính sách cắt ngang |

Không phải cứ một đoạn mã xuất hiện ở nhiều hàm thì phải chuyển thành aspect. Ví dụ, quy tắc **“không được hủy đơn đã giao”** là bất biến nghiệp vụ: nó phải ở nơi quản lý trạng thái đơn hàng. Việc **“mỗi thao tác hủy đơn cần ghi lại ai đã thực hiện và kết quả ra sao”** có thể là chính sách audit dùng chung.

Tương tự, kiểm tra đăng nhập tại một ranh giới kỹ thuật có thể là hành vi cắt ngang; nhưng quyết định người mua có được hủy **đơn hàng cụ thể** hay không thường cần chính trạng thái và quyền sở hữu của đơn, vì vậy không nên giấu toàn bộ quyết định miền trong một aspect khó nhìn thấy.

Có thể tự hỏi ba câu:

1. Nếu bỏ phần kỹ thuật này đi, thuật toán nghiệp vụ còn mô tả đúng bài toán không?
2. Có thể áp dụng **cùng một chính sách** tại nhiều điểm mà không cần biết chi tiết tính toán của từng nghiệp vụ không?
3. Có thể nêu rõ vị trí áp dụng, thứ tự chạy và hành vi khi thất bại không?

Nếu câu trả lời chủ yếu là “có”, đây là ứng viên tốt để tách thành hành vi cắt ngang.

## 3. Các khái niệm AOP giúp việc tách có thể thực thi

- **Aspect:** mô-đun chứa một mối quan tâm cắt ngang, ví dụ audit hoặc đo thời gian. Một aspect có thể chứa chính sách chọn điểm áp dụng và logic bổ sung.
- **Join point (điểm nối):** một vị trí thực thi có thể bị can thiệp, thường là lời gọi hoặc lần thực thi phương thức; tập join point thực tế tùy vào cơ chế AOP.
- **Pointcut (bộ chọn điểm nối):** điều kiện chọn *những join point nào* được áp dụng, chẳng hạn “mọi lần thực thi thao tác tạo đơn hàng”. Pointcut quá rộng dễ gây tác dụng phụ; quá hẹp khiến sót luồng.
- **Advice (hành vi được chèn):** phần mã thực thi tại join point đã chọn.
- **Target:** đối tượng hoặc phần mã nghiệp vụ gốc.
- **Weaving (kết hợp):** quá trình gắn aspect vào luồng thực thi; có thể được thực hiện bằng mã bao, proxy, biến đổi bytecode khi biên dịch hoặc khi nạp lớp, tùy công nghệ.

Các vị trí advice thường được mô tả như sau:

| Loại advice | Thời điểm / trách nhiệm |
| --- | --- |
| **Before** | Trước khi xử lý mục tiêu; phù hợp kiểm tra điều kiện kỹ thuật hoặc ghi sự kiện bắt đầu |
| **After returning** | Khi mục tiêu hoàn thành bình thường; chỉ có kết quả thành công |
| **After throwing** | Khi mục tiêu ném ngoại lệ; thường để ghi nhận thất bại rồi bảo toàn lỗi gốc |
| **After / finally** | Khi mục tiêu kết thúc, dù thành công hay lỗi; phù hợp dọn dẹp hoặc đo thời gian |
| **Around** | Bao lấy toàn bộ lời gọi; có thể thực hiện trước/sau, đọc kết quả, xử lý lỗi và quyết định có gọi tiếp hay không |

Trong `around`, thao tác chuyển quyền điều khiển tới mã gốc thường được gọi là **proceed**. Nếu không gọi `proceed`, nghiệp vụ có thể không chạy; gọi nhiều lần có thể khiến nghiệp vụ chạy nhiều lần. Đây là quyền rất mạnh, phải dùng có chủ đích.

Hình dung luồng xử lý:

~~~text
Người gọi
  |
  v
[Pointcut có chọn lần gọi này?] -- không --> [Nghiệp vụ]
  |
  có
  v
[Before / phần trước của Around]
  |
  v
[Nghiệp vụ gốc (proceed)]
  | thành công                 | ngoại lệ
  v                            v
[After returning]           [After throwing]
  |                            |
  +------------+---------------+
               v
      [After / finally]
               |
               v
        Trả kết quả hoặc ném lỗi gốc
~~~

Đây là mô hình ý niệm: từng cơ chế AOP có quy tắc riêng về thứ tự các advice và cách biểu diễn điểm nối; không suy ra rằng mọi cách triển khai đều có cùng khả năng can thiệp.

## 4. Ví dụ Java 17+: nghiệp vụ độc lập, audit và metrics nằm ngoài

Xét thao tác tạo đơn hàng. Điều kiện số lượng mua phải dương thuộc miền nghiệp vụ; audit và đo thời gian là chính sách cắt ngang. Ví dụ dùng **JDK dynamic proxy** để minh họa một kiểu kết hợp tại ranh giới lời gọi qua interface. Nó không phải một bộ máy AOP tổng quát: pointcut ở đây chỉ là một `Predicate<Method>` do ta định nghĩa.

Tạo tệp `AopBoundaryDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.function.Predicate;

public class AopBoundaryDemo {
    interface Checkout {
        String placeOrder(String item, int quantity);
        String status();
    }

    // Chỉ xử lý quy tắc nghiệp vụ.
    static final class CheckoutCore implements Checkout {
        @Override
        public String placeOrder(String item, int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            System.out.println("BUSINESS: order accepted");
            return item + " x" + quantity;
        }

        @Override
        public String status() {
            return "READY";
        }
    }

    // Nơi thu thập dữ liệu đo lường.
    static final class Metrics {
        static int calls;
        static long totalNanos;

        static void record(long elapsedNanos) {
            calls++;
            totalNanos += elapsedNanos;
        }
    }

    // Bao lời gọi được chọn bằng một chính sách dùng chung.
    static final class CrossCuttingHandler implements InvocationHandler {
        private final Object target;
        private final Predicate<Method> pointcut;

        CrossCuttingHandler(Object target, Predicate<Method> pointcut) {
            this.target = target;
            this.pointcut = pointcut;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            if (!pointcut.test(method)) {
                return invokeTarget(method, args);
            }

            System.out.println("AUDIT: begin");
            long started = System.nanoTime();
            try {
                Object result = invokeTarget(method, args);
                System.out.println("AUDIT: success");
                return result;
            } catch (Throwable cause) {
                System.out.println("AUDIT: failed");
                throw cause;
            } finally {
                Metrics.record(System.nanoTime() - started);
            }
        }

        private Object invokeTarget(Method method, Object[] args)
                throws Throwable {
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException wrapped) {
                throw wrapped.getCause();
            }
        }
    }

    public static void main(String[] args) {
        Checkout core = new CheckoutCore();
        Predicate<Method> pointcut = method ->
                method.getName().equals("placeOrder")
                && method.getParameterCount() == 2;

        Checkout observed = (Checkout) Proxy.newProxyInstance(
                Checkout.class.getClassLoader(),
                new Class<?>[] { Checkout.class },
                new CrossCuttingHandler(core, pointcut));

        System.out.println("STATUS: " + observed.status());
        System.out.println("RESULT: " + observed.placeOrder("Book", 2));
        try {
            observed.placeOrder("Book", 0);
        } catch (IllegalArgumentException e) {
            System.out.println("ERROR: " + e.getMessage());
        }
        System.out.println("METRIC: measured calls = " + Metrics.calls);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AopBoundaryDemo.java
java AopBoundaryDemo
~~~

Kết quả chuẩn:

~~~text
STATUS: READY
AUDIT: begin
BUSINESS: order accepted
AUDIT: success
RESULT: Book x2
AUDIT: begin
AUDIT: failed
ERROR: quantity must be positive
METRIC: measured calls = 2
~~~

**Cách đọc kết quả:**

1. `status()` không khớp pointcut nên đi thẳng tới `CheckoutCore.status()`, không tạo audit hay metrics.
2. `placeOrder("Book", 2)` khớp: audit bắt đầu → nghiệp vụ chạy → audit thành công → kết quả trả về cho người gọi.
3. `placeOrder("Book", 0)` cũng khớp: nghiệp vụ ném `IllegalArgumentException` → audit thất bại → metrics vẫn ghi trong `finally` → ngoại lệ gốc tới người gọi.
4. `InvocationTargetException` là lớp bọc của lời gọi phản chiếu; `invokeTarget()` bóc lỗi này để người gọi nhận nguyên nhân gốc. Phần đo thời gian dùng `System.nanoTime()`, không in số nano giây vì mỗi lần chạy khác nhau.

Điểm then chốt: **`CheckoutCore` không biết audit, metrics, proxy hoặc pointcut tồn tại**. Chính nơi lắp ghép `core` với `CrossCuttingHandler` quyết định chính sách cắt ngang được áp dụng; người gọi tương tác qua cùng interface `Checkout`.

Ví dụ này cố ý minh họa một chính sách kỹ thuật nhỏ, không đại diện cho toàn bộ tính năng của AOP. JDK dynamic proxy chỉ can thiệp lời gọi được thực hiện **thông qua proxy và interface**; một đối tượng `CheckoutCore` được gọi trực tiếp sẽ không đi qua `CrossCuttingHandler`.

## 5. Ba mức độ tách trách nhiệm

**Mức 1 — Trộn trong nghiệp vụ.** Mỗi hàm tự ghi audit, tự đo thời gian, tự xử lý chính sách lặp lại. Mã dễ viết lúc đầu nhưng khó thay đổi nhất quán.

**Mức 2 — Bao thủ công bằng decorator hoặc wrapper.** Một lớp triển khai cùng interface và chuyển tiếp tới lớp gốc. Điều này đã giúp tách trách nhiệm; đổi lại phải viết/lắp wrapper cho các điểm cần bao. Không phải mọi decorator đều là AOP; decorator là kỹ thuật thiết kế có thể hiện thực hóa ý tưởng tách hành vi.

**Mức 3 — Mô tả aspect, pointcut và advice.** Cơ chế AOP lựa chọn join point theo quy tắc và gắn hành vi thông qua proxy hoặc weaving. Có thể tái sử dụng cùng chính sách trên nhiều mục tiêu mà mã nghiệp vụ không trực tiếp gọi aspect.

Độ tự động hóa cao hơn không mặc nhiên tạo ra thiết kế tốt hơn. Một wrapper rõ ràng có thể thích hợp cho vài lời gọi; aspect có ý nghĩa khi chính sách đủ thống nhất, phạm vi áp dụng đủ rõ và lợi ích giảm lặp lớn hơn chi phí hiểu luồng thực thi.

## 6. Thiết kế pointcut và thứ tự advice cho đúng

Một pointcut hữu ích thường chọn theo **vai trò hoặc hợp đồng** thay vì ghép tên tùy tiện. Ví dụ, chọn các thao tác đã được đánh dấu là cần audit có thể ổn định hơn việc chọn mọi phương thức bắt đầu bằng `save`. Tuy nhiên, dấu đánh dấu phải được đặt nhất quán và người đọc cần tra ra được điểm nào bị áp dụng.

Quy trình thực tế:

1. **Khoanh vùng nghiệp vụ:** liệt kê các hành động cần giữ độc lập và các bất biến chỉ miền nghiệp vụ mới quyết định được.
2. **Liệt kê chính sách cắt ngang:** audit, metrics, bảo mật ở ranh giới, tracing, quản lý tài nguyên; ghi rõ đầu vào, đầu ra và hành vi khi lỗi.
3. **Chọn join point:** xác định lời gọi hoặc lần thực thi nào có ý nghĩa, kể cả nhánh thất bại và đường gọi bất đồng bộ.
4. **Viết pointcut hẹp và kiểm tra được:** mô tả tiêu chí chọn, liệt kê vài trường hợp *phải khớp* và *không được khớp*.
5. **Đặt thứ tự advice:** chẳng hạn kiểm quyền trước thao tác; ghi audit kết quả sau thao tác; đo thời gian trong `finally`. Nếu có nhiều advice `around` lồng nhau, thứ tự ngoài–trong ảnh hưởng thời điểm ghi nhận và loại ngoại lệ được quan sát.
6. **Kiểm thử tại ranh giới thật:** gọi qua entry point đã được can thiệp, không chỉ gọi lớp gốc; xác nhận cả thành công, ngoại lệ và đường không khớp pointcut.

Ví dụ chính sách tổng quát cho một thao tác nhạy cảm:

~~~text
Caller
  -> Authorize (trước khi cho phép tiến hành)
    -> Measure duration (bắt đầu đo)
      -> Execute business operation
    <- Measure duration (finally, dù thành công hay lỗi)
  <- Audit result (thành công / thất bại)
<- Return hoặc throw
~~~

Đây chỉ là một cách sắp xếp. Nếu audit bắt buộc ghi cả thao tác **bị từ chối trước khi chạy nghiệp vụ**, audit phải bao ngoài bước kiểm quyền hoặc phải có đường ghi từ chối riêng. Nếu đo thời gian phục vụ SLA của người dùng, điểm bắt đầu/kết thúc có thể cần bao gồm cả kiểm quyền; nếu muốn đo riêng nghiệp vụ, phạm vi lại khác. Thứ tự phải xuất phát từ ý nghĩa dữ liệu đo/ghi.

## 7. Những góc cạnh nâng cao thường bị bỏ sót

### 7.1. Ranh giới can thiệp không đồng nhất

Cơ chế proxy thường chỉ thấy lời gọi đi qua đối tượng đại diện. Nếu một phương thức của lớp gốc gọi trực tiếp một phương thức khác trên chính `this`, lời gọi nội bộ có thể bỏ qua proxy (**self-invocation**). Các cơ chế weaving ở mức bytecode có phạm vi khác; cần kiểm tra chính xác loại join point mà công nghệ sử dụng hỗ trợ.

Tương tự, không thể mặc định rằng phương thức `private`, `final`, constructor, truy cập trường hoặc các lời gọi bất đồng bộ đều được can thiệp như nhau. Hãy mô tả giới hạn của cơ chế triển khai trước khi dựa vào aspect cho một bảo đảm quan trọng.

### 7.2. Ngoại lệ, kết quả và tính trong suốt

Một advice quan sát lý tưởng không được vô tình đổi giá trị trả về, loại ngoại lệ hoặc số lần thực thi nghiệp vụ. Nếu một advice `around` bắt và nuốt lỗi, người gọi có thể hiểu nhầm tác vụ đã thành công. Nếu aspect ghi log ném thêm lỗi, nó có thể che lỗi nghiệp vụ gốc. Với audit/metrics, nên có chính sách rõ cho trường hợp hạ tầng ghi nhận gặp lỗi.

Các advice **có chủ đích thay đổi hành vi** (kiểm quyền, retry, timeout) phải công bố hợp đồng: điều kiện từ chối, ngoại lệ nào được ném, khi nào dừng và có cho phép thực thi lại hay không.

### 7.3. Retry và tính lặp an toàn

Một aspect retry dùng `proceed` nhiều lần có thể lặp cả thanh toán, đặt hàng hoặc gửi thông báo. Retry chỉ nên áp dụng khi có điều kiện xác định lỗi tạm thời, giới hạn số lần và cơ chế bảo đảm an toàn lặp (idempotency) phù hợp. Không biến “mọi ngoại lệ” thành “thử lại”.

### 7.4. Dữ liệu nhạy cảm và ngữ cảnh thực thi

Audit/tracing không có nghĩa là ghi toàn bộ tham số, token, thông tin cá nhân hoặc payload vào log. Chỉ giữ dữ liệu cần thiết, che nội dung nhạy cảm và định rõ thời hạn lưu. Khi luồng đi qua thread, tác vụ bất đồng bộ hoặc ranh giới tiến trình, ngữ cảnh như correlation ID không tự nhiên luôn theo sang nơi mới; phải có cơ chế truyền ngữ cảnh được thiết kế rõ.

### 7.5. Hiệu năng, độ quan sát và gỡ lỗi

Advice chạy ở mọi join point khớp nên pointcut quá rộng có thể tăng overhead, tạo quá nhiều sự kiện hoặc vô tình lặp log. Aspect cũng khiến luồng chạy thực tế khác cấu trúc hiển thị trong mã nghiệp vụ. Cần tài liệu ngắn về pointcut, thứ tự advice và cách bật/tắt quan sát; đo overhead ở tải đại diện trước khi mở rộng phạm vi.

### 7.6. Giao dịch và ranh giới tài nguyên

Mở/đóng giao dịch hoặc dọn dẹp tài nguyên thường có tính cắt ngang, nhưng phạm vi giao dịch phải gắn với **đơn vị công việc** phù hợp. Đặt ranh giới quá nông có thể tách một nghiệp vụ thành nhiều phần không nhất quán; đặt quá rộng có thể giữ tài nguyên lâu. Hành vi rollback khi ngoại lệ cũng cần định nghĩa minh bạch, không được suy luận từ tên aspect.

## 8. Kiểm thử việc tách có thực sự đúng

Dùng ba nhóm kiểm thử khác nhau:

| Bài kiểm tra | Thao tác | Điều cần khẳng định |
| --- | --- | --- |
| Nghiệp vụ thuần | Gọi trực tiếp `CheckoutCore.placeOrder()` | Quy tắc số lượng và kết quả không phụ thuộc audit/metrics |
| Can thiệp đúng điểm | Gọi `placeOrder()` qua proxy, rồi gọi `status()` | Chỉ phương thức khớp pointcut mới được ghi nhận |
| Thành công và thất bại | Gọi số lượng dương và không dương qua proxy | Audit ghi đúng trạng thái; metrics chạy trên cả hai nhánh; ngoại lệ gốc được bảo toàn |

Khi nhiều aspect cùng áp dụng, thêm kiểm thử **thứ tự** và **số lần gọi nghiệp vụ**; khi có retry, bảo mật hoặc giao dịch, kiểm thử các trường hợp bị từ chối, timeout, lỗi hạ tầng và tính nhất quán dữ liệu.

Một tiêu chí thiết kế dễ kiểm tra: **thay đổi định dạng audit hoặc công cụ đo thời gian không đòi sửa `CheckoutCore`; thay đổi quy tắc số lượng đặt hàng không đòi sửa `CrossCuttingHandler`.** Nếu hai phía vẫn buộc phải biết chi tiết triển khai của nhau, việc tách chưa đạt.

## 9. Sai lầm thường gặp và cách tránh

- **Nhầm mọi logic dùng chung thành cross-cutting:** giữ bất biến và quyết định miền trong mô hình nghiệp vụ; chỉ tách chính sách thật sự chung.
- **Pointcut bằng tên quá rộng:** vô tình can thiệp cả getter, hàm tiện ích hoặc lời gọi không mong muốn; hãy kiểm tra tập khớp và trường hợp loại trừ.
- **Cho rằng aspect luôn chạy:** cuộc gọi trực tiếp, self-invocation hoặc loại join point không được hỗ trợ có thể bỏ qua cơ chế can thiệp.
- **Dùng `around` cho mọi thứ:** ưu tiên advice đơn giản hơn khi chỉ cần quan sát trước/sau; `around` làm tăng nguy cơ thay đổi luồng điều khiển.
- **Nuốt ngoại lệ hoặc sửa kết quả ngoài ý muốn:** bảo toàn hợp đồng đầu ra; việc biến đổi phải là chính sách được chỉ định rõ.
- **Phụ thuộc thứ tự ngầm:** xác định thứ tự aspect và đo xem advice ngoài/đóng có chạy cả khi lỗi hay không.
- **Đưa quá nhiều dữ liệu vào audit:** phân loại và loại bỏ dữ liệu nhạy cảm trước khi ghi.
- **Ẩn chính sách quan trọng:** các điều kiện bảo mật, retry và giao dịch cần được ghi rõ tại ranh giới áp dụng, có kiểm thử bao phủ.

## 10. Ghi nhớ

AOP giải quyết bài toán **mô-đun hóa hành vi cắt ngang** bằng cách tách ba quyết định: **mã nghiệp vụ làm gì**, **chính sách kỹ thuật làm gì** và **chính sách được áp dụng ở những điểm thực thi nào**. Khi ba quyết định này rõ ràng, nghiệp vụ dễ đọc và kiểm thử hơn; cùng một chính sách có thể được duy trì nhất quán. Điểm cần kiểm soát là tính chính xác của pointcut, thứ tự advice, phạm vi weaving/proxy và việc bảo toàn kết quả hoặc ngoại lệ của luồng gốc.