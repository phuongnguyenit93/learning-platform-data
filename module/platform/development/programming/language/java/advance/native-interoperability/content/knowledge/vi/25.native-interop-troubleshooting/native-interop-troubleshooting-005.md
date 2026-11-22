# Nhận diện `WrongMethodTypeException`, `WrongThreadException` và lỗi truy cập segment đã đóng

Ba lỗi này có thể cùng xuất hiện trong ứng dụng dùng **Foreign Function & Memory API (FFM)**, nhưng chúng chỉ ra **ba lớp hợp đồng khác nhau**: chữ ký lời gọi `MethodHandle`, quyền truy cập segment theo thread và vòng đời bộ nhớ gắn với `Arena`. Chẩn đoán đúng lớp lỗi giúp sửa nguyên nhân thay vì chỉ thay cờ JVM hay đổi loại arena theo cảm tính.

**Phiên bản áp dụng:** Ví dụ FFM dùng API chính thức của **Java 22+** (JEP 454). Trên Java 17–21, FFM còn ở các giai đoạn incubator/preview, nên tên gói, API và cờ biên dịch/chạy có thể khác. Ví dụ chính không gọi native function, do đó không cần `--enable-native-access`.

## 1. Bản đồ nhận diện nhanh

| Dấu hiệu/ngoại lệ | Hợp đồng bị vi phạm | Điểm thường phát sinh | Kiểm tra trước tiên |
| --- | --- | --- | --- |
| `java.lang.invoke.WrongMethodTypeException` | Kiểu tham số hoặc **kiểu trả về tại call site** không tương ứng `MethodHandle.type()`; cũng có thể do tạo adapter/composition không tương thích | `invokeExact`, `invoke`, `asType`, kết hợp method handles; downcall/upcall dùng handle | In `handle.type()`; đối chiếu kiểu *tĩnh* ở vị trí gọi và `FunctionDescriptor` |
| `java.lang.WrongThreadException` | Dùng segment/arena ở thread không được phép | `segment.get/set` của arena confined, `arena.allocate` hoặc `arena.close` từ thread khác | Xác định thread tạo `Arena.ofConfined()` và thread thực thi |
| `java.lang.IllegalStateException` khi truy cập segment | Scope không còn `alive`, ví dụ arena đã `close()` | `segment.get/set` sau `try-with-resources` hoặc sau đóng arena | Xem `segment.scope().isAlive()` và điểm `close()` thực tế |

**Lưu ý về tên “segment đã đóng”:** Đối tượng `MemorySegment` thường không được đóng bằng `segment.close()`. Một **arena có thể đóng** quản lý vòng đời của các segment; đóng arena làm scope của những segment liên quan không còn hợp lệ. Vì vậy ngoại lệ của thao tác đọc/ghi segment sau đóng thường là `IllegalStateException`.

Không suy luận chỉ từ chuỗi thông báo ngoại lệ: `IllegalStateException` còn có nguyên nhân khác, và khi **cả** điều kiện thread và lifetime sai thì không nên dựa vào thứ tự kiểm tra nội bộ của JVM để dự đoán thông báo nào xuất hiện trước. Hãy tái hiện từng điều kiện riêng.

## 2. Hình dung ba hợp đồng trước khi debug

### 2.1. Kiểu của lời gọi — `MethodHandle`

Trong FFM, `Linker.downcallHandle(...)` trả về `MethodHandle` có chữ ký Java hình thành từ `FunctionDescriptor` và cách tạo handle. `MethodHandle.invokeExact` đòi hỏi **sự trùng khớp hoàn toàn** giữa kiểu của handle và kiểu biểu diễn tĩnh của lời gọi ở bytecode, **bao gồm cả kiểu trả về**. Chỉ sai `int` so với `long`, thiếu tham số, đặt sai thứ tự, hoặc dùng wrapper thay primitive cũng đủ gây `WrongMethodTypeException`.

Ví dụ một handle có `type()` là `(int)int`:

```java
MethodHandle identity = MethodHandles.identity(int.class);

int correct = (int) identity.invokeExact(7); // lời gọi (int)int
int wrong   = (int) identity.invokeExact(7L); // lời gọi (long)int: sai
```

Đoạn mã trên minh họa và giả định đã import `java.lang.invoke.*`, đặt trong method khai báo `throws Throwable`. `7L` có kiểu tĩnh `long`, trong khi handle đòi `int`; dòng thứ hai ném `WrongMethodTypeException` **trước khi có ý nghĩa xử lý giá trị trả về**.

Trường hợp dễ bỏ sót là return type. Một handle `(int)int` không đồng nghĩa với `(int)void` hoặc `(int)long` khi gọi bằng `invokeExact`. Dùng ép kiểu trả về đúng (hoặc lời gọi trong ngữ cảnh kiểu đúng) và kiểm tra `handle.type()` thay vì đoán dựa trên giá trị thực tế.

Phân biệt:
- `invokeExact`: yêu cầu exact match, **không** tự chuyển `int` thành `long`, box/unbox hoặc tự chỉnh signature.
- `invoke`: có thể áp dụng những chuyển đổi mà `asType` cho phép; không phải mọi chuyển đổi đều hợp lệ và không thể sửa chữ ký native khai báo sai.
- `asType(MethodType)`: tạo một adapter với kiểu mong muốn nếu chuyển đổi hợp lệ; chuyển đổi không thể thực hiện cũng có thể dẫn đến `WrongMethodTypeException`.
- `ClassCastException`, `IllegalArgumentException` và `NullPointerException` có thể liên quan dữ liệu hoặc đối số; **không tự động** được xem là `WrongMethodTypeException`.

### 2.2. Thread được phép — `Arena.ofConfined()`

`Arena.ofConfined()` có **owner thread** là thread tạo arena. Segment cấp phát từ arena đó chỉ được truy cập từ owner khi scope còn sống. Thread B đọc hoặc ghi segment của owner A sẽ gặp `WrongThreadException`, dù segment chưa đóng, kích thước đủ và `ValueLayout` chính xác.

`Arena.ofShared()` cho phép truy cập từ nhiều thread, nhưng **không tự đồng bộ các thao tác đọc/ghi** và vẫn có lifetime hữu hạn. Một race về data hoặc thời điểm `close()` có thể tồn tại ngay cả khi đã hết `WrongThreadException`.

### 2.3. Lifetime — `Arena.close()` và `MemorySegment.Scope`

Mỗi `MemorySegment` gắn với một `scope()`. Với arena confined hoặc shared có thể đóng, `close()` kết thúc lifetime; truy cập nội dung qua `get`, `set`, copy… sau khi scope chết sẽ thất bại. Lời gọi `segment.scope().isAlive()` giúp quan sát trạng thái, nhưng **kiểm tra “alive” rồi mới đọc không bảo đảm an toàn** nếu thread khác có thể đóng shared arena giữa hai thao tác.

Một biến Java vẫn có thể giữ reference đến `MemorySegment` sau khi arena đã đóng; GC/reference còn tồn tại **không có nghĩa vùng nhớ native còn hợp lệ**.

## 3. Lab Java 22+: tái hiện chính xác cả ba lỗi

Tạo một file độc lập tên **`NativeErrorLab.java`**:

```java
import java.lang.WrongThreadException;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.WrongMethodTypeException;

public class NativeErrorLab {
    public static void main(String[] args) throws Throwable {
        demoWrongMethodType();
        demoWrongThread();
        demoClosedSegment();
    }

    private static void demoWrongMethodType() throws Throwable {
        System.out.println("[method handle]");
        MethodHandle identity = MethodHandles.identity(int.class);
        System.out.println("type=" + identity.type());

        int value = (int) identity.invokeExact(17);
        System.out.println("ok=" + value);

        try {
            int unexpected = (int) identity.invokeExact(17L);
            System.out.println("unexpected=" + unexpected);
        } catch (WrongMethodTypeException ex) {
            System.out.println("failure=" + ex.getClass().getSimpleName());
        }
    }

    private static void demoWrongThread() throws InterruptedException {
        System.out.println("[wrong thread]");
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 42);

            Thread worker = new Thread(() -> {
                System.out.println("accessibleFromWorker="
                        + segment.isAccessibleBy(Thread.currentThread()));
                try {
                    int unexpected = segment.get(ValueLayout.JAVA_INT, 0);
                    System.out.println("unexpected=" + unexpected);
                } catch (WrongThreadException ex) {
                    System.out.println("failure=" + ex.getClass().getSimpleName());
                }
            });
            worker.start();
            worker.join(); // đợi worker xong, giữ arena vẫn mở
            System.out.println("ownerValue="
                    + segment.get(ValueLayout.JAVA_INT, 0));
        }
    }

    private static void demoClosedSegment() {
        System.out.println("[closed segment]");
        MemorySegment segment;

        try (Arena arena = Arena.ofConfined()) {
            segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 99);
            System.out.println("beforeClose="
                    + segment.get(ValueLayout.JAVA_INT, 0));
        } // owner đóng arena ở đây

        System.out.println("aliveAfterClose=" + segment.scope().isAlive());
        try {
            int unexpected = segment.get(ValueLayout.JAVA_INT, 0);
            System.out.println("unexpected=" + unexpected);
        } catch (IllegalStateException ex) {
            System.out.println("failure=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy bằng JDK 22 trở lên:

```bash
javac NativeErrorLab.java
java NativeErrorLab
```

**Stdout kỳ vọng:**

```text
[method handle]
type=(int)int
ok=17
failure=WrongMethodTypeException
[wrong thread]
accessibleFromWorker=false
failure=WrongThreadException
ownerValue=42
[closed segment]
beforeClose=99
aliveAfterClose=false
failure=IllegalStateException
```

**Vì sao ba nhánh ổn định?**

1. Nhánh `MethodHandle` sử dụng `identity(int.class)` có kiểu `(int)int`, rồi cố ý gọi với `long`. Nó minh họa chính cơ chế kiểu mà FFM downcall handles cũng phải tuân theo; không cần thư viện C.
2. Nhánh `WrongThreadException` dùng một thread Java khác để chạm vào segment của **confined** arena trong lúc arena **vẫn còn mở**; `join()` giữ thứ tự output ổn định và owner đọc được giá trị `42`.
3. Nhánh `IllegalStateException` chỉ truy cập segment ở **chính owner thread** sau khi `try-with-resources` đã đóng arena; không trộn thêm lỗi sai thread. `scope().isAlive()` trả `false`.

Trong ứng dụng thật, đừng chỉ catch các lỗi này rồi tiếp tục sử dụng cùng con trỏ/segment. Các `catch` ở lab phục vụ **nhận diện**; khi chạy production cần sửa hợp đồng kiểu, thread hoặc vòng đời.

## 4. Đọc stack trace và xác định nguyên nhân

### 4.1. Nếu là `WrongMethodTypeException`

Ví dụ thông điệp *có thể* nêu kiểu đang mong đợi và kiểu đang gọi; cú pháp cụ thể thay đổi theo bản JVM:

```text
java.lang.invoke.WrongMethodTypeException:
  expected (int)int but found (long)int
```

Đây là ví dụ **minh họa dạng thông báo**, không phải stderr chính xác được bảo đảm cho mọi phiên bản. Cần:

1. In `handle.type()` ngay trước lời gọi. Nếu là FFM, đối chiếu `FunctionDescriptor` và kiểu handle cuối cùng **sau các phép adapter**.
2. Kiểm tra **số lượng, thứ tự, kiểu tĩnh của tham số và kiểu return tại call site**. Đặc biệt: `int` ≠ `long`, `int` ≠ `Integer` khi dùng `invokeExact`.
3. Kiểm tra bạn tạo downcall handle theo kiểu nào:
   - `linker.downcallHandle(address, functionDescriptor)` có **địa chỉ hàm đã cố định**, nên không cần tham số địa chỉ hàm đứng đầu tại invocation.
   - `linker.downcallHandle(functionDescriptor)` **chưa cố định địa chỉ**; lời gọi handle cần thêm **tham số `MemorySegment` đầu tiên** đại diện địa chỉ hàm (một số trường hợp native struct return còn có đối số allocator bổ sung).
4. Kiểm tra kiểu trả về trong `FunctionDescriptor.of(...)` hoặc `FunctionDescriptor.ofVoid(...)`. Nhầm `JAVA_LONG` với `JAVA_INT`, hoặc bỏ ép kiểu ở `invokeExact`, đều cần xem xét.
5. Sửa bản khai báo/điểm gọi theo đúng ABI và `MethodType`. Chỉ dùng `invoke`/`asType` khi chuyển đổi có chủ đích và hợp lệ; không dựa vào auto conversion để che lỗi khai báo native.

**Minh họa hợp đồng FFM (đoạn ngắn, không phải chương trình hoàn chỉnh):**

```java
// Giả sử "symbol" là địa chỉ hàm C hợp lệ:
// int add_ints(int a, int b);
MethodHandle add = Linker.nativeLinker().downcallHandle(
        symbol,
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT));

System.out.println(add.type());           // (int,int)int
int sum = (int) add.invokeExact(2, 3);     // đúng kiểu Java
```

Đoạn trên **chưa có code tải symbol và định nghĩa thư viện**, nên chỉ dùng để hiểu signature. Tạo downcall handle là thao tác **restricted**: ứng dụng cần native access phù hợp, ví dụ `java --enable-native-access=ALL-UNNAMED ...` khi caller ở classpath. Không tự gọi vào một địa chỉ native chưa xác minh; khai báo `FunctionDescriptor` sai so với ABI thực còn nguy hiểm hơn lỗi Java method type và có thể làm JVM sập.

### 4.2. Nếu là `WrongThreadException`

Tìm điểm tạo `Arena.ofConfined()`. Ví dụ lỗi kiến trúc phổ biến:

```java
// Ví dụ minh họa: method tạo confined segment ở thread A.
MemorySegment segment = confinedArena.allocate(ValueLayout.JAVA_INT);

// Sau đó gửi segment sang executor chạy ở thread B:
executor.submit(() -> segment.get(ValueLayout.JAVA_INT, 0));
// Thread B không phải owner -> WrongThreadException khi thao tác get.
```

Đây là snippet phụ thuộc biến `confinedArena`/`executor` ở chương trình thực tế, **không phải file chạy độc lập**.

Hướng sửa đúng nhu cầu:

- **Không cần chia sẻ segment:** Giữ allocate, đọc/ghi và close trên một owner thread; trả về **giá trị Java đã copy**, không phát tán `MemorySegment`.
- **Phải đọc/ghi từ nhiều thread:** Dùng `Arena.ofShared()` và tổ chức đồng bộ, thứ tự công việc, thời điểm close, ownership rõ ràng. Shared arena giải quyết *thread confinement*, không giải quyết race hay use-after-close.
- **Chỉ cần chuyển dữ liệu sang thread khác:** Sao chép sang `byte[]` hoặc cấu trúc Java phù hợp trước khi rời scope có lifetime ngắn, hoặc tạo vùng memory mới dưới scope được quản lý đúng.
- **Lỗi xảy ra khi `arena.close()`:** Confined arena cũng chỉ được **đóng bởi owner thread**; đừng giao việc đóng cho executor thread khác.

Gợi ý debug:

```java
System.out.println("currentThread=" + Thread.currentThread().getName());
System.out.println("canAccessHere="
        + segment.isAccessibleBy(Thread.currentThread()));
System.out.println("scopeAlive=" + segment.scope().isAlive());
```

Snippet trên yêu cầu `segment` tồn tại trong phạm vi dùng; quan sát `false` hoặc `true` chỉ là dấu hiệu tại một thời điểm. Tránh hiểu `Thread.getName()` là bằng chứng ownership duy nhất: hai thread có thể cùng tên; nếu cần, log `Thread.currentThread().threadId()` (Java 19+) hoặc tham chiếu đối tượng `Thread`.

### 4.3. Nếu segment “đã đóng” / `IllegalStateException`

Ví dụ lỗi điển hình khi trả segment ra ngoài scope:

```java
// Ví dụ minh họa: method này trả về segment đã mất hiệu lực.
static MemorySegment brokenSegmentFactory() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(ValueLayout.JAVA_INT);
    } // close() trước khi bên gọi kịp đọc
}
```

`MemorySegment` được trả về vẫn là một Java reference, nhưng scope đã chết. Nếu caller gọi `get(ValueLayout.JAVA_INT, 0)`, dự kiến `IllegalStateException`.

Hướng sửa:
1. Để phần **sử dụng segment** xảy ra **trong vòng đời arena**, rồi trả về kiểu dữ liệu Java độc lập. Nếu API phải trả một segment, thiết kế rõ **ai sở hữu arena, ai đóng và khi nào đóng**, thay vì tạo rồi tự đóng ngay.
2. Không gọi `close()` trong `finally` trước khi các tác vụ bất đồng bộ, callbacks hoặc downcalls còn dùng segment. Với shared arena, phối hợp hoàn tất tác vụ trước close.
3. Sau close, **không có thao tác “mở lại” scope cũ**. Tạo arena/segment mới hoặc lấy dữ liệu gốc từ nguồn còn hợp lệ; đừng cố `reinterpret` một địa chỉ đã được giải phóng để vượt kiểm soát.
4. Đừng chữa bằng `Arena.global()` cho mọi bộ nhớ: global scope không có cơ chế close thủ công, dễ dẫn đến vòng đời quá dài. `Arena.ofAuto()` cũng không có close thủ công và có cơ chế lifetime khác; chỉ chọn khi hiểu đúng yêu cầu.

**Phân biệt hai dạng `IllegalStateException`:**

- `segment.get/set(...)` sau close: scope segment **không alive**.
- `arena.close()` bị gọi lần thứ hai, hoặc xung đột với truy cập đồng thời: lỗi liên quan **hành vi đóng arena**, không nhất thiết do một `get` trên segment đã chết.

Đọc stack trace để biết thao tác nào ném lỗi. Có thể log `segment.scope().isAlive()`, nhưng đây là một phép quan sát, không có tác dụng kéo dài lifetime.

## 5. Phân biệt khi lỗi xuất hiện trong chuỗi FFM thực tế

Xét đường đi:

```text
Java call site
  -> MethodHandle.invokeExact(...)
     -> Linker/downcall (FunctionDescriptor, ABI)
        -> MemorySegment arguments
           -> kiểm tra scope còn sống
           -> kiểm tra thread có quyền truy cập
           -> native function (nếu hợp lệ)
```

Các nhãn ở trên biểu diễn **những lớp kiểm tra về mặt khái niệm**; không cam kết thứ tự nội bộ của mọi JVM hoặc bảo đảm một hàm native cụ thể sẽ chạy sau mọi phép kiểm tra.

- **Sai kiểu handle trước:** `WrongMethodTypeException` có thể xảy ra ngay ở chữ ký `invokeExact`; không đủ bằng chứng rằng native function đã được gọi.
- **Kiểu đúng nhưng segment không được dùng từ thread hiện tại:** `WrongThreadException` có thể xuất hiện trong `get/set` hoặc khi linker kiểm tra các `MemorySegment` truyền qua ABI.
- **Kiểu đúng, thread đúng nhưng arena đã đóng:** `IllegalStateException` có thể xảy ra khi truy cập segment hoặc trong downcall dùng một segment không còn alive.
- **Đủ ba điều kiện nhưng offset sai:** `IndexOutOfBoundsException` là lỗi ranh giới không gian, không thuộc ba lỗi chính.
- **Đủ ba điều kiện nhưng alignment sai:** `IllegalArgumentException` có thể liên quan layout/alignment. Với native code, chữ ký ABI sai có thể gây hành vi nghiêm trọng mà JVM không thể kiểm tra hoàn toàn.
- **Chưa cấp quyền restricted native call:** `IllegalCallerException`/warning theo chính sách JDK; giải quyết bằng cấu hình native access thích hợp, **không** thay thế việc sửa `WrongMethodTypeException`, thread hoặc lifetime.

### Cùng là `MemorySegment` nhưng ai “sở hữu” lifetime?

| Nguồn tạo | Thread access | Lifetime thường gặp | Hướng chẩn đoán |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Owner thread | Đến khi owner gọi `close()`/thoát `try` | Sai thread → `WrongThreadException`; đã close → `IllegalStateException` |
| `Arena.ofShared()` | Nhiều thread | Đến khi close; cần phối hợp concurrency | Không có confinement, nhưng có thể close quá sớm |
| `Arena.ofAuto()` | Nhiều thread | Theo khả năng reachability/GC của scope | Không dùng `close()`; xem dữ liệu có bị bỏ tham chiếu không |
| `Arena.global()` | Nhiều thread | Global scope còn sống suốt JVM | Không đóng thủ công; phải cân nhắc quản lý tài nguyên |
| `MemorySegment.ofArray(...)` | Nhiều thread | Gắn với Java heap/GC, không phải confined arena | Thường không gặp “arena đã đóng” như ví dụ native confined |

## 6. Quy trình chẩn đoán có thể áp dụng ngay

Khi log có một trong ba lỗi, hãy đi theo thứ tự này:

1. **Xác định thao tác ném lỗi từ stack trace.** Đó là `invokeExact`, `get/set` hay `close`? Ghi lại phiên bản thực `java -version` và code ở dòng báo lỗi.
2. **Nếu có `MethodHandle`**, in `handle.type()`; so với kiểu tham số/return ở call site. Nếu là FFM, kiểm tra `FunctionDescriptor`, hàm đã bound địa chỉ chưa, và xem adapter nào đã được áp dụng.
3. **Nếu có `MemorySegment`**, ghi nhận `segment.scope().isAlive()`, thread đang gọi và loại arena tạo segment. Đừng bắt đầu debug offset/byte order nếu lỗi cho biết lifetime/thread đã sai.
4. **Tái hiện tối thiểu từng lỗi riêng** như lab: same thread + closed arena để kiểm tra lifetime; wrong thread + open arena để kiểm tra confinement; không native call để kiểm tra `MethodHandle`.
5. **Sửa quyền sở hữu/lifetime ở nơi tạo dữ liệu:** đổi thiết kế scope, sắp xếp công việc bất đồng bộ, hoặc sửa signature. Chạy lại bài test và đường đi tích hợp; không chỉ catch bỏ qua lỗi.

### Câu hỏi tự kiểm tra

**Tình huống A:** `handle.type()` là `(long)int`, nhưng gọi `(int) handle.invokeExact(5)`. Lỗi dự kiến? **`WrongMethodTypeException`**, vì `5` là `int`, cần tham số `long` như `5L` (giả sử khai báo handle chính xác).

**Tình huống B:** Thread A tạo `Arena.ofConfined()`, truyền segment sang thread B trước khi arena đóng. Thread B gọi `get`. Lỗi dự kiến? **`WrongThreadException`**, vì sai owner thread.

**Tình huống C:** Thread A tạo segment, kết thúc `try (Arena arena = ...)`, rồi **cũng thread A** đọc segment. Lỗi dự kiến? **`IllegalStateException`**, vì scope đã chết.

**Tình huống D:** Thay confined bằng shared arena, nhưng đóng shared arena khi worker chưa xong. Có chắc hết lỗi? **Không.** Shared arena cho phép nhiều thread truy cập nhưng không kéo dài lifetime; cần chờ worker hoàn tất trước close.

## 7. Tài liệu chuẩn

- [Java SE 25: `MethodHandle.invokeExact`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html) và [`WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): chữ ký tĩnh/return type và chuyển đổi method handles.
- [Java SE 25: `WrongThreadException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/WrongThreadException.html): lỗi gọi sai thread.
- [Java SE 25: `Arena`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared/global/auto, lifetime và `close()`.
- [Java SE 25: `MemorySegment`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html) và [`MemorySegment.Scope`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html): kiểm tra thread/lifetime, `get/set` và `scope().isAlive()`.
- [Java SE 25: `Linker`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html): downcall method handle, native signatures và checks trên segment.
- [OpenJDK JEP 454](https://openjdk.org/jeps/454): chuẩn hóa Foreign Function & Memory API từ JDK 22.
