# Kiểm thử bản sao có cùng giá trị và dữ liệu thành phần lồng nhau trong record (Java 16+)

## 1. “Bản sao có cùng giá trị” nghĩa là gì?

Một `record` là lớp dữ liệu mà các thành phần (*record components*) được công bố ngay trong phần đầu khai báo. Từ **Java 16**, record là tính năng ngôn ngữ chính thức, không cần preview. Ví dụ:

```java
record Position(int x, int y) {}
```

Khi dùng `new Position(3, 5)` hai lần, ta nhận được hai đối tượng riêng biệt. Tuy nhiên, các phương thức `equals()` và `hashCode()` do trình biên dịch sinh ra so sánh **giá trị các component**, nên hai đối tượng có cùng `x` và `y` được xem là **bằng nhau về giá trị**.

```java
// Đoạn minh họa trong thân phương thức:
Position first = new Position(3, 5);
Position second = new Position(3, 5);

System.out.println(first == second);      // false: không cùng tham chiếu
System.out.println(first.equals(second)); // true: cùng giá trị component
```

Phải phân biệt ba khái niệm:

- **Cùng đối tượng (`==`):** hai biến tham chiếu tới đúng một instance. `new` hai lần thường tạo hai instance khác nhau.
- **Bằng nhau về giá trị (`equals`):** record mặc định so sánh từng component theo kiểu của component và quy tắc `equals`/so sánh nguyên thủy tương ứng.
- **Sao chép cấu trúc bên trong (*deep copy*):** tạo các instance con mới khi cần. Hai record có thể `equals` nhau **mà không có deep copy**, vì `equals` không có nhiệm vụ sao chép đối tượng.

**Trọng tâm của bài:** kiểm thử bản sao record bằng `equals`, tính nhất quán `hashCode`, trạng thái của **component lồng nhau** (record chứa record, danh sách chứa record, danh sách lồng danh sách), và khả năng bảo vệ giá trị trước dữ liệu mutable.

## 2. Quy tắc sao chép (copy invariant) của record

Quy tắc quan trọng trong đặc tả Java:

> Với record `R(c1, c2, ..., cn)`, nếu lấy các giá trị qua accessor của đối tượng `r` rồi truyền vào canonical constructor để tạo một `R` mới, bản sao phải bằng đối tượng ban đầu theo `equals`.

```java
// Minh họa cho một record R có hai component.
R copy = new R(original.c1(), original.c2());
boolean sameValue = original.equals(copy); // phải là true
```

`R` ở đây chỉ là **ký hiệu minh họa**, không phải tên lớp đã định nghĩa. Với `record Position(int x, int y)` thực tế:

```java
Position original = new Position(3, 5);
Position copy = new Position(original.x(), original.y());

System.out.println(original.equals(copy));           // true
System.out.println(original.hashCode() == copy.hashCode()); // true
System.out.println(original == copy);                  // false
```

Quy tắc này vẫn có ý nghĩa khi record có component là object hoặc collection. Nhưng **“copy” ở đây là dựng đối tượng mới từ các giá trị accessor**, không cam kết mọi object nằm sâu bên trong sẽ được clone.

Nếu tự viết lại **accessor**, **canonical constructor** hoặc **equals`/`hashCode**, trách nhiệm duy trì quy tắc copy invariant thuộc về người viết. Trình biên dịch không thể tự chứng minh mọi tùy biến đều đúng.

### Những khẳng định test cần và không nên dùng

| Kiểm tra | Kết quả mong muốn | Lý do |
| --- | --- | --- |
| `original.equals(copy)` | `true` nếu component tương đương | Kiểm tra bình đẳng giá trị/copy invariant |
| `original.hashCode() == copy.hashCode()` | `true` khi `equals` bằng nhau | Hợp đồng `equals`/`hashCode` |
| `original == copy` | `false` khi tạo mới hai instance | Phân biệt danh tính đối tượng |
| `original.items().equals(copy.items())` | `true` khi phần tử có giá trị tương đương | `List.equals` so sánh phần tử có thứ tự |
| `original.items() == copy.items()` | **Không nên mặc định đòi `false`** | Các bản sao có thể chia sẻ danh sách immutable an toàn |
| `a.hashCode() != b.hashCode()` khi `!a.equals(b)` | **Không được đòi hỏi** | Hash collision có thể xảy ra hợp lệ |

Đối với hai record bằng nhau, hash code **bắt buộc tương đương**; chiều ngược lại không đúng.

## 3. Dữ liệu lồng nhau: `equals` thực sự so sánh những gì?

Giả sử mô hình có record chứa danh sách record; mỗi record con lại chứa danh sách tag:

```java
record Item(String sku, List<String> tags) {}
record Order(String orderId, List<Item> items) {}
```

Trong ví dụ trên, `Order.equals` do compiler sinh ra so sánh:

1. `orderId` qua ngữ nghĩa bình đẳng của `String`.
2. `items` qua ngữ nghĩa `List.equals`: hai danh sách phải có cùng số phần tử, **đúng thứ tự**, và mỗi phần tử ở vị trí tương ứng phải bằng nhau.
3. Mỗi `Item` lại so sánh `sku` và `tags` theo ngữ nghĩa của các component của nó.
4. `tags` có kiểu `List<String>`, nên so sánh các chuỗi theo thứ tự.

Do vậy, một `Order` xây lại với **các instance `Item` mới nhưng có cùng giá trị** vẫn có thể `equals` bản gốc. Đây là so sánh lồng qua các phương thức `equals` của kiểu component. Nó **không phải** một phép “deep equals” tự động cho mọi kiểu dữ liệu trong Java.

Một số trường hợp phải phân biệt:

- **Record lồng record:** record con dùng `equals` của chính nó, sau đó record cha dùng kết quả này.
- **`List` / `Map` / `Set`:** dùng hợp đồng bình đẳng của collection tương ứng. `List` phụ thuộc thứ tự; `Set` và `Map` không dựa trên thứ tự duyệt để xác định equality.
- **Array (`int[]`, `String[]`):** mảng Java **không ghi đè `Object.equals`** để so sánh nội dung; record mặc định so sánh component mảng bằng **danh tính tham chiếu**. Hai mảng khác nhau có cùng phần tử vẫn có thể khiến hai record **không bằng nhau**.
- **Object mutable tự định nghĩa:** record dùng `equals` của object đó. Nếu object không định nghĩa equality theo giá trị, kết quả có thể phụ thuộc tham chiếu; nếu object bị sửa, kết quả equality của record cha cũng có thể đổi.

**Hệ quả khi kiểm thử:** không suy luận “nested means recursively value-equal” theo cảm tính. Xác định kiểu component ở từng tầng và cách `equals` của mỗi tầng hoạt động.

## 4. Chương trình Java 17+ hoàn chỉnh: kiểm thử bản sao, dữ liệu lồng nhau và mảng

Tạo tệp **`RecordCopyValueDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class RecordCopyValueDemo {
    public record Item(String sku, List<String> tags) {
        public Item {
            sku = Objects.requireNonNull(sku, "sku").strip();
            if (sku.isEmpty()) {
                throw new IllegalArgumentException("sku rỗng");
            }
            tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
        }
    }

    public record Order(String orderId, List<Item> items) {
        public Order {
            orderId = Objects.requireNonNull(orderId, "orderId").strip();
            if (orderId.isEmpty()) {
                throw new IllegalArgumentException("orderId rỗng");
            }
            items = List.copyOf(Objects.requireNonNull(items, "items"));
            if (items.isEmpty()) {
                throw new IllegalArgumentException("thiếu item");
            }
        }
    }

    // Sao chép cả danh sách ngoài và từng danh sách con.
    public record Groups(List<List<String>> groups) {
        public Groups {
            Objects.requireNonNull(groups, "groups");
            groups = groups.stream()
                    .map(group -> List.copyOf(
                            Objects.requireNonNull(group, "group")))
                    .toList();
        }
    }

    // Chỉ sao chép danh sách ngoài: vẫn để lộ danh sách con mutable.
    public record ShallowGroups(List<List<String>> groups) {
        public ShallowGroups {
            groups = List.copyOf(groups);
        }
    }

    // Dùng để chứng minh record chứa mảng không tự so sánh nội dung.
    public record ArrayBox(int[] data) { }

    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        List<String> tagsInput =
                new ArrayList<>(List.of("gift", "priority"));
        List<Item> itemsInput = new ArrayList<>();
        itemsInput.add(new Item("  SKU-1  ", tagsInput));
        Order original = new Order(" ORD-9 ", itemsInput);

        // Copy invariant: dùng trực tiếp các accessor.
        Order copied = new Order(original.orderId(), original.items());

        // Tạo mới cả các Item lồng nhau, vẫn cùng giá trị.
        Order rebuilt = new Order(original.orderId(),
                original.items().stream()
                        .map(item -> new Item(item.sku(), item.tags()))
                        .toList());

        check(original.equals(copied), "copy invariant");
        check(original.equals(rebuilt), "nested values equality");
        check(original.hashCode() == rebuilt.hashCode(), "hash contract");
        check(original != rebuilt, "different instances");
        check(original.items().get(0) != rebuilt.items().get(0),
                "nested copied instance");

        System.out.println("copyEqual=" + original.equals(copied));
        System.out.println("rebuiltEqual=" + original.equals(rebuilt));
        System.out.println("sameReference=" + (original == rebuilt));
        System.out.println("hashConsistent=" +
                (original.hashCode() == rebuilt.hashCode()));

        // Sửa đầu vào sau khi tạo record.
        tagsInput.add("changed");
        itemsInput.clear();
        check(original.items().size() == 1, "outer stable");
        check(original.items().get(0).tags()
                .equals(List.of("gift", "priority")), "inner stable");
        System.out.println("stableTags=" +
                original.items().get(0).tags());

        List<String> inner = new ArrayList<>(List.of("A"));
        List<List<String>> outer = new ArrayList<>();
        outer.add(inner);
        Groups nested = new Groups(outer);
        Groups nestedCopy = new Groups(nested.groups());
        ShallowGroups shallow = new ShallowGroups(outer);
        ShallowGroups shallowSnapshot =
                new ShallowGroups(List.of(List.of("A")));

        inner.add("B");
        outer.clear();

        check(nested.equals(nestedCopy), "deep collection copy");
        check(nested.groups().get(0)
                .equals(List.of("A")), "nested immutable");
        check(shallow.groups().get(0)
                .equals(List.of("A", "B")), "shallow mutation");
        check(!shallow.equals(shallowSnapshot),
                "shallow equality drift");

        System.out.println("deepCopyRows=" + nested.groups());
        System.out.println("shallowRows=" + shallow.groups());
        System.out.println("shallowStillEqual=" +
                shallow.equals(shallowSnapshot));

        ArrayBox array1 = new ArrayBox(new int[] {1, 2});
        ArrayBox array2 = new ArrayBox(new int[] {1, 2});

        check(Arrays.equals(array1.data(), array2.data()),
                "array content");
        check(!array1.equals(array2), "array identity");
        check(array1.equals(new ArrayBox(array1.data())),
                "array copy invariant");

        System.out.println("arrayContentEqual=" +
                Arrays.equals(array1.data(), array2.data()));
        System.out.println("arrayRecordEqual=" +
                array1.equals(array2));
        System.out.println("arrayCopyInvariant=" +
                array1.equals(new ArrayBox(array1.data())));
    }
}
```

**Chạy bằng JDK 17 trở lên:**

```bash
javac --release 17 -encoding UTF-8 RecordCopyValueDemo.java
java RecordCopyValueDemo
```

`--release 17` kiểm tra mã theo Java 17. Những tính năng được dùng (`record`, `List.copyOf`, `Stream.toList`) đã chính thức trong hoặc trước phiên bản này. Không cần cờ preview.

**Đầu ra chính xác của chương trình:**

```text
copyEqual=true
rebuiltEqual=true
sameReference=false
hashConsistent=true
stableTags=[gift, priority]
deepCopyRows=[[A]]
shallowRows=[[A, B]]
shallowStillEqual=false
arrayContentEqual=true
arrayRecordEqual=false
arrayCopyInvariant=true
```

Hàm `check` ném `AssertionError` nếu điều kiện sai, nên chương trình **kiểm tra thực sự**, kể cả khi chạy `java` mà không thêm `-ea`. Các lệnh in giúp xem kết quả; phép kiểm tra mới là phần xác định thành công/thất bại.

## 5. Phân tích từng nhóm kiểm thử

### 5.1. Bản sao trực tiếp và bản xây lại ở nhiều tầng

`copied = new Order(original.orderId(), original.items())` là phép dựng bản sao theo đúng các accessor của record. `original.equals(copied)` phải trả `true`.

`rebuilt` còn tái tạo từng `Item`:

```java
Order rebuilt = new Order(original.orderId(),
        original.items().stream()
                .map(item -> new Item(item.sku(), item.tags()))
                .toList());
```

Hai đối tượng `Order` có **tham chiếu khác nhau**; hai `Item` tương ứng cũng được khởi tạo riêng. Nhưng chúng có cùng `orderId`, cùng danh sách các `Item` có dữ liệu tương đương, nên **`equals` trả `true`**.

`hashConsistent=true` chỉ kiểm tra hợp đồng bắt buộc: **nếu `a.equals(b)` thì `a.hashCode() == b.hashCode()`**. Không kiểm tra hash phải khác khi giá trị khác: có thể xảy ra va chạm băm.

**Đừng nhầm:** phương thức `List.copyOf` trong constructor `Order` có thể tái sử dụng một danh sách đã unmodifiable; không có bảo đảm rằng `original.items() != copied.items()`. Bài test chỉ đòi các **giá trị** đúng. Nếu yêu cầu dữ liệu thật sự phải nằm trong các instance khác nhau, phải có hợp đồng copy riêng và kiểm tra đúng cấp cần thiết.

### 5.2. Vì sao bản sao lồng nhau vẫn giữ giá trị sau khi sửa input?

`Item` tự làm `tags = List.copyOf(tags)`; `Order` tự làm `items = List.copyOf(items)`. Sau đó:

```java
tagsInput.add("changed");
itemsInput.clear();
```

Các thao tác này chỉ sửa hai danh sách mutable **do bên gọi giữ**, không sửa trạng thái đã lưu trong `Item` và `Order`. Đây là một test về **bảo vệ alias (aliasing)**: cùng một đối tượng đầu vào không được phép thay đổi record sau khi constructor đã hoàn thành.

Trong ví dụ, `String` bất biến và `Item` không có trạng thái ẩn mutable, nên các tầng được bảo vệ đầy đủ. Trường hợp thay `List<String>` bằng `List<MutableCustomer>` thì `List.copyOf` **chỉ chụp danh sách**, không tự biến mỗi `MutableCustomer` thành immutable.

### 5.3. Vì sao `Groups` ổn định nhưng `ShallowGroups` thay đổi?

`Groups` sao chép **mỗi danh sách con** bằng `List.copyOf` và thu kết quả vào một danh sách ngoài unmodifiable bằng `Stream.toList`:

```java
groups = groups.stream()
        .map(group -> List.copyOf(
                Objects.requireNonNull(group, "group")))
        .toList();
```

`ShallowGroups` chỉ `List.copyOf(groups)`. Điều đó ngăn thêm/xóa phần tử khỏi danh sách ngoài của record, **nhưng không ngăn `inner.add("B")`**, vì phần tử `inner` vẫn là `ArrayList` mutable ban đầu.

Kết quả:

- `nested.groups()` của `Groups` giữ nguyên `[[A]]`, dù `inner` đổi thành `[A, B]` và danh sách ngoài nguồn bị xóa.
- `shallow.groups()` đổi từ `[[A]]` thành `[[A, B]]` sau khi bên ngoài sửa `inner`.
- `shallow.equals(shallowSnapshot)` **ban đầu bằng nhau**, nhưng sau sửa `inner` sẽ thành `false`.

Đây là lý do phải kiểm thử cả **danh sách ngoài** lẫn **đối tượng/danh sách ở những tầng sâu hơn**. Với dữ liệu cây hoặc đồ thị phức tạp, cần chính sách copy theo từng kiểu thành phần và theo đúng miền dữ liệu; không có phép `List.copyOf` nào tự deep-copy toàn bộ object graph.

### 5.4. Record chứa mảng: bản sao “cùng nội dung” chưa chắc `equals`

`ArrayBox` có component là `int[]`. Hai mảng `new int[]{1,2}` là hai object khác nhau:

```java
ArrayBox a = new ArrayBox(new int[] {1, 2});
ArrayBox b = new ArrayBox(new int[] {1, 2});

System.out.println(Arrays.equals(a.data(), b.data())); // true
System.out.println(a.equals(b));                        // false
```

`Arrays.equals` so sánh phần tử `int`, còn `equals` mặc định của mảng là so sánh tham chiếu. Record mặc định sử dụng ngữ nghĩa `equals` của component tham chiếu, nên `a.equals(b)` là `false` dù **nội dung hai mảng giống nhau**.

Trong khi đó, nếu viết `new ArrayBox(a.data())` thì component của hai record trỏ **đúng cùng một mảng**, khiến `a.equals(new ArrayBox(a.data()))` là `true`. Điều này thỏa copy invariant nhưng **không bảo vệ khỏi việc mảng bị sửa từ bên ngoài**.

Nếu cần record mang dữ liệu mảng theo giá trị:

1. Cân nhắc dùng kiểu collection/value object bất biến có equality phù hợp với dữ liệu trước khi đặt làm component.
2. Nếu vẫn dùng mảng, copy tại constructor và khi trả qua accessor; cân nhắc tự cài đặt `equals`/`hashCode` theo `Arrays.equals`/`Arrays.hashCode` **một cách nhất quán**.
3. Kiểm tra kỹ copy invariant với accessor tùy chỉnh; tránh tạo ra record có bản sao từ accessor nhưng lại `equals` khác bản gốc.

Lưu ý: `Arrays.deepEquals` chỉ thích hợp cho các mảng đối tượng lồng nhau trong ngữ cảnh phù hợp; không tự động thay thế yêu cầu thiết kế equality cho mọi kiểu component.

## 6. Phạm vi bất biến của record và tác động tới test

Java tạo các trường component dạng `private final`. **`final` cố định tham chiếu được lưu, không làm những object được tham chiếu trở thành bất biến sâu.** Chẳng hạn:

```java
record UnsafeContainer(List<List<String>> values) {}
```

Chỉ riêng khai báo record trên không ngăn việc sửa danh sách ngoài hoặc danh sách con. Với dữ liệu lồng nhau, test cần chứng minh những điều kiện cụ thể:

- **Không thay đổi sau khi xây:** sửa danh sách nguồn hoặc một object con do caller giữ; nội dung record không đổi nếu bất biến là hợp đồng mong muốn.
- **Không sửa qua accessor:** thử sửa collection trả về. Nếu accessor trả danh sách unmodifiable, thao tác cấu trúc phải bị từ chối; nếu trả một bản sao mutable, sửa bản sao không được ảnh hưởng record.
- **Giá trị copy không đổi:** `original.equals(copy)` phải tiếp tục đúng sau các thao tác với nguồn bên ngoài, nếu component đã được cách ly đúng.
- **Hash ổn định khi dùng làm key:** nếu record dùng làm key của `HashMap`/`HashSet`, mutation của component có thể khiến vị trí hash không còn phù hợp và tra cứu có thể thất bại. Test bằng bản sao tương đương để kiểm chứng.
- **Không đòi hỏi copy sâu vô điều kiện:** nếu mọi component bên trong đã bất biến, chia sẻ tham chiếu giữa bản gốc và bản sao **không gây rủi ro thay đổi nội dung**. Việc tạo lại toàn bộ đồ thị đối tượng là quyết định riêng của ứng dụng.

Ví dụ kết hợp với `HashSet` (đoạn đặt trong phương thức có `original`, `rebuilt` kiểu `Order` của ví dụ chính):

```java
java.util.Set<Order> keys = new java.util.HashSet<>();
keys.add(original);
System.out.println(keys.contains(rebuilt)); // true, vì equals/hashCode nhất quán
```

Tránh kiểm thử “hash code giữa các đối tượng khác giá trị phải khác nhau”. Yêu cầu đúng là **các đối tượng bằng nhau phải có cùng hash**; hash khác nhau không phải điều kiện cần của `!equals`.

## 7. Chuyển các kiểm tra thành unit test JUnit Jupiter

Trong dự án có dependency **JUnit Jupiter**, có thể viết các ca kiểm thử tự động sau. Đoạn dưới giả định `RecordCopyValueDemo` đã nằm trong cùng package hoặc được import phù hợp. Đây là **một lớp test dùng với JUnit**, không phải mã chạy chỉ bằng `javac` của JDK thuần:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;

class RecordCopyValueTest {
    @Test
    void copyFromComponentsKeepsValue() {
        var first = new RecordCopyValueDemo.Order(
                "O-1",
                List.of(new RecordCopyValueDemo.Item(
                        "SKU-1", List.of("gift"))));

        var copy = new RecordCopyValueDemo.Order(
                first.orderId(), first.items());

        assertNotSame(first, copy);
        assertEquals(first, copy);
        assertEquals(copy, first);
        assertEquals(first.hashCode(), copy.hashCode());
    }

    @Test
    void nestedRecordsCompareByValue() {
        var first = new RecordCopyValueDemo.Order(
                "O-1",
                List.of(new RecordCopyValueDemo.Item(
                        "SKU-1", List.of("gift"))));

        var rebuilt = new RecordCopyValueDemo.Order(
                first.orderId(),
                first.items().stream()
                        .map(item -> new RecordCopyValueDemo.Item(
                                item.sku(), item.tags()))
                        .toList());

        assertNotSame(first.items().get(0), rebuilt.items().get(0));
        assertEquals(first, rebuilt);
    }

    @Test
    void nestedCollectionCannotChangeThroughSource() {
        var nestedSource = new ArrayList<>(List.of("A"));
        var original = new RecordCopyValueDemo.Groups(
                List.of(nestedSource));
        var copy = new RecordCopyValueDemo.Groups(
                original.groups());

        nestedSource.add("B");

        assertEquals(List.of(List.of("A")), original.groups());
        assertEquals(original, copy);
        assertThrows(UnsupportedOperationException.class,
                () -> original.groups().get(0).add("C"));
    }

    @Test
    void arraysNeedExplicitContentComparison() {
        var first = new RecordCopyValueDemo.ArrayBox(
                new int[] {1, 2});
        var second = new RecordCopyValueDemo.ArrayBox(
                new int[] {1, 2});

        assertTrue(Arrays.equals(first.data(), second.data()));
        assertNotEquals(first, second);
        assertEquals(first,
                new RecordCopyValueDemo.ArrayBox(first.data()));
    }
}
```

Test này kiểm tra các hợp đồng quan trọng: **copy bằng accessor**, **đối tượng lồng có giá trị tương đương**, **bảo vệ khỏi mutation** và **ngoại lệ mảng**. Chỉ chạy khi dự án đã cấu hình JUnit Jupiter và test task tương ứng; không có thư viện JUnit trong JDK mặc định.

Trong dự án lớn, nên bổ sung các test bao phủ `null`, danh sách rỗng, phần tử `null`, thứ tự danh sách bị đảo, dữ liệu lồng ở nhiều cấp và case có component object mutable. Các test này cần được xác định từ **invariant nghiệp vụ**, không chỉ từ chữ ký record.

## 8. Khi tự định nghĩa accessor/`equals`: đừng phá copy invariant

Hầu hết record dữ liệu nên dùng `equals` và `hashCode` mặc định. Nếu tự viết accessor chuyển đổi giá trị hoặc giấu bớt component, bản sao qua accessor có thể **không còn bằng** bản gốc:

```java
// Ví dụ không nên áp dụng: accessor không trả component thực tế.
record Clipped(int score) {
    @Override
    public int score() {
        return Math.min(score, 100);
    }
}

// Đặt trong thân phương thức:
Clipped original = new Clipped(150);
Clipped copied = new Clipped(original.score()); // score thành 100
System.out.println(original.equals(copied));   // false
```

Vì `equals` mặc định dựa trên **component field thực tế**, không phải việc gọi accessor có biến đổi, `original` chứa `150` nhưng `copied` chứa `100`. Đây là **vi phạm tinh thần copy invariant** của record và khiến client khó dự đoán.

**Thiết kế đúng hơn:** nếu invariant yêu cầu `score <= 100`, hãy chuẩn hóa hoặc từ chối đầu vào **trong canonical constructor** để field luôn hợp lệ ngay từ khi tạo:

```java
record Clamped(int score) {
    public Clamped {
        score = Math.min(score, 100);
    }
}
```

Với `Clamped`, accessor do compiler sinh trả chính component đã chuẩn hóa, nên bản sao từ accessor bằng bản gốc. Đặt quy tắc chuẩn hóa tại điểm tạo còn giúp `hashCode` và equality không đổi vì dữ liệu được giữ nhất quán.

Nếu bắt buộc tự định nghĩa `equals`/`hashCode` cho một component đặc biệt, hãy kiểm thử đồng thời **phản xạ, đối xứng, bắc cầu, nhất quán, xử lý `null`, hash contract** và đặc biệt là **copy invariant** của record.

## 9. Checklist kiểm thử thực hành

| Ca kiểm thử | Cách thực hiện | Tiêu chí đạt |
| --- | --- | --- |
| Copy bằng accessor | `new R(original.c1(), ... original.cn())` | `equals` true, hash bằng nhau |
| Khác instance | Tạo hai lần `new` | `==` false nếu cần xác định instance mới |
| Copy record con | Dựng lại mỗi component kiểu record lồng | Cha và con đều `equals` theo giá trị |
| Collection cùng dữ liệu | Tạo `List` với phần tử tương đương, đúng thứ tự | `equals` true |
| Collection khác thứ tự | Đảo phần tử danh sách có nhiều phần tử khác nhau | `List.equals` false khi thứ tự có ý nghĩa |
| Thay dữ liệu nguồn | Sửa collection mutable sau constructor | Record giữ invariant nếu đã copy đúng |
| Sửa qua accessor | Thêm/xóa phần tử ở danh sách nhận từ accessor | Bị từ chối hoặc không ảnh hưởng record |
| List nhiều tầng | Sửa danh sách con sau `List.copyOf` chỉ ở outer | Test phát hiện mutable alias; dùng defensive copy từng tầng |
| Array cùng phần tử | Hai instance mảng độc lập nhưng bằng nội dung | `Arrays.equals` true; record default `equals` có thể false |
| Custom constructor/accessor | Tạo bản sao từ accessor khi có chuẩn hóa | Copy invariant vẫn true |
| Dùng làm hash key | Cho `original` vào `HashSet` và tìm bằng bản sao tương đương | `contains(copy)` true nếu state ổn định |
| Input không hợp lệ | Dùng null/giá trị sai quy tắc | Validation từ chối, không trả về record hợp lệ |

**Các lỗi hay gặp:**

1. Chỉ kiểm tra `==` rồi kết luận hai bản sao record “khác dữ liệu”.
2. Chỉ kiểm tra `toString()` (hoặc định dạng chuỗi của record) thay vì `equals` và từng component quan trọng.
3. Dùng `assertNotEquals(hashA, hashB)` cho hai record khác giá trị; điều này không phải hợp đồng `hashCode`.
4. Gọi `List.copyOf` cho danh sách ngoài rồi tưởng rằng nó deep-copy mọi phần tử bên trong.
5. So sánh hai mảng cùng nội dung trong record rồi kỳ vọng `equals` tự dùng `Arrays.equals`.
6. Dùng record làm key trong map/set khi component chứa dữ liệu mutable có thể thay đổi sau khi chèn.
7. Sửa accessor để trả dữ liệu khác component thực tế, khiến phép copy qua accessor vi phạm invariant.
8. Dùng unit test dựa trên thứ tự không được API bảo đảm (chẳng hạn kiểm tra thứ tự của `HashMap`) hoặc danh tính của danh sách immutable do `List.copyOf` tạo.

## 10. Tóm tắt quy tắc thiết kế

Một record có thể là **value carrier đáng tin cậy** khi:

- Các component mô tả trọn vẹn trạng thái cần so sánh; không có state ẩn thay đổi ngầm.
- Component lồng nhau có equality đúng với nghiệp vụ (record con, `List`, `Map`, hoặc value type phù hợp).
- Dữ liệu mutable được cách ly tại đúng tầng, dùng loại component bất biến hoặc defensive copy thích hợp.
- Canonical constructor và accessor giữ **copy invariant**; `equals`/`hashCode` giữ hợp đồng.
- Bộ test bao gồm copy trực tiếp bằng accessor, bản dựng lại nhiều tầng, khác danh tính, cùng hash khi equals, và thử thay đổi input sau khởi tạo.

**Câu hỏi tự kiểm tra:**

1. **Hai `Order` có các `Item` khác instance nhưng cùng `sku`/`tags` có bằng nhau không?** Có, khi `Order` và `Item` dùng equality mặc định theo component và `List` giữ đúng thứ tự, giá trị.
2. **Vì sao `List.copyOf` danh sách ngoài chưa đủ?** Vì phần tử bên trong có thể là `ArrayList` hoặc object mutable; thay đổi chúng làm dữ liệu được quan sát từ record thay đổi.
3. **Vì sao hai `ArrayBox` có hai `int[] {1,2}` lại không bằng nhau theo record mặc định?** Vì equality của mảng dựa trên tham chiếu. Muốn so sánh nội dung cần thiết kế equality/component khác.
4. **Khi record dùng làm key, test quan trọng nhất là gì?** Bản sao cùng giá trị có `equals` và `hashCode` nhất quán, đồng thời trạng thái dùng tính hash không bị sửa từ ngoài sau khi chèn.

### Tài liệu chính thức

- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): record chính thức từ Java 16, thiết kế record như đối tượng dữ liệu minh bạch.
- [Java Language Specification — Record Classes, `8.10](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10): ngữ nghĩa `equals`/`hashCode` của component, copy invariant và accessor.
- [Java SE 25 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html): hợp đồng public API, copy invariant.
- [Dev.java — Using Records to Model Immutable Data](https://dev.java/learn/records/): khai báo component, canonical/compact constructor, defensive copy và accessor.
- [Java SE 25 API — `List.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable collection và null handling.
