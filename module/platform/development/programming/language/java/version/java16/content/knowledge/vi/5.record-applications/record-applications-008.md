# Thiết kế component collection với hợp đồng null và quyền sửa rõ ràng

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Ứng dụng record. Record phù hợp để mô tả snapshot và value object có cấu trúc dữ liệu rõ ràng. Khi component là `List`, `Set` hoặc `Map`, chỉ khai báo trường `final` chưa đủ để bảo vệ dữ liệu: collection có thể vẫn mutable, có thể chứa phần tử mutable và có quy tắc riêng về `null`. Bài học này hướng dẫn thiết kế hợp đồng collection rõ ràng về giá trị null, quyền sửa, thứ tự và cách ly tham chiếu.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt collection reference `null`, collection rỗng và phần tử `null`.
- Chọn giữa `List.copyOf`, `Set.copyOf`, `Map.copyOf` và các wrapper `Collections.unmodifiable...`.
- Hiểu khác biệt giữa view không sửa được và snapshot không sửa được.
- Bảo vệ component collection trong compact constructor của record.
- Cung cấp bản sao mutable khi caller cần chỉnh sửa dữ liệu.
- Xử lý collection có thứ tự và collection lồng nhau.
- Tránh nhầm lẫn giữa unmodifiable, immutable sâu và thread-safe.

## 1. Vì sao collection trong record cần hợp đồng rõ ràng?

Xét record:

```java
import java.util.List;

public record Team(String name, List<String> members) {}
```

Các component của record được lưu trong trường `private final`. Điều đó ngăn gán lại tham chiếu `members` sau khi khởi tạo, nhưng không ngăn nội dung danh sách thay đổi:

```java
List<String> source = new ArrayList<>(List.of("An", "Bình"));
Team team = new Team("Platform", source);

source.add("Chi");
System.out.println(team.members()); // [An, Bình, Chi]
```

Record giữ cùng tham chiếu tới danh sách đầu vào. Caller còn có thể sửa danh sách qua accessor nếu danh sách đó mutable:

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("An", "Bình"));
Team team = new Team("Platform", source);
team.members().add("Dũng"); // Có thể sửa nếu danh sách đang mutable
```

Vì vậy, thiết kế component collection phải trả lời bốn câu hỏi:

1. **Collection có được phép null không?** Giá trị `members == null` có nghĩa là chưa tải dữ liệu, hay tương đương danh sách rỗng?
2. **Phần tử có được phép null không?** Một thành viên null có ý nghĩa nghiệp vụ hay là dữ liệu lỗi?
3. **Ai được phép sửa?** Caller chỉ đọc snapshot, hay cần một bản sao để chỉnh sửa?
4. **Thứ tự có ý nghĩa không?** Danh sách có giữ thứ tự đầu vào? Tập hợp hoặc map có cần giữ thứ tự chèn/sắp xếp?

Nếu không quy định rõ, người dùng kiểu dữ liệu phải đoán cách xử lý và có thể vô tình làm thay đổi trạng thái đã được chia sẻ.

## 2. Phân biệt ba trường hợp null và rỗng

Ba tình huống sau có ngữ nghĩa khác nhau:

| Giá trị | Ý nghĩa có thể có | Cần quyết định |
|---|---|---|
| Collection reference là `null` | Chưa biết, chưa tải, không được cung cấp hoặc lỗi đầu vào | Có cho phép trạng thái này không? |
| Collection rỗng | Đã biết nhưng hiện không có phần tử | Có phải trạng thái hợp lệ không? |
| Collection chứa phần tử `null` | Có một vị trí nhưng giá trị chưa biết/không tồn tại | Có ý nghĩa nghiệp vụ cụ thể không? |

Đừng dùng cả ba trạng thái thay thế cho nhau mà không có quy tắc.

### 2.1. Chính sách thường dùng: collection bắt buộc, rỗng nếu không có phần tử

Với DTO hoặc snapshot, lựa chọn dễ dùng là từ chối collection reference null và biểu diễn “không có phần tử” bằng collection rỗng:

```java
import java.util.List;
import java.util.Objects;

public record Team(String name, List<String> members) {
    public Team {
        Objects.requireNonNull(name, "name");
        members = List.copyOf(
                Objects.requireNonNull(members, "members"));
    }
}
```

Kết quả:

- Truyền `null` cho `members` sẽ ném `NullPointerException`.
- Truyền danh sách rỗng là hợp lệ.
- Phần tử `null` trong danh sách sẽ bị từ chối bởi `List.copyOf`.
- Danh sách lưu trong record không thể bị sửa qua accessor.
- Thay đổi cấu trúc danh sách nguồn sau khi tạo Team không ảnh hưởng Team.

Chính sách này phù hợp khi danh sách luôn có mặt trong hợp đồng, nhưng số phần tử có thể bằng không.

### 2.2. Khi nào nên chuẩn hóa null thành collection rỗng?

Nếu hợp đồng đầu vào định nghĩa rõ “không truyền danh sách” tương đương “không có phần tử”, có thể chuẩn hóa null thành rỗng:

```java
import java.util.List;
import java.util.Objects;

public record Team(String name, List<String> members) {
    public Team {
        Objects.requireNonNull(name, "name");
        members = members == null
                ? List.of()
                : List.copyOf(members);
    }
}
```

Sau constructor, accessor luôn trả một danh sách không null. Cách này giúp caller đơn giản hơn vì không cần kiểm tra null mỗi lần duyệt.

Tuy nhiên, không nên chuẩn hóa nếu null mang nghĩa riêng như “chưa tải danh sách”, “không được phép xem” hoặc “không được cung cấp”. Khi ba trạng thái có ý nghĩa khác nhau, hãy biểu diễn chúng rõ ràng bằng một kiểu trạng thái hoặc kiểu kết quả riêng.

### 2.3. Phần tử null có được phép không?

`List.copyOf` từ chối phần tử null. Nếu null không có ý nghĩa hợp lệ, đây là hành vi hữu ích: lỗi được phát hiện ngay khi tạo record.

Nếu hợp đồng thực sự cần giữ phần tử null, có thể tạo bản sao cấu trúc rồi bọc bằng wrapper không sửa được:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public record ImportedValues(List<String> values) {
    public ImportedValues {
        Objects.requireNonNull(values, "values");
        values = Collections.unmodifiableList(new ArrayList<>(values));
    }
}
```

Cách này tạo danh sách mới, không giữ alias tới danh sách nguồn, chặn sửa cấu trúc qua accessor và giữ nguyên phần tử null nếu nguồn có null.

Chỉ dùng cách này khi null là một phần có chủ đích của hợp đồng. Trong nhiều mô hình miền, một giá trị null trong danh sách khó hiểu hơn một kiểu biểu diễn rõ ràng, ví dụ `Optional<String>` hoặc record mô tả trạng thái chưa biết.

Ví dụ dùng Optional để phân biệt giá trị có mặt và vắng mặt:

```java
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public record ImportedValues(List<Optional<String>> values) {
    public ImportedValues {
        Objects.requireNonNull(values, "values");
        values = List.copyOf(values);
        // List.copyOf từ chối phần tử Optional null.
        // Optional.empty() biểu diễn một giá trị vắng mặt có chủ đích.
    }
}
```

`Optional.empty()` không giống phần tử null: bản thân Optional là một object hợp lệ, diễn tả rõ trạng thái vắng mặt. Chỉ dùng Optional trong component khi hợp đồng thực sự cần biểu diễn trạng thái đó; với API JSON hoặc framework serialization, hãy kiểm tra cách thư viện đang dùng ánh xạ Optional.

## 3. Snapshot không sửa được: copyOf

Các factory `List.copyOf`, `Set.copyOf` và `Map.copyOf` có từ Java 10; chúng vẫn là API chuẩn, phù hợp trong Java hiện đại và rất hữu ích cho component của record. Riêng `Stream.toList()` được bổ sung từ Java 16 và sẽ được trình bày ở phần 8.

### 3.1. List.copyOf

`List.copyOf` tạo danh sách không sửa được, giữ thứ tự duyệt của nguồn và cho phép phần tử trùng lặp. Nó từ chối collection null và phần tử null.

```java
import java.util.List;
import java.util.Objects;

public record Playlist(String title, List<String> tracks) {
    public Playlist {
        Objects.requireNonNull(title, "title");
        tracks = List.copyOf(Objects.requireNonNull(tracks, "tracks"));
    }
}
```

Nếu nguồn là `ArrayList` và sau đó caller thêm/xóa phần tử, danh sách trong Playlist không phản ánh thay đổi cấu trúc đó.

### 3.2. Set.copyOf

`Set.copyOf` tạo Set không sửa được và từ chối collection null hoặc phần tử null. Set không giữ phần tử trùng theo equality; nếu nguồn có các phần tử bằng nhau, kết quả chỉ giữ một trong số đó. Không dựa vào instance cụ thể được giữ lại hoặc thứ tự duyệt.

```java
import java.util.Objects;
import java.util.Set;

public record Permissions(Set<String> roles) {
    public Permissions {
        roles = Set.copyOf(Objects.requireNonNull(roles, "roles"));
    }
}
```

Không dựa vào thứ tự duyệt của Set tạo bởi `Set.copyOf`. Nếu thứ tự chèn là một phần hợp đồng, dùng `LinkedHashSet` rồi bọc một bản sao bằng `Collections.unmodifiableSet`.

### 3.3. Map.copyOf

`Map.copyOf` tạo Map không sửa được và từ chối map nguồn null, key null hoặc value null:

```java
import java.util.Map;
import java.util.Objects;

public record UserSettings(Map<String, String> options) {
    public UserSettings {
        options = Map.copyOf(Objects.requireNonNull(options, "options"));
    }
}
```

`Map.copyOf` không cam kết thứ tự duyệt. Nếu cần giữ thứ tự chèn, dùng `LinkedHashMap` làm bản sao rồi bọc bằng `Collections.unmodifiableMap`. Nếu cần thứ tự theo comparator, dùng `TreeMap` và `Collections.unmodifiableSortedMap`.

### 3.4. Bảng lựa chọn nhanh

| Factory | Cho phép phần tử trùng? | Cho phép null? | Thứ tự |
|---|---|---|---|
| `List.copyOf` | Có | Không nhận collection null hoặc phần tử null | Giữ thứ tự duyệt của nguồn |
| `Set.copyOf` | Không, phần tử bằng nhau được gộp | Không nhận collection null hoặc phần tử null | Không cam kết thứ tự |
| `Map.copyOf` | Key là duy nhất theo Map | Không nhận map, key hoặc value null | Không cam kết thứ tự |

Các phương thức trên tạo collection không sửa được. Chúng không làm cho object mutable nằm bên trong collection trở thành immutable sâu.

## 4. Unmodifiable view khác snapshot như thế nào?

`Collections.unmodifiableList`, `unmodifiableSet` và `unmodifiableMap` tạo một **view không sửa được** trên collection nền. Wrapper chặn thao tác sửa thông qua chính view, nhưng nếu một tham chiếu khác còn sửa được collection nền thì view vẫn nhìn thấy thay đổi đó.

### 4.1. Bọc trực tiếp collection nguồn: chỉ tạo view

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(source);

source.add("C");

System.out.println(view); // [A, B, C]
view.add("D");             // UnsupportedOperationException
```

`view` không thể bị sửa qua accessor, nhưng nó phản ánh thay đổi được thực hiện qua `source`. Đây không phải snapshot độc lập.

### 4.2. Sao chép trước, sau đó bọc: snapshot có thứ tự

Nếu cần giữ thứ tự chèn và đồng thời cách ly với collection nguồn:

```java
List<String> snapshot = Collections.unmodifiableList(
        new ArrayList<>(source));
```

Bản sao `ArrayList` được tạo riêng, sau đó wrapper chặn sửa qua tham chiếu trả ra. Không có tham chiếu mutable nào tới bản sao được giữ lại, nên cấu trúc snapshot không thể bị sửa từ bên ngoài.

Với nhu cầu thông thường, `List.copyOf(source)` ngắn gọn hơn và thường là lựa chọn nên ưu tiên. Cặp “copy rồi wrap” hữu ích khi cần giữ đặc điểm của collection cụ thể hoặc cần chính sách null khác với `copyOf`.

### 4.3. Chọn wrapper có thứ tự phù hợp

Ví dụ giữ thứ tự chèn của Set:

```java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

Set<String> sourceRoles = new LinkedHashSet<>(List.of("reader", "editor"));
Set<String> orderedRoles = Collections.unmodifiableSet(
        new LinkedHashSet<>(sourceRoles));
```

Ví dụ giữ thứ tự comparator của SortedMap:

```java
import java.util.Comparator;
import java.util.Collections;
import java.util.SortedMap;
import java.util.TreeMap;

SortedMap<String, Integer> sourceScores = new TreeMap<>(Comparator.reverseOrder());
sourceScores.put("advanced", 3);
sourceScores.put("basic", 1);

SortedMap<String, Integer> sorted = Collections.unmodifiableSortedMap(
        new TreeMap<>(sourceScores));
```

Trong cả hai ví dụ, bản sao được tạo trước khi bọc. Constructor `TreeMap(SortedMap)` giữ comparator của nguồn `SortedMap`. Nếu chỉ viết `Collections.unmodifiableSet(sourceRoles)` hoặc `unmodifiableSortedMap(sourceScores)`, wrapper vẫn nhìn thấy thay đổi từ tham chiếu mutable tới collection nguồn.

## 5. Quyền sửa trong API: chỉ đọc hay cần bản sao mutable?

Một record thường đại diện giá trị hoặc snapshot. Hợp đồng đơn giản nhất là accessor trả collection không sửa được. Nếu caller cần thao tác, có thể cung cấp một phương thức tạo **bản sao mutable** với tên gọi thể hiện rõ điều đó.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public record Course(String code, List<String> topics) {
    public Course {
        Objects.requireNonNull(code, "code");
        topics = List.copyOf(Objects.requireNonNull(topics, "topics"));
    }

    public List<String> newMutableTopicsCopy() {
        return new ArrayList<>(topics);
    }

    public Course withTopics(List<String> newTopics) {
        return new Course(code, newTopics);
    }
}
```

Cách dùng:

```java
Course original = new Course(
        "JAVA16",
        List.of("record", "Stream"));

List<String> draft = original.newMutableTopicsCopy();
draft.add("pattern matching");

Course revised = original.withTopics(draft);
```

`original` không thay đổi. `draft` là bản sao mutable để caller thao tác; `revised` là một giá trị mới, constructor lại tạo snapshot không sửa được.

Đặt tên như `newMutableTopicsCopy()` giúp caller hiểu rõ quyền sở hữu và quyền sửa. Tránh trả trực tiếp collection nội bộ nếu mục tiêu là giữ snapshot ổn định.

### 5.1. Khi API thật sự cần trả collection mutable

Nếu yêu cầu nghiệp vụ là caller được quyền sửa một bản làm việc, hãy trả bản sao mutable. Đừng làm accessor `topics()` trả một collection mutable dùng chung chỉ để thuận tiện.

Một cách phân chia rõ ràng:

| API | Hợp đồng |
|---|---|
| `topics()` | Trả snapshot không sửa được |
| `newMutableTopicsCopy()` | Trả bản sao riêng, caller được phép sửa |
| `withTopics(newTopics)` | Tạo Course mới từ dữ liệu mới |

Cách này tránh hai caller vô tình cùng sửa một collection đang được chia sẻ.

### 5.2. Không nhầm collection unmodifiable với collection immutable sâu

Collection không sửa được có nghĩa caller không thể thay đổi cấu trúc collection qua các phương thức mutator. Nó không có nghĩa mọi phần tử đều bất biến.

Ví dụ:

```java
import java.util.List;

final class MutableLabel {
    private String value;

    public MutableLabel(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }

    public void rename(String newValue) {
        this.value = newValue;
    }
}

record LabelGroup(List<MutableLabel> labels) {
    public LabelGroup {
        labels = List.copyOf(labels);
    }
}
```

Caller không thể thêm hoặc xóa phần tử khỏi `labels`, nhưng vẫn có thể gọi `labels.get(0).rename(...)`. Nếu cần snapshot bất biến sâu, hãy chuyển từng phần tử mutable thành record/value object bất biến khi tạo:

```java
record LabelSnapshot(String value) {}

public record LabelGroup(List<LabelSnapshot> labels) {
    public LabelGroup {
        labels = List.copyOf(labels);
    }
}
```

Bản sao sâu cần hiểu cấu trúc và ý nghĩa của từng loại phần tử. Java không cung cấp một phép deep-copy tổng quát an toàn cho mọi object graph.

## 6. Hợp đồng collection lồng nhau

Một record có thể chứa Map của List, List của record khác hoặc cấu trúc nhiều tầng. Cần bảo vệ từng tầng mà API cho phép truy cập.

Ví dụ cấu hình nhóm:

```java
public record FeatureConfig(Map<String, List<String>> flagsByModule) {
    public FeatureConfig {
        Objects.requireNonNull(flagsByModule, "flagsByModule");

        Map<String, List<String>> copy = new LinkedHashMap<>();
        flagsByModule.forEach((module, flags) -> {
            Objects.requireNonNull(module, "module");
            Objects.requireNonNull(flags, "flags");
            copy.put(module, List.copyOf(flags));
        });

        flagsByModule = Collections.unmodifiableMap(copy);
    }
}
```

Đoạn code giả định đã import `java.util.Collections`, `java.util.LinkedHashMap`, `java.util.List`, `java.util.Map` và `java.util.Objects`. Chính sách:

- Map ngoài không được null.
- Key module không được null.
- Mỗi danh sách flags không được null.
- Phần tử null trong từng danh sách bị `List.copyOf` từ chối.
- Mỗi danh sách con là snapshot không sửa được.
- Map ngoài là bản sao giữ thứ tự chèn và không sửa được.

Nếu chỉ dùng `Map.copyOf(flagsByModule)`, map ngoài được bảo vệ nhưng các list con vẫn có thể mutable và vẫn bị thay đổi qua tham chiếu nguồn. Vì vậy, phải copy từng tầng collection có thể quan sát từ bên ngoài.

### 6.1. Map key và value cũng cần ổn định

Khi Map nằm trong record, không chỉ value mà cả key có thể là object mutable. Nếu key thay đổi `equals()`/`hashCode()` sau khi được dùng trong map, việc tra cứu có thể hỏng. Dùng key bất biến như `String`, enum hoặc record có component bất biến.

Nếu value là collection, sao chép từng collection con. Nếu value là object mutable, chuyển thành snapshot hoặc áp dụng chính sách sở hữu rõ ràng.

### 6.2. Cập nhật một nhánh của cấu trúc lồng nhau

Để thêm flag vào một module, tạo Map mới, tạo List mới cho nhánh được cập nhật và dựng FeatureConfig mới:

```java
public FeatureConfig withFlag(String module, String newFlag) {
    Objects.requireNonNull(module, "module");
    Objects.requireNonNull(newFlag, "newFlag");

    Map<String, List<String>> updated = new LinkedHashMap<>(flagsByModule);
    List<String> flags = new ArrayList<>(
            updated.getOrDefault(module, List.of()));

    flags.add(newFlag);
    updated.put(module, flags);

    return new FeatureConfig(updated);
}
```

Đây là phương thức bổ sung bên trong record `FeatureConfig` ở ví dụ trước. Cần import `java.util.ArrayList`. Constructor của FeatureConfig sẽ sao chép lại map và các list con, nên instance cũ không bị thay đổi.

Nếu cần tránh thêm flag trùng, hãy kiểm tra trước bằng `contains` hoặc chuyển cấu trúc sang Set nếu ngữ nghĩa miền không cho phép trùng lặp.

## 7. Thứ tự và loại collection là một phần hợp đồng

Chọn List, Set hoặc Map không chỉ là chọn API thao tác; mỗi loại có semantics khác nhau:

| Loại | Đặc điểm | Khi phù hợp |
|---|---|---|
| `List<T>` | Có thứ tự, cho phép trùng | Thứ tự hiển thị hoặc vị trí có ý nghĩa |
| `Set<T>` | Không giữ phần tử trùng theo equality | Tập giá trị duy nhất |
| `Map<K,V>` | Key duy nhất, ánh xạ tới value | Tra cứu theo định danh |

Nếu thứ tự là một phần hợp đồng:

- Dùng `List.copyOf` khi cần giữ thứ tự duyệt và cho phép phần tử trùng.
- Dùng bản sao `LinkedHashSet` cùng `Collections.unmodifiableSet` khi cần loại trùng nhưng vẫn giữ thứ tự chèn.
- Dùng bản sao `LinkedHashMap` cùng `Collections.unmodifiableMap` khi cần giữ thứ tự chèn của entry.
- Dùng `TreeSet` hoặc `TreeMap` cùng wrapper sorted tương ứng khi cần thứ tự theo comparator.

`Set.copyOf` và `Map.copyOf` không cam kết thứ tự duyệt. Đừng dựa vào thứ tự quan sát được trong một lần chạy nếu API không cam kết điều đó.

## 8. Collection từ Stream và hợp đồng quyền sửa

Từ Java 16, `Stream.toList()` trả về danh sách unmodifiable. API này phù hợp khi muốn kết quả pipeline là một snapshot không cho thêm, xóa hoặc thay thế phần tử:

```java
import java.util.List;

record User(String name) {}

List<User> users = List.of(new User("An"), new User("Bình"));
List<String> names = users.stream()
        .map(User::name)
        .toList();
```

Nếu cần danh sách mutable, hãy yêu cầu điều đó rõ ràng:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> editableNames = users.stream()
        .map(User::name)
        .collect(Collectors.toCollection(ArrayList::new));
```

Hoặc:

```java
List<String> editableNames = new ArrayList<>(
        users.stream().map(User::name).toList());
```

Không dựa vào `Collectors.toList()` để đảm bảo collection mutable cụ thể; API không cam kết implementation hoặc khả năng sửa cụ thể. `Collectors.toUnmodifiableList()`, `toUnmodifiableSet()` và `toUnmodifiableMap()` cung cấp kết quả unmodifiable; các collector unmodifiable từ chối null theo hợp đồng của chúng.

Dù dùng API nào, quyền sửa của collection đầu ra cần được thể hiện rõ trong chữ ký, tên phương thức hoặc tài liệu API.

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ khai báo component `final` và giữ collection nguồn | Caller có thể sửa nội dung record gián tiếp | Defensive copy trong constructor |
| Dùng `Collections.unmodifiableList(source)` trực tiếp | View vẫn phản ánh thay đổi từ source | Copy trước rồi wrap, hoặc dùng `List.copyOf` |
| Dùng `List.copyOf` khi null element là hợp lệ | Constructor ném `NullPointerException` | Quy định null rõ ràng; chọn kiểu biểu diễn hoặc wrapper phù hợp |
| Chuẩn hóa mọi collection null thành rỗng | Mất khác biệt giữa chưa biết và không có phần tử | Chỉ chuẩn hóa khi hợp đồng xác định hai trạng thái tương đương |
| Nghĩ `Map.copyOf` giữ thứ tự chèn | Caller phụ thuộc vào thứ tự không được cam kết | Dùng LinkedHashMap copy và unmodifiable wrapper |
| Chỉ copy collection ngoài | Collection con vẫn mutable | Copy từng tầng có thể quan sát |
| Dùng unmodifiable list chứa object mutable rồi gọi là deep immutable | Phần tử vẫn có thể đổi trạng thái | Chuyển phần tử thành snapshot bất biến |
| Trả collection nội bộ để caller chỉnh sửa | Các caller có thể cùng sửa trạng thái chia sẻ | Trả bản sao mutable có tên rõ ràng |
| Nghĩ `Stream.toList()` trả danh sách mutable | Có thể gặp `UnsupportedOperationException` khi sửa | Tạo `ArrayList` riêng nếu cần chỉnh sửa |

## 10. Checklist thiết kế component collection

Trước khi đưa collection vào record, hãy kiểm tra:

1. Collection reference có bắt buộc khác null không?
2. Collection rỗng có khác về ý nghĩa với collection chưa được cung cấp không?
3. Phần tử null có được phép không? Nếu có, nó mang ý nghĩa gì?
4. Constructor có tạo defensive copy không?
5. Collection trả qua accessor có unmodifiable không?
6. Các phần tử bên trong có mutable không?
7. Nếu collection lồng nhau, từng tầng có được bảo vệ không?
8. Thứ tự chèn/thứ tự sắp xếp có phải một phần của hợp đồng không?
9. Caller có cần bản sao mutable riêng không?
10. Record có được dùng làm key trong Map/Set với component ổn định không?

## 11. Bài tập vận dụng

**Bài 1 — Danh sách thành viên:** Tạo `Team(String name, List<String> members)`. Từ chối collection null và phần tử null, nhưng cho phép danh sách rỗng. Chứng minh thay đổi danh sách nguồn không ảnh hưởng Team.

**Bài 2 — Dữ liệu nhập có null:** Tạo record nhận danh sách giá trị từ nguồn import, trong đó null có ý nghĩa “không xác định”. Dùng defensive copy và wrapper unmodifiable cho phép null. So sánh với cách biểu diễn bằng `Optional<String>`.

**Bài 3 — Giữ thứ tự:** Tạo `OrderedRoles` dùng LinkedHashSet để loại trùng và giữ thứ tự chèn. Bọc bản sao để caller chỉ đọc. Kiểm tra thứ tự sau khi tạo.

**Bài 4 — Map lồng nhau:** Tạo `FeatureConfig` chứa Map của List. Sao chép map ngoài và từng list con. Thử sửa map nguồn, list nguồn, map qua accessor và list con qua accessor.

**Bài 5 — API mutable copy:** Tạo record `Course` có accessor chỉ đọc và phương thức `newMutableTopicsCopy()`. Chỉnh sửa bản sao rồi tạo instance mới bằng `withTopics`. Chứng minh instance cũ vẫn nguyên vẹn.

---

**Ghi nhớ:** Component collection trong record cần một hợp đồng rõ ràng về null, thứ tự và quyền sửa. Dùng defensive copy để tách khỏi dữ liệu nguồn, dùng collection unmodifiable cho snapshot chỉ đọc, và chỉ trả bản sao mutable khi caller thật sự cần chỉnh sửa. Hãy kiểm tra cả phần tử bên trong collection vì unmodifiable ở lớp ngoài chưa bảo đảm bất biến sâu.
