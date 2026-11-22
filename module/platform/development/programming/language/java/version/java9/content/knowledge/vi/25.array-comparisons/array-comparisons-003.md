# Tìm vị trí khác đầu tiên bằng mismatch

Java 9 bổ sung các phương thức `Arrays.mismatch()` để tìm **vị trí đầu tiên mà hai mảng không còn tương ứng bằng nhau**. Phương thức trả về chỉ số của phần tử khác đầu tiên; nếu hai mảng bằng nhau hoàn toàn, kết quả là `-1`.

`mismatch()` hữu ích khi so sánh dữ liệu nhị phân, kết quả tính toán, mảng primitive, mảng object hoặc một đoạn con của hai mảng. Với mảng object, có thể truyền `Comparator` để xác định thế nào là hai phần tử tương đương trong phép so sánh.

API này được giới thiệu từ Java 9 và vẫn là API hiện hành. Nội dung dưới đây tập trung vào hợp đồng của `Arrays.mismatch()` và cách sử dụng trong mã ứng dụng.

## Mục tiêu

- Hiểu giá trị trả về của `Arrays.mismatch()`.
- Phân biệt trường hợp hai mảng bằng nhau, khác phần tử và khác độ dài.
- Sử dụng overload cho mảng primitive và mảng object.
- So sánh theo một `Comparator` tùy chỉnh.
- So sánh các đoạn con bằng range overload và quy đổi chỉ số tương đối.
- Nhận biết các trường hợp đặc biệt của `float`, `double`, `null` và kiểm tra phạm vi.

## 1. Ý nghĩa của `Arrays.mismatch()`

`Arrays.mismatch(a, b)` duyệt hai mảng theo cùng vị trí, bắt đầu từ đầu mảng. Kết quả là vị trí đầu tiên mà hai phần tử tương ứng khác nhau theo quy tắc equality của overload được gọi.

| Kết quả | Ý nghĩa |
| --- | --- |
| `0` | Phần tử đầu tiên đã khác nhau |
| Số nguyên dương `k` | Các phần tử từ vị trí `0` đến `k - 1` khớp; vị trí `k` là khác biệt đầu tiên |
| `-1` | Hai mảng có cùng độ dài và mọi phần tử tương ứng đều khớp |
| Độ dài của mảng ngắn hơn | Một mảng là tiền tố hoàn chỉnh của mảng dài hơn; mọi phần tử trong phần chung đều khớp |

Ví dụ:

~~~java
int[] expected = {2, 4, 6, 8, 10};
int[] actual = {2, 4, 7, 8, 10};

int index = Arrays.mismatch(expected, actual);
System.out.println(index); // 2
~~~

Hai mảng có cùng phần tử tại vị trí `0` và `1`. Vị trí `2` chứa `6` ở mảng `expected` và `7` ở mảng `actual`, vì vậy kết quả là `2`.

### 1.1. Hai mảng bằng nhau

Nếu hai mảng có cùng độ dài và mọi phần tử tương ứng bằng nhau, phương thức trả về `-1`:

~~~java
int[] first = {1, 2, 3};
int[] second = {1, 2, 3};

System.out.println(Arrays.mismatch(first, second)); // -1
~~~

Đây là cách kiểm tra nhanh hai mảng có bằng nhau theo đúng quy tắc phần tử của overload hay không. Nếu chỉ cần boolean, `Arrays.equals()` là API diễn đạt ý định trực tiếp hơn; `mismatch()` hữu ích khi cần biết vị trí khác biệt.

### 1.2. Một mảng là tiền tố của mảng còn lại

Độ dài khác nhau cũng được xem là một điểm khác biệt. Nếu mọi phần tử của mảng ngắn hơn đều khớp với phần đầu của mảng dài hơn, kết quả là độ dài mảng ngắn hơn:

~~~java
int[] shortArray = {1, 2};
int[] longArray = {1, 2, 3, 4};

System.out.println(Arrays.mismatch(shortArray, longArray)); // 2
~~~

Chỉ số `2` chính là vị trí đầu tiên mà mảng ngắn không còn phần tử tương ứng. Vì vậy, `-1` chỉ được trả về khi cả nội dung lẫn độ dài đều khớp.

## 2. Các overload theo kiểu mảng

Java 9 cung cấp overload `mismatch()` cho các mảng primitive:

- `boolean[]`
- `byte[]`
- `char[]`
- `short[]`
- `int[]`
- `long[]`
- `float[]`
- `double[]`

Ngoài ra còn có overload cho mảng object `T[]`. Các overload không có range so sánh toàn bộ hai mảng.

Ví dụ với mảng byte:

~~~java
byte[] packetA = {0x10, 0x20, 0x30};
byte[] packetB = {0x10, 0x21, 0x30};

int index = Arrays.mismatch(packetA, packetB);
System.out.println(index); // 1
~~~

Với primitive array, việc so sánh dựa trên giá trị của phần tử theo kiểu tương ứng. Không cần boxing từng phần tử thành object.

## 3. So sánh mảng object

Với `T[]`, overload mặc định so sánh các cặp phần tử bằng `Objects.equals(elementA, elementB)`. Vì vậy:

- Hai tham chiếu `null` tại cùng vị trí được xem là bằng nhau.
- `null` và một object khác `null` được xem là khác nhau.
- Hai object khác instance vẫn có thể bằng nhau nếu `equals()` của chúng trả về `true`.
- Với class tự định nghĩa, kết quả phụ thuộc vào hợp đồng `equals()` của class đó.

Ví dụ:

~~~java
String[] first = {"Java", "Stream", "Array"};
String[] second = {"Java", "stream", "Array"};

System.out.println(Arrays.mismatch(first, second)); // 1
~~~

`String.equals()` phân biệt chữ hoa và chữ thường, vì vậy `"Stream"` khác `"stream"` tại vị trí `1`.

### 3.1. Dùng `Comparator` để tùy chỉnh phép so sánh

Java 9 có overload nhận `Comparator<? super T>`. Hai phần tử được xem là khớp khi comparator trả về `0` cho cặp phần tử đó. Nếu comparator trả về giá trị khác `0`, vị trí tương ứng là mismatch.

~~~java
String[] first = {"Java", "Stream", "Array"};
String[] second = {"Java", "stream", "Array"};

int index = Arrays.mismatch(first, second, String.CASE_INSENSITIVE_ORDER);
System.out.println(index); // -1
~~~

Trong ví dụ, comparator không phân biệt chữ hoa và chữ thường nên các phần tử ở cả ba vị trí được xem là tương đương.

Comparator phải mô tả đúng quy tắc nghiệp vụ. Nếu mảng có thể chứa `null`, comparator cần được thiết kế để xử lý `null`; một comparator không hỗ trợ `null` có thể ném `NullPointerException` khi được gọi.

### 3.2. Equality của phần tử lồng nhau

Overload object array so sánh từng phần tử bằng `Objects.equals()`, không tự thực hiện deep comparison cho mảng lồng nhau. Bản thân array trong Java không ghi đè `equals()`, nên hai array lồng nhau khác instance thường không bằng nhau theo phép so sánh mặc định dù nội dung bên trong giống nhau.

Nếu phần tử là mảng lồng nhau, cần xác định rõ yêu cầu: so sánh identity, equality của object, hay so sánh sâu nội dung. `Arrays.mismatch()` mặc định không tự biến phép so sánh thành deep equality.

## 4. So sánh một đoạn con bằng range overload

Ngoài overload so sánh toàn bộ mảng, `Arrays.mismatch()` có overload nhận cặp giới hạn cho từng mảng:

~~~java
Arrays.mismatch(a, aFromIndex, aToIndex, b, bFromIndex, bToIndex)
~~~

Các khoảng chỉ số tuân theo quy ước **đóng ở đầu, mở ở cuối**: `fromIndex` được tính vào, `toIndex` không được tính vào. Độ dài đoạn là `toIndex - fromIndex`.

Range overload trả về **chỉ số tương đối trong đoạn đang so sánh**, không phải chỉ số tuyệt đối trong mảng ban đầu.

Ví dụ:

~~~java
String[] first = {"skip", "red", "green", "blue", "tail"};
String[] second = {"ignore", "red", "Green", "blue", "ignore"};

int relativeIndex = Arrays.mismatch(first, 1, 4, second, 1, 4);
System.out.println(relativeIndex); // 1
~~~

Đoạn được so sánh là các vị trí `1`, `2`, `3` của mỗi mảng. Trong đoạn đó, `red` khớp ở vị trí tương đối `0`; `green` và `Green` khác nhau ở vị trí tương đối `1`.

Muốn quy đổi về chỉ số tuyệt đối của mảng thứ nhất, cộng kết quả với `aFromIndex` khi kết quả không phải `-1`:

~~~java
int absoluteIndex = relativeIndex == -1 ? -1 : 1 + relativeIndex;
System.out.println(absoluteIndex); // 2
~~~

### 4.1. Range overload với comparator

Với mảng object, có thể kết hợp range overload và comparator:

~~~java
int relativeIndex = Arrays.mismatch(
    first, 1, 4, second, 1, 4, String.CASE_INSENSITIVE_ORDER
);
System.out.println(relativeIndex); // -1
~~~

Trong đoạn được chọn, `red`, `green` và `blue` bằng nhau nếu không phân biệt hoa thường, nên kết quả là `-1`.

### 4.2. Kiểm tra giới hạn đoạn

Range overload kiểm tra giới hạn của từng mảng:

- `fromIndex` âm hoặc `toIndex` vượt quá độ dài mảng sẽ gây `ArrayIndexOutOfBoundsException`.
- `fromIndex > toIndex` sẽ gây `IllegalArgumentException`.
- Truyền mảng `null` sẽ gây `NullPointerException`.

Không dùng range overload nếu chưa xác thực offset và length từ dữ liệu bên ngoài. Với offset/length, nên kiểm tra điều kiện trước khi tính `toIndex` để tránh tràn số nguyên.

## 5. Các trường hợp cần chú ý với `float` và `double`

Overload cho `float[]` và `double[]` có quy tắc tương đương cách Java biểu diễn equality của floating-point trong các phép so sánh mảng:

- `+0.0` và `-0.0` được xem là khác nhau.
- Các giá trị NaN được chuẩn hóa khi so sánh bit, vì vậy các NaN có payload khác nhau vẫn được xem là bằng nhau.
- Hai giá trị hữu hạn được so sánh theo biểu diễn giá trị của kiểu tương ứng.

Ví dụ:

~~~java
System.out.println(Arrays.mismatch(
    new double[] {0.0}, new double[] {-0.0}
)); // 0

double anotherNaN = Double.longBitsToDouble(0x7ff8000000000001L);
System.out.println(Arrays.mismatch(
    new double[] {Double.NaN}, new double[] {anotherNaN}
)); // -1
~~~

Điểm này quan trọng khi dữ liệu có thể chứa số không có dấu hoặc NaN. Nếu miền nghiệp vụ cần quy tắc khác, hãy chuẩn hóa dữ liệu hoặc dùng phép so sánh tùy chỉnh phù hợp.

## 6. Ứng dụng thực tế

### 6.1. Tìm byte đầu tiên khác nhau

Khi so sánh hai buffer đã chuyển thành `byte[]`, `mismatch()` trả về vị trí đầu tiên khác nhau. Vị trí đó có thể dùng để khoanh vùng dữ liệu đầu vào hoặc output bị lệch.

~~~java
byte[] received = {0x01, 0x02, 0x7F, 0x04};
byte[] expected = {0x01, 0x02, 0x70, 0x04};

int mismatch = Arrays.mismatch(expected, received);
if (mismatch >= 0) {
    System.out.println("Different byte at index " + mismatch);
}
~~~

### 6.2. So sánh kết quả kiểm thử

Khi test một thuật toán tạo mảng, `mismatch()` giúp chỉ ra vị trí sai đầu tiên thay vì chỉ báo hai mảng không bằng nhau. Có thể dùng kết quả để tạo thông báo lỗi có ngữ cảnh:

~~~java
int index = Arrays.mismatch(expected, actual);
if (index >= 0) {
    throw new AssertionError(
        "Mismatch at " + index + ": expected=" + expected[index]
            + ", actual=" + actual[index]
    );
}
~~~

Đoạn mã trên giả định hai mảng có cùng kiểu và `index` là chỉ số hợp lệ trong cả hai mảng khi mismatch nằm trong phần tử chung. Nếu kết quả bằng độ dài mảng ngắn hơn, khác biệt là do độ dài; cần kiểm tra độ dài trước khi truy cập phần tử tại chỉ số đó.

## 7. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ này minh họa mảng primitive, mảng object, comparator và range overload. Kết quả không phụ thuộc identity của các array.

**Tệp:** `ArraysMismatchDemo.java`

~~~java
import java.util.Arrays;
import java.util.Comparator;

public class ArraysMismatchDemo {
    public static void main(String[] args) {
        int[] expected = {2, 4, 6, 8, 10};
        int[] actual = {2, 4, 7, 8, 10};
        System.out.println(Arrays.mismatch(expected, actual));

        int[] same = {2, 4, 6, 8, 10};
        System.out.println(Arrays.mismatch(expected, same));

        int[] prefix = {2, 4};
        System.out.println(Arrays.mismatch(prefix, expected));

        String[] first = {"Java", "Stream", "Array"};
        String[] second = {"Java", "stream", "Array"};
        System.out.println(Arrays.mismatch(first, second));
        System.out.println(Arrays.mismatch(first, second, String.CASE_INSENSITIVE_ORDER));

        String[] rangeFirst = {"skip", "red", "green", "blue", "tail"};
        String[] rangeSecond = {"ignore", "red", "Green", "blue", "ignore"};
        System.out.println(Arrays.mismatch(rangeFirst, 1, 4, rangeSecond, 1, 4));
        System.out.println(Arrays.mismatch(
            rangeFirst, 1, 4, rangeSecond, 1, 4, String.CASE_INSENSITIVE_ORDER
        ));
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~text
javac --release 9 ArraysMismatchDemo.java
java ArraysMismatchDemo
~~~

Output:

~~~text
2
-1
2
1
-1
1
-1
~~~

Giải thích theo thứ tự:

1. Hai mảng `int` đầu tiên khác nhau ở vị trí `2`.
2. Hai mảng `expected` và `same` bằng nhau nên kết quả `-1`.
3. Mảng `{2, 4}` là tiền tố của `expected`, vì vậy mismatch là `2`, tức độ dài mảng ngắn hơn.
4. Hai mảng String khác nhau theo phép so sánh mặc định ở vị trí `1`.
5. Comparator không phân biệt hoa thường xem hai mảng String bằng nhau nên kết quả `-1`.
6. Range overload mặc định trả về vị trí tương đối `1` trong đoạn.
7. Range overload có comparator xem các phần tử trong đoạn tương đương nên trả về `-1`.

## 8. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nghĩ `-1` nghĩa là không có phần tử khác trong phần chung dù độ dài khác | Một mảng có thể là tiền tố của mảng kia | Nhớ rằng kết quả khi khác độ dài là độ dài mảng ngắn hơn |
| Dùng kết quả range như chỉ số tuyệt đối | Range overload trả chỉ số tương đối | Cộng `aFromIndex` khi cần chỉ số tuyệt đối trong mảng đầu tiên |
| Nhầm `mismatch()` với `compare()` | Một phương thức trả vị trí khác biệt, phương thức kia trả kết quả thứ tự | Dùng `mismatch()` để tìm vị trí; dùng `compare()` khi cần biết mảng nào đứng trước |
| So sánh object mà không kiểm tra `equals()` | Overload mặc định dùng equality của phần tử | Cài đặt `equals()` phù hợp hoặc truyền comparator |
| Mong đợi so sánh sâu cho array lồng nhau | Object array dùng `Objects.equals()` trên từng phần tử | Xác định rõ quy tắc deep comparison và xử lý riêng |
| Truyền comparator không xử lý `null` | Comparator có thể được gọi với phần tử `null` | Dùng comparator null-safe nếu dữ liệu có null |
| Đọc phần tử tại index trả về khi mảng ngắn hơn | Index có thể bằng độ dài mảng ngắn | Kiểm tra độ dài trước khi truy cập phần tử |
| Range có offset hoặc length sai | Giới hạn đoạn không hợp lệ | Kiểm tra `fromIndex`, `toIndex` và độ dài trước khi gọi |

## 9. Quy tắc thực hành

1. Dùng `Arrays.mismatch()` khi cần vị trí khác biệt đầu tiên giữa hai mảng.
2. Hiểu `-1` là hai mảng cùng độ dài và các phần tử tương ứng đều khớp.
3. Nếu một mảng là tiền tố của mảng kia, kết quả là độ dài của mảng ngắn hơn.
4. Với object array, kiểm tra hợp đồng `equals()` hoặc truyền `Comparator` theo yêu cầu nghiệp vụ.
5. Với range overload, nhớ kết quả là chỉ số tương đối trong đoạn được chọn.
6. Kiểm tra giới hạn range và xử lý trường hợp mảng null.
7. Chú ý quy tắc `+0.0`, `-0.0` và NaN khi so sánh `float[]` hoặc `double[]`.
8. Khi cần chỉ biết hai mảng có bằng nhau hay không, chọn `Arrays.equals()` để thể hiện ý định rõ ràng.

## 10. Tự kiểm tra

- `Arrays.mismatch()` trả về gì khi hai mảng bằng nhau hoàn toàn? `-1`.
- Nếu hai mảng khớp ở ba phần tử đầu nhưng khác ở phần tử thứ tư, kết quả là gì? `3`, vì chỉ số bắt đầu từ `0`.
- Nếu mảng ngắn hơn là tiền tố của mảng dài hơn, kết quả là gì? Độ dài của mảng ngắn hơn.
- Overload object array mặc định dùng quy tắc so sánh nào? `Objects.equals()` cho từng cặp phần tử.
- Khi truyền comparator, cặp phần tử được xem là khớp khi nào? Khi `comparator.compare(a, b)` trả về `0`.
- Range overload trả chỉ số tương đối hay tuyệt đối? Tương đối với đầu đoạn được so sánh.
- `+0.0` và `-0.0` có được xem là bằng nhau trong `double[]` không? Không, chúng tạo mismatch.
- Các NaN có payload khác nhau có tạo mismatch không? Không, các giá trị NaN được chuẩn hóa khi so sánh.

Điểm cốt lõi: **`Arrays.mismatch()` trả về vị trí đầu tiên mà hai mảng khác nhau, hoặc `-1` nếu chúng bằng nhau hoàn toàn.** Với range overload, kết quả là offset tương đối; với object array, comparator cho phép định nghĩa equality theo quy tắc nghiệp vụ.