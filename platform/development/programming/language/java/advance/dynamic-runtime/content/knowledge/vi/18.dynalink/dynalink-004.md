# 18.4 RelinkableCallSite, SimpleRelinkableCallSite và ChainedCallSite

## 1. Chủ đề và mục tiêu

`Dynalink` là thư viện của Java trong module `jdk.dynalink`, hỗ trợ liên kết động những phép toán trên đối tượng như đọc/ghi thuộc tính, lấy phần tử, gọi hàm hoặc tạo đối tượng. Khi loại receiver chỉ được biết tại runtime, một method handle được liên kết cho class A có thể không còn phù hợp với class B. Dynalink hỗ trợ cập nhật liên kết của **cùng một call site** mà không cần xem toàn bộ biểu thức như một lời gọi cố định.

Ba API của bài gồm một **giao thức** và hai **chính sách cache**:

- **`RelinkableCallSite`** là interface mô tả một call site mà `DynamicLinker` có thể quản lý. Nó cung cấp descriptor và nhận các lệnh `initialize`, `relink`, `resetAndRelink`.
- **`SimpleRelinkableCallSite`** là implementation đơn hình (*monomorphic inline cache*), giữ **một `GuardedInvocation`** ở một thời điểm. Nếu guard không còn áp dụng, sẽ đi theo đường fallback để được liên kết lại.
- **`ChainedCallSite`** là implementation đa hình (*polymorphic inline cache*, PIC), giữ **một chuỗi `GuardedInvocation`**. Mặc định giới hạn 8 mục, mới liên kết nhất ở đầu chuỗi, cũ nhất có thể bị loại khi đầy.

Cả Simple lẫn Chained có thể trả **cùng kết quả nghiệp vụ**. Chúng khác ở cách tái sử dụng specialization, số guard cần thử, tần suất relink và áp lực tài nguyên. Không có chiến lược tối ưu cho mọi workload.

Sau bài học, bạn cần phân biệt được liên kết lần đầu với relink, hiểu `GuardedInvocation` và `relinkAndInvoke`, biết chọn Simple/Chained theo hình dạng receiver, xác định khi nào `resetAndRelink` xóa lịch sử cache và triển khai được demo Java 17+.

## 2. Vì sao relink xuất hiện?

Giả sử một ngôn ngữ động có phép:

~~~text
result = receiver.color
~~~

Một biểu thức tại đúng một vị trí source có thể thấy nhiều receiver:

~~~text
Lượt 1: FieldBean   → đọc public field color
Lượt 2: GetterBean  → gọi getColor()
Lượt 3: FieldBean   → đọc field color
Lượt 4: GetterBean  → gọi getter
~~~

Ở bytecode do language runtime sinh, có thể biểu diễn logic tương tự:

~~~text
aload_1
invokedynamic GET:PROPERTY:color (Object)Object
astore_2
~~~

Đây là **sơ đồ bytecode**, không phải output nguyên văn của `javap` và cũng không bắt buộc mọi runtime mã hóa tên operation như vậy. Điểm quan trọng là call site nhận một receiver `Object` và trả `Object`. Với class cụ thể của receiver, linker chọn target đúng.

Một specialization thường gồm hai method handles:

~~~text
guard(receiver)    → receiver có phù hợp kiểu/shape này?
invoke(receiver)   → thao tác chuyên biệt cho kiểu/shape đó
~~~

Receiver thay đổi có thể làm guard fail. Để không ném `ClassCastException` hoặc thực hiện nhầm thao tác, call site đi tới fallback có khả năng xin một specialization khác. Đó là relinking.

**Không phải mỗi lần relink đều chạy lại bootstrap method của `invokedynamic`.** Bootstrap tạo/liên kết `CallSite`, còn relink là thay đổi/ghép target của chính call site đang tồn tại.

## 3. Kiến trúc và vai trò các lớp

~~~text
Dynamic expression
      |
      v
CallSiteDescriptor
  - MethodHandles.Lookup
  - Operation
  - MethodType
      |
      v
RelinkableCallSite
  - SimpleRelinkableCallSite
  - ChainedCallSite
      |
      | DynamicLinker.link(site)
      v
Initial relinkAndInvoke target
      |
  First invocation with actual arguments
      |
      v
GuardingDynamicLinker(s) / BeansLinker
      |
      v
GuardedInvocation
  - invocation MethodHandle
  - guard MethodHandle
  - invalidation assumptions (optional)
      |
      | site.relink(...)
      v
Installed guarded target
      |
      +-- guard passes → execute invocation
      |
      +-- guard fails → next PIC branch or fallback
                                  |
                                  v
                          DynamicLinker relinks
~~~

Bảng API cốt lõi:

| API | Ý nghĩa |
| --- | --- |
| `CallSiteDescriptor` | Metadata cố định cho một site: lookup, operation, method type |
| `Operation` | Phép toán trừu tượng, như `GET:PROPERTY:color` |
| `DynamicLinkerFactory` | Cấu hình rồi tạo `DynamicLinker` |
| `DynamicLinker.link(site)` | Gắn linker vào relinkable site, thiết lập đường liên kết ban đầu |
| `GuardingDynamicLinker` | Nơi có thể tìm một `GuardedInvocation` cho operation và receiver hiện tại |
| `GuardedInvocation` | Invocation handle cộng guard và điều kiện invalidation tùy chọn |
| `RelinkableCallSite` | Giao thức nhận/cài liên kết mới |
| `SimpleRelinkableCallSite` | Cache một guarded invocation |
| `ChainedCallSite` | Cache nhiều guarded invocations dạng chain |

`DynamicLinkerFactory` mặc định tích hợp `BeansLinker` để xử lý nhiều thao tác với Java objects thông thường. Khi triển khai một ngôn ngữ có object model riêng, có thể thêm custom guarding linkers để mô tả luật truy xuất đúng của ngôn ngữ đó.

### Type identity của một call site

Một site có `MethodType` là `(Object)Object` vẫn có kiểu đó sau khi gặp `String`, `Map`, `FieldBean` và `GetterBean`. **Runtime receiver class có thể thay đổi; call-site signature không tự thay đổi.** Các method handles bên trong phải được thích nghi để tương thích với descriptor khi cập nhật target.

## 4. RelinkableCallSite: giao thức chính xác

Các chữ ký Java 17 trọng yếu:

~~~java
// Các method của interface jdk.dynalink.RelinkableCallSite:
CallSiteDescriptor getDescriptor();
void initialize(MethodHandle relinkAndInvoke);
void relink(
        GuardedInvocation guardedInvocation,
        MethodHandle relinkAndInvoke);
void resetAndRelink(
        GuardedInvocation guardedInvocation,
        MethodHandle relinkAndInvoke);
~~~

Đây là **trích đoạn API** nhằm học tên và vai trò, không phải chương trình độc lập. `GuardedInvocation` nằm trong package `jdk.dynalink.linker`; `MethodHandle` nằm trong `java.lang.invoke`.

Các method giải quyết những việc khác nhau:

**`getDescriptor()`:** cung cấp metadata cần để liên kết lại. Nó **không** trả giá trị nghiệp vụ hay một receiver.

**`initialize(relinkAndInvoke)`:** cài `MethodHandle` ban đầu biết yêu cầu linker tìm target mới và gọi luôn target đó. Khi `DynamicLinker.link(site)` được gọi, nó chuẩn bị site bằng callback này; việc tìm một specialization phù hợp có thể được hoãn tới **lần gọi đầu với arguments thực**.

**`relink(guardedInvocation, relinkAndInvoke)`:** thông báo specialization mới. Site **có thể giữ các specialization cũ còn hợp lệ** tùy chính sách cache. Simple thường thay thế; Chained có thể bổ sung.

**`resetAndRelink(guardedInvocation, relinkAndInvoke)`:** yêu cầu quên trạng thái liên kết cũ rồi tạo target từ specialization mới. Đây là thao tác khác `relink`, đặc biệt với PIC.

**`relinkAndInvoke`:** fallback callback do linker đưa vào, có cùng `MethodType` với site. Nó không phải argument người dùng và cũng không phải bản thân bootstrap method.

Interface `RelinkableCallSite` không được khai báo là subclass của `java.lang.invoke.CallSite`. Những implementation có sẵn kế thừa `AbstractRelinkableCallSite extends MutableCallSite`, vì vậy thực tế có cả API của `CallSite` như `type()` và `dynamicInvoker()`.

## 5. Kế thừa giữa hai implementation

~~~text
java.lang.Object
   └── java.lang.invoke.CallSite
        └── java.lang.invoke.MutableCallSite
             └── AbstractRelinkableCallSite
                  ├── SimpleRelinkableCallSite
                  └── ChainedCallSite

AbstractRelinkableCallSite implements RelinkableCallSite
~~~

`AbstractRelinkableCallSite` giữ `CallSiteDescriptor` và hỗ trợ khởi tạo fallback đúng type. Hai lớp con định nghĩa cách thực hiện `relink` và `resetAndRelink`. Chúng được cung cấp sẵn, nên khi viết runtime không bắt buộc phải tự lắp toàn bộ chuỗi guard từ đầu.

Cả hai constructor đều nhận descriptor:

~~~java
new SimpleRelinkableCallSite(descriptor);
new ChainedCallSite(descriptor);
~~~

Đây là **snippet minh họa**, biến `descriptor` phải chứa `Lookup`, `Operation` và `MethodType` hợp lệ.

## 6. GuardedInvocation giữ giả định nào?

`jdk.dynalink.linker.GuardedInvocation` là bộ giá trị immutable, bao gồm:

- **Invocation MethodHandle:** thực thi một thao tác chuyên biệt.
- **Guard MethodHandle (tùy chọn):** xác định specialization này có áp dụng với arguments hiện tại không.
- **SwitchPoint(s) (tùy chọn):** cho phép invalidation khi một assumption bên ngoài không còn đúng.
- **Invalidating exception type (tùy chọn):** ngoại lệ chỉ định có thể làm specialization mất hiệu lực.

Ví dụ:

~~~text
Operation: GET:PROPERTY:color
Guard:     receiver instanceof FieldBean
Invoke:    đọc public field FieldBean.color
Fallback:  yêu cầu linker tìm specialization khác
~~~

Nếu guard trả `true`, invocation chạy. Nếu `false`, site thử một branch khác (trong PIC) hoặc chuyển tới fallback. Guard thường **kiểm tra applicability**, không nhất thiết so sánh giá trị của property. Hai `FieldBean` có `color="red"` và `color="blue"` vẫn có thể cùng dùng một specialization mà không relink.

**Không mặc định một guard là phép `getClass()==X`.** Nó có thể dựa vào class, cấu trúc object, version, switch point hoặc quy tắc ngôn ngữ. `ChainedCallSite` là chuỗi **các điều kiện và targets**, không phải một Map<Class,MethodHandle> được cam kết công khai.

`GuardedInvocation` có constructor:

~~~java
new GuardedInvocation(invocationHandle, guardHandle);
~~~

Trong ví dụ này guard có kiểu `(Object)boolean`, invocation có kiểu `(Object)Object`. Hai handle cần tương thích để ghép bằng `MethodHandles.guardWithTest` và với call-site signature.

## 7. SimpleRelinkableCallSite là monomorphic cache

Simple giữ **một** `GuardedInvocation` tại một thời điểm. Khi guard không khớp, switch point bị vô hiệu hoặc invalidating exception xảy ra, specialization hiện tại không dùng được; fallback tìm cái mới và site thay trạng thái.

~~~text
Receivers: A, A, B, B, A

Simple:
  A → link A
  A → reuse A
  B → guard A miss; replace with B
  B → reuse B
  A → guard B miss; replace with A
~~~

Cách này phù hợp khi một site gần như luôn nhận **cùng một receiver shape**. Guard chain ngắn, state nhỏ, không cần lưu nhiều specialization.

Nhược điểm chính là *thrashing* nếu traffic xen kẽ A/B: mỗi lần đổi shape đều có thể phải relink, dù hai shapes đã từng gặp. Chi phí linker lookup, tạo adapter, invalidation có thể lớn hơn một vài guard checks.

Một ví dụ site phù hợp Simple:

~~~text
95% A, 5% A-subclass mà guard vẫn chấp nhận
  → thường reuse một specialization
~~~

Một ví dụ site không phù hợp:

~~~text
A, B, A, B, A, B liên tục
  → cache một phần tử phải thay liên tục
~~~

Dù vậy, **không bảo đảm một số lượt relink cố định** chỉ từ danh sách receiver: guard thực tế do linker chọn, một guard có thể chấp nhận hơn một class hoặc bị invalidated giữa các lần gọi.

## 8. ChainedCallSite là polymorphic inline cache

Chained giữ **nhiều** `GuardedInvocation` cùng lúc. Khi gọi, nó thử những guard đã được liên kết trước rồi mới fallback nếu không có nhánh phù hợp.

~~~text
Receivers: A, B, A, B, C

Chained (minh họa):
  A → cache [A]
  B → cache [B,A]
  A → B guard fail, A guard pass
  B → B guard pass
  C → cache [C,B,A]
~~~

Theo contract JDK 17:

- `getMaxChainLength()` **mặc định 8**.
- Có thể override giới hạn trong subclass.
- Khi thêm specialization mới và chuỗi đầy, loại **mục cũ nhất**.
- **Mục mới liên kết nhất** đứng ở đầu, mục lâu nhất ở cuối.
- Các mục **không tự reorder mỗi khi hit**; đây không phải LRU cache theo nghĩa mỗi access.
- Các specialization bị invalidation qua switch points/invalidating exceptions có thể được loại khỏi chain.
- Việc đồng thời relink từ nhiều threads có cơ chế giải quyết cạnh tranh; một guarded invocation do thread thua tạo có thể không được tích hợp, gây repeated linking.

### Thay giới hạn bằng subclass

~~~java
static class TwoEntryChain extends ChainedCallSite {
    TwoEntryChain(CallSiteDescriptor descriptor) {
        super(descriptor);
    }

    @Override
    protected int getMaxChainLength() {
        return 2;
    }
}
~~~

Đây là **class minh họa**, cần các imports và đặt trong class/file Java hợp lệ. API yêu cầu `getMaxChainLength()` trả về số từ **1 trở lên**. Không dùng `0` để biểu diễn “no cache”; số nhỏ hơn 1 dẫn tới runtime error.

Nếu lần lượt liên kết A, B, C ở cache hai mục:

~~~text
[A] → [B,A] → [C,B]
                 ^
             A evicted
~~~

Khi A quay lại, guard có thể miss và linker liên kết A trở lại đầu chuỗi. “Bị loại khỏi cache” khác “không bao giờ xử lý được kiểu A”.

## 9. So sánh khả năng cache

| Đặc tính | SimpleRelinkableCallSite | ChainedCallSite |
| --- | --- | --- |
| Cache style | Monomorphic | Polymorphic |
| Số `GuardedInvocation` nhớ | Một | Nhiều, mặc định tối đa 8 |
| Guard miss | Thường relink, thay mục cũ | Thử các mục còn lại; nếu đều fail mới relink |
| A/B xen kẽ | Dễ thay cache liên tục | Có thể dùng lại cả A lẫn B |
| Một kiểu áp đảo | Ít nhánh, đơn giản | Có thể thêm guard overhead không cần thiết |
| Nhiều kiểu độc nhất | Liên kết liên tục | Có eviction/guard chain overhead |
| Tùy chỉnh dung lượng | Không có PIC-size hook | `getMaxChainLength()` |
| Reset | Về một mục mới | Bỏ toàn bộ chain rồi bắt đầu lại |
| Luồng đa hình nhỏ | Thường kém phù hợp hơn | Có thể giảm số lần relink |

Không nên suy ra Chained luôn nhanh hơn. Với chain dài, kiểm tra nhiều guards có thể tốn CPU và ảnh hưởng optimization của JIT. Ngược lại, relink liên tục ở Simple cũng có chi phí. Lựa chọn nên dựa trên phân bố shape, guard hit-rate, cost của linker và benchmark.

## 10. Ví dụ Java 17+ hoàn chỉnh 1: Dynalink thật với hai JavaBeans

Chương trình có hai kiểu đối tượng:

- `FieldBean` với public field `color`;
- `GetterBean` với private field và public getter `getColor()`.

`DynamicLinkerFactory` mặc định tạo linker có khả năng xử lý JavaBeans. Cả Simple và Chained cùng đọc `GET:PROPERTY:color`, nhưng cache theo hai chính sách khác nhau. Code dùng `dynamicInvoker()` trực tiếp, nên **không cần tự sinh opcode `invokedynamic`** trong file ví dụ.

Tạo file **DynalinkCallSitesDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.ArrayList;
import java.util.List;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.support.ChainedCallSite;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkCallSitesDemo {
    public static class FieldBean {
        public final String color;

        public FieldBean(String color) {
            this.color = color;
        }
    }

    public static class GetterBean {
        private final String color;

        public GetterBean(String color) {
            this.color = color;
        }

        public String getColor() {
            return color;
        }
    }

    private static String run(
            CallSite site, Object[] receivers) throws Throwable {
        MethodHandle invoker = site.dynamicInvoker();
        List<String> values = new ArrayList<>();

        for (Object receiver : receivers) {
            Object color = invoker.invokeWithArguments(receiver);
            values.add(String.valueOf(color));
        }
        return String.join(" | ", values);
    }

    public static void main(String[] args) throws Throwable {
        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        DynamicLinker linker = factory.createLinker();

        Operation operation = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("color");

        MethodType type = MethodType.methodType(
                Object.class, Object.class);

        CallSiteDescriptor descriptor = new CallSiteDescriptor(
                MethodHandles.lookup(), operation, type);

        SimpleRelinkableCallSite simple = linker.link(
                new SimpleRelinkableCallSite(descriptor));

        ChainedCallSite chained = linker.link(
                new ChainedCallSite(descriptor));

        Object[] receivers = {
                new FieldBean("red"),
                new GetterBean("green"),
                new FieldBean("blue"),
                new GetterBean("yellow")
        };

        System.out.println("simple: " +
                run(simple, receivers));
        System.out.println("chained: " +
                run(chained, receivers));
        System.out.println("site type: " + simple.type());
        System.out.println("same type: " +
                simple.type().equals(chained.type()));
    }
}
~~~

Biên dịch/chạy bằng **JDK 17+**, bật module `jdk.dynalink` khi dùng classpath:

~~~bash
javac --add-modules jdk.dynalink DynalinkCallSitesDemo.java
java --add-modules jdk.dynalink DynalinkCallSitesDemo
~~~

Stdout dự kiến:

~~~text
simple: red | green | blue | yellow
chained: red | green | blue | yellow
site type: (Object)Object
same type: true
~~~

### Diễn giải luồng

**Operation:** `StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY).named("color")` mô tả đọc property cố định. Vì tên `color` đã được gắn vào `NamedOperation`, call-site signature chỉ nhận receiver, không cần runtime name argument.

**MethodType:** `(Object)Object` cho phép cùng site nhận các Java classes khác nhau. Return type trong descriptor là `Object` dù getter thật có thể trả `String` hoặc một primitive, bởi linker có thể thích nghi handle tương ứng.

**Descriptor:** `CallSiteDescriptor` giữ lookup, operation và type để linker biết cần làm gì khi một receiver mới xuất hiện. Nó không chứa receiver cụ thể của từng lượt gọi.

**Linking:** `linker.link(site)` thiết lập initial relink-and-invoke method handle, thường trì hoãn chuyên biệt hóa đến lần gọi thực tế. Sau đó site có thể relink trong suốt thời gian chạy.

**Invocation:** `site.dynamicInvoker()` tạo MethodHandle dùng target hiện tại của site, khác việc chụp một target rồi không theo những lần relink sau. Mỗi lần `invokeWithArguments(receiver)` thực hiện operation cho receiver thực.

**Kết quả:** hai sites trả cùng màu theo dữ liệu object. Nhưng Simple chỉ giữ một specialization ở một thời điểm, trong khi Chained có thể nhớ các nhánh phù hợp cho cả hai classes. Demo không in số lần relink vì số đó phụ thuộc chính sách guard và liên kết của runtime, không phải hằng số của API.

`FieldBean` và `GetterBean` được khai báo public static để `BeansLinker` có thể dùng các thành phần public theo cơ chế truy cập thích hợp. Nếu đổi thành private inner class hoặc dùng module không export package, cần xem lại quyền lookup và khả năng truy cập khi liên kết.

### Module jdk.dynalink

`jdk.dynalink` là một JDK module không phải lúc nào cũng được resolve mặc định cho ứng dụng chạy bằng classpath; do đó ví dụ nêu cả `javac --add-modules` và `java --add-modules`. Nếu project là named module, có thể khai báo:

~~~java
module example.runtime {
    requires jdk.dynalink;
}
~~~

Đây là **module-info.java minh họa**, không phải file cần thêm vào demo classpath nói trên. Với named module, còn phải đặt sources/build đúng bố cục JPMS.

## 11. Ví dụ Java 17+ hoàn chỉnh 2: mô phỏng rõ relink, reset và eviction

Trong chương trình sau, ta **tự cung cấp guarded invocations**:

- `isText` chỉ chấp nhận `String`;
- `isNumber` chấp nhận `Integer`;
- `isLong` chấp nhận `Long`.

Ba targets trả một chuỗi khác nhau. Fallback `miss` trả chuỗi `"<miss>"` có chủ đích, thay vì gọi linker. Như vậy chương trình kiểm tra trực tiếp tính chất **cache giữ gì sau relink**.

**Giới hạn cần hiểu:** vì không gọi `DynamicLinker.link(site)`, đây chỉ là **mô phỏng giao thức call site**, không phải một Dynalink runtime tự liên kết đầy đủ. Khi guard fail, callback giả chỉ in miss và không cố tìm target mới. Trong production, Dynalink sẽ đưa fallback `relinkAndInvoke` phù hợp để relink tự động.

Tạo file **RelinkProtocolDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.linker.GuardedInvocation;
import jdk.dynalink.support.ChainedCallSite;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class RelinkProtocolDemo {
    static class TwoEntryChain extends ChainedCallSite {
        TwoEntryChain(CallSiteDescriptor descriptor) {
            super(descriptor);
        }

        @Override
        protected int getMaxChainLength() {
            return 2;
        }
    }

    public static boolean isText(Object x) {
        return x instanceof String;
    }

    public static Object text(Object x) {
        return "text:" + x;
    }

    public static boolean isNumber(Object x) {
        return x instanceof Integer;
    }

    public static Object number(Object x) {
        return "int:" + x;
    }

    public static boolean isLong(Object x) {
        return x instanceof Long;
    }

    public static Object longValue(Object x) {
        return "long:" + x;
    }

    public static Object miss(Object x) {
        return "<miss>";
    }

    private static GuardedInvocation guarded(
            MethodHandles.Lookup lookup,
            String invocationName,
            String guardName) throws ReflectiveOperationException {

        MethodHandle action = lookup.findStatic(
                RelinkProtocolDemo.class,
                invocationName,
                MethodType.methodType(Object.class, Object.class));

        MethodHandle guard = lookup.findStatic(
                RelinkProtocolDemo.class,
                guardName,
                MethodType.methodType(boolean.class, Object.class));

        return new GuardedInvocation(action, guard);
    }

    private static String call(
            java.lang.invoke.CallSite site, Object argument)
            throws Throwable {
        Object result = site.dynamicInvoker()
                .invokeWithArguments(argument);
        return String.valueOf(result);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(
                Object.class, Object.class);

        CallSiteDescriptor descriptor = new CallSiteDescriptor(
                lookup,
                StandardOperation.GET
                    .withNamespace(StandardNamespace.PROPERTY)
                    .named("value"),
                type);

        MethodHandle fallback = lookup.findStatic(
                RelinkProtocolDemo.class, "miss", type);

        GuardedInvocation text = guarded(
                lookup, "text", "isText");
        GuardedInvocation integer = guarded(
                lookup, "number", "isNumber");
        GuardedInvocation longValue = guarded(
                lookup, "longValue", "isLong");

        SimpleRelinkableCallSite simple =
                new SimpleRelinkableCallSite(descriptor);
        simple.initialize(fallback);
        simple.relink(text, fallback);

        System.out.println("simple text: " +
                call(simple, "Ada"));

        simple.relink(integer, fallback);
        System.out.println("simple text after relink: " +
                call(simple, "Ada"));
        System.out.println("simple int: " +
                call(simple, 7));

        ChainedCallSite chain = new ChainedCallSite(descriptor);
        chain.initialize(fallback);
        chain.relink(text, fallback);
        chain.relink(integer, fallback);

        System.out.println("chain text: " +
                call(chain, "Ada"));
        System.out.println("chain int: " +
                call(chain, 7));

        chain.resetAndRelink(integer, fallback);
        System.out.println("chain text after reset: " +
                call(chain, "Ada"));
        System.out.println("chain int after reset: " +
                call(chain, 7));

        TwoEntryChain limited = new TwoEntryChain(descriptor);
        limited.initialize(fallback);
        limited.relink(text, fallback);
        limited.relink(integer, fallback);
        limited.relink(longValue, fallback);

        System.out.println("limited old text: " +
                call(limited, "Ada"));
        System.out.println("limited int: " +
                call(limited, 7));
        System.out.println("limited long: " +
                call(limited, 9L));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --add-modules jdk.dynalink RelinkProtocolDemo.java
java --add-modules jdk.dynalink RelinkProtocolDemo
~~~

Stdout dự kiến (single-thread):

~~~text
simple text: text:Ada
simple text after relink: <miss>
simple int: int:7
chain text: text:Ada
chain int: int:7
chain text after reset: <miss>
chain int after reset: int:7
limited old text: <miss>
limited int: int:7
limited long: long:9
~~~

### Vì sao mỗi dòng xuất hiện?

**Kiểu phù hợp:** Invocation MethodHandles đều `(Object)Object`; guards đều `(Object)boolean`; fallback là `(Object)Object`. Vì vậy không cần adapters trong demo.

**Simple ban đầu:** `simple.relink(text,fallback)` cài một nhánh text. Khi chạy `"Ada"`, guard `isText` đạt, target trả `text:Ada`.

**Simple sau relink:** `simple.relink(integer,fallback)` thay nhánh text bằng nhánh integer. `isNumber("Ada")` thất bại nên fallback trả `<miss>`; số nguyên 7 được nhánh integer xử lý thành `int:7`.

**Chained sau hai relinks:** `chain.relink(text,fallback)` rồi `chain.relink(integer,fallback)` giữ cả hai nhánh. `"Ada"` có thể vượt qua integer guard thất bại và dùng text guard; `7` dùng integer guard.

**Chained sau reset:** `chain.resetAndRelink(integer,fallback)` yêu cầu bỏ các nhánh cũ. Text không còn branch phù hợp nên trả `<miss>`; integer vẫn trả `int:7`.

**TwoEntryChain:** sau khi liên kết text, integer, long, chain 2 mục giữ 2 liên kết gần đây, khiến text cũ bị loại. Lúc này số 7 và `9L` vẫn có specialized handles.

**Tại sao operation tên `value` nhưng không có class nào chứa property `value`?** Vì ví dụ chủ động tạo guarded invocations qua MethodHandles và **không gọi DynamicLinker để phân giải operation đó**. Descriptor được dùng để giữ call-site type và minh họa API. Trong demo 1, operation thực sự được `BeansLinker` phân giải.

**Tại sao không dùng fallback giả trong production?** Vì khi một shape mới xuất hiện, runtime phải yêu cầu `DynamicLinker` chọn specialization mới rồi gọi, không được trả `"<miss>"` như một kết quả nghiệp vụ thông thường nếu semantic của ngôn ngữ yêu cầu truy cập property.

## 12. MethodType sau mỗi cập nhật phải nhất quán

Phân biệt các chữ ký liên quan:

~~~text
Site (fixed):      (Object)Object
Invocation:        (Object)Object
Guard:             (Object)boolean
Relink fallback:   (Object)Object
~~~

Trong demo 2, các loại đều khớp sẵn. Với language linker thực, raw target có thể mang kiểu cụ thể hơn, ví dụ `(FieldBean)String`, rồi được thích nghi để phù hợp call site `(Object)Object` qua cơ chế `LinkerServices`.

**Một call site không thay signature vì relink.** Nếu descriptor ban đầu là `(Object)Object`, nó vẫn vậy sau khi được liên kết với getter trả String, int hoặc một object khác. Không nhầm việc thay target với việc đổi `MethodType` của bytecode.

Mẫu debug:

~~~java
MethodType siteType = site.type();
MethodType targetType = site.getTarget().type();
System.out.println("site: " + siteType);
System.out.println("target: " + targetType);
~~~

Đây là **snippet minh họa**; `site` phải có kiểu `CallSite` và đã được khởi tạo. Với `MutableCallSite`, target hợp lệ cần có method type đúng với site type. Guard có return type boolean, nên không so trực tiếp guard type như thể nó là target method.

Nếu viết custom call site mà tạo guard chain sai, có thể gặp `WrongMethodTypeException`, `ClassCastException` hoặc lỗi lúc set target. Luôn kiểm tra parameter/return types và conversions ở ranh giới linker.

## 13. ResetAndRelink không chỉ là một lời gọi relink khác tên

Xét trạng thái:

~~~text
Trước:
  chain = [Integer, String, Boolean]

Sau relink(Double):
  chain = [Double, Integer, String, Boolean]
  (nếu chưa chạm giới hạn và các mục còn hợp lệ)

Sau resetAndRelink(Double):
  chain = [Double]
~~~

Trong `SimpleRelinkableCallSite`, cả hai lời gọi có thể trông giống nhau vì Simple chỉ giữ một mục. Trong `ChainedCallSite`, sự khác biệt lớn: reset xóa lợi thế PIC đã tích lũy.

Đừng tự gọi reset mỗi khi guard miss trong code ứng dụng. Bình thường **DynamicLinker** quyết định khi nào yêu cầu `resetAndRelink`, chẳng hạn theo chính sách instability hoặc trạng thái của linker. Với một call site cần giữ nhiều shapes, gọi reset bừa sẽ biến cache thành chiến lược “quên hết” gây relink nhiều.

`resetAndRelink` không có nghĩa phải chạy lại bootstrap của `invokedynamic`. Nó là yêu cầu **cập nhật target của cùng site**.

## 14. Hai con số 8 dễ nhầm

Có hai API với giá trị mặc định 8 nhưng vai trò khác nhau.

### A. ChainedCallSite.getMaxChainLength()

Đây là **giới hạn số guarded invocations** trong PIC. Default 8; subclass có thể override để chọn 2, 4, 16... theo workload. Chọn quá lớn làm chi phí dò guard/code size tăng.

### B. DynamicLinkerFactory.setUnstableRelinkThreshold(int)

Đây là **ngưỡng số lần relink** mà sau đó call site có thể được đánh dấu unstable và những link requests tiếp theo nhận tín hiệu này. Theo API JDK 17, default 8, giá trị 0 nghĩa là không đánh dấu unstable bằng threshold đó.

~~~java
DynamicLinkerFactory factory = new DynamicLinkerFactory();
factory.setUnstableRelinkThreshold(8);
DynamicLinker linker = factory.createLinker();
~~~

Đây là **snippet minh họa**, cần imports và được dùng trước `createLinker()`. Giá trị 8 ở đây **không** điều khiển số nhánh trong `ChainedCallSite`. Một site có maxChainLength 2 vẫn có thể relink hơn 8 lần qua nhiều shapes; một site maxChainLength 8 có thể chỉ relink một lần.

Không đặt threshold 0 hoặc một số quá lớn chỉ để “hết relink”: guard misses và invalidation vẫn tồn tại, còn unstable threshold chủ yếu thông báo tình trạng cho linker policy.

## 15. SwitchPoint và invalidating exceptions

Một specialization có thể hết hiệu lực **ngay cả khi receiver vẫn cùng class**. Ví dụ runtime cho phép thay đổi prototype hoặc định nghĩa property sau khi đã tạo optimized handle.

`GuardedInvocation` có thể dùng `java.lang.invoke.SwitchPoint` để đánh dấu assumption còn đúng. Khi runtime invalidates switch point, guarded invocation tương ứng không còn hợp lệ.

~~~text
Before:
  guard shape X + switchpoint valid
  → fast getter is applicable

Runtime:
  property definition changes
  SwitchPoint.invalidateAll(...)

After:
  old assumption invalid
  → fallback/relink for updated semantics
~~~

Đây là sơ đồ, không phải chương trình đầy đủ. Nếu ứng dụng chỉ thay giá trị của một field và getter cũ vẫn đúng, không nhất thiết invalidate specialization. Invalidation dành cho thay đổi assumptions về **cách thao tác**, không phải mọi dữ liệu.

`GuardedInvocation` cũng có thể khai báo một exception class gây invalidation. Khi specialized invocation ném loại exception đó, cơ chế liên kết có thể bỏ specialization và chọn lại. Đừng đánh dấu `RuntimeException` quá rộng làm “invalidating exception” nếu còn muốn phân biệt lỗi nghiệp vụ thật; điều này có thể gây relink khó hiểu và che nguyên nhân.

## 16. Chained không phải LRU cache theo mỗi lần truy cập

Thứ tự chained cache là **mới được liên kết nhất trước**. Theo API, các invocations không tự đảo thứ tự khi một guard được hit.

~~~text
Chain: [C, B, A]

Input C:
  guard C → true          (1 guard)

Input B:
  guard C → false
  guard B → true          (2 guards)

Input A:
  guard C → false
  guard B → false
  guard A → true          (3 guards)
~~~

Vì vậy, nếu A cực kỳ “hot” nhưng được link rất sớm và nằm cuối chain, nó có thể trả đúng mà phải qua vài checks. Chained giúp giảm relinks trong workload đa hình nhỏ, không bảo đảm lookup O(1) như hash map.

Khi chain đầy, một kiểu cũ bị evicted có thể xuất hiện lại và được liên kết mới ở đầu. PIC là một **chính sách tối ưu hóa có giới hạn**, không phải khả năng hỗ trợ kiểu đóng.

## 17. Concurrency và MutableCallSite visibility

`ChainedCallSite` có cơ chế relink an toàn trước nhiều thread cùng cập nhật. Khi có race, một specialization do thread “thua” link có thể bị bỏ, dẫn đến việc link lại một kiểu tương tự trong tương lai. Đừng yêu cầu số lần relink đo bằng counter phải bằng đúng 1 trên mọi lịch chạy đa luồng.

Nhưng còn một bài toán khác: **độ hiển thị của thay đổi target**. Hai implementation kế thừa `MutableCallSite`, nơi cập nhật target phải tuân thủ Java memory model. `DynamicLinkerFactory` cung cấp lựa chọn:

~~~java
DynamicLinkerFactory factory = new DynamicLinkerFactory();
factory.setSyncOnRelink(true);
DynamicLinker linker = factory.createLinker();
~~~

Đây là snippet minh họa. `setSyncOnRelink(true)` yêu cầu linker thực hiện `MutableCallSite.syncAll(...)` sau khi relink, hỗ trợ quy tắc visibility cho các thread dùng chung site. Nó có chi phí riêng, nên một runtime multi-thread cần cấu hình và đo phù hợp.

**Không suy ra** concurrency-safe relink có nghĩa object được gọi, custom linker, guard hoặc mutable state của application tự thread-safe. Đó là các phạm vi đồng bộ riêng.

## 18. Nên chọn Simple hay Chained khi nào?

Nên thu thập số liệu **theo từng call site**, không chọn một chính sách chung chỉ theo cảm giác.

| Dạng traffic | Phỏng đoán ban đầu |
| --- | --- |
| Site chỉ thấy A | Simple thường hợp lý |
| Site thấy A/A/A và rất hiếm B | Simple có thể đủ |
| A, B xen kẽ thường xuyên | Chained thường giảm số lần relink |
| A/B/C/D ổn định | Chained có thể giữ PIC hiệu quả |
| Hàng chục/hàng trăm shapes | Cả hai đều có misses; cần đo và xem chiến lược khác |
| Link invalidated thường xuyên | Cần xem switchpoints/reset và chi phí link |
| Nhiều threads dùng chung | Xem synchronization cùng chi phí relink |
| Một kiểu “hot” nằm cuối chain | Chi phí guard checks có thể bất lợi |

Metrics nên đo: số lần invocation, link requests, guard misses, reset events, chain eviction, invalidation, chi phí mỗi liên kết, JIT warm-up, p95 latency và memory cost. Với benchmarks, tách *cold linkage* (lần đầu) và *steady state* (sau warm-up). Không so tốc độ một lần gọi đầu tiên rồi tuyên bố Simple/Chained tối ưu tuyệt đối.

Nếu cần tự xây call-site policy, hãy xem custom subclass của `ChainedCallSite` để thay max chain trước khi viết hẳn implementation `RelinkableCallSite`; cách đó giữ được các semantics guard/invalidation đã có.

## 19. Khi tự triển khai RelinkableCallSite

Một custom implementation ngoài hai built-ins phải đáp ứng đầy đủ:

1. Có `CallSiteDescriptor` và không thay đổi `Operation`/`MethodType` của điểm gọi một cách tùy tiện.
2. `initialize(relinkAndInvoke)` thiết lập một initial target đúng signature.
3. `relink(...)` gắn liên kết mới nhưng không làm hỏng guard, switchpoints và exception invalidation.
4. `resetAndRelink(...)` bỏ trạng thái cũ theo đúng yêu cầu; không âm thầm giữ các assumptions đã bị xóa.
5. Fallback cuối của chain là callback linker với đúng `MethodType`.
6. Những method handles cần được thích nghi phù hợp call-site type, không chỉ trùng số tham số.
7. Chain/cache không tăng vô hạn; có chính sách eviction và memory lifecycle.
8. Cập nhật call site và đọc cache dưới concurrency cần đúng memory consistency.
9. Không giữ references tới generated classloaders quá lâu nếu runtime cần unload plugin.
10. Test guard pass/miss, re-entry, invalidation, reset, multi-shape và thread contention.

Không nên tạo một `GuardedInvocation` không có guard khi target chỉ xử lý một class: site có thể áp dụng handle đó với receiver khác và ném lỗi thay vì fallback đúng.

## 20. Dynalink và MethodHandles.guardWithTest

Ở tầng thấp, `MethodHandles.guardWithTest(test, target, fallback)` tạo handle có nhánh điều kiện:

~~~text
if test(argument):
    return target(argument)
else:
    return fallback(argument)
~~~

Đây là **mã giả**, không phải Java source hoàn chỉnh. Dynalink xây thêm framework xung quanh primitive này:

~~~text
Operation (GET:PROPERTY:color)
            |
CallSiteDescriptor
            |
DynamicLinker + GuardingDynamicLinker
            |
GuardedInvocation
            |
RelinkableCallSite (policy)
            |
CallSite.dynamicInvoker()
~~~

Với `ChainedCallSite`, nhiều guarded branches có thể được sắp thành một chain. Với `SimpleRelinkableCallSite`, chỉ một guarded branch còn hiệu lực tại một thời điểm. Vì vậy Dynalink không thay thế `MethodHandle`; nó **lựa chọn, thích nghi và cập nhật** những method handles cho các operation cấp cao.

Nếu chỉ cần gọi một phương thức cố định với type đã biết, Java method call hoặc `MethodHandles.Lookup.findVirtual` thường đơn giản hơn việc tạo một Dynalink pipeline. Dynalink có ích khi receiver shapes và operations chỉ quyết định ở runtime.

## 21. Tích hợp với invokedynamic bootstrap

Khi một language runtime biên dịch source động thành JVM classfile, bootstrap của `invokedynamic` có thể tạo call site:

~~~java
// Snippet minh họa; dynamicLinker và parseOperation
// cần được cung cấp bởi runtime.
public static java.lang.invoke.CallSite bootstrap(
        MethodHandles.Lookup lookup,
        String name,
        MethodType type) {
    Operation op = parseOperation(name);
    CallSiteDescriptor desc =
            new CallSiteDescriptor(lookup, op, type);

    return dynamicLinker.link(new ChainedCallSite(desc));
}
~~~

**Không chạy độc lập:** các biến/field `dynamicLinker` và method `parseOperation` chưa được định nghĩa ở snippet. Dynalink không tự parse chuỗi `"GET:PROPERTY:color"` nếu runtime chưa quy định cách mã hóa/giải mã tên.

Sau khi JVM có call site, những lần gọi với receiver mới có thể làm guard fail và relink. Điều này cập nhật **target của site hiện có**, không có nghĩa bootstrap luôn phải thực thi lại mỗi lần đổi kiểu.

Cũng có thể dùng Dynalink trong interpreter mà không tự sinh bytecode bằng cách tạo một `SimpleRelinkableCallSite` hoặc `ChainedCallSite` trong Java source, gọi `DynamicLinker.link` rồi dùng `dynamicInvoker()`, như demo 1.

## 22. Ma trận lỗi thường gặp

| Triệu chứng | Lý do thường gặp | Kiểm tra |
| --- | --- | --- |
| `package jdk.dynalink does not exist` | Module chưa được resolve | `--add-modules jdk.dynalink` hoặc `requires jdk.dynalink` |
| Site không chạy khi gọi | Quên `DynamicLinker.link(site)` hoặc initial callback sai | Kiểm tra initialize và target |
| Simple relink liên tục | A/B xen kẽ hoặc guard quá hẹp | Phân bố receiver, số guard misses |
| Chained vẫn relink thường xuyên | Chain overflow, reset, invalidation hoặc guard mismatch | `getMaxChainLength()`, assumptions |
| Sau reset không thấy kiểu cũ | Reset đúng nghĩa bỏ prior linkage | Phân biệt với `relink` |
| `WrongMethodTypeException` | Method types giữa target/site không khớp | In `site.type()`, `getTarget().type()` |
| `ClassCastException` khi chuyển receiver | Thiếu guard hoặc adapter cast sai | Kiểm tra runtime class, LinkerServices |
| Tên property không được tìm thấy | Sai namespace/member visibility | Dùng đúng `GET:PROPERTY`, kiểm tra getter/field access |
| Dùng `named("color")` nhưng vẫn truyền tên argument | Lẫn fixed name với dynamic-name slot | Descriptor getter cố định thường chỉ cần receiver |
| Tưởng PIC là cache không giới hạn | Default 8, eviction, invalidation | Theo dõi số shapes |
| Thấy target cũ ở thread khác | Visibility của MutableCallSite, linker synchronization | Xem `setSyncOnRelink` |
| Giữ plugin loader mãi | Handles/cache còn tham chiếu class/loader | Quản lý lifecycle của site và linker |
| Benchmark chậm dù ít misses | Guard chain dài, cold JIT | Đo warm-up, guard cost và profile |

Đừng bắt mọi exception rồi “link lại” như một lời giải chung. Lỗi thao tác nghiệp vụ, lỗi phân giải operation và exception được chỉ định invalidation có ý nghĩa khác nhau.

## 23. Câu hỏi tự kiểm tra có đáp án

**1. `RelinkableCallSite` là một loại cache cụ thể hay một interface?**  
**Đáp án:** Interface giao thức để `DynamicLinker` quản lý call site; Simple và Chained là hai implementation.

**2. Simple giữ được bao nhiêu guarded invocations cùng lúc?**  
**Đáp án:** Một, theo monomorphic inline cache strategy.

**3. Chained giữ tối đa bao nhiêu mục mặc định?**  
**Đáp án:** 8; có thể override `getMaxChainLength()` trong subclass.

**4. Chained có tự chuyển nhánh vừa hit lên đầu không?**  
**Đáp án:** Không; thứ tự dựa trên thời điểm **liên kết**, newest linked đứng trước, không reorder vì hit.

**5. Vì sao traffic A,B,A,B có thể bất lợi cho Simple?**  
**Đáp án:** Khi guard A không áp dụng cho B, cache một mục phải thay B; A quay lại thường phải liên kết lại.

**6. Chained đã giữ A và B thì A lần sau có chắc chắn hit không?**  
**Đáp án:** Chỉ khi guard và assumptions còn hợp lệ và branch chưa bị evict/reset; không thể bảo đảm vô điều kiện.

**7. Ai cấp `relinkAndInvoke` cho normal Dynalink site?**  
**Đáp án:** `DynamicLinker`, trong quá trình `link(site)` và relinking.

**8. `initialize` để làm gì?**  
**Đáp án:** Cài callback target ban đầu cho call site, cho phép hoãn specialization tới lần gọi với actual arguments.

**9. `relink` khác `resetAndRelink` ở đâu?**  
**Đáp án:** Relink có thể giữ các liên kết cũ hợp lệ; resetAndRelink yêu cầu bỏ prior linkage state và xây lại bằng liên kết mới.

**10. Sao fallback trong demo 2 chỉ trả `<miss>`?**  
**Đáp án:** Đó là fallback mô phỏng, không phải callback của DynamicLinker; demo dùng để quan sát cache, không tự link khi miss.

**11. Tại sao `CallSiteDescriptor` không chứa giá trị `color="red"`?**  
**Đáp án:** Nó giữ operation, lookup và type; giá trị field thuộc receiver instance được đọc lúc invocation.

**12. `(Object)Object` có tự đổi thành `(FieldBean)String` sau liên kết không?**  
**Đáp án:** Không, call-site type cố định. Internal handle có thể được thích nghi cho type đó.

**13. Khi nào switch point gây relink dù receiver class không đổi?**  
**Đáp án:** Khi một assumption ngoài class type không còn hợp lệ, chẳng hạn layout/prototype bị thay đổi.

**14. Giới hạn 8 của PIC và unstable relink threshold 8 có cùng ý nghĩa không?**  
**Đáp án:** Không. Một là số cached guarded invocations; một là ngưỡng số lần relink để đánh dấu instability.

**15. Thêm `setSyncOnRelink(true)` giải quyết thread safety toàn ứng dụng không?**  
**Đáp án:** Không; nó liên quan visibility của cập nhật MutableCallSite target, không tự bảo vệ state của receiver/linker.

**16. Nếu target có kiểu không khớp descriptor, phải làm gì?**  
**Đáp án:** Thích nghi đúng qua LinkerServices/MethodHandle adapters, kiểm tra method types trước khi cài.

**17. Có bắt buộc sinh bytecode invokedynamic để học Dynalink không?**  
**Đáp án:** Không. Demo 1 sử dụng `DynamicLinker.link` và `CallSite.dynamicInvoker()` trực tiếp trong Java.

**18. Vì sao PIC dài không nhất thiết nhanh hơn?**  
**Đáp án:** Có thể phải thử nhiều guards mỗi lần invocation, gây CPU/JIT cost; nhiều shape còn gây eviction.

**19. `GuardedInvocation` chỉ chứa một invocation handle hay còn gì khác?**  
**Đáp án:** Có thể chứa guard, switch points và invalidating exception class tùy chọn.

**20. Khi nào chọn `ChainedCallSite`?**  
**Đáp án:** Khi một site thường thấy tập shapes nhỏ, lặp đi lặp lại, và lợi ích tránh relink lớn hơn chi phí guard chain.

## 24. Checklist triển khai

- [ ] Xác định đúng operation (`GET:PROPERTY`/`GET:ELEMENT`/`CALL`/`NEW`).
- [ ] Tạo đúng `CallSiteDescriptor` với lookup, operation và MethodType.
- [ ] Tạo `DynamicLinker` trước khi link site.
- [ ] Dùng `link(site)` để initial target biết relink khi nhận arguments.
- [ ] Chọn Simple cho site gần monomorphic; Chained cho polymorphism nhỏ, lặp lại.
- [ ] Nếu subclass Chained, giữ `getMaxChainLength() >= 1`.
- [ ] Hiểu rõ guard, invocation, invalidation và fallback.
- [ ] Không đồng nhất guard miss với exception nghiệp vụ.
- [ ] Không gọi `resetAndRelink` khi muốn giữ branches cũ.
- [ ] Kiểm tra site type không đổi qua các lần relink.
- [ ] Đo số relinks, guard misses, eviction và latency thay vì chỉ so stdout.
- [ ] Với đa luồng, xem `setSyncOnRelink` và đồng bộ trong custom linker/receiver.
- [ ] Cấp module `jdk.dynalink` đúng ở compile/runtime.
- [ ] Kiểm tra classloader lifecycle nếu liên kết tới classes sinh động.
- [ ] Test cache với input A/A, A/B/A/B, nhiều kiểu hơn chain length, invalidation và reset.

## 25. Tài liệu JDK tham khảo

- [JDK 17 — Module jdk.dynalink](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html): sơ đồ tổng quan, JavaBean GET, linkers và call sites.
- [JDK 17 — DynamicLinker](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html): `link(RelinkableCallSite)` và delayed linking.
- [JDK 17 — RelinkableCallSite](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/RelinkableCallSite.html): `initialize`, `relink`, `resetAndRelink`.
- [JDK 17 — SimpleRelinkableCallSite](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html): monomorphic strategy.
- [JDK 17 — ChainedCallSite](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/ChainedCallSite.html): PIC, giới hạn mặc định, thứ tự eviction, concurrency.
- [JDK 17 — GuardedInvocation](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardedInvocation.html): guard/target/switchpoints/invalidating exception semantics.

## 26. Kết luận

`RelinkableCallSite` định nghĩa **giao thức cập nhật** mà `DynamicLinker` dùng cho một điểm gọi động. `SimpleRelinkableCallSite` giữ một specialization có guard, phù hợp khi một site gần như chỉ thấy một shape; `ChainedCallSite` giữ nhiều guarded invocations thành PIC, mặc định tối đa 8, để tái sử dụng các specialization trên nhiều shapes.

Điểm phân biệt quan trọng nhất là **giữ hay quên liên kết cũ**. `relink` có thể bổ sung vào chuỗi, còn `resetAndRelink` yêu cầu bỏ trạng thái đã tích lũy. Khi guard miss, fallback của DynamicLinker có trách nhiệm tìm và cài specialization mới, không phải chạy bootstrap vô hạn hoặc tự thay đổi chữ ký call site.

Hiểu được **descriptor → initial fallback → GuardedInvocation → guard pass/miss → relink/reset → cached target** sẽ giúp bạn thiết kế, đọc và debug runtime dispatch đúng, đồng thời chọn chiến lược cache dựa trên dữ liệu thật.
