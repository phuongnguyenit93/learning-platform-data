# 9.8 Kiểm tra `isAccessModeSupported` và giới hạn của biến chỉ đọc

`java.lang.invoke.VarHandle` cung cấp cơ chế truy cập biến theo nhiều **access mode**: đọc thông thường, đọc/ghi với ngữ nghĩa bộ nhớ khác nhau, compare-and-set (CAS), trao đổi giá trị hoặc cập nhật nguyên tử. Tuy nhiên **không phải mode nào cũng được mọi VarHandle hỗ trợ**. Một `final` field là trường hợp tiêu biểu: có thể đọc qua VarHandle nhưng không thể dùng VarHandle để ghi hoặc CAS lên chính field đó.

Phương thức trọng tâm là:

```java
boolean supported = handle.isAccessModeSupported(
        VarHandle.AccessMode.COMPARE_AND_SET);
```

Đây là fragment minh họa: biến `handle` giả định là một `VarHandle` đã được tìm hoặc tạo, và đã import `java.lang.invoke.VarHandle`.

Kết quả `true` nghĩa là **mode được VarHandle hỗ trợ ở cấp loại biến/nhà cung cấp handle**; không phải cam kết rằng **mọi lần gọi** với **mọi đối tượng cụ thể** sẽ thành công. Ví dụ đáng chú ý: VarHandle xem một `ByteBuffer` như mảng `int` có thể báo `SET` được hỗ trợ, nhưng khi truyền **một buffer đang ở chế độ read-only**, việc ghi sẽ ném `ReadOnlyBufferException`.

> **Môi trường thực hành:** Java 17 trở lên; bốn chương trình độc lập ở dưới biên dịch được bằng `javac --release 17`. Tất cả output được đối chiếu với kết quả chạy thực tế. Bài tập trung vào **giới hạn mode và biến chỉ đọc**, không nhằm thay thế một bài đầy đủ về Java Memory Model.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích `VarHandle.isAccessModeSupported(AccessMode)` trả về gì và khi nào cần kiểm tra.
- Phân biệt `GET`, `SET`, `GET_VOLATILE`, `COMPARE_AND_SET`, `GET_AND_ADD`, `GET_AND_BITWISE_OR` theo nhóm thao tác.
- Hiểu vì sao `final` instance field và `static final` field **chỉ có thể đọc qua VarHandle**, kể cả khi code có quyền lookup.
- Không nhầm **`final` tham chiếu đến mảng** với **các phần tử của mảng là bất biến**.
- Phân biệt **mode không được hỗ trợ** (`UnsupportedOperationException`) với **mode được hỗ trợ nhưng receiver hiện tại cấm ghi** (`ReadOnlyBufferException`).
- Đọc `varType()`, `coordinateTypes()` và `accessModeType(...)` để định vị đúng biến và lời gọi.
- Thiết kế nhánh fallback an toàn, không vô tình thay một thao tác nguyên tử bằng chuỗi đọc–ghi không nguyên tử.

## 2. `VarHandle` mô tả biến và tọa độ, không phải một giá trị cố định

Một `VarHandle` không đơn thuần giữ giá trị; nó là tham chiếu kiểu mạnh tới **một biến** hoặc **một họ biến**. Theo cách tạo handle, nó có thể truy cập:

| Đích | Factory/lookup thường dùng | Tọa độ (coordinate types) |
| --- | --- | --- |
| Trường instance `int counter` | `lookup.findVarHandle(Owner.class, "counter", int.class)` | `(Owner)` |
| Trường `static int limit` | `lookup.findStaticVarHandle(Owner.class, "limit", int.class)` | Không có tọa độ |
| Phần tử `int[]` | `MethodHandles.arrayElementVarHandle(int[].class)` | `(int[], int)` |
| Ô dữ liệu trong `ByteBuffer` với view `int` | `MethodHandles.byteBufferViewVarHandle(int[].class, ByteOrder.LITTLE_ENDIAN)` | `(ByteBuffer, int)` |

Ở đây, "tọa độ" là những đối số xác định **vị trí của biến**: object chứa field, mảng và chỉ số, hoặc buffer và byte index. Sau tọa độ, một số access mode còn cần giá trị mới, giá trị mong đợi để CAS, delta cộng hoặc mask bitwise.

API hỗ trợ quan sát:

```java
Class<?> type = handle.varType();
java.util.List<Class<?>> coords = handle.coordinateTypes();
java.lang.invoke.MethodType signature =
        handle.accessModeType(VarHandle.AccessMode.GET);
```

Đây là fragment không độc lập; giả định `handle` đã được khởi tạo. Với instance `int` field của `Owner`, `varType()` là `int.class`, `coordinateTypes()` là danh sách chứa `Owner.class`. Với static field, danh sách tọa độ rỗng. Các thông tin này có ích khi debug mismatch về số hoặc kiểu đối số.

**Quan trọng:** `accessModeType(mode)` chỉ mô tả **chữ ký kiểu của mode đó**, không có nghĩa mode ấy được hỗ trợ. Hãy dùng `isAccessModeSupported(mode)` để kiểm tra khả năng, rồi mới gọi access mode với tọa độ/kiểu đúng.

## 3. Các nhóm `AccessMode` và ngữ nghĩa

`VarHandle.AccessMode` là enum có tên tương ứng với các phương thức `VarHandle`. Một số đại diện:

| Nhóm | Mode ví dụ | Dạng lời gọi/ý nghĩa |
| --- | --- | --- |
| Đọc | `GET`, `GET_OPAQUE`, `GET_ACQUIRE`, `GET_VOLATILE` | Lấy giá trị theo mức ràng buộc thứ tự bộ nhớ tương ứng |
| Ghi | `SET`, `SET_OPAQUE`, `SET_RELEASE`, `SET_VOLATILE` | Gán giá trị mới theo mức ràng buộc thứ tự bộ nhớ tương ứng |
| Cập nhật nguyên tử bằng so sánh | `COMPARE_AND_SET`, `COMPARE_AND_EXCHANGE`, `WEAK_COMPARE_AND_SET` và các biến thể | So sánh giá trị hiện tại với giá trị mong đợi, rồi có thể thay giá trị |
| Đổi giá trị nguyên tử | `GET_AND_SET` và các biến thể | Ghi giá trị mới, trả giá trị trước đó |
| Cộng nguyên tử | `GET_AND_ADD` và các biến thể | Cộng delta, trả giá trị cũ |
| Bitwise nguyên tử | `GET_AND_BITWISE_OR`, `GET_AND_BITWISE_AND`, `GET_AND_BITWISE_XOR` và các biến thể | Thay đổi bit theo phép tương ứng, trả giá trị trước đó |

Các hậu tố như `Acquire`, `Release`, `Volatile` và `Opaque` liên quan tới **thứ tự bộ nhớ và đồng bộ giữa các luồng**. Chúng không tự làm biến final thành có thể ghi. Việc dùng access mode cụ thể cần hợp đồng đồng bộ phù hợp; đây không phải một phép "nâng quyền" hoặc cách cưỡng bức ghi biến chỉ đọc.

### 3.1. Các nhóm không luôn hỗ trợ cùng một kiểu dữ liệu

Đừng kết luận rằng `SET` được hỗ trợ thì `GET_AND_ADD` cũng được hỗ trợ. Đối với các field thông thường:

- Kiểu `int` có thể hỗ trợ `GET_AND_ADD` và các mode bitwise.
- Kiểu tham chiếu `String` có thể hỗ trợ `COMPARE_AND_SET` hoặc `GET_AND_SET`, nhưng không phải `GET_AND_ADD` hay `GET_AND_BITWISE_OR`.
- Các phép numeric atomic update chỉ áp dụng cho nhóm kiểu số primitive tương thích; các phép bitwise atomic update chỉ áp dụng cho nhóm kiểu nguyên/boolean được tài liệu factory quy định.
- Nếu biến là `final`, các mode **ghi và cập nhật** đều không được hỗ trợ, dù kiểu field là `int` vốn hỗ trợ phép cộng nguyên tử khi không final.

Vì thế khả năng được quyết định bởi **cách tạo VarHandle + loại biến + kiểu biến + giới hạn của factory**. Không có một bảng duy nhất "mọi VarHandle đều hỗ trợ tất cả mode".

### 3.2. Kiểm tra mode bằng enum, không dựa trên tên chuỗi

Dùng enum có sẵn:

```java
import java.lang.invoke.VarHandle;

boolean canRead = handle.isAccessModeSupported(
        VarHandle.AccessMode.GET);
boolean canWrite = handle.isAccessModeSupported(
        VarHandle.AccessMode.SET);
boolean canCas = handle.isAccessModeSupported(
        VarHandle.AccessMode.COMPARE_AND_SET);
```

Đây là fragment minh họa. Không tạo chuỗi `"COMPARE_AND_SET"` rồi giả định tên đó tự kích hoạt capability; chính overload nhận `AccessMode` thực hiện kiểm tra.

## 4. Hợp đồng của `isAccessModeSupported`

Định nghĩa thực dụng:

- Trả `true`: VarHandle có triển khai phù hợp để thực hiện mode được hỏi **đối với loại biến mà handle đại diện**.
- Trả `false`: lời gọi phương thức access mode tương ứng sẽ ném **`UnsupportedOperationException`**.
- Mode `GET` được **mọi VarHandle** hỗ trợ, vì vậy `GET` không ném `UnsupportedOperationException` (nhưng vẫn có thể ném lỗi khác khi tọa độ/đối tượng sai).
- Kết quả không tự kiểm tra **giá trị receiver truyền vào sau này**, ví dụ buffer có read-only không, index nằm trong giới hạn không, class đã được khởi tạo chưa, hoặc method call-site có đúng kiểu không.
- Kết quả không nói lên quyền Reflection/lookup hay module permission. Các kiểm tra truy cập để **lấy VarHandle** được xử lý tại bước lookup riêng.

Điểm cuối rất quan trọng. VarHandle có thể hỗ trợ mode `SET` ở cấp "họ biến ByteBuffer" nhưng một `ByteBuffer` cụ thể vẫn là read-only. Điều kiện runtime có thể khiến lời gọi thất bại sau khi capability check đã trả `true`.

### 4.1. Kiểm tra mode trước khi thiết kế lời gọi

Một cách đơn giản:

```java
// Fragment: counter là VarHandle trên int field và state là receiver đúng kiểu.
if (counter.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)) {
    int old = (int) counter.getAndAdd(state, 1);
    System.out.println("old=" + old);
} else {
    throw new UnsupportedOperationException(
            "This VarHandle does not support atomic addition");
}
```

Đây không phải chương trình độc lập; logic giả định các biến đã có. Nhánh lỗi không chọn `counter.set(state, (int) counter.get(state) + 1)` để thay thế vì đọc–tính–ghi **không còn nguyên tử**. Nếu yêu cầu atomicity, fallback phải có một hợp đồng đồng bộ đúng, như khóa phù hợp, hoặc chuyển sang thiết kế dữ liệu khác.

Nếu chỉ cần đọc, có thể dùng `get(...)` mà không kiểm tra support trước, nhưng vẫn phải chuẩn bị đúng tọa độ và kiểu trả về của call-site.

## 5. Biến `final`: đọc được, không thể ghi qua VarHandle

Theo đặc tả VarHandle và Lookup:

- `final int id` (instance field): VarHandle có tọa độ là object sở hữu field; các mode đọc có thể dùng. **`SET`, `SET_VOLATILE`, CAS và atomic update không được hỗ trợ.**
- `static final int LIMIT`: VarHandle có tọa độ rỗng và vẫn chỉ hỗ trợ các mode đọc; không có receiver object truyền vào `get()`.
- `final` là giới hạn về **biến được tham chiếu bởi chính VarHandle**. Kể cả code có quyền tìm được handle tới private final field, quyền lookup đó **không biến field thành mutable**.
- `volatile` không giống `final`. Một `volatile int counter` không-final có thể hỗ trợ `SET`, `COMPARE_AND_SET`, `GET_AND_ADD`; cách chọn mode vẫn quyết định memory ordering thực tế.

Bảng tóm tắt các mode tiêu biểu cho một instance `final int` field:

| Access mode | Hỗ trợ? | Giải thích |
| --- | --- | --- |
| `GET` | Có | Đọc thông thường |
| `GET_OPAQUE`, `GET_ACQUIRE`, `GET_VOLATILE` | Có với VarHandle field này | Các dạng đọc có ngữ nghĩa bộ nhớ tương ứng |
| `SET`, `SET_RELEASE`, `SET_VOLATILE` | Không | Field final không thể gán lại qua VarHandle |
| `COMPARE_AND_SET`, `COMPARE_AND_EXCHANGE` | Không | CAS cũng là cập nhật, không chỉ là đọc |
| `GET_AND_SET`, `GET_AND_ADD`, `GET_AND_BITWISE_OR` | Không | Các thao tác này có khả năng ghi |

Nếu cố gọi một mode không hỗ trợ với tham số đúng, kết quả là `UnsupportedOperationException`, không phải thay đổi field một cách im lặng. Đây là giới hạn **của API VarHandle**, không phụ thuộc vào mong muốn "đang chạy cùng class" của caller.

### 5.1. Tại sao `final` không tương đương `immutable object`?

`final` bảo vệ **phép gán lại biến field** sau quá trình khởi tạo theo hợp đồng của ngôn ngữ, không tự động biến object mà field tham chiếu tới thành bất biến.

Ví dụ:

```java
final int[] values = {1, 2};
```

Đây là một **local variable fragment**. Bạn không gán `values = otherArray` sau lần gán cuối, nhưng vẫn có thể thực hiện `values[0] = 9`. Cùng một nguyên lý áp dụng cho `final int[] values` là field: VarHandle của **field tham chiếu mảng** chỉ cho phép đọc, còn một VarHandle khác trỏ tới **phần tử mảng** có thể cho phép ghi hoặc cập nhật nguyên tử.

**Cũng vậy**, một field `final List<T>` không tự động biến các thao tác thêm/xóa/sửa **nội dung** List thành bị cấm. VarHandle hạn chế việc gán lại chính field; tính bất biến sâu của object là một hợp đồng thiết kế khác.

### 5.2. `static final` và compile-time constants

`static final int LIMIT = 11` có thể là **compile-time constant**. Mã Java khác có thể đã inline giá trị đó trong bytecode khi biên dịch. Điều này không mở thêm quyền cập nhật qua VarHandle; `SET` trên field final vẫn không được hỗ trợ. Đừng thử dùng VarHandle để "đổi hằng số trên toàn ứng dụng", vì cả quyền ghi lẫn cơ chế inline đều chống lại kỳ vọng đó.

## 6. Thực hành 1 — Kiểm tra mode trên final instance/static field

Tạo tệp **`FinalFieldModesDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.VarHandle.AccessMode;

public class FinalFieldModesDemo {
    static class State {
        final int id = 7;
        volatile int counter = 1;
        static final int LIMIT = 11;
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        VarHandle id = lookup.findVarHandle(State.class, "id", int.class);
        VarHandle counter = lookup.findVarHandle(State.class, "counter", int.class);
        VarHandle limit = lookup.findStaticVarHandle(State.class, "LIMIT", int.class);
        State state = new State();

        System.out.println("id variable type: " + id.varType().getSimpleName());
        System.out.println("id coordinates: " + id.coordinateTypes());
        System.out.println("limit coordinates: " + limit.coordinateTypes());
        System.out.println("id GET: " + id.isAccessModeSupported(AccessMode.GET));
        System.out.println("id GET_VOLATILE: " + id.isAccessModeSupported(AccessMode.GET_VOLATILE));
        System.out.println("id SET: " + id.isAccessModeSupported(AccessMode.SET));
        System.out.println("id COMPARE_AND_SET: " + id.isAccessModeSupported(AccessMode.COMPARE_AND_SET));
        System.out.println("id GET_AND_ADD: " + id.isAccessModeSupported(AccessMode.GET_AND_ADD));
        System.out.println("counter SET: " + counter.isAccessModeSupported(AccessMode.SET));
        System.out.println("counter COMPARE_AND_SET: " + counter.isAccessModeSupported(AccessMode.COMPARE_AND_SET));
        System.out.println("limit SET: " + limit.isAccessModeSupported(AccessMode.SET));
        System.out.println("id read: " + (int) id.get(state));
        System.out.println("limit read: " + (int) limit.get());

        try {
            id.set(state, 12);
            System.out.println("unreachable");
        } catch (UnsupportedOperationException ex) {
            System.out.println("id set exception: " + ex.getClass().getSimpleName());
        }

        counter.set(state, 8);
        boolean changed = counter.compareAndSet(state, 8, 9);
        System.out.println("counter changed: " + changed);
        System.out.println("counter read: " + (int) counter.getVolatile(state));
    }
}
```

Lệnh:

```bash
javac --release 17 FinalFieldModesDemo.java
java FinalFieldModesDemo
```

**Stdout chính xác với JDK 17+:**

```text
id variable type: int
id coordinates: [class FinalFieldModesDemo$State]
limit coordinates: []
id GET: true
id GET_VOLATILE: true
id SET: false
id COMPARE_AND_SET: false
id GET_AND_ADD: false
counter SET: true
counter COMPARE_AND_SET: true
limit SET: false
id read: 7
limit read: 11
id set exception: UnsupportedOperationException
counter changed: true
counter read: 9
```

Cách đọc:

1. `id.varType() == int.class`, trong khi `id.coordinateTypes()` có đúng một class `State` vì `id` là instance field. `LIMIT` là static field, nên `limit.coordinateTypes()` rỗng.
2. `id` là final: các mode **GET** và **GET_VOLATILE** được hỗ trợ, còn `SET`, `COMPARE_AND_SET`, `GET_AND_ADD` bị từ chối.
3. `id.get(state)` trả `7`; `limit.get()` trả `11`, không truyền receiver cho static field.
4. Đoạn `id.set(state, 12)` được bao trong `try/catch` để minh họa thất bại có chủ đích: nó ném `UnsupportedOperationException`.
5. `counter` là field `volatile` nhưng không final: `SET` và CAS được hỗ trợ. `compareAndSet(state, 8, 9)` thành công, giá trị cuối là `9`.

> Chương trình thuộc cùng outer class với `State` nên lookup có quyền truy cập member dùng trong ví dụ. Ở ứng dụng đa module, việc tìm field private hoặc non-public còn chịu kiểm tra quyền của `Lookup`, một vấn đề tách biệt với khả năng hỗ trợ access mode.

## 7. Phân biệt VarHandle của field tham chiếu và VarHandle của phần tử

Hai handle sau mô tả **hai loại biến khác nhau**:

```text
class Box {
    final int[] values = {1, 2};
}

reference = lookup.findVarHandle(Box.class, "values", int[].class)
   varType: int[]
   coordinates: (Box)
   access: tham chiếu final => đọc được, không gán lại bằng SET/CAS

element = MethodHandles.arrayElementVarHandle(int[].class)
   varType: int
   coordinates: (int[], int)
   access: phần tử mảng => có thể SET, CAS, GET_AND_ADD...
```

Đây là mô tả để minh họa, không phải chương trình độc lập. `reference` và `element` hoàn toàn không hoán đổi cho nhau: `reference.get(box)` trả một `int[]`; `element.set(array, index, value)` cập nhật một phần tử kiểu `int`.

### 7.1. Thực hành 2 — Final array reference vẫn cho sửa phần tử

Tạo tệp **`FinalArrayVsElementDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.VarHandle.AccessMode;

public class FinalArrayVsElementDemo {
    static class Box {
        final int[] values = {1, 2};
    }

    public static void main(String[] args) throws Exception {
        VarHandle reference = MethodHandles.lookup().findVarHandle(
                Box.class, "values", int[].class);
        VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);
        Box box = new Box();
        int[] array = (int[]) reference.get(box);

        System.out.println("reference SET: " + reference.isAccessModeSupported(AccessMode.SET));
        System.out.println("reference CAS: " + reference.isAccessModeSupported(AccessMode.COMPARE_AND_SET));
        System.out.println("element coordinates: " + element.coordinateTypes());
        System.out.println("element SET: " + element.isAccessModeSupported(AccessMode.SET));
        System.out.println("element GET_AND_ADD: " + element.isAccessModeSupported(AccessMode.GET_AND_ADD));
        System.out.println("before: " + (int) element.get(array, 0));
        element.set(array, 0, 9);
        int old = (int) element.getAndAdd(array, 1, 5);
        System.out.println("element[0]: " + (int) element.get(array, 0));
        System.out.println("element[1] old: " + old);
        System.out.println("element[1] now: " + array[1]);
    }
}
```

```bash
javac --release 17 FinalArrayVsElementDemo.java
java FinalArrayVsElementDemo
```

**Stdout:**

```text
reference SET: false
reference CAS: false
element coordinates: [class [I, int]
element SET: true
element GET_AND_ADD: true
before: 1
element[0]: 9
element[1] old: 2
element[1] now: 7
```

Tại sao?

- VarHandle `reference` chỉ thấy **biến field `values`** và từ chối `SET`/CAS vì field có `final`.
- VarHandle `element` thấy **phần tử mảng `int`** tại tọa độ `(array,index)`, không thấy modifier `final` của field đang giữ tham chiếu đến mảng.
- `element.set(array, 0, 9)` ghi phần tử thứ nhất.
- `element.getAndAdd(array, 1, 5)` trả **giá trị cũ `2`** và cập nhật phần tử thứ hai thành `7`.

Không được suy luận rằng mọi array element VarHandle đều hỗ trợ **mọi** numeric/bitwise mode: hỗ trợ còn phụ thuộc component type (`int` ở ví dụ có thể cộng và xử lý bitwise). Và dù hỗ trợ mode, chỉ số vượt mảng vẫn có thể ném `ArrayIndexOutOfBoundsException`.

## 8. Biến “chỉ đọc” không phải một khái niệm duy nhất

Có ít nhất ba tình huống khác nhau trong thực tế:

| Nguồn giới hạn | Ví dụ | `isAccessModeSupported(SET)` | Điều gì xảy ra nếu cố ghi? |
| --- | --- | --- | --- |
| Bản thân biến được khai báo final | `final int id` hoặc `static final int LIMIT` | `false` | `UnsupportedOperationException` nếu gọi `set` đúng chữ ký |
| Đối tượng receiver **cụ thể** không cho ghi | `ByteBuffer.asReadOnlyBuffer()` với view VarHandle | Có thể `true` cho VarHandle family | `ReadOnlyBufferException` tại lời gọi trên buffer read-only |
| Final chỉ áp dụng cho **field tham chiếu**, không áp dụng cho object được tham chiếu | `final int[] values` và array-element VarHandle | Field VH: `false`; element VH: `true` | Field không gán lại, phần tử vẫn cập nhật được |

Sự khác biệt này giải thích vì sao không thể viết một hàm `isReadOnly(VarHandle)` đơn giản rồi kỳ vọng nó diễn đạt mọi trường hợp. **`VarHandle` không có một API chung hỏi liệu một receiver cụ thể hiện tại có cho ghi hay không**. Khi receiver là ByteBuffer, phải xem thêm `buffer.isReadOnly()` và chấp nhận rằng một lần access vẫn có thể gặp những ngoại lệ runtime khác.

### 8.1. Buffer view VarHandle và chỉ số byte

`MethodHandles.byteBufferViewVarHandle(int[].class, ByteOrder.LITTLE_ENDIAN)` trả VarHandle nhìn một vùng byte của `ByteBuffer` như giá trị `int`. Nó có:

- `varType() == int.class`;
- hai tọa độ `(ByteBuffer.class, int.class)`;
- tọa độ `int` là **byte index** bắt đầu vùng giá trị, không phải "chỉ số phần tử int" tùy ý;
- quy tắc byte order được khai báo lúc tạo view;
- những ràng buộc bổ sung về bounds, alignment và read-only khi thực hiện thao tác cụ thể.

Nếu buffer vừa được chuyển sang read-only bằng `asReadOnlyBuffer()`, cùng một VarHandle đó vẫn mô tả **họ biến ByteBuffer** có thể ghi trong trường hợp buffer writable. Vì vậy `isAccessModeSupported(SET)` có thể trả `true`; khi thực sự truyền buffer read-only, `set` bị từ chối.

### 8.2. Thực hành 3 — Mode `SET` supported nhưng receiver read-only

Tạo tệp **`ReadOnlyBufferDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.VarHandle.AccessMode;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ReadOnlyBufferException;

public class ReadOnlyBufferDemo {
    public static void main(String[] args) {
        ByteBuffer writable = ByteBuffer.allocate(16).order(ByteOrder.LITTLE_ENDIAN);
        writable.putInt(0, 0x01020304);
        ByteBuffer readOnly = writable.asReadOnlyBuffer();
        VarHandle view = MethodHandles.byteBufferViewVarHandle(
                int[].class, ByteOrder.LITTLE_ENDIAN);

        System.out.println("buffer read-only: " + readOnly.isReadOnly());
        System.out.println("view coordinates: " + view.coordinateTypes());
        System.out.println("view SET supported: " + view.isAccessModeSupported(AccessMode.SET));
        System.out.println("view GET supported: " + view.isAccessModeSupported(AccessMode.GET));
        System.out.println("read-only GET: " + (int) view.get(readOnly, 0));
        try {
            view.set(readOnly, 0, 99);
            System.out.println("unreachable");
        } catch (ReadOnlyBufferException ex) {
            System.out.println("read-only SET exception: " + ex.getClass().getSimpleName());
        }
        view.set(writable, 0, 42);
        System.out.println("writable GET: " + (int) view.get(writable, 0));
    }
}
```

```bash
javac --release 17 ReadOnlyBufferDemo.java
java ReadOnlyBufferDemo
```

**Stdout:**

```text
buffer read-only: true
view coordinates: [class java.nio.ByteBuffer, int]
view SET supported: true
view GET supported: true
read-only GET: 16909060
read-only SET exception: ReadOnlyBufferException
writable GET: 42
```

Diễn giải:

1. `writable` chứa một `int` là `0x01020304`; giá trị thập phân `16909060`. VarHandle view sử dụng `ByteOrder.LITTLE_ENDIAN` tương ứng với cách dữ liệu được ghi.
2. `readOnly.isReadOnly()` là `true`. Nhưng `view.isAccessModeSupported(SET)` vẫn là `true` vì ở cấp **VarHandle**, mode được hỗ trợ cho loại view này.
3. `view.get(readOnly, 0)` đọc thành công. `view.set(readOnly, 0, 99)` ném **`ReadOnlyBufferException`** dù capability trả true.
4. `view.set(writable, 0, 42)` thành công với một buffer khác writable, chứng minh handle không tự "read-only".
5. `asReadOnlyBuffer()` tạo một buffer chỉ đọc **chia sẻ vùng lưu trữ** với buffer gốc. Nếu nơi khác tiếp tục ghi qua `writable`, dữ liệu quan sát được từ `readOnly` có thể thay đổi. "Read-only view" không đồng nghĩa "immutable snapshot".

> Với ByteBuffer view, các mode có yêu cầu atomic/volatile có thể còn yêu cầu **alignment** theo kích thước dữ liệu; truy cập sai alignment hoặc vượt bounds có thể ném lỗi riêng. `isAccessModeSupported(...)` không thay việc kiểm tra tọa độ và trạng thái receiver.

## 9. Các giới hạn do kiểu biến quyết định

Ngay cả khi field không final và receiver writable, kiểu biến vẫn hạn chế một số mode.

### 9.1. CAS trên reference và cộng trên primitive là hai việc khác

Một `String` field có thể cho phép CAS (vì nó là một reference variable có thể gán lại), nhưng không có phép cộng nguyên tử `GET_AND_ADD` cho `String`. Một `int` field thường có các mode cộng và bitwise nguyên tử.

**Lưu ý về CAS trên reference:** So sánh expected value của CAS dựa trên **danh tính reference** (tương đương ý nghĩa `==` cho tham chiếu), không gọi `String.equals(...)` hay `Object.equals(...)`. Vì vậy nếu muốn CAS giá trị reference hiện tại, hãy dùng đúng object reference mong đợi; hai `String` có nội dung giống nhau nhưng là hai object khác nhau không tự coi là cùng expected value.

### 9.2. Thực hành 4 — Xác nhận capability theo kiểu `int` và `String`

Tạo tệp **`VarHandleCapabilityDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.VarHandle.AccessMode;

public class VarHandleCapabilityDemo {
    static class Record {
        int points = 5;
        String name = "old";
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        VarHandle points = lookup.findVarHandle(Record.class, "points", int.class);
        VarHandle name = lookup.findVarHandle(Record.class, "name", String.class);
        Record record = new Record();

        System.out.println("points ADD: " + points.isAccessModeSupported(AccessMode.GET_AND_ADD));
        System.out.println("points BITWISE_OR: " + points.isAccessModeSupported(AccessMode.GET_AND_BITWISE_OR));
        System.out.println("name CAS: " + name.isAccessModeSupported(AccessMode.COMPARE_AND_SET));
        System.out.println("name ADD: " + name.isAccessModeSupported(AccessMode.GET_AND_ADD));
        System.out.println("name BITWISE_OR: " + name.isAccessModeSupported(AccessMode.GET_AND_BITWISE_OR));
        if (points.isAccessModeSupported(AccessMode.GET_AND_ADD)) {
            int before = (int) points.getAndAdd(record, 3);
            System.out.println("points before add: " + before);
            System.out.println("points after add: " + (int) points.get(record));
        }
        System.out.println("name compareAndSet: "
                + name.compareAndSet(record, "old", "new"));
        System.out.println("name read: " + (String) name.get(record));
    }
}
```

```bash
javac --release 17 VarHandleCapabilityDemo.java
java VarHandleCapabilityDemo
```

**Stdout:**

```text
points ADD: true
points BITWISE_OR: true
name CAS: true
name ADD: false
name BITWISE_OR: false
points before add: 5
points after add: 8
name compareAndSet: true
name read: new
```

Ý nghĩa:

- `points` là `int` không-final: cộng nguyên tử và OR bitwise được hỗ trợ. `getAndAdd(record, 3)` trả giá trị cũ `5`, cập nhật thành `8`.
- `name` là `String` không-final: CAS được hỗ trợ, numeric/bitwise atomic update không phù hợp nên trả `false`.
- Trong ví dụ này, `name` ban đầu nhận literal `"old"`, còn expected `"old"` cũng là cùng interned string reference; CAS thành công. **Không suy rộng** rằng CAS dùng `equals` cho những object String khác nguồn.
- Mode support cho phép quyết định logic ở bước cấu hình/khởi tạo; khi gọi vẫn phải truyền đúng receiver, kiểu đối số và ngữ cảnh.

## 10. Giới hạn quyền truy cập khác giới hạn access mode

`MethodHandles.Lookup.findVarHandle` và `findStaticVarHandle` thực hiện **access checking** khi tìm field. Nếu không đủ quyền với class/private field/module, lookup có thể thất bại bằng `IllegalAccessException`; nếu field không tồn tại hoặc không đúng kiểu/staticness, có thể thất bại bằng `NoSuchFieldException`.

Khi bạn **đã có** VarHandle:

- `isAccessModeSupported(SET) == false` trên field `final` vẫn là false dù tạo handle bằng lookup có private access.
- `privateLookupIn` trong tình huống được phép có thể giúp tìm được field private, nhưng **không bãi bỏ quy tắc final**.
- `varType()` và `coordinateTypes()` giúp xác định kiểu, không quyết định quyền đọc/ghi của một receiver cụ thể.
- Với `static final`, việc tham chiếu tới field qua VarHandle để đọc không tự cấp quyền thay giá trị.
- Không có thao tác `setAccessible(true)` trên VarHandle để "bật" `SET` cho một final field.

Phân tích đúng theo ba câu hỏi độc lập:

```text
1. Có lấy được VarHandle không?
   -> quyền Lookup, tên và kiểu field

2. Handle có hỗ trợ mode cần dùng không?
   -> isAccessModeSupported(mode)

3. Lần access cụ thể có hợp lệ không?
   -> receiver, tọa độ, buffer read-only, bounds/alignment,
      kiểu call-site, trạng thái class/runtime
```

Nhờ phân tách ba lớp, công cụ sẽ báo lỗi chính xác hơn thay vì gom mọi trường hợp thành “biến này read-only”.

## 11. Xây dựng chính sách fallback an toàn

Một helper dùng trong code nhiều cấu hình runtime có thể làm theo trình tự:

1. Lấy đúng VarHandle và biết rõ nó truy cập **field hay element/view** nào.
2. Xác định mode tối thiểu đáp ứng yêu cầu: `GET` để đọc, `COMPARE_AND_SET` cho CAS, `GET_AND_ADD` cho cộng nguyên tử; đừng chọn mode mạnh hơn nếu không cần.
3. Kiểm tra `isAccessModeSupported(mode)` **trước khi** gắn mode vào một đường code bắt buộc hoạt động.
4. Nếu không hỗ trợ, chọn hợp đồng khác (chẳng hạn không cho cập nhật final field); nếu cần atomicity, không tự chuyển sang `get` rồi `set`.
5. Nếu mode được hỗ trợ, xác định đúng `coordinateTypes()` và trạng thái receiver cụ thể. Với ByteBuffer, kiểm tra `buffer.isReadOnly()` khi định ghi.
6. Xử lý ngoại lệ runtime phù hợp: index sai, buffer read-only, mismatch kiểu và các điều kiện do nhà cung cấp VarHandle định nghĩa.
7. Nếu xử lý đồng thời, duy trì quy tắc thứ tự bộ nhớ và cơ chế đồng bộ nhất quán trên toàn pipeline.

### 11.1. Mẫu kiểm tra đơn giản cho phép ghi

```java
// Fragment: fieldHandle là VarHandle đã có và state là receiver đúng kiểu.
if (!fieldHandle.isAccessModeSupported(VarHandle.AccessMode.SET)) {
    throw new UnsupportedOperationException("This variable is not writable");
}
fieldHandle.set(state, 42);
```

Đây là fragment không độc lập. Nếu fieldHandle truy cập `int` instance field, lệnh trên đúng hình dạng call-site. Tuy nhiên với **ByteBuffer view** cần thêm kiểm tra receiver read-only/bounds. Với `GET_AND_ADD` hoặc CAS còn cần chắc chắn loại mode thật sự hỗ trợ atomicity theo yêu cầu.

### 11.2. Không dùng nhánh fallback làm mất tính nguyên tử

Một cách **sai trong ứng dụng concurrent**:

```java
// Chống ví dụ, KHÔNG dùng làm phép tăng nguyên tử:
int old = (int) counter.get(state);
counter.set(state, old + 1);
```

Hai thread có thể đồng thời đọc cùng `old` rồi cùng ghi `old+1`, làm mất cập nhật. `getAndAdd` có một điểm nguyên tử theo nghĩa của thao tác; đọc–ghi riêng rẽ thì không.

Nếu `GET_AND_ADD` không được hỗ trợ vì field final, giải pháp đúng thường là **không cập nhật field đó**. Nếu mode không hỗ trợ vì kiểu biến hoặc nguồn biến, bạn cần thiết kế đồng bộ/loại dữ liệu khác, chứ không dùng một phép cộng thường như bản thay thế tương đương.

### 11.3. Đối với buffer read-only

Có thể kiểm tra trước:

```java
// Fragment: buffer là java.nio.ByteBuffer, view là VarHandle int view.
if (buffer.isReadOnly()) {
    throw new java.nio.ReadOnlyBufferException();
}
if (!view.isAccessModeSupported(VarHandle.AccessMode.SET)) {
    throw new UnsupportedOperationException("SET not supported");
}
view.set(buffer, 0, 123);
```

Đây chỉ là một **guard trong trường hợp buffer không đồng thời thay đổi trạng thái và tọa độ hợp lệ**; nó không thay mọi xử lý lỗi có thể có. Tương tự, `buffer.isReadOnly()` không bảo đảm buffer có capacity đủ lớn hay thao tác volatile không vi phạm alignment.

## 12. Những ngoại lệ dễ nhầm

| Ngoại lệ | Thời điểm thường gặp | Ý nghĩa |
| --- | --- | --- |
| `UnsupportedOperationException` | Gọi access mode mà `isAccessModeSupported(...) == false` | Mode không có triển khai hợp lệ cho VarHandle đó, ví dụ `SET` trên final field |
| `ReadOnlyBufferException` | Gọi access mode ghi trên buffer read-only | Mode có thể được hỗ trợ ở cấp VarHandle nhưng **receiver cụ thể** cấm ghi |
| `WrongMethodTypeException` | Chữ ký call-site không khớp access mode type | Sai kiểu/số tọa độ, kiểu new value, kiểu kết quả được cast trong lời gọi |
| `ClassCastException` | Một tham chiếu ở call-site không thể cast như yêu cầu | Sai kiểu object/reference runtime |
| `NullPointerException` | Dùng null cho receiver instance, array hoặc buffer bắt buộc tồn tại | Tọa độ null không chỉ tới biến hợp lệ |
| `ArrayIndexOutOfBoundsException` | Index phần tử mảng không hợp lệ | Sai tọa độ của `arrayElementVarHandle` |
| `IndexOutOfBoundsException` | ByteBuffer index/range không hợp lệ | Sai vùng byte của view |
| `IllegalStateException` | Một số access mode của buffer view có yêu cầu căn chỉnh không thỏa | Có mode được hỗ trợ nhưng địa chỉ/index không đủ alignment |
| `IllegalAccessException` | Trong quá trình `Lookup` khi không có quyền | Chưa lấy được VarHandle, không phải kết quả của `isAccessModeSupported` |
| `NoSuchFieldException` | Trong quá trình `Lookup` tìm tên/kiểu field sai | Chưa có handle để kiểm tra mode |

Các nguyên nhân cụ thể khác nhau tùy factory. Ví dụ mismatch kiểu có thể gây lỗi ở bước liên kết call-site trước khi bạn đi được tới logic cập nhật. **Không dùng `catch(Exception)` để coi mọi thất bại là “read-only”**: đó là đánh đồng bug chương trình với chính sách dữ liệu.

### 12.1. `GET` luôn được hỗ trợ nhưng không bảo đảm mọi lần đọc thành công

Ví dụ:

```java
// Fragment: id là VarHandle trên int instance field của State.
int value = (int) id.get(state);
```

Ngay cả khi `id.isAccessModeSupported(GET)` trả `true`, nếu `state == null` thì không có object chứa field; nếu bạn gọi sai kiểu tĩnh tại call-site, có thể xảy ra mismatch. `GET` được hỗ trợ chỉ nói **không gặp UnsupportedOperationException vì mode không được hỗ trợ**.

### 12.2. Đồng bộ và `final` là hai trục khác nhau

`VarHandle.getVolatile` có ngữ nghĩa read giống volatile, nhưng không có khả năng biến field `final` thành biến ghi được. `SET_RELEASE`, `SET_VOLATILE` hoặc CAS vẫn là **ghi/cập nhật**. Đồng thời, một field được khai báo `volatile` có thể được truy cập bằng `get` (plain), `getOpaque`, `getAcquire` hoặc `getVolatile`; chế độ truy cập được lựa chọn có quy tắc thứ tự bộ nhớ riêng, nên không được tự suy luận `volatile` ở khai báo bắt buộc mọi access qua VarHandle đều có cùng memory semantics.

Các ví dụ ở bài chạy đơn luồng để thấy capability/ngoại lệ; ứng dụng đa luồng cần lập luận theo Java Memory Model và chọn đúng mode cho mọi đường đọc/ghi liên quan.

## 13. Bảng quyết định nhanh

| Tình huống | Chọn handle nào? | Kiểm tra gì? | Kỳ vọng |
| --- | --- | --- | --- |
| Đọc `final int id` | `findVarHandle` của field `id` | `GET` (luôn supported) và tọa độ object | Đọc được nếu đủ quyền và receiver hợp lệ |
| Muốn `set` lên `final int id` | Cùng field handle | `SET` | `false`; không thể ghi bằng VarHandle |
| Muốn CAS trên `volatile int count` không-final | Field handle của `count` | `COMPARE_AND_SET`; type/receiver | Thường supported; xử lý expected value đúng |
| Tăng `int` bằng get-and-add | Field/array-element handle phù hợp | `GET_AND_ADD` | Kiểu `int` không-final thường supported |
| Ghi `final int[] values` qua field handle | Field handle của `values` | `SET` | `false`; field reference không gán lại |
| Sửa `values[0]` | `arrayElementVarHandle(int[].class)` | `SET`; array/index | Có thể ghi phần tử dù reference final |
| Ghi qua view của buffer đang read-only | `byteBufferViewVarHandle` | Cả support và `buffer.isReadOnly()` | Mode có thể true nhưng gọi ghi ném `ReadOnlyBufferException` |
| CAS trên `String` field | Field handle của `String` không-final | `COMPARE_AND_SET` | Có thể, so sánh reference thay vì `equals` |
| Cộng `String` qua `GET_AND_ADD` | Field handle của `String` | `GET_AND_ADD` | `false` |
| Tìm field private để đọc | Lookup có quyền phù hợp | Lookup access, sau đó support mode | Không vượt quyền chỉ bằng việc có enum AccessMode |

## 14. Lỗi thiết kế và thói quen cần tránh

1. **Gọi `set` trước, hỏi `isAccessModeSupported` sau.** Nếu mode bắt buộc để chạy đúng, hãy kiểm tra capability trước và fail sớm với thông điệp rõ ràng.
2. **Xem `isAccessModeSupported(SET)==true` là mọi instance đều writable.** Sai với ByteBuffer view trên một receiver `asReadOnlyBuffer()`.
3. **Cho rằng `final` cấm mọi biến bên trong object/mảng thay đổi.** `final` không tự deep-freeze state của object được tham chiếu.
4. **Cho rằng CAS là thao tác chỉ đọc.** CAS có thể ghi, nên final field không hỗ trợ.
5. **Cho rằng numeric/bitwise atomic mode có sẵn cho mọi reference field.** `String` field có thể CAS, nhưng không get-and-add.
6. **Nhầm kiểu field `int[]` với kiểu phần tử `int`.** Field handle và array-element handle có `varType()` và tọa độ khác nhau.
7. **Dùng `get()+set()` thay CAS/get-and-add mà không đồng bộ.** Điều này đánh mất atomicity.
8. **Cho rằng private lookup biến final thành mutable.** Lookup quyền truy cập và mode support là hai lớp khác nhau.
9. **Truyền sai tọa độ tới method signature-polymorphic.** Static field không cần receiver; instance field cần receiver; array element cần array và index.
10. **Xem `volatile` là đồng nghĩa với final hoặc luôn có cùng memory semantics ở mọi mode.** Mỗi access mode có quy tắc riêng.
11. **Bỏ qua checked/unchecked exception phù hợp.** `ReadOnlyBufferException` khác `UnsupportedOperationException`; sai index hoặc sai call-site cũng khác.
12. **Chỉ kiểm tra mode rồi cho rằng chương trình không còn lỗi.** Bounds, alignment, receiver, class loader/module và lifecycle vẫn là điều kiện runtime.
13. **Dùng literal string như expected value để mô phỏng CAS trên mọi object.** CAS reference so sánh danh tính, nên phải biết object thực tế đang chứa.
14. **Nghĩ read-only ByteBuffer là snapshot bất biến.** Nó chỉ cấm ghi qua view đó; một writer khác có thể đổi vùng dữ liệu chung nếu kiến trúc cho phép.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Trên một instance `final int id`, `isAccessModeSupported(GET)`, `isAccessModeSupported(SET)`, và `isAccessModeSupported(COMPARE_AND_SET)` thường trả những gì? Vì sao?

**Câu 2.** Nếu một static final field có VarHandle, cần truyền instance object vào `get(...)` không?

**Câu 3.** `final int[] values` không gán lại được, vậy tại sao `arrayElementVarHandle(int[].class).set(values, 0, 9)` lại có thể thành công?

**Câu 4.** Tại sao một VarHandle do `byteBufferViewVarHandle` tạo có thể báo `SET` supported, nhưng `set(readOnlyBuffer, ...)` lại ném `ReadOnlyBufferException`?

**Câu 5.** Có nên dùng `int old=(int) vh.get(...); vh.set(..., old+1);` như fallback cho `GET_AND_ADD` trong code đa luồng không?

**Câu 6.** `isAccessModeSupported(GET)` luôn true. Có phải `get(...)` không bao giờ ném ngoại lệ không?

**Câu 7.** Vì sao một `String` field không-final có thể hỗ trợ `COMPARE_AND_SET` nhưng không hỗ trợ `GET_AND_ADD`?

**Câu 8.** Trong CAS trên reference, hai object có cùng `equals(...) == true` có chắc được xem là cùng expected value không?

**Câu 9.** Phân biệt ba mức kiểm tra: quyền tạo VarHandle, khả năng hỗ trợ mode và điều kiện của lần access cụ thể.

**Câu 10.** Nếu field `volatile int count` được đọc bằng `get` và `getVolatile`, chúng có bắt buộc cùng ý nghĩa thứ tự bộ nhớ không?

**Gợi ý trả lời:**

1. `GET=true`, `SET=false`, `COMPARE_AND_SET=false`; final cho đọc nhưng không cho cập nhật.
2. Không, static field handle có **0 tọa độ**; dùng `get()`.
3. `final` giới hạn phép gán lại **field reference**, còn phần tử mảng là biến riêng được truy cập qua handle khác.
4. Capability phản ánh **loại VarHandle**; trạng thái read-only là của receiver buffer cụ thể, được kiểm tra lúc gọi.
5. Không nếu cần atomicity; đọc–ghi riêng rẽ có thể làm mất cập nhật.
6. Không; vẫn có lỗi tọa độ, kiểu call-site, null và runtime khác.
7. CAS có thể so sánh/gán lại reference, còn cộng nguyên tử không áp dụng cho `String`.
8. Không; CAS tham chiếu so sánh **identity**, không phải `equals`.
9. Lookup kiểm tra có thể lấy handle; `isAccessModeSupported` kiểm tra mode; access thực tế kiểm tra receiver/index/bounds/alignment/type.
10. Không; mode được gọi quyết định semantics truy cập VarHandle, không chỉ modifier nguồn.

## 16. Tài liệu chuẩn

- [Java SE 21 — `VarHandle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html): nhóm access mode, `isAccessModeSupported`, khả năng đọc, ngữ nghĩa lỗi khi mode không được hỗ trợ và kiểu tọa độ.
- [Java SE 21 — `VarHandle.AccessMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.AccessMode.html): các enum constant `GET`, `SET`, `COMPARE_AND_SET`, `GET_AND_ADD` và các biến thể.
- [Java SE 21 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVarHandle`, `findStaticVarHandle`, quyền truy cập và các mode bị hạn chế với final field.
- [Java SE 21 — `MethodHandles`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): `arrayElementVarHandle`, `byteBufferViewVarHandle` và các factory liên quan.
- [Java SE 21 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): buffer read-only, view chia sẻ lưu trữ, offset và byte order.
- [Java SE 21 — `ReadOnlyBufferException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ReadOnlyBufferException.html): lỗi khi cố thay đổi buffer chỉ đọc.
- [Java Language Specification 21 — `4.12.4 final Variables`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4): ý nghĩa của final variable và giới hạn gán lại.

**Kết luận:** Hãy phân biệt **mode có được VarHandle hỗ trợ không** với **biến/receiver thực tế có cho phép thao tác ở lần gọi này không**. `isAccessModeSupported` trả lời câu hỏi thứ nhất; `final` field làm các mode cập nhật không được hỗ trợ, trong khi một read-only `ByteBuffer` có thể từ chối `set` dù mode có hỗ trợ ở cấp view. Kiểm tra thêm kiểu biến, tọa độ, trạng thái receiver và hợp đồng nguyên tử để tránh biến một capability check thành giả định sai về tính ghi được.