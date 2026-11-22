# Giới hạn của hằng epsilon cố định cho mọi bài toán

Khi xử lý số thực `float` và `double`, phép so sánh bằng tuyệt đối bằng `==` có thể thất bại dù hai kết quả được kỳ vọng bằng nhau về mặt toán học. Một cách xử lý phổ biến là so sánh sai khác tuyệt đối với một ngưỡng nhỏ, thường gọi là **epsilon**:

~~~java
boolean approximatelyEqual = Math.abs(a - b) <= 1e-9;
~~~

Tuy nhiên, **không có một giá trị epsilon cố định phù hợp với mọi bài toán, mọi thang đo và mọi độ lớn của số**. Giá trị `1e-9` có thể quá lỏng đối với số cỡ `1e-12`, nhưng lại quá nghiêm ngặt đối với số cỡ `1e12`. Ngưỡng “nhỏ” phải được định nghĩa theo đơn vị, mức sai số được chấp nhận, độ lớn dữ liệu và mục đích của phép so sánh.

Bài học phân biệt sai số tuyệt đối, sai số tương đối và đơn vị ULP; chỉ ra giới hạn của cách dùng một epsilon tuyệt đối; sau đó xây dựng cách so sánh có chủ đích bằng Java 17+, với xử lý giá trị đặc biệt như NaN và vô cực.

## 1. Vì sao số thực có sai số?

`float` và `double` được Java biểu diễn dưới dạng số thực nhị phân hữu hạn theo IEEE 754. Nhiều phân số thập phân quen thuộc, chẳng hạn `0.1` và `0.2`, không có biểu diễn nhị phân hữu hạn chính xác. Việc lưu trữ và tính toán phải làm tròn.

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum == 0.3);        // false
System.out.println(sum);               // 0.30000000000000004
~~~

Đoạn trên là minh họa để đặt trong phương thức Java. Kết quả `sum` khác bit so với literal `0.3` một lượng nhỏ, mặc dù theo số học thập phân lý tưởng `0.1 + 0.2 = 0.3`.

Không phải mọi phép tính thực đều sai khác: các số có biểu diễn nhị phân chính xác như `0.5`, `0.25` hay một số nguyên nhỏ có thể cho kết quả chính xác trong những phép toán nhất định. Sai số phụ thuộc cả dữ liệu và phép toán, không phải đặc điểm “mọi số `double` đều không thể so sánh bằng”.

Cũng không nên đồng nhất **sai số biểu diễn** với **sai số đo đạc**. Giá trị `3.14159` làm tròn từ một phép đo thực nghiệm có thể mang độ bất định lớn hơn rất nhiều lỗi làm tròn của `double`. Ngưỡng so sánh trong ứng dụng có thể phải phản ánh sai số đo, giới hạn sensor, biến đổi đơn vị hoặc tiêu chí nghiệp vụ, bên cạnh sai số máy tính.

## 2. Ba khái niệm thường bị gọi chung là epsilon

Từ “epsilon” dễ gây nhầm vì được dùng trong nhiều ngữ cảnh:

| Khái niệm | Ý nghĩa | Ví dụ hoặc cách xác định |
| --- | --- | --- |
| **Dung sai tuyệt đối (absolute tolerance)** | Sai khác tuyệt đối lớn nhất được chấp nhận, theo **đơn vị của dữ liệu** | `absTol = 0.01` mét |
| **Dung sai tương đối (relative tolerance)** | Sai khác được chấp nhận so với **độ lớn giá trị**; không có đơn vị | `relTol = 1e-6` |
| **Machine epsilon** | Đặc trưng về khoảng cách biểu diễn của định dạng số thực quanh 1.0; không phải mặc định dung sai nghiệp vụ | Với `double`, khoảng cách `Math.ulp(1.0)` bằng `2.220446049250313E-16` |

Machine epsilon quanh 1.0 **không cố định khoảng cách giữa mọi cặp số có thể biểu diễn**. Khoảng cách giữa các số thực liền kề thay đổi theo độ lớn và vùng số mũ. Java cung cấp `Math.ulp(x)` để quan sát đơn vị theo giá trị cuối cùng tại `x` (ULP, *unit in the last place*).

Ví dụ:

~~~java
System.out.println(Math.ulp(1.0));   // 2.220446049250313E-16
System.out.println(Math.ulp(1e12));  // 1.220703125E-4
~~~

ULP quanh `1e12` lớn hơn rất nhiều ULP quanh `1.0`. Do đó, việc dùng một ngưỡng nhỏ tuyệt đối bằng `1e-15` hay `1e-9` mà không xét độ lớn dữ liệu có thể không hợp lý. Cả ULP lẫn machine epsilon đều **không tự quyết định** phép sai khác nào là chấp nhận được trong bài toán cụ thể.

## 3. Giới hạn thứ nhất: epsilon cố định quá lỏng khi số rất nhỏ

Giả sử dùng một dung sai tuyệt đối chung:

~~~java
static boolean fixed(double a, double b) {
    return Math.abs(a - b) <= 1e-9;
}
~~~

Đây là phương thức minh họa cần đặt trong lớp Java. Xét:

~~~java
double a = 1e-12;
double b = 2e-12;
boolean equal = Math.abs(a - b) <= 1e-9; // true
~~~

Sai khác tuyệt đối là `1e-12` nên nhỏ hơn epsilon `1e-9`. Nhưng `b` **gấp đôi** `a`: sai khác tương đối so với độ lớn lớn hơn bằng 50% khi lấy mẫu số là `max(|a|, |b|)`. Trong bài toán yêu cầu tương đối chính xác, coi hai số “gần bằng” là không hợp lý.

Kết luận: **epsilon tuyệt đối có thể che giấu sai khác quan trọng ở thang giá trị nhỏ**. Không thể chỉ nhìn vào số mũ của epsilon mà xác định mức độ nghiêm ngặt.

## 4. Giới hạn thứ hai: epsilon cố định quá chặt khi số lớn

Xét hai kết quả gần bằng nhau so với thang đo:

~~~java
double a = 1e12;
double b = 1e12 + 0.01;

boolean equal = Math.abs(a - b) <= 1e-9; // false
~~~

Sai khác tuyệt đối vào khoảng `0.01`, lớn hơn hằng `1e-9` nhiều lần, nên kết quả là `false`. Tuy nhiên, so với độ lớn `1e12`, sai khác này có tỷ lệ khoảng `1e-14`. Trong nhiều bài toán có mức dung sai tương đối `1e-12`, hai giá trị như vậy có thể được chấp nhận.

Do `double` làm tròn theo lưới số nhị phân, sai khác thực tế tính từ hai giá trị đã lưu có thể không đúng `0.01` tuyệt đối; trong ví dụ này nó xấp xỉ `0.010009765625`. Điều đó càng cho thấy phải suy luận trên **giá trị được biểu diễn thực tế**, thay vì cho rằng mọi literal số thập phân đều được lưu chính xác.

Kết luận: **epsilon tuyệt đối rất nhỏ có thể từ chối sai khác không đáng kể theo tỷ lệ ở thang giá trị lớn**.

## 5. Đánh giá sai số tuyệt đối và tương đối

Sai khác tuyệt đối giữa `a` và `b`:

\[
d_{\mathrm{abs}} = |a-b|
\]

Một dạng sai khác tương đối đối xứng, khi ít nhất một giá trị khác 0, là:

\[
d_{\mathrm{rel}} =
\frac{|a-b|}{\max(|a|, |b|)}
\]

Trong đó:

- Sai khác tuyệt đối vẫn mang đơn vị dữ liệu: sai khác `0.01` giây khác `0.01` đồng tiền hay `0.01` mét.
- Sai khác tương đối không có đơn vị. Nó hữu ích khi thang đo trải rộng qua nhiều bậc độ lớn.
- Khi cả hai số bằng 0, biểu thức tỷ số trên có mẫu số 0; nếu một hoặc cả hai số gần 0, sai khác tương đối trở nên nhạy và không đáp ứng tốt nhu cầu “gần 0”.

Đối với dữ liệu gần 0, cần một **ngưỡng tuyệt đối dựa trên ý nghĩa của bài toán**. Đối với dữ liệu lớn, ngưỡng tương đối thường phản ánh mức chính xác mong muốn tốt hơn. Vì thế một quy tắc kết hợp phổ biến sử dụng hai dung sai khác nhau:

\[
|a-b| \le \max\left(\mathrm{absTol},
\mathrm{relTol}\cdot\max(|a|,|b|)\right)
\]

Có thể viết dưới dạng logic:

~~~java
difference <= absTol || difference <= relTol * scale
~~~

Trong đó `difference = Math.abs(a - b)` và `scale = Math.max(Math.abs(a), Math.abs(b))`. Đây là **mẫu thiết kế**, không phải định lý rằng mọi miền ứng dụng phải chọn cùng cách chuẩn hóa hoặc cùng dung sai.

### Ví dụ đối chiếu

| Hai giá trị | absTol | relTol | Ý nghĩa |
| --- | ---: | ---: | --- |
| `0.0` và `1e-13` | `1e-12` | `1e-9` | Có thể chấp nhận sai khác cực nhỏ gần 0 |
| `1e-12` và `2e-12` | `1e-15` | `1e-9` | Không nên coi bằng chỉ vì số tuyệt đối rất nhỏ |
| `1e12` và `1e12 + 0.01` | `1e-15` | `1e-12` | Có thể chấp nhận sai khác tuyệt đối lớn hơn nhưng tương đối nhỏ |

Các ngưỡng ở bảng nhằm **minh họa cách chọn theo yêu cầu**, không có giá trị mặc định được Java hoặc IEEE 754 khuyến nghị cho mọi chương trình.

## 6. Chọn dung sai theo miền bài toán

Trước khi viết hàm so sánh, cần xác định:

1. **Đơn vị và độ phân giải:** dữ liệu nhiệt độ chính xác đến 0.1°C khác dữ liệu vị trí cần độ chính xác 0.1 micromet. `absTol` có đơn vị tương ứng với đại lượng được so sánh.
2. **Quy mô và bậc độ lớn:** giá trị đo biến thiên từ `1e-12` đến `1e12` thường cần nghĩ đến sai số tương đối hoặc phép chuẩn hóa thích hợp.
3. **Nguồn sai số:** biểu diễn nhị phân, phép cộng/trừ gần nhau, phép đo, chuyển đổi dữ liệu, cách thuật toán tích lũy lỗi.
4. **Hậu quả của sai lệch:** tiêu chí nghiệm thu hiển thị, kiểm thử thuật toán, cảnh báo an toàn, điều kiện hội tụ có thể đòi mức nghiêm ngặt khác nhau.
5. **Mức tin cậy:** nên lấy ngưỡng từ đặc tả, độ phân giải thiết bị, sai số phân tích, kiểm thử thực nghiệm có đối chứng hoặc ràng buộc nghiệm thu; không tự đặt `1e-9` chỉ vì nó trông nhỏ.

Ví dụ, trong kiểm tra cảm biến có độ phân giải 0.01 đơn vị, so sánh kết quả bằng epsilon `1e-15` là không phản ánh khả năng đo thực tế. Trong bài toán giải hệ phương trình có nghiệm gần 0, kiểm tra chỉ bằng sai số tương đối có thể gây hành vi khó hiểu. Còn với các đại lượng luôn ở một thang đo hẹp, một dung sai tuyệt đối cố định, đã được đặc tả, có thể **rất phù hợp**.

Không cần bắt buộc mọi phép so sánh phải dùng cả absTol và relTol. Hai tiêu chí này chỉ là công cụ. Chọn chúng tùy ngữ nghĩa chứ không theo một “công thức thần kỳ”.

## 7. Ví dụ Java 17+: so sánh fixed và kết hợp

Tạo tệp `EpsilonLimitsDemo.java`:

~~~java
public class EpsilonLimitsDemo {
    static boolean fixed(double a, double b, double epsilon) {
        if (!Double.isFinite(epsilon) || epsilon < 0.0) {
            throw new IllegalArgumentException("epsilon");
        }
        return Double.isFinite(a) && Double.isFinite(b)
                && Math.abs(a - b) <= epsilon;
    }

    static boolean mixed(double a, double b, double absTol, double relTol) {
        if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
                || absTol < 0.0 || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("tolerance");
        }
        if (a == b) return true; // Cả hai cùng vô cực, hoặc +0.0/-0.0
        if (!Double.isFinite(a) || !Double.isFinite(b)) return false;

        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return difference <= absTol || difference <= relTol * scale;
    }

    public static void main(String[] args) {
        double sum = 0.1 + 0.2;
        System.out.println("sum == 0.3: " + (sum == 0.3));
        System.out.println("fixed sum: " + fixed(sum, 0.3, 1e-9));

        System.out.println("small fixed: "
                + fixed(1e-12, 2e-12, 1e-9));
        System.out.println("small mixed: "
                + mixed(1e-12, 2e-12, 1e-15, 1e-9));

        System.out.println("large fixed: "
                + fixed(1e12, 1e12 + 0.01, 1e-9));
        System.out.println("large mixed: "
                + mixed(1e12, 1e12 + 0.01, 1e-15, 1e-12));

        System.out.println("near zero mixed: "
                + mixed(0.0, 1e-13, 1e-12, 1e-9));
        System.out.println("NaN mixed: "
                + mixed(Double.NaN, 1.0, 1e-12, 1e-9));
        System.out.println("same infinity mixed: "
                + mixed(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1e-12, 1e-9));

        System.out.println("ulp(1): " + Math.ulp(1.0));
        System.out.println("ulp(1e12): " + Math.ulp(1e12));

        System.out.println("not transitive: "
                + (fixed(0.0, 0.75, 1.0)
                && fixed(0.75, 1.5, 1.0)
                && !fixed(0.0, 1.5, 1.0)));
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac EpsilonLimitsDemo.java
java EpsilonLimitsDemo
~~~

Đầu ra đã được kiểm chứng:

~~~text
sum == 0.3: false
fixed sum: true
small fixed: true
small mixed: false
large fixed: false
large mixed: true
near zero mixed: true
NaN mixed: false
same infinity mixed: true
ulp(1): 2.220446049250313E-16
ulp(1e12): 1.220703125E-4
not transitive: true
~~~

### Phân tích kết quả

- `fixed sum` là `true` vì `0.1 + 0.2` và `0.3` chỉ sai khác khoảng `5.55e-17`, nhỏ hơn `1e-9`.
- `small fixed` là `true` nhưng `small mixed` là `false`: epsilon tuyệt đối `1e-9` quá rộng cho cặp `1e-12` và `2e-12`; tiêu chí tương đối chặt hơn phản ánh sai khác lớn theo tỷ lệ.
- `large fixed` là `false` còn `large mixed` là `true`: sai khác `0.01` quá lớn so với epsilon tuyệt đối `1e-9`, nhưng đủ nhỏ theo tỷ lệ `1e-12` trên thang `1e12`.
- `near zero mixed` là `true` nhờ `absTol`: quy tắc tương đối thuần túy không được thiết kế để xử lý vùng gần 0 theo cùng ý nghĩa.
- `Math.ulp` minh họa khoảng cách biểu diễn thay đổi mạnh theo độ lớn.
- `not transitive` bằng `true` chứng minh rằng **gần bằng theo dung sai không có tính bắc cầu**: `0` gần `0.75`, `0.75` gần `1.5`, nhưng `0` không gần `1.5` với cùng epsilon 1.

Ví dụ `mixed` minh họa một chính sách so sánh cụ thể. Nó chủ ý cho hai giá trị **cùng vô cực** là bằng nhau, còn NaN luôn không bằng. Trong ứng dụng bắt buộc hai toán hạng hữu hạn, hãy chuyển kiểm tra `Double.isFinite(a) && Double.isFinite(b)` lên **trước** nhánh `a == b`. Không có một quy tắc xử lý vô cực thích hợp cho mọi miền nghiệp vụ.

Với đối số có độ lớn rất lớn và trái dấu, `a - b` có thể tràn ra vô cực dù `a`, `b` đều hữu hạn. Trong ví dụ, khi đó `difference` là vô cực và không vượt qua các ngưỡng hữu hạn; hàm trả `false`. Nếu xây dựng thuật toán phân tích sai số chuyên dụng, cần xem cả vấn đề overflow và underflow khi tính chênh lệch, thay vì cho rằng phép trừ luôn chính xác.

## 8. Tại sao “so sánh gần bằng” không phải quan hệ bằng thật?

Xét `epsilon = 1.0`:

- `a = 0.0` gần `b = 0.75` vì sai khác 0.75.
- `b = 0.75` gần `c = 1.5` vì sai khác 0.75.
- `a = 0.0` **không** gần `c = 1.5` vì sai khác 1.5.

Vì thiếu tính bắc cầu, kiểm tra `Math.abs(a - b) <= epsilon` không tạo thành quan hệ tương đương toán học. Hệ quả:

- Không dùng “bằng trong epsilon” làm định nghĩa trực tiếp của `equals`/`hashCode` trên đối tượng nếu nó vi phạm hợp đồng tương đương.
- Không dùng bộ so sánh “trả 0 nếu gần bằng” một cách tùy tiện trong `TreeSet`, `TreeMap` hoặc `Collections.sort`: nó có thể vi phạm hợp đồng thứ tự của `Comparator` và gây hành vi khó đoán.
- Nếu cần nhóm các số theo bucket, cần xác định **quy tắc lượng tử hóa** (quantization), đơn vị, ranh giới và cách xử lý số âm một cách nhất quán. Bucket cũng có sai khác ở ranh giới, nhưng tạo khóa xác định thay vì so cặp tùy ý.

Trong một số nghiệp vụ, so sánh gần bằng dùng cho **kiểm chứng kết quả** là hợp lý, còn so sánh chính xác dùng để xác định **danh tính hoặc khóa dữ liệu**. Hai khái niệm cần tách biệt.

## 9. Những trường hợp đặc biệt cần xử lý

### 9.1. NaN

Với `double a = Double.NaN`, mọi phép `a == a` đều là `false`, và các phép `<`, `<=`, `>`, `>=` liên quan đến NaN cũng là `false`. Đừng giả định biểu thức so sánh gần bằng nhận NaN là “giá trị cần bỏ qua”; hãy quyết định tường minh:

~~~java
if (Double.isNaN(a) || Double.isNaN(b)) {
    // Từ chối, thông báo dữ liệu thiếu, hoặc chính sách riêng.
}
~~~

Đây là đoạn kiểm tra minh họa. Đối với đối tượng wrapper, `Double.equals` có hợp đồng riêng về NaN, khác toán tử primitive `==`.

### 9.2. Vô cực

`Math.abs(Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY)` là NaN, nên ngay cả hai giá trị vô cực cùng dấu cũng không được coi gần bằng bởi biểu thức chênh lệch đơn giản.

Nếu ứng dụng chấp nhận hai vô cực giống nhau, kiểm tra `a == b` **trước** khi tính `Math.abs(a-b)`. Nếu ứng dụng chỉ chấp nhận số hữu hạn, dùng `Double.isFinite` trước.

### 9.3. Hai dạng số không

`+0.0 == -0.0` là `true` cho primitive, nhưng hai bit pattern có dấu khác nhau. Hàm `mixed` coi hai số không này bằng nhau theo quy ước số học. Nếu bit dấu có ý nghĩa (ví dụ một số ngữ cảnh tính toán IEEE 754), hãy định nghĩa tiêu chí riêng hoặc xem `Double.doubleToRawLongBits`/`Double.doubleToLongBits` theo nhu cầu.

### 9.4. Giá trị nhỏ nhất và underflow

`Double.MIN_VALUE` là số `double` dương nhỏ nhất khác 0 (subnormal), **không phải giá trị âm nhất** của `double`. Ở rất gần 0, `relTol * scale` có thể dưới miền biểu diễn và trở thành 0, nên một dung sai tuyệt đối thích hợp thường có vai trò quan trọng.

### 9.5. Phép chia để tính sai số tương đối

Biểu thức `Math.abs(a-b) / Math.max(Math.abs(a), Math.abs(b))` có thể gặp mẫu số 0 khi cả hai bằng 0, hoặc các trường hợp số thực đặc biệt. So sánh bằng phép nhân như `difference <= relTol * scale` tránh được phép chia trực tiếp, nhưng vẫn cần xem overflow/underflow và kiểm tra miền giá trị. Không phải mọi cách cài đặt tương đương về đại số đều tương đương tuyệt đối khi thực thi bằng số thực hữu hạn.

## 10. Phân biệt sai số làm tròn với ổn định thuật toán

Một thuật toán có thể sinh sai số lớn vì **mất chữ số có nghĩa** (catastrophic cancellation), lặp tích lũy sai số hoặc điều kiện bài toán kém, không chỉ vì lựa chọn epsilon sai. Ví dụ khi lấy hiệu của hai số gần nhau, các chữ số có nghĩa chung có thể bị triệt tiêu; kết quả tương đối của hiệu có thể rất thiếu chính xác.

Vì vậy, nếu hai cách tính trên cùng dữ liệu không gần nhau, đừng ngay lập tức **tăng epsilon cho tới khi kiểm thử qua**. Điều đó có thể che lỗi của thuật toán, lỗi chuyển đơn vị, sai điều kiện đầu vào hoặc lựa chọn phương pháp số không ổn định.

Một quy trình hợp lý:

1. Dùng đại lượng/đơn vị đã được xác minh, dự đoán thang giá trị và khoảng sai số có thể chấp nhận.
2. Kiểm tra phương pháp tính có điều kiện tốt không; khi cần, dùng phép toán ổn định hơn hoặc thuật toán chính xác cao hơn.
3. Chọn tiêu chí kiểm thử dựa trên yêu cầu thực tế và phân tích sai số, sau đó cố định nó trong test; không hiệu chỉnh chỉ để giấu test thất bại.
4. Kiểm thử cả giá trị gần 0, giá trị cực lớn/nhỏ, NaN, vô cực và số âm nếu chúng thuộc miền đầu vào.
5. Ghi rõ lý do và phạm vi áp dụng của `absTol` và `relTol` trong tài liệu hoặc tên hằng thay vì một biến toàn cục mơ hồ như `EPSILON`.

Một bài toán tài chính đòi giá trị thập phân chính xác có thể nên dùng `BigDecimal`, phép tính theo đơn vị nhỏ nhất (ví dụ số xu nguyên) hoặc mô hình số học theo đặc tả; thay epsilon không biến `double` thành số thập phân chính xác. Với hình học tính toán, điều kiện định hướng gần thẳng hàng có thể cần predicate robust thay vì so sánh epsilon tùy tiện. Đó là những lựa chọn thuộc **thiết kế bài toán**, không có một hằng dùng chung.

## 11. Các lỗi phổ biến

**Lỗi 1 — Coi `1e-9` là “độ chính xác của double”.**  
`double` có độ phân giải phụ thuộc độ lớn. `1e-9` là một dung sai do ứng dụng lựa chọn, không phải đặc tính cố định của `double`.

**Lỗi 2 — Chỉ dùng sai số tương đối gần số 0.**  
Khi thang đo gần 0, ngưỡng tương đối có thể cực nhỏ hoặc 0; cần cân nhắc một absTol có ý nghĩa miền bài toán.

**Lỗi 3 — Dùng epsilon tuyệt đối mà không để ý đơn vị.**  
Khoảng chênh 0.01 mét và 0.01 giây không thể tùy ý dùng cùng dung sai, trừ khi đặc tả thiết kế nêu rõ.

**Lỗi 4 — Không xử lý NaN và vô cực.**  
`NaN` có phép so sánh đặc biệt; vô cực trừ chính nó sinh NaN. Cần chọn chính sách cho từng loại.

**Lỗi 5 — Xây dựng Comparator “gần bằng”.**  
Quan hệ gần bằng có thể không bắc cầu nên không dùng trực tiếp làm tương đương hoặc thứ tự trong cấu trúc dữ liệu.

**Lỗi 6 — Tăng epsilon khi phát hiện test sai.**  
Điều chỉnh dung sai phải có cơ sở về lỗi tính toán, dữ liệu đầu vào hoặc ràng buộc nghiệm thu; ngưỡng lớn tùy tiện có thể che lỗi thực sự.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao dùng `Math.abs(a-b) <= 1e-9` có thể cho `true` với `a=1e-12`, `b=2e-12` dù chúng khác nhau nhiều theo tỷ lệ?  
**Đáp án:** Sai khác tuyệt đối `1e-12` nhỏ hơn `1e-9`, nhưng `b` gấp đôi `a`; epsilon tuyệt đối quá lớn so với thang giá trị.

**Câu 2.** Vì sao một epsilon tuyệt đối rất nhỏ lại không phù hợp cho `a=1e12`, `b=1e12+0.01`?  
**Đáp án:** Sai khác tuyệt đối khoảng 0.01, nhưng sai khác tương đối chỉ khoảng `1e-14`. Nếu bài toán chấp nhận mức tương đối đó, dùng duy nhất epsilon tuyệt đối `1e-9` là quá nghiêm.

**Câu 3.** Machine epsilon và absTol giống nhau không?  
**Đáp án:** Không. Machine epsilon mô tả khoảng cách biểu diễn liên quan định dạng số thực quanh 1; absTol là tiêu chí chấp nhận sai khác tuyệt đối của **bài toán**.

**Câu 4.** Vì sao `Double.isFinite(a) && Double.isFinite(b)` có thể cần thiết trước khi so sánh gần bằng?  
**Đáp án:** NaN và vô cực không là giá trị hữu hạn. Nếu miền nghiệp vụ chỉ cho phép số hữu hạn, phải loại chúng theo chính sách chứ không phụ thuộc kết quả tình cờ của phép trừ hoặc quan hệ.

**Câu 5.** Với `epsilon=1.0`, vì sao không thể xây dựng `equals` từ quan hệ `|a-b|<=epsilon`?  
**Đáp án:** Có thể `a~b` và `b~c` nhưng `a!~c`, tức quan hệ không bắc cầu, vi phạm hợp đồng tương đương của `equals`.

**Câu 6.** Khi nào dùng `BigDecimal` thay vì tăng epsilon?  
**Đáp án:** Khi yêu cầu giá trị thập phân chính xác, quy tắc làm tròn xác định hoặc biểu diễn tiền tệ theo đặc tả; epsilon chỉ định nghĩa tính “gần bằng”, không khôi phục chữ số thập phân đã mất.

## 13. Ghi nhớ

- Epsilon dùng cho so sánh gần bằng là **dung sai theo ngữ cảnh**, không có giá trị cố định tối ưu cho tất cả chương trình.
- **Sai số tuyệt đối** có đơn vị và phù hợp với cận sai khác cố định; **sai số tương đối** thay đổi theo độ lớn, hữu ích khi dữ liệu trải rộng nhiều thang đo.
- Kết hợp absTol và relTol thường giúp xử lý cả vùng gần 0 và số rất lớn, nhưng các ngưỡng phải được định nghĩa từ yêu cầu cụ thể.
- ULP và machine epsilon mô tả biểu diễn số thực, không đồng nghĩa với dung sai nghiệp vụ.
- Hãy xét NaN, vô cực, underflow/overflow, tính không bắc cầu và độ ổn định thuật toán trước khi biến một phép so sánh gần bằng thành quy tắc quan trọng.