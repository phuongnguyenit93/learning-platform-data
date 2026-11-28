# Constructor, factory và cách thiết kế tránh sửa sau khởi tạo

Một đối tượng có tính toàn vẹn tốt nên hoàn thành việc thiết lập trạng thái bắt buộc ngay trong quá trình tạo. Các trường `final` giúp biểu đạt rằng tham chiếu của trường được gán một lần trong constructor hoặc bộ khởi tạo, sau đó không bị thay thế. Constructor, static factory và builder là những công cụ để tạo đối tượng đã hợp lệ trước khi công bố cho phần còn lại của chương trình.

Chủ đề này trở nên quan trọng hơn từ JDK 26. JEP 500 bắt đầu cảnh báo khi mã dùng deep reflection để sửa trường `final` sau khởi tạo. Cảnh báo này chuẩn bị cho giai đoạn sau, khi việc sửa trái phép sẽ bị từ chối mặc định. Thiết kế constructor và factory đúng cách giúp ứng dụng không phụ thuộc vào khả năng phá vỡ tính `final` của reflection.

## 1. `final` bảo vệ điều gì?

Với trường instance `final`, Java yêu cầu trường được gán trong constructor hoặc bộ khởi tạo của lớp và không thể được gán lại bằng mã Java thông thường sau khi constructor hoàn tất. Trường `static final` được gán trong khai báo hoặc static initializer. Đây là quy tắc của ngôn ngữ, áp dụng cho mã nguồn Java bình thường.

`final` bảo vệ tham chiếu hoặc giá trị của trường, không tự làm cho toàn bộ object graph trở thành bất biến:

```java
import java.util.List;

final class User {
    private final List<String> roles;

    User(List<String> roles) {
        this.roles = roles;
    }

    List<String> roles() {
        return roles;
    }
}
```

Tham chiếu `roles` không thể được gán sang một list khác sau constructor, nhưng list ban đầu vẫn có thể bị sửa thông qua tham chiếu bên ngoài hoặc từ giá trị trả về bởi `roles()`. Muốn tạo snapshot bất biến, cần sao chép dữ liệu đầu vào và không để lộ cấu trúc mutable.

Trường `final` còn có ngữ nghĩa khởi tạo an toàn trong Java Memory Model. Khi constructor kết thúc bình thường và `this` không bị công bố ra ngoài trước khi khởi tạo hoàn tất, thread khác có thể quan sát giá trị đã thiết lập của các trường `final` khi nhận được tham chiếu đến đối tượng. Đây không phải lý do để bỏ qua safe publication hoặc đồng bộ hóa đối với trạng thái mutable được thay đổi sau constructor.

## 2. Constructor phải tạo ra một trạng thái hợp lệ

Constructor là nơi phù hợp để:

- Kiểm tra các tham số bắt buộc và từ chối dữ liệu không hợp lệ.
- Chuẩn hóa dữ liệu đầu vào trước khi gán.
- Tạo bản sao phòng vệ cho collection, map hoặc mảng mutable.
- Gán tất cả trường `final` để đối tượng không có trạng thái nửa khởi tạo.

Ví dụ:

```java
import java.util.Collection;
import java.util.Objects;
import java.util.Set;

public final class AccessPolicy {
    private final String tenantId;
    private final Set<String> permissions;

    public AccessPolicy(String tenantId, Collection<String> permissions) {
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
        if (tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId must not be blank");
        }
        this.permissions = Set.copyOf(
                Objects.requireNonNull(permissions, "permissions"));
    }

    public String tenantId() {
        return tenantId;
    }

    public Set<String> permissions() {
        return permissions;
    }
}
```

`Set.copyOf` tạo snapshot không sửa đổi được và không giữ lại collection mutable do caller truyền vào. Nếu caller sửa collection gốc sau constructor, `AccessPolicy` không thay đổi. `Set.copyOf` là bản sao nông: nếu phần tử bên trong là đối tượng mutable, các đối tượng đó vẫn có thể thay đổi. Vì vậy, kiểu phần tử cũng nên bất biến hoặc cần được sao chép riêng.

Hãy kiểm tra tham số trước khi gán nếu việc kiểm tra có thể thất bại. Điều này giúp constructor không để lại một đối tượng đã thoát ra ngoài nhưng mới chỉ được gán một phần. Nếu constructor ném exception, đối tượng không được trả về cho caller như một instance hợp lệ.

## 3. Static factory tạo đối tượng hoàn chỉnh

Static factory là phương thức tĩnh trả về một instance đã được xây dựng. Nó có thể đặt tên theo ý nghĩa nghiệp vụ, kiểm tra dữ liệu, chọn implementation hoặc trả về instance dùng chung. Factory không cần tạo một đối tượng rồi dùng reflection hay setter để điền các trường `final`.

```java
import java.util.Collection;
import java.util.Objects;
import java.util.Set;

public final class AccessPolicy {
    private final String tenantId;
    private final Set<String> permissions;

    private AccessPolicy(String tenantId, Collection<String> permissions) {
        Objects.requireNonNull(tenantId, "tenantId");
        if (tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId must not be blank");
        }
        this.tenantId = tenantId;
        this.permissions = Set.copyOf(permissions);
    }

    public static AccessPolicy of(
            String tenantId,
            Collection<String> permissions) {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(permissions, "permissions");

        if (tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId must not be blank");
        }
        return new AccessPolicy(tenantId, permissions);
    }
}
```

Factory `of(...)` thể hiện rõ cách tạo một policy từ dữ liệu đầu vào. Constructor private giữ quyền kiểm soát việc tạo instance trong lớp. Đối tượng được trả về đã có đầy đủ trường bắt buộc.

Một factory có thể đọc cấu hình, phân tích dữ liệu hoặc chọn implementation trước khi gọi constructor. Hãy phân biệt bước chuẩn bị dữ liệu với việc sửa trạng thái sau khi đối tượng đã được công bố. Nếu đối tượng cần được đăng ký với event bus hoặc registry, có thể tạo instance hoàn chỉnh trước, sau đó mới đăng ký nó:

```java
import java.util.Objects;

public final class PriceListener {
    private final PricingRules rules;

    private PriceListener(PricingRules rules) {
        this.rules = Objects.requireNonNull(rules);
    }

    public static PriceListener register(
            PricingRules rules,
            EventBus eventBus) {
        PriceListener listener = new PriceListener(rules);
        eventBus.register(listener); // Constructor đã hoàn tất.
        return listener;
    }
}
```

Nếu đăng ký thất bại, factory cần xử lý việc thu hồi đăng ký hoặc tài nguyên đã tạo theo hợp đồng của `EventBus`. Không để constructor gọi callback, khởi chạy thread hoặc đăng ký `this` khi các trường của đối tượng còn chưa được thiết lập xong.

## 4. Builder cho đối tượng có nhiều tùy chọn

Khi đối tượng có nhiều tham số tùy chọn, builder giúp việc gọi dễ đọc hơn. Builder có thể mutable trong giai đoạn cấu hình; đối tượng kết quả vẫn phải được tạo hoàn chỉnh trong `build()`. Builder không nên tiếp tục chia sẻ collection mutable của nó với instance đã tạo.

```java
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class ReportOptions {
    private final Path output;
    private final List<String> columns;

    private ReportOptions(Builder builder) {
        this.output = Objects.requireNonNull(builder.output, "output");
        this.columns = List.copyOf(builder.columns);
    }

    public static Builder builder() {
        return new Builder();
    }

    public Path output() {
        return output;
    }

    public List<String> columns() {
        return columns;
    }

    public static final class Builder {
        private Path output;
        private final List<String> columns = new ArrayList<>();

        public Builder output(Path output) {
            this.output = output;
            return this;
        }

        public Builder addColumn(String column) {
            columns.add(Objects.requireNonNull(column));
            return this;
        }

        public ReportOptions build() {
            if (columns.isEmpty()) {
                throw new IllegalStateException("At least one column is required");
            }
            return new ReportOptions(this);
        }
    }
}
```

`ReportOptions` chỉ nhận snapshot từ builder qua `List.copyOf`. Sau khi `build()` trả về, các lần gọi `addColumn()` tiếp theo trên builder không làm thay đổi đối tượng đã tạo. Có thể gọi `build()` nhiều lần để tạo nhiều snapshot khác nhau.

Builder không phải lý do để thêm setter vào đối tượng kết quả. Giữ các setter trong builder; giữ các trường của instance cuối cùng là `private final`.

## 5. Sao chép phòng vệ cho collection và mảng

Các API collection bất biến của JDK hữu ích khi tạo snapshot:

| Dữ liệu đầu vào | Cách tạo snapshot | Lưu ý |
|---|---|---|
| `List<T>` | `List.copyOf(input)` | Collection kết quả không sửa đổi được; phần tử mutable vẫn có thể thay đổi |
| `Set<T>` | `Set.copyOf(input)` | Không giữ collection gốc; thứ tự duyệt không nên được dùng như hợp đồng |
| `Map<K,V>` | `Map.copyOf(input)` | Bản sao nông cả khóa và giá trị; không chấp nhận null key/value |
| Mảng | `input.clone()` | Cần clone khi nhận vào và khi trả ra nếu muốn bảo vệ cả hai chiều |
| Ngày giờ | Ưu tiên `Instant`, `LocalDate`, `Duration` | Tránh giữ các kiểu mutable cũ như `Date` nếu không cần tương thích |

Ví dụ với mảng:

```java
import java.util.Objects;

public final class KeyMaterial {
    private final byte[] encoded;

    public KeyMaterial(byte[] encoded) {
        this.encoded = Objects.requireNonNull(encoded).clone();
    }

    public byte[] encoded() {
        return encoded.clone();
    }
}
```

Clone ngăn caller sửa mảng nội bộ thông qua mảng gốc hoặc mảng trả về. Với dữ liệu bí mật, sao chép tạo thêm bản sao trong bộ nhớ; cần thiết kế việc xóa dữ liệu nhạy cảm cẩn thận và không log nội dung. Nếu dùng một kiểu `SecretKey` hoặc API quản lý khóa chuyên dụng, ưu tiên hợp đồng của API đó thay vì tự giữ bản sao byte array không kiểm soát.

Một wrapper `Collections.unmodifiableList(input)` chỉ chặn sửa qua wrapper; nếu caller vẫn giữ `input`, họ vẫn có thể thay đổi nội dung phía sau wrapper. Để tạo snapshot, dùng `List.copyOf(input)` hoặc sao chép trước rồi mới bọc.

## 6. Tránh để `this` thoát khỏi constructor

Một đối tượng không nên được công bố cho code khác trước khi constructor hoàn tất. Những trường hợp dễ gây lỗi:

- Gọi phương thức có thể override từ constructor.
- Đăng ký `this` vào listener, event bus hoặc registry.
- Truyền `this` cho callback, executor hoặc thread mới.
- Khởi chạy thread có thể đọc đối tượng trước khi các trường được thiết lập xong.

Ví dụ không nên làm:

```java
import java.util.Objects;

public final class CacheRefresher {
    private final Config config;

    public CacheRefresher(Config config, EventBus bus) {
        bus.register(this); // this thoát ra trước khi constructor kết thúc.
        this.config = Objects.requireNonNull(config);
    }
}
```

Sửa thiết kế bằng cách gán trường trước và đăng ký sau khi constructor đã trả về, thường thông qua factory hoặc lifecycle owner:

```java
import java.util.Objects;

public final class CacheRefresher {
    private final Config config;

    private CacheRefresher(Config config) {
        this.config = Objects.requireNonNull(config);
    }

    public static CacheRefresher create(Config config, EventBus bus) {
        CacheRefresher refresher = new CacheRefresher(config);
        bus.register(refresher);
        return refresher;
    }
}
```

Factory không loại bỏ mọi vấn đề đồng thời, nhưng nó tạo ranh giới rõ ràng: instance chỉ được chia sẻ sau khi constructor hoàn tất. Nếu có thao tác khởi động hoặc đóng tài nguyên, quản lý chúng bằng lifecycle API rõ ràng; không dùng reflective field mutation để chèn trạng thái sau khi khởi tạo.

## 7. Constructor binding thay cho field injection vào `final`

Một số framework cũ tạo bean bằng constructor rỗng rồi dùng deep reflection để ghi field, kể cả field `final`. Cách làm này xung đột với mục tiêu giữ tính toàn vẹn của `final` và sẽ gặp hạn chế mạnh hơn khi JDK tiến tới từ chối mutation trái phép.

Ưu tiên:

- Constructor injection cho dependency bắt buộc.
- Static factory hoặc factory do dependency injection container gọi.
- Constructor binding cho JSON/configuration binding.
- Record hoặc kiểu immutable phù hợp với DTO chỉ chứa dữ liệu.
- Phiên bản framework hỗ trợ JDK hiện tại và không cần sửa `final` field sau constructor.

Ví dụ DTO có thể dùng record khi component phù hợp:

```java
import java.net.URI;
import java.time.Duration;
import java.util.Objects;
import java.util.Set;

public record ServerConfig(
        URI endpoint,
        Duration requestTimeout,
        Set<String> allowedHosts) {

    public ServerConfig {
        Objects.requireNonNull(endpoint, "endpoint");
        Objects.requireNonNull(requestTimeout, "requestTimeout");
        allowedHosts = Set.copyOf(Objects.requireNonNull(allowedHosts, "allowedHosts"));
        if (requestTimeout.isNegative() || requestTimeout.isZero()) {
            throw new IllegalArgumentException("requestTimeout must be positive");
        }
    }
}
```

Record tự cung cấp component `final` và constructor canonical. Compact constructor cho phép xác thực, chuẩn hóa và sao chép trước khi giá trị được lưu. Tuy nhiên, record cũng chỉ bất biến nông nếu component là đối tượng mutable.

Nếu thư viện chưa hỗ trợ constructor binding, hãy nâng cấp hoặc thay thế thư viện. Không giả định rằng `setAccessible(true)` luôn đủ để ghi `final` field; từ JDK 26 còn có cơ chế cấp quyền mutation riêng.

## 8. JDK 26 và JEP 500: cảnh báo khi sửa `final` bằng deep reflection

JEP 500, **Prepare to Make Final Mean Final**, được triển khai từ JDK 26. Mục tiêu là chuyển dần sang trạng thái integrity by default: mã Java có thể dựa vào cam kết rằng giá trị `final` không bị thay đổi tùy tiện sau khi đối tượng được khởi tạo.

Các mutation methods liên quan gồm:

- `Field.set(Object, Object)` và các biến thể `setBoolean`, `setInt`, `setLong`, `setFloat`, `setDouble`, ...
- `MethodHandles.Lookup.unreflectSetter(Field)` để lấy setter handle cho field phản chiếu.

Trong JDK 26 và JDK 27, lần đầu một module thực hiện deep-reflection mutation trái phép sẽ phát cảnh báo theo mặc định. Mutation vẫn có thể tiếp tục trong chế độ `warn`, nhưng ứng dụng cần xử lý cảnh báo vì một JDK tương lai sẽ từ chối các thao tác đó theo mặc định.

Khả năng mutation bị giới hạn hơn việc chỉ gọi `setAccessible(true)`:

1. `setAccessible(true)` phải thành công. Nếu lớp đích ở module khác, điều kiện truy cập phải được đáp ứng, thường bằng cách mở package cho module gọi; trường hợp cùng module hoặc public field trong package được export có thể đáp ứng theo quy tắc truy cập tương ứng.
2. Module gọi phải được cấp capability qua `--enable-final-field-mutation`.
3. Mutation methods chỉ cho phép sửa trường instance `final` đủ điều kiện. Trường `static final`, trường của record class và hidden class không được sửa theo cơ chế này.

`--add-opens` hoặc `setAccessible(true)` riêng lẻ không cấp capability mutation. Ngược lại, `--enable-final-field-mutation` cũng không tự cấp quyền truy cập sâu vào lớp đích. Hai điều kiện quyền truy cập và capability là riêng biệt. JEP 500 tập trung vào thao tác ghi trường `final`; nó không cấm đọc field bằng reflection và không thay đổi cách ghi các trường không phải `final`.

Các quy tắc này nói về mutation qua reflection/MethodHandles API được nêu trong JEP 500. Chúng không cấm gán trường `final` trong constructor hoặc initializer hợp lệ, cũng không biến một collection mutable thành immutable.

## 9. Các cờ runtime để phát hiện và kiểm thử

JDK 26 hỗ trợ hai nhóm cờ:

| Cờ | Ý nghĩa |
|---|---|
| `--illegal-final-field-mutation=allow` | Cho phép mutation trái phép, không cảnh báo; chỉ nên dùng tạm khi điều tra |
| `--illegal-final-field-mutation=warn` | Cho phép mutation nhưng cảnh báo lần đầu theo module; đây là mặc định của JDK 26 và JDK 27 |
| `--illegal-final-field-mutation=debug` | Cho phép mutation và in cảnh báo cùng stack trace cho từng lần mutation |
| `--illegal-final-field-mutation=deny` | Từ chối mutation trái phép; `Field.set` ném `IllegalAccessException` |
| `--enable-final-field-mutation=ALL-UNNAMED` | Cấp capability cho code trên class path (unnamed modules) |
| `--enable-final-field-mutation=moduleA,moduleB` | Cấp capability cho các module được liệt kê trên module path |

Ví dụ chạy ứng dụng class path để tìm thư viện sửa `final`:

```bash
java --illegal-final-field-mutation=debug -jar application.jar
```

Sau khi xác định và cập nhật các thư viện liên quan, chạy ở chế độ nghiêm ngặt:

```bash
java --illegal-final-field-mutation=deny -jar application.jar
```

Chế độ `deny` giúp phát hiện sớm phụ thuộc vào hành vi sẽ bị từ chối trong tương lai. Nếu dùng một thư viện chưa thể thay thế và cần ngoại lệ tạm thời, chỉ cấp capability cho module thực sự cần thiết, đồng thời bảo đảm package đích được mở theo yêu cầu. Ví dụ với code trên class path:

```bash
java --enable-final-field-mutation=ALL-UNNAMED -jar application.jar
```

Đây là ngoại lệ vận hành, không phải cách sửa thiết kế lâu dài. `--illegal-final-field-mutation` là cờ chuyển tiếp và sẽ bị loại bỏ trong tương lai; không xây dựng cấu hình production lâu dài dựa vào `allow` hoặc `warn`.

## 10. Quy trình nâng cấp thư viện và kiểm thử

Khi chuyển ứng dụng sang JDK 26 trở lên, thực hiện theo thứ tự:

1. Chạy ứng dụng ở chế độ mặc định và thu thập cảnh báo final-field mutation.
2. Chạy với `--illegal-final-field-mutation=debug` để xác định module, lớp và stack trace gây mutation.
3. Cập nhật framework hoặc thư viện lên phiên bản hỗ trợ constructor binding, factory hoặc record; kiểm tra release notes của thư viện.
4. Với mã tự viết, thay field injection và reflective setter bằng constructor/factory; dùng builder chỉ ở giai đoạn tạo object.
5. Thêm defensive copy cho collection, map và mảng; kiểm tra các component mutable lồng bên trong.
6. Chạy test tích hợp với `--illegal-final-field-mutation=deny` và xử lý mọi `IllegalAccessException`.
7. Chỉ giữ `--enable-final-field-mutation` cho module có nhu cầu thực sự và đã được đánh giá; ghi nhận lý do, phạm vi package mở và kế hoạch loại bỏ.
8. Kiểm tra JFR event `jdk.FinalFieldMutation` nếu cần quan sát mutation trong workload thực tế.

Không nên chỉ tắt cảnh báo để làm log sạch. Cảnh báo là bằng chứng về một dependency có thể bị lỗi khi runtime chuyển sang mặc định từ chối mutation.

## 11. Những điểm cần nhớ

- Gán các trường `final` bắt buộc trong constructor hoặc initializer; trả về đối tượng chỉ sau khi nó đã hợp lệ.
- Static factory giúp đặt tên và kiểm soát cách tạo; builder có thể mutable nhưng phải tạo snapshot trong `build()`.
- Sao chép collection bằng `List.copyOf`, `Set.copyOf`, `Map.copyOf`; clone mảng khi nhận và trả dữ liệu nếu cần bảo vệ hai chiều.
- `final` không tạo bất biến sâu; object được tham chiếu vẫn có thể mutable.
- Không để `this` thoát khỏi constructor qua listener, callback, thread hoặc phương thức có thể override.
- Ưu tiên constructor injection, factory và record binding thay cho field injection vào `final`.
- Từ JDK 26, JEP 500 cảnh báo deep-reflection mutation; JDK 26/27 mặc định `warn`, còn `deny` dùng để kiểm tra khả năng tương thích với hướng thay đổi tương lai.
- `--enable-final-field-mutation` chỉ là ngoại lệ có chủ đích; `--add-opens` một mình không cấp quyền sửa `final`.

## Tài liệu tham khảo

- [JEP 500: Prepare to Make Final Mean Final](https://openjdk.org/jeps/500)
- [Java SE 26 Migration Guide: Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
- [Java SE 26 API: Mutation methods](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html)
- [Java SE 26 API: Field](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 27 Migration Guide: Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [Inside Java: Avoiding Final Field Mutation](https://inside.java/2026/04/27/avoiding-final-field-mutation/)
- [Inside Java: Quality Outreach — JDK 26 Final Field Mutation Warnings](https://inside.java/2026/05/15/quality-heads-up/)
- [Java Language Specification: Final Field Semantics](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html)
