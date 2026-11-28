# Kiểm thử danh sách rỗng, null, thứ tự, kiểu generic và quyền sửa

Khi dùng `Stream.toList()`, test nên xác minh hợp đồng mà Java API công bố: kết quả là `List<T>` không sửa đổi được, giữ encounter order nếu stream có thứ tự, và chứa các phần tử mà pipeline phát ra. Bộ kiểm thử cần bao phủ cả trường hợp biên như stream rỗng, phần tử `null`, phần tử trùng lặp, stream song song và kiểu generic.

Một điểm quan trọng là tách **kiểm tra lúc biên dịch** khỏi **kiểm tra lúc chạy**. Kiểu generic như `List<Animal>` được compiler kiểm tra khi biên dịch; mutability, nội dung và thứ tự có thể được kiểm tra bằng JUnit. Không dùng tên lớp triển khai hoặc `getClass()` để suy luận generic type hay hành vi của kết quả.

## 1. Xác định hợp đồng cần kiểm thử

`Stream.toList()` có từ Java 16 và trả về `List<T>` unmodifiable. Trước khi viết test, hãy xác định các bảo đảm cần giữ:

| Thuộc tính | Hợp đồng cần kiểm tra |
| --- | --- |
| Kiểu kết quả | `List<T>` theo kiểu phần tử của stream. |
| Stream rỗng | Trả danh sách rỗng, không phải `null`. |
| Phần tử null | Được giữ lại nếu stream phát ra `null`. |
| Encounter order | Được giữ nếu stream có encounter order. |
| Phần tử trùng lặp | Được giữ; `toList()` không tự loại trùng. |
| Quyền sửa cấu trúc | Mutator ném `UnsupportedOperationException`. |
| Kiểu triển khai | Không được API bảo đảm; không kiểm tra bằng tên lớp. |
| Kiểu generic | Compiler kiểm tra; generic type bị type erasure khi chạy. |

Ví dụ cơ bản:

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream().toList();
```

Biến `names` có kiểu tĩnh `List<String>`. Caller có thể đọc và duyệt danh sách, nhưng không được sửa cấu trúc của nó.

## 2. Kiểm thử stream rỗng

Khi không có phần tử nào được phát ra, `toList()` trả một danh sách rỗng. Kết quả không phải `null` và vẫn unmodifiable:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class EmptyStreamTest {
    @Test
    void returnsAnEmptyList() {
        List<String> result = Stream.<String>empty().toList();

        assertNotNull(result);
        assertTrue(result.isEmpty());
        assertEquals(0, result.size());
        assertThrows(UnsupportedOperationException.class,
            () -> result.add("An"));
    }
}
```

Test này chỉ kiểm tra hợp đồng rỗng. Không nên assert lớp thực tế là `List.of()` hoặc một implementation cụ thể, vì Java API không cam kết lớp đó.

## 3. Kiểm thử phần tử null

Stream có thể phát ra `null`, và `Stream.toList()` giữ lại phần tử đó. Khi viết expected value, không dùng `List.of(...)` vì factory này từ chối `null`; dùng `Arrays.asList(...)` hoặc một cách tạo expected phù hợp:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class NullElementTest {
    @Test
    void keepsNullElements() {
        List<String> result = Stream.<String>of("An", null, "Bình").toList();

        assertEquals(Arrays.asList("An", null, "Bình"), result);
        assertNull(result.get(1));
    }
}
```

Phân biệt rõ ba trường hợp:

- Stream có một phần tử `null`: `toList()` giữ phần tử đó.
- Stream rỗng: `toList()` trả danh sách rỗng.
- Tham chiếu stream là `null`: không thể gọi `.toList()`; chương trình sẽ ném `NullPointerException` khi dereference tham chiếu.

Đừng nhầm `Stream.toList()` với `Collectors.toUnmodifiableList()` hoặc `List.of()`: các API unmodifiable đó từ chối phần tử `null`. Khi refactor từ một collector khác, cần xác định rõ null policy của dữ liệu và của API đích.

## 4. Kiểm thử encounter order trên stream tuần tự và song song

Với nguồn có encounter order như `List`, `toList()` giữ thứ tự đó. Bảo đảm này vẫn áp dụng khi pipeline chạy song song, miễn là pipeline không loại bỏ encounter order:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class EncounterOrderTest {
    @Test
    void preservesOrderForSequentialAndParallelStreams() {
        List<Integer> source = IntStream.rangeClosed(1, 1_000)
            .boxed()
            .toList();

        List<Integer> expected = IntStream.rangeClosed(1, 1_000)
            .map(number -> number * 2)
            .boxed()
            .toList();

        List<Integer> sequential = source.stream()
            .map(number -> number * 2)
            .toList();

        List<Integer> parallel = source.parallelStream()
            .map(number -> number * 2)
            .toList();

        assertEquals(expected, sequential);
        assertEquals(expected, parallel);
    }
}
```

Không dùng `Thread.sleep()` hoặc giả lập thời gian xử lý để ép thứ tự. Test nên kiểm tra kết quả được API bảo đảm, không kiểm tra thread nào chạy mapper trước. Mapper trong ví dụ là stateless và không có side effect nên kết quả có thể dự đoán.

## 5. Kiểm thử phần tử trùng lặp

`toList()` thu thập mọi phần tử mà pipeline phát ra. Nó không có chức năng loại bỏ phần tử trùng lặp:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class DuplicateElementTest {
    @Test
    void preservesDuplicatesAndTheirPositions() {
        List<String> result = Stream.of("A", "B", "A", "C", "B").toList();

        assertEquals(List.of("A", "B", "A", "C", "B"), result);
    }
}
```

Nếu nghiệp vụ yêu cầu loại trùng, hãy thêm `distinct()` vào pipeline và test riêng hành vi đó:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class DistinctElementTest {
    @Test
    void removesDuplicatesWhenDistinctIsRequested() {
        List<String> unique = Stream.of("A", "B", "A", "C", "B")
            .distinct()
            .toList();

        assertEquals(List.of("A", "B", "C"), unique);
    }
}
```

Không chuyển expected hoặc actual sang `Set` trong test cần xác minh số lần xuất hiện, vì `Set` làm mất thông tin duplicate.

## 6. Không giả định thứ tự với nguồn unordered

`HashSet` không cam kết encounter order. Khi lấy stream từ nguồn như vậy, không nên kiểm tra kết quả bằng một list có thứ tự cố định. Hãy kiểm tra tập giá trị và số lượng phần tử:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class UnorderedSourceTest {
    @Test
    void checksElementsWithoutAssumingIterationOrder() {
        Set<String> source = new HashSet<>(List.of("An", "Bình", "Chi"));
        List<String> result = source.stream().toList();

        assertEquals(3, result.size());
        assertEquals(Set.of("An", "Bình", "Chi"), new HashSet<>(result));
    }
}
```

Nếu thứ tự là yêu cầu nghiệp vụ, hãy tạo thứ tự tường minh bằng `sorted(comparator)` hoặc dùng một nguồn có encounter order. Không để test phụ thuộc vào thứ tự tình cờ của `HashSet` trên một máy hay một phiên bản JDK.

## 7. Kiểm thử quyền sửa: mutator phải ném exception

`Stream.toList()` trả danh sách unmodifiable. Các phương thức thay đổi cấu trúc hoặc phần tử đều phải ném `UnsupportedOperationException`:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class UnmodifiableListTest {
    @Test
    void rejectsMutatingOperations() {
        List<String> result = List.of("An", "Bình", "Chi").stream().toList();

        assertThrows(UnsupportedOperationException.class,
            () -> result.add("Dung"));
        assertThrows(UnsupportedOperationException.class,
            () -> result.addAll(List.of("Dung")));
        assertThrows(UnsupportedOperationException.class,
            () -> result.set(0, "Anh"));
        assertThrows(UnsupportedOperationException.class,
            () -> result.remove("An"));
        assertThrows(UnsupportedOperationException.class,
            () -> result.remove(0));
        assertThrows(UnsupportedOperationException.class, result::clear);
        assertThrows(UnsupportedOperationException.class,
            () -> result.sort(String::compareTo));
        assertThrows(UnsupportedOperationException.class,
            () -> result.replaceAll(String::toUpperCase));
        assertThrows(UnsupportedOperationException.class,
            () -> result.removeIf(String::isBlank));
    }
}
```

Không chỉ kiểm tra `add()`. Code thực tế có thể sửa list bằng `set()`, `sort()`, `replaceAll()`, `removeIf()`, iterator hoặc view như `subList()`. Hãy kiểm tra những thao tác mà consumer của ứng dụng thực sự gọi.

Unmodifiable áp dụng cho cấu trúc list, không có nghĩa object phần tử trở thành immutable. Ví dụ, nếu phần tử là `StringBuilder`, caller vẫn có thể thay đổi trạng thái của object qua `get()`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class ElementMutabilityTest {
    @Test
    void listStructureIsUnmodifiableButElementCanStillBeMutable() {
        StringBuilder value = new StringBuilder("Java");
        List<StringBuilder> result = Stream.of(value).toList();

        result.get(0).append(" 16");

        assertEquals("Java 16", result.get(0).toString());
    }
}
```

Đây là khác biệt giữa unmodifiable collection và deep immutability. Nếu cần dữ liệu không thay đổi sâu, hãy dùng phần tử immutable hoặc tạo snapshot độc lập cho từng phần tử.

## 8. Kiểm tra kiểu generic ở thời điểm biên dịch

`toList()` trả về `List<T>` theo kiểu phần tử của stream. Compiler kiểm tra việc gán generic; không thể dùng một assertion runtime để chứng minh đầy đủ kiểu tham số vì Java thực hiện type erasure.

Ví dụ widening từ subtype sang supertype bằng type witness:

```java
import java.util.List;

class Animal {
    private final String name;

    Animal(String name) { this.name = name; }
    String name() { return name; }
}

class Dog extends Animal {
    Dog(String name) { super(name); }
}

class GenericTypeTest {
    static List<Animal> collectAnimals(List<Dog> dogs) {
        return dogs.stream()
            .<Animal>map(dog -> dog)
            .toList();
    }
}
```

Kiểu trả về `List<Animal>` được compiler kiểm tra ngay trong method. Nếu bỏ `.<Animal>map(...)` và viết `return dogs.stream().toList();`, biểu thức có kiểu `List<Dog>` và không thể gán cho `List<Animal>` do generic invariance.

Đoạn sau là ví dụ cố ý không biên dịch:

```java
import java.util.List;

class Animal {}
class Dog extends Animal {}

class InvalidGenericAssignment {
    static List<Animal> collect(List<Dog> dogs) {
        return dogs.stream().toList();
        // Compile error: List<Dog> is not convertible to List<Animal>
    }
}
```

Không đưa một dòng không biên dịch vào test JUnit đang chạy. Hãy kiểm tra nó bằng một compile-fail fixture riêng nếu dự án có hạ tầng kiểm thử compiler; với test ứng dụng thông thường, một method trả `List<Animal>` như ví dụ trên đã xác nhận đường gán hợp lệ.

Nếu API chỉ cần đọc các subtype, có thể dùng wildcard:

```java
import java.util.List;

class Animal {}
class Dog extends Animal {}

class WildcardGenericAssignment {
    static List<? extends Animal> collect(List<Dog> dogs) {
        return dogs.stream().toList();
    }
}
```

Không dùng `getClass()` hoặc tên lớp thực tế để kiểm tra generic parameter. Runtime class không cho biết đầy đủ `List<Dog>` hay `List<Animal>` sau type erasure.

## 9. Kiểm tra bằng một bộ JUnit tổng hợp

Với dự án đã dùng JUnit 5, có thể gom các trường hợp chính vào một test class. Ví dụ dưới đây tập trung vào hợp đồng của API; các test chuyên biệt ở các phần trước giúp cô lập nguyên nhân khi có lỗi:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class StreamToListContractTest {
    @Test
    void emptyStreamProducesEmptyList() {
        List<String> result = Stream.<String>empty().toList();

        assertTrue(result.isEmpty());
        assertEquals(0, result.size());
    }

    @Test
    void nullElementIsPreserved() {
        List<String> result = Stream.<String>of("A", null, "B").toList();

        assertEquals(Arrays.asList("A", null, "B"), result);
    }

    @Test
    void duplicatesAndEncounterOrderArePreserved() {
        List<String> result = Stream.of("A", "B", "A").toList();

        assertEquals(List.of("A", "B", "A"), result);
    }

    @Test
    void listCannotBeModified() {
        List<String> result = Stream.of("A", "B").toList();

        assertThrows(UnsupportedOperationException.class,
            () -> result.add("C"));
        assertThrows(UnsupportedOperationException.class,
            () -> result.set(0, "X"));
    }
}
```

Test tổng hợp này không thay thế test parallel order, unordered source, generic compile-time hoặc các consumer cụ thể. Nó cung cấp một kiểm tra nhanh cho các đặc tính cơ bản của `Stream.toList()`.

## 10. Những lỗi kiểm thử thường gặp

| Cách kiểm thử sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Assert kết quả luôn là `ArrayList` | API không cam kết lớp triển khai. | Assert kiểu interface và hành vi được bảo đảm. |
| Dùng `List.of("A", null)` làm expected | `List.of()` từ chối null. | Dùng `Arrays.asList()` hoặc expected collection cho phép null. |
| Assert thứ tự của `HashSet` | Nguồn không có encounter order. | So sánh tập giá trị và số lượng, hoặc sắp xếp rõ ràng. |
| Chỉ test `add()` | Consumer có thể dùng mutator khác. | Test các thao tác sửa thực tế như `set`, `sort`, `removeIf`. |
| Dùng `==` để so sánh nội dung | `==` so sánh reference identity. | Dùng `equals()` hoặc assertion nội dung. |
| Dùng reflection để kiểm tra `List<Dog>` | Generic type bị erasure. | Kiểm tra assignment/return type tại compile time. |
| Chỉ test compile mà không chạy test mutability | Lỗi UOE xảy ra lúc runtime. | Kiểm tra cả kiểu biên dịch và hành vi mutator. |
| Giả định unmodifiable đồng nghĩa phần tử immutable | Danh sách chỉ khóa cấu trúc, không khóa trạng thái object bên trong. | Test hoặc thiết kế snapshot sâu khi cần. |

## 11. Kiểm tra phiên bản Java và phạm vi test

`Stream.toList()` có từ Java 16. Nếu dự án hỗ trợ Java 16 trở lên, hãy biên dịch test với đúng toolchain hoặc `--release` mà dự án công bố. Nếu baseline thấp hơn Java 16, test dùng API này sẽ không biên dịch.

Khi rà soát test suite, phân chia rõ:

- **Compile-time:** kiểu trả về, generic assignment, type witness và Java baseline.
- **Runtime:** nội dung, rỗng, null, duplicate, encounter order và mutability.
- **Contract integration:** helper hoặc API bên ngoài có sửa list hay không.
- **Concurrency:** chỉ kiểm tra parallel stream khi nghiệp vụ dùng parallel; không khẳng định thứ tự thực thi mapper.

Không cần kiểm tra mọi method của `List` trong mọi test. Hãy kiểm tra đầy đủ các hành vi mà ứng dụng dựa vào, đồng thời giữ một số test contract đại diện cho các bảo đảm cốt lõi của `toList()`.

## 12. Những điểm cần nhớ

- Stream rỗng tạo danh sách rỗng, không phải `null`.
- `Stream.toList()` giữ phần tử `null` và duplicate mà pipeline phát ra.
- Encounter order được giữ cho stream có thứ tự, kể cả khi pipeline chạy song song.
- Nguồn unordered như `HashSet` không cho phép test một thứ tự cố định.
- Mutator của danh sách kết quả ném `UnsupportedOperationException`.
- Unmodifiable list không làm các object phần tử trở thành immutable.
- Generic type phải được kiểm tra ở compile time; đừng dùng reflection hoặc tên lớp để suy luận tham số kiểu.
- Kiểm thử theo API contract và Java baseline mà dự án thực sự hỗ trợ.

Một bộ test tốt xác minh cả dữ liệu đầu ra lẫn cách caller được phép sử dụng kết quả. Khi test `Stream.toList()`, hãy kiểm tra trường hợp biên, thứ tự có bảo đảm, kiểu generic lúc biên dịch và quyền sửa lúc chạy. Nhờ vậy, refactor hoặc nâng JDK ít có nguy cơ phá vỡ hợp đồng mà ứng dụng đang dựa vào.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [List – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Java Language Specification, §4.6 – Type Erasure](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.6)
