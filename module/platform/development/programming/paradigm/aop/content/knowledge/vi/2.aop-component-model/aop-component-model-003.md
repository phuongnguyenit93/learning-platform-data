# Pointcut là điều kiện lựa chọn tập điểm can thiệp trong AOP

> **Mục tiêu:** Hiểu đúng pointcut là **điều kiện lựa chọn các join point** trong mô hình lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP); phân biệt pointcut với join point, advice và aspect; biết xây dựng quy tắc lựa chọn theo cấu trúc hoặc theo ngữ cảnh thực thi; giải thích phạm vi bao phủ, phép kết hợp điều kiện và các lỗi thiết kế thường gặp.

## 1. Câu hỏi mà pointcut trả lời

Trong một chương trình có hàng trăm phương thức và nhiều luồng xử lý, một hành vi xuyên suốt như ghi vết, đo thời gian hay kiểm toán **không nhất thiết được áp dụng ở mọi chỗ**.

Giả sử muốn ghi kiểm toán **chỉ khi** thao tác gửi đơn hàng thuộc nhóm cần theo dõi. Câu hỏi đầu tiên không phải “ghi dòng log nào?”, mà là:

> **Ở những điểm thực thi nào, và khi thỏa những điều kiện nào, hành vi bổ sung được phép tham gia?**

**Pointcut** là thành phần mô tả điều kiện chọn các điểm đó. Hãy hình dung chương trình tạo ra một tập các điểm có khả năng can thiệp, gọi là tập join point ứng viên. Pointcut cung cấp **quy tắc lọc** tập ứng viên, xác định điểm nào được chọn và điểm nào bị loại.

Có thể mô tả bằng ký hiệu khái niệm:

```text
J = tập các join point mà mô hình AOP có thể nhận diện
P = điều kiện pointcut

Matched(P) = { j thuộc J | P(j) đúng }
```

Nếu có một lần thực thi phương thức `submitOrder("VIP")` và điều kiện chọn “lời thực thi submitOrder có đối số VIP” được thỏa mãn, lần thực thi đó thuộc tập điểm được chọn. Lần thực thi `submitOrder("NORMAL")` có cùng tên phương thức nhưng không thỏa điều kiện ở thời điểm chạy nên bị loại.

**Pointcut chọn vị trí/ngữ cảnh; nó không tự định nghĩa hành động cần chạy.** Hành động ở các điểm được chọn thuộc trách nhiệm của *advice*.

## 2. Đặt pointcut vào mô hình thành phần của AOP

| Thành phần | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Concern** | Chương trình đang có trách nhiệm gì? | Xử lý đơn hàng, ghi kiểm toán |
| **Cross-cutting concern** | Trách nhiệm nào cần được áp dụng ở nhiều điểm? | Ghi kiểm toán theo chính sách chung |
| **Join point** | Mô hình AOP có thể can thiệp vào điểm/hoạt động nào? | Một lần thực thi phương thức gửi đơn |
| **Pointcut** | **Điểm nào trong các join point được chọn?** | Thao tác gửi đơn thuộc nhóm VIP |
| **Advice** | Cần làm gì tại những điểm đã chọn? | Ghi sự kiện kiểm toán trước/sau thao tác |
| **Aspect** | Các quy tắc lựa chọn và hành vi liên quan được tổ chức như thế nào? | Khía cạnh kiểm toán thao tác |
| **Weaving** | Hành vi aspect được kết hợp với chương trình ra sao? | Kết nối advice với các join point phù hợp |

Sơ đồ tư duy:

```text
Chương trình nghiệp vụ
       |
       v
Các join point ứng viên
       |
       | pointcut: kiểm tra điều kiện lựa chọn
       v
Các join point được chọn
       |
       | weaving/cơ chế kết hợp hành vi
       v
Advice tham gia vào luồng thực thi
```

Ví dụ có ba join point ứng viên:

```text
j1: thực thi submitOrder("VIP")       → P(j1) = true
j2: thực thi submitOrder("NORMAL")    → P(j2) = false
j3: thực thi cancelOrder("VIP")       → P(j3) = false
```

Một pointcut có thể được mô tả là “chọn thực thi phương thức `submitOrder` có đối số `"VIP"`”. Nó chọn **j1**, không chọn j2 hoặc j3. Advice kiểm toán được kết hợp với j1 theo cơ chế AOP cụ thể.

Đây là **mô tả ngữ nghĩa độc lập công cụ**. Một cơ chế AOP có thể hỗ trợ điểm thực thi phương thức, lời gọi phương thức, truy cập trường, khởi tạo đối tượng hoặc chỉ một tập con trong số đó. Không được giả định mọi loại join point đều được hỗ trợ.

## 3. Join point khác pointcut ở đâu?

Hai khái niệm này dễ bị nhầm vì đều nhắc đến “điểm”.

**Join point** là **điểm có khả năng can thiệp**, chẳng hạn một lần thực thi phương thức hoặc một lời gọi cụ thể. **Pointcut** là **quy tắc chọn** một hoặc nhiều join point phù hợp.

So sánh bằng hình ảnh bộ lọc:

- Join point tương tự một bản ghi đầu vào cần được kiểm tra.
- Pointcut tương tự một điều kiện lọc bản ghi.
- Tập join point phù hợp là **kết quả** của việc áp dụng điều kiện.
- Advice là hành vi chạy tại kết quả đã chọn, không phải điều kiện lọc.

Về mặt logic, cùng một pointcut có thể chọn nhiều join point; nhiều pointcut có thể chọn cùng một join point; và một pointcut cũng có thể không chọn được điểm nào trong lần chạy hiện tại.

**Không nên hiểu pointcut là “một điểm duy nhất”** chỉ vì tên có chữ *point*. Nó thường là biểu thức hoặc định nghĩa điều kiện đại diện cho **một tập**.

### 3.1. Một vị trí mã và nhiều lần xuất hiện động

Xét phương thức:

```java
void submitOrder(String tier) {
    System.out.println("processing " + tier);
}
```

Một điểm thực thi được mô tả ở mức cấu trúc có thể có nhiều **lần xuất hiện khi chạy**:

```text
Lần 1: submitOrder("VIP")
Lần 2: submitOrder("NORMAL")
Lần 3: submitOrder("VIP")
```

Nếu pointcut chỉ kiểm tra tên/phương thức, cả ba lần đều phù hợp. Nếu điều kiện đồng thời kiểm tra đối số bằng `"VIP"`, chỉ lần 1 và lần 3 phù hợp. Vì vậy, phải phân biệt **mẫu vị trí mã** với **ngữ cảnh của từng lần thực thi**.

## 4. Điều kiện pointcut thường xét những gì?

Ngôn ngữ/cơ chế AOP có thể cung cấp nhiều cách mô tả điều kiện. Bảng dưới đây diễn đạt **khái niệm**, không khẳng định một cú pháp chung cho tất cả công cụ.

| Nhóm điều kiện | Điều được kiểm tra | Tình huống |
|---|---|---|
| **Loại join point** | Thực thi phương thức, gọi phương thức, truy cập trường… nếu được hỗ trợ | Chỉ quan sát lúc thực thi phương thức |
| **Chữ ký phương thức** | Tên, kiểu trả về, kiểu tham số, khả năng hiển thị… theo phạm vi công cụ | Chọn các thao tác `submit...` |
| **Kiểu hoặc phạm vi khai báo** | Lớp, giao diện, gói hoặc nhóm thành phần | Chỉ thao tác trong mô-đun đơn hàng |
| **Metadata/annotation** | Phương thức, kiểu hoặc phần tử có một dấu hiệu khai báo | Chọn phương thức mang dấu hiệu cần kiểm toán |
| **Đối tượng nhận lời gọi** | Đặc tính đối tượng thực thi/đích, nếu được hỗ trợ | Chọn thành phần có vai trò nhất định |
| **Đối số thực tế** | Giá trị hoặc kiểu dữ liệu đối số lúc chạy | Chỉ xử lý đơn thuộc nhóm VIP |
| **Luồng điều khiển** | Join point xảy ra trong ngữ cảnh lời gọi nhất định, nếu được hỗ trợ | Chỉ khi đi qua một thao tác cấp cao |
| **Điều kiện ngữ cảnh khác** | Trạng thái hoặc ngữ cảnh có sẵn tại điểm can thiệp | Chỉ khi một điều kiện cho phép được thỏa mãn |

Cần phân biệt “một cơ chế nhận diện được phương thức” với “cơ chế có thể kiểm tra điều kiện bất kỳ trong thân phương thức”. **Pointcut không mặc nhiên đọc được mọi trạng thái nội bộ hay mọi biến cục bộ**; phạm vi phụ thuộc loại join point và thông tin mà mô hình cung cấp.

## 5. Điều kiện theo cấu trúc và điều kiện tại thời điểm chạy

Đây là sự phân chia rất hữu ích khi thiết kế và đánh giá chi phí.

### 5.1. Phần có thể xác định từ cấu trúc

Một điều kiện như “thực thi phương thức tên `submitOrder` của nhóm lớp được chỉ định” có thể được xác định dựa trên tên, kiểu và mô tả chương trình, khi cơ chế có đủ metadata.

Ví dụ:

```text
Tên phương thức = submitOrder
AND lớp khai báo thuộc mô-đun order
```

Điều kiện này thường **không phụ thuộc giá trị đối số của từng lần gọi**. Một lần xác định cấu trúc có thể giúp thu hẹp danh sách điểm cần xử lý.

Tuy nhiên, thời điểm xác định (lúc biên dịch, nạp lớp hoặc chạy) phụ thuộc cơ chế weaving; không nên kết luận tất cả điều kiện cấu trúc luôn được quyết định tại thời điểm biên dịch.

### 5.2. Phần phụ thuộc ngữ cảnh động

Một điều kiện khác có thể phụ thuộc đối số thực tế:

```text
Giá trị đối số đầu tiên = "VIP"
```

Ngay cả khi đã biết đúng phương thức `submitOrder(String)`, điều kiện này có thể cần kiểm tra **mỗi lần thực thi** vì mỗi lần truyền một giá trị khác nhau.

Kết hợp:

```text
P = thực thi phương thức submitOrder(String)
    AND giá trị tham số thứ nhất = "VIP"
```

Nếu đầu vào là `"NORMAL"`, phần cấu trúc đúng nhưng toàn bộ P sai.

**Điều kiện cấu trúc** và **điều kiện động** là hai loại kiểm tra có chi phí, khả năng bao phủ và giới hạn khác nhau. Nhiều cơ chế tối ưu bằng cách loại trước ứng viên không thể khớp theo cấu trúc rồi mới đánh giá phần động khi cần.

## 6. Biểu thức logic: AND, OR, NOT

Pointcut thường cần biểu diễn điều kiện phức hợp. Các phép logic phổ biến ở cấp khái niệm:

- **AND (và):** mọi điều kiện phải đúng; thường **thu hẹp** tập điểm.
- **OR (hoặc):** ít nhất một điều kiện đúng; thường **mở rộng** tập điểm.
- **NOT (phủ định):** loại các điểm thỏa điều kiện bị phủ định, trong **miền join point mà cơ chế xét**.

Giả sử:

```text
A: join point thuộc thao tác submitOrder
B: đối số tier bằng "VIP"
C: join point thuộc thao tác nội bộ cần loại trừ
```

Ta có:

```text
P = (A AND B) AND NOT C
```

Bảng quyết định:

| A | B | C | P = A ∧ B ∧ ¬C |
|---|---|---|---|
| Đúng | Đúng | Sai | **Đúng** |
| Đúng | Đúng | Đúng | Sai |
| Đúng | Sai | Sai | Sai |
| Sai | Đúng | Sai | Sai |
| Sai | Sai | Sai | Sai |

Dấu ngoặc thể hiện nhóm điều kiện. Trong công cụ có ngôn ngữ pointcut cụ thể, phải kiểm tra **cú pháp, độ ưu tiên toán tử và khả năng hỗ trợ phép phủ định**; sơ đồ trên chỉ nói về logic.

### 6.1. Đọc biểu thức như phép toán trên tập hợp

Với tập các join point ứng viên J:

```text
Matched(A AND B) = Matched(A) ∩ Matched(B)
Matched(A OR B)  = Matched(A) ∪ Matched(B)
Matched(NOT A)   = J \ Matched(A)
```

Cách đọc này giúp đánh giá một pointcut lớn có quá rộng hoặc quá hẹp không. Ví dụ `A OR B` có thể vô tình đưa thêm các thao tác chỉ thỏa B nhưng không có ý nghĩa nghiệp vụ mong đợi; `A AND B` có thể bỏ sót hành vi cần quan sát nếu B quá hạn chế.

## 7. Ví dụ Java 17: minh họa điểm chọn bằng điều kiện rõ ràng

Ví dụ sau dùng Java thuần để mô phỏng quá trình **lọc điểm thực thi** và **bao hành vi trước/sau**. Nó **không phải một ngôn ngữ pointcut AOP hoàn chỉnh**. Trong ví dụ, `Proxy` chỉ chặn các lời gọi được thực hiện **qua đối tượng đại diện cho giao diện**; lớp triển khai gọi trực tiếp sẽ đi đường khác.

Chúng ta chọn đúng những lời gọi thỏa **cả ba điều kiện**:

1. Phương thức của giao diện có dấu hiệu `@Observed`.
2. Tên phương thức bằng `submit`.
3. Đối số thứ nhất đúng bằng chuỗi `"VIP"`.

Lưu tệp `PointcutSelectionDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class PointcutSelectionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observed {}

    interface Orders {
        @Observed
        void submit(String tier);

        void cancel(String tier);
    }

    static class OrdersImpl implements Orders {
        @Override
        public void submit(String tier) {
            System.out.println("submit " + tier);
        }

        @Override
        public void cancel(String tier) {
            System.out.println("cancel " + tier);
        }
    }

    // Quy tắc chọn, mô phỏng vai trò của một pointcut.
    static boolean matches(Method method, Object[] args) {
        boolean structural =
                method.isAnnotationPresent(Observed.class)
                && method.getName().equals("submit");

        boolean runtime =
                args != null
                && args.length == 1
                && "VIP".equals(args[0]);

        return structural && runtime;
    }

    static Object invokeTarget(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException exception) {
            throw exception.getCause();
        }
    }

    public static void main(String[] args) {
        Orders target = new OrdersImpl();

        Orders observed = (Orders) Proxy.newProxyInstance(
                Orders.class.getClassLoader(),
                new Class<?>[] {Orders.class},
                (proxy, method, values) -> {
                    if (!matches(method, values)) {
                        return invokeTarget(method, target, values);
                    }

                    System.out.println("[audit] before " + method.getName());
                    try {
                        return invokeTarget(method, target, values);
                    } finally {
                        System.out.println("[audit] after " + method.getName());
                    }
                }
        );

        observed.submit("VIP");
        observed.submit("NORMAL");
        observed.cancel("VIP");

        // Gọi trực tiếp: không đi qua proxy ở ví dụ này.
        target.submit("VIP");
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac PointcutSelectionDemo.java
java PointcutSelectionDemo
```

Kết quả stdout chính xác:

```text
[audit] before submit
submit VIP
[audit] after submit
submit NORMAL
cancel VIP
submit VIP
```

Giải thích từng lời gọi:

| Lời gọi | Dấu hiệu và tên | Đối số VIP | Kết quả chọn |
|---|---|---|---|
| `observed.submit("VIP")` | Đúng | Đúng | Chọn, chạy phần audit |
| `observed.submit("NORMAL")` | Đúng | Sai | Không chọn |
| `observed.cancel("VIP")` | Sai | Đúng | Không chọn |
| `target.submit("VIP")` | Nếu kiểm tra thuần túy thì đúng | Đúng | **Không được cơ chế proxy này chặn** |

**Điểm cần phân biệt:** `matches(...)` mô phỏng **điều kiện pointcut**, còn những câu `System.out.println("[audit] ...")` mô phỏng **hành vi advice**. `Proxy.newProxyInstance(...)` là phương tiện Java được chọn cho ví dụ để dẫn lời gọi qua bộ lọc; đây không phải bằng chứng rằng AOP nói chung bị giới hạn ở proxy.

Phần `method.isAnnotationPresent(Observed.class)` đang kiểm tra **metadata trên phương thức của giao diện**, vì `Method` mà proxy giao diện nhận được mô tả phương thức giao diện. Một công cụ khác có thể chọn quy tắc dựa trên khai báo của lớp triển khai; hai cách này không đương nhiên cho cùng kết quả. `@Retention(RUNTIME)` làm annotation xuất hiện khi dùng reflection lúc chạy.

Phần `invokeTarget` giải gói `InvocationTargetException` để truyền nguyên nhân lỗi từ phương thức đích; `finally` ghi “after” dù phương thức đích kết thúc bình thường hay ném lỗi. “after” ở đây nghĩa là **đã rời lời gọi được bao**, không có nghĩa thao tác thành công. Ví dụ dùng `void` để giữ trọng tâm tại điều kiện chọn; với phương thức trả kết quả, cơ chế bao phải bảo toàn cả giá trị trả về.

### 7.1. Điều ví dụ chứng minh và điều nó không chứng minh

Ví dụ chứng minh rằng một **điều kiện chọn** có thể tách riêng khỏi **hành động bổ sung**, có thể kết hợp thông tin tĩnh với thông tin động, và có thể bị giới hạn bởi **đường đi mà cơ chế can thiệp quan sát được**.

Ví dụ **không** chứng minh việc weaving ở mọi loại join point; không chọn truy cập trường, khởi tạo đối tượng hay mọi lời gọi tự diễn ra bên trong lớp; không tự động áp dụng cho `target` gốc. Một hệ AOP thực sự cần định nghĩa rõ cơ chế weaving và tập join point hỗ trợ.

## 8. Pointcut và advice: cùng liên quan join point nhưng khác trách nhiệm

Xét yêu cầu:

> Khi thực thi thao tác gửi đơn VIP, ghi thời điểm bắt đầu và kết thúc.

Có hai phần độc lập:

```text
Pointcut: chọn thực thi submitOrder với tier = VIP
Advice:   ghi sự kiện "begin" và "end"
```

Nếu sau này thay định dạng ghi sự kiện từ văn bản sang cấu trúc dữ liệu, quy tắc chọn join point **có thể không đổi**. Nếu mở rộng sang mọi đơn hàng thay vì chỉ VIP, phần hành vi audit **có thể không đổi**. Đó là lợi ích của việc phân biệt hai trách nhiệm.

Một pointcut có thể được tái sử dụng bởi nhiều advice; một advice có thể được liên kết với nhiều điều kiện chọn, tùy mô hình tổ chức. **Aspect** đóng vai trò mô-đun quản lý các định nghĩa liên quan. Mối quan hệ này giúp giảm scattering của việc áp dụng chính sách và tangling của mã nghiệp vụ, nhưng chỉ khi chính sách thực sự là mối quan tâm xuyên suốt.

### 8.1. Pointcut không quyết định việc tiếp tục xử lý

Pointcut trả lời **“có khớp hay không?”**. Nó không tự trả lời **“chạy trước hay sau?”**, **“có thực hiện phần gốc hay không?”** hoặc **“xử lý ngoại lệ thế nào?”**.

Những quyết định đó thuộc semantics của advice và cơ chế kết hợp hành vi. Với một loại advice bao quanh, hành vi có thể gọi phần thực thi gốc qua thao tác tương tự `proceed`; việc bỏ qua hoặc gọi nhiều lần phần gốc có thể thay đổi đáng kể kết quả nghiệp vụ.

Vì thế không nên gán cho pointcut các chức năng như bắt lỗi, thử lại, điều khiển transaction hay thay đổi giá trị trả về. Pointcut chỉ **chọn nơi** một hành vi như vậy có thể áp dụng.

## 9. Pointcut tĩnh, động và thời điểm đánh giá

Nói “điều kiện được kiểm tra khi nào?” đòi hỏi nêu đúng phạm vi:

- **Điều kiện dựa trên cấu trúc** thường có thể được xác định từ mô tả lớp/phương thức. Công cụ có thể xử lý sớm trong quá trình weaving hoặc khi hệ thống tạo cơ chế can thiệp.
- **Điều kiện dựa trên dữ liệu động** có thể cần kiểm tra ở từng lần join point xuất hiện, sau khi biết đối tượng, đối số hoặc ngữ cảnh tương ứng.
- **Điều kiện phụ thuộc luồng điều khiển** (nếu hỗ trợ) có thể cần theo dõi ngữ cảnh lời gọi hoặc trạng thái thực thi bổ sung.

Trong một số mô hình AOP, pointcut trộn cả phần tĩnh và động. Tối ưu hợp lý là thu hẹp phạm vi theo cấu trúc rồi mới kiểm tra điều kiện động ở những chỗ có thể khớp. Nhưng **cú pháp và thời điểm đánh giá chính xác phụ thuộc triển khai**.

Điều này ảnh hưởng đến hiệu năng. Một biểu thức chỉ xét tên phương thức không có cùng chi phí với biểu thức cần kiểm tra trạng thái phức tạp ở mọi lần thực thi. Với hệ thống tần suất lời gọi cao, cần đo đạc số điểm khớp, chi phí kiểm tra và chi phí advice riêng rẽ.

## 10. Các bẫy thường gặp khi viết điều kiện chọn

### 10.1. Chọn quá rộng (*overmatching*)

Quy tắc “mọi phương thức có tên bắt đầu `save`” có thể bao gồm thao tác nội bộ, thao tác thử nghiệm hoặc nhóm dữ liệu khác. Một advice ghi chi tiết dữ liệu có thể vô tình thu thập quá nhiều thông tin hoặc áp dụng sai chính sách.

**Cách xử lý:** xác định mục đích của chính sách rồi giới hạn theo **ranh giới có ý nghĩa** (nhóm thành phần, loại join point, metadata rõ ràng), kết hợp phép loại trừ nếu phù hợp; kiểm tra các điểm khớp ngoài dự kiến.

### 10.2. Chọn quá hẹp (*undermatching*)

Quy tắc “chỉ phương thức tên `submitOrder`” sẽ không bao phủ thao tác cùng ý nghĩa nhưng tên `placeOrder`. Khi mã được refactor, pointcut có thể không còn khớp như mong muốn.

**Cách xử lý:** ưu tiên hợp đồng/metadata ổn định khi thích hợp; kiểm thử những thao tác **phải** khớp, và rà soát chính sách khi thay tên hoặc tách chức năng.

### 10.3. Nhầm lời gọi (*call*) với thực thi (*execution*)

Ở mô hình có phân biệt hai loại join point:

- **Call:** điểm một vị trí mã tạo lời gọi đến phương thức.
- **Execution:** điểm phương thức đích thực sự bắt đầu thực thi.

Một phương thức có thể được gọi từ nhiều vị trí, nên lựa chọn theo call site có ý nghĩa khác chọn theo execution. Không phải mọi cơ chế AOP đều cung cấp cả hai loại; với cơ chế giới hạn ở lời gọi qua một lớp trung gian, phạm vi chặn còn phụ thuộc đường đi lời gọi.

Đừng diễn giải hai loại này như từ đồng nghĩa khi cần chứng minh độ bao phủ.

### 10.4. Giả định mọi lời gọi nội bộ đều được chặn

Một phương thức trong đối tượng có thể gọi phương thức khác của **chính đối tượng đó**. Nếu cơ chế can thiệp chỉ hoạt động khi lời gọi đi qua proxy bên ngoài, đường gọi nội bộ có thể không đi qua proxy. Ngược lại, một cơ chế weaving ở cấp mã có thể hỗ trợ ngữ nghĩa khác.

**Cách xử lý:** kiểm tra đường đi cụ thể, đối tượng/giao diện qua đó lời gọi phát sinh, và các join point thực sự được cơ chế hỗ trợ. Không suy ra phạm vi AOP từ chỉ một tên pointcut.

### 10.5. Nhầm chữ ký khai báo với giá trị thực tế

Ví dụ `submitOrder(String tier)` có kiểu tham số luôn là `String`, nhưng đối số thực tế có thể là `"VIP"`, `"NORMAL"` hoặc `null`. Điều kiện **kiểu đối số** không tự tương đương điều kiện **giá trị đối số**.

Tương tự, metadata trên phương thức giao diện có thể khác metadata trên phương thức của lớp triển khai. Luôn chỉ rõ nơi metadata được đọc và thời điểm ngữ cảnh được kiểm tra.

### 10.6. Điều kiện chọn gây tác dụng phụ

Về mặt thiết kế, một điều kiện pointcut nên dễ dự đoán, diễn tả chính sách lựa chọn và hạn chế tác dụng phụ. Nếu điều kiện vừa truy vấn mạng, vừa thay đổi trạng thái hoặc ném ngoại lệ, việc đánh giá pointcut có thể làm chương trình khó giải thích, khó kiểm thử và gây chi phí đáng kể.

Nếu có điều kiện động cần dữ liệu phức tạp, cân nhắc điểm áp dụng ổn định hơn, cung cấp metadata phù hợp hoặc tổ chức kiểm tra rõ ràng bên trong thành phần chính sách.

### 10.7. Một điểm khớp nhiều aspect

Một join point có thể thỏa nhiều pointcut của các aspect khác nhau. Pointcut **không tự quyết định thứ tự** các advice. Ví dụ có advice đo thời gian và advice kiểm toán; kết quả đo có thể bao gồm hoặc loại trừ chi phí ghi kiểm toán tùy thứ tự bao quanh.

Cần xác định thứ tự bằng hợp đồng hoặc cấu hình của cơ chế đang dùng, và có kiểm thử chứng minh đường chạy khi thứ tự thực sự ảnh hưởng đến ngữ nghĩa.

## 11. Thiết kế pointcut có thể kiểm chứng

Một pointcut hữu ích cần có **tên thể hiện ý định** và có phạm vi giải thích được bằng ví dụ cụ thể. Thay vì đặt tên “allMethods”, có thể chọn tên khái niệm như “các thao tác hoàn tất đơn hàng cần kiểm toán”. Tên là tài liệu cho chính sách, còn biểu thức phải thực sự khớp với tài liệu đó.

Quy trình thực hành:

1. **Viết yêu cầu bằng ngôn ngữ nghiệp vụ/kỹ thuật:** “Ghi kiểm toán cho thao tác gửi đơn hàng VIP”. Làm rõ mục tiêu, điểm bắt đầu/kết thúc, các trường hợp ngoại lệ.
2. **Chọn loại join point:** cần quan sát lúc thực thi phương thức, tại nơi gọi hay một sự kiện khác? Xác minh cơ chế hỗ trợ loại đó.
3. **Chọn điều kiện cấu trúc:** phạm vi lớp/giao diện, tên hoặc metadata biểu đạt chủ đích.
4. **Bổ sung điều kiện động nếu cần:** đối số, đối tượng, ngữ cảnh có thể thay đổi từng lần chạy.
5. **Xác định ngoại lệ lựa chọn:** thao tác nội bộ, các đối tượng/loại dữ liệu không thuộc chính sách.
6. **Lập bảng tình huống khớp/không khớp:** ưu tiên cả nhánh biên, `null`, lỗi và luồng nội bộ.
7. **Kiểm tra bằng hành vi quan sát được:** advice chạy tại điểm nào, bao nhiêu lần, theo thứ tự nào; xác nhận mã nghiệp vụ vẫn giữ đúng kết quả.
8. **Rà lại khi refactor:** đổi tên, đổi phân tầng hoặc chuyển lời gọi qua ranh giới khác có thể làm tập join point được chọn thay đổi.

### 11.1. Bảng kiểm thử lựa chọn

Với pointcut minh họa ở phần 7, lập bảng mong đợi trước khi chạy:

| Trường hợp | Dự kiến |
|---|---|
| `observed.submit("VIP")` | Khớp |
| `observed.submit("NORMAL")` | Không khớp |
| `observed.submit(null)` | Không khớp |
| `observed.cancel("VIP")` | Không khớp |
| `target.submit("VIP")` qua tham chiếu gốc | Không được proxy can thiệp, dù bản thân điều kiện dữ liệu có thể đúng |

Đây là hai tầng kiểm chứng khác nhau:

- **Kiểm chứng điều kiện:** với một join point/ngữ cảnh được đưa vào bộ lọc, `P(j)` trả về đúng hay sai?
- **Kiểm chứng phạm vi can thiệp:** join point đó có **thực sự được cơ chế AOP nhìn thấy/bao phủ** khi chạy không?

Một bộ kiểm thử tốt kiểm tra cả hai tầng; chỉ kiểm tra logic biểu thức nhưng bỏ qua đường gọi có thể tạo cảm giác bao phủ sai.

### 11.2. Quan sát được vì sao một điểm được chọn

Khi một pointcut phức tạp khớp bất ngờ, cần cách xác định **phần nào của biểu thức đúng**, loại join point đã xét, đối tượng/ngữ cảnh nào được dùng và advice nào tham gia. Điều này có thể thực hiện bằng chẩn đoán của công cụ hoặc bằng phép thử nhỏ độc lập với nghiệp vụ.

Mục tiêu của khả năng chẩn đoán là giải thích được: “lần thực thi nào được chọn, theo điều kiện gì, dẫn tới hành vi bổ sung nào?”. Pointcut càng rộng và càng động, nhu cầu kiểm chứng càng cao.

## 12. Tình huống nâng cao cần cân nhắc

### 12.1. Điều kiện theo luồng điều khiển

Có nhu cầu chọn “mọi thao tác ghi dữ liệu xảy ra **bên trong** quy trình xử lý đơn hàng”. Đây không đơn thuần là điều kiện tên lớp hoặc phương thức: một thao tác ghi dữ liệu chỉ phù hợp khi xuất hiện trong ngữ cảnh lời gọi được chỉ định.

Nếu cơ chế hỗ trợ pointcut theo **control flow**, chính sách này có thể biểu diễn được. Nhưng khả năng hỗ trợ, chi phí theo dõi ngữ cảnh, ranh giới giữa luồng đồng bộ và tác vụ chạy ở luồng khác đều phải xác minh. Không nên đồng nhất “được gọi sau” với “nằm trong cùng luồng điều khiển”.

### 12.2. Kết hợp pointcut bằng các định nghĩa tái sử dụng

Khi nhiều chính sách dùng chung một miền hoạt động, có thể đặt tên những tập con ở mức ý định:

```text
P_orderOperation = join point thuộc thao tác đơn hàng
P_observed       = thao tác được đánh dấu cần quan sát
P_vip            = đối số tier là VIP

P_auditVIP = P_orderOperation AND P_observed AND P_vip
```

Phân rã như vậy giúp kiểm tra từng phần riêng rẽ. Tuy nhiên, nếu định nghĩa trung gian quá nhiều hoặc dùng điều kiện tên khó hiểu, hệ thống vẫn có thể trở nên khó lần dấu. Dùng tên mô tả ý nghĩa, có bảng trường hợp và chỉ trừu tượng hóa khi phần điều kiện thực sự được chia sẻ.

### 12.3. Pointcut và thay đổi phiên bản mã

Một pointcut phụ thuộc tên/signature có thể thay đổi tập khớp khi phương thức được đổi tên, overload, chuyển sang giao diện khác hoặc thay đổi khả năng hiển thị. Một pointcut dựa trên metadata có thể khác đi khi một annotation được đặt tại lớp khai báo khác.

Do đó, khi thay đổi API nội bộ, cần coi tập điểm được pointcut chọn như một phần hợp đồng tích hợp, đặc biệt với chính sách kiểm toán, truy cập hay tác vụ có ảnh hưởng lớn đến tính đúng đắn.

### 12.4. Đối số, dữ liệu nhạy cảm và an toàn của chính sách

Điều kiện theo đối số không đồng nghĩa được phép ghi toàn bộ đối số ra log. Pointcut có thể chọn đúng, nhưng advice phải tuân thủ chính sách xử lý dữ liệu. Nếu kết quả kiểm tra quyền phụ thuộc thông tin nhạy cảm hoặc trạng thái thay đổi nhanh, cần đặt kiểm tra đúng ranh giới đáng tin cậy và tránh để bộ chọn tạo ra sự bảo đảm an toàn giả.

Không nên dùng tên phương thức hoặc một pointcut dễ bỏ sót như **bằng chứng duy nhất** rằng một yêu cầu kiểm soát bắt buộc đã được áp dụng cho mọi đường đi. Các đường gọi bị loại trừ và phạm vi join point phải được kiểm chứng độc lập.

### 12.5. Lời gọi bất đồng bộ và ý nghĩa của thời điểm can thiệp

Một phương thức có thể trả về ngay một đối tượng đại diện cho công việc chưa hoàn thành. Pointcut ở **thực thi phương thức tạo tác vụ** chọn thời điểm tạo/lập lịch, không tự động có nghĩa chọn thời điểm hoàn tất công việc. Tùy mục tiêu, có thể cần một join point/sự kiện khác hoặc theo dõi vòng đời tác vụ.

Pointcut chỉ chọn một tập điểm đã mô tả. Nó không tự mở rộng ý nghĩa “đã xử lý xong” sang toàn bộ công việc bất đồng bộ nếu điểm được chọn mới phản ánh phần bắt đầu.

## 13. Bài tập vận dụng

**Bài 1.** Một hệ thống có các lần thực thi:

```text
createOrder("VIP")
createOrder("NORMAL")
cancelOrder("VIP")
createOrder("VIP")
```

Điều kiện `P = tên phương thức là createOrder AND đối số thứ nhất bằng "VIP"` chọn những lần nào?

**Đáp án:** lần thứ nhất và thứ tư. Có hai lần xuất hiện động phù hợp dù cùng một phương thức khai báo.

**Bài 2.** Một advice đo thời gian đang chạy trên cả `healthCheck()`, `calculateTotal()` và `generateReport()`, nhưng yêu cầu chỉ đo tác vụ có ảnh hưởng lớn đến người dùng. Cần sửa pointcut hay sửa advice?

**Gợi ý:** trước tiên làm rõ tập thao tác cần quan sát và **điều chỉnh pointcut** cho đúng phạm vi; hành vi đo thời gian trong advice có thể không cần đổi. Việc đưa hay không đưa `healthCheck()` vào tập chọn là quyết định phạm vi chính sách, không phải thuật toán tính thời lượng.

**Bài 3.** Pointcut dự kiến khớp `submit("VIP")`, kiểm tra riêng hàm `matches` cho ra `true`, nhưng lúc chạy advice không xuất hiện. Nêu hai nguyên nhân có thể kiểm tra.

**Đáp án gợi ý:** (1) lời gọi không đi qua **cơ chế can thiệp** (ví dụ đi trực tiếp đến đối tượng đích trong ví dụ proxy); (2) join point/định nghĩa metadata thực tế mà công cụ xét không giống đối tượng `Method` dùng trong phép thử. Cũng cần xét giới hạn loại join point và cấu hình weaving.

**Bài 4.** Vì sao `P = A OR B` có thể rủi ro hơn `P = A AND B` nếu advice thực hiện thao tác có tác dụng phụ?

**Gợi ý:** OR mở rộng tập khớp, có thể áp dụng hành vi vào điểm chỉ thuộc một nhóm; AND thu hẹp tập khớp và có nguy cơ bỏ sót điểm cần xử lý. Không có toán tử “an toàn hơn” trong mọi trường hợp; phải khớp với hợp đồng nghiệp vụ và kiểm thử cả các điểm nên chọn lẫn điểm phải loại.

## 14. Checklist ghi nhớ

- **Join point**: một điểm mà mô hình AOP nhận diện và có thể can thiệp.
- **Pointcut**: **điều kiện/bộ lọc chọn một tập join point**; có thể khớp không, một hoặc nhiều điểm.
- **Advice**: hành vi bổ sung tại các điểm được chọn; không phải biểu thức lựa chọn.
- **Aspect**: mô-đun hóa chính sách và hành vi liên quan; **weaving** là bước kết hợp vào chương trình.
- Điều kiện có thể dựa trên **cấu trúc** hoặc **ngữ cảnh động**, và dùng **AND/OR/NOT** để kết hợp.
- Tập điểm được chọn chịu ảnh hưởng bởi **loại join point, ranh giới can thiệp, thời điểm đánh giá và khả năng hỗ trợ thực tế**.
- Chất lượng pointcut được đo bằng việc nó **chọn đúng điểm, không bỏ sót, không chọn thừa và kiểm chứng được**.

Khi nhìn thấy một pointcut, hãy luôn hỏi: **“Quy tắc này chọn những join point nào, dựa vào thông tin gì, tại thời điểm nào, và cơ chế AOP có nhìn thấy tất cả những điểm đó không?”** Trả lời được bốn câu này mới hiểu đầy đủ vai trò “điều kiện lựa chọn tập điểm can thiệp” của pointcut.
