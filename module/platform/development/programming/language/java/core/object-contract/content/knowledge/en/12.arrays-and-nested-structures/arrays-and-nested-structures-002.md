# `Arrays.equals()` và `Arrays.hashCode()` cho mảng một chiều trong Java

## 1. Vấn đề: hai mảng có cùng phần tử chưa chắc là cùng đối tượng

Trong Java, **mảng là đối tượng**. Hai biến mảng có thể cùng tham chiếu đến **một mảng**, hoặc tham chiếu đến **hai mảng riêng biệt** có các phần tử giống hệt nhau.

~~~java
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};
int[] alias = a;
~~~

- `a == b` trả về `false`: hai biểu thức khởi tạo mảng đã tạo **hai đối tượng mảng** khác nhau.
- `a == alias` trả về `true`: phép gán `alias = a` chỉ sao chép **tham chiếu**, không tạo mảng mới.
- `a.equals(b)` trả về `false`: mảng không ghi đè phương thức `equals(Object)` từ `Object` để so sánh từng phần tử.
- `Arrays.equals(a, b)` trả về `true`: so sánh **nội dung theo vị trí** của hai mảng một chiều.

Tương tự, phương thức `hashCode()` kế thừa từ `Object` trên một đối tượng mảng **không định nghĩa hash theo các phần tử**. Nếu cần so sánh hai mảng như **hai giá trị có nội dung bằng nhau**, dùng cặp API:

~~~java
java.util.Arrays.equals(a, b);
java.util.Arrays.hashCode(a);
~~~

Cặp phương thức này đặc biệt quan trọng khi mảng là một phần trạng thái của một value object hay đối tượng dùng làm khóa `HashMap`/phần tử `HashSet`.

## 2. `Arrays.equals()` kiểm tra bằng nhau theo nội dung như thế nào?

`java.util.Arrays` cung cấp các overload `equals` cho mảng một chiều chứa từng kiểu nguyên thủy (`boolean[]`, `byte[]`, `short[]`, `char[]`, `int[]`, `long[]`, `float[]`, `double[]`) và mảng tham chiếu `Object[]`.

Với hai mảng cùng kiểu thành phần thích hợp:

1. Hai tham chiếu cùng chỉ một mảng thì bằng nhau, kể cả trường hợp **cả hai là `null`**.
2. Một bên là `null`, bên kia không phải `null` thì không bằng nhau.
3. Độ dài khác nhau thì không bằng nhau.
4. Độ dài giống nhau thì kiểm tra **từng cặp phần tử ở cùng chỉ số**, từ đầu đến cuối.
5. Nếu phát hiện phần tử đầu tiên không bằng nhau thì kết quả là `false`; chỉ khi tất cả vị trí tương ứng bằng nhau mới trả về `true`.

Thứ tự phần tử có ý nghĩa: `[1, 2, 3]` không bằng `[3, 2, 1]`. Với cách so sánh nội dung này, hai mảng không cần có cùng địa chỉ hay cùng tham chiếu.

### Ví dụ chạy được: mảng `int[]`

Tạo tệp `PrimitiveArraysDemo.java`:

~~~java
import java.util.Arrays;

public class PrimitiveArraysDemo {
    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        int[] b = {1, 2, 3};
        int[] differentOrder = {3, 2, 1};
        int[] alias = a;

        System.out.println("a == b: " + (a == b));
        System.out.println("a == alias: " + (a == alias));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("Arrays.equals(a,b): " + Arrays.equals(a, b));
        System.out.println("same contents hash: "
                + (Arrays.hashCode(a) == Arrays.hashCode(b)));
        System.out.println("order equal: "
                + Arrays.equals(a, differentOrder));
        System.out.println("hash(a): " + Arrays.hashCode(a));
        System.out.println("null equals null: "
                + Arrays.equals((int[]) null, (int[]) null));
        System.out.println("null equals a: "
                + Arrays.equals((int[]) null, a));
        System.out.println("hash(null): " + Arrays.hashCode((int[]) null));
        System.out.println("hash(empty): " + Arrays.hashCode(new int[0]));

        b[0] = 9;
        System.out.println("after mutation: " + Arrays.equals(a, b));
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac -encoding UTF-8 PrimitiveArraysDemo.java
java PrimitiveArraysDemo
~~~

Stdout:

~~~text
a == b: false
a == alias: true
a.equals(b): false
Arrays.equals(a,b): true
same contents hash: true
order equal: false
hash(a): 30817
null equals null: true
null equals a: false
hash(null): 0
hash(empty): 1
after mutation: false
~~~

`Arrays.hashCode(new int[] {1, 2, 3})` là `30817` theo công thức ở phần tiếp theo. Đây là giá trị của **thuật toán hash theo nội dung**; đừng nhầm với `a.hashCode()`, vốn kế thừa cơ chế hash của đối tượng.

Trong lời gọi `Arrays.equals(null, null)` hoặc `Arrays.hashCode(null)` viết trực tiếp, trình biên dịch có thể không chọn được overload vì có nhiều kiểu mảng. Ép kiểu rõ ràng, chẳng hạn `(int[]) null`, hoặc truyền biến có kiểu khai báo `int[]` giúp chọn đúng overload.

## 3. `Arrays.hashCode()` tạo mã băm theo nội dung

`Arrays.hashCode` cũng có các overload tương ứng với các loại mảng một chiều nguyên thủy và `Object[]`. Đối với một mảng không `null`, hàm duyệt các phần tử **theo thứ tự**, bắt đầu với `result = 1` và lặp công thức:

~~~text
result = 1
for each element:
    result = 31 * result + elementHash
return result
~~~

Ở đây `elementHash` là giá trị hash của từng phần tử theo quy tắc tương ứng với kiểu phần tử:

- `int[]`: chính giá trị `int` của phần tử.
- `long[]`: giá trị như `Long.hashCode(long)`.
- `boolean[]`: giá trị như `Boolean.hashCode(boolean)`.
- `byte[]`, `short[]` và `char[]`: giá trị số của phần tử theo phép chuyển sang `int` thích hợp.
- `float[]` và `double[]`: phép băm tương ứng với `Float.hashCode` hoặc `Double.hashCode`.
- `Object[]`: `0` nếu phần tử là `null`; nếu khác `null` thì gọi `element.hashCode()`.

Với mảng `int[] {1, 2, 3}`:

~~~text
ban đầu:            result = 1
sau phần tử 1:      result = 31 * 1   + 1 = 32
sau phần tử 2:      result = 31 * 32  + 2 = 994
sau phần tử 3:      result = 31 * 994 + 3 = 30817
~~~

Với mảng `null`, `Arrays.hashCode` trả về `0`; với một mảng **rỗng nhưng không `null`**, kết quả là `1`. Phép tính dùng `int` nên có thể tràn số theo ngữ nghĩa số nguyên Java; đây không phải lỗi của thuật toán.

### Hợp đồng giữa `equals` và `hashCode`

Nếu `Arrays.equals(a, b)` trả về `true` với overload thích hợp thì `Arrays.hashCode(a) == Arrays.hashCode(b)` cũng phải đúng. Điều ngược lại **không bảo đảm**: hai mảng có nội dung khác nhau vẫn có thể trùng mã băm vì số kết quả chỉ có 32 bit.

Do đó, **không** dùng điều kiện `Arrays.hashCode(a) == Arrays.hashCode(b)` thay cho so sánh nội dung thực sự. Hash thích hợp để chọn bucket hoặc tăng tốc tra cứu; `equals` mới xác định bằng nhau về giá trị.

## 4. Mảng nguyên thủy và mảng tham chiếu khác nhau ở phép so sánh phần tử

### Mảng kiểu nguyên thủy

Với `int[]`, `byte[]`, `char[]` và các kiểu nguyên thủy khác, `Arrays.equals` áp dụng cách so sánh giá trị phù hợp với kiểu. Ví dụ `char[] {'a', 'b'}` và `char[] {'b', 'a'}` không bằng nhau vì khác thứ tự.

Không có overload `Arrays.equals(int[], long[])` để tự đổi kiểu rồi so. Hai mảng nguyên thủy khác loại phải được chuyển đổi/chuẩn hóa có chủ đích nếu yêu cầu nghiệp vụ cần so nội dung liên kiểu.

### Mảng tham chiếu `Object[]`

Với mảng chứa đối tượng, `Arrays.equals(Object[] a, Object[] b)` so từng cặp phần tử bằng **`equals()` của phần tử** (có xử lý `null`), không bắt buộc hai phần tử là cùng đối tượng.

~~~java
String[] first = {"Java", "Core"};
String[] second = {new String("Java"), "Core"};
System.out.println(Arrays.equals(first, second)); // true
~~~

Hai chuỗi ở vị trí đầu có thể là các đối tượng String khác nhau, nhưng `String.equals` so nội dung nên hai mảng bằng nhau. Khi băm `Object[]`, `Arrays.hashCode` gọi `hashCode()` của từng phần tử; nếu phần tử triển khai đúng hợp đồng `equals/hashCode` thì toàn mảng giữ được sự nhất quán.

Nếu phần tử là một lớp do bạn viết và lớp đó **không ghi đè `equals`**, kết quả vẫn dựa trên danh tính phần tử. Bởi vậy `Arrays.equals(Object[], Object[])` chỉ là **so sánh một cấp** theo quy tắc của các phần tử, không tự biến mọi loại đối tượng thành giá trị được so theo các trường sâu bên trong.

### Ví dụ chạy được: `String[]`, phần tử null và thứ tự

Tạo tệp `ReferenceArraysDemo.java`:

~~~java
import java.util.Arrays;

public class ReferenceArraysDemo {
    public static void main(String[] args) {
        String[] first = {"Java", "Core"};
        String[] second = {new String("Java"), "Core"};
        String[] reordered = {"Core", "Java"};

        Object[] left = {null, new String("A"), 7};
        Object[] right = {null, "A", Integer.valueOf(7)};

        System.out.println("same String content: "
                + Arrays.equals(first, second));
        System.out.println("same String hash: "
                + (Arrays.hashCode(first) == Arrays.hashCode(second)));
        System.out.println("different order: "
                + Arrays.equals(first, reordered));
        System.out.println("null and objects equal: "
                + Arrays.equals(left, right));
        System.out.println("null and objects hash: "
                + (Arrays.hashCode(left) == Arrays.hashCode(right)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceArraysDemo.java
java ReferenceArraysDemo
~~~

Stdout:

~~~text
same String content: true
same String hash: true
different order: false
null and objects equal: true
null and objects hash: true
~~~

`Integer.valueOf(7)` là đối tượng wrapper; `Integer.equals` so cùng kiểu và cùng giá trị. Mảng `Object[]` có thể chứa nhiều kiểu phần tử, miễn là từng cặp phần tử cung cấp ngữ nghĩa `equals/hashCode` tương thích với yêu cầu.

## 5. Điểm đặc biệt của mảng `float[]` và `double[]`

Đối với `float[]` và `double[]`, `Arrays.equals` xử lý hai giá trị dấu phẩy động tương ứng theo ngữ nghĩa của các phương thức so sánh wrapper (`Float.compare`, `Double.compare`), thay vì chỉ dựa vào trực giác về toán tử `==` trên primitive:

- Các giá trị `NaN` được coi là bằng nhau với nhau khi so bằng `Arrays.equals` (các biểu diễn NaN được chuẩn hóa theo quy tắc tương ứng).
- `+0.0` và `-0.0` được coi là **khác nhau**.
- `Arrays.hashCode` dùng cách tạo hash tương ứng với ngữ nghĩa trên, nên mảng được `Arrays.equals` coi là bằng nhau có cùng hash.

Tạo tệp `FloatingArraysDemo.java`:

~~~java
import java.util.Arrays;

public class FloatingArraysDemo {
    public static void main(String[] args) {
        double[] plusZero = {+0.0d};
        double[] minusZero = {-0.0d};
        double[] nanA = {Double.NaN};
        double[] nanB = {
                Double.longBitsToDouble(0x7ff0000000000001L)
        };

        System.out.println("primitive +0 == -0: " + (+0.0d == -0.0d));
        System.out.println("array +0 equals -0: "
                + Arrays.equals(plusZero, minusZero));
        System.out.println("primitive NaN == NaN: "
                + (Double.NaN == Double.NaN));
        System.out.println("NaN arrays equal: "
                + Arrays.equals(nanA, nanB));
        System.out.println("NaN hashes match: "
                + (Arrays.hashCode(nanA) == Arrays.hashCode(nanB)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FloatingArraysDemo.java
java FloatingArraysDemo
~~~

Stdout:

~~~text
primitive +0 == -0: true
array +0 equals -0: false
primitive NaN == NaN: false
NaN arrays equal: true
NaN hashes match: true
~~~

Với bài toán số học muốn coi hai giá trị gần bằng nhau trong **ngưỡng sai số** (tolerance), `Arrays.equals(double[], double[])` không làm điều đó. Bạn cần quy tắc so sánh riêng. Nếu đối tượng cần một `hashCode()` tương ứng với quy tắc “gần bằng”, phải thiết kế thật cẩn thận vì quan hệ so sai số thông thường có thể không **bắc cầu**, gây khó khăn hoặc làm mất hợp đồng `equals()`.

## 6. Mảng một chiều chứa đối tượng mảng: ranh giới của so sánh nông

Một mảng `int[][]` có thể nhìn như mảng hai chiều, nhưng ở mức Java nó là **mảng một chiều chứa các tham chiếu đến `int[]`**. Do đó:

~~~java
int[][] left = {{1, 2}, {3, 4}};
int[][] right = {{1, 2}, {3, 4}};
~~~

- `Arrays.equals(left, right)` sử dụng overload `Object[]` (vì `int[][]` là mảng của các đối tượng `int[]`) rồi gọi `equals` trên **từng mảng con**. Mảng con không định nghĩa so nội dung; những mảng con mới tạo không cùng danh tính, nên kết quả là `false`.
- `Arrays.hashCode(left)` băm các tham chiếu/đối tượng mảng con theo `hashCode` của từng phần tử; đây **không phải băm sâu nội dung số nguyên**.
- `Arrays.deepEquals(left, right)` và `Arrays.deepHashCode(left/right)` là cặp API thích hợp nếu muốn đi sâu vào mảng lồng nhau.

Ví dụ ngắn:

~~~java
System.out.println(Arrays.equals(left, right));       // false
System.out.println(Arrays.deepEquals(left, right));   // true
~~~

Các đoạn trên giả định đang ở trong phương thức, đã khai báo `left`, `right` và đã `import java.util.Arrays;`. Phạm vi bài hiện tại là **mảng một chiều**. Cặp `deepEquals/deepHashCode` chỉ được nhắc để nhận diện đúng ranh giới: `Arrays.equals/hashCode` bản thường **không đệ quy băm/so nội dung của các đối tượng mảng bên trong**.

## 7. Dùng đúng cặp phương thức trong `equals()` và `hashCode()` của value object

Giả sử có một lớp biểu diễn mã định danh dạng `byte[]`. Nếu định nghĩa hai instance bằng nhau khi **chuỗi byte có cùng nội dung**, thì:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof ByteArrayKey other)) return false;
    return Arrays.equals(bytes, other.bytes);
}

@Override
public int hashCode() {
    return Arrays.hashCode(bytes);
}
~~~

Đây là **đoạn trích minh họa**, giả định lớp có trường `byte[] bytes` và import `java.util.Arrays`. Nếu dùng `bytes.equals(other.bytes)` hoặc `bytes.hashCode()`, ý nghĩa sẽ quay về **danh tính mảng**; đặc biệt nguy hiểm nếu `equals` so nội dung nhưng `hashCode` lại băm danh tính, vì có thể vi phạm hợp đồng của `Object`.

### Ví dụ chạy được: khóa `HashMap` dùng nội dung mảng

Tạo tệp `ByteArrayKeyDemo.java`:

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public class ByteArrayKeyDemo {
    static final class ByteArrayKey {
        private final byte[] bytes;

        ByteArrayKey(byte[] input) {
            this.bytes = input.clone();
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof ByteArrayKey other)) return false;
            return Arrays.equals(bytes, other.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }

        byte[] copyBytes() {
            return bytes.clone();
        }
    }

    public static void main(String[] args) {
        byte[] source = {10, 20, 30};
        ByteArrayKey first = new ByteArrayKey(source);
        ByteArrayKey same = new ByteArrayKey(new byte[] {10, 20, 30});

        Map<ByteArrayKey, String> map = new HashMap<>();
        map.put(first, "found");

        System.out.println("equal content: " + first.equals(same));
        System.out.println("matching hashes: "
                + (first.hashCode() == same.hashCode()));
        System.out.println("lookup: " + map.get(same));

        source[0] = 99;
        byte[] exposedCopy = first.copyBytes();
        exposedCopy[1] = 88;

        System.out.println("key stayed unchanged: "
                + Arrays.equals(first.copyBytes(), new byte[] {10, 20, 30}));
        System.out.println("lookup after edits: " + map.get(same));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ByteArrayKeyDemo.java
java ByteArrayKeyDemo
~~~

Stdout:

~~~text
equal content: true
matching hashes: true
lookup: found
key stayed unchanged: true
lookup after edits: found
~~~

**Vì sao constructor dùng `clone()`?** Mảng mutable: bên ngoài có thể đổi phần tử sau khi khóa đã được đưa vào `HashMap`. Khi hash phụ thuộc nội dung, sửa nội dung có thể khiến lookup hoạt động không đúng như kỳ vọng. Lớp minh họa phòng vệ bằng cách sao chép mảng đầu vào và chỉ trả về **bản sao** qua `copyBytes()`; lớp cũng là `final` và không có phương thức sửa mảng nội bộ.

Nếu một lớp có cả `id` và `byte[] bytes` tham gia equality, hãy kết hợp hash của cả hai:

~~~java
int result = Integer.hashCode(id);
result = 31 * result + Arrays.hashCode(bytes);
return result;
~~~

Đoạn trên chỉ là minh họa trong một lớp có trường `int id` và `byte[] bytes`, với `equals` cũng so `id` và `Arrays.equals(bytes, other.bytes)`. Trong trường hợp có nhiều trường mảng, mỗi trường cần so và băm theo cùng chính sách nông/sâu đã chọn.

## 8. Các API gần tên dễ bị nhầm

| Cách viết | So sánh/băm theo điều gì? | Phù hợp khi nào? |
| --- | --- | --- |
| `a == b` với hai biến mảng | Danh tính: cùng một đối tượng mảng hay không | Cần biết hai tham chiếu có cùng mảng |
| `a.equals(b)` | Thường là danh tính, do mảng dùng `Object.equals` | Ít phù hợp để kiểm tra dữ liệu mảng |
| `Arrays.equals(a, b)` | Nội dung **một chiều**, cùng thứ tự, từng phần tử theo kiểu tương ứng | Mảng primitive, mảng đối tượng một chiều |
| `Arrays.hashCode(a)` | Hash theo nội dung **một chiều** | Kết hợp với `Arrays.equals` trong value object |
| `Arrays.deepEquals(a, b)` | Đi sâu vào mảng được lồng bên trong mảng đối tượng | Cấu trúc mảng lồng nhau |
| `Arrays.deepHashCode(a)` | Hash sâu tương ứng | Kết hợp với `Arrays.deepEquals` |
| `Objects.equals(a, b)` với `a`, `b` là mảng | Null-safe nhưng nếu khác tham chiếu thì gọi `a.equals(b)`, **không tự so phần tử** | Giá trị đối tượng thông thường; tránh dùng thay `Arrays.equals` cho mảng |
| `Objects.hash(a)` với `a` là mảng primitive | Một đối số tham chiếu mảng; **không băm từng phần tử primitive** | Không phù hợp thay `Arrays.hashCode(a)` |

Với `Object[]`, `Objects.hash(array)` còn có **bẫy varargs**: tùy kiểu biểu thức, mảng có thể được coi là chính mảng tham số `Object...`, hoặc là một phần tử được bọc trong varargs. Muốn băm nội dung mảng một chiều thì `Arrays.hashCode(array)` diễn đạt ý định trực tiếp và rõ ràng hơn.

## 9. Chi phí thực thi: khi nào so và băm mảng tốn kém?

`Arrays.equals` có thể phải kiểm tra lần lượt tối đa `n` phần tử nếu hai mảng có cùng độ dài; nếu khác độ dài hoặc gặp phần tử không bằng nhau từ sớm, phương thức có thể kết thúc sớm. Về độ phức tạp, trường hợp xấu nhất là **O(n)** theo chiều dài mảng.

`Arrays.hashCode` phải kết hợp tất cả phần tử để tạo mã hash theo nội dung, nên có độ phức tạp **O(n)**. Với mảng tham chiếu, còn phụ thuộc vào độ phức tạp `hashCode()` của **từng phần tử**. Bản thân `Arrays.hashCode(int[])` không cần boxing từng phần tử thành `Integer`; overload cho mảng primitive xử lý trực tiếp các giá trị nguyên thủy.

Một số JVM có thể tối ưu cách triển khai so sánh mảng (đặc biệt một số kiểu primitive), nhưng không nên giả định một mức tăng tốc cố định. Khi băm mảng lớn trong một vòng lặp nóng, hãy đo bằng profiler/JMH ở hoàn cảnh thực tế trước khi quyết định chiến lược cache hash hay thay đổi cấu trúc dữ liệu.

Đừng dùng hash như phép so nhanh mang ý nghĩa kết luận: hai hash bằng nhau **không chứng minh** hai mảng bằng nhau. Đối với khóa mảng lớn bất biến, có thể cân nhắc cache hash, nhưng phải bảo đảm không còn thao tác sửa mảng ảnh hưởng đến equality; cache cũng có chi phí bộ nhớ và đồng bộ trong những thiết kế chia sẻ giữa luồng.

## 10. Sai lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Hai mảng cùng giá trị thì `a.equals(b)` là `true`. | Mảng dùng `Object.equals`; hãy dùng `Arrays.equals(a, b)`. |
| Hai mảng có hash bằng nhau thì chắc chắn có phần tử giống nhau. | Hash có thể va chạm; kết luận bằng nhau phải dùng `Arrays.equals`. |
| `Arrays.equals` không phân biệt vị trí phần tử. | Thứ tự **có ý nghĩa**; đây không phải phép so tập hợp. |
| `Arrays.equals(null, null)` luôn biên dịch mà không có kiểu cụ thể. | Nhiều overload có thể khiến lời gọi mơ hồ; dùng biến mảng có kiểu hoặc cast. |
| `Arrays.hashCode(new int[0])` bằng `0` giống mảng `null`. | Mảng rỗng trả `1`; mảng `null` trả `0`. |
| `+0.0` và `-0.0` được `Arrays.equals(double[])` coi bằng nhau. | Sai: chúng được coi khác nhau theo quy tắc so tương ứng. |
| `Arrays.equals` tự đi sâu vào `int[][]`. | Sai: phần tử `int[]` của mảng ngoài được so theo `equals` của đối tượng; cân nhắc `deepEquals`. |
| Trong value object, `equals` dùng `Arrays.equals` nhưng `hashCode` dùng `array.hashCode()`. | Có nguy cơ phá hợp đồng; dùng `Arrays.hashCode` tương ứng. |
| Đưa mảng mutable vào hash key rồi sửa phần tử vẫn tra cứu chắc chắn đúng. | Nội dung và hash thay đổi có thể làm lookup không còn tìm thấy khóa; sao chép phòng vệ hoặc giữ dữ liệu bất biến. |
| `Objects.equals(a,b)` tự so nội dung mảng. | Nó chỉ null-safe và chuyển sang `a.equals(b)`; mảng vẫn dùng so danh tính. |

## 11. Checklist áp dụng

Khi cần so sánh hoặc băm **mảng một chiều**:

1. Xác định rõ mục tiêu là so **danh tính** hay so **nội dung**. Chọn `==` cho danh tính, `Arrays.equals` cho nội dung.
2. Chọn overload đúng kiểu mảng. `Arrays.equals(int[], int[])` khác `Arrays.equals(Object[], Object[])` ở quy tắc so phần tử.
3. Tính đến `null`, mảng rỗng, độ dài và thứ tự phần tử.
4. Với `float[]`/`double[]`, nhớ quy tắc cho `NaN` và hai dấu zero.
5. Khi dùng trong một value object, cài đặt `equals()` và `hashCode()` đồng bộ: `Arrays.equals` đi với `Arrays.hashCode`, không đi với `array.hashCode()`.
6. Nếu phần tử của mảng cũng là mảng, xem xét chính sách **nông hay sâu**; không tự động coi `Arrays.equals/hashCode` một chiều là đệ quy.
7. Nếu mảng tham gia làm khóa hash, hạn chế sửa nội dung; cân nhắc bản sao phòng vệ khi nhận và trả mảng.
8. Kiểm thử cặp mảng khác tham chiếu nhưng cùng dữ liệu: `Arrays.equals(a,b)` phải `true` và `Arrays.hashCode(a) == Arrays.hashCode(b)` cũng phải `true`. Kiểm thử thêm các cặp dữ liệu khác nhau, `null`, rỗng và biên số thực khi phù hợp.

**Điểm ghi nhớ:** `Arrays.equals()` và `Arrays.hashCode()` là cặp công cụ tiêu chuẩn để mô tả **bằng nhau theo nội dung và băm theo nội dung của mảng một chiều**. Chúng khác với `equals()/hashCode()` kế thừa từ `Object` trên chính mảng. Khi đặt mảng vào trong một lớp, chính sách so sánh mảng phải khớp với chính sách băm mảng thì các cấu trúc hash mới hoạt động đúng.