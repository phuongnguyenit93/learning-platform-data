# Phân biệt so sánh nội dung mảng một chiều và mảng lồng nhau

## 1. Trước hết xác định muốn so sánh điều gì

Hai biến mảng có thể:

- Trỏ tới cùng một đối tượng mảng.
- Trỏ tới hai mảng khác nhau nhưng chứa cùng các giá trị.
- Chứa các mảng con có cùng nội dung nhưng là các đối tượng khác nhau.
- Chứa các đối tượng nghiệp vụ mà ý nghĩa “bằng nhau” phụ thuộc equals của lớp.

Vì vậy, không có một phép so sánh duy nhất phù hợp với mọi yêu cầu.

| Yêu cầu | Công cụ thường dùng |
| --- | --- |
| Hai biến trỏ tới cùng mảng hay không | `a == b` |
| Cùng độ dài và các phần tử một tầng bằng nhau | `Arrays.equals(a, b)` |
| Mảng đối tượng có các mảng lồng nhau bằng nhau theo cấu trúc/nội dung | `Arrays.deepEquals(a, b)` |
| Hai biến khai báo kiểu Object có thể chứa mảng | Cân nhắc `Objects.deepEquals(a, b)` theo hợp đồng của nó |

Mảng Java không ghi đè equals để tự so sánh nội dung. Gọi `a.equals(b)` trên một mảng không thay thế Arrays.equals.

Các ví dụ trong bài dùng Java 17+ và những API vẫn áp dụng hiện nay.

## 2. Mảng một chiều nguyên thủy: dùng đúng overload Arrays.equals

Ví dụ minh họa:

```java
int[] first = {1, 2, 3};
int[] second = {1, 2, 3};
```

Khi đó:

- `first == second` là false: hai mảng được tạo riêng.
- `first.equals(second)` là false: mảng dùng equals theo identity.
- `Arrays.equals(first, second)` là true: cùng độ dài và cùng các giá trị int ở từng vị trí.

Arrays có overload riêng cho tám kiểu mảng nguyên thủy. Không có chuyển đổi tự động toàn bộ int[] thành long[] hay Integer[] để so sánh chéo kiểu.

Đoạn sau không có overload phù hợp:

```java
// Arrays.equals(new int[] {1}, new long[] {1L});
```

Nếu yêu cầu nghiệp vụ coi các dãy số khác kiểu là tương đương, cần định nghĩa cách chuyển đổi/so sánh rõ ràng; không thể mặc định suy từ “đều chứa số 1”.

Thứ tự phần tử có ý nghĩa. `[1, 2]` khác `[2, 1]`. Đây không phải phép so sánh đa tập hoặc so sánh sau khi tự sắp.

## 3. Mảng đối tượng một chiều: mỗi phần tử theo equals

Với String[]:

```java
String[] a = {"Java", null};
String[] b = {new String("Java"), null};
```

`Arrays.equals(a, b)` trả true. Hai String đầu không cần cùng tham chiếu, vì String.equals so sánh nội dung chuỗi. Hai phần tử null cùng vị trí cũng được xem là bằng nhau.

Với một lớp nghiệp vụ thông thường, Arrays.equals không tự phản chiếu vào các trường. Nó dùng equals của phần tử theo hợp đồng. Nếu lớp chưa định nghĩa equals theo giá trị, các đối tượng khác nhau có thể vẫn được xem là không bằng nhau dù các trường trông giống nhau.

Từ “một tầng” không có nghĩa mọi phần tử đều phải là nguyên thủy hoặc String. Nó có nghĩa Arrays.equals chỉ thực hiện phép so sánh phần tử theo quan hệ được quy định, không tự đi sâu đặc biệt qua từng mảng con.

## 4. Mảng lồng nhau: vì sao Arrays.equals có thể trả false?

Xét:

```java
int[][] first = {{1, 2}, {3}};
int[][] second = {{1, 2}, {3}};
```

Mảng ngoài có các phần tử kiểu int[]. Khi gọi `Arrays.equals(first, second)`, Java dùng phiên bản Object[] và so sánh từng mảng con bằng equals của chúng.

Các int[] con được tạo riêng, không ghi đè equals, nên kết quả là false dù các số giống nhau.

`Arrays.deepEquals(first, second)` xử lý các phần tử mảng con theo nội dung và cho kết quả true.

Tuy vậy, Arrays.equals cho mảng lồng không phải **luôn** false. Nếu hai mảng ngoài chứa cùng tham chiếu mảng con ở từng vị trí, so sánh một tầng có thể trả true. Phải phân biệt “không tự đi sâu” với “không bao giờ bằng nhau”.

## 5. Chương trình đầy đủ

Lưu thành `ArrayContentEqualityDemo.java`:

```java
import java.util.Arrays;
import java.util.Objects;

public class ArrayContentEqualityDemo {
    record Person(String name, int age) {
    }

    public static void main(String[] args) {
        int[] numbersA = {1, 2, 3};
        int[] numbersB = {1, 2, 3};

        System.out.println("same reference="
                + (numbersA == numbersB));
        System.out.println("array equals method="
                + numbersA.equals(numbersB));
        System.out.println("one-dimensional content="
                + Arrays.equals(numbersA, numbersB));

        String[] namesA = {"Java", null};
        String[] namesB = {new String("Java"), null};
        System.out.println("String content="
                + Arrays.equals(namesA, namesB));

        int[][] matrixA = {{1, 2}, {}, null, {3}};
        int[][] matrixB = {{1, 2}, {}, null, {3}};

        System.out.println("nested shallow="
                + Arrays.equals(matrixA, matrixB));
        System.out.println("nested deep="
                + Arrays.deepEquals(matrixA, matrixB));

        Object[] mixedA = {
                new int[] {4, 5},
                new String[] {"x", null},
                new Person("An", 20)
        };
        Object[] mixedB = {
                new int[] {4, 5},
                new String[] {new String("x"), null},
                new Person("An", 20)
        };

        System.out.println("mixed deep="
                + Arrays.deepEquals(mixedA, mixedB));

        Object objectA = numbersA;
        Object objectB = numbersB;
        System.out.println("Object deep="
                + Objects.deepEquals(objectA, objectB));

        matrixB[0][1] = 99;
        System.out.println("after nested change="
                + Arrays.deepEquals(matrixA, matrixB));

        double[] nanA = {Double.NaN, 1.0};
        double[] nanB = {Double.NaN, 1.0};
        System.out.println("NaN content="
                + Arrays.equals(nanA, nanB));
        System.out.println("signed zero content="
                + Arrays.equals(
                        new double[] {0.0},
                        new double[] {-0.0}));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 ArrayContentEqualityDemo.java
java ArrayContentEqualityDemo
```

Kết quả:

```text
same reference=false
array equals method=false
one-dimensional content=true
String content=true
nested shallow=false
nested deep=true
mixed deep=true
Object deep=true
after nested change=false
NaN content=true
signed zero content=false
```

Person là record với các thành phần String và int, nên equals được sinh theo các thành phần và phù hợp với yêu cầu trong ví dụ. DeepEquals gọi quan hệ equals của Person; nó không tự có một cơ chế phản chiếu riêng để so sánh mọi lớp nghiệp vụ.

## 6. DeepEquals sâu tới đâu?

Arrays.deepEquals nhận Object[] và xử lý từng cặp phần tử tương ứng:

- Nếu cả hai là mảng nguyên thủy cùng loại, so sánh theo nội dung bằng overload tương ứng.
- Nếu cả hai là mảng đối tượng, tiếp tục so sánh sâu.
- Nếu không phải các trường hợp mảng tương ứng, dùng quan hệ equals của đối tượng theo hợp đồng.

Do đó, một Object[] có thể chứa int[], String[][] và đối tượng thông thường. Nhưng “deep” không có nghĩa là duyệt mọi trường của mọi đối tượng trong đồ thị.

Ví dụ một record có thành phần int[] vẫn dùng equals của thành phần mảng khi so sánh record, nên không tự có ngữ nghĩa so sánh sâu cho nội dung int[] chỉ vì record nằm trong Object[].

DeepEquals cũng không làm int[] và long[] trở thành bằng nhau khi giá trị số trông giống nhau. Loại mảng và quan hệ phần tử vẫn quan trọng.

## 7. Chữ ký Object[] và Objects.deepEquals

Không thể gọi:

```java
// Arrays.deepEquals(new int[] {1, 2}, new int[] {1, 2});
```

vì int[] không phải Object[]. Với hai mảng nguyên thủy có kiểu cụ thể, dùng Arrays.equals là đúng.

Nếu hai biến có kiểu Object và có thể chứa mảng, có thể dùng:

```java
Object a = new int[] {1, 2};
Object b = new int[] {1, 2};

boolean same = Objects.deepEquals(a, b);
```

Objects.deepEquals nhận Object, kiểm tra null và trường hợp mảng theo hợp đồng, nên có thể so sánh nội dung hai int[] trong tình huống này.

Không thay bằng `Objects.equals(a, b)` rồi kỳ vọng kết quả tương tự: Objects.equals dùng equals thông thường của đối tượng; mảng không tự đổi sang equals theo nội dung.

Khi đã có kiểu int[] rõ ràng, Arrays.equals thường thể hiện ý định trực tiếp hơn. Objects.deepEquals hữu ích tại ranh giới dữ liệu mang kiểu Object; nó không tự thay thế toàn bộ thiết kế kiểu của chương trình.

## 8. Null, mảng rỗng và cấu trúc mảng không đều

Với overload đã xác định:

- Hai tham chiếu mảng đều null được xem là bằng nhau.
- Một null và một mảng khác null không bằng nhau.
- Hai mảng rỗng cùng kiểu nội dung phù hợp bằng nhau.
- Mảng null khác mảng rỗng.
- Null tại cùng vị trí trong Object[] được xử lý hợp lệ.

Ví dụ minh họa:

```java
Arrays.equals((int[]) null, (int[]) null); // true
Arrays.equals((int[]) null, new int[0]);   // false

Arrays.deepEquals(
        new Object[] {null, new int[0]},
        new Object[] {null, new int[0]});  // true
```

Dùng kiểu rõ ràng khi truyền null trực tiếp. `Arrays.equals(null, null)` có thể mơ hồ vì có nhiều overload cho các kiểu mảng khác nhau.

Mảng lồng không cần hình chữ nhật. DeepEquals vẫn so sánh đúng từng vị trí và từng độ dài mảng con. `{{1}, {2, 3}}` khác `{{1, 2}, {3}}`; hai cấu trúc không bằng nhau chỉ vì nếu “trải phẳng” thì cùng dãy số.

## 9. Số thực không được so sánh bằng một dung sai ngầm định

Các overload equals cho float[] và double[] không tự có sai số cho tính toán gần đúng.

Theo hợp đồng của chúng:

- Các giá trị NaN tương ứng được xem là bằng nhau.
- `0.0` và `-0.0` được xem là khác nhau.

Đây là lý do hai dòng cuối chương trình có kết quả true rồi false. Không suy trực tiếp từ toán tử `==` của double để dự đoán mọi chi tiết của Arrays.equals.

Nếu bài toán cần `abs(a[i] - b[i]) <= tolerance`, phải định nghĩa thuật toán riêng, bao gồm chính sách NaN, vô cực, signed zero, độ dài và sai số tuyệt đối/tương đối. Arrays.deepEquals khi gặp mảng double cũng sử dụng ngữ nghĩa tương ứng, không tự thêm dung sai.

## 10. Không dùng chuỗi in ra để so sánh nội dung

Arrays.toString và deepToString phục vụ biểu diễn văn bản. Chúng không phải phép kiểm tra bằng nhau.

Ví dụ:

```java
String[] a = {"a, b"};
String[] b = {"a", "b"};
```

hai mảng khác độ dài vẫn có thể cho cùng chuỗi hiển thị `[a, b]`. So sánh chuỗi đó sẽ mất thông tin cấu trúc.

Cũng không dùng hashCode bằng nhau để kết luận hai mảng bằng nhau, vì mã băm có thể trùng. Nếu cần mã băm theo cùng quan hệ nội dung, dùng Arrays.hashCode cho một tầng hoặc Arrays.deepHashCode cho cấu trúc lồng, đồng thời vẫn dùng phép equals phù hợp để quyết định.

Một mảng đặt trực tiếp làm khóa HashMap vẫn dùng equals/hashCode của đối tượng mảng theo identity. Việc từng gọi Arrays.equals ở nơi khác không thay đổi hợp đồng của mảng đó trong collection. Nếu cần khóa theo nội dung, phải thiết kế kiểu khóa và chính sách bất biến phù hợp.

## 11. Chu trình, chi phí và dữ liệu đang thay đổi

Arrays.deepEquals không cung cấp một phép so sánh đồ thị đối tượng có chu trình tổng quát. Với mảng chứa chính nó trực tiếp hoặc gián tiếp, tài liệu quy định hành vi so sánh là không xác định. Không kỳ vọng cơ chế `[...]` của deepToString cũng được áp dụng cho deepEquals.

Với dữ liệu không chu trình, equals có thể dừng sớm khi khác độ dài hoặc khác một phần tử. Trường hợp xấu cho mảng một chiều là phải so sánh các phần tử tới cuối; chi phí còn phụ thuộc equals của từng đối tượng.

Mảng lồng có thể cần đi qua nhiều phần tử ở nhiều mức. Độ sâu quá lớn hoặc các cấu trúc chia sẻ phức tạp cũng cần được cân nhắc; không nên xem từ “deep” như bảo đảm an toàn với mọi đồ thị hoặc kích thước.

Các phép so sánh không tự tạo snapshot nguyên tử. Nếu luồng khác sửa nội dung cùng lúc, kết quả không thể được diễn giải như một bản chụp nhất quán nếu không có chính sách đồng bộ phù hợp.

## 12. Thực hành

1. Cho hai mảng ngoài cùng chứa một int[] chung, rồi so sánh bằng Arrays.equals. Giải thích vì sao có thể true dù phương thức không đi sâu.
2. Thay Person trong chương trình bằng một lớp không ghi đè equals. Dự đoán kết quả mixed deep khi hai mảng chứa hai instance khác nhau.
3. So sánh hai cấu trúc có cùng dãy số sau khi trải phẳng nhưng khác cách chia hàng. Giải thích vì sao deepEquals vẫn false.
4. Đặt hai int[] trong biến Object rồi đối chiếu Objects.equals và Objects.deepEquals.
5. Viết rõ yêu cầu trước khi chọn API: cùng tham chiếu, cùng phần tử một tầng, cùng cấu trúc mảng lồng hay gần bằng theo dung sai.

## Tài liệu đối chiếu

- [Arrays — equals, deepEquals và các hợp đồng số thực](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html).
- [Objects.deepEquals — So sánh sâu khi đối số có kiểu Object](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#deepEquals(java.lang.Object,java.lang.Object)).
