# `Objects.deepEquals()` và cách xử lý hai đối số

`java.util.Objects.deepEquals(Object a, Object b)` là phương thức tiện ích để kiểm tra **hai đối số có bằng nhau không**, đồng thời xử lý **mảng và các mảng lồng nhau** theo nội dung. Điểm khác biệt quan trọng so với `Objects.equals(a, b)` là: khi cả hai đối số là mảng, `deepEquals` có khả năng so sánh các phần tử tương ứng, kể cả phần tử là một mảng khác; còn `Objects.equals` thường dựa vào `equals` của chính mảng, tức so sánh danh tính.

Điều này hữu ích khi dữ liệu gồm `int[]`, `String[]`, `int[][]`, `Object[]` chứa nhiều loại mảng, hoặc cấu trúc lồng nhau. Tuy nhiên, **`deepEquals` không tự đi sâu vào mọi trường của một đối tượng Java thông thường**: nếu hai đối số không phải mảng, kết quả vẫn dựa trên `equals` của đối tượng bên trái.

## 1. Khai báo và ý nghĩa

Phương thức thuộc `java.util.Objects`:

~~~java
public static boolean deepEquals(Object a, Object b)
~~~

Hai tham số đều kiểu `Object`, vì vậy bạn có thể truyền một đối tượng thông thường, một mảng nguyên thủy như `int[]`, một mảng đối tượng như `String[]`, mảng nhiều chiều như `int[][]`, hoặc `null`. Không cần ép một mảng nguyên thủy thành `Object[]`.

Tóm tắt hành vi:

| Hai đối số | Kết quả |
| --- | --- |
| Cùng một tham chiếu, kể cả đều `null` | `true`. |
| Một đối số là `null`, đối số kia không `null` | `false`. |
| Cả hai là mảng đối tượng (`Object[]` hoặc các kiểu mảng tương thích) | So sánh phần tử theo thứ tự và tiếp tục đi sâu khi phần tử là mảng. |
| Cả hai là mảng nguyên thủy cùng kiểu, ví dụ `int[]` | So sánh nội dung từng phần tử theo quy tắc của `Arrays.equals` tương ứng. |
| Cả hai là mảng lồng, ví dụ `int[][]` | So các mảng con tương ứng một cách đệ quy. |
| Không phải cả hai đều là mảng | Về cơ bản sử dụng `a.equals(b)` sau khi xử lý `null`/cùng tham chiếu; không tự khám phá mọi trường. |

Các đối số là **cùng mảng** thì luôn bằng nhau theo nhánh kiểm tra tham chiếu trước tiên, kể cả bên trong mảng có các cấu trúc phức tạp. Với **hai mảng độc lập**, `deepEquals` mới cần kiểm tra các phần tử.

### Thứ tự xử lý quan trọng

Có thể hiểu quy trình chính như sau:

1. Nếu `a == b`, trả `true` ngay. Trường hợp này cũng bao gồm `a == null` và `b == null`.
2. Nếu đúng một đối số là `null`, trả `false`.
3. Với hai đối số không `null`, thực hiện phép so sánh sâu thích hợp cho mảng: nếu chúng là mảng đối tượng thì duyệt phần tử và có thể đi sâu vào mảng con; nếu là hai mảng nguyên thủy cùng loại thì so nội dung; các trường hợp còn lại sử dụng ngữ nghĩa `equals` phù hợp.

Đây là mô hình hành vi để học, không phải lời hứa về thứ tự từng phép gọi nội bộ của mọi bản JDK. Điều cần nhớ là **so mảng theo nội dung khi phù hợp, xử lý `null` an toàn, còn đối tượng không phải mảng vẫn phụ thuộc `equals`**.

## 2. Ví dụ Java 17+: hai đối số, `null`, mảng và đối tượng thường

Tệp **`DeepEqualsArgumentsDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class DeepEqualsArgumentsDemo {
    public static void main(String[] args) {
        System.out.println(Objects.deepEquals(null, null));
        System.out.println(Objects.deepEquals(null, new int[] {1, 2}));

        int[] first = {1, 2};
        int[] second = {1, 2};
        int[] alias = first;

        System.out.println(first == second);
        System.out.println(Objects.equals(first, second));
        System.out.println(Objects.deepEquals(first, second));
        System.out.println(Objects.deepEquals(first, alias));
        System.out.println(Objects.deepEquals(first, new int[] {1, 3}));
        System.out.println(Objects.deepEquals(first, new long[] {1, 2}));

        String left = new String("Java");
        String right = new String("Java");
        System.out.println(left == right);
        System.out.println(Objects.deepEquals(left, right));

        String[] names1 = {"Lan", "An"};
        String[] names2 = {"Lan", "An"};
        System.out.println(Objects.equals(names1, names2));
        System.out.println(Objects.deepEquals(names1, names2));
        System.out.println(Arrays.equals(names1, names2));
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac DeepEqualsArgumentsDemo.java
java DeepEqualsArgumentsDemo
~~~

Kết quả chuẩn:

~~~text
true
false
false
false
true
true
false
false
false
true
false
true
true
~~~

Giải thích theo nhóm:

- `deepEquals(null, null)` trả `true`; chỉ một bên `null` thì `false`. Vì thế dùng phương thức này không gây `NullPointerException` chỉ do một tham số là `null`.
- Hai `int[]` độc lập chứa `{1, 2}` có `first == second` là `false`. `Objects.equals(first, second)` cũng là `false` vì `int[]` không override `Object.equals` để so phần tử. Nhưng `Objects.deepEquals(first, second)` là `true`.
- `alias = first` là cùng tham chiếu, nên `deepEquals(first, alias)` là `true`. Nếu thay `2` bằng `3`, nội dung khác nên `false`. Mảng `int[]` và `long[]` chứa những số trông giống nhau vẫn là hai kiểu mảng nguyên thủy khác nhau, không được `deepEquals` tự ép thành một kiểu chung.
- Hai `String` độc lập có `==` là `false` nhưng `deepEquals` là `true`: với chuỗi không phải mảng, việc so sánh dùng `String.equals`, không phải phản chiếu/so từng trường nội bộ của chuỗi.
- Với hai `String[]` độc lập, `Objects.equals` trả `false`, trong khi `Objects.deepEquals` và `Arrays.equals` cùng trả `true` khi phần tử tương ứng có cùng nội dung.

Lưu ý: `Arrays` được import trong ví dụ để trình bày phép so sánh mảng cùng cấp; nó không phải yêu cầu khi chỉ gọi `Objects.deepEquals`.

## 3. Mảng lồng nhau: “deep” diễn ra ở đâu?

Xét hai ma trận `int[][]`. Trong Java, đây là **mảng chứa các tham chiếu tới mảng `int[]`**, nên việc so mảng ở tầng ngoài phải tiếp tục so nội dung mảng con.

~~~java
int[][] a = {{1, 2}, {3}};
int[][] b = {{1, 2}, {3}};

System.out.println(a == b);                    // false
System.out.println(java.util.Arrays.equals(a, b));     // false
System.out.println(java.util.Arrays.deepEquals(a, b)); // true
System.out.println(java.util.Objects.deepEquals(a, b)); // true
~~~

Đây là đoạn mã minh họa trong thân một phương thức. `Arrays.equals(a, b)` ở đây chỉ so các **phần tử của mảng tầng ngoài**; mỗi phần tử là `int[]`, mà `int[]` không có `equals` theo nội dung. `Arrays.deepEquals(a, b)` và `Objects.deepEquals(a, b)` đi sâu vào từng `int[]` nên cho `true`.

Có thể hình dung phép so sánh:

~~~text
a: int[][{1, 2}, {3}]
b: int[][{1, 2}, {3}]

Tầng ngoài: cùng số phần tử?              Có
  a[0] và b[0]: so {1, 2} với {1, 2}     Bằng
  a[1] và b[1]: so {3} với {3}           Bằng
Kết luận:                                 true
~~~

Với một mảng `Object[]` chứa các phần tử hỗn hợp, `deepEquals` cũng biết phân biệt phần tử thường và phần tử mảng:

~~~java
Object[] x = {
    "Java",
    new int[] {1, 2},
    new Object[] {"nested", new long[] {9, 10}}
};
Object[] y = {
    new String("Java"),
    new int[] {1, 2},
    new Object[] {"nested", new long[] {9, 10}}
};

System.out.println(java.util.Objects.equals(x, y));     // false
System.out.println(java.util.Objects.deepEquals(x, y)); // true
~~~

`"Java"` và `new String("Java")` có nội dung bằng nhau; `int[]` cùng phần tử và `long[]` bên trong cùng phần tử. Hai mảng ngoài khác tham chiếu nhưng bằng nhau khi so sâu.

**Không có chuyện Java tự “flatten” mảng:** cách phân tầng, độ dài và thứ tự phần tử vẫn có ý nghĩa. Ví dụ `int[][] {{1, 2}, {3}}` **không** bằng `int[][] {{1}, {2, 3}}`, dù ghép tất cả số theo thứ tự đều có thể ra `1, 2, 3`.

## 4. `Objects.deepEquals`, `Objects.equals` và `Arrays.equals`

Ba API này trả lời các câu hỏi hơi khác nhau:

| API | Tham số | Cách so sánh nổi bật |
| --- | --- | --- |
| `Objects.equals(a, b)` | Hai `Object` | An toàn `null`, nếu cả hai khác `null` thì gọi `a.equals(b)`. Mảng thường so tham chiếu. |
| `Objects.deepEquals(a, b)` | Hai `Object` | An toàn `null`; nếu hai đối số là mảng, so sâu thích hợp cho mảng; nếu là đối tượng thường, dựa trên `equals`. |
| `Arrays.equals(a, b)` | Hai mảng một chiều có overload tương ứng | So phần tử tầng hiện tại; với mảng lồng chứa mảng con, không tự động so sâu mảng con. |
| `Arrays.deepEquals(a, b)` | Hai `Object[]` | So sâu phần tử/mảng con. Có thể dùng với `int[][]` vì mỗi `int[][]` là một mảng tham chiếu chứa `int[]`; không gọi trực tiếp với hai `int[]`. |

Một điểm rất quan trọng về kiểu dữ liệu: `Arrays.deepEquals(Object[] a, Object[] b)` yêu cầu **mảng tham chiếu ở tầng ngoài**. Vì `int[]` không phải `Object[]`, lệnh `Arrays.deepEquals(new int[]{1}, new int[]{1})` **không biên dịch**. Với hai `int[]`, dùng `Arrays.equals` hoặc `Objects.deepEquals`.

### Chọn công cụ theo dữ liệu

- Hai `int[]` hoặc `double[]` cùng loại: `Arrays.equals` thể hiện rõ ý định so nội dung một chiều.
- Hai `String[]` một chiều: `Arrays.equals` là đủ nếu chỉ cần so từng `String`.
- Hai `int[][]` hoặc hai `Object[]` chứa mảng con: `Arrays.deepEquals` hoặc `Objects.deepEquals` khi muốn so sâu.
- Hai tham số đang có kiểu `Object`, có thể là mảng hoặc không: `Objects.deepEquals` giúp xử lý cả hai trường hợp theo quy tắc đã nêu.
- Hai đối tượng thông thường, không liên quan mảng: `Objects.equals` thường bộc lộ rõ mục đích hơn; dùng `Objects.deepEquals` không mang lại phép so sâu trường dữ liệu bên trong đối tượng.

## 5. “Deep” không có nghĩa là tự so sánh mọi thuộc tính của class

Giả sử một class `Box` chứa trường `int[]`, nhưng **không override `equals`**. Khi đưa hai `Box` độc lập vào `Objects.deepEquals`, kết quả vẫn là `false`, ngay cả khi hai mảng bên trong cùng nội dung.

Tệp **`DeepEqualsObjectDemo.java`**:

~~~java
import java.util.Objects;

public class DeepEqualsObjectDemo {
    static final class Box {
        private final int[] values;

        Box(int[] values) {
            this.values = values;
        }
    }

    record ArrayRecord(int[] values) {}

    public static void main(String[] args) {
        Box first = new Box(new int[] {4, 5});
        Box second = new Box(new int[] {4, 5});

        System.out.println(first == second);
        System.out.println(Objects.deepEquals(first, second));
        System.out.println(Objects.deepEquals(first.values, second.values));

        ArrayRecord r1 = new ArrayRecord(new int[] {4, 5});
        ArrayRecord r2 = new ArrayRecord(new int[] {4, 5});

        System.out.println(r1.equals(r2));
        System.out.println(Objects.deepEquals(r1, r2));
        System.out.println(Objects.deepEquals(r1.values(), r2.values()));
    }
}
~~~

Chạy:

~~~bash
javac DeepEqualsObjectDemo.java
java DeepEqualsObjectDemo
~~~

Kết quả chuẩn:

~~~text
false
false
true
false
false
true
~~~

Phân tích:

- `Box` là class thường không override `equals`, nên `Box.equals` thừa hưởng từ `Object` và chỉ so danh tính. `Objects.deepEquals(first, second)` không tự dò trường `values`: kết quả `false`.
- Nhưng khi truyền **chính hai mảng `first.values` và `second.values`**, `deepEquals` so phần tử nên trả `true`.
- Record Java sinh `equals` dựa trên component, nhưng với component là **mảng**, phép so vẫn theo danh tính mảng khi hai record khác nhau. Do đó hai `ArrayRecord` độc lập chứa `int[]` cùng nội dung vẫn `equals` là `false`.
- Muốn hai instance của class hoặc record **bằng nhau theo nội dung mảng**, bạn phải tự xây dựng ngữ nghĩa `equals`/ `hashCode` của kiểu bao ngoài, không chỉ thay lời gọi ngoài thành `Objects.deepEquals(box1, box2)`.

Điều này giúp phân biệt **so sánh sâu trên mảng là đối số** với **so sánh sâu xuyên qua các trường của bất kỳ object nào**. Java chỉ cung cấp trường hợp thứ nhất trong `Objects.deepEquals`.

## 6. Dùng `Objects.deepEquals` trong `equals` của một value object

Một ứng dụng phổ biến là class giữ cấu trúc mảng lồng và muốn định nghĩa bằng nhau dựa trên toàn bộ phần tử. Khi tự override `equals`, có thể sử dụng `Objects.deepEquals(data, that.data)`. Nhưng **`hashCode` phải sử dụng thuật toán hash tương ứng với phép so sâu**.

Tệp **`MatrixKeyDemo.java`** (Java 17+):

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class MatrixKeyDemo {
    static final class MatrixKey {
        private final int[][] data;

        MatrixKey(int[][] source) {
            Objects.requireNonNull(source);
            data = new int[source.length][];
            for (int i = 0; i < source.length; i++) {
                int[] row = Objects.requireNonNull(source[i]);
                data[i] = Arrays.copyOf(row, row.length);
            }
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof MatrixKey that)) {
                return false;
            }
            return Objects.deepEquals(data, that.data);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(data);
        }
    }

    public static void main(String[] args) {
        int[][] source = {{1, 2}, {3}};
        MatrixKey first = new MatrixKey(source);
        MatrixKey sameValue = new MatrixKey(new int[][] {{1, 2}, {3}});
        MatrixKey different = new MatrixKey(new int[][] {{1, 2}, {4}});

        System.out.println(first == sameValue);
        System.out.println(first.equals(sameValue));
        System.out.println(first.hashCode() == sameValue.hashCode());
        System.out.println(first.equals(different));

        Map<MatrixKey, String> names = new HashMap<>();
        System.out.println(names.put(first, "old"));
        System.out.println(names.put(sameValue, "new"));
        System.out.println(names.put(different, "other"));
        System.out.println(names.size());
        System.out.println(names.get(first));

        source[0][0] = 99;
        System.out.println(first.equals(sameValue));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac MatrixKeyDemo.java
java MatrixKeyDemo
~~~

Kết quả chuẩn:

~~~text
false
true
true
false
null
old
null
2
new
true
~~~

Ý nghĩa:

1. `first` và `sameValue` là hai đối tượng `MatrixKey` độc lập, nhưng dữ liệu ma trận giống nhau nên `equals` trả `true`.
2. `hashCode` dùng `Arrays.deepHashCode(data)` để hai ma trận bằng nhau theo `Objects.deepEquals` cũng có mã băm bằng nhau. Đây là một yêu cầu **bắt buộc** của hợp đồng `equals`/`hashCode`.
3. `different` chứa giá trị `4` ở vị trí khác nên không bằng `first`.
4. Thêm `sameValue` vào `HashMap` thay giá trị của khóa logic đã có; `size()` không tăng. Khóa `different` tạo entry thứ hai.
5. Constructor sao chép **từng mảng con**, nên sửa `source[0][0]` bên ngoài không làm thay đổi dữ liệu trong `first`. Điều này giúp khóa có hash ổn định sau khi dùng trong `HashMap`.

Ví dụ cho phép các hàng có độ dài khác nhau (`int[][]` là mảng của các mảng) nhưng từ chối hàng `null` bằng `requireNonNull`. Đó là quyết định thiết kế của `MatrixKey`, không phải giới hạn của `Objects.deepEquals`: bản thân phép so sâu có thể so các vị trí `null` tương ứng.

**Không thay `Arrays.deepHashCode(data)` bằng `Objects.hashCode(data)`:** đối với mảng, `Objects.hashCode` đi theo `hashCode` của chính mảng, vốn không phải hash sâu theo nội dung. Hai `MatrixKey` bằng nhau theo dữ liệu mảng có thể nhận hash không khớp và làm hỏng cách dùng làm key trong hash collection.

## 7. Những trường hợp góc quan trọng

### 7.1. Cả hai đối số `null`

~~~java
Objects.deepEquals(null, null);             // true
Objects.deepEquals(null, new Object[0]);    // false
Objects.deepEquals(new int[0], new int[0]); // true
~~~

Hai mảng rỗng khác tham chiếu vẫn bằng nhau về nội dung nếu cùng kiểu/cấu trúc phù hợp. Mảng rỗng không giống `null`.

### 7.2. Hai mảng có cùng dữ liệu nhưng không cùng loại mảng nguyên thủy

~~~java
Objects.deepEquals(new int[] {1, 2}, new long[] {1, 2}); // false
Objects.deepEquals(new int[] {1}, new int[] {1});         // true
~~~

`Objects.deepEquals` **không thực hiện chuyển kiểu số** để coi `int[]` và `long[]` là cùng cấu trúc giá trị. Nếu nghiệp vụ muốn so sau chuẩn hóa kiểu, phải định nghĩa phép chuyển/so riêng.

### 7.3. Mảng tham chiếu có thể có kiểu runtime khác nhau

~~~java
Objects.deepEquals(
    new String[] {"Java"},
    new Object[] {"Java"}
); // true
~~~

Cả hai đối số đều là mảng tham chiếu (`Object[]`) với một phần tử có nội dung bằng nhau; phép so sâu có thể trả `true` dù lớp mảng runtime khác nhau. Đừng hiểu `deepEquals` là yêu cầu `getClass()` của hai mảng phải giống hệt nhau.

### 7.4. Cách so `NaN` và `+0.0/-0.0` trong mảng số thực

Các phép `Arrays.equals` cho mảng `float[]`/`double[]` có quy tắc theo bit chuẩn hóa tương ứng với `Float.equals`/`Double.equals`: các biểu diễn `NaN` được coi là bằng nhau và `+0.0` khác `-0.0`. Vì `Objects.deepEquals` dùng ngữ nghĩa mảng tương ứng, cần chú ý:

~~~java
Objects.deepEquals(
    new double[] {Double.NaN},
    new double[] {Double.NaN}
); // true

Objects.deepEquals(
    new double[] {+0.0},
    new double[] {-0.0}
); // false
~~~

Nếu nghiệp vụ cần quy tắc số thực khác, không nên tự giả định `deepEquals` dùng đúng phép so mong muốn. Hãy định nghĩa phép so phù hợp, đồng thời cân nhắc hợp đồng bằng nhau và mã băm nếu triển khai `equals`.

### 7.5. Mảng chứa tham chiếu vòng

Nếu mảng `Object[]` chứa **chính nó** làm phần tử, hoặc các mảng tham chiếu lẫn nhau tạo chu trình, phép duyệt sâu có thể tiếp tục đệ quy không kết thúc và gây lỗi như `StackOverflowError`. Tài liệu `Arrays.deepEquals` không định nghĩa hành vi đối với mảng chứa tham chiếu vòng. Không dùng `Objects.deepEquals` như một thuật toán so sánh đồ thị tổng quát có khả năng xử lý chu trình; nếu dữ liệu là đồ thị, hãy thiết kế thuật toán có theo dõi các nút đã thăm.

### 7.6. Phần tử là đối tượng tùy biến

~~~java
class Item {
    final int id;
    Item(int id) { this.id = id; }
}

Object[] left = {new Item(1)};
Object[] right = {new Item(1)};
System.out.println(java.util.Objects.deepEquals(left, right)); // false
~~~

Đoạn trên là mã minh họa nằm trong ngữ cảnh khai báo lớp và phương thức phù hợp. Vì `Item` không override `equals`, so sánh hai `Item` bên trong mảng vẫn chỉ theo danh tính. `deepEquals` **không tự mở từng `Item` để so trường `id`**. Nếu muốn phần tử `Item` bằng nhau theo giá trị, cần cài đặt `Item.equals` và `Item.hashCode` thích hợp.

## 8. Sai lầm thường gặp và cách tránh

1. **Cho rằng `Objects.equals` đã đủ cho mảng.** Với hai `int[]` hoặc `String[]` độc lập có cùng nội dung, `Objects.equals` thường trả `false`. Chọn `Arrays.equals` hoặc `Objects.deepEquals` khi muốn so nội dung.
2. **Dùng `Arrays.equals` cho mảng lồng rồi chờ so sâu.** Đối với `int[][]`, các phần tử ở tầng ngoài là các `int[]`. Chọn `Arrays.deepEquals` hoặc `Objects.deepEquals` nếu muốn so từng mảng con.
3. **Tưởng `Objects.deepEquals` phản chiếu mọi trường của class.** Với hai object thông thường, phương thức dựa vào `equals` của class. Nó không tự so các trường hay property lồng nhau.
4. **Dùng `Objects.deepEquals` trong `equals` nhưng quên sửa `hashCode`.** Với mảng nhiều chiều, dùng `Arrays.deepHashCode` tương ứng để tránh vi phạm hợp đồng của các hash collection.
5. **Để cấu trúc mảng có thể thay đổi sau khi làm key của `HashMap`.** Khi dữ liệu dùng trong `equals`/`hashCode` thay đổi, map có thể không tìm được entry. Dùng bản sao bảo vệ và thiết kế value object bất biến khi phù hợp.
6. **Dùng so sâu trên đồ thị có chu trình.** Trường hợp mảng chứa chính nó hoặc chứa vòng qua các mảng khác không được đảm bảo an toàn.
7. **Coi “giá trị tương đương theo nghiệp vụ” và “`deepEquals` bằng nhau” là một.** `deepEquals` tôn trọng kiểu mảng, thứ tự phần tử và `equals` của đối tượng thành phần; không tự chuẩn hóa văn bản, số liệu, thứ tự hay định danh nghiệp vụ.

## 9. Quy trình chọn phép so sánh

Khi phải so sánh hai giá trị trong Java:

1. **Kiểm tra loại dữ liệu thực tế:** đối tượng thường, mảng nguyên thủy, mảng tham chiếu, mảng lồng hay một đối tượng chứa trường là mảng.
2. **Nếu muốn biết cùng instance**, sử dụng `==` với tham chiếu.
3. **Nếu chỉ muốn so giá trị của hai đối tượng thường**, dùng `Objects.equals(a, b)` khi cần xử lý `null`, bảo đảm kiểu đó có `equals` phù hợp.
4. **Nếu là mảng một chiều rõ kiểu**, dùng `Arrays.equals(a, b)`.
5. **Nếu là mảng nhiều tầng**, chọn `Arrays.deepEquals` với mảng `Object[]` ở tầng ngoài hoặc `Objects.deepEquals` với hai giá trị kiểu `Object`.
6. **Nếu viết value object chứa mảng**, cài đặt `equals` so trường mảng theo nội dung và `hashCode` theo cùng dữ liệu; bảo vệ khỏi thay đổi ngoài ý muốn.
7. **Nếu có yêu cầu đặc biệt** như so số theo dung sai, bỏ qua thứ tự, chuẩn hóa chữ, hoặc dữ liệu có vòng tham chiếu, hãy viết thuật toán so sánh riêng phù hợp với hợp đồng và mục tiêu bài toán.

## 10. Câu hỏi tự kiểm tra

1. Vì sao `Objects.equals(new int[]{1,2}, new int[]{1,2})` là `false` nhưng `Objects.deepEquals(...)` là `true`?
2. Với hai đối số đều `null`, kết quả `Objects.deepEquals` là gì? Nếu đúng một đối số `null` thì sao?
3. Vì sao `Arrays.equals(a, b)` với hai `int[][]` độc lập cùng nội dung có thể trả `false`, trong khi `Arrays.deepEquals(a,b)` trả `true`?
4. Nếu `Box` có trường `int[] values` nhưng không override `equals`, gọi `Objects.deepEquals(box1,box2)` có tự so từng phần tử của `values` không?
5. Vì sao một class dùng `Objects.deepEquals(matrix1,matrix2)` trong `equals` nên dùng `Arrays.deepHashCode(matrix)` tương ứng trong `hashCode`?
6. `Objects.deepEquals(new int[]{1}, new long[]{1})` trả gì? Phương thức có tự chuyển `int` sang `long` không?
7. Nếu một mảng `Object[]` chứa tham chiếu tới chính nó, vì sao không thể giả định phép so sâu luôn kết thúc an toàn?

**Ghi nhớ:** `Objects.deepEquals(a, b)` nhận **hai đối số kiểu `Object`**, kiểm tra cùng tham chiếu/`null` trước, rồi so sánh **nội dung mảng, kể cả mảng lồng** khi cả hai đối số là mảng. Với các đối tượng thông thường, nó vẫn dựa vào `equals`. Khi dùng so sâu trong `equals` của class chứa mảng, luôn giữ `hashCode` tương ứng và bảo vệ dữ liệu khỏi thay đổi ngoài ý muốn.