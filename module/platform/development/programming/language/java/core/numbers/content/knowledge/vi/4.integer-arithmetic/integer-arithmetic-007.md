# Dấu ngoặc và tác động tới giá trị trung gian trong số học nguyên Java

## 1. Mục tiêu và tình huống đặt vấn đề

Cùng những toán hạng, chương trình có thể trả kết quả rất khác khi thay vị trí dấu ngoặc. Với số học nguyên trong Java, điều đó xảy ra vì **dấu ngoặc quyết định cách nhóm phép toán**, còn **mỗi phép toán trung gian có kiểu dữ liệu, quy tắc chia nguyên và giới hạn biểu diễn riêng**. Một kết quả trung gian đã bị cắt phần dư hoặc tràn miền giá trị sẽ không được “khôi phục” chỉ vì kết quả cuối cùng được gán vào biến rộng hơn.

Sau bài này, bạn có thể:

- Đọc được cách Java nhóm biểu thức bằng **độ ưu tiên toán tử**, **tính kết hợp (associativity)** và dấu ngoặc `( ... )`.
- Phân biệt thứ tự **nhóm phép toán** với thứ tự **đánh giá toán hạng** từ trái sang phải.
- Dự đoán chính xác kết quả của các phép `+`, `-`, `*`, `/` và `%` khi thay dấu ngoặc.
- Nhận diện nơi **phép chia nguyên cắt phần thập phân**, nơi **`int`/`long` có thể tràn**, nơi **numeric promotion** hay **cast** thay đổi kiểu tính trung gian.
- Chọn cách đặt ngoặc, chuyển kiểu và kiểm tra overflow phù hợp với yêu cầu tính toán; tự chạy ví dụ Java 17+ và giải thích stdout.

**Phạm vi:** số học nguyên Java Core với `byte`, `short`, `int`, `long`; số thực xuất hiện khi cần đối chiếu tác động của ép kiểu. Các ví dụ dùng Java SE 17 trở lên và không cần thư viện ngoài JDK.

## 2. Ba quy tắc phải tách riêng

### 2.1. Độ ưu tiên (precedence) — toán tử nào được nhóm chặt hơn?

Với các toán tử số học thường gặp, thứ tự ưu tiên từ cao xuống thấp là:

| Mức | Cú pháp | Ý nghĩa chính |
| --- | --- | --- |
| 1 | `( ... )` | Chỉ rõ biểu thức con; ưu tiên việc tính biểu thức bên trong theo cấu trúc đã nhóm |
| 2 | `+x`, `-x`, `++x`, `x++` | Toán tử một ngôi/tăng giảm; prefix, postfix có chi tiết ưu tiên riêng |
| 3 | `*`, `/`, `%` | Nhân, chia, lấy dư |
| 4 | `+`, `-` | Cộng, trừ |

Bảng giản lược chỉ phục vụ **số học**; biểu thức Java còn có shift, so sánh, logic, điều kiện, gán và các cấu trúc khác với thứ tự ưu tiên riêng. Toán tử một ngôi không đồng nghĩa mọi dạng prefix/postfix đều có cùng mức trong bảng đầy đủ.

Ví dụ:

```java
int result = 10 + 2 * 3;      // 16: 10 + (2 * 3)
int changed = (10 + 2) * 3;   // 36: (10 + 2) * 3
```

Dấu ngoặc không phải “phép toán mới” làm biến đổi dữ liệu. Nó yêu cầu tính **biểu thức con** theo cách nhóm khác, từ đó có thể thay đổi giá trị/kiểu của kết quả trung gian.

### 2.2. Tính kết hợp (associativity) — nhóm thế nào khi cùng mức ưu tiên?

Các phép số học nhị phân `+`, `-`, `*`, `/` và `%` được nhóm **từ trái sang phải** khi không có ngoặc điều chỉnh.

```java
int x = 20 / 3 / 2;      // (20 / 3) / 2 = 6 / 2 = 3
int y = 20 / (3 / 2);    // 20 / 1 = 20
```

Hai biểu thức có cùng toán hạng theo cùng thứ tự nhưng **cấu trúc phép chia khác nhau**. Phép chia không có tính kết hợp đại số, nên dấu ngoặc đặc biệt quan trọng.

Ví dụ khác:

```java
int a = 15 - 6 - 2;      // (15 - 6) - 2 = 7
int b = 15 - (6 - 2);    // 15 - 4 = 11
```

Không nên hiểu “kết hợp trái” là Java được tùy ý đảo thứ tự phép toán trong mọi trường hợp. Đây là quy tắc **phân tích cấu trúc biểu thức**.

### 2.3. Thứ tự đánh giá (evaluation order) — toán hạng nào được thực thi trước?

Java bảo đảm các toán hạng của toán tử nhị phân được **đánh giá từ trái sang phải**, ngay cả khi toán tử bên phải có độ ưu tiên cao hơn. Ví dụ `left() + middle() * right()` được nhóm thành `left() + (middle() * right())`; khi chạy, `left()` vẫn được gọi trước `middle()` và `right()`.

Phân biệt rõ:

- **Grouping/precedence:** biểu thức con nào cung cấp kết quả cho phép toán nào.
- **Evaluation order:** thao tác, lời gọi phương thức hoặc side effect nào xảy ra trước.
- **Integer intermediate:** kết quả tại từng phép số học mang kiểu và quy tắc của chính phép đó.

Vì vậy câu “Java luôn thực thi phép nhân trước phép cộng” là cách nói thiếu chính xác nếu các toán hạng có lời gọi phương thức/side effect. Java **nhóm** phép nhân chặt hơn; đánh giá toán hạng vẫn phải tôn trọng trái sang phải.

## 3. Dấu ngoặc làm đổi kết quả phép cộng, trừ, nhân, chia

| Biểu thức | Tính từng bước | Kết quả `int` |
| --- | --- | ---: |
| `18 / 3 + 3` | `(18 / 3) + 3 = 6 + 3` | 9 |
| `18 / (3 + 3)` | `18 / 6` | 3 |
| `20 / 3 / 2` | `(20 / 3) / 2 = 6 / 2` | 3 |
| `20 / (3 / 2)` | `20 / 1` | 20 |
| `10 + 2 * 3` | `10 + (2 * 3)` | 16 |
| `(10 + 2) * 3` | `12 * 3` | 36 |
| `15 - 6 - 2` | `(15 - 6) - 2` | 7 |
| `15 - (6 - 2)` | `15 - 4` | 11 |

Dấu ngoặc hữu ích khi bạn muốn biểu thức phản ánh công thức nghiệp vụ, chẳng hạn:

- Số nhóm cần xử lý từ `items` và `groupSize`.
- Tổng trọng số chia cho tổng mẫu.
- Thứ tự áp dụng khấu trừ hay điều chỉnh số lượng.

Tuy nhiên, công thức viết giống toán học **chưa đủ** để bảo đảm kết quả: kiểu phép tính và khả năng tràn phải được phân tích độc lập.

## 4. Điều quan trọng nhất: phép chia nguyên cắt phần dư ngay tại bước trung gian

Trong Java, nếu **cả hai toán hạng của `/` là kiểu nguyên**, phép chia nguyên tạo kết quả nguyên và **bỏ phần thập phân theo hướng về 0**. Đặt ngoặc có thể làm phép chia xảy ra sớm hơn hoặc muộn hơn.

```java
int items = 7;
int groups = 2;
int quotient = items / groups;       // 3
int beforeMultiply = (items / groups) * groups; // 6
int afterMultiply = (items * groups) / groups;  // 7
```

Vì `7 / 2` đã trở thành `3`, `(7 / 2) * 2` trở thành `6`, không thể tự lấy lại phần dư `1`. Biểu thức `(7 * 2) / 2` nhận `7` trong ví dụ nhỏ này vì phép nhân xảy ra trước phép chia và không tràn. **Không** suy ra cách “nhân trước chia” luôn an toàn: tích trung gian có thể vượt miền `int`.

### 4.1. Chia cho số âm và toán tử phần dư

`-7 / 2` bằng `-3`, **không phải `-4`**; `-7 % 2` bằng `-1`. Trong Java, số dư có dấu theo số bị chia (dividend) đối với `%` số nguyên, và khi phép tính hợp lệ, `a == (a / b) * b + (a % b)` theo ngữ nghĩa số nguyên.

Ví dụ:

```java
int a = -7;
int b = 2;
System.out.println(a / b);   // -3
System.out.println(a % b);   // -1
```

Tránh áp dụng vô thức hàm floor của toán học cho phép `int / int`. Nếu bài toán muốn chia làm tròn xuống với số âm, xem `Math.floorDiv` và `Math.floorMod`; cần đối chiếu quy ước dấu và các giá trị biên. Chúng **không** đơn thuần là thêm dấu ngoặc cho phép chia nguyên.

### 4.2. Tránh phép tính trung gian khác ý định

```java
int a = 20;
int b = 3;
int c = 2;

int leftGrouped = (a / b) / c; // 3
int rightGrouped = a / (b / c); // 20
```

Trong `a / (b / c)`, hãy tính `b / c` trước: `3 / 2 = 1`. Nếu `b / c` bằng `0`, phép chia ngoài sẽ gây `ArithmeticException`, dù phép chia trái sang phải có thể hoàn toàn hợp lệ.

Nếu mẫu số phụ thuộc dữ liệu, kiểm tra nó **sau khi đã tính đúng biểu thức con**, không chỉ kiểm tra biến ban đầu khác `0`.

## 5. Dấu ngoặc không tự nâng `int` lên `long`

Đây là lỗi thường gặp nhất khi làm phép cộng hoặc nhân trên dữ liệu số nguyên lớn.

Giả sử:

```java
int a = 2_000_000_000;
int b = 1_000_000_000;

long wrong = (long) (a + b);
long correct = (long) a + b;
```

Cách diễn giải:

1. Trong `(a + b)`, cả hai toán hạng là `int`, nên phép cộng diễn ra **trong `int`**. Tổng toán học là `3_000_000_000` vượt `Integer.MAX_VALUE`; kết quả `int` bị tràn thành `-1_294_967_296`.
2. Cast `(long) (a + b)` chỉ mở rộng **giá trị đã tràn**; `wrong` vẫn là `-1_294_967_296L`.
3. Trong `(long) a + b`, toán hạng `a` đã được chuyển sang `long` **trước khi cộng**. Binary numeric promotion chuyển `b` sang `long` và phép cộng trả `3_000_000_000L`.

**Nguyên tắc:** để phép tính trung gian dùng kiểu rộng, hãy chuyển kiểu **trước phép có thể tràn**. Đặt ngoặc quanh toàn phép tính rồi cast sau đó là quá muộn.

Ví dụ tương đương cho phép nhân:

```java
int quantity = 50_000;
int unit = 50_000;
long wrong = quantity * unit;          // int multiplication overflows
long correct = (long) quantity * unit; // long multiplication
```

`wrong` nhận giá trị `-1_794_967_296` vì phép `int * int` tràn rồi mới widening sang `long`; `correct` là `2_500_000_000L`.

Nhưng `long` cũng có giới hạn: khi các toán hạng có thể vượt 64 bit, cân nhắc `BigInteger` hoặc kiểm tra tràn. Không có phép cast kỳ diệu nào khiến phép tính primitive có độ rộng vô hạn.

## 6. Bẫy: phép nhân tràn dù thương cuối cùng đáng lẽ vừa trong `int`

Công thức toán học `n(n + 1) / 2` tính tổng từ 1 đến n. Với `n = 50_000`:

- Tổng toán học bằng `1_250_025_000`, **vừa trong `int`**.
- Tích trung gian `50_000 × 50_001 = 2_500_050_000` lại **vượt `int`**.
- Tính `n * (n + 1) / 2` bằng toàn `int` làm tràn trước khi chia, cho kết quả sai.

```java
int n = 50_000;
int wrong = n * (n + 1) / 2;
long correct = (long) n * (n + 1) / 2;
```

Kết quả:

```text
wrong   = -897458648
correct = 1250025000
```

Dấu ngoặc `(n + 1)` giúp ghi công thức rõ ràng nhưng **không** tự bảo vệ phép nhân tiếp theo. Cast `(long) n` đặt trước phép nhân mới bảo vệ được bước trung gian. Với bài toán cần giữ kết quả cuối là `int` và phải báo lỗi nếu ngoài miền, bạn có thể kiểm tra bằng `Math.toIntExact(correct)` sau khi tính bằng `long`.

Đây là lý do khi review biểu thức, phải xét **miền của từng node trong cây phép toán**, thay vì chỉ xét biến đích hay giá trị cuối kỳ vọng.

## 7. Numeric promotion và phạm vi của cast

Java có quy tắc **binary numeric promotion** cho các toán tử số học nhị phân thường gặp:

- `byte`, `short` và `char` được nâng lên tối thiểu `int` khi tham gia phép toán số học nhị phân.
- Nếu có toán hạng `long` và không có kiểu chấm động thì phép tính nhận kiểu `long`; nếu chỉ có `int` trở xuống thì nhận `int`.
- Khi có toán hạng `float`/`double`, phép tính chuyển sang floating point theo quy tắc promotion tương ứng; đó là chủ đề đối chiếu, không phải giải pháp mặc định cho mọi lỗi overflow số nguyên.

### 7.1. Cùng dấu ngoặc, khác kiểu phép tính

```java
byte left = 100;
byte right = 20;
// byte sum = left + right; // lỗi biên dịch: byte + byte => int
int sum = left + right;
```

Dù `120` vừa trong `byte`, **kiểu của biểu thức `left + right` là `int`**. Nếu thật sự cần chuyển hẹp, `byte sum = (byte) (left + right);` có thể biên dịch nhưng **có thể mất dữ liệu** với đầu vào khác; không coi cast là kiểm tra an toàn.

### 7.2. Cast bên ngoài và cast bên trong khác nhau

Với `a = 7`, `b = 2`:

| Biểu thức | Phép tính trung gian | Kết quả |
| --- | --- | --- |
| `(double) (a / b)` | `a / b` là `int` bằng 3, sau đó đổi sang `double` | `3.0` |
| `(double) a / b` | Đổi `a` sang `double` trước, rồi chia | `3.5` |
| `a / (double) b` | Đổi `b` sang `double` trước, rồi chia | `3.5` |
| `(long) (a * b)` | Nhân trong `int` trước, sau đó widening | Kết quả có thể đã tràn |
| `(long) a * b` | Nhân trong `long` | Tránh tràn `int`, nhưng vẫn phải xét giới hạn `long` |

Không đổi một biểu thức từ số học nguyên sang `double` chỉ để “né” tràn khi nghiệp vụ cần **độ chính xác số nguyên tuyệt đối**. `double` không biểu diễn chính xác mọi số nguyên `long` (vùng nguyên chính xác liên tiếp chỉ đến 2⁵³). Với phép tính số nguyên lớn, dùng `long`/`BigInteger` theo yêu cầu.

## 8. Phân biệt tính kết hợp đại số và tính kết hợp trong Java

Đây là điểm dễ bị dạy sai. Phép **cộng và nhân số nguyên thuần `int` hoặc `long`** của Java, nếu cùng kiểu và không có side effect, vẫn có tính kết hợp theo kết quả modulo 2³²/2⁶⁴ kể cả khi phép tính tràn:

```java
int x = Integer.MAX_VALUE;
int y = 1;
int z = -1;

int first = (x + y) + z;
int second = x + (y + z);
// first == second == Integer.MAX_VALUE
```

Ở cách nhóm đầu, `x + y` tràn thành `Integer.MIN_VALUE` trước rồi cộng `-1`; ở cách nhóm sau, `y + z` thành `0`. Giá trị **trung gian khác nhau**, nhưng kết quả cuối `int` bằng nhau. Không nên kết luận rằng cứ đổi dấu ngoặc cộng `int` thuần là đổi kết quả cuối.

Tính kết hợp trên **không cho phép** tùy ý tái nhóm khi:

- Biểu thức có **chia/lấy dư**, vì chúng không có tính kết hợp tương tự.
- Có **kiểu trung gian khác nhau**, cast, lời gọi chuyển kiểu hoặc các phương thức có hợp đồng riêng.
- Có **side effect** như `++`, phép gán, I/O hoặc gọi phương thức quan sát được.
- Dùng API **kiểm tra tràn** (chẳng hạn `Math.addExact`) thay cho `+` thông thường: điểm phát hiện lỗi trung gian có thể khác.
- Chuyển sang **số thực**: cộng và nhân dấu phẩy động không có tính kết hợp tổng quát do rounding, overflow và NaN.

### 8.1. Ví dụ với phép cộng được kiểm tra tràn

`Math.addExact(a,b)` ném `ArithmeticException` nếu phép cộng vượt miền kiểu trả về:

```java
int x = Integer.MAX_VALUE;
int y = 1;
int z = -1;

// Math.addExact(Math.addExact(x, y), z); // throws: inner add overflows
int safeGrouping = Math.addExact(x, Math.addExact(y, z)); // MAX_VALUE
```

Hai biểu thức số học có cùng tổng toán học; tuy nhiên **hợp đồng phát hiện tràn ở mỗi bước** khác nhau. Không dùng phép cộng `+` tràn để chứng minh phép cộng checked an toàn.

Khi cần tránh báo overflow trung gian nếu chỉ quan tâm tổng cuối, hãy quyết định rõ yêu cầu nghiệp vụ: có thể cộng trong `long`/`BigInteger` rồi kiểm tra miền đích sau; hoặc yêu cầu mọi phép cộng từng bước phải an toàn bằng `addExact`. Đó là hai hợp đồng khác nhau.

## 9. Số học trung gian và thứ tự đánh giá có side effect

Dấu ngoặc thay đổi cách nhóm, nhưng Java vẫn đánh giá các toán hạng theo quy tắc của ngôn ngữ. Ví dụ runnable dưới đây cho thấy lời gọi `left()` xuất hiện trước `right()` dù phép nhân ở vế phải có độ ưu tiên cao hơn phép cộng.

Lưu thành **`EvaluationOrder.java`**:

```java
public class EvaluationOrder {
    static int left() {
        System.out.println("left");
        return 10;
    }

    static int right() {
        System.out.println("right");
        return 3;
    }

    public static void main(String[] args) {
        int result = left() + right() * 2;
        System.out.println(result);
    }
}
```

Chạy:

```bash
javac --release 17 EvaluationOrder.java
java EvaluationOrder
```

Stdout:

```text
left
right
16
```

`right() * 2` được nhóm trước khi cộng, nhưng `left()` vẫn được đánh giá đầu tiên. Java không được tự ý đảo hành vi quan sát được chỉ vì phép nhân có ưu tiên cao.

### 9.1. Tránh nhét `++` hoặc gán vào cùng biểu thức phức tạp

```java
int value = 4;
int result = value + value++;
```

Java có quy tắc xác định cho code trên: toán hạng trái đọc `4` trước, toán hạng phải `value++` trả giá trị cũ `4` và tăng biến lên `5`; `result` là `8`. Tuy vậy đây là mã **khó đọc, dễ nhầm** khi review, nhất là nếu còn lồng dấu ngoặc, phương thức và nhiều side effect.

Thay bằng các bước tường minh:

```java
int value = 4;
int original = value;
value++;
int result = original + original;
```

Ví dụ thay thế thể hiện ý định “cộng hai lần giá trị trước khi tăng”. Dấu ngoặc không thay thế việc tách side effect khỏi phép tính. Còn với các toán tử điều kiện `&&`, `||` và `?:`, Java có quy tắc đánh giá có điều kiện; không được gom chúng vào cách hiểu “luôn đánh giá mọi toán hạng”.

## 10. Ví dụ hoàn chỉnh: dấu ngoặc và mất giá trị trung gian

Lưu nội dung sau thành **`IntegerParentheses.java`**:

```java
public class IntegerParentheses {
    public static void main(String[] args) {
        System.out.println(18 / 3 + 3);
        System.out.println(18 / (3 + 3));

        System.out.println((20 / 3) / 2);
        System.out.println(20 / (3 / 2));

        int seven = 7;
        System.out.println((seven / 2) * 2);
        System.out.println((seven * 2) / 2);

        System.out.println((double) (seven / 2));
        System.out.println((double) seven / 2);

        System.out.println(-7 / 2);
        System.out.println(-7 % 2);
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac --release 17 IntegerParentheses.java
java IntegerParentheses
```

**Stdout chính xác:**

```text
9
3
3
20
6
7
3.0
3.5
-3
-1
```

Điểm cần quan sát: dấu ngoặc `(3 + 3)` thay đổi mẫu của phép chia; `20 / (3 / 2)` tính mẫu trong `int` trước; `(seven / 2) * 2` mất phần dư; cast sau chia không thể lấy lại `0.5`; với số âm, phép chia nguyên cắt về 0.

## 11. Ví dụ hoàn chỉnh: tràn trước khi gán sang kiểu lớn

Lưu thành **`IntermediateOverflow.java`**:

```java
public class IntermediateOverflow {
    public static void main(String[] args) {
        int a = 2_000_000_000;
        int b = 1_000_000_000;

        long lateCast = (long) (a + b);
        long earlyCast = (long) a + b;
        System.out.println(lateCast);
        System.out.println(earlyCast);

        int n = 50_000;
        int wrongSum = n * (n + 1) / 2;
        long correctSum = (long) n * (n + 1) / 2;
        System.out.println(wrongSum);
        System.out.println(correctSum);

        try {
            Math.addExact(a, b);
            System.out.println("no overflow");
        } catch (ArithmeticException ex) {
            System.out.println("overflow detected");
        }
    }
}
```

Chạy:

```bash
javac --release 17 IntermediateOverflow.java
java IntermediateOverflow
```

**Stdout chính xác:**

```text
-1294967296
3000000000
-897458648
1250025000
overflow detected
```

Từng dòng giải thích được bằng kiểu phép tính trung gian:

1. `a + b` tính `int` trước rồi mới cast, nhận giá trị đã tràn.
2. `(long) a + b` sử dụng phép cộng `long` từ đầu.
3. `n * (n + 1)` tính `int` và tràn trước khi chia hai.
4. `(long) n * (n + 1)` tính `long` từ phép nhân nên ra tổng toán học đúng.
5. `Math.addExact(a,b)` phát hiện phép cộng `int` vượt giới hạn và ném ngoại lệ đã được catch.

Trong mã sản xuất, khi tổng phải là `int`, có thể thực hiện phép cộng `long` rồi dùng `Math.toIntExact` để kiểm tra trước khi chuyển về `int`. Tránh dùng cast hẹp `(int)` như thể nó là phép kiểm tra.

## 12. Trường hợp biên: số nguyên nhỏ nhất, chia cho 0, cast và toán tử âm

### 12.1. Chia nguyên cho 0

`int` hoặc `long` chia cho 0 (hoặc lấy dư với 0) ném `ArithmeticException` tại lúc chạy nếu phép chia thật sự được thực hiện.

```java
int denominator = 0;
// int invalid = 10 / denominator; // runtime ArithmeticException
```

Khi mẫu là **biểu thức có ngoặc**, phải xét **giá trị mẫu sau khi tính**:

```java
int a = 10;
int b = 2;
int c = 3;
// int invalid = a / (b / c); // b / c = 0, rồi 10 / 0
```

Đừng kiểm tra riêng `b != 0` và `c != 0` rồi cho rằng `b / c != 0`.

### 12.2. Giá trị nhỏ nhất chia cho `-1`

`Integer.MIN_VALUE` là `-2_147_483_648`. Giá trị đối của nó, `2_147_483_648`, nằm ngoài miền `int`. Theo đặc tả Java, `Integer.MIN_VALUE / -1` trả về lại `Integer.MIN_VALUE` (trường hợp tràn đặc biệt), không ném ngoại lệ.

```java
int min = Integer.MIN_VALUE;
System.out.println(min / -1);         // -2147483648
System.out.println((long) min / -1);   // 2147483648
```

Nếu yêu cầu phép chia chính xác `int` phải báo overflow, kiểm tra riêng ranh giới này trước khi chia; `Math.negateExact(Integer.MIN_VALUE)` cũng ném `ArithmeticException` khi cần phủ định có kiểm tra tràn. Dấu ngoặc không tự làm biểu thức rộng hơn.

### 12.3. Cast hẹp và phép toán ghép

`int result = (int) ((long) Integer.MAX_VALUE + 1);` có thể nhận `Integer.MIN_VALUE` vì phép cast `long` xuống `int` làm mất bit cao; phép cast không đồng nghĩa phép tính an toàn.

`short` và `byte` được nâng lên `int` trong phép cộng thông thường. Phép `s += 1` có quy tắc compound assignment bao gồm chuyển kiểu ngầm, khác `s = s + 1` nếu `s` là `short`. Đây là một nguồn **mất dữ liệu trung gian** dễ bị che khuất; đừng thay dấu ngoặc để “chữa” một phép chuyển kiểu không được kiểm soát.

## 13. Khi nào đổi dấu ngoặc làm đổi kết quả, khi nào không?

| Tình huống | Đổi dấu ngoặc có thể đổi gì? | Cách xử lý |
| --- | --- | --- |
| `(a / b) / c` ↔ `a / (b / c)` | Thương, lỗi chia cho 0 | Viết công thức mong muốn và kiểm tra mẫu trung gian |
| `(a - b) - c` ↔ `a - (b - c)` | Giá trị kết quả | Kiểm tra dấu và ý nghĩa của từng phép trừ |
| `(a + b) * c` ↔ `a + (b * c)` | Công thức khác nhau, có thể tràn ở vị trí khác | Chọn nhóm theo nghiệp vụ và chọn kiểu trước từng phép |
| `(a + b) + c` ↔ `a + (b + c)`, tất cả thuần `int` | Trung gian có thể khác; kết quả `int` cuối giống nhau theo modulo 2³² | Không khẳng định ngoặc luôn đổi kết quả |
| `(long) (a + b)` ↔ `(long) a + b` | **Kiểu của phép cộng** và khả năng tràn | Cast trước phép cộng nếu cần `long` |
| `(double) (a / b)` ↔ `(double) a / b` | `int` division ↔ `double` division | Chuyển kiểu trước phép chia nếu yêu cầu phần thập phân |
| `Math.addExact(Math.addExact(a,b),c)` ↔ nhóm checked còn lại | Vị trí phát hiện overflow | Thống nhất hợp đồng kiểm tra từng bước |
| Biểu thức có `++`/phương thức | Side effect, thứ tự quan sát được | Tách biến trung gian và side effect cho dễ đọc |

Một biểu thức “tương đương đại số” trong toán học không nhất thiết tương đương về **giá trị, ngoại lệ hoặc side effect** trong Java. Ngược lại, không nên phóng đại: một số phép cộng/nhân cùng kiểu nguyên thuần vẫn có tính kết hợp ngay cả khi overflow modulo, như đã giải thích.

## 14. Kỹ thuật viết biểu thức dễ đọc và an toàn

**Bước 1: viết công thức theo nghiệp vụ.** Ví dụ: “tính tổng 1..n” tương ứng `n * (n + 1) / 2`; “chia tổng hai lượng” là `total / (left + right)` nếu đó thực sự là mẫu.

**Bước 2: vẽ sơ đồ kết quả trung gian trên giấy.** Đặt kiểu và miền lên từng phép:

```text
             /
           /   \
          *     2 (int)
        /   \
 n (int)    +
           /   \
        n(int)  1(int)

n = 50_000
n + 1   -> int = 50_001
n * ... -> int overflow
... / 2 -> int không còn là tổng toán học
```

**Bước 3: chuyển kiểu trước phép có nguy cơ vượt miền.** Ví dụ `(long) n * (n + 1) / 2`. Nếu `long` vẫn có nguy cơ tràn, `Math.multiplyExact` hay `BigInteger` có thể phù hợp hơn, tùy hợp đồng.

**Bước 4: xác định quy tắc chia nguyên.** Nếu cần số nhóm làm tròn lên, không tự động dùng `(items + size - 1) / size` với mọi dữ liệu vì phép cộng `items + size - 1` có thể tràn `int`, và dữ liệu âm có ngữ nghĩa khác. Chọn công thức được chứng minh cho miền input; có thể dùng thương/dư hoặc kiểu rộng phù hợp.

**Bước 5: tách biểu thức dài và thêm tên trung gian.** Ví dụ:

```java
int n = 50_000;
long next = (long) n + 1;
long product = (long) n * next;
long result = product / 2;
```

Cách tách này giúp debug, ghi log và gắn kiểm tra ở từng bước. Với phép tính thuần, dấu ngoặc hữu ích cho khả năng đọc; với quy tắc nghiệp vụ phức tạp, **biến trung gian có tên** thường rõ hơn việc lồng nhiều cấp ngoặc.

**Bước 6: kiểm thử boundary.** Tối thiểu gồm `0`, `1`, số âm nếu được phép, số chia bằng 0, `Integer.MIN_VALUE`/`MAX_VALUE`, số khiến trung gian tràn, và trường hợp chia có dư.

## 15. Bài tập tự luyện có đáp án

### Bài 1 — Dự đoán kết quả

Với `int a = 18, b = 3, c = 3;`, kết quả của `a / b + c` và `a / (b + c)` là gì?

**Đáp án:** `9` và `3`. Biểu thức đầu được nhóm `(a/b)+c`; biểu thức sau lấy `b+c` làm mẫu.

### Bài 2 — Đổi ngoặc ở phép chia nguyên

Với `a = 20, b = 3, c = 2`, so sánh `(a/b)/c` và `a/(b/c)`.

**Đáp án:** `3` và `20`; `20/3` thành `6`, rồi `6/2` thành `3`, trong khi `3/2` thành `1`, rồi `20/1` thành `20`.

### Bài 3 — Cast đặt muộn

Tại sao `long total = (long) (Integer.MAX_VALUE + 1);` không cho `2147483648`?

**Đáp án:** phép cộng `int` đã tràn thành `-2147483648` trước khi cast. Sửa thành `(long) Integer.MAX_VALUE + 1` hoặc dùng `Math.addExact` nếu cần báo lỗi kiểu `int`.

### Bài 4 — Kết quả cuối vừa `int` nhưng vẫn sai

Cho `int n = 50_000;`. Giải thích lỗi của `n*(n+1)/2` và sửa.

**Đáp án:** tích `2_500_050_000` tràn `int` trước khi chia. `(long)n*(n+1)/2` cho `1_250_025_000`. Nếu kết quả phải là `int`, kiểm tra bằng `Math.toIntExact`.

### Bài 5 — Phân biệt promotion và ngoặc

`byte x=100, y=20; byte z=(x+y);` có hợp lệ không?

**Đáp án:** không; `x+y` có kiểu `int`. Dấu ngoặc không đổi kiểu. Dùng `int z=x+y;` hoặc cast hẹp có kiểm soát khi yêu cầu dữ liệu là `byte`.

### Bài 6 — Trường hợp phép cộng `int` thuần

Với `x=Integer.MAX_VALUE, y=1, z=-1`, có phải `(x+y)+z` khác `x+(y+z)` không?

**Đáp án:** không; hai kết quả cuối đều `Integer.MAX_VALUE`, dù trung gian khác nhau. Điều này phù hợp tính kết hợp của phép cộng `int` modulo; không áp dụng trực tiếp cho checked addition, chia, số thực hay side effect.

### Bài 7 — Chia cho 0 ẩn trong ngoặc

`int x=10, y=2, z=3;`, vì sao `x/(y/z)` gây lỗi lúc chạy dù `y` và `z` đều khác 0?

**Đáp án:** `y/z` chia nguyên bằng `0`; phép chia ngoài trở thành `10/0` và ném `ArithmeticException`.

### Bài 8 — Thứ tự gọi phương thức

Trong `left() + right() * 2`, phương thức nào chạy trước? Phép nhân được nhóm với những toán hạng nào?

**Đáp án:** `left()` được đánh giá trước `right()`; cấu trúc biểu thức là `left() + (right() * 2)`. Phân biệt thứ tự đánh giá với cách nhóm phép toán.

## 16. Checklist và tài liệu chính thức

- [ ] Tôi đọc đúng precedence, associativity và grouping khi thấy `( ... )`.
- [ ] Tôi phân biệt thứ tự **đánh giá toán hạng** với thứ tự **thực hiện phép tính đã nhóm**.
- [ ] Tôi dự đoán đúng kết quả chia nguyên, dấu của phần dư, và phát hiện mẫu trung gian bằng 0.
- [ ] Tôi không nghĩ `long result = intA * intB` sẽ tự bảo vệ khỏi `int` overflow.
- [ ] Tôi đặt cast trước phép toán cần kiểu rộng, kiểm tra kiểu của từng kết quả trung gian.
- [ ] Tôi biết trường hợp `(a+b)+c` và `a+(b+c)` với cùng kiểu số nguyên thuần không tự nhiên khác kết quả cuối; ngược lại chia và phép checked có khác biệt.
- [ ] Tôi xử lý được số âm, `Integer.MIN_VALUE / -1` và giá trị biên.
- [ ] Tôi tách side effect ra khỏi biểu thức số học phức tạp.
- [ ] Tôi đã chạy ít nhất hai chương trình đầy đủ và thử thêm trường hợp biên.

Đọc thêm theo Java SE 17:

- [JLS §15.7 — Evaluation Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7): thứ tự đánh giá và bảo toàn ngoặc/độ ưu tiên.
- [JLS §15.8.5 — Parenthesized Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.5): biểu thức trong ngoặc và kiểu của biểu thức.
- [JLS §15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17): nhân/chia/lấy dư.
- [JLS §15.18 — Additive Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18): cộng/trừ.
- [JLS §5.6 — Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): promotion và kiểu phép tính.
- [Java SE 17 Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact`, `toIntExact`, `floorDiv`.

**Thông điệp thực hành:** dấu ngoặc chọn **cấu trúc phép tính**, nhưng độ chính xác/overflow được quyết định tại **mỗi phép trung gian**. Hãy ghi đúng công thức, kiểm tra kiểu và miền của từng bước, rồi kiểm chứng bằng dữ liệu biên.