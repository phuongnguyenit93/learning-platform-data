# Bài tập tổng hợp AOP: Thử thay đổi cấu trúc mã để phát hiện pointcut mong manh

## 1. Mục tiêu học tập

Một pointcut có thể hoạt động đúng hôm nay nhưng **âm thầm đổi tập join point được chọn** khi mã nghiệp vụ được refactor. Đổi tên một phương thức, chuyển lớp sang package khác, bổ sung overload, tách helper hoặc đổi từ lời gọi trực tiếp sang callback có thể làm advice biến mất hoặc xuất hiện tại nơi không mong muốn. Điều nguy hiểm nhất là nhiều thay đổi vẫn biên dịch, test nghiệp vụ vẫn qua, nhưng quy tắc AOP không còn đúng.

Bài tập này yêu cầu **thay đổi cấu trúc mã có chủ đích**, quan sát tập join point trước/sau rồi xác định một pointcut có **mong manh (fragile)** hay không. Mục tiêu không phải chứng minh một kiểu pointcut luôn tốt hơn; mục tiêu là học cách viết **hợp đồng chọn join point**, kiểm thử các trường hợp dương/âm và biết khi nào việc refactor cần thay đổi aspect.

**Hoàn thành bài khi có thể:**

1. Giải thích vì sao cùng một pointcut chọn khác đi khi tên, package, method signature, annotation, hierarchy hoặc call graph thay đổi.
2. Đặt được kỳ vọng **match / không match** trước khi chạy test và so với các join point thực tế.
3. Tái hiện được ít nhất một lỗi **false negative** (bỏ sót nơi phải chặn) và một lỗi **false positive** (chặn thêm nơi không nên chặn).
4. Đề xuất pointcut ổn định hơn dựa vào **ngữ nghĩa/hợp đồng**, nếu bài toán cho phép.
5. Phân biệt lỗi do matcher với lỗi **không có interception/weaving** tại điểm gọi.
6. Chạy được ví dụ Java 17 mô phỏng AOP dựa trên proxy và hiểu giới hạn so với AOP dệt bytecode.
7. Lập ma trận regression test và đánh giá tác động nghiệp vụ khi pointcut lệch.

## 2. Pointcut mong manh là gì?

Trong Aspect-Oriented Programming, **join point** là một vị trí/sự kiện có thể bị tác động (ví dụ thực thi method, lời gọi method, khởi tạo hoặc truy cập trường tùy engine); **pointcut** mô tả tập sự kiện được chọn; **advice** là hành vi được thực thi khi chọn được join point đó. **Weaving hoặc interception** xác định các nơi có thể tham gia AOP.

Ví dụ giả định một aspect đo thời gian đang chọn:

```java
// Pointcut kiểu AspectJ, chỉ minh họa cú pháp:
execution(* demo.billing.InvoiceService.submit(..))
```

Nó phụ thuộc vào **tên type**, **package** và **method**. Nếu phương thức được đổi thành `placeOrder` nhưng hành vi nghiệp vụ vẫn là “gửi đơn”, biểu thức trên có thể không khớp nữa. Compiler Java thông thường không nhất thiết báo lỗi vì pointcut chỉ là một mẫu chọn được kiểm tra trong quá trình AOP.

Ngược lại, một pointcut quá rộng:

```java
execution(* demo.billing..*.*(..))
```

có thể bắt cả class mới chứa helper logging hoặc client network vừa được chuyển vào `demo.billing`. Khi advice cũng gọi helper đó, hệ thống có nguy cơ log lặp, tăng overhead hoặc recursion.

**Định nghĩa thực dụng:** pointcut mong manh khi một thay đổi mã **không làm đổi yêu cầu cắt ngang** nhưng lại khiến tập join point phù hợp thay đổi ngoài ý muốn. Không phải thay đổi match nào cũng sai: nếu requirement cố tình gắn với tên hoặc package, khi đổi tên/package thì yêu cầu cũng có thể cần cập nhật.

## 3. Thiết lập hợp đồng chọn trước khi refactor

Trước khi sửa mã, trả lời bằng văn bản:

- **Ý nghĩa nghiệp vụ:** cần chặn thao tác nào? Ví dụ “mọi lệnh đặt hàng” hay “mọi method trong package adapters”?
- **Loại sự kiện:** `call` ở caller, `execution` ở callee, method interception tại proxy, hay loại join point khác?
- **Đơn vị chọn:** khai báo trên method, annotation, interface, hierarchy, package, signature, hay runtime args?
- **Độ sâu:** có bắt lời gọi con, self-invocation, recursion, callback, async completion không?
- **Điều kiện loại trừ:** những helper, serializer, logger, health check nào bắt buộc phải không match?
- **Rủi ro khi lệch:** mất metric, bỏ kiểm tra quyền, trùng audit, nhân đôi side effect, thay exception hoặc latency tăng?

Đặt một **oracle** cho mỗi test: method/sự kiện nào **phải** có advice và method/sự kiện nào **không được** có. Không xây oracle bằng cách sao chép y hệt biểu thức pointcut vào test, vì khi sai cùng một giả định, test có thể cũng sai.

### 3.1. Hai loại sai lệch

| Loại | Định nghĩa | Ví dụ | Tác động |
| --- | --- | --- | --- |
| False negative | Join point thuộc yêu cầu nhưng không được chọn | Đổi `submit()` thành `send()`, mẫu vẫn bắt `submit` | Bỏ log/audit/guard cần thiết |
| False positive | Join point ngoài yêu cầu nhưng bị chọn | Thêm `submitDebug()` vào package và dùng wildcard `submit*` | Chạy advice thừa, overhead, side effect hoặc recursion |
| Mất interception | Matcher có thể đúng nhưng đường gọi không qua proxy/weaving | Target tự gọi `this.send()` trong delegation proxy | Advice không có cơ hội chạy |
| Sai event kind | Matcher gắn vào loại join point khác dự kiến | Chỉ weave `call` ở một số caller, còn code chuyển sang caller khác | Một số sự kiện không được quan sát |
| Match đúng, advice sai | Pointcut chọn đúng nhưng advice không giữ contract | `around` gọi `proceed` hai lần sau refactor retry | Side effect bị nhân đôi |

Bài tập tập trung vào hai hàng đầu, nhưng khi điều tra phải loại trừ ba hàng còn lại để không sửa nhầm nguyên nhân.

## 4. Ma trận thay đổi cấu trúc mã

Đây là tập thí nghiệm nên thực hiện **mỗi lần một thay đổi**, sau đó đối chiếu tập match với bản gốc.

| Thay đổi mã | Pointcut dựa trên tên/package/signature có thể bị gì? | Điều cần quan sát |
| --- | --- | --- |
| Đổi `submit` thành `place` | Bỏ sót method cũ hoặc match vào method khác cùng tên | Có còn advice tại lệnh đặt hàng không? |
| Chuyển `InvoiceService` sang package mới | Mẫu package cũ không khớp | Weaving có xử lý class mới không? |
| Thêm overload `submit(String,int)` | Wildcard `submit(..)` bắt thêm overload | Overload mới thuộc hay không thuộc contract? |
| Thay chữ ký tham số/kiểu trả về | Mẫu signature quá chặt bỏ sót | Compile warning, số join point khớp, giá trị trả về |
| Tách `submit` thành helper hoặc delegate | `execution` bắt thêm tầng, `call` đổi call site | Advice chạy một lần hay nhiều lần? |
| Đổi class sang interface/implementation khác | Mẫu type hoặc annotation lookup đổi | Method nào thực sự được chọn? |
| Đổi tên annotation hoặc chuyển nơi khai báo | `@annotation` và metadata lookup có thể bỏ sót | Annotation có nằm trên join point được engine kiểm tra không? |
| Thêm class/helper vào package đã match rộng | False positive, kể cả logging helper | Có phát sinh advice đệ quy hay metric nhiễu không? |
| Chuyển caller sang callback/lambda | `call` site có thể đổi hoặc proxy boundary bị bỏ qua | Caller mới đã được weave/chặn chưa? |
| Đổi method modifier/visibility | Khả năng interception của proxy có thể khác | Method còn đi qua điểm chặn được hỗ trợ không? |

Lưu ý: sự tác động thực tế tùy **cơ chế AOP**. Với weaving tại `execution`, một lời gọi nội bộ vẫn có thể gặp advice nếu method đích đã được weave. Với **proxy ủy quyền**, lời gọi `this.method()` trong target thường không quay lại proxy. Không dùng một bảng refactor để thay thế việc kiểm tra engine đang chạy.

## 5. Thí nghiệm với pointcut dựa trên tên

### 5.1. Bản gốc

Giả sử mã nghiệp vụ trước khi refactor:

```java
package demo.orders;

public class OrderOperations {
    public String submit(String code) {
        return "accepted:" + code;
    }
}
```

Một pointcut minh họa theo AspectJ:

```java
execution(String demo.orders.OrderOperations.submit(String))
```

Kỳ vọng: chỉ `OrderOperations.submit(String)` được advice. Dấu vết nên cho thấy một match khi gọi đúng phương thức này, không match với `health`, `validate` hay method khác.

### 5.2. Refactor tên nhưng không đổi nghiệp vụ

Đổi `submit` thành `confirmOrder`; cập nhật tất cả caller để chương trình vẫn chạy. Nếu **quên sửa pointcut**, advice sẽ không bám vào method mới dù nghiệp vụ vẫn xử lý đúng.

```java
package demo.orders;

public class OrderOperations {
    public String confirmOrder(String code) {
        return "accepted:" + code;
    }
}
```

Dấu hiệu kiểm chứng:

```text
Before: business call=submit        expectedMatch=true  actualMatch=true
After:  business call=confirmOrder  expectedMatch=true  actualMatch=false
```

Đây là **dấu vết kỳ vọng minh họa**, không phải stdout của mã độc lập. Thay đổi đúng nên là cập nhật pointcut theo hợp đồng mới, hoặc chọn một cách đánh dấu ngữ nghĩa đáng tin hơn.

### 5.3. Nới wildcard quá rộng

Một phản ứng sai thường gặp là đổi thành:

```java
execution(* demo.orders.OrderOperations.*(..))
```

Nó “sửa” trường hợp thiếu match nhưng có thể bắt cả `health()`, `validate()` và những helper tương lai. Vì thế sau mỗi lần mở rộng, phải chạy **negative tests**. Nới wildcard chỉ hợp lý khi requirement thực sự áp dụng cho mọi method trong phạm vi đó.

## 6. Thí nghiệm Java 17 chạy độc lập: tên phương thức so với hợp đồng đánh dấu

Chương trình sau sử dụng **JDK dynamic proxy** để mô phỏng một AOP interceptor. Nó so sánh:

- Một điều kiện **mong manh** dựa vào tên method: `method.getName().equals("submit")`.
- Một điều kiện **ổn định theo hợp đồng**: interface method có annotation `@Observed`.

Trong thí nghiệm, `@Observed` được đặt **trên interface method** và `InvocationHandler` của JDK proxy nhận chính đối tượng `Method` đại diện cho interface method đó. Ví dụ này **không khẳng định** mọi công cụ weaving đều nhìn annotation trên interface giống JDK proxy; khi dùng weaving tại implementation execution phải khai báo và kiểm tra annotation tại method mà engine thực sự quan sát.

Lưu mã vào **`FragilePointcutDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class FragilePointcutDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observed {}

    interface LegacyOrders {
        @Observed String submit(String orderId);
        String submit(String orderId, int attempts);
    }

    interface RefactoredOrders {
        @Observed String confirmOrder(String orderId);
    }

    static final class LegacyService implements LegacyOrders {
        @Override
        public String submit(String orderId) {
            return "accepted:" + orderId;
        }

        @Override
        public String submit(String orderId, int attempts) {
            return "accepted:" + orderId + ":attempts=" + attempts;
        }
    }

    static final class RefactoredService implements RefactoredOrders {
        @Override
        public String confirmOrder(String orderId) {
            return "accepted:" + orderId;
        }
    }

    @SuppressWarnings("unchecked")
    static <T> T trace(Class<T> contract, T target) {
        return (T) Proxy.newProxyInstance(
            contract.getClassLoader(),
            new Class<?>[] {contract},
            (proxy, method, args) -> {
                boolean byName = method.getName().equals("submit");
                boolean byContract = method.isAnnotationPresent(Observed.class);
                System.out.println("pointcut method=" + method.getName()
                        + " name=" + byName
                        + " marker=" + byContract);
                try {
                    return method.invoke(target, args);
                } catch (InvocationTargetException error) {
                    throw error.getCause();
                }
            }
        );
    }

    public static void main(String[] args) {
        LegacyOrders original = trace(LegacyOrders.class, new LegacyService());
        RefactoredOrders renamed =
                trace(RefactoredOrders.class, new RefactoredService());

        System.out.println("result=" + original.submit("A1"));
        System.out.println("result=" + original.submit("A2", 2));
        System.out.println("result=" + renamed.confirmOrder("A3"));
    }
}
```

Lệnh chạy với JDK 17 trở lên:

```bash
javac FragilePointcutDemo.java
java FragilePointcutDemo
```

**Standard output chính xác:**

```text
pointcut method=submit name=true marker=true
result=accepted:A1
pointcut method=submit name=true marker=false
result=accepted:A2:attempts=2
pointcut method=confirmOrder name=false marker=true
result=accepted:A3
```

Phân tích:

1. **Bản gốc `submit(String)`:** cả điều kiện tên và annotation đều khớp; đây là positive control.
2. **Overload `submit(String,int)`:** điều kiện tên trả `true` dù overload không được đánh dấu `@Observed`. Nếu requirement chỉ áp dụng cho method được đánh dấu, đây là **false positive** do biểu thức name-based thiếu chính xác.
3. **Refactor `confirmOrder(String)`:** điều kiện tên trả `false` dù method được đánh dấu và vẫn thực hiện nghiệp vụ đặt hàng. Đây là **false negative** do đổi tên.
4. Matcher theo `@Observed` vẫn chọn đúng hai method được khai báo là cần theo dõi trong **mô hình JDK proxy này**; annotation thể hiện rõ ý định nghiệp vụ hơn tên method tình cờ.
5. Mã này chỉ **in kết quả matcher**, không tự thực thi một advice timing hay audit. Trong một engine AOP hoàn chỉnh, kết quả match sẽ được dùng để quyết định advice nào được chạy; thí nghiệm cố tình tách phép chọn khỏi side effect để dễ chẩn đoán.

**Giới hạn bắt buộc nhớ:** JDK dynamic proxy chỉ chặn lời gọi đi qua proxy của các interface tương ứng. Nó không cung cấp mọi loại join point của một bytecode weaver. Nếu annotation tồn tại **chỉ trên implementation method**, `method.isAnnotationPresent` tại `Method` interface trong ví dụ sẽ cho kết quả khác. Do đó việc chuyển từ tên sang annotation không tự động làm mọi pointcut an toàn; **vị trí annotation và semantics lookup** phải được kiểm thử.

## 7. Pointcut dựa vào annotation: bền hơn theo điều kiện nào?

Khi chính sách AOP gắn với một **khả năng/nghiệp vụ có chủ đích**, marker annotation hoặc một interface hợp đồng có thể ít phụ thuộc hơn vào việc đổi tên/package. Ví dụ ký pháp AspectJ sau chọn execution của **method thực sự mang annotation** `@Measured` trên vị trí mà weaver xét:

```java
// Mảnh cú pháp pointcut cho engine hỗ trợ @annotation:
execution(* demo..*.*(..)) && @annotation(demo.Measured)
```

Đoạn trên chỉ là **mẫu pointcut**, chưa phải một file Java chạy độc lập. Trong triển khai hoàn chỉnh cần khai báo `demo.Measured` với retention/target thích hợp theo engine, biên dịch aspect và bảo đảm các class mục tiêu thuộc vùng được weave.

Điều cần kiểm chứng khi dùng annotation:

- Annotation ở **method declaration của implementation**, interface, inherited method hay class? `@annotation` phụ thuộc sự kiện và metadata mà engine thực sự thấy.
- Annotation có được giữ ở bytecode/runtime theo nhu cầu matcher không? Java reflection runtime đòi hỏi `RetentionPolicy.RUNTIME`; bytecode weaver có thể có yêu cầu khác.
- Refactor sang method mới có mang lại annotation hoặc contract tương ứng không? Nếu developer quên sao chép annotation, matcher vẫn bỏ sót.
- Overload cần chính sách riêng hay tất cả overload đều được chọn? Đánh dấu cụ thể từng method giúp tránh wildcard quá rộng nhưng cần bảo đảm không quên method mới.
- Có cấm annotation lạm dụng ở helper hoặc method không thuộc nghiệp vụ không? Negative tests vẫn cần thiết.
- Annotation có được áp dụng đúng module/package và classloader mà weaver/agent xử lý không? Pointcut đúng nhưng không weave cũng không có advice.

Marker tốt nhất thường là **một phần của hợp đồng nghiệp vụ đã được review**, không phải nhãn trang trí. Với một yêu cầu thật sự định nghĩa theo vị trí kiến trúc (ví dụ mọi method của tầng persistence), pointcut theo type/package có thể phù hợp hơn annotation; chọn cách biểu đạt sát ý nghĩa yêu cầu.

## 8. Đổi package, type và hierarchy

### 8.1. Đổi package

Ví dụ pointcut:

```java
execution(* demo.orders..*.*(..))
```

Sau khi chuyển `demo.orders.OrderService` sang `demo.checkout.OrderService`, pointcut có thể bỏ sót. Mặt khác, chuyển một helper log vào `demo.orders` có thể khiến nó bị chọn ngoài dự kiến.

**Thực nghiệm:** tạo một bảng danh sách fully-qualified method signature trước và sau. Kiểm tra cả đường **include** và đường **exclude**: “method quan trọng còn được bắt không?” và “helper mới có bị bắt sai không?”. Nếu phạm vi package là hợp đồng kiến trúc có chủ ý, việc chuyển package cũng phải bao gồm thay đổi policy và test tương ứng.

### 8.2. Tách interface/implementation

Khi chuyển một method từ class cụ thể sang interface hoặc đổi implementation, biểu thức `execution(* demo.orders.OrderService.submit(..))` có thể không còn đại diện đúng cho method thực thi. Tùy ký pháp matching/subtype pattern và engine, việc chọn theo interface hợp đồng có thể bền hơn. Tuy nhiên **không mặc định** annotation khai báo trên interface được nhìn thấy tại implementation execution; đặc biệt annotation trên method không tự kế thừa theo cùng quy tắc `@Inherited` dành cho loại annotation trên class.

**Thực nghiệm:** đặt marker lần lượt trên interface method, implementation method và cả hai; chạy matcher tại join point thực. Ghi kết quả của từng trường hợp, không phán đoán từ Java reflection ở vị trí khác.

### 8.3. Overload, generic và bridge method

Giả sử thêm `submit(String,int)`, `submit(Order)` hoặc dùng generic interface với erased signature. Mẫu `submit(..)` có thể bắt thêm overload mới; mẫu `submit(String)` có thể không bắt overload mới; compiler có thể sinh bridge method ở một số cấu trúc kế thừa generics.

**Thực nghiệm:** liệt kê đầy đủ declaring class, method name, parameter descriptor, return type, modifiers và event kind của mỗi match. Một biểu thức match theo tên đơn thuần không đủ xác minh. Nếu engine có tùy chọn bỏ qua synthetic/bridge method, cần kiểm tra tài liệu và phép thử riêng; không áp dụng mặc định từ một engine sang engine khác.

## 9. Refactor call graph và khác biệt `call` / `execution`

### 9.1. Tách phương thức

Trước refactor:

```text
Caller -> OrderService.submit()
```

Sau refactor:

```text
Caller -> OrderFacade.submit()
            -> OrderCore.process()
                 -> Repository.save()
```

Nếu pointcut mở rộng bằng wildcard theo tên, việc thêm facade/helper có thể khiến advice chạy ở **hai tầng**. Nếu pointcut cố định vào `OrderService.submit`, lời gọi nghiệp vụ mới có thể không còn match. Cần xác định ý nghĩa mong muốn: đo **đầu vào use case**, một thao tác persistence hay mỗi lần thực thi nội bộ?

### 9.2. Phân biệt call-site và execution-site

- `call` quan sát lệnh gọi tại caller (nếu site được weave). Khi refactor chuyển lời gọi sang một class/caller không được weave, join point có thể biến mất khỏi phạm vi giám sát.
- `execution` quan sát thân method (nếu thân đã weave). Khi caller chuyển nơi gọi nhưng vẫn đi vào cùng thân method, execution join point vẫn có thể được quan sát.
- Proxy interception thường phụ thuộc **đường gọi đi qua proxy**, không tương đương việc dệt method execution. Ví dụ target gọi `this.process()` trong delegation proxy thường bypass proxy, nhưng woven execution có thể vẫn khớp.

**Bài tập:** viết rõ lời gọi đang được đo nằm ở caller hay callee trước khi đổi cấu trúc code; sau đó vẽ trace từng phương án. Đừng kết luận “pointcut sai” khi không có bằng chứng interception/weaver đã chạm join point thực.

### 9.3. Callback, lambda và bất đồng bộ

Khi chuyển từ lời gọi đồng bộ trực tiếp sang callback, executor hoặc một chuỗi future, thời điểm gọi, thread và receiver có thể thay đổi. Một pointcut `execution` trên method nghiệp vụ có thể vẫn match ở thread mới; một `call` pointcut ở caller cũ có thể không match call site mới; proxy reference có thể bị bỏ qua trong callback.

Nếu advice chỉ đo thời gian đến khi method trả một `CompletionStage`, nó chưa đo thời gian hoàn tất tác vụ. Trong bài tập “thay đổi cấu trúc”, phải đo chính xác **join point coverage**, sau đó mới bàn đến semantics latency/outcome.

## 10. Quy trình thử thay đổi có kiểm soát

### Pha A — chốt trạng thái ban đầu

1. Chọn một pointcut hiện hữu và ghi rõ vì sao nó phải chọn những method nào.
2. Tạo danh sách **positive cases** (phải match) và **negative cases** (không match).
3. Bật diagnostics của AOP engine hoặc một tracer tạm thời để ghi chính xác method/event được chọn.
4. Ghi kết quả baseline: số match, tên signature, advice invocation count và các outcome quan trọng.
5. Giữ artifact/version/config weave cụ thể để tái hiện kết quả.

### Pha B — mỗi lần một refactor

1. Đổi **một chiều duy nhất**: tên, package, overload, annotation, hierarchy hoặc call graph.
2. Kiểm tra chương trình nghiệp vụ vẫn đúng trên input tương đương.
3. Chạy lại positive/negative tests. So sánh tập match theo **hợp đồng nghiệp vụ**, không chỉ theo số lượng.
4. Xác định thiếu match hay thừa match; chỉ ra thay đổi cấu trúc nào gây ra.
5. Quyết định sửa pointcut, sửa annotation/hợp đồng, sửa phạm vi weaving hoặc đổi vị trí chặn.
6. Lặp lại với một refactor khác sau khi đã lưu kết quả và kết luận.

### Pha C — cố tình tạo hai lỗi

**False negative:** đổi `submit` thành `confirmOrder` nhưng giữ matcher `name == "submit"`; kết quả `false` dù use case thuộc tập phải chặn.

**False positive:** thêm overload `submit(String,int)` không thuộc policy; matcher `name == "submit"` cho `true` và chọn sai method.

Chương trình `FragilePointcutDemo` ở trên tạo sẵn hai trường hợp này. Có thể mở rộng để so sánh matcher theo annotation ở interface, implementation hoặc signature cụ thể.

### Pha D — sửa và chứng minh hồi quy

Sau khi sửa, chạy lại toàn bộ ma trận; điểm sửa được coi là đạt khi:

- Mọi positive case khớp, kể cả sau các refactor nằm trong phạm vi cần hỗ trợ.
- Mọi negative case không khớp; helper/health method không bị bắt ngoài ý muốn.
- Advice chạy đúng một lần theo mỗi invocation hợp lệ, hoặc số lần cụ thể đã được thiết kế.
- Kết quả và exception của nghiệp vụ không đổi nếu advice là quan sát thuần.
- Test chạy trên **artifact đã weave/proxy setup đúng** với môi trường triển khai.

## 11. Cách kiểm tra thực tế trong build và runtime

Một bộ test có hai tầng:

| Tầng | Điều chứng minh được | Giới hạn |
| --- | --- | --- |
| Kiểm thử predicate/matcher | Với một signature + annotation + args, matcher chọn đúng theo hợp đồng | Không chứng minh class/call site thực được instrument/weave |
| Kiểm thử tích hợp AOP | Advice thực sự chạy ở join point trong bản build/launcher đúng | Có thể khó cô lập lỗi matcher khỏi cấu hình weaving nếu thiếu diagnostics |

Đối với AspectJ/bytecode weaving, bật thông tin weave khi build/launch, đối chiếu class nằm trong source roots, `-inpath`, `-aspectpath` hoặc phạm vi load-time weaving tương ứng. Đối với proxy, kiểm tra receiver thực tại call site và vị trí interceptor. Sau refactor, class mới có thể không còn trong phạm vi build task/agent/classloader, khiến một pointcut đúng vẫn không chạy.

Một dạng trace hữu ích:

```text
revision=before event=execution method=demo.orders.OrderService.submit(String) expected=true actual=true
revision=after event=execution method=demo.checkout.OrderService.confirmOrder(String) expected=true actual=false
revision=after event=execution method=demo.checkout.DebugHelper.flush() expected=false actual=true
```

Đây là **định dạng trace minh họa**. Trước khi báo pointcut mong manh, phải xác nhận `event` và `method` là đúng join point hiện hữu; không so sánh hai tên method khác nhau bằng chuỗi raw đơn giản nếu cả hai đại diện cùng hành vi.

Có thể lưu một “coverage manifest” từ build hoặc integration test chứa join point ID + policy ID, rồi so sánh với baseline. Khi một refactor thay đổi chữ ký, cần ánh xạ **ngữ nghĩa** từ method cũ sang mới trước khi báo thiếu/thừa match.

## 12. Tiêu chí đánh giá sự ổn định của pointcut

Một pointcut tốt là pointcut **đúng phạm vi thay đổi mong đợi**, không phải pointcut match được nhiều nhất.

### 12.1. Dấu hiệu tương đối bền

- Quy tắc dựa trên ý nghĩa nghiệp vụ được biểu đạt tường minh trong annotation/hợp đồng có người sở hữu.
- Pointcut có ranh giới đủ hẹp và **negative tests** cho helper, logging, lifecycle method.
- Các điều kiện type/annotation/args tương ứng với join point kind mà engine thực sự quan sát.
- Build/CI kiểm tra cả AOP integration sau refactor, không chỉ compile/test business logic.
- Việc đổi method/package có checklist cập nhật policy, marker và weave scope.
- Phạm vi include/exclude được kiểm soát bằng review thay vì wildcard tùy tiện.

### 12.2. Dấu hiệu mong manh

- Bám vào package/tên ngẫu nhiên không phản ánh hợp đồng.
- Dùng wildcard để “tránh sửa aspect mỗi khi refactor”, nhưng không có test chặn false positive.
- Matcher dựa vào reflection ở interface còn marker được đặt ở implementation mà không có chính sách lookup rõ ràng.
- Chỉ test “advice có chạy ở một ca” mà không xác minh nhiều ca và số lần.
- Thay đổi cấu trúc source nhưng không chạy lại weaving task hoặc không kiểm tra artifact cuối.
- Trông cậy vào thứ tự/loại method sinh bởi compiler mà không khóa toolchain và không có test.
- Không phân biệt nested calls, retries, overload và invocation riêng biệt.

**Lưu ý về sự cân bằng:** biểu thức theo annotation cũng có thể mong manh nếu annotation bị quên khi tách method; biểu thức theo package có thể bền nếu package **chính là ranh giới kiến trúc được quản lý**. Tính bền vững phụ thuộc việc rule bám vào yêu cầu thật sự hay tình cờ bám vào hình dạng code hiện tại.

## 13. Bài tập bổ sung có tiêu chí chấm rõ ràng

### Bài A — đổi tên nhưng giữ nghĩa

Từ `FragilePointcutDemo`, đổi `confirmOrder` thành `placeOrder` và giữ `@Observed`. Dự đoán từng kết quả trước khi chạy. Chứng minh name-based matcher vẫn false còn marker matcher vẫn true. Sau đó gỡ marker và quan sát lỗi mới.

**Đạt:** giải thích được vì sao annotation chỉ bền khi được duy trì như hợp đồng.

### Bài B — thêm overload

Thêm vào `LegacyOrders` một method `submit(long orderId)` không có marker và triển khai tương ứng. Kiểm tra matcher tên có thể bắt tất cả overload, trong khi chính sách chỉ chọn method đánh dấu. Nâng predicate name-based lên so đủ parameter types để sửa trường hợp cụ thể, sau đó tự đánh giá predicate còn mong manh trước refactor signature hay không.

**Đạt:** có một false positive và một trường hợp được sửa; hiểu sự đánh đổi giữa precision và độ bền.

### Bài C — đổi package

Tạo hai class có cùng role nhưng thuộc `demo.orders` và `demo.checkout`. Định nghĩa một biểu thức chọn theo package, chạy test trước/sau khi chuyển. Tiếp theo thêm logger helper vào package được chọn để kiểm tra negative case.

**Đạt:** có bảng expected/actual và chứng minh không vô tình bắt logger helper.

### Bài D — thay đổi call graph

Tách phương thức nghiệp vụ thành `Facade.accept()` và `Processor.execute()`. Cho pointcut bắt theo tên `execute`, so advice count với pointcut bắt ở facade. Dùng hai cơ chế quan sát khác nhau nếu công cụ hỗ trợ `call` và `execution`, rồi phân tích chính xác vùng đang đo.

**Đạt:** chỉ ra được trường hợp match ở hai tầng và không làm tăng side effect nghiệp vụ.

### Bài E — chuyển annotation

Đặt marker trên interface method, implementation method, cả hai và không bên nào. Chạy thử với proxy reflection và weaving execution (nếu có toolchain). Ghi chính xác event kind và vị trí method metadata được đọc.

**Đạt:** không đưa kết luận “annotation interface luôn được kế thừa sang implementation”.

### Bài F — CI guard chống regression

Tạo bảng dữ liệu test nhỏ:

```text
case                         expectedMatch
LegacyOrders.submit(String)  true
LegacyOrders.submit(String,int) false
RefactoredOrders.confirmOrder(String) true
DebugHelper.flush()          false
HealthService.ping()         false
```

Gắn assertion ở matcher level và integration level. Với refactor mới, test phải fail khi một method bắt buộc biến mất khỏi tập match hoặc khi method ngoài policy bị chọn. Dữ liệu test cần thể hiện **ý nghĩa nghiệp vụ**, không tự sinh expected từ pointcut đang kiểm tra.

## 14. Những lỗi suy luận phổ biến

1. **“Build thành công thì pointcut đúng.”** Sai: biểu thức có thể không match gì mà quá trình biên dịch vẫn thành công.
2. **“Advice không chạy tức pointcut sai.”** Có thể caller không đi qua proxy, class/call site chưa weave hoặc advice chain bị tắt.
3. **“Wildcard càng rộng thì càng tránh bug refactor.”** Nó có thể giảm false negative nhưng tăng false positive nghiêm trọng.
4. **“Đổi method chỉ là rename nên AOP không ảnh hưởng.”** Pointcut theo signature/tên phụ thuộc trực tiếp vào rename.
5. **“Có annotation trên interface là weaving ở implementation luôn nhìn thấy.”** Không có quy tắc chung như vậy cho mọi engine/event.
6. **“Cùng tên method là cùng join point.”** Overload, bridge methods, event kind và declaring class có thể khác.
7. **“Tăng advice count là chắc chắn có lỗi.”** Tập join point dự kiến có thể lớn hơn do yêu cầu mới; so với hợp đồng, không chỉ với một con số cũ.
8. **“Chỉ có một positive test là đủ.”** Không bắt được lỗi wildcard chọn nhầm helper hoặc overload.
9. **“Self-invocation luôn làm advice mất.”** Điều đó phụ thuộc mô hình proxy/weaving; không khái quát.
10. **“Refactor source và rebuild không làm thay đổi weaving.”** Build graph, classloader, source roots, aspectpath/inpath và output artifact có thể thay đổi.
11. **“Thêm logger để debug vô hại.”** Một helper mới nằm trong vùng pointcut có thể tạo recursion hoặc metric bùng nổ.
12. **“Dữ liệu test có thể suy từ pointcut.”** Như vậy sẽ không có oracle độc lập để phát hiện matcher sai.

## 15. Checklist nộp bài

- [ ] Mô tả chính xác chức năng nghiệp vụ nào phải chịu AOP và sự kiện nào là join point.
- [ ] Chụp baseline các positive và negative match trước khi refactor.
- [ ] Đã refactor ít nhất **tên method**, **overload**, và một trong **package/hierarchy/call graph**.
- [ ] Có ít nhất một false negative và một false positive được giải thích từ pointcut.
- [ ] Đã chạy chương trình Java 17 và hiểu vì sao marker annotation trên interface được thấy qua JDK proxy.
- [ ] Không suy luận mọi bytecode weaver có cùng semantics annotation/interface.
- [ ] Đã kiểm tra đúng đường proxy/weaving, signature, event kind và artifact thực chạy.
- [ ] Đã sửa biểu thức/marker theo hợp đồng rõ ràng, không dùng wildcard tùy tiện.
- [ ] Positive và negative tests đều PASS sau refactor.
- [ ] Không có advice đệ quy, chạy lặp ngoài thiết kế, đổi return/exception hoặc nhân đôi side effect.
- [ ] Báo cáo có bảng `before/after` với `expected/actual` và giải thích nguyên nhân.

**Kết luận thực hành:** Khi refactor, đừng chỉ hỏi “mã Java vẫn chạy không?”. Hãy hỏi thêm **“tập join point được chọn có còn phản ánh đúng hợp đồng AOP hay không?”**. Một pointcut tốt phải được chứng minh bằng **cả ca được chọn và ca bị loại**, trên đúng cơ chế weaving/interception đang triển khai.
