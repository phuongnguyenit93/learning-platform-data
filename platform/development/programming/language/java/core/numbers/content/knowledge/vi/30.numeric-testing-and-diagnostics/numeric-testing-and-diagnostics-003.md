# Số âm với phép chia, lấy dư và làm tròn trong Java

## 1. Vì sao số âm là một bài kiểm thử bắt buộc?

Với số dương, nhiều cách chia và làm tròn vô tình cho kết quả giống nhau. Khi xuất hiện số âm, những khác biệt trước đó trở nên rõ ràng:

- Phép chia nguyên `/` trong Java **cắt phần lẻ về 0** (*truncate toward zero*), không làm tròn xuống âm vô cực.
- Phép dư `%` là **remainder**, không nhất thiết là modulo không âm; nếu khác 0, nó có **cùng dấu với số bị chia**.
- `Math.floorDiv` và `Math.floorMod` áp dụng phép chia theo hướng **âm vô cực**, giúp tính các chu kỳ với mẫu số dương.
- Làm tròn `UP`/`DOWN` khác `CEILING`/`FLOOR`. Với số âm, chữ “up” không luôn có nghĩa là “giá trị số học lớn hơn”.
- `Math.round` và `BigDecimal.setScale(..., HALF_UP)` **không dùng cùng quy tắc khi gặp điểm giữa âm**.

Nếu phần mềm xử lý số dư tài khoản, ngày trước mốc tham chiếu, chỉ số vòng tròn, nhiệt độ âm, tiền hoàn trả, lợi nhuận âm hoặc sai số âm, chọn nhầm phép toán có thể tạo lỗi khó thấy ở bộ test chỉ có đầu vào dương.

Bài này thuộc nhóm **Kiểm thử và chẩn đoán**: ngoài giải thích công thức, mỗi phần chỉ ra cách dựng phản ví dụ, tính kết quả kỳ vọng và kiểm chứng hành vi bằng Java 17+.

## 2. Chia nguyên trong Java: cắt phần thập phân về 0

Toán tử `/` với hai toán hạng kiểu nguyên (`int`, `long` và các kiểu được nâng lên thành `int`) cho **thương nguyên được cắt về 0**. Đối với số âm, đây không phải luôn là giá trị floor.

```java
System.out.println( 7 /  3); //  2
System.out.println(-7 /  3); // -2
System.out.println( 7 / -3); // -2
System.out.println(-7 / -3); //  2
```

Ví dụ quan trọng: phép chia thực `-7 / 3 = -2.333...`, nhưng chia nguyên Java nhận `-2`, không phải `-3`.

| Biểu thức | Thương thực | `int / int` của Java | `floor(thương thực)` |
| --- | ---: | ---: | ---: |
| `7 / 3` | khoảng 2.333 | 2 | 2 |
| `-7 / 3` | khoảng -2.333 | -2 | -3 |
| `7 / -3` | khoảng -2.333 | -2 | -3 |
| `-7 / -3` | khoảng 2.333 | 2 | 2 |

Vì toán tử có các overload theo kiểu dữ liệu, `-7 / 3` và `-7.0 / 3` cũng không tương đương:

```java
System.out.println(-7 / 3);     // -2
System.out.println(-7.0 / 3);   // -2.3333333333333335
```

Câu hỏi chẩn đoán đầu tiên là: **Các toán hạng là số nguyên hay số dấu phẩy động?** Nếu phải có thương thực, dùng kiểu hoặc phương pháp số học phù hợp và đừng vô tình chia nguyên trước khi ép kiểu.

## 3. Toán tử % là remainder, không phải modulo không âm

Với toán hạng nguyên thông thường và mẫu số khác 0, Java xác định `q = a / b` bằng cách cắt thương về 0, sau đó:

```text
r = a - q * b
a = q * b + r
```

Toán tử `a % b` trả `r`. Khi `r != 0`, dấu của `r` giống dấu của **`a` (số bị chia)**, không phải dấu của `b`.

```java
System.out.println( 7 %  3); //  1
System.out.println(-7 %  3); // -1
System.out.println( 7 % -3); //  1
System.out.println(-7 % -3); // -1
```

Kiểm tra đẳng thức với `a = -7`, `b = 3`:

```text
q = -7 / 3 = -2
r = -7 % 3 = -1
q*b + r = (-2)*3 + (-1) = -7
```

Trong nhiều tài liệu toán học, **modulo với modulus dương** lại được quy ước nằm trong `[0, m)`. Do đó `-7 mod 3` thường được viết là `2`; Java `-7 % 3` lại là `-1`. Hai phép toán phục vụ các quy ước chia khác nhau.

Điều này làm xuất hiện bug phổ biến:

```java
int size = 5;
int previous = -1;
int index = previous % size; // -1, không thể dùng làm index!
```

Nếu nghiệp vụ cần một chỉ số vòng trong `[0, size)`, không dùng `%` một cách trực tiếp khi `previous` có thể âm. Dùng `Math.floorMod(previous, size)` sau khi kiểm tra `size > 0`.

## 4. Math.floorDiv và Math.floorMod: chia làm tròn xuống

Java cung cấp `Math.floorDiv(int, int)` / `Math.floorDiv(long, long)` và `Math.floorMod(...)`. Chúng dùng **thương lấy floor** thay cho thương cắt về 0.

```java
System.out.println(Math.floorDiv(-7, 3));  // -3
System.out.println(Math.floorMod(-7, 3));  //  2
System.out.println(Math.floorDiv(7, -3));  // -3
System.out.println(Math.floorMod(7, -3));  // -2
System.out.println(Math.floorDiv(-7, -3)); //  2
System.out.println(Math.floorMod(-7, -3)); // -1
```

Các giá trị thoả hệ thức:

```text
a = floorDiv(a,b) * b + floorMod(a,b)
```

với lưu ý riêng cho trường hợp tràn số nguyên ở phép chia `MIN_VALUE / -1` sẽ được bàn ở phần 10.

| `a` | `b` | `a / b` | `a % b` | `floorDiv(a,b)` | `floorMod(a,b)` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 3 | 2 | 1 | 2 | 1 |
| -7 | 3 | -2 | -1 | -3 | 2 |
| 7 | -3 | -2 | 1 | -3 | -2 |
| -7 | -3 | 2 | -1 | 2 | -1 |
| -6 | 3 | -2 | 0 | -2 | 0 |

**Với `b > 0`, `floorMod(a,b)` luôn nằm trong `[0,b)`.** Khi `b < 0`, kết quả khác 0 có dấu của `b`, tức có thể âm. Bởi vậy, nếu cần modulo **không âm**, phải bảo đảm modulus **dương**, không chỉ thay `%` bằng `floorMod` rồi bỏ qua validation.

### Tình huống 1: chỉ số tuần hoàn

```java
int numberOfSlots = 7;
int previousSlot = Math.floorMod(-1, numberOfSlots);
System.out.println(previousSlot); // 6
```

`-1` có thể biểu thị bước lùi một vị trí trước chỉ số 0. Kết quả 6 hợp lệ trong một mảng độ dài 7.

### Tình huống 2: chia thành các khoảng thời gian

Giả sử tính offset mili giây tương đối với một mốc, âm nghĩa là thời điểm trước mốc. Với mỗi đoạn dài `1_000 ms`:

```java
long offsetMillis = -1L;
long bucket = Math.floorDiv(offsetMillis, 1_000L);
long withinBucket = Math.floorMod(offsetMillis, 1_000L);

System.out.println(bucket);       // -1
System.out.println(withinBucket); // 999
```

Đây là ví dụ về cách phân ô thời gian: offset `-1 ms` nằm ở ô thời gian `-1` và vị trí `999 ms` bên trong ô đó. Nếu dùng `/` và `%`, sẽ ra bucket 0 và vị trí -1, không theo quy ước chia thành các khoảng `[k*1000, (k+1)*1000)`.

## 5. Phân biệt bốn hướng làm tròn với số âm

`java.math.RoundingMode` định nghĩa các chính sách áp dụng cho `BigDecimal`. Những tên dễ gây hiểu nhầm nhất là:

| Mode | Quy tắc | Ví dụ làm tròn `-1.26` thành 1 chữ số sau dấu phẩy |
| --- | --- | --- |
| `DOWN` | Hướng **về 0**: bỏ chữ số lẻ vượt scale | `-1.2` |
| `UP` | Hướng **ra xa 0** nếu có phần bị bỏ khác 0 | `-1.3` |
| `CEILING` | Hướng về **dương vô cực** | `-1.2` |
| `FLOOR` | Hướng về **âm vô cực** | `-1.3` |

Với số dương `1.26`, `UP` và `CEILING` cùng thành `1.3`; `DOWN` và `FLOOR` cùng thành `1.2`. **Với số âm, hai cặp này tách ra**. Đây là lý do cần test số dương và số âm khi viết chung một hàm rounding.

```java
BigDecimal x = new BigDecimal("-1.26");
System.out.println(x.setScale(1, RoundingMode.DOWN));    // -1.2
System.out.println(x.setScale(1, RoundingMode.UP));      // -1.3
System.out.println(x.setScale(1, RoundingMode.CEILING)); // -1.2
System.out.println(x.setScale(1, RoundingMode.FLOOR));   // -1.3
```

Các đoạn mã rời về `BigDecimal` trong bài cần `import java.math.BigDecimal;` và `import java.math.RoundingMode;`; chúng minh họa lệnh trong thân phương thức. Phần 11 có lớp Java đầy đủ, biên dịch và chạy độc lập.

### Các chế độ HALF có quy tắc riêng khi đúng điểm giữa

Với `-1.25` làm tròn còn 1 chữ số sau dấu phẩy, hai kết quả gần nhất là `-1.2` và `-1.3`. Giá trị gốc nằm chính giữa:

- `HALF_UP`: khi đúng điểm giữa, chọn **xa 0** → `-1.3`.
- `HALF_DOWN`: khi đúng điểm giữa, chọn **gần 0** → `-1.2`.
- `HALF_EVEN`: khi đúng điểm giữa, chọn chữ số còn giữ ở vị trí cuối là số **chẵn** → `-1.2` (chữ số 2 chẵn).

```java
BigDecimal x = new BigDecimal("-1.25");
System.out.println(x.setScale(1, RoundingMode.HALF_UP));   // -1.3
System.out.println(x.setScale(1, RoundingMode.HALF_DOWN)); // -1.2
System.out.println(x.setScale(1, RoundingMode.HALF_EVEN)); // -1.2
```

Đừng diễn giải `HALF_UP` là “đi về dương vô cực ở điểm .5”. Trong `BigDecimal`, với số âm, `HALF_UP` ở điểm giữa **đi ra xa 0**. Nếu bài toán thuế, phí hoặc hoàn tiền có yêu cầu làm tròn, chính sách phải được mô tả bằng tên mode và ranh giới áp dụng, thay vì chỉ viết “làm tròn lên”.

## 6. Math.round, floor, ceil, rint: khác rounding của BigDecimal

`java.lang.Math` cung cấp các phép toán trên `float`/`double`:

- `Math.floor(x)`: số nguyên lớn nhất **không lớn hơn** `x`, trả về `double`.
- `Math.ceil(x)`: số nguyên nhỏ nhất **không nhỏ hơn** `x`, trả về `double`.
- `Math.round(double)`: trả về `long`, chọn giá trị nguyên gần nhất; điểm đúng giữa được làm tròn về **dương vô cực** (tương ứng quy tắc `floor(x + 0.5)` cho các đầu vào hữu hạn thông thường).
- `Math.round(float)`: tương tự, nhưng trả `int`.
- `Math.rint(x)`: trả về `double` nguyên theo nghĩa số học; ở điểm giữa chọn số nguyên **chẵn**.

Thử các giá trị âm:

```java
System.out.println(Math.floor(-1.5)); // -2.0
System.out.println(Math.ceil(-1.5));  // -1.0
System.out.println(Math.round(-1.5)); // -1
System.out.println(Math.round(-2.5)); // -2
System.out.println(Math.rint(-1.5));  // -2.0
System.out.println(Math.rint(-2.5));  // -2.0
```

Vì `Math.round(-1.5)` cho `-1`, nó **khác** `BigDecimal("-1.5").setScale(0, HALF_UP)` cho `-2`:

```java
System.out.println(Math.round(-1.5)); // -1
System.out.println(new BigDecimal("-1.5")
        .setScale(0, RoundingMode.HALF_UP)); // -2
```

Lưu ý: `Math.round` trên các giá trị `NaN` và ±`Infinity` có xử lý đặc biệt, không phải phép chuyển chính xác tùy ý; số dấu phẩy động cũng có thể chứa `-0.0`. Đừng tự xây hợp đồng cho dữ liệu nhạy cảm bằng một câu “round to nearest” thiếu giải thích điểm giữa, kiểu trả về, miền và đầu vào đặc biệt.

### Quy tắc chọn API

- Muốn **chia chỉ số/bucket** với bội số nguyên và số âm: `floorDiv`/`floorMod`.
- Muốn **làm tròn một giá trị double** tới số nguyên với quy tắc Java của `round`: `Math.round`.
- Muốn **chính sách decimal explicit** về scale và rounding: `BigDecimal.setScale(scale, mode)`.
- Muốn **định dạng đầu ra** có số chữ số sau dấu chấm: tính và làm tròn theo chính sách trước, sau đó dùng `toPlainString()` hoặc formatter theo locale.

## 7. Chia và lấy dư với BigDecimal

`BigDecimal` không dùng toán tử `/` hay `%`. Nó cung cấp các phương thức có hợp đồng riêng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `divide(divisor)` | Chia **chính xác** nếu có biểu diễn thập phân hữu hạn; nếu kết quả vô hạn như 1/3, có thể ném `ArithmeticException`. |
| `divide(divisor, scale, roundingMode)` | Chia và trả kết quả có scale yêu cầu, áp dụng mode khi cần. |
| `divideToIntegralValue(divisor)` | Lấy **phần nguyên của thương theo hướng về 0**, không phải floor với số âm. |
| `remainder(divisor)` | Lấy remainder theo thương nguyên cắt về 0; khác modulo không âm. |
| `divideAndRemainder(divisor)` | Trả về mảng gồm thương nguyên và remainder theo cùng quy ước. |

```java
BigDecimal a = new BigDecimal("-7");
BigDecimal b = new BigDecimal("3");

System.out.println(a.divideToIntegralValue(b)); // -2
System.out.println(a.remainder(b));             // -1
System.out.println(a.divide(b, 2, RoundingMode.HALF_UP)); // -2.33
```

Với `BigDecimal.divideToIntegralValue`, cách biểu diễn `scale` của thương có thể phụ thuộc đầu vào và phép toán; hãy xét trị số và hợp đồng biểu diễn riêng. Phép `remainder` với số bị chia âm có thể trả giá trị âm, bởi nó **không giống `Math.floorMod`**.

Nếu một ứng dụng thực sự yêu cầu **modulo không âm trên decimal với modulus dương**, có thể chuẩn hóa remainder:

```java
static BigDecimal positiveModulo(BigDecimal value, BigDecimal modulus) {
    if (modulus.signum() <= 0) {
        throw new IllegalArgumentException("modulus must be positive");
    }
    BigDecimal rem = value.remainder(modulus);
    return rem.signum() < 0 ? rem.add(modulus) : rem;
}
```

Đây là **phương thức minh họa**, cần đặt trong một lớp Java. Ví dụ `positiveModulo(new BigDecimal("-7.5"), new BigDecimal("3"))` cho `1.5`. Không cần `Math.floorMod` vì API đó chỉ nhận số nguyên primitive.

### Chia BigDecimal cũng có thể mất chính xác theo rounding mode

`-7 / 3` có decimal vô hạn. Phép:

```java
BigDecimal q = new BigDecimal("-7")
        .divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP);
System.out.println(q); // -2.33
```

được làm tròn hai chữ số sau dấu chấm. Đây là **làm tròn có chủ đích**, không phải đồng nghĩa với chia nguyên `-7 / 3 = -2`. Nếu không được phép bỏ chữ số, `RoundingMode.UNNECESSARY` giúp phát hiện giá trị không thể biểu diễn ở scale được yêu cầu bằng cách ném `ArithmeticException`.

Với `BigDecimal`, không sử dụng `new BigDecimal(0.1)` nếu mong chính xác decimal `0.1`; tạo từ chuỗi hoặc nguồn decimal chính xác. Dù dữ liệu gốc âm hay dương, sai số `double` đầu vào không được tự sửa nhờ một lần `setScale`.

## 8. Quy tắc làm tròn âm trong nghiệp vụ

Không có một chính sách rounding đúng cho mọi bài toán. Hãy xác định:

1. **Tọa độ/giá trị mang dấu có ý nghĩa gì?** Số dư âm, độ dịch chuyển, hoàn tiền, nợ, sai lệch hay số ngày trước mốc?
2. **Muốn chia phân đoạn theo trục số nào?** Nếu bucket `[kL, (k+1)L)`, dùng `floorDiv`; nếu loại bỏ phần lẻ của chỉ số về 0, dùng `/`.
3. **Muốn remainder giữ dấu số bị chia hay thuộc khoảng không âm?** `%` và `floorMod` không giống nhau với đầu vào âm.
4. **Rounding theo hướng nào?** Hướng về 0 (`DOWN`), xa 0 (`UP`), dương vô cực (`CEILING`), âm vô cực (`FLOOR`), hay gần nhất kèm quy tắc điểm giữa?
5. **Làm tròn ở ranh giới nào?** Từng dòng, từng giao dịch, tổng cuối hoặc chỉ lúc xuất dữ liệu?
6. **Độ chính xác nào phải được giữ?** Decimal chính xác, đo lường gần đúng hay floating-point theo chuẩn số học?

Ví dụ: giá trị hoàn tiền `-1.25` được làm tròn về một chữ số. Nếu quy định “làm tròn gần nhất, điểm giữa ra xa 0”, `HALF_UP` cho `-1.3`; nếu quy định “làm tròn gần nhất, điểm giữa lấy số chẵn”, `HALF_EVEN` cho `-1.2`. Chênh lệch `0.1` có thể mang ý nghĩa kế toán. Không diễn giải từ tên “HALF_UP” mà bỏ kiểm tra thực tế với âm.

Đối với số tiền, scale cuối và mode cần được quy định theo loại tiền, luật hoặc hợp đồng nghiệp vụ. Không tự giả định hai chữ số thập phân áp dụng được cho mọi currency. Với đo đạc, rounding hiển thị không làm giảm sai số vật lý của phép đo.

## 9. Những lỗi dễ bị che giấu bởi test chỉ có số dương

### Lỗi A — Chỉ số vòng bị âm

```java
int size = 5;
int result = -1 % size; // -1
// access array[result] có thể ném ArrayIndexOutOfBoundsException
int fixed = Math.floorMod(-1, size); // 4
```

**Test cần có:** `-1`, `-size`, `-size-1`, `0`, `size-1`, `size` và `size+1`, đồng thời validate `size > 0`.

### Lỗi B — Dùng / thay floorDiv cho thời điểm trước epoch

```java
System.out.println(-1 / 1000);                 // 0
System.out.println(Math.floorDiv(-1, 1000));   // -1
```

Nếu code phân chia thành các bucket 1000 đơn vị bắt đầu ở mốc 0, bucket của `-1` phải là `-1` chứ không phải bucket 0. Với ngày/giờ thực tế, ưu tiên `java.time` khi nghiệp vụ có múi giờ, lịch và quy tắc DST; ví dụ ở đây chỉ nói về phân đoạn số học.

### Lỗi C — Nhầm HALF_UP với Math.round

```java
System.out.println(Math.round(-1.5)); // -1
System.out.println(new BigDecimal("-1.5")
        .setScale(0, RoundingMode.HALF_UP)); // -2
```

Chúng khác nhau ở điểm giữa âm. Đọc yêu cầu thực sự thay vì tự thay API với niềm tin rằng hai lời gọi “làm tròn” tương đương.

### Lỗi D — Tái sử dụng modulus âm

```java
System.out.println(Math.floorMod(-7, 3));  //  2
System.out.println(Math.floorMod(-7, -3)); // -1
```

Nếu đích là chỉ số từ 0 đến `size - 1`, phải kiểm tra `size > 0`. Một phép `floorMod` đúng về mặt Java có thể vẫn sai về miền nghiệp vụ khi modulus âm.

### Lỗi E — Dấu âm biến mất sau làm tròn về 0

```java
BigDecimal small = new BigDecimal("-0.004");
System.out.println(small.setScale(2, RoundingMode.HALF_UP)); // 0.00
```

Đó là giá trị số học 0 theo scale 2, không phải chứng minh đầu vào đã dương. Nếu nghiệp vụ cần giữ **dấu gốc** hoặc phân biệt “âm nhưng bị làm tròn về 0”, phải lưu thông tin đó riêng; `BigDecimal` không lưu số 0 âm như một giá trị có dấu riêng. Ngược lại, `double` có `-0.0` theo IEEE 754 nên logic so sánh và serialize cần được thiết kế rõ nếu phụ thuộc dấu của zero.

## 10. Những cạnh nguy hiểm: chia 0, overflow, MIN_VALUE và floating-point

### 10.1. Phép chia nguyên cho 0

`int` và `long` chia hoặc lấy dư cho 0 đều ném `ArithmeticException` khi chạy:

```java
int zero = 0;
// System.out.println(7 / zero); // ArithmeticException: / by zero
// System.out.println(7 % zero); // ArithmeticException: / by zero
```

`Math.floorDiv` và `Math.floorMod` cũng không nhận divisor 0. Hãy validate trước khi chia, đặc biệt khi modulus là kích thước collection hoặc độ dài bucket do người dùng cung cấp.

### 10.2. Trường hợp Integer.MIN_VALUE / -1

`Integer.MIN_VALUE` là `-2147483648`. Giá trị toán học của thương khi chia `-1` là `2147483648`, vượt miền `int`. Trong Java, phép chia nguyên đặc biệt này **không ném exception**; nó trả lại `Integer.MIN_VALUE` vì overflow. `Math.floorDiv` không tự sửa được giới hạn kiểu:

```java
int min = Integer.MIN_VALUE;
System.out.println(min / -1);             // -2147483648
System.out.println(min % -1);             // 0
System.out.println(Math.floorDiv(min, -1)); // -2147483648
System.out.println(Math.floorMod(min, -1)); // 0
```

Nếu cần thương toán học chính xác, **mở rộng kiểu trước khi chia**:

```java
long exact = (long) Integer.MIN_VALUE / -1L;
System.out.println(exact); // 2147483648
```

Với `Long.MIN_VALUE / -1L`, ngay cả `long` cũng không chứa thương; cân nhắc `BigInteger` hoặc kiểm tra overflow tường minh. Đừng vô tình gọi `Math.abs(Integer.MIN_VALUE)` để làm modulus dương: giá trị trả về vẫn âm vì trị tuyệt đối toán học vượt miền `int`.

### 10.3. Floating-point / và % không giống integer

`double` chia 0 không dùng cùng quy tắc ngoại lệ như số nguyên: theo IEEE 754, `1.0 / 0.0` là dương vô cực, còn `0.0 / 0.0` là `NaN`. Phép `%` với toán hạng floating point theo quy tắc remainder kiểu Java, không phải `Math.floorMod`, và không phải toán tử `Math.IEEEremainder`:

```java
System.out.println(-7.5 % 3.0); // -1.5
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(0.0 / 0.0);  // NaN
```

Trong xử lý số học thực tế, phải nêu rõ việc cho phép `NaN`/vô cực, quy tắc chuyển về decimal, cũng như sai số nhị phân của các giá trị không biểu diễn chính xác bằng `double`. Không tạo modulo không âm cho số thực bằng cách ép `(int) (a % b)` tùy tiện: conversion làm mất phần lẻ và có thể sai hoàn toàn với miền lớn.

## 11. Ví dụ Java 17+ hoàn chỉnh với stdout xác định

Lưu chương trình sau vào **`NegativeArithmeticDemo.java`**. Nó không phụ thuộc locale và chỉ in các kết quả dự đoán được.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class NegativeArithmeticDemo {

    static BigDecimal positiveModulo(BigDecimal value,
                                     BigDecimal modulus) {
        if (modulus.signum() <= 0) {
            throw new IllegalArgumentException("modulus must be > 0");
        }
        BigDecimal rem = value.remainder(modulus);
        return rem.signum() < 0 ? rem.add(modulus) : rem;
    }

    public static void main(String[] args) {
        System.out.println("-7 / 3 = " + (-7 / 3));
        System.out.println("-7 % 3 = " + (-7 % 3));
        System.out.println("7 / -3 = " + (7 / -3));
        System.out.println("7 % -3 = " + (7 % -3));
        System.out.println("-7 / -3 = " + (-7 / -3));
        System.out.println("-7 % -3 = " + (-7 % -3));

        System.out.println("floorDiv(-7, 3) = "
                + Math.floorDiv(-7, 3));
        System.out.println("floorMod(-7, 3) = "
                + Math.floorMod(-7, 3));
        System.out.println("floorDiv(7, -3) = "
                + Math.floorDiv(7, -3));
        System.out.println("floorMod(7, -3) = "
                + Math.floorMod(7, -3));
        System.out.println("ring previous = "
                + Math.floorMod(-1, 5));

        System.out.println("round(-1.5) = " + Math.round(-1.5));
        System.out.println("round(-2.5) = " + Math.round(-2.5));
        System.out.println("floor(-1.5) = " + Math.floor(-1.5));
        System.out.println("ceil(-1.5) = " + Math.ceil(-1.5));
        System.out.println("rint(-1.5) = " + Math.rint(-1.5));

        BigDecimal negative = new BigDecimal("-1.25");
        System.out.println("HALF_UP = "
                + negative.setScale(1, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN = "
                + negative.setScale(1, RoundingMode.HALF_EVEN));
        System.out.println("DOWN = "
                + negative.setScale(1, RoundingMode.DOWN));
        System.out.println("UP = "
                + negative.setScale(1, RoundingMode.UP));
        System.out.println("FLOOR = "
                + negative.setScale(1, RoundingMode.FLOOR));
        System.out.println("CEILING = "
                + negative.setScale(1, RoundingMode.CEILING));

        BigDecimal a = new BigDecimal("-7");
        BigDecimal b = new BigDecimal("3");
        System.out.println("decimal quotient = "
                + a.divideToIntegralValue(b));
        System.out.println("decimal remainder = " + a.remainder(b));
        System.out.println("decimal division = "
                + a.divide(b, 2, RoundingMode.HALF_UP));
        System.out.println("positive decimal modulo = "
                + positiveModulo(new BigDecimal("-7.5"), b));

        System.out.println("MIN / -1 = "
                + (Integer.MIN_VALUE / -1));
        System.out.println("wide MIN / -1 = "
                + ((long) Integer.MIN_VALUE / -1L));
    }
}
```

Chạy bằng JDK 17 trở lên, trong thư mục chứa file:

```bash
javac NegativeArithmeticDemo.java
java NegativeArithmeticDemo
```

Đầu ra kỳ vọng:

```text
-7 / 3 = -2
-7 % 3 = -1
7 / -3 = -2
7 % -3 = 1
-7 / -3 = 2
-7 % -3 = -1
floorDiv(-7, 3) = -3
floorMod(-7, 3) = 2
floorDiv(7, -3) = -3
floorMod(7, -3) = -2
ring previous = 4
round(-1.5) = -1
round(-2.5) = -2
floor(-1.5) = -2.0
ceil(-1.5) = -1.0
rint(-1.5) = -2.0
HALF_UP = -1.3
HALF_EVEN = -1.2
DOWN = -1.2
UP = -1.3
FLOOR = -1.3
CEILING = -1.2
decimal quotient = -2
decimal remainder = -1
decimal division = -2.33
positive decimal modulo = 1.5
MIN / -1 = -2147483648
wide MIN / -1 = 2147483648
```

Cần quan sát bốn nhóm kết quả:

1. `/` và `%` theo quy tắc **truncation toward zero**, nên `-7 / 3 = -2` và `-7 % 3 = -1`.
2. `floorDiv` và `floorMod` cùng dùng thương floor, nên `-7` chia theo ô kích thước 3 thành thương `-3` và phần dư `2`.
3. `Math.round(-1.5)` trả `-1` còn `HALF_UP` decimal ở điểm giữa âm làm tròn ra xa 0 thành `-2` nếu scale 0; chương trình thể hiện sự khác biệt tương ứng ở scale 1 cho `-1.25`.
4. `Integer.MIN_VALUE / -1` không ném exception dù thương toán học vượt kiểu `int`; nới rộng kiểu trước khi chia để nhận thương chính xác.

## 12. Viết test chẩn đoán theo bất biến thay vì kiểm tra vài ví dụ

Ngoài test đầu ra cố định, có thể viết các kiểm tra **bất biến** cho hàng loạt cặp số:

- Với `b != 0` và tránh trường hợp overflow phép chia đặc biệt, `a == (a / b) * b + (a % b)`.
- Với `b > 0`, `Math.floorMod(a, b)` luôn thỏa `0 <= r < b`.
- Với `b > 0` và `a < 0` không chia hết `b`, thương floor nhỏ hơn thương trunc đúng 1.
- Với `BigDecimal`, kiểm tra `divideToIntegralValue` và `remainder` tái tạo đúng `a` về **trị số**, dùng `compareTo() == 0` thay vì `equals()` nếu scale có thể khác.
- Với `RoundingMode`, so sánh âm và dương tại các điểm `±1.25`, `±1.26`, và quanh 0.

Một bộ test không cần thư viện ngoài, chạy độc lập dưới tên **`SignedDivisionChecks.java`**:

```java
public class SignedDivisionChecks {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        int cases = 0;
        for (int a = -20; a <= 20; a++) {
            for (int b = -7; b <= 7; b++) {
                if (b == 0) {
                    continue;
                }

                int quotient = a / b;
                int remainder = a % b;
                int floorQuotient = Math.floorDiv(a, b);
                int floorRemainder = Math.floorMod(a, b);

                check(a == quotient * b + remainder,
                        "Truncating identity failed");
                check(a == floorQuotient * b + floorRemainder,
                        "Floor identity failed");
                check(remainder == 0 ||
                        Integer.signum(remainder) == Integer.signum(a),
                        "Remainder sign failed");
                check(floorRemainder == 0 ||
                        Integer.signum(floorRemainder) == Integer.signum(b),
                        "Floor remainder sign failed");

                if (b > 0) {
                    check(floorRemainder >= 0 && floorRemainder < b,
                            "Nonnegative modulo range failed");
                }
                cases++;
            }
        }
        System.out.println("checked cases = " + cases);
        System.out.println("all properties passed");
    }
}
```

Chạy:

```bash
javac SignedDivisionChecks.java
java SignedDivisionChecks
```

Đầu ra:

```text
checked cases = 574
all properties passed
```

Tại đây có 41 giá trị `a` từ `-20` đến `20` và 14 giá trị `b` khác 0 từ `-7` đến `7`: `41 × 14 = 574` cặp. Miền nhỏ tránh tràn ở tích `quotient * b`; nếu viết property test trên toàn miền `int`, phải xử lý riêng `Integer.MIN_VALUE / -1` và overflow của phép tính kiểm tra, ví dụ bằng `long` hoặc `BigInteger`.

Test này không thay cho kiểm thử theo đặc tả nghiệp vụ. Nó chỉ kiểm tra các quy tắc số học mà chương trình dựa vào.

## 13. Ma trận test tối thiểu cho số âm

Một bộ test tốt phải cắt theo **dấu của số bị chia**, **dấu của mẫu số**, **chia hết hay không**, **điểm đúng giữa khi làm tròn** và **giá trị biên**:

| Nhóm | Đầu vào gợi ý | Mục tiêu |
| --- | --- | --- |
| Chia số dương | `7 / 3`, `7 % 3` | Mốc so sánh cơ bản. |
| Số bị chia âm | `-7 / 3`, `-7 % 3` | Phân biệt trunc và floor, remainder âm. |
| Mẫu số âm | `7 / -3`, `7 % -3` | Kiểm tra dấu quotient và remainder. |
| Cả hai âm | `-7 / -3`, `-7 % -3` | Không mặc định remainder cùng dấu divisor. |
| Chia hết | `-6 / 3`, `-6 % 3` | Remainder bằng 0. |
| Sát 0 | `-1 / 3`, `-1 % 3` | Phát hiện bucket sai gần mốc. |
| Modulo tuần hoàn | `-1`, `-5`, `-6` với modulus 5 | Giữ index trong `[0, 5)`. |
| Modulus âm | `floorMod(-7, -3)` | Không tự cho rằng modulo luôn không âm. |
| Số âm ở điểm giữa | `-1.25` về scale 1, `-1.5` về số nguyên | Phân biệt HALF_UP, HALF_EVEN, Math.round. |
| Phần lẻ nhỏ âm | `-0.004` về scale 2 | Rounding thành zero và chuyện lưu dấu gốc. |
| Mẫu số bằng 0 | `7 / 0`, `floorMod(7,0)` | Xử lý lỗi một cách có chủ đích. |
| Overflow chia nguyên | `Integer.MIN_VALUE / -1` | Phát hiện thương toán học vượt miền. |
| Decimal không kết thúc | `-7 / 3` trong BigDecimal | Chọn scale và rounding mode rõ. |
| Floating point đặc biệt | `-0.0`, `NaN`, ±`Infinity` | Xác định chính sách dữ liệu đầu vào/đầu ra. |

### Lộ trình chẩn đoán bug ngoài thực tế

Khi log cho thấy một kết quả âm “không đúng ý”:

1. **Ghi lại kiểu số** của mọi toán hạng: `int`, `long`, `double`, `BigDecimal`?
2. **Ghi lại quy tắc thương** kỳ vọng: trunc về 0 hay floor về âm vô cực?
3. **Ghi lại ràng buộc remainder** kỳ vọng: có được âm không, modulus có luôn dương không?
4. **Ghi lại chính sách rounding**: scale, mode và thời điểm áp dụng.
5. **Tái hiện bằng ca nhỏ nhất**: `-7 / 3`, `-1 % 5`, `-1.25`.
6. **Kiểm tra giá trị biên**: chia 0, overflow, số 0 âm, độ chính xác decimal/floating point.
7. **Bổ sung regression test** từ ca đã tái hiện để thay đổi code về sau không tái gây lỗi.

Nếu thay một phép `%` bằng `floorMod`, phải kiểm thử cả dữ liệu dương cũ, dữ liệu âm mới và mọi đường dẫn mà modulus bằng 0 hoặc âm. Nếu thay `Math.round` bằng `BigDecimal.setScale`, phải kiểm thử chính sách điểm giữa và conversion trước khi coi đó là một refactor “không đổi hành vi”.

## 14. Các nhầm lẫn thường gặp

1. **“`-7 / 3` là `-3`.”** Sai đối với chia `int` Java; kết quả là `-2`. `Math.floorDiv(-7,3)` mới là `-3`.
2. **“`a % b` luôn không âm.”** Sai khi `a` âm. `-7 % 3 == -1`.
3. **“`Math.floorMod` luôn dương.”** Không đúng khi divisor âm; `floorMod(7,-3) == -2`.
4. **“`Math.round` tương đương `HALF_UP`.”** Không ở điểm giữa âm; `round(-1.5) == -1` trong khi `HALF_UP` decimal về số nguyên là `-2`.
5. **“`UP` nghĩa là càng lớn trên trục số.”** Không. `RoundingMode.UP` là **xa 0**; với âm nó có thể làm số **âm hơn**.
6. **“`DOWN` nghĩa là âm vô cực.”** Không. `DOWN` là **về 0**; `FLOOR` mới về âm vô cực.
7. **“BigDecimal.remainder là modulo không âm.”** Sai; với dividend âm, remainder có thể âm.
8. **“Phép chia nguyên luôn phát hiện overflow.”** Sai ở `MIN_VALUE / -1`.
9. **“Mọi phép chia cho 0 trong Java đều ném ngoại lệ.”** Sai với `double`/`float` trong các trường hợp IEEE 754 như `1.0/0.0`.
10. **“Có thể dùng `Math.abs(size)` để đảm bảo modulus dương.”** Nguy hiểm với `Integer.MIN_VALUE`/`Long.MIN_VALUE`; phải validate miền và xử lý ngoại lệ biên.
11. **“Một vài test số dương chứng minh modulo hoạt động đúng.”** Không. Các test số âm mới thường bộc lộ khác biệt trunc và floor.
12. **“Scale và rounding mode chỉ ảnh hưởng hiển thị.”** Không. Nếu áp dụng chúng vào giá trị trung gian của công thức, kết quả cuối có thể thay đổi.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Java trả gì cho `-8 / 3` và `-8 % 3`?

**Đáp án:** `-2` và `-2` vì thương nguyên bị cắt về 0: `-8 = (-2)*3 + (-2)`.

**Câu 2.** `Math.floorDiv(-8, 3)` và `Math.floorMod(-8, 3)` là gì?

**Đáp án:** `-3` và `1` vì `-8 = (-3)*3 + 1`.

**Câu 3.** Khi modulus là `5`, vì sao index `-1 % 5` sai cho mảng?

**Đáp án:** Nó là `-1`. `Math.floorMod(-1,5)` cho `4`, một index trong `[0,5)`.

**Câu 4.** `Math.floorMod(8, -3)` có phải số không âm không?

**Đáp án:** Không; kết quả `-1` do floor quotient `-3` và `8 = (-3)*(-3) + (-1)`. Với modulus âm, floor remainder có thể âm.

**Câu 5.** Cho `BigDecimal("-1.25")`, làm tròn còn một chữ số với `HALF_UP` và `HALF_EVEN` được bao nhiêu?

**Đáp án:** `-1.3` và `-1.2`.

**Câu 6.** Vì sao `Math.round(-2.5)` là `-2`?

**Đáp án:** `Math.round` chọn điểm giữa về phía dương vô cực; giữa `-3` và `-2` nó chọn `-2`.

**Câu 7.** `Math.floor(-1.2)` và `BigDecimal("-1.2").setScale(0, DOWN)` là gì?

**Đáp án:** `Math.floor(-1.2) == -2.0`, còn `DOWN` về 0 cho `-1`.

**Câu 8.** Với `BigDecimal("-7")` chia `BigDecimal("3")`, `divideToIntegralValue` và `remainder` là gì?

**Đáp án:** Trị số `-2` và `-1`. Chúng dùng quotient cắt về 0, không phải quotient floor.

**Câu 9.** Tại sao `Integer.MIN_VALUE / -1` nguy hiểm dù divisor khác 0?

**Đáp án:** Thương toán học `2147483648` không nằm trong miền `int`; phép chia Java trả lại `Integer.MIN_VALUE` do overflow. Hãy nới kiểu trước khi chia hoặc kiểm tra rõ.

**Câu 10.** Muốn test hàm làm tròn dùng cho số âm, những nhóm ca nào bắt buộc có?

**Đáp án:** Dương/âm, gần 0, đúng midpoint và sát hai phía midpoint, nhiều rounding mode, giá trị quá lớn/quá nhỏ, và thứ tự làm tròn trong pipeline.

## 16. Tham khảo API Java 17

- [Java Language Specification `15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17): quy tắc `/`, `%` của kiểu nguyên và floating-point, chia 0 và overflow.
- [Java SE 17 — Math.floorDiv, floorMod, round](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): phép chia theo floor, modulo, rounding và hành vi biên.
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): định nghĩa `UP`, `DOWN`, `CEILING`, `FLOOR` và các chế độ `HALF_*`.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `divide`, `divideToIntegralValue`, `remainder`, `setScale` và `MathContext`.

**Ghi nhớ:** Với số âm, trước hết phải chọn **ngữ nghĩa thương** (trunc hay floor), rồi chọn **quy ước phần dư** (`%` hay `floorMod` với modulus dương), sau đó mới chọn **quy tắc làm tròn** cho thập phân. Đừng coi `Math.round`, `RoundingMode.HALF_UP`, `Math.floorDiv` và `BigDecimal.remainder` là các cách viết thay thế cho nhau. Các phản ví dụ nhỏ như `-7 / 3`, `-1 % 5` và `-1.25` sẽ bắt được đa số sai lầm từ rất sớm.
