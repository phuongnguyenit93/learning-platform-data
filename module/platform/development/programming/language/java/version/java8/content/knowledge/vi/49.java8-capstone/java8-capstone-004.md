# Thiết kế API kết quả vắng mặt bằng Optional trong Java

Một method tìm kiếm có thể không tìm thấy đối tượng. Nếu trả `null`, caller phải biết quy ước ngầm và nhớ kiểm tra trước khi dùng. Nếu ném exception cho mọi trường hợp không có kết quả, luồng điều khiển bình thường lại bị biến thành lỗi. **`Optional<T>` giúp biểu diễn rõ một kết quả có thể hiện diện hoặc vắng mặt ngay trong kiểu trả về của API.**

`Optional<T>` được giới thiệu từ Java 8. Nó là một container có thể chứa một giá trị khác-null hoặc rỗng. API này được thiết kế chủ yếu cho **method return type**, trong trường hợp “không có kết quả” là một khả năng bình thường và dùng `null` dễ dẫn đến lỗi. Một method trả `Optional<User>` nói rõ với caller rằng kết quả có thể không tồn tại; caller phải chọn cách xử lý trước khi lấy `User`.

Optional không tự xử lý database, không biến exception thành empty, không xác minh dữ liệu và không thay thế thiết kế domain. Nó là **hợp đồng về sự hiện diện của một giá trị**. Bài này tập trung vào cách thiết kế API, cách triển khai repository/service, cách ghép các phép biến đổi, các lỗi thường gặp và các phương thức bổ sung ở Java 9, 10, 11 trở lên. Tất cả API được giới thiệu đều còn được hỗ trợ trong JDK hiện đại.

## 1. Optional giải quyết vấn đề gì?

Giả sử repository tìm user theo ID. Nếu không tìm thấy, cách cũ thường trả `null`:

~~~java
public User findById(long id) {
    // Không có user thì trả null.
    return null;
}
~~~

Caller phải nhớ kiểm tra:

~~~java
User user = repository.findById(42L);
if (user != null) {
    System.out.println(user.getName());
}
~~~

Nếu caller quên điều kiện, lỗi `NullPointerException` có thể xuất hiện ở một dòng khác, xa nơi giá trị được tạo. API cũng không cho biết rõ việc trả `null` có phải quy ước chính thức hay là bug.

Với Optional:

~~~java
public Optional<User> findById(long id) {
    User user = lookup(id);
    return Optional.ofNullable(user);
}
~~~

Caller nhìn thấy khả năng vắng mặt ngay ở chữ ký:

~~~java
repository.findById(42L)
        .ifPresent(user -> System.out.println(user.getName()));
~~~

`Optional<User>` có hai trạng thái:

- **Present:** chứa một đối tượng `User` khác-null.
- **Empty:** không có đối tượng nào.

Không có trạng thái hợp lệ thứ ba là “biến Optional bằng null”. Một method có kiểu trả `Optional<T>` phải trả một instance Optional không-null, dù có kết quả hay không.

### 1.1. Optional là hợp đồng, không phải cơ chế chữa mọi null

Optional hữu ích khi một giá trị **có thể không tồn tại theo nghiệp vụ**:

- Tìm user theo ID có thể không tìm thấy.
- Tìm cấu hình tùy chọn có thể không được khai báo.
- Tìm cache entry có thể không có.
- Tìm giá trị đầu tiên thỏa điều kiện có thể không có.
- Tìm địa chỉ email phụ có thể không được cung cấp.

Optional không tự làm cho mọi reference trong Java an toàn null. Nếu API bắt buộc phải có một đối tượng, hãy yêu cầu caller truyền giá trị không-null và kiểm tra điều kiện đó. Nếu database ngừng hoạt động, lỗi kết nối vẫn phải được xử lý như lỗi; không nên giả vờ rằng “không tìm thấy user”.

## 2. Hợp đồng method trả Optional

Oracle mô tả Optional là một value-based class và chủ yếu dành cho method return type khi cần diễn đạt “no result”. Vì thế, một API thường có dạng:

~~~java
public Optional<User> findById(long id);
public Optional<Configuration> findConfiguration(String key);
public Optional<String> preferredDisplayName();
~~~

### 2.1. Method Optional không được trả null

Đây là lỗi thiết kế:

~~~java
public Optional<User> findById(long id) {
    if (id < 0) {
        return null; // Sai: caller nhận một Optional null.
    }
    return Optional.empty();
}
~~~

Khi đó caller vẫn phải kiểm tra `optional != null`, làm mất mục đích của API.

Quy ước đúng:

~~~java
public Optional<User> findById(long id) {
    if (id < 0) {
        return Optional.empty();
    }
    return Optional.ofNullable(databaseLookup(id));
}
~~~

Tuy nhiên, `id < 0` có thực sự là “không tìm thấy” hay là input sai? API phải quyết định theo domain. Nếu ID âm là input không hợp lệ, có thể ném `IllegalArgumentException`. `Optional.empty()` nên biểu diễn trường hợp vắng mặt được dự kiến, không phải cách gom mọi tình huống thành một kết quả rỗng.

### 2.2. Khi nào dùng Optional và khi nào ném exception?

| Tình huống | Kết quả API thường phù hợp | Vì sao |
| --- | --- | --- |
| Không có bản ghi với ID hợp lệ | `Optional.empty()` | Không tìm thấy là kết quả bình thường |
| Có bản ghi | `Optional.of(value)` | Kết quả tồn tại |
| ID đầu vào sai định dạng | `IllegalArgumentException` hoặc kiểu lỗi đầu vào đã quy định | Caller gửi dữ liệu không hợp lệ |
| Database mất kết nối | Exception hạ tầng / lỗi repository | Đây là lỗi vận hành, không phải “không có bản ghi” |
| Người dùng không đủ quyền đọc | Lỗi authorization hoặc chính sách che giấu được định nghĩa rõ | Không được vô tình biến lỗi bảo mật thành empty |
| Một phép tính không thể thực hiện | Exception hoặc kiểu kết quả domain có trạng thái lỗi | Không đồng nhất lỗi với absence |
| Danh sách truy vấn không có phần tử | Collection rỗng | Không cần `Optional<List<T>>` trong trường hợp thông thường |

Một quy tắc hữu ích: **Optional diễn đạt absence; exception diễn đạt failure**. Một API có thể dùng cả hai: trả `Optional<T>` khi không có kết quả, đồng thời ném exception khi truy vấn không thể thực hiện.

### 2.3. Đừng đổi API công khai một cách tùy tiện

Đổi chữ ký từ:

~~~java
User findById(long id);
~~~

sang:

~~~java
Optional<User> findById(long id);
~~~

là thay đổi contract và kiểu trả về. Caller cũ phải sửa source; binary compatibility cũng bị ảnh hưởng vì return type nằm trong JVM method descriptor. Với thư viện đã phát hành, nên tạo method mới hoặc thực hiện thay đổi theo chính sách versioning/major release, không coi đây là refactor nội bộ vô hại.

## 3. Tạo Optional đúng cách

Ba factory method cơ bản có từ Java 8:

| Cách tạo | Khi nào dùng | Hành vi |
| --- | --- | --- |
| `Optional.of(value)` | Đã chắc chắn value khác-null | Ném `NullPointerException` nếu value là null |
| `Optional.ofNullable(value)` | Nguồn dữ liệu có thể trả null | Null trở thành `Optional.empty()` |
| `Optional.empty()` | Không có kết quả | Tạo Optional rỗng |

### 3.1. Optional.of

~~~java
User user = new User("Lan");
Optional<User> result = Optional.of(user);
~~~

Dùng `of` khi null là vi phạm invariant và cần phát hiện ngay. Nếu truyền null, method ném `NullPointerException`; điều này giúp phát hiện bug ở boundary thay vì để một Optional không hợp lệ đi sâu vào hệ thống.

### 3.2. Optional.ofNullable

~~~java
User user = legacyDao.findUser(id); // API cũ có thể trả null.
Optional<User> result = Optional.ofNullable(user);
~~~

Đây là cách chuyển từ API cũ trả null sang contract Optional. Nếu `user` null, kết quả là empty. Nếu khác-null, Optional chứa user.

### 3.3. Optional.empty

~~~java
if (!recordExists) {
    return Optional.empty();
}
~~~

Dùng `empty()` khi đã xác định không có kết quả. Không so sánh `result == Optional.empty()` vì API không bảo đảm `empty()` luôn trả cùng một object singleton. Dùng `isPresent()`/`isEmpty()` hoặc các operation của Optional.

### 3.4. Optional không bao giờ chứa null

`Optional.ofNullable(null)` tạo empty. `Optional.of(null)` ném `NullPointerException`. Không có Optional hợp lệ nào “present nhưng value null”.

Một method mapper của `map` trả null cũng tạo Optional empty, vì kết quả được bọc như `Optional.ofNullable`. Ngược lại, mapper của `flatMap` phải trả về một Optional khác-null; trả null sẽ ném `NullPointerException`.

## 4. Các operation cốt lõi trong Java 8

`Optional<T>` cung cấp các operation giúp kiểm tra, biến đổi và chọn fallback. Nên chọn operation theo ý nghĩa thay vì gọi `get()` ngay sau khi tạo Optional.

### 4.1. isPresent và ifPresent

~~~java
Optional<User> found = repository.findById(id);

if (found.isPresent()) {
    System.out.println(found.get().getName());
}
~~~

Đoạn trên hợp lệ nhưng `get()` chỉ an toàn vì đã kiểm tra trạng thái. Nếu chỉ muốn thực hiện hành động khi có giá trị, viết gọn hơn:

~~~java
repository.findById(id)
        .ifPresent(user -> sendWelcomeMessage(user));
~~~

`ifPresent(Consumer)` gọi consumer khi có value; nếu empty thì không làm gì. Consumer không nên bị dùng để giấu exception hoặc tạo side effect khó theo dõi. Nếu caller cần một giá trị để tiếp tục pipeline, `map`/`flatMap` thường phù hợp hơn.

### 4.2. get: biết nó có thể ném exception

~~~java
User user = optional.get();
~~~

Nếu Optional empty, `get()` ném `NoSuchElementException`. Tên `get()` dễ tạo cảm giác đây là getter thông thường, trong khi nó có thể fail. Javadoc khuyến nghị ưu tiên `orElseThrow()` khi cần lấy giá trị và muốn báo rõ hành vi ném lỗi.

Trong code mới, tránh dùng `get()` như một cách bỏ qua thiết kế absence. Chỉ dùng sau một điều kiện đã chứng minh present, và cân nhắc biểu diễn luồng xử lý bằng các operation khác.

### 4.3. orElse: cung cấp giá trị mặc định

~~~java
String displayName = optionalName.orElse("Guest");
~~~

Nếu Optional present, trả giá trị bên trong; nếu empty, trả đối số `other`. Đối số có thể null theo API, nhưng thường nên dùng fallback không-null để giữ invariant của ứng dụng.

**Điểm quan trọng:** Java đánh giá đối số trước khi gọi method. Vì thế `orElse(createDefault())` gọi `createDefault()` ngay cả khi Optional đã có giá trị.

### 4.4. orElseGet: fallback được tính khi cần

~~~java
String displayName = optionalName.orElseGet(
        () -> loadDefaultDisplayName());
~~~

`Supplier` chỉ được gọi khi Optional empty. Dùng `orElseGet` khi tạo fallback tốn chi phí, có I/O hoặc có side effect mà chỉ muốn thực hiện khi thật sự thiếu giá trị.

| Biểu thức | Khi Optional present | Khi Optional empty |
| --- | --- | --- |
| `orElse(create())` | `create()` vẫn được gọi trước | Trả kết quả đã tạo |
| `orElseGet(() -> create())` | Supplier không được gọi | Gọi `create()` rồi trả kết quả |

Không thay `orElse` bằng `orElseGet` theo kiểu máy móc. Với một hằng số hoặc biểu thức rẻ, `orElse` thường dễ đọc hơn.

### 4.5. orElseThrow

Khi absence là điều kiện lỗi đối với caller:

~~~java
User user = repository.findById(id)
        .orElseThrow(() -> new UserNotFoundException(id));
~~~

Overload nhận `Supplier<? extends X>` có từ Java 8. Supplier chỉ được gọi khi Optional empty. Đây là cách thể hiện rõ điểm mà luồng xử lý chuyển từ “kết quả có thể vắng mặt” sang “caller yêu cầu bắt buộc phải có kết quả”.

Nếu exception là checked exception, method bao ngoài phải khai báo hoặc xử lý theo quy tắc Java. Nếu dùng exception không checked của domain, caller có thể bắt ở boundary phù hợp.

### 4.6. map: biến đổi giá trị bên trong

~~~java
Optional<String> name = repository.findById(id)
        .map(User::getName);
~~~

Nếu Optional empty, mapper không được gọi và kết quả vẫn empty. Nếu present, mapper được áp dụng cho value và kết quả được bọc thành Optional mới.

Dùng `map` khi hàm biến đổi trả về một giá trị thông thường `U`, ví dụ `User -> String`, `String -> Integer` hoặc `Order -> BigDecimal`.

Nếu mapper trả null, `map` tạo Optional empty. Điều này có thể hữu ích khi tích hợp API nullable cũ, nhưng không nên cố ý trả null từ mapper trong code mới vì nó làm mất thông tin nguyên nhân absence.

### 4.7. flatMap: tránh Optional lồng nhau

Giả sử `User.primaryEmail()` đã trả `Optional<String>`:

~~~java
Optional<Optional<String>> nested =
        repository.findById(id).map(User::primaryEmail);
~~~

Kết quả là Optional lồng nhau. Thường đây không phải điều caller mong muốn.

Dùng `flatMap`:

~~~java
Optional<String> email = repository.findById(id)
        .flatMap(User::primaryEmail);
~~~

`flatMap` nhận hàm biến đổi mà kết quả đã là Optional và làm phẳng một cấp. Đây là cách nối các bước tìm kiếm mà mỗi bước đều có thể không có kết quả.

**Phân biệt nhanh:**
- `map(T -> U)` tạo `Optional<U>`.
- `flatMap(T -> Optional<U>)` trả trực tiếp `Optional<U>`.

### 4.8. filter: giữ giá trị khi thỏa điều kiện

~~~java
Optional<User> activeUser = repository.findById(id)
        .filter(User::isActive);
~~~

Nếu empty, predicate không chạy. Nếu present và predicate trả true, giữ nguyên value; nếu false, kết quả empty.

`filter` hữu ích khi kiểm tra điều kiện hợp lệ trước khi tiếp tục pipeline. Đừng dùng predicate có side effect hoặc truy vấn tốn kém mà caller không nhận ra.

### 4.9. Ghép pipeline

~~~java
String emailDomain = repository.findById(id)
        .filter(User::isActive)
        .flatMap(User::primaryEmail)
        .map(String::toLowerCase)
        .map(value -> value.substring(value.indexOf('@') + 1))
        .orElse("unknown");
~~~

Pipeline có thể đọc như một chuỗi điều kiện: tìm user, chỉ giữ user active, lấy email nếu có, chuẩn hóa email, lấy domain, nếu bất kỳ bước nào không tạo giá trị thì dùng fallback. Trong production, cần bảo đảm email có format hợp lệ trước khi gọi `substring`; Optional không tự validate dữ liệu.

## 5. Optional trong thiết kế Repository và Service

Một API repository thường dùng Optional để diễn đạt “có thể không có bản ghi”:

~~~java
public interface UserRepository {
    Optional<User> findById(long id);
}
~~~

Service có thể chuyển contract này thành hành vi phù hợp use case:

~~~java
public UserProfile getProfile(long id) {
    return userRepository.findById(id)
            .map(UserProfile::from)
            .orElseThrow(() -> new UserNotFoundException(id));
}
~~~

Ở tầng repository, “không có row” có thể là empty. Ở tầng service, use case “lấy hồ sơ bắt buộc phải tồn tại” có thể chuyển empty thành domain exception. Như vậy mỗi tầng có trách nhiệm rõ ràng.

### 5.1. Không biến lỗi hạ tầng thành empty

Ví dụ một truy vấn database thất bại do connection timeout. Nếu repository bắt tất cả exception rồi trả `Optional.empty()`, caller sẽ hiểu sai rằng ID không tồn tại.

~~~java
// Không nên: mọi lỗi đều bị biến thành absence.
public Optional<User> findById(long id) {
    try {
        return Optional.ofNullable(dao.select(id));
    } catch (Exception ex) {
        return Optional.empty();
    }
}
~~~

Hãy chỉ trả empty khi truy vấn thành công và kết quả thực sự không tồn tại. Lỗi kết nối, lỗi SQL, lỗi mapping hoặc lỗi hệ thống phải đi theo error contract của repository.

### 5.2. API find và get có thể khác nhau

Một thư viện có thể cung cấp hai phương thức:

~~~java
Optional<User> findById(long id); // absence là kết quả bình thường
User getById(long id);            // không tồn tại thì ném domain exception
~~~

Hai method phải được tài liệu hóa rõ. Không đặt tên `get` nhưng lại trả Optional rồi mong caller đoán cách xử lý. Hãy chọn tên diễn đạt semantics.

### 5.3. Tách absence khỏi authorization

Nếu một user không được phép đọc bản ghi, quyết định trả empty hay lỗi authorization phải theo threat model. Một số hệ thống cố ý không tiết lộ bản ghi có tồn tại hay không; hệ thống khác cần phân biệt 403 và 404. Optional không quyết định chính sách đó. Đừng vô tình dùng empty để bỏ qua kiểm tra quyền hoặc che lỗi bảo mật.

## 6. Khi nào không nên dùng Optional?

Optional không phải wrapper mặc định cho mọi biến reference.

### 6.1. Không dùng Optional cho collection rỗng

Thay vì:

~~~java
Optional<List<User>> findAllActiveUsers();
~~~

thường nên dùng:

~~~java
List<User> findAllActiveUsers();
~~~

Trả danh sách rỗng khi không có phần tử. `Optional<List<User>>` tạo hai tầng absence: không có list và có list nhưng không có user. Nếu hai trạng thái đó thực sự mang ý nghĩa khác nhau trong domain, cần giải thích rõ; còn thông thường nó làm API khó dùng hơn.

Tương tự, `Set`, `Map`, `Stream` hoặc array thường nên có biểu diễn rỗng phù hợp thay vì `Optional` bọc quanh collection.

### 6.2. Hạn chế Optional làm tham số

Một method kiểu:

~~~java
void updateEmail(Optional<String> email);
~~~

buộc caller phải tạo Optional cho từng lời gọi và tạo thêm trạng thái “tham số Optional bị null”. Thường dễ hiểu hơn nếu dùng:
- Method riêng cho hành động có/không có giá trị.
- Overload cho hai trường hợp có semantics khác nhau.
- Một command/request object có quy tắc nullability rõ.
- Annotation nullability phù hợp nếu null thật sự là một phần contract.

Với input bắt buộc, nhận `String` và từ chối null theo contract. Với input tùy chọn, nói rõ sự khác nhau giữa “không gửi trường”, “xóa giá trị hiện tại” và “đặt giá trị mới”; một Optional parameter đơn lẻ không phải lúc nào cũng diễn đạt đủ ba trạng thái.

### 6.3. Hạn chế Optional làm field

`Optional` được thiết kế chủ yếu cho return type. Dùng làm field trong entity/DTO có thể gây vấn đề với serialization, persistence, reflection và framework binding; `Optional` không triển khai `Serializable`. Một số framework có adapter riêng, nhưng không nên giả định tất cả đều xử lý giống nhau.

Một cách phổ biến là giữ field nội bộ nullable với invariant rõ ràng, rồi expose accessor Optional:

~~~java
public final class User {
    private final String secondaryEmail; // Có thể null theo invariant nội bộ.

    public Optional<String> secondaryEmail() {
        return Optional.ofNullable(secondaryEmail);
    }
}
~~~

Đây là lựa chọn thiết kế, không phải quy tắc cứng cho mọi framework. Nếu hệ thống dùng record, ORM hoặc serializer có hỗ trợ Optional rõ ràng, hãy kiểm tra contract và behavior cụ thể trước khi dùng.

### 6.4. Không dùng Optional khi absence không thể xảy ra

Nếu method luôn trả một giá trị hợp lệ, `Optional<T>` làm caller phải xử lý một trạng thái không có ý nghĩa. Ví dụ `getCurrentVersion()` nếu contract đảm bảo luôn có version thì trả `Version` trực tiếp, không cần `Optional<Version>`.

### 6.5. Không dùng Optional để biểu diễn nhiều trạng thái domain

Nếu kết quả có ba hoặc nhiều trạng thái như `FOUND`, `NOT_FOUND`, `DISABLED`, `PENDING_REVIEW`, Optional không đủ biểu đạt. Hãy dùng một kiểu kết quả domain rõ ràng, ví dụ enum + payload hoặc sealed result type trên Java phù hợp. Optional chỉ trả lời câu hỏi “có value hay không”.

## 7. Optional và nullability trong API

Một method trả Optional phải luôn trả object Optional không-null. Nếu caller nhận `Optional<T>` mà bản thân reference lại null, đó là contract violation.

### 7.1. Đừng bọc Optional trong Optional

~~~java
Optional<Optional<User>> result;
~~~

Cấu trúc này thường biểu thị việc thiết kế pipeline chưa được làm phẳng hoặc mô hình absence bị trùng lặp. Dùng `flatMap` để nối các bước Optional; nếu có nhiều trạng thái nghiệp vụ, tạo result type có tên.

### 7.2. Chuyển đổi từ API nullable

~~~java
Optional<String> name = Optional.ofNullable(legacyObject.getName());
~~~

Đây là boundary hợp lý khi tích hợp code cũ. Không cần ép mọi method nội bộ phải trả Optional nếu contract hiện tại đã có một biểu diễn nullability được quản lý tốt. Quan trọng là tại ranh giới API phải rõ ai chịu trách nhiệm kiểm tra null.

### 7.3. Optional không thay thế annotation nullability

Trong codebase lớn, annotation như `@Nullable` và `@NonNull` có thể hỗ trợ static analysis, IDE và hợp đồng tham số/field. Optional chủ yếu biểu diễn absence ở return type. Hai công cụ giải quyết những phạm vi khác nhau và có thể cùng tồn tại.

## 8. Các lớp Optional cho kiểu primitive

Java 8 có ba lớp chuyên biệt:

- `OptionalInt`
- `OptionalLong`
- `OptionalDouble`

Chúng tránh phải biểu diễn primitive bằng `Optional<Integer>`, `Optional<Long>` hoặc `Optional<Double>` trong những API phù hợp.

~~~java
OptionalInt count = OptionalInt.of(5);
int value = count.orElse(0);

OptionalLong sequence = OptionalLong.empty();
long next = sequence.orElse(-1L);

OptionalDouble ratio = OptionalDouble.of(0.75);
double result = ratio.orElse(0.0);
~~~

Các lớp primitive có những operation tương ứng như `isPresent`, `getAsInt`, `getAsLong`, `getAsDouble`, `orElse`, `orElseGet` và `orElseThrow`. Chúng không có `ofNullable`, vì primitive không thể là null.

### 8.1. Khi nào dùng primitive Optional?

Dùng khi API thực sự có kết quả primitive tùy chọn, ví dụ tìm vị trí index có thể không tồn tại, tìm số đo có thể chưa được ghi nhận hoặc tìm timestamp/sequence có thể vắng mặt.

Không chuyển mọi số thành Optional primitive chỉ để tránh giá trị sentinel. Nếu `-1` đã là một contract domain rõ ràng và tương thích tốt, hãy cân nhắc chi phí thay đổi API. Nếu sentinel dễ nhầm với giá trị hợp lệ, Optional primitive có thể diễn đạt rõ hơn.

### 8.2. Optional<T> và boxing

`Optional<Integer>` chứa một reference `Integer`; `OptionalInt` lưu giá trị primitive và trạng thái hiện diện theo implementation. Nếu API có nhiều giá trị số và absence là một phần contract, primitive Optional giúp tránh boxing không cần thiết và làm rõ kiểu.

Không tối ưu vi mô khi chưa đo. Chọn kiểu trước hết dựa trên semantics và API ergonomics; performance cần benchmark trên workload thật.

## 9. Các phương thức bổ sung theo phiên bản Java

Optional được bổ sung từ Java 8 và có thêm operation qua các phiên bản. Không nhầm các method Java 9+ với API có sẵn khi project vẫn compile bằng Java 8.

| Method | Phiên bản | Ý nghĩa |
| --- | --- | --- |
| `empty`, `of`, `ofNullable` | Java 8 | Tạo Optional |
| `isPresent`, `get`, `ifPresent` | Java 8 | Kiểm tra/lấy/thực hiện hành động |
| `orElse`, `orElseGet`, `orElseThrow(Supplier)` | Java 8 | Fallback hoặc ném exception |
| `map`, `flatMap`, `filter` | Java 8 | Biến đổi và lọc |
| `ifPresentOrElse` | Java 9 | Nhánh present và empty |
| `or(Supplier<Optional<T>>)` | Java 9 | Cung cấp Optional thay thế khi empty |
| `stream()` | Java 9 | Chuyển Optional thành Stream 0 hoặc 1 phần tử |
| `orElseThrow()` không tham số | Java 10 | Lấy value hoặc ném `NoSuchElementException` |
| `isEmpty()` | Java 11 | Kiểm tra trạng thái empty |

### 9.1. ifPresentOrElse từ Java 9

~~~java
optionalUser.ifPresentOrElse(
        user -> System.out.println(user.getName()),
        () -> System.out.println("No user found"));
~~~

Nó làm rõ cả hai nhánh khi caller cần xử lý present và empty. Với Java 8, có thể dùng `ifPresent` hoặc `isPresent` + `else`.

### 9.2. or từ Java 9

~~~java
Optional<Config> config = readLocalConfig()
        .or(() -> readEnvironmentConfig())
        .or(() -> readDefaultConfig());
~~~

`or` nhận supplier trả về một Optional khác. Supplier chỉ được gọi khi Optional trước đó empty. Đây là cách nối nhiều nguồn fallback mà không phải tạo `Optional<Optional<T>>`.

### 9.3. stream từ Java 9

~~~java
Stream<User> users = userIds.stream()
        .map(repository::findById)
        .flatMap(Optional::stream);
~~~

`Optional.stream()` trả stream có 0 phần tử nếu empty hoặc 1 phần tử nếu present. Nó giúp chuyển `Stream<Optional<T>>` thành `Stream<T>`.

Trên Java 8, có thể viết:

~~~java
Stream<User> users = userIds.stream()
        .map(repository::findById)
        .filter(Optional::isPresent)
        .map(Optional::get);
~~~

Nếu cần source compatibility Java 8, không dùng `Optional::stream` hoặc method mới hơn.

### 9.4. orElseThrow không tham số từ Java 10

~~~java
User user = optionalUser.orElseThrow();
~~~

Nếu empty, method ném `NoSuchElementException`. Java 8 đã có overload nhận exception supplier:

~~~java
User user = optionalUser.orElseThrow(
        NoSuchElementException::new);
~~~

Với API domain, overload có supplier cho phép ném exception cụ thể và giàu ngữ cảnh hơn.

### 9.5. isEmpty từ Java 11

~~~java
if (optionalUser.isEmpty()) {
    System.out.println("No user");
}
~~~

Trên Java 8, viết `!optionalUser.isPresent()`. Không gọi `isEmpty()` trong source phải compile Java 8.

## 10. Optional trong Stream và pipeline

Optional và Stream có mục đích khác nhau:

- Optional biểu diễn tối đa một giá trị có thể vắng mặt.
- Stream biểu diễn một chuỗi 0..n phần tử và các phép xử lý lazy.

### 10.1. Tìm phần tử đầu tiên

~~~java
Optional<User> firstActive = users.stream()
        .filter(User::isActive)
        .findFirst();
~~~

`findFirst()` trả Optional vì stream có thể rỗng. `findAny()` cũng trả Optional và có thể hữu ích khi không cần phần tử đầu tiên, đặc biệt trong parallel stream.

### 10.2. Chuyển Optional thành Stream

Từ Java 9:

~~~java
Stream<Permission> permissions = optionalRole.stream()
        .flatMap(role -> role.permissions().stream());
~~~

Nếu role không có, stream đầu vào rỗng. Nếu có, các permission được phát ra. Cần phân biệt `Optional.stream()` với `Stream.of(optional)`: cách sau tạo stream chứa chính Optional object, không phải stream chứa value bên trong.

### 10.3. Không dùng Optional để thay collection

Nếu method trả nhiều kết quả, hãy trả collection/stream. Optional chỉ phù hợp cho 0 hoặc 1 value. Nếu trả `Optional<Stream<T>>`, cần lý do domain rất rõ; thông thường stream rỗng đã biểu diễn không có phần tử.

## 11. Optional với Map và nguồn dữ liệu nullable

`Map.get(key)` có thể trả null khi key không tồn tại; nếu map cho phép lưu null value, kết quả null còn có thể mang nghĩa key tồn tại nhưng value null. Khi viết:

~~~java
Optional<Value> value = Optional.ofNullable(map.get(key));
~~~

hai trạng thái “key không có” và “key có nhưng value null” bị gộp thành empty. Nếu domain cần phân biệt chúng, dùng `containsKey(key)` hoặc cấm null value trong map theo invariant.

Tương tự, `ResultSet.getString(...)` có thể trả null cho SQL NULL. `Optional.ofNullable` phù hợp nếu API cần biểu diễn giá trị cột có thể thiếu; nhưng cần tách SQL NULL, không có row và lỗi SQL thành những trường hợp đúng contract.

**Optional không phải công cụ tự động chuyển đổi ngữ nghĩa của nguồn dữ liệu.** Hãy hiểu nguồn nullable trước khi bọc.

## 12. Hiệu năng và cách dùng an toàn

Optional là object value-based. Không dùng nó làm lock:

~~~java
synchronized (Optional.empty()) {
    // Không được dùng Optional làm monitor.
}
~~~

Không so sánh identity:

~~~java
if (optional == Optional.empty()) {
    // Không đúng contract.
}
~~~

Dùng `isPresent`, `isEmpty` hoặc `equals` nếu thật sự cần so sánh giá trị. Không dựa vào `toString()` để serialize hoặc parse trạng thái; format hiển thị của nó không phải wire format.

Optional không được thiết kế để thay mọi field/parameter. Tạo rất nhiều Optional tạm trong code nóng có thể tạo overhead tùy runtime và cách escape analysis; đừng tự kết luận có vấn đề hiệu năng nếu chưa benchmark. Với primitive, cân nhắc `OptionalInt`, `OptionalLong`, `OptionalDouble`. Ưu tiên contract rõ ràng trước, sau đó đo workload thực tế.

## 13. Những lỗi thường gặp khi thiết kế API Optional

1. **Trả null thay vì Optional.empty().** Caller vẫn phải kiểm tra null và contract bị phá vỡ.
2. **Dùng Optional cho mọi getter.** Chỉ dùng khi absence thực sự có ý nghĩa; giá trị luôn có thì trả trực tiếp.
3. **Ném exception cho mọi trường hợp không tìm thấy.** Nếu absence là kết quả bình thường, Optional giúp caller xử lý tự nhiên.
4. **Biến mọi exception thành Optional.empty().** Lỗi database, network hoặc mapping không phải “không có kết quả”.
5. **Dùng Optional<List<T>> cho danh sách thường.** Collection rỗng đã diễn đạt không có phần tử.
6. **Dùng Optional làm tham số mà không có lý do.** Tạo thêm trạng thái null và khiến call site rườm rà.
7. **Dùng Optional làm field entity/DTO.** Có thể gây khó với serialization/persistence; Optional không Serializable.
8. **Gọi get() mà không kiểm tra.** Empty sẽ ném NoSuchElementException; ưu tiên pipeline hoặc orElseThrow.
9. **Dùng orElse cho fallback tốn kém.** Đối số được tính eager; dùng orElseGet khi cần lazy.
10. **Dùng map khi mapper đã trả Optional.** Tạo Optional lồng nhau; dùng flatMap.
11. **Mapper flatMap trả null.** Contract yêu cầu Optional không-null; null gây NullPointerException.
12. **Predicate/map có side effect.** Pipeline khó dự đoán và khó kiểm thử; giữ function thuần khi có thể.
13. **Dùng Optional để biểu diễn nhiều trạng thái.** Dùng result type domain nếu có nhiều outcome.
14. **Dùng Optional để che quyền truy cập.** Authorization phải được xử lý theo policy riêng.
15. **So sánh Optional.empty() bằng ==.** API không đảm bảo singleton; dùng method trạng thái.
16. **Đồng bộ hóa trên Optional.** Đây là value-based class; không dùng làm monitor.
17. **Dùng Optional.stream() trong Java 8 source.** Method này chỉ có từ Java 9.
18. **Dùng isEmpty() trong Java 8 source.** Method này chỉ có từ Java 11.
19. **Đổi return type API công khai mà không versioning.** Caller cũ có thể không compile/link được.
20. **Không tài liệu hóa semantics của empty.** Caller không biết empty là not found, chưa cấu hình hay không áp dụng.
21. **Bọc giá trị nullable nhưng không hiểu nguồn.** Có thể gộp key không tồn tại với value null hoặc SQL NULL.
22. **Dùng Optional thay nullability annotations cho mọi trường hợp.** Optional chủ yếu dành cho return type; annotation có phạm vi khác.

## 14. Chương trình Java hoàn chỉnh: OptionalApiDemo

Chương trình `OptionalApiDemo.java` dưới đây chạy trên Java 8. Nó minh họa:
- Repository trả `Optional<User>` khi tìm theo ID.
- `map` lấy tên và `filter` giữ giá trị hợp lệ.
- `flatMap` nối bước lấy email vốn cũng có thể vắng mặt.
- `isPresent` kiểm tra trạng thái.
- Khác biệt eager giữa `orElse` và lazy giữa `orElseGet`.
- `orElseThrow(Supplier)` chuyển absence thành exception có ngữ cảnh.
- `OptionalInt` biểu diễn một primitive value có thể vắng mặt.

### 14.1. Mã nguồn

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.OptionalInt;

public final class OptionalApiDemo {
    private OptionalApiDemo() {
    }

    private static final class User {
        private final int id;
        private final String name;
        private final String primaryEmail;

        private User(int id, String name, String primaryEmail) {
            this.id = id;
            this.name = name;
            this.primaryEmail = primaryEmail;
        }

        private String name() {
            return name;
        }

        private Optional<String> primaryEmail() {
            return Optional.ofNullable(primaryEmail);
        }
    }

    private static final class UserRepository {
        private final Map<Integer, User> users =
                new HashMap<Integer, User>();

        private UserRepository() {
            users.put(1, new User(1, "Lan", "lan@example.test"));
            users.put(2, new User(2, "Minh", null));
        }

        public Optional<User> findById(int id) {
            return Optional.ofNullable(users.get(id));
        }
    }

    private static String createFallback() {
        System.out.println("fallback-created");
        return "guest";
    }

    public static void main(String[] args) {
        UserRepository repository = new UserRepository();

        String name = repository.findById(1)
                .map(User::name)
                .filter(value -> !value.isEmpty())
                .orElse("unknown");
        System.out.println("name=" + name);

        String email = repository.findById(2)
                .flatMap(User::primaryEmail)
                .orElse("no-email");
        System.out.println("email=" + email);

        boolean missing = repository.findById(99).isPresent();
        System.out.println("missingUserPresent=" + missing);

        String eager = Optional.of("cached").orElse(createFallback());
        System.out.println("eager=" + eager);

        String lazy = Optional.of("cached").orElseGet(
                OptionalApiDemo::createFallback);
        System.out.println("lazy=" + lazy);

        try {
            repository.findById(99).orElseThrow(
                    () -> new NoSuchElementException("user not found"));
        } catch (NoSuchElementException ex) {
            System.out.println("notFound=" + ex.getMessage());
        }

        OptionalInt age = OptionalInt.of(25);
        System.out.println("age=" + age.orElse(0));
    }
}
~~~

### 14.2. Biên dịch và chạy

Lưu mã vào file `OptionalApiDemo.java`, sau đó chạy:

~~~bash
javac --release 8 -encoding UTF-8 -Xlint:-options OptionalApiDemo.java
java OptionalApiDemo
~~~

`--release 8` yêu cầu compiler kiểm tra API và language level Java 8 trên JDK hiện đại. `-Xlint:-options` chỉ tắt warning thông báo target release 8 đã cũ trên JDK mới; nó không thay đổi source code hoặc API được phép dùng.

### 14.3. Đầu ra đã chạy kiểm tra

~~~text
name=Lan
email=no-email
missingUserPresent=false
fallback-created
eager=cached
lazy=cached
notFound=user not found
age=25
~~~

### 14.4. Giải thích kết quả

- `name=Lan`: repository tìm thấy user 1; `map` lấy tên, `filter` giữ tên không rỗng và `orElse` nhận value hiện diện.
- `email=no-email`: user 2 tồn tại nhưng email phụ không có; `flatMap` nối Optional email và fallback được dùng.
- `missingUserPresent=false`: ID 99 không tồn tại nên repository trả empty.
- `fallback-created` xuất hiện trước `eager=cached`: đối số `createFallback()` được tính ngay khi gọi `orElse`, dù Optional có `"cached"`.
- Không có dòng `fallback-created` thứ hai trước `lazy=cached`: supplier của `orElseGet` không được gọi khi Optional present.
- `notFound=user not found`: `orElseThrow` tạo exception chỉ ở nhánh empty; chương trình bắt exception để tiếp tục.
- `age=25`: `OptionalInt` trả primitive value.

Chương trình dùng Java 8 API; không sử dụng `Optional.stream()`, `or()`, `ifPresentOrElse()`, `orElseThrow()` không tham số hoặc `isEmpty()`.

## 15. Checklist thiết kế API

- [ ] Absence có phải một kết quả bình thường của method không?
- [ ] Chữ ký có dùng `Optional<T>` cho đúng method return type?
- [ ] Method luôn trả Optional không-null?
- [ ] Khi có value, value luôn khác-null?
- [ ] Empty có semantics rõ: not found, chưa cấu hình hay không áp dụng?
- [ ] Lỗi hạ tầng và lỗi nghiệp vụ có được giữ riêng, không biến thành empty?
- [ ] Input sai có được xử lý bằng contract phù hợp?
- [ ] API collection trả collection rỗng khi không có phần tử?
- [ ] Có tránh Optional parameter/field trừ khi framework và domain có lý do rõ?
- [ ] Có tránh Optional lồng nhau bằng flatMap?
- [ ] Có chọn map/flatMap/filter đúng kiểu function?
- [ ] Có dùng orElseGet cho fallback cần lazy evaluation?
- [ ] Có dùng orElseThrow khi caller yêu cầu value bắt buộc?
- [ ] Có tránh get() không kiểm tra?
- [ ] Có dùng OptionalInt/Long/Double khi primitive absence là một phần contract?
- [ ] Có tránh so sánh identity và synchronization trên Optional?
- [ ] API công khai đã xét source/binary compatibility khi đổi return type?
- [ ] Source compatibility Java 8 có tránh method Java 9+?
- [ ] Javadoc đã giải thích điều kiện empty, nullability và exception?
- [ ] Unit/integration tests bao gồm present, empty, invalid input và infrastructure failure?

**Ghi nhớ:** Optional là cách biểu diễn một giá trị có thể vắng mặt trong kiểu trả về. Dùng `of` khi value phải khác-null, `ofNullable` khi chuyển nguồn nullable và `empty` khi absence là kết quả hợp lệ. Dùng `map`, `flatMap`, `filter`, `orElseGet` và `orElseThrow` để diễn đạt luồng xử lý. Không biến lỗi hệ thống thành empty, không bọc collection một cách máy móc và không trả null từ method Optional. API tốt phải cho caller biết rõ “không có kết quả” có nghĩa gì.

## Tài liệu chính thức

- [Oracle Java SE 26 — Optional API: factory methods, map/flatMap/filter, fallback, value-based semantics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html)
- [Oracle Java SE 26 — OptionalInt API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalInt.html)
- [Oracle Java SE 26 — OptionalLong API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalLong.html)
- [Oracle Java SE 26 — OptionalDouble API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalDouble.html)
- [Oracle Java SE 26 — Stream API: findFirst/findAny and stream pipelines](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Dev.java — Using Optionals: composition, primitive specializations and Java version additions](https://dev.java/learn/api/streams/optionals/)
- [Oracle Java API Specifications — requirements for clear public API contracts](https://www.oracle.com/java/technologies/javase/api-specifications.html)
