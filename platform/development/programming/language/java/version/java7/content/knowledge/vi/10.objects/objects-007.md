# So sánh theo Comparator bằng `Objects.compare` trong Java

## 1. Tình huống sử dụng và mục tiêu

Khi so sánh hai đối tượng Java theo một **quy tắc thứ tự tùy chỉnh**, ví dụ sản phẩm theo giá rồi theo mã, ta thường định nghĩa một `Comparator<T>`. Lớp tiện ích `java.util.Objects` có phương thức `compare` cho phép so sánh hai tham chiếu theo comparator đó, **với một ngoại lệ tối ưu hóa quan trọng**: nếu hai tham chiếu **giống hệt nhau** (`a == b`), kết quả luôn là `0` mà **không gọi comparator**.

Cú pháp tổng quát:

~~~java
int result = Objects.compare(left, right, comparator);
~~~

Đoạn trên minh họa cách gọi, giả sử `left`, `right`, `comparator` đã được khai báo với kiểu tương thích.

Phương thức `Objects.compare` có từ **Java 7** và **vẫn được hỗ trợ trong Java hiện đại**. Bài sử dụng JDK 21, `record` và các API `Comparator` hiện đại để minh họa cách viết đang được dùng hiện nay; không cần JDK cũ hay API legacy.

**Sau bài học, bạn cần làm được:**

- Giải thích chính xác nhánh `a == b` và khi nào `Comparator.compare` thực sự được gọi.
- Đọc dấu của kết quả so sánh; không giả định comparator phải trả đúng `-1`, `0` hoặc `1`.
- Tạo comparator từ thuộc tính bằng `Comparator.comparingInt`, `comparing` và `thenComparing`.
- Phân biệt xử lý `null` của `Objects.compare` với chính sách `null` do `Comparator.nullsFirst` / `nullsLast` cung cấp.
- Tránh nhầm `compare(...) == 0` với `Objects.equals(...)` hoặc `a == b`.
- Tránh comparator có side effect, vi phạm quy tắc thứ tự hoặc làm tràn số khi lấy hiệu hai giá trị.

## 2. Chữ ký và ý nghĩa từng tham số

Khai báo API trong `java.util.Objects`:

~~~java
public static <T> int compare(
        T a,
        T b,
        Comparator<? super T> c)
~~~

Đây là **chữ ký API minh họa**, không phải code độc lập; `Comparator` thuộc `java.util`.

| Thành phần | Ý nghĩa |
| --- | --- |
| `T` | Kiểu của hai đối tượng muốn so sánh |
| `a` | Đối tượng thứ nhất |
| `b` | Đối tượng thứ hai |
| `Comparator<? super T> c` | Quy tắc thứ tự cho `T` hoặc một kiểu cha của `T` |
| `int` trả về | Âm, bằng 0 hoặc dương để biểu diễn thứ tự |

`Comparator<? super T>` dùng wildcard **contravariant** ở vị trí tiêu thụ dữ liệu: comparator nhận một kiểu cha cũng có thể so sánh các đối tượng thuộc `T`. Ví dụ, `Comparator<CharSequence>` có thể dùng cho hai `String` vì `String implements CharSequence`.

Kết quả được diễn giải theo dấu:

| Kết quả | Diễn giải theo comparator `c` |
| --- | --- |
| `result < 0` | `a` đứng **trước** `b` |
| `result == 0` | `a` và `b` **tương đương theo thứ tự so sánh** |
| `result > 0` | `a` đứng **sau** `b` |

Không phải tất cả comparator đều trả chính xác `-1` hay `1`. Ví dụ `String.compareTo` có thể trả số âm/dương lớn hơn về trị tuyệt đối; `Objects.compare` **không tự chuẩn hóa dấu**. Khi cần dấu chuẩn hóa để log hay test, dùng `Integer.signum(result)`; không viết logic chỉ kiểm tra `result == -1`.

## 3. Quy tắc cốt lõi: kiểm tra **cùng tham chiếu** trước khi gọi comparator

Ngữ nghĩa của `Objects.compare(a, b, c)` tương đương:

~~~java
// Mã giả mô tả hành vi, không phải khai báo lại Objects.compare:
return (a == b) ? 0 : c.compare(a, b);
~~~

Điểm cần hiểu:

1. `a == b` với object reference kiểm tra **cùng tham chiếu**, không gọi `equals`.
2. Nếu cùng tham chiếu, trả `0` **ngay lập tức**; `c.compare(...)` không được gọi.
3. Nếu khác tham chiếu, ủy quyền cho `c.compare(a, b)` và trả **đúng giá trị `int`** mà comparator trả về.
4. Không tự tạo natural order, không chọn comparator dự phòng và không tự áp dụng quy tắc `nullsFirst` hay `nullsLast`.
5. Nếu khác tham chiếu mà `c` là `null`, lời gọi sẽ thất bại bằng `NullPointerException`; nếu cùng tham chiếu, nhánh comparator không chạy.

### 3.1. Tại sao `Objects.equals` khác `Objects.compare`?

~~~java
boolean sameValue = Objects.equals(a, b);
int order = Objects.compare(a, b, comparator);
~~~

Đây là hai đoạn minh họa với biến có sẵn:

- `Objects.equals(a, b)` trả **boolean**, so sánh theo `equals` (có xử lý `null`).
- `Objects.compare(a, b, comparator)` trả **int thể hiện thứ tự**, phụ thuộc comparator khi `a != b`.
- `Objects.compare(...) == 0` nghĩa là **tương đương theo comparator** (hoặc cùng tham chiếu), **không chắc** `a.equals(b)` là true.
- Hai object bằng nhau theo `equals` nhưng là **hai instance khác nhau** thì `Objects.compare` **vẫn gọi comparator**.

Ví dụ hai sản phẩm khác mã nhưng cùng giá có thể có `compareByPrice(x, y) == 0` mà `x.equals(y) == false`. Ngược lại, comparator nhất quán thông thường trả 0 cho cùng instance; `Objects.compare` tối ưu trường hợp này nhưng không dùng `equals` để quyết định nhánh.

### 3.2. Comparator có tác dụng phụ là thiết kế không nên dựa vào

Vì `Objects.compare(x, x, comparator)` **bỏ qua** comparator, không được đặt nghiệp vụ quan trọng vào side effect của `compare` như tăng bộ đếm giao dịch, ghi audit log bắt buộc hoặc thay đổi dữ liệu. Trong một comparator đúng chuẩn, việc so sánh phải biểu diễn quy tắc thứ tự ổn định, không phụ thuộc vào số lần bị gọi.

Điều này còn quan trọng khi dùng `List.sort` hoặc `TreeSet`: thuật toán có thể gọi comparator nhiều lần theo chiến lược riêng; số lần gọi không phải một phần hợp đồng nghiệp vụ.

## 4. Tạo comparator có ý nghĩa bằng các API hiện đại

Giả sử có kiểu dữ liệu sản phẩm:

~~~java
record Item(String code, String label, int price) {}
~~~

Đây là **khai báo record minh họa**, có trong Java hiện đại (record trở thành tính năng ổn định ở Java 16). Với sản phẩm có `price` là `int`, cách diễn đạt thứ tự theo giá tăng dần, rồi mã tăng dần là:

~~~java
Comparator<Item> byPriceThenCode = Comparator
        .comparingInt(Item::price)
        .thenComparing(Item::code);
~~~

Đoạn này cần `import java.util.Comparator` và đặt trong ngữ cảnh có khai báo `Item`. Quy tắc:

- `Comparator.comparingInt(Item::price)` so sánh thuộc tính `int price` mà không tạo comparator dựa trên phép trừ dễ tràn số.
- `thenComparing(Item::code)` chỉ dùng mã khi bước so sánh giá trả 0.
- Nếu code có thể `null`, bản mặc định trên có thể thất bại; xem phần xử lý `null`.
- Cách sắp xếp đúng phụ thuộc nghiệp vụ: giá tăng, giá giảm, mã không phân biệt hoa/thường, hoặc quy tắc khác đều phải nêu rõ.

Dùng trực tiếp:

~~~java
int compared = Objects.compare(first, second, byPriceThenCode);
~~~

Nếu cần **sắp xếp cả một collection**, nên truyền comparator trực tiếp cho API sắp xếp:

~~~java
items.sort(byPriceThenCode);
~~~

`Objects.compare` thích hợp khi cần kết quả của **một cặp đối tượng**. Nó không thay thế `Comparator`, cũng không phải một cơ chế sort mới; `List.sort` đã nhận `Comparator` trực tiếp.

### 4.1. Một số comparator thường gặp

| Nhu cầu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Số nguyên tăng dần | `Comparator.comparingInt(Item::price)` | Không dùng phép trừ trực tiếp |
| Tiêu chí chính và phụ | `comparingInt(...).thenComparing(...)` | Phá hòa khi tiêu chí trước bằng nhau |
| Chuỗi không phân biệt hoa/thường | `Comparator.comparing(Item::label, String.CASE_INSENSITIVE_ORDER)` | Dùng comparator riêng cho key |
| Thứ tự giảm dần | `byPriceThenCode.reversed()` | Đảo **toàn bộ** thứ tự ghép |
| Giá trị object `null` ở cuối | `Comparator.nullsLast(byPriceThenCode)` | Xử lý null object trước khi so key |
| Key `label` có thể `null` | `Comparator.comparing(Item::label, Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER))` | Xử lý null **key**, không phải null Item |

Các đoạn trong bảng là **biểu thức minh họa**. `Comparator.comparing(...)`, `thenComparing(...)`, `nullsLast(...)` và `reversed()` có từ Java 8 và vẫn là những API hợp lệ trên JDK hiện đại.

**Phân biệt đảo thứ tự:** Nếu gọi `byPriceThenCode.reversed()` thì cả giá và mã trong chuỗi thứ tự đều bị đảo. Nếu chỉ muốn giá giảm dần nhưng mã tăng dần, hãy ghép một comparator theo giá giảm với comparator mã tăng, thay vì đảo toàn bộ comparator ghép.

## 5. Chương trình Java 21 hoàn chỉnh với các tình huống thực tế

Tạo file `src/main/java/demo/ObjectsCompareExample.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public final class ObjectsCompareExample {
    private ObjectsCompareExample() {}

    record Item(String code, String label, int price) {}

    static int sign(int result) {
        return Integer.signum(result);
    }

    public static void main(String[] args) {
        Item pen = new Item("A", "Pen", 20);
        Item book = new Item("B", "Book", 50);
        Item ruler = new Item("C", "Ruler", 20);

        Comparator<Item> byPriceThenCode = Comparator
                .comparingInt(Item::price)
                .thenComparing(Item::code);

        System.out.println("pen-book=" + sign(Objects.compare(pen, book, byPriceThenCode)));
        System.out.println("ruler-pen=" + sign(Objects.compare(ruler, pen, byPriceThenCode)));
        System.out.println("pen-pen=" + sign(Objects.compare(pen, pen, byPriceThenCode)));

        List<Item> sorted = new ArrayList<>(List.of(book, ruler, pen));
        sorted.sort(byPriceThenCode);
        System.out.println("sorted=" + sorted.stream().map(Item::code).toList());

        Comparator<Item> nullsLast = Comparator.nullsLast(byPriceThenCode);
        System.out.println("null-pen=" + sign(Objects.compare(null, pen, nullsLast)));
        System.out.println("pen-null=" + sign(Objects.compare(pen, null, nullsLast)));
        System.out.println("null-null=" + Objects.compare(null, null, byPriceThenCode));

        AtomicInteger calls = new AtomicInteger();
        Comparator<Item> counted = (left, right) -> {
            calls.incrementAndGet();
            return Integer.compare(left.price(), right.price());
        };
        Objects.compare(pen, pen, counted);
        System.out.println("same-calls=" + calls.get());
        Objects.compare(pen, book, counted);
        System.out.println("distinct-calls=" + calls.get());
        Item penCopy = new Item("A", "Pen", 20);
        System.out.println("equals-not-same=" + (pen.equals(penCopy) && pen != penCopy));
        Objects.compare(pen, penCopy, counted);
        System.out.println("equal-copy-calls=" + calls.get());

        Comparator<Item> byNullableLabel = Comparator.comparing(
                Item::label, Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
        Item withoutLabel = new Item("Z", null, 99);
        System.out.println("null-key=" + sign(
                Objects.compare(pen, withoutLabel, byNullableLabel)));

        try {
            Objects.compare(pen, null, byPriceThenCode);
        } catch (NullPointerException ex) {
            System.out.println("no-null-policy=NullPointerException");
        }
        try {
            Objects.compare(pen, book, null);
        } catch (NullPointerException ex) {
            System.out.println("missing-comparator=NullPointerException");
        }
        System.out.println("same-null-comparator=" + Objects.compare(pen, pen, null));

        int broken = Integer.MIN_VALUE - Integer.MAX_VALUE;
        System.out.println("subtraction-sign=" + sign(broken));
        System.out.println("compare-sign=" + sign(Integer.compare(
                Integer.MIN_VALUE, Integer.MAX_VALUE)));
    }
}
~~~

Từ thư mục chứa `src/`, dùng JDK 21 hoặc JDK hỗ trợ tùy chọn `--release 21`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/ObjectsCompareExample.java
java -cp out demo.ObjectsCompareExample
~~~

**Stdout chính xác** (đã kiểm thử):

~~~text
pen-book=-1
ruler-pen=1
pen-pen=0
sorted=[A, C, B]
null-pen=1
pen-null=-1
null-null=0
same-calls=0
distinct-calls=1
equals-not-same=true
equal-copy-calls=2
null-key=-1
no-null-policy=NullPointerException
missing-comparator=NullPointerException
same-null-comparator=0
subtraction-sign=1
compare-sign=-1
~~~

### Giải thích chi tiết

**(1) `pen-book=-1`:** giá 20 nhỏ hơn 50, nên `pen` đứng trước `book`. Trong output, `sign(...)` chuẩn hóa kết quả về `-1`; không nói rằng mọi comparator thực sự trả đúng `-1`.

**(2) `ruler-pen=1`:** hai giá đều 20, nên `thenComparing(Item::code)` xét `"C"` so với `"A"`; `ruler` đứng sau `pen`.

**(3) `pen-pen=0`:** cùng một tham chiếu, `Objects.compare` trả 0 ngay và không cần gọi comparator.

**(4) `sorted=[A, C, B]`:** `List.sort(byPriceThenCode)` sắp các phần tử theo giá và mã. Khi sắp một danh sách, không cần lặp `Objects.compare` bằng tay.

**(5) `null-pen=1`, `pen-null=-1`:** chính `Comparator.nullsLast(byPriceThenCode)` đặt đối tượng `null` ở cuối. `Objects.compare` chỉ ủy quyền cho comparator khi hai tham chiếu khác nhau.

**(6) `null-null=0`:** hai biến đều `null` nên `a == b` true. `Objects.compare(null, null, byPriceThenCode)` trả 0 mà không gọi comparator `byPriceThenCode`, dù comparator đó không có quy tắc tự xử lý null.

**(7) `same-calls=0`, `distinct-calls=1`:** comparator minh họa có bộ đếm chỉ để xác minh **lần gọi**. Khi hai tham số trỏ tới cùng `pen`, comparator không chạy. Khi so `pen` với `book`, nó chạy một lần. **Không nên** dùng comparator có side effect tương tự làm điều kiện nghiệp vụ trong production.

**(8) `equals-not-same=true`, `equal-copy-calls=2`:** `penCopy` và `pen` là hai record có nội dung như nhau nên `equals` trả true, nhưng `pen != penCopy`. Vì khác tham chiếu, `Objects.compare` vẫn gọi comparator; tổng số lần gọi tăng lên 2. Đây là khác biệt quan trọng giữa **tham chiếu giống nhau** và **giá trị bằng nhau**.

**(9) `null-key=-1`:** đối tượng `withoutLabel` **không null**, nhưng `label` của nó null. Comparator thứ hai dùng `Comparator.nullsLast(...)` cho **thuộc tính label**, khiến `"Pen"` đứng trước `null`. Đây là chính sách **null key**, khác với xử lý **null object**.

**(10) `no-null-policy=NullPointerException`:** `Objects.compare(pen, null, byPriceThenCode)` gọi comparator không hỗ trợ null và ném lỗi. `Objects.compare` tự nó **không bảo đảm null-safe** cho hai đối tượng khác tham chiếu.

**(11) `missing-comparator=NullPointerException`:** `pen != book` nên Java phải gọi `c.compare(...)`, nhưng `c` null.

**(12) `same-null-comparator=0`:** dù `c` null, nhánh `pen == pen` trả 0 trước khi dùng comparator. Đây là **chi tiết về hành vi**, không phải lý do để truyền comparator null trong code thực tế.

**(13) `subtraction-sign=1` vs `compare-sign=-1`:** biểu thức `Integer.MIN_VALUE - Integer.MAX_VALUE` tràn kiểu `int` và cho dấu **sai** nếu được dùng làm comparator. `Integer.compare` tránh lỗi này.

## 6. Xử lý `null`: đối tượng null và thuộc tính null là hai tầng khác nhau

Một sai lầm phổ biến là cho rằng chỉ cần gọi `Objects.compare` là mọi so sánh null sẽ tự an toàn. Thực tế:

| Lời gọi | Hành vi |
| --- | --- |
| `Objects.compare(x, x, c)` | Trả 0 vì cùng tham chiếu |
| `Objects.compare(null, null, c)` | Trả 0, không gọi `c` |
| `Objects.compare(null, x, c)` | Gọi `c.compare(null, x)`; tùy `c` có hỗ trợ null |
| `Objects.compare(x, null, c)` | Gọi `c.compare(x, null)`; tùy `c` có hỗ trợ null |
| `Objects.compare(x, y, null)` với `x != y` | Ném `NullPointerException` |
| `Objects.compare(x, x, null)` | Trả 0 vì nhánh giống tham chiếu; **không khuyến khích** |

### 6.1. Muốn null object đứng đầu hoặc cuối

~~~java
Comparator<Item> nullFirst =
        Comparator.nullsFirst(byPriceThenCode);

Comparator<Item> nullLast =
        Comparator.nullsLast(byPriceThenCode);
~~~

Hai dòng là **mã minh họa** cần có kiểu `Item` và biến `byPriceThenCode`. Những comparator này áp dụng quy tắc cho **toàn bộ tham số `Item`** trước khi đi vào comparator thông thường.

`nullsFirst` đặt null thấp hơn non-null; `nullsLast` đặt null cao hơn non-null. Cả hai trả 0 nếu **hai đối tượng đều null**. Khi không có null, comparator gốc quyết định thứ tự.

### 6.2. Muốn null **trong thuộc tính** đứng cuối

Nếu `Item` có `label` có thể null:

~~~java
Comparator<Item> labelOrder = Comparator.comparing(
        Item::label,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
~~~

Đây là **mã minh họa**. Khi `Item` khác null nhưng `Item.label()` là null, comparator vẫn xử lý được key. Tuy nhiên, nếu **chính `Item` là null**, lời gọi `Item::label` có thể ném `NullPointerException`. Muốn hỗ trợ cả hai tầng, ghép:

~~~java
Comparator<Item> safeForBothLevels =
        Comparator.nullsLast(labelOrder);
~~~

Vì vậy, hỏi rõ: *“Có thể null ở đối tượng đang so sánh, ở thuộc tính được lấy ra, hay cả hai?”* rồi bọc comparator đúng tầng. `Objects.compare` chỉ có tối ưu trường hợp hai tham chiếu giống nhau.

## 7. Phân biệt `Objects.compare`, `Comparator.compare`, `Comparable.compareTo` và `Objects.equals`

| API | Trả về | Quy tắc | Điểm khác |
| --- | --- | --- | --- |
| `Objects.compare(a,b,c)` | `int` | Nếu `a == b` trả 0; nếu không dùng `c.compare` | Bỏ qua comparator với cùng tham chiếu |
| `c.compare(a,b)` | `int` | Theo logic của `c` | **Luôn vào** lời gọi comparator nếu gọi trực tiếp |
| `a.compareTo(b)` | `int` | Natural order do kiểu `a` triển khai `Comparable` | Chỉ cho kiểu có thứ tự tự nhiên; phụ thuộc null policy của implementation |
| `Objects.equals(a,b)` | `boolean` | So sánh bằng nhau theo `equals`, null-safe | **Không** cho thông tin nhỏ hơn/lớn hơn |

`Objects.compare` phù hợp khi quy tắc thứ tự được cung cấp bên ngoài, không muốn ép domain model phải triển khai `Comparable`. Nếu có nhiều tiêu chí sort (giá, tên, mã), dùng `Comparator` để tách chính sách khỏi dữ liệu.

### 7.1. So sánh bằng 0 không đồng nghĩa bằng nhau theo `equals`

~~~java
Comparator<Item> byPrice = Comparator.comparingInt(Item::price);

Item one = new Item("A", "Pen", 20);
Item two = new Item("C", "Ruler", 20);

// byPrice.compare(one, two) == 0, nhưng one.equals(two) == false.
~~~

Đây là đoạn minh họa trong ngữ cảnh có `Item` và `Comparator`. Comparator theo giá coi hai sản phẩm giá 20 là tương đương về **thứ tự giá**, còn record `equals` xét các thành phần giá trị record và có thể coi chúng khác nhau.

Trong cấu trúc `TreeSet` / `TreeMap`, comparator quyết định **các khóa được coi là trùng theo thứ tự** thông qua kết quả 0. Nếu comparator theo giá chỉ nhìn `price`, hai sản phẩm khác mã nhưng cùng giá có thể bị coi là cùng vị trí thứ tự trong `TreeSet`. Thiết kế comparator phải phù hợp ý nghĩa uniqueness của collection.

### 7.2. Hợp đồng comparator đúng chuẩn

Một comparator dùng trong sắp xếp phải duy trì:

- **Đối xứng dấu:** dấu `compare(a,b)` là dấu ngược của `compare(b,a)`.
- **Bắc cầu:** nếu `a > b` và `b > c` thì `a > c`.
- **Nhất quán tương đương:** nếu `compare(a,b) == 0` thì khi so với cùng phần tử thứ ba `z`, dấu thứ tự của `a` và `b` phải phù hợp.

Không viết comparator trả giá trị ngẫu nhiên, phụ thuộc thời gian hoặc mutate dữ liệu trong quá trình compare. `Objects.compare` không cứu được một comparator vi phạm hợp đồng, ngoại trừ nhánh cùng tham chiếu trả 0. Với `List.sort`, comparator không nhất quán còn có thể gây kết quả sai hoặc khiến thuật toán sort báo lỗi về comparator contract.

## 8. Cảnh báo tràn số khi tự viết comparator cho số nguyên

Code ngắn sau **không an toàn**:

~~~java
Comparator<Item> brokenByPrice =
        (left, right) -> left.price() - right.price();
~~~

Lý do: phép trừ `int` có thể **overflow**. Ví dụ `Integer.MIN_VALUE - Integer.MAX_VALUE` cho số dương sau khi tràn, dù số thứ nhất nhỏ hơn số thứ hai. Điều này có thể phá vỡ đối xứng và bắc cầu, làm thuật toán sort không còn đáng tin.

Cách đúng:

~~~java
Comparator<Item> safeByPrice =
        Comparator.comparingInt(Item::price);

// Hoặc dạng tường minh:
Comparator<Item> safeByPrice2 =
        (left, right) -> Integer.compare(left.price(), right.price());
~~~

Đây là các biểu thức minh họa, không phải file chạy độc lập. `Comparator.comparingLong(...)` và `Long.compare(...)` là lựa chọn tương ứng cho `long`; `Comparator.comparingDouble(...)` xử lý `double` theo quy tắc chuẩn. Đừng tự viết phép lấy hiệu rồi cast để so sánh số lớn, nhất là khi domain có giá trị cực đại/cực tiểu.

## 9. Generics và comparator của kiểu cha

`Comparator<? super T>` không yêu cầu comparator phải khai báo đúng chính xác `T`. Ví dụ `Comparator<CharSequence>` có thể so sánh `String` qua độ dài:

~~~java
Comparator<CharSequence> byLength =
        Comparator.comparingInt(CharSequence::length);

int result = Objects.compare("aa", "bbbb", byLength);
System.out.println(Integer.signum(result)); // -1
~~~

Đây là **đoạn minh họa** cần import `Comparator` và `Objects` và đặt trong ngữ cảnh thực thi phù hợp. `String` là subtype của `CharSequence` nên comparator tiêu thụ `CharSequence` có thể nhận hai chuỗi.

Không dùng raw `Comparator` hoặc unchecked cast chỉ để lách generic constraints; nếu compiler báo hai loại không so sánh được, hãy định nghĩa một comparator có type parameter phản ánh đúng tập đối tượng mà nó xử lý.

## 10. Chọn API phù hợp theo mục đích

| Tình huống | Nên dùng | Vì sao |
| --- | --- | --- |
| So một cặp object với quy tắc ngoài | `Objects.compare(a, b, c)` | Một lệnh, có nhánh reference identity |
| Muốn comparator được gọi cả khi hai tham chiếu giống nhau | `c.compare(a, b)` | Không có nhánh bỏ qua (nhưng đừng dựa vào side effects) |
| Sort một danh sách | `list.sort(c)` | API nhận comparator trực tiếp |
| So key theo nhiều mức | `comparingInt(...).thenComparing(...)` | Diễn đạt rõ thứ tự chính/phụ |
| Toàn bộ object có thể null | `Comparator.nullsFirst(c)` hoặc `nullsLast(c)` | Chính sách null ở tầng object |
| Thuộc tính được so sánh có thể null | `Comparator.comparing(key, Comparator.nullsLast(keyC))` | Chính sách null ở tầng key |
| Chỉ muốn biết hai giá trị có bằng nhau không | `Objects.equals(a, b)` | `boolean` thay vì thứ tự |
| So `int` hoặc `long` | `Integer.compare` / `Long.compare` / `comparingInt` / `comparingLong` | Tránh overflow |
| Cần natural order của một kiểu | `Comparable.compareTo` hoặc `Comparator.naturalOrder()` | Phù hợp thứ tự tự nhiên, nếu type cho phép |
| Dữ liệu có thể cần uniqueness theo khóa | Comparator phản ánh **định danh hoặc unique key** | Tránh `TreeSet` coi hai bản ghi khác nhau là trùng |

**Lưu ý về hiệu năng:** nhánh `a == b` có thể tránh một lần comparator chạy, nhưng không nên mặc định `Objects.compare` nhanh hơn hay là lựa chọn bắt buộc ở mọi vị trí. Ưu tiên ý nghĩa rõ ràng, comparator đúng hợp đồng và benchmark khi có vấn đề hiệu năng thực tế.

## 11. Những sai lầm dễ gặp

**Sai lầm 1: “`Objects.compare` tự null-safe giống `Objects.equals`.”**

Sai. Chỉ trường hợp **hai đối số là cùng tham chiếu** (bao gồm cả hai đều null) trả 0 trước khi gọi comparator. Một bên null, bên kia không null thì cần comparator hỗ trợ null.

**Sai lầm 2: “`compare(a,b) == 0` nghĩa là `a.equals(b)`.”**

Không nhất thiết. Comparator có thể cố ý chỉ xét giá tiền, độ dài, tên không phân biệt hoa thường hoặc một khóa con. `TreeSet` và `TreeMap` dùng kết quả của comparator để quyết định quan hệ thứ tự và tính duy nhất theo thứ tự.

**Sai lầm 3: “Comparator luôn trả `-1`/`0`/`1`.”**

Sai. Hợp đồng yêu cầu **dấu** âm/không/dương, không quy định độ lớn. Khi cần một trong ba dấu cho log, dùng `Integer.signum`.

**Sai lầm 4: “Truyền comparator null vẫn dùng được vì đôi khi trả 0.”**

Không. Cùng tham chiếu có thể che lỗi do shortcut. Với hai tham chiếu khác nhau, sẽ ném `NullPointerException`. Hãy truyền comparator hợp lệ.

**Sai lầm 5: “Comparator của thuộc tính null-safe sẽ tự xử lý cả object null.”**

Không. `Comparator.comparing(Item::label, nullsLast(...))` chỉ giải quyết trường hợp `label` null nếu `Item` không null. Nếu cả `Item` cũng có thể null, bọc thêm một lớp `Comparator.nullsLast(...)` bên ngoài.

**Sai lầm 6: “Lấy hiệu hai số là comparator chuẩn.”**

Không an toàn nếu overflow. `Integer.compare`, `Long.compare` và `comparingInt` là cách ngắn gọn và chính xác.

**Sai lầm 7: “Dùng `Objects.compare` để sort sẽ tốt hơn truyền `Comparator` trực tiếp.”**

Không cần. `List.sort` đã hiểu comparator; `Objects.compare` phù hợp khi muốn **so một cặp** theo quy tắc cụ thể.

## 12. Tự luyện và đáp án

**Câu 1.** `Objects.compare(x, x, null)` trả gì? Có nên truyền comparator null không?

**Đáp án:** Trả `0` do cùng tham chiếu, nhưng **không nên** truyền null comparator; với hai tham chiếu khác nhau, method sẽ cố gọi `compare` trên null và gặp `NullPointerException`.

**Câu 2.** `Objects.compare(null, null, Comparator.naturalOrder())` trả gì? Vì sao?

**Đáp án:** Trả `0` trước khi gọi comparator. `Comparator.naturalOrder()` tự nó không hỗ trợ null, nhưng trong trường hợp này nó không hề chạy.

**Câu 3.** Với `Comparator.comparingInt(Item::price)`, hai `Item` khác mã nhưng cùng giá trả 0. Có nên coi chúng là cùng sản phẩm không?

**Đáp án:** Không nhất thiết. Comparator này chỉ xét giá, nên kết quả 0 chỉ nói tương đương về thứ tự giá. Nếu dùng trong `TreeSet` và cần giữ các sản phẩm khác mã, thêm tie-breaker như `thenComparing(Item::code)`.

**Câu 4.** Muốn đưa cả object `null` lẫn `Item.label() == null` xuống cuối danh sách, phải bọc comparator ở những tầng nào?

**Đáp án:** Dùng `Comparator.nullsLast(...)` để xử lý **label key** trong `Comparator.comparing(...)`, rồi bọc comparator của toàn bộ `Item` bằng `Comparator.nullsLast(...)` để xử lý **object null**.

**Câu 5.** Nếu `x` và `y` là hai instance riêng nhưng `x.equals(y) == true`, `Objects.compare(x, y, c)` có bỏ qua `c` không?

**Đáp án:** Không. Shortcut chỉ kiểm tra `x == y`. Vì khác tham chiếu, comparator vẫn chạy và quyết định giá trị trả về.

**Câu 6.** Vì sao comparator `(a,b) -> a.price() - b.price()` không an toàn?

**Đáp án:** Phép trừ số nguyên có thể overflow, cho dấu sai. Dùng `Integer.compare` hoặc `Comparator.comparingInt` thay thế.

**Câu 7.** Muốn sắp xếp toàn bộ `List<Item>`, nên dùng `Objects.compare` cho từng cặp do mình tự lặp hay `items.sort(comparator)`?

**Đáp án:** Dùng `items.sort(comparator)`. Nó là API sort chính thức; `Objects.compare` chỉ trả kết quả so sánh của một cặp.

## 13. Checklist và tài liệu chính thức

- [ ] Nhớ chính xác công thức: `a == b ? 0 : c.compare(a, b)`.
- [ ] Hiểu `==` là **tham chiếu**; `equals` có ngữ nghĩa khác.
- [ ] Chỉ suy diễn theo **dấu** của kết quả comparator, không đòi đúng `-1` hoặc `1`.
- [ ] Truyền comparator không null; không phụ thuộc nhánh shortcut để che bug.
- [ ] Thiết kế null policy cho **object** và **key** theo hai tầng khác nhau khi cần.
- [ ] Dùng `comparingInt` / `Integer.compare` để tránh tràn số.
- [ ] Nếu có tie-breaker, ghép `thenComparing` theo đúng mục tiêu sắp xếp.
- [ ] Đảm bảo comparator có thứ tự ổn định, bắc cầu, đối xứng dấu; tránh side effect.
- [ ] Với `TreeSet` / `TreeMap`, cân nhắc hệ quả của `compare == 0` đối với uniqueness.
- [ ] Với sorting collection, ưu tiên truyền comparator trực tiếp cho `sort`.
- [ ] Biên dịch ví dụ Java 21 bằng `javac --release 21 -Xlint:all` và đối chiếu stdout đầy đủ.

**Tài liệu chính thức và hiện vẫn áp dụng:**

- [Javadoc Java SE 21 — `Objects.compare`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#compare(T,T,java.util.Comparator)): quy tắc trả 0 cho tham chiếu giống nhau và ủy quyền cho `Comparator.compare`.
- [Javadoc Java SE 21 — `Comparator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html): quy tắc thứ tự, `comparing`, `comparingInt`, `thenComparing`, `nullsFirst` và `nullsLast`.
- [Javadoc Java SE 21 — `Objects.equals`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)): so sánh bằng nhau, xử lý null.
- [Javadoc Java SE 21 — `List.sort`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)): cách sắp xếp List với comparator.
- [Javadoc Java SE 21 — `Integer.compare`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#compare(int,int)): cách so sánh số nguyên mà không dùng phép trừ dễ overflow.

**Kết luận:** `Objects.compare` là cầu nối nhỏ gọn giữa hai đối tượng và một `Comparator` có sẵn, với quy tắc đặc biệt **cùng tham chiếu trả 0, không gọi comparator**. Hãy định nghĩa comparator ổn định, tường minh null policy, tránh nhầm kết quả thứ tự với `equals` và dùng API sắp xếp trực tiếp khi làm việc với cả collection. Những hướng dẫn này vẫn phù hợp với JDK hiện đại, không phụ thuộc API legacy.
