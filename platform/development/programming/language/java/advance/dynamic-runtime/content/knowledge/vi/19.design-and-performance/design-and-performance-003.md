# 19.3 Thiết kế bộ phân phối động với chữ ký, chuyển đổi kiểu và lỗi có quy tắc

**Module:** Java Advance - dynamic-runtime  
**Chủ đề cha:** 19. Thiết kế và hiệu năng  
**Ngôn ngữ:** Java 17+  
**API chính:** `MethodType`, `MethodHandle`, `MethodHandles.Lookup`, `MethodHandle.asType`, `asSpreader`, `invokeExact`; chính sách dispatch và xử lý lỗi ở tầng ứng dụng.

## Mục tiêu học tập

Một **bộ phân phối động** (*dynamic dispatcher*) nhận một yêu cầu ở runtime, tìm đúng tác vụ được đăng ký, kiểm tra chữ ký, chuẩn hóa đối số theo chính sách, gọi implementation rồi trả giá trị hoặc một lỗi có thể dự đoán được. Nó có thể đứng phía sau hệ thống plugin, workflow engine, rule engine, RPC adapter hoặc API xử lý thao tác động.

Thách thức không nằm ở việc gọi một method bất kỳ bằng Reflection. Thách thức là xây **một hợp đồng ổn định và có kiểm soát** giữa dữ liệu động và phương thức Java có kiểu: phân biệt overload, tránh chuyển đổi ngầm nguy hiểm, định nghĩa thứ tự kiểm tra lỗi, bảo toàn nguyên nhân thất bại và không mở rộng quyền thực thi vô tình.

Sau bài này, bạn có thể:

1. Thiết kế registry dùng **`(operation, MethodType)`** làm khóa để phân phối overload tường minh, thay vì chọn method bằng thứ tự duyệt ngẫu nhiên.
2. Phân biệt **chữ ký được công bố**, **kiểu runtime của giá trị Java** và **adapter MethodHandle**.
3. Tách hai chính sách chuyển đổi: **`STRICT`** (tham số primitive chỉ nhận đúng wrapper) và **`WIDEN_INT_TO_LONG`** (cho phép đúng một phép mở rộng có chủ đích).
4. Đặt quy tắc lỗi rõ ràng cho thao tác không tồn tại, chữ ký không được hỗ trợ, sai arity, sai kiểu, và exception của target.
5. Xây registry bất biến, tạo MethodHandle adapter một lần, dùng `invokeExact` tại ranh giới đã kiểm tra.
6. Phân biệt `invokeExact`, `invoke`, `asType`, `asSpreader` và `invokeWithArguments`; biết vì sao có thể link/call ở tầng JVM nhưng vẫn không phù hợp chính sách nghiệp vụ.
7. Biên dịch/chạy hai chương trình Java 17 minh họa dispatch thực tế và giới hạn chuyển đổi kiểu.
8. Đánh giá trade-off về hiệu năng, đồng thời, class loader, access control, input validation và observability.

## 1. Bộ phân phối động là một ranh giới có hợp đồng

Hãy bắt đầu từ các yêu cầu bên ngoài:

~~~text
"format", "(String)String", ["Java"]
"format", "(String,int)String", ["ha", 3]
"sum",    "(long,long)long", [2, 5]
~~~

Đây là **dữ liệu minh họa**, chưa phải định dạng JSON hay cú pháp Java hoàn chỉnh. Hai tác vụ `format` có cùng tên nhưng chữ ký khác nhau, nên là **hai route riêng biệt**. Tác vụ `sum` yêu cầu hai `long`, trong khi một nguồn bên ngoài có thể cung cấp số như `Integer`, `Long`, `BigDecimal` hoặc chuỗi `"2"`. Dispatcher không nên âm thầm đoán chuyển đổi.

Pipeline đề xuất:

~~~text
Dữ liệu yêu cầu
      |
      v
[1] Validate request shape
      |
      v
[2] Lookup chính xác (operation, MethodType)
      |
      v
[3] Validate số lượng argument (arity)
      |
      v
[4] Validate/normalize từng runtime value theo Policy
      |
      v
[5] Invoke target qua MethodHandle adapter đã chuẩn bị
      |
      +-- thành công -> Object/boxed primitive/null cho void
      |
      +-- lỗi target -> mã TARGET_FAILURE + nguyên nhân gốc
~~~

Mỗi pha có một **trách nhiệm** và **loại lỗi** riêng. Không dùng một khối `catch(Exception e)` bên ngoài để biến tất cả thành câu “operation failed” rồi mất dấu lỗi chữ ký, lỗi data và lỗi target.

### 1.1. Chữ ký không chỉ là tên method

`java.lang.invoke.MethodType` mô tả kiểu tham số **theo thứ tự** và kiểu trả về. Đoạn:

~~~java
MethodType oneString =
        MethodType.methodType(String.class, String.class);
MethodType stringInt =
        MethodType.methodType(String.class, String.class, int.class);
MethodType twoLongs =
        MethodType.methodType(long.class, long.class, long.class);
~~~

là snippet trong một method có import `java.lang.invoke.MethodType`. Các descriptor tương ứng:

~~~text
(String)String
(String,int)String
(long,long)long
~~~

**Tham số đầu** của `MethodType.methodType` là **return type**; các tham số sau là **parameter types**. `String.class` khác `Object.class`, `long.class` khác `Long.class`, và `(String)String` khác `(String)Object` dù giá trị trả về runtime có thể là String ở cả hai trường hợp.

Dùng `MethodType.equals` để so chữ ký: cùng return type và từng parameter type theo thứ tự. Không chọn overload chỉ vì `getName()` giống nhau hoặc vì số đối số trùng.

### 1.2. Runtime argument không phải MethodType

Giả sử signature yêu cầu `(long,long)long`, nhưng nguồn nhận dữ liệu dạng:

~~~java
Object[] values = {Integer.valueOf(2), Long.valueOf(5)};
~~~

Đây là Java code hợp lệ trong method. Việc `values[0] instanceof Integer` không biến signature được đăng ký thành `(Integer,Long)long`. Phải phân biệt:

- **Declared target signature:** `MethodHandle.type()`.
- **Selected route signature:** `MethodType` đã được đăng ký, phải trùng declared target signature.
- **Runtime values:** những object thực có trong `Object[]`.
- **Conversion policy:** chuẩn hóa runtime values sang kiểu có thể đưa vào target một cách đã được chấp thuận.

Một dispatcher tốt **không để runtime value ngẫu nhiên thay đổi contract của route**. Nếu muốn phân giải overload theo runtime types, phải công bố một thuật toán lựa chọn rõ ràng, có quy tắc ambiguous cases. Bài này chọn thiết kế an toàn và dễ test hơn: **caller phải chọn descriptor chính xác; conversion không tham gia tự chọn overload**.

## 2. Phân phối overload theo khóa tường minh

### 2.1. Registry bất biến

Một route có danh tính:

~~~java
record Key(String operation, MethodType signature) { }
~~~

Đây là một `record` Java 17, không phải chương trình độc lập. Khi tạo Map:

~~~text
Key("format", (String)String)       -> MethodHandle format(String)
Key("format", (String,int)String)   -> MethodHandle format(String,int)
Key("sum",    (long,long)long)      -> MethodHandle sum(long,long)
~~~

**Cùng operation name nhưng signature khác** là những khóa khác nhau. Duplicate chính xác cùng `Key` phải bị từ chối ngay khi đăng ký — không im lặng ghi đè implementation đã cài.

Kiến trúc có hai pha:

1. **Bootstrap/registration:** dùng `MethodHandles.Lookup.findStatic`, `findVirtual`, hoặc factory có quyền hợp lệ để lấy các handle; kiểm tra `handle.type().equals(key.signature())`; tạo adapter; đóng băng registry.
2. **Request-time dispatch:** chỉ lookup một route đã duyệt, validate runtime args, rồi invoke.

Khi không cập nhật registry giữa chừng, `Map.copyOf` ngăn caller tùy tiện thêm route qua reference Map cũ. **Bất biến Map không làm target methods tự động thread-safe** hoặc loại bỏ state bên trong objects mà handle tham chiếu.

### 2.2. Vì sao không dùng `Map<String, Method>` một cách ngây thơ?

Một map chỉ keyed theo tên `format` sẽ ghi đè một trong hai overload, hoặc bắt bạn tự đoán method dựa trên `Object[]`. Đoán bằng “method đầu tiên có thể ép kiểu được” là một anti-pattern:

- Thứ tự `Class.getDeclaredMethods()` không phải precedence rule nghiệp vụ.
- `Integer` có thể match `int`, `long` hay `Number` nếu chọn conversions mở rộng; kết quả dễ phụ thuộc thứ tự duyệt.
- `null` có thể match nhiều reference types nhưng không chọn được kiểu cụ thể.
- Hai method khác nhau về **return type** không thể phân biệt an toàn chỉ từ số arguments.
- Cùng tên method trong hai modules/class loaders có thể cần định danh namespace/version bổ sung.

Nếu hệ thống phải tự chọn overload, nên có **một thuật toán resolution được đặc tả và thử nghiệm** (exact match trước, whitelist widening, ambiguous → mã lỗi riêng), hoặc bỏ overload ở ranh giới external API bằng cách cung cấp tên operation khác. Trong demo, chúng ta **không** tự chọn overload.

### 2.3. Type identity và class loaders

`MethodType` chứa những `Class<?>` thực tế. Nếu hai plugin loaders định nghĩa cùng tên `com.example.Request`, hai `Class<?>` đó không phải cùng kiểu. Không có đảm bảo rằng hai `MethodType` có tên hiển thị giống nhau sẽ bằng nhau khi các parameter classes thuộc những defining loaders khác nhau.

Khi thiết kế plugin dispatcher:

- Đặt SPI contract trong module/loader được chia sẻ đúng **một bản định nghĩa**.
- Chỉ register implementation khi `Lookup` có quyền thực tế; `IllegalAccessException` ở registration không phải lỗi request-time conversion.
- Không chuẩn hóa signature bằng cách so string của `Class.getName()` rồi bỏ qua loader identity.

## 3. Chính sách chuyển đổi kiểu: tường minh, tối thiểu và kiểm chứng được

Bộ phân phối thường nhận `Object[]`. Với Java primitive parameters, object ở boundary phải được unbox. Nhưng việc JVM **có khả năng** thích nghi một lời gọi MethodHandle không có nghĩa hệ thống nên cho phép mọi chuyển đổi.

### 3.1. Chính sách STRICT

Ở `STRICT`:

- Primitive `int` → chỉ nhận `Integer`, `long` → chỉ nhận `Long`, `boolean` → chỉ nhận `Boolean`, v.v.
- Reference type `String` → nhận object `String` hoặc subtype hợp lệ; `Number` → có thể nhận `Integer`/`Long` vì chúng là subclasses của Number.
- Reference parameter có thể nhận `null` nếu contract cho phép; primitive parameter **không** nhận null.
- Không parse chuỗi `"123"` thành số.
- Không nhận `Integer` để đi vào parameter primitive `long`.
- Không thu hẹp `Long` thành `int`, không tự chuyển object arbitrary thành String qua `toString()`.

Bảng kiểm tra:

| Target parameter | Runtime value | STRICT |
| --- | --- | --- |
| `long` | `Long.valueOf(2)` | Cho phép |
| `long` | `Integer.valueOf(2)` | Từ chối |
| `int` | `Integer.valueOf(2)` | Cho phép |
| `int` | `Long.valueOf(2)` | Từ chối |
| `String` | `"Java"` | Cho phép |
| `String` | `Integer.valueOf(2)` | Từ chối |
| `Number` | `Integer.valueOf(2)` | Cho phép theo assignability |
| `long` | `null` | Từ chối |
| `String` | `null` | Cho phép theo ví dụ API này; domain có thể siết thêm |

**Lưu ý:** `STRICT` ở đây là **chính sách được chúng ta định nghĩa**, không phải hằng số sẵn của Java `MethodHandles`. Nó đảm bảo input object khớp wrapper hoặc reference assignability; bản thân target có thể áp dụng validation nghiệp vụ nghiêm hơn.

### 3.2. Chính sách WIDEN_INT_TO_LONG

Để thể hiện chuyển đổi có chủ đích, chúng ta chỉ mở rộng:

~~~text
target param type = primitive long
runtime value     = java.lang.Integer
Policy            = WIDEN_INT_TO_LONG
conversion        = Long.valueOf(integer.longValue())
~~~

Những phép khác vẫn bị từ chối. Lý do chọn `Integer → long`: đây là **widening primitive conversion** không mất giá trị của 32-bit signed int. Nhưng vẫn phải convert **trước khi invoke**, sau đó adapter chỉ unbox `Long`.

Chính sách này **không** cho phép `String "2" → long`, `Long → int` hay `Double → long`. Các phép đó có thể yêu cầu parse, làm tròn, kiểm tra overflow hoặc phụ thuộc locale, không nên “tiện tay” cho phép bởi một mode mang tên “coerce”.

Nếu ứng dụng có thêm quy tắc chuyển đổi, hãy thiết kế một **bảng policy có chủ ý**:

| Chuyển đổi đề nghị | Mức độ rủi ro | Gợi ý |
| --- | --- | --- |
| `byte → short/int/long`, `int → long` | Widening nguyên chính xác | Có thể whitelist nếu contract cho phép |
| `long → double` | Có thể mất precision với số lớn | Không áp dụng mặc định; cần rule rõ |
| `double → int` | Narrowing, cắt phần thập phân/giới hạn | Cần kiểm tra range và semantics |
| `String → Integer/Long` | Parse có thể thất bại, chịu format/locale | Chỉ parse ở tầng DTO/schema riêng |
| `Number → String` | Cách format và locale không thống nhất | Chọn codec chuẩn hóa và versioning |
| `Object → domain DTO` | Reflection/mapper có side effects và lỗ hổng | Validate schema/whitelist fields |
| `null → primitive` | Không có giá trị hợp lệ | Từ chối |
| `String → enum` | Cần bảng tên hợp lệ và chính sách case | Chọn validator tường minh |

### 3.3. Trả về có kiểu cũng là một hợp đồng

Return type nằm trong `MethodType`. Một dispatcher có thể chọn Java API:

~~~java
Object call(String operation, MethodType signature,
            Policy policy, Object... args)
~~~

Khi gọi qua một adapter generic `(Object[])Object`:

- Target trả `long` được boxing thành `Long` tại boundary.
- Target trả `String` cho ra `String`.
- Target trả `void` có thể được adapter quy đổi thành **`null`**.
- Một target ném lỗi không trả kết quả bình thường; nó đi theo chính sách error handling.

**Không đồng nhất `null` trả về với void** trong public API nếu consumer cần phân biệt. Trong hệ thống thật, có thể dùng result envelope gồm `VOID`/`NULL`/`VALUE` hoặc contract result kiểu rõ ràng, ví dụ `record Success(Object value, boolean isVoid)`. Demo tối giản dùng `Object` và có ghi rõ `void → null`.

Nếu caller cần trả kiểu `T`, nên dùng typed facade dựa trên **route signature đã đăng ký**, xác minh return type và cast có kiểm soát. Đừng để client tự chọn một return type khác rồi ép cast từ object mà không kiểm tra descriptor.

## 4. Lỗi “có quy tắc” là kết quả của phân tầng trách nhiệm

Thay vì dùng exceptions không ổn định làm thông điệp API, có thể định nghĩa mã lỗi cố định:

| Mã | Pha | Điều kiện |
| --- | --- | --- |
| `INVALID_REQUEST` | Validate request shape | Tên trống/null, signature null, policy null, varargs array null |
| `UNKNOWN_OPERATION` | Lookup name | Không có operation name nào được đăng ký |
| `SIGNATURE_MISMATCH` | Lookup exact key | Operation có tồn tại nhưng không có `MethodType` được yêu cầu |
| `ARITY_MISMATCH` | Validate argument count | Số runtime arguments khác `signature.parameterCount()` |
| `ARGUMENT_TYPE` | Validate/normalize | Runtime value không phù hợp declared param hoặc policy; primitive null |
| `TARGET_FAILURE` | Invoke target | Implementation ném exception hoặc một lỗi nonfatal được policy bọc |

**Thứ tự kiểm tra trong demo là một phần contract:** `INVALID_REQUEST → UNKNOWN_OPERATION → SIGNATURE_MISMATCH → ARITY_MISMATCH → ARGUMENT_TYPE → invoke`. Nếu request vừa chọn sai chữ ký vừa truyền sai type, demo báo **`SIGNATURE_MISMATCH` trước**, vì chưa có route để xác định đúng parameter types.

Nếu ứng dụng cần kiểm tra arity trước signature resolution, hãy quyết định riêng trong tài liệu API và test thứ tự mới. Đừng để thứ tự bắt exception thay đổi ngẫu nhiên giữa các phiên bản.

### 4.1. Tách lỗi người gọi khỏi lỗi hệ thống

- **Request lỗi**: unknown operation, signature mismatch, bad argument; consumer có thể sửa input mà không cần thay source code của target.
- **Configuration lỗi**: đăng ký cùng route hai lần, target.type không bằng route key, lookup thiếu quyền; thường phát hiện lúc startup, không chờ request mới xử lý.
- **Target lỗi**: business logic ném `IllegalStateException`, `ArithmeticException` hoặc checked exception; cần giữ `getCause()` để debug đúng target.
- **JVM/linkage/fatal lỗi**: `VirtualMachineError`, `ThreadDeath`, `LinkageError`; trong demo **không cố bọc** ba nhóm này thành error code thông thường, để không che các tình trạng không thể tiếp tục an toàn.

Đây là ví dụ một chính sách thực tế, **không phải phân loại duy nhất**. Production có thể cần một `Result<T,Error>` hoặc mapping HTTP/RPC rõ ràng, và cách ứng xử riêng với interruption, cancellation, timeout, retry và idempotency. Không retry mù một target có side effects khi exception đã xảy ra **sau** phần việc thành công.

### 4.2. Bảo toàn root cause

Khi target thật ném lỗi:

~~~java
throw new DispatchFailure(
        Code.TARGET_FAILURE, "target failed: " + operation, failure);
~~~

Lưu `failure` làm cause giúp operator thấy stack trace và chain nguyên nhân, trong khi caller có mã ổn định để quyết định UI/retry/alert. Không in hết message/cause nhạy cảm vào response công khai: log và response envelope có mức chi tiết khác nhau.

Một lưu ý: ví dụ dùng `catch(Throwable)` làm đường bắt cho exceptions của MethodHandle, nhưng nó **tách riêng ba nhóm lỗi JVM đặc biệt trước**. Trong hệ thống thật, cần cân nhắc ném tiếp các `Error` khác theo chính sách fatal/bug cụ thể; không mặc định mọi `Error` đều được phục hồi an toàn.

## 5. Thiết kế adapter: đăng ký một lần, dùng nhiều lần

Giữ target có type chính xác ở registry, nhưng cung cấp một đường gọi đồng nhất dùng `Object[]`:

~~~text
target:       (String,int)String
      |
      | asType((Object,Object)Object)
      v
generic:      (Object,Object)Object
      |
      | asSpreader(Object[].class, 2)
      v
invoker:      (Object[])Object
~~~

Tại registration:

~~~java
MethodHandle invoker = target
        .asType(MethodType.genericMethodType(
                target.type().parameterCount()))
        .asSpreader(Object[].class, target.type().parameterCount());
~~~

Snippet này giả định `target` là một MethodHandle đã tìm được bằng `Lookup`.

**Vì sao thiết kế như vậy?**

- `asType` tạo handle nhìn ra ngoài nhận/return `Object`, chèn checkcast, unboxing, boxing hoặc giá trị default thích hợp cho return void.
- `asSpreader` chuyển một `Object[]` thành các arguments của handle sau adaptation.
- Mỗi route có invoker kiểu **`(Object[])Object`**, nên dispatcher có thể gọi:

~~~java
return (Object) route.invoker().invokeExact(prepared);
~~~

- `invokeExact` đòi descriptor call site đúng **chính xác**; biểu thức trên có argument compile-time kiểu `Object[]` và return kiểu `Object`.
- Việc chuẩn hóa `prepared` được thực hiện **trước** lời gọi handle, theo policy của app. Adapter generic vẫn có khả năng cast/unbox nội bộ, nhưng không phải nguồn quyết định “Integer có được widen sang long hay không”.

**Không tối ưu quá sớm:** `asType`/`asSpreader` có thể hỗ trợ đường gọi linh hoạt nhưng vẫn có chi phí, boxing và kiểm tra runtime. Demo tạo adapter **một lần trong constructor** thay vì mỗi request. Với request nóng, cache/phân lớp typed path có thể phù hợp hơn; cần đo thực tế bằng JMH.

### 5.1. `invokeWithArguments` có thể tiện nhưng không thay thế validation

`MethodHandle.invokeWithArguments(Object...)` rất hữu ích cho dynamic code nhưng dùng conversion semantics linh hoạt và varargs/generic call path. Nó không phải một API “business conversion policy” và thường có overhead khác với typed `invokeExact`. Nếu gọi thẳng với dữ liệu chưa kiểm tra, những cast/unbox/numeric adaptations sẽ phát sinh theo quy tắc JVM, không chắc trùng quy tắc của application.

Phương án đã chọn cố định một **single generic invoker shape**, validate trước rồi mới gọi. Khi cần đường gọi typed cao hiệu năng, bạn có thể giữ thêm direct handle cùng signature để gọi bằng `invokeExact` từ call site có descriptor compile-time phù hợp.

### 5.2. `asType` có thể thích nghi type nhưng không thay đổi route key

Một adapter `asType` trả **MethodHandle mới**. Nó không làm `MethodType` của direct target ban đầu thay đổi. Nếu target type `(long)long`, bạn có thể tạo adapter `(int)long` cho một call site cụ thể, nhưng trong registry:

~~~text
registered route signature = (long)long
runtime integer conversion = Policy.WIDEN_INT_TO_LONG
normalized object          = Long
generic invocation         = (Object[])Object
~~~

Ở đây **route vẫn là `(long)long`**. Không được vô tình đăng ký nó như `(int)long` chỉ vì policy cho phép Integer input. Conversion là thao tác **sau khi chọn route**.

## 6. Demo Java 17 đầy đủ: bộ phân phối động có chữ ký và mã lỗi

Chương trình dưới đây triển khai:

- Route key là `record Key(String operation, MethodType signature)`.
- Registry có hai overload của `format` cùng ba operation khác.
- Mỗi registered MethodHandle được kiểm tra type rồi chuyển thành generic invoker `(Object[])Object`.
- `STRICT` kiểm tra wrapper của primitive hoặc assignability của reference.
- `WIDEN_INT_TO_LONG` chỉ cho phép đúng chuyển đổi `Integer → primitive long`.
- Đường lỗi có mã cố định; lỗi target được giữ dưới `DispatchFailure.getCause()`.
- `void` được biểu diễn thành `null` qua generic return adapter.
- Registry immutable sau bootstrap; runtime không tự sửa route list.

**File độc lập:** `TypedDispatcherDemo.java`

~~~java
import java.lang.invoke.*;
import java.util.*;

public final class TypedDispatcherDemo {
    enum Policy { STRICT, WIDEN_INT_TO_LONG }
    enum Code {
        INVALID_REQUEST, UNKNOWN_OPERATION, SIGNATURE_MISMATCH,
        ARITY_MISMATCH, ARGUMENT_TYPE, TARGET_FAILURE
    }

    static final class DispatchFailure extends RuntimeException {
        private final Code code;
        DispatchFailure(Code code, String message) {
            super(message);
            this.code = code;
        }
        DispatchFailure(Code code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }
        Code code() { return code; }
    }

    record Key(String operation, MethodType signature) { }
    record Route(MethodType signature, MethodHandle invoker) { }

    static final class Dispatcher {
        private final Map<Key, Route> routes;
        private final Set<String> names;

        Dispatcher(Map<Key, MethodHandle> targets) {
            Map<Key, Route> built = new HashMap<>();
            for (Map.Entry<Key, MethodHandle> e : targets.entrySet()) {
                Key key = e.getKey();
                MethodHandle target = e.getValue();
                if (target == null || !target.type().equals(key.signature())) {
                    throw new IllegalArgumentException("invalid route " + key);
                }
                MethodHandle invoker = target
                        .asType(MethodType.genericMethodType(
                                key.signature().parameterCount()))
                        .asSpreader(Object[].class,
                                key.signature().parameterCount());
                built.put(key, new Route(key.signature(), invoker));
            }
            routes = Map.copyOf(built);
            Set<String> declared = new HashSet<>();
            for (Key key : routes.keySet()) {
                declared.add(key.operation());
            }
            names = Set.copyOf(declared);
        }

        Object call(String operation, MethodType signature,
                    Policy policy, Object... args) {
            if (operation == null || operation.isBlank() ||
                    signature == null || policy == null || args == null) {
                throw new DispatchFailure(Code.INVALID_REQUEST, "invalid call");
            }
            if (!names.contains(operation)) {
                throw new DispatchFailure(Code.UNKNOWN_OPERATION,
                        "unknown operation: " + operation);
            }
            Route route = routes.get(new Key(operation, signature));
            if (route == null) {
                throw new DispatchFailure(Code.SIGNATURE_MISMATCH,
                        "unsupported signature: " + signature);
            }
            if (args.length != signature.parameterCount()) {
                throw new DispatchFailure(Code.ARITY_MISMATCH, "wrong arity");
            }
            Object[] prepared = args.clone();
            for (int i = 0; i < prepared.length; i++) {
                prepared[i] = normalize(signature.parameterType(i),
                        prepared[i], policy, i);
            }
            try {
                return (Object) route.invoker().invokeExact(prepared);
            } catch (VirtualMachineError | ThreadDeath | LinkageError fatal) {
                throw fatal;
            } catch (Throwable failure) {
                throw new DispatchFailure(Code.TARGET_FAILURE,
                        "target failed: " + operation, failure);
            }
        }

        private static Object normalize(Class<?> expected, Object value,
                                        Policy policy, int index) {
            if (value == null) {
                if (expected.isPrimitive()) {
                    throw new DispatchFailure(Code.ARGUMENT_TYPE,
                            "null for primitive argument " + index);
                }
                return null;
            }
            Class<?> boxed = wrapper(expected);
            if (boxed.isInstance(value)) {
                return value;
            }
            if (policy == Policy.WIDEN_INT_TO_LONG
                    && expected == long.class
                    && value instanceof Integer n) {
                return Long.valueOf(n.longValue());
            }
            throw new DispatchFailure(Code.ARGUMENT_TYPE,
                    "argument " + index + ": expected " + boxed.getSimpleName());
        }

        private static Class<?> wrapper(Class<?> type) {
            if (type == boolean.class) return Boolean.class;
            if (type == byte.class) return Byte.class;
            if (type == short.class) return Short.class;
            if (type == char.class) return Character.class;
            if (type == int.class) return Integer.class;
            if (type == long.class) return Long.class;
            if (type == float.class) return Float.class;
            if (type == double.class) return Double.class;
            return type;
        }
    }

    private static void add(Map<Key, MethodHandle> routes,
                            String name, MethodHandle target) {
        if (routes.putIfAbsent(new Key(name, target.type()), target) != null) {
            throw new IllegalArgumentException("duplicate route");
        }
    }

    public static String format(String value) {
        return "tag:" + value;
    }

    public static String format(String value, int times) {
        return value.repeat(times);
    }

    public static long sum(long left, long right) {
        return Math.addExact(left, right);
    }

    public static void audit(String value) {
        System.out.println("audit:" + value);
    }

    public static String fail(String value) {
        throw new IllegalStateException("boom:" + value);
    }

    private static void expect(String label, Code code, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=unexpected-success");
        } catch (DispatchFailure error) {
            if (error.code() != code) {
                throw error;
            }
            System.out.println(label + "=" + error.code());
            if (code == Code.TARGET_FAILURE) {
                System.out.println(label + ".cause=" +
                        error.getCause().getClass().getSimpleName());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType oneString = MethodType.methodType(String.class, String.class);
        MethodType stringInt =
                MethodType.methodType(String.class, String.class, int.class);
        MethodType twoLongs =
                MethodType.methodType(long.class, long.class, long.class);
        MethodType voidString =
                MethodType.methodType(void.class, String.class);

        Map<Key, MethodHandle> targets = new HashMap<>();
        add(targets, "format", lookup.findStatic(
                TypedDispatcherDemo.class, "format", oneString));
        add(targets, "format", lookup.findStatic(
                TypedDispatcherDemo.class, "format", stringInt));
        add(targets, "sum", lookup.findStatic(
                TypedDispatcherDemo.class, "sum", twoLongs));
        add(targets, "audit", lookup.findStatic(
                TypedDispatcherDemo.class, "audit", voidString));
        add(targets, "fail", lookup.findStatic(
                TypedDispatcherDemo.class, "fail", oneString));

        Dispatcher dispatcher = new Dispatcher(targets);
        System.out.println("routes=" + targets.size());
        System.out.println("format.one=" +
                dispatcher.call("format", oneString, Policy.STRICT, "Java"));
        System.out.println("format.two=" +
                dispatcher.call("format", stringInt, Policy.STRICT, "ha", 3));
        System.out.println("sum.strict=" +
                dispatcher.call("sum", twoLongs, Policy.STRICT, 2L, 5L));
        System.out.println("sum.widen=" +
                dispatcher.call("sum", twoLongs, Policy.WIDEN_INT_TO_LONG, 2, 5));
        Object ignored = dispatcher.call("audit", voidString,
                Policy.STRICT, "saved");
        System.out.println("audit.return=" + ignored);

        expect("unknown", Code.UNKNOWN_OPERATION,
                () -> dispatcher.call("missing", oneString, Policy.STRICT, "x"));
        expect("signature", Code.SIGNATURE_MISMATCH,
                () -> dispatcher.call("format",
                        MethodType.methodType(Object.class, String.class),
                        Policy.STRICT, "x"));
        expect("arity", Code.ARITY_MISMATCH,
                () -> dispatcher.call("format", stringInt, Policy.STRICT, "ha"));
        expect("strictInteger", Code.ARGUMENT_TYPE,
                () -> dispatcher.call("sum", twoLongs, Policy.STRICT, 2, 5));
        expect("nullPrimitive", Code.ARGUMENT_TYPE,
                () -> dispatcher.call("sum", twoLongs, Policy.STRICT,
                        new Object[]{null, 2L}));
        expect("stringToNumber", Code.ARGUMENT_TYPE,
                () -> dispatcher.call("sum", twoLongs,
                        Policy.WIDEN_INT_TO_LONG, "2", 5L));
        expect("targetFailure", Code.TARGET_FAILURE,
                () -> dispatcher.call("fail", oneString, Policy.STRICT, "x"));
        expect("overflow", Code.TARGET_FAILURE,
                () -> dispatcher.call("sum", twoLongs, Policy.STRICT,
                        Long.MAX_VALUE, 1L));
    }
}
~~~

### 6.1. Cách biên dịch và chạy

Lưu file `TypedDispatcherDemo.java` ở một thư mục riêng. Dùng JDK 17 trở lên:

~~~bash
javac --release 17 -d out TypedDispatcherDemo.java
java -cp out TypedDispatcherDemo
~~~

Ví dụ dùng `record`, pattern matching `instanceof`, `String.repeat` và MethodHandle API có sẵn trong Java 17. Lệnh `javac -d out` có thể tạo thư mục `out` khi chưa có.

### 6.2. Stdout đã kiểm thử chính xác

~~~text
routes=5
format.one=tag:Java
format.two=hahaha
sum.strict=7
sum.widen=7
audit:saved
audit.return=null
unknown=UNKNOWN_OPERATION
signature=SIGNATURE_MISMATCH
arity=ARITY_MISMATCH
strictInteger=ARGUMENT_TYPE
nullPrimitive=ARGUMENT_TYPE
stringToNumber=ARGUMENT_TYPE
targetFailure=TARGET_FAILURE
targetFailure.cause=IllegalStateException
overflow=TARGET_FAILURE
overflow.cause=ArithmeticException
~~~

Mã Java này đã được **biên dịch bằng `javac --release 17` và chạy thực tế**; thứ tự và nội dung các dòng trên khớp kết quả.

### 6.3. Đọc các kết quả thành công

**`routes=5`**: registry có **năm** `Key` chính xác. `format` có hai overload, nên số operation name khác số route. Không ghi đè một implementation bằng implementation khác.

**`format.one=tag:Java`**: route `(String)String` gọi `format(String)`. `format.two=hahaha`: route `(String,int)String` gọi `format(String,int)`. Caller **chỉ rõ signature trước**; dispatcher không dựa vào kiểu runtime String để tìm overload.

**`sum.strict=7`**: hai đối số là `Long` nên khớp `long,long` sau unboxing. **`sum.widen=7`**: hai đối số ban đầu là `Integer` nhưng policy `WIDEN_INT_TO_LONG` đổi chúng thành `Long` trước khi vào generic invoker.

**`audit:saved`**: method trả `void` thực sự được gọi. **`audit.return=null`**: generic adapter có Object return, nên biểu diễn void result bằng null. Đó không phải null do target `audit` tự return.

### 6.4. Đọc các mã lỗi theo đúng pha

**`unknown=UNKNOWN_OPERATION`**: không có tên `missing` trong registry, nên không cần xem descriptor hoặc runtime arguments.

**`signature=SIGNATURE_MISMATCH`**: có operation `format`, nhưng route `(String)Object` không tồn tại. Việc String có thể gán cho Object không làm hai `MethodType` bằng nhau.

**`arity=ARITY_MISMATCH`**: caller chọn route `format(String,int)`, nhưng chỉ truyền một argument; check count chạy trước type normalization.

**`strictInteger=ARGUMENT_TYPE`**: `sum` yêu cầu `long,long`; hai `Integer` không hợp lệ dưới `STRICT` mặc dù JVM có một số phép numeric adaptation. **`nullPrimitive=ARGUMENT_TYPE`**: null không thể unbox thành `long`.

**`stringToNumber=ARGUMENT_TYPE`**: `WIDEN_INT_TO_LONG` không bao gồm parse String. Giá trị `"2"` không được silently parse.

**`targetFailure=TARGET_FAILURE`** và `targetFailure.cause=IllegalStateException`: request đúng chữ ký, đúng runtime args, nhưng `fail(String)` cố tình ném lỗi. **`overflow.cause=ArithmeticException`**: `Math.addExact` kiểm tra tràn số; dispatcher không biến exception target thành lỗi kiểu dữ liệu. Giữ `getCause()` giúp phân biệt logic nghiệp vụ và lỗi của boundary.

### 6.5. Những gì demo cố ý không làm

Đây là **kiến trúc minh họa**, không phải một RPC framework production:

- API trả `Object`, chưa có envelope phân biệt void và nullable return.
- Không có schema validation chi tiết như string length, allowed format, domain constraints, tiền tệ, timezone, locale.
- Không có authorization dựa trên principal/tenant. Việc route tồn tại **không đồng nghĩa** người gọi được phép chạy.
- Không cung cấp hot reload/đăng ký route giữa lúc request đang chạy.
- Không triển khai retry/timeout/circuit breaker/tracing.
- Không tự sinh overloaded resolution từ runtime values. Caller phải biết `MethodType` đã công bố.
- Không quản lý thread interruption/cancellation riêng; production cần cơ chế cụ thể nếu targets có blocking operations.
- Không chứng minh throughput/latency. Chỉ kiểm thử tính đúng về loại lỗi và kết quả.

## 7. Ví dụ độc lập: `invokeExact`, `invoke` và `asType` không đồng nghĩa chính sách ứng dụng

Một method có signature `(long)long` có thể được gọi theo nhiều cách với những rule JVM khác nhau. Nhưng bộ phân phối mẫu vẫn chọn **`STRICT`** theo yêu cầu của API.

**File:** `ConversionBoundaryDemo.java`

~~~java
import java.lang.invoke.*;

public final class ConversionBoundaryDemo {
    public static long twice(long value) {
        return Math.multiplyExact(value, 2L);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle exact = MethodHandles.lookup().findStatic(
                ConversionBoundaryDemo.class, "twice",
                MethodType.methodType(long.class, long.class));
        System.out.println("target.type=" + exact.type());
        System.out.println("exact=" + (long) exact.invokeExact(7L));

        try {
            long ignored = (long) exact.invokeExact(7);
            System.out.println("badExact=" + ignored);
        } catch (WrongMethodTypeException expected) {
            System.out.println("badExact=WrongMethodTypeException");
        }

        System.out.println("invoke.widen=" + (long) exact.invoke(7));
        MethodHandle adapter = exact.asType(
                MethodType.methodType(long.class, int.class));
        System.out.println("adapter.type=" + adapter.type());
        System.out.println("adapter.exact=" + (long) adapter.invokeExact(7));
        try {
            exact.asType(MethodType.methodType(long.class, String.class));
            System.out.println("badAdapter=unexpected");
        } catch (WrongMethodTypeException expected) {
            System.out.println("badAdapter=WrongMethodTypeException");
        }
    }
}
~~~

Biên dịch/chạy trong thư mục chứa file:

~~~bash
javac --release 17 -d out ConversionBoundaryDemo.java
java -cp out ConversionBoundaryDemo
~~~

Stdout **đã kiểm chứng**:

~~~text
target.type=(long)long
exact=14
badExact=WrongMethodTypeException
invoke.widen=14
adapter.type=(int)long
adapter.exact=14
badAdapter=WrongMethodTypeException
~~~

**Phân tích:**

- `exact.invokeExact(7L)` dùng descriptor `(long)long` phù hợp target; kết quả 14.
- `exact.invokeExact(7)` có argument compile-time kiểu `int`, trong khi target yêu cầu `long`; `invokeExact` **không tự widening**, gây `WrongMethodTypeException`.
- `exact.invoke(7)` cho phép adaptation từ `(int)long` sang `(long)long`, nên widening int → long hợp lệ.
- `exact.asType((int)long)` tạo **một handle khác** mà bên ngoài caller có thể `invokeExact` với int; handle gốc vẫn là `(long)long`.
- `asType((String)long)` không tìm được adapter hợp lệ để chuyển String thành primitive long, nên `WrongMethodTypeException` xuất hiện khi tạo adapter.

**Bài học:** JVM có conversion rule của riêng nó; dispatcher policy là **một quyết định về dữ liệu và hợp đồng ứng dụng**. Nên validate/normalize trước khi gọi handle. Không để mọi coercion có thể thực hiện bởi `invoke` vô tình trở thành conversion được phép trên API công khai.

### 7.1. `explicitCastArguments` không phải “asType an toàn hơn”

`MethodHandles.explicitCastArguments` có quy tắc conversion khác `asType` và có thể hỗ trợ narrowing/explicit casting tương tự cast; dùng sai có thể làm mất precision hoặc xuất hiện kết quả bất ngờ. Đừng chọn nó chỉ để “đỡ gặp WrongMethodTypeException”; nếu contract yêu cầu cấm narrowing, hãy giữ policy strict và kiểm tra range/semantic khi có conversion tường minh.

Đừng nhầm các lỗi:

| Tầng | Ví dụ | Lỗi |
| --- | --- | --- |
| Chọn route | `(String)Object` nhưng chỉ có `(String)String` | `SIGNATURE_MISMATCH` (ứng dụng) |
| Chuẩn hóa runtime value | `Integer` vào primitive `long` dưới STRICT | `ARGUMENT_TYPE` (ứng dụng) |
| Sai call-site descriptor của `invokeExact` | int argument cho handle `(long)long` | `WrongMethodTypeException` (JVM MethodHandle API) |
| Tạo adapter không tương thích | String argument muốn adapt sang primitive long | `WrongMethodTypeException` |
| Cast runtime sau adaptation | Object thực không phải subtype yêu cầu | Có thể `ClassCastException` |
| Method thực thi ném lỗi | `Math.addExact` tràn | `ArithmeticException`, do target |

Nếu dispatcher tự bắt các exception JVM mà không phân biệt bước, caller sẽ không biết nên sửa request, sửa registry hay sửa implementation.

## 8. Hiệu năng: tối ưu phần cần thiết mà không hy sinh hợp đồng

### 8.1. Startup work và request work

Trong demo:

~~~text
Startup:
  Lookup.findStatic -> MethodHandle.type validation
  -> asType -> asSpreader -> immutable Map

Mỗi request:
  Key lookup -> count check -> normalize
  -> prepared Object[] -> cached generic invoker.invokeExact
~~~

Bằng cách dựng adapter lúc startup:

- Tránh tạo `asType`/`asSpreader` mới mỗi request.
- Phát hiện target signature mismatch khi đăng ký.
- Cho runtime dễ thấy một đường gọi ổn định theo dạng `(Object[])Object`.

Tuy nhiên generic invoker dùng `Object[]`, boxed primitive và dynamic type checks. Trong hot path có volume cao, chi phí có thể không nhỏ. Đừng khẳng định mọi `MethodHandle` luôn nhanh hơn Reflection, hay JIT luôn inline mọi call dynamic.

### 8.2. Các phương án cải thiện khi đo được bottleneck

| Kỹ thuật | Lợi ích có thể có | Rủi ro/điều kiện |
| --- | --- | --- |
| Cache `MethodHandle` và adapter sau registration | Giảm tìm kiếm member/chuyển đổi lại | Cần invalidation và loader lifecycle rõ |
| Cache route lookup theo `Key` | Giảm overhead map lookup ở đường nóng | Không cache key chứa classloader cũ vô hạn |
| Typed fast path dùng `invokeExact` tại call site cố định | Có thể giảm boxing/array allocations | Cần compiler/type signature tĩnh phù hợp |
| Guarded dispatch bằng `guardWithTest` / PIC | Tối ưu nhiều kiểu input thường gặp | Guard/fallback phải giữ cùng MethodType |
| `MutableCallSite`/`VolatileCallSite` cho relink runtime | Đổi target mà giữ descriptor | Cần quản lý visibility/thread coordination |
| Generate code với JMH benchmark | Đo throughput/latency thực | Benchmark cần warmup, fork, tiêu thụ kết quả đúng |
| Tránh chuyển đổi quá rộng | Giảm lỗi và chi phí chuyển dữ liệu | Cần đặc tả policy rõ ở API boundary |

Nếu thật sự cần **auto-overload resolution**, nên cache kết quả của **thuật toán đã đặc tả** theo signature/runtime type vector, nhưng xử lý đúng `null` và class loader identity; không chỉ hash tên class.

### 8.3. Cache và lifecycle của plugin

Một registry giữ `MethodHandle` có thể giữ tham chiếu tới declaring class, receiver được bind, classloader và object graph. Với plugin hot reload:

- Không giữ static caches vô hạn theo `Class<?>` của loader cũ.
- Có cơ chế retire route, đợi/điều phối in-flight calls và dọn resources.
- Nếu dùng đổi registry theo snapshot, atomic swap của **một immutable registry** thường dễ suy luận hơn cập nhật từng entry sống.
- Không để một request đang chạy xem nửa trạng thái cũ, nửa trạng thái mới khi yêu cầu transaction-level consistency.

## 9. Bảo mật, ownership và ranh giới module

### 9.1. MethodHandle có quyền truy cập tương ứng Lookup

`Lookup.findStatic`, `findVirtual`, `findConstructor`, `findGetter`... kiểm tra quyền truy cập member khi tạo handle. Một handle đã được tạo có thể mang khả năng gọi member mà caller thông thường không được phép trực tiếp gọi theo source access. Vì vậy **registry là capability boundary**.

Không cho dữ liệu request trực tiếp chọn arbitrary class/method names rồi dùng privileged `MethodHandles.Lookup` để tạo handle. Đăng ký **allowlist operations** ở startup từ code có quyền, và kiểm tra mỗi request có được phép gọi route đã chọn hay không.

### 9.2. Contract nào được phép đi qua plugin boundary?

Nếu plugin A/B dùng hai class loaders khác nhau, cùng binary name của parameter type không bảo đảm cùng runtime Class. Dùng contract Java public ở module/loader được chia sẻ, và truyền dữ liệu qua DTO/interface đã xác định.

Đối với caller từ mạng:

- Không nhận class name/sig string từ client rồi phản chiếu thành bất kỳ `MethodType` nào trong JVM.
- Định nghĩa **API schema** độc lập; map schema đã validate sang **route key allowlisted** trong server.
- Tách xác thực identity, authorization, validation nội dung và transport codec khỏi target dispatch.
- Đặt rate limit, quotas, timeout/cancellation policy và audit cho route có side effects.

### 9.3. Null và dữ liệu sai kiểu là vấn đề domain

Java primitive không nhận null, nhưng reference `String` có thể nhận null theo Java type system. **Điều đó không có nghĩa operation `format(null)` hợp lệ về nghiệp vụ.** Trong demo, normalization có thể cho qua reference null, rồi target có thể ném `NullPointerException`. Nếu `format` yêu cầu non-null, hãy validate schema/domain **trước** khi gọi target và trả mã riêng, ví dụ `INVALID_VALUE`.

Tương tự, `int times=-1` có đúng kiểu int nhưng `String.repeat(-1)` ném `IllegalArgumentException`. Đây là **domain validation** hoặc target error, không phải `ARGUMENT_TYPE`; hãy phân biệt khi mở rộng API.

## 10. Đồng thời, consistency và lỗi khi thay route

Registry immutable giúp nhiều thread có thể **đọc bảng route** mà không phải đồng bộ việc thêm/xóa entry. Nhưng:

- Target có thể dùng static mutable fields, file, database connection hoặc receiver object không thread-safe.
- Conversion policy có thể cần cấu hình theo tenant hoặc version; không dùng biến static mutable toàn cục làm policy ẩn.
- Lúc đổi route, cần publication an toàn. Có thể tạo map mới và thay reference `volatile`/`AtomicReference`, hoặc dùng CallSite đúng semantics, thay vì sửa chung `HashMap` trong lúc request đang đọc.
- Việc một request lấy route cũ trước lúc swap là hành vi cần được cho phép hoặc chặn theo policy. Không hứa mọi in-flight call đổi sang route mới một cách tức thì.
- Retry cần phân biệt **request không hợp lệ** và **target execution failure**. Một call bị timeout không chắc target đã dừng hay chưa, nên không retry tác vụ không idempotent nếu chưa có cơ chế dedup.

### 10.1. Error envelope phục vụ API bên ngoài

Demo dùng `DispatchFailure` là unchecked exception. Với RPC/REST, có thể định nghĩa một envelope:

~~~text
{
  "ok": false,
  "code": "ARGUMENT_TYPE",
  "operation": "sum",
  "requestId": "req-42",
  "message": "argument 0 must be long-compatible under STRICT"
}
~~~

Đây là **JSON minh họa**, không phải output của Java demo. Không đưa toàn bộ stack trace, classpath hay mã bí mật từ `Throwable.getMessage()` cho client. Trong log nội bộ có thể giữ `cause` và trace identifiers.

Nếu cần theo dõi khả năng tương thích, versioning error codes quan trọng như versioning route signatures. Đừng đổi nghĩa của `SIGNATURE_MISMATCH` từ “route không tồn tại” sang “conversion thất bại” một cách âm thầm.

## 11. So sánh với các lựa chọn khác

| Cơ chế | Điều nó cung cấp | Có nên dùng cho dispatcher này? |
| --- | --- | --- |
| `java.lang.reflect.Method.invoke` | Gọi method sau lookup, một mức argument checking/conversion và wrapping | Hữu ích cho công cụ admin đơn giản; vẫn cần registry/policy/error taxonomy |
| `MethodHandle.invokeExact` | Lời gọi theo descriptor chính xác, thuận lợi cho typed hot path | Dùng sau khi xây handle phù hợp và validation |
| `MethodHandle.invoke` | Có một số adaptation như `asType` | Dùng khi conversion semantics hợp lệ theo thiết kế |
| `asType` / `asSpreader` | Xây generic typed adapter một lần | Phù hợp cho dispatcher nhận `Object[]` |
| `invokeWithArguments` | Gọi handle với số arguments động | Tiện nhưng không thay policy/schema |
| `ServiceLoader` | Khám phá providers của SPI | Có thể dùng để **đăng ký route**, không tự giải quyết invocation policy |
| `LambdaMetafactory` | Tạo function object implement functional interface từ direct impl handle theo protocol riêng | Không phải generic dispatcher cho mọi adapter handle |
| `ConstantCallSite` | Liên kết một target bất biến theo MethodType | Hữu ích nếu JVM/dynamic runtime cần call site |
| `MutableCallSite`/`VolatileCallSite` | Relink target cùng MethodType | Hữu ích cho hot-swap/inline cache khi có synchronization policy |
| `invokedynamic` | Instruction JVM liên kết qua bootstrap đến CallSite | Dành cho compiler/runtime phát sinh bytecode; không bắt buộc cho registry Java thông thường |

**Tránh biến việc dùng công cụ nâng cao thành mục tiêu tự thân.** Nếu số operation ít, Java `switch` và typed interfaces có thể dễ kiểm toán hơn, nhanh hơn về mặt phát triển và an toàn hơn. Chỉ thêm dynamic dispatch khi thực sự cần đăng ký tác vụ, runtime type routing hoặc plugin integration.

## 12. Tình huống thiết kế thực tế

### 12.1. Dynamic plugin operations

Plugin công bố operations:

~~~text
"validate" : (Document,Context)ValidationResult
"transform": (Document,Options)Document
"emit"     : (Event)void
~~~

Đây là **chữ ký minh họa**, không phải các class có sẵn trong Java SE. Host chỉ cho phép những operation IDs cố định, dùng contract classes ở shared loader, đăng ký direct MethodHandles từ provider có quyền. Một runtime request phải chọn schema version, validate payload, rồi chọn signature chính xác.

Nếu `Document` thuộc loader của plugin A mà host dùng `Document` do plugin B tự định nghĩa, cả hai có thể cùng tên nhưng **không cùng Class**; `MethodType.equals` giúp không vô tình coi chúng là một.

### 12.2. Trường hợp numeric policy cần giới hạn rõ

Một nguồn JSON decode số `5` thành Integer nhưng target chờ long. Có thể cho phép `WIDEN_INT_TO_LONG`. Tuy nhiên nguồn khác gửi `5.2` dưới dạng Double; không được chuyển sang long bằng cách cắt thập phân rồi âm thầm thực thi. Nếu nghiệp vụ thật sự có conversion, cần:

- Xác định kiểu nguồn cho phép;
- Kiểm tra range/overflow/precision;
- Xác định rounding mode (nếu dùng số thập phân);
- Ghi audit về conversion;
- Test cả giới hạn lớn/nhỏ, NaN, infinities nếu có floating-point.

Đừng hiểu nhãn “numeric widening” như một quyền chuyển mọi số sang mọi primitive.

### 12.3. Return contract khi thêm plugin version

Một route cũ `(String)String` không tự trở thành route `(String)Object` chỉ vì `String <: Object`. Nếu thay return type ở API schema:

- Giữ route cũ cho clients cũ hoặc version rõ.
- Đăng ký route mới với một MethodHandle/adapter **có type đúng**.
- Kiểm thử binary compatibility của callers, không chỉ JSON shape.
- Nếu dùng `CallSite`, **không thể đổi MethodType của cùng một CallSite bằng `setTarget`**; phải duy trì chữ ký của site.

## 13. Debug một lỗi dynamic dispatcher

### 13.1. Checklist theo thứ tự

1. **Request:** operation có trong allowlist không? route được chọn có version/descriptor nào?
2. **Registry:** `Key` có trùng exact `MethodType` không? MethodHandle được tạo từ `Lookup` nào? `handle.type()` có bằng key signature không?
3. **Arity:** `args.length` bằng parameter count chưa? Caller dùng `Object[]` hay truyền một array duy nhất vào varargs?
4. **Types:** từng expected parameter là primitive hay reference? Runtime value class là gì? `null` được phép không? Policy bật gì?
5. **Conversion:** đã normalize thành **đúng boxed type** cho primitive target chưa? Có parsing/narrowing ngầm không?
6. **Adapter:** `asType`/`asSpreader` được dựng từ type nào? Generic invoker cuối là `(Object[])Object` hay không?
7. **Invocation:** lỗi từ method handle linkage/call site hay từ target? Có giữ `cause` không?
8. **Concurrency:** registry immutable hay đang bị sửa? Target có state chia sẻ/thread-safe? Lifecycle loader có thể gây stale cache không?
9. **Security:** caller có quyền operation? Có dữ liệu nhạy cảm trong log/exception hay trong arguments không?
10. **Benchmark:** nếu cần hiệu năng, đã dùng JMH có warmup/forks, xác nhận kết quả/side effects và đo phân bố request types chưa?

### 13.2. Các mã lỗi trong demo tương ứng với hành động nào?

| Mã | Ai nên xử lý | Hành động đầu tiên |
| --- | --- | --- |
| `INVALID_REQUEST` | Caller/API gateway | Sửa cấu trúc request, không thử lại y nguyên |
| `UNKNOWN_OPERATION` | Client/contract owner | Kiểm tra operation ID, version, allowlist |
| `SIGNATURE_MISMATCH` | Client và provider owner | Xác minh exact MethodType/ABI đã đăng ký |
| `ARITY_MISMATCH` | Client/codec layer | Kiểm tra số positional arguments |
| `ARGUMENT_TYPE` | Client/validation layer | Kiểm tra runtime data type và conversion policy |
| `TARGET_FAILURE` | Owner của method thực thi | Xem root cause, error domain, idempotency/retry policy |

Không áp dụng một kiểu retry chung cho cả bảng. Request invalid thường không tự hết lỗi chỉ vì retry; target failure có thể hoặc không thể retry tùy nghiệp vụ.

## 14. Bài tập thực hành

1. **Overload selection:** Vì sao `"format"` với `(String)String` và `(String,int)String` đều nằm được trong Map của demo? Nếu chỉ keyed bằng name thì chuyện gì xảy ra?
2. **Return type:** Thay signature requested `(String)String` thành `(String)Object`, vẫn truyền đúng String. Tại sao `SIGNATURE_MISMATCH` xuất hiện trước khi invoke?
3. **STRICT versus widening:** Cho route `sum(long,long)long` và values `[Integer(2),Long(5)]`. Dự đoán `STRICT` và `WIDEN_INT_TO_LONG` trả lỗi/giá trị nào.
4. **Primitive null:** Vì sao `Long.valueOf(2)` được nhận cho `long` nhưng `null` không được nhận? Nếu parameter type là `Long.class` thì sao?
5. **Target failure:** Cho `format("ha",-1)`. Tham số vẫn đúng `(String,int)String`, vậy lỗi nên coi là `ARGUMENT_TYPE`, domain validation hay `TARGET_FAILURE` theo demo hiện tại?
6. **Interruption:** Thay target bằng một method blocking có thể ném `InterruptedException`. Đề xuất policy bảo toàn interrupt flag, cancellation và root cause.
7. **Registration failure:** Đăng ký hai lần cùng `Key("sum",(long,long)long)`; helper `add` phải xử lý thế nào? Vì sao không chọn “last registered wins”?
8. **Adapter boundary:** Vì sao generic invoker có `(Object[])Object` dù target `sum` là `(long,long)long`? `STRICT` được thực thi ở vị trí nào trong pipeline?
9. **Direct invocation:** Tại sao `invokeExact(7)` trên target `(long)long` thất bại, còn `invoke(7)` có thể thành công? Điều này có cho phép dispatcher bỏ validation policy không?
10. **Plugin security:** Một user gửi method name `deleteAllUsers` qua API ngoài. Vì sao không nên dùng privileged lookup phản chiếu method ấy? Thiết kế allowlist route và authorization.
11. **Hot reload:** Hai class cùng tên ở hai plugin loaders có thể tạo hai `MethodType` bằng nhau không khi parameter type là class riêng loader? Khi thay plugin, phải xử lý cache và lifecycle thế nào?
12. **Benchmark:** Thiết kế thử nghiệm so sánh Reflection, generic MethodHandle adapter và typed direct invoke cho cùng operation, có warmup, fork và tỉ lệ dữ liệu phù hợp production.

## 15. Tổng kết

Một bộ phân phối động đáng tin cậy cần **tách ba lớp**:

1. **Chọn route bằng hợp đồng tĩnh:** `(operation, MethodType)` và exact signature.
2. **Chuyển đổi dữ liệu bằng chính sách ứng dụng:** validate arity, null, primitive wrappers, reference assignability, chỉ whitelist những conversion có chủ đích.
3. **Thực thi và báo lỗi có quy tắc:** cached MethodHandle adapter, stable error code theo pha, giữ cause của target, không đánh đồng lỗi cấu hình, lỗi dữ liệu và lỗi JVM.

Demo dùng `Map.copyOf` và một invoker generic `(Object[])Object` để minh họa đúng cơ chế. Với hệ thống production, cần bổ sung authorization, schema/domain validation, thread safety, lifecycle class loader, timeout/cancellation, observability và benchmark. **Khả năng thích nghi kiểu của JVM không thay thế quy tắc conversion của API.**

## Tài liệu tham khảo chính thức

- [Java SE 17 — `MethodHandle`: `invokeExact`, `invoke`, `asType`, `invokeWithArguments`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java SE 17 — `MethodHandles`: `asSpreader`, `explicitCastArguments`, `guardWithTest`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 17 — `MutableCallSite` và `syncAll`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html)
- [Java SE 17 — `VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html)
- [JVM Specification 17 — `invokevirtual` / `invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html)
