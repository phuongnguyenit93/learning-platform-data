# Sao chép sâu và phạm vi dữ liệu cần sao chép trong Java

**Sao chép sâu (deep copy)** là thao tác tạo một bản biểu diễn mới của trạng thái đối tượng sao cho những **thành phần có thể thay đổi cần được tách độc lập** không còn bị chia sẻ ngoài ý muốn giữa bản gốc và bản sao. Trong Java, câu hỏi khó không phải chỉ là “dùng `clone()` hay constructor?”, mà là:

> **Phạm vi dữ liệu nào thuộc snapshot? Thành phần nào cần tạo bản sao độc lập, thành phần nào nên giữ nguyên identity hoặc chia sẻ an toàn?**

Xét một `Order` gồm danh sách `OrderLine`, thông tin khách hàng, một tham chiếu đến `ProductCatalog` và `PaymentGateway`:

- Các dòng hàng đang được phép sửa số lượng: thường **cần copy** nếu tạo một bản nháp order độc lập.
- Mã sản phẩm và chuỗi tên sản phẩm bất biến: có thể **chia sẻ**.
- Tham chiếu đến `ProductCatalog` là dịch vụ tra cứu: thường **không thuộc payload snapshot**.
- `PaymentGateway` có connection/resource: **không deep copy** như dữ liệu.
- Nếu hai dòng cùng trỏ một object mutable `DiscountRule`, cần quyết định bản sao giữ **một alias dùng chung bên trong** hay tạo các rules độc lập.
- Nếu hai objects tham chiếu ngược nhau, thuật toán copy phải xử lý **cycle**, không đệ quy vô hạn.

Bài học này thuộc phần **Sao chép đối tượng** của Java Core, dùng **Java 17+**. Nội dung bao gồm mô hình object graph, xác định boundary/ownership, shallow copy và deep copy, giữ alias/cycle, cách copy array/collection/custom class/record, copy constructor/factory/`clone`, tài nguyên/identity, snapshot dưới concurrency, test kết quả, lỗi phổ biến và chương trình biên dịch/chạy được với stdout được xác định.

## 1. Copy object có nghĩa gì?

Giả sử:

```java
class Note {
    String text;
    Note(String text) { this.text = text; }
}

Note original = new Note("Java");
Note alias = original;
```

Lệnh `Note alias = original;` **không sao chép object**: cả hai biến trỏ đến cùng một instance.

```java
System.out.println(original == alias); // true
```

Nếu làm:

```java
Note copy = new Note(original.text);
```

ta tạo instance mới với trạng thái `text` ban đầu tương đương. Vì `String` immutable, hai Note có thể chia sẻ String reference mà trạng thái text không bị một bên sửa trực tiếp.

Nhưng khi fields chứa mutable objects, một thao tác copy chỉ các field references chưa đủ để tách trạng thái.

### Định nghĩa thực dụng

- **Reference assignment:** không tạo object bản sao; cùng identity.
- **Shallow copy:** tạo outer object mới, copy các giá trị primitive và references tới các objects con.
- **Deep copy:** tạo outer object mới và copy những mutable descendants **thuộc phạm vi dữ liệu cần độc lập**; có thể chia sẻ immutable values hoặc dependencies ngoài phạm vi.
- **Snapshot:** biểu diễn trạng thái tại một thời điểm logic; có thể immutable hoặc mutable, shallow hoặc deep tùy contract.
- **Immutable:** trạng thái quan sát được không đổi sau construction; **không đồng nghĩa** với việc đã từng được deep copy.

Nói “deep copy mọi thứ có thể truy cập được” thường vừa không khả thi vừa không đúng nghiệp vụ. **Phải định nghĩa phạm vi trước.**

## 2. Đồ thị đối tượng, không chỉ cây

Java objects nối nhau bằng tham chiếu thành **object graph**:

```text
Order
 ├── lines: ArrayList
 │    ├── Line A ──► Product("P01")
 │    └── Line B ──► Product("P02")
 ├── customer ────► Customer("C07")
 ├── gateway ─────► PaymentGateway service
 └── catalog ─────► Shared Catalog service
```

Một traversal nông chỉ thấy các field trực tiếp. Một traversal sâu có thể tìm thấy nested collections, arrays, domain values, back-references, caches, services và resources.

Nhưng **“reachable” khác “owned state”**:
- `Order.lines` có thể là phần cấu thành dữ liệu order.
- `Order.gateway` có thể chỉ là service được inject.
- `Order.catalog` có thể là singleton được nhiều orders sử dụng.
- `Product` có thể là immutable shared lookup value.
- `Customer` có thể là entity được tra cứu bằng ID, không nên tự ý nhân bản và cấp identity mới.

**Ranh giới copy** thường là một tập có chọn lọc các edges/nodes trong graph, không phải toàn bộ phần còn lại của JVM.

## 3. Ba quy tắc quyết định copy

Với mỗi field/reference khi xây bản sao, đặt câu hỏi:

1. **Nó thuộc trạng thái giá trị của object cần snapshot?** Nếu không, đừng mặc định copy; có thể bỏ, gắn lại, giữ shared reference hoặc chỉ giữ ID.
2. **Nếu phần tử đó bị mutate sau copy, có cần bên còn lại không bị ảnh hưởng?** Nếu có, cần copy hoặc chuyển sang immutable representation.
3. **Quan hệ identity của các tham chiếu trong bản gốc có phải được bảo toàn?** Nếu hai edges trỏ cùng một child, đôi khi bản sao cũng phải có hai edges trỏ **cùng một child copy**.

Từ đó có các chính sách:

| Loại thành phần | Chính sách thường hợp lý |
| --- | --- |
| Primitive `int`, `boolean`, `double` | Copy giá trị |
| `String`, `Instant`, immutable records đúng nghĩa | Chia sẻ an toàn |
| `int[]`, `ArrayList<MutableItem>` | Copy phần mutable nằm trong snapshot |
| Mutable value child thuộc owner | Copy recursive đúng contract |
| Shared immutable lookup/cache | Có thể chia sẻ |
| JPA entity/aggregate khác, external identity | Thường dùng ID hoặc reference, không nhân bản bừa |
| `Socket`, `Connection`, `Thread`, executor | Không clone như dữ liệu; thiết kế lifecycle riêng |
| `Lock`, monitor object | Không nhân bản ngẫu nhiên; đồng bộ của copy cần thiết kế rõ |
| Back-reference về owner | Trỏ về **owner copy**, không owner gốc |
| Two fields tham chiếu một mutable node | Bảo toàn hoặc cố tình tách alias theo yêu cầu |
| Derived cache, transient field | Có thể bỏ và tính lại |

Bảng trên là hướng phân tích, không phải quy tắc bắt buộc cho mọi domain.

## 4. Copy nông tạo outer object mới nhưng vẫn chia sẻ child

Chương trình **`ShallowOrderDemo.java`**:

```java
final class MutableLine {
    String sku;
    int quantity;

    MutableLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }
}

final class Order {
    final MutableLine line;

    Order(MutableLine line) {
        this.line = line;
    }
}

public class ShallowOrderDemo {
    public static void main(String[] args) {
        MutableLine line = new MutableLine("P01", 2);
        Order original = new Order(line);
        Order shallow = new Order(original.line);

        System.out.println(original == shallow);
        System.out.println(original.line == shallow.line);

        shallow.line.quantity = 9;
        System.out.println(original.line.quantity);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ShallowOrderDemo.java
java ShallowOrderDemo
```

Stdout:

```text
false
true
9
```

Có hai `Order` instances, nhưng chỉ **một MutableLine**. Mutate qua bản sao ảnh hưởng dữ liệu bản gốc.

**Tại sao `final MutableLine line` không giúp?** `final` cấm gán lại reference field, không cấm `line.quantity = 9`.

## 5. Copy sâu đúng với graph đơn giản

Nếu một `Order` **sở hữu** `MutableLine` và bản sao cần độc lập, hãy copy child:

```java
final class Order {
    final MutableLine line;

    Order(MutableLine line) {
        this.line = line;
    }

    Order deepCopy() {
        MutableLine source = line;
        return new Order(
                new MutableLine(source.sku, source.quantity));
    }
}
```

`MutableLine.sku` là `String` immutable, nên được phép chia sẻ string reference. `quantity` là primitive, copy trực tiếp. Tạo một MutableLine mới làm hai bản orders tách mutable state.

**Deep copy ở đây có phạm vi hai tầng**: Order và MutableLine. Không phải “mọi Java objects trong bộ nhớ” đều được nhân bản.

## 6. Runnable: hai copies độc lập về mutable line

Lưu **`DeepOrderDemo.java`**:

```java
final class MutableLine {
    final String sku;
    int quantity;

    MutableLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    MutableLine copy() {
        return new MutableLine(sku, quantity);
    }
}

final class Order {
    final MutableLine line;

    Order(MutableLine line) {
        this.line = line;
    }

    Order deepCopy() {
        return new Order(line.copy());
    }
}

public class DeepOrderDemo {
    public static void main(String[] args) {
        Order original = new Order(
                new MutableLine("P01", 2));
        Order copy = original.deepCopy();

        copy.line.quantity = 9;

        System.out.println(original == copy);
        System.out.println(original.line == copy.line);
        System.out.println(original.line.quantity);
        System.out.println(copy.line.quantity);
        System.out.println(
                original.line.sku == copy.line.sku);
    }
}
```

```bash
javac -encoding UTF-8 DeepOrderDemo.java
java DeepOrderDemo
```

Stdout:

```text
false
false
2
9
true
```

Hai `sku` có thể là cùng String reference do copy trực tiếp giá trị field `sku`; điều này **không phá độc lập về trạng thái mutable** vì String không mutate được.

## 7. Deep copy khác deep immutability

Một bản copy sâu vẫn có thể **mutable**:

```java
Order copied = original.deepCopy();
copied.line.quantity = 9;
```

Điều cần chứng minh của bản copy sâu: mutation ở copied line **không ảnh hưởng** original line và ngược lại, trong phạm vi contract.

Ngược lại, một immutable `record Point(int x, int y)` có thể được **chia sẻ trực tiếp** giữa nhiều owners mà không cần nhân bản, bởi không có mutation thuộc value state đó.

| Câu hỏi | Deep copy | Immutable |
| --- | --- | --- |
| Có tạo independent representation? | Có, ở phần mutable cần tách | Không nhất thiết tạo bản mới |
| Bản kết quả có setter? | Có thể có | Không được làm đổi state đã hứa |
| Có thể share immutable child? | Có | Có |
| Có thể share mutable child? | Nếu child thuộc snapshot cần độc lập: không | Nếu child ảnh hưởng observable value: không |
| Mục đích | Tách tác động mutation | Ngăn mutation trạng thái |
| Có cần kiểm tra alias? | Rất cần | Rất cần |

Đừng dùng hai thuật ngữ thay thế lẫn nhau.

## 8. Array một chiều: `clone`/`Arrays.copyOf`

Mảng primitive một chiều có các phần tử **giá trị primitive**, vì thế:

```java
int[] original = {1, 2, 3};
int[] copy = original.clone();
```

tạo array mới và copy 3 giá trị.

Cũng có:

```java
int[] copy = java.util.Arrays.copyOf(
        original, original.length);
```

`Arrays.copyOf` cho phép chọn độ dài khác, có hành vi padding/truncation theo từng overload; nếu mục tiêu “copy giống hệt”, nên giữ đúng độ dài.

`System.arraycopy` cũng copy nhanh một vùng phần tử nhưng caller phải tự cấp phát destination và kiểm soát bounds/type.

### Runnable

Lưu **`PrimitiveArrayCopyDemo.java`**:

```java
import java.util.Arrays;

public class PrimitiveArrayCopyDemo {
    public static void main(String[] args) {
        int[] source = {4, 5, 6};
        int[] clone = source.clone();
        int[] copy = Arrays.copyOf(source, source.length);

        source[0] = 99;
        clone[1] = 88;

        System.out.println(Arrays.toString(source));
        System.out.println(Arrays.toString(clone));
        System.out.println(Arrays.toString(copy));
        System.out.println(source == copy);
    }
}
```

```bash
javac -encoding UTF-8 PrimitiveArrayCopyDemo.java
java PrimitiveArrayCopyDemo
```

Stdout:

```text
[99, 5, 6]
[4, 88, 6]
[4, 5, 6]
false
```

Đây là deep copy **đối với dữ liệu thuộc mảng `int[]` này**, vì không có nested mutable references.

## 9. Array references: copy outer chưa đủ

```java
StringBuilder[] source = {
    new StringBuilder("A")
};
StringBuilder[] copy = source.clone();
```

`source != copy` nhưng `source[0] == copy[0]`.

Tương tự, `Employee[]`, `Date[]`, `List<?>[]` chứa **references**, nên các phần tử mutable được chia sẻ khi chỉ clone array.

Muốn tách:
- Cấp phát outer array mới.
- Copy mỗi element mutable theo model.
- Giữ `null` đúng contract.
- Có thể giữ nguyên reference immutable elements.
- Nếu một element xuất hiện nhiều lần và cần giữ alias structure, dùng identity map hoặc cách xử lý riêng.

### Runnable

Lưu **`ReferenceArrayCopyDemo.java`**:

```java
import java.util.Arrays;

public class ReferenceArrayCopyDemo {
    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("A");
        StringBuilder[] original = {item};
        StringBuilder[] shallow = original.clone();
        StringBuilder[] deep = {
                new StringBuilder(original[0].toString())
        };

        item.append("!");

        System.out.println(Arrays.toString(original));
        System.out.println(Arrays.toString(shallow));
        System.out.println(Arrays.toString(deep));
        System.out.println(shallow[0] == original[0]);
        System.out.println(deep[0] == original[0]);
    }
}
```

```bash
javac -encoding UTF-8 ReferenceArrayCopyDemo.java
java ReferenceArrayCopyDemo
```

Stdout:

```text
[A!]
[A!]
[A]
true
false
```

## 10. Mảng hai chiều: sao chép từng hàng

`int[][]` là **mảng của các references tới `int[]`**, nên `source.clone()` chỉ copy outer array.

```java
int[][] source = {{1, 2}, {3, 4}};
int[][] shallow = source.clone();
source[0][0] = 9;
```

`shallow[0][0]` cũng thành 9.

Với mảng primitive hai chiều, deep copy thuộc phạm vi này:

```java
static int[][] deepCopy(int[][] source) {
    int[][] result = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        result[i] = source[i] == null
                ? null
                : source[i].clone();
    }
    return result;
}
```

Hàm giữ được:
- Số rows.
- Độ dài riêng của từng row, kể cả *jagged array*.
- `null` rows nếu contract cho phép.
- Các giá trị primitive.

**Có một tinh tế về identity:** nếu `source[0] == source[1]` (hai vị trí cùng trỏ một row), mã trên sẽ tạo **hai row copies khác nhau**. Đối với matrix value thông thường, điều đó có thể phù hợp; nếu alias topology cần được bảo toàn, phải dùng memoization ngay cả ở mảng.

## 11. Runnable: matrix copy với ragged rows

Lưu **`MatrixDeepCopyDemo.java`**:

```java
import java.util.Arrays;

public class MatrixDeepCopyDemo {
    static int[][] deepCopy(int[][] source) {
        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = source[i] == null
                    ? null
                    : source[i].clone();
        }
        return result;
    }

    public static void main(String[] args) {
        int[][] original = {
                {1, 2},
                {3},
                null
        };

        int[][] copy = deepCopy(original);
        original[0][0] = 9;
        copy[1][0] = 8;

        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(copy));
        System.out.println(original[0] == copy[0]);
    }
}
```

```bash
javac -encoding UTF-8 MatrixDeepCopyDemo.java
java MatrixDeepCopyDemo
```

Stdout:

```text
[[9, 2], [3], null]
[[1, 2], [8], null]
false
```

Đây là ví dụ chính xác cho phạm vi các mảng primitives; không phải thuật toán clone sâu đa hình của mọi object.

## 12. `new ArrayList<>(source)` là shallow copy

Một collection constructor:

```java
List<Employee> copy = new ArrayList<>(source);
```

tạo một list mới nhưng giữ **same Employee references**.

Hệ quả:
- `copy.add(newEmployee)` không làm tăng size `source`.
- `copy.get(0).setName(...)` vẫn có thể đổi Employee mà `source.get(0)` tham chiếu.
- Copy list structure không tạo độc lập với mutable elements.

Nếu `Employee` là immutable, việc chia sẻ elements an toàn đối với mutation. Nếu `Employee` là một domain entity có identity chung, **việc chia sẻ có thể là cố ý**, không nhất thiết là lỗi.

### Copy elements bằng một copy factory

```java
List<EmployeeSnapshot> result = source.stream()
        .map(EmployeeSnapshot::from)
        .toList();
```

`EmployeeSnapshot.from` phải được định nghĩa để copy đúng các state fields cần snapshot. `Stream.toList()` ở Java 17 trả unmodifiable list; không tự quyết định nội dung deep của từng snapshot.

## 13. Runnable: list copy tầng ngoài và copy từng giá trị

Lưu **`ListElementCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class MutableItem {
    final String code;
    int quantity;

    MutableItem(String code, int quantity) {
        this.code = code;
        this.quantity = quantity;
    }

    MutableItem copy() {
        return new MutableItem(code, quantity);
    }

    @Override
    public String toString() {
        return code + ":" + quantity;
    }
}

public class ListElementCopyDemo {
    public static void main(String[] args) {
        MutableItem item = new MutableItem("A", 2);
        List<MutableItem> original = new ArrayList<>();
        original.add(item);

        List<MutableItem> shallow =
                new ArrayList<>(original);

        List<MutableItem> deep = original.stream()
                .map(MutableItem::copy)
                .toList();

        item.quantity = 5;

        System.out.println("original = " + original);
        System.out.println("shallow = " + shallow);
        System.out.println("deep = " + deep);
        System.out.println(original.get(0) == deep.get(0));
    }
}
```

```bash
javac -encoding UTF-8 ListElementCopyDemo.java
java ListElementCopyDemo
```

Stdout:

```text
original = [A:5]
shallow = [A:5]
deep = [A:2]
false
```

`deep` có list structure không cho mutator thông thường qua API `Stream.toList`, nhưng `MutableItem` bên trong vẫn mutable nếu người giữ reference khác đến chính item copy đó. **Copy sâu và bất biến là hai điều riêng.**

## 14. `List.copyOf` chỉ đóng cấu trúc list

`List.copyOf(source)` tạo **unmodifiable list** chứa snapshot của các phần tử theo nguồn mutable thông thường, nhưng **không deep-copy mỗi element**.

```java
StringBuilder b = new StringBuilder("A");
List<StringBuilder> source = new ArrayList<>();
source.add(b);

List<StringBuilder> snapshot = List.copyOf(source);
b.append("!");
```

Giờ `snapshot.get(0).toString()` là `"A!"`. Không thể gọi `snapshot.add(...)` thành công, nhưng không ngăn mutation vào builder.

Cũng cần nhớ:
- `List.copyOf` không nhận elements null; có thể ném `NullPointerException`.
- Khi input đã là một implementation unmodifiable phù hợp, có thể trả chính instance đó.
- Một “snapshot tầng ngoài” có ý nghĩa khác với snapshot **toàn object graph**.

**Câu hỏi phải xét là elements có immutable hay cần copy thành value snapshots.**

## 15. Collection wrapper view khác detached snapshot

`Collections.unmodifiableList(backing)` tạo **view**: sửa backing có thể làm view thay đổi.

`List.copyOf(backing)` trả **unmodifiable snapshot** của list elements với backing mutable thông thường, không phản ánh thay đổi cấu trúc tiếp theo của backing.

`new ArrayList<>(backing)` tạo **mutable shallow copy**.

`backing.stream().map(Item::copy).toList()` tạo list các **element copies** theo semantics `Item.copy`; với Java 17 outer list unmodifiable.

Một decision table:

| Nhu cầu | Giải pháp tiêu biểu | Đánh đổi |
| --- | --- | --- |
| Caller không được mutate qua view nhưng owner vẫn quản lý live list | `unmodifiableList(backing)` | Không phải detached snapshot |
| Lấy lịch sử cấu trúc của immutable elements | `List.copyOf(backing)` | Shallow elements |
| Bản list có thể thêm/xóa độc lập | `new ArrayList<>(backing)` | Mutable children vẫn share |
| Bản list với mutable elements tách độc lập | Copy outer và copy từng child | Phải thiết kế copy scope |
| Immutable value graph | Immutable elements + snapshot | Có thể không cần tạo child instances |
| Bảo toàn alias/cycles của graph | Memoized object graph copy | Phức tạp hơn, cần identity mapping |

Đừng dùng tên phương thức “copy” làm bằng chứng đã copy đúng phạm vi.

## 16. Map: phân biệt keys, values và nested mutable state

Một `Map<String, List<Line>>` có nhiều tầng:
1. Map structure.
2. String keys.
3. List values.
4. Line elements.
5. Fields bên trong Line.

Nếu yêu cầu một **snapshot của draft order** không bị ảnh hưởng bởi những lần sửa Line/Lists từ caller:
- Copy Map entries sang Map mới.
- Có thể **giữ String keys** vì immutable.
- Copy mỗi List structure.
- Copy các mutable Line objects.
- Tiếp tục sâu hơn nếu Line có mutable child thuộc snapshot.
- Kiểm soát iteration order nếu output phụ thuộc thứ tự.

`new HashMap<>(source)` chỉ copy tầng Map; `Map.copyOf(source)` đóng outer structure nhưng không copy deep values.

### Cẩn thận với mutable keys

Nếu key là mutable object mà `equals/hashCode` phụ thuộc field có thể đổi, bản sao map cùng key references dễ bị lỗi lookup khi key bị mutate. Nên dùng immutable keys (ID/value objects), hoặc copy keys theo value contract và xác định cách xử lý duplicate/equality đúng.

## 17. Runnable: copy Map và nested Lists/Items

Lưu **`MapDeepCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class Line {
    final String sku;
    int quantity;

    Line(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    Line copy() {
        return new Line(sku, quantity);
    }

    @Override
    public String toString() {
        return sku + ":" + quantity;
    }
}

public class MapDeepCopyDemo {
    static Map<String, List<Line>> copyDeep(
            Map<String, List<Line>> source) {

        Map<String, List<Line>> result =
                new LinkedHashMap<>();

        for (var entry : source.entrySet()) {
            List<Line> copiedLines = new ArrayList<>();
            for (Line line : entry.getValue()) {
                copiedLines.add(line.copy());
            }

            result.put(entry.getKey(), copiedLines);
        }

        return result;
    }

    public static void main(String[] args) {
        Line item = new Line("A", 1);

        Map<String, List<Line>> source =
                new LinkedHashMap<>();
        source.put("cart", new ArrayList<>(List.of(item)));

        Map<String, List<Line>> copy =
                copyDeep(source);

        item.quantity = 9;
        source.get("cart").add(new Line("B", 2));

        System.out.println("source = " + source);
        System.out.println("copy = " + copy);
        System.out.println(
                source.get("cart") == copy.get("cart"));
    }
}
```

```bash
javac -encoding UTF-8 MapDeepCopyDemo.java
java MapDeepCopyDemo
```

Stdout:

```text
source = {cart=[A:9, B:2]}
copy = {cart=[A:1]}
false
```

Sử dụng `LinkedHashMap` để giữ thứ tự insertion trong ví dụ. `String` key được share an toàn; `List` và `Line` là những mutable nodes được copy.

## 18. Nên copy theo **ownership boundary**

Một object domain không nhất thiết sở hữu mọi thứ nó tham chiếu.

Ví dụ `OrderService` có:
- `Repository`;
- `Clock`;
- `PaymentClient`;
- `InventoryCatalog`;
- Một biến `OrderDraft` đang xử lý.

Nếu yêu cầu “tạo một bản order draft khác để user thử sửa”, ta thường copy **dữ liệu OrderDraft**, **không clone** Repository, Clock, PaymentClient hay Catalog.

### Phân tích từng field

| Field | Thuộc snapshot order? | Lựa chọn |
| --- | --- | --- |
| `orderId` | Tùy semantics | Có thể gán ID mới nếu tạo new aggregate, hoặc giữ ID nếu snapshot cùng aggregate |
| `line.quantity` | Có | Copy mutable value |
| `line.sku` | Có | Share immutable String |
| `customerId` | Có | Share/copy immutable ID |
| `customerEntity` | Tùy boundary | Giữ ID/shared reference hoặc tạo customer snapshot |
| `inventoryService` | Không | Inject lại/share, không deep-copy |
| `paymentGateway` | Không | Không copy resource/connection |
| `status` | Có | Copy enum value |
| `auditLog` | Tùy yêu cầu | Có thể snapshot entries hoặc tham chiếu log bên ngoài |

**“Copy sâu” không nên đồng nghĩa “clone toàn bộ business universe”.**

## 19. Entity identity khác value copy

Đối với **value object**, sao chép dữ liệu có thể là ý định chính: `Address(city,street)`, `Money(amount,currency)` hoặc `Coordinate(x,y)`.

Đối với **entity**, identity có ý nghĩa độc lập với fields:
- Hai `Customer` entities có cùng tên/email không nhất thiết là cùng customer.
- Copy `Order` với cùng ID có thể nghĩa là snapshot của **cùng logical entity** tại thời điểm khác.
- Copy `Order` với ID mới có thể nghĩa là **duplicate as new order**, với rules khác (reset status, timestamps, totals).
- Copy một JPA-managed entity bằng `new` không tự làm object mới trở thành managed entity trong persistence context.

Do đó cần **đặt tên operation theo ngữ nghĩa**:
- `snapshot()`: chụp dữ liệu để quan sát/lưu trữ.
- `duplicateForEditing()`: tạo working copy.
- `copyWithNewId()`: tạo một aggregate mới có identity mới.
- `toDto()` hoặc `toValueSnapshot()`: chuyển entity thành data representation.

Một method `deepCopy()` không giải thích được những quyết định identity này nếu không có tài liệu contract.

## 20. Runnable: snapshot giữ ID, duplicate cấp ID mới

Lưu **`IdentityCopyPolicyDemo.java`**:

```java
record OrderSnapshot(String id, String sku, int quantity) {
}

final class OrderDraft {
    private final String id;
    private final String sku;
    private int quantity;

    OrderDraft(String id, String sku, int quantity) {
        this.id = id;
        this.sku = sku;
        this.quantity = quantity;
    }

    OrderSnapshot snapshot() {
        return new OrderSnapshot(id, sku, quantity);
    }

    OrderDraft duplicateAs(String newId) {
        return new OrderDraft(newId, sku, quantity);
    }

    void changeQuantity(int value) {
        quantity = value;
    }
}

public class IdentityCopyPolicyDemo {
    public static void main(String[] args) {
        OrderDraft original =
                new OrderDraft("ORD-1", "SKU-A", 2);

        OrderSnapshot snapshot = original.snapshot();
        OrderDraft duplicate =
                original.duplicateAs("ORD-2");

        original.changeQuantity(9);

        System.out.println(snapshot);
        System.out.println(duplicate.snapshot());
        System.out.println(original.snapshot());
    }
}
```

```bash
javac -encoding UTF-8 IdentityCopyPolicyDemo.java
java IdentityCopyPolicyDemo
```

Stdout:

```text
OrderSnapshot[id=ORD-1, sku=SKU-A, quantity=2]
OrderSnapshot[id=ORD-2, sku=SKU-A, quantity=2]
OrderSnapshot[id=ORD-1, sku=SKU-A, quantity=9]
```

Snapshot record bảo toàn identity **theo giá trị ID**, còn duplication chủ động cấp ID khác. Mỗi operation có nghĩa rõ hơn một lời gọi clone mơ hồ.

## 21. Bảo toàn shared aliases khi copy graph

Đây là vấn đề tinh tế nhất của deep copy.

Giả sử trong graph gốc:

```text
root.left  ──► Child X
root.right ──► Child X
```

Hai fields trỏ tới **cùng child instance**:

```java
root.left == root.right  // true
```

Nếu copy đệ quy đơn giản:

```java
copy.left = root.left.copy();
copy.right = root.right.copy();
```

bản sao có thể thành:

```text
copy.left  ──► Child X1
copy.right ──► Child X2
```

và `copy.left == copy.right` là false.

**Liệu điều đó sai?** Tùy contract:
- Nếu hai fields cố ý phải luôn là cùng logical part (identity-sharing), **sai**.
- Nếu chỉ cần hai values độc lập và alias không quan trọng, có thể chấp nhận.
- Nếu copy nhằm tạo một **graph đẳng cấu về references**, bắt buộc bảo toàn topology alias.

Một thuật toán deep-copy graph thông thường cần **memo map original object identity → copied object**.

## 22. `IdentityHashMap` và việc nhớ những node đã copy

`java.util.IdentityHashMap` so sánh keys theo **reference identity** (`==`), thay vì chỉ dựa trên custom `equals`.

Tại sao quan trọng? Hai mutable nodes khác nhau có thể `equals` nhau nhưng vẫn là hai objects cần copy riêng.

Một `HashMap<Node,Node>` để memo hóa có thể gộp nhầm nếu `Node.equals` định nghĩa equality by value. `IdentityHashMap` phù hợp khi nhiệm vụ là bảo toàn **object graph identities**.

Quy trình:

1. Nếu node là null, trả null.
2. Nếu node đã có trong memo map, trả **cùng copied node** đã tạo.
3. Nếu chưa có, **cấp phát node copy trước**.
4. Đưa mapping `original → copy` vào memo.
5. Đệ quy copy children/edges; khi gặp node cũ thì dùng memo.
6. Trả node copy.

**Thứ tự “đưa vào memo trước khi đi sâu” rất quan trọng** để xử lý cycles.

## 23. Cyclic graph: vòng tham chiếu A → B → A

Nếu graph có:

```text
A.next ──► B
B.next ──► A
```

hàm copy naïve:

```java
Node deepCopy(Node n) {
    Node result = new Node(n.name);
    result.next = deepCopy(n.next);
    return result;
}
```

không có điểm dừng cho cycle; nó liên tục sao chép A,B,A,B...

Phải memoize ngay sau khi cấp phát copy của mỗi node. Khi gặp lại A, tra memo và dùng `copyA` thay vì cấp phát A2.

### Với immutable nodes có final next fields?

Xây dựng graph có cycle bằng **chỉ final fields** có thể khó vì cần tạo objects trỏ về nhau trước khi cả hai hoàn tất construction. Có thể:
- Dùng mutable build phase rồi freeze qua một representation/cấu trúc khác;
- Chuyển graph sang adjacency IDs immutable;
- Dùng builder graph tách khỏi data snapshot;
- Định nghĩa snapshot của edges bằng IDs thay vì Java references.

**Không nên ép một thuật toán deep-copy “generic” bỏ qua initialization/invariants của type.**

## 24. Chương trình Java 17: copy graph có shared alias và cycle

Lưu **`GraphDeepCopyDemo.java`**:

```java
import java.util.IdentityHashMap;
import java.util.Map;

final class Node {
    final String label;
    Node first;
    Node second;

    Node(String label) {
        this.label = label;
    }

    static Node copyGraph(Node root) {
        return copyGraph(root, new IdentityHashMap<>());
    }

    private static Node copyGraph(
            Node original,
            Map<Node, Node> visited) {

        if (original == null) {
            return null;
        }

        Node known = visited.get(original);
        if (known != null) {
            return known;
        }

        Node copy = new Node(original.label);
        visited.put(original, copy);

        copy.first = copyGraph(original.first, visited);
        copy.second = copyGraph(original.second, visited);

        return copy;
    }
}

public class GraphDeepCopyDemo {
    public static void main(String[] args) {
        Node root = new Node("root");
        Node shared = new Node("shared");

        root.first = shared;
        root.second = shared;
        shared.first = root;

        Node copy = Node.copyGraph(root);

        System.out.println(root == copy);
        System.out.println(root.first == copy.first);
        System.out.println(copy.first == copy.second);
        System.out.println(copy.first.first == copy);
        System.out.println(copy.label);
        System.out.println(copy.first.label);
    }
}
```

```bash
javac -encoding UTF-8 GraphDeepCopyDemo.java
java GraphDeepCopyDemo
```

**Stdout:**

```text
false
false
true
true
root
shared
```

Phân tích:
- Outer root đã được copy, không còn identity với original.
- Shared child đã được copy, không còn là original shared node.
- **Hai edges trong copy cùng trỏ một shared-node copy**, nên alias relation được giữ.
- Back-reference từ child copy về **root copy**, không trỏ root gốc.
- Các `String label` immutable có thể chia sẻ an toàn.

**Phạm vi demo:** Graph nodes có hai references và String label. Nó không sao chép arbitrary Java fields qua reflection; đây là thuật toán domain-specific rõ ràng.

## 25. Trường hợp copy làm mất alias nhưng không nhất thiết sai

Nếu original có:

```text
Pair(left = mutable Money M, right = mutable Money M)
```

và business requirement là “tạo hai số tiền độc lập để chỉnh sửa riêng rẽ” thì việc copy M thành hai objects **có thể chính là mong muốn**.

Ngược lại, nếu Pair biểu diễn “debit/credit cùng tham chiếu một source value entity”, phá alias có thể vi phạm domain invariant.

Vì vậy phải trả lời một câu trước khi viết memo algorithm:

> **Contract yêu cầu copy các values hay copy topology/identity của graph?**

- **Value copy**: có thể làm phẳng và nhân bản các giá trị.
- **Graph-preserving copy**: cần giữ relationships về identity.
- **Snapshot DTO**: có thể chuyển edges sang IDs thay vì references.
- **Aggregate duplicate**: có thể đổi identity root và chỉ deep-copy owned children.

Từ “deep” không giải quyết những quyết định nghiệp vụ này.

## 26. Nulls, polymorphism và field subclasses

Nếu field khai báo:

```java
Animal pet;
```

nhưng runtime object là `Dog`, việc tạo:

```java
new Animal(/* base fields */)
```

khi copy `pet` có thể làm **mất Dog-specific state** và behavior. Java không tự clone runtime subtype khi ta viết constructor của base.

Ví dụ về yêu cầu:
- Giữ runtime subtype nếu snapshot phải vẫn là một `Dog`;
- Hoặc chuyển thành immutable DTO có discriminator/type field;
- Hoặc copy chỉ những state thuộc base contract nếu business requirement thực sự chỉ cần phần base.

### Các lựa chọn thiết kế

1. **Polymorphic copy method** trong hierarchy có contract rõ.
2. **Visitor/factory** với sealed types nếu tập subclasses đóng.
3. **Snapshot DTO** với các fields cần thiết từ từng subtype.
4. **Serialization** nếu model thực sự có serializer với schema phù hợp, nhưng cần biết caveats.

**Không xem cast là copy**:

```java
Animal pet = new Dog();
// Dog dog = (Dog) pet; // Chỉ đổi kiểu nhìn thấy, không clone.
```

## 27. Runnable: copy giữ subtype có chủ đích

Lưu **`PolymorphicCopyDemo.java`**:

```java
sealed interface Pet permits Dog, Cat {
    Pet copy();
    String describe();
}

final class Dog implements Pet {
    private int tricks;

    Dog(int tricks) {
        this.tricks = tricks;
    }

    void learn() {
        tricks++;
    }

    @Override
    public Pet copy() {
        return new Dog(tricks);
    }

    @Override
    public String describe() {
        return "Dog tricks=" + tricks;
    }
}

final class Cat implements Pet {
    private int naps;

    Cat(int naps) {
        this.naps = naps;
    }

    @Override
    public Pet copy() {
        return new Cat(naps);
    }

    @Override
    public String describe() {
        return "Cat naps=" + naps;
    }
}

public class PolymorphicCopyDemo {
    public static void main(String[] args) {
        Pet original = new Dog(2);
        Pet copied = original.copy();

        ((Dog) original).learn();

        System.out.println(original.describe());
        System.out.println(copied.describe());
        System.out.println(original == copied);
        System.out.println(copied instanceof Dog);
    }
}
```

```bash
javac -encoding UTF-8 PolymorphicCopyDemo.java
java PolymorphicCopyDemo
```

Stdout:

```text
Dog tricks=3
Dog tricks=2
false
true
```

Ở đây copy là **value copy của một Pet object đơn lẻ**; vì fields chỉ là primitive, không có nested mutable children. Với graph phức tạp có cycles, mỗi implementation cần cùng cơ chế memo/context để bảo toàn topology.

## 28. Copy constructor: dễ đọc nhưng phải copy đúng phần mutable

Một copy constructor:

```java
final class Profile {
    private final String name;
    private final int[] scores;

    Profile(Profile other) {
        name = other.name;
        scores = other.scores.clone();
    }
}
```

rõ:
- Share `String name` an toàn.
- Copy primitive array độc lập.

**Không có syntax đặc biệt `copy constructor` trong Java** như một built-in clone operator. Đó là một constructor do người lập trình viết, nhận object cùng type làm đầu vào.

### Những hạn chế cần xét

- Nếu class không `final` và có subclasses, gọi base copy constructor có thể không copy state ở subtype.
- Nếu nested fields mutable, phải copy sâu hơn.
- Nếu object có ID/resource, cần định nghĩa cách xử lý.
- Nếu fields có invariants, constructor cần validate hoặc dùng helper giữ invariant.
- Nếu source đang bị thread khác mutate, một copy constructor không synchronized không bảo đảm snapshot nhất quán.

## 29. Static factory `copyOf` và tên API truyền ý định

Một pattern:

```java
final class Profile {
    static Profile copyOf(Profile source) {
        return new Profile(source);
    }
}
```

Factory cho phép:
- Validate source/null;
- Chọn trả immutable existing object nếu chia sẻ là an toàn và hợp contract;
- Chọn representation khác;
- Có tên rõ: `deepCopyOf`, `snapshotOf`, `duplicateAs`;
- Giấu constructors nếu cần.

**Nhưng** tên `copyOf` **không bảo đảm cấp phát**: một số APIs như `List.copyOf` có thể trả input nếu đã là unmodifiable implementation thích hợp. Khi thiết kế API riêng, phải tài liệu hóa có cam kết **new identity** hay chỉ cam kết **value/immutability**.

Nếu caller bắt buộc `copy != source`, nêu điều đó rõ trong contract.

## 30. `Object.clone()`: cơ chế nền, mặc định nông

`Object` có method `protected Object clone() throws CloneNotSupportedException`. Nó không public trong Object. Việc gọi clone hợp lệ phụ thuộc class, access và marker interface `Cloneable` cùng các quy tắc áp dụng.

`Object.clone()` thực hiện sao chép fields theo kiểu **field-wise**, nên những reference fields mặc định trỏ **cùng child objects** (shallow copy), trừ khi custom logic sửa lại.

### Marker interface `Cloneable`

`Cloneable` không tự khai báo public method `clone`; nó đánh dấu khả năng để `Object.clone` không từ chối theo điều kiện thông thường của API.

Nếu muốn công bố clone:
- Class có thể override `clone` thành public;
- Có thể gọi `super.clone()`;
- Phải copy lại mutable components;
- Phải xử lý exception/return type;
- Phải xét subclassing.

### Tại sao copy constructor/factory thường dễ dùng hơn?

`clone` có nhiều góc cạnh với inheritance, protected access, invariants, final fields và shallow nested references. Đối với object graph có identity/cycles, phải thiết kế logic custom dù dùng clone hay không.

**Không phải cứ `implements Cloneable` là “copy sâu”.**

## 31. Runnable: `clone()` nông và copy sâu thủ công

Lưu **`CloneDepthDemo.java`**:

```java
import java.util.Arrays;

final class Scores implements Cloneable {
    private int[] values;

    Scores(int[] values) {
        this.values = values;
    }

    @Override
    public Scores clone() {
        try {
            return (Scores) super.clone();
        } catch (CloneNotSupportedException error) {
            throw new AssertionError(error);
        }
    }

    Scores deepCopy() {
        return new Scores(values.clone());
    }

    void set(int index, int value) {
        values[index] = value;
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class CloneDepthDemo {
    public static void main(String[] args) {
        Scores original = new Scores(new int[] {1, 2});
        Scores shallow = original.clone();
        Scores deep = original.deepCopy();

        shallow.set(0, 99);
        deep.set(1, 88);

        System.out.println("original = " + original);
        System.out.println("shallow = " + shallow);
        System.out.println("deep = " + deep);
    }
}
```

```bash
javac -encoding UTF-8 CloneDepthDemo.java
java CloneDepthDemo
```

Stdout:

```text
original = [99, 2]
shallow = [99, 2]
deep = [1, 88]
```

**Cảnh báo có chủ đích:** constructor `Scores(int[])` giữ direct input alias nên bản thân Scores **không bất biến** và không bảo vệ dữ liệu khỏi nguồn bên ngoài. Mục tiêu của ví dụ là làm rõ `super.clone()` nông; API production cần xác định ownership.

## 32. Record: copy dữ liệu nhưng nested references vẫn cần chính sách

Một record:

```java
record Report(String title, List<StringBuilder> lines) {
}
```

được tạo mới bằng:

```java
Report copy = new Report(
        original.title(), original.lines());
```

đang giữ **chính cùng list**. Copy record container chưa deep-copy.

Nếu muốn snapshot text:
- Chuyển từng `StringBuilder` thành `String`;
- Lưu dưới `List<String>`;
- Không nhất thiết record copy có cùng type như source nếu ý nghĩa snapshot khác.

Ví dụ:

```java
record ReportSnapshot(
        String title, List<String> lines) {

    ReportSnapshot {
        lines = List.copyOf(lines);
    }
}
```

Đừng nhầm record ngầm định final với deep immutability: components có thể chứa mutable referents. Việc copy một record chỉ bằng canonical constructor là nông với những references đó.

## 33. Runnable: mutable source → immutable snapshot record

Lưu **`RecordSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class MutableReport {
    String title;
    List<StringBuilder> lines = new ArrayList<>();

    MutableReport(String title) {
        this.title = title;
    }
}

record ReportSnapshot(
        String title, List<String> lines) {

    ReportSnapshot {
        lines = List.copyOf(lines);
    }

    static ReportSnapshot from(MutableReport source) {
        List<String> copiedText = source.lines.stream()
                .map(StringBuilder::toString)
                .toList();

        return new ReportSnapshot(source.title, copiedText);
    }
}

public class RecordSnapshotDemo {
    public static void main(String[] args) {
        MutableReport report = new MutableReport("Q1");
        StringBuilder line = new StringBuilder("Revenue");

        report.lines.add(line);
        ReportSnapshot snapshot =
                ReportSnapshot.from(report);

        line.append(" updated");
        report.lines.add(new StringBuilder("Profit"));

        System.out.println(report.lines);
        System.out.println(snapshot);
    }
}
```

```bash
javac -encoding UTF-8 RecordSnapshotDemo.java
java RecordSnapshotDemo
```

Stdout:

```text
[Revenue updated, Profit]
ReportSnapshot[title=Q1, lines=[Revenue]]
```

Immutable `String` elements và unmodifiable list tạo representation không bị mutate bởi những changes sau của source, trong phạm vi model. Nếu `source` bị sửa từ thread khác **trong lúc copy**, vẫn phải có snapshot synchronization.

## 34. Defensive copying: bảo vệ ranh giới owner

Một class công bố “giữ snapshot dữ liệu” thường cần:
- **Copy khi nhận input** để caller không còn alias tới state nội bộ.
- **Copy khi trả output** nếu internal representation vẫn mutable.
- **Không để mutators khác công bố reference nội bộ**.
- **Không giữ exposed mutable children** trong field mà caller biết và sửa được.

Ví dụ với `int[]`:

```java
final class IntSnapshot {
    private final int[] values;

    IntSnapshot(int[] input) {
        values = input.clone();
    }

    int[] values() {
        return values.clone();
    }
}
```

Tuy nhiên nếu getter chỉ cần `size()`/`get(i)`, có thể không trả mảng nào cả.

### Deep copy trong constructor vs method snapshot

Nếu source là một aggregate mutable lớn, copy ở constructor của value object snapshot sẽ tạo boundary rõ:
- Aggregate thực hiện nghiệp vụ;
- Snapshot giữ fields quan sát;
- Không tạo duplicate aggregate với hai IDs cùng nghĩa;
- Có thể serialize snapshot mà không chạm live aggregate.

**Không phải mọi getter phải deep-copy toàn graph**. Thiết kế một immutable read model thường tốt hơn trả một đống mutable internals rồi copy mỗi lần.

## 35. Runnable: bảo vệ cả input và output arrays

Lưu **`DefensiveCopyDemo.java`**:

```java
import java.util.Arrays;

final class IntSnapshot {
    private final int[] values;

    IntSnapshot(int[] input) {
        values = input.clone();
    }

    int[] values() {
        return values.clone();
    }

    int at(int index) {
        return values[index];
    }
}

public class DefensiveCopyDemo {
    public static void main(String[] args) {
        int[] input = {10, 20};
        IntSnapshot snapshot = new IntSnapshot(input);

        input[0] = 99;
        int[] fromGetter = snapshot.values();
        fromGetter[1] = 88;

        System.out.println(snapshot.at(0));
        System.out.println(snapshot.at(1));
        System.out.println(Arrays.toString(fromGetter));
        System.out.println(Arrays.toString(input));
    }
}
```

```bash
javac -encoding UTF-8 DefensiveCopyDemo.java
java DefensiveCopyDemo
```

Stdout:

```text
10
20
[10, 88]
[99, 20]
```

Hai copy operations phục vụ **hai hướng aliasing** khác nhau; bỏ một hướng là còn đường mutate nội bộ.

## 36. Sao chép sâu dưới concurrency: snapshot phải nhất quán

Một phương thức:

```java
List<Item> snapshot = source.stream()
        .map(Item::copy)
        .toList();
```

có thể đúng trong single-threaded state nhưng không tự là **atomic snapshot** khi threads khác đang mutate `source` hoặc những Item bên trong.

Nếu source bị thay đồng thời không synchronized, có thể:
- Gặp `ConcurrentModificationException` với một số iterators (không phải bảo đảm phát hiện mọi race);
- Sao chép một tập dữ liệu “nửa trước/nửa sau”;
- Đọc fields không nhất quán;
- Tạo bản snapshot vi phạm invariant business.

### Thiết kế nhất quán

1. Mọi writer và copier dùng **cùng monitor/lock**, copy trong critical section ngắn và hợp lý.
2. Chuyển toàn state thành **immutable aggregate snapshot** rồi publish một reference atomic.
3. Dùng transaction/versioning/snapshot isolation ở data layer nếu nguồn là database.
4. Nếu dùng concurrent collection, đọc đúng contract iteration/snapshot của nó (một số iterators weakly consistent, không phải atomic snapshot).

**Deep copy và concurrency snapshot là hai yêu cầu tách biệt.** Copy đúng mutable nodes nhưng đọc không nhất quán vẫn có thể cho dữ liệu sai.

## 37. Runnable: chụp hai fields dưới cùng monitor

Lưu **`ConsistentSnapshotDemo.java`**:

```java
record BalanceSnapshot(int debit, int credit) {
}

final class AccountPair {
    private final Object lock = new Object();
    private int debit;
    private int credit;

    void setBoth(int debit, int credit) {
        synchronized (lock) {
            this.debit = debit;
            this.credit = credit;
        }
    }

    BalanceSnapshot snapshot() {
        synchronized (lock) {
            return new BalanceSnapshot(debit, credit);
        }
    }
}

public class ConsistentSnapshotDemo {
    public static void main(String[] args)
            throws InterruptedException {

        AccountPair pair = new AccountPair();
        pair.setBoth(10, 10);

        Thread writer = new Thread(
                () -> pair.setBoth(20, 20));
        writer.start();
        writer.join();

        BalanceSnapshot snapshot = pair.snapshot();
        System.out.println(snapshot);
    }
}
```

```bash
javac -encoding UTF-8 ConsistentSnapshotDemo.java
java ConsistentSnapshotDemo
```

Stdout:

```text
BalanceSnapshot[debit=20, credit=20]
```

Ví dụ cố ý `join` để stdout chắc chắn; trong ứng dụng concurrent thực, `snapshot()` giữ monitor giúp đọc **cặp fields nhất quán**, không đọc một field trước update và field kia sau update.

## 38. Không copy tài nguyên hệ thống như giá trị thường

Những loại sau có identity/vòng đời riêng:

- `java.net.Socket`;
- `java.io.InputStream` / `OutputStream`;
- `java.sql.Connection`;
- `Thread`, executor;
- File descriptor/OS handle;
- Monitor lock/`ReentrantLock`;
- Transaction context và managed persistence sessions.

Việc cố deep copy chúng có thể:
- Không có API clone;
- Tạo một resource mới không cùng semantics;
- Vi phạm ownership và lifecycle;
- Làm nhiều copies tưởng sở hữu cùng handle;
- Mất tính đúng của synchronization.

Khi một object cần clone **dữ liệu** và cũng giữ resource:
- **Copy data fields** theo scope.
- **Bỏ hoặc cấp lại dependency** ở composition root.
- **Không copy trực tiếp resource** trừ khi API resource cung cấp một operation có contract rõ (ví dụ tạo stream mới tới cùng file) và yêu cầu thật sự muốn vậy.
- Document ai chịu trách nhiệm `close()` ở original/copy.

**Không dùng reflection để sao chép mọi field một cách mù quáng**, đặc biệt với internals của JDK/resources.

## 39. Dịch vụ dùng chung không phải child state của snapshot

`ReportGenerator` có field:

```java
private final Formatter formatter;
private final Repository repository;
private final List<Section> sections;
```

Yêu cầu “copy report draft để chỉnh sửa sections” thường chỉ cần:
- Copy `sections` cùng những mutable elements thuộc draft;
- Có thể giữ `formatter` và `repository` references cho hai generators nếu đây là shared dependencies có contract dùng chung;
- Hoặc không đưa services vào snapshot DTO.

**Cách thể hiện API tốt:**

```java
ReportSnapshot snapshot = generator.snapshot();
ReportGenerator copy = new ReportGenerator(
        formatter, repository, snapshot.copySections());
```

Đoạn trên **minh họa ý tưởng**, không phải standalone runnable vì `ReportSnapshot`/`copySections` cần được định nghĩa theo domain.

Điều quan trọng là dependency injection và copy policy rõ, không phải vẽ object graph rồi copy mọi edge.

## 40. Không deep-copy JPA entities ngoài transaction một cách tuỳ tiện

Với các ORM/JPA entities:
- Proxy và lazy associations có thể khởi tạo truy vấn khi duyệt graph.
- Bidirectional associations dễ tạo cycles.
- Entity identity và persistence context có ý nghĩa riêng.
- Collection wrappers của ORM có semantics đặc thù.
- Copy IDs y nguyên có thể gây nhầm “snapshot của entity” với “entity mới để persist”.

Hướng thường an toàn:
- Xác định aggregate boundary.
- Tạo DTO/value snapshot từ dữ liệu cần thiết dưới transaction phù hợp.
- Không gọi reflection clone mọi field.
- Với duplication, tạo entity mới theo business rules, cấp IDs/trạng thái mới thích hợp.
- Nếu cần clone owned child collection, phân biệt owned vs shared relationships rõ.

**Deep copy cho domain không đồng nghĩa deep clone toàn database.**

## 41. Serialization round-trip có phải deep copy?

Có thể nghe mẹo:

```text
object -> JSON -> object mới
```

hoặc Java serialization/other binary codec để “deep clone”. Nhưng round-trip **không phải giải pháp chung không cần suy nghĩ**.

Rủi ro:
- Chỉ fields được serialize mới xuất hiện trong bản sao;
- Object graph cycles/shared identity có thể không được giữ nguyên nếu format/config không hỗ trợ;
- Polymorphic subtype info có thể mất nếu schema không biểu diễn;
- Transient fields, derived caches và resource references xử lý khác;
- Constructors/validation và default values có thể cho semantics khác;
- Serialization/deserialization dữ liệu không tin cậy có rủi ro bảo mật;
- CPU/allocations và compatibility/schema versioning có thể tốn kém.

**Dùng serialization khi snapshot format/DTO đã là một hợp đồng thực sự**, không mặc định xem nó là một `Object.deepCopy` tổng quát.

### Nếu cần graph-preserving serialization

Phải kiểm tra rõ codec có hỗ trợ:
- Object identity/reference tracking;
- Cycle handling;
- Immutable/record value construction;
- Subclass type discriminators;
- Nulls, generics, maps và collections;
- Security/allowlists;
- Version migration.

Không suy từ việc “JSON ra giống nhau” thành “copy đã bảo toàn graph identity”.

## 42. HashMap keys và copy policy

Một `Map<Key,Value>` có thể dùng keys mutable hoặc immutable.

Nếu copy map mà chia sẻ mutable keys, một thread/caller thay fields tham gia `equals/hashCode` có thể khiến map lookup hành xử bất ngờ.

Nếu **deep-copy keys**, lại có các vấn đề:
- Copy có được giữ equality semantics không?
- Có key collisions sau normalize/copy không?
- Có hai original keys identity khác nhau nhưng value equal, map mới không thể chứa cả hai theo same equality contract?
- Nếu key là entity identity, copy nó có làm hỏng link với các objects khác không?

Vì thế:
- Dùng immutable key types khi có thể (String, immutable IDs/records).
- Copy values/nested state theo cần thiết.
- Không copy keys mù quáng.
- Khi keys có custom equality, test cụ thể mapping sau copy.

**Tính đúng của copied map không chỉ là “size bằng nhau”.**

## 43. Chọn copy depth bằng API contract

Một method `copy()` thiếu mô tả có thể tạo hiểu lầm:
- Caller tưởng deep, implementation làm shallow.
- Caller tưởng snapshot, implementation giữ live view.
- Caller tưởng new identity, implementation share immutable instance.
- Caller tưởng include resource, implementation bỏ resource.
- Caller tưởng copy cả subtype, implementation chỉ copy base fields.

Nên nêu rõ:
- Các fields thuộc snapshot;
- Các nested types được copy hoặc share;
- Có giữ alias/cycle topology không;
- Có bảo đảm object mới cho root không;
- Có chia sẻ dependencies/resources không;
- Bản sao mutable hay immutable;
- Có thread-safe snapshot không;
- Có ID mới hay giữ ID.

Ví dụ JavaDoc:

```java
/**
 * Tạo working copy độc lập của các order lines.
 * String SKU và ProductId được chia sẻ vì immutable.
 * InventoryService không thuộc snapshot.
 * Root nhận identity mới theo business rule.
 * Các line objects mới có thể sửa mà không ảnh hưởng original.
 */
OrderDraft duplicateForEditing(String newOrderId) {
    // implementation...
    return null;
}
```

Đây là đoạn **minh họa hợp đồng**, không phải implementation nên dùng. Return null chỉ là chỗ biểu diễn rằng body chưa được trình bày; trong source production phải viết implementation thật, không giữ placeholder này.

## 44. Tính đúng: equality, independence và alias preservation

Một deep copy test không nên chỉ có:

```java
assertNotSame(original, copy);
```

Điều đó mới xác nhận root mới, chưa nói gì về children.

Test phải trả lời nhiều chiều:
1. **Initial value equivalence:** các giá trị thuộc copy scope bằng nhau khi tạo copy.
2. **Mutable independence:** sửa original không đổi copy; sửa copy không đổi original.
3. **Root identity:** new root nếu contract yêu cầu.
4. **Nested identity:** mutable child copy khác original child tương ứng.
5. **Shared alias topology:** nếu original có aliases tới một child, copy có giữ relation như mong muốn?
6. **Cycles:** back-reference trỏ về copy root, không original root.
7. **Null/empty input:** copy đúng cả missing/empty branches.
8. **Runtime subtype:** implementation types có giữ nếu contract yêu cầu?
9. **External references:** services/resources có được xử lý đúng policy?
10. **Concurrency:** state snapshot có nhất quán nếu source được sửa đồng thời?

### Không bắt buộc mọi field đều khác identity

Đối với immutable `String` hoặc `Instant`, `original.name == copy.name` có thể true mà deep copy hoàn toàn đúng theo contract mutation independence.

## 45. Runnable: kiểm thử deep copy bằng output ổn định

Lưu **`DeepCopyContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class EditableLine {
    final String code;
    int count;

    EditableLine(String code, int count) {
        this.code = code;
        this.count = count;
    }

    EditableLine copy() {
        return new EditableLine(code, count);
    }
}

final class Draft {
    private final List<EditableLine> lines;

    Draft(List<EditableLine> lines) {
        this.lines = lines;
    }

    Draft deepCopy() {
        List<EditableLine> result = new ArrayList<>();
        for (EditableLine line : lines) {
            result.add(line.copy());
        }
        return new Draft(result);
    }

    EditableLine line(int index) {
        return lines.get(index);
    }

    int size() {
        return lines.size();
    }
}

public class DeepCopyContractDemo {
    public static void main(String[] args) {
        EditableLine line = new EditableLine("P", 2);
        Draft original = new Draft(
                new ArrayList<>(List.of(line)));
        Draft copy = original.deepCopy();

        boolean rootDistinct = original != copy;
        boolean childDistinct =
                original.line(0) != copy.line(0);

        original.line(0).count = 9;
        copy.line(0).count = 5;

        System.out.println("root distinct = " + rootDistinct);
        System.out.println("child distinct = " + childDistinct);
        System.out.println("original count = "
                + original.line(0).count);
        System.out.println("copy count = "
                + copy.line(0).count);
        System.out.println("same size = "
                + (original.size() == copy.size()));
    }
}
```

```bash
javac -encoding UTF-8 DeepCopyContractDemo.java
java DeepCopyContractDemo
```

Stdout:

```text
root distinct = true
child distinct = true
original count = 9
copy count = 5
same size = true
```

Ví dụ cho thấy cả root và mutable element được tách. Nó chưa test cycles hay shared-alias preservation; những case đó thuộc contract graph riêng.

## 46. Chi phí: độ phức tạp và memory

Giả sử copy một acyclic tree gồm `n` mutable nodes:
- Time thường **O(n)** nếu mỗi node được thăm/copy một lần và thao tác copy field có chi phí cố định.
- Memory mới cho nodes thường **O(n)**, thêm recursion stack theo độ sâu.
- Nếu mỗi node chứa array/string lớn phải copy, tổng thời gian/memory phụ thuộc **tổng lượng dữ liệu thực sự sao chép**.

Với graph có cycles/shared aliases dùng memo:
- Nếu duyệt mỗi node/edge một lần, độ phức tạp cơ bản **O(V + E)** cho graph structure, cộng chi phí sao chép payload.
- Memo map cần bộ nhớ theo số original nodes được copy.
- Recursion depth có thể gây `StackOverflowError` ở graph rất sâu; iterative traversal/work queue là phương án cho dữ liệu lớn hoặc không kiểm soát độ sâu.

### Đừng deep-copy mọi lần getter được gọi

Nếu một object có 100.000 elements, mỗi lần `getLines()` deep-copy có thể tạo nhiều allocations và chậm. Thay vào đó:
- Công bố immutable snapshot một lần ở boundary;
- Cung cấp `getCount()`/`getAt(i)` query hẹp;
- Dùng persistent data structures khi cần các phiên bản thường xuyên;
- Định nghĩa explicit `snapshot()` để caller biết chi phí.

**Performance là vấn đề thiết kế API**, không chỉ tối ưu loop.

## 47. Structural sharing: không phải lúc nào độc lập cũng cần clone mọi node

Immutable persistent structures có thể tạo version mới và **chia sẻ các nhánh immutable** với version cũ:

```text
Version A ──► Branch1 ──► SharedImmutableTail
Version B ──► Branch2 ──► SharedImmutableTail
```

Vì SharedImmutableTail không thể mutate, việc chia sẻ không ảnh hưởng observational independence của hai versions.

Ngược lại, **share mutable tail** làm bản A có thể đổi khi B mutate, phá snapshot contract.

Tư duy tốt:
- **Copy** những mutable values cần độc lập.
- **Share** những immutable nodes an toàn.
- **Preserve identity** đối với shared references có ý nghĩa.
- **Exclude/reinject** services/resources ngoài dữ liệu.
- **Change representation** nếu graph gốc quá phức tạp hoặc không phù hợp snapshot.

Đây là lý do “deep copy” phải được định nghĩa theo **phạm vi và contract**, không theo độ sâu số lớp cố định.

## 48. Giới hạn kỹ thuật: reflection không giải quyết tất cả

Một helper cố tự động iterate fields và recursively copy bằng reflection có thể gặp:

- Private fields/strong encapsulation và JPMS module accessibility;
- Constructors và invariants không được thiết lập đúng;
- Final fields không thể xử lý như mutable references tùy tiện;
- Không biết field nào owned, shared, derived hoặc resource;
- Cycles, aliases và class loaders;
- Collections với internal representations đặc biệt;
- Security risk khi đụng secrets;
- Types không cloneable hoặc cần lifecycle;
- Dynamic proxies, bytecode-enhanced ORM entities.

Vì vậy, **“generic recursive deepCopy(Object)” không phải giải pháp mặc định an toàn cho Java**.

Dùng explicit copy policy/factory hoặc một serialization schema có chủ đích giúp review tính đúng dễ hơn.

## 49. Các câu hỏi thiết kế trước khi chọn kỹ thuật

Hãy trả lời cụ thể:

1. **Mục đích copy là gì?** Undo, snapshot, prototype, concurrent read model, duplicate entity, message payload hay test fixture?
2. **Root cần identity mới không?**
3. **Trạng thái nào là owned data?**
4. **Thành phần nào chỉ là dependency/reference bên ngoài?**
5. **Những values nào immutable và share được?**
6. **Mutable children nào phải độc lập?**
7. **Có shared alias relationships không?**
8. **Có cycles/back-references không?**
9. **Có polymorphic subclasses không?**
10. **Có nulls, jagged arrays hoặc sparse collections không?**
11. **Có unmanaged resources không?**
12. **Source có bị sửa đồng thời không?**
13. **Cần bảo toàn object graph topology hay chỉ content values?**
14. **Bản sao có mutable tiếp không, hay snapshot phải immutable?**
15. **Data size và copy frequency bao nhiêu?**

Nếu chưa có câu trả lời, chọn `clone()` hoặc serialize-copy ngay thường chỉ che dấu quyết định quan trọng.

## 50. Decision matrix cho một số yêu cầu thực tế

| Yêu cầu | Thứ phải copy | Thứ có thể share/không copy | Hướng kỹ thuật |
| --- | --- | --- | --- |
| Copy `int[]` trước khi lưu | Array values | Không có nested mutable refs | `clone`/`Arrays.copyOf` |
| Copy `int[][]` | Outer + inner arrays | Primitive values | Copy từng row |
| Chụp danh sách tên | Outer list snapshot | `String` elements | `List.copyOf` |
| Copy danh sách `MutableLine` | Outer + từng Line mutable | Immutable SKU | Copy constructor/factory từng Line |
| Chụp report từ builders | Text content | Không giữ StringBuilder aliases | Chuyển `StringBuilder→String` |
| Duplicate Order với ID mới | Owned lines + domain values; ID theo rule | Product catalog, services | Domain factory rõ |
| Clone cyclic graph giữ alias | Các nodes/edges thuộc graph | Immutable payload | `IdentityHashMap` memo |
| Copy API DTO | DTO fields theo schema | Services/resources bỏ | Mapping explicit |
| Copy ORM entity | Chỉ owned aggregate theo business | Shared entities theo ID | DTO/new aggregate factory |
| Copy `Socket/Connection` | Không copy như value | Reinject/construct according to contract | Lifecycle design |
| Snapshot mutable concurrent state | State nhất quán theo lock/transaction | Immutable subgraphs | Lock/snapshot isolation |
| Versioned immutable tree | Những nhánh thay đổi | Immutable unchanged nodes | Structural sharing |

## 51. Bài tập 1 — Gán reference có copy không?

```java
List<String> a = new ArrayList<>();
List<String> b = a;
```

**Đáp án:** Không. `a == b` là true. Mutate List qua một reference ảnh hưởng cả hai vì cùng object.

## 52. Bài tập 2 — Copy `List<String>` có cần deep copy String không?

**Đáp án:** Không, `String` immutable. Nếu muốn unmodifiable detached list snapshot, `List.copyOf(source)` thường đủ với một mutable `List<String>` nguồn (có null policy phù hợp). Không cần nhân bản từng String.

## 53. Bài tập 3 — Copy `List<StringBuilder>` bằng `new ArrayList<>(source)` có sâu không?

**Đáp án:** Không. Outer list mới nhưng StringBuilder references được chia sẻ. Muốn độc lập về nội dung builders, copy từng builder hoặc chuyển sang String snapshots.

## 54. Bài tập 4 — Copy matrix bằng `matrix.clone()` có sâu không?

**Đáp án:** Không với `int[][]`. Nó chỉ copy outer references; rows vẫn chung. Cần clone từng row hoặc thiết kế graph-aware nếu shared-row alias topology quan trọng.

## 55. Bài tập 5 — Hai fields trỏ cùng node

```java
root.left == root.right // true
```

Sau deep copy cần luôn giữ true?

**Đáp án:** **Tùy contract.** Nếu copy phải bảo toàn graph identity/alias topology thì có, cần memo map; nếu copy values thành hai child độc lập theo yêu cầu thì không nhất thiết.

## 56. Bài tập 6 — Cyclic graph

A.next = B và B.next = A. Deep copy naïve recursion có vấn đề gì?

**Đáp án:** Không kết thúc do cycle, thường gây `StackOverflowError`. Cần memoize original→copy **ngay khi tạo copy node** trước khi đệ quy children.

## 57. Bài tập 7 — `HashMap` hay `IdentityHashMap` cho visited map?

Nodes override `equals` để hai nodes khác identity nhưng cùng label được coi equal.

**Đáp án:** Nếu mục tiêu bảo toàn **reference identity** của graph, dùng `IdentityHashMap` hoặc một identity-aware strategy. `HashMap` có thể gộp nhầm nodes equal nhưng khác identity.

## 58. Bài tập 8 — Clone shared `Connection`?

Một OrderService giữ `Connection` được DI container quản lý. Khi copy Order draft có cần deep copy Connection không?

**Đáp án:** Không. Connection là resource/dependency ngoài phạm vi snapshot dữ liệu order. Owner/lifecycle của connection phải được quản lý riêng.

## 59. Bài tập 9 — Copy entity ID

Tạo order mới từ order cũ, nhưng phải có ID khác.

**Đáp án:** Nên dùng factory `duplicateAs(newId)` hoặc workflow tương đương, không copy nguyên ID rồi giả vờ hai entities khác nhau. Owned lines được copy theo business rules; shared catalog/products được xử lý theo identity semantics.

## 60. Bài tập 10 — Clone là deep?

Một class `implements Cloneable` và public `clone()` chỉ `return (X)super.clone();`, class có field `ArrayList`.

**Đáp án:** Mặc định shallow với reference field ArrayList. Cần custom copy cho những mutable state thuộc phạm vi; chỉ implements marker interface chưa đủ.

## 61. Bài tập 11 — `List.copyOf` với MutableItem

```java
List<MutableItem> x = List.copyOf(source);
```

**Đáp án:** Cấu trúc List unmodifiable; MutableItem elements vẫn cùng references. Chưa phải deep copy về mutable values.

## 62. Bài tập 12 — Record chứa array

```java
record Packet(byte[] payload) {}
```

**Đáp án:** Canonical constructor/accessor mặc định có thể giữ/lộ same mutable array reference. Nếu cần payload snapshot, clone lúc nhận và clone lúc trả; nếu cần value equality theo bytes, xử lý `equals/hashCode` phù hợp hoặc chuyển sang immutable representation khác.

## 63. Bài tập 13 — Deep copy có đồng nghĩa immutable không?

**Đáp án:** Không. Bản sao vẫn có thể sửa fields/collections của riêng nó. Deep copy bảo đảm independence theo scope; immutability bảo đảm state không thay đổi qua API/aliases tương ứng.

## 64. Bài tập 14 — Shared immutable child có phải copy mới?

Hai objects cùng trỏ `String "Java"` hoặc immutable Address record.

**Đáp án:** Không bắt buộc tạo child mới. Vì child immutable, chia sẻ không làm mutation lan từ bản này sang bản kia.

## 65. Bài tập 15 — Source bị thay đổi khi copy

Một thread mutate `ArrayList<Line>`, thread khác gọi stream để deep-copy Line, không synchronization.

**Đáp án:** Không có bảo đảm snapshot nhất quán và có thể có race. Cần dùng lock/transaction/immutable publication hoặc collection với snapshot contract phù hợp.

## 66. Bài tập 16 — Serialization JSON giữ object aliases?

Graph có root.left và root.right cùng trỏ một child. Serialize sang JSON rồi parse có chắc hai fields trỏ cùng child instance không?

**Đáp án:** Không. Hầu hết representations theo values không tự biểu diễn Java object identity. Chỉ khi schema/codec đặc biệt hỗ trợ reference tracking và được cấu hình thích hợp mới có thể giữ alias topology.

## 67. Bài tập 17 — Một mutable cache bên trong snapshot

Snapshot có derived cache, ban đầu null và có thể tính lại.

**Đáp án:** Có thể **bỏ cache khi copy** nếu cache không phải state nghiệp vụ, và để copy tự tính lại khi cần. Nếu cache được share và mutable, phải xét thread-safety và observable semantics. Không copy máy móc mọi field.

## 68. Bài tập 18 — Deep copy graph có final references và cycle

Bạn muốn clone một cyclic graph nhưng fields `next` final và constructors không cho tạo node chưa có next.

**Đáp án:** Không thể áp dụng trực tiếp thuật toán “cấp phát node trống rồi gắn edges” nếu API không cho. Cần đổi representation sang immutable IDs, builder/freeze phase hoặc factory hỗ trợ cycles; không dùng reflection phá invariants.

## 69. Bài tập 19 — Copy map có keys mutable

Map keys có `equals/hashCode` theo mutable field. Bản copy share keys.

**Đáp án:** Keys có thể đổi và làm lookup bất thường. Tốt nhất dùng immutable key types hoặc explicit copy policy với value semantics đúng.

## 70. Bài tập 20 — Giảm chi phí deep copy

Getter gọi `deepCopy()` của danh sách 100.000 nodes mỗi lần để hiển thị count.

**Đáp án:** Thiết kế API `size()`/`count()` đọc an toàn, hoặc một immutable snapshot rõ ràng khi thật sự cần. Deep-copy toàn graph cho một count là chi phí không cần thiết.

## 71. Bài tập 21 — Object graph “sao chép sâu toàn bộ” có hợp lý?

Một DTO tham chiếu `CustomerEntity`, `DataSource`, `Logger`, `Cache`, `List<Line>`.

**Đáp án:** Không thể quyết định chỉ từ độ sâu của graph. Phải đặt scope: Lines thuộc snapshot; Customer có thể giữ ID; DataSource/Logger/Cache là dependencies nên không tự deep-copy. Kết quả phụ thuộc ownership và use case.

## 72. Checklist review deep copy

1. Đã viết rõ **mục tiêu copy**: snapshot, working copy hay duplicate entity?
2. Đã xác định **root identity** có thay không?
3. Những field nào thuộc **data payload**, những field nào là dependency?
4. Có mutable descendants nào caller vẫn giữ alias không?
5. Mọi mutable part thuộc scope có được copy độc lập không?
6. Có thể chia sẻ immutable values như `String`/`Instant`/immutable records không?
7. Có copy sai external resources/locks/connections không?
8. Nếu là List/Map, đã copy **outer structure** và những mutable elements/values cần copy chưa?
9. Nếu `int[][]`, đã xử lý inner arrays và possible null rows chưa?
10. Có shared aliases giữa nhiều edges không?
11. Contract có cần bảo toàn **alias topology** không?
12. Có cycles cần memo map original→copy không?
13. Memo map có sử dụng **reference identity** khi phù hợp không?
14. Có cấp phát copy node trước khi đệ quy để tránh cycle không?
15. Copy có thể gặp subclasses mà base constructor không bao phủ fields không?
16. `clone()` có đang chỉ shallow-copy references không?
17. Có record với arrays/collections không được copy đủ không?
18. Entity IDs và JPA lifecycle có được xử lý theo business rule không?
19. Dữ liệu có thể mutate **trong lúc copy** không?
20. Cần snapshot nhất quán ở monitor/transaction boundary nào?
21. Bản sao có immutable theo API hay vẫn mutable?
22. Getter của snapshot có lộ mutable internals không nếu yêu cầu immutable?
23. Có xác định null/empty policy không?
24. Có test sửa original sau copy và sửa copy sau đó không?
25. Có test alias/cycle/subtype-specific fields không?
26. Có test value equality/hashCode nếu copy sẽ dùng làm map key không?
27. Có giới hạn depth/size hoặc bảo vệ recursion stack cho graph lớn không?
28. Chi phí copy có phù hợp frequency/độ lớn dữ liệu không?
29. Một DTO immutable/structural sharing có giúp đơn giản hóa không?
30. Tên API/tài liệu đã nói rõ *những gì thực sự được sao chép* chưa?

## Ghi nhớ

**Deep copy trong Java không có nghĩa “copy mọi thứ object có thể trỏ tới”.** Nó là việc tạo representation độc lập cho **phần dữ liệu mutable đã xác định thuộc phạm vi copy**.

- Gán reference không copy object; `new` một outer object có thể vẫn chỉ là **shallow copy**.
- Array một chiều primitive thường copy đủ bằng `clone`; array references, multi-dimensional arrays, collections và nested classes cần xem các mutable tầng sâu.
- `List.copyOf`/`Map.copyOf` tạo unmodifiable outer structures, **không tự copy sâu elements**.
- Share immutable leaves là an toàn; copy resources/shared dependencies mù quáng thường sai.
- Shared aliases và cycles cần chính sách rõ. Nếu phải giữ graph topology, dùng **identity memoization** như `IdentityHashMap` và memoize node trước khi copy edges.
- Copy constructor, `clone`, factory `copyOf`, DTO mapping và serialization **không tự định nghĩa copy depth**. Cần thiết kế theo từng domain.
- Phân biệt **snapshot cùng identity** với **duplicate entity identity mới**, và **deep copy** với **deep immutability**.
- Under concurrency, snapshot phải được đọc từ state nhất quán; copy đúng graph không tự làm concurrent reads atomic.
- Kiểm chứng bằng **value equivalence, mutation independence, alias/cycle preservation, resource policy và performance**.

Một bản sao đúng không nhất thiết có nhiều objects mới nhất, mà là **bản sao giữ đúng giá trị và quan hệ cần giữ, đồng thời tách đúng những thay đổi cần được độc lập**.
