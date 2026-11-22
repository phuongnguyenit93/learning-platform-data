# 19.1. Chọn lời gọi trực tiếp, functional interface, reflection, method handle hoặc proxy theo nhu cầu

## 1. Vấn đề thiết kế: không có một cơ chế gọi nào luôn tốt nhất

Một hệ thống Java có nhiều cách kích hoạt cùng một hành vi:

- **Gọi trực tiếp** một method qua biến có kiểu tĩnh đã biết, có thể là lời gọi trên concrete class hoặc qua interface.
- **Functional interface** nhận lambda/method reference, chẳng hạn `Runnable`, `Function<T,R>`, `IntUnaryOperator` hoặc interface tự định nghĩa.
- **Core Reflection** dùng `java.lang.reflect.Method`, `Constructor`, `Field` để khám phá và thao tác member từ metadata runtime.
- **`MethodHandle`** dùng `java.lang.invoke.MethodHandles.Lookup`, `MethodType` và `MethodHandle.invokeExact`/`invoke` để tạo và sử dụng lời gọi có kiểu rõ ràng, có thể tổ hợp thành các adapter.
- **JDK dynamic proxy** dùng `Proxy.newProxyInstance` + `InvocationHandler` để chặn và ủy quyền các lời gọi qua **interface** mà không viết một wrapper thủ công cho từng method.

Cả năm có thể dẫn tới **cùng method nghiệp vụ**, nhưng chúng khác nhau ở **thời điểm quyết định đích**, **khả năng khám phá metadata**, **chữ ký và chuyển kiểu**, **phạm vi chặn lời gọi**, **quyền truy cập**, **lỗi**, **khả năng công cụ/JIT tối ưu**, **chi phí khởi tạo** và **khả năng bảo trì**.

**Quy tắc chủ đạo:** chọn cơ chế **đơn giản nhất đáp ứng đúng contract và điểm biến động thực tế**, rồi đo hiệu năng trong workload thật khi cần. Không nên tự động thay mọi lời gọi bình thường bằng `MethodHandle` vì nghe “gần JVM”, cũng không nên dùng reflection hoặc proxy khi một public method/interface đơn giản đã giải quyết được yêu cầu.

Mục tiêu học tập:

1. Phân biệt “động” ở **đích gọi** với “động” ở **tên/signature/member metadata**.
2. Xác định khi nào **direct/interface** hay **functional interface** là đủ.
3. Xác định khi nào Reflection thực sự cần cho discovery, và khi nào nên chuyển từ metadata sang `MethodHandle` đã cache.
4. Hiểu `MethodType`, `invokeExact`, receiver, boxing/unboxing, exception và JPMS access.
5. Biết khi nào proxy mang lại lợi ích interception/cross-cutting và những giới hạn quan trọng của JDK proxy.
6. Biết **đo hiệu năng đáng tin** bằng benchmark/JMH hoặc profiling, không suy ra thứ hạng cố định từ một lần `nanoTime`.
7. Dùng một ví dụ Java 17+ **biên dịch và chạy thật** để kiểm chứng các cơ chế trên cùng một nghiệp vụ.

## 2. Quyết định nhanh theo câu hỏi nghiệp vụ

Trước khi chọn API, hãy trả lời các câu hỏi theo thứ tự:

```text
Đã biết method và kiểu tại thời điểm viết code?
  |
  +-- Có
  |     |
  |     +-- Chỉ cần thực thi nghiệp vụ?
  |     |      -> Gọi trực tiếp / qua interface
  |     |
  |     +-- Muốn truyền một hành vi/callback có kiểu?
  |     |      -> Functional interface + lambda/method reference
  |     |
  |     +-- Muốn intercept nhiều method của một interface
  |            với logging, auth, metrics, transaction ...?
  |            -> Decorator thủ công hoặc JDK dynamic proxy
  |
  +-- Không
        |
        +-- Cần duyệt annotations, tên, signatures, fields
        |      hay plugin types được biết ở runtime?
        |      -> Core Reflection để khám phá
        |
        +-- Cần gọi target đã khám phá nhiều lần, gắn tham số,
               đổi type hay ghép adapter động?
               -> Lookup + MethodHandle được chuẩn hóa và tái sử dụng
```

**Lưu ý:** một kiến trúc có thể dùng **nhiều cơ chế nối tiếp**: reflection để khám phá member một lần, `MethodHandle` cho đường gọi lặp lại, functional interface làm public API, và proxy để audit/authorization ở biên dịch vụ. Đây không phải năm công nghệ loại trừ nhau.

### Bảng lựa chọn ở mức kiến trúc

| Bài toán thực | Chọn ban đầu | Vì sao |
| --- | --- | --- |
| Gọi `service.calculate(x)` đã biết từ source | Direct hoặc interface dispatch | Contract rõ, compiler kiểm tra kiểu, ít code |
| Thay thuật toán bằng callback đơn hoặc strategy | Functional interface | Hành vi là giá trị có kiểu; dễ injection/test |
| Tìm method qua tên/annotation lúc chạy | Reflection | API metadata trực tiếp và toàn diện |
| Gọi member đã tìm trong đường hot path hoặc tổ hợp call adapters | MethodHandle | Invocation có `MethodType`, dễ cache/compose |
| Thêm logging/metrics/auth quanh mọi lời gọi của interface | Decorator hoặc JDK proxy | Có một điểm intercept tập trung |
| Chặn calls tới concrete class **không có interface** | Không dùng JDK dynamic proxy như giải pháp trực tiếp | JDK `Proxy` tạo implementations của interfaces, không tùy ý subclass class |
| Một API public ổn định nhưng backend thay đổi | Interface + dependency injection; proxy chỉ khi cần cross-cutting | Cách đơn giản vẫn rõ ràng |
| Plugin có member hoàn toàn không biết trước | Reflection discovery, sau đó cân nhắc handles | Dữ liệu metadata chỉ có lúc runtime |
| Mục tiêu chỉ là “chạy nhanh hơn” | Giữ cấu trúc hiện tại, đo/profiling trước | Tránh tối ưu khi chưa có bottleneck |

## 3. Lời gọi trực tiếp và lời gọi qua interface: mặc định nên ưu tiên

Ví dụ:

```java
int direct = real.compute(3);

Operation service = real;
int throughInterface = service.compute(3);
```

Đây là **đoạn mã minh họa** trong chương trình mục 10, với `RealOperation real` và `Operation` đã được khai báo.

- `real.compute(3)` có static receiver type `RealOperation`; bytecode có thể dùng `invokevirtual` với class method reference.
- `service.compute(3)` có static receiver type `Operation`; bytecode thường dùng `invokeinterface`.
- **Cả hai vẫn dùng dynamic dispatch đối với instance virtual/interface methods**: runtime chọn implementation tương ứng receiver. “Gọi trực tiếp” ở đây có nghĩa **lập trình viên biết target contract và gọi bằng cú pháp Java bình thường**, không phải “JVM luôn bỏ virtual dispatch”.
- `javac` và JVM kiểm tra method, tham số và type theo các quy tắc Java thông thường.
- JIT có thể inline, devirtualize, dùng type profiling hoặc tối ưu qua interface dispatch nếu thấy đủ ổn định. **Không có quy tắc interface call chắc chắn chậm hơn concrete call** trong mọi tình huống.

**Ưu điểm:** cú pháp dễ đọc, stack trace/IDE refactoring rõ, kiểm tra kiểu lúc compile, ít setup, không cần tự xử lý `MethodType`, `InvocationTargetException` hay handler.

**Giới hạn:** không thích hợp nếu **tên và signature member chỉ được biết từ cấu hình runtime** và không có interface ổn định. Việc dùng rất nhiều `if/else` theo tên method có thể báo hiệu thiếu mô hình polymorphism hoặc cần registry/lookup.

### Gọi concrete class hay interface?

Nếu mục tiêu là bảo trì lâu dài, nhiều hệ thống nên **khai báo dependency dưới dạng interface** để thay implementation khi test hoặc triển khai, dù call site có thể chậm hơn hay nhanh hơn vài nano-giây tùy JIT. Đây là **lựa chọn thiết kế**, không phải khẳng định hiệu năng cố định.

Không tạo interface cho **mọi** class chỉ để “đẹp kiến trúc”. Dùng interface khi có contract có ý nghĩa: nhiều implementations, plugin boundary, test seam, public SPI, hoặc phân tách phụ thuộc. Với helper thuần nội bộ và ổn định, concrete class/method bình thường có thể đơn giản hơn.

## 4. Functional interface: truyền hành vi có kiểu thay vì tên method

Một **functional interface** có đúng một abstract method theo quy tắc Java (có thể có `default`/`static` methods và phương thức `Object` không tính theo cách thông thường). Lambda/method reference có thể hiện thực contract đó:

```java
IntUnaryOperator operation = real::compute;
int result = operation.applyAsInt(3);
```

Đây là **đoạn trong ngữ cảnh ví dụ mục 10**.

Functional interface phù hợp khi:

- Bên nhận chỉ cần **một hành vi cụ thể**, ví dụ callback, predicate, transformer, strategy, retry callback.
- Tên/signature của thao tác **đã biết khi biên dịch**.
- Muốn tránh đưa `Method`, `MethodHandle` hoặc `InvocationHandler` như một public contract quá kỹ thuật.
- Muốn khả năng test bằng lambda `x -> x + 1` hoặc method reference `service::compute`.
- Có thể dùng các specialized interfaces cho primitive để tránh boxing: `IntUnaryOperator`, `IntPredicate`, `ToIntFunction<T>`, `IntConsumer`, ...

Ví dụ trong một pipeline:

```java
static int applyTwice(IntUnaryOperator operation, int value) {
    return operation.applyAsInt(operation.applyAsInt(value));
}
```

Đây là một **method minh họa độc lập** nếu có `import java.util.function.IntUnaryOperator;`.

**Ưu điểm:** giữ type-safe contract, ít boilerplate; implementation có thể là lambda, method reference hoặc class. Lập trình viên không cần biết implementation đang là generated lambda object hay wrapper.

**Giới hạn:**

- Không tự khám phá một method bất kỳ chỉ bằng tên string lấy từ config.
- Không cung cấp danh sách mọi methods/fields/annotations của receiver.
- Với nhiều operations hoặc nhiều cross-cutting concerns, một interface/service API có nhiều methods và decorator/proxy có thể phù hợp hơn một collection callbacks rời rạc.
- Các generic `Function<Integer,Integer>` có thể kéo theo boxing; dùng primitive specializations khi số lượng lời gọi/allocations đủ quan trọng.
- Lambda capture có thể giữ reference tới receiver hoặc các object khác và kéo dài vòng đời của chúng; đừng vô tình lưu callback trong global registry.

**Về hiệu năng:** compiler có thể phát `invokedynamic` cho expression tạo lambda/method reference và JVM có thể tối ưu rất tốt, nhưng điều đó không đồng nghĩa **mỗi lần `applyAsInt` là instruction `invokedynamic`**. Trong ví dụ Java 17 ở dưới, lời gọi functional method dùng `invokeinterface`; `invokedynamic` xuất hiện khi tạo method-reference object. Không tự suy thứ hạng nhanh/chậm từ một opcode.

## 5. Core Reflection: chọn khi phải hiểu và thao tác metadata runtime

Nếu tên/signature hoặc cấu trúc class chỉ xuất hiện khi chạy, Reflection là công cụ trực tiếp nhất:

```java
Method method = Operation.class.getMethod("compute", int.class);
Object value = method.invoke(real, 3);
```

Đây là **đoạn minh họa**; cần `import java.lang.reflect.Method;` và các biến đúng ngữ cảnh.

`Method` cho phép đọc `getName()`, `getParameterTypes()`, `getReturnType()`, annotations, modifiers, declaring class, generic type metadata... Những API này đặc biệt hữu ích cho:

- Dependency injection/container scans.
- Serialization/ORM binding.
- Plugin discovery có type chưa biết tại compile time.
- Validation dựa trên annotations và reflective introspection.
- CLI/RPC/command dispatcher ánh xạ cấu hình hoặc metadata thành một method.

Reflection **không có nghĩa mọi member đều truy cập được**. `getMethod` tìm public members theo contract; `getDeclaredMethod` tìm member được khai báo trực tiếp (kể cả private), nhưng **tìm được Method object không đồng nghĩa `Method.invoke` được phép gọi**. Java access control và JPMS module exports/opens vẫn áp dụng. `setAccessible(true)` không phải bypass tuyệt đối khi strong encapsulation cấm deep reflection.

### Chi phí cần tính

- **Discovery**: tìm methods, duyệt annotations, kiểm tra signatures, xử lý lỗi; có thể tốn chi phí đáng kể nếu lặp lại trong mỗi request.
- **Invocation**: `Method.invoke(target,args)` sử dụng varargs `Object...`; tham số primitive có thể boxing và kết quả primitive thường được boxing để trả dưới dạng `Object`.
- **Error handling**: method đích ném exception sẽ được bọc trong `InvocationTargetException`, cần unwrap khi muốn giữ lỗi gốc.
- **Access check**: Reflection thông thường kiểm tra quyền theo caller khi invoke, trừ các trường hợp access checks đã được suppress hợp lệ theo API.
- **JIT**: hiệu năng thay đổi theo JDK version, method stability, escape analysis, inlining và cách tổ chức code; không có một mức overhead cố định.

**Nguyên tắc:** thực hiện `getMethod`/annotation discovery ở **giai đoạn setup**, lưu `Method`/schema mapping cho các lần dùng sau. Nhưng việc cache không tự giải quyết những vấn đề boxing, exception hay access.

Không viết:

```java
for (...) {
    Method m = target.getClass().getMethod("compute", int.class);
    m.invoke(target, value);
}
```

trong hot path chỉ vì dễ code, nếu method thực tế ổn định. Đây là **mẫu phản ví dụ**; vòng lặp thiếu biến cụ thể và không phải chương trình Java độc lập.

## 6. `MethodHandle`: khi invocation cần typed adapter và tổ hợp động

`MethodHandle` là **đối tượng tham chiếu lời gọi đã được tạo**, có kiểu chính xác `MethodType`. Bạn thường dùng `Lookup` để lấy handle:

```java
MethodHandle handle = MethodHandles.lookup().findVirtual(
        Operation.class,
        "compute",
        MethodType.methodType(int.class, int.class));
```

Đây là **đoạn minh họa** trong cùng class có quyền đối với `Operation`.

Với instance method `int Operation.compute(int)`, handle thực tế có type:

```text
(Operation,int)int
```

**Receiver** là tham số đầu của `MethodHandle` dù trong method Java nguyên bản nó được viết trước dấu chấm. Ví dụ:

```java
int result = (int) handle.invokeExact((Operation) real, 3);
```

`invokeExact` yêu cầu **static type của arguments và return type ở call site khớp chính xác** với `handle.type()`. Trong ví dụ này, cast `(Operation) real` là cần thiết để caller signature có receiver kiểu `Operation`, và cast `(int)` trên kết quả xác định return type là primitive `int`.

Nếu truyền `(Object) real` vào chính `invokeExact` thì Java source vẫn có thể compile do signature-polymorphic method, nhưng runtime sẽ báo **`WrongMethodTypeException`** vì call-site type `(Object,int)int` không bằng `(Operation,int)int`.

### Khi nào dùng?

- Member được resolve từ metadata runtime nhưng được gọi **rất nhiều lần** sau khi tìm ra.
- Một framework cần compose adapters: `bindTo`, `asType`, `filterArguments`, `foldArguments`, `guardWithTest`, `dropArguments`, `insertArguments`, ...
- Cần type signature rõ ràng khi xây dynamic dispatch hoặc runtime DSL.
- Muốn tạo hẹp một **capability** gọi member riêng tư đã được `Lookup` có quyền tạo hợp lệ, thay vì chia sẻ nguyên full-privilege `Lookup`.
- Cần liên kết với những cơ chế `java.lang.invoke` khác, ví dụ `CallSite`/`invokedynamic`; **nhưng tự gọi `invokeExact` vẫn không đồng nghĩa opcode `invokedynamic`**.

### Chi phí và giới hạn

- `Lookup.findVirtual`, `MethodType` construction và adapter creation có **setup cost**; đừng làm lại mọi lần trên hot path.
- `invokeExact` cần **exact type**; nếu sử dụng `invoke` thì có thể có conversions theo `asType`. `invokeWithArguments(Object...)` tiện cho số lượng tham số/kiểu thật sự động, nhưng có thể có varargs allocation, boxing và adaptation.
- `findVirtual` có thể ném `NoSuchMethodException`/`IllegalAccessException`; Java module boundary và lookup modes vẫn cần được tôn trọng.
- Method handles được tạo hợp lệ có thể được invoke bởi bên nhận dù họ không thể tự access member private. **Không chia sẻ private handle hoặc full `Lookup` cho untrusted code một cách vô ý.**
- Typed handles **không thay thế Reflection metadata APIs** khi cần liệt kê annotations, fields hoặc constructors; có thể dùng Reflection để khám phá rồi tạo handle một lần.

### `bindTo` khi muốn loại receiver khỏi call site

```java
MethodHandle bound = handle.bindTo(real);
int result = (int) bound.invokeExact(3);
```

Đây là **đoạn minh họa** trong ví dụ; với target handle `(Operation,int)int`, bound handle sẽ có type `(int)int`. Việc giữ `bound` giữ reference tới `real`; cần xét memory/caching nếu receiver là object ngắn hạn hoặc thuộc plugin class loader cần unload.

**Không khẳng định `MethodHandle` luôn nhanh hơn `Method.invoke`.** Java 17 khác các JDK sau ở implementation details; HotSpot có thể tối ưu cả direct, lambda, reflective và handle paths tùy call site. Cần đo với version, độ ổn định type và workload tương ứng.

## 7. Dynamic proxy: khi cần can thiệp lời gọi vào một interface

JDK dynamic proxy là một object implement một hoặc nhiều interfaces được đưa vào `Proxy.newProxyInstance`. Nó chuyển interface method calls tới một `InvocationHandler`:

```java
Operation proxy = (Operation) Proxy.newProxyInstance(
        Operation.class.getClassLoader(),
        new Class<?>[] { Operation.class },
        (p, method, args) -> method.invoke(real, args));
```

Đây là **đoạn minh họa**, chưa có xử lý `InvocationTargetException`, Object methods hoặc policy. Ví dụ chạy đầy đủ ở mục 10 có các phần bổ sung ấy.

Dùng khi:

- Cần ghi log, metrics, tracing, retry, authorization hoặc transaction boundary **cho nhiều methods thuộc một interface**.
- Muốn code chặn cuộc gọi nằm trong một handler thay vì viết wrapper riêng cho mỗi signature.
- Contract public của ứng dụng đã dựa trên interface.
- Framework hoặc integration point nhận một interface object do bạn cung cấp.

### Cần hiểu đúng receiver

- `proxy` trong `InvocationHandler.invoke(proxy, method, args)` là **object proxy** mà client vừa gọi.
- `real`/`target` là **implementation thật**.
- Khi muốn ủy quyền, dùng `method.invoke(real,args)`, **không** dùng `method.invoke(proxy,args)` vì lời gọi trên proxy lại vào chính handler và có thể gây **đệ quy vô hạn**.
- Với method do target ném exception, `Method.invoke` bọc nó trong `InvocationTargetException`. Handler có thể unwrap để caller nhận **exception gốc** nếu tương thích contract.

**Self-invocation bypass:** nếu target thực hiện `this.anotherMethod()` từ trong `real.compute(...)`, lời gọi nội bộ đó không tự đi qua proxy, vì `this` là target. Điều này rất quan trọng nếu proxy đang chịu trách nhiệm authorization, transaction hoặc metrics.

### Những method/giới hạn đặc biệt

- JDK proxy **chỉ implement interfaces**, không tự subclass một concrete class chỉ vì class ấy có public methods.
- `equals(Object)`, `hashCode()` và `toString()` cũng đi qua handler. Nếu handler log bằng cách nối `proxy` vào string (kích hoạt `toString`), có thể vô tình tái nhập.
- Default interface methods cần lựa chọn rõ: delegate trên target hay dùng `InvocationHandler.invokeDefault(...)` để gọi default implementation trên proxy (Java 16+). Hai chiến lược có thể khác nhau về nested interception.
- Handler nhận `Object[] args` (có thể là `null` nếu method không có arguments), có overhead boxing/varargs trong nhiều trường hợp.
- Lời gọi checked exception không được interface khai báo có thể bị JDK proxy bọc vào `UndeclaredThrowableException`; không dùng `catch(Exception)` tùy tiện để xóa cause.
- Cần kiểm soát class loader, module, interface visibility và vòng đời của proxy/handler/target.
- Handler state chia sẻ qua threads phải tuân thủ thread safety khi proxy được gọi đồng thời.

### Proxy hay decorator thủ công?

Nếu chỉ có một vài methods ổn định và type safety rõ ràng, **decorator thủ công** thường dễ đọc và dễ debug. Dynamic proxy thích hợp hơn khi nhiều interfaces/methods cùng dùng một interceptor policy, hoặc khi framework tạo hàng loạt wrappers từ metadata.

Không phải cứ cần logging là phải dùng dynamic proxy; đôi khi ghi log thẳng trong application service hoặc dùng một decorator tĩnh là đủ và minh bạch hơn.

## 8. Bảng so sánh theo chi phí, kiểu, khả năng biến đổi và rủi ro

| Tiêu chí | Direct/interface | Functional interface | Reflection | MethodHandle | JDK dynamic proxy |
| --- | --- | --- | --- | --- | --- |
| Đích/contract biết trước lúc compile | Thường có | Có đối với signature callback | Không bắt buộc | Không bắt buộc | Interface cần biết/nhìn thấy |
| API type-safe tại call site | **Có** | **Có** | Tham số/return qua `Object[]`/`Object` | Có nếu type chuẩn và `invokeExact` chính xác | Có ở client interface; trong handler là dynamic |
| Khám phá methods/annotations | Không phải mục đích | Không phải mục đích | **Mạnh** | Không thay Reflection metadata discovery | Handler nhận `Method` ở mỗi interception |
| Tổ hợp/chỉnh signature runtime | Java code thường | Lambda composition theo interface | Không phải thế mạnh | **Mạnh** (`asType`, `filter*`, `guardWithTest`...) | Đổi logic intercept, không đổi signature interface |
| Chi phí khởi tạo | Rất nhỏ | Có thể tạo/giữ functional object | Tìm `Method`, setup access | `Lookup`, handle/adapters | Tạo proxy class/instance và handler |
| Chi phí trong mỗi lời gọi | Phụ thuộc JIT/dispatch | Phụ thuộc capture, JIT và interface | Reflection + conversions | Phụ thuộc handle graph, adaptation và JIT | Interception + handler + delegation |
| Primitive boxing | Có thể tránh | Có thể tránh với primitive-specialized interfaces | Thường có boxing tại API boundary | `invokeExact` có thể giữ primitive | Handler `Object[]` có thể boxing |
| Xử lý exception target | Java bình thường | Java interface contract | `InvocationTargetException` wrapper | Target exception truyền như vốn có | Handler có thể unwrap; checked exception constraints |
| Access control | Java/JPMS compile/link | Java/JPMS tại tạo lambda/callback | Reflection access & `setAccessible` restrictions | Lookup access lúc tạo handle | Chỉ intercept methods của interface visible |
| Cross-cutting nhiều methods | Viết wrapper/decorator | Từng behavior riêng | Framework có thể dispatch bằng reflection | Tạo adapter graph | **Điểm mạnh chính** |
| Dễ debug/refactor | Thường dễ nhất | Dễ nếu contract gọn | Chuỗi tên/signatures lỗi runtime | Phải hiểu `MethodType` | Stack trace và reentrancy phức tạp hơn |
| Cần khi external config chọn member bằng string | Không tự xử lý | Không tự xử lý | **Có** | Sau khi discovery/lookup | Không giải quyết metadata discovery một mình |

**Các mục chi phí trên là mô hình định tính, không phải bảng xếp hạng benchmark.** JIT có thể inline hoặc hoist setup, runtime context có thể khiến chênh lệch nhỏ hơn hoặc lớn hơn nhiều so với trực giác; dữ liệu thực tế mới quyết định.

## 9. Thiết kế một phép thử công bằng: một method, nhiều đường gọi

Chúng ta cần giữ **cùng mục tiêu nghiệp vụ**:

```java
int compute(int value) {
    if (value < 0) throw new IllegalArgumentException("negative");
    return value * 2 + 2;
}
```

Đây là **mảnh mã minh họa**, implementation chạy đầy đủ ở phần tiếp theo.

Nếu mỗi chiến lược gọi một method khác nhau, benchmark/correctness test sẽ không so sánh cùng một công việc. Vì vậy ví dụ dưới đây dùng **một `RealOperation`** và đi qua nhiều cơ chế để quan sát:

- Tất cả trả cùng kết quả cho `3`.
- Reflection và proxy handler có `InvocationTargetException` path.
- MethodHandle có typed receiver và thể hiện `WrongMethodTypeException`.
- Proxy intercept đúng một lần cho lời gọi thành công; không bị đệ quy.
- `bindTo` loại receiver khỏi type của handle.
- Số lượt thực thi method thật vẫn đếm được.
- `Proxy` xử lý `equals` và `toString` mà không tự tái nhập.

**Ví dụ này kiểm tra correctness/semantics, KHÔNG đo tốc độ.** Đọc các dòng output để phân biệt cơ chế thay vì suy ra số nano-giây.

## 10. Chương trình Java 17+ chạy độc lập: sáu đường gọi tới cùng nghiệp vụ

Lưu file đúng tên **`DispatchChoiceDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntUnaryOperator;

public final class DispatchChoiceDemo {
    interface Operation {
        int compute(int value);
    }

    static final class RealOperation implements Operation {
        int calls;

        @Override
        public int compute(int value) {
            calls++;
            if (value < 0) {
                throw new IllegalArgumentException("negative");
            }
            return value * 2 + 2;
        }
    }

    public static void main(String[] args) throws Throwable {
        RealOperation real = new RealOperation();
        Operation asInterface = real;
        IntUnaryOperator function = real::compute;

        Method method = Operation.class.getMethod("compute", int.class);

        MethodHandle handle = MethodHandles.lookup().findVirtual(
                Operation.class, "compute",
                MethodType.methodType(int.class, int.class));
        MethodHandle bound = handle.bindTo(real);

        AtomicInteger intercepted = new AtomicInteger();
        Operation proxy = (Operation) Proxy.newProxyInstance(
                Operation.class.getClassLoader(),
                new Class<?>[] { Operation.class },
                (p, m, params) -> {
                    if (m.getDeclaringClass() == Object.class) {
                        return switch (m.getName()) {
                            case "equals" -> p == params[0];
                            case "hashCode" -> System.identityHashCode(p);
                            case "toString" -> "OperationProxy";
                            default -> throw new UnsupportedOperationException(
                                    m.getName());
                        };
                    }

                    intercepted.incrementAndGet();

                    try {
                        // ĐÚNG: target là real, KHÔNG phải p (proxy).
                        return m.invoke(real, params);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                });

        System.out.println("direct=" + real.compute(3));
        System.out.println("interface=" + asInterface.compute(3));
        System.out.println("functional=" + function.applyAsInt(3));
        System.out.println("reflection="
                + ((Integer) method.invoke(real, 3)).intValue());
        System.out.println("handle="
                + (int) handle.invokeExact((Operation) real, 3));
        System.out.println("boundHandle="
                + (int) bound.invokeExact(3));
        System.out.println("proxy=" + proxy.compute(3));

        System.out.println("realCalls=" + real.calls);
        System.out.println("intercepted=" + intercepted.get());
        System.out.println("handleTypeMatches="
                + handle.type().equals(MethodType.methodType(
                        int.class, Operation.class, int.class)));
        System.out.println("boundTypeMatches="
                + bound.type().equals(MethodType.methodType(
                        int.class, int.class)));
        System.out.println("proxyEqualsSelf=" + proxy.equals(proxy));
        System.out.println("proxyToString=" + proxy.toString());

        try {
            method.invoke(real, -1);
        } catch (InvocationTargetException ex) {
            System.out.println("reflectionException="
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            proxy.compute(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("proxyException="
                    + ex.getClass().getSimpleName());
        }

        try {
            int ignored =
                    (int) handle.invokeExact((Operation) real, -1);
            System.out.println(ignored);
        } catch (IllegalArgumentException ex) {
            System.out.println("handleException="
                    + ex.getClass().getSimpleName());
        }

        try {
            int ignored =
                    (int) handle.invokeExact((Object) real, 3);
            System.out.println(ignored);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrongHandleType=detected");
        }

        System.out.println("realCallsFinal=" + real.calls);
        System.out.println("interceptedFinal=" + intercepted.get());
    }
}
```

### 10.1. Biên dịch và thực thi

Dùng **JDK 17+**, đứng trong thư mục chứa file:

```bash
javac --release 17 DispatchChoiceDemo.java
java DispatchChoiceDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
direct=8
interface=8
functional=8
reflection=8
handle=8
boundHandle=8
proxy=8
realCalls=7
intercepted=1
handleTypeMatches=true
boundTypeMatches=true
proxyEqualsSelf=true
proxyToString=OperationProxy
reflectionException=IllegalArgumentException
proxyException=IllegalArgumentException
handleException=IllegalArgumentException
wrongHandleType=detected
realCallsFinal=10
interceptedFinal=2
```

Ví dụ đã biên dịch thành công bằng `javac --release 17` và chạy với Java; không phụ thuộc thư viện ngoài.

### 10.2. Vì sao tất cả các dòng đầu đều trả `8`?

Tất cả đường gọi cùng tới `RealOperation.compute(3)`. Với biểu thức `3 * 2 + 2`, kết quả là `8`:

- `direct`: Java call trên biến concrete `RealOperation`.
- `interface`: Java call trên `Operation`.
- `functional`: `IntUnaryOperator` chứa method reference `real::compute`.
- `reflection`: `Method` đại diện `Operation.compute`, gọi trên `real`; kết quả primitive `int` được boxing về `Integer`.
- `handle`: `MethodHandle` tới interface method, với receiver `(Operation)real`.
- `boundHandle`: `bindTo(real)` đã gắn receiver; caller chỉ truyền `int`.
- `proxy`: handler nhận một interface call, sau đó `Method.invoke(real,params)` chạy cùng method thật.

Vì có **bảy lời gọi thành công** vào target (tính `boundHandle` riêng), `realCalls=7`. Proxy chỉ tham gia **một** lời gọi đến lúc này, nên `intercepted=1`.

### 10.3. Vì sao có `handleTypeMatches=true`?

`Operation.compute(int)` là instance method. `MethodHandles.lookup().findVirtual(Operation.class, "compute", MethodType.methodType(int.class,int.class))` tìm member signature `(int)int`, nhưng handle trả về có **receiver** thêm vào đầu, thành `(Operation,int)int`.

`bindTo(real)` cố định tham số receiver, nên `bound.type()` trở thành `(int)int`.

Nếu muốn sử dụng handle trong một framework generic, hãy ghi nhận **`MethodType` thật** chứ không chỉ chữ ký của Java method khai báo.

### 10.4. Vì sao Reflection bọc exception, proxy và handle thì không?

Khi gọi `compute(-1)`, method thật ném `IllegalArgumentException("negative")`:

- `Method.invoke(real,-1)` phản chiếu method đã thực thi, nên bọc exception đích vào `InvocationTargetException`. Demo bắt wrapper và in **tên class của cause**.
- Proxy handler bắt wrapper do chính `m.invoke(real,params)` ném và **rethrow cause**, nên caller nhìn thấy `IllegalArgumentException` gốc.
- `MethodHandle.invokeExact` truyền exception do target ném mà không tự bọc trong `InvocationTargetException`.

Ba cơ chế **không làm exception nghiệp vụ biến mất**. Khác biệt là đường bọc và contract của API.

### 10.5. Vì sao `(Object)real` báo `WrongMethodTypeException`?

Dòng:

```java
(int) handle.invokeExact((Object) real, 3)
```

làm call site có receiver kiểu `Object`; trong khi handle cần receiver `Operation`. `invokeExact` yêu cầu **khớp tuyệt đối** nên không tự cast `Object` về `Operation`, kể cả object runtime thực tế là một `RealOperation`.

`wrongHandleType=detected` chứng minh type check xảy ra **trước khi** method nghiệp vụ được gọi, nên `realCallsFinal=10` thay vì 11: ba lời gọi `compute(-1)` đã tăng bộ đếm từ 7 lên 10; wrong-type call không chạy target.

### 10.6. Proxy không chặn mọi lời gọi tới object thật

`interceptedFinal=2` vì proxy handler chỉ nhận hai lần `proxy.compute(...)`: một lần thành công (`3`), một lần ném lỗi (`-1`). Các lời gọi bằng `real`, `asInterface`, lambda, reflection và method handle **không tự đi qua proxy**.

Đây là sự thật quan trọng nếu proxy đang bảo vệ an ninh hoặc tạo transaction boundary: **ai giữ reference tới target thật có thể gọi trực tiếp ngoài proxy**. Muốn có chính sách đáng tin phải thiết kế object ownership, API boundary và không vô ý phát target raw ra những nơi cần interception.

`proxy.equals(proxy)` và `proxy.toString()` cũng vào handler, nhưng demo chọn một **identity policy** riêng và không tăng bộ đếm nghiệp vụ. Điều này tránh nhầm Object methods với `compute` và tránh recursion do `toString` trong logging.

## 11. Kiểm tra bytecode: “tên API” không quyết định opcode một cách đơn giản

Sau khi compile, chạy:

```bash
javap -c -p DispatchChoiceDemo
```

Trong một lần biên dịch với Java 17, disassembly cho thấy các lớp khác nhau:

| Source expression | Opcode/hoạt động thấy được |
| --- | --- |
| `real.compute(3)` | `invokevirtual` tới `RealOperation.compute` |
| `asInterface.compute(3)` | `invokeinterface` tới `Operation.compute` |
| `function.applyAsInt(3)` | `invokeinterface` tới `IntUnaryOperator.applyAsInt` |
| `method.invoke(real,3)` | `invokevirtual` tới `java.lang.reflect.Method.invoke` |
| `handle.invokeExact(...)` | `invokevirtual` signature-polymorphic tới `MethodHandle.invokeExact` |
| `proxy.compute(3)` | Client call tới interface thường là `invokeinterface`; generated proxy/handler thực hiện interception |
| Expression `real::compute` | Compiler có thể phát **`invokedynamic`** để tạo functional object |
| Expression lambda cho `InvocationHandler` | Compiler có thể phát `invokedynamic` để tạo handler |
| Runtime string concatenation trong logging | Java 17 `javac` thường phát `invokedynamic` qua `StringConcatFactory` |

**Không suy diễn:** thấy `invokedynamic` trong disassembly **không chứng minh** lời gọi `MethodHandle.invokeExact` dùng opcode `invokedynamic`. `invokeExact` là method signature-polymorphic nhưng lời gọi từ Java source vẫn dùng `invokevirtual`, theo Java SE 17 API.

**Cũng không kết luận “direct luôn nhanh hơn interface” từ hai opcode.** JIT có thể devirtualize và inline cùng target; bytecode ban đầu không phải mã máy tối ưu cuối cùng. Bytecode hữu ích để hiểu cơ chế và phát hiện adapter/object allocation paths, nhưng chưa phải benchmark.

## 12. So sánh chi phí **setup** và chi phí **mỗi lần gọi**

Một mô hình sơ bộ, chỉ dùng để suy nghĩ:

\[
T_{\text{tổng}} \approx T_{\text{khởi tạo}} + N \times T_{\text{đường gọi}} + T_{\text{nghiệp vụ}} + T_{\text{bộ nhớ/GC/I/O}}
\]

Đây là **mô hình định tính**, không phải công thức đo chính xác cho mọi workload. Trong thực tế, JIT compilation, code layout, branches, allocations, contention và GC thay đổi chi phí theo thời gian.

| Cơ chế | Setup một lần | Những thứ có thể xảy ra trên mỗi call |
| --- | --- | --- |
| Direct/interface | Tạo object hoặc dependency injection thông thường | JVM dispatch; có thể inline |
| Functional interface | Tạo method reference/lambda; có thể capture receiver | Invoke SAM method; có thể inline; boxing nếu dùng generic wrappers |
| Reflection | `getMethod`/`getDeclaredMethod`, chọn access | Varargs `Object[]`, boxing/unboxing, access/invocation machinery, wrapper cho target exceptions |
| MethodHandle | `Lookup.find*`, `MethodType`, tạo/bind/adapt handle | Exact invoke hoặc conversion/adapter graph; có thể inline nếu handle/call site đủ ổn định |
| JDK proxy | Tạo generated proxy class (khi cần), instance, handler | Proxy method → handler → policy → delegate; `Method`/`Object[]`/boxing tùy trường hợp |

Khi **N rất nhỏ**, setup overhead có thể chiếm tỷ trọng lớn: dùng reflection lookup hoặc tạo proxy mỗi request có thể tệ hơn một lời gọi direct đơn giản. Khi **N rất lớn**, setup amortized; điều quan trọng hơn là chi phí call path, tính ổn định của target, boxing, cache miss, allocation và JIT.

### Ví dụ so sánh lựa chọn theo tần suất

- **Một công cụ CLI gọi một method từ config đúng một lần**: Reflection sau khi validate metadata có thể hoàn toàn hợp lý; tạo cả framework handle graph chưa chắc mang lại lợi ích.
- **Một serializer xử lý hàng triệu fields**: khám phá annotations/field mapping một lần, cache schema và thử các accessor có hiệu năng phù hợp; MethodHandle/VarHandle có thể đáng thử.
- **Một API service có DB/network request 10 ms**: overhead dispatch tính bằng ns hoặc µs có thể không quyết định p99 latency; đừng tối ưu sai tầng.
- **Một parser/interpreter thao tác hàng trăm triệu bước trong CPU loop**: typed call sites, primitive specializations và cấu trúc adapter có thể trở thành bottleneck đáng đo.
- **Một hệ thống logging/metrics cần intercept hàng trăm service methods**: dynamic proxy giúp giảm boilerplate, nhưng vẫn cần đánh giá độ phức tạp và workload.

## 13. Vì sao benchmark bằng `System.nanoTime()` rất dễ kết luận sai?

Một vòng lặp đo thời gian ngắn như:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    target.compute(i);
}
long elapsed = System.nanoTime() - start;
```

Đây là **đoạn minh họa không đủ để kết luận benchmark**. Mã Java trên có thể bị JIT tối ưu khác với đường production; nếu không dùng kết quả, dead-code elimination có thể thay đổi công việc thực thi.

Các sai lệch phổ biến:

- **Cold vs warmed JVM**: JIT chưa compile/hồ sơ type chưa ổn định ở đầu; chạy nhiều lần thay đổi kết quả.
- **Dead-code elimination**: kết quả không dùng nên JVM có thể bỏ cả phép tính thuần.
- **Constant folding**: input cố định làm compiler/JIT có thể tính trước.
- **Escape analysis**: allocation có thể bị loại bỏ, hoặc lại xuất hiện khi thêm một wrapper/context mới.
- **Branch prediction**: một nhánh được chọn 100% khác với phân phối input thật.
- **Benchmark method quá nhỏ**: overhead của harness/timer và OS scheduling lấn át.
- **Dynamic targets**: một call site monomorphic khác với polymorphic/megamorphic.
- **GC/allocations**: proxy và reflection có thể tạo temporary objects tùy version/call shape; chỉ nhìn `ns/op` bỏ qua `B/op`.
- **Locking/threads**: singleton handler hoặc cache shared có thể tạo contention mà benchmark một thread không thấy.
- **Tiered compilation, inlining, CPU frequency, JDK flags và container limits**: không tương đương giữa máy/dev/prod.
- **Benchmark vốn thêm logging và `println` trong loop**: I/O thống trị dispatch overhead; kết quả không còn phản ánh chi phí lời gọi.

**Không công bố một bảng kiểu “direct = 1 ns, lambda = 2 ns, reflection = 20 ns, handle = 3 ns, proxy = 50 ns” mà không có nguồn benchmark, cấu hình và workload.** Những con số đó không phải thuộc tính cố định của Java API.

## 14. Dùng JMH và đo cả throughput, allocation lẫn tình huống thực tế

**JMH (Java Microbenchmark Harness)** do OpenJDK phát triển là công cụ chuẩn để xây microbenchmarks trên JVM, với cơ chế warmup, measurement, forks, state management và tránh một số bẫy tối ưu. Khi cần quyết định dựa trên chênh lệch nhỏ giữa reflection/handle/proxy, ưu tiên JMH hơn vòng lặp thủ công.

Quy trình đo:

1. Tạo benchmark riêng, cấu hình Java version đúng production.
2. Dùng **cùng target behavior và cùng dữ liệu** cho mọi biến thể.
3. **Tách setup** (`Method` lookup, `MethodHandle` creation, proxy construction) khỏi **call-path benchmark** nếu muốn so chi phí steady state.
4. Làm một nhóm benchmark **setup cost** khác nếu object được tạo mỗi request.
5. Tránh constant folding: input thay đổi hợp lý, consume output hoặc trả kết quả mà JMH xử lý.
6. Đo cả p50/p95/p99 trong integration workload nếu mục tiêu liên quan latency, và cả **allocation rate**, GC/CPU.
7. Có warmup/measurement iterations, nhiều forks để giảm ảnh hưởng JIT/class loading/runs trước.
8. Kiểm tra output và exception behavior **trước khi** đo tốc độ.
9. So sánh overhead với tác vụ thực tế; nếu DB/I/O hoặc business logic tốn phần lớn latency, chọn thiết kế dễ bảo trì trước.
10. Ghi đầy đủ môi trường: JDK build, JVM flags, hardware, OS, container CPU/memory, thread count, data distribution và sai số.

### Sườn JMH có chú thích — cần thư viện bên ngoài

Đoạn code sau là **sườn minh họa** cách tách setup khỏi đường đo. Nó **không chạy chỉ với JDK**, vì cần dependency `jmh-core` và annotation processor `jmh-generator-annprocess`, một project JMH được build/packaging đúng. Ví dụ runnable, không phụ thuộc thư viện ngoài, đã có ở mục 10.

```java
package demo.bench;

import java.util.concurrent.TimeUnit;
import java.util.function.IntUnaryOperator;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(3)
public class DispatchBench {
    interface Op { int compute(int x); }

    static final class Target implements Op {
        public int compute(int x) { return x * 3 + 1; }
    }

    final Target target = new Target();
    final Op viaInterface = target;
    final IntUnaryOperator function = target::compute;

    Method reflective;
    MethodHandle handle;
    Op proxy;
    int sequence;

    @Setup(Level.Trial)
    public void prepare() throws Throwable {
        reflective = Op.class.getMethod("compute", int.class);
        handle = MethodHandles.lookup().findVirtual(
                Op.class, "compute",
                MethodType.methodType(int.class, int.class));
        proxy = (Op) Proxy.newProxyInstance(
                Op.class.getClassLoader(),
                new Class<?>[] { Op.class },
                (p, method, args) -> method.invoke(target, args));
    }

    private int next() { return sequence++ & 1023; }

    @Benchmark public int direct() {
        return target.compute(next());
    }

    @Benchmark public int viaInterface() {
        return viaInterface.compute(next());
    }

    @Benchmark public int functional() {
        return function.applyAsInt(next());
    }

    @Benchmark public int reflection() throws Throwable {
        return ((Integer) reflective.invoke(target, next())).intValue();
    }

    @Benchmark public int handle() throws Throwable {
        return (int) handle.invokeExact((Op) target, next());
    }

    @Benchmark public int proxy() {
        return proxy.compute(next());
    }
}
```

Đây là **benchmark skeleton**; nếu bạn muốn chạy thực tế, hãy tạo project bằng archetype/cấu hình được hướng dẫn trong [OpenJDK JMH](https://github.com/openjdk/jmh), khai báo dependencies/annotation processing và package `demo.bench` đúng đường dẫn. Không gán stdout hay điểm số giả vì đoạn này **chưa được chạy bằng JMH** trong bài.

**Giới hạn phép so sánh của skeleton:** mỗi phương thức có call site khác nhau, type stability và inlining khác nhau; `next()` thay đổi input, nhưng target vẫn là arithmetic rất nhỏ. Kết quả JMH nếu có chỉ áp dụng cho **mô hình này**, không chứng minh overhead trong framework full stack hoặc khi reflection thực hiện parsing/lookup mỗi request.

Muốn đo **cold startup** hoặc **proxy creation**, viết benchmark setup riêng; đừng kết luận chi phí setup bằng số steady-state calls. Có thể dùng `-prof gc` để quan sát allocations trong benchmark được đóng gói đúng.

## 15. Quyết định dựa trên profiler và contract, không chỉ microbenchmark

Trước khi tối ưu dispatch, xem application-level profile:

- CPU time nằm ở nơi nào? Business logic, regex/parsing, JSON, database client, encryption hay invocation?
- Có hàng triệu method lookups lặp lại không?
- Có nhiều boxing/allocation object arrays ở Reflection/proxy boundary không?
- Có quá nhiều generated proxy classes/handlers làm tăng class loading hoặc metaspace không?
- Cần xử lý low-latency dưới tải và nhiều threads không?
- Đường gọi có một target ổn định hay thay đổi liên tục?
- Exception path có thường xuyên không? Throw exception đắt hơn một lời gọi thành công bình thường và có thể tạo stack traces.
- Có memory retention do caching `Method`, `MethodHandle`, bound handles hoặc `InvocationHandler` giữ class loaders/plugin classes không?

**Cải tiến thường có lợi hơn việc đổi API:**

- Di chuyển Reflection metadata scanning khỏi vòng lặp.
- Cache schema/method mapping có key đúng identity của class/class loader.
- Dùng `IntUnaryOperator` thay `Function<Integer,Integer>` ở hot path thực sự primitive.
- Giảm số lần intercept/log trong đường quan trọng.
- Tránh tạo proxy/handle mới cho từng request nếu contract và target giống nhau.
- Cải thiện algorithm hoặc loại bỏ network/DB round trip trước khi giảm ns-level dispatch.
- Giảm contention trong shared interceptors/caches.

Một lần đổi `Method.invoke` thành `MethodHandle.invokeExact` có thể cải thiện, không đổi hoặc kém hơn tùy cách bạn tạo/adapt handles, khả năng inline và JDK. Nếu benchmark không chứng minh lợi ích đáng kể, đừng đổi code chỉ vì “API mới hơn”.

## 16. Reflection discovery rồi chuyển sang handle: một pipeline hợp lý

Một framework có thể có hai giai đoạn:

```text
Giai đoạn setup/registration:
  scan class / annotation / config
       |
       v
  Method / member metadata
       |
       v
  kiểm tra signature, permissions, plugin policy
       |
       v
  MethodHandles.Lookup.unreflect(method) hoặc find*
       |
       v
  optional asType, bindTo, filterArguments, ...
       |
       v
  cache một invoker với contract chuẩn
       |
       v
Giai đoạn hot path:
  validate input -> invoke invoker -> business result
```

**`Lookup.unreflect(method)` không phải công cụ tự động vượt mọi quyền private**: việc tạo handle vẫn phải thỏa quy tắc access của Lookup/reflective object, gồm JPMS/module openness khi phù hợp.

Cần chọn **cache key đúng**. Nếu application có nhiều class loaders, hai class cùng binary name **không nhất thiết là cùng class identity**. Cache theo duy nhất `"com.example.Plugin"` có thể gọi nhầm class/loader, giữ references quá lâu hoặc gây lỗi type/reflective access. `Class<?>` identity và module/loader context phải được xét.

Cache cũng cần có **eviction** nếu plugin unload/reload: `Method`, `MethodHandle`, `Lookup` có thể giữ references tới declaring class và class loader, khiến code cũ không được unload. Đối với dynamic runtime systems, chi phí memory/metaspace có thể quan trọng hơn một cải thiện rất nhỏ về call latency.

**Không bắt buộc** biến mọi `Method` thành handle. Nếu plugin action chỉ thực thi hiếm khi, Reflection với metadata cache và error handling rõ ràng có thể là giải pháp hợp lý, dễ debug.

## 17. Kiểm tra chữ ký: từ `Object` sang `MethodType` mà không mất contract

Với Reflection:

```java
Method m = Operation.class.getMethod("compute", int.class);
Object out = m.invoke(real, 3);
int result = ((Integer) out).intValue();
```

Với MethodHandle:

```java
MethodHandle mh = MethodHandles.lookup().findVirtual(
        Operation.class, "compute",
        MethodType.methodType(int.class, int.class));
int result = (int) mh.invokeExact((Operation) real, 3);
```

Hai đoạn là **mã minh họa rời**, cần imports và definitions như mục 10.

Reflection cung cấp `Object` return chung, có thể boxing primitive. Với MethodHandle, chữ ký **có kiểu primitive `int` và receiver `Operation` rõ ràng**; `invokeExact` sẽ không tự boxing hay widening arguments. `invoke` cho phép conversions mà `asType` hỗ trợ, nhưng điều đó không có nghĩa kiểu nào cũng chuyển được.

### Nếu hệ thống dùng generic adapter

Một framework nhận `Object receiver` và `Object[] args` có thể muốn chuẩn hóa handle sang một contract generic thay vì dùng `invokeExact` trực tiếp với type runtime không biết lúc compile. Có thể xem `asType`, `asSpreader`, `asCollector`, `invokeWithArguments` hoặc functional interface wrapper.

Nhưng **mỗi lớp conversion/adaptation** có thể tạo chi phí và khó debug; nếu cuối cùng bạn vẫn boxing mọi thứ vào Object arrays và convert mỗi call, lợi thế mà bạn kỳ vọng từ primitive `MethodHandle` có thể bị triệt tiêu.

Một lựa chọn khác là **tạo mã/adapter có static type rõ** ở giai đoạn setup để consumer gọi bình thường qua interface. Vì thế MethodHandles và functional interfaces **có thể bổ trợ**, không phải thay thế hoàn toàn cho nhau.

## 18. Quyền truy cập và ranh giới module quan trọng hơn vài nano-giây

### 18.1. Direct/interface

Java source compile theo visibility/method signature. Khi chạy trong JPMS, module readability và `exports` vẫn quyết định public API có truy cập được hay không. Đừng sửa thiết kế bằng việc mở private package vô tội vạ chỉ để gọi một method.

### 18.2. Reflection

`getDeclaredMethod` có thể tìm metadata private, nhưng `Method.invoke` chịu access checks, trừ khi suppress checks hợp lệ. `setAccessible(true)`/`trySetAccessible()` bị ràng buộc bởi module access/open packages; code không được tự giả định mọi private field/method đều mở.

### 18.3. MethodHandles.Lookup

`MethodHandles.lookup()` gắn với **class thực tế gọi lookup**. `findVirtual`/`findStatic` thực hiện access checks khi **tạo handle**. Sau khi có handle hợp lệ, bên nhận có thể invoke dù họ không tự đủ quyền để tạo handle tương tự. Vì vậy một private MethodHandle là **capability**, còn full-privilege `Lookup` có thể cấp quyền tạo thêm handles trong phạm vi cho phép.

**Không xuất full lookup qua public API chỉ để gọi một method.** Hãy cấp public interface hoặc một handle đã được kiểm soát. Cần kiểm tra cả `reads`, `exports`, `opens` và điều kiện `privateLookupIn` khi vượt module boundaries; không “vá” bằng các flags `--add-opens` trên production nếu chưa có lý do thiết kế.

### 18.4. Proxy

Proxy có thể kiểm tra quyền ở **entrypoint**:

```java
if (!authorization.canCall(principal, method)) {
    throw new SecurityException("Denied");
}
return method.invoke(target, args);
```

Đây là **mã minh họa**, `principal`, `method`, `target` và `authorization` phải có sẵn. Nó không tự tạo một security boundary vững chắc nếu code khác vẫn giữ `target` raw hoặc target tự gọi method bên trong bằng `this`.

**Proxy không thay thế authorization ở service/domain boundary** khi các đường truy cập khác còn tồn tại. Nếu security decisions thay đổi mỗi request, đảm bảo mọi đường đi cần bảo vệ thực sự chạy qua kiểm tra, không phụ thuộc vào cache/handle/callback đã bypass policy.

## 19. So sánh exception và khả năng chẩn đoán

| Cơ chế | Sai member/không đủ access | Target ném exception | Sai kiểu call-site |
| --- | --- | --- | --- |
| Direct/interface | Compile errors hoặc linkage/access errors theo tình huống | Exception gốc | Đa phần phát hiện lúc compile |
| Functional interface | Không khớp target signature thường lỗi lúc compile | Exception gốc theo SAM contract | Compile-time type checking |
| Reflection | `NoSuchMethodException`, `IllegalAccessException` hoặc JPMS access restrictions | **`InvocationTargetException`** chứa cause | `IllegalArgumentException` với wrong args/receiver, `ClassCastException` khi caller cast kết quả |
| MethodHandle | `NoSuchMethodException`/`IllegalAccessException` khi Lookup tạo handle | Exception gốc truyền qua invocation | **`WrongMethodTypeException`** hoặc conversion-related errors |
| Dynamic proxy | Interface/classloader/proxy creation errors | Handler có thể unwrap hoặc bọc lại | Client type-safe theo interface; handler sai type/return có thể lỗi runtime |

Một số điểm debug thực dụng:

- Không catch mọi `Throwable` rồi nuốt lỗi chỉ vì `MethodHandle.invokeExact` khai báo `throws Throwable`.
- Khi Reflection trả `InvocationTargetException`, **xem `getCause()`** để biết exception nghiệp vụ.
- Với JDK proxy, nếu checked exception không được interface method khai báo, có thể nhận `UndeclaredThrowableException`; tránh làm rò wrapper không cần thiết.
- Với `WrongMethodTypeException`, kiểm tra **`handle.type()` và static types ở call site**, không chỉ actual class của object runtime.
- Với proxy recursion, stack trace có thể lặp `InvocationHandler.invoke → Method.invoke → proxy method` liên tục; kiểm tra receiver `proxy` vs `target`.
- Với nhiều class loaders, lỗi `ClassCastException` dù tên class giống nhau có thể do **khác class identity**.

Cần phân loại rõ lỗi **setup/discovery**, lỗi **invoke/adaptation**, và lỗi **nghiệp vụ thực thi**. Việc đổi công cụ invocation thường làm thay đổi loại wrapper exception mà ứng dụng phải xử lý.

## 20. Trường hợp có nhiều overload hoặc signatures thay đổi

Giả sử class có:

```java
int convert(int input);
int convert(long input);
String convert(String input);
```

Đây là **ba khai báo minh họa** trong một class; không phải một chương trình độc lập.

Khi source code biết static type, `javac` giải quyết overload theo Java overload resolution. Với Reflection, phải chọn **đúng danh sách parameter types** khi gọi `getMethod`/`getDeclaredMethod`, và xử lý return type mong đợi. Với MethodHandles, `MethodType.methodType(returnType, parameters...)` là một phần của lookup contract; sai return type hoặc parameter types có thể làm `findVirtual` ném `NoSuchMethodException`.

**Tránh `getMethods()` rồi lấy method có tên giống đầu tiên**: overload và declaring class khác nhau có thể gây dispatch sai. Nếu config/plugin metadata cung cấp chữ ký runtime, hãy chuẩn hóa **tên + parameter types + return type + access policy**.

Functional interface phù hợp nếu bạn chỉ muốn chọn một implementation cho **một signature cụ thể**; nếu plugin cho phép hành động hoàn toàn khác nhau về số lượng tham số/type, bạn cần một contract generic hoặc registry adapter ở tầng setup.

Proxy tự nhận `Method` object trong handler cho mỗi interface call, nên có thể biết overload bằng signature. Đừng switch theo `method.getName()` duy nhất khi có cùng tên và khác tham số.

## 21. Tình huống thiết kế thường gặp

### 21.1. Strategy đơn giản cho pricing/validation

**Ưu tiên:** functional interface hoặc interface strategy. Callback có kiểu là dữ liệu đủ, không cần reflection/proxy.

```java
IntPredicate validQuantity = count -> count >= 0;
```

Đây là **đoạn minh họa** với import `java.util.function.IntPredicate;`. Nó tránh boxing của `Predicate<Integer>` trên hot path primitive. Nếu strategy cần nhiều methods hoặc trạng thái/lifecycle riêng, dùng interface giàu ý nghĩa.

### 21.2. Annotation-driven validation/serialization

**Ưu tiên:** reflection discovery ở startup, cache mappings. Nếu profile cho thấy invocation trong hot loop là bottleneck, tạo `MethodHandle`/`VarHandle` hoặc accessor để benchmark. Đừng reflection scan mọi field cho mỗi JSON object.

### 21.3. RPC dispatcher nhận tên method từ HTTP/gRPC metadata

**Ưu tiên:** registry xác thực ở startup, rõ allowlist, map operation key sang method/typed handler. Reflection/handles có thể dùng **nội bộ**, nhưng request của người dùng **không nên trở thành tên private method tùy ý**. Validate arguments, authorization và schema trước khi invoke.

### 21.4. Metrics/tracing cho nhiều service methods

**Ưu tiên:** wrapper/decorator hoặc JDK proxy nếu interfaces phù hợp. Nếu backend được gọi không qua proxy, metrics/interceptor không thấy các lời gọi ấy. Với target self-invocation, cũng không tự intercept. Nếu cần can thiệp concrete classes không có interface, có thể cân nhắc bytecode generation/AOP framework có cơ chế riêng, nhưng phải hiểu proxy vs weaving.

### 21.5. Plugin engine tải class bằng tên từ JAR

**Ưu tiên:** contract interface/SPI nếu có thể; reflection khi member discovery phải động; cache handles sau khi xác thực chữ ký. Chọn class loader chính xác, theo dõi references để hỗ trợ unload/reload. Không lưu global strong cache chứa `MethodHandle` tới plugin loader đã retire.

### 21.6. Interpreter/DSL cần đổi cấu trúc lời gọi runtime

**Ưu tiên:** typed handle graph và combinators nếu chúng thực sự đơn giản hóa interpreter và đã được đo. `guardWithTest`, `filterArguments`, `foldArguments`, `asType` có thể tổ hợp, nhưng code có thể khó bảo trì hơn một interpreter loop đơn giản. Profiling quyết định.

### 21.7. Quy trình báo cáo chạy theo lịch, chỉ vài trăm lời gọi/ngày

**Ưu tiên:** giải pháp dễ hiểu nhất. Không cần `MethodHandle` và JMH chỉ để thay một lời gọi public method đã biết. Tối ưu DB queries, retries, error messages và maintainability thường có giá trị hơn.

## 22. Những phản ví dụ thường làm hệ thống phức tạp hoặc chậm hơn

### 22.1. Dùng reflection lookup lại trên từng request

```java
Method m = target.getClass().getMethod("compute", int.class);
return m.invoke(target, value);
```

Đây là **mảnh mã trong một method có return type `Object` và có khai báo exceptions phù hợp**, không chạy độc lập. Nếu signature không đổi, nên resolve/cache `Method` trong setup, thay vì lặp discovery.

### 22.2. Tạo handle và adapter mới cho mỗi phần tử

```java
MethodHandle mh = MethodHandles.lookup().findVirtual(
        Operation.class, "compute",
        MethodType.methodType(int.class, int.class));
return (int) mh.invokeExact((Operation) receiver, value);
```

Đoạn này là **mảnh minh họa**; nó có thể hợp lệ nhưng không nên mặc định lặp lại trong một loop nóng. Hãy cache handle/adapter khi contract ổn định. **Đừng** cache bound handle dài hạn nếu receiver lẽ ra chỉ sống trong một request hoặc tenant.

### 22.3. Dùng `Function<Integer,Integer>` cho hot path primitive mà không đo boxing

```java
Function<Integer, Integer> f = x -> x + 1;
```

Đây là **đoạn minh họa**. Nếu data là `int`, dùng `IntUnaryOperator` có thể tránh một số boxing. Tuy nhiên JIT có thể scalar-replace/eliminate allocations trong một số tình huống; benchmark thực tế vẫn quan trọng.

### 22.4. Proxy tự gọi lại chính proxy

```java
InvocationHandler handler = (proxy, method, args) ->
        method.invoke(proxy, args); // SAI nếu muốn ủy quyền cho target
```

Đây là **phản ví dụ**, không chạy. Nó tái nhập handler và có thể thành đệ quy vô hạn. Hãy dùng target thật, unwrap `InvocationTargetException` và chọn policy rõ ràng cho Object/default methods.

### 22.5. Dùng proxy làm security gate nhưng phát target raw ra ngoài

Nếu code khác có `real` và được phép gọi `real.compute(...)`, nó không qua proxy. Đừng kết luận “mọi lời gọi đã được kiểm tra” chỉ vì caller thông thường được cấp proxy. Thiết kế ranh giới ownership và enforce policy ngay tại đường hành động quan trọng.

### 22.6. Benchmark một lần rồi thay đổi toàn bộ dự án

Một kết quả ngẫu nhiên không đủ loại bỏ lợi ích của interface abstraction, khả năng test và maintainability. Benchmark phải cùng payload, warmed JVM, đủ fork/measurement, không bị dead-code elimination, và có ý nghĩa với latency/throughput thật.

## 23. Checklist lựa chọn và kiểm thử trước khi đưa lên production

1. **Contract:** caller biết method/signature khi compile hay chỉ biết từ config runtime?
2. **Số hành vi:** một callback, nhiều operations, hay mọi method của interface cần interception?
3. **Metadata:** có cần annotations/modifiers/parameters để quyết định không?
4. **Type:** primitive/reference, boxing, overloads và receiver type có đúng không?
5. **Setup:** discovery/proxy/handle được tạo một lần hay mỗi request?
6. **Hot path:** số lần gọi trong vòng đời ứng dụng; call site có monomorphic/polymorphic không?
7. **Error contract:** target exception, reflection wrapper, wrong handle type và checked exceptions xử lý thế nào?
8. **Access:** Java visibility, JPMS module readability/exports/opens, `Lookup` quyền nào, có rò private handle không?
9. **Proxy target:** handler có delegate tới đúng target không; có self-invocation bypass và reentrancy hợp lệ không?
10. **Threading:** shared handler/registry/engine có mutable state hay contention không?
11. **Memory:** callback captures, bound handles, reflective caches và proxy handlers có giữ plugin classloader lâu không?
12. **Measurements:** có JMH/profiler/production load test phù hợp thay vì suy từ JDK docs không?
13. **Observability:** stack traces, tracing spans và metrics có phân biệt dispatch overhead với target work không?
14. **Maintainability:** refactor IDE, compile-time checks, readability, test fixtures và debugging experience.
15. **Fallback:** nếu dynamic member mất hoặc module policy thay đổi, lỗi có actionable và fail-safe không?
16. **Evolution:** đổi method signatures/interface versions có dễ phát hiện trong build hay chờ lỗi runtime?
17. **Security:** có bypass được authorization qua target raw, reflection capability hoặc handle đã phát không?
18. **Benchmark validity:** đã phân tách setup vs steady state và xem allocations/latency tail chưa?

**Mốc quyết định cuối:** nếu direct/interface hoặc callback đáp ứng contract, bắt đầu ở đó. Thêm Reflection, MethodHandles hoặc proxy **theo yêu cầu chức năng thực**; tối ưu sau khi có profile.

## 24. Câu hỏi tự kiểm tra kèm đáp án

1. **Method đã biết ở source và không cần can thiệp, chọn gì trước?** Direct/interface call.
2. **Muốn truyền một phép tính `int -> int` làm callback, chọn gì?** `IntUnaryOperator`/functional interface có type phù hợp.
3. **Muốn duyệt annotation của methods khi runtime, công cụ nào tự nhiên nhất?** Reflection.
4. **Một `MethodHandle` thay thế trực tiếp `getDeclaredMethods()` để liệt kê annotations được không?** Không; nó đại diện invocation đã được tạo, không phải metadata registry.
5. **Vì sao `Method.invoke` dễ có boxing?** API nhận `Object...` và trả `Object`; primitive phải được biểu diễn qua wrappers ở boundary.
6. **Handle của `Operation.compute(int)` có `MethodType` gì?** `(Operation,int)int`, vì instance receiver là tham số đầu.
7. **`invokeExact((Object)real,3)` có hợp lệ với handle trên không?** Không, vì static receiver type không khớp; demo báo `WrongMethodTypeException`.
8. **`bindTo(real)` làm gì?** Gắn receiver, làm handle kiểu `(int)int`.
9. **`Method.invoke` xử lý exception do target ném thế nào?** Bọc trong `InvocationTargetException`; xem `getCause()`.
10. **MethodHandle có tự bọc target exception trong `InvocationTargetException` không?** Không.
11. **JDK Proxy có tự subclass mọi concrete class không?** Không, nó tạo implementations của interfaces.
12. **Tại sao handler không gọi `method.invoke(proxy,args)` khi muốn delegation?** Vì gọi lại proxy và có thể đệ quy vô hạn.
13. **Proxy có thấy lời gọi `this.otherMethod()` trong target không?** Không tự động, đó là self-invocation bypass.
14. **Proxy có tự intercept lời gọi trực tiếp qua `real` reference không?** Không.
15. **`getEngine...` hoặc một API Reflection có thay thế JMH không?** Không; công cụ runtime metadata/discovery không phải hệ thống benchmarking.
16. **Trong ví dụ, vì sao `realCalls=7`?** Có bảy lời gọi nghiệp vụ thành công: direct, interface, functional, reflection, handle, boundHandle, proxy.
17. **Trong ví dụ, vì sao `intercepted=1` rồi `interceptedFinal=2`?** Chỉ các lời gọi thực sự qua proxy vào handler; Object methods không được tính như nghiệp vụ.
18. **Vì sao `realCallsFinal=10` chứ không phải 11?** Ba đường gọi `compute(-1)` chạy target; sai kiểu `invokeExact((Object)real,3)` bị từ chối trước khi target chạy.
19. **Có nên dùng `Function<Integer,Integer>` ở mọi hot primitive pipeline không?** Không mặc định; có thể thử primitive specializations, nhưng đo trước khi kết luận.
20. **`invokedynamic` trong `real::compute` có nghĩa mỗi `applyAsInt` là opcode ấy không?** Không; việc tạo functional object có thể dùng indy, lời gọi SAM là interface invocation.
21. **Vì sao phải cache reflection/handle khi signature ổn định?** Tránh lặp setup/discovery và tăng khả năng JVM thấy đường gọi ổn định, nhưng không bảo đảm thắng trong mọi workload.
22. **Full-privilege `Lookup` có nên đưa cho plugin tùy ý không?** Không; nó có thể trao quyền tạo handles tới members mà plugin không nên được cấp.
23. **Nếu backend trả kết quả sau 100 ms I/O, nên ưu tiên tối ưu gì?** Cân nhắc I/O/DB/network, concurrency và end-to-end latency trước chi phí invocation nhỏ.
24. **JMH có bảo đảm kết quả benchmark là thuộc tính bất biến của Java API không?** Không; kết quả thuộc phiên bản JDK, workload, flags, hardware, shape và môi trường chạy.
25. **Cách kết hợp Reflection và MethodHandle hợp lý?** Reflection khám phá/validate metadata lúc setup, handle được chuẩn hóa và cache cho đường gọi lặp lại nếu đo thấy hợp lý.
26. **Vì sao `Method.invoke` tìm qua `getDeclaredMethod` chưa chắc gọi private thành công?** Access check/JPMS vẫn áp dụng, và suppress checks không luôn được cho phép.
27. **Khi JDK proxy không thể proxy một concrete class thiếu interface, có nên ép cast proxy thành class gốc?** Không; thiết kế interface/decorator hoặc cân nhắc công cụ proxying khác.
28. **Đâu là tiêu chí quan trọng hơn vài ns nếu đường xử lý là nghiệp vụ công ty sống lâu?** Đúng contract, an toàn, maintainability, testability, runtime visibility và dữ liệu đo đáng tin.

## 25. Tài liệu chính thức và công cụ đo

- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): kiểu của method handle, `invokeExact`/`invoke`, invocation checking, access capability, target exceptions.
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVirtual`, `findStatic`, access checking, lookup modes và module boundaries.
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): method descriptor của handle.
- [Java SE 17 — `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): Reflection lookup/invocation, arguments và `InvocationTargetException`.
- [Java SE 17 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): access checks và giới hạn của `setAccessible`/`trySetAccessible`.
- [Java SE 17 — `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): JDK dynamic proxy, interface restrictions và Object methods.
- [Java SE 17 — `InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): tham số proxy/method/args, exception rules và default method invocation.
- [Java SE 17 — `IntUnaryOperator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/IntUnaryOperator.html): specialized functional interface tránh boxing cho `int -> int`.
- [Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): bytecode disassembly để đối chiếu dispatch.
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): cách lập project benchmark, samples, configuration và measurement.

**Kết luận:** **Direct/interface là lựa chọn mặc định**, **functional interface dành cho callback/strategy có kiểu**, **Reflection dành cho khám phá metadata runtime**, **MethodHandle dành cho invocation có kiểu và composition động sau setup**, **dynamic proxy dành cho interception theo interface**. Các cơ chế có thể kết hợp thành một pipeline, nhưng mỗi lớp thêm vào phải giải quyết một nhu cầu cụ thể. **Đúng contract, đúng ranh giới truy cập và khả năng bảo trì đi trước; hiệu năng phải được đo, không được đoán.**