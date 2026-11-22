# Sao chép mảng primitive và mảng tham chiếu

## 1. Bắt đầu từ câu hỏi: phần tử của mảng đang chứa gì?

Khi cần giữ một bản dữ liệu trước khi chỉnh sửa, ta thường nghĩ “tạo mảng mới là đã độc lập”. Điều này đúng ở cấp các ô phần tử, nhưng chưa đủ nếu những ô đó chứa tham chiếu đến đối tượng có thể thay đổi.

Cần phân biệt hai tầng:

- **Đối tượng mảng:** chứa các ô phần tử, có độ dài cố định.
- **Giá trị trong từng ô:** giá trị nguyên thủy đối với `int[]`, `boolean[]`…; giá trị tham chiếu đối với `String[]`, `Customer[]`, `int[][]`…

Mọi mảng Java đều là đối tượng. Biến có kiểu mảng giữ một tham chiếu đến đối tượng mảng đó. Vì thế ngay cả `int[]` cũng không phải một “giá trị nguyên thủy”; chỉ các phần tử trực tiếp của nó là `int`. [Quy tắc mảng trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html)

Trong bài, **mảng primitive** là mảng có kiểu thành phần trực tiếp nguyên thủy, ví dụ `int[]`; **mảng tham chiếu** là mảng có kiểu thành phần trực tiếp là kiểu tham chiếu, ví dụ `Person[]` hoặc `int[][]`.

## 2. Gán biến không phải sao chép nội dung mảng

```java
int[] original = {10, 20};
int[] alias = original;
alias[0] = 99;
// original[0] cũng là 99 vì hai biến chỉ đến cùng một mảng.
```

Đây là đoạn minh họa có thể đặt trong một phương thức Java. Phép gán chỉ sao chép giá trị tham chiếu từ `original` sang `alias`; không tạo đối tượng mảng mới.

```text
original ----+
             +----> mảng [99, 20]
alias -------+
```

Để có các ô phần tử độc lập, phải tạo mảng đích khác rồi sao chép. `Arrays.copyOf`, `clone()` của mảng hoặc `System.arraycopy` vào một mảng mới có thể thực hiện điều đó; ý nghĩa của phần tử được chép vẫn phụ thuộc vào kiểu thành phần.

## 3. Mảng primitive: các giá trị được chép sang ô mới

Với `int[]`, mỗi ô giữ một giá trị `int`. Khi tạo bản sao, hai mảng có những ô khác nhau nhưng ban đầu chứa các giá trị tương ứng bằng nhau.

```java
int[] original = {10, 20};
int[] copy = java.util.Arrays.copyOf(original, original.length);
copy[0] = 99;
// original vẫn là [10, 20]; copy là [99, 20].
```

```text
original ---> mảng thứ nhất [10, 20]
copy -------> mảng thứ hai  [99, 20]
```

Chỉnh `copy[0]` không chỉnh `original[0]`. Không có đối tượng phần tử nào được hai ô tham chiếu chung, vì giá trị trong ô là số nguyên. Cách suy luận tương tự áp dụng cho `byte[]`, `short[]`, `long[]`, `float[]`, `double[]`, `char[]` và `boolean[]`.

Điều đó không có nghĩa bản sao tự đồng bộ với nguồn. Nếu sau đó đổi `original[1]`, `copy[1]` giữ nguyên giá trị đã được chép trước đó. Đây là hai vùng chứa phần tử độc lập, không phải một chế độ xem đang theo dõi nhau.

## 4. Mảng tham chiếu: mảng mới nhưng đối tượng phần tử có thể dùng chung

Xét một lớp có thể thay đổi `Box` với trường `int value`. Khi sao chép `Box[]`, mỗi ô đích nhận giá trị tham chiếu từ ô nguồn. Không có thao tác tự động gọi constructor để tạo một `Box` mới.

```text
boxes --------> mảng A: [ref-X, ref-Y]
                            |      |
                            v      v
                         Box X   Box Y
                            ^      ^
                            |      |
referenceCopy -> mảng B: [ref-X, ref-Y]
```

Đây là **sao chép nông (shallow copy)**: mảng ngoài mới, còn các đối tượng được phần tử trỏ đến ban đầu vẫn có thể dùng chung. Sao chép giá trị tham chiếu không đồng nghĩa sao chép đối tượng đích.

Có hai loại thay đổi cần tách rõ:

| Thao tác trên bản sao | Thực sự thay đổi gì? | Nguồn có bị ảnh hưởng không? |
| --- | --- | --- |
| `copy[0] = anotherBox` | Thay giá trị tham chiếu ở một ô của mảng sao | Không thay ô tương ứng của mảng nguồn |
| `copy[0].value = 99` | Sửa đối tượng đang được ô trỏ đến | Có, nếu nguồn vẫn trỏ đến đúng đối tượng đó |
| `copy[0] = null` | Xóa tham chiếu ở ô của bản sao | Không tự xóa tham chiếu trong nguồn |

Nếu phần tử là `null`, bản sao của phần tử đó cũng là `null`. Không có đối tượng nào được tạo để thay cho giá trị rỗng.

`String[]` có thể khiến người học khó nhìn thấy sự dùng chung vì `String` là bất biến: không thể sửa nội dung một đối tượng `String` đang tồn tại. Gán `copy[0] = "new"` chỉ thay ô của bản sao. Điều này không chứng minh các đối tượng `String` đã được nhân bản; việc dùng chung giá trị bất biến thường là hoàn toàn phù hợp.

`Integer[]` cũng là mảng tham chiếu. Việc `Integer` biểu diễn số không biến các ô của `Integer[]` thành những ô primitive như trong `int[]`.

## 5. Minh chứng hoàn chỉnh, chạy được trên Java 17+

Chương trình sau quan sát ba cấp độ: sao chép số nguyên, sao chép các tham chiếu `Box`, và tạo `Box` độc lập theo hợp đồng của lớp. Sau đó chương trình kiểm tra mảng hai chiều và kiểu mảng thực tế.

Lưu toàn bộ mã thành `PrimitiveReferenceCopyDemo.java`:

```java
import java.util.Arrays;

public class PrimitiveReferenceCopyDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }

        Box(Box other) {
            this.value = other.value;
        }

        @Override
        public String toString() {
            return Integer.toString(value);
        }
    }

    static Box[] copyBoxes(Box[] source) {
        Box[] result = new Box[source.length];
        for (int i = 0; i < source.length; i++) {
            result[i] = source[i] == null ? null : new Box(source[i]);
        }
        return result;
    }

    static int[][] copyRows(int[][] source) {
        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = source[i] == null ? null : source[i].clone();
        }
        return result;
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2};
        int[] numberCopy = Arrays.copyOf(numbers, numbers.length);
        numberCopy[0] = 9;
        System.out.println("primitive-source=" + Arrays.toString(numbers));
        System.out.println("primitive-copy=" + Arrays.toString(numberCopy));

        Box[] boxes = {new Box(10), new Box(20), null};
        Box[] referenceCopy = Arrays.copyOf(boxes, boxes.length);
        referenceCopy[0].value = 99;
        referenceCopy[1] = new Box(77);
        System.out.println("reference-source=" + Arrays.toString(boxes));
        System.out.println("reference-copy=" + Arrays.toString(referenceCopy));
        System.out.println("shared-first=" + (boxes[0] == referenceCopy[0]));
        System.out.println("shared-second=" + (boxes[1] == referenceCopy[1]));

        Box[] independent = copyBoxes(boxes);
        independent[0].value = 5;
        System.out.println("deep-source=" + Arrays.toString(boxes));
        System.out.println("deep-copy=" + Arrays.toString(independent));

        int[][] matrix = {{1, 2}, {3, 4}};
        int[][] outerCopy = matrix.clone();
        outerCopy[0][0] = 8;
        int[][] rowCopy = copyRows(matrix);
        rowCopy[1][1] = 90;
        System.out.println("matrix-source=" + Arrays.deepToString(matrix));
        System.out.println("matrix-independent=" + Arrays.deepToString(rowCopy));

        System.out.println("expanded-primitive="
                + Arrays.toString(Arrays.copyOf(numbers, 4)));
        System.out.println("expanded-reference="
                + Arrays.toString(Arrays.copyOf(boxes, 4)));

        Number[] source = new Integer[] {1, 2};
        Number[] sameRuntimeType = Arrays.copyOf(source, 3);
        System.out.println("component="
                + sameRuntimeType.getClass().getComponentType().getSimpleName());
        try {
            sameRuntimeType[2] = 3.5;
        } catch (ArrayStoreException e) {
            System.out.println("narrow-store=ArrayStoreException");
        }
        Number[] widened = Arrays.copyOf(source, 3, Number[].class);
        widened[2] = 3.5;
        System.out.println("widened=" + Arrays.toString(widened));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 PrimitiveReferenceCopyDemo.java
java PrimitiveReferenceCopyDemo
```

Đầu ra:

```text
primitive-source=[1, 2]
primitive-copy=[9, 2]
reference-source=[99, 20, null]
reference-copy=[99, 77, null]
shared-first=true
shared-second=false
deep-source=[99, 20, null]
deep-copy=[5, 20, null]
matrix-source=[[8, 2], [3, 4]]
matrix-independent=[[8, 2], [3, 90]]
expanded-primitive=[1, 2, 0, 0]
expanded-reference=[99, 20, null, null]
component=Integer
narrow-store=ArrayStoreException
widened=[1, 2, 3.5]
```

### Đọc phần primitive và phần tham chiếu

`numberCopy[0] = 9` chỉ sửa bản sao nên nguồn vẫn `[1, 2]`.

`referenceCopy[0].value = 99` đi qua tham chiếu dùng chung đến `Box` thứ nhất, nên cả hai mảng nhìn thấy 99. Ngược lại, `referenceCopy[1] = new Box(77)` chỉ thay ô thứ hai của bản sao; nguồn vẫn giữ `Box(20)`.

`shared-first=true` xác nhận hai ô đầu còn trỏ đến cùng một đối tượng. `shared-second=false` xác nhận việc gán đối tượng mới đã làm hai ô thứ hai trỏ khác nhau.

`copyBoxes` tạo mảng mới và tạo `Box` mới cho từng phần tử khác `null`. Vì lớp `Box` trong ví dụ chỉ có một trường `int`, việc chép trường đó đủ tạo dữ liệu độc lập cho mô hình này. Sửa `independent[0].value` thành 5 không quay lại sửa nguồn đang giữ 99.

## 6. Mảng nhiều chiều là bẫy thường gặp

`int[][]` không phải một mảng có các ô trực tiếp đều là `int`. Các ô của mảng ngoài chứa tham chiếu đến các `int[]` con; các mảng con có thể khác độ dài hoặc là `null`.

Khi gọi `matrix.clone()`, chỉ mảng ngoài mới được tạo. Các hàng vẫn được dùng chung. Vì vậy `outerCopy[0][0] = 8` trong ví dụ làm hàng đầu của `matrix` cũng đổi thành `[8, 2]`. Hợp đồng clone của mảng nhiều chiều không tự clone các mảng con. [Thành viên và clone của mảng](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html#jls-10.7)

`copyRows` trong ví dụ tạo mảng ngoài mới rồi clone từng hàng primitive khác `null`. Sau bước đó, sửa một ô số ở hàng của `rowCopy` không ảnh hưởng đến hàng nguồn.

Nhưng đừng áp dụng kết luận đó thiếu điều kiện cho `Person[][]`. Clone từng hàng chỉ tạo những mảng hàng mới; các ô trong hàng vẫn chứa tham chiếu đến `Person`. Nếu `Person` có thể thay đổi, cần xác định có phải tạo bản sao cho từng `Person` hay không.

Trường hợp nhiều ô nguồn cùng trỏ đến **cùng một hàng** cũng cần hợp đồng rõ ràng. Hàm `copyRows` hiện tại tạo bản sao cho mỗi vị trí hàng, nên không giữ quan hệ dùng chung hàng trong nguồn. Độc lập khỏi nguồn và giữ nguyên mọi quan hệ chia sẻ bên trong là hai yêu cầu khác nhau.

## 7. Chọn công cụ sao chép phù hợp

| Công cụ | Ai tạo mảng đích? | Giữ hay đổi độ dài? | Có tự sao chép đối tượng phần tử không? |
| --- | --- | --- | --- |
| `array.clone()` | Lời gọi tạo mảng mới | Giữ độ dài và kiểu mảng thực tế | Không |
| `Arrays.copyOf(array, newLength)` | Phương thức tạo mảng mới | Độ dài theo `newLength` | Không |
| `Arrays.copyOfRange(array, from, to)` | Phương thức tạo mảng mới | Độ dài theo khoảng yêu cầu | Không |
| `System.arraycopy(...)` | Bên gọi cung cấp mảng đích | Không đổi độ dài đích | Không |
| Vòng lặp và constructor/phương thức sao chép phần tử | Ứng dụng quyết định | Theo nhu cầu | Có thể, nếu mã ứng dụng thực sự làm điều đó |

Với mảng một chiều, `clone()` là cách ngắn gọn nếu chỉ cần mảng mới cùng độ dài; kiểu trả về của biểu thức clone mảng cho phép gán về đúng kiểu mảng. Điều đó không có nghĩa phải làm cho lớp phần tử triển khai `Cloneable`: clone mảng không gọi `clone()` trên từng đối tượng phần tử. [Hợp đồng clone](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html#clone())

`System.arraycopy` hữu ích khi muốn chép vào vị trí đã có của một mảng đích, kể cả trường hợp vùng nguồn/đích cùng mảng chồng lấn. Với mảng tham chiếu, nó vẫn chỉ chép các giá trị tham chiếu. [Tài liệu System.arraycopy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int))

### Phần mở rộng được điền giá trị mặc định

Nếu `Arrays.copyOf` yêu cầu mảng dài hơn nguồn, phần mới nhận giá trị mặc định: `0` cho `int`, `false` cho `boolean`, `null` cho kiểu tham chiếu. Độ dài ngắn hơn thì chỉ giữ phần đầu tương ứng. `newLength` âm gây `NegativeArraySizeException`; nguồn `null` không được coi là mảng rỗng. [Các overload copyOf trong Arrays](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html)

Trong chương trình, mở rộng `{1, 2}` thành độ dài 4 tạo `[1, 2, 0, 0]`; mở rộng `Box[]` độ dài 3 thành 4 thêm một ô `null`. Không tự tạo `Box(0)` cho ô mới.

`copyOfRange` cũng không phải cơ chế sao chép sâu; lựa chọn một khoảng khác chỉ thay những ô nguồn được đưa sang đích. Khi dùng công cụ đó, còn phải kiểm tra quy tắc chỉ số `from`/`to` của chính phương thức, không suy ra từ phép cắt chuỗi hoặc API khác.

## 8. Kiểu khai báo không thay được kiểu mảng thực tế

Trong phần cuối của chương trình:

```java
Number[] source = new Integer[] {1, 2};
Number[] sameRuntimeType = Arrays.copyOf(source, 3);
```

Biến có kiểu khai báo `Number[]`, nhưng đối tượng nguồn thực tế là `Integer[]`. Overload `copyOf` này tạo bản sao có cùng kiểu mảng thực tế với nguồn; mảng mới vẫn chỉ nhận phần tử tương thích với `Integer`.

Vì thế `sameRuntimeType[2] = 3.5` biên dịch được thông qua kiểu `Number[]`, nhưng thất bại lúc chạy bằng `ArrayStoreException`. Khi muốn một mảng thực tế `Number[]`, dùng overload có kiểu đích:

```java
Number[] widened = Arrays.copyOf(source, 3, Number[].class);
widened[2] = 3.5;
```

Thay kiểu mảng đích không nhân bản đối tượng phần tử. Hai số nguyên đầu vẫn được sao chép dưới dạng tham chiếu đến các `Integer`. Trong ví dụ chúng là giá trị bất biến nên việc dùng chung không tạo vấn đề sửa đổi nội dung.

Các mảng primitive không có phép mở rộng kiểu mảng tương tự từ `int[]` thành `long[]`. `System.arraycopy` cũng không tự chuyển từng `int` sang `long`. Nếu cần chuyển kiểu giá trị, hãy viết vòng lặp hoặc chọn công cụ chuyển đổi phù hợp; đó là một bước chuyển đổi dữ liệu, không chỉ chép mảng.

## 9. Sao chép sâu phải theo hợp đồng dữ liệu

Không có một dòng `Arrays.copyOf` nào tự biết ứng dụng muốn nhân bản đến đâu. Với `Customer` chứa một `Address` có thể thay đổi, một constructor chỉ gán `this.address = other.address` vẫn làm hai khách hàng dùng chung địa chỉ.

Khi thiết kế bản sao độc lập, xác định:

1. Đối tượng nào có thể thay đổi và phải được tách ra?
2. Giá trị bất biến nào có thể dùng chung an toàn?
3. `null` là hợp lệ hay cần bị từ chối?
4. Nếu hai ô nguồn cùng trỏ đến một đối tượng, bản sao có phải tiếp tục giữ quan hệ đó không?
5. Nếu đồ thị đối tượng có chu trình, chiến lược sao chép xử lý thế nào để không lặp vô hạn?

`copyBoxes` trong chương trình chỉ giải quyết mô hình `Box` rất nhỏ. Nếu hai ô nguồn cùng trỏ đến một `Box`, hàm sẽ tạo hai `Box` riêng biệt ở đích. Đây có thể đúng hoặc sai tùy ý nghĩa nghiệp vụ; không gọi nó là lời giải sao chép mọi đồ thị đối tượng.

Không sao chép sâu chỉ vì tên gọi nghe an toàn hơn. Dữ liệu bất biến dùng chung thường tiết kiệm bộ nhớ và giữ mô hình đơn giản. Chọn mức tách biệt cần thiết cho bên sử dụng thay vì tự động nhân bản mọi đối tượng có thể đi tới.

## 10. Lưu ý khi dùng ở biên API và khi kiểm thử

### Bảo vệ mảng không đồng nghĩa bảo vệ phần tử

Một getter trả `Arrays.copyOf(internal, internal.length)` ngăn bên gọi thay ô của mảng nội bộ thông qua mảng trả về. Nhưng nếu phần tử là đối tượng có thể thay đổi, bên gọi vẫn có thể sửa đối tượng dùng chung qua `result[0].set...`.

Tương tự, constructor sao chép mảng đầu vào tránh việc bên gọi thay ô nguồn sau đó làm đổi mảng đã giữ. Nó chưa cách ly được các đối tượng phần tử có thể thay đổi. Cần chọn cả hợp đồng sở hữu mảng và hợp đồng sở hữu phần tử.

### Không dùng equals của mảng để chứng minh nội dung

`a == b` kiểm tra hai tham chiếu có cùng chỉ đến một mảng hay không. `a.equals(b)` với mảng cũng không tự so sánh từng phần tử. Khi kiểm tra nội dung, dùng `Arrays.equals` cho mảng một chiều hoặc `Arrays.deepEquals` phù hợp với mảng lồng nhau.

Tuy nhiên, nội dung bằng nhau không chứng minh đã tách biệt. Sau khi kiểm tra giá trị ban đầu, cần sửa một phía và kiểm tra phía kia có giữ nguyên theo hợp đồng hay không. Với mảng tham chiếu, kiểm tra cả thao tác thay ô và thao tác sửa đối tượng phần tử.

### Không coi sao chép là ảnh chụp nguyên tử giữa các luồng

Nếu luồng khác đang chỉnh mảng nguồn hoặc đối tượng phần tử trong lúc sao chép, việc có mảng đích mới không tự bảo đảm một ảnh chụp nhất quán tại một thời điểm. Cần quy tắc đồng bộ hoặc dữ liệu bất biến phù hợp với yêu cầu nhất quán của ứng dụng.

### Không giả định lỗi chép vào mảng có sẵn sẽ tự hoàn tác

Với `System.arraycopy` giữa các mảng tham chiếu, nếu gặp một phần tử không lưu được vào kiểu mảng đích, có thể đã có các phần tử trước đó được chép trước khi `ArrayStoreException` xuất hiện. Không coi lời gọi thất bại là một giao dịch tự quay lại trạng thái ban đầu; nếu cần chỉ công bố kết quả khi hoàn tất, hãy cân nhắc chép/kiểm tra vào mảng tạm thích hợp trước.

## 11. Bài tập phân biệt mức sao chép

- Với `int[]`, so sánh phép gán `b = a` và `b = a.clone()`. Sau `b[0] = 7`, nguồn đổi trong trường hợp nào?
- Thêm một `Box` rồi đặt cùng tham chiếu đó vào hai ô nguồn. Gọi `copyBoxes`; bản sao hiện tại còn giữ quan hệ hai ô cùng đối tượng không?
- Thay `Box` bằng một kiểu chỉ có trạng thái bất biến. Khi nào sao chép mảng ngoài đã đủ cho nhu cầu của bên gọi?
- Tạo `int[][]` có một hàng `null` và một hàng rỗng. Kiểm tra `copyRows` giữ đúng hai trạng thái đó và các hàng khác độc lập.
- Trong ví dụ kiểu mảng thực tế, thay `Integer[]` nguồn bằng `Number[]` thực tế rồi dự đoán `sameRuntimeType[2] = 3.5` còn ném lỗi hay không.

Trước mỗi lần sao chép, hãy trả lời rõ: cần tách **biến tham chiếu**, **các ô của mảng**, hay cả **trạng thái các đối tượng mà phần tử trỏ đến**. Ba yêu cầu đó dẫn đến những đoạn mã khác nhau.
