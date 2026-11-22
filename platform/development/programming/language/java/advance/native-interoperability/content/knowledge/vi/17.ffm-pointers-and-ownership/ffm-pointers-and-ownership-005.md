# AddressLayout.withTargetLayout: khai báo con trỏ có kiểu và trách nhiệm xác định đúng vùng nhớ đích

## 1. Vấn đề: từ địa chỉ máy đến một vùng nhớ mà Java được phép đọc

Khi kết nối Java với thư viện C/C++, ta thường gặp các đối số hoặc trường dữ liệu dạng con trỏ:

```c
int *value;
int values[3];
struct Record *record;
void *data;
char *text;
```

Một con trỏ native về cơ bản chứa **địa chỉ**, nhưng giá trị địa chỉ riêng lẻ không trả lời được những câu hỏi thiết yếu: vùng nhớ đó lớn bao nhiêu byte, có thực sự được cấp phát không, cần alignment thế nào, ai sở hữu quyền `free`, còn hiệu lực đến khi nào, có cho phép Java ghi hay không?

Trong **Foreign Function & Memory API (FFM)**, `java.lang.foreign.AddressLayout` mô tả *một giá trị địa chỉ* được lưu trong bộ nhớ hoặc đi qua lời gọi hàm native. Mặc định `ValueLayout.ADDRESS` cho phép đọc **giá trị con trỏ**, nhưng Java **không tự biết** độ dài vùng nhớ mà con trỏ trỏ tới.

Phương thức:

```java
AddressLayout typedPointer =
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT);
```

cho phép nói rằng: **“Khi đọc một địa chỉ theo layout này, hãy trả về một `MemorySegment` có view dài bằng target layout, ở đây là 4 byte.”**

**Câu quan trọng nhất của bài:** `withTargetLayout` là **một khai báo về cách diễn giải địa chỉ và biên kích thước giả định**, không phải thao tác kiểm chứng bộ nhớ native thực sự. Nó **không tự cấp phát, không sở hữu, không giữ sống, không kiểm tra toàn bộ vùng được trỏ tới**. Lập trình viên vẫn phải xác định đúng size, alignment, lifetime, ownership và hợp đồng C của pointer.

### Phiên bản Java

Các ví dụ sử dụng `java.lang.foreign` chuẩn được hoàn thiện từ **JDK 22 (JEP 454)**. Hãy dùng JDK **22+**; các chương trình được biên dịch và chạy kiểm chứng trên JDK 24. `AddressLayout.withTargetLayout(MemoryLayout)` là **restricted method**, nên ví dụ classpath chạy với:

```bash
java --enable-native-access=ALL-UNNAMED TenLop
```

Nếu đặt chương trình trong named module, cần cấp native access cho đúng tên module. Đừng bỏ cờ rồi cho rằng cảnh báo hoặc `IllegalCallerException` liên quan tới kích thước pointer: đây là quy tắc cấp quyền restricted API. Khác với ví dụ FFM chỉ gọi `Arena.allocate`, ví dụ này **có thao tác restricted**.

## 2. Phân biệt địa chỉ lưu ở đâu và vùng nhớ được trỏ tới ở đâu

Giả sử một vùng C có bốn byte chứa số `12345` tại địa chỉ A, và một ô pointer chứa A tại địa chỉ P:

```text
   vùng chứa pointer (slot)                   vùng dữ liệu (target)
   địa chỉ P                                  địa chỉ A
+-----------------------+            +-----------------------+
|    A (pointer value)  | ----------> |   12345 (4 bytes)     |
+-----------------------+            +-----------------------+
   layout: ADDRESS                          layout: JAVA_INT
   kích thước pointer: 4/8 bytes            target size: 4 bytes

Java MemorySegment slot                  Java MemorySegment target
  biết vị trí ô pointer                     biết vùng nhớ do arena cấp phát
  chỉ được dùng khi slot owner alive        chỉ được dùng khi target owner alive
```

Có **ba loại kích thước** khác nhau:

1. **`slot.byteSize()`:** kích thước view chứa một hoặc nhiều con trỏ. Với một ô con trỏ, thường bằng `ValueLayout.ADDRESS.byteSize()`.
2. **`AddressLayout.byteSize()`:** kích thước **giá trị con trỏ** khi đọc/ghi từ slot; phụ thuộc ABI, thường là 8 byte trên nền tảng 64-bit.
3. **`targetLayout.byteSize()`:** số byte giả định ở **địa chỉ đích**, ví dụ `JAVA_INT.byteSize() == 4`. Độ dài này được gán cho `MemorySegment` trả về khi đọc pointer bằng address layout có target.

Do đó:

```java
AddressLayout addr = ValueLayout.ADDRESS;
AddressLayout intPtr = addr.withTargetLayout(ValueLayout.JAVA_INT);

System.out.println(addr.byteSize() == intPtr.byteSize()); // true
System.out.println(intPtr.targetLayout().orElseThrow().byteSize()); // 4
```

`withTargetLayout` **không biến một con trỏ 64-bit thành một con trỏ 32-bit**. Pointer storage vẫn theo `ADDRESS`; chỉ có view **được trả khi đọc địa chỉ** thay đổi kích thước.

### Không nhầm kiểu carrier

`AddressLayout` là subtype của `ValueLayout`, nhưng carrier của nó là **`MemorySegment.class`**, không phải Java `long`:

```java
boolean yes = ValueLayout.ADDRESS.carrier() == MemorySegment.class;
```

`MemorySegment.get(AddressLayout, offset)` trả về một `MemorySegment` đại diện cho **địa chỉ lấy từ slot**, không phải một đối tượng Java sở hữu tự động allocation đó.

## 3. Mặc định ADDRESS trả view 0 byte; target layout mở rộng view theo khai báo

Nếu đọc pointer bằng layout không có target:

```java
MemorySegment opaque = slot.get(ValueLayout.ADDRESS, 0);
```

FFM tạo một **native segment có kích thước 0 byte**, dù địa chỉ đọc được không bằng 0. Đây là rào chắn có chủ đích: Java không biết kích thước allocation nên không cho phép đọc một byte nào bằng access kiểm tra biên thông thường.

Nếu đọc cùng pointer bằng layout có target:

```java
AddressLayout intPointer =
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT);

MemorySegment typed = slot.get(intPointer, 0);
```

FFM trả về native segment có:

- `typed.address()` bằng địa chỉ máy vừa đọc từ `slot`.
- `typed.byteSize() == ValueLayout.JAVA_INT.byteSize()` (4 byte).
- Scope của **native segment được tạo từ pointer read là global scope**, không phải scope của `slot` hay scope của allocation gốc.
- Việc đọc pointer còn kiểm tra **căn chỉnh của địa chỉ đích với target layout**; nếu không tương thích, có thể ném `IllegalArgumentException`.

Khi và **chỉ khi** bạn đã biết vùng đích thực tế hợp lệ, đủ dài và chưa được giải phóng, có thể:

```java
int value = typed.get(ValueLayout.JAVA_INT, 0);
```

**Bẫy lớn nhất:** mặc dù `typed.byteSize() == 4` cho phép access trong phạm vi view, FFM **không tự truy ra** rằng 4 byte đó thực sự thuộc một allocation còn sống. Nếu pointer là stale, dangling hoặc forged, lần dereference có thể gây **JVM crash hoặc memory corruption**, chứ không phải luôn có `IllegalStateException` lịch sự.

### So sánh ngắn

| Cách đọc | `byteSize()` của pointer view trả về | Có diễn giải được vùng đích? | Rủi ro |
| --- | ---: | --- | --- |
| `slot.get(ValueLayout.ADDRESS, 0)` | 0 | Không đọc bytes đích bằng `get(JAVA_BYTE,0)` thông thường | Giữ pointer ở dạng opaque an toàn hơn khi chưa biết size |
| `slot.get(ADDRESS.withTargetLayout(JAVA_INT),0)` | 4 | Cho phép access 4 byte nếu pointer thực sự hợp lệ | Size chỉ là **giả định do caller cung cấp** |
| `slot.get(ADDRESS.withTargetLayout(sequenceLayout(3,JAVA_INT)),0)` | 12 | Cho phép đọc 3 `int` hợp lệ theo bounds đã khai báo | Không kiểm chứng actual allocation chứa đủ 3 `int` |
| `ofAddress(rawAddress)` không mở rộng | 0 | Không đọc được bytes khi chưa có thông tin hợp lệ | Chỉ biểu diễn địa chỉ opaque |
| `reinterpret` trên địa chỉ | Kích thước do người dùng chỉ định | Có thể tạo view mới nhưng cũng là restricted/unsafe | Không tự xác minh lifetime hoặc provenance |

## 4. Điều withTargetLayout thực sự làm và không làm

### Những việc có làm

- Tạo một **`AddressLayout` mới, immutable**, có associated target `MemoryLayout`.
- **Giữ nguyên** carrier, alignment của chính address layout, byte order, tên và kích thước giá trị pointer.
- Cho phép `slot.get(typedAddressLayout, offset)` trả `MemorySegment` có `byteSize` bằng `targetLayout.byteSize()` thay vì 0.
- Kiểm tra alignment của **địa chỉ đích** theo `targetLayout.byteAlignment()` tại bước đọc pointer.
- Cho phép mô tả con trỏ tới một kiểu/value/sequence/struct có kích thước xác định trong một số API FFM như `MemorySegment.get`, function descriptor cho downcall hoặc upcall.

### Những việc hoàn toàn không đảm bảo

- **Không tạo allocation:** không gọi `malloc`, không gọi `Arena.allocate`, không cấp phát thêm bytes ở địa chỉ đích.
- **Không xác nhận địa chỉ hợp lệ:** một địa chỉ có thể là số rác, pointer đã free, pointer vào bộ nhớ chưa mapped, hoặc null.
- **Không xác nhận actual size:** khai báo target là 16 byte không chứng minh allocation thực sự có ít nhất 16 byte.
- **Không biết ownership:** không xác định ai phải gọi `free`/`delete`/`munmap` hay library-specific destructor.
- **Không bảo vệ lifetime của referent:** pointer view có global scope không giữ allocation của arena khác tiếp tục sống.
- **Không kiểm tra kiểu C thực tế:** khai báo `JAVA_LONG` không làm một C `long` tự trở thành 8 byte trên mọi ABI.
- **Không kiểm soát khả năng sửa dữ liệu hoặc đồng bộ native:** target layout không thay thế contract constness, locks, thread-affinity và memory barriers.
- **Không tự kiểm tra vùng đích không chồng lấp/không alias:** nhiều pointers có thể chỉ đến cùng vùng.
- **Không chứng minh việc dereference an toàn chỉ vì alignment hợp lệ:** căn chỉnh là cần nhưng chưa đủ.

Xem `targetLayout` là một **cam kết của người viết Java đối với FFM**. Nếu cam kết sai về biên không gian hoặc thời gian, hậu quả vượt khỏi kiểm tra Java thông thường.

## 5. Chương trình 1: đọc pointer có và không có target layout

Chương trình này cố ý tạo **cả vùng dữ liệu và ô chứa pointer** bằng một arena vẫn đang mở. Nhờ vậy việc dereference ở bên trong `try` là hợp lệ, có thể kiểm thử. Sau khi arena đóng, chương trình **chỉ quan sát metadata**, tuyệt đối không dereference pointer đã giải phóng.

### 5.1. Tệp `AddressTargetDemo.java`

```java
import java.lang.foreign.*;
import static java.lang.foreign.ValueLayout.*;

public class AddressTargetDemo {
    private static final AddressLayout INT_POINTER =
            ADDRESS.withTargetLayout(JAVA_INT);

    public static void main(String[] args) {
        System.out.println("Pointer layout bytes: " + ADDRESS.byteSize());
        System.out.println("Target layout bytes: "
                + INT_POINTER.targetLayout().orElseThrow().byteSize());
        System.out.println("Carrier: "
                + (INT_POINTER.carrier() == MemorySegment.class));

        MemorySegment typed;
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment value = arena.allocate(JAVA_INT);
            value.set(JAVA_INT, 0, 12345);

            MemorySegment slot = arena.allocate(ADDRESS);
            slot.set(ADDRESS, 0, value);

            MemorySegment opaque = slot.get(ADDRESS, 0);
            typed = slot.get(INT_POINTER, 0);

            System.out.println("Without target bytes: " + opaque.byteSize());
            System.out.println("With target bytes: " + typed.byteSize());
            System.out.println("Same address: "
                    + (typed.address() == value.address()));
            System.out.println("Read while owner open: "
                    + typed.get(JAVA_INT, 0));
            System.out.println("Typed scope alive while open: "
                    + typed.scope().isAlive());

            MemorySegment larger = arena.allocate(8, 8);
            MemorySegment misaligned = larger.asSlice(1, 4);
            slot.set(ADDRESS, 0, misaligned);

            try {
                slot.get(INT_POINTER, 0);
                System.out.println("Unexpected aligned");
            } catch (IllegalArgumentException expected) {
                System.out.println("Misaligned target: blocked");
            }

            slot.set(ADDRESS, 0, MemorySegment.NULL);
            MemorySegment nullPtr = slot.get(ADDRESS, 0);
            MemorySegment nullTyped = slot.get(INT_POINTER, 0);

            System.out.println("Null raw address: "
                    + (nullPtr.address() == 0));
            System.out.println("Null typed address: "
                    + (nullTyped.address() == 0));
            System.out.println("Null typed bytes: " + nullTyped.byteSize());
            // Không dereference nullTyped!
        }

        System.out.println("Typed global scope remains alive: "
                + typed.scope().isAlive());
        // Không dereference typed: vùng value đã bị arena.close() giải phóng.
    }
}
```

**Chạy trên JDK 22+ trong classpath:**

```bash
javac AddressTargetDemo.java
java --enable-native-access=ALL-UNNAMED AddressTargetDemo
```

**Stdout đã xác minh trên JDK 24, hệ 64-bit:**

```text
Pointer layout bytes: 8
Target layout bytes: 4
Carrier: true
Without target bytes: 0
With target bytes: 4
Same address: true
Read while owner open: 12345
Typed scope alive while open: true
Misaligned target: blocked
Null raw address: true
Null typed address: true
Null typed bytes: 4
Typed global scope remains alive: true
```

**Giải thích từng quan sát:**

1. Pointer dài 8 byte trên nền tảng 64-bit chạy kiểm chứng. Nền tảng 32-bit có thể báo 4 byte; **target `JAVA_INT` vẫn 4 byte**.
2. `slot.set(ADDRESS, 0, value)` ghi **địa chỉ của value** vào slot. Nó **không chuyển quyền sở hữu** allocation từ arena sang slot.
3. `slot.get(ADDRESS, 0)` trả view 0 byte, an toàn ở dạng pointer opaque.
4. `slot.get(INT_POINTER, 0)` trả view 4 byte. Khi arena đang mở, pointer trỏ đúng vào allocation 4 byte và có alignment 4, nên đọc ra `12345`.
5. Pointer `larger.asSlice(1,4)` không aligned 4 byte; `slot.get(INT_POINTER,0)` từ chối bằng `IllegalArgumentException` **trước khi dùng target**.
6. Một địa chỉ null khi đọc bằng target layout **vẫn có thể có `byteSize() == 4`**. **Không được dereference!** `byteSize` là annotation cho view, không phải bằng chứng cấp phát.
7. Sau close, `typed.scope().isAlive()` vẫn true vì pointer view trả về từ `get(AddressLayout)` là **global-scope segment**. **Điều này không làm allocation sống lại.** Đọc `typed` sau close là use-after-free và bị cố ý loại khỏi ví dụ.

Dòng cuối là bằng chứng đặc biệt quan trọng: **global scope của view dựng từ địa chỉ không chứng nhận lifetime của vùng nhớ ở địa chỉ đó**.

## 6. Rủi ro lifetime: pointer view và allocation gốc không chung scope

### 6.1. Source slot và target allocation có thể có hai owner khác nhau

Một con trỏ có thể được lưu trong vùng nhớ thuộc arena A nhưng trỏ đến vùng nhớ thuộc arena B:

```text
Arena A (sở hữu pointer slot)           Arena B (sở hữu actual data)
+-----------------------------+         +----------------------------+
| slot chứa địa chỉ X          | ------> | data tại X, 3 số int       |
+-----------------------------+         +----------------------------+

slot.get(ADDRESS.withTargetLayout(...),0)
                |
                v
        pointer-derived segment
          size = khai báo target
          scope = GLOBAL, không phải A hoặc B
```

Khi arena A đóng, Java không còn quyền đọc **ô lưu địa chỉ** `slot`. Nhưng nếu arena B còn mở và chương trình vẫn bảo đảm địa chỉ X hợp lệ, target data vẫn tồn tại.

Ngược lại, khi arena B đóng, dữ liệu X hết hạn **dù** pointer-derived segment có global scope đang báo alive. **Đừng đánh đồng lifetime của ô pointer, lifetime của view và lifetime của allocation thực sự.**

### 6.2. Pointer-derived segment không tự đóng theo owner

Khác với `MemorySegment` gốc được `Arena.ofConfined().allocate` trả về, một segment dựng từ **raw address đọc bằng `get(AddressLayout)`** mang global scope theo đặc tả. Nó có thể tiếp tục hiện diện sau khi owner free memory và `scope().isAlive()` vẫn true.

Điều đó khiến thiết kế chỉ dựa trên:

```java
if (pointer.scope().isAlive()) {
    int x = pointer.get(ValueLayout.JAVA_INT, 0);
}
```

**không đủ an toàn** đối với pointer-derived segment. Kiểm tra global scope hầu như không cung cấp thông tin vòng đời actual allocation.

**Trách nhiệm của ứng dụng** là giữ owner arena/handle sống ít nhất tới khi mọi lần dereference kết thúc, không cho nơi khác giải phóng sớm và không dùng pointer sau khi thư viện C đã invalidate nó.

## 7. Chương trình 2: con trỏ tới mảng và hai arena khác nhau

Bài thực hành dùng `MemoryLayout.sequenceLayout(3, JAVA_INT)` làm target. Pointer có view 12 byte, có thể đọc `getAtIndex` từ 0 đến 2 trong lúc allocation còn sống.

### 7.1. Tệp `PointerOwnershipDemo.java`

```java
import java.lang.foreign.*;
import static java.lang.foreign.ValueLayout.*;

public class PointerOwnershipDemo {
    private static final SequenceLayout THREE_INTS =
            MemoryLayout.sequenceLayout(3, JAVA_INT);

    private static final AddressLayout INT_ARRAY_POINTER =
            ADDRESS.withTargetLayout(THREE_INTS);

    public static void main(String[] args) {
        MemorySegment loaded;

        try (Arena dataOwner = Arena.ofConfined()) {
            MemorySegment data = dataOwner.allocate(THREE_INTS);
            data.setAtIndex(JAVA_INT, 0, 10);
            data.setAtIndex(JAVA_INT, 1, 20);
            data.setAtIndex(JAVA_INT, 2, 30);

            try (Arena slotOwner = Arena.ofConfined()) {
                MemorySegment slot = slotOwner.allocate(ADDRESS);
                slot.set(ADDRESS, 0, data);

                loaded = slot.get(INT_ARRAY_POINTER, 0);

                System.out.println("Array target bytes: " + loaded.byteSize());
                System.out.println("Value index 1: "
                        + loaded.getAtIndex(JAVA_INT, 1));
                System.out.println("Pointer global scope: "
                        + loaded.scope().isAlive());
            }

            System.out.println("Source slot closed, data alive: "
                    + data.scope().isAlive());
            System.out.println("Value index 2: "
                    + loaded.getAtIndex(JAVA_INT, 2));

            try {
                loaded.getAtIndex(JAVA_INT, 3);
            } catch (IndexOutOfBoundsException expected) {
                System.out.println("Outside declared target: blocked");
            }
        }

        System.out.println("Loaded pointer scope alive after free: "
                + loaded.scope().isAlive());
        // Không dereference loaded sau khi dataOwner đóng!
    }
}
```

**Chạy:**

```bash
javac PointerOwnershipDemo.java
java --enable-native-access=ALL-UNNAMED PointerOwnershipDemo
```

**Stdout đã xác minh trên JDK 24:**

```text
Array target bytes: 12
Value index 1: 20
Pointer global scope: true
Source slot closed, data alive: true
Value index 2: 30
Outside declared target: blocked
Loaded pointer scope alive after free: true
```

Tình huống học được:

- **Khi `slotOwner` đóng:** không thể đọc slot nữa, nhưng `dataOwner` vẫn mở; target data còn, nên `loaded.getAtIndex(...,2)` tại đây hợp lệ.
- **Khi `dataOwner` đóng:** actual allocation được giải phóng. `loaded.scope()` vẫn global và alive, nhưng nó đã trở thành **dangling view**. Mọi dereference tiếp theo đều bị coi là không hợp lệ theo hợp đồng ownership, dù layout và `byteSize` vẫn trông đúng.
- `getAtIndex(JAVA_INT,3)` bị chặn vì target view dài 12 byte; đây là **bounds check theo chiều dài đã khai báo**, không phải phép xác nhận physical allocation. Nếu target thực tế chỉ cấp phát 8 byte nhưng khai báo 12, truy cập index 2 cũng có nguy cơ memory corruption mà check theo view **không phát hiện**.

### 7.2. Tại sao không test bằng cách đọc sau free?

Vì việc dùng sai raw native pointer có thể **crash JVM**, làm hỏng bộ nhớ hoặc có hành vi không xác định trong native side. Một bài kiểm thử không nên cố tạo use-after-free như phương pháp chứng minh hợp đồng.

Muốn kiểm chứng logic owner, hãy kiểm tra `data.scope().isAlive()` trên segment **gốc được arena quản lý** và bố trí code sao cho mọi dereference của pointer-derived view chỉ diễn ra trong vùng `dataOwner` còn mở. Các test sai layout có thể dùng **địa chỉ hợp lệ nhưng lệch alignment**, hoặc offset ngoài **view đã khai báo**, không cần đưa JVM vào tình trạng đọc từ vùng nhớ đã free.

## 8. Struct C: khai báo target layout đúng ABI

Trong code C, một con trỏ `struct Record *` được hiểu theo kích thước, alignment và offset fields của struct mà compiler C thực sự sử dụng. Java cần một `MemoryLayout` khớp với **C ABI**. Không phải cứ gọi `withTargetLayout(structLayout)` là Java tự đoán đúng.

Ví dụ minh họa một bố trí cụ thể:

```c
/* Minh họa một ABI nơi int dài 4, int64_t dài 8,
   total ở offset 8 và sizeof(Record) bằng 16. */
struct Record {
    int32_t code;
    /* 4 bytes padding theo ABI minh họa */
    int64_t total;
};
```

Không mặc định C `long` luôn có 8 byte: trên Windows 64-bit, `long` thường 4 byte theo LLP64, trong khi trên Unix-like 64-bit nó thường 8 byte theo LP64. Phải dựa trên header và ABI của thư viện (ví dụ `int32_t`, `int64_t`), hoặc công cụ tạo binding/phép kiểm tra `sizeof`, `alignof` và `offsetof`.

### 8.1. Tệp `PointerStructDemo.java`

```java
import java.lang.foreign.*;
import static java.lang.foreign.ValueLayout.*;
import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class PointerStructDemo {
    private static final StructLayout RECORD = MemoryLayout.structLayout(
            JAVA_INT.withName("code"),
            MemoryLayout.paddingLayout(4),
            JAVA_LONG.withName("total"));

    private static final AddressLayout RECORD_POINTER =
            ADDRESS.withTargetLayout(RECORD);

    public static void main(String[] args) {
        System.out.println("Pointer carrier: "
                + (RECORD_POINTER.carrier() == MemorySegment.class));
        System.out.println("Address target present: "
                + ADDRESS.targetLayout().isPresent());
        System.out.println("Record target present: "
                + RECORD_POINTER.targetLayout().isPresent());
        System.out.println("Target bytes: "
                + RECORD_POINTER.targetLayout().orElseThrow().byteSize());
        System.out.println("Pointer bytes unchanged: "
                + (RECORD_POINTER.byteSize() == ADDRESS.byteSize()));
        System.out.println("Without target: "
                + RECORD_POINTER.withoutTargetLayout().equals(ADDRESS));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment record = arena.allocate(RECORD);
            record.set(JAVA_INT, RECORD.byteOffset(groupElement("code")), 7);
            record.set(JAVA_LONG, RECORD.byteOffset(groupElement("total")), 500L);

            MemorySegment slot = arena.allocate(ADDRESS);
            slot.set(ADDRESS, 0, record);

            MemorySegment throughPointer = slot.get(RECORD_POINTER, 0);
            System.out.println("Record bytes: " + throughPointer.byteSize());
            System.out.println("Code: " + throughPointer.get(JAVA_INT, 0));
            System.out.println("Total: " + throughPointer.get(JAVA_LONG, 8));
        }
    }
}
```

**Biên dịch/chạy:**

```bash
javac PointerStructDemo.java
java --enable-native-access=ALL-UNNAMED PointerStructDemo
```

**Stdout đã xác minh trên JDK 24:**

```text
Pointer carrier: true
Address target present: false
Record target present: true
Target bytes: 16
Pointer bytes unchanged: true
Without target: true
Record bytes: 16
Code: 7
Total: 500
```

Giải thích:

- `RECORD_POINTER.targetLayout()` chứa `RECORD`, trong khi `ValueLayout.ADDRESS.targetLayout()` mặc định rỗng.
- `RECORD_POINTER.byteSize()` vẫn là pointer storage size, bằng `ADDRESS.byteSize()`.
- `RECORD_POINTER.withoutTargetLayout()` trả một layout giống `ADDRESS` về các thuộc tính còn lại; **không có side effect lên `RECORD_POINTER`**, vì layout immutable.
- `MemoryLayout.paddingLayout(4)` thể hiện bốn byte đệm, để `total` nằm ở offset 8.
- `arena.allocate(RECORD)` tạo **actual native allocation hợp lệ** đúng layout; sau đó pointer được ghi vào slot và đọc thành view 16 byte.
- Chỉ đọc `throughPointer` khi `arena` vẫn còn mở. Trả `throughPointer` ra ngoài khối `try` rồi đọc sau close là sai, dù view dùng global scope.

### 8.2. Nhầm layout field với layout pointer

Không dùng `JAVA_LONG` để đọc *pointer value* chỉ vì con trỏ 64-bit rộng 8 byte. Address layout có carrier `MemorySegment`, tuân theo kích thước/ABI pointer; `JAVA_LONG` là layout một **Java long** 8 byte. Sự trùng kích thước trên một nền tảng không biến hai loại ABI thành tương đương.

Để đọc pointer `T*` được lưu trong struct C, field tương ứng thường dùng một `AddressLayout` (có target layout `T` nếu hợp đồng thật sự biết kích thước và lifetime của T). Để đọc nội dung `T` sau khi đã xác minh hợp đồng, dùng `ValueLayout`/`MemoryLayout` cho data, không tiếp tục đọc như các pointer bytes.

## 9. Alignment của slot và alignment của target là hai điều kiện khác nhau

Với `AddressLayout` có target:

1. **Ô lưu pointer:** phải đủ `ADDRESS.byteSize()` bytes, và vị trí đọc pointer phải đáp ứng `ADDRESS.byteAlignment()`.
2. **Pointer trỏ tới target:** địa chỉ đọc được phải đáp ứng `targetLayout.byteAlignment()` nếu layout yêu cầu.
3. **Vùng dữ liệu thực tế:** vẫn phải còn hợp lệ và có kích thước đúng, điều này **không** suy ra từ chỉ hai phép kiểm tra alignment.

Ví dụ: một slot pointer 8-byte-aligned có thể chứa địa chỉ của buffer bị lệch 1 byte. Khi đọc bằng `ADDRESS.withTargetLayout(JAVA_INT)` (target yêu cầu alignment 4), FFM sẽ từ chối bằng `IllegalArgumentException` do địa chỉ đích không aligned. Đây là trường hợp an toàn được thực thi ở chương trình `AddressTargetDemo`.

Nếu dữ liệu C thực tế được đóng gói không căn chỉnh (*packed*) và API hợp đồng cho phép, target layout có thể dùng `ValueLayout.JAVA_INT_UNALIGNED` (alignment 1). Tuy nhiên **không** đổi layout sang unaligned để che đi con trỏ hỏng, sai offset hoặc sai ABI.

**Alignment đúng không chứng minh pointer hợp lệ.** Một con trỏ đã `free` vẫn có thể chia hết cho 8; dereference nó có nguy cơ crash, cho dù `withTargetLayout` không báo lỗi.

## 10. Null pointer: view có kích thước nhưng không có bộ nhớ

Dữ liệu pointer của C có thể nhận giá trị `NULL`. Trong FFM:

```java
slot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);
MemorySegment ptr = slot.get(ValueLayout.ADDRESS, 0);

if (ptr.address() == 0) {
    // Không có referent hợp lệ để đọc.
}
```

**Đặc biệt:** khi đọc với `AddressLayout.withTargetLayout(JAVA_INT)`, pointer null trong thực nghiệm JDK 24 được trả về như một view có:

```text
nullTyped.address() == 0
nullTyped.byteSize() == 4
```

Con số `byteSize() == 4` chỉ do bạn **khai báo target**, không chứng minh 4 byte ở địa chỉ 0 được cấp phát. **Tuyệt đối không gọi `nullTyped.get(JAVA_INT, 0)`.** Truy cập invalid native memory có thể crash JVM hoặc gây lỗi nghiêm trọng, không được coi là một bài test bình thường để bắt bằng `try/catch`.

Quy trình xử lý pointer nullable:

```java
MemorySegment readPointer = slot.get(INT_POINTER, 0);
if (readPointer.address() == 0) {
    // Giá trị null: xử lý theo hợp đồng native (trả Optional.empty,
    // bỏ qua, hoặc ném exception Java ở boundary).
} else {
    // Phải xác minh size, lifetime, ownership, alignment, thread
    // trước khi dereference readPointer.
}
```

Đây là **đoạn minh họa** trong ngữ cảnh đã có `slot`, `INT_POINTER` và owner hợp lệ; không phải ứng dụng độc lập.

## 11. Ownership: ai cấp phát, ai giải phóng, pointer sống tới khi nào?

`withTargetLayout` hoàn toàn không trả lời ownership. Một API C có thể có những hợp đồng khác nhau:

| Nguồn pointer | Hợp đồng thường gặp | Java cần làm |
| --- | --- | --- |
| Trỏ tới vùng do `Arena.allocate` của Java tạo | Java arena sở hữu allocation | Giữ arena mở đến khi mọi native users hoàn tất; close đúng lúc |
| Native function trả **borrowed pointer** | Thư viện C vẫn sở hữu, có thể vô hiệu hóa khi owner close hoặc lần gọi sau | Chỉ dereference trong hạn sử dụng được tài liệu hóa; **không free** |
| Native function trả **owned pointer** | Caller được chuyển ownership và phải dùng native release phù hợp | Dùng đúng hàm giải phóng của thư viện, thường không phải Java `free` tùy ý |
| Trỏ đến dữ liệu tĩnh của thư viện | Lifetime theo thư viện/process | Không tự free; tránh dùng sau unload hoặc invalidation |
| Pointer tới buffer + length được trả riêng | Length thực tế biết ở runtime | Kiểm tra length, overflow, capacity; tạo view phù hợp **chỉ khi** pointer sống |
| Nullable pointer | `NULL` là giá trị hợp lệ báo không có dữ liệu | Kiểm tra địa chỉ 0 **trước khi dereference** |
| Pointer-to-pointer `T**` | Ô pointer chứa một pointer tới một vùng khác | Đọc từng tầng với layout và ownership của từng tầng, không nhầm target `T` với `T*` |

**Đây là hướng dẫn đọc hợp đồng ABI, không phải suy luận tự động từ Java `AddressLayout`.** Trong hệ thống thật, hãy lấy thông tin từ C header, tài liệu native library, mã nguồn công khai, hoặc binding generator đáng tin cậy. Nếu thư viện không chỉ rõ ownership/lifetime, **không đủ cơ sở** để làm một dereference an toàn.

### 11.1. Borrowed pointer

Giả sử C trả `const char *get_name()`, nhưng thư viện nói bộ nhớ chỉ hợp lệ cho tới lần gọi `update_name()` tiếp theo:

- Pointer thuộc thư viện; Java không `free`.
- Nếu cần giữ chuỗi sau lần cập nhật tiếp theo, **copy bytes/string** khi pointer còn hợp lệ.
- `withTargetLayout` không kéo dài lifetime và không bảo vệ được callback/native thread làm invalidation.
- C string có thể kết thúc bằng NUL trong một vùng có độ dài chưa biết; **đừng tự chọn một target size cực lớn rồi quét tùy ý**.

### 11.2. Owned pointer

Giả sử C trả `Widget *widget_create()` và cung cấp `void widget_destroy(Widget*)`:

- Caller Java cần wrapper hoặc owner record giữ handle và nắm nghĩa vụ `widget_destroy`.
- Nên cung cấp `close()`/`AutoCloseable`, gọi release đúng lúc; `Cleaner` nếu dùng thì chỉ là fallback best-effort.
- Tránh double-free và concurrent use-after-free giữa các threads.
- Không giả định `Arena.close()` tự gọi `widget_destroy` đối với pointer native trả về nếu không có cơ chế cleanup phù hợp.

Mã FFM thường cần linker/downcall handle cho hàm destroy của thư viện. Lựa chọn cụ thể tùy ABI và quy tắc owner; không gọi `free` cho mọi pointer, vì có thể thư viện dùng allocator/destructor riêng.

### 11.3. Cấu trúc chứa pointer trường bên trong

Ví dụ:

```c
struct BufferView {
    const unsigned char *data;
    size_t length;
};
```

Java cần đúng hai thông tin: `data` và `length`. Một `AddressLayout` có target layout cố định **không tự nhận ra** `length` tại runtime. Phải đọc length từ trường tương ứng đúng ABI, kiểm tra giới hạn và chỉ tạo view dài bằng số bytes thực sự còn sống. Trên nền tảng 32-bit/64-bit, width và alignment của `size_t` có thể khác nhau, nên layout Java phải khớp **C ABI**, không mặc định `size_t == JAVA_LONG`.

## 12. Xác định kích thước dữ liệu động: không đoán bằng kích thước pointer

Nếu thư viện trả một `T*` kèm số phần tử `count`, số bytes lý thuyết là:

\[
\text{bytes} = \text{count} \times \text{sizeof}(T)
\]

Nhưng công thức chỉ hữu ích khi cả ba điều kiện đúng:

1. `count` đến từ hợp đồng native đáng tin, không âm và không vượt maximum được thư viện cấp phát.
2. `sizeof(T)` là kích thước đúng theo ABI/MemoryLayout (kể cả padding của struct).
3. Allocation còn hợp lệ trong toàn bộ thời gian Java đọc/ghi.

Ví dụ chuẩn bị một target sequence layout theo count có kiểm tra overflow:

```java
static AddressLayout pointerToInts(long count) {
    if (count < 0 || count > 1_000_000) {
        throw new IllegalArgumentException("Untrusted count");
    }

    long bytes = Math.multiplyExact(
            count, ValueLayout.JAVA_INT.byteSize());

    MemoryLayout target = MemoryLayout.sequenceLayout(
            count, ValueLayout.JAVA_INT);

    if (target.byteSize() != bytes) {
        throw new AssertionError("Wrong layout size");
    }

    return ValueLayout.ADDRESS.withTargetLayout(target);
}
```

Đây là **helper minh họa** trong class đã import `java.lang.foreign.*`; gọi nó cần native-access permission do `withTargetLayout` là restricted. Giới hạn một triệu chỉ là **chính sách ví dụ**, không tự chứng minh thư viện cấp phát nhiều bytes ấy. Nếu `count` từ input không tin cậy, phải còn xác minh với capacity/contract thực sự của thư viện.

**Không dùng** target sequence kích thước `Long.MAX_VALUE` chỉ để tránh bounds checks. Javadoc có mô tả khả năng tạo view cực lớn bằng target sequence, nhưng điều đó là **unsafe declaration**, không phải chứng nhận vùng nhớ quá lớn tồn tại thật.

## 13. Scope của pointer view không thể thay cho scope của allocation thật

Đặc tả `MemorySegment.get(AddressLayout,long)` nói rõ pointer value được wrap trong native segment **associated with the global scope**, có hoặc không có target. Từ đây suy ra:

```text
    MemorySegment target = dataOwner.allocate(...)
        |
        +-- scope = dataOwner.scope()
        |
        +-- slot.set(ADDRESS, 0, target)
                |
                +-- slot.get(ADDRESS.withTargetLayout(...), 0)
                        |
                        +-- pointer-derived segment
                              scope = global scope
                              byteSize = targetLayout.byteSize()
```

Khi `dataOwner.close()`:

- `target.scope().isAlive()` trở thành false; access qua `target` sẽ bị chặn.
- Pointer-derived view **không** chuyển scope về false, vì nó không gắn trực tiếp với `dataOwner`.
- Giá trị địa chỉ và size của pointer-derived view có thể vẫn trông bình thường.
- **Không được dereference pointer-derived view**, vì actual allocation đã free.

Sự khác biệt này không phải “lỗi của FFM”: native pointer **không mang theo thông tin owner/lifetime**. API cố ý coi việc diễn giải pointer thành vùng nhớ là restricted và giao trách nhiệm spatial/temporal bounds cho người viết code.

### Khi nào nên dùng trực tiếp segment gốc thay vì pointer-derived view?

Nếu Java **đã nắm `MemorySegment target` gốc** do `Arena.allocate` trả về, hãy ưu tiên dùng `target.get/set` trực tiếp. Nó giữ bounds và scope đúng của arena. Không cần vòng qua `slot.set(ADDRESS,...); slot.get(withTargetLayout,...)` chỉ để đọc dữ liệu mà Java vốn đã sở hữu.

Chỉ giải mã pointer thành typed view khi pointer thực sự xuất hiện từ ABI native hoặc một cấu trúc dữ liệu yêu cầu việc đọc con trỏ. Khi đó phải có contract bổ sung về owner.

### Một mô hình guard hợp lý

Khi API Java là owner hoặc có quyền mượn pointer từ một owner, hãy đặt tất cả dereferences trong một thao tác quản lý vòng đời:

```java
try (Arena dataOwner = Arena.ofConfined()) {
    MemorySegment target = dataOwner.allocate(ValueLayout.JAVA_INT);
    target.set(ValueLayout.JAVA_INT, 0, 42);

    // Khi target còn sống: có thể tạo/đọc pointer liên quan.
    // Bất kỳ pointer-derived view nào cũng chỉ được sử dụng
    // trong khoảng bảo đảm dataOwner chưa đóng.

    System.out.println(target.get(ValueLayout.JAVA_INT, 0));
}
```

Nếu có nhiều thread dùng shared arena, cần protocol chặn close khi còn in-flight users. `scope().isAlive()` kiểm tra một lần rồi dereference sau đó không phải atomic reservation. Với raw native pointer, JVM không thể phát hiện mọi native worker vẫn dùng allocation.

## 14. Pointer và JNI: hai mô hình handle không được trộn lẫn

Trong module native interoperability, phân biệt rõ:

- **FFM pointer:** `AddressLayout`/`MemorySegment` biểu diễn native machine address và memory view. `withTargetLayout` khai báo vùng đích theo `MemoryLayout`, không sở hữu actual allocation.
- **JNI reference:** `jobject`, `jweak`, `jclass` là các **JNI handles** do JVM quản lý, **không phải** raw C pointers tới Java objects được phép dereference tùy ý.
- **JNI direct buffer:** `GetDirectBufferAddress` có thể cung cấp native address trong điều kiện API quy định, nhưng lifetime của backing buffer vẫn phải được bảo vệ theo hợp đồng; không tự assume có thể `free` địa chỉ ấy.
- **C library pointer:** `void*`, `char*` hoặc struct pointer có thể mang ownership riêng; phải dùng đúng native destructor nếu được giao sở hữu.

Không lưu `jobject` vào một vùng nhớ rồi diễn giải là `AddressLayout` native pointer tới object. Không đổi `jweak` thành `MemorySegment.ofAddress` rồi dereference. Chúng là **hai cơ chế hoàn toàn khác**; sai lầm có thể làm hỏng JVM.

`AddressLayout.withTargetLayout` không thể bảo vệ vòng đời các JNI global/local references hoặc thay thế `DeleteGlobalRef`/`DeleteWeakGlobalRef`.

## 15. Những lỗi phổ biến

| Sai lầm | Điều thực tế xảy ra | Cách sửa |
| --- | --- | --- |
| “withTargetLayout(JAVA_INT) tạo 4 byte memory” | Chỉ tạo metadata layout và view 4 byte khi đọc pointer | Cấp phát/nhận allocation hợp lệ riêng, xác minh ownership |
| “Có byteSize() == 4 thì chắc chắn đọc 4 byte an toàn” | View bounds là một cam kết do caller khai báo, không kiểm chứng actual allocation | Đối chiếu C contract: real size và lifetime |
| “Pointer vừa được đọc từ slot sống trong arena thì có cùng scope” | Pointer-derived segment mang **global scope** | Theo dõi actual target owner bằng cơ chế riêng |
| “scope().isAlive() của loaded true, vậy allocation chưa free” | Global scope luôn có thể alive dù target owner đóng | Không dùng after free; guard bằng owner/borrow |
| “Pointer alignment đúng thì địa chỉ hợp lệ” | Dangling pointer cũng có thể aligned | Kiểm tra provenance, lifetime và valid allocation từ hợp đồng |
| “Pointer null với target có byteSize>0 nghĩa có buffer” | Null address vẫn không có referent hợp lệ | Kiểm tra `address()==0` trước dereference |
| “withTargetLayout thay đổi kích thước pointer lưu trong struct” | Pointer size giữ nguyên `ADDRESS.byteSize()` | Dùng target layout để mô tả dữ liệu, không mô tả pointer width mới |
| “Dùng JAVA_LONG để đọc pointer trên mọi ABI” | C pointer width có thể khác Java long width | Dùng `ValueLayout.ADDRESS` cho pointer |
| “C long luôn giống Java long” | ABI LP64/LLP64 khác nhau | Dùng layout phù hợp struct header / `int64_t` / ABI |
| “C string pointer luôn trỏ đủ N byte tôi chọn” | Độ dài và điểm NUL phụ thuộc contract | Dùng API có length, áp dụng size cap và lifetime |
| “withTargetLayout cho phép đọc qua arena đã đóng” | Nó có thể cho phép access vào address stale và gây crash | Tuyệt đối không dereference sau deallocation |
| “Cứ khai báo Long.MAX_VALUE để khỏi lỗi bounds” | Cực kỳ unsafe, view không phản ánh actual allocation | Chỉ khai báo đúng memory bounds |
| “Nếu slot owner đóng thì target lập tức bị free” | Source slot và target có thể thuộc hai owners khác nhau | Theo dõi riêng vòng đời từng allocation |
| “Nếu target owner đóng, typed view tự bị đóng” | Pointer-derived view có global scope, không có automatic invalidation | Chặn mọi use sau owner close |
| “Layout gắn tên/type là bảo đảm C data đúng kiểu” | Layout chỉ diễn giải bytes, không kiểm chứng struct ABI | Khớp byte order, field sizes, padding, alignment |

## 16. Quy trình review khi gặp AddressLayout.withTargetLayout

Khi review đoạn code dùng restricted target layout, hãy trả lời **từng câu hỏi**:

1. **Nguồn địa chỉ:** pointer đến từ đâu? `Arena.allocate`, field của struct, native return, JNI direct buffer hay foreign library?
2. **NULL:** pointer có nullable không? Có check `address()==0` trước mọi dereference không?
3. **Cấp phát:** đã chắc đây là vùng nhớ **native thật**, không phải địa chỉ ảo hóa của heap segment hoặc JNI handle?
4. **Kích thước:** target layout có chính xác `sizeof`/count/capacity được thư viện cấp phát không? Có overflow/giới hạn input?
5. **Căn chỉnh:** địa chỉ pointer và các field targets có phù hợp alignment của layout/ABI không? Dữ liệu có packed không?
6. **Lifetime:** ai quyết định pointer hết hạn? `Arena.close`, `free`, callback khác, lần gọi C API tiếp theo, unload library?
7. **Ownership:** ai được gọi destructor? Nếu borrowed thì tuyệt đối không free; nếu owned thì đúng hàm cleanup nào?
8. **Luồng:** có native workers/callbacks nào dùng pointer khi Java có thể close không? Có thread affinity?
9. **Scope:** code có nhầm global scope của pointer-derived view là owner scope của actual allocation không?
10. **Đường lỗi:** khi pointer null, target size thiếu, allocation đã hết hạn, native error… API Java phải trả gì/throw gì?
11. **Thời điểm copy:** nếu cần dữ liệu sau lifetime ngắn, có copy vào owned Java array hoặc memory thuộc arena lâu sống hơn không?
12. **Restricted methods:** ứng dụng có cấu hình native access phù hợp, hiểu trách nhiệm unsafe của `withTargetLayout` không?
13. **Test:** có kiểm tra layout properties, correct alignment, bounds của view, ownership trong phạm vi còn sống; **không test bằng dereference pointer đã free**?

### Bảng quyết định nhanh

| Trường hợp | Lựa chọn đề xuất |
| --- | --- |
| Java đã giữ `MemorySegment` gốc có scope hợp lệ | Dùng trực tiếp segment gốc, không round-trip qua pointer |
| Chỉ cần truyền pointer opaque tới hàm native khác | `ValueLayout.ADDRESS` không target, view 0 byte |
| Đã biết target là đúng một `int` và lifetime được quản lý | `ADDRESS.withTargetLayout(JAVA_INT)` với native access enabled |
| Đã biết target là 3 `int` cùng allocation hợp lệ | `ADDRESS.withTargetLayout(sequenceLayout(3,JAVA_INT))` |
| C trả pointer tới struct với ABI xác định | Tạo `MemoryLayout.structLayout` đúng fields/padding/size/alignment |
| Target length ở runtime | Xác minh count và capacity, rồi tạo sequence layout phù hợp |
| Pointer nullable | Check `address()==0`; không dereference khi null |
| Native data cần giữ sau khi owner giải phóng | Copy sang storage có lifetime độc lập trước khi free |
| Native pointer có thể hết hạn bất đồng bộ | Thiết kế owner/lease/copy/synchronization; target layout không đủ |
| Không có tài liệu ownership/lifetime | Không dereference; cần xác minh hợp đồng trước |

## 17. Bài tập tự kiểm tra

**Câu 1.** `AddressLayout p = ValueLayout.ADDRESS.withTargetLayout(JAVA_INT)` có làm `p.byteSize()` bằng 4 không?

**Đáp án:** Không nhất thiết; `p.byteSize()` vẫn là **kích thước pointer** (ví dụ 8 trên hệ 64-bit). Khi dùng `get(p,offset)`, segment trả về có `byteSize()` bằng target size 4.

**Câu 2.** Đọc `slot.get(ADDRESS,0)` cho một địa chỉ khác 0 nhưng kết quả có `byteSize() == 0`. Tại sao?

**Đáp án:** Không có target layout, nên API không biết actual allocation size. View 0 byte cho phép giữ/truyền pointer dạng opaque mà không tự ý cung cấp quyền đọc các bytes đích.

**Câu 3.** `slot.get(ADDRESS.withTargetLayout(sequenceLayout(3,JAVA_INT)),0)` có thể trả view 12 byte. Điều đó chứng minh thư viện C đã cấp phát đủ 12 byte không?

**Đáp án:** Không. Độ dài view được gán từ target layout **do Java khai báo**. Phải kiểm tra count/capacity và hợp đồng allocation của C; khai báo sai có nguy cơ memory corruption.

**Câu 4.** Slot pointer được cấp phát trong `Arena A`, còn dữ liệu trỏ tới thuộc `Arena B`. Đóng A làm B hết hạn không?

**Đáp án:** Không tự động. A chỉ sở hữu slot; lifetime dữ liệu phụ thuộc B. Nếu B còn sống, pointer được đọc từ slot trước đó có thể vẫn hợp lệ (nếu không có điều kiện invalidation khác).

**Câu 5.** Khi đóng B, `loaded.scope().isAlive()` vẫn true vì loaded là pointer-derived global-scope view. Có thể đọc loaded không?

**Đáp án:** Không. Pointer-derived global scope **không theo dõi lifetime của actual allocation**. Đọc sau B.close là use-after-free, phải tránh.

**Câu 6.** `slot` chứa pointer null. Nếu dùng target layout, kết quả có `byteSize() = 4`, vậy có thể đọc `get(JAVA_INT,0)` không?

**Đáp án:** Không. Địa chỉ 0 không phải referent hợp lệ; size là annotation. Kiểm tra `address()==0` và xử lý null theo contract.

**Câu 7.** Pointer target địa chỉ +1 không aligned 4 byte. `withTargetLayout(JAVA_INT)` giúp gì?

**Đáp án:** Khi đọc địa chỉ bằng target layout, FFM có thể ném `IllegalArgumentException` nếu target pointer không tương thích alignment 4. Nhưng điều này không kiểm tra pointer còn sống hay actual size.

**Câu 8.** Một native method trả pointer được thư viện C sở hữu và chỉ sống đến lần gọi native tiếp theo. Java muốn lưu nội dung lâu dài phải làm gì?

**Đáp án:** Copy dữ liệu hợp lệ **trước** khi native call tiếp theo hoặc invalidation xảy ra. Không `free` borrowed pointer; target layout không kéo dài lifetime.

**Câu 9.** Một struct C có `int32_t code`, `int64_t total` tại offset 8 và total size 16. Có thể chỉ dùng `JAVA_INT` + `JAVA_LONG` liền nhau rồi giả định đúng không?

**Đáp án:** Không. Phải mô tả padding 4 byte hoặc layout tương đương theo ABI; dùng `structLayout(JAVA_INT, paddingLayout(4), JAVA_LONG)` trong ví dụ. Sau đó kiểm tra offsets, alignment, sizeof.

**Câu 10.** Có nên dùng target sequence `Long.MAX_VALUE` để né `IndexOutOfBoundsException` khi đọc pointer native?

**Đáp án:** Không. Đó là việc khai báo bounds cực rộng không tương xứng với actual allocation, dễ dẫn tới crash/corruption. Chỉ khai báo size dựa trên hợp đồng đã kiểm chứng.

**Câu 11.** Vì sao `withTargetLayout` được đánh dấu restricted?

**Đáp án:** Vì nó có thể làm một pointer view zero-length được diễn giải thành vùng nhớ có kích thước do caller khai báo. Nếu kích thước hoặc lifetime khai báo không đúng với actual memory, việc access có thể vượt ra khỏi bảo đảm safety của JVM và gây lỗi nghiêm trọng.

**Câu 12.** Nếu Java đang giữ segment gốc `MemorySegment data` từ `Arena.allocate`, liệu nên luôn chuyển sang pointer rồi dùng `withTargetLayout` để đọc không?

**Đáp án:** Không. Segment gốc đã mang size và scope chính xác do arena quản lý. Dùng trực tiếp nó là cách giảm nguy cơ đánh mất thông tin lifecycle. Pointer-derived view chỉ cần khi thực sự nhận một địa chỉ từ ABI native.

## Tài liệu chính thức

- [Java SE 22 — AddressLayout: withTargetLayout, targetLayout, withoutTargetLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/AddressLayout.html)
- [Java SE 24 — AddressLayout: restricted access và alignment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/AddressLayout.html)
- [Java SE 22 — MemorySegment: zero-length pointers, get(AddressLayout), global scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 24 — MemorySegment: pointer read và access safety](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 24 — ValueLayout.ADDRESS](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Java SE 24 — Arena: lifetime và quyền giải phóng](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html)
- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454)

**Ghi nhớ:** `AddressLayout.withTargetLayout` khai báo **view size và alignment mong đợi của pointer target**. Nó không xác minh **vùng nhớ đích có thật, đúng size, còn sống, được phép truy cập hay thuộc ownership của Java**. Mọi dereference phải tuân theo hợp đồng native và sự quản lý vòng đời actual allocation — **đừng nhầm “typed pointer” với “safe pointer”.**
