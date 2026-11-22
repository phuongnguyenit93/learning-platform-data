# Java 7 — Objects: So sánh mảng lồng nhau bằng `deepEquals`

## Mục tiêu

Khi một giá trị Java là mảng nhiều chiều, mảng chứa các mảng khác, hoặc một `Object[]` trộn các mảng kiểu nguyên thủy với phần tử thông thường, dùng `==` hay `Objects.equals` thường **không** kiểm tra toàn bộ nội dung như mong muốn.

Java 7 giới thiệu tiện ích `java.util.Objects`, trong đó `Objects.deepEquals(Object a, Object b)` giúp so sánh **cấu trúc mảng lồng nhau theo từng phần tử**, dùng các phép so sánh phù hợp với mảng đối tượng và các loại mảng nguyên thủy. API này **vẫn được hỗ trợ trên Java hiện đại**. Đừng nhầm với `Arrays.deepEquals(Object[], Object[])` hoặc `Objects.equals(Object, Object)`.

Bài học tập trung vào câu hỏi: **Khi nào `deepEquals` trả `true`, khi nào trả `false`, và những giới hạn quan trọng nào không thể bỏ qua?**

Sau khi học, bạn có thể:

1. Phân biệt so sánh **cùng tham chiếu**, **bằng nhau theo `equals`** và **bằng nhau sâu đối với mảng**.
2. Viết đúng `Objects.deepEquals` cho `int[]`, `int[][]`, `String[][]` và mảng `Object[]` lồng nhiều kiểu.
3. Giải thích vì sao `Objects.equals` và `Arrays.equals` cho kết quả khác `Objects.deepEquals` với các mảng con là đối tượng khác nhau.
4. Nhận ra trường hợp `null`, khác chiều dài/cấu trúc, khác kiểu mảng nguyên thủy và các ngoại lệ của so sánh dấu phẩy động.
5. Không nhầm `Objects.deepEquals` với so sánh sâu tùy ý của `List`, `Map`, object graph hoặc với deep clone.
6. Sử dụng `Arrays.deepHashCode`, `Arrays.deepToString` khi phù hợp, đồng thời hiểu giới hạn khi dùng mảng làm key trong hash collection.
7. Viết test cho dữ liệu lồng nhau, tránh vòng tham chiếu/cyclic arrays và đánh giá ảnh hưởng của mutable arrays.

Các chương trình chạy được bằng **JDK 17+** và tương thích cú pháp hiện hành. Mỗi tệp có lệnh `javac --release 17` cùng stdout đã được kiểm tra trực tiếp.

## 1. Vì sao `==` và `Objects.equals` chưa đủ?

Trong Java, mảng là **đối tượng**. Hai lần gọi `new int[]{1, 2}` tạo ra hai object khác nhau dù phần tử giống hệt. Mảng không override `Object.equals` theo kiểu so sánh từng phần tử, vì vậy:

```java
int[] first = {1, 2};
int[] second = {1, 2};

System.out.println(first == second);               // false
System.out.println(Objects.equals(first, second)); // false
System.out.println(Objects.deepEquals(first, second)); // true
```

Đây là **mảnh minh họa đặt trong một phương thức**, với `import java.util.Objects;`. Ba kết quả được giải thích như sau:

- `first == second` hỏi hai biến có cùng tham chiếu tới **chính một object** không. Hai mảng được tạo riêng, nên `false`.
- `Objects.equals(first, second)` null-safe, nhưng đối với array riêng biệt nó dựa trên phép `equals` thông thường của mảng, không duyệt các phần tử, nên `false`.
- `Objects.deepEquals(first, second)` có logic đặc biệt dành cho **mảng**, so sánh `int[]` theo nội dung, nên `true`.

Cần phân biệt **same reference** với **same contents**. Cùng tham chiếu luôn biểu thị cùng object ngay ở thời điểm so sánh; hai object khác nhau vẫn có thể chứa nội dung tương đương.

### 1.1. Bảng chọn API

| API | Đối số | So sánh gì? | Dùng cho |
| --- | --- | --- | --- |
| `a == b` với object | Hai tham chiếu | Cùng object hay không | Kiểm tra identity, singleton, alias |
| `Objects.equals(a, b)` | Hai `Object` | Null-safe và `equals` thông thường | Object/value có hợp đồng `equals` phù hợp |
| `Objects.deepEquals(a, b)` | Hai `Object` | Nhận diện mảng và so sánh phần tử đệ quy khi phù hợp; ngoài mảng dùng `equals` | Mảng nguyên thủy, mảng nhiều chiều/hỗn hợp, có thể null |
| `Arrays.equals(int[], int[])` | Hai mảng nguyên thủy cùng kiểu | Từng phần tử ở một cấp | Mảng một chiều nguyên thủy |
| `Arrays.equals(Object[], Object[])` | Hai mảng tham chiếu | Từng phần tử theo `equals` thông thường, **không đi sâu** vào array con | Mảng một chiều không lồng mảng cần so sánh sâu |
| `Arrays.deepEquals(Object[], Object[])` | Hai `Object[]` | So sánh sâu array elements | Mảng lồng nhau có thể nhìn như `Object[]` |

`Arrays.equals` có nhiều overload theo loại phần tử. Trong bảng, chỉ xét hai dạng thường gặp. Không được nhầm “mảng chứa mảng nguyên thủy” với “mảng nguyên thủy một chiều”: `int[][]` **là `Object[]`** vì mỗi phần tử là một `int[]`, còn `int[]` **không phải `Object[]`**.

### 1.2. Quy tắc null-safe của `Objects.deepEquals`

`Objects.deepEquals(a, b)` trả:

- `true` nếu `a` và `b` chính là cùng tham chiếu, bao gồm trường hợp **cả hai là `null`**.
- `false` nếu chỉ một đối số là `null`.
- Nếu hai đối số khác `null`, dùng logic deep comparison của `Arrays` khi là mảng phù hợp; nếu không phải mảng tương ứng, việc so sánh còn phụ thuộc `equals` thông thường.

Không cần viết `if (a == null)` ở caller chỉ để tránh `NullPointerException` của `Objects.deepEquals`. Tuy nhiên, null-safe **không có nghĩa là so sánh đúng mọi object graph** — giới hạn này sẽ được bàn riêng.

## 2. Mảng hai chiều: khác tham chiếu nhưng bằng nhau sâu

Một mảng hai chiều như `int[][]` có thể hiểu là mảng chứa các tham chiếu `int[]`. Nếu sao chép nội dung sang các mảng con mới, `Arrays.equals` cấp ngoài sẽ so sánh các **tham chiếu mảng con** theo `equals` thông thường, nên có thể thất bại dù số nguyên giống nhau.

### Chương trình đầy đủ A — `NestedArraysDemo.java`

```java
import java.util.Arrays;
import java.util.Objects;

public final class NestedArraysDemo {
    public static void main(String[] args) {
        int[][] left = {{1, 2}, {3, 4}};
        int[][] right = {{1, 2}, {3, 4}};

        System.out.println("sameReference=" + (left == right));
        System.out.println("objectsEquals=" + Objects.equals(left, right));
        System.out.println("arraysEquals=" + Arrays.equals(left, right));
        System.out.println("objectsDeepEquals=" + Objects.deepEquals(left, right));
        System.out.println("arraysDeepEquals=" + Arrays.deepEquals(left, right));
        System.out.println("deepHashEqual="
                + (Arrays.deepHashCode(left) == Arrays.deepHashCode(right)));

        right[1][1] = 5;
        System.out.println("afterMutation=" + Objects.deepEquals(left, right));
        System.out.println("right=" + Arrays.deepToString(right));
    }
}
```

Lưu đúng tên tệp và chạy:

```bash
javac --release 17 -encoding UTF-8 NestedArraysDemo.java
java NestedArraysDemo
```

**Stdout chính xác:**

```text
sameReference=false
objectsEquals=false
arraysEquals=false
objectsDeepEquals=true
arraysDeepEquals=true
deepHashEqual=true
afterMutation=false
right=[[1, 2], [3, 5]]
```

### 2.1. Đọc kết quả từng bước

- `sameReference=false`: hai `int[][]` ngoài cùng được tạo tách biệt.
- `objectsEquals=false`: `Objects.equals` không đi sâu các mảng.
- `arraysEquals=false`: `Arrays.equals(Object[], Object[])` so sánh từng phần tử cấp ngoài, nhưng hai phần tử tương ứng là các `int[]` khác object, nên không coi bằng nhau.
- `objectsDeepEquals=true`: `Objects.deepEquals` đi qua các mảng con để so sánh từng số nguyên.
- `arraysDeepEquals=true`: `int[][]` có thể truyền cho `Arrays.deepEquals(Object[], Object[])`, nên API này cũng đi sâu đến mảng `int[]`.
- `deepHashEqual=true`: hai cấu trúc bằng nhau sâu tạo cùng giá trị `Arrays.deepHashCode` ở thời điểm đó.
- Sau `right[1][1] = 5`, một giá trị thay đổi làm `Objects.deepEquals(left, right)` chuyển thành `false`.
- `Arrays.deepToString(right)` hiển thị nội dung lồng nhau dễ đọc, không phải chuỗi identity dạng `[[I@...` thường thấy khi in mảng trực tiếp.

**Điểm cốt lõi:** Sự bằng nhau sâu là một **kết quả tại thời điểm so sánh**, không phải trạng thái vĩnh viễn hay quan hệ liên kết giữa hai mảng. Thay đổi một mảng sau đó làm kết quả so sánh có thể đổi ngay.

### 2.2. Tại sao `int[][]` dùng được với `Arrays.deepEquals` nhưng `int[]` không?

Về kiểu Java:

```java
int[][] matrix = {{1, 2}, {3, 4}};
Object[] outer = matrix; // HỢP LỆ: mỗi phần tử là một int[]
```

Nhưng:

```java
int[] numbers = {1, 2};
// Object[] wrong = numbers; // CỐ Ý SAI về kiểu
```

Hai đoạn là **minh họa**, không phải chương trình độc lập. `int[]` là một object nhưng không phải `Object[]`. Ngược lại, `int[][]` là mảng có phần tử `int[]` — một kiểu tham chiếu — nên có thể được nhìn như `Object[]`.

Vì `Arrays.deepEquals` chỉ nhận hai `Object[]`, bạn không thể gọi trực tiếp nó với hai `int[]`. Với `int[]`, dùng `Arrays.equals(int[], int[])` hoặc `Objects.deepEquals(Object, Object)` tùy nhu cầu.

## 3. Mảng hỗn hợp: Object[] chứa int[], long[], Object[] và null

Các ứng dụng có thể dùng cấu trúc dữ liệu lồng nhau không đồng nhất: một `Object[]` chứa một `int[]`, rồi một `Object[]` khác chứa cả `String` và `long[]`, sau đó có thể có phần tử `null`.

`Objects.deepEquals` xử lý được **mảng bên trong mảng** khi mảng con là mảng tham chiếu hoặc mảng nguyên thủy tương ứng. Bạn không cần tự ép từng leaf array ra một mảng cùng kiểu tại caller.

### Chương trình đầy đủ B — `MixedAndPrimitiveDemo.java`

```java
import java.util.Arrays;
import java.util.Objects;

public final class MixedAndPrimitiveDemo {
    public static void main(String[] args) {
        Object[] left = {
            new int[]{1, 2},
            new Object[]{"ready", new long[]{4L, 5L}},
            null
        };
        Object[] right = {
            new int[]{1, 2},
            new Object[]{"ready", new long[]{4L, 5L}},
            null
        };

        System.out.println("mixed=" + Objects.deepEquals(left, right));
        System.out.println("text=" + Arrays.deepToString(left));
        System.out.println("primitiveDeep="
                + Objects.deepEquals(new int[]{1, 2}, new int[]{1, 2}));
        System.out.println("primitiveShallow="
                + Objects.equals(new int[]{1, 2}, new int[]{1, 2}));
        System.out.println("differentPrimitiveType="
                + Objects.deepEquals(new int[]{1, 2}, new long[]{1L, 2L}));
        System.out.println("bothNull=" + Objects.deepEquals(null, null));
        System.out.println("oneNull=" + Objects.deepEquals(null, new int[]{1}));
        System.out.println("differentLength="
                + Objects.deepEquals(new int[]{1}, new int[]{1, 2}));
        System.out.println("sameReference="
                + Objects.deepEquals(left, left));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 MixedAndPrimitiveDemo.java
java MixedAndPrimitiveDemo
```

**Stdout chính xác:**

```text
mixed=true
text=[[1, 2], [ready, [4, 5]], null]
primitiveDeep=true
primitiveShallow=false
differentPrimitiveType=false
bothNull=true
oneNull=false
differentLength=false
sameReference=true
```

### 3.1. Vì sao `mixed=true`?

Hai mảng ngoài tương ứng từng vị trí:

1. Vị trí 0 là hai `int[]` có nội dung `1,2`; logic deep comparison dùng so sánh từng phần tử của `int[]`.
2. Vị trí 1 là hai `Object[]`. Chúng chứa chuỗi `"ready"`, được so theo `String.equals`, và hai `long[]`, được so theo nội dung.
3. Vị trí 2 là `null` ở cả hai bên; phần tử `null` tương ứng được xem là bằng nhau.
4. Độ dài và cấu trúc phù hợp, nên trả `true`.

Mặc dù `left` và `right` chứa các mảng con mới, chúng không cần là **cùng object** để bằng nhau sâu. Đây là giá trị thực tiễn của `deepEquals` trong kiểm thử matrix, parser output hoặc các cấu trúc array lồng nhau.

### 3.2. Mảng nguyên thủy không được “tự ép kiểu” khi so sâu

`Objects.deepEquals(new int[]{1,2}, new long[]{1L,2L})` trả `false`, dù các giá trị số trông giống nhau. `int[]` và `long[]` là **hai loại mảng nguyên thủy khác nhau**, và các overload so sánh từng loại không tự chuyển `int` thành `long`.

Tương tự, `byte[]` so với `short[]` không trở thành bằng nhau chỉ vì cùng biểu diễn một danh sách giá trị. Để coi chúng tương đương theo một quy tắc chuyển kiểu nghiệp vụ, bạn phải **chuẩn hóa dữ liệu** trước khi so sánh, không trông chờ `deepEquals` tự diễn dịch semantics.

### 3.3. `null` và chiều dài

- Hai tham chiếu cùng `null` → `true`.
- Một bên `null`, bên kia là mảng → `false`.
- Hai mảng có số phần tử khác nhau → `false`.
- Hai mảng rỗng cùng cấu trúc thích hợp có thể → `true` dù khác object.
- Hai mảng nhiều chiều có khác shape (ví dụ `{{1,2}}` và `{{1},{2}}`) → `false`.

Khi viết test parser, cần kiểm tra cả **shape**, không chỉ tổng số phần tử hoặc một vài giá trị biên.

## 4. Đường đi so sánh: deep nghĩa là “đi sâu vào mảng”, không phải mọi object

Một mô hình tư duy gần đúng và hữu ích của `Objects.deepEquals(a,b)` là:

```text
objectsDeepEquals(a, b):
    nếu a và b là cùng một tham chiếu -> true
    nếu một bên null -> false
    nếu a, b là các Object[] -> so các phần tử đệ quy
    nếu a, b là cùng loại mảng nguyên thủy -> Arrays.equals(đúng overload)
    trường hợp còn lại -> dùng phép equals thông thường của đối tượng
```

Đây là **mô hình giải thích**, không phải mã nguồn sao chép từ JDK. Những phép so sánh chuyên biệt cho mảng nguyên thủy gồm `boolean[]`, `byte[]`, `short[]`, `char[]`, `int[]`, `long[]`, `float[]` và `double[]`.

Có ba giới hạn nổi bật:

1. Nếu phần tử **là mảng**, thuật toán có thể đi sâu tiếp.
2. Nếu phần tử **không phải mảng**, thuật toán dùng `equals` hiện có của object — không tự phản chiếu mọi field bên trong để so sánh.
3. Nếu cấu trúc chứa **chu trình tham chiếu mảng** (array trỏ trực tiếp/gián tiếp về chính nó), `Arrays.deepEquals` không định nghĩa hành vi hữu ích tổng quát; không dùng `deepEquals` tùy tiện cho object graph có chu trình.

**Điểm thường gây nhầm:** Java `List` không phải mảng. Một `List` có thể chứa mảng, nhưng gọi `Objects.deepEquals(listA, listB)` không tự bước vào từng mảng nằm trong list bằng quy tắc `Arrays.deepEquals`. Nó dựa trên `List.equals`, và các mảng làm phần tử vẫn có ngữ nghĩa identity thông thường.

## 5. Giới hạn với List, Map và mảng làm key

### Chương trình đầy đủ C — `CollectionBoundaryDemo.java`

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class CollectionBoundaryDemo {
    public static void main(String[] args) {
        List<int[]> left = List.of(new int[]{1, 2});
        List<int[]> right = List.of(new int[]{1, 2});
        System.out.println("listOfArrays=" + Objects.deepEquals(left, right));
        System.out.println("arrayOfArrays="
                + Objects.deepEquals(
                    new Object[]{new int[]{1, 2}},
                    new Object[]{new int[]{1, 2}}));

        List<List<Integer>> a = List.of(List.of(1, 2));
        List<List<Integer>> b = List.of(List.of(1, 2));
        System.out.println("listOfLists=" + Objects.deepEquals(a, b));

        Map<String, int[]> mapA = Map.of("scores", new int[]{1, 2});
        Map<String, int[]> mapB = Map.of("scores", new int[]{1, 2});
        System.out.println("mapWithArrayValue=" + Objects.deepEquals(mapA, mapB));

        Map<int[], String> byArray = new HashMap<>();
        byArray.put(new int[]{1, 2}, "value");
        System.out.println("arrayAsKeyLookup=" + byArray.get(new int[]{1, 2}));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CollectionBoundaryDemo.java
java CollectionBoundaryDemo
```

Output:

```text
listOfArrays=false
arrayOfArrays=true
listOfLists=true
mapWithArrayValue=false
arrayAsKeyLookup=null
```

### 5.1. Vì sao list chứa mảng không bằng nhau sâu?

`List<int[]> left` và `right` là hai list, mỗi list có một mảng `int[]` được tạo riêng. `Objects.deepEquals(left,right)` không thấy đối số top-level là array nên sử dụng `List.equals`. `List.equals` so sánh element theo `equals` của chúng; hai mảng `int[]` khác tham chiếu, nên `false`.

Chuyển top-level sang `Object[]{new int[]{...}}` trong thí nghiệm `arrayOfArrays` dẫn đến `true` vì lúc này **ngữ nghĩa deep array** được kích hoạt.

**Không kết luận** tất cả list lồng nhau đều so sánh bằng identity. Với `List<List<Integer>>`, list con có `equals` theo phần tử, nên hai list có số nguyên giống nhau trả `true` mà không cần `Objects.deepEquals` đặc biệt. Kết quả phụ thuộc hợp đồng `equals` của **loại phần tử**.

### 5.2. Vì sao Map có giá trị array cho false?

Hai `Map<String,int[]>` đều có key `"scores"` nhưng value là hai mảng `int[]` khác nhau. `Map.equals` so sánh cặp key/value theo hợp đồng map; mảng value không tự có content equality, nên `false`. `Objects.deepEquals(mapA,mapB)` không thay đổi điều đó.

Nếu yêu cầu **deep equality cho Map chứa array**, có thể:

- Chuẩn hóa value thành một value type có `equals`/`hashCode` phù hợp.
- Chuyển value array thành `List<Integer>` bất biến theo nghiệp vụ **nếu** đổi representation là phù hợp và được thiết kế có chủ đích.
- Viết một comparator chuyên biệt kiểm tra key set và dùng `Objects.deepEquals` cho **từng value là mảng**.
- Chọn một mô hình dữ liệu domain có định nghĩa equality nhất quán; không “ép” `Objects.deepEquals` làm một công cụ deep object graph tổng quát.

### 5.3. Vì sao dùng array làm HashMap key dễ gây lỗi?

`HashMap`/`HashSet` dùng `equals` và `hashCode` của **key object**. Array mặc định dùng identity semantics, nên key tạo bởi `new int[]{1,2}` **không** được tìm thấy chỉ bằng một mảng mới cùng nội dung. Dòng `arrayAsKeyLookup=null` minh họa chính xác.

Dù `Objects.deepEquals(new int[]{1,2},new int[]{1,2})` trả `true`, điều đó **không sửa** hợp đồng `equals/hashCode` của array trong `HashMap`. Nếu cần key theo nội dung, dùng value object bất biến có `equals`/`hashCode` đúng, hoặc mô hình key khác do ứng dụng định nghĩa.

**Tránh thiết kế** một key mutable mà `hashCode` của nó thay đổi sau khi thêm vào hash collection. Đây là lỗi riêng của tính ổn định hash key và cần được cân nhắc khi chuyển array sang wrapper.

## 6. Trường hợp biên: khác shape, null bên trong, kiểu thành phần

Không phải sự khác nhau nào của hai array cũng làm `deepEquals` trả false. Với **hai object arrays** có phần tử tương ứng bằng nhau, **runtime component class** của hai mảng ngoài có thể khác nhau mà nội dung vẫn bằng nhau sâu, vì việc so sánh tập trung vào phần tử.

### Chương trình đầy đủ D — `DeepEqualsEdgeDemo.java`

```java
import java.util.Arrays;
import java.util.Objects;

public final class DeepEqualsEdgeDemo {
    public static void main(String[] args) {
        System.out.println("empty=" +
                Objects.deepEquals(new Object[0], new Object[0]));
        System.out.println("nestedNull=" +
                Objects.deepEquals(new Object[]{null, new int[]{2}},
                                   new Object[]{null, new int[]{2}}));
        System.out.println("shape=" +
                Objects.deepEquals(new int[][]{{1, 2}},
                                   new int[][]{{1}, {2}}));
        System.out.println("componentTypes=" +
                Objects.deepEquals(new Object[]{"x"}, new String[]{"x"}));
        Object[] same = {new int[]{4}};
        System.out.println("self=" + Objects.deepEquals(same, same));
        System.out.println("nestedHash=" +
                (Arrays.deepHashCode(new Object[]{new int[]{4}})
                 == Arrays.deepHashCode(new Object[]{new int[]{4}})));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DeepEqualsEdgeDemo.java
java DeepEqualsEdgeDemo
```

Output:

```text
empty=true
nestedNull=true
shape=false
componentTypes=true
self=true
nestedHash=true
```

### 6.1. Giải thích các ca

- `empty=true`: hai mảng đối tượng rỗng khác nhau vẫn bằng nhau sâu vì không có phần tử khác nhau.
- `nestedNull=true`: vị trí chứa `null` ở cả hai mảng được coi là bằng nhau; phần tử `int[]` còn lại có nội dung tương ứng.
- `shape=false`: một mảng ngoài dài 1 với hàng `{1,2}` không bằng mảng ngoài dài 2 với hàng `{1}` và `{2}`. Tổng số phần tử là 2 không làm shape bằng nhau.
- `componentTypes=true`: `new Object[]{"x"}` và `new String[]{"x"}` là hai **mảng tham chiếu**, phần tử tương ứng đều là chuỗi `"x"`; so sánh sâu chấp nhận chúng dù array component type ngoài cùng khác nhau. Vì vậy không nên mô tả `deepEquals` là “so sánh array class chính xác trước rồi mới so phần tử”.
- `self=true`: cùng một object được so với chính nó. Đây là phép so sánh cùng tham chiếu; không có yêu cầu đi sâu vào từng phần tử để chứng minh điều gì.
- `nestedHash=true`: cấu trúc chứa một `int[]` với cùng nội dung có giá trị deep hash giống nhau.

### 6.2. So sánh theo shape không phải phép so sánh tập hợp

Nếu dữ liệu dạng matrix, hai ma trận có thể có cùng tổng, cùng tập giá trị nhưng thứ tự/shape khác nhau; `deepEquals` vẫn trả `false`. Nó so sánh **vị trí tương ứng**, không tự sắp xếp, chuẩn hóa hoặc coi array là multiset.

Ví dụ:

```java
Objects.deepEquals(new int[]{1, 2}, new int[]{2, 1}) // false
```

Đây là biểu thức minh họa; nếu nghiệp vụ coi hai tập phần tử không thứ tự là tương đương, cần chọn biểu diễn/thuật toán khác. Không làm thay đổi dữ liệu gốc bằng cách sort in-place nếu caller còn phụ thuộc thứ tự ban đầu.

## 7. Mảng số thực: NaN và dấu của số không

Khi array chứa `float` hoặc `double`, quy tắc so sánh của `Arrays.equals` đối với primitive floating arrays có một số chi tiết **khác với việc dùng toán tử `==` từng phần tử bằng tay**:

- Các giá trị `NaN` được xem là tương đương theo quy tắc nội dung của mảng floating type, kể cả vì `Double.NaN == Double.NaN` ở mức toán tử số là `false`.
- `+0.0` và `-0.0` được **phân biệt** trong phép so sánh mảng floating type, dù `+0.0 == -0.0` theo toán tử số là `true`.
- Quy tắc này gắn với cách `Arrays.equals` xác định equality cho `float[]`/`double[]`. `Objects.deepEquals` khi gặp các mảng nguyên thủy đó đi theo cùng semantics.

### Chương trình đầy đủ E — `FloatingAndHashDemo.java`

```java
import java.util.Arrays;
import java.util.Objects;

public final class FloatingAndHashDemo {
    public static void main(String[] args) {
        double[] a = {Double.NaN, +0.0d};
        double[] b = {Double.NaN, +0.0d};
        double[] c = {Double.NaN, -0.0d};

        System.out.println("nanAndSameZero=" + Objects.deepEquals(a, b));
        System.out.println("nanAndDifferentZero=" + Objects.deepEquals(a, c));

        Object[] left = {new int[]{2, 3}, new String[]{"ok"}};
        Object[] right = {new int[]{2, 3}, new String[]{"ok"}};
        System.out.println("deepEquals=" + Objects.deepEquals(left, right));
        System.out.println("deepHashMatch="
                + (Arrays.deepHashCode(left) == Arrays.deepHashCode(right)));
        System.out.println("shallowEquals=" + Arrays.equals(left, right));
        System.out.println("deepToString=" + Arrays.deepToString(left));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FloatingAndHashDemo.java
java FloatingAndHashDemo
```

Output:

```text
nanAndSameZero=true
nanAndDifferentZero=false
deepEquals=true
deepHashMatch=true
shallowEquals=false
deepToString=[[2, 3], [ok]]
```

**Ứng dụng:** Nếu một hệ thống dùng dữ liệu scientific computing hoặc đo lường và có quy tắc nghiệp vụ riêng về tolerance của `double`, `Objects.deepEquals` là phép so **chính xác theo semantics mảng của Java**, không phải phép so xấp xỉ. Muốn chấp nhận hai số sai lệch không quá một ngưỡng thì cần comparator có tolerance, chú ý `NaN`/vô cực và các yêu cầu số học đặc thù.

## 8. deep equality và hash code

Hai khái niệm thường đi cùng nhau trong `equals/hashCode` của Java. Với **hai `Object[]` không chứa chu trình** bằng nhau theo `Arrays.deepEquals`, `Arrays.deepHashCode` cung cấp hàm hash tương thích về nguyên tắc: các cấu trúc bằng nhau sâu sẽ có deep hash bằng nhau.

```java
Object[] a = {new int[]{1, 2}, new String[]{"ok"}};
Object[] b = {new int[]{1, 2}, new String[]{"ok"}};

boolean same = Objects.deepEquals(a, b); // true
boolean sameHash = Arrays.deepHashCode(a) == Arrays.deepHashCode(b); // true
```

Đây là đoạn minh họa cần import `java.util.Arrays` và `java.util.Objects`, được kiểm tra bằng các chương trình ở trên.

### 8.1. Những điều không được suy ra từ hash

- **Deep hash bằng nhau không chứng minh hai cấu trúc bằng nhau sâu**, vì hash có thể va chạm (collision).
- `Arrays.deepHashCode(Object[])` chỉ nhận `Object[]` ở cấp ngoài. Với `int[]` một chiều dùng `Arrays.hashCode(int[])`; với `int[][]` có thể dùng `Arrays.deepHashCode(int[][])` vì `int[][]` là `Object[]`.
- `Objects.hashCode(a)` cho một array không tự chuyển thành deep hash. Nó gọi hợp đồng `hashCode` của object, và mảng mặc định không có content hashing.
- `Objects.hash(a)` cũng không phải cơ chế deep hash tổng quát cho mọi cấp array; đừng chọn chỉ vì có từ “Objects” trong tên.
- **HashMap vẫn dùng `key.equals` và `key.hashCode` theo hợp đồng của chính key.** Việc gọi `Objects.deepEquals` ở một nơi khác không làm cho array trở thành content-key.
- Nếu tự định nghĩa một value wrapper coi array fields bằng nhau sâu, cần định nghĩa cả `equals` và `hashCode` nhất quán, bảo vệ dữ liệu khỏi thay đổi sau khi đưa làm key nếu key có tính mutable.

### 8.2. Khi nào cần `Arrays.deepToString`?

`System.out.println(matrix)` thường in kiểu/tọa độ identity cho array, không hiển thị cấu trúc nội dung. Với mảng lồng nhau là `Object[]` ở cấp ngoài, `Arrays.deepToString(matrix)` cung cấp dạng chuỗi dễ quan sát. Nhưng đây là **công cụ hiển thị/chẩn đoán**, không phải định nghĩa equality và không nên dùng kết quả chuỗi làm phép so nội dung trong production.

Không nên dùng `Arrays.deepToString(a).equals(Arrays.deepToString(b))` để thay `deepEquals`: biểu diễn text là dành cho đọc/log, có thể không duy nhất hoặc bị ảnh hưởng bởi `toString` của object con. So sánh **giá trị/kiểu** bằng API có hợp đồng đúng sẽ rõ hơn.

## 9. Các giới hạn thiết kế cần nhận diện

### 9.1. Không xử lý mọi đồ thị đối tượng

Giả sử một `record` hay lớp POJO chứa `int[]`. `Objects.deepEquals(recordA,recordB)` không tự mở field để so mảng: nó dùng hợp đồng `equals` của loại object. Nếu `equals` của loại ấy chỉ so array theo identity, deepEquals ở cấp object vẫn trả `false` khi hai field array được tạo riêng.

Nếu muốn **value equality cho domain object có array field**, hãy định nghĩa rõ cách so trong `equals` và `hashCode` của domain type. Có thể cần dùng `Arrays.equals` hoặc `Objects.deepEquals` ngay ở **field**, chứ không gọi một lần `Objects.deepEquals` cho cả object và mong tự suy luận toàn bộ cây.

### 9.2. Cấu trúc có chu trình (cyclic arrays)

Mảng `Object[]` có thể chứa chính nó hoặc chứa mảng khác trỏ ngược về nó:

```java
Object[] cyclic = new Object[1];
cyclic[0] = cyclic;
```

Đây là **mảnh minh họa**, không phải chương trình độc lập. Đặc tả `Arrays.deepEquals` nêu rằng hành vi không được xác định cho array chứa chính nó trực tiếp hoặc gián tiếp thông qua các array khác. So sánh hai cấu trúc cyclic khác nhau có thể gây recursion không kết thúc hữu ích/`StackOverflowError` trên implementation cụ thể.

**Không dùng `Objects.deepEquals` như một graph-isomorphism algorithm** hoặc tin rằng nó phát hiện và xử lý chu trình trong mọi trường hợp. Nếu dữ liệu có chu trình, thiết kế bộ so sánh có **visited identity pairs** và quy tắc tương đương miền nghiệp vụ riêng.

### 9.3. Mảng lớn hoặc lồng quá sâu

Độ phức tạp phụ thuộc số phần tử phải xét và chi phí `equals` trên các leaf object. Với cấu trúc lớn, chi phí có thể đáng kể; mảng lồng rất sâu cũng gây tải đệ quy. Không mặc định rằng `deepEquals` luôn rẻ vì lời gọi chỉ có một dòng.

Đừng dùng microbenchmark không warm-up để kết luận hiệu năng. Khi performance ảnh hưởng thực tế, benchmark trên cấu trúc, kích thước và cách sử dụng của ứng dụng; cân nhắc short-circuit và những đặc điểm của dữ liệu. Thêm caching/hash tùy ý có thể sai nếu mảng mutable.

### 9.4. Mutability và concurrent modification

Mảng là mutable. `Objects.deepEquals` kiểm tra các giá trị đọc được trong quá trình so sánh, **không tạo snapshot nhất quán** và không tự đồng bộ hóa các thread. Nếu thread khác thay đổi phần tử trong khi đang so, kết quả có thể không ổn định hoặc không phản ánh một snapshot nghiệp vụ mong muốn.

Đối với dữ liệu cần so nhất quán, thiết kế ownership, đồng bộ hóa, immutable snapshots hoặc defensive copy phù hợp. **Không** coi `deepEquals` là giải pháp concurrency.

### 9.5. Không phải deep copy

Bằng nhau sâu **không** đồng nghĩa hai cấu trúc độc lập hoàn toàn, và cũng không có tác dụng clone. Hai mảng có thể dùng chung array con hoặc cùng tham chiếu leaf object; `Objects.deepEquals` vẫn chỉ trả một giá trị boolean. Nếu cần copy cấu trúc dữ liệu để ngăn mutation, phải thực hiện clone/copy riêng với độ sâu phù hợp.

## 10. Lựa chọn hàm theo tình huống

| Dữ liệu cần so | API thường phù hợp | Lý do |
| --- | --- | --- |
| `int[]` một chiều | `Arrays.equals(int[], int[])` hoặc `Objects.deepEquals` | So số nguyên theo phần tử |
| `int[][]` | `Arrays.deepEquals(int[][], int[][])` hoặc `Objects.deepEquals` | So từng mảng con |
| `String[]` một chiều | `Arrays.equals(String[], String[])` hoặc `Objects.deepEquals` | So `String.equals` từng vị trí |
| `Object[]` có `int[]`, `long[]`, `Object[]` lồng nhau | `Objects.deepEquals` hoặc `Arrays.deepEquals` | So cả primitive arrays và object arrays |
| Hai object có thể `null` hoặc không chắc có phải array | `Objects.deepEquals` khi mong muốn xử lý array đặc biệt | Null-safe, fallback sang `equals` của non-array |
| Hai `List<Integer>` | `List.equals`/`Objects.equals` | List có value equality theo phần tử |
| Hai `List<int[]>` | Comparator domain riêng | `List.equals` không deep compare array elements |
| Hai `Map<String,int[]>` | Comparator domain riêng / value type phù hợp | `Map.equals` không deep compare array values |
| Array làm `Map` key | Không khuyến nghị khi muốn content-key | Array key mặc định identity semantics |
| Cấu trúc array có chu trình | Comparator có theo dõi chu trình | `Arrays.deepEquals` không có contract tổng quát cho chu trình |
| Mảng `double[]` cần tolerance | Bộ so sánh số học riêng | `deepEquals` là so exact theo quy tắc `Arrays.equals` |

### 10.1. Quy trình quyết định ngắn

1. **Hai biến có phải array không?** Nếu không, hiểu `equals` của loại object trước.
2. **Array một chiều hay lồng nhau?** Một chiều nguyên thủy dùng `Arrays.equals` rõ ràng; lồng nhau xem `Objects.deepEquals` hoặc `Arrays.deepEquals` nếu top-level là `Object[]`.
3. **Có primitive array ở bất kỳ tầng nào không?** Các overload cho primitive được sử dụng trong deep comparison; không tự đổi kiểu phần tử.
4. **Có array nằm trong List/Map/record không?** Không mặc định recursive equality vượt qua ranh giới non-array object.
5. **Có chu trình, mutation concurrent hay giới hạn thời gian không?** Xác định thuật toán/ownership riêng.
6. **Có cần equals/hashCode của domain key không?** Đảm bảo hai hợp đồng nhất quán, không lấy `deepEquals` ngoài object để thay thế chúng.

## 11. Bộ kiểm thử tối thiểu nên có

Khi sử dụng `Objects.deepEquals` để đối chiếu output của parser, bảng dữ liệu, ma trận hoặc một API trả về mảng lồng nhau, nên viết test ít nhất cho những ca sau:

| Ca | A | B | Kỳ vọng |
| --- | --- | --- | --- |
| Cùng tham chiếu | `int[][] x` | `x` | `true` |
| Hai mảng con riêng có cùng dữ liệu | `{{1,2},{3,4}}` | `{{1,2},{3,4}}` | `true` |
| Thay một phần tử | `{{1,2}}` | `{{1,9}}` | `false` |
| Khác chiều dài | `{1}` | `{1,2}` | `false` |
| Khác shape | `{{1,2}}` | `{{1},{2}}` | `false` |
| Hai null | `null` | `null` | `true` |
| Một null | `null` | `new int[]{1}` | `false` |
| Mảng nguyên thủy khác loại | `new int[]{1}` | `new long[]{1L}` | `false` |
| Mảng hỗn hợp có null | `Object[]{int[], null}` | Có nội dung tương ứng | `true` |
| List chứa mảng được tạo riêng | `List<int[]>` | `List<int[]>` cùng số | `false` với `Objects.deepEquals` |
| Floating NaN | `double[]{NaN}` | `double[]{NaN}` | `true` |
| Dấu của số không | `double[]{+0.0}` | `double[]{-0.0}` | `false` |

Nếu thư viện test tự động không có sẵn, có thể viết helper `require(boolean condition, String label)` ném `AssertionError` khi điều kiện sai. Với JUnit, `assertArrayEquals` cũng có các overload phù hợp cho mảng; nhưng nên đọc chính xác contract của assertion đang dùng và kiểu dữ liệu lồng nhau. Đừng nhầm một assertion chỉ so mảng một chiều với phép so sâu cho mọi cấu trúc.

### 11.1. Kiểm thử âm tại compile-time: `Arrays.deepEquals` không nhận `int[]` trực tiếp

Lưu vào `BadDeepEquals.java` (file **cố ý không biên dịch**):

```java
import java.util.Arrays;

public final class BadDeepEquals {
    public static void main(String[] args) {
        int[] a = {1, 2};
        int[] b = {1, 2};
        System.out.println(Arrays.deepEquals(a, b));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BadDeepEquals.java
```

Kỳ vọng: **FAIL**, vì method `Arrays.deepEquals` yêu cầu `Object[]` ở cấp ngoài, không nhận một `int[]` một chiều. Đây là **lỗi compile-time**, không phải kết quả `false` của một phép so runtime. Sửa bằng:

```java
System.out.println(Arrays.equals(a, b));  // true
// Hoặc:
System.out.println(Objects.deepEquals(a, b)); // true
```

Hai dòng sửa là **mảnh minh họa** cần import `java.util.Arrays` và `java.util.Objects`, đặt trong cùng scope đã khai báo `a`, `b`.

### 11.2. Test về contract khi mảng đã bị thay đổi

Bắt đầu từ hai ma trận giống nhau, kiểm tra `true`. Thay một phần tử ở một phía, kiểm tra `false`. Thay trở lại giá trị cũ, kiểm tra `true`. Điều này xác nhận so sánh dựa trên **nội dung ở thời điểm chạy**, chứ không tạo snapshot hoặc cache kết quả.

### 11.3. Kiểm tra kết quả hash đúng cách

Nếu bạn dùng `Arrays.deepHashCode(Object[])` để tạo một giá trị hash ở cấu trúc hợp lệ:

- Với hai mảng bằng nhau sâu, kiểm tra hash bằng nhau.
- **Không** dùng việc hash bằng nhau làm điều kiện xác nhận `deepEquals` vì collision có thể xảy ra.
- Nếu cấu trúc mutable, hash có thể đổi theo nội dung; không sử dụng nó như key hash cố định khi dữ liệu còn được sửa.
- Không thay `Arrays.deepHashCode` bằng `Objects.hashCode` nếu cần deep hashing của array.

## 12. Lỗi thường gặp và cách sửa

### 12.1. So sánh hai ma trận bằng `Objects.equals`

Vấn đề: hai `int[][]` mới có cùng nội dung nhưng `Objects.equals` trả `false` vì array identity semantics.

Cách sửa: dùng `Objects.deepEquals(a,b)` hoặc `Arrays.deepEquals(a,b)` với kiểu phù hợp.

### 12.2. Dùng `Arrays.equals` cho ma trận lồng nhau

Vấn đề: overload `Arrays.equals(Object[],Object[])` so phần tử cấp ngoài bằng `equals` thông thường; hai `int[]` con riêng biệt không bằng nhau.

Cách sửa: nếu muốn so nội dung con, dùng `Arrays.deepEquals`/`Objects.deepEquals`.

### 12.3. Cố ép `int[]` sang `Object[]`

Vấn đề: `int[]` không phải `Object[]`; không giải quyết bằng cast ép buộc.

Cách sửa: gọi overload `Arrays.equals(int[], int[])` hoặc dùng `Objects.deepEquals` trực tiếp.

### 12.4. Nghĩ rằng deepEquals so sâu cả List/Map

Vấn đề: với non-array object, cơ chế dùng `equals` của loại đó. `List<int[]>` và `Map<String,int[]>` có thể không bằng nhau theo nội dung mảng.

Cách sửa: thiết kế comparator riêng hoặc chuyển dữ liệu sang value types có equality đúng.

### 12.5. Dùng array làm HashMap key theo nội dung

Vấn đề: HashMap không chuyển sang `Objects.deepEquals`; nó dùng `equals/hashCode` mặc định của array.

Cách sửa: dùng immutable value key hoặc wrapper có `equals/hashCode` nhất quán.

### 12.6. Dùng hash bằng nhau làm kiểm tra cuối cùng

Vấn đề: hash collision có thể xảy ra; đây chỉ là dấu hiệu phù hợp, không phải chứng minh equality.

Cách sửa: dùng `Objects.deepEquals` khi cần kết quả so sánh, dùng hash như công cụ hỗ trợ theo đúng contract.

### 12.7. Dùng `deepToString` để so sánh

Vấn đề: đây là hàm biểu diễn dành cho chẩn đoán, không mang hợp đồng equality. Chuỗi có thể không đủ phân biệt các object khác nhau.

Cách sửa: dùng hàm equality thích hợp.

### 12.8. Nghĩ rằng `deepEquals` kiểm tra set/multiset

Vấn đề: array giữ **thứ tự và shape**. `{1,2}` khác `{2,1}`; `{{1,2}}` khác `{{1},{2}}`.

Cách sửa: nếu bài toán không xét thứ tự, định nghĩa quy tắc chuẩn hóa riêng.

### 12.9. Không xét chu trình trong input

Vấn đề: array có thể trỏ về chính nó. `Arrays.deepEquals` không bảo đảm hành vi xác định cho cấu trúc cyclic.

Cách sửa: tránh dùng nó cho cyclic graph; dùng comparator có visited-pair policy khi thật sự cần.

### 12.10. Cho rằng kết quả bằng nhau sẽ không thay đổi

Vấn đề: mảng mutable; kết quả `deepEquals` có thể thay sau một phép gán hoặc do thread khác thay đổi trong lúc so.

Cách sửa: quản lý ownership/đồng bộ hoặc so trên snapshot immutable khi cần nhất quán.

### 12.11. Dùng `deepEquals` làm phép so xấp xỉ cho `double`

Vấn đề: API không có tham số epsilon; và có quy tắc riêng về `NaN`, `+0.0` và `-0.0`.

Cách sửa: nếu nghiệp vụ cho phép sai số, dùng comparator chuyên biệt đã xác định NaN/infinity/tolerance.

## 13. Bài tập thực hành

**Bài 1 — Phân tích không chạy:** Cho `int[][] a={{1,2},{3,4}}` và `b` có cùng phần tử nhưng được tạo riêng. Dự đoán `a==b`, `Objects.equals(a,b)`, `Arrays.equals(a,b)`, `Objects.deepEquals(a,b)` và giải thích cấp nào được so.

**Bài 2 — Viết test matrix:** Tạo hai ma trận `String[][]` có hàng dài ngắn khác nhau nhưng cùng cấu trúc và nội dung. Kiểm tra `true`; sửa một chuỗi trong một hàng, kiểm tra `false`.

**Bài 3 — Trộn primitive arrays:** Viết hai `Object[]` chứa `byte[]`, `double[]` và một `Object[]` có `null` bên trong. Dùng `deepEquals` và `deepToString`; sau đó đổi một leaf `byte`.

**Bài 4 — Shape:** So sánh `int[][]{{1,2}}` và `int[][]{{1},{2}}`. Hai bên cùng tổng số phần tử, tại sao `deepEquals` trả `false`?

**Bài 5 — List chứa array:** Chứng minh `Objects.deepEquals(List.of(new int[]{1}), List.of(new int[]{1}))` cho kết quả khác so sánh `new Object[]{new int[]{1}}` ở hai bên. Đề xuất một comparator phù hợp cho `List<int[]>`.

**Bài 6 — Map key:** Thêm `new int[]{1,2}` vào `HashMap<int[],String>` làm key, tra cứu bằng một mảng mới giống nội dung. Vì sao không tìm thấy? Nếu muốn content-key, hãy đề xuất value object bất biến.

**Bài 7 — Hash:** Với hai `Object[]` chứa các mảng con giống nhau, kiểm tra `Arrays.deepHashCode` bằng nhau. Vì sao không được dùng `hashA==hashB` thay cho `Objects.deepEquals(a,b)`?

**Bài 8 — Floating edge:** Dự đoán kết quả khi so `double[]{Double.NaN,+0.0}` với bản giống hệt, rồi với `double[]{Double.NaN,-0.0}`. Vì sao dùng `==` với mỗi leaf có thể cho một semantics khác?

**Bài 9 — Chu trình:** Tạo một `Object[]` tự tham chiếu để nhận diện nguy cơ, nhưng **không chạy so sánh sâu hai chu trình khác nhau** trong chương trình production. Viết giả mã comparator có tập cặp tham chiếu đã thăm và xác định tiêu chuẩn tương đương cần thiết.

**Bài 10 — API review:** Một phương thức public nhận `Object payload` từ người dùng và gọi `Objects.deepEquals(payload, expected)`. Liệt kê câu hỏi về kiểu dữ liệu, mutability, giới hạn kích thước, chu trình và hợp đồng `equals` của non-array leaves trước khi coi so sánh ấy là đủ.

### Checklist khi sử dụng trong code thật

- [ ] Đã xác định dữ liệu có thật sự là mảng lồng nhau, không phải List/Map hoặc POJO.
- [ ] Đã chọn `Objects.deepEquals` hay `Arrays.deepEquals` đúng với kiểu top-level.
- [ ] Đã hiểu `int[][]` là `Object[]` nhưng `int[]` không phải `Object[]`.
- [ ] Có test cho null, rỗng, khác shape, khác leaf value, khác primitive type.
- [ ] Có test cho `String[]` và các object leaf có `equals` riêng.
- [ ] Không mặc định deep comparison tự xử lý các collection chứa array.
- [ ] Không dùng array làm key theo nội dung nếu chưa có wrapper với equals/hashCode phù hợp.
- [ ] Không suy rằng hash bằng nhau là bằng nhau sâu.
- [ ] Không dùng `deepToString` như comparator.
- [ ] Có chính sách cho dữ liệu cyclic, quá sâu/quá lớn hoặc bị mutate đồng thời.
- [ ] Không thay thế deep comparison bằng “so string” hay một phép cast không hợp lệ.
- [ ] Đã chạy ví dụ trên JDK được hỗ trợ và kiểm tra stdout.

## Tài liệu chính thức vẫn áp dụng

- [Java SE 17 — `java.util.Objects` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `deepEquals(Object,Object)`, `equals` và null semantics.
- [Java SE 17 — `java.util.Arrays` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `deepEquals(Object[],Object[])`, các overload `equals`/`hashCode`, `deepHashCode` và `deepToString`; chú ý lưu ý về mảng chứa chu trình.
- [Java Language Specification 17 — Arrays, Chapter 10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html): loại mảng, mảng nhiều chiều và quan hệ giữa mảng nguyên thủy với mảng tham chiếu.
- [Java Language Specification 17 — `4.3 Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): mảng là kiểu tham chiếu, ý nghĩa của giá trị tham chiếu.
- [Java SE 17 — `java.util.List` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): hợp đồng `List.equals` để hiểu vì sao `List<int[]>` không được deep compare như array.
- [Java SE 17 — `java.util.Map` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `Map.equals` và hợp đồng key/value.

**Tóm lại:** `Objects.deepEquals` là lựa chọn tốt khi bạn muốn **so sánh nội dung của mảng lồng nhau**, kể cả mảng chứa primitive arrays và `null`. Nó không biến Java thành ngôn ngữ có deep equality mặc định cho mọi List, Map hoặc object graph. Luôn xác định ranh giới array, phân biệt equality với hashing và chú ý đến shape, mutation, chu trình cùng hợp đồng kiểu dữ liệu trước khi áp dụng.