# Kiểm thử `null`, `NaN`, `+0.0`, `-0.0`, mảng và cấu trúc lồng trong hợp đồng đối tượng Java

Một phương thức `equals()` trông đúng với dữ liệu thông thường vẫn có thể sai khi gặp `null`, số thực đặc biệt, mảng hoặc đối tượng lồng nhau. Sai lệch thường kéo theo `hashCode()` không nhất quán, hoặc `compareTo()`/`Comparator` coi hai khóa như nhau trong khi `equals()` không coi chúng bằng nhau. Hậu quả có thể là `HashSet` chứa phần tử trùng về mặt nghiệp vụ, `HashMap` tra khóa thất bại hoặc `TreeSet` loại bỏ dữ liệu không mong muốn.

Bài này tập trung **cách xác định kỳ vọng, triển khai và kiểm thử hợp đồng** trong Java 17+: phân biệt toán tử `==` với giá trị bằng nhau, lựa chọn ngữ nghĩa cho `double`/`float`, so sánh mảng đúng chiều sâu, và giữ hợp đồng ổn định với cấu trúc lồng. Không có một phép so sánh nào đúng cho mọi mô hình: phải xác định "bằng nhau" có nghĩa gì với kiểu đối tượng cụ thể, rồi dùng cùng một quy tắc cho `equals()`, `hashCode()` và quan hệ thứ tự nếu cần.

## 1. Các bất biến phải kiểm chứng trước trường hợp biên

Với các đối tượng không `null` là `x`, `y`, `z`:

1. **Phản xạ:** `x.equals(x)` là `true`.
2. **Đối xứng:** `x.equals(y) == y.equals(x)`.
3. **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
4. **Nhất quán:** kết quả không đổi giữa các lần gọi nếu trạng thái tham gia so sánh không thay đổi.
5. **Với `null`:** `x.equals(null)` phải là `false`.
6. **Ràng buộc băm:** nếu `x.equals(y)` thì **bắt buộc** `x.hashCode() == y.hashCode()`. Hai đối tượng không bằng nhau **vẫn có thể** cùng hash; không dùng điều ngược lại làm tiêu chuẩn.
7. **Ràng buộc thứ tự:** `compareTo`/`Comparator` phải nhất quán về dấu khi đảo đối số, có tính bắc cầu và nhất quán theo lớp tương đương của phép so sánh. Với `TreeSet`/`TreeMap`, hai khóa có kết quả `compare(...) == 0` được xem là cùng khóa. Nếu loại dữ liệu kỳ vọng tính duy nhất theo `equals`, nên thiết kế comparator **consistent with equals**, tức `compare(x,y)==0` khi và chỉ khi `x.equals(y)`.

Kiểm thử cần tạo **hai instance độc lập nhưng cùng giá trị**, vì `x.equals(x)` luôn đúng do nhánh `this == other` có thể che lỗi so sánh trường. Với mỗi cặp đã cho là bằng nhau, kiểm tra cả hai hướng `equals` và hash tương ứng; với mỗi giá trị biên, kiểm tra khác biệt có chủ đích.

### Bảng ca kiểm thử tối thiểu

| Ca | Điều cần kiểm tra | Kỳ vọng nền tảng Java |
| --- | --- | --- |
| Đối tượng so với `null` | `x.equals(null)` | `false` |
| Hai tham chiếu đều `null` | `Objects.equals(null, null)` | `true` |
| Thuộc tính nullable | Hai đối tượng có trường `null` cùng vị trí | Bằng nhau nếu các trường khác cùng giá trị |
| `NaN` với toán tử số học | `Double.NaN == Double.NaN` | `false` |
| Hai số `NaN` dưới `Double.equals` | Bao gồm các payload bit khác nhau | `true` |
| `+0.0` với `-0.0` dùng `==` | `+0.0 == -0.0` | `true` |
| `+0.0` với `-0.0` dùng `Double.equals` | So sánh hai wrapper | `false` |
| Mảng nguyên thủy cùng phần tử | `Arrays.equals(a,b)` | `true` |
| Hai mảng lồng cùng dữ liệu | `Arrays.deepEquals(a,b)` | `true` với cấu trúc tương thích, không có chu trình |
| Collection lồng có mảng bên trong | `List.equals` trên phần tử kiểu mảng | **Không** tự trở thành so sánh theo nội dung mảng |
| Đối tượng tùy biến | `equals` cùng `hashCode` | Hai đối tượng bằng nhau có hash bằng nhau |
| Khóa trong sorted collection | `compare(x,y)==0` | `TreeSet`/`TreeMap` xem là một khóa |

## 2. `null`: kiểm tra cả receiver lẫn trường thành phần

`null` không phải một instance để gọi phương thức. Biểu thức `null.equals(x)` không hợp lệ về ngữ nghĩa và nếu biến tham chiếu bằng `null` rồi gọi `reference.equals(x)` sẽ ném `NullPointerException`. Sử dụng `Objects.equals(a,b)` cho phép so sánh hai tham chiếu an toàn:

```java
Objects.equals(null, null);      // true
Objects.equals(null, "value");   // false
Objects.equals("x", "x");        // true
Objects.hashCode(null);          // 0
```

Đoạn trên là các biểu thức minh họa, cần `import java.util.Objects;` khi đặt trong một lớp Java.

Trong một lớp giá trị có trường `name` có thể `null`, nên viết `Objects.equals(name, that.name)` thay cho `name.equals(that.name)`. Trong một mảng/collection, phân biệt rõ **tham chiếu collection bằng `null`**, **collection rỗng** và **collection chứa phần tử `null`**. Đây là ba trạng thái khác nhau tùy hợp đồng nghiệp vụ.

Đừng tự biến mọi `null` thành giá trị mặc định nếu mô hình không yêu cầu. Nếu constructor cấm `null`, dùng `Objects.requireNonNull(...)` và kiểm thử nó ném lỗi ở biên tạo đối tượng; nếu cho phép `null`, `equals`/`hashCode` phải xử lý nhất quán.

Với so sánh có thứ tự, `Comparator.naturalOrder()` không chấp nhận `null`; `Comparator.nullsFirst(...)` hoặc `nullsLast(...)` đưa ra quy tắc rõ ràng khi thứ tự cần chứa `null`. `equals()` của một đối tượng không được coi bản thân bằng `null` chỉ vì comparator đặt `null` ở đầu/cuối.

## 3. `NaN` và số thực: `==` khác `Double.equals()`

Theo IEEE 754 và ngữ nghĩa Java, `NaN` không bằng bất kỳ giá trị nào khi so sánh bằng toán tử `==`, kể cả chính nó:

```java
double a = Double.NaN;
double b = Double.longBitsToDouble(0x7ff8000000000001L);

// a == b               => false
// Double.isNaN(a)       => true
// Double.isNaN(b)       => true
// Double.compare(a, b)  => 0
// Double.valueOf(a).equals(Double.valueOf(b)) => true
```

`b` có payload NaN khác `a` ở dạng bit thô. `Double.equals` dùng `Double.doubleToLongBits` để xét bit với **các giá trị NaN được canonicalize**. Vì vậy nó coi mọi NaN bằng nhau. `Double.hashCode` dùng cách diễn giải bit tương thích, nên những giá trị NaN được `Double.equals` coi bằng nhau cũng có hash giống nhau. `Float.equals`/`Float.hashCode` áp dụng nguyên tắc tương ứng với `float`.

**Không dùng `x == y` cho `double` trong một `equals()` rồi dùng `Double.hashCode(x)` nếu dự định coi các NaN là bằng nhau**: hai đối tượng có NaN tương đương theo mô hình sẽ bị `equals` từ chối, trong khi các thành phần khác có thể cùng. Điều này có thể không vi phạm mệnh đề một chiều về hash, nhưng lại **khác ngữ nghĩa mong muốn**. Để thực hiện ngữ nghĩa kiểu `Double`, dùng `Double.compare(a,b)==0` và `Double.hashCode(a)` hoặc `Double.doubleToLongBits(a)==Double.doubleToLongBits(b)` cùng phép băm tương ứng.

### `+0.0` và `-0.0`: cùng toán tử nhưng khác wrapper

```java
// +0.0 == -0.0                                      => true
// Double.compare(-0.0, +0.0) < 0                     => true
// Double.valueOf(+0.0).equals(Double.valueOf(-0.0)) => false
// Double.hashCode(+0.0) == Double.hashCode(-0.0)    => false
```

Lý do: `+0.0` và `-0.0` có biểu diễn bit khác nhau, dù `==` coi chúng bằng nhau. `Double.compare` định nghĩa một thứ tự toàn phần tiện cho sắp xếp: `-0.0` đứng trước `+0.0`; các NaN đứng sau mọi giá trị số khác và được so sánh như cùng một nhóm. Kiểm thử `Double.compare(a,b)` tại `-Infinity`, số hữu hạn, `-0.0`, `+0.0`, `+Infinity` và `NaN` khi lớp cần thứ tự.

Nếu nghiệp vụ muốn **coi hai số không là cùng một giá trị**, có thể chuẩn hóa cả hai trước so sánh **và trước hash**, ví dụ:

```java
static double normalizeZero(double value) {
    return value == 0.0d ? 0.0d : value;
}

static boolean sameMetric(double left, double right) {
    return Double.compare(normalizeZero(left), normalizeZero(right)) == 0;
}

static int metricHash(double value) {
    return Double.hashCode(normalizeZero(value));
}
```

Đây là các phương thức minh họa đặt bên trong một lớp. Quy tắc này giữ NaN theo cách của `Double.compare`, gộp `+0.0` với `-0.0`, và tránh vi phạm hợp đồng hash. Chọn cách này **chỉ khi phù hợp đặc tả đối tượng**; không thay đổi quy tắc ngầm trong một codebase đã phụ thuộc vào phân biệt signed zero. Khi số thực đại diện cho phép đo, cần quyết định riêng có chấp nhận sai số hay không; **không tùy tiện dùng phép so sánh gần đúng `abs(a-b) < epsilon` cho `equals`**, vì quan hệ đó nói chung không bắc cầu (A gần B, B gần C, nhưng A không gần C), đồng thời làm khóa hash khó đúng.

## 4. Mảng: `equals()` của chính mảng, `Arrays.equals` và `Arrays.deepEquals`

Mảng trong Java **không ghi đè `Object.equals`**, do đó `a.equals(b)` so sánh danh tính đối tượng. Hai mảng khác nhau nhưng chứa cùng phần tử vẫn trả `false`. Sử dụng `Arrays.equals` để so sánh phần tử ở một chiều:

```java
int[] a = {1, 2};
int[] b = {1, 2};

a.equals(b);        // false
Arrays.equals(a,b); // true
Arrays.hashCode(a) == Arrays.hashCode(b); // true
```

Cần `import java.util.Arrays;` nếu đưa các biểu thức vào lớp hoàn chỉnh. `Arrays.equals` có các overload cho mảng nguyên thủy và mảng đối tượng. Với `Object[]`, phép so sánh phần tử dùng ngữ nghĩa `equals` của từng phần tử; nếu một phần tử lại là mảng, lần so sánh đó vẫn là **so sánh tham chiếu**.

Với cấu trúc nhiều tầng, dùng `Arrays.deepEquals(Object[],Object[])` và `Arrays.deepHashCode(Object[])`:

```java
Object[] first = {new int[]{1, 2}, new Object[]{"A", new String[]{"B"}}};
Object[] second = {new int[]{1, 2}, new Object[]{"A", new String[]{"B"}}};

Arrays.equals(first, second);     // false: phần tử kiểu mảng là tham chiếu khác
Arrays.deepEquals(first, second); // true: so sánh mảng con theo nội dung
Arrays.deepHashCode(first) == Arrays.deepHashCode(second); // true
```

Mảng hai chiều kiểu `int[][]` cũng là mảng các tham chiếu `int[]`, do đó cần `deepEquals/deepHashCode` khi kỳ vọng so sánh nội dung mọi tầng. `Arrays.deepEquals` áp dụng cho `Object[]` ở lớp ngoài, **không** gọi trực tiếp `Arrays.deepEquals(int[], int[])` vì không có overload như vậy. Với mảng nguyên thủy một chiều, chọn đúng `Arrays.equals(int[],int[])` và `Arrays.hashCode(int[])`.

Hai tham chiếu mảng đều `null` được `Arrays.equals` coi là bằng nhau, còn một bên `null` và một bên mảng rỗng là khác nhau. `Arrays.deepEquals` cũng xử lý hai tham chiếu mảng `Object[]` đều `null`. Cấu trúc tự chứa chu trình (mảng tham chiếu lại chính nó, hoặc hai mảng tham chiếu vòng) **không thích hợp cho phép đệ quy sâu này**; thiết kế so sánh theo đồ thị có cơ chế phát hiện chu trình riêng khi dữ liệu có vòng.

**Đừng ghép `Arrays.deepEquals(...)` với `Arrays.hashCode(...)` một cách máy móc.** Nếu bằng nhau được xét ở mọi tầng, phép hash cũng phải xét ở mọi tầng; ngược lại có thể làm hai đối tượng bằng nhau tạo hash khác nhau.

### `record` và mảng: tự sinh `equals` chưa chắc là so sánh sâu

Java `record` tự sinh `equals`/`hashCode` theo các component, nhưng component kiểu mảng vẫn dùng đặc tính so sánh danh tính của mảng. Do đó:

```java
record IntBundle(int[] values) {}

new IntBundle(new int[]{1, 2})
    .equals(new IntBundle(new int[]{1, 2})); // false
```

Đó là lý do không giả định `record` tự làm deep equality cho mọi kiểu component. Nếu mảng là một phần danh tính giá trị, cần viết hợp đồng tùy chỉnh và sao chép phòng vệ phù hợp, hoặc biểu diễn bằng kiểu collection bất biến có ngữ nghĩa nội dung.

## 5. Danh sách, tập hợp, bản đồ và cấu trúc lồng

`List.equals` so sánh theo thứ tự từng phần tử; `Set.equals` so theo tập phần tử không quan tâm thứ tự; `Map.equals` so theo ánh xạ khóa–giá trị. Những hợp đồng này dựa trên `equals/hashCode` của phần tử hoặc khóa/giá trị, vì vậy **nội dung bên trong không được so sánh sâu tự động nếu chính kiểu phần tử thiếu hợp đồng giá trị**.

```java
List<List<String>> left = List.of(List.of("a", "b"), List.of("c"));
List<List<String>> right = List.of(List.of("a", "b"), List.of("c"));
// left.equals(right) => true: List lồng có equality theo phần tử.

List<int[]> leftArrays = List.of(new int[]{1, 2});
List<int[]> rightArrays = List.of(new int[]{1, 2});
// leftArrays.equals(rightArrays) => false: phần tử int[] so sánh danh tính.
```

Đây là các biểu thức minh họa bên trong một lớp có `import java.util.List;`. Với nested objects, xác định rõ tầng nào tham gia nhận diện đối tượng và tầng nào được bỏ qua. Một đối tượng bao gồm `List<List<String>>` sẽ so sánh nội dung xuyên các tầng List theo hợp đồng sẵn có, nhưng khi danh sách chứa `int[]` hay đối tượng tự định nghĩa không ghi đè `equals` thì cần xử lý thêm.

Với `Map` có key là mảng hoặc đối tượng mutable, dễ xảy ra lỗi khó thấy: thay đổi trường tham gia `equals/hashCode` **sau khi đưa vào `HashMap`/`HashSet`** có thể khiến không tìm lại được khóa vì bucket hash lúc tra đã khác bucket khi chèn. Giải pháp là thiết kế khóa có trạng thái liên quan đến equality được cố định hợp lý, và **sao chép phòng vệ** khi chứa hoặc trả mảng/collection mutable.

Nếu cần so sánh một cấu trúc lồng pha trộn `Map`, `List`, mảng, và đối tượng tùy biến, không thể gọi duy nhất `Objects.deepEquals` rồi mặc định có một hợp đồng deep equality tổng quát cho mọi loại collection. `Objects.deepEquals` chỉ có xử lý mảng đặc biệt khi cả hai đối số là mảng; nó không đệ quy hiểu quy tắc nghiệp vụ của một đồ thị đối tượng bất kỳ.

## 6. Ví dụ Java 17 hoàn chỉnh: kiểm chứng equality, hash và dữ liệu lồng

Tạo **`ObjectContractEdgeCases.java`**. `Snapshot` là một lớp giá trị có `name` nullable, số `double`, mảng nguyên thủy và `List<List<String>>`. Constructor tạo bản sao của mảng và các List để không cho caller thay đổi trạng thái tham gia `equals/hashCode` sau khi tạo. Trong ví dụ, List bên trong phải không chứa phần tử `null`; List bên ngoài cũng không được chứa List `null` khi không `null` toàn bộ.

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class ObjectContractEdgeCases {
    private static final class Snapshot {
        private final String name;
        private final double metric;
        private final int[] samples;
        private final List<List<String>> groups;

        Snapshot(String name, double metric, int[] samples,
                 List<List<String>> groups) {
            this.name = name;
            this.metric = metric;
            this.samples = samples == null ? null : samples.clone();
            this.groups = groups == null ? null
                    : groups.stream().map(List::copyOf).toList();
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Snapshot that)) {
                return false;
            }
            return Objects.equals(name, that.name)
                    && Double.compare(metric, that.metric) == 0
                    && Arrays.equals(samples, that.samples)
                    && Objects.equals(groups, that.groups);
        }

        @Override
        public int hashCode() {
            int result = Objects.hash(name, Double.hashCode(metric), groups);
            return 31 * result + Arrays.hashCode(samples);
        }
    }

    record IntBundle(int[] values) {}

    private static void check(boolean result, String description) {
        if (!result) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        double otherNaN = Double.longBitsToDouble(0x7ff8000000000001L);
        int[] a = {1, 2};
        int[] b = {1, 2};

        Object[] deepA = {new int[]{1, 2},
                new Object[]{"A", new String[]{"B"}}};
        Object[] deepB = {new int[]{1, 2},
                new Object[]{"A", new String[]{"B"}}};

        List<List<String>> groupsA = List.of(List.of("a", "b"), List.of("c"));
        List<List<String>> groupsB = List.of(List.of("a", "b"), List.of("c"));

        Snapshot first = new Snapshot(null, Double.NaN, a, groupsA);
        Snapshot second = new Snapshot(null, otherNaN, b, groupsB);
        Snapshot plusZero = new Snapshot(null, +0.0, a, groupsA);
        Snapshot minusZero = new Snapshot(null, -0.0, b, groupsB);
        Snapshot emptyA = new Snapshot(null, 0.0, null, null);
        Snapshot emptyB = new Snapshot(null, 0.0, null, null);

        // Kiểm tra hợp đồng, không phụ thuộc việc chạy java -ea.
        check(!first.equals(null), "non-null object must differ from null");
        check(first.equals(first), "reflexivity");
        check(first.equals(second) && second.equals(first), "symmetry");
        check(first.hashCode() == second.hashCode(), "equal objects' hashes");
        check(!plusZero.equals(minusZero), "signed zeros are distinct");
        check(emptyA.equals(emptyB), "null fields must compare safely");
        check(Arrays.equals(a, b), "primitive array contents");
        check(Arrays.deepEquals(deepA, deepB), "nested array contents");
        check(Arrays.deepHashCode(deepA) == Arrays.deepHashCode(deepB),
                "nested array hash");

        Set<Snapshot> snapshots = new HashSet<>();
        snapshots.add(first);
        snapshots.add(second);

        System.out.println("Objects.equals(null,null): "
                + Objects.equals(null, null));
        System.out.println("snapshot.equals(null): " + first.equals(null));
        System.out.println("null fields equal: " + emptyA.equals(emptyB));
        System.out.println("NaN == NaN: " + (Double.NaN == Double.NaN));
        System.out.println("raw NaN bits differ: "
                + (Double.doubleToRawLongBits(Double.NaN)
                    != Double.doubleToRawLongBits(otherNaN)));
        System.out.println("Double.equals(NaN payloads): "
                + Double.valueOf(Double.NaN).equals(Double.valueOf(otherNaN)));
        System.out.println("+0.0 == -0.0: " + (+0.0 == -0.0));
        System.out.println("Double.equals(+0.0,-0.0): "
                + Double.valueOf(+0.0).equals(Double.valueOf(-0.0)));
        System.out.println("Double.compare(-0.0,+0.0)<0: "
                + (Double.compare(-0.0, +0.0) < 0));
        System.out.println("array Object.equals: " + a.equals(b));
        System.out.println("Arrays.equals: " + Arrays.equals(a, b));
        System.out.println("nested Arrays.equals: "
                + Arrays.equals(deepA, deepB));
        System.out.println("Arrays.deepEquals: "
                + Arrays.deepEquals(deepA, deepB));
        System.out.println("Arrays.deepHashCode match: "
                + (Arrays.deepHashCode(deepA) == Arrays.deepHashCode(deepB)));
        System.out.println("record array equals: "
                + new IntBundle(new int[]{1, 2})
                    .equals(new IntBundle(new int[]{1, 2})));
        System.out.println("nested List.equals: "
                + groupsA.equals(groupsB));
        System.out.println("NaN snapshots equal: " + first.equals(second));
        System.out.println("NaN snapshot hashes equal: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("signed-zero snapshots equal: "
                + plusZero.equals(minusZero));
        System.out.println("HashSet size: " + snapshots.size());
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac ObjectContractEdgeCases.java
java ObjectContractEdgeCases
```

Kết quả chuẩn:

```text
Objects.equals(null,null): true
snapshot.equals(null): false
null fields equal: true
NaN == NaN: false
raw NaN bits differ: true
Double.equals(NaN payloads): true
+0.0 == -0.0: true
Double.equals(+0.0,-0.0): false
Double.compare(-0.0,+0.0)<0: true
array Object.equals: false
Arrays.equals: true
nested Arrays.equals: false
Arrays.deepEquals: true
Arrays.deepHashCode match: true
record array equals: false
nested List.equals: true
NaN snapshots equal: true
NaN snapshot hashes equal: true
signed-zero snapshots equal: false
HashSet size: 1
```

Giải thích ý nghĩa kiểm chứng:

- `first` và `second` dùng hai NaN khác payload bit, mảng `int[]` độc lập và hai cấu trúc `List<List<String>>` độc lập. Chúng vẫn bằng nhau vì `Snapshot.equals` xử lý từng kiểu đúng cách; `hashCode` cũng cho cùng kết quả và `HashSet` chỉ giữ một instance theo equality.
- `plusZero` và `minusZero` khác nhau vì chủ động theo ngữ nghĩa của `Double.compare`, phù hợp với thành phần băm `Double.hashCode`. Đây là một quyết định thiết kế, không phải bắt buộc mọi đối tượng số đều phải phân biệt hai số không.
- `emptyA`/`emptyB` kiểm tra `name`, `samples` và `groups` có thể `null`. `Arrays.equals(null,null)` và `Objects.equals(null,null)` hỗ trợ quy tắc này mà không ném `NullPointerException`.
- Hai `IntBundle` record mang mảng nội dung giống nhau vẫn không bằng nhau, vì mảng so sánh theo danh tính.
- `Snapshot` phòng vệ ở constructor, không cung cấp getter trả thẳng mảng mutable. Nếu cần getter, phải trả `samples.clone()` hoặc view/copy không sửa được; đồng thời cần bảo đảm phần tử lồng không phải đối tượng mutable làm thay đổi equality.

Ví dụ dùng dữ liệu không có chu trình và các danh sách bên trong không chứa `null`. Nếu hợp đồng đầu vào cho phép List con `null` hoặc element `null`, phải chọn chiến lược copy và định nghĩa equality tương ứng trước khi dùng trong sản phẩm.

## 7. Kiểm thử so sánh có thứ tự: tránh comparator làm mất khóa

`Comparable`/`Comparator` là hợp đồng **thứ tự**, không phải bản sao của `equals`. Ví dụ `Comparator.comparingDouble(...)` dùng thứ tự theo `Double.compare`, nên phân biệt signed zero và nhóm các NaN. Tuy nhiên, nếu comparator chỉ xét `metric` trong khi `Snapshot.equals` còn xét `name`, `samples` và `groups`, hai `Snapshot` khác nhau có thể bị xếp kết quả `0`. Với `TreeSet`/`TreeMap`, điều đó khiến một trong hai bị coi là trùng khóa.

Một comparator phù hợp cần xét đủ các thành phần nhận diện theo cách nhất quán với `equals`, hoặc tài liệu hóa rằng sorted collection đang dùng **khái niệm khóa khác**. Đối với mảng và cấu trúc lồng, việc định nghĩa thứ tự từ điển phải có quy tắc rõ ràng (thứ tự phần tử, độ dài, `null`, signed zero, NaN), tránh chỉ dựa `toString` hay giá trị hash.

Bộ ca kiểm thử cho comparator nếu được sử dụng:

1. `sign(compare(x,y)) == -sign(compare(y,x))`, với cách kiểm tra dấu an toàn bằng `Integer.signum`.
2. Nếu `compare(x,y)>0` và `compare(y,z)>0` thì `compare(x,z)>0`; tương tự với `<0`.
3. Nếu `compare(x,y)==0` thì dấu của `compare(x,z)` và `compare(y,z)` phải giống nhau với mọi `z`.
4. Nếu cần consistent with equals: `compare(x,y)==0` đúng chính xác khi `x.equals(y)`; đặc biệt kiểm tra `null` (khi comparator hỗ trợ), NaN, signed zero, mảng trùng nội dung và nested fields khác nhau.
5. Với `TreeSet`, thử thêm hai instance bằng nhau; và hai instance khác nhau theo đặc tả để chắc không bị gộp nhầm.

Không viết comparator dạng `(int)(a-b)` cho số thực hay số nguyên rộng: có thể tràn số, mất phần lẻ, biến NaN thành giá trị sai và phá tính bắc cầu. Dùng `Double.compare`, `Integer.compare` hoặc comparator chuẩn phù hợp.

## 8. Thiết kế dữ liệu kiểm thử và test tự động

Để kiểm chứng hợp đồng một cách có hệ thống, lập ma trận ca thay vì chỉ thử một cặp:

| Nhóm dữ liệu | Trường hợp đại diện | Điều cần assert |
| --- | --- | --- |
| `null` | đối tượng `null`; trường `null`/không `null`; mảng `null`/rỗng | Không ném lỗi bất ngờ, đúng quy tắc equality |
| Số thực | số thường, hai NaN khác bit, `±0.0`, `±Infinity` | Equality, hash, ordering đúng theo đặc tả |
| Mảng | cùng tham chiếu, hai mảng độc lập cùng phần tử, phần tử khác, độ dài khác | Đúng nông/sâu; hash tương ứng |
| Nested | `List<List<T>>`, mảng trong `List`, mảng trong `Map`, object con | Đúng ngữ nghĩa từng tầng |
| Tính ổn định | Đầu vào mutable bị sửa sau constructor | Trạng thái khóa không đổi nếu lớp cam kết immutable |
| Tính tương đương | ba đối tượng `x,y,z` cùng nội dung và dữ liệu biên | Phản xạ, đối xứng, bắc cầu, hash |
| Collections | `HashSet`/`HashMap` và `TreeSet`/`TreeMap` nếu có comparator | Không gộp nhầm/không mất khả năng tra khóa |

Nên dùng test có tên chỉ rõ tình huống, chẳng hạn `equalInstancesWithDistinctNaNPayloadsShareHash`, `negativeZeroAndPositiveZeroFollowChosenPolicy`, `nestedPrimitiveArraysUseDeepEquality` và `defensiveCopyKeepsHashStable`. Với JUnit 5, có thể tổ chức `@ParameterizedTest` cùng `@MethodSource` để chạy bảng cặp giá trị, và gọi các assertion như `assertEquals`/`assertNotEquals`/`assertTrue`. Cần nhớ `assertEquals(double, double)` trong thư viện kiểm thử có quy tắc riêng với kiểu số thực; khi muốn kiểm tra **chính xác hợp đồng do bạn xây**, hãy assert biểu thức `Double.compare(...)`, `x.equals(y)`, `Objects.equals(...)`, `Arrays.equals(...)` hoặc `Arrays.deepEquals(...)` cụ thể, không suy diễn mọi overload `assertEquals` có cùng logic với primitive `==`.

Với property-based testing (như jqwik hoặc QuickTheories) nếu dự án có thư viện, tạo giá trị gồm `null` có kiểm soát, kích cỡ mảng biến đổi, nested collections và những mẫu bit tạo NaN khác nhau; kiểm tra các bất biến ở mục 1 thay vì chỉ đầu ra cố định. Với dữ liệu đệ quy, đặt giới hạn độ sâu và tránh chu trình khi hợp đồng chưa hỗ trợ chu trình.

### Những lỗi phổ biến cần chủ động phát hiện

- Dùng `a.equals(b)` với `a` nullable gây `NullPointerException`; dùng `Objects.equals` hoặc bảo đảm non-null trước.
- Dùng `==` cho trường `double` nhưng mong mọi NaN bằng nhau; dùng `Double.compare`/`Double.hashCode` theo cùng chính sách.
- Coi `+0.0` và `-0.0` bằng nhau trong `equals` nhưng dùng `Double.hashCode` gốc trong `hashCode`; sẽ vi phạm hợp đồng hash. Phải chuẩn hóa cùng cách trước cả hai thao tác.
- Dùng `Arrays.equals` cho `int[][]` hoặc `Object[]` chứa mảng con rồi tưởng được so sâu; cần `Arrays.deepEquals` và `deepHashCode` đúng cặp.
- Để record tự sinh equality cho component là mảng trong khi mong so sánh nội dung; phải thay kiểu representation hoặc cài hợp đồng rõ ràng.
- Dùng mảng/collection mutable làm trường hash key nhưng cho bên ngoài sửa được; thiết kế bản sao phòng vệ và API bất biến.
- Viết comparator chỉ so một phần của đối tượng rồi sử dụng `TreeSet` như thể nó thực hiện uniqueness theo toàn bộ `equals`.
- Kiểm thử chỉ cùng tham chiếu, bỏ qua hai instance độc lập, các giá trị biên và quan hệ hash.

**Tự kiểm tra:** (1) Hai `double` NaN khác payload bit có thể bằng nhau theo `Double.equals` không? Có. (2) `+0.0 == -0.0` có đúng không, trong khi `Double.equals` khác nhau? Đúng. (3) Hai `int[][]` độc lập có dữ liệu giống nhau nên dùng `Arrays.equals` hay `Arrays.deepEquals`? `deepEquals`. (4) Nếu chuẩn hóa signed zero trong `equals` thì có phải chuẩn hóa khi băm không? Bắt buộc. (5) `HashMap` và `TreeMap` có cùng định nghĩa khóa trùng không? Không: `HashMap` dựa vào equality/hash, còn `TreeMap` dựa vào comparator hoặc natural order.

**Nguyên tắc cốt lõi:** xác định cùng một ngữ nghĩa giá trị xuyên suốt **so sánh – băm – thứ tự – tính bất biến của khóa**, rồi kiểm thử riêng `null`, NaN, hai dấu của số không, mảng một/nhiều chiều và từng tầng dữ liệu lồng. Chính các ca biên này mới làm lộ một hợp đồng đối tượng tưởng như đúng nhưng không đủ vững khi dùng với collection Java.
