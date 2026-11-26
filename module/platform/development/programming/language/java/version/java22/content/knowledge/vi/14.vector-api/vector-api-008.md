# Reduction, chuyển kiểu và sắp xếp lại lane theo yêu cầu thuật toán

Một thuật toán vector thường bắt đầu bằng phép tính độc lập trên từng lane, nhưng không phải lúc nào kết quả cũng giữ nguyên kiểu và vị trí. Tính tổng cần gộp nhiều lane thành một giá trị; cộng số nguyên lớn cần mở rộng kiểu trước khi tràn; xử lý dữ liệu theo cặp cần đưa các phần tử liên quan về đúng vị trí.

Bài này trình bày cách phối hợp ba thao tác đó theo ý nghĩa của thuật toán. Mục tiêu là giữ đúng dữ liệu, kiểu số và quan hệ chỉ số trước khi xét lợi ích hiệu năng.

Các khái niệm và API nền tảng đã có trong Java 22 vẫn hiện diện ở tài liệu Java hiện đại. Phần hợp đồng API được đối chiếu với **JDK 27**; `jdk.incubator.vector` tại mốc này vẫn là incubator module, chưa phải API ổn định giữa mọi bản JDK. Xem [IntVector của Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html) và [mô-đun Vector API hiện hành](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html).

## 1. Ba thao tác thay đổi những gì?

| Thao tác | Ví dụ về dữ liệu | Kết quả cần quan tâm |
| --- | --- | --- |
| Reduction | `[3, 5, 7, 9]` thành tổng `24` | Kiểu của phép gộp, giá trị khởi tạo và thứ tự tính |
| Chuyển giá trị số | Bốn `int` được biểu diễn thành các `long` | Giá trị có được giữ đúng không, cần bao nhiêu phần kết quả |
| Sắp xếp lại lane | `[3, 5, 7, 9]` thành `[5, 3, 9, 7]` | Mỗi lane đích đọc từ lane nguồn nào |

Phép cộng hai vector tương ứng từng lane vẫn tạo một vector. Reduction đi qua ranh giới lane để tạo một scalar. Shuffle chuyển vị trí dữ liệu theo bản đồ chỉ số. Các nhóm thao tác này được phân biệt trong [mô hình Vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html).

Ví dụ các lane có thể biểu diễn số phút học, số lượt tương tác hoặc các cặp đặc trưng. Chính cách biểu diễn đó quyết định nên gộp, chuyển kiểu hay đổi bố trí ở bước nào.

## 2. Reduction: từ nhiều lane về một kết quả

### Chọn phép gộp có ngữ nghĩa phù hợp

Với một `IntVector v`, các lời gọi quen thuộc là:

```java
int sum = v.reduceLanes(VectorOperators.ADD);
int minimum = v.reduceLanes(VectorOperators.MIN);
int maximum = v.reduceLanes(VectorOperators.MAX);
```

Những đoạn ngắn trong bài giả định đã import các kiểu của `jdk.incubator.vector` được sử dụng. Ví dụ hoàn chỉnh ở phần sau cung cấp đầy đủ import và lệnh chạy.

Reduction nhận một operator thuộc nhóm `VectorOperators.Associative`, không nhận một lambda tùy ý. Phép trừ tuần tự không thể được thay trực tiếp bằng một reduction cộng mà vẫn giữ nguyên ý nghĩa. Hợp đồng operator nằm trong [VectorOperators](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html).

Với phép tổng trên số nguyên, một mô hình hữu ích là tích lũy theo lane qua nhiều khối rồi reduction ở cuối:

```text
Khối 0:  [a0, a1, a2, a3]
Khối 1:  [a4, a5, a6, a7]
                ↓ cộng theo lane
Tích lũy: [a0+a4, a1+a5, a2+a6, a3+a7]
                ↓ reduction
Tổng các phần tử
```

Cách tổ chức này giảm số lần chuyển từ kết quả vector về scalar so với reduction từng khối. Đó là một lựa chọn cần đo trên thuật toán thực tế, không phải bảo đảm mọi máy đều chạy nhanh hơn.

### Giá trị đơn vị phụ thuộc phép gộp

Khi mask không chọn lane nào, reduction trả về giá trị đơn vị của operator. Với `IntVector`:

| Operator | Giá trị khi không có lane được chọn |
| --- | --- |
| `ADD`, `OR`, `XOR` | `0` |
| `MUL` | `1` |
| `MIN` | `Integer.MAX_VALUE` |
| `MAX` | `Integer.MIN_VALUE` |
| `AND` | `-1`, tức mọi bit đều bằng 1 |

Các giá trị này được quy định trong [IntVector.reduceLanes](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html). Chúng không thay thế quyết định nghiệp vụ cho tập dữ liệu rỗng. Ví dụ một phương thức tìm điểm nhỏ nhất có thể chọn trả `OptionalInt.empty()` khi không có điểm, thay vì công khai `Integer.MAX_VALUE` như một điểm thật.

### Phần cuối mảng cần đúng mask của phép reduction

Một đoạn đọc phần cuối có thể viết:

```java
var valid = species.indexInRange(offset, data.length);
var tail = IntVector.fromArray(species, data, offset, valid);
int minimum = tail.reduceLanes(VectorOperators.MIN, valid);
```

Ở đây `species` là `VectorSpecies<Integer>` và `offset` nằm trong khoảng từ 0 đến độ dài mảng. Đọc có mask không cho phép phần tử ngoài mảng trở thành dữ liệu thật của thuật toán.

Các lane không được tải có giá trị 0. Nếu dữ liệu hợp lệ toàn số dương mà bỏ mask ở bước tìm `MIN`, các số 0 đệm có thể làm kết quả sai. Với phép cộng, 0 tình cờ là giá trị đơn vị; không được khái quát điều đó cho mọi operator.

## 3. Chọn kiểu tích lũy trước khi xảy ra tràn

Giả sử cần cộng hai giá trị `2_000_000_000`. Tổng toán học là `4_000_000_000`, vượt miền của `int` nhưng vẫn nằm trong miền của `long`.

Đoạn sau không giải quyết được việc tràn trong reduction:

```java
long total = v.reduceLanes(VectorOperators.ADD);
```

Reduction của `IntVector` tạo kết quả `int`, sau đó phép gán mới mở rộng kết quả sang `long`. Nếu `int` đã tràn, phép mở rộng không khôi phục tổng toán học.

Tên phương thức sau cũng dễ gây hiểu lầm:

```java
long total = v.reduceLanesToLong(VectorOperators.ADD);
```

Hợp đồng của `reduceLanesToLong` tương đương việc reduction theo kiểu lane rồi cast kết quả sang `long`. Nó không tự mở rộng từng lane sang `long` trước khi cộng. Xem [Vector.reduceLanesToLong](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html).

Khi cần tổng chính xác của các `int`, hãy mở rộng dữ liệu sang lane `long` trước khi cộng, rồi reduction trên `LongVector`. Tương tự, với tích có thể vượt `int`, việc chuyển sang `long` phải xảy ra trước phép nhân có nguy cơ tràn.

Lựa chọn kiểu là một phần của hợp đồng thuật toán. Nếu chủ đích là số học `int` có tràn theo quy tắc Java, phép tính đó có thể phù hợp; nếu cần tổng toán học rộng hơn thì phải chọn kiểu tích lũy tương ứng.

## 4. Chuyển kiểu phải xét cả giá trị và số lane

### Cùng shape không có nghĩa cùng số phần tử

Một shape 128 bit chứa bốn lane `int` hoặc hai lane `long`. Khi chuyển bốn `int` sang giá trị `long`, kết quả logic cần 256 bit. Một vector `long` 128 bit chỉ chứa được một nửa kết quả đó:

```text
Nguồn int 128 bit:      [10, 20, 30, 40]
Kết quả logic long:    [10L, 20L, 30L, 40L]

convert(I2L, 0):       [10L, 20L]
convert(I2L, 1):       [30L, 40L]
```

Một ví dụ về chính phép chuyển này:

```java
var ints = IntVector.fromArray(
        IntVector.SPECIES_128, new int[] {10, 20, 30, 40}, 0);

LongVector first = (LongVector) ints.convert(VectorOperators.I2L, 0);
LongVector second = (LongVector) ints.convert(VectorOperators.I2L, 1);
```

`part` chọn phần kết quả khi số lane không khớp; nó không phải chỉ số phần tử đầu trong mảng. Dùng duy nhất `part = 0` ở ví dụ này bỏ qua hai phần tử cuối nếu thuật toán cần toàn bộ dữ liệu.

`convert` giữ nguyên shape và suy ra species đích từ kiểu của operator. `convertShape` cho phép chỉ định species đích; khi thay đổi shape, tỷ lệ số lane và cách chọn phần kết quả cũng phải được tính lại. Hợp đồng nằm trong [Vector.convert và convertShape](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html).

Ví dụ tổng hợp bên dưới dùng `convert(I2L, 0)` và `convert(I2L, 1)`. Species `long` có cùng shape được tạo bằng `intSpecies.withLanes(long.class)`, theo [VectorSpecies.withLanes](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html).

### Chuyển giá trị số khác với đọc lại bit

Với các lane `float` như `[1.0f, -2.0f, 3.5f, 0.0f]`:

```java
IntVector numbers = (IntVector) floats.convert(VectorOperators.F2I, 0);
IntVector bits = floats.reinterpretAsInts();
```

Ở đây `floats` là `FloatVector` tương thích về shape. `numbers` chứa giá trị số nguyên sau cast, chẳng hạn `[1, -2, 3, 0]`. `bits` chứa các mẫu bit của giá trị `float` được đọc như `int`; lane của `1.0f` tương ứng mẫu `0x3f800000`, không phải số nguyên 1.

Chọn chuyển giá trị khi thuật toán cần số ở kiểu mới. Chọn reinterpret khi xử lý biểu diễn nhị phân, chẳng hạn thao tác trên bit của dữ liệu. Việc dùng reinterpret để thay một phép cast số sẽ thay đổi ý nghĩa đầu vào.

### Chuyển hẹp không tự thực hiện quy tắc làm tròn nghiệp vụ

Operator `F2I` tương ứng cast `(int) floatValue`. Với giá trị hữu hạn trong miền phù hợp, phần lẻ bị bỏ theo hướng về 0: `3.9f` thành `3`, `-3.9f` thành `-3`. `NaN` thành 0; giá trị quá lớn hoặc quá nhỏ được xử lý theo quy tắc cast sang số nguyên của Java. Xem [JLS §5.1.3](https://docs.oracle.com/javase/specs/jls/se27/html/jls-5.html#jls-5.1.3).

Nếu thuật toán yêu cầu làm tròn gần nhất, báo lỗi khi ngoài miền hoặc chặn giá trị trong một khoảng nghiệp vụ, hãy thực hiện chính sách đó một cách rõ ràng. Đừng suy ra rằng mọi conversion đều tự làm tròn hoặc kiểm tra tràn theo cùng một cách.

## 5. Số thực: đổi thứ tự cộng có thể đổi kết quả

Phép cộng số thực không kết hợp chính xác như phép cộng trên số thực toán học. Hai cách nhóm `((a + b) + c)` và `(a + (b + c))` có thể làm tròn khác nhau.

Reduction `ADD` hoặc `MUL` trên vector số thực có thể chọn thứ tự gộp để phù hợp phần cứng. Không giả định nó giống vòng lặp scalar cộng từ trái sang phải, hoặc cho kết quả bit giống nhau ở mọi lần thực thi và mọi nền tảng. Xem [FloatVector.reduceLanes](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html).

Ví dụ, ba giá trị `1e20f`, `-1e20f`, `3.0f` có thể cho kết quả khác nhau tùy cách nhóm phép cộng. Đây là hệ quả của cách biểu diễn và làm tròn, không tự chứng minh cài đặt vector sai.

Trước khi vector hóa một phép tổng số thực, cần xác định mức sai số chấp nhận được, cách xử lý `NaN`, vô cực và yêu cầu tái lập kết quả. Nếu kết quả buộc phải đúng từng bit theo một thứ tự tính cụ thể, không đổi sang reduction có thứ tự không xác định rồi giữ nguyên kỳ vọng so sánh.

## 6. Shuffle: mô tả lane đích đọc từ đâu

Với vector `[10, 20, 30, 40]` và shuffle `[1, 0, 3, 2]`:

```text
Lane đích:         0   1   2   3
Lane nguồn được lấy: 1   0   3   2
Kết quả:          20  10  40  30
```

Quy tắc cần ghi nhớ là:

```text
result[destination] = input[sourceIndex[destination]]
```

Shuffle chỉ định chỉ số nguồn cho từng lane đích. Cùng một chỉ số nguồn có thể được chọn nhiều lần; đây không nhất thiết là phép hoán vị một-một. `VectorShuffle` lưu các chỉ số, không lưu giá trị dữ liệu cần xử lý. Xem [VectorShuffle](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorShuffle.html).

Để đổi chỗ các cặp lane liền kề trong species `int` đang dùng:

```java
var swapPairs = VectorShuffle.fromOp(species, lane -> lane ^ 1);
var swapped = vector.rearrange(swapPairs);
```

Ví dụ ánh xạ `0 → 1`, `1 → 0`, `2 → 3`, `3 → 2`. Species `int` trong các shape thông dụng của ví dụ có số lane chẵn, nên ánh xạ này nằm trong miền hợp lệ. Tạo shuffle cố định ngoài vòng lặp, sau đó tái sử dụng cho các khối có cùng species.

Một shuffle đảo thứ tự trong khối có thể dùng `lane -> species.length() - 1 - lane`. Đảo từng khối không đồng nghĩa đảo toàn bộ mảng: thuật toán đảo cả mảng còn phải thay đổi vị trí của các khối khi lưu kết quả.

### Ghép hai nguồn theo bố trí thuật toán

Khi có hai vector `a = [a0, a1, a2, a3]` và `b = [b0, b1, b2, b3]`, `makeZip` có thể giúp tạo bố trí xen kẽ:

```text
Phần 0: [a0, b0, a1, b1]
Phần 1: [a2, b2, a3, b3]
```

Hai phần cần thiết vì kết quả logic có tám lane, trong khi mỗi vector đầu ra chứa bốn lane. Các phương thức `VectorShuffle.makeZip` và `makeUnzip` mô tả kiểu tổ chức này trong [tài liệu VectorShuffle](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorShuffle.html).

Chọn bố trí theo bước tính kế tiếp. Ví dụ dữ liệu hai thành phần của một cặp có thể cần xen kẽ khi lưu nhưng cần tách riêng khi tính toán. Mỗi lần đổi bố trí có chi phí, nên không thêm shuffle chỉ để làm đoạn mã có vẻ vector hóa hơn.

## 7. Mask phải theo đúng vị trí dữ liệu sau shuffle

Có hai vấn đề khác nhau: đọc bộ nhớ an toàn và biết lane nào đại diện cho dữ liệu thật sau khi di chuyển.

Giả sử một khối cuối bốn lane chỉ có hai phần tử hợp lệ:

```text
Dữ liệu sau masked load: [4, 8, 0, 0]
Mask hợp lệ ban đầu:    [T, T, F, F]

Sau khi đảo khối:       [0, 0, 8, 4]
Mask hợp lệ tương ứng:  [F, F, T, T]
```

Nếu giữ mask cũ rồi reduction trên hai lane đầu, thuật toán chọn các số 0 đệm thay vì hai giá trị thật. Khi shuffle được dùng cho dữ liệu có mask ngữ nghĩa, phải xác định lại tính hợp lệ của lane đích dựa trên lane nguồn được chọn.

Overload `rearrange(shuffle, mask)` dùng mask để chọn **lane đầu ra** và đặt lane không được chọn thành 0. Nó không tự hiểu mask nào đánh dấu dữ liệu thật ở bố trí ban đầu. Xem [IntVector.rearrange](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html).

Khi conversion thay đổi số lane, mask cũ cũng không thể được áp lại máy móc cho species mới. Ví dụ hoàn chỉnh bên dưới dùng vòng lặp scalar cho phần cuối để giữ việc theo dõi chỉ số đơn giản.

## 8. Ví dụ hoàn chỉnh: tổng rộng và đổi chỗ từng cặp

Chương trình sau có hai thuật toán độc lập:

- `sumAsLong` mở rộng các lane `int` sang `long`, tích lũy rồi reduction một lần ở cuối.
- `swapAdjacent` đổi chỗ từng cặp phần tử, giữ nguyên phần tử cuối nếu số phần tử lẻ.

Cả hai dùng `SPECIES_PREFERRED` cho đường xử lý khối đầy đủ và scalar cho phần dư. Mảng được giả định khác `null`.

Lưu vào `VectorLaneOpsDemo.java`:

```java
import java.util.Arrays;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.LongVector;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorShuffle;
import jdk.incubator.vector.VectorSpecies;

public class VectorLaneOpsDemo {
    private static final VectorSpecies<Integer> INTS = IntVector.SPECIES_PREFERRED;
    private static final VectorSpecies<Long> LONGS = INTS.withLanes(long.class);
    private static final VectorShuffle<Integer> SWAP_PAIRS =
            VectorShuffle.fromOp(INTS, lane -> lane ^ 1);

    static long sumAsLong(int[] input) {
        LongVector firstAcc = LongVector.zero(LONGS);
        LongVector secondAcc = LongVector.zero(LONGS);
        int limit = INTS.loopBound(input.length);
        int i = 0;

        for (; i < limit; i += INTS.length()) {
            IntVector values = IntVector.fromArray(INTS, input, i);
            LongVector first = (LongVector) values.convert(VectorOperators.I2L, 0);
            LongVector second = (LongVector) values.convert(VectorOperators.I2L, 1);
            firstAcc = firstAcc.add(first);
            secondAcc = secondAcc.add(second);
        }

        long total = firstAcc.add(secondAcc).reduceLanes(VectorOperators.ADD);
        for (; i < input.length; i++) {
            total += input[i];
        }
        return total;
    }

    static int[] swapAdjacent(int[] input) {
        int[] output = new int[input.length];
        int limit = INTS.loopBound(input.length);
        int i = 0;

        for (; i < limit; i += INTS.length()) {
            IntVector values = IntVector.fromArray(INTS, input, i);
            values.rearrange(SWAP_PAIRS).intoArray(output, i);
        }

        for (; i + 1 < input.length; i += 2) {
            output[i] = input[i + 1];
            output[i + 1] = input[i];
        }
        if (i < input.length) {
            output[i] = input[i];
        }
        return output;
    }

    public static void main(String[] args) {
        int[] input = new int[INTS.length() + 3];
        Arrays.setAll(input, i -> i + 1);
        input[0] = 2_000_000_000;
        input[1] = 2_000_000_000;

        long expectedSum = 0;
        for (int value : input) {
            expectedSum += value;
        }
        System.out.println("sumMatches=" + (sumAsLong(input) == expectedSum));

        int[] swapped = swapAdjacent(input);
        boolean swapMatches = true;
        for (int i = 0; i < input.length; i++) {
            int source = i ^ 1;
            if (source >= input.length) {
                source = i;
            }
            swapMatches &= swapped[i] == input[source];
        }
        System.out.println("swapMatches=" + swapMatches);
    }
}
```

Biên dịch và chạy trên JDK có mô-đun Vector API tương ứng; ví dụ được đối chiếu API JDK 27:

```shell
javac --add-modules jdk.incubator.vector VectorLaneOpsDemo.java
java --add-modules jdk.incubator.vector VectorLaneOpsDemo
```

Kết quả ứng dụng mong đợi, ngoài cảnh báo incubator nếu có:

```text
sumMatches=true
swapMatches=true
```

Độ dài dữ liệu được tạo dựa trên species để luôn có một khối đầy đủ và phần dư, thay vì vô tình chỉ chạy đường scalar trên máy có vector rộng. Hai giá trị lớn bảo đảm ví dụ tổng cần miền kết quả rộng hơn `int`.

### Vì sao không bỏ sót nửa sau khi mở rộng?

Mỗi vector nguồn `int` có số lane gấp đôi species `long` cùng shape. Hai lần `convert` lấy lần lượt nửa đầu và nửa sau. Hai vector tích lũy giữ toàn bộ phần đóng góp, sau đó được cộng và reduction bằng [LongVector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/LongVector.html).

Với một mảng Java gồm các `int`, tổng của mọi phần tử nằm trong miền của `long`; phương pháp này tránh tràn do cộng trong lane `int`. Không khái quát kết luận đó cho tích hoặc tổng nhiều tập dữ liệu có thể vượt cả `long`.

### Vì sao đổi cặp trong từng khối vẫn đúng trên cả mảng?

Số lane `int` của species dùng trong ví dụ là chẵn, nên ranh giới giữa các khối cũng là ranh giới giữa các cặp. Phần scalar tiếp tục từ một chỉ số chẵn và giữ lại phần tử cuối nếu cần. Nếu thuật toán dùng nhóm ba hoặc một bố trí khác, phải kiểm tra lại quan hệ giữa kích thước nhóm và ranh giới khối.

Phép kiểm tra trong `main` minh họa đối chiếu với định nghĩa scalar. Nó không đo thông lượng, chi phí conversion hoặc chi phí shuffle.

## 9. Chọn thứ tự thao tác theo yêu cầu thuật toán

| Nhu cầu | Thứ tự cần cân nhắc |
| --- | --- |
| Tổng các số `int` có thể vượt `int` | Mở rộng giá trị → cộng lane `long` → reduction |
| Tổng có điều kiện | Tạo điều kiện hợp lệ → tích lũy/reduction theo mask đúng bố trí |
| Phân tích bit của giá trị `float` | Reinterpret biểu diễn → thao tác bit |
| Chuyển dữ liệu số thực sang chỉ số nguyên | Xác định quy tắc miền và làm tròn → conversion |
| Xử lý từng cặp hoặc đổi bố trí đặc trưng | Xác định ánh xạ nguồn–đích → shuffle → phép tính kế tiếp |
| Đổi bố trí một khối cuối chưa đầy | Theo dõi dữ liệu hợp lệ sau ánh xạ hoặc xử lý scalar |

Không đổi thứ tự conversion và phép tính một cách tùy ý. Chẳng hạn “cộng hai `int` rồi chuyển kết quả sang `long`” khác “chuyển hai `int` sang `long` rồi cộng” khi có tràn. Tương tự, conversion số thực và reduction có thể thay đổi cách làm tròn.

Trước khi tối ưu, hãy xác định kiểu kết quả, miền giá trị, số phần đầu ra của conversion và ý nghĩa từng lane. Khi những điều này rõ ràng, việc chọn `reduceLanes`, `convert` hay `rearrange` trở thành lựa chọn có cơ sở từ thuật toán thay vì thử ghép các API.

## 10. Những trường hợp nên đối chiếu khi áp dụng

Một triển khai thực tế nên được đối chiếu với định nghĩa scalar bằng các dữ liệu làm lộ sai lệch:

- Mảng rỗng, một phần tử, khối đầy đủ và độ dài không chia hết số lane.
- Giá trị âm và tổng vượt `int`, để phát hiện conversion quá muộn.
- Dữ liệu có kết quả khác nhau ở nửa đầu và nửa sau, để phát hiện bỏ quên `part`.
- Shuffle có bản đồ chỉ số bất đối xứng hoặc lặp chỉ số, để phát hiện nhầm chiều nguồn–đích.
- Số thực có độ lớn chênh lệch, cùng chính sách rõ cho sai số và giá trị đặc biệt.

Sau khi đúng ngữ nghĩa, mới so sánh hiệu năng trên JDK và CPU mục tiêu, với dữ liệu đại diện cho ứng dụng. Giữ shuffle không đổi ngoài vòng lặp và hạn chế chuyển qua lại giữa kiểu/bố trí khi không cần thiết. Những lựa chọn này cần được đánh giá trên cả thuật toán, vì một phép vector riêng lẻ chưa nói lên chi phí của toàn bộ chuỗi xử lý.