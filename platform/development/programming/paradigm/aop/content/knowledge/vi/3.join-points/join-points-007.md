# Thông tin tĩnh và ngữ cảnh động của một join point trong AOP

## 1. Vấn đề cốt lõi: một điểm được mô tả trước, nhiều lần xuất hiện khi chạy

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, một **join point** là điểm trong mô hình thực thi mà cơ chế AOP có thể quan sát hoặc can thiệp. Ví dụ: một lần thực thi phương thức, một vị trí gọi phương thức, hoặc một lần đọc trường dữ liệu, nếu mô hình join point của công cụ hỗ trợ loại đó.

Khi phân tích một join point, cần tách hai câu hỏi:

1. **Thông tin tĩnh (static information):** đây là loại điểm nào, gắn với thành phần mã nào, chữ ký nào, vị trí mã nào? Những đặc điểm này có thể xác định từ cấu trúc chương trình và mô hình weaving trước khi biết dữ liệu cụ thể của từng lần chạy.
2. **Ngữ cảnh động (dynamic context):** lần thực thi hiện tại đang xảy ra trên đối tượng nào, với tham số gì, trong điều kiện nào, kết thúc bằng kết quả hay ngoại lệ nào? Những thông tin này chỉ có thể biết tại thời điểm thích hợp của một lần chạy cụ thể.

Ví dụ, cùng một phương thức:

```java
String transfer(String account, long amount) {
    return account + ":" + amount;
}
```

Đây là **đoạn minh họa** trong một kiểu Java, không phải chương trình độc lập. Chữ ký `transfer(String,long):String` không đổi giữa các lần gọi. Nhưng `transfer("A", 100)` và `transfer("B", 500)` có tham số và kết quả khác nhau.

Nếu một aspect ghi log phương thức, thông tin tĩnh giúp xác định **đang áp dụng vào phương thức nào**; ngữ cảnh động giúp xác định **lần gọi nào**, **dữ liệu nào**, và **đã xảy ra điều gì**.

**Mấu chốt:** tĩnh không có nghĩa “không bao giờ thay đổi trong suốt đời phần mềm”; nó nghĩa là đặc điểm của **vị trí/kiểu join point trong phiên bản mã đang xét**, tương đối độc lập với từng lần xuất hiện động. Khi thay mã, nạp lớp khác hoặc thay cấu hình weaving, tập thông tin tĩnh có thể thay đổi.

## 2. Khái niệm join-point shadow và lần xuất hiện động

Trong các mô hình AOP có phân biệt hai tầng, **join-point shadow** là vị trí hoặc cấu trúc mã tĩnh *có thể phát sinh* một hay nhiều join point khi chạy. Mỗi lần luồng điều khiển thực sự đi qua vị trí đó có thể tạo ra **một lần xuất hiện động (dynamic occurrence)**.

Minh họa:

```java
for (int i = 1; i <= 3; i++) {
    gateway.pay("ORDER-" + i, i * 100);
}
```

Đây là mã minh họa, trong đó `gateway` giả định là đối tượng có phương thức `pay`. Lệnh gọi `gateway.pay(...)` xuất hiện **một vị trí tĩnh** nhưng vòng lặp tạo ra **ba lần gọi động**:

```text
Vị trí tĩnh: gateway.pay(String, int)
   |
   +-- Lần 1: pay("ORDER-1", 100)
   +-- Lần 2: pay("ORDER-2", 200)
   +-- Lần 3: pay("ORDER-3", 300)
```

Tùy mô hình, vị trí trên có thể đại diện một *method-call join point shadow*; khi phần thân `pay` được chạy, có thể phát sinh một *method-execution join point* khác ở phía phương thức được gọi.

Hai hệ quả cần nhớ:

- Không được suy ra **số lần advice chạy** chỉ từ số vị trí mã nguồn. Một shadow có thể được đi qua nhiều lần, không lần nào hoặc lồng nhau trong đệ quy.
- Không phải shadow tiềm năng nào cũng được advice xử lý. Pointcut có thể chọn theo điều kiện tĩnh hoặc kiểm tra thêm điều kiện động; phạm vi weaving còn phụ thuộc công cụ.

Thuật ngữ *shadow* không bắt buộc có trong mọi API AOP, nhưng cách phân biệt **vị trí trong mã** và **lần thực thi cụ thể** là nền tảng để hiểu chủ đề này.

## 3. Những gì thường được xem là thông tin tĩnh

Thông tin tĩnh mô tả hình dạng/định danh của join point. Cụ thể đến đâu phụ thuộc loại join point và metadata mà công cụ cung cấp.

| Thông tin tĩnh | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Loại join point (kind)** | Sự kiện nào đang được mô hình hóa | Method call, method execution, field read |
| **Chữ ký (signature)** | Tên, kiểu khai báo, danh sách kiểu tham số, kiểu trả về nếu áp dụng | `PaymentService.pay(String,long):Receipt` |
| **Kiểu khai báo (declaring type)** | Kiểu mà thành viên/chữ ký được khai báo | `PaymentService` |
| **Modifier/visibility** | Các thuộc tính như `public`, `static` nếu được biểu diễn | `public` |
| **Vị trí mã (source location)** | Tệp/dòng/vị trí được liên kết với shadow nếu có | `Checkout.java:42` |
| **Đặc tính cấu trúc khác** | Quan hệ kiểu, annotation, kiểu field, constructor… | Phương thức có dấu đánh dấu kiểm toán |

Một số lưu ý quan trọng:

1. **Source location không luôn tồn tại.** Mã tạo tự động, lớp biên dịch không kèm thông tin gỡ lỗi, mã native hoặc nền tảng không lưu ánh xạ nguồn có thể không cung cấp tệp/dòng.
2. **Chữ ký của điểm gọi và điểm thực thi có thể khác góc nhìn.** Một call join point thường gắn với vị trí gọi; execution join point gắn với phần thân được thực thi. Đừng mặc định chữ ký/đối tượng nhìn từ bên gọi luôn trùng với đích thực tế.
3. **Kiểu khai báo khác kiểu runtime.** Giao diện `PaymentGateway` có thể khai báo `pay`, còn lúc chạy đối tượng thực tế là `RemotePaymentGateway`.
4. **Cùng tên không đủ định danh phương thức.** Java có overload, nên `pay(String)` và `pay(String,long)` là hai chữ ký khác nhau.
5. **Thông tin tĩnh là metadata, không phải bảo đảm can thiệp.** Việc công cụ đọc được chữ ký chưa chứng minh mọi đường gọi đã được weaving.

### 3.1. “Tĩnh” tương đối với chính join point đang xét

Nếu một ứng dụng có cùng chữ ký phương thức ở hai lớp khác nhau thì thông tin tĩnh của chúng vẫn khác bởi **kiểu khai báo**. Nếu một phương thức xuất hiện ở nhiều vị trí gọi, các **call shadows** có thể có source location khác nhau nhưng cùng nhắm tới chữ ký liên quan.

Điều này quan trọng khi yêu cầu là “theo dõi *mọi lần thực thi của một phương thức*” so với “theo dõi *lời gọi xuất phát từ một tệp/đoạn mã cụ thể*”. Hai yêu cầu có thể cần chọn loại join point và tiêu chí tĩnh khác nhau.

## 4. Những gì thường thuộc ngữ cảnh động

Ngữ cảnh động thuộc về **một lần xuất hiện cụ thể** của join point. Tùy loại điểm và kiểu advice, hệ thống có thể cung cấp các dữ liệu sau:

| Ngữ cảnh động | Ví dụ | Thời điểm/giới hạn |
| --- | --- | --- |
| **Đối tượng đang thực thi (nếu có)** | Instance của `CheckoutService` | Không phải join point nào cũng có một đối tượng |
| **Đối tượng đích nhận thao tác (nếu có)** | Instance của `PaymentGatewayImpl` | Khác đối tượng bên gọi trong nhiều trường hợp |
| **Giá trị tham số** | `["A-01", 500]` | Có khi bắt đầu lời gọi; có thể bị thay đổi bởi advice/cơ chế |
| **Thông tin thread hoặc execution context** | Thread hiện tại, trace ID | Có thể thay đổi khi chuyển luồng; không luôn tự động lan truyền |
| **Giá trị trả về** | Một `Receipt` | Chỉ biết sau khi hoàn tất bình thường ở điểm tương ứng |
| **Ngoại lệ thoát ra** | `IllegalArgumentException` | Chỉ có trên đường thất bại mà ranh giới quan sát nhận thấy |
| **Thời điểm/duration** | Bắt đầu và thời gian xử lý | Phải tự đo/ghi bằng advice hoặc cơ chế quan sát |
| **Trạng thái runtime liên quan** | Dữ liệu dùng trong điều kiện chọn điểm | Tùy hợp đồng ứng dụng và công cụ |

Không phải mọi mục đều là trường API có sẵn trên đối tượng `JoinPoint`. Ví dụ, **thời gian thực thi** thường phải được đo bằng cách lấy mốc bắt đầu/kết thúc, và **trace ID** có thể nằm trong ngữ cảnh riêng của ứng dụng. Bảng phân biệt thông tin *có thể thu thập/quan sát* với những trường mặc định mà một API nhất định hứa cung cấp.

### 4.1. Giá trị thay đổi trong một lần chạy

Tham số là ngữ cảnh động ngay cả khi **kiểu tham số** là thông tin tĩnh. Một tham số tham chiếu đến đối tượng mutable có thể thay đổi trạng thái trong khi thao tác chạy. Tương tự, giá trị trả về chưa có ở thời điểm before advice, còn ngoại lệ chưa có cho tới khi nhánh ném lỗi thực sự xuất hiện.

Ví dụ:

```text
Static:
  kind = method execution
  signature = OrderService.place(String, int):String

Lần gọi #1:
  target = OrderServiceImpl instance X
  args = ["ORD-7", 2]
  outcome = return "ACCEPTED:ORD-7"

Lần gọi #2:
  target = OrderServiceImpl instance Y
  args = ["ORD-8", -1]
  outcome = throw IllegalArgumentException
```

Bảng thông tin tĩnh của hai lần gọi **có thể giống nhau**, nhưng kết quả động khác hẳn. Tên instance X/Y chỉ là nhãn minh họa; không nên đưa địa chỉ bộ nhớ ngẫu nhiên vào log hay coi identity hash là danh tính nghiệp vụ.

## 5. Thời điểm các thông tin xuất hiện trong luồng advice

Một mô hình đơn giản cho thao tác đồng bộ:

```text
[Có thông tin tĩnh về điểm được chọn]
                 |
                 v
Join point bắt đầu một lần thực thi
  |  + Có tham số thực tế / đối tượng phù hợp (nếu loại điểm hỗ trợ)
  |  + Before advice có thể quan sát ngữ cảnh bắt đầu
  |
  v
Thực thi phần gốc (hoặc lớp around tiếp theo)
  |
  +---- trả về bình thường ----> Có giá trị trả về cho nhánh thành công
  |                                  |
  |                                  +--> After returning advice
  |
  +---- ném ngoại lệ ----------> Có ngoại lệ thoát ra tại ranh giới
                                     |
                                     +--> After throwing advice

Các bước kết thúc/finally của chuỗi advice (nếu được hỗ trợ)
                 |
                 v
Bên gọi nhận kết quả hoặc ngoại lệ sau can thiệp
```

Sơ đồ khái niệm này không ấn định thứ tự mặc định cho mọi công cụ và không bảo đảm tất cả advice chạy trong mọi tình huống. **Around advice** có thể không gọi tiếp phần gốc; nó cũng có thể thay đổi tham số, kết quả hoặc ngoại lệ nếu giải pháp AOP cho phép.

Từ đó rút ra nguyên tắc:

- **Before:** hợp lý để dùng metadata tĩnh, giá trị tham số và đối tượng của lần bắt đầu. Không nên đòi “kết quả đã trả” khi thao tác chưa chạy.
- **After returning:** có thể gắn kết quả với chữ ký và tham số của lần chạy thành công.
- **After throwing:** có thể gắn ngoại lệ thoát ra với điểm và lần thực thi thất bại.
- **Around:** có thể thấy nhiều giai đoạn, đo thời lượng hoặc thay đổi luồng; phải xác định rõ hành vi khi không `proceed`.

**Không có kiểu dữ liệu “result hoặc exception” duy nhất trong mọi join-point API.** Kết quả và ngoại lệ thường do advice hoặc cơ chế interception cung cấp ở giai đoạn kết thúc thích hợp.

## 6. Ví dụ Java 17 chạy được: một chữ ký tĩnh, hai ngữ cảnh động

Java thông thường không tự có cú pháp aspect/pointcut thống nhất. Ví dụ dưới đây sử dụng **proxy giao diện của JDK** để quan sát các lời gọi đi qua proxy. `java.lang.reflect.Method` cung cấp một số metadata tương ứng thông tin tĩnh; `target`, `arguments` và kết quả/ngoại lệ của từng lời gọi là phần ngữ cảnh động được handler thu thập.

Đây là **mô hình minh họa interception có giới hạn**, không phải hiện thực của mọi loại join point AOP. Nó chỉ quan sát các lời gọi được chuyển qua proxy đang tạo.

Lưu vào `JoinPointContextDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;
import java.util.stream.Collectors;

public class JoinPointContextDemo {

    interface Operation {
        String execute(String requestId, int units);
    }

    static final class DefaultOperation implements Operation {
        @Override
        public String execute(String requestId, int units) {
            System.out.println("business: " + requestId + " x " + units);
            if (units < 0) {
                throw new IllegalArgumentException("units must be nonnegative");
            }
            return requestId + ":" + units;
        }
    }

    public static void main(String[] args) {
        Operation target = new DefaultOperation();

        Operation proxy = (Operation) Proxy.newProxyInstance(
                Operation.class.getClassLoader(),
                new Class<?>[] { Operation.class },
                (ignoredProxy, method, arguments) -> invoke(target, method, arguments)
        );

        System.out.println("caller: " + proxy.execute("JOB-7", 2));

        try {
            proxy.execute("BAD", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("caller caught: " + ex.getMessage());
        }
    }

    private static Object invoke(Operation target, Method method, Object[] arguments)
            throws Throwable {
        String parameterTypes = Arrays.stream(method.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));

        String signature = method.getDeclaringClass().getSimpleName()
                + "." + method.getName()
                + "(" + parameterTypes + "):"
                + method.getReturnType().getSimpleName();

        System.out.println("static: " + signature);
        System.out.println("dynamic: target=" + target.getClass().getSimpleName()
                + ", args=" + Arrays.toString(arguments));

        try {
            Object result = method.invoke(target, arguments);
            System.out.println("outcome: return " + result);
            return result;
        } catch (InvocationTargetException wrapped) {
            Throwable cause = wrapped.getCause();
            System.out.println("outcome: throw " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
            throw cause;
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac JoinPointContextDemo.java
java JoinPointContextDemo
```

Đầu ra xác định:

```text
static: Operation.execute(String,int):String
dynamic: target=DefaultOperation, args=[JOB-7, 2]
business: JOB-7 x 2
outcome: return JOB-7:2
caller: JOB-7:2
static: Operation.execute(String,int):String
dynamic: target=DefaultOperation, args=[BAD, -1]
business: BAD x -1
outcome: throw IllegalArgumentException: units must be nonnegative
caller caught: units must be nonnegative
```

### 6.1. Giải thích sự khác nhau giữa các dòng

- Hai lần đều in `static: Operation.execute(String,int):String`. Tại handler, đối tượng `Method` mô tả cùng phương thức giao diện, vì vậy tên, kiểu tham số và kiểu trả về không thay đổi giữa hai lời gọi.
- `target=DefaultOperation` là loại đối tượng thực được chuyển tiếp tới trong ví dụ; đây là **thông tin runtime** được suy từ `target`. Việc cả hai lần có cùng loại target không biến nó thành chữ ký tĩnh.
- Mảng tham số `[JOB-7, 2]` và `[BAD, -1]` khác nhau; đây là **ngữ cảnh động**.
- Sau khi phần nghiệp vụ chạy, kết quả thành công `JOB-7:2` chỉ có ở lần thứ nhất. Lần thứ hai phát sinh `IllegalArgumentException`; handler gỡ lớp bọc `InvocationTargetException` do reflection tạo ra rồi ném lại lỗi gốc.
- Caller nhận kết quả hoặc bắt ngoại lệ **sau khi** cơ chế chặn hoàn tất phần xử lý của nó.

### 6.2. Chính xác thì ví dụ mô phỏng điều gì?

Proxy minh họa cách tách **metadata tương đối ổn định** khỏi **dữ liệu theo invocation**. Nó không có bộ pointcut tổng quát, không cho phép mặc nhiên can thiệp vào field access hay mọi lời gọi nội bộ, và `Method` trong handler là phương thức tương ứng trên giao diện proxy, không nhất thiết là mọi metadata của một execution join point trong công cụ weaving thực thụ.

Cũng không nên suy rằng `getDeclaringClass()` luôn trả về **lớp cài đặt thực tế**. Ở ví dụ này, nó trả `Operation` vì handler nhận `Method` của giao diện; `target.getClass().getSimpleName()` trả `DefaultOperation`. Đây chính là lý do cần phân biệt **declaring type** với **runtime target type**.

### 6.3. Điều không được suy từ kết quả

Ví dụ không chứng minh mọi công cụ AOP đều thu được source location, caller object, tên tham số nguồn, giá trị trả về ở before advice, hay toàn bộ ngữ cảnh của cuộc gọi được thực thi bên ngoài proxy. Nó chỉ chứng minh những gì handler JDK đang thực sự quan sát.

## 7. Static signature, declaring type và runtime target khác nhau thế nào?

Trong Java, tính đa hình khiến cùng một chữ ký nhìn từ bên gọi có thể dẫn tới các hiện thực khác nhau.

```java
interface Formatter {
    String format(String value);
}

final class UpperFormatter implements Formatter {
    public String format(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }
}

final class LowerFormatter implements Formatter {
    public String format(String value) {
        return value.toLowerCase(java.util.Locale.ROOT);
    }
}
```

Đoạn trên chỉ minh họa kiểu và cài đặt; không có `main` riêng. Với lời gọi `Formatter formatter = ...; formatter.format("AbC")`:

- Chữ ký quan sát từ kiểu giao diện có thể là `Formatter.format(String):String`.
- Nếu đối tượng thực là `UpperFormatter`, kết quả là `"ABC"`.
- Nếu đối tượng thực là `LowerFormatter`, kết quả là `"abc"`.
- Tùy kiểu join point, thông tin tĩnh có thể gắn với **vị trí lời gọi**, **khai báo trên giao diện** hoặc **điểm thực thi của cài đặt**.

Đừng áp đặt một cách diễn giải duy nhất cho toàn bộ mô hình AOP. Trước khi thiết kế pointcut/advice, phải xác định rõ: **đang quan sát method call hay method execution, và metadata do giải pháp cụ thể trả về mang ngữ nghĩa nào?**

### 7.1. Overload và override không giống nhau

- **Overload:** `pay(String)` và `pay(String,long)` có các danh sách kiểu tham số khác nhau; chỉ dùng tên `pay` là không đủ để định danh.
- **Override:** lớp con ghi đè một phương thức có cùng chữ ký tương ứng; kiểu runtime có thể quyết định phần thực thi thật sự.
- **Generic/bridge methods:** trình biên dịch Java có thể sinh phương thức cầu nối để giữ ngữ nghĩa đa hình sau type erasure. Công cụ chặn/weaving có thể thấy metadata mức bytecode khác với hình dung ở mã nguồn.

Vì vậy, đừng xây các chính sách quan trọng chỉ từ chuỗi tên phương thức; hãy hiểu cách xác định chữ ký và điểm thực thi của nền tảng.

## 8. Đối tượng bên gọi, đối tượng đích và đối tượng hiện tại

Một mô hình join point có thể phân biệt nhiều vai trò:

- **Caller:** thành phần kích hoạt một lời gọi, nếu loại join point cho phép nhận diện.
- **Current/this object:** đối tượng gắn với phần mã đang chạy ở một phía của điểm thực thi, tùy định nghĩa ngữ nghĩa của công cụ.
- **Target object:** đối tượng nhận thao tác hoặc đối tượng đích liên quan đến join point.
- **Proxy/interceptor object:** đối tượng trung gian mà caller có thể thấy ở một số cơ chế triển khai.

Chúng có thể trùng nhau hoặc khác nhau. Với lời gọi `checkoutService.checkout()` bên trong có `gateway.charge()`, `checkoutService` có thể là phía gọi còn `gateway` là đích, trong khi một proxy có thể đứng giữa.

Ví dụ sơ đồ:

```text
CheckoutService instance X
    |
    | gateway.charge("ORD-7")
    v
Gateway proxy P (nếu có)
    |
    | chuyển tiếp lời gọi
    v
GatewayImpl instance Y
```

Nếu advice nhận được các đối tượng đó, phải biết công cụ mô tả chúng ở **loại join point nào**. Không nên giả định `this`, `target`, proxy và caller luôn là một đối tượng. Ở điểm `static` hoặc một loại sự kiện không gắn với instance, một số vai trò thậm chí không tồn tại.

Quan trọng hơn, **identity của đối tượng** khác **loại của đối tượng**: `GatewayImpl` có thể dùng chung cho hàng nghìn lần gọi; từng instance khác nhau vẫn có cùng tên lớp. Đừng dựa vào `toString()` mặc định hoặc địa chỉ bộ nhớ thay cho mã nghiệp vụ/trace ID ổn định.

## 9. Ngữ cảnh kết quả và ngoại lệ không có cùng vòng đời

Cùng một lần thực thi có thể được quan sát tại nhiều giai đoạn:

```text
Before:
  static  = kind/signature/location
  dynamic = target + args + context khả dụng

Proceed:
  phần nghiệp vụ gốc chạy

After returning:
  kết quả trả về + context gắn với lần thực thi

After throwing:
  ngoại lệ thoát ra + context gắn với lần thực thi

After/finally:
  hành vi kết thúc theo ngữ nghĩa advice của công cụ
```

Ví dụ phương thức:

```java
String lookup(int code) {
    if (code < 0) {
        throw new IllegalArgumentException("bad code");
    }
    return "VALUE-" + code;
}
```

Đây là đoạn minh họa, không độc lập có `main`. Một advice ở thời điểm trước khi chạy có thể biết `code=-1` và chữ ký, nhưng **chưa có ngoại lệ thoát ra**. Một advice quan sát sau khi ném lỗi có thể biết ngoại lệ `IllegalArgumentException` vì khi đó đường thực thi đã thất bại.

### 9.1. Ngoại lệ được bắt bên trong không phải ngoại lệ thoát khỏi join point

```java
String safeLookup(int code) {
    try {
        return lookup(code);
    } catch (IllegalArgumentException ex) {
        return "FALLBACK";
    }
}
```

Nếu join point đang quan sát là **method execution của `safeLookup`**, nó có thể kết thúc bình thường với `"FALLBACK"`. Ngoại lệ phát sinh tại `lookup` đã được xử lý trước khi thoát khỏi `safeLookup`. Muốn quan sát chính exception handler hay lần thực thi `lookup`, cần điểm can thiệp tương ứng **nếu công cụ hỗ trợ**.

### 9.2. Advice cũng có thể thay đổi thứ mà lớp ngoài nhìn thấy

Một around advice có thể bắt ngoại lệ rồi trả fallback, hoặc tự ném ngoại lệ mới. Advice ở vòng ngoài khi đó thấy kết quả/ngoại lệ sau chuyển đổi, có thể khác kết quả/ngoại lệ gốc. Vì thế, khi phân tích **dynamic outcome**, phải xác định **ranh giới đang quan sát**: phần thân nghiệp vụ, một lớp advice bên trong hay toàn bộ chuỗi advice.

## 10. Điều kiện tĩnh và điều kiện động trong pointcut

Một pointcut có thể kết hợp điều kiện dựa trên cấu trúc chương trình và điều kiện dựa trên lần chạy. Cách biểu đạt cụ thể tùy giải pháp AOP.

Mã giả (không phải cú pháp Java hoặc cú pháp chung cho mọi công cụ):

```text
pointcut largeTransfer:
    kind == METHOD_EXECUTION
    AND signature == TransferService.transfer(String,long)
    AND runtimeArgument("amount") > 1000

before largeTransfer(context):
    recordAudit(context.signature, context.arguments)
```

Phân tích:

- `kind == METHOD_EXECUTION` là điều kiện theo **loại join point**, thuộc cấu trúc tĩnh.
- `signature == ...` là điều kiện **theo chữ ký**.
- `amount > 1000` là điều kiện **theo giá trị động** của một lần thực thi.
- `recordAudit` sử dụng cả metadata tĩnh và dữ liệu động.

Cùng một shadow có thể đi qua nhiều lần:

| Lần gọi | Chữ ký | Amount | Pointcut có khớp? |
| --- | --- | ---: | --- |
| #1 | `transfer(String,long)` | 100 | Không |
| #2 | `transfer(String,long)` | 1001 | Có |
| #3 | `transfer(String,long)` | 5000 | Có |

Bảng là kết quả **theo quy tắc mã giả** và giả định điểm thực thi đã được công cụ can thiệp. Không phải mọi công cụ đều hỗ trợ chọn join point dựa vào giá trị tham số hoặc tên tham số nguồn.

### 10.1. Điều kiện động được kiểm tra khi nào?

Tùy cơ chế, một phần pointcut có thể được xác định lúc biên dịch/nạp mã, nhưng điều kiện phụ thuộc tham số/chủ thể vẫn phải kiểm tra **ở lần chạy liên quan**. Điều này có thể phát sinh chi phí khi điểm tĩnh xuất hiện rất thường xuyên.

Không nên giả định “pointcut đã khớp một lần” thì mọi invocation sau cũng khớp. Ngược lại, một chính sách có điều kiện động kiểm tra sai thời điểm có thể đọc trạng thái đã thay đổi và tạo ra kết quả khó giải thích.

### 10.2. Kiểu tham số tĩnh khác giá trị tham số động

Với chữ ký `save(List<String> items)`:

- Kiểu khai báo được lưu ở bytecode Java chịu ảnh hưởng của **type erasure**; generic type information có thể cần cơ chế metadata khác để đọc.
- Giá trị động `items` là **một đối tượng danh sách cụ thể** ở từng invocation, có thể rỗng hoặc có hàng trăm phần tử.
- Suy ra số phần tử từ **chữ ký** là sai; muốn biết `items.size()` phải quan sát đối tượng ở lần chạy phù hợp.

## 11. Nhiều luồng, đệ quy và trạng thái theo invocation

Thông tin tĩnh có thể dùng chung cho vô số lần thực thi, nhưng ngữ cảnh động của mỗi lần phải được quản lý đúng ranh giới.

### 11.1. Nhiều luồng dùng cùng phương thức

Hai thread cùng gọi `transfer`:

```text
Thread A:  static S  | args ["A", 100]  | start A ------- end A
Thread B:  static S  | args ["B", 900]  |    start B -------- end B
```

Cả hai có thể có chữ ký tĩnh S như nhau. Nhưng trạng thái `startTime`, `requestId`, `outcome` không được đặt trong một biến instance dùng chung rồi ghi đè tùy ý. Nếu không, duration và trace có thể nhầm qua lại giữa các lần gọi.

Một around advice đồng bộ thường có thể giữ biến local cho từng lời gọi; nếu dùng bộ nhớ dùng chung, cần thiết kế khóa hoặc cấu trúc dữ liệu phù hợp.

### 11.2. Đệ quy: cùng chữ ký, nhiều frame sống đồng thời

```text
factorial(3)
   -> factorial(2)
      -> factorial(1)
      <- result 1
   <- result 2
<- result 6
```

Cùng kiểu điểm thực thi `factorial(int)` có nhiều lần xuất hiện lồng nhau. Nếu advice ghi mốc thời gian bằng biến dùng chung, một lần gọi sâu có thể ghi đè lần gọi ngoài. Thông tin động phải được gắn với **đúng invocation/frame**, không chỉ với chữ ký.

### 11.3. Ngữ cảnh thread-local không luôn đi theo tác vụ

Một số hệ thống dùng `ThreadLocal` cho trace ID hoặc thông tin tạm thời. Nếu một thao tác chuyển sang worker thread hoặc dùng mô hình bất đồng bộ, context đó **không tự được mang qua mọi ranh giới**. Cần cơ chế truyền ngữ cảnh rõ ràng theo tác vụ nếu thiết kế yêu cầu.

## 12. Bất đồng bộ: kết quả trả về khác thời điểm công việc hoàn tất

Giả sử một phương thức `startExport()` trả về `CompletableFuture<Report>`:

```text
Gọi startExport()
   |
   | static = startExport():CompletableFuture
   | dynamic args = dữ liệu request
   v
Method return -> Future chưa hoàn tất
   |
   | ... công việc tiếp tục ...
   v
Future hoàn tất với Report hoặc lỗi
```

Nếu join point là **method execution của `startExport`**, advice sau khi phương thức trả về có thể chỉ thấy **đối tượng Future**, không thấy báo cáo cuối cùng. Ngoại lệ từ tác vụ bất đồng bộ có thể được biểu diễn trong Future thay vì thoát trực tiếp khỏi phương thức khởi tạo.

Muốn ghi nhận kết quả cuối cùng, cần quan sát thêm ranh giới completion của tác vụ (callback/completion stage hoặc điểm phù hợp khác). Không được đánh đồng:

- **Return value động của method execution:** đối tượng Future.
- **Kết quả động của tác vụ bất đồng bộ:** giá trị Report hoặc lỗi ở thời điểm hoàn thành về sau.

Điều này cũng ảnh hưởng tới đo thời gian, log và truyền ngữ cảnh qua luồng.

## 13. Dữ liệu tĩnh không bảo đảm lúc chạy sẽ can thiệp được

Một hệ thống AOP có thể thực hiện weaving khi biên dịch, khi nạp mã hoặc chặn lời gọi tại thời điểm chạy. Các phương thức này không có cùng tập join point.

- **Compile-time weaving:** mã thực thi có thể đã được kết hợp với advice khi tạo bản build.
- **Load-time weaving:** mã có thể được thay đổi khi thành phần được nạp.
- **Runtime interception:** lời gọi có thể cần đi qua đối tượng trung gian cụ thể.

Một tình huống dễ nhầm: phản xạ Java có thể đọc metadata của `method.execute()`, nhưng nếu ứng dụng gọi trực tiếp `target.execute()` mà không đi qua proxy ở ví dụ, handler **không chạy**, cho dù chữ ký vẫn tồn tại.

Vậy cần phân biệt hai câu hỏi:

1. **Điểm này mô tả được bằng metadata hay không?**
2. **Cơ chế AOP hiện tại có thực sự can thiệp được ở đường chạy này hay không?**

Chỉ câu thứ hai mới trả lời chuyện advice có chạy trong invocation đang xét. Các biến thể như self-invocation, gọi từ mã thư viện, code được nạp động hoặc điểm field access cần được xác minh riêng theo công cụ.

## 14. Dùng static information và dynamic context để logging, audit, metrics

### 14.1. Thiết kế một bản ghi có cấu trúc

Một bản ghi quan sát hữu ích có thể tách phần định danh điểm thực thi và phần dữ liệu theo lần gọi:

```json
{
  "joinPoint": {
    "kind": "method-execution",
    "signature": "PaymentService.pay(String,long)"
  },
  "invocation": {
    "correlationId": "req-204",
    "durationMs": 18,
    "status": "success"
  }
}
```

Đây là **mẫu dữ liệu minh họa**, không phải đầu ra của một API mặc định. `durationMs` và `correlationId` phải do ứng dụng/cơ chế đo tạo ra, không phải cứ có join point là tự phát sinh.

Thông thường nên dùng:

- Metadata tĩnh để **phân nhóm** theo phương thức, loại điểm, thành phần.
- Dynamic context để **liên kết lần gọi**, đếm thành công/thất bại và đo thời lượng.
- Một định danh correlation riêng để gắn các log thuộc cùng yêu cầu/tác vụ.
- Bộ nhãn metrics có cardinality kiểm soát được; không dùng các giá trị ngẫu nhiên như từng request ID làm nhãn metrics có số lượng vô hạn.

### 14.2. Bảo vệ dữ liệu nhạy cảm

Các tham số và kết quả động có thể chứa mật khẩu, token, dữ liệu cá nhân hoặc thông tin thanh toán. Một aspect tự động `toString()` toàn bộ `args` hoặc `result` có thể vô tình làm rò rỉ dữ liệu.

Do đó cần:

1. Chỉ ghi các trường phục vụ mục đích quan sát đã xác định.
2. Loại bỏ hoặc che dữ liệu nhạy cảm trước khi ghi.
3. Giới hạn độ dài và cấu trúc của bản ghi để tránh dữ liệu quá lớn, vòng tham chiếu hoặc `toString()` ném lỗi.
4. Xác định vòng đời và quyền truy cập dữ liệu log.
5. Không để telemetry thay đổi hợp đồng nghiệp vụ chỉ vì một bản ghi bị lỗi, trừ khi chính sách hệ thống có chủ ý yêu cầu như vậy.

### 14.3. Phân biệt metadata tĩnh với giá trị được suy diễn

Tên tệp/dòng, chữ ký và kiểu join point là những thông tin gắn với cấu trúc mã. Nhưng việc gắn nhãn `status=success` có thể phụ thuộc vào cách ứng dụng hiểu “thành công”: trả về bình thường chưa chắc đồng nghĩa giao dịch phân tán đã được hoàn tất ở hệ thống bên ngoài.

Advice cần chọn **ranh giới nghiệp vụ đúng** trước khi suy diễn trạng thái động thành một sự kiện nghiệp vụ.

## 15. Những lỗi thường gặp

**“Static information chỉ là tên phương thức.”** Chưa đủ. Cần xét loại join point, chữ ký, kiểu khai báo, vị trí mã và những metadata khác nếu phù hợp.

**“Đối tượng target là một phần của chữ ký tĩnh.”** Thường sai. Chữ ký chỉ mô tả phương thức/kiểu; đối tượng đích cụ thể là dữ liệu của invocation. Kiểu runtime cũng có thể khác declaring type.

**“Một shadow ứng với đúng một lần advice chạy.”** Sai. Một vị trí mã có thể chạy không lần nào, nhiều lần hoặc đệ quy; pointcut động còn có thể lọc một số lần.

**“Before advice đã biết kết quả và ngoại lệ.”** Không theo nghĩa thông thường. Kết quả và lỗi thoát ra chỉ biết khi phần được quan sát đã diễn ra, trừ các giá trị giả lập/tiên đoán của chính advice.

**“Có source location trong mã nguồn thì lúc chạy luôn đọc được vị trí ấy.”** Không bảo đảm. Tùy debug metadata, công cụ, cách tạo và biến đổi mã.

**“Method call và method execution có cùng bộ ngữ cảnh.”** Không nhất thiết. Phía gọi và phía thân thực thi có thể có vai trò đối tượng, vị trí tĩnh và thông tin khác nhau.

**“Mọi giá trị runtime đều là trường bắt buộc của JoinPoint API.”** Không. Thread context, duration, correlation ID hoặc kết quả hoàn tất bất đồng bộ có thể cần cơ chế riêng.

**“Metadata của phương thức chứng minh advice đã chạy.”** Sai. Phải kiểm tra điểm có nằm trong phạm vi weaving/interception và có khớp pointcut khi chạy hay không.

**“Ghi tất cả args/result sẽ giúp debug tốt nhất.”** Không an toàn và có thể rất tốn kém. Nên chọn lọc/che dữ liệu và kiểm soát độ lớn.

## 16. Cách tự kiểm chứng trên một chương trình

Khi cần phân tích thông tin tĩnh và động của một join point cụ thể, thực hiện theo thứ tự:

1. **Chọn đúng loại điểm:** method call, execution, constructor, field access… tùy công cụ.
2. **Xác định thông tin tĩnh:** chữ ký đầy đủ, declaring type, loại join point, vị trí mã nếu có.
3. **Liệt kê những giá trị động thật sự có sẵn:** đối tượng, args, kết quả/ngoại lệ và context theo từng thời điểm advice.
4. **Phân biệt phía gọi và phía đích:** đặc biệt khi có interface, override, proxy hoặc nhiều đường gọi.
5. **Đánh giá pointcut:** điều kiện tĩnh có chọn đúng shadow; điều kiện động có chọn đúng invocation.
6. **Kiểm tra đường thực thi:** điểm đã được weaving/chặn thật chưa; có đường gọi trực tiếp hoặc nội bộ bỏ qua interception không.
7. **Thử ít nhất hai invocation khác dữ liệu:** kiểm tra static metadata ổn định và dynamic values tương ứng.
8. **Thử đường ngoại lệ và bất đồng bộ nếu có:** xác minh advice nhận điều gì ở từng giai đoạn.
9. **Thử đồng thời/đệ quy nếu liên quan:** tránh trộn trạng thái của các lần gọi.

Bảng kiểm thử minh họa:

| Ca | Static metadata | Dynamic context | Kỳ vọng |
| --- | --- | --- | --- |
| `execute("X",1)` | Cùng signature | Args X,1; trả kết quả | Truy xuất được dữ liệu riêng lần X |
| `execute("Y",2)` | Cùng signature | Args Y,2; trả kết quả | Không lẫn với lần X |
| `execute("BAD",-1)` | Cùng signature | Args BAD,-1; ngoại lệ | Quan sát đúng đường lỗi |
| Lời gọi qua đường khác | Có thể cùng signature | Invocation khác | Advice chỉ chạy nếu đường đó được hỗ trợ |
| Hai lời gọi đồng thời | Metadata dùng chung | Context khác nhau | Không lẫn dữ liệu |
| Future chưa hoàn thành | Signature trả Future | Return là Future | Không báo tác vụ hoàn tất sớm |

## 17. Câu hỏi tự luyện

**1. Hai lần gọi cùng một phương thức có thể có static information khác nhau không?**

Nếu chúng là cùng loại join point ở cùng vị trí/định nghĩa tĩnh thì phần metadata tương ứng thường giống nhau; tuy nhiên hai **method-call shadows ở vị trí khác nhau** hoặc khác phần khai báo/điểm thực thi có thể có thông tin tĩnh khác. Phải xác định đang so sánh *đúng loại điểm* và *đúng vị trí* nào.

**2. Nếu một biến có kiểu `Formatter` nhưng trỏ tới `UpperFormatter`, đâu là dữ liệu tĩnh và động?**

Kiểu/chữ ký được dùng để mô tả điểm gọi có thể dựa trên `Formatter.format(String)` ở phía mã gọi. Đối tượng runtime `UpperFormatter` là ngữ cảnh động. Nếu quan sát điểm **execution** của phần cài đặt, metadata tĩnh của điểm đó có thể gắn với `UpperFormatter.format(String)`.

**3. Một pointcut chọn phương thức `transfer(String,long)` khi amount > 1000. Hai lần gọi 100 và 5000 có cùng static signature nhưng advice chạy mấy lần?**

Theo quy tắc giả định, advice chỉ chạy ở lần 5000 **nếu** join point được hỗ trợ và pointcut thực sự đánh giá giá trị động như mô tả.

**4. Vì sao after-returning trên phương thức trả Future không bảo đảm biết kết quả cuối cùng của tác vụ?**

Vì tại thời điểm phương thức trả về, Future có thể chưa hoàn tất. Đây là kết quả của *method execution*, khác với giá trị/lỗi của công việc được Future biểu diễn về sau.

**5. Vì sao không nên lưu một biến `currentArgument` chung trong aspect cho mọi lần gọi?**

Vì nhiều invocation có thể đồng thời hoặc lồng nhau; trạng thái chung có thể bị ghi đè, dẫn tới ngữ cảnh sai. Cần lưu theo invocation/tác vụ hoặc đồng bộ đúng mục đích.

**6. Nếu hệ thống đọc được `Method.getName()` nhưng advice không chạy, điều gì cần kiểm tra?**

Cần kiểm tra mô hình join point, pointcut, đường đi qua proxy/weaving, phạm vi lớp được áp dụng, điều kiện động và thứ tự/khả năng dừng của các advice bên ngoài. Đọc metadata chưa đủ chứng minh đường gọi bị chặn.

## 18. Kết luận

Đối với một join point, hãy luôn nhìn theo **hai tầng bổ sung**:

- **Thông tin tĩnh** định danh loại điểm thực thi, cấu trúc/chữ ký, kiểu khai báo và vị trí trong mã khi có. Nó giúp xác định *điểm nào có khả năng được chọn* và hỗ trợ mô tả pointcut.
- **Ngữ cảnh động** gắn với *mỗi lần điểm ấy thực sự diễn ra*: đối tượng, tham số, trạng thái, kết quả, ngoại lệ và những thông tin quan sát theo thời gian phù hợp. Nó giúp aspect ứng xử/ghi nhận đúng cho từng invocation.

Một vị trí tĩnh có thể phát sinh nhiều lần chạy, hai lần chạy cùng chữ ký có thể có đối tượng và kết quả khác nhau, và không phải mọi đường gọi đều được cơ chế AOP can thiệp. Hiểu rõ ranh giới **static shadow — dynamic occurrence — pointcut — advice — weaving** giúp xây dựng aspect chính xác, kiểm thử được và không làm mất ngữ nghĩa nghiệp vụ.
