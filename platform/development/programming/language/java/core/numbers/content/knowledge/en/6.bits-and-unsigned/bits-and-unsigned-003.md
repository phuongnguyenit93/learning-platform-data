# Khoảng dịch được rút gọn theo kiểu `int` hoặc `long` trong Java

Khi viết `1 << 32` trong Java, kết quả là **1**, không phải `0` hoặc `4_294_967_296`. Nhưng `1L << 32` lại bằng **4_294_967_296**. Sự khác nhau bắt nguồn từ quy tắc của các toán tử dịch bit: **Java chỉ dùng 5 bit thấp của khoảng dịch nếu vế trái sau khi nâng kiểu là `int`, và 6 bit thấp nếu vế trái là `long`**.

Quy tắc này áp dụng cho cả ba toán tử `<<`, `>>` và `>>>`. Nó giải thích vì sao những khoảng dịch như `32`, `64`, `40`, hoặc thậm chí `-1` vẫn biên dịch và thực thi, đôi khi cho kết quả rất khác trực giác.

## 1. Toán tử dịch bit làm việc với những gì?

Java có ba toán tử dịch bit trên số nguyên:

| Toán tử | Tên | Cách thao tác các bit |
| --- | --- | --- |
| `a << n` | Dịch trái | Đưa bit sang trái, điền `0` vào các vị trí trống bên phải; các bit vượt khỏi độ rộng bị loại bỏ |
| `a >> n` | Dịch phải giữ dấu | Đưa bit sang phải, lấp các vị trí trống bên trái bằng bit dấu ban đầu |
| `a >>> n` | Dịch phải không giữ dấu | Đưa bit sang phải, lấp các vị trí trống bên trái bằng `0` |

Trong biểu thức `a << n`, `a >> n` hoặc `a >>> n`, **`a` là vế trái chứa mẫu bit cần dịch**, còn **`n` là vế phải chỉ số vị trí muốn dịch**. Cả hai phải có kiểu nguyên phù hợp: `byte`, `short`, `char`, `int` hoặc `long` (hoặc các wrapper được unbox tương ứng). Không thể dịch trực tiếp `float`, `double` hoặc `boolean`.

Java áp dụng **unary numeric promotion riêng rẽ cho từng toán hạng**. Vế trái kiểu `byte`, `short`, `char` được nâng thành `int`; nếu vế trái đã là `int` thì kết quả phép dịch là `int`, nếu là `long` thì kết quả là `long`. Kiểu của vế phải không làm thay đổi kiểu của kết quả.

Đối với số âm, các bit đang biểu diễn theo bù hai. `>>` có thể giữ các bit `1` ở phía trái, còn `>>>` đưa các bit `0` vào; nhưng **quy tắc rút gọn khoảng dịch vẫn giống nhau**.

## 2. Quy tắc chính: chỉ giữ 5 hoặc 6 bit thấp của khoảng dịch

Với một vế trái có kiểu sau nâng kiểu là `int` (32 bit):

```text
effectiveDistance = distance & 0x1F
                  = distance & 31
```

Với vế trái `long` (64 bit):

```text
effectiveDistance = distance & 0x3F
                  = distance & 63
```

`&` ở đây là phép AND từng bit. Mặt nạ `0x1F` có 5 bit thấp bằng `1`, còn `0x3F` có 6 bit thấp bằng `1`. Do đó phạm vi dịch thực sự của mỗi phép toán là:

- **`int`: từ 0 đến 31**, bất kể giá trị ban đầu của vế phải là bao nhiêu.
- **`long`: từ 0 đến 63**, bất kể giá trị ban đầu của vế phải là bao nhiêu.

Ví dụ các khoảng dịch được quy về giá trị sau:

| `n` được viết | `int`: `n & 31` | `long`: `n & 63` |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 31 | 31 | 31 |
| 32 | 0 | 32 |
| 33 | 1 | 33 |
| 40 | 8 | 40 |
| 63 | 31 | 63 |
| 64 | 0 | 0 |
| 65 | 1 | 1 |
| -1 | 31 | 63 |
| -32 | 0 | 32 |
| -64 | 0 | 0 |

Nói cách khác, đối với **khoảng dịch số nguyên** thì kết quả của phép `&` trên tương đương với lấy phần dư không âm theo 32 hoặc 64. Tuy nhiên, cần nhớ **quy tắc chính xác trong Java là mặt nạ bit**, vì cả giá trị âm cũng được diễn giải tự nhiên: `-1 & 31 == 31`; `-1 & 63 == 63`.

**Không có ngoại lệ tự động vì khoảng dịch lớn hơn độ rộng hoặc vì khoảng dịch âm.** Một phép `1 << -1` là hợp lệ và có khoảng dịch thực tế 31, không có nghĩa là dịch ngược 1 bit.

## 3. Phân biệt `1 << 32` và `1L << 32`

Hai biểu thức nhìn rất gần nhau nhưng có vế trái khác kiểu:

```java
int a = 1 << 32;      // Dịch int: 32 & 31 == 0  => 1
long b = 1L << 32;    // Dịch long: 32 & 63 == 32 => 4294967296
```

Đây là hai câu lệnh minh họa có thể đặt trong một phương thức Java. Literal `1` mặc định là `int`; hậu tố `L` tạo literal `long`. Vậy `1 << 32` thực chất giống `1 << 0`, trong khi `1L << 32` đặt bit `1` ở vị trí 32 của một mẫu 64 bit.

So sánh thêm:

| Biểu thức | Khoảng dịch thực | Kết quả |
| --- | ---: | ---: |
| `1 << 0` | 0 (int) | 1 |
| `1 << 31` | 31 (int) | -2_147_483_648 |
| `1 << 32` | 0 (int) | 1 |
| `1 << 33` | 1 (int) | 2 |
| `1 << 40` | 8 (int) | 256 |
| `1 << 64` | 0 (int) | 1 |
| `1L << 31` | 31 (long) | 2_147_483_648 |
| `1L << 32` | 32 (long) | 4_294_967_296 |
| `1L << 40` | 40 (long) | 1_099_511_627_776 |
| `1L << 63` | 63 (long) | `Long.MIN_VALUE` |
| `1L << 64` | 0 (long) | 1 |
| `1L << 65` | 1 (long) | 2 |

`1 << 31` cho giá trị âm vì bit 31 là **bit dấu** của `int`, không phải vì dịch 31 bit không hợp lệ. Tương tự, `1L << 63` bật bit dấu của `long`. Bit vẫn được đặt đúng vị trí; khi in theo thập phân có dấu, Java hiển thị số âm tương ứng.

## 4. Vế trái quyết định mặt nạ, ngay cả khi vế phải là `long`

Xem đoạn mã:

```java
long distance = 40L;
int a = 1 << distance;  // 256: 40 & 31 == 8
long b = 1L << distance; // 1099511627776: 40 & 63 == 40
```

Hai câu lệnh đặt trong phương thức Java. Vế phải `distance` có kiểu `long` trong **cả hai** biểu thức; điều đó **không khiến** biểu thức `1 << distance` trở thành `long`. Kết quả đầu tiên vẫn là `int`, vì vế trái được xác định từ literal `1` có kiểu `int`.

Cần phân biệt:

- `long result = 1 << 40;`: phép dịch hoàn tất dưới dạng `int`, kết quả 256 mới được chuyển sang `long`; nhận **256L**.
- `long result = 1L << 40;`: phép dịch diễn ra bằng `long`; nhận **1_099_511_627_776L**.
- `long result = ((long) 1) << 40;`: ép vế trái thành `long` trước phép dịch, nên giống trường hợp thứ hai.
- `long result = (long) (1 << 40);`: ép **sau** phép dịch, nên vẫn nhận **256L**.

Đây là cùng nguyên tắc “nâng kiểu phải diễn ra trước phép toán” từng gặp trong tính toán số nguyên. Kiểu của biến đích không thể thay đổi quyết định mặt nạ đã áp dụng lên khoảng dịch.

## 5. `byte`, `short` và `char` cũng dùng quy tắc 5 bit

Các toán hạng `byte`, `short`, `char` được Java nâng lên **`int`** trước phép dịch. Chúng không dùng các mặt nạ riêng kiểu `& 7` cho `byte` hoặc `& 15` cho `short`.

```java
byte b = 1;
short s = 1;
char c = 1;

int a = b << 32; // 1: thao tác bằng int, 32 & 31 == 0.
int d = s << 33; // 2: thao tác bằng int, 33 & 31 == 1.
int e = c << 40; // 256: thao tác bằng int, 40 & 31 == 8.
```

Đây là mảnh mã hợp lệ trong một phương thức. Kiểu kết quả của từng phép dịch là `int`. Nếu muốn gán về biến `byte` hoặc `short`, thường cần ép kiểu hẹp có thể mất bit. Phép gán kết hợp như `b <<= n` có quy tắc chuyển đổi về kiểu biến gốc; vẫn không làm khoảng dịch được rút gọn theo độ rộng 8 bit.

Ví dụ: `byte b = -1; int result = b >>> 1;` thực hiện `>>>` trên **`int` -1 đã nâng kiểu**, nên kết quả là `2_147_483_647`; nó không phải phép dịch không dấu của một mẫu chỉ 8 bit có kết quả 127. Nếu yêu cầu xử lý một byte như giá trị không dấu 8 bit, trước tiên dùng `b & 0xFF` để diễn giải byte thành số `int` từ 0 đến 255, rồi tính trên phạm vi ấy.

## 6. Khoảng dịch âm được xử lý thế nào?

Java không hiểu `<< -1` là “dịch phải một bit”. Nó áp dụng mặt nạ bình thường lên số âm được biểu diễn bù hai:

```java
int intShift = 1 << -1;  // Tương đương 1 << 31 => Integer.MIN_VALUE.
long longShift = 1L << -1; // Tương đương 1L << 63 => Long.MIN_VALUE.
```

Các câu lệnh minh họa đặt trong phương thức Java. Vì `-1` có toàn bit thấp bằng `1`, nên `-1 & 31 == 31` và `-1 & 63 == 63`. Ví dụ khác:

```java
int x = 1 << -32; // -32 & 31 == 0  => 1.
long y = 1L << -32; // -32 & 63 == 32 => 4294967296.
```

Đừng dùng khoảng dịch âm để biểu đạt chiều dịch ngược, và đừng dựa vào thao tác mask ngầm để “sửa” giá trị nhập sai. Nếu yêu cầu chỉ cho phép vị trí bit từ 0 đến 31 (hoặc 63), nên kiểm tra giá trị đầu vào rõ ràng rồi mới dịch.

## 7. Ba toán tử `<<`, `>>`, `>>>` cùng áp dụng mặt nạ khoảng dịch

Mặt nạ khoảng dịch không phụ thuộc hướng dịch hay chính sách điền bit. Với `int`, mọi biểu thức `x << 32`, `x >> 32`, `x >>> 32` đều có khoảng dịch thực **0**, vì `32 & 31 == 0`. Do đó:

```java
int x = -1;
int left = x << 32;       // -1: không dịch.
int arithmetic = x >> 32; // -1: không dịch.
int logical = x >>> 32;   // -1: không dịch.
int logicalOne = x >>> 1; // 2147483647: điền 0 phía trái khi dịch 1.
```

Đây là các câu lệnh minh họa. `>>` bảo toàn dấu trong quá trình dịch phải; `>>>` điền số 0. Khi khoảng dịch thực bằng 0, cả hai đều trả lại cùng mẫu bit của `x`, không làm mất dấu.

Đối với `long`, khoảng dịch `32` **không** bị rút về 0:

```java
long x = -1L;
long a = x >> 32;  // -1L: các bit 1 của dấu được điền thêm.
long b = x >>> 32; // 4294967295L: 32 bit cao được điền 0.
long c = x >>> 64; // -1L: vì 64 & 63 == 0.
```

Với `x = -1L`, mẫu ban đầu có 64 bit đều là 1. Dịch không dấu sang phải 32 bit chỉ còn 32 bit thấp là 1, nên `x >>> 32` là một `long` dương có giá trị `4_294_967_295`. Còn `x >>> 64` **không dịch chút nào** vì khoảng dịch thực bằng 0. Đây là trường hợp quan trọng khi xử lý dữ liệu nhị phân hoặc chia một giá trị 64 bit thành các phần.

## 8. Ví dụ Java 17+ đầy đủ, biên dịch và chạy được

Tạo tệp **`ShiftDistanceDemo.java`**:

```java
public class ShiftDistanceDemo {
    public static void main(String[] args) {
        int count = 40;
        long longCount = 40L;
        byte small = 1;

        System.out.println("intCount32=" + (1 << 32));
        System.out.println("intCount33=" + (1 << 33));
        System.out.println("intCount40=" + (1 << count));
        System.out.println("intCount64=" + (1 << 64));
        System.out.println("intCountMinus1=" + (1 << -1));
        System.out.println("longCount32=" + (1L << 32));
        System.out.println("longCount40=" + (1L << count));
        System.out.println("longCount64=" + (1L << 64));
        System.out.println("longCount65=" + (1L << 65));
        System.out.println("longCountMinus1=" + (1L << -1));
        System.out.println("intLeftLongRight=" + (1 << longCount));
        System.out.println("byteLeft=" + (small << 32));
        System.out.println("intEffective40=" + (count & 0x1F));
        System.out.println("longEffective40=" + (count & 0x3F));
        System.out.println("intSignBit=" + (1 << 31));
        System.out.println("longSignBit=" + (1L << 63));
        System.out.println("unsignedIntShift32=" + (-1 >>> 32));
        System.out.println("unsignedIntShift1=" + (-1 >>> 1));
        System.out.println("unsignedLongShift32=" + (-1L >>> 32));
        System.out.println("signedLongShift32=" + (-1L >> 32));
        System.out.println("intShift40Binary=" + Integer.toBinaryString(1 << count));
    }
}
```

Trong thư mục chứa tệp, chạy:

```bash
javac --release 17 -encoding UTF-8 ShiftDistanceDemo.java
java ShiftDistanceDemo
```

Stdout chính xác:

```text
intCount32=1
intCount33=2
intCount40=256
intCount64=1
intCountMinus1=-2147483648
longCount32=4294967296
longCount40=1099511627776
longCount64=1
longCount65=2
longCountMinus1=-9223372036854775808
intLeftLongRight=256
byteLeft=1
intEffective40=8
longEffective40=40
intSignBit=-2147483648
longSignBit=-9223372036854775808
unsignedIntShift32=-1
unsignedIntShift1=2147483647
unsignedLongShift32=4294967295
signedLongShift32=-1
intShift40Binary=100000000
```

Giải thích những dòng dễ nhầm:

- `intCount32=1`, `intCount64=1`: cả 32 và 64 đều cho khoảng dịch thực 0 trên `int`.
- `intCount40=256` so với `longCount40=1099511627776`: cùng số 40 nhưng một bên mask `&31`, bên kia mask `&63`.
- `intCountMinus1=-2147483648` và `longCountMinus1=-9223372036854775808`: `-1` được mask thành 31 hoặc 63 rồi bật đúng bit dấu.
- `intLeftLongRight=256`: vế phải kiểu `long` **không** làm phép dịch của vế trái `int` thành phép dịch 64 bit.
- `byteLeft=1`: `byte` được nâng thành `int`, nên cũng rút gọn khoảng dịch 32 thành 0.
- `unsignedIntShift32=-1`: `>>>` không thay đổi mẫu bit khi khoảng dịch thực bằng 0; `unsignedLongShift32=4294967295` cho thấy `long` lại dịch thực 32 bit.

## 9. Hệ quả khi tạo mặt nạ bit (bit mask)

Trong các chương trình có cờ bật/tắt, có thể cần tạo một mẫu bit chỉ có vị trí `index` được bật:

```java
int intMask = 1 << index;     // Dành cho index 0..31.
long longMask = 1L << index;  // Dành cho index 0..63.
```

Đoạn này là mã minh họa trong phạm vi có biến `index`. Không nên thay `1L` bằng `1` trong biểu thức thứ hai, vì `long longMask = 1 << 40;` cho **256L**, chỉ bật bit 8 chứ không phải bit 40.

Khi `index` đến từ input hoặc một vòng lặp, **phải chủ động kiểm tra phạm vi** để tránh mask ngầm. Ví dụ hàm truy cập bit của `long`:

```java
static boolean isBitSet(long flags, int index) {
    if (index < 0 || index >= Long.SIZE) {
        throw new IllegalArgumentException("bit index must be 0..63");
    }
    long mask = 1L << index;
    return (flags & mask) != 0L;
}
```

Đây là **phương thức** cần đặt bên trong một lớp Java. `Long.SIZE` bằng 64. Hàm kiểm tra rõ `index` từ 0 đến 63, sau đó tạo mask bằng `long`, nên kể cả vị trí 63 (bit dấu) cũng kiểm tra được đúng bằng AND bit. Nếu thiếu kiểm tra, `index = 64` sẽ bị rút về 0 và vô tình kiểm tra bit 0; `index = -1` bị rút về 63. Cả hai có thể khiến logic quyền truy cập, cờ tính năng hoặc dữ liệu nhị phân sai.

Với bit mask 32 bit, dùng `Integer.SIZE` (32) để kiểm tra `0 <= index && index < 32`. Việc mặt nạ `1 << 31` có giá trị `int` âm **không khiến nó sai**: bitwise AND và OR vẫn thao tác đúng trên mẫu bit.

## 10. Dịch trái lớn không tự báo overflow

Trong `<<`, những bit rời khỏi độ rộng của vế trái bị loại bỏ. Ngoài việc khoảng dịch được mask, còn có khả năng **mất thông tin do dịch trái**, kể cả khi khoảng dịch thực nằm trong phạm vi hợp lệ.

```java
int highBit = 1 << 31;        // Integer.MIN_VALUE.
int lostBit = highBit << 1;   // 0: bit cao nhất bị đẩy ra khỏi 32 bit.
long retained = ((long) highBit) << 1; // -4294967296L: mở rộng dấu trước dịch.
long positive = 1L << 32;     // 4294967296L.
```

Mã trên là các khai báo minh họa. `highBit` vốn đã là số `int` âm, nên mở rộng dấu `highBit` sang `long` rồi dịch sẽ cho số âm; không khôi phục số dương `2^31`. Muốn xây dựng `2^32`, cần bắt đầu từ `1L << 32`.

Dịch trái không ném `ArithmeticException` khi mất bit hoặc khi bit dấu thay đổi. Đừng dùng `x << n` như phép nhân `2^n` vô điều kiện: kết quả chỉ tương ứng với phép nhân toán học khi giá trị cần thiết vẫn biểu diễn chính xác trong kiểu kết quả và không bị tác động bởi bit bị loại bỏ.

## 11. Tình huống thường gặp trong code và cách sửa

| Cách viết | Điều dễ gây sai | Cách hiểu/sửa |
| --- | --- | --- |
| `1 << 32` | Chờ một `int` biểu diễn `2^32` | Khoảng dịch thực 0, kết quả 1; dùng `1L << 32` nếu muốn `2^32` |
| `1L << 64` | Nghĩ phép dịch ra 0 | `64 & 63 == 0`; kết quả 1 |
| `1 << -1` | Nghĩ dịch ngược hoặc ném lỗi | `-1 & 31 == 31`; kết quả `Integer.MIN_VALUE` |
| `long x = 1 << 40;` | Tưởng kiểu biến `long` làm vế trái rộng 64 bit | Biểu thức `int` cho 256 trước khi gán; dùng `1L << 40` |
| `1 << 40L` | Tưởng vế phải `long` khiến toàn biểu thức `long` | Vế trái `int` nên mask `& 31`, kết quả 256 |
| `byte b = 1; b << 32` | Tưởng `byte` dùng khoảng dịch `& 7` | `byte` được nâng kiểu `int`, mask `& 31` |
| `-1 >>> 32` | Tưởng chắc chắn đổi thành số không âm | Dịch thực 0, vẫn `int` -1 |
| `-1L >>> 32` | Tưởng kết quả giống biểu thức `int` | `long` dịch 32 bit, trả `4_294_967_295L` |
| `1L << index` với `index = 64` | Tưởng index sai sẽ bị báo lỗi | Khoảng dịch thực 0; phải kiểm tra index bằng điều kiện rõ ràng |

## 12. Câu hỏi tự kiểm tra

1. **`1 << 32` bằng bao nhiêu?** **1**, vì vế trái là `int` và `32 & 31 == 0`.
2. **`1L << 32` bằng bao nhiêu?** **4_294_967_296**, vì vế trái là `long`, còn 32 là khoảng dịch hợp lệ thực sự.
3. **`1 << 40` bằng bao nhiêu?** **256**, vì `40 & 31 == 8`, tức dịch trái 8 bit.
4. **`1L << 40` bằng bao nhiêu?** **1_099_511_627_776**, do `40 & 63 == 40`.
5. **`1 << 40L` trả kiểu `int` hay `long`?** **`int`**, vì kiểu kết quả phụ thuộc vế trái, không phụ thuộc kiểu `long` của khoảng dịch.
6. **`1L << -1` cho gì?** **`Long.MIN_VALUE`**, vì `-1 & 63 == 63`.
7. **`-1 >>> 32` có khác `-1` không?** **Không**, vì khoảng dịch thực bằng 0. Nhưng `-1L >>> 32` cho **`4_294_967_295L`**.
8. **Dịch `byte` có rút gọn khoảng dịch theo 8 bit không?** **Không**: trước phép dịch, `byte` được nâng thành `int`; quy tắc vẫn là `& 31`.
9. **Tại sao phải kiểm tra `index` khi tạo bit mask?** Vì các chỉ số âm hoặc vượt độ rộng sẽ bị mask ngầm, có thể kiểm tra/bật sai một bit khác mà không báo lỗi.

**Ghi nhớ:** với `<<`, `>>`, `>>>`, hãy **nhìn kiểu vế trái sau nâng kiểu** để biết khoảng dịch thực: **`int` dùng `distance & 31`; `long` dùng `distance & 63`**. Vế phải có kiểu `long` không làm kết quả rộng hơn; các khoảng dịch lớn hoặc âm được mask chứ không bị từ chối. Khi xử lý bit mask hoặc đầu vào có chỉ số bit, hãy xác định độ rộng mong muốn và kiểm tra giới hạn chỉ số một cách tường minh.
