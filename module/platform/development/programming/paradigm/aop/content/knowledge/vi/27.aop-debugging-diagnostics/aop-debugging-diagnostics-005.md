# Phân biệt pointcut không khớp và lời gọi không đi qua proxy trong AOP

## 1. Vấn đề: cùng không thấy advice, nhưng có hai nguyên nhân khác nhau

Khi một advice không xuất hiện trong log hoặc một kiểm tra cắt ngang không chạy, kết luận “pointcut viết sai” có thể dẫn đến sửa nhầm chỗ. Với AOP dùng proxy/interceptor, một lời gọi chỉ đi qua advice khi **thực sự chạm tới đường chặn** và **được bộ chọn join point/pointcut chấp nhận**. Hai lỗi cần phân biệt:

1. **Pointcut không khớp:** lời gọi **đã đi vào** proxy/interceptor nhưng phép chọn không áp dụng advice cho sự kiện này; có thể sai tên/phạm vi phương thức, sai loại join point, điều kiện annotation/tham số không đạt, hoặc loại sự kiện không được hỗ trợ.
2. **Lời gọi không đi qua proxy:** phương thức đích vẫn chạy nhưng caller nắm tham chiếu đối tượng gốc, gọi nội bộ trên `this`, đi theo nhánh bỏ qua wrapper hoặc chạy ở nơi chưa được chặn. Pointcut có thể đúng với phương thức ấy, nhưng không có cơ hội được đánh giá trên đường gọi thực tế.

Cần thêm trạng thái thứ ba: **đã đến interceptor, matcher báo khớp, nhưng advice vẫn không chạy**. Đây là lỗi ở cấu hình advice/chuỗi interceptor, thứ tự, điều kiện runtime, nhánh exception hoặc bản thân cơ chế quan sát; không nên ép thành một trong hai kết luận trên.

> Phạm vi bài: các khái niệm Aspect-Oriented Programming (AOP) nói chung, đặc biệt là **proxy-based AOP** so với **weaving vào mã**. Không có một quy tắc hoạt động duy nhất áp dụng cho mọi bộ công cụ AOP.

## 2. Mô hình hai tầng: bắt được lời gọi rồi mới chọn advice

Một pipeline AOP dựa trên proxy có dạng khái niệm:

```text
Caller
  |
  v
Reference đến proxy? -- KHÔNG --> Target.method() (không có proxy interception)
  |
 CÓ
  v
Proxy / interception boundary
  |
  v
Có nhận được loại lời gọi này? -- KHÔNG --> không tạo join point phù hợp
  |
 CÓ
  v
Đánh giá pointcut / matcher
  |
  +-- FALSE --> Target.method() (bỏ qua advice tương ứng)
  |
 TRUE
  v
Advice chain --> proceed / gọi Target.method()
```

Phân biệt các khái niệm:

| Khái niệm | Vai trò và ý nghĩa khi chẩn đoán |
| --- | --- |
| **Target** | Đối tượng chứa logic nghiệp vụ; gọi trực tiếp target có thể hoàn toàn bỏ qua proxy. |
| **Proxy** | Đối tượng trung gian đóng vai trò điểm đi vào interception; tên biến là `service` không chứng minh nó là proxy. |
| **Join point** | Sự kiện có thể tác động: gọi phương thức, thực thi phương thức, đọc/ghi trường, khởi tạo... tùy mô hình AOP. |
| **Pointcut** | Quy tắc nhận diện một tập join point, có thể gồm điều kiện tĩnh và runtime. |
| **Advice** | Đoạn xử lý `before`, `after`, `around`... được gắn vào join point đã chọn. |
| **Weaving** | Cách đưa hành vi AOP vào luồng thực thi, ví dụ biến đổi bytecode hoặc can thiệp trong biên dịch/nạp lớp. |

**Công thức tư duy:** trong mô hình proxy, thiếu advice có thể do **đường gọi không được chặn** hoặc **interceptor có chạy nhưng pointcut không chọn**. Vì vậy, dấu hiệu “không thấy dòng log của advice” **không đủ** để phân biệt.

Một hệ thống có thể đánh giá pointcut sớm để quyết định có tạo proxy hay không; không phải mọi bộ công cụ đều gọi bộ matcher trên **mọi** lần invocation. Sơ đồ trên biểu diễn các điều kiện logic, không khẳng định thứ tự triển khai nội bộ của mọi thư viện.

## 3. Trường hợp A — điểm vào đã được chặn, pointcut không khớp

Một số nguyên nhân thường gặp:

### 3.1. Sai signature, phạm vi hoặc kiểu phương thức

Pointcut dự kiến chọn `InvoiceService.submit(..)` nhưng code gọi `InvoiceService.preview(..)`; hoặc đối tượng nằm ở package khác; hoặc chữ ký có overload khác kiểu tham số/kiểu trả về. Tên method tương tự nhau chưa chứng minh cùng một signature.

Kiểm tra **tên lớp khai báo**, method name, parameter types, kiểu trả về, modifier, và loại join point đúng với DSL đang dùng. Với generic, Java có thể sinh **bridge method** để duy trì tương thích type erasure; compiler-generated member cũng cần được tính đến nếu matcher hoặc weaver quan sát các method đó.

### 3.2. Nhầm `call` và `execution`

Trong mô hình AOP hỗ trợ hai loại join point này:

- `call` là sự kiện tại **vị trí thực hiện lời gọi** (caller); cần vị trí gọi thuộc vùng được weave/quan sát.
- `execution` là sự kiện tại **việc thực thi thân phương thức** (callee); cần thân phương thức tương ứng được weave/quan sát.

Ví dụ ký pháp pointcut kiểu AspectJ, **chỉ để đọc ý nghĩa**, không phải chương trình Java độc lập:

```java
// Chọn vị trí gọi process(...) trong mã được weave:
call(* demo.Payments.process(..))

// Chọn nơi thực thi thân process(...) trong mã được weave:
execution(* demo.Payments.process(..))
```

Một ứng dụng chỉ instrument phương thức thực thi không tự nhiên tạo ra mọi join point `call` tại các caller, và ngược lại. Nếu nền tảng interception chỉ hỗ trợ method invocation trên proxy, cú pháp `call`/`execution` của công cụ weaving cũng không được mặc định hỗ trợ. Chẩn đoán phải bắt đầu từ tập join point **thực tế được AOP engine cung cấp**.

### 3.3. Điều kiện annotation, đối tượng hoặc đối số không đạt

Pointcut có thể bị ràng buộc bởi annotation, subtype, trạng thái runtime hoặc giá trị tham số. Chẳng hạn, matcher yêu cầu một annotation trên **implementation method**, còn phép tra cứu metadata lại được thực hiện trên **interface method** (hoặc chiều ngược lại). Annotation không phải lúc nào cũng được kế thừa/hiển thị theo cách mà người viết pointcut dự đoán.

Một pointcut có thể khớp với một overload nhưng không khớp overload khác; với runtime type conditions, cùng một method cũng có thể khớp ở lần gọi này và không khớp ở lần gọi khác. Khi điều tra, ghi rõ cả **static signature**, **runtime receiver**, **args**, loại pointcut và vị trí metadata được đọc.

### 3.4. Điều kiện loại trừ quá rộng hoặc thiếu điều kiện

Các phủ định kiểu `!within(...)`, phạm vi package, cflow và điều kiện loại trừ có thể khiến đúng method bị loại. Khi đọc biểu thức phức tạp, hãy tách nó thành từng vế và ghi kết quả từng vế đối với **một join point cụ thể**. Tối giản biểu thức trong phép thử nhỏ là cách xác minh hiệu quả, nhưng bản cuối phải giữ chính xác ranh giới nghiệp vụ.

### 3.5. Làm thế nào chứng minh thật sự là lỗi match?

Đặt một log chẩn đoán **ở biên interceptor**, **trước khi áp dụng điều kiện pointcut**, chẳng hạn:

```text
interceptor.enter method=preview
pointcut.evaluate method=preview result=false
target.enter method=preview
```

Đây là bằng chứng lời gọi đã đi qua interceptor; chỉ có điều advice không được chọn. Nếu bộ công cụ không phơi bày matcher trực tiếp, tạo một interceptor “bắt mọi lời gọi hỗ trợ” **tạm thời**, có phạm vi hẹp và dấu vết tối thiểu, rồi so sánh. Không cần dựa vào log bên trong advice đang mất tích.

## 4. Trường hợp B — lời gọi bỏ qua proxy/interception boundary

Một proxy theo kiểu **ủy quyền** thường giữ một đối tượng target bên trong. Caller gọi phương thức qua proxy để vào advice; caller gọi trực tiếp target thì đi thẳng tới nghiệp vụ.

### 4.1. Caller giữ tham chiếu target thô

```text
Client -> proxy.process()  -> interceptor -> advice (nếu match) -> target.process()
Client -> target.process() -------------------------------> target.process()
```

Cùng `target.process()` được thực thi ở cả hai đường; chỉ đường đầu tạo cơ hội cho proxy advice. Những nơi dễ giữ sai tham chiếu: tự tạo target bằng `new` rồi chuyển đi, expose target qua field/getter, đăng ký callback bằng target, hoặc một đối tượng khác đã nhận target trước khi lớp proxy được bọc vào.

Để xác minh, kiểm tra đối tượng thực sự mà **caller nhận** tại thời điểm gọi, không chỉ biến được đặt tên “proxy” ở đoạn cấu hình.

### 4.2. Self-invocation trên `this`

Trong một proxy ủy quyền, khi `proxy.outer()` chuyển tới `target.outer()`, bên trong `target.outer()` có thể gọi `this.inner()`. Lệnh `this.inner()` thực thi trên target, **không quay lại proxy**; advice trên `inner` có thể vắng mặt dù pointcut chọn đúng `inner`.

```text
proxy.outer()
  -> interceptor thấy outer
     -> target.outer()
        -> this.inner()   // gọi thẳng trong target, không qua proxy
```

Đây là tình huống kinh điển để tạo phép thử **cùng một phương thức**: gọi `proxy.inner()` có advice, còn gọi `proxy.outer()` làm `this.inner()` chạy mà không có advice của inner.

**Giới hạn quan trọng:** self-invocation **không luôn luôn** bypass AOP ở mọi cơ chế. Weaving tại `execution` của phương thức có thể chặn được lời gọi nội bộ vì instrumentation ở thân phương thức. Một proxy **kế thừa và override** cũng có semantics khác proxy **ủy quyền**; lời gọi ảo trên `this` có thể đi qua override nếu receiver thực sự là subclass proxy. Hãy kiểm tra cơ chế cụ thể và tham chiếu thực tế trước khi chẩn đoán.

### 4.3. Giới hạn kiểu proxy và method

Với `java.lang.reflect.Proxy` trong JDK, proxy thực hiện **các interface được khai báo**; một method chỉ có trên concrete class nhưng không có trong interface tương ứng không thể được gọi qua biến interface proxy đó. Phương thức `Object` (như `equals`, `hashCode`, `toString`) có các quy tắc dispatch riêng cần xét khi logging/đo lường.

Với proxy kiểu subclass/override, `final` method không thể được override, `private` method không thể bị override, `static` method không phải virtual dispatch, constructor không phải một method instance để override. Nhưng đừng khái quát rằng “method final không bao giờ được aspect can thiệp”: một **interface-based delegation proxy** vẫn có thể intercept lời gọi trước khi ủy quyền tới implementation có method final; cơ chế weaving vào bytecode cũng có khả năng khác.

Một số interceptor chặn ở biên method, không chặn field access, constructor execution hoặc call site. Nếu thao tác cần theo dõi nằm ngoài tập join point hỗ trợ, phải đổi cơ chế AOP hoặc thiết kế điểm chặn — việc sửa chuỗi ký tự pointcut có thể không giải quyết được.

### 4.4. Không nên đánh đồng “không qua proxy” với “không có weaving”

Với AOP dùng bytecode weaving, advice có thể được chèn vào `execution` của một phương thức. Khi đó lời gọi đến từ target, từ `this`, hoặc qua tham chiếu bất kỳ vẫn có thể gặp advice **nếu phương thức được weave và join point khớp**. Điều tra kiểu weaving cần kiểm tra lớp đã biến đổi, classloader, thời điểm load, cấu hình weave, thay vì chỉ kiểm tra có proxy hay không.

## 5. Ví dụ Java 17 chạy độc lập: tách hai lỗi chỉ bằng một phép thử

Ví dụ dưới đây tự xây một **interface delegation proxy** bằng Java Reflection. Đây là mô phỏng nguyên tắc AOP: `interceptor` là nơi quan sát lời gọi, điều kiện `method.getName().equals("detail")` đóng vai trò pointcut, và dòng `advice: detail` đại diện cho advice.

Lưu toàn bộ mã thành **`ProxyDiagnosisDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public final class ProxyDiagnosisDemo {
    public interface Work {
        void entry();
        void detail();
        void skipped();
    }

    public static final class WorkImpl implements Work {
        @Override
        public void entry() {
            System.out.println("target.entry");
            detail(); // self-invocation trên target, không qua proxy ủy quyền
        }

        @Override
        public void detail() {
            System.out.println("target.detail");
        }

        @Override
        public void skipped() {
            System.out.println("target.skipped");
        }
    }

    public static void main(String[] args) {
        Work target = new WorkImpl();
        Work proxy = (Work) Proxy.newProxyInstance(
            Work.class.getClassLoader(),
            new Class<?>[] { Work.class },
            (proxyInstance, method, methodArgs) -> {
                boolean matches = method.getName().equals("detail");
                System.out.println(
                    "interceptor: " + method.getName() + " match=" + matches
                );
                if (matches) {
                    System.out.println("advice: detail");
                }
                try {
                    return method.invoke(target, methodArgs);
                } catch (InvocationTargetException ex) {
                    throw ex.getCause();
                }
            }
        );

        System.out.println("1. proxy.skipped()");
        proxy.skipped();

        System.out.println("2. proxy.detail()");
        proxy.detail();

        System.out.println("3. target.detail()");
        target.detail();

        System.out.println("4. proxy.entry()");
        proxy.entry();
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac ProxyDiagnosisDemo.java
java ProxyDiagnosisDemo
```

Kết quả chuẩn:

```text
1. proxy.skipped()
interceptor: skipped match=false
target.skipped
2. proxy.detail()
interceptor: detail match=true
advice: detail
target.detail
3. target.detail()
target.detail
4. proxy.entry()
interceptor: entry match=false
target.entry
target.detail
```

**Diễn giải từng ca:**

1. `proxy.skipped()`: interceptor **đã chạy** (có dòng `interceptor`) nhưng matcher trả `false`; đây là **pointcut không khớp**.
2. `proxy.detail()`: interceptor chạy, matcher `true`, advice chạy; đây là **đường chuẩn** để chứng minh method `detail` *có thể* được advice bắt.
3. `target.detail()`: chỉ có `target.detail`, **không có `interceptor`**; cùng method `detail` có khả năng khớp nhưng caller đi **thẳng vào target**, tức bypass proxy.
4. `proxy.entry()`: interceptor thấy `entry`, matcher `false` nên không có advice trên `entry`; trong thân `entry`, `this.detail()` chạy trực tiếp trên target, do đó **không thấy** dòng interceptor riêng của `detail` dù nó là method được chọn khi gọi qua proxy. Một lần gọi này minh họa cả việc `entry` không khớp và self-invocation của `detail` bypass proxy.

Điểm thú vị: `method.invoke(target, ...)` chuyển cuộc gọi từ proxy sang target. Khi code của target gọi một method khác bằng `this`, nó không quay lại InvocationHandler. Mã tự động bỏ nguyên nhân do cấu hình môi trường cụ thể, giúp quan sát riêng cơ chế.

**Cần nhớ giới hạn ví dụ:** đây là `java.lang.reflect.Proxy` chuẩn của JDK, không phải một engine AOP hoàn chỉnh. Nó chỉ chứng minh quy tắc về điểm vào, matcher và self-invocation ở proxy ủy quyền. `Proxy` chỉ định nghĩa chặn lời gọi thông qua các interface được liệt kê; không thể dùng nó để suy luận trực tiếp về bytecode weaving.

## 6. Ma trận kiểm chứng phân biệt nguyên nhân

Đừng kiểm tra mỗi ca “đang lỗi”. Tạo bốn đường gọi trên **cùng method cần quan sát**, nếu kiến trúc cho phép:

| Ca thử | Đường gọi | Interceptor probe | Pointcut | Kết luận |
| --- | --- | --- | --- | --- |
| A | Gọi method khớp qua proxy | Có | true | Advice phải có cơ hội chạy; nếu không, kiểm tra advice chain/activation. |
| B | Gọi method không khớp qua proxy | Có | false | Chứng cứ của **pointcut mismatch**, không phải bypass. |
| C | Gọi method khớp trực tiếp target | Không | Không được đánh giá ở biên proxy | Chứng cứ của **bypass proxy** cho đường gọi đó. |
| D | Gọi qua proxy một method A, A gọi method B trên `this` của target | Có cho A; không có cho B | Tùy A, B | Nếu B khớp khi gọi trực tiếp proxy nhưng không được chặn ở đây: **self-invocation bypass**. |

Trên công cụ không cho log trực tiếp ở điểm intercept, có thể dùng một interceptor thử nghiệm cực hẹp với predicate `true` hoặc thống kê invocation trên boundary đang điều tra. Nếu một interceptor khác chạy còn advice mong muốn không chạy, đã có chứng cứ đường gọi không bỏ qua **toàn bộ** interception boundary; tuy nhiên cần đối chiếu nó có thực sự ở **cùng boundary** hay không.

**Không suy luận vòng tròn:** “pointcut đang đúng” chỉ dựa trên chữ ký mà chưa chứng minh nó match theo metadata/runtime của engine. “Có proxy” chỉ dựa trên việc đối tượng từng được tạo proxy mà chưa chứng minh caller đang giữ proxy tại thời điểm gọi.

## 7. Quy trình chẩn đoán từng bước

### Bước 1 — Chứng minh nghiệp vụ có thật sự được chạy

Đầu tiên ghi marker ngay trong thân method hoặc kiểm chứng side effect/kết quả. Nếu target chưa bao giờ chạy, “thiếu advice” có thể chỉ do luồng điều khiển không đến đó. Hạn chế marker gây side effect; tránh dùng `toString()` phức tạp của đối tượng tham số ngay trong interceptor vì việc format log có thể lại kích hoạt code bị advice.

Ghi ít nhất: `requestId`, `invocationId`, `thread`, signature, timestamp/sequence, và outcome. Cần phân biệt “một request” với “một method invocation” vì một request có thể gọi cùng method nhiều lần.

### Bước 2 — Xác định đúng caller và reference

Lần từ call site thực tế đến receiver thực tế:

- Caller đang nắm **proxy** hay **target gốc**? Reference có bị thay thế, cache, truyền qua callback hoặc tự tạo bằng `new` không?
- Đường gọi có đi qua interface/decorator/delegating wrapper được thiết kế không?
- Method được gọi từ bên ngoài hay từ chính target thông qua `this`?
- Receiver có nằm đúng phạm vi lớp/module/classloader mà cơ chế interception quản lý không?

Nếu đang dùng `java.lang.reflect.Proxy`, có thể kiểm tra:

```java
boolean jdkProxy = Proxy.isProxyClass(receiver.getClass());
```

Đoạn này là **mảnh minh họa**, giả sử `receiver` là đối tượng đã xác định; không phải chương trình độc lập. Kết quả `false` chỉ có nghĩa đối tượng ấy **không phải** lớp proxy do `java.lang.reflect.Proxy` tạo, không chứng minh nó không thuộc một loại proxy khác. Để kiểm tra identity, `receiver == expectedProxy` đáng tin hơn so sánh `equals()` do `equals()` có thể được override hoặc intercept.

### Bước 3 — Đặt “probe” trước pointcut, rồi so event và matcher

Các dấu vết tối thiểu theo thứ tự:

```text
caller: BEFORE call              (biết call site)
interceptor: ENTER method=...    (đã vào interception boundary)
pointcut: MATCH=true|false      (khi engine phơi bày phép đánh giá)
advice: ENTER advice=...         (advice được gọi)
target: ENTER method=...         (logic nghiệp vụ chạy)
```

Ghi các marker có correlation ID chung. Với một số engine, matcher được tính trước khi interceptor tạo ra, nên không phải lúc nào có đủ cả năm marker; khi đó dùng diagnostics về danh sách method được chặn, loại join point và bảng cấu hình proxy/weaving do engine cung cấp.

Cách đọc:

- Có `target`, **không có interceptor**, trong khi caller được xác nhận đã gọi đúng target: khả năng cao là bypass/không instrument; cần xác minh probe đã được gắn ở đúng boundary.
- Có `interceptor`, có `MATCH=false`: **pointcut không khớp**.
- Có `interceptor`, có `MATCH=true`, thiếu `advice`: kiểm tra advice registration, chain, điều kiện bật/tắt, lỗi trước advice.
- Có `advice` mà log dự kiến không thấy: lỗi có thể ở nhánh logic logging, appender/filter, ngoại lệ hoặc thời điểm flush; không phải tự động do AOP.
- Không có `target` lẫn `interceptor`: tìm nhánh nghiệp vụ trước; không thể từ đó kết luận pointcut.

### Bước 4 — Phân rã pointcut theo **join point thực tế**

Ghi rõ:

1. **Event kind:** `call` hay `execution`, hoặc method interception không phân biệt hai loại.
2. **Static signature:** declaring class, method name, return type, parameter types; xét override/bridge/overload.
3. **Runtime receiver:** proxy class, implementation class, classloader.
4. **Annotation/type/args:** đọc annotation trên interface hay implementation? Matcher xử lý generic/erasure ra sao? Có `args`/dynamic condition không?
5. **Loại trừ:** pointcut bị loại bởi `within`, `!within`, control flow hoặc điều kiện khác?
6. **Vùng weaving:** caller/callee có được weave không, lớp đã load trước khi cấu hình instrumentation có hiệu lực chưa?

Dùng một join point cụ thể làm đầu vào để thử từng vế; chỉ khi hiểu vì sao nó bị loại mới sửa pointcut chính thức. Không nới pointcut toàn hệ thống chỉ để “bắt cho được”, vì như vậy có thể tạo đệ quy logging/audit hoặc nhân đôi side effect.

### Bước 5 — Tái hiện bằng phép thử có kiểm soát

Với proxy ủy quyền, thử cùng một method qua reference proxy và reference target (nếu quyền truy cập/kiến trúc thử nghiệm cho phép). Giữ input, thread, trạng thái và feature flags tương đương; so **số lần target chạy**, **số lần interceptor vào** và **số lần advice thực thi**. Nếu proxy method chạy advice còn target raw chạy không, bộ matcher đã có ca kiểm chứng dương và lỗi ở **đường gọi**.

Với weaving, đổi cách kiểm tra: lấy bằng chứng lớp/method đã weave, join point kind và điều kiện matcher. “Không có proxy” không phải một lỗi trong kiến trúc weaving thuần túy.

### Bước 6 — Sửa đúng tầng và kiểm chứng regression

Sau khi xác nhận nguyên nhân, sửa đúng call graph, reference hoặc predicate; chạy lại cả positive và negative tests, kể cả lời gọi nội bộ, exception path và concurrency nếu ứng dụng có. Chỉ giữ diagnostics chi tiết trong phạm vi thích hợp; tracing mọi method vĩnh viễn có thể làm tăng chi phí và tự tạo các lời gọi lồng.

## 8. Các dạng bypass proxy thường gây nhầm lẫn

### 8.1. Self-invocation và direct target access

Hai nhánh này gần nhau nhưng khác vị trí: **self-invocation** sinh từ bên trong target; **direct target access** có thể do caller bên ngoài nắm sai reference. Cả hai tạo hiện tượng method chạy nhưng không vào proxy ủy quyền.

Cách sửa kiến trúc có thể là để caller chỉ nhận proxy, tách chức năng cần advice ra một component được gọi qua boundary hợp lệ, hoặc chọn weaving nếu yêu cầu thực sự là interception ở execution của mọi lời gọi. Không biến việc gọi vòng qua proxy thành sự phụ thuộc ngầm nếu thiết kế có thể thay đổi rõ ràng hơn.

### 8.2. Proxy chỉ bọc một phần API

Một interface proxy không cung cấp các method ngoài hợp đồng interface đó; một subclass proxy không thể override tất cả hình thức method. Chỉ thay pointcut từ `foo` sang `*` không tạo ra join point cho method mà proxy không thể chặn. Cần đối chiếu **proxy technology**, method visibility/modifiers và khả năng chặn thực tế.

### 8.3. Proxy lồng nhau hoặc bị bỏ qua ở một tầng

Hệ thống có thể có nhiều decorator/proxy liên tiếp: `Caller → Proxy A → Proxy B → Target`. Log xuất hiện ở A không chứng minh B cũng được đi qua; có thể A gọi trực tiếp target ở một nhánh. Đặt probe có tên boundary rõ ràng (`A.enter`, `B.enter`) và correlation ID để định vị chính xác tầng biến mất.

### 8.4. Callback, sự kiện và bất đồng bộ

Khi target tự đăng ký `this` làm listener hoặc callback, lời gọi về sau có thể đánh thẳng vào target. Khi nhiệm vụ chuyển qua thread khác, thiếu marker có thể do đường gọi khác, ngữ cảnh quan sát bị mất hoặc log chưa được gom đúng. Đừng vội sửa matcher trước khi dựng chuỗi dispatch và phân biệt receiver thực tế từng callback.

## 9. Trường hợp vẫn thiếu advice dù đã qua proxy và pointcut khớp

Đây là nhóm thứ ba nên giữ riêng trong điều tra:

- **Advice chưa được đăng ký/active:** aspect không được nạp, pointcut kết nối sai advice, hoặc thứ tự khởi tạo khiến cấu hình không áp dụng.
- **Chuỗi interceptor không tiếp tục:** một `around` ở ngoài có thể quyết định không gọi `proceed`/next; advice ở bên trong vì vậy không được thực thi.
- **Advice loại khác chạy trên nhánh khác:** `after returning` không chạy khi join point ném ngoại lệ; `after throwing` không chạy khi trả về bình thường. Logging sau `proceed` không ở `finally` cũng có thể biến mất khi có lỗi.
- **Dữ liệu runtime phân nhánh:** bộ matcher tĩnh cho phép method nhưng điều kiện runtime chặn một invocation riêng.
- **Quan sát bị sai:** logger bị filter, hai appender bị cấu hình ngược, log async bị chậm hoặc correlation ID không được truyền.

Một proxy được tạo không bảo đảm mọi advice sẽ được chạy. Quy trình chẩn đoán cần tách ít nhất ba sự kiện: **intercepted**, **selected**, **advice actually entered**.

## 10. Lựa chọn cách sửa theo bằng chứng

| Kết luận có bằng chứng | Hướng sửa thích hợp | Điều cần xác nhận lại |
| --- | --- | --- |
| Interceptor đã thấy method, matcher false | Chỉnh đúng pointcut signature, annotation lookup, loại join point, điều kiện runtime hoặc exclude | Negative case vẫn không được chọn; positive case được chọn |
| Caller nắm target thô | Chuyển tham chiếu tới đúng proxy tại call site/khâu lắp ghép | Một lời gọi qua proxy xuất hiện probe và advice; logic nghiệp vụ không đổi |
| `this.inner()` bỏ qua delegating proxy | Đổi cấu trúc call boundary; chuyển logic sang đối tượng được chặn, hoặc cân nhắc weaving | Gọi inner từ ngoài và từ luồng nghiệp vụ đều đáp ứng contract |
| Method không nằm trong khả năng proxy | Dùng API/proxy model có thể chặn method, hoặc weaving phù hợp | Method thực tế đã xuất hiện ở interception boundary |
| Cấu hình weaving bỏ sót lớp/call site | Sửa phạm vi weaving, classloader hoặc thời điểm instrumentation | Có bằng chứng bytecode/join point đúng môi trường thực thi |
| Matcher true, advice không vào | Kiểm tra registration, chain, `around`, runtime condition và exception path | Advice chạy ở đúng nhánh, đúng thứ tự và đúng số lần |
| Advice vào nhưng log không thấy | Sửa logic quan sát và propagation, không nới pointcut | Trace khớp sự kiện thực, không còn gap giả |

Khi sửa, ưu tiên thay đổi **nhỏ nhất ở tầng đã xác định**. Nới rộng pointcut khi lỗi là gọi trực tiếp target thường không có tác dụng; thay thế reference bằng proxy khi lỗi là matcher `false` cũng không giải quyết được điều kiện khớp.

## 11. Những bẫy suy luận và giới hạn cần nhớ

1. **“Method chạy thì advice phải chạy.”** Sai: chạy nghiệp vụ không chứng minh đi qua proxy hoặc được pointcut chọn.
2. **“Method nằm đúng package nên pointcut chắc chắn khớp.”** Sai: có thể khác method signature, join point kind, annotation source, runtime args hoặc exclude condition.
3. **“Có biến proxy là mọi caller đều dùng proxy.”** Sai: nhiều chỗ vẫn giữ target thô hay tham chiếu từ trước.
4. **“Self-invocation luôn bỏ qua AOP.”** Sai với các cơ chế weave tại method execution; nó phụ thuộc đường gọi và cách AOP được cài.
5. **“Method final không thể có advice.”** Không đúng với mọi proxy: delegation qua interface có thể chặn trước khi gọi final implementation; subclass override có hạn chế riêng.
6. **“Khi gọi qua proxy, matcher luôn được đánh giá ngay lúc runtime invocation.”** Một số framework tối ưu/chốt match trước, và có thể có phần runtime guard; nên quan sát ở tầng engine phù hợp.
7. **“Chỉ cần thấy interceptor của một method là interceptor của method khác chắc chắn cũng chạy.”** Sai: boundary, surface API và đường gọi có thể khác.
8. **“Log của advice không xuất hiện tức advice không chạy.”** Sai nếu log bị filter, nhánh code không đến lệnh log hoặc log bị gửi qua sink khác.
9. **“Hai proxy cùng tên type là cùng instance.”** Sai: dùng identity của object và correlation thay vì chỉ in class name hoặc `equals()`.
10. **“Tăng log trên mọi phương thức là cách debug an toàn.”** Không chắc: tracing có thể làm thay đổi thời gian, kích hoạt recursion hoặc sinh log quá lớn; giới hạn phạm vi và tránh gọi code nghiệp vụ từ logger.

## 12. Checklist kiểm nghiệm sau khi sửa

- [ ] Target method chắc chắn được thực thi trong trường hợp cần kiểm tra.
- [ ] Đã xác định receiver ở **call site thực tế** là proxy, target gốc hay một wrapper khác.
- [ ] Đã xác định rõ AOP dùng proxy/delegation, subclass override, weaving hay tổ hợp.
- [ ] Đã đặt hoặc thu thập bằng chứng ở **biên interception**, độc lập với advice đang thiếu.
- [ ] Đã kiểm chứng pointcut trên join point thực (event kind, chữ ký, receiver, annotation, runtime args).
- [ ] Đã thử đường **proxy + match true** và **proxy + match false**.
- [ ] Đã thử **direct target** và **self-invocation** nếu chúng thuộc kiến trúc.
- [ ] Đã tách lỗi “matcher true nhưng advice không thực thi” khỏi hai nhóm nguyên nhân chính.
- [ ] Đã kiểm chứng method modifiers, interface/subclass limitations và phạm vi weaving khi liên quan.
- [ ] Đã chạy lại positive/negative tests cùng các đường exception, callback, async nếu chúng xuất hiện trong bug.
- [ ] Không tạo thêm advice trùng, vòng gọi logging hoặc làm thay đổi business side effect.

**Kết luận kỹ thuật:** Phải quan sát **đường gọi có đến interception boundary hay không** trước khi đổ lỗi cho pointcut. Khi đã đến boundary, kiểm tra matcher và advice chain; khi chưa đến, lần theo receiver và cơ chế proxy/weaving. Hai nguyên nhân dẫn tới cùng một biểu hiện, nhưng nằm ở **hai tầng hoàn toàn khác nhau** và đòi hỏi hai cách sửa khác nhau.