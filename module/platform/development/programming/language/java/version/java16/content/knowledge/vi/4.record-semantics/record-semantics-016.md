# Kiểm thử equality, hash collection và đột biến từ dữ liệu bên ngoài

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, JUnit Jupiter 5 và Java hiện đại.

Record tự sinh `equals(Object)` và `hashCode()` từ các component. Điều đó giúp value object có hành vi nhất quán mà không phải viết lại hai phương thức, nhưng vẫn cần kiểm thử khi record được dùng làm khóa `HashMap`, phần tử `HashSet` hoặc chứa dữ liệu mutable.

Một bài kiểm thử hữu ích cần xác nhận bốn điều:

1. Hai record có cùng giá trị nghiệp vụ có thực sự bằng nhau không?
2. Các record bằng nhau có cùng `hashCode` không?
3. Hash collection có tìm được khóa bằng một instance khác nhưng tương đương không?
4. Thay đổi dữ liệu nguồn sau khi tạo record có làm thay đổi equality hoặc hash của record không?

Bài học sử dụng JUnit Jupiter để kiểm thử các điều kiện này. Ví dụ tập trung vào hành vi công khai của Java, không kiểm tra cấu trúc nội bộ của `HashMap` hoặc `HashSet`.

## 1. Kiểm tra equality mặc định của record

Với record chỉ chứa component immutable:

```java
record UserKey(String tenant, String username) {}

UserKey first = new UserKey("acme", "linh");
UserKey second = new UserKey("acme", "linh");
UserKey anotherUser = new UserKey("acme", "minh");

System.out.println(first == second);           // false
System.out.println(first.equals(second));      // true
System.out.println(first.equals(anotherUser)); // false
```

Hai instance riêng biệt có cùng component phải bằng nhau theo `equals`. Khi kiểm thử `equals`, cần kiểm tra các tính chất trong hợp đồng `Object.equals`:

- **Phản xạ:** một object phải bằng chính nó.
- **Đối xứng:** nếu `a.equals(b)` là true thì `b.equals(a)` cũng phải true.
- **Bắc cầu:** nếu `a.equals(b)` và `b.equals(c)` là true thì `a.equals(c)` cũng phải true.
- **Nhất quán:** khi dữ liệu tham gia equality không đổi, kết quả so sánh phải ổn định.
- **Khác null:** một object không được bằng `null`.

Một test JUnit Jupiter có thể kiểm tra các điều kiện cơ bản:

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class RecordEqualityTest {
    record UserKey(String tenant, String username) {}

    @Test
    void generatedEqualityFollowsRecordComponents() {
        UserKey first = new UserKey("acme", "linh");
        UserKey second = new UserKey("acme", "linh");
        UserKey third = new UserKey("acme", "linh");
        UserKey different = new UserKey("acme", "minh");

        assertEquals(first, first);       // Phản xạ
        assertEquals(first, second);
        assertEquals(second, first);      // Đối xứng
        assertEquals(second, third);
        assertEquals(first, third);       // Bắc cầu
        assertNotEquals(first, different);
        assertNotEquals(first, null);
        assertFalse(first.equals("acme/linh"));
    }
}
```

Đối với record mặc định, compiler tạo `equals` theo lớp record và component. Test vẫn có giá trị vì nó xác nhận hợp đồng mà ứng dụng dựa vào, đồng thời phát hiện sớm nếu sau này record được tùy biến hoặc component thay đổi.

## 2. Kiểm tra hashCode nhất quán với equals

Hợp đồng `Object.hashCode` yêu cầu hai object bằng nhau theo `equals` phải có cùng mã băm. Chiều ngược lại không bắt buộc: hai object khác nhau vẫn có thể có cùng hash do va chạm.

```java
@Test
void equalRecordsHaveEqualHashCodes() {
    UserKey first = new UserKey("acme", "linh");
    UserKey second = new UserKey("acme", "linh");

    assertEquals(first, second);
    assertEquals(first.hashCode(), second.hashCode());

    int initialHash = first.hashCode();
    assertEquals(initialHash, first.hashCode());
}
```

Không viết test yêu cầu hai record khác nhau luôn có hash khác nhau. Hash collision là hợp lệ; điều cần bảo đảm là equality kéo theo hash bằng nhau.

Nếu record ghi đè `equals` hoặc `hashCode`, các test này càng quan trọng. Chỉ ghi đè một phương thức có thể làm hai record bằng nhau nhưng có hash khác nhau, khiến lookup trong hash collection sai hợp đồng.

## 3. Kiểm tra hành vi HashSet và HashMap

`HashSet` không giữ hai phần tử bằng nhau theo `equals`. `HashMap` xem hai khóa bằng nhau là cùng một mapping; lần `put` tiếp theo cập nhật giá trị của mapping đó.

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

UserKey first = new UserKey("acme", "linh");
UserKey equivalent = new UserKey("acme", "linh");

Set<UserKey> users = new HashSet<>();
users.add(first);
users.add(equivalent);
System.out.println(users.size()); // 1

Map<UserKey, String> names = new HashMap<>();
names.put(first, "Linh");
names.put(equivalent, "Linh Nguyen");
System.out.println(names.size()); // 1
System.out.println(names.get(first)); // Linh Nguyen
```

Test tương ứng:

```java
@Test
void hashCollectionsUseRecordValueEquality() {
    UserKey first = new UserKey("acme", "linh");
    UserKey equivalent = new UserKey("acme", "linh");

    Set<UserKey> users = new HashSet<>();
    assertTrue(users.add(first));
    assertFalse(users.add(equivalent));
    assertEquals(1, users.size());
    assertTrue(users.contains(equivalent));

    Map<UserKey, String> names = new HashMap<>();
    names.put(first, "Linh");
    names.put(equivalent, "Linh Nguyen");

    assertEquals(1, names.size());
    assertEquals("Linh Nguyen", names.get(first));
    assertEquals("Linh Nguyen", names.get(equivalent));
}
```

Dùng một instance mới tương đương để gọi `contains` và `get` là cách kiểm tra quan trọng. Nếu chỉ tra cứu bằng đúng instance đã chèn, test có thể không phát hiện lỗi trong `equals` hoặc `hashCode`.

## 4. Kiểm tra snapshot trước đột biến từ collection bên ngoài

Nếu record giữ collection mutable trực tiếp, mã gọi vẫn có thể sửa component thông qua tham chiếu nguồn. Với danh sách chứa `String`, tạo snapshot trong compact constructor:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record SearchKey(List<String> filters) {
    SearchKey {
        filters = List.copyOf(
            new ArrayList<>(
                Objects.requireNonNull(filters, "filters")
            )
        );
    }
}
```

Constructor tạo một bản sao cấu trúc độc lập rồi lưu danh sách không thể sửa. Phần tử `String` immutable nên không có trạng thái phần tử nào bị thay đổi từ bên ngoài.

Test cần kiểm tra dữ liệu đọc được, mã băm và khả năng dùng khóa trong collection:

```java
@Test
void externalListMutationDoesNotChangeRecordKey() {
    List<String> source = new ArrayList<>(List.of("java"));
    SearchKey key = new SearchKey(source);

    int originalHash = key.hashCode();
    Set<SearchKey> keys = new HashSet<>();
    keys.add(key);

    Map<SearchKey, String> cache = new HashMap<>();
    cache.put(key, "cached result");

    source.add("records");

    assertEquals(List.of("java"), key.filters());
    assertEquals(originalHash, key.hashCode());
    assertTrue(keys.contains(new SearchKey(List.of("java"))));
    assertEquals(
        "cached result",
        cache.get(new SearchKey(List.of("java")))
    );
    assertThrows(
        UnsupportedOperationException.class,
        () -> key.filters().add("streams")
    );
}
```

Test này chứng minh rằng:

- Sửa collection nguồn không sửa snapshot của record.
- Hash của khóa giữ nguyên sau thao tác bên ngoài.
- Một record mới có cùng giá trị vẫn tìm được phần tử trong `HashSet` và mapping trong `HashMap`.
- Accessor không cho sửa cấu trúc danh sách đã lưu.

Không chỉ kiểm tra accessor trả về danh sách không thể sửa. Một wrapper không thể sửa có thể vẫn phản ánh mutation từ collection nguồn; vì vậy test cần sửa chính nguồn sau khi tạo record.

## 5. Phân biệt snapshot collection với sao chép nông phần tử

`List.copyOf` bảo vệ cấu trúc danh sách, nhưng không sao chép sâu từng phần tử. Nếu phần tử là object mutable và `equals`/`hashCode` của nó dựa trên trạng thái mutable, record vẫn có thể đổi equality và hash sau khi object bên ngoài bị sửa.

Ví dụ:

```java
import java.util.List;
import java.util.Objects;

final class MutableTag {
    private String name;

    MutableTag(String name) {
        this.name = Objects.requireNonNull(name);
    }

    void rename(String newName) {
        name = Objects.requireNonNull(newName);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableTag that
            && name.equals(that.name);
    }

    @Override
    public int hashCode() {
        return name.hashCode();
    }
}

record UnsafeTags(List<MutableTag> tags) {
    UnsafeTags {
        tags = List.copyOf(tags);
    }
}
```

Test thể hiện mutation đi xuyên qua snapshot nông:

```java
@Test
void mutableElementCanStillChangeRecordEqualityAndHash() {
    MutableTag tag = new MutableTag("java");
    UnsafeTags key = new UnsafeTags(List.of(tag));
    UnsafeTags expected = new UnsafeTags(
        List.of(new MutableTag("java"))
    );

    assertEquals(key, expected);

    tag.rename("records");

    assertNotEquals(key, expected);
}
```

Đây là test cho thấy danh sách đã được snapshot nhưng object phần tử vẫn dùng chung. Nếu record được dùng làm key hoặc Set element, trạng thái tham gia equality/hash không còn ổn định. Test chỉ khẳng định equality thay đổi; không yêu cầu hash mới phải khác hash cũ vì hai giá trị hash khác nhau vẫn có thể va chạm.

Không nên viết test khẳng định `HashSet.contains(key)` chắc chắn trả về `false` sau mutation. Hợp đồng `Set` quy định hành vi không xác định nếu một phần tử bị thay đổi theo cách ảnh hưởng đến equality khi đang ở trong set. Kết quả cụ thể còn phụ thuộc hash mới và cấu trúc nội bộ; điều cần kiểm tra là thiết kế đã để trạng thái khóa thay đổi, và cần sửa bằng immutable element hoặc deep snapshot.

## 6. Kiểm tra array component có defensive copy

Mảng Java so sánh theo identity nếu dùng `equals`/`hashCode` mặc định. Nếu mảng đại diện cho một value theo nội dung, record cần:

- Clone mảng đầu vào trong constructor.
- Clone mảng khi trả từ accessor.
- Dùng `Arrays.equals` và `Arrays.hashCode` cho equality/hash theo nội dung.

Ví dụ:

```java
import java.util.Arrays;
import java.util.Objects;

record ByteKey(byte[] bytes) {
    ByteKey {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
            || (other instanceof ByteKey that
                && Arrays.equals(bytes, that.bytes));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
```

Test cả alias đầu vào và alias đầu ra:

```java
@Test
void arrayInputAndAccessorCannotMutateRecordValue() {
    byte[] source = {1, 2, 3};
    ByteKey key = new ByteKey(source);

    int originalHash = key.hashCode();
    source[0] = 99;

    byte[] exposed = key.bytes();
    exposed[1] = 88;

    assertArrayEquals(new byte[] {1, 2, 3}, key.bytes());
    assertEquals(originalHash, key.hashCode());

    ByteKey equivalent = new ByteKey(new byte[] {1, 2, 3});
    assertEquals(key, equivalent);
    assertEquals(key.hashCode(), equivalent.hashCode());
}
```

Nếu chỉ clone ở accessor, test thay đổi `source` sẽ thất bại. Nếu chỉ clone trong constructor, test thay đổi `exposed` sẽ thất bại. Hai đường alias cần được kiểm tra riêng.

Với mảng lồng nhau, `clone()` chỉ sao chép nông mảng ngoài. Cần thay đổi cả mảng con trong test nếu record tuyên bố bảo vệ toàn bộ cấu trúc.

## 7. Tổ chức bộ test JUnit

Các test trên có thể đặt trong cùng một class test. Một khung tổ chức gọn:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.Test;

class RecordEqualityTest {
    record UserKey(String tenant, String username) {}

    record SearchKey(List<String> filters) {
        SearchKey {
            filters = List.copyOf(
                new ArrayList<>(
                    Objects.requireNonNull(filters, "filters")
                )
            );
        }
    }

    record ByteKey(byte[] bytes) {
        ByteKey {
            bytes = Objects.requireNonNull(bytes, "bytes").clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                || (other instanceof ByteKey that
                    && Arrays.equals(bytes, that.bytes));
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }
    }

    @Test
    void equalRecordsWorkAsHashKeys() {
        UserKey first = new UserKey("acme", "linh");
        UserKey second = new UserKey("acme", "linh");

        assertEquals(first, second);
        assertEquals(first.hashCode(), second.hashCode());

        Set<UserKey> set = new HashSet<>(List.of(first));
        Map<UserKey, String> map = new HashMap<>();
        map.put(first, "Linh");

        assertTrue(set.contains(second));
        assertEquals("Linh", map.get(second));
    }

    @Test
    void sourceMutationDoesNotChangeSnapshotKey() {
        List<String> source = new ArrayList<>(List.of("java"));
        SearchKey key = new SearchKey(source);
        int originalHash = key.hashCode();

        source.add("records");

        assertEquals(List.of("java"), key.filters());
        assertEquals(originalHash, key.hashCode());
    }

    @Test
    void arrayIsCopiedAtInputAndOutputBoundaries() {
        byte[] source = {1, 2, 3};
        ByteKey key = new ByteKey(source);
        source[0] = 99;

        byte[] exposed = key.bytes();
        exposed[1] = 88;

        assertArrayEquals(new byte[] {1, 2, 3}, key.bytes());
        assertEquals(key, new ByteKey(new byte[] {1, 2, 3}));
    }
}
```

Đây là khung rút gọn để thấy cách tổ chức test theo từng hợp đồng. Trong dự án, giữ các test riêng cho mutable nested element và các trường hợp biên để lỗi được định vị dễ hơn. Không cần gom mọi assertion vào một test dài.

## 8. Những điều không nên khẳng định trong test

| Không nên kiểm tra | Vì sao | Kiểm tra phù hợp |
| --- | --- | --- |
| Hai object khác nhau phải có hash khác nhau | Hash collision hợp lệ | Chỉ yêu cầu object bằng nhau có hash bằng nhau |
| `HashSet.contains` luôn false sau khi sửa phần tử đã chèn | Hành vi khi element bị thay đổi ảnh hưởng equality là không xác định theo hợp đồng Set | Kiểm tra component mutation làm thay đổi equality/hash và loại bỏ thiết kế đó |
| `List.copyOf` làm phần tử mutable bất biến | Đây là snapshot nông | Sửa object phần tử bên ngoài và xác nhận test phát hiện mutation |
| Tra cứu bằng đúng instance chứng minh equality đúng | Có thể chỉ kiểm tra identity/đường đi thuận lợi | Tra cứu bằng instance mới nhưng bằng nhau |
| `toString()` giống nhau chứng minh hai record bằng nhau | `toString` là biểu diễn, không phải equality contract | Dùng `equals` và `hashCode` |
| Một lần test pass chứng minh mọi interleaving thread an toàn | Test đơn lẻ không chứng minh memory model/thread safety | Thiết kế đồng bộ hóa đúng và dùng công cụ kiểm thử concurrency chuyên biệt khi cần |

## 9. Chạy test trong dự án

Các ví dụ dùng JUnit Jupiter 5. Trong dự án đã cấu hình JUnit 5, đặt test vào source set test theo quy ước build hiện tại rồi chạy test task tương ứng. Với Maven Surefire hoặc Gradle JUnit Platform, cần bảo đảm test engine Jupiter được cấu hình.

Không cần thêm framework property-based chỉ để kiểm tra vài record nhỏ. Khi custom equality phức tạp hoặc có nhiều kiểu component, property-based testing có thể bổ sung bằng thư viện đang được dự án chấp thuận; vẫn phải giữ các test ví dụ nghiệp vụ dễ đọc.

Khi test thất bại, xác định nguyên nhân theo lớp:

1. Equality component sai so với nghiệp vụ.
2. `equals` và `hashCode` không cùng quy tắc.
3. Collection nguồn hoặc phần tử mutable vẫn được chia sẻ.
4. Accessor làm lộ tham chiếu mutable.
5. Record được dùng làm hash key trong khi trạng thái tham gia equality thay đổi.

## 10. Checklist kiểm thử record

1. Có test equality cho hai instance riêng biệt cùng component không?
2. Có test phản xạ, đối xứng, bắc cầu, nhất quán và so sánh với `null` không?
3. Có test rằng các record bằng nhau có cùng `hashCode` không?
4. Có test HashMap và HashSet bằng instance tương đương mới không?
5. Có sửa collection đầu vào sau khi tạo record để kiểm tra snapshot không?
6. Có kiểm tra accessor không cho sửa collection snapshot không?
7. Nếu collection chứa object mutable, có test mutation của chính phần tử không?
8. Nếu có array component, có test alias đầu vào và đầu ra riêng không?
9. Có tránh assert hash khác nhau cho mọi object khác nhau không?
10. Có tránh assert kết quả `contains` cụ thể sau mutation vi phạm hợp đồng Set không?
11. Test có kiểm tra hành vi công khai thay vì chi tiết nội bộ của hash collection không?
12. Các test có được chia nhỏ theo từng hợp đồng để dễ chẩn đoán không?

**Ghi nhớ:** Kiểm thử record cần xác nhận equality theo nghiệp vụ, hash nhất quán, lookup bằng instance tương đương và khả năng chống đột biến từ alias bên ngoài. Với collection, test cả việc sửa danh sách nguồn lẫn sửa phần tử mutable; với array, test cả đầu vào và đầu ra. Đừng dựa vào kết quả hash collision hoặc hành vi không được đặc tả sau khi thay đổi khóa đang nằm trong hash collection.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, record equality và copy invariant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java SE 26 API — `java.lang.Object`, hợp đồng `equals` và `hashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html).
- [Java SE 26 API — `java.util.Set`, hợp đồng phần tử và hành vi khi phần tử bị thay đổi](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html).
- [JUnit 5 User Guide — Jupiter assertions and tests](https://junit.org/junit5/docs/current/user-guide/).
- [Java Language Specification, Section 8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
