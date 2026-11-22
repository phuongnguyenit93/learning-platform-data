# Điều kiện tĩnh và điều kiện cần đánh giá lúc chạy trong pointcut AOP

> **Mục tiêu học tập:** Phân biệt những điều kiện lựa chọn join point có thể quyết định từ cấu trúc chương trình với những điều kiện phụ thuộc dữ liệu/ngữ cảnh tại **mỗi lần thực thi**; hiểu cách hai nhóm điều kiện phối hợp trong một pointcut, thời điểm đánh giá, lợi ích của việc lọc sớm, giới hạn của weaving và cách kiểm thử để tránh lựa chọn thừa hoặc bỏ sót điểm can thiệp.

## 1. Vì sao cùng một phương thức có lần được chọn, lần không?

Giả sử một chính sách AOP cần đo thời gian xử lý **chỉ khi** một thao tác thanh toán có mã khách hàng thuộc nhóm ưu tiên và số tiền đạt ngưỡng. Phương thức có thể được gọi nhiều lần:

~~~java
pay("VIP", 120);
pay("VIP", 20);
pay("NORMAL", 150);
~~~

*Đây là ba lời gọi minh họa, chưa phải chương trình Java độc lập.*

Cả ba lời gọi có cùng **phương thức được chọn theo tên và chữ ký**. Nhưng điều kiện **giá trị đối số** chỉ đúng ở lần đầu.

Muốn mô tả chính sách đó, ta cần hai loại thông tin:

- **Thông tin cấu trúc:** có đang thực thi phương thức `pay(String, int)` trong loại thành phần dự định không? Phương thức có dấu hiệu khai báo cần thiết không?
- **Thông tin động:** ở lần gọi cụ thể, tier có bằng `"VIP"` và amount có đạt ngưỡng `100` hay không?

Trong AOP (Aspect-Oriented Programming), **pointcut** mô tả điều kiện chọn một tập **join point**; **advice** là hành vi bổ sung tại các điểm được chọn. Điều kiện có thể có phần xác định được từ cấu trúc mã và phần phải kiểm tra khi chương trình chạy. Đây là cốt lõi của việc phân biệt **static matching** và **dynamic matching**.

Không được suy rằng tên gọi “static” ở đây chỉ nói đến từ khóa `static` của Java. “Tĩnh” nói về **thông tin cần để quyết định điều kiện**, hoàn toàn khác với khái niệm **static method**.

## 2. Join point, pointcut, shadow và lần xuất hiện động

Những khái niệm dưới đây cần được giữ riêng:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Join point** | Điểm/sự kiện trong mô hình thực thi mà cơ chế AOP có thể nhận diện | Một lần thực thi của `pay(...)` |
| **Join point shadow** | Vị trí trong mã có khả năng tạo join point tại lúc chạy, trong những mô hình có thuật ngữ này | Thân phương thức `pay(String,int)` hoặc một call site |
| **Pointcut** | Điều kiện chọn những join point cần áp dụng chính sách | Chọn `pay` khi tier VIP và amount đạt ngưỡng |
| **Điều kiện tĩnh** | Phần lựa chọn có thể quyết định từ thông tin cấu trúc được cung cấp, không cần giá trị của lần chạy đó | Tên, chữ ký, loại join point |
| **Điều kiện động** | Phần phụ thuộc dữ liệu hoặc ngữ cảnh của một lần xuất hiện | Giá trị đối số, đối tượng thực tế, luồng điều khiển |
| **Advice** | Hành vi thực hiện tại join point được chọn | Ghi bắt đầu/kết thúc |
| **Weaving** | Cơ chế kết hợp hành vi aspect vào chương trình | Kết hợp advice tại phạm vi điểm được hỗ trợ |

Một phương thức được biên dịch một lần nhưng thực thi nhiều lần. Với pointcut chỉ dựa trên **chữ ký phương thức**, các lần đó thường cho cùng một câu trả lời lựa chọn (giả sử cấu trúc mã không thay đổi). Với pointcut dựa trên **đối số thực tế**, mỗi lần thực thi có thể cho câu trả lời khác nhau.

Các tên như *shadow* hoặc cách phân loại join point là những khái niệm trong một số mô hình AOP; không phải mọi công cụ đều mô tả hoặc cung cấp cùng loại điểm.

## 3. Định nghĩa chính xác điều kiện tĩnh

Một điều kiện được gọi là **tĩnh** khi kết quả chọn có thể được xác định từ **thông tin không thay đổi giữa các lần xuất hiện của điểm đang xét**, trong phạm vi mô hình và cấu hình hiện hành.

Ví dụ mô tả khái niệm:

~~~text
S(j) =
    kind(j) = METHOD_EXECUTION
    AND declaredMethodName(j) = "pay"
    AND declaredParameterTypes(j) = (String, int)
~~~

Nếu cơ chế biết trước loại join point và chữ ký khai báo, nó có thể kết luận rằng những điểm không thuộc `pay(String,int)` **không bao giờ được chọn bởi phần này**.

Những đặc tính thường dùng cho static matching khi mô hình AOP hỗ trợ:

- Loại join point: method execution, method call, constructor execution, field access…
- Tên phương thức, lớp khai báo và chữ ký tham số.
- Phạm vi kiểu hoặc package theo cấu trúc đã biết.
- Modifier khai báo như public/private/static/final khi có ý nghĩa trong ngôn ngữ biểu thức.
- Metadata khai báo được công cụ đọc trong giai đoạn phù hợp, ví dụ annotation.
- Vị trí mã/call site đối với những mô hình có khả năng xác định chúng.

**Lưu ý quan trọng:** “Có thể xác định bằng thông tin cấu trúc” **không đồng nghĩa** “bắt buộc được đánh giá khi biên dịch”. Công cụ có thể lấy thông tin ấy lúc biên dịch, lúc nạp lớp hoặc ở thời điểm thiết lập một cơ chế can thiệp. Thời điểm **đánh giá** khác với **loại thông tin mà điều kiện cần**.

### 3.1. Khi nào thông tin trông có vẻ tĩnh nhưng chưa đủ?

Một biểu thức “đối tượng đích có runtime type là `PremiumPaymentService`” phụ thuộc kiểu thực tế của receiver tại lần chạy nếu kiểu ấy chưa xác định. Dù tên lớp là một hằng chuỗi, bản chất phép kiểm tra vẫn có thể **động**.

Ngược lại, “phương thức được khai báo trong `PaymentService`” có thể là cấu trúc xác định ngay từ mô tả phương thức. Phân biệt **declared type** với **runtime type** giúp tránh nhầm lẫn.

## 4. Định nghĩa chính xác điều kiện cần đánh giá lúc chạy

**Điều kiện động** chỉ quyết định được khi có dữ liệu/ngữ cảnh của một **lần xuất hiện thực tế**. Ví dụ:

~~~text
D(event) =
    actualArg(event, 0) = "VIP"
    AND actualArg(event, 1) >= 100
~~~

Giá trị đối số thay đổi giữa các lời gọi nên dù cùng một phương thức, `D` có thể đúng ở sự kiện này và sai ở sự kiện khác.

Các nguồn thông tin động thường gặp khi mô hình AOP hỗ trợ:

- Giá trị tham số tại lần gọi.
- Kiểu runtime hoặc danh tính của receiver/target.
- Ngữ cảnh luồng điều khiển: join point xảy ra bên trong một chuỗi lời gọi nhất định hay không.
- Trạng thái khả dụng lúc chạy mà một điều kiện động hợp lệ được phép kiểm tra.
- Ngữ cảnh theo luồng/tác vụ, nếu công cụ có thể truyền và đọc nó ở đúng join point.

**Điều kiện động không đương nhiên được phép đọc mọi biến cục bộ** nằm bên trong thân phương thức. Mỗi mô hình join point chỉ cung cấp một tập thông tin nhất định. Ví dụ, AOP chỉ đặt điểm chặn tại lời gọi method có thể đọc những đối số mà điểm chặn nhận được; nó không tự nhìn thấy mọi biến nội bộ hoặc tất cả tác dụng phụ sau đó.

### 4.1. “Đánh giá lúc chạy” không có nghĩa “luôn luôn chậm”

Một so sánh số nguyên lúc chạy có thể rất rẻ; một phép tra cứu trạng thái phức tạp có thể đắt. Chi phí phụ thuộc biểu thức và cách triển khai, không chỉ nhãn static/dynamic. Tối ưu hợp lý bắt đầu từ **tránh kiểm tra động tại điểm đã chắc chắn không khớp theo cấu trúc**.

## 5. Mô hình toán học: lọc tĩnh rồi lọc động

Gọi:

- `J`: tập join point mà công cụ AOP có thể xét.
- `s`: một vị trí/cấu trúc điểm ứng viên.
- `e`: một lần xuất hiện động tương ứng khi chạy.
- `S(s)`: điều kiện tĩnh.
- `D(e)`: điều kiện động.
- `P(e)`: kết quả lựa chọn của pointcut đối với lần xuất hiện `e`.

Một mô hình đơn giản là:

~~~text
P(e) = S(shadow(e)) AND D(e)
~~~

Trong đó `shadow(e)` chỉ vị trí cấu trúc gắn với lần xuất hiện động `e`, khi mô hình có khái niệm tương ứng.

Nếu `S` sai, toàn bộ `P` sai **bất kể** đối số, receiver hay luồng điều khiển. Nếu `S` đúng, muốn kết luận `P` đúng còn phải đánh giá `D`.

| S (tĩnh) | D (động) | P = S AND D |
|---|---|---|
| Sai | Sai | Sai |
| Sai | Đúng theo giá trị giả định | Sai |
| Đúng | Sai | Sai |
| Đúng | Đúng | **Đúng** |

Về thực thi, với những điểm đã được loại bởi phần tĩnh, **không cần đánh giá D**. Đây là cơ sở của phép lọc hai giai đoạn.

Tất nhiên, không phải mọi pointcut có thể tách sạch thành một `S` duy nhất và một `D` duy nhất bằng cú pháp đơn giản; những biểu thức có nhiều nhánh OR, loại join point khác nhau và ngữ cảnh phức tạp có thể cần nhiều tập con hoặc trạng thái trung gian.

## 6. Ba kết quả trong phân tích tĩnh: luôn đúng, luôn sai, cần kiểm tra động

Một cách mô tả tối ưu hữu ích là phân tích một **join point shadow** và trả về một trong ba trạng thái:

1. **NEVER / luôn sai:** chắc chắn điểm đó không khớp pointcut; không cần chèn logic advice.
2. **ALWAYS / luôn đúng:** theo thông tin và hợp đồng đang xét, điểm đó luôn khớp; không cần điều kiện động cho chính pointcut đó.
3. **MAYBE / phụ thuộc lúc chạy:** có khả năng khớp, cần sinh hoặc đặt một phép kiểm tra động.

Ví dụ:

~~~text
Pointcut: execution(pay(String,int)) AND tier == "VIP"

Một vị trí refund(String,int):
    structural match = NEVER

Một vị trí pay(String,int):
    structural match = MAYBE
    vì tier của từng lần chạy chưa được biết
~~~

Với pointcut chỉ là `execution(pay(String,int))`, cùng vị trí `pay` có thể được kết luận **ALWAYS** về phần phù hợp của pointcut, trong phạm vi mô hình xác định.

Tên **ALWAYS / NEVER / MAYBE** là cách giải thích kết quả phân tích; không nhất thiết là enum hay API công khai của công cụ. Cũng cần phân biệt kết quả *pointcut có thể khớp* với việc advice **thật sự chạy**: mã có thể không bao giờ được thực thi trong ca thử, nằm ngoài phạm vi weaving hoặc bị ràng buộc bởi đường can thiệp.

## 7. Ví dụ Java 17: cùng phương thức, kết quả lựa chọn khác nhau từng lần gọi

Chương trình sau **mô phỏng** tách điều kiện tĩnh/động bằng `java.lang.reflect.Proxy`. Nó sử dụng Java chuẩn để cho thấy:

- **Kiểm tra tĩnh một lần trong bước chuẩn bị**: phương thức giao diện có dấu hiệu `@Observed`, tên là `pay` và có hai tham số với đúng kiểu.
- **Kiểm tra động ở mỗi lời gọi đủ điều kiện tĩnh**: tier là `"VIP"`, amount từ 100 trở lên.
- **Phần can thiệp** chỉ in before/after cho lời gọi thỏa cả hai điều kiện.

**Giới hạn cần nhớ:** Đây là ví dụ trực quan về điều kiện lựa chọn; Java Dynamic Proxy chỉ quan sát các lời gọi **đi qua proxy** của giao diện. Nó không phải một hệ AOP tự động weaving mọi loại join point. Phần `after` trong chương trình chỉ chạy sau khi lời gọi đích hoàn tất bình thường.

Lưu file **`StaticDynamicPointcutDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Map;

public class StaticDynamicPointcutDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Observed {}

    public interface PaymentService {
        @Observed
        String pay(String tier, int amount);

        String status(String code);
    }

    public static class PaymentImpl implements PaymentService {
        @Override
        public String pay(String tier, int amount) {
            System.out.println("business pay " + tier + " " + amount);
            return "receipt-" + tier + "-" + amount;
        }

        @Override
        public String status(String code) {
            System.out.println("business status " + code);
            return "status-" + code;
        }
    }

    // Phần cấu trúc: có thể chuẩn bị trước các lần gọi.
    static boolean staticMatch(Method method) {
        return method.isAnnotationPresent(Observed.class)
                && method.getName().equals("pay")
                && method.getReturnType() == String.class
                && method.getParameterCount() == 2
                && method.getParameterTypes()[0] == String.class
                && method.getParameterTypes()[1] == int.class;
    }

    // Phần động: giá trị có thể đổi ở từng lần gọi.
    static boolean dynamicMatch(Object[] values) {
        return values != null
                && values.length == 2
                && "VIP".equals(values[0])
                && values[1] instanceof Integer amount
                && amount >= 100;
    }

    static Object invoke(Method method, Object target, Object[] values)
            throws Throwable {
        try {
            return method.invoke(target, values);
        } catch (InvocationTargetException e) {
            throw e.getCause();
        }
    }

    public static void main(String[] args) throws Exception {
        Method pay = PaymentService.class.getMethod(
                "pay", String.class, int.class);
        Method status = PaymentService.class.getMethod(
                "status", String.class);

        Map<Method, Boolean> staticMatches = Map.of(
                pay, staticMatch(pay),
                status, staticMatch(status)
        );

        System.out.println("static candidates: pay="
                + staticMatches.get(pay)
                + ", status=" + staticMatches.get(status));

        PaymentService target = new PaymentImpl();
        PaymentService proxy = (PaymentService) Proxy.newProxyInstance(
                PaymentService.class.getClassLoader(),
                new Class<?>[] {PaymentService.class},
                (proxyObject, method, values) -> {
                    boolean staticOk = staticMatches.getOrDefault(
                            method, false);
                    boolean dynamicOk = staticOk && dynamicMatch(values);

                    System.out.println("[pointcut] " + method.getName()
                            + " static=" + (staticOk ? "Y" : "N")
                            + " dynamic=" + (staticOk
                                    ? (dynamicOk ? "Y" : "N")
                                    : "SKIP"));

                    if (dynamicOk) {
                        System.out.println("[advice] before "
                                + method.getName());
                    }

                    Object result = invoke(method, target, values);

                    if (dynamicOk) {
                        System.out.println("[advice] after "
                                + method.getName());
                    }
                    return result;
                }
        );

        System.out.println(proxy.pay("VIP", 120));
        System.out.println(proxy.pay("VIP", 20));
        System.out.println(proxy.pay("NORMAL", 150));
        System.out.println(proxy.status("A-1"));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac StaticDynamicPointcutDemo.java
java StaticDynamicPointcutDemo
~~~

**Stdout chính xác:**

~~~text
static candidates: pay=true, status=false
[pointcut] pay static=Y dynamic=Y
[advice] before pay
business pay VIP 120
[advice] after pay
receipt-VIP-120
[pointcut] pay static=Y dynamic=N
business pay VIP 20
receipt-VIP-20
[pointcut] pay static=Y dynamic=N
business pay NORMAL 150
receipt-NORMAL-150
[pointcut] status static=N dynamic=SKIP
business status A-1
status-A-1
~~~

### 7.1. Đọc kết quả theo hai giai đoạn

| Lần gọi qua proxy | Phần tĩnh | Phần động | Advice | Vì sao? |
|---|---|---|---|---|
| `pay("VIP",120)` | Đúng | Đúng | **Có** | Đúng chữ ký/annotation và giá trị |
| `pay("VIP",20)` | Đúng | Sai | Không | Số tiền dưới ngưỡng |
| `pay("NORMAL",150)` | Đúng | Sai | Không | tier không phải VIP |
| `status("A-1")` | Sai | **Không đánh giá** | Không | Không thuộc cấu trúc được chọn |

Lời gọi `status` được hiển thị `dynamic=SKIP` để nhấn mạnh rằng **khi phần tĩnh chắc chắn sai, phần động không cần chạy**. Tuy nhiên, mã nghiệp vụ của `status` vẫn chạy bình thường. Điều kiện pointcut quyết định có gắn hành vi bổ sung hay không; nó không quyết định liệu hoạt động nghiệp vụ có được thực thi, trừ khi một advice khác có chủ đích làm thay đổi luồng điều khiển.

### 7.2. Annotation được đọc ở đâu?

Trong ví dụ, `@Observed` nằm ở phương thức **giao diện** và `Method` mà proxy dùng cũng thuộc giao diện. `@Retention(RUNTIME)` làm annotation có thể được reflection đọc lúc chạy.

Nếu đặt annotation **chỉ trên phương thức của lớp triển khai** mà vẫn dùng `Method` từ giao diện, kết quả `isAnnotationPresent` có thể khác. Một công cụ AOP khác có thể quy định lookup metadata theo lớp đích, interface, method được resolve hoặc chuỗi kế thừa. Đó là vấn đề **nguồn thông tin cấu trúc**, không có nghĩa annotation đột nhiên trở thành điều kiện phụ thuộc giá trị tham số.

### 7.3. Bảng tĩnh không làm biến mất mọi kiểm tra lúc chạy

`Map<Method, Boolean>` được lập trước các lời gọi để minh họa quá trình **chuẩn bị tập ứng viên theo cấu trúc**. Handler vẫn cần tìm cờ ứng viên mỗi lần lời gọi đi qua proxy, rồi kiểm tra đối số cho các lời gọi đủ điều kiện. Cơ chế weaving thực tế có thể tạo mã khác, phân giải/caching ở thời điểm khác hoặc loại hẳn các điểm không cần chặn.

Đừng đồng nhất cách tổ chức `Map` ở Java thuần với thuật toán bắt buộc của mọi bộ máy AOP.

## 8. Tại sao phải phân biệt “điều kiện động” với “advice”?

Một số người đặt kiểm tra giá trị bên trong advice:

~~~text
Pointcut rộng: chọn mọi lần thực thi pay(...)
Advice:
    nếu tier = "VIP" và amount >= 100:
        ghi đo lường
~~~

Một cách khác là mô tả điều kiện giá trị như một phần của pointcut (nếu ngôn ngữ/cơ chế AOP hỗ trợ), để chỉ chọn những lần cần chạy advice.

**Sự khác biệt về thiết kế:**

- **Pointcut động:** thể hiện *khi nào một join point đủ điều kiện để advice tham gia*.
- **Điều kiện trong advice:** thể hiện *hành vi bên trong advice cần thực hiện gì*, sau khi advice đã được kích hoạt bởi pointcut.

Hai cách có thể cùng tạo một dòng log ở ví dụ đơn giản nhưng **không mặc nhiên tương đương** về thứ tự, kiểm soát luồng, giá trị trả về, ngoại lệ, chi phí hoặc khả năng phối hợp với nhiều advice.

Không nên đẩy mọi quy tắc nghiệp vụ vào pointcut. Nếu điều kiện gắn với quyết định nghiệp vụ sâu bên trong, tốt hơn nên thiết kế một ranh giới API/chính sách nghiệp vụ rõ ràng rồi lựa chọn AOP ở ranh giới thực sự xuyên suốt.

## 9. Điều kiện cấu trúc nào hay được xem là tĩnh?

### 9.1. Tên phương thức và chữ ký

Ví dụ mô tả:

~~~text
execution of pay(String, int)
~~~

Khi cơ chế có loại join point method execution và biết chữ ký khai báo, phần lựa chọn có thể được quyết định theo cấu trúc. Với overload như `pay(String)` và `pay(String,int)`, hai chữ ký khác nhau; cần tránh wildcard quá rộng vô tình bao phủ cả hai.

Trong Java, generic type arguments chịu **type erasure**. Một biểu thức muốn chọn dựa trên `List<String>` đối lập `List<Integer>` cần kiểm tra metadata/cơ chế thực tế; không được giả định mỗi loại generic đều tạo một chữ ký runtime độc lập.

### 9.2. Lớp, interface, package và modifier

“Phương thức được khai báo trong package X” thường là điều kiện cấu trúc; “receiver thật lúc chạy có runtime type Y” có thể cần thông tin động. Một cơ chế weaving có thể suy ra một số trường hợp từ cấu trúc để tránh phép kiểm tra runtime; nhưng không được suy ngược rằng mọi điều kiện liên quan kiểu đều tĩnh.

Modifier `static` trong Java là metadata của một method; kiểm tra **method có khai báo static hay không** có thể là điều kiện tĩnh. Điều này khác hoàn toàn với nhãn “static pointcut matching”.

### 9.3. Annotation/metadata

Một dấu hiệu khai báo có thể là điều kiện cấu trúc nếu công cụ kiểm tra trên phần tử đã xác định (class/method/field). Phải làm rõ **vị trí khai báo**, thời điểm metadata có thể truy xuất, chính sách kế thừa annotation và việc weave những lớp liên quan.

Không phải mọi annotation đều tồn tại ở runtime. Một số được dùng ở giai đoạn nguồn hoặc class file theo retention của Java; khả năng nhìn thấy qua reflection thông thường khác với khả năng phân tích bytecode.

## 10. Điều kiện động nào thường cần kiểm tra theo từng lần xuất hiện?

### 10.1. Giá trị đối số

Cùng `pay(String,int)`, lời gọi `pay("VIP",120)` và `pay("NORMAL",120)` chỉ khác dữ liệu đầu vào. Nếu mục tiêu là chọn **VIP**, pointcut phải dùng thông tin giá trị ở lần chạy hoặc ranh giới khác thể hiện rõ phân loại đó.

### 10.2. Kiểu đối tượng đích thực tế

Một biến kiểu interface có thể tham chiếu nhiều lớp triển khai. Nếu pointcut phân biệt theo **runtime receiver type**, nó có thể cần kiểm tra đối tượng của lần thực thi, trong phạm vi mô hình hỗ trợ `this`, `target` hoặc khái niệm tương ứng.

Cần phân biệt kiểm tra **kiểu khai báo của phương thức**, **kiểu runtime của đối tượng** và **kiểu tham số thực tế**. Ba thông tin không nhất thiết trùng nhau.

### 10.3. Luồng điều khiển

Một điều kiện như “chỉ khi lời gọi xảy ra **trong luồng điều khiển của một thao tác cấp cao**” phụ thuộc ngữ cảnh tại thời điểm join point xuất hiện. Những mô hình AOP có hỗ trợ loại điều kiện này có thể phải theo dõi trạng thái ngữ cảnh hoặc chuỗi thực thi.

Một lời gọi thực hiện trên thread khác hoặc công việc bất đồng bộ **không mặc nhiên vẫn nằm trong cùng ngữ cảnh**. Cách truyền dữ liệu liên luồng là một thiết kế riêng, không thể tự suy ra từ biểu thức pointcut.

### 10.4. Trạng thái bên ngoài

Điều kiện đọc trạng thái thay đổi của một cấu hình, đối tượng hoặc thành phần ngoài có thể là động. Tuy nhiên, việc nhúng một lời gọi I/O chậm hoặc có tác dụng phụ vào điều kiện chọn cần được cân nhắc nghiêm túc. Nhiều ngôn ngữ pointcut không cho phép tùy ý gọi mã như vậy; nếu có, chi phí, exception và tính quyết định cần được làm rõ.

## 11. Điều kiện tĩnh và điều kiện động có thể kết hợp bằng logic

Xét các predicate:

~~~text
S1 = methodName = "pay"
S2 = declaredReturnType = String

D1 = tier = "VIP"
D2 = amount >= 100

P = (S1 AND S2) AND (D1 AND D2)
~~~

Điểm khớp khi thỏa **toàn bộ** điều kiện. Nếu thêm ngoại lệ:

~~~text
E = isInternalCall

P = (S1 AND S2) AND D1 AND D2 AND NOT E
~~~

Thì ngay cả lời gọi VIP đạt ngưỡng cũng không được chọn nếu thuộc ngoại lệ E.

Có thể dùng OR để cho phép nhiều nhóm:

~~~text
P = (S_pay AND D_vip) OR (S_refund AND D_highRisk)
~~~

Không được biến biểu thức này thành:

~~~text
P_wrong = (S_pay OR S_refund) AND (D_vip OR D_highRisk)
~~~

Hai biểu thức **khác nhau**: dạng sai cho phép kết hợp chéo `S_pay` với `D_highRisk` hoặc `S_refund` với `D_vip`, dù chính sách ban đầu không định làm vậy.

Dấu ngoặc cho thấy **nhóm điều kiện động nào thuộc nhóm cấu trúc nào**. Trong các ngôn ngữ pointcut có toán tử khác nhau, cần kiểm tra cú pháp và độ ưu tiên của công cụ.

## 12. Static matching không nhất thiết xảy ra trước runtime

Có ba trục phân loại dễ bị trộn lẫn:

1. **Loại thông tin:** cấu trúc không phụ thuộc lần chạy hay ngữ cảnh động của lần chạy?
2. **Thời điểm phân tích:** biên dịch, xử lý bytecode, nạp lớp, cấu hình runtime hay lúc lời gọi đầu tiên xuất hiện?
3. **Cơ chế thực thi:** weaving vào mã, lớp trung gian, interceptor, công cụ instrumentation hoặc cơ chế khác?

Một điều kiện chỉ dùng tên phương thức vẫn có thể được kiểm tra tại runtime bởi một implementation đơn giản. Nó **vẫn là điều kiện tĩnh theo nội dung**. Ngược lại, một điều kiện phụ thuộc giá trị `amount` thường cần dữ liệu tại lần thực thi, dù điểm can thiệp đã được chuẩn bị từ trước.

### 12.1. Weaving lúc biên dịch

Một hệ AOP có thể phân tích thông tin cấu trúc và lựa chọn các join point shadow ngay khi xây dựng mã. Nếu còn phần dynamic matching, mã sinh ra có thể chứa kiểm tra lúc chạy.

### 12.2. Weaving lúc nạp lớp

Một cơ chế khác có thể xác định cấu trúc khi class được nạp và chèn kiểm tra động vào các điểm phù hợp. Kết quả logic tương tự, thời điểm xử lý cấu trúc khác.

### 12.3. Proxy/interceptor lúc chạy

Một cơ chế trung gian có thể kiểm tra chữ ký khi tạo proxy hoặc lần đầu xử lý lời gọi, rồi cache kết quả. Nếu mỗi lần gọi cần xét đối số thực tế, kiểm tra động vẫn phải xảy ra ở những lần thích hợp.

**Không đồng nhất tất cả các cách này:** một loại join point tồn tại trong công cụ weaving mã chưa chắc được proxy interface hỗ trợ.

## 13. Kết quả ba trạng thái và tối ưu hóa điểm can thiệp

Giả sử pointcut có biểu thức:

~~~text
(methodName = "pay") AND (tier = "VIP")
~~~

Với từng phương thức, một bộ phân tích có thể quyết định:

| Vị trí cấu trúc | Phân tích sơ bộ | Điều cần làm lúc chạy |
|---|---|---|
| `status(String)` | Chắc chắn không khớp | Không cần kiểm tra tier |
| `pay(String,int)` | Có thể khớp | Kiểm tra tier từng lần |
| `pay(...)` với pointcut chỉ dựa trên tên | Cấu trúc đủ để khẳng định khớp theo phần lựa chọn | Không cần điều kiện tier |

Tối ưu không chỉ giảm phép so sánh. Ở một số cơ chế weaving, nếu biết một vị trí **không bao giờ** khớp thì có thể không cần sinh điểm chặn ở đó; nếu biết **luôn khớp** thì có thể bỏ phép kiểm tra tương ứng. Khi tồn tại điều kiện động, chi phí được dành cho các ứng viên thực sự có khả năng khớp.

Tuy nhiên, không nên tự khẳng định công cụ nào cũng thực hiện tối ưu giống nhau. Cần xem đặc tả hoặc kiểm chứng nếu hiệu năng là yêu cầu quan trọng.

## 14. Những giới hạn của dynamic matching

### 14.1. Thông tin có sẵn tại join point

Một điều kiện đòi hỏi “số tiền cuối cùng sau toàn bộ nghiệp vụ” thường không thể suy ra từ một join point đặt **trước khi phương thức bắt đầu** nếu số tiền được tính sau đó. Để chọn theo **kết quả** hoặc diễn biến bên trong, phải kiểm tra mô hình có hỗ trợ điều kiện phù hợp tại thời điểm phù hợp hay không, hoặc thay đổi ranh giới quan sát.

### 14.2. Đọc trạng thái biến đổi

Một đối tượng có thể thay đổi giữa thời điểm điều kiện chọn được kiểm tra và thời điểm advice hoàn tất. Vì thế, việc một dynamic pointcut khớp tại thời điểm bắt đầu không bảo đảm trạng thái vẫn như vậy suốt lời gọi. Nếu cần quy tắc nhất quán, phải thiết kế hợp đồng chụp trạng thái, khóa hoặc kiểm tra nghiệp vụ ở nơi sở hữu bất biến.

### 14.3. Tác dụng phụ khi đánh giá predicate

Điều kiện chọn nên dễ dự đoán. Nếu predicate có tác dụng phụ, gọi mạng, ghi cơ sở dữ liệu hoặc ném ngoại lệ, việc **lựa chọn có chạy advice hay không** cũng biến thành nguồn thay đổi trạng thái và lỗi. Nhiều ngôn ngữ pointcut cố ý giới hạn điều có thể kiểm tra. Khi có khả năng đặt điều kiện tùy ý, nên giữ phép đánh giá thuần, rẻ và rõ hợp đồng.

### 14.4. `null`, boxing và kiểu đối số

Trong Java, giá trị `null` và primitive boxing có thể ảnh hưởng đến logic điều kiện lúc chạy. Ở ví dụ Java 17, `amount` được truyền đến proxy như `Integer` do signature nguyên thủy `int`, và việc so sánh dùng pattern `instanceof Integer`. Điều kiện `"VIP".equals(values[0])` an toàn khi đối số đầu có thể `null`.

Một DSL pointcut có thể có ngữ nghĩa so khớp kiểu/generic riêng. Không sao chép cú pháp kiểm tra Java thuần thành cú pháp của mọi công cụ AOP.

## 15. Join point model, pointcut và phạm vi weaving là các tầng khác nhau

Một điều kiện static/dynamic hoàn toàn đúng **vẫn có thể không kích hoạt advice**.

Ví dụ cơ chế AOP đang dùng chỉ hỗ trợ method invocation qua một proxy giao diện. Khi đó:

~~~text
client --> proxy --> target.pay("VIP", 120)
             |
             +-- cơ chế proxy có thể kiểm tra điều kiện

client ------------> target.pay("VIP", 120)
                            |
                            +-- gọi thẳng target, không đi qua proxy
~~~

Hai lời gọi có cùng method và đối số. Nếu đánh giá `S AND D` riêng lẻ, cả hai đều đúng. Nhưng chỉ lời gọi qua proxy được **cơ chế minh họa** chặn.

Để phân tích hiện tượng này, cần phân biệt:

- **Join point model:** loại điểm như call, execution, field access, constructor… được công cụ hỗ trợ.
- **Pointcut:** điểm nào được chọn trong mô hình.
- **Weaving scope:** mã/lớp/vùng nào đã được công cụ xử lý.
- **Runtime path:** đường thực thi có đi qua cơ chế can thiệp và phát sinh điểm tương ứng hay không.

Sửa dynamic predicate không giải quyết được một đường gọi vốn không đi qua proxy hoặc không thuộc phạm vi weaving.

## 16. Những lỗi thường gặp khi nhận diện điều kiện tĩnh

### 16.1. Nhầm “static matching” với static method

Một **instance method** có thể được chọn hoàn toàn từ tên và chữ ký, tức dùng static matching. Một **static method** vẫn có thể chứa điều kiện cần đánh giá lúc chạy khi mô hình có loại join point thích hợp, ví dụ dữ liệu đối số.

Hai khái niệm độc lập.

### 16.2. Nhầm kiểu khai báo với kiểu runtime

Điều kiện “parameter declared type = `Object`” có thể kiểm tra từ chữ ký. Điều kiện “giá trị đối số lúc chạy là một `String`” không thể suy ra chỉ từ chữ ký `Object`.

### 16.3. Nhầm tên method với ý nghĩa nghiệp vụ

Pointcut tĩnh `name startsWith "save"` có thể chọn cả `saveDraft`, `saveDiagnosticData`, hoặc bỏ sót phương thức `persistOrder`. Điều kiện tĩnh đúng cú pháp không đồng nghĩa chính sách bao phủ đúng về ngữ nghĩa.

### 16.4. Nhầm điểm được nhận diện với điểm xảy ra

Phân tích tĩnh có thể xác định một join point shadow, nhưng nhánh mã chứa nó **không nhất thiết được thực thi** trong ca thử. Không thấy advice vì không phát sinh sự kiện là điều khác với static match sai.

## 17. Những lỗi thường gặp khi viết điều kiện động

### 17.1. Giữ kết quả động trong cache quá lâu

Sai lầm:

~~~text
Lần đầu pay("VIP",120) → match = true
Ghi nhớ match=true cho method pay
Lần sau pay("NORMAL",20) → dùng lại match=true
~~~

Phần **tĩnh** có thể cache theo phương thức hoặc vị trí mã khi thông tin cấu trúc phù hợp. Phần **động** phụ thuộc các giá trị từng lần gọi nên không được tái sử dụng như hằng bất biến chỉ vì method giống nhau.

Nếu có memoization cho predicate động, phải định nghĩa khóa, tính bất biến và vòng đời dữ liệu chính xác; đa số trường hợp không nên tự đưa thêm một bộ cache như vậy.

### 17.2. Điều kiện động quá đắt

Đọc cấu hình từ mạng tại mỗi lời gọi, tra cứu dữ liệu từ xa hoặc thực hiện regex phức tạp trên dữ liệu rất dài có thể gây chi phí lớn hơn cả nghiệp vụ được quan sát. Nên thu hẹp ứng viên bằng điều kiện cấu trúc, dùng ngữ cảnh đã có và đo thực tế.

### 17.3. Sai thời điểm lấy ngữ cảnh

Nếu chính sách cần chỉ đo khi tác vụ thực sự hoàn thành, kiểm tra động lúc phương thức **lập lịch tác vụ** trả về không phản ánh kết quả sau cùng. Cần xác định đúng join point của sự kiện cần quan sát.

### 17.4. Dynamic pointcut trở thành quy tắc nghiệp vụ bí mật

Một điều kiện phức tạp điều khiển “cho phép giao dịch hay không” có thể không nên nằm ẩn trong advice/pointcut nếu đó là bất biến cốt lõi của nghiệp vụ. AOP thích hợp với mối quan tâm xuyên suốt có ranh giới rõ; kết quả nghiệp vụ quan trọng cần được biểu diễn và kiểm thử tại thành phần sở hữu chính sách.

## 18. Trường hợp nâng cao: condition theo luồng điều khiển

Một điều kiện chọn kiểu “chỉ chọn join point `charge` nếu nó xảy ra trong chuỗi xử lý `checkout`” thường phụ thuộc **runtime control flow**. Mỗi lời gọi `charge` có thể đến từ `checkout` hoặc `batchSettlement`; cùng chữ ký nhưng ngữ cảnh khác.

Pseudocode độc lập công cụ:

~~~text
S = execution(charge(...))
D = withinControlFlow(checkout(...))

P = S AND D
~~~

Nếu công cụ hỗ trợ điều kiện luồng điều khiển, nó có thể theo dõi phạm vi gọi đang hoạt động, thực thi stack hoặc cơ chế ngữ cảnh tương ứng. Nhưng không phải mọi AOP đều hỗ trợ `withinControlFlow`, và cú pháp trên **chỉ là mô tả**.

**Lưu ý về luồng khác:** Khi `checkout` gửi một tác vụ để chạy về sau ở thread khác, quan hệ “được khởi phát từ checkout” và “đang nằm trên stack/luồng điều khiển của checkout” không tự đồng nghĩa. Cần có định nghĩa rõ về lan truyền ngữ cảnh nếu muốn chọn theo nguyên nhân logic xuyên thread.

## 19. Điều kiện tĩnh/động và thứ tự nhiều aspect

Một join point có thể được chọn bởi nhiều pointcut, trong đó có pointcut tĩnh và pointcut động. Ví dụ:

~~~text
P_metrics = execution(pay(...))
P_audit   = execution(pay(...)) AND tier == "VIP"
~~~

Một lần `pay("VIP",120)` có thể khớp cả hai; `pay("NORMAL",120)` chỉ khớp `P_metrics`.

Việc `P_audit` phụ thuộc động **không tự quyết định thứ tự advice** giữa metrics và audit. Thứ tự/chồng lớp advice là vấn đề khác, có thể ảnh hưởng phép đo thời gian, ngoại lệ và số lần phần gốc được gọi.

Vì thế, khi thiết kế, nên tài liệu hóa riêng:

1. **Điểm nào mỗi aspect chọn?**
2. **Advice nào chạy ở từng điểm?**
3. **Nếu nhiều advice cùng chạy, thứ tự và hợp đồng kết quả thế nào?**

## 20. Kiểm thử đúng hai loại điều kiện

Một bộ kiểm thử nên tách kết quả **chọn về logic** và **quan sát được trong runtime**.

### 20.1. Ma trận kiểm thử logic

Với `S = method pay(String,int) có dấu hiệu Observed`, `D = tier VIP AND amount >= 100`:

| Tình huống | S | D | P |
|---|---|---|---|
| `pay("VIP",120)` | Đúng | Đúng | **Đúng** |
| `pay("VIP",20)` | Đúng | Sai | Sai |
| `pay("NORMAL",150)` | Đúng | Sai | Sai |
| `pay(null,150)` | Đúng | Sai | Sai |
| `status("A-1")` | Sai | Không cần xét | Sai |

Kiểm thử nên xác minh điều kiện cấu trúc áp dụng đúng phương thức/interface và điều kiện động thay đổi theo từng lần gọi.

### 20.2. Ma trận kiểm thử phạm vi can thiệp

Ngay cả khi P đúng, cần kiểm tra:

- Lời gọi đi qua proxy/interceptor khi cơ chế yêu cầu.
- Lớp/method nằm trong weaving scope thực tế.
- Loại join point tương ứng được mô hình hỗ trợ.
- Điều kiện động dùng đúng dữ liệu của **lần thực thi hiện tại**.
- Advice ghi đúng và không làm sai giá trị trả về/ngoại lệ.
- Trường hợp lỗi của phần nghiệp vụ có được xử lý đúng theo loại advice đã chọn.

**Hai tầng kiểm chứng không được trộn:** một unit test cho `dynamicMatch` trả true không chứng minh toàn bộ luồng weaving sẽ kích hoạt advice.

## 21. Quy trình thiết kế pointcut có điều kiện tĩnh và động

1. **Viết mục tiêu chính sách:** “Đo thời gian lời thực thi `pay` với tier VIP và số tiền đạt ngưỡng”.
2. **Xác định join point:** đang chọn method **call**, method **execution**, hay loại khác? Công cụ có hỗ trợ không?
3. **Chỉ ra phần cấu trúc:** tên, chữ ký, package, metadata, loại khai báo nào thể hiện miền ứng viên?
4. **Chỉ ra phần động:** đối số, runtime type, luồng điều khiển hoặc ngữ cảnh nào có thể thay đổi từng lần?
5. **Ghép logic với dấu ngoặc:** đặc biệt khi có nhiều nhóm `OR` và ngoại lệ `NOT`.
6. **Đặt giả định về ngữ cảnh:** nơi đọc đối số, đối tượng/metadata nào, thời điểm nào.
7. **Kiểm tra hiệu năng:** loại sớm các điểm tĩnh chắc chắn sai; tránh predicate động đắt hoặc có tác dụng phụ.
8. **Lập bảng ca dương/âm:** thêm overload, `null`, tên gần giống, dữ liệu biên và nhiều lần gọi liên tiếp.
9. **Xác minh weaving/runtime path:** gọi qua ranh giới đúng, xác nhận advice được kích hoạt chính xác.
10. **Kiểm thử tính đúng đắn của nghiệp vụ:** cùng dữ liệu, logic nghiệp vụ trả kết quả/ngoại lệ đúng; chính sách can thiệp không làm thay đổi số lần xử lý nếu không có chủ đích.

Những bước này giúp pointcut vừa dễ đọc, vừa tránh lỗi “cùng một method nên chắc cùng kết quả khớp” trong hệ thống có dữ liệu động.

## 22. Câu hỏi tự kiểm tra

### Câu 1: Phân loại

Trong các điều kiện sau, điều kiện nào **có thể tĩnh theo thông tin sử dụng**, điều kiện nào **cần dữ liệu runtime**?

A. Tên phương thức khai báo là `calculate`.

B. Đối số thứ nhất ở lần gọi hiện tại lớn hơn 100.

C. Phương thức có annotation khai báo được công cụ nhìn thấy.

D. Receiver thực tế ở lần gọi là một subtype nhất định, trong trường hợp declared type chưa đủ khẳng định.

**Đáp án:** A và C có thể quyết định từ cấu trúc/metadata; B cần dữ liệu lúc chạy; D có thể cần runtime type. Thời điểm công cụ thực hiện phép kiểm tra cấu trúc vẫn phụ thuộc triển khai.

### Câu 2: Cùng một phương thức

Pointcut chọn `pay(String,int)` với tier VIP và amount từ 100. Có ba lời gọi `pay("VIP",120)`, `pay("VIP",30)`, `pay("NORMAL",120)`. Có bao nhiêu lần khớp?

**Đáp án:** một lần, nếu cả ba lời gọi đi tới cùng loại join point hợp lệ. Phần cấu trúc đều đúng, phần dữ liệu chỉ đúng ở lần đầu.

### Câu 3: Cache sai chỗ

Một lập trình viên lưu kết quả `tier == "VIP"` gắn với `Method pay` sau lời gọi đầu. Vì sao đó là lỗi?

**Đáp án:** tier là giá trị **mỗi lần gọi**, không phải metadata cố định của Method. Cache theo method làm nhầm các lần gọi có dữ liệu khác nhau.

### Câu 4: Static pointcut có nghĩa là static method?

**Đáp án:** không. Điều kiện tĩnh nói đến **cách quyết định lựa chọn** dựa trên cấu trúc. Một instance method vẫn có điều kiện chọn tĩnh; một static method vẫn có thể được quan sát theo điều kiện động nếu mô hình hỗ trợ join point tương ứng.

### Câu 5: Đúng pointcut nhưng thiếu advice

Một lần `pay("VIP",120)` thỏa tất cả điều kiện, nhưng lời gọi đi thẳng đến đối tượng đích trong ví dụ proxy. Advice có chắc chạy không?

**Đáp án:** không. **Runtime path** không đi qua proxy, nên cơ chế proxy không quan sát lời gọi. Đây không phải lỗi của phần điều kiện động.

### Câu 6: Ranh giới bất đồng bộ

Một phương thức `submitAsync()` trả về đối tượng đại diện tác vụ. Pointcut chọn method execution và đọc trạng thái “đang chạy” lúc method trả về. Điều đó có đo được trạng thái tác vụ lúc hoàn tất không?

**Đáp án:** không mặc nhiên. Phải xác định join point/sự kiện hoàn tất và cách lấy ngữ cảnh tại thời điểm đó.

### Câu 7: Dấu ngoặc OR

Hai chính sách lựa chọn `pay` khi VIP và `refund` khi highRisk. Vì sao `(pay OR refund) AND (VIP OR highRisk)` có thể sai?

**Đáp án:** biểu thức cho phép hai tổ hợp chéo không được yêu cầu. Phải giữ nhóm tương ứng: `(pay AND VIP) OR (refund AND highRisk)`.

## 23. Ghi nhớ

- **Điều kiện tĩnh** dùng thông tin như loại join point, tên/chữ ký khai báo, phạm vi mã hoặc metadata, có thể quyết định độc lập với giá trị của từng lần xuất hiện.
- **Điều kiện động** dùng ngữ cảnh thực tế: đối số, receiver, runtime type, luồng điều khiển hoặc trạng thái phù hợp; cùng một phương thức có thể khớp ở lần này nhưng không khớp ở lần khác.
- **Static matching khác static method**, và “tĩnh” **không bắt buộc đồng nghĩa** “đánh giá ở compile time”.
- Bộ máy AOP có thể **loại sớm điểm chắc chắn sai**, **chấp nhận điểm luôn đúng** hoặc **đặt kiểm tra động cho điểm có thể khớp**; mức tối ưu cụ thể phụ thuộc cơ chế.
- Cần tách **đúng về biểu thức pointcut** khỏi **được weaving và phát sinh qua đúng đường runtime**.
- Không cache kết quả động như hằng theo method; cần kiểm tra thời điểm, phạm vi, dữ liệu `null` và ngữ cảnh bất đồng bộ.
- Một pointcut tốt nêu rõ cả **miền cấu trúc được chọn** và **điều kiện của từng lần thực thi**, có kiểm thử dương/âm và không làm mất hợp đồng nghiệp vụ.

Câu hỏi quyết định khi nhìn một pointcut là: **“Phần nào biết được trước khi nhìn dữ liệu của lần chạy, phần nào chỉ có thể biết khi join point thực sự xuất hiện, và cơ chế AOP có quan sát được lần xuất hiện đó không?”**.
