# Pointcut mong manh khi đổi tên, di chuyển hoặc nạp chồng phương thức trong AOP

## 1. Vấn đề cần nhận diện

**Aspect-Oriented Programming (AOP)** dùng **pointcut** để chọn những **join point** mà advice sẽ chạy. Khi một ứng dụng được refactor, tên phương thức, tên lớp, package, interface, danh sách tham số và đường gọi thường thay đổi. Nếu pointcut dựa chặt vào các chi tiết này, mã nghiệp vụ vẫn biên dịch và chạy bình thường nhưng hành vi xuyên suốt (logging, transaction, kiểm tra quyền, retry, giám sát) có thể **im lặng biến mất** hoặc **áp nhầm vào lời gọi khác**.

Ví dụ một bộ ghi audit ban đầu chặn thao tác `OrderService.submit(String)`. Sau đó nhóm phát triển:

- Đổi tên `submit(String)` thành `place(String)` để đúng ngôn ngữ nghiệp vụ.
- Chuyển interface từ package cũ sang package mới.
- Thêm overload `submit(int)` để tra cứu đơn theo mã số.
- Giữ nguyên một biểu thức pointcut `execution(* *.submit(..))`.

Khi đó lời gọi tạo đơn có thể không được audit, còn overload chỉ để đọc lại bị instrument nhầm. Nếu advice dùng để phân quyền hoặc quản lý transaction, hậu quả không chỉ là một dòng log thiếu: đó có thể là sai chính sách thực thi.

Bài này giúp bạn:

1. Hiểu selector theo tên, package, type, chữ ký, modifier và annotation có thể đổi nghĩa thế nào sau refactor.
2. Phân biệt **false negative** (bỏ sót join point phải được chặn) và **false positive** (chặn thừa join point không thuộc chính sách).
3. Thiết kế pointcut theo **hợp đồng ngữ nghĩa** và đường thực thi thật, đồng thời kiểm soát sự dịch chuyển của hợp đồng.
4. Xử lý overload, override, generic bridge method, inheritance, proxy và weaving theo đúng mô hình công cụ.
5. Kiểm thử **phạm vi chọn join point** và **việc advice thực sự chạy**, gồm cả đường gọi trực tiếp, self-invocation, callback và interface.
6. Thực hành với ví dụ Java 17 có thể biên dịch và chạy để thấy lỗi của pointcut phụ thuộc tên/lớp và cách khắc phục bằng metadata nghiệp vụ.

Trọng tâm là **AOP tổng quát**. Các biểu thức như `execution(...)` dưới đây minh họa một họ cú pháp pointcut thường gặp; không giả định mọi thư viện/interceptor đều hỗ trợ cùng ngữ pháp.

## 2. Pointcut không phải là tên hàm

Ba khái niệm cần tách rõ:

- **Join point:** sự kiện/vị trí có thể bị quan sát: thực thi method, gọi method, truy cập field, xây dựng object… Tập khả dụng tùy công cụ weaving/interception.
- **Pointcut:** vị từ chọn join point dựa trên thuộc tính của chúng; nó có thể xét tên, chữ ký, type, annotation, phạm vi lexical, đối tượng runtime hoặc điều kiện khác.
- **Advice:** hành vi được kích hoạt cho các join point được pointcut chọn, chẳng hạn ghi audit, đo duration, kiểm tra quyền hoặc áp retry.

Một selector minh họa:

```text
execution(* example.orders.OldOrderService.submit(..))
```

Ý tưởng là chọn *execution join point* của method tên `submit` trong một type cụ thể. Ngay khi type được di chuyển hoặc method đổi tên, tập join point được chọn có thể trở thành rỗng. Ngay cả khi tập này không rỗng, selector không tự chứng minh lời gọi nghiệp vụ mong muốn thực sự đi qua nó.

**Biên dịch thành công không chứng minh pointcut còn đúng.** Một biểu thức pointcut đặt trong string/config có thể không được compiler Java refactor cùng với biểu tượng method, và một số cơ chế chỉ xác minh selector khi khởi động hoặc khi join point xuất hiện.

## 3. Thế nào là pointcut “mong manh”?

Đặt:

- `E`: tập join point **mong muốn** được chính sách chọn.
- `M`: tập join point **thực sự** được pointcut chọn.
- `E \ M`: join point bị bỏ sót (**false negative**).
- `M \ E`: join point bị chọn thừa (**false positive**).

Một refactor hợp lệ có thể làm thay đổi cả `E` và `M`. Ta cần xác định mục tiêu **ngữ nghĩa** trước, rồi kiểm tra selector vẫn chọn đúng tập mới.

Ví dụ bảng:

| Thay đổi | Pointcut ban đầu | Rủi ro |
|---|---|---|
| Đổi `submit` thành `place` | Khớp tên `submit` | Bỏ sót thao tác cần audit |
| Chuyển `old.orders.Service` sang `new.orders.Service` | Khớp FQN của lớp/package cũ | Bỏ sót toàn bộ thao tác mới |
| Thêm `submit(int)` | Khớp `submit(..)` | Bắt cả overload khác nghĩa |
| Đổi `submit(String)` thành `submit(Command)` | Khớp tham số `String` | Bỏ sót vì chữ ký đổi |
| Đổi implementation nhưng giữ interface | Match dựa trên declaring class/implementation | Có thể trượt theo loại join point |
| Thêm override trong subclass | Match chỉ một method hoặc type | Có thể bỏ sót override thực thi |
| Sinh bridge method do generics | Đếm/match tất cả method reflect | Có thể tính hai method hoặc chọn sai |
| Chuyển từ gọi qua proxy sang gọi trực tiếp | Proxy interception | Advice không còn chạy |
| Mở rộng wildcard package | `..*Service.*(..)` | Chọn nhiều helper hoặc method không liên quan |

Độ mong manh là kết quả của **sự lệ thuộc vào chi tiết dễ thay đổi**. Không có nghĩa luôn phải tránh exact signature: đôi khi chính xác một overload là hợp đồng quan trọng. Điều cần làm là chọn đặc tính **được quản lý và kiểm thử như một phần kiến trúc**.

## 4. Ba nguồn thay đổi quan trọng

### 4.1. Đổi tên phương thức

Một pointcut chỉ dựa trên chuỗi `submit` có thể mất tác dụng khi refactor thành `place`, dù nghiệp vụ vẫn là đặt hàng. Tên method phục vụ thiết kế API nhưng không phải lúc nào cũng là định danh ổn định của **business action**.

```text
Trước:
  OrderActions.submit(String orderId)   -> ORDER_PLACE

Sau:
  OrderActions.place(String orderId)    -> ORDER_PLACE

Pointcut theo tên:
  name == "submit"    // mất thao tác ORDER_PLACE sau refactor

Pointcut theo mã action đã kiểm tra:
  action == ORDER_PLACE  // vẫn nhận diện thao tác đổi tên
```

Một số thay đổi tên còn làm lộ sự khác biệt ngữ nghĩa thật: `save` trước đây có thể vừa tạo vừa cập nhật, sau refactor thành `create` và `update` với chính sách khác nhau. Khi đó không nên copy máy móc cùng annotation/mã action cho cả hai. **Ổn định selector không quan trọng hơn đúng hợp đồng nghiệp vụ**.

### 4.2. Di chuyển lớp, package, module

Pointcut theo tên package hay lớp cụ thể dễ vỡ khi nhóm phát triển tái cấu trúc module, đổi namespace hoặc thay implementation. Nếu advice được weave tại bytecode, cần hiểu nó matching **declaring type**, **runtime type**, subtype hierarchy hay location lexical. Nếu dùng proxy, cần biết proxy hiện thực interface nào và join point thực tế nằm ở phía gọi hay method execution.

```text
Trước:
  old.application.OrderCommands.submit(...)

Sau:
  app.orders.usecase.OrderCommands.place(...)
```

Một selector chuỗi gắn với `old.application..*` có thể không được refactoring tool cập nhật. Ngược lại, wildcard `*..*` quá rộng sẽ bắt nhiều thao tác không cần. Đừng giải quyết selector bỏ sót bằng một biểu thức wildcard không kiểm soát; cần xác định **ranh giới kiến trúc có tên và có hợp đồng**.

Trong triển khai thực tế, package có thể vẫn là tín hiệu hữu ích để xác định vùng ứng dụng cần kiểm tra, nhưng nên kết hợp **hợp đồng method** thay vì dùng package làm toàn bộ quyết định.

### 4.3. Nạp chồng phương thức (overloading)

Java cho phép một type có nhiều method cùng tên, khác danh sách kiểu tham số:

```java
// Mảnh minh họa, không phải chương trình độc lập.
void submit(String orderId); // đặt đơn
void submit(int orderNumber); // tra cứu đơn cũ
```

Selector `name == "submit"` chặn cả hai, trong khi selector `name + parameterTypes == (String)` chỉ chặn một overload. Nếu overload mới là một hành động khác, chặn cả hai có thể dẫn tới:

- Transaction không cần thiết quanh lời gọi chỉ đọc.
- Metric bị đếm sai; tên span trùng nhau dù action khác.
- Retry không an toàn hoặc không phù hợp với overload mới.
- Quy tắc quyền nhầm: người được phép tạo đơn bị buộc phải có quyền tra cứu, hoặc ngược lại.
- Log đối số không phù hợp, tăng khả năng lộ thông tin.

**Overloading không phải overriding.** Overload được chọn từ chữ ký tại compile time; override là implementation mới của method có quan hệ kế thừa, với dispatch tại runtime. Một pointcut phải giải thích nó chọn **declaration, implementation, call site hay execution**.

## 5. Tại sao selector chỉ theo tên thường quá yếu?

Tên thường biểu thị cách code được viết, không đầy đủ ý nghĩa nghiệp vụ. Ví dụ `save` có thể vừa:

- Lưu hóa đơn, đòi transaction và audit.
- Ghi một cache entry, không cần transaction nghiệp vụ.
- Lưu nhật ký hệ thống, không nên lặp vô điều kiện.
- Là helper xây dựng object, không có thao tác bảo mật.

Một selector rộng kiểu “mọi phương thức có tên `save`” sẽ tác động đồng loạt. Còn selector cực hẹp vào FQN và chữ ký có thể vỡ sau khi đổi interface, di chuyển package hoặc điều chỉnh overload.

Lựa chọn thực tiễn:

1. Chọn **logical boundary** mà team duy trì được như một hợp đồng: command/query service, nghiệp vụ tạo/duyệt/xuất dữ liệu.
2. Định danh hành động bằng mã có ý nghĩa ổn định (`ORDER_PLACE`, `ORDER_LOOKUP`), annotation hoặc registry explicit.
3. Kết hợp ràng buộc phạm vi để không mở selector ra toàn ứng dụng.
4. Kiểm thử cả danh sách join point được chọn và khả năng lời gọi thật thực sự đi qua interception.
5. Khi refactor, cập nhật contract và test cùng thay đổi mã nghiệp vụ.

Một annotation không phải “lá bùa” giải quyết mọi trường hợp. Nó có thể bị quên, bị copy sai, mất do retention, đặt trên interface nhưng interceptor chỉ đọc implementation, hoặc chính method có ý nghĩa mới trong khi annotation cũ chưa đổi.

## 6. Biến ngữ nghĩa nghiệp vụ thành metadata

Một hướng thiết kế là khai báo ý định:

```java
// Mảnh minh họa API, không phải chương trình độc lập.
@BusinessAction("ORDER_PLACE")
Receipt place(CreateOrderCommand command);

@BusinessAction("ORDER_LOOKUP")
OrderView submit(int orderNumber);
```

Interception chọn join point theo annotation và/hoặc registry, sau đó đọc mã action để điều khiển advice. Nếu `place` đổi thành `confirm` nhưng ý nghĩa không đổi, mã `ORDER_PLACE` có thể được giữ. Nếu hành động đổi nghĩa, người sửa phải cập nhật chính sách và test.

Cần kiểm soát những vấn đề sau:

- **Retention:** annotation được đọc bằng reflection tại runtime cần `@Retention(RetentionPolicy.RUNTIME)`. Với weaving diễn ra ở thời điểm khác, yêu cầu cụ thể phụ thuộc cơ chế.
- **Target:** annotation method khác annotation type; đặt sai vị trí không được tự động hiểu là áp cho từng method.
- **Interface vs implementation:** `method.getAnnotation(...)` xem metadata trên đúng đối tượng `Method` đang đọc. Không được giả định annotation trên interface tự sao sang implementation.
- **Kế thừa:** `@Inherited` chủ yếu ảnh hưởng truy vấn annotation ở class, không tự khiến annotation method của interface/overridden method được kế thừa khi truy vấn reflection.
- **Khả năng thiếu khai báo:** một method mới ở boundary bảo vệ phải có policy phù hợp hoặc được phân loại public bằng cơ chế rõ ràng; không ngầm coi không có annotation nghĩa là không cần kiểm tra.
- **Tính ổn định của mã action:** mã action phải có catalog và owner; rename của mã action cũng cần migration có kiểm soát.
- **Nhiều semantics trên một method:** ví dụ một operation có thể yêu cầu audit và transaction. Tách metadata/policy cho từng concern nếu chúng không có cùng tập join point.

Với API bên thứ ba không thể gắn annotation, một **typed registry** ánh xạ method/signature sang chính sách có thể phù hợp. Nhưng registry phải được đồng bộ và được test coverage khi API thay đổi.

## 7. Ví dụ Java 17 hoàn chỉnh: pointcut theo tên, chữ ký và action

Ví dụ này chỉ dùng JDK: reflection và dynamic proxy.

- `fragileExact` mô phỏng selector buộc method phải thuộc `LegacyCommands.submit(String)`.
- `fragileName` mô phỏng selector chỉ dựa vào tên `submit`.
- `semantic` chọn mã hành động `ORDER_PLACE` từ annotation trên method.
- `Commands.place(String)` là thao tác đổi tên, cùng ý nghĩa đặt đơn.
- `Commands.submit(int)` là overload mới với ý nghĩa **tra cứu**, dù tên giống method cũ.
- Proxy `guarded` tạo interception theo metadata. Nó minh họa kỹ thuật chặn lời gọi, chưa có quyết định phân quyền hay transaction thực tế.

Lưu vào file **PointcutStabilityDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class PointcutStabilityDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface BusinessAction { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface PublicAction {}

    interface LegacyCommands {
        @BusinessAction("ORDER_PLACE")
        String submit(String orderId);
    }

    interface Commands {
        @BusinessAction("ORDER_PLACE")
        String place(String orderId);

        @BusinessAction("ORDER_LOOKUP")
        String submit(int orderNumber);

        @PublicAction
        String health();
    }

    static final class Handler implements Commands {
        public String place(String orderId) { return "placed:" + orderId; }
        public String submit(int orderNumber) { return "lookup:" + orderNumber; }
        public String health() { return "ok"; }
    }

    static boolean fragileExact(Method method) {
        return method.getDeclaringClass() == LegacyCommands.class
                && method.getName().equals("submit")
                && method.getParameterCount() == 1
                && method.getParameterTypes()[0] == String.class;
    }

    static boolean fragileName(Method method) {
        return method.getName().equals("submit");
    }

    static boolean semantic(Method method) {
        BusinessAction action = method.getAnnotation(BusinessAction.class);
        return action != null && action.value().equals("ORDER_PLACE");
    }

    static Commands guarded(Commands target) {
        return (Commands) Proxy.newProxyInstance(
                Commands.class.getClassLoader(),
                new Class<?>[] { Commands.class },
                (proxy, method, args) -> {
                    BusinessAction action = method.getAnnotation(BusinessAction.class);
                    if (action != null) {
                        System.out.println("intercept=" + action.value());
                    } else if (!method.isAnnotationPresent(PublicAction.class)) {
                        throw new IllegalStateException("Unclassified operation");
                    }
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                });
    }

    public static void main(String[] args) throws Exception {
        Method old = LegacyCommands.class.getMethod("submit", String.class);
        Method renamed = Commands.class.getMethod("place", String.class);
        Method overloaded = Commands.class.getMethod("submit", int.class);
        System.out.println("legacy_exact=" + fragileExact(old));
        System.out.println("renamed_exact=" + fragileExact(renamed));
        System.out.println("renamed_name=" + fragileName(renamed));
        System.out.println("overload_name=" + fragileName(overloaded));
        System.out.println("renamed_semantic=" + semantic(renamed));
        System.out.println("overload_semantic=" + semantic(overloaded));

        Commands api = guarded(new Handler());
        System.out.println(api.place("A-7"));
        System.out.println(api.submit(7));
        System.out.println(api.health());
    }
}
```

Biên dịch và chạy bằng Java 17:

```bash
javac --release 17 -encoding UTF-8 PointcutStabilityDemo.java
java PointcutStabilityDemo
```

Kết quả đã chạy kiểm chứng:

```text
legacy_exact=true
renamed_exact=false
renamed_name=false
overload_name=true
renamed_semantic=true
overload_semantic=false
intercept=ORDER_PLACE
placed:A-7
intercept=ORDER_LOOKUP
lookup:7
ok
```

Giải thích theo từng dòng:

1. `legacy_exact=true`: selector cũ còn match chữ ký trong `LegacyCommands`.
2. `renamed_exact=false`: thao tác sau refactor nằm ở interface `Commands`, tên `place`, nên matcher buộc type/chữ ký cũ bị bỏ sót.
3. `renamed_name=false`: matcher theo tên `submit` cũng bỏ sót thao tác đặt đơn đã đổi tên.
4. `overload_name=true`: matcher theo tên lại chọn overload `submit(int)`, một hành động tra cứu khác.
5. `renamed_semantic=true` và `overload_semantic=false`: khi hỏi riêng *“có phải ORDER_PLACE không?”*, metadata phân biệt đúng hai nghiệp vụ.
6. Khi gọi thật qua proxy, hai method có action được instrument với mã thích hợp; `health()` được khai báo `@PublicAction` nên chạy không có dòng intercept.

**Quan trọng:** `semantic` trong ví dụ chỉ chọn `ORDER_PLACE`, còn proxy `guarded` cố ý intercept *mọi method có `@BusinessAction`* để log mã action. Hai hành vi này không mâu thuẫn: selector lọc một action cụ thể khác với một interceptor chung cho tất cả business action.

**Phạm vi:** JDK proxy chỉ intercept các lời gọi **qua interface của proxy**. Ví dụ không thay thế một engine weaving đầy đủ, không chứng minh mọi join point trong ứng dụng đều được chặn. `@BusinessAction` và `@PublicAction` được khai báo trên interface; nếu chuyển annotation sang implementation thì cách lấy metadata phải thay theo hợp đồng. Handler demo cũng không trình bày đầy đủ hành vi các method của `Object` trên proxy; khi dùng production cần xác định rõ cách xử lý `equals/hashCode/toString` và những method ngoài interface được bảo vệ.

## 8. Điểm chặn theo kiểu `call` và `execution` khác nhau

AOP có thể quan sát **lời gọi method** tại call site hoặc **việc thực thi method** tại implementation; công cụ khác nhau hỗ trợ tập join point khác nhau.

```text
Caller -> [call join point] -> dynamic dispatch -> [execution join point] -> body
```

Điểm cần suy nghĩ:

- Method gọi có thể được khai báo ở interface/superclass; method thực thi có thể nằm ở subclass khác.
- Compile-time type tại call site khác runtime target type.
- Pointcut chọn `call` trong một package có thể bỏ qua caller chuyển sang package khác dù method không đổi.
- Pointcut chọn `execution` theo declaring type có thể thay đổi khi method được override hoặc chuyển sang một implementation khác.
- Proxy interception chặn những lời gọi đi qua proxy; self-invocation bằng `this.method()` thường không đi qua proxy. Weaving có thể hỗ trợ phạm vi khác, nhưng phải dựa vào engine đang dùng, không suy luận chung.

Vì vậy câu “pointcut match method X” còn thiếu thông tin. Cần viết rõ: **join point loại nào, code/lớp nào, điều kiện static hay dynamic, được gắn tại build/load/runtime, và đường gọi nào được bao phủ**.

## 9. Overriding, inheritance và generic bridge methods

### 9.1. Override làm thay đổi nơi thực thi

Một method công khai qua interface có thể được implement bởi nhiều lớp. Nếu pointcut match một lớp cụ thể, implementation mới có thể không được chặn. Ngược lại, một selector rộng theo subtype có thể bắt thêm implementation mà policy khác nhau.

Trước khi refactor, xác định rõ:

- Advice thuộc hợp đồng **giao diện** hay thuộc implementation?
- Có bao gồm override mới trong subclass?
- Có method default trên interface và lời gọi vào nó không?
- Dynamic proxy có nhận đúng interface method không? Weaving có chọn execution của implementation không?
- Có method synthetic/bridge mà công cụ có thể trình bày như join point riêng không?

### 9.2. Generic và type erasure

Java xóa phần lớn thông tin generic ở runtime. Một method như `process(List<Order>)` và `process(List<Customer>)` không thể là hai overload chỉ khác generic element type vì chúng có cùng erasure. Dựa trên tên generic được suy ra từ source để xây runtime pointcut có thể không khớp như mong đợi.

Compiler cũng có thể sinh **bridge method** nhằm bảo toàn polymorphism sau type erasure. Reflection có `Method.isBridge()` và `Method.isSynthetic()`; không tự cho rằng mọi method thu được từ `getDeclaredMethods()` là một business operation độc lập.

Một công cụ AOP có thể đã xử lý bridge/synthetic cho bạn, hoặc không. Nếu tự làm interception/registry dựa trên reflection, cần chính sách chuẩn hóa method gốc/bridge rõ ràng và test với generic override.

### 9.3. Return type và covariant return

Java không phân biệt overload chỉ bằng return type. Một phương thức override có thể trả subtype phù hợp (*covariant return*), và có thể liên quan đến bridge method. Selector hoặc registry lưu đầy đủ mô tả bytecode phải xử lý sự khác biệt giữa chữ ký Java ở source và method descriptor trong bytecode.

### 9.4. Varargs

`send(String...)` được biên dịch thành tham số mảng `String[]`. Pointcut/registry dựa trên runtime parameter types nhìn thấy array, không phải “số đối số tùy ý” như ở call site. Reflection có `Method.isVarArgs()` để xác nhận ngữ nghĩa. Đổi từ `send(String)` thành `send(String...)` có thể làm exact selector cũ không còn match.

## 10. Tên tham số, modifier và annotation cũng có giới hạn

Pointcut hoặc advice đôi khi dựa vào tên tham số để suy ý nghĩa:

```java
// Mảnh minh họa, không phải chương trình độc lập.
void approve(String documentId, String reviewerId);
```

Ở runtime Java, `Parameter.getName()` có thể chỉ trả `arg0`/`arg1` nếu không biên dịch với `-parameters` và không có nguồn metadata khác. Việc đổi tên biến cũng có thể phá quy tắc dù hợp đồng thao tác không đổi. Dùng kiểu, vị trí, annotation hoặc request schema có kiểm soát khi cần trích tài nguyên cho policy.

Các modifier như `public`, `protected`, `private`, `static`, `final` có thể ảnh hưởng khả năng intercept theo cơ chế. Không phải mọi engine có thể chặn constructor, field access hoặc method final/private giống nhau. Đừng dùng một pointcut “rộng trên giấy” rồi mặc định mọi kiểu member đều được quan sát.

**Annotation matching** cũng cần test retention và lookup location. Thêm annotation vào interface, implementation hoặc override có thể không có cùng tác dụng. Không copy annotation từ method gốc tới method mới nếu ngữ nghĩa đã đổi.

## 11. Hậu quả khác nhau theo loại advice

Cùng một false negative/false positive có mức rủi ro rất khác nhau:

| Concern | Bỏ sót pointcut | Bắt thừa pointcut |
|---|---|---|
| Logging/observability | Thiếu trace, audit, metric | Log rác, dữ liệu nhạy cảm, tăng chi phí |
| Authorization | Có thể chạy thao tác mà chưa kiểm quyền | Từ chối thao tác hợp lệ hoặc áp policy sai |
| Transaction | Thiếu ranh giới commit/rollback mong muốn | Transaction dài, lock thừa, quy tắc commit sai |
| Retry | Bỏ mất khả năng phục hồi transient | Gọi lại side effect không idempotent |
| Cache | Không dùng cache ở nơi cần | Cache sai dữ liệu/ngữ cảnh actor |
| Rate limit | Đường gọi mới tránh giới hạn | Chặn cả helper đọc nhẹ |
| Timing/metrics | Mất dữ liệu đo theo nghiệp vụ | Nhân đôi metric, làm sai cardinality |

Với **phân quyền và tính toàn vẹn dữ liệu**, đừng dựa duy nhất vào một selector tên method mà không có guard/constraint sát thao tác nghiệp vụ. AOP có thể là PEP ở boundary, nhưng nội bộ vẫn cần xác minh các bất biến quan trọng trong transaction/storage khi nhiều đường vào tồn tại.

## 12. Thiết kế pointcut bền vững hơn

Một thiết kế hợp lý thường có **hai lớp điều kiện**:

1. **Phạm vi kiến trúc:** chỉ chọn nhóm operation boundary do ứng dụng quản lý.
2. **Phân loại ngữ nghĩa:** chọn business action/annotation/registry cụ thể được quy định bằng hợp đồng.

Ví dụ diễn đạt khái niệm:

```text
isManagedBusinessBoundary(method)
    AND operationContract(method).action == ORDER_PLACE
```

Như vậy, việc di chuyển package có thể yêu cầu cập nhật boundary definition và kiểm thử coverage, nhưng không bắt mọi method chỉ vì tên giống nhau. Ngược lại, annotation đánh dấu action không vô tình áp dụng đến các helper ngoài boundary.

Các nguyên tắc:

- **Nguyên tắc tối thiểu:** chỉ intercept phạm vi cần cho concern.
- **Explicit contract:** mỗi operation nhạy cảm phải được khai báo policy rõ, kể cả khi public.
- **Fail closed phù hợp:** nếu một operation thuộc boundary bảo vệ nhưng thiếu classification, không tự cho chạy; một policy bị thiếu phải phát hiện khi build/startup hoặc bị từ chối theo hợp đồng.
- **Tách ngữ nghĩa khỏi tên implementation:** business action ID có thể giữ ổn định qua rename, move, đổi implementation khi ý định không đổi.
- **Có kiểm thử phủ pointcut:** lời gọi thật phải đi qua advice, không chỉ metadata phản chiếu.
- **Không kết hợp quá nhiều mối quan tâm vào một selector:** authorization, telemetry, retry và transaction có thể cần tập join point khác nhau.
- **Review thay đổi contract:** tách/tổng hợp operation phải được xét lại chính sách; không giữ ID cũ chỉ vì tiện tương thích.

Không có “pointcut bất biến” miễn phí. Mục tiêu là khiến thay đổi có tác động lên selector được **phát hiện và đánh giá có chủ đích**.

## 13. Kiểm thử pointcut như một phần của hợp đồng kiến trúc

Kiểm thử chỉ xem method trả kết quả đúng là chưa đủ. Cần test cụ thể **advice có chạy cho đúng tập lời gọi không**.

### 13.1. Test positive

Tạo fixture có một lời gọi bắt buộc được chặn; assertion có thể kiểm tra:

- Advice tăng counter hoặc ghi event test-only.
- Đúng mã action và metadata được dùng.
- `proceed()` được gọi đúng theo hợp đồng (ví dụ một lần khi không có retry).
- Policy thực sự từ chối trước side effect khi áp dụng authorization.

### 13.2. Test negative

Tạo method giống tên nhưng khác nghĩa hoặc nằm ngoài boundary. Assert advice không chạy ở nơi không thuộc scope. Ví dụ overload `submit(int)` không bị áp nhầm policy `ORDER_PLACE`.

### 13.3. Test refactor

Trong bài kiểm thử kiến trúc, liệt kê các command/query method trong vùng được quản lý và yêu cầu **được phân loại**. Sau đó:

- Rename method trên fixture: semantic action đúng vẫn được chọn.
- Move type sang package mới của boundary: coverage không bị âm thầm mất.
- Thêm overload khác nghĩa: không nhận policy của overload cũ.
- Thêm implementation/override: lời gọi thật vẫn qua điểm chặn cần thiết.
- Thêm method không khai báo: build/test thất bại thay vì tự mặc định public.
- Bỏ annotation: test chỉ ra lỗi phân loại hoặc fail-closed.

Những test này phải cập nhật khi hợp đồng nghiệp vụ thay đổi, thay vì cứng hóa tên method cũ mãi mãi.

### 13.4. Phân biệt test match và test execution

Một test `pointcut.matches(Method)` có thể PASS nhưng advice **không bao giờ chạy** vì ứng dụng gọi implementation trực tiếp, gọi nội bộ qua `this`, hoặc sử dụng entrypoint khác. Cần cả:

- **Static/metadata test:** selector và registry có chọn đúng method mong muốn?
- **Integration test:** lời gọi qua đường thực tế có kích hoạt interceptor/weaving không?
- **Behavior test:** side effect, exception, audit/metric/transaction thực sự đúng không?

Với phản xạ Java, lọc hoặc chuẩn hóa method synthetic/bridge khi đếm coverage; tránh đếm bridge thành operation riêng hoặc làm bỏ sót contract method thật.

## 14. Refactor an toàn: thay đổi từng bước

Khi chuyển một pointcut mong manh sang hợp đồng ổn định hơn:

**Bước 1 — Chụp tập join point hiện tại.** Từ cấu hình và test, ghi lại phương thức nào thực sự bị chặn, concern nào dùng pointcut đó và mục đích nghiệp vụ.

**Bước 2 — Xác định tập mong muốn.** Chủ sở hữu nghiệp vụ xác nhận action nào phải được authorization, transaction, retry, audit… Đừng coi tập đang bị chặn là đúng tuyệt đối: lỗi cũ có thể đã tồn tại.

**Bước 3 — Định nghĩa metadata/registry.** Có tên action rõ, phạm vi type, cách xử lý public command và policy khi thiếu metadata.

**Bước 4 — Tạo test coverage.** Assertion dương/âm cho rename, overload, implementation mới, self-call, exception, async. Với bảo mật, dùng test “không có side effect khi thiếu quyền”.

**Bước 5 — Chuyển interception và kiểm tra trùng.** Nếu pointcut cũ và mới chạy song song, tránh ghi audit đôi, mở hai transaction hoặc retry lồng nhau. Có thể so sánh song song ở chế độ chỉ đánh giá (shadow) khi phù hợp, nhưng phải tránh vô tình nhân hiệu ứng.

**Bước 6 — Gỡ selector cũ sau khi xác minh.** Tài liệu hóa ranh giới mới, cách khai báo method và kiểm tra trong CI.

**Bước 7 — Rà soát sau mỗi thay đổi.** Thêm overload/method mới, move package hoặc thay đường gọi là thay đổi kiến trúc cần review policy.

Đặc biệt cẩn trọng với việc “thay hết bằng wildcard `*`”: làm vậy có thể chữa false negative bằng cách tăng mạnh false positive.

## 15. Pointcut coverage trong các tình huống bất đồng bộ

Một method có thể trả `CompletableFuture` hoặc một đối tượng mô tả luồng xử lý bất đồng bộ. Pointcut trên **method entry** chỉ chặn lúc tạo handle, không đồng nghĩa chặn mọi callback, attempt, subscription hay handler chạy về sau.

Ví dụ:

```text
submitOperation() --returns future--> caller
     |
     +-- executor task --> callback --> external side effect
```

Nếu refactor chuyển side effect từ phần đồng bộ của method vào callback, một advice trước method có thể vẫn match về tên/type nhưng **không còn bao trùm thời điểm hiệu ứng phát sinh**. Đó là thay đổi **ngữ nghĩa join point**, không thể phát hiện chỉ bằng kiểm tra chuỗi tên.

Với ranh giới bất đồng bộ:

- Xác định action được **chấp nhận**, **xếp lịch** hay **thực hiện** ở đâu.
- Kiểm tra quyền, transaction và dữ liệu tại nơi side effect thực sự xảy ra nếu trạng thái có thể đổi.
- Propagate correlation/security context qua executor/scheduler bằng snapshot và restore, không giả định `ThreadLocal` tự đi theo.
- Kiểm tra completion khi cần đo thời gian/ghi kết quả cuối cùng, thay vì dừng tại thời điểm trả future.
- Bảo đảm pointcut không chỉ đánh dấu API wrapper mà bỏ sót consumer hoặc task thực hiện.

Đối với queue và message handler, một thay đổi route hoặc serializer cũng có thể làm handler mới không thuộc pointcut cũ. Cần test từ entrypoint đến effect.

## 16. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân | Hướng sửa |
|---|---|---|
| Advice mất sau rename | Match literal method name | Gắn theo business action contract và test positive |
| Move package xong không còn trace | Match FQN/package cũ | Kiểm soát boundary registry và test khi move |
| Thêm overload làm policy chạy sai | Wildcard `methodName(..)` | Phân biệt action, parameter signature hoặc annotation |
| Thay implementation làm interceptor im lặng | Selector gắn implementation cũ | Xác định join point/declaring type và test execution |
| Self-invocation bỏ qua guard | Proxy chỉ chặn lời gọi qua proxy | Giữ boundary rõ và kiểm tra sát dữ liệu |
| Pointcut trên interface không áp vào implementation | Đọc annotation sai vị trí | Lookup method/metadata theo chiến lược rõ |
| Advice chạy hai lần | Bridge method hoặc hai interception layer | Chuẩn hóa method và dedup theo scope |
| Method mới không được bảo vệ | Không có metadata/kiểm tra contract | Default deny tại managed boundary, CI test |
| Pointcut wildcard bắt cả helper | Match theo pattern quá rộng | Giới hạn phạm vi + semantic action |
| Test PASS nhưng production bypass | Chỉ unit test predicate | Integration test đường gọi thật |
| AOP match vẫn sai thời điểm | Side effect chuyển sang future/queue | Đặt guard/observation tại execution boundary phù hợp |

## 17. Checklist rà soát pointcut trước release

- [ ] Tập join point mong muốn được mô tả bằng **ý nghĩa nghiệp vụ**, không chỉ chuỗi tên method.
- [ ] Selector xác định rõ loại join point (`call`, `execution` hoặc proxy invocation) và phạm vi type.
- [ ] Rename, move package/module và overload đã được kiểm thử cả positive lẫn negative.
- [ ] Overriding, inheritance, generic bridge, varargs và covariant return được xem xét khi có liên quan.
- [ ] Annotation hoặc registry được đặt/đọc đúng interface/implementation và retention.
- [ ] Method mới ở boundary nhạy cảm không thể im lặng bỏ qua policy.
- [ ] Không có raw instance/self-invocation hoặc entrypoint ngoài scope vô tình bypass enforcement.
- [ ] Có test chứng minh advice **thực sự chạy**, không chỉ kiểm tra selector bằng reflection.
- [ ] Authorization/transaction/retry/audit không bị áp nhầm overload hoặc chạy hai lần.
- [ ] Async callback/message consumer được kiểm tra tại ranh giới side effect tương ứng.
- [ ] Phạm vi instrument và action registry được cập nhật cùng refactor trong code review/CI.
- [ ] Monitoring theo logical action cho thấy thay đổi đột ngột về số lần interception khi rollout.

## 18. Ghi nhớ

**Pointcut dựa vào hình dạng mã nguồn sẽ mong manh khi hình dạng ấy thay đổi.** Đổi tên phương thức có thể gây bỏ sót, nạp chồng có thể gây chọn nhầm, còn di chuyển lớp hoặc đổi đường gọi có thể khiến advice không chạy dù ứng dụng vẫn bình thường. Để bền vững, cần **ranh giới nghiệp vụ rõ, metadata/registry có ngữ nghĩa, phạm vi interception xác định và kiểm thử cả phần được chọn lẫn phần không được chọn**. Với concern quan trọng như phân quyền hay tính toàn vẹn dữ liệu, hãy bổ sung bảo vệ sát side effect để một thay đổi pointcut không trở thành một đường truy cập ngoài chính sách.
