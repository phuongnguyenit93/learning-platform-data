# 18.6 GuardingDynamicLinker, LinkRequest và LinkerServices cho mô hình đối tượng riêng

**Ngữ cảnh:** Java Advance → dynamic-runtime → 18. Dynalink.

Java có cơ chế `invokedynamic` và `MethodHandle` để xử lý các lời gọi được liên kết khi chạy. Tuy nhiên, nếu đang viết một ngôn ngữ động, template runtime, expression engine, rule engine hay mô hình đối tượng dựa trên bản đồ thuộc tính, một câu hỏi lớn xuất hiện: **Khi caller yêu cầu `obj.color`, JVM nên gọi logic nào nếu `obj` lúc này là đối tượng do runtime của ta định nghĩa, lúc khác lại là JavaBean thông thường?**

**Dynalink** (module `jdk.dynalink`) tổ chức việc lựa chọn và liên kết hành vi đó. Ba API trọng tâm của bài này là:

- **`GuardingDynamicLinker`:** thành phần do runtime tự viết để **nhận diện** object/operation mà mình hiểu, sau đó cung cấp một `MethodHandle` thực hiện hành vi cùng **guard** xác định khi nào linkage còn hợp lệ.
- **`LinkRequest`:** mô tả **yêu cầu liên kết** ở một call site với operation, `MethodType`, đối tượng receiver, các giá trị tham số thực tế tại lúc phát sinh relink, và tín hiệu call site có đang mất ổn định hay không.
- **`LinkerServices`:** các dịch vụ của `DynamicLinker` cấp cho linker để thích nghi `MethodHandle` theo kiểu gọi, xét khả năng chuyển đổi kiểu, phối hợp những bộ chuyển đổi do ngôn ngữ định nghĩa, lọc đối tượng nội bộ hoặc nhờ các linker khác.

Điểm nền tảng: **liên kết không phải chính lời gọi nghiệp vụ**. `GuardingDynamicLinker.getGuardedInvocation` được yêu cầu khi call site cần chọn hoặc chọn lại một đường gọi. Một khi đường gọi đã được cài, các lần invoke có thể **đi thẳng qua guarded handle đã cache**, không gọi linker cho từng request.

## 1. Bài toán: mô hình đối tượng không theo JavaBean

Giả sử runtime có một kiểu `DynamicRecord` lưu các thuộc tính trong `Map<String,String>`:

```text
DynamicRecord {
    fields = {
        "color" : "red",
        "status": "ready"
    }
}
```

Nguồn truy cập của ngôn ngữ động có thể viết `obj.color`. Trong JavaBeans truyền thống, "color" thường tương ứng `getColor()` hoặc field có thể đọc. Nhưng `DynamicRecord` của ta **không có method `getColor()`**; thuộc tính là một key trong map. Nếu chỉ dựa vào reflection trên class, truy cập đó không tự có nghĩa.

Ta muốn một nơi gọi động hỗ trợ:

```text
GET PROPERTY "color" : (Object)Object
SET PROPERTY "color" : (Object,Object)void
```

Đây là các chữ ký của **call site**, không phải Java method declarations. Runtime sẽ hiểu:

- Với receiver `DynamicRecord`: truy cập `Map` theo tên property.
- Với receiver là JavaBean bình thường: để **`BeansLinker`** của Dynalink thử giải nghĩa property theo Java conventions.
- Nếu receiver không phù hợp với bất kỳ linker nào: để runtime xử lý lỗi liên kết/operation không được hỗ trợ theo hợp đồng, **không đoán bừa** một target.
- Nếu receiver của **cùng** GET call site thay từ record sang bean rồi quay lại record: guard của linkage cũ không còn phù hợp, Dynalink tiến hành **relink**.

Đó là lúc cần một `GuardingDynamicLinker` riêng, `LinkRequest` và `LinkerServices`.

## 2. Các vai trò trong một lần dynamic linkage

```text
                  caller: getColorInvoker.invokeExact(receiver)
                                      |
                                      v
                        RelinkableCallSite
                       (GET PROPERTY "color")
                                      |
                         cached guarded invocation?
                           /                    \
                          yes                    no / guard false
                           |                      |
                           v                      v
                     invoke target          DynamicLinker
                                                 |
                                   create LinkRequest
                                                 |
                              prioritized custom linkers
                                                 |
                                  RecordLinker.getGuardedInvocation(
                                     request, services)
                                      /                 \
                           supports receiver?          no
                                  |                     |
                                  v                     v
                          GuardedInvocation        other linkers,
                          (target + guard)        default BeansLinker
                                  |                     |
                           cache in call site <---------+
                                  |
                        guarded target.invoke(...)
                                  |
                           result to caller
```

| Thành phần | Được tạo/tồn tại ở đâu? | Vai trò chính |
| --- | --- | --- |
| `Operation` | Trong `CallSiteDescriptor` | Mô tả GET/SET property, tên property; không phải Method Java cố định |
| `CallSiteDescriptor` | Gắn với `RelinkableCallSite` | Lưu lookup context, operation và `MethodType` của call site |
| `RelinkableCallSite` | Điểm gọi được `DynamicLinker.link` quản lý | Có thể thay cached target khi cần relink |
| `DynamicLinker` | Tạo từ `DynamicLinkerFactory` | Điều phối các linker, chuyển đổi, cài/relink target |
| `GuardingDynamicLinker` | Runtime hoặc thư viện triển khai | Thử liên kết operation cho object model của mình |
| `LinkRequest` | Dynalink cung cấp lúc link/relink | Mang thông tin hiện tại cần để quyết định linkage |
| `LinkerServices` | Do `DynamicLinker` cung cấp | API phối hợp chuyển đổi kiểu và linkers |
| `GuardedInvocation` | Do linker trả về | Cặp target + guard, có thể kèm `SwitchPoint`/exception để invalidation |
| `BeansLinker` | Fallback mặc định của factory | Hỗ trợ liên kết Java object theo Java semantics |

**Một thiết kế hợp lý** không cho custom linker "chiếm" mọi object. Nó nên nhận diện chính xác receiver thuộc runtime mình, hỗ trợ những operation mình hiểu, và **trả `null`** cho yêu cầu không thể xử lý để các linker khác có cơ hội. Điều đó giúp interoperability với Java object và ngôn ngữ khác.

## 3. Định nghĩa hợp đồng của `GuardingDynamicLinker`

Interface chính:

```java
public interface GuardingDynamicLinker {
    GuardedInvocation getGuardedInvocation(
            LinkRequest linkRequest,
            LinkerServices linkerServices) throws Exception;
}
```

Đây là **chữ ký API được lược `public/abstract` để minh họa**, không phải chương trình độc lập.

Các điểm trong contract:

1. **Nhận `LinkRequest`:** trong đó có operation, `MethodType`, receiver và các argument values tại thời điểm link.
2. **Xác định có hỗ trợ hay không:** nếu object không thuộc mô hình của linker, hoặc operation không hiểu, **trả `null`**.
3. **Nếu hỗ trợ, tạo invocation:** một `MethodHandle` thực thi logic đã chọn, có thể đã bind tên thuộc tính hoặc specialization khác.
4. **Tạo guard khi invocation chỉ hợp lệ cho một nhóm receiver:** ví dụ `receiver instanceof DynamicRecord`. Nếu guard thất bại, Dynalink được phép chọn lại linkage.
5. **Giữ chữ ký tương thích với call site:** các parameter types được thích nghi phù hợp; return type handling nên tuân theo chính sách `LinkerServices.asTypeLosslessReturn`/pre-link transformer.
6. **Không tự gọi target nghiệp vụ khi đang link** chỉ để trả kết quả: linker phải trả một executable handle cho các lần invocation tương lai.

**Trả `null` khác với trả handle có kết quả `null`:**

- `return null;` từ `getGuardedInvocation` nghĩa là "linker này không nhận xử lý yêu cầu; thử linker khác".
- Một `GuardedInvocation` có invocation trả `null` nghĩa là "linker đã nhận và hoàn tất operation, giá trị nghiệp vụ bằng null".
- Ném exception khi lỗi cấu hình/không thể tạo target là một tình huống thứ ba; không dùng exception thay cho fallback thông thường.

### Một guard tối thiểu

Với riêng `DynamicRecord`, guard có thể là handle:

```java
public static boolean isRecord(Object receiver) {
    return receiver instanceof DynamicRecord;
}
```

Đây là **snippet phương thức** (giả sử class `DynamicRecord` tồn tại). `MethodType` của guard là `(Object)boolean`. Nó không xét value của `color` mà xét **kiểu object**. Nếu vẫn dùng cùng kiểu object, target method có thể đọc dữ liệu khác nhau ở các lần gọi mà **không cần relink**.

Nếu target đã bind vào **một object cụ thể**, hoặc vào **shape/schema phiên bản cụ thể**, guard chỉ kiểm tra `instanceof` có thể **quá rộng**. Khi đó phải thêm kiểm tra identity, shape, version hoặc sử dụng `SwitchPoint` để invalidation.

## 4. `LinkRequest`: thông tin tại *thời điểm liên kết*

Các phương thức chính:

| Phương thức | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `getCallSiteDescriptor()` | Descriptor của call site: lookup, `Operation` và `MethodType` | Dùng để biết caller đang yêu cầu **hành vi nào** |
| `getReceiver()` | Đối số đầu tiên tại lần gọi đang được link | Thường là object cần truy cập property/method |
| `getArguments()` | Mảng argument values tại thời điểm link | Có thể dùng để specialization, nhưng không phải toàn bộ future arguments |
| `isCallSiteUnstable()` | Hint rằng call site đã bị relink vượt ngưỡng mà factory đặt | Không phải bảo đảm lỗi, mà gợi ý chọn guard rộng hơn |
| `replaceArguments(...)` | Tạo yêu cầu mới với descriptor/arguments khác | Dùng khi cần phối hợp delegation có kiểm soát |

**Một hiểu nhầm lớn:** `LinkRequest` **không phải** một callback nhận mọi lần gọi nghiệp vụ. Trong demo, GET được gọi hai lần liên tiếp trên record, nhưng linker không nhất thiết chạy hai lần. `LinkRequest.getArguments()` chứa **giá trị của lần gọi gây link**, không phải một source dữ liệu sẽ tự cập nhật khi consumer gọi tiếp.

### `getReceiver()` và số lượng đối số

Theo mô hình thông dụng, receiver nằm ở tham số 0 của call site. Trong ví dụ:

```text
GET "color": MethodType (Object)Object
  args[0] = record
  getReceiver() == record
  getArguments().length == 1

SET "color": MethodType (Object,Object)void
  args[0] = record
  args[1] = "blue"
  getArguments().length == 2
```

Nếu thiết kế operation không có receiver ở tham số 0, cần xem lại quy ước linker. `LinkRequest.getReceiver()` lấy đối số đầu nên các mẫu property/method call receiver-based thường bố trí theo cách trên. Code phải kiểm tra arity nếu operation cho phép nhiều biến thể, không truy cập `args[1]` tùy tiện.

`getArguments()` trả một bản sao của array theo interface contract. Đừng viết `request.getArguments()[0]=x` rồi mong đổi arguments của lời gọi gốc. Muốn tạo yêu cầu mới, dùng `replaceArguments` với **descriptor và values hợp lệ**, thường để một linker ủy quyền phần còn lại cho linkers khác.

### `isCallSiteUnstable()` có dùng để đo latency không?

Không. Đây là một **hint về số lần relink**, không phải số lượng invocation, CPU time hoặc độ chậm của method. `DynamicLinkerFactory.setUnstableRelinkThreshold(int)` điều chỉnh khi Dynalink coi site mất ổn định; giá trị mặc định của factory là 8 nếu không cấu hình. Một linker có thể chọn ít specialization hơn để tránh ping-pong nếu `isCallSiteUnstable()==true`.

Trong demo stdout tất cả những lần custom linker được gọi đều in `unstable=false`, vì chưa vượt ngưỡng. Không suy ra mọi application luôn false; khi receiver types thay đổi liên tục, site có thể được đánh dấu unstable.

## 5. `CallSiteDescriptor` và tên operation trong object model

Dynalink không bắt buộc dùng một chuỗi đặc biệt kiểu `"GET:PROPERTY:color"` để định nghĩa tên. Các API `Operation` giúp mô tả cấu trúc rõ ràng:

```java
Operation op = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("color");
MethodType type = MethodType.methodType(Object.class, Object.class);
CallSiteDescriptor descriptor = new CallSiteDescriptor(
        MethodHandles.lookup(), op, type);
```

Đây là **snippet**; cần import `jdk.dynalink.Operation`, `StandardOperation`, `StandardNamespace`, `CallSiteDescriptor` và các class `java.lang.invoke`.

- `StandardOperation.GET`: thao tác lấy.
- `StandardNamespace.PROPERTY`: không gian property; khác `ELEMENT` hoặc `METHOD`.
- `.named("color")`: **tên cố định tại call site**. Một site khác có thể dùng tên `"status"`.
- `MethodType.methodType(Object.class,Object.class)`: runtime caller truyền receiver `Object` và lấy kết quả `Object`. Tên property không xuất hiện trong signature vì nó **được bind ở link time**.
- `MethodHandles.lookup()`: lookup context để Dynalink áp dụng quyền truy cập phù hợp khi cần gọi member Java.

Một custom linker không nên chỉ kiểm tra `method.getName()` như Reflection. Nó kiểm tra **`Operation`** của descriptor, phân biệt `GET` với `SET`, `PROPERTY` với `ELEMENT` và tên của `NamedOperation`.

Trong demo, ta so:

```java
Operation getProperty =
        StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY);
Operation setProperty =
        StandardOperation.SET.withNamespace(StandardNamespace.PROPERTY);
Operation base = named.getBaseOperation();

if (getProperty.equals(base)) {
    // chuẩn bị getter
} else if (setProperty.equals(base)) {
    // chuẩn bị setter
}
```

Đây là snippet từ linker, không phải chương trình độc lập. Với operation có nhiều namespaces, thường cần phân tích `NamespaceOperation` và thứ tự namespaces theo ngữ nghĩa riêng; đừng coi mọi `GET` đều là property getter bất kể namespace.

## 6. `LinkerServices`: vì sao không tự `MethodHandle.asType` mọi nơi?

`LinkerServices` tập trung các dịch vụ của `DynamicLinker`; **không phải** một `CallSite`, cũng **không phải** nơi tự lưu giá trị của object model.

| API | Ý nghĩa | Khi nào hữu ích |
| --- | --- | --- |
| `asType(handle, desiredType)` | Chuyển kiểu handle, bao gồm những conversion được language runtime đăng ký qua `GuardingTypeConverterFactory` | Ghép target có kiểu nội bộ với `MethodType` của caller |
| `asTypeLosslessReturn(handle, desiredType)` | Thích nghi input types và chỉ tự chuyển return type khi chuyển đổi không mất precision/magnitude | Giữ khả năng xử lý chính sách return ở pre-link stage |
| `canConvert(from,to)` | Kiểm tra **có thể có** chuyển đổi tương ứng hay không | Cân nhắc chọn overload/converter |
| `getTypeConverter(from,to)` | Lấy một converter `MethodHandle` giữa hai kiểu | Khi thật sự cần tái dùng converter ngoài bước `asType` |
| `compareConversion(source,t1,t2)` | So sánh hai đường chuyển đổi kiểu | Overload resolution |
| `filterInternalObjects(handle)` | Áp dụng filter nội bộ đã cấu hình, khi có | Ngăn object nội bộ của runtime lộ ra boundary |
| `getGuardedInvocation(linkRequest)` | Nhờ dynamic linker điều phối một yêu cầu link khác | Delegation/composition giữa linkers |
| `getWithLookup(...)` | Chạy thao tác trong ngữ cảnh lookup được cấp | Converters phụ thuộc quyền lookup khi làm việc ngoài relinking thông thường |

**Đặc biệt:** `canConvert` trả `true` **không chứng minh mọi giá trị runtime đều convert thành công**. Ví dụ cast từ `Object` tới `String` có thể đúng với object là String và sai với Integer. Đừng dùng `canConvert(Object.class,String.class)==true` làm validation rằng mọi Object đều có thể trở thành String.

### 6.1 `asTypeLosslessReturn` trong demo

Getter nội bộ có chữ ký:

```text
read(DynamicRecord receiver, String propertyName) : String
```

Sau khi bind `propertyName="color"` bằng `MethodHandles.insertArguments`:

```text
readBound : (DynamicRecord)String
```

Call site lại yêu cầu:

```text
GET color : (Object)Object
```

Ta dùng:

```java
MethodType siteType = request.getCallSiteDescriptor().getMethodType();
target = services.asTypeLosslessReturn(target, siteType);
```

Kết quả `target` trong ca GET có kiểu phù hợp `(Object)Object`: receiver từ `Object` được cast/đổi sang `DynamicRecord` khi gọi, còn return `String` có thể widening an toàn thành `Object`. Guard kiểm tra `instanceof DynamicRecord` trước khi target thực hiện cast. Với setter, target sau bind có `(DynamicRecord,String)void` và được thích nghi thành `(Object,Object)void`; argument thứ hai yêu cầu giá trị `String`.

**Vì sao không tự biến mọi return type thành kiểu site ngay trong linker?** Contract của `GuardingDynamicLinker` khuyến nghị linker chỉ làm những return conversions không mất dữ liệu; factory có **pre-link transformer** để xử lý adaptation cuối cùng, mặc định áp dụng `GuardedInvocation.asType(LinkerServices,MethodType)`. Bằng cách giữ trách nhiệm phân tầng, runtime có thể áp dụng policy ngôn ngữ cho các conversion mất precision hoặc special null behavior một cách tập trung.

### 6.2 `GuardingTypeConverterFactory` cho conversion của ngôn ngữ riêng

Nếu language runtime có kiểu số/chuỗi đặc biệt, một `GuardingDynamicLinker` có thể triển khai thêm `GuardingTypeConverterFactory` để cung cấp chuyển đổi tùy ngữ nghĩa ngôn ngữ; `LinkerServices.asType` sẽ phối hợp converter đó khi chuyển các `MethodHandle`.

Ví dụ một ngôn ngữ muốn ép `DynamicNumber` sang `BigDecimal` hoặc chuỗi có locale cụ thể không thể chỉ dựa vào cast và boxing của Java. Converter cần định nghĩa **hợp đồng thất bại**, null behavior, overflow, thread-safety và quyền lookup. Đừng tự động coi mọi Object có thể parse thành số, nhất là khi caller yêu cầu overload khác.

`LinkerServices.getTypeConverter` luôn trả một handle theo API, nhưng có thể là identity/cast khiến một giá trị cụ thể lỗi lúc chạy. Không nên chỉ kiểm tra handle khác null rồi kết luận conversion của mọi input là an toàn.

### 6.3 Gọi lại `LinkerServices.getGuardedInvocation`: dễ đệ quy

Một linker phức tạp có thể muốn đổi một operation thành operation khác rồi nhờ toàn bộ dynamic linker tìm target. Khi ấy `LinkerServices.getGuardedInvocation(anotherRequest)` có thể hữu ích. Nhưng nếu gọi lại với **cùng request** mà không thay đổi điều kiện, dynamic linker có thể **gọi trở lại chính linker hiện tại**, gây đệ quy vô hạn.

Quy tắc thiết kế:

1. Chỉ delegation khi request mới có **operation/arguments/descriptor khác rõ ràng** và đảm bảo tiến triển.
2. Dùng `LinkRequest.replaceArguments(...)` để thể hiện yêu cầu thay thế, không mutate mảng `getArguments()`.
3. Kiểm tra kết quả có thể `null`; không assume luôn có linker nhận.
4. Thiết kế guard/invalidation cho composed result, tránh capture sai receiver.
5. Không dùng delegation như lời gọi target nghiệp vụ; đây là **quá trình tìm cách liên kết**, không phải xử lý dữ liệu từng lần.

Demo cơ bản không dùng phương thức này vì có đủ logic cho GET/SET; đó là lựa chọn đúng khi không cần composition nâng cao.

## 7. Chương trình Java 17 hoàn chỉnh: custom property object và fallback JavaBean

Chương trình bên dưới là một ví dụ độc lập, chạy được bằng **JDK 17 trở lên** với module `jdk.dynalink`. Nó tạo một custom object model `DynamicRecord` lưu property bằng map, một `GuardingDynamicLinker` cho GET/SET, một JavaBean bình thường để kiểm thử fallback, và hai call sites có kiểu rõ ràng.

**Tạo file `CustomDynalinkDemo.java`**, không cần dependency ngoài JDK. Tên file **phải khớp** tên public class.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.HashMap;
import java.util.Map;
import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.NamedOperation;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.linker.GuardedInvocation;
import jdk.dynalink.linker.GuardingDynamicLinker;
import jdk.dynalink.linker.LinkRequest;
import jdk.dynalink.linker.LinkerServices;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class CustomDynalinkDemo {
    static final class DynamicRecord {
        final Map<String, String> fields = new HashMap<>();
        DynamicRecord(String color) { fields.put("color", color); }
    }

    public static final class JavaBean {
        private final String color;
        public JavaBean(String color) { this.color = color; }
        public String getColor() { return color; }
    }

    public static boolean isRecord(Object receiver) {
        return receiver instanceof DynamicRecord;
    }

    public static String read(DynamicRecord receiver, String key) {
        return receiver.fields.get(key);
    }

    public static void write(DynamicRecord receiver, String key, String value) {
        receiver.fields.put(key, value);
    }

    static final class RecordLinker implements GuardingDynamicLinker {
        static final MethodHandle READ;
        static final MethodHandle WRITE;
        static final MethodHandle GUARD;
        int linkCount;

        static {
            try {
                MethodHandles.Lookup lookup = MethodHandles.lookup();
                READ = lookup.findStatic(CustomDynalinkDemo.class, "read",
                        MethodType.methodType(String.class, DynamicRecord.class, String.class));
                WRITE = lookup.findStatic(CustomDynalinkDemo.class, "write",
                        MethodType.methodType(void.class, DynamicRecord.class, String.class, String.class));
                GUARD = lookup.findStatic(CustomDynalinkDemo.class, "isRecord",
                        MethodType.methodType(boolean.class, Object.class));
            } catch (ReflectiveOperationException ex) {
                throw new ExceptionInInitializerError(ex);
            }
        }

        @Override
        public GuardedInvocation getGuardedInvocation(
                LinkRequest request, LinkerServices services) throws Exception {
            if (!(request.getReceiver() instanceof DynamicRecord)) {
                return null; // let BeansLinker or another linker try
            }
            Operation op = request.getCallSiteDescriptor().getOperation();
            if (!(op instanceof NamedOperation named)
                    || !(named.getName() instanceof String key)) {
                return null;
            }
            Operation base = named.getBaseOperation();
            Operation getProperty =
                    StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY);
            Operation setProperty =
                    StandardOperation.SET.withNamespace(StandardNamespace.PROPERTY);
            MethodHandle target;
            MethodHandle guard = GUARD;
            if (getProperty.equals(base)) {
                target = MethodHandles.insertArguments(READ, 1, key); // (DynamicRecord)String
            } else if (setProperty.equals(base)) {
                target = MethodHandles.insertArguments(WRITE, 1, key); // (DynamicRecord,String)void
                guard = MethodHandles.dropArguments(GUARD, 1, Object.class);
            } else {
                return null;
            }

            MethodType siteType = request.getCallSiteDescriptor().getMethodType();
            target = services.asTypeLosslessReturn(target, siteType);
            linkCount++;
            System.out.println("link:" + (getProperty.equals(base) ? "GET" : "SET")
                    + ":" + key + ":args=" + request.getArguments().length
                    + ":unstable=" + request.isCallSiteUnstable());
            return new GuardedInvocation(target, guard);
        }
    }

    static MethodHandle siteInvoker(DynamicLinker linker,
                                    StandardOperation operation, String name,
                                    MethodType type) {
        CallSiteDescriptor desc = new CallSiteDescriptor(
                MethodHandles.lookup(),
                operation.withNamespace(StandardNamespace.PROPERTY).named(name),
                type);
        return linker.link(new SimpleRelinkableCallSite(desc)).dynamicInvoker();
    }

    public static void main(String[] args) throws Throwable {
        RecordLinker custom = new RecordLinker();
        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setPrioritizedLinker(custom);
        DynamicLinker linker = factory.createLinker();

        MethodHandle get = siteInvoker(linker, StandardOperation.GET, "color",
                MethodType.methodType(Object.class, Object.class));
        MethodHandle set = siteInvoker(linker, StandardOperation.SET, "color",
                MethodType.methodType(void.class, Object.class, Object.class));
        DynamicRecord record = new DynamicRecord("red");
        JavaBean bean = new JavaBean("green");

        System.out.println("get.type=" + get.type());
        System.out.println("set.type=" + set.type());
        System.out.println("record.1=" + (Object) get.invokeExact((Object) record));
        System.out.println("record.2=" + (Object) get.invokeExact((Object) record));
        System.out.println("bean=" + (Object) get.invokeExact((Object) bean));
        System.out.println("record.3=" + (Object) get.invokeExact((Object) record));
        set.invokeExact((Object) record, (Object) "blue");
        System.out.println("record.4=" + (Object) get.invokeExact((Object) record));
        System.out.println("custom.links=" + custom.linkCount);
    }
}
```

### 7.1 Biên dịch và chạy

Chạy từ thư mục chứa `CustomDynalinkDemo.java` với **JDK 17+**:

```bash
javac --release 17 --add-modules jdk.dynalink -encoding UTF-8 CustomDynalinkDemo.java
java --add-modules jdk.dynalink CustomDynalinkDemo
```

`jdk.dynalink` là module của JDK từ Java 9, nhưng không nằm trong `java.base`; với ứng dụng chạy theo **classpath** như demo, thêm `--add-modules jdk.dynalink` để chắc chắn module được đưa vào module graph. Trong một module ứng dụng dùng JPMS, có thể khai báo `requires jdk.dynalink;` trong `module-info.java` thay cho cách cấu hình classpath trong ví dụ.

**Stdout chính xác của ví dụ đã kiểm chứng bằng `javac --release 17` và JDK có module Dynalink:**

```text
get.type=(Object)Object
set.type=(Object,Object)void
link:GET:color:args=1:unstable=false
record.1=red
record.2=red
bean=green
link:GET:color:args=1:unstable=false
record.3=red
link:SET:color:args=2:unstable=false
record.4=blue
custom.links=3
```

### 7.2 Phân tích từng dòng output

1. `get.type=(Object)Object` và `set.type=(Object,Object)void` cho thấy **call-site MethodType**. Chúng không nhất thiết trùng chữ ký Java của getter/setter nội bộ.
2. **Lần GET đầu:** receiver là `DynamicRecord`, guard/link chưa có. Dynalink gọi `RecordLinker.getGuardedInvocation`. Linker hỗ trợ `GET PROPERTY color`, bind `key="color"` và trả guarded invocation. Dòng `link:GET:color:args=1:unstable=false` được in **trong quá trình liên kết**.
3. `record.1=red` là kết quả của target `read(DynamicRecord,"color")`. Đây mới là logic nghiệp vụ.
4. `record.2=red` không có dòng `link:GET` thứ hai: guard phù hợp và `SimpleRelinkableCallSite` tái sử dụng cached linkage. Linker **không chạy lại trên mỗi request**.
5. `bean=green`: receiver là `JavaBean`, guard `isRecord` không còn đúng, Dynalink thực hiện relink. Custom linker **trả `null`**, sau đó fallback `BeansLinker` giải quyết `getColor()` theo JavaBean semantics.
6. `record.3=red`: receiver đổi về `DynamicRecord`. Cache đơn hình (monomorphic) của `SimpleRelinkableCallSite` đã chuyển sang bean, nên phải liên kết lại custom GET. Vì vậy có dòng `link:GET...` thứ hai.
7. `link:SET:color:args=2:unstable=false`: một **call site khác** xử lý `SET PROPERTY color` với 2 parameters; custom linker bind tên property và chuẩn bị setter.
8. `record.4=blue`: setter thay giá trị trong map. GET call site vẫn có custom guard phù hợp, nên **không cần relink** chỉ vì value trong map thay từ red sang blue. Target đọc map khi được gọi.
9. `custom.links=3`: trong trace có ba **lượt custom linker tạo guarded invocation** (GET record lần đầu, GET record sau bean, SET record). Đây không phải tổng số lần `get.invokeExact` thực hiện, cũng không đếm các lần BeansLinker liên kết.

Nếu thay `DynamicRecord` bằng implementation có layout/shape linh hoạt, hãy xem kỹ guard. Trong demo, target **không cache giá trị của key**, nên guard chỉ theo receiver type là đủ. Nếu target được tối ưu hóa theo vị trí slot, thứ tự fields hoặc version của class shape, guard type-only có thể trả dữ liệu sai sau khi cấu trúc đổi.

## 8. Đọc code theo các bước xây dựng linkage

### Bước A — Chuẩn bị `MethodHandle` cho logic riêng

```java
READ = lookup.findStatic(CustomDynalinkDemo.class, "read",
        MethodType.methodType(String.class, DynamicRecord.class, String.class));
WRITE = lookup.findStatic(CustomDynalinkDemo.class, "write",
        MethodType.methodType(void.class, DynamicRecord.class, String.class, String.class));
GUARD = lookup.findStatic(CustomDynalinkDemo.class, "isRecord",
        MethodType.methodType(boolean.class, Object.class));
```

Đây là **snippet** từ `RecordLinker`, chưa độc lập. Việc tìm handle được làm một lần trong static initializer; nếu không tìm được method/không có quyền, class init thất bại rõ ràng. Trong sản phẩm thật, cân nhắc quản lý lookup và lỗi bootstrap riêng.

Các kiểu ban đầu:

```text
READ  : (DynamicRecord,String)String
WRITE : (DynamicRecord,String,String)void
GUARD : (Object)boolean
```

### Bước B — Kiểm tra receiver/operation

```java
if (!(request.getReceiver() instanceof DynamicRecord)) {
    return null;
}
Operation op = request.getCallSiteDescriptor().getOperation();
if (!(op instanceof NamedOperation named)
        || !(named.getName() instanceof String key)) {
    return null;
}
```

Đây là **phần của method `getGuardedInvocation`** trong code hoàn chỉnh. Một linker quan tâm `DynamicRecord` cần từ chối JavaBean, Java Map thuần hoặc đối tượng runtime khác; do đó không nên ép bất kỳ receiver nào thành `DynamicRecord`.

### Bước C — Bind tên property nhưng không bind value

```java
target = MethodHandles.insertArguments(READ, 1, key);
```

Biến `key` chứa tên cố định của site (ví dụ `"color"`); `target` mới có kiểu `(DynamicRecord)String`. Khi được invoke, nó vẫn đọc `receiver.fields.get("color")` **vào thời điểm gọi**, không ghi nhớ chuỗi `"red"` ở lúc link.

Với setter:

```java
target = MethodHandles.insertArguments(WRITE, 1, key);
```

Target mới có kiểu `(DynamicRecord,String)void`. Hai tham số còn lại là **receiver và value thực sự được truyền cho từng lần call**. Không được bind value `"blue"` lấy từ `LinkRequest.getArguments()[1]` nếu muốn setter hỗ trợ mọi giá trị tương lai.

### Bước D — Guard cho GET và SET

GET có một argument receiver:

```text
GET target: (Object)Object
GET guard:  (Object)boolean
```

SET có hai arguments, nên guard được bổ sung một tham số thứ hai **bị bỏ qua**:

```java
guard = MethodHandles.dropArguments(GUARD, 1, Object.class);
```

Kết quả:

```text
SET target: (Object,Object)void
SET guard:  (Object,Object)boolean
```

Guard chỉ kiểm tra tham số 0 là `DynamicRecord`. Tham số value không tham gia kiểm tra type ownership, vì target sẽ cast value thành `String` theo hợp đồng demo. Nếu language runtime muốn hỗ trợ các loại value khác nhau, cần thiết kế converter và/hoặc guard tương ứng.

### Bước E — Thích nghi qua `LinkerServices` và trả `GuardedInvocation`

```java
MethodType siteType = request.getCallSiteDescriptor().getMethodType();
target = services.asTypeLosslessReturn(target, siteType);
return new GuardedInvocation(target, guard);
```

Snippet thuộc method linker. `GuardedInvocation` chứa **invocation + guard**, để `DynamicLinker` cài vào `RelinkableCallSite`. Linker không giữ target sau đó để tự chạy mọi lần, trừ khi có design khác có chủ đích. `LinkerServices` chuyển tham số đúng policy, còn adaptation cuối thuộc pipeline linking của Dynalink.

### Bước F — Tạo call site và lấy live invoker

```java
CallSiteDescriptor desc = new CallSiteDescriptor(
        MethodHandles.lookup(),
        StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY)
                .named("color"),
        MethodType.methodType(Object.class, Object.class));

MethodHandle get = linker.link(
        new SimpleRelinkableCallSite(desc)).dynamicInvoker();
```

Snippet trên cần có `DynamicLinker linker` đã khởi tạo. `DynamicLinker.link(...)` cài ban đầu một cơ chế relink; **lần gọi đầu tiên** với receiver thực tế thường mới yêu cầu custom linker tạo guarded invocation. `dynamicInvoker()` tiếp tục trỏ tới call site, kể cả sau khi target được relink; không cần lấy invoker mới sau mỗi lần đổi receiver.

## 9. Guard: correctness quan trọng hơn cache hit rate

Một `GuardedInvocation` chỉ an toàn khi guard mô tả **đủ điều kiện hợp lệ** của invocation.

| Tối ưu dựa trên | Guard/invalidation cần suy nghĩ |
| --- | --- |
| Chỉ object thuộc custom model `DynamicRecord` | `instanceof DynamicRecord` có thể đủ |
| Target gắn với một instance cụ thể | Kiểm tra identity `receiver == capturedReceiver` |
| Target dùng offset của shape/property layout | Kiểm tra shape/version; có thể thêm `SwitchPoint` |
| Target giả định giá trị input luôn String | Guard value class hoặc converter/cast policy rõ ràng |
| Target phụ thuộc phân quyền/tenant | Kiểm tra policy tại invocation hoặc cơ chế invalidation đáng tin |
| Target dựa trên một method implementation thay được | Invalidate khi version implementation đổi |

Guard quá rộng là **bug correctness**: target cũ bị gọi cho receiver/shape không phù hợp, có thể trả sai dữ liệu hoặc lỗi kiểu. Guard quá hẹp thường đúng về mặt dữ liệu nhưng gây **relink liên tục**, làm mất hiệu năng.

Đừng trả một `GuardedInvocation(target)` **không có guard** cho target chuyên biệt chỉ chấp nhận `DynamicRecord`, vì cùng call site có thể được gọi về sau với JavaBean. Lúc đó Dynalink không có dấu hiệu rõ ràng để relink. Unconditional linkage chỉ hợp lý khi invocation thực sự áp dụng cho **mọi future arguments** của site.

### Kết hợp `SwitchPoint` với guard

Một guard như `instanceof` kiểm tra điều kiện ở lần invoke. `SwitchPoint` có thể biểu diễn **invalidation chủ động** khi runtime thay schema, method table, module version hoặc policy. `GuardedInvocation` hỗ trợ constructor nhận guard kèm switch point, ví dụ snippet:

```java
SwitchPoint switchPoint = new SwitchPoint();
GuardedInvocation linked =
        new GuardedInvocation(target, guard, switchPoint);

// Khi model/scheme version bị thay:
SwitchPoint.invalidateAll(new SwitchPoint[]{switchPoint});
```

Đoạn này **không phải chương trình độc lập**; cần có `MethodHandle target/guard` với chữ ký tương thích và import `java.lang.invoke.SwitchPoint`. Các invocation được xây từ switch point có thể đi vào fallback/relink sau khi nó invalidated. Một switch point đã invalidated **không được reset**; version mới thường cần switch point mới.

**Thực tế:** `SwitchPoint` không tự đồng bộ mutable fields nội bộ, không thu hồi request đã vào target cũ và không áp dụng transaction đa call sites. Thiết kế concurrency, lifecycle và version cần có quy tắc riêng.

### Exception làm điều kiện relink

`GuardedInvocation` cũng có thể kèm một `Class<? extends Throwable>` biểu thị exception được xem là tín hiệu linkage không còn phù hợp. Ví dụ một runtime dùng `ClassCastException` hiếm gặp để quyết định relink thay vì kiểm tra `instanceof` mỗi lần. Cơ chế này chỉ nên dùng nếu exception **thực sự có nghĩa** "assumption của cached target sai", không phải dùng mọi exception nghiệp vụ làm dấu hiệu đổi target.

Nếu target ném `IllegalArgumentException` vì người dùng nhập sai, không nên tự động coi đó là lỗi guard rồi relink vô hạn. Phân biệt exception của business logic và exception liên quan type/shape specialization.

## 10. `SimpleRelinkableCallSite`, `ChainedCallSite` và relinking strategy

Ví dụ dùng `SimpleRelinkableCallSite`, thuộc nhóm **monomorphic inline cache**: chỉ giữ một guarded invocation đang hoạt động. Khi receiver đổi từ `DynamicRecord` sang JavaBean, guard của target record không còn đúng, Dynalink cần link sang JavaBean. Khi quay lại record, cần link lại lần nữa.

`ChainedCallSite` cung cấp kiểu **polymorphic inline cache**, có thể giữ chuỗi nhiều guarded invocations. Nó thường thích hợp khi một vị trí gọi gặp vài receiver shapes/types ổn định. Tuy nhiên phải benchmark workload:

| Tình huống | `SimpleRelinkableCallSite` | `ChainedCallSite` |
| --- | --- | --- |
| Gần như chỉ một receiver type | Rất đơn giản, ít guard chain | Có thể không cần thêm độ phức tạp |
| Luân phiên 2–4 types | Có thể relink liên tục | Có thể giảm relink nhờ cached guards nhiều type |
| Quá nhiều types/shape churn | Relink nhiều, có thể megamorphic | Chain cũng có thể trở nên dài/đắt; giới hạn và chiến lược runtime quan trọng |
| Trạng thái model thay đổi liên tục | Cần invalidation phù hợp | Vẫn phải invalidation đúng, không tự chữa guard sai |

Dynalink không tự đọc một `Map` để xác định object model. Cache strategy chỉ có ý nghĩa nếu linker tạo đúng invocation và guard. Cũng đừng hiểu `ChainedCallSite` bảo đảm mọi object vĩnh viễn dùng cache: giới hạn chain, invalidation và unstable threshold có thể kích hoạt reset/relink.

### Ngữ nghĩa đa luồng

`SimpleRelinkableCallSite` và `ChainedCallSite` dựa trên mô hình mutable call-site. `DynamicLinkerFactory.setSyncOnRelink(boolean)` quyết định có gọi `MutableCallSite.syncAll(...)` khi relink để phối hợp visibility giữa thread. Javadoc factory khuyến nghị cân nhắc `true` nếu runtime hỗ trợ nhiều threads; mặc định là `false`.

Trong demo **chỉ một thread**, nên không cần thay config để chứng minh ý nghĩa của `GuardingDynamicLinker`. Ứng dụng nhiều thread phải xem xét `setSyncOnRelink(true)` và đồng bộ riêng cho dữ liệu mục tiêu; **setSyncOnRelink không tự khiến `HashMap` mutable thread-safe**. Khi getter/setter của record được gọi đồng thời, phải bảo vệ map (hoặc chọn concurrent data structure) theo mô hình concurrency thực tế.

## 11. Ưu tiên linker và interoperability với JavaBean

`DynamicLinkerFactory` tổ chức nhiều tầng:

```text
setPrioritizedLinker(custom)
            |
            v
 custom GuardingDynamicLinker
   -> accepts DynamicRecord?
            |
       yes /    \ no: return null
          |       |
          v       v
       custom    other discovered linkers
       target       |
                    v
                default BeansLinker fallback
                    |
                JavaBean.getColor()
```

Một điểm quan trọng về cấu hình:

- `setPrioritizedLinker(custom)` thêm custom linker vào vị trí được hỏi sớm.
- Các `GuardingDynamicLinkerExporter` có thể được tự động tìm qua class loader/service loading khi được cấu hình phù hợp; đó là khả năng interoperability nâng cao.
- Nếu không chỉ định fallback khác, factory mặc định có **`BeansLinker`** để xử lý Java object thông thường.
- Nếu `setFallbackLinkers(...)` được gọi với danh sách rỗng, có thể loại bỏ fallback mặc định; **không** assume BeansLinker còn ở cuối pipeline sau mọi cấu hình.
- `getGuardedInvocation` trả `null` là cách tự nhiên để chuyển cơ hội sang linker tiếp theo; nếu mọi linker đều không hiểu operation, Dynalink có thể thất bại khi linking.

Trong demo, JavaBean có:

```java
public static final class JavaBean {
    private final String color;
    public JavaBean(String color) { this.color = color; }
    public String getColor() { return color; }
}
```

Đây là snippet type đã có trong chương trình đầy đủ. Nó **không** phải `DynamicRecord` và custom linker bỏ qua. Default BeansLinker nhận `GET PROPERTY color`, dùng getter public `getColor()`, nên console có `bean=green` **mà không xuất hiện dòng `link:GET` do custom linker tạo**. Đây là ví dụ sống về sự phối hợp giữa object model riêng và Java semantics.

## 12. Định nghĩa object model cẩn thận hơn: GET/SET, missing property và value types

Demo chọn mục tiêu rõ ràng: property names là `String`, values trong `DynamicRecord` cũng là `String`, GET trả `String` và SET nhận `String`.

### Missing property

`Map.get(key)` trả `null` nếu key không tồn tại (và cũng có thể nếu value là null với map cho phép null). Demo không phân biệt hai tình huống này. Trong một dynamic language, bạn có thể muốn:

- Trả giá trị kiểu `undefined` do runtime định nghĩa.
- Ném exception chỉ ra property không tồn tại.
- Cho phép fallback đến prototype/parent object.
- Tự động tạo property với giá trị mặc định.
- Trả `null` như demo.

**Đây là policy của ngôn ngữ/object model**, không phải default bắt buộc của Dynalink. Khi có nhiều namespaces (PROPERTY, ELEMENT, METHOD), cần quy định thứ tự và ưu tiên rõ ràng.

### Value types và type conversion

`SET` trong demo có call site `(Object,Object)void` nhưng setter nội bộ yêu cầu `String`. `LinkerServices` thích nghi target theo `MethodType`; nếu caller đưa một `Integer` làm value, cast/convert không tương thích có thể gây exception. Không dùng `canConvert` như lời hứa mọi Object đều trở thành String đúng semantic.

Nếu ngôn ngữ của bạn quy định rằng `42` phải thành `"42"`, hãy triển khai converter cụ thể hoặc normalize value có chủ đích trước khi gọi target. Điều này nên được kiểm thử với `null`, numbers, booleans, user-defined objects và exceptions, không dùng `toString()` trên mọi thứ một cách tùy tiện nếu có dữ liệu nhạy cảm hoặc side effects.

### Bind **tên** chứ không bind **giá trị**

Khi link `GET PROPERTY color`, đoạn:

```java
MethodHandles.insertArguments(READ, 1, key);
```

chỉ cố định key `"color"`. Đây là lợi ích của NamedOperation: tên property là một phần operation descriptor và thường ổn định tại vị trí gọi; receiver/value thay đổi ở runtime. Nếu code vô tình bind giá trị đầu tiên `"red"` mà nó đọc được từ `LinkRequest.getArguments()`, GET sau khi SET thành blue có thể vẫn trả red, dù guard type còn đúng. Muốn cache **giá trị**, phải có thêm invalidation/guard/version thích hợp.

## 13. API nào làm gì trong quá trình relink?

| Câu hỏi thực tế | Nơi giải quyết đúng |
| --- | --- |
| "Tên operation và kiểu call site là gì?" | `request.getCallSiteDescriptor().getOperation()/getMethodType()` |
| "Receiver của lần liên kết này là object gì?" | `request.getReceiver()` |
| "Có bao nhiêu argument values trong lần link?" | `request.getArguments().length` |
| "Site relink nhiều chưa?" | `request.isCallSiteUnstable()` |
| "Custom model có hiểu receiver này không?" | Logic `GuardingDynamicLinker` (trả null nếu không) |
| "Target handle nào đọc property từ Map?" | `MethodHandles.findStatic/insertArguments` |
| "Dựa vào điều kiện gì có thể dùng target?" | `GuardedInvocation` guard + switch points/exception nếu cần |
| "Làm sao target đổi kiểu thành contract của caller?" | `LinkerServices.asType/asTypeLosslessReturn` và pre-link transformer |
| "Làm sao xử lý JavaBean khi custom linker từ chối?" | Các linker tiếp theo, thường default `BeansLinker` |
| "Khi guard thất bại có cần user tự rebuild call site?" | Không; `RelinkableCallSite` và `DynamicLinker` phối hợp relink |
| "Làm sao giữ nhiều chuyên biệt kiểu receiver?" | Xem `ChainedCallSite`, guard chains và unstable threshold |
| "Làm sao đảm bảo quyền method Java?" | `CallSiteDescriptor` lookup context và Java access/module checks |
| "Khi schema đổi, làm sao invalidate?" | Guard version/shape hoặc `SwitchPoint` với protocol phù hợp |

Đặc biệt, nếu muốn ghi log số lần gọi business, **đừng chỉ đặt counter trong `getGuardedInvocation`**. Nó chỉ đếm **lần liên kết/relink**. Để đếm tất cả business invocations, thêm instrumentation vào target handle hoặc code thực thi target.

## 14. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Không trả `null` khi receiver không thuộc model | Linker "chiếm" JavaBeans, lỗi cast/đọc sai | Trả `null` cho unsupported receiver/operation |
| Trả unconditional invocation chuyên biệt `DynamicRecord` | Sau này receiver là JavaBean vẫn gọi target cũ | Trả guard đúng `instanceof`/shape |
| Guard theo class nhưng target bind một object cụ thể | Receiver khác cùng class được dùng target của object cũ | Guard identity hoặc không bind object |
| Guard theo class nhưng target phụ thuộc schema version | Cache vẫn được dùng sau khi schema đổi | Guard version/`SwitchPoint` invalidation |
| Dùng `LinkRequest.getArguments()` làm state biến đổi của mỗi call | Request chỉ cho một **link-time snapshot** | Future calls lấy args thật qua target signature |
| Mutate array từ `getArguments()` để đổi dispatch | Contract trả array clone | Dùng `replaceArguments` khi tạo request mới |
| Gọi `LinkerServices.getGuardedInvocation` với cùng request | Có thể recurse quay lại chính linker | Tạo request thật sự khác hoặc đừng delegate |
| Không khớp `MethodType` target/guard | Runtime linkage/adaptation có thể lỗi | In `.type()` và kiểm tra `MethodType` theo site |
| Dùng `MethodHandle.asType` tùy tiện, bỏ custom converters | Không áp dụng conversion policy của language runtime | Dùng `LinkerServices` và policy có kiểm chứng |
| Trả value trong `getGuardedInvocation` thay vì `GuardedInvocation` | Nhầm linking với invocation | Tạo `MethodHandle` rồi bọc đúng API |
| Chỉ parse operation bằng tên string mơ hồ | GET property và GET element/method bị nhập nhằng | Dùng `StandardOperation`, `NamespaceOperation`, `NamedOperation` |
| Tin rằng fallback luôn tồn tại | Factory có thể bị cấu hình không có BeansLinker | Kiểm tra `setFallbackLinkers` và runtime wiring |
| Đếm relink như đếm business requests | Một linkage được invoke nhiều lần | Instrument target nếu muốn thống kê business calls |
| Dùng `SimpleRelinkableCallSite` khi luân phiên nhiều types | Có thể ping-pong relink | Xem `ChainedCallSite` và benchmark |
| Nghĩ `setSyncOnRelink(true)` làm mọi state an toàn | Chỉ xử lý visibility của relink call site | Đồng bộ state mutable của object model riêng |
| Quên `--add-modules jdk.dynalink` trên classpath | Module có thể chưa được resolve | Thêm module lúc compile/run hoặc dùng `requires` trong JPMS |
| Để `MethodHandles.lookup()` của class sai quyền truy cập member | Handle creation có thể bị IllegalAccessException | Dùng lookup context hợp lệ, tuân thủ module access |
| Cho linker thay đổi shared mutable maps không đồng bộ | Data races khi nhiều thread GET/SET | Concurrent map/locks/immutable version protocol |
| Xem `canConvert` true là conversion chắc chắn thành công | Một số giá trị có thể cast thất bại | Test runtime values, validate rõ ràng |

## 15. Debug một dynamic call site không trả đúng kết quả

Quy trình điều tra thực tế:

1. **In `CallSiteDescriptor`:** xem `operation`, `MethodType`, lookup context; tên property có đúng không?
2. **Kiểm tra receiver:** `LinkRequest.getReceiver()` là object model nào? Nếu null/JavaBean/Map thuần, custom linker có chủ ý từ chối không?
3. **Đọc `getArguments()` để biết lần link:** nhưng không nhầm với tất cả các lần gọi sau.
4. **Kiểm tra operation:** `NamedOperation` có đúng tên? Base operation có đúng GET/SET + PROPERTY, không phải ELEMENT/METHOD?
5. **Kiểm tra thứ tự linker:** custom có thực sự được thêm bằng `setPrioritizedLinker` trước fallback?
6. **Nếu custom trả `null`:** xem các linker khác, `BeansLinker` có hiểu receiver và operation không?
7. **Kiểm tra method handle types:** trước và sau `insertArguments`, `services.asTypeLosslessReturn`, `new GuardedInvocation(...)`.
8. **Kiểm tra guard semantics:** guard false có đúng khi receiver type đổi? Có quá rộng khi object schema đổi không?
9. **Theo dõi số lần relink:** nếu luân phiên types, `SimpleRelinkableCallSite` có thể relink thường xuyên; cân nhắc `ChainedCallSite`.
10. **Nếu lỗi chỉ khi nhiều thread:** kiểm tra `setSyncOnRelink`, mutable state của target, invalidation và race.
11. **Nếu lỗi access:** xem `CallSiteDescriptor` lookup, JPMS exports/opens, class loader identity và quyền của target method.
12. **Nếu lỗi conversion:** xem `LinkerServices.canConvert/getTypeConverter` và policy của `GuardingTypeConverterFactory`.
13. **Nếu đầu vào bị thay đổi sau link:** xác định có vô tình bind giá trị lấy từ request thay vì dùng runtime parameters của target.
14. **Không giả định mọi call đều gọi linker:** nên đặt tracing ở cả **linking** và **invocation** với nhãn riêng.

Snippet kiểm tra tại thời điểm linking, không phải chương trình độc lập:

```java
CallSiteDescriptor descriptor = request.getCallSiteDescriptor();
System.out.println("operation=" + descriptor.getOperation());
System.out.println("type=" + descriptor.getMethodType());
System.out.println("receiver=" +
        (request.getReceiver() == null
            ? "null" : request.getReceiver().getClass().getName()));
System.out.println("unstable=" + request.isCallSiteUnstable());
```

**Lưu ý logging:** đừng in `request.getArguments()` nguyên vẹn trong production nếu có mật khẩu, tokens, dữ liệu PII hoặc object có `toString()` tốn kém/side effects. Log tên operation, class identity và số lượng args đủ để chẩn đoán hầu hết lỗi relinking mà không lộ dữ liệu.

## 16. Thiết kế production: quyền truy cập, lifecycle, hiệu năng và ranh giới

### 16.1 Java access và module boundaries

`CallSiteDescriptor` chứa `MethodHandles.Lookup` nhằm cho các linker biết ngữ cảnh caller. Khi custom linker tìm method `private`/package-private hoặc khi `BeansLinker` liên kết Java members, Java language access rules, module exports/opens và class loader runtime identity đều quan trọng.

Không tự giả định `MethodHandles.lookup()` được gọi trong class linker luôn có quyền truy cập private của consumer. Nếu cần hỗ trợ object của module khác, hãy thiết kế API public/export, lookup capabilities phù hợp, và từ chối truy cập không hợp lệ. Dynalink không phải công cụ tự động "vượt private" của JVM.

Đối với JPMS app, module ứng dụng nên khai báo `requires jdk.dynalink;`. Đối với classpath demo, thêm `--add-modules jdk.dynalink`. Không nhầm namespace Java `jdk.dynalink` với package `java.lang.invoke`: Dynalink được xây **trên** MethodHandle/CallSite, nhưng cung cấp tầng operation/linker cao hơn.

### 16.2 Linker không phải storage của mỗi object

Custom linker nên phát ra target handle cho object model; nếu handler cần bộ nhớ theo instance, dùng object receiver/adapter rõ ràng. Cache `GuardedInvocation` thuộc call site, không có nghĩa hệ thống tự cache property values. Trong demo, property mới được đọc từ `HashMap` trên mỗi invocation.

Nếu object model có lazily computed properties hoặc inheritance/prototype chain, tạo guard và invalidation đúng theo mô hình ấy. Không nên giấu business state trong global static Map của linker mà không có policy concurrency/lifecycle.

### 16.3 Tránh premature specialization

Nếu một site thường nhận `DynamicRecord`, cache target theo class có thể hiệu quả. Nếu nhận hàng trăm object shapes, guard chains dài hoặc link liên tục có thể đắt. `isCallSiteUnstable()` cung cấp tín hiệu để chọn một target ít chuyên biệt hơn. Hãy đo: relink count, guard miss rate, fallback path, latency và GC. Đừng đo mỗi thời gian gọi linker rồi kết luận runtime nhanh/chậm: phần lớn calls có thể dùng cached target.

### 16.4 Bảo vệ dữ liệu và lỗi

Một property lookup không chắc hợp lệ chỉ vì guard true. Mô hình riêng vẫn cần xử lý key thiếu, policy `null`, stale snapshot, wrong value types và errors từ underlying Map/database. Đừng dùng relink cho mọi exception nghiệp vụ; không phải lỗi nào cũng có nghĩa cached linkage không còn đúng.

Trong runtime chạy mã không đáng tin, dynamic property access còn có thể là điểm kiểm soát quyền. Guard theo Java type **không** tự chứng minh user có quyền đọc mọi key. Authorization cần kiểm tra trong target hoặc invalidation/version policy được thiết kế an toàn; việc thay linker không tự tạo sandbox.

## 17. Bài tập và đáp án

**Câu 1.** `GuardingDynamicLinker` là nơi thực thi nghiệp vụ ở mỗi lần dynamic call đúng không?

**Đáp án:** Không. Nó tạo một `GuardedInvocation` khi cần link/relink. Sau khi target được cache, nhiều lời gọi đi qua handle mà không gọi linker lại.

**Câu 2.** Khi receiver là JavaBean và custom linker chỉ hỗ trợ `DynamicRecord`, nên trả giá trị nào từ `getGuardedInvocation`?

**Đáp án:** Trả **`null`** để các linker tiếp theo, thông thường `BeansLinker` fallback, có cơ hội xử lý. Không ném cast exception làm cơ chế fallback mặc định.

**Câu 3.** GET call site có kiểu `(Object)Object`. Linker nội bộ có `read(DynamicRecord,String)String`. Cần làm gì?

**Đáp án:** Bind tên property bằng `insertArguments` thành `(DynamicRecord)String`, rồi thích nghi bằng `LinkerServices.asTypeLosslessReturn` và trả guarded invocation có guard receiver phù hợp.

**Câu 4.** Vì sao guard `(Object)boolean` chỉ kiểm tra `instanceof DynamicRecord` có thể đúng cho demo, nhưng sai nếu target cache field offset theo schema?

**Đáp án:** Demo target đọc Map theo tên key ở mỗi invocation. Nếu cached target phụ thuộc shape/version, type guard quá rộng, cần guard shape/version hoặc switch point invalidation.

**Câu 5.** Nếu cùng GET call site gọi hai lần liên tiếp trên `DynamicRecord`, `getGuardedInvocation` luôn được gọi hai lần không?

**Đáp án:** Không. `SimpleRelinkableCallSite` có thể dùng cached guarded invocation ở lần hai nếu guard hợp lệ; stdout demo chỉ báo một custom link cho hai lời GET đầu tiên.

**Câu 6.** `LinkRequest.getReceiver()` và `getArguments()` có khác nhau?

**Đáp án:** `getReceiver()` là đối số đầu của lần linking (tránh clone toàn array), còn `getArguments()` trả mảng clone chứa toàn bộ args ở lần linking; không phải các giá trị của mọi invocation tương lai.

**Câu 7.** `isCallSiteUnstable()` có nghĩa current invocation quá chậm?

**Đáp án:** Không. Nó là hint site bị relink quá nhiều so với threshold; linker có thể chọn specialization ổn định hơn, không phải latency measurement.

**Câu 8.** `LinkerServices.canConvert(Object.class,String.class)` trả true. Điều này có đảm bảo một `Integer` được convert thành `String` không?

**Đáp án:** Không. `true` chỉ báo có thể tồn tại phép chuyển đổi theo type-level logic; một giá trị cụ thể vẫn có thể thất bại.

**Câu 9.** Một custom linker gọi `LinkerServices.getGuardedInvocation(request)` với chính request mà nó đang xử lý. Nguy cơ gì?

**Đáp án:** Dynamic linker có thể lại gọi chính custom linker với cùng request → đệ quy vô hạn. Cần tạo request khác có tiến triển rõ ràng hoặc không delegate.

**Câu 10.** Vì sao `SimpleRelinkableCallSite` trong demo link custom GET hai lần khi lần gọi trung gian trên JavaBean?

**Đáp án:** Nó có **monomorphic cache**. Khi Bean làm guard của record không hợp lệ, cached linkage đổi sang Bean; quay lại record lại cần custom relink.

**Câu 11.** Muốn giữ cached targets cho nhiều receiver types tại một site, nên cân nhắc class nào?

**Đáp án:** `ChainedCallSite`, một polymorphic inline cache. Vẫn phải đảm bảo guards đúng và benchmark theo type mix.

**Câu 12.** `setSyncOnRelink(true)` có làm một `HashMap` dùng bởi record trở thành thread-safe không?

**Đáp án:** Không. Nó là cơ chế đồng bộ các mutable call-site updates; dữ liệu Map cần concurrency policy riêng.

**Câu 13.** SET property trong demo có 2 tham số. Guard từ `isRecord(Object)` cần thích nghi thế nào?

**Đáp án:** Dùng `MethodHandles.dropArguments(GUARD, 1, Object.class)` để nhận thêm value argument nhưng chỉ kiểm tra receiver. Kết quả guard `(Object,Object)boolean`.

**Câu 14.** Setter thay `red` thành `blue` trong cùng `DynamicRecord` có bắt buộc relink GET không?

**Đáp án:** Không. Trong demo, getter đọc Map ở invocation-time và guard class vẫn đúng. Nếu implementation cache giá trị thì cần invalidation khác.

**Câu 15.** Một call site yêu cầu GET PROPERTY "color" và một site khác yêu cầu SET PROPERTY "color". Có dùng chung `MethodType` không?

**Đáp án:** Không. GET dùng `(Object)Object`; SET trong demo dùng `(Object,Object)void`. Cả operation lẫn signature đều khác nhau.

**Câu 16.** Khi mô hình riêng không có support cho operation, custom linker có nên tự fallback bằng `method.invoke(proxy)` không?

**Đáp án:** Không. Hãy trả `null` để Dynalink hỏi linker khác hoặc dùng `LinkerServices.getGuardedInvocation` với request khác có kiểm soát. Gọi lại proxy/call site bừa bãi có thể tạo vòng lặp.

**Câu 17.** Linker có thể trả `GuardedInvocation` không guard không?

**Đáp án:** Có khi invocation thực sự **unconditional** với mọi future arguments, nhưng với target type-specialized thì thường phải có guard hoặc cơ chế invalidation khác.

**Câu 18.** `NamedOperation` khác `StandardNamespace.PROPERTY` ở đâu?

**Đáp án:** NamedOperation gắn **tên cố định** (ví dụ `"color"`) vào một operation; PROPERTY mô tả **namespace** của thao tác. GET/SET mô tả động từ hành động.

## 18. Tóm tắt kiến thức

- **Dynalink nối operation động với MethodHandle/CallSite**, không tự thay thế ngôn ngữ Java hoặc Java reflection.
- **`GuardingDynamicLinker`** nhận `LinkRequest` + `LinkerServices`, chọn target theo receiver/operation và trả `GuardedInvocation` với guard đủ mạnh. **Trả null** nếu không hỗ trợ để linker khác thử.
- **`LinkRequest`** mô tả lần cần link/relink, gồm descriptor, receiver, args tại link-time và unstable hint; **không phải mỗi lần business invocation**.
- **`LinkerServices`** xử lý adaptation/conversions, phối hợp type converters, fallback delegation; `asTypeLosslessReturn` tránh tự ép return mất dữ liệu trong custom linker.
- **`CallSiteDescriptor`** mô tả tên GET/SET PROPERTY và `MethodType`; `SimpleRelinkableCallSite` là monomorphic cache còn `ChainedCallSite` hỗ trợ polymorphic caching.
- **Guards quyết định correctness:** receiver type/identity/shape/version phải phù hợp với những assumption đã specialize. Khi guard false hoặc invalidation, Dynalink relink.
- **Object model riêng và JavaBean có thể cùng tồn tại:** custom prioritized linker xử lý `DynamicRecord`, fallback `BeansLinker` xử lý `getColor()`.
- **Giữ đúng ranh giới:** relinking khác invocation; caching method handles khác caching data values; `setSyncOnRelink` khác đồng bộ mutable business state; Dynalink không vượt Java access controls.

### Tài liệu chính thức Java SE 17

- [`jdk.dynalink` module overview — dynamic operations, language-specific linkers và JavaBeans interoperability](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html)
- [`GuardingDynamicLinker` — hợp đồng `getGuardedInvocation` và guard semantics](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardingDynamicLinker.html)
- [`LinkRequest` — descriptor, receiver, arguments, unstable hint và replaceArguments](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/LinkRequest.html)
- [`LinkerServices` — asTypeLosslessReturn, asType, canConvert, getTypeConverter và composition](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/LinkerServices.html)
- [`GuardedInvocation` — invocation, guard, switch points và exception-based invalidation](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardedInvocation.html)
- [`DynamicLinkerFactory` — priority/fallback linkers, syncOnRelink và unstable threshold](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html)
- [`DynamicLinker` — linking và `RelinkableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html)
- [`SimpleRelinkableCallSite` và `ChainedCallSite` — cache strategies](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html)