# `BitSet` trong Java: Lưu cờ, lọc tập chỉ số và kiểm chứng chuyển đổi

## 1. Vì sao dùng `BitSet`?

Trong nhiều bài toán, mỗi phần tử chỉ cần trạng thái **bật hoặc tắt**, hoặc ứng dụng phải lưu một **tập các chỉ số nguyên không âm**:

- Tài khoản có hay không một quyền, cờ tính năng hoặc trạng thái xác nhận.
- Những bản ghi nào đạt điều kiện lọc: đã kích hoạt, đã thanh toán, không bị khóa.
- Những vị trí nào đã xử lý trong một lô dữ liệu hoặc những chỉ số nào được đánh dấu trong bitmap.
- Dữ liệu bit cần đóng gói sang `byte[]` hoặc `long[]` để lưu và khôi phục.

`java.util.BitSet` là một **tập bit thay đổi kích thước theo nhu cầu**. Mỗi bit được định danh bằng một chỉ số nguyên không âm: bit bằng `true` tương ứng với phần tử đang có trong tập, bit bằng `false` tương ứng với phần tử không có.

```java
import java.util.BitSet;

BitSet flags = new BitSet();
flags.set(0);          // Bật bit 0.
flags.set(3);          // Bật bit 3.
flags.set(9);          // Bật bit 9.
System.out.println(flags); // {0, 3, 9}
```

Đây là **đoạn minh họa đặt trong phương thức**, không phải tệp Java độc lập. Chương trình có thể biên dịch và chạy trực tiếp bằng Java 17+ nằm ở mục 9.

**Lưu ý phiên bản:** `BitSet` đã có trước Java 7 và vẫn được dùng trong Java hiện đại. Những API quan trọng cho **chuyển đổi byte/long** như `BitSet.valueOf(byte[])`, `BitSet.valueOf(long[])`, `toByteArray()` và `toLongArray()` được hỗ trợ từ **Java 7**. `BitSet.stream()` có từ **Java 8**, còn tiện ích in hex `HexFormat` trong ví dụ đầy đủ có từ **Java 17**. Không có nội dung nào ở đây yêu cầu sử dụng kỹ thuật Java đã lỗi thời.

## 2. Biểu diễn và cách đánh số bit

Hãy tưởng tượng một dãy bit theo chỉ số:

```text
Chỉ số:    0 1 2 3 4 5 6 7 8 9
Giá trị:   1 0 0 1 0 0 0 0 0 1

Tập chỉ số được bật: {0, 3, 9}
```

`BitSet` làm việc với **chỉ số zero-based** và không lưu tên tượng trưng của cờ. Trong ví dụ cờ tính năng:

```java
private static final int VERIFIED = 0;
private static final int ENABLED = 3;
private static final int BETA = 9;
```

Đây là các **hằng số đặt trong một lớp Java**. Với chúng, `flags.get(VERIFIED)` diễn đạt rõ ý nghĩa hơn `flags.get(0)`. Chính ứng dụng quyết định cờ nào dùng chỉ số nào; `BitSet` không biết cờ thứ 9 có tên “BETA”.

Các thao tác cơ bản:

| API | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `set(index)` | Bật bit thành `true` | `bits.set(4)` |
| `set(index, boolean)` | Gán bit bằng giá trị chỉ định | `bits.set(4, enabled)` |
| `get(index)` | Đọc trạng thái, trả `boolean` | `bits.get(4)` |
| `clear(index)` | Tắt một bit | `bits.clear(4)` |
| `flip(index)` | Đảo một bit | `bits.flip(4)` |
| `set(from, to)` | Bật khoảng chỉ số `[from, to)` | `bits.set(2, 6)` |
| `clear(from, to)` | Tắt khoảng `[from, to)` | `bits.clear(2, 6)` |
| `flip(from, to)` | Đảo các bit trong khoảng `[from, to)` | `bits.flip(0, 8)` |
| `clear()` | Tắt toàn bộ bit | `bits.clear()` |

Một phép kiểm tra ví dụ:

```java
BitSet flags = new BitSet();
flags.set(VERIFIED);
flags.set(ENABLED);
flags.set(BETA);

boolean allowed = flags.get(ENABLED); // true
flags.clear(ENABLED);
boolean after = flags.get(ENABLED);   // false
```

Đoạn này nằm trong lớp có ba hằng số `VERIFIED`, `ENABLED` và `BETA` như trên. `clear` chỉ tắt bit; không làm dịch vị trí những bit khác. Ví dụ `clear(3)` không biến bit 9 thành bit 8.

**Lưu ý biên:** Chỉ số âm không hợp lệ, ví dụ `set(-1)` gây `IndexOutOfBoundsException`. `BitSet` không phải một bảng ánh xạ key–value nên nếu ID nghiệp vụ là chuỗi, UUID hoặc số âm, phải dùng một **ánh xạ hợp lệ sang chỉ số** trước khi thao tác.

## 3. Ứng dụng 1 — lưu tập cờ tính năng/trạng thái

Giả sử hệ thống có ba cờ:

| Chỉ số ổn định | Ý nghĩa | Ban đầu |
| --- | --- | --- |
| `0` | Đã xác minh | Bật |
| `3` | Đang kích hoạt | Bật |
| `9` | Được bật beta | Bật |

Ta có thể lưu chúng bằng một `BitSet`:

```java
BitSet flags = new BitSet();
flags.set(0);
flags.set(3);
flags.set(9);

System.out.println(flags);       // {0, 3, 9}
System.out.println(flags.get(3)); // true

flags.clear(3);
System.out.println(flags);       // {0, 9}
```

Đoạn trên có thể đặt trong `main` với `import java.util.BitSet;`.

### 3.1. Khi nào phù hợp?

`BitSet` hữu ích khi số lượng **loại cờ** có thể lớn, khi muốn kết hợp các tập bit bằng phép toán tập hợp, hoặc khi cần chuyển ra dạng bit/byte tương đối gọn.

Tuy nhiên, muốn dùng lâu dài phải xác định **quy ước chỉ số**:

- Không tự động đổi chỉ số của một cờ giữa hai phiên bản dữ liệu đã lưu.
- Không dựa vô điều kiện vào vị trí các phần tử trong danh sách cấu hình có thể bị sắp xếp lại.
- Nếu xuất dữ liệu sang hệ thống khác, cần ghi lại **bảng ý nghĩa chỉ số** và phiên bản của bảng.
- Với trạng thái quan trọng, ngoài `BitSet` còn cần quy tắc xác thực, phân quyền và lưu trữ phía server; một bit do phía client cung cấp **không phải bằng chứng được phép truy cập**.

### 3.2. So sánh với `EnumSet` và mặt nạ `long`

| Cách biểu diễn | Điểm mạnh | Giới hạn cần nhớ |
| --- | --- | --- |
| `BitSet` | Chỉ số bit linh hoạt, phép giao/hợp/hiệu, chuyển `byte[]`/`long[]` | Không giữ tên cờ; bit cao có thể gây tốn bộ nhớ |
| `EnumSet<Feature>` | Biểu diễn rõ tên phần tử enum, API tập hợp an toàn kiểu | Gắn với một enum; không tự quy định wire format ổn định |
| `long` làm bit mask | Rất gọn cho tối đa 64 vị trí bit trong một giá trị | Phải dùng shift/mask cẩn thận; cố định 64 bit |
| `boolean[]` | Chỉ số trực tiếp và rõ ràng, độ dài cố định | Không sẵn các phép toán tập bit hay codec như `BitSet` |
| `Set<Integer>` | Phù hợp tập chỉ số thưa/sparse hoặc IDs rời rạc | Tốn overhead đối tượng hơn với chỉ số dày đặc |

Nếu các quyền là một **enum có danh sách tên cố định**, `EnumSet` thường dễ đọc hơn về nghiệp vụ. Nếu cần lưu/khôi phục **những vị trí bit có quy ước ổn định**, `BitSet` có giá trị thực tiễn. Không chọn `BitSet` chỉ vì “bit tiết kiệm bộ nhớ”; cách phân bố chỉ số và yêu cầu giao thức mới quyết định.

## 4. Ứng dụng 2 — lọc tập chỉ số bằng giao, hợp và hiệu

Giả sử một lô có **8 bản ghi**, đánh số `0` đến `7`:

- `active`: các bản ghi đang hoạt động: `{0, 2, 3, 5, 7}`.
- `paid`: các bản ghi đã thanh toán: `{2, 3, 6, 7}`.
- `blocked`: các bản ghi bị chặn: `{3, 6}`.

Ta cần tập chỉ số:

> Đang hoạt động **và** đã thanh toán **và không** bị chặn.

Đây là một bài toán phép toán tập hợp:

```text
eligible = (active ∩ paid) \ blocked

active   = {0, 2, 3, 5, 7}
paid     = {2, 3, 6, 7}
blocked  = {3, 6}

active ∩ paid       = {2, 3, 7}
(active ∩ paid) \ blocked = {2, 7}
```

`BitSet` có các phương thức tương đương:

| Phép toán tập hợp | Phương thức | Thay đổi đối tượng |
| --- | --- | --- |
| Giao `A ∩ B` | `a.and(b)` | **Sửa `a`** |
| Hợp `A ∪ B` | `a.or(b)` | **Sửa `a`** |
| Hiệu `A \ B` | `a.andNot(b)` | **Sửa `a`** |
| Hiệu đối xứng `A △ B` | `a.xor(b)` | **Sửa `a`** |
| Hai tập có chung phần tử? | `a.intersects(b)` | Không sửa |
| Độ lớn tập được bật | `a.cardinality()` | Không sửa |

### 4.1. Đừng vô tình sửa dữ liệu nguồn

Vì `and`, `or`, `andNot` và `xor` làm thay đổi **đối tượng nhận lời gọi**, không nên viết trực tiếp:

```java
active.and(paid); // Đã THAY ĐỔI active.
active.andNot(blocked);
```

Nếu `active` là mặt nạ được chia sẻ để dùng tiếp, hai lệnh trên phá mất tập ban đầu. Cách an toàn là **tạo bản sao**:

```java
BitSet eligible = (BitSet) active.clone();
eligible.and(paid);
eligible.andNot(blocked);
```

Sau đó `eligible` có các bit `{2, 7}`, còn `active` vẫn giữ dữ liệu cũ.

`clone()` ở đây tạo một `BitSet` độc lập; việc sửa những bit của `eligible` không thay đổi bit của `active`. Đây là trường hợp **copy trước khi biến đổi** đặc biệt hữu ích khi nhiều bước lọc sử dụng chung các mask nguồn.

### 4.2. Khi cần phủ định điều kiện, hãy chỉ rõ tập vũ trụ

Nếu muốn “tất cả bản ghi không bị chặn”, không thể hiểu đơn giản là phủ định vô hạn các bit vì phía ngoài phạm vi dữ liệu còn vô số chỉ số chưa dùng.

Với `rowCount = 8`:

```java
BitSet available = new BitSet();
available.set(0, rowCount);  // Bật [0, 8).
available.andNot(blocked);  // Xóa những chỉ số bị chặn.
```

Đây là đoạn minh họa khi biến `rowCount` và `blocked` đã tồn tại. Kết quả chỉ nằm trong **tập vũ trụ có giới hạn `[0, rowCount)`**. Nếu dùng `flip(0,rowCount)` trên một mặt nạ, bạn cũng cần kiểm tra rằng mặt nạ ấy không chứa những bit ngoài phạm vi. Không được suy rằng “phủ định BitSet” tạo một tập hữu hạn một cách tự động.

### 4.3. Dùng `intersects` để kiểm tra có trùng hay không

```java
boolean hasOverlap = paid.intersects(blocked); // true
```

Trong ví dụ này, có các chỉ số chung `3` và `6`. `intersects` tránh phải tạo một tập trung gian chỉ để hỏi **có ít nhất một bit cùng bật hay không**.

## 5. Ứng dụng 3 — liệt kê chỉ số được bật để xử lý bản ghi

Sau khi tính `eligible`, có thể duyệt các vị trí được bật bằng `nextSetBit`:

```java
for (int index = eligible.nextSetBit(0);
     index >= 0;
     index = eligible.nextSetBit(index + 1)) {

    System.out.println("process row " + index);
}
```

Với `eligible = {2, 7}`, kết quả:

```text
process row 2
process row 7
```

`nextSetBit(fromIndex)` trả **chỉ số bit bật nhỏ nhất không nhỏ hơn `fromIndex`**; nếu không còn, trả `-1`. Đây là cách duyệt **những chỉ số thực sự có mặt**, thay vì chạy qua toàn bộ dải `0..max` và gọi `get` cho từng vị trí.

Một phương thức helper:

```java
private static List<Integer> positions(BitSet bits) {
    List<Integer> out = new ArrayList<>();
    for (int index = bits.nextSetBit(0);
         index >= 0;
         index = bits.nextSetBit(index + 1)) {
        out.add(index);
    }
    return out;
}
```

Đoạn này thuộc lớp đã import `BitSet`, `List` và `ArrayList`. Nó hữu ích khi cần truyền các chỉ số được chọn sang API chỉ chấp nhận `List<Integer>`. Bản thân `BitSet` **không phải** một `Set<Integer>` triển khai `java.util.Set`.

Từ **Java 8**, có thể dùng `bits.stream()` để lấy một `IntStream` gồm các chỉ số bit đang bật theo thứ tự tăng dần:

```java
int[] indices = eligible.stream().toArray(); // [2, 7]
```

Chọn `nextSetBit` khi muốn vòng lặp trực tiếp hoặc tương thích với cú pháp Java 7; chọn `stream()` khi đã có pipeline xử lý `IntStream`. Khi đối tượng `BitSet` được chia sẻ, không nên sửa nó đồng thời trong quá trình duyệt mà không có phối hợp thích hợp.

### 5.1. `get(from, to)` không giữ chỉ số gốc

Một API dễ hiểu nhầm là:

```java
BitSet active = new BitSet();
active.set(0);
active.set(2);
active.set(3);
active.set(5);
active.set(7);

BitSet window = active.get(2, 8);
System.out.println(window); // {0, 1, 3, 5}
```

`get(2,8)` **tạo một BitSet mới cho đoạn `[2,8)`**, nhưng các bit của kết quả được **đánh số lại từ 0**:

- Bit gốc `2` trở thành bit `0`.
- Bit gốc `3` trở thành bit `1`.
- Bit gốc `5` trở thành bit `3`.
- Bit gốc `7` trở thành bit `5`.

Nếu hệ thống cần **ID ban đầu** thay vì chỉ số tương đối, phải cộng lại offset `2` khi đọc các bit trong `window`, hoặc dùng `nextSetBit` trên tập gốc với điều kiện giới hạn `index < to`.

## 6. Ba khái niệm phải phân biệt: `cardinality`, `length` và `size`

Một `BitSet` không lưu một “độ dài logic cố định” giống mảng dữ liệu. Các phương thức trả về những ý nghĩa khác nhau:

| Phương thức | Ý nghĩa |
| --- | --- |
| `cardinality()` | **Số bit `true`**, tương đương số chỉ số được chọn |
| `length()` | Chỉ số bit bật cao nhất **cộng 1**; nếu không có bit bật, trả `0` |
| `size()` | Số bit của **vùng lưu trữ nội bộ đã cấp phát** theo cách triển khai; không dùng làm số cờ hoặc độ dài dữ liệu giao thức |
| `isEmpty()` | `true` nếu không có bit bật nào |
| `toByteArray().length` | Số byte **tối thiểu** để biểu diễn các bit bật, loại bỏ byte 0 cao cuối |
| `toLongArray().length` | Số phần tử 64-bit **tối thiểu** để biểu diễn các bit bật |

Ví dụ đặt các bit `0`, `7`, `8`, `63`, `64` và `70`:

```text
Bit đang bật: {0, 7, 8, 63, 64, 70}

cardinality = 6
length      = 71  (bit cao nhất là 70)
byte count  = 9
long count  = 2
```

**Không lấy `length()` để đếm số bản ghi thỏa lọc.** Với tập `{2,7}`, `cardinality() == 2` nhưng `length() == 8`. Cũng không lấy `size()` để suy ra số phần tử đang dùng: nó nói về dung lượng vùng lưu trữ, có thể lớn hơn nhiều so với dữ liệu thực tế.

Một minh họa:

```java
BitSet empty = new BitSet(128);
empty.set(1);
empty.clear(1);

System.out.println(empty.length());            // 0
System.out.println(empty.toByteArray().length); // 0
System.out.println(empty.size());              // 128
```

Dù ban đầu yêu cầu dung lượng 128 bit, sau khi không còn bit nào được bật, `length() == 0` và `toByteArray()` trả mảng rỗng. Kích thước vùng cấp phát **không phải metadata chiều rộng** của payload đã được chuyển đổi.

## 7. Ứng dụng 4 — chuyển đổi `BitSet` sang `byte[]` và `long[]`

### 7.1. Các API chính

`BitSet` cung cấp cặp chuyển đổi:

```java
byte[] bytes = bits.toByteArray();
BitSet fromBytes = BitSet.valueOf(bytes);

long[] words = bits.toLongArray();
BitSet fromWords = BitSet.valueOf(words);
```

Đây là ví dụ trong phương thức có biến `bits` kiểu `BitSet`. Từ Java 7, các API này cho phép lưu/khôi phục **tập bit được bật** mà không cần tự triển khai vòng lặp đóng gói từng bit.

**Cam kết round-trip đúng bản chất:**

```java
BitSet.valueOf(bits.toByteArray()).equals(bits) == true
BitSet.valueOf(bits.toLongArray()).equals(bits) == true
```

Hai biểu thức trên biểu thị **bất biến cần kiểm thử** cho một `BitSet` thông thường. Kết quả tương đương theo các bit được bật; **không có nghĩa** dung lượng cấp phát `size()` hoặc “độ rộng dữ liệu cố định” lúc tạo ban đầu được khôi phục nguyên vẹn.

### 7.2. Thứ tự bit và byte: little-endian theo quy tắc của `BitSet`

`toByteArray` biểu diễn bit index theo quy tắc:

```text
bit index i -> byte ở vị trí i / 8
             -> bit bên trong byte ở vị trí i % 8
```

Vì vậy, bit `0` ứng với **bit thấp nhất** của byte đầu tiên, bit `7` ứng với **bit cao nhất** của byte đầu tiên và bit `8` ứng với **bit thấp nhất** của byte thứ hai.

Ví dụ:

```java
BitSet bits = new BitSet();
bits.set(0);
bits.set(7);
bits.set(8);

byte[] bytes = bits.toByteArray();
```

Nội dung byte theo dạng hex là:

```text
Index   Binary     Hex
0       10000001   81
1       00000001   01

Payload hex: 8101
```

Cách viết bit trong phần nhị phân ở trên dùng cách trình bày thông thường từ bit cao tới bit thấp trong **một byte**. Quy tắc ánh xạ chỉ số của `BitSet` vẫn là **least significant bit first** ở từng byte, đồng thời byte có chỉ số nhỏ chứa các bit có chỉ số nhỏ.

Khi chuyển sang `long[]`, phần tử `words[0]` chứa các bit `0..63`, `words[1]` chứa các bit `64..127`, v.v. Thứ tự này quan trọng nếu bạn định chuyển payload sang hệ thống khác dùng **network byte order** hoặc biểu diễn big-endian; không được mặc định mọi chuẩn dữ liệu đều có cùng byte order với `BitSet`.

### 7.3. Byte Java có dấu không làm sai các bit

Trong Java, kiểu `byte` là số nguyên 8-bit **có dấu**, nên giá trị hex `0x81` có thể được in dạng thập phân là `-127` nếu đọc như `byte`. Điều này **không làm thay đổi 8 bit** được lưu.

Nếu cần truyền hoặc lưu payload, nên kiểm tra bằng **hex** hoặc thao tác với bit; đừng giải thích một byte âm thành một chỉ số bit âm. Từ Java 17 có thể in hex bằng:

```java
System.out.println(java.util.HexFormat.of().formatHex(bytes));
```

Đoạn này minh họa khi biến `bytes` đã tồn tại. `HexFormat` là API **Java 17+**; không có trong Java 7, dù `BitSet.toByteArray()` đã có từ Java 7.

### 7.4. Bit cao không nhất thiết phải là bit gần đầu

Một bài kiểm tra tốt nên đặt bit ở ranh giới **byte và word**:

```java
BitSet original = new BitSet();
for (int index : new int[] {0, 7, 8, 63, 64, 70}) {
    original.set(index);
}
```

Vì bit cao nhất là `70`:

- `original.length() == 71`.
- `original.cardinality() == 6`.
- `original.toByteArray().length == 9` vì cần byte chứa bit `70`.
- `original.toLongArray().length == 2` vì bit `64` trở lên nằm ở phần tử `long` thứ hai.
- `java.util.HexFormat.of().formatHex(original.toByteArray())` trả `"810100000000008041"`.

Đặt bit ở vị trí `63` và `64` giúp bắt lỗi nhầm ranh giới giữa hai phần tử `long`. Đặt bit ở `7` và `8` giúp phát hiện lỗi nhầm ranh giới giữa hai byte.

## 8. Kiểm chứng chuyển đổi: test round-trip, biên và tính độc lập

Chỉ in `byte[]` chưa đủ để biết mã serialize/deserialze của bạn đúng. Cần **kiểm chứng nhiều tính chất**.

### 8.1. Round-trip phải giữ đúng tập bit

```java
BitSet original = new BitSet();
original.set(0);
original.set(7);
original.set(8);
original.set(63);
original.set(64);
original.set(70);

BitSet restoredBytes = BitSet.valueOf(original.toByteArray());
BitSet restoredLongs = BitSet.valueOf(original.toLongArray());

if (!original.equals(restoredBytes)
        || !original.equals(restoredLongs)) {
    throw new AssertionError("BitSet round-trip mismatch");
}
```

Đoạn trên có thể đặt trong `main`. Phương thức `BitSet.equals` so sánh **các bit được bật**, không buộc hai đối tượng cùng dung lượng nội bộ.

### 8.2. Không được giả định các bit 0 ở cuối được giữ như metadata

Giả sử ứng dụng lưu **một mặt nạ đúng 128 vị trí**, nhưng mới bật một bit nhỏ:

```java
BitSet bits = new BitSet(128);
bits.set(1);

byte[] payload = bits.toByteArray(); // 1 byte, không phải 16 byte.
```

Khi cần giao thức cố định 128 bit, hãy lưu thêm **độ rộng `128`** hoặc chuẩn hóa payload theo format đã thống nhất. `toByteArray()` trả biểu diễn tối thiểu và **loại bỏ các byte cao toàn 0**. Với `BitSet` rỗng, `toByteArray()` trả mảng rỗng.

Không dùng `bits.size()` làm số lượng bit logic. Nó phản ánh dung lượng nội bộ và có thể khác độ rộng do ứng dụng định nghĩa. Một giao thức cố định 128 bit có nghĩa **hợp đồng ngoài `BitSet` biết 128**, không phải “BitSet ghi nhớ mọi bit 0 ở cuối”.

### 8.3. Khôi phục mảng không có nghĩa giữ cùng tham chiếu mảng

`BitSet.valueOf(bytes)` tạo một đối tượng mới từ nội dung mảng. Không nên thiết kế phụ thuộc vào việc `BitSet` chia sẻ vùng nhớ của `bytes`. Khi cần kiểm chứng, tạo bản khôi phục rồi **thay đổi mảng nguồn**:

```java
byte[] bytes = original.toByteArray();
BitSet decoded = BitSet.valueOf(bytes);

bytes[0] = 0;

boolean independent = decoded.equals(original); // true
```

Đây là đoạn minh họa khi `original` đã được khai báo. Nó cho thấy đối tượng được giải mã vẫn giữ nội dung bit từ thời điểm khôi phục. Tương tự, khi xuất dữ liệu bằng `toByteArray()`, bạn đang có một mảng để truyền/lưu; sửa mảng đó không phải là cách cập nhật các bit của `BitSet` gốc.

### 8.4. Test theo bảng ca quan trọng

| Tập bit ban đầu | Ý nghĩa ca test | Điều cần xác minh |
| --- | --- | --- |
| `{}` | Tập rỗng | Payload rỗng; round-trip trả tập rỗng |
| `{0}` | Bit đầu tiên | Byte thấp chứa `0x01` |
| `{7}` | Cuối byte đầu | Byte thấp chứa `0x80` |
| `{8}` | Đầu byte thứ hai | Có đúng hai byte khi bit cao nhất là `8` |
| `{63}` | Cuối `long` đầu | Đúng một word |
| `{64}` | Đầu `long` thứ hai | Đúng hai word |
| `{0,7,8,63,64,70}` | Trộn ranh giới byte/word | Hai round-trip bằng nhau; hex đúng |
| `{1}` với độ rộng yêu cầu 128 | Bit 0 cao ở cuối | Payload không tự giữ độ rộng 128 |
| Tập bất kỳ không âm | Tính tổng quát | `valueOf(toByteArray()).equals(original)` và `valueOf(toLongArray()).equals(original)` |

Nếu dùng test sinh dữ liệu ngẫu nhiên, hãy cố ý sinh bit gần ranh giới `7/8`, `63/64` và nhiều bit cao, thay vì chỉ các vị trí `0..5`. Nên kiểm thử cả bit tắt ở cuối, vì lỗi về **độ rộng logic** thường bị che bởi việc round-trip vẫn đúng theo tập bit.

## 9. Ví dụ Java 17+ độc lập: lưu cờ, lọc chỉ số và round-trip

Chương trình sau gom ba nhu cầu thực tế. Nó tự chạy, không cần tệp, database hoặc thư viện ngoài, dùng `AssertionError` nếu bất biến kiểm chứng không đúng và in kết quả dễ quan sát.

Tạo tệp **`BitSetApplicationsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.BitSet;
import java.util.HexFormat;
import java.util.List;

public final class BitSetApplicationsDemo {
    private static final int VERIFIED = 0;
    private static final int ENABLED = 3;
    private static final int BETA = 9;

    private static BitSet bits(int... positions) {
        BitSet out = new BitSet();
        for (int position : positions) {
            out.set(position);
        }
        return out;
    }

    private static List<Integer> positions(BitSet bits) {
        List<Integer> out = new ArrayList<>();
        for (int index = bits.nextSetBit(0);
             index >= 0;
             index = bits.nextSetBit(index + 1)) {
            out.add(index);
        }
        return out;
    }

    private static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        BitSet flags = new BitSet();
        flags.set(VERIFIED);
        flags.set(ENABLED);
        flags.set(BETA);
        System.out.println("flags = " + flags);
        System.out.println("enabled = " + flags.get(ENABLED));
        flags.clear(ENABLED);
        System.out.println("after disable = " + flags);

        BitSet active = bits(0, 2, 3, 5, 7);
        BitSet paid = bits(2, 3, 6, 7);
        BitSet blocked = bits(3, 6);
        BitSet selected = (BitSet) active.clone();
        selected.and(paid);
        selected.andNot(blocked);
        check(selected.equals(bits(2, 7)), "filter");
        check(active.equals(bits(0, 2, 3, 5, 7)), "source unchanged");
        System.out.println("eligible = " + selected);
        System.out.println("eligible indices = " + positions(selected));
        System.out.println("eligible count = " + selected.cardinality());
        System.out.println("active window [2,8) = " + active.get(2, 8));

        BitSet original = bits(0, 7, 8, 63, 64, 70);
        byte[] bytes = original.toByteArray();
        long[] words = original.toLongArray();
        BitSet fromBytes = BitSet.valueOf(bytes);
        BitSet fromWords = BitSet.valueOf(words);
        check(fromBytes.equals(original), "byte roundtrip");
        check(fromWords.equals(original), "word roundtrip");
        System.out.println("original = " + original);
        System.out.println("hex little endian = " + HexFormat.of().formatHex(bytes));
        System.out.println("word count = " + words.length);
        System.out.println("byte count = " + bytes.length);
        System.out.println("length = " + original.length());
        System.out.println("cardinality = " + original.cardinality());
        System.out.println("byte roundtrip = " + fromBytes.equals(original));
        System.out.println("long roundtrip = " + fromWords.equals(original));
        bytes[0] = 0;
        System.out.println("decoded independent = " + fromBytes.equals(original));

        BitSet empty = new BitSet(128);
        empty.set(1);
        empty.clear(1);
        System.out.println("empty logical length = " + empty.length());
        System.out.println("empty encoded bytes = " + empty.toByteArray().length);
        System.out.println("empty allocated bits = " + empty.size());
        System.out.println("checks = PASS");
    }
}
```

Biên dịch bằng JDK 17 trở lên, bật lint và buộc compiler dừng nếu có cảnh báo:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 BitSetApplicationsDemo.java
java BitSetApplicationsDemo
```

**Stdout chính xác:**

```text
flags = {0, 3, 9}
enabled = true
after disable = {0, 9}
eligible = {2, 7}
eligible indices = [2, 7]
eligible count = 2
active window [2,8) = {0, 1, 3, 5}
original = {0, 7, 8, 63, 64, 70}
hex little endian = 810100000000008041
word count = 2
byte count = 9
length = 71
cardinality = 6
byte roundtrip = true
long roundtrip = true
decoded independent = true
empty logical length = 0
empty encoded bytes = 0
empty allocated bits = 128
checks = PASS
```

### 9.1. Phần lưu cờ

`flags` bật ba cờ rồi tắt `ENABLED`. Phương thức `get(ENABLED)` trả `true` trước khi tắt; sau lệnh `clear`, tập cờ còn `{0,9}`.

### 9.2. Phần lọc chỉ số

`selected` được sao chép từ `active`, rồi giao với `paid` và trừ `blocked`. Hai phép `check` kiểm chứng:

1. Kết quả chính xác phải là `{2,7}`.
2. `active` vẫn giữ nguyên sau khi xử lý vì phép toán đã thực hiện trên bản sao.

`positions` sử dụng `nextSetBit` để tạo danh sách `[2,7]`. `cardinality()` bằng 2 là **số phần tử được chọn**, không phải chỉ số lớn nhất +1. `active.get(2,8)` minh họa việc đổi gốc chỉ số, nên ra `{0,1,3,5}`.

### 9.3. Phần chuyển đổi

Các bit `0,7,8,63,64,70` đi qua cả ranh giới byte lẫn word. Chương trình gọi `toByteArray`/`toLongArray`, khôi phục bằng `valueOf` và kiểm tra `equals` hai chiều chuyển đổi. Chuỗi hex `810100000000008041` giúp xác nhận vị trí bit theo quy tắc little-endian.

Sau khi tạo `fromBytes`, chương trình sửa `bytes[0] = 0` nhưng `fromBytes` vẫn bằng `original`; điều này kiểm chứng dữ liệu đã khôi phục không phụ thuộc vào việc sửa mảng sau đó.

### 9.4. Phần độ dài logic

`new BitSet(128)` biểu thị yêu cầu dung lượng ban đầu. Sau khi bật rồi tắt bit `1`, không còn bit nào được bật:

- `length()` trở về `0`.
- Mảng byte tối thiểu trả về có độ dài `0`.
- `size()` của đối tượng minh họa vẫn là `128`.

Đây là ví dụ cụ thể cho việc **không dùng dung lượng cấp phát làm chiều rộng payload**.

## 10. Nếu cần lưu xuống tệp hoặc gửi qua mạng, phải định nghĩa giao thức

Dữ liệu từ `toByteArray()` hoặc `toLongArray()` chỉ có ý nghĩa khi hai đầu **đồng ý** cách giải mã và ý nghĩa của bit. Một payload tốt cần có những thông tin phù hợp với mục tiêu:

| Thông tin | Vì sao cần? |
| --- | --- |
| Phiên bản format | Biết quy tắc giải mã và mapping chỉ số đang dùng |
| Quy tắc bit-to-feature | Bit 0, bit 9 đại diện cho trạng thái gì |
| Độ rộng logic (nếu cố định) | Không làm mất các bit 0 cao ở cuối |
| Thứ tự bit/byte | Tránh nhầm little-endian của `BitSet` với hệ thống big-endian |
| Số bản ghi và mapping từ bit index sang ID | Không lấy sai bản ghi khi dữ liệu đã sắp xếp lại |
| Kiểm tra giới hạn đầu vào | Tránh cho payload cố ý chứa chỉ số cực cao dẫn đến tiêu tốn nhiều bộ nhớ |
| Integrity/authentication khi cần | Không coi bit quyền gửi từ client là nguồn tin cậy duy nhất |

### Ví dụ format bitset tối thiểu

```text
version: 1
bitCount: 128
encoding: BitSet.toByteArray / little-endian bit order
payloadHex: 02
```

Đây là **mô tả format minh họa**, không phải một chuẩn định dạng Java có sẵn. Payload `02` biểu thị bit `1` bật; `bitCount: 128` được **lưu riêng theo giao thức** và không được suy ra từ độ dài byte array, vì các bit cao đều 0. Khi thực hiện thực tế, cần định nghĩa rõ header, độ dài và cách đóng gói/phân tách, thay vì ghép chuỗi minh họa này rồi coi đó là định dạng tệp tiêu chuẩn.

### Đồng bộ mapping chỉ số khi lọc dữ liệu

Nếu mỗi bit chỉ một **vị trí hàng** trong danh sách hiện tại, ví dụ bit `7` tương ứng với `rows.get(7)`, thì khi danh sách bị sắp xếp lại, xóa phần tử hoặc lọc lại, **vị trí không còn đại diện cho cùng bản ghi**. Trước khi lưu lâu dài, cần quy tắc map **ID ổn định ↔ chỉ số ổn định** hoặc xác định bitmap chỉ hợp lệ với **một snapshot dữ liệu**.

Đây là giới hạn nghiệp vụ của cách biểu diễn, không phải lỗi của API `BitSet`. Một tập chỉ số không tự mang định danh bản ghi mà bạn gán cho nó.

## 11. Giới hạn hiệu năng, bộ nhớ và đồng thời

### 11.1. Chỉ số lớn nhưng số bit bật ít vẫn có thể tốn bộ nhớ

`BitSet` lưu dữ liệu theo những khối bit. Nếu bật riêng một bit ở chỉ số rất cao, nó có thể phải cấp phát vùng nhớ đủ để đại diện cho các bit tới vị trí ấy. Vì vậy, **ít bit bật** không đồng nghĩa **ít bộ nhớ**.

Khi dữ liệu thật sự thưa trên một miền ID rất lớn (ví dụ chỉ vài ID trong hàng tỷ ID), nên cân nhắc `Set<Integer>` hoặc một cấu trúc nén bitmap phù hợp được dự án phê duyệt. Không dùng chỉ số trực tiếp từ dữ liệu không tin cậy để gọi `set(index)` mà không xác minh giới hạn.

### 11.2. Độ phức tạp nên nhìn theo dữ liệu và phép toán

- `get(index)` thường rất nhanh vì truy cập vị trí bit trong một vùng lưu trữ.
- `and`, `or`, `xor`, `andNot` tận dụng các khối bit nên có thể hiệu quả khi tập chỉ số tương đối dày.
- `nextSetBit` phù hợp khi cần chỉ duyệt những vị trí đang bật.
- Chuyển `toByteArray`/`toLongArray` phải tạo mảng kết quả, nên có chi phí sao chép và cấp phát.
- Lọc bằng `clone()` tránh sửa nguồn nhưng cũng tạo bản sao; trong một pipeline phức tạp cần cân nhắc ownership và số lần sao chép.

Không nên khẳng định một mức hiệu năng tuyệt đối cho mọi phân bố dữ liệu. Hãy đo trên kích thước thật, mật độ bit thật và mô hình truy cập của ứng dụng.

### 11.3. `BitSet` là mutable và không tự thread-safe

`set`, `clear`, `flip`, `and`, `or`, `xor` và `andNot` đều có thể **làm thay đổi trạng thái**. Khi nhiều luồng đọc/ghi chung một `BitSet`, cần cơ chế đồng bộ hoặc **snapshot độc lập** như `clone()` được tạo dưới cơ chế phối hợp phù hợp.

Không suy ra rằng một `BitSet` trở thành thread-safe chỉ vì mỗi thao tác làm việc ở mức bit. Nếu dùng nó để đại diện cho trạng thái quyền truy cập hoặc tiến độ quan trọng, hãy xác định rõ luồng sở hữu dữ liệu và cách công bố bản cập nhật.

## 12. Sai lầm thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng ID âm hoặc không xác minh input làm bit index | Có thể gây `IndexOutOfBoundsException` hoặc sai mapping | Kiểm tra chỉ số không âm và giới hạn |
| Gán cờ dựa trên thứ tự danh sách có thể thay đổi | Giải mã dữ liệu phiên bản cũ thành ý nghĩa sai | Dùng mapping chỉ số ổn định và version |
| Gọi `active.and(paid)` rồi còn cần `active` ban đầu | Dữ liệu nguồn đã bị biến đổi | Dùng `(BitSet) active.clone()` trước khi kết hợp |
| Nhầm `andNot` với phép phủ định toàn bộ | Thiếu khái niệm tập vũ trụ hữu hạn | Xác định `[0, rowCount)` trước |
| Đếm kết quả bằng `length()` | Nhầm chỉ số cao nhất +1 với số phần tử | Dùng `cardinality()` |
| Dùng `size()` làm số bit của giao thức | Phụ thuộc dung lượng vùng lưu trữ | Lưu độ rộng logic riêng |
| Nghĩ `get(from,to)` giữ nguyên chỉ số tuyệt đối | Vị trí trong kết quả bị lệch | Cộng offset hoặc duyệt tập gốc |
| Nghĩ mảng `byte[]` có signed byte âm là payload hỏng | Đọc sai biểu diễn số có dấu | Kiểm tra hex và vị trí bit |
| Viết decoder big-endian cho payload `toByteArray()` | Đổi ý nghĩa thứ tự bit | Thống nhất little-endian bit mapping |
| Quên trường hợp `bit 7/8` hoặc `63/64` | Không phát hiện sai ranh giới byte/word | Test các bit biên |
| Cho rằng round-trip giữ luôn dung lượng `size()` | Metadata độ rộng cố định bị mất | Lưu bitCount riêng |
| Cho rằng các bit cao 0 được serialize nguyên trạng | Payload bị rút gọn | Định nghĩa độ rộng cố định nếu cần |
| Dùng mặt nạ vị trí sau khi sắp xếp lại dữ liệu | Lọc sai bản ghi | Dùng snapshot hoặc ID–index mapping ổn định |
| Sửa một `BitSet` trong khi luồng khác đang duyệt | Race condition hoặc dữ liệu không nhất quán | Đồng bộ/snapshot đúng cách |
| Dùng `BitSet` cho chỉ số cực cao nhưng rất thưa | Cấp phát bộ nhớ không phù hợp | Chọn biểu diễn sparse khác |
| Lưu payload quyền hạn và tin tuyệt đối dữ liệu từ client | Rủi ro giả mạo quyền | Kiểm tra quyền ở phía có thẩm quyền |

## 13. Bài tập và đáp án

### Bài 1 — Lưu cờ

Ứng dụng có cờ `VERIFIED = 0`, `ENABLED = 3` và `BETA = 9`. Cần bật `VERIFIED` và `BETA`, tắt `ENABLED` và kiểm tra `ENABLED`.

**Đáp án:**

```java
BitSet flags = new BitSet();
flags.set(VERIFIED);
flags.set(BETA);
flags.clear(ENABLED);

boolean enabled = flags.get(ENABLED); // false
```

Đoạn trên thuộc lớp có các hằng số và `import java.util.BitSet;`. Kết quả biểu diễn bằng `toString` là `{0, 9}`.

### Bài 2 — Lọc theo ba tập chỉ số

Cho `active = {0,2,3,5,7}`, `paid = {2,3,6,7}`, `blocked = {3,6}`. Tính `active ∩ paid \ blocked` mà không sửa ba tập nguồn.

**Đáp án:**

```java
BitSet eligible = (BitSet) active.clone();
eligible.and(paid);
eligible.andNot(blocked);
// eligible = {2, 7}
```

Lệnh `clone()` quan trọng vì các phép toán được gọi trên `eligible` là phép **thay đổi trạng thái**.

### Bài 3 — Đếm số phần tử hay xác định biên?

Với `bits = {2,7}`, `cardinality()` và `length()` trả gì?

**Đáp án:** `cardinality() == 2`, còn `length() == 8`. `size()` không dùng để đếm số phần tử.

### Bài 4 — Ranh giới chuyển đổi

Một `BitSet` chỉ có các bit `63` và `64` bật. `toLongArray()` cần bao nhiêu phần tử? `toByteArray()` cần bao nhiêu byte?

**Đáp án:** Hai phần tử `long` (bit 64 nằm trong word thứ hai) và chín byte (byte chứa bit 64 là byte chỉ số 8).

### Bài 5 — Ý nghĩa hex `8101`

Nếu dùng `BitSet.valueOf(new byte[] {(byte) 0x81, 0x01})`, những bit nào bật?

**Đáp án:** Các bit `{0,7,8}`. Byte đầu có bit thấp và cao bật, byte thứ hai có bit thấp bật. Giá trị `(byte)0x81` là âm nếu in kiểu `byte` có dấu, nhưng không đổi ý nghĩa bit.

### Bài 6 — Vì sao không đủ chỉ lưu payload?

Ứng dụng xác định bitmap có chính xác 128 bit, nhưng chỉ bật bit 1. `toByteArray()` trả bao nhiêu byte và có giữ được chiều rộng 128 bit không?

**Đáp án:** Một byte `0x02`. Không, các bit 0 cao bị loại bỏ khỏi biểu diễn tối thiểu. Phải lưu **bitCount = 128** như metadata nếu giao thức yêu cầu.

### Bài 7 — Duyệt các chỉ số

Vì sao `nextSetBit(0)` thường thích hợp khi tập chỉ số thưa hơn vòng lặp gọi `get(i)` trên toàn bộ phạm vi?

**Đáp án:** Nó chuyển tới **vị trí đang bật kế tiếp**, nên tránh phải hỏi trạng thái cho từng vị trí không có trong tập. Tuy nhiên cần đánh giá hiệu năng trên kích thước và phân bố dữ liệu thực tế.

### Bài 8 — Cắt tập chỉ số

`active = {0,2,3,5,7}`, vậy `active.get(2,8)` có trả `{2,3,5,7}` không?

**Đáp án:** Không. Kết quả được đánh số tương đối từ 0, nên là `{0,1,3,5}`. Nếu cần vị trí gốc, phải cộng offset `2` hoặc duyệt tập gốc với điều kiện biên.

### Bài 9 — Kiểm thử codec

Thiết kế một bộ ca test để kiểm chứng `BitSet.toByteArray`/`valueOf`.

**Đáp án gợi ý:** Tập rỗng, bit `0`, `7`, `8`, `63`, `64`, tập hỗn hợp có bit cao, tập có nhiều bit 0 ở cuối và trường hợp mảng byte chứa byte âm. Với từng ca, khôi phục rồi kiểm tra `decoded.equals(original)`; kiểm tra thêm độ dài payload, mapping bit và metadata độ rộng nếu format yêu cầu.

## 14. Checklist trước khi ứng dụng `BitSet` vào hệ thống

- [ ] Mỗi bit index có **ý nghĩa và mapping** rõ ràng; chỉ số đầu vào không âm.
- [ ] Đã xác định tập vũ trụ khi thực hiện phủ định hoặc lọc theo danh sách bản ghi.
- [ ] Phép toán tập hợp có chủ đích về **mutable receiver**; sao chép nguồn khi cần.
- [ ] Dùng `cardinality()` cho số phần tử; `length()` cho bit bật cao nhất +1; không nhầm với `size()`.
- [ ] Đã kiểm chứng `toByteArray`/`valueOf` và `toLongArray`/`valueOf` trên các bit ở ranh giới byte/word.
- [ ] Đã thống nhất **bit order/little-endian**, không đoán theo byte order của một hệ thống khác.
- [ ] Đã lưu độ rộng logic và phiên bản mapping nếu payload phải có kích thước/ý nghĩa cố định.
- [ ] Đã quy định liệu bitmap chỉ hợp lệ cho một snapshot danh sách hay một mapping ID lâu dài.
- [ ] Đã đánh giá chỉ số cao, mật độ thưa, bộ nhớ và chi phí sao chép khi dùng `clone()`.
- [ ] Không có đọc/ghi đồng thời không được đồng bộ trên `BitSet` mutable.
- [ ] Đã phân biệt API Java 7 (`BitSet`/codec) với API Java 8 (`stream`) và Java 17 (`HexFormat`).

## 15. Tổng kết

`BitSet` thích hợp để biểu diễn **nhiều cờ boolean hoặc một tập chỉ số nguyên không âm**, kết hợp bằng các phép `and`/`or`/`andNot`/`xor` và duyệt bằng `nextSetBit`. Khi lọc bản ghi, hãy **sao chép trước khi biến đổi** nếu còn cần mặt nạ nguồn, và dùng `cardinality` để đếm kết quả.

Đối với chuyển đổi, `toByteArray`/`valueOf(byte[])` và `toLongArray`/`valueOf(long[])` có thể round-trip đúng **các bit được bật**; kiểm tra ở ranh giới `7/8` và `63/64`, hiểu quy tắc little-endian, và **không nhầm dữ liệu bit với chiều rộng cố định của giao thức**. Những nguyên tắc này tiếp tục có giá trị trong Java 17+ và Java hiện đại; chúng giúp ứng dụng bitmap chính xác, có thể kiểm thử và dễ bảo trì.