# Phản chiếu, đóng gói dữ liệu ngữ cảnh và cấp phát bộ nhớ trong AOP

Trong *aspect-oriented programming* (AOP), một lời gọi nghiệp vụ có thể được chặn tại *join point* để advice quan sát hoặc thay đổi hành vi. Để thực hiện việc đó, bộ máy AOP có thể phải xác định phương thức đích bằng **reflection**, chuyển phương thức và đối số vào một **ngữ cảnh lời gọi**, rồi cấp phát các đối tượng hoặc vùng nhớ tạm. Đây là ba nguồn chi phí có liên quan nhưng **không đồng nhất**: không phải AOP nào cũng dùng reflection, không phải advice nào cũng cần một context object, và không phải đối tượng tạo ra trong mã nguồn đều trở thành cấp phát heap thực tế sau tối ưu của JVM.

Bài học giải thích các cơ chế này ở cấp AOP tổng quát, cách quản lý vòng đời dữ liệu ngữ cảnh, cách đo allocation thực và cách tối ưu mà không làm sai ngữ nghĩa của advice.

## 1. Đặt đúng vị trí của reflection và context trong AOP

- **Join point** là điểm trong thực thi chương trình có thể được can thiệp; tập join point tùy mô hình AOP, chẳng hạn thực thi hoặc gọi phương thức.
- **Pointcut** chọn các join point cần áp dụng advice bằng điều kiện tĩnh hoặc động.
- **Advice** là xử lý chạy tại join point: trước, sau, khi có lỗi hoặc bao quanh công việc gốc.
- **Proxy** là một cách đưa lời gọi qua lớp điều phối trung gian. Cơ chế khác có thể chèn lệnh vào bytecode bằng *weaving*.
- **Invocation context** là dữ liệu gắn với **một lần thực thi cụ thể**: phương thức/join point, đối tượng đích, đối số, thông tin chuỗi advice, dữ liệu correlation hoặc kết quả/ngoại lệ.
- **Reflection** là khả năng kiểm tra hoặc gọi thành phần chương trình qua metadata ở runtime, chẳng hạn đối tượng `java.lang.reflect.Method` và `Method.invoke`.

Sơ đồ một cách triển khai điển hình:

```text
Caller
  │
  ▼
Proxy / entry point
  │  tìm metadata của join point
  │  chuẩn bị arguments và context
  ▼
Advice 1  →  Advice 2  →  Target Method
   ▲             ▲              │
   └─────────────┴──── return / throw
  │
  ▼
Caller
```

Trong sơ đồ này, runtime có thể dùng reflection để gọi đích. Tuy nhiên, một proxy cũng có thể trực tiếp gọi phương thức hoặc dùng *method handle*; một chương trình đã weave có thể chạy advice như mã Java/bytecode thông thường trong thân phương thức. Không được mặc định rằng mọi mũi tên trong đường gọi đều có một lần `Method.invoke` hay một cấp phát object.

### Phân biệt chi phí khởi tạo và chi phí mỗi lời gọi

| Công việc | Thời điểm điển hình | Ý nghĩa hiệu năng |
|---|---|---|
| Đọc annotation, phân tích kiểu, xây tập pointcut | Khởi tạo / class loading; đôi khi cả runtime | Ảnh hưởng startup và cache metadata |
| Tìm hoặc tạo đối tượng `Method`, chuỗi advice, proxy class | Thiết lập hoặc lần đầu gọi; tùy implementation | Có thể amortize qua nhiều lần gọi |
| Kiểm tra pointcut động | Có thể lặp lại mỗi join point | Ảnh hưởng hot path nếu điều kiện phức tạp |
| Tạo mảng `Object[]`, boxing đối số | Khi lời gọi cần biểu diễn đối số như object | Có thể tạo allocation/GC pressure |
| Tạo context chứa method, target, args, chain index | Thường mỗi invocation, nếu implementation yêu cầu | Ảnh hưởng allocation rate và retention |
| Thực hiện advice và gọi target | Mỗi lần kích hoạt thực tế | CPU, exception handling, I/O, lock tùy nội dung advice |
| Giải phóng tham chiếu và tài nguyên ngữ cảnh | Khi hoàn tất hoặc khi cleanup | Quyết định dữ liệu có bị giữ sống quá lâu |

Một lời gọi có thể tạo **một context dùng chung cho cả chuỗi** hoặc **nhiều context riêng cho từng advice**. Hai mô hình có hành vi tài nguyên rất khác nhau. Cần đọc đường thực thi của công cụ hoặc profile allocation thay vì suy ra từ số advice.

## 2. Reflection xuất hiện như thế nào?

Java reflection cung cấp các API như `Class<?>`, `Method`, `Constructor<?>`, `Field` và `Annotation`. Trong AOP áp dụng lên phương thức, metadata được dùng để biết tên phương thức, kiểu tham số, annotation hoặc quyết định pointcut. Lời gọi đến target có thể thực hiện bằng:

```java
Method method = target.getClass().getMethod(
    "calculate", int.class, int.class
);
Object result = method.invoke(target, 100, 15);
```

Đây là **đoạn minh họa**, chỉ chạy khi `target` có phương thức public `calculate(int, int)` hợp lệ; không phải một chương trình độc lập.

`Method.invoke` có các đặc điểm quan trọng:

1. Nhận target và các tham số dưới dạng `Object` hoặc mảng `Object[]` ở biên API, do đó các giá trị nguyên thủy có thể cần boxing và kết quả nguyên thủy được biểu diễn qua wrapper.
2. Có chi phí điều phối động và các quy tắc kiểm tra truy cập/cách gọi tùy JDK, trạng thái call site và mức tối ưu hiện tại.
3. Nếu chính phương thức đích ném ngoại lệ, `Method.invoke` thường bọc nó trong `InvocationTargetException`; muốn giữ nguyên ngữ nghĩa ngoại lệ đích cần xử lý `getCause()` đúng cách.
4. Với phương thức thành viên, đối tượng target phải phù hợp kiểu khai báo; danh sách tham số và kiểu giá trị phải tương thích.
5. Quy tắc module/access của Java vẫn có hiệu lực. Không nên tùy tiện dùng `setAccessible(true)` để vượt encapsulation; một số truy cập có thể bị cấm với `InaccessibleObjectException`.

### Có nên tìm `Method` ở mỗi lời gọi?

Nếu pointcut đã biết phương thức cần chạy từ lúc thiết lập, việc tra cứu bằng `getMethod(...)` ở mỗi invocation thường là công việc dư thừa. Có thể chuẩn bị và cache metadata bất biến theo phương thức hoặc theo class rồi tái sử dụng.

```text
Không cache:
call → tìm Method → xét metadata → tạo context → gọi target

Có cache phù hợp:
startup/first use → tìm Method + chuẩn bị metadata
call             → lấy metadata đã chuẩn bị → tạo context (nếu cần) → gọi target
```

**Cache metadata không có nghĩa cache mọi context.** `Method` hoặc danh sách advice bất biến có thể được chia sẻ giữa nhiều invocation; đối số, kết quả, ngoại lệ, chỉ số `proceed()` và trạng thái kiểm soát lời gọi lại thường thuộc từng invocation. Chia sẻ nhầm các dữ liệu này làm rò rỉ request, sai tham số và race giữa luồng.

Dùng cache cũng có chi phí: bộ nhớ thường trú, invalidation khi class loader khác nhau và nguy cơ giữ sống `Class`/`Method`/class loader không cần thiết. Khóa cache phải xét cả class loader và chữ ký phương thức khi phù hợp; hai lớp trùng tên do class loader khác nhau có thể là hai kiểu độc lập.

### Reflection, method handle và gọi trực tiếp khác nhau ra sao?

| Đường gọi | Đặc điểm | Điều cần kiểm tra |
|---|---|---|
| Gọi Java tĩnh/ảo thông thường | Call site có thông tin kiểu rõ hơn | Khả năng inline và tính ổn định kiểu đích |
| `Method.invoke` | Chuyển qua API reflection, đối số/kết quả dạng object | Boxing, mảng đối số, exception wrapper, JIT và JDK |
| `MethodHandle.invoke` / `invokeExact` | Gọi thông qua handle với kiểu phương thức xác định | Chi phí tạo/adapt handle, kiểu chữ ký chính xác, call site |
| Mã bytecode được weave | Advice có thể nằm trực tiếp trong mã đã biến đổi | Code size, class loading, mức inline và phạm vi join point |

Không có một bảng xếp hạng tốc độ bất biến cho mọi JDK và workload. Từ các phiên bản Java khác nhau, implementation reflection và khả năng tối ưu của JVM đã thay đổi. Thay `Method.invoke` bằng method handle chỉ để “chắc chắn nhanh hơn” có thể không đem lại lợi ích nếu mã gọi thực tế, adapt kiểu hoặc chuỗi advice mới là nút thắt.

## 3. Dữ liệu ngữ cảnh gồm những gì?

Context phục vụ cho advice cần trả lời: **đang xử lý lời gọi nào, với dữ liệu gì, đang ở bước nào, kết quả ra sao?**

Một cấu trúc khái niệm:

```text
InvocationContext
├── method / joinPoint metadata   ← thường có thể chia sẻ
├── target                        ← tham chiếu đối tượng đích
├── arguments[]                   ← dữ liệu riêng lời gọi
├── current interceptor index     ← trạng thái riêng lời gọi
├── start time / correlation id   ← dữ liệu quan sát
├── attributes/map                ← giá trị bổ sung nếu cần
└── outcome / throwable           ← hoàn tất hoặc lỗi
```

Đối với advice đo thời gian, không cần mặc nhiên có cả `Map<String, Object>`, bản sao toàn bộ tham số, tên tất cả annotation và stack trace. Chỉ giữ thời điểm bắt đầu và thông tin định danh cần thiết đã đủ cho nhiều trường hợp. Ngược lại, advice audit có thể cần những trường bổ sung đã được xác định rõ bởi yêu cầu dữ liệu.

### Chi phí đóng gói (marshalling/packing)

Đóng gói context thường bao gồm một số bước:

- Biểu diễn đối số qua `Object[]` hoặc danh sách, có thể boxing `int`, `long`, `double` và các kiểu nguyên thủy.
- Tạo wrapper hoặc object định danh invocation.
- Lấy tên phương thức, thông tin annotation hoặc ký hiệu mô tả điểm gọi.
- Tạo tag/attribute map, chuỗi correlation, nhãn metric hay snapshot đối số.
- Tạo closure/lambda giữ những tham chiếu cần dùng khi interceptor tiếp tục hoặc chạy bất đồng bộ.
- Nếu cần, tạo bản sao phòng vệ để ngăn mutation dữ liệu giữa các advice.

Các bước trên có thể gây **CPU overhead**, **allocation**, **pressure lên GC** và **retention**. Chúng có thể tồn tại tách biệt: sao chép dữ liệu là việc tiêu CPU ngay cả khi một số cấu trúc được tái sử dụng; giữ một tham chiếu đến object lớn có thể gây giữ sống nhiều bộ nhớ dù bản thân context chỉ nhỏ.

### Tham chiếu, bản sao nông và bản sao sâu

`Object[] snapshot = args.clone()` tạo bản sao **mảng** chứa các tham chiếu; nó **không sao chép sâu** các object được tham chiếu.

Ví dụ nếu `args[0]` là một `List` có thể thay đổi, cả mảng gốc và mảng clone vẫn có thể cùng trỏ tới đúng list đó. Một advice thay đổi list có thể ảnh hưởng đối tượng mà advice khác nhìn thấy, dù đã clone mảng. Không gọi `args.clone()` là một snapshot bất biến hoàn toàn.

Ba lựa chọn thường gặp:

1. **Không sao chép:** tiết kiệm thời gian/bộ nhớ nhưng advice phải tuân thủ hợp đồng không sửa hoặc phải chấp nhận việc sửa đối số.
2. **Sao chép nông:** bảo vệ cấu trúc mảng đối số, không bảo vệ trạng thái mutable sâu bên trong.
3. **Sao chép sâu hoặc chuyển sang DTO bất biến:** tốn thêm CPU/bộ nhớ và có thể không khả thi với tài nguyên, stream hoặc object graph có vòng; chỉ áp dụng khi thực sự cần tính cô lập.

Nếu một advice đổi đối số rồi gọi `proceed()`, đó có thể là chức năng AOP được thiết kế chủ động. “Tối ưu” bằng cách clone hoặc bỏ clone đối số mà không kiểm tra hợp đồng có thể làm thay đổi kết quả nghiệp vụ.

## 4. Cấp phát bộ nhớ: allocation khác retained memory

Cần phân biệt bốn khái niệm:

- **Allocation count:** số object/array được tạo theo phép đo phù hợp.
- **Allocated bytes/op:** lượng byte cấp phát trên mỗi lần thực thi; dùng để đánh giá áp lực tạo object.
- **Allocation rate:** byte được cấp phát mỗi giây. Một khoản nhỏ mỗi lời gọi có thể trở nên đáng kể ở tần suất cao.
- **Retained heap:** bộ nhớ vẫn reachable sau khi lời gọi kết thúc. Một context bị giữ lại trong map, queue, ThreadLocal hoặc closure có thể làm tăng heap giữ sống dù tổng allocation không lớn.

Ví dụ số học (hoàn toàn **giả định**, không phải benchmark JVM): mỗi lời gọi tạo thêm 400 byte, ứng dụng xử lý 250.000 lời gọi/giây, thì:

```text
400 byte/call × 250.000 call/s
= 100.000.000 byte/s
≈ 95,37 MiB/s
```

Đây là **allocation rate bổ sung**, không có nghĩa heap luôn tăng 100 MB mỗi giây. Nếu đối tượng nhanh chóng mất tham chiếu, GC có thể thu hồi chúng. Tuy nhiên, tốc độ cấp phát cao vẫn có thể tăng tần suất collection, tải CPU của bộ gom rác hoặc đẩy p99 latency lên dưới tải.

Nếu một context giữ tham chiếu đến object 10 MB trong một queue, chi phí giữ sống có thể bị chi phối bởi **đối tượng được tham chiếu**, không phải kích thước của chính context.

### JVM có luôn tạo object như trong mã nguồn?

Không. JVM dùng escape analysis và các tối ưu khác để có thể bỏ bớt cấp phát hoặc inline các lời gọi khi chứng minh được object không cần tồn tại như một thực thể heap quan sát được. Hiệu quả phụ thuộc JVM, JDK, code path và trạng thái JIT. Việc viết `new InvocationContext(...)` chứng tỏ mã *biểu diễn* một đối tượng mới theo ngữ nghĩa Java, nhưng **không bảo đảm profiler phải thấy một cấp phát heap thực tế mỗi lượt**.

Ngược lại, trong một đường gọi khó inline, với callback đa hình hoặc object thoát sang một bộ lưu trữ, JVM có thể không loại bỏ được allocation. Vì thế, tính bytes/op bằng cách cộng kích thước trường của record/class là một ước lượng thiết kế, không thể thay cho phép đo.

### ThreadLocal và luồng thực thi bất đồng bộ

Một số hệ thống gắn correlation data cho advice qua `ThreadLocal` để tránh truyền tham số dọc chuỗi. Cách này tiện cho luồng đồng bộ nhưng có rủi ro:

- Luồng của thread pool có thể được tái sử dụng: nếu không xóa giá trị, dữ liệu invocation trước có thể xuất hiện ở thao tác khác.
- Value trong ThreadLocal có thể giữ nhiều object reachable lâu hơn dự tính.
- Nếu công việc chuyển sang executor/thread khác, giá trị ThreadLocal **không tự truyền** đến thread mới theo cách tổng quát. Các cơ chế thừa kế hoặc propagation cụ thể có ngữ nghĩa riêng.
- Khi xử lý async, vòng đời ngữ cảnh có thể dài hơn stack frame gốc; không được dọn quá sớm nếu nhiệm vụ vẫn cần dữ liệu, và cũng không được giữ vô hạn.

Mẫu đồng bộ có cleanup rõ ràng:

```java
// Chỉ minh họa mẫu quản lý vòng đời, không phải chương trình độc lập.
String previous = CURRENT_TRACE.get();
CURRENT_TRACE.set(traceId);
try {
    return invocation.proceed();
} finally {
    if (previous == null) {
        CURRENT_TRACE.remove();
    } else {
        CURRENT_TRACE.set(previous);
    }
}
```

Các tên `CURRENT_TRACE`, `traceId` và `invocation` trong đoạn trên là thành phần giả định. Khôi phục giá trị trước đó giữ đúng ngữ nghĩa cho lời gọi lồng nhau; `remove()` giúp tránh để lại value ở luồng được dùng lại. Mã thực tế cần có chiến lược truyền ngữ cảnh riêng khi chuyển sang async.

## 5. Ví dụ Java 17+: thấy rõ reflection và việc tạo context

Ví dụ sau dùng **JDK dynamic proxy** để chặn một lần gọi interface. Handler tạo một object context và snapshot nông của mảng đối số, sau đó gọi đích bằng reflection. Biến đếm giúp xác nhận **logic đóng gói được thực thi**; nó không phải công cụ đo số heap allocation sau JIT.

Tạo tệp `AopContextDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public class AopContextDemo {
    public interface Calculator {
        int subtract(int left, int right);
    }

    static final class CalculatorImpl implements Calculator {
        @Override
        public int subtract(int left, int right) {
            return left - right;
        }
    }

    record InvocationContext(Method method, Object[] arguments) {
        // Record giữ một tham chiếu tới mảng; nó không tự clone mảng.
    }

    public static void main(String[] args) {
        Calculator target = new CalculatorImpl();
        AtomicInteger contextsPrepared = new AtomicInteger();

        InvocationHandler handler = (proxy, method, arguments) -> {
            // Object[] mới là bản sao nông, không deep copy object con.
            Object[] snapshot = arguments == null
                ? new Object[0]
                : arguments.clone();

            InvocationContext context =
                new InvocationContext(method, snapshot);
            contextsPrepared.incrementAndGet();

            try {
                return context.method().invoke(
                    target, context.arguments()
                );
            } catch (InvocationTargetException exception) {
                // Chuyển tiếp đúng nguyên nhân từ phương thức đích.
                throw exception.getCause();
            }
        };

        Calculator intercepted = (Calculator) Proxy.newProxyInstance(
            Calculator.class.getClassLoader(),
            new Class<?>[] { Calculator.class },
            handler
        );

        System.out.println("Direct: " + target.subtract(100, 15));
        System.out.println("Proxy: " + intercepted.subtract(100, 15));
        System.out.println("Contexts: " + contextsPrepared.get());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AopContextDemo.java
java AopContextDemo
```

Stdout dự kiến chính xác:

```text
Direct: 85
Proxy: 85
Contexts: 1
```

Diễn giải từng bước:

1. Lời gọi trực tiếp đến `target.subtract(100, 15)` trả về 85 mà không chạy qua handler.
2. Lời gọi `intercepted.subtract(...)` đi qua dynamic proxy; handler nhận đối tượng `Method` và các đối số ở biên handler.
3. Handler clone mảng đối số thành `snapshot`, tạo `InvocationContext` chứa `method` và mảng snapshot, rồi tăng biến đếm.
4. `context.method().invoke(target, context.arguments())` gọi phương thức đích thông qua reflection.
5. Giá trị trả về `int` được biểu diễn dạng object tại ranh giới reflection/proxy và trả lại cho caller dưới kiểu primitive theo chữ ký interface.
6. Nếu phương thức đích ném ngoại lệ, mã bắt `InvocationTargetException` và ném ra nguyên nhân. Ngoại lệ checked không được interface cho phép có thể còn được cơ chế dynamic proxy Java bọc theo hợp đồng của nó.

**Điều ví dụ không chứng minh:** “mỗi proxy call luôn có đúng một heap allocation” hoặc “clone array tốn X ns”. Handler thể hiện **một cách thiết kế cố ý cấp phát thêm**; việc JVM có tối ưu được hay không cần profile trên môi trường thật. Nếu chỉ muốn quan sát join point, một proxy khác có thể không clone mảng và không tạo `InvocationContext`. Trong ví dụ, `record` chỉ khiến **tham chiếu trường** bất biến; các phần tử của `arguments` và object bên trong vẫn có thể bị sửa. Đoạn code không xây dựng đầy đủ chính sách xử lý `equals/hashCode/toString` của proxy trong một thư viện sản phẩm.

## 6. Chuỗi interceptor có thể nhân số lần đóng gói như thế nào?

Giả sử một lời gọi đi qua ba interceptor:

```text
Proxy
  │
  ├─ Context dùng chung (method, target, args)
  │     │
  │     ├─ LoggingInterceptor
  │     ├─ SecurityInterceptor
  │     └─ TimingInterceptor
  │            └─ Target
  │
  └─ trả kết quả hoặc ngoại lệ
```

Nếu ba interceptor chỉ đọc một context chung, chi phí đóng gói có thể chủ yếu đến từ context khởi tạo và state riêng từng interceptor (nếu có). Nhưng nếu mỗi interceptor lại tự dựng map mới, sao chép `Object[]`, stringify tham số và tạo span object, tổng allocation có thể lớn hơn nhiều.

Đừng suy luận máy móc rằng “N interceptor = N context” hoặc “mỗi interceptor = một lần reflection”. Phần lớn cách triển khai có thể chỉ gọi đích một lần ở **cuối chuỗi**. Khi một advice kiểu *around* quyết định gọi `proceed()` nhiều lần, đường thực thi trở nên khác: phương thức đích có thể chạy lại, và số context/đối tượng cấp phát cũng có thể thay đổi theo hợp đồng của implementation.

### Dữ liệu metadata được chia sẻ, trạng thái invocation được cô lập

| Loại dữ liệu | Chia sẻ an toàn trong trường hợp nào? | Không nên chia sẻ khi nào? |
|---|---|---|
| `Method`, chữ ký phương thức | Metadata xác định đúng method/class loader và đủ quyền truy cập | Cache khóa chỉ theo tên khiến lẫn overload/class loader |
| Danh sách interceptor | Danh sách bất biến, interceptor được thiết kế thread-safe | Interceptor giữ mutable state của lượt gọi ngay trên singleton |
| Pointcut matcher | Kết quả tĩnh/bất biến với class/method cụ thể | Điều kiện cần xét đối số hoặc trạng thái từng invocation |
| `Object[] arguments` | Chỉ theo hợp đồng cho phép chia sẻ/không mutation | Dùng lại mảng chung cho các thread hoặc lần gọi |
| `nextIndex`/trạng thái `proceed()` | Thuộc một invocation và được điều phối đúng vòng đời | Dùng lại instance context cho các lời gọi đồng thời |
| Kết quả/ngoại lệ | Truyền cho advice liên quan của chính lượt gọi | Lưu vào trường chung không có khóa hoặc không có khóa định danh |
| Correlation/trace context | Có thể truyền snapshot bất biến có kiểm soát | Giữ tham chiếu sống lâu hơn request hoặc bị lẫn thread |

Mục tiêu tối ưu không chỉ là “ít object nhất”, mà là **ít cấp phát không cần thiết trong khi dữ liệu riêng lời gọi vẫn được cô lập và giữ đúng vòng đời**.

## 7. Các nguồn giữ bộ nhớ sống lâu ngoài ý muốn

Một context 64 byte vẫn có thể tạo ra memory leak gián tiếp nếu nó giữ tham chiếu tới graph dữ liệu lớn. Một số mẫu đáng chú ý:

**1. Map toàn cục lưu context theo id nhưng không xóa:** mỗi request thêm một mục; map ngày càng phình, giữ sống đối số, target hoặc exception. Cần chính sách lifecycle cụ thể, cleanup ở cả đường thành công/lỗi và cơ chế giới hạn dung lượng.

**2. ThreadLocal trên thread pool:** value còn sau khi xử lý request; request kế tiếp chạy cùng thread có thể đọc nhầm và bộ nhớ bị giữ sống. Với context lồng nhau cần restore đúng giá trị cha; với context không có cha thì remove.

**3. Queue async không giới hạn:** advice gửi event mang context hoặc closure bắt giữ target/args; producer nhanh hơn consumer làm hàng đợi tăng. Cần backpressure, bộ đệm giới hạn và quyết định rõ có được phép drop/sampling hay không.

**4. Ghi log bằng cách lưu object gốc:** thay vì trích trường an toàn thành DTO nhỏ, event giữ cả object chứa graph lớn hoặc dữ liệu nhạy cảm. Log/tracing cần giới hạn độ sâu, kích thước và dữ liệu được phép ghi.

**5. Cache class/method không xét class loader:** cache sống lâu có thể vô tình giữ class loader của module/plugin đã dỡ tải; cần xác định vòng đời cache, weak references nếu thực sự phù hợp và cơ chế invalidation.

**6. Giữ `Throwable`/stack trace:** giữ một ngoại lệ trong bộ nhớ có thể kéo theo cause/suppressed chain và các dữ liệu đính kèm; tạo stack trace hoặc stringify mỗi lần cũng tốn CPU. Không bắt lỗi chỉ để lưu vô thời hạn.

Các nguồn giữ sống này tác động đến **retention** chứ không chỉ allocation/op. Một heap dump hoặc retained-size analysis giúp tìm chuỗi tham chiếu thực sự đang ngăn GC.

## 8. Đo allocation và overhead có kiểm soát

Nên đo **ít nhất hai tầng**:

- **Vi benchmark:** cô lập khác biệt giữa gọi trực tiếp, proxy không tạo context, proxy tạo context, context clone mảng, context dựng map, đường reflection/cách gọi khác. Đo ns/op và byte/op dưới cấu hình JDK xác định.
- **Tải hệ thống:** chạy workload đại diện để thấy kết quả trên throughput, CPU, p95/p99, heap, collection, pause và contention. Một đường gọi rất ngắn có thể bị overhead tương đối lớn dù chi phí tuyệt đối nhỏ; ngược lại, retention và GC có thể chỉ xuất hiện khi duy trì tải nhiều phút.

Một ma trận đo có ích:

| Biến thể | Cần làm giống nhau | So sánh gì? |
|---|---|---|
| Gọi đích trực tiếp | Cùng input, cùng output | Baseline |
| Proxy gọi đích trực tiếp | Cùng nghĩa nghiệp vụ | Chi phí đi vào proxy/handler |
| Proxy gọi đích bằng reflection | Cùng nghĩa nghiệp vụ | Phần dispatch reflection nếu so sánh hợp lệ |
| Proxy + context nhỏ | Cùng method và args | Context object / initialization |
| Proxy + clone `Object[]` | Cùng semantics cho lời gọi | Chi phí bản sao nông |
| Proxy + map/tags động | Cùng nội dung context cần thiết | CPU/allocation cho metadata động |
| Proxy + nhiều advice no-op | Chỉ thêm chuyển tiếp | Mức nhạy với độ sâu interceptor |
| Lời gọi sau weaving phù hợp | Cùng tập join point và side effect | Đặc điểm của một cơ chế triển khai khác |

Dùng JMH để tránh các lỗi đo microbenchmark phổ biến:

1. Chạy nhiều warm-up iterations và measurement iterations, nhiều JVM forks khi hợp lý.
2. Đảm bảo kết quả thực sự được tiêu thụ, chẳng hạn với `Blackhole`; tránh dead-code elimination.
3. Cố định JDK, VM flags, machine load, input, kích thước context và tính đa hình của call site.
4. Quan sát cả thông lượng/độ trễ và cấp phát bằng profiler thích hợp, ví dụ JMH GC profiler (`-prof gc`) hoặc JFR allocation events khi phù hợp.
5. Không đặt `System.out.println`, ghi file hoặc gửi trace đồng bộ trong vòng benchmark cơ chế thuần; nếu cần đo advice chứa I/O thì coi đó là trường hợp riêng và đo đầy đủ.
6. Với dữ liệu async, ghi rõ cách truyền context, tốc độ sản xuất/tiêu thụ, kích thước queue, thời gian giữ sống và chính sách drop/backpressure.
7. Quan sát p50/p95/p99 và GC dưới tải thật vì độ trễ đuôi có thể phản ánh queue/retention chứ không phải riêng một lần reflection.

### Đọc các kết quả đúng cách

Ví dụ các giá trị **giả định**:

```text
Direct                 30 ns/op     0 B/op
Proxy + reflection     75 ns/op    32 B/op
Proxy + context       105 ns/op    64 B/op
Proxy + context + map 260 ns/op   200 B/op
```

Các giá trị này chỉ minh họa cách đọc bảng, **không phải kết quả đo thực tế**. Trong ví dụ giả định, không được vội kết luận reflection “tốn 45 ns” trên mọi máy: biến thể còn có thể khác nhau ở boxing, các call site, tối ưu JIT hoặc nhánh điều phối. Muốn kết luận cho một sản phẩm cần profile hot path cụ thể và ghi điều kiện thí nghiệm.

Nếu bytes/op gần 0, không đồng nghĩa không có overhead CPU. Nếu CPU overhead thấp nhưng allocated bytes/op lớn, throughput cao vẫn có thể gây GC pressure. Nếu allocation rate thấp mà heap liên tục tăng, cần điều tra retention, cache hoặc queue thay vì cố giảm một mảng `Object[]` nhỏ.

## 9. Những cách giảm chi phí mà vẫn giữ đúng semantics

### 9.1. Đưa xử lý tĩnh ra khỏi hot path

- Phân tích pointcut, annotation và chữ ký phương thức lúc khởi tạo nếu điều kiện thật sự tĩnh.
- Cache `Method`, method handle, danh sách interceptor hoặc mô tả join point bất biến khi có lifecycle/cache key đúng.
- Tránh quét annotation, duyệt toàn bộ class hierarchy hoặc dựng chuỗi metadata khi mọi thông tin đã biết từ trước.
- Dùng cơ chế phân giải metadata phù hợp với class loader; không biến cache thành nguồn giữ class vô hạn.

### 9.2. Thiết kế context tối thiểu

- Với timing advice, chỉ tạo các trường cần đo; đừng mặc nhiên tạo map/tags/stack trace cho mọi invocation.
- Ưu tiên metadata bất biến có thể dùng chung và state nhỏ riêng cho mỗi invocation.
- Chỉ clone/snapshot đối số khi yêu cầu tính toàn vẹn dữ liệu thực sự cần nó; ghi rõ shallow/deep copy.
- Tránh tạo string trong hot path chỉ để truyền context nội bộ; giữ dạng số hoặc id khi phù hợp.
- Nếu cần object pooling, chứng minh bằng benchmark rằng lợi ích lớn hơn chi phí reset, đồng bộ, lỗi lifetime và retention. Object ngắn hạn thường được JVM/GC xử lý tốt; pooling không luôn có lợi.

### 9.3. Giảm chi phí bên trong advice

- Hoãn stringify/log formatting cho đến khi thật sự cần ghi.
- Lấy một số trường đã chọn thay vì serialize toàn bộ object graph.
- Giới hạn kích thước tag, thông điệp, stack trace và queue sự kiện.
- Đưa những tác vụ I/O/đồng bộ nặng khỏi hot path khi hợp đồng cho phép, kèm backpressure và chính sách lỗi rõ ràng.
- Tránh nhiều advice độc lập cùng sao chép đối số hoặc dựng dữ liệu metadata giống nhau, nếu có thể dùng một snapshot an toàn.

### 9.4. Bảo toàn vòng đời dữ liệu

- Dữ liệu riêng invocation không được chia sẻ bừa giữa các thread.
- Dọn ThreadLocal trong `finally` hoặc qua lifecycle tương đương, kể cả khi có exception.
- Với async callback, xác định ai giữ context, khi nào hết dùng và cách giải phóng.
- Nếu advice có thể retry, short-circuit, hoặc gọi `proceed()` nhiều lần, snapshot và cleanup phải dựa trên hợp đồng thực tế, không giả định đích luôn chạy đúng một lần.

### 9.5. Chọn cơ chế AOP theo mục tiêu và ràng buộc

Proxy dynamic, proxy sinh bytecode, decorator và weaving có cấu trúc dispatch/allocation khác nhau. Một số ứng dụng cần khả năng runtime interception; một số ưu tiên thấp allocation và chọn weaving. Trước khi thay thế, cần bảo đảm vẫn bắt đúng join point, cùng thứ tự advice, cùng semantics đối số/kết quả/ngoại lệ và cùng khả năng quan sát. Nếu thay đổi cơ chế khiến một lời gọi nội bộ trước kia không được chặn nay được chặn, chênh lệch benchmark không còn là cùng một chức năng.

## 10. Sai lầm phổ biến

1. **“AOP = reflection.”** Sai. Reflection là một kỹ thuật tùy chọn; có thể dùng mã proxy gọi trực tiếp, method handle hoặc weaving.
2. **“Cứ gọi reflection là mỗi lần phải tìm Method từ đầu.”** Sai. Có thể dùng metadata được chuẩn bị và cache; thao tác tìm metadata khác thao tác `invoke`.
3. **“Record làm context hoàn toàn immutable.”** Sai. Các field reference của record là final, nhưng object mutable được tham chiếu vẫn thay đổi được.
4. **“Clone `Object[]` bảo vệ mọi tham số.”** Sai. Clone mảng là sao chép nông.
5. **“Mỗi interceptor bắt buộc có một mảng đối số mới.”** Sai. Tùy cấu trúc engine, toàn chuỗi có thể dùng chung context.
6. **“`new` trong source luôn bằng một allocation trong profiler.”** Không chắc. JIT có thể inline hoặc loại bỏ cấp phát khi đủ điều kiện.
7. **“GC thu hồi nhanh thì không có chi phí bộ nhớ.”** Sai. Allocation rate cao vẫn có thể tăng CPU GC/pause; retained references còn là vấn đề khác.
8. **“ThreadLocal là bộ nhớ riêng tự động sạch ở cuối request.”** Sai. Giá trị theo đời thread, không theo đời request; thread pool cần cleanup.
9. **“Method cache càng lớn càng tốt.”** Không chắc. Cache có thể giữ class loader và metadata sống lâu không cần thiết.
10. **“Tối ưu bằng cách không tạo snapshot luôn an toàn.”** Không đúng nếu advice dựa vào ảnh chụp đối số, audit snapshot hoặc ngữ nghĩa độc lập với mutation.
11. **“Cộng kích thước object là đo được bytes/op.”** Không đủ. Object headers, alignment, reference width, escape analysis, TLAB và tối ưu JVM có thể ảnh hưởng.
12. **“Đo riêng reflection là biết chi phí của mọi advice.”** Sai. Advice có thể chi phối bởi format log, I/O, lock, serialization hoặc dữ liệu ngữ cảnh.

## 11. Ba tình huống thực tế

**Tình huống A — hàm tính toán nhỏ được gọi hàng triệu lần:** mỗi lần proxy dựng `Object[]`, context, map tags và gọi đích qua reflection. Bắt đầu bằng phép đo JMH + allocation profiler, sau đó thử bỏ map động, cache metadata hoặc dùng context tối thiểu. Đảm bảo hai biến thể cùng đầu ra và cùng advice semantics.

**Tình huống B — tracing với executor:** advice bắt giữ `InvocationContext` trong callback async. Nếu callback xếp hàng chậm, các context giữ sống đối số lớn; heap và p99 tăng dù phần dispatch reflection rất nhỏ. Cần payload nhỏ, queue giới hạn, backpressure và cơ chế propagation/cleanup rõ ràng.

**Tình huống C — module thay class loader thường xuyên:** cache toàn cục có khóa tên class và value là `Method`. Qua nhiều lần nạp lại, metadata cũ vẫn reachable; profiler thấy class loader/metaspace hoặc heap tăng. Cần gắn cache với vòng đời loader và dọn entry đúng lúc, đồng thời không ghép nhầm class trùng tên.

## 12. Câu hỏi tự kiểm tra

1. **Đâu là khác biệt giữa reflection và context?** Reflection giúp tra cứu/gọi thành phần chương trình qua metadata; context là gói dữ liệu của một lần invocation. Chúng có thể đi cùng nhau nhưng không phụ thuộc bắt buộc.
2. **Tại sao cache `Method` vẫn có allocation/op?** Vì mảng đối số, context, tags hoặc dữ liệu advice vẫn có thể được tạo mỗi lần; cache metadata chỉ loại bỏ một phần công việc.
3. **Bản clone mảng đối số có làm context thread-safe không?** Không đủ nếu phần tử chứa object mutable hoặc context giữ state tiếp tục chuỗi có thể bị chia sẻ.
4. **Khác biệt giữa 100 MiB/s allocation và 100 MiB retained heap?** Allocation rate biểu diễn tốc độ tạo dữ liệu tạm; retained heap biểu diễn dữ liệu vẫn còn reachable. Cần phép đo khác nhau.
5. **Vì sao một queue async có thể nguy hiểm hơn bản thân context?** Queue giữ tham chiếu đến nhiều context và object graph của chúng; nếu không giới hạn, dữ liệu có thể tích tụ nhanh hơn tốc độ xử lý.
6. **Khi nào cần đo JMH và khi nào cần đo tải hệ thống?** JMH giúp cô lập chi phí từng cơ chế; tải hệ thống thể hiện contention, GC, throughput và latency đuôi thực tế.
7. **Có nên mặc định thay reflection bằng method handle?** Không. Cần benchmark cùng semantics trên JDK đích, tính cả lookup/adaptation và hiệu năng call site.
8. **Tối ưu nào dễ làm sai chức năng nhất?** Bỏ snapshot, dùng lại invocation state giữa luồng, làm mất propagation hoặc thay vòng đời/đường cleanup mà chưa kiểm tra hợp đồng của advice.

**Ghi nhớ:** Ba câu hỏi cần giải đáp riêng là **phương thức đích được gọi bằng cách nào**, **dữ liệu nào được tạo/đóng gói mỗi lần** và **dữ liệu đó còn được giữ sống bao lâu**. Chỉ khi phân biệt rõ reflection, CPU allocation, GC và retention, việc tối ưu AOP mới có cơ sở thực nghiệm và không đánh đổi sự đúng đắn.