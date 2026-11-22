# NaN không bằng chính nó trong so sánh primitive của Java

Khi so sánh các số thực nguyên thủy `float` và `double`, biểu thức `x == x` **không luôn là `true`**. Nếu `x` là **NaN (Not a Number)**, Java trả `false` cho phép so sánh bằng, kể cả hai vế chính là cùng một biến. Ngược lại, `x != x` trả `true`. Đây là một quy tắc có chủ đích của số thực IEEE 754 được Java áp dụng, không phải lỗi của toán tử `==`.

~~~java
double x = Double.NaN;

System.out.println(x == x);         // false
System.out.println(x != x);         // true
System.out.println(x == Double.NaN); // false
System.out.println(Double.isNaN(x)); // true
~~~

Đây là đoạn mã minh họa cần đặt trong phương thức Java. Trong chương trình thực tế, **nên dùng `Double.isNaN(x)` hoặc `Float.isNaN(x)`** để nhận biết NaN rõ ràng, thay vì dựa vào mẹo `x != x`.

Bài học thuộc chủ đề **so sánh số thực**: tập trung vào toán tử so sánh của primitive, các điều kiện dễ sai khi có NaN, và lý do kết quả của lớp wrapper có thể khác.

## 1. NaN là gì và xuất hiện từ đâu?

`float` (32 bit) và `double` (64 bit) là các kiểu số thực dấu phẩy động của Java. Ngoài các giá trị hữu hạn, chúng có những giá trị đặc biệt như **dương vô cực**, **âm vô cực** và **NaN**. NaN biểu thị kết quả không phải một giá trị số thông thường có thể so sánh theo thứ tự số học.

Các ví dụ tạo NaN hợp lệ trong Java:

~~~java
double a = 0.0 / 0.0;               // NaN
double b = Double.POSITIVE_INFINITY
         - Double.POSITIVE_INFINITY; // NaN
double c = Math.sqrt(-1.0);        // NaN
float d = Float.NaN;                // NaN
~~~

Lưu ý sự khác biệt giữa phép chia số nguyên và phép chia số thực:

- `0.0 / 0.0` là phép chia `double`, cho ra NaN, không ném `ArithmeticException`.
- Phép chia số nguyên cho 0 ném `ArithmeticException` khi được thực thi, kể cả biểu thức `1 / 0`. Đừng nhầm với phép chia số thực `0.0 / 0.0` cho NaN.
- `1.0 / 0.0` cho dương vô cực, **không** phải NaN.
- Một khi NaN tham gia nhiều phép toán số học thông thường, kết quả tiếp tục là NaN, ví dụ `Double.NaN + 10.0`.

NaN có các mẫu bit đặc biệt trong biểu diễn số thực và có thể tồn tại nhiều bit pattern NaN khác nhau. Quy tắc so sánh primitive nói đến **bất kỳ giá trị NaN nào**, không phụ thuộc nó được tạo như thế nào. Ta không cần so sánh hay chỉnh sửa các bit này để nhận diện NaN.

## 2. Quy tắc == và != với primitive float/double

Theo ngữ nghĩa phép so sánh số thực của Java:

- Nếu **một trong hai toán hạng** là NaN, `==` luôn là `false`.
- Nếu **một trong hai toán hạng** là NaN, `!=` luôn là `true`.
- Điều này vẫn đúng khi cả hai toán hạng là NaN, hoặc hai vế lấy từ **cùng một biến**.

| Phép so sánh primitive | Kết quả |
| --- | --- |
| `Double.NaN == Double.NaN` | `false` |
| `Double.NaN != Double.NaN` | `true` |
| `Double.NaN == 1.0` | `false` |
| `Double.NaN != 1.0` | `true` |
| `Float.NaN == Float.NaN` | `false` |
| `Float.NaN != Float.NaN` | `true` |
| `1.0 == 1.0` | `true` |
| `1.0 != 1.0` | `false` |

Việc có NaN làm cho một trực giác quen thuộc, “mọi thứ đều bằng chính nó”, **không đúng đối với phép `==` trên primitive `float`/`double`**. Nói một cách chính xác, quan hệ bằng theo số thực ở đây không mang tính phản xạ trên toàn miền giá trị primitive vì có NaN.

Một biến không phải NaN vẫn so sánh với chính nó bằng `true` theo `==`, kể cả khi nó là `Double.POSITIVE_INFINITY` hay `Double.NEGATIVE_INFINITY`. Ví dụ:

~~~java
double infinity = Double.POSITIVE_INFINITY;
System.out.println(infinity == infinity); // true

double zero = +0.0;
System.out.println(zero == -0.0);         // true
~~~

Hai giá trị `+0.0` và `-0.0` có biểu diễn bit khác nhau, nhưng `==` của primitive coi chúng bằng nhau. Quy tắc đặc biệt của NaN không đồng nghĩa mọi giá trị đặc biệt đều tự bất đẳng.

## 3. Các phép so sánh thứ tự với NaN

NaN còn làm cho các phép so sánh thứ tự `<`, `<=`, `>` và `>=` đều trả về `false` khi **ít nhất một toán hạng** là NaN.

| Biểu thức | Kết quả khi `x = Double.NaN` |
| --- | --- |
| `x < 1.0` | `false` |
| `x <= 1.0` | `false` |
| `x > 1.0` | `false` |
| `x >= 1.0` | `false` |
| `x == 1.0` | `false` |
| `x != 1.0` | `true` |

Không thể coi NaN là số “rất lớn”, “rất nhỏ” hay “bằng chính nó” trong các phép so sánh primitive. NaN được xem là **unordered** so với các giá trị số thực trong quan hệ thứ tự của các toán tử trên.

Hậu quả quan trọng: những cách kiểm tra tưởng tương đương khi dữ liệu là số hữu hạn **không tương đương** nếu dữ liệu có NaN.

~~~java
double x = Double.NaN;

boolean outOfRange = x < 0.0 || x > 100.0; // false
boolean insideRange = x >= 0.0 && x <= 100.0; // false
boolean notInsideRange = !insideRange;        // true
~~~

Biểu thức `x < 0 || x > 100` **không phát hiện được NaN** và có thể cho phép NaN lọt qua nếu ứng dụng chỉ dùng nó để từ chối dữ liệu ngoài miền. Tương tự, `!(x < 0)` là `true` với NaN, nhưng `x >= 0` là `false`. Hai điều kiện không tương đương trên toàn miền `double`.

## 4. Nhận diện NaN bằng API đúng nghĩa

Ưu tiên hai phương thức tĩnh:

~~~java
double x = 0.0 / 0.0;
float y = Float.NaN;

boolean a = Double.isNaN(x); // true
boolean b = Float.isNaN(y);  // true
~~~

Chúng trả `true` đúng khi đối số là NaN và `false` cho các giá trị khác, bao gồm dương/âm vô cực.

Có thể viết:

~~~java
boolean hasNaN = x != x; // true khi x là NaN, dựa trên đặc tính IEEE 754
~~~

Nhưng đây là cách kiểm tra khó đọc hơn. `Double.isNaN(x)` nêu rõ chủ đích, thuận lợi cho review, bảo trì và tìm kiếm trong codebase.

Nếu nghiệp vụ cần chấp nhận **chỉ giá trị số hữu hạn**, `isNaN` là chưa đủ, vì vô cực không phải NaN:

~~~java
double value = Double.POSITIVE_INFINITY;

System.out.println(Double.isNaN(value));   // false
System.out.println(Double.isFinite(value)); // false
~~~

`Double.isFinite(value)` và `Float.isFinite(value)` trả `true` khi giá trị không phải NaN và không phải vô cực. Khi xử lý số đo, tiền tệ quy đổi, xác suất hoặc giới hạn, hãy chọn chính sách rõ ràng: cấm riêng NaN hay cấm cả vô cực.

## 5. Ví dụ Java 17+ độc lập và đầu ra

Tạo tệp `NaNComparisonDemo.java`:

~~~java
public class NaNComparisonDemo {
    public static void main(String[] args) {
        double invalid = 0.0 / 0.0;
        float missing = Float.NaN;

        System.out.println("value: " + invalid);
        System.out.println("self ==: " + (invalid == invalid));
        System.out.println("self !=: " + (invalid != invalid));
        System.out.println("NaN == NaN: " + (invalid == Double.NaN));
        System.out.println("NaN < 1: " + (invalid < 1.0));
        System.out.println("NaN <= 1: " + (invalid <= 1.0));
        System.out.println("NaN > 1: " + (invalid > 1.0));
        System.out.println("NaN >= 1: " + (invalid >= 1.0));
        System.out.println("float self ==: " + (missing == missing));

        System.out.println("Double.isNaN: " + Double.isNaN(invalid));
        System.out.println("Float.isNaN: " + Float.isNaN(missing));
        System.out.println("Double.isFinite: " + Double.isFinite(invalid));

        System.out.println("boxed equals: "
                + Double.valueOf(invalid).equals(Double.valueOf(Double.NaN)));
        System.out.println("Double.compare: "
                + Double.compare(invalid, Double.NaN));

        System.out.println("infinity self ==: "
                + (Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY));
        System.out.println("signed zero ==: " + (+0.0 == -0.0));
        System.out.println("sqrt(-1): " + Math.sqrt(-1.0));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac NaNComparisonDemo.java
java NaNComparisonDemo
~~~

Kết quả:

~~~text
value: NaN
self ==: false
self !=: true
NaN == NaN: false
NaN < 1: false
NaN <= 1: false
NaN > 1: false
NaN >= 1: false
float self ==: false
Double.isNaN: true
Float.isNaN: true
Double.isFinite: false
boxed equals: true
Double.compare: 0
infinity self ==: true
signed zero ==: true
sqrt(-1): NaN
~~~

Giải thích từng nhóm:

1. Phép chia `0.0 / 0.0` tạo NaN, nên `invalid == invalid` vẫn là `false` và `invalid != invalid` là `true`.
2. Các toán tử quan hệ với NaN trả `false`, kể cả `<=` và `>=`, vì không có thứ tự số học với NaN.
3. `Float.NaN` có cùng **quy tắc so sánh primitive** như `Double.NaN`, không phụ thuộc độ rộng 32 hay 64 bit.
4. `Double.isNaN`/`Float.isNaN` nhận diện NaN, còn `Double.isFinite` loại NaN và vô cực.
5. Hai dòng `boxed equals` và `Double.compare` có kết quả khác toán tử `==` primitive theo **hợp đồng API** của lớp wrapper, được giải thích ở phần sau.
6. Vô cực so sánh bằng chính nó cho `true`, hai số không có dấu đối nhau vẫn được coi bằng nhau, và căn bậc hai của số âm trong `Math.sqrt(-1.0)` là NaN.

## 6. Khác biệt với Double.equals, Double.compare và Float tương ứng

Chủ đề “NaN không bằng chính nó” nói về **toán tử so sánh giá trị nguyên thủy**. Java cũng có các API phục vụ so sánh đối tượng, sắp xếp và cấu trúc dữ liệu, với quy ước khác.

| Cách so sánh | Hai giá trị NaN | `+0.0` và `-0.0` | Mục đích |
| --- | --- | --- | --- |
| `doubleA == doubleB` | `false` | `true` | Phép so sánh primitive |
| `Double.valueOf(a).equals(Double.valueOf(b))` | `true` | `false` | Hợp đồng bằng nhau của wrapper |
| `Double.compare(a, b)` | `0` | Khác 0 | Thứ tự xác định, phục vụ sắp xếp |

`Double.equals` coi tất cả các giá trị NaN là bằng nhau theo hợp đồng của lớp `Double`. Nó đồng thời phân biệt bit dấu của hai số 0; `Double.compare` có cùng quy ước thứ tự: `-0.0` đứng trước `+0.0`, và NaN được xếp lớn hơn mọi giá trị số (kể cả dương vô cực). Các quy ước này hữu ích cho sắp xếp, bản đồ có thứ tự và cấu trúc dữ liệu cần quan hệ nhất quán.

Ví dụ đoạn mã minh họa **đặt trong một phương thức Java**:

~~~java
double a = Double.NaN;
double b = Double.NaN;

System.out.println(a == b);  // false (primitive)
System.out.println(Double.valueOf(a).equals(Double.valueOf(b))); // true
System.out.println(Double.compare(a, b) == 0); // true
System.out.println(+0.0 == -0.0);              // true
System.out.println(Double.compare(-0.0, +0.0)); // -1
~~~

Tương tự có `Float.equals` và `Float.compare`. Các API `Double.compare`/`Float.compare` xây dựng một thứ tự toàn phần theo **quy ước của Java**, khác quan hệ thứ tự primitive khi xuất hiện NaN.

Cần tránh nhầm thêm: với hai biến tham chiếu `Double`, toán tử `==` trên **hai đối tượng** có thể so sánh danh tính tham chiếu, không phải nội dung số thực. Nếu một vế là primitive và xảy ra unboxing, phép toán lại theo quy tắc primitive. Vì vậy khi nói “so sánh NaN”, hãy chỉ rõ đang dùng toán tử primitive, wrapper `equals` hay `compare`.

## 7. Lỗi thường gặp khi kiểm tra dữ liệu

### 7.1. So sánh với Double.NaN bằng ==

~~~java
double value = compute();

// Sai: điều kiện luôn false kể cả khi value là NaN.
if (value == Double.NaN) {
    throw new IllegalArgumentException("NaN");
}

// Đúng: nhận diện NaN rõ ràng.
if (Double.isNaN(value)) {
    throw new IllegalArgumentException("NaN");
}
~~~

Ở đây `compute()` là tên phương thức **giả định**, nên đoạn code này chỉ minh họa điều kiện kiểm tra, không phải chương trình chạy độc lập. Vì `Double.NaN == Double.NaN` vốn là `false`, dùng `== Double.NaN` sẽ không bao giờ là cách nhận diện NaN đúng.

### 7.2. Chỉ kiểm tra điều kiện ngoài khoảng

~~~java
double percentage = Double.NaN;

if (percentage < 0.0 || percentage > 100.0) {
    throw new IllegalArgumentException("Out of range");
}
// NaN lọt qua vì cả hai phép so sánh đều false.
~~~

Nếu chỉ chấp nhận tỷ lệ hữu hạn từ 0 đến 100, hãy viết điều kiện bao quát miền đặc biệt:

~~~java
static boolean validPercentage(double value) {
    return Double.isFinite(value) && value >= 0.0 && value <= 100.0;
}
~~~

Đoạn trên là **phương thức minh họa** để đặt trong lớp Java. Khi `value` là NaN, `Double.isFinite(value)` là `false`; khi là vô cực cũng vậy. Chỉ khi giá trị hữu hạn mới cần xét cận dưới và cận trên.

Nếu yêu cầu cho phép vô cực thì hãy định nghĩa quy tắc riêng, không tự động dùng `isFinite`. Ví dụ bài toán tối ưu đôi khi chủ ý dùng `Double.POSITIVE_INFINITY` như một giá trị sentinel.

### 7.3. Suy luận từ phủ định của toán tử thứ tự

~~~java
double x = Double.NaN;
boolean notLess = !(x < 5.0); // true
boolean atLeast = x >= 5.0;   // false
~~~

Với NaN, `!(x < 5)` và `x >= 5` **khác nhau**. Tương tự `!(x == y)` tương đương `x != y`, nhưng `!(x < y)` không có nghĩa `x >= y` khi một bên NaN. Đây là nguyên nhân những cách viết lại điều kiện toán học có thể thay đổi kết quả khi dữ liệu chứa NaN.

### 7.4. Nhầm NaN với null hoặc Infinity

- `NaN` là **một giá trị primitive đặc biệt** của `float`/`double`, không phải `null`.
- `null` là trạng thái của **tham chiếu** như `Double`, không phải giá trị mà primitive `double` chứa được.
- `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` là vô cực, không phải NaN. Có thể kiểm tra bằng `Double.isInfinite` hoặc kiểm tra cả tính hữu hạn bằng `Double.isFinite`.
- Một biến `Double` chứa `null` nếu bị **unbox** để dùng phép toán primitive có thể gây `NullPointerException`; đây là lỗi khác với việc toán tử so sánh nhận NaN.

## 8. NaN trong điều kiện rẽ nhánh và sắp xếp

Xét cách viết:

~~~java
double measurement = Double.NaN;

if (measurement < 0.0) {
    System.out.println("Negative");
} else if (measurement >= 0.0) {
    System.out.println("Nonnegative");
} else {
    System.out.println("Not ordered (NaN)");
}
~~~

Nhánh cuối chạy, bởi cả `measurement < 0.0` và `measurement >= 0.0` đều `false`. Khi thuật toán phân nhánh dựa vào điều kiện thứ tự, phải xử lý NaN rõ ràng trước hoặc có nhánh dự phòng cho trường hợp không có thứ tự.

Khi cần sắp xếp một danh sách có NaN, không nên tạo comparator đơn giản như `(a, b) -> a < b ? -1 : a > b ? 1 : 0`. Comparator đó sẽ trả 0 khi một bên NaN, khiến NaN bị coi ngang hàng với mọi số, và có thể vi phạm tính nhất quán mà thuật toán sắp xếp yêu cầu.

Hãy dùng:

~~~java
java.util.List<Double> values = new java.util.ArrayList<>(
        java.util.List.of(Double.NaN, 2.0, -1.0, 0.0));
values.sort(Double::compare);
// Thứ tự theo Double.compare: -1.0, 0.0, 2.0, NaN
~~~

Đây là **đoạn mã minh họa** để đặt trong một phương thức; `Double::compare` bảo đảm thứ tự theo hợp đồng Java, bao gồm quy tắc NaN đứng sau mọi số. Các dấu phân cách danh sách là ví dụ giải thích, không phải stdout bắt buộc.

## 9. Câu hỏi tự luyện có lời giải

**Câu 1.** Cho `double x = Double.NaN;`, các biểu thức `x == x`, `x != x`, `x <= x` có kết quả gì?  
**Đáp án:** `false`, `true`, `false`. Với NaN, so sánh bằng và so sánh thứ tự đều `false`, còn so sánh khác `true`.

**Câu 2.** `Double.NaN == 5.0` và `Double.NaN > 5.0` có giống kết quả không?  
**Đáp án:** Có, cả hai đều `false`; nhưng lý do không phải NaN là một số nhỏ hơn 5 mà vì NaN không có thứ tự số học với 5.

**Câu 3.** Vì sao `!(x < 10.0)` không luôn tương đương `x >= 10.0`?  
**Đáp án:** Khi `x` là NaN, `x < 10.0` là `false` nên biểu thức phủ định là `true`, nhưng `x >= 10.0` vẫn `false`.

**Câu 4.** Nên dùng gì để kiểm tra một giá trị `double` được phép tham gia phép tính nhưng tuyệt đối không được là NaN?  
**Đáp án:** `!Double.isNaN(value)`. Nếu đồng thời không chấp nhận vô cực thì dùng `Double.isFinite(value)`.

**Câu 5.** Tại sao `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` là `true` còn `Double.NaN == Double.NaN` là `false`?  
**Đáp án:** `Double.equals` áp dụng hợp đồng của wrapper để coi các NaN là bằng nhau; `==` trên primitive áp dụng quy tắc so sánh số thực, theo đó NaN không bằng bất kỳ giá trị nào, kể cả chính nó.

**Câu 6.** Một comparator viết `a < b ? -1 : a > b ? 1 : 0` có lỗi gì khi `a` hoặc `b` là NaN?  
**Đáp án:** Cả `a < b` và `a > b` đều `false`, nên comparator trả 0 cho nhiều cặp không tương đương, có nguy cơ phá vỡ hợp đồng so sánh. Hãy dùng `Double.compare(a, b)` để có quy tắc thứ tự rõ ràng.

## 10. Ghi nhớ

- NaN là giá trị đặc biệt của `float` và `double`; phép `==` primitive với bất kỳ NaN nào trả `false`, ngay cả `x == x`.
- Phép `!=` với NaN trả `true`; `<`, `<=`, `>`, `>=` với NaN đều trả `false`.
- Dùng `Float.isNaN`/`Double.isNaN` để nhận biết NaN. Nếu cấm cả vô cực, dùng `Float.isFinite`/`Double.isFinite`.
- Không suy ra “không nhỏ hơn” thì “lớn hơn hoặc bằng” khi dữ liệu có NaN; kiểm tra miền giá trị phải tính đến trường hợp không có thứ tự.
- `Double.equals` và `Double.compare` có quy ước riêng về NaN để phục vụ so sánh đối tượng và sắp xếp, vì vậy cần phân biệt với `==` primitive.