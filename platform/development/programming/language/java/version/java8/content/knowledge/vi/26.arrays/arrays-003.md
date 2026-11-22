# Arrays.setAll và hàm sinh theo chỉ số trong Java

`Arrays.setAll` là phương thức tĩnh trong `java.util.Arrays`, có từ **Java 8**, dùng để **gán lại tất cả phần tử của một mảng hiện có** bằng một hàm sinh giá trị theo **chỉ số**. Thay vì tự viết vòng `for` rồi tính `array[i] = ...`, ta diễn đạt quy tắc khởi tạo bằng một lambda nhận `i` và trả giá trị cần đặt ở vị trí đó.

~~~java
int[] squares = new int[5];
Arrays.setAll(squares, i -> i * i);
// squares = [0, 1, 4, 9, 16]
~~~

Trong biểu thức `i -> i * i`, `i` là **index**, bắt đầu từ 0, **không phải giá trị cũ** đang có trong mảng. Lời gọi thay đổi trực tiếp mảng `squares` và trả `void`, không tạo hoặc trả về một mảng mới.

`Arrays.setAll` và `Arrays.parallelSetAll` vẫn là API hiện hành trên Java hiện đại. Bài học này tập trung vào cơ chế hàm sinh theo chỉ số, bốn overload, kiểu primitive và tham chiếu, tính đúng, xử lý ngoại lệ, mảng nhiều chiều, cách so sánh với `Arrays.fill`/`IntStream` và giới hạn khi dùng phiên bản song song. Tất cả ví dụ chính tương thích Java 8 và có thể chạy với JDK 17+.

## 1. Hiểu đúng ý nghĩa của generator

Với mảng độ dài `n`, mục tiêu về mặt kết quả là:

~~~text
array[0]     = generator(0)
array[1]     = generator(1)
...
array[n - 1] = generator(n - 1)
~~~

**Generator** là hàm nhận một chỉ số kiểu `int`, trả về giá trị gán vào vị trí đó. Các đặc điểm:

- Chỉ số bắt đầu từ **0** và các vị trí hợp lệ kết thúc tại `array.length - 1`.
- `setAll` áp dụng generator để tạo giá trị cho **mọi vị trí** trong mảng đang có, không chỉ các phần tử đang bằng 0 hoặc null.
- Mảng là **đối tượng đầu ra được thay đổi tại chỗ** (*in-place*); phương thức trả `void`.
- `setAll` không thay đổi **độ dài** mảng. Muốn mảng kích thước khác, tạo mảng mới.
- Với mảng rỗng, không có vị trí nào cần gán, nên generator không được gọi cho phần tử nào.
- Generator cần hợp lệ, không null; callback có thể ném lỗi nếu chính logic bên trong nó ném lỗi.
- Để dễ kiểm thử và có thể đổi sang `parallelSetAll`, nên thiết kế giá trị `generator(i)` chỉ phụ thuộc vào `i` và dữ liệu đầu vào **không thay đổi** trong khi đang sinh.

Một điểm quan trọng: generator **không nhận giá trị phần tử** như hàm `map(value -> ...)`. Nếu viết:

~~~java
int[] numbers = {10, 20, 30};
Arrays.setAll(numbers, i -> i * 2);
// Kết quả: [0, 2, 4], KHÔNG PHẢI [20, 40, 60].
~~~

Đây là ví dụ minh họa độc lập về biểu thức, cần `import java.util.Arrays;` khi dùng trong lớp Java. Giá trị cũ của mảng bị ghi đè. Nếu muốn biến đổi **giá trị cũ**, phải thiết kế thao tác khác hoặc chủ động đọc giá trị cần thiết theo cách an toàn, thay vì tưởng generator tự nhận phần tử cũ.

## 2. Bốn overload của `Arrays.setAll`

Java cung cấp đúng các overload thông dụng sau:

| Kiểu mảng | Chữ ký | Functional interface nhận chỉ số |
| --- | --- | --- |
| Mảng tham chiếu `T[]` | `<T> void setAll(T[] array, IntFunction<? extends T> generator)` | `IntFunction<? extends T>` |
| `int[]` | `void setAll(int[] array, IntUnaryOperator generator)` | `IntUnaryOperator` |
| `long[]` | `void setAll(long[] array, IntToLongFunction generator)` | `IntToLongFunction` |
| `double[]` | `void setAll(double[] array, IntToDoubleFunction generator)` | `IntToDoubleFunction` |

Cả bốn có từ **Java 8** và vẫn dùng được trên các JDK mới. Không có overload `Arrays.setAll(byte[])`, `short[]`, `char[]`, `boolean[]` hoặc `float[]` trực tiếp. Với các kiểu đó, có thể dùng một vòng lặp có chỉ số hoặc `IntStream.range(0,n)` để tự gán theo nhu cầu, đồng thời chú ý ép kiểu đúng.

### 2.1. `int[]` và `IntUnaryOperator`

~~~java
int[] even = new int[5];
Arrays.setAll(even, index -> index * 2);
// [0, 2, 4, 6, 8]
~~~

Hàm nhận `int` (chỉ số) và trả `int`. `IntUnaryOperator` có phương thức trừu tượng `applyAsInt(int operand)`. Lambda `index -> index * 2` được Java tự suy luận theo kiểu tham số của overload.

### 2.2. `long[]` và `IntToLongFunction`

~~~java
long[] squares = new long[4];
Arrays.setAll(squares, index ->
    (long) (index + 1) * (index + 1)
);
// [1, 4, 9, 16]
~~~

Đầu vào của hàm **vẫn là `int`** vì chỉ số mảng của Java là `int`, còn kết quả trả là `long`. Ép kiểu `(long)` **trước khi nhân** giúp tránh phép nhân `int` tràn trước khi gán vào `long` khi chỉ số lớn.

Sai lầm thường gặp:

~~~java
// PHẢN VÍ DỤ khi index lớn: nhân bằng int rồi mới ép kiểu.
(long) (index * index)

// Đúng hơn: ép kiểu một toán hạng trước khi nhân.
(long) index * index
~~~

Đây là các biểu thức minh họa; `index` phải được khai báo trong phạm vi sử dụng. Dùng `Math.multiplyExact` hoặc kiểm tra giới hạn nếu nghiệp vụ cần báo lỗi khi kết quả vượt phạm vi `long`.

### 2.3. `double[]` và `IntToDoubleFunction`

~~~java
double[] fractions = new double[4];
Arrays.setAll(fractions, index -> index / 4.0);
// [0.0, 0.25, 0.5, 0.75]
~~~

Hàm nhận chỉ số `int` và trả `double`. Viết `index / 4.0` để thực hiện phép chia số thực. Nếu viết `index / 4` thì Java tính **chia nguyên** trước, ví dụ `1 / 4 == 0`, rồi mới chuyển 0 thành `0.0`; kết quả không còn như mong muốn.

### 2.4. `T[]` và `IntFunction<? extends T>`

~~~java
String[] labels = new String[3];
Arrays.setAll(labels, index -> "item-" + (index + 1));
// [item-1, item-2, item-3]
~~~

Với mảng tham chiếu, kết quả của generator là một đối tượng hoặc giá trị tham chiếu kiểu phù hợp với `T`. Những ví dụ hợp lệ khác:

~~~java
Integer[] ids = new Integer[3];
Arrays.setAll(ids, index -> 100 + index);

String[] optionalLabels = new String[3];
Arrays.setAll(optionalLabels, index ->
    index == 1 ? null : "A" + index
);
// [A0, null, A2]
~~~

`Integer[]` dùng overload mảng tham chiếu và có thể phát sinh boxing giá trị `int`. `String[]` cũng có thể chứa null nếu chính sách dữ liệu cho phép; khác với primitive arrays, mảng tham chiếu có thể lưu tham chiếu null. Nếu generator tạo đối tượng không tương thích với kiểu phần tử thực tế của mảng, việc gán có thể gây `ArrayStoreException`; các kiểu nên được xác định rõ ngay từ đầu.

## 3. `setAll` khác vòng `for` như thế nào?

Hai cách sau có cùng ý nghĩa về kết quả nếu generator là hàm thuần và không có tác dụng phụ:

~~~java
int[] a = new int[5];

for (int i = 0; i < a.length; i++) {
    a[i] = i * i;
}
~~~

~~~java
int[] b = new int[5];
Arrays.setAll(b, i -> i * i);
~~~

Cả hai tạo kết quả `[0,1,4,9,16]`. `setAll` có lợi khi quy tắc theo chỉ số đơn giản, có thể truyền dưới dạng lambda/method reference. Vòng `for` vẫn hoàn toàn phù hợp khi cần logic nhiều bước, xử lý lỗi chi tiết, cập nhật một đoạn mảng, hoặc yêu cầu rõ thứ tự phụ thuộc vào phần tử trước đó.

**Lựa chọn không phải “vòng for lỗi thời, lambda mới đúng”.** Cả hai đều là cách lập trình hợp lệ trên Java hiện đại. `setAll` thiên về mô tả quy tắc giá trị theo chỉ số; vòng `for` có thể dễ đọc hơn với thuật toán có trạng thái tuần tự.

### Hàm đã định nghĩa sẵn làm generator

~~~java
static int squareIndex(int i) {
    return i * i;
}

// Trong phương thức:
int[] data = new int[5];
Arrays.setAll(data, MyClass::squareIndex);
~~~

Đây là mã minh họa, `MyClass` chỉ tên lớp chứa phương thức `static`. Một method reference nhận `int` và trả `int` đáp ứng `IntUnaryOperator`. Nếu hàm được sử dụng nhiều nơi, tách thành phương thức riêng có thể giúp dễ đọc, viết unit test và tái sử dụng.

### Đọc dữ liệu không đổi từ bên ngoài

~~~java
final int step = 3;
int[] multiples = new int[4];
Arrays.setAll(multiples, i -> (i + 1) * step);
// [3, 6, 9, 12]
~~~

Lambda có thể capture biến cục bộ `final` hoặc *effectively final* (không bị gán lại sau khi khởi tạo). Với cấu hình thay đổi qua thread khác, phải thiết kế quyền sở hữu và đồng bộ; không chỉ vì dùng lambda mà mọi dữ liệu chia sẻ tự thread-safe.

## 4. Khởi tạo từ mảng nguồn: dùng chỉ số để đối chiếu dữ liệu

Một ứng dụng thường cần tính giá trị đích từ **mảng nguồn có sẵn**:

~~~java
int[] prices = {10, 20, 30};
int[] withTax = new int[prices.length];

Arrays.setAll(withTax, i -> prices[i] + 2);
// withTax = [12, 22, 32]
// prices  = [10, 20, 30]
~~~

Generator nhận `i` rồi chủ động truy cập `prices[i]`. Đây là cách minh bạch để biến đổi dữ liệu nguồn mà vẫn **giữ nguyên mảng nguồn**. Điều kiện quan trọng là `prices.length == withTax.length` (hoặc có chính sách xử lý khác) để mọi truy cập `prices[i]` hợp lệ.

Nếu generator truy cập ngoài biên, `ArrayIndexOutOfBoundsException` có thể bị ném và mảng đích có thể đã bị ghi vào một số vị trí trước đó. Vì thế cần kiểm tra độ dài hoặc quy tắc mapping trước khi bắt đầu.

**Không nhầm** với:

~~~java
Arrays.setAll(prices, i -> prices[i] + 2);
~~~

Cách này ghi đè **chính `prices`**. Với `setAll` tuần tự và phép tính chỉ đọc `prices[i]` cùng chỉ số, mã có thể cho kết quả mong muốn; tuy nhiên khi muốn bảo toàn input hoặc có phụ thuộc chéo giữa các phần tử, nên dùng một mảng đích riêng. Không thiết kế generator phụ thuộc vào trạng thái đang thay đổi của nhiều index nếu sau này có thể chuyển sang `parallelSetAll`.

## 5. `Arrays.fill` và `Arrays.setAll`: cùng giá trị hay theo chỉ số?

`Arrays.fill` đặt **một giá trị cho mọi vị trí**; `Arrays.setAll` tính **mỗi vị trí theo chỉ số**.

~~~java
int[] same = new int[4];
Arrays.fill(same, 7);
// [7, 7, 7, 7]

int[] different = new int[4];
Arrays.setAll(different, i -> i + 7);
// [7, 8, 9, 10]
~~~

Nếu generator không dùng chỉ số, hai cách có thể cho cùng giá trị:

~~~java
Arrays.setAll(different, i -> 7);
~~~

Nhưng `Arrays.fill(different, 7)` thường rõ ý hơn khi đơn giản chỉ cần một hằng. Khi mỗi phần tử phải khác nhau theo vị trí, `setAll` thể hiện ý định chính xác hơn.

### Cảnh báo về object mutable khi dùng `Arrays.fill`

~~~java
StringBuilder[] shared = new StringBuilder[2];
Arrays.fill(shared, new StringBuilder("X"));

// shared[0] và shared[1] tham chiếu CÙNG một đối tượng.
boolean sameRef = shared[0] == shared[1]; // true

StringBuilder[] distinct = new StringBuilder[2];
Arrays.setAll(distinct, i -> new StringBuilder("X"));

boolean differentRefs = distinct[0] != distinct[1]; // true
~~~

`fill` lặp cùng **reference** đến một `StringBuilder`, không tự gọi constructor nhiều lần. Với `setAll` và biểu thức `new StringBuilder(...)` trong generator, mỗi vị trí được tạo một instance riêng. Đây là khác biệt có ý nghĩa khi tạo các bộ đệm, list hoặc object mutable theo từng vị trí.

Không suy ra rằng `setAll` luôn tạo object khác nhau: nếu generator cố ý trả **cùng một instance** đã được tạo trước, các vị trí vẫn có thể chia sẻ tham chiếu. Độ độc lập đến từ **logic generator**, không phải một tính chất ma thuật của API.

## 6. Mảng rỗng, kích thước, kiểu số và trường hợp biên

### 6.1. Mảng rỗng

~~~java
int[] empty = new int[0];
Arrays.setAll(empty, i -> i * 10);
// empty.length vẫn bằng 0; không sinh phần tử nào.
~~~

Nếu một bộ đếm được tăng bên trong generator, số lượt gọi ứng với **không có phần tử** vẫn bằng 0. Dù vậy, generator truyền vào phải hợp lệ; không dùng null generator để suy đoán rằng vì mảng rỗng nên mọi kiểm tra tham số sẽ bị bỏ qua.

### 6.2. Chỉ số bắt đầu từ 0

~~~java
String[] codes = new String[3];
Arrays.setAll(codes, i -> "code-" + (i + 1));
// [code-1, code-2, code-3]
~~~

Nếu muốn nhãn một-based, tự cộng 1. Không nhầm chỉ số `i=0` là phần tử thứ nhất hay giá trị cũ tại vị trí đó.

### 6.3. Độ dài không tự tăng

~~~java
int[] existing = {4, 5, 6};
Arrays.setAll(existing, i -> 100 + i);
// existing.length == 3; [100, 101, 102]
~~~

Muốn thêm một vị trí, phải cấp phát mảng khác và quyết định cách sao chép/khởi tạo giá trị.

### 6.4. Tràn số

~~~java
int[] large = new int[3];
Arrays.setAll(large, i -> i * 1_000_000_000);
~~~

Với `i=2`, kết quả `2_000_000_000` còn nằm trong `int`; khi index đủ lớn để vượt miền `int`, phép nhân có thể tràn. Chỉ số mảng là `int` nhưng không có nghĩa phép toán tính giá trị luôn vừa trong `int`.

Nếu muốn sinh giá trị lớn, dùng `long[]` và ép kiểu đúng trước phép nhân:

~~~java
long[] largeLong = new long[4];
Arrays.setAll(largeLong, i -> (long) i * 1_000_000_000L);
// [0, 1000000000, 2000000000, 3000000000]
~~~

Hoặc dùng `Math.multiplyExact` để ném lỗi khi phép nhân vượt miền cần thiết. Việc chọn kiểu số phải theo dữ liệu thực tế; `setAll` không tự kiểm tra overflow cho biểu thức generator.

## 7. Mảng hai chiều và việc khởi tạo từng hàng

Trong Java, `int[][]` là **mảng các tham chiếu tới `int[]`**, không phải một khối ma trận buộc phải hình chữ nhật. `Arrays.setAll` trên mảng ngoài dùng overload **`T[]`** với `T = int[]`: generator nhận **chỉ số hàng** và trả một `int[]`.

~~~java
int[][] matrix = new int[2][];

Arrays.setAll(matrix, row -> {
    int[] cells = new int[3];
    Arrays.setAll(cells, col -> row * 10 + col);
    return cells;
});

// [[0, 1, 2], [10, 11, 12]]
~~~

Hai bước có ý nghĩa:

1. `Arrays.setAll(matrix, row -> ...)` tạo một hàng mới cho mỗi `row`.
2. `Arrays.setAll(cells, col -> ...)` sinh giá trị từng cột trong hàng đó.

**Không dùng `Arrays.fill(matrix, new int[3])`** nếu mỗi hàng phải độc lập: tất cả hàng sẽ trỏ tới cùng một đối tượng `int[]`. Khi một ô bị sửa, mọi hàng chia sẻ cùng array có thể nhìn thấy thay đổi.

Nếu cần hàng có số cột khác nhau (*jagged array*):

~~~java
int[][] staircase = new int[3][];
Arrays.setAll(staircase, row -> {
    int[] cells = new int[row + 1];
    Arrays.setAll(cells, col -> row + col);
    return cells;
});

// [[0], [1, 2], [2, 3, 4]]
~~~

Với mảng đa chiều, dùng `Arrays.deepToString(matrix)` để in nội dung lồng nhau. `Arrays.toString(matrix)` chỉ hiển thị tham chiếu của các mảng hàng dưới dạng chuỗi implementation, không phải ma trận dễ đọc.

## 8. Chỉ gán một phần mảng: không có overload `setAll(from,to)`

`Arrays.setAll` xử lý **toàn bộ mảng**. Nó không có overload nhận `fromIndex` và `toIndex` như một số phương thức khác của `Arrays`.

Nếu chỉ muốn gán các vị trí trong nửa khoảng `[from, to)`, sử dụng vòng `for` hoặc `IntStream.range`:

~~~java
int[] values = {7, 7, 7, 7, 7};

IntStream.range(1, 4)
    .forEach(i -> values[i] = i * 10);

// values = [7, 10, 20, 30, 7]
~~~

Đây là minh họa; cần `import java.util.stream.IntStream;`. `range(1,4)` chứa các chỉ số **1, 2, 3**, không chứa 4.

Trong trường hợp `from`/`to` do người dùng cung cấp, hãy kiểm tra:

- `0 <= from <= to <= array.length`.
- Quy tắc tính không truy cập ngoài biên mảng nguồn.
- Phần ngoài nửa khoảng phải giữ nguyên.

Khi chỉ cần điền cùng một hằng trong một đoạn mảng, `Arrays.fill(array, fromIndex, toIndex, value)` có overload riêng và thường ngắn hơn. Nếu cần hàm theo index trong đoạn, `IntStream.range` hoặc vòng `for` là cách rõ ràng.

## 9. `parallelSetAll`: cùng kết quả theo chỉ số, khác cách thực thi

Java 8 cũng giới thiệu `Arrays.parallelSetAll` với **bốn overload tương ứng**: `T[]`, `int[]`, `long[]`, `double[]`. Thay vì thực thi generator theo cách tuần tự, nó cho phép các phần tử được tính **song song**, không cam kết thứ tự gọi generator giữa các index.

~~~java
int[] result = new int[6];

Arrays.parallelSetAll(result, i -> i * i);
// [0, 1, 4, 9, 16, 25]
~~~

Vì `i -> i*i` là hàm **thuần**, các phần tử cuối cùng vẫn đúng theo index, bất kể worker nào xử lý index trước. Đầu ra ổn định không chứng minh một thứ tự thực thi ổn định.

### 9.1. Generator phải an toàn khi chạy song song

Tránh trạng thái thay đổi chung:

~~~java
// PHẢN VÍ DỤ: không an toàn và không giữ quan hệ index -> value.
int[] result = new int[5];
int[] counter = {0};

Arrays.parallelSetAll(result, i -> counter[0]++);
~~~

`counter[0]++` là thao tác đọc–tăng–ghi không nguyên tử. Nhiều thread có thể làm mất cập nhật, và ngay cả khi đổi sang `AtomicInteger` để tránh race, việc phân phối giá trị cho các index sẽ phụ thuộc thứ tự task, **không phải quy tắc theo chỉ số**. Nếu muốn `[0,1,2,3,4]`, viết `i -> i`.

Tránh generator phụ thuộc vào giá trị **đang được thay đổi ở index khác**:

~~~java
// PHẢN VÍ DỤ với parallel: index hiện tại phụ thuộc index trước.
int[] data = {1, 1, 1, 1};
Arrays.parallelSetAll(data, i ->
    i == 0 ? data[0] : data[i - 1] + 1
);
~~~

Khi task tính vị trí 3 trước vị trí 2, kết quả có thể không đúng như một thuật toán cộng dồn tuần tự. Nếu muốn prefix sum, dùng thuật toán chuyên dụng có hợp đồng thích hợp, ví dụ `Arrays.parallelPrefix` khi toán tử đáp ứng yêu cầu, hoặc một vòng lặp tuần tự rõ ràng. Không biến một phép tính có phụ thuộc chéo thành phép khởi tạo độc lập theo chỉ số rồi mong nó tự đồng bộ.

### 9.2. Không mặc định chạy song song nhanh hơn

`parallelSetAll` có overhead chia việc, lập lịch, đồng bộ hoàn tất và sử dụng nhiều core/băng thông bộ nhớ. Với mảng nhỏ hoặc generator rất nhẹ, `Arrays.setAll` hay vòng `for` thường có thể nhanh hơn. Với mảng đủ lớn và generator tính toán nặng, song song **có khả năng** hữu ích nhưng cần đo trên workload thật.

**Tiêu chí lựa chọn:** dùng `parallelSetAll` khi generator độc lập, không có side effect ngoài mảng đích và đã có số liệu benchmark cho lợi ích hiệu năng. Đừng dùng nó chỉ vì tên có “parallel”. Khi công việc gồm I/O hay cập nhật dịch vụ bên ngoài, khởi tạo song song thiếu kiểm soát có thể gây contention hoặc giới hạn tài nguyên.

### 9.3. Không chia sẻ mảng đang bị ghi như một snapshot

Dù việc `parallelSetAll` đã hoàn tất trả lại cho caller thì caller có thể tiếp tục sử dụng kết quả, các thread **khác** đồng thời đọc mảng trong lúc thao tác đang chạy có thể thấy một số vị trí đã mới, số khác vẫn cũ. Một lời gọi `setAll`/`parallelSetAll` **không phải transaction nguyên tử cho toàn mảng**.

Nếu cần công bố kết quả đã khởi tạo đầy đủ cho thread khác, một cách đơn giản là xây dựng **mảng mới**, hoàn tất thao tác, rồi công bố reference bằng cơ chế safe publication thích hợp (ví dụ trường `volatile` hoặc kết hợp lock/executor theo thiết kế). Không truyền mảng đang được khởi tạo dở cho nhiều thread.

## 10. Ngoại lệ: mảng có thể bị thay đổi một phần

Theo hợp đồng API, nếu generator ném ngoại lệ trong `Arrays.setAll`, ngoại lệ được chuyển tới caller và **mảng để lại trong trạng thái không xác định**. Không có cơ chế rollback mặc định.

~~~java
int[] output = {9, 9, 9, 9};

try {
    Arrays.setAll(output, i -> {
        if (i == 2) {
            throw new IllegalArgumentException("bad index");
        }
        return i;
    });
} catch (IllegalArgumentException ex) {
    System.out.println("failure=" + ex.getClass().getSimpleName());
}

// Không giả định output vẫn là [9, 9, 9, 9],
// cũng không dùng một trạng thái trung gian cụ thể làm contract.
~~~

Đoạn trên là minh họa; cần import `java.util.Arrays` nếu dùng riêng. `parallelSetAll` cũng có thể ném một ngoại lệ không kiểm tra nếu generator thất bại và để mảng ở trạng thái không xác định; ngoại lệ được chuyển đến caller nhưng **đừng dựa vào thứ tự phần tử nào đã được cập nhật**.

Nếu cần bảo đảm “hoặc toàn bộ kết quả mới, hoặc giữ nguyên kết quả cũ”, hãy dùng **mảng tạm**:

~~~java
int[] next = new int[output.length];
Arrays.setAll(next, i -> generateValue(i));

// Chỉ sau khi thành công, thay đổi tham chiếu
// tại nơi quản lý state (với đồng bộ phù hợp nếu đa luồng).
output = next;
~~~

Đoạn trên là **mã minh họa**, `generateValue` là phương thức do ứng dụng định nghĩa, `output` là biến có thể gán. Với biến reference chia sẻ giữa thread, chỉ gán reference không tự làm mọi truy cập an toàn; hãy dùng cơ chế công bố/đồng bộ phù hợp.

### Một số ngoại lệ khác

- `NullPointerException`: generator null; mảng null cũng không thể sử dụng hợp lệ.
- `ArrayIndexOutOfBoundsException`: có thể do generator truy cập một mảng nguồn khác bằng chỉ số không phù hợp.
- `ArithmeticException`: có thể xảy ra trong generator, ví dụ chia nguyên cho 0 hoặc `Math.multiplyExact` phát hiện tràn.
- `ArrayStoreException`: mảng tham chiếu thực tế không chấp nhận object mà generator trả.
- Ngoại lệ nghiệp vụ từ chính generator: phải được xử lý bởi caller hoặc triển khai quy tắc trước khi gọi.

**Đừng dùng `setAll` trong trạng thái cần rollback nhưng không có chiến lược thay thế mảng tạm.** Với dữ liệu quan trọng, tính nhất quán của toàn bộ mảng có thể quan trọng hơn cú pháp gọn.

## 11. Ví dụ Java đầy đủ: bốn overload, mảng 2D, đoạn chỉ số và parallel

Lưu toàn bộ mã sau vào **`ArraysSetAllDemo.java`**. Mã chỉ sử dụng API có từ Java 8; biên dịch và chạy với JDK 17+.

~~~java
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

public class ArraysSetAllDemo {

    public static void main(String[] args) {
        int[] even = new int[5];
        Arrays.setAll(even, i -> i * 2);
        System.out.println("even=" + Arrays.toString(even));

        long[] longSquares = new long[4];
        Arrays.setAll(longSquares, i ->
                (long) (i + 1) * (i + 1));
        System.out.println(
                "longSquares=" + Arrays.toString(longSquares));

        double[] quarters = new double[4];
        Arrays.setAll(quarters, i -> i / 4.0);
        System.out.println(
                "quarters=" + Arrays.toString(quarters));

        String[] labels = new String[3];
        Arrays.setAll(labels, i -> "item-" + (i + 1));
        System.out.println("labels=" + Arrays.toString(labels));

        String[] nullable = new String[3];
        Arrays.setAll(nullable, i -> i == 1 ? null : "A" + i);
        System.out.println(
                "nullable=" + Arrays.toString(nullable));

        int[] source = {10, 20, 30};
        int[] withTax = new int[source.length];
        Arrays.setAll(withTax, i -> source[i] + 2);
        System.out.println(
                "withTax=" + Arrays.toString(withTax));
        System.out.println(
                "source=" + Arrays.toString(source));

        int[][] matrix = new int[2][];
        Arrays.setAll(matrix, row -> {
            int[] cells = new int[3];
            Arrays.setAll(cells, col -> row * 10 + col);
            return cells;
        });
        System.out.println(
                "matrix=" + Arrays.deepToString(matrix));

        int[] parallelSquares = new int[6];
        Arrays.parallelSetAll(parallelSquares, i -> i * i);
        System.out.println("parallelSquares="
                + Arrays.toString(parallelSquares));

        int[] subset = {7, 7, 7, 7, 7};
        IntStream.range(1, 4)
                .forEach(i -> subset[i] = i * 10);
        System.out.println(
                "subset=" + Arrays.toString(subset));

        StringBuilder[] shared = new StringBuilder[2];
        Arrays.fill(shared, new StringBuilder("X"));

        StringBuilder[] distinct = new StringBuilder[2];
        Arrays.setAll(distinct, i -> new StringBuilder("X"));

        System.out.println("fillSharesObject="
                + (shared[0] == shared[1]));
        System.out.println("setAllIndependent="
                + (distinct[0] != distinct[1]));

        AtomicInteger calls = new AtomicInteger();
        int[] empty = new int[0];
        Arrays.setAll(empty, i -> {
            calls.incrementAndGet();
            return i;
        });
        System.out.println("emptyLength=" + empty.length
                + ", generatorCalls=" + calls.get());

        int[] potentiallyPartial = {9, 9, 9, 9};
        try {
            Arrays.setAll(potentiallyPartial, i -> {
                if (i == 2) {
                    throw new IllegalArgumentException("bad index");
                }
                return i;
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("failure="
                    + ex.getClass().getSimpleName());
        }
        // Không kiểm tra trạng thái trung gian của mảng lỗi:
        // API không cam kết các vị trí nào đã cập nhật.
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ArraysSetAllDemo.java
java ArraysSetAllDemo
~~~

**Đầu ra kỳ vọng xác định** (không có dòng thể hiện trạng thái mảng sau ngoại lệ):

~~~text
even=[0, 2, 4, 6, 8]
longSquares=[1, 4, 9, 16]
quarters=[0.0, 0.25, 0.5, 0.75]
labels=[item-1, item-2, item-3]
nullable=[A0, null, A2]
withTax=[12, 22, 32]
source=[10, 20, 30]
matrix=[[0, 1, 2], [10, 11, 12]]
parallelSquares=[0, 1, 4, 9, 16, 25]
subset=[7, 10, 20, 30, 7]
fillSharesObject=true
setAllIndependent=true
emptyLength=0, generatorCalls=0
failure=IllegalArgumentException
~~~

Vì sao kết quả ổn định?

1. Các lambda tạo `even`, `longSquares`, `quarters`, `labels` và `nullable` chỉ phụ thuộc index; không có trạng thái mutable ngoài.
2. `withTax` đọc `source` **không bị thay đổi**; mảng đích đủ dài nên không truy cập ngoài biên.
3. `matrix` tạo một mảng con riêng cho mỗi hàng; `Arrays.deepToString` hiển thị toàn bộ nội dung lồng nhau.
4. `parallelSquares` có thể được tính theo thứ tự khác nhau giữa các thread, nhưng mỗi vị trí `i` cuối cùng nhận `i*i`; không cần phụ thuộc lịch thực thi.
5. `subset` chỉ gán ở index 1, 2, 3 nhờ `IntStream.range(1,4)`.
6. `Arrays.fill` trên mảng object dùng chung reference; `Arrays.setAll` với `new StringBuilder` tạo các object riêng.
7. Mảng rỗng không có phần tử để gọi generator; chương trình đếm được 0 lượt.
8. Lỗi `IllegalArgumentException` là chủ động từ generator; chương trình chỉ xác nhận **kiểu ngoại lệ**, không tuyên bố mảng còn nguyên hay phần nào đã bị ghi.

## 12. So sánh với `IntStream.range`, `Stream.generate`, `Arrays.fill`

| Mục tiêu | API phù hợp | Điểm khác biệt |
| --- | --- | --- |
| Gán một giá trị giống nhau cho toàn mảng | `Arrays.fill(array, value)` | Không phụ thuộc index; với object mutable, các phần tử chia sẻ cùng reference. |
| Gán giá trị theo chỉ số vào mảng đã có | `Arrays.setAll(array, i -> ...)` | Mutate toàn bộ mảng, trả `void`. |
| Gán giá trị theo chỉ số vào mảng đã có, song song | `Arrays.parallelSetAll(array, i -> ...)` | Generator phải độc lập, an toàn với parallel; đo hiệu năng trước. |
| Tạo mảng `int[]` mới từ một dãy index | `IntStream.range(0,n).map(i -> ...).toArray()` | Trả **mảng mới**, không cần cấp phát mảng đích thủ công. |
| Gán chỉ một đoạn theo index | `IntStream.range(from,to).forEach(i -> array[i]=...)` | Chủ động chỉ định nửa khoảng; phải tự kiểm tra biên và side effects. |
| Tạo dữ liệu không dựa vào chỉ số | `Stream.generate(supplier)` cùng giới hạn | Supplier không được truyền index; lưu ý stream vô hạn nếu không giới hạn. |
| Logic tuần tự có phụ thuộc phần tử trước | Vòng `for` hoặc thuật toán prefix phù hợp | Quan hệ phụ thuộc thứ tự nên viết rõ thay vì giả làm index-independent generator. |

Ví dụ tạo mảng mới:

~~~java
int[] generated = IntStream.range(0, 5)
        .map(i -> i * i)
        .toArray();
// [0, 1, 4, 9, 16]
~~~

Cùng ý định sinh giá trị theo index nhưng **khác quyền sở hữu kết quả**: `IntStream.range(...).toArray()` cấp phát mảng mới; `Arrays.setAll` dùng mảng đã được cấp phát.

Không dùng `Stream.generate(() -> ...)` rồi mặc định supplier biết đang ở vị trí thứ mấy; `Supplier` thông thường **không nhận chỉ số**. Để sinh ID dựa theo index, `IntStream.range` hoặc `Arrays.setAll` trực tiếp hơn.

## 13. Những lỗi phổ biến

### Lỗi 1 — Tưởng tham số lambda là giá trị cũ

~~~java
int[] a = {10, 20, 30};
Arrays.setAll(a, value -> value * 2);
// Thực tế [0, 2, 4], vì value là 0,1,2.
~~~

Đặt tên biến `index` hoặc `i` cho rõ. Nếu muốn biến đổi dữ liệu cũ, cân nhắc mảng đích riêng và đọc từ nguồn theo chỉ số.

### Lỗi 2 — Muốn nhận mảng mới từ `setAll`

~~~java
// Sai, không biên dịch:
// int[] copy = Arrays.setAll(new int[5], i -> i + 1);
~~~

`setAll` trả `void`. Cách đúng: giữ reference của mảng đã cấp phát rồi gọi hàm, hoặc dùng `IntStream.range(...).toArray()`.

### Lỗi 3 — Dùng sai kiểu generator cho overload

`Arrays.setAll(int[], ...)` cần `IntUnaryOperator`, `long[]` cần `IntToLongFunction` và `double[]` cần `IntToDoubleFunction`. Đầu vào của mọi generator đều là index kiểu `int`. Các mảng `boolean[]`, `float[]`, `byte[]`... không có overload setAll trực tiếp.

### Lỗi 4 — Nhầm `i / 4` với `i / 4.0`

Với `double[]`, phép chia nguyên được thực hiện trước khi chuyển sang double nếu cả hai toán hạng đều nguyên. Viết số chia kiểu double khi muốn kết quả thực.

### Lỗi 5 — Tràn trước khi chuyển sang `long`

`(long)(i*i)` có thể giữ kết quả đã tràn của phép nhân int. Viết `(long)i*i` hoặc dùng kiểm tra giới hạn.

### Lỗi 6 — Tạo cùng object mutable cho mọi vị trí

`Arrays.fill(objects, new MutableObject())` dùng **một instance**. Nếu cần mỗi vị trí một object, dùng `Arrays.setAll(objects, i -> new MutableObject())`; biết rằng chính generator quyết định có tạo instance mới hay không.

### Lỗi 7 — Generator có state hoặc side effect

Generator dùng biến ngoài tăng dần, ghi log theo index hoặc cập nhật một map chung có thể không tương thích `parallelSetAll`. Kể cả khi chỉ dùng `setAll`, logic phụ thuộc side effect có thể khó bảo trì. Ưu tiên hàm thuần để một index luôn ra cùng kết quả.

### Lỗi 8 — Phụ thuộc giá trị của một index đang được ghi ở index khác

`parallelSetAll` không bảo đảm index trước hoàn tất trước index sau. Nếu cần prefix sum hoặc truy hồi, dùng thuật toán được thiết kế cho phụ thuộc dữ liệu; không chuyển tùy tiện sang parallel.

### Lỗi 9 — Đoán mảng còn nguyên nếu callback ném lỗi

API nói mảng có trạng thái **không xác định** sau lỗi generator. Nếu cần atomic replacement theo nghiệp vụ, khởi tạo mảng tạm rồi chỉ công bố khi thành công.

### Lỗi 10 — Tưởng setAll tự cấp phát hoặc tăng kích thước

Mảng phải tồn tại và có kích thước hợp lệ trước lời gọi. `setAll` ghi vào tất cả phần tử hiện có, không tự thêm phần tử.

### Lỗi 11 — Quên lỗi null hoặc ArrayStoreException

Generator không được null. Mảng tham chiếu có thể chứa phần tử null nhưng kiểu runtime vẫn phải tương thích với giá trị được gán. Nếu generator cố trả object sai kiểu với component type thật, `ArrayStoreException` có thể xảy ra.

### Lỗi 12 — Dùng parallel chỉ vì tên API

Với mảng nhỏ hoặc công thức rẻ, scheduling overhead có thể khiến `parallelSetAll` chậm hơn `setAll`. Chỉ dùng song song sau khi xác nhận correctness và có benchmark theo dữ liệu thực tế.

## 14. Hiệu năng và nguyên tắc kiểm thử

Với mảng có `n` phần tử, `Arrays.setAll` phải tính/ghi mỗi vị trí, nên thời gian cơ bản là khoảng **O(n)** cộng chi phí riêng của generator. API không tăng kích thước mảng và không cần lưu một danh sách trung gian của tất cả các giá trị để trả về, nhưng generator có thể cấp phát object ở mỗi phần tử.

`Arrays.parallelSetAll` cũng cần xử lý tổng cộng `n` vị trí, có thể chia công việc cho nhiều worker. Thời gian thực tế chịu ảnh hưởng của:

- Số phần tử, chi phí generator cho một index và khả năng chia việc.
- Bộ nhớ/cache, số core, tình trạng CPU/JVM và tải song song khác.
- Việc generator có tạo nhiều object gây GC hay không.
- Mức độ tranh chấp do shared mutable state (nếu thiết kế sai).
- Thời gian publish/đọc kết quả sau khởi tạo.

**Không tuyên bố speedup mặc định.** Đối với tối ưu nghiêm túc, dùng JMH để benchmark tuần tự/parallel, thử nhiều kích thước n và kiểm tra output tương đương trước khi đánh giá tốc độ.

Bộ test nên gồm:

1. Mảng rỗng và mảng một phần tử.
2. Mảng đủ lớn để phát hiện tràn số hoặc sai index.
3. Sinh object mutable: mỗi index cần instance riêng hay có chủ đích chia sẻ?
4. Dữ liệu nguồn và đích khác nhau: nguồn có bị sửa không?
5. Mảng nhiều chiều: hàng có độc lập, kích thước cột đúng?
6. Mảng đích chỉ muốn sửa một đoạn: ngoài đoạn có giữ nguyên?
7. Generator ném ngoại lệ: caller không dựa vào mảng đích sau lỗi.
8. Cả `setAll` và `parallelSetAll` với generator thuần: nội dung sau khi hoàn tất phải bằng nhau.
9. Khi dùng đa luồng: không có mutation đồng thời chưa đồng bộ lên cùng dữ liệu nguồn/đích.
10. Tài nguyên: đo memory, CPU và GC nếu generator cấp phát nhiều object.

## 15. Checklist áp dụng trong dự án

1. **Mảng đã có chưa?** `Arrays.setAll` cần mảng đầu ra đã cấp phát; nếu cần mảng mới, cân nhắc `IntStream.range(...).toArray()`.
2. **Generator nhận gì?** Đó là **index kiểu int**, từ 0 đến length-1, không phải phần tử cũ.
3. **Overload nào?** `T[]`, `int[]`, `long[]` hay `double[]`.
4. **Kiểu kết quả đúng chưa?** Tránh chia nguyên ngoài ý muốn và tràn trước khi nâng sang long.
5. **Mỗi phần tử có độc lập?** Với object mutable, dùng `new` trong generator nếu cần mỗi vị trí một instance riêng.
6. **Giữ nguyên nguồn?** Nếu cần, tạo mảng đích mới rồi đọc mảng nguồn bất biến theo index.
7. **Chỉ một đoạn mảng?** Dùng vòng `for` hoặc `IntStream.range(from,to)`; `setAll` không có overload subrange.
8. **Có khả năng ném lỗi?** Mảng có thể bị thay đổi một phần; nếu cần “tất cả hoặc không”, dùng mảng tạm.
9. **Muốn chạy song song?** Chỉ khi generator thuần, không phụ thuộc index khác, và đã đo tính đúng/hiệu năng.
10. **Kết quả đã sẵn sàng cho thread khác chưa?** Hoàn tất khởi tạo và công bố reference bằng cơ chế phù hợp khi chia sẻ giữa thread.

**Ghi nhớ:** `Arrays.setAll(array, i -> value)` là cú pháp ngắn gọn để **sinh giá trị theo chỉ số và ghi vào mảng hiện có**. `i` là index, không phải value. API vẫn hiện hành; `parallelSetAll` chỉ nên dùng với generator độc lập và sau khi kiểm chứng lợi ích thực tế. Khi yêu cầu giữ nguyên mảng cũ hoặc cần rollback khi lỗi, hãy tạo mảng mới trước khi đưa vào sử dụng.

## Tài liệu chính thức

- [Oracle Java SE 26 — Arrays.setAll và Arrays.parallelSetAll, bốn overload, ngoại lệ khi generator thất bại](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html)
- [Oracle Java SE 26 — IntUnaryOperator, IntToLongFunction, IntToDoubleFunction và IntFunction](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/package-summary.html)
- [Oracle Java SE 26 — IntStream.range và toArray](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html)
- [Oracle Java SE 26 — Arrays.fill, Arrays.deepToString và Arrays.parallelPrefix](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html)
