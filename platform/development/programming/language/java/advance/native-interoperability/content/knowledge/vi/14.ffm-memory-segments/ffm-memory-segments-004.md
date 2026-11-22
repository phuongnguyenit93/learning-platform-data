# Phân biệt offset theo byte với chỉ số phần tử trong getAtIndex và setAtIndex của MemorySegment

## 1. Bài toán: một con số có thể là byte offset hoặc element index

Khi thao tác với bộ nhớ qua **Foreign Function & Memory API (FFM API)**, `MemorySegment` biểu diễn **một vùng bộ nhớ liên tiếp có kích thước đo bằng byte**. Bạn có thể truy cập vùng ấy bằng layout mô tả kiểu dữ liệu, độ rộng, thứ tự byte và yêu cầu căn chỉnh. Hai nhóm phương thức nhìn khá giống nhau nhưng **đơn vị của tham số vị trí khác nhau**:

- `segment.get(layout, offset)` và `segment.set(layout, offset, value)`: `offset` là **số byte** tính từ đầu **segment hiện tại**.
- `segment.getAtIndex(layout, index)` và `segment.setAtIndex(layout, index, value)`: `index` là **chỉ số phần tử logic**. JVM nhân chỉ số này với `layout.byteSize()` để suy ra vị trí byte.

Đây là nguồn gốc phổ biến của lỗi “đọc sai phần tử” hoặc “lệch dữ liệu” khi mã Java sử dụng vùng nhớ native.

**Công thức cốt lõi:**

```text
byteOffset = index × layout.byteSize()

segment.getAtIndex(layout, index)
    tương ứng về vị trí với:
segment.get(layout, byteOffset)

segment.setAtIndex(layout, index, value)
    tương ứng về vị trí với:
segment.set(layout, byteOffset, value)
```

Tính tương ứng chỉ có ý nghĩa khi cả hai phép truy cập đều hợp lệ theo **kích thước, căn chỉnh (alignment), phạm vi sống (lifetime) và quyền truy cập** của segment. Không phải một phép nhân tùy ý sẽ bỏ qua các ràng buộc an toàn của API.

Ví dụ với `ValueLayout.JAVA_INT` (một giá trị Java `int` rộng **4 byte**):

```text
             byte offset trong segment
              0         4         8        12        16
              │         │         │         │         │
              ▼         ▼         ▼         ▼         │
            ┌─────────┬─────────┬─────────┬─────────┐  │
            │ int[0]  │ int[1]  │ int[2]  │ int[3]  │  │
            │ 10      │ 20      │ 30      │ 40      │  │
            └─────────┴─────────┴─────────┴─────────┘  │
            index 0   index 1   index 2   index 3       │
                                                        │
                                             byte 16 = hết vùng
```

Trong vùng 16 byte này:

- `getAtIndex(JAVA_INT, 2)` đọc `int[2]` ở **byte offset 8**, trả `30`.
- `get(JAVA_INT, 8)` cũng đọc phần tử đó, trả `30`.
- `get(JAVA_INT, 2)` **không có nghĩa** là phần tử thứ 2: đó là truy cập `int` tại **byte offset 2**, có thể vi phạm căn chỉnh 4 byte và ném ngoại lệ.
- `getAtIndex(JAVA_INT, 8)` cố đọc ở **byte offset 32**; với segment 16 byte sẽ vượt giới hạn.

Điểm mấu chốt: cùng số `2` hoặc `8`, nhưng **đơn vị mà API hiểu** quyết định vùng bộ nhớ được truy cập.

> **Phiên bản API:** Ví dụ trong bài dùng `java.lang.foreign.MemorySegment`, `Arena` và `ValueLayout` của **JDK 22 trở lên**, khi FFM API đã trở thành API chính thức. JDK 21 dùng preview API; các bản JDK 17–19 có API incubator/preview khác package hoặc cách gọi. Không copy nguyên ví dụ vào Java 17 rồi mong biên dịch mà không sửa API. Bài ưu tiên mã thực thi ổn định trên JDK 22+ thay vì gượng ép dùng API cũ.

## 2. Hai hệ tọa độ: byte offset và logical element index

### 2.1. Byte offset: đo khoảng cách bằng byte

Một `MemorySegment` có `byteSize()`, ví dụ `16L`. Khi gọi:

```java
int value = segment.get(ValueLayout.JAVA_INT, 8L);
```

JVM hiểu:

1. Bắt đầu từ vị trí đầu segment.
2. Di chuyển **8 byte**.
3. Đọc **4 byte** theo kiểu, byte order và alignment của `ValueLayout.JAVA_INT`.
4. Trả về một Java `int`.

Tương tự:

```java
segment.set(ValueLayout.JAVA_INT, 12L, 44);
```

ghi một `int` vào **byte 12..15** của segment. Không có phép nhân ngầm với `4` đối với tham số `12L`.

Cần phân biệt **vị trí bắt đầu** và **độ rộng dữ liệu**: `offset = 12`, `layout.byteSize() = 4` nghĩa là vùng đọc/ghi trải từ byte 12 đến trước byte 16; bản thân offset không phải độ dài được truy cập.

### 2.2. Element index: đếm theo độ rộng của ValueLayout

Khi gọi:

```java
int value = segment.getAtIndex(ValueLayout.JAVA_INT, 2L);
```

JVM hiểu:

```text
layout.byteSize() = 4
index             = 2
byte offset       = 2 × 4 = 8
```

Kết quả giống `get(JAVA_INT, 8L)` trong cùng trạng thái bộ nhớ. Tương tự, `setAtIndex(JAVA_INT, 3L, 44)` ghi vào byte offset `12L`.

**Không nhân chỉ số thủ công rồi truyền vào `getAtIndex`:**

```java
long index = 2L;
long byteOffset = Math.multiplyExact(
        index, ValueLayout.JAVA_INT.byteSize());

// ĐÚNG: tham số là index (2), JVM tự nhân 4.
int a = segment.getAtIndex(ValueLayout.JAVA_INT, index);

// ĐÚNG: tham số là offset đã tính bằng byte (8).
int b = segment.get(ValueLayout.JAVA_INT, byteOffset);

// SAI Ý ĐỊNH: 8 được hiểu là index, JVM nhân 4 thêm lần nữa.
// int wrong = segment.getAtIndex(ValueLayout.JAVA_INT, byteOffset);
```

Đây là **fragment minh họa**, `segment` là một `MemorySegment` đủ lớn, còn sống và có alignment phù hợp; chương trình đầy đủ xuất hiện ở phần 5.

### 2.3. Tại sao layout nằm trong phép tính?

`getAtIndex` không có một “element size” cố định của segment. Cùng segment có thể được nhìn qua nhiều layout khác nhau:

| Layout | `layout.byteSize()` | `getAtIndex(layout, 3)` đọc tại byte offset |
| --- | ---: | ---: |
| `ValueLayout.JAVA_BYTE` | 1 | 3 |
| `ValueLayout.JAVA_SHORT` | 2 | 6 |
| `ValueLayout.JAVA_INT` | 4 | 12 |
| `ValueLayout.JAVA_FLOAT` | 4 | 12 |
| `ValueLayout.JAVA_LONG` | 8 | 24 |
| `ValueLayout.JAVA_DOUBLE` | 8 | 24 |

Các `byteSize()` trên là giá trị của **Java primitive layouts**. Đối với `ValueLayout.ADDRESS`, độ rộng địa chỉ có thể phụ thuộc ABI/platform; không suy đoán luôn bằng 8 byte. Nếu dùng layout được tùy chỉnh bằng `withOrder` hoặc `withByteAlignment`, **độ rộng vẫn phải lấy từ `layout.byteSize()`** thay vì hard-code.

Một segment chỉ là vùng byte; nó **không tự biết** bạn định biểu diễn `int[]`, `short[]`, cấu trúc C hay dãy pixel. Layout chính là hợp đồng diễn giải bytes đó.

## 3. Bảng so sánh API và các tình huống tương đương

| Tác vụ | API theo byte | API theo phần tử |
| --- | --- | --- |
| Đọc int thứ 0 | `get(JAVA_INT, 0)` | `getAtIndex(JAVA_INT, 0)` |
| Đọc int thứ 1 | `get(JAVA_INT, 4)` | `getAtIndex(JAVA_INT, 1)` |
| Đọc int thứ 2 | `get(JAVA_INT, 8)` | `getAtIndex(JAVA_INT, 2)` |
| Ghi int thứ 3 = 44 | `set(JAVA_INT, 12, 44)` | `setAtIndex(JAVA_INT, 3, 44)` |
| Đọc long thứ 2 | `get(JAVA_LONG, 16)` | `getAtIndex(JAVA_LONG, 2)` |
| Ghi byte thứ 3 | `set(JAVA_BYTE, 3, value)` | `setAtIndex(JAVA_BYTE, 3, value)` |

Tên đầy đủ của các API thuộc `MemorySegment`:

```java
// Ví dụ các overload cho Java int.
int get(ValueLayout.OfInt layout, long offset);
void set(ValueLayout.OfInt layout, long offset, int value);

int getAtIndex(ValueLayout.OfInt layout, long index);
void setAtIndex(ValueLayout.OfInt layout, long index, int value);
```

Bốn dòng trên là **chữ ký để đọc hiểu API**, không phải khai báo có thể đặt trong chương trình Java của bạn (chúng là phương thức đã có trên `MemorySegment`). `getAtIndex`/`setAtIndex` có overload tương tự cho `byte`, `short`, `char`, `long`, `float`, `double`, `boolean` và address layout.

**Một bẫy dễ mắc:** `getAtIndex(layout, index)` không nhận tham số base byte offset. Khi có một header ở đầu segment, phải tạo slice từ vị trí header kết thúc, hoặc tự tính byte offset chính xác và gọi `get`/`set`. Không dùng `index + headerBytes` rồi hy vọng API hiểu header ở đơn vị byte.

## 4. Cách chọn API nhanh

**Dùng `getAtIndex`/`setAtIndex` khi** dữ liệu là một dãy các phần tử có kích thước bằng nhau, liên tục, được mô tả bởi **cùng một `ValueLayout`**:

```java
for (long index = 0; index < count; index++) {
    segment.setAtIndex(ValueLayout.JAVA_INT, index, (int)index);
}
```

Ở đây `count` là **số int**, không phải số byte. Nếu segment có `count * JAVA_INT.byteSize()` bytes và alignment thích hợp, mỗi lần lặp truy cập đúng một phần tử.

**Dùng `get`/`set` theo byte khi** vị trí đến từ:

- Offset field trong một struct C hoặc file format.
- Một header length hoặc offset tính bằng byte từ giao thức.
- Vị trí của một phần tử trong record có **stride khác** `layout.byteSize()`.
- Cần truy cập vùng nhớ không đồng nhất gồm các field `byte`, `int`, `long` xen kẽ.
- Một slice có vị trí bắt đầu xác định bằng byte.

Ví dụ: trong một record dài 12 byte, field `int score` nằm ở byte offset 8 của mỗi record. Score của record thứ 3 (index 2) ở byte offset `2 * 12 + 8 = 32`. Gọi `getAtIndex(JAVA_INT, 2)` sẽ đọc offset `8` — **không phải** byte 32. Phần 8 sẽ phân tích struct và stride chi tiết.

## 5. Ví dụ Java 22+ chạy được: cùng dữ liệu, hai cách định vị

Chương trình sau tạo một **native segment 16 byte**, lưu 4 số `int` liên tiếp, rồi chứng minh cách đọc/ghi theo index và byte offset. Ví dụ tự cấp phát bộ nhớ, không cần JNI C hay thư viện ngoài.

### 5.1. Tệp `ByteOffsetVsIndex.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ByteOffsetVsIndex {
    public static void main(String[] args) {
        var intLayout = ValueLayout.JAVA_INT;
        long elementBytes = intLayout.byteSize(); // 4 bytes
        int count = 4;

        try (Arena arena = Arena.ofConfined()) {
            // 4 phần tử int = 16 byte; yêu cầu alignment phù hợp.
            MemorySegment segment = arena.allocate(
                    Math.multiplyExact((long) count, elementBytes),
                    intLayout.byteAlignment());

            for (int i = 0; i < count; i++) {
                segment.setAtIndex(intLayout, i, (i + 1) * 10);
            }

            System.out.println("element bytes: " + elementBytes);
            System.out.println("segment bytes: " + segment.byteSize());

            // Hai đường truy cập cùng phần tử int[1].
            System.out.println(
                    "index 1: " + segment.getAtIndex(intLayout, 1));
            System.out.println(
                    "byte 4: " + segment.get(intLayout, 4));

            // Hai đường truy cập cùng phần tử int[2].
            System.out.println(
                    "index 2: " + segment.getAtIndex(intLayout, 2));
            System.out.println(
                    "byte 8: " + segment.get(intLayout, 8));

            // setAtIndex tự nhân index=2 với 4 byte.
            segment.setAtIndex(intLayout, 2, 99);
            System.out.println(
                    "after setAtIndex(2): " + segment.get(intLayout, 8));

            // set nhận vị trí byte, không nhận logical index.
            segment.set(intLayout, 12, 44);
            System.out.println(
                    "after set(byte 12): " +
                    segment.getAtIndex(intLayout, 3));

            // Slice có hệ tọa độ riêng, bắt đầu từ byte 4.
            MemorySegment slice = segment.asSlice(4, 8);
            System.out.println(
                    "slice index 0: " + slice.getAtIndex(intLayout, 0));
            System.out.println(
                    "slice index 1: " + slice.getAtIndex(intLayout, 1));

            // 16 byte chỉ đủ 4 int (index 0..3).
            try {
                segment.getAtIndex(intLayout, 4);
            } catch (IndexOutOfBoundsException ex) {
                System.out.println("index 4: out of bounds");
            }

            // Native segment được cấp phát căn hàng 4 byte;
            // offset 3 không đáp ứng alignment 4 byte.
            try {
                segment.get(intLayout, 3);
            } catch (IllegalArgumentException ex) {
                System.out.println("byte 3: misaligned");
            }
        }
    }
}
```

**Tệp này là chương trình Java độc lập.** `Arena.ofConfined()` chỉ cho phép thread sở hữu arena truy cập segment; toàn bộ chương trình sử dụng trong một thread. `try-with-resources` đóng arena khi thoát block, giải phóng native memory.

Lệnh với **JDK 22 hoặc mới hơn**:

```bash
javac ByteOffsetVsIndex.java
java ByteOffsetVsIndex
```

Không cần `--enable-preview` đối với FFM API chính thức từ JDK 22. Các thao tác thuần `MemorySegment`/`Arena`/`ValueLayout` ở ví dụ này cũng không cần gọi restricted native linker hoặc nạp thư viện JNI.

**Stdout dự kiến:**

```text
element bytes: 4
segment bytes: 16
index 1: 20
byte 4: 20
index 2: 30
byte 8: 30
after setAtIndex(2): 99
after set(byte 12): 44
slice index 0: 20
slice index 1: 99
index 4: out of bounds
byte 3: misaligned
```

### 5.2. Giải thích kết quả

- `intLayout.byteSize()` trả `4`, `segment.byteSize()` trả `16`.
- `getAtIndex(intLayout, 1)` → byte offset `4`. Cùng kết quả với `get(intLayout, 4)`.
- `getAtIndex(intLayout, 2)` → byte offset `8`. Cùng kết quả với `get(intLayout, 8)`.
- `setAtIndex(intLayout, 2, 99)` ghi vào byte 8..11; `get(intLayout, 8)` đọc lại `99`.
- `set(intLayout, 12, 44)` ghi vào byte 12..15; `getAtIndex(intLayout, 3)` đọc lại `44`.
- `asSlice(4, 8)` tạo góc nhìn 8 byte bắt đầu từ byte offset 4 của segment gốc. Trong slice, **index 0** là int thứ 1 của segment gốc (`20`), còn **index 1** là int thứ 2 sau khi sửa (`99`).
- `getAtIndex(intLayout, 4)` tương ứng byte offset 16 và cần thêm 4 byte để đọc; vùng 16 byte không đủ, nên có `IndexOutOfBoundsException`.
- `get(intLayout, 3)` nằm trong bounds nếu chỉ xét 3+4 ≤ 16, nhưng **không căn hàng đúng** cho `JAVA_INT` ở offset 3; truy cập bị từ chối với `IllegalArgumentException`.

Ví dụ dùng `JAVA_INT` để tránh phụ thuộc endian trong stdout: giá trị được **ghi rồi đọc lại bằng chính layout ấy**. Nếu thay layout byte order giữa bước ghi và đọc, giá trị có thể khác (phần 10).

## 6. Kiểm tra giới hạn: byteSize không phải số lượng phần tử

`segment.byteSize()` trả về số **byte**, không phải số `int`, `long` hoặc số record trong segment.

Nếu một segment chứa **N** phần tử đồng đều, mỗi phần tử rộng **S** byte, tổng dung lượng tối thiểu là:

```text
requiredBytes = N × S
validIndices  = 0, 1, 2, ..., N - 1
elementOffset = index × S
```

Với `JAVA_INT` 4 byte và `segment.byteSize() == 16`, chỉ có **4 phần tử nguyên vẹn**, index hợp lệ `0..3`.

Nếu segment 18 byte và mỗi phần tử 4 byte, segment có thể chứa **4 phần tử nguyên vẹn**, dư 2 byte. Không làm tròn lên thành 5 phần tử để đọc/ghi `int` thứ 5.

### 6.1. Điều kiện truy cập theo byte

Đối với `get(layout, offset)` hoặc `set(layout, offset, value)`, khi `layout.byteSize() = S` và `segment.byteSize() = B`, phải thỏa:

```text
0 <= offset
offset + S <= B
```

Nói cách khác, một access bắt đầu ở offset `B - S` là **điểm cuối có thể** đọc/ghi phần tử rộng `S` bytes. Trong phép kiểm tra thủ công, dùng `offset <= B - S` sau khi chắc chắn các số không âm để tránh overflow ở phép cộng.

Nếu dùng `getAtIndex(layout, index)`:

```text
0 <= index
index * S + S <= B
```

API kiểm tra phép nhân và giới hạn. Với `index * S` bị overflow kiểu `long`, javadoc quy định `IndexOutOfBoundsException` chứ không cho phép wrap thành địa chỉ không an toàn.

### 6.2. Một helper chuyển đổi index thành byte offset

Khi code cần chuyển đơn vị để phối hợp với field offset hoặc protocol, hãy cho phép bắt lỗi nhân tràn:

```java
static long toByteOffset(long index, long elementBytes) {
    if (index < 0 || elementBytes <= 0) {
        throw new IllegalArgumentException(
                "index must be non-negative and size positive");
    }
    return Math.multiplyExact(index, elementBytes);
}
```

Đây là **fragment phương thức static** (không phải chương trình độc lập). `Math.multiplyExact` ném `ArithmeticException` nếu kết quả vượt giới hạn `long`; sau khi tính vẫn phải kiểm tra có đủ bytes từ offset đến cuối segment. `getAtIndex` tự có kiểm tra overflow/bounds nhưng **không thay thế** logic validate số phần tử/record của ứng dụng.

Có thể lấy số phần tử **nguyên vẹn** bằng:

```java
long wholeElements = segment.byteSize() / intLayout.byteSize();
```

Câu lệnh trên giả định `segment` và `intLayout` đã khai báo. Khi dữ liệu có header, padding hoặc stride khác `layout.byteSize()`, phép chia chỉ là phép đếm lý thuyết theo layout, **không tự động chứng minh đó là số record nghiệp vụ**.

## 7. Alignment: chỉ số đúng chưa đủ để truy cập được

**Căn chỉnh (alignment)** là ràng buộc về địa chỉ bắt đầu của vùng đọc/ghi, đo bằng byte, không phải số phần tử. `ValueLayout.JAVA_INT` có:

```text
byteSize()      = 4
byteAlignment() = 4
```

Với một native memory segment có địa chỉ đầu căn hàng 4 byte:

- `get(JAVA_INT, 0)` hợp lệ về căn chỉnh.
- `get(JAVA_INT, 4)`, `get(JAVA_INT, 8)` cũng hợp lệ.
- `get(JAVA_INT, 3)` **không** căn hàng 4 byte.
- `getAtIndex(JAVA_INT, 1)` sử dụng byte offset 4 nên căn hàng đúng.

Tạo vùng nhớ đủ alignment:

```java
try (Arena arena = Arena.ofConfined()) {
    var i32 = ValueLayout.JAVA_INT;
    MemorySegment ints =
            arena.allocate(4L * i32.byteSize(),
                           i32.byteAlignment());
    ints.setAtIndex(i32, 0, 123);
}
```

Đây là **fragment Java chạy được trong ngữ cảnh method**. Việc `Arena.allocate(byteSize, byteAlignment)` bảo đảm địa chỉ cấp phát thỏa alignment yêu cầu của layout; chỉ cấp phát `4 * 4` bytes mà không quan tâm alignment có thể không đủ nếu bạn đang đọc một vùng nhớ **không thuộc arena** với các ràng buộc địa chỉ khác.

### 7.1. Layout unaligned không làm thay đổi ý nghĩa index

`ValueLayout.JAVA_INT_UNALIGNED` là layout đọc/ghi `int` rộng 4 byte nhưng chỉ yêu cầu alignment 1 byte:

```java
var unaligned = ValueLayout.JAVA_INT_UNALIGNED;

// Vị trí vẫn tính bằng BYTE:
int a = segment.get(unaligned, 3);

// getAtIndex vẫn tự nhân 4:
int b = segment.getAtIndex(unaligned, 3); // Byte offset 12
```

Đây là **fragment**, giả định segment đủ lớn, còn sống và không bị hạn chế quyền. Hai câu lệnh truy cập hai vị trí khác nhau, **kể cả khi alignment được nới**. Không đánh đồng “unaligned” với “index là byte offset”.

Một ví dụ hay gặp là `MemorySegment.ofArray(new byte[16])`: heap segment từ `byte[]` có maximum alignment 1 byte. Do đó dùng layout `JAVA_INT` (alignment 4) trên đó có thể bị từ chối **ngay cả tại byte offset 0**. Nếu dữ liệu thật sự nằm trong `byte[]` và phải đọc `int`, dùng `JAVA_INT_UNALIGNED` và byte order đúng để đọc, hoặc chọn segment dựa trên mảng kiểu khác có alignment phù hợp. **Nới alignment cần căn cứ định dạng/ABI và cân nhắc hiệu năng/portability**, không phải cách sửa mọi lỗi vùng nhớ.

### 7.2. Alignment lớn hơn byteSize: một trường hợp đặc biệt của AtIndex

Javadoc `getAtIndex`/`setAtIndex` có thể ném `IllegalArgumentException` nếu:

```text
layout.byteAlignment() > layout.byteSize()
```

Ví dụ layout mô tả `int` 4 byte nhưng yêu cầu alignment 8 byte có `byteAlignment = 8 > byteSize = 4`. `AtIndex` dùng stride 4 nên **không phải lựa chọn phù hợp** với các phần tử cách nhau 8 byte. Cần xử lý stride bằng **byte offset** và dùng `get(layout, byteOffset)`/`set(layout, byteOffset, value)` trên segment đủ alignment.

Lưu ý: `withByteAlignment` không làm `byteSize()` tăng. Đây là một khác biệt quan trọng giữa **độ rộng dữ liệu**, **yêu cầu căn hàng** và **khoảng cách (stride)** giữa các record.

## 8. Header, slice và base offset: tọa độ tương đối với segment nào?

`getAtIndex` luôn tính index từ **đầu segment mà bạn gọi phương thức trên đó**. Nó không biết dữ liệu thật bắt đầu sau header bao nhiêu byte.

Giả sử protocol có 8 byte header, tiếp theo là 3 số Java `int` (12 byte). Tổng `20 byte`:

```text
Base segment (20 bytes):
offset 0..7  = header
offset 8..11 = value[0]
offset 12..15= value[1]
offset 16..19= value[2]
```

Nếu gọi `base.getAtIndex(JAVA_INT, 1)`, API đọc **byte offset 4**, tức là vẫn nằm trong header, không phải `value[1]`.

Có hai cách đúng:

**Cách A — Tính offset theo byte:**

```java
long headerBytes = 8;
long index = 1;
long offset = Math.addExact(
        headerBytes,
        Math.multiplyExact(index, ValueLayout.JAVA_INT.byteSize()));

int value = base.get(ValueLayout.JAVA_INT, offset); // offset = 12
```

**Cách B — Tạo slice sau header, sau đó dùng index:**

```java
MemorySegment values = base.asSlice(8, 12);

int value = values.getAtIndex(ValueLayout.JAVA_INT, 1);
// index 1 trong slice -> byte offset 4 trong slice
// tức byte offset 12 trong base.
```

Cả hai là **fragments**, giả định `base` đã được cấp phát đủ 20 byte và địa chỉ/access alignment phù hợp. `asSlice(offset, length)` dùng đơn vị **byte** cho cả `offset` lẫn `length`. Slice không copy dữ liệu; nó tạo một **góc nhìn** vào cùng vùng nhớ. Vì thế ghi qua slice sẽ phản ánh trên base, và ngược lại, trong giới hạn lifetime của segment.

Sau khi slice:

- `slice.byteSize()` là **12 byte**, không phải 20.
- `slice.getAtIndex(JAVA_INT, 0)` tương ứng `base.get(JAVA_INT, 8)`.
- `slice.getAtIndex(JAVA_INT, 1)` tương ứng `base.get(JAVA_INT, 12)`.
- `slice.getAtIndex(JAVA_INT, 3)` vượt giới hạn 12 byte của slice.

**Đừng lấy một global byte offset rồi truyền vào `getAtIndex` trên slice.** Hệ tọa độ đã được thay đổi: offset phải tương đối với **segment đích**, còn index lại tiếp tục được layout scale từ đầu segment đích đó.

### 8.1. Slice có thể làm phát sinh lỗi alignment

Nếu base được căn hàng 4 byte nhưng slice bắt đầu ở **byte offset 1**, địa chỉ bắt đầu của slice bị lệch 1 byte so với căn hàng 4. Khi đó `slice.getAtIndex(JAVA_INT, 0)` có thể không hợp lệ về alignment, mặc dù index 0 và byteSize đủ.

Một cách truy cập có chủ đích đối với dữ liệu nằm lệch byte là dùng `JAVA_INT_UNALIGNED` *nếu định dạng thật sự cho phép*; còn với struct được thiết kế căn hàng, giải pháp đúng thường là chỉnh lại vị trí field hoặc layout chứ không phải bỏ ràng buộc căn chỉnh.

## 9. Khi dữ liệu là struct/record: index của record khác index của primitive

`getAtIndex(ValueLayout.JAVA_INT, i)` luôn tính `i * 4`. Nhưng trong một mảng các bản ghi C, mỗi record có thể chứa **nhiều field và padding**:

```text
struct Example { int id; int score; }   // minh họa 2 int 4 byte
record[0]  bytes 0..7:  id ở 0, score ở 4
record[1]  bytes 8..15: id ở 8, score ở 12
record[2]  bytes 16..23: id ở 16, score ở 20
```

Với cấu trúc hai `int` đã biết chắc layout 8 byte và không padding:

```text
recordStride   = 8 bytes
scoreOffset    = 4 bytes
score[2]       = 2 * 8 + 4 = 20 bytes

getAtIndex(JAVA_INT, 2)
  = byte offset 8   (id của record[1])
  KHÔNG phải score của record[2].
```

Để đọc field của record thứ `i`, công thức đúng là:

```text
recordBase = i * recordLayout.byteSize()
fieldByteOffset = recordLayout.byteOffset(pathToField)
absoluteOffset = recordBase + fieldByteOffset

segment.get(fieldValueLayout, absoluteOffset)
```

**Mã Java 22+ độc lập** minh họa rõ sự khác biệt:

### 9.1. Tệp `StructStrideDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class StructStrideDemo {
    public static void main(String[] args) {
        var intLayout = ValueLayout.JAVA_INT;

        var recordLayout = MemoryLayout.structLayout(
                intLayout.withName("id"),
                intLayout.withName("score"));

        long stride = recordLayout.byteSize(); // 8
        long scoreOffset = recordLayout.byteOffset(
                MemoryLayout.PathElement.groupElement("score")); // 4

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment records = arena.allocate(
                    Math.multiplyExact(3L, stride),
                    recordLayout.byteAlignment());

            for (int i = 0; i < 3; i++) {
                long recordBase = Math.multiplyExact((long)i, stride);
                records.set(intLayout, recordBase, 100 + i);
                records.set(intLayout, recordBase + scoreOffset, 900 + i);
            }

            // index=2 ở đây là primitive-int index -> byte 8.
            System.out.println(
                    "wrong record interpretation: " +
                    records.getAtIndex(intLayout, 2));

            // Đúng: score của record[2] -> byte 2*8+4=20.
            long scoreByteOffset = 2L * stride + scoreOffset;
            System.out.println(
                    "score of record 2: " +
                    records.get(intLayout, scoreByteOffset));

            System.out.println("record stride: " + stride);
            System.out.println("score byte offset: " + scoreByteOffset);
        }
    }
}
```

Lệnh:

```bash
javac StructStrideDemo.java
java StructStrideDemo
```

**Stdout dự kiến:**

```text
wrong record interpretation: 101
score of record 2: 902
record stride: 8
score byte offset: 20
```

Vì record 1 bắt đầu ở byte 8, `getAtIndex(JAVA_INT, 2)` đọc `id = 101` của record 1, không phải `score = 902` của record 2. Đây là lỗi logic **không nhất thiết ném exception**: truy cập có thể vẫn nằm trong bounds và đúng alignment nhưng trả **nhầm dữ liệu hợp lệ**.

Cấu trúc trên dùng đúng hai Java `int` liền nhau để ví dụ đơn giản. Khi ánh xạ C struct thực tế, cần xét **ABI**, padding giữa field, tổng kích thước, căn chỉnh và kiểu C thực tế. Không suy ra `sizeof(struct)` chỉ bằng cách cộng thủ công kích thước các field nếu ABI có padding. Hãy mô tả chính xác bằng `MemoryLayout.structLayout` và `MemoryLayout.paddingLayout` khi cần, hoặc dùng layout do code native và Java cùng thỏa thuận.

### 9.2. Array-of-structs không đồng nghĩa dãy int liên tục theo nghiệp vụ

Một cách tránh nhầm là dùng:

- `recordLayout.byteSize()` để tính **stride giữa các record**.
- `recordLayout.byteOffset(...)` để tìm **offset của field trong một record**.
- `segment.get(fieldLayout, absoluteByteOffset)` để đọc field theo **byte**.
- `segment.getAtIndex(primitiveLayout, i)` **chỉ khi** dữ liệu thật sự là một dãy primitive liên tục có khoảng cách `primitiveLayout.byteSize()`.

Nếu record có field `int value` ở mỗi 16 byte, `getAtIndex(JAVA_INT, i)` không biểu diễn record index `i`; phải dùng `base + i * 16 + valueFieldOffset`. Mọi phép nhân/cộng offset từ dữ liệu bên ngoài cần được kiểm soát overflow và bounds.

## 10. Byte order là một vấn đề khác với offset

**Byte order (endianness)** quyết định 4 bytes được ghép thành một `int` ra sao; **offset/index** quyết định bắt đầu từ byte nào. Đây là hai trục độc lập.

`ValueLayout.JAVA_INT` dùng `ByteOrder.nativeOrder()`. Nếu một file/protocol yêu cầu **big-endian** hoặc **little-endian**, tạo layout tương ứng:

```java
import java.nio.ByteOrder;

// Fragments:
var big = ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
var little = ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);

// Cả hai vẫn rộng 4 byte và getAtIndex(..., 2)
// đều bắt đầu ở byte offset 8.
int x = segment.getAtIndex(big, 2);
int y = segment.getAtIndex(little, 2);
```

Đây là **fragment**, cần các biến `segment` và import `ValueLayout` trong chương trình thực. `x` và `y` có thể khác nhau vì diễn giải byte order khác, nhưng vị trí bắt đầu vẫn là byte offset `2 × 4 = 8`.

**Không dùng thay đổi endianness để sửa lỗi lệch vị trí.** Nếu đọc sai field do nhầm record stride hoặc header bytes, đổi `withOrder` chỉ biến đổi giá trị từ những bytes sai; nó không sửa offset.

## 11. Ngoại lệ và kiểm tra an toàn

Những lỗi thường gặp ở FFM access:

| Tình huống | Dấu hiệu thường gặp | Nguyên nhân và cách xử lý |
| --- | --- | --- |
| `getAtIndex(JAVA_INT, 4)` trên 16 byte | `IndexOutOfBoundsException` | Index 4 ứng với byte 16, không còn 4 byte để đọc |
| `get(JAVA_INT, -4)` | `IndexOutOfBoundsException` | Byte offset âm |
| `getAtIndex(JAVA_INT, -1)` | `IndexOutOfBoundsException` | Element index âm |
| Index × layout size overflow `long` | `IndexOutOfBoundsException` | API kiểm tra overflow; đừng tự tính bằng phép nhân unchecked |
| `get(JAVA_INT, 3)` trên segment căn hàng 4 | `IllegalArgumentException` | Vị trí byte không đáp ứng alignment |
| `getAtIndex` với `layout.byteAlignment() > layout.byteSize()` | `IllegalArgumentException` | AtIndex không phù hợp stride/alignment của layout |
| `set` trên read-only segment | `IllegalArgumentException` | Segment không cho phép ghi |
| Dùng segment từ arena đã đóng | `IllegalStateException` | Backing memory đã hết lifetime |
| Truy cập confined segment từ thread khác | `WrongThreadException` | Segment không accessible từ thread hiện tại |
| Đọc đúng bounds nhưng sai giá trị | Có thể **không có exception** | Nhầm byte offset, index, struct stride, endianness hoặc field layout |

Javadoc định nghĩa cụ thể ngoại lệ theo overload và tình trạng segment. Nếu nhiều ràng buộc cùng bị vi phạm, không viết code phụ thuộc thứ tự kiểm tra của VM, ví dụ một truy cập vừa vượt bounds vừa misaligned. Kiểm tra đầy đủ **cả bounds và alignment** theo định dạng dữ liệu.

### 11.1. Segment còn sống là điều kiện độc lập với index

`Arena` quản lý lifetime của native segments. Ví dụ:

```java
MemorySegment segment;
try (Arena arena = Arena.ofConfined()) {
    segment = arena.allocate(
            ValueLayout.JAVA_INT.byteSize(),
            ValueLayout.JAVA_INT.byteAlignment());
    segment.setAtIndex(ValueLayout.JAVA_INT, 0, 7);
}

// Sai: arena đã đóng, vùng native memory không còn hợp lệ.
// int value = segment.getAtIndex(ValueLayout.JAVA_INT, 0);
```

Đây là **fragment**; không dùng `segment` sau `arena.close()`. Chỉ số `0` vẫn nằm trong phạm vi lý thuyết, nhưng lifetime không còn hợp lệ: một lời gọi có thể ném `IllegalStateException`. Có bounds hợp lệ không cho phép dùng vùng bộ nhớ đã đóng.

### 11.2. Heap segment và native segment có khác đơn vị không?

Không. Cả hai đều dùng byte offset cho `get`/`set` và element index được layout scale cho `getAtIndex`/`setAtIndex`.

Ví dụ một mảng Java `int[]`:

```java
MemorySegment heap = MemorySegment.ofArray(
        new int[] {10, 20, 30});

System.out.println(
        heap.getAtIndex(ValueLayout.JAVA_INT, 1)); // 20

System.out.println(
        heap.get(ValueLayout.JAVA_INT, 4)); // 20
```

Đây là **fragment** với `MemorySegment` và `ValueLayout` đã import. Nó sử dụng heap segment backed by `int[]`, có alignment đủ cho `JAVA_INT`. Không nên suy luận từ ví dụ này rằng `MemorySegment.ofArray(new byte[12])` cũng hỗ trợ `JAVA_INT` alignment 4; maximum alignment của heap segment phụ thuộc primitive array type.

## 12. Những lỗi thực tế hay gặp và cách sửa

### Lỗi 1 — Truyền element index cho API byte offset

```java
long elementIndex = 3;

// SAI Ý ĐỊNH: 3 là byte offset, không phải index thứ 3.
// int result = segment.get(ValueLayout.JAVA_INT, elementIndex);

// ĐÚNG:
int result = segment.getAtIndex(ValueLayout.JAVA_INT, elementIndex);
```

Với layout 4 byte, offset 3 thường misaligned. Nếu dùng unaligned layout thì lỗi có thể **không bị phát hiện** và trả dữ liệu sai.

### Lỗi 2 — Nhân 4 rồi đưa vào getAtIndex

```java
long elementIndex = 3;
long byteOffset = elementIndex * ValueLayout.JAVA_INT.byteSize();

// SAI: truyền byteOffset=12 như element index → truy cập byte 48.
// int wrong = segment.getAtIndex(ValueLayout.JAVA_INT, byteOffset);

// ĐÚNG: mỗi API nhận đúng đơn vị.
int a = segment.getAtIndex(ValueLayout.JAVA_INT, elementIndex);
int b = segment.get(ValueLayout.JAVA_INT, byteOffset);
```

### Lỗi 3 — Dùng segment.byteSize làm số phần tử

```java
long byteCount = segment.byteSize();
long elementCount = byteCount / ValueLayout.JAVA_INT.byteSize();

// SAI: loop i < byteCount để getAtIndex(JAVA_INT,i).
// ĐÚNG khi dữ liệu là dãy int liên tục:
for (long i = 0; i < elementCount; i++) {
    int value = segment.getAtIndex(ValueLayout.JAVA_INT, i);
    // ... xử lý value ...
}
```

Đây là **fragment**; nếu segment chứa header hoặc trailing bytes, phải giảm khoảng dữ liệu và/hoặc tạo slice trước khi đếm.

### Lỗi 4 — Nhầm index của struct với index của field

Trong `struct { int id; int score; }` (8 byte), record index 2 cần byte offset `16` cho `id` và `20` cho `score`, không phải `getAtIndex(JAVA_INT, 2)` hay `getAtIndex(JAVA_INT, 5)` theo “vị trí field” tùy tiện nếu layout có padding. Hãy lấy stride và field offset từ layout thực.

### Lỗi 5 — Bỏ qua byte order hoặc alignment của dữ liệu native

FFM API kiểm tra alignment/bounds nhưng **không biết** file protocol/C ABI của bạn có đúng hay không. Hãy xác minh layout chuẩn của dữ liệu bên ngoài, dùng `withOrder` khi cần và đảm bảo field offsets chính xác.

### Lỗi 6 — Dùng layout sai kích thước

Nếu segment chứa 4 phần tử `short` (mỗi phần tử 2 byte), `getAtIndex(JAVA_INT, 1)` bắt đầu ở byte 4 và đọc 4 byte, tức ghép hai `short`; đó là cách diễn giải khác hoàn toàn. `getAtIndex` không suy ra kiểu dữ liệu thật từ bộ nhớ. Layout phải phản ánh đúng hợp đồng dữ liệu.

## 13. Mẫu thiết kế API tránh nhầm đơn vị

Một cách giảm bug là **đặt tên biến kèm đơn vị**:

```java
long elementIndex = 3;
long elementByteSize = ValueLayout.JAVA_INT.byteSize();
long byteOffset = Math.multiplyExact(
        elementIndex, elementByteSize);

int valueByIndex = segment.getAtIndex(
        ValueLayout.JAVA_INT, elementIndex);
int valueByBytes = segment.get(
        ValueLayout.JAVA_INT, byteOffset);
```

Ưu tiên:

- `byteOffset`, `headerBytes`, `recordStrideBytes` cho mọi giá trị **byte**.
- `elementIndex`, `recordIndex`, `elementCount` cho mọi giá trị **chỉ số / số phần tử**.
- `layout.byteSize()` thay vì viết trực tiếp `4` hay `8` khắp code.
- `Math.multiplyExact`/`Math.addExact` nếu cần tính offset thủ công từ input lớn.
- `asSlice(headerBytes, payloadByteCount)` để loại header khỏi hệ tọa độ trước khi dùng `getAtIndex`.
- Kiểm thử **ít nhất ba vị trí**: index 0, index cuối hợp lệ và index đầu tiên vượt bounds.

Khi làm API wrapper, có thể giữ một phương thức `getElement(long elementIndex)` bên ngoài và chỉ chuyển đổi ở lớp thấp. Tránh một biến tên `offset` mơ hồ được lúc thì dùng như bytes, lúc thì dùng như index.

## 14. Câu hỏi tự kiểm tra (kèm đáp án)

**Câu 1.** Một segment dài 32 byte chứa `long`, mỗi `long` 8 byte. `getAtIndex(JAVA_LONG, 2)` dùng byte offset bao nhiêu?  
**Đáp án:** `2 × 8 = 16` byte. Tương đương `get(JAVA_LONG, 16)` nếu alignment/lifetime hợp lệ.

**Câu 2.** `set(JAVA_INT, 2, 99)` có nghĩa là ghi phần tử `int[2]` không?  
**Đáp án:** Không. Nó yêu cầu ghi `int` bắt đầu ở **byte offset 2**, thường misaligned. Muốn ghi phần tử index 2, dùng `setAtIndex(JAVA_INT, 2, 99)` hoặc `set(JAVA_INT, 8, 99)`.

**Câu 3.** `getAtIndex(JAVA_INT, 8)` có đọc byte thứ 8 không?  
**Đáp án:** Không. Nó đọc một `int` bắt đầu ở byte `8 × 4 = 32` của segment.

**Câu 4.** Một segment 18 byte lưu các `int` liên tục. Có thể đọc bao nhiêu `int` đầy đủ?  
**Đáp án:** `⌊18/4⌋ = 4`, chỉ số `0..3`, thừa 2 byte. Còn phải bảo đảm căn chỉnh/lifetime.

**Câu 5.** `base.asSlice(8, 12).getAtIndex(JAVA_INT, 1)` đọc bắt đầu ở byte nào của `base`?  
**Đáp án:** Byte `8 + 1 × 4 = 12` của base. Tham số `1` là index tính từ đầu slice.

**Câu 6.** Nếu layout có `byteSize = 4` nhưng `byteAlignment = 8` thì `getAtIndex` có phải luôn dùng stride 8?  
**Đáp án:** Không. Index scaling vẫn theo `byteSize = 4`, và API có thể ném `IllegalArgumentException` vì `byteAlignment > byteSize`. Với dữ liệu cách nhau 8 byte, tính byte offsets và dùng `get`/`set`.

**Câu 7.** Record có stride 24 byte, field `price` bắt đầu sau 16 byte. `price` của record index 3 nằm ở đâu?  
**Đáp án:** `3 × 24 + 16 = 88` byte từ đầu bảng record (nếu không có header). Không dùng `getAtIndex(JAVA_LONG, 3)` nếu price là 8 byte, vì nó chỉ đọc từ byte `24`.

**Câu 8.** Nếu hai lời gọi có cùng byte offset nhưng dùng `JAVA_INT` và `JAVA_INT.withOrder(BIG_ENDIAN)`, kết quả có chắc bằng nhau?  
**Đáp án:** Không, dữ liệu bytes được diễn giải theo byte order khác nhau. Byte offset/index xác định **vị trí**, còn layout xác định **cách diễn giải**.

**Câu 9.** Byte offset hợp lệ nhưng arena đã đóng: có đọc tiếp được không?  
**Đáp án:** Không. MemorySegment còn bị ràng buộc bởi lifetime, thread accessibility và quyền ghi/đọc, không chỉ bounds.

## 15. Kết luận nhanh

- **`get(layout, offset)` / `set(layout, offset, value)`:** tham số vị trí là **byte offset**.
- **`getAtIndex(layout, index)` / `setAtIndex(layout, index, value)`:** tham số vị trí là **logical element index**, JVM tự nhân `layout.byteSize()`.
- **`byteOffset = index × layout.byteSize()`**, nhưng **đừng nhân hai lần** và đừng coi `segment.byteSize()` là số phần tử.
- **`asSlice` nhận byte offsets và tạo hệ tọa độ mới**; index trong slice tính từ đầu slice.
- **Structs/records có stride và field offsets riêng**; `getAtIndex(JAVA_INT, recordIndex)` không tự hiểu cấu trúc record.
- **Bounds, alignment, byte order, lifetime và quyền truy cập** là các quy tắc độc lập; một vị trí đúng về toán học vẫn có thể không hợp lệ hoặc đọc dữ liệu sai.
- **FFM API trong `java.lang.foreign` là API chính thức từ JDK 22**; dùng JDK 22+ cho ví dụ biên dịch/chạy trong bài.

### Tài liệu chính thức

- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): chữ ký `get`/`set`/`getAtIndex`/`setAtIndex`, công thức scale index, quy tắc bounds, alignment và lifetime.
- [Oracle Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): `byteSize()`, `byteAlignment()`, `withOrder`, `JAVA_INT`/`JAVA_INT_UNALIGNED`.
- [Oracle Java SE 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html): cách phân bổ native segments bằng `Arena` và cách truy cập layout theo phần tử.
- [Oracle Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): `byteOffset`, group/sequence layouts và layout paths cho structs.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): API hoàn thiện trong JDK 22, phạm vi FFM và lý do thay thế các cơ chế native-memory cũ.
