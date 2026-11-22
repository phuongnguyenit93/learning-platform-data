# GuardedInvocation cùng điều kiện bảo vệ trong Java Dynalink

## 1. GuardedInvocation là gì?

GuardedInvocation là lớp thuộc package jdk.dynalink.linker trong module jdk.dynalink. Nó biểu diễn một MethodHandle chỉ hợp lệ khi các điều kiện liên kết còn đúng.

Một GuardedInvocation gom bốn thành phần:

1. **Invocation**: MethodHandle thực hiện thao tác đã liên kết.
2. **Guard**: MethodHandle trả về boolean để kiểm tra invocation có phù hợp với các đối số hiện tại hay không.
3. **SwitchPoint**: một hoặc nhiều điểm vô hiệu hóa liên kết từ bên ngoài.
4. **Exception type**: loại exception mà nếu invocation ném ra thì liên kết được xem là không còn hợp lệ.

Guard, SwitchPoint và exception type đều có thể không được cung cấp. Nếu không có cả ba, invocation là unconditional: nó không có điều kiện guard hoặc cơ chế invalidation đi kèm.

GuardedInvocation là một đối tượng bất biến. Khi cần thay đổi invocation, guard hoặc switch point, API tạo ra một GuardedInvocation mới.

## 2. Dynalink giải quyết bài toán gì?

Dynalink là thư viện JDK dùng để liên kết động các thao tác cấp cao trên object, chẳng hạn:

- Đọc hoặc ghi property.
- Truy cập phần tử collection.
- Gọi function hoặc method.
- Chọn method theo kiểu đối số tại runtime.
- Thực hiện type conversion theo object model của ngôn ngữ.

Các thao tác này thường được biểu diễn bằng invokedynamic call site. Kiểu object thực tế có thể thay đổi giữa những lần gọi, vì vậy call site cần được liên kết lại khi target cũ không còn phù hợp.

Dynalink sử dụng java.lang.invoke, MethodHandle và CallSite để quản lý việc liên kết. GuardedInvocation là kết quả mà một linker có thể trả về để mô tả target hiện tại cùng điều kiện mà target đó còn hợp lệ.

Module jdk.dynalink được đưa vào JDK từ Java 9 và vẫn có trong các JDK hiện hành. GuardedInvocation là API công khai của module này; không cần Nashorn để sử dụng nó.

Trong ứng dụng dùng named module, khai báo dependency:

~~~java
module example.app {
    requires jdk.dynalink;
}
~~~

## 3. Bốn thành phần của một GuardedInvocation

### Invocation MethodHandle

Invocation là MethodHandle thực hiện thao tác thực tế. Nó không được null.

Ví dụ một handle gọi phương thức đọc property:

~~~java
MethodHandle invocation = lookup.findStatic(
    PropertyLinker.class,
    "readName",
    MethodType.methodType(Object.class, Object.class)
);
~~~

MethodHandle có kiểu rõ ràng. Kiểu tham số phải phù hợp với kiểu của call site sau khi được linker chuyển đổi.

### Guard MethodHandle

Guard là MethodHandle trả về boolean:

- true: invocation phù hợp với các đối số hiện tại.
- false: invocation không phù hợp; call site cần chạy fallback để xử lý hoặc liên kết lại.

Ví dụ guard kiểm tra receiver là String:

~~~java
private static boolean isString(Object value) {
    return value instanceof String;
}
~~~

Guard phải tương thích với invocation theo quy tắc của MethodHandles.guardWithTest. Guard thường nhận các đối số tương ứng với invocation và trả về boolean.

Guard nên rẻ, ổn định và không có side effect. Nếu guard kiểm tra sai điều kiện, call site có thể gọi nhầm implementation hoặc gặp lỗi kiểu dữ liệu.

### SwitchPoint

SwitchPoint cho phép một thành phần khác vô hiệu hóa liên kết đã tạo trước đó. Nó hữu ích khi metadata, cấu hình hoặc cấu trúc object thay đổi.

~~~java
SwitchPoint switchPoint = new SwitchPoint();

GuardedInvocation guarded =
    new GuardedInvocation(invocation, guard, switchPoint);
~~~

Khi cần vô hiệu hóa:

~~~java
SwitchPoint.invalidateAll(new SwitchPoint[] { switchPoint });
~~~

SwitchPoint chỉ chuyển từ trạng thái còn hiệu lực sang invalidated; không có thao tác kích hoạt lại cùng một SwitchPoint. Khi trạng thái thay đổi lần nữa, tạo SwitchPoint mới cho generation mới.

Nếu GuardedInvocation có nhiều SwitchPoint, chỉ cần một SwitchPoint bị invalidated là liên kết không còn hợp lệ.

### Exception type

Constructor có thể nhận một loại Throwable. Nếu invocation ném ra exception thuộc loại đã khai báo, liên kết được xem là không còn hợp lệ và fallback được gọi khi handle đã được compose.

~~~java
GuardedInvocation guarded = new GuardedInvocation(
    invocation,
    guard,
    switchPoint,
    ClassCastException.class
);
~~~

Cách này hữu ích khi một exception hiếm nhưng có ý nghĩa báo rằng giả định liên kết không còn đúng. Không khai báo những exception nghiệp vụ thông thường nếu chúng không có nghĩa là cần relink.

## 4. Tạo GuardedInvocation bằng constructor nào?

Các constructor chính:

| Constructor | Mục đích |
|---|---|
| GuardedInvocation(invocation) | Invocation không có guard hoặc invalidation |
| GuardedInvocation(invocation, guard) | Invocation có điều kiện guard |
| GuardedInvocation(invocation, switchPoint) | Invocation có thể bị SwitchPoint vô hiệu hóa |
| GuardedInvocation(invocation, guard, switchPoint) | Kết hợp guard và một SwitchPoint |
| GuardedInvocation(invocation, guard, switchPoint, exception) | Guard, SwitchPoint và exception invalidation |
| GuardedInvocation(invocation, guard, switchPoints, exception) | Guard, nhiều SwitchPoint và exception invalidation |

Invocation bắt buộc khác null. Guard và SwitchPoint có thể null; exception type cũng là tùy chọn trong các constructor tương ứng.

Nếu guard, switch point và exception đều không có, invocation là unconditional.

## 5. Điều kiện bảo vệ hoạt động như thế nào?

Giả sử call site nhận một đối số Object. Linker tìm được implementation tối ưu cho String:

~~~text
đối số runtime
      |
      v
   guard?
   /    \
 true   false
  |       |
  v       v
invocation fallback
~~~

Khi guard trả về true, invocation được thực hiện. Khi guard trả về false, invocation không được gọi và fallback được thực hiện.

Ví dụ:

- Đối số là String: guard trả về true, dùng fast path.
- Đối số là Integer: guard trả về false, dùng fallback.
- SwitchPoint bị invalidated: liên kết cũ không còn được dùng, fallback chạy.
- Invocation ném exception đã khai báo: fallback xử lý tình huống invalidation.

Guard chỉ xác định invocation có phù hợp với đối số hiện tại hay không. Nó không thay thế việc kiểm tra kiểu, quyền truy cập hoặc logic nghiệp vụ bên trong implementation.

## 6. compose tạo MethodHandle có fallback

GuardedInvocation.compose(fallback) kết hợp invocation, guard, SwitchPoint và exception thành một MethodHandle tổng hợp:

~~~java
MethodHandle linked = guarded.compose(fallback);
~~~

Fallback phải có kiểu tương thích với invocation. Handle tổng hợp sẽ gọi:

- Invocation khi guard đạt, mọi SwitchPoint còn hiệu lực và không có exception invalidation.
- Fallback khi guard trả về false.
- Fallback khi SwitchPoint bị invalidated.
- Fallback khi invocation ném exception type đã khai báo.

compose không tự sửa CallSite hoặc tự tạo một linker mới. Nó chỉ tạo MethodHandle tổng hợp. Trong Dynalink thực tế, fallback thường là relink-and-invoke handle do call site cung cấp để tìm GuardedInvocation mới rồi chạy lại thao tác.

Nếu cần các fallback riêng cho từng nguyên nhân, dùng overload ba tham số:

~~~java
MethodHandle linked = guarded.compose(
    guardFallback,
    switchpointFallback,
    catchFallback
);
~~~

Ba handle phải tương thích với kiểu invocation:

- guardFallback chạy khi guard trả về false.
- switchpointFallback chạy khi SwitchPoint bị invalidated.
- catchFallback chạy khi exception invalidation xảy ra.

## 7. Ví dụ hoàn chỉnh: guard, fast path, fallback và SwitchPoint

Ví dụ sau tạo một GuardedInvocation cho String. Khi đối số là String, fast path được gọi. Khi đối số không phải String, guard thất bại và fallback được gọi. Sau khi SwitchPoint bị invalidated, mọi lời gọi tiếp theo đi qua fallback.

**Tệp GuardedInvocationDemo.java:**

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;
import jdk.dynalink.linker.GuardedInvocation;

public class GuardedInvocationDemo {
    private static String fastPath(Object value) {
        return "fast: " + value;
    }

    private static boolean isString(Object value) {
        return value instanceof String;
    }

    private static String fallback(Object value) {
        return "fallback: " + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType callType =
                MethodType.methodType(String.class, Object.class);

        MethodHandle invocation = lookup.findStatic(
                GuardedInvocationDemo.class, "fastPath", callType);
        MethodHandle guard = lookup.findStatic(
                GuardedInvocationDemo.class, "isString",
                MethodType.methodType(boolean.class, Object.class));
        MethodHandle fallback = lookup.findStatic(
                GuardedInvocationDemo.class, "fallback", callType);

        SwitchPoint switchPoint = new SwitchPoint();
        GuardedInvocation guarded =
                new GuardedInvocation(invocation, guard, switchPoint);

        MethodHandle linked = guarded.compose(fallback);

        System.out.println((String) linked.invokeExact((Object) "hello"));
        System.out.println((String) linked.invokeExact((Object) 42));
        System.out.println("invalidated before: "
                + guarded.hasBeenInvalidated());

        SwitchPoint.invalidateAll(new SwitchPoint[] { switchPoint });

        System.out.println("invalidated after: "
                + guarded.hasBeenInvalidated());
        System.out.println((String) linked.invokeExact(
                (Object) "after invalidation"));
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 --add-modules jdk.dynalink -Xlint:all GuardedInvocationDemo.java
java --add-modules jdk.dynalink -cp . GuardedInvocationDemo
~~~

Output:

~~~text
fast: hello
fallback: 42
invalidated before: false
invalidated after: true
fallback: after invalidation
~~~

Lời gọi đầu tiên thỏa guard nên dùng fastPath. Lời gọi thứ hai truyền Integer nên guard trả về false và fallback được gọi. Sau khi invalidate SwitchPoint, hasBeenInvalidated() trả về true và lời gọi String tiếp theo cũng đi qua fallback.

## 8. GuardingDynamicLinker tạo GuardedInvocation ở đâu?

Trong Dynalink, một linker triển khai GuardingDynamicLinker và cung cấp phương thức:

~~~java
GuardedInvocation getGuardedInvocation(
    LinkRequest linkRequest,
    LinkerServices linkerServices
)
~~~

LinkRequest mô tả yêu cầu liên kết cho một thao tác tại call site. LinkerServices cung cấp các dịch vụ dùng chung như chuyển đổi kiểu và gọi lại dynamic linker.

Một linker thường thực hiện các bước:

1. Đọc operation và kiểu đối số từ LinkRequest.
2. Kiểm tra object hoặc receiver hiện tại.
3. Chọn MethodHandle phù hợp.
4. Tạo guard mô tả khi nào MethodHandle đó còn hợp lệ.
5. Có thể thêm SwitchPoint hoặc exception invalidation.
6. Trả về GuardedInvocation.

Nếu linker không thể xử lý yêu cầu, nó trả về null để linker khác có cơ hội xử lý.

Mẫu mã minh họa:

~~~java
@Override
public GuardedInvocation getGuardedInvocation(
        LinkRequest request,
        LinkerServices services) throws Exception {

    Object receiver = request.getReceiver();

    if (!(receiver instanceof MyObject)) {
        return null;
    }

    MethodHandle invocation = createInvocation(request, services);
    MethodHandle guard = createReceiverGuard(MyObject.class);

    return new GuardedInvocation(invocation, guard);
}
~~~

Đây là cấu trúc minh họa; tên createInvocation và createReceiverGuard là các hàm do linker của ứng dụng định nghĩa. Một implementation thật phải tạo MethodHandle có kiểu phù hợp với CallSiteDescriptor của request.

## 9. Guard helper có sẵn trong Dynalink

Package jdk.dynalink.linker.support cung cấp lớp Guards để tạo các guard thông dụng:

| API | Ý nghĩa |
|---|---|
| Guards.getClassGuard(clazz) | Kiểm tra đối số đầu tiên có đúng class, không chấp nhận subclass |
| Guards.getInstanceOfGuard(clazz) | Kiểm tra đối số đầu tiên là instance của class hoặc subclass |
| Guards.getIdentityGuard(object) | Kiểm tra tham chiếu có cùng identity |
| Guards.isNull() | Kiểm tra đối số đầu tiên là null |
| Guards.isNotNull() | Kiểm tra đối số đầu tiên khác null |
| Guards.isArray(pos, type) | Kiểm tra đối số tại vị trí chỉ định là array |
| Guards.isInstance(clazz, pos, type) | Tạo guard kiểm tra kiểu tại vị trí chỉ định |
| Guards.asType(test, type) | Điều chỉnh kiểu guard và giữ kiểu trả về boolean |

Ví dụ tạo guard kiểm tra receiver là một instance:

~~~java
MethodHandle guard =
    Guards.getInstanceOfGuard(MyObject.class);
~~~

Nếu cần đúng class, không chấp nhận subclass:

~~~java
MethodHandle guard =
    Guards.getClassGuard(MyObject.class);
~~~

Chọn đúng loại kiểm tra. Exact-class guard có thể phù hợp với implementation tối ưu dựa trên cấu trúc chính xác của class; instance guard phù hợp khi subclass cũng tuân theo cùng hợp đồng.

## 10. Điều chỉnh kiểu và biến đổi GuardedInvocation

MethodHandle có kiểu tĩnh. Khi invocation cần phù hợp với call site descriptor, GuardedInvocation cung cấp các phương thức biến đổi:

| API | Tác dụng |
|---|---|
| asType(MethodType) | Điều chỉnh kiểu invocation và guard |
| asType(CallSiteDescriptor) | Điều chỉnh theo kiểu của call site descriptor |
| asType(LinkerServices, MethodType) | Điều chỉnh kiểu bằng dịch vụ chuyển đổi của linker |
| asTypeSafeReturn(LinkerServices, MethodType) | Điều chỉnh return type theo quy tắc chuyển đổi không mất dữ liệu |
| filterArguments(pos, filters) | Lọc đối số của invocation và guard |
| dropArguments(pos, types) | Thêm các đối số bị bỏ qua vào invocation và guard |
| addSwitchPoint(point) | Tạo GuardedInvocation mới có thêm SwitchPoint |
| replaceMethods(invocation, guard) | Thay invocation và guard trong đối tượng mới |

Khi dùng asType, invocation được điều chỉnh theo MethodHandle.asType. Guard cũng được điều chỉnh để trả về boolean và có số tham số phù hợp.

Nếu ngôn ngữ có type conversion riêng, ưu tiên overload nhận LinkerServices để sử dụng các conversion factory mà Dynalink quản lý.

Không ép kiểu bằng cast tùy tiện chỉ để làm MethodHandle khớp chữ ký. Hãy bảo đảm conversion đúng ngữ nghĩa của ngôn ngữ và không làm mất dữ liệu ngoài ý muốn.

## 11. Invalidation và relinking

GuardedInvocation giúp call site tránh phải tra cứu lại target ở mọi lần gọi. Khi target còn hợp lệ, invocation đã liên kết được dùng trực tiếp.

Liên kết cần được làm mới khi:

- Guard trả về false do receiver hoặc shape đã thay đổi.
- SwitchPoint bị invalidated do metadata hoặc cấu hình thay đổi.
- Invocation ném exception type được khai báo là invalidating exception.

Fallback trong hệ thống Dynalink thường gọi lại cơ chế relink của call site. Linker tìm target phù hợp mới, tạo GuardedInvocation mới và thay target của call site.

Với SimpleRelinkableCallSite, call site thường nhớ liên kết gần nhất. ChainedCallSite có thể giữ nhiều liên kết hợp lệ để hỗ trợ polymorphic inline cache. Những call site này là thành phần của Dynalink; GuardedInvocation chỉ mô tả một liên kết có điều kiện.

hasBeenInvalidated() chỉ báo có SwitchPoint bị invalidated. Nó không cho biết guard từng trả về false và cũng không phải cờ tổng hợp cho exception invalidation.

## 12. Lỗi thường gặp

- **Dùng invocation sai chữ ký:** MethodHandle phải phù hợp với kiểu call site sau khi điều chỉnh.
- **Guard không trả về boolean:** guard cần có kiểu trả về boolean theo hợp đồng guardWithTest.
- **Guard không tương thích với invocation:** kiểm tra arity và kiểu tham số trước khi tạo GuardedInvocation.
- **Guard có side effect:** guard có thể được gọi nhiều lần; nên giữ phép kiểm tra thuần và rẻ.
- **Guard kiểm tra thiếu điều kiện:** invocation tối ưu có thể chạy với receiver không phù hợp.
- **Không có fallback hợp lệ:** compose cần fallback có kiểu tương thích với invocation.
- **Nhầm guard false với exception invalidation:** guard false là điều kiện không phù hợp; exception invalidation xảy ra khi invocation ném đúng loại exception đã khai báo.
- **Nhầm hasBeenInvalidated():** phương thức này chỉ kiểm tra SwitchPoint.
- **Cho rằng SwitchPoint tự liên kết lại call site:** SwitchPoint chỉ làm liên kết cũ không còn hợp lệ; fallback phải thực hiện relink nếu ứng dụng cần.
- **Không tạo SwitchPoint mới sau invalidation:** SwitchPoint đã invalidated không thể được kích hoạt lại.
- **Dùng exception quá rộng:** chỉ chọn loại exception thực sự có nghĩa rằng giả định liên kết đã sai.
- **Không trả null khi linker không xử lý được request:** linker khác cần có cơ hội xử lý.
- **Cho rằng compose cập nhật CallSite:** compose chỉ tạo MethodHandle tổng hợp; call site phải cài đặt hoặc sử dụng handle đó.

## 13. Chọn cơ chế theo tình huống

| Nhu cầu | Cơ chế |
|---|---|
| Chọn implementation theo kiểu receiver | Guard MethodHandle |
| Kiểm tra chính xác class | Guards.getClassGuard |
| Chấp nhận subclass | Guards.getInstanceOfGuard |
| Kiểm tra receiver identity | Guards.getIdentityGuard |
| Metadata có thể thay đổi độc lập với đối số | SwitchPoint |
| Một exception hiếm báo liên kết cũ không còn đúng | Exception type |
| Tạo handle chạy được với fallback | GuardedInvocation.compose |
| Chuyển đổi kiểu theo ngôn ngữ động | asType(LinkerServices, MethodType) |
| Biến đổi đồng thời invocation và guard | filterArguments hoặc dropArguments |
| Hệ thống cần tìm implementation mới khi điều kiện đổi | Fallback relink-and-invoke |

## 14. Ghi nhớ

GuardedInvocation của jdk.dynalink đóng gói một invocation MethodHandle cùng guard, SwitchPoint và exception type tùy chọn. Guard trả về true khi invocation phù hợp; guard false chuyển sang fallback. SwitchPoint cho phép vô hiệu hóa liên kết từ bên ngoài, còn exception type cho phép một lỗi cụ thể kích hoạt fallback. compose tạo MethodHandle tổng hợp xử lý các đường fallback; trong Dynalink thực tế, fallback thường thực hiện relink call site. Hãy bảo đảm invocation, guard và fallback có chữ ký tương thích, giữ guard rẻ và chính xác, đồng thời tạo SwitchPoint mới khi trạng thái liên kết thay đổi.

## 15. Tài liệu tham khảo

- [GuardedInvocation – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardedInvocation.html)
- [Guards – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.dynalink/jdk/dynalink/linker/support/Guards.html)
- [jdk.dynalink – Java SE 25 Module](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.dynalink/module-summary.html)
- [GuardingDynamicLinker – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardingDynamicLinker.html)
- [ChainedCallSite – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.dynalink/jdk/dynalink/support/ChainedCallSite.html)
