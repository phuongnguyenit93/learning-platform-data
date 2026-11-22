# Kiểm thử collection rỗng, bất biến và thao tác không được hỗ trợ

Khi kiểm thử collection trong Java 21, cần tách biệt ba đặc tính: collection có rỗng hay không, có cho phép thay đổi cấu trúc/phần tử hay không, và thao tác cụ thể có được implementation hỗ trợ hay không. Một collection rỗng vẫn có thể mutable; một collection không rỗng vẫn có thể unmodifiable; một list có thể cho phép thay phần tử nhưng không cho phép tăng hoặc giảm kích thước.

Các test nên xác minh hợp đồng công khai của `List`, `Set`, `Map` và các factory/wrapper tương ứng. Không nên phụ thuộc tên class triển khai, thứ tự duyệt không được bảo đảm hoặc nội dung thông báo exception. Các ví dụ kiểm thử dùng JUnit Jupiter (JUnit 5), một lựa chọn hiện hành cho Java 21.

## 1. Phân biệt empty, mutable, unmodifiable và fixed-size

Các khái niệm này không đồng nghĩa:

| Loại collection | Có thể rỗng? | Thay đổi phần tử? | Thay đổi kích thước? | Ví dụ |
| --- | --- | --- | --- | --- |
| Empty mutable | Có | Có thể, tùy thao tác | Có | `new ArrayList<>()`, `new HashSet<>()`, `new HashMap<>()`. |
| Empty unmodifiable | Có | Không | Không | `List.of()`, `Set.of()`, `Map.of()`, `Collections.emptyList()`. |
| Unmodifiable view | Có hoặc không | Không qua view | Không qua view | `Collections.unmodifiableList(backing)`. |
| Fixed-size list | Có hoặc không | Có thể dùng `set()` | Không hỗ trợ add/remove | `Arrays.asList(array)`. |
| Mutable collection | Có hoặc không | Có | Có, nếu implementation hỗ trợ | `ArrayList`, `LinkedHashSet`, `HashMap`. |

Ví dụ, hai list dưới đây đều rỗng nhưng có hợp đồng khác nhau:

```java
List<String> mutableEmpty = new ArrayList<>();
List<String> unmodifiableEmpty = List.of();

mutableEmpty.add("Java"); // Thành công
unmodifiableEmpty.add("Java"); // UnsupportedOperationException
```

Test chỉ kiểm tra `isEmpty()` không đủ để kết luận collection có hỗ trợ thay đổi hay không. Cần test riêng các thao tác thuộc hợp đồng mà ứng dụng dựa vào.

## 2. Kiểm thử hợp đồng đọc của collection rỗng

Các hành vi đọc cơ bản của collection rỗng thường có thể kiểm tra ổn định qua interface:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import org.junit.jupiter.api.Test;

class EmptyCollectionTest {
    @Test
    void emptyListHasNoElements() {
        List<String> values = List.of();

        assertTrue(values.isEmpty());
        assertEquals(0, values.size());
        assertFalse(values.contains("Java"));
        assertEquals(0, values.stream().count());
        assertEquals(0, values.toArray().length);
    }

    @Test
    void emptyIteratorHasNoNextElement() {
        Iterator<String> iterator = List.<String>of().iterator();

        assertFalse(iterator.hasNext());
        assertThrows(NoSuchElementException.class, iterator::next);
    }

    @Test
    void emptyListIndexAndSequencedAccessHaveDifferentExceptions() {
        List<String> values = List.of();

        assertThrows(IndexOutOfBoundsException.class, () -> values.get(0));
        assertThrows(NoSuchElementException.class, values::getFirst);
        assertThrows(NoSuchElementException.class, values::getLast);
    }

    @Test
    void emptySetAndMapHaveNoEntries() {
        var set = java.util.Set.<String>of();
        var map = java.util.Map.<String, Integer>of();

        assertTrue(set.isEmpty());
        assertFalse(set.contains("Java"));
        assertTrue(map.isEmpty());
        assertFalse(map.containsKey("Java"));
        assertTrue(map.entrySet().isEmpty());
        assertThrows(UnsupportedOperationException.class,
                () -> set.add("Java"));
        assertThrows(UnsupportedOperationException.class,
                () -> map.put("Java", 21));
    }
}
```

`List.get(0)` kiểm tra index nên ném `IndexOutOfBoundsException`. `getFirst()` và `getLast()` là các phương thức của sequenced collection có trong Java 21; với list rỗng, chúng ném `NoSuchElementException`. Đây là hai hợp đồng khác nhau, vì vậy test nên xác nhận đúng loại exception cho đúng API.

Với map rỗng, có thể kiểm tra `isEmpty()`, `size()`, `containsKey()` và `entrySet().isEmpty()`. `Map.get(key)` trả về `null` nếu không có mapping; nếu map cho phép giá trị null, riêng `get()` không phân biệt được khóa vắng mặt với khóa được ánh xạ tới null. Các factory `Map.of()` không cho phép null key/value nên trường hợp đó có hợp đồng rõ hơn.

## 3. Phân biệt collection rỗng mutable và unmodifiable

Một test nên xác nhận collection rỗng mutable có thể nhận phần tử, còn collection rỗng unmodifiable từ factory không hỗ trợ mutation:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class EmptyMutabilityTest {
    @Test
    void emptyArrayListCanAcceptAnElement() {
        List<String> values = new ArrayList<>();

        assertTrue(values.isEmpty());
        values.add("Java 21");

        assertEquals(List.of("Java 21"), values);
    }

    @Test
    void emptyFactoryListDoesNotSupportMutation() {
        List<String> values = List.of();

        assertTrue(values.isEmpty());
        assertThrows(UnsupportedOperationException.class,
                () -> values.add("Java 21"));
        assertTrue(values.isEmpty());
    }
}
```

Sau khi một thao tác ném exception, kiểm tra lại trạng thái giúp xác nhận collection không bị thay đổi một phần ngoài mong đợi. Không kiểm tra thông điệp exception vì thông điệp không phải hợp đồng portable.

## 4. Kiểm thử `List.of`, `Set.of` và `Map.of`

Các factory `of()` tạo collection unmodifiable. Chúng không chấp nhận phần tử null; `Set.of()` không chấp nhận phần tử trùng; `Map.of()` không chấp nhận khóa trùng hoặc key/value null.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class CollectionFactoryTest {
    @Test
    void listOfPreservesOrderAndRejectsMutation() {
        List<String> values = List.of("A", "B");

        assertEquals(List.of("A", "B"), values);
        assertThrows(UnsupportedOperationException.class,
                () -> values.set(0, "X"));
        assertThrows(UnsupportedOperationException.class,
                () -> values.add("C"));
        assertThrows(NullPointerException.class,
                () -> List.of("A", (String) null));
    }

    @Test
    void setOfRejectsDuplicatesAndNull() {
        Set<String> values = Set.of("A", "B");
        assertEquals(2, values.size());
        assertTrue(values.containsAll(Set.of("A", "B")));
        assertThrows(IllegalArgumentException.class,
                () -> Set.of("A", "A"));
        assertThrows(NullPointerException.class,
                () -> Set.of("A", (String) null));
    }

    @Test
    void mapOfRejectsDuplicateKeysAndNulls() {
        Map<String, Integer> values = Map.of("A", 1);
        assertEquals(1, values.get("A"));
        assertThrows(UnsupportedOperationException.class,
                () -> values.put("B", 2));
        assertThrows(IllegalArgumentException.class,
                () -> Map.of("A", 1, "A", 2));
        assertThrows(NullPointerException.class,
                () -> Map.<String, Integer>of("A", null));
        assertThrows(NullPointerException.class,
                () -> Map.<String, Integer>of(null, 1));
    }

    @Test
    void setOfDoesNotSupportAddingElements() {
        Set<String> values = Set.of("A");

        assertThrows(UnsupportedOperationException.class,
                () -> values.add("B"));
        assertEquals(Set.of("A"), values);
    }
}
```

Các lời gọi `Map.<String, Integer>of("A", null)` và `Map.<String, Integer>of(null, 1)` hợp lệ về cú pháp; factory ném `NullPointerException` lúc chạy vì key hoặc value là null.

Không kiểm tra thứ tự iteration của `Set.of()` hoặc `Map.of()`: API không cam kết thứ tự duyệt. Hãy dùng `assertEquals()` với một Set/Map kỳ vọng hoặc kiểm tra membership/mapping thay vì so sánh chuỗi `toString()` hay danh sách được tạo từ iterator.

## 5. Kiểm thử `copyOf()` và phân biệt bản sao với view

`List.copyOf()`, `Set.copyOf()` và `Map.copyOf()` tạo collection unmodifiable từ dữ liệu nguồn. `List.copyOf()` giữ thứ tự phần tử của list nguồn. `Set.copyOf()` và `Map.copyOf()` không cam kết iteration order. Các phương thức này không tạo deep copy của object nằm bên trong.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class CopyOfTest {
    @Test
    void listCopyOfIsAnUnmodifiableSnapshotOfStructure() {
        List<String> source = new ArrayList<>(List.of("A", "B"));
        List<String> copy = List.copyOf(source);

        source.add("C");

        assertEquals(List.of("A", "B"), copy);
        assertEquals(List.of("A", "B", "C"), source);
        assertThrows(UnsupportedOperationException.class,
                () -> copy.add("D"));
    }

    @Test
    void copyOfRejectsNullElements() {
        List<String> source = new ArrayList<>();
        source.add(null);

        assertThrows(NullPointerException.class, () -> List.copyOf(source));
    }
}
```

Không kiểm tra `copy == source` hoặc `copy != source`. Implementation được phép tái sử dụng một collection đã unmodifiable phù hợp; identity không phải hợp đồng mà ứng dụng nên dựa vào. Với nguồn mutable như `ArrayList` trong test, hãy kiểm tra rằng thay đổi nguồn sau lời gọi không làm thay đổi kết quả. Nếu đầu vào là unmodifiable view đang backing bởi một collection mutable khác, đừng giả định `copyOf()` luôn tách view khỏi backing; khi cần snapshot độc lập chắc chắn, trước tiên sao chép view sang một collection mutable mới rồi tạo bản unmodifiable từ bản sao đó.

```java
List<String> backing = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(backing);
List<String> detached = List.copyOf(new ArrayList<>(view));

backing.add("C");
assertEquals(List.of("A", "B"), detached);
```

Một điểm khác biệt: `Set.copyOf(collection)` xử lý các phần tử trùng trong nguồn bằng cách giữ một phần tử đại diện; `Set.of(...)` nhận các phần tử trực tiếp và ném `IllegalArgumentException` nếu có phần tử trùng. Đừng viết test yêu cầu `Set.copyOf()` ném exception chỉ vì nguồn có duplicate.

## 6. Kiểm thử unmodifiable wrapper là live view

`Collections.unmodifiableList(backing)` và `Collections.unmodifiableMap(backing)` tạo wrapper chặn thao tác thay đổi qua wrapper. Chúng vẫn nhìn thấy thay đổi được thực hiện trực tiếp trên collection/map backing:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;

class UnmodifiableViewTest {
    @Test
    void wrapperReflectsChangesMadeThroughBackingCollection() {
        List<String> backing = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(backing);

        backing.add("B");

        assertEquals(List.of("A", "B"), view);
        assertThrows(UnsupportedOperationException.class,
                () -> view.add("C"));
    }
}
```

Test này giúp phân biệt wrapper với bản sao unmodifiable do `List.copyOf()` tạo từ một nguồn mutable. Wrapper bảo vệ đường truy cập được cung cấp cho caller; nó không làm cho backing collection trở nên immutable nếu nơi khác vẫn giữ tham chiếu mutable.

Nếu mục tiêu là không cho code gọi thay đổi dữ liệu qua bất kỳ tham chiếu nào, cần không để lộ backing reference hoặc tạo snapshot phù hợp. Chỉ trả về unmodifiable wrapper không đủ nếu một phần khác của chương trình vẫn sửa backing collection.

## 7. Phân biệt `Arrays.asList()` với list unmodifiable

`Arrays.asList(array)` trả về list có kích thước cố định, được backing bởi mảng. `set()` được hỗ trợ và thay đổi cả list lẫn mảng; `add()` và `remove()` không được hỗ trợ vì kích thước mảng không đổi.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;

class ArraysAsListTest {
    @Test
    void arraysAsListAllowsReplacementButNotResize() {
        String[] source = {"A", "B"};
        List<String> values = Arrays.asList(source);

        values.set(0, "X");

        assertEquals("X", source[0]);
        assertThrows(UnsupportedOperationException.class,
                () -> values.add("C"));
        assertThrows(UnsupportedOperationException.class,
                () -> values.remove(0));
    }
}
```

Đây là trường hợp quan trọng khi kiểm thử thao tác không được hỗ trợ: không nên gắn nhãn mọi list không hỗ trợ `add()` là immutable. `Arrays.asList()` vẫn cho phép thay thế phần tử tại index hợp lệ.

## 8. Kiểm thử `UnsupportedOperationException` đúng cách

Khi API không hỗ trợ thao tác mutation, loại exception thường là `UnsupportedOperationException` (UOE). Test nên kích hoạt thao tác thực sự cần thay đổi trạng thái và xác minh trạng thái sau đó:

```java
List<String> values = List.of("A", "B");

assertThrows(UnsupportedOperationException.class,
        () -> values.add("C"));
assertThrows(UnsupportedOperationException.class,
        () -> values.set(0, "X"));
assertThrows(UnsupportedOperationException.class,
        () -> values.remove(0));
assertEquals(List.of("A", "B"), values);
```

Một số thao tác như `removeIf(predicate)` có thể không cần thay đổi collection nếu predicate không khớp phần tử nào. Với implementation dùng cách duyệt mặc định, iterator chỉ bị yêu cầu xóa khi predicate trả về `true`; nếu không có phần tử khớp, thao tác có thể trả về `false` mà không cần gọi một mutation bị cấm. Theo hợp đồng chung, không nên viết test portable yêu cầu mọi implementation đều ném UOE khi thao tác không làm thay đổi gì. Nếu cần test unsupported mutation, hãy chọn input chắc chắn kích hoạt thay đổi, ví dụ predicate khớp phần tử đang có.

Ví dụ với fixed-size list: predicate không khớp thì không có thao tác xóa nào được gọi; predicate khớp phần tử thì thao tác xóa không được hỗ trợ:

```java
import java.util.Arrays;

List<String> values = Arrays.asList("A", "B");

assertFalse(values.removeIf(value -> false));
assertThrows(UnsupportedOperationException.class,
        () -> values.removeIf("A"::equals));
```

Predicate luôn trả `false`, nên không có phần tử nào cần xóa. `Arrays.asList()` là fixed-size list; với triển khai mặc định của `removeIf`, không có lần gọi `Iterator.remove()` nào xảy ra nên kết quả là `false`. Không suy rộng kết quả này cho mọi unmodifiable implementation.

## 9. Phân biệt các exception theo nguyên nhân

Không phải mọi lỗi khi thao tác collection rỗng hoặc unmodifiable đều là UOE:

| Tình huống | Exception mong đợi | Ý nghĩa |
| --- | --- | --- |
| Thêm/xóa/thay phần tử trên collection unmodifiable | `UnsupportedOperationException` | Collection không hỗ trợ mutation đó. |
| Gọi `List.get(0)` khi list rỗng | `IndexOutOfBoundsException` | Index không hợp lệ. |
| Gọi `List.getFirst()` hoặc `getLast()` khi list rỗng | `NoSuchElementException` | Không có phần tử ở đầu/cuối. |
| Gọi `Iterator.next()` khi iterator đã hết | `NoSuchElementException` | Không còn phần tử để trả về. |
| Truyền null vào `List.of`, `Set.of`, `Map.of` | `NullPointerException` | Factory không cho phép null. |
| Trùng phần tử trong `Set.of` hoặc trùng key trong `Map.of` | `IllegalArgumentException` | Đầu vào vi phạm tính duy nhất. |
| Truyền null vào `List.copyOf`, `Set.copyOf`, `Map.copyOf` | `NullPointerException` | Factory copy không chấp nhận null. |

Test chính xác exception giúp tài liệu hóa hợp đồng và làm rõ nguyên nhân lỗi. Tránh bắt `RuntimeException` chung vì có thể che giấu một lỗi khác ngoài dự kiến.

## 10. Dùng parameterized test để kiểm tra nhiều implementation

Nếu nhiều loại list đều phải tuân thủ cùng một hợp đồng unmodifiable, dùng JUnit Jupiter `@ParameterizedTest` để tránh lặp code:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class UnmodifiableListContractTest {
    static Stream<Arguments> unmodifiableLists() {
        return Stream.of(
                Arguments.of("List.of", List.of("A", "B")),
                Arguments.of(
                        "unmodifiable wrapper",
                        Collections.unmodifiableList(new ArrayList<>(List.of("A", "B")))
                ),
                Arguments.of("emptyList", Collections.<String>emptyList())
        );
    }

    @ParameterizedTest(name = "{0} rejects mutation")
    @MethodSource("unmodifiableLists")
    void rejectsMutation(String description, List<String> values) {
        if (values.isEmpty()) {
            assertThrows(UnsupportedOperationException.class,
                    () -> values.add("C"));
        } else {
            assertThrows(UnsupportedOperationException.class,
                    () -> values.add("C"));
            assertThrows(UnsupportedOperationException.class,
                    () -> values.set(0, "X"));
            assertThrows(UnsupportedOperationException.class,
                    () -> values.remove(0));
        }
    }
}
```

Trong dự án thực tế, có thể tách test cho list rỗng và list có phần tử để mỗi assertion có cùng tiền điều kiện. Parameterized test hữu ích khi cùng một contract cần được xác minh cho nhiều factory hoặc wrapper.

Đừng đưa `Arrays.asList()` vào tập test unmodifiable ở trên nếu contract cần kiểm tra `set()` bị từ chối, vì fixed-size list vẫn cho phép thay phần tử. Hãy có test riêng cho fixed-size behavior.

## 11. Kiểm thử map và set mà không phụ thuộc iteration order

`Set.of()` và `Map.of()` không cam kết iteration order. Test nên kiểm tra nội dung theo ngữ nghĩa của Set/Map:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class SetMapContractTest {
    @Test
    void setChecksMembershipAndUniqueness() {
        Set<String> values = Set.of("A", "B");

        assertEquals(2, values.size());
        assertTrue(values.contains("A"));
        assertFalse(values.contains("C"));
    }

    @Test
    void mapChecksMappingsByKey() {
        Map<String, Integer> values = Map.of("A", 1, "B", 2);

        assertEquals(2, values.size());
        assertEquals(1, values.get("A"));
        assertTrue(values.containsKey("B"));
        assertFalse(values.containsKey("C"));
    }
}
```

Không chuyển set/map thành list rồi so sánh theo một thứ tự cụ thể, trừ khi đang kiểm thử một implementation có hợp đồng thứ tự như `LinkedHashSet`, `LinkedHashMap` hoặc một `SequencedSet`/`SequencedMap` cụ thể.

## 12. Kiểm thử tính bất biến chỉ ở cấu trúc collection

Unmodifiable collection bảo vệ cấu trúc và các thao tác cập nhật qua collection; nó không tự làm cho object phần tử trở thành immutable. Ví dụ list unmodifiable có thể chứa một `StringBuilder` mutable:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class ShallowUnmodifiableTest {
    @Test
    void elementsCanRemainMutable() {
        StringBuilder element = new StringBuilder("A");
        List<StringBuilder> values = List.of(element);

        values.get(0).append("B");

        assertEquals("AB", values.get(0).toString());
        assertThrows(UnsupportedOperationException.class,
                () -> values.set(0, new StringBuilder("X")));
    }
}
```

Test này phân biệt unmodifiable structure với deep immutability. Nếu ứng dụng yêu cầu dữ liệu bất biến sâu, cần dùng phần tử immutable hoặc tạo defensive copy phù hợp; `List.copyOf()` chỉ sao chép cấu trúc và tham chiếu phần tử.

## 13. Những điều không nên assert

- Không assert tên class cụ thể của `List.of()`, `Set.of()`, `Map.of()` hoặc wrapper. Implementation class là chi tiết nội bộ.
- Không assert object identity của kết quả `copyOf()`.
- Không assert iteration order của `Set.of()` và `Map.of()`.
- Không assert nội dung message của `UnsupportedOperationException`, `NullPointerException` hoặc `IllegalArgumentException`.
- Không giả định mọi mutation method đều ném UOE khi thao tác không làm thay đổi dữ liệu.
- Không coi `Arrays.asList()` là unmodifiable; đây là list fixed-size, vẫn cho phép `set()`.
- Không coi unmodifiable wrapper là snapshot hoặc deep immutable.
- Không gộp mọi exception thành `RuntimeException` trong assertion.

## 14. Checklist thiết kế test

1. Xác định test đang kiểm tra emptiness, mutability, unmodifiable behavior hay fixed-size behavior.
2. Chọn collection phù hợp với contract: `ArrayList`, `List.of`, `Collections.unmodifiableList`, `Arrays.asList` hoặc `copyOf`.
3. Test các thao tác đọc của collection rỗng và đúng exception cho index/iterator/first/last.
4. Với mutation, dùng dữ liệu chắc chắn làm thay đổi trạng thái; kiểm tra cả exception và trạng thái sau đó.
5. Test riêng quy tắc null và duplicate của factory methods.
6. Phân biệt live unmodifiable view với bản sao độc lập được tạo từ nguồn mutable bằng `copyOf()`; không giả định `copyOf()` luôn tách một unmodifiable view khỏi backing collection.
7. Với Set/Map không có encounter-order contract, chỉ assert membership và mapping.
8. Test phần tử mutable riêng nếu nghiệp vụ có yêu cầu deep immutability.
9. Dùng JUnit Jupiter parameterized tests khi nhiều implementation phải tuân thủ cùng một contract.
10. Không phụ thuộc implementation class, exception message hoặc hành vi không được API bảo đảm.

## 15. Tài liệu tham khảo chính thức

- [Java SE 21 API — `List`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html): list factory, `copyOf`, index access và sequenced operations.
- [Java SE 21 API — `Set`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html): uniqueness, `of`, `copyOf` và iteration-order contract.
- [Java SE 21 API — `Map`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html): `of`, `copyOf`, null/duplicate rules và map views.
- [Java SE 21 API — `Collections`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): empty collections và unmodifiable wrappers.
- [Java SE 21 API — `Arrays.asList`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size list được backing bởi array.
- [Java SE 21 API — `SequencedCollection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): `getFirst`, `getLast` và thao tác hai đầu.
- [JUnit 5 User Guide — Jupiter](https://junit.org/junit5/docs/current/user-guide/): `@Test`, assertions và parameterized tests.
