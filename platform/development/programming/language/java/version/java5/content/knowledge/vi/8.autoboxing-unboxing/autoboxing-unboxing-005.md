# So sánh giá trị bằng equals và so sánh tham chiếu bằng ==

## 1. Xác định câu hỏi cần trả lời

Khi hai biến cùng biểu diễn số 100, có ít nhất hai câu hỏi khác nhau: chúng có biểu diễn giá trị bằng nhau theo hợp đồng của kiểu không, và chúng có đang tham chiếu tới đúng cùng một đối tượng không?

Với wrapper như `Integer`, hai câu hỏi tương ứng với những phép kiểm tra khác nhau:

- `a.equals(b)` kiểm tra quan hệ bằng nhau do lớp wrapper định nghĩa.
- `a == b`, khi cả hai toán hạng được xử lý như tham chiếu, kiểm tra chúng cùng trỏ tới một đối tượng hay cùng bằng `null`.

Nhưng `==` không phải lúc nào cũng là so sánh tham chiếu: nếu các toán hạng được xử lý như số nguyên thủy, nó so sánh giá trị số. Boxing và unboxing làm việc xác định kiểu toán hạng trở nên đặc biệt quan trọng.

Đừng chọn phép so sánh chỉ bằng việc nhìn thấy hai chữ số giống nhau trên màn hình. Hãy xác định kiểu tĩnh của hai biểu thức và quan hệ mà chương trình thật sự muốn kiểm tra.

Các quy tắc trong bài vẫn áp dụng trong Java hiện hành; ví dụ chạy bằng JDK 17 trở lên.

## 2. Bảng phân biệt các trường hợp thường gặp

| Biểu thức | Ý nghĩa chính | Điểm cần nhớ |
| --- | --- | --- |
| `intValue1 == intValue2` | So sánh giá trị nguyên thủy | Có thể có quy tắc nâng kiểu số khi hai kiểu khác nhau |
| `integer1 == integer2` với hai biến `Integer` | So sánh tham chiếu | Không tự coi đây là so sánh hai giá trị `int` |
| `integer == intValue` | Mở hộp rồi so sánh số | Wrapper bằng `null` có thể gây `NullPointerException` |
| `integer1.equals(integer2)` | So sánh theo hợp đồng `Integer.equals` | Biến nhận lời gọi phải khác `null` |
| `Objects.equals(a, b)` | So sánh đối tượng có xử lý `null` | Không tự chuẩn hóa các wrapper số khác kiểu |
| `a == null` với biến tham chiếu | Kiểm tra tham chiếu rỗng | Không cần gọi phương thức trên đối tượng |

`Integer` và `int` khác nhau trong bảng không chỉ về chữ viết hoa. Một bên là kiểu tham chiếu có thể bằng `null`; bên kia là kiểu nguyên thủy.

Quy tắc toán tử bằng và khác được nêu tại [JLS §15.21](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.21).

## 3. Vì sao dùng == với hai wrapper dễ dẫn tới kết luận sai?

```java
Integer first = 100;
Integer second = 100;
boolean sameReference = first == second;
boolean sameValue = first.equals(second);
```

Trong ví dụ boxing các hằng số này, hai tham chiếu có thể được dùng chung theo bảo đảm của Java cho miền giá trị nhỏ; kết quả `sameReference` là `true`. Kết quả đó dễ làm người mới tin rằng `==` luôn kiểm tra giá trị wrapper.

Thực ra, boxing không bắt buộc tạo đối tượng mới riêng cho mọi lần xuất hiện. Với các hằng số `int` trong khoảng -128 đến 127, Java có bảo đảm danh tính phù hợp cho việc boxing được mô tả trong đặc tả. Ngoài những bảo đảm ấy, không được viết logic phụ thuộc vào việc hai lần boxing giá trị bằng nhau chắc chắn có cùng hay khác tham chiếu.

```java
Integer first = 1000;
Integer second = 1000;
boolean sameValue = first.equals(second);
```

`sameValue` là `true`. Không cần dựa vào kết quả `first == second` để biết hai `Integer` biểu diễn cùng giá trị. Cũng không nên dùng số 1000 để tuyên bố phép `==` chắc chắn luôn trả `false` trên mọi cấu hình phù hợp; cơ chế tái sử dụng wrapper có thể rộng hơn miền bảo đảm tối thiểu.

Nếu hai biến được gán trực tiếp cùng một tham chiếu, như `Integer alias = first`, thì `alias == first` là `true`. Đây là điều phép so sánh danh tính thực sự diễn đạt.

Đối chiếu bảo đảm boxing tại [JLS §5.1.7](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.7). Trong mã nghiệp vụ cần so giá trị wrapper, chọn `equals` hoặc `Objects.equals` theo chính sách `null`, không chọn `==` dựa vào cache.

## 4. Khi một bên là kiểu nguyên thủy

```java
Integer boxed = 1000;
int primitive = 1000;
boolean equal = boxed == primitive;
```

Ở đây có toán hạng số nguyên thủy, nên `boxed` được mở hộp để tham gia so sánh số. Kết quả là `true`; phép kiểm tra không hỏi hai bên có cùng đối tượng hay không vì `primitive` không phải tham chiếu đối tượng.

Đổi một vế từ wrapper sang nguyên thủy có thể làm thay đổi ý nghĩa của một biểu thức trông rất giống nhau. Điều này cũng thay đổi rủi ro với `null`:

```java
Integer absent = null;
// boolean equal = absent == 0; // Khi chạy sẽ mở hộp null và gây lỗi
```

`absent == null` kiểm tra tham chiếu rỗng an toàn. `absent == 0` cần giá trị số và có thể gây `NullPointerException`. Hai biểu thức cùng dùng `==` nhưng áp dụng những quy tắc khác nhau.

Đừng mở hộp một giá trị chưa rõ chính sách `null` chỉ để làm phép so sánh bằng “gọn hơn”. Cần xác định trước `null` biểu thị thiếu dữ liệu, một trạng thái hợp lệ hay lỗi đầu vào.

## 5. equals của wrapper không phải phép bằng số tổng quát

`Integer.equals` chỉ coi một đối tượng khác bằng nó khi đối tượng ấy cũng là `Integer` và chứa cùng giá trị `int`:

```java
Integer one = 1;
boolean sameType = one.equals(1);
boolean differentType = one.equals(1L);
```

Đối số `1` được boxing thành `Integer`, nên `sameType` là `true`. Đối số `1L` được boxing thành `Long`, nên `differentType` là `false`.

Ngược lại, biểu thức nguyên thủy `1 == 1L` cho kết quả `true` theo quy tắc so sánh số sau nâng kiểu phù hợp. Không có mâu thuẫn: đây là hai quan hệ được định nghĩa khác nhau.

Việc biến được khai báo là `Number` không tạo một hợp đồng mới chuẩn hóa mọi kiểu số:

```java
Number integer = Integer.valueOf(1);
Number longNumber = Long.valueOf(1L);
boolean sameReference = integer == longNumber;
boolean sameValue = integer.equals(longNumber);
```

Hai đối tượng thuộc các lớp khác nhau, nên không thể cùng một đối tượng; `sameReference` là `false`. Lời gọi `equals` vẫn dùng phần triển khai của đối tượng `Integer`, nên `sameValue` cũng là `false`.

Đặc biệt, biểu thức so trực tiếp một biến `Integer` với một biến `Long` bằng `==` bị từ chối khi biên dịch vì hai kiểu tham chiếu ấy không tương thích cho phép so tham chiếu đó. Java không tự mở hộp mọi cặp wrapper chỉ vì chúng đều là số.

Xem hợp đồng [Integer.equals](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#equals(java.lang.Object)). Nếu nghiệp vụ cần so số thuộc nhiều kiểu biểu diễn, hãy xác định quy tắc chuẩn hóa và độ chính xác phù hợp; không mặc định chuyển mọi `Number` sang `double` là chính xác.

## 6. Xử lý null bằng Objects.equals

```java
Objects.equals(null, null);                    // true
Objects.equals(null, Integer.valueOf(1));      // false
Objects.equals(Integer.valueOf(1), null);      // false
Objects.equals(Integer.valueOf(1), Integer.valueOf(1)); // true
```

Đoạn này minh họa các biểu thức, cần `import java.util.Objects;`. `Objects.equals` xử lý trường hợp tham chiếu rỗng trước khi cần gọi `equals` trên đối tượng thích hợp.

`a.equals(b)` có thể gây `NullPointerException` nếu chính `a` bằng `null`. Nếu `a` là một wrapper khác `null`, `a.equals(null)` trả `false` theo hợp đồng.

`Objects.equals` không phải một phép mở hộp rồi so sánh số chung. Ví dụ `Objects.equals(Integer.valueOf(1), Long.valueOf(1))` vẫn là `false`. Nó giữ nguyên ý nghĩa bằng nhau do lớp đối tượng quy định.

Tham khảo [Objects.equals](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).

## 7. Chương trình chạy đầy đủ

Lưu thành `WrapperEqualityDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class WrapperEqualityDemo {
    public static void main(String[] args) {
        Integer smallA = 100;
        Integer smallB = 100;
        System.out.println("small reference=" + (smallA == smallB));
        System.out.println("small value=" + smallA.equals(smallB));

        Integer largeA = 1000;
        Integer largeB = 1000;
        Integer alias = largeA;
        System.out.println("large value=" + largeA.equals(largeB));
        System.out.println("alias reference=" + (alias == largeA));
        System.out.println("wrapper and primitive=" + (largeA == 1000));

        Integer intOne = 1;
        Long longOne = 1L;
        System.out.println("same wrapper value=" + intOne.equals(1));
        System.out.println("different wrapper value=" + intOne.equals(1L));
        System.out.println("objects cross type=" + Objects.equals(intOne, longOne));
        System.out.println("primitive cross type=" + (1 == 1L));

        Number asInteger = intOne;
        Number asLong = longOne;
        System.out.println("number references=" + (asInteger == asLong));

        Integer absent = null;
        System.out.println("both null=" + Objects.equals(absent, null));
        System.out.println("one null=" + Objects.equals(absent, intOne));
        System.out.println("equals null=" + intOne.equals(absent));
        try {
            boolean result = absent == 0;
            System.out.println("unexpected=" + result);
        } catch (NullPointerException expected) {
            System.out.println("null numeric=NullPointerException");
        }

        System.out.println("collection cross type=" + List.of(1).contains(1L));
        System.out.println("primitive NaN=" + (Double.NaN == Double.NaN));
        System.out.println("wrapper NaN="
                + Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN)));
        System.out.println("primitive zero=" + (0.0 == -0.0));
        System.out.println("wrapper zero="
                + Double.valueOf(0.0).equals(Double.valueOf(-0.0)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror WrapperEqualityDemo.java
java WrapperEqualityDemo
```

Stdout:

```text
small reference=true
small value=true
large value=true
alias reference=true
wrapper and primitive=true
same wrapper value=true
different wrapper value=false
objects cross type=false
primitive cross type=true
number references=false
both null=true
one null=false
equals null=false
null numeric=NullPointerException
collection cross type=false
primitive NaN=false
wrapper NaN=true
primitive zero=true
wrapper zero=false
```

Chương trình không in kết quả `==` giữa hai wrapper giá trị 1000, để không biến một chi tiết có thể phụ thuộc cơ chế tái sử dụng thành stdout được khẳng định chung. Các kết quả so sánh giá trị và kiểm tra alias không cần giả định ấy.

Khối `catch` chỉ minh họa việc mở hộp `null` trong biểu thức số. Trong mã ứng dụng, xử lý chính sách thiếu dữ liệu trước khi thực hiện phép toán, thay vì dùng ngoại lệ làm nhánh so sánh thông thường.

## 8. Hợp đồng equals của kiểu cụ thể vẫn quan trọng

### 8.1. Collection cũng dùng ý nghĩa bằng nhau của phần tử

`List.of(1).contains(1L)` là `false`: danh sách chứa `Integer`, còn đối số tìm kiếm được boxing thành `Long`; chúng không bằng nhau theo hợp đồng wrapper.

Không suy ra rằng nhìn thấy cùng giá trị toán học là mọi API tìm kiếm hay khóa collection sẽ coi chúng là cùng một phần tử. Chọn kiểu dữ liệu thống nhất ở biên API thường giúp tránh sự khác nhau không chủ đích.

### 8.2. Double có các quy tắc đáng chú ý

Những dòng cuối chương trình minh họa rằng `Double.equals` không chỉ là mở hộp rồi dùng toán tử `==` cho mọi trường hợp:

- Hai giá trị `double` là NaN so bằng `==` cho `false`, nhưng hai wrapper NaN bằng nhau theo `Double.equals`.
- `0.0 == -0.0` là `true`, còn wrapper `Double` của `+0.0` và `-0.0` không bằng nhau theo `equals`.

Đó là hợp đồng có chủ đích của [Double.equals](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html#equals(java.lang.Object)), phù hợp với cách wrapper tham gia các cấu trúc dữ liệu cần quan hệ bằng nhau nhất quán. Không nên chuyển kết luận cho `Integer` thành một quy tắc số học bao quát mọi wrapper mà không đọc hợp đồng kiểu.

### 8.3. equals không tự so sánh mọi trường của mọi lớp

Với lớp do mình viết, gọi `equals` không tự động có nghĩa so sánh toàn bộ dữ liệu. Phần triển khai mặc định của [Object.equals](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)) dùng quan hệ cùng đối tượng; lớp cụ thể có thể định nghĩa lại theo hợp đồng phù hợp.

Vì vậy câu “dùng equals để so giá trị” trong ngữ cảnh wrapper dựa trên việc wrapper đã có phần triển khai bằng nhau thích hợp. Thiết kế `equals`/`hashCode` cho một lớp nghiệp vụ là một trách nhiệm riêng.

## 9. Chọn phép kiểm tra theo nhu cầu

| Nhu cầu | Cách dùng phù hợp |
| --- | --- |
| So hai giá trị `Integer` chắc chắn khác `null` | `a.equals(b)` |
| So hai wrapper có thể có `null` theo hợp đồng cùng kiểu | `Objects.equals(a, b)` |
| Kiểm tra có dữ liệu hay không | `a == null` hoặc `a != null` |
| So các giá trị nguyên thủy | Toán tử số thích hợp, với quy tắc của kiểu số đó |
| Xác định hai tham chiếu có dẫn tới cùng đối tượng | `a == b` khi phép so tham chiếu hợp lệ |
| So số khác kiểu biểu diễn theo nghiệp vụ | Chuẩn hóa bằng quy tắc và độ chính xác được thiết kế rõ |

## 10. Tự kiểm tra

1. Vì sao `Integer a = 100; Integer b = 100; a == b` cho `true` không chứng minh `==` luôn so giá trị wrapper?
2. Vì sao `Integer.valueOf(1).equals(Long.valueOf(1))` là `false`?
3. `Integer value = null; value == 0` có chỉ trả `false` không?
4. `Objects.equals` có tự mở hộp mọi wrapper số để so chung không?
5. Có được khẳng định hai lần boxing giá trị 1000 luôn tạo hai đối tượng khác nhau không?

Đáp án:

1. Vì boxing có thể dùng chung đối tượng; phép `==` vẫn đang so danh tính tham chiếu.
2. Hợp đồng `Integer.equals` yêu cầu đối tượng kia cũng là `Integer` với cùng giá trị.
3. Không. Nó cần mở hộp và gây `NullPointerException` khi wrapper rỗng.
4. Không. Nó xử lý `null` và dùng ý nghĩa bằng nhau của đối tượng.
5. Không. Không viết logic phụ thuộc vào danh tính wrapper ngoài các bảo đảm cụ thể của đặc tả/API.

Hãy xác định trước muốn so giá trị theo hợp đồng nào, kiểm tra thiếu dữ liệu hay nhận diện cùng đối tượng. Sau đó xét kiểu của từng toán hạng để biết boxing/unboxing có làm thay đổi ý nghĩa phép so sánh hay không.
