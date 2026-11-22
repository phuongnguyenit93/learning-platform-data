# Chọn thứ tự byte phù hợp với dữ liệu bản địa hoặc định dạng tệp

## 1. Vì sao byte order quan trọng khi làm việc với MemorySegment?

Trong Java FFM API (Foreign Function & Memory API), `MemorySegment` là một vùng nhớ gồm các **byte**. Để đọc hoặc ghi một giá trị nhiều byte — chẳng hạn `short`, `int`, `long`, `float` hoặc `double` — chương trình cần biết **các byte được sắp theo thứ tự nào**. Thứ tự đó gọi là *byte order* hay *endianness*.

Một giá trị số nguyên 32-bit có cùng giá trị toán học nhưng có thể được biểu diễn trong bộ nhớ như sau:

```text
Giá trị logic: 0x12345678 (4 byte)

BIG_ENDIAN:
vị trí byte     0     1     2     3
               12    34    56    78
               ↑                 ↑
        byte quan trọng nhất     byte ít quan trọng nhất

LITTLE_ENDIAN:
vị trí byte     0     1     2     3
               78    56    34    12
               ↑                 ↑
        byte ít quan trọng nhất  byte quan trọng nhất
```

Nếu bốn byte `12 34 56 78` được **đọc theo big-endian**, giá trị nhận được là `0x12345678`. Nếu cũng bốn byte đó được **đọc theo little-endian**, giá trị lại là `0x78563412`. Không có lỗi bounds hay exception bắt buộc nào: phần mềm có thể nhận **một số hợp lệ nhưng sai ý nghĩa**.

Vì thế, câu hỏi đúng không phải là “máy tính của tôi đang dùng little-endian hay big-endian?”, mà là:

> **Những byte đang đọc/ghi được định nghĩa theo quy ước nào: ABI bản địa của tiến trình, một định dạng tệp cố định, hay một giao thức truyền dữ liệu?**

Câu trả lời quyết định việc dùng `ByteOrder.nativeOrder()`, `ByteOrder.BIG_ENDIAN` hay `ByteOrder.LITTLE_ENDIAN`.

**Phiên bản:** Mã FFM trong bài dùng `java.lang.foreign` chính thức từ **JDK 22** (JEP 454). Java 17 không có cùng API ổn định; ví dụ chỉ cần `ByteBuffer` có thể chạy từ JDK 17, nhưng ví dụ `MemorySegment` cần **JDK 22+**. Đây là nội dung Java nâng cao về tương tác với bộ nhớ/native, không phải khẳng định mọi JDK 17 đều biên dịch được `java.lang.foreign`.

## 2. Ba loại byte order và quy tắc chọn

`java.nio.ByteOrder` cung cấp:

- `ByteOrder.BIG_ENDIAN`: byte quan trọng nhất (*most significant byte*) đứng trước ở địa chỉ thấp.
- `ByteOrder.LITTLE_ENDIAN`: byte ít quan trọng nhất (*least significant byte*) đứng trước ở địa chỉ thấp.
- `ByteOrder.nativeOrder()`: trả về thứ tự byte **của nền tảng JVM đang chạy**; giá trị trả về là một trong hai hằng trên.

| Nguồn dữ liệu | Chọn byte order | Vì sao |
| --- | --- | --- |
| Một C `int32_t` được native library ghi trực tiếp vào vùng nhớ trong cùng process | Thường dùng `nativeOrder()` | C compiler/CPU biểu diễn scalar nguyên theo ABI của platform; còn phải khớp kiểu và alignment |
| Native library công khai ABI quy định field luôn là big-endian | `BIG_ENDIAN` | **Hợp đồng ABI** cụ thể quan trọng hơn kiến trúc CPU |
| Một file format quy định số nguyên 32-bit ở dạng big-endian | `BIG_ENDIAN` | File phải đọc nhất quán trên mọi máy |
| Một file format quy định số nguyên 32-bit ở dạng little-endian | `LITTLE_ENDIAN` | Không phụ thuộc máy chạy Java |
| Một packet/protocol định nghĩa “network byte order” theo quy ước chuẩn | Thường là `BIG_ENDIAN`, nếu protocol đó quy định | Phải dựa vào specification của protocol, không suy đoán mọi giao thức đều big-endian |
| Vùng nhớ nhận từ API native nhưng tài liệu không nói endian/ABI | **Chưa đủ thông tin để chọn** | Phải xem contract hoặc giao thức trao đổi |
| Dãy dữ liệu 1 byte (`byte`, ASCII/UTF-8 byte stream) | Endian không ảnh hưởng từng byte | Byte order chỉ có nghĩa khi tổ hợp **nhiều byte** thành một giá trị |

**Quy tắc thiết kế:** byte order là **thuộc tính của dữ liệu/field theo hợp đồng**. Không nên gán `nativeOrder()` chỉ vì ứng dụng đang chạy trên máy x86 hay vì “native” xuất hiện trong tên API.

### 2.1. Native byte order có nghĩa gì?

Trên nhiều CPU x86-64, `ByteOrder.nativeOrder()` là `LITTLE_ENDIAN`; nhưng Java vẫn hỗ trợ môi trường khác. Đừng viết code giả định **mọi** JVM đều little-endian.

```java
import java.nio.ByteOrder;

System.out.println(ByteOrder.nativeOrder());
```

Đây là fragment từ một đoạn Java hợp lệ nếu đặt trong method; kết quả tùy platform nên không có stdout cố định chung cho mọi máy.

Native order thường có ích cho **memory-mapped hoặc shared memory của chương trình native đang chạy cùng ABI**, đặc biệt khi hai bên trao đổi trực tiếp một mảng scalar C và Java. Nó **không đủ** để chứng minh một `struct` bất kỳ tương thích: còn có `sizeof`, padding, alignment, kiểu `long`/`size_t`, enum, boolean, ABI và vòng đời con trỏ.

### 2.2. Fixed endian cho file format và network protocol

Một file ghi trên máy little-endian có thể được mở nhiều năm sau trên máy big-endian. Nếu file format có quy ước `uint32` big-endian, Java phải đọc bằng big-endian **trên cả hai máy**. Ngược lại, nếu file quy định little-endian, layout phải cố định little-endian.

Không nên lưu tệp bằng cách đơn giản là `fwrite(&someInt, sizeof someInt, 1, file)` phía C rồi cho rằng file portable. Cách ấy ghi bytes theo biểu diễn native; khi chuyển platform, file có thể bị diễn giải sai. Nếu muốn định dạng bền vững, **chọn quy ước on-disk có tài liệu** và mã hóa/giải mã đúng tại ranh giới.

## 3. Cách biểu diễn byte order với ValueLayout

FFM dùng `ValueLayout` để diễn giải bytes theo kiểu Java cụ thể. Trong JDK 22+:

```java
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

// Layout int 4 byte theo thứ tự byte bản địa.
ValueLayout.OfInt nativeInt = ValueLayout.JAVA_INT;

// Cùng độ rộng và carrier int, nhưng cố định BIG_ENDIAN.
ValueLayout.OfInt bigInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

// Cùng độ rộng và carrier int, nhưng cố định LITTLE_ENDIAN.
ValueLayout.OfInt littleInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);
```

Đây là **fragment khai báo biến** có thể đặt trong phương thức Java. `JAVA_INT` có `byteSize() == 4` và `order() == ByteOrder.nativeOrder()`. `withOrder(order)` trả về **một layout mới**, không sửa dữ liệu trong `MemorySegment` và không thay đổi layout gốc.

Ví dụ truy cập:

```java
int value = segment.get(bigInt, 0L);
segment.set(littleInt, 4L, 0x12345678);
```

`get(layout, offset)` và `set(layout, offset, value)` dùng **byte offset** so với đầu segment hiện tại. Ở dòng đầu `get(bigInt, 0)` đọc từ byte 0 theo big-endian; dòng hai ghi 4 byte bắt đầu ở offset 4 theo little-endian.

### 3.1. Byte order là thuộc tính của *phép truy cập*, không phải của cả segment

`MemorySegment` chỉ cung cấp bytes và các ràng buộc truy cập. Cùng một segment có thể được truy cập bằng nhiều layout:

```java
int bigValue = segment.get(bigInt, 0L);
int littleValue = segment.get(littleInt, 0L);
```

Hai biến có thể có giá trị khác nhau dù cùng địa chỉ. **Không có bản sao dữ liệu hay phép hoán đổi bytes vĩnh viễn** khi gọi `withOrder`. Mỗi `get` diễn giải những bytes đang có theo layout đã chọn; mỗi `set` mã hóa giá trị theo layout đó.

Một file header cũng có thể chứa nhiều field có endian khác nhau. Bạn có quyền dùng `bigInt` cho field A và `littleInt` cho field B nếu tài liệu định dạng quy định như vậy.

### 3.2. `order()` cho biết layout đang dùng thứ tự nào

```java
ByteOrder order = ValueLayout.JAVA_INT.order();
boolean matchesHost = order == ByteOrder.nativeOrder();
```

Đây là fragment. `matchesHost` luôn `true` đối với layout `JAVA_INT` chuẩn trên JVM đó, trong khi:

```java
ByteOrder fileOrder =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN).order();
```

cho `BIG_ENDIAN` trên mọi nền tảng. Đừng suy từ `segment.byteSize()` hoặc địa chỉ bộ nhớ ra thứ tự byte; **bytes không tự mang metadata nói rằng chúng là big hay little endian**.

### 3.3. Những kiểu có byte order ý nghĩa

| Layout | Độ rộng | Ví dụ ý nghĩa |
| --- | ---: | --- |
| `ValueLayout.JAVA_BYTE` | 1 byte | Một byte đơn lẻ không đổi khi chuyển endian |
| `ValueLayout.JAVA_SHORT` | 2 byte | Cách diễn giải số 16-bit từ hai byte |
| `ValueLayout.JAVA_CHAR` | 2 byte | Một code unit UTF-16; không đồng nghĩa encoding của cả chuỗi |
| `ValueLayout.JAVA_INT` | 4 byte | Số nguyên 32-bit |
| `ValueLayout.JAVA_LONG` | 8 byte | Số nguyên 64-bit |
| `ValueLayout.JAVA_FLOAT` | 4 byte | 32-bit IEEE 754 theo cách Java dùng |
| `ValueLayout.JAVA_DOUBLE` | 8 byte | 64-bit IEEE 754 theo cách Java dùng |
| `ValueLayout.ADDRESS` | Platform-dependent | Địa chỉ native; **không phải một field file portable** |

Byte order chỉ kiểm soát **thứ tự các byte của một value**. Nó không đổi số byte của value, kiểu carrier Java, vị trí offset hay số phần tử. Với pointer, `size_t` và C `long`, phải xét ABI chứ không chỉ endian.

## 4. Ví dụ Java 22+: cùng giá trị, hai chuỗi byte khác nhau

Ví dụ độc lập này dùng `MemorySegment.ofArray(new byte[8])` để nhìn trực tiếp một mảng byte. Nó ghi cùng giá trị `0x12345678` lần lượt theo big-endian và little-endian, rồi in bytes và kết quả khi cố ý đọc sai thứ tự.

Vì backing memory là `byte[]`, **alignment tối đa cho heap segment này là 1 byte**. Do đó ta dùng `JAVA_INT_UNALIGNED` thay vì `JAVA_INT`. Chọn `UNALIGNED` **không đổi độ rộng 4 byte**, chỉ nới alignment; byte order vẫn được quyết định bằng `withOrder`.

### 4.1. Tệp `EndianMemorySegmentDemo.java`

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;
import java.util.HexFormat;
import java.util.Locale;

public class EndianMemorySegmentDemo {
    public static void main(String[] args) {
        byte[] bytes = new byte[8];
        MemorySegment segment = MemorySegment.ofArray(bytes);

        ValueLayout.OfInt big =
                ValueLayout.JAVA_INT_UNALIGNED
                        .withOrder(ByteOrder.BIG_ENDIAN);
        ValueLayout.OfInt little =
                ValueLayout.JAVA_INT_UNALIGNED
                        .withOrder(ByteOrder.LITTLE_ENDIAN);

        int number = 0x12345678;

        // Vùng đầu: 4 byte big-endian.
        segment.set(big, 0L, number);

        // Vùng sau: 4 byte little-endian.
        segment.set(little, 4L, number);

        String hexBytes = HexFormat.ofDelimiter(" ")
                .withUpperCase().formatHex(bytes);
        System.out.println("bytes: " + hexBytes);

        System.out.printf(Locale.ROOT,
                "big @0: %08X%n", segment.get(big, 0L));
        System.out.printf(Locale.ROOT,
                "little @4: %08X%n", segment.get(little, 4L));

        // Cố tình đọc bytes big-endian bằng layout little-endian.
        System.out.printf(Locale.ROOT,
                "wrong order @0: %08X%n", segment.get(little, 0L));
    }
}
```

**Build và chạy với JDK 22+:**

```bash
javac EndianMemorySegmentDemo.java
java EndianMemorySegmentDemo
```

**Stdout dự kiến, độc lập thứ tự byte của máy:**

```text
bytes: 12 34 56 78 78 56 34 12
big @0: 12345678
little @4: 12345678
wrong order @0: 78563412
```

### 4.2. Vì sao kết quả độc lập platform?

- `big` và `little` đều là layout **có order cố định**, không phụ thuộc `nativeOrder()`.
- `set(big, 0L, number)` ghi `12 34 56 78` vào byte 0..3.
- `set(little, 4L, number)` ghi `78 56 34 12` vào byte 4..7.
- `get(big, 0L)` và `get(little, 4L)` tái tạo cùng giá trị Java `0x12345678`.
- `get(little, 0L)` cố đọc dãy `12 34 56 78` theo little-endian; nhận `0x78563412` — một **giá trị sai ngữ nghĩa**, không phải lỗi memory safety.
- `HexFormat` in **từng byte nguyên vẹn**, dùng ký hiệu hex để nhìn rõ bytes. Nó không tự đảo thứ tự byte của số nguyên nhiều byte.

Không cần gọi JNI hoặc `Arena` cho ví dụ này vì chỉ kiểm chứng FFM view của mảng `byte[]`. Với native memory thực, có thể dùng `Arena.allocate`; quy tắc `withOrder` vẫn như nhau.

## 5. Dữ liệu bản địa: khi nào chọn ByteOrder.nativeOrder()?

Khi trao đổi trực tiếp với một native library trong cùng tiến trình, chương trình C/C++ có thể cung cấp vùng nhớ chứa một array `int32_t` theo ABI của platform. Khi **hợp đồng native API khẳng định** rằng các phần tử dùng biểu diễn máy hiện tại, Java có thể đọc:

```java
var nativeInt = ValueLayout.JAVA_INT;
int first = segment.getAtIndex(nativeInt, 0);
int second = segment.getAtIndex(nativeInt, 1);
```

Đây là fragment giả định `segment` trỏ tới vùng nhớ còn sống, đủ kích thước, căn hàng phù hợp, có quyền đọc và lưu đúng các số 32-bit native. `ValueLayout.JAVA_INT.order()` đã là `ByteOrder.nativeOrder()`, nên không cần `withOrder(nativeOrder())` trừ khi muốn thể hiện chủ ý rõ ràng.

Có thể viết tường minh:

```java
ValueLayout.OfInt nativeInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.nativeOrder());
```

**Quan trọng:** “dữ liệu bản địa” không có nghĩa mọi giá trị ở native memory đều dùng native order. Ví dụ native code đọc một file big-endian vào buffer `uint8_t *` và **chưa decode**; buffer vẫn chứa **big-endian bytes** cho dù nằm trong RAM của máy little-endian. Java phải đọc theo **định dạng bytes thực tế trong buffer**, không theo ngôn ngữ đã cấp phát nó.

### 5.1. Phân biệt *native scalar* và *opaque byte buffer*

Giả sử một API C trả:

```c
/* Fragment C: giả định out đã được cấp phát đủ lớn. */
uint32_t value = 0x12345678u;
memcpy(out, &value, sizeof(value));
```

Nếu `uint32_t` tồn tại và C API thật sự trả bytes từ object representation của giá trị native này, thứ tự bytes là native order của platform. Java nhận buffer phải dùng layout tương ứng (và biết chính xác số byte/kiểu).

Một API khác trả:

```c
/* Fragment C: ghi chuẩn big-endian bất kể CPU. */
out[0] = 0x12;
out[1] = 0x34;
out[2] = 0x56;
out[3] = 0x78;
```

Vùng nhớ có thể cùng được tạo bởi `malloc`, nhưng **hợp đồng bytes đã thay đổi**. Java phải dùng `BIG_ENDIAN`. Nếu chỉ biết `out` là “native pointer” mà không biết bên nào tạo dữ liệu theo quy tắc gì, không có đủ thông tin để decode chính xác.

`memcpy` trong ví dụ không tự byteswap; nó sao chép bytes của biến nguồn. Ngược lại, `segment.get(layout, offset)` diễn giải bytes dựa trên layout cụ thể và trả giá trị Java, tách biệt thứ tự biểu diễn của máy Java caller.

### 5.2. Với native struct, byte order chỉ là một phần ABI

Một C `struct` có thể có padding, alignment và kích thước field phụ thuộc ABI. Ví dụ một struct có `uint8_t kind` rồi `uint32_t count` thường cần padding trước `count` trên nhiều ABI. Chọn đúng endian cho `count` **chưa đủ** nếu Java đọc offset sai.

Khi mô tả một C struct, nên xác nhận:

1. Kích thước field: `uint32_t` khác `unsigned long`, `size_t` và pointer; không gán tất cả là Java `int`.
2. Offset/padding: xác định qua ABI/`offsetof`/header của thư viện, thay vì đoán bằng phép cộng không xét alignment.
3. Thứ tự byte của **từng scalar field**, đặc biệt nếu struct chứa buffer network-order được xử lý riêng.
4. Lifetime và ownership của vùng nhớ native; `MemorySegment` không tự giữ một con trỏ C vô hạn.
5. Quyền đọc/ghi và thread access của segment, nhất là khi callback từ native thread.

Nếu định dạng bên ngoài yêu cầu portability cao, thường tốt hơn là mô tả **serialization layout rõ ràng**, không dump trực tiếp C structs ra file.

## 6. Định dạng tệp: cố định endian cho từng trường dữ liệu

Giả sử một định dạng tệp giả lập có header 12 byte với quy tắc:

| Byte offset | Độ dài | Tên field | Kiểu/byte order |
| ---: | ---: | --- | --- |
| 0 | 4 | `magic` | 4 byte ASCII `DMO1`, không liên quan endian |
| 4 | 2 | `version` | Unsigned 16-bit **little-endian** |
| 6 | 2 | `flags` | Unsigned 16-bit **big-endian** |
| 8 | 4 | `payloadLength` | Unsigned 32-bit **big-endian** |

Định dạng này cố tình dùng endian hỗn hợp để chỉ ra **byte order là contract của field**, không phải một thuộc tính duy nhất của file hoặc CPU.

Bytes của header:

```text
offset:   00 01 02 03   04 05   06 07   08 09 10 11
hex:      44 4D 4F 31   01 02   A0 B1   00 00 01 00
meaning:  D  M  O  1    version  flags   payload length

version bytes 01 02 (little) -> 0x0201 = 513
flags   bytes A0 B1 (big)    -> 0xA0B1
length  bytes 00 00 01 00    -> 0x00000100 = 256
```

### 6.1. Tệp `MixedEndianHeader.java`

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class MixedEndianHeader {
    public static void main(String[] args) {
        byte[] header = {
                0x44, 0x4D, 0x4F, 0x31,
                0x01, 0x02,
                (byte) 0xA0, (byte) 0xB1,
                0x00, 0x00, 0x01, 0x00
        };

        if (header.length != 12) {
            throw new IllegalArgumentException(
                    "expected 12-byte header");
        }

        MemorySegment segment = MemorySegment.ofArray(header);

        // byte[] heap segment: dùng UNALIGNED layout, alignment 1.
        ValueLayout.OfShort shortLittle =
                ValueLayout.JAVA_SHORT_UNALIGNED
                        .withOrder(ByteOrder.LITTLE_ENDIAN);
        ValueLayout.OfShort shortBig =
                ValueLayout.JAVA_SHORT_UNALIGNED
                        .withOrder(ByteOrder.BIG_ENDIAN);
        ValueLayout.OfInt intBig =
                ValueLayout.JAVA_INT_UNALIGNED
                        .withOrder(ByteOrder.BIG_ENDIAN);

        String magic = new String(
                header, 0, 4, StandardCharsets.US_ASCII);
        int version = Short.toUnsignedInt(
                segment.get(shortLittle, 4L));
        int flags = Short.toUnsignedInt(
                segment.get(shortBig, 6L));
        long payloadLength = Integer.toUnsignedLong(
                segment.get(intBig, 8L));

        System.out.println("magic: " + magic);
        System.out.println("version: " + version);
        System.out.printf(Locale.ROOT, "flags: %04X%n", flags);
        System.out.println("payload length: " + payloadLength);
    }
}
```

**Lệnh JDK 22+:**

```bash
javac MixedEndianHeader.java
java MixedEndianHeader
```

**Stdout dự kiến:**

```text
magic: DMO1
version: 513
flags: A0B1
payload length: 256
```

### 6.2. Các điểm cần kiểm chứng khi đọc header thật

- Field `magic` được xem như **bốn byte ASCII**, không được “byteswap” thành một số nguyên chỉ vì CPU dùng little-endian.
- `version` là little-endian nên `01 02` nghĩa là `0x0201`, không phải `0x0102`.
- `flags` là big-endian. Vì Java `short` là **signed**, `Short.toUnsignedInt` giúp diễn giải 16 bit theo kiểu unsigned mà file format đã quy định.
- `payloadLength` cũng big-endian. Java `int` signed, nên dùng `Integer.toUnsignedLong` khi header quy định **uint32**. Nếu dùng trực tiếp `int`, giá trị lớn hơn `Integer.MAX_VALUE` sẽ trông thành số âm.
- Ví dụ chỉ chứa **header**, chưa chứa payload thật. Nó minh họa cách đọc length, **không tuyên bố** rằng có sẵn 256 byte payload sau header.

Khi xử lý file thực tế, phải kiểm tra **file/header có đủ bytes** *trước* khi đọc từng field, và kiểm tra `payloadLength` đối với số byte còn lại, chính sách giới hạn kích thước và overflow trước khi cấp phát. Một số sai lệch nguy hiểm không gây exception ngay khi đọc header — chẳng hạn length được diễn giải sai endian nhưng vẫn là một số dương rất lớn.

### 6.3. Hai vấn đề khác nhau: byte order và unsignedness

Thứ tự byte trả lời câu hỏi “các byte được sắp thế nào?”, còn **signed/unsigned** trả lời “tập bit được diễn giải thành số âm hay không?”. Chọn đúng `BIG_ENDIAN` nhưng quên chuyển unsigned có thể vẫn cho giá trị sai khi đọc `uint16`/`uint32` lớn.

Ví dụ:

```java
short rawFlags = segment.get(shortBig, 6L);
int flagsUnsigned = Short.toUnsignedInt(rawFlags);

int rawLength = segment.get(intBig, 8L);
long lengthUnsigned = Integer.toUnsignedLong(rawLength);
```

Đây là **fragment**, dùng các biến `segment`/`shortBig`/`intBig` trong phần 6. `Short.toUnsignedInt` và `Integer.toUnsignedLong` **không đổi endian**; chúng chỉ diễn giải cùng bit pattern không dấu trong một Java type lớn hơn.

## 7. Struct/file layout với từng field có byte order riêng

Với một record có field số nguyên cố định, ta có thể gắn `withOrder` trực tiếp lên leaf layouts:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

var fileRecord = MemoryLayout.structLayout(
        ValueLayout.JAVA_SHORT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN).withName("type"),
        ValueLayout.JAVA_SHORT_UNALIGNED
                .withOrder(ByteOrder.LITTLE_ENDIAN).withName("flags"),
        ValueLayout.JAVA_INT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN).withName("length")
);

long lengthOffset = fileRecord.byteOffset(
        MemoryLayout.PathElement.groupElement("length"));
```

Đây là **fragment trong Java method**, giả định import được đặt ở đầu tệp. Layout trên dùng field widths 2+2+4 = 8 byte, đều `UNALIGNED` theo chủ ý cho định dạng packed-file. `lengthOffset` là **4 byte** từ đầu record; thứ tự byte của `length` là big-endian, độc lập với `flags` little-endian.

Trong format khác có padding, không được bỏ qua padding để “cho vừa”. `MemoryLayout.structLayout` mô tả các member theo thứ tự đã khai báo; nó **không tự thêm toàn bộ padding theo mọi C ABI**. Với dữ liệu C struct thực, xác minh offset/layout của compiler và dùng `MemoryLayout.paddingLayout(...)` khi cần.

### 7.1. Record stride và endianness là hai trục độc lập

Ví dụ field `uint32_t value` nằm ở byte offset 8 của mỗi record dài 16 byte. Phần tử record thứ `i` có byte offset:

```text
recordOffset = i * 16
valueOffset  = recordOffset + 8
```

Nếu file quy định field big-endian:

```java
long valueByteOffset = Math.addExact(
        Math.multiplyExact(recordIndex, 16L), 8L);

int raw = segment.get(
        ValueLayout.JAVA_INT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN),
        valueByteOffset);
long value = Integer.toUnsignedLong(raw);
```

Đây là fragment giả định `recordIndex` và `segment` hợp lệ. `Math.multiplyExact`/`Math.addExact` bắt overflow; `get` kiểm tra bounds, alignment và lifetime. Dù sử dụng đúng endian, nếu record stride/field offset bị sai thì vẫn đọc **nhầm bytes**.

**Không dùng `getAtIndex(JAVA_INT, recordIndex)` để tự động áp dụng stride 16**. `getAtIndex` scale theo `layout.byteSize()`, tức 4 đối với `JAVA_INT`. Nó không biết record nghiệp vụ dài 16 byte.

### 7.2. Khi nào endian không quan trọng?

Đối với **chuỗi byte hoặc payload opaque**, không cần chuyển endian từng byte. Ví dụ một field `magic` dài 4 byte, ảnh JPEG, chuỗi UTF-8 hoặc buffer nén — đọc như sequence of bytes, không phải `int` nhiều byte (trừ khi format quy định field multi-byte cụ thể). Byte order cũng **không đảo thứ tự ký tự trong chuỗi**.

Ngược lại, **UTF-16** có quy tắc lưu code units nhiều byte và có thể liên quan BOM/big-endian/little-endian. Ở trường hợp đó hãy dùng charset decoder phù hợp với quy định định dạng; không lấy một layout `JAVA_CHAR` bất kỳ rồi mặc nhiên hiểu đúng mọi file text.

## 8. MemorySegment và ByteBuffer: khác biệt mặc định dễ mắc

**`ByteBuffer` có byte order mặc định là `BIG_ENDIAN`.** Các `ValueLayout.JAVA_INT` và layout primitive chuẩn của FFM lại có byte order mặc định là **`ByteOrder.nativeOrder()`**. Do đó **hai API có thể diễn giải cùng bytes khác nhau khi không cấu hình**.

So sánh:

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

byte[] data = {0x12, 0x34, 0x56, 0x78};

// Mặc định ByteBuffer là BIG_ENDIAN.
int fromBuffer = ByteBuffer.wrap(data).getInt();

// FFM JAVA_INT_UNALIGNED mặc định theo nativeOrder.
int fromSegment = MemorySegment.ofArray(data)
        .get(ValueLayout.JAVA_INT_UNALIGNED, 0);

// Cố định FFM BIG_ENDIAN để khớp ByteBuffer mặc định:
int portable = MemorySegment.ofArray(data).get(
        ValueLayout.JAVA_INT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN), 0);
```

Đây là **fragment**; `fromBuffer` và `portable` đều là `0x12345678`, còn `fromSegment` phụ thuộc byte order host. Với little-endian host, `fromSegment` là `0x78563412`. Không nên mặc định kỳ vọng các API “trong cùng JVM” có cùng default endian.

Nếu muốn `ByteBuffer` little-endian:

```java
ByteBuffer view = ByteBuffer.wrap(data)
        .order(ByteOrder.LITTLE_ENDIAN);

int fromLittle = view.getInt(0); // 0x78563412
```

`ByteBuffer.order(...)` thay đổi cách **view** của buffer đọc/ghi primitive values. Nó không trực tiếp đảo ngược bytes đã có. Ngược lại, `ValueLayout.withOrder(...)` tạo một **layout mới**, cũng không thay đổi bytes trong memory cho đến khi có `set`.

### 8.1. Không byteswap hai lần

Một lỗi hay gặp:

1. Đọc dữ liệu big-endian bằng `get(BIG_ENDIAN, offset)` — Java đã có **giá trị logic đúng**.
2. Lại gọi `Integer.reverseBytes(value)` vì nghĩ phải “chuyển từ big sang little”.
3. Kết quả bị đảo thêm lần nữa, trở thành sai.

Nếu truy cập qua FFM với layout đúng, **API đã diễn giải bytes theo order được chỉ định**. `Integer.reverseBytes` chỉ có ích trong các trường hợp code thật sự cần đảo **bit pattern của một số**; nó không phải bước bắt buộc sau `get(...withOrder(...))`.

Tương tự, `MemorySegment.copy(...)` hay sao chép `byte[]`/`ByteBuffer` theo bytes **không tự chuyển endian**. Nếu muốn chuyển một dãy int từ big-endian sang little-endian, phải **đọc từng giá trị bằng big-endian layout rồi ghi bằng little-endian layout** (hoặc một thuật toán chuyển đổi phù hợp), không chỉ copy bytes từ nguồn sang đích.

## 9. Ví dụ chuyển đổi encoding giữa hai vùng nhớ

Mục tiêu: nguồn chứa hai giá trị int được mã hóa big-endian; đích phải chứa **cùng hai giá trị logic** theo little-endian. Không phụ thuộc máy đang chạy.

**Tệp `EndianConversion.java` (JDK 22+):**

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;
import java.util.HexFormat;
import java.util.Locale;

public class EndianConversion {
    public static void main(String[] args) {
        byte[] source = {
                0x01, 0x02, 0x03, 0x04,
                0x11, 0x22, 0x33, 0x44
        };
        byte[] destination = new byte[source.length];

        MemorySegment input = MemorySegment.ofArray(source);
        MemorySegment output = MemorySegment.ofArray(destination);

        ValueLayout.OfInt be =
                ValueLayout.JAVA_INT_UNALIGNED
                        .withOrder(ByteOrder.BIG_ENDIAN);
        ValueLayout.OfInt le =
                ValueLayout.JAVA_INT_UNALIGNED
                        .withOrder(ByteOrder.LITTLE_ENDIAN);

        long count = source.length / be.byteSize();
        for (long index = 0; index < count; index++) {
            int value = input.getAtIndex(be, index);
            output.setAtIndex(le, index, value);
        }

        System.out.println("source: " +
                HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(source));
        System.out.println("result: " +
                HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(destination));

        System.out.printf(Locale.ROOT, "first value: %08X%n",
                output.getAtIndex(le, 0));
        System.out.printf(Locale.ROOT, "second value: %08X%n",
                output.getAtIndex(le, 1));
    }
}
```

**Lệnh:**

```bash
javac EndianConversion.java
java EndianConversion
```

**Stdout dự kiến:**

```text
source: 01 02 03 04 11 22 33 44
result: 04 03 02 01 44 33 22 11
first value: 01020304
second value: 11223344
```

Lý do: `getAtIndex(be, index)` đọc từng giá trị logic ở source; `setAtIndex(le, index, value)` ghi giá trị đó với thứ tự byte little-endian. Dãy bytes đích **khác** nhưng các giá trị logic khi đọc đúng endian **giống** source.

Đoạn ví dụ giả định số bytes chia hết cho 4; đối với input thực phải kiểm tra độ dài/element count, xác minh dữ liệu đủ và ràng buộc tài nguyên trước khi cấp phát. Nếu file chứa các field có kích thước khác nhau, không thể “swap toàn bộ file theo từng block 4 byte”: phải đọc theo schema từng field để tránh đảo header, padding, chuỗi hoặc payload không liên quan.

## 10. Alignment và phạm vi bộ nhớ: vấn đề riêng, không phải endian

`ValueLayout` còn chứa:

- `byteSize()`: giá trị dùng bao nhiêu byte.
- `byteAlignment()`: vị trí truy cập phải căn theo bao nhiêu byte.
- `order()`: diễn giải bytes theo big/little/native.
- `carrier()`: kiểu Java như `int.class`, `long.class`.

**`withOrder` không tự nới alignment.** Ví dụ:

```java
var beInt = ValueLayout.JAVA_INT
        .withOrder(ByteOrder.BIG_ENDIAN);
```

vẫn có alignment 4 byte. Với `MemorySegment.ofArray(new byte[4])`, maximum alignment của heap segment từ `byte[]` chỉ là 1, vì thế truy cập bằng `beInt` có thể ném `IllegalArgumentException` ngay tại offset 0.

Cách đúng khi đọc một packed-file header từ `byte[]`:

```java
var beIntUnaligned = ValueLayout.JAVA_INT_UNALIGNED
        .withOrder(ByteOrder.BIG_ENDIAN);

int value = MemorySegment.ofArray(
        new byte[] {0x01, 0x02, 0x03, 0x04})
        .get(beIntUnaligned, 0L); // 0x01020304
```

Đây là fragment, không phải file Java độc lập. Dùng `*_UNALIGNED` chỉ khi dữ liệu cần/cho phép layout packed; một số trường hợp unaligned có chi phí hiệu năng hoặc giới hạn platform, đặc biệt khi giao tiếp trực tiếp với native ABI.

### 10.1. Các kiểm tra không thể bỏ qua

| Ràng buộc | Kiểm tra |
| --- | --- |
| Byte offset | `0 <= offset` và `offset + layout.byteSize() <= segment.byteSize()`, tránh overflow khi tự cộng |
| Element index | `getAtIndex` nhân `index * layout.byteSize()`, không nhân theo độ dài struct nếu khác |
| Alignment | Địa chỉ truy cập phù hợp `layout.byteAlignment()`; có thể dùng unaligned layout khi hợp đồng dữ liệu cho phép |
| Lifetime | `Arena` hoặc backing scope còn sống; dùng sau khi close có thể ném `IllegalStateException` |
| Thread confinement | Confined arena/segment phải truy cập từ thread được phép, nếu không có thể ném `WrongThreadException` |
| Quyền ghi | `set` lên read-only segment không hợp lệ |
| Unsignedness | Dùng `Short.toUnsignedInt`/`Integer.toUnsignedLong` khi file quy định unsigned field |
| Byte order | Luôn lấy từ **đặc tả field/protocol/ABI**, không lấy từ phỏng đoán CPU |
| Kiểu dữ liệu | Một `int` 4 byte và một `float` 4 byte có cùng size nhưng ý nghĩa bit pattern khác nhau |

Một kết quả sai endian có thể **không gây exception**, trong khi lỗi bounds/alignment/lifetime thường có ngoại lệ tương ứng. Vì vậy kiểm thử byte order phải dựa trên **bytes mẫu cố định và expected numeric values**, không chỉ dựa vào việc code “chạy được”.

## 11. Các lỗi thường gặp

| Sai lầm | Hệ quả | Sửa thế nào |
| --- | --- | --- |
| Đọc file big-endian bằng `JAVA_INT` mặc định | Trên host little-endian nhận số sai | `JAVA_INT[_UNALIGNED].withOrder(BIG_ENDIAN)` |
| Đọc buffer native scalar bằng `BIG_ENDIAN` cho mọi CPU | Sai khi ABI native little-endian | Dùng layout theo contract native/`nativeOrder()` |
| Mặc định `ByteBuffer` và `ValueLayout.JAVA_INT` có order giống nhau | Cùng bytes nhưng nhận giá trị khác | Chỉ định explicit order ở hai API |
| Cho rằng `withOrder` đảo bytes trong `MemorySegment` | Data không đổi, chỉ diễn giải thay đổi | `get` đúng order, `set` bằng order đích nếu muốn re-encode |
| Gọi `Integer.reverseBytes` sau khi `get(BIG_ENDIAN)` | Đảo lần thứ hai, nhận sai kết quả | Không swap thêm nếu layout đã đúng |
| Đọc `uint32` rồi xử lý `int` âm | Sai kích thước/độ dài khi giá trị vượt 2^31-1 | `Integer.toUnsignedLong` |
| Dùng `JAVA_INT` trên `byte[]` packed | Vi phạm alignment | `JAVA_INT_UNALIGNED` rồi `withOrder` |
| Chỉ sửa endian, bỏ qua padding của C struct | Đọc nhầm field dù endian đúng | Dùng offsets/layout khớp ABI |
| Cắt file bằng block 4 byte rồi đảo mọi block | Làm hỏng strings, padding và fields khác kích cỡ | Decode/encode theo schema từng field |
| Lưu file bằng native `fwrite` rồi kỳ vọng portable | Bytes thay đổi theo ABI/endianness | Chọn file specification endian cố định |
| Tin Java `char`/`String` file tự theo FFM endianness | Nhầm encoding văn bản với primitive layouts | Dùng charset đúng (UTF-8/UTF-16LE/BE...) |
| Dùng native-order trong dữ liệu đã chuyển sang network order | Dữ liệu có order được chuẩn hóa khác CPU | Chọn order theo giao thức dữ liệu đã được chuẩn hóa |

### 11.1. Nhầm endian với offset

Giả sử segment 16 byte có header 8 byte và một số 4 byte big-endian ở offset 8. Đọc bằng `get(BIG_ENDIAN, 0)` vẫn sai vì vị trí sai; đọc bằng `get(LITTLE_ENDIAN, 8)` cũng sai vì order sai. Phép truy cập đúng cần **cả vị trí và order**:

```java
long byteOffset = 8L;
int number = segment.get(
        ValueLayout.JAVA_INT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN),
        byteOffset);
```

Đây là fragment trong ngữ cảnh đã có `segment`. Với `getAtIndex`, index được nhân với `layout.byteSize()`; không dùng byte offset như element index. Endianness không thay đổi phép nhân chỉ số.

### 11.2. Nhầm endian với bit order hoặc network-bit-stream encoding

Byte order quyết định **vị trí các byte của một scalar**. Nó **không định nghĩa thứ tự bit trong từng byte**, bit packing của bitfields C hay cách một codec nén dữ liệu. Nếu wire format có các bitfields như “3 bit type + 5 bit flags”, phải dùng thao tác mask/shift theo specification; `withOrder` không tự parse bitfields.

Tương tự, một chuỗi UTF-8 là một chuỗi byte có encoding riêng. Không đảo bytes của ký tự UTF-8 theo `nativeOrder()`. Đối với UTF-16 file, hãy dựa vào BOM hoặc quy định `UTF-16BE`/`UTF-16LE` của format.

## 12. Quy trình ra quyết định khi nhận buffer native hoặc file

Trước khi chọn layout để đọc dữ liệu:

1. **Xác định nguồn:** vùng nhớ C scalar trong cùng process, buffer chứa file, payload network, hay native struct.
2. **Đọc schema:** mỗi field rộng bao nhiêu byte, signed/unsigned, endian, base offset, record stride và padding.
3. **Chọn byte order theo contract:** `nativeOrder()` chỉ cho dữ liệu thực sự dùng native representation; nếu format cố định thì dùng `BIG_ENDIAN`/`LITTLE_ENDIAN` theo tài liệu.
4. **Chọn đúng `ValueLayout`:** `JAVA_SHORT`/`JAVA_INT`/`JAVA_LONG`...; nếu heap `byte[]` hoặc packed data, xem xét layout `*_UNALIGNED`.
5. **Kiểm tra kích thước/bounds/alignment/lifetime:** không cấp phát theo giá trị length chưa validate. Chú ý signedness.
6. **Đọc/ghi bằng layout explicit:** `segment.get(layout, byteOffset)` hoặc `getAtIndex(layout, elementIndex)`; không trộn byte offset và element index.
7. **Đối chiếu golden bytes:** test một giá trị như `0x12345678` để có bytes khác nhau rõ ràng; test cả dữ liệu có byte 0x80 trở lên, length lớn và truncated files.
8. **Kiểm tra trên ít nhất hai môi trường khi có thể:** trên host little-endian là phổ biến, nhưng test endian cố định có thể bảo đảm tính portable ngay cả khi chưa có máy big-endian.
9. **Ghi rõ contract trong API:** đặt tên `bigEndianInt`, `fileOrder`, `nativeIntLayout`; tránh một biến `layout` chung bị tái dùng cho field khác order.

Một API chất lượng có thể định nghĩa:

```java
private static final ValueLayout.OfInt FILE_INT32_BE =
        ValueLayout.JAVA_INT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN);

private static final ValueLayout.OfShort FILE_UINT16_LE =
        ValueLayout.JAVA_SHORT_UNALIGNED
                .withOrder(ByteOrder.LITTLE_ENDIAN);
```

Đây là fragment thuộc một class có imports `ValueLayout`/`ByteOrder`. Các hằng này mã hóa **hợp đồng định dạng tệp**, tránh phụ thuộc platform và tránh đổi layout trong mỗi lần đọc.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Bốn byte `12 34 56 78` được đọc theo big-endian và little-endian cho hai kết quả nào?  
**Đáp án:** Big-endian `0x12345678`, little-endian `0x78563412`. Byte order thay đổi cách **diễn giải** cùng bytes.

**Câu 2.** `ValueLayout.JAVA_INT` có byte order mặc định là gì?  
**Đáp án:** `ByteOrder.nativeOrder()`. Không suy ra luôn little-endian trên mọi JVM.

**Câu 3.** Tệp ghi số 32-bit theo big-endian, ứng dụng chạy trên x86-64 little-endian. Nên dùng `nativeOrder()` để tăng hiệu năng?  
**Đáp án:** Không. File format quy định `BIG_ENDIAN`, nên dùng `ValueLayout.JAVA_INT_UNALIGNED.withOrder(BIG_ENDIAN)` nếu buffer là packed `byte[]`; kết quả đúng quan trọng hơn mặc định native.

**Câu 4.** `MemorySegment.ofArray(new byte[4]).get(ValueLayout.JAVA_INT, 0)` có thể thất bại dù offset 0 và đủ bytes?  
**Đáp án:** Có. Heap segment từ `byte[]` chỉ hỗ trợ maximum alignment 1, trong khi `JAVA_INT` yêu cầu alignment 4. Dùng `JAVA_INT_UNALIGNED` (thêm `withOrder` đúng format).

**Câu 5.** `withOrder(BIG_ENDIAN)` có làm bytes trong segment đổi thứ tự ngay không?  
**Đáp án:** Không. Nó trả layout mới; bytes chỉ được ghi theo order đó khi gọi `set`, hoặc diễn giải theo đó khi `get`.

**Câu 6.** Sau `get(bigEndianLayout, offset)` trả `0x12345678`, có cần `Integer.reverseBytes` để Java có “native int” không?  
**Đáp án:** Không. Java `int` đã là giá trị logic đúng; gọi reverse bytes sẽ đổi bit pattern thành `0x78563412` và gây sai kết quả nếu không có mục tiêu rõ.

**Câu 7.** File có field `uint16` big-endian `A0 B1`, Java `get(JAVA_SHORT_UNALIGNED.withOrder(BIG_ENDIAN), off)` trả giá trị `short` âm. Phải đổi endian?  
**Đáp án:** Không. Endian đã đúng. Hãy dùng `Short.toUnsignedInt` để biểu diễn kiểu không dấu, nhận `0xA0B1`.

**Câu 8.** Một API C cấp phát buffer chứa payload file big-endian. Java nên chọn nativeOrder vì memory được cấp bằng `malloc`?  
**Đáp án:** Không. Cách cấp phát không quyết định byte order của payload; phải dựa vào contract của **bytes đang lưu trong buffer**.

**Câu 9.** `MemorySegment.copy` có tự chuyển mảng int big-endian thành little-endian không?  
**Đáp án:** Không. Nó sao chép bytes. Muốn chuyển order phải decode từng giá trị bằng layout nguồn rồi encode bằng layout đích.

**Câu 10.** Nếu chọn đúng endian cho field 32-bit trong C struct nhưng vẫn đọc sai, bước nào nên kiểm tra tiếp?  
**Đáp án:** Kích thước field và signedness, ABI padding, alignment, byte offset, record stride, segment lifetime và version của struct.

## 14. Ghi nhớ

- **Endian thuộc về dữ liệu**, không thuộc về cái tên “native”, kiểu con trỏ hoặc nơi cấp phát buffer.
- **`BIG_ENDIAN`:** byte quan trọng nhất trước; **`LITTLE_ENDIAN`:** byte ít quan trọng nhất trước; **`nativeOrder()`:** theo nền tảng hiện tại.
- Trong **FFM JDK 22+**, `ValueLayout.JAVA_INT` dùng native order. **`withOrder(...)` tạo layout mới**, còn `MemorySegment` giữ nguyên bytes cho đến khi được ghi.
- **Định dạng file/protocol có endian cố định phải được tôn trọng trên mọi host**, kể cả khi host dùng order khác. Chỉ dùng native order khi hợp đồng native thực sự yêu cầu.
- Với `MemorySegment.ofArray(byte[])`, dùng các `*_UNALIGNED` layouts cho field nhiều byte; endian và alignment là hai điều kiện khác nhau.
- `ByteBuffer` mặc định **BIG_ENDIAN**, không nhất thiết giống FFM `JAVA_INT` mặc định **native order**.
- Muốn chuyển encoding, **đọc theo source order rồi ghi theo destination order**; copy bytes hoặc thay layout không tự chuyển dữ liệu.
- Phải kiểm tra **offset, stride, padding, unsignedness, bounds, lifetime và schema** bên cạnh byte order.

### Tài liệu chính thức

- [Oracle Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): `JAVA_INT` và các layout mặc định theo native order; `order()`, `withOrder(...)`, unaligned layouts.
- [Oracle Java SE 22 — ValueLayout.OfInt](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.OfInt.html): `withOrder` trả typed layout; tương quan byte size và alignment.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `get`, `set`, byte offsets, memory safety, heap alignment, cách dùng layout big-endian.
- [Oracle Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): group/struct layouts, padding, field offsets.
- [Oracle Java SE 22 — ByteBuffer](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/ByteBuffer.html): `order`, mặc định big-endian và thao tác đọc/ghi primitive.
- [Oracle Java SE 22 — ByteOrder](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/ByteOrder.html): `BIG_ENDIAN`, `LITTLE_ENDIAN`, `nativeOrder()`.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API được hoàn thiện từ JDK 22.
