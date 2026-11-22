# Binary numeric promotion với int, long, float và double trong Java

## 1. Binary numeric promotion là gì?

**Binary numeric promotion** (nâng kiểu số nhị phân) là bộ quy tắc Java dùng để xác định **kiểu chung cho hai toán hạng số** của nhiều toán tử nhị phân. Khi hai toán hạng có kiểu nguyên thủy khác nhau, Java chuyển chúng sang kiểu thích hợp trước khi thực hiện phép toán. Kết quả của phép toán số học có kiểu do quy tắc này quyết định, **không được lựa chọn ngược từ kiểu của biến đang nhận giá trị**.

Ví dụ:

```java
int count = 50_000;
int price = 50_000;

long wrong = count * price;          // Phép nhân là int, tràn trước khi gán long.
long correct = (long) count * price; // Phép nhân là long, kết quả 2500000000.
```

Một phép toán số học giữa hai `int` vẫn là `int`, ngay cả khi kết quả được gán vào `long` hoặc `double`. Chỉ khi **ít nhất một toán hạng** được nâng thành `long`, `float` hoặc `double` *trước phép toán*, loại phép toán mới thay đổi theo quy tắc tương ứng.

Bài này tập trung vào sự kết hợp giữa bốn kiểu: `int`, `long`, `float` và `double`. Các kiểu số nguyên nhỏ hơn cũng được nhắc đến để làm rõ vì sao điểm xuất phát mặc định là `int`.

## 2. Quy tắc chọn kiểu theo thứ tự ưu tiên

Theo Java Language Specification (JLS §5.6), với hai toán hạng số trong ngữ cảnh áp dụng binary numeric promotion, trước tiên các đối tượng wrapper phù hợp được **unbox** nếu cần. Sau đó Java chọn kiểu chung theo thứ tự sau:

1. Nếu **một trong hai toán hạng là `double`**, toán hạng còn lại được chuyển sang `double`.
2. Nếu không có `double` nhưng có **`float`**, toán hạng còn lại được chuyển sang `float`.
3. Nếu không có hai kiểu số thực trên nhưng có **`long`**, toán hạng còn lại được chuyển sang `long`.
4. Nếu không có những kiểu trên, cả hai toán hạng được chuyển thành **`int`** khi cần. Điều này áp dụng cho `byte`, `short`, `char` và `int`.

| Hai kiểu toán hạng | Kiểu chung cho phép toán số học |
| --- | --- |
| `int` + `int` | `int` |
| `int` + `long` | `long` |
| `long` + `float` | `float` |
| `int` + `float` | `float` |
| `float` + `double` | `double` |
| `long` + `double` | `double` |
| `byte` + `short` | `int` |
| `char` + `int` | `int` |

Thứ tự cần nhớ là **`double > float > long > int`** để chọn kiểu chung, nhưng **“kiểu đứng cao hơn” không luôn đồng nghĩa “giữ nguyên tất cả chữ số”**. Đặc biệt, `long → float` có thể làm tròn, và `long → double` có thể làm tròn các số nguyên lớn.

Ở bảng trên, dấu `+` minh họa phép **cộng số**. Nếu một toán hạng là `String`, dấu `+` có thể thực hiện *nối chuỗi* theo những quy tắc khác. `boolean` không phải kiểu số và không thuộc binary numeric promotion.

## 3. Các phép toán nào áp dụng quy tắc này?

Binary numeric promotion tham gia khi Java thực hiện nhiều toán tử số nhị phân:

- Các toán tử số học `+`, `-`, `*`, `/`, `%` khi hai toán hạng là số.
- Các toán tử so sánh thứ tự `<`, `<=`, `>`, `>=` trên các toán hạng số. Hai toán hạng được nâng kiểu để so sánh, nhưng **kết quả phép so sánh là `boolean`**.
- `==` và `!=` khi so sánh hai toán hạng thuộc kiểu số nguyên thủy (hoặc được unbox theo quy tắc áp dụng). Kết quả là `boolean`.
- Các toán tử bit `&`, `|`, `^` ở chế độ **số nguyên**, với kiểu chung là `int` hoặc `long`.

Điều quan trọng là **không áp dụng nhầm quy tắc này cho mọi toán tử**. Các phép dịch `<<`, `>>`, `>>>` sử dụng *unary numeric promotion* riêng trên mỗi toán hạng; kiểu kết quả phụ thuộc vào toán hạng **bên trái** sau khi nâng, không bị toán hạng bên phải kéo lên `long`. Toán tử điều kiện `?:` và toán tử gán ghép cũng có quy tắc định kiểu riêng, dù bên trong có thể cần nâng kiểu số.

Ví dụ:

```java
int a = 7;
long b = 2L;

long sum = a + b;       // long + long => long
long quotient = a / b;  // long / long => long; kết quả 3L.
boolean larger = a > b; // Hai toán hạng so sánh theo long; kết quả boolean.
```

Ngay cả phép chia với kiểu chung `long` vẫn là **chia nguyên** và làm tròn về 0. Để có kết quả `3.5`, phải dùng một toán hạng `float` hoặc `double`.

## 4. Kết hợp `int` và `long`: phép toán ở 64 bit

Nếu một toán hạng là `long` và không có `float`/`double`, Java chuyển toán hạng còn lại sang `long` trước khi thực hiện phép toán:

```java
int n = 2_000_000_000;
long m = 2L;

long product = n * m;  // 4000000000; phép toán int * long => long.
long also = n * 2L;    // 4000000000; hậu tố L tạo long literal.
```

Đối chiếu trường hợp không có toán hạng `long`:

```java
int n = 2_000_000_000;

long tooLate = n * 2;        // -294967296; phép nhân int tràn.
long early = ((long) n) * 2; // 4000000000; phép nhân long.
```

**Cách nghĩ đúng:** phép gán `long tooLate = ...` gồm hai bước: tính **toàn bộ biểu thức vế phải** theo kiểu của nó, rồi chuyển kết quả sang `long`. Nếu phép nhân `int` đã tràn, bước gán không khôi phục các bit đã mất.

Dấu ngoặc có thể làm thay đổi thời điểm nâng kiểu:

```java
int a = 50_000, b = 50_000;
long c = 2L;

long tooLate = (a * b) * c;      // -3589934592
long early = ((long) a * b) * c; // 5000000000
```

Trong `(a * b) * c`, biểu thức con `a * b` đã tràn `int`; việc gặp `c` kiểu `long` sau đó không sửa kết quả cũ. Quy tắc nâng kiểu được áp dụng **tại từng phép toán** của cây biểu thức.

## 5. Kết hợp số nguyên với `float`: cần đề phòng làm tròn

Khi một toán hạng là `float` và không có `double`, Java tính phép toán ở kiểu `float`:

```java
int a = 4;
float b = 1.5f;
float sum = a + b;     // 5.5f

long big = 10L;
float product = big * b; // 15.0f, vì long được chuyển thành float.
```

`float` sử dụng dấu phẩy động nhị phân với **24 bit độ chính xác của phần trị**. Điều này không đủ giữ chính xác mọi giá trị `int` hoặc `long`. Tất cả số nguyên trong khoảng từ `-16_777_216` đến `16_777_216` đều biểu diễn chính xác dưới `float`, nhưng những số nguyên lớn hơn có thể bị làm tròn.

```java
int exactInt = 16_777_217;
float rounded = exactInt + 0.0f;

System.out.println(rounded == 16_777_216f); // true
System.out.println((int) rounded == exactInt); // false
```

Giải thích từng bước:

1. Toán hạng `exactInt` là `int`, toán hạng `0.0f` là `float`.
2. Binary numeric promotion chuyển `exactInt` sang `float`.
3. Giá trị `16_777_217` không biểu diễn chính xác bằng `float`, nên được làm tròn thành `16_777_216.0f` (làm tròn về giá trị gần nhất theo quy tắc IEEE 754).
4. Sau đó mới cộng `0.0f`, cho kết quả đã làm tròn.

Vì thế, **chuyển sang kiểu có miền số lớn hơn không đảm bảo tính chính xác**. `float` có khả năng biểu diễn độ lớn lớn hơn `long`, nhưng lại có độ chính xác số nguyên kém hơn nhiều.

Một ví dụ dễ gặp là `long + float`:

```java
long id = 16_777_217L;
float value = id + 0.0f;

System.out.println((long) value == id); // false
```

Với các mã định danh, bộ đếm hoặc tiền tệ nguyên chính xác, không nên dùng `float` để “tránh tràn” chỉ vì nó đứng trước `long` trong thứ tự nâng kiểu.

## 6. Kết hợp với `double`: ưu tiên cao nhất nhưng không phải chính xác vô hạn

Nếu một trong hai toán hạng là `double`, phép toán số học dùng `double`:

```java
float left = 1.25f;
double right = 2.5;
double sum = left + right; // 3.75.

long count = 7L;
double factor = 0.5;
double half = count * factor; // 3.5.
```

`double` có **53 bit độ chính xác của phần trị**, nên mọi giá trị `int` và mọi số nguyên có trị tuyệt đối không quá `2^53` đều biểu diễn chính xác. Nhưng `long` có thể lớn hơn `2^53`. Một phép tính `long + double` có thể mất độ chính xác khi chuyển `long` thành `double`:

```java
long exact = 9_007_199_254_740_993L; // 2^53 + 1.
double rounded = exact + 0.0;

System.out.println((long) rounded == exact); // false
```

Giá trị `9_007_199_254_740_993` không thể được biểu diễn chính xác bằng `double`. Nó được làm tròn thành `9_007_199_254_740_992.0`. Chuyển ngược `double` sang `long` không phục hồi đơn vị đã mất.

Cũng cần phân biệt **độ lớn biểu diễn**, **độ chính xác** và **quy tắc phép tính**. Ví dụ `0.1 + 0.2` dùng `double` nhưng không biểu diễn chính xác phép cộng thập phân toán học `0.3` do các số thập phân này không biểu diễn hữu hạn trong nhị phân. Đó là giới hạn của dấu phẩy động, không phải lỗi của binary numeric promotion.

## 7. Kiểu biểu thức được quyết định trước khi gán cho biến

Ba ví dụ cùng một quy tắc:

### 7.1. Gán vào `long` sau phép nhân `int`

```java
int price = 50_000;
int quantity = 50_000;

long wrong = price * quantity;          // -1794967296
long correct = (long) price * quantity; // 2500000000
```

### 7.2. Gán vào `double` sau phép chia `int`

```java
int numerator = 1;
int denominator = 2;

double wrong = numerator / denominator;         // 0.0
double correct = (double) numerator / denominator; // 0.5
double alsoCorrect = numerator / 2.0;           // 0.5
```

Vì `int / int` là phép chia nguyên, `numerator / denominator` cho `0`. Gán số `0` đó vào `double` cho `0.0`, không phải `0.5`. Ngược lại, `(double) numerator / denominator` dùng `double` ngay từ phép chia.

### 7.3. Ép kiểu sau biểu thức khác ép kiểu trước biểu thức

```java
int a = 50_000, b = 50_000;

long castAfter = (long) (a * b); // -1794967296
long castBefore = (long) a * b;  // 2500000000
```

Việc đặt dấu ngoặc khiến phép nhân thực hiện trước khi cast. Muốn mở rộng miền tính toán, hãy cast **một toán hạng trước khi thực hiện phép toán nguy hiểm**, không chỉ cast toàn bộ biểu thức sau cùng.

## 8. `byte`, `short` và `char` đều được nâng lên `int`

Binary numeric promotion không có nhánh chọn kiểu chung `byte`, `short` hay `char`. Nếu không có `long`/`float`/`double`, các kiểu nguyên nhỏ đó đều được nâng lên `int`:

```java
byte b = 10;
short s = 20;
char c = 'A';

int sum = b + s;        // 30; kiểu biểu thức là int.
int codePointValue = c + 1; // 66; kiểu biểu thức là int.

// byte wrong = b + s; // Không biên dịch: int không tự thu hẹp thành byte.
```

Ngoại lệ gán một số **biểu thức hằng** kiểu `int` có giá trị nằm trong miền đích (ví dụ `byte k = 10 + 20;`) là quy tắc *assignment conversion* dành cho hằng. Nó **không thay đổi kiểu của biểu thức cộng**: `10 + 20` vẫn là `int`.

Các wrapper như `Integer`/`Long`/`Float`/`Double` có thể tham gia bằng **unboxing**:

```java
Integer boxedInt = 2;
Long boxedLong = 3L;
long sum = boxedInt + boxedLong; // 5L.
```

Tuy nhiên, nếu một wrapper đang là `null` và phải unbox để tính, biểu thức có thể ném `NullPointerException`. Binary numeric promotion không làm `null` trở thành số `0`.

## 9. Hai bẫy tinh tế: so sánh hỗn hợp và phép gán ghép

### 9.1. So sánh `int` với `float` có thể mất tính phân biệt

```java
int n = 16_777_217;
float f = 16_777_216f;

System.out.println(n == f); // true
```

Hai giá trị số nguyên dự định khác nhau, nhưng toán tử `==` áp dụng binary numeric promotion cho cặp `int`/`float`. `n` được làm tròn xuống `16_777_216f` trước khi so sánh, nên kết quả là `true`.

Khi cần so sánh **chính xác các số nguyên**, nên giữ các toán hạng trong kiểu nguyên đủ rộng (`long` nếu đủ miền, hoặc `BigInteger` khi vượt 64 bit). Không sử dụng so sánh hỗn hợp với `float`/`double` một cách vô thức.

### 9.2. Toán tử gán ghép có chuyển kiểu hẹp ngầm

Với phép `E1 += E2`, Java tính phép cộng rồi chuyển kết quả về kiểu của `E1`. Về mặt giá trị, điều này gần với `E1 = (T) (E1 + E2)`, với `T` là kiểu của `E1`, nhưng toán hạng `E1` chỉ được đánh giá một lần trong phép gán ghép.

```java
byte count = 120;
count += 10; // Hợp lệ, phép cộng như int, rồi chuyển hẹp về byte.
System.out.println(count); // -126

int whole = 2;
whole += 1.75; // Hợp lệ, phép cộng như double, rồi chuyển về int.
System.out.println(whole); // 3
```

Các cách viết `count = count + 10` và `whole = whole + 1.75` không biên dịch nếu không cast phù hợp. Nhưng `+=` có cơ chế chuyển kiểu ngầm, có thể dẫn đến tràn hay cắt phần thập phân. Vì thế **gán ghép không phải bằng chứng rằng phép toán ban đầu có kiểu hẹp**.

## 10. Phân biệt với unary numeric promotion và phép dịch bit

Ví dụ dưới đây dễ khiến người học áp dụng sai bảng *binary* cho phép dịch bit:

```java
int bits = 1;
long count = 40L;

int shifted = bits << count; // Kiểu kết quả là int.
```

Dù toán hạng bên phải `count` có kiểu `long`, phép dịch **không đổi toán hạng bên trái `int` thành `long`**. Mỗi toán hạng được *unary numeric promotion* riêng; kết quả có kiểu của toán hạng trái sau nâng kiểu. Với phép dịch `int`, Java chỉ sử dụng 5 bit thấp của khoảng dịch nên `1 << 40` tương đương `1 << 8`, cho `256`.

Nếu thật sự muốn dịch trên 64 bit:

```java
long shifted64 = 1L << 40; // 1099511627776.
```

Đây là khác biệt quan trọng giữa **binary numeric promotion** cho phép toán số học và quy tắc riêng của các toán tử dịch bit. Không suy đoán kiểu kết quả chỉ dựa vào việc toán hạng nào “rộng nhất” nếu toán tử không áp dụng binary numeric promotion.

## 11. Ví dụ Java 17+ hoàn chỉnh

Tạo file **`BinaryNumericPromotionDemo.java`**:

```java
public class BinaryNumericPromotionDemo {
    public static void main(String[] args) {
        int a = 50_000;
        int b = 50_000;

        long late = a * b;
        long early = (long) a * b;
        System.out.println("int * int then long = " + late);
        System.out.println("long * int = " + early);

        int halfAsInt = 1 / 2;
        double halfLate = 1 / 2;
        double halfCorrect = 1 / 2.0;
        System.out.println("int division = " + halfAsInt);
        System.out.println("int division then double = " + halfLate);
        System.out.println("double division = " + halfCorrect);

        int number = 16_777_217;
        float roundedFloat = number + 0.0f;
        System.out.println("int to float exact = "
                + ((int) roundedFloat == number));

        long big = 9_007_199_254_740_993L;
        double roundedDouble = big + 0.0;
        System.out.println("long to double exact = "
                + ((long) roundedDouble == big));

        float f = 1.25f;
        double d = 2.5;
        System.out.println("float + double = " + (f + d));

        byte small = 120;
        small += 10;
        System.out.println("byte += 10 = " + small);

        int n = 16_777_217;
        float compare = 16_777_216f;
        System.out.println("int == float = " + (n == compare));

        long mixed = 2 + 3L;
        System.out.println("int + long = " + mixed);
    }
}
```

Biên dịch và chạy từ thư mục chứa file bằng JDK 17 trở lên:

```bash
javac BinaryNumericPromotionDemo.java
java BinaryNumericPromotionDemo
```

Kết quả chuẩn:

```text
int * int then long = -1794967296
long * int = 2500000000
int division = 0
int division then double = 0.0
double division = 0.5
int to float exact = false
long to double exact = false
float + double = 3.75
byte += 10 = -126
int == float = true
int + long = 5
```

Ở ví dụ này, `int * int` tràn dù biến nhận là `long`; `int / int` làm mất phần phân số dù biến nhận là `double`; các toán hạng `float`/`double` có thể buộc số nguyên làm tròn **trước phép toán hoặc phép so sánh**. Mỗi trường hợp cho thấy kiểu của biểu thức phải được xác định tại **toán tử**, không suy ra từ nơi lưu kết quả.

## 12. Lỗi thường gặp và cách tránh

| Nhầm lẫn | Sự thật | Cách xử lý |
| --- | --- | --- |
| “Vế trái là `long` nên `int * int` thành phép nhân 64 bit.” | Phép nhân `int` đã xảy ra trước phép gán. | Viết `(long) a * b` hoặc dùng toán hạng `long`. |
| “Vế trái là `double` nên `1 / 2` ra `0.5`.” | Phép chia là `int / int`, tạo `0`. | Viết `1.0 / 2`. |
| “`float` rộng hơn `long` nên giữ chính xác mọi `long`.” | `float` có 24 bit độ chính xác, nhiều số nguyên bị làm tròn. | Duy trì kiểu nguyên khi yêu cầu độ chính xác tuyệt đối. |
| “`double` luôn giữ được mọi `long`.” | `double` có 53 bit độ chính xác, không giữ mọi giá trị 64 bit. | Dùng `long`/`BigInteger` khi cần tính nguyên chính xác. |
| “Cộng hai `byte` cho `byte`.” | Phép cộng số học nâng lên `int`. | Nhận kết quả bằng `int`, kiểm tra miền trước khi thu hẹp. |
| “Phép `+= `không mất dữ liệu do không cần cast.” | Gán ghép có chuyển kiểu về toán hạng trái. | Xét tràn và cắt phần phân số rõ ràng. |
| “Mọi toán tử hai toán hạng đều dùng bảng ưu tiên như nhau.” | Dịch bit, nối chuỗi, `?:` có quy tắc riêng. | Xác định toán tử rồi tra đúng ngữ cảnh định kiểu. |
| “So sánh số nguyên với `float` luôn chính xác.” | Ép kiểu trong so sánh có thể làm tròn trước khi đánh giá `==`. | So sánh trong kiểu nguyên đủ rộng. |

**Ghi nhớ:** Với phép toán số học chịu binary numeric promotion, ưu tiên kiểu **`double > float > long > int`**. Chọn kiểu trước khi tính không đảm bảo luôn chính xác: phép `int` có thể tràn, còn chuyển số nguyên sang `float`/`double` có thể làm tròn. Để có kết quả mong muốn, hãy xác định kiểu của **từng phép toán và biểu thức con**, chủ động chọn toán hạng phù hợp và chỉ sau đó xét phép gán kết quả.

**Nguồn tham khảo:** [JLS §5.6 — Numeric Contexts and Promotions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.6), [JLS §15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17), [JLS §15.18 — Additive Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18), [JLS §15.20 — Relational Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20), [JLS §15.26 — Assignment Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.26).
