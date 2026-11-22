# Collection factory và dữ liệu không cho phép sửa đổi trong Java 17

Java 9 bổ sung các phương thức factory như `List.of(...)`, `Set.of(...)` và `Map.of(...)` để tạo collection ngắn gọn. Java 10 bổ sung `List.copyOf(...)`, `Set.copyOf(...)` và `Map.copyOf(...)` để tạo collection không cho phép sửa đổi từ một collection có sẵn. Những API này đều dùng ổn định trong Java 17.

Khi dùng chúng, cần hiểu hai ý riêng biệt:

- **Factory method** giúp tạo collection từ các phần tử hoặc cặp key/value.
- **Unmodifiable collection** không cho phép thay đổi cấu trúc collection qua các phương thức sửa đổi. Điều đó không tự động làm cho mọi object bên trong trở thành bất biến.

Ngoài ra, `Collections.unmodifiableList(...)` và các wrapper tương tự cũng tạo collection không cho phép sửa đổi, nhưng chúng hoạt động như **view** trên collection gốc. Khác biệt giữa view và bản sao là điều rất quan trọng khi dữ liệu được chia sẻ giữa nhiều phần của ứng dụng.

## 1. Collection factory là gì?

Collection factory là các phương thức tĩnh tạo collection mà không cần viết nhiều câu lệnh `new ArrayList<>()`, `add(...)` hoặc `put(...)`.

Ví dụ:

~~~java
import java.util.List;
import java.util.Set;
import java.util.Map;

List<String> names = List.of("An", "Bình", "Chi");
Set<Integer> ids = Set.of(10, 20, 30);
Map<String, Integer> scores = Map.of(
        "An", 90,
        "Bình", 85
);
~~~

Các collection trên có thể đọc, duyệt, tìm kiếm và dùng như các collection thông thường:

~~~java
System.out.println(names.get(0));       // An
System.out.println(ids.contains(20));   // true
System.out.println(scores.get("An"));   // 90
~~~

Nhưng chúng **không cho phép thêm, xóa hoặc thay thế phần tử**. Ví dụ:

~~~java
names.add("Dung");          // UnsupportedOperationException
ids.remove(10);             // UnsupportedOperationException
scores.put("Chi", 95);      // UnsupportedOperationException
~~~

Ngoại lệ là `UnsupportedOperationException`, cho biết thao tác sửa đổi không được collection hỗ trợ.

### 1.1. Các factory method chính

| API | Dùng để tạo | Đặc điểm |
|---|---|---|
| `List.of(e1, e2, ...)` | List | Giữ thứ tự, cho phép phần tử trùng lặp |
| `Set.of(e1, e2, ...)` | Set | Không cho phần tử trùng lặp |
| `Map.of(k1, v1, ...)` | Map | Key duy nhất, truyền key/value theo cặp |
| `Map.ofEntries(entry1, ...)` | Map | Tạo map từ các `Map.Entry` |
| `List.copyOf(collection)` | List | Tạo collection không cho phép sửa đổi từ nguồn |
| `Set.copyOf(collection)` | Set | Tạo set không cho phép sửa đổi từ nguồn |
| `Map.copyOf(map)` | Map | Tạo map không cho phép sửa đổi từ nguồn |

`List.of`, `Set.of`, `Map.of` và `Map.ofEntries` được giới thiệu từ Java 9. Các phương thức `copyOf` được bổ sung từ Java 10. Java 17 có đầy đủ các API này.

## 2. Tạo List bằng `List.of(...)`

`List.of(...)` tạo một list không cho phép sửa đổi:

~~~java
import java.util.List;

public class ListFactoryDemo {
    public static void main(String[] args) {
        List<String> languages = List.of(
                "Java",
                "Kotlin",
                "Scala"
        );

        System.out.println(languages);
        System.out.println(languages.get(1));
        System.out.println(languages.size());
    }
}
~~~

Kết quả:

~~~text
[Java, Kotlin, Scala]
Kotlin
3
~~~

List giữ thứ tự phần tử được truyền vào và cho phép các giá trị trùng lặp:

~~~java
List<String> tags = List.of("java", "backend", "java");

System.out.println(tags); // [java, backend, java]
~~~

Tuy nhiên, không thể thay đổi list:

~~~java
tags.add("database");       // UnsupportedOperationException
tags.set(0, "spring");      // UnsupportedOperationException
tags.remove("backend");     // UnsupportedOperationException
tags.clear();               // UnsupportedOperationException
~~~

### 2.1. List rỗng và List một phần tử

Có thể dùng factory cho các trường hợp nhỏ:

~~~java
List<String> empty = List.of();
List<String> one = List.of("Java");
List<String> several = List.of("Java", "SQL", "HTTP");
~~~

Không cần tạo một `ArrayList` rồi thêm từng phần tử chỉ để biểu diễn một danh sách cố định.

### 2.2. List.of không chấp nhận null

Các phần tử của `List.of(...)` không được là `null`:

~~~java
List<String> values = List.of("A", null, "B");
// Ném NullPointerException.
~~~

Nếu dữ liệu có thể chứa null, hãy xác định rõ hợp đồng dữ liệu. Có thể dùng một collection có thể sửa đổi phù hợp, hoặc kiểm tra và chuẩn hóa dữ liệu trước khi tạo list không cho phép sửa đổi.

Ví dụ kiểm tra:

~~~java
String input = null;

if (input == null) {
    throw new IllegalArgumentException("Tên không được null");
}

List<String> names = List.of(input);
~~~

Việc từ chối null ngay lúc tạo collection giúp lỗi xuất hiện gần nơi dữ liệu được đưa vào hệ thống.

## 3. Tạo Set bằng `Set.of(...)`

Set không lưu nhiều phần tử bằng nhau. Factory `Set.of(...)` yêu cầu tất cả phần tử truyền vào phải khác nhau theo quy tắc `equals`.

~~~java
import java.util.Set;

Set<String> roles = Set.of(
        "ADMIN",
        "EDITOR",
        "VIEWER"
);

System.out.println(roles.contains("ADMIN")); // true
System.out.println(roles.size());            // 3
~~~

### 3.1. Phần tử trùng lặp sẽ gây lỗi

Khác với `List.of(...)`, đoạn sau ném `IllegalArgumentException`:

~~~java
Set<String> roles = Set.of("ADMIN", "USER", "ADMIN");
// IllegalArgumentException: duplicate element
~~~

Factory không âm thầm loại bỏ phần tử trùng lặp. Nếu đầu vào có thể trùng và mục tiêu là loại trùng, hãy dùng một bước chuyển đổi rõ ràng:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

List<String> input = List.of("ADMIN", "USER", "ADMIN");
Set<String> unique = Set.copyOf(new LinkedHashSet<>(input));
~~~

Lưu ý: `Set.copyOf` tạo set không cho phép sửa đổi, nhưng **không cam kết giữ thứ tự duyệt**. Nếu thứ tự là yêu cầu nghiệp vụ, hãy chọn cấu trúc có hợp đồng thứ tự rõ ràng và thiết kế cách công bố dữ liệu tương ứng.

### 3.2. Set.of không chấp nhận null

~~~java
Set<String> codes = Set.of("A", null, "B");
// Ném NullPointerException.
~~~

Set factory không thể dùng để biểu diễn một tập hợp có phần tử null.

### 3.3. Không dựa vào thứ tự duyệt của Set.of

Set là collection không có chỉ số. Không nên dựa vào thứ tự các phần tử được in ra hoặc duyệt qua `for-each`:

~~~java
Set<String> values = Set.of("A", "B", "C");

for (String value : values) {
    System.out.println(value);
}
~~~

Tập phần tử là `A`, `B`, `C`, nhưng thứ tự duyệt không phải hợp đồng mà chương trình nên dựa vào. Nếu cần thứ tự chèn, cân nhắc `LinkedHashSet`; nếu cần sắp xếp, cân nhắc `TreeSet`.

## 4. Tạo Map bằng `Map.of(...)`

Map factory nhận các cặp key/value xen kẽ:

~~~java
import java.util.Map;

Map<String, Integer> scores = Map.of(
        "An", 90,
        "Bình", 85,
        "Chi", 95
);

System.out.println(scores.get("An")); // 90
System.out.println(scores.containsKey("Chi")); // true
~~~

Cần nhớ rằng đối số được truyền theo thứ tự:

~~~java
Map.of(key1, value1, key2, value2, key3, value3)
~~~

Không phải một danh sách các phần tử đơn lẻ.

### 4.1. Map.of giới hạn tối đa 10 cặp key/value

Các overload của `Map.of(...)` hỗ trợ từ 0 đến 10 cặp key/value. Nếu cần nhiều hơn 10 cặp, dùng `Map.ofEntries(...)`:

~~~java
import java.util.Map;

Map<String, Integer> statusCodes = Map.ofEntries(
        Map.entry("OK", 200),
        Map.entry("CREATED", 201),
        Map.entry("ACCEPTED", 202),
        Map.entry("NO_CONTENT", 204),
        Map.entry("BAD_REQUEST", 400),
        Map.entry("UNAUTHORIZED", 401),
        Map.entry("FORBIDDEN", 403),
        Map.entry("NOT_FOUND", 404),
        Map.entry("CONFLICT", 409),
        Map.entry("SERVER_ERROR", 500),
        Map.entry("UNAVAILABLE", 503)
);
~~~

`Map.entry(key, value)` tạo entry không cho phép sửa đổi. `Map.ofEntries(...)` nhận các entry đó để tạo map.

### 4.2. Map không chấp nhận key trùng hoặc null

Key phải duy nhất:

~~~java
Map<String, Integer> map = Map.of(
        "A", 1,
        "A", 2
);
// IllegalArgumentException: duplicate key
~~~

Key và value đều không được là null:

~~~java
Map<String, Integer> map1 = Map.of(null, 1); // NullPointerException
Map<String, Integer> map2 = Map.of("A", null); // NullPointerException
~~~

Khác với List, Map không cho phép key trùng. Nếu cần cập nhật giá trị theo key, hãy tạo một map có thể sửa đổi hoặc xây dựng map mới với dữ liệu đã hợp nhất.

### 4.3. Không dựa vào thứ tự duyệt của Map.of

`Map.of(...)` không đảm bảo thứ tự iteration. Không nên viết logic nghiệp vụ dựa trên thứ tự key khi duyệt:

~~~java
for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}
~~~

Nếu cần thứ tự chèn, cân nhắc `LinkedHashMap`; nếu cần sắp xếp theo key, cân nhắc `TreeMap`. Các map factory phù hợp cho dữ liệu tra cứu cố định mà thứ tự duyệt không phải yêu cầu.

## 5. Tạo collection không cho phép sửa đổi từ collection có sẵn: copyOf

Các phương thức `copyOf` cho phép tạo collection không cho phép sửa đổi từ dữ liệu đã có:

~~~java
List<String> source = new ArrayList<>();
source.add("Java");
source.add("SQL");

List<String> snapshot = List.copyOf(source);
~~~

Sau khi tạo, `snapshot` không cho phép thêm, xóa hoặc thay thế phần tử.

~~~java
snapshot.add("HTTP"); // UnsupportedOperationException
~~~

### 5.1. copyOf tạo một collection độc lập với thay đổi cấu trúc của nguồn

~~~java
List<String> source = new ArrayList<>();
source.add("Java");
source.add("SQL");

List<String> snapshot = List.copyOf(source);

source.add("HTTP");

System.out.println(source);   // [Java, SQL, HTTP]
System.out.println(snapshot); // [Java, SQL]
~~~

`snapshot` phản ánh các phần tử tại thời điểm tạo. Việc thêm phần tử mới vào list nguồn sau đó không làm thay đổi list snapshot.

Đây là cách hữu ích để lưu một bản dữ liệu đầu vào đã được kiểm tra, tránh việc người gọi thay đổi cấu trúc list sau khi truyền vào.

### 5.2. copyOf cũng từ chối null

Nếu collection nguồn có phần tử null, các phương thức factory `copyOf` ném `NullPointerException`:

~~~java
List<String> source = new ArrayList<>();
source.add("Java");
source.add(null);

List<String> snapshot = List.copyOf(source); // NullPointerException
~~~

Tương tự, `Set.copyOf` không chấp nhận phần tử null và `Map.copyOf` không chấp nhận key hoặc value null.

### 5.3. Set.copyOf xử lý phần tử trùng như thế nào?

`Set.copyOf(collection)` nhận collection nguồn có thể chứa phần tử trùng; kết quả là Set nên chỉ giữ một phần tử trong mỗi nhóm bằng nhau. Nếu nguồn có các phần tử trùng, một phần tử đại diện được giữ lại.

Điều này khác với `Set.of(a, a)`, vốn ném `IllegalArgumentException` khi đối số bị trùng:

~~~java
Set<String> fromFactory = Set.of("A", "A"); // IllegalArgumentException

List<String> input = List.of("A", "B", "A");
Set<String> copied = Set.copyOf(input);     // Hợp lệ: chỉ có A và B
~~~

Nếu cần giữ thứ tự đầu vào đồng thời loại trùng, hãy thiết kế rõ một cấu trúc có thứ tự như `LinkedHashSet` và cách công bố dữ liệu không cho phép sửa đổi phù hợp.

### 5.4. Map.copyOf tạo map không cho phép sửa đổi

~~~java
Map<String, Integer> source = new HashMap<>();
source.put("A", 1);
source.put("B", 2);

Map<String, Integer> snapshot = Map.copyOf(source);

source.put("C", 3);

System.out.println(source);   // Có A, B, C
System.out.println(snapshot); // Chỉ có A, B
~~~

`Map.copyOf` không cho phép sửa đổi cấu trúc map kết quả. Map nguồn vẫn có thể thay đổi độc lập.
Thứ tự iteration của map kết quả cũng không được bảo đảm; nếu thứ tự là yêu cầu, hãy dùng một kiểu map có hợp đồng thứ tự phù hợp và công bố nó theo cách không cho phép sửa đổi.

## 6. Phân biệt factory, copyOf và Collections.unmodifiable*

Đây là ba cách tạo collection thường bị nhầm lẫn:

1. `List.of(...)`: tạo collection không cho phép sửa đổi từ các phần tử truyền vào.
2. `List.copyOf(source)`: tạo collection không cho phép sửa đổi từ các phần tử hiện có của nguồn.
3. `Collections.unmodifiableList(source)`: tạo **view không cho phép sửa đổi** trên list nguồn.

### 6.1. Unmodifiable view không phải snapshot

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>();
source.add("Java");
source.add("SQL");

List<String> view = Collections.unmodifiableList(source);

source.add("HTTP");

System.out.println(view); // [Java, SQL, HTTP]
~~~

`view` không cho phép người giữ nó sửa list:

~~~java
view.add("Python"); // UnsupportedOperationException
~~~

Nhưng vì `view` tham chiếu đến collection nguồn, thay đổi qua `source` vẫn xuất hiện khi đọc qua `view`.

### 6.2. So sánh với copyOf

~~~java
List<String> source = new ArrayList<>();
source.add("Java");
source.add("SQL");

List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("HTTP");

System.out.println(view);     // [Java, SQL, HTTP]
System.out.println(snapshot); // [Java, SQL]
~~~

| Tiêu chí | `Collections.unmodifiableList(source)` | `List.copyOf(source)` |
|---|---|---|
| Có thể sửa qua biến kết quả? | Không | Không |
| Thay đổi cấu trúc qua nguồn có thấy ở kết quả? | Có | Không |
| Tạo bản snapshot cấu trúc? | Không | Có |
| Chấp nhận null từ nguồn? | Có, wrapper không tự kiểm tra null | Không |
| Mục đích thường gặp | Cung cấp view chỉ đọc của collection đang tồn tại | Công bố/cất giữ bản collection không cho sửa đổi |

**Lưu ý:** `Collections.unmodifiableList` không làm collection gốc trở nên không thể sửa đổi. Nếu mã khác vẫn giữ tham chiếu đến `source`, mã đó có thể thêm/xóa phần tử và view sẽ phản ánh thay đổi.

### 6.3. Các wrapper tương tự cho Set và Map

Java cung cấp:

~~~java
Collections.unmodifiableSet(sourceSet);
Collections.unmodifiableMap(sourceMap);
~~~

Chúng có cùng nguyên tắc view không cho phép sửa đổi: không sửa qua wrapper, nhưng thay đổi trên collection gốc vẫn được phản ánh.

Nếu muốn snapshot cấu trúc, cân nhắc:

~~~java
Set.copyOf(sourceSet);
Map.copyOf(sourceMap);
~~~

## 7. Không cho phép sửa đổi cấu trúc không đồng nghĩa object bên trong bất biến

Một điểm rất quan trọng: collection factory chỉ ngăn việc thay đổi **cấu trúc collection**. Nếu phần tử là một object có thể sửa đổi, trạng thái của object đó vẫn có thể thay đổi.

Ví dụ:

~~~java
import java.util.List;

class User {
    private String name;

    User(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}

List<User> users = List.of(new User("An"));

users.get(0).setName("Bình"); // Hợp lệ
System.out.println(users.get(0).getName()); // Bình
~~~

Không thể gọi `users.add(...)` hoặc `users.set(0, ...)`, nhưng có thể gọi setter trên object được trả về từ `get(0)`.

Đây là **shallow unmodifiability**: cấu trúc collection không thay đổi được, nhưng các object được tham chiếu có thể vẫn mutable.

### 7.1. Phần tử bất biến giúp dữ liệu an toàn hơn

Các kiểu như `String`, wrapper primitive (`Integer`, `Long`, `Boolean`) và record có thiết kế thành phần bất biến thường phù hợp để đưa vào collection không cho phép sửa đổi.

Ví dụ:

~~~java
record UserInfo(String id, String name) {
}

List<UserInfo> users = List.of(
        new UserInfo("U01", "An"),
        new UserInfo("U02", "Bình")
);
~~~

Record không tự đảm bảo mọi thành phần đều immutable nếu component chứa object mutable. Ví dụ record có component `List<String>` vẫn cần cân nhắc defensive copy trong constructor:

~~~java
record Team(String name, List<String> members) {
    public Team {
        members = List.copyOf(members);
    }
}
~~~

Như vậy, thay đổi cấu trúc list đầu vào không làm thay đổi list được lưu trong record. Tuy nhiên, nếu phần tử trong list là object mutable, việc sao chép list vẫn là sao chép nông.

### 7.2. Sao chép collection lồng nhau

Nếu map chứa các list, `Map.copyOf` chỉ làm map ngoài không cho phép sửa đổi. Các list bên trong vẫn có thể thay đổi:

~~~java
Map<String, List<String>> source = new HashMap<>();
source.put("backend", new ArrayList<>(List.of("Java", "SQL")));

Map<String, List<String>> copy = Map.copyOf(source);

copy.get("backend").add("HTTP"); // Hợp lệ: list bên trong mutable
~~~

Nếu muốn ngăn thay đổi cả collection bên trong, cần sao chép từng lớp:

~~~java
Map<String, List<String>> immutableStructure = source.entrySet()
        .stream()
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                Map.Entry::getKey,
                entry -> List.copyOf(entry.getValue())
        ));
~~~

Cấu trúc map và các list bên trong đều không cho phép sửa đổi. Nhưng object phần tử trong list, nếu mutable, vẫn không tự trở thành immutable.

## 8. Factory collection có thread-safe không?

Không nên suy luận rằng một collection không cho phép sửa đổi là một cơ chế đồng bộ hóa hoặc đảm bảo an toàn cho mọi trạng thái được tham chiếu.

- Collection factory không cung cấp thao tác sửa đổi cấu trúc.
- Việc đọc đồng thời một collection không cho phép sửa đổi thường đơn giản hơn khi cấu trúc không bị thay đổi.
- Nhưng nếu phần tử bên trong mutable, nhiều luồng vẫn có thể tranh chấp khi sửa trạng thái của phần tử đó.
- Nếu collection nguồn hoặc object phần tử vẫn bị chia sẻ và thay đổi ở nơi khác, cần thiết kế đồng bộ và công bố dữ liệu đúng cách.

Ví dụ:

~~~java
List<String> names = List.of("An", "Bình", "Chi");
~~~

List này không thể thêm/xóa/sửa phần tử, nên phù hợp để chia sẻ như dữ liệu cấu hình cố định. Nhưng nếu collection chứa object mutable, hãy bảo vệ trạng thái của các object đó theo quy tắc đồng bộ phù hợp.

Ngoài ra, các collection tạo bởi factory có thể là **value-based**. Không dựa vào identity của chúng, không so sánh bằng `==` để suy luận nội dung và không dùng instance làm monitor để đồng bộ hóa. Hãy dùng `equals` để so sánh nội dung và một lock riêng nếu cần đồng bộ.

## 9. So sánh với Arrays.asList và collection có thể sửa đổi

Không phải mọi cách tạo list ngắn gọn đều tạo collection không cho phép sửa đổi.

### 9.1. Arrays.asList là list kích thước cố định

~~~java
import java.util.Arrays;
import java.util.List;

String[] array = {"Java", "SQL"};
List<String> list = Arrays.asList(array);

list.set(0, "Kotlin"); // Hợp lệ
list.add("HTTP");      // UnsupportedOperationException
~~~

`Arrays.asList` trả về list có kích thước cố định, nhưng vẫn cho phép thay thế phần tử. Thay đổi giữa array và list được phản ánh hai chiều vì chúng dùng chung dữ liệu nền.

Do đó, nó khác với `List.of(...)`, vốn không cho phép cả thao tác `set`.

### 9.2. ArrayList có thể sửa đổi

Nếu cần thêm, xóa hoặc thay thế phần tử, dùng collection mutable:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Bình"));

names.add("Chi");
names.set(0, "Anh");

System.out.println(names); // [Anh, Bình, Chi]
~~~

Ở đây `List.of(...)` chỉ là nguồn ban đầu; `new ArrayList<>(...)` tạo list mới có thể sửa đổi.

### 9.3. Chọn đúng cách tạo collection

| Nhu cầu | API phù hợp |
|---|---|
| Danh sách cố định, không cho sửa | `List.of(...)` |
| Tập giá trị duy nhất, không cho sửa | `Set.of(...)` |
| Map key/value cố định, không cho sửa | `Map.of(...)` / `Map.ofEntries(...)` |
| Công bố bản sao không cho sửa từ nguồn | `List.copyOf`, `Set.copyOf`, `Map.copyOf` |
| Tạo view chỉ đọc, vẫn phản ánh thay đổi nguồn | `Collections.unmodifiableList/Set/Map` |
| Cần list có thể thêm/xóa/thay thế | `new ArrayList<>(...)` |
| Cần set có thứ tự chèn và mutable | `new LinkedHashSet<>(...)` |
| Cần map có thứ tự chèn và mutable | `new LinkedHashMap<>(...)` |
| Cần list có kích thước cố định nhưng thay được phần tử | `Arrays.asList(...)` |

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `List.of(...).add(...)` ném UnsupportedOperationException | List factory không cho sửa đổi | Tạo `ArrayList` nếu cần thêm phần tử |
| `Set.of("A", "A")` ném IllegalArgumentException | Đối số có phần tử trùng | Loại trùng trước hoặc dùng `Set.copyOf` nếu đúng nghiệp vụ |
| `List.of("A", null)` ném NullPointerException | Factory không chấp nhận null | Kiểm tra/chuẩn hóa null hoặc chọn collection có hợp đồng phù hợp |
| `Map.of(...)` có key trùng | Map yêu cầu key duy nhất | Hợp nhất dữ liệu trước khi tạo map |
| `Map.of` có hơn 10 cặp | Overload của `Map.of` chỉ hỗ trợ tối đa 10 cặp | Dùng `Map.ofEntries` |
| Nghĩ `unmodifiableList` là snapshot | Wrapper chỉ là view | Dùng `List.copyOf` khi cần bản sao cấu trúc |
| Nghĩ collection unmodifiable làm phần tử immutable | Chỉ cấu trúc collection bị khóa | Dùng phần tử immutable hoặc defensive copy phù hợp |
| Dựa vào thứ tự duyệt của Set/Map factory | API không cam kết thứ tự đó | Dùng cấu trúc có hợp đồng thứ tự rõ ràng |
| Dùng `==` để so sánh hai collection factory | Không nên dựa vào identity/value-based semantics | Dùng `equals` |

## 11. Ví dụ tổng hợp chạy trên Java 17

Tạo file **`CollectionFactoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CollectionFactoryDemo {
    public static void main(String[] args) {
        // Factory: list giữ thứ tự và cho phép phần tử trùng.
        List<String> languages = List.of("Java", "SQL", "Java");

        // Factory: set không chứa phần tử trùng.
        Set<String> roles = Set.of("ADMIN", "EDITOR", "VIEWER");

        // Factory: map nhỏ.
        Map<String, Integer> statusCodes = Map.of(
                "OK", 200,
                "NOT_FOUND", 404
        );

        // Factory: map nhiều hơn 10 cặp.
        Map<String, String> headers = Map.ofEntries(
                Map.entry("Content-Type", "application/json"),
                Map.entry("Cache-Control", "no-cache"),
                Map.entry("X-Application", "demo")
        );

        // copyOf: snapshot không cho sửa.
        List<String> source = new ArrayList<>(List.of("An", "Bình"));
        List<String> snapshot = List.copyOf(source);
        source.add("Chi");

        // unmodifiableList: view phản ánh nguồn.
        List<String> view = Collections.unmodifiableList(source);
        source.add("Dung");

        // Mutable copy: có thể sửa.
        List<String> editable = new ArrayList<>(languages);
        editable.add("Kotlin");

        System.out.println(languages);
        System.out.println(roles.contains("ADMIN"));
        System.out.println(statusCodes.get("OK"));
        System.out.println(headers.get("Content-Type"));
        System.out.println(snapshot); // [An, Bình]
        System.out.println(view);     // [An, Bình, Chi, Dung]
        System.out.println(editable);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 CollectionFactoryDemo.java
java CollectionFactoryDemo
~~~

Kết quả chính:

~~~text
[Java, SQL, Java]
true
200
application/json
[An, Bình]
[An, Bình, Chi, Dung]
[Java, SQL, Java, Kotlin]
~~~

Ví dụ minh họa ba kiểu dữ liệu:

- Collection factory tạo dữ liệu không cho sửa đổi ngay từ đầu.
- `copyOf` tạo bản sao cấu trúc không cho sửa đổi.
- Wrapper `unmodifiableList` tạo view chỉ đọc phản ánh thay đổi từ nguồn.
- `ArrayList` tạo bản mutable khi ứng dụng cần cập nhật dữ liệu.

## 12. Bài tập thực hành

### Bài 1: Chọn factory phù hợp

Tạo:

1. List các ngày trong tuần, giữ thứ tự.
2. Set các quyền `READ`, `WRITE`, `ADMIN`.
3. Map ánh xạ mã HTTP sang nhãn, có 12 cặp.

**Gợi ý đáp án:**

~~~java
List<String> days = List.of(
        "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"
);

Set<String> permissions = Set.of("READ", "WRITE", "ADMIN");

Map<Integer, String> labels = Map.ofEntries(
        Map.entry(200, "OK"),
        Map.entry(201, "Created"),
        Map.entry(202, "Accepted"),
        Map.entry(204, "No Content"),
        Map.entry(301, "Moved"),
        Map.entry(302, "Found"),
        Map.entry(400, "Bad Request"),
        Map.entry(401, "Unauthorized"),
        Map.entry(403, "Forbidden"),
        Map.entry(404, "Not Found"),
        Map.entry(409, "Conflict"),
        Map.entry(500, "Server Error")
);
~~~

### Bài 2: Vì sao đoạn này ném ngoại lệ?

~~~java
List<String> names = List.of("An", "Bình");
names.add("Chi");
~~~

**Đáp án:** `List.of` trả về list không cho phép sửa đổi. `add` là thao tác thay đổi cấu trúc nên ném `UnsupportedOperationException`. Nếu cần list mutable:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Bình"));
names.add("Chi");
~~~

### Bài 3: So sánh view và snapshot

~~~java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("C");
~~~

Giá trị của `view` và `snapshot` là gì?

**Đáp án:**

- `view`: `[A, B, C]`, vì wrapper nhìn vào list nguồn.
- `snapshot`: `[A, B]`, vì `copyOf` giữ cấu trúc tại thời điểm tạo.

### Bài 4: Collection không cho sửa đổi có làm object bên trong immutable không?

~~~java
List<StringBuilder> values = List.of(new StringBuilder("Java"));
values.get(0).append(" 17");
~~~

**Đáp án:** Lệnh `append` hợp lệ. List không cho thêm/xóa/thay thế phần tử, nhưng `StringBuilder` là object mutable. Sau lệnh, nội dung phần tử là `Java 17`.

### Bài 5: Chọn cấu trúc khi cần thứ tự

Ứng dụng cần một tập quyền không trùng, giữ đúng thứ tự khai báo và không cho bên ngoài sửa đổi.

**Gợi ý:** Có thể xây dựng `LinkedHashSet` để duy trì thứ tự chèn, sau đó cung cấp một view không cho sửa đổi hoặc một bản sao có hợp đồng thứ tự phù hợp. Không dựa vào thứ tự iteration của `Set.of` hay `Set.copyOf`.

## 13. Ghi nhớ

Khi chọn collection factory trong Java 17, hãy xác định ba điều:

1. **Cần kiểu collection nào?** List giữ thứ tự và cho phép trùng; Set không trùng; Map ánh xạ key/value.
2. **Dữ liệu được tạo từ đâu?** Dùng `of(...)` cho các phần tử đã biết; dùng `copyOf(...)` để tạo collection không cho sửa đổi từ nguồn.
3. **Cần snapshot hay view?** `copyOf` tạo bản sao cấu trúc; `Collections.unmodifiable...` tạo view chỉ đọc phản ánh thay đổi của nguồn.

Cuối cùng, hãy nhớ rằng **unmodifiable không đồng nghĩa deep immutable**. Collection không cho phép sửa đổi cấu trúc vẫn có thể chứa object mutable. Nếu dữ liệu cần được bảo vệ hoàn toàn ở nhiều cấp, hãy dùng phần tử bất biến và defensive copy phù hợp cho collection lồng nhau.

## 14. Tài liệu tham khảo

- [Oracle Java SE 17 — List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `List.of`, `List.copyOf` và đặc tính unmodifiable/value-based.
- [Oracle Java SE 17 — Set API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): `Set.of`, `Set.copyOf`, duplicate và thứ tự iteration.
- [Oracle Java SE 17 — Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `Map.of`, `Map.ofEntries`, `Map.copyOf` và giới hạn cặp key/value.
- [Oracle Java SE 17 — Collections API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): các wrapper `unmodifiableList`, `unmodifiableSet`, `unmodifiableMap`.
- [OpenJDK JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): thiết kế các collection factory được bổ sung từ Java 9.

