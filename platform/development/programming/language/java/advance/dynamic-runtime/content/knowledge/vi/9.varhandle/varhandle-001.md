# 9.1 Vai trò của `VarHandle` và khác biệt với `Field` hoặc `MethodHandle`

Trong Java 9+, `java.lang.invoke.VarHandle` là một đối tượng mô tả **cách truy cập một biến có kiểu cụ thể**, chẳng hạn một instance field, static field, phần tử mảng hoặc vị trí dữ liệu trong các cấu trúc được hỗ trợ. Nó không chỉ cho phép `get`/`set`, mà còn cung cấp những **access modes** tường minh: plain, opaque, acquire, release, volatile và các phép cập nhật nguyên tử như compare-and-set hoặc get-and-add.

`VarHandle` đặc biệt hữu ích khi viết thư viện, runtime, cấu trúc dữ liệu đồng thời, bộ lập trình framework hoặc công cụ cần truy cập biến động nhưng vẫn tuân theo **Java Memory Model (JMM)**. Tuy nhiên, nó không phải sự thay thế mặc định cho mọi getter/setter, cũng không phải “Reflection nhanh hơn” với quyền truy cập không giới hạn.

**Phân biệt ngắn gọn:**

- **`java.lang.reflect.Field`:** metadata và thao tác đọc/ghi **một field đã được phản chiếu**, cùng thông tin modifier, annotation, declaring class; thuận tiện cho khảo sát cấu trúc lớp.
- **`java.lang.invoke.MethodHandle`:** tham chiếu có kiểu đến **một thao tác có thể gọi**: method, constructor, field getter/setter, adapter hoặc tổ hợp các thao tác. Nó mô tả một hành động qua `MethodType`, không mặc nhiên đem tới cả bộ memory access modes.
- **`java.lang.invoke.VarHandle`:** tham chiếu có kiểu đến **một biến hoặc họ vị trí biến**. Cùng một handle có thể được gọi với nhiều **access modes** như `getAcquire`, `setRelease`, `compareAndSet`, `getAndAdd`, nếu biến và chế độ đó được hỗ trợ.

Bài này giải thích vai trò, cơ chế tạo và sử dụng `VarHandle`, so sánh với `Field`/`MethodHandle`, lựa chọn đúng công cụ, giới hạn quyền truy cập và các sai lầm thường gặp. Ví dụ tương thích **Java 17+** và các chương trình hoàn chỉnh bên dưới có lệnh biên dịch/chạy cùng stdout kiểm chứng.

## 1. Vì sao Java có VarHandle?

Giả sử lớp có biến:

```java
class Counter {
    int value;
}
```

Nếu chỉ làm việc trong một class bình thường, Java source có thể đọc/ghi trực tiếp: `counter.value`, `counter.value = 5`. Với biến chia sẻ giữa các luồng, yêu cầu lại khác: phải phân biệt một phép đọc plain với đọc volatile, hoặc thay đổi `value` bằng một thao tác **nguyên tử** tránh lost update.

Để cập nhật `value` đồng thời, code dạng sau **không** đủ:

```java
// Minh họa trong nơi có quyền truy cập field:
counter.value = counter.value + 1;
```

Nó gồm **đọc, tính toán rồi ghi**. Hai thread có thể cùng đọc giá trị cũ và ghi trùng giá trị mới. Biến có khai báo `volatile` cũng không tự biến phép cộng trên thành atomic read-modify-write.

`VarHandle` cho phép biểu đạt rõ ý đồ:

```java
// Đoạn minh họa: VALUE là VarHandle trỏ tới field int value của Counter.
int previous = (int) VALUE.getAndAdd(counter, 1);
```

`getAndAdd` thực hiện cập nhật nguyên tử với độ ngữ nghĩa bộ nhớ được API định nghĩa và trả về **giá trị trước khi cộng**. Cùng `VALUE` đó có thể được dùng cho `get`, `set`, `getVolatile`, `setRelease`, `compareAndSet`, tùy `AccessMode` được hỗ trợ.

**Điểm nổi bật:** VarHandle gom **địa chỉ logic của biến** với các **cách truy cập có ngữ nghĩa bộ nhớ khác nhau**; không bắt bạn tạo một object wrapper mới cho mỗi instance field.

## 2. Mô hình biến: variable type và coordinate types

Một `VarHandle` có hai thành phần quan trọng:

1. **Variable type (`T`)** — kiểu giá trị được lưu, ví dụ `int`, `long`, `String`, `Object`.
2. **Coordinate types (`CT1...CTn`)** — các đối số xác định **biến cụ thể nào** đang được truy cập. Chúng không phải giá trị mới sẽ ghi; chúng là “tọa độ” của vị trí dữ liệu.

Đọc metadata bằng:

```java
Class<?> variableType = handle.varType();
java.util.List<Class<?>> coordinates = handle.coordinateTypes();
```

Đây là **đoạn minh họa** với biến `handle` kiểu `VarHandle` đã được tạo.

| Biến đích | Cách tạo điển hình | `varType()` | `coordinateTypes()` | Cách gọi |
| --- | --- | --- | --- | --- |
| Instance field `int Cell.value` | `lookup.findVarHandle(Cell.class, "value", int.class)` | `int` | `[Cell.class]` | `(int) vh.get(cell)` |
| Static field `int Config.level` | `lookup.findStaticVarHandle(Config.class, "level", int.class)` | `int` | `[]` | `(int) vh.get()` |
| Phần tử `int[]` | `MethodHandles.arrayElementVarHandle(int[].class)` | `int` | `[int[].class, int.class]` | `(int) vh.get(array, index)` |
| Byte-array/ByteBuffer view (kiểu số hợp lệ) | `byteArrayViewVarHandle` / `byteBufferViewVarHandle` | Kiểu thành phần của view | Array/buffer và vị trí truy cập | Có ràng buộc byte order và alignment |

Ví dụ instance field: `vh.get(cell1)` và `vh.get(cell2)` cùng dùng **một handle**, nhưng tọa độ `cell1`/`cell2` chọn hai biến khác nhau. Với mảng: `vh.get(numbers, 0)` và `vh.get(numbers, 1)` chọn hai phần tử khác nhau. Với static field, không có receiver nên **không có coordinate argument**.

Không nên hiểu `VarHandle` như một `Field` giữ sẵn object instance. Nó thường mô tả một vị trí **tham số hóa bằng tọa độ**, rồi mỗi lần truy cập caller cung cấp receiver hoặc index.

### 2.1. MethodType của một access mode

Mỗi access mode có một chữ ký riêng; `VarHandle.accessModeType(VarHandle.AccessMode.GET)` trả về `MethodType` cho mode `get` của handle đó. Với `int Cell.value`:

| Access mode | Các argument | Kiểu kết quả | Ví dụ chữ ký |
| --- | --- | --- | --- |
| `get` | `Cell` | `int` | `(Cell)int` |
| `set` | `Cell, int newValue` | `void` | `(Cell,int)void` |
| `getVolatile` | `Cell` | `int` | `(Cell)int` |
| `compareAndSet` | `Cell, int expected, int replacement` | `boolean` | `(Cell,int,int)boolean` |
| `compareAndExchange` | `Cell, int expected, int replacement` | `int` (witness) | `(Cell,int,int)int` |
| `getAndAdd` | `Cell, int delta` | `int` (giá trị cũ) | `(Cell,int)int` |

Các method trên `VarHandle` được khai báo trong Java API dưới dạng **signature polymorphic**: chữ ký tại *call site* được kiểm tra động dựa trên handle và access mode. Với kiểu primitive, viết cast kết quả rõ ràng để caller biểu diễn kiểu mong muốn, ví dụ `(int) vh.get(cell)`; không giả định vì khai báo API nhìn giống `Object get(Object...)` mà kết quả thực tế luôn là `Object`.

**Chi tiết quan trọng của Java 17:** `VarHandle` mới tạo thường có **invoke behavior** cho phép các conversion tương thích như `MethodHandle.invoke`. Gọi `vh.withInvokeExactBehavior()` tạo một handle tham chiếu cùng biến nhưng yêu cầu **khớp chính xác** access-mode `MethodType` giống tinh thần `MethodHandle.invokeExact`. Không nên khẳng định mọi `VarHandle.get(...)` mặc định đều cấm tất cả conversions; việc này phụ thuộc invocation behavior.

## 3. Tạo VarHandle đúng cách

Những factory API được sử dụng phổ biến:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

// Instance field của một lớp:
VarHandle instanceField =
        lookup.findVarHandle(Example.class, "count", int.class);

// Static field của một lớp:
VarHandle staticField =
        lookup.findStaticVarHandle(Example.class, "global", int.class);

// Phần tử mảng:
VarHandle arrayElement =
        MethodHandles.arrayElementVarHandle(int[].class);
```

**Đoạn code minh họa**, giả sử `Example` có đúng những fields với kiểu `int`, các static modifier tương ứng và caller có quyền lookup; cần import `java.lang.invoke.*` hoặc các lớp riêng, xử lý `NoSuchFieldException`/`IllegalAccessException`.

`findVarHandle` nhận **field type chính xác**, không phải kiểu thuận tiện để tự chuyển đổi. Nếu field khai báo `long` mà bạn truyền `int.class`, lookup có thể báo `NoSuchFieldException`. Tương tự `findStaticVarHandle` không thay cho `findVarHandle` nếu field thực tế không static.

Một cách giữ handle ổn định là tạo trong static initializer, nơi lookup diễn ra **một lần**:

```java
private static final VarHandle VALUE;

static {
    try {
        VALUE = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
    } catch (ReflectiveOperationException e) {
        throw new ExceptionInInitializerError(e);
    }
}
```

Đây là **đoạn khai báo bên trong class** có field `Counter.value`, không phải chương trình độc lập. Việc dùng `static final` cho tham chiếu VarHandle ngăn vô tình thay thế handle ở các đoạn code khác; **không** làm biến đích trở thành `final`, cũng **không** tự khiến mọi thao tác với biến đích có memory semantics volatile.

### 3.1. Quyền truy cập ở bước tạo handle

`MethodHandles.Lookup` mang quyền của caller. Để tìm private field, caller cần quyền truy cập thực sự theo Java/JPMS. Code trong chính declaring class hoặc cùng nest thường có thể dùng `MethodHandles.lookup()`; code ở lớp/module khác có thể cần `MethodHandles.privateLookupIn(targetClass, lookup)`, nhưng chỉ khi các điều kiện module/access được đáp ứng.

- `getDeclaredField(...)` của Core Reflection tìm metadata mà chưa chứng minh quyền đọc/ghi.
- `lookup.findVarHandle(...)` kiểm tra quyền **khi tạo handle** và có thể ném `IllegalAccessException`.
- Khi handle truy cập private field đã được tạo hợp lệ, ai **nhận được handle đó** có thể sử dụng capability tương ứng mà không trải qua lại phép kiểm tra quyền private field như `Field.get`. Vì vậy **không phát tán VarHandle tới code không tin cậy**.
- `privateLookupIn` không bypass JPMS: package của module khác có thể cần `opens` cho module caller; không tự động gọi `--add-opens` hay yêu cầu blanket access.

Khác với quan niệm “Reflection là đọc được mọi thứ”, cả Core Reflection lẫn Method Handles đều bị điều chỉnh bởi Java access control và module boundaries.

## 4. Ví dụ đầy đủ 1: instance field và cập nhật nguyên tử

Tạo **`VarHandleIntroDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleIntroDemo {
    private static final class Cell {
        private int value = 5;
    }

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Cell.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) {
        Cell cell = new Cell();
        System.out.println("variable type: " + VALUE.varType().getSimpleName());
        System.out.println("coordinate count: " + VALUE.coordinateTypes().size());
        System.out.println("get access type: "
                + VALUE.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("initial: " + (int) VALUE.get(cell));
        VALUE.set(cell, 8);
        System.out.println("after set: " + (int) VALUE.get(cell));

        boolean first = VALUE.compareAndSet(cell, 8, 13);
        boolean second = VALUE.compareAndSet(cell, 8, 99);
        System.out.println("CAS first: " + first);
        System.out.println("CAS second: " + second);

        int old = (int) VALUE.getAndAdd(cell, 4);
        System.out.println("getAndAdd old: " + old);
        System.out.println("final: " + (int) VALUE.getVolatile(cell));
        System.out.println("CAS supported: "
                + VALUE.isAccessModeSupported(VarHandle.AccessMode.COMPARE_AND_SET));
    }
}
```

Lệnh chạy Java 17+:

```bash
javac --release 17 VarHandleIntroDemo.java
java VarHandleIntroDemo
```

**Stdout đã kiểm tra bằng cách biên dịch và chạy:**

```text
variable type: int
coordinate count: 1
get access type: (Cell)int
initial: 5
after set: 8
CAS first: true
CAS second: false
getAndAdd old: 13
final: 17
CAS supported: true
```

Phân tích:

1. `Cell.value` là private instance field kiểu `int`; static initializer tra handle trong **nest** bao gồm `VarHandleIntroDemo` và nested class `Cell`, nên lookup có quyền.
2. `varType()` là `int`; `coordinateTypes().size()` là `1` vì phải truyền một `Cell` instance.
3. `get(cell)` đọc `5`. `set(cell,8)` ghi `8`; trong chương trình một thread, đây là hai thao tác hợp lệ.
4. `compareAndSet(cell,8,13)` cập nhật vì giá trị hiện tại đúng `8`, trả `true`.
5. Lần `compareAndSet(cell,8,99)` sau đó thấy giá trị hiện tại đã là `13`, nên trả `false`, không đổi biến.
6. `getAndAdd(cell,4)` tăng nguyên tử từ `13` lên `17` và trả **giá trị trước khi cộng** là `13`.
7. `getVolatile(cell)` đọc theo volatile mode; chương trình có thể chọn ngữ nghĩa này ngay tại access site dù field nguồn không khai báo `volatile`.
8. `isAccessModeSupported(COMPARE_AND_SET)` trả `true` đối với field `int` ghi được trong ví dụ.

`compareAndSet` là một atomic read-modify-write operation, không tương đương với đoạn `if (get() == expected) set(newValue)`. Đoạn tách đôi có thể bị thread khác chen vào giữa hai thao tác.

## 5. So sánh tổng quát: `Field`, `MethodHandle`, `VarHandle`

| Tiêu chí | `Field` | `MethodHandle` | `VarHandle` |
| --- | --- | --- | --- |
| Bản chất | Metadata của field cụ thể | Handle có kiểu cho **thao tác có thể gọi** | Handle có kiểu cho **vị trí biến/họ vị trí biến** |
| Thuộc API | `java.lang.reflect` | `java.lang.invoke` | `java.lang.invoke` |
| Cách lấy | `Class.getField/getDeclaredField` | `Lookup.findStatic/findVirtual/findGetter/findSetter/...` | `Lookup.findVarHandle/findStaticVarHandle`, factories cho array/view |
| Tra cứu / diễn giải kiểu | `getType()`, `getGenericType()`, annotations, modifiers | `type(): MethodType` | `varType()`, `coordinateTypes()`, `accessModeType(...)` |
| Hoạt động chính | `get/getInt/set/setInt`, khảo sát metadata | `invokeExact/invoke`, tổ hợp adapters | `get/set/getVolatile/getAcquire/setRelease/CAS/getAndAdd/...` |
| Đối tượng nhận | Receiver object khi field instance, `null` cho static | Arguments theo `MethodType`, có thể gồm receiver | Coordinate arguments theo vị trí biến: receiver/index/không có |
| Memory ordering | Gắn với ngữ nghĩa truy cập field và modifiers; không có danh sách mode tùy chọn trên từng lời gọi | Phụ thuộc thao tác target mà handle biểu diễn | **Chọn access mode tại mỗi lời gọi**, nếu được hỗ trợ |
| Atomic compare-and-set | Không có API CAS trực tiếp trên `Field` | Có thể bọc/gọi thao tác CAS khác nếu tạo handle tới nó | **Được định nghĩa trực tiếp** qua `compareAndSet` và related modes |
| Xử lý exception truy cập | Có thể `IllegalAccessException` khi đọc/ghi; có thể `setAccessible` theo giới hạn module | Lookup có thể ném `IllegalAccessException`; gọi target qua MethodHandle theo chữ ký đã tạo | Lookup có thể ném `IllegalAccessException`; access modes kiểm tra kiểu/hỗ trợ mode |
| Khả năng khảo sát annotation/modifier | **Rất phù hợp** | Không phải mục đích chính | Không phải mục đích chính |
| Trường hợp tiêu biểu | Serializer schema discovery, inspection, tooling | Dynamic method invocation, adapters, runtime dispatch | Truy cập state, coordination, atomics, concurrency primitives |

**Hai điểm cần tránh hiểu sai:**

1. `MethodHandle` **cũng có thể đại diện cho field getter/setter**: `Lookup.findGetter`, `findSetter` hoặc `VarHandle.toMethodHandle(AccessMode.GET)` trả một MethodHandle tương ứng. Vì vậy không đúng nếu nói MethodHandle “chỉ gọi method, không đụng được field”. Điểm khác là `VarHandle` liên kết **nhiều memory access modes vào cùng một biến**.
2. `Field.get/set` vẫn có Java Memory Model semantics phù hợp với field được khai báo `volatile`; không nên khẳng định Reflection “không có volatile”. Khác biệt là Core Reflection **không cho chọn plain/opaque/acquire/release/volatile riêng trên cùng một Field API call** như VarHandle.

`Field` thường dễ dùng khi cần khám phá metadata rồi đọc/ghi cấu hình hoặc object-mapping đơn giản. `MethodHandle` phù hợp với một lời gọi động có chữ ký và adapters cụ thể. `VarHandle` là công cụ đúng khi **biến** và **ngữ nghĩa truy cập biến** mới là trọng tâm.

### 5.1. Hiệu năng không phải một cam kết tuyệt đối

Không khẳng định `VarHandle` luôn nhanh hơn `Field`/`MethodHandle` ở mọi trường hợp. Hiệu năng phụ thuộc JDK/JIT, call-site stability, lookup/caching, các access modes, topology của CPU, contention và cách viết benchmark.

Đặc biệt, `getVolatile` hoặc `getAndAdd` có semantics mạnh hơn plain read, nên không thể so benchmark với `Field.get` một cách công bằng mà bỏ qua khác biệt về đồng bộ. Khi chọn API, trước tiên phải **đúng ngữ nghĩa**, sau đó mới đo trong workload thực tế bằng benchmark phù hợp như JMH.

## 6. Ví dụ đầy đủ 2: cùng một field qua ba API

Ví dụ sau chủ ý dùng **hai top-level classes** trong cùng file để chứng minh `Field` và `VarHandle` có mô hình quyền truy cập khác nhau. Lớp `HiddenState` không cùng nest với `FieldAndMethodHandleDemo`, nhưng cả hai chạy trong unnamed module trên classpath.

Tạo **`FieldAndMethodHandleDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Field;

class HiddenState {
    private int score = 10;
}

public class FieldAndMethodHandleDemo {
    public static void main(String[] args) throws Throwable {
        HiddenState state = new HiddenState();

        Field field = HiddenState.class.getDeclaredField("score");
        System.out.println("Field canAccess: " + field.canAccess(state));
        System.out.println("Field trySetAccessible: " + field.trySetAccessible());
        System.out.println("Field getInt: " + field.getInt(state));

        MethodHandles.Lookup privateLookup =
                MethodHandles.privateLookupIn(HiddenState.class,
                        MethodHandles.lookup());
        VarHandle score = privateLookup.findVarHandle(
                HiddenState.class, "score", int.class);
        System.out.println("VarHandle get: " + (int) score.get(state));
        score.set(state, 20);
        System.out.println("VarHandle after set: " + (int) score.get(state));

        MethodHandle getter =
                score.toMethodHandle(VarHandle.AccessMode.GET);
        System.out.println("MethodHandle type: " + getter.type());
        System.out.println("MethodHandle result: "
                + (int) getter.invokeExact(state));
    }
}
```

Lệnh chạy:

```bash
javac --release 17 FieldAndMethodHandleDemo.java
java FieldAndMethodHandleDemo
```

Stdout đã kiểm tra:

```text
Field canAccess: false
Field trySetAccessible: true
Field getInt: 10
VarHandle get: 10
VarHandle after set: 20
MethodHandle type: (HiddenState)int
MethodHandle result: 20
```

Giải thích rõ ranh giới:

- `Field` dùng `getDeclaredField("score")` tìm metadata private. Vì caller là top-level class khác, `canAccess(state)` ban đầu trả `false`. Trên classpath/unnamed module không có hạn chế bổ sung, `trySetAccessible()` trả `true`, sau đó `getInt(state)` đọc `10`.
- `MethodHandles.privateLookupIn(HiddenState.class, MethodHandles.lookup())` lấy một lookup có quyền private phù hợp trong môi trường thử nghiệm. `findVarHandle` tìm vị trí field `score`.
- `score.get(state)` đọc `10`, `score.set(state,20)` ghi `20`.
- `score.toMethodHandle(VarHandle.AccessMode.GET)` tạo **một MethodHandle cho riêng access mode GET**. Handle đó có `type() == (HiddenState)int` và được gọi bằng `(int) getter.invokeExact(state)`.
- Sau khi VarHandle đã ghi `20`, MethodHandle getter đọc cùng một field và trả `20`.

**Không rút ra kết luận sai:** `privateLookupIn` không phải cơ chế tự động phá module encapsulation. Nếu `HiddenState` nằm trong named module khác với package chưa `opens` cho caller, việc lấy private lookup có thể bị từ chối. Chương trình minh họa việc truy cập hợp lệ **trong cùng unnamed module**, không chứng minh quyền ngoài phạm vi đó.

### 6.1. `toMethodHandle` được dùng để làm gì?

Mỗi `VarHandle.AccessMode` tương ứng với một kiểu lời gọi. `toMethodHandle(mode)` cho phép bạn chuyển một access mode thành một MethodHandle có thể đưa vào API tổ hợp Method Handles hoặc gọi khi cần một callable handle duy nhất.

Ví dụ:

```java
MethodHandle get = vh.toMethodHandle(VarHandle.AccessMode.GET);
MethodHandle cas = vh.toMethodHandle(VarHandle.AccessMode.COMPARE_AND_SET);
```

Đây là **mã minh họa** có biến `vh` được tạo trước. `get.type()` và `cas.type()` có các signatures khác nhau. Chúng **không thay thế** VarHandle gốc bằng một MethodHandle có đầy đủ access modes; bạn đã chọn ra **một thao tác cụ thể**.

Một số hệ thống dùng `MethodHandles.varHandleInvoker(...)` hoặc `varHandleExactInvoker(...)` khi cần xây invoker nhận VarHandle như argument. Chỉ dùng dạng phức tạp này khi thật sự cần dynamic composition; với một field và mode ổn định, trực tiếp `vh.get(...)`/`vh.compareAndSet(...)` dễ hiểu hơn.

## 7. Các access modes: plain, opaque, acquire/release, volatile, atomic

Java Memory Model quan tâm không chỉ tới giá trị, mà còn **thứ tự có thể quan sát giữa các thread**. Cùng một field, `VarHandle` cho phép chọn semantics đọc/ghi:

| Nhóm | Đọc / ghi tương ứng | Ý nghĩa tóm tắt |
| --- | --- | --- |
| **Plain** | `get`, `set` | Tương tự read/write field không volatile; **không cung cấp ordering bảo đảm giữa các thread** |
| **Opaque** | `getOpaque`, `setOpaque` | Bảo đảm tính atomic/coherence cho từng biến theo mode này nhưng ordering liên luồng yếu |
| **Acquire / Release** | `getAcquire`, `setRelease` | Khi phối hợp đúng, đảm bảo thứ tự cho dữ liệu đọc sau acquire và ghi trước release |
| **Volatile** | `getVolatile`, `setVolatile` | Có ngữ nghĩa volatile mạnh, tham gia thứ tự volatile theo JMM |
| **Atomic update** | `compareAndSet`, `compareAndExchange`, `getAndSet` | Thao tác cập nhật nguyên tử; từng variant có ordering được xác định |
| **Atomic numeric/bitwise** | `getAndAdd`, `getAndBitwiseOr`, `getAndBitwiseAnd`, `getAndBitwiseXor` | Thay đổi giá trị nguyên tử cho các kiểu được hỗ trợ |

**Cảnh báo:** “atomic” của **một lần truy cập** không có nghĩa toàn bộ chuỗi nhiều lệnh là atomic. `getVolatile` rồi `setVolatile` vẫn không tự thành thao tác cộng nguyên tử. `getAndAdd` mới là thao tác đọc–sửa–ghi nguyên tử được hỗ trợ.

### 7.1. Plain không đủ để phối hợp giữa các thread

`get`/`set` được thiết kế với semantics như trường non-volatile. Nếu thread A ghi nhiều trường và bật cờ bằng plain write, thread B quay vòng bằng plain read **không có giao thức công bố dữ liệu đúng đắn**. JMM có thể cho phép hành vi không như trực giác từ thứ tự source code; không nên dựa vào kết quả “thấy chạy trên máy tôi”.

Bảo đảm atomicity của plain read/write cũng có giới hạn theo kích thước và nền tảng; ví dụ `long`/`double` trên một số nền tảng 32-bit không được bảo đảm bitwise atomic với plain mode. `getVolatile`/các mode mạnh hơn có các bảo đảm khác, theo JDK API.

### 7.2. Acquire/Release dùng cho công bố dữ liệu

Một mẫu giao tiếp gồm producer ghi dữ liệu trước, sau đó **release-write** cờ; consumer **acquire-read** cờ thành công rồi mới đọc dữ liệu đã công bố:

```java
// Mô hình minh họa: FlagBox có int payload và boolean ready;
// READY là VarHandle trỏ tới boolean ready trên FlagBox.

// Thread sản xuất:
box.payload = 42;
READY.setRelease(box, true);

// Thread tiêu thụ:
while (!(boolean) READY.getAcquire(box)) {
    Thread.onSpinWait();
}
int publishedValue = box.payload;
```

**Đây chỉ là hai đoạn thuộc hai thread, không phải chương trình độc lập**: class, handle, vòng đời thread và điều kiện dừng chưa được khai báo. Đọc acquire quan sát được release phù hợp trên cùng biến giúp thiết lập thứ tự cho dữ liệu đã được ghi trước release. Trong ứng dụng thật, cần cơ chế kết thúc/cancel và tránh spin liên tục không giới hạn.

Sử dụng `getAcquire` mà producer vẫn dùng `set` plain, hoặc đặt ghi `payload` sau `setRelease`, sẽ không thiết lập đúng mô hình công bố dữ liệu này.

### 7.3. Volatile là ordering, không phải “atomic cộng”

`getVolatile` và `setVolatile` cung cấp semantics tương đương các truy cập volatile liên quan, nhưng code:

```java
// Minh họa: COUNT là VarHandle tới field int value.
int current = (int) COUNT.getVolatile(counter);
COUNT.setVolatile(counter, current + 1);
```

vẫn có race: hai thread có thể cùng đọc `current`. Nếu mục tiêu là counter chính xác, dùng `getAndAdd` hoặc vòng CAS phù hợp. Nếu cần phối hợp nhiều field theo invariant chung, đôi khi `synchronized`/`Lock` đơn giản và đúng hơn.

### 7.4. Declaration `volatile` không ép mọi VarHandle mode thành volatile

Một field khai báo `volatile int value` vẫn có thể được truy cập bằng `vh.get(obj)`, tức **plain mode**, nếu API hỗ trợ mode đó. `VarHandle` dùng semantics của access mode được chọn, **ghi đè hiệu ứng memory ordering từ declaration** cho chính thao tác đó. Trộn truy cập plain và volatile lên cùng biến mà không có thiết kế JMM rõ ràng dễ tạo bug tinh vi.

Không nên diễn giải “VarHandle dành cho concurrency” thành “mọi `vh.get()` là thread-safe”. Cần chọn mode phù hợp cho protocol thực tế.

### 7.5. CAS, exchange và điều kiện thành công

- `compareAndSet(coordinates..., expected, next)` trả **`boolean`**: `true` khi giá trị hiện tại bằng expected theo so sánh của thao tác và cập nhật thành công, ngược lại `false`.
- `compareAndExchange(coordinates..., expected, next)` trả **witness/giá trị quan sát trước thao tác**; muốn biết có đổi hay không, so sánh witness với expected theo ngữ nghĩa của kiểu đó.
- `getAndSet(coordinates..., next)` thay giá trị và trả **giá trị cũ**.
- `getAndAdd(coordinates..., delta)` cộng nguyên tử vào kiểu số phù hợp và trả **giá trị cũ**.
- Các `weakCompareAndSet...` có thể **thất bại giả** ngay cả khi giá trị hiện tại bằng expected; chương trình phải thiết kế đúng để retry khi dùng variants này.

Đối với **reference value**, compare-and-set so sánh **đồng nhất tham chiếu** (`==`), không gọi `.equals()`. Một đối tượng khác có nội dung bằng nhau vẫn không tự là expected reference.

Atomic update không có nghĩa không bao giờ phải retry: `compareAndSet` có thể trả `false` khi thread khác đổi giá trị trước; đó là đường cạnh tranh hợp lệ. Việc dùng CAS trong vòng lặp cần tính đến fairness, contention và phản ứng với ngoại lệ của nghiệp vụ.

## 8. Ví dụ đầy đủ 3: phần tử mảng qua VarHandle

Một `VarHandle` được tạo bằng `MethodHandles.arrayElementVarHandle(int[].class)` không gắn với **một** index cố định; nó mô tả **họ các phần tử** kiểu `int`, tọa độ là `(int[] array, int index)`.

Tạo **`ArrayVarHandleDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class ArrayVarHandleDemo {
    public static void main(String[] args) {
        int[] numbers = {3, 5};
        VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);

        System.out.println("var type: " + element.varType().getSimpleName());
        System.out.println("coordinate count: " + element.coordinateTypes().size());
        System.out.println("initial index 1: " + (int) element.get(numbers, 1));

        element.set(numbers, 1, 7);
        boolean changed = element.compareAndSet(numbers, 1, 7, 10);
        System.out.println("CAS: " + changed);
        System.out.println("old: " + (int) element.getAndAdd(numbers, 1, 3));
        System.out.println("array[1]: " + numbers[1]);

        try {
            int ignored = (int) element.get(numbers, 99);
            System.out.println(ignored);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("invalid index: ArrayIndexOutOfBoundsException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ArrayVarHandleDemo.java
java ArrayVarHandleDemo
```

Stdout đã kiểm tra:

```text
var type: int
coordinate count: 2
initial index 1: 5
CAS: true
old: 10
array[1]: 13
invalid index: ArrayIndexOutOfBoundsException
```

Giải thích: `element.set(numbers,1,7)` ghi `7`; CAS thấy `7` nên cập nhật thành `10`; `getAndAdd(numbers,1,3)` trả `10` và đổi phần tử thành `13`. Vị trí `99` không nằm trong mảng 2 phần tử nên ném `ArrayIndexOutOfBoundsException`.

Khi phải điều khiển access semantics trên từng phần tử, `VarHandle` đặc biệt thích hợp. Nó **không** đổi kích thước mảng, không cho phép bỏ qua bounds checking, và không biến phần tử mảng thành object được Reflection `Field` mô tả như một field riêng.

### 8.1. Byte-array/ByteBuffer view không đơn giản là array element

Ngoài mảng `T[]`, Java có factory cho view của byte array/ByteBuffer theo component type và byte order, ví dụ `MethodHandles.byteBufferViewVarHandle(int[].class, java.nio.ByteOrder.BIG_ENDIAN)`.

Các view này có **ràng buộc alignment, vị trí và kiểu thành phần**. Một số access modes không hợp lệ khi địa chỉ không aligned, và vùng buffer read-only không chấp nhận write modes. Đừng suy rộng việc CAS thành công trên `int[]` ở ví dụ trước cho mọi ByteBuffer view và mọi offset.

## 9. Ví dụ đầy đủ 4: atomic counter nhiều thread

Một phép `getAndAdd` trên field `int` phù hợp giúp nhiều thread tăng chung counter mà không đánh mất lượt tăng do cạnh tranh đọc–sửa–ghi. Chương trình này tạo 4 thread, mỗi thread tăng 5.000 lần, sau đó `join()` để xác nhận chúng đã hoàn tất.

Tạo **`AtomicVarHandleDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class AtomicVarHandleDemo {
    private static final class Counter {
        volatile int value;
    }

    private static final VarHandle VALUE;
    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        int workerCount = 4;
        int iterations = 5_000;
        Thread[] threads = new Thread[workerCount];

        for (int i = 0; i < workerCount; i++) {
            threads[i] = new Thread(() -> {
                for (int j = 0; j < iterations; j++) {
                    int previous = (int) VALUE.getAndAdd(counter, 1);
                }
            });
        }

        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("expected: " + workerCount * iterations);
        System.out.println("actual: " + (int) VALUE.getVolatile(counter));
    }
}
```

Lệnh:

```bash
javac --release 17 AtomicVarHandleDemo.java
java AtomicVarHandleDemo
```

Stdout đã kiểm tra:

```text
expected: 20000
actual: 20000
```

Ở ví dụ này:

- Mỗi lượt `getAndAdd(counter,1)` cập nhật nguyên tử và trả giá trị trước đó. Local `previous` ở ví dụ không được dùng tiếp; có mặt để biểu diễn đúng return type `int` cho signature-polymorphic call site.
- `Thread.join()` bảo đảm main chỉ đọc kết quả sau khi các worker kết thúc.
- `getVolatile` đọc giá trị cuối với volatile semantics. Không dùng `get` plain làm cơ sở thiết kế giao tiếp giữa các thread đang chạy.
- Dự kiến sau 4 × 5.000 cập nhật nguyên tử là `20.000`, không có lost update. Trong ứng dụng thật còn cần xem integer overflow, lifetime của counter và throughput khi contention cao.

**Lưu ý thiết kế:** Nếu chỉ cần một counter độc lập, `AtomicInteger` thường dễ đọc và đủ dùng. `VarHandle` mạnh khi cần cập nhật **field nằm sẵn trong object** hoặc các phần tử mảng, muốn chọn memory modes và tránh thay hình dạng dữ liệu bằng wrapper riêng. Với counter có contention rất cao, `LongAdder` có thể phù hợp hơn tùy yêu cầu đọc tổng và độ nhất quán, nhưng không thay thế mọi trường hợp cần CAS trên cùng biến.

## 10. Ví dụ đầy đủ 5: static field và final field

Một static field không cần receiver; final field được VarHandle xem như biến **read-only** đối với các write/atomic update modes.

Tạo **`StaticAndFinalVarHandleDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class StaticAndFinalVarHandleDemo {
    private static int global = 3;

    private static final class Immutable {
        private final int amount = 7;
    }

    private static final VarHandle GLOBAL;
    private static final VarHandle AMOUNT;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            GLOBAL = lookup.findStaticVarHandle(
                    StaticAndFinalVarHandleDemo.class, "global", int.class);
            AMOUNT = lookup.findVarHandle(
                    Immutable.class, "amount", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) {
        System.out.println("static coordinates: " + GLOBAL.coordinateTypes().size());
        System.out.println("static before: " + (int) GLOBAL.get());
        GLOBAL.set(5);
        System.out.println("static after: " + (int) GLOBAL.get());

        Immutable immutable = new Immutable();
        System.out.println("final read: " + (int) AMOUNT.get(immutable));
        System.out.println("final set supported: "
                + AMOUNT.isAccessModeSupported(VarHandle.AccessMode.SET));
        try {
            AMOUNT.set(immutable, 9);
        } catch (UnsupportedOperationException e) {
            System.out.println("final set: UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 StaticAndFinalVarHandleDemo.java
java StaticAndFinalVarHandleDemo
```

Stdout đã kiểm tra:

```text
static coordinates: 0
static before: 3
static after: 5
final read: 7
final set supported: false
final set: UnsupportedOperationException
```

`GLOBAL` có **zero coordinate types** vì static field là một vị trí dùng chung của class; `GLOBAL.get()` không truyền receiver. `AMOUNT` có một coordinate là `Immutable`, nên `AMOUNT.get(immutable)` cần instance.

Vì `amount` là final, `AMOUNT.isAccessModeSupported(SET)` trả `false`. Việc gọi `AMOUNT.set(immutable,9)` không “mở khóa final” mà ném `UnsupportedOperationException`. Tương tự, các atomic update modes thay đổi final field cũng không được hỗ trợ. Không coi `VarHandle` là công cụ bypass tính bất biến.

## 11. VarHandle access modes có invoke behavior và invoke-exact behavior

Đây là khác biệt kỹ thuật dễ bị bỏ sót khi so sánh với `MethodHandle`:

- **`MethodHandle.invokeExact`:** đòi call-site `MethodType` khớp **chính xác** handle `type()`, bao gồm kiểu tham số và kết quả; không tự convert.
- **`VarHandle` được tạo bình thường:** access-mode invocation mặc định thường có **invoke behavior**, cho phép các conversion hợp lệ tương tự `MethodHandle.invoke` thông qua `asType`.
- **`VarHandle.withInvokeExactBehavior()`:** trả handle truy cập cùng biến nhưng yêu cầu exact call-site access-mode type; dùng `hasInvokeExactBehavior()` để biết handle đang ở chế độ nào.
- **`VarHandle.withInvokeBehavior()`:** trả handle với invoke behavior khi muốn điều kiện conversion linh hoạt trở lại.

Ví dụ hoàn chỉnh sau cho thấy cùng field `int` nhưng caller dùng receiver kiểu `Object` và muốn return `long`; mặc định có thể thích nghi, trong khi exact mode từ chối return mismatch.

Tạo **`VarHandleModeDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;

public class VarHandleModeDemo {
    private static class Cell {
        int count = 42;
    }
    public static void main(String[] args) throws ReflectiveOperationException {
        Cell c = new Cell();
        VarHandle flexible = MethodHandles.lookup().findVarHandle(
                Cell.class, "count", int.class);
        VarHandle strict = flexible.withInvokeExactBehavior();
        Object broaderReceiver = c;
        long adapted = (long) flexible.get(broaderReceiver);
        System.out.println("flexible: " + adapted);
        System.out.println("strict: " + strict.hasInvokeExactBehavior());
        try {
            long wrong = (long) strict.get(c);
            System.out.println(wrong);
        } catch (WrongMethodTypeException e) {
            System.out.println("strict wrong: WrongMethodTypeException");
        }
        int right = (int) strict.get(c);
        System.out.println("strict right: " + right);
    }
}
```

Chạy:

```bash
javac --release 17 VarHandleModeDemo.java
java VarHandleModeDemo
```

Stdout đã kiểm tra:

```text
flexible: 42
strict: true
strict wrong: WrongMethodTypeException
strict right: 42
```

Giải thích:

1. `flexible.get(broaderReceiver)` dùng receiver có static type `Object`, thực tế chứa `Cell`; đồng thời cast kết quả thành `long` trong khi biến là `int`. Với invoke behavior mặc định, reference cast và primitive widening hợp lệ được áp dụng, trả `42`.
2. `strict` nhận từ `withInvokeExactBehavior()`, có `hasInvokeExactBehavior() == true`.
3. `(long) strict.get(c)` yêu cầu caller return `long` nhưng access-mode type trả `int`, nên ném `WrongMethodTypeException`.
4. `(int) strict.get(c)` tạo call site đúng cả receiver `Cell` lẫn return `int`, nên thành công.

Điều này không biến `VarHandle` thành một `MethodHandle`: nó vẫn đại diện cho **biến** và các access modes. “Invoke”/“invoke-exact” trong VarHandle là **hành vi kiểm tra/chuyển đổi kiểu khi gọi access-mode methods**, không phải thao tác gọi method tùy ý như `MethodHandle`.

**Không nên dùng conversion để che lỗi thiết kế:** Nếu caller dự định truy cập field thuộc class khác, hãy xác minh tọa độ trước thay vì truyền mọi thứ qua `Object` và chờ cast runtime.

## 12. Access mode nào được hỗ trợ? Đừng đoán

Không phải mọi `VarHandle` hỗ trợ mọi mode. Sự hỗ trợ tùy vào:

- Kiểu biến: ví dụ numeric atomic add phù hợp với các kiểu số được hỗ trợ; không phải mọi reference/primitive đều cho `getAndAdd`.
- Mutability: `final` field chỉ đọc, không hỗ trợ set/CAS/add/bitwise update.
- Cách handle được tạo: instance field, array, byte-array/ByteBuffer view có thể có các ràng buộc khác nhau.
- Điều kiện runtime: buffer read-only, alignment, chỉ số vượt phạm vi hoặc receiver null có thể gây các ngoại lệ tương ứng khi thực thi.

Để kiểm tra trước:

```java
if (handle.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)) {
    // Chỉ nhánh này mới được phép gọi getAndAdd phù hợp.
}
```

Đây là **mã minh họa**, không phải chương trình độc lập. `isAccessModeSupported` trả `false` thì việc thực thi mode đó sẽ ném `UnsupportedOperationException`; nó không “hạ cấp” sang mode yếu hơn. Cần tự chọn đường thay thế theo yêu cầu nghiệp vụ.

Ví dụ về final field đã chứng minh `SET` không được hỗ trợ. Với kiểu không có phép cộng như `Object` hoặc `String`, đừng tự giả định `getAndAdd` khả dụng; nếu cần cập nhật reference theo điều kiện, có thể xét `compareAndSet` với semantics identity.

### 12.1. Vùng nhớ đích và lỗi tọa độ

Một handle hợp lệ vẫn có thể bị gọi với tọa độ không hợp lệ:

- Instance field với receiver `null` có thể ném `NullPointerException`.
- Receiver có kiểu không tương thích có thể dẫn tới `ClassCastException` hoặc mismatch kiểu tùy invoke behavior.
- Array element với index ngoài giới hạn ném `ArrayIndexOutOfBoundsException`.
- ByteBuffer/byte-array view có thể gặp lỗi bounds, read-only và alignment khi mode yêu cầu tính nguyên tử.
- Call-site `MethodType` không tương thích, đặc biệt trong exact mode, có thể ném `WrongMethodTypeException`.

Không bắt tất cả những lỗi trên rồi trả giá trị mặc định không rõ nghĩa. Hãy báo **handle, access mode, tọa độ và hợp đồng mong đợi**, đồng thời giữ root cause cho chẩn đoán.

## 13. Các lỗi thường gặp khi lựa chọn API

### 13.1. “VarHandle là Field có thêm cách đọc nhanh”

Không đủ chính xác. `Field` là đối tượng metadata cho **một field**, còn `VarHandle` là typed capability tới **biến/họ biến** và có access modes. Một `VarHandle` tới `int[]` xử lý các phần tử mảng bằng `(array,index)`, không thể mô tả đơn giản như một reflected `Field`.

### 13.2. “VarHandle thay mọi MethodHandle”

Sai. `MethodHandle` có thể biểu diễn method, constructor, getter/setter hoặc tổ hợp transformations. `VarHandle` không thay thế chức năng gọi method tùy ý hoặc adapter graph tổng quát. Nếu bạn cần dynamic dispatch đến một method `calculate(x,y)`, `MethodHandle` thường tự nhiên hơn.

### 13.3. “MethodHandle không có khả năng truy cập field”

Sai. `Lookup.findGetter`, `findSetter`, `findStaticGetter`, `findStaticSetter` tạo MethodHandles cho field access; `VarHandle.toMethodHandle(mode)` cũng có thể chuyển mode thành callable handle. Sự khác biệt cốt lõi là **VarHandle cho phép chọn nhiều access modes trên cùng logical variable**.

### 13.4. “Field không có semantics volatile”

Sai. Core Reflection truy cập một field `volatile` theo semantics phù hợp với field đó. `VarHandle` có lợi thế là đặt semantics **trực tiếp ở thao tác gọi**, kể cả khi declaration không có `volatile`.

### 13.5. “Dùng `getVolatile` và `setVolatile` sẽ không mất lượt tăng”

Sai vì một chuỗi đọc–tính–ghi không trở thành nguyên tử. Dùng `getAndAdd`, `compareAndSet` có vòng lặp đúng, hoặc khóa nếu invariant cần cập nhật nhiều biến cùng lúc.

### 13.6. “`compareAndSet` so sánh reference bằng `equals`”

Sai. Với reference variables, comparison theo identity `==`. Hai `String` khác object nhưng cùng nội dung không tự bảo đảm CAS khớp expected reference.

### 13.7. “VarHandle vào private field là cách bypass Java modules”

Sai. Việc tạo handle dùng `Lookup` và phải có quyền tương ứng. `privateLookupIn` có các ràng buộc JPMS; nếu package không mở cho module caller trong tình huống cần private lookup, có thể ném `IllegalAccessException`.

### 13.8. “`final` có thể được `set` nếu VarHandle được tạo rồi”

Sai. Read-only variable không hỗ trợ write/update modes và ném `UnsupportedOperationException`. `setAccessible(true)` của Core Reflection cũng không phải phương tiện chung để thay đổi mọi final field an toàn.

### 13.9. “VarHandle nào cũng exact giống `invokeExact`”

Sai với VarHandle tạo mặc định trên Java 17: access-mode calls có **invoke behavior**. Chỉ khi dùng `withInvokeExactBehavior()` mới yêu cầu exact matching theo cơ chế đó. Phân biệt hành vi này khi xử lý `WrongMethodTypeException`.

### 13.10. “Atomic nghĩa là mọi đoạn xử lý đều lock-free và nhanh hơn”

Không được bảo đảm. Atomicity của operation là một thuộc tính ngữ nghĩa; thư viện/JVM/hardware có thể có các cách triển khai khác nhau. Performance có thể thay đổi theo contention và access mode; cần đo ở workload cụ thể. Atomic trên **một biến** cũng không tự bảo toàn invariant liên quan tới **nhiều biến**.

## 14. Cách chọn công cụ trong dự án thực tế

Tình huống 1 — **Serializer đọc schema và annotation**: cần tên field, generic type, annotation, modifier, declaring class. Chọn `Field` để khám phá metadata; khi đọc/ghi phải tuân theo access rules. Nếu framework cần nhiều thao tác cập nhật atomic vào field, có thể chuyển sang `VarHandle` sau khi xử lý lookup đúng.

Tình huống 2 — **Gọi method xác định khi runtime biết class/name**: chọn `MethodHandle` cho method/constructor có `MethodType` cụ thể. Tận dụng `bindTo`, `asType` và combinators khi cần dynamic call chains.

Tình huống 3 — **Một biến counter tồn tại sẵn trong từng object**: chọn `VarHandle` nếu cần atomic increment/CAS mà không đổi domain model thành nhiều wrapper objects. Nếu chỉ cần một giá trị atomic độc lập, `AtomicInteger` có thể dễ đọc hơn.

Tình huống 4 — **Cờ công bố trạng thái giữa thread**: thiết kế Java Memory Model protocol rõ; có thể dùng `volatile`, `synchronized`, thư viện concurrency hoặc `VarHandle.setRelease/getAcquire` khi bạn hiểu ordering cần thiết. Chọn mode yếu nhất chỉ khi có lý do đúng đắn và đã kiểm chứng.

Tình huống 5 — **Cập nhật phần tử mảng theo CAS**: `arrayElementVarHandle` đem lại tọa độ `(array,index)` và atomic update trên phần tử phù hợp, trong khi `Field` không đại diện cho từng element như một field.

Tình huống 6 — **Mở private state của module khác**: trước hết cân nhắc public API. Nếu thật sự là framework hợp lệ cần deep access, cấp quyền có chủ đích ở module/package (ví dụ `opens` phù hợp). Không tự kết luận thay `Field` bằng `VarHandle` là vượt qua lỗi truy cập.

### 14.1. Nguyên tắc thiết kế khi đưa VarHandle vào codebase

- Tạo handle ở vị trí hợp lý, thường khi khởi tạo class/component; **không làm lookup bằng tên field ở mỗi thao tác hot-path**.
- Giữ handle có quyền private trong phạm vi tin cậy, vì đó là một **capability** đã được xác minh quyền lúc tạo.
- Ghi rõ access mode tương ứng với giao thức concurrency; tránh trộn plain và volatile thiếu chủ ý.
- Kiểm tra `varType`, `coordinateTypes` và `accessModeType` khi xây framework động.
- Kiểm tra `isAccessModeSupported` khi mode không hiển nhiên được hỗ trợ, đặc biệt trên field final và data views.
- Giữ test cho lỗi lookup, module access, readonly, receiver/index mismatch, mode unsupported, và concurrency correctness.
- Với kiểu dữ liệu đơn giản và ít yêu cầu concurrency, ưu tiên code Java bình thường hơn một tầng dynamic access không cần thiết.

## 15. Bảng chẩn đoán nhanh

| Lỗi / triệu chứng | Giai đoạn | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- | --- |
| `NoSuchFieldException` từ `findVarHandle` | Lookup | Sai tên, sai declared type, nhầm static/instance | Kiểm tra khai báo thật; dùng đúng factory/field type |
| `IllegalAccessException` từ lookup | Tạo handle | `Lookup` không đủ quyền hoặc JPMS chặn private lookup | Sửa thiết kế public API/module opens phù hợp; không bypass |
| `WrongMethodTypeException` tại access mode | Invoke | Call-site parameter/return không tương thích với access-mode type; exact behavior nghiêm ngặt | In `accessModeType`, kiểm tra tọa độ, kiểu primitive/reference, return |
| `ClassCastException` | Conversion/receiver | Runtime object không có kiểu mà conversion yêu cầu | Kiểm tra object type và adapter policy |
| `UnsupportedOperationException` | Invoke access mode | Biến không hỗ trợ mode, ví dụ write vào final | Dùng `isAccessModeSupported`; chọn mode/factory thích hợp |
| `NullPointerException` | Định vị instance variable | Receiver/array không có object | Kiểm tra tọa độ và input |
| `ArrayIndexOutOfBoundsException` | Array access | Index không nằm trong mảng | Kiểm tra index; không coi là access-control error |
| Kết quả counter nhỏ hơn mong đợi | Concurrency logic | Đọc–ghi tách đôi, race/lost update | Dùng atomic RMW hoặc khóa; kiểm thử đa luồng |
| Một thread không thấy dữ liệu công bố | Memory ordering | Thiếu acquire/release/volatile synchronization | Thiết kế happens-before đúng theo JMM |
| `Field.canAccess` false nhưng `VarHandle` dùng được ở code khác | Access model khác nhau | Field kiểm tra access tại lời gọi; VarHandle capability được cấp khi lookup hợp lệ | Kiểm tra caller/module và nơi handle được tạo, không coi là bypass |

Khi chẩn đoán, hãy bắt đầu bằng **mục tiêu là một biến hay một lời gọi method**, tiếp theo là **mode cần có và type signature của thao tác**. Đừng thay đổi visibility, concurrency mode hoặc API chỉ vì một thông báo lỗi chung chung.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Điểm khác nhau về mục đích giữa `Field` và `VarHandle` là gì?

**Đáp án:** `Field` cung cấp metadata và API đọc/ghi field; `VarHandle` là typed reference tới một biến/họ biến với nhiều access modes gồm plain, volatile và atomic updates. Cả hai vẫn chịu Java access control và module boundaries.

**Câu 2.** Instance field `int Box.count` có variable type và coordinate types nào?

**Đáp án:** `varType() == int.class`, `coordinateTypes() == [Box.class]`. `get` cần một receiver Box; `compareAndSet` còn cần expected và replacement values.

**Câu 3.** Vì sao static field handle có `coordinateTypes().size() == 0`?

**Đáp án:** static field không gắn với một object instance. Một class có một vị trí static field tương ứng trong bối cảnh runtime/class loader; access call không truyền receiver.

**Câu 4.** `compareAndSet(box,5,8)` khác gì `if (get(box)==5) set(box,8)`?

**Đáp án:** CAS là một thao tác đọc–so sánh–ghi nguyên tử khi mode hỗ trợ; hai lời gọi tách riêng có thể bị thread khác chen giữa.

**Câu 5.** Hai thread cùng tăng `volatile int count` bằng `count++` có bảo đảm số lần tăng chính xác không?

**Đáp án:** Không. `volatile` không biến ba bước đọc–cộng–ghi thành một thao tác atomic. Dùng `getAndAdd`, CAS loop hoặc đồng bộ thích hợp.

**Câu 6.** Vì sao `VarHandle` đọc được field final nhưng `set` ném `UnsupportedOperationException`?

**Đáp án:** final field được coi là read-only variable cho VarHandle; write/update modes không được hỗ trợ. Kiểm tra `isAccessModeSupported(SET)` trước.

**Câu 7.** Một MethodHandle tạo từ `vh.toMethodHandle(GET)` khác chính VarHandle ở điểm nào?

**Đáp án:** MethodHandle chỉ biểu diễn thao tác GET đã chọn với `MethodType` tương ứng. VarHandle gốc vẫn cung cấp cả tập modes cho cùng biến (nếu được hỗ trợ).

**Câu 8.** Nếu cần gọi private field nằm trong module khác, `findVarHandle` có luôn vượt qua bảo vệ JPMS không?

**Đáp án:** Không. Lookup kiểm tra quyền khi tạo handle; private lookup có thể yêu cầu package được mở cho module caller. Phải xử lý đúng public API hoặc `opens` có chủ đích.

**Câu 9.** VarHandle tạo mặc định trong Java 17 có hoàn toàn giống `MethodHandle.invokeExact` về conversion không?

**Đáp án:** Không. Default VarHandle access-mode calls có invoke behavior, có thể thích nghi các conversion hợp lệ; `withInvokeExactBehavior()` mới chuyển sang exact behavior.

**Câu 10.** `getAndAdd(box,1)` trả về giá trị sau khi cộng hay trước khi cộng?

**Đáp án:** Giá trị **trước** khi cộng. Biến được cập nhật nguyên tử; người gọi có thể đọc lại bằng mode thích hợp nếu cần giá trị mới.

**Câu 11.** Một `VarHandle` tới `int[]` cần truyền những tọa độ nào cho `get`?

**Đáp án:** Mảng `int[]` và chỉ số `int`. `varType()` là `int`; chỉ số không hợp lệ ném exception về bounds.

**Câu 12.** Khi nào nên chọn `AtomicInteger` thay vì `VarHandle`?

**Đáp án:** Với một biến atomic độc lập và không cần truy cập field có sẵn hay memory mode tùy biến, `AtomicInteger` thường đơn giản hơn. `VarHandle` phù hợp với field/array element và giao thức access-mode chuyên biệt.

## 17. Tài liệu chuẩn

- **Java SE 17 `VarHandle` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html — variable/coordinate types, access modes, invocation behavior, memory ordering, `isAccessModeSupported`.
- **Java SE 17 `VarHandle.AccessMode` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.AccessMode.html — tên và vai trò từng mode.
- **Java SE 17 `MethodHandles` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html — `arrayElementVarHandle`, buffer views, invokers.
- **Java SE 17 `MethodHandles.Lookup` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html — `findVarHandle`, `findStaticVarHandle`, quyền lookup.
- **Java SE 17 `MethodHandle` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html — typed invocations, `invokeExact`, `invoke`, adapters.
- **Java SE 17 `Field` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html — metadata, `get`/`set`, modifiers.
- **JEP 193 — Variable Handles:** https://openjdk.org/jeps/193 — lý do thiết kế VarHandle và các access modes.
- **Java Language Specification 17 — Memory Model:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4 — synchronization và happens-before.

**Kết luận:** `VarHandle` giải quyết bài toán **truy cập biến với một ngữ nghĩa bộ nhớ được chỉ rõ ở từng thao tác**. `Field` phục vụ khám phá và thao tác field qua Reflection; `MethodHandle` phục vụ lời gọi có kiểu. Chọn đúng công cụ theo **ý đồ truy cập, khả năng kiểm soát concurrency, quyền module và hợp đồng dữ liệu**, thay vì chỉ so tên API hay phỏng đoán hiệu năng.