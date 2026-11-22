# Thiết kế chính sách cho khóa `null` và giá trị `null`

Khi chuyển dữ liệu thành `Map` bằng Java Stream API, chương trình phải trả lời hai câu hỏi khác nhau: **nếu khóa là `null` thì làm gì**, và **nếu giá trị là `null` thì làm gì**? Một `HashMap` thông thường có thể chứa các giá trị đó, nhưng điều này không có nghĩa mọi collector hoặc mọi kiểu `Map` đều chấp nhận chúng. Bỏ qua khác biệt này dễ dẫn đến `NullPointerException` khi `collect` chạy, mất bản ghi âm thầm hoặc một `Map` có ý nghĩa không rõ ràng.

Bài thuộc chương **Thu thập thành Map** của module **JAVA_STREAM_API**. Ta sẽ thiết kế chính sách `null` rõ ràng cho `Collectors.toMap`, `groupingBy`, `toUnmodifiableMap`, các cấu trúc `Map` khác nhau và pipeline tuần tự/song song. Nội dung liên hệ trực tiếp đến `filter`, `map`, `collect`, xử lý trùng khóa, đặc tính collector, tính lazy, trạng thái dùng chung và chi phí của việc xử lý dữ liệu.

## 1. Phải phân biệt ba trạng thái dữ liệu

Xét một danh bạ `Map<String, String>` ánh xạ mã người dùng sang email:

```java
import java.util.HashMap;
import java.util.Map;

Map<String, String> emails = new HashMap<>();
emails.put("u1", "an@example.com");
emails.put("u2", null);

System.out.println(emails.get("u1"));          // an@example.com
System.out.println(emails.get("u2"));          // null
System.out.println(emails.get("u3"));          // null
System.out.println(emails.containsKey("u2"));  // true
System.out.println(emails.containsKey("u3"));  // false
```

Ở đây có ba trạng thái nghiệp vụ khác nhau:

1. **Có khóa và có giá trị**: người dùng `u1` có email.
2. **Có khóa nhưng giá trị `null`**: người dùng `u2` có bản ghi nhưng chưa có email.
3. **Không có khóa**: người dùng `u3` không có bản ghi trong danh bạ.

`get(key) == null` **không phân biệt được trạng thái 2 và 3**. Nếu ứng dụng cần phân biệt, dùng `containsKey` kết hợp `get`, hoặc chọn mô hình giá trị biểu diễn sự thiếu dữ liệu một cách tường minh.

Khóa `null` lại là vấn đề riêng: một bản ghi được đưa vào nhóm nào khi thuộc tính dùng làm khóa vắng mặt? Nếu nhiều bản ghi cùng có khóa `null`, chúng sẽ cùng tranh một mục trong `Map`, nên còn phải xác định **chính sách khi khóa trùng**.

## 2. Không phải mọi `Map` đều có cùng hợp đồng về `null`

Trước khi chọn collector, hãy xác định cấu trúc kết quả:

| Cấu trúc hoặc API | Khóa `null` | Giá trị `null` | Ghi chú |
|---|---|---|---|
| `HashMap` | Cho phép một khóa `null` | Cho phép | Không bảo đảm thứ tự duyệt |
| `LinkedHashMap` | Cho phép một khóa `null` | Cho phép | Giữ thứ tự chèn theo mặc định |
| `TreeMap` với natural ordering | Không cho phép | Cho phép | Có thể dùng comparator hỗ trợ `null` để xác định thứ tự khóa khác |
| `ConcurrentHashMap` | Không cho phép | Không cho phép | Cấu trúc đồng thời |
| `Map.of(...)`, `Map.ofEntries(...)` | Không cho phép | Không cho phép | Không thể chỉnh sửa; `null` gây lỗi |
| `Map.copyOf(map)` | Không cho phép | Không cho phép | Tạo kết quả không thể chỉnh sửa |
| `Collectors.toUnmodifiableMap(...)` | Không cho phép | Không cho phép | Collector Java 10+ |
| `Collectors.toMap(...)` | Không nên phụ thuộc vào việc chấp nhận `null` | Không dùng để lưu giá trị `null` | Không cam kết kiểu `Map` trả về |
| `Collectors.groupingBy(classifier)` | Từ chối khóa phân nhóm `null` | Phụ thuộc downstream collector | Không suy từ việc map kết quả có thể là `HashMap` |

`Collectors.toMap` mặc định thường tạo `HashMap` trên các JDK thông dụng, và một số phiên bản có thể chấp nhận khóa `null`; **hợp đồng collector không bảo đảm kiểu map hay quyền dùng khóa `null`**. Mặt khác, `valueMapper` trả `null` có thể gây `NullPointerException` ngay trong lúc tích lũy. Vì thế, phải xử lý chính sách `null` trước khi dựa vào collector.

Các đoạn mã tiếp theo sử dụng Java 17. Các factory `Map.of` xuất hiện từ Java 9; `Collectors.toUnmodifiableMap` và `Map.copyOf` có từ Java 10; `record` là tính năng chính thức từ Java 16.

## 3. Hiểu `Collectors.toMap` trước khi xây chính sách

Overload đơn giản nhất:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record User(String id, String email) {}

List<User> users = List.of(
        new User("u1", "an@example.com"),
        new User("u2", "binh@example.com")
);

Map<String, String> emailById = users.stream()
        .collect(Collectors.toMap(User::id, User::email));

System.out.println(emailById.get("u1")); // an@example.com
```

Hai hàm `User::id` và `User::email` lần lượt là **key mapper** và **value mapper**. Collector cần một giá trị đưa vào map cho mỗi phần tử nguồn. Khi dữ liệu đầy đủ và khóa duy nhất, mẫu này ngắn gọn.

Các overload quan trọng:

| Overload | Tác dụng |
|---|---|
| `toMap(keyMapper, valueMapper)` | Tạo map, ném `IllegalStateException` khi khóa trùng |
| `toMap(keyMapper, valueMapper, mergeFunction)` | Cho phép giải quyết khóa trùng |
| `toMap(keyMapper, valueMapper, mergeFunction, mapFactory)` | Thêm quyền chọn cấu trúc `Map` kết quả |

Một lỗi cần phân biệt:

```java
List<User> duplicateIds = List.of(
        new User("u1", "old@example.com"),
        new User("u1", "new@example.com")
);

// Không chạy: trùng khóa "u1" sẽ gây IllegalStateException.
// duplicateIds.stream()
//         .collect(Collectors.toMap(User::id, User::email));
```

`IllegalStateException` do **khóa trùng** và `NullPointerException` do **giá trị `null`** là hai vấn đề khác nhau. Bổ sung `mergeFunction` xử lý trùng khóa nhưng **không biến giá trị `null` thành giá trị hợp lệ** cho `toMap`.

## 4. Bốn chính sách thực tế dành cho khóa `null`

Với đầu vào:

```java
record Ticket(String id, String team, String description) {}

List<Ticket> tickets = List.of(
        new Ticket("T1", "backend", "API"),
        new Ticket("T2", null, "Chưa phân nhóm"),
        new Ticket("T3", "frontend", "UI")
);
```

Thuộc tính `team` có thể thiếu, nên phải chọn một trong các chính sách phù hợp với hợp đồng nghiệp vụ.

### 4.1. Từ chối dữ liệu thiếu khóa

Nếu `team` là trường bắt buộc, lỗi nên xuất hiện rõ ràng ở ranh giới xử lý:

```java
import java.util.Objects;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> descriptionsByTeam = tickets.stream()
        .collect(Collectors.toMap(
                ticket -> Objects.requireNonNull(
                        ticket.team(),
                        "Thiếu team cho ticket " + ticket.id()
                ),
                Ticket::description,
                (oldValue, newValue) -> newValue
        ));
```

Với `T2`, `Objects.requireNonNull` ném `NullPointerException` kèm ngữ cảnh dễ truy vết. Trong hệ thống thật, có thể kiểm tra và báo lỗi nghiệp vụ `IllegalArgumentException` hoặc trả kết quả validation trước khi tạo stream. **Điều quan trọng là từ chối có chủ đích**, thay vì trông đợi lỗi ngẫu nhiên từ collector.

### 4.2. Bỏ qua bản ghi thiếu khóa

Nếu dữ liệu thiếu khóa không nằm trong phạm vi báo cáo:

```java
Map<String, String> descriptionsByTeam = tickets.stream()
        .filter(ticket -> ticket.team() != null)
        .collect(Collectors.toMap(
                Ticket::team,
                Ticket::description,
                (first, later) -> first
        ));

System.out.println(descriptionsByTeam.keySet());
// Chứa "backend" và "frontend", không có ticket T2.
```

Lọc làm giảm số bản ghi được tổng hợp. Đây là quyết định có tác động dữ liệu: cần theo dõi số bản ghi bị bỏ nếu nghiệp vụ yêu cầu giải trình hoặc kiểm toán.

### 4.3. Ánh xạ sang một khóa thay thế được quy định

Nếu báo cáo muốn một nhóm “Chưa phân loại”:

```java
Map<String, Long> countsByTeam = tickets.stream()
        .collect(Collectors.groupingBy(
                ticket -> ticket.team() == null
                        ? "(chưa phân loại)"
                        : ticket.team(),
                Collectors.counting()
        ));

System.out.println(countsByTeam.get("(chưa phân loại)")); // 1
```

Khóa thay thế phải thuộc miền dữ liệu và **không được vô tình trùng với khóa hợp lệ thật**. Nếu một team thật tên là `"(chưa phân loại)"`, hai trường hợp bị gộp với nhau. Có thể dùng kiểu khóa riêng để phân biệt hoặc chính sách validation nhằm ngăn sự va chạm đó.

### 4.4. Biểu diễn khóa vắng mặt như một trạng thái riêng

`Optional` làm khóa `Map` có thể biểu diễn sự thiếu dữ liệu mà không dùng khóa `null`:

```java
import java.util.Optional;

Map<Optional<String>, Long> counts = tickets.stream()
        .collect(Collectors.groupingBy(
                ticket -> Optional.ofNullable(ticket.team()),
                Collectors.counting()
        ));

System.out.println(counts.get(Optional.of("backend"))); // 1
System.out.println(counts.get(Optional.empty()));       // 1
```

`Optional.empty()` là **một đối tượng khóa không null**, biểu thị nhóm thiếu team. Khi cần API dữ liệu lâu dài, có thể định nghĩa một kiểu khóa riêng, ví dụ `TeamKey` có trường phân biệt “đã biết/chưa biết”, thay vì dùng một chuỗi đặc biệt dễ va chạm.

### 4.5. Khi thực sự cần giữ khóa `null`

Nếu phải tương thích với định dạng cũ vốn quy định **một khóa `null`**, hãy dùng cấu trúc hỗ trợ điều đó và thao tác rõ ràng:

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, String> legacy = new LinkedHashMap<>();
for (Ticket ticket : tickets) {
    legacy.put(ticket.team(), ticket.description());
}

System.out.println(legacy.containsKey(null)); // true
System.out.println(legacy.get(null));         // Chưa phân nhóm
```

`LinkedHashMap` cho phép khóa `null`; với nhiều bản ghi cùng khóa, `put` sẽ **ghi đè giá trị trước bằng giá trị sau**. Đây là chính sách *last wins* trong vòng lặp tuần tự. Không suy rằng `Collectors.toMap` hoặc `groupingBy` sẽ bảo toàn khóa `null` giống cách này trên mọi JDK.

## 5. Bốn chính sách dành cho giá trị `null`

Giả sử `email` là thuộc tính tùy chọn:

```java
List<User> users = List.of(
        new User("u1", "an@example.com"),
        new User("u2", null),
        new User("u3", "chi@example.com")
);
```

Không nên gọi trực tiếp:

```java
// Có thể ném NullPointerException khi gặp giá trị null:
// Map<String, String> byId = users.stream()
//         .collect(Collectors.toMap(User::id, User::email));
```

Ngay cả overload có merge function cũng không biến `null` thành giá trị hợp lệ trong `toMap`.

### 5.1. Từ chối giá trị thiếu

```java
Map<String, String> requiredEmails = users.stream()
        .collect(Collectors.toMap(
                User::id,
                user -> Objects.requireNonNull(
                        user.email(),
                        "Thiếu email của " + user.id()
                )
        ));
```

Giải pháp này phù hợp khi email bắt buộc; lỗi sẽ được bộc lộ khi terminal `collect` tiêu thụ phần tử.

### 5.2. Loại bản ghi chưa có giá trị

```java
Map<String, String> knownEmails = users.stream()
        .filter(user -> user.email() != null)
        .collect(Collectors.toMap(User::id, User::email));

System.out.println(knownEmails.containsKey("u2")); // false
```

Chính sách này **không giữ bản ghi `u2` trong map kết quả**. Nếu ý nghĩa nghiệp vụ là “người dùng tồn tại nhưng email chưa xác định”, nên dùng cách khác.

### 5.3. Thay `null` bằng giá trị mặc định

```java
Map<String, String> emailsWithFallback = users.stream()
        .collect(Collectors.toMap(
                User::id,
                user -> user.email() == null
                        ? "(chưa có email)"
                        : user.email()
        ));

System.out.println(emailsWithFallback.get("u2")); // (chưa có email)
```

Giá trị mặc định phải được định nghĩa rõ để không bị hiểu nhầm là email thật. Việc thay thế đồng nghĩa đã **biến đổi thông tin**, nên các bước tiếp theo cần biết đó là placeholder.

### 5.4. Giữ ý nghĩa “có khóa nhưng chưa có giá trị”

Một cách tương thích với `toMap` là dùng `Optional` làm giá trị:

```java
import java.util.Optional;

Map<String, Optional<String>> optionalEmails = users.stream()
        .collect(Collectors.toMap(
                User::id,
                user -> Optional.ofNullable(user.email())
        ));

System.out.println(optionalEmails.containsKey("u2"));      // true
System.out.println(optionalEmails.get("u2").isEmpty());    // true
System.out.println(optionalEmails.containsKey("u4"));      // false
```

Trong map này, **mọi giá trị `Optional` đều không null**; `Optional.empty()` biểu thị email chưa có. Phân biệt một `Optional.empty()` ở khóa hiện hữu với khóa không tồn tại vẫn cần `containsKey` hoặc truy xuất có kiểm soát, vì `Map.get` trả `null` khi không có mapping.

Đây là một lựa chọn mô hình hóa khi cần phân biệt ba trạng thái rõ ràng, dù có thêm đối tượng bao và chi phí đọc kiểu dữ liệu. Trong API lớn, một record diễn đạt các trạng thái nghiệp vụ có thể phù hợp hơn việc lồng nhiều `Optional`.

### 5.5. Nếu cần giữ giá trị `null` thực sự

`HashMap` và `LinkedHashMap` cho phép giá trị `null`:

```java
Map<String, String> rawEmails = new LinkedHashMap<>();
for (User user : users) {
    rawEmails.put(user.id(), user.email());
}

System.out.println(rawEmails.containsKey("u2")); // true
System.out.println(rawEmails.get("u2"));         // null
```

Đây là chính sách lưu `null` thực sự, thích hợp khi phải tương thích dữ liệu cũ. Nó đòi người tiêu thụ map luôn phân biệt `containsKey` với `get`. Không chọn `Collectors.toMap` để thực hiện việc này chỉ vì `HashMap` hỗ trợ `null`.

## 6. Trùng khóa và `null` tương tác ra sao?

Mỗi khóa trong `Map` chỉ có một mapping tại một thời điểm. Nếu đầu vào có nhiều bản ghi cùng khóa, phải chỉ rõ cách chọn hoặc kết hợp giá trị:

```java
List<User> updates = List.of(
        new User("u1", "old@example.com"),
        new User("u1", "new@example.com")
);

Map<String, String> latest = updates.stream()
        .collect(Collectors.toMap(
                User::id,
                User::email,
                (previous, current) -> current
        ));

System.out.println(latest.get("u1")); // new@example.com
```

Ở đây merge function **chọn giá trị mới hơn theo encounter order** của danh sách được xử lý theo cách có thứ tự. Với nguồn không có encounter order hoặc khi yêu cầu “mới nhất” dựa trên thời gian nghiệp vụ, không dùng thứ tự tình cờ của pipeline: hãy so sánh timestamp hoặc version rõ ràng.

Nếu một bản ghi cập nhật có `email == null`, merge function trên **không cứu được** lỗi do value mapper trả `null`. Trước tiên phải chọn chính sách trong mục 5: từ chối, bỏ, thay thế hay dùng `Optional`.

Ví dụ “bản cập nhật mới nhất kể cả khi email thiếu”:

```java
Map<String, Optional<String>> latestUpdates = List.of(
        new User("u1", "old@example.com"),
        new User("u1", null)
).stream().collect(Collectors.toMap(
        User::id,
        user -> Optional.ofNullable(user.email()),
        (previous, current) -> current
));

System.out.println(latestUpdates.get("u1").isEmpty()); // true
```

Đây là **quy tắc ghi đè bằng bản cập nhật cuối cùng**, trong đó `Optional.empty()` có nghĩa cập nhật đã chủ động đặt email thành thiếu. Nếu `null` có nghĩa “không thay đổi trường hiện tại”, merge function phải được thiết kế khác:

```java
Map<String, Optional<String>> keepOldWhenMissing = List.of(
        new User("u1", "old@example.com"),
        new User("u1", null)
).stream().collect(Collectors.toMap(
        User::id,
        user -> Optional.ofNullable(user.email()),
        (previous, current) -> current.isPresent() ? current : previous
));

System.out.println(keepOldWhenMissing.get("u1").orElseThrow());
// old@example.com
```

Hai kết quả này **đều hợp lệ về kỹ thuật** nhưng mang ý nghĩa nghiệp vụ khác nhau. Phải đưa chính sách vào code thay vì đoán `null` là “xóa” hay “bỏ qua”.

## 7. Tại sao `groupingBy` không tự gom khóa `null`?

`Collectors.groupingBy(classifier)` dùng khóa do classifier tạo ra. Trong các triển khai JDK thông dụng, khi classifier trả `null`, collector ném `NullPointerException` với thông báo gần như “element cannot be mapped to a null key”. Kể cả `HashMap` có thể chứa khóa `null`, **`groupingBy` không cung cấp hợp đồng cho khóa nhóm `null`**.

```java
// Không chạy: có ticket với team == null.
// Map<String, List<Ticket>> groups = tickets.stream()
//         .collect(Collectors.groupingBy(Ticket::team));
```

Thay vào đó, hãy biến quyết định thành code:

```java
// Phương án 1: bỏ bản ghi thiếu khóa.
Map<String, List<Ticket>> knownGroups = tickets.stream()
        .filter(ticket -> ticket.team() != null)
        .collect(Collectors.groupingBy(Ticket::team));

// Phương án 2: tách hẳn một nhóm khóa Optional.empty().
Map<Optional<String>, List<Ticket>> allGroups = tickets.stream()
        .collect(Collectors.groupingBy(
                ticket -> Optional.ofNullable(ticket.team())
        ));

System.out.println(allGroups.get(Optional.empty()).size()); // 1
```

`groupingByConcurrent` cũng không phải cách né kiểm tra khóa `null`: kết quả thường là `ConcurrentMap`, và khóa phân nhóm `null` không được hỗ trợ. Muốn hỗ trợ một nhóm thiếu thông tin, dùng khóa không null như `Optional.empty()` hoặc giá trị miền dữ liệu đã quy định.

### 7.1. Dùng `partitioningBy` khi chỉ có hai trường hợp

Nếu chỉ cần chia “có team” và “thiếu team”, có thể dùng `partitioningBy`, vì khóa là `Boolean` không null:

```java
Map<Boolean, List<Ticket>> byMissingTeam = tickets.stream()
        .collect(Collectors.partitioningBy(
                ticket -> ticket.team() == null
        ));

System.out.println(byMissingTeam.get(true).size());  // 1: thiếu team
System.out.println(byMissingTeam.get(false).size()); // 2: có team
```

Cách này giữ cả hai nhóm và không cần một chuỗi placeholder. Nhưng nó chỉ biểu diễn hai trạng thái; khi muốn phân nhóm theo giá trị team cụ thể, sử dụng `groupingBy` với classifier không null.

## 8. `Map.merge` và `computeIfAbsent`: `null` còn có ý nghĩa đặc biệt

Nhiều collector và chương trình cập nhật map dựa trên cơ chế `Map.merge`. Phải hiểu luật của chính `Map`:

```java
Map<String, Integer> counts = new HashMap<>();
counts.merge("java", 1, Integer::sum);
counts.merge("java", 1, Integer::sum);
System.out.println(counts.get("java")); // 2
```

Với `merge(key, value, remappingFunction)`:

- Đối số `value` được đưa vào **phải khác `null`**.
- Nếu khóa chưa có mapping hoặc đang có giá trị `null`, `merge` đặt giá trị mới mà không cần gọi hàm gộp.
- Nếu khóa đã có giá trị không null, hàm gộp nhận giá trị cũ và mới.
- Nếu hàm gộp **trả `null`**, mapping cho khóa đó bị **xóa**.

```java
Map<String, String> map = new HashMap<>();
map.put("k", null);
map.merge("k", "A", String::concat);
System.out.println(map.get("k")); // A

map.merge("k", "B", (oldValue, newValue) -> null);
System.out.println(map.containsKey("k")); // false: merge đã xóa mapping

// map.merge("k", null, (a, b) -> a); // NullPointerException
```

Vì `null` là tín hiệu đặc biệt của `merge`, không dùng hàm merge trả `null` để biểu thị “giữ bản ghi với giá trị `null`”. Nó sẽ loại bỏ mapping.

`computeIfAbsent` cũng có quy tắc riêng: nếu khóa chưa có mapping hoặc đang ánh xạ tới `null`, nó gọi hàm tạo giá trị; nếu hàm trả `null`, phương thức không ghi giá trị mới:

```java
Map<String, String> cache = new HashMap<>();
cache.computeIfAbsent("u1", key -> null);
System.out.println(cache.containsKey("u1")); // false
```

Đừng đồng nhất “không tìm thấy mapping” với “mapping có giá trị null” khi chọn API cập nhật.

## 9. Kết quả không thể chỉnh sửa và chính sách `null`

Các cách tạo map không thể chỉnh sửa thường có hợp đồng **cấm khóa và giá trị null**:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> fixed = Map.of(
        "u1", "an@example.com",
        "u2", "binh@example.com"
);

Map<String, String> result = users.stream()
        .filter(user -> user.email() != null)
        .collect(Collectors.toUnmodifiableMap(
                User::id,
                User::email
        ));
```

`toUnmodifiableMap` từ Java 10 từ chối cả khóa và giá trị `null`; nếu khóa trùng mà không cung cấp merge function, nó cũng ném `IllegalStateException`. `Map.copyOf` (Java 10+) tương tự từ chối `null` trong map nguồn. `Map.of` (Java 9+) từ chối `null` và khóa trùng ngay khi tạo.

Nếu **bắt buộc** có map không cho chỉnh sửa nhưng vẫn chứa `null`, có thể tạo bản sao `HashMap` rồi bọc bằng `Collections.unmodifiableMap`:

```java
import java.util.Collections;

Map<String, String> legacy = new HashMap<>();
legacy.put(null, "không có mã");
legacy.put("u1", null);

Map<String, String> readOnly =
        Collections.unmodifiableMap(new HashMap<>(legacy));

System.out.println(readOnly.containsKey(null)); // true
System.out.println(readOnly.containsKey("u1")); // true
// readOnly.put("u2", "x"); // UnsupportedOperationException
```

Bản sao làm cho việc sửa `legacy` sau đó không ảnh hưởng trực tiếp đến `readOnly`. Tuy nhiên, đây là **bất biến nông**: nếu giá trị là object mutable, bên gọi vẫn có thể thay đổi trạng thái bên trong object đó. Bản wrapper không tự biến dữ liệu thành deep immutable.

## 10. Xử lý song song: tính đúng đắn trước, hiệu năng sau

Một pipeline `parallelStream()` có thể chia nguồn và tích lũy vào nhiều map trung gian rồi kết hợp chúng. Đối với `toMap`, việc gộp các map có thể tốn chi phí, đặc biệt nếu nhiều khóa trùng:

```java
Map<String, Long> eventCounts = List.of(
        "open", "save", "open", "close"
).parallelStream().collect(Collectors.groupingBy(
        event -> event,
        Collectors.counting()
));

System.out.println(eventCounts.get("open")); // 2
```

Không cập nhật một `HashMap` bên ngoài bằng nhiều thread qua `forEach`:

```java
Map<String, String> shared = new HashMap<>();

// Sai: HashMap dùng chung không an toàn trước cập nhật đồng thời.
// users.parallelStream().forEach(user ->
//         shared.put(user.id(), user.email()));
```

Một số lưu ý:

1. `Collectors.toMap` không cam kết `Map` trả về là thread-safe. `collect` quản lý các map trung gian theo hợp đồng collector; không có nghĩa bên ngoài có thể đồng thời sửa map kết quả tùy ý.
2. `Collectors.toConcurrentMap` và `groupingByConcurrent` hướng đến kết quả đồng thời, nhưng các cấu trúc concurrent thường **không cho phép khóa hoặc giá trị `null`**. Không chuyển sang collector concurrent chỉ để xử lý dữ liệu có `null`.
3. Nếu merge function chọn “bản đầu” hoặc “bản cuối”, phải xét encounter order và ngữ nghĩa kết hợp. Với dữ liệu không có thứ tự, dùng khóa thời gian/phiên bản rõ ràng nếu muốn chọn “mới nhất”.
4. Nếu nguồn có bản ghi thiếu dữ liệu, hãy chuẩn hóa/lọc/kiểm tra theo chính sách trước khi tích lũy song song. Một lỗi từ mapper có thể xuất hiện trong worker thread và được lan về terminal operation.
5. Không mặc định `parallel()` nhanh hơn. Bảo trì các map trung gian, ghép kết quả và đồng bộ có thể khiến pipeline nhỏ chậm hơn; chỉ chọn song song sau khi đo trên dữ liệu phù hợp.

## 11. Vòng đời stream và nguồn dữ liệu lớn

`filter`, `map` và các thao tác trung gian là lazy: chúng mô tả quy tắc xử lý, còn `collect` thực sự tiêu thụ stream. Một lỗi do mapper trả `null` thường chỉ xuất hiện khi terminal operation chạy.

```java
var pipeline = users.stream()
        .map(User::email);
// Chưa tiêu thụ pipeline.

// Khi terminal operation yêu cầu dữ liệu mới phát sinh xử lý thực tế.
long missing = pipeline.filter(Objects::isNull).count();
System.out.println(missing); // 1
```

Không dùng lại chính `pipeline` sau `count()`; Stream chỉ dành cho một lần tiêu thụ. Với nguồn mở tài nguyên như `Files.lines(path)`, dùng `try-with-resources` để đóng tài nguyên:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static Map<String, String> readPairs(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .map(line -> line.split("=", 2))
                .filter(parts -> parts.length == 2)
                .filter(parts -> !parts[0].isBlank())
                .collect(Collectors.toMap(
                        parts -> parts[0],
                        parts -> parts[1],
                        (oldValue, newValue) -> newValue
                ));
    }
}
```

Ví dụ quy ước không chấp nhận khóa trống, cho phép giá trị chuỗi rỗng `""` và chọn bản sau cùng khi khóa xuất hiện lại. Trong ứng dụng thực, định dạng dữ liệu cần quy định rõ cách escape dấu `=`, encoding, dòng lỗi và thông tin nhạy cảm. `Collectors.toMap` phải giữ toàn bộ các cặp khóa/giá trị trong bộ nhớ; không áp dụng trực tiếp trên nguồn vô hạn nếu không có giới hạn kết thúc.

## 12. Ví dụ tổng hợp có thể chạy (Java 17+)

Chương trình độc lập dưới đây minh họa ba chính sách khác nhau: loại `null`, giữ dấu hiệu thiếu bằng `Optional`, và thực sự giữ khóa/giá trị `null` trong `LinkedHashMap`.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Objects;
import java.util.stream.Collectors;

public class NullMapPolicyDemo {
    record User(String id, String team, String email) {}

    public static void main(String[] args) {
        List<User> users = List.of(
                new User("u1", "backend", "an@example.com"),
                new User("u2", null, null),
                new User("u3", "frontend", "chi@example.com")
        );

        // 1. Bỏ giá trị null: u2 không được đưa vào map email.
        Map<String, String> knownEmails = users.stream()
                .filter(user -> user.email() != null)
                .collect(Collectors.toMap(User::id, User::email));
        System.out.println(knownEmails.containsKey("u2")); // false

        // 2. Giữ thông tin "có user nhưng chưa có email".
        Map<String, Optional<String>> emailStates = users.stream()
                .collect(Collectors.toMap(
                        User::id,
                        user -> Optional.ofNullable(user.email())
                ));
        System.out.println(emailStates.containsKey("u2"));   // true
        System.out.println(emailStates.get("u2").isEmpty()); // true

        // 3. Phân nhóm theo team, coi thiếu team là một nhóm riêng.
        Map<Optional<String>, Long> teamCounts = users.stream()
                .collect(Collectors.groupingBy(
                        user -> Optional.ofNullable(user.team()),
                        Collectors.counting()
                ));
        System.out.println(teamCounts.get(Optional.empty())); // 1

        // 4. Nếu bắt buộc tương thích Map legacy có null thật.
        Map<String, String> legacy = new LinkedHashMap<>();
        for (User user : users) {
            legacy.put(user.team(), user.email());
        }
        System.out.println(legacy.containsKey(null)); // true
        System.out.println(legacy.get(null));         // null

        // 5. Chính sách không null và không cho chỉnh sửa.
        Map<String, String> immutableEmails = users.stream()
                .filter(user -> user.email() != null)
                .collect(Collectors.toUnmodifiableMap(
                        User::id,
                        User::email
                ));
        System.out.println(immutableEmails.size()); // 2
    }
}
```

Chương trình tránh phụ thuộc vào thứ tự duyệt của map do `toMap`, `groupingBy` hoặc `toUnmodifiableMap` tạo ra. Nó kiểm tra nội dung bằng `containsKey`, `get` và `size`, là những hợp đồng phù hợp với mục đích minh họa.

## 13. Bảng chọn chính sách

| Yêu cầu nghiệp vụ | Chính sách gợi ý |
|---|---|
| Khóa bắt buộc, thiếu khóa là dữ liệu lỗi | Kiểm tra `Objects.requireNonNull` hoặc validation rõ ràng |
| Chỉ tổng hợp bản ghi có khóa | `filter(row -> row.key() != null)` |
| Cần nhóm riêng cho khóa thiếu | Khóa thay thế không va chạm, `Optional.empty()` hoặc kiểu khóa miền dữ liệu |
| Phải lưu khóa `null` vì giao thức cũ | Dùng `HashMap`/`LinkedHashMap` trực tiếp và kiểm soát chính sách ghi đè |
| Giá trị bắt buộc, `null` là lỗi | Validate trước `toMap` hoặc reject trong value mapper |
| Giá trị thiếu thì bỏ bản ghi | `filter(row -> row.value() != null)` |
| Giá trị thiếu phải được phân biệt với khóa không có | `Map<K, Optional<V>>` hoặc kiểu trạng thái miền dữ liệu |
| Phải lưu giá trị `null` thực sự | Dùng map hỗ trợ `null` và phân biệt `containsKey` với `get` |
| Khóa trùng nhưng chỉ lấy bản mới nhất | Merge theo timestamp/version rõ ràng; không đoán từ thứ tự không được bảo đảm |
| Kết quả không thể chỉnh sửa và không cho `null` | `Collectors.toUnmodifiableMap` hoặc `Map.copyOf` |
| Kết quả không thể sửa nhưng vẫn cần `null` | Bọc bản sao bằng `Collections.unmodifiableMap` và hiểu giới hạn bất biến nông |

## 14. Sai lầm thường gặp

| Ngộ nhận | Hậu quả | Cách sửa |
|---|---|---|
| “`HashMap` nhận `null`, vậy `toMap` cũng nhận mọi `null`” | `toMap` có hợp đồng riêng; value mapper `null` có thể ném lỗi | Chọn chính sách `null` trước collector |
| “`groupingBy` có thể nhóm bằng khóa `null`” | Classifier trả `null` thường gây `NullPointerException` | Dùng `Optional.empty()` hoặc khóa thay thế |
| “Có merge function thì `toMap` sẽ cho phép value mapper trả `null`” | Merge không xử lý trường hợp giá trị đầu vào `null` | Biến `null` thành giá trị không null trước |
| “`get(k) == null` nghĩa là khóa không tồn tại” | Không phân biệt missing key và stored null | Kiểm tra `containsKey` |
| “`Map.merge(k, v, fn)` có thể nhận `v == null`” | Ném `NullPointerException` | Chỉ truyền giá trị không null |
| “Remapping function trả `null` sẽ lưu `null`” | `Map.merge` xóa mapping | Dùng chính sách lưu `null` riêng |
| “`Map.copyOf` giúp đóng băng cả map chứa `null`” | `null` không được chấp nhận | Bỏ/chuẩn hóa `null` hoặc dùng wrapper phù hợp |
| “`parallelStream().forEach(map::put)` là cách tạo map nhanh” | Map dùng chung không thread-safe | Dùng collector hoặc cấu trúc đồng thời được thiết kế đúng |
| “Thay khóa `null` bằng chuỗi bất kỳ là luôn an toàn” | Có thể trùng với khóa thật và gộp nhầm | Chọn kiểu khóa biểu diễn missing rõ ràng |
| “Không có email nghĩa là không có user” | Mất phân biệt giữa bản ghi tồn tại và thuộc tính thiếu | Dùng `Optional`/trạng thái rõ ràng hoặc giữ mapping có null |

## 15. Tự kiểm tra

1. **`HashMap` có thể chứa khóa `null` không?** Có, nhưng điều đó không bảo đảm `Collectors.toMap` hoặc `groupingBy` chấp nhận khóa `null`.
2. **Vì sao `map.get("u2") == null` chưa đủ để kết luận `u2` không tồn tại?** Vì `u2` có thể đã được ánh xạ đến giá trị `null`; cần thêm `containsKey`.
3. **`Collectors.toMap(User::id, User::email)` có an toàn khi email `null` không?** Không. Cần chọn chính sách xử lý trước khi collect.
4. **Muốn bỏ các bản ghi có team `null`, đặt bước nào trước `toMap`?** `filter(user -> user.team() != null)`.
5. **Muốn vẫn nhóm các bản ghi có team `null` với `groupingBy`, làm thế nào?** Dùng classifier trả `Optional.ofNullable(team)` hoặc khóa thay thế không null.
6. **`toUnmodifiableMap` có cho phép khóa hoặc giá trị `null` không?** Không; nó từ chối cả hai.
7. **`Map.merge` có tác dụng gì khi remapping function trả `null`?** Xóa mapping cho khóa đó.
8. **Khi `computeIfAbsent` nhận kết quả `null` từ mapping function, điều gì xảy ra?** Không tạo mapping mới nếu khóa đang vắng hoặc ánh xạ `null`.
9. **Vì sao placeholder `"(chưa phân loại)"` có thể nguy hiểm?** Vì có thể trùng với tên nhóm thật, làm gộp hai loại dữ liệu khác nghĩa.
10. **Muốn giữ trạng thái có người dùng nhưng chưa có email mà vẫn dùng `toMap`, chọn kiểu giá trị nào?** Có thể dùng `Optional<String>`, với `Optional.empty()` biểu thị email thiếu.
11. **Với khóa trùng và bản ghi cập nhật có giá trị `null`, cần quyết định gì?** `null` là “xóa giá trị”, “bỏ qua cập nhật”, “thay mặc định”, hay lỗi; merge function phải thực hiện đúng chính sách.
12. **Làm sao tạo map chỉ đọc vẫn có `null` để tương thích giao thức cũ?** Sao chép vào `HashMap` rồi bọc bằng `Collections.unmodifiableMap`; lưu ý đây là bất biến nông.

**Ghi nhớ:** `null` ở **khóa** và `null` ở **giá trị** biểu thị những vấn đề khác nhau. Trước khi `collect` thành `Map`, phải xác định ứng dụng sẽ **từ chối, bỏ qua, thay thế, biểu diễn trạng thái thiếu hay giữ nguyên `null`** cho từng trường hợp. Sau đó chọn đúng collector và loại map, quy tắc xử lý khóa trùng và hợp đồng về thứ tự/khả năng chỉnh sửa. Cách làm này giúp pipeline khai báo có kết quả dự đoán được cả khi dữ liệu không đầy đủ và khi thực thi song song.
