# Kiểm chứng reversed view và các hợp đồng bất biến

Lab này giúp bạn kiểm chứng các hợp đồng của Sequenced Collections trong Java 21: `reversed()` trả về một view có thứ tự encounter đảo ngược; với collection có thể thay đổi, thao tác qua view và thay đổi trên collection gốc được phản ánh qua lại. Lab cũng phân biệt unmodifiable collection, unmodifiable view, fixed-size list và snapshot để tránh kết luận sai rằng mọi collection không hỗ trợ `add()` đều bất biến hoàn toàn.

Bạn sẽ dùng JUnit Jupiter để kiểm tra `List`, `LinkedHashSet` và `LinkedHashMap`, sau đó kiểm tra các trường hợp `List.of()`, `Collections.unmodifiableList()`, `Arrays.asList()` và `List.copyOf()`. Tất cả ví dụ dùng API Java SE 21, không cần preview feature.

## 1. Mục tiêu và chuẩn bị

Sau lab, bạn cần có khả năng:

- Xác nhận thứ tự của `reversed()` mà không phụ thuộc implementation class.
- Chứng minh reversed view được backing bởi collection gốc.
- Hiểu cách `addFirst`, `addLast`, `putFirst` và `putLast` tác động lên thứ tự của collection gốc khi thao tác qua reversed view.
- Xác minh reversed view vẫn tuân theo giới hạn mutation của collection gốc.
- Phân biệt live unmodifiable view, fixed-size list và snapshot từ `copyOf()`.
- Viết test không phụ thuộc object identity hoặc iteration order không được API bảo đảm.

Yêu cầu môi trường:

- JDK 21.
- JUnit Jupiter (JUnit 5) trong test scope của dự án.
- Một project Java có source/test folder theo build tool bạn đang dùng.

Ví dụ Maven dependency tối thiểu cho JUnit Jupiter nếu project chưa có:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.2</version>
    <scope>test</scope>
</dependency>
```

Giữ cấu hình Surefire/JUnit Platform tương thích với phiên bản Maven và JDK của dự án. Lab không yêu cầu thay đổi cấu hình build nếu JUnit Jupiter đã chạy được.

## 2. Ôn lại các hợp đồng cần kiểm chứng

`SequencedCollection`, `SequencedSet` và `SequencedMap` được bổ sung trong Java 21 để biểu diễn collection/map có thứ tự encounter xác định và thao tác ở hai đầu. `reversed()` trả về view có thứ tự encounter ngược với collection/map gốc.

| Kiểu dữ liệu | View đảo ngược | Cách kiểm tra thứ tự |
| --- | --- | --- |
| `List<E>` | `List<E> reversed()` | Duyệt list hoặc so sánh với list kỳ vọng. |
| `SequencedSet<E>` | `SequencedSet<E> reversed()` | Chuyển encounter order thành `List` để assert; `Set.equals()` không kiểm tra thứ tự. |
| `SequencedMap<K,V>` | `SequencedMap<K,V> reversed()` | Dùng `sequencedKeySet()` hoặc `sequencedEntrySet()` để kiểm tra encounter order. |

Reversed view không phải bản sao độc lập. Nếu collection gốc hỗ trợ mutation, thay đổi qua view sẽ tác động lên collection gốc và thay đổi trực tiếp trên collection gốc sẽ xuất hiện trong view. Nếu collection gốc không hỗ trợ một mutation, reversed view cũng không được dùng để vượt qua giới hạn đó.

Các hợp đồng cần phân biệt:

| Loại | Đặc tính | Ví dụ |
| --- | --- | --- |
| Mutable | Có thể thêm, xóa hoặc thay phần tử tùy API. | `ArrayList`, `LinkedHashSet`, `LinkedHashMap`. |
| Unmodifiable collection | Không cho thay đổi qua chính collection đó. | `List.of`, `Set.of`, `Map.of`, `List.copyOf`. |
| Unmodifiable view | Chặn mutation qua view nhưng vẫn phản ánh thay đổi từ backing collection. | `Collections.unmodifiableList(backing)`. |
| Fixed-size list | Không đổi kích thước, nhưng vẫn có thể thay phần tử. | `Arrays.asList(array)`. |

## 3. Bài 1 — Kiểm chứng `List.reversed()` là view có backing

Tạo list gốc `[A, B, C]`, lấy `reversed()` rồi kiểm tra thứ tự `[C, B, A]`. Sau đó sửa phần tử qua reversed view và sửa cấu trúc qua list gốc để xác nhận cả hai phía nhìn thấy cùng dữ liệu.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ReversedListLabTest {
    @Test
    void reversedListIsABackedView() {
        List<String> original = new ArrayList<>(List.of("A", "B", "C"));
        List<String> reversed = original.reversed();

        assertEquals(List.of("C", "B", "A"), reversed);

        // Index 0 của view là phần tử cuối của list gốc.
        reversed.set(0, "C*");
        assertEquals(List.of("A", "B", "C*"), original);

        // Thay đổi trực tiếp trên list gốc xuất hiện trong view.
        original.add("D");
        assertEquals(List.of("D", "C*", "B", "A"), reversed);
    }
}
```

**Kết quả cần đạt:** test pass. `reversed.get(0)` tương ứng với phần tử cuối của list gốc; `set(0, ...)` trên view cập nhật phần tử cuối của list gốc. Khi thêm `D` vào cuối list gốc, `D` xuất hiện ở đầu reversed view.

### Thử thao tác hai đầu

Mở rộng test để kiểm tra ánh xạ của `addFirst()` và `addLast()`:

```java
@Test
void firstAndLastOperationsOnViewMapToOppositeEnds() {
    List<String> original = new ArrayList<>(List.of("A", "B", "C"));
    List<String> reversed = original.reversed();

    reversed.addFirst("X");
    assertEquals(List.of("A", "B", "C", "X"), original);

    reversed.addLast("Y");
    assertEquals(List.of("Y", "A", "B", "C", "X"), original);

    assertEquals(List.of("X", "C", "B", "A", "Y"), reversed);
}
```

`addFirst()` trên reversed view thêm vào cuối list gốc; `addLast()` trên reversed view thêm vào đầu list gốc. Đây là hệ quả của thứ tự encounter bị đảo, không phải một bản sao được cập nhật thủ công.

Bạn cũng có thể kiểm tra đảo hai lần:

```java
List<String> twiceReversed = original.reversed().reversed();
assertEquals(original, twiceReversed);
```

Chỉ assert thứ tự và nội dung. Không assert `twiceReversed == original`; API không yêu cầu hai biểu thức phải trả cùng object identity.

## 4. Bài 2 — Kiểm chứng `SequencedSet.reversed()`

`LinkedHashSet` giữ encounter order và triển khai `SequencedSet` trong Java 21. Vì `Set.equals()` chỉ so sánh membership, không so sánh thứ tự, hãy chuyển view thành `List` khi cần assert thứ tự.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;
import org.junit.jupiter.api.Test;

class ReversedSetLabTest {
    @Test
    void reversedLinkedHashSetIsBackedAndKeepsReverseEncounterOrder() {
        LinkedHashSet<String> original = new LinkedHashSet<>(List.of("A", "B", "C"));
        SequencedSet<String> reversed = original.reversed();

        assertEquals(List.of("C", "B", "A"), new ArrayList<>(reversed));

        reversed.addFirst("X");
        assertEquals(List.of("A", "B", "C", "X"), new ArrayList<>(original));

        reversed.addLast("Y");
        assertEquals(List.of("Y", "A", "B", "C", "X"), new ArrayList<>(original));
        assertEquals(List.of("X", "C", "B", "A", "Y"), new ArrayList<>(reversed));
    }
}
```

**Kết quả cần đạt:** test pass và encounter order thay đổi đúng ở cả hai phía. Không dùng `assertEquals(Set.of(...), original)` để xác minh thứ tự vì Set equality không có ý nghĩa thứ tự.

## 5. Bài 3 — Kiểm chứng `SequencedMap.reversed()`

`LinkedHashMap` triển khai `SequencedMap` và giữ encounter order của các mapping. Dùng `sequencedKeySet()` để assert thứ tự khóa thay vì giả định `Map.equals()` so sánh thứ tự.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.SequencedMap;
import org.junit.jupiter.api.Test;

class ReversedMapLabTest {
    @Test
    void reversedLinkedHashMapIsBackedAndReversesKeyOrder() {
        LinkedHashMap<String, Integer> original = new LinkedHashMap<>();
        original.put("A", 1);
        original.put("B", 2);
        original.put("C", 3);

        SequencedMap<String, Integer> reversed = original.reversed();
        assertEquals(List.of("C", "B", "A"),
                new ArrayList<>(reversed.sequencedKeySet()));

        reversed.putFirst("X", 24);
        assertEquals(List.of("A", "B", "C", "X"),
                new ArrayList<>(original.sequencedKeySet()));

        reversed.putLast("Y", 25);
        assertEquals(List.of("Y", "A", "B", "C", "X"),
                new ArrayList<>(original.sequencedKeySet()));
        assertEquals(24, original.get("X"));
        assertEquals(25, original.get("Y"));
    }
}
```

**Kết quả cần đạt:** test pass. `putFirst()` trên reversed map đặt mapping ở cuối map gốc; `putLast()` trên reversed map đặt mapping ở đầu map gốc. Dữ liệu key/value vẫn thuộc cùng một map được backing.

## 6. Bài 4 — Reversed view không vượt qua giới hạn unmodifiable

Collection unmodifiable không cho thay đổi qua reversed view. Kiểm tra các thao tác thay phần tử và thay đổi cấu trúc:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class UnmodifiableReversedListLabTest {
    @Test
    void reversedViewOfListOfRemainsUnmodifiable() {
        List<String> original = List.of("A", "B", "C");
        List<String> reversed = original.reversed();

        assertEquals(List.of("C", "B", "A"), reversed);
        assertThrows(UnsupportedOperationException.class,
                () -> reversed.set(0, "X"));
        assertThrows(UnsupportedOperationException.class,
                () -> reversed.addFirst("X"));
        assertThrows(UnsupportedOperationException.class,
                reversed::removeLast);
        assertEquals(List.of("A", "B", "C"), original);
    }
}
```

Với `SequencedSet` và `SequencedMap`, Java 21 cung cấp wrapper tương ứng:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedMap;
import java.util.SequencedSet;
import org.junit.jupiter.api.Test;

class UnmodifiableSequencedViewLabTest {
    @Test
    void reversedUnmodifiableSetRejectsMutation() {
        SequencedSet<String> backing = new LinkedHashSet<>(List.of("A", "B"));
        SequencedSet<String> readOnly = Collections.unmodifiableSequencedSet(backing);
        SequencedSet<String> reversed = readOnly.reversed();

        assertEquals(List.of("B", "A"), List.copyOf(reversed));
        assertThrows(UnsupportedOperationException.class,
                () -> reversed.addFirst("X"));
    }

    @Test
    void reversedUnmodifiableMapRejectsMutation() {
        LinkedHashMap<String, Integer> backing = new LinkedHashMap<>();
        backing.put("A", 1);
        backing.put("B", 2);

        SequencedMap<String, Integer> readOnly =
                Collections.unmodifiableSequencedMap(backing);
        SequencedMap<String, Integer> reversed = readOnly.reversed();

        assertEquals(List.of("B", "A"), List.copyOf(reversed.sequencedKeySet()));
        assertThrows(UnsupportedOperationException.class,
                () -> reversed.putFirst("X", 3));
        assertThrows(UnsupportedOperationException.class,
                reversed::pollFirstEntry);
    }
}
```

Các wrapper trên chặn mutation qua reversed view. Nếu backing collection vẫn được giữ ở nơi khác, thay đổi trực tiếp qua backing vẫn có thể xuất hiện trong read-only view; đây là hợp đồng của view, không phải deep immutable snapshot.

## 7. Bài 5 — Phân biệt live unmodifiable view và snapshot

`Collections.unmodifiableList(backing)` là một live view: nó phản ánh thay đổi từ backing list nhưng không cho caller thay đổi qua wrapper. Ngược lại, `List.copyOf(mutableSource)` tạo một collection unmodifiable độc lập về cấu trúc với nguồn mutable tại thời điểm gọi.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;

class ViewAndSnapshotLabTest {
    @Test
    void reversedUnmodifiableWrapperStillReflectsBackingChanges() {
        List<String> backing = new ArrayList<>(List.of("A", "B", "C"));
        List<String> readOnly = Collections.unmodifiableList(backing);
        List<String> reversed = readOnly.reversed();

        backing.add("D");

        assertEquals(List.of("D", "C", "B", "A"), reversed);
        assertThrows(UnsupportedOperationException.class,
                () -> reversed.addFirst("X"));
    }

    @Test
    void reversedCopyOfDoesNotFollowLaterStructuralChangesToMutableSource() {
        List<String> source = new ArrayList<>(List.of("A", "B", "C"));
        List<String> snapshot = List.copyOf(source);
        List<String> reversed = snapshot.reversed();

        source.set(0, "X");
        source.add("D");

        assertEquals(List.of("C", "B", "A"), reversed);
        assertThrows(UnsupportedOperationException.class,
                () -> reversed.set(0, "Y"));
    }
}
```

Không kiểm tra `snapshot == source` hoặc `snapshot != source`; identity không phải hợp đồng. Ví dụ dùng `ArrayList` mutable làm nguồn để kiểm tra snapshot độc lập về cấu trúc. Không suy rộng rằng `copyOf()` luôn tạo object mới khi nguồn vốn đã unmodifiable.

`copyOf()` là shallow copy: nếu phần tử là object mutable, trạng thái bên trong phần tử vẫn có thể thay đổi:

```java
StringBuilder element = new StringBuilder("A");
List<StringBuilder> snapshot = List.copyOf(List.of(element));

element.append("B");
assertEquals("AB", snapshot.getFirst().toString());
```

Collection không cho thay đổi cấu trúc qua API của nó, nhưng không tự làm immutable các object phần tử.

## 8. Bài 6 — Kiểm tra fixed-size list từ `Arrays.asList()`

`Arrays.asList(array)` cho phép thay phần tử bằng `set()`, nhưng không hỗ trợ tăng hoặc giảm kích thước. Reversed view phải giữ đúng hợp đồng này:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;

class FixedSizeReversedListLabTest {
    @Test
    void reversedArraysAsListAllowsSetButRejectsResize() {
        String[] backing = {"A", "B", "C"};
        List<String> fixedSize = Arrays.asList(backing);
        List<String> reversed = fixedSize.reversed();

        assertEquals(List.of("C", "B", "A"), reversed);

        reversed.set(0, "C*");
        assertEquals("C*", backing[2]);

        assertThrows(UnsupportedOperationException.class,
                () -> reversed.addFirst("X"));
        assertThrows(UnsupportedOperationException.class,
                reversed::removeLast);
    }
}
```

Test này chứng minh “không hỗ trợ `add/remove`” không đồng nghĩa “không hỗ trợ mọi mutation”. `set()` vẫn hợp lệ và cập nhật cả mảng backing.

## 9. Bài 7 — Kiểm tra null, duplicate và thứ tự không được bảo đảm

Các factory collection bất biến có những hợp đồng đầu vào riêng:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ImmutableFactoryContractLabTest {
    @Test
    void listFactoryRejectsNull() {
        assertThrows(NullPointerException.class,
                () -> List.of("A", (String) null));
        assertThrows(NullPointerException.class,
                () -> List.copyOf(java.util.Arrays.asList("A", null)));
    }

    @Test
    void setFactoryRejectsDuplicatesAndNull() {
        assertThrows(IllegalArgumentException.class,
                () -> Set.of("A", "A"));
        assertThrows(NullPointerException.class,
                () -> Set.of("A", (String) null));
    }

    @Test
    void mapFactoryRejectsDuplicateKeysAndNulls() {
        assertThrows(IllegalArgumentException.class,
                () -> Map.of("A", 1, "A", 2));
        assertThrows(NullPointerException.class,
                () -> Map.<String, Integer>of("A", null));
        assertThrows(NullPointerException.class,
                () -> Map.<String, Integer>of(null, 1));
    }
}
```

Không dùng `Set.of()` hoặc `Map.of()` để kiểm tra reversed order vì các kiểu trả về của factory này không cung cấp contract encounter order như `SequencedSet`/`SequencedMap`. Dùng `LinkedHashSet` và `LinkedHashMap` khi bài test cần thứ tự có thể dự đoán.

## 10. Tổng hợp các assertion nên và không nên dùng

| Mục tiêu | Assertion phù hợp | Tránh |
| --- | --- | --- |
| Kiểm tra thứ tự list reversed | `assertEquals(expectedList, reversed)` | So sánh implementation class. |
| Kiểm tra thứ tự set reversed | `assertEquals(expectedList, new ArrayList<>(reversed))` | `Set.equals()` để kiểm tra order. |
| Kiểm tra thứ tự map reversed | Assert `sequencedKeySet()` hoặc `sequencedEntrySet()` theo encounter order. | `Map.equals()` để kiểm tra order. |
| Kiểm tra view có backing | Sửa qua view rồi đọc collection gốc; sửa gốc rồi đọc view. | Chỉ kiểm tra `==` hoặc `equals()` một lần. |
| Kiểm tra unmodifiable | Thử mutation có thay đổi thực sự và assert UOE. | Assert exception message hoặc mọi method đều ném UOE trong mọi tình huống. |
| Kiểm tra snapshot | Thay đổi nguồn mutable sau `copyOf()` rồi kiểm tra cấu trúc kết quả. | Assert object identity. |
| Kiểm tra fixed-size | Assert `set()` thành công và `add/remove` ném UOE. | Gọi fixed-size list là immutable hoàn toàn. |
| Kiểm tra factory input | Assert NPE/IAE theo null và duplicate contract. | Phụ thuộc thông điệp exception. |

## 11. Bài tập mở rộng

1. Viết test `removeFirst()` và `removeLast()` qua reversed list, xác nhận đúng đầu bị xóa ở list gốc.
2. Viết test cho `LinkedHashSet.reversed()` khi xóa phần tử đầu/cuối qua view và kiểm tra encounter order của set gốc.
3. Viết test cho `SequencedMap.pollFirstEntry()` trên mutable reversed map và xác nhận mapping bị loại ở cuối map gốc.
4. Bọc một `LinkedHashMap` bằng `Collections.unmodifiableSequencedMap()`, sau đó xác minh cả `putFirst`, `putLast`, `pollFirstEntry` và `pollLastEntry` đều không cho thay đổi.
5. Tạo một API trả về reversed view của collection nội bộ; đánh giá liệu caller có thể quan sát thay đổi từ code khác hay không và chọn view hoặc snapshot phù hợp.
6. Thêm một test với phần tử mutable để chứng minh unmodifiable collection không đồng nghĩa deep immutability.

## 12. Tiêu chí hoàn thành lab

- [ ] Test xác nhận `List.reversed()` đảo encounter order.
- [ ] Thay đổi qua list reversed được phản ánh trên list gốc.
- [ ] Thay đổi list gốc được phản ánh trong reversed view.
- [ ] `addFirst`/`addLast` qua reversed view tác động đúng đầu của list gốc.
- [ ] `LinkedHashSet` và `LinkedHashMap` có test thứ tự reversed bằng sequenced views.
- [ ] Reversed view của unmodifiable collection từ chối mutation.
- [ ] Unmodifiable wrapper được phân biệt với snapshot từ nguồn mutable.
- [ ] `Arrays.asList()` được kiểm tra như fixed-size list.
- [ ] Null và duplicate factory contracts được kiểm thử.
- [ ] Không có assertion phụ thuộc implementation class, object identity hoặc iteration order không được bảo đảm.

## 13. Tài liệu tham khảo chính thức

- [Java SE 21 API — `SequencedCollection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): `reversed`, thao tác first/last và reverse-ordered view.
- [Java SE 21 API — `SequencedSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html): sequenced set và reversed view.
- [Java SE 21 API — `SequencedMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): `reversed`, sequenced key/value/entry views và thao tác hai đầu.
- [Java SE 21 API — `List`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html): `reversed`, `of` và `copyOf`.
- [Java SE 21 API — `LinkedHashSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html): encounter order và sequenced operations.
- [Java SE 21 API — `LinkedHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): encounter order và sequenced map operations.
- [Java SE 21 API — `Collections`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): unmodifiable sequenced wrappers.
- [Java SE 21 API — `Arrays.asList`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size list backed by array.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter tests và assertions.
