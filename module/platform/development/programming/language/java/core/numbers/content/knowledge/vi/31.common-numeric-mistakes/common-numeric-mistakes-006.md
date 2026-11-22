# Sai lầm: so sánh số thực bằng một epsilon tùy tiện

Khi lập trình với `double` hoặc `float`, nhiều người thay phép so sánh `a == b` bằng `Math.abs(a - b) < 1e-9` và cho rằng như vậy đã giải quyết mọi sai số dấu phẩy động. Đó là một sai lầm: **không tồn tại một epsilon tuyệt đối duy nhất phù hợp cho mọi giá trị, phép toán, đơn vị đo và yêu cầu nghiệp vụ**. Ngưỡng quá nhỏ khiến những kết quả đáng ra được coi là tương đương bị từ chối; ngưỡng quá lớn làm những giá trị thực sự khác nhau bị coi là bằng nhau. Với `NaN`, vô cực, số cực lớn hoặc phép trừ bị overflow, công thức đơn giản còn mang những cạm bẫy khác.

Bài học thuộc nhóm **Sai lầm thường gặp** của Java Core - Numbers. Mục tiêu là hiểu gốc rễ sai số IEEE 754, phân biệt so sánh **chính xác** với so sánh **gần bằng theo một ngưỡng có ý nghĩa**, dùng sai số tuyệt đối/tương đối/ULP đúng hoàn cảnh, xử lý dữ liệu đặc biệt và biết khi nào phải chọn `BigDecimal`.

## 1. Vì sao 0.1 + 0.2 có thể không bằng 0.3?

`float` và `double` là các kiểu dấu phẩy động nhị phân theo chuẩn IEEE 754. Phần lớn phân số thập phân như 0.1, 0.2 không có biểu diễn hữu hạn chính xác trong hệ cơ số 2. Java lưu giá trị nhị phân gần nhất có thể biểu diễn; mỗi phép tính có thể làm tròn theo quy tắc của kiểu số.

~~~java
double a = 0.1 + 0.2;
double b = 0.3;

System.out.println(a);      // 0.30000000000000004
System.out.println(b);      // 0.3
System.out.println(a == b); // false
~~~

Đây là đoạn minh họa dùng bên trong một phương thức Java. Kết quả `a == b` không sai theo ngôn ngữ: nó kiểm tra sự bằng nhau của **hai giá trị `double` đang được biểu diễn**, không kiểm tra "hai công thức toán học lý tưởng trên giấy có ý nghĩa tương đương hay không".

Một số phép tính tạo được kết quả chính xác, ví dụ những số nguyên nhỏ hoặc các phân số có mẫu là lũy thừa của 2. Vì vậy cũng không đúng khi khẳng định rằng `double` "không bao giờ dùng được `==`". Vấn đề là **định nghĩa bằng nhau mong muốn** và **nguồn gốc của từng giá trị**.

## 2. Epsilon tùy tiện gây hai loại lỗi trái ngược

Cách viết phổ biến:

~~~java
static boolean almostEqualWrong(double a, double b) {
    return Math.abs(a - b) < 1e-9;
}
~~~

Đoạn phương thức trên dùng một ngưỡng **sai số tuyệt đối** là `1e-9` trong đơn vị của dữ liệu. Nó có thể thích hợp nếu hệ thống **có hợp đồng độ chính xác tương ứng**; nó không tự nhiên đúng cho mọi bài toán.

**Lỗi 1 — ngưỡng quá chặt:** Giả sử hai kết quả tính lớn khác nhau khoảng `0.5` đơn vị do quá trình xấp xỉ đã được nghiệm thu cho phép sai số tối đa một đơn vị. Epsilon `1e-9` sẽ báo "khác nhau", dù yêu cầu miền ứng dụng có thể coi chúng tương đương.

**Lỗi 2 — ngưỡng quá rộng:** Nếu đang so sánh mức chênh lệch `1e-10` của một cảm biến có khả năng phân biệt đến `1e-12`, ngưỡng `1e-9` lại xóa đi một khác biệt có ý nghĩa. Tương tự, một ngưỡng tuyệt đối `0.01` được dùng để so sánh số tiền có thể vô tình xem hai khoản chênh nhau nhỏ hơn một xu là bằng nhau dù hợp đồng thanh toán yêu cầu giá trị chính xác.

Ngưỡng nào "rộng" hay "chặt" phụ thuộc ít nhất vào:
- **Đơn vị và độ lớn:** mét, micromét, giây, phần trăm hay đồng tiền không chung một mức sai số tuyệt đối hợp lý.
- **Sai số đầu vào:** độ phân giải thiết bị, phép đo hoặc nguồn dữ liệu.
- **Chuỗi phép toán:** số lần cộng/trừ/nhân/chia, độ điều kiện của bài toán, hiện tượng triệt tiêu chữ số (cancellation), nguy cơ overflow/underflow.
- **Hậu quả khi phân loại sai:** chỉ vẽ biểu đồ, cảnh báo cảm biến, quyết định phân quyền, tính tiền hay kiểm tra điều kiện dừng thuật toán.

**Một epsilon phải là phần của yêu cầu, không phải một con số chọn vì thấy quen thuộc trên mạng.**

## 3. Ba khái niệm cần tách riêng: machine epsilon, tolerance và ULP

| Thuật ngữ | Ý nghĩa | Cạm bẫy |
|---|---|---|
| Machine epsilon (với `double` là khoảng `2.22 × 10^-16` quanh 1.0) | Độ giãn biểu diễn tương đối quanh 1.0 của số dấu phẩy động nhị phân | Không phải ngưỡng đúng cho mọi phép toán |
| Absolute tolerance (`absTol`) | Chênh lệch tối đa tính theo **đơn vị dữ liệu** | Cần chọn theo ngữ cảnh, không scale theo độ lớn |
| Relative tolerance (`relTol`) | Tỷ lệ chênh lệch tối đa so với độ lớn tham chiếu | Cần chính sách gần 0 và tránh cho phép khác biệt lớn một cách vô lý |
| ULP (*unit in the last place*) | Khoảng cách lân cận giữa những giá trị có thể biểu diễn ở một thang độ lớn | Đo độ phân giải máy tại độ lớn đó, không đo độ đúng nghiệp vụ |

`Math.ulp(1.0)` trả khoảng `2.220446049250313E-16`; `Math.ulp(0.0)` trả `Double.MIN_VALUE` (khoảng `4.9E-324`, số dương *nhỏ nhất khác 0* của `double`). `Double.MIN_VALUE` **không** phải số âm nhỏ nhất: tên này dễ gây nhầm.

Không suy rằng một sai số bằng 1 hoặc 2 ULP luôn chấp nhận được. Một phép tính kém điều kiện có thể sai hơn nhiều ULP; ngược lại, hai số cách nhau chỉ một ULP cũng có thể là hai mã giá trị khác nhau cần giữ nguyên (ví dụ khóa dữ liệu hoặc trạng thái tính toán).

## 4. Sai số tuyệt đối: khi nào phù hợp?

Kiểm tra theo ngưỡng tuyệt đối:

\[
|a - b| \leq \varepsilon_{\text{abs}}
\]

`absTol` được đo cùng đơn vị với `a`, `b`. Ví dụ, một thiết bị đo chiều dài có hợp đồng **chấp nhận độ lệch không quá 0.01 mét** thì `absTol = 0.01` có thể là một quy tắc miền dữ liệu được lựa chọn có căn cứ.

~~~java
boolean within = Math.abs(actualMeters - targetMeters) <= 0.01;
~~~

Đoạn code trên là minh họa trong một phương thức; yêu cầu rằng `actualMeters` và `targetMeters` là các giá trị hữu hạn và `0.01` thật sự là sai lệch cho phép. Đừng chỉ áp dụng công thức này lên mọi `double` không kiểm tra đầu vào.

Ưu điểm: dễ hiểu, phù hợp gần 0 và có đơn vị rõ ràng. Hạn chế: một độ lệch `0.01` là lớn đối với phép đo cỡ `0.001` nhưng rất nhỏ đối với phép đo cỡ hàng tỷ đơn vị.

Với việc so sánh kết quả phép tính nội bộ, không nên chọn `absTol` chỉ vì số hiển thị có sáu chữ số thập phân. **Số chữ số người dùng muốn nhìn** và **mức sai số được phép của phép tính** là hai yêu cầu khác nhau.

## 5. Sai số tương đối: khi độ lớn thay đổi mạnh

Một tiêu chí thường dùng cho các giá trị khác 0 là:

\[
|a-b| \leq \varepsilon_{\text{rel}} \cdot \max(|a|, |b|)
\]

`relTol` là tỷ lệ không có đơn vị, ví dụ `1e-6` tương ứng khoảng một phần triệu của độ lớn tham chiếu. Nó điều chỉnh ngưỡng theo thang độ lớn.

Ví dụ `a = 1_000_000_000.5` và `b = 1_000_000_000.0`: chênh lệch tuyệt đối là `0.5`. Với `relTol = 1e-9`, ngưỡng tương đối xấp xỉ `1.0` nên chúng được xem là "gần bằng". Điều này **có thể hoàn toàn sai về nghiệp vụ** nếu khác biệt `0.5` là quan trọng. Do vậy, so sánh tương đối cũng không tự động đúng.

Gần 0, một tiêu chí thuần tương đối thường không đáp ứng mục tiêu: so sánh `0.0` với `1e-13` và `relTol = 1e-9` sẽ cho ngưỡng cỡ `1e-22`, dẫn tới "khác nhau". Nếu dụng ý là cho phép nhiễu đầu vào gần 0 với `absTol = 1e-12`, hãy kết hợp hai dạng.

## 6. Kết hợp ngưỡng tuyệt đối và tương đối có kiểm soát

Một tiêu chí phổ biến cho **giá trị `double` hữu hạn** là:

\[
|a-b| \leq \max\left(\varepsilon_{\text{abs}},
\varepsilon_{\text{rel}}\max(|a|,|b|)\right)
\]

Ý nghĩa: chênh lệch được chấp nhận khi **nằm trong ngưỡng tuyệt đối** hoặc **ngưỡng tương đối theo thang độ lớn**. Dùng `max` ở đây tương đương phép OR giữa hai phép thử sai số; không được nhầm với quy tắc bắt buộc đáp ứng *cả hai* ngưỡng (AND). Chọn OR hay AND là một quyết định miền dữ liệu; công thức này là **một chính sách gợi ý**, không phải định nghĩa bằng nhau toàn cục.

Ví dụ helper ở Java 17:

~~~java
static boolean close(double a, double b, double absTol, double relTol) {
    if (!Double.isFinite(absTol) || absTol < 0.0
            || !Double.isFinite(relTol) || relTol < 0.0
            || relTol >= 1.0) {
        throw new IllegalArgumentException("invalid tolerances");
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    if (a == b) {
        return true;
    }
    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= absTol || difference <= relTol * scale;
}
~~~

Đây là **đoạn phương thức** cần đặt trong một lớp Java. Ràng buộc `0 <= relTol < 1` là **chính sách an toàn của ví dụ** để không chấp nhận các ngưỡng tương đối cực lớn; không phải định nghĩa chung mà Java bắt buộc. Giá trị `absTol` và `relTol` được truyền từ yêu cầu hệ thống, không hard-code một epsilon bất kỳ trong helper.

Các lựa chọn đã được chủ động khai báo:
- `NaN` và cả hai loại vô cực bị từ chối. Nếu nghiệp vụ muốn `+Infinity` bằng chính nó, phải định nghĩa riêng trước khi dùng chính sách này.
- `+0.0` và `-0.0` được coi là bằng nhau (`a == b` là `true`). Nếu dấu của zero quan trọng, cần cách kiểm tra khác.
- Dùng `<=` để chấp nhận chính điểm ranh giới sai số. `<` là một quy tắc khác, không được đổi ngầm giữa kiểm thử và hệ thống.
- Với `absTol = 0`, `relTol = 0`, helper tương đương so sánh bằng nhau về số học cho giá trị hữu hạn, ngoại trừ việc nó vẫn từ chối `NaN` và vô cực.

**Giới hạn số học của công thức:** Nếu `a` và `b` rất lớn nhưng trái dấu, `a-b` có thể thành vô cực dù cả hai đầu vào hữu hạn; ví dụ `Double.MAX_VALUE - (-Double.MAX_VALUE)`. Với chính sách `relTol < 1` và `absTol` hữu hạn của helper, hai giá trị quá xa như vậy vẫn được phân loại "khác", nên phép trừ overflow không làm một kết quả sai được chấp nhận. Tuy nhiên, không coi helper này là thư viện so sánh số học bất biến cho mọi nhu cầu; nếu cần so sánh sai số tương đối cực kỳ chặt ở cả miền cực trị, hãy thiết kế thuật toán có kiểm soát overflow/underflow và đánh giá độ điều kiện.

## 7. Ví dụ chạy độc lập Java 17+

Tạo tệp `FloatingCompareDemo.java`:

~~~java
import java.math.BigDecimal;

public final class FloatingCompareDemo {
    static boolean close(double a, double b, double absTol, double relTol) {
        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol) || relTol < 0.0
                || relTol >= 1.0) {
            throw new IllegalArgumentException("invalid tolerances");
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) return false;
        if (a == b) return true;
        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return difference <= absTol || difference <= relTol * scale;
    }

    public static void main(String[] args) {
        double calculated = 0.1 + 0.2;
        System.out.println("exact binary comparison = "
                + (calculated == 0.3));
        System.out.println("domain tolerance = "
                + close(calculated, 0.3, 1e-12, 1e-12));
        System.out.println("near zero = "
                + close(1e-13, 0.0, 1e-12, 1e-9));
        System.out.println("different measurements = "
                + close(1.001, 1.0, 1e-5, 1e-6));
        System.out.println("large relative = "
                + close(1e9 + 0.5, 1e9, 1e-6, 1e-9));
        System.out.println("large absolute only = "
                + close(1e9 + 0.5, 1e9, 1e-6, 0.0));
        System.out.println("NaN = "
                + close(Double.NaN, Double.NaN, 1e-12, 1e-9));
        System.out.println("infinities = "
                + close(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1e-12, 1e-9));
        System.out.println("signed zeros = "
                + close(+0.0, -0.0, 0.0, 0.0));

        double next = Math.nextUp(1.0);
        System.out.println("adjacent = " + (next > 1.0));
        System.out.println("one ulp = "
                + ((next - 1.0) == Math.ulp(1.0)));

        System.out.println("nontransitive a,b = "
                + close(0.0, 0.75, 1.0, 0.0));
        System.out.println("nontransitive b,c = "
                + close(0.75, 1.5, 1.0, 0.0));
        System.out.println("nontransitive a,c = "
                + close(0.0, 1.5, 1.0, 0.0));

        BigDecimal money = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimal equality = "
                + money.equals(new BigDecimal("0.3")));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 FloatingCompareDemo.java
java FloatingCompareDemo
~~~

Kết quả được kiểm chứng:

~~~text
exact binary comparison = false
domain tolerance = true
near zero = true
different measurements = false
large relative = true
large absolute only = false
NaN = false
infinities = false
signed zeros = true
adjacent = true
one ulp = true
nontransitive a,b = true
nontransitive b,c = true
nontransitive a,c = false
decimal equality = true
~~~

Kết luận từ ví dụ:

- `0.1 + 0.2` khác `0.3` ở biểu diễn nhị phân nhưng có thể được coi là gần nhau nếu **mức sai số cho phép đã được xác định**.
- `1e9 + 0.5` và `1e9` vượt ngưỡng tuyệt đối `1e-6` nhưng nằm trong ngưỡng tương đối `1e-9`. Điều này chỉ đúng với chính sách của helper, không mặc nhiên đúng cho quyết định tài chính.
- Hai trường hợp `NaN` và vô cực được phân loại theo quy tắc rõ ràng thay vì để phép trừ sinh `NaN` gây kết quả ngầm.
- So sánh gần bằng có thể không bắc cầu; `0.0` gần `0.75` và `0.75` gần `1.5` nhưng `0.0` không gần `1.5`.

## 8. Gần bằng không có tính bắc cầu: đừng dùng làm equals của khóa

Đây là một trong những lý do quan trọng nhất để không dùng epsilon tùy ý ở mọi nơi.

Giả sử `absTol = 1.0` và `relTol = 0`:

~~~text
a = 0.00
b = 0.75
c = 1.50

close(a, b) == true  (chênh lệch 0.75)
close(b, c) == true  (chênh lệch 0.75)
close(a, c) == false (chênh lệch 1.50)
~~~

Trong toán học, **quan hệ tương đương** phải có tính phản xạ, đối xứng và bắc cầu. Quan hệ “cách nhau không quá epsilon” nhìn chung **không bắc cầu**, vì vậy nó không phải một định nghĩa `equals()` hợp lệ cho các đối tượng dùng làm khóa.

Hậu quả nếu dùng `close(a,b)` làm `equals()` của một lớp:

- Không có cách thông thường nào để xây dựng `hashCode()` vừa hữu ích vừa giữ hợp đồng hash/equality cho các “lân cận” chồng nhau trên toàn miền.
- `HashSet`/`HashMap` có thể cho kết quả không ổn định theo thứ tự chèn, vi phạm kỳ vọng về quan hệ bằng nhau.
- Một `Comparator` trả 0 cho những cặp “gần” nhau có thể vi phạm tính nhất quán và các quy tắc sắp thứ tự mà `TreeSet`/`TreeMap` dựa vào.

**Giải pháp:** nếu cần gom nhóm các giá trị theo độ phân giải, định nghĩa một **quy tắc lượng tử hóa/nhóm thành bucket có biên cố định** rõ ràng, rồi so sánh khóa bucket theo quan hệ tương đương thực sự; các điểm gần ranh giới bucket có thể rơi vào nhóm khác, vì vậy phải nêu rõ semantics. Đừng biến ngưỡng gần bằng vốn không bắc cầu thành `equals` toàn cục.

Khi chỉ dùng để *kiểm tra một kết quả số học đơn lẻ* với kỳ vọng đã định nghĩa, hàm `close` lại rất hữu ích. Tính phù hợp phụ thuộc **vai trò của phép so sánh**.

## 9. NaN, Infinity và số 0 có dấu

IEEE 754 có những giá trị đặc biệt; một epsilon tùy tiện không xử lý chúng đúng cho mọi tình huống.

| Giá trị | Với toán tử số học Java | Điều cần quyết định |
|---|---|---|
| `Double.NaN` | `NaN == NaN` là `false`; `NaN < x` và `NaN > x` đều `false` | Từ chối, biểu diễn dữ liệu thiếu hay có quy tắc riêng? |
| `+Infinity` và `-Infinity` | Vô cực cùng dấu `==` nhau, trừ/chia có thể tạo vô cực/`NaN` | Có cho phép vô cực trong miền nghiệp vụ không? |
| `+0.0` và `-0.0` | `+0.0 == -0.0` là `true` | Dấu zero có mang ý nghĩa hay không? |
| Hai giá trị `double` lớn trái dấu | `a - b` có thể thành Infinity vì overflow | Tránh suy luận vội từ một phép trừ |
| Số rất nhỏ gần 0 | Có giá trị subnormal và rounding/underflow | Ngưỡng tuyệt đối hoặc thiết kế thuật toán tương ứng |

Không làm điều sau mà chưa xác định chính sách:

~~~java
return Math.abs(a - b) <= epsilon;
~~~

Nếu `a` và `b` đều là `+Infinity`, `a - b` là `NaN`; phép so sánh với epsilon sẽ là `false`, dù `a == b` trả `true`. Nếu `NaN` xuất hiện trong tính toán, việc chỉ nhận `false` âm thầm có thể che khuất nguồn lỗi; tùy ứng dụng nên kiểm tra và báo dữ liệu không hợp lệ.

Với mục tiêu **sắp xếp/khóa collection**, `Double.compare(a,b)` tạo thứ tự toàn phần theo quy tắc của Java: `-0.0` đứng trước `+0.0`, và `NaN` được xếp sau vô cực dương. Điều này khác với `a == b` (coi hai zero bằng nhau nhưng không coi `NaN` bằng chính nó). `Double.equals()` của wrapper cũng định nghĩa ngữ nghĩa phù hợp cho hash collections. Không thay comparator sắp xếp bằng kiểm tra epsilon thiếu tính bắc cầu.

## 10. Math.ulp và Math.nextUp: đo khoảng cách biểu diễn

`Math.ulp(x)` trả kích thước một đơn vị ở vị trí chữ số có trọng số thấp nhất (*unit in the last place*) quanh giá trị `x`, phụ thuộc thang độ lớn. `Math.nextUp(x)` trả giá trị `double` kế tiếp hướng tới dương vô cực.

~~~java
double x = 1.0;
double next = Math.nextUp(x);

System.out.println(next > x);              // true
System.out.println(next - x == Math.ulp(x)); // true
~~~

Gần `1.0`, khoảng cách giữa hai số `double` liền kề khoảng `2.22e-16`. Ở độ lớn khác, khoảng cách có thể lớn hơn hoặc nhỏ hơn. Ví dụ quanh `1e16`, không thể đại diện mọi số nguyên liền kề bằng `double`: bước giữa các giá trị có thể biểu diễn đã lớn hơn 1.

ULP có giá trị khi mục tiêu là đánh giá **chất lượng số học của một thuật toán dấu phẩy động** so với kết quả tham chiếu cùng kiểu, đặc biệt khi bạn hiểu quy tắc rounding và miền đầu vào.

Tuy nhiên:
- Một thuật toán tích lũy sai số qua nhiều bước có thể khác kết quả lý tưởng nhiều hơn vài ULP; không chọn “4 ULP” chỉ vì thấy trong mẫu test.
- Hai giá trị rất nhỏ khác nhau vài ULP có thể nhỏ hơn độ phân giải đo lường thực tế nhiều bậc.
- ULP không thay thế việc định nghĩa sai số nghiệp vụ; giữa sai số máy và sai số của phép đo/dữ liệu còn nhiều tầng khác.
- Nếu áp dụng kiểm tra khoảng cách theo bit representation, phải xử lý cẩn thận số âm, signed zero, `NaN` và vô cực. Không chuyển `double` sang `long` bằng ép kiểu rồi trừ hai `long` để tính ULP distance.

ULP là công cụ *chẩn đoán và lượng hóa độ phân giải máy*, không phải một epsilon phổ quát khác.

## 11. Sai số và độ điều kiện của thuật toán

Không chỉ **cách lưu số** mà cả **cấu trúc phép tính** ảnh hưởng sai số. Ví dụ, trừ hai số gần bằng có thể khiến phần kết quả còn lại mang sai số tương đối lớn vì triệt tiêu chữ số có nghĩa (*catastrophic cancellation*) khi dữ liệu đầu vào đã bị làm tròn.

~~~java
double x = 1e16;
double y = x + 1.0;

System.out.println(x == y); // true
~~~

Ở thang `1e16`, thêm 1 có thể không đổi biểu diễn `double` do bước ULP đã lớn hơn 1. Nếu sau đó tính `y - x`, kết quả 0 không chứng minh sự thay đổi toán học ban đầu không tồn tại; thông tin đã bị mất khi biểu diễn `y`. Không một lựa chọn epsilon nào có thể **khôi phục chữ số đã mất**.

Cách cải thiện tùy bài toán:
- Chọn thuật toán ổn định số học hơn, ví dụ công thức giảm sự trừ hai số gần nhau, dùng `Math.fma` khi giảm được lỗi làm tròn ở phép nhân-cộng.
- Thay đổi thang đo/chuẩn hóa đơn vị khi thích hợp, nhưng phải giữ diễn giải nghiệp vụ.
- Sử dụng độ chính xác cao hơn hoặc `BigDecimal` nếu yêu cầu tính thập phân chính xác và hiệu năng cho phép.
- Ước lượng/chứng minh sai số từ số bước và đặc tính dữ liệu thay vì chọn một con số “cảm giác an toàn”.

Với phép thử hồi quy thuật toán số, **expected value** thường cần lấy từ một nguồn tham chiếu có chất lượng tốt hơn phép tính cần kiểm tra, và tolerance phải gắn với độ chính xác mong đợi của thuật toán.

## 12. Khi nào dùng ==, Double.compare hoặc BigDecimal?

| Nhu cầu | Lựa chọn thích hợp | Vì sao |
|---|---|---|
| Kiểm tra một cờ/trạng thái encoded bằng các giá trị `double` chính xác đã định nghĩa | `==`, sau khi có chính sách `NaN`/zero rõ ràng | Không cần tự ý gộp các giá trị lân cận |
| Kiểm tra kết quả xấp xỉ của một phép toán với sai số được phép | `close(a,b,absTol,relTol)` theo miền dữ liệu | Chọn ngưỡng từ yêu cầu |
| Sắp xếp `Double` và làm khóa sorted collection | `Double.compare`/comparator nhất quán | Giữ quy tắc thứ tự hợp lệ |
| Số lượng, ID, timestamp dạng nguyên trong giới hạn kiểu số nguyên | `int`/`long` hoặc kiểu phù hợp | Tránh đưa bài toán nguyên sang dấu phẩy động không cần thiết |
| Tiền/định mức decimal phải chính xác | `BigDecimal` từ chuỗi hoặc số nguyên đơn vị nhỏ nhất | Biểu diễn thập phân và rounding có chính sách rõ ràng |
| Kiểm tra chất lượng hàm số học gần giới hạn khả năng của `double` | ULP + phân tích sai số/độ điều kiện | Đánh giá gần mức biểu diễn máy |

Ví dụ tính thập phân:

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal expected = new BigDecimal("0.3");

System.out.println(a.add(b).equals(expected)); // true
~~~

`BigDecimal` không phải tự động bảo đảm mọi phép toán vô hạn được biểu diễn chính xác: `divide` có thể yêu cầu `RoundingMode` và `MathContext`. Ngoài ra, `BigDecimal.equals()` còn kiểm tra `scale`: `2.0` không `equals()` với `2.00`, dù `compareTo() == 0`. Chọn ngữ nghĩa bằng nhau phù hợp.

Tránh `new BigDecimal(0.1)` nếu muốn decimal chính xác 0.1: constructor nhận `double` giữ giá trị nhị phân thực có thể không đúng biểu diễn thập phân mong muốn. Dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` theo nguồn dữ liệu.

## 13. Đặt epsilon trong unit test như thế nào?

Trong kiểm thử phép tính số, không chỉ chọn epsilon để “test xanh”. Một test tốt bao gồm:

1. **Giải thích độ chính xác kỳ vọng:** sai số đến từ biểu diễn nhị phân, thuật toán hay độ chính xác của nguồn dữ liệu?
2. **Tách absolute và relative tolerance:** với kết quả có thể gần 0, một ngưỡng tuyệt đối có căn cứ thường cần thiết; với kết quả trải nhiều bậc độ lớn, kiểm tra relative tolerance.
3. **Kiểm tra trường hợp biên:** gần 0, số rất lớn/nhỏ, số âm, signed zero, `NaN`, vô cực, phép tính ở vùng cancellation.
4. **Kiểm tra các giá trị phải phân biệt:** tránh tăng epsilon chỉ để những case sai bị coi là "đúng".
5. **Không dùng gần bằng làm invariant collection:** nếu kiểm thử cấu trúc dữ liệu yêu cầu duy nhất/sắp thứ tự, định nghĩa semantics khóa/Comparator rõ ràng.
6. **Báo sai số thực tế khi fail:** in `actual`, `expected`, `difference`, ngưỡng cho phép và unit để dễ chẩn đoán.

Ví dụ một bài toán đo độ dài quy định dung sai tối đa `0.001 m`, viết test với `absTol = 0.001` có giải thích “dung sai đo một milimét”. Một phép tính xấp xỉ tương đối `1e-8` có thể dùng `relTol = 1e-8` nếu đã được chứng minh/kiểm định cho miền dữ liệu; không lấy cả hai con số từ những bài toán khác rồi ghép ngẫu nhiên.

Với các framework test hỗ trợ assertion kiểm tra `double` kèm `delta`, cần đọc kỹ hợp đồng: `delta` thường là một sai số **tuyệt đối**, không tự thực hiện chính sách tương đối/phối hợp. Tự đổi framework assertion không giải quyết nguồn gốc lựa chọn ngưỡng.

## 14. Những lỗi phổ biến cần loại bỏ

1. **Hard-code `1e-9` ở mọi nơi:** không có ngưỡng tuyệt đối nào phù hợp tất cả miền giá trị.
2. **Dùng `Double.MIN_VALUE` làm epsilon chung:** đây là số dương `double` nhỏ nhất, không phải sai số rounding thông thường gần 1.0.
3. **Lấy `Math.ulp(1.0)` áp cho mọi số:** khoảng biểu diễn phụ thuộc độ lớn; nó cũng không phản ánh yêu cầu nghiệp vụ.
4. **Chỉ dùng sai số tương đối cho giá trị gần 0:** ngưỡng thu nhỏ về 0 và có thể không nhận sai số tuyệt đối có ý nghĩa.
5. **Không kiểm tra `NaN`/vô cực:** `Math.abs(a-b)` có thể là `NaN` hoặc `Infinity`; phép so sánh boolean chỉ trở thành false mà không nói vì sao.
6. **Lấy `==` hoặc `Double.compare()` thay cho kiểm tra xấp xỉ:** hai API ấy có semantics riêng; so sánh exact không diễn đạt sai số được phép.
7. **Dùng so sánh gần bằng làm `equals()`/`Comparator`:** tính bắc cầu không được bảo đảm; có thể phá hợp đồng map/set.
8. **Coi tolerance là cách sửa thuật toán kém ổn định:** epsilon không phục hồi dữ liệu bị mất do cancellation/rounding.
9. **Đổi đơn vị nhưng giữ nguyên ngưỡng tuyệt đối:** `0.001 m` phải được đổi thành `1 mm` khi biến dữ liệu từ mét sang milimét, nếu thực sự là cùng dung sai.
10. **Bỏ qua overflow trong phép trừ:** hai toán hạng hữu hạn rất lớn trái dấu có thể cho hiệu vô cực; cần đánh giá trường hợp đặc biệt và miền đầu vào.
11. **Đánh đồng độ chính xác hiển thị với độ chính xác tính toán:** in 2 chữ số sau dấu phẩy không chứng minh phép tính chỉ sai ít hơn `0.005`.
12. **Chọn epsilon bằng cách tăng dần cho tới khi test qua:** điều đó có thể che bug hoặc thay đổi sai lệch mà đáng ra phải phát hiện.

## 15. Bài tập tự kiểm tra

**Bài 1 — epsilon quá rộng**

Một phép đo khác nhau `0.0005` mét và yêu cầu chính thức chỉ cho phép chênh `0.0001` mét. Dùng `Math.abs(a-b) < 0.001` có phù hợp không?

**Đáp án:** Không. Ngưỡng 0.001 mét quá rộng so với dung sai quy định 0.0001 mét; nó nhận một giá trị sai. Cần dùng ngưỡng đúng theo hợp đồng, kiểm tra tình huống biên và đơn vị.

**Bài 2 — ngưỡng tương đối và số lớn**

`a = 1e9 + 0.5`, `b = 1e9`. Theo `relTol = 1e-9` và `absTol = 1e-6` trong helper của mục 6, hai số có gần bằng không?

**Đáp án:** Có, vì ngưỡng tương đối khoảng 1.0 lớn hơn chênh lệch 0.5. Điều đó chỉ phản ánh **chính sách cho phép 1 phần tỷ theo độ lớn**, không phải xác nhận hai số phải được coi là tương đương cho mọi nghiệp vụ.

**Bài 3 — tính bắc cầu**

Với ngưỡng tuyệt đối 1, hãy so `0.0`, `0.75`, `1.5`. Vì sao không được dùng quy tắc đó để viết `equals()`?

**Đáp án:** Hai cặp kề nhau "gần" nhưng cặp ngoài cùng không "gần". Quan hệ không bắc cầu, nên không phải quan hệ tương đương thích hợp cho `equals()` hoặc các khóa collection.

**Bài 4 — NaN**

`Double.NaN == Double.NaN` là `true` hay `false`? Nếu muốn từ chối dữ liệu không hợp lệ trước so sánh gần bằng, kiểm tra gì?

**Đáp án:** `false`. Sử dụng `Double.isFinite(a)`/`Double.isFinite(b)` nếu quy tắc phải từ chối cả `NaN` lẫn hai loại vô cực.

**Bài 5 — rounding và exact equality**

Một hệ thống tiền tệ yêu cầu số thập phân chính xác từ chuỗi `"0.1"` và `"0.2"`. Có nên lấy `double` rồi thêm epsilon?

**Đáp án:** Không cần. Dùng `BigDecimal` tạo từ chuỗi, xác định `scale` và `RoundingMode` theo hợp đồng khi cần. `BigDecimal` giúp mô tả chính xác dữ liệu decimal; nó không thay thế việc thiết kế quy tắc làm tròn.

**Bài 6 — số ở thang 1e16**

`double x = 1e16; double y = x + 1.0;`. Nếu `x == y` là `true`, có thể chọn epsilon để khôi phục sự khác biệt đúng bằng 1 không?

**Đáp án:** Không. Phép cộng đã làm tròn về cùng một giá trị biểu diễn; thông tin về phần cộng 1 bị mất. Cần đổi kiểu biểu diễn hoặc cách tính khi bài toán thực sự đòi phân biệt các đơn vị nguyên tại thang độ lớn này.

## 16. Ghi nhớ và tài liệu chuẩn

Đừng hỏi “nên dùng epsilon là bao nhiêu cho Java?”. Hãy hỏi: **đơn vị gì, thang số nào, sai số nào được phép, và hệ quả nếu coi hai số khác nhau là bằng nhau?**

- `==` có ích khi mục tiêu là bằng nhau chính xác theo semantics dấu phẩy động đã định nghĩa.
- `absTol` thích hợp khi có mức lệch được phép theo đơn vị; `relTol` hỗ trợ nhiều thang độ lớn; **phối hợp ngưỡng vẫn cần lý do định lượng**.
- `Math.ulp`/`Math.nextUp` giúp hiểu độ phân giải biểu diễn máy, không xác định tự động dung sai nghiệp vụ.
- So sánh gần bằng **không bắc cầu**, không thay thế `equals()` hoặc comparator cho cấu trúc dữ liệu.
- Với decimal chính xác, kiểu nguyên theo đơn vị nhỏ nhất hoặc `BigDecimal` thường hợp lý hơn một epsilon tùy tiện.

Tài liệu chính thức:
- [Double — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): IEEE 754, `NaN`, signed zero, `Double.compare`, `Double.isFinite` và semantics của wrapper.
- [Math — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `ulp`, `nextUp`, `fma` và độ chính xác các hàm floating point.
- [Java Language Specification SE 17, `4.2.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): biểu diễn kiểu `float`/`double`, giá trị đặc biệt và hành vi dấu phẩy động.
- [BigDecimal — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): tính thập phân, `equals`, `compareTo` và rounding theo hợp đồng.
