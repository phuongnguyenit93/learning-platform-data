# Arrays.parallelPrefix và phép tích lũy kết hợp trong Java

`java.util.Arrays.parallelPrefix(...)` là API có từ **Java 8 và vẫn còn áp dụng trong Java hiện hành**. Nó biến một mảng thành dãy **kết quả tích lũy theo tiền tố** (*inclusive prefix scan*) bằng một phép toán hai ngôi, có thể dùng xử lý song song khi phù hợp. Những phần tử của mảng **được thay đổi ngay tại chỗ**, thay vì trả một mảng mới.

Ví dụ với mảng ban đầu:

~~~text
[2, 1, 0, 3]
~~~

và phép cộng, kết quả là:

~~~text
[2, 3, 3, 6]
~~~

Vì phần tử thứ `i` của kết quả đại diện cho phép cộng những phần tử **từ đầu mảng đến chính `i`**. Để thao tác tích lũy được chia và gộp trên nhiều thread mà vẫn có ý nghĩa xác định, phép toán cần **có tính kết hợp (associative) và không có side effect**. Điều đó **không đồng nghĩa** với tính giao hoán, không làm phép tính tràn số nguyên trở nên an toàn, và cũng không khắc phục sai số của `double`.

Bài học giải thích cơ chế, toàn mảng so với một khoảng, các toán tử phù hợp, việc phân nhóm tính toán khi song song, dữ liệu số và object, giới hạn API, kiểm thử và thiết kế hiệu năng.

## 1. Prefix scan là gì?

Cho mảng ban đầu gồm `a[0], a[1], ..., a[n-1]`, với phép toán hai ngôi `op(left, right)` có tính kết hợp.

Sau khi gọi:

~~~java
Arrays.parallelPrefix(a, op);
~~~

kết quả ở mỗi vị trí mang ý nghĩa **inclusive prefix**:

~~~text
a[0]  = phần tử gốc thứ 0
a[1]  = op(gốc[0], gốc[1])
a[2]  = op(op(gốc[0], gốc[1]), gốc[2])
...
a[i]  = tích lũy các phần tử gốc từ 0 đến i
~~~

Đây là **mô tả ý nghĩa toán học**, không mô tả thứ tự thực tế các lời gọi `op` trong thuật toán song song. Nếu phép toán kết hợp, các cách đặt ngoặc khác nhau trên cùng thứ tự phần tử cho cùng kết quả theo phép toán đó.

### 1.1. Ví dụ cộng dồn từng bước

~~~text
Mảng gốc:      [2, 1, 0, 3]
Tiền tố 0:      2              = 2
Tiền tố 1:      2 + 1          = 3
Tiền tố 2:      2 + 1 + 0      = 3
Tiền tố 3:      2 + 1 + 0 + 3  = 6
Mảng kết quả:  [2, 3, 3, 6]
~~~

Java:

~~~java
int[] amounts = {2, 1, 0, 3};
Arrays.parallelPrefix(amounts, Integer::sum);
System.out.println(Arrays.toString(amounts));
// [2, 3, 3, 6]
~~~

Đây là **mảnh code chạy trong một phương thức** với `import java.util.Arrays;`. `Integer::sum` có chữ ký phù hợp với `IntBinaryOperator`. `parallelPrefix` trả `void` và sửa chính mảng `amounts`.

### 1.2. Inclusive khác exclusive scan

`Arrays.parallelPrefix` tạo **inclusive scan**: phần tử đầu của kết quả là **phần tử đầu của nguồn**, không tự chèn giá trị khởi tạo.

Ví dụ phép cộng:

~~~text
Dữ liệu gốc:       [2, 1, 0, 3]
Inclusive prefix:  [2, 3, 3, 6]
Exclusive prefix:  [0, 2, 3, 3]  (nếu chọn identity = 0)
~~~

**Exclusive prefix** ở ví dụ này là tổng các phần tử **đứng trước** vị trí hiện tại. `Arrays.parallelPrefix` **không có tham số identity** và **không tự tạo exclusive result**. Nếu ứng dụng cần exclusive prefix, phải xây dựng kết quả theo quy tắc riêng, ví dụ điền phần tử đầu bằng identity và chuyển các prefix inclusive về sau; không thể tự coi kết quả API là exclusive.

Một phép toán như `Math.max` thường không có một giá trị identity hiển nhiên phù hợp mọi miền dữ liệu; inclusive scan tiện ở chỗ bắt đầu trực tiếp từ phần tử đầu.

## 2. Các overload còn được hỗ trợ

`Arrays.parallelPrefix` có các dạng chính:

| Loại mảng | Toàn mảng | Chỉ một khoảng |
|---|---|---|
| `int[]` | `parallelPrefix(int[], IntBinaryOperator)` | Thêm `fromIndex, toIndex` trước operator |
| `long[]` | `parallelPrefix(long[], LongBinaryOperator)` | Thêm `fromIndex, toIndex` trước operator |
| `double[]` | `parallelPrefix(double[], DoubleBinaryOperator)` | Thêm `fromIndex, toIndex` trước operator |
| `T[]` (mảng object) | `parallelPrefix(T[], BinaryOperator<T>)` | Thêm `fromIndex, toIndex` trước operator |

Những overload này có từ Java 8. Java hiện hành vẫn dùng chúng trực tiếp.

Cú pháp sử dụng:

~~~java
Arrays.parallelPrefix(ints, Integer::sum);
Arrays.parallelPrefix(ints, fromIndex, toIndex, Integer::sum);

Arrays.parallelPrefix(longs, Long::sum);
Arrays.parallelPrefix(longs, fromIndex, toIndex, Long::sum);

Arrays.parallelPrefix(doubles, Double::sum);
Arrays.parallelPrefix(doubles, fromIndex, toIndex, Double::sum);

Arrays.parallelPrefix(objects, binaryOperator);
Arrays.parallelPrefix(objects, fromIndex, toIndex, binaryOperator);
~~~

Đây là **mẫu cú pháp**, giả sử mảng và các biến đã khai báo đúng kiểu. Những functional interface tương ứng nằm trong `java.util.function`: `IntBinaryOperator`, `LongBinaryOperator`, `DoubleBinaryOperator`, `BinaryOperator<T>`.

**Không có overload trực tiếp cho `byte[]`, `short[]`, `char[]`, `float[]` hoặc `boolean[]`.** Nếu nguồn thuộc các kiểu ấy, lựa chọn phù hợp là chuyển dữ liệu sang mảng loại được hỗ trợ khi quy tắc nghiệp vụ cho phép, hoặc tự xây một thuật toán tính prefix trên kiểu dữ liệu gốc. Không cast `float[]` thành `double[]`: đó là hai loại mảng không tương thích.

Các phép biến đổi không được API cho phép vẫn là lỗi kiểu khi biên dịch; `parallelPrefix` không tự động boxing mọi mảng nguyên thủy thành `T[]`.

## 3. Sắp tích lũy trong một khoảng [fromIndex, toIndex)

Overload có cận chỉ xử lý một đoạn **nửa mở**:

~~~java
Arrays.parallelPrefix(array, fromIndex, toIndex, op);
~~~

Quy tắc:

- `fromIndex` **bao gồm**.
- `toIndex` **loại trừ**.
- Phần tử đầu của **đoạn** trở thành điểm bắt đầu tích lũy: `array[fromIndex]`.
- Kết quả tại `fromIndex + 1` được tính từ hai phần tử gốc tại `fromIndex` và `fromIndex + 1`.
- Các vị trí **nằm ngoài đoạn** giữ nguyên.
- **Không cộng thêm giá trị ở vị trí `fromIndex - 1`** vào đoạn mới. Đó sẽ là một quy tắc tích lũy khác, không phải hợp đồng của overload này.

Ví dụ:

~~~java
int[] values = {100, 2, 1, 3, 200};
Arrays.parallelPrefix(values, 1, 4, Integer::sum);

System.out.println(Arrays.toString(values));
// [100, 2, 3, 6, 200]
~~~

Phân tích chỉ số:

~~~text
Index:    0     1  2  3    4
Before: 100  |  2  1  3 | 200
              +----------------+
              Phạm vi [1,4)
Prefix:       [2, 3, 6]
After:  100  |  2  3  6 | 200
~~~

Mảng ở index 0 và 4 không đổi. `100` **không tham gia tính tổng** của đoạn `[1,4)`. Ngay cả khi mảng ban đầu đã chứa prefix của một đoạn trước đó, lời gọi mới không tự nối hai đoạn vào chung một prefix toàn mảng.

### 3.1. Những biên hợp lệ và không hợp lệ

Cho `int[] a` có độ dài `n`:

| Cận | Nghĩa | Tác dụng |
|---|---|---|
| `[0, n)` | Toàn mảng | Tích lũy toàn bộ |
| `[2, 5)` khi `n >= 5` | Vị trí 2, 3, 4 | Chỉ đổi đoạn này |
| `[k, k)` khi `0 <= k <= n` | Đoạn rỗng | Không đổi mảng |
| `[k, k+1)` khi cận hợp lệ | Một phần tử | Phần tử đó giữ nguyên |
| `[n, n)` | Đoạn rỗng ở cuối | Hợp lệ, không đổi |
| `fromIndex > toIndex` | Cận đảo chiều | `IllegalArgumentException` |
| `fromIndex < 0` | Chỉ số âm | `ArrayIndexOutOfBoundsException` |
| `toIndex > n` | Cận cuối vượt mảng | `ArrayIndexOutOfBoundsException` |

Nếu muốn xử lý **toàn bộ** mảng có độ dài `n`, cận phải là `[0,n)` chứ không phải `[0,n-1)`. Trong dữ liệu lập trình, n là một chiều dài, còn n-1 mới là index của phần tử cuối.

Với đầu vào cận đến từ người dùng, kiểm tra `0 <= from <= to <= array.length` **trước** khi gọi. Nếu tính cận cuối bằng `from + count`, tránh tràn kiểu `int`: có thể xác minh `from >= 0`, `count >= 0` và `count <= array.length - from` (sau khi kiểm `from <= array.length`) rồi mới cộng.

### 3.2. Hai lần gọi trên hai đoạn không tự tương đương toàn mảng

Ví dụ:

~~~java
int[] separate = {1, 2, 3, 4};
Arrays.parallelPrefix(separate, 0, 2, Integer::sum);
Arrays.parallelPrefix(separate, 2, 4, Integer::sum);
// [1, 3, 3, 7], không phải [1, 3, 6, 10]
~~~

Đoạn này chạy trong một phương thức. Mỗi lần gọi bắt đầu prefix từ đầu đoạn của **chính lần gọi đó**; phép tính thứ hai không dùng tổng của đoạn thứ nhất.

Nếu cần prefix toàn mảng, chỉ gọi overload toàn mảng một lần hoặc thiết kế thuật toán ghép prefix các đoạn đúng về mặt toán học. Không chỉ chia mảng và cho rằng việc gọi độc lập nhiều lần sẽ tự mang trạng thái qua biên.

## 4. “Phép tích lũy kết hợp” là gì?

Hai cách đặt ngoặc đối với một phép toán `op` được gọi là tương đương nếu:

~~~text
op(op(a, b), c) = op(a, op(b, c))
~~~

với mọi phần tử hợp lệ của miền đang xử lý. Đây là **tính kết hợp** (*associativity*).

Tính kết hợp cho phép thuật toán song song **chia mảng thành các nhóm**, tính kết quả tạm và ghép nhóm theo cách khác nhau mà vẫn giữ được cùng ý nghĩa của các tiền tố.

Ví dụ phép cộng số học:

~~~text
(2 + 1) + 3 = 2 + (1 + 3) = 6
~~~

Ví dụ `max`:

~~~text
max(max(3, 1), 4) = max(3, max(1, 4)) = 4
~~~

`Arrays.parallelPrefix` không hứa gọi operator theo cùng thứ tự thời gian và cùng cách đặt ngoặc như một vòng lặp. Do đó, **bạn không thể suy luận số lần/đúng thứ tự callback** chỉ từ vị trí của mỗi phần tử đầu ra.

### 4.1. Kết hợp KHÔNG đồng nghĩa giao hoán

**Giao hoán** có nghĩa đổi vị trí hai toán hạng mà kết quả không đổi: `op(a,b) == op(b,a)`.

`String::concat` là ví dụ **kết hợp nhưng không giao hoán**:

~~~text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
"A" + "B" = "AB" nhưng "B" + "A" = "BA"
~~~

Java:

~~~java
String[] steps = {"A", "B", "C"};
Arrays.parallelPrefix(steps, String::concat);

// [A, AB, ABC]
~~~

Mảnh code trên giả định import `java.util.Arrays`. Prefix luôn mang thứ tự phần tử của nguồn: `"A"`, sau đó `"AB"`, rồi `"ABC"`. API **không yêu cầu toán tử giao hoán**, và không có quyền tự đổi thứ tự phần tử thành `"BA"` khi ghép prefix. Điều cần có là tính kết hợp và không side effect.

### 4.2. Những phép toán phù hợp và không phù hợp

| Toán tử | Có tính kết hợp? | Lưu ý |
|---|---|---|
| Cộng `int`/`long` theo quy tắc overflow của Java | Có theo phép cộng modulo kiểu nguyên | Vẫn có thể tràn, sai tổng toán học ngoài miền |
| Nhân `int`/`long` theo quy tắc overflow | Có theo modulo kiểu nguyên | Dễ tràn, không dùng nếu cần kết quả nguyên chính xác |
| `Math.max` / `Math.min` trên `int`/`long` | Có | Tính min/max chạy dọc theo prefix |
| Bitwise OR/AND/XOR trên số nguyên | Có | Theo dõi cờ, hợp nhất mask tiền tố |
| Nối chuỗi bất biến `String::concat` | Có | Giữ thứ tự nhưng có thể tạo nhiều chuỗi trung gian |
| `BigInteger::add` | Có | Tổng nguyên tùy ý chính xác; dùng mảng object |
| Trừ hoặc chia | Không | Kết quả phụ thuộc cách nhóm |
| Phép cộng `double` | **Không kết hợp chặt chẽ** do làm tròn | Kết quả parallel có thể lệch với tuần tự |
| Toán tử thay đổi shared state khi tính | Không đáp ứng yêu cầu không side effect | Có thể race và cho kết quả khó kiểm soát |

Phân biệt **tính kết hợp của toán tử dưới quy tắc kiểu Java** với **giá trị đúng về mặt nghiệp vụ**. Dù cộng nguyên với overflow vẫn kết hợp theo modulo, kết quả có thể là số âm không hợp lý đối với số lượng hàng hóa. Một thuật toán chạy nhất quán không có nghĩa nó là đúng trong miền dữ liệu thực tế.

### 4.3. Tại sao phép trừ không dùng làm prefix song song?

Giả sử:

~~~text
a = 10, b = 3, c = 2

(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Hai kết quả khác nhau. Nếu cung cấp `(a,b) -> a-b` cho `parallelPrefix`, kết quả **không có hợp đồng tương đương một vòng lặp tích lũy tuần tự** vì operator không kết hợp. Không nên thử vài mảng nhỏ thấy “đúng” rồi suy ra code an toàn khi dữ liệu lớn và thư viện dùng nhiều nhóm song song.

**Phép toán chỉ “trông có vẻ kết hợp” trên dữ liệu nhỏ không đủ.** Phải chứng minh nó kết hợp trên toàn miền đầu vào và điều kiện số học thực tế, hoặc chọn chiến lược tuần tự có thứ tự xác định nếu bài toán thực sự cần phép tính không kết hợp.

## 5. Các phép tích lũy điển hình

### 5.1. Running sum

~~~java
int[] sales = {2, 1, 0, 3};
Arrays.parallelPrefix(sales, Integer::sum);
// [2, 3, 3, 6]
~~~

Ý nghĩa: mỗi vị trí là **tổng tất cả số lượng từ đầu mảng tới vị trí đó**. Hữu ích trong báo cáo tổng lũy kế, biến đổi từ dữ liệu gia tăng thành dữ liệu tích lũy hoặc chuẩn bị truy vấn tổng khoảng.

Nếu số lượng có thể vượt `Integer.MAX_VALUE`, **không dùng `int[]` chỉ vì phần tử riêng lẻ là int**: chuyển sang `long[]` *trước khi tích lũy*, và nếu tổng có thể vượt long, cân nhắc `BigInteger[]`.

### 5.2. Running max/min

~~~java
int[] peaks = {3, 1, 4, 2};
Arrays.parallelPrefix(peaks, Math::max);
// [3, 3, 4, 4]
~~~

Mỗi vị trí là giá trị lớn nhất đã quan sát được tính từ đầu đoạn. `Math::min` tương tự cho giá trị nhỏ nhất tích lũy. Cả min và max trên số nguyên có tính kết hợp và không đòi hỏi sắp mảng trước.

### 5.3. Bitmask tích lũy

~~~java
int[] flags = {1, 2, 4, 8};
Arrays.parallelPrefix(flags, (left, right) -> left | right);
// [1, 3, 7, 15]
~~~

Mỗi prefix là tập hợp các bit đã bật từ đầu nguồn đến vị trí đó. Bitwise OR kết hợp và giao hoán, rất phù hợp khi cần tổng hợp cờ trạng thái. Nếu nghiệp vụ cần giao/đồng thuận bit, bitwise AND cũng kết hợp; XOR dùng được cho trạng thái parity.

Những phép trên hoạt động ở mức bit của `int`; với trường hợp cần logic true/false trên mảng `boolean[]`, `parallelPrefix` không có overload primitive boolean, có thể dùng biểu diễn khác nếu thật sự cần.

### 5.4. Running product

~~~java
long[] factors = {2L, 3L, 4L};
Arrays.parallelPrefix(factors, (left, right) -> left * right);
// [2, 6, 24]
~~~

Phép nhân kiểu nguyên có tính kết hợp theo số học nguyên của Java, nhưng tràn `long` có thể làm kết quả sai miền thực. Không dùng phép nhân các hệ số lớn khi không có chính sách tràn thích hợp.

### 5.5. Prefix nối thông tin theo thứ tự

~~~java
String[] segments = {"A", "B", "C"};
Arrays.parallelPrefix(segments, String::concat);
// [A, AB, ABC]
~~~

Hữu ích để minh họa toán tử **kết hợp nhưng không giao hoán**. Trong thực tế, lưu mọi tiền tố của một chuỗi dài có thể tốn nhiều bộ nhớ và thời gian tạo chuỗi; đừng dùng nó cho khối lượng lớn nếu bài toán chỉ muốn chuỗi hoàn chỉnh cuối cùng. Có thể thiết kế dạng cấu trúc dữ liệu khác phù hợp.

## 6. In-place: mảng đầu vào chính là kết quả

Hợp đồng `Arrays.parallelPrefix` là cập nhật ngay trên mảng nhận vào. Nó **không trả mảng mới**:

~~~java
int[] input = {2, 1, 3};
Arrays.parallelPrefix(input, Integer::sum);
System.out.println(Arrays.toString(input));
// [2, 3, 6]
~~~

Vì vậy đừng viết `int[] result = Arrays.parallelPrefix(...);`: phương thức trả `void` nên không thể gán như vậy.

Nếu cần giữ dữ liệu nguyên thủy để tính nhiều truy vấn hoặc so sánh, sao chép **trước khi** tích lũy:

~~~java
int[] source = {2, 1, 3};
int[] prefix = Arrays.copyOf(source, source.length);
Arrays.parallelPrefix(prefix, Integer::sum);

// source = [2, 1, 3]
// prefix = [2, 3, 6]
~~~

`Arrays.copyOf` hoặc `clone()` tạo bản sao mảng mới. Với `T[]`, đây chỉ là **shallow copy**: các object phần tử vẫn được chia sẻ. Nếu operator cũng mutate chính object mà hai mảng cùng trỏ tới, bạn không còn giữ được dữ liệu nguồn độc lập. **Operator nên không có side effect và phù hợp với immutability/ownership**.

Sau một lần gọi, mảng hiện chứa **prefix**, không phải các phần tử gốc. Gọi `parallelPrefix` lần thứ hai trên cùng mảng không phải phép tính idempotent thông thường; nó tích lũy **một lần nữa trên chính dãy prefix đã sinh ra**. Ví dụ tổng prefix từ `[2,3,6]` cho ra `[2,5,11]`, không phải vẫn `[2,3,6]`.

## 7. Lưu ý đặc biệt về số học: tràn và double

### 7.1. Cộng int/long có tính kết hợp nhưng vẫn tràn

Ví dụ:

~~~java
int[] numbers = {Integer.MAX_VALUE, 1};
Arrays.parallelPrefix(numbers, Integer::sum);

// [2147483647, -2147483648]
~~~

Kết quả thứ hai **không phải tổng toán học chính xác**; đây là overflow của `int`. Java không tự ném exception cho cộng `int` thông thường, và `parallelPrefix` cũng không biến phép cộng ấy thành big integer.

Nếu số hạng ban đầu là int nhưng tổng có thể lớn hơn int, nên tạo `long[]` trước:

~~~java
int[] input = {Integer.MAX_VALUE, 1};
long[] widened = Arrays.stream(input)
        .asLongStream()
        .toArray();
Arrays.parallelPrefix(widened, Long::sum);

// [2147483647, 2147483648]
~~~

Đây là đoạn đặt trong một phương thức có import Arrays. **Cần chuyển kiểu trước khi tích lũy**: nếu đã tràn ở bước xử lý int, cast kết quả sang long sau đó không thể phục hồi số đúng.

Nếu tổng vượt cả `long`, dùng kiểu số lớn:

~~~java
java.math.BigInteger[] exact = {
        java.math.BigInteger.valueOf(Long.MAX_VALUE),
        java.math.BigInteger.ONE,
        java.math.BigInteger.TEN
};

Arrays.parallelPrefix(exact, java.math.BigInteger::add);
// [9223372036854775807,
//  9223372036854775808,
//  9223372036854775818]
~~~

`BigInteger::add` là phép toán kết hợp trên số nguyên tùy ý và trả object mới. Đó là ví dụ phù hợp khi ứng dụng cần **tổng nguyên chính xác**, đổi lại có chi phí tạo object/bộ nhớ.

### 7.2. Đừng dùng Math.addExact rồi mặc định an toàn cho scan song song

`Math.addExact` ném `ArithmeticException` khi **một phép cộng trung gian** tràn. Nó giúp phát hiện lỗi trong một số thuật toán, nhưng khi ghép prefix song song, các phép tính có thể được nhóm theo cách khác vòng lặp trái sang phải.

Chẳng hạn một nhóm tạm có thể tràn int dù tổng toán học cuối sau khi cộng các giá trị trái dấu vẫn nằm trong miền int. Vì thế `Math::addExact` không phải giải pháp tổng quát để biến `parallelPrefix` thành thuật toán tính “mọi tổng prefix chính xác” trên mọi input. Khi cần kết quả nguyên **chính xác và độc lập cách nhóm**, sử dụng miền số đủ lớn, ví dụ `BigInteger[]`.

Nếu ứng dụng chủ đích phát hiện overflow theo **một trình tự cộng cố định**, hãy dùng thuật toán tuần tự với `Math.addExact` và tài liệu hóa trình tự; đừng phụ thuộc vào thứ tự nội bộ không được cam kết của parallel prefix.

### 7.3. Double không kết hợp nghiêm ngặt

Phép cộng `double` là số học dấu phẩy động với làm tròn hữu hạn. Nói chung:

~~~text
(a + b) + c có thể khác a + (b + c)
~~~

Do đó, tài liệu của `Arrays.parallelPrefix(double[], op)` ghi rõ rằng kết quả **có thể không giống kết quả cộng tuần tự** khi toán tử dấu phẩy động không kết hợp nghiêm ngặt. Không gán lời hứa sai rằng mọi giá trị tiền tố sẽ có cùng bit kết quả trên mọi số lượng thread, mọi kích thước và mọi version JDK.

Ví dụ với dữ liệu **có thể biểu diễn chính xác trong nhị phân**:

~~~java
double[] sample = {1.5, 2.0, 3.5};
Arrays.parallelPrefix(sample, Double::sum);
// [1.5, 3.5, 7.0]
~~~

Đây là một ví dụ đầu ra ổn định, không chứng minh rằng mọi phép cộng `double` đều kết hợp. Với dữ liệu như `0.1`, `0.2`, số rất lớn xen số rất nhỏ, giá trị trung gian có thể lệch do làm tròn. `NaN`, `Infinity` và zero có dấu cũng phải có chính sách đầu vào riêng.

Nếu số tiền cần đúng đến đơn vị thập phân, chọn biểu diễn phù hợp như số nguyên đơn vị nhỏ nhất trong miền đủ rộng hoặc `BigDecimal[]` với chính sách làm tròn được kiểm soát, thay vì tin rằng parallelPrefix khắc phục được sai số `double`.

## 8. Side-effect-free: yêu cầu quan trọng ngang tính kết hợp

Tài liệu `Arrays.parallelPrefix` nêu operator phải **không có side effect** và có tính kết hợp (trường hợp `double` có cảnh báo riêng về giới hạn floating point).

Điều này có nghĩa **không nên** cho callback:

- Thêm dữ liệu vào một `ArrayList` dùng chung.
- Tăng bộ đếm làm logic nghiệp vụ.
- Ghi log rồi kỳ vọng một dòng cho mỗi phần tử hoặc đúng thứ tự.
- Sửa chính mảng đang được parallelPrefix xử lý.
- Gọi dịch vụ bên ngoài có side effect, ghi database hoặc gửi message.
- Đọc trạng thái mutable đang bị thread khác thay đổi khiến phép toán không còn nhất quán.

Phản ví dụ:

~~~java
int[] values = {1, 2, 3, 4};
java.util.concurrent.atomic.AtomicInteger calls =
        new java.util.concurrent.atomic.AtomicInteger();

Arrays.parallelPrefix(values, (a, b) -> {
    calls.incrementAndGet(); // Không dùng để suy ra số prefix.
    return a + b;
});
~~~

Đoạn code có thể chạy nhưng là **cách sử dụng không nên áp dụng**. Dù `AtomicInteger` tránh data race cho bộ đếm, nó vẫn là side effect; cách chia nhóm và số lần gọi operator không được dùng làm hợp đồng đếm số phần tử. **Thread-safe side effect không tự biến toán tử thành side-effect-free**.

### 8.1. Có cần operator giao hoán không?

Không. Sắp xếp thứ tự phần tử là một phần ý nghĩa prefix. `String::concat` không giao hoán nhưng cho dãy `[A, AB, ABC]` đúng khi các chuỗi đầu vào là `[A,B,C]`. Chỉ cần toán tử **có tính kết hợp theo thứ tự đó** và không tạo side effect.

Nếu một toán tử cần thông tin index, timestamp, trạng thái ngoài hoặc điều kiện không cố định, hãy cân nhắc tiền xử lý dữ liệu thành giá trị độc lập trước khi chạy prefix. Toán tử chỉ nên ghép hai đại diện kết quả theo quy tắc rõ ràng.

### 8.2. Object mutable và alias

Với `T[]`, operator có thể nhận object cũng được tham chiếu ở nơi khác. Nếu nó mutate `left` rồi trả `left`, các phần tử khác có thể đang giữ cùng tham chiếu hoặc được một nhánh tính khác truy cập, gây sai nghĩa và race.

Ưu tiên các loại immutable như `String`, `BigInteger`, record/value object không thay đổi (record là API Java hiện hành) hoặc một kiểu kết quả mới được tạo từ hai đối số mà không sửa chúng. Tránh trả một object mutable được chia sẻ giữa mọi vị trí trong mảng.

### 8.3. Lỗi ở giữa quá trình tính

Nếu operator ném exception khi một nhánh đã tính xong, **đừng giả định mảng được rollback toàn bộ** về trạng thái trước lời gọi. Đây là thao tác **in-place**, không phải transaction. Tùy lúc xảy ra exception, một phần mảng có thể đã bị cập nhật.

Với dữ liệu quan trọng, validate trước, dùng copy để thực hiện tính toán rồi chỉ công bố kết quả sau khi thành công. Cần tách bạch việc bảo vệ bản gốc bằng copy với các vấn đề concurrency khác.

## 9. Ví dụ Java độc lập: nhiều kiểu phép tích lũy

Tạo file **`ParallelPrefixDemo.java`**. Chương trình chạy trên **JDK 17+** và chỉ sử dụng API Java còn được hỗ trợ, không cần thư viện bên ngoài. Từng ví dụ kiểm tra một hợp đồng rõ ràng: inclusive scan, khoảng nửa mở, running max, bitwise OR, long product, double trên dữ liệu biểu diễn chính xác, nối chuỗi, overflow, BigInteger, mảng rỗng, mảng một phần tử và lỗi chỉ số.

~~~java
import java.math.BigInteger;
import java.util.Arrays;

public class ParallelPrefixDemo {
    public static void main(String[] args) {
        int[] sums = {2, 1, 0, 3};
        Arrays.parallelPrefix(sums, Integer::sum);
        System.out.println("Sums: " + Arrays.toString(sums));

        int[] partial = {100, 2, 1, 3, 200};
        Arrays.parallelPrefix(partial, 1, 4, Integer::sum);
        System.out.println("Range [1,4): " + Arrays.toString(partial));

        int[] maxes = {3, 1, 4, 2};
        Arrays.parallelPrefix(maxes, Math::max);
        System.out.println("Running max: " + Arrays.toString(maxes));

        int[] flags = {1, 2, 4, 8};
        Arrays.parallelPrefix(flags, (left, right) -> left | right);
        System.out.println("Flags OR: " + Arrays.toString(flags));

        long[] products = {2L, 3L, 4L};
        Arrays.parallelPrefix(products, (a, b) -> a * b);
        System.out.println("Long products: "
                + Arrays.toString(products));

        double[] decimals = {1.5, 2.0, 3.5};
        Arrays.parallelPrefix(decimals, Double::sum);
        System.out.println("Double sums: "
                + Arrays.toString(decimals));

        String[] text = {"A", "B", "C"};
        Arrays.parallelPrefix(text, String::concat);
        System.out.println("Concat: " + Arrays.toString(text));

        String[] textRange = {"start", "a", "b", "c", "end"};
        Arrays.parallelPrefix(textRange, 1, 4, String::concat);
        System.out.println("Text range: "
                + Arrays.toString(textRange));

        int[] overflows = {Integer.MAX_VALUE, 1};
        Arrays.parallelPrefix(overflows, Integer::sum);
        System.out.println("Int overflow: "
                + Arrays.toString(overflows));

        BigInteger[] precise = {
                BigInteger.valueOf(Long.MAX_VALUE),
                BigInteger.ONE, BigInteger.TEN
        };
        Arrays.parallelPrefix(precise, BigInteger::add);
        System.out.println("Exact big sum: "
                + Arrays.toString(precise));

        int[] empty = {};
        long[] single = {7};
        Arrays.parallelPrefix(empty, Integer::sum);
        Arrays.parallelPrefix(single, Long::sum);
        System.out.println("Empty: " + Arrays.toString(empty));
        System.out.println("Single: " + Arrays.toString(single));

        try {
            Arrays.parallelPrefix(partial, 4, 3, Integer::sum);
        } catch (IllegalArgumentException expected) {
            System.out.println("Reversed range rejected");
        }

        try {
            Arrays.parallelPrefix(partial, -1, 3, Integer::sum);
        } catch (ArrayIndexOutOfBoundsException expected) {
            System.out.println("Negative index rejected");
        }

        try {
            Arrays.parallelPrefix(sums,
                    (java.util.function.IntBinaryOperator) null);
        } catch (NullPointerException expected) {
            System.out.println("Null operator rejected");
        }

        System.out.println("Prefix verified: "
                + Arrays.equals(sums, new int[]{2, 3, 3, 6}));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ParallelPrefixDemo.java
java ParallelPrefixDemo
~~~

Stdout đã được xác minh:

~~~text
Sums: [2, 3, 3, 6]
Range [1,4): [100, 2, 3, 6, 200]
Running max: [3, 3, 4, 4]
Flags OR: [1, 3, 7, 15]
Long products: [2, 6, 24]
Double sums: [1.5, 3.5, 7.0]
Concat: [A, AB, ABC]
Text range: [start, a, ab, abc, end]
Int overflow: [2147483647, -2147483648]
Exact big sum: [9223372036854775807, 9223372036854775808, 9223372036854775818]
Empty: []
Single: [7]
Reversed range rejected
Negative index rejected
Null operator rejected
Prefix verified: true
~~~

**Giải thích:**

1. `Sums: [2, 3, 3, 6]`: mọi vị trí là tổng **bao gồm chính phần tử ấy**.
2. `Range [1,4): [100, 2, 3, 6, 200]`: index 0 và 4 không đổi; đoạn tích lũy bắt đầu tại giá trị 2, không cộng 100.
3. `Running max` và `Flags OR` lần lượt dùng hai phép kết hợp đúng nghĩa để theo dõi cực đại và hợp nhất các bit đã quan sát.
4. `Long products: [2, 6, 24]`: phép nhân tích lũy, không phải `sum`.
5. `Double sums: [1.5, 3.5, 7.0]` dùng giá trị nhỏ có thể biểu diễn chính xác, không phủ nhận cảnh báo sai số đối với dữ liệu khác.
6. `Concat: [A, AB, ABC]` cho thấy operator có thể **kết hợp nhưng không giao hoán**; `Text range` nhấn mạnh điểm bắt đầu mới của đoạn.
7. `Int overflow` quay vòng thành `Integer.MIN_VALUE`, còn `Exact big sum` giữ số nguyên chính xác lớn hơn long.
8. `Empty` và `Single` giữ nguyên dữ liệu do không có đủ hai phần tử để kết hợp; operator vẫn phải khác null.
9. Các lời gọi cận sai lần lượt bị từ chối bằng `IllegalArgumentException` và `ArrayIndexOutOfBoundsException`. Operator null bị từ chối bằng `NullPointerException`.
10. Dòng `Prefix verified: true` chỉ kiểm thử một kết quả cụ thể bằng `Arrays.equals`, không giả định hay kiểm đếm số lần operator được framework gọi.

Lệnh chạy chương trình trên sử dụng mảng được in bằng `Arrays.toString`. Không in trực tiếp một mảng rồi kỳ vọng Java tự định dạng danh sách các phần tử.

## 10. So sánh với for, Stream.reduce và parallelSetAll

### 10.1. Một vòng lặp tuần tự cũng có thể tính prefix

Ví dụ phép cộng khi không có yêu cầu xử lý song song:

~~~java
int[] input = {2, 1, 0, 3};
int[] output = new int[input.length];
int acc = 0;

for (int i = 0; i < input.length; i++) {
    acc += input[i];
    output[i] = acc;
}
// output = [2, 3, 3, 6]
~~~

Đây là mảnh code chạy trong phương thức. Nó **tính tuần tự theo thứ tự xác định** và giữ mảng đầu vào nguyên vẹn vì ghi ra mảng riêng. Với phép cộng, identity 0 là phù hợp. Với phép toán tổng quát, muốn tính inclusive mà không có identity thì phải khởi tạo từ phần tử đầu của mảng khi mảng không rỗng.

`Arrays.parallelPrefix` có thể thuận tiện và tận dụng tính song song ở mảng lớn, nhưng không mặc nhiên nhanh hơn vòng lặp nhỏ. Cần đo benchmark theo dữ liệu và môi trường thật.

### 10.2. Reduce trả kết quả cuối, prefix tạo mọi kết quả trung gian

~~~java
int[] values = {2, 1, 0, 3};
int total = Arrays.stream(values).sum(); // 6
~~~

`sum()`/`reduce()` của Stream thường dùng để tạo **một kết quả tổng hợp**. Ngược lại, `parallelPrefix` giữ **một kết quả cho mỗi vị trí**:

~~~text
reduce/sum:           6
parallelPrefix:       [2, 3, 3, 6]
~~~

Nếu chỉ cần tổng cuối, không cần biến toàn mảng thành prefix; cân nhắc Stream sum hoặc một vòng lặp với kiểu số phù hợp. Nếu cần tất cả tổng lũy kế, prefix mới là cấu trúc dữ liệu trực tiếp.

`Stream` không cung cấp một lời gọi `scan(...)` tương đương `Arrays.parallelPrefix` trong bộ API Stream chuẩn đang được dùng phổ biến; các thư viện khác hoặc các cách xây pipeline riêng có thể hỗ trợ, nhưng không nên thay lời gọi Arrays chuẩn bằng API chưa có trong JDK mục tiêu.

### 10.3. ParallelSetAll khác parallelPrefix

~~~java
int[] numbers = new int[4];
Arrays.parallelSetAll(numbers, i -> i * 2);
// [0, 2, 4, 6]
~~~

`parallelSetAll` tính **giá trị từng phần tử theo chỉ số** độc lập với các phần tử trước, còn `parallelPrefix` kết hợp **giá trị của các tiền tố**. Hai phương thức không thể thay thế nhau chỉ vì đều có tiền tố tên “parallel”.

`Arrays.parallelSort` lại thực hiện **sắp thứ tự**, không cộng dồn. Nếu bạn muốn danh sách tăng dần giá trị, dùng sort; nếu muốn running total, dùng prefix.

## 11. Hiệu năng: khi nào nên dùng parallelPrefix?

Trong thuật toán song song, dữ liệu có thể được chia thành nhóm, tính tích lũy từng nhóm và kết hợp thông tin prefix của những nhóm trước. Cách tổ chức này giúp nhiều phép toán được thực hiện song song về mặt cấu trúc khi toán tử kết hợp.

Nhưng điều đó **không bảo đảm nhanh hơn vòng lặp tuần tự**:

- **Mảng nhỏ**: chi phí phân chia task và phối hợp có thể lớn hơn lợi ích song song.
- **Operator rẻ**: ví dụ cộng `int` trên mảng ngắn, tốc độ đọc/ghi bộ nhớ có thể chi phối; cần benchmark trước khi chọn.
- **Operator tốn chi phí**: khả năng có lợi từ nhiều lõi cao hơn, nhưng operator phải thread-safe và không side effect.
- **Mảng object**: phép tính có thể cấp phát object trung gian, làm tăng GC/áp lực bộ nhớ; đặc biệt prefix tạo nhiều chuỗi dài.
- **Hệ thống đang chạy nhiều tác vụ**: tài nguyên CPU và cấu hình parallelism ảnh hưởng throughput, không thể suy ra tốc độ chỉ từ tên API.
- **Truy cập bộ nhớ**: nhiều công việc prefix thường cần đọc/ghi từng phần tử và phối hợp các chunk; băng thông bộ nhớ có thể là nút thắt.

JDK có thể sử dụng các tác vụ ForkJoin và cơ chế thực thi song song, nhưng **không có cam kết** rằng một lời gọi trên mảng nhỏ sẽ chạy trên nhiều thread cụ thể, cũng không có bảo đảm operator được gọi đúng một lần cho mỗi vị trí.

Để benchmark, dùng công cụ đo thực nghiệm như JMH, warm-up và input phù hợp; luôn tạo **bản sao dữ liệu đầu vào** cho mỗi lần chạy vì `parallelPrefix` làm thay đổi mảng ngay tại chỗ. Nếu benchmark lặp trên cùng mảng đã tính prefix, dữ liệu vòng sau khác vòng trước và phép so sánh có thể vô nghĩa.

## 12. Kiểm thử đúng hợp đồng, không theo scheduler

### 12.1. Bảng ca kiểm thử

| Tình huống | Kỳ vọng |
|---|---|
| Mảng rỗng | Không đổi, không có prefix |
| Một phần tử | Phần tử đó giữ nguyên |
| Toàn mảng, phép cộng | Kết quả thứ i là tổng gốc từ 0 đến i |
| Khoảng `[from,to)` | Bên ngoài đoạn không đổi, bên trong tính từ `from` |
| Khoảng rỗng `[k,k)` | Mảng không đổi |
| `from > to` | Ném `IllegalArgumentException` |
| `from < 0` hoặc `to > length` | Ném `ArrayIndexOutOfBoundsException` |
| Toán tử null | Ném `NullPointerException` |
| Running max | Mỗi prefix là max đã gặp |
| Nối chuỗi | Giữ thứ tự các phần tử, dù phép toán không giao hoán |
| Cộng int chạm biên | Xác nhận overflow modulo hoặc chọn kiểu lớn hơn |
| Tổng nguyên lớn hơn long | `BigInteger[]` giữ kết quả chính xác |
| Double có giá trị gây làm tròn | Dùng chính sách sai số/tolerance, không đòi bit y hệt tuần tự |
| Operator có state hoặc side effect | Thiết kế lại operator, không test một thứ tự callback cố định |
| Cùng mảng bị thread ngoài sửa | Không có giả định an toàn; dùng ownership/snapshot |
| Operator ném exception | Không giả định mảng tự được rollback |

### 12.2. Oracle tuần tự để đối chiếu

Với operator **kết hợp và không side effect**, có thể tính kết quả tham chiếu từ một bản gốc **không bị sửa**:

~~~java
int[] original = {4, 1, 3, 2};
int[] expected = original.clone();

for (int i = 1; i < expected.length; i++) {
    expected[i] = Integer.sum(expected[i - 1], original[i]);
}

int[] actual = original.clone();
Arrays.parallelPrefix(actual, Integer::sum);

if (!Arrays.equals(expected, actual)) {
    throw new AssertionError("Prefix mismatch");
}
~~~

Đoạn code này có thể chạy trong phương thức có import Arrays. Vòng lặp tham chiếu sử dụng phần tử **gốc** ở `original[i]`, không đọc nhầm phần tử có thể đã bị biến đổi ngoài ý muốn. Kỳ vọng với dữ liệu trên là `[4,5,8,10]`.

Với một toán tử tổng quát khác, oracle phải tuân theo cùng **thứ tự phần tử** và hợp đồng kết hợp. Đối với `double`, so sánh tolerance và xử lý `NaN`/`Infinity` theo quy tắc bài toán; không luôn dùng `Arrays.equals` để bắt buộc exact bitwise giữa parallel và left fold nếu phép tính có sai số làm tròn.

### 12.3. Kiểm thử khoảng

Cho `[from,to)`:

1. Chụp bản sao dữ liệu trước khi gọi.
2. So sánh vị trí `i < from` và `i >= to` sau lời gọi: chúng phải giữ nguyên.
3. Với đoạn không rỗng, vị trí `from` giữ giá trị phần tử gốc.
4. Với các vị trí sau đó trong đoạn, so sánh với oracle chỉ cộng từ **from** đến **i**.
5. Kiểm cả trường hợp `from == to`, `to == array.length` và các biên không hợp lệ.

Đặc biệt, **không yêu cầu prefix đoạn thứ hai chứa tổng đoạn thứ nhất** trừ khi ứng dụng đã tự thiết kế cách nối các tổng đoạn bằng một bước riêng.

### 12.4. Kiểm tính kết hợp của operator

Với toán tử tự xây trên kiểu miền, tạo test đại diện:

~~~java
int left = Math.max(Math.max(3, 1), 4);
int right = Math.max(3, Math.max(1, 4));

if (left != right) {
    throw new AssertionError("max must be associative");
}
~~~

Đây là mảnh code đơn giản. Một test với vài mẫu **không chứng minh tính kết hợp cho mọi input**; phải dựa vào đặc tính toán học/hợp đồng của kiểu và operator. Với operator có trạng thái hoặc giới hạn overflow khác nhau theo cách nhóm, cần phân tích kỹ hơn.

Đừng dùng phép thử chỉ so total cuối rồi kết luận mọi prefix đều đúng: một toán tử sai có thể cho total cuối trông hợp lý nhưng nhiều tiền tố sai. Test cần kiểm **tất cả vị trí**, kể cả khoảng.

## 13. Các lỗi phổ biến và cách tránh

**Lỗi 1 — Tưởng parallelPrefix là parallelSort.** Prefix tích lũy các phần tử, không sắp xếp chúng. Running max cũng không đồng nghĩa với sort: `[3,3,4,4]` là một dãy prefix max, không phải bản sắp của `[3,1,4,2]`.

**Lỗi 2 — Dùng phép trừ hoặc chia và kỳ vọng giống vòng lặp.** Chúng không kết hợp; parallel có thể nhóm khác thứ tự dấu ngoặc. Chọn thuật toán tuần tự hoặc thiết kế biểu diễn toán tử khác có tính kết hợp.

**Lỗi 3 — Yêu cầu toán tử giao hoán.** API chỉ cần kết hợp và không side effect. `String::concat` hợp lệ cho các chuỗi khác null và vẫn giữ thứ tự prefix.

**Lỗi 4 — Viết operator có side effect.** Callback có thể được gọi từ nhiều thread và theo chiến lược không cố định. Không ghi DB, mutate Map/ArrayList dùng chung hoặc đếm số callback làm business logic.

**Lỗi 5 — Quên phương thức sửa mảng tại chỗ.** Không có mảng mới được trả về. Clone/copy trước nếu cần giữ dữ liệu gốc hoặc tránh các caller khác nhìn thấy trạng thái bị đổi.

**Lỗi 6 — Tưởng prefix là exclusive.** Phần tử đầu là `a[0]`, không phải zero; không có tham số identity trong overload hiện hành.

**Lỗi 7 — Dùng cận cuối inclusive.** `parallelPrefix(a, 1, 4, op)` chỉ xử lý chỉ số 1,2,3. Không kéo index 4 vào prefix.

**Lỗi 8 — Ghép prefix hai đoạn mà không mang trạng thái.** Hai lần gọi range độc lập không tạo prefix trên toàn mảng; cần bước gộp riêng nếu muốn tổng lũy kế xuyên đoạn.

**Lỗi 9 — Dùng int/long cho tổng vượt miền.** Cộng primitive vẫn có thể overflow và wrap. Chuyển sang long trước khi tích lũy nếu đủ miền; dùng BigInteger nếu cần số nguyên chính xác lớn hơn.

**Lỗi 10 — Tin double cộng song song luôn bitwise giống cộng tuần tự.** Số thực không kết hợp chặt chẽ vì làm tròn; thiết kế dung sai hoặc thuật toán/kiểu số chuyên biệt.

**Lỗi 11 — Benchmark nhiều lượt trên cùng mảng.** Sau lượt đầu, dữ liệu đầu vào đã là prefix. Phải reset/copy nguồn trước mỗi lần đo.

**Lỗi 12 — Dùng parallelPrefix trên object mutable có alias và operator mutate operand.** Làm phá vỡ điều kiện không side effect và có thể tạo race. Ưu tiên giá trị bất biến hoặc tạo kết quả mới mà không sửa đầu vào.

**Lỗi 13 — Coi “parallel” là chắc chắn nhanh và nhiều thread.** Hiệu năng phụ thuộc kích thước dữ liệu, operator, máy, contention và overhead; không có bảo đảm mọi lần đều chạy song song trên nhiều thread.

**Lỗi 14 — Nếu operator lỗi, giả định mảng trở về trạng thái cũ.** Không có rollback transaction trong hợp đồng; phải dùng bản sao khi tính toàn vẹn dữ liệu quan trọng.

## 14. Bài tập tự luyện

1. Cho `int[] a = {3, 2, 4, 1}`. Hãy dự đoán kết quả `Arrays.parallelPrefix(a, Integer::sum)`.
2. Cho `int[] a = {50, 2, 3, 4, 60}`. Với `Arrays.parallelPrefix(a, 1, 4, Integer::sum)`, các vị trí ngoài đoạn có thay đổi không? Kết quả trong đoạn là gì?
3. Tại sao `(x,y) -> x-y` không được dùng như một operator prefix song song đúng nghĩa?
4. `String::concat` có cần giao hoán không? Nó có tính kết hợp không đối với chuỗi khác null?
5. Phân biệt kết quả của `Arrays.parallelPrefix`, `Arrays.parallelSort` và `Arrays.parallelSetAll`.
6. Nếu `int[]` gồm hai giá trị `Integer.MAX_VALUE` và `1`, kết quả prefix thứ hai là gì? Làm thế nào để giữ tổng toán học chính xác?
7. Vì sao `Double::sum` có thể cho kết quả không giống vòng lặp khi dữ liệu lớn và có độ lớn chênh lệch nhiều?
8. Chương trình cần giữ mảng gốc cho một phần khác sử dụng. Nên làm gì trước khi parallelPrefix?
9. Nếu đoạn `[4,4)` trên một mảng dài 6 được đưa vào, điều gì xảy ra? Còn `[5,4)`?
10. Nêu một bộ test kiểm tra đúng **mọi** prefix với operator `Math::max`, không chỉ kết quả cuối.
11. Vì sao operator có `AtomicInteger.incrementAndGet()` vẫn không nên dùng để đếm “số thao tác nghiệp vụ”?
12. Khi cần tổng nguyên chính xác vượt giới hạn long, dùng mảng object và operator nào?

**Gợi ý đáp án:**

1. `[3, 5, 9, 10]`.
2. Index 0 và 4 giữ nguyên; kết quả `[50, 2, 5, 9, 60]`.
3. Vì phép trừ không kết hợp; thay đổi cách nhóm có thể thay kết quả.
4. Không cần giao hoán; nối chuỗi khác null kết hợp, giữ thứ tự phần tử.
5. Prefix tính dãy tích lũy; sort sắp thứ tự; setAll tính từng phần tử theo index độc lập.
6. Tràn thành `Integer.MIN_VALUE`; chuyển sang long trước hoặc dùng BigInteger.
7. Vì phép cộng double có sai số làm tròn nên không kết hợp nghiêm ngặt.
8. Sao chép mảng trước, rồi chạy parallelPrefix trên bản sao.
9. `[4,4)` rỗng và hợp lệ; `[5,4)` có from lớn hơn to, ném `IllegalArgumentException`.
10. Duyệt từng vị trí trên bản gốc để tính running max, rồi so sánh từng phần tử.
11. AtomicInteger chỉ giúp đếm an toàn hơn về data race nhưng side effect vẫn không thuộc hợp đồng operator; số lần gọi/timing không được hứa.
12. `BigInteger[]` và `BigInteger::add`.

## Ghi nhớ

- `Arrays.parallelPrefix` **tính tiền tố tích lũy inclusive** và **sửa mảng tại chỗ**.
- Có overload cho `int[]`, `long[]`, `double[]` và `T[]`; cả toàn mảng lẫn đoạn `[fromIndex, toIndex)`.
- Đoạn bắt đầu prefix **tại fromIndex**, không nối trạng thái từ phần tử trước đoạn; vị trí ngoài đoạn được bảo toàn.
- Operator phải **kết hợp và không side effect**. Nó **không bắt buộc giao hoán**; thứ tự phần tử vẫn được giữ trong nghĩa prefix.
- Số nguyên có thể tràn; `double` không kết hợp nghiêm ngặt do làm tròn; chọn kiểu dữ liệu và chính sách sai số theo nhu cầu nghiệp vụ.
- Không mặc định chạy nhanh hơn for tuần tự, không dựa vào số thread/callback, không mutate cùng mảng từ nơi khác khi đang tính.

### Tài liệu chính thức, API vẫn hiện hành

- [Oracle Java SE 26 — Arrays.parallelPrefix và các overload](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html)
- [Oracle Java SE 26 — IntBinaryOperator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/IntBinaryOperator.html)
- [Oracle Java SE 26 — LongBinaryOperator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/LongBinaryOperator.html)
- [Oracle Java SE 26 — DoubleBinaryOperator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/DoubleBinaryOperator.html)
- [Oracle Java SE 26 — BinaryOperator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/BinaryOperator.html)
- [Oracle Java SE 26 — BigInteger](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html)
