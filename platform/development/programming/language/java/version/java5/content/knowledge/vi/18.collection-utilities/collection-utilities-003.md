# Arrays.hashCode và Arrays.deepHashCode

## 1. Vì sao mảng cần hàm băm theo nội dung?

Trong Java, mảng là đối tượng, nhưng `equals()` và `hashCode()` gọi trực tiếp trên mảng không tự xét từng phần tử:

```java
int[] first = {1, 2};
int[] second = {1, 2};

boolean same = first.equals(second); // false: hai đối tượng mảng khác nhau.
```

Hai mảng có cùng nội dung không vì thế mà là cùng một đối tượng. Nếu muốn mô hình giá trị dựa trên phần tử, cần chọn cặp công cụ phù hợp:

| Quy tắc bằng nhau | Hàm băm tương ứng |
|---|---|
| Nội dung một cấp: `Arrays.equals(...)` | `Arrays.hashCode(...)` |
| Nội dung mảng lồng: `Arrays.deepEquals(...)` | `Arrays.deepHashCode(...)` |

Điều quan trọng không phải chọn hàm “băm mạnh hơn”, mà là **hàm băm phải nhất quán với quy tắc bằng nhau**.

Theo [hợp đồng Object.hashCode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#hashCode()), hai đối tượng bằng nhau phải có cùng mã băm. Chiều ngược lại không được bảo đảm: hai đối tượng khác nhau vẫn có thể cùng mã băm.

Bài dùng các API còn áp dụng hiện nay và chương trình kiểm chứng Java 17+.

## 2. Arrays.hashCode: băm một cấp của mảng

`Arrays.hashCode` có các overload cho mảng kiểu nguyên thủy và mảng đối tượng, ví dụ:

```java
Arrays.hashCode(new int[] {1, 2});
Arrays.hashCode(new byte[] {1, 2});
Arrays.hashCode(new String[] {"A", "B"});
```

Những lời gọi này chọn overload theo kiểu mảng của biểu thức đối số. Không có một kết quả duy nhất áp dụng cho mọi kiểu phần tử dù nhìn các giá trị có vẻ giống nhau.

### Với int[]

Có thể hình dung cách kết hợp giá trị như sau:

```java
int result = 1;
for (int element : values) {
    result = 31 * result + element;
}
```

Đây là mảnh minh họa công thức cho mảng `int[]` khác null, giả định đã có biến `values`.

Với `[1, 2]`:

```text
ban đầu: 1
sau 1: 31 × 1 + 1 = 32
sau 2: 31 × 32 + 2 = 994
```

Thứ tự tham gia vào phép kết hợp, nên đảo phần tử có thể đổi mã băm. Kết quả là một `int`; tràn số theo phép toán số nguyên Java là một phần bình thường của cách tính, không phải một ngoại lệ số học.

Các overload nguyên thủy khác có quy tắc chuyển giá trị phần tử thành thành phần mã băm phù hợp với kiểu đó. Không dùng riêng công thức “cộng trực tiếp phần tử” của `int[]` cho mọi kiểu nguyên thủy.

### Với Object[]

Ở một cấp mảng đối tượng:

- Phần tử null góp giá trị băm 0.
- Phần tử khác null góp kết quả `hashCode()` của chính phần tử.
- Các giá trị được kết hợp theo vị trí.

Ví dụ `new Object[] {"A", null}`:

```text
String "A" có hashCode = 65
31 × (31 × 1 + 65) + 0 = 2976
```

Điểm dễ bỏ sót: nếu một phần tử lại là một mảng, `Arrays.hashCode(Object[])` chỉ gọi `hashCode()` trên đối tượng mảng con. Nó **không tự đi sâu vào nội dung mảng con**.

Vì vậy, “mảng đối tượng” không đồng nghĩa với “mọi đối tượng bên trong được băm sâu”.

## 3. Null, mảng rỗng và va chạm

Với các overload `Arrays.hashCode`:

- Tham chiếu mảng null có mã băm 0.
- Mảng rỗng có mã băm 1.

Vì có nhiều overload mảng, lời gọi chỉ viết `Arrays.hashCode(null)` bị mơ hồ. Chỉ rõ kiểu khi muốn kiểm chứng:

```java
Arrays.hashCode((int[]) null);
Arrays.hashCode((Object[]) null);
```

Mảng null và mảng rỗng là hai trạng thái khác nhau; đừng đổi một trạng thái thành trạng thái kia chỉ để có một mã băm.

### Mã băm không phải mã nhận dạng duy nhất

Hai mảng sau khác nhau nhưng cùng mã băm:

```text
[0, 31] → 31 × (31 + 0) + 31 = 992
[1, 0]  → 31 × (31 + 1) + 0  = 992
```

Đây là **va chạm mã băm (hash collision)** hợp lệ. Không kiểm tra bằng nhau bằng cách chỉ so hai số băm.

Một cấu trúc như `HashMap` còn dùng `equals` để phân biệt các khóa có mã băm liên quan; chính tính nhất quán của cả hai phương thức mới làm mô hình khóa hoạt động đúng.

## 4. Chương trình kiểm chứng băm một cấp

Lưu tệp `ArrayHashDemo.java`:

```java
import java.util.Arrays;

public class ArrayHashDemo {
    public static void main(String[] args) {
        int[] first = {1, 2};
        int[] second = {1, 2};
        System.out.println("array equals=" + first.equals(second));
        System.out.println("content equals=" + Arrays.equals(first, second));
        System.out.println("first content hash=" + Arrays.hashCode(first));
        System.out.println("second content hash=" + Arrays.hashCode(second));
        System.out.println("reversed hash=" + Arrays.hashCode(new int[] {2, 1}));
        System.out.println("empty hash=" + Arrays.hashCode(new int[0]));
        System.out.println("null hash=" + Arrays.hashCode((int[]) null));
        System.out.println("object hash="
                + Arrays.hashCode(new Object[] {"A", null}));

        int[] collisionA = {0, 31};
        int[] collisionB = {1, 0};
        System.out.println("collision equals="
                + Arrays.equals(collisionA, collisionB));
        System.out.println("collision hashes=" + Arrays.hashCode(collisionA)
                + "," + Arrays.hashCode(collisionB));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror ArrayHashDemo.java
java ArrayHashDemo
```

Stdout:

```text
array equals=false
content equals=true
first content hash=994
second content hash=994
reversed hash=1024
empty hash=1
null hash=0
object hash=2976
collision equals=false
collision hashes=992,992
```

Cần phân biệt ba kết luận:

1. `first.equals(second)` là false vì hai tham chiếu chỉ tới hai mảng khác nhau.
2. `Arrays.equals(first, second)` là true vì nội dung một cấp bằng nhau.
3. Hai mã băm nội dung bằng nhau là điều bắt buộc bởi quy tắc bằng nhau tương ứng.

Ví dụ không in mã băm đối tượng trực tiếp của các mảng. Không cần giả định chúng là địa chỉ bộ nhớ hoặc nhất thiết khác nhau; mã băm đối tượng cũng có thể va chạm.

Các quy tắc của nhóm phương thức được công bố trong [tài liệu Arrays.hashCode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#hashCode(int%5B%5D)).

## 5. Arrays.deepHashCode: đi sâu qua cấu trúc mảng lồng

`Arrays.deepHashCode` nhận một `Object[]`. Khi gặp từng phần tử:

- Null: dùng 0.
- Mảng đối tượng: tiếp tục băm sâu mảng đó.
- Mảng nguyên thủy: dùng overload `Arrays.hashCode` phù hợp.
- Đối tượng không phải mảng: dùng `hashCode()` của đối tượng đó.

Kết quả cũng được kết hợp theo vị trí. Nó phù hợp với phép so sánh `Arrays.deepEquals`.

### Mảng hai chiều nguyên thủy cũng dùng được

`int[][]` là một mảng mà các phần tử là tham chiếu `int[]`. Do đó, tầng ngoài là mảng đối tượng và dùng được với `deepHashCode`:

```java
int[][] matrix = {{1, 2}, {3}};
int hash = Arrays.deepHashCode(matrix);
```

Ngược lại, một `int[]` đơn lẻ không phải `Object[]`:

```java
int[] values = {1, 2};
int hash = Arrays.hashCode(values);

// Không biên dịch:
// int wrong = Arrays.deepHashCode(values);
```

Đừng bọc mảng vào một tầng mới chỉ để gọi được “deep” nếu mô hình dữ liệu thực tế là mảng nguyên thủy một chiều. Việc thêm một tầng mảng có thể làm thay đổi phép kết hợp và mã băm.

### Deep chỉ nói về các mảng lồng

`deepHashCode` không tự đi xuyên mọi đồ thị đối tượng. Nếu một phần tử là một `List`, một đối tượng nghiệp vụ hoặc một wrapper, nó dùng `hashCode()` của đối tượng ấy.

Ví dụ, một `List<int[]>` có quy tắc băm riêng của `List`; không phải vì nó nằm trong `Object[]` mà `deepHashCode` tự chuyển mọi mảng bên trong list sang so sánh nội dung. Nếu cần mô hình bằng nhau sâu hơn, phải định nghĩa hợp đồng của kiểu dữ liệu đó.

[Tài liệu Arrays.deepHashCode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#deepHashCode(java.lang.Object%5B%5D)) mô tả phạm vi mảng lồng và mối liên hệ với `deepEquals`.

## 6. Chương trình so sánh shallow và deep

Lưu tệp `DeepArrayHashDemo.java`:

```java
import java.util.Arrays;

public class DeepArrayHashDemo {
    public static void main(String[] args) {
        Object[] left = {new int[] {1, 2}, new Object[] {"X", null}};
        Object[] right = {new int[] {1, 2}, new Object[] {"X", null}};

        System.out.println("shallow equals=" + Arrays.equals(left, right));
        System.out.println("deep equals=" + Arrays.deepEquals(left, right));
        System.out.println("left deep hash=" + Arrays.deepHashCode(left));
        System.out.println("right deep hash=" + Arrays.deepHashCode(right));
        int shallowFormula = 31 * (31 + left[0].hashCode())
                + left[1].hashCode();
        System.out.println("shallow uses element hash="
                + (Arrays.hashCode(left) == shallowFormula));

        int[][] matrix = {{1, 2}, {3}};
        System.out.println("matrix deep hash=" + Arrays.deepHashCode(matrix));
        System.out.println("empty deep hash="
                + Arrays.deepHashCode(new Object[0]));
        System.out.println("null deep hash=" + Arrays.deepHashCode(null));

        float[] nanA = {Float.NaN};
        float[] nanB = {Float.intBitsToFloat(0x7fc00001)};
        System.out.println("NaN content equals=" + Arrays.equals(nanA, nanB));
        System.out.println("NaN hashes equal="
                + (Arrays.hashCode(nanA) == Arrays.hashCode(nanB)));
        System.out.println("signed zeros equal="
                + Arrays.equals(new float[] {0.0f}, new float[] {-0.0f}));
        System.out.println("signed zero hashes equal="
                + (Arrays.hashCode(new float[] {0.0f})
                == Arrays.hashCode(new float[] {-0.0f})));
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror DeepArrayHashDemo.java
java DeepArrayHashDemo
```

Stdout:

```text
shallow equals=false
deep equals=true
left deep hash=35464
right deep hash=35464
shallow uses element hash=true
matrix deep hash=31809
empty deep hash=1
null deep hash=0
NaN content equals=true
NaN hashes equal=true
signed zeros equal=false
signed zero hashes equal=false
```

### Vì sao shallow equals là false nhưng deep equals là true?

`left` và `right` chứa các mảng con được tạo riêng:

```text
left  → [ int[]{1,2}, Object[]{"X", null} ]
right → [ int[]{1,2}, Object[]{"X", null} ]
```

So sánh một cấp thấy các mảng con là những đối tượng khác nhau. So sánh sâu nhìn vào nội dung mảng con và nhận thấy chúng bằng nhau.

Tương ứng:

- `Arrays.hashCode(left)` dùng mã băm đối tượng của hai mảng con.
- `Arrays.deepHashCode(left)` dùng nội dung của các mảng con.
- Vì `deepEquals(left, right)` là true, hai mã băm sâu phải bằng nhau.

Chương trình chỉ kiểm tra rằng mã băm một cấp khớp với công thức gọi `hashCode()` của từng phần tử. Nó không in một con số mã băm đối tượng rồi yêu cầu mọi lần chạy phải giống con số đó, cũng không giả định hai mảng con khác nhau bắt buộc có mã băm khác nhau.

### Tính mã băm cho matrix

Với `{{1, 2}, {3}}`:

```text
hash hàng thứ nhất = Arrays.hashCode([1,2]) = 994
hash hàng thứ hai  = Arrays.hashCode([3])   = 34

hash tầng ngoài = 31 × (31 + 994) + 34 = 31809
```

Đây là cách băm nội dung từng hàng rồi kết hợp ở tầng ngoài. Nếu dùng `Arrays.hashCode(matrix)`, các hàng `int[]` được băm như đối tượng mảng, không phải theo công thức nội dung hàng vừa dùng.

### Float: NaN và hai số không có dấu khác nhau

Các overload số thực nhất quán với quy tắc `Arrays.equals` dành cho số thực:

- Những biểu diễn NaN trong ví dụ được xem là bằng nhau theo phép so sánh nội dung mảng, nên mã băm bằng nhau.
- `0.0f` và `-0.0f` được phân biệt trong phép so sánh nội dung mảng và cho kết quả băm khác nhau trong ví dụ.

Không suy diễn chỉ từ toán tử `==` của số thực để tự viết một công thức băm mảng thay thế. Cặp công cụ bằng nhau/băm cần giữ cùng quy tắc.

## 7. Dùng mảng làm khóa theo nội dung

Gọi `Arrays.hashCode(array)` một lần không thay đổi cách `HashMap` xử lý một khóa có kiểu `int[]`. Nếu đưa trực tiếp mảng vào map, khóa vẫn dùng `equals()`/`hashCode()` của đối tượng mảng.

Muốn có khóa theo nội dung, có thể tạo một kiểu bao định nghĩa đồng thời `equals` và `hashCode`. Đồng thời phải bảo vệ nội dung dùng cho khóa khỏi bị sửa ngoài ý muốn.

Lưu tệp `ArrayKeyDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ArrayKeyDemo {
    static final class IntArrayKey {
        private final int[] values;

        IntArrayKey(int[] values) {
            this.values = Objects.requireNonNull(values, "values").clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || other instanceof IntArrayKey that
                    && Arrays.equals(values, that.values);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        Map<int[], String> raw = new HashMap<>();
        raw.put(new int[] {1, 2}, "raw");
        System.out.println("raw lookup=" + raw.get(new int[] {1, 2}));

        int[] source = {1, 2};
        Map<IntArrayKey, String> byContent = new HashMap<>();
        byContent.put(new IntArrayKey(source), "first");
        source[0] = 99;
        System.out.println("after source change="
                + byContent.get(new IntArrayKey(new int[] {1, 2})));
        byContent.put(new IntArrayKey(new int[] {1, 2}), "updated");
        System.out.println("content keys=" + byContent.size());
        System.out.println("content lookup="
                + byContent.get(new IntArrayKey(new int[] {1, 2})));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror ArrayKeyDemo.java
java ArrayKeyDemo
```

Kết quả:

```text
raw lookup=null
after source change=first
content keys=1
content lookup=updated
```

### Khóa mảng trực tiếp

`raw.get(new int[] {1, 2})` không tìm thấy khóa đã thêm bằng một đối tượng mảng khác. Cùng nội dung không đủ vì map chưa có mô hình khóa dựa trên phần tử.

### Kiểu bao nội dung

`IntArrayKey` có các điểm chủ đích:

- Lớp là `final` để hợp đồng bằng nhau không bị mở rộng tùy ý qua lớp con.
- Constructor sao chép mảng `int[]` đầu vào.
- Không trả ra tham chiếu mảng bên trong.
- `equals` dùng `Arrays.equals`.
- `hashCode` dùng `Arrays.hashCode`.

Sau khi tạo khóa, việc sửa `source[0]` không sửa mảng được giữ bên trong khóa. Thêm một khóa mới có cùng nội dung làm cập nhật giá trị của cùng khóa logic, nên kích thước map vẫn là 1.

Đây là bản sao đủ cho một mảng `int[]`. Với mảng đối tượng lồng, chỉ gọi `clone()` ở tầng ngoài không tạo bản sao sâu của các đối tượng/mảng con; cần thiết kế mức bất biến phù hợp nếu nội dung sâu tham gia bằng nhau.

Không giả định một record chứa trường mảng sẽ tự dùng `Arrays.equals` hoặc `deepEquals` cho trường đó. Khi muốn ngữ nghĩa nội dung, phải xác định rõ cách bằng nhau và băm tương ứng.

## 8. Thay đổi dữ liệu và giới hạn cần hiểu

### Hash theo nội dung có thể đổi khi nội dung đổi

`Arrays.hashCode` và `deepHashCode` tính dựa trên dữ liệu tại lúc gọi. Chúng không tự làm mảng bất biến và không đăng ký cập nhật với một `HashMap` đã chứa khóa.

Nếu dữ liệu tham gia `equals`/`hashCode` của khóa bị sửa sau khi đưa vào cấu trúc băm, việc tra cứu có thể không còn đáp ứng kỳ vọng. Không lấy việc một lần thử vẫn tìm được khóa làm bằng chứng rằng sửa khóa là an toàn.

Ngay cả khi chỉ lưu sẵn mã băm cũ, việc thay đổi nội dung được dùng bởi `equals` vẫn làm mô hình khóa thiếu nhất quán. Ví dụ kiểu bao giải quyết bằng bản sao và không để lộ mảng nội bộ.

### DeepHashCode không xử lý đồ thị có chu trình theo một hợp đồng an toàn

Một mảng đối tượng có thể trực tiếp hoặc gián tiếp chứa chính nó. Hành vi `deepHashCode` với cấu trúc tự tham chiếu như vậy không được xác định theo hợp đồng; không dùng nó làm thuật toán băm đồ thị có phát hiện chu trình.

Ví dụ cấu trúc cần tránh đưa vào phép băm sâu này:

```java
Object[] cycle = new Object[1];
cycle[0] = cycle;
// Không coi Arrays.deepHashCode(cycle) là phép băm đồ thị có hỗ trợ chu trình.
```

Không chạy ví dụ rồi phụ thuộc vào một ngoại lệ cụ thể để coi đó là giao thức phát hiện chu trình.

### Chi phí phụ thuộc lượng dữ liệu được đọc

Với mảng một chiều, phép băm đi qua các phần tử; chi phí còn phụ thuộc cách băm của từng phần tử nếu là mảng đối tượng.

Với mảng lồng, phép băm sâu đi qua các tầng mảng cần xét. Những tham chiếu lặp lại không tự trở thành một cơ chế ghi nhớ băm đồ thị. Không gọi lặp lại trên dữ liệu rất lớn chỉ vì phương thức trả về một số `int` ngắn.

### Mã băm này không phải dấu vân tay duy nhất

`hashCode` phục vụ hợp đồng băm trong chương trình. Nó có va chạm, có thể âm và không phải một chứng cứ rằng hai nội dung giống nhau. Cũng không tự trở thành giá trị bền vững qua các lần chạy khi cấu trúc chứa đối tượng có mã băm phụ thuộc từng đối tượng.

Nếu cần chứng minh nội dung bằng nhau, dùng phép so sánh nội dung phù hợp. Nếu cần một thuật toán dấu vân tay hoặc băm mật mã, đó là yêu cầu khác với hai API trong bài.

## 9. Chọn đúng cặp phương thức

| Dữ liệu và ý định | Phép bằng nhau | Phép băm |
|---|---|---|
| `int[]` theo phần tử | `Arrays.equals` | `Arrays.hashCode` |
| `String[]` theo chuỗi và vị trí | `Arrays.equals` | `Arrays.hashCode` |
| `int[][]` theo nội dung các hàng | `Arrays.deepEquals` | `Arrays.deepHashCode` |
| `Object[]` có mảng lồng, muốn xét nội dung mảng con | `Arrays.deepEquals` | `Arrays.deepHashCode` |
| `Object[]` muốn xét mỗi phần tử bằng equals của chính nó | `Arrays.equals` | `Arrays.hashCode` |

Không chọn `deepHashCode` chỉ vì tên “deep” có vẻ đầy đủ hơn. Nếu `equals` của kiểu bao chỉ xét một cấp, hãy băm theo cùng ngữ nghĩa đó. Nếu kiểu bao xét mảng lồng theo nội dung, hãy dùng cơ chế sâu tương ứng.

Tương tự, không thay công thức cho một trường `int[]` bằng `Objects.hash(values)` rồi mặc định nó băm nội dung các số. Với `int[]` truyền như một đối số của varargs đối tượng, chính đối tượng mảng trở thành một phần tử được băm. Dùng `Arrays.hashCode(values)` khi ý định là băm nội dung mảng nguyên thủy.

## 10. Tự kiểm tra

### Câu 1

Hai mảng có mã băm 992. Có thể kết luận chúng cùng nội dung không?

**Đáp án:** Không. `[0,31]` và `[1,0]` là ví dụ khác nội dung nhưng trùng mã băm.

### Câu 2

Hai `int[][]` có các hàng mới được tạo riêng nhưng cùng nội dung. Muốn coi chúng bằng nhau theo từng số thì chọn cặp nào?

**Đáp án:** `Arrays.deepEquals` và `Arrays.deepHashCode`.

### Câu 3

Vì sao không viết trực tiếp `Arrays.deepHashCode(new int[] {1,2})`?

**Đáp án:** Phương thức nhận `Object[]`; một `int[]` không phải mảng đối tượng. Với mảng nguyên thủy một chiều, dùng overload `Arrays.hashCode` tương ứng.

### Câu 4

Sau khi tính mã băm nội dung, đưa chính mảng vào HashMap có khiến map dùng nội dung làm khóa không?

**Đáp án:** Không. Cách map so sánh và băm khóa phụ thuộc `equals`/`hashCode` của đối tượng khóa. Cần một kiểu có hợp đồng nội dung nếu đó là ý định.

### Câu 5

Sao chép tầng ngoài của `Object[][]` có đủ để mọi nội dung sâu không đổi không?

**Đáp án:** Không. Các mảng và đối tượng bên trong vẫn có thể được chia sẻ; mức sao chép phải phù hợp phần dữ liệu tham gia bằng nhau/băm.

Khi chọn hàm băm, hãy xác định **bằng nhau theo tham chiếu hay nội dung → một cấp hay mảng lồng → phần tử nào có thể thay đổi → mã băm được dùng trong hợp đồng nào**. Tính nhất quán với phép bằng nhau mới là tiêu chí quyết định.
