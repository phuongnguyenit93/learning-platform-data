# Arrays.toString và Arrays.deepToString

## 1. Vì sao in một mảng thường không thấy các phần tử?

Mảng Java là một đối tượng. Tuy nhiên, mảng không tự ghi đè `Object.toString()` để in nội dung phần tử như một danh sách.

Ví dụ minh họa:

```java
int[] values = {10, 20, 30};
System.out.println(values.toString());
```

Kết quả có dạng biểu diễn lớp mảng và mã băm hệ mười sáu, chẳng hạn bắt đầu bằng `[I@`. Phần mã băm phụ thuộc đối tượng và lần chạy, không phải địa chỉ bộ nhớ được API bảo đảm.

Để nhìn nội dung:

```java
System.out.println(java.util.Arrays.toString(values));
```

kết quả là:

```text
[10, 20, 30]
```

Hai tiện ích cần phân biệt:

- `Arrays.toString`: mô tả các phần tử ở một tầng của mảng.
- `Arrays.deepToString`: đi sâu vào các phần tử cũng là mảng để mô tả nội dung lồng nhau.

Cả hai vẫn là API thông thường trong Java hiện đại. Ví dụ đầy đủ trong bài chạy trên Java 17+.

## 2. Chọn đúng phương thức theo dạng dữ liệu

| Dữ liệu | Cách dùng thông thường | Lý do |
| --- | --- | --- |
| `int[]`, `long[]`, `boolean[]`... | `Arrays.toString(array)` | Có phiên bản riêng cho từng kiểu mảng nguyên thủy |
| `String[]` hoặc mảng đối tượng một chiều | `Arrays.toString(array)` | Gọi biểu diễn chuỗi của từng phần tử |
| `int[][]`, `String[][]` | `Arrays.deepToString(array)` | Các phần tử bên trong cũng là mảng |
| `Object[]` trộn đối tượng và các mảng | `Arrays.deepToString(array)` | Có thể xử lý các phần tử mảng nguyên thủy hoặc mảng đối tượng bên trong |

`deepToString` nhận `Object[]`, không có phiên bản nhận trực tiếp `int[]`.

Một `int[]` là Object nhưng không phải Object[]. Ngược lại, một `int[][]` là một mảng có phần tử kiểu int[], nên mảng ngoài là Object[] và có thể truyền vào deepToString.

Không cần dùng deepToString cho mọi mảng. Với một int[] một chiều, toString đã đúng và rõ ý định.

## 3. Arrays.toString: nhìn một tầng

Các phiên bản cho mảng nguyên thủy chuyển từng phần tử thành biểu diễn phù hợp. Kết quả có dấu ngoặc vuông, dấu phẩy và khoảng trắng giữa các phần tử.

Ví dụ:

```java
Arrays.toString(new int[] {1, 2});       // "[1, 2]"
Arrays.toString(new boolean[] {true}); // "[true]"
Arrays.toString(new char[] {'J', 'a'}); // "[J, a]"
```

Đây là các biểu thức minh họa; tệp sử dụng cần import `java.util.Arrays`.

Với Object[], mỗi phần tử được mô tả qua `String.valueOf`. Phần tử null thành chuỗi `"null"`; phần tử đối tượng bình thường dùng toString của nó.

Nếu phần tử chính là một mảng, toString một tầng không tự đi vào mảng con. Vì vậy:

```java
int[][] matrix = {{1, 2}, {3, 4}};
String text = Arrays.toString(matrix);
```

text sẽ chứa biểu diễn đối tượng của các int[] bên trong, không phải chuỗi nội dung đầy đủ `[[1, 2], [3, 4]]`.

Không chép nguyên các mã băm từ một lần chạy thành “stdout luôn đúng”. Hãy dùng deepToString nếu nội dung mảng lồng mới là điều cần quan sát.

## 4. Arrays.deepToString: đi sâu qua các phần tử mảng

Với:

```java
int[][] matrix = {{1, 2}, {3, 4}};
```

`Arrays.deepToString(matrix)` cho:

```text
[[1, 2], [3, 4]]
```

Nó xử lý được mảng nhiều chiều không đều và các hàng null. Trong Java, mảng hai chiều thực chất là mảng chứa tham chiếu tới các mảng con; các mảng con không bắt buộc cùng độ dài.

Một Object[] cũng có thể trộn:

- Một String.
- Một int[].
- Một Object[] khác.
- null.
- Một đối tượng thông thường có toString riêng.

DeepToString chỉ đi sâu đặc biệt đối với **mảng**. Nó không phản chiếu mọi trường trong một đối tượng và không tự biến một đối tượng nghiệp vụ thành một cây dữ liệu đầy đủ.

Nếu một lớp có trường int[] nhưng toString của lớp vẫn in trường đó theo dạng mã băm, deepToString trên một mảng chứa đối tượng lớp ấy không tự sửa toString của đối tượng.

## 5. Chương trình đầy đủ với output xác định

Lưu thành `ArrayTextDemo.java`:

```java
import java.util.Arrays;

public class ArrayTextDemo {
    static final class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public String toString() {
            return "Point(" + x + "," + y + ")";
        }
    }

    public static void main(String[] args) {
        int[] numbers = {10, 20, 30};
        String[] names = {"An", null, "Binh"};
        int[][] matrix = {
                {1, 2},
                {},
                null,
                {3}
        };

        Object[] mixed = {
                "group",
                new int[] {4, 5},
                new Object[] {new boolean[] {true, false}, "end"},
                null,
                new Point(2, 3)
        };

        System.out.println("numbers=" + Arrays.toString(numbers));
        System.out.println("names=" + Arrays.toString(names));
        System.out.println("matrix=" + Arrays.deepToString(matrix));
        System.out.println("mixed=" + Arrays.deepToString(mixed));

        int[] missing = null;
        System.out.println("null primitive array="
                + Arrays.toString(missing));
        System.out.println("null object array="
                + Arrays.deepToString((Object[]) null));
        System.out.println("empty="
                + Arrays.toString(new int[0]));

        char[] letters = {'J', 'a', 'v', 'a'};
        System.out.println("char elements="
                + Arrays.toString(letters));
        System.out.println("char text=" + new String(letters));

        Object[] cycle = new Object[1];
        cycle[0] = cycle;
        System.out.println("cycle=" + Arrays.deepToString(cycle));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 ArrayTextDemo.java
java ArrayTextDemo
```

Kết quả:

```text
numbers=[10, 20, 30]
names=[An, null, Binh]
matrix=[[1, 2], [], null, [3]]
mixed=[group, [4, 5], [[true, false], end], null, Point(2,3)]
null primitive array=null
null object array=null
empty=[]
char elements=[J, a, v, a]
char text=Java
cycle=[[...]]
```

Ví dụ tránh in trực tiếp biểu diễn identity của mảng, nên output không phụ thuộc mã băm từng lần chạy.

Point được in bằng toString do lớp định nghĩa. Các mảng nằm trong mixed được deepToString đi sâu, còn Point không bị phản chiếu vào từng trường.

## 6. Null, mảng rỗng và phần tử null khác nhau

Cả toString và deepToString đều trả chuỗi `"null"` khi đối số mảng là null. Đây là một đối tượng String chứa bốn ký tự, không phải giá trị tham chiếu null.

Phân biệt:

| Dữ liệu | Biểu diễn |
| --- | --- |
| Mảng null | `null` |
| Mảng không có phần tử | `[]` |
| Object[] có một phần tử null | `[null]` |
| Object[] có một mảng rỗng | `[[]]` khi dùng deepToString |

Với lời gọi trực tiếp:

```java
// Arrays.toString(null);
```

trình biên dịch không biết chọn phiên bản cho int[], long[], Object[] hay các kiểu mảng khác, nên lời gọi mơ hồ. Dùng biến có kiểu rõ ràng như `int[] missing = null`, hoặc ép kiểu mảng phù hợp:

```java
String a = Arrays.toString((int[]) null);
String b = Arrays.toString((Object[]) null);
```

DeepToString chỉ có phiên bản Object[] tương ứng, nên không có cùng xung đột overload đó. Viết ép kiểu `(Object[]) null` trong ví dụ nhằm làm ý định dữ liệu rõ ràng.

## 7. Char[]: in phần tử hay tạo chuỗi văn bản?

`Arrays.toString(char[])` in từng ký tự như các phần tử:

```text
[J, a, v, a]
```

`new String(char[])` tạo văn bản:

```text
Java
```

Đây là hai mục tiêu khác nhau. Đáng chú ý, `System.out.println(char[])` có overload riêng và có thể in các ký tự như văn bản. Vì thế không nên dạy quy tắc quá rộng rằng “println mọi mảng đều ra dạng mã băm”.

Nếu mảng char[] được đặt trong một biến Object rồi in, quá trình chọn overload khác đi. Với bài toán xem phần tử một cách rõ ràng, dùng Arrays.toString; với bài toán tạo nội dung văn bản, dùng API chuỗi thích hợp.

## 8. Mảng tự tham chiếu được biểu diễn thế nào?

Trong chương trình:

```java
Object[] cycle = new Object[1];
cycle[0] = cycle;
```

mảng chứa chính nó. DeepToString nhận diện việc đi lại vào một mảng đang được mở rộng và dùng `[...]` để biểu diễn tham chiếu lặp. Kết quả toàn bộ là `[[...]]`, tránh lặp vô hạn cho chu trình mảng đó.

Một tham chiếu mảng xuất hiện lặp lại ở hai vị trí nhưng không tạo chu trình vẫn có thể được in nội dung tại cả hai vị trí. Vì vậy, output không phải sơ đồ identity đầy đủ của đồ thị đối tượng.

Cơ chế nhận diện chu trình mảng không bảo đảm xử lý được mọi toString do người dùng viết. Nếu toString của một đối tượng tự gọi đệ quy sai, các tiện ích này không tự sửa lỗi đó.

## 9. Không dùng kết quả như định dạng lưu trữ hoặc phép so sánh

Arrays.toString và deepToString hữu ích cho chẩn đoán, học tập và thông báo ngắn về dữ liệu. Chúng không phải định dạng JSON hoặc giao thức tuần tự hóa.

Ví dụ:

```java
String[] one = {"a, b"};
String[] two = {"a", "b"};
```

Hai mảng khác nhau đều có thể được biểu diễn thành chuỗi `[a, b]`. Các chuỗi phần tử không tự được đặt trong dấu nháy hoặc escape theo một định dạng dữ liệu chuẩn.

Do đó:

- Không parse ngược một cách tổng quát để khôi phục mảng.
- Không dùng chuỗi kết quả để kiểm tra hai mảng bằng nhau.
- Với so sánh mảng một tầng, xem xét Arrays.equals.
- Với mảng đối tượng lồng nhau, xem xét Arrays.deepEquals theo hợp đồng của nó.
- Nếu cần lưu/truyền dữ liệu, chọn định dạng có schema và cách escape rõ ràng.

Các tiện ích in chuỗi không sắp xếp, không sao chép sâu và không thay đổi các phần tử của mảng. Một toString do lớp phần tử tự định nghĩa vẫn có thể có tác dụng phụ; nên viết toString phục vụ quan sát một cách đơn giản, tránh dựa vào nó cho hành vi nghiệp vụ.

## 10. Chi phí và giới hạn khi chẩn đoán dữ liệu

ToString duyệt một tầng phần tử; deepToString còn đi qua các mảng con. Với dữ liệu không có chia sẻ/chu trình phức tạp, có thể hình dung chi phí tỷ lệ với số phần tử được biểu diễn và tổng độ dài văn bản tạo ra, cộng công việc của toString từng đối tượng.

Với mảng dùng chung xuất hiện ở nhiều nhánh, cùng nội dung có thể được in nhiều lần. Không nên chỉ đếm số đối tượng mảng khác nhau rồi coi đó là cận đầy đủ cho mọi đồ thị chia sẻ.

Mảng lớn hoặc lồng sâu có thể tạo chuỗi rất lớn, tốn bộ nhớ và thời gian. Mảng lồng cực sâu còn có nguy cơ vượt độ sâu ngăn xếp. Việc phát hiện chu trình không tạo giới hạn kích thước output.

Khi ghi log, hãy chọn dữ liệu và mức chi tiết cần thiết. Không tự đưa toàn bộ dữ liệu nhạy cảm vào log chỉ vì có một tiện ích in mảng.

Các hàm này cũng không tạo snapshot nguyên tử khi luồng khác sửa cùng dữ liệu. Nếu cần bản ghi nhất quán của dữ liệu chia sẻ, phải có chính sách đồng bộ hoặc sao chép phù hợp trước khi biểu diễn.

## 11. Thực hành

1. Dùng Arrays.toString cho matrix trong chương trình và quan sát các mảng con không được in sâu. Không coi mã băm quan sát được là output cố định.
2. Thay deepToString cho mixed bằng toString và chỉ ra những phần tử nào đổi cách biểu diễn.
3. So sánh ba dữ liệu: mảng null, mảng rỗng và mảng một phần tử null.
4. In hai mảng String ở mục 9, rồi giải thích vì sao cùng chuỗi không chứng minh cùng cấu trúc.
5. Đặt cùng một int[] vào hai vị trí của Object[] và dùng deepToString. Giải thích khác biệt giữa chia sẻ tham chiếu và chu trình.

## Tài liệu đối chiếu

- [Arrays — Các phiên bản toString và deepToString](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html).
- [Object.toString — Biểu diễn đối tượng mặc định](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#toString()).
