# VectorSpecies, số lane và lựa chọn species phù hợp với nền tảng

## 1. Vì sao không nên mặc định một vector luôn có 8 phần tử?

Khi cộng hai mảng `float`, một phép toán vector có thể xử lý nhiều phần tử ở cùng vị trí tương ứng. Nhưng số phần tử được xử lý trong một vector không cố định cho mọi máy và mọi kiểu dữ liệu. Vector 256 bit chứa 8 giá trị `float`, trong khi cùng độ rộng đó chỉ chứa 4 giá trị `double`.

`VectorSpecies` mô tả định dạng của vector mà thuật toán sẽ dùng. Từ species, chương trình biết kiểu phần tử, độ rộng toàn vector, số lane và cách chia một mảng thành các khối xử lý phù hợp.

Bài học thuộc module Java 22 và tập trung vào những khái niệm vẫn còn áp dụng: chọn species theo nền tảng, lấy số lane qua API và viết vòng lặp không phụ thuộc một độ rộng hardcode. Các thành phần cốt lõi được trình bày có trong [API Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html) và tiếp tục được sử dụng trong [API Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html).

**Mốc đối chiếu hiện đại: JDK 27, ngày 25/11/2026.** Vector API vẫn thuộc module incubator `jdk.incubator.vector`. Incubator là trạng thái phát triển của API, khác với preview. Các ví dụ chỉ dùng Vector API trong bài cần thêm module lúc biên dịch và chạy; không cần `--enable-preview` chỉ để dùng các phép toán này. Tên package và hợp đồng của API cần được đối chiếu lại khi đổi JDK vì đây chưa phải API Java SE ổn định. Xem [module `jdk.incubator.vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html).

## 2. Species được tạo từ kiểu phần tử và shape

### 2.1. Ba khái niệm cần tách biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Kiểu phần tử | Kiểu primitive của một giá trị trong vector | `float`, `double`, `int` |
| Shape | Độ rộng tổng thể của vector | `VectorShape.S_256_BIT` |
| Species | Tổ hợp kiểu phần tử và shape | `float` với shape 256 bit |

Một **lane** là một vị trí chứa một phần tử trong vector. Chỉ số lane bắt đầu từ 0 và kết thúc ở `species.length() - 1`.

Ví dụ, một vector `float` 256 bit có thể được hình dung như sau:

```text
Toàn vector: 256 bit = 32 byte

lane       0        1        2        3        4        5        6        7
       ┌────────┬────────┬────────┬────────┬────────┬────────┬────────┬────────┐
float  │ 32 bit │ 32 bit │ 32 bit │ 32 bit │ 32 bit │ 32 bit │ 32 bit │ 32 bit │
       └────────┴────────┴────────┴────────┴────────┴────────┴────────┴────────┘
```

Lane là vị trí dữ liệu của mô hình SIMD. Nó không phải một Java thread, một CPU core hay một tác vụ được tạo qua executor.

### 2.2. Công thức tính số lane

Với species đã chọn:

```text
số lane = số bit toàn vector / số bit của một phần tử
```

Trong API, quan hệ tương ứng là:

```text
species.length() = species.vectorBitSize() / species.elementSize()
```

| Độ rộng vector | Số byte toàn vector | Lane `byte` (8 bit) | Lane `short` (16 bit) | Lane `int` hoặc `float` (32 bit) | Lane `long` hoặc `double` (64 bit) |
| --- | --- | --- | --- | --- | --- |
| 64 bit | 8 | 8 | 4 | 2 | 1 |
| 128 bit | 16 | 16 | 8 | 4 | 2 |
| 256 bit | 32 | 32 | 16 | 8 | 4 |
| 512 bit | 64 | 64 | 32 | 16 | 8 |

Bảng thể hiện số học của các định dạng, không khẳng định mọi tổ hợp đều được phần cứng của máy bạn tăng tốc.

Không nên tự tính số lane tại mọi điểm sử dụng. Hãy lấy `species.length()` để mã làm việc với đúng species đang chọn. Cách này cũng tránh lỗi nhầm bit với byte.

### 2.3. `VectorSpecies<Float>` vẫn biểu diễn các lane primitive

Một khai báo thường gặp:

```java
private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;
```

Tham số generic là `Float` vì generic của Java dùng kiểu tham chiếu. Các lane của `FloatVector` chứa giá trị primitive `float`; khai báo này không yêu cầu tạo một đối tượng `Float` cho từng lane.

Khi truyền lớp kiểu phần tử vào factory, dùng primitive class:

```java
VectorSpecies<Float> preferred = VectorSpecies.ofPreferred(float.class);
VectorSpecies<Float> fixed256 =
        VectorSpecies.of(float.class, VectorShape.S_256_BIT);
```

`float.class` và `Float.class` có vai trò khác nhau. Các factory này yêu cầu kiểu phần tử primitive hợp lệ, không phải wrapper class. Chi tiết nằm trong [API `VectorSpecies`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html).

## 3. Đọc đúng các thông số của species

| Phương thức | Đại lượng trả về | Đơn vị hoặc dạng kết quả |
| --- | --- | --- |
| `elementType()` | Kiểu primitive của lane | Chẳng hạn `float.class` |
| `elementSize()` | Kích thước một lane | Bit |
| `length()` | Số lane trong một vector | Số phần tử |
| `vectorBitSize()` | Kích thước toàn vector | Bit |
| `vectorByteSize()` | Kích thước toàn vector | Byte |
| `vectorShape()` | Shape của species | Một giá trị `VectorShape` |

Với species `float` 256 bit:

```text
elementSize()   = 32
length()        = 8
vectorBitSize() = 256
vectorByteSize() = 32
```

Trong một vòng lặp trên `float[]`, chỉ số mảng được tính bằng **số phần tử**. Vì vậy, bước tiến thường là `length()`, không phải `vectorBitSize()` hay `vectorByteSize()`.

Cũng cần phân biệt số phần tử của mảng và số lane của vector:

```text
array.length     = tổng số phần tử của dữ liệu đầu vào
species.length() = số phần tử trong một khối vector
```

Một species có thể được dùng để xử lý nhiều mảng dài ngắn khác nhau. Mảng ngắn không tự làm species giảm độ rộng; thuật toán phải xử lý trường hợp không đủ một vector đầy.

## 4. Chọn species theo mục tiêu của thuật toán

### 4.1. Bắt đầu với `SPECIES_PREFERRED`

Với phép tính trên `float`, điểm bắt đầu phù hợp là:

```java
private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;
```

Đây là species mà nền tảng chọn làm phương án ưu tiên. Khi cùng mã nguồn chạy trên môi trường có lựa chọn ưu tiên khác, `SPECIES.length()` có thể khác, còn thuật toán dùng `length()` và `loopBound()` vẫn thích nghi được.

Không gắn ý nghĩa của `PREFERRED` với một số cụ thể như 8 lane hay 256 bit. Đây cũng không phải một hệ thống đo thử mọi thuật toán của bạn rồi chọn kết quả nhanh nhất.

Theo hợp đồng của `VectorSpecies.ofPreferred`, preferred species của các kiểu phần tử có chung shape. Ví dụ, preferred species của `float` và `double` có cùng tổng số bit, nhưng số lane khác nhau vì kích thước phần tử khác nhau. Đặc tính này hữu ích khi thuật toán cần làm việc với nhiều kiểu phần tử. Xem [API `ofPreferred`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html#ofPreferred(java.lang.Class)).

Trong cùng lần chạy, một species cụ thể mô tả một định dạng xác định; nó không đổi số lane theo từng mảng hoặc từng vòng lặp. Sự thích nghi đến từ việc chọn species cho môi trường đang chạy và viết thuật toán theo các thuộc tính của species đó.

### 4.2. Species cố định, `SPECIES_MAX` và `ofLargestShape`

| Lựa chọn | Ý nghĩa | Khi cần xem xét |
| --- | --- | --- |
| `FloatVector.SPECIES_PREFERRED` | Species ưu tiên cho `float` trên nền tảng đang chạy | Thuật toán cần tính di động và điểm bắt đầu để đo hiệu năng |
| `FloatVector.SPECIES_128`, `_256`, `_512` | Species có độ rộng cố định theo tên | Có yêu cầu độ rộng cụ thể hoặc đang so sánh các biến thể trên môi trường đích |
| `FloatVector.SPECIES_MAX` | Species gắn với `VectorShape.S_Max_BIT` | Cần hiểu shape cực đại phụ thuộc nền tảng; không coi `MAX` là tên khác của 512 bit |
| `VectorSpecies.ofLargestShape(float.class)` | Species có shape lớn nhất mà nền tảng chọn cho kiểu phần tử đó | Đánh giá một trường hợp có chủ đích, sau khi hiểu khác biệt với preferred species |
| `VectorSpecies.of(float.class, shape)` | Species cho kiểu phần tử và shape chỉ định | Cần xây dựng định dạng từ thông tin shape tường minh |

`ofLargestShape` xét kiểu phần tử cụ thể. Hợp đồng của `ofPreferred` chọn shape dùng chung được cho các kiểu phần tử. Trên nhiều nền tảng, hai lựa chọn có thể trùng nhau; không viết thuật toán dựa vào giả định chúng luôn trùng nhau.

Không nên mặc định chọn độ rộng lớn nhất với lý do xử lý nhiều lane hơn chắc chắn nhanh hơn. Khả năng tăng tốc còn phụ thuộc phép toán, cách truy cập bộ nhớ và mã máy mà runtime tạo được.

`VectorShape` cũng lưu ý rằng chọn shape cụ thể có thể làm giảm tính di động hoặc hiệu năng trên nền tảng khác. Tham khảo [API `VectorShape`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorShape.html) và [API `ofLargestShape`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html#ofLargestShape(java.lang.Class)).

## 5. Ví dụ hoàn chỉnh: xem species trên môi trường đang chạy

Chương trình `SpeciesInfoDemo.java` in thông số thay vì đoán số lane từ tên CPU:

```java
import jdk.incubator.vector.DoubleVector;
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class SpeciesInfoDemo {
    private static final VectorSpecies<Float> FLOAT_SPECIES =
            FloatVector.SPECIES_PREFERRED;

    public static void main(String[] args) {
        describe("float preferred", FLOAT_SPECIES);
        describe("double preferred", DoubleVector.SPECIES_PREFERRED);
        describe("float fixed 128", FloatVector.SPECIES_128);
        describe("float fixed 256", FloatVector.SPECIES_256);

        VectorSpecies<Float> fromFactory =
                VectorSpecies.ofPreferred(float.class);
        System.out.println("same preferred species = "
                + FLOAT_SPECIES.equals(fromFactory));
    }

    private static void describe(String label, VectorSpecies<?> species) {
        System.out.printf(
                "%s -> type=%s, shape=%s, vectorBits=%d, "
                        + "elementBits=%d, lanes=%d, vectorBytes=%d%n",
                label,
                species.elementType().getSimpleName(),
                species.vectorShape(),
                species.vectorBitSize(),
                species.elementSize(),
                species.length(),
                species.vectorByteSize());
    }
}
```

Biên dịch và chạy bằng JDK có module Vector API, chẳng hạn JDK 27:

```shell
javac --add-modules jdk.incubator.vector -encoding UTF-8 SpeciesInfoDemo.java
java --add-modules jdk.incubator.vector SpeciesInfoDemo
```

Cảnh báo về việc dùng incubator module là thông tin về trạng thái API, không phải bằng chứng rằng thuật toán tính sai.

Thông số của hai dòng preferred phụ thuộc môi trường. Nếu nền tảng chọn 256 bit, phần thông số chính sẽ là:

```text
float preferred:  vectorBits=256, elementBits=32, lanes=8, vectorBytes=32
double preferred: vectorBits=256, elementBits=64, lanes=4, vectorBytes=32
```

Đây là ví dụ có điều kiện, không phải kết quả cố định của mọi máy. Hai species cố định trong chương trình mô tả lần lượt 4 và 8 lane `float`; việc in được metadata của chúng chưa chứng minh các phép toán trên chúng sẽ được phần cứng tăng tốc.

Dùng `equals` khi cần so sánh species về mặt giá trị. Không dựa vào `==`, đồng nhất đối tượng hoặc khóa đồng bộ hóa trên các đối tượng của Vector API. Các đối tượng này có ngữ nghĩa dạng giá trị; xem phần [ghi chú hiệu năng của package Vector API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html).

## 6. Viết vòng lặp theo số lane thực tế

### 6.1. Chia mảng thành phần vector đầy và phần đuôi

Giả sử:

```text
n = số phần tử của mảng
L = species.length()
bound = species.loopBound(n)
```

Với `n` không âm, có thể suy luận:

```text
bound = floor(n / L) * L
phần vector đầy: [0, bound)
phần đuôi:       [bound, n)
```

Ví dụ với `n = 23`:

| Số lane L | `loopBound(23)` | Số khối đầy | Số phần tử đuôi |
| --- | --- | --- | --- |
| 4 | 20 | 5 | 3 |
| 8 | 16 | 2 | 7 |
| 16 | 16 | 1 | 7 |
| 32 | 0 | 0 | 23 |

Bảng là ví dụ về cách chia dữ liệu theo độ dài vector, không phải danh sách lane count được máy hiện tại hỗ trợ.

Khi `L = 8`, mảng được chia như sau:

```text
Chỉ số:  0..7        8..15       16..22
        ├───────────┼───────────┼───────────┤
        vector 1    vector 2    đuôi 7 phần tử
```

`loopBound` giúp lần tải không có mask chỉ chạm vào các phần tử hợp lệ. Nó không tự xử lý phần đuôi thay cho bạn.

### 6.2. Chương trình cộng hai mảng không hardcode độ rộng

Chương trình `VectorAdditionDemo.java`:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class VectorAdditionDemo {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    public static void main(String[] args) {
        float[] left = new float[23];
        float[] right = new float[23];

        for (int i = 0; i < left.length; i++) {
            left[i] = i + 1;
            right[i] = 100.0f;
        }

        float[] result = add(left, right);

        System.out.println("lanes = " + SPECIES.length());
        System.out.println("vector bound = "
                + SPECIES.loopBound(left.length));
        System.out.println("first = " + result[0]);
        System.out.println("last = " + result[result.length - 1]);
    }

    public static float[] add(float[] left, float[] right) {
        if (left.length != right.length) {
            throw new IllegalArgumentException("array lengths must match");
        }

        float[] result = new float[left.length];
        int lanes = SPECIES.length();
        int bound = SPECIES.loopBound(left.length);
        int i = 0;

        for (; i < bound; i += lanes) {
            FloatVector a = FloatVector.fromArray(SPECIES, left, i);
            FloatVector b = FloatVector.fromArray(SPECIES, right, i);
            a.add(b).intoArray(result, i);
        }

        for (; i < left.length; i++) {
            result[i] = left[i] + right[i];
        }

        return result;
    }
}
```

Biên dịch và chạy:

```shell
javac --add-modules jdk.incubator.vector -encoding UTF-8 VectorAdditionDemo.java
java --add-modules jdk.incubator.vector VectorAdditionDemo
```

Nếu preferred species có 8 lane, kết quả dự kiến:

```text
lanes = 8
vector bound = 16
first = 101.0
last = 123.0
```

Hai dòng về species có thể khác ở môi trường khác. Hai giá trị đầu và cuối của kết quả vẫn phải là `101.0` và `123.0` với dữ liệu trong ví dụ.

Cùng phương thức `add` xử lý được mảng rỗng và mảng ngắn hơn một vector: phần vector không chạy khi `bound = 0`, còn vòng lặp scalar xử lý các phần tử hiện có. Mã in trong `main` dùng mảng 23 phần tử nên việc đọc phần tử đầu và cuối là hợp lệ.

Một species duy nhất được dùng cho tải dữ liệu, phép cộng và bước tiến chỉ số. Khai báo species bằng `static final` cũng phù hợp với cách lưu trữ được tài liệu API khuyến nghị để hỗ trợ tối ưu hóa. Điều đó tạo cơ hội cho runtime tối ưu, không thay thế việc đo hiệu năng.

### 6.3. Đừng tự thay `loopBound` bằng mẹo bit không có điều kiện

Một công thức dễ gặp là:

```java
int bound = n & ~(lanes - 1);
```

Công thức này chỉ tương đương làm tròn xuống theo bội số lane khi `lanes` là lũy thừa của hai. Không nên biến giả định đó thành yêu cầu ẩn của mã dùng species phụ thuộc nền tảng.

Chẳng hạn, nếu xét một species giả định có 12 lane `float`, tương ứng 384 bit, bội số lớn nhất của 12 không vượt 23 là 12. Mẹo bit trên cho 20, không phải một bội số hợp lệ của 12. Đây là ví dụ số học để thấy lỗi giả định, không khẳng định máy đang chạy sử dụng vector 384 bit.

Dùng `species.loopBound(n)` thể hiện đúng ý định và không cần giả định lane count là lũy thừa của hai. Tài liệu package cũng nêu trường hợp shape phụ thuộc nền tảng có độ rộng khác các mốc thường gặp. Xem [hướng dẫn vòng lặp của Vector API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html).

## 7. Mask xử lý lane hợp lệ, không thay đổi species

Một cách khác để xử lý đuôi là dùng mask. Sau vòng lặp vector đầy ở ví dụ trên, có thể thay vòng scalar bằng đoạn sau:

```java
if (i < left.length) {
    var mask = SPECIES.indexInRange(i, left.length);
    var a = FloatVector.fromArray(SPECIES, left, i, mask);
    var b = FloatVector.fromArray(SPECIES, right, i, mask);
    a.add(b).intoArray(result, i, mask);
}
```

Đây là đoạn thay thế đặt bên trong phương thức `add`, nơi `i`, `left`, `right` và `result` đã được khai báo như phần trước.

Nếu species có 8 lane và còn 3 phần tử:

```text
lane:       0 1 2 3 4 5 6 7
mask:       T T T F F F F F
số lane:    vẫn là 8
lane hợp lệ: 3
```

Mask chọn các lane được đọc hoặc ghi. Nó không biến vector 8 lane thành một species mới có 3 lane. Các lần tải và ghi có mask tránh truy cập những phần tử nằm ngoài biên ở phần đuôi.

Cả mask và các vector phải có species tương thích. Tạo mask bằng `SPECIES.indexInRange(...)` ngay từ species đang dùng là cách giữ sự nhất quán. Tham khảo [API `VectorMask`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html).

Với phép cộng ở đây, cả cách xử lý đuôi bằng scalar và bằng mask đều rõ ràng. Việc cách nào nhanh hơn cần được đo trong bối cảnh cụ thể; dùng mask ở mọi vòng lặp không mặc nhiên tốt hơn chỉ dùng ở phần đuôi.

## 8. Giữ species nhất quán trong một phép toán

Kiểu Java chưa diễn đạt hết mọi điều kiện tương thích. Hai biến đều có kiểu `FloatVector` vẫn có thể thuộc hai species khác nhau.

| Cặp định dạng | Điều cần nhận ra |
| --- | --- |
| `float` 128 bit và `float` 256 bit | Cùng kiểu lane nhưng khác shape và số lane |
| `float` 256 bit và `double` 256 bit | Cùng tổng số bit nhưng khác kiểu phần tử và số lane |
| `float` 256 bit và `double` 512 bit | Cùng 8 lane nhưng khác kiểu phần tử và shape |
| Hai vector `float` được tải bằng cùng species | Có cùng định dạng để dùng trong phép cộng lane-wise thông thường |

Không cộng trực tiếp hai vector thuộc các species khác nhau rồi mong runtime tự mở rộng hoặc thu hẹp chúng. Nếu thuật toán cần đổi kiểu hoặc shape, phải dùng các phép chuyển đổi hoặc diễn giải lại được API quy định và hiểu rõ dữ liệu được ánh xạ thế nào.

Tương tự, `VectorMask<Float>` cho biết kiểu phần tử liên quan nhưng không có nghĩa mask của mọi shape đều dùng thay nhau được. Mask cho species 128 bit không tự trở thành mask cho species 256 bit.

Một cách tổ chức dễ duy trì là dùng cùng hằng `SPECIES` cho toàn bộ một kernel tính toán: tạo vector, tạo mask, xác định bound và tăng chỉ số. Khi thay lựa chọn species, các phần đó cùng thay đổi theo một nguồn.

## 9. Chọn species là quyết định về tính di động và hiệu năng

### 9.1. Nhiều lane hơn chưa đủ để kết luận nhanh hơn

Vector API biểu diễn các phép tính để runtime có thể biên dịch thành lệnh SIMD khi phần cứng và runtime hỗ trợ phù hợp. Một đối tượng vector rộng hơn trong mã Java không chứng minh đã có một lệnh phần cứng tương ứng được sử dụng.

Những yếu tố cần xem xét:

| Yếu tố | Ảnh hưởng đến lựa chọn |
| --- | --- |
| Hỗ trợ phần cứng và runtime | Quyết định phép toán và shape có được tăng tốc phù hợp hay không |
| Kích thước mảng | Dữ liệu ngắn có thể không đủ một khối vector đầy hoặc có chi phí điều phối lớn so với phần tính toán |
| Truy cập bộ nhớ | Việc đọc, ghi và băng thông bộ nhớ có thể chi phối thời gian |
| Loại phép toán | Một phép cộng đơn giản khác với phép cần chuyển đổi hoặc sắp xếp lại lane |
| Phần đuôi | Thay species làm thay số phần tử cần xử lý bằng scalar hoặc mask |
| Cách JIT tối ưu mã | Phụ thuộc cấu trúc kernel và thông tin species có sẵn cho compiler |

Không suy ra vector có 8 lane sẽ làm toàn bộ ứng dụng nhanh gấp 8 lần. Số lane mô tả số phần tử trong định dạng vector; hiệu năng cuối cùng còn gồm nhiều chi phí khác.

### 9.2. Cách bắt đầu thực tế

Trước hết, dùng `SPECIES_PREFERRED` và viết kernel đúng cho mọi lane count mà lựa chọn đó cung cấp. Giữ cách xử lý đuôi rõ ràng và xác nhận thuật toán không bỏ hoặc lặp phần tử.

Chỉ khi có nhu cầu hiệu năng cụ thể, hãy so sánh các species cố định hoặc lựa chọn lớn nhất trên môi trường đích. Mỗi biến thể phải thực hiện cùng công việc, bao gồm phần đuôi và các chi phí cần có trong ứng dụng thật.

Khi đo, cần cho runtime đủ cơ hội tối ưu, dùng kích thước dữ liệu đại diện và bảo đảm kết quả tính toán được sử dụng. Tách mục đích in metadata khỏi mục đích đo thời gian; các chương trình trong bài minh họa hành vi API, không phải benchmark.

Nếu truyền `VectorSpecies` qua tham số để thuận tiện cho thử nghiệm, hãy đo cả cách gọi mà ứng dụng thực sự sử dụng. Không mặc định rằng một kernel nhận species thay đổi liên tục có cùng đặc tính tối ưu với kernel dùng một hằng `static final`.

### 9.3. Hai mức di động khác nhau

**Di động về thuật toán** nghĩa là cùng mã xử lý đúng khi lane count thay đổi: bước tiến theo `length()`, giới hạn theo `loopBound()` và phần đuôi được xử lý đầy đủ.

**Di động về hiệu năng** nghĩa là mã giữ được hiệu năng phù hợp trên các môi trường đích. `SPECIES_PREFERRED` giúp bắt đầu theo hướng này, nhưng vẫn cần đo trên những máy và runtime thực tế sẽ dùng. Việc một shape cố định chạy đúng chưa chứng minh nó là lựa chọn tốt ở mọi môi trường.

## 10. Các lỗi dễ gặp khi sử dụng species

| Biểu hiện hoặc cách viết | Vấn đề | Cách sửa |
| --- | --- | --- |
| Tăng chỉ số mảng bằng `vectorBitSize()` | Nhầm số bit với số phần tử | Dùng `species.length()` |
| Dùng `vectorByteSize()` làm số phần tử của `float[]` | Nhầm byte với lane `float` | Lấy số lane trực tiếp |
| Hardcode `i += 8` với preferred species | Giả định độ rộng ưu tiên luôn có 8 lane | Tăng theo `species.length()` |
| Chỉ chạy tới `loopBound(n)` rồi kết thúc | Bỏ sót phần tử đuôi | Thêm vòng scalar hoặc phần xử lý có mask |
| Tải vector đầy tại mọi `i < n` | Lần cuối có thể đọc vượt mảng | Chỉ tải không mask trong phần vector đầy |
| Dùng mẹo bit làm tròn mà không biết điều kiện | Phụ thuộc lane count là lũy thừa của hai | Dùng `loopBound(n)` |
| Cộng hai `FloatVector` được tạo từ species khác nhau | Kiểu lớp giống nhau chưa đủ để bảo đảm tương thích | Giữ species nhất quán trong kernel |
| Truyền `Float.class` cho factory yêu cầu kiểu lane | Wrapper không phải kiểu phần tử primitive được yêu cầu | Dùng `float.class` |
| Luôn chọn 512 bit vì cho là nhanh nhất | Bỏ qua nền tảng, phép toán và chi phí thực tế | Bắt đầu với preferred rồi đo khi cần |
| Chạy thiếu incubator module | JVM hoặc compiler không thấy API cần dùng | Thêm `--add-modules jdk.incubator.vector` ở đúng giai đoạn |

Khi triển khai một phép tính mới, hãy xác định kiểu phần tử trước, chọn species, rồi để species cung cấp độ dài khối và giới hạn xử lý. Tách rõ số phần tử dữ liệu, số lane của vector và số lane đang được mask cho phép. Cách tổ chức đó giúp thuật toán vẫn đúng khi đổi nền tảng và giúp việc đánh giá hiệu năng dựa trên một kernel có vòng lặp đầy đủ.
