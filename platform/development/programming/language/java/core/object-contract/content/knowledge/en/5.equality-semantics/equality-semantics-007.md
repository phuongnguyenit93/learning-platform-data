# Vì sao so sánh số thực bằng một ngưỡng sai số có thể mất tính bắc cầu?

## 1. Vấn đề: “gần bằng” có thực sự là “bằng nhau” không?

Khi làm việc với số thực trong Java, ta thường gặp sai số biểu diễn và sai số tính toán của kiểu `double`/`float`. Ví dụ, phép cộng `0.1 + 0.2` không nhất thiết cho cùng giá trị `double` với literal `0.3`. Một kỹ thuật phổ biến để kiểm tra hai kết quả số học có đủ gần nhau là dùng **ngưỡng sai số** (tolerance, hay epsilon):

```java
static boolean approximatelyEqual(double x, double y, double epsilon) {
    return Math.abs(x - y) <= epsilon;
}
```

Đây là một **đoạn minh họa**, chưa xử lý `NaN`, vô cực, tham số không hợp lệ hoặc tràn trong phép trừ. Ý nghĩa thông thường: khoảng cách giữa hai số không lớn hơn `epsilon`.

Vấn đề xuất hiện khi ta đem kết quả “gần bằng” này làm định nghĩa cho `equals()`. Theo hợp đồng `Object.equals(Object)`, tính bắc cầu (transitivity) bắt buộc thỏa:

> Nếu `a.equals(b)` đúng và `b.equals(c)` đúng thì `a.equals(c)` cũng phải đúng, với mọi bộ ba đối tượng `a`, `b`, `c`.

Quan hệ `|x - y| <= epsilon` với `epsilon > 0` **không bảo đảm tính bắc cầu**, mặc dù trông giống phép so sánh bằng nhau. Vì thế một hàm “gần bằng” có thể hữu ích cho việc kiểm tra kết quả đo, nhưng không thích hợp để thay thế `equals()`.

## 2. Phản ví dụ cụ thể trên ba số

Chọn `epsilon = 0.125` và ba giá trị:

- `a = 1.0`;
- `b = 1.09375`;
- `c = 1.1875`.

Các giá trị trên cùng `0.125` đều biểu diễn **chính xác** trong số thực nhị phân (IEEE 754 binary floating-point), nên ta không cần dựa vào sai số làm tròn để có phản ví dụ.

| Phép so sánh | Khoảng cách tuyệt đối | Nhỏ hơn hoặc bằng `0.125`? |
| --- | ---: | --- |
| `a` với `b` | `|1.0 - 1.09375| = 0.09375` | Có, `true` |
| `b` với `c` | `|1.09375 - 1.1875| = 0.09375` | Có, `true` |
| `a` với `c` | `|1.0 - 1.1875| = 0.1875` | Không, `false` |

Kết quả:

```text
a ~ b: true
b ~ c: true
a ~ c: false
```

Dấu `~` ở đây chỉ quan hệ “gần bằng theo epsilon”, **không phải toán tử của Java**.

Vì `a ~ b` và `b ~ c` đều đúng nhưng `a ~ c` sai, quan hệ này không bắc cầu. Đây là lý do cốt lõi: **“gần” theo từng cặp không có nghĩa các điểm ở hai đầu của một chuỗi đều gần nhau**.

### Giải thích bằng bất đẳng thức tam giác

Với số thực, ta có:

```text
|a - c| <= |a - b| + |b - c|
```

Nếu mỗi khoảng `|a-b|` và `|b-c|` không vượt `epsilon`, ta chỉ suy ra:

```text
|a - c| <= 2 * epsilon
```

Ta **không** suy ra được `|a-c| <= epsilon`. Trong ví dụ, hai bước dài `0.09375` gộp lại thành `0.1875`; mỗi bước đạt điều kiện, nhưng tổng vượt ngưỡng `0.125`.

Lập luận áp dụng ngay cả khi các số là số thực toán học với phép tính chính xác tuyệt đối. Sai số làm tròn của `double` có thể làm việc kiểm tra epsilon phức tạp thêm, nhưng **không phải nguyên nhân gốc** của việc mất tính bắc cầu.

## 3. Thử trực tiếp với Java 17+

Lưu chương trình hoàn chỉnh dưới đây thành `FloatingToleranceDemo.java`:

```java
public class FloatingToleranceDemo {
    private static final double EPSILON = 0.125;

    // Đây là phép kiểm "gần bằng" dành cho số đo hữu hạn.
    // Cố ý KHÔNG dùng hàm này làm Object.equals().
    static boolean near(double x, double y) {
        return Double.isFinite(x)
                && Double.isFinite(y)
                && Math.abs(x - y) <= EPSILON;
    }

    // Một khóa phân nhóm minh họa quan hệ bằng nhau đúng nghĩa.
    record BucketKey(int index) {}

    static BucketKey fixedBucket(double value) {
        // Giới hạn miền chỉ để ví dụ chuyển sang int an toàn.
        if (!Double.isFinite(value) || value < -1000 || value > 1000) {
            throw new IllegalArgumentException("Value outside supported range");
        }
        return new BucketKey((int) Math.floor(value / 0.5));
    }

    public static void main(String[] args) {
        double a = 1.0;
        double b = 1.09375;
        double c = 1.1875;

        System.out.println("epsilon: " + EPSILON);
        System.out.println("|a-b|: " + Math.abs(a - b));
        System.out.println("|b-c|: " + Math.abs(b - c));
        System.out.println("|a-c|: " + Math.abs(a - c));
        System.out.println("near(a,b): " + near(a, b));
        System.out.println("near(b,c): " + near(b, c));
        System.out.println("near(a,c): " + near(a, c));

        // Điều kiện tiền đề đúng, nhưng kết luận sai.
        boolean chainIsTransitive =
                !(near(a, b) && near(b, c)) || near(a, c);
        System.out.println("near transitive for this triple: "
                + chainIsTransitive);

        BucketKey ka = fixedBucket(a);
        BucketKey kb = fixedBucket(b);
        BucketKey kc = fixedBucket(c);
        System.out.println("bucket(a): " + ka.index());
        System.out.println("bucket(b): " + kb.index());
        System.out.println("bucket(c): " + kc.index());
        System.out.println("bucket a=b: " + ka.equals(kb));
        System.out.println("bucket b=c: " + kb.equals(kc));
        System.out.println("bucket a=c: " + ka.equals(kc));

        System.out.println("near(NaN,NaN): "
                + near(Double.NaN, Double.NaN));
        System.out.println("near(+inf,+inf): "
                + near(Double.POSITIVE_INFINITY,
                       Double.POSITIVE_INFINITY));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac FloatingToleranceDemo.java
java FloatingToleranceDemo
```

Kết quả stdout chính xác:

```text
epsilon: 0.125
|a-b|: 0.09375
|b-c|: 0.09375
|a-c|: 0.1875
near(a,b): true
near(b,c): true
near(a,c): false
near transitive for this triple: false
bucket(a): 2
bucket(b): 2
bucket(c): 2
bucket a=b: true
bucket b=c: true
bucket a=c: true
near(NaN,NaN): false
near(+inf,+inf): false
```

Những điều cần quan sát:

1. `near(a, b)` và `near(b, c)` đều `true`, nhưng `near(a, c)` là `false`: một phản ví dụ đủ để bác bỏ phát biểu “quan hệ gần bằng này luôn bắc cầu”.
2. Biểu thức `!(P && Q) || R` kiểm tra mệnh đề `(P && Q) => R` cho **một bộ ba**. Kết quả `false` chứng minh bộ ba đã phá vỡ bắc cầu; kết quả `true` trên một bộ ba khác chưa đủ chứng minh hợp đồng đúng trên toàn miền.
3. `BucketKey` là `record` có `equals()`/`hashCode()` dựa trên `index`. Khi `index(a) = index(b)` và `index(b) = index(c)` thì `index(a) = index(c)`; vì vậy quan hệ bằng nhau theo khóa nhóm là bắc cầu. Ba giá trị ở đây đều thuộc nhóm có chỉ số `2`.
4. Nhóm có biên: chẳng hạn `1.49` và `1.51` rất gần nhưng thuộc hai nhóm khác nhau (`Math.floor(x / 0.5)` cho `2` và `3`). **Bằng nhau theo nhóm không tương đương “chênh không quá epsilon”**; chỉ dùng khi nghiệp vụ thật sự định nghĩa các khoảng cố định.
5. `near` chủ ý từ chối `NaN` và vô cực để thể hiện miền dữ liệu là số đo hữu hạn. Đây không phải thiết kế `equals()` vì `equals()` phải phản xạ đối với mọi đối tượng, kể cả đối tượng chứa dữ liệu đặc biệt.

## 4. Tại sao chọn epsilon nhỏ hơn vẫn không giải quyết được?

Giảm epsilon có thể làm số lượng cặp được chấp nhận ít đi, nhưng với **mọi epsilon dương** trên một miền đủ rộng, vẫn có thể tạo ba giá trị:

```text
a = 0
b = 0.75 * epsilon
c = 1.50 * epsilon

|a-b| = 0.75 * epsilon <= epsilon
|b-c| = 0.75 * epsilon <= epsilon
|a-c| = 1.50 * epsilon >  epsilon
```

Đây là chứng minh toán học cho số thực; khi hiện thực bằng `double`, phải tính tới phạm vi, độ phân giải biểu diễn và các phép làm tròn. Vì vậy phát biểu “**bất kỳ epsilon dương đều chắc chắn cho phản ví dụ với mọi tập giá trị double**” là quá mạnh: trên một miền rời rạc hoặc cực nhỏ, có thể không tìm được ba phần tử như vậy. Điều đúng là công thức khoảng cách theo ngưỡng **không đảm bảo bắc cầu theo nguyên lý**, nên không được dùng làm cơ sở tổng quát của `equals()`.

Đổi phép so sánh `<= epsilon` thành `< epsilon` cũng không chữa được. Chọn các khoảng nhỏ hơn epsilon nhưng tổng của chúng vượt epsilon vẫn tạo phản ví dụ. Tương tự, thay ngưỡng tuyệt đối bằng ngưỡng tương đối theo độ lớn `max(|x|, |y|)` có thể hữu ích cho tính toán số, nhưng **không tự đem lại tính bắc cầu**.

## 5. Phân biệt ba nhu cầu khác nhau

| Nhu cầu | Cách làm phù hợp | Tính chất cần lưu ý |
| --- | --- | --- |
| Hai kết quả tính toán/đo lường có đủ gần nhau không? | Phương thức riêng `near`/`withinTolerance` | Quan hệ gần bằng có thể không bắc cầu |
| Hai giá trị mang cùng bản sắc logic trong một đối tượng Java không? | `equals()` và `hashCode()` dựa trên tiêu chí ổn định, nhất quán | Phải tuân thủ phản xạ, đối xứng, bắc cầu, nhất quán, không bằng `null` |
| Hai số thuộc cùng một khoảng phân nhóm nghiệp vụ không? | Chuẩn hóa thành khóa nhóm rồi so sánh khóa | Bằng nhau theo khóa bắc cầu, nhưng có ranh giới cứng |

### a. Khi chỉ cần so sánh gần bằng

Một API rõ ý định có thể nhận tolerance tại thời điểm gọi:

```java
static boolean nearFinite(double x, double y, double epsilon) {
    if (!Double.isFinite(epsilon) || epsilon < 0) {
        throw new IllegalArgumentException("Invalid epsilon");
    }
    return Double.isFinite(x)
            && Double.isFinite(y)
            && Math.abs(x - y) <= epsilon;
}
```

Đây là **phương thức minh họa độc lập**, chưa phải chương trình có `main`. Nó phù hợp khi miền sử dụng là các số hữu hạn, phép trừ không gây tràn và khoảng cách tuyệt đối là tiêu chí đúng. Ví dụ: đánh giá kết quả thuật toán trên dữ liệu có thang đo cố định, kiểm tra sensor trong một dung sai được chỉ định, hoặc so sánh sai số đầu ra trong bài test.

Đối với giá trị có độ lớn rất khác nhau, có thể cần dung sai tương đối, dung sai kết hợp tuyệt đối và tương đối, hoặc kiểm tra ULP (đơn vị của độ chính xác biểu diễn tại vùng giá trị đang xét). Việc chọn cách nào phụ thuộc bài toán số học; **tất cả vẫn là cách kiểm tra độ gần**, không phải lời giải thay thế hợp đồng `equals()`.

Lưu ý trường hợp cực trị: `Math.abs(x-y)` có thể thành `Infinity` khi hai số hữu hạn rất lớn trái dấu làm phép trừ tràn. Một triển khai thư viện số đáng tin cần xác định hành vi với overflow, dưới ngưỡng, `NaN`, `Infinity`, `+0.0`/`-0.0` và epsilon âm/không hữu hạn.

### b. Khi cần định nghĩa `equals()`

Không triển khai kiểu:

```java
// PHẢN VÍ DỤ về cách thiết kế; không chép vào lớp production:
@Override
public boolean equals(Object obj) {
    if (!(obj instanceof Measurement other)) {
        return false;
    }
    return Math.abs(this.value - other.value) <= EPSILON;
}
```

Fragment trên giả định đang ở trong lớp có kiểu `Measurement`, trường `value` và hằng `EPSILON`. Nó cố ý minh họa quy tắc sai, **không phải file chạy độc lập**. Ngoài lỗi bắc cầu, phép so sánh không được quy định rõ cho `NaN`/vô cực và cách tính `hashCode()` có thể vi phạm thêm hợp đồng.

Thay vào đó, trước tiên xác định bản sắc logic: cùng mã định danh? cùng các thành phần giá trị? cùng đơn vị đã chuẩn hóa? cùng khóa đã được lượng tử hóa theo quy tắc nghiệp vụ? Sau đó so sánh **khóa xác định ổn định**. Một lớp bất biến hoặc `record` với các thành phần có quan hệ bằng nhau hợp lệ thường là lựa chọn dễ kiểm soát.

Các giá trị cần gần bằng có thể để nguyên trong record và được so sánh qua phương thức khác, chẳng hạn `measurement.closeTo(other, tolerance)`. Đừng buộc khái niệm “đủ gần” thành “cùng đối tượng logic”.

### c. Khi dùng phân nhóm/lượng tử hóa

Nếu nghiệp vụ cố định giá trị về bội số của bước đo, ví dụ phân vào các vùng `[0.0, 0.5)`, `[0.5, 1.0)`, `[1.0, 1.5)`, hãy tính khóa nhóm trước rồi chỉ so sánh khóa. Các đối tượng được phân loại cùng một khóa tạo thành một **lớp tương đương**.

Tuy nhiên, vị trí gần biên có thể bị chia nhóm dù chênh lệch rất nhỏ; bước nhóm và chính sách làm tròn phải được quyết định theo nghiệp vụ. Trong code dùng `double`, cần nêu giới hạn miền, xử lý giá trị đặc biệt và kiểm soát độ chính xác phép chia/nhân khi tính khóa; không mặc định `Math.round(x / step)` chính xác cho mọi số cực lớn.

## 6. Liên hệ với `hashCode()` và các collection

Các collection như `HashSet` và `HashMap` giả định đối tượng tuân thủ hợp đồng bằng nhau. Nếu đưa epsilon vào `equals()`:

- Một đối tượng `a` có thể được coi bằng `b`, `b` bằng `c` nhưng `a` không bằng `c`. Khái niệm “trùng giá trị” khi tìm kiếm, thêm, xóa và khử trùng lặp sẽ mất tính nhất quán.
- `hashCode()` còn phải thỏa: khi `x.equals(y)` là `true` thì `x.hashCode() == y.hashCode()`. Lấy hash trực tiếp từ số `double` thường không thỏa với các cặp được xem là gần bằng theo epsilon. Làm tròn để hash vào bucket cố định cũng không cứu được quan hệ bằng nhau theo **khoảng cách từng cặp** tại ranh giới bucket.
- Cho mọi đối tượng cùng một hash có thể thỏa điều kiện “bằng nhau thì hash giống nhau” một cách hình thức, nhưng gây nhiều va chạm và **vẫn không sửa được lỗi bắc cầu**.

Tương tự, `TreeSet`/`TreeMap` dùng thứ tự theo `Comparator`. Một comparator trả về `0` khi hai số chỉ “đủ gần” cũng có thể gây quan hệ thứ tự không nhất quán, vi phạm yêu cầu của một thứ tự hợp lệ. Khi cần sắp xếp hoặc tạo khóa, hãy định nghĩa thứ tự/khóa rõ ràng thay vì “gần nhau thì coi như bằng” tùy cặp.

## 7. Những nhầm lẫn Java thường gặp

1. **`==` giữa `double` và `Double.equals` không có cùng hành vi ở mọi giá trị đặc biệt.** Với nguyên thủy `double`, `Double.NaN == Double.NaN` là `false` và `+0.0 == -0.0` là `true`. Với `Double.equals`, các đối tượng chứa giá trị `NaN` được xem bằng nhau và `+0.0` khác `-0.0`. Hai cách có quy tắc khác nhau; tự chọn ngữ nghĩa phù hợp thay vì trộn lẫn chúng.
2. **`Double.compare(x, y) == 0` là so sánh theo thứ tự toàn phần được định nghĩa cho giá trị `double`**, khác kiểm tra gần bằng với epsilon. Nó phân biệt hai dạng zero theo dấu và xếp các dạng NaN vào cùng một nhóm so sánh; nếu dùng kết quả này làm quan hệ bằng nhau, tính bắc cầu được bảo đảm bởi tiêu chí so sánh nhất quán.
3. **Một bộ test ngắn không chứng minh được đúng với mọi bộ ba.** Cần lập luận từ chính quy tắc so sánh; với dung sai, phản ví dụ ba phần tử đã đủ chứng minh sự cố.
4. **Lỗi bắc cầu khác sai số làm tròn.** Cùng một ví dụ có thể dùng các số nhị phân biểu diễn chính xác. Thay thuật toán `double` bằng `BigDecimal` vẫn không khiến “chênh không quá epsilon” trở thành quan hệ bắc cầu.
5. **Bằng nhau theo số học và bằng nhau theo biểu diễn có thể khác.** Với `BigDecimal`, `compareTo` có thể coi `1.0` và `1.00` cùng giá trị số, trong khi `equals` phân biệt scale. Hai tiêu chí khác nhau không tự chứng minh một trong số đó thiếu tính bắc cầu; quan trọng là dùng nhất quán một tiêu chí cho từng quan hệ.

## 8. Câu hỏi tự kiểm tra

**Câu 1.** Với `epsilon = 0.2`, `a = 2.0`, `b = 2.15`, `c = 2.3`, ba phép kiểm gần bằng sẽ ra sao?

Đáp án theo khoảng cách lý tưởng: `|a-b| = 0.15 <= 0.2`, `|b-c| = 0.15 <= 0.2`, nhưng `|a-c| = 0.3 > 0.2`. Đây vẫn là phản ví dụ bắc cầu. Khi chạy `double`, giá trị gần đúng có thể không hiển thị đúng những số thập phân trên, nhưng các khoảng được chọn cách đủ xa ngưỡng để kết quả boolean vẫn như mô tả.

**Câu 2.** Đổi thành `epsilon = 0.001` có giải quyết tận gốc không?

Không. Với miền số thực đủ rộng, ta vẫn có thể chọn hai bước riêng rẽ không vượt `0.001` nhưng tổng vượt `0.001`. Giảm tolerance chỉ thay đổi việc cặp nào được chấp nhận.

**Câu 3.** Vì sao so sánh khóa nhóm hợp lệ về bắc cầu dù đôi khi hai số rất gần lại nằm ở hai nhóm khác nhau?

Vì quan hệ được định nghĩa là **“có cùng khóa”**, không phải “gần nhau”. Phép bằng nhau của khóa ổn định và bắc cầu; ranh giới nhóm là đánh đổi về ngữ nghĩa cần chấp nhận rõ ràng.

**Câu 4.** Khi kiểm thử phép tính dấu phẩy động, có nên luôn dùng `Double.compare(x, y) == 0` không?

Không nhất thiết. Nếu mục tiêu là đánh giá kết quả gần một giá trị kỳ vọng trong giới hạn sai số, dùng phép kiểm dung sai tường minh phù hợp hơn. Nhưng nếu định nghĩa bản sắc logic của đối tượng hoặc khóa collection, không nên sử dụng quan hệ dung sai thiếu bắc cầu.

## Kết luận

**So sánh số thực với ngưỡng epsilon chỉ đảm bảo hai giá trị gần nhau theo từng cặp.** Hai cặp liên tiếp đều đạt ngưỡng vẫn có thể khiến cặp đầu–cuối vượt ngưỡng (`0.09375 + 0.09375 > 0.125`). Đây là đặc tính của quan hệ khoảng cách, không phải lỗi riêng của cách Java làm tròn `double`. Hãy dùng phương thức riêng cho kiểm tra xấp xỉ và dùng một tiêu chí bằng nhau ổn định, có tính bắc cầu, khi thiết kế `equals()`, `hashCode()` hoặc khóa collection.
