# Nâng kiểu toán hạng trước phép nhân thay vì ép kiểu sau trong Java

Một lỗi phổ biến khi xử lý số nguyên Java là tính tích của hai giá trị `int`, rồi **gán kết quả cho `long`** với kỳ vọng Java sẽ tự giữ toàn bộ kết quả:

```java
int quantity = 50_000;
int unit = 50_000;
long total = quantity * unit;       // Sai về giá trị: -1794967296
```

Tích toán học là **2.500.000.000**, lớn hơn `Integer.MAX_VALUE` (2.147.483.647) nhưng vẫn nằm trong miền `long`. Tuy nhiên, **kiểu của biểu thức nhân được quyết định từ các toán hạng trước khi phép nhân diễn ra**. Cả hai toán hạng đều là `int` nên Java nhân bằng `int`, bị tràn, rồi mới mở rộng *kết quả sai* sang `long`.

Giải pháp là **nâng ít nhất một toán hạng lên `long` trước phép nhân**:

```java
long correct = (long) quantity * unit; // 2500000000
```

Sự khác biệt không nằm ở việc biến `total` có rộng hay không, mà ở **thời điểm chuyển kiểu** so với **thời điểm phép nhân được thực hiện**.

## 1. Java quyết định kiểu của phép nhân như thế nào?

Với biểu thức số học `a * b`, Java áp dụng **binary numeric promotion**:

| Kiểu hai toán hạng | Kiểu tính toán/kết quả của `*` | Ví dụ |
| --- | --- | --- |
| `byte` và `byte` | `int` | `byte` được nâng lên `int` |
| `short` và `short` | `int` | `short` được nâng lên `int` |
| `byte` và `int` | `int` | Ít nhất là `int` |
| `int` và `int` | `int` | Có thể tràn khi tích vượt miền `int` |
| `int` và `long` | `long` | Toán hạng `int` được nâng thành `long` |
| `long` và `long` | `long` | Vẫn có thể tràn nếu tích vượt miền `long` |
| Có toán hạng `float` hoặc `double` | Theo quy tắc nâng kiểu số thực | Phạm vi lớn hơn có thể kèm mất độ chính xác |

Bài này tập trung vào phép nhân **số nguyên có dấu**. Độ rộng của các kiểu liên quan là `byte` 8 bit, `short` 16 bit, `int` 32 bit và `long` 64 bit; các phép `byte * byte` và `short * short` được tính ít nhất theo `int`.

Kết quả toán học của `int * int` có thể cần tới 64 bit để biểu diễn đầy đủ. Java **không tự nâng `int * int` lên `long` chỉ vì kết quả quá lớn**. Với các toán tử số nguyên nguyên thủy thông thường, phép nhân tràn **không tự ném ngoại lệ**: bit cao vượt khỏi độ rộng bị bỏ và mẫu bit còn lại được diễn giải theo số có dấu.

Ví dụ:

- `50_000 * 50_000` bằng **2.500.000.000** về mặt toán học.
- Giá trị đó vượt `Integer.MAX_VALUE` nên phép nhân `int` tạo ra **-1.794.967.296** theo bề rộng 32 bit.
- `long total = ...` chỉ chuyển **-1.794.967.296** sang `long`. Các bit đã mất không thể phục hồi sau phép nhân.

Ở mức bit, kết quả phép nhân `int` về cơ bản giữ phần thấp 32 bit của tích; còn phép nhân `long` giữ phần thấp 64 bit. Hai hành vi đều cần được xem xét nếu bài toán phải tính chính xác.

## 2. So sánh trực tiếp ba cách viết

```java
int a = 50_000;
int b = 50_000;

long wrong1 = a * b;           // -1794967296: nhân int rồi gán long
long wrong2 = (long) (a * b);  // -1794967296: ép kiểu sau khi nhân int
long right1 = (long) a * b;    // 2500000000: a thành long trước khi nhân
long right2 = a * (long) b;    // 2500000000: b thành long trước khi nhân
long right3 = 1L * a * b;      // 2500000000: 1L khiến phép nhân đầu tiên là long
```

**Vì sao cách viết thứ hai vẫn sai?** Phép `(long) (a * b)` bắt Java tính toàn bộ biểu thức trong ngoặc `a * b` thành `int` trước, sau đó mới cast sang `long`. Cast mở rộng **giữ nguyên giá trị `int` bị tràn**, không tính lại phép nhân. Với `(long) a * b`, cast áp dụng cho `a` trước, nên `long * int` được tính theo `long`.

Có thể hình dung trình tự:

```text
Sai:  (long) (a * b)
       a:int × b:int  → tích:int đã tràn → cast long → giá trị sai dưới dạng long

Đúng: (long) a * b
       a:int → cast long  → a:long × b:int → tích:long (nếu vừa miền long)
```

Một quy tắc thực hành dễ nhớ: **muốn kết quả phép nhân nguyên được tính theo `long`, hãy đảm bảo kiểu `long` đã xuất hiện ở toán hạng của phép nhân cần bảo vệ**.

## 3. Toán tử `*` kết hợp trái: nâng kiểu phải đủ sớm

Với chuỗi phép nhân, `*` có tính kết hợp từ trái sang phải. Một toán hạng `long` xuất hiện **quá muộn** không cứu được phép nhân `int` đã diễn ra.

```java
int a = 50_000;
int b = 50_000;

long late = a * b * 1L;      // -1794967296
long early = a * 1L * b;     // 2500000000
long grouped = a * (b * 1L); // 2500000000
```

Vì `a * b * 1L` được nhóm như `(a * b) * 1L`, tích `a * b` bị tràn `int` **trước** khi toán hạng `1L` có mặt. Ngược lại, trong `a * 1L * b`, phép nhân đầu tiên đã thuộc `long`; kết quả trung gian `long` tiếp tục tham gia phép nhân tiếp theo.

Với ba hoặc nhiều toán hạng `int`:

```java
int x = 20_000, y = 20_000, z = 20;
long unsafe = x * y * z;        // Phép nhân thứ hai có thể tràn int
long safer = (long) x * y * z; // Mọi phép nhân trong chuỗi tính theo long
```

Từ “safer” ở đây chỉ có nghĩa **tránh tràn trung gian kiểu `int`**. Nếu tích cuối hoặc một tích trung gian vượt `Long.MAX_VALUE`/`Long.MIN_VALUE`, `long` cũng sẽ tràn. Cần kiểm tra miền dữ liệu thực tế.

Không chỉ phép nhân: `long answer = (long) (x * y + z);` cũng **cast sau toàn bộ biểu thức `int`**. Nếu `x * y` đã tràn, chuyển sang `long` không sửa được. Hãy đưa toán hạng sang `long` trước bước tính có nguy cơ tràn, chẳng hạn `long answer = (long) x * y + z;`.

## 4. Phép nhân trong lời gọi và giá trị trả về

Quy tắc nâng kiểu áp dụng cả trong đối số và giá trị trả về: chữ ký nhận/trả `long` không tự đổi phép nhân `int * int` thành `long`. Chẳng hạn, `static long wrongTotal(int a, int b) { return a * b; }` vẫn có thể trả tích đã tràn, còn `return (long) a * b;` tính tích trong `long` trước khi trả.

Vì vậy, hãy kiểm tra vị trí cast ngay tại **biểu thức nhân đầu tiên** trong lời gọi, chuỗi toán tử hoặc câu lệnh `return`, thay vì suy luận từ kiểu biến/parameter ở bên ngoài.

## 5. Những cách tạo phép nhân `long` đúng

Chọn một trong các cách sau tùy mục đích diễn đạt:

| Cách viết | Kiểu phép nhân | Khi dùng |
| --- | --- | --- |
| `(long) a * b` | `long` | Dễ đọc, thể hiện rõ việc nâng `a` trước phép nhân |
| `a * (long) b` | `long` | Tương đương, nâng `b` trước |
| `1L * a * b` | `long` từ đầu chuỗi | Có thể tiện khi nhiều toán hạng `int`, nhưng cast tường minh thường rõ hơn |
| `a * b * 1L` | Phép `a * b` đầu tiên là `int` | **Không an toàn** nếu `a * b` có thể tràn |
| `(long) (a * b)` | `int` rồi mới mở rộng | **Không sửa được** tích `int` đã tràn |
| `Math.multiplyFull(a, b)`, với hai `int` | Kết quả `long` chính xác | Không cần cast; Java 9+ |
| `Math.multiplyExact((long) a, b)` | `long`, phát hiện tràn | Tích được tính theo `long` với kiểm tra giới hạn |

Nếu có dữ liệu nguồn `long`, chỉ cần phép nhân `long * long` là chưa đủ để cam kết kết quả chính xác khi tích lớn. Dùng `Math.multiplyExact(long, long)` để phát hiện tràn hoặc `BigInteger` khi cần vượt 64 bit.

Không nên đổi tùy tiện sang `double` chỉ vì `double` biểu diễn được số rất lớn. `double` có 53 bit phần trị hiệu dụng, nên nhiều số nguyên lớn (và nhiều phép nhân) có thể bị làm tròn. Với bài toán đếm, tiền ở đơn vị nguyên nhỏ nhất hoặc mã số nguyên, cần kiểm soát độ chính xác số nguyên.

## 6. Dùng `Math.multiplyExact`, `Math.multiplyFull` và `BigInteger`

### `Math.multiplyExact`: phát hiện tràn số

`Math.multiplyExact(int, int)` trả `int` nếu tích vừa miền `int`; nếu không, ném `ArithmeticException`. `Math.multiplyExact(long, long)` trả `long` nếu tích vừa miền `long`; nếu không, cũng ném `ArithmeticException`.

```java
int a = 50_000, b = 50_000;

// Math.multiplyExact(a, b) sẽ ném ArithmeticException do tích vượt int.
long result = Math.multiplyExact((long) a, b); // 2500000000
```

Ở đây, việc cast **trước lời gọi** khiến overload có toán hạng `long` được chọn. Nếu viết `long result = Math.multiplyExact(a, b);`, overload `int,int` vẫn được chọn và sẽ ném khi tích vượt `int`. Kiểu biến nhận kết quả không thay đổi overload được chọn từ các đối số.

Cẩn thận với biểu thức truyền vào:

```java
int a = 50_000, b = 50_000;
long c = 2;

// Sai mục tiêu: a * b đã tràn trước khi phương thức được gọi.
long wrong = Math.multiplyExact(a * b, c);

// Đúng về thời điểm tính: a được mở rộng trước phép nhân.
// Math.multiplyExact còn kiểm tra tích kiểu long có vượt miền hay không.
long right = Math.multiplyExact(Math.multiplyExact((long) a, b), c);
```

`Math.multiplyExact` **không thể phát hiện một phép toán đã tràn trước lúc dữ liệu đến tay nó**.

### `Math.multiplyFull`: nhận tích chính xác của hai `int`

Vì tích của **hai giá trị `int` có dấu** luôn nằm trong phạm vi `long` (kể cả `Integer.MIN_VALUE * Integer.MIN_VALUE`), Java cung cấp `Math.multiplyFull(int, int)`, trả về **`long`** là tích chính xác.

```java
int a = 50_000, b = 50_000;
long exact = Math.multiplyFull(a, b); // 2500000000
```

Đây là API hữu ích khi rõ ràng hai toán hạng thuộc `int` và mong kết quả 64 bit. Với nhiều thừa số `int`, phải xét từng bước hoặc dùng chiến lược kiểm tra giới hạn tiếp theo.

### `BigInteger`: khi `long` cũng không đủ

Ví dụ `3_100_000_000L * 3_100_000_000L` có tích toán học **9.610.000.000.000.000.000**, vượt `Long.MAX_VALUE`. Ép kiểu `(long)` không giúp gì vì hai toán hạng đã là `long`.

```java
import java.math.BigInteger;

// Mã minh họa trong phương thức:
long a = 3_100_000_000L;
long b = 3_100_000_000L;

BigInteger exact = BigInteger.valueOf(a).multiply(BigInteger.valueOf(b));
// 9610000000000000000
```

`BigInteger` tính số nguyên có độ lớn tùy ý trong giới hạn tài nguyên. Chuyển đầu vào bằng `BigInteger.valueOf(...)` **trước phép nhân**; đừng dùng `BigInteger.valueOf(a * b)` nếu `a * b` có thể đã tràn `long`.

## 7. Chương trình Java 17+ kiểm chứng cả phép nhân sai và đúng

Tạo tệp `MultiplyPromotionDemo.java`:

```java
public class MultiplyPromotionDemo {
    public static void main(String[] args) {
        int a = 50_000;
        int b = 50_000;

        System.out.println("int product: " + (a * b));
        System.out.println("cast after: " + ((long) (a * b)));
        System.out.println("cast before: " + ((long) a * b));
        System.out.println("long operand: " + (1L * a * b));
        System.out.println("cast late in chain: " + (a * b * 1L));
        System.out.println("cast early in chain: " + (a * 1L * b));

        try {
            Math.multiplyExact(a, b);
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact int: overflow");
        }

        System.out.println("multiplyExact long: " + Math.multiplyExact((long) a, b));
        System.out.println("multiplyFull: " + Math.multiplyFull(a, b));

        long large = 3_100_000_000L;
        System.out.println("long product overflow: " + (large * large));
        try {
            Math.multiplyExact(large, large);
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact long: overflow");
        }

        System.out.println("BigInteger product: "
            + java.math.BigInteger.valueOf(large)
                .multiply(java.math.BigInteger.valueOf(large)));
    }
}
```

Biên dịch/chạy:

```bash
javac MultiplyPromotionDemo.java
java MultiplyPromotionDemo
```

Kết quả stdout:

```text
int product: -1794967296
cast after: -1794967296
cast before: 2500000000
long operand: 2500000000
cast late in chain: -1794967296
cast early in chain: 2500000000
multiplyExact int: overflow
multiplyExact long: 2500000000
multiplyFull: 2500000000
long product overflow: -8836744073709551616
multiplyExact long: overflow
BigInteger product: 9610000000000000000
```

Chương trình chứng minh ba điều:

1. **Cast sau phép nhân chỉ mở rộng giá trị đã tràn:** hai dòng đầu và `cast late in chain` cùng in `-1794967296`.
2. **Nâng kiểu trước phép nhân giải quyết overflow trung gian `int` khi tích vừa `long`:** `cast before`, `long operand` và `cast early in chain` đều in `2500000000`.
3. **Mở rộng lên `long` vẫn có giới hạn:** ví dụ `large * large` bị tràn `long`; `Math.multiplyExact` phát hiện, `BigInteger` giữ kết quả toán học chính xác.

## 8. Kiểm tra biên trước khi chọn `int`, `long` hay `BigInteger`

Một cách thực tế để thiết kế phép nhân:

1. **Xác định miền đầu vào**: giá trị nhỏ nhất/lớn nhất có thể xuất hiện là bao nhiêu, có âm hay không?
2. **Xác định miền tích toán học**, không chỉ miền của từng toán hạng. Hai số đều vừa `int` vẫn có thể cho tích lớn hơn `int`.
3. **Chọn kiểu tính toán đủ rộng từ đầu**: `int * int` cần tối đa `long` để giữ tích chính xác; `long * long` có thể cần `BigInteger`.
4. **Nếu kiểu kết quả phải bị giới hạn**, dùng `Math.multiplyExact` và xử lý `ArithmeticException` theo nghiệp vụ.
5. **Kiểm tra các biểu thức trung gian** trong tích nhiều thừa số, phép cộng/nhân xen kẽ, lệnh gọi hàm và biểu thức ép kiểu.

Ví dụ với `quantity * unitPriceInCents`, cả số lượng và đơn giá lưu dạng `int` chưa bảo đảm **tổng tiền** nằm trong `int`. Nếu kết quả phải là `long`:

```java
int quantity = 50_000;
int unitPriceInCents = 50_000;

long totalCents = (long) quantity * unitPriceInCents; // 2500000000
```

Nếu kết quả dài hơn `long` có thể xảy ra vì dữ liệu nhập không giới hạn, cần thiết kế biên rõ ràng hoặc tính bằng `BigInteger`. Nếu dùng `long` mà muốn kiểm tra thay vì tràn im lặng, `Math.multiplyExact((long) quantity, unitPriceInCents)` là lựa chọn phù hợp.

**Lưu ý về tốc độ và độ rộng:** Không nhất thiết chuyển mọi phép nhân nhỏ thành `long`; cần chọn kiểu theo miền giá trị và yêu cầu dữ liệu. Điều cần tránh là chọn kiểu biến đích đủ rộng nhưng để **biểu thức trung gian** tính ở miền hẹp hơn.

## 9. Những nhầm lẫn thường gặp

1. **“`long result = intA * intB` chắc chắn đúng.”** Sai: `intA * intB` được tính theo `int` trước khi chuyển sang `long`.
2. **“`(long) (intA * intB)` khôi phục tích.”** Sai: cast áp dụng **sau** phép nhân trong ngoặc.
3. **“Chỉ cần thêm `1L` ở cuối chuỗi nhân.”** Sai: `a * b * 1L` đã tính `a * b` theo `int`.
4. **“Nếu cả hai toán hạng nằm trong miền `int` thì tích cũng vừa `int`.”** Sai: `50_000 * 50_000` vượt `Integer.MAX_VALUE`.
5. **“Overflow của `int` luôn ném ngoại lệ.”** Sai: phép `*` nguyên thủy thường quấn vòng, chỉ API kiểm tra như `Math.multiplyExact` báo lỗi.
6. **“Đổi một toán hạng sang `double` luôn tốt hơn `long`.”** Sai với tính toán nguyên chính xác: `double` có thể làm tròn số nguyên lớn.
7. **“`Math.multiplyExact(intA, intB)` trả được `long` vì biến nhận là `long`.”** Sai: overload `int,int` được chọn từ **kiểu đối số**.
8. **“`Math.multiplyExact(intA * intB, longC)` kiểm tra cả phép nhân đầu tiên.”** Sai: đối số `intA * intB` có thể tràn trước khi gọi hàm.
9. **“`long * long` không bao giờ tràn.”** Sai: `long` chỉ có 64 bit; tích của hai `long` có thể cần rộng hơn.
10. **“`BigInteger.valueOf(longA * longB)` tránh mất dữ liệu.”** Sai: phép nhân `long` xảy ra trước khi tạo `BigInteger`.

## 10. Tự kiểm tra

- **`int a = 70_000, b = 70_000; long x = a * b;` có chính xác `4_900_000_000` không?** Không, vì `int * int` tràn. Sửa thành `long x = (long) a * b;`.
- **`long x = (long) (a * b);` có tốt hơn không?** Không: vẫn nhân `int` trước.
- **`long x = a * b * 1L;` và `long y = 1L * a * b;` khác gì?** `x` có phép nhân đầu theo `int`; `y` có các phép nhân theo `long`.
- **`Math.multiplyFull(a, b)` trả về kiểu gì khi `a` và `b` là `int`?** `long`, và tích của hai `int` luôn vừa miền `long`.
- **Nếu hai toán hạng đã là `long` và tích có thể vượt `long`, làm gì?** `Math.multiplyExact(long,long)` để phát hiện tràn; `BigInteger` để biểu diễn kết quả nguyên chính xác vượt 64 bit.
- **Vì sao cast `(long)` ở ngoài dấu ngoặc không cứu được số đã tràn?** Vì quá trình tính toán bằng `int` đã bỏ các bit vượt phạm vi **trước khi cast**.

**Ghi nhớ:** Java quyết định kiểu của phép nhân từ **kiểu toán hạng**, rồi mới tính và gán. Với `int * int` có thể vượt 32 bit, hãy **nâng một toán hạng thành `long` trước dấu `*`**: `(long) a * b`. Cast sau `(long) (a * b)` chỉ mở rộng một kết quả `int` có thể đã sai. Khi `long` chưa đủ, cần phát hiện tràn hoặc dùng `BigInteger`.
