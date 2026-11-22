# Xây dựng điều kiện kiểm tra miền giá trị rõ ràng — Java 17+

## 1. Mục tiêu

**Kiểm tra miền giá trị** (*range validation*) là xác định một giá trị có thuộc tập giá trị được phép hay không: tuổi từ 18 đến 65, chỉ số mảng từ 0 đến `length - 1`, tỷ lệ trong khoảng 0–1, một giá trị không được rơi vào vùng cấm, v.v.

Trong Java, điều kiện đúng không chỉ cần **biên dưới và biên trên**, mà còn phải quy định:

- Hai biên **được lấy hay loại trừ**?
- Chấp nhận **số âm**, số 0 và các giá trị cực trị không?
- Hai điều kiện nối bằng **`&&` (và)** hay **`||` (hoặc)**?
- Giá trị đến từ `int`/`long`, `float`/`double`, wrapper có thể null hay số decimal?
- Nếu giới hạn bị khai báo sai (`min > max`) thì báo lỗi hay trả false?

Một biểu thức dễ đọc, đúng về ý nghĩa:

~~~java
int age = 20;
boolean validAge = (age >= 18) && (age <= 65);

System.out.println(validAge); // true
~~~

Đây là **khoảng đóng** `[18, 65]`: bao gồm cả 18 và 65. Việc đặt dấu ngoặc riêng cho mỗi so sánh giúp làm rõ hai điều kiện; với biểu thức ngắn, có thể viết `age >= 18 && age <= 65`.

## 2. Dịch yêu cầu thành khoảng toán học và điều kiện Java

| Ý nghĩa | Ký hiệu toán học | Điều kiện Java |
|---|---|---|
| Từ `min` đến `max`, lấy hai biên | `[min, max]` | `value >= min && value <= max` |
| Nằm giữa, không lấy hai biên | `(min, max)` | `value > min && value < max` |
| Lấy biên dưới, không lấy biên trên | `[min, max)` | `value >= min && value < max` |
| Không lấy biên dưới, lấy biên trên | `(min, max]` | `value > min && value <= max` |
| Nhỏ hơn `min` hoặc lớn hơn `max` | Ngoài `[min, max]` | `value < min || value > max` |
| Không nhỏ hơn `min` | `[min, +∞)` | `value >= min` |
| Nhỏ hơn `max` | `(-∞, max)` | `value < max` |
| Bằng một đầu mút | `value = min` | `value == min` |

**Chọn `<` hay `<=` từ yêu cầu, không chọn tùy ý.** Ví dụ chỉ số mảng có `length` phần tử thường phải thuộc **`[0, length)`**, vì vị trí `length` không tồn tại:

~~~java
int[] numbers = {10, 20, 30};
int index = 2;
boolean validIndex = index >= 0 && index < numbers.length;
System.out.println(validIndex); // true
~~~

Nếu `index == numbers.length`, điều kiện trả false. Trước khi truy cập mảng, vẫn cần kiểm tra rằng tham chiếu mảng không null nếu đầu vào có thể thiếu.

## 3. Java không hỗ trợ so sánh dây chuyền kiểu toán học

Trong toán học có thể viết:

~~~text
18 <= age <= 65
~~~

Nhưng Java **không** cho phép:

~~~java
// 18 <= age <= 65 // LỖI BIÊN DỊCH
~~~

Biểu thức `18 <= age` tạo `boolean`, không thể tiếp tục dùng `<= 65` với boolean và int.

Viết hai phép so sánh đầy đủ:

~~~java
boolean valid = (age >= 18) && (age <= 65);
~~~

**Không** dùng `||` khi muốn nằm trong cả hai biên:

~~~java
int age = 100;
boolean wrong = (age >= 18) || (age <= 65);
System.out.println(wrong); // true: điều kiện sai về ý nghĩa
~~~

Với `min <= max`, điều kiện `value >= min || value <= max` hầu như luôn true đối với số nguyên: nó đang hỏi **“thỏa ít nhất một phía”**, không phải “ở giữa”.

## 4. Kiểm tra ngoài miền: dùng `||`, không dùng `&&`

Nếu miền hợp lệ là `[min, max]`, một số nguyên nằm **ngoài miền** khi:

~~~java
boolean outside = (value < min) || (value > max);
~~~

Một số nguyên không thể đồng thời nhỏ hơn min **và** lớn hơn max nếu `min <= max`, nên viết:

~~~java
// value < min && value > max // Sai khi định kiểm tra ngoài miền
~~~

Các cặp điều kiện tương đương trên số nguyên khi giới hạn hợp lệ:

| Ý định | Biểu thức |
|---|---|
| Trong khoảng đóng | `value >= min && value <= max` |
| Ngoài khoảng đóng | `value < min || value > max` |
| Phủ định điều kiện trong khoảng | `!(value >= min && value <= max)` |
| Trong khoảng mở | `value > min && value < max` |
| Ngoài khoảng mở | `value <= min || value >= max` |

Đây là ứng dụng quy tắc **De Morgan**: `!(A && B)` tương đương `!A || !B`. Khi điều kiện phức tạp, nên đặt tên rõ:

~~~java
boolean inside = (value >= min) && (value <= max);
boolean rejected = !inside;
~~~

**Lưu ý với `double` và `NaN`:** cách viết `value < min || value > max` **không nhận diện được NaN**, vì cả hai phép so sánh đều false khi `value` là NaN. Cách xử lý riêng sẽ có ở phần số thực.

## 5. `&&`, `||`, dấu ngoặc và short-circuit

`&&` có mức ưu tiên cao hơn `||`. Khi kết hợp nhiều nhóm, đặt ngoặc theo **quy tắc nghiệp vụ**:

~~~java
boolean adult = true;
boolean verified = false;
boolean admin = true;

boolean ruleA = adult && (verified || admin);
boolean ruleB = (adult && verified) || admin;

System.out.println(ruleA); // true
System.out.println(ruleB); // true
~~~

Với bộ dữ liệu trên, cả hai đều true; nhưng **không đồng nghĩa** chúng luôn tương đương. Hãy xét `adult = false`, `verified = false`, `admin = true`: `ruleA` là false còn `ruleB` là true. Nếu điều kiện tuổi bắt buộc với mọi người, chỉ `adult && (verified || admin)` phản ánh đúng yêu cầu.

Toán tử `&&` và `||` **đánh giá ngắn mạch**:

~~~java
Integer age = null;
boolean validAge = (age != null) && (age >= 18) && (age <= 65);
System.out.println(validAge); // false, không unbox null
~~~

Nếu `age == null`, vế sau không chạy, tránh `NullPointerException`. Đừng thay `&&` bằng `&` nếu mục đích là bỏ qua phép kiểm tra tiếp theo khi điều kiện trước thất bại.

## 6. Validate cấu hình biên trước khi dùng

Một miền `[min, max]` chỉ hợp lệ nếu `min <= max`. Nếu API nhận giới hạn đảo ngược:

~~~java
int min = 100;
int max = 50;
~~~

thì biểu thức `value >= min && value <= max` trả false cho mọi `int`, **che giấu lỗi cấu hình**.

Tạo hàm có hợp đồng rõ:

~~~java
static boolean inClosedRange(int value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min > max");
    }
    return value >= min && value <= max;
}
~~~

**Hai lựa chọn khác nhau:**

1. **Giới hạn sai là lỗi cấu hình:** ném `IllegalArgumentException`.
2. **Khoảng rỗng là trạng thái có chủ đích:** có thể trả false, nhưng phải ghi rõ trong hợp đồng.

Bài này chọn cách đầu. Với miền `[min, max)`, nếu `min == max`, miền rỗng theo định nghĩa; không nhất thiết là lỗi — hãy quyết định phù hợp với API. Trong ví dụ Java đầy đủ, khoảng nửa mở cho phép hai biên bằng nhau và luôn trả false.

## 7. Không kiểm tra miền số nguyên bằng phép trừ dễ tràn

Dễ gặp cách viết:

~~~java
// KHÔNG NÊN:
// value - min >= 0 && max - value >= 0
~~~

Với `int`, phép trừ có thể **overflow** trước khi so sánh. Ví dụ:

~~~java
int value = Integer.MAX_VALUE;
int min = -1;

System.out.println(value - min); // -2147483648: tràn int
~~~

Trong khi đó so sánh trực tiếp:

~~~java
boolean atLeastMin = value >= min;
System.out.println(atLeastMin); // true
~~~

đúng với miền giá trị nguyên mà không thực hiện phép trừ có nguy cơ overflow.

**Dùng so sánh trực tiếp** cho điều kiện miền; nếu thực sự cần tính độ dài khoảng, hãy cân nhắc chuyển rộng **trước phép trừ**:

~~~java
long width = (long) max - (long) min;
~~~

Đừng gán một kết quả trừ int đã tràn sang long rồi mong số được sửa lại.

## 8. Số thực: `NaN`, Infinity và lựa chọn miền hợp lệ

Với `double`:

~~~java
double value = Double.NaN;

boolean inside = value >= 0.0 && value <= 1.0;
boolean naivelyOutside = value < 0.0 || value > 1.0;

System.out.println(inside);         // false
System.out.println(naivelyOutside); // false
~~~

Cả hai đều false vì mọi phép so sánh thứ tự (`<`, `<=`, `>`, `>=`) có toán hạng NaN đều false. Nếu chỉ kiểm tra `outside` rồi suy rằng `!outside` là hợp lệ, NaN **có thể lọt qua**.

Nếu miền dữ liệu cho phép **chỉ số hữu hạn**, dùng:

~~~java
static boolean inFiniteClosedRange(
        double value, double min, double max) {
    if (!Double.isFinite(min) || !Double.isFinite(max) || min > max) {
        throw new IllegalArgumentException("invalid floating bounds");
    }
    return Double.isFinite(value) && value >= min && value <= max;
}
~~~

Ở đây:

- `min`/`max` phải hữu hạn và theo đúng thứ tự.
- `value` là `NaN` hoặc Infinity → false.
- Cả `+0.0` và `-0.0` thỏa một miền đóng chứa 0.
- Các so sánh là so đúng **giá trị `double` đã biểu diễn**.

**Ranh giới số thực cần đặc tả rõ**: `0.1 + 0.2` trong double cho `0.30000000000000004`; vì vậy phép kiểm tra `value <= 0.3` trả false. Không tự mở rộng ngưỡng để làm kết quả “đẹp” nếu nghiệp vụ yêu cầu biên cứng. Với dữ liệu đo có dung sai thực tế, phải quy định và kiểm chứng **chính sách sai số** phù hợp; với giá trị thập phân đòi chính xác, cân nhắc `BigDecimal`.

## 9. `BigDecimal`: so miền theo giá trị thập phân

Với số tiền hoặc tỷ lệ cần so đúng decimal, dùng `BigDecimal.compareTo`:

~~~java
java.math.BigDecimal rate = new java.math.BigDecimal("0.30");
java.math.BigDecimal min = new java.math.BigDecimal("0.00");
java.math.BigDecimal max = new java.math.BigDecimal("1.00");

boolean valid = rate.compareTo(min) >= 0 && rate.compareTo(max) <= 0;
System.out.println(valid); // true
~~~

`compareTo` so **giá trị số**, không yêu cầu cùng scale. Ví dụ `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có `compareTo == 0`, nhưng `equals` có thể false do khác scale.

**Không khởi tạo BigDecimal từ `new BigDecimal(0.1)` nếu muốn chính xác giá trị decimal 0.1**. Tạo từ chuỗi `"0.1"` hoặc theo một đường chuyển đổi được đặc tả, và chuẩn hóa đơn vị/rounding theo nghiệp vụ.

## 10. Miền hợp lệ có nhiều khoảng hoặc vùng cấm

Ví dụ cho phép điểm nằm trong **`[1, 5]` hoặc `[10, 12]`**:

~~~java
boolean allowed =
        (score >= 1 && score <= 5)
        || (score >= 10 && score <= 12);
~~~

Dấu ngoặc giúp thể hiện hai khoảng được **nối bằng OR**. Nếu đã có hàm:

~~~java
boolean allowed =
        inClosedRange(score, 1, 5)
        || inClosedRange(score, 10, 12);
~~~

Ví dụ chỉ chấp nhận `[1, 10]` nhưng **loại trừ `[4, 6]`**:

~~~java
boolean allowed = inClosedRange(score, 1, 10)
        && !inClosedRange(score, 4, 6);
~~~

**Bảo đảm ý nghĩa tại biên:** nếu `score = 4` hoặc 6, điều kiện vùng cấm đóng trả true và toàn điều kiện trả false. Nếu muốn cấm chỉ `(4, 6)`, phải dùng toán tử `>` và `<` thay vì `>=`, `<=`.

## 11. Guard clause: tách validation khỏi xử lý

Thay vì nhồi điều kiện vào nhiều nhánh lồng nhau, một hàm có thể reject dữ liệu ngoài miền ngay đầu vào:

~~~java
static int requireAge(int age) {
    if (!inClosedRange(age, 18, 65)) {
        throw new IllegalArgumentException("age out of range");
    }
    return age;
}
~~~

Cách này giúp:

- Biên miền được kiểm tra ở **một nơi rõ ràng**.
- Code xử lý chính chỉ chạy sau khi input hợp lệ.
- Đặt test cho **giới hạn dưới, giới hạn trên và giá trị sát hai phía** dễ hơn.
- Phân biệt rõ **lỗi tham số** với kết quả hợp lệ có giá trị `0` hoặc `false`.

Với ứng dụng nhận dữ liệu người dùng, có thể trả đối tượng kết quả validation thay vì ném ngoại lệ; đây là lựa chọn giao diện API, không thay đổi toán tử so sánh cơ bản.

~~~mermaid
flowchart TD
    A["Nhận value, min, max"] --> B{"Giới hạn hợp lệ?"}
    B -- "Không" --> C["Báo lỗi cấu hình/đầu vào"]
    B -- "Có" --> D{"Kiểu số thực? Cần finite?"}
    D -- "Có" --> E{"Giá trị hữu hạn?"}
    E -- "Không" --> F["Từ chối giá trị"]
    E -- "Có" --> G{"Đạt hai điều kiện biên?"}
    D -- "Không" --> G
    G -- "Có" --> H["Hợp lệ"]
    G -- "Không" --> F
~~~

## 12. Bảng kiểm thử biên bắt buộc

Với miền đóng **`[10, 20]`**:

| Giá trị | Kết quả đúng | Lý do |
|---:|---|---|
| `9` | false | Ngay dưới biên |
| `10` | true | Bằng biên dưới |
| `11` | true | Bên trong |
| `20` | true | Bằng biên trên |
| `21` | false | Ngay trên biên |

Với miền nửa mở **`[0, 3)`** dành cho chỉ số:

| Giá trị | Kết quả đúng |
|---:|---|
| `-1` | false |
| `0` | true |
| `2` | true |
| `3` | false |

Ngoài các giá trị thông thường, nên kiểm tra:

- `Integer.MIN_VALUE`, `Integer.MAX_VALUE` và các mốc gần chúng.
- `min == max`, `min > max` theo hợp đồng hàm.
- `null` với wrapper hoặc object đầu vào.
- `Double.NaN`, hai dấu Infinity và signed zero nếu dùng floating-point.
- Giá trị rất gần biên floating-point do làm tròn.
- Các miền bị nối `||` hoặc loại trừ bằng `!`.

## 13. Chương trình Java 17 hoàn chỉnh — chạy được bằng CLI

Tạo đúng file **`RangeConditionDemo.java`**:

~~~java
import java.math.BigDecimal;

public final class RangeConditionDemo {
    private RangeConditionDemo() {}

    static boolean inClosedRange(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        return value >= min && value <= max;
    }

    static boolean inOpenRange(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        return value > min && value < max;
    }

    static boolean inHalfOpenRange(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        return value >= min && value < max;
    }

    static boolean inFiniteClosedRange(
            double value, double min, double max) {
        if (!Double.isFinite(min) || !Double.isFinite(max)
                || min > max) {
            throw new IllegalArgumentException("invalid floating bounds");
        }
        return Double.isFinite(value)
                && value >= min && value <= max;
    }

    static int requireAge(int age) {
        if (!inClosedRange(age, 18, 65)) {
            throw new IllegalArgumentException("age out of range");
        }
        return age;
    }

    public static void main(String[] args) {
        System.out.println("closed lower="
                + inClosedRange(10, 10, 20));
        System.out.println("closed upper="
                + inClosedRange(20, 10, 20));
        System.out.println("closed below="
                + inClosedRange(9, 10, 20));
        System.out.println("closed above="
                + inClosedRange(21, 10, 20));

        System.out.println("open lower="
                + inOpenRange(10, 10, 20));
        System.out.println("open middle="
                + inOpenRange(15, 10, 20));
        System.out.println("half open start="
                + inHalfOpenRange(0, 0, 3));
        System.out.println("half open end="
                + inHalfOpenRange(3, 0, 3));
        System.out.println("half open empty="
                + inHalfOpenRange(3, 3, 3));

        int score = 4;
        boolean union = inClosedRange(score, 1, 5)
                || inClosedRange(score, 10, 12);
        System.out.println("union accepted=" + union);

        score = 7;
        boolean gap = inClosedRange(score, 1, 5)
                || inClosedRange(score, 10, 12);
        System.out.println("union gap=" + gap);

        boolean excluded = inClosedRange(score, 1, 10)
                && !inClosedRange(score, 4, 6);
        System.out.println("exclude forbidden=" + excluded);
        System.out.println("negative accepted="
                + inClosedRange(-2, -5, 0));
        System.out.println("near int max="
                + inClosedRange(Integer.MAX_VALUE,
                        Integer.MAX_VALUE - 1, Integer.MAX_VALUE));

        int value = Integer.MAX_VALUE;
        int min = -1;
        System.out.println("unsafe subtraction=" + (value - min));
        System.out.println("direct comparison=" + (value >= min));

        double computed = 0.1 + 0.2;
        System.out.println("floating upper strict="
                + inFiniteClosedRange(computed, 0.0, 0.3));
        System.out.println("floating inside="
                + inFiniteClosedRange(computed, 0.0, 0.4));
        System.out.println("NaN accepted="
                + inFiniteClosedRange(Double.NaN, 0.0, 1.0));
        System.out.println("Infinity accepted="
                + inFiniteClosedRange(Double.POSITIVE_INFINITY, 0.0, 1.0));
        System.out.println("negative zero accepted="
                + inFiniteClosedRange(-0.0, 0.0, 1.0));

        double nan = Double.NaN;
        System.out.println("naive NaN outside="
                + (nan < 0.0 || nan > 1.0));
        System.out.println("validated NaN invalid="
                + !inFiniteClosedRange(nan, 0.0, 1.0));

        BigDecimal rate = new BigDecimal("0.30");
        BigDecimal low = new BigDecimal("0.00");
        BigDecimal high = new BigDecimal("1.00");
        boolean validDecimal = rate.compareTo(low) >= 0
                && rate.compareTo(high) <= 0;
        System.out.println("decimal within=" + validDecimal);

        Integer nullableAge = null;
        boolean validNullableAge = nullableAge != null
                && inClosedRange(nullableAge, 18, 65);
        System.out.println("nullable age=" + validNullableAge);

        int denominator = 0;
        boolean guarded = denominator != 0
                && 10 / denominator > 1;
        System.out.println("short circuit guard=" + guarded);

        System.out.println("age valid=" + requireAge(20));
        try {
            requireAge(17);
        } catch (IllegalArgumentException ex) {
            System.out.println("age invalid=" + ex.getMessage());
        }
        try {
            inClosedRange(10, 20, 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("bad integer bounds=" + ex.getMessage());
        }
        try {
            inFiniteClosedRange(0.5, 1.0, 0.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("bad floating bounds=" + ex.getMessage());
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal mở tại thư mục chứa file; không cần Maven, Gradle hoặc thư viện bên ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 RangeConditionDemo.java
java -cp . RangeConditionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\RangeConditionDemo.java
java -cp . RangeConditionDemo
~~~

**Exact expected stdout:**

~~~text
closed lower=true
closed upper=true
closed below=false
closed above=false
open lower=false
open middle=true
half open start=true
half open end=false
half open empty=false
union accepted=true
union gap=false
exclude forbidden=true
negative accepted=true
near int max=true
unsafe subtraction=-2147483648
direct comparison=true
floating upper strict=false
floating inside=true
NaN accepted=false
Infinity accepted=false
negative zero accepted=true
naive NaN outside=false
validated NaN invalid=true
decimal within=true
nullable age=false
short circuit guard=false
age valid=20
age invalid=age out of range
bad integer bounds=min > max
bad floating bounds=invalid floating bounds
~~~

### Giải thích các nhóm kết quả

1. **Khoảng đóng/mở/nửa mở:** `[10,20]` lấy cả 10 và 20, `(10,20)` không lấy 10, `[0,3)` lấy 0 nhưng loại 3.
2. **Hai khoảng và vùng cấm:** `||` diễn đạt hợp của hai miền, còn `&& !(...)` loại một miền con.
3. **Số âm và cận lớn:** so sánh trực tiếp vẫn đúng; `value-min` trên `int` có thể tràn và tạo giá trị sai.
4. **Floating-point:** `0.1 + 0.2` lớn hơn literal `0.3` một chút; hàm finite-only từ chối NaN và Infinity.
5. **NaN:** hai phép kiểm tra `nan < min`, `nan > max` đều false; cần chính sách kiểm tra tính hữu hạn trước.
6. **Decimal:** `BigDecimal.compareTo` kiểm tra giá trị thập phân chính xác.
7. **Wrapper và short-circuit:** guard `null`/mẫu số 0 ngăn các phép toán nguy hiểm ở vế sau.
8. **Guard clauses:** trả giá trị hợp lệ hoặc báo ngoại lệ có thông điệp rõ khi giá trị/biên không hợp lệ.

## 14. Lỗi thường gặp và cách sửa

| Lỗi hoặc ngộ nhận | Vấn đề | Cách đúng |
|---|---|---|
| `min <= x <= max` | Java không có so sánh dây chuyền | `x >= min && x <= max` |
| `x >= min || x <= max` để kiểm tra trong khoảng | `||` chỉ yêu cầu một vế đúng | Dùng `&&` |
| `x < min && x > max` để kiểm tra ngoài khoảng | Không thể cùng đúng nếu min ≤ max | Dùng `||` |
| Dùng `<= length` cho index mảng | Truy cập index bằng length vượt giới hạn | Dùng `index < length` |
| Quên xét biên đầu và biên cuối | Off-by-one | Test sát hai biên |
| Không kiểm tra `min > max` | Lỗi cấu hình bị che thành false | Validate giới hạn |
| `x - min >= 0` thay cho `x >= min` | Integer subtraction có thể overflow | So sánh trực tiếp |
| `! (x < min || x > max)` để duyệt double mà không xét NaN | NaN làm hai phép so false, phủ định cho true | `Double.isFinite(x)` và kiểm tra trong miền |
| Xem Infinity là dữ liệu đo hợp lệ | Infinity không hữu hạn | Chính sách chấp nhận rõ ràng |
| Dùng biên double 0.3 rồi mong mọi phép tính gần 0.3 đều lọt | Sai số nhị phân | Dung sai có cơ sở hoặc `BigDecimal` |
| Dùng `BigDecimal.equals` để so giá trị decimal mọi scale | `equals` còn xét scale | `compareTo` |
| Dùng `&` thay `&&` để guard null | `&` đánh giá cả hai vế | `&&` |
| Gộp nhiều nhóm `&&`/`||` không có ngoặc | Dễ hiểu sai logic | Đặt ngoặc theo quy tắc nghiệp vụ |
| Cắt `double` thành `int` rồi mới kiểm tra miền | Mất phần lẻ, có thể chấp nhận nhầm | Validate đúng kiểu trước chuyển đổi |

## 15. Bài tập có đáp án

### Bài A — khoảng đóng

Kiểm tra `score` từ 0 tới 100, **lấy hai biên**.

~~~java
boolean valid = score >= 0 && score <= 100;
~~~

**Đáp án:** với `score = 0` hoặc `100`, true; `-1` hoặc `101`, false.

### Bài B — chỉ số mảng

Mảng có `length = 5`. Viết điều kiện cho index hợp lệ.

~~~java
boolean validIndex = index >= 0 && index < 5;
~~~

**Đáp án:** `0..4` là hợp lệ; `-1` và `5` không hợp lệ.

### Bài C — ngoài khoảng

Viết điều kiện để reject tuổi **ngoài `[18,65]`**.

~~~java
boolean rejected = age < 18 || age > 65;
~~~

**Đáp án:** với tuổi 17 hoặc 66, true; tuổi 18 hoặc 65, false.

### Bài D — khoảng rỗng

~~~java
System.out.println(inHalfOpenRange(5, 5, 5));
~~~

**Đáp án:** `false`, vì `[5,5)` rỗng. Hàm ví dụ cho phép `min == max` trong miền nửa mở.

### Bài E — NaN

~~~java
double x = Double.NaN;
boolean outside = x < 0 || x > 1;
System.out.println(outside);
~~~

**Đáp án:** `false`, nhưng **không có nghĩa x hợp lệ**. Cần reject NaN tường minh bằng `Double.isFinite(x)` hoặc `Double.isNaN(x)` theo chính sách.

### Bài F — hai miền được phép

Chấp nhận `x` trong `[1,3]` **hoặc** `[7,9]`.

~~~java
boolean accepted =
        (x >= 1 && x <= 3)
        || (x >= 7 && x <= 9);
~~~

**Đáp án:** 1, 3, 7, 9 đều được chấp nhận; 4, 5, 6 bị từ chối.

### Bài G — lỗi overflow khi so miền

~~~java
int value = Integer.MAX_VALUE;
int min = -1;
System.out.println(value - min >= 0);
System.out.println(value >= min);
~~~

**Đáp án:**

~~~text
false
true
~~~

Dòng đầu bị tràn khi trừ int; dòng sau dùng so sánh trực tiếp và chính xác.

## 16. Checklist và kết luận

- [ ] Chọn rõ khoảng đóng, mở, nửa mở và ý nghĩa tại biên.
- [ ] Dùng `&&` để yêu cầu đồng thời đạt biên dưới và biên trên.
- [ ] Dùng `||` để nhận diện ngoài khoảng hoặc hợp nhiều khoảng.
- [ ] Không viết `min <= value <= max` trong Java.
- [ ] Validate `min <= max` theo hợp đồng API.
- [ ] Kiểm thử `min - 1`, `min`, trong miền, `max`, `max + 1` khi không overflow.
- [ ] Với index mảng, dùng miền `[0,length)`.
- [ ] Tránh công thức kiểm tra miền số nguyên dùng phép trừ có thể overflow.
- [ ] Với `double`, có chính sách rõ cho NaN, Infinity và sai số tại biên.
- [ ] Không dùng tolerance tùy tiện để vượt qua ràng buộc an toàn.
- [ ] Với decimal exact, xét `BigDecimal.compareTo`.
- [ ] Dùng guard `null` với wrapper và `&&` để tránh unboxing null.
- [ ] Đặt ngoặc giúp người đọc nhận ra các nhóm điều kiện nghiệp vụ.
- [ ] Chạy `RangeConditionDemo.java` bằng Java 17+ và đối chiếu từng dòng expected output.

**Kết luận:** Một điều kiện miền giá trị tốt phải **biểu đạt đúng tập giá trị cho phép**, xử lý rõ hai biên, dùng đúng `&&`/`||`, tránh overflow và định nghĩa chính sách cho dữ liệu số thực bất thường. Hãy đặt tên cho điều kiện quan trọng, validate giới hạn và kiểm thử ngay tại ranh giới để code Java 17+ dễ đọc, dễ bảo trì và không chấp nhận nhầm dữ liệu.