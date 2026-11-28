# Defensive copy collection khi nhận dữ liệu vào constructor

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá những cải tiến từ Java 16 vẫn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này giải thích cách bảo vệ component kiểu collection khi tạo record, để dữ liệu bên ngoài không thể âm thầm làm thay đổi trạng thái mà record đang biểu diễn.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao field `final` không làm cho collection mà nó tham chiếu trở nên bất biến.
- Dùng `List.copyOf`, `Set.copyOf` và `Map.copyOf` để tạo collection không thể sửa đổi.
- Phân biệt bản sao cấu trúc (shallow copy) với bản sao sâu (deep copy).
- Nhận diện việc lộ collection qua accessor hoặc qua phần tử mutable bên trong.
- Chọn cách sao chép phù hợp khi cần giữ thứ tự, cho phép null hoặc bảo vệ dữ liệu lồng nhau.
- Kiểm thử rằng thay đổi collection đầu vào sau khi tạo record không làm thay đổi dữ liệu record.

## 1. Vì sao record cần defensive copy?

Record phù hợp để mô hình hóa dữ liệu giá trị. Các component được khai báo trong record header sẽ trở thành field `private final` và có accessor tương ứng.

Ví dụ:

```java
import java.util.List;

public record SearchRequest(String query, List<String> tags) {}
```

Từ khóa `final` đảm bảo field `tags` không thể được gán lại sang một tham chiếu khác sau khi khởi tạo. Nhưng nó **không làm cho đối tượng List mà field trỏ đến trở nên bất biến**.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("java", "record"));
SearchRequest request = new SearchRequest("records", source);

source.add("mutable");

System.out.println(request.tags());
// [java, record, mutable]
```

Record vẫn giữ cùng tham chiếu đến danh sách `source`. Khi bên gọi thêm phần tử vào danh sách đó, kết quả quan sát qua `request.tags()` cũng thay đổi.

Điều này làm cho record không còn hoạt động như một snapshot dữ liệu độc lập. Nếu trạng thái collection là một phần của giá trị record, constructor nên tạo bản sao phòng vệ (defensive copy) trước khi lưu component.

## 2. Dùng List.copyOf trong compact constructor

Từ Java 10, `List.copyOf` cung cấp cách tạo danh sách không thể sửa đổi từ một collection đầu vào. API này vẫn áp dụng bình thường trong Java 16 và các phiên bản Java hiện đại.

Ví dụ:

```java
import java.util.List;
import java.util.Objects;

public record SearchRequest(String query, List<String> tags) {

    public SearchRequest {
        query = Objects.requireNonNull(query, "query").strip();

        tags = List.copyOf(
                Objects.requireNonNull(tags, "tags")
        );

        if (query.isEmpty()) {
            throw new IllegalArgumentException("query is required");
        }
    }
}
```

Trong compact constructor:

1. Kiểm tra `query` và chuẩn hóa chuỗi.
2. Kiểm tra collection `tags` không null.
3. Tạo danh sách không thể sửa đổi bằng `List.copyOf`.
4. Gán lại tham số ngầm `tags` bằng danh sách mới.
5. Khi thân constructor kết thúc bình thường, compiler gán các tham số cuối cùng vào component field.

Bạn không cần viết `this.tags = ...`. Đây là gán lại tham số ngầm của compact constructor, theo đúng quy tắc khởi tạo record.

Sử dụng:

```java
List<String> source = new ArrayList<>(List.of("java", "record"));
SearchRequest request = new SearchRequest("records", source);

source.add("changed");

System.out.println(request.tags()); // [java, record]

// request.tags().add("new");
// UnsupportedOperationException
```

Danh sách được lưu trong record không bị ảnh hưởng khi danh sách nguồn có thể sửa đổi thay đổi. Accessor trả về danh sách không thể sửa đổi qua các thao tác collection thông thường.

## 3. Kiểm tra null và phần tử null

`List.copyOf` từ chối:

- Collection đầu vào là `null`.
- Bất kỳ phần tử nào trong collection là `null`.

Cả hai trường hợp đều gây `NullPointerException`. Nếu hợp đồng record yêu cầu danh sách và mọi phần tử đều phải tồn tại, đây thường là hành vi phù hợp.

Ví dụ:

```java
List<String> valid = List.of("java", "record");
List<String> invalid = java.util.Arrays.asList("java", null);

// List.copyOf(valid);   // Hợp lệ
// List.copyOf(invalid); // NullPointerException
// List.copyOf(null);    // NullPointerException
```

Nếu nghiệp vụ cho phép phần tử null, `List.copyOf` không phù hợp. Có thể tạo bản sao riêng rồi bọc bằng `Collections.unmodifiableList`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public record OptionalLabels(List<String> values) {

    public OptionalLabels {
        Objects.requireNonNull(values, "values");
        values = Collections.unmodifiableList(
                new ArrayList<>(values)
        );
    }
}
```

Ở đây `new ArrayList<>(values)` tạo bản sao cấu trúc trước, còn `Collections.unmodifiableList` cung cấp một view không cho phép sửa qua accessor. Vì view bọc một bản sao riêng do record sở hữu, việc thay đổi collection đầu vào không ảnh hưởng đến record.

Không nên viết `Collections.unmodifiableList(values)` trực tiếp nếu `values` vẫn là collection do bên gọi sở hữu. Cách đó chỉ tạo view không cho phép sửa qua view; bên gọi vẫn có thể sửa collection gốc và thay đổi nội dung mà view quan sát được.

## 4. Phân biệt bản sao cấu trúc và bản sao sâu

`List.copyOf` tạo một danh sách không thể sửa đổi, nhưng việc sao chép chỉ ở **cấu trúc collection**. Nó không tự sao chép từng đối tượng nằm bên trong danh sách.

Ví dụ:

```java
import java.util.List;

final class MutableTag {
    private String name;

    public MutableTag(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public void rename(String name) {
        this.name = name;
    }
}

public record TagGroup(List<MutableTag> tags) {
    public TagGroup {
        tags = List.copyOf(tags);
    }
}
```

Sử dụng:

```java
MutableTag tag = new MutableTag("java");
TagGroup group = new TagGroup(List.of(tag));

tag.rename("changed");

System.out.println(group.tags().get(0).name()); // changed
```

Danh sách trong record không thể thêm hoặc xóa phần tử, nhưng phần tử `MutableTag` vẫn là cùng đối tượng với đầu vào. Bên gọi thay đổi đối tượng đó thì record quan sát được thay đổi.

Đây là khác biệt:

| Loại sao chép | Điều được sao chép | Điều vẫn có thể dùng chung |
| --- | --- | --- |
| Bản sao cấu trúc (shallow copy) | Cấu trúc danh sách, vị trí phần tử | Các đối tượng phần tử |
| Bản sao sâu (deep copy) | Cấu trúc và các đối tượng mutable theo chính sách sao chép | Chỉ các đối tượng được chủ ý chia sẻ hoặc kiểu bất biến |

Đối với `List<String>`, phần tử `String` là bất biến nên sao chép cấu trúc thường đã đủ. Với danh sách đối tượng mutable, cần quyết định cách bảo vệ từng phần tử.

Phần tử mutable còn ảnh hưởng đến `equals()` và `hashCode()` do record sinh tự động dựa trên giá trị component. Nếu trạng thái phần tử thay đổi sau khi record được dùng làm key trong `HashMap` hoặc phần tử trong `HashSet`, kết quả so sánh và tra cứu có thể thay đổi ngoài dự kiến. Đây là một lý do quan trọng để ưu tiên kiểu phần tử bất biến.

## 5. Sao chép phần tử khi component chứa đối tượng mutable

Nếu kiểu phần tử có thể thay đổi, một cách tiếp cận là tạo bản sao riêng cho từng phần tử trong constructor.

Ví dụ, giả sử có kiểu dữ liệu mutable `MutableTag` ở phần trước:

```java
import java.util.List;
import java.util.Objects;

public record SafeTagGroup(List<MutableTag> tags) {

    public SafeTagGroup {
        tags = Objects.requireNonNull(tags, "tags")
                .stream()
                .map(tag -> {
                    Objects.requireNonNull(tag, "tag");
                    return new MutableTag(tag.name());
                })
                .toList();
    }

    @Override
    public List<MutableTag> tags() {
        return tags.stream()
                .map(tag -> new MutableTag(tag.name()))
                .toList();
    }
}
```

Constructor tạo đối tượng `MutableTag` mới cho từng phần tử. Accessor cũng trả về danh sách các bản sao mới, không để bên gọi sửa đối tượng đang được record lưu giữ.

Phương thức `Stream.toList()` có từ Java 16 và trả về danh sách không thể sửa đổi. Tuy nhiên, danh sách này vẫn chứa các phần tử mutable; vì vậy ví dụ phải sao chép từng `MutableTag` cả khi nhận đầu vào lẫn khi trả dữ liệu ra.

Nếu có thể thiết kế lại kiểu phần tử thành record hoặc một kiểu bất biến, giải pháp thường đơn giản và an toàn hơn:

```java
// File: TagGroup.java; Tag is an immutable value type.
record Tag(String name) {}

public record TagGroup(List<Tag> tags) {
    public TagGroup {
        tags = List.copyOf(tags);
    }
}
```

`Tag` là record với component `String` bất biến. Khi đó, bản sao cấu trúc bằng `List.copyOf` thường đủ để bảo vệ cả danh sách lẫn các giá trị phần tử.

## 6. Cần bảo vệ cả chiều dữ liệu đi ra

Defensive copy ở constructor bảo vệ dữ liệu đi vào. Nhưng nếu component vẫn có thể bị thay đổi thông qua accessor, record vẫn có thể bị thay đổi từ bên ngoài.

Ví dụ:

```java
import java.util.List;

public record MutableItems(List<MutableTag> items) {
    public MutableItems {
        items = List.copyOf(items);
    }
}
```

Accessor mặc định `items()` trả về chính danh sách đã lưu. Danh sách không thể sửa cấu trúc, nhưng các phần tử `MutableTag` vẫn có thể được đổi tên.

Có ba hướng thiết kế:

1. Dùng kiểu phần tử bất biến để không cần sao chép sâu.
2. Sao chép từng phần tử ở constructor và trả bản sao từng phần tử qua accessor.
3. Không công bố đối tượng mutable ra ngoài; chỉ cung cấp các thao tác đọc hoặc giá trị bất biến.

Nếu override accessor để trả bản sao, hãy bảo đảm bản sao đó cũng bảo vệ phần tử mutable bên trong. Chỉ viết `return new ArrayList<>(items)` vẫn là shallow copy và không ngăn người gọi sửa các phần tử.

## 7. Dùng Set.copyOf và Map.copyOf

Java cung cấp các phương thức tương tự cho `Set` và `Map`:

- `Set.copyOf(collection)` tạo Set không thể sửa đổi.
- `Map.copyOf(map)` tạo Map không thể sửa đổi.

Ví dụ:

```java
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public record AccessPolicy(Set<String> roles, Map<String, Boolean> permissions) {

    public AccessPolicy {
        roles = Set.copyOf(Objects.requireNonNull(roles, "roles"));
        permissions = Map.copyOf(
                Objects.requireNonNull(permissions, "permissions")
        );
    }
}
```

Sau khi tạo record, bên gọi không thể thêm/xóa role hoặc thay đổi mapping permission thông qua các thao tác sửa đổi thông thường.

Cần chú ý:

- `Set.copyOf` không bảo đảm thứ tự lặp phần tử.
- `Map.copyOf` không bảo đảm thứ tự lặp entry.
- `Set.copyOf` loại bỏ phần tử trùng theo quy tắc của Set.
- `Set.copyOf` và `Map.copyOf` không chấp nhận null; Map không chấp nhận key hoặc value null.
- Bản sao cấu trúc không tự sao chép sâu các key, value hoặc phần tử mutable.

Nếu thứ tự là một phần hợp đồng dữ liệu, hãy chọn kiểu collection và cách sao chép giữ thứ tự thay vì dựa vào thứ tự lặp của `Set.copyOf` hoặc `Map.copyOf`.

## 8. Giữ thứ tự khi cần snapshot của Map hoặc Set

Nếu cần giữ thứ tự chèn của map, có thể tạo một `LinkedHashMap` mới rồi bọc nó bằng `Collections.unmodifiableMap`:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

public record OrderedSettings(Map<String, String> values) {

    public OrderedSettings {
        Objects.requireNonNull(values, "values");

        values = Collections.unmodifiableMap(
                new LinkedHashMap<>(values)
        );
    }
}
```

`new LinkedHashMap<>(values)` tạo cấu trúc riêng và giữ thứ tự lặp của nguồn theo thứ tự mà nguồn cung cấp. `Collections.unmodifiableMap` ngăn thay đổi map thông qua tham chiếu được lưu trong record.

Tương tự, nếu cần thứ tự chèn của Set:

```java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

public record OrderedNames(Set<String> names) {

    public OrderedNames {
        names = Collections.unmodifiableSet(
                new LinkedHashSet<>(names)
        );
    }
}
```

Các wrapper `unmodifiableMap` và `unmodifiableSet` không tự sao chép dữ liệu. Tính độc lập ở đây đến từ việc đã tạo `LinkedHashMap` hoặc `LinkedHashSet` riêng trước khi bọc.

Nếu thứ tự không quan trọng, `Map.copyOf` và `Set.copyOf` thường gọn hơn.

## 9. Snapshot của collection đầu vào và thay đổi đồng thời

Khi sao chép một collection, nguồn đầu vào không nên bị thay đổi đồng thời trong lúc constructor đang duyệt hoặc sao chép nó.

Ví dụ, nếu một thread thêm phần tử trong lúc thread khác chạy `List.copyOf(source)`, kết quả có thể không phản ánh một snapshot nhất quán; một số collection còn có thể ném `ConcurrentModificationException`.

Nếu collection được chia sẻ giữa nhiều thread, hãy đồng bộ hóa theo cơ chế mà chủ sở hữu collection cung cấp hoặc tạo snapshot ở nơi có quyền kiểm soát việc sửa đổi. Không nên coi thao tác copy đơn thuần là một giao dịch nguyên tử trên collection mutable bất kỳ.

Defensive copy bảo vệ record sau khi đã tạo thành công. Nó không tự giải quyết mọi vấn đề đồng bộ hóa của collection nguồn.

## 10. Collection lồng nhau cần sao chép từng tầng

Một collection có thể chứa collection khác. Sao chép lớp ngoài chưa bảo vệ cấu trúc lớp trong.

Ví dụ:

```java
import java.util.List;
import java.util.Objects;

public record MatrixRows(List<List<Integer>> rows) {
    public MatrixRows {
        rows = Objects.requireNonNull(rows, "rows").stream()
                .map(List::copyOf)
                .toList();
    }
}
```

Trong ví dụ này:

- Mỗi hàng được sao chép bằng `List.copyOf`.
- Stream `toList()` tạo danh sách ngoài không thể sửa đổi.
- `Integer` là kiểu bất biến nên không cần sao chép từng phần tử.

Nếu phần tử trong cùng là đối tượng mutable, vẫn phải sao chép phần tử theo chính sách của kiểu đó. Với cấu trúc lồng nhiều tầng, hãy xác định rõ tầng nào có thể thay đổi và sao chép từng tầng có thể bị bên ngoài tác động.

## 11. Component là array cũng cần defensive copy

Array không phải Collection, nhưng cũng là đối tượng mutable thường được dùng làm component của record. Field `final` chỉ cố định tham chiếu array, không ngăn sửa từng phần tử.

Ví dụ:

```java
public record BytePayload(byte[] bytes) {

    public BytePayload {
        bytes = java.util.Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
```

Constructor clone array đầu vào. Accessor override để trả bản clone khác, tránh bên gọi thay đổi array đang được record lưu.

Với array nhiều chiều, `clone()` chỉ sao chép lớp ngoài; các array con vẫn được chia sẻ. Cần sao chép từng hàng nếu muốn bảo vệ sâu:

```java
public record IntMatrix(int[][] values) {

    public IntMatrix {
        values = deepCopy(values);
    }

    @Override
    public int[][] values() {
        return deepCopy(values);
    }

    private static int[][] deepCopy(int[][] source) {
        java.util.Objects.requireNonNull(source, "source");

        int[][] copy = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copy[i] = java.util.Objects.requireNonNull(
                    source[i], "row " + i
            ).clone();
        }
        return copy;
    }
}
```

Lưu ý: array dùng `equals()` và `hashCode()` theo identity, không so sánh nội dung sâu. Vì vậy, record có component array có thể không có equality theo giá trị mà bạn mong đợi. Nếu cần semantics giá trị, hãy cân nhắc chuyển sang collection bất biến hoặc tự định nghĩa cách so sánh phù hợp.

## 12. Collections.unmodifiableList và List.copyOf khác nhau thế nào?

Hai API đều có thể tạo danh sách mà người nhận không thể sửa qua tham chiếu trả về, nhưng mục đích và cách dùng khác nhau:

| Cách viết | Kết quả | Nguồn bên ngoài sửa được thì sao? |
| --- | --- | --- |
| `Collections.unmodifiableList(source)` | View không cho sửa qua view | Thay đổi nguồn có thể được nhìn thấy qua view |
| `Collections.unmodifiableList(new ArrayList<>(source))` | View trên bản sao riêng | Thay đổi nguồn không ảnh hưởng cấu trúc bản sao |
| `List.copyOf(source)` | Danh sách không thể sửa đổi chứa các phần tử của nguồn | Không thể sửa qua kết quả; không dựa vào identity hoặc cách triển khai |
| `List.copyOf(new ArrayList<>(source))` | Danh sách không thể sửa đổi từ một bản sao cấu trúc vừa tạo | Tạo ranh giới snapshot rõ ràng với collection nguồn |

Nếu mục tiêu là snapshot từ một collection mutable thông thường, `List.copyOf(source)` là lựa chọn gọn và phổ biến. Nếu API chấp nhận cả các unmodifiable view có thể phản ánh một backing collection mutable và bạn cần tách hẳn khỏi view đó, hãy materialize cấu trúc riêng trước khi tạo collection không thể sửa đổi.

Không nên nhầm "không thể sửa qua tham chiếu này" với "không có bất kỳ tham chiếu nào khác có thể thay đổi dữ liệu". Defensive copy tạo ra ranh giới sở hữu rõ ràng cho cấu trúc collection; việc bảo vệ phần tử mutable cần được giải quyết riêng.

## 13. Thiết kế component collection trong record

Khi thiết kế record có collection, hãy quyết định rõ các câu hỏi sau:

1. Component có bắt buộc non-null không?
2. Phần tử null có được phép không?
3. Có cần giữ thứ tự và phần tử trùng lặp không?
4. Bên gọi có thể thay đổi collection nguồn sau khi tạo record không?
5. Phần tử bên trong có mutable không?
6. Accessor có thể trả thẳng collection đã lưu không?
7. Collection lồng nhau hoặc array có cần sao chép sâu không?
8. Equality của record có phù hợp với equality của component collection không?

Ví dụ một record lưu danh sách tên role:

```java
import java.util.List;
import java.util.Objects;

public record UserRoles(String username, List<String> roles) {

    public UserRoles {
        username = Objects.requireNonNull(username, "username").strip();
        roles = List.copyOf(Objects.requireNonNull(roles, "roles"));

        if (username.isEmpty()) {
            throw new IllegalArgumentException("username is required");
        }
    }
}
```

Ở đây, `String` bất biến, `List.copyOf` tạo danh sách không thể sửa đổi và giữ thứ tự cùng các phần tử trùng lặp như danh sách nguồn. Record vì thế có thể chia sẻ an toàn giá trị `roles` qua accessor.

## 14. Kiểm thử defensive copy

Test nên xác minh hai điều:

- Thay đổi collection nguồn sau khi tạo record không làm thay đổi dữ liệu được lưu.
- Người gọi không thể sửa cấu trúc collection thông qua accessor.

Ví dụ với JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

class SearchRequestTest {

    @Test
    void copiesInputList() {
        List<String> source = new ArrayList<>(List.of("java", "record"));

        SearchRequest request = new SearchRequest("records", source);
        source.add("changed");

        assertEquals(List.of("java", "record"), request.tags());
    }

    @Test
    void accessorReturnsUnmodifiableList() {
        SearchRequest request = new SearchRequest(
                "records",
                List.of("java")
        );

        assertThrows(
                UnsupportedOperationException.class,
                () -> request.tags().add("new")
        );
    }

    @Test
    void rejectsNullCollection() {
        assertThrows(
                NullPointerException.class,
                () -> new SearchRequest("records", null)
        );
    }

    @Test
    void rejectsNullElement() {
        List<String> source = new ArrayList<>();
        source.add("java");
        source.add(null);

        assertThrows(
                NullPointerException.class,
                () -> new SearchRequest("records", source)
        );
    }
}
```

Với component chứa phần tử mutable, cần thêm test thay đổi đối tượng nguồn và thử sửa đối tượng nhận qua accessor. Test phải chứng minh cả cấu trúc lẫn phần tử được bảo vệ theo hợp đồng đã chọn.

## 15. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ khai báo component `final` | Collection vẫn có thể bị sửa qua alias khác. | Tạo defensive copy trong constructor. |
| Lưu trực tiếp collection đầu vào | Bên gọi thay đổi nguồn sẽ làm record thay đổi. | Dùng `List.copyOf`, `Set.copyOf`, `Map.copyOf` hoặc bản sao riêng phù hợp. |
| Chỉ dùng `Collections.unmodifiableList(source)` | View vẫn phản ánh thay đổi từ nguồn mutable. | Copy cấu trúc trước rồi mới bọc. |
| Nghĩ `List.copyOf` sao chép sâu | Phần tử mutable vẫn có thể thay đổi. | Sao chép từng phần tử hoặc dùng kiểu phần tử bất biến. |
| Dùng `Set.copyOf` khi cần thứ tự | Thứ tự lặp không được bảo đảm. | Dùng snapshot `LinkedHashSet` nếu thứ tự chèn là hợp đồng. |
| Dùng `Map.copyOf` khi cần thứ tự | Thứ tự lặp entry không được bảo đảm. | Dùng bản sao `LinkedHashMap` và unmodifiable wrapper. |
| Quên null trong collection | `copyOf` ném `NullPointerException`. | Xác định rõ chính sách null và chọn cách copy tương ứng. |
| Chỉ copy array trong constructor | Accessor vẫn có thể làm lộ array nội bộ. | Clone ở cả constructor và accessor. |
| Chỉ copy collection ngoài | Collection hoặc array lồng bên trong vẫn mutable. | Copy đệ quy theo cấu trúc dữ liệu. |
| Copy trong lúc nguồn bị sửa đồng thời | Snapshot có thể không nhất quán hoặc thao tác copy thất bại. | Đồng bộ hóa hoặc snapshot ở nơi kiểm soát được việc sửa. |

## 16. Bài tập tự luyện

### Bài 1: Bảo vệ danh sách đầu vào

Viết record `Course(String name, List<String> topics)` sao cho:

- `name` không null và không rỗng sau `strip()`.
- `topics` không null.
- Danh sách được lưu không thể sửa đổi.
- Thay đổi danh sách nguồn sau khi tạo record không ảnh hưởng record.

**Đáp án tham khảo:**

```java
import java.util.List;
import java.util.Objects;

public record Course(String name, List<String> topics) {
    public Course {
        name = Objects.requireNonNull(name, "name").strip();
        topics = List.copyOf(
                Objects.requireNonNull(topics, "topics")
        );

        if (name.isEmpty()) {
            throw new IllegalArgumentException("name is required");
        }
    }
}
```

### Bài 2: Cho phép phần tử null

`List.copyOf` không chấp nhận phần tử null. Hãy tạo record `NullableValues(List<String> values)` cho phép null nhưng vẫn tạo bản sao cấu trúc độc lập và không cho sửa qua accessor.

**Đáp án tham khảo:**

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public record NullableValues(List<String> values) {
    public NullableValues {
        Objects.requireNonNull(values, "values");
        values = Collections.unmodifiableList(
                new ArrayList<>(values)
        );
    }
}
```

### Bài 3: Phân biệt shallow copy và deep copy

Một record lưu `List<MutableTag>` và gọi `List.copyOf` trong constructor. Bên gọi vẫn có thể đổi tên một `MutableTag` rồi quan sát thay đổi qua accessor. Vì sao?

**Đáp án:** `List.copyOf` chỉ bảo vệ cấu trúc danh sách. Nó vẫn giữ tham chiếu đến các đối tượng phần tử. Cần sao chép từng phần tử mutable hoặc chuyển sang kiểu phần tử bất biến.

### Bài 4: Giữ thứ tự của Map

Viết record `OrderedSettings(Map<String, String> values)` sao cho map được sao chép độc lập, không thể sửa đổi qua accessor và giữ thứ tự chèn.

**Đáp án tham khảo:**

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

public record OrderedSettings(Map<String, String> values) {
    public OrderedSettings {
        Objects.requireNonNull(values, "values");
        values = Collections.unmodifiableMap(
                new LinkedHashMap<>(values)
        );
    }
}
```

### Bài 5: Bảo vệ array hai chiều

Vì sao `values.clone()` không đủ để bảo vệ `int[][] values`? Cần làm gì?

**Đáp án:** `clone()` chỉ sao chép array ngoài; các array con vẫn dùng chung tham chiếu. Cần clone từng hàng trong constructor và trả về một bản sao sâu qua accessor nếu muốn bên gọi không thể sửa dữ liệu nội bộ.

## Ghi nhớ

Field `final` của record chỉ cố định tham chiếu, không làm collection trở nên bất biến. Khi nhận collection từ bên ngoài, hãy tạo defensive copy trong compact hoặc canonical constructor. `List.copyOf`, `Set.copyOf` và `Map.copyOf` là các API hiện đại để tạo collection không thể sửa đổi; chúng bảo vệ cấu trúc, không tự sao chép sâu phần tử mutable. Cần xét thêm null, thứ tự, collection lồng nhau và dữ liệu đi ra qua accessor. Hãy kiểm thử bằng cách thay đổi nguồn sau khi tạo record và thử sửa collection qua accessor.

## Tài liệu tham khảo

- [Java API — List.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
- [Java API — Set.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)).
- [Java API — Map.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)).
- [Java API — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).
- [Java Language Specification — Java SE 26, `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records (hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
