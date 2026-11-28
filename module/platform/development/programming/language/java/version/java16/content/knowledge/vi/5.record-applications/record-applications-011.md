# Giới hạn của record với proxy kế thừa và mô hình entity có vòng đời mutable

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Ứng dụng record. Record được chuẩn hóa từ Java 16 và vẫn phù hợp để biểu diễn DTO, value object, snapshot và dữ liệu truyền giữa các tầng ứng dụng. Tuy nhiên, record có những giới hạn có chủ đích: record luôn final, không thể kế thừa class nghiệp vụ khác và không thể được proxy bằng cách tạo subclass. Những đặc điểm này cần được cân nhắc khi làm việc với AOP, lazy loading và ORM. Bài học tập trung vào cách chọn đúng vai trò giữa record, interface, proxy và entity có vòng đời mutable trong Java hiện đại.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao record không thể làm superclass hoặc bị subclass.
- Phân biệt proxy dựa trên kế thừa với proxy dựa trên interface.
- Nhận biết giới hạn của CGLIB và cách Spring AOP chọn proxy.
- Hiểu vì sao record không phù hợp làm JPA entity có identity và lifecycle được quản lý.
- Dùng record đúng vai trò làm DTO, value object, snapshot, embeddable hoặc composite key.
- Thiết kế entity class phù hợp với persistence context, dirty checking và lazy loading.
- Chọn composition, interface hoặc adapter thay cho kế thừa khi cần tích hợp record với hệ thống khác.

## 1. Record có giới hạn kế thừa theo thiết kế

Record là một dạng class đặc biệt dùng để biểu diễn một tập hợp giá trị. Theo Java Language Specification, một record class được ngầm định là `final`. Nó có superclass trực tiếp là `java.lang.Record` và cú pháp khai báo record không có mệnh đề `extends`.

Ví dụ:

```java
public record CustomerId(String value) {}
```

Record trên không thể có class khác kế thừa từ nó. Các khai báo sau không hợp lệ:

```java
// Không hợp lệ: record không thể được mở rộng.
class PremiumCustomerId extends CustomerId {}

// Không hợp lệ: record không có extends clause.
public record CustomerId(String value) extends SomeBaseClass {}
```

Quy tắc này có hai chiều:

- Một class thông thường không thể kế thừa từ record.
- Một record không thể kế thừa từ class nghiệp vụ do ứng dụng định nghĩa.

Record vẫn có thể triển khai một hoặc nhiều interface. Đây là cơ chế mở rộng hành vi và hợp đồng kiểu phù hợp với record.

```java
interface Identified {
    String id();
}

record CustomerId(String value) implements Identified {
    @Override
    public String id() {
        return value;
    }
}
```

Trong ví dụ, `CustomerId` không kế thừa một base class. Nó đáp ứng hợp đồng `Identified` bằng cách triển khai phương thức `id()`.

### 1.1. Vì sao record không mở rộng được?

Record hướng đến mô hình dữ liệu theo giá trị:

- Danh sách component được xác định ngay trong header.
- Component được lưu trong các trường final.
- Canonical constructor tạo trạng thái ban đầu của instance.
- `equals()` và `hashCode()` mặc định dựa trên component.
- Record class final, nên không có subclass bổ sung trạng thái hoặc thay đổi equality theo kiểu kế thừa.

Nếu record có thể được mở rộng tùy ý, subclass có thể thêm state mới hoặc thay đổi ý nghĩa của equality, làm hợp đồng value-based khó dự đoán. Tính final giữ cấu trúc dữ liệu và semantics của record ổn định.

### 1.2. Dùng interface khi cần nhiều kiểu triển khai

Nếu nhiều loại dữ liệu cần chia sẻ một hợp đồng, hãy định nghĩa interface:

```java
interface PaymentReference {
    String reference();
}

record CardPaymentReference(String reference)
        implements PaymentReference {}

record BankTransferReference(String reference)
        implements PaymentReference {}
```

Caller có thể làm việc với `PaymentReference` mà không cần biết kiểu record cụ thể:

```java
final class PaymentPrinter {
    public static void printReference(PaymentReference payment) {
        System.out.println(payment.reference());
    }
}
```

Cách này giữ record nhỏ và rõ nghĩa, đồng thời cho phép các class hoặc record khác nhau triển khai cùng một hợp đồng. Interface không cung cấp state dùng chung như abstract class, nhưng có thể khai báo phương thức và default method khi cần hành vi chung.

## 2. Proxy dựa trên kế thừa không thể subclass record

Một số framework tạo proxy bằng cách sinh class mới kế thừa class mục tiêu. Proxy override phương thức để thêm logging, transaction, security, retry hoặc lazy loading rồi ủy quyền lời gọi tới object thật.

Mô hình đó cần class mục tiêu có thể được kế thừa và các phương thức cần intercept có thể override. Record final không đáp ứng điều kiện này.

### 2.1. Proxy subclass hoạt động như thế nào?

Về mặt khái niệm, proxy dựa trên subclass có cấu trúc như sau:

```text
Client
  |
  v
GeneratedSubclass extends TargetClass
  |
  +-- intercept method
  |
  +-- delegate to target behavior
```

Nếu `TargetClass` là final, khai báo `extends TargetClass` không hợp lệ. Record luôn final, vì vậy công cụ proxy không thể tạo subclass của record theo cách này.

Không có cấu hình CGLIB nào có thể làm một class final trở thành class có thể kế thừa. Nếu framework buộc dùng proxy class-based, record không thể đóng vai trò target class cho cơ chế đó.

### 2.2. Spring AOP và CGLIB

Spring AOP sử dụng hai cơ chế proxy phổ biến:

- **JDK dynamic proxy:** tạo object triển khai các interface được chỉ định và chuyển lời gọi qua `InvocationHandler`.
- **CGLIB proxy:** tạo subclass của target class tại runtime và override các phương thức có thể override.

CGLIB không thể proxy class final vì không thể kế thừa class đó. Phương thức final cũng không thể được override để gắn advice. Spring cho phép cấu hình kiểu proxy, vì vậy cần kiểm tra chiến lược thực tế trong ứng dụng thay vì chỉ nhìn vào annotation.

Nếu một record triển khai interface và Spring dùng JDK dynamic proxy, proxy có thể bọc target record thông qua interface. Nếu cấu hình ép dùng CGLIB, target record vẫn không thể được subclass.

### 2.3. JDK dynamic proxy có thể bọc một record qua interface

JDK dynamic proxy không tạo subclass của record. Nó tạo một class proxy riêng triển khai interface, rồi ủy quyền lời gọi tới target.

Ví dụ:

```java
import java.lang.reflect.Proxy;
import java.math.BigDecimal;

public final class PriceProxyDemo {
    public interface PriceSource {
        BigDecimal price();
    }

    public record FixedPrice(BigDecimal price) implements PriceSource {}

    public static void main(String[] args) {
        PriceSource target = new FixedPrice(new BigDecimal("125000"));

        PriceSource proxy = (PriceSource) Proxy.newProxyInstance(
                PriceSource.class.getClassLoader(),
                new Class<?>[] { PriceSource.class },
                (proxyObject, method, arguments) -> {
                    System.out.println("Calling " + method.getName());
                    return method.invoke(target, arguments);
                }
        );

        System.out.println(proxy.price());
        System.out.println(proxy instanceof PriceSource); // true
        System.out.println(proxy instanceof FixedPrice);  // false
    }
}
```
Lời gọi `proxy.price()` được chuyển tới invocation handler, sau đó handler gọi phương thức trên target `FixedPrice`. Object proxy triển khai `PriceSource` nhưng không phải instance của `FixedPrice`.

Đây là điểm quan trọng: interface-based proxy bọc một record mà không thay đổi bản chất final của record. Caller phải tham chiếu qua interface. Nếu code yêu cầu ép proxy về kiểu record cụ thể, nó sẽ thất bại.

### 2.4. Khi nào interface proxy không đủ?

Interface proxy chỉ hiển thị các phương thức nằm trong interface. Nếu một phương thức của record không có trong interface, caller không thể gọi phương thức đó thông qua proxy.

Nếu API yêu cầu truyền object bằng kiểu concrete record, kiểm tra trực tiếp `instanceof FixedPrice` hoặc gọi phương thức cụ thể ngoài interface, interface proxy không còn trong suốt với caller.

Khi cần interception cho một service, thường nên đặt interface ở ranh giới service và giữ record làm dữ liệu đầu vào/đầu ra. Không nên biến mọi record thành service chỉ để có thể áp dụng AOP.

## 3. Phân biệt proxy object với target object

Proxy và target là hai object có vai trò khác nhau:

| Đặc điểm | Target record | Interface proxy |
|---|---|---|
| Kiểu runtime | Record class | Class proxy do JDK tạo |
| Kế thừa record | Không có subclass | Không kế thừa record |
| Triển khai interface | Có thể | Có triển khai interface được chỉ định |
| Gọi accessor | Trực tiếp trên record | Qua invocation handler rồi ủy quyền |
| `instanceof RecordType` | true | Thông thường false |
| Dùng như value object | Có | Không nên thay thế target trong equality/value semantics |

Không nên đưa proxy vào nơi yêu cầu value object thật, chẳng hạn làm khóa Map dựa trên record type hoặc serialize một kiểu record cụ thể. Proxy có thể không giữ cùng class, identity, annotation hoặc metadata như target.

Nếu cần log, đo thời gian hoặc kiểm tra quyền khi gọi service, đặt proxy ở ranh giới interface service. Dữ liệu record đi qua service dưới dạng tham số hoặc kết quả.

## 4. Record và mô hình entity có vòng đời mutable

Record thường mô tả giá trị. Entity trong ORM thường mô tả một đối tượng có identity và được persistence context quản lý qua nhiều trạng thái.

Một entity có thể:

- Được tạo mới và chưa được quản lý.
- Được đưa vào persistence context.
- Được thay đổi trong transaction.
- Được đồng bộ xuống database khi flush.
- Trở thành detached khi persistence context kết thúc hoặc entity bị detach.
- Bị đánh dấu xóa và được xóa khi đồng bộ transaction.

Với JPA/Hibernate, framework cần theo dõi entity, ánh xạ identity, quản lý quan hệ và có thể tạo proxy để lazy loading. Mô hình này khác với record là snapshot dữ liệu được tạo đầy đủ qua constructor.

### 4.1. Entity thường cần khả năng được framework quản lý

Jakarta Persistence quy định entity class phải đáp ứng một số điều kiện:

- Entity không được là record.
- Entity phải là class không final.
- Entity cần public hoặc protected constructor không tham số.
- Các phương thức và persistent instance variable của entity không được final theo yêu cầu portable của specification.

Những điều kiện này hỗ trợ persistence provider khởi tạo và quản lý entity, cũng như tạo proxy khi cần. Java sinh canonical constructor cho record chứ không sinh no-args constructor theo quy ước entity. Dù có thể tự khai báo constructor overload, record vẫn final và Jakarta Persistence 3.2 không cho chỉ định record làm entity.

### 4.2. Ví dụ entity class có identity và trạng thái

Một entity đơn giản có thể được khai báo:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Version;
import java.util.Objects;

@Entity
public class CustomerEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    private String name;

    protected CustomerEntity() {
        // Dành cho persistence provider.
    }

    public CustomerEntity(String name) {
        rename(name);
    }

    public Long id() {
        return id;
    }

    public String name() {
        return name;
    }

    public void rename(String newName) {
        Objects.requireNonNull(newName, "newName");
        String normalized = newName.strip();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        this.name = normalized;
    }
}
```

Class này không final và có protected no-args constructor. Phương thức `rename` thay đổi trạng thái entity có kiểm soát. `@Version` hỗ trợ optimistic locking để phát hiện cập nhật xung đột theo cơ chế của persistence provider.

Ví dụ dùng field access vì annotation `@Id` nằm trên field. Trong ứng dụng thật, có thể chọn property access hoặc field access theo quy tắc mapping nhất quán.

### 4.3. Entity được quản lý khác với một bản sao record

Ví dụ trong transaction:

```java
CustomerEntity customer = entityManager.find(CustomerEntity.class, customerId);

customer.rename("Nguyen An");

// Không cần tạo một CustomerEntity mới rồi gọi update.
// Persistence context theo dõi entity đang managed.
entityManager.flush();
```

Khi entity đang managed, thay đổi trạng thái được persistence provider phát hiện và đồng bộ theo cơ chế dirty checking. Việc chính xác khi nào SQL được phát ra phụ thuộc flush mode, transaction và provider.

Với record, cách cập nhật thường là tạo instance mới và truyền nó qua các tầng ứng dụng. Record không có persistence identity hoặc persistence context tự động theo dõi như entity.

### 4.4. Entity không đồng nghĩa mọi field đều phải public setter

Entity có thể giữ field private và chỉ cung cấp phương thức nghiệp vụ để thay đổi trạng thái. Ví dụ `rename` kiểm tra tên trước khi gán. Không cần công khai setter cho mọi field nếu nghiệp vụ không cho phép cập nhật tùy ý.

Tính mutable của entity có thể được kiểm soát qua phương thức nghiệp vụ, transaction và persistence context. Điểm khác biệt là object có identity và trạng thái sống qua một vòng đời persistence, không phải mọi code đều được phép sửa tự do.

## 5. Vì sao record không phải JPA entity portable?

Jakarta Persistence 3.2 ghi rõ enum, record và interface không thể được chỉ định làm entity. Entity class phải không final và có constructor không tham số public hoặc protected.

Vì vậy, khai báo sau không phải entity portable theo Jakarta Persistence:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public record CustomerEntity(Long id, String name) {}
```

Không nên suy luận rằng một provider có thể đọc được record bằng reflection hoặc constructor thì record sẽ trở thành entity hợp lệ theo specification. Việc mapping có thể phụ thuộc provider-specific extension, phiên bản và giới hạn proxy/lifecycle; ứng dụng portable cần tuân theo hợp đồng chuẩn.

Hibernate có tài liệu riêng về việc persist một số class final trong chế độ provider-specific, nhưng class final sẽ hạn chế proxy-based lazy loading. Điều đó không thay đổi quy tắc portable của Jakarta Persistence rằng record không được chỉ định làm entity. Hãy phân biệt khả năng riêng của provider với hợp đồng chuẩn khi thiết kế ứng dụng cần di chuyển giữa các persistence provider.

### 5.1. Record vẫn có vị trí trong Jakarta Persistence

Không dùng record làm entity không có nghĩa record không thể tham gia persistence model.

Jakarta Persistence 3.2 cho phép record làm:

- **Embeddable value:** một giá trị nhúng trong entity, không có persistent identity riêng.
- **Composite primary key class:** kiểu biểu diễn khóa chính gồm nhiều component.

Ví dụ embeddable:

```java
import jakarta.persistence.Embeddable;
import java.util.Objects;

@Embeddable
public record Address(
        String street,
        String city,
        String postalCode
) {
    public Address {
        Objects.requireNonNull(street, "street");
        Objects.requireNonNull(city, "city");
        Objects.requireNonNull(postalCode, "postalCode");

        street = street.strip();
        city = city.strip();
        postalCode = postalCode.strip();

        if (street.isEmpty() || city.isEmpty() || postalCode.isEmpty()) {
            throw new IllegalArgumentException("Address fields are required");
        }
    }
}
```

Entity có thể chứa Address như một giá trị:

```java
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class SupplierEntity {
    @Id
    @GeneratedValue
    private Long id;

    @Embedded
    private Address address;

    protected SupplierEntity() {}

    public SupplierEntity(Address address) {
        this.address = address;
    }

    public Long id() {
        return id;
    }

    public Address address() {
        return address;
    }

    public void changeAddress(Address newAddress) {
        this.address = newAddress;
    }
}
```

`Address` là value object bất biến theo giá trị; `SupplierEntity` vẫn là entity có identity và lifecycle do persistence context quản lý. Khi địa chỉ thay đổi, entity thay component Address bằng một giá trị mới.

Lưu ý: hỗ trợ record làm embeddable được bổ sung trong Jakarta Persistence 3.2. Kiểm tra phiên bản API và persistence provider của ứng dụng trước khi sử dụng; không giả định các phiên bản cũ có cùng khả năng.

### 5.2. Record làm composite primary key

Record cũng phù hợp để biểu diễn khóa ghép vì các component được đặt tên và equality được sinh theo giá trị:

```java
import java.io.Serializable;

public record OrderId(String tenantCode, long orderNumber)
        implements Serializable {}
```

Trong Jakarta Persistence 3.2, record có thể được dùng làm primary key class. Ví dụ trên minh họa kiểu khóa; mapping cụ thể với `@EmbeddedId` hoặc `@IdClass` cần tuân theo quy tắc của persistence version và provider đang dùng.

Không nhầm composite key record với entity record. Khóa là value object dùng định danh entity; bản thân entity vẫn là class theo yêu cầu persistence.

## 6. Record phù hợp với value object, DTO và snapshot

Record phù hợp khi dữ liệu:

- Được tạo đầy đủ tại thời điểm khởi tạo.
- Được so sánh theo giá trị component.
- Không cần subclass để mở rộng trạng thái.
- Không cần ORM quản lý identity và lifecycle trực tiếp.
- Được truyền giữa các tầng hoặc lưu như một snapshot.

Ví dụ response DTO:

```java
public record SupplierView(Long id, Address address) {}
```

Chuyển entity sang DTO tại ranh giới:

```java
public final class SupplierMapper {
    private SupplierMapper() {}

    public static SupplierView toView(SupplierEntity supplier) {
        return new SupplierView(supplier.id(), supplier.address());
    }
}
```

Đoạn mapper minh họa cách chuyển entity sang snapshot. DTO không cần giữ persistence proxy hoặc persistence context; nó mang dữ liệu cần thiết cho response.

Record cũng có thể biểu diễn kết quả truy vấn, message/event payload, cấu hình đã validate hoặc giá trị miền như Money, Address, DateRange.

## 7. Chọn kiểu dữ liệu theo vai trò

| Nhu cầu | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Dữ liệu request/response | Record DTO | Cấu trúc rõ, constructor validation, value equality |
| Giá trị miền không có identity riêng | Record value object | Equality theo component, dễ tạo snapshot |
| Entity được JPA quản lý | Class entity không final | Đáp ứng lifecycle, identity, proxy và persistence rules |
| Giá trị nhúng trong entity | Record embeddable nếu Jakarta Persistence 3.2/provider hỗ trợ | Value không có identity riêng |
| Khóa chính ghép | Record key class theo persistence version hỗ trợ | Component có tên và equality theo giá trị |
| Service cần AOP | Service class triển khai interface | Có thể dùng JDK dynamic proxy |
| Hợp đồng nhiều implementation | Interface | Cho phép record và class cùng triển khai |
| Hành vi dùng chung có state | Composition hoặc class cơ sở phù hợp | Record không thể kế thừa class nghiệp vụ |

Không chọn record chỉ vì nó ngắn hơn class. Hãy chọn theo semantics: value hay identity, snapshot hay lifecycle, constructor hoàn chỉnh hay object được framework quản lý.

## 8. Thiết kế thay thế cho kế thừa và class proxy

Khi một hệ thống yêu cầu kế thừa hoặc proxy subclass, có một số cách thiết kế có thể dùng.

### 8.1. Dùng interface cho hợp đồng

Nếu cần nhiều implementation hoặc interface proxy:

```java
public interface SupplierReader {
    SupplierView findById(long id);
}
```

Một implementation service có thể đọc `SupplierEntity` rồi chuyển thành `SupplierView`. Framework có thể tạo JDK dynamic proxy triển khai `SupplierReader`. Record DTO là giá trị trả về, không cần bị proxy hoặc subclass.

### 8.2. Dùng composition thay cho base class

Nếu record cần mang dữ liệu chung với một kiểu khác, đặt kiểu đó thành component:

```java
import java.time.Instant;

record AuditInfo(String createdBy, Instant createdAt) {}

public record DocumentSnapshot(
        String documentId,
        String title,
        AuditInfo audit
) {}
```

Composition thể hiện rõ dữ liệu nào thuộc snapshot. Nó tránh việc cố đưa record vào một class hierarchy mà record không thể tham gia.

### 8.3. Dùng decorator ở interface boundary

Nếu muốn thêm logging hoặc metrics cho một dịch vụ, có thể tạo decorator triển khai cùng interface:

```java
import java.util.Objects;

public final class LoggingSupplierReader implements SupplierReader {
    private final SupplierReader delegate;

    public LoggingSupplierReader(SupplierReader delegate) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
    }

    @Override
    public SupplierView findById(long id) {
        System.out.println("Find supplier " + id);
        return delegate.findById(id);
    }
}
```

Decorator không cần kế thừa class target. Nó giữ tham chiếu tới delegate và bổ sung hành vi ở ranh giới interface. Đây là cách rõ ràng khi không cần framework AOP.

## 9. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế | Cách xử lý |
|---|---|---|
| Record có thể kế thừa abstract class | Record luôn final và không có extends clause | Dùng interface hoặc composition |
| Record không thể triển khai interface | Record có thể implements nhiều interface | Khai báo hợp đồng qua interface |
| Mọi proxy đều cần subclass | JDK dynamic proxy triển khai interface | Dùng interface proxy nếu hợp đồng phù hợp |
| CGLIB có thể proxy record nếu cấu hình đặc biệt | CGLIB cần subclass, record final | Chọn interface proxy hoặc decorator |
| JDK proxy vẫn là instance của record target | Proxy là object khác triển khai interface | Dùng kiểu interface ở caller |
| Record là JPA entity vì có constructor đầy đủ | Jakarta Persistence 3.2 cấm record làm entity | Dùng class entity và record làm DTO/value |
| Record không dùng được với ORM | JPA 3.2 cho phép record làm embeddable và composite key class | Kiểm tra provider/version |
| Entity phải có public setter cho mọi field | Có thể dùng field private và phương thức nghiệp vụ | Giữ mutation có kiểm soát |
| Entity mutable và record bất biến có thể thay thế nhau trực tiếp | Identity/lifecycle khác value/snapshot | Chuyển đổi tại ranh giới |

## 10. Checklist chọn record, proxy và entity

Trước khi chọn kiểu dữ liệu, hãy kiểm tra:

1. Kiểu này đại diện giá trị hay entity có identity?
2. Nó có cần kế thừa một class nghiệp vụ không?
3. Framework proxy dùng JDK interface proxy hay subclass proxy?
4. Có cần proxy được cast về concrete type không?
5. Nếu dùng ORM, persistence specification và provider có hỗ trợ đúng vai trò của record không?
6. Có cần lazy loading, dirty checking hoặc lifecycle callbacks không?
7. Component record có phải snapshot đầy đủ và hợp lệ ngay khi tạo không?
8. Có thể dùng interface hoặc composition để biểu đạt hợp đồng không?
9. DTO có đang giữ proxy/entity thay vì dữ liệu đã tách khỏi persistence context không?
10. Phiên bản Jakarta Persistence/provider có hỗ trợ record embeddable hoặc composite key cần dùng không?

## 11. Bài tập vận dụng

**Bài 1 — Giới hạn kế thừa:** Tạo record `CustomerId` và thử viết class kế thừa nó. Quan sát lỗi biên dịch. Sau đó định nghĩa interface `Identified` và cho record triển khai interface.

**Bài 2 — JDK dynamic proxy:** Tạo interface `PriceSource` và record `FixedPrice`. Dùng `Proxy.newProxyInstance` để bọc target record. Kiểm tra `instanceof PriceSource` và `instanceof FixedPrice`, giải thích kết quả.

**Bài 3 — Spring AOP:** Tạo một service interface và một implementation. So sánh interface-based proxy với class-based proxy. Giải thích tại sao record không thể là target cho CGLIB subclass proxy.

**Bài 4 — Entity và value object:** Tạo `SupplierEntity` có ID và phương thức thay đổi địa chỉ. Tạo `SupplierView` record để trả dữ liệu ra API. Viết mapper và giải thích vòng đời của hai object.

**Bài 5 — Persistence record:** Dựa trên Jakarta Persistence 3.2, tạo record `Address` làm embeddable hoặc record khóa ghép. Phân biệt kiểu đó với entity class có identity và persistence lifecycle.

---

## Tài liệu tham khảo

- [Java Language Specification, Java SE 16 — Record Classes](https://docs.oracle.com/javase/specs/jls/se16/html/jls-8.html): record class là final và có superclass trực tiếp là `java.lang.Record`.
- [Java SE API — java.lang.reflect.Proxy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Proxy.html): dynamic proxy triển khai các interface được chỉ định.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): record không được chỉ định làm entity; entity class cần non-final và no-args constructor, đồng thời record có thể làm embeddable.
- [Jakarta Persistence 3.2 Specification — Embeddable Classes](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html#embeddable-classes): record có thể làm embeddable.
- [Spring Framework Reference — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): Spring AOP sử dụng JDK dynamic proxy hoặc CGLIB; CGLIB không thể proxy class final.
- [Hibernate ORM User Guide — Prefer non-final classes](https://docs.hibernate.org/stable/orm/userguide/html_single/): class final làm hạn chế proxy cho lazy loading; hướng dẫn về entity và embeddable.

---

**Ghi nhớ:** Record là value-oriented và final; entity ORM thường cần identity, persistence lifecycle và khả năng được provider quản lý. Proxy subclass không thể kế thừa record, nhưng interface proxy có thể bọc target record nếu record triển khai interface. Hãy dùng record cho DTO, value object, snapshot, embeddable hoặc composite key theo phiên bản persistence hỗ trợ; dùng class entity riêng cho đối tượng có lifecycle được ORM quản lý.
