# Phân biệt segment chứa địa chỉ với vùng nhớ mà địa chỉ trỏ tới

## 1. Hai vùng nhớ khác nhau có thể xuất hiện trong một phép truy cập con trỏ

Khi lập trình Java với Foreign Function & Memory API (FFM API), câu lệnh `slot.get(ValueLayout.ADDRESS, 0)` rất dễ gây hiểu nhầm. Nó **đọc một giá trị địa chỉ (pointer value) từ vùng nhớ `slot`**, chứ không có nghĩa `slot` chính là vùng dữ liệu mà địa chỉ ấy trỏ đến.

Cần phân biệt ba thực thể:

1. **Pointer slot** — vùng nhớ *chứa các byte biểu diễn một địa chỉ*, có kích thước thường bằng `ValueLayout.ADDRESS.byteSize()`. Nó tương đương một ô lưu biến con trỏ `int *p` trong mô hình C.
2. **Pointer value / address segment** — giá trị được đọc từ slot bằng `get(ValueLayout.ADDRESS, offset)`. Java biểu diễn giá trị địa chỉ này bằng một `MemorySegment`; thông thường segment kết quả có **`byteSize() == 0`**, vì JVM chưa biết vùng đích rộng bao nhiêu.
3. **Pointee / target region** — vùng nhớ thật ở địa chỉ vừa đọc, ví dụ ba số nguyên 32-bit liên tiếp. Vùng đích có kích thước, quyền truy cập, lifetime và **chủ sở hữu riêng**. Muốn đọc dữ liệu ở vùng này, cần một segment view có giới hạn bộ nhớ đúng và phải bảo đảm vùng nhớ ấy thực sự còn hợp lệ.

Sơ đồ minh họa trên nền tảng con trỏ 64-bit:

```text
Vùng A: pointer slot (8 byte)                Vùng B: pointee (12 byte)
địa chỉ minh họa 0xA000                      địa chỉ minh họa 0xB000
┌──────────────────────────┐                  ┌────────┬────────┬────────┐
│ lưu pointer value 0xB000 ├───────────────►  │ int 10 │ int 20 │ int 30 │
└──────────────────────────┘                  └────────┴────────┴────────┘
 ^                                             ^
 |                                             |
 slot.address() = 0xA000                       data.address() = 0xB000
 slot.byteSize() = 8                           data.byteSize() = 12

slot.get(ValueLayout.ADDRESS, 0) trả về một address segment:
  address()  = 0xB000
  byteSize() = 0 (nếu ADDRESS không có target layout)
```

**Các địa chỉ 0xA000 và 0xB000 chỉ để minh họa**, không phải địa chỉ thực tế hay giá trị được bảo đảm khi chạy chương trình.

Điểm then chốt: **địa chỉ *của* pointer slot** và **giá trị địa chỉ *lưu trong* pointer slot** là hai số khác nhau. Một segment chứa pointer không tự động là segment của vùng nhớ mà pointer trỏ tới.

### 1.1. Liên hệ với C/C++

```c
int values[3] = {10, 20, 30};
int *p = values;

int first = *p;         /* 10: đọc dữ liệu tại địa chỉ p */
int second = p[1];      /* 20: đọc phần tử kế tiếp */
int **pp = &p;          /* pp là địa chỉ của biến con trỏ p */
int viaTwoLevels = **pp;/* 10: đi qua hai lớp con trỏ */
```

Đây là **fragment C**, không phải file C có `main()`. Các quan hệ:

- `&p`: địa chỉ nơi lưu biến con trỏ `p` (mức chứa địa chỉ).
- `p`: giá trị địa chỉ trỏ tới `values[0]`.
- `*p`: dữ liệu ở vùng đích (`values[0]`).
- `pp`: pointer-to-pointer; phải đọc hai cấp để đến giá trị `int`.

Trong FFM, `MemorySegment` có thể đóng cả vai trò *slot*, *address wrapper*, hoặc *data view*, tùy cách nó được tạo và API được gọi. **Cùng kiểu Java `MemorySegment` không đồng nghĩa cùng mục đích hay cùng quyền sở hữu.**

> **Phiên bản:** Bài sử dụng `java.lang.foreign` của **JDK 22+** (FFM API chính thức từ JDK 22, JEP 454). Trong JDK 17 không có cùng API ổn định. Những ví dụ có `reinterpret`/`withTargetLayout` là các **restricted methods**, cần bật quyền native access; không dùng các đoạn JDK 22 này nguyên xi với JDK 17.

## 2. Bảng phân biệt: slot, address value và pointee

| Đặc điểm | Pointer slot `slot` | Address segment `p` đọc từ slot | Target segment `data` |
| --- | --- | --- | --- |
| Đại diện cho | Bytes lưu một giá trị con trỏ | Địa chỉ lấy từ giá trị con trỏ | Bytes dữ liệu thật được trỏ tới |
| Nguồn tạo mẫu | `arena.allocate(ValueLayout.ADDRESS)` | `slot.get(ValueLayout.ADDRESS, 0)` | `arena.allocate(...bytes...)` |
| `address()` | Địa chỉ **của slot** | Địa chỉ **được lưu trong slot** | Địa chỉ **của data** |
| `byteSize()` | `ADDRESS.byteSize()` | Thông thường **0**, nếu không có target layout | Kích thước dữ liệu, ví dụ 12 byte |
| Đọc kiểu `int` ở offset 0 | Đọc **bytes của pointer value**, không phải pointee | Bị từ chối do kích thước 0 | Đọc dữ liệu `int` của pointee |
| Lifetime | Theo arena/owner của slot | Wrapper mặc định gắn với **global scope** | Theo arena hoặc native allocator của target |
| Giải phóng | Giải phóng *vùng lưu con trỏ* | Không tự sở hữu/free target | Theo owner/allocator thật sự của target |

`ValueLayout.ADDRESS` là `AddressLayout`, với size/alignment của địa chỉ phụ thuộc platform (ví dụ 8 byte trên hệ 64-bit thông dụng). **Không hard-code 8** cho mọi hệ.

### 2.1. `segment.address()` không phải `segment.get(ADDRESS, 0)`

Hai câu lệnh này làm việc khác nhau:

```java
long addressOfSlot = slot.address();

MemorySegment storedAddress =
        slot.get(ValueLayout.ADDRESS, 0L);
long addressOfTarget = storedAddress.address();
```

Đây là **fragment** giả định `slot` là native memory segment còn sống, đủ rộng và aligned để chứa một địa chỉ hợp lệ. `addressOfSlot` là chỗ lưu pointer, còn `addressOfTarget` là giá trị pointer đọc ra. Không sử dụng `address()` của heap segment như địa chỉ C: địa chỉ của heap segment được virtualize và có thể bằng 0, không phải con trỏ ổn định có thể truyền tùy ý cho C.

### 2.2. Một pointer value không mang thông tin kích thước

Trong C, `int *p` không chứa `sizeof` của mảng đích. Khi FFM đọc một pointer qua `ValueLayout.ADDRESS`, Java cũng không tự biết nó trỏ tới một `int`, 3 `int`, struct C hay một vùng nhớ đã bị free.

Vì thế JDK 22 mặc định trả **zero-length native segment** từ một pointer vừa đọc:

```java
MemorySegment raw = slot.get(ValueLayout.ADDRESS, 0L);

System.out.println(raw.byteSize()); // 0
```

Mặc định `raw` có **global scope**, không tự kế thừa lifetime của `slot` hoặc của vùng target. Global scope của *wrapper* **không có nghĩa dữ liệu đích sống mãi**.

Nếu thử:

```java
// Fragment minh họa lỗi nếu raw là zero-length segment.
int x = raw.get(ValueLayout.JAVA_INT, 0L);
```

thao tác bị từ chối vì `raw.byteSize() == 0`, nên không đủ 4 byte đọc `int`. Kỳ vọng `IndexOutOfBoundsException`, **không** tự động đọc vùng đích.

Đây là một rào cản an toàn có chủ ý: muốn dereference pointer, lập trình viên phải đưa ra thông tin về kích thước và lifetime, thay vì JVM đoán.

## 3. Ba thao tác then chốt với AddressLayout

### 3.1. `set(ADDRESS, offset, value)` ghi một **giá trị địa chỉ**

```java
MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
MemorySegment data = arena.allocate(
        ValueLayout.JAVA_INT.byteSize(),
        ValueLayout.JAVA_INT.byteAlignment());

data.set(ValueLayout.JAVA_INT, 0L, 123);
slot.set(ValueLayout.ADDRESS, 0L, data);
```

Đây là fragment sử dụng một `Arena arena` còn sống. `slot.set(ADDRESS, 0, data)` **sao chép giá trị địa chỉ của `data` vào vùng nhớ `slot`**. Nó không sao chép 4 byte số `123` vào slot, không tạo bộ nhớ data mới và không chuyển quyền sở hữu từ arena sang slot.

### 3.2. `get(ADDRESS, offset)` đọc giá trị địa chỉ thành một MemorySegment

```java
MemorySegment addressValue =
        slot.get(ValueLayout.ADDRESS, 0L);
```

`addressValue.address()` là địa chỉ đã lưu trong slot, thường bằng `data.address()` ở ví dụ trên; **`addressValue.byteSize() == 0`** vì layout chỉ là `ValueLayout.ADDRESS` chưa có target layout.

Chú ý rằng `addressValue` **không phải** `data`: nó chỉ là wrapper mới đại diện cùng địa chỉ. Hai segment có thể khác kích thước và scope. Đọc/ghi một địa chỉ đúng không làm Java phát hiện allocator, bounds hay quyền free của target.

### 3.3. `get(JAVA_INT, offset)` trên slot đọc bytes của con trỏ, không dereference

```java
// SAI về ngữ nghĩa nếu mục tiêu là giá trị int ở data:
int notPointee = slot.get(ValueLayout.JAVA_INT, 0L);
```

Nếu alignment/bounds cho phép, lệnh này đọc **4 byte đầu của vùng lưu địa chỉ** rồi diễn giải thành `int`. Giá trị phụ thuộc platform/address layout và không phải `data.get(JAVA_INT, 0)`. **Không dùng cách này để chuyển pointer sang `int`**, và không coi nó là cách dereference.

Đường truy cập đúng phải có một **segment view tới target** với kích thước/lifetime hợp lệ, ví dụ original `data` vẫn đang trong scope, hoặc một view được tạo có chủ đích từ pointer.

## 4. Ví dụ hoàn chỉnh JDK 22+: một slot chứa pointer, một vùng chứa dữ liệu

Ví dụ tạo mảng 3 `int` trong native memory, tạo pointer slot riêng, ghi địa chỉ mảng vào slot, đọc địa chỉ, rồi **mở rộng view một cách tường minh** để truy cập target. Chương trình dùng chung `Arena.ofConfined()` cho cả hai vùng cấp phát, vì vậy **lifetime của target đã biết rõ trong demo**.

Tệp **`PointerSlotDemo.java`**:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class PointerSlotDemo {
    public static void main(String[] args) {
        var intLayout = ValueLayout.JAVA_INT;

        try (Arena arena = Arena.ofConfined()) {
            // Vùng đích: 3 giá trị int (12 byte).
            MemorySegment data = arena.allocate(
                    3L * intLayout.byteSize(),
                    intLayout.byteAlignment());

            data.setAtIndex(intLayout, 0L, 10);
            data.setAtIndex(intLayout, 1L, 20);
            data.setAtIndex(intLayout, 2L, 30);

            // Vùng chứa 1 pointer, không phải vùng 3 int.
            MemorySegment slot =
                    arena.allocate(ValueLayout.ADDRESS);

            // Ghi ĐỊA CHỈ data vào slot.
            slot.set(ValueLayout.ADDRESS, 0L, data);

            // Đọc GIÁ TRỊ pointer lưu tại slot.
            MemorySegment addressValue =
                    slot.get(ValueLayout.ADDRESS, 0L);

            System.out.println(
                    "slot has one pointer: " +
                    (slot.byteSize() ==
                            ValueLayout.ADDRESS.byteSize()));
            System.out.println(
                    "slot and data separate: " +
                    (slot.address() != data.address()));
            System.out.println(
                    "stored pointer targets data: " +
                    (addressValue.address() == data.address()));
            System.out.println(
                    "address view bytes: " +
                    addressValue.byteSize());

            // Zero-length pointer wrapper không thể đọc int.
            try {
                addressValue.get(intLayout, 0L);
            } catch (IndexOutOfBoundsException ex) {
                System.out.println(
                        "direct read of zero-length view: rejected");
            }

            // RESTRICTED: chỉ hợp lệ vì ta BIẾT data được arena
            // cấp phát với đúng 12 byte và chưa bị giải phóng.
            MemorySegment targetView = addressValue.reinterpret(
                    data.byteSize(), arena, null);

            System.out.println(
                    "target int[1] via pointer: " +
                    targetView.getAtIndex(intLayout, 1L));

            // targetView và data cùng nhìn tới 1 vùng dữ liệu.
            targetView.setAtIndex(intLayout, 2L, 99);
            System.out.println(
                    "original data int[2]: " +
                    data.getAtIndex(intLayout, 2L));

            // Xóa GIÁ TRỊ con trỏ trong slot, không free data.
            slot.set(ValueLayout.ADDRESS, 0L, MemorySegment.NULL);
            System.out.println(
                    "slot is NULL: " +
                    (slot.get(ValueLayout.ADDRESS, 0L)
                            .address() == 0L));

            System.out.println(
                    "data still valid: " +
                    data.getAtIndex(intLayout, 2L));
        }
        // Đóng arena: data và slot cùng hết lifetime.
    }
}
```

Dùng **JDK 22+**:

```bash
javac PointerSlotDemo.java
java --enable-native-access=ALL-UNNAMED PointerSlotDemo
```

`reinterpret(...)` là **restricted method** trong JDK 22, nên lệnh chạy mở native access cho lớp không thuộc named module bằng `--enable-native-access=ALL-UNNAMED`. Trong ứng dụng module hóa, cấp native access cho **đúng module cần dùng**, thay vì mở rộng toàn bộ khi không cần. Đừng bỏ restricted-method warning/error vì đây là ranh giới kiểm soát truy cập bộ nhớ raw.

**Stdout dự kiến** (không in địa chỉ cụ thể để không phụ thuộc platform):

```text
slot has one pointer: true
slot and data separate: true
stored pointer targets data: true
address view bytes: 0
direct read of zero-length view: rejected
target int[1] via pointer: 20
original data int[2]: 99
slot is NULL: true
data still valid: 99
```

### 4.1. Tại sao ba giá trị trên độc lập với kích thước pointer?

- `slot.byteSize() == ValueLayout.ADDRESS.byteSize()` đúng trên mọi nền tảng nếu `arena.allocate(ValueLayout.ADDRESS)` thành công.
- `data.byteSize() == 3 * JAVA_INT.byteSize() == 12`; data và slot là hai allocation riêng biệt, còn sống cùng lúc nên địa chỉ đầu khác nhau.
- `addressValue.address() == data.address()` vì `set(ADDRESS, 0, data)` đã ghi chính địa chỉ native của data.
- `addressValue.byteSize() == 0` do `get` dùng ADDRESS **không có target layout**.
- Cả `getAtIndex(intLayout, 1)` trên target view lẫn trên data đều truy cập byte offset 4 của cùng một vùng nhớ, trả `20`.
- Việc set `int[2] = 99` qua target view thay đổi **chính allocation data**, không tạo array mới.
- Ghi `MemorySegment.NULL` vào slot khiến **giá trị con trỏ** trong slot bằng 0. Nó **không giải phóng allocation data**, nên `data.getAtIndex(..., 2)` vẫn trả `99` cho tới khi arena đóng.

**Không dùng `targetView` sau khi arena đóng.** Việc `reinterpret(..., arena, null)` gắn temporal bounds của view với arena chỉ bảo vệ khi lifetime thực sự phù hợp; nó không tạo ra hay chuyển giao ownership của bytes đích.

## 5. `reinterpret`: khai báo vùng nhớ đích có chủ đích, không tự cấp phát

JDK 22 cung cấp `MemorySegment.reinterpret(...)` để tạo view với spatial/temporal bounds khác. Đặc biệt:

```java
MemorySegment zeroLength =
        slot.get(ValueLayout.ADDRESS, 0L);

// Dữ liệu đích thực tế rộng N byte và còn sống:
MemorySegment view = zeroLength.reinterpret(
        N, arena, null);
```

Đây là **fragment**, giả định `slot` chứa một pointer **khác NULL, hợp lệ**, `N` là độ dài đã được xác minh từ contract và `arena` thực sự mô hình hóa lifetime của vùng đích. `reinterpret` được đánh dấu **restricted**; phải bật quyền native access.

### 5.1. Điều gì thay đổi và không thay đổi?

| Thuộc tính | Sau `reinterpret(N, arena, null)` |
| --- | --- |
| Địa chỉ bắt đầu | **Không thay đổi**; vẫn là địa chỉ pointer đã đọc |
| `byteSize()` | Trở thành `N` |
| Phạm vi sống (scope) | Gắn với `arena.scope()` được cung cấp |
| Thread confinement | Theo đặc tính arena mới |
| Có copy dữ liệu không? | **Không** |
| Có tạo allocation mới cho pointee không? | **Không** |
| Có kiểm chứng địa chỉ đang trỏ vào N byte thật không? | **Không** |
| Có tự nhận quyền free vùng nhớ gốc không? | **Không** nếu không đăng ký cleanup hợp lệ; vẫn phải quản lý theo owner thật |

`reinterpret` cho JVM một *giả định* về kích thước và lifetime. Nếu giả định sai, giới hạn ảo không ngăn truy cập một địa chỉ vốn đã bị free hoặc không thuộc process. Hậu quả có thể là **native memory corruption hoặc JVM crash**, chứ không nhất thiết chỉ là Java exception.

### 5.2. Rủi ro của `reinterpret(long)` không kèm arena

```java
// Chỉ là fragment để so sánh API; không thực hiện
// trên pointer chưa được chứng minh còn hợp lệ.
MemorySegment widened = rawPointer.reinterpret(16L);
```

Overload `reinterpret(long)` tạo native segment có cùng địa chỉ và scope của pointer wrapper. Với pointer đọc qua `get(ADDRESS, 0)`, scope mặc định là **global scope**. Vì vậy view có kích thước 16 nhưng **không tự biết** pointee thuộc arena nào hay được free khi nào.

Nếu vùng đích thuộc một `Arena.ofConfined()` đã đóng, `widened` vẫn mang scope toàn cục và có thể cho phép một access không an toàn tới vùng đã bị thu hồi. **Nên ưu tiên view có scope đúng** khi contract cho phép, và quan trọng nhất là quản lý owner sao cho không giải phóng pointee trong lúc view được dùng.

### 5.3. Đừng tự gắn một arena bất kỳ

Nếu pointer đến từ C `malloc`, không thể gán `reinterpret(size, arbitraryArena, null)` rồi giả định đóng arena ấy sẽ tự gọi đúng `free`. Nếu pointer trỏ vào memory do thư viện khác quản lý (database, GPU, mapped buffer, SDK callback), người dùng còn phải tôn trọng hợp đồng của thư viện ấy.

Ví dụ một C API công khai:

```c
/* Fragment C minh họa hợp đồng sở hữu: */
void *library_allocate(size_t bytes);
void library_release(void *p);
```

Java có thể tạo view có kích thước phù hợp, nhưng để giải phóng cần **gọi đúng `library_release` theo contract**. Không gọi `free` chung nếu thư viện dùng allocator riêng. Các cleanup callback của FFM cần được thiết kế cẩn thận, tránh free khi còn người dùng khác hoặc free trùng.

## 6. `AddressLayout.withTargetLayout`: cung cấp kích thước đích ngay trên layout

Nếu biết **target layout tĩnh**, có thể mô tả quan hệ pointer → pointee trên `AddressLayout`:

```java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;

// Fragment: pointer tới đúng 3 số int liên tiếp.
AddressLayout pointerToThreeInts =
        ValueLayout.ADDRESS.withTargetLayout(
                MemoryLayout.sequenceLayout(
                        3, ValueLayout.JAVA_INT));

// slot chứa địa chỉ target native hợp lệ, đủ 12 byte:
MemorySegment target = slot.get(
        pointerToThreeInts, 0L);

System.out.println(target.byteSize()); // 12
```

**`withTargetLayout(...)` cũng là restricted method** trong JDK 22, cần native access. Với target layout `T`, `slot.get(addressLayoutWithT, offset)` sẽ trả một segment có `byteSize() == T.byteSize()` thay vì 0, đồng thời kiểm tra alignment của địa chỉ đọc với target layout.

Không nên hiểu “có target layout” là “FFM biết allocator”:

- Target layout định nghĩa **hình dạng/kích thước** mà bạn tự khẳng định.
- Segment trả về vẫn gắn với **global scope** theo quy tắc đọc address, không tự kế thừa owner của target.
- Nếu pointer thực tế NULL, dangling, ngắn hơn layout, không aligned hoặc sai loại, target layout **không thể chứng minh bộ nhớ hợp lệ**.
- Nếu muốn scope gắn với một arena đã được chứng minh là owner/lifetime tương ứng, cân nhắc `reinterpret(..., arena, null)` theo chính sách sử dụng restricted methods.
- Đừng gọi target layout có 3 int nếu function trả pointer tới chỉ **1 int** hoặc buffer không đủ 12 byte.

Vì vậy, `withTargetLayout` hữu ích để mô tả kiểu pointer *khi contract rõ*, không phải cách tự động giải quyết vấn đề ownership/lifetime.

### 6.1. Khi nào dùng `withTargetLayout` thay vì `reinterpret`?

| Trường hợp | Gợi ý |
| --- | --- |
| C struct có field `int *ptr` biết chắc trỏ tới một `int` | `ADDRESS.withTargetLayout(JAVA_INT)` có thể diễn đạt hình dạng |
| Trả về mảng có độ dài runtime từ C (`pointer + length`) | Đọc pointer zero-length; xác minh `length`; `reinterpret(length * elementSize, ownerArena, null)` nếu hợp đồng lifetime phù hợp |
| Opaque handle không cho phép dereference | **Không** tạo target layout; giữ zero-length segment và truyền handle trở lại C |
| Pointer tới memory mà C sẽ thay hoặc free bất đồng bộ | Cần giao thức đồng bộ/lifetime; target layout không giải quyết được |
| Pointer-to-pointer | Mở từng lớp: layout pointer cho slot trung gian, sau đó đọc pointer cuối và xác định target |

### 6.2. Target layout và endian/alignment

Một pointer tới vùng dữ liệu không nói các byte đích là big-endian hay little-endian. Khi đọc native `int`, `ValueLayout.JAVA_INT` mặc định dùng native byte order. Nếu C API trả một buffer chứa network-order values, phải dùng layout `withOrder(BIG_ENDIAN)` đúng contract. Tương tự, C `struct` có padding/stride phải mô tả chính xác bằng `MemoryLayout`, không suy từ việc có `ADDRESS`.

## 7. Null pointer: `MemorySegment.NULL`, không phải Java `null`

Trong FFM JDK 22, `MemorySegment.NULL` là **zero-length native segment có `address() == 0L`**. Đây là biểu diễn một C NULL pointer.

```java
slot.set(ValueLayout.ADDRESS, 0L, MemorySegment.NULL);

MemorySegment pointer =
        slot.get(ValueLayout.ADDRESS, 0L);

boolean isNullPointer = pointer.address() == 0L;
```

Đây là fragment, `slot` hợp lệ. `pointer` là **Java object kiểu `MemorySegment`**, không phải `null` trong Java. So sánh `pointer == null` không phải cách kiểm tra con trỏ C NULL trong trường hợp này.

**Bắt buộc kiểm tra NULL trước khi dereference**:

```java
MemorySegment pointer =
        slot.get(ValueLayout.ADDRESS, 0L);

if (pointer.address() == 0L) {
    throw new IllegalStateException(
            "Native function returned a NULL pointer");
}

// Tiếp tục chỉ khi có đủ contract về size và lifetime.
// Không reinterpret tùy tiện một địa chỉ chưa biết.
```

Một pointer khác 0 **không bảo đảm** trỏ tới allocation còn sống. Nó có thể là dangling pointer, một địa chỉ không đọc được, một handle mờ (opaque handle) hoặc pointer chỉ hợp lệ trong một callback ngắn.

### 7.1. Pointer slot bằng NULL có phải vùng slot không tồn tại?

Không. `slot` vẫn là một allocation chứa bytes (ví dụ 8 byte). Nó chỉ đang lưu số 0 trong ô con trỏ. Ghi `MemorySegment.NULL` vào slot khác hoàn toàn với việc đóng arena chứa slot.

Trong C, `p = NULL` không tự giải phóng `malloc` cũ; nếu không còn reference tới allocation, có thể dẫn tới **memory leak**. Trong Java FFM, `slot.set(ADDRESS, 0, NULL)` cũng không tự free target.

## 8. Ownership và lifetime: slot còn sống không đồng nghĩa pointee còn sống

Đây là khác biệt quan trọng nhất sau khi hiểu hai mức địa chỉ. Có thể tồn tại **hai arena** hoặc hai allocator độc lập:

```text
Arena A (sở hữu pointer slot)       Arena B (sở hữu pointee)
        │                                   │
        ▼                                   ▼
     slot ------------------------------► data
        │                                   │
        │ vẫn alive                          │ đã close/free
        ▼                                   ▼
Có thể đọc pointer value            Vùng đích KHÔNG được truy cập
nhưng pointer đó có thể dangling.
```

Ví dụ tình huống khái niệm:

```java
// Fragment có hai arena độc lập, KHÔNG dereference sau close:
Arena slotArena = Arena.ofConfined();
Arena dataArena = Arena.ofConfined();

MemorySegment slot =
        slotArena.allocate(ValueLayout.ADDRESS);
MemorySegment data =
        dataArena.allocate(ValueLayout.JAVA_INT);

data.set(ValueLayout.JAVA_INT, 0L, 42);
slot.set(ValueLayout.ADDRESS, 0L, data);

dataArena.close();  // Pointee hết lifetime.

// slotArena vẫn còn mở; pointer value vẫn nằm trong slot.
// Tuyệt đối KHÔNG reinterpret và dereference pointer đã cũ.
MemorySegment dangling =
        slot.get(ValueLayout.ADDRESS, 0L);

slotArena.close();
```

Đây là **fragment chỉ minh họa nguy cơ**, không phải mẫu nên dùng trong sản phẩm. Biến `dangling` nhận một địa chỉ vật lý đã từng hợp lệ, không có nghĩa target còn sống. Để xử lý kiểu này trong thực tế, thiết kế owner và borrow duration rõ ràng; nếu owner đã free thì mọi dereference đều bị cấm.

### 8.1. Một segment có scope global không tự động giữ pointee sống

Pointer đọc bằng `get(ADDRESS, 0)` có global scope. Điều đó chỉ nói **wrapper address không bị đóng theo arena nào**. Nó không tạo GC root hay reference đến allocation của `Arena.ofConfined()` và không ngăn native library free vùng nhớ.

**Sai lầm phổ biến:** “`pointer.scope().isAlive()` là true, vậy pointer an toàn.” Khi wrapper có global scope, phép kiểm tra ấy không chứng minh memory đích tồn tại.

Với target do Java arena cấp phát, giữ reference tới arena/owner đúng và chỉ truy cập khi arena còn sống. Với pointer do C trả về, theo đúng tài liệu của C API về ownership, không suy từ kiểu trả về `MemorySegment`.

### 8.2. Owner, borrower và transfer ownership

Một thiết kế API nên nói rõ ai giải phóng:

| Tình huống | Ai sở hữu? | Java cần làm |
| --- | --- | --- |
| `arena.allocate(...)` | Arena đã cấp phát | Giữ trong lifetime arena; arena đóng và cleanup một lần |
| C trả pointer tới memory do thư viện tự quản | Native library | Dùng trong phạm vi thư viện cho phép; **không tự free** |
| C trả pointer từ `malloc` và yêu cầu caller gọi `free` | Caller theo contract | Gọi đúng deallocator (có thể là `free`), đúng thời điểm, một lần |
| C trả opaque handle | Native library quản lý cấu trúc ẩn | Chỉ truyền handle cho các API được công khai; **không dereference** |
| Java gửi pointer buffer cho native đọc tạm | Java arena/owner | Đảm bảo segment còn sống cho đến khi native hoàn tất |
| C hàm callback cung cấp pointer chỉ hợp lệ trong callback | Native callback lifetime | Copy dữ liệu nếu phải giữ về sau; không cache pointer vô thời hạn |

**Không suy “con trỏ trả về = Java sở hữu dữ liệu”.** Một field `T*` trong C struct thường chỉ biểu thị liên kết dữ liệu; quyền free phải được mô tả riêng.

### 8.3. Không double-free và không use-after-free

- Nếu `data` được cấp bởi `Arena.ofConfined()`, đừng gọi `free(data.address())` rồi lại để arena đóng và free lần nữa.
- Nếu C native function yêu cầu `library_free(handle)`, không thay bằng `free(handle)` nếu thư viện có allocator riêng.
- Khi chuyển từ raw pointer sang bounded view bằng `reinterpret`, **không có lệnh free ẩn**. Có thể đăng ký cleanup callback với arena theo API phù hợp, nhưng chỉ khi owner contract cấp quyền và tránh cùng lúc cleanup ở nơi khác.
- Đừng để native thread bất đồng bộ tiếp tục dùng target khi Java đã đóng arena; phải stop/drain/join hoặc có synchronization/ownership policy.

**Quyền sở hữu là một quy tắc của API, không thể suy ra đầy đủ từ địa chỉ, kích thước hay kiểu `MemorySegment`.**

## 9. Pointer-to-pointer: từ `int **` qua hai lần đọc địa chỉ

Khi C khai báo `int **pp`, dữ liệu theo hai cấp:

```text
ppSlot (chứa địa chỉ của pSlot)
      │
      ▼
pSlot (chứa địa chỉ của giá trị int)
      │
      ▼
int value = 7
```

Để đọc `**pp`, FFM phải đi qua **hai pointer values** và chỉ ở bước cuối mới đọc `int`. Nếu gọi `ppSlot.get(JAVA_INT, 0)`, bạn sẽ đọc bytes của địa chỉ, không phải giá trị `7`.

### 9.1. Ví dụ Java 22+ độc lập

Tệp **`PointerToPointerDemo.java`**:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class PointerToPointerDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment value = arena.allocate(
                    ValueLayout.JAVA_INT);
            value.set(ValueLayout.JAVA_INT, 0L, 7);

            MemorySegment pSlot = arena.allocate(
                    ValueLayout.ADDRESS);
            pSlot.set(ValueLayout.ADDRESS, 0L, value);

            MemorySegment ppSlot = arena.allocate(
                    ValueLayout.ADDRESS);
            ppSlot.set(ValueLayout.ADDRESS, 0L, pSlot);

            // *pp: đọc địa chỉ pSlot (trả zero-length).
            MemorySegment pSlotAddress =
                    ppSlot.get(ValueLayout.ADDRESS, 0L);

            // Cần biết pSlot thực sự rộng ADDRESS.byteSize().
            MemorySegment pSlotView = pSlotAddress.reinterpret(
                    ValueLayout.ADDRESS.byteSize(), arena, null);

            // *p: đọc tiếp địa chỉ value (trả zero-length).
            MemorySegment valueAddress =
                    pSlotView.get(ValueLayout.ADDRESS, 0L);

            // **pp: tạo view đúng sizeof(int), rồi đọc int.
            MemorySegment valueView = valueAddress.reinterpret(
                    ValueLayout.JAVA_INT.byteSize(), arena, null);

            System.out.println(
                    "**pp = " + valueView.get(
                            ValueLayout.JAVA_INT, 0L));
        }
    }
}
```

Lệnh với JDK 22+:

```bash
javac PointerToPointerDemo.java
java --enable-native-access=ALL-UNNAMED PointerToPointerDemo
```

Stdout:

```text
**pp = 7
```

**Điều kiện an toàn của demo:** mỗi allocation được tạo bởi **cùng arena**, có kích thước/alignment biết chắc, vẫn sống trong toàn bộ quá trình truy cập. Trong chương trình thực, nếu pointer của một cấp đến từ native library hoặc từ file bytes, bạn **không được mặc định** mở rộng view mà chưa xác minh hợp đồng vùng đích.

### 9.2. Pointer arrays và element index

Nếu một segment lưu **một dãy con trỏ**, thì:

```java
// Fragment: pointerArray chứa n native pointer slots liên tiếp.
MemorySegment ptr = pointerArray.getAtIndex(
        ValueLayout.ADDRESS, index);
```

`index` là chỉ số **pointer slot**, được nhân với `ValueLayout.ADDRESS.byteSize()` (4 hoặc 8 byte tùy platform). Nó **không phải** chỉ số phần tử `int` trong pointee. Muốn truy cập phần tử `int` thứ `j` của mảng do pointer đó trỏ tới, phải có bounded target view phù hợp, sau đó mới gọi `targetView.getAtIndex(JAVA_INT, j)`.

## 10. Pointer được thay đổi trong slot không làm các view cũ tự đổi đích

Giả sử:

```java
// Fragment: cả dataA/dataB/slot đều là allocations hợp lệ.
slot.set(ValueLayout.ADDRESS, 0L, dataA);
MemorySegment oldPointer =
        slot.get(ValueLayout.ADDRESS, 0L);

slot.set(ValueLayout.ADDRESS, 0L, dataB);
MemorySegment newPointer =
        slot.get(ValueLayout.ADDRESS, 0L);
```

`oldPointer.address()` vẫn là địa chỉ **dataA** đã đọc ở thời điểm trước; `newPointer.address()` là địa chỉ **dataB** sau khi thay. Hai đối tượng view **không** phải một con trỏ có khả năng “tự theo dõi” các thay đổi tương lai của slot.

Đây là lý do nên phân biệt:

- **Pointer slot:** vị trí có thể bị ghi đè bằng địa chỉ khác.
- **Snapshot pointer value:** giá trị địa chỉ đã được đọc ở một thời điểm.
- **Target view:** vùng nhớ mà snapshot pointer được diễn giải trỏ tới, có điều kiện lifetime riêng.

Nếu C native thread thay slot từ xa trong lúc Java đọc, còn xuất hiện bài toán **data race và synchronization**; việc dùng `MemorySegment` không thay thế lock, volatile/atomic protocol hoặc ràng buộc thread của native library.

## 11. Opaque handles: có địa chỉ nhưng không được dereference

Nhiều C API không trả con trỏ tới một cấu trúc công khai mà trả `void *handle` hoặc `struct Engine *` có định nghĩa private. Java có thể biểu diễn handle như một `MemorySegment` có địa chỉ, truyền lại cho downcall, nhưng **không nên `reinterpret` rồi đọc ngẫu nhiên field**.

Ví dụ hợp đồng C:

```c
/* Fragment API C, chưa có implementation. */
typedef struct Engine Engine;

Engine *engine_create(void);
void engine_run(Engine *engine);
void engine_destroy(Engine *engine);
```

`Engine *` là opaque handle. Java FFM có thể lưu pointer từ `engine_create` dưới dạng segment không có bounds đích, dùng làm tham số cho `engine_run`, rồi gọi `engine_destroy` đúng một lần theo contract.

**Không thể suy ra** rằng `Engine` có field ở offset 0 hoặc có kích thước 64 byte chỉ từ giá trị handle. `withTargetLayout` hoặc `reinterpret` không biến private C struct thành layout hợp lệ. Hãy để native library sở hữu và truy cập dữ liệu ẩn.

### 11.1. C pointer value không phải Java object reference

`MemorySegment` chứa raw native address **không phải** `jobject` JNI handle, và không phải một Java heap object. Trong JNI, `jobject` do JVM quản lý và có quy tắc local/global references, GC; không được ép bừa địa chỉ `MemorySegment` thành `jobject` hoặc ngược lại.

- Java heap array có thể bị GC di chuyển.
- `MemorySegment.ofArray(byte[])` không đại diện cho một địa chỉ C cố định có thể đưa qua `ADDRESS` như native pointer.
- `MemorySegment` từ `Arena.allocate` trỏ tới native memory thực; vẫn cần hợp đồng lifetime, alignment và ownership.
- Nếu cần chuyển Java array xuống C, sử dụng đúng phương thức JNI hoặc FFM marshalling/copy/pinning được hỗ trợ, không lấy “địa chỉ” heap segment rồi cast thành C pointer.

## 12. Trường hợp dễ nhầm với `asSlice` và `copyFrom`

### 12.1. `asSlice` không tự dereference pointer

`slot.asSlice(0L, ValueLayout.ADDRESS.byteSize())` tạo một **view của bytes lưu pointer trong slot**. Nó không đi đến vùng đích. Địa chỉ slice vẫn nằm trong allocation slot.

Ngược lại:

```java
MemorySegment rawPointer =
        slot.get(ValueLayout.ADDRESS, 0L);
```

trả về một wrapper có địa chỉ bằng **giá trị con trỏ đã lưu**, dù wrapper đó zero-length. Chỉ khi đã có bounded view tới pointee thì `asSlice` trên pointee mới cắt dữ liệu thật ở target.

### 12.2. `copyFrom` có thể copy bytes của slot, không copy pointee

Nếu copy:

```java
// Fragment: bothSlots đủ ADDRESS.byteSize() bytes và hợp lệ.
anotherSlot.copyFrom(slot);
```

thì bạn sao chép **bytes của giá trị pointer** sang một slot khác. Kết quả là hai slot cùng lưu một địa chỉ target. Không có việc clone dữ liệu ở pointee; không có cấp phát mới cho target, cũng không có shared ownership/reference counting tự động.

Sao chép pointer bytes cũng có nguy cơ double-free nếu code sau đó đối xử hai slot như hai owner độc lập của một allocation. Đây là lỗi ownership, không phải lỗi của `copyFrom`.

## 13. Bảng tình huống: đúng / sai và vì sao

| Ý định | Cách sai hoặc chưa đủ | Cách đúng / điều kiện |
| --- | --- | --- |
| Đọc địa chỉ được lưu trong slot | `slot.address()` | `slot.get(ADDRESS, 0).address()` |
| Lấy địa chỉ vật lý của slot | `slot.get(ADDRESS, 0).address()` | `slot.address()` nếu slot là native segment |
| Đọc `int` ở pointee | `slot.get(JAVA_INT, 0)` | `data.get(JAVA_INT, 0)`, hoặc bounded target view đã được xác minh |
| Ghi pointer vào slot | `slot.copyFrom(data)` | `slot.set(ADDRESS, 0, data)` |
| Ghi giá trị 123 vào pointee | `slot.set(JAVA_INT, 0, 123)` | `data.set(JAVA_INT, 0, 123)` hoặc target view hợp lệ |
| Đọc một `int *` qua ADDRESS | Mong có view 4 byte tự động | Nhận zero-length view; `reinterpret` hoặc target layout theo contract |
| Kiểm tra NULL pointer | `pointer == null` | `pointer.address() == 0L` |
| Giải phóng vùng đích | Đóng arena chứa riêng slot | Đóng đúng owner của data hoặc gọi deallocator chính thức |
| Con trỏ từ native library | `reinterpret(Long.MAX_VALUE)` không xác minh | Lấy size và lifetime từ API, bound hợp lý, kiểm soát ownership |
| Pointer tới opaque handle | Đoán field offset và đọc | Chỉ truyền lại cho API native quản lý handle |
| Pointer-to-pointer | Đọc `JAVA_INT` tại offset 0 của outer slot | Đọc từng address level, tạo views đúng size rồi đọc dữ liệu |

## 14. Những ngoại lệ có thể thấy, và những trường hợp nguy hiểm không có ngoại lệ

| Trường hợp | Điều thường xảy ra |
| --- | --- |
| `pointer.get(JAVA_INT, 0)` với pointer view size 0 | `IndexOutOfBoundsException` |
| `slot.get(ADDRESS, offset)` vượt phạm vi slot | `IndexOutOfBoundsException` |
| `slot.get(ADDRESS, 0)` với slot đã đóng arena | `IllegalStateException` |
| Dùng confined slot từ thread không sở hữu | `WrongThreadException` |
| `slot.set(ADDRESS, 0, data)` với `data` là heap segment không dùng được làm native pointer | `IllegalArgumentException` theo contract của address access |
| Đọc/writing layout có căn chỉnh không tương thích | `IllegalArgumentException` |
| Gọi restricted `reinterpret` / `withTargetLayout` không bật native access | `IllegalCallerException` trên JDK có enforced restriction |
| Gán view có kích thước quá lớn rồi đọc ra ngoài vùng C cấp phát thực tế | Có thể **segfault, JVM crash hoặc silent memory corruption** |
| Dereference dangling pointer sau khi native đã free vùng nhớ | Có thể **crash hoặc corrupt memory**, không mong một Java exception an toàn |
| Dereference pointer NULL sau khi tự reinterpret thành size >0 | Hành vi nguy hiểm; phải check NULL trước |

Các kiểm tra bounds của segment **chỉ dựa trên giới hạn đã biết hoặc được khai báo**. Nếu bạn tự đưa ra giới hạn sai bằng restricted API, Java không thể xác minh physical allocation bên ngoài thật sự rộng bao nhiêu.

### 14.1. Không đọc pointer từ dữ liệu không tin cậy như địa chỉ process

Bốn hoặc tám byte bất kỳ trong file, network packet hay untrusted memory **không** tự trở thành một con trỏ hợp lệ của tiến trình. Đừng nhận một số nguyên từ dữ liệu không tin cậy, tạo `MemorySegment.ofAddress(number)`, sau đó `reinterpret` và dereference. `ofAddress` tạo zero-length wrapper **chứ không kiểm chứng** địa chỉ có thể đọc, có ownership hay nằm trong address space thích hợp.

Các file format thường nên lưu **offset tương đối** hoặc **ID**, không lưu raw process pointers. Raw pointers chỉ có nghĩa trong không gian địa chỉ tiến trình và trong khoảng lifetime xác định.

## 15. Quy trình an toàn khi làm việc với pointer trả về từ native API

1. **Xác định kiểu dữ liệu:** đây là pointer slot, pointer value, array-of-pointers, struct field `T *` hay opaque handle?
2. **Xác nhận owner:** allocation do Java arena hay C allocator tạo; ai được phép free; free bằng API nào?
3. **Xác nhận lifetime:** pointer còn hợp lệ đến khi callback kết thúc, đến khi gọi `release`, hay đến khi đóng arena?
4. **Xác nhận kích thước:** nếu là buffer, size đến từ tham số riêng hoặc layout rõ ràng; kiểm tra `0 <= size`, overflow và giới hạn ứng dụng.
5. **Xác nhận NULL:** nếu `pointer.address() == 0L`, dừng và xử lý theo API contract.
6. **Xác nhận alignment, byte order, stride:** biết chính xác kiểu C/ABI, không áp bừa `JAVA_INT` lên struct chưa xác minh.
7. **Chọn cách tạo view:** dùng original bounded segment khi có thể; nếu chỉ có pointer raw thì restricted `reinterpret`/target layout cần size và temporal contract đúng.
8. **Giữ owner trong suốt thời gian dùng:** không để native free đột ngột, không đóng arena giữa lúc có callback hoặc worker.
9. **Cleanup đúng một lần:** xóa handle, close arena hoặc gọi deallocator, nhưng không trộn allocator; không xem việc set pointer NULL là free.
10. **Chỉ chuyển pointer across threads khi hợp đồng cho phép:** đồng bộ hóa native writes và tôn trọng confined segments.

Một API chất lượng nên cung cấp thay vì raw pointer trần:

- `Pointer + length` cho mảng động.
- `Pointer + release function` cho vùng nhớ do C cấp phát và chuyển ownership.
- `Opaque handle + native methods` khi layout nội bộ không công khai.
- `Arena + MemorySegment` khi Java là chủ cấp phát và nắm lifetime.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `slot.address()` và `slot.get(ADDRESS, 0).address()` khác nhau thế nào?  
**Đáp án:** Cái đầu là địa chỉ vùng lưu biến con trỏ; cái sau là giá trị pointer lưu trong vùng ấy, tức địa chỉ target (nếu giá trị hợp lệ).

**Câu 2.** Tại sao `slot.get(ADDRESS, 0)` thường có `byteSize() == 0`?  
**Đáp án:** JVM chỉ đọc được giá trị địa chỉ, không biết target rộng bao nhiêu. Zero-length segment ngăn dereference ngầm; muốn đọc phải tạo view có bounds đáng tin.

**Câu 3.** `slot.set(ADDRESS, 0, data)` có sao chép các giá trị `int` của `data` vào slot không?  
**Đáp án:** Không. Nó ghi **địa chỉ của data** vào slot, không sao chép nội dung hay chuyển ownership.

**Câu 4.** Đã gọi `addressValue.reinterpret(12)` thì JVM có chắc allocation target dài ít nhất 12 byte không?  
**Đáp án:** Không. `reinterpret` là restricted method khai báo bounds theo giả định của người gọi; sai giả định có thể gây crash/corruption.

**Câu 5.** Nếu `slot` do Arena A quản lý, còn `data` do Arena B quản lý, đóng Arena B có làm pointer value trong slot biến thành NULL không?  
**Đáp án:** Không. Giá trị pointer có thể vẫn nằm trong slot, nhưng đó là **dangling pointer**. Không dereference nữa.

**Câu 6.** `MemorySegment.NULL` có phải Java reference `null` không?  
**Đáp án:** Không. Nó là một native segment wrapper với `address()==0L`, mô hình hóa C NULL pointer.

**Câu 7.** `withTargetLayout(MemoryLayout.sequenceLayout(3, JAVA_INT))` có tự quản lý free buffer 12 byte không?  
**Đáp án:** Không. Nó chỉ cho biết target size/layout để tạo view; ownership và lifetime vẫn phải xác minh riêng.

**Câu 8.** Một C function trả `void *handle` đến struct private. Có nên `reinterpret(64)` rồi đọc field đầu?  
**Đáp án:** Không. Opaque handle không có public layout để dereference; chỉ truyền cho API native phù hợp.

**Câu 9.** Trong `int **pp`, để đến số nguyên phải đọc bao nhiêu cấp address?  
**Đáp án:** Hai cấp pointer: đọc từ outer slot để tìm pointer slot trung gian, rồi đọc pointer từ trung gian để tìm vùng chứa `int`.

**Câu 10.** Sao chép bytes từ slot A sang slot B có tạo một bản sao vùng target không?  
**Đáp án:** Không. Hai slot có thể lưu cùng địa chỉ target; copy pointer bytes không copy pointee, không tạo hai owner độc lập.

**Câu 11.** Vùng target đã free nhưng wrapper pointer vẫn có global scope. `pointer.scope().isAlive()` có chứng minh dereference an toàn không?  
**Đáp án:** Không. Global scope của wrapper không kiểm soát lifetime của allocation bên ngoài.

## 17. Tóm tắt trọng tâm

- **Pointer slot** là vùng nhớ lưu giá trị địa chỉ; **pointee** là vùng dữ liệu được chỉ tới. Hai vùng có thể nằm ở hai địa chỉ, hai allocator và hai lifetime khác nhau.
- `slot.address()` = địa chỉ **của slot**; `slot.get(ADDRESS, 0).address()` = địa chỉ **đọc từ slot**.
- `slot.get(ADDRESS, 0)` thông thường trả zero-length segment, không tự cung cấp bounds/owner của pointee.
- `reinterpret` và `AddressLayout.withTargetLayout` là **restricted/unsafe operations** cần kích thước, alignment và lifetime đúng; chúng **không cấp phát**, **không copy** và **không tự free** vùng dữ liệu đích.
- `slot.set(ADDRESS, 0, data)` ghi **pointer value**, không ghi nội dung data. `slot.set(ADDRESS, 0, NULL)` chỉ xóa giá trị con trỏ, không free pointee.
- Một **opaque handle** chỉ được truyền qua các API của owner, không tự reinterpret để đọc layout private.
- Pointer đã đọc mang giá trị **tại thời điểm đọc**, không tự theo dõi mọi lần ghi lại slot.
- Khi tạo bounded target view, luôn **check NULL, size, ownership, lifetime, thread confinement và allocator** trước khi dereference.

### Tài liệu chuẩn

- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): zero-length segments khi đọc địa chỉ, `get(AddressLayout, offset)`, `set(AddressLayout, offset, value)`, `reinterpret` và phạm vi sống.
- [Oracle Java SE 22 — AddressLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/AddressLayout.html): kích thước/alignment pointer phụ thuộc platform, `withTargetLayout` là restricted method.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): allocator, confined scope, thời điểm đóng arena và tài nguyên được sở hữu.
- [Oracle Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): target/struct/sequence layouts và các đường truy cập giá trị.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): JDK 22 final FFM API, restricted operations và điều kiện tương tác native.
