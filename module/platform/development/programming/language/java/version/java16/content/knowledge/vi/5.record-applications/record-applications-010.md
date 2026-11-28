# Binding qua constructor và khác biệt giữa accessor record với JavaBeans getter

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Ứng dụng record. Record được chuẩn hóa từ Java 16 và tiếp tục hữu ích trong Java hiện đại để biểu diễn dữ liệu bất biến theo giá trị. Khi framework binding dữ liệu vào record, framework phải tạo instance qua canonical constructor. Cách này khác với JavaBeans property binding truyền thống vốn thường tìm getter/setter theo quy ước tên. Bài học giải thích hai hợp đồng này, cách kiểm tra introspection và cách chọn adapter khi tích hợp với framework.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt accessor của record với getter theo quy ước JavaBeans.
- Giải thích constructor binding và vì sao record không cần constructor không tham số hoặc setter.
- Dùng record component metadata để kiểm tra tên, kiểu và accessor bằng reflection.
- Kiểm tra hành vi của JavaBeans `Introspector` và `PropertyDescriptor`.
- Nhận biết framework nào cần hỗ trợ record-aware binding và framework nào chỉ hiểu JavaBeans.
- Thiết kế adapter hoặc DTO chuyển tiếp khi tích hợp với API cũ.
- Xác định chính sách cho field thiếu, null, giá trị mặc định và validation tại thời điểm binding.

## 1. Hai cách framework đọc và tạo object

Khi framework nhận dữ liệu từ JSON, form, cấu hình hoặc request, nó phải chuyển các giá trị đầu vào thành một object Java. Có hai mô hình thường gặp.

**Constructor binding** thu thập giá trị cho các tham số constructor rồi tạo object trong một lần gọi. Record phù hợp với mô hình này vì canonical constructor nhận toàn bộ component.

**JavaBeans property binding** thường tạo object trước, sau đó đọc hoặc ghi property qua getter và setter. Mô hình này phù hợp với class có constructor không tham số và setter công khai.

Hai mô hình có thể cùng tồn tại trong một ứng dụng. Điều quan trọng là framework phải hỗ trợ đúng kiểu object mà nó đang binding.

Quy ước JavaBeans vẫn được dùng trong nhiều API introspection, công cụ giao diện và framework. Đây không phải một cơ chế đã bị loại bỏ; nó là một hợp đồng property riêng, khác với metadata của record.

### 1.1. Record được tạo qua canonical constructor

Ví dụ:

```java
import java.util.Objects;

public record AccountSettings(
        String username,
        boolean enabled,
        int retryLimit
) {
    public AccountSettings(
            String username,
            boolean enabled,
            int retryLimit
    ) {
        username = Objects.requireNonNull(username, "username").strip();
        if (username.isEmpty() || retryLimit < 0) {
            throw new IllegalArgumentException("Invalid account settings");
        }
        this.username = username;
        this.enabled = enabled;
        this.retryLimit = retryLimit;
    }
}
```

Canonical constructor nhận các tham số theo đúng thứ tự và kiểu component đã khai báo. Java tự sinh constructor này nếu ta không khai báo constructor tường minh. Framework record-aware đọc tên và kiểu component, lấy các giá trị tương ứng rồi gọi constructor để tạo instance.

Không cần setter để gán từng component sau khi object được tạo. Khi constructor kết thúc, các component đã có giá trị và không thể được gán lại.

### 1.2. JavaBeans thường dùng constructor và setter

Một JavaBean truyền thống có thể được viết:

```java
public class AccountSettingsBean {
    private String username;
    private boolean enabled;
    private int retryLimit;

    public AccountSettingsBean() {}

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getRetryLimit() {
        return retryLimit;
    }

    public void setRetryLimit(int retryLimit) {
        this.retryLimit = retryLimit;
    }
}
```

Framework hỗ trợ JavaBeans có thể tạo instance bằng constructor không tham số rồi gọi setter cho từng property. Object có thể tồn tại ở trạng thái chưa được điền đủ dữ liệu trong quá trình binding.

Record không được thiết kế theo quy trình đó. Nếu một thư viện chỉ tìm constructor không tham số và setter, nó có thể không bind được record dù record có accessor công khai.

## 2. Accessor của record không phải JavaBeans getter

Khai báo:

```java
public record UserProfile(
        String displayName,
        boolean active
) {}
```

tạo ra hai accessor:

- `displayName()` trả về giá trị component `displayName`.
- `active()` trả về giá trị component `active`.

Các phương thức này không có tiền tố `get` hoặc `is`. Record không tự sinh `getDisplayName()` hay `isActive()`.

Theo quy ước JavaBeans phổ biến:

| Loại property | Getter JavaBeans | Setter JavaBeans |
|---|---|---|
| `String displayName` | `getDisplayName()` | `setDisplayName(String)` |
| `boolean active` | `isActive()` | `setActive(boolean)` |
| `int retryLimit` | `getRetryLimit()` | `setRetryLimit(int)` |

Với record, accessor luôn mang đúng tên component và không có tiền tố. Component kiểu boolean cũng dùng `active()`, không tự đổi thành `isActive()`.

### 2.1. Gọi accessor trực tiếp

Khi dùng code Java thông thường:

```java
UserProfile profile = new UserProfile("An", true);

String name = profile.displayName();
boolean active = profile.active();
```

Đây là cách truy cập chuẩn của record. Method reference cũng dùng tên accessor:

```java
import java.util.List;

List<UserProfile> profiles = List.of(
        new UserProfile("An", true),
        new UserProfile("Bình", false)
);

List<String> names = profiles.stream()
        .map(UserProfile::displayName)
        .toList();
```

Không viết `UserProfile::getDisplayName` nếu record không tự khai báo phương thức đó. Đây là khác biệt về tên phương thức và hợp đồng introspection, không phải khác biệt về khả năng đọc component.

### 2.2. Có thể tự khai báo getter theo JavaBeans không?

Record có thể khai báo thêm phương thức thông thường nếu không vi phạm quy tắc của record:

```java
public record UserProfile(String displayName, boolean active) {
    public String getDisplayName() {
        return displayName;
    }

    public boolean isActive() {
        return active;
    }
}
```

Sau khi thêm các phương thức này, code JavaBeans có thể nhận diện property tương ứng qua getter. Tuy nhiên, các phương thức đó là API do ta tự viết; Java không tự sinh chúng.

Chỉ thêm getter tương thích khi có một tích hợp cụ thể yêu cầu. Không nên thêm hàng loạt getter chỉ để biến mọi record thành JavaBean, vì điều đó tạo hai cách truy cập cho cùng dữ liệu và có thể gây nhầm lẫn trong code.

## 3. JavaBeans Introspector nhìn thấy gì?

JDK cung cấp `java.beans.Introspector` để khám phá property theo quy ước JavaBeans. Công cụ này tìm các phương thức getter/setter theo tên, ví dụ `getName()`, `isEnabled()` và `setName(...)`.

Nó không tự xem mọi phương thức không tham số là getter. Vì vậy, accessor `name()` của record không tự động trở thành JavaBeans property `name`.

Ví dụ record:

```java
record UserRecord(String name, boolean enabled) {}
```

Kiểm tra property descriptor:

```java
import java.beans.BeanInfo;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.util.Arrays;

BeanInfo info = Introspector.getBeanInfo(UserRecord.class, Object.class);

String[] properties = Arrays.stream(info.getPropertyDescriptors())
        .map(PropertyDescriptor::getName)
        .toArray(String[]::new);

System.out.println(Arrays.toString(properties));
```

Với record không khai báo getter theo JavaBeans, danh sách không có `name` hoặc `enabled`. Tham số `Object.class` yêu cầu Introspector dừng trước lớp `Object`, tránh property `class` được kế thừa từ `getClass()`.

So sánh với JavaBean:

```java
import java.beans.BeanInfo;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.util.Arrays;

BeanInfo info = Introspector.getBeanInfo(AccountSettingsBean.class, Object.class);

Arrays.stream(info.getPropertyDescriptors())
        .map(PropertyDescriptor::getName)
        .forEach(System.out::println);
```

Với class có `getUsername()`, `isEnabled()` và `getRetryLimit()`, Introspector nhận diện các property tương ứng. Nó có thể nhận diện property chỉ đọc nếu có getter mà không có setter; setter cho phép ghi property.

### 3.1. PropertyDescriptor mô tả getter và setter

`PropertyDescriptor` giữ metadata về tên property, phương thức đọc và phương thức ghi. Có thể kiểm tra:

```java
for (PropertyDescriptor descriptor : info.getPropertyDescriptors()) {
    System.out.println("name = " + descriptor.getName());
    System.out.println("read = " + descriptor.getReadMethod());
    System.out.println("write = " + descriptor.getWriteMethod());
}
```

Với JavaBean mutable, property có thể có cả read method và write method. Với record thuần, JavaBeans Introspector không tự tạo descriptor cho accessor record theo tên component, vì accessor không tuân theo quy ước `getX()`/`isX()`.

Điều này không có nghĩa record thiếu metadata. Record có một mô hình metadata riêng dành cho record component, được trình bày ở phần tiếp theo.

## 4. Record component có metadata riêng trong Java

Từ Java 16, reflection API cung cấp `Class.isRecord()` và `Class.getRecordComponents()` để kiểm tra record và đọc danh sách component.

Ví dụ:

```java
import java.lang.reflect.RecordComponent;

Class<UserRecord> type = UserRecord.class;

if (type.isRecord()) {
    for (RecordComponent component : type.getRecordComponents()) {
        System.out.println("name = " + component.getName());
        System.out.println("type = " + component.getType().getTypeName());
        System.out.println("accessor = " + component.getAccessor());
    }
}
```

Với `UserRecord(String name, boolean enabled)`, metadata cho biết:

| Component | Kiểu | Accessor |
|---|---|---|
| `name` | `String` | `name()` |
| `enabled` | `boolean` | `enabled()` |

Framework record-aware có thể dùng metadata này để liên kết tên property đầu vào với component, sau đó gọi canonical constructor. Nó không cần suy ra property từ quy tắc getter JavaBeans.

### 4.1. Tên và thứ tự component là một phần cấu trúc record

Record component có thứ tự khai báo xác định. Canonical constructor nhận tham số theo thứ tự đó. Khi viết binder thủ công, phải truyền đúng thứ tự và đúng kiểu:

```java
UserRecord user = new UserRecord("An", true);
```

Không nên tự viết binder tổng quát bằng cách dựa vào thứ tự của một `Map`, vì thứ tự entry của map có thể không phải thứ tự component mà constructor yêu cầu. Hãy ánh xạ theo tên component hoặc tạo lời gọi constructor rõ ràng.

### 4.2. Kiểm tra canonical constructor bằng reflection

Có thể lấy danh sách kiểu component rồi tìm constructor tương ứng:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

RecordComponent[] components = UserRecord.class.getRecordComponents();

Class<?>[] parameterTypes = Arrays.stream(components)
        .map(RecordComponent::getType)
        .toArray(Class<?>[]::new);

Constructor<UserRecord> canonical =
        UserRecord.class.getDeclaredConstructor(parameterTypes);
```

Đoạn code minh họa cách xác định canonical constructor. Trong ứng dụng thông thường, hãy để framework hỗ trợ record thực hiện việc binding; không cần tự xây một reflection binder nếu không có yêu cầu cụ thể.

## 5. Constructor binding bảo vệ invariant như thế nào?

Record có thể xác thực dữ liệu ngay trong compact constructor. Mọi đường tạo instance đều phải đi qua constructor, bao gồm code ứng dụng và framework binding record-aware.

Ví dụ:

```java
import java.util.Objects;

public record ServerSettings(
        String host,
        int port,
        int connectionLimit
) {
    public ServerSettings {
        Objects.requireNonNull(host, "host");
        host = host.strip();

        if (host.isEmpty()) {
            throw new IllegalArgumentException("host must not be blank");
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("port is out of range");
        }
        if (connectionLimit <= 0) {
            throw new IllegalArgumentException("connectionLimit must be positive");
        }
    }
}
```

Khi binder thu thập giá trị và gọi canonical constructor, các điều kiện trên được thực thi. Không có giai đoạn setter nào cho phép object tồn tại lâu dài với `port` không hợp lệ rồi mới được sửa sau.

Đây là lợi ích quan trọng của constructor binding: binder quyết định giá trị cho từng component (từ dữ liệu, giá trị mặc định hoặc quy tắc binding), sau đó object chỉ được tạo nếu constructor chấp nhận các giá trị đó.

### 5.1. Binding từ cấu hình bằng constructor

Ví dụ chuyển dữ liệu cấu hình đã đọc thành record:

```java
import java.time.Duration;
import java.util.Objects;

public record ClientSettings(
        String endpoint,
        Duration timeout,
        int maxAttempts
) {
    public ClientSettings {
        Objects.requireNonNull(endpoint, "endpoint");
        Objects.requireNonNull(timeout, "timeout");
        endpoint = endpoint.strip();
        if (endpoint.isEmpty() || timeout.isNegative() || timeout.isZero()
                || maxAttempts <= 0) {
            throw new IllegalArgumentException("Invalid client settings");
        }
    }
}
```

Binder tường minh:

```java
import java.time.Duration;
import java.util.Map;

public final class ClientSettingsBinder {
    private ClientSettingsBinder() {}

    public static ClientSettings bind(Map<String, String> values) {
        String endpoint = values.get("endpoint");
        Duration timeout = Duration.parse(
                values.getOrDefault("timeout", "PT5S"));
        int maxAttempts = Integer.parseInt(
                values.getOrDefault("maxAttempts", "3"));

        return new ClientSettings(endpoint, timeout, maxAttempts);
    }
}
```

Đây là binder tường minh để minh họa luồng dữ liệu: đọc các giá trị, chuyển kiểu và gọi constructor. Binder thực tế của framework có thể hỗ trợ nested property, placeholder, converter, annotation và thông báo lỗi chi tiết hơn.

Trong ứng dụng thực tế, `ClientSettings` nên có compact constructor để kiểm tra `endpoint`, `timeout` và `maxAttempts`. Ví dụ tập trung vào cách tạo record từ dữ liệu đã được chuyển đổi.

### 5.2. Field thiếu, null và giá trị mặc định

Constructor binding không tự quy định một chính sách duy nhất cho field thiếu hoặc null. Hành vi phụ thuộc binder và kiểu component:

- Component tham chiếu có thể nhận null nếu binder cho phép.
- Component primitive có thể nhận giá trị mặc định như `0` hoặc `false` nếu binder không phân biệt trạng thái thiếu.
- Một số binder yêu cầu property bắt buộc hoặc cung cấp giá trị mặc định theo cấu hình.
- Constructor có thể từ chối dữ liệu thiếu hoặc null bằng validation.

Nếu cần phân biệt “không được cung cấp” với “được cung cấp nhưng rỗng”, kiểu wrapper như `Integer` hoặc `Boolean` có thể giữ thêm thông tin so với primitive. Với API patch, cần thiết kế rõ ý nghĩa của missing, null và giá trị cụ thể.

Đừng giả định mọi framework có cùng quy tắc. Hãy kiểm tra tài liệu và viết test cho binder đang dùng.

## 6. Framework phải hỗ trợ record-aware binding

Một framework có thể hỗ trợ constructor binding cho một số loại class nhưng không tự động hiểu record component. Khi đánh giá framework hoặc thư viện, hãy kiểm tra:

1. Framework có nhận diện `Class.isRecord()` hoặc record component metadata không?
2. Framework có chọn canonical constructor làm constructor tạo object không?
3. Framework ánh xạ tên property vào đúng component như thế nào?
4. Có hỗ trợ annotation trên record component hoặc constructor parameter không?
5. Converter có xử lý được kiểu component như `LocalDate`, enum, nested record và collection không?
6. Validation có chạy sau hoặc trong quá trình binding không?
7. Missing/null/default được xử lý theo hợp đồng nào?

Với thư viện JSON, khả năng record support phụ thuộc phiên bản thư viện thực tế được chạy. Với framework cấu hình hoặc web binding, hỗ trợ có thể phụ thuộc module và phiên bản framework. Không suy luận rằng framework hiểu record chỉ vì nó hỗ trợ JavaBean.

### 6.1. Binding qua constructor không đồng nghĩa framework dùng JavaBeans getter

Một framework có thể tạo record qua canonical constructor nhưng vẫn gọi accessor `name()` khi serialize hoặc khi đọc giá trị sau đó. Đây là hai hoạt động khác nhau:

- **Deserialization/binding:** lấy dữ liệu đầu vào và tạo object qua constructor.
- **Serialization/read access:** đọc component qua accessor.
- **JavaBeans introspection:** tìm property qua quy ước getter/setter.

Một thư viện record-aware có thể hỗ trợ hai hoạt động đầu mà không dùng JavaBeans introspector. Vì vậy, đừng dùng kết quả `Introspector` để kết luận mọi thư viện đều không thể bind record.

## 7. Khi cần tích hợp với JavaBeans API

Nếu một thư viện chỉ nhận JavaBeans property, có một số lựa chọn phù hợp.

### 7.1. Dùng adapter JavaBean ở ranh giới

Giữ record làm dữ liệu nội bộ và tạo adapter có getter/setter cho thư viện yêu cầu JavaBeans:

```java
public final class AccountSettingsBeanAdapter {
    private String username;
    private boolean enabled;

    public AccountSettingsBeanAdapter() {}

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public AccountSettings toRecord() {
        return new AccountSettings(username, enabled, 3);
    }
}
```

Ví dụ trên giả định `AccountSettings` là record đã khai báo ở phần đầu. Adapter là kiểu mutable để tương thích với API yêu cầu JavaBeans; record vẫn giữ hợp đồng bất biến của nó. Khi chuyển đổi, constructor của record kiểm tra invariant nếu đã được định nghĩa.

Không để adapter mutable lan sâu vào mô hình miền nếu chỉ một thư viện tích hợp cần nó.

### 7.2. Dùng DTO class riêng cho giao thức cũ

Nếu framework yêu cầu no-args constructor, setter, annotation hoặc lifecycle riêng, một DTO class có thể là lựa chọn phù hợp. Chuyển DTO sang record hoặc domain value object ngay tại ranh giới ứng dụng.

Mẫu luồng:

```text
Dữ liệu bên ngoài
    -> JavaBeans DTO / adapter
    -> kiểm tra và chuyển đổi
    -> record hoặc domain value object
    -> xử lý nghiệp vụ
```

Không bắt buộc mọi lớp trong ứng dụng đều phải là record. Chọn kiểu dữ liệu theo hợp đồng mà từng ranh giới cần.

### 7.3. Tự khai báo getter trên record

Nếu tích hợp chỉ cần getter để đọc dữ liệu và không cần setter, record có thể tự khai báo phương thức như `getUsername()` hoặc `isEnabled()`. Đây là cách nhỏ gọn nhưng không giải quyết yêu cầu framework cần constructor không tham số hoặc setter để ghi property.

Hãy xác định framework cần đọc hay cần cả ghi. Thêm getter chỉ xử lý được yêu cầu đọc theo JavaBeans; nó không biến record thành JavaBean mutable đầy đủ.

## 8. Validation và lỗi binding

Lỗi binding có thể xảy ra trước khi constructor được gọi hoặc trong lúc constructor kiểm tra invariant:

| Loại lỗi | Ví dụ | Nơi nên xử lý |
|---|---|---|
| Không tìm thấy component/property | Tên đầu vào sai hoặc binder không hiểu record | Cấu hình mapping/framework |
| Không chuyển đổi được kiểu | Chuỗi `"abc"` cho component `int` | Converter/binder |
| Field bắt buộc bị thiếu | Không có `host` | Chính sách required/default |
| Giá trị null không hợp lệ | `host == null` | Constructor hoặc validator |
| Vi phạm invariant | `port` ngoài khoảng cho phép | Canonical constructor |
| Property không biết | Client gửi field ngoài DTO | Chính sách unknown property |

Không nên nuốt tất cả lỗi rồi tạo record với giá trị mặc định tùy tiện. Thông báo lỗi nên chỉ ra property nào không hợp lệ, nhưng tránh đưa dữ liệu nhạy cảm hoặc nội dung request đầy đủ vào log.

### 8.1. Validation annotation cần được gọi bởi framework

Annotation như `@NotNull`, `@NotBlank`, `@Min` có thể mô tả ràng buộc trên record component nếu Bean Validation provider hỗ trợ target tương ứng. Tuy nhiên, việc framework đọc annotation và thực thi validator là một bước riêng với constructor binding.

Hãy kiểm tra rằng framework thực sự kích hoạt validation ở ranh giới phù hợp. Canonical constructor vẫn hữu ích để bảo vệ invariant cốt lõi ngay cả khi validator bên ngoài chưa được gọi.

## 9. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế | Cách xử lý |
|---|---|---|
| Accessor `name()` là getter JavaBeans `getName()` | Hai tên thuộc hai quy ước khác nhau | Dùng accessor record hoặc adapter |
| Record có setter tự động | Record không sinh setter | Tạo instance mới khi cần thay đổi |
| Framework hỗ trợ JavaBean thì chắc chắn hỗ trợ record | Binding có thể phụ thuộc getter/setter hoặc no-args constructor | Kiểm tra record-aware constructor binding |
| Introspector không thấy property nghĩa là record không có metadata | Record có `RecordComponent` metadata riêng | Dùng `getRecordComponents()` |
| Constructor binding luôn tự validate annotation | Validation là bước riêng của framework | Kiểm tra cấu hình validator |
| Field thiếu luôn giống null | Hành vi tùy binder và kiểu component | Test missing, null, default riêng |
| Thêm getter là đủ cho mọi framework | Framework có thể còn yêu cầu setter/no-args constructor | Dùng DTO/adapter phù hợp |
| Thứ tự Map đầu vào luôn là thứ tự constructor | Map có thể không bảo đảm thứ tự | Ánh xạ theo tên component |

## 10. Checklist tích hợp

Trước khi dùng record trong một hệ thống binding, hãy kiểm tra:

1. Framework đang dùng constructor binding hay JavaBeans property binding?
2. Framework có hỗ trợ record component metadata không?
3. Canonical constructor nào sẽ được gọi?
4. Accessor record có bị nhầm với getter JavaBeans không?
5. Tên property đầu vào có khớp tên component hoặc annotation không?
6. Field thiếu, null, primitive default và giá trị mặc định được xử lý thế nào?
7. Constructor có kiểm tra invariant quan trọng không?
8. Validation annotation có thực sự được thực thi không?
9. Có cần adapter hoặc DTO JavaBeans ở ranh giới không?
10. Có test cho cả binding thành công và lỗi mapping không?

## 11. Bài tập vận dụng

**Bài 1 — So sánh introspection:** Tạo `UserRecord(String name, boolean active)` và một JavaBean có `getName()`/`isActive()`. Dùng `Introspector.getBeanInfo` để liệt kê property descriptor của cả hai. Giải thích vì sao kết quả khác nhau.

**Bài 2 — Record component metadata:** Dùng `Class.isRecord()` và `getRecordComponents()` để in tên, kiểu và accessor của từng component. Từ metadata, tìm canonical constructor tương ứng.

**Bài 3 — Constructor binding:** Tạo `ServerSettings(host, port, connectionLimit)` với compact constructor xác thực dữ liệu. Viết binder tường minh từ `Map<String, String>` và kiểm tra trường thiếu, null, sai kiểu.

**Bài 4 — Adapter JavaBeans:** Tạo adapter có getter/setter cho một thư viện giả định chỉ hiểu JavaBeans. Viết phương thức chuyển adapter thành record và chứng minh invariant vẫn được kiểm tra ở constructor record.

**Bài 5 — Kiểm tra framework:** Chọn một binder đang dùng trong ứng dụng. Xác minh nó có nhận diện record component và gọi canonical constructor không. Viết test cho nested component, property thiếu và giá trị null.

---

**Ghi nhớ:** Record dùng accessor theo tên component và được tạo qua canonical constructor. JavaBeans dùng quy ước getter/setter như `getName()`, `isActive()` và `setName(...)`. Hai mô hình đều còn hữu ích nhưng có hợp đồng khác nhau. Hãy dùng record-aware constructor binding khi framework hỗ trợ; nếu một API chỉ hiểu JavaBeans, đặt adapter hoặc DTO tương thích ở ranh giới và chuyển đổi sang record sau khi kiểm tra dữ liệu.
