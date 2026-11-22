# Java 11 — Optional.isEmpty và phân biệt vắng mặt với null

**Chủ đề:** Java 11 → Tiện ích dữ liệu. Bài học tập trung vào `java.util.Optional<T>`, đặc biệt là phương thức `isEmpty()` có từ **Java 11**, và cách phân biệt đúng các tình huống “không có kết quả”, “tham chiếu Java bằng `null`”, “khóa dữ liệu không tồn tại”, “khóa tồn tại với giá trị null”. Những nguyên tắc này vẫn được áp dụng trong thiết kế API, xử lý JSON, cập nhật từng phần và kiểm thử ứng dụng hiện nay.

**Mục tiêu:** Sau bài này, người học có thể kiểm tra Optional rỗng bằng `isEmpty()`, chọn đúng `of`/`ofNullable`/`empty`, xử lý thiếu giá trị mà không gọi `get()` liều lĩnh, không nhầm `null` với `Optional.empty()`, và bảo toàn đủ ba trạng thái khi nghiệp vụ yêu cầu.

## 1. Cần phân biệt ít nhất ba khái niệm

### 1.1. `null` là gì?

Trong Java, `null` là một giá trị đặc biệt của **kiểu tham chiếu**: biến không tham chiếu tới một object. Gọi phương thức qua biến `null` thường gây `NullPointerException`. Ví dụ:

~~~java
String name = null;
// name.length(); // Nếu mở dòng này sẽ ném NullPointerException.
~~~

`null` tự nó **không cho biết vì sao không có object**: người dùng chưa nhập, dữ liệu chưa tải, giá trị bị xóa, lỗi lập trình hay giá trị hợp lệ trong một định dạng bên ngoài. Ý nghĩa phải đến từ **hợp đồng dữ liệu**.

### 1.2. `Optional<T>` biểu diễn điều gì?

`Optional<T>` là container **có hoặc không có một giá trị khác null**:

- **Present:** có giá trị `T` không null.
- **Empty:** không chứa giá trị.

Nó chỉ có **hai trạng thái**, không mang sẵn nguyên nhân thiếu dữ liệu. Một object `Optional` hợp lệ tự nó không nên là `null`; dùng `Optional<String> x = null;` làm mất ý nghĩa thiết kế.

~~~java
Optional<String> found = Optional.of("Linh");  // Có giá trị.
Optional<String> absent = Optional.empty();     // Không có giá trị.
Optional<String> fromNull = Optional.ofNullable(null); // Empty.
~~~

Nếu `Optional.of(null)` thì ném `NullPointerException` ngay tại chỗ tạo. `Optional.ofNullable(value)` chọn present khi `value != null`, và empty khi `value == null`. Vì vậy `Optional.ofNullable(null)` **không giữ lại một trạng thái “present nhưng bên trong là null”**.

### 1.3. “Vắng mặt” và “null được gửi tường minh” có thể khác nhau

Xét payload cập nhật người dùng:

~~~json
{}
~~~

~~~json
{"nickname": null}
~~~

~~~json
{"nickname": "Linh"}
~~~

Nếu API quy định: thiếu `nickname` = **giữ nguyên**, gửi `null` = **xóa biệt danh**, gửi chuỗi = **đặt biệt danh mới**, thì đây là **ba trạng thái nghiệp vụ**. `Optional<String>` đơn lẻ không thể biểu diễn đủ ba trạng thái, vì `ofNullable(null)` trùng `empty()`. Không nên dùng Optional để vô tình gộp “không muốn cập nhật” và “muốn xóa”.

Bảng phân biệt:

| Tình huống | Ý nghĩa có thể có | `Optional.ofNullable(value)` |
| --- | --- | --- |
| Không tìm thấy bản ghi | Không có kết quả tìm kiếm | Empty — phù hợp. |
| Trường Java có giá trị `null` | Chưa biết/không có dữ liệu, theo hợp đồng | Empty — mất nguyên nhân. |
| Khóa không xuất hiện trong payload PATCH | Không gửi yêu cầu thay đổi trường | Empty nếu chỉ đọc `get`. |
| Khóa xuất hiện với JSON `null` | Có thể yêu cầu xóa giá trị | Cũng empty nếu chỉ lấy Java `null`. |
| Chuỗi rỗng `""` | **Có** chuỗi, nhưng độ dài bằng 0 | Present với chuỗi rỗng. |
| Chuỗi chỉ có dấu cách | **Có** chuỗi; có hợp lệ hay không là quy tắc riêng | Present với chuỗi đó. |
| Danh sách rỗng | **Có** object danh sách, kích thước 0 | Present với danh sách rỗng. |
| Số 0 hoặc boolean `false` | Giá trị hợp lệ của miền dữ liệu | Present nếu dùng kiểu đối tượng phù hợp. |

**Quy tắc:** Optional mô tả **có/không có kết quả**. Việc phân biệt **thiếu thuộc tính / thuộc tính có giá trị null / thuộc tính có giá trị thật** thuộc về schema, parser, DTO và hợp đồng nghiệp vụ.

## 2. `Optional.isEmpty()` — API được bổ sung ở Java 11

~~~java
Optional<String> nickname = Optional.empty();

System.out.println(nickname.isEmpty());   // true
System.out.println(nickname.isPresent()); // false
~~~

- `isEmpty()` trả `true` khi Optional không có giá trị. Phương thức **Since: 11**.
- `isPresent()` trả `true` khi Optional có giá trị, tồn tại từ trước Java 11.
- Với cùng một object Optional hợp lệ, `x.isEmpty() == !x.isPresent()` luôn đúng.
- `OptionalInt`, `OptionalLong` và `OptionalDouble` cũng có `isEmpty()` từ Java 11, áp dụng cho giá trị nguyên thủy tương ứng.
- Khi **biến Optional tự nó là null**, gọi `isEmpty()` vẫn ném `NullPointerException`; `isEmpty()` không phải phép “kiểm tra null mọi thứ”.

Ví dụ ngắn về nhánh xử lý:

~~~java
Optional<String> result = findDisplayName(userId);
if (result.isEmpty()) {
    return "Không tìm thấy người dùng";
}
return result.orElseThrow();
~~~

Đây là **đoạn minh họa**: giả sử `findDisplayName` và `userId` đã được định nghĩa, return type của method bao quanh là `String`. Sau nhánh `isEmpty()` trả về, `orElseThrow()` lấy giá trị present; cách này hữu ích khi cần early return. Nếu không cần chia nhánh, có thể viết ngắn hơn `return findDisplayName(userId).orElse("Không tìm thấy người dùng");`, tùy hợp đồng.

**Không cần viết `if (!optional.isPresent())` trên Java 11** nếu `isEmpty()` diễn đạt rõ ý định hơn. Nhưng `isPresent()` vẫn hoàn toàn hợp lệ và đôi khi rõ hơn khi kiểm tra nhánh có giá trị; nó không bị loại bỏ hay deprecated.

## 3. Tạo Optional đúng cách và hiểu hợp đồng

| API Java 11 | Khi nào dùng | Nếu input null |
| --- | --- | --- |
| `Optional.empty()` | Chủ động báo không có kết quả | Không nhận input. |
| `Optional.of(value)` | Có hợp đồng bảo đảm `value` không null | Ném `NullPointerException` để lộ vi phạm hợp đồng. |
| `Optional.ofNullable(value)` | Dữ liệu nguồn có thể null và muốn quy đổi thành “không có kết quả” | Trả `Optional.empty()`. |

Ví dụ repository hoặc lookup:

~~~java
public Optional<String> findNickname(long userId) {
    String nickname = lookupNullableNickname(userId); // API nguồn có thể trả null.
    return Optional.ofNullable(nickname);
}
~~~

Đây là đoạn minh họa, `lookupNullableNickname` là API cần được cung cấp. Khi sử dụng `ofNullable`, người thiết kế **chủ động quyết định rằng null và không tìm thấy có cùng ý nghĩa** trong hợp đồng mới. Nếu null là dữ liệu nghiệp vụ hợp lệ cần phân biệt, phép chuyển này làm mất thông tin và phải đổi kiểu trả về hoặc hợp đồng.

**Không trả về `null` từ method khai báo `Optional<T>`.** Trường hợp không có dữ liệu trả `Optional.empty()`. Nếu giá trị bắt buộc và thiếu được xem là lỗi, hợp đồng có thể yêu cầu ném exception cụ thể thay vì trả Optional.

## 4. Lấy và biến đổi giá trị mà không che giấu lỗi

### 4.1. `orElse`, `orElseGet`, `orElseThrow`

~~~java
String display = nickname.orElse("Khách");
String lazy = nickname.orElseGet(() -> loadDefaultName());
String required = nickname.orElseThrow(
    () -> new IllegalArgumentException("Thiếu biệt danh"));
~~~

Đây là **đoạn minh họa**, giả sử `nickname` là `Optional<String>` và `loadDefaultName` trả về `String`.

- `orElse(value)` nhận sẵn giá trị thay thế. **Biểu thức đối số được đánh giá trước** khi gọi phương thức, kể cả Optional đang present. Do đó `optional.orElse(expensiveCall())` có thể vẫn chạy `expensiveCall()`.
- `orElseGet(supplier)` chỉ gọi supplier khi Optional rỗng; nên dùng nếu fallback tốn I/O, tính toán hoặc có side effect.
- `orElseThrow(supplier)` ném exception theo nghiệp vụ khi không có dữ liệu. Dạng `orElseThrow()` không tham số cũng có trên JDK 11 và ném `NoSuchElementException` khi empty.
- `get()` vẫn tồn tại nhưng ném `NoSuchElementException` khi rỗng và dễ bị gọi thiếu kiểm tra. **Ưu tiên `orElseThrow()` khi muốn lấy giá trị bắt buộc**, hoặc dùng `map`/`ifPresent` khi có thể xử lý theo luồng.

**Không biến mọi Empty thành giá trị giả** như `"N/A"` hoặc `0` nếu nghiệp vụ cần phân biệt “không tìm thấy”. Fallback chỉ hợp lệ khi hợp đồng cho phép giá trị mặc định.

### 4.2. `map`, `filter`, `flatMap`

~~~java
Optional<String> cleaned = Optional.ofNullable(rawName)
    .map(String::strip)
    .filter(name -> !name.isBlank());
~~~

Đây là đoạn minh họa với `rawName` có kiểu `String`. Ở đây, việc coi null, rỗng và chỉ có khoảng trắng là “không có tên hợp lệ” là **quyết định validation cụ thể**, không phải định nghĩa mặc định của Optional. `strip()` và `isBlank()` đều có trên Java 11.

- `map(f)` chỉ gọi `f` nếu có giá trị; trả Optional của kết quả. Nếu mapper trả `null`, kết quả trở thành **Empty** (theo quy tắc `ofNullable`), cần lưu ý nguy cơ mất thông tin.
- `filter(predicate)` giữ giá trị khi predicate đúng; nếu sai sẽ trả Empty.
- `flatMap(f)` dùng khi mapper **đã trả Optional**, tránh kiểu `Optional<Optional<T>>`; mapper của `flatMap` **không được trả null**, nếu trả null sẽ ném `NullPointerException`.
- `ifPresent(action)` thực thi hành động khi present. `ifPresentOrElse(action, emptyAction)` (có trước Java 11) thực thi một trong hai nhánh khi cần side effect.
- `or(supplier)` chọn một **Optional thay thế** khi rỗng; supplier phải trả Optional khác null.
- `stream()` biến một Optional present thành stream một phần tử, empty thành stream rỗng; hữu ích với `flatMap(Optional::stream)` trong xử lý collection. Tất cả các API này có trên JDK 11.

Đối với chuỗi xử lý nhiều bước, dùng `map`/`flatMap` để diễn đạt biến đổi thay vì liên tục `isPresent()` rồi `get()`. Tuy nhiên, khi kiểm soát nhiều trạng thái/side effects, một khối `if` rõ ràng vẫn có thể dễ đọc hơn.

## 5. Ví dụ Java 11 hoàn chỉnh: Optional rỗng so với khóa có null

Ví dụ độc lập sau **không cần Internet, Maven hoặc thư viện bên thứ ba**, có thể biên dịch với JDK 11. Nó minh họa hai miền khác nhau:

1. Method `findNickname` trả Optional vì bản ghi có thể không tồn tại.
2. `HashMap` lưu ba trường hợp **không có khóa / có khóa với null / có khóa với chuỗi**. `Optional.ofNullable(map.get(key))` sẽ làm mất khác biệt giữa hai trường hợp đầu.

Lưu tệp đúng tên **`OptionalPresenceDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public final class OptionalPresenceDemo {
    private OptionalPresenceDemo() {
    }

    static Optional<String> findNickname(long userId) {
        if (userId == 42L) {
            return Optional.of("Linh");
        }
        return Optional.empty();
    }

    static String describeField(Map<String, String> fields, String key) {
        if (!fields.containsKey(key)) {
            return "ABSENT";
        }
        String value = fields.get(key);
        if (value == null) {
            return "EXPLICIT_NULL";
        }
        return "VALUE(" + value + ")";
    }

    public static void main(String[] args) {
        Optional<String> found = findNickname(42L);
        Optional<String> missing = findNickname(7L);

        System.out.println("found.isEmpty=" + found.isEmpty());
        System.out.println("missing.isEmpty=" + missing.isEmpty());
        System.out.println("found=" +
                found.map(String::toUpperCase).orElse("UNKNOWN"));
        System.out.println("fallback=" +
                missing.orElseGet(() -> "Guest"));

        Map<String, String> fields = new HashMap<>();
        fields.put("nickname", "Linh");
        fields.put("middleName", null);

        System.out.println("nickname=" +
                describeField(fields, "nickname"));
        System.out.println("middleName=" +
                describeField(fields, "middleName"));
        System.out.println("unknown=" +
                describeField(fields, "unknown"));
        System.out.println("collapsed=" +
                Optional.ofNullable(fields.get("middleName")).isEmpty());
    }
}
~~~

Biên dịch, chạy:

~~~bash
javac -encoding UTF-8 OptionalPresenceDemo.java
java OptionalPresenceDemo
~~~

**Stdout chính xác:**

~~~text
found.isEmpty=false
missing.isEmpty=true
found=LINH
fallback=Guest
nickname=VALUE(Linh)
middleName=EXPLICIT_NULL
unknown=ABSENT
collapsed=true
~~~

**Giải thích từng bước:**

- `findNickname(42L)` trả Optional present; `findNickname(7L)` trả Empty. Vì vậy `isEmpty()` lần lượt là `false` và `true`.
- `map(String::toUpperCase)` biến “Linh” thành “LINH”; `orElse("UNKNOWN")` không thay thế dữ liệu vì giá trị đang present.
- `orElseGet(() -> "Guest")` cấp fallback vì nickname của người dùng 7 không có.
- `HashMap` cho phép giá trị null; `containsKey("middleName")` vẫn là `true` dù `get("middleName") == null`. Với khóa `"unknown"`, `containsKey` là `false`.
- `Optional.ofNullable(fields.get("middleName"))` trở thành Empty. Nếu dùng cách này để xử lý PATCH thì sẽ không biết người dùng đã gửi null tường minh hay không.
- `Map.of(...)` hoặc các map implementation **không cho phép null** sẽ không phù hợp khi cần minh họa trạng thái “có khóa và giá trị null”. Không giả định mọi `Map` hỗ trợ null.

Đoạn `describeField` đọc `containsKey` rồi `get` trong một `HashMap` không bị chỉnh sửa đồng thời. Nếu dữ liệu có nhiều thread sửa trong lúc đọc, cần chiến lược snapshot/đồng bộ hoặc cấu trúc dữ liệu phù hợp; hai lời gọi độc lập không tự tạo giao dịch nguyên tử.

## 6. Thiết kế API: dùng Optional ở ranh giới đúng

### 6.1. Return type là vị trí sử dụng điển hình

Các method như `findUser(id)`, `findConfig(key)`, `findFirst()` thường có kết quả tùy có/tùy không; trả `Optional<User>` làm sự vắng mặt rõ ràng:

~~~java
Optional<User> findUserById(long id);
~~~

Đây là **chữ ký minh họa**, giả sử class `User` có trong ứng dụng. Caller có thể:

~~~java
User user = repository.findUserById(id)
    .orElseThrow(() -> new UserNotFoundException(id));
~~~

Đây là đoạn minh họa, `repository`, `id` và exception riêng được định nghĩa bởi ứng dụng. Có thể dùng fallback hoặc trả 404 ở tầng HTTP, tùy hợp đồng. **Không** biến `Optional.empty()` thành “API bị lỗi mạng” hoặc “DB hỏng”: những lỗi không phải vắng mặt dữ liệu thường phải được biểu diễn qua exception/result type có nhánh lỗi rõ ràng.

### 6.2. Parameter và field: cần cân nhắc, không ép mọi thứ thành Optional

Với tham số bắt buộc, sử dụng kiểu `T` và kiểm tra `Objects.requireNonNull(value, "value")` nếu null là lỗi gọi API. Nếu tham số có giá trị mặc định, dùng overload, options object hoặc hợp đồng nullable rõ ràng; tránh bắt caller phải viết `Optional.of(value)` cho mọi tham số chỉ vì một số trường hợp có thể thiếu.

Đối với các field trong entity/DTO, việc nhét `Optional<T>` vào mọi field có thể khiến mapper, JSON serializer, ORM và validation phức tạp. Tài liệu JDK mô tả Optional **chủ yếu dành cho method return type**. Hãy để framework/DTO biểu đạt nullability đúng theo schema; chỉ dùng Optional làm field/parameter khi hợp đồng và hệ sinh thái thực sự có lý do hỗ trợ.

Cần nhớ `Optional` là **value-based class**. Không dùng `==` để so sánh identity, không khóa đồng bộ trên đối tượng Optional và không dựa vào việc `Optional.empty()` là singleton. So sánh giá trị/trạng thái qua `equals`, `isEmpty`, `isPresent`; đồng bộ trên lock được thiết kế riêng. `Optional` cũng không được coi là cơ chế tự động serialize object JSON.

### 6.3. Empty không thay thế được ngoại lệ và thông tin lỗi

| Tình huống | Kiểu thể hiện thường hợp lý |
| --- | --- |
| Tìm ID hợp lệ nhưng không có bản ghi | `Optional<User>` Empty. |
| ID âm hoặc định dạng input sai | Validation error/exception rõ ràng. |
| Database bị timeout | Exception hoặc result type mang trạng thái lỗi. |
| Tìm thấy bản ghi nhưng trường phụ có thể null | Theo schema của field/DTO; không tự đồng nhất với “không có bản ghi”. |
| API gửi yêu cầu xóa một field | Trạng thái cập nhật tường minh, không chỉ Optional rỗng. |

Nguyên tắc này giúp observability và xử lý lỗi đúng: “không có kết quả” là một nhánh nghiệp vụ bình thường; “không truy cập được nguồn dữ liệu” cần được báo, ghi log và có thể retry riêng.

## 7. Xử lý payload PATCH hoặc cấu hình có ba trạng thái

Giả sử API nhận partial update:

- **ABSENT:** không có khóa → giữ nguyên dữ liệu cũ.
- **EXPLICIT_NULL:** có khóa với null → xóa/reset trường.
- **VALUE:** có khóa với giá trị hợp lệ → ghi giá trị mới.

Với một `Map<String, String>` cho phép null, phép đọc an toàn trong cùng snapshot là:

~~~java
if (!payload.containsKey("nickname")) {
    // Không thay đổi biệt danh.
} else {
    String newName = payload.get("nickname");
    if (newName == null) {
        // Xóa biệt danh nếu hợp đồng API cho phép.
    } else {
        // Validate và cập nhật thành newName.
    }
}
~~~

Đây là đoạn minh họa: `payload` là map có thể lưu null, mã trong comment biểu thị hành động nghiệp vụ; nó không phải một chương trình độc lập. Việc gửi null có nghĩa là “xóa” **chỉ khi hợp đồng API quy định như vậy**. Một số hệ thống dùng null để báo lỗi, không cho xóa hoặc có semantics khác.

**Nếu chuyển thành kiểu domain, đặt tên rõ ba nhánh**. Ví dụ với Java 11 có thể dùng enum và class thay cho kiểu dữ liệu nhiều tầng khó hiểu:

~~~java
enum ChangeKind { UNCHANGED, CLEAR, SET }

final class FieldChange<T> {
    final ChangeKind kind;
    final T value;

    private FieldChange(ChangeKind kind, T value) {
        this.kind = kind;
        this.value = value;
    }

    static <T> FieldChange<T> unchanged() {
        return new FieldChange<>(ChangeKind.UNCHANGED, null);
    }

    static <T> FieldChange<T> clear() {
        return new FieldChange<>(ChangeKind.CLEAR, null);
    }

    static <T> FieldChange<T> set(T value) {
        return new FieldChange<>(
            ChangeKind.SET, java.util.Objects.requireNonNull(value));
    }
}
~~~

Đây là **đoạn định nghĩa kiểu minh họa**; để dùng ở production, bổ sung validation, getter/method xử lý và giới hạn truy cập phù hợp. Điểm thiết kế là **`kind` nói rõ ý nghĩa**; riêng `value == null` không đủ quyết định. Nếu schema chỉ có hai trạng thái (có dữ liệu hoặc không tìm thấy), kiểu ba nhánh này là thừa, khi đó Optional sẽ gọn hơn.

**Với JSON:** Java SE 11 không tích hợp parser JSON. Thư viện được duy trì như Jackson giúp kiểm tra field **có mặt hay không** và field có JSON null hay không theo API của thư viện; đừng parse JSON bằng regex. Đảm bảo parser/DTO vẫn giữ được sự khác biệt nếu endpoint cần PATCH semantics. Chú ý: `Map.getOrDefault(key, default)` dùng fallback khi **thiếu key**; nếu key hiện diện và map chứa null, nó trả null, vì vậy cũng cần hiểu hợp đồng từng phương thức.

## 8. Kết hợp Optional với Stream và dữ liệu thực tế

### 8.1. Lọc kết quả tìm kiếm vắng mặt

Giả sử có danh sách user ID và phương thức `findNickname` như chương trình hoàn chỉnh ở trên:

~~~java
List<String> names = ids.stream()
    .map(OptionalPresenceDemo::findNickname)
    .flatMap(Optional::stream)
    .collect(Collectors.toList());
~~~

Đây là đoạn minh họa với `ids` là `List<Long>`, import `java.util.List`, `java.util.stream.Collectors` và `java.util.Optional`. `Optional.stream()` trả một phần tử khi present, không phần tử khi empty. Trên JDK 11 dùng `Collectors.toList()` hoặc `Collectors.toUnmodifiableList()` (khi cần immutable); **không dùng `Stream.toList()` nếu đang biên dịch trực tiếp bằng JDK 11** vì phương thức này ra đời sau Java 11.

### 8.2. Tránh mất thông tin do mapper trả null

~~~java
Optional<String> name =
    Optional.of("user").map(value -> (String) null);

System.out.println(name.isEmpty()); // true
~~~

Đây là chương trình minh họa nhỏ khi đặt trong method và import Optional. `map` chọn Empty nếu kết quả mapping là null. Nếu null có nghĩa đặc biệt (ví dụ “đã tìm thấy nhưng bị xóa”), **đừng nối `map` rồi coi Empty là “không tìm thấy”**; hãy chuẩn hóa hợp đồng trước khi xây pipeline.

### 8.3. Giá trị rỗng khác Optional rỗng

~~~java
System.out.println(Optional.of("").isEmpty());          // false
System.out.println(Optional.of(" ").isEmpty());         // false
System.out.println(Optional.of(java.util.List.of()).isEmpty()); // false
~~~

Một chuỗi blank, danh sách rỗng hay giá trị bằng 0 không tự biến Optional thành Empty. Nếu muốn bỏ dữ liệu trắng, phải áp dụng `filter`/validation có chủ đích. Không dùng `Optional` để che giấu các quy tắc hợp lệ của miền dữ liệu.

### 8.4. Optional của primitive

Khi tìm một số có thể vắng mặt mà không cần boxing, Java cung cấp `OptionalInt`, `OptionalLong`, `OptionalDouble`. Chúng có `isEmpty()` trên Java 11:

~~~java
OptionalInt count = OptionalInt.empty();
System.out.println(count.isEmpty()); // true
System.out.println(count.orElse(0));  // 0
~~~

Đây là đoạn minh họa cần import `java.util.OptionalInt`. **Lưu ý:** `orElse(0)` chỉ đúng nếu fallback 0 được hợp đồng cho phép; trong nhiều nghiệp vụ “không đo được” khác “đo được 0”.

## 9. Kiểm thử các tình huống vắng mặt và null

Unit test cần thể hiện rõ **hợp đồng**, đặc biệt với dữ liệu có ba trạng thái. Tránh test chỉ theo “không ném NullPointerException” vì có thể code đã vô tình gộp hai ý nghĩa.

| Case | Input | Kết quả cần kiểm |
| --- | --- | --- |
| Có kết quả | `findNickname(42L)` | Present; `isEmpty() == false`; giá trị “Linh”. |
| Không có kết quả | `findNickname(7L)` | Empty; `isEmpty() == true`. |
| Tạo từ null | `Optional.ofNullable(null)` | Empty. |
| Tạo bắt buộc từ null | `Optional.of(null)` | Ném `NullPointerException`. |
| Khóa tồn tại với null | `Map.put("name", null)` | `containsKey("name") == true` nhưng `get("name") == null`. |
| Khóa chưa tồn tại | Không `put` khóa đó | `containsKey("name") == false` và `get("name") == null` (với HashMap). |
| Chuỗi rỗng | `Optional.of("")` | Present, không phải Empty. |
| Fallback tốn tài nguyên | Present + `orElseGet` | Supplier không bị gọi. |
| Mapper trả null | `map(x -> null)` | Empty; không giữ “present-null”. |

Nếu dự án đã dùng **JUnit Jupiter 5.x bản tương thích JDK 11**, có thể viết các kiểm thử độc lập sau (đoạn test cần dependency JUnit 5 và `OptionalPresenceDemo.java` cùng package):

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OptionalPresenceDemoTest {
    @Test
    void optionalEmptyMeansNoResult() {
        assertTrue(OptionalPresenceDemo.findNickname(7L).isEmpty());
        assertFalse(OptionalPresenceDemo.findNickname(42L).isEmpty());
        assertEquals("Linh",
            OptionalPresenceDemo.findNickname(42L).orElseThrow());
    }

    @Test
    void mapKeepsAbsentAndExplicitNullDistinct() {
        Map<String, String> data = new HashMap<>();
        data.put("nickname", null);
        assertEquals("ABSENT",
            OptionalPresenceDemo.describeField(data, "unknown"));
        assertEquals("EXPLICIT_NULL",
            OptionalPresenceDemo.describeField(data, "nickname"));
        assertTrue(Optional.ofNullable(data.get("nickname")).isEmpty());
    }

    @Test
    void emptyStringIsAValue() {
        assertFalse(Optional.of("").isEmpty());
        assertThrows(NullPointerException.class,
            () -> Optional.of(null));
    }
}
~~~

Các phương thức mẫu trong `OptionalPresenceDemo` được khai báo package-private (`static` không có `private`), nên test có thể gọi khi đặt cùng package mặc định như bài demo. Với dự án thật, nên đặt trong package rõ ràng và để test cùng package hoặc thông qua public API; không thêm access modifier chỉ để test tùy tiện. Cấu hình build tool để Surefire hoặc Gradle test task chạy JUnit Jupiter qua JUnit Platform.

Đối với API PATCH thực tế, bổ sung test kiểm tra ba hậu quả khác nhau: **giữ nguyên** giá trị khi khóa thiếu, **xóa** khi null tường minh (nếu được phép), **cập nhật** khi có giá trị, và một test validation khi kiểu/value sai. Đó là bảo vệ quan trọng hơn việc chỉ kiểm tra Optional không null.

## 10. Những lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `Optional<String> result = null;` | Gọi `isEmpty` vẫn gây NPE, vi phạm hợp đồng Optional. | Luôn trả object `Optional.of/empty/ofNullable`. |
| `Optional.of(valueNullable)` | Ném NPE nếu value null. | Dùng `ofNullable` **chỉ khi** null và vắng mặt cùng ý nghĩa; nếu không, giữ kiểu trạng thái rõ ràng. |
| `optional.get()` không kiểm tra | Empty gây `NoSuchElementException`. | Dùng `orElseThrow`, `orElseGet`, `map` hoặc nhánh có kiểm tra. |
| `optional.orElse(expensiveCall())` | `expensiveCall()` vẫn được đánh giá dù present. | Dùng `orElseGet(() -> expensiveCall())` nếu cần lazy fallback. |
| Gộp `payload.get(key) == null` thành “khóa thiếu” | Map có thể chứa mapping với null. | Kiểm tra `containsKey` khi cần phân biệt. |
| Dùng `Optional.ofNullable(payload.get(key))` cho PATCH ba trạng thái | Empty xóa đi sự khác biệt ABSENT và EXPLICIT_NULL. | Dùng presence flag/enum/result type rõ trạng thái. |
| Coi `""`, `false`, `0` hoặc collection rỗng là absence | Đây là các giá trị hợp lệ của kiểu dữ liệu. | Áp dụng validation theo miền dữ liệu, không dựa vào isEmpty. |
| Dùng `==` với hai Optional | Optional là value-based, không nên kiểm tra identity. | So sánh qua `equals` hoặc kiểm tra state. |
| Mọi lỗi lookup đều chuyển `Optional.empty()` | Che giấu timeout, lỗi truy cập và bug. | Chỉ Empty cho trường hợp hợp đồng định nghĩa “không tìm thấy”; lỗi thật phải đi nhánh lỗi. |
| Dùng `Stream.toList()` trong bài Java 11 | Không có API đó trên JDK 11. | Dùng `collect(Collectors.toList())` hoặc `toUnmodifiableList()`. |

## 11. Checklist lựa chọn thiết kế

Khi chuẩn bị dùng Optional, tự trả lời:

1. API đang diễn đạt **kết quả có thể không tồn tại**, hay đang xử lý một trường có **giá trị null hợp lệ**?
2. Có cần phân biệt **không có trường**, **có trường với null**, **có trường với giá trị** không? Nếu có, hãy giữ sự phân biệt ngay từ parser/DTO.
3. Nếu thiếu dữ liệu, có thể dùng fallback không, hay phải trả lỗi/404? Nếu fallback tốn chi phí, dùng `orElseGet`.
4. `Optional.empty()` có đang vô tình che giấu lỗi mạng, exception hoặc dữ liệu không hợp lệ không?
5. Dữ liệu blank, 0, false, danh sách rỗng có phải giá trị hợp lệ? Nếu muốn loại, quy tắc validation đã được mô tả và test chưa?
6. Code có giữ tương thích Java 11 không? `isEmpty()` dùng được; chọn những API khác theo đúng phiên bản.
7. Unit test đã chứng minh cả nhánh present, empty và **present-null của nguồn dữ liệu** khi nghiệp vụ yêu cầu chưa?

## 12. Bài tự luyện

**Bài 1 — dự đoán:** với `Optional.of(" ")`, dự đoán `isEmpty()` trước và sau `map(String::strip).filter(s -> !s.isBlank())`. Giải thích vì sao kết quả thay đổi do validation, không phải bản thân Optional.

**Bài 2 — kiểm tra lỗi:** thay `Optional.ofNullable(null)` bằng `Optional.of(null)`, quan sát ngoại lệ. Giải thích trường hợp nào NPE sớm là đúng vì input bắt buộc.

**Bài 3 — dữ liệu PATCH:** chạy chương trình mẫu, sau đó thay `fields.get("middleName")` bằng `fields.get("unknown")` trong dòng `collapsed`. Cả hai đều Empty, nhưng kết quả `describeField` khác nhau. Thiết kế một `FieldChange` có ba trạng thái và viết test để ngăn lỗi xóa nhầm dữ liệu.

**Bài 4 — lazy fallback:** viết supplier tăng counter; so sánh số lần được gọi giữa `orElse(expensiveCall())` và `orElseGet(() -> expensiveCall())` khi Optional present.

**Bài 5 — API:** thiết kế `Optional<User> findUser(long id)` và nhánh xử lý khi user không tồn tại; chỉ ra cách báo lỗi khác khi database timeout. Giải thích vì sao Empty không được dùng cho mọi exception.

**Nguồn API chính thức, áp dụng lâu dài:** [Optional trong Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Optional.html), [Map trong Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Map.html), [Optional trong Java SE hiện hành](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html).

**Ghi nhớ:** `Optional.isEmpty()` là phép hỏi “Optional này có thiếu **giá trị khác null** hay không?”. Nó **không** thể thay thế phép phân biệt “field không được gửi” và “field được gửi với null”. Chọn Optional cho kết quả tùy có; dùng schema, presence indicator hoặc kiểu domain có trạng thái rõ ràng khi ngữ nghĩa đòi hỏi nhiều hơn hai trạng thái.