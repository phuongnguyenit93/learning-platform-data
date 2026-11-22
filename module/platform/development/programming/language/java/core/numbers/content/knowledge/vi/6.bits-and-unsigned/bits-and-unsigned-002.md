# Dịch trái `<<`, dịch phải `>>` và dịch phải không dấu `>>>` trong Java

## 1. Ba toán tử dịch bit giải quyết vấn đề gì?

Trong Java, các toán tử dịch bit (*bitwise shift operators*) di chuyển các bit của một giá trị số nguyên theo số vị trí được chỉ định:

- **`x << n` — dịch trái (*left shift*)**: đưa các bit của `x` sang trái `n` vị trí, điền bit `0` vào các vị trí trống bên phải; những bit đi ra khỏi độ rộng kiểu bị loại bỏ.
- **`x >> n` — dịch phải có dấu (*signed/arithmetic right shift*)**: đưa các bit sang phải; các vị trí trống bên trái được điền bằng **bit dấu** của toán hạng (`0` nếu không âm, `1` nếu âm).
- **`x >>> n` — dịch phải không dấu (*unsigned/logical right shift*)**: đưa các bit sang phải; các vị trí trống bên trái **luôn được điền `0`**.

Cả ba thao tác trên **mẫu bit** của số nguyên và tạo ra một kết quả có kiểu số nguyên. `>>>` không tạo ra kiểu `unsigned int` mới: Java không có kiểu nguyên thủy riêng mang tên này.

| Phép dịch | Hướng | Bit điền vào vùng trống | Điểm đáng nhớ |
|---|---|---|---|
| `<<` | Trái | `0` từ bên phải | Có thể mất bit cao hoặc đổi dấu |
| `>>` | Phải | Lặp lại bit dấu từ bên trái | Giữ cách diễn giải dấu với số âm |
| `>>>` | Phải | `0` từ bên trái | Đọc mẫu bit như giá trị không dấu khi dịch |

Ví dụ với một mẫu **8 bit minh họa** là `0010 1100` (44 thập phân):

```text
0010 1100  (44)
0101 1000  (dịch trái 1 lần -> 88)
0001 0110  (dịch phải 1 lần -> 22)
```

Ở số không âm và không có bit cao bị mất, `>>` và `>>>` thường cho cùng kết quả. Sự khác biệt quan trọng xuất hiện với **số âm**.

**Lưu ý:** bảng 8 bit phía trên chỉ minh họa trực quan. Trong Java, toán hạng `byte` và `short` được nâng lên `int` trước khi dịch; để dự đoán đúng kết quả Java, luôn tính trên độ rộng **32 hoặc 64 bit** của biểu thức thực tế.

## 2. Số nguyên có dấu và cách đọc bit cao nhất

Java sử dụng biểu diễn **bù hai** (*two's complement*) cho `int` 32 bit và `long` 64 bit:

- Bit cao nhất của mẫu bit có dấu là **bit dấu**; `0` tương ứng số không âm, `1` tương ứng số âm.
- Ví dụ `int` dương 8 có mẫu bit 32 bit `00000000 00000000 00000000 00001000`.
- `int` âm -8 có mẫu bit 32 bit `11111111 11111111 11111111 11111000`.

Trong nội dung này, thuật ngữ **“dịch phải không dấu”** mô tả **cách chèn bit 0** của toán tử `>>>`, không có nghĩa toán hạng trở thành kiểu dữ liệu unsigned. Kết quả vẫn là `int` hoặc `long` theo kiểu biểu thức.

### Hình dung trên ví dụ -8 dưới dạng `int` 32 bit

```text
-8 (int):
11111111 11111111 11111111 11111000

-8 >> 2  (điền bit dấu 1):
11111111 11111111 11111111 11111110  = -2

-8 >>> 2 (điền bit 0):
00111111 11111111 11111111 11111110  = 1073741822
```

Hai phép dịch đều đưa bit sang **phải 2 vị trí**, nhưng `>>` duy trì phần mở rộng dấu trong khi `>>>` điền 0. Vì bit đầu của kết quả `>>>` trên đây là 0, kết quả được diễn giải là số `int` dương.

## 3. Toán tử `<<`: dịch trái

Cú pháp:

```java
int result = value << distance;
```

Các bit được đẩy sang trái, vùng trống bên phải điền `0`. Đối với các giá trị không âm và khi kết quả vẫn nằm trong miền có dấu, dịch trái `n` vị trí cho cùng kết quả toán học với **nhân \(2^n\)**:

```java
int a = 3 << 1; // 6, tương ứng 3 * 2
int b = 3 << 2; // 12, tương ứng 3 * 4
int c = 5 << 3; // 40, tương ứng 5 * 8
```

Tuy nhiên, toán tử dịch trái **không kiểm tra tràn số**. Các bit vượt ra khỏi biên trái bị loại; dấu của kết quả có thể thay đổi.

```java
int signBit = 1 << 31; // -2147483648
int wrapped = 1 << 32; // 1, vì khoảng dịch int bị giới hạn 5 bit thấp
long wide = 1L << 32;  // 4294967296, toán hạng trái là long
```

Ở `1 << 31`, bit 1 được đưa đến vị trí dấu của `int`, khiến kết quả mang giá trị âm `Integer.MIN_VALUE`. Với `1 << 32`, Java **không dịch đủ 32 vị trí**; quy tắc khoảng dịch sẽ được giải thích riêng trong mục 7.

**Không coi `x << n` là phép nhân an toàn với \(2^n\)** trong trường hợp tổng quát. Dịch bit có thể bỏ bit cao, tràn miền hoặc thay đổi dấu; phép dịch cũng không phát hiện lỗi bằng ngoại lệ. Nếu nghiệp vụ cần phép nhân chính xác và phát hiện tràn, hãy cân nhắc `Math.multiplyExact` hoặc `BigInteger`.

## 4. Toán tử `>>`: dịch phải giữ dấu

Cú pháp:

```java
int result = value >> distance;
```

Khi dịch phải có dấu, vùng trống bên trái được điền bằng bản sao của **bit cao nhất**:

- Số không âm: bit dấu là `0`, do đó chèn `0`.
- Số âm: bit dấu là `1`, do đó chèn `1`.

Ví dụ:

```java
int positive = 40 >> 2; // 10
int negative = -8 >> 2; // -2
int odd = -7 >> 1;      // -4
```

Với số nguyên có dấu, kết quả của `x >> n` tương ứng phép chia lấy phần nguyên xuống dưới (*floor*) của \(x / 2^n\), khi hiểu khoảng dịch theo quy tắc Java. Vì vậy phải cẩn thận với số âm lẻ:

```java
System.out.println(-7 / 2);  // -3: chia nguyên làm tròn về 0
System.out.println(-7 >> 1); // -4: dịch phải làm tròn xuống
```

Phép `/` trên số nguyên Java **làm tròn về 0**, trong khi dịch phải dấu với số âm thường có hiệu ứng làm tròn về âm vô cực. Hai cách không luôn tương đương.

**Khi nào dùng `>>`?** Khi bạn muốn xử lý các bit trong kiểu số nguyên có dấu và cần giữ hiệu ứng mở rộng dấu, hoặc khi một thuật toán bit được định nghĩa rõ bằng dịch phải số học.

## 5. Toán tử `>>>`: dịch phải điền `0`

Cú pháp:

```java
int result = value >>> distance;
```

Toán tử này luôn điền bit `0` vào vùng trống bên trái, bất kể dấu của toán hạng. Ví dụ:

```java
int a = 40 >>> 2;   // 10
int b = -8 >>> 2;   // 1073741822
int c = -1 >>> 1;   // 2147483647
long d = -1L >>> 1; // 9223372036854775807L
```

Với số không âm, `>>` và `>>>` cho cùng kết quả nếu cùng toán hạng và khoảng dịch. Với số âm, `>>>` thường cho kết quả số **dương lớn** vì bit dấu `1` ban đầu được thay bằng `0`.

`>>>` hữu ích khi đọc các trường bit, xử lý mẫu bit như **bit pattern không dấu**, trích xuất byte/nhóm bit từ số nguyên, hoặc triển khai thuật toán băm, checksum, mã hóa nhị phân.

Không nhầm `>>>` với phép chia số có dấu. Ví dụ, `-8 / 4` bằng -2; `-8 >>> 2` bằng 1_073_741_822. Nếu muốn phép chia nguyên theo nghĩa toán học trong Java, hãy dùng `/` hoặc API phù hợp thay vì tự thay thế bằng `>>>`.

## 6. Chương trình Java 17+ đối chiếu cả ba toán tử

Tạo file `ShiftOperatorsDemo.java`:

```java
public class ShiftOperatorsDemo {
    public static void main(String[] args) {
        int positive = 40;
        int negative = -8;

        System.out.println("40 << 2 = " + (positive << 2));
        System.out.println("40 >> 2 = " + (positive >> 2));
        System.out.println("40 >>> 2 = " + (positive >>> 2));

        System.out.println("-8 << 2 = " + (negative << 2));
        System.out.println("-8 >> 2 = " + (negative >> 2));
        System.out.println("-8 >>> 2 = " + (negative >>> 2));

        System.out.println("-1 >> 1 = " + (-1 >> 1));
        System.out.println("-1 >>> 1 = " + (-1 >>> 1));
        System.out.println("-7 / 2 = " + (-7 / 2));
        System.out.println("-7 >> 1 = " + (-7 >> 1));

        System.out.printf("hex(-8 >>> 2) = %08X%n", negative >>> 2);
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac ShiftOperatorsDemo.java
java ShiftOperatorsDemo
```

Kết quả chính xác:

```text
40 << 2 = 160
40 >> 2 = 10
40 >>> 2 = 10
-8 << 2 = -32
-8 >> 2 = -2
-8 >>> 2 = 1073741822
-1 >> 1 = -1
-1 >>> 1 = 2147483647
-7 / 2 = -3
-7 >> 1 = -4
hex(-8 >>> 2) = 3FFFFFFE
```

Quan sát hai điểm:

1. Dịch trái `-8 << 2` cho -32 trong ví dụ này vì các bit còn lại tạo ra giá trị -32, nhưng không thể kết luận mọi phép dịch trái đều tương đương phép nhân số học an toàn.
2. Với `-8 >>> 2`, kết quả hex `3FFFFFFE` cho thấy hai bit `1` đầu ở biểu diễn âm đã được thay bằng hai bit `0`.

## 7. Khoảng dịch và kiểu của vế trái

Java không ném ngoại lệ khi số bước dịch âm hoặc lớn hơn độ rộng kiểu. Khoảng dịch hiệu dụng được rút gọn theo **kiểu vế trái sau nâng kiểu**, còn kiểu vế phải không quyết định độ rộng biểu thức.

| Kiểu vế trái | Số bước dịch hiệu dụng | Ví dụ |
| --- | --- | --- |
| `int`, kể cả `byte`/`short`/`char` đã nâng lên `int` | `distance & 31` | `1 << 32 == 1` |
| `long` | `distance & 63` | `1L << 32 == 4294967296L` |

```java
int lowerWidth = 1 << 40;       // 256: 40 & 31 = 8
long higherWidth = 1L << 40;    // 1099511627776L
long assignedAfterShift = 1 << 40; // 256L: phép dịch đã xong ở int
int negativeDistance = 1 << -1;   // Integer.MIN_VALUE: -1 & 31 = 31
```

Một `byte` âm cũng được mở rộng dấu thành `int` trước khi dịch: với `byte b = -8;`, `b >>> 2` cho `1073741822`, trong khi `Byte.toUnsignedInt(b) >>> 2` cho `62`. Khi `index` đến từ input để tạo mặt nạ, phải kiểm tra rõ `0 <= index && index < 32` hoặc `< 64` theo kiểu trước khi dịch; Java không bác bỏ chỉ số ngoài miền.

Bài tiếp theo **Khoảng dịch được rút gọn theo kiểu int hoặc long** đi sâu vào trường hợp số bước âm, bội 32/64, vế phải kiểu `long` và việc bảo vệ phép truy cập bit theo chỉ số.

## 8. Độ ưu tiên toán tử, ngoặc và biểu thức điều kiện

Các toán tử `<<`, `>>`, `>>>` có **cùng độ ưu tiên** và tính kết hợp trái. Chúng có độ ưu tiên **thấp hơn các toán tử cộng/trừ** nhưng **cao hơn các toán tử so sánh quan hệ** như `<`, `>=`.

Ví dụ:

```java
int a = 1 << 2 + 1; // 8: diễn giải thành 1 << (2 + 1)
int b = (1 << 2) + 1; // 5
int c = 32 >> 1 >> 2; // 4: (32 >> 1) >> 2
boolean d = (1 << 3) > 7; // true
```

Khi viết điều kiện và bitmask, nên đặt ngoặc theo ý định để người đọc không cần nhớ bảng độ ưu tiên. Chẳng hạn:

```java
int mask = 1 << 5;
boolean hasFlag = (flags & mask) != 0;
```

Đoạn trên là **mã minh họa** cần một biến `int flags` đã khai báo trước; `&` là AND theo bit và `!=` là so sánh khác. Nó cho biết bit thứ 5 có đang bật trong mẫu bit của `flags` hay không.

Các toán tử dịch chỉ nhận toán hạng **kiểu tích phân** (sau unboxing/thăng cấp phù hợp), không dịch trực tiếp `float`, `double` hoặc `String`. Nếu dùng wrapper như `Integer` mà giá trị là `null`, việc unboxing cho phép dịch có thể ném `NullPointerException`.

## 9. Ứng dụng thực tế: bitmask và tách byte

### 11.1. Tạo bitmask cho cờ trạng thái

Để bật bit thứ `k` của một biến `int`:

```java
int flags = 0;
int readFlag = 1 << 2;   // 0b00000100
int writeFlag = 1 << 5;  // 0b00100000

flags |= readFlag;
flags |= writeFlag;
boolean canRead = (flags & readFlag) != 0;   // true
boolean canWrite = (flags & writeFlag) != 0; // true
```

Đây là các biểu thức cần đặt trong một chương trình Java có `main` hoặc phương thức để chạy. `|` là OR theo bit, `|=` là phép OR gán; toán tử `<<` chỉ giúp đặt bit 1 ở vị trí mong muốn. Với `int`, vị trí bit có ý nghĩa thông thường từ 0 đến 31; với `long` từ 0 đến 63. Hãy giới hạn `k` theo miền này để tránh quy tắc vòng khoảng dịch tạo nhầm mask.

### 11.2. Trích xuất từng byte từ một số 32 bit

Giả sử `int word = 0x1234ABCD`. Để lấy bốn byte theo thứ tự bit từ cao đến thấp, sử dụng `>>>` và mặt nạ `0xFF`:

```java
int word = 0x1234ABCD;
int first  = (word >>> 24) & 0xFF; // 0x12 = 18
int second = (word >>> 16) & 0xFF; // 0x34 = 52
int third  = (word >>>  8) & 0xFF; // 0xAB = 171
int fourth = word & 0xFF;          // 0xCD = 205
```

Mặt nạ `& 0xFF` chỉ giữ **8 bit thấp**. `>>>` thích hợp khi muốn trích xuất một trường bit mà không kéo bit dấu `1` vào vùng cao của kết quả. Trong biểu thức có mặt nạ đủ chặt, đôi khi `>>` vẫn cho cùng 8 bit thấp; nhưng `>>>` truyền đạt rõ ý định dịch logic.

**Endianness** (big-endian/little-endian) là quy ước sắp thứ tự các byte khi lưu/truyền dữ liệu. Các phép dịch ở trên chỉ tách các nhóm 8 bit theo vị trí trong **giá trị `int`**, không tự xác định thứ tự byte trong một file hoặc byte buffer. Khi ghi ra ngoài, cần chỉ rõ thứ tự theo giao thức.

### 11.3. Chương trình chạy được: tách byte

Tạo file `ExtractBytesDemo.java`:

```java
public class ExtractBytesDemo {
    public static void main(String[] args) {
        int word = 0x1234ABCD;
        System.out.printf("%02X%n", (word >>> 24) & 0xFF);
        System.out.printf("%02X%n", (word >>> 16) & 0xFF);
        System.out.printf("%02X%n", (word >>> 8) & 0xFF);
        System.out.printf("%02X%n", word & 0xFF);
    }
}
```

Chạy:

```bash
javac ExtractBytesDemo.java
java ExtractBytesDemo
```

Kết quả:

```text
12
34
AB
CD
```

`%02X` định dạng số dưới dạng hex chữ hoa và chèn số 0 để có ít nhất 2 chữ số khi cần.

## 10. Dịch bit có thể và không thể thay thế phép nhân/chia

Một số quy tắc gần đúng hữu ích:

- Với `x >= 0`, khi không làm mất bit và kết quả còn vừa kiểu: `x << n` có cùng giá trị với `x * 2^n`.
- Với `x >= 0`: `x >> n` và `x >>> n` có cùng giá trị với phép chia nguyên `x / 2^n` trong giới hạn khoảng dịch phù hợp.
- Với `x < 0`: `x >> n` **không luôn** bằng `x / 2^n` vì hướng làm tròn khác nhau.
- Với `x < 0`: `x >>> n` diễn giải bit như không dấu rồi dịch, nên không tương đương phép chia có dấu.

Dùng `Math.multiplyExact` hoặc tính trên kiểu rộng hơn nếu tính đúng và phát hiện overflow là yêu cầu. Đừng tối ưu mã nghiệp vụ bằng việc đổi `*` hay `/` thành toán tử dịch khi chưa kiểm tra hành vi ở số âm, giá trị biên và khoảng dịch lớn. Trình biên dịch/JIT có thể tự thực hiện các tối ưu phù hợp khi được phép.

## 11. Những lỗi phổ biến

| Biểu hiện | Nguyên nhân | Cách sửa/ghi nhớ |
|---|---|---|
| `-8 >>> 2` ra số dương rất lớn | `>>>` chèn `0` vào bit cao của `int` 32 bit | Chỉ dùng khi muốn dịch logic theo mẫu bit |
| `1 << 32` vẫn bằng 1 | Với `int` chỉ dùng 5 bit thấp của khoảng dịch | Dùng `1L << 32` nếu muốn tạo \(2^{32}\) |
| `1L << 64` vẫn bằng 1 | Với `long` chỉ dùng 6 bit thấp | Kiểm tra khoảng dịch trước |
| `byte b = -8; b >>> 2` không cho 62 | `byte` nâng có dấu thành `int` trước dịch | Dùng `Byte.toUnsignedInt(b) >>> 2` |
| `byte b = 1; b = b << 1;` lỗi biên dịch | Dịch cho kết quả `int` | Nhận bằng `int` hoặc ép kiểu có kiểm tra |
| `-7 >> 1` khác `-7 / 2` | Dịch phải giữ dấu làm tròn xuống; chia nguyên làm tròn về 0 | Dùng `/` khi muốn phép chia Java |
| `1 << 31` âm | Đưa 1 vào bit dấu của `int` | Hiểu biểu diễn bù hai và miền kiểu |
| `x << n` không báo lỗi tràn | Bit cao bị loại bỏ âm thầm | Dùng phép toán có kiểm tra nếu cần |
| `int x = 1; long y = x << 40;` cho kết quả lạ | Phép dịch dùng `int` trước khi mở rộng sang `long` | Dùng `((long) x) << 40` |
| Điều kiện bitmask khó đọc | Nhầm độ ưu tiên `&`, `<<` và so sánh | Thêm ngoặc: `(flags & mask) != 0` |

## 12. Tự kiểm tra

**Câu 1.** Với `int x = 16`, `x << 1`, `x >> 2` và `x >>> 2` bằng bao nhiêu?  
**Đáp án:** lần lượt là 32, 4 và 4.

**Câu 2.** Với `int x = -8`, `x >> 2` và `x >>> 2` bằng bao nhiêu?  
**Đáp án:** -2 và 1_073_741_822. Phép đầu điền bit dấu `1`, phép sau điền `0`.

**Câu 3.** Vì sao `1 << 32` trả 1?  
**Đáp án:** toán hạng trái kiểu `int`, nên chỉ 5 bit thấp của khoảng dịch được sử dụng; 32 & 31 bằng 0.

**Câu 4.** Muốn tạo \(2^{32}\) bằng phép dịch, viết thế nào?  
**Đáp án:** `1L << 32`, kết quả `long` là 4_294_967_296.

**Câu 5.** Vì sao `byte b = -8; b >>> 2` không phải phép dịch unsigned 8 bit?  
**Đáp án:** `byte` được nâng lên `int` 32 bit bằng mở rộng dấu rồi mới dịch. Dùng `Byte.toUnsignedInt(b) >>> 2` nếu muốn lấy giá trị 248 rồi dịch thành 62.

**Câu 6.** Với `int n = -7`, `n / 2` và `n >> 1` khác nhau ra sao?  
**Đáp án:** -3 và -4 vì quy tắc làm tròn của chia số nguyên và dịch phải dấu khác nhau với số âm lẻ.

**Câu 7.** Phép `(word >>> 16) & 0xFF` dùng để làm gì?  
**Đáp án:** dịch mẫu bit `word` qua phải 16 vị trí, rồi chỉ giữ 8 bit thấp của kết quả (nhóm bit 16..23 của giá trị gốc).

**Câu 8.** Kết quả `long x = 1 << 40;` có khác `long y = 1L << 40;` không?  
**Đáp án:** có. `x` nhận 256 vì dịch `int` với khoảng hiệu dụng 8; `y` nhận 1_099_511_627_776 vì phép dịch trên `long` với khoảng 40.

**Câu 9.** Dịch trái có luôn là phép nhân \(2^n\) an toàn không?  
**Đáp án:** không. Bit cao có thể bị loại bỏ hoặc chuyển thành bit dấu; Java không ném ngoại lệ vì tràn trong phép dịch.

**Ghi nhớ:** `<<` dịch trái và điền `0`; `>>` dịch phải và **giữ bit dấu**; `>>>` dịch phải và **điền `0`**. Kiểu kết quả phụ thuộc **toán hạng trái sau thăng cấp**. Với `int` chỉ dùng **5 bit thấp** của khoảng dịch (0..31), với `long` chỉ dùng **6 bit thấp** (0..63). Khi thao tác `byte`/`short` âm, đặc biệt với `>>>`, hãy nhớ rằng Java thực hiện phép dịch trên `int` 32 bit sau khi thăng cấp.
