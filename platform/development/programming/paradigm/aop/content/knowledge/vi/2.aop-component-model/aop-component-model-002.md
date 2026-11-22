# Join point là điểm có thể can thiệp trong mô hình thực thi AOP

## 1. Join point là gì?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, **join point** là **một điểm được xác định trong mô hình thực thi của chương trình mà cơ chế AOP cho phép gắn thêm hành vi**. Hành vi gắn thêm này thường được gọi là **advice**; tập hợp các điểm cần tác động có thể được diễn đạt bằng **pointcut**.

Định nghĩa cần hiểu theo hai lớp:

1. **Điểm có ý nghĩa trong luồng thực thi:** chẳng hạn trước khi một phương thức bắt đầu, tại một lời gọi phương thức, khi trường dữ liệu được đọc, hoặc khi một ngoại lệ được xử lý.
2. **Điểm thuộc mô hình join point được công cụ hỗ trợ:** một sự kiện xảy ra khi chạy chương trình chưa chắc là join point nếu cơ chế AOP đang sử dụng không thể nhận biết hoặc can thiệp tại đó.

Ví dụ, ứng dụng có các phương thức `PaymentService.pay()` và `RefundService.refund()`. Ta muốn đo thời gian mỗi lần thực hiện nghiệp vụ:

```text
Người dùng gọi pay()
        |
        v
[điểm thực thi pay() bắt đầu]  <-- join point có thể gắn advice bắt đầu đo
        |
   xử lý thanh toán
        |
        v
[điểm thực thi kết thúc]       <-- advice có thể ghi kết quả/thời gian
```

Sơ đồ mang tính **khái niệm**. Trong một mô hình AOP có join point kiểu *method execution*, việc vào thực thi phương thức `pay()` là một join point; advice `around` có thể bao cả lần thực thi đó. Không phải cứ có dòng chương trình hoặc mốc thời gian bất kỳ thì tự nhiên có thể đặt advice vào.

**Phân biệt quan trọng:** join point cho biết **điểm nào có thể can thiệp**, pointcut trả lời **chọn điểm nào**, còn advice mô tả **làm gì tại điểm được chọn**.

## 2. Join point tồn tại trong mô hình thực thi, không chỉ trong mã nguồn

Một chương trình có thể nhìn theo **cấu trúc tĩnh** (lớp, hàm, dòng lệnh) và **diễn tiến động** (những lần gọi, nhánh, ngoại lệ, luồng thực thi). Join point liên quan đến cả hai:

- **Vị trí hoặc loại điểm thực thi xác định được:** ví dụ vị trí gọi `gateway.charge()` ở trong phương thức `checkout()`, hoặc việc bắt đầu thực thi `charge()`.
- **Một lần xuất hiện khi chương trình chạy:** mỗi lần đi qua vị trí đó có thể mang ngữ cảnh khác nhau như tham số, đối tượng đích, kết quả hoặc ngoại lệ.
- **Khả năng can thiệp của công cụ:** có công cụ biến đổi mã đã biên dịch; có công cụ chặn lời gọi qua một đối tượng trung gian. Chúng không nhất thiết quan sát được cùng các điểm.

Một số hệ thống AOP dùng thuật ngữ **join-point shadow** cho vị trí tĩnh trong mã tương ứng với các join point có thể phát sinh lúc chạy. Ví dụ một lời gọi được viết một lần trong vòng lặp có thể tạo ra nhiều lần xuất hiện join point:

```java
for (int i = 0; i < 3; i++) {
    payment.pay(i);
}
```

Nếu cơ chế chọn được điểm gọi `pay(i)`, **một vị trí lời gọi** có thể phát sinh **ba lần thực thi tại điểm đó**, mỗi lần với giá trị `i` khác nhau. Không nên đồng nhất "một dòng mã" với "một lần chạy join point".

Khi một pointcut chứa điều kiện theo tham số hoặc trạng thái khi chạy, việc một vị trí tĩnh có khả năng khớp chưa bảo đảm **mọi lần xuất hiện động** đều thỏa điều kiện. Chẳng hạn chỉ can thiệp khi số tiền thanh toán vượt một ngưỡng; các lần gọi cùng vị trí nhưng số tiền khác nhau có thể cho kết quả khớp khác nhau.

## 3. Join point, pointcut, advice và aspect phối hợp ra sao?

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Join point** | Điểm/sự kiện thực thi thuộc mô hình có thể can thiệp | Một lần bắt đầu thực thi `pay()` |
| **Pointcut** | Điều kiện/quy tắc lựa chọn tập join point | Chọn các lần thực thi thao tác thanh toán |
| **Advice** | Hành vi gắn vào join point được chọn | Ghi log, đo thời gian, kiểm tra chính sách |
| **Aspect** | Đơn vị mô-đun hóa một mối quan tâm xuyên suốt, thường chứa pointcut và advice | `AuditAspect` |
| **Weaving** | Cơ chế kết hợp advice với điểm được chọn trong chương trình | Biến đổi mã hoặc chặn lời gọi tại thời điểm chạy |

Ví dụ **mã giả AOP tổng quát** (không phải cú pháp Java có thể biên dịch trực tiếp):

```text
aspect AuditPayment:
    pointcut paidOperations =
        executionsOf(PaymentService.pay)
        OR executionsOf(RefundService.refund)

    before paidOperations(context):
        audit("start", context.operationName)

    afterFinally paidOperations(context):
        audit("end", context.operationName)
```

Trong ví dụ:

1. Hệ thống thực thi các thao tác thanh toán/hoàn tiền sẽ tạo ra các điểm thực thi tương ứng, **nếu loại điểm này được công cụ hỗ trợ**.
2. `paidOperations` là pointcut chọn các join point thích hợp.
3. Hai advice ghi thông tin trước và khi kết thúc thao tác.
4. Aspect gom mô tả chính sách kiểm toán; weaving làm cho advice thực sự chạy ở các điểm được chọn.

Cú pháp `executionsOf` và `afterFinally` trong ví dụ chỉ diễn đạt ý tưởng; mỗi ngôn ngữ/công cụ AOP có quy ước và khả năng khác nhau. **Chỉ khai báo pointcut không tạo được join point mới ngoài mô hình mà công cụ hỗ trợ.**

### 3.1. Join point khác lời gọi helper như thế nào?

Ở mã thông thường, lập trình viên chèn lời gọi tường minh:

```text
logStart()
pay()
logEnd()
```

Trong AOP, người viết nghiệp vụ có thể chỉ gọi `pay()`; pointcut và cơ chế weaving khiến việc ghi log được áp dụng ở điểm thực thi được chọn. Lợi ích nằm ở khả năng **mô-đun hóa chính sách trải rộng ở nhiều nơi**, nhưng luồng thực tế phải được tài liệu hóa và kiểm thử vì advice có thể không xuất hiện trong thân phương thức nghiệp vụ.

### 3.2. Join point khác event nghiệp vụ như thế nào?

Một **event nghiệp vụ** như `OrderPaid` là thông tin do ứng dụng chủ động phát ra để mô tả sự kiện miền. Một **join point** là vị trí/sự kiện được xác định bởi mô hình thực thi của AOP. Chúng có thể liên quan nhưng không đồng nghĩa: việc trả về từ `pay()` không tự chứng minh thanh toán đã được hệ thống bên ngoài ghi nhận thành công, và một event có thể được phát ra sau nhiều bước bất đồng bộ.

## 4. Những loại join point thường gặp

**Không có một danh sách join point bắt buộc chung cho mọi nền tảng AOP.** Một mô hình có thể bao quát nhiều loại; một cơ chế đơn giản có thể chỉ chặn được lời gọi phương thức đi qua lớp trung gian.

| Loại điểm thực thi | Ý nghĩa | Tình huống sử dụng |
| --- | --- | --- |
| **Method execution** | Khi thân một phương thức được thực thi | Đo thời gian xử lý một phương thức |
| **Method call** | Tại vị trí mã gọi một phương thức | Quan sát một lời gọi từ phía bên gọi |
| **Constructor call/execution** | Khi gọi hoặc thực thi logic khởi tạo đối tượng | Theo dõi hoạt động tạo đối tượng |
| **Field get/set** | Khi đọc hoặc gán giá trị trường | Quan sát truy cập trạng thái |
| **Exception handler** | Khi luồng điều khiển đi vào phần xử lý ngoại lệ | Ghi nhận đường đi xử lý lỗi |
| **Initialization/static initialization** | Các điểm trong vòng đời khởi tạo (nếu được hỗ trợ) | Phân tích giai đoạn khởi tạo |
| **Sự kiện khác do công cụ định nghĩa** | Chỉ tồn tại nếu mô hình join point mô tả được | Những điểm can thiệp dành riêng cho nền tảng |

Một vài điểm cần lưu ý:

- **Đọc trường dữ liệu** và **gọi getter** có thể là hai dạng hoạt động khác nhau; không được coi chúng luôn tương đương.
- **Gọi constructor** khác với **thực thi phần thân constructor**, và có mô hình còn phân biệt các giai đoạn khởi tạo.
- **Ngoại lệ được ném** và **đi vào handler bắt ngoại lệ** là hai sự kiện khác nhau. Một công cụ chỉ hỗ trợ join point của handler không có nghĩa là nó can thiệp được tại mọi lệnh `throw`.
- Một công cụ hỗ trợ method execution không nhất thiết hỗ trợ field access, thao tác native, đoạn code được tối ưu hóa đặc biệt hoặc mọi lời gọi ở môi trường chạy.

Chính **mô hình join point của giải pháp AOP** xác định tập các điểm có thể áp dụng advice. Không nên suy từ tên các loại điểm phổ biến để kết luận ứng dụng cụ thể đã hỗ trợ hết.

## 5. Method call và method execution: hai góc nhìn khác nhau

Đây là phân biệt quan trọng khi học join point ở mức nâng cao.

Giả sử có mã Java:

```java
class PaymentGateway {
    void charge() {
        System.out.println("charging");
    }
}

class CheckoutService {
    void checkout(PaymentGateway gateway) {
        gateway.charge();
    }
}
```

Đây là **đoạn mã minh họa** (không phải chương trình độc lập có `main`).

- **Method-call join point** nằm ở **phía gọi**, tương ứng vị trí biểu thức `gateway.charge()` trong `checkout()`. Ngữ cảnh có thể liên quan đến vị trí, kiểu và đối tượng bên gọi.
- **Method-execution join point** nằm ở **phía phương thức được gọi**, tương ứng việc chạy thân `charge()`. Các lời gọi khác nhau tới cùng phương thức có thể đi vào cùng loại execution join point.

Sơ đồ:

```text
CheckoutService.checkout()              PaymentGateway.charge()
    |                                           |
    |-- gateway.charge() ---------------------->|
    ^                                           ^
    |                                           |
  call join point                         execution join point
  (phía gọi)                              (phía được gọi)
```

Sự phân biệt này có hậu quả thực tế:

1. Nhiều vị trí gọi có thể cùng hướng tới một phương thức thực thi.
2. Một vị trí gọi có thể dẫn đến những triển khai khác nhau qua đa hình hoặc dispatch động.
3. Mã thư viện, lời gọi phản xạ, lời gọi được tạo bởi công cụ hoặc những đường gọi đặc biệt có thể không nằm trong phạm vi weaving đã cấu hình.
4. Một advice gắn ở phía gọi có thể thu thập ngữ cảnh khác với advice gắn ở phía thực thi.

**Không nên đồng nhất** tên phương thức trong pointcut với khái niệm "mọi đường chạy qua phương thức này"; phải xác định pointcut đang chọn kiểu join point nào.

### 5.1. Tương tác với đa hình

Ví dụ biến có kiểu giao diện `PaymentGateway` nhưng lúc chạy trỏ tới một hiện thực cụ thể. Kiểu khai báo tại vị trí call, chữ ký phương thức được gọi, kiểu đối tượng thực tế và việc dispatch tới phần thân thực thi **có thể khác nhau**. Tùy ngôn ngữ và công cụ, các điều kiện pointcut dựa trên kiểu tĩnh hoặc kiểu thực tế có thể khớp khác nhau.

Khi kiểm chứng, cần phân biệt:

- Kiểu/chữ ký phương thức nhìn từ **vị trí gọi**.
- Kiểu/chữ ký của **phần thực thi thực tế**.
- Đối tượng **bên gọi** và đối tượng **đích** (nếu công cụ cung cấp).
- Giá trị **tham số thực tế** tại lần gọi cụ thể.

## 6. Ví dụ Java 17 chạy được: giới hạn điểm can thiệp qua proxy

Không có cú pháp AOP tích hợp sẵn trong ngôn ngữ Java thông thường. Để quan sát rõ tác động của **cơ chế can thiệp**, ta dùng `java.lang.reflect.Proxy` trong JDK để chặn **lời gọi đi qua một proxy giao diện**. Đây là **ví dụ kỹ thuật interception**, không phải một hệ thống AOP tổng quát và không chứng minh mọi loại join point đều được hỗ trợ.

Tạo tệp `JoinPointDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class JoinPointDemo {
    interface TaskService {
        void outer();
        void inner();
    }

    static final class TaskServiceImpl implements TaskService {
        @Override
        public void outer() {
            System.out.println("body:outer");
            inner();
        }

        @Override
        public void inner() {
            System.out.println("body:inner");
        }
    }

    public static void main(String[] args) {
        TaskService target = new TaskServiceImpl();
        TaskService proxy = (TaskService) Proxy.newProxyInstance(
                TaskService.class.getClassLoader(),
                new Class<?>[] { TaskService.class },
                (ignoredProxy, method, arguments) -> {
                    System.out.println("before:" + method.getName());
                    try {
                        return method.invoke(target, arguments);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    } finally {
                        System.out.println("after:" + method.getName());
                    }
                }
        );

        proxy.outer();
        proxy.inner();
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac JoinPointDemo.java
java JoinPointDemo
```

Kết quả mong đợi chính xác:

```text
before:outer
body:outer
body:inner
after:outer
before:inner
body:inner
after:inner
```

**Giải thích kỹ:**

- `proxy.outer()` đi qua proxy nên handler được gọi và in `before:outer`; sau đó nó chuyển tiếp vào `target.outer()`.
- Trong `target.outer()`, lời gọi `inner()` là lời gọi trên chính đối tượng đích; nó **không đi lại qua proxy**, nên không có `before:inner` hay `after:inner` cho lần gọi bên trong này.
- `proxy.inner()` ở cuối chương trình là một lời gọi **đi qua proxy**, nên handler ghi cả `before:inner` và `after:inner`.

Ví dụ giúp phân biệt **“phương thức đã được thực thi”** và **“lời gọi đã đi qua cơ chế can thiệp cụ thể”**. Ở mô hình can thiệp bằng proxy này, điểm có thể chặn là lời gọi đi qua proxy; việc thực thi trực tiếp trên đối tượng đích không tự động được chặn. Một giải pháp AOP có weaving vào mã chương trình có thể quan sát được những điểm thực thi khác. Đây là **giới hạn của cơ chế triển khai**, không phải quy luật rằng mọi AOP đều bỏ qua lời gọi nội bộ.

## 7. Điều gì xảy ra khi advice can thiệp vào join point?

Khi pointcut chọn một join point và weaving đã áp dụng advice, hành vi phụ trợ có thể chạy ở các thời điểm khác nhau so với thao tác gốc:

```text
Một lần thực thi thao tác
  |
  +--> advice trước (before)
  |
  +--> phần xử lý gốc
  |       |
  |       +--> trả về bình thường ----> after returning
  |       |
  |       +--> ném ngoại lệ ----------> after throwing
  |
  +--> advice kết thúc/finally (nếu được hỗ trợ)
```

**Around advice** có thể bao toàn bộ chuỗi, tùy ngữ nghĩa của công cụ. Mã giả:

```text
around selectedExecution(joinPointContext):
    startedAt = monotonicClock()
    try:
        result = proceed(joinPointContext)
        recordSuccess(joinPointContext, monotonicClock() - startedAt)
        return result
    catch error:
        recordFailure(joinPointContext, error)
        throw error
```

Đây là **mã giả**, không phải Java độc lập. `proceed` biểu thị việc tiếp tục thao tác được bao quanh. Việc dùng đồng hồ tăng đơn điệu giúp tính thời lượng; ném lại ngoại lệ giúp giữ tín hiệu lỗi, trong phạm vi ngữ nghĩa của cơ chế advice.

Các kiểu advice có ý nghĩa khác nhau:

- **Before:** xảy ra trước phần xử lý được chọn, nhưng không nhất thiết có quyền sửa kết quả.
- **After returning:** chỉ áp dụng khi hoàn tất bình thường.
- **After throwing:** xử lý đường kết thúc bằng ngoại lệ.
- **After/finally:** dành cho mọi đường kết thúc nếu công cụ cung cấp.
- **Around:** có thể quyết định việc tiếp tục, thứ tự và cách xử lý kết quả/ngoại lệ; cần đặc biệt cẩn trọng.

Không phải mọi hệ thống đều có tất cả những kiểu advice này; ranh giới và thứ tự áp dụng phải được xác định theo mô hình AOP thực tế.

### 7.1. Join point không quyết định chính sách lỗi

Join point chỉ định **chỗ có thể can thiệp**. Nó không tự quyết định:

- Có tiếp tục thao tác gốc hay không.
- Có biến đổi kết quả trả về hay không.
- Có bắt, thay thế hoặc ném lại ngoại lệ hay không.
- Có chạy lại thao tác gốc khi lỗi hay không.

Những quyết định ấy thuộc về advice và hợp đồng ứng dụng. Một around advice vô tình gọi `proceed` hai lần có thể khiến thao tác có tác dụng phụ được thực hiện hai lần; điều này nguy hiểm cho nghiệp vụ thanh toán, gửi thông báo hoặc cập nhật dữ liệu.

## 8. Ngữ cảnh sẵn có tại một join point

Một join point có thể mang theo **ngữ cảnh** cho advice. Mức độ thông tin phụ thuộc vào loại join point và công cụ:

| Thành phần ngữ cảnh | Dùng để làm gì? | Lưu ý |
| --- | --- | --- |
| Loại join point | Phân biệt call, execution, field access… | Tập loại điểm tùy công cụ |
| Chữ ký phương thức/thành phần | Định danh thao tác | Chữ ký tĩnh và đích thực tế có thể khác |
| Vị trí mã nguồn | Truy vết điểm xuất phát | Có thể không có trong mã biên dịch không kèm thông tin nguồn |
| Đối tượng phía gọi/đích | Theo dõi ngữ cảnh đối tượng | Có loại join point không có một hoặc cả hai |
| Tham số thực tế | Phân loại, đo đạc hoặc kiểm tra quy tắc | Cẩn thận dữ liệu nhạy cảm, dữ liệu thay đổi |
| Giá trị trả về | Quan sát kết quả thành công | Chỉ có sau khi hoàn thành bình thường nếu công cụ hỗ trợ |
| Ngoại lệ | Ghi nhận đường thất bại | Chỉ có tại những thời điểm/kiểu advice thích hợp |

Nhiều framework AOP định nghĩa một đối tượng ngữ cảnh cho join point, nhưng tên API và tập thuộc tính không thống nhất. Tránh thiết kế advice dựa trên dữ liệu mà kiểu join point hoặc cơ chế thực thi không bảo đảm cung cấp.

**Vấn đề riêng tư và bảo mật:** tự động ghi lại mọi tham số/kết quả có thể làm lộ mật khẩu, mã truy cập hoặc dữ liệu cá nhân. Nếu dùng join point để quan sát, nên chọn metadata cần thiết, che dữ liệu nhạy cảm và định nghĩa chính sách lưu trữ phù hợp.

## 9. Weaving quyết định điểm nào thật sự có hiệu lực

Về mặt ý tưởng, join point nằm trong mô hình thực thi; để advice chạy tại điểm đó, hệ thống cần một cơ chế **weaving/interception**.

Các hướng triển khai thường gặp:

1. **Compile-time weaving:** kết hợp hành vi vào mã trong quá trình biên dịch.
2. **Load-time weaving:** kết hợp hoặc biến đổi mã khi thành phần được nạp vào môi trường chạy.
3. **Runtime interception/weaving:** dùng cơ chế tại thời điểm chạy, có thể bao gồm proxy hoặc cách biến đổi/can thiệp khác.

Không phải ba cách này có cùng khả năng chọn join point. Ví dụ một proxy chỉ nhìn thấy cuộc gọi qua proxy của nó; cơ chế biến đổi bytecode có thể tác động đến điểm thực thi trong thân lớp mà proxy không thấy, nếu được thiết kế và cấu hình tương ứng.

**Đừng suy luận rằng chỉ cần viết pointcut chọn `execute()` thì mọi đường gọi đều bị can thiệp.** Cần xác minh:

- **Loại join point:** call hay execution, hoặc một loại khác?
- **Vùng mã được weaving:** chương trình của mình, mã thư viện, mã được nạp động?
- **Đường gọi:** bên ngoài, nội bộ, qua proxy, phản xạ hay native?
- **Khả năng công cụ:** có hỗ trợ đúng loại điểm và đối tượng đích không?
- **Thứ tự áp dụng:** nếu nhiều advice cùng khớp, ai chạy trước/sau?

Một lời gọi không bị advice chạm tới có thể là do **điểm đó nằm ngoài mô hình hoặc phạm vi can thiệp**, không nhất thiết do biểu thức pointcut viết sai.

## 10. Các tình huống nâng cao cần hiểu đúng

### 10.1. Một điểm tĩnh, nhiều lần chạy

Một phương thức có thể được gọi nhiều lần, đồng thời trên nhiều luồng và với các tham số khác nhau. Mỗi lần đi qua join point là một **lần xuất hiện động**. Advice đo thời gian không nên dùng chung một biến mốc thời gian có thể ghi đè giữa các lần gọi; nên giữ trạng thái theo lần thực thi tương ứng.

Với chương trình có đệ quy, cùng một vị trí method execution có thể xuất hiện nhiều lần lồng nhau. Advice quanh thao tác đệ quy cần bảo toàn quan hệ gọi lồng nhau và tránh giả định luôn chỉ có một lần bắt đầu/kết thúc đang hoạt động.

### 10.2. Một join point khớp nhiều pointcut

Một lần thực thi `pay()` có thể đồng thời được chọn bởi pointcut kiểm toán, đo thời gian và kiểm soát quyền. Thứ tự quanh thao tác có thể làm thay đổi ngữ nghĩa:

```text
Audit(Authorization(Timing(pay)))
```

Trong thứ tự minh họa này, audit có thể nhìn thấy một lần gọi bị từ chối quyền, còn timer bên trong chỉ đo được các lần vượt qua kiểm tra. Nếu đổi thứ tự thành `Authorization(Audit(Timing(pay)))`, việc bị từ chối sớm có thể không được audit bởi advice bên trong. Cách công cụ chọn thứ tự mặc định có thể khác nhau: **phải xác định thứ tự rõ ràng, rồi kiểm thử các đường thành công và thất bại**.

### 10.3. Kiểm soát điều kiện động

Một pointcut có thể chọn join point dựa trên cả điều kiện cấu trúc (loại phương thức, kiểu đối tượng) và điều kiện lúc chạy (giá trị tham số, trạng thái). Trong trường hợp đó:

- Vị trí tĩnh thuộc **tập điểm có khả năng khớp**.
- Một lần xuất hiện cụ thể chỉ **thật sự được advice xử lý** khi điều kiện động thỏa.
- Điều kiện động có thể tăng chi phí kiểm tra; điều kiện dựa vào trạng thái dễ đổi có thể khiến việc quan sát khó dự đoán.

Chọn điểm bằng quy tắc quá rộng gây tác động không mong muốn; quy tắc quá hẹp bỏ sót điểm cần bảo vệ.

### 10.4. Bất đồng bộ và ranh giới thời gian

Giả sử phương thức `startPaymentAsync()` trả về ngay một đối tượng công việc hoặc tương lai (future), rồi công việc mới hoàn tất sau đó. Advice quanh **lần thực thi phương thức trả về** có thể đo được thời gian khởi tạo tác vụ, **không nhất thiết là thời gian thanh toán hoàn tất**.

Muốn theo dõi trọn công việc bất đồng bộ, thiết kế phải chọn ranh giới hoàn tất thật sự (ví dụ callback/completion) và quản lý ngữ cảnh giữa các luồng/tác vụ. Không được coi mọi kết quả trả về là kết thúc nghiệp vụ.

### 10.5. Tác động của tối ưu hóa và mã không thuộc phạm vi quản lý

JIT, mã native, thư viện nạp riêng, phản xạ hoặc trình biên dịch có thể thay đổi cách thực thi. Khả năng nhìn thấy join point và bảo toàn advice phụ thuộc vào cam kết của công cụ AOP cũng như điểm weaving đã được cài đặt. Việc phương thức được inline hay tối ưu hóa không nên bị suy đoán là chắc chắn làm mất hoặc giữ join point trong mọi hệ thống.

### 10.6. Join point là ranh giới kỹ thuật, không tự tạo bảo đảm an ninh

Nếu dùng advice tại join point để kiểm tra truy cập, hãy chứng minh **mọi đường vào cần bảo vệ** đều đi qua điểm can thiệp. Nếu còn đường gọi trực tiếp bỏ qua proxy hoặc một lời gọi không được weaving, chính sách có thể bị bỏ qua. Các bất biến an toàn quan trọng phải được thiết kế với ranh giới tin cậy rõ ràng và kiểm chứng đầy đủ.

## 11. Cách thiết kế, kiểm chứng một tập join point

Khi muốn áp dụng chính sách AOP vào nhiều thao tác, có thể làm lần lượt:

1. **Xác định concern:** ví dụ đo thời gian xử lý thao tác thanh toán; không lẫn vào thuật toán tính tiền.
2. **Xác định ranh giới mong muốn:** muốn đo *lần gọi từ phía bên ngoài* hay *lần thực thi phương thức*, trước khi khởi tạo hay sau khi hoàn tất?
3. **Chọn loại join point mà công cụ hỗ trợ:** method call, execution, field access hay loại khác; đọc đúng khả năng triển khai.
4. **Diễn đạt pointcut tối thiểu:** chọn những điểm có chủ ý; tránh wildcard quá rộng hoặc phụ thuộc vào tên tình cờ.
5. **Xác định advice và thứ tự:** kết quả, ngoại lệ, chạy một lần hay nhiều lần, tình huống bị ngăn thực thi.
6. **Kiểm thử hành vi:** một đường phải được can thiệp; một đường không được can thiệp; lời gọi nội bộ/đa hình nếu liên quan; lỗi, đồng thời và bất đồng bộ.
7. **Kiểm tra chi phí và khả năng quan sát:** tác động hiệu năng, dữ liệu ghi nhận, độ dễ truy vết và chính sách nhạy cảm dữ liệu.

Ví dụ bảng ca kiểm thử cho một hệ thống muốn đo mọi lần thực thi của một nhóm thao tác:

| Tình huống | Kết quả mong muốn | Điều cần xác minh |
| --- | --- | --- |
| Gọi `pay()` ở đường sử dụng chuẩn | Đo đúng một lần | Điểm khớp pointcut và advice chạy |
| Gọi `pay()` qua một đường khác | Theo chính sách đã thiết kế | Đường đó nằm trong phạm vi weaving hay không |
| Lời gọi nội bộ trong cùng đối tượng | Theo bảo đảm thực tế của công cụ | Có bị bỏ qua do proxy không |
| Phương thức ném lỗi | Có đo và ghi trạng thái lỗi nếu yêu cầu | Advice không nuốt ngoại lệ |
| Nhiều luồng chạy đồng thời | Dữ liệu từng lần không chồng lẫn | Mốc thời gian/ngữ cảnh theo từng invocation |
| Gọi tác vụ bất đồng bộ | Đo đúng ranh giới đã công bố | Phương thức trả về hay tác vụ hoàn thành |
| Phương thức ngoài danh sách | Không bị ảnh hưởng | Pointcut không quá rộng |

Kiểm thử cả trường hợp **không khớp** là thiết yếu, vì pointcut quá rộng có thể tạo lỗi dù những ca cần can thiệp đều hoạt động.

## 12. Lỗi hiểu sai thường gặp

**Nhầm “mọi chỗ có thể đặt lệnh” với join point.** Join point chỉ bao gồm các điểm mà mô hình AOP cụ thể xác định và hỗ trợ. Không phải từng dòng lệnh, từng phép cộng hoặc mọi sự kiện chạy đều có join point độc lập.

**Nhầm join point với pointcut.** Join point là điểm/sự kiện thực thi; pointcut là quy tắc chọn nhiều điểm. Một pointcut có thể khớp nhiều điểm và một điểm có thể khớp nhiều pointcut.

**Nhầm method call với method execution.** Method call nhìn từ phía vị trí gọi; method execution nhìn từ phía thân được thực thi. Điều này ảnh hưởng đến nơi advice chạy và ngữ cảnh quan sát được.

**Nhầm lời gọi đi qua proxy với toàn bộ lần thực thi của target.** Proxy chỉ thấy những lời gọi đi qua nó. Cơ chế weaving khác có thể có tập điểm rộng hơn hoặc những giới hạn khác.

**Cho rằng advice không thể ảnh hưởng nghiệp vụ.** Around advice có thể bỏ qua, gọi lại hoặc làm biến đổi kết quả nếu cơ chế cho phép. Phải kiểm soát rõ hợp đồng của thao tác gốc.

**Cho rằng thấy method return nghĩa là việc bất đồng bộ đã hoàn tất.** Một phương thức trả về future hoặc handle có thể kết thúc trước tác vụ thật sự.

**Cho rằng quan sát được join point là bảo đảm mọi đường gọi đều bị bảo vệ.** Một chính sách quan trọng cần kiểm tra phạm vi weaving và các đường truy cập khác, không chỉ kiểm tra cú pháp pointcut.

## 13. Câu hỏi tự kiểm tra

**1. Một vị trí gọi `pay()` nằm trong vòng lặp chạy năm lần. Có bao nhiêu join point?**

Có thể có **một vị trí tĩnh** tương ứng nhiều lần xuất hiện khi chạy — thường là năm lần, nếu mỗi lượt đều đi qua vị trí đó. Việc công cụ có thực sự chọn/can thiệp hay không còn tùy pointcut và cơ chế weaving.

**2. Vì sao advice cho `inner()` không chạy trong lời gọi `outer() -> inner()` ở ví dụ Java?**

Vì lời gọi nội bộ được thực hiện trực tiếp trên `target`, không đi qua `proxy`. Lệnh `proxy.inner()` độc lập sau đó đi qua proxy nên bị chặn. Đây là đặc điểm của ví dụ interception bằng proxy.

**3. Khi nào cần phân biệt call và execution join point?**

Khi quan tâm đến phía gọi hoặc phía được gọi, nhiều vị trí gọi tới cùng phương thức, đa hình, phạm vi mã được weaving, hoặc metadata chỉ có ở một phía.

**4. Một join point được chọn bởi hai aspect có đảm bảo hai advice chạy theo thứ tự viết trong mã không?**

Không thể kết luận chung. Cần xác minh quy tắc ưu tiên/thứ tự của cơ chế AOP đang dùng và kiểm thử sự kết hợp của advice, đặc biệt khi có quyền từ chối thao tác hoặc thay đổi ngoại lệ.

**5. Có nên dùng join point để đo thời gian hoàn thành của một tác vụ bất đồng bộ chỉ bằng advice quanh phương thức khởi tạo không?**

Không đủ trong nhiều trường hợp. Advice đó có thể chỉ đo thời gian phương thức tạo/trả tác vụ; cần xác định điểm hoàn tất công việc và ràng buộc ngữ cảnh đúng.

## 14. Ghi nhớ

**Join point là một điểm có thể can thiệp trong mô hình thực thi mà giải pháp AOP hỗ trợ.** Tại những điểm được **pointcut** chọn, **advice** mới có thể được kết hợp thông qua **weaving/interception**. Muốn hiểu đúng và dùng AOP an toàn phải phân biệt *vị trí tĩnh* với *lần xuất hiện động*, *call* với *execution*, và *điểm mong muốn can thiệp* với *điểm công cụ thật sự chặn được*. Đây là nền tảng để thiết kế, giải thích và kiểm chứng các aspect mà không làm mơ hồ luồng chạy của chương trình.
