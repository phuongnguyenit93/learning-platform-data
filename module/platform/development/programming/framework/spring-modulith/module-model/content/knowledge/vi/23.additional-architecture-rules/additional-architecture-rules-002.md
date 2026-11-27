# DDD architecture rules khi thư viện có trên classpath

Spring Modulith không chỉ kiểm tra ranh giới giữa các application module. Khi thư viện jMolecules ArchUnit và mô hình DDD tương ứng có mặt trên classpath, các lần gọi `ApplicationModules.verify()` hoặc `detectViolations()` còn tự động chạy bộ quy tắc DDD của jMolecules.

Điều này giúp nhóm kiểm tra một tầng kiến trúc khác: các entity, aggregate root, value object và association có tuân theo những quan hệ mà mô hình DDD đã khai báo hay không. Việc kích hoạt dựa trên classpath nên một bài test module có thể bắt đầu kiểm tra thêm các quy tắc DDD sau khi nhóm thêm dependency. Bài học này giải thích điều kiện kích hoạt, nhóm quy tắc được áp dụng, cách đọc lỗi và cách bổ sung các quy tắc layering, onion hoặc hexagonal khi dự án cần.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt quy tắc module mặc định của Spring Modulith với quy tắc DDD do jMolecules bổ sung.
- Xác định dependency cần có để kích hoạt tự động DDD verification.
- Giải thích các quy tắc về identity, quyền sở hữu entity, tham chiếu giữa aggregate và value object.
- Dùng annotation hoặc type-based model của jMolecules để mô tả domain model.
- Chẩn đoán lỗi khi dependency DDD hoặc ArchUnit thiếu trên classpath.
- Bổ sung quy tắc hexagonal, layered hoặc onion bằng `VerificationOptions`.
- Đưa kiểm tra kiến trúc vào test và CI để phát hiện vi phạm sớm.

## Hai nhóm quy tắc chạy trong một lần verification

Spring Modulith luôn kiểm tra cấu trúc application module theo mô hình của nó. Các quy tắc cốt lõi gồm:

- Đồ thị dependency giữa các module không có chu trình.
- Module khác chỉ được tham chiếu type nằm trong API package được công bố; truy cập package nội bộ bị từ chối, trừ trường hợp module được mở.
- Nếu module khai báo `allowedDependencies`, các dependency phải tuân theo danh sách đó.

Đây là các quy tắc bảo vệ ranh giới package và module. Chúng không tự xác minh rằng một aggregate có identity, một entity thuộc đúng aggregate root hay một value object tránh tham chiếu entity.

Khi jMolecules ArchUnit có trên classpath, Spring Modulith tích hợp thêm bộ DDD verification của jMolecules. Vì vậy, một lệnh:

```java
ApplicationModules.of(Application.class).verify();
```

có thể thực hiện cả hai nhóm kiểm tra. Nếu không có integration tương ứng trên classpath, Spring Modulith vẫn kiểm tra module như bình thường; phần DDD bổ sung không được kích hoạt.

`detectViolations()` cũng sử dụng các verification mặc định dựa trên classpath. Vì vậy, việc chuyển từ `verify()` sang `detectViolations()` để lọc hoặc báo cáo vi phạm không tự tắt quy tắc DDD.

## Dependency nào kích hoạt DDD rules?

Spring Modulith tích hợp với artifact `org.jmolecules.integrations:jmolecules-archunit`. Để mô tả domain model bằng annotation hoặc interface, dự án còn cần artifact vocabulary như `org.jmolecules:jmolecules-ddd`.

Nếu mã nguồn production dùng annotation DDD, hãy đặt `jmolecules-ddd` trên compile classpath. `jmolecules-archunit` thường được đặt ở test scope để các quy tắc chạy khi test kiến trúc được thực thi.

Ví dụ Gradle:

```groovy
dependencies {
    implementation("org.jmolecules:jmolecules-ddd")
    testImplementation("org.jmolecules.integrations:jmolecules-archunit")
}
```

Ví dụ Maven:

```xml
<dependency>
    <groupId>org.jmolecules</groupId>
    <artifactId>jmolecules-ddd</artifactId>
</dependency>

<dependency>
    <groupId>org.jmolecules.integrations</groupId>
    <artifactId>jmolecules-archunit</artifactId>
    <scope>test</scope>
</dependency>
```

Hãy quản lý phiên bản tương thích bằng BOM của jMolecules và Spring Modulith theo dependency management của dự án. Các dependency jMolecules được Spring Modulith khai báo ở dạng optional; không nên giả định chỉ thêm `spring-modulith-core` là đã kéo theo toàn bộ thư viện DDD và ArchUnit cần thiết.

`jmolecules-archunit` cũng khai báo các vocabulary artifact như `jmolecules-ddd` ở dạng optional. Nếu domain code dùng annotation hoặc interface DDD, khai báo `jmolecules-ddd` trực tiếp để bảo đảm type có trên compile classpath và test runtime. Nếu thiếu vocabulary nhưng ArchUnit integration đã được nạp, một số tổ hợp phiên bản có thể gặp lỗi thiếu class khi khởi tạo bộ quy tắc.

Nếu chỉ thêm `jmolecules-ddd` mà không có `jmolecules-archunit`, nhóm có thể dùng các annotation và interface trong source code, nhưng Spring Modulith không có integration ArchUnit để tự chạy DDD rules.

## jMolecules biểu diễn mô hình DDD như thế nào?

jMolecules cung cấp hai cách diễn đạt domain model:

1. **Annotation-based model:** đánh dấu class hoặc field bằng annotation như `@AggregateRoot`, `@Entity`, `@Identity`, `@ValueObject` và `@Association`.
2. **Type-based model:** triển khai các interface như `AggregateRoot<T, ID>`, `Entity<T, ID>`, `Identifier` và `Association<T, ID>` để thể hiện quan hệ trực tiếp trong hệ thống kiểu của Java.

Hai cách đều giúp công cụ nhận biết ý nghĩa DDD trong mã nguồn. Type-based model có thể diễn đạt quan hệ sở hữu aggregate và kiểu identifier ngay trong generic type; annotation-based model ít thay đổi cấu trúc kế thừa hiện có hơn.

Ví dụ annotation-based:

```java
import java.util.UUID;

import org.jmolecules.ddd.annotation.AggregateRoot;
import org.jmolecules.ddd.annotation.Identity;

record OrderId(UUID value) {}

@AggregateRoot
class Order {

    @Identity
    private final OrderId id;

    Order(OrderId id) {
        this.id = id;
    }
}
```

Ví dụ type-based:

```java
import java.util.UUID;

import org.jmolecules.ddd.types.Association;
import org.jmolecules.ddd.types.AggregateRoot;
import org.jmolecules.ddd.types.Identifier;

record OrderId(UUID value) implements Identifier {}

class Order implements AggregateRoot<Order, OrderId> {

    private final OrderId id;

    Order(OrderId id) {
        this.id = id;
    }

    @Override
    public OrderId getId() {
        return id;
    }
}
```

Trong ví dụ type-based, `Order` khai báo rõ mình là aggregate root và `OrderId` là kiểu định danh của aggregate đó. Compiler có thể kiểm tra một phần quan hệ kiểu; jMolecules ArchUnit bổ sung kiểm tra cấu trúc trên tập class đã phân tích.

## Những quy tắc DDD thường được kiểm tra

Bộ quy tắc `JMoleculesDddRules.all()` tập trung vào các ràng buộc giữa những building block DDD mà jMolecules nhận diện. Các nhóm lỗi thường gặp gồm:

### Entity và aggregate root phải có identity

Entity có vòng đời và định danh riêng. Aggregate root cũng là một entity và cần một identity rõ ràng. Với annotation model, identity thường được đánh dấu bằng `@Identity` trên field hoặc method. Với type-based model, entity cung cấp kiểu ID thông qua `Identifiable<ID>` hoặc các interface kế thừa.

Ví dụ lỗi:

```java
@AggregateRoot
class Order {
    private String number;
}
```

Nếu `number` là định danh của đơn hàng, hãy khai báo nó như identity theo mô hình jMolecules:

```java
@AggregateRoot
class Order {

    @Identity
    private final OrderId id;
}
```

Tên một field như `id` hoặc `number` tự nó không đủ để công cụ kết luận đây là identity nếu mô hình không đánh dấu theo cách jMolecules nhận diện.

### Entity phải thuộc một aggregate root xác định

Aggregate root xác định ranh giới nhất quán. Entity bên trong aggregate cần được khai báo là thuộc về aggregate root đó. Type-based model diễn đạt điều này bằng tham số generic đầu tiên của `Entity<T, ID>`:

```java
import java.util.UUID;

import org.jmolecules.ddd.types.Entity;
import org.jmolecules.ddd.types.Identifier;

record OrderLineId(UUID value) implements Identifier {}

class OrderLine implements Entity<Order, OrderLineId> {

    private final OrderLineId id;

    @Override
    public OrderLineId getId() {
        return id;
    }
}
```

`OrderLine` khai báo rõ nó thuộc aggregate `Order`. Nhờ đó, công cụ có thể phát hiện một entity được sử dụng từ aggregate không sở hữu nó hoặc một quan hệ ownership không nhất quán với mô hình đã khai báo.

### Aggregate khác nhau tham chiếu nhau qua identity hoặc Association

Một aggregate không nên giữ trực tiếp object reference đến aggregate root khác như thể hai object thuộc cùng một consistency boundary. Tham chiếu chéo aggregate nên đi qua identity hoặc `Association`.

Ví dụ type-based:

```java
import java.util.UUID;

import org.jmolecules.ddd.types.Association;
import org.jmolecules.ddd.types.AggregateRoot;
import org.jmolecules.ddd.types.Identifier;

record OrderId(UUID value) implements Identifier {}
record CustomerId(UUID value) implements Identifier {}

class Customer implements AggregateRoot<Customer, CustomerId> {

    private final CustomerId id;

    @Override
    public CustomerId getId() {
        return id;
    }
}

class Order implements AggregateRoot<Order, OrderId> {

    private final OrderId id;
    private final Association<Customer, CustomerId> customer;

    Order(OrderId id, CustomerId customerId) {
        this.id = id;
        this.customer = Association.forId(customerId);
    }

    @Override
    public OrderId getId() {
        return id;
    }
}
```

`Order` giữ association đến `Customer` bằng identity. Nó không giữ trực tiếp một object `Customer` có vòng đời và consistency boundary riêng.

Mô hình annotation cũng có thể dùng annotation `@Association` để đánh dấu quan hệ đến aggregate khác. Cách khai báo cụ thể cần tuân theo API annotation và phiên bản jMolecules mà dự án đang dùng.

### Value object không tham chiếu identifiable

Value object được xác định bằng giá trị và không có identity độc lập. Vì vậy, một value object không nên chứa tham chiếu trực tiếp đến entity hoặc aggregate có identity.

Ví dụ không phù hợp:

```java
import org.jmolecules.ddd.annotation.ValueObject;

@ValueObject
record ShippingPreference(String instructions, Customer customer) {}
```

`Customer` là aggregate có identity. Đưa object đó vào value object khiến value object phụ thuộc vào một đối tượng có vòng đời riêng. Hãy xem lại mô hình: giữ các giá trị thực sự thuộc `ShippingPreference` trong value object và đặt association đến aggregate ở vị trí thích hợp trong aggregate sở hữu nó.

Các ràng buộc này giúp mô hình domain thể hiện rõ consistency boundary và giảm việc chia sẻ object graph giữa các aggregate.

## Bài test Spring Modulith tự chạy DDD rules

Sau khi khai báo các dependency cần thiết, nhóm không cần tự gọi `JMoleculesDddRules.all()` trong một ArchUnit test riêng nếu mục tiêu là dùng integration mặc định của Spring Modulith.

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleAndDddArchitecture() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

Khi `jmolecules-archunit` và vocabulary DDD phù hợp có trên test runtime classpath, `verify()` sẽ áp dụng thêm DDD verification. Nếu có vi phạm, test thất bại và thông báo chỉ ra class hoặc field liên quan.

Nếu muốn lấy kết quả để in hoặc lọc, có thể dùng:

```java
var violations = ApplicationModules.of(Application.class)
    .detectViolations();

violations.getMessages().forEach(System.err::println);
violations.throwIfPresent();
```

`detectViolations()` cũng xét các verification mặc định theo classpath. Nếu chỉ in thông báo mà không gọi `throwIfPresent()` hoặc assertion tương ứng, test có thể vẫn xanh dù có lỗi DDD.

## Quy tắc layering, onion và hexagonal không tự động giống DDD rules

`jmolecules-archunit` cung cấp nhiều bộ quy tắc kiến trúc. Tuy nhiên, việc Spring Modulith tự động kích hoạt bộ DDD rules khi dependency có mặt không đồng nghĩa mọi quy tắc layered, onion hoặc hexagonal đều tự động chạy.

Nếu muốn kiểm tra kiến trúc hexagonal, hãy đăng ký quy tắc một cách tường minh:

```java
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.jmolecules.archunit.VerificationDepth;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

var hexagonal = JMoleculesArchitectureRules.ensureHexagonal(
    VerificationDepth.STRICT
);

var options = VerificationOptions.defaults()
    .andAdditionalVerifications(hexagonal);

ApplicationModules.of(Application.class).verify(options);
```

Ví dụ này giữ các verification mặc định, bao gồm DDD rules nếu có trên classpath, rồi thêm quy tắc hexagonal ở chế độ strict. Tùy phiên bản jMolecules, API cũng cung cấp các lựa chọn để kiểm tra layered hoặc onion architecture.

Hãy phân biệt hai cách cấu hình:

| API | Tác dụng |
|---|---|
| `VerificationOptions.defaults()` | Tạo cấu hình mặc định và bao gồm jMolecules verification nếu thư viện có trên classpath |
| `andAdditionalVerifications(rule)` | Thêm quy tắc mới bên cạnh các quy tắc mặc định |
| `withAdditionalVerifications(rule)` | Định nghĩa tập quy tắc bổ sung thay thế, vô hiệu hóa tập mặc định |
| `withoutAdditionalVerifications()` | Tắt các verification bổ sung được đăng ký mặc định |

Nếu dùng `withAdditionalVerifications()` hoặc `withoutAdditionalVerifications()` mà không chủ ý, nhóm có thể vô tình bỏ các DDD rules tự động. Khi muốn giữ mặc định và bổ sung rule mới, ưu tiên `andAdditionalVerifications()`.

## Đọc và xử lý vi phạm DDD

Thông báo vi phạm cần được đọc cùng với building block mà nhóm đã khai báo. Ví dụ:

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Aggregate root thiếu identity | Chưa đánh dấu field hoặc method định danh | Khai báo `@Identity` hoặc cung cấp ID qua type-based model |
| Entity không xác định aggregate sở hữu | Thiếu quan hệ ownership hoặc khai báo sai generic type | Xác định aggregate root thực sự sở hữu entity |
| Aggregate tham chiếu trực tiếp aggregate khác | Object graph vượt qua consistency boundary | Dùng identifier hoặc `Association` |
| Value object chứa entity/aggregate | Value object phụ thuộc vào object có identity | Tách giá trị cần thiết và đặt association ở aggregate phù hợp |
| Lỗi xuất hiện sau khi thêm dependency | DDD verification được kích hoạt theo classpath | Đọc violation và quyết định sửa model hay điều chỉnh phạm vi dependency có chủ đích |

Không nên xóa dependency ArchUnit chỉ để test xanh nếu dự án chủ động muốn thực thi DDD. Nếu nhóm chưa sẵn sàng áp dụng DDD rules cho toàn bộ codebase, hãy xác định phạm vi mô hình được kiểm tra hoặc có kế hoạch chuyển đổi rõ ràng. Việc bỏ integration sẽ làm mất hàng rào DDD cho tất cả phần mã nằm trong phạm vi scan.

## Những lỗi cấu hình thường gặp

| Lỗi | Kết quả | Cách xử lý |
|---|---|---|
| Chỉ thêm `spring-modulith-core` | jMolecules optional dependencies có thể không được đưa vào ứng dụng | Khai báo trực tiếp artifact cần dùng |
| Có `jmolecules-ddd` nhưng thiếu `jmolecules-archunit` | Có thể dùng annotation nhưng không tự chạy ArchUnit DDD rules | Thêm `jmolecules-archunit` vào test runtime classpath |
| Có ArchUnit integration nhưng thiếu DDD vocabulary | Thiếu annotation/interface hoặc có thể gặp lỗi class khi khởi tạo rules | Thêm `jmolecules-ddd` và quản lý phiên bản tương thích |
| Chỉ chạy test compile | Không thực thi `ApplicationModules.verify()` | Đặt verification trong test được CI chạy |
| Dùng `withAdditionalVerifications()` khi muốn bổ sung | Tập rule mặc định có thể bị thay thế | Dùng `andAdditionalVerifications()` |
| Nghĩ layering/onion/hexagonal tự chạy cùng DDD | Các quy tắc đó có thể chưa được đăng ký | Tạo `ArchRule` và thêm bằng `VerificationOptions` |

## Quy trình đưa DDD rules vào CI

1. Chọn cách biểu diễn DDD: annotation-based hoặc type-based, phù hợp với cấu trúc domain hiện có.
2. Thêm `jmolecules-ddd` vào compile classpath nếu production source sử dụng vocabulary này.
3. Thêm `jmolecules-archunit` vào test runtime classpath và quản lý phiên bản bằng BOM tương thích.
4. Viết test `ApplicationModules.of(Application.class).verify()` để kiểm tra cả module boundaries và DDD rules mặc định.
5. Đọc thông báo vi phạm và sửa identity, aggregate ownership, association hoặc value object theo đúng mô hình nghiệp vụ.
6. Nếu cần layering, onion hoặc hexagonal verification, đăng ký riêng bằng `VerificationOptions`.
7. Đưa test vào task verification bắt buộc của CI để thay đổi vi phạm làm pull request thất bại.
8. Khi cập nhật phiên bản Spring Modulith hoặc jMolecules, chạy lại test và xem xét các thay đổi trong rule set.

## Bài tập tự đánh giá

Một ứng dụng có hai aggregate `Order` và `Customer`. `Order` được đánh dấu `@AggregateRoot` nhưng không có field hoặc method identity được đánh dấu. Nó giữ trực tiếp một object `Customer`. Ngoài ra, `ShippingAddress` được đánh dấu `@ValueObject` nhưng lại chứa một field `Customer`.

Sau khi nhóm thêm `jmolecules-archunit` và `jmolecules-ddd`, test `ApplicationModules.of(Application.class).verify()` bắt đầu thất bại.

Hãy trả lời:

1. Vì sao cùng một test module lại bắt đầu phát hiện lỗi DDD sau khi dependency được thêm?
2. `Order` cần khai báo identity như thế nào?
3. Vì sao giữ trực tiếp `Customer` trong `Order` vượt qua ranh giới aggregate?
4. Vì sao `ShippingAddress` không nên chứa object `Customer`?
5. Nếu nhóm muốn kiểm tra thêm hexagonal architecture, cần thay đổi `VerificationOptions` ra sao?

Một hướng sửa là khai báo `OrderId` làm identity của `Order`, thay tham chiếu trực tiếp `Customer` bằng `CustomerId` hoặc `Association<Customer, CustomerId>`, và giữ `ShippingAddress` chỉ chứa các giá trị địa chỉ. Khi cần hexagonal verification, tạo rule bằng `JMoleculesArchitectureRules.ensureHexagonal(VerificationDepth.STRICT)` rồi thêm nó bằng `andAdditionalVerifications()` để giữ nguyên các DDD rules mặc định.

## Kết luận

Spring Modulith tự động bổ sung DDD verification khi jMolecules ArchUnit và vocabulary DDD cần thiết có trên classpath. Các quy tắc giúp kiểm tra identity, quyền sở hữu entity, tham chiếu giữa aggregate và tính độc lập của value object. Những quy tắc layered, onion hoặc hexagonal cần được đăng ký riêng khi dự án muốn áp dụng. Hãy quản lý dependency rõ ràng, dùng `VerificationOptions` đúng ý định và chạy `ApplicationModules.verify()` trong CI để giữ cả module boundary lẫn domain model nhất quán.

## Tài liệu tham khảo

- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith API — `VerificationOptions`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)
- [jMolecules — Domain-Driven Design Model](https://github.com/xmolecules/jmolecules)
- [jMolecules Integrations — ArchUnit Rules](https://github.com/xmolecules/jmolecules-integrations/tree/main/jmolecules-archunit)
- [Maven Central — `jmolecules-archunit`](https://central.sonatype.com/artifact/org.jmolecules.integrations/jmolecules-archunit)
