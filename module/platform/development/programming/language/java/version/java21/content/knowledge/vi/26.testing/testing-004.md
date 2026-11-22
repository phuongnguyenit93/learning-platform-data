# Kiểm tra encounter order và write-through của reversed view

Java 21 bổ sung Sequenced Collections với phương thức `reversed()` để cung cấp một view có encounter order đảo ngược. View này được backing bởi collection gốc: thay đổi được hỗ trợ qua view sẽ được phản ánh vào collection gốc và ngược lại.

Khi kiểm thử, cần xác minh riêng hai hợp đồng: **encounter order** (thứ tự duyệt) và **write-through** (thay đổi đi qua lại giữa view và collection gốc). Không thể chỉ dùng `equals()` của `Set` hoặc `Map` để kiểm tra thứ tự, vì equality của hai loại collection này không phụ thuộc encounter order.

## 1. Những thuộc tính cần kiểm thử

Một bộ contract test cho `reversed()` nên bao gồm:

1. View duyệt các phần tử theo thứ tự ngược với collection gốc.
2. Thay đổi qua view được phản ánh vào collection gốc.
3. Thay đổi collection gốc được phản ánh vào view.
4. Gọi `reversed()` trên reverse view trả lại collection gốc theo hợp đồng API.
5. Với collection không thể sửa đổi, thao tác ghi qua view vẫn bị từ chối.
6. Assertion kiểm tra thứ tự phải dựa trên iteration hoặc snapshot có thứ tự.

Các ví dụ dùng JUnit Jupiter và API Java 21 đã final. Có thể đặt test trong source set kiểm thử của dự án; không cần bật Preview.

## 2. Kiểm tra encounter order của List

Với `List`, equality đã xét thứ tự, nhưng dùng `assertIterableEquals` giúp thể hiện trực tiếp rằng test đang xác minh encounter order của view.

```java
import static org.junit.jupiter.api.Assertions.assertIterableEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ReversedListViewTest {
    @Test
    void reversedViewUsesReverseEncounterOrder() {
        List<String> original =
                new ArrayList<>(List.of("An", "Binh", "Chi"));

        List<String> reversed = original.reversed();

        assertIterableEquals(
                List.of("Chi", "Binh", "An"),
                reversed);

        // Collection gốc vẫn giữ thứ tự ban đầu.
        assertIterableEquals(
                List.of("An", "Binh", "Chi"),
                original);
    }
}
```

Test này kiểm tra cả hai hướng quan sát: view có thứ tự đảo ngược, còn collection gốc không bị đảo tại chỗ chỉ vì gọi `reversed()`.

`reversed()` không phải thao tác `Collections.reverse(list)`. Nó trả về view; collection gốc vẫn giữ encounter order vốn có.

## 3. Kiểm tra write-through từ view về collection gốc

Với `ArrayList`, view đảo ngược hỗ trợ cập nhật. Thao tác theo chỉ số trong view được ánh xạ sang vị trí tương ứng trong list gốc.

```java
import static org.junit.jupiter.api.Assertions.assertIterableEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ReversedListWriteThroughTest {
    @Test
    void mutationsThroughViewUpdateOriginalList() {
        List<String> original =
                new ArrayList<>(List.of("A", "B", "C"));
        List<String> reversed = original.reversed();

        // Index 0 của view là phần tử cuối của list gốc.
        reversed.set(0, "C2");
        assertIterableEquals(List.of("A", "B", "C2"), original);

        // Thêm ở đầu view tương ứng thêm ở cuối list gốc.
        reversed.add(0, "D");
        assertIterableEquals(List.of("A", "B", "C2", "D"), original);

        // Xóa index 1 của view sẽ xóa phần tử C2 trong list gốc.
        reversed.remove(1);
        assertIterableEquals(List.of("A", "B", "D"), original);
    }
}
```

Test trên xác nhận `set`, `add` và `remove` qua view đều tác động đến cùng dữ liệu. Cần chọn đúng vị trí kỳ vọng vì index của view được tính theo chiều đảo ngược.

## 4. Kiểm tra thay đổi từ collection gốc được phản ánh vào view

Write-through là quan hệ hai chiều. Sau khi tạo view, nếu collection gốc thay đổi bằng thao tác được hỗ trợ, lần duyệt tiếp theo qua view phải phản ánh dữ liệu mới.

```java
import static org.junit.jupiter.api.Assertions.assertIterableEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ReversedListBackingTest {
    @Test
    void mutationsToOriginalAreVisibleThroughView() {
        List<String> original =
                new ArrayList<>(List.of("A", "B", "C"));
        List<String> reversed = original.reversed();

        original.add(0, "START");
        assertIterableEquals(
                List.of("C", "B", "A", "START"),
                reversed);

        original.set(1, "B2");
        assertIterableEquals(
                List.of("C", "B2", "A", "START"),
                reversed);
    }
}
```

Không sửa cấu trúc collection trong lúc đang duyệt view, trừ khi iterator đang dùng hỗ trợ rõ thao tác đó. Việc sửa collection từ một reference khác trong khi iteration diễn ra có thể làm kết quả iteration không xác định hoặc kích hoạt cơ chế fail-fast của implementation.

## 5. Kiểm tra reversed hai lần

Hợp đồng của `SequencedCollection.reversed()` quy định reverse view có `reversed()` trả lại collection ban đầu. Có thể kiểm tra cả danh tính object và encounter order:

```java
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class DoubleReverseTest {
    @Test
    void reversingTheReverseViewReturnsOriginalCollection() {
        List<String> original =
                new ArrayList<>(List.of("A", "B", "C"));

        List<String> reversed = original.reversed();
        List<String> twice = reversed.reversed();

        assertSame(original, twice);
        assertIterableEquals(List.of("A", "B", "C"), twice);
    }
}
```

`assertSame` kiểm tra reference được trả lại đúng collection gốc theo hợp đồng view. `assertIterableEquals` kiểm tra encounter order mà caller quan sát được. Hai assertion này kiểm tra hai thuộc tính khác nhau.

## 6. Kiểm tra SequencedSet mà không nhầm với Set.equals

`SequencedSet` giữ tính duy nhất của `Set` và encounter order của `SequencedCollection`. Tuy nhiên, `Set.equals()` vẫn chỉ so sánh tập phần tử, không so sánh thứ tự. Vì vậy, dùng `assertEquals(setA, setB)` không đủ để chứng minh reverse view có đúng thứ tự.

Với `LinkedHashSet`, có thể kiểm tra thứ tự bằng cách duyệt view hoặc chuyển thành `List` snapshot:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;
import org.junit.jupiter.api.Test;

class ReversedSetViewTest {
    @Test
    void reversedSetHasReverseOrderAndWritesThrough() {
        SequencedSet<String> original = new LinkedHashSet<>();
        original.addLast("A");
        original.addLast("B");
        original.addLast("C");

        SequencedSet<String> reversed = original.reversed();

        assertIterableEquals(
                List.of("C", "B", "A"),
                new ArrayList<>(reversed));

        // addFirst trên view tương ứng addLast trên set gốc.
        reversed.addFirst("D");
        assertIterableEquals(
                List.of("A", "B", "C", "D"),
                new ArrayList<>(original));

        // Set equality không xét encounter order.
        assertEquals(original, reversed);
    }
}
```

Assertion cuối cùng có chủ ý: hai set bằng nhau theo hợp đồng `Set`, dù thứ tự duyệt của chúng ngược nhau. Assertion kiểm tra order phải dùng `new ArrayList<>(...)` hoặc một phép duyệt có thứ tự.

`addFirst` và `addLast` là optional operations. Ví dụ trên gắn với `LinkedHashSet`, implementation hỗ trợ reposition ở hai đầu. Không áp dụng kỳ vọng này cho mọi `SequencedSet`; chẳng hạn thứ tự của `TreeSet` do comparator quyết định và các thao tác thêm tùy ý vào đầu/cuối không được hỗ trợ.

## 7. Kiểm tra SequencedMap theo thứ tự entry

`SequencedMap.reversed()` trả về view đảo ngược thứ tự entry. `Map.equals()` không xét thứ tự entry, do đó cần kiểm tra `sequencedEntrySet()` theo iteration order.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.SequencedMap;
import org.junit.jupiter.api.Test;

class ReversedMapViewTest {
    @Test
    void reversedMapViewPreservesWriteThroughAndEntryOrder() {
        SequencedMap<String, Integer> original = new LinkedHashMap<>();
        original.putLast("A", 1);
        original.putLast("B", 2);
        original.putLast("C", 3);

        SequencedMap<String, Integer> reversed = original.reversed();

        assertIterableEquals(
                List.of(
                        Map.entry("C", 3),
                        Map.entry("B", 2),
                        Map.entry("A", 1)),
                new ArrayList<>(reversed.sequencedEntrySet()));

        // putFirst trên view tương ứng putLast trên map gốc.
        reversed.putFirst("D", 4);
        assertIterableEquals(
                List.of(
                        Map.entry("A", 1),
                        Map.entry("B", 2),
                        Map.entry("C", 3),
                        Map.entry("D", 4)),
                new ArrayList<>(original.sequencedEntrySet()));

        // Cập nhật value qua view cũng cập nhật map gốc.
        reversed.put("B", 20);
        assertEquals(20, original.get("B"));

        // Map equality không xét thứ tự entry.
        assertEquals(original, reversed);
    }
}
```

Trong test map, `new ArrayList<>(reversed.sequencedEntrySet())` tạo snapshot có encounter order tại thời điểm assertion. `Map.entry(...)` phù hợp với dữ liệu ví dụ không chứa null; nếu test cho phép key/value null, hãy dùng entry implementation phù hợp thay vì `Map.entry`.

## 8. Kiểm tra view của collection không thể sửa đổi

`reversed()` không làm một collection bất biến trở thành mutable. Nếu collection gốc không hỗ trợ thao tác ghi, reverse view cũng không hỗ trợ thao tác ghi tương ứng.

```java
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class ImmutableReversedViewTest {
    @Test
    void reverseViewOfImmutableListRejectsMutation() {
        List<String> original = List.of("A", "B", "C");
        List<String> reversed = original.reversed();

        assertIterableEquals(List.of("C", "B", "A"), reversed);
        assertThrows(
                UnsupportedOperationException.class,
                () -> reversed.add("D"));
    }
}
```

Test này tách biệt hai hợp đồng: đọc view vẫn hoạt động, còn ghi bị từ chối. Không chỉ kiểm tra `add`; tùy loại collection, có thể kiểm tra thêm `set`, `remove`, `clear` hoặc các thao tác đầu/cuối mà implementation công bố là không hỗ trợ.

## 9. Không dùng equals để kiểm tra thứ tự của Set và Map

Các phép so sánh dưới đây không xác nhận encounter order:

```java
// Set.equals() không xét thứ tự phần tử.
assertEquals(set, set.reversed());

// Map.equals() không xét thứ tự entry.
assertEquals(map, map.reversed());
```

Để xác nhận thứ tự, chuyển view thành list hoặc thu thập phần tử theo iteration order:

```java
List<String> actualSetOrder = new ArrayList<>(sequencedSet.reversed());
List<Map.Entry<String, Integer>> actualMapOrder =
        new ArrayList<>(sequencedMap.reversed().sequencedEntrySet());
```

List equality xét cả phần tử lẫn vị trí, vì vậy có thể dùng `assertEquals(expected, actual)` hoặc `assertIterableEquals(expected, actual)`. Nếu collection cho phép `null`, ưu tiên `new ArrayList<>(view)`; `List.copyOf(view)` từ chối phần tử null.

## 10. Một helper nhỏ để tái sử dụng assertion

Khi có nhiều loại sequenced collection, có thể tạo helper nhận `Iterable` để xác nhận encounter order:

```java
import static org.junit.jupiter.api.Assertions.assertIterableEquals;

import java.util.List;

static <T> void assertEncounterOrder(
        List<T> expected, Iterable<T> actual) {
    assertIterableEquals(expected, actual);
}
```

Với map, truyền `sequencedEntrySet()` vào helper để so sánh thứ tự entry. Với set hoặc collection, truyền trực tiếp view. Helper không cần biết implementation cụ thể; trách nhiệm chọn implementation có encounter order được cam kết thuộc về test fixture.

Không viết helper dựa vào `toString()` của collection. Chuỗi hiển thị không phải hợp đồng kiểm thử tốt bằng việc duyệt phần tử theo API.

## 11. Những giới hạn khi kiểm thử backed view

- **Implementation phải hỗ trợ thao tác:** write-through chỉ áp dụng với các thao tác mà collection nền cho phép. Collection bất biến hoặc operation không hỗ trợ có thể ném `UnsupportedOperationException`.
- **Kiểm tra đúng encounter order:** `HashSet` và các collection không cam kết thứ tự không phù hợp để assert một chuỗi thứ tự cố định.
- **Không sửa đồng thời trong lúc duyệt:** tránh thay đổi collection qua reference khác trong khi iterator của view đang chạy.
- **Không nhầm view với snapshot:** view phản ánh thay đổi; snapshot như `new ArrayList<>(view)` giữ thứ tự tại thời điểm tạo và không theo dõi cập nhật về sau.
- **Equality của Set/Map không theo thứ tự:** dùng list snapshot hoặc iteration assertion để kiểm tra vị trí.
- **Kiểm thử theo hợp đồng API:** nếu cần reposition ở hai đầu, chọn implementation như `LinkedHashSet` hoặc `LinkedHashMap` có hỗ trợ và viết test gắn với implementation đó.

## 12. Chạy test với Java 21

`SequencedCollection`, `SequencedSet`, `SequencedMap` và các phương thức `reversed()` là API final trong Java 21. Test có thể biên dịch bằng release 21 mà không bật Preview.

Ví dụ chạy test JUnit Jupiter bằng Maven:

```bash
mvn -Dtest=ReversedListViewTest,ReversedListWriteThroughTest,ReversedSetViewTest,ReversedMapViewTest test
```

Đảm bảo dự án đã cấu hình JUnit Jupiter trong test dependencies và Maven Surefire tương thích với JUnit 5. Nếu dùng Gradle, cấu hình `useJUnitPlatform()` cho test task. Các lệnh trên chỉ minh họa cách chạy test trong dự án đã có cấu hình tương ứng.

## 13. Checklist cho reviewer

- [ ] Test xác nhận view có encounter order ngược với collection gốc.
- [ ] Test xác nhận mutation qua view được phản ánh vào collection gốc.
- [ ] Test xác nhận mutation từ collection gốc được phản ánh vào view.
- [ ] Test xác nhận `reversed().reversed()` trả lại collection gốc.
- [ ] Test không dùng `Set.equals()` hoặc `Map.equals()` để khẳng định thứ tự.
- [ ] Test immutable collection xác nhận thao tác ghi bị từ chối.
- [ ] Fixture dùng implementation có encounter order được cam kết.
- [ ] Không sửa collection từ reference khác trong khi đang duyệt view.

## 14. Tài liệu tham khảo

- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
- [Java SE 21 API — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [Java SE 21 API — List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html)
- [Java SE 21 API — SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html)
- [Java SE 21 API — SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
