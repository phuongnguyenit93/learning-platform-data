# Float.isNaN, Double.isNaN, isInfinite và isFinite trong Java

## 1. Vì sao phải phân loại giá trị số thực?

Trong Java, `float` và `double` tuân theo biểu diễn số thực nhị phân IEEE 754. Ngoài các giá trị hữu hạn (*finite*), chúng còn có các giá trị đặc biệt:

- **NaN** (*Not a Number*): biểu diễn kết quả không phải số thực thông thường, chẳng hạn `0.0 / 0.0`.
- **+Infinity**: vô cực dương, chẳng hạn `1.0 / 0.0`.
- **-Infinity**: vô cực âm, chẳng hạn `-1.0 / 0.0`.
- **Giá trị hữu hạn**: số thông thường (kể cả +0.0, -0.0, số dưới chuẩn và số cực lớn nhưng còn hữu hạn).

Để kiểm tra đúng từng loại, Java cung cấp ba nhóm phương thức tĩnh trên cả hai lớp bao:

| Phương thức | Trả `true` khi nào? | Không trả `true` với |
|---|---|---|
| `Float.isNaN(float)` / `Double.isNaN(double)` | Giá trị là NaN | ±Infinity, mọi số hữu hạn |
| `Float.isInfinite(float)` / `Double.isInfinite(double)` | Giá trị là +Infinity hoặc -Infinity | NaN, mọi số hữu hạn |
| `Float.isFinite(float)` / `Double.isFinite(double)` | Giá trị hữu hạn, bao gồm ±0 và số dưới chuẩn | NaN, +Infinity, -Infinity |

Các phương thức này trả `boolean` và **không thay đổi** số được kiểm tra. Nếu một số `double` đã là NaN hoặc vô cực do bước tính trước đó, gọi `isFinite` chỉ phát hiện trạng thái ấy; phương thức không tự sửa kết quả.

Ví dụ ngắn:

```java
double a = 12.5;
double b = 0.0 / 0.0;
double c = 1.0 / 0.0;

System.out.println(Double.isFinite(a));   // true
System.out.println(Double.isNaN(b));      // true
System.out.println(Double.isInfinite(c)); // true
```

**Điểm cần nhớ:** một giá trị thuộc đúng một trong ba loại **NaN**, **vô cực**, hoặc **hữu hạn**. Riêng dấu của Infinity có thể xác định bằng so sánh với `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` (hoặc các hằng tương ứng của `Float`).

## 2. Dấu phẩy động có khác số nguyên ở phép chia cho 0

Trong số học nguyên, chia cho 0 bằng toán tử `/` ném `ArithmeticException`:

```java
// int bad = 1 / 0; // nếu được thực thi, ném ArithmeticException
int numerator = 1;
int denominator = 0;
// int result = numerator / denominator; // lúc chạy: ArithmeticException
```

Với `float`/`double`, phép chia cho 0 tuân theo quy tắc dấu phẩy động:

```java
double positiveInfinity = 1.0 / 0.0; // Infinity
double negativeInfinity = -1.0 / 0.0; // -Infinity
double notANumber = 0.0 / 0.0;       // NaN
```

Đây là những giá trị có thể lưu trong biến `double`; **phép chia số thực không tự ném `ArithmeticException` vì mẫu 0.0**.

NaN cũng có thể xuất hiện từ phép toán không có kết quả số thực hữu hạn:

```java
double a = Math.sqrt(-1.0); // NaN
double b = Double.POSITIVE_INFINITY
         + Double.NEGATIVE_INFINITY; // NaN
double c = Double.POSITIVE_INFINITY * 0.0; // NaN
```

Vô cực có thể xuất hiện từ phép toán hữu hạn bị **tràn miền số thực**:

```java
double tooLarge = Double.MAX_VALUE * 2.0; // Infinity
float alsoTooLarge = Float.MAX_VALUE * 2.0f; // Infinity
```

Ngược lại, số rất nhỏ có thể **underflow** thành 0.0 hoặc còn là số dưới chuẩn; cả hai vẫn là **hữu hạn** theo `isFinite`.

## 3. NaN: tại sao không dùng `==` để kiểm tra?

NaN có quy tắc so sánh đặc biệt. Theo toán tử so sánh số thực Java:

- `NaN == NaN` trả **false**, kể cả khi hai vế là cùng một biến.
- `NaN != NaN` trả **true**.
- `NaN < x`, `NaN <= x`, `NaN > x` và `NaN >= x` đều **false** với mọi giá trị số thực `x`, kể cả NaN.

Ví dụ:

```java
double x = Double.NaN;

System.out.println(x == x); // false
System.out.println(x != x); // true
System.out.println(x < 0);  // false
System.out.println(x > 0);  // false
```

Do đó, cách đúng, rõ ràng và ổn định để phát hiện NaN là:

```java
boolean invalid = Double.isNaN(x);
```

Không viết:

```java
// boolean invalid = (x == Double.NaN); // luôn false
```

Đôi khi bạn thấy mẹo `x != x` để nhận diện NaN. Mẹo này đúng với primitive floating-point theo quy tắc trên, nhưng **`Double.isNaN(x)` nói rõ ý định**, dễ đọc và ít gây nhầm hơn.

### NaN lan truyền qua phép toán

Với các phép cộng/trừ/nhân/chia số thực thông thường, nếu một toán hạng là NaN thì kết quả cũng thường là NaN:

```java
double x = Double.NaN;
System.out.println(Double.isNaN(x + 1.0)); // true
System.out.println(Double.isNaN(x * 0.0)); // true
```

Không nên áp dụng một quy tắc này một cách máy móc cho **mọi API toán học**: mỗi phương thức `Math` có hợp đồng riêng cho các trường hợp đặc biệt. Khi cần đảm bảo dữ liệu đầu vào hợp lệ, kiểm tra `isFinite` **trước** khi đưa vào chuỗi tính toán.

## 4. Infinity: có cả dấu dương và dấu âm

`Float.isInfinite` và `Double.isInfinite` trả `true` cho **cả hai dấu**:

```java
double plus = Double.POSITIVE_INFINITY;
double minus = Double.NEGATIVE_INFINITY;

System.out.println(Double.isInfinite(plus));  // true
System.out.println(Double.isInfinite(minus)); // true
System.out.println(Double.isNaN(plus));       // false
```

Khi cần phân biệt dấu:

```java
if (value == Double.POSITIVE_INFINITY) {
    // giá trị là vô cực dương
} else if (value == Double.NEGATIVE_INFINITY) {
    // giá trị là vô cực âm
}
```

Đây là **đoạn mã minh họa** với biến `double value` đã khai báo trong phạm vi thích hợp, không phải chương trình độc lập.

Với toán tử so sánh số học:

- `Double.POSITIVE_INFINITY > Double.MAX_VALUE` là `true`.
- `Double.NEGATIVE_INFINITY < -Double.MAX_VALUE` là `true`.
- Vô cực không phải NaN, và không phải số hữu hạn.

**Sai lầm thường gặp:** kiểm tra `!Double.isNaN(value)` rồi kết luận giá trị hữu hạn. Điều này **sai** vì ±Infinity không phải NaN.

## 5. isFinite: kiểm tra một giá trị có hữu hạn không

`Double.isFinite(value)` tương đương về ý nghĩa với:

```java
!Double.isNaN(value) && !Double.isInfinite(value)
```

Tương tự:

```java
Float.isFinite(value)
```

tương đương với:

```java
!Float.isNaN(value) && !Float.isInfinite(value)
```

Ví dụ:

```java
System.out.println(Double.isFinite(100.0)); // true
System.out.println(Double.isFinite(0.0)); // true
System.out.println(Double.isFinite(-0.0)); // true
System.out.println(Double.isFinite(Double.MIN_VALUE)); // true
System.out.println(Double.isFinite(Double.MAX_VALUE)); // true

System.out.println(Double.isFinite(Double.NaN)); // false
System.out.println(Double.isFinite(Double.POSITIVE_INFINITY)); // false
System.out.println(Double.isFinite(Double.NEGATIVE_INFINITY)); // false
```

**`Double.MIN_VALUE` không phải số âm nhỏ nhất!** Hằng này là số **dương khác 0 nhỏ nhất** biểu diễn được (số dưới chuẩn). `-Double.MAX_VALUE` gần vùng hữu hạn âm thấp nhất. Việc nhầm `MIN_VALUE` trong số thực với `Integer.MIN_VALUE` trong số nguyên là lỗi rất phổ biến.

Tương tự cho `Float.MIN_VALUE` và `Float.MAX_VALUE`.

### Phân biệt “hữu hạn” với “hợp lệ theo nghiệp vụ”

`Double.isFinite(1.0e300)` là `true`, dù số ấy có thể quá lớn đối với số tiền, cân nặng hay số lượng sản phẩm. `isFinite` **chỉ loại NaN và vô cực**, không tự kiểm tra giá trị dương, không kiểm tra giới hạn min/max, và không khẳng định số có độ chính xác thập phân mong muốn.

Muốn đảm bảo số trong đoạn [0, 100], cần **cả tính hữu hạn và giới hạn**:

```java
boolean valid = Double.isFinite(value)
        && value >= 0.0
        && value <= 100.0;
```

Nếu cần số nguyên chính xác, còn phải kiểm tra phần lẻ và độ chính xác của dữ liệu, không chỉ `isFinite`.

## 6. Chương trình chạy được: phân loại đầy đủ

Tạo file `FloatingClassificationDemo.java`:

```java
public class FloatingClassificationDemo {
    public static void main(String[] args) {
        double[] values = {
                0.0,
                -0.0,
                Double.MIN_VALUE,
                Double.MAX_VALUE,
                Double.POSITIVE_INFINITY,
                Double.NEGATIVE_INFINITY,
                Double.NaN
        };
        String[] labels = {
                "+0.0", "-0.0", "MIN_VALUE", "MAX_VALUE",
                "+Infinity", "-Infinity", "NaN"
        };

        for (int i = 0; i < values.length; i++) {
            double x = values[i];
            System.out.printf(
                    "%s: NaN=%b, Infinite=%b, Finite=%b%n",
                    labels[i],
                    Double.isNaN(x),
                    Double.isInfinite(x),
                    Double.isFinite(x));
        }

        float f = 3.5f;
        System.out.println("Float 3.5 finite: " + Float.isFinite(f));
        System.out.println("Float NaN: " + Float.isNaN(Float.NaN));
        System.out.println("Float +Infinity: "
                + Float.isInfinite(Float.POSITIVE_INFINITY));
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac FloatingClassificationDemo.java
java FloatingClassificationDemo
```

Kết quả chính xác:

```text
+0.0: NaN=false, Infinite=false, Finite=true
-0.0: NaN=false, Infinite=false, Finite=true
MIN_VALUE: NaN=false, Infinite=false, Finite=true
MAX_VALUE: NaN=false, Infinite=false, Finite=true
+Infinity: NaN=false, Infinite=true, Finite=false
-Infinity: NaN=false, Infinite=true, Finite=false
NaN: NaN=true, Infinite=false, Finite=false
Float 3.5 finite: true
Float NaN: true
Float +Infinity: true
```

Dấu `+` trong `+0.0` hoặc `+Infinity` ở cột nhãn là văn bản do mảng `labels` cung cấp, không phải dấu tự thêm bởi `printf`. Ba cột boolean là kết quả kiểm tra thực tế bằng API.

## 7. So sánh NaN và hai giá trị ±0.0

Ngoài NaN, số thực còn có **+0.0** và **-0.0**. Hai giá trị bằng nhau với toán tử `==` nhưng khác bit dấu:

```java
double a = 0.0;
double b = -0.0;

System.out.println(a == b);          // true
System.out.println(1.0 / a);         // Infinity
System.out.println(1.0 / b);         // -Infinity
System.out.println(Double.isFinite(a)); // true
System.out.println(Double.isFinite(b)); // true
```

Cả hai số 0 đều **hữu hạn**; `isNaN` và `isInfinite` đều trả false.

### `Double.compare` và `Double.equals` có quy tắc khác `==`

Đối với primitive, `NaN == NaN` false. Nhưng khi sử dụng `Double.compare` hoặc phương thức `Double.equals` của wrapper, Java đặt ra một thứ tự/quan hệ bằng nhau **nhằm làm việc nhất quán với sắp xếp và collections**:

- `Double.compare(Double.NaN, Double.NaN)` trả **0**.
- `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` trả **true**.
- `Double.compare(+0.0, -0.0)` trả **số dương**.
- `Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` trả **false**.

Điều này không mâu thuẫn: `==` trên primitive áp dụng quan hệ số học IEEE 754, còn `compare`/`equals` được đặc tả riêng cho wrapper. Khi so sánh cho mục đích nghiệp vụ, phải biết rõ bạn muốn **so sánh số học** hay **phân biệt các biểu diễn đặc biệt**.

Chương trình minh họa:

```java
public class FloatingComparisonDemo {
    public static void main(String[] args) {
        double nan = Double.NaN;

        System.out.println("NaN == NaN: " + (nan == nan));
        System.out.println("NaN != NaN: " + (nan != nan));
        System.out.println("NaN < 0: " + (nan < 0.0));
        System.out.println("NaN > 0: " + (nan > 0.0));
        System.out.println("Double.isNaN: " + Double.isNaN(nan));
        System.out.println("Double.compare(NaN, NaN): "
                + Double.compare(nan, Double.NaN));
        System.out.println("Double.equals(NaN): "
                + Double.valueOf(nan).equals(Double.valueOf(Double.NaN)));

        System.out.println("+0.0 == -0.0: " + (0.0 == -0.0));
        System.out.println("Double.compare(+0, -0): "
                + Double.compare(0.0, -0.0));
        System.out.println("Double.equals(+0, -0): "
                + Double.valueOf(0.0).equals(Double.valueOf(-0.0)));
    }
}
```

Lưu file `FloatingComparisonDemo.java`, biên dịch và chạy:

```bash
javac FloatingComparisonDemo.java
java FloatingComparisonDemo
```

Kết quả:

```text
NaN == NaN: false
NaN != NaN: true
NaN < 0: false
NaN > 0: false
Double.isNaN: true
Double.compare(NaN, NaN): 0
Double.equals(NaN): true
+0.0 == -0.0: true
Double.compare(+0, -0): 1
Double.equals(+0, -0): false
```

Nếu mục tiêu là **phát hiện NaN**, vẫn nên gọi `Double.isNaN`/`Float.isNaN`, thay vì tìm cách kiểm tra bằng wrapper `equals` hoặc thao tác so sánh bit.

## 8. Một biểu thức kiểm tra phạm vi có thể lọt NaN

Đây là lỗi logic quan trọng. Xem cách kiểm tra một giá trị phải ở trong đoạn từ 0 đến 100:

```java
double value = Double.NaN;

boolean outside = value < 0.0 || value > 100.0;
System.out.println(outside); // false
```

Vì **mọi so sánh quan hệ với NaN đều false**, `outside` trở thành false. Nếu ứng dụng chỉ bác bỏ giá trị khi `outside == true`, NaN sẽ bị **lọt qua** như một giá trị “không nằm ngoài phạm vi”, dù thực ra không hợp lệ.

Cách an toàn:

```java
boolean accepted = Double.isFinite(value)
        && value >= 0.0
        && value <= 100.0;
```

Hoặc muốn kiểm tra điều kiện bị từ chối:

```java
boolean rejected = !Double.isFinite(value)
        || value < 0.0
        || value > 100.0;
```

Nhờ kiểm tra `isFinite` trước, cả NaN và ±Infinity đều bị loại. Tính short-circuit của `&&`/`||` giúp biểu thức thể hiện rõ các bước kiểm tra; không phải vì việc so sánh NaN ném ngoại lệ (nó không ném).

Nếu chỉ kiểm tra `value >= 0.0 && value <= 100.0`, NaN cũng bị loại vì hai so sánh đều false. Tuy nhiên thêm `isFinite` giúp **diễn đạt trực tiếp yêu cầu** và tránh các lỗi khi tái cấu trúc biểu thức theo dạng “không ở ngoài miền”.

## 9. Cần phân loại trước hay sau chuyển từ `double` sang `float`?

`double` có miền độ lớn rộng hơn `float`. Một số đang hữu hạn với `double` có thể thành Infinity sau khi ép hẹp sang `float`:

```java
double big = 1.0e40;
float narrowed = (float) big;

System.out.println(Double.isFinite(big));  // true
System.out.println(Float.isFinite(narrowed));  // false
System.out.println(Float.isInfinite(narrowed)); // true
```

Tương tự, giá trị `double` rất nhỏ có thể bị làm tròn thành `0.0f` khi chuyển sang `float`. Số 0 vẫn hữu hạn, nhưng thông tin độ lớn đã mất.

Do đó cần đặt kiểm tra **ở đúng biên dữ liệu**:

- Nếu API nhận `double` và yêu cầu dữ liệu `double` hữu hạn, kiểm tra `Double.isFinite` trước.
- Nếu API **phải lưu thành `float`**, kiểm tra thêm **`Float.isFinite` sau chuyển đổi** khi không cho phép Infinity ở đích.
- Nếu cần chống mất chính xác do ép kiểu hoặc làm tròn, phải dùng kiểm tra khác; `isFinite` không đủ để chứng minh dữ liệu được bảo toàn chính xác.

### Ví dụ ngắn về chuyển đổi

```java
double finiteDouble = 1.0e40;
float overflowedFloat = (float) finiteDouble;

System.out.println("double finite: "
        + Double.isFinite(finiteDouble));
System.out.println("float finite: "
        + Float.isFinite(overflowedFloat));
System.out.println("float infinite: "
        + Float.isInfinite(overflowedFloat));
```

Kết quả:

```text
double finite: true
float finite: false
float infinite: true
```

Đây là **đoạn minh họa đặt bên trong phương thức Java** (không có class/`main` độc lập). Nó nhấn mạnh rằng không nên kiểm tra một lần ở kiểu nguồn rồi mặc định mọi chuyển đổi về sau đều an toàn.

## 10. Kiểm tra chuỗi đầu vào và API trước khi tính toán

Một số API parse số thực của Java có thể chấp nhận chuỗi biểu diễn giá trị đặc biệt, chẳng hạn `"NaN"`, `"Infinity"` và `"-Infinity"`. Vì thế parse thành công **không** có nghĩa dữ liệu hữu hạn.

Thiết kế phương thức parse chấp nhận **chỉ số hữu hạn**:

```java
static double parseFiniteDouble(String text) {
    double value = Double.parseDouble(text);
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("non-finite number");
    }
    return value;
}
```

`Double.parseDouble` có thể ném `NumberFormatException` với chuỗi sai cú pháp; phương thức trên dùng `IllegalArgumentException` để từ chối đầu vào đã parse được nhưng không hữu hạn. Nếu đầu vào do người dùng cung cấp, cần chuyển những lỗi này thành thông báo phù hợp giao diện/API, thay vì đưa nguyên stack trace ra ngoài.

### Chương trình chạy được

Tạo file `FiniteInputDemo.java`:

```java
public class FiniteInputDemo {
    static double parseFiniteDouble(String text) {
        double value = Double.parseDouble(text);
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("non-finite number");
        }
        return value;
    }

    public static void main(String[] args) {
        String[] samples = {
                "1.25", "0", "NaN", "Infinity", "-Infinity",
                "1e309", "abc"
        };

        for (String text : samples) {
            try {
                double value = parseFiniteDouble(text);
                System.out.println(text + " -> accepted: " + value);
            } catch (NumberFormatException e) {
                System.out.println(text + " -> invalid format");
            } catch (IllegalArgumentException e) {
                System.out.println(text + " -> non-finite");
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FiniteInputDemo.java
java FiniteInputDemo
```

Kết quả:

```text
1.25 -> accepted: 1.25
0 -> accepted: 0.0
NaN -> non-finite
Infinity -> non-finite
-Infinity -> non-finite
1e309 -> non-finite
abc -> invalid format
```

Chuỗi `"1e309"` có cú pháp số khoa học hợp lệ, nhưng độ lớn vượt miền hữu hạn `double` và được parse thành +Infinity. Vì vậy cần kiểm tra **sau parse**, không chỉ kiểm tra cú pháp chuỗi.

Nếu giá trị là đơn giá, tỷ lệ phần trăm, khoảng thời gian hoặc một đại lượng có miền xác định, bổ sung kiểm tra miền **sau** bước `isFinite`.

## 11. Lưu ý với `null`, wrapper và dữ liệu thiếu

Các phương thức `Float.isNaN(float)`, `Double.isNaN(double)`, `isInfinite` và `isFinite` nhận **primitive**, không nhận giá trị `null` trực tiếp. Nếu bạn truyền một biến kiểu wrapper có thể null, Java có thể **unbox** trước:

```java
Double nullable = null;

// boolean ok = Double.isFinite(nullable);
// sẽ ném NullPointerException khi unbox null
```

Đừng nhầm “thiếu dữ liệu” với “NaN”:

- **`null`** là tham chiếu không có đối tượng, có thể dùng trong `Double`/`Float`.
- **`Double.NaN`/`Float.NaN`** là một giá trị dấu phẩy động đặc biệt, **không phải null**.
- **Infinity** cũng là giá trị số thực đặc biệt, không phải null.

Một đoạn kiểm tra an toàn, có chính sách rõ ràng:

```java
static boolean isPresentAndFinite(Double value) {
    return value != null && Double.isFinite(value);
}
```

Đây là đoạn **phương thức minh họa**, đặt trong class. Nhờ short-circuit `&&`, khi `value == null`, Java không đánh giá vế phải nên không unbox null.

Nếu dữ liệu thiếu cần được coi là lỗi bắt buộc nhập, đừng âm thầm đổi null thành 0.0; nên phân biệt lỗi thiếu dữ liệu và lỗi giá trị không hữu hạn để xử lý chính xác.

## 12. isFinite không phải bộ kiểm tra tính chính xác

Một số `double` hữu hạn vẫn có thể là kết quả của sai số do biểu diễn nhị phân:

```java
double sum = 0.1 + 0.2;
System.out.println(sum);                 // 0.30000000000000004
System.out.println(Double.isFinite(sum)); // true
System.out.println(sum == 0.3);          // false
```

`Double.isFinite(sum)` trả true vì sum không phải NaN hoặc Infinity; nó **không** chứng minh sum bằng 0.3 theo cách so sánh bit hoặc biểu diễn thập phân mong muốn.

Với số thực, một kiểm tra so sánh gần đúng có thể dùng **ngưỡng sai số phù hợp miền ứng dụng** khi mục đích là so sánh kết quả tính toán gần nhau. Chỉ dùng ngưỡng cố định mà không xem xét độ lớn có thể gây sai cho nhiều bài toán.

Khi xử lý tiền hoặc số thập phân cần chính xác theo quy tắc nghiệp vụ, cân nhắc `BigDecimal` với nguồn dữ liệu thập phân thích hợp và chính sách làm tròn rõ ràng. `BigDecimal` không có khái niệm giá trị NaN hay Infinity như `double`; vì vậy một số phép chuyển đầu vào đặc biệt sẽ phải được từ chối.

Ngoài ra, `-0.0` là hữu hạn nhưng khác `+0.0` ở bit dấu; nếu thuật toán liên quan đến nghịch đảo hoặc bảo toàn biểu diễn, cần cân nhắc dấu của 0.

## 13. Thực hành phát hiện kết quả không hợp lệ sau phép toán

Nếu đầu vào đều hữu hạn, kết quả **không được bảo đảm** vẫn hữu hạn. Có thể tràn khi nhân/cộng hoặc tạo NaN từ phép toán không xác định:

```java
double a = Double.MAX_VALUE;
double b = 2.0;

double product = a * b; // +Infinity
System.out.println(Double.isFinite(a)); // true
System.out.println(Double.isFinite(b)); // true
System.out.println(Double.isFinite(product)); // false
```

Vì vậy trong đoạn tính toán quan trọng, kiểm tra tính hữu hạn ở **các ranh giới có ý nghĩa**: khi nhận dữ liệu đầu vào, sau những phép có thể tạo giá trị đặc biệt, và trước khi lưu/trả kết quả nếu hợp đồng API không cho phép các giá trị ấy.

Ví dụ chức năng nghiệp vụ chỉ chấp nhận kết quả hữu hạn:

```java
static double multiplyFinite(double a, double b) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        throw new IllegalArgumentException("non-finite input");
    }
    double result = a * b;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("non-finite product");
    }
    return result;
}
```

Đây là **phương thức minh họa**, đặt trong class để sử dụng. Nó phát hiện NaN và Infinity, nhưng không ngăn mọi vấn đề: kết quả có thể **underflow về 0** hoặc có **sai số làm tròn** mà vẫn hữu hạn. Nếu những tình huống ấy cũng quan trọng, bạn phải đặt thêm quy tắc kiểm tra.

## 14. Những lỗi phổ biến

| Nhầm lẫn | Kết quả thực tế | Cách xử lý |
|---|---|---|
| `x == Double.NaN` kiểm tra NaN | Luôn false | Dùng `Double.isNaN(x)` |
| `x != Double.NaN` nghĩa là không phải NaN | Luôn true, kể cả x là NaN | Dùng `!Double.isNaN(x)` |
| `!isNaN(x)` nghĩa là hữu hạn | Infinity không phải NaN | Dùng `isFinite(x)` |
| `isInfinite(x)` phân biệt dấu vô cực | Trả true cho cả ±Infinity | So sánh với hằng dấu tương ứng nếu cần |
| `x < min || x > max` sẽ loại mọi dữ liệu sai | NaN làm cả hai vế false | Dùng `!isFinite(x) || x < min || x > max` |
| `isFinite` loại số cực lớn | `Double.MAX_VALUE` vẫn hữu hạn | Kiểm tra giới hạn nghiệp vụ |
| `isFinite` phát hiện mất độ chính xác | Sai số làm tròn vẫn hữu hạn | Kiểm tra độ chính xác theo mục tiêu |
| Kiểm tra `double` hữu hạn là đủ trước khi cast `float` | Cast có thể tạo Infinity | Kiểm tra `Float.isFinite` sau cast |
| `Double.MIN_VALUE` là số âm nhỏ nhất | Đây là số dương khác 0 nhỏ nhất | Dùng `-Double.MAX_VALUE` cho cận âm hữu hạn |
| Parse thành công nghĩa là số bình thường | Có thể parse NaN/Infinity | Kiểm tra `isFinite` sau parse |
| `Double.isFinite(nullWrapper)` trả false | Unboxing null ném NPE | Kiểm tra `wrapper != null` trước |
| Đầu vào hữu hạn thì đầu ra cũng hữu hạn | Phép toán có thể tràn hoặc tạo NaN | Kiểm tra kết quả khi cần |

## 15. Bài tập tự kiểm tra

**Câu 1.** `Double.isNaN(0.0 / 0.0)` bằng gì?  
**Đáp án:** `true`.

**Câu 2.** `Double.isInfinite(1.0 / 0.0)` và `Double.isInfinite(-1.0 / 0.0)` bằng gì?  
**Đáp án:** Cả hai đều `true` vì phương thức nhận biết cả hai dấu vô cực.

**Câu 3.** `Double.isFinite(Double.NaN)` có đúng không?  
**Đáp án:** Không, là `false`.

**Câu 4.** `Double.isFinite(Double.MIN_VALUE)` có đúng không?  
**Đáp án:** Có. `MIN_VALUE` là số dưới chuẩn dương nhỏ nhất, nhưng vẫn hữu hạn.

**Câu 5.** Vì sao `double x = Double.NaN; x == x` trả false?  
**Đáp án:** Theo quy tắc so sánh dấu phẩy động, NaN không bằng bất kỳ giá trị nào, kể cả chính nó, khi dùng `==` primitive.

**Câu 6.** Có thể dùng `value < 0 || value > 100` để từ chối mọi giá trị sai không?  
**Đáp án:** Không. NaN khiến cả hai phép so sánh đều false. Cần kiểm tra `!Double.isFinite(value)` hoặc xác minh cả hữu hạn và thuộc miền.

**Câu 7.** `Double.compare(Double.NaN, Double.NaN)` bằng bao nhiêu?  
**Đáp án:** 0. `compare` dành cho thứ tự/so sánh wrapper, khác quan hệ `==` primitive.

**Câu 8.** `+0.0 == -0.0` có đúng không, và `isFinite` của chúng thế nào?  
**Đáp án:** `==` là true; cả hai đều hữu hạn. Chúng vẫn có bit dấu khác nhau.

**Câu 9.** Nếu `double x = 1e40` rồi ép `float y = (float) x` thì `Double.isFinite(x)` và `Float.isFinite(y)` cho gì?  
**Đáp án:** Lần lượt true và false vì x hữu hạn dưới `double` nhưng y trở thành Infinity dưới `float`.

**Câu 10.** Dữ liệu `Double nullable = null` truyền vào `Double.isNaN(nullable)` có an toàn không?  
**Đáp án:** Không. Java cần unbox để lấy `double` và sẽ ném `NullPointerException`.

**Câu 11.** `double x = 0.1 + 0.2` có hữu hạn không, và có chắc bằng `0.3` qua `==` không?  
**Đáp án:** Hữu hạn, nhưng `x == 0.3` thường false trong Java vì x là 0.30000000000000004.

**Câu 12.** Hai toán hạng `double` đều hữu hạn có bảo đảm tích hữu hạn không?  
**Đáp án:** Không. `Double.MAX_VALUE * 2.0` cho Infinity; cần kiểm tra kết quả nếu ứng dụng yêu cầu giá trị hữu hạn.

## 16. Tóm tắt và tài liệu tham khảo

- **`isNaN(x)`**: nhận biết chính xác trường hợp NaN.
- **`isInfinite(x)`**: nhận biết +Infinity và -Infinity.
- **`isFinite(x)`**: chỉ true khi x không phải NaN và không phải ±Infinity.
- **NaN không dùng `==` để phát hiện**; các phép `<`, `>`, `<=`, `>=` với NaN đều false.
- **Hữu hạn không đồng nghĩa hợp lệ hay chính xác**: vẫn cần kiểm tra miền, sai số, chính sách null và kết quả sau phép tính.
- **`float` và `double` có miền khác nhau**; một `double` hữu hạn có thể thành Infinity khi ép sang `float`.

Tra cứu API chính thức: [Float — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html), [Double — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html), và [Java Language Specification — Floating-Point Operations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html).
