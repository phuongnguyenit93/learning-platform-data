# So sánh toàn mảng hoặc hai đoạn chỉ định trong Java

Java cung cấp các phương thức tĩnh trong `java.util.Arrays` để so sánh nội dung mảng. Từ Java 9, các nhóm API `equals`, `compare` và `mismatch` có thêm overload nhận chỉ số đầu và cuối của hai đoạn mảng. Nhờ đó, có thể so sánh hai vùng dữ liệu trực tiếp mà không cần tạo mảng con bằng `copyOfRange`.

Ba thao tác có mục đích khác nhau:

- `Arrays.equals(...)`: kiểm tra hai mảng hoặc hai đoạn có nội dung bằng nhau hay không.
- `Arrays.compare(...)`: so sánh theo thứ tự từ điển (lexicographic), trả về số âm, 0 hoặc số dương.
- `Arrays.mismatch(...)`: tìm vị trí đầu tiên mà hai mảng hoặc hai đoạn khác nhau; trả về -1 nếu không có khác biệt.

Chọn đúng thao tác phụ thuộc vào câu hỏi cần trả lời: chỉ cần biết bằng nhau, cần xác định mảng nào đứng trước, hay cần tìm vị trí dữ liệu bắt đầu khác nhau.

## 1. So sánh tham chiếu và so sánh nội dung

Toán tử `==` với mảng kiểm tra hai biến có tham chiếu đến cùng một đối tượng hay không. Nó không duyệt phần tử:

~~~java
int[] first = {1, 2, 3};
int[] second = {1, 2, 3};

System.out.println(first == second); // false
~~~

Hai mảng có nội dung giống nhau nhưng là hai đối tượng khác nhau nên `==` trả về false.

Dùng `Arrays.equals` để so sánh nội dung:

~~~java
System.out.println(Arrays.equals(first, second)); // true
~~~

Không dùng `first.equals(second)` để so sánh phần tử. Mảng kế thừa `equals` từ Object, nên lời gọi đó cũng so sánh định danh đối tượng như `==`.

## 2. Arrays.equals: so sánh toàn bộ mảng

Dạng tổng quát:

~~~java
Arrays.equals(array1, array2)
~~~

API có overload cho từng loại mảng nguyên thủy như `byte[]`, `short[]`, `int[]`, `long[]`, `char[]`, `boolean[]`, `float[]`, `double[]`, cũng như mảng đối tượng.

Hai mảng được xem là bằng nhau khi:

1. Cả hai cùng null; hoặc
2. Cả hai đều khác null, có cùng độ dài và các phần tử tương ứng bằng nhau theo quy tắc của overload được gọi.

Nếu một mảng null còn mảng kia không null, kết quả là false. Hai mảng rỗng cùng kiểu có nội dung bằng nhau.

Ví dụ với mảng số nguyên:

~~~java
int[] a = {10, 20, 30};
int[] b = {10, 20, 30};
int[] c = {10, 20};

System.out.println(Arrays.equals(a, b)); // true
System.out.println(Arrays.equals(a, c)); // false
~~~

Với mảng đối tượng, phép so sánh được thực hiện theo từng cặp phần tử bằng quy tắc tương đương `Objects.equals`: hai phần tử null được xem là bằng nhau; một phần tử null và một phần tử khác null không bằng nhau; các phần tử khác null được so sánh bằng `equals`.

~~~java
String[] x = {"Java", null, "Stream"};
String[] y = {"Java", null, "Stream"};

System.out.println(Arrays.equals(x, y)); // true
~~~

Nếu lớp phần tử tự định nghĩa `equals`, kết quả phụ thuộc vào cách lớp đó định nghĩa equality. Nếu lớp chỉ kế thừa `Object.equals`, hai đối tượng khác nhau vẫn không bằng nhau dù các trường dữ liệu của chúng giống nhau.

### So sánh mảng đối tượng theo Comparator

Java cũng cung cấp overload nhận Comparator:

~~~java
String[] first = {"Java", "Stream"};
String[] second = {"java", "STREAM"};

boolean sameIgnoringCase = Arrays.equals(
    first,
    second,
    String.CASE_INSENSITIVE_ORDER
);
~~~

Comparator quyết định khi nào hai phần tử được xem là tương đương trong phép so sánh này. Nếu Comparator trả về 0 cho từng cặp phần tử tương ứng, hai mảng được xem là bằng nhau theo Comparator, kể cả khi `String.equals` trả về false.

Chỉ dùng Comparator có quy tắc nhất quán với ý nghĩa equality mà ứng dụng cần. Không giả định rằng kết quả này giống `Arrays.equals(first, second)` không có Comparator.

## 3. So sánh hai đoạn mảng bằng range overload

Từ Java 9, có thể so sánh hai đoạn được chỉ định trực tiếp:

~~~java
Arrays.equals(
    array1, fromIndex1, toIndex1,
    array2, fromIndex2, toIndex2
)
~~~

Mỗi đoạn dùng quy ước:

- `fromIndex` là chỉ số bắt đầu, được tính vào đoạn.
- `toIndex` là chỉ số kết thúc, không được tính vào đoạn.
- Độ dài đoạn bằng `toIndex - fromIndex`.

Ví dụ:

~~~java
int[] left = {9, 1, 2, 3, 8};
int[] right = {7, 1, 2, 3, 0};

boolean sameMiddle = Arrays.equals(
    left, 1, 4,
    right, 1, 4
);

System.out.println(sameMiddle); // true
~~~

Hai đoạn được chọn đều chứa các phần tử `[1, 2, 3]`, nên kết quả là true, dù toàn bộ hai mảng khác nhau.

Nếu hai đoạn có độ dài khác nhau, `Arrays.equals` trả về false. Không cần tự tạo mảng con:

~~~java
// Cách trực tiếp: không tạo mảng tạm
boolean equal = Arrays.equals(left, 1, 4, right, 1, 4);

// Có thể làm bằng cách sao chép, nhưng tạo thêm mảng
boolean equalByCopies = Arrays.equals(
    Arrays.copyOfRange(left, 1, 4),
    Arrays.copyOfRange(right, 1, 4)
);
~~~

Range overload thường phù hợp hơn khi chỉ cần so sánh một vùng, đặc biệt với mảng lớn hoặc khi muốn tránh cấp phát các mảng tạm.

Các overload range cũng có biến thể nhận Comparator cho mảng đối tượng:

~~~java
boolean sameIgnoringCase = Arrays.equals(
    first, 0, first.length,
    second, 0, second.length,
    String.CASE_INSENSITIVE_ORDER
);
~~~

## 4. Arrays.compare: so sánh theo thứ tự từ điển

`Arrays.compare(a, b)` so sánh lần lượt các phần tử từ đầu mảng. Kết quả là:

- Số âm nếu mảng thứ nhất đứng trước mảng thứ hai.
- 0 nếu hai mảng bằng nhau theo quy tắc so sánh.
- Số dương nếu mảng thứ nhất đứng sau mảng thứ hai.

Không nên phụ thuộc vào giá trị số cụ thể như -1 hoặc 1. Hợp đồng chỉ yêu cầu dấu âm, bằng 0 hoặc dấu dương.

Ví dụ:

~~~java
int[] a = {1, 4, 7};
int[] b = {1, 5, 0};

System.out.println(Arrays.compare(a, b) < 0); // true
~~~

Hai mảng có cùng phần tử đầu là 1. Ở vị trí tiếp theo, 4 nhỏ hơn 5, nên mảng a đứng trước b. Phần tử cuối không cần xét nữa.

### Quy tắc khi một mảng là tiền tố của mảng kia

Nếu mọi phần tử trong đoạn ngắn hơn đều bằng phần tử tương ứng của đoạn dài hơn, đoạn ngắn hơn được xem là nhỏ hơn:

~~~java
int[] shortArray = {1, 2};
int[] longArray = {1, 2, 0};

System.out.println(Arrays.compare(shortArray, longArray) < 0); // true
~~~

Mặc dù hai phần tử đầu giống nhau, mảng ngắn hơn đứng trước mảng dài hơn.

### So sánh hai đoạn bằng Arrays.compare

Từ Java 9, có thể truyền phạm vi của cả hai mảng:

~~~java
int result = Arrays.compare(
    left, 1, 4,
    right, 1, 4
);
~~~

Nếu hai đoạn bằng nhau, kết quả là 0. Nếu khác nhau, thứ tự được quyết định bởi phần tử khác nhau đầu tiên; nếu một đoạn là tiền tố của đoạn kia thì độ dài quyết định kết quả.

Với mảng đối tượng, overload không có Comparator yêu cầu các phần tử triển khai `Comparable`. Có thể truyền Comparator để chọn thứ tự riêng:

~~~java
String[] first = {"Alpha", "beta"};
String[] second = {"alpha", "BETA"};

int result = Arrays.compare(
    first,
    second,
    String.CASE_INSENSITIVE_ORDER
);
~~~

Kết quả bằng 0 vì Comparator bỏ qua khác biệt chữ hoa/chữ thường.

## 5. Arrays.mismatch: tìm vị trí đầu tiên khác nhau

`Arrays.mismatch(a, b)` trả về chỉ số của phần tử đầu tiên mà hai mảng không bằng nhau:

- Trả về chỉ số từ 0 nếu khác nhau ngay phần tử đầu.
- Trả về chỉ số khác nếu có phần đầu giống nhau.
- Trả về -1 nếu hai mảng bằng nhau.
- Nếu phần chung giống nhau nhưng độ dài khác nhau, trả về độ dài của đoạn ngắn hơn.

Ví dụ:

~~~java
int[] a = {4, 7, 8, 9};
int[] b = {4, 7, 3, 9};

System.out.println(Arrays.mismatch(a, b)); // 2
~~~

Hai mảng khác nhau lần đầu ở chỉ số 2.

### mismatch với hai đoạn chỉ định

Range overload cũng có từ Java 9:

~~~java
int mismatch = Arrays.mismatch(
    left, 1, 4,
    changed, 1, 4
);
~~~

Giá trị trả về là chỉ số tương đối tính từ đầu đoạn, không phải chỉ số tuyệt đối của mảng gốc. Nếu kết quả là 1, phần tử khác nhau nằm ở vị trí `fromIndex + 1` trong mỗi mảng.

Ví dụ, đoạn bắt đầu ở chỉ số 1 và mismatch trả về 1 thì vị trí tuyệt đối là 2.

Với hai đoạn có phần đầu giống nhau nhưng độ dài khác nhau, mismatch trả về độ dài của đoạn ngắn hơn. Với hai đoạn hoàn toàn bằng nhau, kết quả là -1.

### mismatch kết hợp với equals và compare

Ba phương thức bổ sung cho nhau:

- Cần câu trả lời đúng/sai: dùng `equals`.
- Cần thứ tự để sắp xếp hoặc so sánh thứ tự từ điển: dùng `compare`.
- Cần vị trí dữ liệu khác nhau để chẩn đoán: dùng `mismatch`.

Không cần tự viết vòng lặp để tìm phần tử khác đầu tiên nếu API mismatch đã đáp ứng yêu cầu.

## 6. So sánh không dấu với compareUnsigned

Với dữ liệu nhị phân, byte trong Java là kiểu có dấu, có miền giá trị từ -128 đến 127. Nhưng nhiều định dạng byte lưu giá trị theo miền không dấu từ 0 đến 255.

`Arrays.compareUnsigned` so sánh các phần tử byte, short, int hoặc long như các giá trị không dấu. Điều này quan trọng khi so sánh dữ liệu nhị phân, mã hóa hoặc số nguyên được lưu theo biểu diễn unsigned.

~~~java
byte[] high = {(byte) 0xFF};
byte[] zero = {0};

System.out.println(Arrays.compare(high, zero) < 0);         // true
System.out.println(Arrays.compareUnsigned(high, zero) > 0); // true
~~~

Với so sánh có dấu, byte `0xFF` có giá trị -1 nên nhỏ hơn 0. Với so sánh không dấu, cùng byte đó biểu diễn 255 nên lớn hơn 0.

Range overload cũng có sẵn:

~~~java
int order = Arrays.compareUnsigned(
    firstBytes, start1, end1,
    secondBytes, start2, end2
);
~~~

Không dùng compareUnsigned cho mọi mảng số. Chỉ dùng khi ý nghĩa dữ liệu là số không dấu; với số nguyên Java thông thường, dùng `compare`.

## 7. Mảng lồng nhau: equals và deepEquals

Mảng hai chiều trong Java thực chất là mảng chứa các mảng khác. Vì vậy, `Arrays.equals` trên mảng ngoài chỉ so sánh từng phần tử theo `equals` của phần tử đó. Với phần tử là mảng con, `equals` kế thừa từ Object nên so sánh tham chiếu.

~~~java
int[][] first = {{1, 2}, {3}};
int[][] second = {{1, 2}, {3}};

System.out.println(Arrays.equals(first, second));     // false
System.out.println(Arrays.deepEquals(first, second)); // true
~~~

Hai mảng ngoài chứa các mảng con khác đối tượng, nên so sánh nông trả về false. `Arrays.deepEquals` đi sâu vào các mảng lồng nhau và so sánh nội dung tương ứng.

Với hash code cũng cần chọn đúng cặp:

- `Arrays.equals` đi cùng `Arrays.hashCode`.
- `Arrays.deepEquals` đi cùng `Arrays.deepHashCode`.

Nếu dùng mảng làm khóa trong cấu trúc dựa trên equality, phải đảm bảo cách tính equals và hashCode nhất quán. Mảng không tự triển khai equality theo nội dung cho mục đích đó.

## 8. Các trường hợp đặc biệt với float và double

So sánh mảng `float[]` và `double[]` có quy tắc riêng. Với `Arrays.equals`, phần tử được so sánh theo quy tắc tương ứng với `Float.floatToIntBits` hoặc `Double.doubleToLongBits`:

- NaN được chuẩn hóa khi so sánh bit, vì vậy một NaN so sánh bằng một NaN khác.
- `+0.0` và `-0.0` được phân biệt, nên không bằng nhau trong phép so sánh mảng này.

Ví dụ:

~~~java
System.out.println(Arrays.equals(
    new float[] {Float.NaN},
    new float[] {Float.NaN}
)); // true

System.out.println(Arrays.equals(
    new float[] {0.0f},
    new float[] {-0.0f}
)); // false
~~~

`Arrays.compare` dùng quy tắc thứ tự tương ứng của Float/Double. Nếu nghiệp vụ cần một quy tắc gần đúng với sai số cho số thực, các phương thức Arrays không tự áp dụng epsilon; cần viết Comparator hoặc hàm kiểm tra theo ngưỡng phù hợp.

## 9. Kiểm tra chỉ số và biên của đoạn

Các range overload dùng khoảng nửa mở `[fromIndex, toIndex)`. Ví dụ `fromIndex = 2`, `toIndex = 5` sẽ lấy các chỉ số 2, 3, 4.

Khi truyền phạm vi không hợp lệ:

- `fromIndex > toIndex` gây IllegalArgumentException.
- Chỉ số âm hoặc `toIndex` vượt quá độ dài mảng gây lỗi chỉ số ngoài phạm vi (IndexOutOfBoundsException hoặc kiểu con cụ thể theo API).

Nên kiểm tra rõ ràng giá trị bắt đầu/kết thúc nếu chúng đến từ dữ liệu bên ngoài. Không được nhầm `toIndex` là chỉ số cuối cùng được lấy.

Ví dụ với mảng có độ dài 5:

| fromIndex | toIndex | Phần tử được lấy |
|---:|---:|---|
| 0 | 5 | Chỉ số 0, 1, 2, 3, 4 |
| 1 | 4 | Chỉ số 1, 2, 3 |
| 2 | 2 | Đoạn rỗng |
| 3 | 2 | Không hợp lệ vì điểm bắt đầu lớn hơn điểm kết thúc |

Hai đoạn rỗng có cùng độ dài và không có phần tử nên được xem là bằng nhau khi cả hai phạm vi đều hợp lệ.

## 10. Ví dụ Java chạy được

Ví dụ sau minh họa so sánh toàn mảng, so sánh đoạn, tìm mismatch, thứ tự lexicographic, unsigned, Comparator, mảng lồng nhau và quy tắc số thực.

~~~java
import java.util.Arrays;

public class ArrayComparisonExamples {
    public static void main(String[] args) {
        int[] left = {9, 1, 2, 3, 8};
        int[] sameSlice = {7, 1, 2, 3, 0};
        int[] changedSlice = {7, 1, 9, 3, 0};

        System.out.println("whole equals=" + Arrays.equals(left, sameSlice));
        System.out.println("slice equals="
            + Arrays.equals(left, 1, 4, sameSlice, 1, 4));
        System.out.println("slice compare="
            + Arrays.compare(left, 1, 4, sameSlice, 1, 4));
        System.out.println("slice mismatch="
            + Arrays.mismatch(left, 1, 4, changedSlice, 1, 4));
        System.out.println("slice compare changed="
            + Arrays.compare(left, 1, 4, changedSlice, 1, 4));

        int[] prefix = {1, 2};
        int[] longer = {1, 2, 0};
        System.out.println("prefix mismatch="
            + Arrays.mismatch(prefix, longer));
        System.out.println("prefix compare="
            + Arrays.compare(prefix, longer));

        byte[] signed = {(byte) 0xFF};
        byte[] zero = {0};
        System.out.println("signed compare="
            + Arrays.compare(signed, zero));
        System.out.println("unsigned compare="
            + Arrays.compareUnsigned(signed, zero));

        String[] words1 = {"Alpha", "beta"};
        String[] words2 = {"alpha", "BETA"};
        System.out.println("case-insensitive equals="
            + Arrays.equals(words1, words2, String.CASE_INSENSITIVE_ORDER));
        System.out.println("case-insensitive compare="
            + Arrays.compare(words1, words2, String.CASE_INSENSITIVE_ORDER));

        String[][] matrix1 = {{"A", "B"}, {"C"}};
        String[][] matrix2 = {{"A", "B"}, {"C"}};
        System.out.println("nested shallow equals="
            + Arrays.equals(matrix1, matrix2));
        System.out.println("nested deep equals="
            + Arrays.deepEquals(matrix1, matrix2));

        float[] floats1 = {Float.NaN, 0.0f};
        float[] floats2 = {Float.NaN, -0.0f};
        System.out.println("NaN equals NaN="
            + Arrays.equals(new float[] {Float.NaN}, new float[] {Float.NaN}));
        System.out.println("positive zero equals negative zero="
            + Arrays.equals(new float[] {0.0f}, new float[] {-0.0f}));
        System.out.println("float arrays equal=" + Arrays.equals(floats1, floats2));
    }
}
~~~

Lưu trong tệp `ArrayComparisonExamples.java`, sau đó biên dịch và chạy bằng Java 17 trở lên:

~~~shell
javac --release 17 -Xlint:all ArrayComparisonExamples.java
java ArrayComparisonExamples
~~~

Kết quả stdout chính xác:

~~~text
whole equals=false
slice equals=true
slice compare=0
slice mismatch=1
slice compare changed=-1
prefix mismatch=2
prefix compare=-1
signed compare=-1
unsigned compare=255
case-insensitive equals=true
case-insensitive compare=0
nested shallow equals=false
nested deep equals=true
NaN equals NaN=true
positive zero equals negative zero=false
float arrays equal=false
~~~

Giải thích kết quả:

1. Hai mảng đầy đủ khác nhau, nhưng hai đoạn từ chỉ số 1 đến trước chỉ số 4 bằng nhau.
2. `compare` trả 0 cho hai đoạn bằng nhau; khi phần tử thứ hai trong đoạn khác nhau, kết quả âm vì 2 nhỏ hơn 9.
3. `mismatch` trả 1, nghĩa là khác biệt nằm ở vị trí tương đối thứ hai trong đoạn, tương ứng chỉ số 2 của mảng gốc.
4. Hai mảng `[1, 2]` và `[1, 2, 0]` có phần chung bằng nhau, nên mismatch trả về 2 và compare cho biết mảng ngắn hơn đứng trước.
5. Byte `0xFF` có giá trị có dấu -1 nhưng giá trị không dấu 255.
6. Comparator không phân biệt chữ hoa/chữ thường nên hai mảng String được xem là bằng nhau theo Comparator.
7. `deepEquals` so sánh nội dung mảng con; `equals` chỉ so sánh tham chiếu của các mảng con.
8. NaN bằng NaN theo quy tắc Arrays.equals; +0.0 khác -0.0.

## 11. Chọn API theo mục đích

| Mục đích | API |
|---|---|
| Kiểm tra toàn bộ hai mảng bằng nhau | `Arrays.equals(a, b)` |
| Kiểm tra hai đoạn bằng nhau | `Arrays.equals(a, fromA, toA, b, fromB, toB)` |
| So sánh thứ tự từ điển toàn mảng | `Arrays.compare(a, b)` |
| So sánh thứ tự từ điển hai đoạn | `Arrays.compare(a, fromA, toA, b, fromB, toB)` |
| Tìm vị trí khác đầu tiên | `Arrays.mismatch(a, b)` |
| Tìm mismatch trong hai đoạn | `Arrays.mismatch(a, fromA, toA, b, fromB, toB)` |
| So sánh số nguyên theo unsigned | `Arrays.compareUnsigned(a, b)` |
| So sánh mảng lồng nhau | `Arrays.deepEquals(a, b)` |
| So sánh phần tử theo quy tắc riêng | Overload nhận Comparator |

## 12. Những lỗi thường gặp

- **Dùng `==` hoặc `array.equals(other)` để so sánh nội dung:** các cách này so sánh định danh mảng. Dùng `Arrays.equals`.
- **Dùng `Arrays.equals` cho mảng hai chiều và mong so sánh sâu:** dùng `Arrays.deepEquals` khi cần so sánh đệ quy các mảng lồng nhau.
- **Nhầm `toIndex` là chỉ số cuối được lấy:** đây là điểm kết thúc không bao gồm trong đoạn.
- **Tạo hai mảng con chỉ để so sánh:** range overload có thể so sánh trực tiếp hai đoạn.
- **Dùng `Arrays.compare` như phép kiểm tra boolean:** kết quả âm/0/dương biểu diễn thứ tự; dùng `equals` nếu chỉ cần đúng/sai.
- **Nghĩ mismatch trả về chỉ số tuyệt đối khi dùng range overload:** kết quả là chỉ số tương đối tính từ đầu đoạn.
- **Giả định compare luôn trả về -1 hoặc 1:** chỉ dựa vào dấu âm, bằng 0 hoặc dương.
- **Dùng compare có dấu cho dữ liệu byte unsigned:** cân nhắc `compareUnsigned` khi dữ liệu mang ý nghĩa không dấu.
- **Giả định +0.0 bằng -0.0 trong Arrays.equals:** hai giá trị này được phân biệt; NaN được chuẩn hóa theo quy tắc bit của Float/Double.
- **Dùng equals khi cần thứ tự tùy chỉnh:** dùng overload nhận Comparator của `equals` hoặc `compare`, tùy mục đích.

## 13. Tài liệu tham khảo chính thức

- [Arrays — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html): hợp đồng của `equals`, `compare`, `compareUnsigned`, `mismatch`, `deepEquals` và các overload theo đoạn.
- [Comparator — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html): quy tắc tạo thứ tự tùy chỉnh cho mảng đối tượng.
- [Object.equals — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): hợp đồng equality mặc định dựa trên định danh đối tượng.
- [Java Language Specification — Expressions, Java SE 26](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html): quy tắc biểu thức và truy cập phần tử mảng trong Java.