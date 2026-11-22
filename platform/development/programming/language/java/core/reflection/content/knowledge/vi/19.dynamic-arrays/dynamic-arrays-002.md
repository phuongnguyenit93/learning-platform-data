# Tạo mảng nhiều chiều và ý nghĩa của danh sách kích thước trong Java Reflection

Khi kiểu phần tử, số chiều hoặc độ dài mảng chỉ được biết lúc chạy, Java cung cấp **java.lang.reflect.Array.newInstance(Class<?> componentType, int... dimensions)**. Phương thức tạo một mảng thật ở runtime, dùng **componentType** xác định kiểu và mảng số nguyên **dimensions** xác định độ dài các chiều cần cấp phát.

Quan trọng nhất: **mỗi phần tử của dimensions là độ dài của một chiều, theo thứ tự từ ngoài vào trong**. Đây không phải danh sách chỉ số, không phải giới hạn trên bao gồm, và cũng không phải các độ dài của những hàng khác nhau. Ví dụ:

~~~java
int[][] matrix = (int[][]) java.lang.reflect.Array.newInstance(int.class, 2, 3);
~~~

Kết quả tương đương về kiểu và hình dạng ban đầu với **new int[2][3]**: 2 hàng, mỗi hàng có 3 phần tử int mặc định bằng 0.

Bài học đi sâu vào ý nghĩa dimensions, đặc biệt khi **componentType vốn đã là array class**, cách cấp phát từng phần để dựng mảng răng cưa, trường hợp kích thước 0, ngoại lệ và thao tác kiểm chứng bằng Reflection.

## 1. Hai overload của Array.newInstance

Lớp java.lang.reflect.Array cung cấp:

~~~java
static Object newInstance(Class<?> componentType, int length)
static Object newInstance(Class<?> componentType, int... dimensions)
~~~

- **newInstance(componentType, length):** tạo một mảng ngoài có độ dài length, chứa phần tử thuộc componentType. Nếu componentType là kiểu mảng, phần tử ngoài là tham chiếu đến mảng con, ban đầu null.
- **newInstance(componentType, dimensions):** nhận một hay nhiều số nguyên để tạo các chiều ngoài tương ứng. Dạng int... cho phép truyền các số rời hoặc một int[].
- **Kết quả tĩnh là Object:** vì componentType có thể thay đổi tại runtime. Đối tượng thực tế vẫn là một Java array mang class đúng kiểu; có thể cast hoặc thao tác tiếp bằng Array.get, Array.set, Array.getLength.
- **componentType hợp lệ:** kiểu primitive như int.class, tham chiếu như String.class, hoặc class của mảng như String[].class. Không thể là void.class.

Ví dụ hai biểu thức đầu tạo mảng cùng hình dạng với biểu thức cuối, nhưng mỗi lần gọi đều cấp phát đối tượng mới:

~~~java
Object first = Array.newInstance(String.class, 4, 5);
Object second = Array.newInstance(String.class, new int[] {4, 5});
String[][] third = new String[4][5];
~~~

Các ví dụ sử dụng **import java.lang.reflect.Array;**. Cả first, second và third đều có runtime class String[][], nhưng không tham chiếu cùng một mảng.

## 2. Đọc chính xác danh sách dimensions

Với componentType là một class **không phải mảng**, số chiều kết quả bằng đúng **dimensions.length**:

| Gọi Array.newInstance | Kiểu runtime | Độ dài các chiều được cấp phát | Số slot cuối |
| --- | --- | --- | --- |
| (int.class, 5) | int[] | 5 | 5 |
| (int.class, 2, 3) | int[][] | 2 rồi 3 | 6 |
| (int.class, 2, 3, 4) | int[][][] | 2 rồi 3 rồi 4 | 24 |
| (String.class, 3, 2) | String[][] | 3 rồi 2 | 6 |
| (String.class, 2, 0, 4) | String[][][] | 2 rồi 0; chiều sâu không có vị trí tiếp cận | 0 |

Nếu truyền **{2, 3, 4}**, ta đọc:

1. **dimensions[0] = 2:** mảng ngoài chứa hai phần tử.
2. **dimensions[1] = 3:** mỗi phần tử ngoài chứa một mảng có ba phần tử.
3. **dimensions[2] = 4:** mỗi phần tử ở tầng hai chứa một mảng có bốn phần tử cuối.

Với int[][] kích thước 2 × 3, cấu trúc ban đầu là:

~~~text
int[][] data, data.length = 2
    data[0] -> int[3] = [0, 0, 0]
    data[1] -> int[3] = [0, 0, 0]

data[1][2] -> phần tử thứ ba của hàng thứ hai.
~~~

Chỉ số của chiều có độ dài 2 là 0 và 1; chỉ số của chiều có độ dài 3 là 0, 1 và 2. Nếu truy cập data[2] trong mảng ngoài dài 2, sẽ nhận **ArrayIndexOutOfBoundsException**.

**Tích các kích thước** có thể cho số vị trí phần tử cuối về mặt logic nếu toàn bộ các chiều đến kiểu phần tử cuối đều được cấp phát. Nó không cho biết trực tiếp số byte heap, vì Java cấp phát các đối tượng mảng con và overhead riêng.

## 3. Mảng nhiều chiều thực chất là mảng của mảng

Trong Java, int[][] là một mảng mà mỗi phần tử có kiểu int[]. Tương tự String[][][] chứa các phần tử có kiểu String[][]. Đây không phải mô hình bắt buộc mọi hàng luôn cùng kích thước.

Khi gọi Array.newInstance(int.class, 2, 3), Java tạo hình dạng ban đầu đều nhau: hai mảng con dài 3. Nhưng sau đó ta vẫn có thể thay một mảng con bằng mảng có độ dài khác:

~~~java
int[][] rows = new int[3][];
rows[0] = new int[1];
rows[1] = new int[4];
rows[2] = new int[2];

System.out.println(rows.length);     // 3
System.out.println(rows[1].length);  // 4
~~~

Đây là **mảng răng cưa (jagged/ragged array)**, có ba hàng dài 1, 4, 2. Mỗi hàng là đối tượng riêng, nên Java không có một thuộc tính bất biến bắt buộc mọi hàng đều dài như nhau.

**Cần phân biệt:** danh sách {1, 4, 2} đưa vào Array.newInstance(int.class, 1, 4, 2) sẽ tạo **mảng ba chiều**, không phải một mảng hai chiều có ba hàng dài 1, 4, 2.

## 4. Khi componentType đã là mảng: số chiều tăng thêm

Theo Javadoc, nếu componentType **không phải array class**, số chiều kết quả là số phần tử trong dimensions. Nhưng nếu componentType **đã là array class**, số chiều cuối bằng:

**rank của componentType + dimensions.length**

Các số trong dimensions dùng để cấp phát **những tầng mảng mới ở bên ngoài**. Các tầng vốn nằm trong array-typed component **chưa được cấp phát**; phần tử đại diện cho mảng con ở mức cuối được tạo ban đầu là null.

| Lời gọi | Kiểu runtime | Đã cấp phát |
| --- | --- | --- |
| Array.newInstance(String.class, 2) | String[] | 2 ô String, mặc định null |
| Array.newInstance(String.class, 2, 3) | String[][] | Hai hàng, mỗi hàng 3 ô String |
| Array.newInstance(String[].class, 2) | String[][] | Chỉ mảng ngoài dài 2; mỗi String[] ban đầu null |
| Array.newInstance(String[].class, 2, 3) | String[][][] | Hai chiều ngoài 2 × 3; mỗi String[] cuối ban đầu null |
| Array.newInstance(int[][].class, 2, 3) | int[][][][] | Hai tầng ngoài 2 × 3; mỗi int[][] tại tầng kế tiếp ban đầu null |

Hai lời gọi khác nhau có thể cho **cùng runtime type** nhưng cấp phát các tầng khác nhau:

~~~java
String[][] full = (String[][]) Array.newInstance(String.class, 2, 3);
String[][] outerOnly = (String[][]) Array.newInstance(String[].class, 2);

System.out.println(full[0].length); // 3
System.out.println(outerOnly[0]);    // null
~~~

Với outerOnly, truy cập outerOnly[0].length khi chưa gán sẽ ném **NullPointerException**, không phải trả 0. Ngược lại, full đã có các mảng con dài 3.

Có thể hình dung **Array.newInstance(String[].class, 2, 3)** tương đương về hình dạng ban đầu với **new String[2][3][]**. Kiểu có ba chiều nhưng chỉ hai chiều đầu được cấp phát.

### Class.getComponentType chỉ bỏ một tầng

~~~java
String[][][] values = (String[][][]) Array.newInstance(String[].class, 2, 3);
System.out.println(values.getClass().getTypeName()); // java.lang.String[][][]
System.out.println(values.getClass().getComponentType().getTypeName());
                                                   // java.lang.String[][]
~~~

Class.getComponentType() trên String[][][] trả String[][], vì một phần tử của mảng ngoài là mảng hai chiều. Muốn đi đến String.class phải tiếp tục bóc từng tầng:

~~~java
Class<?> leaf = values.getClass();
int rank = 0;
while (leaf.isArray()) {
    rank++;
    leaf = leaf.getComponentType();
}
// rank là 3, leaf là String.class
~~~

Đây là fragment sử dụng biến values vừa tạo ở trên. **Không đồng nhất rank của runtime type với số độ dài truyền vào** nếu componentType ban đầu đã là array class.

## 5. Chương trình Java 17+ hoàn chỉnh

Ví dụ bao quát cấp phát đầy đủ, độ dài 0, mảng răng cưa, componentType là mảng và các lỗi về kích thước.

Lưu nguyên văn vào file **MultiArrayDemo.java**:

~~~java
import java.lang.reflect.Array;

public class MultiArrayDemo {
    public static void main(String[] args) {
        int[][] grid = (int[][]) Array.newInstance(int.class, 2, 3);
        Array.setInt(Array.get(grid, 1), 2, 17);
        System.out.println("grid type=" + grid.getClass().getTypeName());
        System.out.println("grid lengths=" + Array.getLength(grid)
                + "x" + Array.getLength(Array.get(grid, 0)));
        System.out.println("grid default=" + grid[0][0] + ", changed=" + grid[1][2]);

        String[][][] zero = (String[][][]) Array.newInstance(String.class, 2, 0, 4);
        System.out.println("zero lengths=" + zero.length + "," + zero[0].length);

        String[][] ragged = (String[][]) Array.newInstance(String[].class, 2);
        System.out.println("ragged before=" + ragged[0]);
        ragged[0] = new String[] {"A"};
        ragged[1] = new String[] {"B", "C", "D"};
        System.out.println("ragged lengths=" + ragged[0].length + "," + ragged[1].length);

        String[][][] partial =
                (String[][][]) Array.newInstance(String[].class, 2, 3);
        System.out.println("partial type=" + partial.getClass().getTypeName());
        System.out.println("partial lengths=" + partial.length + "," + partial[0].length);
        System.out.println("partial innermost=" + partial[0][0]);
        System.out.println("partial component=" +
                partial.getClass().getComponentType().getTypeName());

        try {
            Array.newInstance(int.class, 2, -1);
        } catch (NegativeArraySizeException ex) {
            System.out.println("negative=" + ex.getClass().getSimpleName());
        }
        try {
            Array.newInstance(void.class, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("void=" + ex.getClass().getSimpleName());
        }
        try {
            Array.newInstance(int.class, new int[0]);
        } catch (IllegalArgumentException ex) {
            System.out.println("zero ranks=" + ex.getClass().getSimpleName());
        }
        try {
            Array.newInstance(int[][].class, new int[254]);
        } catch (IllegalArgumentException ex) {
            System.out.println("too many ranks=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 MultiArrayDemo.java
java MultiArrayDemo
~~~

**Stdout đã kiểm tra thực tế** với javac hỗ trợ --release 17:

~~~text
grid type=int[][]
grid lengths=2x3
grid default=0, changed=17
zero lengths=2,0
ragged before=null
ragged lengths=1,3
partial type=java.lang.String[][][]
partial lengths=2,3
partial innermost=null
partial component=java.lang.String[][]
negative=NegativeArraySizeException
void=IllegalArgumentException
zero ranks=IllegalArgumentException
too many ranks=IllegalArgumentException
~~~

Giải thích:

1. **grid:** int[][] gồm 2 × 3 slot, giá trị int mặc định bằng 0. Array.get(grid, 1) cho mảng int[] thứ hai; Array.setInt(..., 2, 17) gán slot thứ ba của mảng con.
2. **zero:** String[][][] với kích thước 2 × 0 × 4 vẫn hợp lệ. Mảng ngoài có hai slot, nhưng các mảng con thứ hai đều dài 0, không có vị trí [0][0] để tiếp tục xuống chiều cuối.
3. **ragged:** khi truyền String[].class cùng một độ dài 2, ta chỉ nhận mảng ngoài String[][] với phần tử con null. Sau đó gán lần lượt String[] dài 1 và 3.
4. **partial:** truyền String[].class với hai độ dài 2, 3 tạo String[][][]; hai tầng đầu được cấp phát, còn phần tử String[] ở tầng sâu là null. getComponentType() từ runtime class trả String[][], không phải String.
5. **negative:** độ dài bất kỳ âm dẫn đến NegativeArraySizeException.
6. **void / zero ranks / too many ranks:** tương ứng componentType không hợp lệ, không có chiều nào được cung cấp và yêu cầu 256 chiều khi đã có int[][].class thêm 254 chiều; đều ném IllegalArgumentException.

## 6. Tạo mảng răng cưa hoàn toàn bằng Reflection

Khi số hàng biết trước nhưng mỗi hàng có độ dài khác nhau, chỉ tạo chiều ngoài rồi cấp phát từng hàng:

~~~java
int[][] jagged = (int[][]) Array.newInstance(int[].class, 3);

for (int row = 0; row < jagged.length; row++) {
    int size = row + 1;
    Object inner = Array.newInstance(int.class, size);
    Array.set(jagged, row, inner);
}
~~~

Sau vòng lặp, ba hàng dài 1, 2, 3. Array.set nhận một **đối tượng int[]** để gán vào slot của int[][]; nó không nhận trực tiếp số int vì phần tử của mảng ngoài có kiểu int[].

Cú pháp Java tĩnh tương đương:

~~~java
int[][] jagged = new int[3][];
for (int row = 0; row < jagged.length; row++) {
    jagged[row] = new int[row + 1];
}
~~~

Nếu số chiều và kiểu thành phần đều biết lúc biên dịch, cú pháp **new** trực tiếp thường đơn giản và an toàn kiểu hơn. Reflection có lợi khi kiểu hoặc kích thước được xác định từ metadata/cấu hình lúc chạy.

### Tạo từ cấu hình động

Giả sử chương trình nhận danh sách cấu hình {2, 3, 4}:

~~~java
int[] sizes = {2, 3, 4};
Class<?> component = double.class;
Object data = Array.newInstance(component, sizes);
~~~

Runtime type của data là double[][][]. **sizes.length** là 3 chiều, **không** phải ba hàng dài lần lượt 2, 3, 4. Nếu muốn ba hàng răng cưa tương ứng, tạo double[3][] rồi cấp phát ba hàng riêng.

## 7. Đọc và ghi mảng nhiều chiều bằng Reflection

Các API hữu ích trong java.lang.reflect.Array:

| Phương thức | Ý nghĩa |
| --- | --- |
| **Array.getLength(array)** | Độ dài mảng tại **tầng hiện tại** |
| **Array.get(array, index)** | Đọc phần tử; primitive được boxing nếu cần trả Object |
| **Array.set(array, index, value)** | Ghi phần tử tương thích kiểu, kể cả mảng con |
| **Array.getInt(array, index)** | Đọc giá trị int từ mảng primitive tương thích |
| **Array.setInt(array, index, intValue)** | Ghi int vào mảng primitive tương thích |
| **Class.isArray()** | Runtime class là mảng? |
| **Class.getComponentType()** | Bóc đúng một cấp component type |

Khi đi qua mảng nhiều chiều bằng Reflection, mỗi lần Array.get chỉ đi xuống **một tầng**:

~~~java
Object cube = Array.newInstance(String.class, 2, 3, 4);
Object plane = Array.get(cube, 1);  // String[][]
Object row = Array.get(plane, 2);   // String[]
Array.set(row, 3, "ok");
System.out.println(Array.get(row, 3)); // ok
~~~

Đây là fragment chạy trong method sau khi import Array. Không thể gán String trực tiếp vào Array.set(cube, 0, "x"), vì phần tử ở tầng ngoài của String[][][] phải có kiểu String[][].

Lưu ý **int[] không thể cast thành Object[]** dù mảng là một Object trong Java. Tuy nhiên **int[][] có thể xem là Object[] ở tầng ngoài**, vì các phần tử của nó là các đối tượng int[]. Nếu cần code áp dụng cho mọi primitive array, giữ biến kiểu Object và dùng API Array.

## 8. Giới hạn dimensions và ngoại lệ

Theo Javadoc Java SE 17:

| Điều kiện | Kết quả |
| --- | --- |
| dimensions có ít nhất một phần tử, mọi độ dài >= 0 | Hợp lệ nếu đủ tài nguyên |
| Có một độ dài bằng 0 | Hợp lệ: mảng độ dài 0 ở tầng tương ứng |
| Có một độ dài âm | **NegativeArraySizeException** |
| componentType là null | **NullPointerException** |
| dimensions là null | **NullPointerException** |
| dimensions là mảng rỗng (0 phần tử) | **IllegalArgumentException** |
| componentType là void.class | **IllegalArgumentException** |
| Số chiều cuối vượt 255 | **IllegalArgumentException** |
| Yêu cầu cấp phát quá nhiều bộ nhớ | Có thể **OutOfMemoryError** |

Số chiều cuối **không chỉ phụ thuộc vào dimensions.length**. Nếu componentType đã là String[][].class, phải cộng thêm 2 chiều. Ví dụ Array.newInstance(int[][].class, new int[254]) yêu cầu 256 chiều nên bị từ chối.

**Danh sách kích thước rỗng khác kích thước bằng 0**:

~~~java
Array.newInstance(int.class, new int[0]); // IllegalArgumentException
Array.newInstance(int.class, 0);          // int[] dài 0, hợp lệ
Array.newInstance(int.class, 2, 0);       // int[][] có 2 hàng, mỗi hàng dài 0
~~~

Chiều 0 không có phần tử để duyệt xuống sâu hơn. Vì thế Array.getLength của mảng con ở tầng trước vẫn có thể là 0, còn truy cập chỉ số [0] của mảng con đó sẽ ném ArrayIndexOutOfBoundsException.

Các thao tác sau tạo cũng có ngoại lệ riêng:

- Array.getLength(null) ném **NullPointerException**.
- Array.getLength trên object không phải mảng ném **IllegalArgumentException**.
- Array.get/Array.set với index âm hay vượt độ dài ném **ArrayIndexOutOfBoundsException**.
- Array.set với giá trị không tương thích kiểu phần tử có thể ném **IllegalArgumentException**.
- Cast một Object sang kiểu mảng có rank/component type không phù hợp ném **ClassCastException**.
- Với mảng outer-only, đọc chiều sâu từ phần tử null gây **NullPointerException**.

Một công cụ xây mảng từ cấu hình không tin cậy nên kiểm tra số chiều, các độ dài, giới hạn cấp phát và kiểu phần tử để tránh cấp phát sai hoặc quá lớn.

## 9. Công thức kiểm tra shape và rank

Giả sử:

~~~java
Object created = Array.newInstance(componentType, dimensions);
~~~

Các quy tắc:

1. **rank(created)** = **rank(componentType) + dimensions.length**; class không phải mảng có rank 0.
2. Các tầng mới tạo có độ dài lần lượt **dimensions[0], dimensions[1], ...**.
3. Nếu componentType vốn là mảng, những tầng nằm sẵn trong componentType **chưa được cấp phát** bởi lần gọi trên.
4. Runtime type cho biết **có bao nhiêu cấp dấu []**, nhưng không tự bảo đảm mỗi nhánh hiện có đủ tất cả mảng con hay độ dài như nhau sau khi chương trình thay đổi.
5. Muốn lấy kiểu lá, gọi getComponentType lặp lại đến khi Class.isArray() trả false.

| Gọi | Rank | Trạng thái phần tử ở mức sâu nhất đã cấp phát |
| --- | --- | --- |
| newInstance(int.class, 2, 3) | 2 | int mặc định 0 |
| newInstance(int[].class, 2) | 2 | Hai int[] null |
| newInstance(int[].class, 2, 3) | 3 | Sáu int[] null |
| newInstance(String.class, 2, 3) | 2 | String mặc định null |
| newInstance(String.class, 0, 3) | 2 | Không có hàng để đọc |

Không nên ước lượng dung lượng bằng cách nhân tất cả dimensions khi componentType vốn là array class: lúc đó phần các tầng chưa cấp phát không có slot phần tử lá tương ứng.

## 10. Sai lầm thường gặp

1. **Đọc {2,3} là hai hàng có độ dài 2 và 3:** đây là 2 chiều kích thước 2 × 3; mảng răng cưa cần cấp phát từng hàng.
2. **Bỏ qua rank có sẵn trong componentType:** String[].class cộng {2,3} tạo String[][][], không phải String[][].
3. **Cho rằng tất cả các chiều trong runtime type đều được cấp phát:** với array-typed component, các chiều còn lại có phần tử mảng con null.
4. **Nhầm null với mảng độ dài 0:** null là chưa có đối tượng mảng; chiều 0 là một mảng hợp lệ có length == 0.
5. **Gọi Array.getLength một lần để lấy mọi chiều:** phương thức chỉ trả length của object mảng cụ thể.
6. **Dùng Object[] cho int[]:** kiểu mảng primitive một chiều không phải Object[].
7. **Giả định Array.newInstance tự cấp phát constructor của mọi phần tử tham chiếu:** String hay object references ban đầu là null, không tự tạo instance.
8. **Truyền dimensions âm/rỗng:** bị từ chối; kiểm tra trước khi cấp phát.
9. **Quên giới hạn 255 chiều:** tính cả rank sẵn của componentType.
10. **Tạo mảng khổng lồ từ cấu hình mà không giới hạn dung lượng:** ngay cả kích thước hợp lệ vẫn có thể gây OutOfMemoryError.

## 11. Tự kiểm tra

**Câu 1.** Array.newInstance(double.class, 4, 2) có kiểu gì và bao nhiêu phần tử cuối?

**Đáp án:** double[][], 4 hàng × 2 phần tử, tổng 8 số double mặc định 0.0.

**Câu 2.** Array.newInstance(double[].class, 4) có kiểu giống câu 1 không? Các hàng đã được cấp phát chưa?

**Đáp án:** Cùng kiểu double[][], nhưng chỉ có mảng ngoài dài 4; cả bốn double[] còn null.

**Câu 3.** Array.newInstance(String[][].class, 2, 3) có runtime type gì?

**Đáp án:** String[][][][] với tổng rank 4; hai tầng mới dài 2 và 3, các tham chiếu String[][] ở tầng cuối được tạo còn null.

**Câu 4.** {3,0,5} có hợp lệ không? Có thể truy cập [0][0] không?

**Đáp án:** Hợp lệ. Mảng ngoài dài 3, mảng con thứ hai dài 0. Truy cập [0][0] gây ArrayIndexOutOfBoundsException.

**Câu 5.** Muốn ba hàng dài 2,5,1 thì có nên gọi newInstance(int.class, 2,5,1)?

**Đáp án:** Không. Đó là mảng ba chiều 2 × 5 × 1. Hãy tạo int[3][] hoặc Array.newInstance(int[].class, 3) rồi tạo các hàng dài 2,5,1.

**Câu 6.** Vì sao newInstance(int.class, new int[0]) lỗi nhưng newInstance(int.class, 0) thành công?

**Đáp án:** Mảng kích thước thứ nhất rỗng, nghĩa là **không cung cấp chiều nào**. Lời gọi thứ hai chỉ tạo **một chiều có độ dài 0**.

**Ghi nhớ:** danh sách dimensions cho biết **độ dài các chiều mới, theo thứ tự ngoài vào trong**. Nếu componentType là array class thì số chiều kết quả tăng thêm nhưng các chiều sẵn có bên trong componentType vẫn chưa được cấp phát. Java dùng mảng của mảng nên bạn có thể tạo hình chữ nhật hoặc mảng răng cưa có độ dài từng hàng khác nhau.

### Tài liệu tham khảo

- Java SE 17, Array.newInstance/get/set/getLength: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html
- Java SE 17, Class.isArray và getComponentType: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java Language Specification 17, Chapter 10 — Arrays: https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html
