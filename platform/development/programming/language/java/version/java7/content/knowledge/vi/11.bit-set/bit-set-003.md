# Chuyển từ mảng byte hoặc long bằng `BitSet.valueOf` (Java 7+)

> **Chủ đề:** Chuyển dữ liệu bit đang nằm trong `byte[]` hoặc `long[]` thành `java.util.BitSet` bằng các phương thức static `BitSet.valueOf(...)`. Trọng tâm là quy tắc **least-significant bit trước (little-endian theo thứ tự bit trong mỗi phần tử và phần tử có chỉ số thấp trước)**, cách xác định bit index, sự khác nhau giữa dấu của số nguyên và mẫu bit, chuyển ngược bằng `toByteArray()`/`toLongArray()`, dữ liệu zero ở cuối, và bẫy khi truyền/lưu dữ liệu nhị phân. Các phương thức này có từ Java 7 và **vẫn dùng được trong Java 17+**.

## 1. Vì sao cần `BitSet.valueOf`?

`BitSet` là một cấu trúc lưu một tập hợp các **vị trí bit bật/tắt** (true/false) có chỉ số không âm. Thay vì tạo hàng trăm biến `boolean`, ứng dụng có thể dùng:

```java
BitSet flags = new BitSet();
flags.set(0);
flags.set(9);
System.out.println(flags.get(9)); // true
```

Đây là snippet trong class/method đã import `java.util.BitSet`. Một vị trí bit có thể biểu diễn quyền truy cập, trạng thái đã xử lý hoặc một cờ dữ liệu.

Trong thực tế, các bit thường **đã có sẵn** trong một mảng byte hoặc một dãy word 64-bit từ API khác, file nhị phân hoặc giao thức do ứng dụng định nghĩa. Việc gọi `set(index)` cho từng bit vừa dài dòng vừa dễ sai thứ tự. `BitSet.valueOf` chuyển **mẫu bit đã có** thành một `BitSet` mới theo quy tắc thống nhất.

Các trường hợp sử dụng:

- Đọc một bitmap quyền hoặc tập cờ từ `byte[]` do hệ thống đưa vào.
- Chuyển các word `long[]` thành tập vị trí bit để gọi `get`, `set`, `clear`, `cardinality`.
- Phân tích một vùng `ByteBuffer`/`LongBuffer` với cùng quy tắc bit, khi source đã ở dạng buffer.
- Xuất ngược bitmap sang các phần tử nguyên thủy để lưu/trao đổi dữ liệu **khi hai phía cùng thống nhất quy ước**.

**Giới hạn trách nhiệm:** `BitSet.valueOf` diễn giải **bit pattern**. Nó không xác minh dữ liệu có đúng phiên bản protocol, số lượng cờ hợp lệ hay quyền truy cập nào được phép. Những quy tắc này vẫn phải do ứng dụng kiểm tra.

## 2. Những overload cần biết và phiên bản

Trong Java SE 17, các overload liên quan gồm:

```java
public static BitSet valueOf(byte[] bytes);
public static BitSet valueOf(long[] longs);
public static BitSet valueOf(ByteBuffer bb);
public static BitSet valueOf(LongBuffer lb);
```

Đây là **chữ ký rút gọn từ API**, không phải code định nghĩa lại các method. Cả bốn phương thức đều có từ **Java 7**. Hai overload dùng buffer nhận kiểu trong `java.nio`.

| Phương thức | Dữ liệu đầu vào | Quy tắc chia nhóm | Kết quả |
| --- | --- | --- | --- |
| `BitSet.valueOf(byte[])` | Mỗi phần tử 8 bit | Bit thấp trong byte trước, phần tử `[0]` trước | `BitSet` mới |
| `BitSet.valueOf(long[])` | Mỗi phần tử 64 bit | Bit thấp trong long trước, phần tử `[0]` trước | `BitSet` mới |
| `BitSet.valueOf(ByteBuffer)` | Các byte còn lại từ `position` đến `limit` | Giống `byte[]` | `BitSet` mới |
| `BitSet.valueOf(LongBuffer)` | Các long còn lại từ `position` đến `limit` | Giống `long[]` | `BitSet` mới |

**Lưu ý cú pháp:** `valueOf` ở đây là **static factory method** của `BitSet`, không phải `byte[].valueOf(...)` hoặc method trên một instance. Muốn gọi cần import:

```java
import java.util.BitSet;
```

Khi đầu vào hợp lệ, phương thức tạo ra một đối tượng `BitSet` **độc lập với mảng/buffer đầu vào** về mặt trạng thái các bit. Việc thay đổi mảng/buffer sau đó không làm những bit đã chuyển đổi thay đổi theo.

## 3. Công thức chuyển `byte[]` sang bit index

Java `byte` có **8 bit** nhưng là số có dấu ở mức biểu diễn giá trị (`-128` đến `127`). `BitSet.valueOf(byte[])` không quan tâm đó là số dương hay âm: nó đọc **8 bit của từng phần tử**.

Với phần tử `bytes[i]`:

- Các bit trong phần tử có offset `k = 0..7`, trong đó `k=0` là bit có trọng số `2^0`, `k=7` là bit có trọng số `2^7`.
- Nếu bit `k` của `bytes[i]` bật, `BitSet` sẽ có bit toàn cục ở chỉ số **`8 * i + k`**.
- Phần tử `bytes[0]` giữ các vị trí `0..7`, `bytes[1]` giữ `8..15`, `bytes[2]` giữ `16..23`…

Biểu diễn cùng quy tắc bằng một bảng:

| Phần tử | Vị trí tương ứng trong BitSet |
| --- | --- |
| `bytes[0]` | `0..7` |
| `bytes[1]` | `8..15` |
| `bytes[2]` | `16..23` |
| `bytes[3]` | `24..31` |
| `bytes[i]` | `8*i..8*i+7` |

Điều này thường được mô tả là **little-endian** đối với cách chuyển bit. Nó không có nghĩa `BitSet` dự đoán “endianness của một giao thức” từ dữ liệu; bạn phải **xác nhận giao thức ngoài** đang dùng cùng quy ước.

### 3.1. Ví dụ với một byte

```java
BitSet bits = BitSet.valueOf(new byte[] {0x05});
System.out.println(bits); // {0, 2}
```

Đây là snippet với import `java.util.BitSet`. `0x05 = 0000_0101` có bit `0` và bit `2` bật. `BitSet` đánh số từ bit có trọng số nhỏ nhất, nên in `{0, 2}`.

Với bit dấu của byte:

```java
BitSet signBit = BitSet.valueOf(new byte[] {(byte) 0x80});
System.out.println(signBit); // {7}
```

`0x80` có bit `7` bật, nhưng literal số nguyên `0x80` là `128`, vượt phạm vi của `byte`. Cast `(byte)` có chủ đích biểu diễn đúng mẫu 8 bit. Đó là lý do giá trị `(byte) 0x80` được in như `-128` khi chuyển sang dạng số có dấu, nhưng `BitSet` vẫn bật bit `7`, **không có khái niệm “bit âm”**.

### 3.2. Hai byte không phải hai bit

```java
BitSet bits = BitSet.valueOf(new byte[] {0x01, 0x02});
System.out.println(bits); // {0, 9}
```

`bytes[0] = 0x01` bật chỉ số 0. `bytes[1] = 0x02` bật bit offset 1 của byte thứ hai, nên chỉ số toàn cục là `8 + 1 = 9`. Một lỗi rất phổ biến là tưởng hai phần tử mảng tương ứng đúng hai vị trí 0 và 1 trong `BitSet`; thực tế mỗi phần tử chứa **8 vị trí**.

## 4. Chương trình đầy đủ: `valueOf(byte[])` với byte có dấu

Lưu thành `BitSetBytesDemo.java`:

```java
import java.util.Arrays;
import java.util.BitSet;

public class BitSetBytesDemo {
    public static void main(String[] args) {
        byte[] input = {(byte) 0x81, (byte) 0x02, (byte) 0x80};
        BitSet flags = BitSet.valueOf(input);

        System.out.println("bits=" + flags);
        System.out.println("length=" + flags.length());
        System.out.println("count=" + flags.cardinality());
        System.out.println("bytes=" + Arrays.toString(flags.toByteArray()));

        input[0] = 0;
        System.out.println("copied=" + flags.get(0));
    }
}
```

Biên dịch và chạy JDK 17+:

```bash
javac -encoding UTF-8 --release 17 BitSetBytesDemo.java
java BitSetBytesDemo
```

Stdout đã được kiểm tra bằng `javac`/`java`:

```text
bits={0, 7, 9, 23}
length=24
count=4
bytes=[-127, 2, -128]
copied=true
```

**Giải từng phần:**

- `input[0] = (byte) 0x81`, nhị phân `1000_0001`, nên bật các bit **0, 7**.
- `input[1] = (byte) 0x02`, nhị phân `0000_0010`, nên bật chỉ số `8+1 = 9`.
- `input[2] = (byte) 0x80`, nhị phân `1000_0000`, nên bật chỉ số `16+7 = 23`.
- `flags.length()` bằng **24**, bởi bit cao nhất đang bật là 23 và `length()` trả vị trí cao nhất + 1.
- `flags.cardinality()` bằng **4**, vì có đúng bốn bit bật. `length` không phải số lượng bit bật.
- `flags.toByteArray()` tạo mảng mới có mẫu bit tương ứng; Java in `0x81` thành `-127` và `0x80` thành `-128` do `byte` có dấu.
- Sau `input[0] = 0`, bit 0 trong `flags` vẫn bật, nên `copied=true`. `valueOf` không duy trì một view sống cùng mảng gốc.

Dù mảng nguồn chứa số âm, dữ liệu bitmap **không hề bị từ chối**. Các bit vẫn được nhận đầy đủ, kể cả bit dấu của byte cuối.

## 5. Công thức chuyển `long[]` sang bit index

Với `long[]`, mỗi phần tử là một **word 64 bit**:

- `longs[0]` giữ các vị trí bit `0..63`.
- `longs[1]` giữ `64..127`.
- `longs[2]` giữ `128..191`.
- Bit ở offset `k = 0..63` trong `longs[i]` ánh xạ vào **`64*i+k`**.

| Phần tử | Vùng vị trí trong BitSet |
| --- | --- |
| `longs[0]` | `0..63` |
| `longs[1]` | `64..127` |
| `longs[2]` | `128..191` |
| `longs[i]` | `64*i..64*i+63` |

Cũng như `byte[]`, Java `long` là kiểu có dấu, nhưng `BitSet` dùng **mẫu 64 bit** chứ không xem một số âm là dữ liệu không hợp lệ.

Ví dụ:

```java
BitSet flags = BitSet.valueOf(new long[] {1L, 2L});
System.out.println(flags); // {0, 65}
```

`longs[0]=1L` bật bit 0; `longs[1]=2L` bật bit offset 1 của word thứ hai, tức **bit toàn cục 65**.

### 5.1. `Long.MIN_VALUE` là bit nào?

`Long.MIN_VALUE` có mẫu bit 64-bit mà chỉ **bit 63** bật (bit dấu). Vì vậy:

```java
BitSet oneWord = BitSet.valueOf(new long[] {Long.MIN_VALUE});
System.out.println(oneWord); // {63}
```

Đây là snippet. Nếu `Long.MIN_VALUE` nằm tại `longs[1]`, bit bật sẽ là **64 + 63 = 127**. Không có chỉ số âm.

### 5.2. `-1L` chứa 64 bit bật

Biểu diễn bù hai của `-1L` gồm 64 bit 1:

```java
BitSet all = BitSet.valueOf(new long[] {-1L});
System.out.println(all.cardinality()); // 64
System.out.println(all.get(63));       // true
System.out.println(all.get(64));       // false
```

Đây là snippet. Bit 64 không thuộc word đầu (chỉ có các chỉ số 0..63), nên false. Đừng nhầm phép diễn giải bit thành phép diễn giải dấu/độ lớn của số nguyên.

## 6. Chương trình đầy đủ: nhiều word và bit dấu của `long`

Lưu thành `BitSetLongsDemo.java`:

```java
import java.util.Arrays;
import java.util.BitSet;

public class BitSetLongsDemo {
    public static void main(String[] args) {
        long[] input = {(1L << 5) | 1L, Long.MIN_VALUE};
        BitSet flags = BitSet.valueOf(input);

        System.out.println("bits=" + flags);
        System.out.println("length=" + flags.length());
        System.out.println("count=" + flags.cardinality());
        System.out.println("words=" + Arrays.toString(flags.toLongArray()));

        BitSet signed = BitSet.valueOf(new long[] {-1L});
        System.out.println("allBitsCount=" + signed.cardinality());
        System.out.println("contains0=" + signed.get(0));
        System.out.println("contains63=" + signed.get(63));
        System.out.println("contains64=" + signed.get(64));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 BitSetLongsDemo.java
java BitSetLongsDemo
```

Stdout đã xác minh:

```text
bits={0, 5, 127}
length=128
count=3
words=[33, -9223372036854775808]
allBitsCount=64
contains0=true
contains63=true
contains64=false
```

Giải thích:

- `(1L << 5) | 1L` bật bit 5 và bit 0 trong word thứ nhất; giá trị word bằng **33**.
- `Long.MIN_VALUE` ở `input[1]` bật bit 63 của **word thứ hai**, tương ứng vị trí toàn cục **127**.
- Vì bit lớn nhất là 127, `length() = 128`; có ba bit bật nên `cardinality() = 3`.
- `toLongArray()` trả lại biểu diễn theo các word: `33` và số âm `Long.MIN_VALUE`. Dấu âm chỉ là cách Java hiển thị giá trị `long`.
- `BitSet.valueOf(new long[]{-1L})` bật chính xác các vị trí `0..63`, tổng cộng 64.

**Đặc điểm phiên bản:** `BitSet.valueOf(long[])` đã được bổ sung từ Java 7 và không cần thư viện ngoài JDK. Các phép `<<` và `|` dùng ở đây là phép toán dịch bit/bitwise OR trên `long`, **khác với ký hiệu `|` dùng trong cú pháp multi-catch**.

## 7. Liên hệ giữa mảng byte và mảng long

Một word `long` chứa **64 bit = 8 byte**. Nếu cả hai loại mảng dùng **cùng quy ước little-endian**, chúng có thể biểu diễn cùng một `BitSet`.

Ví dụ một tập cờ bật vị trí **0, 9, 70**:

- Vị trí 0: byte thứ 0, offset 0; long thứ 0, offset 0.
- Vị trí 9: byte thứ 1, offset 1; long thứ 0, offset 9.
- Vị trí 70: byte thứ 8, offset 6; long thứ 1, offset 6.

Khi xuất bằng `toByteArray()`, byte thứ 8 sẽ chứa `0x40` (64), còn byte thứ 1 là `0x02` và byte thứ 0 là `0x01`. Khi xuất bằng `toLongArray()`, word thứ nhất là `2^0 + 2^9 = 513`, word thứ hai là `2^6 = 64`.

**Bảng đối chiếu nhanh:**

| Bit index | `byte[]`: phần tử / offset | `long[]`: phần tử / offset |
| --- | --- | --- |
| 0 | `[0]` / 0 | `[0]` / 0 |
| 7 | `[0]` / 7 | `[0]` / 7 |
| 8 | `[1]` / 0 | `[0]` / 8 |
| 9 | `[1]` / 1 | `[0]` / 9 |
| 63 | `[7]` / 7 | `[0]` / 63 |
| 64 | `[8]` / 0 | `[1]` / 0 |
| 70 | `[8]` / 6 | `[1]` / 6 |
| 127 | `[15]` / 7 | `[1]` / 63 |

Điều này cũng giải thích tại sao **thứ tự word** khác với **thứ tự byte**: tăng một phần tử `long[]` nhảy qua 64 bit, còn tăng một phần tử `byte[]` nhảy qua 8 bit.

Không tự làm phép chuyển dựa trên **giá trị thập phân có dấu** của từng byte/long. Mục tiêu là bảo toàn **mẫu bit**.

## 8. Chuyển ngược và kiểm chứng round-trip

Hai API đi cùng `valueOf` là:

```java
byte[] bytes = flags.toByteArray();
long[] words = flags.toLongArray();
```

Đây là snippet với `BitSet flags` đã định nghĩa. Các array được tạo mới theo thứ tự **little-endian** tương ứng.

Nếu bắt đầu từ một `BitSet` rồi xuất thành `byte[]` hoặc `long[]`, dùng `valueOf` để nhập lại, ta nên nhận được **cùng tập bit bật**:

```java
BitSet a = BitSet.valueOf(original.toByteArray());
BitSet b = BitSet.valueOf(original.toLongArray());

boolean sameBytes = a.equals(original);
boolean sameLongs = b.equals(original);
```

Đây là snippet. `equals` so sánh nội dung bit theo logic, không so sánh danh tính đối tượng.

### 8.1. Chương trình chạy được: round-trip và bỏ số 0 ở cuối

Lưu thành `BitSetRoundTripDemo.java`:

```java
import java.util.Arrays;
import java.util.BitSet;

public class BitSetRoundTripDemo {
    public static void main(String[] args) {
        BitSet original = new BitSet();
        original.set(0);
        original.set(9);
        original.set(70);

        byte[] bytes = original.toByteArray();
        long[] words = original.toLongArray();

        System.out.println("bytes=" + Arrays.toString(bytes));
        System.out.println("words=" + Arrays.toString(words));
        System.out.println("fromBytes=" + BitSet.valueOf(bytes).equals(original));
        System.out.println("fromLongs=" + BitSet.valueOf(words).equals(original));

        original.clear(70);
        System.out.println("trimmedBytes=" + Arrays.toString(original.toByteArray()));
        System.out.println("trimmedLongs=" + Arrays.toString(original.toLongArray()));
        System.out.println("trailingZerosSame=" +
            BitSet.valueOf(new byte[] {1, 0, 0}).equals(
                BitSet.valueOf(new byte[] {1})));
        System.out.println("zeroWords=" +
            Arrays.toString(BitSet.valueOf(new long[] {0L, 0L}).toLongArray()));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 BitSetRoundTripDemo.java
java BitSetRoundTripDemo
```

Stdout đã được kiểm chứng:

```text
bytes=[1, 2, 0, 0, 0, 0, 0, 0, 64]
words=[513, 64]
fromBytes=true
fromLongs=true
trimmedBytes=[1, 2]
trimmedLongs=[513]
trailingZerosSame=true
zeroWords=[]
```

**Những điều bắt buộc hiểu:**

- `toByteArray` cần 9 byte để chứa vị trí bit cao nhất 70 (byte thứ 8), nên output có các byte zero nằm **ở giữa**.
- `toLongArray` chỉ cần hai word, với giá trị `513` và `64`.
- `fromBytes=true` và `fromLongs=true` chứng minh cả hai biểu diễn tái tạo cùng **tập bit**, không nhất thiết cùng metadata/độ dài mảng nguồn gốc.
- Xóa bit 70 khiến bit cao nhất còn bật là 9; do đó `toByteArray()` rút còn hai byte `[1, 2]`, `toLongArray()` còn một word `[513]`.
- `new byte[]{1,0,0}` và `new byte[]{1}` có cùng nội dung bit bật: bit 0. `BitSet` không lưu thông tin “đã có ba byte nguồn”.
- `new long[]{0L,0L}` tạo tập bit trống; `toLongArray()` trả mảng rỗng `[]`.

**Điểm dễ nhầm:** round-trip `BitSet → byte[] → BitSet` bảo toàn **các bit bật**, nhưng round-trip `byte[] gốc → BitSet → byte[]` **không nhất thiết bảo toàn số byte ban đầu** nếu byte cuối toàn 0. `BitSet` là tập bit, không phải container nguyên xi của độ dài buffer nguồn.

## 9. `length()`, `cardinality()`, `size()` và độ dài mảng khác nhau

Để tránh sai khi chuyển đổi, cần phân biệt:

- `length()`: **vị trí bit cao nhất đang bật + 1**; nếu không có bit nào bật, trả 0.
- `cardinality()`: số lượng bit có giá trị true.
- `size()`: số bit mà **biểu diễn nội bộ** hiện có thể chứa; không phải số bit đang bật, cũng không phải cam kết định dạng dữ liệu.
- `toByteArray().length`: số byte tối thiểu để chứa vị trí bit cao nhất bật, bằng `ceil(length()/8)` nếu có bit bật.
- `toLongArray().length`: số word tối thiểu để chứa vị trí bit cao nhất bật, bằng `ceil(length()/64)` nếu có bit bật.

Nếu tập bit rỗng, cả `toByteArray()` và `toLongArray()` trả array **độ dài 0**; không nhất thiết trả một array gồm toàn zero với độ dài mà bạn đã cấp ở input.

**Hệ quả thực tế:** không dùng `BitSet.size()` để làm số byte phải ghi ra file hay network. Đây là chi tiết capacity của implementation, còn dữ liệu serialize theo `toByteArray()`/`toLongArray()` dựa trên bit thực sự bật.

### 9.1. Những số 0 bị “mất” ở đâu?

Mảng nguồn `new byte[]{1, 0, 0}` có thêm hai byte zero ở **cuối dãy**. Sau khi nhập vào BitSet, cả hai byte này không chứa bit bật nào; khi xuất ngược, chúng không được giữ lại. Nhưng với `new byte[]{1, 0, 2}`, byte zero **ở giữa** vẫn xuất hiện nếu xuất mảng bởi byte thứ ba có bit bật.

Đây là lý do phải tách biệt giữa **nội dung bitmap logic** và **chiều dài khung dữ liệu ngoài**.

## 10. Xuất mảng cố định độ dài khi giao thức yêu cầu

Nếu hệ thống gửi đúng 4 byte hoặc 16 byte cho một trường bitmap, `toByteArray()` không tự giữ chiều dài ấy. Bạn cần **quy định số byte cố định ở tầng serialization**, đồng thời kiểm tra bitset không vượt phạm vi.

Một ví dụ nhỏ có kiểm tra lỗi rõ ràng:

Lưu thành `BitSetFixedWidthDemo.java`:

```java
import java.util.Arrays;
import java.util.BitSet;

public class BitSetFixedWidthDemo {
    static byte[] encode(BitSet bits, int widthBytes) {
        if (widthBytes < 0 || bits.length() > (long) widthBytes * Byte.SIZE) {
            throw new IllegalArgumentException("bit set does not fit");
        }
        return Arrays.copyOf(bits.toByteArray(), widthBytes);
    }

    public static void main(String[] args) {
        BitSet flags = BitSet.valueOf(new byte[] {1, 0, 0});
        System.out.println("fixed=" + Arrays.toString(encode(flags, 4)));

        BitSet tooWide = new BitSet();
        tooWide.set(32);
        try {
            encode(tooWide, 4);
        } catch (IllegalArgumentException error) {
            System.out.println("error=" + error.getMessage());
        }

        try {
            BitSet.valueOf((byte[]) null);
        } catch (NullPointerException error) {
            System.out.println("nullInput=" + error.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 BitSetFixedWidthDemo.java
java BitSetFixedWidthDemo
```

Stdout đã kiểm chứng:

```text
fixed=[1, 0, 0, 0]
error=bit set does not fit
nullInput=NullPointerException
```

**Phân tích:**

1. `flags` chỉ bật bit 0. `toByteArray()` là `[1]`, nhưng `Arrays.copyOf(..., 4)` **đệm ba byte 0** vào cuối để khớp chiều dài protocol.
2. Nếu bật bit 32, không thể chứa trong bốn byte (chỉ đủ vị trí 0..31). `encode` từ chối thay vì âm thầm cắt mất bit.
3. So sánh sử dụng `(long) widthBytes * Byte.SIZE` để tránh overflow khi nhân hai giá trị `int` lớn. `Byte.SIZE` là hằng số 8.
4. `BitSet.valueOf((byte[]) null)` ném NPE. Phải cast kiểu khi minh họa với null vì có **nhiều overload `valueOf`**; biểu thức `valueOf(null)` không đủ chỉ rõ lựa chọn nào.

**Không lấy chương trình này làm định dạng protocol mặc định** nếu một phía dùng big-endian hoặc có header/version/checksum riêng. Đây là kỹ thuật xuất **đúng chiều dài**, không tự thay thế tài liệu đặc tả nhị phân giữa các hệ thống.

### 10.1. Mỗi bên cần thống nhất thêm điều gì?

Khi lưu/truyền bitmap, hãy xác nhận rõ:

- Số bit tối đa và số byte/word được phép.
- Cách đánh số bit: bit 0 là cờ nào, bit 7 là cờ nào, bit 64 là cờ nào.
- Byte order/word order và cách đóng gói từ dữ liệu bên ngoài.
- Định dạng có giữ zero ở cuối không, hoặc truyền riêng chiều dài gốc?
- Cách xử lý byte thừa, bit ngoài phạm vi và dữ liệu null.
- Giới hạn kích thước đầu vào trước khi cấp phát memory từ nguồn không tin cậy.
- Tính tương thích khi nâng phiên bản giao thức hoặc thêm cờ mới.

`BitSet.valueOf` giúp thực hiện **bước chuyển bit**, không thay việc thiết kế và xác nhận protocol.

## 11. Ngoài mảng: `valueOf(ByteBuffer)` và `valueOf(LongBuffer)`

Khi làm việc với NIO, bạn có thể đang có `ByteBuffer` hoặc `LongBuffer` thay vì array. Hai overload:

```java
BitSet fromBytes = BitSet.valueOf(byteBuffer);
BitSet fromWords = BitSet.valueOf(longBuffer);
```

Đây là snippet với hai biến buffer đã có. Các giá trị **được lấy trong phần còn lại của buffer** — khoảng từ `position` đến `limit`, không tự đọc mọi phần tử trong toàn bộ capacity.

- `BitSet.valueOf(ByteBuffer)` coi mỗi byte còn lại là 8 bit, byte đầu tiên trong vùng remaining có các bit `0..7`.
- `BitSet.valueOf(LongBuffer)` coi mỗi long còn lại là 64 bit, word đầu tiên có các bit `0..63`.
- Các method này **không thay đổi `position`/`limit`** của buffer đầu vào.
- Các bit được sao chép vào BitSet mới; không duy trì live view của buffer.
- `BitSet.valueOf(ByteBuffer)` xác định thứ tự bit **bên trong các byte** theo quy tắc như byte[], không để thuộc tính `ByteBuffer.order()` tự diễn dịch thành big-endian bitmap.

### 11.1. Ví dụ có thể chạy: region, position, limit và copy

Lưu thành `BitSetBuffersDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.LongBuffer;
import java.util.BitSet;

public class BitSetBuffersDemo {
    public static void main(String[] args) {
        ByteBuffer bytes = ByteBuffer.wrap(new byte[] {99, 1, 2, 4});
        bytes.position(1);
        bytes.limit(3);
        bytes.order(ByteOrder.BIG_ENDIAN);
        BitSet bits = BitSet.valueOf(bytes);

        System.out.println("byteBits=" + bits);
        System.out.println("bytePosition=" + bytes.position());
        System.out.println("byteLimit=" + bytes.limit());
        bytes.put(1, (byte) 0);
        System.out.println("byteCopied=" + bits.get(0));

        LongBuffer words = LongBuffer.wrap(new long[] {99L, 1L, Long.MIN_VALUE, 55L});
        words.position(1);
        words.limit(3);
        BitSet longBits = BitSet.valueOf(words);

        System.out.println("longBits=" + longBits);
        System.out.println("longPosition=" + words.position());
        System.out.println("longLimit=" + words.limit());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 BitSetBuffersDemo.java
java BitSetBuffersDemo
```

Stdout đã kiểm chứng:

```text
byteBits={0, 9}
bytePosition=1
byteLimit=3
byteCopied=true
longBits={0, 127}
longPosition=1
longLimit=3
```

**Đọc ví dụ:**

- `ByteBuffer` ban đầu có bốn byte, nhưng `position=1` và `limit=3` nghĩa là chỉ hai byte ở vị trí **1, 2** tham gia chuyển đổi, có giá trị `1, 2`. Vì vậy bit bật là `0` và `9`. Byte `99` ở trước position và byte `4` ở sau limit không tham gia.
- `order(ByteOrder.BIG_ENDIAN)` ở ví dụ giúp chứng minh rằng `valueOf(ByteBuffer)` không đảo cách đánh số bit theo “big-endian mode” của buffer.
- Sau khi chuyển, `position` vẫn là 1, `limit` vẫn là 3; đồng thời sửa phần tử byte nguồn tại index 1 không làm tắt bit 0 đã chuyển vào BitSet (`byteCopied=true`).
- `LongBuffer` chọn hai word tại vị trí 1 và 2, tương ứng `1L` và `Long.MIN_VALUE`. Hai bit bật là **0** và **127**. Position và limit giữ nguyên.

### 11.2. Khác biệt với việc đọc một giá trị `long` từ byte buffer

`ByteBuffer.getLong()` diễn giải **tám byte** thành một giá trị `long` theo byte order cấu hình của buffer. `BitSet.valueOf(ByteBuffer)` lại coi **từng byte** như những nhóm 8 bit riêng theo quy tắc `BitSet`.

Nếu ứng dụng chủ động parse `long` từ một `ByteBuffer` big-endian rồi đưa nó vào `BitSet.valueOf(long[])`, kết quả có thể khác với việc đưa trực tiếp tám byte vào `BitSet.valueOf(byte[])`. Muốn hai cách phù hợp, phải chuẩn hóa byte/word order theo protocol trước khi chuyển đổi.

Đừng dựa vào byte order mặc định của một runtime hoặc định dạng binary để suy đoán. Hãy viết test với các byte **không đối xứng** (ví dụ `1, 2` thay vì toàn 0) để bắt lỗi đảo thứ tự.

## 12. Snapshot và tính độc lập của dữ liệu đầu vào

`valueOf` không “gắn” `BitSet` vào mảng nguồn. Trong `BitSetBytesDemo`, sau khi gọi `valueOf(input)` rồi sửa `input[0]`, nội dung `flags` không đổi.

Điều ngược lại cũng quan trọng: `toByteArray()` và `toLongArray()` trả về **mảng chứa dữ liệu biểu diễn được tạo cho lời gọi**, không phải một cơ chế để bạn sửa live state của BitSet qua array đó. Nếu muốn bật/tắt bit, hãy gọi `set`/`clear`/`flip` trên chính `BitSet`.

### 12.1. Tại sao cần chú ý trong code nhiều thread?

`BitSet` là **mutable** và không có cam kết thread-safe cho các thay đổi đồng thời không được đồng bộ. Việc factory trả một snapshot độc lập với array nguồn **không** khiến mọi thao tác cập nhật BitSet từ nhiều thread đều an toàn. Nếu chia sẻ một BitSet đang bị sửa giữa các thread, dùng đồng bộ hoặc thiết kế chia sẻ phù hợp với yêu cầu nhất quán.

Ở đầu vào không tin cậy, cũng cần giới hạn kích thước mảng/buffer trước khi tạo BitSet để tránh mức sử dụng bộ nhớ ngoài dự kiến. `valueOf` không là một bộ kiểm tra an ninh cho data format.

## 13. Lỗi thường gặp với byte có dấu

Java `byte` chỉ biểu diễn trực tiếp các giá trị `-128..127`. Một số byte trong định dạng binary có bit cao nhất bật nên in ra thành số âm.

Ví dụ:

```java
byte signed = (byte) 0xFF; // Giá trị Java là -1.
int unsigned = signed & 0xFF; // 255.
BitSet bits = BitSet.valueOf(new byte[] {signed});
```

Đây là snippet. `0xFF` có đủ tám bit bật nên kết quả có các vị trí `0..7`. Phép `& 0xFF` có ích nếu cần **hiển thị hoặc xử lý byte như số nguyên không dấu**, nhưng **không bắt buộc** để `BitSet.valueOf` đọc đúng bit: factory đã định nghĩa ánh xạ qua mẫu 8 bit.

Đừng chuyển một byte âm thành chuỗi thập phân rồi parse ngược và kỳ vọng bảo toàn protocol nếu không có định dạng rõ. Hãy giữ dữ liệu ở dạng `byte[]`/`ByteBuffer` và dùng bitwise operations đúng chỗ.

### 13.1. Dịch bit trên byte cần nhớ phép nâng kiểu

Trong Java, toán tử dịch trên `byte` thường nâng toán hạng thành `int`. Khi viết tiện ích tự đọc từng bit, một cách minh bạch là:

```java
int unsigned = bytes[i] & 0xFF;
boolean set = (unsigned & (1 << offset)) != 0;
```

Đây là snippet với `byte[] bytes`, `i` là chỉ số phần tử hợp lệ và `offset = 0..7`. Nhưng nếu mục tiêu chỉ là chuyển **toàn bộ mảng**, dùng `BitSet.valueOf(bytes)` đơn giản và ít sai hơn.

### 13.2. Đọc little-endian không phải đảo tất cả bit

“Little-endian” ở đây có nghĩa byte đầu chứa các chỉ số thấp và bit thấp trong mỗi byte ứng với chỉ số thấp. Nó **không** yêu cầu dùng `Integer.reverse` hay đảo chuỗi nhị phân của từng phần tử trước khi gọi `valueOf`. Tự đảo thêm một lần thường khiến bit 0 trở thành bit 7 hoặc đổi thứ tự nhóm, tạo lỗi rất khó thấy khi dữ liệu chỉ toàn 0.

## 14. Lỗi thường gặp với `long` có dấu và dịch bit

`Long.MIN_VALUE` là mẫu có bit dấu bật; `-1L` là mẫu toàn bit 1. `BitSet` đánh số bit từ 0, nên không có bit “-63” hoặc “bit âm”.

Ví dụ:

```java
long word = 1L << 63; // Long.MIN_VALUE.
BitSet flags = BitSet.valueOf(new long[] {word});
System.out.println(flags.get(63)); // true
```

Đây là snippet. Về biểu diễn số, word là số âm; về biểu diễn bit, nó có đúng bit 63 bật.

**Cẩn thận khi tạo mask:** sử dụng `1L << k` để thao tác với word 64-bit, không dùng `1 << k` khi `k` có thể đến 63. `1` là `int` 32-bit; ngữ nghĩa số bit dịch của `int` khác `long` và sẽ tạo mask sai khi tính bit cao.

Tuy nhiên, nếu đã có cả mảng `long[]`, không cần tự tách từng mask rồi gọi `BitSet.set` — `valueOf(longs)` thực hiện chuyển đổi cho toàn bộ mẫu bit.

## 15. `BitSet` có giống một mảng `boolean[]` cố định không?

Không hoàn toàn.

- `boolean[]` giữ **độ dài do caller cấp** ngay cả nếu tất cả phần tử false.
- `BitSet` lưu tập vị trí true với khả năng mở rộng. `length()` gắn với bit cao nhất true, **không phải độ dài logic ban đầu của bài toán**.
- `BitSet` rất hữu ích cho các tập bit tương đối lớn, phép tập hợp như `and`, `or`, `xor` hoặc duyệt bit bật bằng `nextSetBit`.
- Một `BitSet` tạo từ `byte[]`/`long[]` không lưu độ dài gốc của array trong một trường contract có thể truy xuất; số zero ở cuối không được phân biệt.

Nếu bài toán cần đúng 128 cờ (kể cả tất cả đều false), ứng dụng phải giữ **độ dài 128** như một thông tin riêng hoặc theo đặc tả protocol, không suy ra từ `flags.length()`.

Nếu mỗi bit biểu diễn một **trạng thái đa giá trị** hoặc cần giữ metadata riêng, dùng BitSet có thể không phù hợp. Lựa chọn cấu trúc dữ liệu theo hợp đồng hơn là chỉ tối ưu vài byte bộ nhớ.

## 16. Bảng nhận diện nhanh các sai lầm

| Hiểu hoặc viết sai | Vì sao không đúng | Hướng đúng |
| --- | --- | --- |
| `bytes[1]` là bit 1 | Mỗi byte chứa 8 bit | Byte 1 ánh xạ vào bit 8..15 |
| `longs[1]` là bit 1 | Mỗi long chứa 64 bit | Long 1 ánh xạ vào bit 64..127 |
| `0x80` là byte dương 128 | Java byte là signed | Dùng `(byte) 0x80`; bit 7 vẫn bật |
| `Long.MIN_VALUE` biểu diễn “bit âm” | BitSet có chỉ số không âm | Mẫu bit Long.MIN_VALUE bật bit 63 |
| `valueOf` thay đổi mảng đầu vào | Factory tạo BitSet độc lập | Mảng đầu vào không trở thành live view |
| Sửa `toByteArray()[i]` là sửa BitSet | Mảng xuất ra không phải view cập nhật trực tiếp | Dùng `set`/`clear`/`flip` |
| `length() == cardinality()` | Một cái là bit cao nhất + 1, một cái đếm bit true | Dùng đúng method |
| `size()` bằng kích thước dữ liệu serialize | `size` nói về capacity nội bộ | Dùng output array length và protocol |
| Xuất ngược phải giữ mọi byte zero cuối | BitSet không lưu độ dài input | Truyền length riêng hoặc pad đúng width |
| `ByteBuffer.valueOf` đọc toàn bộ capacity | Chỉ đọc vùng remaining | Kiểm tra `position` và `limit` |
| `ByteBuffer.order(BIG_ENDIAN)` đảo bit của BitSet | `valueOf(ByteBuffer)` có quy tắc byte/bit riêng | Chuyển byte order chủ động ở tầng protocol |
| Dùng `1 << 63` tạo bit cao trên long | `1` là int 32-bit | Dùng `1L << 63` |
| Đọc dữ liệu nhị phân ngoài không kiểm tra độ dài | Dễ lỗi dữ liệu, lãng phí RAM hoặc sai schema | Validate kích thước/range/version trước |
| Dùng BitSet mutable đồng thời không đồng bộ | Không có bảo đảm mọi mutation thread-safe | Đồng bộ hoặc dùng thiết kế bất biến/chia ownership |
| Truyền `BitSet.valueOf(null)` để thử null | Có nhiều overload nên lời gọi mơ hồ | Cast rõ kiểu như `(byte[]) null` |
| Tự tin rằng mọi protocol bitmap đều little-endian | Protocol bên ngoài có thể khác | Chuẩn hóa endian theo đặc tả trước |

## 17. Checklist trước khi dùng `valueOf` trong sản phẩm

1. **Dữ liệu gốc là gì?** `byte[]`, `long[]`, `ByteBuffer`, `LongBuffer` hay một định dạng file/network khác?
2. **Bit numbering có thống nhất không?** Bit 0 tương ứng cờ nào; offset trong byte/long được đánh theo thứ tự nào?
3. **Nguồn có big-endian không?** Nếu có, chuyển sang thứ tự mong muốn trước khi dùng `BitSet.valueOf`.
4. **Số bit logic là bao nhiêu?** Có cần lưu riêng chiều dài kể cả các bit cuối đều 0?
5. **Phương thức xuất nào đúng?** `toByteArray` hay `toLongArray`, và có cần pad đúng size không?
6. **Giới hạn dữ liệu đã được kiểm tra chưa?** Không để input quá lớn hoặc bật bit vượt phạm vi mà protocol không cho phép.
7. **Có cần kiểm tra giá trị null không?** `valueOf` không dùng null làm mã hóa cho “tập rỗng”.
8. **Có coi âm là lỗi không?** Với bit pattern, byte/long âm vẫn hợp lệ; đừng tự từ chối.
9. **Có chia sẻ BitSet mutable cho nhiều luồng không?** Cần cơ chế đồng bộ thích hợp.
10. **Đã có test cho các ranh giới 7/8, 63/64, 127/128 và trailing zero chưa?**
11. **Đã test round-trip theo chuẩn ngoài chưa?** `BitSet` có thể round-trip logic nhưng không giữ nguyên frame length.
12. **Phiên bản Java có đúng không?** Các overload valueOf trong bài có từ Java 7, chạy được trên JDK 17+; lệnh biên dịch các demo đặt `--release 17` rõ ràng.

## 18. Bài tập thực hành có đáp án

**Bài 1.** `BitSet.valueOf(new byte[]{0x01, 0x02})` bật các vị trí nào?  
**Đáp án:** `0` và `9`, không phải 0 và 1.

**Bài 2.** `BitSet.valueOf(new byte[]{(byte)0x80})` có `cardinality` và `length` bằng bao nhiêu?  
**Đáp án:** `cardinality() = 1`, `length() = 8`, vì bit 7 bật.

**Bài 3.** `BitSet.valueOf(new long[]{0L, 1L})` bật bit nào?  
**Đáp án:** Chỉ bit `64`; word thứ hai bắt đầu từ bit 64.

**Bài 4.** `BitSet.valueOf(new long[]{Long.MIN_VALUE})` bật bit nào?  
**Đáp án:** Bit `63`; nếu từ `longs[1]` thì là bit `127`.

**Bài 5.** `BitSet.valueOf(new long[]{-1L}).cardinality()` bằng bao nhiêu?  
**Đáp án:** `64`, do 64 bit của `-1L` đều là 1.

**Bài 6.** `new byte[]{1, 0, 0}` được chuyển thành BitSet rồi xuất `toByteArray()` còn bao nhiêu byte?  
**Đáp án:** Một byte `[1]`, vì hai byte 0 ở cuối không đóng góp bit bật.

**Bài 7.** Một BitSet bật bit `0, 9, 70` có `toLongArray()` như thế nào?  
**Đáp án:** `[513, 64]`. Word đầu bật bit 0 và 9; word thứ hai bật bit offset 6.

**Bài 8.** Tại sao `length()` của trường hợp trên là 71 chứ không phải 3?  
**Đáp án:** `length()` là bit index cao nhất bật + 1 (`70 + 1 = 71`); số bit bật là `cardinality() = 3`.

**Bài 9.** Buffer có capacity 100 nhưng `position=10`, `limit=12`. `valueOf(ByteBuffer)` đọc bao nhiêu byte?  
**Đáp án:** Hai byte (`10` và `11`), không phải 100 byte. Position/limit không bị thay bởi lời gọi.

**Bài 10.** Một giao thức yêu cầu 16 byte bitmap, nhưng `toByteArray()` trả chỉ một byte. Có phải Java mất dữ liệu?  
**Đáp án:** Không nhất thiết. Nó dùng biểu diễn tối thiểu chứa bit bật. Phải pad byte zero đến 16 byte và giữ quy tắc kiểm tra bit index giới hạn.

**Bài 11.** Có nên sử dụng `BitSet.size()` để xác định độ dài frame xuất network không?  
**Đáp án:** Không. `size()` là storage capacity nội bộ, không định nghĩa độ dài khung dữ liệu.

**Bài 12.** Nếu input array thay đổi sau `valueOf`, BitSet có đổi theo không?  
**Đáp án:** Không. Factory tạo nội dung bit mới, không giữ live view.

**Bài 13.** `BitSet.valueOf((byte[])null)` trả tập rỗng hay gây lỗi?  
**Đáp án:** Gây `NullPointerException`. Tập rỗng có thể tạo bằng `new BitSet()` hoặc `BitSet.valueOf(new byte[0])`.

**Bài 14.** Đầu vào là long `1L << 63`. Tại sao không được thay bằng `1 << 63`?  
**Đáp án:** Literal `1` là `int`; dịch bit trong `int` không tương đương dịch bit của `long` 64-bit. Dùng `1L` để tạo mask trên long.

**Bài 15.** `BitSet.valueOf(ByteBuffer)` có bắt buộc dùng `ByteOrder.LITTLE_ENDIAN` mới đúng không?  
**Đáp án:** Không. Phương thức diễn giải từng byte theo quy tắc `BitSet`. Byte order của buffer quan trọng với các lệnh đọc số nhiều byte như `getLong()`, không làm `valueOf(ByteBuffer)` tự đảo hướng đánh số bit.

### Thực hành A — Ranh giới 7/8

Tạo các `byte[]` lần lượt là `{(byte)0x80}` và `{0, 1}`. Dự đoán `get(7)`, `get(8)`, `length()` và `cardinality()`. Xác minh bằng chương trình Java 17.

### Thực hành B — Ranh giới 63/64

Tạo `long[]{Long.MIN_VALUE, 1L}`, sau đó xác nhận `get(63)==true`, `get(64)==true` và `cardinality()==2`. So sánh với mảng `byte[]` tương đương bằng round-trip.

### Thực hành C — Trailing zeros

Tạo `new byte[]{0,0,1,0,0}`, nhập vào BitSet rồi xuất ra byte array. Giải thích tại sao các byte 0 **đầu mảng** vẫn cần có khi dữ liệu có bit bật ở byte thứ ba, còn zero **cuối mảng** bị lược bỏ.

### Thực hành D — Buffer range

Dùng `ByteBuffer.wrap` với nhiều byte, thay đổi position/limit rồi gọi `valueOf`. Assert `position`/`limit` không thay đổi; thử thay đổi buffer sau conversion và xác nhận BitSet không thay đổi.

### Thực hành E — Export đúng width

Sửa `BitSetFixedWidthDemo.encode` để nhận số **bit logic** thay vì số byte. Từ số bit, tính số byte cần thiết, bảo vệ overflow và kiểm tra mọi bit bật có nằm trong vùng hợp lệ. Đối chiếu với wire format mà ứng dụng định nghĩa.

## 19. Tài liệu chuẩn

- [Oracle Java SE 17 — java.util.BitSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html): `valueOf(byte[])`, `valueOf(long[])`, overload nhận buffer, `toByteArray`, `toLongArray`, `length`, `cardinality` và `size`.
- [Oracle Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, remaining và byte order.
- [Oracle Java SE 17 — LongBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/LongBuffer.html): dữ liệu long ở vùng remaining.
- [Oracle Java SE 17 — Byte](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html) và [Long](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): độ rộng bit và cách Java thể hiện kiểu nguyên thủy có dấu.
- [Java Language Specification 17 — `15.19, Shift Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.19): toán tử dịch bit và ảnh hưởng của kiểu `int`/`long`.

**Ghi nhớ cốt lõi:** `BitSet.valueOf(byte[])` đánh số các bit theo **8*i + k**, `BitSet.valueOf(long[])` theo **64*i + k**, với `k` là vị trí bit từ thấp lên cao. Giá trị `byte`/`long` âm **không làm mất bit dấu**. `toByteArray()`/`toLongArray()` giúp round-trip tập bit, nhưng **không bảo toàn độ dài mảng đầu vào khi cuối dãy toàn zero**. Khi cần một định dạng binary cố định, giữ chiều dài và quy ước byte order ở tầng giao thức, kiểm tra giới hạn rồi mới xuất dữ liệu.
