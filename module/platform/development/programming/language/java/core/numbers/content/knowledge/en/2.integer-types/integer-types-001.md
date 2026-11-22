# `byte`, `short`, `int` và `long` trong Java

Java có bốn kiểu số nguyên nguyên thủy (*primitive integer types*) có dấu: **`byte` (8 bit), `short` (16 bit), `int` (32 bit), `long` (64 bit)**. Chúng lưu số nguyên chính xác **trong miền giá trị của từng kiểu**, nhưng có thể gặp tràn số khi kết quả phép toán vượt miền. Để dùng đúng, cần hiểu giới hạn, literal, chuyển kiểu, cơ chế nâng kiểu khi tính toán và các phép chia số nguyên.

## 1. Độ rộng, phạm vi và bản chất của bốn kiểu

| Kiểu | Độ rộng | Nhỏ nhất | Lớn nhất | Wrapper |
| --- | ---: | ---: | ---: | --- |
| `byte` | 8 bit | -128 | 127 | `Byte` |
| `short` | 16 bit | -32.768 | 32.767 | `Short` |
| `int` | 32 bit | -2.147.483.648 | 2.147.483.647 | `Integer` |
| `long` | 64 bit | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 | `Long` |

Kiểu số nguyên có dấu gồm `n` bit có miền `-2^(n-1)` đến `2^(n-1)-1`. Chẳng hạn, `byte` có miền từ `-2^7 = -128` đến `2^7-1 = 127`. Phần âm có thêm một giá trị vì miền không âm phải chứa cả số 0.

Java quy định bốn kiểu này dùng biểu diễn **bù hai (two's complement)** cho các phép toán nguyên có dấu. Giá trị `-1` có tất cả bit bằng 1 ở độ rộng đang dùng. Số bit của từng kiểu **không thay đổi** giữa máy 32 bit và 64 bit. Trong các kiểu nguyên có dấu, `int` thường là lựa chọn mặc định cho biến đếm và tính toán thông thường; `long` dùng khi cần miền lớn hơn.

Các hằng của wrapper giúp tra giới hạn an toàn: `Byte.MIN_VALUE`, `Short.MAX_VALUE`, `Integer.MIN_VALUE`, `Long.MAX_VALUE`. Không nên nhầm độ rộng giá trị với dung lượng thực tế của một object trong bộ nhớ: object header, căn chỉnh, boxing và cấu trúc collection có chi phí bổ sung. Với `int[]` hoặc `byte[]`, dữ liệu là primitive nhưng mảng vẫn có phần quản lý của JVM.

Cần phân biệt `char`: dù có 16 bit, nó biểu diễn một đơn vị mã UTF-16 **không dấu**, không thuộc bốn kiểu số nguyên có dấu ở đây. `boolean` cũng không phải kiểu số nguyên.

## 2. Khai báo biến, giá trị mặc định và literal

```java
byte level = 25;
short year = 2026;
int users = 100_000_000;
long count = 3_000_000_000L;
long smallCount = 100;  // literal int 100 được mở rộng chính xác thành long
```

Literal số nguyên **thập phân** không có hậu tố thường là `int` nếu nằm trong miền `int`. Nếu số lớn hơn `Integer.MAX_VALUE` và cần kiểu `long`, thêm `L` viết hoa:

```java
long ok = 5_000_000_000L;
// long wrong = 5_000_000_000; // Lỗi: literal thập phân vượt miền int
```

Dùng `L` thay vì `l` thường để tránh nhìn nhầm chữ `l` với số `1`. Dấu `_` bên trong các chữ số giúp dễ đọc mà không thay đổi giá trị; không được tùy tiện đặt ở đầu/cuối literal hoặc ngay trước hậu tố.

Java còn có literal nhị phân `0b1010`, bát phân `012` và thập lục phân `0x0A`; cả ba ví dụ đều có giá trị **10**. Riêng `012` là bát phân: số 0 ở đầu literal nguyên có ý nghĩa cú pháp, không phải cách viết thập phân bình thường.

Field primitive và phần tử mảng primitive được khởi tạo mặc định bằng **0** (`long` có giá trị 0L). Biến cục bộ trong phương thức **không được tự động gán 0 để có thể đọc ngay**; Java yêu cầu nó đã được gán chắc chắn trước khi sử dụng.

Với hằng `final`, trình biên dịch có thể áp dụng quy tắc hằng số tại thời điểm biên dịch. Ví dụ:

```java
byte first = 127;          // Hợp lệ: hằng int 127 nằm trong miền byte
final int LIMIT = 100;
byte second = LIMIT;       // Hợp lệ: constant expression trong miền byte
int variable = 100;
// byte third = variable; // Không hợp lệ: int thông thường không tự thu về byte
// byte fourth = 128;    // Không hợp lệ: ngoài miền byte
```

Đây là **quy tắc gán hằng số có điều kiện**, không phải mọi chuyển kiểu `int → byte` đều tự động.

## 3. Mở rộng kiểu (widening): không mất số nguyên trong bốn kiểu

Chuỗi mở rộng điển hình là:

```text
byte → short → int → long
```

Mọi giá trị của kiểu bên trái đều biểu diễn được bởi kiểu bên phải:

```java
byte original = -100;
short a = original;
int b = a;
long c = b;        // c vẫn bằng -100
```

Chuyển mở rộng giữa **`byte`, `short`, `int` và `long`** là ngầm định và giữ chính xác giá trị. Tuy nhiên, đừng suy diễn rằng chuyển một `long` lớn sang `double` cũng luôn giữ chính xác mọi chữ số nguyên: độ chính xác phần trị của số dấu phẩy động hữu hạn.

## 4. Thu hẹp kiểu (narrowing): cast có thể đổi giá trị

Muốn gán từ kiểu lớn về kiểu nhỏ, Java thường yêu cầu ép kiểu tường minh:

```java
int number = 130;
byte small = (byte) number; // -126

long huge = 3_000_000_000L;
int changed = (int) huge;   // -1294967296
```

Với các chuyển kiểu số nguyên thu hẹp, Java giữ **các bit thấp**, bỏ các bit cao rồi diễn giải kết quả theo kiểu đích có dấu. Ví dụ 130 có tám bit thấp là `1000_0010`, nên khi đọc theo `byte` có dấu, giá trị nhận được là -126. Cast **không làm tròn**, **không kẹp tại `MIN_VALUE`/`MAX_VALUE`**, và **không tự báo lỗi** nếu số vượt miền đích.

Nếu cần chuyển `long` sang `int` và phát hiện giá trị nằm ngoài miền, dùng `Math.toIntExact(value)`: nó ném `ArithmeticException` khi không thể biểu diễn trong `int`. Với `int` sang `byte` hoặc `short`, hãy kiểm tra giới hạn kiểu đích trước khi cast.

## 5. Quy tắc nâng kiểu trong biểu thức số học

Trong nhiều phép toán hai ngôi như `+`, `-`, `*`, `/`, `%`, các toán hạng `byte` hoặc `short` được nâng lên **`int`** trước khi tính (*binary numeric promotion*). Khi một toán hạng là `long` và toán hạng còn lại là kiểu số nguyên trong bốn kiểu này, phép toán được thực hiện theo `long`.

```java
byte a = 10;
byte b = 20;
int sum = a + b;            // Đúng: kiểu biểu thức là int
// byte wrong = a + b;      // Lỗi biên dịch: int không tự thu về byte
byte smallSum = (byte) (a + b);

int x = 1_000_000;
long wrongProduct = x * x;          // Phép nhân int tràn trước khi gán long
long correctProduct = (long) x * x; // 1_000_000_000_000L
```

**Kiểu của biến nhận không quyết định kiểu trung gian của biểu thức**. `long wrongProduct = x * x` vẫn nhân theo `int`. Ép một toán hạng thành `long` **trước phép tính** mới giúp biểu thức nhân theo `long`; sau đó vẫn phải bảo đảm kết quả nằm trong giới hạn `long`.

Các phép toán đơn ngôi `+`, `-`, `~` nâng `byte`/`short` lên `int`. Với dịch bit `<<`, `>>`, `>>>`, toán hạng trái sau nâng kiểu quyết định kiểu kết quả (`int` hoặc `long`).

### Tại sao `byte counter += 1` lại biên dịch?

```java
byte counter = 127;
counter += 1;             // Hợp lệ, kết quả sẽ là -128
// counter = counter + 1;  // Lỗi: counter + 1 có kiểu int
```

Phép gán rút gọn `counter += 1` bao gồm chuyển kiểu về `byte` một cách ngầm định (tương tự `counter = (byte) (counter + 1)`, trừ việc biểu thức bên trái chỉ được đánh giá một lần). Điều đó thuận tiện về cú pháp nhưng **không bảo vệ khỏi overflow**.

## 6. Tràn số (overflow) và phép toán an toàn

Nếu kết quả toán học vượt miền giá trị, phép cộng/trừ/nhân trên kiểu số nguyên nguyên thủy có kết quả theo độ rộng bit cố định. Ví dụ:

- `Integer.MAX_VALUE + 1` cho `Integer.MIN_VALUE`.
- `Long.MAX_VALUE + 1L` cho `Long.MIN_VALUE`.
- `Math.abs(Integer.MIN_VALUE)` vẫn cho `Integer.MIN_VALUE` vì không thể biểu diễn giá trị đối dương tương ứng trong `int`.

Các phép cộng, trừ, nhân thông thường **không tự ném ngoại lệ khi tràn**. Nếu cần phát hiện thay vì nhận kết quả đã quấn vòng, dùng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.incrementExact`, `Math.decrementExact`, `Math.negateExact` hoặc kiểm tra miền. Chúng ném `ArithmeticException` với các trường hợp overflow mà API xử lý. `Math.toIntExact` hữu ích riêng cho đổi `long` sang `int`.

Muốn tính với số nguyên vượt cả 64 bit, sử dụng `java.math.BigInteger`. `BigInteger` không có độ rộng cố định như `long` nhưng vẫn chịu giới hạn bộ nhớ và thời gian xử lý.

## 7. Phép chia nguyên, phép lấy dư và chia cho 0

Phép chia hai số nguyên cho kết quả số nguyên, **cắt phần phân số về phía 0**:

- `7 / 3 == 2`.
- `-7 / 3 == -2`, không phải -3.
- `7 % 3 == 1`.
- `-7 % 3 == -1` (số dư khác 0 cùng dấu với số bị chia).

Nếu mẫu số là 0, `x / 0` và `x % 0` với các toán hạng kiểu nguyên gây `ArithmeticException`. Trường hợp đặc biệt `Integer.MIN_VALUE / -1` trả về `Integer.MIN_VALUE` theo quy tắc kết quả số nguyên cố định, không tự ném ngoại lệ.

Khi nghiệp vụ cần phép chia **làm tròn về âm vô cực**, `Math.floorDiv` và `Math.floorMod` có quy tắc khác `/`, `%` khi số âm tham gia. Những API này không thay thế cho kiểm tra overflow tổng quát.

## 8. Có kiểu nguyên không dấu (unsigned) không?

Bốn primitive đang xét đều **có dấu**. Tuy nhiên, Java có API giúp **diễn giải các bit như giá trị không dấu** trong giao thức hoặc file nhị phân:

- `Byte.toUnsignedInt(b)`: đọc mẫu 8 bit của `byte` như số từ 0 đến 255, trả về `int`.
- `Short.toUnsignedInt(s)`: đọc mẫu 16 bit như số 0..65535.
- `Integer.toUnsignedLong(i)`: đọc mẫu 32 bit như số 0..4294967295 dưới dạng `long`.
- `Integer.compareUnsigned`, `Integer.divideUnsigned`, `Long.compareUnsigned` và `Long.toUnsignedString`: hỗ trợ thao tác/biểu diễn theo ngữ nghĩa không dấu.

Ví dụ, `Integer.toUnsignedLong(-1)` bằng `4_294_967_295L` do 32 bit của -1 đều bằng 1. Biến `int` ban đầu **vẫn là -1**; đây là sự thay đổi cách diễn giải bit, không phải một kiểu `unsigned int` primitive mới.

## 9. Ví dụ hoàn chỉnh chạy trên Java 17+

Lưu tệp `IntegerTypesDemo.java`:

```java
public class IntegerTypesDemo {
    public static void main(String[] args) {
        byte b = 127;
        short s = 30_000;
        int i = 2_000_000_000;
        long l = 3_000_000_000L;

        System.out.println("byte: " + Byte.MIN_VALUE + " .. " + Byte.MAX_VALUE);
        System.out.println("short: " + Short.MIN_VALUE + " .. " + Short.MAX_VALUE);
        System.out.println("int: " + Integer.MIN_VALUE + " .. " + Integer.MAX_VALUE);
        System.out.println("long: " + Long.MIN_VALUE + " .. " + Long.MAX_VALUE);
        System.out.println("values: " + b + ", " + s + ", " + i + ", " + l);

        byte a = 10, c = 20;
        int sum = a + c;
        System.out.println("byte + byte -> int: " + sum);

        System.out.println("int overflow: " + (Integer.MAX_VALUE + 1));
        System.out.println("promote before add: " + ((long) Integer.MAX_VALUE + 1));
        System.out.println("narrowing long -> int: " + (int) 3_000_000_000L);

        System.out.println("division: " + (-7 / 3) + ", remainder: " + (-7 % 3));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addExact: overflow detected");
        }
        System.out.println("unsigned view of -1: " + Integer.toUnsignedLong(-1));
    }
}
```

Biên dịch/chạy:

```bash
javac IntegerTypesDemo.java
java IntegerTypesDemo
```

Đầu ra:

```text
byte: -128 .. 127
short: -32768 .. 32767
int: -2147483648 .. 2147483647
long: -9223372036854775808 .. 9223372036854775807
values: 127, 30000, 2000000000, 3000000000
byte + byte -> int: 30
int overflow: -2147483648
promote before add: 2147483648
narrowing long -> int: -1294967296
division: -2, remainder: -1
addExact: overflow detected
unsigned view of -1: 4294967295
```

**Giải thích:** Tổng hai `byte` được xử lý theo `int`; cộng `Integer.MAX_VALUE + 1` tràn miền `int`; nâng một toán hạng lên `long` trước khi cộng giữ được `2147483648`; cast `3_000_000_000L` về `int` bỏ bit cao; chia âm cắt phần dư thập phân về 0; `Math.addExact` chủ động phát hiện overflow; `Integer.toUnsignedLong` chỉ đổi cách hiểu bit.

## 10. Tiện ích của wrapper và boxing

| Việc cần làm | API | Lưu ý |
| --- | --- | --- |
| Đọc giới hạn | `Integer.MIN_VALUE`, `Long.MAX_VALUE` | Tránh số cố định khó kiểm chứng |
| Đổi chuỗi thành số | `Integer.parseInt("42")`, `Long.parseLong("3000000000")` | `NumberFormatException` nếu sai định dạng hoặc vượt miền |
| Đổi số thành chuỗi | `Integer.toString(x)`, `Long.toString(y)` | Không mở rộng phạm vi dữ liệu |
| So sánh | `Integer.compare(x, y)`, `Long.compare(x, y)` | An toàn hơn cách so sánh dựa vào dấu của `x-y` khi phép trừ có thể tràn |
| Kiểm tra phép tính | `Math.addExact`, `Math.multiplyExact`, `Math.toIntExact` | Phát hiện một số lỗi overflow |
| Chuyển cách hiểu bit | `Byte.toUnsignedInt`, `Integer.toUnsignedLong` | Hữu ích cho binary/network protocol |

`Byte`, `Short`, `Integer` và `Long` là **wrapper reference types**, khác với `byte`, `short`, `int` và `long` primitive. `List<Integer>` chứa wrapper, có boxing/unboxing. Wrapper có thể là `null`, và **unboxing `null` gây `NullPointerException`**. Đối với mảng `int[]`, phần tử là giá trị primitive, không phải object `Integer` riêng lẻ.

## 11. Chọn kiểu phù hợp

| Nhu cầu | Kiểu gợi ý | Vì sao |
| --- | --- | --- |
| Số lượng, bộ đếm, vòng lặp, chỉ số mảng, số học thông thường | `int` | Đủ cho phần lớn số nguyên thông thường và phù hợp cơ chế nâng kiểu |
| Timestamp, khoảng thời gian theo mili giây, bộ đếm rất lớn | `long` | Miền rộng hơn `int`; vẫn cần kiểm tra tràn phép tính |
| Một byte dữ liệu trong file, buffer hoặc giao thức | `byte`/`byte[]` | Phù hợp đơn vị dữ liệu 8 bit; có thể diễn giải unsigned khi cần |
| Dữ liệu nguồn thực sự yêu cầu số nguyên 16 bit có dấu | `short` | Thể hiện chính xác giới hạn/định dạng 16 bit |
| Số nguyên vượt miền 64 bit | `BigInteger` | Không giới hạn ở 64 bit cố định |

Đừng dùng `byte` hoặc `short` chỉ vì nghĩ phép toán sẽ hiệu quả hơn; nhiều toán tử Java vẫn nâng chúng lên `int`. Nếu dữ liệu nguồn cho phép tới 255, một `byte` có dấu **không** biểu diễn trực tiếp mọi giá trị 0..255 theo ngữ nghĩa có dấu. Hãy xác định đơn vị, miền giá trị và cách chuyển đổi trước khi chọn kiểu.

## 12. Lỗi thường gặp và cách tránh

1. **Nhầm `int` là 64 bit trên máy 64 bit:** Java giữ độ rộng cố định 32/64 bit.
2. **Quên `L` với literal thập phân lớn:** `long x = 3_000_000_000;` không hợp lệ; cần `3_000_000_000L`.
3. **Gán `byte + byte` về `byte`:** kết quả biểu thức là `int`; phải đổi khai báo đích hoặc cast sau khi kiểm tra miền.
4. **Ép kiểu sau khi biểu thức đã tràn:** `long r = (long) (x * y);` không phục hồi bit mất; nâng toán hạng trước phép nhân.
5. **Cho rằng cast tự báo lỗi/kẹp giới hạn:** `(byte) 130` bằng `-126`, không phải 127.
6. **Cho rằng cộng nguyên tự ném overflow:** cộng/trừ/nhân thường quấn vòng; dùng các hàm `Exact` khi cần.
7. **Chia số nguyên và mong ra số lẻ:** `1 / 2` bằng 0; cần dùng phép toán kiểu số thực hoặc biểu diễn số thập phân theo yêu cầu khác.
8. **Cho rằng `-7 / 3` bằng -3:** phép chia nguyên `/` cắt về 0 nên bằng -2.
9. **Dùng `x - y` để lấy dấu so sánh:** hiệu có thể tràn; dùng phép so sánh hoặc `Integer.compare`.
10. **Cho rằng `byte` là số nguyên 0..255:** đó là cách diễn giải không dấu; `byte` primitive có dấu là -128..127.

## 13. Tự kiểm tra

- `short` có chứa 40.000 không? **Không**, vì tối đa là 32.767.
- `long id = 5_000_000_000;` có biên dịch không? **Không**; literal thập phân phải có `L`.
- `byte a = 5, b = 6;` thì `a + b` có kiểu gì? **`int`**.
- `int x = 1_500_000_000; long y = x * 2;` có cho 3 tỷ không? **Không**, biểu thức nhân kiểu `int` đã tràn. Dùng `x * 2L`.
- `Math.addExact(Integer.MAX_VALUE, 1)` có trả một `int` bị quấn vòng không? **Không**; nó ném `ArithmeticException`.
- `Integer.toUnsignedLong(-1)` là bao nhiêu? **4_294_967_295L**, trong khi biến `int` đầu vào vẫn là -1.

**Ghi nhớ:** `byte`/`short`/`int`/`long` đều lưu chính xác số nguyên **trong phạm vi của mình**. Khác biệt cốt lõi là **8 / 16 / 32 / 64 bit**. Trước khi tính toán, xác định kiểu của **literal và toán hạng**; trước khi thu hẹp, kiểm tra phạm vi; khi cần phát hiện tràn, dùng API kiểm tra phù hợp.
