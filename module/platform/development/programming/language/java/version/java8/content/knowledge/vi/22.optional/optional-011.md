# Optional: Giới hạn dùng cho field, tham số và mô hình dữ liệu trong Java

**Chủ đề cha:** Optional — Java Stream/Java 8. **Trọng tâm:** `java.util.Optional<T>` rất hữu ích khi một phương thức **có thể không trả được một giá trị**, nhưng không có nghĩa mọi field, tham số, entity, DTO hoặc dữ liệu JSON đều nên được bao bọc bởi `Optional`. Bài này phân biệt **cú pháp được Java cho phép** với **lựa chọn thiết kế nên dùng**, các ngoại lệ hợp lý và yêu cầu khi tích hợp framework.

**Phạm vi:** `Optional` có từ Java 8 và vẫn là API hiện hành. Các ví dụ hoàn chỉnh dùng **JDK 17+**; `record` và `sealed interface` ở ví dụ đều dùng được từ Java 17. Các lưu ý về cơ sở dữ liệu, JSON và công cụ mapping được diễn đạt theo hợp đồng tích hợp, không coi hành vi của một thư viện cụ thể là mặc định của mọi dự án.

## 1. Optional biểu diễn điều gì?

`Optional<T>` là một container **có một giá trị không-null hoặc không có giá trị**. Nó biểu diễn hai trạng thái của một kết quả 0–1:

| Tình huống | Biểu diễn | Ý nghĩa |
| --- | --- | --- |
| Tìm thấy người dùng | `Optional.of(user)` | Có đúng một kết quả |
| Không tìm thấy | `Optional.empty()` | Không có kết quả |
| API cũ trả đối tượng có thể null | `Optional.ofNullable(value)` | Null được chuyển thành empty |
| Một giá trị hợp lệ bằng 0 | `Optional.of(0)` | **Có giá trị 0**, không phải empty |
| Chuỗi rỗng hợp lệ | `Optional.of("")` | **Có chuỗi rỗng**, không phải empty |

`Optional.of(null)` ném `NullPointerException`. `Optional.ofNullable(null)` trả empty. Bản thân **biến chứa Optional không nên là null**: `Optional<User> maybeUser = null` tạo ra một trạng thái thứ ba ngoài hợp đồng hai trạng thái mà người gọi tưởng đang dùng.

Theo tài liệu API, `Optional` là **value-based class**. Không dựa vào object identity, không so sánh bằng `==` để kiểm tra empty, không dùng nó làm monitor của `synchronized`. Hãy dùng `isPresent()`, `isEmpty()` (Java 11+) hoặc các phép biến đổi `map`/`flatMap`/`orElse`. Nếu cần so sánh giá trị hai Optional, dùng `equals`.

**Định hướng quan trọng:** Optional chủ yếu dành cho **kiểu trả về của phương thức** khi “không có kết quả” là một outcome hợp lệ và trả `null` dễ gây lỗi. Optional **không** thay thế exception, không chứa thông tin nguyên nhân thất bại và không phải một kiểu để tự động sửa mọi thiết kế nullable.

## 2. Bảng quyết định nhanh: Optional ở đâu là hợp lý?

| Vị trí | Khuyến nghị thông thường | Lý do |
| --- | --- | --- |
| Phương thức trả **0 hoặc 1** kết quả | **Ưu tiên `Optional<T>`** | Chữ ký cho biết có thể vắng mặt |
| Phương thức trả **0 đến n** kết quả | **Collection rỗng** | `List<T>` rỗng đã biểu đạt số phần tử bằng 0 |
| Trường dữ liệu bắt buộc, invariant không-null | **Trường `T` trực tiếp** | Optional thêm một lớp không cần thiết |
| Trường tùy chọn của entity/DTO lưu trữ | **Cân nhắc hợp đồng nullability và framework** | Serializer/ORM/mapping/validation có quy ước riêng |
| Tham số tùy chọn của một API thông thường | **Thường chọn overload, kiểu request hoặc chính sách nullability rõ ràng** | Tránh buộc mọi caller tạo wrapper |
| Trường hợp thực sự cần một field Optional trong mô hình nội bộ | **Có thể dùng có chủ đích** | Bảo đảm chính field Optional không null và kiểm tra toolchain |
| Cập nhật PATCH: giữ nguyên/xóa/đặt mới | **Kiểu domain có ba trạng thái hoặc presence tracking** | Một `Optional<T>` thường chỉ mã hóa hai trạng thái |
| Kết quả có thể là thành công, không thấy, thiếu quyền, lỗi mạng | **Mô hình kết quả đa trạng thái/exception** | Optional không giữ nguyên nhân |

Đây là **quy tắc thiết kế theo ngữ cảnh**, không phải lệnh cấm của trình biên dịch. Java cho phép field và tham số kiểu `Optional<T>`; điều cần cân nhắc là tính rõ ràng, khả năng tương tác và ý nghĩa dữ liệu.

## 3. Trường hợp điển hình nên dùng: kiểu trả về của phương thức

Ví dụ một repository tìm user theo ID:

```java
Optional<User> findById(String id);
```

Đây là **khai báo minh họa** khi kiểu `User` đã được định nghĩa. Nó cho người gọi biết “không tìm thấy” là kết quả có thể xảy ra. Một phương thức trả `User` thẳng có thể yêu cầu người gọi đọc tài liệu để biết khi nào có `null`.

Một hợp đồng rõ ràng hơn:

- `id` **bắt buộc không-null**: khi caller truyền null, phương thức có thể ném `NullPointerException` hoặc `IllegalArgumentException` theo quy ước API.
- Không có user khớp ID: trả `Optional.empty()`.
- Tìm thấy user: trả `Optional.of(user)`.
- Cơ sở dữ liệu bị lỗi hoặc quá hạn kết nối: phát sinh lỗi thích hợp; **không** trả empty như thể truy vấn thành công nhưng không thấy bản ghi.

`Optional` không phân biệt “không tìm thấy” và “không có quyền đọc” nếu cả hai cùng được mã hóa thành empty; khi yêu cầu nghiệp vụ cần phân biệt, phải dùng kiểu kết quả giàu thông tin hơn.

### 3.1. Ví dụ Java 17+: Optional ở ranh giới truy vấn, không phải field

Tạo file **`OptionalBoundaryDemo.java`**:

```java
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class OptionalBoundaryDemo {
    // Giả lập dữ liệu nhận từ một nguồn cho phép email null.
    record User(String id, String email) {
        public User {
            Objects.requireNonNull(id, "id");
        }

        Optional<String> emailIfPresent() {
            return Optional.ofNullable(email);
        }
    }

    private static final List<User> USERS = List.of(
            new User("u1", "lan@example.com"),
            new User("u2", null)
    );

    static Optional<User> findById(String id) {
        Objects.requireNonNull(id, "id");
        return USERS.stream()
                .filter(user -> user.id().equals(id))
                .findFirst();
    }

    public static void main(String[] args) {
        Optional<User> found = findById("u1");
        Optional<User> missing = findById("u9");

        System.out.println("Found: "
                + found.map(User::id).orElse("missing"));
        System.out.println("Missing user: " + missing.isEmpty());
        System.out.println("Email u2: "
                + findById("u2")
                        .flatMap(User::emailIfPresent)
                        .orElse("not set"));
        System.out.println("Zero is present: "
                + Optional.of(0).isPresent());
        System.out.println("Blank is present: "
                + Optional.of("").isPresent());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 OptionalBoundaryDemo.java
java OptionalBoundaryDemo
```

**Stdout:**

```text
Found: u1
Missing user: true
Email u2: not set
Zero is present: true
Blank is present: true
```

**Phân tích:**

1. `findById` trả `Optional<User>` để thể hiện 0–1 kết quả mà không trả `null` ở ranh giới repository.
2. `User` cố ý có trường `email` kiểu `String` nullable vì đây là **ví dụ mô phỏng dữ liệu cũ**. Điều này không có nghĩa mọi domain model nên cho phép null: nếu email bắt buộc, hãy validate ngay constructor và giữ invariant không-null.
3. Accessor `emailIfPresent()` đưa giá trị nullable qua ranh giới an toàn bằng `Optional.ofNullable`. `flatMap` nối hai phép tìm kiếm có thể rỗng mà không tạo `Optional<Optional<String>>`.
4. `Optional.of(0)` và `Optional.of("")` đều present. Quy tắc “chuỗi blank là thiếu dữ liệu” phải được thể hiện riêng qua `filter`/validation, không tự phát sinh từ Optional.
5. `List.of` không chứa phần tử null; các phần tử ở đây là hai đối tượng `User` không-null. Việc record thứ hai có một component `email` null **không** làm `List.of` lỗi.

Trong hệ thống thực, repository có thể là JDBC/JPA/remote client. Ví dụ chỉ minh họa **hợp đồng trả về**, không áp đặt một công nghệ persistence cụ thể.

## 4. Giới hạn khi đặt Optional làm field của entity

### 4.1. Field Optional không bị Java cấm, nhưng thêm một lớp trạng thái

So sánh hai cách biểu diễn trong lớp đối tượng:

```java
// Mô hình A: thuộc tính nullable (khi hợp đồng dữ liệu cho phép).
private String nickname;

// Mô hình B: field luôn phải giữ một container hợp lệ.
private Optional<String> nickname = Optional.empty();
```

Hai dòng này là **đoạn minh họa field trong các lớp khác nhau**, không phải file có thể biên dịch độc lập. Với mô hình B, chương trình phải bảo đảm **không bao giờ gán `nickname = null`**, kể cả qua reflection, deserialize hoặc mapper. Nếu không, “Optional có thể empty” cộng thêm “Optional field có thể null” khiến logic vẫn phải kiểm tra null trên wrapper.

Mô hình A đơn giản cho nhiều storage mapper nhưng yêu cầu người dùng của model biết rõ quy tắc nullability. Một accessor có thể giúp ranh giới sử dụng dễ hơn:

```java
public Optional<String> nicknameIfPresent() {
    return Optional.ofNullable(nickname);
}
```

Đây là **đoạn phương thức trong một lớp có field `String nickname`**. Nó trả Optional khi *đọc*, đồng thời cho phép persistence model giữ biểu diễn phù hợp với framework.

### 4.2. ORM/JPA và mapping database

Không nên mặc định một field `Optional<String>` tự được ORM xem như cột `VARCHAR` cho `String` bên trong. Khả năng ánh xạ, access strategy, attribute converter, setter, proxy và dirty checking phụ thuộc framework/phiên bản/cấu hình.

Điểm cần kiểm tra khi thiết kế entity:

- Entity nào là chủ sở hữu invariant của trường nullable/NOT NULL?
- Field Optional có được mapping/persist đúng không, hay mapper coi `Optional` là một kiểu object khác?
- Khi tải record từ DB, setter/constructor/binding có thể tạo field Optional **null** hay không?
- Validation chạy tại thời điểm nào? Có thể mapper bypass constructor không?
- Việc update null, clear field và không update field có được tách biệt không?

Nhiều repository API trả `Optional<Entity>` từ **phương thức tìm một entity**. Điều đó **không suy ra** chính entity nên chứa mọi thuộc tính tùy chọn dưới dạng `Optional<...>`. Hai cấp độ dữ liệu có vai trò khác nhau.

### 4.3. Serializable và các framework data binding

`java.util.Optional` **không triển khai `java.io.Serializable`**. Vì vậy không được giả định một object có field Optional sẽ tự tương thích với Java object serialization chỉ nhờ các field khác triển khai Serializable. Đây là ràng buộc kỹ thuật nếu một hệ thống còn có hợp đồng tương tác dạng Java serialization; không phải đề xuất dùng cơ chế serialization cũ cho dự án mới.

JSON, ORM, mapper, Bean Validation và các công cụ phát sinh schema có thể có **hỗ trợ riêng** đối với Optional, tùy thư viện, phiên bản và module/cấu hình. Chẳng hạn một số JSON library có module hỗ trợ kiểu Optional; không có điều đó thì kết quả có thể khác với mong muốn biểu diễn thuộc tính JSON hoặc bị báo lỗi mapping. Cần kiểm tra bằng round-trip test cho **trường hiện diện, trường vắng mặt, trường null và giá trị hợp lệ**.

Không coi những hành vi của thư viện cụ thể (ví dụ trường empty sẽ bị bỏ qua hay xuất hiện với `null`) là một quy tắc của Java Optional. Đó là **quy tắc serialization**, không phải hợp đồng của `Optional<T>`.

## 5. Field Optional có bao giờ là lựa chọn đúng không?

**Có thể**, khi mô hình nội bộ được thiết kế với invariant rõ ràng, các công cụ sử dụng nó đều hỗ trợ và hai trạng thái present/empty thật sự là đủ. Ví dụ một record nội bộ chỉ phục vụ logic Java:

```java
record InternalQuery(Optional<String> prefix) {
    public InternalQuery {
        Objects.requireNonNull(prefix, "prefix");
    }
}
```

Đây là **khai báo record đặt bên trong một lớp với import `java.util.Optional` và `java.util.Objects`**, không phải file độc lập. Constructor buộc **container** khác null. Người gọi phải tạo `new InternalQuery(Optional.empty())` hoặc `new InternalQuery(Optional.of("AB"))`; truyền null gây `NullPointerException`.

Ưu điểm của lựa chọn này: invariant “có/không có prefix” hiển thị trong kiểu của record, phù hợp nếu các caller vốn làm việc với Optional. Đổi lại: mọi caller phải bọc giá trị và mọi serializer/mapper phải tương thích. Nếu chỉ cần một request đơn giản hoặc cùng kiểu này được gửi ra JSON/DB, có thể thuận tiện hơn khi dùng `String prefix` với contract nullable rõ ràng hoặc một request object có phương thức kiểm tra trạng thái riêng.

Vì vậy hướng dẫn **“Optional chủ yếu cho return type” không phải “field Optional luôn sai”**. Quyết định dựa trên phạm vi dùng, chi phí tương tác và invariant mà mô hình phải giữ.

## 6. Giới hạn khi truyền Optional làm tham số phương thức

Java cho phép:

```java
void sendReport(Optional<String> recipient);
```

Đây là **khai báo minh họa**. Tuy nhiên với API gọi phổ biến, cách này có ba nhược điểm:

1. Người gọi vốn có `String` phải tự tạo `Optional.of(value)`; người không có giá trị tạo `Optional.empty()` — tăng ceremony cho các lời gọi.
2. Chính tham số `Optional<String> recipient` vẫn có thể bị truyền `null`; Java không tự cấm `sendReport(null)`.
3. Khi tham số có nhiều trạng thái hoặc nhiều lựa chọn liên quan, một wrapper Optional không diễn đạt hết validation và invariant của request.

### 6.1. Dùng overload khi có một mặc định đơn giản

Tạo file **`OptionalParameterDemo.java`**:

```java
import java.util.Objects;

public class OptionalParameterDemo {
    static String greeting() {
        return greeting("Guest");
    }

    static String greeting(String name) {
        return "Hello, " + Objects.requireNonNull(name, "name");
    }

    record SearchOptions(boolean includeDisabled, int pageSize) {
        public SearchOptions {
            if (pageSize < 1) {
                throw new IllegalArgumentException("pageSize must be positive");
            }
        }
    }

    static String describe(SearchOptions options) {
        Objects.requireNonNull(options, "options");
        String filter = options.includeDisabled() ? "All" : "Active only";
        return filter + ", pageSize=" + options.pageSize();
    }

    public static void main(String[] args) {
        System.out.println(greeting());
        System.out.println(greeting("Lan"));
        System.out.println(describe(new SearchOptions(false, 20)));
    }
}
```

Chạy:

```bash
javac --release 17 OptionalParameterDemo.java
java OptionalParameterDemo
```

**Stdout:**

```text
Hello, Guest
Hello, Lan
Active only, pageSize=20
```

Phương thức overload `greeting()` biểu đạt việc không truyền tên, còn `greeting(String)` có yêu cầu không-null rõ ràng. Với nhiều tham số liên quan, `SearchOptions` gom cấu hình thành một kiểu có invariant (`pageSize` dương). Trong các API thực tế có thể dùng request builder, default configuration hoặc một kiểu domain khác nếu phù hợp.

**Không có một quy tắc duy nhất cho mọi API:** nếu một thư viện Java nội bộ có hợp đồng nhận `Optional<T>` từ caller và điều đó thực sự làm lời gọi rõ ràng hơn, việc dùng Optional parameter vẫn hợp lệ. Khi đó phải kiểm tra non-null container bằng `Objects.requireNonNull(optional)` và ghi rõ semantics present/empty.

### 6.2. Tham số nullable và annotation

Một số codebase chọn tham số `String` có thể null cùng annotation nullability, chẳng hạn `@Nullable` từ thư viện/chính sách mà dự án sử dụng. **Java SE không có một annotation `@Nullable` thống nhất cho mọi framework**; cần xác định annotation, static analyzer, IDE và công cụ binding nào hiểu nó.

Nếu chọn hợp đồng nullable, hãy mô tả rõ: `null` có nghĩa gì, có giá trị mặc định hay không, và thành phần nào validate. Không dùng `null` tùy tiện; đồng thời cũng không bọc `Optional` chỉ để lảng tránh việc định nghĩa hợp đồng.

## 7. Mô hình dữ liệu: phân biệt “thuộc tính tùy chọn” với “kết quả tìm kiếm tùy chọn”

Một **kết quả tìm kiếm** là 0 hoặc 1 `User`; `Optional<User> findById(...)` biểu đạt điều đó tốt.

Một **User entity** lại có các thuộc tính và invariant riêng. Đối với `email`:

- Nếu email **bắt buộc**, constructor/validation nên đảm bảo email hợp lệ. Không cần `Optional<String>` để bao bọc một giá trị luôn có.
- Nếu email **có thể thiếu** trong dữ liệu lưu trữ, các lựa chọn gồm field nullable có contract rõ và accessor Optional; hoặc field Optional có kiểm soát khi toolchain hỗ trợ.
- Nếu email có nhiều trạng thái nghiệp vụ (chưa xác thực, bị ẩn do quyền riêng tư, người dùng đã xóa, không tải được từ dịch vụ ngoài), một Optional rỗng **không nói trạng thái nào đã xảy ra**. Cần domain type mang thông tin cụ thể.
- Nếu phía ngoài là JSON, dữ liệu không chứa field, chứa `null` và chứa `""` có thể mang nghĩa khác nhau. Phải kiểm tra hợp đồng JSON độc lập với lựa chọn kiểu Java.

### 7.1. Vì sao `Optional<List<T>>` thường không cần thiết?

Với phương thức tìm nhiều phần tử:

```java
List<Order> findOrders(String customerId);
```

Đây là chữ ký minh họa khi kiểu `Order` đã được định nghĩa. `List.of()` hoặc danh sách rỗng biểu thị **truy vấn thành công và có 0 bản ghi**. `Optional<List<Order>>` tạo thêm trạng thái “không có danh sách”, thường không cung cấp ý nghĩa hữu ích.

Nhưng nếu hệ thống phải phân biệt **chưa từng truy vấn** với **đã truy vấn và có danh sách rỗng**, `Optional<List<T>>` có thể có ý nghĩa trong một mô hình cụ thể. Hãy đặt tên và tài liệu hóa hai trạng thái; trong một số tình huống, enum hoặc kiểu state riêng rõ ràng hơn.

## 8. Tại sao Optional không đủ cho JSON PATCH và ba trạng thái cập nhật?

Đây là giới hạn quan trọng trong **mô hình dữ liệu yêu cầu cập nhật từng phần**.

Ví dụ một yêu cầu sửa email:

1. **Không gửi thuộc tính email** → giữ nguyên giá trị hiện có.
2. **Gửi email: null** → xóa email.
3. **Gửi email: "new@example.com"** → đặt giá trị mới.

Một `Optional<String>` thông thường chỉ chứa **present(value)** hoặc **empty**. Nếu deserializer gộp “thuộc tính không tồn tại” và “thuộc tính có null” thành `Optional.empty()`, hai yêu cầu khác nhau sẽ không thể phân biệt.

**Ví dụ JSON minh họa:**

```json
{}
```

```json
{"email": null}
```

```json
{"email": "new@example.com"}
```

Đừng suy luận một thư viện JSON bất kỳ sẽ biến ba cấu trúc này thành ba trạng thái Java khác nhau. Cần **presence tracking** ở tầng parsing hoặc một kiểu domain phân biệt ba hành động, rồi validate trước khi áp dụng cập nhật.

### 8.1. Java 17+: dùng kiểu domain phân biệt Keep, Clear, Set

Tạo file **`EmailPatchDemo.java`**:

```java
import java.util.Objects;

public class EmailPatchDemo {
    sealed interface EmailChange permits Keep, Clear, SetEmail {}

    record Keep() implements EmailChange {}
    record Clear() implements EmailChange {}

    record SetEmail(String value) implements EmailChange {
        public SetEmail {
            Objects.requireNonNull(value, "value");
        }
    }

    static String apply(String current, EmailChange change) {
        Objects.requireNonNull(change, "change");

        if (change instanceof Keep) {
            return current;
        }
        if (change instanceof Clear) {
            return null;
        }
        return ((SetEmail) change).value();
    }

    static String display(String email) {
        return email == null ? "<none>" : email;
    }

    public static void main(String[] args) {
        String current = "lan@example.com";

        System.out.println("Keep: "
                + display(apply(current, new Keep())));
        System.out.println("Clear: "
                + display(apply(current, new Clear())));
        System.out.println("Set: "
                + display(apply(current, new SetEmail("new@example.com"))));
    }
}
```

Chạy:

```bash
javac --release 17 EmailPatchDemo.java
java EmailPatchDemo
```

**Stdout:**

```text
Keep: lan@example.com
Clear: <none>
Set: new@example.com
```

**Giải thích:**

- `sealed interface` (được chuẩn hóa trong Java 17) giới hạn các biến thể của hành động email. `record Keep`/`Clear`/`SetEmail` biểu đạt ba lựa chọn ngay trong kiểu dữ liệu.
- `SetEmail` không chấp nhận `null`; sản phẩm thực còn nên validate định dạng email và các giới hạn nghiệp vụ phù hợp.
- Phương thức `apply` trả `String` nullable chỉ để mô phỏng giá trị email lưu trữ khi **Clear**. Đây là ranh giới được quản lý; không đồng nhất với cách trả kết quả tra cứu `Optional`.
- Tầng nhận JSON phải xác định **field có xuất hiện không**, field có null hay không, rồi chuyển thành `Keep`/`Clear`/`SetEmail`. Bản thân `sealed interface` không tự cấu hình serializer hay bảo đảm mapping HTTP.
- Với dự án chạy phiên bản Java thấp hơn 17, cùng ý nghĩa có thể biểu đạt bằng enum và lớp request được validate; không nhất thiết cần sealed/record.

Mô hình này xử lý đúng yêu cầu **ba trạng thái**. Đừng cố nén tất cả vào `Optional.empty()`, vì thông tin “không gửi” và “muốn xóa” sẽ bị mất.

## 9. Nullable, absent và invalid không đồng nghĩa

Cần phân biệt ít nhất ba lớp trạng thái:

| Trạng thái | Ý nghĩa | Cách xử lý thường dùng |
| --- | --- | --- |
| **Absent** | Không có giá trị/kết quả | Optional empty, collection rỗng, hành động Keep tùy contract |
| **Present, valid** | Có giá trị hợp lệ | `Optional.of(value)`, field domain kiểu `T` |
| **Present nhưng invalid** | Có giá trị song không thỏa invariant | Validation error/exception, không tự biến thành absent |
| **External error** | Không tải/không truy vấn được | Báo lỗi có thông tin; không giả vờ “không thấy” |

Ví dụ email `""`: Optional coi đây là **present**. Nếu nghiệp vụ cấm chuỗi rỗng, cần xác minh:

```java
Optional<String> nonBlankEmail = Optional.ofNullable(input)
        .map(String::trim)
        .filter(s -> !s.isEmpty());
```

Đây là **đoạn mã trong phương thức** và `input` là String có thể null. Nó phù hợp khi mục tiêu là biến dữ liệu tùy chọn blank thành không có email. Nếu quy tắc bắt buộc email không rỗng, **trả lỗi validation** thay vì âm thầm biến email sai thành absent. Lựa chọn đúng phụ thuộc contract.

Đặc biệt, database `NULL`, JSON `null`, field không có trong JSON và `Optional.empty()` có thể tương quan nhưng **không phải cùng một khái niệm**. Không chuyển qua lại thiếu kiểm soát trong nhiều tầng ứng dụng.

## 10. Những yếu tố framework phải kiểm thử trước khi chọn Optional field

Khi dự định dùng Optional trong entity/DTO/record được serialize, hãy lập một **test round-trip** và xác nhận:

1. **Serialization:** khi field present, JSON/XML/schema tạo ra giá trị mong muốn hay object wrapper ngoài ý muốn?
2. **Deserialization:** thuộc tính bị thiếu, `null`, `""` và giá trị có thật được phân biệt thế nào?
3. **Initialization:** mapper/ORM có thể tạo field Optional bằng `null` không, kể cả khi constructor đã có default?
4. **Database:** field có được ánh xạ đúng kiểu cột và `NULL` không? Các update có tuân thủ constraint và dirty checking?
5. **Validation:** các annotation/validator được áp dụng vào phần tử `T` bên trong Optional hay vào container? Tool có hỗ trợ unwrap không?
6. **API generation:** OpenAPI/GraphQL/IDL/schema nhìn nhận field optional ra sao, có sinh kiểu wrapper trong client không?
7. **Backward compatibility:** thay `String` bằng `Optional<String>` ở public DTO/record có làm thay đổi chữ ký constructor, accessor, getter hoặc JSON contract đang dùng không?
8. **Performance:** có phải tạo hàng triệu Optional như field sống lâu trong object graph, hay chỉ tạo tạm khi trả phương thức? Đánh giá khi thực sự có bằng chứng bottleneck.

**Một số thư viện có module hỗ trợ Optional** nên việc dùng nó trong DTO không tự động là sai. Nhưng việc hỗ trợ phải được xác minh bằng phiên bản và cấu hình đang chạy. Quy tắc chính là **không đoán hành vi framework chỉ từ kiểu Optional của Java**.

## 11. Thiết kế API không làm lộ nullable một cách tình cờ

Một API thực tế có thể phân chia ranh giới như sau:

```java
// Lớp lưu trữ: nullable do schema/legacy.
String emailColumn;

// Lớp truy vấn: có thể tìm thấy hoặc không tìm thấy entity.
Optional<User> findUserById(String id);

// Lớp domain: thuộc tính email có thể vắng mặt.
Optional<String> emailIfPresent();

// Lớp cập nhật: có ba hành động riêng.
EmailChange emailChange;
```

Các dòng trên là **sơ đồ chữ ký và field rời**; không phải một chương trình Java độc lập. Điều quan trọng là lựa chọn kiểu phản ánh **ngữ nghĩa ở từng tầng**:

- Có/không tìm thấy một entity: `Optional<User>`.
- Có/không có một email được đọc từ storage: Optional accessor hoặc contract nullable rõ.
- Thao tác cập nhật email: kiểu `EmailChange` phân biệt Keep/Clear/Set.
- Không có đơn hàng trong truy vấn thành công: `List<Order>` rỗng.
- Tham số user ID bắt buộc: `String id` được validate, không bọc `Optional<String>`.
- Truy vấn thất bại: lỗi riêng, không `Optional.empty()`.

Không cần “thống nhất” dùng Optional cho mọi tầng. **Tính nhất quán của ý nghĩa** quan trọng hơn sự đồng nhất hình thức của wrapper.

## 12. Những hiểu nhầm và lỗi phổ biến

1. **“Java không cho phép field Optional.”** Không đúng: trình biên dịch cho phép; vấn đề là API khuyến nghị Optional chủ yếu làm return type và các ràng buộc tích hợp.
2. **“Tất cả field nullable nên đổi thành `Optional<T>`.”** Không đúng: ORM, serializer, domain invariant và nullability contract phải được cân nhắc.
3. **“`Optional<String> field` không bao giờ null.”** Sai: chính field Optional vẫn có thể bị gán null hoặc bị mapper khởi tạo sai; hãy validate non-null container khi dùng.
4. **“Có thể dùng `Optional<T>` ở tham số để Java tự cấm truyền null.”** Sai: `method(null)` vẫn biên dịch với tham số kiểu Optional; phải kiểm tra.
5. **“`Optional.empty()` biểu thị giá trị null được chứa bên trong.”** Không đúng: Optional empty không chứa giá trị nào; `Optional.of(null)` ném NPE.
6. **“JSON absent và JSON null luôn giống nhau.”** Không đúng: giao thức/contract có thể phân biệt, cần presence tracking nếu quan trọng.
7. **“PATCH có thể dùng Optional là đủ cho Keep/Clear/Set.”** Không hẳn: một Optional thường chỉ có hai trạng thái, dễ gộp hai hành động khác nhau.
8. **“Mapper sẽ tự lưu Optional xuống cột String.”** Không có bảo đảm chung; cấu hình ORM và converter phải được kiểm tra.
9. **“Optional triển khai Serializable.”** Sai: Java `Optional` không triển khai `java.io.Serializable`.
10. **“Repository trả `Optional<User>` nghĩa là mọi thuộc tính của `User` phải là Optional.”** Sai: Optional bao quanh **kết quả tìm entity**, không xác định field design.
11. **“`Optional<List<T>>` tốt hơn mọi `List<T>`.”** Trong nhiều API tìm nhiều phần tử, list rỗng đã đủ; chỉ dùng Optional<List> khi có ý nghĩa phân biệt riêng.
12. **“`Optional.of(0)` và `Optional.of("")` là empty.”** Sai: cả hai present; validate nội dung riêng.
13. **“Trả empty khi DB bị timeout giúp API đơn giản.”** Che mất lỗi quan trọng; phân biệt không tìm thấy và truy vấn thất bại.
14. **“Optional có cùng identity mỗi lần empty.”** Không dựa vào identity; là value-based class.
15. **“Dùng `Optional.get()` ở mọi nơi vì field vốn có.”** Nếu field có khả năng empty, `get()` ném `NoSuchElementException`; dùng `orElse`/`orElseThrow` khi phù hợp hoặc bảo vệ invariant ở nơi tạo.
16. **“Có annotation `@Nullable` duy nhất do Java SE định nghĩa.”** Không có một chuẩn Java SE duy nhất cho tất cả công cụ; dùng annotation theo toolchain của dự án.
17. **“`Optional<T>` diễn đạt tất cả kết quả thành công/lỗi.”** Nó chỉ diễn đạt có/không giá trị, không chứa mã lỗi, nguyên nhân hoặc hành động.
18. **“Dùng Optional ở field chắc chắn nâng hiệu năng.”** Đó là một object wrapper có chi phí và ranh giới sử dụng; hiệu năng cần đo, không giả định.
19. **“Chuyển public field `String` sang `Optional<String>` không làm thay đổi API.”** Chữ ký constructor, accessor, serializer và client có thể thay đổi; cần kiểm tra tương thích.
20. **“Record có `Optional` field luôn an toàn cho data binding.”** Record constructor có thể bảo vệ invariant, nhưng framework vẫn cần hỗ trợ serialization/deserialization theo contract.

## 13. Checklist trước khi đưa Optional vào model

Khi xem một lời khai báo `Optional<T>`, đặt các câu hỏi:

1. **Đây là kết quả phương thức hay trạng thái lưu trữ?** Nếu là kết quả 0–1, Optional thường phù hợp.
2. **“Không tồn tại” có phải outcome bình thường?** Nếu là lỗi, giữ thông tin lỗi qua exception/result type.
3. **Có cần phân biệt missing, null, blank, invalid không?** Optional một tầng không biểu diễn toàn bộ các trạng thái đó.
4. **Tại sao đặt wrapper ở field thay vì accessor?** Có lý do domain cụ thể hay chỉ muốn tránh nullable?
5. **Có đang gửi object qua ORM, JSON, validation, reflection, schema generator?** Đã xác minh hỗ trợ cho Optional chưa?
6. **Ai đảm bảo bản thân Optional field/parameter không null?** Constructor, validator, method precondition hay dữ liệu framework?
7. **Tham số có đơn giản hơn khi dùng overload/default/request type không?** Cân nhắc trải nghiệm của caller.
8. **Cần 0–1 hay 0–n kết quả?** Dùng Optional cho 0–1, collection rỗng cho 0–n trong trường hợp thông thường.
9. **Đây là PATCH hay create/update đầy đủ?** Với PATCH, xác định rõ Keep/Clear/Set và cách map từ JSON.
10. **Tác động tương thích và test?** Kiểm thử null/absent/present/invalid, round-trip serialization, mapper, constructor và các client cũ.

## 14. Bài tập tự kiểm tra

1. Vì sao `Optional<User> findById(String id)` thường là ví dụ sử dụng Optional phù hợp hơn so với `Optional<String> email` làm field của một JPA entity?
2. Nếu một API nhận `Optional<String> nickname` làm tham số, caller có thể gọi với `null` không? Làm gì để giữ invariant?
3. Một phương thức trả `List<Order>` có thể trả danh sách rỗng. Khi nào cần `Optional<List<Order>>` và khi nào đây chỉ là một lớp wrapper thừa?
4. Vì sao JSON `{}` và `{"email":null}` có thể mang nghĩa khác nhau trong PATCH? Một Optional empty có đủ không?
5. Khi một record nội bộ chọn field `Optional<String>`, constructor nên kiểm tra điều gì?
6. Nếu serializer không hiểu Optional, nên suy đoán biểu diễn JSON hay đọc tài liệu và làm round-trip test?
7. Khi một field email bắt buộc được gán null do lỗi mapping, nên chuyển nó thành `Optional.empty()` hay báo invariant violation?
8. Nếu domain phân biệt người dùng bị xóa, bị khóa, không có quyền và không tìm thấy, một `Optional<User>` có đủ thông tin không?

**Gợi ý:** (1) return type 0–1 phản ánh trực tiếp outcome tìm kiếm; entity có vấn đề mapping/nullability/invariant khác. (2) có thể truyền null, dùng `Objects.requireNonNull` hoặc đổi thiết kế. (3) chỉ cần Optional<List> khi “không có danh sách” khác “danh sách rỗng”. (4) thiếu key khác xóa key; dùng presence tracking/tri-state type. (5) chính Optional container phải khác null. (6) test. (7) báo lỗi vì invariant sai. (8) không; dùng result type phong phú hơn hoặc error contract rõ.

**Kết luận:** `Optional<T>` mạnh nhất khi được dùng ở **ranh giới trả kết quả có thể vắng mặt**. Trong **field, tham số và mô hình dữ liệu**, nó có thể hợp pháp nhưng không phải lựa chọn mặc định: phải hiểu invariant, tương thích ORM/serializer, giá trị null, dữ liệu nhiều trạng thái và hợp đồng gọi API. Thay vì “bọc Optional khắp nơi”, chọn kiểu dữ liệu **diễn đạt đúng ý nghĩa** ở từng tầng.

## Tài liệu API chính thức (kiến thức còn áp dụng)

- `Optional<T>` — mô tả value-based và intended use cho return type: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html
- `Objects.requireNonNull` — bảo vệ invariant đối với tham số/field: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html
- `List` và các hợp đồng collection: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html
- `java.lang.Record` — mô hình record, constructor: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html
- `java.lang.SealedClass` / đặc tả sealed classes: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html
