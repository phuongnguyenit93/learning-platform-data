# 12.9 Phân biệt thay target với liên kết lại chỉ thị `invokedynamic` đã hoàn tất

**Một chỉ thị `invokedynamic` đã liên kết (linked) với một đối tượng `CallSite` không trở lại trạng thái chưa liên kết chỉ vì target của `CallSite` thay đổi.** Với `MutableCallSite` hoặc `VolatileCallSite`, bạn có thể thay `MethodHandle` đích bằng `setTarget(...)`; những lời gọi về sau đi qua chính call site đã liên kết đó và sử dụng target mới theo quy tắc quan sát cập nhật của loại call site. JVM **không gọi lại bootstrap method** để thực hiện hành động `setTarget`.

Bài này làm rõ ranh giới giữa **liên kết chỉ thị `invokedynamic`** (linkage, nối một vị trí lệnh với một `CallSite`) và **thay thế target của `CallSite`** (retargeting, thay một `MethodHandle` bên trong call site). Đây là hai cơ chế khác nhau, dù trong tài liệu của một số dynamic-language runtime người ta có thể gọi việc thay target là “relink” theo nghĩa **logic ứng dụng**.

> **Môi trường:** Java 17+. Bốn chương trình Java độc lập ở cuối các mục thực hành được kiểm thử bằng `javac --release 17` và thực thi thành công; riêng ví dụ nâng cao tạo một class file chứa **opcode `invokedynamic` thực sự**, không chỉ gọi `CallSite.dynamicInvoker()`. Các tình huống cập nhật target trong mã mẫu được chạy tuần tự để có đầu ra xác định. Khi triển khai đa luồng phải bổ sung quy tắc hiển thị bộ nhớ thích hợp.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Phân biệt **một lần liên kết vị trí lệnh `invokedynamic`** với **nhiều lần đổi `CallSite.target`** trên cùng vị trí đã liên kết.
- Giải thích vai trò của `CONSTANT_InvokeDynamic`, `BootstrapMethods`, `Lookup`, `invokedName`, `MethodType` và `CallSite` trong vòng đời điểm gọi động.
- Biết khi nào JVM chạy bootstrap method và vì sao gọi lại cùng điểm lệnh sau khi đã liên kết **không** tự kích hoạt bootstrap nữa.
- So sánh `ConstantCallSite`, `MutableCallSite` và `VolatileCallSite`; giải thích ý nghĩa của `MutableCallSite.syncAll(...)` và hiển thị cập nhật giữa các thread.
- Phân biệt `site.getTarget()` (lấy một handle cụ thể tại thời điểm đọc) và `site.dynamicInvoker()` (handle có thể gọi theo **target hiện hành**).
- Tránh hiểu sai `setTarget`, `syncAll`, `SwitchPoint.invalidateAll` và thuật ngữ “relink” trong framework.
- Nhận diện các giới hạn về kiểu `MethodType`, lỗi `WrongMethodTypeException`, các lời gọi đang chạy dở và các tình huống bootstrap bị thực thi đồng thời khi liên kết lần đầu.
- Đọc kết quả từ một class file tự tạo để thấy **đếm bootstrap không tăng** dù opcode `invokedynamic` tiếp tục gọi target mới.

## 2. Hai trục khác nhau: identity của `CallSite` và giá trị target

Hãy hình dung trạng thái của một vị trí lệnh:

```text
Class file: một lệnh invokedynamic cụ thể
    |
    | constant pool: invokedName + method descriptor
    | BootstrapMethods: bootstrap handle + static arguments
    |
    v
UNLINKED
    |
    | JVM giải quyết metadata, gọi bootstrap, nhận CallSite
    v
LINKED -----> CallSite S  (identity của S đã gắn với vị trí lệnh)
                type = (String)String   [cố định]
                target = T0            [có thể thay tùy subclass]
                    |
                    | S.setTarget(T1)  (nếu mutable/volatile)
                    v
                target = T1
                    |
                    | S.setTarget(T2)
                    v
                target = T2

Vị trí lệnh: vẫn LINKED tới đúng S; không chạy bootstrap lần nữa.
```

Phân biệt rõ:

1. **Liên kết chỉ thị (instruction linkage):** JVM liên kết một **vị trí bytecode `invokedynamic`** với **một `CallSite` object** do bootstrap trả về. Sau liên kết thành công, mối liên hệ này là cố định theo hợp đồng JVMS.
2. **Giá trị target trong `CallSite`:** là một `MethodHandle` có cùng `MethodType` với call site. Một vài loại `CallSite` cho phép thay handle này.
3. **Hành vi thực thi:** khi điểm gọi chạy, lời gọi được chuyển đến target theo trạng thái call site và semantics nhất quán của loại call site. Method đích chạy có thể thay đổi mặc dù cấu trúc class file, vị trí opcode và identity call site không đổi.

**Điểm mấu chốt:** “một lệnh được liên kết vĩnh viễn” không có nghĩa “method implementation chạy ở lệnh đó phải vĩnh viễn là cùng một `MethodHandle`” nếu bootstrap đã trả về một `MutableCallSite` hoặc `VolatileCallSite`.

### 2.1. Đừng đồng nhất “linked” với “target không thay”

Các ví dụ diễn đạt đúng:

- “Lệnh `invokedynamic` vẫn liên kết với `MutableCallSite S`, nhưng `S` nay trỏ target mới.”
- “Target thay đổi sau `setTarget`; bootstrap method không chạy lại.”
- “Một `ConstantCallSite` không cho thay target, nhưng đây là chính sách của **loại call site**.”
- “`syncAll` công bố cập nhật target giữa các thread; nó không reset trạng thái liên kết bytecode.”

Các cách diễn đạt dễ gây hiểu sai:

- “`setTarget` khiến JVM hủy liên kết rồi gọi bootstrap lại.”
- “Sau lần đầu, `invokedynamic` luôn gọi cùng method gốc trong mọi trường hợp.”
- “`VolatileCallSite` relink liên tục vì lần nào cũng phải đọc target.”
- “Tạo `CallSite` bằng constructor Java là tạo ngay một opcode `invokedynamic`.”

## 3. Vòng đời liên kết một lệnh `invokedynamic`

Về mặt class file, operand của `invokedynamic` trỏ tới một `CONSTANT_InvokeDynamic_info` trong constant pool. Entry này chứa chỉ số một mục `BootstrapMethods` và tham chiếu `NameAndType` có **tên điểm gọi** cùng **JVM method descriptor**.

Quy trình khái niệm:

```text
Trước lần chạy đầu:
  invokedynamic instruction -> UNLINKED

Khi cần chạy:
  1. Xác định symbolic name và method type từ constant pool.
  2. Resolve bootstrap method handle và các static arguments.
  3. Gọi bootstrap(caller Lookup, invokedName, invokedType, ...staticArgs).
  4. Bootstrap trả CallSite S có type đúng với invokedType.
  5. JVM chốt liên kết vị trí lệnh -> S.
  6. Dùng target của S để hoàn thành lời gọi.

Những lần chạy tiếp theo:
  invokedynamic instruction -> S -> target hiện hành theo loại CallSite
  [không tự lặp bước 1-5]
```

Bootstrap **không** được gọi với các đối số runtime của method đích như một lần method invocation thông thường. Nó nhận metadata `Lookup`, `String invokedName`, `MethodType invokedType` và static arguments từ `BootstrapMethods` để **thiết lập call site**. Runtime arguments được truyền về sau cho target của call site.

### 3.1. Liên kết gắn với vị trí lệnh, không chỉ với constant-pool entry

Nhiều opcode `invokedynamic` có thể dùng chung một constant-pool entry, nhưng theo JVMS, mỗi **vị trí lệnh** có trạng thái liên kết riêng. Vì vậy:

- **Một vị trí lệnh** đã liên kết thành công không tự relink khi chạy lần thứ hai.
- **Hai vị trí lệnh khác nhau** có thể đều yêu cầu bootstrap riêng, ngay cả khi cùng chỉ số constant pool.
- Hai bootstrap invocations cũng có thể trả **cùng một `CallSite` object** có chủ ý; khi đó nhiều vị trí lệnh liên kết tới cùng object và cùng bị ảnh hưởng bởi thay target của nó.
- Ngược lại, mỗi vị trí có thể liên kết tới **một `CallSite` riêng**, độc lập với vị trí khác.

Nói “một lần bootstrap cho cả class” hoặc “một lần bootstrap cho mỗi constant-pool entry” là không chính xác.

### 3.2. Trường hợp nhiều thread cùng chạm site chưa liên kết

Ở **đợt liên kết ban đầu**, nếu nhiều thread đua nhau chạy cùng một chỉ thị `invokedynamic` chưa linked, JVMS cho phép bootstrap **được thực thi đồng thời nhiều lần**. JVM chọn một kết quả bootstrap phù hợp để cài cho vị trí lệnh; các kết quả còn lại bị bỏ qua.

Do đó cần phân biệt:

- **Đúng:** Sau khi liên kết thành công hoàn tất, không có API thông thường để đưa **chính vị trí lệnh đó** về UNLINKED rồi gọi bootstrap lại.
- **Không đúng trong mọi cuộc đua:** “Bootstrap method chắc chắn được thực thi đúng một lần trong toàn bộ vòng đời.” Nó có thể chạy nhiều lần **trong race trước khi cài kết quả liên kết**, dù chỉ một kết quả được dùng.
- **Trách nhiệm thiết kế:** Bootstrap có side effect (đăng ký listener, cấp tài nguyên, tăng counter...) phải tính đến concurrent linkage.

Trong **ví dụ thực hành 4**, mọi lời gọi ở cùng một thread, không có race; bộ đếm bootstrap bằng 1 sau khi thực hiện lời gọi đầu và **vẫn bằng 1** sau mọi lần retarget.

### 3.3. Thất bại liên kết không tự được thử lại như một “relink”

Nếu bootstrap thất bại, JVM áp dụng quy tắc lỗi liên kết (có thể phát sinh `BootstrapMethodError`, tùy nguyên nhân). Đối với một vị trí `invokedynamic` đã resolve thất bại, lỗi được ghi nhận theo JVMS thay vì dùng `setTarget` để chữa lỗi trên một `CallSite` chưa từng được cài. Việc bootstrap trả một `CallSite` đúng kiểu và kết thúc thành công khác với chuyện target bên trong nó có thể tự ném exception khi chạy.

Đừng gộp hai loại lỗi:

- **Lỗi liên kết:** bootstrap không giải quyết được symbolic metadata, trả null/sai type, hoặc ném lỗi; JVM chưa thiết lập liên kết thành công.
- **Lỗi khi invoke target sau liên kết:** target hiện tại ném exception, việc cập nhật target có vấn đề, hoặc caller truyền sai kiểu; liên kết của opcode không vì vậy tự bị hủy.

## 4. Ba loại `CallSite` và khả năng thay target

| Loại | `setTarget(newTarget)` | Khi opcode đã linked | Khả năng quan sát cập nhật đa luồng |
| --- | --- | --- | --- |
| `ConstantCallSite` | **Luôn từ chối** với `UnsupportedOperationException` | Luôn sử dụng target cố định | Không có cập nhật target để đồng bộ |
| `MutableCallSite` | **Cho phép** khi type tương đương | Dùng target hiện tại của object đã linked | Giống ghi/đọc biến thường; cần `syncAll` hoặc đồng bộ phù hợp để bảo đảm công bố đến các reader |
| `VolatileCallSite` | **Cho phép** khi type tương đương | Dùng target hiện tại của object đã linked | `setTarget`/`getTarget` như ghi/đọc `volatile`; cập nhật được quan sát theo semantics volatile |

Cả ba đều là `java.lang.invoke.CallSite`. Chúng không phải ba biến thể opcode bytecode: **một opcode `invokedynamic` có thể liên kết với bất kỳ loại nào** nếu bootstrap trả đối tượng đáp ứng hợp đồng kiểu.

### 4.1. `ConstantCallSite`: đích cố định không phải “liên kết nhiều lần”

`new ConstantCallSite(target)` giữ target vĩnh viễn. `getTarget()` và `dynamicInvoker()` trả về handle cố định. Gọi `setTarget(...)` trên constant site ném `UnsupportedOperationException`, ngay cả khi bạn đề xuất một target mới có **đúng type**.

Điều này phù hợp cho bootstrap tạo hành vi không cần cập nhật. “Không có retarget” là do **chọn `ConstantCallSite`**; không nên suy ra rằng mọi `CallSite` đều cố định như vậy.

### 4.2. `MutableCallSite`: trạng thái target thay đổi như biến thường

`MutableCallSite` được thiết kế cho site có target thay đổi sau liên kết. `setTarget(newTarget)` cập nhật một trường target theo semantics của biến Java thông thường (không mặc nhiên có volatile visibility).

Trong **cùng thread**, bạn có thể thấy target mới ngay ở lời gọi tiếp theo. Nhưng **giữa các thread**:

- Một thread khác có thể giữ/cached target cũ nếu không có đồng bộ đủ.
- `setTarget` đơn lẻ **không bảo đảm** mọi thread đang chạy lập tức nhìn target mới.
- `MutableCallSite.syncAll(new MutableCallSite[]{site})` là thao tác đồng bộ chuyên biệt giúp các reader ở những thread khác chấp nhận target mới.
- `syncAll` có thể tốn chi phí; thường nên gộp các site cần công bố trong cùng một mảng hơn là gọi liên tục cho từng thay đổi nhỏ.
- `syncAll` **không thu hồi hoặc chạy ngược** những lời gọi đã bắt đầu dùng target cũ.

Theo tài liệu Java, khi thiết kế cập nhật nhiều site, nên điều phối `setTarget` và `syncAll` bằng cơ chế loại trừ tương hỗ phù hợp để tránh cập nhật đua nhau.

**Không gọi `syncAll` là bootstrap.** Nó chỉ thực hiện thao tác đồng bộ/visibility đối với target của các `MutableCallSite` hiện hữu; có thể khiến runtime/compiler phải điều chỉnh cache/optimization, nhưng không thay lại cấu trúc `CONSTANT_InvokeDynamic` hoặc cài `CallSite` mới cho opcode.

### 4.3. `VolatileCallSite`: cập nhật như biến `volatile`

`VolatileCallSite` có `getTarget`/`setTarget` theo volatile memory semantics. Mỗi lần quan sát target có yêu cầu nhận biết các ghi target mới theo quy tắc volatile; không có API `VolatileCallSite.syncAll(...)` vì thao tác trên chính target đã dùng volatile semantics.

Điều này hữu ích nếu target được cập nhật thường xuyên và nhiều thread cần nhận biết thay đổi đáng tin cậy. Đổi lại, đọc target với yêu cầu volatile có thể đắt hơn `MutableCallSite` trong một số cấu hình tối ưu hóa.

**Cảnh báo:** “Thấy cập nhật mới” không có nghĩa bất kỳ lời gọi đang chạy dở nào cũng phải chuyển sang target mới ở giữa method body. Một invocation đã bắt đầu trên target cũ có thể hoàn thành trên target cũ, tương tự nhiều thiết kế cập nhật con trỏ/hàm khác.

### 4.4. Định nghĩa `CallSite.type()` là bất biến

Cả ba loại site có một `MethodType` bất biến: số lượng, thứ tự và kiểu tham số, cùng kiểu trả về. `site.setTarget(targetB)` chỉ hợp lệ nếu:

```java
// Fragment: site là MutableCallSite hoặc VolatileCallSite hợp lệ.
site.type().equals(targetB.type());
```

Đoạn trên minh họa điều kiện kiểm tra, không phải chương trình độc lập.

Nếu target mới sai type, `setTarget` ném `WrongMethodTypeException`. Không có tự động chuyển đổi `(Object)String` thành `(String)String` ở `setTarget`. Nếu hợp đồng cho phép chuyển đổi, có thể tạo adapter `newTarget.asType(site.type())` rồi mới thay:

```java
// Fragment: các chuyển đổi phải hợp lệ, không được mặc định luôn thành công.
MethodHandle adapted = candidate.asType(site.type());
site.setTarget(adapted);
```

Cần lựa chọn chuyển đổi cẩn thận; các phép cast reference có thể gây `ClassCastException` khi chạy. Chính bất biến `CallSite.type()` cho phép bytecode giữ nguyên descriptor dù target có thể đổi.

## 5. `getTarget()` và `dynamicInvoker()`: snapshot hay đường gọi sống?

Đây là khác biệt thực hành quan trọng nhất.

```text
MutableCallSite site:  target = T0

MethodHandle snapshot = site.getTarget();     // lấy T0
MethodHandle live     = site.dynamicInvoker(); // luôn đi qua site

Sau site.setTarget(T1):

snapshot.invokeExact(...) -> T0
live.invokeExact(...)     -> T1 (theo visibility)
```

`getTarget()` trả về một **MethodHandle value cụ thể** tại lúc đọc target; khi giữ lại biến `snapshot`, biến đó không tự cập nhật thành handle mới. Nó có thể biểu diễn một phương thức vẫn truy cập dữ liệu mutable bên ngoài, nhưng bản thân **reference tới target handle** đã lấy ra không tự đổi theo `site.setTarget`.

`dynamicInvoker()` trả một method handle có cơ chế gọi **qua site**; với mutable/volatile site, những lời gọi về sau sử dụng target được quan sát ở thời điểm gọi. Theo Javadoc, nó tương đương một `invokedynamic` đã liên kết với call site đó.

**Lưu ý quan trọng:** Gọi `site.dynamicInvoker()` trong source Java **không tự sinh** một instruction `invokedynamic` trong bytecode của người gọi. Nó giúp bạn thử hành vi tương đương trên object `CallSite` đã có. Nếu muốn **chứng minh bootstrap và liên kết bytecode thực**, cần có lệnh `invokedynamic` thực sự, như ví dụ 4.

Đối với `ConstantCallSite`, `dynamicInvoker()` có thể trả luôn permanent target vì nó không bao giờ thay; hai trường hợp dễ nhầm ở mutable/volatile không phát sinh ở constant site.

## 6. Thực hành 1: thay target `MutableCallSite` không làm đổi `CallSite.type()`

Tạo tệp **`MutableTargetDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.WrongMethodTypeException;

public final class MutableTargetDemo {
    static String oldRoute(String value) {
        return "old:" + value;
    }

    static String newRoute(String value) {
        return "new:" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(
                String.class, String.class);
        MethodHandle oldTarget = lookup.findStatic(
                MutableTargetDemo.class, "oldRoute", signature);
        MethodHandle newTarget = lookup.findStatic(
                MutableTargetDemo.class, "newRoute", signature);

        MutableCallSite site = new MutableCallSite(oldTarget);
        MethodHandle live = site.dynamicInvoker();
        MethodHandle snapshot = site.getTarget();

        System.out.println("site type: " + site.type());
        System.out.println("before: " + (String) live.invokeExact("A"));
        site.setTarget(newTarget);
        MutableCallSite.syncAll(new MutableCallSite[]{site});
        System.out.println("after: " + (String) live.invokeExact("B"));
        System.out.println("snapshot: " + (String) snapshot.invokeExact("C"));
        System.out.println("type unchanged: " + site.type().equals(signature));

        try {
            site.setTarget(MethodHandles.constant(String.class, "wrong type"));
        } catch (WrongMethodTypeException error) {
            System.out.println("type mismatch: "
                    + error.getClass().getSimpleName());
        }
        System.out.println("still new: " + (String) live.invokeExact("D"));
    }
}
```

Lệnh Java 17+:

```bash
javac --release 17 MutableTargetDemo.java
java MutableTargetDemo
```

**Stdout đã kiểm chứng:**

```text
site type: (String)String
before: old:A
after: new:B
snapshot: old:C
type unchanged: true
type mismatch: WrongMethodTypeException
still new: new:D
```

Giải thích từng dòng:

1. `new MutableCallSite(oldTarget)` tạo site có kiểu `(String)String` và target `oldRoute`.
2. `live.invokeExact("A")` đi qua site đến `oldRoute`, trả `old:A`.
3. `site.setTarget(newTarget)` thay con trỏ target, **không tạo site mới**. `syncAll` làm thao tác đồng bộ; trong ví dụ một thread, thao tác này không nhằm chứng minh race đa luồng.
4. `live.invokeExact("B")` đi qua site hiện tại, gọi `newRoute` để trả `new:B`.
5. `snapshot` đã lấy `oldTarget` bằng `getTarget()` trước khi đổi, nên khi gọi vẫn trả `old:C`.
6. `site.type()` vẫn là `(String)String`. Một handle `()String` từ `MethodHandles.constant(...)` không tương thích, nên `setTarget` ném `WrongMethodTypeException`; target hiện tại vẫn là `newRoute`.

Ví dụ **chứng minh retarget của CallSite** nhưng chưa có opcode `invokedynamic` tùy biến. Nó chủ động dùng `dynamicInvoker()` để mô phỏng lời gọi của một lệnh đã liên kết.

## 7. Thực hành 2: `VolatileCallSite` giữ live target và không cần `syncAll`

Tạo tệp **`VolatileTargetDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VolatileCallSite;

public final class VolatileTargetDemo {
    static int addOne(int value) {
        return value + 1;
    }

    static int addHundred(int value) {
        return value + 100;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(int.class, int.class);
        MethodHandle first = lookup.findStatic(
                VolatileTargetDemo.class, "addOne", signature);
        MethodHandle second = lookup.findStatic(
                VolatileTargetDemo.class, "addHundred", signature);

        VolatileCallSite site = new VolatileCallSite(first);
        MethodHandle live = site.dynamicInvoker();
        MethodHandle snapshot = site.getTarget();

        System.out.println("site type: " + site.type());
        System.out.println("before: " + (int) live.invokeExact(5));
        site.setTarget(second);
        System.out.println("after: " + (int) live.invokeExact(5));
        System.out.println("snapshot: " + (int) snapshot.invokeExact(5));
        System.out.println("current target: " + (int) site.getTarget().invokeExact(5));
    }
}
```

```bash
javac --release 17 VolatileTargetDemo.java
java VolatileTargetDemo
```

**Stdout đã kiểm chứng:**

```text
site type: (int)int
before: 6
after: 105
snapshot: 6
current target: 105
```

- Cả `addOne` và `addHundred` đều có type `(int)int` nên `setTarget` hợp lệ.
- `live` gọi target mới sau cập nhật, trong khi `snapshot` vẫn gọi target đã lấy trước đó.
- `site.getTarget()` ở thời điểm sau đọc target `addHundred`. Theo API, các lần đọc/ghi target của `VolatileCallSite` có semantics như trường `volatile`.
- Demo một thread có kết quả xác định, nhưng không tự chứng minh mọi interleaving của hai thread. Khác biệt volatile cần được hiểu qua Java Memory Model/Javadoc, không thể suy ra chỉ từ output.

## 8. Thực hành 3: `ConstantCallSite` và target khởi tạo dạng “chưa sẵn sàng”

Tạo tệp **`ConstantAndBlankDemo.java`**:

```java
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;

public final class ConstantAndBlankDemo {
    static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle fixed = MethodHandles.constant(String.class, "fixed");
        ConstantCallSite constant = new ConstantCallSite(fixed);
        System.out.println("constant: " + (String) constant.dynamicInvoker().invokeExact());
        try {
            constant.setTarget(MethodHandles.constant(String.class, "other"));
        } catch (UnsupportedOperationException error) {
            System.out.println("constant retarget: "
                    + error.getClass().getSimpleName());
        }
        System.out.println("still constant: "
                + (String) constant.dynamicInvoker().invokeExact());

        MethodType signature = MethodType.methodType(int.class, int.class);
        MutableCallSite blank = new MutableCallSite(signature);
        MethodHandle live = blank.dynamicInvoker();
        System.out.println("blank type: " + blank.type());
        try {
            int result = (int) live.invokeExact(4);
            System.out.println(result);
        } catch (IllegalStateException error) {
            System.out.println("blank invoke: " + error.getClass().getSimpleName());
        }
        MethodHandle actual = MethodHandles.lookup().findStatic(
                ConstantAndBlankDemo.class, "twice", signature);
        blank.setTarget(actual);
        System.out.println("initialized invoke: " + (int) live.invokeExact(4));
    }
}
```

```bash
javac --release 17 ConstantAndBlankDemo.java
java ConstantAndBlankDemo
```

**Stdout đã kiểm chứng:**

```text
constant: fixed
constant retarget: UnsupportedOperationException
still constant: fixed
blank type: (int)int
blank invoke: IllegalStateException
initialized invoke: 8
```

Hai điểm dễ bỏ qua:

- `ConstantCallSite.setTarget` **luôn** từ chối, bất kể type của target đề xuất. Lệnh `dynamicInvoker` của constant site trả lại permanent target.
- `new MutableCallSite(signature)` tạo một **CallSite object đã tồn tại**, có type `(int)int`, nhưng target khởi tạo là một handle **ném `IllegalStateException` khi invoke**. Gọi `blank.setTarget(actual)` sau đó thay target để sử dụng bình thường.

Đừng gọi target ban đầu dạng throwing handle này là **trạng thái UNLINKED của một chỉ thị `invokedynamic`**. Một bootstrap có thể trả về `MutableCallSite` dạng đó để liên kết một opcode; sau khi JVM nhận nó, opcode **đã linked** dù target đầu chưa làm việc hữu ích. Vì vậy câu “target chưa sẵn sàng” không giống câu “opcode chưa liên kết”.

## 9. Thực hành 4: một opcode `invokedynamic` thực sự, bootstrap đếm được

Ba demo trước kiểm tra API `CallSite` qua `dynamicInvoker()`. Demo này đi thêm một bước: **tự tạo class file hợp lệ trong bộ nhớ ở Java 17**, định nghĩa nó bằng `MethodHandles.Lookup.defineClass`, rồi thực thi method có opcode `invokedynamic`. Bootstrap do chính chương trình cung cấp tăng biến đếm mỗi khi JVM gọi nó.

Tất cả nằm trong **một tệp Java**, không cần dependency ASM, Byte Buddy hay cờ `--add-exports`. Chương trình không ghi `.class` của class được sinh ra ra đĩa; bytecode được tạo bằng `DataOutputStream`, sau đó nạp trong memory. Đây là ví dụ nâng cao để kiểm chứng **lifecycle linkage**, không phải mẫu khuyến nghị để tự viết bytecode trong ứng dụng thông thường.

### 9.1. Sơ đồ class được tạo

```text
GeneratedIndyW15
  public static String call(String s)
      aload_0
      invokedynamic #18, 0
      areturn

Constant pool:
  #18 = InvokeDynamic bootstrap_method_attr_index=0
                       name_and_type_index=17
  #17 = NameAndType "route" : (Ljava/lang/String;)Ljava/lang/String;
  #15 = MethodHandle REF_invokeStatic
                      RealIndyRetargetDemo.bootstrap

BootstrapMethods:
  [0] bootstrap_method_ref=#15, bootstrap_arguments=[]

Khi JVM gặp invokedynamic lần đầu:
  bootstrap(Lookup for GeneratedIndyW15, "route", (String)String)
      -> MutableCallSite S có target oldRoute

Lần đầu / thứ hai: S -> oldRoute
Sau S.setTarget(newRoute); syncAll([S]):
  chính invokedynamic #18 này -> S -> newRoute
  KHÔNG invoke lại bootstrap
```

Các index trên là **chỉ số do chính mã generator bên dưới cố định**; chúng không phải ví dụ suy đoán từ javac khác.

### 9.2. Toàn bộ `RealIndyRetargetDemo.java`

Tạo tệp **`RealIndyRetargetDemo.java`** với nội dung:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.reflect.Method;

public final class RealIndyRetargetDemo {
    private static int bootstrapCalls;
    private static MutableCallSite linkedSite;

    public static String oldRoute(String s) {
        return "old:" + s;
    }

    public static String newRoute(String s) {
        return "new:" + s;
    }

    public static CallSite bootstrap(MethodHandles.Lookup caller,
                                     String name,
                                     MethodType type) throws Throwable {
        bootstrapCalls++;
        System.out.println("bootstrap caller: " + caller.lookupClass().getSimpleName());
        System.out.println("bootstrap name: " + name);
        System.out.println("bootstrap type: " + type);
        MethodHandle target = MethodHandles.lookup().findStatic(
                RealIndyRetargetDemo.class, "oldRoute", type);
        linkedSite = new MutableCallSite(target);
        return linkedSite;
    }

    private static void utf(DataOutputStream out, String s) throws Exception {
        out.writeByte(1);
        out.writeUTF(s);
    }

    private static void cpClass(DataOutputStream out, int name) throws Exception {
        out.writeByte(7);
        out.writeShort(name);
    }

    private static void cpNameType(DataOutputStream out, int name, int type)
            throws Exception {
        out.writeByte(12);
        out.writeShort(name);
        out.writeShort(type);
    }

    private static byte[] makeClass() throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.writeInt(0xCAFEBABE);
        out.writeShort(0);
        out.writeShort(61);          // Java 17
        out.writeShort(19);          // 18 entries, 1-based
        utf(out, "GeneratedIndyW15");      // #1
        cpClass(out, 1);                   // #2
        utf(out, "java/lang/Object");      // #3
        cpClass(out, 3);                   // #4
        utf(out, "Code");                  // #5
        utf(out, "call");                  // #6
        utf(out, "(Ljava/lang/String;)Ljava/lang/String;"); // #7
        utf(out, "BootstrapMethods");      // #8
        utf(out, "bootstrap");             // #9
        utf(out, "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/invoke/MethodType;)"
                + "Ljava/lang/invoke/CallSite;");          // #10
        utf(out, "RealIndyRetargetDemo");  // #11
        cpClass(out, 11);                  // #12
        cpNameType(out, 9, 10);            // #13
        out.writeByte(10);                 // #14 Methodref
        out.writeShort(12);
        out.writeShort(13);
        out.writeByte(15);                 // #15 MethodHandle
        out.writeByte(6);                  // REF_invokeStatic
        out.writeShort(14);
        utf(out, "route");                 // #16
        cpNameType(out, 16, 7);            // #17
        out.writeByte(18);                 // #18 InvokeDynamic
        out.writeShort(0);                 // BootstrapMethods[0]
        out.writeShort(17);                // NameAndType #17

        out.writeShort(0x0021);            // public, super
        out.writeShort(2);                 // this_class
        out.writeShort(4);                 // super_class
        out.writeShort(0);                 // interfaces
        out.writeShort(0);                 // fields
        out.writeShort(1);                 // methods

        out.writeShort(0x0009);            // public static call
        out.writeShort(6);                 // name "call"
        out.writeShort(7);                 // descriptor
        out.writeShort(1);                 // one method attribute
        out.writeShort(5);                 // "Code"
        out.writeInt(19);                  // code attribute length
        out.writeShort(1);                 // max_stack
        out.writeShort(1);                 // max_locals
        out.writeInt(7);                   // code_length
        out.writeByte(0x2A);               // aload_0
        out.writeByte(0xBA);               // invokedynamic
        out.writeShort(18);                // CP #18
        out.writeShort(0);                 // mandatory zero bytes
        out.writeByte(0xB0);               // areturn
        out.writeShort(0);                 // exception table length
        out.writeShort(0);                 // Code subattributes

        out.writeShort(1);                 // class attributes
        out.writeShort(8);                 // BootstrapMethods
        out.writeInt(6);                   // attribute length
        out.writeShort(1);                 // one bootstrap entry
        out.writeShort(15);                // MethodHandle #15
        out.writeShort(0);                 // zero bootstrap arguments
        out.flush();
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws Throwable {
        Class<?> generated = MethodHandles.lookup().defineClass(makeClass());
        Method method = generated.getMethod("call", String.class);

        System.out.println("before first: " + bootstrapCalls);
        System.out.println("first: " + method.invoke(null, "A"));
        System.out.println("after first: " + bootstrapCalls);
        System.out.println("second: " + method.invoke(null, "B"));
        System.out.println("after second: " + bootstrapCalls);

        MethodType sameType = MethodType.methodType(String.class, String.class);
        linkedSite.setTarget(MethodHandles.lookup().findStatic(
                RealIndyRetargetDemo.class, "newRoute", sameType));
        MutableCallSite.syncAll(new MutableCallSite[]{linkedSite});
        System.out.println("after target change: " + method.invoke(null, "C"));
        System.out.println("after change bootstrap count: " + bootstrapCalls);
    }
}
```

Chạy:

```bash
javac --release 17 RealIndyRetargetDemo.java
java RealIndyRetargetDemo
```

**Stdout chính xác đã kiểm chứng trên JDK:**

```text
before first: 0
bootstrap caller: GeneratedIndyW15
bootstrap name: route
bootstrap type: (String)String
first: old:A
after first: 1
second: old:B
after second: 1
after target change: new:C
after change bootstrap count: 1
```

### 9.3. Tại sao đây là bằng chứng trực tiếp?

1. `makeClass()` tạo một class file Java 17 (major version `61`), với method `call(String)String` gồm `aload_0`, `invokedynamic` và `areturn`. Không có instruction gọi thẳng `oldRoute` hoặc `newRoute` trong bytecode của generated method.
2. `CONSTANT_InvokeDynamic` tại entry `#18` trỏ tới bootstrap record `0`; bootstrap handle trong record đó tham chiếu `RealIndyRetargetDemo.bootstrap`. Vì vậy **JVM thực sự gọi bootstrap**, chứ không phải `main` tự gọi hàm đó.
3. `bootstrap(...)` in ra class caller, tên site và type mà JVM đưa vào; sau đó trả một `MutableCallSite` đang trỏ tới `oldRoute`.
4. Trước lần gọi đầu, biến đếm bằng `0`. Lần gọi đầu tăng lên `1` và trả `old:A`.
5. Lần gọi tiếp theo chạy **cùng method, cùng vị trí opcode** và trả `old:B`; đếm bootstrap vẫn `1`.
6. `linkedSite.setTarget(newRoute)` cập nhật target của **CallSite đã được JVM liên kết trước đó**. `syncAll` công bố thay đổi target, không thay bootstrap metadata.
7. Lần gọi thứ ba tới chính method `GeneratedIndyW15.call("C")` trả `new:C`, trong khi `bootstrapCalls` **vẫn bằng 1**. Vị trí lệnh vẫn liên kết với cùng `linkedSite`.

Ví dụ chạy đơn luồng nên bộ đếm `int` đơn giản đủ minh họa. Trong một ví dụ có nhiều thread đua tới *first linkage*, phải dùng bộ đếm thread-safe nếu muốn ghi nhận mọi bootstrap execution và không nên mong số đếm luôn là 1.

**Lưu ý bảo mật/kỹ thuật:** Tạo class file bằng tay là kỹ thuật giáo dục. Trong hệ thống thực tế, nên dùng compiler/bytecode library phù hợp, kiểm soát quyền `Lookup.defineClass` và class loader. Không sửa bytecode của lớp đang chạy hoặc tự ý dùng `--add-opens` để né chính sách module chỉ nhằm retarget một call site.

## 10. “Relink” trong dynamic-language framework: thuật ngữ hay thao tác JVM?

Trong một dynamic language runtime, bạn có thể gặp tên như `relinkCallSite`, `linkAndGetTarget`, hoặc “relink fallback”. Những tên này thường chỉ hoạt động cấp **framework**:

```text
Một invokedynamic đã linked -> MutableCallSite S
                               |
                               v
                          target T0
                               |
                       một guard thất bại
                               |
                               v
                     fallback / resolver
                               |
                      tính ra target T1
                               |
                               v
                       S.setTarget(T1)
                               |
                         syncAll nếu cần
                               |
                               v
                         tiếp tục qua T1
```

Đó là **chạy lại thuật toán chọn target** của framework và **thay target**; không nhất thiết có lần liên kết `invokedynamic` thứ hai ở cấp JVMS. Trong báo cáo kỹ thuật nên ghi rõ:

- “Framework relink: computed a new target and called `MutableCallSite.setTarget`.”
- “JVMS invokedynamic linkage: unchanged; the instruction stays associated with the original CallSite.”

Nếu triển khai công cụ quan sát, hãy đặt **hai counter riêng**: số lần JVM gọi BSM (initial linkage attempts), và số lần framework tính lại/cài target. Không gom hai loại số liệu thành “link count”.

### 10.1. Invalidate guard không đồng nghĩa reset bootstrap

`SwitchPoint` cho phép các `MethodHandle` guard chọn một nhánh trước/sau khi bị invalidated. `SwitchPoint.invalidateAll(...)` có thể khiến một đường gọi chuyển sang fallback, và fallback có thể tự tạo/cài target mới. Nhưng invalidating switch point **không** đưa opcode `invokedynamic` về UNLINKED; liên kết `instruction -> CallSite` vẫn nguyên.

Tương tự:

- `MutableCallSite.syncAll(...)` công bố target mới cho các reader.
- `VolatileCallSite.setTarget(...)` thay target với volatile semantics.
- `MethodHandle.asType(...)` tạo adapter.
- `MethodHandles.guardWithTest(...)` tạo handle điều phối.

Không thao tác nào trong nhóm này tự trở thành “re-execute bootstrap for an already-linked instruction”.

### 10.2. Còn class redefinition hoặc class loader mới?

Tải **một class mới** bằng class loader khác có thể tạo ra **những vị trí `invokedynamic` mới** với vòng đời liên kết riêng. Điều đó không phải phép undo linkage của vị trí lệnh cũ.

Các cơ chế Instrumentation/hot-swap/class redefinition nằm ở tầng VM/tooling khác; không nên dùng chúng làm bằng chứng rằng `setTarget` tự relink hoặc JVM hứa tái chạy BSM của site cũ. Khi debug, hãy tách rõ “đang nói về cùng vị trí lệnh thuộc cùng phiên bản class hay không”.

## 11. Khi nào callback nhìn target cũ, mới hoặc lỗi?

### 11.1. Lời gọi đã bắt đầu trước khi cập nhật

Giả sử thread A bắt đầu chạy target `T0`, thread B sau đó thực hiện `site.setTarget(T1)`:

- Việc cài `T1` **không** hủy invocation của `T0` đang diễn ra.
- Những lần gọi **sau khi cập nhật được quan sát** sẽ có thể chạy `T1`.
- Khi dùng `MutableCallSite`, nếu không đồng bộ, một thread có thể tiếp tục quan sát `T0` lâu hơn mong đợi.
- Khi dùng `VolatileCallSite`, việc đọc target có volatile semantics nên tránh vấn đề nhìn mãi target cũ vì cache không đồng bộ; nhưng không có bảo đảm “đang chạy dở phải nhảy giữa chừng”.

### 11.2. So sánh các đường gọi có mục tiêu khác nhau

| Cách gọi | Tham chiếu tới ai? | Sau thay target |
| --- | --- | --- |
| `site.getTarget()` lúc ban đầu, giữ trong biến `snapshot` | `MethodHandle T0` cụ thể | `snapshot` vẫn là `T0` |
| `site.dynamicInvoker()` giữ trong biến `live` | Đường gọi qua `site` | Sử dụng target hiện hành theo semantics của site |
| Opcode `invokedynamic` đã liên kết tới `site` | Cùng `CallSite` đã cài | Sử dụng target hiện hành theo semantics của site |
| `ConstantCallSite.dynamicInvoker()` | Permanent target | Không retarget được |
| Gọi trực tiếp Java method `oldRoute("x")` | Method tĩnh `oldRoute` | Không bị `setTarget` chuyển sang method khác |

Đây là lý do chương trình có thể vừa in “`new:B`” qua `live`, vừa in “`old:C`” qua `snapshot` trong demo 1 mà hoàn toàn hợp lệ.

### 11.3. Điều kiện kiểu khi thay target

`setTarget` không chọn overload khác theo tên và không chạy lại BSM để tìm kiểu mới. Nó chỉ chấp nhận `MethodHandle` có `MethodType` **bằng** `site.type()`. Ví dụ:

```text
site.type()  = (String)String

target A:     (String)String   -> hợp lệ
target B:     (Object)String   -> không tương đương, phải adapt hợp lệ
target C:     (String)Object   -> không tương đương, phải adapt hợp lệ
target D:     ()String         -> không tương đương
```

Với `MethodHandles.Lookup`, một ứng dụng có thể lookup method overload khác và dùng `asType(site.type())` khi chuyển đổi hợp lệ; lúc đó retarget cài **adapter có đúng type**, chứ không thay đổi descriptor của `invokedynamic`.

### 11.4. Bootstrap có thể trả cùng CallSite cho nhiều vị trí

Theo Javadoc gói `java.lang.invoke`, một `CallSite` có thể được gắn với nhiều `invokedynamic` instructions. Khi chia sẻ site:

- Những vị trí liên kết ấy đều đi qua **cùng đối tượng**.
- `setTarget` trên đối tượng chia sẻ làm thay đổi hành vi của **mọi vị trí nhìn thấy target mới**.
- Việc dùng chung không đồng nghĩa “các vị trí chỉ liên kết một lần tổng cộng”; mỗi vị trí vẫn có vòng đời linkage riêng, và bootstrap có thể quyết định trả lại cùng object.

Nếu không muốn thay đổi đồng loạt, bootstrap nên tạo site riêng cho từng linkage request theo mục tiêu của runtime.

## 12. Câu chuyện `syncAll`: visibility, không phải liên kết lại

Một đoạn mẫu thường thấy:

```java
site.setTarget(newHandle);
MutableCallSite.syncAll(new MutableCallSite[]{site});
```

Đây là **fragment**, giả định `site` là `MutableCallSite` và `newHandle.type().equals(site.type())`. Hai dòng có ý nghĩa:

1. `setTarget`: thay giá trị target trong một site đã tồn tại.
2. `syncAll`: giúp các thread khác nhận biết target mới theo contract JMM của `MutableCallSite`.

**Không có bước thứ ba bí mật “gọi lại BSM”.** Nếu nguồn log thấy “bootstrap đã chạy thêm”, cần kiểm tra có **vị trí lệnh khác**, **class khác/class loader khác**, **race trong liên kết ban đầu**, hoặc **framework tự gọi một method đặt tên bootstrap/relink** hay không; tuyệt đối không đổ ngay cho `syncAll`.

### 12.1. Khi nào chọn `MutableCallSite`, khi nào chọn `VolatileCallSite`?

- **Target hầu như không đổi, cần tốc độ hot path:** `ConstantCallSite` nếu hợp đồng thực sự cố định.
- **Target đổi theo sự kiện cấu hình hoặc tối ưu hóa lại, cập nhật không quá thường xuyên:** `MutableCallSite` cùng quy trình `setTarget`/`syncAll` được điều phối.
- **Target đổi thường xuyên và readers ở nhiều thread cần volatile-style visibility:** `VolatileCallSite`; chấp nhận overhead quan sát volatile có thể có.

Đây là định hướng thiết kế, không phải benchmark tuyệt đối; hiệu năng phụ thuộc implementation JVM và tần suất gọi/cập nhật. Không dùng benchmark chạy một thread để kết luận về thứ tự bộ nhớ trong ứng dụng đa luồng.

### 12.2. Tính nhất quán giữa nhiều CallSite

`MutableCallSite.syncAll(new MutableCallSite[]{siteA, siteB})` thực hiện đồng bộ trên một tập site. Nhưng điều này **không biến việc thay target ở hai site thành giao dịch atomically visible như một khối thống nhất** cho mọi reader, nhất là khi có concurrent writers. Nếu cần invariant liên site, ứng dụng phải thiết kế cơ chế phối hợp phiên bản/transaction/đồng bộ riêng.

Tương tự, hai `VolatileCallSite` cập nhật bằng hai lần `setTarget` không tự thành một transaction. Mỗi target có volatile semantics, không cung cấp cập nhật nguyên tử nhiều đối tượng cùng lúc.

## 13. Lỗi phổ biến và cách gỡ

| Hiểu sai / hiện tượng | Nguyên nhân thực | Kiểm tra |
| --- | --- | --- |
| “Retarget rồi bootstrap phải chạy lại” | Nhầm linkage với target mutation | Đặt counter ở BSM và ở chỗ `setTarget`; so sánh trên **cùng opcode** |
| “`syncAll` relink instruction” | Nhầm memory synchronization với bootstrap resolution | Đọc `MutableCallSite.syncAll` Javadoc và `CallSite` identity |
| “`getTarget()` trả object sống luôn tự cập nhật” | Giữ lại `MethodHandle` cũ trong biến snapshot | Gọi qua `dynamicInvoker()` khi cần live target |
| “`MutableCallSite.setTarget` luôn thấy ngay trên mọi thread” | Normal-field visibility không bảo đảm | `syncAll` hoặc đồng bộ phù hợp; cân nhắc `VolatileCallSite` |
| “`VolatileCallSite` buộc invocation đang chạy đổi code” | Nhầm volatile read với hủy/khởi động lại method | Phân biệt việc chọn target tại invocation và code đang thực thi |
| `WrongMethodTypeException` ở `setTarget` | Kiểu target mới không bằng `site.type()` | Kiểm tra `MethodType.equals`; adapt có chủ đích nếu được |
| `UnsupportedOperationException` khi `ConstantCallSite.setTarget` | Site cố định theo thiết kế | Chọn loại CallSite thích hợp từ bootstrap, không hack target |
| `IllegalStateException` khi gọi blank site | `new MutableCallSite(MethodType)` có throwing target lúc khởi tạo | `setTarget` tới handle hữu ích trước khi invoke |
| “Có hai lời gọi BSM, chắc JVM relink một site” | Hai opcode khác, class loader khác hoặc race đầu tiên | Kiểm tra vị trí bytecode, caller class, loader, bootstrap counter và concurrency |
| “`SwitchPoint.invalidateAll` reset CP entry” | Invalidate guard handle, không phải CP/site linkage | Xem đồ thị MethodHandle/guard, phân biệt với bootstrap |
| “Type của target được phép đổi sau liên kết” | `CallSite.type()` vĩnh viễn không đổi | Adapter bằng `asType` theo điều kiện, không sửa descriptor |
| “Thay một site phải ảnh hưởng mọi site cùng CP entry” | Các instruction có thể liên kết tới các object khác nhau | Kiểm tra identity của CallSite trả từ từng linkage |
| “SetTarget ảnh hưởng lời gọi Java trực tiếp” | Chỉ các đường gọi **qua site** dùng target động | Phân biệt `live.invokeExact` với lời gọi trực tiếp/snapshot |
| “BSM luôn chạy đúng một lần kể cả race” | JVM có thể chạy bootstrap song song trước khi cài kết quả | Viết bootstrap an toàn concurrency; không dựa vào side effect chạy đúng 1 lần |

### 13.1. Checklist chẩn đoán thực tế

Với một hệ thống dynamic dispatch đang có hiện tượng “target đổi nhưng output vẫn cũ”, hãy hỏi theo thứ tự:

1. **Đây có thật là cùng vị trí instruction `invokedynamic` đã linked?** Cùng class loader và phiên bản class hay không?
2. **Bootstrap thực tế trả loại `CallSite` nào?** `ConstantCallSite` có thể không cho retarget; `MutableCallSite` và `VolatileCallSite` cho phép.
3. **Tôi có giữ đúng reference tới `CallSite` đã liên kết hay không?** Tạo một `MutableCallSite` mới cùng type **không** thay object cũ mà opcode đang gắn.
4. **Target mới có type bằng `site.type()` không?** Nếu không, `setTarget` thất bại và sẽ không cập nhật.
5. **Caller đi qua `dynamicInvoker` hoặc instruction đã linked hay gọi một snapshot `getTarget()` đã giữ từ trước?**
6. **Có nhiều thread không?** Nếu dùng MutableCallSite, đã có công bố bằng `syncAll` hoặc đồng bộ hợp lệ chưa?
7. **Có invocation bắt đầu trước cập nhật hay không?** Chạy dở target cũ không bị hủy.
8. **Có fallback/guard hoặc SwitchPoint vẫn chọn nhánh cũ không?** Kiểm tra tập adapter handles thay vì giả định BSM chạy lại.
9. **Bootstrap counter tăng do đâu?** Xác định từng vị trí opcode, race trong first linkage và các class/loaders khác; không chỉ dựa vào tên method.
10. **Chính xác đang yêu cầu “target update” hay “bytecode/class replacement”?** Đó là hai hệ thống vận hành khác nhau.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao “lệnh `invokedynamic` đã linked vĩnh viễn” vẫn tương thích với việc `MutableCallSite` thay target nhiều lần?

**Câu 2.** Khi thực hiện `site.setTarget(newTarget)`, những thành phần nào giữ nguyên: identity `CallSite`, `MethodType` của site, CP entry, `BootstrapMethods` và vị trí opcode?

**Câu 3.** `MutableCallSite.syncAll(...)` làm gì? Nó có gọi lại bootstrap method hoặc sinh lại `CallSite` không?

**Câu 4.** `VolatileCallSite` khác `MutableCallSite` ở cơ chế quan sát target giữa các thread như thế nào? Có cần `VolatileCallSite.syncAll` không?

**Câu 5.** Trong demo 1, vì sao `live` trả `new:B` nhưng `snapshot` trả `old:C` sau cùng một lần `setTarget`?

**Câu 6.** Trong demo 3, target khởi tạo của `new MutableCallSite(MethodType)` ném `IllegalStateException`. Điều này có nghĩa instruction đang UNLINKED không?

**Câu 7.** Nếu bạn gọi `ConstantCallSite.setTarget` với một MethodHandle có đúng `MethodType`, kết quả là gì?

**Câu 8.** Một call site có type `(String)String`, nhưng candidate target là `(Object)String`. Có thể `setTarget` trực tiếp không? Có cách nào chuẩn để thử thích nghi?

**Câu 9.** Vì sao bộ đếm bootstrap trong `RealIndyRetargetDemo` bằng 1 sau khi gọi opcode ba lần và đổi target?

**Câu 10.** Nếu có hai bytecode `invokedynamic` cùng trỏ một constant-pool entry, JVM có bắt buộc dùng cùng `CallSite` không?

**Câu 11.** Trong race lần liên kết đầu, bootstrap có thể được gọi hơn một lần không? JVM sử dụng bao nhiêu kết quả liên kết?

**Câu 12.** `SwitchPoint.invalidateAll` tự làm instruction `invokedynamic` quay về UNLINKED không?

**Câu 13.** `MutableCallSite.setTarget` có đảm bảo những invocation đã bắt đầu ở target cũ được thực hiện lại trên target mới không?

**Câu 14.** Một framework nói “relink fallback” sau khi guard bị sai. Bạn cần hỏi gì để phân biệt nghĩa “framework relink” với “JVMS bootstrap linkage”?

### Đáp án gợi ý

1. Identity `instruction -> CallSite` được cố định; `CallSite.target` là trường riêng có thể thay khi loại site cho phép.
2. Tất cả các mục liệt kê đều giữ nguyên; chỉ giá trị target thay (khi update hợp lệ).
3. Đồng bộ/công bố target cho reader của `MutableCallSite`; không gọi BSM, không cài lại site.
4. Volatile có get/set target như `volatile`, không cần/hỗ trợ `syncAll` kiểu Mutable.
5. `live` đi qua site; `snapshot` giữ handle `oldRoute` đã lấy trước khi cập nhật.
6. Không; đó là một `CallSite` có target throwing handle, khác với trạng thái chưa liên kết của một opcode.
7. Ném `UnsupportedOperationException`; target cố định.
8. Không; type phải bằng. Có thể thử `candidate.asType(site.type())` khi phép chuyển đổi hợp lệ rồi mới set.
9. Một site, một thread: bootstrap chạy lúc instruction liên kết đầu; các lần gọi sau và `setTarget` không chạy lại.
10. Không; mỗi vị trí instruction liên kết riêng, BSM có thể trả các site riêng hoặc cùng một site.
11. Có, khi tranh chấp; JVM chọn **một kết quả** để gắn cho một vị trí lệnh.
12. Không; chỉ invalidate hành vi guard theo cơ chế `SwitchPoint`.
13. Không; invocation đang chạy có thể tiếp tục trên target cũ.
14. Họ có gọi `setTarget`/thay guard trên site cũ hay thực sự tạo/chạy một instruction mới? Kiểm tra identity site và số lần BSM.

## 15. Nguồn tham chiếu chuẩn

- [Java SE 21 API — `CallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/CallSite.html): mô hình `target`, kiểu cố định, quan hệ một `CallSite` với một hoặc nhiều instruction, ý nghĩa `dynamicInvoker()`.
- [Java SE 21 API — `ConstantCallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/ConstantCallSite.html): permanent target, `setTarget` ném `UnsupportedOperationException`.
- [Java SE 21 API — `MutableCallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MutableCallSite.html): `setTarget` như biến thường, `dynamicInvoker`, `syncAll` và Java Memory Model.
- [Java SE 21 API — `VolatileCallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): target có volatile semantics, quan sát cập nhật giữa các thread, không có `syncAll`.
- [Java SE 21 API — gói `java.lang.invoke`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/package-summary.html): bootstrap, liên kết một `invokedynamic` instruction thành `CallSite`, cạnh tranh khi initial linkage.
- [JVMS Java SE 21 — `5.4.3.6 Dynamic Constant and Call Site Resolution`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3.6): vòng đời resolution, lỗi và khả năng bootstrap chạy cạnh tranh.
- [JVMS Java SE 21 — `6.5 invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.invokedynamic): cấu trúc operand và quy tắc instruction.
- [JVMS Java SE 21 — `4.4.10 CONSTANT_Dynamic_info và CONSTANT_InvokeDynamic_info`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4.10): CP entry chọn bootstrap record và tên/descriptor.
- [Java SE 21 API — `SwitchPoint`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/SwitchPoint.html): cơ chế invalidating guard, khác với JVM linkage.

**Kết luận:** `invokedynamic` có thể **chốt liên kết đúng một lần về mặt kết quả** tới một `CallSite` nhưng **đổi hành vi nhiều lần** nhờ target mutable/volatile. `setTarget` thay method handle được gọi; `syncAll` công bố thay đổi; `VolatileCallSite` dùng volatile semantics. Không thao tác nào trong số đó tự đưa **vị trí lệnh đã liên kết** về trạng thái unlinked hoặc gọi lại bootstrap method.