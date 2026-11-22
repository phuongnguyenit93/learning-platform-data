# Kiểm tra `null` tại ranh giới dữ liệu khi thiết kế collection chỉ đọc (Java 10+)

## 1. Tại sao phải kiểm tra `null` ngay tại ranh giới?

Trong Java, kiểu tham chiếu như `String`, `List<String>` hay `Map<String, String>` **không tự động bảo đảm giá trị khác `null`**. Một API nhận dữ liệu từ JSON, database, lời gọi service, input của người dùng hoặc module khác có thể nhận một collection `null`, collection chứa phần tử `null`, hay Map chứa khóa/giá trị `null`.

Khi thiết kế một đối tượng sở hữu **snapshot chỉ đọc**, nhiều chương trình dùng các factory Java 10:

```java
var roles = List.copyOf(inputRoles);
var attributes = Map.copyOf(inputAttributes);
```

Các dòng trên là ví dụ trong một phương thức, giả sử `inputRoles` và `inputAttributes` đã có kiểu thích hợp.

**Điểm quan trọng:** `List.copyOf` và `Map.copyOf` **không chấp nhận `null`** (tương tự `Set.copyOf`). Chúng sẽ ném `NullPointerException` nếu bản thân nguồn là `null` hoặc dữ liệu bên trong chứa giá trị `null` không được hỗ trợ. Đây là một **ràng buộc hiện hành của Java**, không phải hạn chế cũ đã được dỡ bỏ.

Chủ động kiểm tra tại **ranh giới vào** giúp:

1. Phát hiện dữ liệu sai trước khi nó đi sâu vào domain model.
2. Trả thông báo có ngữ cảnh, ví dụ `roles[2]` hoặc `attributes[mode]`.
3. Quy định rõ khi nào `null` phải bị từ chối, được mặc định hóa, hoặc được bỏ qua.
4. Xây dựng snapshot không sửa đổi có invariant rõ ràng cho mã bên trong.
5. Tránh biến `NullPointerException` khó hiểu ở một bước xử lý muộn thành lỗi bất ngờ.

Một chính sách tốt không chỉ “tránh NPE”: nó phải **giữ đúng ý nghĩa nghiệp vụ của dữ liệu thiếu hoặc không hợp lệ**.

## 2. Hiểu bốn loại `null` thường gặp

Trước khi viết validator, phân biệt vị trí xuất hiện `null`.

| Nơi xuất hiện | Ví dụ | Rủi ro khi tạo kết quả chỉ đọc |
| --- | --- | --- |
| Chính đối tượng collection | `List<String> roles = null;` | `List.copyOf(roles)` ném `NullPointerException` |
| Phần tử List/Set | `Arrays.asList("read", null)` | `List.copyOf` / `Set.copyOf` từ chối phần tử `null` |
| Khóa Map | `map.put(null, "x")` trên `HashMap` | `Map.copyOf(map)` từ chối khóa `null` |
| Giá trị Map | `map.put("mode", null)` trên `HashMap` | `Map.copyOf(map)` từ chối giá trị `null` |

**Không suy luận sai rằng vì `HashMap` hoặc `ArrayList` chấp nhận `null` nên `copyOf` cũng chấp nhận.** Mỗi implementation/factory có hợp đồng riêng.

Ví dụ Java hiện hành:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

var list = new ArrayList<String>();
list.add("A");
list.add(null); // ArrayList cho phép null

var map = new HashMap<String, String>();
map.put("mode", null); // HashMap cho phép null

// List.copyOf(list); // NullPointerException
// Map.copyOf(map);   // NullPointerException
```

Các lệnh với `var` phải nằm trong phương thức hoặc block thích hợp; import được viết để cho thấy các lớp liên quan. Những câu lệnh `copyOf` ghi chú là **các lời gọi có thể biên dịch nhưng ném ngoại lệ khi thực thi**.

## 3. Kiểm tra container đầu vào bằng `Objects.requireNonNull`

`Objects.requireNonNull` thuộc `java.util.Objects` và được thiết kế để kiểm tra tham số/phần dữ liệu bắt buộc khác `null`.

```java
static List<String> snapshotRoles(List<String> input) {
    Objects.requireNonNull(input, "roles");
    return List.copyOf(input);
}
```

Đoạn trên là phương thức minh họa trong một lớp và cần import `java.util.List`, `java.util.Objects`.

Khi `input == null`, lệnh `requireNonNull` ném `NullPointerException` với thông điệp `roles` thay vì để lỗi phát sinh sâu hơn. Với input hợp lệ, nó trả lại **chính tham chiếu đầu vào**.

Các overload phổ biến:

```java
Objects.requireNonNull(value);              // NPE nếu null
Objects.requireNonNull(value, "fieldName"); // NPE có thông điệp
Objects.requireNonNull(value, () -> "field " + index); // dựng thông điệp khi cần
```

Overload nhận `Supplier<String>` có thể tránh việc tạo thông điệp phức tạp trong trường hợp không có lỗi. Không cần lạm dụng lambda cho mọi thông điệp ngắn.

**Phân biệt lỗi lập trình và lỗi nghiệp vụ:** `NullPointerException` do `requireNonNull` là phù hợp khi hợp đồng API nói tham số bắt buộc không được là null. Với dữ liệu người dùng có thể thiếu hợp lệ theo nghiệp vụ, ứng dụng có thể chọn lỗi validation riêng hoặc `IllegalArgumentException`/đối tượng báo lỗi có cấu trúc. Không có quy tắc rằng mọi giá trị null từ request phải biến thành NPE; quan trọng là hợp đồng và tầng chịu trách nhiệm xử lý.

## 4. Kiểm tra từng phần tử trước khi dùng `List.copyOf`

Một danh sách **khác null** vẫn có thể chứa phần tử null. Chỉ gọi `Objects.requireNonNull(input)` không đủ để bảo đảm `List.copyOf(input)` thành công.

Giải pháp fail-fast với thông điệp vị trí:

```java
static <T> List<T> strictList(List<? extends T> source, String field) {
    Objects.requireNonNull(source, field);
    for (int i = 0; i < source.size(); i++) {
        Objects.requireNonNull(source.get(i), field + "[" + i + "]");
    }
    return List.copyOf(source);
}
```

Đây là một **phương thức minh họa**, cần `java.util.List` và `java.util.Objects`. Ví dụ:

```java
var roles = strictList(List.of("reader", "writer"), "roles"); // hợp lệ
// strictList(Arrays.asList("reader", null), "roles");
// ném NullPointerException với thông điệp "roles[1]"
```

Với API nhận collection mà không phải `List`, có thể duyệt bằng vòng `for` và dùng chỉ số tự tăng theo **thứ tự duyệt**. Khi đầu vào thực sự là `List`, ghi `field[index]` giúp định vị phần tử trực tiếp. Nếu nguồn là collection có thao tác `get` tốn chi phí hoặc là view bất thường, một lần duyệt bằng iterator có thể phù hợp hơn; giữ nguyên ngữ nghĩa của validator.

**Quan trọng với concurrency:** kiểm tra xong rồi gọi `copyOf` là hai bước. Nếu một luồng khác vẫn được sửa nguồn giữa hai bước, validation và snapshot không phải thao tác nguyên tử. Với nguồn mutable được chia sẻ, cần phối hợp cập nhật (ví dụ cùng khóa) hoặc tạo dữ liệu đầu vào ổn định trước khi xác thực. `List.copyOf` không tự biến một collection đang bị sửa cạnh tranh thành snapshot nguyên tử.

## 5. Kiểm tra khóa và giá trị trước khi dùng `Map.copyOf`

Map có hai vị trí cần kiểm tra: **key** và **value**. Điều này thường quan trọng ở ranh giới JSON/configuration, nơi khóa có ý nghĩa định danh một trường.

```java
static <K, V> Map<K, V> strictMap(
        Map<? extends K, ? extends V> source,
        String field) {
    Objects.requireNonNull(source, field);

    for (var entry : source.entrySet()) {
        var key = Objects.requireNonNull(entry.getKey(),
                field + " contains null key");
        Objects.requireNonNull(entry.getValue(),
                field + "[" + key + "]");
    }
    return Map.copyOf(source);
}
```

Đây là phương thức minh họa trong một lớp, cần `java.util.Map` và `java.util.Objects`. Ví dụ:

```java
var props = new HashMap<String, String>();
props.put("mode", null);

// strictMap(props, "properties");
// NullPointerException: properties[mode]
```

Tự kiểm tra từng ánh xạ giúp **biết chính xác trường nào bị thiếu**, thay vì chỉ nhận `NullPointerException` không có key cụ thể từ `Map.copyOf`.

**Vấn đề Map.get:** với Map cho phép giá trị null, `map.get("mode") == null` có thể nghĩa là:

- không tồn tại key `"mode"`; hoặc
- key tồn tại nhưng ánh xạ tới `null`.

Dùng `map.containsKey("mode")` nếu nghiệp vụ cần phân biệt hai trường hợp trên. `Map.copyOf` không cho lưu null value, nên sau khi chuyển sang kết quả `copyOf`, mỗi key có tồn tại sẽ gắn với value không null.

## 6. Kiểm tra `Set.copyOf` và dữ liệu không duy nhất

`Set.copyOf` cũng xuất hiện từ Java 10, yêu cầu collection đầu vào **khác null và không chứa phần tử null**:

```java
var source = java.util.Arrays.asList("A", "B", null);
// var result = Set.copyOf(source); // NullPointerException
```

Khác với List, Set không mô tả thứ tự theo chỉ số. Nếu muốn thông điệp lỗi, có thể duyệt từng phần tử và nêu tên field hoặc thông tin bản ghi:

```java
static <T> Set<T> strictSet(Collection<? extends T> source) {
    Objects.requireNonNull(source, "permissions");
    for (var permission : source) {
        Objects.requireNonNull(permission, "permissions contains null element");
    }
    return Set.copyOf(source);
}
```

Đoạn trên cần `java.util.Collection`, `Objects`, `Set`.

Nếu collection đầu vào có phần tử bằng nhau theo `equals`, `Set.copyOf` giữ một phần tử đại diện cho mỗi nhóm trùng; không nên mặc định tính độc nhất là lỗi. Nếu nghiệp vụ muốn **từ chối bản ghi trùng**, phải bổ sung một bước kiểm tra riêng trước khi tạo Set. `null` và trùng lặp là **hai loại ràng buộc khác nhau**, không được đánh đồng.

## 7. Không nhầm snapshot `copyOf` với view không sửa trực tiếp

Hãy so sánh:

```java
var source = new ArrayList<String>();
source.add("reader");
source.add(null);

var editable = new ArrayList<>(source);
var liveView = Collections.unmodifiableList(source);

// List.copyOf(source); // NullPointerException
```

Đoạn cần `java.util.ArrayList`, `java.util.Collections` và `java.util.List`.

- `new ArrayList<>(source)` tạo bản sao cấu trúc có thể sửa, **cho phép null**.
- `Collections.unmodifiableList(source)` trả view không cho sửa qua view nhưng **phản ánh thay đổi từ backing source**; nếu backing cho phép null thì view cũng có thể thấy null.
- `List.copyOf(source)` tạo danh sách không sửa được, **không phản ánh sửa cấu trúc của nguồn về sau** và **từ chối null**.

Vì vậy, thay một wrapper cũ bằng `List.copyOf` có thể là **thay đổi hợp đồng dữ liệu**, không chỉ tối ưu cú pháp.

Nếu cần **snapshot không sửa được nhưng phải giữ các null có ý nghĩa**, một phương án là:

```java
List<String> nullableSnapshot =
        Collections.unmodifiableList(new ArrayList<>(source));
```

Đoạn này tạo một `ArrayList` riêng rồi bọc view trên bản sao đó. Để giữ được tính chất snapshot cấu trúc, không được để mã khác giữ tham chiếu và sửa backing copy. Phần tử mutable vẫn dùng tham chiếu chung (*shallow copy*).

**Đừng lén lọc bỏ null chỉ để được dùng `List.copyOf`.** Nếu null mang nghĩa “chưa được xác nhận” hoặc “không có dữ liệu”, việc xóa nó có thể khiến người đọc mất ngữ nghĩa.

## 8. Ba chính sách xử lý null tại ranh giới

Không có chính sách chung đúng cho mọi domain. Một thiết kế cần xác định giá trị thiếu có nghĩa gì.

### 8.1. Chính sách A: từ chối (*reject*)

Nếu `userId`, `role` hoặc `currencyCode` là dữ liệu bắt buộc, **không nhận null** và báo vị trí lỗi:

```java
String userId = Objects.requireNonNull(rawUserId, "userId");
```

Sau đó mới xây domain object hoặc collection chỉ đọc. Điều này giúp trạng thái bên trong đơn giản: các phương thức xử lý không phải liên tục kiểm tra null cho trường được đảm bảo.

Không sử dụng mặc định hóa để che lỗi nếu việc thiếu dữ liệu cần làm request thất bại.

### 8.2. Chính sách B: thay bằng mặc định (*default*)

Nếu nghiệp vụ nói “thiếu locale thì chọn locale mặc định”, có thể dùng:

```java
String locale = Objects.requireNonNullElse(rawLocale, "vi-VN");
```

`Objects.requireNonNullElse` có từ Java 9 và vẫn hiện hành. Nếu cả giá trị lẫn default đều null, phương thức ném `NullPointerException`. Dùng nó khi **mặc định hóa là một quy tắc nghiệp vụ được công nhận**, không phải để xóa dấu vết dữ liệu sai.

Phân biệt `null` với chuỗi rỗng `""` và chuỗi chỉ có whitespace: `requireNonNullElse` **chỉ** xử lý null, không tự trim, parse, hay xác thực định dạng.

### 8.3. Chính sách C: bỏ phần tử null (*filter*)

Nếu danh sách sự kiện phụ có ý nghĩa “chỉ quan tâm các phần tử khác null”, có thể lọc trước khi tạo kết quả không sửa được:

```java
var accepted = java.util.Arrays.asList("reader", null, "writer")
        .stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());

// accepted = [reader, writer]
```

Đoạn trên cần import `java.util.Objects` và `java.util.stream.Collectors`. `Collectors.toUnmodifiableList` có từ Java 10; nếu null **không được lọc**, collector này sẽ từ chối null.

**Không lạm dụng `filter(Objects::nonNull)` trên dữ liệu bắt buộc.** Ví dụ danh sách từng dòng giao dịch có một dòng null thường là lỗi đầu vào, không phải một dòng được quyền bỏ qua và tiếp tục.

## 9. Phân biệt `Optional` với `null` trong thiết kế API

`Optional<T>` diễn đạt một kết quả có thể không tồn tại mà không cần giá trị null làm tín hiệu:

```java
Optional<String> maybeName = Optional.ofNullable(rawName);
```

`Optional.ofNullable(null)` trả về `Optional.empty()`, còn `Optional.of(null)` ném `NullPointerException`.

Nhưng không nên thay mọi giá trị bắt buộc bằng `Optional.empty()`. Nếu trường là **bắt buộc**, việc đổi null thành empty mà không báo lỗi có thể che dấu dữ liệu sai. `Optional` phù hợp khi sự vắng mặt là một trạng thái **được định nghĩa rõ ràng trong hợp đồng**.

Ví dụ muốn biểu diễn một Map có key tồn tại nhưng giá trị tùy chọn:

```java
Map<String, Optional<String>> fields = Map.of(
        "nickname", Optional.empty(),
        "language", Optional.of("vi")
);
```

Đây là cách dùng một đối tượng `Optional` **không null** làm value, khác với Map value `null`. Tuy nhiên, Map thiếu key và Map có key ánh xạ tới `Optional.empty()` có thể mang ý nghĩa khác nhau; API phải giải thích rõ.

## 10. Collector tạo collection không sửa được cũng có kiểm tra null

Java 10 bổ sung các collector:

- `Collectors.toUnmodifiableList()`
- `Collectors.toUnmodifiableSet()`
- `Collectors.toUnmodifiableMap(keyMapper, valueMapper)` và overload có merge function.

Các collector này cũng **không cho phần tử/khóa/giá trị null** theo hợp đồng tương ứng.

```java
var users = java.util.Arrays.asList("A", null, "B");

// users.stream().collect(Collectors.toUnmodifiableList());
// Ném NullPointerException khi collect.

var cleanedUsers = users.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());
```

Một số API tạo List khác có thể có hợp đồng về null **khác**. Ví dụ `Stream.toList()` (có từ Java 16) trả list không sửa được nhưng không có ràng buộc cấm null giống `Collectors.toUnmodifiableList()`. **Không suy luận chính sách null chỉ từ việc kết quả là một List không thể sửa**; đọc đúng Javadoc của factory/collector được sử dụng.

Với Map collector, không chỉ cần kiểm tra null mà còn phải quyết định chính sách khi **hai khóa bằng nhau**: overload không có merge function có thể ném `IllegalStateException` do khóa trùng. Đây là vấn đề riêng, không được giải quyết tự động bằng kiểm tra null.

## 11. Ưu tiên thông điệp lỗi có thể hành động được

Một ngoại lệ chỉ ghi “`NullPointerException`” thường không đủ giúp người sửa dữ liệu nhận biết bản ghi nào sai. Khi xác thực ranh giới, thông điệp tốt nên nói rõ:

- **Tên trường**: `roles`, `properties`, `userId`.
- **Vị trí**: `roles[1]` đối với danh sách.
- **Key bị ảnh hưởng**: `properties[mode]` đối với Map.
- **Quy tắc**: “must not be null” hoặc “required field”.
- **Ngữ cảnh không nhạy cảm**: ví dụ chỉ số dòng, mã trường; tránh đưa token bí mật hay nội dung nhạy cảm vào exception/log.

Mẫu kiểm tra:

```java
Objects.requireNonNull(roles, "roles");
for (int i = 0; i < roles.size(); i++) {
    Objects.requireNonNull(roles.get(i), "roles[" + i + "]");
}
```

Trong một lớp domain hoặc service, nên cân nhắc gom quy tắc vào constructor/factory đầu vào để mọi đường tạo đối tượng đều đi qua validation. Nếu dữ liệu đến từ request, có thể chuyển exception thành thông báo validation phù hợp với tầng HTTP/UI, nhưng không nên “nuốt” lỗi rồi âm thầm trả kết quả rỗng.

**Khác biệt null với các quy tắc khác:** Một chuỗi khác null vẫn có thể sai định dạng, rỗng hoặc không có quyền sử dụng. `Objects.requireNonNull` không thay thế việc kiểm tra các invariant nghiệp vụ đó.

## 12. Chương trình Java 17+ chạy được: validate rồi lưu snapshot

Tạo tệp `BoundaryValidationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class BoundaryValidationDemo {

    static final class Settings {
        private final List<String> roles;
        private final Map<String, String> properties;

        Settings(List<String> inputRoles,
                 Map<String, String> inputProperties) {
            Objects.requireNonNull(inputRoles, "roles");
            Objects.requireNonNull(inputProperties, "properties");

            for (int i = 0; i < inputRoles.size(); i++) {
                Objects.requireNonNull(
                        inputRoles.get(i), "roles[" + i + "]");
            }

            for (var entry : inputProperties.entrySet()) {
                var key = Objects.requireNonNull(
                        entry.getKey(), "properties key");
                Objects.requireNonNull(entry.getValue(),
                        "properties[" + key + "]");
            }

            this.roles = List.copyOf(inputRoles);
            this.properties = Map.copyOf(inputProperties);
        }

        List<String> roles() {
            return roles;
        }

        Map<String, String> properties() {
            return properties;
        }
    }

    static void check(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + "=OK");
        } catch (NullPointerException e) {
            System.out.println(name + "="
                    + e.getClass().getSimpleName()
                    + ":" + e.getMessage());
        }
    }

    public static void main(String[] args) {
        var sourceRoles = new ArrayList<String>(
                List.of("reader", "writer"));
        var sourceProperties = new LinkedHashMap<String, String>();
        sourceProperties.put("mode", "safe");

        var settings = new Settings(sourceRoles, sourceProperties);
        sourceRoles.add("admin");
        sourceProperties.put("mode", "unsafe");

        System.out.println("roles=" + settings.roles());
        System.out.println("properties="
                + new TreeMap<>(settings.properties()));

        check("nullRoles", () -> new Settings(null, Map.of()));
        check("nullRole", () -> new Settings(
                Arrays.asList("reader", null), Map.of()));

        var badProperties = new HashMap<String, String>();
        badProperties.put("mode", null);
        check("nullValue", () -> new Settings(
                List.of("reader"), badProperties));

        var filtered = Arrays.asList("reader", null, "writer")
                .stream()
                .filter(Objects::nonNull)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("filtered=" + filtered);

        System.out.println("default="
                + Objects.requireNonNullElse(null, "guest"));
    }
}
```

Biên dịch/chạy:

```bash
javac BoundaryValidationDemo.java
java BoundaryValidationDemo
```

Kết quả:

```text
roles=[reader, writer]
properties={mode=safe}
nullRoles=NullPointerException:roles
nullRole=NullPointerException:roles[1]
nullValue=NullPointerException:properties[mode]
filtered=[reader, writer]
default=guest
```

**Đọc kết quả đúng theo hợp đồng:**

1. `Settings` kiểm tra cả hai collection đầu vào không null, từng phần tử role và từng key/value property.
2. `List.copyOf` và `Map.copyOf` tạo các snapshot không cho sửa; sau đó `sourceRoles.add("admin")` hoặc `sourceProperties.put("mode","unsafe")` không thay đổi cấu trúc dữ liệu mà `settings` giữ.
3. `TreeMap` được dùng **chỉ để in có thứ tự ổn định theo khóa**; `Map.copyOf` không bảo đảm iteration order.
4. Ba lỗi cố ý đều có **ngữ cảnh vị trí cụ thể** do `Objects.requireNonNull` tạo ra.
5. `filtered` minh họa chính sách bỏ null **chỉ khi có chủ ý** rồi tạo List không sửa được.
6. `Objects.requireNonNullElse(null, "guest")` trả giá trị mặc định `guest`; việc mặc định hóa phải được cho phép bởi nghiệp vụ.

Ví dụ sử dụng `var` trong phương thức và các API `copyOf`/`toUnmodifiableList` được giới thiệu từ Java 10; không cần API preview hoặc công nghệ đã ngừng hỗ trợ.

## 13. Thiết kế lớp có invariant không-null

Lý tưởng, một đối tượng domain sau khi được tạo thành công có thể hứa:

> `roles` và `properties` không null; mọi role, key và value không null; hai collection không cho sửa cấu trúc qua API; thay đổi các collection đầu vào sau đó không thay đổi các ánh xạ/phần tử đã lưu.

Hợp đồng này giúp giảm lượng kiểm tra lặp lại trong mã bên trong. Khi đọc `settings.roles()`, mã nghiệp vụ không cần đặt các nhánh xử lý null container hoặc null element ở mọi vòng lặp.

Tuy nhiên, phải đánh giá **giá trị phần tử**: `List.copyOf` và `Map.copyOf` **không deep copy** mọi object. Nếu list chứa `StringBuilder` hoặc map chứa đối tượng mutable, những đối tượng ấy vẫn có thể đổi trạng thái từ ngoài. Nếu yêu cầu snapshot bất biến sâu, cần dùng value object bất biến hoặc sao chép dữ liệu phần tử theo thiết kế.

Bên cạnh đó, việc copy từ một collection đang bị cập nhật đồng thời có thể đòi hỏi đồng bộ riêng. Kiểm tra null không làm cho đầu vào trở thành thread-safe.

## 14. Các lỗi thường gặp

| Tình huống | Vì sao sai/dễ gây lỗi? | Cách xử lý |
| --- | --- | --- |
| `List.copyOf(input)` khi `input == null` | Factory ném `NullPointerException`, không có thông điệp field cụ thể | `Objects.requireNonNull(input, "input")` ở ranh giới |
| Chỉ kiểm tra `input != null` rồi cho rằng phần tử luôn hợp lệ | Collection vẫn có thể chứa null | Duyệt phần tử và xác thực theo vị trí trước khi copy |
| `Map.copyOf(map)` khi có key/value null | Factory từ chối cả hai dạng null | Kiểm tra riêng key và value, nêu key/field bị lỗi |
| Tự động `filter(Objects::nonNull)` trên mọi danh sách | Có thể âm thầm bỏ một bản ghi bắt buộc | Chỉ lọc khi đó là quy tắc nghiệp vụ |
| Dùng `requireNonNullElse` với default không hợp lệ | Giá trị mặc định có thể che input sai | Chỉ dùng với trường tùy chọn và default được phê duyệt |
| Cho rằng `Collections.unmodifiableList` loại bỏ null | View không sửa không đồng nghĩa cấm null | Dựa vào contract của backing list |
| Cho rằng `List.copyOf` làm phần tử mutable thành immutable | Chỉ shallow copy tham chiếu | Chọn value object bất biến hoặc deep copy phù hợp |
| Dùng `map.get(key) == null` để kết luận key vắng trên nullable Map | Giá trị null và key không tồn tại cùng cho `null` | Kiểm tra thêm `containsKey` khi cần phân biệt |
| Validate nguồn rồi để luồng khác sửa nguồn trước `copyOf` | Bước validate/copy không nguyên tử | Dùng nguồn ổn định hoặc cùng cơ chế đồng bộ |
| Dựa vào `Map.copyOf` để giữ thứ tự `LinkedHashMap` | Factory không cam kết thứ tự duyệt | Chỉ sắp xếp khi xuất hoặc dùng cấu trúc có order contract |
| Nuốt `NullPointerException` và trả danh sách rỗng | Che lỗi dữ liệu thật | Báo lỗi có ngữ cảnh hoặc xử lý theo chính sách đã định |

## 15. Bài tập tự kiểm tra

### Bài 1: kết quả của ba factory

```java
var raw = java.util.Arrays.asList("A", null, "B");
// var a = List.copyOf(raw);
var b = new ArrayList<>(raw);
var c = Collections.unmodifiableList(raw);
```

**Đáp án:** `List.copyOf(raw)` ném `NullPointerException` vì có phần tử null. `b` chấp nhận null và tạo bản sao cấu trúc sửa được. `c` là view không cho sửa trực tiếp nhưng vẫn phản ánh nguồn, có thể chứa null. Đoạn minh họa cần import `java.util.List`, `ArrayList`, `Collections` hoặc tên đầy đủ.

### Bài 2: phân biệt key vắng và key null

```java
var map = new HashMap<String, String>();
map.put("mode", null);
boolean a = map.containsKey("mode");
boolean b = map.containsKey("other");
```

**Đáp án:** `a == true` và `b == false`, dù `map.get("mode")` và `map.get("other")` đều trả null. `Map.copyOf(map)` ném `NullPointerException` do value null.

### Bài 3: chọn reject/default/filter

Từ ba trường: `userId` bắt buộc, `locale` tùy chọn mặc định `"vi-VN"`, và danh sách `suggestions` cho phép bỏ các entry null, hãy nêu chính sách.

**Đáp án:** `userId` cần validate và reject null; `locale` có thể dùng `Objects.requireNonNullElse(rawLocale, "vi-VN")` nếu nghiệp vụ chấp thuận; `suggestions` có thể dùng `filter(Objects::nonNull)` rồi collect. Việc chọn ba chính sách khác nhau là có chủ ý theo **nghĩa của từng trường**.

### Bài 4: snapshot có được bảo đảm bất biến sâu không?

```java
var mutable = new StringBuilder("A");
var source = List.of(mutable);
var snapshot = List.copyOf(source);
mutable.append("B");
```

**Đáp án:** `snapshot.get(0).toString()` trả `"AB"` vì snapshot vẫn tham chiếu cùng `StringBuilder`. Không có thao tác sửa cấu trúc list; đây là hệ quả của shallow copy.

### Bài 5: lỗi xảy ra ở thời điểm nào?

Đã kiểm tra từng phần tử của một `ArrayList` đều khác null, nhưng một luồng khác có thể sửa list trước khi `List.copyOf` thực thi. Validation trước đó có bảo đảm copy thành công không?

**Đáp án:** Không. Nếu nguồn mutable bị truy cập/sửa đồng thời mà không phối hợp, có thể phát sinh race condition; validation và copy không phải một thao tác nguyên tử. Dùng nguồn ổn định hoặc đồng bộ cùng một quy tắc để tạo snapshot.

## 16. Checklist áp dụng tại boundary

Trước khi lưu dữ liệu vào một object với collection chỉ đọc, hãy xác nhận:

1. **Container có bắt buộc không-null không?** Nếu có, validate rõ tên.
2. **Phần tử List/Set có thể null không?** Nếu không, kiểm tra từng phần tử trước khi `copyOf`.
3. **Key và value Map có được phép null không?** Nếu không, xác thực cả hai; không chỉ kiểm tra `map != null`.
4. **Nếu null có ý nghĩa, chính sách là reject/default/filter hay biểu diễn trạng thái tùy chọn?** Phải thống nhất với nghiệp vụ.
5. **Error message có đủ vị trí để xử lý không?** Ưu tiên `field[index]`, `field[key]` và mã lỗi có cấu trúc khi cần.
6. **Dữ liệu đầu vào có ổn định trong lúc validate và copy không?** Nếu không, cần cơ chế đồng bộ hoặc điểm lấy snapshot thích hợp.
7. **Kết quả cần giữ thứ tự không?** `List.copyOf` giữ thứ tự duyệt, trong khi `Set.copyOf`/`Map.copyOf` không hứa iteration order.
8. **Các object phần tử có mutable không?** Quyết định có cần immutable value/deep copy hay không.
9. **Có đang dùng unmodifiable view rồi tưởng nó là snapshot không?** Phân biệt rõ `Collections.unmodifiable*` với `copyOf`.
10. **Có đang bỏ qua lỗi bằng cách trả rỗng không?** Việc đó chỉ đúng khi được nêu rõ trong hợp đồng API.

## Kết luận

**Kiểm tra `null` tại ranh giới dữ liệu là bước thiết kế hợp đồng, không chỉ là xử lý ngoại lệ.** Trong Java 10+, `List.copyOf`, `Set.copyOf` và `Map.copyOf` tạo collection không sửa được và **từ chối dữ liệu null** theo quy tắc tương ứng. `Objects.requireNonNull` giúp báo lỗi sớm với ngữ cảnh rõ ràng; `Objects.requireNonNullElse`, `Optional.ofNullable` hoặc `filter(Objects::nonNull)` chỉ nên sử dụng khi chính sách nghiệp vụ cho phép.

Kiểm tra container, phần tử, Map key/value và độ ổn định của nguồn trước khi tạo snapshot. Khi thành công, đối tượng bên trong có thể dựa trên invariant rõ ràng, giảm nhánh xử lý null lặp lại và tránh thất thoát dữ liệu do việc mặc định hóa/lọc quá tay.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `Objects.requireNonNull` và `requireNonNullElse`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html): kiểm tra tham số bắt buộc khác null và mặc định hóa có kiểm soát.
- [Java SE 26 — `List.copyOf`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): không nhận container hay phần tử null, trả list không sửa được.
- [Java SE 26 — `Set.copyOf`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): không nhận null, xử lý phần tử trùng theo hợp đồng Set.
- [Java SE 26 — `Map.copyOf`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): không nhận null key/value, giữ snapshot các ánh xạ.
- [Java SE 26 — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view của backing list, không tự cấm null.
- [Java SE 26 — `Collectors.toUnmodifiableList`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): collector Java 10 tạo List không sửa và từ chối null.
- [Java SE 26 — `Optional.ofNullable`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html#ofNullable(T)): biểu diễn sự vắng mặt có chủ ý.
