# Truy cập chữ ký và mô tả điểm can thiệp trong advice AOP

> **Mục tiêu học tập:** Hiểu dữ liệu mô tả **join point** mà một advice có thể quan sát: loại điểm can thiệp, **chữ ký khai báo** (signature), kiểu khai báo, tên, các kiểu tham số, kiểu kết quả và metadata tùy mô hình; phân biệt chúng với **đối số, đối tượng và ngữ cảnh thực thi thực tế**. Biết khai thác thông tin để ghi vết, đo lường và chẩn đoán mà không nhầm call site với execution, phương thức giao diện với phương thức triển khai, hoặc dữ liệu mô tả tĩnh với dữ liệu thay đổi theo từng lần gọi.

## 1. Vì sao advice cần biết nó đang đứng ở đâu?

Một hệ thống có nhiều thao tác như `submitOrder`, `refund` và `cancelOrder`. Nếu một advice chỉ in thông báo “đã vào phương thức” thì rất khó xác định hoạt động nào đang được quan sát, đặc biệt khi có **overload** (nhiều phương thức cùng tên nhưng khác chữ ký) hoặc những nhóm lớp dùng tên phương thức giống nhau.

Hành vi ghi nhận hữu ích thường cần thông tin có cấu trúc:

~~~text
Loại join point:  thực thi phương thức
Phương thức:       OrderService.submit(String, int)
Đối tượng đích:   OrderServiceImpl
Đối số lần này:   ["A-17", 2]
Kết quả:           "receipt-A-17"
~~~

Trong đó:

- **Loại join point, tên và chữ ký** mô tả **phần tử hoặc ranh giới chương trình** mà công cụ đang quan sát.
- **Đối tượng đích và đối số** nói về **một lần thực thi cụ thể**.
- **Kết quả hoặc ngoại lệ** chỉ biết được sau khi phần thực thi liên quan hoàn tất theo ngữ nghĩa của advice.
- Một số thông tin khác như **vị trí mã nguồn, annotation, caller, luồng điều khiển** chỉ có khi mô hình AOP, môi trường chạy và cơ chế weaving thực sự cung cấp.

Bài học tập trung vào câu hỏi: **“Từ bên trong một advice, ta biết điểm can thiệp này là gì, và mô tả nó chính xác đến mức nào?”** Đây là kiến thức nền tảng để làm logging, tracing, kiểm toán kỹ thuật, đo thời lượng và chẩn đoán pointcut.

## 2. Vị trí của dữ liệu join point trong AOP

Các thành phần thường gặp:

| Thành phần | Trách nhiệm | Thông tin liên quan |
|---|---|---|
| **Join point** | Điểm/sự kiện trong luồng chương trình mà mô hình AOP cho phép can thiệp | Loại điểm, phần tử thực thi, ngữ cảnh |
| **Pointcut** | Điều kiện lựa chọn tập join point | Có thể dùng một phần chữ ký và ngữ cảnh để so khớp |
| **Advice** | Hành vi bổ sung chạy tại join point được chọn | Có thể được cung cấp dữ liệu mô tả điểm và dữ liệu runtime |
| **Aspect** | Tổ chức các pointcut và advice của một mối quan tâm xuyên suốt | Nhóm các chính sách quan sát hoặc kiểm soát |
| **Weaving** | Kết hợp advice với chương trình | Quyết định khả năng truy cập dữ liệu tại điểm được hỗ trợ |

**Chữ ký không phải là advice.** Chữ ký mô tả phần tử của chương trình. **Điểm can thiệp không phải pointcut.** Pointcut là điều kiện lựa chọn các điểm đó. Một advice có thể đọc dữ liệu của **join point đã được lựa chọn**, nhưng không được suy rằng nó tự thấy mọi hoạt động tồn tại trong hệ thống.

Một công cụ chỉ hỗ trợ chặn **lời gọi phương thức qua proxy** không tự cung cấp join point của phép gán trường hoặc lời gọi constructor. Không thể yêu cầu “đọc chữ ký của field-set join point” khi cơ chế thực tế không có loại join point ấy.

## 3. Signature là gì?

**Signature** (chữ ký) là thông tin nhận diện cấu trúc của một phần tử chương trình tại một loại join point phù hợp. Với phương thức Java, một mô tả chữ ký có thể chứa:

- Tên phương thức: `submitOrder`.
- Kiểu khai báo: `OrderService`.
- Các kiểu tham số: `String`, `int`.
- Kiểu trả về: `Receipt` hoặc `void`.
- Một số thuộc tính khai báo như modifier, metadata hoặc thông tin kiểu, tùy API.
- Trong một số mô hình, một đối tượng signature có kiểu chuyên biệt: method signature, constructor signature, field signature…

Ví dụ mô tả dành cho người đọc:

~~~text
OrderService.submitOrder(String, int):Receipt
~~~

**Đây là ký pháp trình bày**, không phải biểu thức Java chuẩn hay cú pháp pointcut bắt buộc. Các công cụ AOP có thể định dạng chữ ký khác nhau; một đối tượng signature có thể trả nhiều trường thông tin thay vì chỉ một chuỗi.

### 3.1. Tên và chữ ký không giống nhau

Hai phương thức dưới đây có **cùng tên** nhưng khác danh sách kiểu tham số:

~~~java
void submitOrder(String id);
void submitOrder(String id, int quantity);
~~~

*Đây là hai khai báo minh họa, không phải chương trình Java độc lập.*

Chỉ ghi `submitOrder` vào log sẽ không cho biết overload nào được thực thi. Khi cần phân biệt, nên hiển thị **kiểu khai báo + tên + danh sách kiểu tham số**, và thêm kiểu trả về nếu hữu ích cho việc đọc.

### 3.2. “Chữ ký Java” và “chuỗi mô tả đầy đủ” không hoàn toàn tương đương

Trong quy tắc khai báo/overload của Java, **không thể overload chỉ bằng cách đổi kiểu trả về**. Một chuỗi mô tả để log có thể chứa kiểu trả về, modifier và annotation, dù những trường đó **không nhất thiết thuộc định nghĩa chữ ký dùng cho overload** của ngôn ngữ Java.

Ví dụ:

~~~text
public String find(String id)
~~~

là một mô tả giàu thông tin hơn chỉ `find(String)`. Khi trình bày dữ liệu AOP, hãy phân biệt:

1. **Danh tính/đặc điểm của phần tử khai báo** theo mô hình ngôn ngữ.
2. **Đối tượng metadata** do API/công cụ cung cấp.
3. **Chuỗi diễn giải** mà advice tự tạo để con người dễ đọc.

## 4. Signature khác dữ liệu runtime của một lời gọi

Xét phương thức:

~~~java
String submitOrder(String orderId, int quantity);
~~~

Hai lần thực thi có thể là:

~~~text
Lần 1: submitOrder("A-17", 2)
Lần 2: submitOrder("B-28", 5)
~~~

Ở cùng một phương thức khai báo, **tên và kiểu tham số không đổi**. Nhưng giá trị `orderId`, `quantity` khác nhau.

| Câu hỏi | Dữ liệu cần dùng |
|---|---|
| Đây là phương thức có tên gì? | Signature/metadata |
| Phương thức khai báo ở kiểu nào? | Declaring type của signature |
| Tham số thứ hai được khai báo kiểu nào? | Kiểu tham số trong signature |
| Lần gọi này truyền số lượng mấy? | **Đối số runtime** |
| Đối tượng triển khai thật sự thuộc lớp nào? | **Runtime target/receiver**, nếu công cụ cung cấp |
| Caller đã nhận kết quả nào? | Return value ở advice có ngữ nghĩa phù hợp |
| Ngoại lệ nào vừa được ném ra ngoài điểm này? | Dữ liệu exception ở advice tương ứng |

Một lời gọi có thể dùng cùng chữ ký nhưng **đối số khác**, **đối tượng đích khác**, **trạng thái khác**, hoặc được kích hoạt từ **caller khác**. Không được ghi một chữ ký rồi coi đó là bản sao đầy đủ của sự kiện runtime.

### 4.1. Static metadata và dynamic context

Thông tin chữ ký khai báo thường là **cấu trúc**, có thể được biết trước khi một lần gọi xảy ra. Dữ liệu runtime như đối số thực tế chỉ tồn tại tại lần xảy ra đó.

Tuy nhiên, “cấu trúc” không có nghĩa một cơ chế bắt buộc phân tích ở compile time. Metadata có thể được đọc qua reflection ở runtime hoặc được đưa sẵn vào advice trong quá trình weaving.

## 5. Các loại join point có chữ ký tương ứng khác nhau

Không phải mọi join point đều là thực thi phương thức.

| Loại join point nếu mô hình hỗ trợ | Thông tin mô tả thường hữu ích | Ví dụ |
|---|---|---|
| **Method execution** | Phương thức được thực thi, tên, kiểu khai báo, kiểu tham số/return | `OrderService.submit(String)` |
| **Method call** | Lời gọi được tạo tại một call site, phần tử được gọi | `caller -> service.submit(...)` |
| **Constructor call** | Constructor được yêu cầu ở nơi tạo đối tượng | `new Order(String)` |
| **Constructor execution** | Constructor cụ thể đang thực thi | `Order(String)` |
| **Field get** | Trường được đọc, kiểu khai báo, kiểu dữ liệu | `Order.status:String` |
| **Field set** | Trường được ghi, kiểu khai báo, kiểu dữ liệu | `Order.status:String` |
| **Exception handler** | Loại điểm xử lý ngoại lệ, dữ liệu có thể khác kiểu chữ ký method | Ranh giới xử lý `catch` nếu mô hình có hỗ trợ |

Một mô hình AOP có thể cung cấp **signature của field**, **signature của constructor** hoặc các loại descriptor khác. Không nên ép tất cả vào API method signature.

**Giới hạn quan trọng:** Đó là các **khả năng theo mô hình**, không phải lời hứa mọi hệ AOP đều hỗ trợ toàn bộ các loại join point trên. Khi viết advice, trước tiên phải xem công cụ đang chọn được loại điểm nào, và loại đối tượng mô tả nào được cung cấp ở chính điểm đó.

## 6. Mô tả join point thường gồm những nhóm dữ liệu nào?

Có thể chia theo vai trò:

### 6.1. Kind — loại điểm can thiệp

Ví dụ: method execution, method call, constructor execution, field get/set. Loại điểm quyết định các thuộc tính nào có ý nghĩa.

### 6.2. Signature — phần tử được quan sát

Một method signature có thể chứa tên, declaring type, parameter types, return type và modifier. Một constructor signature thường không có kiểu trả về như một phương thức thông thường. Field signature có tên trường và kiểu của trường.

### 6.3. Source location — vị trí mã nguồn nếu được cung cấp

Một số cơ chế có thể trả file và dòng nguồn liên quan đến join point shadow hoặc call site. Nhưng vị trí này **không phải luôn có**, và số dòng có thể thiếu hoặc thay đổi khi build, generate code, tối ưu hoặc không giữ debug metadata.

### 6.4. Target/this/receiver — đối tượng liên quan

Tùy mô hình, join point có thể cung cấp đối tượng đích, đối tượng đang thực thi hoặc một đối tượng đại diện. Không được giả định các khái niệm đó luôn cùng tham chiếu, nhất là khi dùng proxy hay các loại join point khác nhau.

### 6.5. Arguments — đối số tại lần xảy ra

Danh sách đối số hoặc các binding tương ứng có thể cho biết dữ liệu mà lời gọi mang theo. Giá trị này cần được phân biệt với **kiểu tham số khai báo**.

### 6.6. Return value và exception — dữ liệu sau thực thi

Không phải advice nào cũng có quyền quan sát kết quả. Advice chạy **trước** phần gốc chưa có return value của lần đó. Advice sau hoàn tất bình thường hoặc sau ngoại lệ có thể có dữ liệu khác nhau. Around advice có thể nhận giá trị hoặc lỗi khi continuation/proceed kết thúc.

**Đừng tự giả định một API join point duy nhất luôn có tất cả các trường trên.** Mỗi điểm và mỗi loại advice có thể có hợp đồng dữ liệu riêng.

## 7. Phân biệt method call với method execution khi đọc chữ ký

Một dòng chương trình có thể tạo một lời gọi:

~~~java
service.submitOrder("A-17");
~~~

Trong mô hình phân biệt các loại điểm:

- **Method call join point:** diễn ra ở **vị trí caller yêu cầu gọi**.
- **Method execution join point:** diễn ra khi **phương thức đích được thực thi**.

Cả hai có thể mô tả `submitOrder`, nhưng **ranh giới** khác nhau. Nếu một công cụ hỗ trợ cả hai, advice ở call site và advice ở execution có thể chạy khác thời điểm, khác phạm vi và có thông tin vị trí mã nguồn khác nhau.

Ví dụ phương thức được gọi từ hai nơi:

~~~text
CheckoutScreen.checkout()  ──┐
                             ├──> OrderService.submitOrder(...)
BatchImport.run()        ────┘
~~~

Có hai **vị trí gọi** khác nhau nhưng cùng có thể đi tới một phương thức thực thi ở phía đích. Chữ ký method giống nhau không đủ để nói caller nào đã gọi; cần **call site hoặc ngữ cảnh** tương ứng, nếu mô hình có hỗ trợ.

Vì vậy, advice cần phân biệt:

- **Chữ ký phần tử được gọi**.
- **Vị trí của join point đang được chọn**.
- **Ngữ cảnh thực tế của lần xuất hiện**.

### 7.1. Gọi qua interface và thực thi lớp triển khai

Biến `service` có thể được khai báo kiểu `OrderService`, còn đối tượng thực tế thuộc `OrderServiceImpl`.

Một cơ chế quan sát lời gọi trên **giao diện** có thể cung cấp metadata của method trên interface, không tự động là `Method` của lớp triển khai. Một cơ chế quan sát execution có thể quy định cách lấy method khác.

Đó không phải lỗi của metadata: **hai nguồn mô tả những ranh giới khác nhau**.

## 8. Ví dụ Java 17 hoàn chỉnh: quan sát chữ ký và ngữ cảnh qua proxy

Ví dụ này dùng Java Dynamic Proxy để chứng minh:

1. Lấy `Method` mô tả phương thức được gọi qua giao diện.
2. Đọc tên, declaring type, các kiểu tham số và kiểu trả về.
3. Đọc annotation trên phương thức giao diện.
4. Đọc đối số **của từng lần gọi**.
5. Phân biệt kiểu khai báo của method và lớp thực tế của đối tượng đích.
6. Truyền lời gọi tới phần nghiệp vụ và bảo toàn kết quả.

**Đây là chương trình Java 17 chạy độc lập, dùng proxy để mô phỏng ranh giới can thiệp; không phải một hệ weaving AOP tổng quát.** Java Dynamic Proxy không tự can thiệp vào constructor hay phép gán trường, và không quan sát các lời gọi không đi qua proxy.

Lưu tệp **`JoinPointSignatureDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;
import java.util.stream.Collectors;

public class JoinPointSignatureDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Tracked {}

    public interface Operations {
        @Tracked
        String submit(String orderId, int quantity);
        String preview(String orderId);
    }

    public static final class OperationsImpl implements Operations {
        @Override
        public String submit(String orderId, int quantity) {
            System.out.println("[business] submit " + orderId
                    + " x" + quantity);
            return "receipt:" + orderId + ":" + quantity;
        }

        @Override
        public String preview(String orderId) {
            System.out.println("[business] preview " + orderId);
            return "preview:" + orderId;
        }
    }

    static String signature(Method method) {
        String parameterTypes = Arrays.stream(method.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));
        return method.getDeclaringClass().getSimpleName()
                + "." + method.getName()
                + "(" + parameterTypes + "):"
                + method.getReturnType().getSimpleName();
    }

    static Object callTarget(Method method, Object target, Object[] values)
            throws Throwable {
        try {
            return method.invoke(target, values);
        } catch (InvocationTargetException error) {
            throw error.getCause();
        }
    }

    public static void main(String[] args) {
        Operations target = new OperationsImpl();

        Operations observed = (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[] {Operations.class},
                (proxy, method, values) -> {
                    System.out.println("[point] " + signature(method));
                    System.out.println("[metadata] declaring="
                            + method.getDeclaringClass().getSimpleName()
                            + ", target=" + target.getClass().getSimpleName()
                            + ", tagged="
                            + method.isAnnotationPresent(Tracked.class));
                    System.out.println("[runtime] args="
                            + Arrays.toString(values));

                    Object result = callTarget(method, target, values);
                    System.out.println("[return] " + result);
                    return result;
                }
        );

        System.out.println("[caller] " + observed.submit("A-7", 2));
        System.out.println("[caller] " + observed.preview("B-8"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac JoinPointSignatureDemo.java
java JoinPointSignatureDemo
~~~

**Stdout chính xác:**

~~~text
[point] Operations.submit(String,int):String
[metadata] declaring=Operations, target=OperationsImpl, tagged=true
[runtime] args=[A-7, 2]
[business] submit A-7 x2
[return] receipt:A-7:2
[caller] receipt:A-7:2
[point] Operations.preview(String):String
[metadata] declaring=Operations, target=OperationsImpl, tagged=false
[runtime] args=[B-8]
[business] preview B-8
[return] preview:B-8
[caller] preview:B-8
~~~

### 8.1. Vì sao chữ ký có `Operations`, không phải `OperationsImpl`?

Đối tượng `Method` trong lời gọi proxy giao diện mô tả **phương thức được khai báo trên giao diện**. Do đó:

~~~text
method.getDeclaringClass().getSimpleName() → Operations
target.getClass().getSimpleName()          → OperationsImpl
~~~

Cả hai kết quả đều đúng nhưng trả lời **hai câu hỏi khác nhau**. Đó là lý do không nên mặc định dùng `method.getDeclaringClass()` để kết luận runtime target class.

### 8.2. Vì sao giá trị tagged khác nhau?

`submit` được đánh dấu `@Tracked` trên giao diện, còn `preview` không có dấu hiệu đó. `@Retention(RUNTIME)` cho phép reflection quan sát annotation vào lúc chạy. Nếu đặt annotation **chỉ trên phương thức triển khai** mà handler vẫn nhận `Method` của giao diện, `method.isAnnotationPresent(...)` có thể không trả cùng kết quả.

Một cơ chế AOP khác có thể định nghĩa quy tắc lookup annotation riêng, vì thế phải xem **phần tử nào** đang được dùng làm metadata source.

### 8.3. `Arrays.toString(values)` có ý nghĩa gì?

`values` chứa đối số thực tế tại **lần gọi hiện tại**; đối số `int` đi qua cơ chế phản chiếu dưới dạng đối tượng boxed phù hợp, nên in ra `2`. Đó là dữ liệu runtime, không phải kiểu tham số `int` trong signature.

Trong chương trình thật, **không nên tự in mọi đối số**: có thể chứa mật khẩu, token, dữ liệu cá nhân, nội dung lớn hoặc đối tượng mà `toString()` tốn chi phí/gây tác dụng phụ. Ví dụ in đối số chỉ nhằm minh họa cấu trúc.

### 8.4. Kết quả trả về được xử lý ra sao?

Handler gọi phương thức đích rồi nhận giá trị. `callTarget` giải gói `InvocationTargetException` để trả lại nguyên nhân lỗi do method đích ném, nếu có. Ở hai lời gọi minh họa đều không có lỗi, nên handler in `[return]` và trả kết quả.

Nếu method đích **ném ngoại lệ**, dòng `[return]` ở phiên bản này sẽ không xuất hiện; muốn ghi nhận đường lỗi cần `catch` hoặc `finally` thích hợp. **Khả năng đọc chữ ký không phụ thuộc việc phương thức thành công**, nhưng dữ liệu kết quả chỉ có nếu ranh giới thực thi thực sự hoàn tất bình thường.

### 8.5. Giới hạn phạm vi của ví dụ

Java Dynamic Proxy chặn những lời gọi **đi qua đối tượng `observed`**, không tự chặn mọi lời gọi lên `target` hay những lời gọi nội bộ trên target. Ví dụ vì thế minh họa API metadata và dữ liệu runtime, **không chứng minh một công cụ AOP nào có thể truy cập mọi loại join point**.

## 9. Ví dụ thứ hai: phương thức, constructor và field có dạng mô tả khác nhau

Khi mô hình AOP hỗ trợ các loại join point khác ngoài phương thức, khái niệm signature cũng thay đổi tương ứng. Java Reflection có các phần tử `Method`, `Constructor` và `Field`; chúng là **nguồn metadata Java**, không tự động là đối tượng join point của một engine AOP.

Lưu tệp **`SignatureKindsDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

public class SignatureKindsDemo {
    static final class Ledger {
        private final String code;

        Ledger(String code) {
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    static String parameters(Class<?>[] types) {
        return Arrays.stream(types)
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) throws Exception {
        Constructor<Ledger> constructor =
                Ledger.class.getDeclaredConstructor(String.class);
        Method method = Ledger.class.getDeclaredMethod("code");
        Field field = Ledger.class.getDeclaredField("code");

        System.out.println("constructor="
                + constructor.getDeclaringClass().getSimpleName()
                + "(" + parameters(constructor.getParameterTypes()) + ")");

        System.out.println("method="
                + method.getDeclaringClass().getSimpleName()
                + "." + method.getName()
                + "(" + parameters(method.getParameterTypes()) + "):"
                + method.getReturnType().getSimpleName());

        System.out.println("field="
                + field.getDeclaringClass().getSimpleName()
                + "." + field.getName()
                + ":" + field.getType().getSimpleName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SignatureKindsDemo.java
java SignatureKindsDemo
~~~

**Stdout chính xác:**

~~~text
constructor=Ledger(String)
method=Ledger.code():String
field=Ledger.code:String
~~~

Ở đây constructor được mô tả bằng tên lớp và tham số, method bằng tên/tham số/kiểu trả về, field bằng tên/kiểu trường. Việc Java Reflection có thể đọc metadata **không đồng nghĩa** một công cụ AOP có thể gắn advice vào mọi constructor hoặc field access.

Muốn từ metadata tới một sự kiện AOP, cần có **mô hình join point hỗ trợ loại điểm**, pointcut lựa chọn và cơ chế weaving xử lý đúng nơi.

## 10. Các mức chi tiết khi in chữ ký

Một advice có thể muốn log:

~~~text
submit
submit(String,int)
Operations.submit(String,int)
Operations.submit(String,int):String
public abstract Operations.submit(String,int):String
~~~

Mỗi dòng có độ phân biệt và độ dài khác nhau. Chọn mức chi tiết theo mục đích:

- **Log ngắn:** chỉ tên hoặc tên + kiểu khai báo nếu không có nguy cơ trùng.
- **Chẩn đoán overload:** cần danh sách **kiểu tham số**.
- **Phân tích API/kiểu:** thêm kiểu trả về, modifier hoặc metadata đặc biệt.
- **Định danh ổn định hơn:** có thể cần tên kiểu đầy đủ (fully qualified name), cùng thông tin module/class loader khi thực sự có xung đột.
- **Đo hiệu năng:** tránh dựng chuỗi dài, đọc annotation lặp hoặc serialize mọi đối số ở đường thực thi tần suất cao.

Một chuỗi `toString()` của đối tượng join point có thể dễ đọc nhưng **không nhất thiết là định dạng ổn định để parse**. Nếu cần hệ thống theo dõi tự động, nên lấy **các trường cấu trúc riêng** mà API cung cấp, rồi tự định nghĩa schema thống nhất.

## 11. Tên kiểu đơn giản và tên kiểu đầy đủ

Trong Java:

- `Class.getSimpleName()` trả tên dạng ngắn, ví dụ `String`.
- `Class.getName()` hoặc `getTypeName()` thường chứa mô tả đầy đủ hơn theo API, ví dụ `java.lang.String`.
- Tên của **array**, **kiểu lồng**, **kiểu ẩn danh**, **kiểu sinh tự động**, **generic** và **kiểu bị erasure** có những khác biệt cần cân nhắc.

Ví dụ `String` và `java.lang.String` có thể là hai cách hiển thị cùng một kiểu. Nhưng hai lớp thuộc các package khác nhau đều có thể có simple name `Service`, nên định dạng chỉ dùng simple name dễ gây nhầm.

**Một identifier dễ đọc không đương nhiên là identifier toàn cục.** Trong hệ thống lớn có nhiều module, class loader hoặc mã sinh, nên thiết kế khóa định danh join point một cách rõ ràng thay vì dùng một chuỗi ngắn làm khóa duy nhất.

## 12. Tham số khai báo, tên tham số và giá trị đối số

Ba loại dữ liệu khác nhau:

| Dữ liệu | Ví dụ | Nguồn |
|---|---|---|
| **Kiểu tham số** | `String, int` | Chữ ký khai báo |
| **Tên tham số** | `orderId, quantity` | Metadata khai báo nếu được giữ và truy cập được |
| **Giá trị đối số thực tế** | `"A-7", 2` | Ngữ cảnh runtime của lần gọi |

Trong Java Reflection, `Method.getParameterTypes()` cung cấp kiểu tham số ở dạng `Class<?>[]`, còn `Method.getParameters()` cho thông tin `Parameter`. **Tên tham số gốc** không luôn được lưu ở dạng có thể đọc: với mã biên dịch bằng `javac -parameters`, reflection có thể thấy tên khai báo; nếu thiếu metadata đó, API có thể hiển thị tên tổng hợp như `arg0`.

Vì vậy không được xây chính sách quan trọng dựa trên việc tên tham số tự động luôn là `orderId`. Khi cần bind dữ liệu theo tham số, phải xem ngôn ngữ/công cụ AOP dùng **vị trí, tên, kiểu hoặc cơ chế binding** nào và biên dịch yêu cầu metadata gì.

### 12.1. Varargs và mảng

Một phương thức khai báo `log(String... tags)` thường được biểu diễn ở cấp bytecode/reflection bằng tham số mảng `String[]`. Khi tạo mô tả cho người đọc, cần quyết định hiển thị `String...` hay `String[]`, dựa trên cờ varargs và API có sẵn.

Không nên coi hai chuỗi hiển thị khác nhau đó là bằng chứng hai phương thức khai báo độc lập.

## 13. Generic, type erasure và bridge method

Một chữ ký ở mã nguồn có thể chứa `List<String>`, `T` hoặc generic bound; còn kiểu tham số trong bytecode thường chịu **type erasure**.

Ví dụ khai báo:

~~~java
void send(java.util.List<String> items);
~~~

Đây là khai báo minh họa. Nếu chỉ gọi `Method.getParameterTypes()`, kiểu tham số có thể được nhìn thấy là `java.util.List`. Muốn đọc metadata generic khai báo, reflection có các API như `getGenericParameterTypes()`, nhưng không phải mọi thông tin generic của đối tượng runtime đều còn tồn tại.

**Trong Java không thể khai báo hai overload chỉ khác `List<String>` so với `List<Integer>`** trên cùng kiểu theo cách khiến hai method có cùng erasure. Vì vậy, một định danh AOP dựa trên chữ ký runtime không được tự suy rằng parameterized type arguments luôn giúp phân biệt overload.

Khi Java compiler tạo **bridge method** để phục vụ tính tương thích đa hình với generic/covariant return, reflection có thể thấy các phương thức có cờ `isBridge()` hoặc `isSynthetic()`. Nếu một công cụ AOP quan sát các method-level join point ở bytecode, cần tìm hiểu nó xử lý bridge/synthetic method ra sao để tránh đếm trùng hoặc hiểu sai điểm gốc.

Không nên tự dùng tên phương thức đơn giản làm điều kiện duy nhất trong hệ có generic và các lớp triển khai phức tạp.

## 14. Annotation là dữ liệu mô tả nhưng nơi khai báo rất quan trọng

Một annotation có thể xuất hiện ở:

- Kiểu/lớp.
- Phương thức của giao diện.
- Phương thức triển khai.
- Constructor.
- Field hoặc tham số.
- Một phần tử khác theo `@Target`.

Từ góc độ advice, câu hỏi không chỉ là “có annotation này không?” mà còn là:

> **Annotation đang được tra cứu trên chính phần tử nào?**

Ví dụ một method trên interface có `@Tracked`, nhưng method triển khai không được ghi annotation đó. Java Reflection trên `Method` của lớp triển khai không tự có nghĩa kết quả giống method trên interface. Một cơ chế AOP có thể có quy tắc kết hợp hoặc tra cứu metadata riêng; cần nêu rõ.

**Retention** cũng ảnh hưởng khả năng đọc metadata. Annotation phục vụ compile time không nhất thiết tồn tại cho `isAnnotationPresent` khi chạy. Một bộ phân tích mã/bytecode có thể có nguồn dữ liệu khác reflection runtime.

### 14.1. Không gộp annotation của class với annotation của method

Một annotation trên class không tự đồng nghĩa mọi method đều trực tiếp mang annotation ấy. Nếu chính sách pointcut muốn chọn mọi method thuộc một class được đánh dấu, cần biểu thức phù hợp với **metadata của class**, không chỉ kiểm tra method annotation.

## 15. Modifier và khả năng truy cập

Metadata có thể mô tả `public`, `private`, `static`, `final`, `abstract` hoặc các thuộc tính khác, nhưng không phải mọi modifier đều có cùng ý nghĩa với mọi loại phần tử.

Ví dụ:

- Một constructor không được override như instance method.
- Một static method không được dispatch đa hình như instance method.
- Một field có modifier final không nói được điểm field-read có được weaving hay không.
- Một phương thức private có thể không chặn được bằng một cơ chế subclass override, nhưng một cơ chế weaving trực tiếp mã có thể có khả năng khác.

**Đọc được chữ ký không đồng nghĩa chặn được hành vi.** Java Reflection có thể trả `Method` cho một private method, nhưng một công cụ AOP dùng proxy giao diện không tự nhiên can thiệp vào mọi lần private method thực thi.

Tương tự, khả năng dùng reflection để **truy cập/invoke** một phần tử và khả năng chỉ **đọc metadata** là những quyền khác nhau, có thể chịu ràng buộc module/access của Java.

## 16. Source location: hữu ích nhưng không phải luôn đáng tin làm khóa định danh

Một số mô hình join point cho phép lấy file nguồn, dòng hoặc vị trí gần điểm can thiệp. Điều này hữu ích khi chẩn đoán:

~~~text
point: method call
called member: OrderService.submit(String)
source: CheckoutScreen.java, line 87
~~~

Đây chỉ là **ví dụ định dạng**, không phải một kết quả có thật được đo từ chương trình.

Cần lưu ý:

1. Không phải mọi điểm đều có thông tin file/line.
2. Mã bytecode có thể được tạo từ nhiều nguồn; debug metadata có thể bị bỏ.
3. Refactor hoặc chèn dòng có thể thay đổi số dòng mà ngữ nghĩa nghiệp vụ không đổi.
4. Cùng một phương thức có thể được gọi tại nhiều call site, nhưng execution join point không nhất thiết cung cấp caller source location.
5. Class loader, mã generate và optimization có thể ảnh hưởng dữ liệu mà công cụ báo.

Không nên dùng **số dòng mã nguồn** làm khóa duy nhất cho sự kiện kiểm toán lâu dài. Nó thích hợp để điều tra, không phải danh tính nghiệp vụ bền vững.

## 17. Static part và dynamic context của join point

Trong một số mô hình AOP, đối tượng join point có thể có phần mô tả **tĩnh** (*static part*) và ngữ cảnh động của **lần thực thi**.

Mô hình tư duy:

~~~text
STATIC PART
    kind
    signature
    source location (nếu có)
    thông tin cấu trúc khác
          |
          | được dùng tại nhiều lần xuất hiện
          v
DYNAMIC JOIN POINT OCCURRENCE
    đối tượng hiện tại / đối tượng đích
    đối số cụ thể
    ngữ cảnh lời gọi
    kết quả / ngoại lệ nếu phù hợp với loại advice
~~~

Ví dụ một method execution có cùng chữ ký xuất hiện 10.000 lần. Bộ máy có thể tái sử dụng phần metadata tĩnh và đưa dữ liệu động cho từng lần xảy ra. Nhưng **không được tự suy rằng mọi API AOP đều công khai một kiểu `StaticPart` hoặc có cùng chiến lược cache**.

### 17.1. Điều kiện tĩnh không có nghĩa runtime không cần xử lý

Một bộ máy có thể phân tích chữ ký trước rồi tạo code can thiệp. Một proxy đơn giản có thể kiểm tra method qua reflection khi được gọi. Hai cách đều có thể dùng **thông tin cấu trúc**.

Đừng nhầm **loại thông tin** với **thời điểm công cụ tính ra thông tin đó**.

## 18. Tên join point không đồng nghĩa ngữ nghĩa nghiệp vụ

Một method tên `save()` có thể:

- Lưu bản nháp.
- Lưu giao dịch đã được xác nhận.
- Lưu một bản ghi chẩn đoán.
- Gửi một yêu cầu tới hệ thống ngoài mà chưa bảo đảm kết quả cuối.

Nếu advice quyết định chính sách chỉ theo tên `save`, nó có thể bao phủ quá rộng. **Signature mô tả cấu trúc**, không bảo đảm ý nghĩa nghiệp vụ hoặc trạng thái kết quả.

Khi cần phân biệt “đã lưu thành công”, advice thường phải căn cứ vào hợp đồng trả về, ngoại lệ, điểm commit hoặc sự kiện có ngữ nghĩa phù hợp. Dữ liệu runtime có thể mang những thông tin đó, nhưng vẫn phải chọn đúng ranh giới quan sát.

**Ví dụ:** `processAsync()` trả về một `Future` bình thường. Chữ ký có kiểu trả về `Future`, còn công việc thực sự có thể thất bại vài giây sau. Advice đọc chữ ký và thấy phương thức trả về không đồng nghĩa “công việc đã hoàn tất”.

## 19. Rủi ro khi ghi đối số và kết quả thô vào log

Lấy được dữ liệu join point chỉ là khả năng kỹ thuật, **không có nghĩa luôn nên ghi ra**.

Những rủi ro:

- Dữ liệu nhạy cảm: thông tin khách hàng, token, bí mật, tài khoản, dữ liệu sức khỏe.
- Đối tượng lớn hoặc đệ quy: in toàn bộ object graph gây tốn tài nguyên hoặc lỗi stack.
- `toString()` có tác dụng phụ hoặc chi phí lớn.
- Dữ liệu đồng thời thay đổi: chuỗi log có thể không mô tả một snapshot nhất quán.
- Số lượng log quá cao tại hot path.
- Tên loại hoặc chữ ký nội bộ có thể không nên lộ ra bên ngoài ranh giới tin cậy.

Cách làm phù hợp:

1. Ưu tiên **metadata cấu trúc** cần thiết như operation name và loại join point.
2. Định nghĩa danh sách giá trị được phép ghi, masking/redaction và giới hạn kích thước.
3. Chỉ ghi dữ liệu runtime đúng mục đích, tránh serialize tùy tiện.
4. Tách log kỹ thuật khỏi quyết định nghiệp vụ/kiểm soát quyền.
5. Bảo đảm lỗi của logger không vô tình thay đổi giá trị trả về hoặc che ngoại lệ gốc nếu quan sát được kỳ vọng là best-effort.

## 20. Metadata, performance và cache đúng cách

Chữ ký của một `Method` không đổi vì đối số `"A-7"` hay `"B-8"`. Vì vậy có thể cân nhắc **cache phép định dạng chữ ký** theo một khóa metadata phù hợp, trong phạm vi vòng đời và class loader đúng.

Nhưng **đối số, receiver và kết quả** thay đổi theo từng lần gọi, không nên dùng một cache chỉ dựa trên tên method để lưu chúng.

Ví dụ chiến lược:

~~~text
Ở giai đoạn chuẩn bị / khi gặp method đầu tiên:
    xây chuỗi mô tả signature
    cache theo định danh Method thích hợp

Ở mỗi lần join point xuất hiện:
    lấy signature có sẵn
    đọc đối số thực tế lần này
    thực hiện advice theo chính sách
~~~

Đây là pseudocode, không phải thuật toán bắt buộc. Trong chương trình có **nhiều class loader hoặc hot reload**, cache có thể cần chính sách vòng đời để tránh giữ tham chiếu class mãi mãi.

**Tránh tối ưu sớm:** việc dùng cache phải được đo đạc, không nên thêm độ phức tạp nếu chi phí chính đến từ I/O logging, serialization hoặc truy vấn trạng thái.

## 21. Phân biệt thông tin ở before, after và around advice

| Loại advice | Có thể mong đợi thông tin nào? | Không nên giả định |
|---|---|---|
| **Before** | Metadata của join point và ngữ cảnh đầu vào nếu có | Đã biết kết quả trả về của hoạt động chưa chạy |
| **After-returning** | Metadata và kết quả hoàn tất bình thường nếu cơ chế cung cấp | Mọi lần trả bình thường đều thành công nghiệp vụ |
| **After-throwing** | Metadata và ngoại lệ đi ra khỏi ranh giới nếu cơ chế cung cấp | Mọi ngoại lệ được bắt trong phương thức đều đi ra |
| **After/finally** | Metadata và thông tin kết thúc theo semantics của công cụ | Luôn có cả return value lẫn exception trong một lần thoát |
| **Around** | Metadata, ngữ cảnh khi vào, kết quả/ngoại lệ từ continuation nếu gọi tiếp | `proceed` luôn gọi thẳng phần gốc hoặc luôn chỉ được gọi một lần |

Một số cơ chế cấp quyền truy cập đối tượng join point trong advice qua tham số ràng buộc; một số có một context object hay API khác. Không thể suy ra cú pháp chỉ từ khái niệm AOP.

### 21.1. Proceed và dữ liệu join point

Trong around advice, `proceed` hoặc continuation tương đương biểu diễn **phần thực thi tiếp theo trong chuỗi**. Nó có thể đi qua advice khác trước khi tới phần gốc. Nếu around advice không gọi tiếp, dữ liệu return/exception mà caller thấy có thể phản ánh **kết quả thay thế**, không phải kết quả nghiệp vụ gốc.

Nếu cơ chế cho phép thay đối số khi tiếp tục, cần phân biệt **đối số tại điểm vào**, **đối số được truyền xuống** và **đối số advice phía trong nhìn thấy**. Không có hợp đồng chung cho tất cả công cụ.

## 22. Điểm cần cẩn thận với nhiều aspect

Nếu hai aspect cùng quan sát một join point, chúng có thể cùng đọc signature và đối số, nhưng:

- Thứ tự chạy có thể khác nhau.
- Around advice phía ngoài có thể short-circuit, khiến phần gốc hoặc advice phía trong không chạy.
- Around advice có thể thay return value hoặc exception theo chính sách.
- Điều kiện động có thể thay đổi tập điểm được chọn từng lần.
- Mã nghiệp vụ có thể hoàn tất bình thường nhưng trạng thái nghiệp vụ thất bại.

**Một metadata signature giống nhau không bảo đảm hai advice cùng thấy một sự kiện có cùng kết quả cuối.** Phải nêu rõ ranh giới và thứ tự advice khi diễn giải log.

## 23. Những lỗi phổ biến khi truy cập signature/join point

### 23.1. Chỉ in tên mà bỏ kiểu khai báo và tham số

Rủi ro: log `submit` không phân biệt hai overload hoặc hai lớp khác nhau.

**Khắc phục:** định nghĩa định dạng gồm đủ các trường cần để phân biệt.

### 23.2. Đồng nhất declaring type với runtime target

Rủi ro: metadata lấy từ interface `Operations` nhưng lại ghi “đối tượng thực thi là Operations”.

**Khắc phục:** đọc đúng trường **declaring type** và trường **đối tượng runtime** riêng biệt, nếu công cụ có cung cấp.

### 23.3. Coi giá trị đối số là một phần cố định của signature

Rủi ro: dùng cùng chữ ký `pay(String,int)` để suy mọi lời gọi đều là VIP hoặc đều có số tiền giống nhau.

**Khắc phục:** phân biệt metadata tĩnh với ngữ cảnh từng lần thực thi.

### 23.4. Coi string từ `toString()` là hợp đồng API

Rủi ro: định dạng thay đổi theo phiên bản hoặc mô hình; parser log bị lỗi.

**Khắc phục:** truy cập trường có cấu trúc, tạo schema/log format riêng.

### 23.5. Tưởng Method của interface có mọi annotation ở implementation

Rủi ro: đọc annotation không đúng nguồn và loại nhầm join point.

**Khắc phục:** xác định rõ phần tử metadata; kiểm tra quy tắc lookup của cơ chế đang dùng.

### 23.6. Cho rằng reflection đọc được nghĩa là AOP chặn được

Rủi ro: đọc được `Field` hoặc constructor qua Reflection rồi kết luận tool proxy hiện tại hỗ trợ field/constructor join point.

**Khắc phục:** kiểm tra join point model, pointcut, weaving scope và runtime path.

### 23.7. Đọc source location như một định danh ổn định

Rủi ro: sửa file, biên dịch lại hoặc bỏ debug info khiến file/line thay đổi.

**Khắc phục:** dùng source location cho chẩn đoán, không làm khóa nghiệp vụ duy nhất.

### 23.8. Ghi toàn bộ arguments/return value

Rủi ro: rò rỉ dữ liệu nhạy cảm, tạo log khổng lồ, `toString` có tác dụng phụ.

**Khắc phục:** redaction, whitelist, giới hạn độ dài và kiểm tra tác động hiệu năng.

### 23.9. Lấy thời điểm method return làm thời điểm hoàn tất toàn bộ async task

Rủi ro: advice ghi `SUCCESS` khi thực chất mới nhận một handle tới công việc đang chạy.

**Khắc phục:** quan sát đúng sự kiện hoàn tất của tác vụ nếu đó mới là mục tiêu.

### 23.10. Dùng dữ liệu metadata để thay kiểm tra quyền

Rủi ro: suy rằng phương thức có tên `authorized*` nghĩa là người dùng đã được phân quyền.

**Khắc phục:** chính sách an toàn phải dựa trên ranh giới đáng tin cậy và dữ liệu quyền thực tế; signature chỉ hỗ trợ nhận diện thao tác.

## 24. Quy trình thực hành khi thiết kế advice đọc chữ ký

1. **Xác định mục đích:** logging, audit, metrics hay chẩn đoán pointcut?
2. **Chọn loại join point:** method call, execution, constructor, field…; kiểm tra mô hình có hỗ trợ không.
3. **Liệt kê metadata cần thiết:** kind, declaring type, member name, parameter types, return type, annotation, location nếu có.
4. **Liệt kê ngữ cảnh động cần thiết:** receiver/target, đối số, kết quả/exception, correlation ID.
5. **Xác định thời điểm có dữ liệu:** before, returning, throwing, finally hay around?
6. **Xác định nguồn metadata:** interface, implementation, call site hay đối tượng signature chuyên biệt?
7. **Thiết kế định dạng:** ưu tiên trường có cấu trúc, ổn định và tránh phụ thuộc chuỗi mặc định.
8. **Thiết kế xử lý dữ liệu nhạy cảm:** không in thô mọi đối số; giới hạn độ dài và masking.
9. **Kiểm thử overload/generic/proxy:** các điểm giống tên nhưng khác kiểu có được phân biệt?
10. **Kiểm thử nhánh thành công/lỗi:** có bảo toàn return/exception và không làm thay đổi nghiệp vụ?
11. **Kiểm thử phạm vi can thiệp:** method gọi qua proxy hay gọi trực tiếp, điểm có thuộc phạm vi weaving không?
12. **Đo chi phí:** cache metadata cấu trúc nếu cần; không cache giá trị runtime như dữ liệu cố định.
13. **Tài liệu hóa giới hạn:** dữ liệu nào được hỗ trợ, dữ liệu nào không thể lấy ở mô hình hiện tại.

Một advice tốt không chỉ “in được tên phương thức”; nó **biết tên đó phản ánh ranh giới nào, có thể tin cậy đến mức nào và những dữ liệu runtime nào không được phép suy ra từ chữ ký**.

## 25. Bài tập tự kiểm tra

### Bài 1. Tên và chữ ký

Hai phương thức `send(String)` và `send(String,int)` có cùng tên. Nếu log chỉ in `send`, thiếu dữ liệu gì để phân biệt overload?

**Đáp án:** cần danh sách **kiểu tham số khai báo** (và thường thêm kiểu khai báo để phân biệt các lớp). Kiểu trả về có thể hữu ích khi mô tả nhưng không phải căn cứ overload chỉ dựa vào return type.

### Bài 2. Giao diện và lớp đích

Advice dùng proxy giao diện lấy `method.getDeclaringClass().getSimpleName()` bằng `Operations`; đối tượng đích là `OperationsImpl`. Hai giá trị có mâu thuẫn không?

**Đáp án:** không. Một giá trị mô tả **nơi phương thức phản chiếu được khai báo**, giá trị kia là **lớp của đối tượng runtime**.

### Bài 3. Static versus dynamic

Cùng method `pay(String,int)` được gọi `pay("VIP",120)` rồi `pay("NORMAL",120)`. Dữ liệu nào có thể dùng lại giữa hai lần?

**Đáp án:** tên, declaring type, kiểu tham số và return type có thể giống nhau; **giá trị tier** khác, phải đọc tại mỗi lần gọi nếu chính sách phụ thuộc nó.

### Bài 4. Metadata của annotation

Annotation nằm trên method implementation, nhưng advice kiểm tra `Method` của interface. Có thể kết luận annotation chắc chắn hiện diện không?

**Đáp án:** không. Phải xác định phần tử được tra cứu và quy tắc metadata lookup; reflection trên method interface không tự kế thừa mọi annotation của method triển khai.

### Bài 5. Generic signature

`getParameterTypes()` đối với một tham số khai báo `List<String>` có nhất thiết trả một kiểu runtime độc lập tên `List<String>` không?

**Đáp án:** không. Type erasure và API reflection ảnh hưởng cách biểu diễn; `getGenericParameterTypes()` có thể đọc metadata generic khai báo khi còn lưu, nhưng không biến type argument thành kiểu runtime phân biệt overload.

### Bài 6. Constructor và field

Java Reflection tìm được `Constructor` và `Field`. Có được kết luận một công cụ AOP hiện tại chặn mọi constructor execution và field set không?

**Đáp án:** không. Khả năng đọc metadata Java khác với hỗ trợ **loại join point** và **weaving scope** của công cụ AOP.

### Bài 7. Source location

Một điểm can thiệp hôm nay được ghi ở dòng 87, mai refactor thành dòng 95. Điều đó có chắc là hai hoạt động nghiệp vụ khác nhau?

**Đáp án:** không. Dòng nguồn hữu ích cho chẩn đoán, nhưng không phải khóa định danh ngữ nghĩa ổn định.

### Bài 8. Ngoại lệ

Advice chạy trước method `submit`. Nó có thể biết trước ngoại lệ thực tế mà method sẽ ném ra sau đó chỉ bằng cách đọc chữ ký `throws` không?

**Đáp án:** không. Danh sách kiểu ngoại lệ **được khai báo** (nếu có) là metadata; ngoại lệ **thực tế xảy ra** của một lần thực thi chỉ biết khi đường lỗi phát sinh và được quan sát.

### Bài 9. Kết quả async

Một method có signature trả `CompletionStage<Result>`. Advice đọc chữ ký và thấy method return bình thường. Có thể ghi “công việc cuối cùng thành công” không?

**Đáp án:** không. Return của phương thức và việc tác vụ bất đồng bộ hoàn tất là hai mốc khác nhau; cần quan sát kết quả hoàn tất đúng ranh giới.

### Bài 10. Dữ liệu log

Tại sao in `Arrays.toString(args)` cho mọi advice không phải chính sách production an toàn?

**Đáp án:** đối số có thể chứa dữ liệu nhạy cảm, lớn hoặc object có `toString()` gây tác dụng phụ. Cần chọn trường được phép ghi, masking, giới hạn kích thước và đo chi phí.

## 26. Tổng kết

- **Signature** mô tả **phần tử khai báo hoặc ranh giới cấu trúc** liên quan đến join point: tên, declaring type, các kiểu tham số, kiểu trả về và metadata khác khi mô hình cung cấp.
- **Mô tả join point** có thể rộng hơn signature, gồm loại điểm, vị trí mã, target/receiver, đối số và ngữ cảnh liên quan.
- **Đối số, đối tượng, kết quả và ngoại lệ thực tế** là thông tin của **một lần thực thi**, không phải đặc điểm bất biến của chữ ký.
- **Method call và method execution** có thể mang cùng member name nhưng là **hai ranh giới khác nhau**; thông tin call site không tự được suy ra từ execution signature.
- Java Reflection cho phép đọc **Method/Constructor/Field**, nhưng đọc được metadata **không đồng nghĩa một công cụ AOP chặn được tất cả loại join point**.
- Cần chú ý interface so với implementation, overload, annotation retention, generic erasure, bridge method, varargs, modifier và source location.
- Khi đưa metadata vào advice, phải thiết kế định dạng log ổn định, kiểm soát dữ liệu nhạy cảm và chi phí; không suy trạng thái nghiệp vụ từ tên method.
- **Pointcut, loại join point, weaving và runtime path** vẫn quyết định dữ liệu nào có thể được quan sát ở một điểm thực tế.

**Câu hỏi kiểm tra quan trọng nhất:** *“Thông tin này mô tả phần tử chương trình, vị trí join point, hay giá trị của lần thực thi hiện tại — và cơ chế AOP có thực sự cung cấp nó tại ranh giới mà tôi đã chọn không?”*
