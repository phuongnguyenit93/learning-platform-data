# Dùng Arrays.hashCode() hoặc deepHashCode() theo cách so sánh mảng

## 1. Vì sao mảng cần cách tính hashCode riêng?

Trong Java, mảng là đối tượng, nhưng **mảng không override Object.equals(Object) hay Object.hashCode() để so nội dung**. Vì vậy hai mảng được tạo riêng dù chứa các phần tử giống hệt nhau vẫn là hai đối tượng khác nhau theo equals mặc định. Nếu ta thiết kế một lớp giá trị chứa mảng và muốn hai instance bằng nhau **dựa trên nội dung mảng**, phải tự chọn **phép so sánh nội dung** và **hàm hash tương ứng**.

Hợp đồng quan trọng nhất:

> Nếu a.equals(b) trả về true thì a.hashCode() bắt buộc bằng b.hashCode().

Điều ngược lại **không bắt buộc**: hai giá trị khác nhau có thể trùng hash do va chạm băm. Không được dùng **hashCode() bằng nhau** làm bằng chứng để kết luận hai mảng bằng nhau.

Đối với mảng, cần thống nhất **độ sâu của phép so sánh**:

- Mảng một chiều như **int[]**, **byte[]**, **char[]**: dùng **Arrays.equals(...)** để so từng giá trị và **Arrays.hashCode(...)** với cùng loại mảng để tính hash theo nội dung.
- Mảng đối tượng một chiều như **String[]**: **Arrays.equals(Object[], Object[])** dùng **Objects.equals(...)** cho từng phần tử; **Arrays.hashCode(Object[])** gọi hashCode của các phần tử tương ứng.
- Mảng lồng nhau như **int[][]**, **String[][]** hoặc **Object[]** chứa các mảng: muốn so **sâu theo nội dung của các mảng con**, dùng **Arrays.deepEquals(Object[], Object[])** và **Arrays.deepHashCode(Object[])**.

Không nên chọn hàm hash theo số dấu ngoặc vuông một cách máy móc: **String[]** là mảng đối tượng một chiều và so sánh nông thường đã đủ vì phần tử String tự so nội dung; còn **Object[]** một chiều nhưng chứa **int[]** vẫn cần so sánh sâu nếu quy tắc giá trị đòi so nội dung của các mảng con.

## 2. Bảng đối chiếu phép so sánh và phép băm

| Kiểu dữ liệu và ngữ nghĩa mong muốn | So sánh giá trị | Tính hash tương ứng |
| --- | --- | --- |
| **int[]** / **long[]** / **byte[]** / **char[]** / các mảng primitive một chiều | **Arrays.equals(a, b)** | **Arrays.hashCode(a)** |
| **String[]** hoặc **Integer[]**, so từng phần tử bằng equals | **Arrays.equals(a, b)** | **Arrays.hashCode(a)** |
| **Object[]** có phần tử là các đối tượng thường, so trực tiếp mỗi phần tử | **Arrays.equals(a, b)** | **Arrays.hashCode(a)** |
| **int[][]**, **long[][]**, **String[][]**, so sâu các hàng | **Arrays.deepEquals(a, b)** | **Arrays.deepHashCode(a)** |
| **Object[]** chứa mảng ở một hay nhiều mức và muốn so sâu | **Arrays.deepEquals(a, b)** | **Arrays.deepHashCode(a)** |
| **Object[]** có mảng con nhưng nghiệp vụ **chỉ so tham chiếu mảng con** | **Arrays.equals(a, b)** | **Arrays.hashCode(a)** |

**“Nông” (shallow)** trong bảng nghĩa là hàm xét lần lượt **các phần tử của mảng ngoài**: nếu một phần tử lại là mảng, equals/hashCode mặc định của chính mảng con vẫn theo đối tượng, tức thường là theo tham chiếu. **“Sâu” (deep)** nghĩa là khi phần tử cũng là mảng, Java đi sâu vào các mảng con và xử lý phần tử lồng bên trong.

Lưu ý về chữ **deep**: đây là so sánh sâu **các lớp mảng**, không tự động duyệt mọi trường của mọi object tùy ý. Khi gặp phần tử là đối tượng thông thường, **Arrays.deepEquals** vẫn dựa trên phương thức **equals** của đối tượng ấy, và **Arrays.deepHashCode** dựa trên **hashCode** của nó. Nếu lớp phần tử tự cài sai hợp đồng equals/hashCode, phép deep không thể tự sửa lỗi đó.

## 3. Ví dụ 1: mảng primitive một chiều dùng Arrays.equals và Arrays.hashCode

Tạo tệp **PrimitiveArrayHashDemo.java**:

~~~java
import java.util.Arrays;

public class PrimitiveArrayHashDemo {
    public static void main(String[] args) {
        int[] first = {1, 2, 3};
        int[] second = {1, 2, 3};
        int[] third = {1, 2, 4};

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(Arrays.equals(first, second));
        System.out.println(Arrays.hashCode(first));
        System.out.println(Arrays.hashCode(second));
        System.out.println(Arrays.equals(first, third));
        System.out.println(Arrays.hashCode(first) == Arrays.hashCode(second));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac PrimitiveArrayHashDemo.java
java PrimitiveArrayHashDemo
~~~

Kết quả:

~~~text
false
false
true
30817
30817
false
true
~~~

**Giải thích:** **first** và **second** là hai instance mảng khác nhau, nên cả **==** lẫn **first.equals(second)** đều false. Nhưng **Arrays.equals(first, second)** duyệt từng phần tử int và trả true. **Arrays.hashCode(int[])** cũng dựa trên cùng dãy giá trị nên cho kết quả giống nhau.

Đối với int[], Java định nghĩa phép tích lũy hash dạng:

~~~text
result = 1
với từng phần tử v:
    result = 31 * result + v
~~~

Phép nhân/cộng thực hiện theo số nguyên **int** của Java, nên tràn số là hợp lệ và có thể xảy ra. Với **{1, 2, 3}**:

~~~text
31 * 1   + 1 = 32
31 * 32  + 2 = 994
31 * 994 + 3 = 30817
~~~

Công thức minh họa cho **int[]**; các overload primitive khác dùng cách đưa từng phần tử về số băm phù hợp với kiểu phần tử. **Không cần tự viết vòng lặp tính hash**, vì Arrays.hashCode đã cung cấp cơ chế nhất quán với Arrays.equals.

### Mảng rỗng, null và thứ tự

- Hai **int[] rỗng** bằng nhau theo **Arrays.equals** và có cùng Arrays.hashCode.
- **Arrays.equals((int[]) null, (int[]) null)** trả true; một bên null, một bên không null thì false.
- **Arrays.hashCode((int[]) null)** trả 0.
- Thứ tự phần tử là một phần của giá trị: **{1, 2}** khác **{2, 1}** theo Arrays.equals. Hai mảng khác thứ tự có thể vô tình cùng hash, nhưng vẫn không bằng nhau.
- Nếu nghiệp vụ coi mảng là **tập hợp không có thứ tự**, Arrays.equals/hashCode theo thứ tự **không phù hợp** với định nghĩa đó. Cần một mô hình giá trị hoặc khóa chuẩn hóa khác, kèm equals/hashCode nhất quán.

## 4. Ví dụ 2: vì sao mảng lồng nhau cần deepEquals và deepHashCode?

Với **int[][]**, mỗi phần tử của mảng ngoài là một **int[]**. Nếu dùng **Arrays.equals(int[][], int[][])**, Java chọn overload **Object[]**; ở cấp mảng ngoài, các phần tử là mảng con. Hai hàng **new int[]{1, 2}** được tạo riêng không bằng nhau theo Object.equals mặc định.

Tạo file **NestedArrayHashDemo.java**:

~~~java
import java.util.Arrays;

public class NestedArrayHashDemo {
    public static void main(String[] args) {
        int[][] first = {
            {1, 2},
            {3, 4}
        };
        int[][] second = {
            {1, 2},
            {3, 4}
        };
        int[][] changed = {
            {1, 2},
            {3, 9}
        };

        System.out.println("shallow equals: " +
            Arrays.equals(first, second));
        System.out.println("deep equals: " +
            Arrays.deepEquals(first, second));
        System.out.println("deep hash equal: " +
            (Arrays.deepHashCode(first) == Arrays.deepHashCode(second)));
        System.out.println("changed deep equals: " +
            Arrays.deepEquals(first, changed));
        System.out.println("matrix: " +
            Arrays.deepToString(first));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac NestedArrayHashDemo.java
java NestedArrayHashDemo
~~~

Kết quả:

~~~text
shallow equals: false
deep equals: true
deep hash equal: true
changed deep equals: false
matrix: [[1, 2], [3, 4]]
~~~

**Cơ chế hoạt động:**

1. **Arrays.equals(first, second)** xét các phần tử của mảng ngoài. Các phần tử này là mảng con khác tham chiếu, nên kết quả false.
2. **Arrays.deepEquals(first, second)** nhận **Object[]** ở cấp ngoài (int[][] là Object[]) và nhận biết mỗi phần tử con là **int[]**, rồi gọi cách so primitive thích hợp.
3. **Arrays.deepHashCode(first)** đi sâu qua các mảng con để băm từng giá trị int. Nếu hai cấu trúc bằng nhau theo deepEquals và các object phần tử tuân thủ hợp đồng, chúng có deep hash bằng nhau.
4. **Arrays.deepToString** rất tiện để in cấu trúc lồng nhau phục vụ kiểm tra dữ liệu. Đây là hàm biểu diễn chuỗi, **không thay thế** equals/hashCode.

Không có overload **Arrays.deepHashCode(int[])**: phương thức deep nhận **Object[]**, trong khi **int[] không phải Object[]**. Đối với một **int[]** độc lập, dùng **Arrays.hashCode(int[])**. Đối với **int[][]**, có thể dùng **Arrays.deepHashCode(int[][])** vì **int[][] là mảng chứa các phần tử int[]**, nên tương thích với tham số Object[].

## 5. Ví dụ 3: Object[] một chiều nhưng chứa các mảng khác nhau

Chiều khai báo của mảng ngoài không phải toàn bộ câu chuyện. Một **Object[]** có thể chứa **int[]**, **String[]**, mảng nhiều chiều và đối tượng thường cùng lúc.

Tạo file **MixedNestedArrayDemo.java**:

~~~java
import java.util.Arrays;

public class MixedNestedArrayDemo {
    public static void main(String[] args) {
        Object[] left = {
            "header",
            new int[]{5, 8},
            new String[]{"A", "B"}
        };

        Object[] right = {
            "header",
            new int[]{5, 8},
            new String[]{"A", "B"}
        };

        System.out.println("shallow: " +
            Arrays.equals(left, right));
        System.out.println("deep: " +
            Arrays.deepEquals(left, right));
        System.out.println("deep hash equal: " +
            (Arrays.deepHashCode(left) == Arrays.deepHashCode(right)));
        System.out.println("display: " +
            Arrays.deepToString(left));
    }
}
~~~

Kết quả khi chạy **javac MixedNestedArrayDemo.java** rồi **java MixedNestedArrayDemo**:

~~~text
shallow: false
deep: true
deep hash equal: true
display: [header, [5, 8], [A, B]]
~~~

Vì có các phần tử **int[]** và **String[]** được tạo độc lập, so sánh nông trả false. So sánh sâu biết cách xử lý cả mảng primitive và mảng tham chiếu lồng nhau.

**Arrays.deepEquals/deepHashCode vẫn quan tâm kiểu và cấu trúc mảng.** Chẳng hạn **new int[]{1}** không tự động được coi là bằng **new Integer[]{1}**; việc “cùng con số” không đủ để hai mảng khác kiểu có cùng ngữ nghĩa giá trị. Nếu nghiệp vụ muốn coi chúng tương đương, cần chuyển chúng về một biểu diễn giá trị chung **trước** khi so sánh/băm.

## 6. Cài equals và hashCode cho lớp có trường mảng một chiều

Đây là trường hợp thường gặp nhất: một đối tượng chứa **int[] samples**, và nội dung dãy số cấu thành giá trị đối tượng. Nếu chỉ dùng **Objects.equals(samples, other.samples)**, Java so tham chiếu mảng; nếu chỉ dùng **Objects.hash(samples)**, hash có thể phụ thuộc vào danh tính mảng chứ không phải các số bên trong.

Tạo tệp **IntVectorDemo.java** với một kiểu khóa bất biến về mặt quan sát từ bên ngoài:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class IntVectorDemo {
    static final class IntVector {
        private final int[] values;

        IntVector(int[] values) {
            this.values = Arrays.copyOf(
                Objects.requireNonNull(values, "values"),
                values.length
            );
        }

        public int[] values() {
            return values.clone();
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof IntVector other)) {
                return false;
            }
            return Arrays.equals(values, other.values);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }

        @Override
        public String toString() {
            return Arrays.toString(values);
        }
    }

    public static void main(String[] args) {
        int[] input = {2, 4};
        IntVector one = new IntVector(input);
        IntVector two = new IntVector(new int[]{2, 4});

        System.out.println("equal: " + one.equals(two));
        System.out.println("hash equal: " +
            (one.hashCode() == two.hashCode()));

        Set<IntVector> unique = new HashSet<>();
        System.out.println("add one: " + unique.add(one));
        System.out.println("add two: " + unique.add(two));
        System.out.println("set size: " + unique.size());

        input[0] = 99;
        System.out.println("after editing input: " + one);
        int[] exposedCopy = one.values();
        exposedCopy[1] = 77;
        System.out.println("after editing getter copy: " + one);
    }
}
~~~

Chạy:

~~~bash
javac IntVectorDemo.java
java IntVectorDemo
~~~

Kết quả:

~~~text
equal: true
hash equal: true
add one: true
add two: false
set size: 1
after editing input: [2, 4]
after editing getter copy: [2, 4]
~~~

**Tại sao cần sao chép mảng?** Nếu giữ nguyên tham chiếu đầu vào hoặc trả thẳng mảng nội bộ qua getter, mã ngoài có thể sửa phần tử sau khi object được đặt làm khóa HashMap/HashSet. Khi ấy **hashCode thay đổi theo nội dung** và việc tìm kiếm có thể không còn đúng. Lớp trên copy trong constructor và copy khi trả dữ liệu, nên các thành phần tham gia hashCode không thể bị thay đổi bởi mã bên ngoài.

**final field không đồng nghĩa với mảng bất biến.** Khai báo **private final int[] values** chỉ ngăn gán lại tham chiếu values bên trong lớp, không ngăn **values[0] = ...**. Nếu chính class vẫn cung cấp phương thức sửa mảng nội bộ, nó vẫn là mutable key; muốn khóa ổn định thì phải đảm bảo không có đường thay đổi nội dung.

**Nếu có nhiều trường giá trị:** tính cả những trường được equals so sánh. Ví dụ một lớp có **String id** và **int[] samples** có thể cài:

~~~java
// Đoạn trích trong equals(Object), sau khi đã xác nhận đúng kiểu:
return Objects.equals(id, other.id)
    && Arrays.equals(samples, other.samples);

// Đoạn trích trong hashCode():
return 31 * Objects.hashCode(id) + Arrays.hashCode(samples);
~~~

Đây là **đoạn mã minh họa trong một lớp**, không phải chương trình độc lập. Cách kết hợp bằng hệ số 31 là một lựa chọn thông dụng, không phải duy nhất. Điều bắt buộc là **mọi cặp bằng nhau theo equals đều có cùng hashCode**, chứ không phải có một số công thức băm cụ thể.

## 7. Cài equals và hashCode cho lớp chứa mảng lồng nhau

Với **int[][] matrix** được coi là một giá trị cấu trúc, cần dùng **Arrays.deepEquals** và **Arrays.deepHashCode**. Muốn object ổn định khi làm khóa, cũng cần **sao chép từng hàng**: chỉ clone mảng ngoài chưa đủ vì mảng con vẫn được chia sẻ.

Tạo file **MatrixKeyDemo.java**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MatrixKeyDemo {
    static final class MatrixKey {
        private final int[][] matrix;

        MatrixKey(int[][] source) {
            Objects.requireNonNull(source, "source");
            this.matrix = copyMatrix(source);
        }

        private static int[][] copyMatrix(int[][] source) {
            int[][] copy = new int[source.length][];
            for (int i = 0; i < source.length; i++) {
                copy[i] = source[i] == null
                    ? null
                    : source[i].clone();
            }
            return copy;
        }

        public int[][] getMatrix() {
            return copyMatrix(matrix);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof MatrixKey other)) {
                return false;
            }
            return Arrays.deepEquals(matrix, other.matrix);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(matrix);
        }
    }

    public static void main(String[] args) {
        int[][] input = {
            {1, 2},
            null,
            {3}
        };

        MatrixKey one = new MatrixKey(input);
        MatrixKey two = new MatrixKey(new int[][]{
            {1, 2},
            null,
            {3}
        });

        System.out.println("equal: " + one.equals(two));
        System.out.println("hash equal: " +
            (one.hashCode() == two.hashCode()));

        Set<MatrixKey> keys = new HashSet<>();
        keys.add(one);
        keys.add(two);
        System.out.println("set size: " + keys.size());

        input[0][0] = 999;
        int[][] copy = one.getMatrix();
        copy[2][0] = 888;

        System.out.println("stable: " + one.equals(two));
    }
}
~~~

Lệnh chạy:

~~~bash
javac MatrixKeyDemo.java
java MatrixKeyDemo
~~~

Kết quả:

~~~text
equal: true
hash equal: true
set size: 1
stable: true
~~~

Trong ví dụ, cả mảng ngoài lẫn từng **int[]** bên trong đều được copy. Hàm copy chấp nhận các hàng null để phù hợp với dữ liệu mà **deepEquals/deepHashCode** hỗ trợ. Sau khi khởi tạo, sửa mảng input hoặc bản sao từ getter không ảnh hưởng tới giá trị của MatrixKey.

Nếu ma trận chứa các đối tượng **mutable** ở lá, việc clone mảng ngoài và mảng con vẫn chỉ sao chép **tham chiếu đến object lá**. Khi yêu cầu bất biến sâu, phải có chính sách copy hoặc kiểu immutable phù hợp cho các object lá; **Arrays.deepHashCode không làm cho nội dung thành bất biến**.

## 8. Cạm bẫy với Objects.hash, Objects.hashCode và record

### 8.1. Objects.hash không phải hàm thay thế cho Arrays.hashCode của mọi mảng

**Objects.hash(Object... values)** là phương thức varargs, về bản chất băm một **Object[] tham số**. Với **int[]**, nó coi mảng primitive là **một object phần tử**, nên hash có thể dựa trên **hashCode danh tính của mảng**. Vì vậy:

~~~java
int[] first = {1, 2};
int[] second = {1, 2};

// Đoạn trích minh họa:
boolean contentEqual = java.util.Arrays.equals(first, second);  // true
boolean correctHashEqual =
    java.util.Arrays.hashCode(first) ==
    java.util.Arrays.hashCode(second);                           // true
~~~

Đây là đoạn trích, không phải file độc lập. **Không nên thay Arrays.hashCode(first) bằng Objects.hash(first)** rồi kỳ vọng nhận được cùng quy tắc băm nội dung primitive.

Với **Object[]**, lời gọi varargs như **Objects.hash(objectArray)** có thể dùng chính các phần tử của Object[] làm danh sách tham số, nên hành vi còn tùy kiểu mảng và cách gọi. Dùng overload **Arrays.hashCode(Object[])** hoặc **Arrays.deepHashCode(Object[])** tường minh để tránh hiểu nhầm và giữ đúng cặp với phép equals.

**Objects.hashCode(array)** (số ít, nhận một Object) chỉ gọi **array.hashCode()** khi khác null, nên đối với mảng cũng **không tính băm theo nội dung**.

### 8.2. Record có trường mảng không tự so nội dung mảng

Record sinh **equals/hashCode** từ các component, nhưng một component kiểu mảng vẫn dùng ngữ nghĩa **equals/hashCode của mảng** thay vì tự chuyển thành **Arrays.equals** và **Arrays.hashCode**.

Tạo file **RecordArrayDemo.java**:

~~~java
import java.util.Arrays;

public class RecordArrayDemo {
    record RawReading(int[] values) {}

    record ValueReading(int[] values) {
        ValueReading {
            values = values.clone();
        }

        @Override
        public int[] values() {
            return values.clone();
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof ValueReading other
                && Arrays.equals(values, other.values);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        RawReading raw1 = new RawReading(new int[]{1, 2});
        RawReading raw2 = new RawReading(new int[]{1, 2});
        ValueReading good1 = new ValueReading(new int[]{1, 2});
        ValueReading good2 = new ValueReading(new int[]{1, 2});

        System.out.println("generated equals: " + raw1.equals(raw2));
        System.out.println("custom equals: " + good1.equals(good2));
        System.out.println("custom hash equal: " +
            (good1.hashCode() == good2.hashCode()));
    }
}
~~~

Chạy:

~~~bash
javac RecordArrayDemo.java
java RecordArrayDemo
~~~

Kết quả:

~~~text
generated equals: false
custom equals: true
custom hash equal: true
~~~

Trong **ValueReading**, compact constructor sao chép component mảng trước khi lưu, accessor override trả bản sao, equals/hashCode tự dùng cùng nội dung int[]. Cần xem xét tương tự với **record có mảng lồng nhau**: clone mảng ngoài chưa đủ; khi dùng deepEquals/deepHashCode thì cần chính sách bất biến sâu tương ứng.

### 8.3. Các loại số thực và phần tử null

- **Arrays.equals(float[], float[])** và **Arrays.equals(double[], double[])** sử dụng quy tắc tương ứng với **Float.compare** và **Double.compare** cho phần tử. Điều này xử lý NaN và phân biệt **+0.0** với **-0.0** theo quy tắc của các wrapper, thay vì dùng trực tiếp toán tử **==** của số thực.
- **Arrays.hashCode(float[])** và **Arrays.hashCode(double[])** được định nghĩa tương thích với chính phép so sánh mảng đó. Không tự thay equals bằng vòng lặp dùng **==** trong khi giữ Arrays.hashCode mà không hiểu sự khác biệt.
- **Arrays.equals(Object[], Object[])** có thể xử lý phần tử null: hai null ở cùng vị trí là bằng nhau; một null và một giá trị khác null thì không. **Arrays.hashCode(Object[])** và deepHashCode tính hash tương ứng cho vị trí null.
- Đối với mảng top-level null, **Arrays.deepEquals((Object[]) null, (Object[]) null)** trả true và **Arrays.deepHashCode((Object[]) null)** trả 0. Khi biến khai báo không rõ kiểu, nên chỉ định đúng overload hoặc ép kiểu có chủ đích.

## 9. Những giới hạn cần biết của deepEquals và deepHashCode

**Không dùng cho mảng tham chiếu vòng lặp (cyclic arrays).** Một Object[] có thể tự chứa chính nó hoặc tạo chu kỳ qua nhiều mảng. Các API deep không thiết kế để xử lý cấu trúc mảng đệ quy như đồ thị chu kỳ theo cách tổng quát; deepHashCode có thể đệ quy không dừng và gây **StackOverflowError**. Với đồ thị có chu kỳ, cần mô hình so sánh/băm riêng có cơ chế theo dõi các node đã thăm, cùng định nghĩa rõ thế nào là hai đồ thị bằng nhau.

**Độ sâu có chi phí.** Arrays.hashCode trên mảng một chiều cần duyệt các phần tử ở cấp tương ứng; deepHashCode phải đi qua các mảng lồng nhau. Việc gọi hashCode nhiều lần trên khóa là một chi phí có thật. Chỉ cân nhắc cache hash sau khi thiết kế object thực sự bất biến và đã có lý do đo đạc; cache trên dữ liệu mutable có thể khiến equals/hashCode không nhất quán.

**Các phần tử object phải có hợp đồng đúng.** Nếu Object[] chứa một lớp custom có equals theo trường A nhưng hashCode theo trường B, cả Arrays.hashCode và deepHashCode đều không thể cứu hợp đồng. Cặp phương thức mảng chỉ kế thừa tính đúng đắn từ các phần tử.

**Hai mảng khác nhau có thể cùng hash.** Ví dụ, băm dựa trên 31 là hàm nén từ rất nhiều dãy giá trị xuống một int 32-bit. Không được dùng hash để thay cho equals, kiểm tra trùng nội dung, hay làm dấu vân tay bảo mật.

**Chiều và hình dạng là một phần của cấu trúc.** Một ma trận gồm một hàng hai phần tử và một ma trận gồm hai hàng một phần tử không có cấu trúc deepEquals giống nhau, ngay cả khi liệt kê phẳng các số có thể trông tương tự. Nếu miền nghiệp vụ muốn bỏ qua hình dạng, phải tự chuyển dữ liệu về biểu diễn chuẩn trước.

**Arrays.compare, Arrays.mismatch và Comparator** giải quyết các bài toán khác: thứ tự từ điển, vị trí khác nhau đầu tiên hay so theo tiêu chí tùy chọn. Không mặc định thay đổi equals/hashCode của khóa chỉ vì dùng comparator trong TreeMap/TreeSet. Các cấu trúc sắp xếp xác định sự trùng khóa bằng **compare == 0**, có thể khác hợp đồng equals nếu comparator không nhất quán.

## 10. Kiểm thử hợp đồng và lựa chọn trong bài toán thật

Với một lớp có thành phần mảng, hãy xây ít nhất ba đối tượng **a, b, c**:

- **a** và **b** có dữ liệu nội dung bằng nhau nhưng mảng bên trong được cấp phát độc lập.
- **c** khác **a** ở một phần tử, một hàng lồng nhau hoặc ở một trường giá trị khác.
- Thêm trường hợp mảng rỗng, mảng con null (nếu được phép), phần tử object null, thứ tự khác và object có mảng bị thay đổi sau khởi tạo.

Kiểm tra những điều sau:

1. **a.equals(b)** true khi và chỉ khi nội dung theo tiêu chí nghiệp vụ thực sự bằng nhau; nếu dùng deep, thay mảng con bằng mảng mới cùng dữ liệu không làm đổi kết quả.
2. Khi **a.equals(b)** true, **a.hashCode() == b.hashCode()** luôn true.
3. **a.equals(c)** false nếu tiêu chí giá trị phân biệt a và c. Không kiểm tra rằng hash bắt buộc khác: va chạm hợp lệ.
4. Tính phản xạ, đối xứng, bắc cầu, tính nhất quán và quy tắc với null của **equals** vẫn phải thỏa.
5. Cho các instance bằng nhau vào **HashSet** thì tập chỉ giữ một khóa logic; HashMap tra cứu bằng instance khác nhưng bằng giá trị phải thành công.
6. Thử sửa **mảng đầu vào** và **mảng từ getter** sau khi tạo khóa; nếu lớp được thiết kế bất biến, equals/hashCode của khóa không đổi.
7. Với mảng lồng nhau, chắc chắn mọi tầng mảng phải tham gia so sánh theo đúng ngữ nghĩa đã chọn; không chỉ test một hàng hoặc những trường hợp dùng lại cùng tham chiếu mảng.

### Quy trình quyết định nhanh

| Câu hỏi | Cách chọn |
| --- | --- |
| Có phải mảng primitive **một chiều** và so từng phần tử? | **Arrays.equals** + **Arrays.hashCode** |
| Có phải mảng **Object[]** không chứa mảng con cần duyệt sâu? | **Arrays.equals** + **Arrays.hashCode** |
| Có phải mảng nhiều chiều hoặc Object[] chứa mảng con **và muốn so nội dung lồng nhau**? | **Arrays.deepEquals** + **Arrays.deepHashCode** |
| Trường mảng thuộc **record** hoặc lớp custom? | Override **cả equals lẫn hashCode** nếu muốn so theo nội dung mảng |
| Object được dùng làm khóa HashMap/HashSet? | Đảm bảo các mảng tham gia so sánh **ổn định/bất biến**, sao chép phòng vệ khi cần |
| Dữ liệu chứa cấu trúc chu kỳ hoặc so sánh theo tiêu chí đặc biệt? | Thiết kế **kiểu giá trị và thuật toán riêng**, không dựa trực tiếp vào deep API |

**Ghi nhớ:** **equals và hashCode phải nhìn cùng một “hình dạng giá trị”**. Nếu equals so nội dung một chiều thì hashCode cũng băm nội dung một chiều; nếu equals đi sâu vào các mảng con thì hashCode cũng phải đi sâu bằng quy tắc tương ứng. **Arrays.hashCode** đi cùng **Arrays.equals**; **Arrays.deepHashCode** đi cùng **Arrays.deepEquals**. Trong một lớp chứa mảng, việc chọn đúng hàm mới là bước đầu: giữ dữ liệu khóa ổn định mới giúp hợp đồng hoạt động tin cậy trong các cấu trúc băm.
