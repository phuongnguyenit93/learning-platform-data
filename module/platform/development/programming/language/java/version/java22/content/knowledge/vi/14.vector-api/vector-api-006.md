# VectorMask và xử lý phần đuôi khi độ dài dữ liệu không chia hết cho số lane

## 1. Bối cảnh và mục tiêu

Vector API xử lý dữ liệu theo từng nhóm phần tử gọi là **lane**. Khi số phần tử không chia hết cho số lane, lần xử lý cuối chỉ còn một phần dữ liệu. Nếu vẫn đọc hoặc ghi cả vector, chương trình có thể vượt biên mảng hoặc sửa phần tử nằm ngoài phạm vi cần xử lý.

`VectorMask` cho phép chọn các lane hợp lệ trong nhóm cuối. Mục tiêu của bài là xây dựng một vòng lặp vừa xử lý đủ dữ liệu, vừa giữ đúng giới hạn đọc và ghi.

Trong Java 22, Vector API là **incubator lần thứ bảy**. Tại thời điểm đối chiếu 25/11/2026, Java 27 vẫn cung cấp Vector API dưới dạng **incubator lần thứ mười hai**. Không coi đây là API chuẩn đã hoàn tất. Xem [ghi chú phát hành Java 22](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html) và [ghi chú phát hành Java 27](https://www.oracle.com/java/technologies/javase/27all-relnotes.html).

Bài sử dụng các thao tác `FloatVector`, `VectorSpecies`, `loopBound`, `indexInRange` và masked load/store có ở Java 22 và còn áp dụng trong Java hiện đại.

## 2. Vì sao xuất hiện phần đuôi?

Ký hiệu:

- `n`: số phần tử cần xử lý.
- `L`: số lane của species, lấy bằng `SPECIES.length()`.
- `bound`: số phần tử có thể xử lý bằng các vector đầy đủ.
- `r`: số phần tử còn lại ở phần đuôi.

Với `n >= 0`:

```text
bound = n - n % L
r     = n - bound
0 <= r < L
```

Dùng API thay vì tự mã hóa một độ rộng cố định:

```java
int bound = SPECIES.loopBound(n);
```

Ví dụ minh họa với `L = 8`, `n = 19`:

| Vị trí bắt đầu | Chỉ số dữ liệu | Cách xử lý |
| --- | --- | --- |
| 0 | 0 đến 7 | Một vector đầy đủ |
| 8 | 8 đến 15 | Một vector đầy đủ |
| 16 | 16 đến 18 | Ba lane hợp lệ trong vector cuối |

```text
dữ liệu: [0 1 2 3 4 5 6 7] [8 9 10 11 12 13 14 15] [16 17 18]
                                                        phần đuôi
```

`loopBound(n)` trả về bội lớn nhất của số lane không vượt quá `n`. `indexInRange(offset, limit)` tạo mask theo giới hạn chỉ số, trong đó `limit` là cận trên không bao gồm. Xem [VectorSpecies](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html).

Số lane phụ thuộc species. Ví dụ, vector chứa `float` rộng 256 bit có tám lane vì mỗi `float` chiếm 32 bit. Tuy nhiên, không nên mặc định mọi máy đều dùng tám lane.

## 3. VectorMask chọn lane, không làm vector ngắn lại

`VectorMask<E>` là một dãy boolean bất biến có số phần tử bằng số lane của species tương ứng. Mask và vector phải tương thích về kiểu phần tử và hình dạng.

Với phần đuôi ở ví dụ trên:

```java
VectorMask<Float> tail = SPECIES.indexInRange(16, 19);
```

Ý nghĩa theo từng lane:

| Lane | Chỉ số mảng tương ứng | Mask |
| --- | --- | --- |
| 0 | 16 | true |
| 1 | 17 | true |
| 2 | 18 | true |
| 3 | 19 | false |
| 4 | 20 | false |
| 5 | 21 | false |
| 6 | 22 | false |
| 7 | 23 | false |

```text
lane:      0 1 2 3 4 5 6 7
tail mask: T T T F F F F F
```

Vector vẫn có tám lane trong minh họa này. Mask chỉ điều khiển tác dụng của thao tác chấp nhận mask; nó không thay đổi độ dài vector hay mảng.

Các phương thức như `trueCount()`, `anyTrue()` và `allTrue()` giúp quan sát mask. Ví dụ, `tail.trueCount()` ở đây bằng 3. Xem [VectorMask](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html).

## 4. Masked load, phép toán và masked store có ngữ nghĩa riêng

Không nên suy rằng “lane false luôn được gán 0” cho mọi thao tác.

| Thao tác | Khi lane được bật | Khi lane bị tắt |
| --- | --- | --- |
| `FloatVector.fromArray(species, a, i, mask)` | Đọc phần tử `a[i + lane]` | Lane kết quả nhận `+0.0f` |
| `va.add(vb, mask)` | Cộng hai lane tương ứng | Giữ giá trị lane của `va` |
| `result.intoArray(out, i, mask)` | Ghi vào `out[i + lane]` | Không ghi vào phần tử tương ứng |
| `reduceLanes(op, mask)` | Cho lane tham gia reduction | Loại lane khỏi reduction |

Với masked load/store, việc kiểm tra biên mảng áp dụng cho các lane được bật. Lane bị tắt không cần tương ứng với một phần tử tồn tại trong mảng. Mask không miễn yêu cầu rằng mảng phải khác `null`.

Đây là hợp đồng của từng thao tác trong [FloatVector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html), không phải một cơ chế tự bảo vệ mọi lệnh xuất hiện sau khi tạo mask.

Một điểm quan trọng: **tạo mask không làm phép đọc không mask trở nên an toàn**. Muốn giới hạn một thao tác bộ nhớ, phải truyền mask vào chính thao tác đó.

## 5. Ví dụ hoàn chỉnh: khối đầy đủ và một phần đuôi có mask

Bài toán là cộng từng cặp phần tử:

```text
out[k] = a[k] + b[k]
```

Hợp đồng của ví dụ:

- Ba mảng khác `null` và có cùng độ dài.
- Mọi phần tử của hai đầu vào được xử lý đúng một lần.
- Phần đuôi không đọc hay ghi qua cuối mảng.

Lưu mã thành `TailMaskDemo.java` nếu muốn thực hành:

```java
import java.util.Arrays;
import java.util.Objects;
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorSpecies;

public class TailMaskDemo {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    public static void add(float[] a, float[] b, float[] out) {
        checkLengths(a, b, out);

        int n = a.length;
        int bound = SPECIES.loopBound(n);
        int i = 0;

        for (; i < bound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
            va.add(vb).intoArray(out, i);
        }

        if (i < n) {
            VectorMask<Float> tail = SPECIES.indexInRange(i, n);
            FloatVector va = FloatVector.fromArray(SPECIES, a, i, tail);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i, tail);
            va.add(vb).intoArray(out, i, tail);
        }
    }

    private static void checkLengths(float[] a, float[] b, float[] out) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        Objects.requireNonNull(out, "out");

        if (a.length != b.length || a.length != out.length) {
            throw new IllegalArgumentException(
                    "a, b and out must have equal lengths");
        }
    }

    public static void main(String[] args) {
        int lanes = SPECIES.length();
        int n = 2 * lanes + 1;
        float[] a = new float[n];
        float[] b = new float[n];
        float[] out = new float[n];

        for (int i = 0; i < n; i++) {
            a[i] = i;
            b[i] = 100.0f + i;
        }

        add(a, b, out);

        System.out.printf("lanes=%d, n=%d, tail=%d%n",
                lanes, n, n % lanes);
        System.out.println(Arrays.toString(out));
    }
}
```

`SPECIES_PREFERRED` chọn species ưu tiên của nền tảng Java đang chạy. Mã lấy bước nhảy và mask từ cùng species nên không phụ thuộc giả định tám hay mười sáu lane. Khái niệm lane và species được mô tả trong [Vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html).

Nếu nền tảng chọn tám lane, dữ liệu minh họa có 17 phần tử và một phần tử đuôi. Kết quả dự kiến:

```text
lanes=8, n=17, tail=1
[100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 114.0, 116.0, 118.0, 120.0, 122.0, 124.0, 126.0, 128.0, 130.0, 132.0]
```

Số lane và độ dài mảng in ra có thể khác trên máy khác.

### 5.1. Biên dịch và chạy

Dùng bộ công cụ JDK tương ứng với môi trường muốn thực hành, chẳng hạn JDK 22 hoặc JDK 27:

```shell
javac --add-modules jdk.incubator.vector TailMaskDemo.java
java --add-modules jdk.incubator.vector TailMaskDemo
```

Ví dụ chỉ dùng Vector API incubator, nên cần đưa module `jdk.incubator.vector` vào quá trình biên dịch và chạy. Riêng các thao tác này không đòi hỏi `--enable-preview`. Cảnh báo sử dụng module incubator là bình thường.

Đối chiếu [module Vector API của Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/module-summary.html), [module Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html) và tùy chọn `--add-modules` trong [lệnh java](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

## 6. Vì sao vòng lặp trên không bỏ sót hoặc vượt biên?

Có thể kiểm tra bằng các khoảng chỉ số.

### 6.1. Phần đầy đủ

`bound` là bội của `L`. Mỗi vòng lặp xử lý đoạn:

```text
[i, i + L)
```

Lần cuối bắt đầu tại `bound - L`, nên chỉ số lớn nhất được đọc hoặc ghi là `bound - 1`. Vì `bound <= n`, các thao tác không mask trong phần này hợp lệ.

Sau vòng lặp, `i == bound`.

### 6.2. Phần đuôi

Nếu `i < n`, số phần tử còn lại là `n - i`, nhỏ hơn `L`. Mask bật đúng các lane có:

```text
0 <= i + lane < n
```

Cả hai phép đọc và phép ghi đều dùng mask này. Do ba mảng có cùng độ dài, một lane được bật có chỉ số hợp lệ cho cả ba.

Mẫu chỉ xử lý phần đuôi một lần. Không cần tạo mảng phụ, thêm phần tử đệm hay sao chép dữ liệu sang vùng tạm.

### 6.3. Các trường hợp không có phần đuôi

- `n == 0`: vòng lặp và khối đuôi đều không chạy.
- `n < L`: không có khối đầy đủ; toàn bộ dữ liệu được xử lý như phần đuôi.
- `n % L == 0`: vòng lặp đầy đủ xử lý hết; điều kiện `i < n` là false.

Điều kiện của vòng đầy đủ là `i < bound`, không phải `i <= bound`.

## 7. Ba cách tổ chức phần đuôi

| Cách tổ chức | Đặc điểm | Điều cần cân nhắc |
| --- | --- | --- |
| Vector đầy đủ rồi scalar tail | Các phần tử cuối được xử lý từng phần tử | Dễ đối chiếu với vòng lặp scalar |
| Vector đầy đủ rồi masked tail | Một mask cho khối cuối không đầy đủ | Mẫu chính của bài |
| Mỗi vòng đều dùng mask | Mỗi khối tính mask theo giới hạn | Mã thống nhất nhưng có thể phát sinh thêm chi phí |

Nếu chọn scalar tail, giữ nguyên phần vector đầy đủ rồi thay khối `if` bằng:

```java
for (; i < n; i++) {
    out[i] = a[i] + b[i];
}
```

Cả scalar tail và masked tail đều là cách xử lý còn phù hợp. Không thể kết luận một cách luôn nhanh hơn trên mọi CPU, kích thước dữ liệu và JDK.

Tài liệu [package Vector API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html) minh họa dùng mask trong mọi vòng và lưu ý cách đó có thể chưa tối ưu cho mảng lớn. Việc sinh lệnh SIMD còn phụ thuộc khả năng của runtime và phần cứng; một API có ngữ nghĩa vector không phải bằng chứng về tốc độ thực tế của toàn bộ thuật toán.

## 8. Xử lý một khoảng con: phân biệt biên mảng và biên nghiệp vụ

Giả sử mảng có 100 phần tử nhưng chỉ được sửa đoạn `[from, to)`. Nếu tạo mask bằng `a.length`, các lane sau `to` vẫn có thể được bật vì chúng còn nằm trong mảng.

Đọc không vượt biên vật lý chưa đủ; phép ghi còn phải tôn trọng phạm vi mà bên gọi yêu cầu.

Phương thức dưới đây có thể thêm vào lớp `TailMaskDemo`, dùng lại `SPECIES` và `checkLengths`:

```java
public static void addRange(
        float[] a, float[] b, float[] out, int from, int to) {
    checkLengths(a, b, out);
    Objects.checkFromToIndex(from, to, a.length);

    int fullEnd = from + SPECIES.loopBound(to - from);
    int i = from;

    for (; i < fullEnd; i += SPECIES.length()) {
        FloatVector va = FloatVector.fromArray(SPECIES, a, i);
        FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
        va.add(vb).intoArray(out, i);
    }

    if (i < to) {
        VectorMask<Float> tail = SPECIES.indexInRange(i, to);
        FloatVector va = FloatVector.fromArray(SPECIES, a, i, tail);
        FloatVector vb = FloatVector.fromArray(SPECIES, b, i, tail);
        va.add(vb).intoArray(out, i, tail);
    }
}
```

Ở đây:

- `to - from` là số phần tử cần xử lý, dùng để tính số khối đầy đủ.
- `i` là chỉ số tuyệt đối trong mảng, nên mask dùng cận trên tuyệt đối `to`.
- Các phần tử của `out` trước `from` và từ `to` trở đi được giữ nguyên.

Ví dụ, với `from = 3`, `to = 14`, `L = 8`, khối đầy đủ bắt đầu ở 3, còn khối đuôi bắt đầu ở 11 và chỉ bật các chỉ số 11, 12, 13.

Không thay `indexInRange(i, to)` bằng `indexInRange(i, to - from)` khi `i` vẫn là chỉ số tuyệt đối. Hai đối số của mask phải được hiểu trong cùng hệ tọa độ.

## 9. Kết hợp mask giới hạn và mask điều kiện dữ liệu

Mask phần đuôi trả lời “lane này có thuộc phạm vi dữ liệu không?”. Mask điều kiện trả lời “giá trị của lane này có thỏa điều kiện không?”. Hai câu hỏi khác nhau.

Các đoạn minh họa điều kiện và reduction dưới đây dùng thêm import:

```java
import jdk.incubator.vector.VectorOperators;
```

Giả sử đang ở vị trí `i` trong phạm vi `[0, n)`, hai mảng `input` và `out` đủ dài. Muốn chỉ ghi những phần tử không âm:

```java
VectorMask<Float> inRange = SPECIES.indexInRange(i, n);
FloatVector value = FloatVector.fromArray(SPECIES, input, i, inRange);

VectorMask<Float> nonNegative =
        value.compare(VectorOperators.GE, 0.0f);

VectorMask<Float> selected = inRange.and(nonNegative);
value.intoArray(out, i, selected);
```

Phép so sánh `GE` kiểm tra lớn hơn hoặc bằng; các operator so sánh được định nghĩa trong [VectorOperators](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html).

Vì masked load điền `+0.0f` vào lane bị tắt, các lane không có dữ liệu cũng có thể vượt qua điều kiện “không âm”. Phép `and(inRange)` loại chúng trước khi ghi.

Nếu chỉ dùng `nonNegative` làm mask ghi, chương trình có thể bật lại các lane vượt phạm vi. Tương tự, khi phủ định một điều kiện bằng `not()`, vẫn phải giao với mask giới hạn.

Ví dụ trên giữ nguyên phần tử đích khi dữ liệu không thỏa điều kiện. Nó không tạo danh sách được nén và không dồn các phần tử được chọn về đầu mảng.

## 10. Reduction: lane được nạp thành 0 vẫn có thể làm sai kết quả

Với phép cộng từng cặp trong ví dụ chính, có thể dùng `va.add(vb)` không mask sau hai masked load, vì:

- Mỗi lane được tính độc lập.
- Các lane không hợp lệ không được ghi ra nhờ masked store.
- Không có thao tác trộn lane không hợp lệ vào lane hợp lệ.

Không áp dụng suy luận đó một cách máy móc cho reduction hoặc thao tác chéo lane.

### 10.1. Ví dụ tìm min của phần đuôi

Giả sử một vector tám lane được nạp từ ba giá trị dương:

```text
dữ liệu thật:   [5, 7, 9]
masked load:   [5, 7, 9, 0, 0, 0, 0, 0]
mask hợp lệ:   [T, T, T, F, F, F, F, F]
```

Nếu giảm tất cả lane bằng `MIN`, các số 0 được điền vào làm kết quả trở thành 0, trong khi min của dữ liệu thật là 5.

Ở khối đuôi, dùng reduction có mask:

```java
VectorMask<Float> tail = SPECIES.indexInRange(i, n);
FloatVector value = FloatVector.fromArray(SPECIES, input, i, tail);

float tailMinimum = value.reduceLanes(VectorOperators.MIN, tail);
```

Đoạn này chỉ tính min của khối đuôi; bên gọi còn cần kết hợp với kết quả của các khối trước theo thuật toán tương ứng.

Đối chiếu [reduceLanes với mask](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html#reduceLanes(jdk.incubator.vector.VectorOperators.Associative,jdk.incubator.vector.VectorMask)).

### 10.2. Không coi 0 là giá trị trung tính cho mọi phép toán

Với các giá trị hữu hạn thông thường:

| Phép kết hợp | Giá trị trung tính về mặt toán học | Nguy cơ nếu đưa thêm 0 |
| --- | --- | --- |
| Cộng | 0 | Cần tiếp tục xét quy tắc số thực của thuật toán |
| Nhân | 1 | Có thể làm tích trở thành 0 |
| Min | Dương vô cực | Có thể làm giảm sai min của dữ liệu dương |
| Max | Âm vô cực | Có thể làm tăng sai max của dữ liệu âm |

Dùng overload reduction có mask giúp biểu đạt trực tiếp lane nào được tính. Với mask không có lane được bật, API trả giá trị identity theo phép reduction; bên gọi vẫn cần định nghĩa ý nghĩa nghiệp vụ của đầu vào rỗng.

Khi cộng hoặc nhân số thực qua reduction, thứ tự kết hợp có thể khác vòng lặp scalar. Cần có tiêu chí sai số và quy tắc cho `NaN`, vô cực, số 0 có dấu phù hợp; xem phần reduction của `FloatVector`.

### 10.3. Phép toán có điều kiện hợp lệ riêng

Ví dụ, khi chuyển sang phép chia `IntVector`, lane mẫu số được masked load thành 0 có thể gây lỗi nếu sau đó dùng phép chia không mask trên toàn bộ vector.

Cần chọn phép chia có mask để loại lane không hợp lệ khỏi phép toán, đồng thời vẫn xử lý mẫu số 0 ở lane dữ liệu thật theo hợp đồng ứng dụng. Xem [IntVector.div](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html).

Mask ở phép ghi không sửa được một lỗi đã phát sinh trong phép toán trước đó.

## 11. Những lỗi thường gặp

| Mẫu sai hoặc thiếu | Hậu quả | Cách tổ chức đúng |
| --- | --- | --- |
| Chạy full load khi `i < n` mà không xét số lane còn lại | Đọc vượt biên ở khối cuối | Giới hạn phần đầy đủ bằng `loopBound` hoặc dùng masked load |
| Masked load nhưng store không mask | Có thể ghi vượt biên hoặc ghi ngoài khoảng cần sửa | Truyền mask giới hạn vào store |
| Chỉ mask phép toán, còn load không mask | Lỗi đọc xảy ra trước khi tính toán | Bảo vệ từng thao tác bộ nhớ |
| Dùng `i <= bound` cho vòng đầy đủ | Thêm một khối không hợp lệ | Dùng `i < bound` |
| Ghi cứng bước nhảy là 8 | Mất đúng đắn khi species khác | Lấy bước từ `SPECIES.length()` |
| Tạo mask từ độ dài một đầu vào nhưng mảng khác ngắn hơn | Lane được bật không hợp lệ với mảng còn lại | Kiểm tra hợp đồng độ dài hoặc xác định phạm vi chung rõ ràng |
| Dùng chiều dài mảng làm cận khi chỉ xử lý khoảng con | Sửa dữ liệu ngoài phạm vi bên gọi yêu cầu | Dùng cận logic của khoảng |
| Dùng riêng mask điều kiện sau masked load | Có thể chọn cả lane không có dữ liệu | Kết hợp điều kiện với mask giới hạn |
| Reduce mọi lane sau masked load | Giá trị điền vào tham gia kết quả | Dùng reduction có mask hoặc thiết kế giá trị trung tính đúng |

Không lấy `Math.min` độ dài các mảng chỉ để tránh ngoại lệ nếu hợp đồng yêu cầu ba mảng bằng nhau. Cách đó có thể che giấu dữ liệu đầu vào thiếu hoặc kết quả bị bỏ sót.

## 12. Các ca biên cần đối chiếu khi áp dụng

Với `L = SPECIES.length()`, những độ dài sau giúp quan sát cả hai nhánh xử lý:

| Độ dài | Điều cần kiểm tra |
| --- | --- |
| 0 | Không truy cập dữ liệu |
| 1 | Xử lý dữ liệu rất ngắn |
| `L - 1` nếu dương | Toàn bộ dữ liệu là phần đuôi |
| `L` | Một khối đầy đủ, không có đuôi |
| `L + 1` | Một khối đầy đủ và một lane đuôi |
| `2 * L - 1` | Khối cuối thiếu một lane |
| `2 * L` | Nhiều khối đầy đủ, không có đuôi |
| `2 * L + 3` | Nhiều khối và phần dư theo species thực tế |

Với `addRange`, bổ sung khoảng rỗng, điểm bắt đầu khác 0 và điểm kết thúc trước cuối mảng. Có thể điền một giá trị đánh dấu vào `out` rồi kiểm tra phần trước `from` và từ `to` trở đi không thay đổi.

Đối chiếu với một vòng lặp scalar có cùng hợp đồng. Với ví dụ cộng từng cặp, các số nguyên nhỏ biểu diễn chính xác bằng `float` giúp xác định giá trị mong đợi dễ dàng. Với thuật toán số thực phức tạp hơn, cần tiêu chí so sánh theo chính thuật toán.

Khi đọc mã xử lý đuôi, hãy theo đường đi của từng lane: chỉ số nào tồn tại, lệnh nào thật sự nhận mask, giá trị nào được điền vào lane tắt và liệu giá trị đó có thể tham gia kết quả cuối hay không.
