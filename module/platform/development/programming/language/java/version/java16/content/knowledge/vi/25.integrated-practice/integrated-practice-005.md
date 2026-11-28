# Thiết kế bộ kiểm thử hồi quy cho equality, null và collection unmodifiable

Một bộ kiểm thử hồi quy tốt phải xác nhận các hợp đồng quan sát được của ứng dụng: hai value object có dữ liệu tương đương phải được xem là bằng nhau, giá trị `null` được xử lý theo quy tắc đã chọn, và collection không sửa đổi được phải từ chối thao tác thay đổi. Với Java hiện đại, record tự sinh `equals()`/`hashCode()`, pattern matching cho `instanceof` giúp kiểm tra kiểu an toàn với `null`, còn các API như `List.of()`, `List.copyOf()` và `Stream.toList()` có những hợp đồng bất biến khác nhau.

Không nên gom tất cả các collection này thành một khái niệm “immutable” rồi viết một assertion chung. `List.copyOf()` tạo một snapshot không sửa đổi được; `Collections.unmodifiableList()` là view không sửa đổi được của một list khác; `Stream.toList()` trả về list không sửa đổi được nhưng cho phép phần tử `null`; `Collectors.toUnmodifiableList()` thì từ chối phần tử `null`. Bộ test phải ghi rõ những khác biệt này để phát hiện regression mà không phụ thuộc vào implementation class.

Bài học thuộc chương **Thực hành tổng hợp** của module **JAVA_VERSION_JAVA16**. Nội dung kết hợp record, pattern matching cho `instanceof` và Stream API được chuẩn hóa trong Java 16 với các collection factory/copy API vẫn dùng trong JDK hiện đại. Ví dụ kiểm thử dùng JUnit Jupiter 5; các assertion dựa trên hợp đồng API công khai, không dựa vào chi tiết triển khai nội bộ.

## 1. Xác định hợp đồng cần bảo vệ

Trước khi viết test, ghi rõ hành vi mà ứng dụng cam kết:

| Nhóm | Hợp đồng cần kiểm tra | Regression có thể phát hiện |
| --- | --- | --- |
| Equality | Reflexive, symmetric, transitive, consistent; `null` không bằng object | Record/class thay đổi component hoặc implementation `equals()` sai |
| Hash code | Hai object bằng nhau phải có cùng `hashCode()` | Key bị mất trong `HashMap`/`HashSet` sau khi sửa value semantics |
| Null | Constructor/API từ chối hoặc chấp nhận `null` đúng theo thiết kế | `NullPointerException` xuất hiện sai thời điểm hoặc dữ liệu null lọt vào domain |
| Pattern matching | `instanceof` với `null` cho kết quả `false`; pattern variable chỉ dùng khi match thành công | Nhánh xử lý null hoặc kiểu không mong đợi bị thay đổi |
| Unmodifiable collection | Mutator ném `UnsupportedOperationException` | API vô tình trả collection có thể sửa đổi |
| Snapshot/view | Thay đổi nguồn có hoặc không ảnh hưởng kết quả đúng theo API được chọn | Dùng nhầm wrapper view thay cho snapshot hoặc ngược lại |
| Null trong collection | Factory/collector có chính sách null riêng | Chuyển đổi API làm thay đổi việc chấp nhận phần tử null |

Nên tách test theo hợp đồng nhỏ. Khi test thất bại, tên test cần chỉ ra hành vi bị vi phạm thay vì chỉ nói chung chung “collection test failed”.

## 2. Kiểm thử hợp đồng equals() và hashCode()

Theo hợp đồng của `Object.equals()`:

- **Reflexive:** `x.equals(x)` luôn là `true`.
- **Symmetric:** nếu `x.equals(y)` là `true` thì `y.equals(x)` cũng phải là `true`.
- **Transitive:** nếu `x.equals(y)` và `y.equals(z)` là `true` thì `x.equals(z)` phải là `true`.
- **Consistent:** kết quả không thay đổi giữa các lần gọi nếu dữ liệu dùng để so sánh không đổi.
- Với object khác `null`, `x.equals(null)` phải là `false`.

Quy tắc `hashCode()` đi kèm: nếu hai object bằng nhau theo `equals()`, chúng phải có cùng hash code. Hai object không bằng nhau vẫn có thể trùng hash code; do đó không viết test yêu cầu hash code luôn khác nhau.

### Record và equality theo component

Record tự sinh `equals()` và `hashCode()` dựa trên các record component. Ví dụ:

~~~java
record Customer(String id, String name) {
    Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
    }
}
~~~

Hai instance `Customer` độc lập nhưng có cùng `id` và `name` sẽ bằng nhau. Test nên xác nhận cả equality trực tiếp lẫn hành vi khi dùng record làm key trong collection:

~~~java
@Test
void recordEqualityAndHashCodeFollowComponents() {
    Customer first = new Customer("C-01", "An");
    Customer sameValue = new Customer("C-01", "An");
    Customer different = new Customer("C-02", "An");

    assertNotSame(first, sameValue);
    assertEquals(first, sameValue);
    assertEquals(first.hashCode(), sameValue.hashCode());
    assertNotEquals(first, different);

    Set<Customer> customers = new HashSet<>();
    customers.add(first);
    customers.add(sameValue);
    assertEquals(1, customers.size());

    Map<Customer, String> lookup = new HashMap<>();
    lookup.put(first, "active");
    assertEquals("active", lookup.get(sameValue));
}
~~~

### Kiểm tra các thuộc tính của equality

Với record được sinh `equals()` tự động, một test mẫu:

~~~java
@Test
void recordEqualityContractIsReflexiveSymmetricAndTransitive() {
    Customer a = new Customer("C-01", "An");
    Customer b = new Customer("C-01", "An");
    Customer c = new Customer("C-01", "An");

    assertTrue(a.equals(a));                         // Reflexive
    assertTrue(a.equals(b));
    assertTrue(b.equals(a));                         // Symmetric
    assertTrue(b.equals(c));
    assertTrue(a.equals(c));                         // Transitive
    boolean firstComparison = a.equals(b);
    for (int i = 0; i < 5; i++) {
        assertEquals(firstComparison, a.equals(b));  // Consistent
    }
    assertFalse(a.equals(null));
    assertFalse(a.equals("C-01"));
    assertEquals(a.hashCode(), b.hashCode());
}
~~~

Assertion consistency ở ví dụ chỉ minh họa việc gọi lặp lại với object không thay đổi. Với class có state mutable, nên kiểm tra riêng việc state dùng trong equality có bị thay đổi sau khi object được dùng làm key hay không. Tốt nhất, key trong `HashMap`/`HashSet` nên có equality state bất biến.

## 3. Các trường hợp equality dễ bị bỏ sót

### Khác kiểu hoặc khác record type

Với `equals()` được sinh mặc định, record chỉ bằng một instance của cùng record type có các component tương ứng bằng nhau. Hai record khác kiểu không trở thành bằng nhau chỉ vì có cùng tên component và giá trị:

~~~java
record UserCode(String value) {}
record OrderCode(String value) {}

@Test
void differentRecordTypesAreNotEqual() {
    assertNotEquals(new UserCode("A-1"), new OrderCode("A-1"));
}
~~~

### Component là array

Không mặc định rằng record so sánh nội dung array theo kiểu deep equality. Array dùng equality theo identity, nên hai array riêng biệt có cùng byte vẫn không bằng nhau khi đặt trong component record:

~~~java
record Payload(byte[] bytes) {}

@Test
void recordArrayComponentUsesArrayEqualitySemantics() {
    Payload first = new Payload(new byte[] {1, 2});
    Payload second = new Payload(new byte[] {1, 2});

    assertNotEquals(first, second);
}
~~~

Nếu domain yêu cầu so sánh nội dung, hãy đóng gói array trong value type có `equals()`/`hashCode()` phù hợp hoặc triển khai semantics riêng một cách có chủ đích. Đồng thời cân nhắc defensive copy ở constructor và accessor để array không bị sửa sau khi object đã được dùng làm key.

### Component mutable

Record không tự làm các object component trở nên immutable. Ví dụ `record Tags(List<String> values)` vẫn có thể chứa một list mutable nếu truyền trực tiếp vào. Khi component tham gia equality/hash code, thay đổi list sau khi record được đưa vào `HashSet` có thể làm hành vi lookup không còn như mong đợi.

Nếu domain yêu cầu snapshot không sửa đổi được, có thể sao chép trong compact constructor:

~~~java
record Tags(List<String> values) {
    Tags {
        values = List.copyOf(values);
    }
}
~~~

Đoạn code cũng từ chối list hoặc phần tử `null`, đúng với hợp đồng của `List.copyOf()`. Nếu domain cần cho phép null, phải chọn cách biểu diễn và copy phù hợp thay vì dùng `List.copyOf()` một cách máy móc.

## 4. Kiểm thử null và pattern matching cho instanceof

Pattern matching cho `instanceof` trong Java 16 cho phép khai báo pattern variable ngay tại phép kiểm tra:

~~~java
static boolean isNonBlankText(Object value) {
    return value instanceof String text && !text.isBlank();
}
~~~

Nếu `value` là `null`, `instanceof` trả về `false`; vế phải của `&&` không được đánh giá và `text` không được sử dụng. Đây là hành vi hữu ích để tránh ép kiểu thủ công và lỗi null khi kiểm tra kiểu.

Test:

~~~java
@Test
void instanceofPatternHandlesNullAndUnexpectedTypes() {
    assertFalse(isNonBlankText(null));
    assertFalse(isNonBlankText(42));
    assertFalse(isNonBlankText("   "));
    assertTrue(isNonBlankText("Java"));
}
~~~

Không nhầm kết quả `instanceof` với chính sách null của domain. `instanceof` an toàn với null không có nghĩa constructor hoặc API nghiệp vụ phải chấp nhận null.

### Objects.equals() và requireNonNull()

`Objects.equals(a, b)` xử lý hai giá trị null an toàn:

~~~java
@Test
void objectsEqualsHandlesNullSymmetrically() {
    assertTrue(Objects.equals(null, null));
    assertFalse(Objects.equals(null, "Java"));
    assertFalse(Objects.equals("Java", null));
    assertTrue(Objects.equals("Java", "Java"));
}
~~~

Khi null không hợp lệ trong domain, fail fast ở constructor hoặc ranh giới API:

~~~java
@Test
void customerRejectsNullRequiredComponents() {
    assertThrows(NullPointerException.class,
            () -> new Customer(null, "An"));
    assertThrows(NullPointerException.class,
            () -> new Customer("C-01", null));
}
~~~

Kiểm thử loại exception và điểm phát sinh theo hợp đồng đã chọn. Không bắt mọi exception rồi bỏ qua, vì như vậy test có thể che một regression khác.

## 5. Phân biệt các loại collection không sửa đổi được

Các API có thể cùng từ chối mutator nhưng khác nhau về nguồn dữ liệu, snapshot và null:

| API | Có sửa qua reference trả về? | Có phản ánh thay đổi từ nguồn? | Null element |
| --- | --- | --- | --- |
| `List.of(...)` | Không | Không có nguồn ngoài | Từ chối |
| `List.copyOf(source)` | Không | Không phản ánh thay đổi sau đó của mutable source | Từ chối |
| `Stream.toList()` | Không | Là kết quả materialize của stream | Cho phép |
| `Collectors.toUnmodifiableList()` | Không | Là kết quả collector | Từ chối |
| `Collections.unmodifiableList(source)` | Không qua wrapper | Có, vì wrapper là view của source | Theo khả năng của source |

“Unmodifiable” nghĩa là không thể thay đổi collection qua reference đó. Nó không tự bảo đảm object bên trong là immutable, cũng không bảo đảm mọi collection có cùng chính sách null hoặc snapshot.

## 6. Test List.of() và List.copyOf()

`List.of()` tạo list không sửa đổi được và từ chối phần tử null:

~~~java
@Test
void listOfRejectsMutationAndNull() {
    List<String> values = List.of("a", "b");

    assertEquals(List.of("a", "b"), values);
    assertThrows(UnsupportedOperationException.class,
            () -> values.add("c"));
    assertThrows(NullPointerException.class,
            () -> List.of("a", (String) null));
}
~~~

`List.copyOf()` tạo collection không sửa đổi được từ nguồn. Khi nguồn ban đầu là mutable, thay đổi nguồn sau khi copy không làm thay đổi snapshot:

~~~java
@Test
void listCopyOfIsAnUnmodifiableSnapshot() {
    List<String> source = new ArrayList<>(List.of("a"));
    List<String> snapshot = List.copyOf(source);

    source.add("b");

    assertEquals(List.of("a"), snapshot);
    assertEquals(List.of("a", "b"), source);
    assertThrows(UnsupportedOperationException.class,
            () -> snapshot.add("c"));
}
~~~

Không test rằng `List.copyOf(source)` phải trả về object khác reference với source trong mọi trường hợp. API có thể tái sử dụng một collection đã không sửa đổi được; identity của kết quả không phải hợp đồng cần dựa vào.

## 7. Test Stream.toList() và Collectors.toUnmodifiableList()

`Stream.toList()` được bổ sung trong Java 16. Kết quả là list không sửa đổi được; phần tử null trong stream vẫn có thể xuất hiện trong kết quả:

~~~java
@Test
void streamToListIsUnmodifiableAndCanContainNull() {
    List<String> values = Stream.<String>of("a", null).toList();

    assertEquals(2, values.size());
    assertEquals("a", values.get(0));
    assertNull(values.get(1));
    assertThrows(UnsupportedOperationException.class,
            () -> values.add("b"));
}
~~~

Trong khi đó, `Collectors.toUnmodifiableList()` từ chối null:

~~~java
@Test
void toUnmodifiableListRejectsNullElement() {
    assertThrows(NullPointerException.class,
            () -> Stream.<String>of("a", null)
                    .collect(Collectors.toUnmodifiableList()));
}
~~~

Đây là khác biệt quan trọng khi refactor từ collector sang `Stream.toList()`. Nếu hợp đồng nghiệp vụ không cho phép null, hãy kiểm tra hoặc lọc null rõ ràng trước khi tạo kết quả, thay vì vô tình dựa vào exception của một API.

Không giả định `Collectors.toList()` luôn trả list mutable hoặc một implementation class cụ thể; hợp đồng của collector này không cam kết các chi tiết đó. Nếu cần kết quả không sửa đổi được, dùng API có hợp đồng unmodifiable rõ ràng.

## 8. Test Collections.unmodifiableList() là view

`Collections.unmodifiableList(source)` tạo wrapper không cho phép sửa collection thông qua wrapper. Nó không tạo snapshot độc lập: thay đổi trực tiếp trên `source` vẫn được nhìn thấy qua wrapper.

~~~java
@Test
void unmodifiableListIsAViewOfItsBackingList() {
    List<String> backing = new ArrayList<>(List.of("a"));
    List<String> view = Collections.unmodifiableList(backing);

    backing.add("b");

    assertEquals(List.of("a", "b"), view);
    assertThrows(UnsupportedOperationException.class,
            () -> view.add("c"));
}
~~~

Nếu cần snapshot, cân nhắc `List.copyOf()`. Nếu cần view phản ánh thay đổi từ nguồn, wrapper unmodifiable có thể phù hợp. Chọn theo semantics mà API công bố.

## 9. Kiểm thử Set.of() và Map.of()

Collection factory của `Set` và `Map` có thêm ràng buộc về phần tử trùng lặp và key:

~~~java
@Test
void setAndMapFactoriesRejectDuplicatesAndNulls() {
    assertThrows(IllegalArgumentException.class,
            () -> Set.of("a", "a"));
    assertThrows(NullPointerException.class,
            () -> Set.of("a", (String) null));
    assertThrows(IllegalArgumentException.class,
            () -> Map.of("a", 1, "a", 2));
    assertThrows(NullPointerException.class,
            () -> Map.of("a", (String) null));
}
~~~

Không phụ thuộc vào thứ tự iteration của `Set.of()` hoặc `Map.of()`. Nếu thứ tự là một phần của yêu cầu nghiệp vụ, chọn loại collection có hợp đồng thứ tự phù hợp và test thứ tự đó một cách tường minh.

## 10. Bộ test hồi quy tích hợp với JUnit Jupiter 5

Ví dụ sau gom các hợp đồng quan trọng thành một test class. Trong dự án thực tế, đặt record production ở source chính và test trực tiếp type đó; record lồng trong test class ở đây chỉ giúp ví dụ tự chứa.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class ValueAndCollectionRegressionTest {
    record Customer(String id, String name) {
        Customer {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(name, "name");
        }
    }

    record Tags(List<String> values) {
        Tags {
            values = List.copyOf(values);
        }
    }

    record Payload(byte[] bytes) {}

    static boolean isNonBlankText(Object value) {
        return value instanceof String text && !text.isBlank();
    }

    @Test
    void recordEqualityAndHashCode() {
        Customer a = new Customer("C-01", "An");
        Customer b = new Customer("C-01", "An");
        Customer c = new Customer("C-01", "An");
        Customer different = new Customer("C-02", "An");

        assertNotSame(a, b);
        assertEquals(a, b);
        assertEquals(a.hashCode(), b.hashCode());
        assertNotEquals(a, different);
        assertTrue(a.equals(a));
        assertTrue(a.equals(b));
        assertTrue(b.equals(a));
        assertTrue(b.equals(c));
        assertTrue(a.equals(c));
        assertFalse(a.equals(null));

        Set<Customer> set = new HashSet<>(List.of(a, b));
        assertEquals(1, set.size());
    }

    @Test
    void recordDefensivelyCopiesMutableCollectionComponent() {
        List<String> source = new ArrayList<>(List.of("java"));
        Tags tags = new Tags(source);

        source.add("streams");

        assertEquals(List.of("java"), tags.values());
        assertThrows(UnsupportedOperationException.class,
                () -> tags.values().add("records"));
    }

    @Test
    void recordArrayComponentUsesArrayIdentity() {
        Payload a = new Payload(new byte[] {1, 2});
        Payload b = new Payload(new byte[] {1, 2});

        assertNotEquals(a, b);
    }

    @Test
    void requiredComponentsRejectNull() {
        assertThrows(NullPointerException.class,
                () -> new Customer(null, "An"));
        assertThrows(NullPointerException.class,
                () -> new Customer("C-01", null));
    }

    @Test
    void nullAndPatternMatchingBehavior() {
        assertTrue(Objects.equals(null, null));
        assertFalse(Objects.equals(null, "Java"));
        assertFalse(isNonBlankText(null));
        assertFalse(isNonBlankText(10));
        assertFalse(isNonBlankText("  "));
        assertTrue(isNonBlankText("Java"));
    }

    @Test
    void listFactoriesAndCopiesAreUnmodifiable() {
        List<String> fixed = List.of("a", "b");
        assertThrows(UnsupportedOperationException.class,
                () -> fixed.add("c"));
        assertThrows(NullPointerException.class,
                () -> List.of("a", (String) null));

        List<String> source = new ArrayList<>(List.of("a"));
        List<String> copy = List.copyOf(source);
        source.add("b");
        assertEquals(List.of("a"), copy);
        assertThrows(UnsupportedOperationException.class,
                () -> copy.add("c"));
    }

    @Test
    void streamCollectionFactoriesHaveDifferentNullContracts() {
        List<String> streamList = Stream.<String>of("a", null).toList();
        assertNull(streamList.get(1));
        assertThrows(UnsupportedOperationException.class,
                () -> streamList.add("b"));

        assertThrows(NullPointerException.class,
                () -> Stream.<String>of("a", null)
                        .collect(Collectors.toUnmodifiableList()));
    }

    @Test
    void unmodifiableWrapperReflectsBackingChanges() {
        List<String> backing = new ArrayList<>(List.of("a"));
        List<String> view = Collections.unmodifiableList(backing);

        backing.add("b");
        assertEquals(List.of("a", "b"), view);
        assertThrows(UnsupportedOperationException.class,
                () -> view.add("c"));
    }

    @Test
    void setAndMapFactoriesRejectInvalidEntries() {
        assertThrows(IllegalArgumentException.class,
                () -> Set.of("a", "a"));
        assertThrows(NullPointerException.class,
                () -> Set.of("a", (String) null));
        assertThrows(IllegalArgumentException.class,
                () -> Map.of("a", 1, "a", 2));
        assertThrows(NullPointerException.class,
                () -> Map.of("a", (String) null));
    }
}
~~~

Test class sử dụng `Stream.toList()` nên cần compile với JDK 16 trở lên. JUnit Jupiter 5 là framework kiểm thử; hãy dùng phiên bản JUnit đang được dự án hỗ trợ và cấu hình test runner tương ứng.

## 11. Ma trận hồi quy trước khi merge

| Khu vực | Test tối thiểu | Kết quả mong đợi |
| --- | --- | --- |
| Record equality | Hai instance cùng component | `equals()` true và hash code bằng nhau |
| Equality contract | Reflexive, symmetric, transitive, null | Các thuộc tính luôn đúng |
| Hash collection | Key/value object tương đương | `HashSet` loại trùng; `HashMap` lookup bằng key tương đương thành công |
| Record array | Hai array khác identity nhưng cùng nội dung | Không mặc định deep equality |
| Null constructor | Component bắt buộc bị null | Ném `NullPointerException` tại ranh giới đã định |
| Pattern matching | null, sai kiểu, chuỗi rỗng và hợp lệ | Nhánh xử lý đúng, không phát sinh NPE |
| `List.of()` | Mutator và phần tử null | `UnsupportedOperationException` và `NullPointerException` |
| `List.copyOf()` | Sửa source sau khi copy | Snapshot không đổi; mutator trên copy bị từ chối |
| `Stream.toList()` | Mutator và phần tử null | List unmodifiable, phần tử null được giữ |
| `toUnmodifiableList()` | Stream có null | Ném `NullPointerException` |
| Unmodifiable view | Sửa backing list và sửa qua view | View thấy thay đổi backing; mutator qua view bị từ chối |
| Set/Map factory | Duplicate và null | Duplicate bị từ chối; null bị từ chối |

## 12. Những assertion không nên viết

- Không assert tên implementation class như `ImmutableCollections$ListN`; đó là chi tiết nội bộ.
- Không assert hai lần gọi `List.copyOf()` phải trả cùng hoặc khác reference.
- Không giả định `Collectors.toList()` luôn mutable.
- Không giả định `Set.of()` hoặc `Map.of()` có thứ tự iteration cố định.
- Không giả định mọi collection unmodifiable đều từ chối null theo cùng cách.
- Không giả định record tự deep-compare array hoặc tự làm component mutable trở nên immutable.
- Không assert hash code của object khác nhau luôn khác; hash collision là hợp lệ.
- Không chỉ test exception chung; hãy kiểm tra đúng loại exception theo hợp đồng API.

## 13. Quy trình thêm regression test khi sửa code

1. Viết test tái hiện hành vi sai trước khi sửa implementation.
2. Chốt contract: equality theo component nào, null bị từ chối ở đâu, collection là snapshot hay view.
3. Thêm test dương và âm: dữ liệu hợp lệ, null, kiểu không mong đợi, mutator, duplicate.
4. Chạy test class liên quan và toàn bộ suite phù hợp với thay đổi.
5. Nếu thay API collection, kiểm tra mọi caller có dựa vào mutability, null hoặc thứ tự hay không.
6. Giữ assertion dựa trên API contract; loại bỏ assertion phụ thuộc implementation.
7. Khi regression test pass, giữ test trong suite để bảo vệ lần thay đổi sau.

## 14. Bài tập tự kiểm tra

Một API hiện trả về `Collections.unmodifiableList(backing)`. Nhóm phát triển đổi sang `List.copyOf(backing)` để “tối ưu collection”. Một caller trước đây dựa vào việc view phản ánh thay đổi mới nhất của `backing`. Cùng lúc, một pipeline đổi từ `Collectors.toUnmodifiableList()` sang `Stream.toList()`.

Hãy trả lời:

1. Vì sao caller có thể thấy hành vi khác sau khi đổi sang `List.copyOf()`?
2. Assertion nào chứng minh view cũ phản ánh thay đổi của backing list?
3. `Stream.toList()` và `Collectors.toUnmodifiableList()` khác nhau thế nào với phần tử null?
4. Test nào bảo vệ equality/hashCode của record dùng làm key trong `HashMap`?
5. Vì sao không nên assert implementation class của list trả về?

**Đáp án:**

1. `Collections.unmodifiableList()` là view; `List.copyOf()` tạo snapshot không phản ánh các thay đổi sau đó của mutable source.
2. Thêm phần tử vào backing list rồi assert phần tử xuất hiện trong view; đồng thời xác nhận mutator qua view ném `UnsupportedOperationException`.
3. `Stream.toList()` có thể giữ phần tử null; `Collectors.toUnmodifiableList()` từ chối null bằng `NullPointerException`.
4. Tạo hai record instance khác identity nhưng bằng nhau theo component, put một instance làm key và get bằng instance còn lại; đồng thời assert hash code bằng nhau.
5. Implementation class là chi tiết triển khai có thể thay đổi; contract cần test là mutability, equality, null và thứ tự được API bảo đảm.

## Ghi nhớ

**Bộ kiểm thử hồi quy phải bảo vệ hợp đồng equality, null và từng loại collection theo đúng semantics của API.** Record tự sinh equality theo component nhưng không deep-compare array; object component mutable vẫn có thể làm thay đổi hash code. Pattern matching `instanceof` an toàn với null, trong khi constructor/API vẫn cần chính sách null rõ ràng. `List.of()`, `List.copyOf()`, `Stream.toList()`, `Collectors.toUnmodifiableList()` và `Collections.unmodifiableList()` đều có hành vi không sửa đổi qua reference trả về nhưng khác nhau về null, snapshot và backing view. Test theo contract, không theo implementation class.

## Tài liệu tham khảo

- [Oracle Java SE 26 — Object.equals and hashCode](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html)
- [Oracle Java SE 26 — Record Classes](https://docs.oracle.com/en/java/javase/26/language/records.html)
- [Oracle Java SE 26 — List](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
- [Oracle Java SE 26 — Stream.toList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Oracle Java SE 26 — Collectors.toUnmodifiableList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList())
- [Oracle Java SE 26 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
