# Java 7 — BitSet: Xuất dữ liệu bằng `toByteArray()` và `toLongArray()`

## Mục tiêu bài học

`java.util.BitSet` là cấu trúc lưu tập hợp các bit có chỉ số không âm, hỗ trợ thao tác `set`, `clear`, `get`, `or`, `and`, `xor` và các phép toán bit khác. Khi cần **đưa trạng thái bit ra khỏi chương trình** — lưu tệp, tạo payload nhị phân, chuyển giữa các API hoặc dựng dữ liệu truyền tải — hai phương thức quan trọng là:

- `byte[] toByteArray()`: xuất thành dãy byte, với **bit chỉ số thấp nằm trước** và các byte theo thứ tự little-endian.
- `long[] toLongArray()`: xuất thành dãy từ 64 bit kiểu `long`, với **từ chứa các bit thấp đứng trước**.

Cả hai được bổ sung từ **Java 7** và **vẫn có hiệu lực trên Java hiện đại**. Chúng không xuất object metadata hay một định dạng lưu trữ đầy đủ có version, checksum hoặc độ rộng cố định. Mảng trả về có độ dài **tối thiểu** đủ chứa bit cao nhất đang bật; vì vậy việc serialize thành một protocol cụ thể đòi hỏi hiểu chính xác cách đánh số bit, vị trí bit trong mỗi byte/từ, chữ ký giá trị có dấu và xử lý các bit 0 ở cuối.

Sau bài, bạn có thể:

1. Dự đoán chính xác `toByteArray()` và `toLongArray()` từ tập các chỉ số bit.
2. Hiểu công thức ánh xạ `n` sang `bytes[n/8]` hoặc `longs[n/64]` và thứ tự bit **least significant bit trước**.
3. Phân biệt `BitSet.length()`, `size()` và `cardinality()`; tính đúng kích thước dữ liệu xuất ra.
4. Xử lý byte Java **có dấu** mà không làm sai các bit nhị phân.
5. Khôi phục tập bit từ mảng bằng `BitSet.valueOf(byte[])` hoặc `BitSet.valueOf(long[])` và kiểm thử round-trip.
6. Biết cách tạo payload **độ rộng cố định** hoặc thiết kế hợp đồng lưu trữ có metadata thay vì giả định mảng xuất tự giữ độ rộng ban đầu.
7. Tránh nhầm little-endian `BitSet` với định dạng byte của thư viện ngoài, `BigInteger`, `ByteBuffer` hoặc một giao thức network có byte order khác.
8. Nắm giới hạn của việc xuất mảng với mutable `BitSet`, dữ liệu thưa và lập trình đa luồng.

Các ví dụ đầy đủ chạy trên **JDK 17+** bằng `javac --release 17`. Mọi kết quả stdout được kiểm chứng bằng chương trình thật, không dùng kiến thức Java lỗi thời.

## 1. Mô hình dữ liệu: bit có chỉ số, không phải chuỗi nhị phân có chiều rộng cố định

Một `BitSet` là tập các bit được bật (`true`). Vị trí bit được đánh số từ **0**:

```java
BitSet flags = new BitSet();
flags.set(0);
flags.set(7);
flags.set(8);
System.out.println(flags); // {0, 7, 8}
```

Đây là **mảnh minh họa** đặt trong phương thức, cần `import java.util.BitSet;`. Các vị trí `0`, `7`, `8` là các chỉ số, không phải byte values. Điều này khác với một số biểu diễn “bit string” thường in bit cao nhất trước.

Một điều quan trọng khác: **`BitSet` không tự lưu “độ rộng nghiệp vụ”**. Một bitset chứa bit `0` được bật và một bitset được tạo với ý định biểu diễn 32 cờ nhưng chỉ có bit `0` bật là **cùng tập bit** theo quan sát của `BitSet`, dù giao thức ngoài có thể mong hai độ rộng khác nhau.

```text
Các bit đang bật: {0, 7, 8}

Byte 0 ứng với bit 0..7:
  vị trí nội bộ: 7 6 5 4 3 2 1 0
  giá trị:       1 0 0 0 0 0 0 1  = 0x81

Byte 1 ứng với bit 8..15:
  vị trí nội bộ: 15 14 13 12 11 10 9 8
  giá trị:       0  0  0  0  0  0 0 1 = 0x01

toByteArray() -> [0x81, 0x01] (đặt byte thấp trước)
```

**Lưu ý về cách vẽ:** Trong mỗi dòng byte ở ví dụ, bit số lớn được in bên trái cho dễ đọc theo cách viết số nhị phân. Trong **mảng byte**, byte chứa bit số thấp vẫn nằm ở phần tử **đầu tiên**. Đừng nhầm thứ tự biểu diễn khi in số với thứ tự byte khi truyền/lưu dữ liệu.

### 1.1. Ba số đo cần phân biệt

| Thuộc tính | Ý nghĩa | Dùng vào việc gì? |
| --- | --- | --- |
| `length()` | Chỉ số bit bật cao nhất cộng 1; bằng 0 nếu rỗng | Tính độ dài tối thiểu cần biểu diễn |
| `cardinality()` | Số bit thực sự đang bật | Đếm số cờ true; **không phải độ dài export** |
| `size()` | Số bit của không gian lưu trữ bên trong mà implementation đang có | Thông tin về capacity; **không nên dùng làm độ rộng serialize** |

Ví dụ các bit bật là `{0,7,8}`:

- `length() == 9` vì chỉ số cao nhất là `8`.
- `cardinality() == 3`.
- `toByteArray().length == 2` vì cần 2 byte để chứa tới bit `8`.
- `size()` có thể lớn hơn `9` vì `BitSet` giữ vùng cấp phát nội bộ theo các khối. Nó không phải độ rộng dữ liệu bạn đã thỏa thuận với hệ thống nhận.

## 2. `toByteArray()`: công thức ánh xạ bit sang byte

Theo hợp đồng API, với `BitSet bits`:

```text
byte[] bytes = bits.toByteArray();

bytes.length = (bits.length() + 7) / 8

bit n thuộc byte:
    byteIndex = n / 8
    bitOffset = n % 8

bits.get(n) ==
    ((bytes[n / 8] & (1 << (n % 8))) != 0)
```

Các biểu thức chỉ dành cho những chỉ số còn nằm trong mảng; đối với chỉ số vượt quá mảng trả về, bit tương ứng bằng `false`. Công thức độ dài phía trên đúng với trạng thái `BitSet` hợp lệ thông thường và phản ánh việc **bỏ các byte 0 cao không cần thiết**.

### 2.1. Little-endian ở đây nghĩa là gì?

- `bytes[0]` chứa các bit có chỉ số `0..7`.
- `bytes[1]` chứa các bit `8..15`.
- `bytes[2]` chứa các bit `16..23`.
- Trong mỗi byte, bit `n % 8` là bit có trọng số `2^(n%8)`: bit `0` có trọng số 1, bit `7` có trọng số 128.

Do đó, nếu chỉ bật bit `8`, dữ liệu là `[0x00, 0x01]`, **không phải** `[0x01, 0x00]`. Byte thấp ở trước là điều cần đồng thuận khi nối vào format lưu trữ bên ngoài.

### 2.2. Java `byte` là số có dấu

`byte` Java có giá trị từ `-128` đến `127`. Khi một byte chứa bit số 7 bật, giá trị nhị phân có thể in thành số âm. Ví dụ:

- `0x81` tương ứng giá trị `-127` khi xem dưới kiểu `byte`.
- `0x80` tương ứng `-128`.
- `0xFF` tương ứng `-1`.

**Giá trị âm trong `Arrays.toString(byte[])` không có nghĩa bit bị hỏng**. Bộ nhớ vẫn có 8 bit nhị phân đúng; chỉ cách diễn giải giá trị có dấu khác đi. Để xem giá trị unsigned, dùng `Byte.toUnsignedInt(bytes[i])` hoặc `bytes[i] & 0xFF`.

## 3. Chương trình A — Xuất byte, in hex và khôi phục

Lưu toàn bộ mã sau vào tệp **`ByteExportDemo.java`**:

```java
import java.util.BitSet;
import java.util.Arrays;

public final class ByteExportDemo {
    public static void main(String[] args) {
        BitSet flags = new BitSet();
        flags.set(0);
        flags.set(7);
        flags.set(8);
        flags.set(15);
        flags.set(23);

        byte[] bytes = flags.toByteArray();
        System.out.println("bits=" + flags);
        System.out.println("length=" + flags.length());
        System.out.println("byteCount=" + bytes.length);
        System.out.println("signedBytes=" + Arrays.toString(bytes));
        System.out.print("hex=");
        for (int i = 0; i < bytes.length; i++) {
            if (i > 0) {
                System.out.print(" ");
            }
            System.out.printf("%02X", Byte.toUnsignedInt(bytes[i]));
        }
        System.out.println();
        System.out.println("roundTrip=" + flags.equals(BitSet.valueOf(bytes)));

        bytes[0] = 0;
        System.out.println("afterArrayMutation=" + flags.get(0));
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 ByteExportDemo.java
java ByteExportDemo
```

**Stdout chính xác:**

```text
bits={0, 7, 8, 15, 23}
length=24
byteCount=3
signedBytes=[-127, -127, -128]
hex=81 81 80
roundTrip=true
afterArrayMutation=true
```

### 3.1. Tính tay trước khi chạy

Tập bit bật là `{0,7,8,15,23}`.

| Byte | Các vị trí bit mà byte chứa | Bit được bật | Giá trị hex | `byte` có dấu |
| --- | --- | --- | --- | --- |
| `bytes[0]` | 0..7 | 0, 7 | `0x81` | `-127` |
| `bytes[1]` | 8..15 | 8, 15 | `0x81` | `-127` |
| `bytes[2]` | 16..23 | 23 | `0x80` | `-128` |

- Bit cao nhất là `23`, nên `length() == 24` và số byte là `(24 + 7) / 8 == 3`.
- Việc in `Arrays.toString(bytes)` dùng biểu diễn có dấu và tạo `[-127, -127, -128]`.
- Dòng hex dùng `Byte.toUnsignedInt`, nên nhìn thấy đúng `81 81 80`.
- `BitSet.valueOf(bytes)` hiểu chuỗi byte theo cùng thứ tự little-endian và dựng lại đúng các bit; `roundTrip=true`.
- Khi gán `bytes[0] = 0` **sau khi export**, trạng thái `flags` không đổi: `afterArrayMutation=true`. Mảng nhận từ `toByteArray()` là một bản dữ liệu mới, không phải một cửa sổ sửa trực tiếp các bit bên trong `BitSet`.

### 3.2. Đừng nhầm định dạng hex hiển thị với endianness

Dòng `hex=81 81 80` đang in **theo thứ tự byte trong mảng**. Một thư viện khác có thể mong chuỗi big-endian hoặc một sequence bit theo thứ tự MSB-first; khi ấy cùng ký tự hex có thể mang ý nghĩa khác.

Nếu viết protocol, cần nói rõ:

1. Bit số `0` ở đâu?
2. Byte đầu tiên chứa bit số nào?
3. Trong byte, bit offset `0` là least-significant hay most-significant bit?
4. Payload được phép bỏ các byte 0 cao không?
5. Độ rộng tối đa/tối thiểu là bao nhiêu, và có metadata riêng không?

Không để hai đầu hệ thống “tự hiểu” các câu hỏi này.

## 4. `toLongArray()`: từ 64 bit và thứ tự thấp trước

`toLongArray()` xuất nội dung `BitSet` thành một mảng `long[]`. Mỗi phần tử chứa **64 vị trí bit**:

```text
long[] words = bits.toLongArray();

words.length = (bits.length() + 63) / 64

bit n thuộc long:
    wordIndex = n / 64
    bitOffset = n % 64

bits.get(n) ==
    ((words[n / 64] & (1L << (n % 64))) != 0)
```

Tương tự mảng byte, công thức truy cập chỉ áp dụng khi `wordIndex` nằm trong mảng; mọi bit vượt phạm vi dữ liệu xuất đều là `false`. Mảng trả về bỏ các **long 0 cao không cần thiết**.

### 4.1. Thứ tự và ý nghĩa của từ 64 bit

- `words[0]` biểu diễn bit `0..63`.
- `words[1]` biểu diễn bit `64..127`.
- `words[2]` biểu diễn bit `128..191`.
- Trong mỗi từ, bit offset 0 có trọng số `1L`; bit offset 63 là bit cao nhất.

**Quan trọng:** Mảng `long[]` là các **giá trị 64 bit**, không phải trực tiếp là một chuỗi byte theo format file/network. Nếu cần chuyển từng `long` thành byte, phải định nghĩa và áp dụng rõ byte order; không thể lấy “Java `long[]` đã little-endian” làm bảo đảm về cách một thư viện nhị phân bất kỳ sẽ mã hóa `long` ra byte.

### 4.2. Kiểu `long` cũng có dấu

Một `long` có bit số 63 được bật được biểu diễn như một số có dấu âm. Điều đó không làm thay đổi nội dung bit:

- `0x8000000000000000L` tương ứng `Long.MIN_VALUE`.
- Nếu bật cả bit số 0 và bit số 63, từ đầu tiên là `0x8000000000000001`, in signed decimal là `-9223372036854775807`.
- Để quan sát dạng nhị phân/hex mà không suy diễn dấu, dùng `Long.toHexString(word)` hoặc các phép bitwise.

Đừng đem giá trị signed decimal trong `Arrays.toString(long[])` so trực tiếp với tài liệu protocol ghi unsigned long rồi cho rằng dữ liệu khác. Cần so **pattern 64 bit**.

## 5. Chương trình B — Xuất long qua ranh giới 63/64 và 127/128

Lưu thành **`LongExportDemo.java`**:

```java
import java.util.Arrays;
import java.util.BitSet;

public final class LongExportDemo {
    public static void main(String[] args) {
        BitSet flags = new BitSet();
        for (int bit : new int[]{0, 63, 64, 70, 130}) {
            flags.set(bit);
        }
        long[] words = flags.toLongArray();
        System.out.println("bits=" + flags);
        System.out.println("length=" + flags.length());
        System.out.println("longCount=" + words.length);
        System.out.println("longValues=" + Arrays.toString(words));
        System.out.print("hexWords=");
        for (int i = 0; i < words.length; i++) {
            if (i > 0) {
                System.out.print(" ");
            }
            System.out.print(Long.toHexString(words[i]).toUpperCase());
        }
        System.out.println();
        System.out.println("roundTrip=" + flags.equals(BitSet.valueOf(words)));
        words[0] = 0;
        System.out.println("afterArrayMutation=" + flags.get(63));
    }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 LongExportDemo.java
java LongExportDemo
```

**Stdout chính xác:**

```text
bits={0, 63, 64, 70, 130}
length=131
longCount=3
longValues=[-9223372036854775807, 65, 4]
hexWords=8000000000000001 41 4
roundTrip=true
afterArrayMutation=true
```

### 5.1. Giải thích từng phần tử `long`

| Vị trí | Khoảng bit | Những bit được bật | Nội dung hex |
| --- | --- | --- | --- |
| `words[0]` | 0..63 | 0, 63 | `8000000000000001` |
| `words[1]` | 64..127 | 64, 70 | `41` (tức 0x41) |
| `words[2]` | 128..191 | 130 | `4` (tức 0x4) |

- Bit cao nhất được bật là `130` nên `length() == 131`.
- Số `long` = `(131 + 63) / 64 == 3`.
- `words[0]` có bit cao nhất của một signed long được bật nên khi in decimal là số âm.
- `words[1]` có offset `64-64 = 0` và `70-64 = 6`, nên `1 + 64 = 65`, hex `0x41`.
- `words[2]` có offset `130-128 = 2`, nên `1L << 2 == 4`.
- `BitSet.valueOf(words)` dựng lại đúng tập bit.
- Thay đổi `words[0]` sau export **không sửa `BitSet` gốc**, vì đây là mảng mới.

### 5.2. Khi nào chọn `long[]`?

`long[]` phù hợp khi consumer sử dụng các **từ 64 bit** để xử lý bitwise, tính toán hoặc tích hợp với API Java nhận `long[]`. `byte[]` phù hợp hơn khi API nhận **payload byte**, file, socket hoặc codec nhị phân. Không có lựa chọn nào tự giải quyết metadata, kích thước logic hay endianness của giao thức ngoài.

**Không nên** chuyển sang `long[]` chỉ vì cho rằng nó sẽ tiết kiệm dung lượng lưu trữ nhị phân: một `long` có 8 byte, và export dạng `long[]` có thể giữ thêm bit 0 ở cuối từ cuối cùng. Hai mảng là **hai biểu diễn**, không có kích thước phần tử bằng nhau.

## 6. Độ dài tối thiểu: những bit 0 ở phía cao không được lưu

Cả hai phương thức export đều tạo mảng vừa đủ chứa tới bit `length()-1`. Vì thế độ dài là:

```text
byteCount = (bitSet.length() + 7) / 8
longCount = (bitSet.length() + 63) / 64
```

Đây không phải `size()/8` hay `cardinality()/8`.

- Nếu `BitSet` rỗng (không có bit nào bật), `length() == 0`, cả hai phương thức trả **mảng độ dài 0**.
- Nếu bật bit `0`, export byte có 1 phần tử và export long có 1 phần tử.
- Nếu bật bit `15`, export byte có 2 phần tử nhưng export long vẫn có 1.
- Nếu xóa bit cao nhất, kích thước export có thể **giảm** dù object đã từng có capacity lớn hơn.
- Hai `BitSet` với cùng các bit bật tạo nội dung export giống nhau, kể cả nếu trước đó chúng được cấp phát bằng những capacity khác nhau.

Một ứng dụng có thể cần đúng **256 bit** để biểu diễn một bitmap. Nếu tất cả bit đều 0, `toByteArray()` không trả 32 byte; nó trả **`new byte[0]`** về mặt kích thước. Nếu giao thức yêu cầu 32 byte, phải có bước padding và lưu ý chiều rộng.

## 7. Chương trình C — Empty, capacity, clear và kích thước export

Lưu vào **`MinimalLengthDemo.java`**:

```java
import java.util.BitSet;
import java.util.Arrays;

public final class MinimalLengthDemo {
    public static void main(String[] args) {
        BitSet empty = new BitSet(256);
        System.out.println("emptyLength=" + empty.length());
        System.out.println("emptySize=" + empty.size());
        System.out.println("emptyBytes=" + empty.toByteArray().length);
        System.out.println("emptyLongs=" + empty.toLongArray().length);

        BitSet set = new BitSet(256);
        set.set(0);
        set.set(15);
        System.out.println("beforeLength=" + set.length());
        System.out.println("beforeBytes=" + set.toByteArray().length);
        System.out.println("beforeLongs=" + set.toLongArray().length);

        set.clear(15);
        System.out.println("afterLength=" + set.length());
        System.out.println("afterBytes=" + set.toByteArray().length);
        System.out.println("afterLongs=" + set.toLongArray().length);

        set.clear();
        System.out.println("clearedBytes=" + set.toByteArray().length);
        System.out.println("clearedLongs=" + set.toLongArray().length);
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MinimalLengthDemo.java
java MinimalLengthDemo
```

Kết quả trên JDK kiểm thử:

```text
emptyLength=0
emptySize=256
emptyBytes=0
emptyLongs=0
beforeLength=16
beforeBytes=2
beforeLongs=1
afterLength=1
afterBytes=1
afterLongs=1
clearedBytes=0
clearedLongs=0
```

### 7.1. Phân tích

`new BitSet(256)` yêu cầu một khả năng chứa ít nhất 256 bit theo cách quản lý storage của implementation. Trong phép thử, `size()` báo 256, nhưng **không** có bit nào bật nên `length() == 0` và hai mảng export đều rỗng.

Khi bật bit `15`, bit cao nhất là 15 nên `length() == 16` và cần 2 byte, 1 long. Sau khi `clear(15)`, bit cao nhất còn lại là 0, nên `length() == 1` và cần 1 byte, 1 long. Khi xóa hết, cả hai export dài 0.

**Nguyên tắc:** Đừng lưu `size()` làm “số bit có ý nghĩa” nếu dữ liệu của bạn là các cờ đã bật. `size()` liên quan storage capacity và không phản ánh độ rộng do giao thức quyết định. Nếu phải biết rằng một tập bit dùng để biểu diễn đúng 256 vị trí, metadata `256` phải nằm trong **hợp đồng bên ngoài `BitSet`**.

### 7.2. Ranh giới 8 và 64 bit

| Bit cao nhất đang bật | `length()` | Byte tối thiểu | Long tối thiểu |
| --- | ---: | ---: | ---: |
| Không có bit bật | 0 | 0 | 0 |
| 0 | 1 | 1 | 1 |
| 7 | 8 | 1 | 1 |
| 8 | 9 | 2 | 1 |
| 15 | 16 | 2 | 1 |
| 63 | 64 | 8 | 1 |
| 64 | 65 | 9 | 2 |
| 127 | 128 | 16 | 2 |
| 128 | 129 | 17 | 3 |

Bảng cho thấy rõ: **số phần tử export phụ thuộc vị trí bit bật cao nhất**, không phải số lượng cờ đang true.

## 8. `BitSet.valueOf(...)` và khôi phục vòng tròn

Hai chiều làm việc tương ứng:

```java
byte[] binary = bits.toByteArray();
BitSet fromBytes = BitSet.valueOf(binary);

long[] words = bits.toLongArray();
BitSet fromLongs = BitSet.valueOf(words);
```

Đây là **mảnh minh họa** cần import `java.util.BitSet` và có biến `bits` đã tạo. Với `BitSet` bình thường, không có dữ liệu bị thay đổi trong lúc export, hai vòng tròn bảo toàn **những bit đang bật**:

```text
bits.equals(BitSet.valueOf(bits.toByteArray())) == true
bits.equals(BitSet.valueOf(bits.toLongArray())) == true
```

### 8.1. Round-trip bảo toàn điều gì?

- Bảo toàn tất cả vị trí bit đang bật.
- Các vị trí bit không nằm trong mảng nhận được hiểu là `false`.
- Không bảo toàn “capacity đã từng cấp phát”, chiều rộng protocol hoặc số lượng byte 0 cao bị trim.
- Không tự bảo toàn metadata như version, checksum, bit order của thư viện ngoài, timestamp hoặc các ràng buộc nghiệp vụ.
- Mảng từ export là **dữ liệu độc lập**; sửa mảng trả về không trực tiếp sửa trạng thái `BitSet` gốc. Ngược lại, `valueOf(...)` dùng nội dung dữ liệu tại lúc khôi phục; các thay đổi sau đó trên mảng nguồn không nên được coi là thao tác trên `BitSet` đã dựng.

Một round-trip thành công **chỉ chứng minh hợp đồng của hai API Java tương thích với nhau**. Nó không chứng minh một chương trình ngoài Java đang đọc cùng byte order hoặc độ rộng như mong muốn.

### 8.2. Các byte 0 cao bị chuẩn hóa

Ví dụ mảng được cung cấp từ bên ngoài:

```java
byte[] padded = {1, 0, 0};
BitSet bits = BitSet.valueOf(padded);
byte[] canonical = bits.toByteArray();
// canonical là [1], không còn hai byte 0 ở cuối.
```

Đây là **mảnh minh họa**; cần import `BitSet`. Cả input `[1,0,0]` và output `[1]` đại diện cho cùng tập bit chỉ có bit `0` bật. Nhưng nếu protocol cần đúng 3 byte, **không thể dùng `toByteArray()` đơn lẻ để bảo đảm giữ chiều rộng đó**.

## 9. Chiều rộng cố định và contract lưu trữ

Một bài toán thực tế: hệ thống bên ngoài yêu cầu **chính xác 4 byte**, với bit `0` là cờ đầu và bit `31` là cờ cuối.

`BitSet` đang bật bit `0` và `12` sẽ xuất tối thiểu 2 byte:

```text
bits = {0, 12}
toByteArray() = [0x01, 0x10]
```

Nếu gửi trực tiếp, payload chỉ dài 2 byte và **không đạt contract 4 byte**. Cách làm phù hợp là **kiểm tra mọi bit đều nằm trong giới hạn**, sau đó padding phía **cuối mảng** bằng các byte 0, bởi byte thấp nằm trước.

### Chương trình D — `FixedWidthDemo.java`

```java
import java.util.BitSet;
import java.util.Arrays;

public final class FixedWidthDemo {
    private static byte[] encode(BitSet bits, int widthBytes) {
        if (widthBytes < 0 || (long) bits.length() > (long) widthBytes * 8L) {
            throw new IllegalArgumentException("bit set does not fit");
        }
        return Arrays.copyOf(bits.toByteArray(), widthBytes);
    }

    public static void main(String[] args) {
        BitSet flags = new BitSet();
        flags.set(0);
        flags.set(12);
        byte[] fixed = encode(flags, 4);
        System.out.println("minimal=" + Arrays.toString(flags.toByteArray()));
        System.out.println("fixed=" + Arrays.toString(fixed));
        System.out.println("fixedLength=" + fixed.length);
        System.out.println("decoded=" + BitSet.valueOf(fixed));
        System.out.println("equal=" + flags.equals(BitSet.valueOf(fixed)));

        try {
            encode(flags, 1);
            System.out.println("unexpected-success");
        } catch (IllegalArgumentException e) {
            System.out.println("reject=" + e.getMessage());
        }

        byte[] leadingZeroSuffix = new byte[]{1, 0, 0};
        BitSet decoded = BitSet.valueOf(leadingZeroSuffix);
        System.out.println("decodedLength=" + decoded.length());
        System.out.println("canonical=" + Arrays.toString(decoded.toByteArray()));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FixedWidthDemo.java
java FixedWidthDemo
```

Stdout:

```text
minimal=[1, 16]
fixed=[1, 16, 0, 0]
fixedLength=4
decoded={0, 12}
equal=true
reject=bit set does not fit
decodedLength=1
canonical=[1]
```

### 9.1. Tại sao phải kiểm tra kích thước trước khi copy?

`Arrays.copyOf(source, requestedLength)` có thể **cắt bỏ phần cuối** nếu `requestedLength` nhỏ hơn độ dài source. Với dữ liệu bit, cắt phần cuối có thể **làm mất các bit cao đang bật** mà không báo lỗi. Trong bài, guard:

```java
(long) bits.length() > (long) widthBytes * 8L
```

ngăn trường hợp một bit bật nằm ngoài miền cho phép. Việc ép sang `long` trước khi nhân tránh overflow khi tính `widthBytes * 8` bằng `int` cho các giá trị lớn.

Hàm này là ví dụ dành cho **width tính theo số byte** và contract little-endian kiểu `BitSet`. Nếu giao thức yêu cầu một số bit không chia hết cho 8 (ví dụ 13 bit), cần kiểm tra **bit cao nhất nhỏ hơn 13**, đồng thời xác định cách zero các bit không sử dụng trong byte cuối. Không thể chỉ suy từ số byte làm đủ contract mọi định dạng.

### 9.2. Vì sao padding ở cuối?

Mảng `toByteArray()` đặt byte chứa bit thấp ở đầu. Bởi vậy, cần giữ nguyên các phần tử hiện có rồi thêm byte 0 vào **cuối**, không phải thêm số 0 vào trước làm dịch vị trí mọi bit.

Nếu format bên ngoài yêu cầu big-endian, bạn phải dùng một bước **chuyển đổi thứ tự byte được thỏa thuận**, không được chỉ luôn padding đầu hoặc cuối theo cảm tính. Thiết kế codec cần có test ở hai phía.

### 9.3. Decode khi độ rộng không nằm trong mảng `BitSet`

Khi nhận một mảng cố định 4 byte, `BitSet.valueOf(bytes)` trả lại các bit đang bật, nhưng không lưu thông tin “độ rộng từng là 32 bit” vào `BitSet`. Nếu API nội bộ cần biết 32 bit là miền hợp lệ, giữ `widthBits=32` tách khỏi đối tượng hoặc đóng gói vào một value type có contract riêng.

Điều này quan trọng cho:
- Flags phiên bản có vị trí dành riêng để mở rộng.
- Bitmap permission/feature với tổng số flag cố định.
- Khuôn dữ liệu giao tiếp thiết bị hoặc payload nhị phân theo chuẩn đã định.
- Mã hóa có phần header ghi width/schema version.

Đừng coi `BitSet.size()` là nơi lấy lại width giao thức sau khi decode; nó phản ánh quản lý storage, không phải số bit mang ý nghĩa nghiệp vụ.

## 10. Chương trình E — Các ranh giới bit và mảng nguồn độc lập

Lưu thành **`BoundaryAndCopyDemo.java`**:

```java
import java.util.BitSet;
import java.util.Arrays;

public final class BoundaryAndCopyDemo {
    public static void main(String[] args) {
        int[] indexes = {7, 8, 63, 64};
        BitSet bits = new BitSet();
        for (int index : indexes) {
            bits.set(index);
        }
        System.out.println("bit7=" + bits.get(7));
        System.out.println("bit8=" + bits.get(8));
        System.out.println("bit63=" + bits.get(63));
        System.out.println("bit64=" + bits.get(64));
        System.out.println("length=" + bits.length());
        System.out.println("byteCount=" + bits.toByteArray().length);
        System.out.println("longCount=" + bits.toLongArray().length);
        System.out.println("byteHexFirst=" + Integer.toHexString(
                Byte.toUnsignedInt(bits.toByteArray()[0])));
        System.out.println("byteHexSecond=" + Integer.toHexString(
                Byte.toUnsignedInt(bits.toByteArray()[1])));
        System.out.println("lastByte=" + bits.toByteArray()[8]);

        byte[] originalBytes = {0, -128, 1, 0};
        BitSet restored = BitSet.valueOf(originalBytes);
        System.out.println("restored=" + restored);
        originalBytes[1] = 0;
        System.out.println("afterInputMutation=" + restored.get(15));
        System.out.println("canonicalBytes=" + Arrays.toString(restored.toByteArray()));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BoundaryAndCopyDemo.java
java BoundaryAndCopyDemo
```

Stdout:

```text
bit7=true
bit8=true
bit63=true
bit64=true
length=65
byteCount=9
longCount=2
byteHexFirst=80
byteHexSecond=1
lastByte=1
restored={15, 16}
afterInputMutation=true
canonicalBytes=[0, -128, 1]
```

### 10.1. Diễn giải

- Bật bit `7` tạo `0x80` ở byte đầu.
- Bật bit `8` tạo `0x01` ở byte thứ hai.
- Bật bit `63` nằm trong `words[0]`, nhưng ở byte thứ tám (index 7).
- Bật bit `64` tạo phần tử `words[1]` và byte thứ chín (index 8).
- Bit cao nhất là 64, nên `length() == 65`; byteCount là `ceil(65/8) = 9` và longCount là `ceil(65/64) = 2`.
- Mảng input `{0, -128, 1, 0}` tương ứng byte index 1 có bit offset 7 (bit tổng `15`), byte index 2 có offset 0 (bit tổng `16`); byte cuối 0 không thêm bit nào.
- Sau khi dựng `BitSet`, sửa `originalBytes[1]` không làm đổi tập bit đã khôi phục (`afterInputMutation=true`).
- Dữ liệu xuất lại trở thành dạng tối thiểu `[0, -128, 1]`, bỏ byte 0 cao ở cuối.

### 10.2. Đọc `byte[]` có dấu đúng cách

`Byte.toUnsignedInt` được hỗ trợ trên JDK hiện đại và phù hợp khi in giá trị hex. Ví dụ:

```java
int unsigned = Byte.toUnsignedInt((byte) 0x80); // 128
boolean highBit = (unsigned & 0x80) != 0;       // true
```

Đây là mảnh code minh họa. Không dùng phép so `bytes[i] > 127` vì `byte` Java không bao giờ có giá trị signed lớn hơn 127. Nếu muốn kiểm tra bit, dùng bit mask như công thức của `BitSet`.

## 11. Xuất dữ liệu sang protocol: điều cần thống nhất trước

`toByteArray()` và `toLongArray()` là **representation helpers**, không phải định dạng serialization độc lập mang tính tự mô tả. Trước khi lưu hoặc gửi qua mạng, xác định hợp đồng:

| Thành phần contract | Câu hỏi phải trả lời |
| --- | --- |
| Vị trí bit | Bit số 0 ứng với cờ nào? Có reserved bits không? |
| Bit order trong byte | Offset `0` là bit ít quan trọng nhất hay nhiều nhất? |
| Byte order | Byte thấp đứng trước hay sau trong payload? |
| Word order | Nếu truyền `long[]`, thứ tự các từ 64 bit là gì? |
| Byte order của một `long` khi encode | Dùng little-endian hay big-endian cho 8 byte của mỗi từ? |
| Độ rộng | Dạng tối thiểu hay cố định, số bit/byte là bao nhiêu? |
| Trailing zeros | Có được lược bỏ các byte/từ 0 cao không? |
| Phiên bản schema | Vị trí bit có thể được gán lại ý nghĩa ở version khác không? |
| Giới hạn đầu vào | Payload tối đa dài bao nhiêu? Bit index lớn nhất hợp lệ? |
| Tính toàn vẹn | Có header length, checksum hoặc kiểm tra corruption không? |

### 11.1. Little-endian ở API không tự biến network thành little-endian

`BitSet.toByteArray()` cho byte thứ tự thấp trước. Nhưng `ByteBuffer` thông thường có byte order do API quyết định (mặc định của `ByteBuffer` là big-endian), và thư viện giao thức có thể đặt quy định khác. Nếu bạn chuyển `long[]` qua một writer byte-oriented, writer sẽ dùng byte order của chính nó, **không suy từ `BitSet`**.

Ví dụ dưới đây chỉ minh họa cách chỉ định byte order khi biểu diễn **một `long` thành 8 byte**, không phải một trình serialize tổng quát:

```java
ByteBuffer buffer = ByteBuffer.allocate(Long.BYTES)
        .order(ByteOrder.LITTLE_ENDIAN);
buffer.putLong(0x0000000000000041L);
byte[] out = buffer.array(); // [65, 0, 0, 0, 0, 0, 0, 0]
```

Đây là **mảnh minh họa** cần import `java.nio.ByteBuffer` và `java.nio.ByteOrder`. Nó cho thấy khi cần định dạng **8 byte cố định**, số `long` 65 có thể được viết bằng little-endian. Trong hệ thống thật, muốn chuyển nhiều từ và bảo toàn độ rộng, phải xác định số từ, giới hạn và cách xử lý trailing zeros.

Không nên dùng `new BigInteger(bytes)` rồi tin nó sẽ giữ nguyên semantics của `BitSet`, vì `BigInteger(byte[])` có quy tắc signed two's-complement **big-endian** riêng. Nếu phải tương tác với `BigInteger`, chọn constructor/API và phép đảo thứ tự/signedness theo một specification đã được kiểm tra, không chuyển đổi tùy ý.

### 11.2. Đồng nhất với byte-stream khác ngôn ngữ

Khi thiết kế decoder cho Python, Go, C, Rust hoặc service bên ngoài:

- Khẳng định rõ byte đầu tiên là byte chứa bit `0..7`.
- Byte cuối có thể chỉ chứa vài bit thấp có ý nghĩa và các bit cao còn lại bằng 0.
- Để đọc bit `n`: truy byte `n/8` và mask `1 << (n%8)` nếu trong phạm vi payload.
- Với `long[]`, từng từ `longs[i]` chứa `64` bit bắt đầu tại `64*i`.
- Nếu dữ liệu lưu width riêng, decode xong cần xác nhận không có bit bất hợp lệ ngoài width.
- Đặt test vectors cố định như `{0,7,8} => 81 01` hoặc `{0,63,64}` ở cả hai phía.

Đừng dựa trên `BitSet.toString()`, vốn hiển thị **danh sách chỉ số bit bật** như `{0, 7, 8}`, làm format wire. Chuỗi đó hữu ích để debug, không phải codec nhị phân ổn định được thiết kế cho protocol.

## 12. Dữ liệu thưa, kích thước và chi phí xuất

`BitSet` thường hiệu quả khi thao tác với các bit trong một phạm vi vừa phải, đặc biệt khi cần các phép bitwise. Tuy vậy, các mảng export ở đây **không phải danh sách sparse các chỉ số bit bật**. Nếu chỉ có **một bit ở vị trí rất lớn** thì `toByteArray()` vẫn phải cấp đủ byte từ bit 0 tới vị trí đó.

Ví dụ ý nghĩa:

```java
BitSet sparse = new BitSet();
sparse.set(1_000_000);
int byteCount = sparse.toByteArray().length; // 125001
int longCount = sparse.toLongArray().length; // 15626
```

Đoạn trên là **mảnh minh họa**. Tính toán:

- Bit cao nhất là 1.000.000, nên `length() = 1.000.001`.
- `ceil(1_000_001/8) = 125001` byte.
- `ceil(1_000_001/64) = 15626` long.
- `cardinality() = 1` dù các mảng export phải chứa nhiều giá trị 0 ở giữa.

Không nhầm mảng dài với số bit true. Với dữ liệu cực thưa ở các chỉ số rất lớn, có thể cần một representation **danh sách chỉ số đã bật** hay một cấu trúc sparse chuyên biệt, tùy bài toán và tần suất các phép toán. Không tự chọn `BitSet` cho mọi tập chỉ số chỉ vì nó tiết kiệm bit trên lý thuyết.

### 12.1. Đừng xuất trong hot loop một cách không cần thiết

Mỗi lần gọi `toByteArray()`/`toLongArray()` tạo một mảng chứa snapshot biểu diễn bit của trạng thái tại thời điểm gọi. Gọi liên tục trong vòng lặp lớn có thể tạo allocation và chi phí sao chép. Nếu chỉ cần kiểm tra `get`, `nextSetBit`, `cardinality` hoặc tính toán bitwise trong Java, dùng trực tiếp `BitSet` có thể hợp lý hơn.

Khi performance thực sự quan trọng, benchmark với dữ liệu của ứng dụng. Không suy diễn rằng `toLongArray()` luôn nhanh hơn `toByteArray()` chỉ vì mỗi phần tử chứa 64 bit; hai API phục vụ các consumer và chi phí chuyển đổi khác nhau.

### 12.2. Thread-safety và tính nhất quán của snapshot

`BitSet` mutable và không tự bảo đảm thread-safety cho truy cập đồng thời. Nếu một thread đang `set`/`clear` trong lúc thread khác export, không nên dựa vào việc output là một snapshot nghiệp vụ nhất quán nếu không có đồng bộ hóa hợp lệ.

Có thể dùng ownership rõ ràng, lock hoặc một bản sao ổn định trước khi serialize, tùy yêu cầu. Đừng hiểu việc mảng trả về độc lập với object gốc như bằng chứng export **được atomic** trong mọi tình huống concurrent modification.

## 13. Trường hợp biên và những suy diễn sai

### 13.1. Mảng xuất rỗng có thể hoàn toàn hợp lệ

`new BitSet().toByteArray().length == 0` và `new BitSet().toLongArray().length == 0` là bình thường. Đừng diễn giải độ dài 0 là lỗi I/O hoặc cho rằng phải có ít nhất 1 byte/từ chỉ để thể hiện “bitmap rỗng”.

Nếu giao thức ngoài không cho phép payload rỗng, bạn cần tạo **dạng lưu trữ của giao thức**, ví dụ zero-padding đủ width; đừng đổi semantics của `BitSet`.

### 13.2. Không lấy `cardinality()` để tính số byte

Một tập bit có 1 vị trí bật ở bit `130` cần 17 byte và 3 long, dù `cardinality()==1`. Lỗi tính theo `cardinality` sẽ cắt mất dữ liệu.

### 13.3. Không lấy `size()` để suy độ dài tối thiểu

Capacity của `BitSet` là chi tiết storage. Một `BitSet(256)` rỗng vẫn export 0 byte. Nếu cần 256-bit record, metadata chiều rộng phải do API/protocol nắm giữ.

### 13.4. Không đảo byte vì tưởng `toByteArray()` là big-endian

Bit `8` phải nằm ở `bytes[1]`, offset 0. Nếu đảo byte của mảng nhỏ, ý nghĩa các chỉ số bit sẽ đổi. Chỉ chuyển endian nếu **đã có** yêu cầu rõ ràng từ định dạng ngoài, và cần test vectors cụ thể.

### 13.5. Không coi signed `byte`/`long` âm là dữ liệu lỗi

Giá trị `-128` là pattern `0x80`; giá trị `Long.MIN_VALUE` là pattern có bit 63 bật. Dùng mask, `Byte.toUnsignedInt` hoặc hex để đọc đúng bit.

### 13.6. Không tự suy byte width từ số bit tối đa trong schema

Một schema 128 cờ không có nghĩa `toByteArray()` luôn trả 16 byte. Nếu bit cao nhất đang bật chỉ là bit `0`, output có 1 byte. Cần padding nếu protocol cố định.

### 13.7. Không tin rằng `valueOf` lưu giữ byte 0 ở cuối

`BitSet.valueOf(new byte[]{1,0,0}).toByteArray()` trả `[1]`; nó giữ bit pattern, không giữ padding/độ rộng của mảng input.

### 13.8. Không nghĩ rằng `long[]` là chuỗi byte little-endian sẵn có

`long[]` là các từ có kiểu dữ liệu; khi lưu file, cần chỉ định writer và byte order. Hai cách output có thể encode cùng bitset nhưng có kích thước padding khác nhau.

### 13.9. Không dùng `toString()` thay cho codec

`BitSet.toString()` hiển thị chỉ số bit theo format đọc được. Nó không phải đặc tả payload có độ rộng, version hoặc byte order cho hệ thống ngoài.

### 13.10. Không làm rơi bit cao khi copy mảng

`Arrays.copyOf(bits.toByteArray(), fixedWidth)` có thể cắt bớt nếu width không đủ. Luôn kiểm tra bit index tối đa/trường hợp overflow trước.

### 13.11. Không giả định kết quả export có thể sửa ngược lại BitSet

Đổi `bytes[0]` hoặc `words[0]` không cập nhật các bit đã lưu trong `BitSet`. Nếu muốn thay đổi bitset, dùng `set`/`clear` hoặc dựng lại bằng `valueOf` rồi thay thế object theo hợp đồng ứng dụng.

### 13.12. Không bỏ qua giới hạn đầu vào từ mạng

Dữ liệu ngoài có thể rất lớn. Trước khi `valueOf` hoặc allocation, kiểm tra độ dài payload, quota, width, version và chính sách lỗi. Với dữ liệu không tin cậy, đừng cấp mảng khổng lồ chỉ dựa vào một length field chưa validate.

## 14. Ma trận kiểm thử đầy đủ

Những tình huống sau có thể dùng làm test khi triển khai exporter/importer:

| Trạng thái `BitSet` | `length` | `toByteArray().length` | `toLongArray().length` | Điều cần khẳng định |
| --- | ---: | ---: | ---: | --- |
| Rỗng | 0 | 0 | 0 | Không có padding tự động |
| `{0}` | 1 | 1 | 1 | Bit thấp nhất |
| `{7}` | 8 | 1 | 1 | Byte đầu có pattern `0x80` |
| `{8}` | 9 | 2 | 1 | Chuyển sang byte thứ hai |
| `{63}` | 64 | 8 | 1 | Bit cao nhất của long đầu |
| `{64}` | 65 | 9 | 2 | Chuyển sang long thứ hai |
| `{127}` | 128 | 16 | 2 | Bit cao nhất của long thứ hai |
| `{128}` | 129 | 17 | 3 | Chuyển sang long thứ ba |
| `{0,7,8,15,23}` | 24 | 3 | 1 | Byte hex `81 81 80` |
| `{0,63,64,70,130}` | 131 | 17 | 3 | Long hex `8000000000000001 41 4` |

### 14.1. Tính đúng của phép biến đổi

Với mọi `BitSet` trong phạm vi được hỗ trợ:

```text
original.equals(BitSet.valueOf(original.toByteArray())) == true

original.equals(BitSet.valueOf(original.toLongArray())) == true

toByteArray().length == (original.length() + 7) / 8

toLongArray().length == (original.length() + 63) / 64
```

Ngoài ra, trong phạm vi mảng byte:

```text
original.get(n) == ((bytes[n / 8] & (1 << (n % 8))) != 0)
```

Và trong phạm vi mảng long:

```text
original.get(n) == ((longs[n / 64] & (1L << (n % 64))) != 0)
```

### 14.2. Property test với bộ dữ liệu xác định

Để giảm nguy cơ kiểm tra thiếu boundary, có thể chạy cùng một bộ 2.000 trạng thái bit ngẫu nhiên **có seed cố định**, rồi kiểm tra đồng thời:

- Độ dài byte và long theo công thức.
- Round-trip của cả hai dạng export.
- Mọi bit trong miền 0..319 khớp chính xác cả hai biểu diễn.

Lưu chương trình sau vào **`BitSetPropertyChecks.java`**:

```java
import java.util.BitSet;
import java.util.Random;

public final class BitSetPropertyChecks {
    public static void main(String[] args) {
        Random random = new Random(20261104L);
        int checked = 0;
        for (int trial = 0; trial < 2000; trial++) {
            BitSet bits = new BitSet();
            for (int k = 0; k < 70; k++) {
                int bit = random.nextInt(300);
                if (random.nextBoolean()) {
                    bits.set(bit);
                } else {
                    bits.clear(bit);
                }
            }
            byte[] b = bits.toByteArray();
            long[] l = bits.toLongArray();
            if (b.length != (bits.length() + 7) / 8) {
                throw new AssertionError("byte length");
            }
            if (l.length != (bits.length() + 63) / 64) {
                throw new AssertionError("long length");
            }
            if (!bits.equals(BitSet.valueOf(b)) || !bits.equals(BitSet.valueOf(l))) {
                throw new AssertionError("round trip");
            }
            for (int index = 0; index < 320; index++) {
                boolean fromBytes = index < b.length * 8
                        && ((b[index / 8] & (1 << (index % 8))) != 0);
                boolean fromLongs = index < l.length * 64
                        && ((l[index / 64] & (1L << (index % 64))) != 0);
                if (bits.get(index) != fromBytes || bits.get(index) != fromLongs) {
                    throw new AssertionError("bit mismatch at " + index);
                }
            }
            checked++;
        }
        System.out.println("roundTrips=" + checked);
        System.out.println("bitMappingVerified=true");
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BitSetPropertyChecks.java
java BitSetPropertyChecks
```

Stdout chính xác:

```text
roundTrips=2000
bitMappingVerified=true
```

Seed làm cho phép thử lặp lại được. Nó là **một kiểm thử bổ sung**, không thay thế test vectors ranh giới 7/8, 63/64, trailing zeros hoặc tích hợp protocol giữa các hệ thống. Trong CI, bạn có thể giữ test này vì nó dùng input và số vòng hữu hạn, không cần phụ thuộc ngoài.

## 15. Quy trình áp dụng vào dự án

Khi cần xuất một `BitSet` thật:

1. **Xác định output consumer:** cần `byte[]` (I/O, codec) hay `long[]` (logic xử lý theo 64-bit words)?
2. **Xác định bit numbering:** bit 0 là cờ nào, có reserved bits, có version của schema không?
3. **Xác định quy tắc kích thước:** minimal như API Java hay fixed-size do format ngoài yêu cầu?
4. **Kiểm tra giới hạn:** chỉ số bit cao nhất, width, size limit, khả năng overflow/cắt dữ liệu.
5. **Nếu fixed width:** chuẩn hóa theo byte order đã thống nhất, padding/copy sau khi validate.
6. **Nếu ghi long[] ra byte:** chỉ định little/big-endian của từng `long` trong codec bên ngoài.
7. **Thử round-trip trong Java:** `valueOf(toByteArray())` và `valueOf(toLongArray())` phải giữ các bit bật.
8. **Thử interop:** kiểm tra các test vectors có bit 0, bit 7, 8, 63, 64, 127, 128 và trường hợp bitset rỗng ở cả hai phía.
9. **Kiểm tra dữ liệu signed:** khi log/debug dùng unsigned/hex, không coi byte âm là lỗi.
10. **Đánh giá snapshot/concurrency:** không xuất trong lúc state đang bị sửa mà không có coordination phù hợp.
11. **Ghi rõ contract của API public:** định dạng, byte order, width, version, semantic của bit flags.
12. **Đo chi phí khi cần:** dữ liệu thưa, nhiều lần export hoặc payload lớn có thể tạo allocation đáng kể.

### Checklist khi code review

- [ ] Không nhầm `length()`, `size()` và `cardinality()`.
- [ ] Không đảo vị trí byte khi dùng `BitSet.toByteArray()`.
- [ ] Có test xác nhận bit n nằm ở byte `n/8`, offset `n%8`.
- [ ] Có test xác nhận bit n nằm ở long `n/64`, offset `n%64`.
- [ ] Hiểu signed `byte`/`long` và dùng unsigned/hex để so pattern.
- [ ] Xác nhận empty bitset trả array rỗng.
- [ ] Xác nhận bit cao bị clear thì mảng export có thể ngắn đi.
- [ ] Nếu payload fixed-size, đã padding đúng phía và kiểm tra bit không vượt width.
- [ ] Nếu format ngoài Java, có hợp đồng endian rõ và test cross-language.
- [ ] Có test round-trip bằng hai overload `BitSet.valueOf`.
- [ ] Không trông đợi mảng export share storage với BitSet.
- [ ] Có giới hạn memory/payload và tránh thiếu synchronization khi serialize mutable state.

## 16. Bài tập thực hành

**Bài 1 — Tính byte theo bit index.** Cho `BitSet` có các bit `{0,1,7,8,14}`. Hãy tính bằng tay `toByteArray()` dạng hex và số byte. Sau đó viết chương trình `BitSet` để xác minh.

**Bài 2 — Ranh giới 7/8.** Chỉ bật bit `7` và so sánh với trường hợp chỉ bật bit `8`. Kết quả `toByteArray()` có độ dài và vị trí nonzero như thế nào?

**Bài 3 — Ranh giới 63/64.** Với `{63,64}`, hãy dự đoán `toLongArray().length`, phần tử nào âm khi in signed decimal, và mỗi long có pattern hex ra sao.

**Bài 4 — Giá trị có dấu.** Tại sao byte `0x80` in thành `-128`? Viết lệnh dùng `Byte.toUnsignedInt` để trả `128`, rồi kiểm tra bit offset `7` đang bật.

**Bài 5 — Xóa bit cao.** Cho `{0,15}`, in hai độ dài export, xóa bit `15` rồi in lại. Vì sao `size()` không phù hợp làm căn cứ cắt payload?

**Bài 6 — Fixed width.** Một protocol yêu cầu đúng 8 byte. Dùng cách trong `FixedWidthDemo` để encode `{0,12,63}`; tạo thử `{64}` và xác nhận phép encode phải bị từ chối.

**Bài 7 — Dữ liệu nhận có padding.** Decode `new byte[]{1,0,0,0}`, rồi xuất lại. Tại sao output tối thiểu chỉ có `[1]`? Nếu cần gửi lại đúng 4 byte thì làm thế nào?

**Bài 8 — Word và byte.** Bật bit `63` và `64`. So sánh `toByteArray().length` và `toLongArray().length`; giải thích tại sao hai mảng không thể so trực tiếp về số phần tử để kết luận kích thước byte.

**Bài 9 — Interop.** Một service ghi bitmap theo big-endian, một service khác khôi phục bằng `BitSet.valueOf(byte[])`. Hãy chỉ ra test vector phát hiện lệch byte order trước khi triển khai.

**Bài 10 — Sparse.** Một `BitSet` chỉ có bit `1_000_000` bật. Tính kích thước byte và long export; so với việc gửi một chỉ số nguyên. Bài toán nào phù hợp kiểu sparse thay vì dense?

**Bài 11 — Concurrency.** Một thread có thể `set`/`clear` cờ khi thread khác gọi `toByteArray`. Vì sao không được tự giả định output là snapshot nguyên tử? Đề xuất giải pháp ownership hoặc synchronization.

**Bài 12 — Property test.** Chạy `BitSetPropertyChecks` rồi thêm các bit test cố định ở biên 7/8, 63/64, 127/128. Nêu lý do test property có seed không thay thế được test integration với protocol ngoài Java.

## Tài liệu chính thức còn hiệu lực

- [Java SE 17 — `java.util.BitSet` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html): hợp đồng `toByteArray()`, `toLongArray()`, `valueOf(byte[])`, `valueOf(long[])`, `length()`, `size()`, `cardinality()`, cùng mô tả thứ tự bit.
- [Java SE 17 — `java.lang.Byte` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): `Byte.toUnsignedInt` và cách chuyển giá trị byte có dấu sang int unsigned.
- [Java SE 17 — `java.lang.Long` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): biểu diễn signed long, `toHexString`.
- [Java SE 17 — `java.util.Arrays` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `copyOf` dùng cho padding fixed-size sau khi kiểm tra không cắt bit.
- [Java SE 17 — `java.nio.ByteBuffer` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): thao tác chuyển long thành byte và byte order khi mã hóa protocol.
- [Java Language Specification 17 — `4.2 Primitive Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2): ngữ nghĩa kiểu `byte` và `long` trong Java.

**Kết luận:** `BitSet.toByteArray()` xuất các byte thấp trước, `BitSet.toLongArray()` xuất các từ 64 bit thấp trước; cả hai trả mảng **tối thiểu chứa mọi bit đang bật**. Dùng `BitSet.valueOf` để khôi phục tập bit, nhưng đừng coi chúng tự lưu **độ rộng, version hoặc byte order của protocol ngoài Java**. Kiểm tra công thức vị trí bit, byte signed, padding, giới hạn và round-trip trước khi đưa dữ liệu vào I/O hoặc giao tiếp hệ thống.