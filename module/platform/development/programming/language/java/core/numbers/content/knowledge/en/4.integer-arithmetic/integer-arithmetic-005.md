# Phép toán đơn ngôi và tiền tố, hậu tố `++`, `--` trong Java

**Toán tử đơn ngôi** (*unary operator*) tác động lên một toán hạng, chẳng hạn `-x` hoặc `~mask`. Hai toán tử **tăng một đơn vị `++`** và **giảm một đơn vị `--`** có hai cách viết: đặt **trước** biến (`++i`, `--i`) hoặc **sau** biến (`i++`, `i--`). Điểm quan trọng nhất là cả hai dạng đều thay đổi biến, nhưng **giá trị mà biểu thức trả về khác nhau**.

Trong phạm vi số học nguyên, cần hiểu đồng thời kiểu của kết quả, phạm vi giá trị, tràn số, thứ tự đánh giá và điều kiện để toán hạng có thể thay đổi. Bài này dùng Java 17+ và phân biệt các ví dụ chạy độc lập với những dòng chỉ dùng để minh họa lỗi biên dịch.

## 1. Các toán tử đơn ngôi liên quan

| Cú pháp | Tên | Ý nghĩa | Kiểu toán hạng |
| --- | --- | --- | --- |
| `+x` | Dấu cộng đơn ngôi | Lấy giá trị số sau *unary numeric promotion*; không đổi dấu | Kiểu số nguyên hoặc số thực |
| `-x` | Dấu trừ đơn ngôi | Đổi dấu giá trị số sau *unary numeric promotion* | Kiểu số nguyên hoặc số thực |
| `~x` | Bù bit (*bitwise complement*) | Đảo từng bit của giá trị đã nâng kiểu | Chỉ kiểu số nguyên |
| `!flag` | Phủ định logic | `true` thành `false` và ngược lại | `boolean` hoặc `Boolean` (unboxing) |
| `++x` / `x++` | Tăng tiền tố / hậu tố | Thay đổi biến bằng cách tăng 1; khác ở giá trị trả về | Biến có kiểu số nguyên/số thực hoặc wrapper số tương ứng |
| `--x` / `x--` | Giảm tiền tố / hậu tố | Thay đổi biến bằng cách giảm 1; khác ở giá trị trả về | Biến có kiểu số nguyên/số thực hoặc wrapper số tương ứng |

`+` và `-` cũng tồn tại ở **dạng nhị nguyên**: `a + b` cộng hai số, `a - b` trừ hai số. Java xác định dạng đang dùng dựa trên cấu trúc biểu thức:

```java
int a = 5;
int positive = +a; // 5: cộng đơn ngôi
int negative = -a; // -5: trừ đơn ngôi
int sum = a + 2;   // 7: cộng nhị nguyên
int difference = a - 2; // 3: trừ nhị nguyên
```

`+` đơn ngôi **không phải toán tử nối chuỗi**: `+"abc"` không hợp lệ. Toán tử logic `!` chỉ áp dụng cho boolean; không có quy tắc kiểu C/C++ coi `0` tương đương `false`:

```java
boolean enabled = true;
boolean disabled = !enabled; // false
// boolean invalid = !0;      // lỗi: int không phải boolean
// int invalidBits = ~true;    // lỗi: ~ không nhận boolean
```

## 2. Nâng kiểu số học đơn ngôi (*unary numeric promotion*)

Với `+x`, `-x` và `~x`, Java thực hiện *unary numeric promotion* trước khi tạo kết quả. Đây là khác biệt dễ bỏ sót khi toán hạng là `byte`, `short` hoặc `char`.

| Kiểu toán hạng | Kiểu kết quả của `+x`, `-x` | Kiểu kết quả của `~x` |
| --- | --- | --- |
| `byte`, `short`, `char` | `int` | `int` |
| `int` | `int` | `int` |
| `long` | `long` | `long` |
| `float` | `float` | Không hợp lệ |
| `double` | `double` | Không hợp lệ |

Wrapper số như `Byte` có thể được *unbox* rồi nâng kiểu; nếu giá trị wrapper là `null` thì việc unboxing có thể gây `NullPointerException`.

Ví dụ:

```java
byte b = 5;
int x = +b;  // +b có kiểu int
int y = -b;  // -b có kiểu int
int z = ~b;  // ~b có kiểu int, giá trị -6

// byte wrong = -b; // lỗi: kết quả int không tự gán về byte
byte converted = (byte) -b; // -5, ép kiểu có chủ đích
```

Điểm cần phân biệt: **`b++` vẫn cập nhật biến `b` theo kiểu `byte`**, dù `+b` và `-b` tạo kết quả kiểu `int`. Quy tắc đặc biệt của `++`/`--` sẽ được giải thích bên dưới.

### Bù bit `~` và biểu diễn bù hai

Với `int`, `~` đảo toàn bộ 32 bit; với `long`, đảo toàn bộ 64 bit. Ta có đồng nhất thức toán học theo biểu diễn bù hai:

```text
~x == -x - 1
```

Ví dụ:

```java
int mask = 0b1010; // 10
int oppositeBits = ~mask; // -11
```

`~10` không ra `0b0101` (5), vì `int` có **32 bit**, gồm cả các bit 0 bên trái bốn bit thấp. Đảo tất cả 32 bit tạo ra giá trị âm `-11`. Muốn **chỉ đảo bốn bit thấp**, dùng mặt nạ:

```java
int lowFourFlipped = (~0b1010) & 0b1111; // 0b0101 = 5
```

Đừng nhầm `~` với `!`: `~` làm việc trên bit số nguyên, còn `!` làm việc trên giá trị logic.

## 3. `++` và `--`: tác dụng phụ và giá trị của biểu thức

Mỗi toán tử tăng/giảm vừa **đọc giá trị cũ**, vừa **ghi giá trị mới** vào biến. Về giá trị dùng trong một biểu thức lớn hơn:

- **Tiền tố `++i`:** tăng biến `i` trước; giá trị biểu thức là **giá trị mới**.
- **Hậu tố `i++`:** tăng biến `i`; giá trị biểu thức là **giá trị cũ**.
- **Tiền tố `--i`:** giảm biến trước; giá trị biểu thức là **giá trị mới**.
- **Hậu tố `i--`:** giảm biến; giá trị biểu thức là **giá trị cũ**.

Giả sử ban đầu `i = 5`. Mỗi hàng trong bảng sau là **một lần chạy độc lập** bắt đầu từ 5:

| Biểu thức | Giá trị biểu thức | Giá trị `i` sau biểu thức |
| --- | ---: | ---: |
| `++i` | 6 | 6 |
| `i++` | 5 | 6 |
| `--i` | 4 | 4 |
| `i--` | 5 | 4 |

Ví dụ hậu tố:

```java
int i = 5;
int old = i++; // old = 5; i = 6
```

Ví dụ tiền tố:

```java
int i = 5;
int current = ++i; // current = 6; i = 6
```

Khi **dùng như một câu lệnh độc lập**, `i++` và `++i` đều làm `i` tăng một. Khác biệt quan trọng khi kết quả biểu thức được dùng, ví dụ `int a = i++;` hoặc `System.out.println(++i);`.

Tương tự `i--` và `--i` đều giảm một khi đứng một mình, nhưng cách trả về giá trị cũ/mới vẫn khác nhau.

### Đọc output từ đầu đến cuối

Tệp Java hoàn chỉnh sẽ có ở phần 9. Với hai câu lệnh này:

```java
int n = 3;
System.out.println(n++); // in 3; sau đó n thành 4
System.out.println(++n); // n thành 5; in 5
```

Output theo đúng thứ tự là `3` rồi `5`. Không thể hiểu hậu tố theo nghĩa “tăng muộn ở một thời điểm tùy ý”; tác dụng ghi vào biến xảy ra trong quá trình đánh giá biểu thức đó. Chỉ **giá trị trả về của biểu thức hậu tố** là giá trị trước khi tăng/giảm.

## 4. Kiểu của `++`/`--` và vì sao `byte` vẫn tăng được

Với `++`/`--`, toán hạng phải là một **biến** có kiểu số. Java lấy giá trị của biến, thực hiện phép tăng/giảm theo quy tắc số học, rồi **chuyển kết quả trở lại kiểu của biến** trước khi lưu. Giá trị của biểu thức tăng/giảm cũng có kiểu của biến đó.

Do vậy:

```java
byte count = 127;
count++;  // hợp lệ: byte từ 127 tràn sang -128
byte result = count++; // hợp lệ: kết quả hậu tố cũng có kiểu byte
```

Khác với:

```java
byte count = 5;
// byte invalid = count + 1; // lỗi: count + 1 có kiểu int
// byte invalid2 = +count;   // lỗi: +count có kiểu int
count++;                   // hợp lệ: phép ++ có quy tắc chuyển kiểu đặc biệt
```

Câu `count++` **không tương đương về kiểu** với việc viết một phép gán `count = count + 1;`, vì biểu thức `count + 1` là `int`. `count += 1;` cũng hợp lệ trong nhiều trường hợp nhưng là toán tử gán kết hợp có quy tắc riêng và cần hiểu hệ quả ép kiểu.

Điểm chú ý đối với wrapper:

```java
Integer boxed = 3;
boxed++;  // unbox Integer -> int, tăng, box lại thành Integer
// Integer missing = null;
// missing++; // biên dịch được nhưng ném NullPointerException lúc chạy
```

Wrapper `Integer` là tham chiếu tới object; đây là phép **gán lại biến tham chiếu tới một giá trị mới được boxing**, không có chuyện thay đổi nội dung object `Integer` bất biến.

`char` cũng là kiểu nguyên 16 bit không dấu và có thể tăng:

```java
char letter = 'A';
letter++;                // 'B'
int code = letter;       // 66
```

Không dùng `++` trên `boolean`, `String` hoặc `BigInteger`. Với `BigInteger`, nên gọi `add(BigInteger.ONE)` để tạo giá trị mới.

## 5. Biến nào là toán hạng hợp lệ của `++` và `--`?

Toán tử tăng/giảm phải tác động lên **biến có thể gán được** (*assignable variable*) có kiểu số. Ví dụ:

```java
int local = 1;
local++;                 // biến cục bộ
int[] items = {4};
items[0]++;              // phần tử mảng
Counter counter = new Counter();
counter.value++;         // field có thể gán
```

`Counter` ở trên là một class minh họa, ví dụ:

```java
class Counter {
    int value;
}
```

Các trường hợp dưới đây sai nếu bỏ dấu chú thích:

```java
// 5++;                 // literal không phải biến
// (2 + 3)++;           // giá trị phép cộng không phải biến
// getNumber()++;       // giá trị trả về của method không phải biến
final int limit = 10;
// limit++;             // final không thể gán lại
```

Một biến cục bộ phải được **gán chắc chắn trước khi tăng/giảm**, vì `++` và `--` luôn cần đọc giá trị cũ:

```java
void example() {
    int number;
    // number++; // lỗi biên dịch: number chưa được khởi tạo
    number = 0;
    number++;    // hợp lệ
}
```

Đoạn `example()` chỉ là một method minh họa đặt trong class; không có method `main` nên không độc lập để chạy.

## 6. Thứ tự đánh giá trong biểu thức có nhiều lần tăng

Java đánh giá các toán hạng theo thứ tự xác định từ **trái sang phải**. Vì vậy Java cho kết quả xác định đối với biểu thức như sau:

```java
int i = 1;
int sum = i++ + ++i;
```

Diễn tiến:

1. Đánh giá toán hạng bên trái `i++`: lấy giá trị biểu thức là `1` rồi cập nhật `i = 2`.
2. Đánh giá toán hạng bên phải `++i`: cập nhật `i = 3` rồi lấy giá trị biểu thức là `3`.
3. Cộng `1 + 3` thành `4`; sau câu lệnh, `i = 3`.

Do đó `sum == 4` và `i == 3`. Đây là hành vi Java xác định, nhưng kiểu mã trên **khó đọc và dễ bảo trì sai**. Trong code ứng dụng, ưu tiên tách ra:

```java
int i = 1;
int left = i;
i++;
i++;
int right = i;
int sum = left + right; // 4; i = 3
```

Chỉ đọc `i++` và `++i` theo ý nghĩa giá trị cũ/mới; không dựa vào mẹo ghi nhớ mơ hồ “trước thì trước, sau thì sau” mà quên theo dõi biến được cập nhật lúc nào.

### Bẫy: `i = i++`

```java
int i = 1;
i = i++;
```

Phép `i++` tạo giá trị biểu thức **`1`**, đồng thời cập nhật biến lên 2. Sau đó phép gán bên ngoài ghi **`1`** trở lại `i`. Kết quả cuối cùng vẫn là **`i == 1`**.

Đây là ví dụ điển hình cho thấy hậu tố có hai kết quả cần phân biệt: *side effect* lên biến và *giá trị biểu thức được sử dụng*. Nếu chỉ muốn tăng, viết riêng `i++;`. Đừng kết hợp gán lại cùng một biến.

### Thứ tự đánh giá với phần tử mảng

```java
int[] values = {3};
int index = 0;
int previous = values[index++]++;
```

Java đánh giá mảng và chỉ số, nên phần tử được chọn là `values[0]`; đồng thời `index` tăng lên 1. Toán tử hậu tố trên phần tử trả giá trị cũ `3` rồi ghi `4` vào `values[0]`. Kết quả: `previous == 3`, `values[0] == 4` và `index == 1`.

Khi chỉ cần tăng một phần tử, cách `values[index]++;` thường dễ hiểu hơn; tăng cả `index` và phần tử trong cùng biểu thức có thể gây nhầm lẫn.

## 7. Tràn số và các giá trị biên

`++`, `--` không tự ném exception khi số nguyên primitive vượt phạm vi. Java số nguyên có độ rộng cố định; các phép tính có thể **tràn** (*overflow*).

```java
int max = Integer.MAX_VALUE; // 2147483647
max++;                      // -2147483648

int min = Integer.MIN_VALUE; // -2147483648
min--;                      // 2147483647

byte b = Byte.MAX_VALUE;     // 127
b++;                        // -128
```

Cũng cần chú ý toán tử trừ đơn ngôi tại biên:

```java
int min = Integer.MIN_VALUE;
int negated = -min; // vẫn -2147483648 do int không biểu diễn được +2147483648
long exact = -(long) min; // 2147483648: mở rộng trước rồi đổi dấu
```

Nếu bài toán yêu cầu phát hiện tràn thay vì chấp nhận quay vòng, sử dụng `Math.addExact(x, 1)`, `Math.subtractExact(x, 1)` hoặc `Math.negateExact(x)` khi phù hợp cho kiểu `int`/`long`. Ví dụ `Math.incrementExact(Integer.MAX_VALUE)` ném `ArithmeticException` thay vì trả số âm. Những method này **không được gọi ngầm** bởi `++`/`--`.

Với số thực `float`/`double`, `++`/`--` vẫn hợp lệ; nhưng do độ chính xác hữu hạn, tăng 1 có thể **không làm giá trị thay đổi** ở độ lớn nhất định. Tránh dùng số thực nhị phân cho tiền tệ; đây là vấn đề độ chính xác số học, không phải riêng toán tử `++`.

## 8. Lỗi thường gặp và cách sửa

| Nhầm lẫn / lỗi | Giải thích đúng |
| --- | --- |
| “`i++` và `++i` luôn trả về cùng giá trị” | Chúng cùng tăng biến, nhưng hậu tố trả giá trị cũ; tiền tố trả giá trị mới |
| “`System.out.println(i++)` sẽ in giá trị mới” | `println` nhận giá trị cũ của biểu thức hậu tố |
| “`-b` có kiểu `byte` nếu `b` là byte” | Unary numeric promotion khiến kết quả có kiểu `int` |
| “`~0b1010` bằng `0b0101`” | `~` đảo đủ 32 bit của `int` nên ra `-11`; muốn chỉ 4 bit, cần mặt nạ |
| “`byte b = 127; b++;` là lỗi biên dịch” | Hợp lệ; khi tăng sẽ tràn về `-128` |
| “`i = i++;` giúp tăng i” | Phép gán cuối cùng ghi đè thay đổi, khiến `i` giữ giá trị cũ |
| “Có thể viết `5++` hoặc `getNumber()++`” | Toán hạng phải là biến gán được, không phải literal hay giá trị method |
| “`final int n = 1; n++;` hợp lệ” | Không thể gán lại biến `final` |
| “`Integer n = null; n++;` tự khởi tạo n thành 1” | Unboxing `null` gây `NullPointerException` |
| “`i++` luôn an toàn khi nhiều thread cùng chạy” | Đọc, cộng và ghi là các bước; `++` không bảo đảm cập nhật nguyên tử giữa nhiều thread |

### Ghi chú về nhiều luồng

`counter++` trên biến dùng chung **không phải thao tác nguyên tử**. Hai thread có thể đọc cùng giá trị và ghi đè kết quả của nhau, dẫn đến mất lần tăng. Nếu cần bộ đếm dùng chung, một lựa chọn là `AtomicInteger`:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger(0);
int old = counter.getAndIncrement(); // trả giá trị cũ
int current = counter.incrementAndGet(); // trả giá trị mới
```

Đây là ví dụ nhỏ đối chiếu ngữ nghĩa hậu tố/tiền tố; việc thiết kế đồng bộ giữa thread là chủ đề riêng.

## 9. Chương trình chạy độc lập trên Java 17+

Tạo tệp **`UnaryOperatorsDemo.java`**:

```java
public class UnaryOperatorsDemo {
    public static void main(String[] args) {
        int i = 5;
        System.out.println("postIncValue=" + i++);
        System.out.println("afterPostInc=" + i);
        System.out.println("preIncValue=" + ++i);
        System.out.println("afterPreInc=" + i);
        System.out.println("postDecValue=" + i--);
        System.out.println("afterPostDec=" + i);
        System.out.println("preDecValue=" + --i);
        System.out.println("afterPreDec=" + i);

        byte b = 127;
        b++;
        System.out.println("byteWrap=" + b);

        int mask = 0b1010;
        System.out.println("unaryPlus=" + (+mask));
        System.out.println("unaryMinus=" + (-mask));
        System.out.println("bitwiseNot=" + (~mask));
        System.out.println("lowFourNot=" + ((~mask) & 0b1111));
        System.out.println("logicalNot=" + (!true));

        int j = 1;
        int sum = j++ + ++j;
        System.out.println("combinedSum=" + sum);
        System.out.println("combinedJ=" + j);

        int assigned = 1;
        assigned = assigned++;
        System.out.println("assignedPost=" + assigned);

        int[] values = {3};
        int index = 0;
        int previous = values[index++]++;
        System.out.println("arrayOld=" + previous);
        System.out.println("arrayCurrent=" + values[0]);
        System.out.println("arrayIndex=" + index);

        int min = Integer.MIN_VALUE;
        System.out.println("negMinInt=" + (-min));
        System.out.println("negMinLong=" + (-(long) min));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac UnaryOperatorsDemo.java
java UnaryOperatorsDemo
```

Output chính xác:

```text
postIncValue=5
afterPostInc=6
preIncValue=7
afterPreInc=7
postDecValue=7
afterPostDec=6
preDecValue=5
afterPreDec=5
byteWrap=-128
unaryPlus=10
unaryMinus=-10
bitwiseNot=-11
lowFourNot=5
logicalNot=false
combinedSum=4
combinedJ=3
assignedPost=1
arrayOld=3
arrayCurrent=4
arrayIndex=1
negMinInt=-2147483648
negMinLong=2147483648
```

Đọc từng dòng theo hai câu hỏi: **biến đã thay đổi thành gì?** và **giá trị biểu thức được truyền cho `println` là gì?** Ví dụ `postIncValue=5` đi kèm `afterPostInc=6` là bằng chứng rõ ràng rằng hậu tố trả giá trị cũ nhưng đã cập nhật biến.

## 10. Quy trình giải bài toán có `++`/`--`

Khi phân tích một biểu thức, làm theo thứ tự:

1. **Kiểm tra toán hạng:** `++`/`--` cần biến số gán được, đã được gán trước khi đọc và không phải `final` không thể cập nhật.
2. **Xác định vị trí toán tử:** tiền tố trả giá trị sau thay đổi, hậu tố trả giá trị trước thay đổi.
3. **Theo dõi tác dụng phụ:** cập nhật giá trị biến đúng một bước tăng/giảm (có thể tràn hoặc chịu quy tắc số thực).
4. **Theo dõi thứ tự tính biểu thức:** Java đánh giá các toán hạng từ trái sang phải; nếu một biến xuất hiện nhiều lần, ghi lại cả giá trị trả về và giá trị biến tại mỗi bước.
5. **Kiểm tra kiểu:** `+`, `-`, `~` có nâng kiểu số học; `++`, `--` lưu kết quả trở lại kiểu biến và có thể thu hẹp/tràn.
6. **Ưu tiên viết rõ:** trong mã sản phẩm, tránh trộn nhiều lần tăng/giảm hoặc vừa gán vừa hậu tố trên cùng biến. Chia thành các câu lệnh độc lập khi logic không cần biểu thức phức tạp.

**Điểm cần nhớ:** `++i` trả giá trị **mới**, `i++` trả giá trị **cũ**, nhưng cả hai đều tăng biến. Dấu `+`/`-` đơn ngôi và `~` lại tuân theo quy tắc nâng kiểu số học; hiểu rõ kiểu, thứ tự đánh giá và giá trị biên giúp tránh lỗi khó phát hiện.