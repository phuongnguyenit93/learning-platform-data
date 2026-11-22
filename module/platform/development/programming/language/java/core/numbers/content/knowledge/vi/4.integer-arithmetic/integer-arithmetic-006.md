# Độ ưu tiên, tính kết hợp và thứ tự đánh giá toán hạng trong Java

> **Java core – numbers · Số học nguyên**  
> **Mục tiêu:** Phân biệt đúng *precedence*, *associativity* và *evaluation order*; đọc được các biểu thức số học nguyên, bitwise và điều kiện; dự đoán kết quả khi toán hạng có tác dụng phụ; biết khi nào phải đặt ngoặc để chương trình rõ nghĩa và an toàn.

## 1. Ba quy tắc trả lời ba câu hỏi khác nhau

Khi đọc biểu thức Java như:

```java
int result = 2 + 3 * 4;
```

Ta cần phân biệt **ba khái niệm**:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Độ ưu tiên toán tử** (*operator precedence*) | Toán tử nào **gắn với toán hạng nào**, biểu thức được nhóm như thế nào? | `2 + 3 * 4` được nhóm `2 + (3 * 4)`, kết quả 14 |
| **Tính kết hợp** (*associativity*) | Các toán tử **cùng mức ưu tiên** được nhóm theo bên trái hay bên phải? | `20 - 6 - 2` nhóm `(20 - 6) - 2`, kết quả 12 |
| **Thứ tự đánh giá** (*evaluation order*) | Các **toán hạng/biểu thức con được thực thi** theo trình tự nào, đặc biệt nếu gọi hàm hoặc sửa biến? | Trong `a() + b() * c()`, Java đánh giá `a()` trước `b()` rồi `c()`, mặc dù phép nhân có độ ưu tiên cao hơn |

**Điểm mấu chốt:** “`*` ưu tiên hơn `+`” **không có nghĩa** hàm tạo toán hạng cho phép nhân chắc chắn chạy trước hàm tạo toán hạng cho phép cộng. *Precedence* quyết định **cấu trúc phép tính**; *evaluation order* quyết định **trình tự thực hiện biểu thức con**.

Ví dụ sau đánh giá `left()` trước rồi mới đến `middle()` và `right()`, nhưng vẫn nhân hai kết quả cuối trước khi cộng:

```java
int answer = left() + middle() * right();
// Nhóm tương đương: left() + (middle() * right())
// Thứ tự gọi hàm: left(), middle(), right()
```

Mặc dù một số compiler có thể tối ưu việc tính toán, hành vi quan sát được của chương trình Java phải tuân thủ ngữ nghĩa thứ tự đánh giá được quy định.

## 2. Bảng độ ưu tiên toán tử thường gặp

Đọc **từ trên xuống dưới**: mức trên có độ ưu tiên cao hơn mức dưới. Đây là bảng thực hành tập trung vào số học và các toán tử thường xuất hiện cùng biểu thức số.

| Mức (cao → thấp) | Toán tử | Ví dụ và cách nhóm |
| --- | --- | --- |
| Hậu tố (*postfix*) | `expr++`, `expr--` | `i++` trả giá trị cũ rồi tăng biến |
| Đơn ngôi (*unary*) | `++expr`, `--expr`, `+expr`, `-expr`, `~expr`, `!expr` | `-a * b` nhóm `(-a) * b` |
| Nhân/chia/chia dư | `*`, `/`, `%` | `a + b * c` nhóm `a + (b * c)` |
| Cộng/trừ | `+`, `-` | `a + b << 2` nhóm `(a + b) << 2` |
| Dịch bit | `<<`, `>>`, `>>>` | `1 << 2 + 1` nhóm `1 << (2 + 1)` |
| So sánh thứ tự | `<`, `<=`, `>`, `>=`, `instanceof` | `a + b < c` nhóm `(a + b) < c` |
| So sánh bằng | `==`, `!=` | `a < b == flag` nhóm `(a < b) == flag` |
| AND bitwise/boolean | `&` | `(a & b) == c` phải đặt ngoặc nếu muốn so sánh kết quả AND |
| XOR bitwise/boolean | `^` | `a ^ b & c` nhóm `a ^ (b & c)` |
| OR bitwise/boolean | `|` | `a | b ^ c` nhóm `a | (b ^ c)` |
| AND logic ngắn mạch | `&&` | `checkA() && checkB()` |
| OR logic ngắn mạch | `||` | `checkA() || checkB()` |
| Điều kiện | `? :` | `a ? x : b ? y : z` là `a ? x : (b ? y : z)` |
| Gán và gán kết hợp | `=`, `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `^=`, `|=`, `<<=`, `>>=`, `>>>=` | `a = b = c` nhóm `a = (b = c)` |

**Lưu ý về bảng:** ngoặc tròn `(...)` chủ động chỉ định cách nhóm; truy cập thành viên, gọi phương thức, indexing, cast, tạo đối tượng và các cấu trúc đặc biệt của ngữ pháp cũng có quy tắc riêng. Bảng trên là phần quy tắc quan trọng khi học biểu thức, **không phải toàn bộ ngữ pháp Java**.

Trong code production, dấu ngoặc thường đáng dùng ngay cả khi không bắt buộc, nhất là lúc kết hợp shift, bitwise, so sánh và điều kiện.

### Ví dụ nhanh để đọc đúng bảng

```java
int a = 2 + 3 * 4;         // 14 = 2 + 12
int b = (2 + 3) * 4;       // 20
int c = 1 << 2 + 1;        // 8 = 1 << (2 + 1)
int d = (1 << 2) + 1;      // 5
int e = 17 % 5 * 2;        // 4 = (17 % 5) * 2
int f = 2 | 4 & 3;         // 2 = 2 | (4 & 3)
boolean g = (5 & 3) == 1; // true
```

Biểu thức `5 & 3 == 1` **không tương đương** `(5 & 3) == 1`. Vì `==` có độ ưu tiên cao hơn `&`, Java cố nhóm `5 & (3 == 1)`. Vế phải lúc đó là `boolean`, còn vế trái là `int`, gây **lỗi biên dịch**. Khi kiểm tra bit bằng mask, viết rõ `(value & mask) == expected` hoặc `(value & mask) != 0`.

## 3. Tính kết hợp: nhóm từ trái hoặc từ phải

**Associativity** chỉ có ý nghĩa khi biểu thức gồm các toán tử có cách nhóm có thể gây nhập nhằng tại cùng một mức ưu tiên.

### 3.1. Nhiều toán tử nhị phân kết hợp trái

Các toán tử số học như `+`, `-`, `*`, `/` và `%` ở cùng mức tương ứng được nhóm **từ trái sang phải**.

```text
20 - 6 - 2
= (20 - 6) - 2
= 12

20 - (6 - 2)
= 20 - 4
= 16
```

```java
int leftGrouped = 20 - 6 - 2;      // 12
int rightGrouped = 20 - (6 - 2);   // 16

int quotient = 100 / 5 / 2;       // 10 = (100 / 5) / 2
int other = 100 / (5 / 2);        // 50: 5 / 2 = 2, rồi 100 / 2
```

Vì phép chia nguyên bỏ phần thập phân theo hướng về 0, thay ngoặc có thể thay đổi đáng kể kết quả. Ví dụ `7 / 2 * 2 = 6`, dù biểu thức toán học trên số thực `(7/2)×2 = 7`. Trong Java, `/` và `*` **cùng mức ưu tiên**; cách nhóm bên trái và kiểu số của toán hạng mới quyết định kết quả.

Tương tự, `1 << 2 << 1` nhóm `(1 << 2) << 1`, kết quả 8. Các toán tử shift ở cùng mức có cách nhóm trái.

### 3.2. Phép gán kết hợp phải

```java
int a, b, c;
a = b = c = 7;
```

Cách nhóm là:

```text
a = (b = (c = 7))
```

Cả ba biến đều nhận 7. Biểu thức gán trả về giá trị được gán, vì vậy kết quả của `c = 7` được dùng làm giá trị để gán cho `b`, rồi `a`.

**Không suy ra** từ tính kết hợp phải rằng “mọi toán hạng đều được thực thi từ phải sang trái”. Phần **đánh giá vế trái của phép gán** và các biểu thức con vẫn có quy tắc đánh giá riêng. Cách nhóm của biểu thức và thứ tự thực thi có thể khác nhau.

### 3.3. Toán tử ba ngôi kết hợp phải

```java
int value = false ? 10 : true ? 20 : 30;
// Nhóm: false ? 10 : (true ? 20 : 30)
// Kết quả: 20
```

Để dễ bảo trì, đặt ngoặc rõ ràng trong biểu thức điều kiện lồng nhau, hoặc dùng `if/else` nếu nội dung phức tạp. Chỉ **một** trong hai nhánh tương ứng với kết quả điều kiện được đánh giá.

## 4. Java đánh giá toán hạng theo thứ tự từ trái sang phải

Với phần lớn biểu thức toán tử nhị phân thông thường, Java **đánh giá toán hạng bên trái trước**, rồi toán hạng bên phải; sau đó mới thực hiện phép toán với các giá trị thu được.

Xét:

```java
int result = first() + second() * third();
```

Cây cấu trúc phép tính:

```text
         (+)
        /   \
   first()   (*)
            /   \
       second() third()
```

Trình tự thực thi khi chạy:

```text
1. Gọi first(), giữ giá trị trả về
2. Gọi second(), giữ giá trị trả về
3. Gọi third(), giữ giá trị trả về
4. Nhân kết quả second() với third()
5. Cộng kết quả first() vào tích
```

Đây là ví dụ điển hình chứng minh **độ ưu tiên phép toán** không đồng nghĩa **ưu tiên chạy hàm**.

Lệnh gọi phương thức cũng đánh giá các đối số theo thứ tự từ trái sang phải. Ví dụ `method(first(), second())` gọi `first()` trước `second()`; nếu đối số thứ nhất ném ngoại lệ, đối số thứ hai không được đánh giá.

Java còn bảo đảm sự quan sát nhất quán các tác dụng phụ theo thứ tự quy định, kể cả khi compiler hoặc máy ảo tối ưu các biểu thức không gây thay đổi hành vi quan sát được.

## 5. Increment/decrement: tiền tố và hậu tố

`++x` và `x++` đều tăng biến `x` thêm 1, nhưng **giá trị của biểu thức** khác nhau.

| Cách viết | Giá trị biểu thức | Giá trị biến sau thao tác |
| --- | --- | --- |
| `++x` | Giá trị **mới** của `x` | Đã tăng 1 |
| `x++` | Giá trị **cũ** của `x` | Đã tăng 1 |
| `--x` | Giá trị **mới** sau giảm | Đã giảm 1 |
| `x--` | Giá trị **cũ** trước giảm | Đã giảm 1 |

```java
int i = 1;
int a = i++; // a = 1, i = 2
int b = ++i; // b = 3, i = 3
```

Một biểu thức có nhiều tác dụng phụ vẫn có kết quả **được Java xác định**, nhưng dễ gây lỗi khi đọc:

```java
int i = 1;
int result = i++ + i++ * 10;
// Toán hạng trái của +: i++ trả 1, i thành 2.
// Toán hạng trái của *: i++ trả 2, i thành 3.
// Phép nhân: 2 * 10 = 20.
// Phép cộng: 1 + 20 = 21.
// Sau cùng: result = 21, i = 3.
```

Nếu nhầm rằng “nhân chạy trước nên `i++` của phép nhân phải chạy trước”, bạn sẽ dự đoán sai. Đây chính là sự khác nhau giữa **gắn toán tử với toán hạng** và **thực thi toán hạng**.

Dù Java xác định rõ kết quả, trong code nghiệp vụ nên tách tác dụng phụ để tránh người đọc phải mô phỏng trạng thái biến:

```java
int i = 1;
int first = i++;
int second = i++;
int result = first + second * 10; // 21
```

## 6. Toán tử logic ngắn mạch khác bitwise/boolean không ngắn mạch

Với toán hạng kiểu `boolean`:

- `a && b`: luôn đánh giá `a`; nếu `a` là `false` thì **bỏ qua** `b`.
- `a || b`: luôn đánh giá `a`; nếu `a` là `true` thì **bỏ qua** `b`.
- `a & b`, `a | b`, `a ^ b` dùng được với `boolean` nhưng **đánh giá cả hai vế** (trừ khi việc đánh giá vế trước bị dừng bởi ngoại lệ); không có tính ngắn mạch như `&&`, `||`.
- Với số nguyên, `&`, `|`, `^` là các toán tử bitwise; `&&`/`||` **không dùng cho số nguyên**.

```java
int divisor = 0;
boolean safe = divisor != 0 && 100 / divisor > 10; // false, không chia 0
```

Trong biểu thức trên, nếu thay `&&` bằng `&`, vế phải vẫn chạy và dẫn đến `ArithmeticException: / by zero`. Vì vậy thứ tự đánh giá và việc **có đánh giá hay không** là một phần của tính đúng đắn, không chỉ là chuyện hiệu năng.

```java
boolean accepted = true || expensiveCheck(); // expensiveCheck() không được gọi
boolean both = true & expensiveCheck();       // expensiveCheck() được gọi
```

Toán tử ba ngôi `condition ? whenTrue : whenFalse` cũng chỉ đánh giá một nhánh sau khi đã đánh giá điều kiện. Trong một biểu thức lồng nhau, đặt ngoặc hoặc dùng cấu trúc điều khiển khi nhánh có tác dụng phụ.

## 7. Ngoặc tròn thay đổi cách nhóm, không tự đảo thứ tự chạy

Dùng ngoặc để nêu rõ ý định:

```java
int defaultValue = 2 + 3 * 4;   // 14
int overridden = (2 + 3) * 4;   // 20
```

Nhưng:

```java
int result = first() + (second() * third());
```

vẫn gọi `first()` trước, rồi `second()`, rồi `third()`. Ngoặc ở đây làm rõ **cách nhóm đã có sẵn**; không ra lệnh “chạy `second()` trước `first()`”.

Nếu bạn thật sự muốn điều chỉnh thứ tự tác dụng phụ, hãy viết biểu thức thành nhiều câu lệnh theo thứ tự mong muốn:

```java
int secondValue = second();
int thirdValue = third();
int firstValue = first();
int result = firstValue + secondValue * thirdValue;
```

Không nên thay đổi cách nhóm tùy tiện vì với phép trừ/chia nguyên, tràn số hay phép cộng số thực, việc đổi ngoặc có thể đổi kết quả.

## 8. Riêng với số học nguyên: kiểu toán hạng và phép chia quan trọng không kém độ ưu tiên

### 8.1. Phép nhân, chia, chia dư cùng mức

```java
int a = 7 / 2 * 2;       // (7 / 2) * 2 = 3 * 2 = 6
int b = 7 * 2 / 2;       // (7 * 2) / 2 = 14 / 2 = 7
int c = 20 % 6 * 3;      // (20 % 6) * 3 = 2 * 3 = 6
int d = 20 % (6 * 3);    // 20 % 18 = 2
```

Cả `/`, `*` và `%` có cùng mức ưu tiên; vì thế thứ tự kết hợp trái giải thích sự khác nhau. Phép chia nguyên Java làm tròn thương về **0**: `-7 / 2 == -3`, `7 / -2 == -3`. Phần dư `a % b` thỏa `a == (a / b) * b + (a % b)` trong các trường hợp nguyên thông thường (kể cả tình huống tràn đặc biệt của `MIN_VALUE / -1` theo cách Java xác định), và phần dư có dấu cùng dấu với số bị chia khi khác 0.

### 8.2. Phép toán thực hiện theo kiểu sau numeric promotion

```java
int x = 1_500_000_000;
long wrong = x * 2;           // -1294967296L: phép nhân int tràn trước
long correct = (long) x * 2; // 3000000000L: chuyển x sang long trước
```

Đây là hiệu ứng của **kiểu toán hạng** và **thời điểm cast**, không phải độ ưu tiên đơn thuần. Trong `(long) x * 2`, `(long) x` trở thành `long` trước phép nhân, khiến phép nhân được tính bằng `long`. Gán kết quả phép nhân `int` sang biến `long` sau khi đã tràn không thể lấy lại bit đã mất.

Tương tự, `byte`, `short` và `char` thường được nâng thành `int` khi tham gia phép toán số học nhị phân:

```java
byte a = 10, b = 20;
int sum = a + b;      // int, giá trị 30
// byte bad = a + b;  // lỗi biên dịch: expression int không thể gán ngầm vào byte
```

**Ngoại lệ liên quan hằng:** compiler cho phép một số biểu thức hằng `int` gán cho `byte`/`short`/`char` nếu nằm trong miền phù hợp, ví dụ `byte p = 10 + 20;`. Điều này không biến `byte + byte` thành phép toán có kết quả `byte`.

### 8.3. Dấu âm đơn ngôi và giá trị biên

`-` đơn ngôi có độ ưu tiên cao hơn `*` và `+` nhị phân:

```java
int a = -2 * 3;      // (-2) * 3 = -6
int b = 2 * -3;      // 2 * (-3) = -6
int c = -(2 + 3);    // -5
```

Với `Integer.MIN_VALUE`, phủ định ở kiểu `int` tạo kết quả tràn:

```java
int min = Integer.MIN_VALUE;
int same = -min;                 // vẫn là Integer.MIN_VALUE
long positive = -(long) min;     // 2147483648L
```

Việc mở rộng kiểu phải diễn ra **trước phép đổi dấu** nếu muốn có kết quả toán học dương đúng. Dùng `Math.negateExact` nếu cần phát hiện tràn thay vì chấp nhận vòng bit.

## 9. Dịch bit, mask và phép so sánh

Trong nhóm số học nguyên, việc nhầm ưu tiên giữa cộng, dịch bit và so sánh rất phổ biến:

```java
int a = 1 << 3 + 1;       // 16 vì 1 << (3 + 1)
int b = (1 << 3) + 1;     // 9

int flags = 0b1010;
boolean hasBit = (flags & 0b0010) != 0; // true
```

Để kiểm tra bit bằng mask, nên luôn dùng ngoặc:

```java
if ((flags & mask) != 0) {
    // Có ít nhất một bit trong mask được bật.
}
```

`flags & mask != 0` không được nhóm như phép kiểm tra mong muốn: phép `!=` gắn chặt hơn `&` và gây lỗi kiểu `int & boolean`.

Nhớ rằng toán tử dịch bit thực hiện trên `int` hoặc `long` sau promotion. `>>` dịch phải giữ dấu, `>>>` dịch phải điền 0. Khi số lượng bit dịch là biểu thức số học, cả **ưu tiên dấu cộng** lẫn **loại của toán hạng trái** đều ảnh hưởng kết quả.

## 10. Thứ tự đánh giá trong phép gán và compound assignment

Phép gán kết hợp phải, nhưng vế trái có thể là biến, trường hoặc phần tử mảng có biểu thức truy cập cần đánh giá. Đừng gộp “đặt nhóm từ phải” với “chạy từ phải”.

Ví dụ:

```java
int[] numbers = {10, 20};
int index = 0;
numbers[index++] = 99;
// Phần tử numbers[0] thành 99, index thành 1.
```

Với **compound assignment** như `x += expression`, Java lưu giá trị hiện có của vế trái để thực hiện phép toán kết hợp trước khi ghi kết quả; đối với vế trái có chỉ mục/receiver phức tạp, chúng chỉ được đánh giá một lần theo quy tắc của phép gán kết hợp.

```java
int x = 1;
x += (x = 5);
System.out.println(x); // 6
```

Diễn giải: vế trái của `+=` đọc và giữ giá trị cũ `1`; vế phải `(x = 5)` đặt `x` thành `5` và có giá trị `5`; phép `+=` sử dụng giá trị đã giữ `1 + 5` rồi gán cuối cùng `6` cho `x`.

Phép gán kết hợp cũng chứa chuyển kiểu ngầm về kiểu của biến bên trái. Ví dụ:

```java
byte count = 127;
count += 1;          // count thành -128 do ép hẹp, không ném lỗi
// count = count + 1; // lỗi biên dịch vì count + 1 có kiểu int
```

Về khái niệm, `E1 op= E2` gần với `E1 = (T)((E1) op (E2))` trong đó `T` là kiểu của `E1`, **nhưng `E1` chỉ được đánh giá một lần**. Vì vậy không được triển khai thay bằng phép gán thường một cách máy móc nếu `E1` có tác dụng phụ hoặc là vị trí truy cập mảng/phương thức.

## 11. Khi xảy ra ngoại lệ, thứ tự đánh giá quyết định tác dụng phụ nào đã xảy ra

Phép chia nguyên cho 0 ném `ArithmeticException`. Với biểu thức:

```java
int result = numerator() / denominator();
```

Java đánh giá `numerator()` trước rồi `denominator()`. Sau đó phép chia được thực hiện; nếu mẫu số bằng 0 thì ném ngoại lệ. Nếu `numerator()` đã in log hoặc cập nhật biến, tác dụng phụ đó đã xảy ra.

Trong `left() + right()`, nếu `left()` ném ngoại lệ thì `right()` không được gọi. Cùng nguyên lý áp dụng cho các đối số hàm đánh giá từ trái sang phải. Còn trong `&&`/`||`, một vế có thể không được đánh giá vì ngắn mạch ngay cả khi không có ngoại lệ.

Khi logic chỉ có ý nghĩa nếu các bước thành công, phân chia thành các câu lệnh riêng thường làm rõ hơn những nơi có thể phát sinh ngoại lệ và những thay đổi trạng thái đã thực hiện.

## 12. Chương trình Java 17+ tự chạy và kết quả

Tạo file **`OperatorEvaluationDemo.java`**:

```java
public class OperatorEvaluationDemo {
    private static int number(String name, int value) {
        System.out.print(name + " ");
        return value;
    }

    private static boolean condition(String name, boolean value) {
        System.out.print(name + " ");
        return value;
    }

    public static void main(String[] args) {
        System.out.print("precedence: ");
        int p = number("A", 2) + number("B", 3) * number("C", 4);
        System.out.println("=> " + p);

        System.out.print("associativity: ");
        int s = number("X", 20) - number("Y", 6) - number("Z", 2);
        System.out.println("=> " + s);

        int shift = 1 << 2 + 1;
        int mask = 5 & 3;
        System.out.println("shift = " + shift);
        System.out.println("mask = " + mask);

        int i = 1;
        int value = i++ + i++ * 10;
        System.out.println("postfix value = " + value + ", i = " + i);

        int x = 1;
        x += (x = 5);
        System.out.println("compound x = " + x);

        System.out.print("short-circuit AND: ");
        boolean and = condition("left", false)
                && condition("right", true);
        System.out.println("=> " + and);

        System.out.print("short-circuit OR: ");
        boolean or = condition("left", true)
                || condition("right", false);
        System.out.println("=> " + or);

        System.out.print("conditional: ");
        int selected = condition("test", false)
                ? number("then", 10)
                : number("else", 20);
        System.out.println("=> " + selected);

        System.out.print("division: ");
        try {
            int quotient = number("numerator", 10)
                    / number("denominator", 0);
            System.out.println("=> " + quotient);
        } catch (ArithmeticException e) {
            System.out.println("=> / by zero");
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac OperatorEvaluationDemo.java
java OperatorEvaluationDemo
```

**Kết quả chuẩn:**

```text
precedence: A B C => 14
associativity: X Y Z => 12
shift = 8
mask = 1
postfix value = 21, i = 3
compound x = 6
short-circuit AND: left => false
short-circuit OR: left => true
conditional: test else => 20
division: numerator denominator => / by zero
```

Những điểm cần quan sát:

- Dù phép nhân có mức ưu tiên cao hơn phép cộng, `A` vẫn được đánh giá trước `B` và `C`. Kết quả tính toán là `2 + (3 * 4) = 14`.
- Phép trừ kết hợp trái: `(20 − 6) − 2 = 12`.
- `1 << 2 + 1` lấy số bit dịch là `3`; phép `&` trên `5` và `3` cho `1`.
- Hai lần `i++` lần lượt đọc `1` và `2`; kết quả `21` và `i` cuối cùng bằng `3`.
- `+=` giữ giá trị cũ của vế trái nên `x` cuối cùng bằng `6`.
- `right` không in ra với `&&` khi vế trái sai, và với `||` khi vế trái đúng.
- Toán tử `?:` chỉ gọi `else` khi điều kiện sai.
- Phép chia đã gọi cả `numerator` lẫn `denominator` trước khi phát hiện số chia bằng 0.

## 13. Lỗi hay gặp trong thực tế

| Nhầm lẫn | Vì sao sai và cách khắc phục |
| --- | --- |
| “`*` ưu tiên cao hơn nên hàm ở vế nhân được gọi trước” | Java đánh giá toán hạng bên trái trước; ưu tiên chỉ xác định nhóm phép toán |
| “Kết hợp trái nghĩa là mọi hàm/phép toán đều chạy ngay lập tức từ trái sang phải” | Kết hợp quyết định cây biểu thức; kết quả phép toán chỉ tính khi đủ toán hạng, trong khi việc gọi hàm có thứ tự riêng |
| “`a = b = c` chạy mọi thứ từ phải sang trái” | Đây là **cách nhóm phép gán**; việc đánh giá các biểu thức làm vế trái có quy tắc riêng |
| “`100 / 5 / 2` = `100 / (5 / 2)`” | Cách nhóm khác nhau; phép chia nguyên còn làm tròn về 0 |
| “`1 << 2 + 1` dịch 2 bit rồi cộng 1” | `+` ưu tiên hơn `<<`; thực tế dịch 3 bit |
| “`flags & mask != 0` kiểm tra mask” | `!=` ưu tiên hơn `&`; cần `(flags & mask) != 0` |
| “`&&` và `&` giống nhau với boolean” | `&&` có ngắn mạch, `&` đánh giá cả hai vế |
| “`i++ + i++` là không có thứ tự trong Java” | Java quy định thứ tự trái sang phải; vẫn nên tránh vì khó bảo trì |
| “`long x = intA * intB` tránh tràn `int`” | Tràn có thể đã xảy ra trong phép nhân trước khi gán; cast trước phép nhân |
| “Ngoặc cho phép gọi hàm bên phải trước” | Ngoặc đổi cấu trúc phép tính, không tự đảo thứ tự đánh giá các hàm |
| “`x += y` luôn tương đương `x = x + y`” | Có chuyển kiểu ngầm và bảo đảm vị trí bên trái chỉ được đánh giá một lần |
| “Thay đổi ngoặc luôn cho cùng kết quả theo toán học” | Chia nguyên, tràn số, số thực nhị phân và tác dụng phụ đều có thể làm kết quả khác |

## 14. Bài tập tự kiểm tra

Hãy tính kết quả theo Java, không dựa riêng vào trực giác về toán học.

**Bài 1.** Kết quả của `int x = 2 + 4 * 3 - 5;` là gì?

**Bài 2.** `int x = 32 / 4 / 2;` khác thế nào với `int y = 32 / (4 / 2);`?

**Bài 3.** `int x = 1 << 1 + 2;` cho số nào?

**Bài 4.** Với `int flags = 0b1100; int mask = 0b0100;`, viết điều kiện boolean để kiểm tra bit của `mask` có bật trong `flags` không.

**Bài 5.** Sau đoạn này, `result` và `i` có giá trị bao nhiêu?

```java
int i = 1;
int result = ++i + i++ * 3;
```

**Bài 6.** Vì sao hai biểu thức sau có thể cho kết quả khác nhau?

```java
int a = 7 / 2 * 2;
int b = 7 * 2 / 2;
```

**Bài 7.** `boolean ok = false && (10 / 0 > 1);` có gây ngoại lệ lúc chạy không? So với việc dùng `&` thì sao?

**Bài 8.** `int x = 1; x += (x = 4);` sẽ để `x` bằng mấy? Vì sao?

### Đáp án giải thích

1. `2 + 12 - 5 = 9`, do `*` ưu tiên hơn `+`/`-`.
2. `x = (32/4)/2 = 4`; `y = 32/(4/2) = 16`.
3. `1 << (1 + 2) = 1 << 3 = 8`.
4. `boolean enabled = (flags & mask) != 0;`, kết quả `true`.
5. `++i` trả `2` và để `i=2`; `i++` tiếp theo trả `2` rồi để `i=3`; `result = 2 + 2*3 = 8`.
6. Trong `7 / 2 * 2`, phép chia nguyên cho `3` trước rồi nhân được `6`; trong `7 * 2 / 2`, nhân trước cho `14` rồi chia cho `2` được `7`.
7. `false && ...` ngắn mạch nên không đánh giá phép chia; không ném ngoại lệ. Với `false & ...`, Java đánh giá vế phải và phép chia cho 0 ném `ArithmeticException`. *Trong bài tập, số chia bằng literal 0 nằm trong biểu thức runtime; biểu thức được biên dịch và lỗi xảy ra nếu thực sự đánh giá phép chia.*
8. `x += (x = 4)` giữ `x` ban đầu là `1` cho vế trái; vế phải gán `4`; kết quả phép cộng là `1+4=5`, nên `x` cuối cùng bằng `5`.

## 15. Checklist khi đọc hoặc viết biểu thức phức tạp

1. **Xác định kiểu** của từng toán hạng: `int`, `long`, `boolean` hay kiểu tham chiếu? Phép toán có promote, cast hẹp hoặc tràn không?
2. **Nhóm biểu thức** theo ngoặc và độ ưu tiên; khi cùng mức, xác định tính kết hợp.
3. **Đánh dấu thứ tự đánh giá toán hạng**, nhất là các lời gọi hàm, `++`/`--`, phép gán và truy cập mảng.
4. **Kiểm tra ngắn mạch** ở `&&`, `||` và nhánh của `?:`; vế nào có thể bị bỏ qua?
5. **Kiểm tra ngoại lệ** và tác dụng phụ: vế nào đã chạy trước khi một phép chia 0, truy cập sai hoặc hàm ném lỗi?
6. **Thêm ngoặc và tách câu lệnh** nếu người đọc phải nhớ nhiều quy tắc cùng lúc; ưu tiên tính rõ ràng trong code tính tiền, dữ liệu bit và điều kiện xác thực.
7. **Không áp dụng biến đổi đại số tùy tiện**: tính toán trên integer có giới hạn miền và phép chia nguyên; trên floating-point có làm tròn và các giá trị đặc biệt.

**Ghi nhớ:** **Ưu tiên** chọn phép toán gắn với toán hạng; **kết hợp** quyết định cách nhóm các toán tử cùng cấp; **thứ tự đánh giá** quyết định biểu thức con nào thực sự chạy trước. Phân biệt chính xác cả ba giúp bạn dự đoán đúng giá trị, tác dụng phụ và ngoại lệ của biểu thức Java.
