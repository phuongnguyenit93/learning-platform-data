# Phép toán trên lane, so sánh và VectorMask

## 1. Mục tiêu và bối cảnh phiên bản

Vector API biểu diễn một vector như một dãy có số lane cố định. Mỗi lane giữ một giá trị nguyên thủy cùng kiểu; các phép toán thường áp dụng cùng một phép toán vô hướng lên từng cặp lane tương ứng. Cách thực thi này khai thác SIMD (Single Instruction, Multiple Data) khi CPU và JIT hỗ trợ.

Bài học tập trung vào ba nhóm thao tác:

- Phép toán lane-wise như cộng, trừ, nhân, chia và giá trị nhỏ nhất/lớn nhất.
- So sánh lane-wise để tạo ra `VectorMask`.
- Dùng mask để kết hợp điều kiện, chọn lane, giới hạn phép toán và xử lý phần tử dư ở cuối mảng.

Vector API vẫn là incubator:

| JDK | JEP | Trạng thái |
|---|---|---|
| JDK 26 | JEP 529 | Incubator lần thứ mười một |
| JDK 27 | JEP 537 | Incubator lần thứ mười hai |

Tính đến 27/11/2026, JDK 27 là feature release mới hơn. JDK 27 tiếp tục incubate Vector API và không có thay đổi đáng kể so với JDK 26. Đây không phải API chuẩn ổn định của Java SE; module và chữ ký API vẫn có thể thay đổi hoặc bị loại bỏ ở các phiên bản sau.

Bài dùng Java 27 API làm chuẩn hiện hành. Nếu thử nghiệm trên JDK 26, thay số phiên bản trong lệnh biên dịch/chạy. Vì Vector API là incubator module, cần thêm module `jdk.incubator.vector`; không cần `--enable-preview`.

## 2. Vector, lane, shape và species

### 2.1. Lane là gì?

Một vector gồm nhiều lane cùng kiểu dữ liệu. Ví dụ minh họa một vector có bốn lane:

~~~text
Lane index:  0   1   2   3
Vector A:   10  20  30  40
Vector B:    1   2   3   4
             |   |   |   |
A + B:       11  22  33  44
~~~

Phép cộng được áp dụng độc lập cho từng cặp lane:

- Lane 0: 10 + 1 = 11.
- Lane 1: 20 + 2 = 22.
- Lane 2: 30 + 3 = 33.
- Lane 3: 40 + 4 = 44.

Vector API không bắt buộc mọi CPU phải có đúng bốn lane. Số lane phụ thuộc kiểu phần tử và shape được chọn.

### 2.2. Shape và species

- **Element type** là kiểu nguyên thủy của lane: `byte`, `short`, `int`, `long`, `float` hoặc `double`.
- **Vector shape** mô tả dung lượng vector theo bit, ví dụ 128-bit, 256-bit hoặc 512-bit.
- **Vector length** là số lane trong vector.
- **Vector species** là tổ hợp của element type và shape, đại diện bởi `VectorSpecies<E>`.

Ví dụ, vector 256-bit chứa lane `int` có 8 lane vì mỗi `int` rộng 32 bit. Vector 256-bit chứa lane `double` có 4 lane vì mỗi `double` rộng 64 bit.

Các vector tham gia cùng một phép toán lane-wise thông thường phải có cùng species, tức cùng element type, shape và số lane. Không ghép hai vector có độ dài khác nhau rồi mong API tự căn chỉnh.

### 2.3. Chọn species phù hợp nền tảng

Dùng species được runtime ưu tiên cho kiểu phần tử:

~~~java
private static final VectorSpecies<Integer> INT_SPECIES =
        IntVector.SPECIES_PREFERRED;

private static final VectorSpecies<Float> FLOAT_SPECIES =
        FloatVector.SPECIES_PREFERRED;
~~~

`SPECIES_PREFERRED` cho phép implementation chọn shape phù hợp với nền tảng hiện tại. Tránh mặc định mã phải dùng 256-bit hoặc 512-bit; CPU, JIT và hệ điều hành khác nhau có thể hỗ trợ shape khác nhau.

Nên giữ species trong trường `static final` để runtime có thể tối ưu việc tạo và sử dụng vector. Nếu cần kiểm tra thông tin, dùng:

~~~java
System.out.println(INT_SPECIES.vectorShape());
System.out.println(INT_SPECIES.vectorBitSize());
System.out.println(INT_SPECIES.length());
~~~

## 3. Phép toán lane-wise

### 3.1. Phép toán một vector và hai vector

Phép toán unary nhận một vector và tính trên từng lane, ví dụ:

~~~java
IntVector negative = vector.neg();
IntVector absolute = vector.abs();
~~~

Phép toán binary nhận hai vector cùng species:

~~~java
IntVector sum = a.add(b);
IntVector difference = a.sub(b);
IntVector product = a.mul(b);
IntVector quotient = a.div(b);
IntVector minimum = a.min(b);
IntVector maximum = a.max(b);
~~~

Với mỗi lane N, kết quả được tính từ lane N của các vector đầu vào. Ví dụ `a.mul(b)` tương đương phép nhân từng cặp lane, không phải nhân ma trận hay nhân chéo các lane.

Một số phép toán cũng có overload nhận scalar. Scalar được broadcast thành giá trị dùng cho mọi lane:

~~~java
IntVector plusTen = a.add(10);
IntVector atLeastTen = a.max(10);
~~~

Tên phương thức có sẵn tùy theo loại phép toán và kiểu vector. Nếu một phép toán không có overload tên riêng, API cung cấp các phương thức `lanewise(...)` cùng `VectorOperators`.

### 3.2. VectorOperators

`VectorOperators` cung cấp token mô tả phép toán. Ví dụ:

~~~java
IntVector sum = a.lanewise(VectorOperators.ADD, b);
IntVector product = a.lanewise(VectorOperators.MUL, b);
IntVector absolute = a.lanewise(VectorOperators.ABS);
~~~

Các token thường gặp:

| Token | Ý nghĩa |
|---|---|
| `ADD`, `SUB`, `MUL`, `DIV` | Cộng, trừ, nhân, chia |
| `MIN`, `MAX` | Chọn giá trị nhỏ hơn/lớn hơn |
| `NEG`, `ABS` | Đổi dấu, trị tuyệt đối |
| `EQ`, `NE` | Bằng, khác |
| `LT`, `LE`, `GT`, `GE` | Nhỏ hơn, nhỏ hơn hoặc bằng, lớn hơn, lớn hơn hoặc bằng |
| `AND`, `OR`, `XOR` | Phép logic trên bit của lane nguyên |

Một token chỉ hợp lệ với các kiểu phần tử hỗ trợ phép toán đó. Ví dụ, phép toán bitwise phù hợp với kiểu nguyên; các phép toán lượng giác chỉ phù hợp với floating-point. Nếu vector không hỗ trợ token, API có thể ném `UnsupportedOperationException`.

### 3.3. Các phép toán vẫn theo ngữ nghĩa kiểu nguyên thủy

Vector API áp dụng phép toán nguyên thủy tương ứng trên từng lane. Vì vậy, các quy tắc của kiểu dữ liệu vẫn có hiệu lực:

- Phép cộng `int` có thể tràn và cuộn theo ngữ nghĩa `int` của Java.
- Chia số nguyên cho 0 ở một lane được chọn sẽ ném `ArithmeticException`.
- Chia floating-point có thể tạo `Infinity` hoặc `NaN` theo quy tắc floating-point.
- Phép toán trên `float`/`double` có thể chịu ảnh hưởng của làm tròn và thứ tự tính.

Không giả định vector hóa sẽ tự nâng độ chính xác số học. Nếu thuật toán cần tránh tràn, hãy chọn kiểu lane đủ rộng hoặc kiểm tra miền dữ liệu trước khi tính.

## 4. So sánh lane-wise tạo VectorMask

### 4.1. Kết quả so sánh là mask

So sánh hai vector không trả về một vector `boolean`. Nó trả về `VectorMask<E>`, trong đó mỗi lane là một bit logic:

~~~java
VectorMask<Integer> mask = a.compare(VectorOperators.GT, b);
~~~

Mask tại lane N được bật nếu phép so sánh giữa lane N của `a` và lane N của `b` là đúng.

Ví dụ minh họa:

~~~text
A:       [ 4, 12,  7, 20]
B:       [ 8, 10,  7, 15]

A > B:   [ F,  T,  F,  T]
~~~

Các cách viết tương đương và thường dễ đọc:

~~~java
VectorMask<Integer> equal = a.eq(b);
VectorMask<Integer> less = a.lt(b);
VectorMask<Integer> greater = a.compare(VectorOperators.GT, b);
~~~

Có thể so sánh với một scalar:

~~~java
VectorMask<Integer> aboveLimit =
        a.compare(VectorOperators.GT, 100);
~~~

Scalar được broadcast cho tất cả lane trước khi so sánh.

### 4.2. Các toán tử so sánh

| Token | Điều kiện trên từng cặp lane |
|---|---|
| `EQ` | `a == b` |
| `NE` | `a != b` |
| `LT` | `a < b` |
| `LE` | `a <= b` |
| `GT` | `a > b` |
| `GE` | `a >= b` |

Với vector nguyên, API còn có các phép so sánh không dấu cho những thuật toán cần diễn giải bit như unsigned integer. Chỉ dùng các token không dấu khi miền dữ liệu và kiểu phần tử thực sự cần ngữ nghĩa unsigned.

Với `float` và `double`, phép so sánh tuân theo quy tắc floating-point của Java. Chẳng hạn, phép so sánh với `NaN` có thể không khớp như kỳ vọng nếu bạn chỉ xét số hữu hạn. Nếu cần lọc `NaN` hoặc vô cực, dùng các test operator phù hợp như `IS_NAN`, `IS_FINITE` hoặc `IS_INFINITE`.

### 4.3. So sánh có mask đầu vào

Có thể giới hạn những lane được đem ra so sánh:

~~~java
VectorMask<Integer> selected = a.compare(
        VectorOperators.GT,
        b,
        activeLanes
);
~~~

Kết quả tương đương:

~~~java
VectorMask<Integer> selected =
        a.compare(VectorOperators.GT, b).and(activeLanes);
~~~

Các lane không được chọn trong `activeLanes` sẽ không bật trong mask kết quả. Cách này đặc biệt hữu ích khi vector cuối chỉ chứa một phần dữ liệu hợp lệ.

## 5. VectorMask: kết hợp điều kiện và truy vấn kết quả

### 5.1. Mask là một dãy boolean bất biến

`VectorMask<E>` biểu diễn một dãy boolean có thứ tự. Mask có cùng số lane với vector tương thích. Mỗi lane được gọi là:

- **Set** khi giá trị boolean là `true`.
- **Unset** khi giá trị boolean là `false`.

Mask là immutable và value-based. Không dùng toán tử `==` để so sánh identity của hai mask; dùng `equals()` khi cần so sánh giá trị mask.

### 5.2. Kết hợp mask

Mask hỗ trợ các phép toán logic theo từng lane:

~~~java
VectorMask<Integer> positive = values.compare(VectorOperators.GT, 0);
VectorMask<Integer> belowLimit = values.compare(VectorOperators.LT, 100);

VectorMask<Integer> validRange = positive.and(belowLimit);
VectorMask<Integer> outsideRange = positive.not().or(belowLimit.not());
VectorMask<Integer> eitherCondition = positive.or(belowLimit);
VectorMask<Integer> difference = positive.xor(belowLimit);
~~~

| Phương thức | Ý nghĩa |
|---|---|
| `and(mask)` | Chỉ bật lane khi cả hai mask đều bật |
| `or(mask)` | Bật lane nếu ít nhất một mask bật |
| `xor(mask)` | Bật lane khi hai mask khác nhau |
| `andNot(mask)` | `a & ~b`, giữ lane bật trong mask đầu nhưng tắt trong mask sau |
| `not()` | Đảo trạng thái từng lane |
| `eq(mask)` | Tạo mask cho các lane mà hai mask có cùng trạng thái |

Các mask phải tương thích về species/độ dài. Không kết hợp mask của hai vector có kiểu phần tử hoặc shape khác nhau nếu chưa chuyển đổi mask đúng cách.

### 5.3. Hỏi mask có lane nào thỏa điều kiện không

Một số phép truy vấn thường dùng:

~~~java
if (mask.anyTrue()) {
    System.out.println("Có ít nhất một lane phù hợp");
}

if (mask.allTrue()) {
    System.out.println("Tất cả lane đều phù hợp");
}

int count = mask.trueCount();
int first = mask.firstTrue();
int last = mask.lastTrue();
~~~

- `anyTrue()`: có ít nhất một lane được bật.
- `allTrue()`: tất cả lane được bật.
- `trueCount()`: đếm số lane được bật.
- `firstTrue()`: chỉ số lane đầu tiên được bật; trả về `mask.length()` nếu không có lane nào bật.
- `lastTrue()`: chỉ số lane cuối cùng được bật; trả về `-1` nếu không có lane nào bật.
- `laneIsSet(i)`: kiểm tra một lane cụ thể.

Ví dụ, sau khi tìm các phần tử vượt ngưỡng:

~~~java
VectorMask<Integer> above = values.compare(VectorOperators.GT, threshold);

if (above.anyTrue()) {
    int firstIndexInVector = above.firstTrue();
    int numberOfMatches = above.trueCount();
}
~~~

Chỉ gọi `firstTrue()` như một vị trí hợp lệ trong vector sau khi đã kiểm tra `anyTrue()`, hoặc tự xử lý trường hợp trả về `length()`.

## 6. Dùng mask để chọn giá trị với blend()

### 6.1. blend chọn lane từ hai vector

`blend(other, mask)` tạo vector mới bằng cách chọn từng lane từ vector hiện tại hoặc vector `other`:

- Nếu lane mask được bật, lấy lane tương ứng từ `other`.
- Nếu lane mask tắt, giữ lane tương ứng của vector ban đầu.

Ví dụ:

~~~java
IntVector a = ...;
IntVector b = ...;
VectorMask<Integer> chooseB = a.compare(VectorOperators.GT, 10);

IntVector selected = a.blend(b, chooseB);
~~~

Có thể hiểu như biểu thức chọn theo từng lane:

~~~text
result[i] = mask[i] ? b[i] : a[i]
~~~

Lưu ý thứ tự: `blend` lấy giá trị từ vector truyền vào khi mask bật. Nếu đảo hai vector, kết quả sẽ khác.

### 6.2. blend với scalar

Có thể thay các lane được chọn bằng cùng một scalar:

~~~java
VectorMask<Integer> negative = values.compare(VectorOperators.LT, 0);
IntVector nonNegative = values.blend(0, negative);
~~~

Kết quả là các lane âm được thay bằng 0; các lane khác giữ nguyên.

### 6.3. Masked arithmetic khác với blend

Các phép toán có overload nhận mask, ví dụ:

~~~java
IntVector updated = a.add(b, activeLanes);
~~~

Ở lane mask bật, phép cộng được thực hiện. Ở lane mask tắt, phép toán bị bỏ qua và lane kết quả giữ nguyên giá trị từ vector bên trái (`a`).

Đây là khác biệt quan trọng:

| Cách dùng | Lane mask bật | Lane mask tắt |
|---|---|---|
| `a.add(b, mask)` | Tính `a + b` | Giữ giá trị `a` |
| `a.blend(b, mask)` | Chọn giá trị `b` | Giữ giá trị `a` |
| `fromArray(..., mask)` | Đọc phần tử mảng | Lane được nạp giá trị mặc định của kiểu, ví dụ `int` là 0 |
| `intoArray(..., mask)` | Ghi lane vào mảng | Không ghi, phần tử mảng giữ nguyên |

Không giả định masked operation tự gán 0 cho lane không được chọn. Nếu cần gán 0, hãy dùng `blend` với vector zero hoặc một phép chọn rõ ràng.

## 7. Xử lý phần tử dư ở cuối mảng bằng VectorMask

### 7.1. Vấn đề tail

Nếu species có 8 lane nhưng mảng chỉ còn 3 phần tử ở vòng cuối, tải vector không mask sẽ đọc vượt giới hạn mảng.

Có hai cách thường dùng:

1. Xử lý phần chia hết bằng vector loop, sau đó xử lý phần dư bằng scalar loop.
2. Tạo mask chỉ bật những lane có chỉ số hợp lệ.

Cách thứ hai tận dụng `VectorSpecies.indexInRange(offset, limit)`.

### 7.2. Tạo mask theo phạm vi

~~~java
VectorMask<Integer> valid =
        INT_SPECIES.indexInRange(offset, array.length);
~~~

Lane N được bật khi `offset + N` nằm trong khoảng `[0, array.length)`. Các lane còn lại tắt.

Có thể dùng cùng mask cho tải, tính toán và lưu:

~~~java
IntVector values = IntVector.fromArray(INT_SPECIES, array, offset, valid);
IntVector doubled = values.add(values, valid);
doubled.intoArray(output, offset, valid);
~~~

Với masked load, lane không được chọn được điền bằng giá trị mặc định của kiểu lane. Với masked store, lane không được chọn không ghi ra mảng; những vị trí này không cần nằm trong giới hạn mảng.

### 7.3. Vòng lặp tail hoàn chỉnh

~~~java
private static final VectorSpecies<Integer> SPECIES =
        IntVector.SPECIES_PREFERRED;

static void doubleValues(int[] input, int[] output) {
    if (input.length != output.length) {
        throw new IllegalArgumentException("Array lengths must match");
    }

    int length = input.length;

    for (int i = 0; i < length; i += SPECIES.length()) {
        VectorMask<Integer> valid = SPECIES.indexInRange(i, length);

        IntVector values = IntVector.fromArray(
                SPECIES, input, i, valid
        );

        IntVector doubled = values.add(values, valid);

        doubled.intoArray(output, i, valid);
    }
}
~~~

Cách này không cần tách riêng scalar tail loop. Với mọi vòng lặp, mask đảm bảo các lane ngoài phạm vi không đọc hoặc ghi phần tử mảng không hợp lệ.

## 8. Ví dụ hoàn chỉnh: cộng hai mảng, lọc và thay giá trị bằng mask

Chương trình sau thực hiện ba việc trên từng nhóm lane:

1. Cộng hai mảng theo lane.
2. Tìm các lane có tổng lớn hơn ngưỡng và đếm số kết quả.
3. Thay tổng âm bằng 0 bằng `blend`, đồng thời ghi kết quả an toàn cả ở vòng cuối.

Tạo file `LaneMaskDemo.java`:

~~~java
import java.util.Arrays;

import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

public class LaneMaskDemo {
    private static final VectorSpecies<Integer> SPECIES =
            IntVector.SPECIES_PREFERRED;

    static void addAndClamp(
            int[] left,
            int[] right,
            int threshold,
            int[] output
    ) {
        if (left.length != right.length
                || left.length != output.length) {
            throw new IllegalArgumentException(
                    "All arrays must have the same length"
            );
        }

        int length = left.length;

        for (int i = 0; i < length; i += SPECIES.length()) {
            // Chỉ bật các lane có chỉ số còn nằm trong mảng.
            VectorMask<Integer> valid =
                    SPECIES.indexInRange(i, length);

            IntVector a = IntVector.fromArray(
                    SPECIES, left, i, valid
            );
            IntVector b = IntVector.fromArray(
                    SPECIES, right, i, valid
            );

            // Phép cộng lane-wise; lane ngoài phạm vi không được xử lý.
            IntVector sum = a.add(b, valid);

            // So sánh theo từng lane, chỉ xét lane hợp lệ.
            VectorMask<Integer> aboveThreshold = sum.compare(
                    VectorOperators.GT,
                    threshold,
                    valid
            );

            if (aboveThreshold.anyTrue()) {
                int count = aboveThreshold.trueCount();
                int firstIndex = i + aboveThreshold.firstTrue();

                System.out.printf(
                        "Chunk %d: %d values above %d; first index=%d%n",
                        i,
                        count,
                        threshold,
                        firstIndex
                );
            }

            // Nếu tổng âm, chọn 0; các lane khác giữ nguyên tổng.
            VectorMask<Integer> negative = sum.compare(
                    VectorOperators.LT,
                    0,
                    valid
            );

            IntVector nonNegative = sum.blend(
                    SPECIES.zero(),
                    negative
            );

            // Chỉ ghi các lane hợp lệ.
            nonNegative.intoArray(output, i, valid);
        }
    }

    public static void main(String[] args) {
        int[] left = {
                -4, 2, 8, 12, 7, -9, 20, 5, 14, 3,
                -2, 18, 6, 11, 0, 21, 4, 9, -5
        };

        int[] right = {
                1, 5, 7, 8, 10, 2, -3, 4, 5, 6,
                1, -4, 9, 7, 2, 3, 8, 9, 1
        };

        int[] output = new int[left.length];

        addAndClamp(left, right, 15, output);

        System.out.println("Result: " + Arrays.toString(output));
        System.out.println("Species: " + SPECIES);
        System.out.println("Lanes per vector: " + SPECIES.length());
    }
}
~~~

Kết quả mảng sau khi cộng và thay tổng âm bằng 0:

~~~text
Result: [0, 7, 15, 20, 17, 0, 17, 9, 19, 9, 0, 14, 15, 18, 2, 24, 12, 18, 0]
~~~

Số lane trên mỗi vòng phụ thuộc species được chọn ở máy chạy. Vì dữ liệu có 19 phần tử, chương trình vẫn đúng khi vector có 4, 8 hoặc 16 lane; vòng cuối sử dụng mask để xử lý phần còn lại.

## 9. Phân biệt lane-wise operation, reduction và cross-lane

Không phải mọi thao tác vector đều độc lập giữa các lane.

| Nhóm | Cách hoạt động | Ví dụ |
|---|---|---|
| Lane-wise | Mỗi lane tính từ lane cùng vị trí ở đầu vào | `add`, `mul`, `compare` |
| Mask operation | Chỉ thực hiện hoặc chọn lane được bật trong mask | `add(v, mask)`, `blend(v, mask)` |
| Reduction | Gộp nhiều lane thành một giá trị scalar | `reduceLanes(ADD)` |
| Cross-lane | Di chuyển hoặc sắp xếp lane giữa các vị trí | `rearrange`, `slice`, `compress` |

Ví dụ reduction tổng các lane được chọn:

~~~java
VectorMask<Integer> selected = values.compare(VectorOperators.GT, 0);

int total = values.reduceLanes(
        VectorOperators.ADD,
        selected
);
~~~

Reduction thay đổi cấu trúc kết quả từ vector thành scalar. Với `float` và `double`, thứ tự cộng có thể thay đổi do phép reduction có thể dùng thứ tự kết hợp khác nhau; kết quả floating-point vì thế có thể khác một vòng lặp scalar cộng tuần tự ở các bit cuối.

Cross-lane operations như `compress(mask)` có thể đưa các lane được chọn về phía đầu vector và đặt các lane còn lại thành 0. Đây không còn là phép toán từng lane độc lập; nó thay đổi vị trí dữ liệu.

## 10. Các lỗi thường gặp khi dùng VectorMask

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng vector hoặc mask khác species | Không ghép được lane tương ứng hoặc API từ chối | Dùng cùng `VectorSpecies` cho vector và mask |
| Coi compare trả về `boolean[]` | Sai kiểu kết quả | Nhận `VectorMask<E>` |
| Dùng mask không giới hạn ở tail | Có thể đọc hoặc ghi ngoài mảng | Tạo bằng `species.indexInRange(offset, length)` |
| Nghĩ lane mask tắt trong phép cộng trở thành 0 | Dữ liệu kết quả sai | Masked arithmetic giữ lane trái; dùng `blend` nếu cần thay bằng 0 |
| Đảo thứ tự hai vector trong blend | Chọn nhầm nguồn dữ liệu | Nhớ mask bật sẽ chọn vector truyền vào `blend` |
| Gọi `firstTrue()` khi không có lane nào bật | Nhận chỉ số bằng `length()`, không phải lane hợp lệ | Kiểm tra `anyTrue()` trước |
| So sánh identity bằng `==` | Không tuân theo semantics value-based | Dùng `equals()` khi cần so sánh nội dung |
| Hard-code shape 256/512 bit | Giảm khả năng chạy trên CPU khác | Dùng `SPECIES_PREFERRED` và `length()` |

Ngoài ra, `VectorMask.toLong()` chỉ hỗ trợ mask tối đa 64 lane. Nếu code cần chạy với species có nhiều lane hơn, dùng `toArray()`, `trueCount()` hoặc các phương thức truy vấn mask thay vì giả định mask luôn vừa trong một `long`.

## 11. Biên dịch và chạy incubator module

Vector API nằm trong module `jdk.incubator.vector`. Với ứng dụng dùng classpath, thêm module ở cả bước biên dịch và chạy:

~~~bash
javac --release 27 --add-modules jdk.incubator.vector -d out LaneMaskDemo.java
java --add-modules jdk.incubator.vector -cp out LaneMaskDemo
~~~

Nếu thử bằng JDK 26 còn được nhà cung cấp hỗ trợ, thay `27` bằng `26`:

~~~bash
javac --release 26 --add-modules jdk.incubator.vector -d out LaneMaskDemo.java
java --add-modules jdk.incubator.vector -cp out LaneMaskDemo
~~~

Với dự án modular, khai báo module phụ thuộc trong `module-info.java`:

~~~java
module example.vector {
    requires jdk.incubator.vector;
}
~~~

Không cần `--enable-preview`; đây là incubator module chứ không phải preview language feature. Khi chạy, JDK có thể phát cảnh báo rằng chương trình đang sử dụng incubator module. Đây là tín hiệu về trạng thái thử nghiệm của API.

## 12. Khi nào nên dùng và cách đánh giá hiệu năng

Vector API có thể hữu ích cho:

- Xử lý ảnh, âm thanh và tín hiệu.
- Tính toán số học trên mảng lớn.
- Lọc, chuẩn hóa và biến đổi dữ liệu dạng cột.
- Mô phỏng số hoặc thuật toán có nhiều phép toán giống nhau trên các phần tử độc lập.

Tuy nhiên, vector code không tự động nhanh hơn scalar code. Kết quả phụ thuộc vào:

- CPU có hỗ trợ tập lệnh vector phù hợp hay không.
- JIT có biên dịch được phép toán thành lệnh vector hiệu quả hay không.
- Dữ liệu đủ lớn để bù chi phí thiết lập và xử lý tail hay không.
- Thuật toán có bị giới hạn bởi băng thông bộ nhớ hay chi phí truy cập dữ liệu hay không.
- Mask và chuyển đổi dữ liệu có làm tăng overhead hay không.

Khi benchmark:

1. Viết một scalar baseline đúng và dễ đọc.
2. Dùng JMH hoặc benchmark harness phù hợp, có warmup và nhiều lần đo.
3. Dùng dữ liệu đại diện với kích thước nhỏ, vừa và lớn.
4. Chạy trên đúng loại CPU dự kiến triển khai.
5. Đo throughput, latency, allocation và độ ổn định giữa các lần chạy.
6. Kiểm tra kết quả vector và scalar tương đương về mặt nghiệp vụ.
7. Chỉ giữ vector path khi lợi ích đo được đủ lớn để bù chi phí bảo trì.

Vì API còn incubator, nên cô lập code vector trong một module hoặc adapter nội bộ. Tránh để các kiểu `IntVector`, `VectorMask` hoặc `VectorSpecies` xuất hiện trong public API của thư viện dùng chung. Khi API thay đổi, phạm vi cần sửa sẽ nhỏ hơn.

## 13. Kết luận

Lane-wise operations thực hiện cùng một phép toán trên các lane tương ứng. Các phép so sánh như `EQ`, `LT`, `GT` trả về `VectorMask`, cho phép kết hợp điều kiện, đếm số lane phù hợp, chọn dữ liệu bằng `blend` hoặc chỉ thực hiện phép toán trên lane được chọn.

Các điểm cần nhớ:

- Vector và mask phải tương thích về species và số lane.
- `VectorMask` là dãy boolean bất biến, có các phép logic và reduction như `anyTrue`, `allTrue`, `trueCount`, `firstTrue`.
- Mask bật trong `blend` chọn lane từ vector thứ hai; mask tắt giữ lane của vector đầu tiên.
- Masked arithmetic bỏ qua lane không được chọn và giữ giá trị ban đầu của vector bên trái.
- `indexInRange` tạo tail mask để đọc/ghi mảng không vượt giới hạn.
- Vector API vẫn là incubator ở JDK 27. Phải thêm module `jdk.incubator.vector` và kiểm thử hiệu năng trên CPU đích; không xem API này là hợp đồng Java SE ổn định.

## Tài liệu tham khảo chính thức

- [JEP 529 — Vector API (Eleventh Incubator, JDK 26)](https://openjdk.org/jeps/529)
- [JEP 537 — Vector API (Twelfth Incubator, JDK 27)](https://openjdk.org/jeps/537)
- [JDK 27 Release Notes — Vector API](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Vector — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html)
- [IntVector — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html)
- [VectorMask — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html)
- [VectorSpecies — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
- [VectorOperators — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html)
- [Vector API package summary — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)

