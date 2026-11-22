# Overflow số nguyên và hiện tượng quay vòng trong Java

Trong Java, **overflow (tràn số nguyên)** xảy ra khi kết quả toán học của một phép tính nằm ngoài phạm vi biểu diễn của kiểu số nguyên đang thực hiện phép tính. Với phép cộng, trừ và nhân thông thường trên `int` hoặc `long`, Java giữ lại mẫu bit có độ rộng cố định. Vì vậy giá trị có thể **quay vòng** từ giá trị dương lớn nhất sang giá trị âm nhỏ nhất, hoặc theo chiều ngược lại, mà **không có ngoại lệ tự động**.

Ví dụ tiêu biểu:

```java
int max = Integer.MAX_VALUE; // 2147483647
int wrapped = max + 1;       // -2147483648, không ném exception
```

Hai khai báo trên là mã minh họa đặt trong phương thức Java. Giá trị toán học đúng của `2_147_483_647 + 1` là `2_147_483_648`, nhưng một phép cộng `int` không thể chứa giá trị ấy. Muốn hiểu tại sao kết quả biến thành số âm, cần nhìn cả **giới hạn kiểu, mẫu bit bù hai và thứ tự chuyển kiểu**.

## 1. Phạm vi của các kiểu số nguyên

| Kiểu | Độ rộng | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `byte` | 8 bit có dấu | -128 | 127 |
| `short` | 16 bit có dấu | -32_768 | 32_767 |
| `int` | 32 bit có dấu | -2_147_483_648 | 2_147_483_647 |
| `long` | 64 bit có dấu | -9_223_372_036_854_775_808 | 9_223_372_036_854_775_807 |

Các kiểu nguyên có dấu của Java dùng **biểu diễn bù hai (two's complement)**. Đối với một kiểu `w` bit, miền giá trị là từ `-2^(w-1)` đến `2^(w-1) - 1`. Một bit được dành cho ý nghĩa dấu; có nhiều hơn một giá trị âm so với giá trị dương.

Các hằng số thường dùng để kiểm tra ranh giới gồm `Byte.MIN_VALUE`, `Short.MAX_VALUE`, `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE`, `Long.MAX_VALUE`. `char` cũng là kiểu nguyên thủy 16 bit nhưng **không dấu** (0–65_535), chủ yếu chứa đơn vị mã UTF-16; không được áp dụng nguyên xi phạm vi có dấu của `short` cho `char`.

**Phạm vi của toán hạng quyết định phép tính**, không phải tên biến nhận kết quả. Vì vậy phải hỏi “phép tính đang chạy ở `int` hay `long`?” trước khi xét biến đích.

## 2. Cơ chế quay vòng từ mẫu bit bù hai

Ở phép cộng, trừ, nhân nguyên thông thường, Java sử dụng phần thấp của kết quả biểu diễn bằng độ rộng đích; về mặt giá trị không dấu, đây là phép tính theo modulo `2^32` cho `int` và modulo `2^64` cho `long`. Sau đó cùng mẫu bit được diễn giải theo kiểu **có dấu**.

Ví dụ 32 bit tại ranh giới:

```text
Integer.MAX_VALUE =  2147483647 = 0x7FFFFFFF
                     +         1
------------------------------------------------
Mẫu 32 bit mới:                    0x80000000
Giá trị int có dấu:             -2147483648
```

Bit cao nhất (bit 31) chuyển từ `0` sang `1`. Với mẫu `0x8000_0000`, hệ bù hai diễn giải đó là `Integer.MIN_VALUE`. Bởi vậy:

```java
int a = Integer.MAX_VALUE + 1; // Integer.MIN_VALUE
int b = Integer.MIN_VALUE - 1; // Integer.MAX_VALUE
int c = -Integer.MIN_VALUE;    // Integer.MIN_VALUE
```

Đây là các khai báo minh họa hợp lệ trong phương thức. Trường hợp thứ ba đặc biệt: `int` không có giá trị dương `2_147_483_648`, nên đổi dấu `Integer.MIN_VALUE` bằng toán tử `-` lại nhận chính giá trị ban đầu.

Một cách mô hình hóa kết quả toán học `R` thành giá trị `int` là: giữ `R` theo modulo `2^32`, rồi nếu bit 31 bằng 1 thì trừ `2^32` để đọc dưới dạng có dấu. Với `long` thay `2^32` bằng `2^64`. Đây là cách **giải thích hành vi quấn vòng**, không có nghĩa Java tự biến `int` thành một kiểu unsigned.

Trong Java, hiện tượng này được quy định rõ cho số nguyên, chứ không phải một kết quả ngẫu nhiên phụ thuộc máy. Dù vậy, **hành vi được định nghĩa không có nghĩa kết quả đúng theo nghiệp vụ**: tổng tiền, số lượng, kích thước bộ đệm hoặc mốc thời gian bị âm bất ngờ vẫn là lỗi ứng dụng.

## 3. Overflow ở phép cộng, trừ, nhân và đổi dấu

| Phép tính | Kết quả toán học | Kết quả Java kiểu `int` |
| --- | ---: | ---: |
| `Integer.MAX_VALUE + 1` | 2_147_483_648 | -2_147_483_648 |
| `Integer.MIN_VALUE - 1` | -2_147_483_649 | 2_147_483_647 |
| `100_000 * 100_000` | 10_000_000_000 | 1_410_065_408 |
| `-Integer.MIN_VALUE` | 2_147_483_648 | -2_147_483_648 |

Với phép nhân, biểu thức `100_000 * 100_000` sử dụng hai `int`, vì vậy bản thân phép nhân cũng chạy trong `int`; giá trị đúng 10 tỷ nằm ngoài phạm vi 32 bit. Java giữ mẫu bit thấp, nên phép nhân cho `1_410_065_408`. Nếu ứng dụng lưu số lượng sản phẩm × đơn giá vào `int`, kết quả sẽ sai dù hai toán hạng riêng lẻ hoàn toàn hợp lệ.

Có hiện tượng tương tự ở `long`:

```java
long afterMax = Long.MAX_VALUE + 1L; // Long.MIN_VALUE
long beforeMin = Long.MIN_VALUE - 1L; // Long.MAX_VALUE
```

**`long` chỉ tăng phạm vi lên 64 bit**, không loại bỏ overflow vĩnh viễn. Đặc biệt `Math.abs(Integer.MIN_VALUE)` vẫn trả về `Integer.MIN_VALUE` (giá trị âm), vì không có `int` dương tương ứng; tương tự `Math.abs(Long.MIN_VALUE)` trả về `Long.MIN_VALUE`. Nếu cần bắt lỗi, Java 17 có `Math.negateExact` hoặc `Math.absExact` để ném `ArithmeticException` khi không biểu diễn được kết quả.

## 4. Gán vào `long` sau phép tính `int` không sửa được kết quả đã tràn

Một trường hợp hay gây lỗi:

```java
long wrong = 2_000_000_000 + 1_000_000_000;
long right = 2_000_000_000L + 1_000_000_000;
```

- Ở dòng `wrong`, **cả hai toán hạng đều là `int`**, phép cộng `int` tràn thành `-1_294_967_296`; sau đó Java mới mở rộng kết quả đó thành `long`. Kết quả vẫn là số âm.
- Ở dòng `right`, hậu tố `L` khiến một toán hạng là `long`. Toán hạng `int` còn lại được nâng lên `long` trước phép cộng, nên nhận đúng `3_000_000_000L`.

Kết quả còn phụ thuộc **vị trí ép kiểu**:

```java
long tooLate = (long) (100_000 * 100_000);  // 1410065408L
long correct1 = ((long) 100_000) * 100_000; // 10000000000L
long correct2 = 100_000L * 100_000;        // 10000000000L
```

Trong `tooLate`, cặp ngoặc buộc nhân bằng `int` trước; `(long)` chỉ nhận được kết quả đã tràn. Hai dòng `correct` chuyển ít nhất một toán hạng thành `long` **trước khi nhân**.

Phép cộng, trừ hoặc nhân hai `byte`/`short`/`char` thông thường còn được nâng kiểu lên **`int`**. Ví dụ, `byte a = 127; byte b = 1; int c = a + b;` cho `c == 128`, bởi phép cộng chạy ở `int`. Tuy nhiên, `byte a = 127; a++;` lại đưa `a` về `-128` do phép tăng và chuyển kết quả trở lại kiểu `byte`. Vì thế cần phân biệt overflow khi tính ở `int` với **chuyển hẹp** xuống kiểu nhỏ hơn.

## 5. Overflow số học, literal ngoài phạm vi và ép kiểu hẹp là ba tình huống khác

| Tình huống | Ví dụ | Điều xảy ra |
| --- | --- | --- |
| Literal thập phân không hợp lệ ngay trong mã nguồn | `long x = 3_000_000_000;` | **Lỗi biên dịch**: literal không có `L` vượt phạm vi `int` |
| Các toán hạng hợp lệ nhưng phép tính tràn | `int x = Integer.MAX_VALUE + 1;` | **Biên dịch được**, kết quả `Integer.MIN_VALUE` |
| Phép tính `int` tràn rồi mở rộng | `long x = 2_000_000_000 + 1_000_000_000;` | **Biên dịch được**, nhận giá trị `long` âm đã sai |
| Ép kiểu hẹp có mất bit | `byte x = (byte) 128;` | **Biên dịch được**, `x == -128` |
| Chuỗi số vượt phạm vi khi phân tích | `Integer.parseInt("2147483648")` | **Ném `NumberFormatException`**, không tự quay vòng |

Bảng này quan trọng khi chẩn đoán: nếu một literal trực tiếp vượt phạm vi thì chương trình **không chạy được**; nhưng khi hai số hợp lệ sinh ra tổng quá lớn thì phép toán nguyên thông thường có thể **chạy và cho giá trị sai**. Trong trường hợp ép hẹp tường minh, Java giữ các bit thấp theo độ rộng đích; đó là chuyển đổi kiểu có thể mất dữ liệu, không phải nguyên nhân giống hệt phép cộng tràn.

Một điểm khác: **biểu thức hằng** có thể được Java tính từ lúc biên dịch mà vẫn có kết quả quay vòng. Chẳng hạn `int wrapped = 2_147_483_647 + 1;` vẫn hợp lệ và bằng `-2_147_483_648`. Đừng suy rằng “được tính ở compile time” sẽ được báo lỗi overflow. Cách phát hiện tràn chủ động nằm ở bước kiểm tra hoặc các API có kiểm tra.

## 6. Ngoại lệ quan trọng: phép chia `MIN_VALUE / -1`

Phép chia số nguyên khác phép cộng, trừ, nhân. Thông thường chia cho **0** ném `ArithmeticException`. Tuy nhiên, Java có một trường hợp phép chia **vượt phạm vi nhưng không ném lỗi**:

```java
int q = Integer.MIN_VALUE / -1; // Integer.MIN_VALUE
long r = Long.MIN_VALUE / -1L;  // Long.MIN_VALUE
```

Giá trị toán học của `Integer.MIN_VALUE / -1` là `2_147_483_648`, không biểu diễn được bằng `int`; quy tắc Java trả lại chính `Integer.MIN_VALUE`. Tương tự cho `long`. Phần dư của trường hợp này là **0**.

Vì vậy, không nên nói “phép chia số nguyên luôn phát hiện overflow”. Khi tính số nguyên có dấu và đặc biệt khi có `MIN_VALUE`, phải kiểm tra `dividend == MIN_VALUE && divisor == -1` nếu yêu cầu kết quả toán học chính xác và được bảo đảm nằm trong phạm vi. Dùng kiểu rộng hơn (nếu đủ chỗ) hoặc `BigInteger` để biểu diễn thương toán học.

## 7. Chương trình Java 17+ có thể biên dịch và chạy độc lập

Tạo tệp **`IntegerOverflowDemo.java`**:

```java
import java.math.BigInteger;

public class IntegerOverflowDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int min = Integer.MIN_VALUE;
        long longMax = Long.MAX_VALUE;

        System.out.println("intMax=" + max);
        System.out.println("intMaxPlusOne=" + (max + 1));
        System.out.println("intMinMinusOne=" + (min - 1));
        System.out.println("negatedIntMin=" + (-min));
        System.out.println("productInInt=" + (100_000 * 100_000));
        System.out.println("lateWidening=" + (2_000_000_000 + 1_000_000_000));
        System.out.println("earlyLong=" + (2_000_000_000L + 1_000_000_000));
        System.out.println("longMaxPlusOne=" + (longMax + 1L));
        System.out.println("intMinDivMinusOne=" + (min / -1));
        System.out.println("narrowByte=" + ((byte) 128));
        System.out.println("wrappedBits=" + Integer.toHexString(max + 1));
        System.out.println("unsignedMinusOne=" + Integer.toUnsignedString(-1));
        System.out.println("unsignedCompare=" + Integer.compareUnsigned(-1, max));

        try {
            System.out.println(Math.addExact(max, 1));
        } catch (ArithmeticException ex) {
            System.out.println("addExact=overflow detected");
        }

        try {
            System.out.println(Math.multiplyExact(100_000, 100_000));
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact=overflow detected");
        }

        try {
            System.out.println(Math.negateExact(min));
        } catch (ArithmeticException ex) {
            System.out.println("negateExact=overflow detected");
        }

        try {
            System.out.println(Math.toIntExact(3_000_000_000L));
        } catch (ArithmeticException ex) {
            System.out.println("toIntExact=overflow detected");
        }

        BigInteger beyondLong =
                BigInteger.valueOf(longMax).add(BigInteger.ONE);
        System.out.println("beyondLong=" + beyondLong);
    }
}
```

Biên dịch rồi chạy:

```bash
javac --release 17 -encoding UTF-8 IntegerOverflowDemo.java
java IntegerOverflowDemo
```

Kết quả stdout (đã đối chiếu khi chạy):

```text
intMax=2147483647
intMaxPlusOne=-2147483648
intMinMinusOne=2147483647
negatedIntMin=-2147483648
productInInt=1410065408
lateWidening=-1294967296
earlyLong=3000000000
longMaxPlusOne=-9223372036854775808
intMinDivMinusOne=-2147483648
narrowByte=-128
wrappedBits=80000000
unsignedMinusOne=4294967295
unsignedCompare=1
addExact=overflow detected
multiplyExact=overflow detected
negateExact=overflow detected
toIntExact=overflow detected
beyondLong=9223372036854775808
```

Giải thích các kết quả chính:

- `intMaxPlusOne` và `intMinMinusOne` minh họa quay vòng qua hai biên 32 bit; `negatedIntMin` minh họa giá trị âm nhỏ nhất không có đối số dương tương ứng.
- `productInInt`, `lateWidening` và `earlyLong` cho thấy overflow xảy ra **trong kiểu của phép tính**, không phụ thuộc biến nhận.
- `longMaxPlusOne` khẳng định phép tính 64 bit cũng có biên; `intMinDivMinusOne` minh họa quy tắc đặc biệt của phép chia.
- `narrowByte=-128` là ví dụ **chuyển hẹp**; `wrappedBits=80000000` cho thấy mẫu 32 bit sau khi cộng `1` vào số lớn nhất.
- `unsignedMinusOne=4294967295` chỉ là cách **diễn giải không dấu** của mẫu `int` `-1`, không có thêm dung lượng lưu trữ; `unsignedCompare=1` nghĩa là `-1` được xem là lớn hơn `Integer.MAX_VALUE` **theo thứ tự không dấu**.
- Bốn phương thức có `Exact` chủ động ném `ArithmeticException` trong các trường hợp không biểu diễn được; `BigInteger` chứa được kết quả lớn hơn `Long.MAX_VALUE`.

## 8. Phát hiện overflow bằng các phương thức `Math.*Exact`

Khi yêu cầu nghiệp vụ là **phát hiện tràn thay vì nhận kết quả quấn vòng**, hãy dùng các phương thức có kiểm tra:

| API | Khi nào hữu ích |
| --- | --- |
| `Math.addExact(a, b)` | Phát hiện tràn khi cộng `int` hoặc `long` |
| `Math.subtractExact(a, b)` | Phát hiện tràn khi trừ `int` hoặc `long` |
| `Math.multiplyExact(a, b)` | Phát hiện tràn khi nhân `int` hoặc `long` |
| `Math.incrementExact(a)` / `decrementExact(a)` | Tăng/giảm biến đếm nhưng không âm thầm quay vòng |
| `Math.negateExact(a)` / `absExact(a)` | Xử lý dấu và trị tuyệt đối ở ranh giới âm nhỏ nhất |
| `Math.toIntExact(longValue)` | Đưa `long` sang `int` nhưng báo lỗi khi ngoài phạm vi |

Các phương thức trên ném **`ArithmeticException`** khi kết quả không biểu diễn được trong kiểu kết quả. Ví dụ:

```java
int count = 2_147_483_647;
int next = Math.incrementExact(count); // Ném ArithmeticException.
```

Đây là mảnh mã cần đặt trong phương thức. Nếu ứng dụng cần xử lý lỗi, đặt lời gọi trong `try/catch` hoặc để ngoại lệ được xử lý ở lớp phù hợp. Lưu ý `Math.addExact(int, int)` kiểm tra phạm vi **`int`**, kể cả khi kết quả được gán cho biến `long`. Muốn cộng trong 64 bit, hãy chuyển ít nhất một toán hạng sang `long` **trước khi gọi** overload kiểu `long`:

```java
long sum = Math.addExact(2_000_000_000L, 1_000_000_000L); // 3000000000
```

Các phương thức `Exact` chỉ hoạt động trên phép toán được gọi. Nếu một biểu thức con đã tràn trước đó, chúng **không thể khôi phục dữ liệu**:

```java
long wrong = Math.addExact((long) (Integer.MAX_VALUE + 1), 0L);
// Kết quả vẫn là -2147483648: tràn int xảy ra trước lời gọi.

long right = Math.addExact((long) Integer.MAX_VALUE, 1L);
// Kết quả chính xác: 2147483648.
```

## 9. Kiểm tra biên trước phép tính

Nếu không dùng các hàm `Exact`, đôi khi có thể kiểm tra biên trước khi cộng, ví dụ khi **`delta` không âm**:

```java
static int addNonNegativeExact(int current, int delta) {
    if (delta < 0) {
        throw new IllegalArgumentException("delta must be nonnegative");
    }
    if (current > Integer.MAX_VALUE - delta) {
        throw new ArithmeticException("int overflow");
    }
    return current + delta;
}
```

Đây là **phương thức** cần đặt bên trong một lớp Java. Vì `delta` đã được xác nhận không âm, `Integer.MAX_VALUE - delta` là an toàn trong phạm vi `int`; nếu `current` lớn hơn ngưỡng cho phép thì cộng sẽ tràn. Với phép cộng hai số bất kỳ có thể âm/dương, dùng `Math.addExact` thường ít lỗi hơn việc tự xây dựng nhiều điều kiện biên.

Các trường hợp thực tế nên coi overflow là lỗi thay vì tình huống quay vòng bình thường: tính tổng tiền, đếm số bản ghi, tính kích thước mảng/buffer, cộng số lượng tồn kho, tính tổng byte, kích thước file hoặc kiểm tra giới hạn đầu vào. Ví dụ, nếu mã tính `items * bytesPerItem` bằng `int` rồi dùng kết quả để cấp phát bộ nhớ, một tích tràn có thể biến thành số âm hoặc một số dương quá nhỏ. Dùng `Math.multiplyExact` và kiểm tra giới hạn thực tế trước khi cấp phát.

## 10. Khi nên dùng `long`, `BigInteger` hoặc unsigned API?

**Chọn `long`** khi kết quả có thể vượt phạm vi `int`, nhưng chứng minh được nó vẫn nằm trong phạm vi `long`. Điều kiện quan trọng là chuyển kiểu **trước phép toán**:

```java
int quantity = 100_000;
int unit = 100_000;
long total = (long) quantity * unit; // 10000000000
```

**Chọn `BigInteger`** khi kết quả có thể lớn hơn `Long.MAX_VALUE` hoặc nhỏ hơn `Long.MIN_VALUE`. Ví dụ:

```java
java.math.BigInteger result =
        java.math.BigInteger.valueOf(Long.MAX_VALUE)
                .add(java.math.BigInteger.ONE);
// result == 9223372036854775808.
```

`BigInteger` lưu số nguyên với độ chính xác tùy dung lượng bộ nhớ; phải dùng các phương thức như `add`, `subtract`, `multiply`, vì toán tử `+` và `*` không được nạp chồng cho đối tượng Java. Nếu chuyển ngược về `long` hoặc `int`, dùng `longValueExact()` / `intValueExact()` khi muốn phát hiện giá trị ngoài phạm vi.

**Dùng `Integer.toUnsignedString`, `Integer.toUnsignedLong`, `Integer.compareUnsigned`, `Long.toUnsignedString`** khi đặc tả đầu vào nói rõ dữ liệu là **mẫu bit unsigned** (ví dụ định dạng nhị phân hoặc giao thức). Các API này thay đổi cách **diễn giải, so sánh, chia hoặc hiển thị** mẫu bit, chứ không làm phép cộng `int` thông thường có khả năng chứa số có dấu lớn hơn. Không nên dùng unsigned chỉ nhằm “che” overflow của phép tính nghiệp vụ có dấu.

## 11. Dấu hiệu overflow trong chương trình thật

Hãy nghi ngờ overflow khi quan sát những hành vi như:

- Bộ đếm `int` đang tăng bỗng trở thành số âm hoặc số âm nhỏ nhất.
- Tổng hai số dương trả về số âm hoặc kết quả nhỏ hơn từng số hạng.
- Tích `quantity * price` khác kết quả kỳ vọng dù dữ liệu đầu vào đều hợp lệ.
- Biến `long` nhận kết quả âm từ biểu thức gồm **toàn `int`**.
- Một điều kiện phụ thuộc thứ tự tăng, ví dụ `next > current`, bất ngờ sai ở biên.
- `Math.abs` với giá trị nhỏ nhất vẫn trả về số âm.

Cần phân biệt với tình huống **thiết kế có chủ đích dựa vào modulo**, chẳng hạn một số hàm băm, thuật toán xử lý bit, bộ đếm vòng hoặc giao thức quy định số 32 bit. Khi modulo là yêu cầu thật sự, hãy ghi rõ độ rộng và mẫu bit mong muốn; khi tính toán chính xác là yêu cầu, hãy phát hiện overflow.

Trong kiểm thử, cần thử **ngay bên dưới biên, đúng tại biên và ngay sau phép toán gây vượt biên**. Ví dụ `Integer.MAX_VALUE - 1`, `Integer.MAX_VALUE`, `Integer.MAX_VALUE + 1`; đồng thời thử `Integer.MIN_VALUE`, phép đổi dấu, phép trừ 1, nhân số lớn và giá trị `Long.MAX_VALUE`. Không cần cố viết literal thập phân quá phạm vi để thử overflow: khi đó chỉ đang kiểm tra **lỗi biên dịch literal**, không kiểm tra hành vi chạy của phép toán.

## 12. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `int` tự ném lỗi khi cộng quá giới hạn | `+` thông thường dùng số nguyên độ rộng cố định và quay vòng | Dùng `Math.addExact` khi muốn phát hiện |
| `long x = a * b;` luôn an toàn nếu `x` là `long` | Nếu `a`, `b` là `int`, phép nhân có thể tràn ở `int` | `long x = (long) a * b;` |
| Ép `(long)` quanh biểu thức đã tràn sẽ sửa kết quả | Ép kiểu diễn ra sau phép toán bên trong | Ép một toán hạng từ trước |
| `long` không bao giờ overflow | `long` có độ rộng 64 bit hữu hạn | `Math.*Exact` hoặc `BigInteger` |
| `Math.abs(Integer.MIN_VALUE)` luôn không âm | Giá trị dương tương ứng vượt `int` | `Math.absExact`, `long` hoặc `BigInteger` theo yêu cầu |
| Chia cho `-1` luôn biểu diễn được | `MIN_VALUE / -1` vượt phạm vi nhưng trả lại `MIN_VALUE` | Kiểm tra trường hợp đặc biệt |
| `Integer.parseInt("2147483648")` sẽ quay vòng | Parse kiểm tra phạm vi và báo lỗi | Dùng `Long.parseLong` nếu phù hợp |
| Ép hẹp `(byte)128` giống lỗi cộng `int` | Đó là chuyển kiểu hẹp giữ bit thấp | Kiểm tra biên hoặc dùng API chuyển đổi chính xác |
| API unsigned làm `int` rộng hơn | API chỉ đổi cách đọc mẫu bit | Dùng kiểu đủ rộng để tính chính xác |

## 13. Câu hỏi tự kiểm tra

1. **`Integer.MAX_VALUE + 1` bằng gì?** `Integer.MIN_VALUE`, do mẫu 32 bit quay vòng sang bit dấu bằng 1.
2. **`Integer.MIN_VALUE - 1` bằng gì?** `Integer.MAX_VALUE`, do quay vòng qua biên dưới.
3. **`long total = 2_000_000_000 + 1_000_000_000;` bằng gì?** `-1_294_967_296L`, do phép cộng đã tràn ở `int` trước khi mở rộng.
4. **Làm sao nhận đúng `3_000_000_000`?** `2_000_000_000L + 1_000_000_000` hoặc chuyển một toán hạng sang `long` trước khi cộng.
5. **`long x = Long.MAX_VALUE + 1L;` bằng gì?** `Long.MIN_VALUE`; dùng `Math.addExact(Long.MAX_VALUE, 1L)` nếu cần ném lỗi.
6. **Có phải overflow nào cũng do toán tử `+` không?** Không: phép trừ, nhân, đổi dấu và trường hợp `MIN_VALUE / -1` đều có ranh giới cần xét.
7. **Một `int` có thể lưu chính xác `2_147_483_648` không?** Không; dùng `long`. Nếu yêu cầu giữ mẫu 32 bit như unsigned, phải thể hiện rõ cách diễn giải.
8. **Khi nào dùng `BigInteger`?** Khi dải kết quả yêu cầu vượt phạm vi `long` hoặc cần tính số nguyên tùy độ chính xác.

**Ghi nhớ:** trong Java, phép tính nguyên thông thường có thể **quay vòng modulo độ rộng bit mà không báo lỗi**. Để tránh sai số ngoài ý muốn, xác định kiểu của **từng toán hạng trước phép tính**, chọn `long` khi đủ phạm vi, dùng `Math.*Exact` hoặc kiểm tra biên khi cần phát hiện overflow, và dùng `BigInteger` nếu yêu cầu vượt cả `long`.
