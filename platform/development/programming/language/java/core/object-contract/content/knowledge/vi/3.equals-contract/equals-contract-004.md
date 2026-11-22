# Tính bắc cầu giữa ba đối tượng trong `equals()`

## 1. Tính bắc cầu là gì?

Trong Java, `Object.equals(Object)` xác định hai đối tượng có được xem là **bằng nhau về mặt logic** hay không. Một yêu cầu bắt buộc của hợp đồng `equals()` là **tính bắc cầu (transitivity)**:

> Với ba tham chiếu khác `null` là `a`, `b`, `c`: nếu `a.equals(b)` là `true` và `b.equals(c)` là `true` thì `a.equals(c)` cũng phải là `true`.

Có thể viết:

```text
a ==(equals)== b  và  b ==(equals)== c
                    => a ==(equals)== c
```

Ở đây, “bằng nhau” là kết quả của `equals()`, **không nhất thiết là cùng một đối tượng trong bộ nhớ** (`a == b`). Ba đối tượng khác nhau vẫn có thể mang cùng giá trị và `equals()` trả về `true` cho cả ba cặp.

Ví dụ đúng: ba đối tượng đại diện cùng mã định danh bất biến `"A-101"`. Khi `a` bằng `b` theo mã này và `b` bằng `c` theo cùng mã, `a` bắt buộc bằng `c`. Quy tắc phải áp dụng nhất quán cho **mọi bộ ba** thuộc kiểu đối tượng đó, chứ không chỉ bộ ba được chọn để kiểm thử.

Tính bắc cầu là một thành phần trong hợp đồng đầy đủ của `equals()`: phản xạ, đối xứng, bắc cầu, nhất quán và trả về `false` khi so sánh với `null`. Bài này tập trung vào tính bắc cầu; các tính chất còn lại vẫn phải được đảm bảo khi triển khai thực tế.

## 2. Phản ví dụ: coi hai số “đủ gần” là bằng nhau

Giả sử một lớp đo khoảng cách quyết định hai giá trị bằng nhau khi chênh lệch không quá **10 mm**. Với ba đối tượng lưu lần lượt `0 mm`, `8 mm` và `16 mm`:

| Cặp đối tượng | Độ lệch | Kết quả “chênh ≤ 10 mm” |
| --- | ---: | --- |
| `a(0)` và `b(8)` | `8 mm` | `true` |
| `b(8)` và `c(16)` | `8 mm` | `true` |
| `a(0)` và `c(16)` | `16 mm` | `false` |

Ta có `a.equals(b) && b.equals(c)` là `true` nhưng `a.equals(c)` là `false`. Đây là **vi phạm trực tiếp tính bắc cầu**.

Nguyên nhân không nằm ở sai số số thực: ví dụ sử dụng số nguyên. Quan hệ “cách nhau tối đa 10 đơn vị” cho phép chuỗi các bước nhỏ tích lũy thành khoảng cách lớn hơn 10; vì thế nó không tạo thành quan hệ bằng nhau đúng nghĩa. Thay `10` bằng bất kỳ dung sai dương cố định nào vẫn có nguy cơ tương tự.

## 3. Chương trình Java 17 chạy được: lỗi và hai cách thiết kế đúng

Lưu toàn bộ mã sau vào tệp `EqualsTransitivityDemo.java`. Lớp `NearReading` **cố ý sai về tính bắc cầu** để minh họa; đừng dùng cách định nghĩa `equals()` này trong ứng dụng. Hai kiểu `ExactReading` và `BucketReading` bên dưới minh họa các quan hệ bằng nhau hợp lệ.

```java
import java.util.List;

public class EqualsTransitivityDemo {

    // PHẢN VÍ DỤ: equals() dựa trên khoảng cách tối đa 10 mm.
    static final class NearReading {
        private final int millimeters;

        NearReading(int millimeters) {
            this.millimeters = millimeters;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof NearReading that)) {
                return false;
            }
            return Math.abs((long) millimeters - that.millimeters) <= 10;
        }

        @Override
        public int hashCode() {
            return 0; // Chỉ để cô lập lỗi bắc cầu; hash kém hiệu quả.
        }
    }

    // CÁCH ĐÚNG 1: giá trị mm phải bằng chính xác.
    record ExactReading(int millimeters) {}

    // CÁCH ĐÚNG 2: so sánh một khóa phân nhóm đã định nghĩa rõ.
    record BucketReading(int bucket) {
        static BucketReading fromMillimeters(int millimeters) {
            return new BucketReading(Math.floorDiv(millimeters, 10));
        }
    }

    // Kiểm tra TẤT CẢ bộ ba trong một tập mẫu hữu hạn.
    static <T> boolean isTransitiveOn(List<T> values) {
        for (T a : values) {
            for (T b : values) {
                for (T c : values) {
                    if (a.equals(b) && b.equals(c) && !a.equals(c)) {
                        return false;
                    }
                }
            }
        }
        return true;
    }

    public static void main(String[] args) {
        NearReading a = new NearReading(0);
        NearReading b = new NearReading(8);
        NearReading c = new NearReading(16);
        System.out.println("near a=b: " + a.equals(b));
        System.out.println("near b=c: " + b.equals(c));
        System.out.println("near a=c: " + a.equals(c));
        System.out.println("near transitive: "
                + isTransitiveOn(List.of(a, b, c)));

        ExactReading p = new ExactReading(8);
        ExactReading q = new ExactReading(8);
        ExactReading r = new ExactReading(8);
        System.out.println("exact p=q: " + p.equals(q));
        System.out.println("exact q=r: " + q.equals(r));
        System.out.println("exact p=r: " + p.equals(r));
        System.out.println("exact transitive: "
                + isTransitiveOn(List.of(p, q, r)));

        BucketReading u = BucketReading.fromMillimeters(0);
        BucketReading v = BucketReading.fromMillimeters(8);
        BucketReading w = BucketReading.fromMillimeters(16);
        System.out.println("bucket u=v: " + u.equals(v));
        System.out.println("bucket v=w: " + v.equals(w));
        System.out.println("bucket transitive: "
                + isTransitiveOn(List.of(u, v, w)));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac EqualsTransitivityDemo.java
java EqualsTransitivityDemo
```

Kết quả chuẩn:

```text
near a=b: true
near b=c: true
near a=c: false
near transitive: false
exact p=q: true
exact q=r: true
exact p=r: true
exact transitive: true
bucket u=v: true
bucket v=w: false
bucket transitive: true
```

Giải thích:

- `NearReading` dùng `Math.abs((long) millimeters - that.millimeters)` để tránh tràn số khi trừ hai giá trị `int` cực trị. Dù phép tính khoảng cách an toàn, **quy tắc bằng nhau vẫn sai** vì không bắc cầu.
- `ExactReading` là `record`; Java tự cung cấp `equals()` và `hashCode()` dựa trên thành phần `millimeters`. Ba bản ghi cùng giá trị `8` bằng nhau theo mọi cặp.
- `BucketReading` chuyển dữ liệu thành **khóa phân nhóm cố định**: `Math.floorDiv(value, 10)`. Hai bản ghi bằng nhau khi có cùng `bucket`. `0` và `8` cùng nhóm `0`; `16` ở nhóm `1`. Khi `bucket(a) = bucket(b)` và `bucket(b) = bucket(c)` thì chắc chắn `bucket(a) = bucket(c)`.
- Phép kiểm `isTransitiveOn` xét mọi bộ ba của **tập mẫu truyền vào**, có chi phí `O(n³)` nên phù hợp với bài kiểm thử nhỏ. Kết quả `true` trên một tập mẫu **không chứng minh** lớp đúng với mọi giá trị có thể có; cần kết hợp lý luận về quy tắc so sánh.

Chú ý: phân nhóm có biên cứng. Ví dụ `9 mm` và `10 mm` rất gần nhưng thuộc hai nhóm khác nhau. Chỉ chọn mô hình này khi ý nghĩa nghiệp vụ thực sự là “cùng nhóm”; không dùng nó để giả vờ tái tạo quy tắc “cách nhau tối đa 10 mm”.

## 4. Thiết kế `equals()` thế nào để giữ tính bắc cầu?

### Cách A — so sánh khóa hoặc trạng thái bất biến, nhất quán

Nếu hai đối tượng biểu diễn cùng thực thể khi có cùng mã định danh bất biến, hãy so sánh **chính mã đó**. Với value object, so sánh đầy đủ tập thuộc tính được định nghĩa là bản sắc logic. Dùng `record` khi dữ liệu phù hợp với ngữ nghĩa giá trị; Java sẽ tạo các phương thức bằng nhau theo thành phần.

Ví dụ một value object đơn giản:

```java
record DocumentKey(String namespace, long id) {}
```

`new DocumentKey("docs", 7)` bằng một `DocumentKey` khác có cùng `namespace` và `id`. Nếu `a`, `b` và `c` có cùng cặp thuộc tính đó thì tính bắc cầu suy ra từ tính bắc cầu của phép so sánh thành phần. Mã trên là **đoạn minh họa**, không phải chương trình độc lập.

Nếu tự viết `equals()`, cần kiểm tra kiểu đối tượng và so sánh **cùng một bộ tiêu chí** ở mọi lần gọi. Tránh thay đổi chính sách dựa vào phía nào của phép so sánh, trạng thái toàn cục, thời điểm, hoặc nhánh kiểu lớp khác nhau.

### Cách B — chuẩn hóa thành dạng đại diện (canonical form)

Nếu nghiệp vụ xem các cách biểu diễn là giống nhau (ví dụ mã không phân biệt chữ hoa/thường), chuẩn hóa **một lần theo quy tắc ổn định**, rồi so sánh các giá trị chuẩn hóa. Một hàm chuẩn hóa xác định `f` tạo quan hệ `a ~ b` khi `f(a).equals(f(b))`. Vì phép bằng nhau trên giá trị chuẩn hóa là bắc cầu, quan hệ này cũng bắc cầu nếu `f` ổn định và có ngữ nghĩa đúng.

Các quy tắc chuẩn hóa phải được quy định rõ: chuẩn hóa Unicode, khoảng trắng, chữ hoa/thường theo locale phù hợp, đơn vị đo hoặc mức làm tròn cố định. Không nên tùy tiện cắt chữ, làm tròn hay đổi locale vì có thể vô tình gộp những giá trị cần phân biệt.

### Cách C — tách “gần nhau” khỏi “bằng nhau”

Nếu cần hỏi hai phép đo có gần nhau trong một sai số cho phép, hãy tạo một phương thức riêng như `withinTolerance(other, tolerance)`. Đây là **quan hệ xấp xỉ**, không có nghĩa vụ bắc cầu, và không nên được sử dụng làm `equals()`.

```java
static boolean withinTolerance(long a, long b, long tolerance) {
    if (tolerance < 0) {
        throw new IllegalArgumentException("tolerance must be nonnegative");
    }
    // Ví dụ giới hạn đầu vào để tránh tràn khi trừ:
    return Math.abs((double) a - (double) b) <= tolerance;
}
```

Đoạn minh họa trên dùng `double` cho hiệu để tránh tràn số nguyên nhưng **có thể mất độ chính xác với số `long` rất lớn**. Trong code cần chính xác tuyệt đối cho mọi `long`, hãy dùng `BigInteger` hoặc phép so sánh trừ có kiểm soát. Với dữ liệu đo lường thực tế, còn phải xác định sai số tuyệt đối, tương đối, đơn vị và cách xử lý `NaN`/vô cực nếu dùng số thực. Việc dùng API xấp xỉ độc lập giúp không làm sai hợp đồng `equals()`.

## 5. Vì sao lỗi này ảnh hưởng đến Java Collections?

`HashSet`, `HashMap` và nhiều thao tác tìm kiếm/deduplicate dựa trên việc `equals()` biểu diễn **một quan hệ bằng nhau ổn định**. Nếu `a` bằng `b`, `b` bằng `c` nhưng `a` khác `c`, ý nghĩa “một phần tử tương đương” trở nên mâu thuẫn: thao tác thêm, tìm, loại trùng có thể cho kết quả khó dự đoán theo dữ liệu và thứ tự thao tác. Vì thế lỗi không chỉ làm hỏng một biểu thức `if`.

Bắc cầu và `hashCode()` là hai yêu cầu liên quan nhưng **khác nhau**:

1. Nếu `x.equals(y)` là `true` thì `x.hashCode() == y.hashCode()` phải đúng.
2. Mã băm giống nhau **không bắt buộc** đồng nghĩa hai đối tượng bằng nhau.
3. Sửa `hashCode()` không thể chữa một quan hệ `equals()` không bắc cầu.

Trong `NearReading` ở ví dụ, `hashCode()` cố ý trả về `0` cho mọi đối tượng để **không vi phạm quy tắc “equals ⇒ hash bằng nhau”** trong khi phơi bày lỗi bắc cầu. Cách dùng hằng số này làm tất cả phần tử rơi vào cùng nhóm băm và có thể giảm hiệu suất nghiêm trọng; không phải cách cài đặt nên áp dụng. Với kiểu hợp lệ, hãy tính hash từ đúng các thuộc tính góp phần xác định `equals()`, hoặc để `record` sinh hộ.

Một lưu ý khác: những thuộc tính được dùng làm khóa trong `HashMap`/`HashSet` nên ổn định khi đối tượng đang nằm trong collection. Thay đổi các trường tham gia `equals()`/`hashCode()` sau khi chèn có thể khiến việc tìm kiếm thất bại, ngay cả khi quy tắc so sánh về mặt toán học vẫn bắc cầu.

## 6. Những trường hợp dễ nhầm với lỗi bắc cầu

- **Tính đối xứng khác tính bắc cầu.** Nếu `a.equals(b)` khác `b.equals(a)`, đó là lỗi đối xứng. Các kiểu cha/con tự viết `equals()` theo những trường khác nhau có thể mắc lỗi đối xứng, bắc cầu hoặc cả hai; phải kiểm tra từng tính chất riêng.
- **`==` khác `equals()`.** `==` so sánh hai tham chiếu có cùng chỉ đến một đối tượng hay không; nó không phải định nghĩa bản sắc logic của value object.
- **`BigDecimal.compareTo()` và `BigDecimal.equals()` có tiêu chí khác nhau.** Ví dụ `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0`, trong khi hai đối tượng đó không `equals()` vì khác scale. Đây **không phải bằng chứng vi phạm tính bắc cầu**: chỉ là hai quan hệ có ngữ nghĩa khác nhau. Đừng trộn tiêu chí của hai phương thức trong một lập luận.
- **`Objects.equals(a, b)` chỉ hỗ trợ null-safe.** Nó gọi `a.equals(b)` khi `a` không null; không tự sửa logic bất bắc cầu của lớp.
- **Tính nhất quán theo thời gian cũng quan trọng.** Nếu `equals()` phụ thuộc dữ liệu biến đổi, đồng hồ hoặc ngữ cảnh không ổn định, cùng cặp đối tượng có thể cho kết quả khác nhau ở các lần gọi; đó là vấn đề cần xử lý bên cạnh bắc cầu.

## 7. Cách kiểm tra khi review hoặc viết test

Với một lớp có `equals()` tự viết, hãy lần lượt:

1. **Xác định bản sắc logic:** cụ thể thuộc tính/khóa nào làm hai đối tượng bằng nhau? Định nghĩa đó có nhất quán cho tất cả đối tượng, lớp con và dữ liệu biên không?
2. **Tạo bộ ba có chủ đích:** chọn `a`, `b`, `c` sao cho `a.equals(b)` và `b.equals(c)` đều `true`; khẳng định `a.equals(c)` cũng `true`. Đặc biệt thử các điểm sát ngưỡng, khác kiểu lớp, trạng thái rỗng và giá trị cực trị nếu liên quan.
3. **Kiểm tra cả hợp đồng:** `a.equals(a)` đúng; `a.equals(b) == b.equals(a)`; lặp lại kết quả với trạng thái không đổi; `a.equals(null)` sai; `equals` đúng thì hash phải bằng nhau.
4. **Kiểm tra với collection:** thử các tình huống thêm/tìm/xóa với các đối tượng tương đương, đồng thời giữ khóa bất biến. Test collection bổ sung bằng chứng nhưng không thay thế phép kiểm bộ ba.
5. **Lý giải tổng quát:** đối chiếu thuật toán với định nghĩa quan hệ tương đương. Ví dụ “cùng mã bất biến” hoặc “cùng khóa chuẩn hóa” có lập luận bắc cầu rõ ràng; “chênh không quá epsilon” thì không.

Một mẫu assertion để dùng trong test (giả sử đã tạo sẵn ba đối tượng `a`, `b`, `c`):

```java
if (a.equals(b) && b.equals(c) && !a.equals(c)) {
    throw new AssertionError("equals() vi phạm tính bắc cầu");
}
```

Đây là **fragment cho test**, không phải một file Java độc lập. Khi `a`, `b`, `c` là ba `NearReading(0)`, `NearReading(8)`, `NearReading(16)` trong chương trình phía trên, assertion sẽ ném lỗi như mong đợi; khi dùng định nghĩa bằng nhau đúng, không được có bộ ba phản ví dụ.

## 8. Ghi nhớ

Tính bắc cầu nói rằng **`a.equals(b)` và `b.equals(c)` cùng đúng thì `a.equals(c)` bắt buộc đúng**. Nó bảo đảm các đối tượng được xem là “cùng giá trị” tạo thành những nhóm tương đương nhất quán. Không dùng khoảng sai số, quy tắc “gần giống”, hoặc tiêu chí so sánh thay đổi theo đối tượng để định nghĩa `equals()`. Hãy định nghĩa khóa/trạng thái bằng nhau rõ ràng; nếu cần xấp xỉ, tách nó thành một thao tác riêng.
