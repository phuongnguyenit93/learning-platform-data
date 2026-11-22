# Quy tắc khi một mảng là tiền tố của mảng kia

Khi so sánh hai mảng theo thứ tự từ điển (lexicographic order), Java lần lượt so sánh các phần tử ở cùng vị trí từ đầu đến cuối. Nếu tất cả phần tử trong phần chung đều bằng nhau và một mảng kết thúc trước, **mảng ngắn hơn được xem là nhỏ hơn**. Đây là quy tắc quyết định khi một mảng là tiền tố của mảng kia.

Từ Java 9, có thể dùng **Arrays.compare()** để so sánh hai mảng theo quy tắc này. Phương thức hỗ trợ mảng primitive và mảng object, đồng thời có overload nhận Comparator để tùy chỉnh thứ tự của phần tử.

## 1. Thế nào là một mảng tiền tố của mảng kia?

Mảng A là tiền tố của mảng B khi:

- A không dài hơn B.
- Mọi phần tử của A đều bằng phần tử ở cùng chỉ số trong B.
- A kết thúc trước hoặc cùng lúc với B.

Ví dụ:

~~~text
A = [2, 4]
B = [2, 4, 6]
~~~

Hai phần tử chung ở vị trí 0 và 1 bằng nhau. A kết thúc trước khi B có phần tử thứ ba, vì vậy A là tiền tố thực sự của B.

Theo thứ tự từ điển:

~~~text
[2, 4] < [2, 4, 6]
[2, 4, 6] > [2, 4]
~~~

Nếu hai mảng có cùng độ dài và mọi phần tử tương ứng bằng nhau, chúng được xem là bằng nhau theo phép so sánh:

~~~text
[2, 4] = [2, 4]
~~~

Một mảng rỗng là tiền tố của mọi mảng không rỗng cùng kiểu phần tử:

~~~text
[] < [1]
[] < [1, 2, 3]
~~~

## 2. Quy tắc so sánh từ trái sang phải

Khi so sánh hai mảng, thứ tự được xác định theo các bước:

1. So sánh phần tử tại chỉ số 0.
2. Nếu hai phần tử khác nhau, kết quả so sánh phần tử đó quyết định thứ tự của cả hai mảng; không cần xét các phần tử phía sau.
3. Nếu hai phần tử bằng nhau, tiếp tục với chỉ số kế tiếp.
4. Nếu đã so sánh hết phần tử của mảng ngắn hơn mà chưa tìm thấy khác biệt, so sánh độ dài hai mảng.
5. Nếu độ dài cũng bằng nhau, hai mảng bằng nhau theo thứ tự so sánh.

Ví dụ:

| Mảng A | Mảng B | Kết quả | Lý do |
|---|---|---|---|
| [1, 2] | [1, 2, 3] | A < B | A là tiền tố của B; A ngắn hơn |
| [1, 2, 3] | [1, 2] | A > B | B là tiền tố của A; B ngắn hơn |
| [1, 4] | [1, 3, 9] | A > B | Khác nhau tại chỉ số 1; 4 lớn hơn 3 |
| [1, 2] | [1, 2] | A = B | Cùng độ dài và mọi phần tử tương ứng bằng nhau |
| [] | [5] | A < B | Mảng rỗng là tiền tố và ngắn hơn |

**Lưu ý:** Quy tắc độ dài chỉ được áp dụng sau khi toàn bộ phần chung đã bằng nhau. Không được kết luận mảng ngắn hơn luôn nhỏ hơn nếu hai mảng đã khác nhau ở một vị trí trước khi mảng ngắn kết thúc.

Ví dụ [1, 9] lớn hơn [1, 5, 7], dù mảng thứ nhất ngắn hơn, vì phần tử đầu tiên khác nhau là 9 và 5 tại chỉ số 1.

## 3. Dùng Arrays.compare() từ Java 9

Phương thức Arrays.compare() được bổ sung trong Java 9. Nó trả về một số nguyên thể hiện thứ tự tương đối của hai mảng:

~~~java
int result = Arrays.compare(first, second);
~~~

Ý nghĩa của kết quả:

- Giá trị âm: mảng thứ nhất nhỏ hơn mảng thứ hai.
- Giá trị 0: hai mảng bằng nhau theo quy tắc so sánh.
- Giá trị dương: mảng thứ nhất lớn hơn mảng thứ hai.

Chỉ nên dựa vào dấu âm, 0 hoặc dương. Không nên phụ thuộc vào một giá trị âm hoặc dương cụ thể, vì độ lớn chính xác của kết quả không phải điều cần dùng để xác định thứ tự.

### Mảng primitive

Arrays.compare() có overload cho các kiểu mảng primitive như:

- byte[]
- short[]
- int[]
- long[]
- char[]
- float[]
- double[]
- boolean[]

Ví dụ:

~~~java
int[] shorter = {1, 2};
int[] longer = {1, 2, 3};

int result = Arrays.compare(shorter, longer);

if (result < 0) {
    System.out.println("shorter comes first");
}
~~~

Kết quả:

~~~text
shorter comes first
~~~

Với mảng primitive, phần tử được so sánh theo quy tắc tương ứng với kiểu dữ liệu. Với float và double, Java sử dụng quy tắc so sánh của các kiểu đó; nếu ứng dụng cần thứ tự số học đặc biệt cho NaN hoặc signed zero, hãy kiểm tra rõ yêu cầu trước khi chọn phép so sánh.

### Mảng object

Có thể so sánh các mảng object nếu phần tử có thứ tự tự nhiên, tức kiểu phần tử triển khai Comparable:

~~~java
String[] first = {"api", "stream"};
String[] second = {"api", "stream", "optional"};

int result = Arrays.compare(first, second);
~~~

String triển khai Comparable<String>, nên Java có thể dùng thứ tự tự nhiên của String. Vì hai chuỗi đầu giống nhau và mảng first kết thúc trước, kết quả âm.

Nếu phần tử không có thứ tự tự nhiên phù hợp hoặc ứng dụng cần quy tắc khác, dùng overload nhận Comparator.

## 4. Dùng Comparator để thay đổi cách so sánh phần tử

Overload có Comparator cho phép xác định cách so sánh từng cặp phần tử:

~~~java
Arrays.compare(first, second, comparator);
~~~

Comparator quyết định thứ tự của phần tử tại vị trí đang xét. Quy tắc tiền tố vẫn giữ nguyên: chỉ khi mọi cặp phần tử trong phần chung được Comparator xem là bằng nhau thì độ dài mới được dùng để phân định.

Ví dụ so sánh String không phân biệt chữ hoa và chữ thường:

~~~java
String[] first = {"Alpha", "zeta"};
String[] second = {"alpha", "beta"};

int result = Arrays.compare(
        first,
        second,
        String.CASE_INSENSITIVE_ORDER
);
~~~

Ở phần tử đầu tiên, Alpha và alpha được xem là bằng nhau theo Comparator. Ở phần tử thứ hai, zeta lớn hơn beta, vì vậy mảng first lớn hơn second.

Comparator cũng có thể xác định cách xử lý phần tử null. Nếu mảng có null, Comparator cần được thiết kế để xử lý null an toàn; không nên giả định thứ tự tự nhiên của phần tử sẽ tự xử lý được null.

## 5. Ví dụ hoàn chỉnh: so sánh tiền tố và phần tử khác nhau

Lưu chương trình dưới tên **ArrayPrefixComparisonDemo.java**. Ví dụ dùng API Arrays.compare() có từ Java 9 và biên dịch được với Java 9 trở lên.

~~~java
import java.util.Arrays;

public class ArrayPrefixComparisonDemo {
    public static void main(String[] args) {
        int[] prefix = {1, 2};
        int[] longer = {1, 2, 3};
        int[] firstDifferenceLeft = {1, 4, 9};
        int[] firstDifferenceRight = {1, 3, 9};

        System.out.println("prefix vs longer: " +
                Integer.signum(Arrays.compare(prefix, longer)));
        System.out.println("longer vs prefix: " +
                Integer.signum(Arrays.compare(longer, prefix)));
        System.out.println("first differing element: " +
                Integer.signum(Arrays.compare(firstDifferenceLeft, firstDifferenceRight)));
        System.out.println("equal arrays: " +
                Arrays.compare(new int[]{1, 2}, new int[]{1, 2}));

        String[] wordsPrefix = {"api", "stream"};
        String[] wordsLonger = {"api", "stream", "optional"};
        System.out.println("object prefix: " +
                Integer.signum(Arrays.compare(wordsPrefix, wordsLonger)));

        String[] caseLeft = {"Alpha", "zeta"};
        String[] caseRight = {"alpha", "beta"};
        System.out.println("natural object order: " +
                Integer.signum(Arrays.compare(caseLeft, caseRight)));
        System.out.println("custom comparator: " +
                Integer.signum(Arrays.compare(
                        caseLeft, caseRight, String.CASE_INSENSITIVE_ORDER)));

        System.out.println("empty vs non-empty: " +
                Integer.signum(Arrays.compare(new int[0], new int[]{1})));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 9 ArrayPrefixComparisonDemo.java
java ArrayPrefixComparisonDemo
~~~

Kết quả stdout:

~~~text
prefix vs longer: -1
longer vs prefix: 1
first differing element: 1
equal arrays: 0
object prefix: -1
natural object order: -1
custom comparator: 1
empty vs non-empty: -1
~~~

Giải thích:

- prefix vs longer là -1 vì mảng [1, 2] là tiền tố của [1, 2, 3] và ngắn hơn.
- longer vs prefix là 1 vì thứ tự so sánh được đảo lại.
- first differing element là 1 vì tại chỉ số 1, giá trị 4 lớn hơn 3; độ dài không còn là yếu tố quyết định.
- equal arrays là 0 vì hai mảng int có cùng nội dung.
- object prefix là -1 vì hai phần tử String chung bằng nhau và mảng thứ nhất kết thúc trước.
- natural object order là -1 vì String được so sánh theo thứ tự tự nhiên, có phân biệt chữ hoa/chữ thường.
- custom comparator là 1 vì Comparator bỏ qua khác biệt hoa/thường ở phần tử đầu, rồi xác định zeta lớn hơn beta ở phần tử tiếp theo.
- empty vs non-empty là -1 vì mảng rỗng ngắn hơn mảng có một phần tử.

## 6. Cách hiểu thuật toán tiền tố

Có thể hình dung quy tắc tổng quát như sau:

~~~text
So sánh từng cặp phần tử từ trái sang phải
                 |
                 v
       Có cặp phần tử khác nhau?
            /           \
          Có             Không
          |                |
          v                v
  Trả thứ tự của       So sánh độ dài
  cặp khác nhau             |
                            v
                 Mảng ngắn hơn nhỏ hơn
                 Cùng độ dài thì bằng nhau
~~~

Với mảng object, phép so sánh từng cặp phần tử được thực hiện bằng thứ tự tự nhiên hoặc Comparator được truyền vào. Với mảng primitive, Java dùng phép so sánh phù hợp với kiểu primitive.

Đây là cách hiểu để dự đoán kết quả. Trong ứng dụng, nên dùng Arrays.compare() thay vì tự viết vòng lặp nếu chỉ cần phép so sánh chuẩn.

## 7. Phân biệt Arrays.compare() và Arrays.equals()

Hai phương thức có mục đích khác nhau:

| Phương thức | Mục đích | Kết quả |
|---|---|---|
| Arrays.compare(a, b) | Xác định thứ tự từ điển giữa hai mảng | Số âm, 0 hoặc số dương |
| Arrays.equals(a, b) | Kiểm tra hai mảng có nội dung tương ứng bằng nhau không | true hoặc false |

Ví dụ:

~~~java
int[] prefix = {1, 2};
int[] longer = {1, 2, 3};

System.out.println(Arrays.equals(prefix, longer));
System.out.println(Arrays.compare(prefix, longer) < 0);
~~~

Kết quả:

~~~text
false
true
~~~

Arrays.equals() trả về false vì hai mảng khác độ dài. Arrays.compare() cung cấp thêm thông tin rằng mảng prefix đứng trước mảng longer theo thứ tự từ điển.

Arrays.compare() không thay đổi nội dung hai mảng. Nó chỉ đọc và so sánh các phần tử.

## 8. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng mảng ngắn hơn luôn nhỏ hơn | Kết luận sai khi hai mảng khác nhau trước khi mảng ngắn kết thúc | Chỉ so sánh độ dài sau khi phần chung bằng nhau |
| So sánh độ dài trước khi so sánh phần tử | Không tuân theo thứ tự từ điển | So sánh từ chỉ số 0 và dừng tại cặp đầu tiên khác nhau |
| Kiểm tra result == -1 hoặc result == 1 | Phụ thuộc vào độ lớn kết quả không được bảo đảm | Dùng result < 0, result == 0 hoặc result > 0 |
| Dùng Arrays.compare() cho object không có thứ tự tự nhiên | Không có phép so sánh phần tử phù hợp | Triển khai Comparable hoặc truyền Comparator |
| Dùng Comparator không xử lý null trong khi mảng có null | Có thể phát sinh NullPointerException | Dùng Comparator có quy tắc null rõ ràng |
| Nhầm Arrays.compare() với Arrays.equals() | Dùng phép kiểm tra bằng nhau khi cần xác định thứ tự | Dùng compare cho thứ tự; equals cho kiểm tra nội dung bằng nhau |
| Nghĩ Arrays.compare() sắp xếp mảng | Hiểu sai tác dụng của API | compare chỉ trả về kết quả so sánh, không sửa đổi mảng |

## 9. Ghi nhớ

- Java 9 bổ sung Arrays.compare() để so sánh mảng theo thứ tự từ điển.
- Hai mảng được so sánh từ trái sang phải; cặp phần tử khác nhau đầu tiên quyết định kết quả.
- Nếu mọi phần tử trong phần chung bằng nhau, mảng ngắn hơn nhỏ hơn.
- Nếu cùng độ dài và mọi phần tử tương ứng bằng nhau, kết quả là 0.
- Quy tắc tiền tố áp dụng cho cả mảng primitive và mảng object.
- Với object array, có thể dùng thứ tự tự nhiên hoặc Comparator để tùy chỉnh cách so sánh phần tử.
- Chỉ dựa vào dấu âm, 0 hoặc dương của kết quả; không phụ thuộc vào giá trị cụ thể.
- Arrays.compare() không thay đổi mảng và không thay thế Arrays.equals() khi mục tiêu chỉ là kiểm tra bằng nhau.
