# Xây dựng hàm so sánh gần bằng có hợp đồng rõ ràng trong Java

## 1. Mục tiêu thực hành

Trong Java, `float` và `double` dùng biểu diễn nhị phân hữu hạn theo IEEE 754. Nhiều số thập phân quen thuộc, chẳng hạn `0.1` hoặc `0.2`, không biểu diễn chính xác bằng một số bit hữu hạn. Vì vậy phép tính:

```java
double value = 0.1 + 0.2;
System.out.println(value);       // 0.30000000000000004
System.out.println(value == 0.3); // false
```

cho kết quả khác trực giác thập phân. Đôi khi bài toán cho phép xem hai giá trị sai lệch rất nhỏ là **gần bằng nhau** (*approximately equal*), chẳng hạn khi đối chiếu kết quả đo đạc, mô phỏng hoặc phép tính dấu phẩy động có dung sai đã được quy định.

Tuy nhiên, câu “gần bằng nếu chênh lệch đủ nhỏ” chưa đủ để triển khai: **đủ nhỏ so với cái gì, khi dữ liệu gần 0 thì sao, có tính vô cực/NaN không, và những giá trị không hợp lệ được xử lý thế nào?** Một hàm so sánh cần **hợp đồng** (*contract*) tường minh và bộ kiểm thử sát biên.

Bài này xây dựng một hàm Java 17+ cho `double` với **absolute tolerance** (ngưỡng sai lệch tuyệt đối) và **relative tolerance** (ngưỡng sai lệch tương đối), xử lý `NaN`, `Infinity`, `+0.0`/`-0.0`, tránh lỗi tràn trong phép trừ; đồng thời chỉ ra giới hạn toán học khiến hàm gần bằng **không** thay thế được `equals()` hoặc `compareTo()`.

## 2. Phải chọn công thức và ý nghĩa trước khi viết code

Gọi hai số cần so sánh là \(a\) và \(b\). Với các số hữu hạn, ta định nghĩa:

\[
\Delta = |a-b|,\qquad
S = \max(|a|,|b|),\qquad
T = \max(\mathrm{absTol}, \mathrm{relTol}\times S)
\]

Hàm trả về **`true` nếu và chỉ nếu** \(\Delta \le T\), sau khi xử lý các ngoại lệ `NaN`, vô cực và bằng nhau chính xác theo hợp đồng.

- **`absTol`:** sai số tuyệt đối tối đa theo **đơn vị của đại lượng**. Ví dụ kết quả đo bằng mét có thể cho phép lệch `0.001` mét.
- **`relTol`:** tỷ lệ sai lệch cho phép theo độ lớn của hai giá trị, ví dụ `1e-9` là một phần trên một tỷ. Đây là tỷ lệ **không có đơn vị**.
- **`max(absTol, relTol × S)`:** cho phép sai lệch theo **một trong hai điều kiện** (absolute hoặc relative). Đây là **lựa chọn chính sách trong bài**, không phải định nghĩa duy nhất của “gần bằng”.

Cách chọn `max` đồng nghĩa:

```text
abs(a - b) <= absTol
                 HOẶC
abs(a - b) <= relTol * max(abs(a), abs(b))
```

Một số thư viện dùng `absTol + relTol × S` hoặc dạng khác. Hai công thức không giống nhau gần ranh giới, nên không thể thay thế tùy tiện nếu chưa cập nhật hợp đồng và test.

### Vì sao cần kết hợp cả hai loại dung sai?

Chỉ có **sai số tuyệt đối**:

```text
abs(a-b) <= 0.001
```

hợp lý nếu tất cả kết quả có một thang đo cố định, nhưng có thể quá chặt đối với những số cỡ một tỷ và quá lỏng đối với những số cỡ một phần tỷ.

Chỉ có **sai số tương đối**:

```text
abs(a-b) <= 1e-9 * max(abs(a), abs(b))
```

tự thay đổi theo độ lớn của giá trị, nhưng gần `0`, độ lớn `S` tiến về `0` và ngưỡng tương đối cũng tiến về `0`. Do đó cần một ngưỡng tuyệt đối có ý nghĩa nghiệp vụ để quyết định “đủ gần 0”.

Ví dụ, `absTol = 1e-9`, `relTol = 0` coi `0.0` và `1e-12` là gần bằng. Còn `absTol = 0`, `relTol = 1e-9` chỉ có thể chấp nhận các giá trị đủ gần nhau theo tỷ lệ, không cung cấp “vùng an toàn” tuyệt đối quanh 0.

## 3. Hợp đồng của hàm sẽ triển khai

Hàm có chữ ký:

```java
static boolean nearlyEqual(
        double a, double b, double absTol, double relTol)
```

Hợp đồng rõ ràng:

1. Hai tham số `a`, `b` có thể là bất kỳ giá trị `double`, bao gồm hữu hạn, `+0.0`, `-0.0`, hai vô cực và `NaN`.
2. `absTol` phải **hữu hạn và không âm**. Chấp nhận `0.0`; từ chối `NaN`, vô cực và mọi số âm.
3. `relTol` phải **hữu hạn và thuộc khoảng `[0, 1)`**. Ràng buộc nhỏ hơn 1 là một quyết định trong hợp đồng để relative tolerance luôn nhỏ hơn 100% độ lớn tham chiếu; ứng dụng thực tế nên chọn giá trị nhỏ hơn rất nhiều.
4. **`NaN` ở một trong hai toán hạng → `false`**, kể cả khi cả hai đều là NaN.
5. Nếu `a == b` theo so sánh primitive của Java → **`true`**. Do đó cùng một vô cực theo dấu trả `true` và `+0.0` gần bằng `-0.0`.
6. Nếu chỉ một toán hạng là vô cực, hoặc chúng là hai vô cực khác dấu → **`false`**. Không cố tính sai số hữu hạn cho vô cực.
7. Với hai số hữu hạn còn lại, tính \(\Delta\), \(S\), \(T\) theo công thức ở phần 2 và trả `true` khi \(\Delta \le T\). **Đúng bằng ngưỡng cũng được chấp nhận**.
8. Với tolerance không hợp lệ, ném `IllegalArgumentException` **trước khi xem dữ liệu**. Nghĩa là ngay cả `nearlyEqual(1, 1, NaN, 0)` vẫn ném lỗi: cấu hình sai không được âm thầm bỏ qua.

Ràng buộc dung sai và hành vi đối với special values là quyết định thiết kế. Một hệ thống khác có thể chọn coi NaN là lỗi đầu vào và ném exception, hoặc yêu cầu tất cả đầu vào đều hữu hạn. Điều quan trọng là **công khai chính sách** và kiểm thử chúng, chứ không để chúng phát sinh ngẫu nhiên từ các toán tử Java.

## 4. Cài đặt Java 17+: phiên bản có thể dùng và kiểm thử

Lưu toàn bộ file dưới tên **`NearlyEqualDemo.java`**:

```java
public class NearlyEqualDemo {

    /**
     * Approximate comparison by an absolute-or-relative tolerance:
     * |a - b| <= max(absTol, relTol * max(|a|, |b|)).
     *
     * absTol: finite, >= 0.
     * relTol: finite, 0 <= relTol < 1.
     * NaN: false; same-sign infinities: true;
     * other infinite pairs: false; +0 and -0: true.
     */
    public static boolean nearlyEqual(
            double a, double b, double absTol, double relTol) {

        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol)
                || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("invalid tolerances");
        }

        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }

        if (a == b) {
            return true;
        }

        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }

        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        double allowed = Math.max(absTol, relTol * scale);
        return difference <= allowed;
    }

    public static void main(String[] args) {
        System.out.println("0.1 + 0.2 ~= 0.3: "
                + nearlyEqual(0.1 + 0.2, 0.3, 1e-12, 0.0));

        System.out.println("large relative pass: "
                + nearlyEqual(
                        1_000_000_000.0, 1_000_000_001.0, 0.0, 1e-9));
        System.out.println("large relative fail: "
                + nearlyEqual(
                        1_000_000_000.0, 1_000_000_002.0, 0.0, 1e-9));
        System.out.println("near zero absolute: "
                + nearlyEqual(0.0, 1e-12, 1e-9, 0.0));

        System.out.println("zero tolerances require exact equality: "
                + nearlyEqual(1.0, Math.nextUp(1.0), 0.0, 0.0));
        System.out.println("one ulp accepted: "
                + nearlyEqual(
                        1.0, Math.nextUp(1.0), Math.ulp(1.0), 0.0));

        System.out.println("signed zeros: "
                + nearlyEqual(+0.0, -0.0, 0.0, 0.0));
        System.out.println("same infinities: "
                + nearlyEqual(
                        Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 0.0, 0.0));
        System.out.println("different infinities: "
                + nearlyEqual(
                        Double.POSITIVE_INFINITY,
                        Double.NEGATIVE_INFINITY, 0.0, 0.0));
        System.out.println("NaNs: "
                + nearlyEqual(Double.NaN, Double.NaN, 1.0, 0.1));

        System.out.println("overflowing difference: "
                + nearlyEqual(
                        Double.MAX_VALUE, -Double.MAX_VALUE,
                        Double.MAX_VALUE, 0.5));

        double sub = Double.MIN_VALUE;
        System.out.println("subnormal exact-only: "
                + nearlyEqual(0.0, sub, 0.0, 0.0));
        System.out.println("subnormal with absTol: "
                + nearlyEqual(0.0, sub, sub, 0.0));

        boolean ab = nearlyEqual(0.0, 0.75, 1.0, 0.0);
        boolean bc = nearlyEqual(0.75, 1.5, 1.0, 0.0);
        boolean ac = nearlyEqual(0.0, 1.5, 1.0, 0.0);
        System.out.println(
                "not transitive: " + ab + ", " + bc + ", " + ac);

        try {
            nearlyEqual(1.0, 1.0, Double.NaN, 0.0);
            System.out.println("invalid tolerance: accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid tolerance: rejected");
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac NearlyEqualDemo.java
java NearlyEqualDemo
```

Đầu ra:

```text
0.1 + 0.2 ~= 0.3: true
large relative pass: true
large relative fail: false
near zero absolute: true
zero tolerances require exact equality: false
one ulp accepted: true
signed zeros: true
same infinities: true
different infinities: false
NaNs: false
overflowing difference: false
subnormal exact-only: false
subnormal with absTol: true
not transitive: true, true, false
invalid tolerance: rejected
```

### Giải thích thứ tự xử lý

**Kiểm tra tolerance trước:** nếu `absTol` là `NaN` mà ta dùng trực tiếp `Math.max`, kết quả so sánh có thể bị ảnh hưởng khó hiểu. Điều tệ hơn là một nhánh xử lý giá trị bằng nhau có thể che giấu cấu hình sai. Vì vậy, validation là bước đầu.

**NaN trước toán tử bằng:** trong Java, `Double.NaN == Double.NaN` là `false`. Việc xét riêng cho biết rõ đây là chính sách, thay vì tình cờ phụ thuộc toán tử.

**Đúng bằng nhau trước kiểm tra vô cực:** `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` là `true`; hai số 0 khác dấu cũng `==`. Không nên lấy `Infinity - Infinity` rồi so sánh, vì hiệu như vậy có thể tạo `NaN`.

**Kiểm tra hữu hạn trước tính sai số:** nếu còn ít nhất một vô cực, `a != b` và không thể áp công thức cho hai số hữu hạn, hàm trả `false`.

**Tính ngưỡng rồi so sánh:** với hai số hữu hạn, hàm dùng `difference <= allowed`, chấp nhận cả trường hợp bằng đúng ngưỡng. `Math.max(Math.abs(a), Math.abs(b))` khiến kết quả **đối xứng** khi đổi chỗ hai toán hạng. Không dùng riêng `Math.abs(a)` làm mẫu số/thang đo vì khi đảo đối số có thể cho kết quả khác.

## 5. Vì sao có thể viết Math.abs(a - b) ở đây?

Một lỗi thường gặp là khẳng định hiệu hai số `double` hữu hạn luôn hữu hạn. Không đúng: với `a = Double.MAX_VALUE` và `b = -Double.MAX_VALUE`, biểu thức `a - b` **tràn thành `+Infinity`**, dù cả hai toán hạng đều hữu hạn.

Hàm trên kiểm soát trường hợp đó bằng hợp đồng cụ thể:

- `absTol` phải **hữu hạn**, nên không lớn hơn `Double.MAX_VALUE`.
- `relTol < 1` và `scale` hữu hạn, nên `relTol * scale` vẫn hữu hạn và không vượt `Double.MAX_VALUE`.
- Nếu `Math.abs(a-b)` thành `Infinity`, sai lệch thực lớn hơn miền hữu hạn của `double`, và **không thể nhỏ hơn hoặc bằng ngưỡng hữu hạn** đã chọn. Vì vậy `Infinity <= allowed` là `false` và phù hợp với chính sách này.

Điều này giải thích vì sao hàm **không cần giả vờ trừ chính xác bằng BigDecimal** cho mọi trường hợp. Tuy nhiên, các phép trừ dấu phẩy động vẫn có làm tròn. Nếu cần chứng minh chính xác ranh giới độ sai số tính theo số thực toán học, phải xem xét cách biểu diễn đầu vào và đặc tả bài toán; hàm trên có hợp đồng dựa trên các **giá trị double thực tế và phép tính double**.

Không dùng thay bằng biểu thức:

```java
Math.abs(a / b - 1.0) <= relTol
```

nếu chưa xử lý `b == 0`, dấu âm, underflow, overflow và tính đối xứng. Phép chia có thể không xác định hoặc tạo vô cực; chọn scale bằng `max(abs(a), abs(b))` là quy tắc rõ ràng hơn cho hợp đồng đã chọn.

## 6. Chọn ngưỡng dung sai từ miền bài toán

Các giá trị `1e-12`, `1e-9` trong chương trình là **giá trị minh họa**, không phải dung sai mặc định an toàn cho mọi hệ thống. Một ngưỡng phù hợp phải xuất phát từ ít nhất một trong các yếu tố:

- **Đơn vị và độ phân giải đầu vào:** thiết bị đo nhiệt độ có sai số ±0,1°C không cần dung sai `1e-15` °C.
- **Giới hạn sai số được nghiệm thu:** nếu hệ thống định nghĩa kết quả chênh không quá 0,01 đơn vị, `absTol = 0.01` có ý nghĩa nghiệp vụ cụ thể.
- **Độ lớn biến thiên:** kết quả có thể từ phần triệu tới hàng tỷ; `relTol` hữu ích khi sai số cho phép tỷ lệ với độ lớn.
- **Tích lũy lỗi của thuật toán:** sau nhiều phép cộng/nhân, sai số làm tròn có thể tích lũy tùy thuật toán, thứ tự phép tính và điều kiện số (*numerical conditioning*).
- **Nhu cầu xác nhận chính xác:** với tiền tệ hoặc dữ liệu định danh số nguyên, một ngưỡng gần bằng tùy ý có thể che giấu lỗi quan trọng.

### Ví dụ về ngưỡng tuyệt đối

Nếu hai cảm biến cùng đo chiều dài theo mét và yêu cầu “chênh tối đa `0.002` mét”, hàm có thể gọi:

```java
boolean close = nearlyEqual(measuredA, measuredB, 0.002, 0.0);
```

Đây là ngưỡng **định nghĩa bằng mét**, áp dụng đồng đều trên miền giá trị. Không nên dùng `0.002` nếu giá trị đang ở đơn vị milimét mà không đổi đơn vị tương ứng.

### Ví dụ về ngưỡng tương đối

Nếu yêu cầu “sai khác dưới một phần triệu so với độ lớn của giá trị”, có thể chọn `relTol = 1e-6` và một `absTol` nhỏ phù hợp khi gần 0. Với `a` và `b` khoảng một triệu, ngưỡng tương đối khi ấy khoảng 1 đơn vị; với giá trị cỡ một phần triệu, ngưỡng tương đối chỉ cỡ `1e-12`.

Công thức của bài sử dụng **`<=`** nên “dưới một phần triệu” cần được diễn đạt chính xác trong hợp đồng là **không vượt quá ngưỡng**. Nếu yêu cầu thật sự là “nhỏ hơn nghiêm ngặt”, phải đổi toán tử và sửa bài kiểm thử biên.

### Tolerance bằng 0

Khi `absTol = 0` và `relTol = 0`, hai số hữu hạn phải có hiệu tính bằng 0 để gần bằng; với các số finite thông thường, tương đương so sánh `==`. Trong chính sách đang dùng, `+0.0` và `-0.0` bằng nhau, hai vô cực cùng dấu bằng nhau, còn NaN không gần bằng chính nó.

Nếu yêu cầu **so sánh cùng mẫu bit**, dùng `Double.doubleToRawLongBits` để kiểm tra riêng; đó là hợp đồng khác hoàn toàn so với gần bằng về số học.

## 7. Kiểm thử theo lớp tương đương và giá trị biên

Một hàm so sánh gần bằng cần kiểm thử theo **hợp đồng**, không chỉ bằng ví dụ `0.1 + 0.2`. Các nhóm ca tối thiểu:

| Nhóm | Ví dụ | Kỳ vọng theo hợp đồng |
|---|---|---|
| Đúng bằng finite | `(1.0, 1.0, 0, 0)` | `true` |
| Sai lệch thập phân nhỏ | `(0.1+0.2, 0.3, 1e-12, 0)` | `true` |
| Vượt ngưỡng tuyệt đối | `(0, 0.02, 0.01, 0)` | `false` |
| Gần 0 | `(0, 1e-12, 1e-9, 0)` | `true` |
| Số lớn, ngưỡng tương đối đủ | `(1e9, 1e9+1, 0, 1e-9)` | `true` |
| Số lớn, ngưỡng tương đối thiếu | `(1e9, 1e9+2, 0, 1e-9)` | `false` |
| Không dung sai | `(1, Math.nextUp(1), 0, 0)` | `false` |
| Một ULP ở 1 | `(1, Math.nextUp(1), Math.ulp(1), 0)` | `true` |
| Hai zero có dấu | `(+0.0, -0.0, 0, 0)` | `true` |
| Hai vô cực dương | `(+∞, +∞, 0, 0)` | `true` |
| Vô cực khác dấu | `(+∞, -∞, 0, 0)` | `false` |
| NaN | `(NaN, NaN, 1, 0.1)` | `false` |
| Hiệu double tràn | `(MAX_VALUE, -MAX_VALUE, MAX_VALUE, 0.5)` | `false` |
| Subnormal sát 0 | `(0, MIN_VALUE, 0, 0)` | `false` |
| Subnormal có dung sai | `(0, MIN_VALUE, MIN_VALUE, 0)` | `true` |
| Tolerance không hợp lệ | `absTol = NaN`; `relTol = 1`; `absTol < 0` | Ném `IllegalArgumentException` |

`Double.MIN_VALUE` là **số `double` dương nhỏ nhất khác 0** (subnormal), không phải số âm có độ lớn lớn nhất. `Double.MAX_VALUE` là số hữu hạn dương lớn nhất. Không nhầm hai hằng số này khi thiết kế test.

### Kiểm tra tính đối xứng

Hàm được định nghĩa đối xứng: `nearlyEqual(a,b,t,r)` phải bằng `nearlyEqual(b,a,t,r)` với cùng tolerance hợp lệ. Việc lấy `max(abs(a),abs(b))` giúp giữ thuộc tính này. Nếu dùng `relTol * abs(a)` riêng và xem `a` là tham chiếu, đó là **so sánh có hướng**; cũng có ứng dụng hợp lệ nhưng phải ghi rõ và không gọi là quan hệ đối xứng.

### Kiểm tra gần biên với nextUp và nextDown

Dùng `Math.nextUp(x)` và `Math.nextDown(x)` để lấy giá trị `double` liền kề trong thứ tự số thực có thể biểu diễn, thay vì tự cộng `1e-16` rồi tưởng rằng số thực sẽ đổi. `Math.ulp(x)` cho khoảng cách ULP tại vùng đó (với chú ý về vị trí sát ranh giới số mũ).

Ví dụ `Math.nextUp(1.0)` khác `1.0` một bước `Math.ulp(1.0)`. Với `absTol = 0` và `relTol = 0`, hàm phải trả `false`; với `absTol = Math.ulp(1.0)` thì trả `true`.

**Đừng mặc định N ULP giống một sai số nghiệp vụ cố định.** ULP đo theo cấu trúc biểu diễn nhị phân và thay đổi theo độ lớn; việc chọn ULP làm tiêu chí phải xuất phát từ đặc điểm thuật toán, không thay thế vô điều kiện ngưỡng tuyệt đối/tương đối.

## 8. Những tính chất toán học và giới hạn quan trọng

### Gần bằng không có tính bắc cầu

Một quan hệ bằng nhau theo nghĩa thông thường cần tính bắc cầu: nếu A bằng B và B bằng C thì A phải bằng C. Gần bằng theo tolerance **không có** tính chất này.

Với `absTol = 1.0` và `relTol = 0`:

```text
a = 0.00
b = 0.75
c = 1.50

|a - b| = 0.75 <= 1.0 => gần bằng
|b - c| = 0.75 <= 1.0 => gần bằng
|a - c| = 1.50 >  1.0 => KHÔNG gần bằng
```

Do đó `nearlyEqual(a,b) == true` và `nearlyEqual(b,c) == true` không suy ra `nearlyEqual(a,c) == true`. Hàm trong bài cũng **không phản xạ đối với NaN**, vì chính sách cố ý coi mọi so sánh có NaN là false.

**Hệ quả:** không dùng so sánh gần bằng làm cơ sở triển khai `Object.equals()`/`hashCode()` cho đối tượng đưa vào `HashSet` hoặc làm khóa `HashMap`. Cũng không tự dùng nó để trả `0` trong `Comparator` của `TreeSet`/`TreeMap` hoặc thuật toán sắp xếp: comparator cần hợp đồng thứ tự nhất quán; không bắc cầu có thể gây lỗi hoặc hành vi khó đoán.

Nếu cần **gom nhóm** những số theo độ phân giải cố định, hãy chọn quy tắc phân vùng/quantization có định nghĩa ranh giới rõ ràng, hoặc xây thuật toán clustering với hợp đồng riêng. Những kỹ thuật đó có ngữ nghĩa khác và có thể gây khác biệt tại ranh giới nhóm.

### Ngưỡng phụ thuộc giá trị so sánh

Với công thức `max(absTol, relTol × max(abs(a), abs(b)))`, một giá trị `b` rất lớn có thể làm relative tolerance lớn. Chẳng hạn `relTol = 0.5` cho phép sai lệch tới 50% độ lớn tham chiếu; về mặt số học hợp đồng vẫn nhất quán, nhưng phần lớn ứng dụng sẽ coi ngưỡng như vậy là quá rộng.

Giới hạn kỹ thuật `relTol < 1` ngăn cấu hình bằng hoặc vượt 100%, **không chứng minh** dung sai nhỏ phù hợp. Cần giới hạn riêng theo miền nghiệp vụ: ví dụ tối đa `1e-6` nếu hợp đồng yêu cầu.

### Không có “một epsilon cho mọi double”

`Double.MIN_VALUE` không phải epsilon thích hợp cho mọi phép tính; khoảng cách giữa các giá trị biểu diễn được tăng theo độ lớn. `Math.ulp(1.0)` phản ánh bước gần 1, còn `Math.ulp(1e12)` lớn hơn nhiều. Một ngưỡng `1e-9` có thể quá nghiêm ngặt ở miền giá trị lớn nhưng lại quá dễ dãi ở miền rất nhỏ. Chính sách thực tế phải xét đơn vị, số phép toán, độ nhạy của thuật toán và mức sai khác có thể chấp nhận.

### Precision là khái niệm khác với tolerance

`double` có precision nhị phân hữu hạn (53 bit có nghĩa đối với số chuẩn hóa); đây là giới hạn biểu diễn. `absTol` và `relTol` là **chính sách chấp nhận sai khác** khi so sánh kết quả. Chúng có liên quan khi phân tích sai số nhưng không phải một khái niệm.

Ví dụ một phép toán kém điều kiện có thể khuếch đại sai số đầu vào lớn hơn nhiều ULP. Dung sai cho kết quả phải dựa trên sai số hợp lệ của **toàn thuật toán**, chứ không đơn giản lấy cố định `Math.ulp(1.0)` ở mọi nơi.

## 9. Khi nào cần BigDecimal hoặc so sánh chính xác?

Với **tiền, tỷ lệ được quy định bằng số chữ số thập phân, hoặc quy tắc làm tròn pháp lý/nghiệp vụ**, so sánh `double` gần bằng có thể che giấu sự khác biệt cần được phát hiện. Nếu dữ liệu là thập phân chính xác, nên cân nhắc `BigDecimal` dựng từ chuỗi:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.00");
BigDecimal b = new BigDecimal("1.0");

// So sánh giá trị số học; không coi scale là điều kiện bằng:
boolean sameNumericValue = a.compareTo(b) == 0; // true

// Nếu quy định độ lệch thập phân tối đa là 0.01:
BigDecimal tolerance = new BigDecimal("0.01");
boolean withinAbsoluteTolerance =
        a.subtract(b).abs().compareTo(tolerance) <= 0; // true
```

Đây là **đoạn mã minh họa dùng trong phương thức hoặc lớp**; nó không có `main()` độc lập. `BigDecimal.compareTo()` so sánh giá trị số học, còn `BigDecimal.equals()` còn xét scale; ví dụ `"1.00"` và `"1.0"` có giá trị bằng nhau nhưng `equals()` trả false.

Khi áp dụng dung sai với `BigDecimal`, cần đặt giới hạn giá trị/tài nguyên, xác định scale/precision, quy tắc làm tròn nếu các phép tính không hữu hạn trong biểu diễn thập phân, và trường hợp làm tròn trước hay sau khi so sánh. Không nên âm thầm ép `BigDecimal` về `double` chỉ để sử dụng hàm `nearlyEqual` khi yêu cầu đòi độ chính xác thập phân.

Nếu so sánh **số nguyên** (`int`, `long`, `BigInteger`), giá trị đã biểu diễn chính xác theo miền kiểu; thường so sánh bằng chính xác phù hợp hơn. Nếu muốn cho phép lệch N đơn vị nguyên, hãy định nghĩa phạm vi rõ ràng và chú ý overflow khi tính hiệu, không tự chuyển sang `double` với các số nguyên lớn hơn \(2^{53}\).

## 10. Các sai lầm triển khai phổ biến

### Chỉ viết Math.abs(a - b) < 1e-9

Cách này không nói rõ miền đơn vị, loại trừ trường hợp **bằng đúng ngưỡng** vì dùng `<`, không có tương đối theo độ lớn và không mô tả NaN/vô cực. Nó có thể đủ cho một phép kiểm tra nhỏ đã giới hạn thang đo, nhưng không phải API dùng chung có hợp đồng đầy đủ.

### Dùng relTol * a thay vì một thang đo đối xứng

Nếu dùng riêng `a` làm mốc, đảo tham số có thể đổi kết quả. Có bài toán chủ ý phân biệt **giá trị mong đợi** và **giá trị đo được**; khi đó dùng sai số tương đối theo expected là hợp lệ nếu hợp đồng nêu rõ vai trò từng đối số. Nhưng nếu tên hàm hàm ý so sánh đối xứng hai số, dùng `max(abs(a), abs(b))` giúp tính chất đó rõ ràng.

### Dùng Infinity làm tolerance để “bật tắt” kiểm tra

Nếu `absTol = Infinity`, các trường hợp xa nhau có thể được coi gần bằng vô điều kiện và gây kết quả bất ngờ với special values. Hàm bài này **từ chối tolerance vô hạn và NaN** để tránh cấu hình che giấu lỗi. Muốn bỏ một loại điều kiện, dùng giá trị `0` cho loại đó và chọn rõ loại còn lại theo nghiệp vụ.

### Quên quy tắc NaN và signed zero

`Double.NaN == Double.NaN` là false, nhưng `Double.compare(Double.NaN, Double.NaN) == 0` có ngữ nghĩa khác. `+0.0 == -0.0` là true, dù `Double.doubleToRawLongBits` cho hai mẫu bit khác nhau. Hàm gần bằng nên quy định **ngữ nghĩa số học** hay **ngữ nghĩa bit** từ đầu.

### Không chặn hiệu số tràn

Hai số hữu hạn có thể cho hiệu vô cực. Nếu viết một công thức tương đối có phép chia trên hiệu, hoặc dùng một tolerance vô hạn, lỗi có thể khó nhận thấy. Trong hàm bài này, `difference == Infinity` tự cho kết quả false vì `allowed` hữu hạn, và điều đó có lý do từ hợp đồng `relTol < 1`.

### Kiểm tra trung bình hai số để lấy scale

Viết `scale = Math.abs((a+b)/2)` có thể bị overflow ở `a+b`, hoặc gần 0 khi hai giá trị lớn nhưng trái dấu, khiến ngưỡng trở nên sai lệch. `max(abs(a),abs(b))` tránh phép cộng trung gian và giữ tính đối xứng theo định nghĩa đã chọn.

### Làm tròn chuỗi rồi so sánh

Định dạng `String.format("%.2f", value)` chỉ kiểm soát **hiển thị**, có thể làm hai số khác nhau cùng trông giống nhau hoặc biến đổi theo locale. So sánh chuỗi đã định dạng không thể thay thế hợp đồng số học về tolerance; nếu nghiệp vụ yêu cầu làm tròn về 2 chữ số thập phân, phải định nghĩa đúng phép làm tròn và thời điểm thực hiện trước khi so sánh.

### Áp dụng cho dữ liệu đã mất precision mà không biết

Một số `long` lớn có thể mất chữ số khi chuyển thành `double`. Lúc đó `nearlyEqual` đang so sánh **hai giá trị double sau chuyển đổi**, không khôi phục dữ liệu nguyên gốc. Tương tự, số tiền đi qua `double` có thể đã mất thông tin thập phân chính xác. Hãy xác nhận nguồn dữ liệu trước khi chọn cách so sánh.

## 11. Bài tập áp dụng và tiêu chí nghiệm thu

Giả sử một bộ kiểm thử số học phải chấp nhận sai lệch tối đa `0.001` theo đơn vị của kết quả, hoặc `1e-8` theo độ lớn của kết quả, tùy điều kiện nào cho ngưỡng lớn hơn. Theo hợp đồng đã chọn, lời gọi là:

```java
boolean accepted = nearlyEqual(actual, expected, 0.001, 1e-8);
```

Để sử dụng trong ứng dụng, trước tiên phải làm rõ ý nghĩa của `actual` và `expected`, đơn vị đo, cách lấy giá trị mong đợi và liệu ngưỡng **bằng đúng ranh giới** có chấp nhận hay không. Hàm đang định nghĩa so sánh **đối xứng** (đổi `actual`/`expected` không đổi kết quả). Nếu nghiệm thu yêu cầu “sai lệch không quá X% của giá trị expected”, hãy xây một hàm khác theo đúng **mẫu số expected** và xử lý expected bằng 0, thay vì bí mật đổi công thức của hàm này.

Kiểm thử nghiệm thu nên có các nhóm:

1. Một kết quả đúng chính xác; một kết quả lệch nhỏ nhưng trong ngưỡng; một kết quả vượt ngưỡng.
2. Giá trị gần 0 để absolute tolerance có vai trò rõ ràng.
3. Giá trị rất lớn để relative tolerance chi phối.
4. Số âm, hai số trái dấu, `+0.0` và `-0.0`.
5. `NaN`, hai vô cực cùng dấu, vô cực khác dấu, một hữu hạn và một vô cực.
6. Dung sai không hợp lệ: âm, `NaN`, vô cực, `relTol = 1`.
7. Các số liền kề bằng `Math.nextUp`/`nextDown` và số subnormal sát 0.
8. Ví dụ mất tính bắc cầu để người dùng API hiểu rằng gần bằng **không phải quan hệ tương đương**.

### Câu hỏi tự kiểm tra

**1.** Vì sao `absTol = 0` và `relTol = 1e-9` chưa đủ cho một phép thử “gần bằng 0” có sai số đo tuyệt đối nhỏ? Vì ngưỡng tương đối `relTol × max(|a|,|b|)` tiến về 0 khi hai giá trị cùng tiến về 0; cần một `absTol` dựa trên độ phân giải thực tế.

**2.** `nearlyEqual(Double.POSITIVE_INFINITY, Double.POSITIVE_INFINITY, 0, 0)` trả gì? **`true`**, vì hai giá trị bằng chính xác theo chính sách, được xử lý trước phép trừ có thể tạo NaN.

**3.** Tại sao không dùng `nearlyEqual` trong `hashCode`/`equals` của khóa map? Vì quan hệ gần bằng theo ngưỡng **không bắc cầu**, không đáp ứng hợp đồng tương đương cần cho equality collections.

**4.** `nearlyEqual(0.0, Double.MIN_VALUE, 0, 0)` trả gì? **`false`**, vì một số là 0 còn số kia là subnormal dương khác 0. Nếu đặt `absTol = Double.MIN_VALUE` thì là **`true`**.

**5.** Nếu tính `a - b` từ hai số double hữu hạn mà kết quả thành vô cực, có chắc nên coi chúng gần bằng không? **Không**. Hợp đồng của bài từ chối cả hai số khác nhau khi sai lệch vượt ngưỡng hữu hạn; `difference <= allowed` sẽ false.

**Ghi nhớ:** Một hàm gần bằng tốt phải có **công thức, ý nghĩa tolerance, xử lý special values, quy tắc biên, giới hạn đầu vào và phép kiểm thử** được công bố. Hợp đồng bài này chọn \(|a-b| \le \max(\mathrm{absTol},\mathrm{relTol}\cdot\max(|a|,|b|))\) cho hai số hữu hạn, NaN luôn false, cùng vô cực true, signed zero true, tolerance bất hợp lệ ném lỗi. Hãy chọn các ngưỡng bằng yêu cầu thực tế và không dùng gần bằng thay thế bằng nhau chính xác trong cấu trúc dữ liệu.
