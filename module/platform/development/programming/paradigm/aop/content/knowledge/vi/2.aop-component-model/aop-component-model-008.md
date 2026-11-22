# Luồng tương tác giữa mã nghiệp vụ và một aspect trong AOP

## 1. Mục tiêu: hiểu điều gì thực sự xảy ra khi có aspect

Trong **Aspect-Oriented Programming (AOP)**, mã nghiệp vụ thực hiện công việc chính như xử lý đơn hàng, tính giá hay lưu dữ liệu. Một **aspect** mô-đun hóa hành vi có tính xuyên suốt, chẳng hạn ghi nhận thao tác, đo thời gian, theo dõi lỗi hoặc áp dụng một chính sách chung ở nhiều điểm trong chương trình.

Điều quan trọng nhất là: **mã nghiệp vụ không nhất thiết gọi trực tiếp aspect**. Thay vào đó, cơ chế AOP xác định các điểm thực thi có thể can thiệp (**join point**), chọn các điểm thích hợp bằng **pointcut** và kết hợp hành vi bổ sung (**advice**) vào luồng thực thi thông qua **weaving** hoặc cơ chế chặn lời gọi tương ứng.

Sơ đồ ý tưởng cho một thao tác đồng bộ:

```text
Bên gọi (caller)
       |
       v
[Cơ chế AOP áp dụng pointcut tại join point]
       |
       v
[Advice trước thao tác]
       |
       v
[Mã nghiệp vụ gốc chạy]
       |
       v
[Advice xử lý kết quả / lỗi / kết thúc]
       |
       v
Bên gọi nhận kết quả hoặc ngoại lệ
```

Sơ đồ này mô tả **thứ tự tương tác có thể quan sát được**, không khẳng định mọi giải pháp AOP đều xây một đối tượng trung gian hoặc tạo ra các bước máy chạy đúng như từng ô trong sơ đồ. Một công cụ có thể biến đổi mã trong lúc biên dịch hoặc nạp mã; công cụ khác có thể chặn lời gọi đi qua proxy. Bản chất cần giữ là hành vi của aspect được kết hợp vào **điểm thực thi đã được chọn**.

Sau bài này, người học cần giải thích được ai gọi ai, lúc nào advice chạy, điều gì trở về bên gọi, cách ngoại lệ đi qua aspect, và tại sao một số đường gọi có thể nằm ngoài phạm vi can thiệp.

## 2. Những thành phần tham gia luồng tương tác

| Thành phần | Trách nhiệm | Có nhất thiết biết về thành phần khác? |
| --- | --- | --- |
| **Caller** | Gọi thao tác và nhận kết quả/ngoại lệ | Biết hợp đồng gọi nghiệp vụ; thường không cần biết aspect |
| **Mã nghiệp vụ (target)** | Thực hiện chức năng cốt lõi | Không cần phụ thuộc trực tiếp vào advice |
| **Join point** | Điểm trong mô hình thực thi có thể bị can thiệp | Là khái niệm của mô hình AOP, không tự là một lời gọi |
| **Pointcut** | Quy tắc lựa chọn những join point cần tác động | Cần khớp đúng loại điểm và điều kiện |
| **Advice** | Hành vi phụ trợ chạy tại điểm được chọn | Có thể quan sát hoặc tác động đến luồng thực thi |
| **Aspect** | Nhóm các pointcut/advice cùng một mối quan tâm | Có thể độc lập với mã nghiệp vụ khi thiết kế đúng |
| **Weaver/interception mechanism** | Kết hợp advice vào đường thực thi | Phụ thuộc công nghệ AOP và thời điểm áp dụng |
| **Join-point context** | Thông tin về điểm/lần thực thi | Các trường được cung cấp khác nhau theo công cụ |

Ví dụ có phương thức `OrderService.placeOrder(orderId)` và chính sách kiểm toán `OrderAudit`:

- `placeOrder` xử lý đơn hàng: kiểm tra dữ liệu, tính tổng và ghi đơn.
- `OrderAudit` ghi nhận thao tác bắt đầu, thành công hoặc thất bại.
- Một pointcut chọn các lần thực thi `placeOrder` cần kiểm toán.
- Cơ chế AOP làm cho advice của `OrderAudit` chạy quanh thao tác được chọn.

Các thành phần này trả lời những câu hỏi riêng: **chương trình đang làm gì** (nghiệp vụ), **can thiệp ở đâu** (join point/pointcut), **làm thêm gì** (advice/aspect), và **việc kết hợp xảy ra bằng cách nào** (weaving/interception).

## 3. Hai thời điểm khác nhau: cấu hình kết hợp và chạy nghiệp vụ

Không nên tưởng tượng pointcut được tạo mới cho từng lệnh nghiệp vụ hoặc aspect chỉ xuất hiện khi caller gọi đến. Có hai nhóm hoạt động cần phân biệt.

### 3.1. Trước hoặc trong quá trình chuẩn bị thực thi

Tùy công cụ, hệ thống thực hiện những việc như:

1. Xác định mô hình join point có thể hỗ trợ: thực thi phương thức, gọi phương thức, truy cập trường, khởi tạo đối tượng hoặc các điểm khác.
2. Đọc/biên dịch quy tắc pointcut, nhận diện điểm có khả năng khớp.
3. Chuẩn bị cách áp dụng advice: biến đổi mã khi biên dịch, can thiệp lúc nạp mã hoặc tạo cấu trúc chặn lời gọi khi chạy.
4. Xác lập thứ tự của các advice/aspect nếu nhiều chính sách cùng khớp một điểm.

Trong một số cơ chế, điều kiện động vẫn phải được đánh giá khi mỗi lần gọi diễn ra. Vì vậy, "đã có cấu hình" không có nghĩa là mọi lần thực thi đều được advice xử lý.

### 3.2. Khi một thao tác thực sự chạy

Khi caller gọi một thao tác, hệ thống có thể:

1. Đi qua một điểm mà cơ chế AOP quan sát hoặc chặn được.
2. Kiểm tra liệu lần thực thi đó thỏa các điều kiện chọn điểm hay không.
3. Chạy advice thích hợp theo thứ tự đã xác định.
4. Tiếp tục thao tác gốc nếu advice cho phép.
5. Xử lý kết quả hoặc ngoại lệ bằng những advice tương ứng.
6. Trả kết quả/ngoại lệ cho caller theo hợp đồng hiệu lực sau can thiệp.

**Phân biệt quan trọng:** mô tả cấu trúc aspect và weaving là chuyện **lắp ghép hành vi**; mỗi lời gọi cụ thể là chuyện **diễn tiến động**. Không nên trộn hai việc này thành một bước "caller gọi aspect".

## 4. Luồng đồng bộ thành công: từ caller đến mã nghiệp vụ rồi quay về

Xét một lần `placeOrder("A-01")` trả về mã xác nhận. Giả sử công cụ cho phép advice trước, advice sau khi trả về và advice cuối cùng.

```text
Caller                  Cơ chế AOP / advice                   OrderService
  |                            |                                   |
  |-- placeOrder("A-01") ------>|                                   |
  |                            |-- before: ghi nhận bắt đầu       |
  |                            |-- gọi thao tác gốc ------------->|
  |                            |                                   |-- kiểm tra đơn
  |                            |                                   |-- xử lý nghiệp vụ
  |                            |<----- trả "OK:A-01" -------------|
  |                            |-- after returning: ghi thành công|
  |                            |-- finally: ghi kết thúc          |
  |<------- "OK:A-01" ----------|                                   |
```

Các bước trên thể hiện một **trình tự minh họa**, không phải quy tắc bắt buộc về thứ tự tuyệt đối giữa tất cả những kiểu advice ở mọi công cụ. Điểm cốt lõi:

- Caller gọi qua đường thực thi có hỗ trợ can thiệp, không tự gọi lệnh `before`.
- Advice trước chạy khi join point phù hợp được chọn.
- Phần nghiệp vụ chỉ chạy nếu đường advice/chặn cho phép tiếp tục.
- Advice sau thành công chỉ có ý nghĩa khi thao tác hoàn thành bình thường.
- Kết quả quay về caller **sau những advice cần thiết**, nên thời điểm caller nhận kết quả có thể muộn hơn thời điểm thân phương thức kết thúc.

Ví dụ này giả định advice chỉ quan sát và không sửa kết quả. Một advice có quyền bao quanh còn có thể thay đổi kết quả hoặc ngăn thao tác gốc, khi cơ chế hỗ trợ và thiết kế cho phép.

### 4.1. “Gọi phương thức” và “thực thi phương thức” có thể là hai join point

Giả sử trong `CheckoutService.checkout()` có lệnh `gateway.charge()`:

```text
checkout():                              gateway.charge():
    gateway.charge() ----------------------> xử lý thanh toán
       ^                                             ^
       |                                             |
   điểm method call                          điểm method execution
   ở phía gọi                               ở phía được gọi
```

Aspect tác động vào **method call** có thể chạy ở phía lời gọi trong `checkout()`; aspect tác động vào **method execution** có thể chạy tại phần thân `charge()`. Hai loại điểm có thể có ngữ cảnh khác nhau (đối tượng bên gọi, đối tượng thực hiện, vị trí mã nguồn, v.v.).

Một công cụ có thể chỉ hỗ trợ một trong hai loại, hoặc chỉ chặn những lời gọi đi qua một lớp trung gian. Vì vậy, sơ đồ tương tác phải nói rõ **đường gọi nào đang được can thiệp** trước khi khẳng định advice chạy ở đâu.

## 5. Advice quyết định cách tiếp tục luồng

Các tên gọi phổ biến dưới đây mô tả vai trò của advice. Không phải công cụ nào cũng hỗ trợ đầy đủ hoặc dùng cùng cú pháp.

| Kiểu advice | Thời điểm | Điều cần lưu ý |
| --- | --- | --- |
| **Before** | Trước thao tác được chọn | Có thể ghi nhận hoặc kiểm tra, nhưng khả năng dừng lời gọi tùy cơ chế |
| **After returning** | Khi hoàn tất bình thường | Có thể quan sát kết quả nếu công cụ cung cấp |
| **After throwing** | Khi thao tác kết thúc bằng ngoại lệ | Cần xác định ngoại lệ được giữ, đổi hay xử lý |
| **After/finally** | Khi kết thúc bất kể thành công hay lỗi | Không có nghĩa mọi kiểu kết thúc bất thường của tiến trình đều được xử lý |
| **Around** | Bao quanh điểm được chọn | Có thể quyết định gọi tiếp, số lần gọi tiếp và cách trả kết quả |

Một dạng mã giả AOP trung lập công cụ:

```text
aspect OperationAudit:
    pointcut tracked = executionsOf(BusinessOperation)

    around tracked(context):
        audit("start", context.name)
        try:
            result = proceed(context)
            audit("success", context.name)
            return result
        catch error:
            audit("failure", context.name, error)
            throw error
        finally:
            audit("finished", context.name)
```

Đây là **mã giả**, không phải Java biên dịch được hay một ngôn ngữ AOP chuẩn chung. `proceed` biểu thị thao tác tiếp tục đến mắt xích kế tiếp hoặc phần nghiệp vụ gốc tùy cấu trúc advice. Ở cách mô tả này, một lượt thành công đi theo thứ tự:

```text
audit(start)
    -> proceed -> business operation -> trả result
audit(success)
audit(finished)
return result
```

Còn lượt lỗi:

```text
audit(start)
    -> proceed -> business operation -> ném error
audit(failure)
audit(finished)
throw error
```

Nên hiểu `finally` ở đây là cơ chế kết thúc theo luồng điều khiển thông thường của lời gọi; không nên suy diễn rằng nó chắc chắn thực thi khi tiến trình bị chấm dứt cưỡng bức hoặc môi trường chạy gặp sự cố không thể phục hồi.

### 5.1. Advice quanh thao tác có thể thay đổi kết quả

Nếu `around` trả về dữ liệu khác kết quả `proceed`, caller nhận dữ liệu đã được biến đổi theo cơ chế chặn, miễn là hợp đồng kiểu/giá trị được thỏa. Nếu advice **không gọi `proceed`**, phần nghiệp vụ gốc có thể bị bỏ qua. Nếu advice **gọi nhiều lần**, phần nghiệp vụ có thể thực thi nhiều lần.

Đây là khác biệt lớn giữa một advice bao quanh và một đoạn ghi log đơn giản. Thao tác có tác dụng phụ như tạo đơn, chuyển tiền hoặc gửi email phải được xem xét kỹ nếu có logic thử lại, bỏ qua hoặc đổi lỗi. Khả năng can thiệp mạnh **không đồng nghĩa với quyền thay đổi nghiệp vụ tùy ý**.

## 6. Ví dụ Java 17 chạy được: mô phỏng luồng advice → nghiệp vụ → advice

Java thông thường không tự động nhận cú pháp pointcut và weaving. Để **quan sát luồng tương tác** bằng JDK 17 thuần, ta dùng `java.lang.reflect.Proxy`: các lời gọi đi qua proxy được chuyển cho một `InvocationHandler`, tại đây viết logic trước/sau và gọi đích gốc.

Ví dụ là **mô phỏng một cơ chế chặn lời gọi**, không phải khai báo aspect theo một ngôn ngữ AOP tổng quát. Nó có phạm vi cụ thể: các phương thức giao diện được gọi **qua proxy**.

Tạo tệp `AspectFlowDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AspectFlowDemo {

    public interface OrderService {
        String place(String orderId);
        String cancel(String orderId);
    }

    public static final class DefaultOrderService implements OrderService {
        @Override
        public String place(String orderId) {
            System.out.println("business:place " + orderId);
            return "placed:" + orderId;
        }

        @Override
        public String cancel(String orderId) {
            System.out.println("business:cancel " + orderId);
            if ("BAD".equals(orderId)) {
                throw new IllegalArgumentException("invalid order");
            }
            return "cancelled:" + orderId;
        }
    }

    public static void main(String[] args) {
        OrderService target = new DefaultOrderService();

        OrderService intercepted = (OrderService) Proxy.newProxyInstance(
                OrderService.class.getClassLoader(),
                new Class<?>[] { OrderService.class },
                (Object proxy, Method method, Object[] arguments) -> {
                    String operation = method.getName();
                    System.out.println("aspect:before " + operation);

                    try {
                        Object result = method.invoke(target, arguments);
                        System.out.println(
                                "aspect:afterReturning " + operation + " -> " + result
                        );
                        return result;
                    } catch (InvocationTargetException ex) {
                        Throwable cause = ex.getCause();
                        System.out.println(
                                "aspect:afterThrowing " + operation +
                                " -> " + cause.getClass().getSimpleName()
                        );
                        throw cause;
                    } finally {
                        System.out.println("aspect:finally " + operation);
                    }
                }
        );

        System.out.println("caller:begin");
        System.out.println("caller:result " + intercepted.place("A-01"));

        try {
            intercepted.cancel("BAD");
        } catch (IllegalArgumentException ex) {
            System.out.println("caller:error " + ex.getMessage());
        }

        System.out.println("caller:end");
    }
}
```

Biên dịch/chạy:

```bash
javac AspectFlowDemo.java
java AspectFlowDemo
```

Đầu ra:

```text
caller:begin
aspect:before place
business:place A-01
aspect:afterReturning place -> placed:A-01
aspect:finally place
caller:result placed:A-01
aspect:before cancel
business:cancel BAD
aspect:afterThrowing cancel -> IllegalArgumentException
aspect:finally cancel
caller:error invalid order
caller:end
```

### 6.1. Đọc kết quả theo từng vai trò

- `caller:begin`: mã bên gọi bắt đầu kịch bản.
- `aspect:before place`: đường gọi đi qua proxy, logic chặn chạy trước khi gọi đích.
- `business:place A-01`: thân phương thức nghiệp vụ thực thi trên `target`.
- `aspect:afterReturning ...`: đích đã trả kết quả bình thường, handler ghi nhận trước khi trao kết quả lại caller.
- `aspect:finally place`: khối dọn dẹp/ghi kết thúc của handler chạy.
- `caller:result placed:A-01`: caller mới nhìn thấy kết quả sau các bước phía trên.
- Với `cancel("BAD")`, nghiệp vụ ném `IllegalArgumentException`. Reflection bọc ngoại lệ đích trong `InvocationTargetException`; handler lấy `getCause()`, ghi nhánh lỗi và **ném lại nguyên nhân** để caller bắt được `IllegalArgumentException`.

Đó là lý do cần phân biệt **ngoại lệ do nghiệp vụ sinh ra** với lớp bọc kỹ thuật của phương tiện gọi phản xạ. Cơ chế AOP thật có thể trình bày/lan truyền ngoại lệ theo những hợp đồng riêng; trong ví dụ này, mã minh họa chủ động giữ ngoại lệ nghiệp vụ.

### 6.2. Điểm tương đồng và khác biệt với AOP đầy đủ

Handler đóng vai trò tương tự một `around advice`: nó chạy trước, thực hiện một lời gọi tiếp tục đến `target`, rồi xử lý kết quả, lỗi và `finally`. Sự tương tác được thể hiện rõ bằng stdout.

Nhưng ví dụ **không có bộ biểu thức pointcut tổng quát** và không thể can thiệp tự động vào mọi loại join point. Mã nghiệp vụ được gọi trực tiếp qua `target` sẽ không đi qua handler. Nếu thêm một phương thức trong `DefaultOrderService` tự gọi phương thức khác của cùng đối tượng, lời gọi nội bộ cũng không mặc nhiên được proxy chặn. Công cụ dùng cách weaving khác có thể cung cấp phạm vi join point rộng hơn.

## 7. Luồng thất bại: ngoại lệ đi qua advice và caller như thế nào?

Một trường hợp quan trọng là thao tác nghiệp vụ ném ngoại lệ. Nếu không có advice xử lý, ngoại lệ đi ngược ngăn xếp lời gọi tới nơi bắt thích hợp. Có aspect thì đường đi có thể gồm các advice quan sát hoặc tác động đến ngoại lệ:

```text
Caller                     Advice / cơ chế AOP               Mã nghiệp vụ
  |                              |                                |
  |-- gọi thao tác -------------->|                                |
  |                              |-- before                      |
  |                              |-- tiếp tục ------------------->|
  |                              |                                |-- ném E
  |                              |<------- E ---------------------|
  |                              |-- after throwing(E)           |
  |                              |-- finally                     |
  |<------------- E -------------|                                |
  |-- bắt E nếu có handler phù hợp|
```

Sơ đồ giả định advice **không nuốt và không chuyển đổi ngoại lệ**. Một advice có thể được thiết kế để dịch ngoại lệ sang kiểu khác hoặc thay bằng kết quả dự phòng, nhưng đó là quyết định có ảnh hưởng đến hợp đồng nghiệp vụ, không phải hệ quả tự nhiên của việc có join point.

Đừng nhầm các khái niệm:

- **After returning** không chạy cho lần gọi đã ném ngoại lệ từ phần được theo dõi, trừ khi một lớp bao bên ngoài thực sự chuyển tình huống thành một kết quả bình thường tại ranh giới mà advice đó quan sát.
- **After throwing** quan sát sự thoát ra bằng ngoại lệ của điểm được chọn; nó không đồng nghĩa với việc chỉ định một trình xử lý bắt ngoại lệ trong mã nghiệp vụ.
- **Finally** dùng để giữ hành vi kết thúc ở cả hai nhánh, trong các tình huống chương trình còn thực thi bình thường.
- Nếu chính advice ném lỗi, lỗi đó có thể che khuất lỗi gốc hoặc thay đổi thứ mà caller nhận được. Vì thế logging và telemetry không nên vô tình làm hỏng kết quả của thao tác chính.

### 7.1. Phân biệt ngoại lệ được bắt bên trong với ngoại lệ thoát khỏi phương thức

Xét đoạn mã:

```java
String calculate() {
    try {
        return parseExternalData();
    } catch (NumberFormatException ex) {
        return "default";
    }
}
```

Đây là **đoạn minh họa**, không phải chương trình Java độc lập; `parseExternalData()` chỉ là ký hiệu cho phương thức phụ thuộc khác. Nếu ngoại lệ xảy ra rồi được xử lý bên trong `calculate()`, một advice quan sát **method execution của `calculate()`** có thể thấy kết quả trả về bình thường `"default"`, chứ không thấy ngoại lệ thoát khỏi điểm thực thi đó. Muốn quan sát chính đoạn bắt ngoại lệ, cần một loại join point hoặc kỹ thuật quan sát khác mà công cụ thực sự hỗ trợ.

## 8. Nhiều aspect cùng áp dụng: tạo thành chuỗi bao quanh

Một thao tác có thể đồng thời chịu chính sách xác thực, kiểm toán và đo thời gian. Nếu các advice đều áp dụng tại cùng điểm, thực thi thường được hiểu bằng hình ảnh các lớp bao quanh:

```text
Caller
  |
  v
Audit.around
  |
  v
Permission.around
  |
  v
Timing.around
  |
  v
BusinessOperation
  |
  v
Timing hoàn tất
  |
  v
Permission hoàn tất
  |
  v
Audit hoàn tất
  |
  v
Caller
```

Trong trường hợp các lớp bao quanh được thiết kế như trên, biểu thức tư duy là:

```text
Audit(Permission(Timing(BusinessOperation)))
```

Lượt thành công có thể có dạng:

```text
audit before
permission before
timer start
business
timer end
permission after
audit after
```

Các dòng chỉ minh họa thứ tự cho **cấu hình đã được ấn định như sơ đồ**. Không thể suy luận thứ tự chỉ từ tên aspect hay thứ tự viết chúng trong tệp nguồn: hệ thống AOP có thể có cơ chế ưu tiên riêng; hãy xác định thứ tự được hỗ trợ và kiểm tra nó trên chương trình.

### 8.1. Thứ tự ảnh hưởng đến chính sách

Giả sử `Permission` từ chối lời gọi trước khi đi tiếp:

- Với `Audit(Permission(Timing(BusinessOperation)))`, audit bên ngoài có thể ghi cả lần truy cập bị từ chối; timer và mã nghiệp vụ không chạy nếu advice phân quyền không tiếp tục.
- Với `Permission(Audit(Timing(BusinessOperation)))`, audit ở bên trong có thể không quan sát được lần gọi bị từ chối từ vòng ngoài.

Tương tự, đặt timer bên ngoài hay bên trong một advice thử lại (retry) quyết định thời gian đo là **toàn bộ các lần thử** hay **từng lần thử**. Thứ tự là một phần của thiết kế ngữ nghĩa, cần được mô tả cùng với chính sách.

### 8.2. Around advice quyết định việc chuyển tiếp

Mã giả:

```text
around operation:
    if not authorized:
        throw AccessDenied
    return proceed()
```

Nếu điều kiện thất bại, `proceed()` không chạy nên nghiệp vụ bị chặn. Còn nếu một advice retry gọi `proceed()` hai lần, đích có thể chạy hai lần. Với thao tác có tác dụng phụ như thu tiền, thêm hàng hoặc cập nhật kho, điều này đòi hỏi ràng buộc về idempotency và tính đúng đắn; không nên tự thêm retry xuyên suốt nếu chưa hiểu hợp đồng nghiệp vụ.

### 8.3. Hai aspect không nhất thiết hoàn toàn độc lập

Dù aspect được mô-đun hóa, chúng vẫn có thể tương tác gián tiếp thông qua thứ tự, ngoại lệ, thông tin ngữ cảnh, trạng thái thread-local hoặc dữ liệu dùng chung. Một aspect biến đổi ngoại lệ có thể khiến aspect bên ngoài quan sát kiểu lỗi khác; một aspect thay đổi tham số có thể đổi điều kiện khớp của logic phía sau trong những mô hình hỗ trợ điều kiện động.

Do đó, ngoài kiểm thử từng aspect, cần kiểm thử **tổ hợp aspect** tại các điểm có nguy cơ thay đổi hành vi.

## 9. Khác biệt giữa luồng logic và cách cơ chế AOP triển khai

Sơ đồ `advice → nghiệp vụ → advice` mô tả **ngữ nghĩa quan sát được**, không quy định có một proxy hoặc một method Java mới. Khi lần theo luồng thực, phân biệt:

| Cơ chế | Đường thực thi khi lời gọi xuất hiện | Điều cần kiểm chứng |
| --- | --- | --- |
| Weaving khi biên dịch / biến đổi bytecode | Caller đi vào mã đã tích hợp advice tại join point được dệt | Class/call site thuộc tập weave; lời gọi nội bộ **có thể** gặp execution advice |
| Weaving lúc nạp lớp | JVM định nghĩa lớp có mã biến đổi | Agent, config và classloader hoạt động đúng **trước khi** nạp lớp cần dệt |
| Proxy/interceptor | `caller → proxy → advice chain → target` | Caller thật sự có dùng proxy, hay dùng target thô/`this.inner()`? |

Luồng qua proxy có thể sinh advice, trong khi lời gọi đến cùng method trên target gốc thì không. Khác biệt ấy nằm ở **biên interception**; weaving tại execution lại có thể thấy cả lời gọi nội bộ. Sơ đồ đường proxy:

```text
caller --> proxy/interceptor --> target
              |                 ^
              +---- advice ------+
```

## 10. Luồng có điều kiện: pointcut chọn điểm nào, vào thời điểm nào?

Điểm có thể can thiệp không đồng nghĩa điểm luôn được advice xử lý. Một pointcut có thể kết hợp:

- **Điều kiện tĩnh:** loại join point, tên/chữ ký phương thức, kiểu lớp, phạm vi mã.
- **Điều kiện động:** tham số, đối tượng thực tế, trạng thái hoặc thông tin ngữ cảnh trong lần gọi, nếu công cụ hỗ trợ.

Ví dụ một quy tắc chọn các thao tác `transfer(amount)` khi `amount` lớn hơn một ngưỡng:

```text
Lần gọi 1: transfer(50)
  -> đi qua vị trí có khả năng là join point
  -> điều kiện động không khớp
  -> không chạy advice tương ứng

Lần gọi 2: transfer(5000)
  -> đi qua cùng loại join point
  -> điều kiện động khớp
  -> chạy advice tương ứng
```

Đây là tình huống **mã giả** và không nói rằng mọi công cụ đều có biểu thức chọn theo giá trị tham số.

Trong một số cách triển khai, việc chọn phần tĩnh được chuẩn bị từ trước, còn điều kiện động được đánh giá khi chương trình chạy. Nếu pointcut quá rộng, việc kiểm tra có thể tốn chi phí và aspect chạm vào thao tác ngoài ý muốn; nếu quá hẹp, thao tác cần kiểm soát có thể bị bỏ sót.

### 10.1. Không nhầm việc pointcut khớp với việc advice chắc chắn hoàn tất

Ngay cả khi điểm đã được chọn, advice có thể ném ngoại lệ trước khi tiếp tục; một advice ngoài có thể từ chối thao tác; môi trường chạy có thể bị gián đoạn. Ngược lại, một lời gọi hợp lệ đi qua nhiều lớp can thiệp nhưng ở mỗi lớp điều kiện chọn điểm có thể khác nhau.

Do đó, chuỗi logic hoàn chỉnh gồm cả **đánh giá điều kiện**, **quyết định tiếp tục**, **thực hiện phần gốc**, và **xử lý kết quả/ngoại lệ**, chứ không chỉ gồm một lệnh "chèn code".

## 11. Luồng lồng nhau, đệ quy và lời gọi nội bộ

### 11.1. Một phương thức nghiệp vụ gọi phương thức nghiệp vụ khác

Ví dụ:

```text
OrderService.placeOrder()
    -> InventoryService.reserve()
    -> PaymentService.charge()
```

Nếu pointcut chọn các phương thức ở cả ba dịch vụ, có thể xuất hiện các đoạn advice lồng nhau:

```text
before(placeOrder)
  business placeOrder
    before(reserve)
      business reserve
    after(reserve)
    before(charge)
      business charge
    after(charge)
after(placeOrder)
```

Chuỗi này **chỉ đúng khi các lời gọi tương ứng đều thực sự đi qua điểm được cơ chế AOP hỗ trợ và khớp pointcut**. Nó không thể được suy ra duy nhất từ sơ đồ gọi phương thức.

### 11.2. Self-invocation có thể thay đổi đường đi

Nếu `placeOrder()` tự gọi `validateInternal()` trên cùng đối tượng, một công cụ chỉ chặn ở proxy phía ngoài có thể ghi advice cho `placeOrder()` nhưng không ghi cho `validateInternal()`. Mã gốc vẫn thực thi `validateInternal()`; chỉ là đường gọi đó **không đi qua điểm chặn**.

Với cơ chế weaving vào thân mã, cùng tình huống có thể được xử lý khác. Khi kiểm thử AOP, cần xác minh cả đường gọi trực tiếp, qua proxy và từ bên trong đối tượng nếu chúng ảnh hưởng đến yêu cầu.

### 11.3. Đệ quy tạo nhiều lần xuất hiện của cùng điểm

Một phương thức gọi chính nó nhiều lần tạo ra những lần xuất hiện join point lồng nhau. Nếu mỗi lần đều được advice bao quanh, thứ tự có thể là:

```text
before(factorial 3)
  before(factorial 2)
    before(factorial 1)
    after(factorial 1)
  after(factorial 2)
after(factorial 3)
```

Tương tự luồng call stack, các phần kết thúc có thể xuất hiện theo thứ tự ngược phần bắt đầu. Advice đo thời gian không nên lưu một biến `startTime` chung duy nhất cho mọi lần gọi đệ quy, vì lần gọi sâu hơn có thể ghi đè mốc của lần ngoài.

## 12. Ngoại lệ, giao dịch và tác dụng phụ trong chuỗi tương tác

Với hành vi xuyên suốt, cần nhìn cả kết quả nghiệp vụ **và** tác động của advice.

### 12.1. Advice xử lý lỗi có thể tạo thêm lỗi

Nếu `auditFailure()` trong advice ném một ngoại lệ mới, caller có thể nhận lỗi của hệ thống audit thay vì lỗi nghiệp vụ ban đầu. Khi đó chính sách báo lỗi phải được thiết kế rõ: cố gắng ghi nhận lỗi theo hướng không làm mất thông tin gốc, hoặc chủ động coi sự cố audit là lý do chặn thao tác nếu yêu cầu hệ thống quy định vậy.

Trong trường hợp advice làm thay đổi lỗi, điều quan trọng là có phương án ghi nhận nguyên nhân gốc để chẩn đoán; không nên vô tình che lỗi bằng các `catch` trống.

### 12.2. Side effect của advice có thể không được hoàn tác

Một advice gửi sự kiện ra ngoài hoặc ghi audit vào hệ thống khác trước khi nghiệp vụ hoàn tất. Nếu nghiệp vụ thất bại, sự kiện đã phát có thể vẫn tồn tại. Dù hai phần được gọi trong cùng luồng, **không có bảo đảm nguyên tử hoặc cùng giao dịch** nếu không thiết kế cơ chế phối hợp cụ thể.

Tương tự, advice `after returning` ghi nhận thành công ở mức lời gọi chưa chắc có nghĩa toàn bộ quy trình phân tán đã cam kết bền vững. Nên định nghĩa "thành công" tại đúng ranh giới có ý nghĩa nghiệp vụ.

### 12.3. Advice retry là một thay đổi luồng lớn

Mã giả:

```text
around operation:
    try:
        return proceed()
    catch TemporaryFailure:
        return proceed()
```

Ở đây phần gốc **có thể chạy hai lần**. Nếu thao tác không an toàn khi lặp, thử lại có thể nhân đôi side effect. Không được xem retry như một log aspect vô hại. Cần có giới hạn lần thử, điều kiện retry, cơ chế idempotency và chính sách lỗi trước khi áp dụng cho nghiệp vụ thực.

## 13. Bất đồng bộ và đa luồng: kết thúc phương thức chưa phải kết thúc công việc

Với hàm đồng bộ, thời điểm trả về của phương thức thường là ranh giới trực tiếp giữa nghiệp vụ và caller. Nhưng một thao tác bất đồng bộ có thể trả về ngay đối tượng biểu diễn công việc đang chạy:

```text
Caller
  |
  |-- startTask() --------> advice trước
  |                        -> tạo / lên lịch công việc
  |<-- Future/handle ------ advice sau thời điểm method return
  |
  |                  ... công việc thật tiếp tục ở thời điểm khác ...
  |
  |<------------------- tín hiệu hoàn tất về sau
```

**Điểm method execution của `startTask()` kết thúc khi phương thức trả về**, không tự động kéo dài đến khi future hoàn tất. Nếu đo khoảng từ advice trước tới advice sau của phương thức, ta có thể chỉ đo **thời gian lên lịch**, không phải **thời gian xử lý toàn tác vụ**.

Muốn đo đến khi tác vụ hoàn tất, thiết kế phải xác định một ranh giới bổ sung: completion callback, completion stage, nơi xử lý kết quả hoặc một điểm khác có thể được can thiệp. Việc chuyển ngữ cảnh trace/audit sang luồng thực thi khác cũng phải có chủ đích.

### 13.1. Trạng thái của advice trong môi trường đồng thời

Nếu nhiều lời gọi được xử lý song song, trạng thái đếm thời gian, số lần thử hay correlation ID phải được gắn với **mỗi invocation hoặc tác vụ** phù hợp. Biến mutable dùng chung thiếu đồng bộ có thể tạo log sai hoặc làm hỏng dữ liệu.

Giả sử hai lượt chạy:

```text
Call A: before(A) ----------- business(A) -------- after(A)
Call B:      before(B) ---- business(B) ---------------- after(B)
```

Thứ tự log liên luồng có thể đan xen; điều đó **không nhất thiết là sai thứ tự nội bộ** của mỗi invocation. Cần phân biệt thứ tự tổng thể và quan hệ nhân quả từng lời gọi; nên ghi correlation ID để gom các bản ghi thuộc cùng lần xử lý.

## 14. Quan sát và gỡ lỗi luồng tương tác

Vì lời gọi đến advice có thể không hiện trực tiếp trong thân phương thức nghiệp vụ, việc gỡ lỗi AOP thường khó hơn lần theo các lời gọi tường minh. Cách tiếp cận hữu ích:

1. Xác định **caller**, điểm gọi và đường đi tới target.
2. Kiểm tra **đúng loại join point** cần can thiệp: call, execution hay loại khác.
3. Xác định **pointcut khớp những vị trí/lần chạy nào**.
4. Kiểm tra **thời điểm và phạm vi weaving**: mã được biên dịch, nạp hoặc đi qua proxy nào.
5. Liệt kê các **advice theo thứ tự hiệu lực**, đặc biệt các advice `around`.
6. Theo dõi `proceed`, kết quả và ngoại lệ: phần nghiệp vụ có chạy một lần, nhiều lần hay không chạy?
7. Đối chiếu **stdout, trace hoặc bài kiểm thử** để xem thứ tự quan sát thực tế có phù hợp hợp đồng.

Ví dụ khi không nhìn thấy log `before charge`, những nguyên nhân khả dĩ gồm: pointcut không khớp, điểm call/execution chưa được hỗ trợ, lớp chưa được weaving, đường gọi đi thẳng vào target, hoặc một advice bên ngoài đã chặn trước khi phần bên trong được tiếp tục.

Không thể kết luận nguyên nhân chỉ bằng cách nhìn tên phương thức. Cần đối chiếu cơ chế triển khai và đường gọi thực tế.

### 14.1. Kiểm thử bằng vết thực thi

Một bộ kiểm thử tốt không chỉ kiểm tra đầu ra nghiệp vụ mà còn kiểm chứng trình tự tại những ranh giới cần thiết:

| Ca kiểm thử | Điều cần kiểm tra |
| --- | --- |
| Lời gọi thành công | Advice bắt đầu, nghiệp vụ, advice kết thúc, caller nhận kết quả đúng thứ tự |
| Nghiệp vụ ném lỗi | Advice đường lỗi, cleanup và ngoại lệ tới caller đúng hợp đồng |
| Pointcut không khớp | Không có advice ngoài ý muốn |
| Aspect ngoài từ chối | Nghiệp vụ không chạy, các advice được phép vẫn xử lý đúng |
| Hai aspect cùng khớp | Thứ tự và quan hệ bao quanh đúng |
| Lời gọi nội bộ | Phạm vi interception/weaving đúng như thiết kế |
| Hai lời gọi đồng thời | Ngữ cảnh từng invocation độc lập |
| Thao tác bất đồng bộ | Ranh giới đo và tín hiệu hoàn tất đúng |
| Retry | Số lần chạy phần nghiệp vụ và side effect đúng mong đợi |

Kiểm thử **đường không được can thiệp** cũng cần thiết như kiểm thử đường phải được can thiệp. Pointcut quá rộng có thể vô tình áp dụng cùng chính sách cho một thao tác không thuộc phạm vi.

## 15. Những hiểu nhầm thường gặp

**“Business method tự động gọi aspect.”** Không phải mô hình chung. Thông thường advice được kết hợp bởi cơ chế AOP tại điểm được chọn; thân nghiệp vụ có thể hoàn toàn không tham chiếu aspect.

**“Aspect luôn chạy trước nghiệp vụ.”** Chỉ đúng với phần trước của một số kiểu advice. Có advice xử lý sau khi trả về, sau khi ném lỗi hoặc bao quanh cả thao tác.

**“Aspect chỉ quan sát, không thể đổi kết quả.”** Sai với những mô hình hỗ trợ `around` có quyền bỏ qua, gọi lại, biến đổi kết quả hoặc ngoại lệ. Việc có nên thực hiện quyền đó là câu hỏi thiết kế riêng.

**“Một phương thức có tên khớp thì mọi lời gọi đều qua aspect.”** Chưa chắc. Cần kiểm tra loại join point, điều kiện pointcut và phạm vi cơ chế weaving/interception.

**“Thân nghiệp vụ kết thúc thì caller lập tức nhận kết quả.”** Nếu có advice sau thao tác, caller chỉ nhận kết quả sau khi các bước cần thiết hoàn tất, trừ cách triển khai đặc biệt khác. Với tác vụ bất đồng bộ, còn phải tách thời điểm trả về handle và thời điểm hoàn thành công việc.

**“Nhiều aspect có thứ tự hiển nhiên.”** Không. Thứ tự có thể thay đổi kết quả, log, phân quyền và số liệu đo. Cần cấu hình và kiểm thử theo cơ chế cụ thể.

**“Ghi audit trong advice bảo đảm cùng giao dịch với nghiệp vụ.”** Không tự động. Tính nguyên tử phụ thuộc ranh giới giao dịch và hệ thống ghi dữ liệu thực tế.

**“Có proxy thì mọi lời gọi tới target đều đi qua proxy.”** Sai. Lời gọi trực tiếp trên target hoặc lời gọi nội bộ có thể bỏ qua proxy; những cách weaving khác có khả năng khác.

## 16. Bài tập đọc luồng

### Bài 1. Thành công và lỗi

Giả sử một `around advice` ghi `start`, gọi `proceed`, ghi `success` khi trả về bình thường, ghi `failure` nếu có ngoại lệ thoát ra và luôn ghi `finish` trong `finally`.

- Nếu thao tác trả `42`, thứ tự mong đợi là: `start → business → success → finish → caller nhận 42`.
- Nếu thao tác ném `IllegalStateException` và advice ném lại lỗi gốc, thứ tự là: `start → business → failure → finish → caller nhận lỗi`.

Chú ý phân biệt `success` với việc một ngoại lệ đã được **bắt và xử lý bên trong** nghiệp vụ trước khi phương thức trả về bình thường.

### Bài 2. Hai lớp advice

Có chuỗi `Logging(Authorization(Operation))`. Nếu `Authorization` từ chối mà không tiếp tục, phần nào có thể chạy? 

`Logging` bên ngoài vẫn có thể ghi bắt đầu và kết thúc; `Operation` không chạy; phần sau của `Authorization` sẽ tùy cách advice đó được viết. Nếu đảo thành `Authorization(Logging(Operation))`, lần từ chối trước khi chuyển tiếp có thể khiến `Logging` không được thực thi.

### Bài 3. Lời gọi nội bộ

Một đối tượng `Target` có `outer()` gọi `inner()`. Caller gọi `proxy.outer()` và proxy chỉ chặn lời gọi giao diện đi qua nó. Có chắc advice cho `inner()` sẽ chạy không?

**Không.** Nếu `outer()` chạy trên target và gọi `inner()` trực tiếp, lời gọi đó có thể không qua proxy. Cần dựa trên cơ chế AOP cụ thể mới biết mức độ can thiệp.

### Bài 4. Đo một tác vụ bất đồng bộ

Một advice quanh `startExport()` dừng đồng hồ ngay khi phương thức trả về `Future`. Nó có đo toàn bộ thời gian xuất dữ liệu không?

**Chưa chắc.** Nó có thể chỉ đo thời gian tạo/lên lịch tác vụ. Để đo đến khi xuất dữ liệu hoàn tất phải theo dõi điểm completion phù hợp và chuyển ngữ cảnh đo qua vòng đời tác vụ.

### Bài 5. Điểm gọi và điểm thực thi

`checkout()` gọi `gateway.pay()`; cùng `pay()` còn được gọi từ `retryPayment()`. Nếu muốn ghi log theo **vị trí lời gọi**, chọn cách nghĩ về **method call join point**. Nếu muốn ghi log cho **mọi lần thực thi thực tế của thân `pay()` trong phạm vi weaving**, chọn cách nghĩ về **method execution join point**. Công cụ thực tế có hỗ trợ được cả hai hay không phải được xác minh riêng.

## 17. Tổng kết mô hình tư duy

Mỗi lần theo dõi tương tác giữa nghiệp vụ và aspect, hãy trả lời lần lượt:

1. **Ai khởi phát?** Caller gọi một thao tác theo hợp đồng nghiệp vụ.
2. **Điểm nào bị can thiệp?** Một join point được hệ thống AOP hỗ trợ.
3. **Vì sao điểm đó được chọn?** Pointcut khớp điều kiện cần thiết.
4. **Hành vi nào chạy?** Advice do aspect định nghĩa, với thứ tự đã xác định.
5. **Nghiệp vụ có được thực thi không?** Phụ thuộc chuỗi advice và việc tiếp tục lời gọi.
6. **Điều gì quay về caller?** Kết quả hoặc ngoại lệ sau các xử lý của advice.
7. **Đường nào nằm ngoài phạm vi?** Phụ thuộc loại join point, weaving và đường gọi cụ thể.

**Luồng AOP là sự kết hợp có kiểm soát giữa xử lý nghiệp vụ và các chính sách xuyên suốt tại những điểm thực thi được lựa chọn.** Thiết kế tốt giữ trách nhiệm nghiệp vụ rõ ràng, làm cho điều kiện can thiệp kiểm chứng được, bảo toàn kết quả/ngoại lệ khi cần và thể hiện rành mạch thứ tự cũng như giới hạn của từng aspect.
