# Optional trong kiểu trả về và thiết kế API Java

`Optional<T>` là kiểu giá trị có từ Java 8 và tiếp tục được hỗ trợ trong Java hiện hành. Nó biểu diễn **có thể có một kết quả khác null**, hoặc **không có kết quả**. Theo ghi chú API chính thức, `Optional` **chủ yếu được thiết kế làm kiểu trả về của phương thức khi “không có kết quả” là tình huống cần biểu diễn rõ**, đặc biệt lúc trả `null` có thể gây lỗi.

Bài này tập trung vào **phạm vi nên dùng Optional trong chữ ký phương thức và thiết kế API**, không chỉ cú pháp `Optional.of(...)`. Khi thiết kế đúng, người gọi nhìn chữ ký có thể biết cần xử lý sự vắng mặt; khi thiết kế sai, ta lại tạo ra những tầng null và Optional rối rắm hơn ban đầu.

## 1. Khi nào nên trả Optional?

Ví dụ một repository có phương thức tìm người dùng theo ID:

~~~java
Optional<User> findById(String id);
~~~

Đây là **chữ ký minh họa**, giả sử đã có lớp `User` và import `java.util.Optional`. Ý nghĩa hợp đồng:

- **Có kết quả:** trả `Optional.of(user)` với `user` khác null.
- **Không tìm thấy:** trả `Optional.empty()`.
- **Không bao giờ trả null cho chính biến Optional:** `return null;` là vi phạm hợp đồng API, khiến caller có thể lại gặp `NullPointerException` khi dùng `map` hoặc `isPresent`.
- **Input không hợp lệ hoặc lỗi hệ thống:** xử lý theo chính sách lỗi riêng; không mặc định che tất cả lỗi thành `Optional.empty()`.

Từ chữ ký `Optional<User>`, người gọi biết rằng không phải mọi ID đều tồn tại. Tuy nhiên **Optional không mô tả lý do vắng mặt**, không cho biết dữ liệu bị thiếu vì quyền truy cập, mạng lỗi, truy vấn thất bại hay bản ghi bị lọc. Nếu các trạng thái ấy quan trọng, phải thiết kế hợp đồng khác.

### 1.1. Bảng quyết định cho kiểu trả về

| Nhu cầu API | Kiểu trả về thường phù hợp | Giải thích |
|---|---|---|
| Tìm một đối tượng có thể không tồn tại | `Optional<User>` | Sự vắng mặt là kết quả bình thường |
| Tìm một phần tử nhỏ nhất từ tập có thể rỗng | `Optional<T>` | Không có min khi không có phần tử |
| Lấy số đo thống kê từ primitive stream rỗng | `OptionalInt`, `OptionalLong`, `OptionalDouble` | Tránh boxing khi API primitive hỗ trợ |
| Liệt kê 0, 1 hoặc nhiều đối tượng | `List<User>` | Danh sách rỗng thường biểu diễn không có phần tử |
| Phải có một đối tượng, thiếu là lỗi nghiệp vụ | `User` hoặc ngoại lệ có chủ đích | Caller không phải xử lý nhánh vắng mặt hợp lệ |
| Lưu bản ghi thất bại do hạ tầng, validation, quyền | Kiểu kết quả lỗi hoặc exception thích hợp | Không được coi lỗi như “không tìm thấy” |
| Hành động không trả dữ liệu | `void` hoặc kiểu kết quả có ý nghĩa | Không tạo `Optional<Void>` chỉ để biểu diễn thành công |
| Hai trạng thái “không có danh sách” và “có danh sách rỗng” thật sự khác nhau | Kiểu miền rõ ràng, hoặc `Optional<List<T>>` nếu cần | Chỉ dùng lớp Optional ngoài nếu sự khác biệt này có ý nghĩa cụ thể |

Bảng là **gợi ý thiết kế**, không phải một bộ luật tuyệt đối. Quan trọng nhất là caller hiểu được hợp đồng và có cách xử lý đúng. Không nên dùng `Optional` cho mọi biến chỉ vì muốn “code hiện đại”.

## 2. Phân biệt không tìm thấy, đầu vào sai và lỗi thực thi

Thiết kế một API tra cứu thường có ba đường đi:

1. **Không có kết quả hợp lệ:** `findById("unknown")` trả `Optional.empty()`.
2. **Đầu vào sai:** `findById(null)` có thể ném `NullPointerException` hoặc `IllegalArgumentException` nếu hợp đồng yêu cầu ID khác null; **không cần biến null ID thành một lần tìm thất bại hợp lệ**.
3. **Không thể thực hiện truy vấn:** lỗi database/network, thiếu quyền hay dữ liệu bị hỏng cần được báo theo API lỗi. Nếu trả empty cho những lỗi ấy, caller dễ kết luận nhầm “bản ghi không tồn tại”.

Ví dụ với hai phương thức có chính sách khác nhau:

~~~java
Optional<User> findById(String id); // Không thấy là kết quả bình thường.
User requireById(String id);        // Không thấy là một tình huống lỗi.
~~~

Hai dòng trên là **chữ ký minh họa**, không phải chương trình độc lập. `requireById` có thể triển khai bằng cách gọi `findById` rồi dùng `orElseThrow(...)` với exception được tài liệu hóa.

Ở tầng HTTP/REST, việc dịch “không tìm thấy” thành `404`, lỗi đầu vào thành `400` và lỗi server thành các mã tương ứng là trách nhiệm **tầng giao tiếp**, không phải bản thân `Optional`. Một `Optional.empty()` không tự xác định status HTTP; API phải đặt quy tắc chuyển đổi rõ ràng.

### 2.1. Optional rỗng không phải lỗi và cũng không phải null

~~~java
Optional<String> present = Optional.of("Lan");
Optional<String> absent = Optional.empty();
Optional<String> fromNullable = Optional.ofNullable(null);
~~~

Ba khai báo chạy được trong một phương thức với import `java.util.Optional`. `present` có nội dung; `absent` và `fromNullable` đều rỗng. Những tình huống sai thường gặp:

~~~java
Optional<String> invalid = null;   // Sai hợp đồng trả Optional.
Optional<String> broken = Optional.of(null); // Ném NullPointerException.
~~~

Hai dòng này là **phản ví dụ**, không phải hướng dẫn sử dụng. `Optional.of(value)` yêu cầu giá trị không null, `Optional.ofNullable(value)` chấp nhận null và biến nó thành empty, `Optional.empty()` thể hiện không có kết quả.

Nếu database adapter có thể trả null khi không có hàng, bọc tại **biên chuyển đổi**:

~~~java
return Optional.ofNullable(rawRepository.findUser(id));
~~~

Đây là **mảnh code minh họa**: chỉ áp dụng khi `rawRepository` và `id` đã tồn tại, và null từ adapter **thực sự có nghĩa “không tìm thấy”**. Không bọc null để che lỗi hoặc dữ liệu không hợp lệ.

## 3. Thiết kế API “find” và “require” nhất quán

Tên phương thức giúp người gọi đoán hợp đồng, nhưng kiểu trả về mới thể hiện chắc chắn điều họ phải xử lý.

~~~java
// Hai contract khác nhau, minh họa:
Optional<Product> findProduct(String sku);
Product requireProduct(String sku);
~~~

Với `findProduct`, không tồn tại là bình thường và thường được thể hiện bằng empty. Với `requireProduct`, không tồn tại là bất thường và có thể ném exception rõ nghĩa như `ProductNotFoundException` (nếu ứng dụng định nghĩa nó). Không tạo tên `getProduct` nhưng đôi khi trả null, đôi khi ném exception, đôi khi trả Optional mà không tài liệu hóa.

**Khuyến nghị cho API public:**

- Nêu rõ **khóa hoặc tham số đầu vào có được phép null không**.
- Nêu rõ **điều kiện nào cho `Optional.empty()`** và điều kiện nào ném exception.
- Nếu phương thức chịu tác dụng của quyền truy cập, hãy quyết định liệu “không được phép thấy” có được cố ý **ẩn như không tồn tại** hay cần kết quả lỗi riêng; điều này do bảo mật và nghiệp vụ quyết định, không phải mặc định của Optional.
- Nếu dữ liệu còn có trạng thái “đã xóa”, “hết hạn”, “không được phép”, “chưa đồng bộ”, một kiểu miền mô tả các nhánh đó có thể tốt hơn `Optional<T>`. Không cố nhồi nhiều ý nghĩa vào một empty.

### 3.1. Không dùng Optional để biến lỗi thành thành công giả

Ví dụ không tốt:

~~~java
Optional<User> findById(String id) {
    try {
        return Optional.ofNullable(database.load(id));
    } catch (RuntimeException ex) {
        return Optional.empty(); // Nguy hiểm: che mọi lỗi hạ tầng.
    }
}
~~~

Đây là **phản ví dụ**, giả sử có `database` và `User`. Khi kết nối đứt, caller sẽ nhận tín hiệu giống hệt “ID chưa từng tồn tại”. Thay vì thế, chỉ chuyển đúng trường hợp “không tìm thấy” thành empty; lỗi database vẫn phải được truyền hoặc chuyển thành lỗi miền có thông tin phù hợp.

Không sử dụng `Optional` như một hệ thống xử lý exception. Nó chỉ biểu diễn **có/không có giá trị**, không mang thông tin lỗi.

## 4. Tại sao API trả collection thường không cần Optional?

Giả sử phương thức trả tất cả người dùng đang hoạt động:

~~~java
List<User> findAllActiveUsers();
~~~

Một `List<User>` rỗng thường đủ để biểu diễn “không tìm thấy ai”; không cần `Optional<List<User>>`. Với Stream cũng có thể trả `Stream<User>` rỗng nếu API thích hợp, nhưng phải tài liệu hóa lifecycle, ví dụ Stream truy vấn database có cần đóng tài nguyên không.

So sánh:

~~~java
Optional<User> findOneActiveUser();
List<User> findAllActiveUsers();
~~~

Đây là hai chữ ký có **ý nghĩa khác nhau**:

- Tìm **một** người: có hoặc không có phần tử.
- Tìm **nhiều** người: có thể có **0 phần tử**, và chính collection đã thể hiện tình huống đó.

Ngoại lệ có lý do: nếu ứng dụng cần phân biệt **“chưa tải danh sách”** với **“đã tải, danh sách trống”**, kiểu `Optional<List<User>>` *có thể* mô tả hai trạng thái. Tuy nhiên một model riêng như `NotLoaded`/`Loaded(empty or nonempty)` hoặc object trạng thái có thể diễn đạt nghiệp vụ tốt hơn khi còn nhiều trạng thái khác.

**Không dùng `null` để đại diện một collection rỗng** nếu API đã chọn hợp đồng luôn trả collection khác null. Người gọi không nên phải kiểm cùng lúc `result == null`, `result.isEmpty()` và `Optional.isEmpty()` chỉ để trả lời câu hỏi “có dữ liệu không?”.

## 5. Optional có nên làm field hoặc tham số không?

Ghi chú Oracle nói Optional **chủ yếu** được thiết kế làm kiểu trả về của method. Đây là định hướng API, **không phải lệnh cấm cú pháp** đối với field hoặc tham số.

### 5.1. Tham số `Optional<T>`

Cách thường dễ gọi hơn:

~~~java
void searchUsers(String keyword);       // Quy định keyword có/không được null.
void searchUsers(SearchCriteria query); // Gom nhiều điều kiện tùy chọn.
~~~

Thay vì đẩy cho mọi caller nghĩa vụ tạo `Optional.of(...)` hoặc `Optional.empty()` cho một tham số đơn giản, hãy cân nhắc overload có ý nghĩa, kiểu cấu hình `SearchCriteria` hoặc một tham số nullable được hợp đồng hóa và kiểm tra ở biên. **Không tự ý cho null** nếu hệ thống có chính sách input phải khác null.

Dùng `Optional<T>` làm tham số vẫn có trường hợp hợp lý, ví dụ một API nội bộ đã dùng Optional như kiểu dữ liệu trung gian và muốn giữ nguyên trạng thái có/không. Nhưng không nên sử dụng chỉ để “thay một null bằng hai tầng kiểm tra”: caller có thể vô tình truyền **null Optional** nếu không có kiểm tra.

### 5.2. Field `Optional<T>` và DTO/persistence

Ví dụ thiết kế cần cân nhắc:

~~~java
class Profile {
    Optional<String> nickname; // Không mặc nhiên phù hợp với DTO/JPA/JSON.
}
~~~

Đây là **mảnh mã minh họa**. Khi đưa Optional vào entity, DTO hoặc trường của model, cần kiểm tra framework cụ thể có hỗ trợ mapping, serialization, validation, reflection và schema ra sao. Không giả định toàn bộ Jackson, ORM hoặc công cụ sinh API đều đối xử với Optional giống nhau.

Một domain model có thể dùng field `String nickname` (nullable theo ràng buộc rõ ràng), nhưng trả ra `Optional<String> nickname()` ở API public:

~~~java
class Profile {
    private final String nickname;

    Profile(String nickname) {
        this.nickname = nickname;
    }

    Optional<String> nickname() {
        return Optional.ofNullable(nickname);
    }
}
~~~

Đây là **class độc lập khi có import `Optional`**, mô tả cách giữ quyền quyết định biểu diễn lưu trữ ở bên trong và dùng Optional tại ranh giới trả về. Điều quan trọng là xác định quy tắc null và không để caller trực tiếp phụ thuộc vào field nội bộ.

### 5.3. Giá trị Optional không dùng làm khóa đồng bộ

`Optional` là **value-based class**: các instance bằng nhau nên được đối xử như giá trị thay thế được. Không dùng `==` để kiểm tra hai Optional có cùng “identity”, không `synchronized(optional)`, và không giả định `Optional.empty()` luôn là một singleton theo hợp đồng API.

So sánh ý nghĩa:

~~~java
boolean absent = result.isEmpty();      // Java 11+
boolean present = result.isPresent();   // Java 8+
~~~

Đây là mảnh code giả sử đã có `result` là `Optional<?>`. Các method kiểm tra trạng thái của Optional an toàn hơn so sánh danh tính instance.

## 6. Caller dùng Optional như thế nào cho đúng?

Một API chỉ tốt khi caller xử lý kết quả có chủ đích. Các phương thức quan trọng:

| Phương thức | Khi dùng | Điều cần nhớ |
|---|---|---|
| `map(f)` | Có kết quả và muốn chuyển kiểu | Mapper trả null sẽ được chuyển thành Optional rỗng |
| `flatMap(f)` | Hàm f **đã** trả Optional | Tránh `Optional<Optional<T>>`; mapper không được trả null Optional |
| `filter(p)` | Chỉ giữ kết quả thỏa điều kiện | Không thỏa điều kiện sẽ thành empty |
| `ifPresent(consumer)` | Cần hành động khi có kết quả | Không tạo giá trị trả về |
| `ifPresentOrElse(a, b)` | Cần hành động cả hai nhánh | Java 9+ |
| `orElse(x)` | Fallback đã có hoặc rẻ | Biểu thức x được đánh giá trước khi gọi phương thức |
| `orElseGet(supplier)` | Fallback chỉ tạo khi rỗng | Supplier được gọi lười khi cần |
| `orElseThrow(supplier)` | Không có kết quả là lỗi trong ngữ cảnh caller | Chọn exception đúng nghiệp vụ |
| `or(supplier)` | Chuyển sang nguồn **Optional khác** nếu rỗng | Java 9+; supplier phải trả Optional khác null |
| `stream()` | Chuyển Optional thành Stream 0 hoặc 1 phần tử | Java 9+; hỗ trợ `flatMap(Optional::stream)` |
| `isEmpty()` | Muốn hỏi có rỗng không | Java 11+; `!isPresent()` nếu cần Java 8 |

Bảng mô tả API hiện hành. `Optional.get()` **vẫn tồn tại, không phải phương thức đã bị xóa hay deprecated**. Tuy nhiên gọi `get()` khi empty ném `NoSuchElementException`; tài liệu API ưu tiên `orElseThrow()` nếu bạn có chủ đích yêu cầu giá trị, hoặc `orElseThrow(supplier)` khi cần lỗi cụ thể.

### 6.1. `map` và `flatMap` tránh lồng Optional

Cho một phương thức:

~~~java
Optional<User> findById(String id);
~~~

Khi muốn lấy tên người dùng khác null:

~~~java
Optional<String> name = findById(id).map(User::name);
~~~

Cả hai là **mảnh mã giả định** các kiểu/phương thức có thật. Nếu `User::name` trả `String`, dùng `map` đúng. Nếu `User::displayName` **đã** trả `Optional<String>`, dùng:

~~~java
Optional<String> name = findById(id)
        .flatMap(User::displayName);
~~~

Không dùng `map(User::displayName)` nếu bạn thực sự muốn một `Optional<String>` đơn: nó tạo `Optional<Optional<String>>`. Với `flatMap`, nếu mapper trả null **thay vì Optional**, API ném `NullPointerException`.

### 6.2. Fallback sớm hay muộn?

~~~java
String name = findById(id)
        .map(User::name)
        .orElse("guest");

String expensiveFallback = findById(id)
        .map(User::name)
        .orElseGet(() -> loadFallbackFromService());
~~~

Đây là các **mảnh mã minh họa**. `orElse("guest")` phù hợp với giá trị có sẵn. Với `orElse(loadFallbackFromService())`, Java đánh giá `loadFallbackFromService()` **trước khi gọi** `orElse`, kể cả khi Optional đã có nội dung. Với `orElseGet(() -> loadFallbackFromService())`, phương thức tạo fallback chỉ được gọi nếu Optional rỗng.

Không phải cứ `orElseGet` luôn nhanh hơn: với hằng số đơn giản, `orElse` dễ đọc hơn. Quyết định dựa vào chi phí và side effect của fallback.

### 6.3. Xử lý lỗi tại đúng lớp

Có thể để tầng repository trả `Optional<User>`, tầng nghiệp vụ yêu cầu bản ghi thì gọi:

~~~java
User user = repository.findById(id)
        .orElseThrow(() -> new UserNotFoundException(id));
~~~

Đây là **mảnh mã minh họa** cần định nghĩa `repository`, `User`, `UserNotFoundException` và `id`. Ý nghĩa là tầng nghiệp vụ chuyển một **sự vắng mặt được phép ở repository** thành **lỗi có ý nghĩa ở use case**. Không cần bắt mọi `NoSuchElementException` sau `get()` rồi mới gắn thông điệp.

Khi caller được phép làm tiếp dù không có dữ liệu, xử lý nhánh empty bằng `ifPresent`, `orElse` hoặc luồng nghiệp vụ tương ứng. Đừng ném exception chỉ để rồi bắt lại ở cùng một phương thức khi empty là tình huống bình thường.

## 7. Ví dụ Java hoàn chỉnh: API tra cứu rõ nghĩa

Tạo file `OptionalApiDesignDemo.java`. Ví dụ có `Directory` với ba hợp đồng:

- `findById` trả `Optional<User>` khi việc không tìm thấy là bình thường.
- `requireById` trả `User` hoặc ném exception nếu không tìm thấy.
- `findAllActive` trả `List<User>`, không cần `Optional<List<User>>`.

Ví dụ chạy trên **JDK 17+**. `Optional` có từ Java 8; trong mã có `Map.of`/`List.of` (Java 9+), `Optional.stream` (Java 9+) và `Optional.isEmpty` (Java 11+): tất cả đều là API đang được hỗ trợ, không phải legacy.

~~~java
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.*;

public class OptionalApiDesignDemo {
    static final class User {
        private final String id;
        private final String name;
        private final boolean active;

        User(String id, String name, boolean active) {
            this.id = id;
            this.name = name;
            this.active = active;
        }

        String name() { return name; }
        boolean active() { return active; }
    }

    static final class Directory {
        private final Map<String, User> users = Map.of(
                "u1", new User("u1", "Lan", true),
                "u2", new User("u2", "Minh", false));

        Optional<User> findById(String id) {
            Objects.requireNonNull(id, "id");
            return Optional.ofNullable(users.get(id));
        }

        Optional<String> findActiveName(String id) {
            return findById(id)
                    .filter(User::active)
                    .map(User::name);
        }

        User requireById(String id) {
            return findById(id).orElseThrow(
                    () -> new NoSuchElementException("No user: " + id));
        }

        List<User> findAllActive() {
            return users.values().stream()
                    .filter(User::active)
                    .collect(Collectors.toList());
        }
    }

    static String fallback(AtomicInteger count) {
        count.incrementAndGet();
        return "guest";
    }

    public static void main(String[] args) {
        Directory directory = new Directory();

        System.out.println("Found: "
                + directory.findById("u1")
                        .map(User::name).orElse("not found"));

        System.out.println("Missing: "
                + directory.findById("u9").isEmpty());

        System.out.println("Inactive name: "
                + directory.findActiveName("u2"));

        System.out.println("Active users: "
                + directory.findAllActive().size());

        System.out.println("Fallback: "
                + directory.findActiveName("u2")
                        .orElseGet(() -> "guest"));

        List<String> activeNames = Stream.of("u1", "u9", "u2")
                .map(directory::findActiveName)
                .flatMap(Optional::stream)
                .collect(Collectors.toList());
        System.out.println("Active names: " + activeNames);

        AtomicInteger fallbackCalls = new AtomicInteger();
        directory.findActiveName("u1")
                .orElse(fallback(fallbackCalls));
        directory.findActiveName("u1")
                .orElseGet(() -> fallback(fallbackCalls));
        System.out.println("Fallback evaluations: "
                + fallbackCalls.get());

        try {
            directory.requireById("u9");
        } catch (NoSuchElementException ex) {
            System.out.println("Required: " + ex.getMessage());
        }

        try {
            directory.findById(null);
        } catch (NullPointerException ex) {
            System.out.println("Null id rejected: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OptionalApiDesignDemo.java
java OptionalApiDesignDemo
~~~

Stdout:

~~~text
Found: Lan
Missing: true
Inactive name: Optional.empty
Active users: 1
Fallback: guest
Active names: [Lan]
Fallback evaluations: 1
Required: No user: u9
Null id rejected: id
~~~

**Giải thích chính xác kết quả:**

1. `findById("u1")` có người dùng `Lan`; `map(User::name)` lấy tên rồi `orElse` để có fallback nếu thiếu.
2. `findById("u9")` trả `Optional.empty`; `isEmpty()` là true.
3. `findActiveName("u2")` rỗng vì tài khoản tồn tại nhưng bị `filter(User::active)` loại. Tại API này, “không có tên active” có thể do thiếu user **hoặc** user không active; nếu caller phải phân biệt hai trường hợp, phương thức cần hợp đồng nhiều trạng thái hơn.
4. `findAllActive()` trả danh sách người dùng active; ở dữ liệu mẫu chỉ có một người, nên size bằng 1.
5. `flatMap(Optional::stream)` chuyển ba kết quả tra cứu tùy chọn thành Stream chỉ có tên thực sự hiện diện; không sinh phần tử null.
6. `Fallback evaluations: 1` cho thấy `orElse(fallback(...))` gọi fallback dù có dữ liệu; `orElseGet(() -> fallback(...))` không gọi supplier khi Optional đang có dữ liệu.
7. `requireById("u9")` ném `NoSuchElementException` có thông báo tường minh, sau đó demo bắt exception để hiển thị.
8. `findById(null)` bị từ chối ở `Objects.requireNonNull`; đây là input sai, **khác** với một ID hợp lệ nhưng không có kết quả.

Trong hệ thống thật, exception nên thuộc miền nghiệp vụ và được tầng giao tiếp chuyển thành lỗi đúng. Demo dùng `NoSuchElementException` của JDK để độc lập, không cần thư viện ngoài.

## 8. Optional ở các kiểu trả về khác

### 8.1. Primitive: OptionalInt, OptionalLong, OptionalDouble

Khi API primitive có sẵn Optional chuyên biệt, dùng chúng để tránh boxing không cần thiết:

~~~java
java.util.OptionalInt min =
        java.util.stream.IntStream.of(3, 8, 2).min();

java.util.OptionalDouble average =
        java.util.stream.DoubleStream.of(2.0, 4.0).average();
~~~

Đây là đoạn chạy trong một phương thức. `min` chứa 2 và `average` chứa 3.0; trên Stream rỗng, kết quả tương ứng là `OptionalInt.empty()` hoặc `OptionalDouble.empty()`. Không cố dùng `Optional<int>`: tham số generic `T` chỉ nhận kiểu tham chiếu, không phải primitive.

Có API trả `Optional<Integer>` nếu mô hình domain là object, nhưng không cần đổi toàn bộ primitive pipeline sang boxed stream chỉ để làm Optional.

### 8.2. Bất đồng bộ

Trong API bất đồng bộ, việc vắng kết quả và việc xử lý bất đồng bộ là hai khía cạnh riêng:

~~~java
java.util.concurrent.CompletionStage<Optional<User>>
        findByIdAsync(String id);
~~~

Đây là **chữ ký minh họa**, cần `User` và import đúng. Nó có ý nghĩa: *sau khi công việc bất đồng bộ hoàn tất bình thường*, có thể có hoặc không có người dùng. Lỗi bất đồng bộ cần đi theo cơ chế báo thất bại của `CompletionStage`, không biến hết thành empty.

`Optional<CompletionStage<User>>` mô tả tình huống khác: ngay lúc gọi đã biết có hay không có một tác vụ bất đồng bộ. Vì vậy không coi hai kiểu này là tương đương.

### 8.3. API public, binary compatibility và client

Nếu API ban đầu trả `User` hoặc `null`, đổi trực tiếp kiểu trả về thành `Optional<User>` sẽ làm các caller hiện tại phải sửa mã và có thể phá tương thích nhị phân. **Không thể overload Java chỉ bằng kiểu trả về.**

Có thể chuyển đổi dần, ví dụ thêm tên phương thức mới `findOptionalById(...)`, giữ method cũ trong giai đoạn migration theo kế hoạch rõ ràng; hoặc thực hiện thay đổi lớn ở một phiên bản API có thông báo phá tương thích. Chọn tên public nhất quán, và tài liệu hóa cả nhánh không tìm thấy.

Với public JSON schema, RPC hoặc database API, `Optional<T>` trong Java **không tự quy định** cách mã hóa “missing”, `null` hay giá trị hiện diện trên wire. Thiết kế hợp đồng giao tiếp riêng và kiểm tra serializer/framework; tránh vô tình để cấu trúc Optional trở thành chi tiết API công khai trên JSON.

## 9. Kiểm thử hợp đồng trả về

Một bộ kiểm thử tốt cho `Optional<User> findById(String id)` nên gồm:

| Trường hợp | Kỳ vọng | Tại sao |
|---|---|---|
| ID hợp lệ và tồn tại | `Optional` có đối tượng đúng | Bảo đảm nhánh thành công |
| ID hợp lệ nhưng vắng | `Optional.empty()` | Đúng ý nghĩa “không tìm thấy” |
| ID null | Lỗi input đúng hợp đồng | Không nhầm input sai thành “không có người dùng” |
| Lỗi database/network | Lỗi riêng, không nuốt thành empty | Không che lỗi hệ thống |
| Trả kết quả | **Không bao giờ là `null Optional`** | Caller được dùng API Optional an toàn |
| Mapper trả null | `map(...)` cho kết quả empty | Xác minh ngữ nghĩa chuyển đổi |
| Hàm đã trả Optional | `flatMap(...)` không lồng Optional | Giữ chữ ký rõ ràng |
| Stream chứa nhiều Optional | `flatMap(Optional::stream)` bỏ kết quả rỗng | Không tạo null trong stream |

Trong bộ test JUnit hoặc framework tương đương, hãy so sánh bằng `assertEquals(Optional.empty(), actual)` hoặc kiểm `actual.isEmpty()`, **không dùng `actual == Optional.empty()`**. Nếu muốn kiểm giá trị, có thể dùng `assertEquals(expected, actual.orElseThrow())` khi test đã biết chắc phải có kết quả.

Đối với hợp đồng thay đổi theo điều kiện nghiệp vụ, bổ sung test về quyền truy cập, bản ghi bị khóa, bản ghi bị xóa mềm và lỗi timeout. Những tình huống này không tự “đi theo Optional”; chúng phải do người thiết kế API định nghĩa.

## 10. Những lỗi thường gặp trong thiết kế

**Lỗi 1 — Trả `null` thay vì `Optional.empty()`.** Chữ ký Optional mất ý nghĩa và caller vẫn NPE. Trả một instance Optional không null trong mọi nhánh thực thi bình thường.

**Lỗi 2 — Dùng `Optional` cho mọi phương thức.** `List<T>` rỗng, `void`, `boolean` hoặc kiểu kết quả chuyên biệt thường diễn đạt đúng hơn tùy mục đích. Optional chỉ nói có/không một giá trị, không thay thế toàn bộ kiểu trả về.

**Lỗi 3 — Biến lỗi database thành empty.** Caller hiểu nhầm “không tìm thấy”. Phải tách lỗi hệ thống khỏi kết quả không tồn tại.

**Lỗi 4 — Bắt người gọi nhận `Optional<Optional<T>>`.** Khi phương thức mapper đã trả Optional, dùng `flatMap`, không dùng `map` theo cách lồng tùy chọn không cần thiết.

**Lỗi 5 — Dùng `get()` ngay sau `findById` mà không kiểm.** Nếu ID vắng, code ném `NoSuchElementException` không đúng ý đồ. Dùng `orElseThrow` có thông điệp/lỗi miền khi thiếu là lỗi, hoặc xử lý nhánh empty một cách bình thường.

**Lỗi 6 — Dùng `orElse(expensive())` và tưởng lazy.** Java đánh giá đối số phương thức trước khi gọi `orElse`. Dùng `orElseGet(() -> expensive())` khi chỉ muốn tính fallback lúc rỗng.

**Lỗi 7 — Dùng Optional làm field/parameter một cách máy móc.** Có thể phát sinh vấn đề mapping, JSON, overload và mã gọi. Ưu tiên dùng làm kiểu trả về; ngoại lệ phải có lý do, ràng buộc và kiểm thử.

**Lỗi 8 — So sánh Optional bằng `==` hoặc khóa trên Optional.** Optional là value-based; không dựa vào identity, không dùng nó làm monitor đồng bộ.

**Lỗi 9 — Coi `Optional.empty()` luôn có cùng ý nghĩa.** Với API `findActiveName`, empty có thể đến từ không tồn tại hoặc không active. Nếu caller cần phân biệt, xây kiểu trả về diễn đạt được nhiều trạng thái.

**Lỗi 10 — Đổi `T` thành `Optional<T>` mà không xét tương thích API.** Đây là thay đổi chữ ký công khai, phá code hiện tại và có thể phá binary compatibility; cần chính sách tiến hóa API rõ.

## 11. Câu hỏi luyện tập

1. Một endpoint có thể tìm thấy một hóa đơn hoặc không. Nên để tầng repository trả `Invoice` nullable hay `Optional<Invoice>`? Khi nào việc trả empty là hợp lệ?
2. Phương thức liệt kê mọi hóa đơn của khách hàng nên trả `Optional<List<Invoice>>` hay `List<Invoice>` trong trường hợp thông thường? Vì sao?
3. Khi một truy vấn database timeout, có nên bắt mọi exception và trả `Optional.empty()` không?
4. Nếu `User.displayName()` trả `Optional<String>`, tại sao nên dùng `flatMap(User::displayName)`?
5. Vì sao `findUser(null)` không nhất thiết phải trả empty, dù `findUser("unknown")` trả empty?
6. Nếu caller cần phân biệt “không có người dùng”, “không có quyền” và “có người dùng”, một `Optional<User>` có đủ thông tin không?
7. API hiện tại trả `User`/null. Đổi thành `Optional<User>` có thể làm hỏng những caller nào, và giải pháp migration hợp lý là gì?

**Gợi ý đáp án:**

1. `Optional<Invoice>` hợp lý khi không tìm thấy là bình thường; lỗi hạ tầng hoặc quyền phải có chính sách riêng.
2. `List<Invoice>`, vì bản thân danh sách rỗng biểu diễn không có phần tử; chỉ dùng Optional ngoài khi “danh sách chưa có” và “danh sách rỗng” thật sự khác nhau.
3. Không. Timeout là lỗi truy vấn, không đồng nghĩa với kết quả vắng.
4. Vì mapper đã trả Optional; `flatMap` giữ một tầng Optional.
5. Null ID là input không hợp lệ theo hợp đồng; unknown ID có thể là input hợp lệ nhưng không tồn tại.
6. Không. Dùng result type nhiều trạng thái hoặc exception phù hợp để không đánh mất ngữ nghĩa.
7. Source caller phải đổi cách xử lý và binary caller có thể không tương thích; có thể thêm method API mới, deprecate method cũ theo kế hoạch và cập nhật test.

## Tóm tắt

**Ưu tiên `Optional<T>` làm kiểu trả về khi sự vắng mặt của một kết quả là hợp lệ, nhưng `null` dễ gây lỗi.** Trả `Optional.empty()` thay vì null Optional; phân biệt “không tìm thấy” với lỗi; thường trả collection rỗng cho truy vấn nhiều phần tử; hạn chế dùng Optional làm field/parameter nếu không có lý do. Caller nên khai thác `map`, `flatMap`, `orElseGet`, `orElseThrow` và `stream` thay vì `get()` vô điều kiện. Chữ ký API, tài liệu hợp đồng, chính sách lỗi và kiểm thử phải nhất quán.

### Tài liệu chính thức, còn áp dụng

- [Oracle Java SE 26 — Optional: API Note, mục đích kiểu trả về và các phương thức](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html)
- [Oracle Java SE 26 — OptionalInt](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalInt.html)
- [Oracle Java SE 26 — OptionalLong](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalLong.html)
- [Oracle Java SE 26 — OptionalDouble](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalDouble.html)
- [Oracle Java SE 26 — Stream.findFirst/findAny và Stream API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 26 — CompletionStage](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html)
