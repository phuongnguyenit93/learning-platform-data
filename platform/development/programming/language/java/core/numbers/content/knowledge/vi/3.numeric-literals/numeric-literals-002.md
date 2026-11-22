# Hậu tố `L` cho `long` và thời điểm integer literal vượt phạm vi trong Java

Khi viết `long value = 3_000_000_000;`, nhiều người tưởng rằng trình biên dịch sẽ nhìn kiểu biến `long` rồi tự động chấp nhận số này. Thực tế, Java **xác định kiểu của literal trước khi xét phép gán**. Với literal số nguyên hệ thập phân, nếu không có hậu tố `L`, giá trị thường phải nằm trong phạm vi `int`. Vì `3_000_000_000` lớn hơn `Integer.MAX_VALUE`, đoạn mã trên không biên dịch được. Cách đúng là:

```java
long value = 3_000_000_000L; // long literal, giá trị 3 tỷ.
```

Bài này phân biệt ba hiện tượng dễ nhầm: **literal không hợp lệ ngay ở thời điểm biên dịch**, **kết quả biểu thức `int` tràn rồi mới được chuyển sang `long`**, và **phép tính `long` vẫn có thể tràn ở thời điểm chạy**.

## 1. Literal số nguyên là gì? Hậu tố `L` thay đổi điều gì?

Literal số nguyên là giá trị nguyên viết trực tiếp trong mã nguồn, chẳng hạn `42`, `3_000_000_000L`, `0xFF` hoặc `0b1010`. Java có bốn cách viết số nguyên: thập phân (decimal), thập lục phân (hexadecimal, `0x`/`0X`), nhị phân (binary, `0b`/`0B`) và bát phân (octal, thường bắt đầu bằng `0`, chẳng hạn `017`).

**Hậu tố `L` hoặc `l` làm literal có kiểu `long`**. Nên dùng chữ hoa `L`, vì chữ thường `l` dễ nhầm với chữ số `1`. Không có hậu tố, literal số nguyên sẽ có kiểu `int` nếu hợp lệ theo quy tắc phạm vi và ngoại lệ ở ranh giới âm được giải thích bên dưới.

| Viết trong Java | Kiểu của literal | Ý nghĩa |
| --- | --- | --- |
| `42` | `int` | Số nguyên 42 |
| `42L` | `long` | Số nguyên 42 thuộc kiểu 64 bit |
| `2_147_483_647` | `int` | Giá trị dương lớn nhất của `int` |
| `2_147_483_648L` | `long` | Vượt `int`, vẫn nằm trong phạm vi `long` |
| `0xFFL` | `long` | Giá trị 255 viết ở hệ 16 |
| `0b1010L` | `long` | Giá trị 10 viết ở hệ 2 |
| `017L` | `long` | Giá trị 15 viết ở hệ 8 |
| `1.0` | `double` | Literal số thực, không phải literal số nguyên |

Dấu gạch dưới `_` trong literal giúp đọc nhóm chữ số nhưng **không ảnh hưởng giá trị hoặc kiểu**: `3_000_000_000L` tương đương `3000000000L`. Không đặt `_` trước/sau dãy chữ số, ngay sau tiền tố `0x`/`0b`, hoặc giữa chữ số và `L`: `3_000L` hợp lệ, còn `3_000_L` thì không.

## 2. Phạm vi `int`, `long` và cách Java nhận literal thập phân

| Kiểu | Độ rộng | Nhỏ nhất | Lớn nhất |
| --- | ---: | ---: | ---: |
| `int` | 32 bit có dấu | `-2_147_483_648` | `2_147_483_647` |
| `long` | 64 bit có dấu | `-9_223_372_036_854_775_808L` | `9_223_372_036_854_775_807L` |

Với số nguyên **thập phân**:

- Literal không hậu tố `L` có giới hạn dương bình thường là `2_147_483_647` (`Integer.MAX_VALUE`). Ví dụ `2_147_483_648` đứng một mình sẽ không hợp lệ.
- Literal có hậu tố `L` có giới hạn dương bình thường là `9_223_372_036_854_775_807L` (`Long.MAX_VALUE`). `9_223_372_036_854_775_808L` đứng một mình không hợp lệ.
- Có một **ngoại lệ đặc biệt cho hai giá trị biên âm**: Java cho phép chữ số thập phân `2147483648` không có `L` **chỉ khi là toán hạng của dấu trừ đơn ngôi** trong `-2147483648`, để biểu diễn `Integer.MIN_VALUE`. Tương tự, `-9223372036854775808L` biểu diễn `Long.MIN_VALUE`. Đây không phải là cơ chế chuyển kiểu tự động khi literal dương vượt giới hạn.

Dấu `-` là **toán tử trừ đơn ngôi** tác động lên literal, không phải một phần của cú pháp literal. Bởi vậy các trường hợp ở biên cần xét cả biểu thức và ngữ cảnh, không chỉ đếm chữ số.

```java
int maxInt = 2_147_483_647;
int minInt = -2_147_483_648;             // Ngoại lệ biên âm: hợp lệ.
long aboveInt = 2_147_483_648L;          // Phải dùng L.
long maxLong = 9_223_372_036_854_775_807L;
long minLong = -9_223_372_036_854_775_808L; // Biên âm long: hợp lệ.
```

Đoạn trên là các khai báo hợp lệ có thể đặt trong một phương thức Java. **Không thể tăng giới hạn của `long` chỉ bằng việc thêm `L`**: một giá trị lớn hơn `Long.MAX_VALUE` vẫn không trở thành `long` hợp lệ.

## 3. Vì sao biến `long` không cứu được literal `int` quá lớn?

Xét đoạn không hợp lệ dưới đây (chỉ để minh họa lỗi, không đưa vào chương trình chạy):

```java
long total = 3_000_000_000; // LỖI BIÊN DỊCH: integer literal quá lớn cho int.
```

Trình biên dịch xử lý **kiểu và tính hợp lệ của literal trong biểu thức trước**, sau đó mới xét liệu kết quả có thể gán cho biến hay không. Kiểu đích `long` cho phép *widening primitive conversion* từ một giá trị `int` **đã hợp lệ**, nhưng không thay đổi cách phân tích một literal `int` quá phạm vi.

```java
long small = 123;             // Hợp lệ: int 123 mở rộng thành long.
long large = 3_000_000_000L;  // Hợp lệ: bản thân literal đã là long.
```

Không có quy tắc “literal thập phân không `L` sẽ tự thành `long` nếu lớn hơn `int`”. Khi số viết trực tiếp vượt `int`, hãy khai báo literal là `long` ngay tại chỗ.

Các ví dụ dưới đây đều **không biên dịch**, nhưng vì lý do khác nhau:

```java
long a = 2_147_483_648;           // Decimal int literal vượt phạm vi.
long b = 9_223_372_036_854_775_808L; // Decimal long literal vượt phạm vi.
int c = 3_000_000_000L;          // Literal long hợp lệ nhưng không gán thẳng vào int.
```

Ở dòng `c`, lỗi là phép gán `long` sang `int` có thể mất dữ liệu; dấu `L` giải quyết **kiểu của literal**, không cấp quyền tự động chuyển hẹp kiểu.

## 4. Lưu ý riêng cho literal nhị phân, bát phân và thập lục phân

Literal **không phải thập phân** còn có quy tắc sử dụng mẫu bit. Ví dụ `0xFFFF_FFFF` hợp lệ khi không có `L`: toàn bộ 32 bit đều bằng 1 và được diễn giải thành số `int` có dấu **-1**. Trong khi đó `0xFFFF_FFFFL` dùng `long` 64 bit, có 32 bit thấp bằng 1, nên giá trị là **4_294_967_295**.

```java
int minViaBits = 0x8000_0000;    // -2147483648 (bit dấu của int bật).
int minusOne = 0xFFFF_FFFF;      // -1 (toàn bộ 32 bit đều bật).
long positive = 0xFFFF_FFFFL;    // 4294967295 (là long 64 bit).
long minLongBits = 0x8000_0000_0000_0000L; // Long.MIN_VALUE.
long allLongBits = 0xFFFF_FFFF_FFFF_FFFFL;  // -1L.
```

Đây là mã hợp lệ có thể đặt trong một phương thức Java. Với literal không thập phân, **cùng dãy chữ số** có thể mang ý nghĩa số có dấu khác nhau tùy kiểu `int` 32 bit hay `long` 64 bit. Các mẫu quá 32 bit không có `L` vẫn là lỗi, ví dụ `0x1_0000_0000`; thêm `L` vào mẫu phù hợp 64 bit mới được.

Đừng suy từ việc `0xFFFF_FFFF` được chấp nhận rằng `4_294_967_295` cũng là `int` hợp lệ. Hai cách ghi dùng các quy tắc kiểm tra khác nhau: số thập phân diễn tả độ lớn, còn các literal nhị phân/bát phân/thập lục phân có thể diễn tả mẫu bit có dấu.

## 5. Hai loại tràn cần phân biệt: literal quá phạm vi và phép tính tràn

**A. Vượt phạm vi ngay khi viết literal: lỗi biên dịch.** Ví dụ `long n = 3_000_000_000;` thất bại trước khi chạy. Hậu tố `L` khiến số đó có kiểu `long`, nên có thể dùng.

**B. Các literal riêng lẻ hợp lệ nhưng phép toán tràn: có thể biên dịch và chạy ra giá trị sai.** Ví dụ:

```java
long wrong = 2_000_000_000 + 1_000_000_000;   // -1294967296
long right = 2_000_000_000L + 1_000_000_000; // 3000000000
```

Ở dòng đầu, cả hai toán hạng là `int`; phép cộng được thực hiện trong `int`, kết quả vượt `Integer.MAX_VALUE`, nên tràn về `-1_294_967_296`. Java chỉ chuyển **kết quả đã tràn** sang `long` khi gán. Ở dòng thứ hai, một toán hạng có kiểu `long`, toán hạng còn lại được nâng lên `long` và phép cộng được tính trong phạm vi 64 bit.

**Thêm `L` hoặc ép kiểu phải xảy ra trước phép toán có nguy cơ tràn.** Ép kiểu sau phép tính không thể khôi phục các bit đã mất:

```java
long wrongProduct = 100_000 * 100_000;          // int overflow -> 1410065408L
long alsoWrong = (long) (100_000 * 100_000);    // Ép kiểu sau khi đã tràn.
long rightProduct = 100_000L * 100_000;         // 10000000000L
long alsoRight = ((long) 100_000) * 100_000;     // Ép kiểu trước khi nhân.
```

Trong các phép toán số học nhị phân thường gặp, nếu ít nhất một toán hạng thuộc `long` (và không có `float`/`double`), kết quả phép toán được tính theo `long`. Nhưng **`long` cũng có giới hạn**: `Long.MAX_VALUE + 1L` tràn về `Long.MIN_VALUE`. Phép toán số nguyên `+`, `-`, `*` bình thường không tự ném ngoại lệ khi tràn.

Lưu ý biểu thức hằng `int` cũng có thể tràn khi được tính ở thời điểm biên dịch. Ví dụ `int wrapped = Integer.MAX_VALUE + 1;` có giá trị `Integer.MIN_VALUE`. “Được compiler tính trước” không đồng nghĩa “compiler sẽ bắt lỗi tràn số học”. Riêng phép chia cho 0 là một tình huống khác với tràn cộng/nhân.

## 6. Chương trình chạy độc lập (Java 17 trở lên)

Lưu đúng tên tệp **`LongLiteralDemo.java`**:

```java
public class LongLiteralDemo {
    public static void main(String[] args) {
        long largeLiteral = 3_000_000_000L;
        int intMin = -2_147_483_648;
        long longMin = -9_223_372_036_854_775_808L;

        long tooLate = 2_000_000_000 + 1_000_000_000;
        long promotedEarly = 2_000_000_000L + 1_000_000_000;
        long productTooLate = 100_000 * 100_000;
        long productCorrect = 100_000L * 100_000;

        int allIntBits = 0xFFFF_FFFF;
        long sameHexDigitsWithL = 0xFFFF_FFFFL;

        System.out.println("largeLiteral=" + largeLiteral);
        System.out.println("intMin=" + intMin);
        System.out.println("longMin=" + longMin);
        System.out.println("tooLate=" + tooLate);
        System.out.println("promotedEarly=" + promotedEarly);
        System.out.println("productTooLate=" + productTooLate);
        System.out.println("productCorrect=" + productCorrect);
        System.out.println("allIntBits=" + allIntBits);
        System.out.println("sameHexDigitsWithL=" + sameHexDigitsWithL);
        System.out.println("parsed=" + Long.parseLong("3000000000"));
        System.out.println("longOverflow=" + (Long.MAX_VALUE + 1L));

        try {
            Math.multiplyExact(100_000, 100_000);
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact=overflow detected");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 LongLiteralDemo.java
java LongLiteralDemo
```

Kết quả stdout chính xác:

```text
largeLiteral=3000000000
intMin=-2147483648
longMin=-9223372036854775808
tooLate=-1294967296
promotedEarly=3000000000
productTooLate=1410065408
productCorrect=10000000000
allIntBits=-1
sameHexDigitsWithL=4294967295
parsed=3000000000
longOverflow=-9223372036854775808
multiplyExact=overflow detected
```

Chương trình minh họa ba điều: một literal thập phân 3 tỷ cần `L`; phép cộng/nhân thực hiện bằng `int` vẫn có thể tràn trước khi kết quả được gán sang `long`; và với cùng 8 chữ số thập lục phân `FFFFFFFF`, thêm `L` đổi cách diễn giải bit theo độ rộng 64 thay vì 32. `Math.multiplyExact` thể hiện lựa chọn khác: yêu cầu Java **ném `ArithmeticException`** khi phép nhân nguyên bị tràn.

## 7. Muốn phát hiện tràn thay vì nhận giá trị quấn vòng?

Dùng nhóm phương thức có kiểm tra của lớp `Math`:

```java
int safeSum = Math.addExact(1_000_000_000, 1_000_000_000);
long safeProduct = Math.multiplyExact(100_000L, 100_000L);
int checkedNarrowing = Math.toIntExact(2_000_000_000L);
```

Các khai báo trên hợp lệ trong một phương thức Java; kết quả lần lượt là `2_000_000_000`, `10_000_000_000`, `2_000_000_000`. `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact` và `Math.toIntExact` ném `ArithmeticException` khi tràn hoặc khi chuyển hẹp vượt phạm vi.

Một điểm cần nhớ: `Math.addExact` có overload `int` và `long`. Nếu muốn cộng hai giá trị mà kết quả có thể lớn hơn `int`, dùng ít nhất một toán hạng kiểu `long` để chọn phép toán `long`:

```java
long total = Math.addExact(2_000_000_000L, 1_000_000_000L);
```

Với số lớn hơn phạm vi `long`, cần chuyển sang `java.math.BigInteger` thay vì cố dùng literal `long` quá giới hạn:

```java
java.math.BigInteger veryLarge =
        new java.math.BigInteger("9223372036854775808");
```

Đây là số nguyên tùy độ chính xác, được khởi tạo từ chuỗi; nó **không** phải một `long` literal.

## 8. Khi số đến từ chuỗi, `L` có còn tác dụng?

Hậu tố `L` là **cú pháp mã nguồn Java**, không phải thành phần của dữ liệu số dạng văn bản. Nếu đầu vào là chuỗi `"3000000000"`, hãy dùng API phân tích phù hợp:

```java
long number = Long.parseLong("3000000000"); // 3000000000L.
```

`Integer.parseInt("3000000000")` ném `NumberFormatException` vì vượt `int`. `Long.parseLong("3000000000L")` cũng ném `NumberFormatException`, vì ký tự `L` không phải chữ số thập phân hợp lệ trong chuỗi. Tương tự, dấu phân cách `_` được phép trong literal mã nguồn như `3_000L`, nhưng `Long.parseLong("3_000")` không chấp nhận.

Để phân tích văn bản hệ 16 hoặc hệ 2, cung cấp radix tương ứng, chẳng hạn `Long.parseLong("FF", 16)` trả 255. API xử lý chuỗi còn phải đối phó với đầu vào sai định dạng hoặc vượt phạm vi; không nên coi việc thêm `L` vào cuối chuỗi là một bước chuyển kiểu.

## 9. Những lỗi phổ biến và cách sửa

| Trường hợp | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `long n = 3000000000;` | Literal thập phân không `L` vượt `int` | `long n = 3000000000L;` |
| `long n = 2147483648;` | Kiểu biến không quyết định kiểu literal | `long n = 2147483648L;` |
| `long n = 9223372036854775808L;` | Vượt `Long.MAX_VALUE` | Dùng `BigInteger` nếu cần số dương đó |
| `int n = 3000000000L;` | Literal hợp lệ kiểu `long`, nhưng đích là `int` | Chọn `long` làm kiểu biến; chỉ chuyển hẹp khi đã kiểm tra |
| `long x = 100000 * 100000;` | Phép nhân `int` tràn trước khi gán | `100000L * 100000` |
| `long x = (long) (100000 * 100000);` | Ép kiểu kết quả đã tràn | Ép một toán hạng trước khi nhân |
| `long x = Long.MAX_VALUE + 1L;` | Phép cộng `long` vẫn có thể tràn | `Math.addExact` để phát hiện; `BigInteger` nếu cần giá trị lớn hơn |
| `Long.parseLong("123L")` | Hậu tố `L` chỉ thuộc cú pháp mã nguồn | `Long.parseLong("123")` |
| `0xFFFF_FFFF` bị hiểu là số dương | Mẫu 32 bit có bit dấu 1 nên là `int` âm | Dùng `0xFFFF_FFFFL` nếu mong muốn 4_294_967_295 |
| `3_000_L` | Gạch dưới đứng giữa chữ số và hậu tố | `3_000L` |

## 10. Tự kiểm tra

1. **`long a = 5;` có hợp lệ không?** Có. `5` là literal `int` hợp lệ, được mở rộng sang `long`.
2. **`long a = 2_147_483_648;` có hợp lệ không?** Không. Bản thân literal thập phân không `L` vượt giới hạn `int`.
3. **`long a = -2_147_483_648;` có hợp lệ không?** Có. Java cho phép trường hợp đặc biệt biểu diễn `Integer.MIN_VALUE`, rồi mở rộng kết quả sang `long`.
4. **`long a = 2_147_483_647 + 1;` cho giá trị gì?** `-2_147_483_648`, vì phép cộng `int` tràn trước khi gán. Nếu muốn `2_147_483_648`, viết `2_147_483_647L + 1`.
5. **`int x = 0xFFFF_FFFF;` có hợp lệ không?** Có, `x == -1`. **`long y = 0xFFFF_FFFFL;`** có giá trị `4_294_967_295`.
6. **Khi nào `L` không đủ?** Khi giá trị vượt cả `long`, khi kết quả phép toán `long` có thể tràn, hoặc khi muốn phát hiện tràn bằng ngoại lệ. Khi đó dùng `BigInteger` hoặc phép toán kiểm tra của `Math` theo nhu cầu.

**Ghi nhớ:** `L` quyết định **kiểu của literal số nguyên ngay khi mã nguồn được phân tích**. Kiểu biến nhận kết quả không sửa được một literal vốn đã quá phạm vi, và phép gán sang `long` không khôi phục được phép tính `int` đã tràn. Hãy chọn kiểu đủ rộng **trước phép toán**, và sử dụng kiểm tra tràn khi tính chính xác là yêu cầu bắt buộc.
