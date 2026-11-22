# Không mặc định một cơ chế luôn nhanh hơn cơ chế còn lại: Reflection, MethodHandle và VarHandle

## 1. Kết luận cần hiểu đúng

Trong Java, `MethodHandle` và `VarHandle` cung cấp cách truy cập thành viên/biến với chữ ký được JVM xử lý trực tiếp, nhưng **không có quy tắc chung** rằng chúng luôn nhanh hơn `Method.invoke` hoặc `Field.get/set` của Core Reflection. Và cũng không thể nói `MethodHandle` luôn nhanh hơn `VarHandle`: chúng **không giải quyết chính xác cùng một bài toán**.

Tốc độ thực tế phụ thuộc đồng thời vào:
- **Thao tác**: gọi method, đọc field, ghi field, truy cập `volatile`, hay `compareAndSet`.
- **Độ ổn định của kiểu và call site**: đối tượng `MethodHandle`, `VarHandle`, `Method`, `Field` có được cache, có ổn định qua mỗi lần gọi, có thể được JIT nhận biết và tối ưu không.
- **Khả năng inline và profile runtime**: call site đơn hình (monomorphic) hay đa hình, lớp receiver và target thay đổi đến đâu.
- **Chi phí chuyển đổi**: boxing/unboxing, mảng `Object[]` cho arguments, chuyển đổi kiểu của `invoke` so với `invokeExact`, adapters như `asType`, `bindTo` và `filterArguments`.
- **Ràng buộc bộ nhớ**: plain/opaque/acquire/release/volatile có semantics và chi phí khác nhau; so sánh khác semantics sẽ sai mục tiêu.
- **Phiên bản JDK/JVM, kiến trúc CPU, tier biên dịch, GC, cấu hình và tải thực tế**.

Một benchmark tốt phải xác định **“nhanh hơn khi làm việc gì, trên runtime nào, với semantics gì?”** trước khi đưa ra quyết định. Ưu tiên tính đúng, quyền truy cập và khả năng bảo trì; dùng dữ liệu hiệu năng đo trên đường chạy quan trọng để cân nhắc đổi cơ chế.

## 2. Chúng làm gì và không thay thế nhau ra sao?

| Cơ chế | Nhiệm vụ phù hợp | Cách gọi đặc trưng | Điều cần lưu ý khi so hiệu năng |
| --- | --- | --- | --- |
| Gọi Java thông thường | Đã biết kiểu/method ở thời điểm biên dịch | `obj.work(arg)` | Mốc so sánh có ích; JIT có thể inline và loại bỏ phần việc không quan sát được. |
| `java.lang.reflect.Method` | Tìm/gọi method linh hoạt từ metadata runtime | `method.invoke(obj, args...)` | Trả về `Object`; có thể boxing/unboxing, xử lý argument và kiểm tra truy cập. |
| `MethodHandle` | Tham chiếu có kiểu tới method/constructor/field, kết hợp thành chuỗi xử lý động | `mh.invokeExact(...)`, `mh.invoke(...)` | Chi phí và khả năng tối ưu phụ thuộc chữ ký, adapter, call site, handle có ổn định hay không. |
| `java.lang.reflect.Field` | Đọc/ghi field qua metadata Reflection | `field.getInt(obj)`, `field.setInt(obj, v)` | Các API primitive như `getInt` giúp tránh boxing do `get` trả `Object`. |
| `VarHandle` | Truy cập biến/field/array với các access mode và memory ordering rõ ràng | `vh.get(obj)`, `vh.set(obj,v)`, `vh.compareAndSet(obj,a,b)` | Phải chọn mode tương đương khi so; `getVolatile` không đồng nghĩa `get`. |

`MethodHandle` có thể đại diện cho **getter/setter** của field, còn `VarHandle` có thể chuyển một access mode thành `MethodHandle` qua `toMethodHandle(...)`. Như vậy có phần giao nhau nhưng `VarHandle` được thiết kế để biểu diễn **nhiều chế độ truy cập biến** và atomic operations, không phải một cơ chế gọi arbitrary method.

Không nên so thời gian của `MethodHandle.invokeExact` để gọi phép cộng với `VarHandle.compareAndSet` để cập nhật biến: hai thao tác tạo ra kết quả và bảo đảm khác nhau. Nếu cần so field read, hãy so `obj.field`, `Field.getInt`, `MethodHandle` getter và `VarHandle.get` cùng một field, trên điều kiện tương đương.

## 3. Điều gì quyết định hiệu năng ở call site?

### 3.1. Lookup khác invocation

`Class.getMethod`, `MethodHandles.Lookup.findVirtual`, `findGetter` và `findVarHandle` dùng để **tìm và kiểm tra khả năng truy cập**. Chi phí lookup không phải chi phí gọi method/đọc field nhiều lần.

- Nếu ứng dụng chỉ thực hiện vài lần truy cập, chi phí khởi tạo/cấu hình một handle có thể quan trọng hơn thời gian gọi.
- Nếu chạy hàng triệu lần, cache `Method`/`Field`/`MethodHandle`/`VarHandle` bên ngoài vòng lặp thường giúp đánh giá đúng hot path.
- Đừng chỉ đặt lookup *bên trong* một phiên bản benchmark còn phiên bản khác đã cache sẵn. Muốn so tổng chi phí khởi tạo + sử dụng thì phải đo **cùng vòng đời** cho tất cả.

### 3.2. JIT optimization và hằng hóa handle

Trong điều kiện JIT nhận diện được target/handle ổn định (ví dụ một trường `static final` hoặc đường truyền dữ liệu đủ rõ), JIT có **cơ hội** inline, chuyên biệt hóa hoặc loại một số bước trung gian. Khi thay target liên tục, lấy từ phần tử mảng hoặc một call site có nhiều loại target, tối ưu hóa có thể khác.

Không được suy luận “`static final` bảo đảm inline” hay “không `final` thì chắc chắn chậm”: đây là kết quả phụ thuộc profile và triển khai JIT. `final` là tín hiệu hữu ích để JVM thấy tham chiếu ổn định, không phải lời hứa về thứ hạng hiệu năng.

### 3.3. `invokeExact`, `invoke` và adapters

- `MethodHandle.invokeExact` đòi hỏi **chữ ký tại call site khớp chính xác** với `MethodHandle.type()`, gồm kiểu tham số **và kiểu trả về**. Sai kiểu có thể gây `WrongMethodTypeException`.
- `MethodHandle.invoke` cho phép một số chuyển đổi kiểu như `asType`. JVM có thể tối ưu các chuyển đổi nếu đủ thông tin, nhưng adaptation cũng có thể tạo thêm công việc.
- `invokeWithArguments` thuận tiện với tham số động dạng `Object[]`/`List<?>`, không đại diện cho cùng cách gọi tối ưu như `invokeExact` cố định chữ ký.
- `VarHandle` có các access mode dạng signature-polymorphic; `withInvokeExactBehavior()` yêu cầu đối chiếu chữ ký chính xác, còn dạng mặc định có thể cho phép điều chỉnh tương đương `invoke` theo quy tắc API.

Khi benchmark, ghi chính xác variant được dùng và kiểu tại call site. Đổi `invokeExact` sang `invokeWithArguments` rồi quy chụp toàn bộ `MethodHandle` là kết luận không hợp lệ.

### 3.4. Core Reflection thay đổi qua các bản Java

Từ **JDK 18**, [JEP 416](https://openjdk.org/jeps/416) tái triển khai phần lõi Core Reflection (`Method`, `Constructor`, `Field`) dựa trên method handles. Điều này **không** có nghĩa `Method.invoke` và `MethodHandle.invokeExact` là cùng một public API hay có overhead giống hệt nhau. Nhưng nó cho thấy cách tổ chức runtime thay đổi: những so sánh dựa trên cơ chế Reflection cũ không tự áp dụng cho JDK mới.

JEP 416 cũng nêu benchmark cho thấy hiệu năng thay đổi **theo mẫu giữ tham chiếu** (hằng, biến, truy cập mảng...) và theo loại thao tác. Những con số trong một đề xuất JDK chỉ mô tả môi trường và workload của phép đo đó; không phải một tỷ lệ tăng tốc cố định cho ứng dụng khác. **Không suy diễn từ benchmark của một phiên bản sang mọi JDK.**

## 4. Ví dụ Java 17+ chạy được: giống kết quả, chưa nói ai nhanh hơn

Lưu toàn bộ chương trình sau thành **`AccessChoicesDemo.java`**. Nó dùng cùng một phương thức `add(int)` và cùng một field `value` để kiểm chứng kết quả tương đương trước khi bàn tới hiệu năng.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class AccessChoicesDemo {
    public static final class Counter {
        public int value = 2;

        public int add(int delta) {
            return value + delta;
        }
    }

    public static void main(String[] args) throws Throwable {
        Counter counter = new Counter();
        Method reflectedAdd = Counter.class.getMethod("add", int.class);
        Field reflectedValue = Counter.class.getField("value");

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle addHandle = lookup.findVirtual(
                Counter.class, "add", MethodType.methodType(int.class, int.class));
        MethodHandle getterHandle = lookup.findGetter(
                Counter.class, "value", int.class);
        VarHandle valueHandle = lookup.findVarHandle(
                Counter.class, "value", int.class);

        System.out.println("Direct call: " + counter.add(3));
        System.out.println("Method.invoke: " + reflectedAdd.invoke(counter, 3));
        System.out.println("MethodHandle.invokeExact: "
                + (int) addHandle.invokeExact(counter, 3));

        System.out.println("Direct field read: " + counter.value);
        System.out.println("Field.getInt: " + reflectedValue.getInt(counter));
        System.out.println("MethodHandle field getter: "
                + (int) getterHandle.invokeExact(counter));
        System.out.println("VarHandle.get: " + (int) valueHandle.get(counter));

        System.out.println("VarHandle.compareAndSet: "
                + valueHandle.compareAndSet(counter, 2, 9));
        System.out.println("Field after CAS: " + reflectedValue.getInt(counter));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 AccessChoicesDemo.java
java AccessChoicesDemo
```

Kết quả đã được kiểm tra thực tế bằng JDK 24 với mã biên dịch ở mức Java 17:

```text
Direct call: 5
Method.invoke: 5
MethodHandle.invokeExact: 5
Direct field read: 2
Field.getInt: 2
MethodHandle field getter: 2
VarHandle.get: 2
VarHandle.compareAndSet: true
Field after CAS: 9
```

Phân tích:

1. Ba cách gọi `add(3)` đều trả `5`. `Method.invoke` trả `Object` nên khi nối chuỗi sẽ thấy giá trị từ một `Integer` đã được boxing; `invokeExact` ở đây trả nguyên thủy `int` đúng `MethodType`.
2. Bốn cách đọc field đọc cùng giá trị `2`. `Field.getInt` và `MethodHandle` getter là lựa chọn trực tiếp để so **plain read** với `VarHandle.get`. `MethodHandle getter` có chữ ký tương đương `(Counter)int`.
3. `compareAndSet` thực hiện một thao tác **nguyên tử** kiểm tra `2` rồi đổi sang `9`; đây là tính năng khác với plain field read và không nên đưa chung vào phép đo “chi phí đọc”.
4. Tất cả lookup được thực hiện trước phần gọi; **chương trình là kiểm tra correctness chứ không phải benchmark tốc độ**. Thêm `System.nanoTime()` quanh từng dòng này sẽ không cho ra bảng xếp hạng có giá trị.

Ví dụ dùng thành viên `public` để không cần `setAccessible(true)`. Với private member, quyền truy cập của `MethodHandles.Lookup` và Reflection phải được cấu hình theo module/package tương ứng; đừng đem một bản thất bại vì thiếu quyền so với một bản đã mở quyền.

## 5. Memory semantics: so cùng công việc rồi mới so thời gian

`VarHandle` có các kiểu thao tác phân biệt rõ:
- `get` / `set`: truy cập **plain** (ngữ nghĩa đọc/ghi thông thường, không tự thêm cam kết đồng bộ của `volatile`).
- `getOpaque` / `setOpaque`: opaque access; cung cấp ràng buộc thứ tự yếu hơn acquire/release/volatile.
- `getAcquire` / `setRelease`: acquire/release ordering, phù hợp một số giao thức publication/consumption.
- `getVolatile` / `setVolatile`: semantics tương tự đọc/ghi `volatile`.
- `compareAndSet`, `compareAndExchange`, `getAndAdd`...: các primitive nguyên tử hoặc read-modify-write khi access mode và kiểu biến hỗ trợ.

`Field.getInt` trên field thông thường và `VarHandle.get` cùng field là cặp hợp lý để bắt đầu so **đọc plain**. Trên field khai báo `volatile`, hãy phân tích lại semantics rồi mới chọn API/mode; đừng so plain read với volatile read và cho rằng phần nhanh hơn vẫn giải quyết được điều kiện đồng bộ. `VarHandle` cũng không tự biến một thuật toán có data race thành an toàn: phải chọn memory ordering/atomicity phù hợp và thiết kế protocol chính xác.

Không phải mọi access mode đều có trên mọi loại biến (ví dụ các thao tác ghi/atomic trên field `final` có hạn chế). Kiểm tra `isAccessModeSupported` và hợp đồng `VarHandle` khi cần thao tác chuyên biệt.

## 6. Đo đúng: JMH, warmup, forks và kiểm soát sai lệch

### 6.1. Vì sao một vòng lặp với `nanoTime` chưa đủ?

Nếu viết:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    handle.invokeExact(counter, 3); // chú ý kiểu trả về!
}
long elapsed = System.nanoTime() - start;
```

đoạn minh họa này **không phải một chương trình benchmark đúng**: lời gọi `invokeExact` dưới dạng statement có kiểu trả về `void` tại call site trong khi handle ví dụ trả `int`, nên có thể ném `WrongMethodTypeException`. Ngay cả khi ép kiểu/tiêu thụ kết quả đúng, phép đo vẫn có vấn đề như JIT chưa nóng, code bị tối ưu bỏ, phép đo bị nhiễu từ hệ điều hành/GC hoặc thuật toán đang thực hiện các tác vụ không tương đương.

Sửa tối thiểu cho mặt chữ ký là:

```java
int result = (int) addHandle.invokeExact(counter, 3);
```

nhưng một lần đo bằng `nanoTime` vẫn **không** thay thế benchmark có thiết kế nghiêm túc.

### 6.2. Cách tổ chức benchmark với JMH

[JMH (Java Microbenchmark Harness)](https://github.com/openjdk/jmh) là bộ công cụ chuyên dụng của OpenJDK cho microbenchmark JVM. Khi cần quyết định tối ưu trên hot path:

1. **Định nghĩa cùng semantics** và các cặp so sánh: (a) gọi method trực tiếp / `Method.invoke` / `MethodHandle.invokeExact`; (b) field direct read / `Field.getInt` / getter `MethodHandle` / `VarHandle.get`. Đo riêng CAS/volatile operations.
2. **Chuyển lookup ra pha setup** khi đo invocation ổn định, và tạo benchmark **khác** nếu nghiệp vụ cần đo cả setup + sử dụng một lần.
3. **Thiết lập warmup, nhiều measurement iterations và nhiều forks**. Ghi JDK vendor/version, JVM flags, CPU/OS, môi trường tải, GC và JMH version.
4. **Tiêu thụ kết quả** (trả về từ `@Benchmark` hoặc dùng `Blackhole`), cung cấp đầu vào thay đổi đúng nhu cầu và tránh dead-code elimination/constant folding làm workload biến mất. Không in console trong phương thức benchmark.
5. **Đảm bảo cùng mức đa hình**: một target cố định không thể đem so trực tiếp với target chọn ngẫu nhiên trong từng iteration.
6. **Xem phân phối kết quả và độ bất định**, độ ổn định giữa forks và profiling. Nếu chênh lệch nhỏ so với nhiễu hoặc không làm thay đổi bottleneck ứng dụng, không có cơ sở để thay API.

Mẫu *phác thảo cấu trúc*, cần đặt trong class benchmark có các field `MethodHandle addHandle`, `Method reflectedAdd`, `Counter counter` và phụ thuộc JMH; **không phải file Java độc lập**:

```java
@Benchmark
public int direct() {
    return counter.add(3);
}

@Benchmark
public int viaReflection() throws ReflectiveOperationException {
    return (Integer) reflectedAdd.invoke(counter, 3);
}

@Benchmark
public int viaHandle() throws Throwable {
    return (int) addHandle.invokeExact(counter, 3);
}
```

Trước khi chạy mẫu này cần khai báo đầy đủ `@State`, setup handle/method/receiver, import `org.openjdk.jmh.annotations.Benchmark` và cấu hình JMH cùng annotation processor trong công cụ build. Hãy biến `Counter` thành workload có trạng thái/đầu vào phù hợp, để phép tính thật không bị JIT chứng minh là hằng số. **Không tự điền “ns/op dự kiến”**: con số phải xuất phát từ phép đo cụ thể và có thông tin hệ thống đi kèm.

### 6.3. Bảng kiểm soát phép đo

| Câu hỏi | Nếu bỏ qua thì sao? |
| --- | --- |
| Lookup/cache giống nhau? | Đang đo thêm setup bên này nhưng không đo bên kia. |
| Chữ ký và chuyển đổi tương đương? | Đang đo overhead boxing/adapters khác nhau mà không nói rõ. |
| Thao tác field cùng memory ordering? | Đang so hai semantics khác nhau. |
| Input, target, số kiểu receiver giống nhau? | Profile JIT không thể so được. |
| Warmup/forks và trạng thái hệ thống hợp lý? | Số liệu ngẫu nhiên, nhiễu hoặc chủ yếu đo JIT startup. |
| Return value được tiêu thụ và có side effect thật? | JIT có thể loại hoàn toàn công việc. |
| Chạy trên JDK/CPU tương ứng sản phẩm? | Kết quả thí nghiệm không đại diện deployment. |
| Hiệu năng end-to-end có cải thiện không? | Tối ưu microbenchmark có thể không đem lợi ích thực tế. |

## 7. Tình huống chọn API dựa trên yêu cầu thực tế

**Framework discovery/plugin/serialization:** Nếu phải khám phá lớp/phương thức theo tên ở runtime và số lượt gọi ít, Core Reflection thường là lựa chọn đơn giản và dễ diễn đạt. Khi một thành viên được gọi cực nhiều lần với chữ ký ổn định, có thể thử cache `MethodHandle` rồi **đo** lợi ích; kết quả còn phụ thuộc JDK và call site.

**Cơ chế gọi hàm động với phép biến đổi chữ ký:** `MethodHandle` là lựa chọn có API thích hợp cho composition (`asType`, `bindTo`, `filterArguments`...), dù mỗi adapter có thể ảnh hưởng tối ưu hóa. Nếu phải tạo adapter một lần và dùng lặp lại, hãy đo mô hình đó thay vì xây lại chuỗi adapter mỗi invocation.

**Truy cập field với concurrency protocol:** Chọn `VarHandle` khi cần `getAcquire`/`setRelease`/`compareAndSet` hoặc các memory access mode rõ ràng, bởi vì **đúng semantics** là điều kiện bắt buộc. Sau đó tối ưu trong phạm vi các cách cài đặt cùng bảo đảm. Không thay một CAS nguyên tử bằng plain write chỉ để giảm thời gian benchmark.

**Mã thông thường biết kiểu tại compile time:** Gọi trực tiếp hoặc dùng cấu trúc Java chuẩn thường dễ hiểu và là mốc so sánh đầu tiên. Không có lý do mặc định chuyển mọi getter thành `MethodHandle`/`VarHandle` với hy vọng tăng tốc.

**Sau khi nâng JDK:** Đo lại nếu đây là điểm nóng quan trọng. JIT, implementation của Reflection, memory barriers và optimization thay đổi giữa các bản runtime. “Năm trước framework A nhanh hơn B” không phải hợp đồng hiệu năng.

## 8. Những kết luận sai phổ biến

| Nhận định sai | Diễn giải đúng |
| --- | --- |
| “`MethodHandle` luôn nhanh hơn Reflection.” | Khả năng JIT tối ưu và chi phí phụ thuộc loại thao tác, dạng handle, call site và phiên bản JDK. |
| “`VarHandle` luôn nhanh hơn `MethodHandle`.” | Chúng khác vai trò; chỉ so khi thực hiện đúng cùng field operation và cùng semantics. |
| “`invokeExact` luôn nhanh hơn `invoke`.” | `invokeExact` tránh nhu cầu adaptation về mặt semantics, nhưng runtime có thể tối ưu `invoke` trong trường hợp thích hợp; phải đo workload cụ thể. |
| “Đo `Field.get` rồi so `VarHandle.get` là hoàn toàn công bằng.” | `Field.get` có thể boxing primitive; cân nhắc `Field.getInt` nếu mục tiêu là plain int read. |
| “Một lần `nanoTime` đủ để kết luận.” | Cần warmup, forks, kiểm soát nhiễu và chống tối ưu mất công việc. |
| “JDK 18 dùng MethodHandle triển khai Reflection nên hai API có tốc độ bằng nhau.” | Chung một phần cơ chế bên trong không xóa khác biệt API, caller shape và overhead. |
| “CAS chậm hơn plain set nên dùng plain set cho đồng bộ.” | CAS bảo đảm atomicity khác plain store; phải giữ đúng yêu cầu đồng bộ. |
| “Kết quả benchmark vượt trội nghĩa là ứng dụng chắc chắn nhanh hơn.” | Bottleneck có thể nằm ở I/O, allocation, locks, GC hoặc thuật toán; cần đo end-to-end. |

## 9. Câu hỏi tự kiểm tra

1. Khi so thời gian `Method.invoke` và `MethodHandle.invokeExact` gọi cùng method, tại sao phải đưa bước tìm `Method`/`MethodHandle` ra ngoài benchmark hoặc đo riêng?
2. Khi đọc `int field`, vì sao `Field.getInt` là đối chứng hữu ích hơn `Field.get` đối với `VarHandle.get`?
3. `MethodHandle.invokeExact` trả `int`. Việc gọi như một statement `mh.invokeExact(...)` không ép kiểu trả về có thể tạo vấn đề gì?
4. Nếu biến chỉ có thể được cập nhật an toàn bằng `compareAndSet`, có hợp lệ dùng `VarHandle.set` làm đối chứng trực tiếp về tốc độ không?
5. Vì sao `static final MethodHandle` có thể giúp JIT nhưng không bảo đảm nhanh hơn một `Method` được cache?
6. Sau khi nâng từ JDK 17 lên JDK mới, vì sao các con số microbenchmark cũ phải được đánh giá lại?

**Nguyên tắc áp dụng:** Chọn API theo thao tác và semantics; thử một bản triển khai đúng; cache hợp lý; dùng benchmark tái lập trên runtime thực và kiểm tra ảnh hưởng end-to-end. Nếu chưa có số liệu đáng tin, **không khẳng định bất kỳ cơ chế nào luôn thắng**.

## 10. Nguồn tham khảo chính thức

- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `invoke`, adaptation và quy tắc kiểm tra kiểu.
- [Java SE 17 — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): các access mode, memory ordering và kiểu lời gọi.
- [Java SE 17 — `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `invoke` và hợp đồng Core Reflection.
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi từ JDK 18 cùng kết quả đo theo từng pattern.
- [OpenJDK JMH](https://github.com/openjdk/jmh): harness cho JVM microbenchmark, cách dựng benchmark và công cụ chạy.
