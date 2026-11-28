# Chuyển lớp dữ liệu sang record và kiểm tra tương thích của bên sử dụng

Chuyển một lớp dữ liệu (POJO/DTO) sang `record` có thể làm mã nguồn gọn hơn và thể hiện rõ ý định mô hình hóa dữ liệu bất biến. Tuy nhiên, đây là thay đổi hợp đồng API nếu lớp đã được công khai cho module khác, framework hoặc ứng dụng bên ngoài sử dụng. Record sinh accessor theo tên component, có canonical constructor, tự định nghĩa equality theo component và không hỗ trợ kế thừa lớp như một class thông thường.

Vì vậy, không nên chuyển hàng loạt chỉ bằng cách thay `class` thành `record`. Cần kiểm tra cách bên sử dụng tạo object, đọc/ghi thuộc tính, so sánh object, dùng reflection, serialize dữ liệu và phụ thuộc vào lớp cha. Bài học tập trung vào lộ trình chuyển đổi có kiểm soát, các mức tương thích và cách kiểm thử trên JDK hiện đại.

## 1. Khi nào một lớp dữ liệu phù hợp để chuyển thành record?

Record phù hợp khi object chủ yếu biểu diễn một tập giá trị đã xác định tại thời điểm tạo và không cần thay đổi trạng thái sau đó. Một DTO nhận dữ liệu từ API, kết quả truy vấn, thông điệp hoặc cấu hình thường là ứng viên tốt nếu hợp đồng của nó ổn định.

Trước khi chuyển đổi, hãy kiểm tra các điều kiện:

- Trạng thái của object có thể xác định đầy đủ qua một tập component không?
- Có thể khởi tạo object qua constructor thay vì tạo rỗng rồi gọi setter không?
- Bên sử dụng có chấp nhận accessor dạng `id()` thay cho `getId()` không, hoặc có thể giữ alias tương thích không?
- Object có cần được sửa đổi sau khi tạo không?
- Lớp có đang kế thừa một base class hoặc được lớp khác kế thừa không?
- Các framework đang dùng có hỗ trợ record và canonical constructor không?
- Equality theo giá trị có phù hợp với nghiệp vụ không?
- Component có chứa collection, array hoặc object mutable cần defensive copy không?

Nếu object đại diện cho một entity có vòng đời, identity, lazy loading, proxy hoặc trạng thái thay đổi thường xuyên, class thông thường có thể vẫn phù hợp hơn. Record là công cụ mô hình hóa dữ liệu, không phải lựa chọn thay thế bắt buộc cho mọi POJO.

## 2. Ví dụ một DTO dạng class trước khi chuyển đổi

Giả sử thư viện công khai DTO sau:

```java
import java.math.BigDecimal;
import java.util.Objects;

public final class PaymentSummary {
    private final String paymentId;
    private final BigDecimal amount;
    private String description;

    public PaymentSummary(
            String paymentId,
            BigDecimal amount,
            String description) {
        this.paymentId = Objects.requireNonNull(paymentId);
        this.amount = Objects.requireNonNull(amount);
        this.description = description;
    }

    public String getPaymentId() {
        return paymentId;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }
}
```

Bên sử dụng có thể viết:

```java
PaymentSummary summary = new PaymentSummary(
        "PAY-100",
        new BigDecimal("125.50"),
        "Initial payment");

String id = summary.getPaymentId();
summary.setDescription("Reconciled payment");
```

Để chuyển class này sang record, trước tiên cần quyết định `description` có thực sự phải mutable không. Nếu mô hình nghiệp vụ cho phép thay đổi mô tả sau khi tạo, chuyển thẳng sang record sẽ làm mất setter và thay đổi cách sử dụng. Nếu toàn bộ dữ liệu là snapshot bất biến, có thể chuyển như sau.

## 3. Chuyển DTO sang record

```java
import java.math.BigDecimal;
import java.util.Objects;

public record PaymentSummary(
        String paymentId,
        BigDecimal amount,
        String description) {

    public PaymentSummary {
        Objects.requireNonNull(paymentId, "paymentId");
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }
    }
}
```

Sau chuyển đổi:

- Component tạo accessor `paymentId()`, `amount()` và `description()`.
- Canonical constructor nhận ba tham số theo đúng thứ tự component.
- Các component được lưu trong field `private final`.
- Record class là `final` và không thể được subclass.
- `equals`, `hashCode` và `toString` được triển khai theo component.
- Compact constructor cho phép kiểm tra và chuẩn hóa dữ liệu trước khi component được gán.

Ví dụ sử dụng mới:

```java
PaymentSummary summary = new PaymentSummary(
        "PAY-100",
        new BigDecimal("125.50"),
        "Initial payment");

String id = summary.paymentId();
```

Compact constructor không cần gán lại từng field. Sau khi phần thân constructor hoàn tất, Java tự gán các tham số đã được kiểm tra/điều chỉnh vào component tương ứng. Nếu cần chuẩn hóa giá trị, có thể gán lại tham số, ví dụ `paymentId = paymentId.strip();` trước khi constructor kết thúc.

## 4. Những khác biệt API bên sử dụng cần xử lý

Chuyển class sang record thay đổi một số điểm mà client thường gọi trực tiếp:

| Khía cạnh | Class/POJO thường gặp | Record | Tác động đến bên sử dụng |
|---|---|---|---|
| Accessor | `getPaymentId()` | `paymentId()` | Source code gọi getter cũ cần sửa hoặc dùng alias |
| Mutator | Có thể có `setDescription()` | Không có setter sinh tự động | Client không thể cập nhật component sau khi tạo |
| Constructor | Có thể có no-arg và nhiều overload | Canonical constructor theo component | Framework/client cần tạo đủ giá trị component |
| Kế thừa | Có thể extends class khác nếu không final | Record luôn final và extends `java.lang.Record` | Không còn khả năng subclass hoặc giữ base class cũ |
| Equality | Mặc định là identity nếu không override | So sánh theo component | Map, Set, cache và test có thể đổi hành vi |
| Reflection | Field/getter/constructor theo thiết kế class | Có record component metadata | Framework introspection có thể chọn cách bind khác |
| String representation | Phụ thuộc `toString()` được viết | Dạng mặc định dựa trên component | Log/test dựa vào chuỗi cũ có thể thất bại |

Hãy rà soát các cách sử dụng thực tế trong codebase và hợp đồng công khai. Một class có vẻ chỉ là DTO vẫn có thể được framework hoặc client bên ngoài sử dụng theo quy ước JavaBeans.

## 5. Getter JavaBeans và accessor của record

Accessor được sinh từ record component có tên trùng component, không có tiền tố `get` hoặc `is`:

```java
public record User(String id, String activeName, boolean enabled) {
}
```

Các accessor là:

```java
user.id();
user.activeName();
user.enabled();
```

Không tự động có `getId()`, `getActiveName()` hoặc `isEnabled()`. Điều này ảnh hưởng đến code gọi getter trực tiếp và một số công cụ introspection dựa trên JavaBeans convention.

### Giữ getter cũ bằng alias

Nếu muốn bên sử dụng cũ tiếp tục gọi getter trong giai đoạn chuyển đổi, có thể khai báo phương thức thông thường:

```java
public record User(String id, String activeName, boolean enabled) {
    @Deprecated(forRemoval = false)
    public String getId() {
        return id;
    }

    @Deprecated(forRemoval = false)
    public String getActiveName() {
        return activeName;
    }

    @Deprecated(forRemoval = false)
    public boolean isEnabled() {
        return enabled;
    }
}
```

Các alias này có thể giữ source và binary call site nếu chữ ký cũ được bảo toàn. Tuy nhiên, chúng không biến record thành JavaBean mutable; framework phải nhận diện được record hoặc được cấu hình để gọi constructor/accessor phù hợp.

Nếu bên sử dụng dựa vào `Introspector`, property descriptor hoặc framework cũ chỉ tìm `getX()`/`setX()`, cần kiểm thử trực tiếp với phiên bản framework đó. Việc có getter alias chưa đủ nếu framework yêu cầu no-arg constructor và setter để hydrate object.

## 6. Setter và tính bất biến: không thể giữ nguyên semantics bằng alias

Record component được lưu trong field `final`. Vì vậy, không thể viết một setter có tác dụng thay đổi component như setter của POJO mutable.

Ví dụ sau không hợp lệ vì component `description` không thể được gán lại sau khi constructor kết thúc:

```java
public record PaymentSummary(String description) {
    public void setDescription(String description) {
        this.description = description; // Không biên dịch
    }
}
```

Có thể khai báo một method cùng tên setter để giữ chữ ký ở mức binary, nhưng nếu method ném `UnsupportedOperationException` thì client cũ vẫn bị thay đổi hành vi. Method no-op còn nguy hiểm hơn vì bên gọi tưởng dữ liệu đã được cập nhật trong khi thực tế không đổi. Không nên tạo alias giả để tuyên bố tương thích.

Nếu client cần cập nhật dữ liệu, có thể cung cấp phương thức tạo record mới:

```java
public record PaymentSummary(
        String paymentId,
        BigDecimal amount,
        String description) {

    public PaymentSummary withDescription(String newDescription) {
        return new PaymentSummary(paymentId, amount, newDescription);
    }
}
```

Client dùng:

```java
summary = summary.withDescription("Reconciled payment");
```

Đây là API immutable mới; nó không tương đương setter cũ vì object ban đầu không thay đổi. Nếu bắt buộc duy trì semantics mutable cho client cũ, hãy giữ một class facade/adapter mutable và chuyển đổi với record ở ranh giới nội bộ.

## 7. Constructor, no-arg constructor và binary linkage

Record có canonical constructor tương ứng với danh sách component. Một record có component không tự sinh no-arg constructor. Có thể khai báo constructor overload nếu có quy tắc mặc định hợp lệ:

```java
public record Coordinate(int x, int y) {
    public Coordinate() {
        this(0, 0);
    }
}
```

Tuy nhiên, constructor rỗng chỉ hợp lý khi `(0, 0)` là trạng thái mặc định được định nghĩa rõ. Không nên thêm constructor mặc định chỉ để làm hài lòng framework nếu nó tạo ra object không hợp lệ.

### Canonical constructor và binary compatibility

Giả sử class cũ có constructor:

```java
public PaymentSummary(String paymentId, BigDecimal amount, String description)
```

Record mới có cùng thứ tự và kiểu component thì canonical constructor có cùng JVM descriptor. Binary client gọi constructor đó có thể tiếp tục liên kết. Tuy nhiên, điều này không bảo đảm toàn bộ API tương thích: getter, setter, superclass, reflection và equality có thể đã thay đổi.

Nếu đổi thứ tự component, đổi kiểu hoặc thêm/bỏ component, descriptor canonical constructor thường thay đổi. Client binary gọi descriptor cũ có thể gặp `NoSuchMethodError` nếu overload tương ứng không được giữ lại.

Tên tham số không nằm trong JVM method descriptor, nhưng có thể được đọc qua reflection hoặc được framework sử dụng. Thứ tự component cũng là metadata và thứ tự tham số canonical constructor, nên không thay đổi tùy tiện.

## 8. Kế thừa và các lớp phụ thuộc vào base class

Record luôn là `final` và có superclass cố định là `java.lang.Record`. Record có thể `implements` interface, nhưng không thể `extends` một class nghiệp vụ khác.

Nếu POJO cũ kế thừa `BaseDto`, có các protected field hoặc dùng template method từ base class, không thể chuyển trực tiếp thành record mà vẫn giữ cấu trúc kế thừa đó. Nếu có client subclass POJO cũ, việc đổi cùng tên class thành record là breaking change vì record không thể được mở rộng.

Một số hướng xử lý:

- Thay kế thừa bằng composition nếu quan hệ chỉ nhằm tái sử dụng dữ liệu.
- Đưa hành vi chung vào interface hoặc service bên ngoài nếu phù hợp.
- Tạo record mới cho dữ liệu truyền tải, giữ class cũ làm facade/adapter.
- Phát hành kiểu mới hoặc package/version API mới nếu cấu trúc kế thừa là hợp đồng công khai.

Không nên cố chuyển một hierarchy entity/domain model sang record chỉ để giảm số dòng code. Hãy xác định rõ identity, vòng đời và khả năng mở rộng của kiểu trước khi quyết định.

## 9. Equality và hashCode thay đổi theo giá trị

Nếu class cũ không override `equals()` và `hashCode()`, hai object khác instance thường không bằng nhau dù các field giống hệt nhau. Record sinh equality dựa trên component.

Ví dụ:

```java
public record UserKey(String tenant, String userId) {
}

UserKey first = new UserKey("acme", "U-10");
UserKey second = new UserKey("acme", "U-10");

System.out.println(first.equals(second)); // true
```

Nếu chuyển một class dùng identity equality thành record, hành vi trong `HashMap`, `HashSet`, cache, deduplication và test có thể thay đổi. Hai key trước đây được coi là khác nhau có thể trở thành cùng một key theo giá trị.

Ngược lại, nếu class cũ đã có equality theo một tập field khác với tất cả component mới, record sẽ thay đổi semantics. Cần kiểm tra xem các component nào thực sự định nghĩa giá trị bằng nhau của domain.

Không dùng record làm entity identity chỉ vì nó có nhiều field. Nếu hai object cùng dữ liệu nhưng phải đại diện cho hai thực thể khác nhau, value equality mặc định có thể không phù hợp.

## 10. Record là bất biến nông: kiểm tra component mutable

Field component là `final`, nhưng đối tượng được tham chiếu có thể mutable. Ví dụ:

```java
public record SearchRequest(String query, List<String> filters) {
}
```

Client vẫn có thể thay đổi list sau khi tạo record:

```java
List<String> filters = new ArrayList<>();
filters.add("active");

SearchRequest request = new SearchRequest("orders", filters);
filters.add("admin"); // request.filters() nhìn thấy thay đổi
```

Nếu muốn snapshot bất biến, tạo defensive copy trong compact constructor:

```java
public record SearchRequest(String query, List<String> filters) {
    public SearchRequest {
        filters = List.copyOf(filters);
    }
}
```

`List.copyOf` tạo list không thể sửa thông qua reference trả về; nó cũng từ chối phần tử `null`. Hãy xác định rõ chính sách null trước khi dùng. Với map/set, có thể dùng `Map.copyOf`/`Set.copyOf` khi semantics và thứ tự phù hợp.

Với array, cần clone cả khi nhận vào và khi trả ra nếu muốn bảo vệ trạng thái:

```java
public record Payload(byte[] bytes) {
    public Payload {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
```

Lưu ý: equality mặc định của record với array component không so sánh nội dung array theo `Arrays.equals`; nó sử dụng semantics `equals` của component, mà array kế thừa identity equality. Nếu cần value equality theo nội dung array, phải định nghĩa lại `equals`/`hashCode` hoặc chọn kiểu dữ liệu phù hợp.

## 11. Validation và normalization khi chuyển đổi

POJO cũ có thể thực hiện validation trong constructor, setter hoặc một phương thức `validate()` riêng. Khi chuyển sang record, invariant cần được đưa vào canonical constructor để mọi instance đều hợp lệ ngay sau khi tạo.

```java
import java.util.Objects;

public record UserProfile(String userId, String email) {
    public UserProfile {
        userId = Objects.requireNonNull(userId, "userId").strip();
        email = Objects.requireNonNull(email, "email").strip();

        if (userId.isEmpty()) {
            throw new IllegalArgumentException("userId is required");
        }
        if (!email.contains("@")) {
            throw new IllegalArgumentException("email is invalid");
        }
    }
}
```

Khi migration, so sánh kỹ hành vi validation cũ:

- Setter cũ có cho phép trạng thái tạm thời chưa hợp lệ không?
- Constructor cũ có chuẩn hóa dữ liệu giống compact constructor mới không?
- `null`, chuỗi rỗng, whitespace và giá trị mặc định được xử lý thế nào?
- Có client phụ thuộc vào việc lỗi chỉ xuất hiện lúc gọi setter hoặc lúc lưu dữ liệu không?

Record khuyến khích invariant được kiểm tra tại thời điểm tạo. Đây có thể là thay đổi hành vi tốt, nhưng vẫn là thay đổi cần thông báo nếu bên sử dụng trước đây cho phép object ở trạng thái chưa hoàn chỉnh.

## 12. Framework, JavaBeans và mapping dữ liệu

Không phải mọi framework đều xử lý record giống nhau. Trước khi chuyển DTO được framework quản lý, hãy xác nhận phiên bản framework hỗ trợ:

- Nhận diện record bằng reflection.
- Đọc record component và accessor dạng `componentName()`.
- Gọi canonical constructor với đúng thứ tự/kiểu component.
- Ánh xạ JSON property, validation annotation và generic type.
- Tạo schema hoặc query projection từ record.

Một framework JavaBeans cũ có thể tìm getter `getX()` và setter `setX()`, sau đó yêu cầu no-arg constructor để hydrate object. Record không đáp ứng mô hình mutable bean này theo mặc định. Getter alias chỉ giải quyết một phần; nếu framework cần setter, cần DTO mutable riêng hoặc nâng cấp/cấu hình framework để hỗ trợ record.

Ví dụ với JSON, thay đổi tên component có thể làm tên property thay đổi theo cấu hình mặc định của serializer. Nếu API bên ngoài cần giữ JSON contract, hãy khai báo tên property tường minh bằng annotation mà framework hỗ trợ và viết contract test trên đúng phiên bản thư viện.

Với ORM/entity, cần phân biệt DTO/projection với entity có identity và lifecycle. Một số framework hỗ trợ record cho projection hoặc kết quả truy vấn, nhưng entity cần proxy, lazy loading hoặc mutation có thể không phù hợp với record. Kiểm tra yêu cầu của framework cụ thể thay vì suy ra từ việc nó hỗ trợ record ở một tính năng khác.

## 13. Serialization và dữ liệu đã lưu

Nếu class cũ triển khai `Serializable`, không nên giả định chuyển sang record giữ nguyên khả năng đọc mọi dữ liệu serialized trước đây. Record có quy tắc serialization riêng; khi deserialize, canonical constructor được gọi để tạo record instance. Component, kiểu dữ liệu và constructor validation có thể ảnh hưởng quá trình đọc dữ liệu từ phiên bản cũ.

Nếu record được dùng với Java object serialization:

- Tạo fixture bằng phiên bản class cũ và thử deserialize bằng phiên bản record mới.
- Kiểm tra đổi tên, thêm/bớt component và thay đổi kiểu.
- Kiểm tra canonical constructor mới có từ chối dữ liệu cũ không.
- Không coi `serialVersionUID` là giải pháp tự động cho mọi thay đổi schema.

Với dữ liệu lưu dài hạn hoặc giao tiếp giữa các service, nên ưu tiên schema có version và serializer định nghĩa rõ mapping/compatibility (chẳng hạn JSON/Avro/Protobuf theo tiêu chuẩn của hệ thống). Không dùng định dạng `toString()` của record làm serialization format.

## 14. Lộ trình chuyển đổi ít rủi ro

Một lộ trình thực tế có thể chia thành các bước:

1. **Kiểm kê bên sử dụng:** tìm constructor, getter/setter, subclass, reflection, serialization, framework mapping và equality usage.
2. **Phân loại contract:** xác định API nội bộ, public library API, wire schema và persisted data.
3. **Xác định semantics:** quyết định object có thật sự immutable/value-based hay không; component nào cần defensive copy.
4. **Tạo record mới hoặc chuyển đổi type:** giữ nguyên tên/kiểu/thứ tự component nếu có thể, tránh thay đổi không liên quan trong cùng một release.
5. **Cung cấp adapter:** giữ getter alias hoặc constructor overload khi chúng có thể bảo toàn semantics; dùng facade mutable nếu client vẫn cần setter.
6. **Cập nhật framework/config:** xác nhận record support và mapping của serializer/validator/ORM.
7. **Chạy compatibility tests:** source, binary, behavior, reflection, serialization và integration.
8. **Thông báo migration:** đánh dấu API cũ deprecated, cung cấp ví dụ thay thế và lịch loại bỏ nếu có.
9. **Phát hành theo version:** nếu có breaking change, dùng major version hoặc kiểu/package API mới.
10. **Theo dõi sau phát hành:** quan sát lỗi linkage, mapping và dữ liệu trong các client đã nâng cấp.

Không nhất thiết phải giữ cùng tên class nếu việc chuyển đổi làm thay đổi semantics lớn. Tạo `PaymentSummaryRecord` hoặc `PaymentSummaryV2` trong giai đoạn chuyển tiếp đôi khi an toàn hơn thay thế trực tiếp một class public đang được nhiều client sử dụng.

## 15. Ví dụ adapter giữ API mutable cũ

Nếu client cũ cần setter nhưng phần lõi mới muốn dùng record bất biến, có thể giữ facade mutable chuyển đổi sang record:

```java
import java.math.BigDecimal;

public record PaymentSnapshot(
        String paymentId,
        BigDecimal amount,
        String description) {
}

public final class LegacyPaymentSummary {
    private String paymentId;
    private BigDecimal amount;
    private String description;

    public LegacyPaymentSummary(
            String paymentId,
            BigDecimal amount,
            String description) {
        this.paymentId = paymentId;
        this.amount = amount;
        this.description = description;
    }

    public String getPaymentId() {
        return paymentId;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public PaymentSnapshot toRecord() {
        return new PaymentSnapshot(paymentId, amount, description);
    }

    public static LegacyPaymentSummary fromRecord(PaymentSnapshot snapshot) {
        return new LegacyPaymentSummary(
                snapshot.paymentId(),
                snapshot.amount(),
                snapshot.description());
    }
}
```

Facade này giữ semantics mutable cho client cũ; phần service/domain mới có thể nhận `PaymentSnapshot`. Adapter làm ranh giới chuyển đổi tường minh, nhưng cần xác định ai sở hữu object, khi nào snapshot được tạo và dữ liệu nào là nguồn chuẩn. Không nên để hai representation cùng được sửa độc lập mà không có quy tắc đồng bộ.

## 16. Kiểm thử tương thích cho bên sử dụng

Một bộ kiểm thử migration nên xác nhận nhiều lớp hợp đồng, không chỉ test rằng record tạo được object.

### Source compatibility

Biên dịch client mẫu với API mới. Các lời gọi getter, setter, constructor, subclass và framework mapping cũ cần được rà soát. Nếu chủ đích là breaking change, cập nhật client mẫu để chứng minh hướng migration mới.

### Binary compatibility

Biên dịch một consumer bằng phiên bản class cũ, sau đó chạy bytecode consumer đó với artifact API mới. Kiểm tra các method descriptor cũ còn tồn tại hay lỗi linkage như `NoSuchMethodError`, `AbstractMethodError`, `IncompatibleClassChangeError` có xuất hiện.

Giữ nguyên canonical constructor descriptor không có nghĩa toàn bộ binary API được giữ. Phải kiểm tra riêng getter, setter, constructor overload và superclass.

### Behavioral compatibility

Kiểm tra:

- Giá trị sau khi tạo và sau khi chuyển đổi từ class cũ.
- Hành vi validation và exception.
- Equality/hashCode và hành vi trong map/set/cache.
- Các thao tác cập nhật trước đây có còn được hỗ trợ hoặc đã được thay bằng API tạo object mới.
- `toString()` nếu test/log đang phụ thuộc vào chuỗi cũ.

### Reflection và framework compatibility

Kiểm tra `Class.isRecord()`, `getRecordComponents()`, tên/kiểu/thứ tự component, accessor và constructor được framework chọn. Chạy contract test với đúng phiên bản JSON serializer, validation, ORM hoặc dependency injection trong ứng dụng.

### Serialization compatibility

Tạo dữ liệu serialized hoặc message fixture từ phiên bản trước. Đọc bằng phiên bản mới và xác nhận mapping, default, validation và lỗi được xử lý đúng. Với schema ngoài Java serialization, kiểm tra JSON key hoặc schema registry contract.

## 17. Checklist review trước khi merge

- [ ] Object có thực sự là value/data carrier bất biến không?
- [ ] Tất cả bên sử dụng đã được kiểm kê chưa?
- [ ] Getter JavaBeans có cần alias để giữ client cũ không?
- [ ] Setter có semantics mutable bắt buộc phải giữ không?
- [ ] Canonical constructor và các overload cũ có giữ đúng descriptor không?
- [ ] Có client subclass hoặc phụ thuộc base class không?
- [ ] Equality/hashCode mới có ảnh hưởng collection, cache hoặc identity không?
- [ ] Component mutable đã được defensive copy khi cần chưa?
- [ ] Framework và serializer hỗ trợ record trên đúng version chưa?
- [ ] Serialization fixture và wire schema cũ đã được kiểm tra chưa?
- [ ] Source, binary, behavior và reflection compatibility tests đã chạy chưa?
- [ ] Breaking change, deprecation và hướng migration đã được công bố chưa?

## 18. Ghi nhớ

- Record phù hợp với dữ liệu có cấu trúc ổn định và value semantics rõ ràng.
- Accessor record có tên component như `id()`, không tự sinh `getId()`.
- Getter alias có thể giữ một phần source/binary API; setter mutable không thể được giữ nguyên semantics trong record.
- Canonical constructor có thể giữ descriptor cũ nếu số lượng, kiểu và thứ tự tham số không đổi.
- Record là final, không thể giữ quan hệ kế thừa class cũ.
- `equals`/`hashCode` chuyển sang value semantics theo component và có thể làm thay đổi hành vi map/set/cache.
- Record bất biến nông; collection, array và object mutable cần defensive copy khi cần snapshot.
- Framework phải hỗ trợ record constructor/accessor; JavaBeans binder chỉ dựa vào no-arg/setter có thể không tương thích.
- Serialization, JSON schema và reflection cần được kiểm thử riêng.
- Dùng adapter/facade hoặc API version mới khi cần giữ semantics của client cũ.

Chuyển một lớp dữ liệu sang record là thay đổi thiết kế và có thể là thay đổi API. Khi kiểm kê bên sử dụng, xác định rõ value semantics, giữ adapter ở nơi cần thiết và kiểm thử source/binary/behavioral compatibility, nhóm phát triển có thể tận dụng record mà không làm gián đoạn client ngoài dự kiến.
