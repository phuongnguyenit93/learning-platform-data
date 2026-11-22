# Bài tập tổng hợp: So sánh lời gọi qua proxy với cơ chế biến đổi mã trong AOP

## 1. Mục tiêu của bài

AOP (Aspect-Oriented Programming, lập trình hướng khía cạnh) giúp tách hành vi xuyên suốt như logging, kiểm tra truy cập, đo thời gian hoặc theo dõi lỗi khỏi mã nghiệp vụ. Tuy nhiên, **“có aspect” không có nghĩa mọi phương thức đều bị chặn theo cùng một cách**. Hai cơ chế thường được so sánh là:

1. **Can thiệp lời gọi qua proxy:** caller gọi vào một đối tượng trung gian. Proxy nhận lời gọi, chạy logic bổ sung rồi chuyển tiếp đến đối tượng đích hoặc một tầng proxy khác.
2. **Can thiệp bằng weaving/biến đổi mã:** trình dệt chọn các join point và chèn hoặc biến đổi bytecode tại những vị trí tương ứng. Khi mã đã dệt thực thi, advice chạy ngay ở vị trí được tích hợp, không cần mọi caller đều giữ tham chiếu tới một wrapper proxy.

Bài tập yêu cầu **dự đoán kết quả, chạy hai cấu hình trên cùng một mã nghiệp vụ, giải thích sự khác biệt và chọn giải pháp theo yêu cầu**. Dùng Java 17 và JDK dynamic proxy cho nhánh proxy; dùng AspectJ code-style cho nhánh bytecode weaving. Đây là ví dụ cụ thể để học cơ chế **AOP tổng quát**, không phải ví dụ về một hệ thống dependency injection hay framework ứng dụng riêng.

Sau bài này, người học cần:

- Vẽ được đường đi **caller → proxy → handler → target** và đường đi **caller → mã đã dệt → advice/thân gốc**.
- Phân biệt interface proxy của JDK với proxy tạo subclass; phân biệt proxy ở runtime với compile-time/binary/load-time weaving.
- Giải thích đúng vì sao **gọi trực tiếp target** không đi qua JDK proxy, và vì sao **self-invocation (`this.inner()`)** trên target có thể không vào proxy ủy quyền.
- Hiểu khác biệt giữa join point `call` và `execution` trong AspectJ; biết dệt vào **caller** hay **callee** dẫn đến kết quả khác.
- Quan sát advice, exception, `around`/`proceed` và phạm vi can thiệp; không suy diễn từ tên công nghệ.
- Đo overhead công bằng, cân nhắc giới hạn, khả năng bảo trì và an toàn vận hành.

## 2. Khái niệm: advice được thực thi ở đâu?

### 2.1. Proxy-based interception

Proxy là đối tượng thay mặt đối tượng đích tiếp nhận lời gọi. Với **`java.lang.reflect.Proxy`**, JVM tạo một đối tượng triển khai các interface được chỉ định. Mỗi lời gọi phương thức qua interface trên đối tượng proxy được chuyển vào `InvocationHandler.invoke(proxy, method, args)`; handler tự quyết định có gọi target hay không. Handler có thể chạy logic trước/sau, xử lý ngoại lệ, thay tham số hoặc trả giá trị khác.

```text
Client
  |
  | Work.outer() qua tham chiếu proxy
  v
JDK Proxy implements Work
  |
  v
InvocationHandler.invoke(...)
  |
  | Method.invoke(target, args) nếu muốn chuyển tiếp
  v
Target.outer()
  |
  v
Target.inner()  // self-invocation trên target
```

Điểm quan trọng là **hành vi bổ sung nằm trên tuyến lời gọi đi qua proxy**. Nếu client có một tham chiếu trực tiếp đến target rồi gọi target, handler không biết lời gọi ấy. Nếu phương thức target gọi phương thức khác qua `this`, lời gọi nội bộ vẫn chạy trên target và không tự quay lại wrapper proxy ủy quyền.

JDK dynamic proxy cần **interface** phù hợp; nó không tự tạo subclass của một lớp Java bất kỳ. Một thư viện AOP cũng có thể tạo **class-based proxy** bằng subclass/interception. Với class-based proxy, khả năng chặn self-invocation **phụ thuộc thiết kế**: nếu lời gọi nội bộ chạy trên chính đối tượng subclass và dùng virtual dispatch đến override, lời gọi có thể bị chặn; nếu proxy ủy quyền sang một target tách biệt, self-invocation của target có thể bỏ qua proxy. Vì vậy, không được khẳng định “mọi proxy đều bỏ qua mọi self-invocation”.

### 2.2. Bytecode weaving

Với kiểu AOP dệt mã, công cụ phân tích aspect và các **join point shadow** trong bytecode/source được cung cấp rồi tích hợp advice. Trong AspectJ, pointcut `execution(...)` chọn nơi **thân phương thức được thực thi**, còn `call(...)` chọn **vị trí gọi phương thức**. Ngoài phương thức, mô hình AspectJ còn có các join point phù hợp khác như constructor, field access/set và exception handler theo các giới hạn riêng.

```text
Client ----> Target.outer() [mã đã dệt]
                           |
                      advice outer
                           |
                      thân outer
                           |
                      Target.inner() [mã đã dệt]
                           |
                      advice inner
                           |
                      thân inner
```

Khi `Target.outer` và `Target.inner` đều đã được dệt với `execution` advice, lời gọi bên trong target vẫn đi vào thân `inner` đã được biến đổi. Không cần chuyển lời gọi từ `this` ra một wrapper khác.

**Không phải “mọi bytecode trên classpath đều tự được dệt”.** Kết quả phụ thuộc những class được đưa vào compilation/binary weaving, phạm vi include/exclude, cấu hình load-time weaver, class loader, khả năng hỗ trợ join point và thứ tự nạp lớp. Một class chưa được dệt không có lời đảm bảo được advice áp dụng chỉ vì tồn tại aspect trong project.

### 2.3. Thời điểm can thiệp

| Cơ chế | Khi nào tạo hiệu ứng can thiệp? | Lời gọi phải qua đối tượng trung gian? |
| --- | --- | --- |
| JDK dynamic proxy | Proxy class được tạo/cached lúc runtime; handler chạy tại mỗi lời gọi qua proxy | Có, đối với interface dispatch qua proxy |
| Class-based proxy | Proxy subclass/wrapper được tạo hoặc cấu hình lúc runtime tùy thư viện | Lời gọi phải đến đường dispatch có thể chặn |
| Compile-time weaving (CTW) | Chèn advice trong quá trình biên dịch nguồn | Không, nếu method đã được dệt ở execution join point |
| Post-compile/binary weaving | Biến đổi `.class`/JAR đã biên dịch | Không, với execution join point trong class đã dệt |
| Load-time weaving (LTW) | Biến đổi bytecode lúc class loader nạp class | Không, sau khi class được dệt đúng cách |

Một implementation thực tế có thể kết hợp nhiều tầng; dùng proxy không loại trừ dùng weaving. Phân tích **điểm chặn cụ thể** quan trọng hơn việc chỉ biết nhãn công nghệ.

## 3. Thí nghiệm A: JDK dynamic proxy thuần Java 17

Tạo thư mục `src/demo`. Ví dụ có một interface `Work`, target `Target` và một proxy dùng `InvocationHandler`. `outer` gọi `inner` bằng phương thức instance thường trên cùng target. Cuối cùng, chương trình gọi `outer` một lần **qua proxy** và một lần **trực tiếp qua target**.

**Tệp `src/demo/Main.java`:**

```java
package demo;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class Main {
    public static void main(String[] args) {
        Work target = new Target();

        Work proxied = (Work) Proxy.newProxyInstance(
                Work.class.getClassLoader(),
                new Class<?>[] { Work.class },
                (proxy, method, methodArgs) -> {
                    System.out.println("proxy enter " + method.getName());
                    try {
                        return method.invoke(target, methodArgs);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    } finally {
                        System.out.println("proxy exit " + method.getName());
                    }
                });

        System.out.println("-- via proxy --");
        proxied.outer();

        System.out.println("-- direct target --");
        target.outer();
    }
}

interface Work {
    void outer();
    void inner();
}

class Target implements Work {
    @Override
    public void outer() {
        System.out.println("target outer");
        inner();
    }

    @Override
    public void inner() {
        System.out.println("target inner");
    }
}
```

**Biên dịch và chạy với JDK 17+:**

```bash
javac -d out-java src/demo/Main.java
java -cp out-java demo.Main
```

**Stdout chính xác:**

```text
-- via proxy --
proxy enter outer
target outer
target inner
proxy exit outer
-- direct target --
target outer
target inner
```

### 3.1. Phân tích từng sự kiện

1. `proxied.outer()` là một lời gọi qua interface của proxy. JVM dispatch vào `InvocationHandler.invoke` với `method.getName()` là `outer`.
2. Handler in `proxy enter outer` rồi gọi `method.invoke(target, methodArgs)`. Target chạy `outer`, in `target outer` và gọi `inner()` trên chính target.
3. Lời gọi `inner()` **không** đi vào handler, vì proxy chỉ đang chuyển tiếp một lần đến target và không được target sử dụng khi tự gọi.
4. Khi target `outer` trả về, handler chạy `finally` và in `proxy exit outer`.
5. `target.outer()` là gọi trực tiếp target; lần này ngay cả `outer` cũng không qua proxy, nên hoàn toàn không có hai dòng `proxy enter/exit`.

**Chú ý exception:** `Method.invoke` bọc ngoại lệ do method đích ném trong `InvocationTargetException`. Handler trên dùng `throw e.getCause()` để chuyển lỗi nghiệp vụ thật ra ngoài. Với checked exception, hợp đồng throws của interface và quy tắc `UndeclaredThrowableException` của dynamic proxy vẫn cần tuân thủ. `finally` chạy cả khi target ném lỗi.

### 3.2. Biến thể kiểm thử

- Thay `proxied.outer()` bằng `proxied.inner()`: handler sẽ in `proxy enter inner` và `proxy exit inner` vì lời gọi đi **trực tiếp qua proxy**.
- Thay `target.outer()` bằng `target.inner()`: không in dòng nào của handler.
- Thêm log/đo thời gian trong handler: nó đo lời gọi qua wrapper, không tự động đo lời gọi nội bộ trên target.
- Thêm `proxied.equals(...)` hoặc `proxied.toString()`: `equals`, `hashCode` và `toString` còn được dispatch qua handler theo quy tắc JDK proxy; handler production cần thiết kế ngữ nghĩa cho chúng, không giả định mọi method đều là nghiệp vụ.
- Đừng gọi lại `method.invoke(proxy, ...)` ngay trong handler để “chuyển tiếp”: điều đó có thể tái vào chính handler và tạo đệ quy vô hạn. Trong ví dụ, lời gọi chuyển tới **target** là cố ý.

## 4. Thí nghiệm B: dệt advice vào bytecode của chính Target

Giữ **nguyên `src/demo/Main.java`**. Thêm một aspect theo cú pháp AspectJ:

**Tệp `src/demo/TraceAspect.aj`:**

```aspectj
package demo;

public aspect TraceAspect {
    before(): execution(void demo.Target.outer()) {
        System.out.println("weave execution outer");
    }

    before(): execution(void demo.Target.inner()) {
        System.out.println("weave execution inner");
    }
}
```

Hai pointcut chọn **execution join point của đúng phương thức trong `demo.Target`**. Chúng không chọn `InvocationHandler.invoke`, không chọn method interface `Work`, cũng không tự động thêm một handler mới vào proxy. Target class được dệt mới là nơi chứa hiệu ứng.

Cần bộ **AspectJ compiler `ajc` hỗ trợ Java 17** và runtime `aspectjrt.jar`. Giả sử `ajc` có trên PATH, và `aspectjrt.jar` ở thư mục project. **Không dùng thư mục output Java chưa dệt làm input ngầm cho lần build này**; build nguồn sạch vào thư mục `out-woven` riêng:

**Windows PowerShell:**

```powershell
ajc -17 -showWeaveInfo -d out-woven -classpath "aspectjrt.jar" src/demo/Main.java src/demo/TraceAspect.aj
java -cp "out-woven;aspectjrt.jar" demo.Main
```

**Linux/macOS:**

```bash
ajc -17 -showWeaveInfo -d out-woven -classpath aspectjrt.jar src/demo/Main.java src/demo/TraceAspect.aj
java -cp "out-woven:aspectjrt.jar" demo.Main
```

**Stdout của `demo.Main` khi chạy bản đã dệt** (bỏ qua các thông báo `-showWeaveInfo` của compiler):

```text
-- via proxy --
proxy enter outer
weave execution outer
target outer
weave execution inner
target inner
proxy exit outer
-- direct target --
weave execution outer
target outer
weave execution inner
target inner
```

### 4.1. Vì sao lại có những dòng này?

- Đường **qua proxy** vẫn in `proxy enter/exit outer`, vì `proxied.outer()` đi qua `InvocationHandler` của JDK dynamic proxy.
- Khi handler chuyển tiếp `method.invoke(target, ...)`, việc **thực thi `Target.outer`** đã dệt kích hoạt advice `before` và in `weave execution outer`.
- Trong `Target.outer`, lời gọi `inner()` thực thi **`Target.inner` cũng đã dệt**, nên in `weave execution inner` dù không đi qua handler.
- Đường **gọi trực tiếp `target.outer()`** vẫn kích hoạt hai advice execution của bytecode weaving, nhưng không có dòng `proxy enter/exit` vì không có tuyến gọi qua proxy.

Đây là chứng cứ khác nhau về **đường can thiệp**, không phải khẳng định weaving luôn tốt hơn proxy. Ở ví dụ, cả hai cơ chế **cùng đang hoạt động** khi gọi qua `proxied`; do đó có thể nhìn rõ từng tầng chặn.

### 4.2. Có thể dệt vào caller thay vì callee không?

Có. AspectJ có pointcut `call(...)`: nó nhận diện **vị trí lời gọi trong mã đã dệt**. Nếu muốn can thiệp một lời gọi `inner` bằng `call`, phải bảo đảm class **chứa lời gọi** có trong phạm vi dệt. `execution` chọn vị trí thân method của callee; nếu callee đã dệt thì caller trực tiếp hay caller đi qua proxy vẫn có thể kích hoạt advice.

Không đồng nhất `call` với `execution`:

| Khía cạnh | `call` | `execution` |
| --- | --- | --- |
| Join point shadow | Nằm ở **vị trí gọi** | Nằm tại **thân phương thức được thực thi** |
| Điều kiện để dệt | Bytecode ở caller có trong phạm vi dệt | Bytecode của callee có trong phạm vi dệt |
| Trường hợp caller không được dệt | Không có chặn tại call site đó | Vẫn có thể chặn nếu callee đã dệt |
| Lời gọi nội bộ | Có thể chọn nơi `outer` gọi `inner` nếu caller code được dệt và pointcut khớp | Chọn việc `inner` được thực thi nếu body đã dệt |
| Khác biệt ngữ nghĩa | Gắn với site gọi, kiểu tĩnh của tham chiếu và luật method call | Gắn với method body, class/override được thực thi |

Tùy pointcut, weaving mode, bytecode đầu vào và giới hạn của engine, một số call site (đặc biệt các lệnh gọi `super` đặc thù) không hoạt động giống ordinary virtual calls. Vì thế, không đổi `call` thành `execution` mà không kiểm thử semantics.

## 5. Bảng so sánh hệ thống

| Tiêu chí | Proxy chặn lời gọi | Weaving/biến đổi bytecode |
| --- | --- | --- |
| Điểm mở rộng | Đối tượng trung gian và handler/interceptor | Join point shadow trong class/call site được dệt |
| Yêu cầu caller | Phải gọi qua proxy phù hợp để interceptor chạy | Phải thực thi mã đã dệt hoặc gọi vào join point đã được biến đổi |
| JDK dynamic proxy | Chủ yếu interface methods được chọn | Không dựa trên interface wrapper của JDK |
| Class-based proxy | Có thể subclass/chặn virtual methods tùy thư viện | Có thể chọn method execution/call hoặc join point khác tùy weaver |
| Direct reference đến target | Bỏ qua proxy ủy quyền | Vẫn áp dụng tại method body đã dệt |
| Self-invocation | JDK proxy ủy quyền sang target thường không bắt lời gọi nội bộ của target | Execution advice trên inner body đã dệt vẫn chạy |
| Phương thức không public | JDK interface proxy không chặn arbitrary private method; class proxy có giới hạn override | Có thể can thiệp method execution phù hợp, kể cả không public nếu engine có quyền dệt class |
| `final` / `private` / `static` | Không thể override chúng theo subclass interception thông thường; interface proxy không bao trùm arbitrary methods | Dệt bytecode có thể chọn execution của nhiều phương thức dạng này nếu join point hợp lệ và class được dệt |
| Constructor/field access | JDK dynamic proxy không tự bọc constructor hay field read/write | Weaver hỗ trợ pointcut constructor/field tùy mô hình, trừ trường hợp bị giới hạn/inlined |
| Kích hoạt runtime | Handler chạy tại mỗi lời gọi qua proxy | Mã đã dệt được thực thi ở các vị trí được chọn |
| Kiểm soát phạm vi | Qua đối tượng được trao cho caller, interface và proxy factory | Qua phạm vi weaving, pointcut, loại join point và loader |
| Debug | Có thêm proxy/handler frame | Có thể có helper/source mapping của bytecode đã dệt |
| Deployment | Tạo và phân phối proxy đúng nơi; không nhất thiết sửa class đích | Cần build/weaver/agent và quản lý artifact/classloader |
| Rủi ro cấu hình | Lộ target gốc, thiếu proxy, self-invocation, chain interceptor | Thiếu weave input, agent chạy muộn, dệt sai/mở rộng pointcut, chồng lời khuyên |
| Chi phí | Dispatch proxy, handler, reflection/delegation nếu sử dụng | Chi phí lúc dệt và phí guard/advice khi thực thi mã đã dệt |
| Khả năng quan sát | Có thể tập trung trong handler/proxy | Có thể dệt tại các join point mà wrapper proxy không chặn được |

**Ghi chú:** `final` và `private` có ý nghĩa khác với mọi loại proxy, và weaving không bảo đảm can thiệp được *mọi* kiểu bytecode. Ví dụ Java cho phép inline tham chiếu hằng `static final` compile-time constant, nên pointcut đọc field theo `get` không quan sát một lần đọc vốn không còn instruction truy cập field trong bytecode.

## 6. Bài tập áp dụng: dự đoán trước khi chạy

Với `Main.java` ở mục 3 và `TraceAspect.aj` ở mục 4, hãy viết bảng dự đoán trước khi chạy:

| Hành động | Có vào JDK handler? | Có advice `execution outer`? | Có advice `execution inner`? |
| --- | --- | --- | --- |
| `proxied.outer()` khi chỉ `javac` | Có, cho `outer` | Không | Không |
| `target.outer()` khi chỉ `javac` | Không | Không | Không |
| `proxied.inner()` khi chỉ `javac` | Có, cho `inner` | Không | Không |
| `proxied.outer()` khi chạy class đã dệt | Có, cho `outer` | Có | Có |
| `target.outer()` khi chạy class đã dệt | Không | Có | Có |
| `proxied.inner()` khi chạy class đã dệt | Có, cho `inner` | Không | Có |

**Lý giải:** ở hàng `proxied.inner()`, `outer` không được gọi nên advice cho execution của `outer` không chạy. Lời gọi đi qua handler với method `inner`, và thân `Target.inner` đã dệt kích hoạt advice tương ứng.

Thực hành mở rộng:

1. **Thêm `target.inner()` sau lời gọi trực tiếp:** dự đoán không có log proxy; trong bản woven có log `weave execution inner`.
2. **Di chuyển lời gọi `inner()` sang caller:** ví dụ `proxied.outer(); proxied.inner();`. Khi đó proxy intercept hai lời gọi interface riêng biệt; so với lời gọi nội bộ của target trong `outer`.
3. **Thêm around cho `Target.inner`:** chạy `proceed()` một lần, sau đó thử short-circuit. Quan sát target `inner` có chạy không khi around không gọi tiếp.
4. **Biến đổi argument/return của advice:** xác định tầng thay đổi dữ liệu, kết quả và thứ tự khi phối hợp proxy với weaving.
5. **Thêm method không có trong `Work`:** JDK dynamic proxy kiểu này không công bố method đó qua interface `Work`; thử gọi trực tiếp target, rồi dệt execution pointcut phù hợp.
6. **Tạo subclass-based proxy bằng thư viện thích hợp** (thực nghiệm riêng): kiểm tra đúng behavior của self-invocation theo cơ chế subclass hoặc delegation. Không mặc định nó giống JDK dynamic proxy.

## 7. `around` / `proceed` so với handler chuyển tiếp

Trong proxy, `InvocationHandler` có thể **chuyển tiếp** bằng `method.invoke(target, args)`, tự trả một kết quả, hoặc ném lỗi; việc chuyển tiếp chỉ nằm trong logic do handler thiết kế. Trong bytecode weaving kiểu AspectJ, một `around advice` có thể gọi `proceed(...)` để tiếp tục phần tính toán của join point, bao gồm advice khác nếu có. Hai khái niệm có vẻ giống về mục tiêu nhưng **không phải cùng API**.

Ví dụ minh họa AspectJ (đoạn thay cho advice tương ứng; không thêm đồng thời nếu sẽ chọn cùng join point và muốn output ở mục 4):

```aspectj
void around(): execution(void demo.Target.inner()) {
    System.out.println("around before inner");
    try {
        proceed();
    } finally {
        System.out.println("around after inner");
    }
}
```

Với `inner` thực thi bình thường, các dòng theo đường quanh sẽ là `around before inner`, `target inner`, `around after inner`. Nếu `around` không gọi `proceed`, nội dung `Target.inner` được bao quanh có thể không chạy. Nếu gọi `proceed` nhiều lần, phần tính toán phía trong có thể thực thi nhiều lần — cần cẩn trọng với I/O, giao dịch, thao tác không idempotent.

Tại thời điểm weaving, cách mã được tạo ra còn phụ thuộc độ ưu tiên advice; nếu nhiều around cùng match, `proceed` có thể vào tầng advice khác trước khi đến method body. Proxy chain cũng có thứ tự, nhưng thứ tự đó có thể được quản lý bằng wrapper composition/interceptor ordering khác với precedence của bytecode weaver. Hãy kiểm tra dựa trên **đường gọi thực tế**, không chỉ tên lớp.

### 7.1. Ngoại lệ qua hai cơ chế

- JDK dynamic proxy: target throw → `Method.invoke` có thể bọc trong `InvocationTargetException` → handler có thể unwrap → caller thấy exception theo hợp đồng interface. Một checked exception không được phương thức interface khai báo có thể trở thành `UndeclaredThrowableException`.
- Weaving: advice `before` có thể throw trước thân gốc; `around` có thể catch/wrap/throw; `after throwing` và `after` phản ánh đường lỗi theo semantics của join point. Trên code đã dệt, exception không đi qua `InvocationTargetException` trừ khi có đường reflection thật sự.
- Khi **cả proxy và weaving** cùng hoạt động, lỗi có thể đi qua **cả hai**: code đã dệt throw trước, reflection của handler bắt và bọc, handler unwrap trước khi trả lên caller. Thứ tự và loại lỗi quan sát được phải kiểm tra thực nghiệm.

## 8. Tình huống chọn cơ chế AOP

### 8.1. Chỉ cần các lời gọi đi qua API công khai

Một hệ thống dùng interface cho những dịch vụ công khai và mọi caller đều được cấp tham chiếu tới proxy. Nếu mục tiêu chỉ là logging/metrics/policy tại ranh giới API này, proxy có thể đủ và dễ bật/tắt theo cấu hình. Nhưng phải kiểm soát không để caller giữ target gốc ngoài dự kiến và ghi rõ handler nào áp dụng cho method nào.

### 8.2. Cần can thiệp internal method hoặc join point ngoài API

Nếu yêu cầu phải áp dụng cho nội bộ class, private execution được hỗ trợ, constructor hoặc field access, interface proxy thông thường không bao quát đủ. Weaving giúp đưa advice vào những join point tương ứng **nếu chúng được weaver hỗ trợ và mã nằm trong phạm vi dệt**. Chi phí là cần quản lý toolchain, build/reweaving, bytecode compatibility và cấu hình class loader.

### 8.3. Cần cập nhật logic mà không rebuild target class

Một proxy có thể thay hành vi bằng cấu hình/factory và object graph mới mà không sửa file `.class` của target. Tuy vậy, để thay đổi những caller đang giữ target cũ, thường vẫn phải thay tham chiếu hoặc quản lý điểm tạo đối tượng. LTW cũng có thể biến đổi class lúc nạp, nhưng **không được giả định có thể tự động áp dụng cho những class đã nạp trước đó**; agent/instrumentation và support retransform quyết định khả năng này.

### 8.4. Yêu cầu liên quan bảo mật

Không coi proxy hoặc weaving là **ranh giới bảo mật duy nhất** nếu có thể gọi code theo đường khác: bỏ qua proxy, chạy bytecode chưa dệt, thay class loader hoặc không nạp weaver có thể thay đổi nơi advice chạy. Chính sách bảo mật quan trọng phải được thiết kế với ranh giới kiểm soát tin cậy; test cần chứng minh mọi đường truy cập thực tế đều được kiểm tra, không chỉ đường demo thành công.

## 9. Hiệu năng: so sánh đúng bản chất

Không nên kết luận **proxy luôn chậm hơn weaving** hoặc ngược lại. Chi phí phụ thuộc implementation, pointcut, guard động, advice, reflection, JIT, inline, boxing, allocations, số tầng interceptor và tần suất gọi.

### 9.1. Mô hình chi phí đơn giản

```text
T_proxy_call ≈ T_dispatch_proxy
             + T_handler
             + T_delegation_or_reflection
             + T_target
             + T_advice_work

T_woven_call ≈ T_woven_dispatch_or_guard
             + T_target
             + T_advice_work

T_total_weaving ≈ T_build_or_load_weaving
               + sum(T_runtime_woven_calls)
```

Đây là mô hình định tính. Bộ tối ưu JIT có thể inline một phần proxy handler/delegation hoặc advice woven; dynamic matching và thông tin join point có thể tốn thêm runtime. Build-time weaving chuyển một phần chi phí vào build; LTW có thể tác động thời gian class loading/startup. **Phí thật của advice** (I/O, logging, lock) thường lớn hơn phần dispatch.

### 9.2. Thiết kế benchmark công bằng

1. Dùng cùng tác vụ nghiệp vụ, cùng JDK/JVM flags, cùng máy, cùng dữ liệu.
2. Đo ít nhất ba bản: **target trực tiếp**, **target qua proxy**, **target với advice woven**. Nếu cần đánh giá phối hợp, thêm bản **proxy + woven**.
3. Giữ nội dung advice tương đương. Nếu bản proxy in console mà bản weaving không in, phép đo không so overhead can thiệp.
4. Không ghi console trong vòng đo; dùng JMH hoặc benchmark được thiết kế chuẩn có warm-up, nhiều iterations/forks và chống dead-code elimination.
5. Đo riêng creation/class load/build overhead và steady-state call latency/throughput; theo dõi allocation, GC và tail latency khi thích hợp.
6. Thử cả lời gọi qua proxy, direct target, self-invocation, dynamic condition true/false, số lượng method và concurrency thực tế.
7. Đọc profiler và bytecode khi có khác biệt; đừng suy từ một con số microbenchmark rằng lựa chọn nào tối ưu cho mọi hệ thống.

Ví dụ các dòng `System.out.println` trong hai thí nghiệm chỉ là **trace để hiểu semantics**, không phải mã benchmark. Một trace in nhiều dòng hơn không chứng minh cơ chế đó chậm hơn về chi phí dispatch thuần túy.

## 10. Triển khai và gỡ lỗi

### 10.1. Dấu hiệu proxy không được gọi

- Đối tượng được truyền vào caller là **target**, không phải proxy.
- Một method được gọi từ trong target qua `this`, trong kiến trúc proxy ủy quyền sang target tách biệt.
- Method không được công bố qua interface của JDK dynamic proxy hoặc interceptor bị giới hạn method.
- Proxy subclass không thể override method cần chặn (ví dụ `final`/`private`), hoặc lời gọi không đi qua override.
- Handler đã intercept nhưng branch/cấu hình quyết định **không gọi** advice.

Kiểm tra kiểu thực của object tại caller, `Proxy.isProxyClass(...)` nếu là JDK proxy, `Proxy.getInvocationHandler(...)` khi phù hợp, và breakpoint trong `InvocationHandler.invoke`. Với class-based proxy, dùng cơ chế inspect của thư viện proxy đang sử dụng.

### 10.2. Dấu hiệu weaving không áp dụng

- Class đích không nằm trong input/`-inpath`/phạm vi include của weaver.
- Pointcut khớp sai signature, package, overload hoặc loại `call`/`execution`.
- Chạy class từ output **chưa dệt** hoặc JAR cũ trên classpath.
- LTW agent không khởi động đúng lúc hoặc class đã nạp qua loader ngoài cấu hình.
- Advice có điều kiện động false ở lần chạy hiện tại.
- Phiên bản JDK, bytecode và weaver không tương thích; compilation/weaving có warnings/errors.

Với AspectJ, có thể bật `-showWeaveInfo` và kiểm tra bytecode:

```bash
javap -classpath out-java -c -p demo.Target
javap -classpath out-woven -c -p demo.Target
```

Dùng debugger đặt breakpoint ở handler, trong advice `TraceAspect.aj` và trong `Target.outer/inner`. Nếu debugger chuyển vào helper tổng hợp, đó có thể là cấu trúc sau weaving; breakpoint nguồn và log trace giúp tái dựng đường thực thi.

## 11. Các sai lầm thường gặp

**“AOP nào cũng chặn self-invocation như nhau.”** Sai. JDK proxy ủy quyền sang target không tự nhận lời gọi nội bộ trên target; subclass proxy hoặc bytecode weaving có cơ chế khác và phải phân tích theo đường dispatch.

**“Dùng proxy thì method gốc đã được biến đổi bytecode.”** Không nhất thiết. JDK dynamic proxy tạo lớp proxy tại runtime và gọi handler, trong khi class đích ở ví dụ không bị sửa.

**“Weaving chỉ là tạo một proxy ẩn.”** Không đúng theo nghĩa kỹ thuật: CTW/Binary/LTW có thể thay đổi bytecode tại join point shadow, kể cả execution body hoặc field access mà interface wrapper không cung cấp.

**“Direct target luôn được advice chặn.”** Chỉ khi target thật sự đã được dệt ở join point phù hợp. Một aspect có trên classpath chưa đủ.

**“`call` và `execution` tương đương.”** Không. `call` nằm ở caller; `execution` nằm ở callee; phạm vi dệt và điều kiện chọn khác nhau.

**“Mọi subclass proxy đều bỏ qua self-invocation.”** Không thể khẳng định chung; cần xem instance chạy code, cơ chế override và việc proxy có delegate sang target tách biệt không.

**“Phương thức final/private đều không thể áp dụng AOP.”** Không đúng đối với toàn bộ AOP: subclass override và bytecode weaving có khả năng/giới hạn khác nhau.

**“Nếu có hai interceptor thì chắc chắn chỉ chạy một lần.”** Khi proxy và weaving cùng chặn một hành vi, cả hai đều có thể chạy; nhiều advice còn tạo thứ tự và side effect bổ sung.

**“Lỗi hiệu năng nhìn thấy từ stdout.”** Console output chỉ giúp phân tích lời gọi, không đo overhead; cần benchmark chuẩn.

**“Thay target bằng proxy ở một điểm tạo đối tượng sẽ bao phủ mọi lời gọi.”** Chưa chắc: có thể còn các tham chiếu target khác, callback, reflection, lời gọi nội bộ hoặc điểm tạo đối tượng không đi qua factory.

## 12. Tiêu chí hoàn thành bài tập tổng hợp

Hãy tự kiểm tra rằng bạn có thể giải thích và chứng minh:

- **Sơ đồ:** proxy handler nằm ở caller boundary, weaving execution nằm ở method body; giải thích call site vs execution site.
- **Thực nghiệm Java 17:** chạy được `Main.java` với `javac` và thu stdout ở mục 3, đúng hiện tượng self-invocation.
- **Thực nghiệm weaving:** dùng `ajc` dệt thêm `TraceAspect.aj` và thu stdout ở mục 4, kể cả lời gọi trực tiếp target.
- **Bảng dự đoán:** giải thích đủ sáu tình huống ở mục 6, không chỉ thuộc lòng log.
- **Ngoại lệ:** biết handler reflection unwrap `InvocationTargetException`, còn `around` có `proceed` điều khiển đường return/throw.
- **Giới hạn:** phân biệt JDK interface proxy, subclass proxy, CTW/binary/LTW và class loader.
- **Vận hành:** biết kiểm tra artifact class đã dệt, weave info, breakpoint và tránh double interception không chủ ý.
- **Lựa chọn:** chọn cơ chế theo join point cần bao phủ, mức kiểm soát caller, toolchain, semantics, test và overhead đo được.

**Kết luận:** proxy can thiệp những lời gọi **đi qua đối tượng trung gian**; weaving đưa advice vào **các vị trí mã đã được chọn và biến đổi**. Hai đường đi khác nhau giải thích sự khác biệt về direct call, self-invocation, loại join point và phạm vi áp dụng. Cách hiểu bền vững nhất là chạy cùng một chương trình dưới hai cấu hình và kiểm chứng đường thực thi bằng stdout, debugger và bytecode — thay vì xem proxy và weaving là hai tên gọi tương đương.

## Tài liệu tham khảo

- Java SE 17: `java.lang.reflect.Proxy` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html
- Java SE 17: `java.lang.reflect.InvocationHandler` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html
- Java SE 17: `java.lang.reflect.Method.invoke` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- AspectJ Programming Guide — join point, `call` và `execution`: https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html
- AspectJ Development Guide — `ajc` và các chế độ weaving: https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html
- AspectJ Load-Time Weaving — https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html
