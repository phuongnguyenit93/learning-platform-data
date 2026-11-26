# Phép toán số học, so sánh, lựa chọn phần tử và kết hợp mask

## 1. Phạm vi và phiên bản sử dụng

Trong chương **Vector API** của module `JAVA_VERSION_JAVA22`, bài này tập trung vào nhóm thao tác còn hữu ích khi viết mã SIMD trên Java hiện đại: tính toán theo lane, tạo điều kiện bằng phép so sánh, kết hợp mask và chọn giá trị đầu ra.

Các khái niệm này đã có trong Vector API của Java 22 và tiếp tục hiện diện trong API hiện hành. Bài đối chiếu với **JDK 27**; tại mốc tài liệu này, Vector API vẫn là **incubator**, được phát triển qua JEP 537, chưa phải API chính thức của Java SE. [Javadoc Vector API Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html), [Oracle: thay đổi trong JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html).

Vector API biểu đạt phép tính SIMD trên các lane dữ liệu. Nó không tự tạo nhiều tác vụ Java để xử lý từng phần tử. Khả năng tăng tốc phụ thuộc phần cứng, JVM và mã được sinh ra. [Javadoc: package jdk.incubator.vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html).

## 2. Ba loại giá trị cần phân biệt

| Thành phần | Vai trò trong ví dụ dùng `float` |
| --- | --- |
| `FloatVector` | Chứa các giá trị số để tính toán |
| `VectorMask<Float>` | Chứa một điều kiện boolean cho mỗi lane |
| `VectorSpecies<Float>` | Mô tả kiểu phần tử và hình dạng vector tương thích |

Một phép so sánh vector trả về mask; một phép cộng trả về vector số. Không thể dùng trực tiếp mask như điều kiện `boolean` của câu lệnh `if`.

Vector và mask tham gia cùng phép toán phải tương thích về species. Dùng species ưu tiên của nền tảng và lấy số lane từ nó:

```java
static final VectorSpecies<Float> SPECIES = FloatVector.SPECIES_PREFERRED;
```

`SPECIES.length()` là số lane, không phải số bit. Không cố định số bước vòng lặp bằng `4`, `8` hoặc `16` khi đã chọn `SPECIES_PREFERRED`. [Javadoc: VectorSpecies](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html).

Các bảng bốn lane dưới đây chỉ giúp quan sát phép tính; chúng không giả định máy thực thi luôn dùng bốn lane.

## 3. Phép toán số học hoạt động theo từng lane

Với hai vector `a` và `b`, các thao tác cơ bản tương ứng với phép toán trên từng cặp phần tử:

| Biểu thức vector | Giá trị tại lane `k` |
| --- | --- |
| `a.add(b)` | `a[k] + b[k]` |
| `a.sub(b)` | `a[k] - b[k]` |
| `a.mul(b)` | `a[k] * b[k]` |
| `a.div(b)` | `a[k] / b[k]` |

Ví dụ tính tay:

| Dữ liệu hoặc phép tính | Lane 0 | Lane 1 | Lane 2 | Lane 3 |
| --- | ---: | ---: | ---: | ---: |
| `a` | -2 | 0 | 3 | 8 |
| `b` | 1 | 2 | 4 | 2 |
| `a.add(b)` | -1 | 2 | 7 | 10 |
| `a.sub(b)` | -3 | -2 | -1 | 6 |
| `a.mul(b)` | -2 | 0 | 12 | 16 |
| `a.div(b)` | -2 | 0 | 0.75 | 4 |

`VectorOperators` cung cấp các token như `ADD`, `SUB`, `MUL`, `DIV` cho dạng gọi `lanewise`. Chẳng hạn, `a.lanewise(VectorOperators.ADD, b)` biểu đạt phép cộng theo lane. [Javadoc: VectorOperators](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html).

### Kết hợp vector với một giá trị scalar

```java
FloatVector transformed = x.mul(2.0f).add(1.0f);
```

Đoạn trên tương ứng với `x[k] * 2.0f + 1.0f` ở mỗi lane. Các overload nhận scalar áp dụng cùng một giá trị cho các lane; có thể tạo vector hằng tường minh bằng `FloatVector.broadcast(SPECIES, value)`.

`FloatVector` là bất biến. Lệnh `x.add(y)` không sửa `x`; muốn sử dụng kết quả phải giữ giá trị trả về hoặc nối tiếp phép toán. [Javadoc: FloatVector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html).

## 4. So sánh tạo một điều kiện cho mỗi lane

```java
VectorMask<Float> nonNegative = x.compare(VectorOperators.GE, 0.0f);
VectorMask<Float> notTooLarge = x.compare(VectorOperators.LE, 10.0f);
```

Các token thường dùng:

| Token | Điều kiện tại từng lane |
| --- | --- |
| `EQ` | Bằng nhau |
| `NE` | Khác nhau |
| `LT` | Nhỏ hơn |
| `LE` | Nhỏ hơn hoặc bằng |
| `GT` | Lớn hơn |
| `GE` | Lớn hơn hoặc bằng |

Có thể so sánh với một scalar hoặc với vector khác. Kết quả vẫn là mask có điều kiện ở vị trí tương ứng. [Javadoc: VectorOperators.Comparison](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.Comparison.html), [Javadoc: các token so sánh](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html#GE).

Với `x = [-2, 0, 3, 8]`:

```text
x >= 0       → [false, true, true, true]
x <= 10      → [true,  true, true, true]
```

Mỗi lane giữ quyết định riêng. Muốn biểu đạt `0 <= x[k] && x[k] <= 10`, kết hợp hai mask thay vì viết `if` cho cả vector.

## 5. Kết hợp mask bằng logic boolean

```java
VectorMask<Float> accepted = nonNegative.and(notTooLarge);
```

Các phép kết hợp áp dụng theo lane:

| Phương thức | Biểu thức boolean tương ứng |
| --- | --- |
| `a.and(b)` | `a[k] & b[k]` |
| `a.or(b)` | `a[k] \| b[k]` |
| `a.xor(b)` | `a[k] ^ b[k]` |
| `a.not()` | `!a[k]` |
| `a.andNot(b)` | `a[k] & !b[k]` |

`andNot` có thứ tự: loại khỏi `a` các lane được chọn trong `b`. Các phép này trả mask mới, không sửa các mask đầu vào. [Javadoc: VectorMask](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html).

Bảng chân trị giúp phân biệt các trường hợp:

| A | B | A AND B | A OR B | A XOR B | A AND NOT B |
| --- | --- | --- | --- | --- | --- |
| false | false | false | false | false | false |
| false | true | false | true | true | false |
| true | false | false | true | true | true |
| true | true | true | true | false | false |

Ví dụ nghiệp vụ: dữ liệu được chấp nhận khi nằm trong khoảng, hoặc thuộc một nhóm được miễn điều kiện. Viết riêng mask cho từng điều kiện rồi kết hợp giúp người đọc kiểm tra được công thức.

### Tóm tắt mask thành một giá trị scalar

`anyTrue()` hỏi có lane nào được chọn, `allTrue()` hỏi mọi lane có được chọn không, còn `trueCount()` đếm số lane được chọn.

```java
int count = accepted.trueCount();
```

`if (accepted.anyTrue())` chỉ chọn một nhánh cho cả khối mã. Nó không tự áp dụng phép tính riêng lên các lane đang `true`; việc đó cần masked operation hoặc `blend`.

## 6. Chọn giá trị bằng `blend`: nhớ đúng chiều

Hợp đồng quan trọng:

```java
FloatVector result = base.blend(replacement, mask);
```

- Mask `false`: lấy lane từ `base`.
- Mask `true`: lấy lane từ `replacement`.

Tương ứng tại một lane là `mask[k] ? replacement[k] : base[k]`. [Javadoc: FloatVector.blend](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html#blend(jdk.incubator.vector.Vector,jdk.incubator.vector.VectorMask)).

Với điều kiện chấp nhận `0 <= x <= 10`, đầu ra là `2*x+1` khi chấp nhận, còn lại dùng `-1`:

| Thành phần | Lane 0 | Lane 1 | Lane 2 | Lane 3 |
| --- | ---: | ---: | ---: | ---: |
| `x` | -2 | 0 | 3 | 8 |
| Giá trị thay thế `2*x+1` | -3 | 1 | 7 | 17 |
| Giá trị nền | -1 | -1 | -1 | -1 |
| `accepted` | false | true | true | true |
| Kết quả | -1 | 1 | 7 | 17 |

```java
FloatVector base = FloatVector.broadcast(SPECIES, -1.0f);
FloatVector candidate = x.mul(2.0f).add(1.0f);
FloatVector result = base.blend(candidate, accepted);
```

Đảo vị trí `base` và `candidate` sẽ đảo ý nghĩa điều kiện. `blend` ở đây giữ nguyên vị trí lane; nó không gom các phần tử được chọn thành một mảng ngắn hơn.

Java vẫn đánh giá đối số trước khi gọi phương thức. Trong `base.blend(makeCandidate(), accepted)`, `makeCandidate()` vẫn được gọi dù mask không chọn lane nào. Mask của blend không biến lời gọi đó thành một nhánh scalar đánh giá có điều kiện. [JLS 27, §15.12.4.2](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.12.4.2).

## 7. Lane không được chọn nhận giá trị nào?

Không có một quy tắc duy nhất rằng lane `false` luôn bằng zero:

| Thao tác | Tác dụng tại lane mask `false` |
| --- | --- |
| `x.add(y, mask)` | Giữ lane từ `x` |
| `x.compare(op, y, mask)` | Mask kết quả tại lane đó là `false` |
| Load mảng có mask | Lane vector được điền zero |
| Store mảng có mask | Không ghi vị trí tương ứng trong mảng |

Đây là các hợp đồng khác nhau của masked arithmetic, comparison, load và store. [Javadoc: masked operations](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html#masking).

Ví dụ, nếu yêu cầu ngoài khoảng phải trả `-1`, chỉ gọi `x.mul(2.0f, accepted)` là chưa đủ: các lane bị loại vẫn giữ giá trị gốc từ `x`. Cần biểu đạt rõ giá trị thay thế, chẳng hạn tạo vector nền rồi blend như mục 6.

## 8. Mask điều kiện và mask biên mảng

Giả sử chỉ còn ba phần tử thật nhưng vector có bốn lane. Tạo mask biên bằng:

```java
VectorMask<Float> inBounds = SPECIES.indexInRange(i, input.length);
```

Mask chọn lane `k` khi chỉ số `i+k` hợp lệ. [Javadoc: VectorSpecies.indexInRange](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html#indexInRange(int,int)).

Load và store phần đuôi bằng mask này:

```java
FloatVector x = FloatVector.fromArray(SPECIES, input, i, inBounds);
result.intoArray(output, i, inBounds);
```

Những lane không load được chọn có giá trị zero. Store chỉ ghi các lane `true`, nên các chỉ số ngoài mảng không bị truy cập. [Javadoc: FloatVector load/store](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html).

### Zero ở lane đệm có thể thỏa điều kiện nghiệp vụ

Nếu điều kiện là `x >= 0`, lane đệm zero cũng vượt qua phép so sánh. Vì vậy, mask chọn dữ liệu thật nên được tạo thành:

```java
VectorMask<Float> selected = inBounds
        .and(x.compare(VectorOperators.GE, low))
        .and(x.compare(VectorOperators.LE, high));
```

Nếu cần những phần tử thật không được chọn:

```java
VectorMask<Float> rejected = inBounds.andNot(selected);
```

Chỉ dùng `selected.not()` sẽ bật cả lane đệm. Sai sót này dễ lộ ra ở thao tác đếm hoặc kiểm tra toàn bộ điều kiện, ngay cả khi bước store đã có mask biên.

Một hệ quả khác: `selected.allTrue()` có thể trả `false` ở khối cuối dù mọi phần tử thật đều đạt điều kiện. Khi cần hỏi điều đó, có thể so sánh `selected.trueCount() == inBounds.trueCount()`, với điều kiện `selected` đã được giới hạn bởi `inBounds`.

## 9. Ví dụ hoàn chỉnh: biến đổi dữ liệu được chọn

Yêu cầu tại mỗi phần tử thật:

```java
output[j] = input[j] >= low && input[j] <= high
        ? input[j] * gain + bias
        : fallback;
```

Đồng thời, trả số phần tử nằm trong khoảng. Ví dụ quy định hai mảng không null, cùng độ dài; `low` và `high` hữu hạn, `low <= high`. Phép tính đầu ra tuân theo số học `float` của Java.

Lưu thành `VectorMaskDemo.java`:

```java
import java.util.Arrays;
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

public class VectorMaskDemo {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static int transform(float[] input, float[] output,
                         float low, float high,
                         float gain, float bias, float fallback) {
        if (input.length != output.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }
        if (!Float.isFinite(low) || !Float.isFinite(high) || low > high) {
            throw new IllegalArgumentException("Invalid interval");
        }

        FloatVector base = FloatVector.broadcast(SPECIES, fallback);
        int matched = 0;

        for (int i = 0; i < input.length; ) {
            int chunkLength = Math.min(SPECIES.length(), input.length - i);
            VectorMask<Float> inBounds = SPECIES.indexInRange(i, input.length);
            FloatVector x = FloatVector.fromArray(SPECIES, input, i, inBounds);

            VectorMask<Float> selected = inBounds
                    .and(x.compare(VectorOperators.GE, low))
                    .and(x.compare(VectorOperators.LE, high));

            FloatVector candidate = x.mul(gain).add(bias);
            FloatVector result = base.blend(candidate, selected);

            result.intoArray(output, i, inBounds);
            matched += selected.trueCount();
            i += chunkLength;
        }

        return matched;
    }

    public static void main(String[] args) {
        float[] input = {
                -5.0f, 0.0f, 10.0f, 100.0f, 101.0f,
                Float.NaN, Float.POSITIVE_INFINITY,
                Float.NEGATIVE_INFINITY, -0.0f
        };
        float[] output = new float[input.length];

        int matched = transform(input, output,
                0.0f, 100.0f, 2.0f, 1.0f, -1.0f);

        System.out.println(Arrays.toString(output));
        System.out.println("matched=" + matched);
    }
}
```

Trên JDK 27 có module Vector API, biên dịch và chạy:

```powershell
javac --add-modules jdk.incubator.vector -d out VectorMaskDemo.java
java --add-modules jdk.incubator.vector -cp out VectorMaskDemo
```

Ví dụ dùng module incubator nên cần resolve `jdk.incubator.vector` ở cả hai bước. Không cần `--enable-preview` cho riêng mã ví dụ này. [Javadoc: module jdk.incubator.vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html), [Oracle: javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html), [Oracle: java](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

Kết quả dự kiến của chương trình:

```text
[-1.0, 1.0, 21.0, 201.0, -1.0, -1.0, -1.0, -1.0, 1.0]
matched=4
```

Các điểm cần đọc cùng nhau trong ví dụ:

1. `inBounds` bảo vệ chỉ số mảng, kể cả khối cuối chưa đủ số lane.
2. `selected` kết hợp biên mảng với hai điều kiện số học.
3. `candidate` tính công thức; `base.blend(...)` quyết định giá trị nào xuất hiện ở đầu ra.
4. Store dùng `inBounds`, để mọi phần tử thật đều được ghi, bao gồm giá trị `fallback` ở phần tử bị loại.
5. `selected.trueCount()` chỉ đếm phần tử thật đạt điều kiện.

Nếu store bằng `selected`, các phần tử bị loại sẽ giữ nội dung cũ của `output` thay vì nhận `fallback`. Đây là lỗi có thể bị che giấu nếu dữ liệu khởi tạo vô tình giống giá trị mong muốn.

`chunkLength` giúp chỉ số tiến theo số phần tử thật được xử lý. Khi mảng rỗng, vòng lặp không chạy và trả số đếm bằng zero.

## 10. Số thực: NaN, vô cực và signed zero

So sánh số thực cần giữ ngữ nghĩa Java:

| Giá trị | Hệ quả cần nhớ |
| --- | --- |
| `NaN` | So sánh thứ tự và `EQ` đều cho `false`; `NE` cho `true` |
| `+Infinity`, `-Infinity` | Có thứ tự so với số hữu hạn |
| `+0.0f`, `-0.0f` | Bằng nhau trong so sánh số học |

Vì vậy, không được đổi tùy ý `!(x < limit)` thành `x >= limit`: hai biểu thức khác nhau khi `x` là NaN. [JLS 27, §15.20.1 và §15.21.1](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.20.1).

Trong ví dụ, NaN không nằm trong khoảng; hai vô cực bị loại vì giới hạn hữu hạn. `-0.0f` nằm trong khoảng `[0, 100]`, nên được đếm và cho kết quả `1.0f`.

Khi nghiệp vụ cần điều kiện tường minh, có thể dùng:

```java
VectorMask<Float> finite = inBounds.and(x.test(VectorOperators.IS_FINITE));
VectorMask<Float> nan = inBounds.and(x.test(VectorOperators.IS_NAN));
```

Hai token này kiểm tra tính hữu hạn và NaN theo lane. [Javadoc: VectorOperators](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html#IS_FINITE).

Mask không tự biến số học `float` thành số thực toán học có độ chính xác vô hạn. Khi thay đổi công thức hoặc yêu cầu sai số, cần đối chiếu lại kết quả scalar tương ứng.

## 11. Đọc lỗi theo từng hợp đồng

| Lỗi thường gặp | Điều cần sửa |
| --- | --- |
| Lane đúng điều kiện lại nhận giá trị nền | Kiểm tra chiều `base.blend(replacement, mask)` |
| Gọi phép toán nhưng vector cũ không đổi | Giữ giá trị trả về của thao tác bất biến |
| Số đếm lớn hơn số phần tử thật | Giao mask điều kiện với `inBounds` trước khi đếm |
| Phủ định mask làm chọn cả lane đệm | Dùng `inBounds.andNot(selected)` |
| Đầu ra còn giá trị từ lần chạy trước | Kiểm tra store dùng mask biên hay chỉ mask điều kiện |
| Khối cuối vượt giới hạn mảng | Dùng load/store có mask biên |
| `anyTrue()` khiến mọi phần tử cùng được biến đổi | Chuyển quyết định theo lane sang masked operation hoặc blend |
| NaN đi vào nhánh ngoài dự kiến | Giữ đúng predicate số học; tránh biến đổi logic không hợp lệ với NaN |
| Không tương thích vector và mask | Dùng cùng species cho các toán hạng liên quan |

Để đối chiếu một triển khai với công thức scalar, nên có dữ liệu sát hai biên, mảng rỗng, độ dài nhỏ hơn số lane, độ dài không chia hết số lane, toàn bộ đạt hoặc không đạt điều kiện, và các giá trị số thực đặc biệt. Với `L = SPECIES.length()`, các độ dài như `0`, `1`, `L-1`, `L`, `L+1` giúp quan sát các ranh giới này.

## 12. Giữ rõ ý nghĩa trước khi tối ưu

Mẫu dùng mask ở mọi lượt giúp trình bày thống nhất việc tính toán và xử lý phần đuôi. Nó không bảo đảm là cách nhanh nhất cho mọi CPU hoặc kích thước mảng; tài liệu API cũng lưu ý chi phí của cách dùng mask xuyên suốt vòng lặp. Khi tối ưu, có thể cân nhắc vòng lặp xử lý các vector đầy đủ và phần đuôi riêng, rồi đo trên JDK và phần cứng mục tiêu. [Javadoc: ví dụ vòng lặp Vector API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html).

Với một biểu thức có điều kiện, hãy xác định lần lượt: công thức tính giá trị, predicate chọn lane, giá trị khi predicate sai, và miền chỉ số hợp lệ. Khi bốn phần này rõ ràng, có thể kết hợp phép toán, mask và blend mà vẫn giải thích được kết quả của từng phần tử.
