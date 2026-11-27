# Phân biệt rule Modulith với rule jMolecules

Spring Modulith và jMolecules đều có thể kiểm tra kiến trúc của một ứng dụng Java, nhưng chúng tập trung vào những câu hỏi khác nhau. **Rule của Spring Modulith kiểm tra ranh giới giữa các application module**; **rule DDD của jMolecules kiểm tra cách mô hình hóa các building block trong domain**; còn **rule kiến trúc của jMolecules kiểm tra hướng phụ thuộc giữa các layer, ring hoặc port/adapter**.

Ba nhóm rule có thể bổ sung cho nhau trong cùng một bài kiểm thử. Tuy nhiên, không nên coi chúng là cùng một bộ kiểm tra hoặc cho rằng Spring Modulith tự động chạy tất cả rule mà jMolecules cung cấp.

## 1. Ba phạm vi kiểm tra khác nhau

Giả sử ứng dụng bán hàng có các application module `orders`, `catalog` và `inventory`. Bên trong mỗi module, code còn được chia thành domain, application và infrastructure.

```text
com.example.shop
├── orders
│   ├── Order.java
│   ├── application
│   └── infrastructure
├── catalog
│   ├── Product.java
│   └── infrastructure
└── inventory
    ├── Stock.java
    └── infrastructure
```

Ta có thể đặt câu hỏi ở ba cấp độ:

| Nhóm rule | Câu hỏi chính | Phạm vi |
|---|---|---|
| Spring Modulith | Module nào được phụ thuộc vào module nào? Consumer có truy cập internal package không? Có chu trình module không? | Application module và package boundary |
| jMolecules DDD | Aggregate, entity, identity, association và value object có tuân theo quan hệ DDD đã khai báo không? | Domain model và quan hệ giữa các building block |
| jMolecules Architecture | Domain, application, infrastructure hoặc port/adapter có phụ thuộc đúng chiều không? | Layer, onion ring hoặc hexagonal role |

Ví dụ, `orders` import `catalog.internal.ProductRepository` là vấn đề boundary của Spring Modulith. `Order` giữ tham chiếu trực tiếp đến một aggregate `Customer` khác là vấn đề mô hình DDD. Một class domain phụ thuộc vào adapter cơ sở dữ liệu là vấn đề hướng phụ thuộc của kiến trúc layered/onion/hexagonal.

## 2. Spring Modulith kiểm tra ranh giới application module

`ApplicationModules.verify()` kiểm tra mô hình module được phát hiện từ package của ứng dụng. Các quy tắc cốt lõi gồm:

1. **Không có chu trình ở cấp module:** dependency giữa các application module phải tạo thành directed acyclic graph (DAG).
2. **Truy cập module khác qua API:** module không được tham chiếu type trong sub-package nội bộ của một closed module. Base package là API mặc định; named interface có thể công khai một sub-package có chọn lọc.
3. **Tuân thủ allow-list nếu có khai báo:** khi module đặt `allowedDependencies`, dependency thực tế phải nằm trong danh sách module hoặc named interface được cho phép.

Ví dụ, `orders` chỉ được phép dùng API truy vấn của `catalog`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog::query"
)
package com.example.shop.orders;
```

Nếu `orders` import type trong `catalog.internal`, verification có thể báo lỗi vì consumer đang truy cập phần triển khai nội bộ. Nếu `orders` tạo dependency tới module không nằm trong allow-list, verification cũng báo vi phạm. Nếu `orders` và `catalog` phụ thuộc lẫn nhau, kiểm tra DAG phát hiện chu trình.

Đây là các quy tắc về **module arrangement và dependency giữa module**. Chúng không kiểm tra một aggregate có identity hay một value object có tham chiếu entity khác hay không.

## 3. jMolecules DDD rules kiểm tra mô hình miền

jMolecules cung cấp annotation và type để diễn đạt các khái niệm DDD như `@AggregateRoot`, `@Entity`, `@ValueObject`, `@Identity`, `Association`, `Identifier` và `Repository`. Những metadata này cho phép công cụ phân tích các quan hệ trong domain model.

`JMoleculesDddRules.all()` là bộ ArchUnit rule dành cho các ràng buộc DDD. Những vi phạm điển hình gồm:

- Entity hoặc aggregate root thiếu khai báo identity.
- Entity khai báo không đúng aggregate root sở hữu nó.
- Aggregate root hoặc entity tham chiếu trực tiếp aggregate root khác thay vì dùng identifier hoặc `Association`.
- Value object hoặc identifier tham chiếu tới identifiable/entity, làm rò rỉ quan hệ identity vào một kiểu dữ liệu vốn nên biểu đạt giá trị.

Ví dụ, mô hình sau có tham chiếu trực tiếp giữa hai aggregate:

```java
@AggregateRoot
class Order {

    @Identity
    private OrderId id;

    // Không nên giữ trực tiếp một aggregate khác.
    private Customer customer;
}
```

Có thể biểu diễn quan hệ bằng identifier hoặc `Association`:

```java
@AggregateRoot
class Order {

    @Identity
    private OrderId id;

    private Association<Customer, CustomerId> customer;
}
```

Với mô hình type-based, jMolecules còn diễn đạt quan hệ aggregate ownership và identifier trong generic type:

```java
class Order implements AggregateRoot<Order, OrderId> {
    // Aggregate root có identifier riêng.
}

class OrderLine implements Entity<Order, OrderLineId> {
    // Entity khai báo aggregate root mà nó thuộc về.
}
```

Những quy tắc này giúp domain model giữ được consistency boundary và tránh liên kết object graph trực tiếp giữa các aggregate. Chúng không thay thế quy tắc Spring Modulith về module nào được phép import package của module khác.

## 4. jMolecules Architecture rules kiểm tra layering, onion và hexagonal

Ngoài DDD building block rules, jMolecules cung cấp các rule kiến trúc riêng trong `JMoleculesArchitectureRules`. Các rule này sử dụng stereotype/annotation để xác định vai trò của class và kiểm tra hướng phụ thuộc.

### Layered architecture

Với layered architecture, jMolecules có các stereotype như:

- `@InterfaceLayer`
- `@ApplicationLayer`
- `@DomainLayer`
- `@InfrastructureLayer`

`JMoleculesArchitectureRules.ensureLayering()` kiểm tra dependency theo thứ tự layer đã khai báo. Biến thể `ensureLayeringStrict()` áp dụng hướng phụ thuộc chặt hơn, chỉ cho phép truy cập layer kế tiếp trong chuỗi.

Ví dụ, nếu domain layer phụ thuộc trực tiếp vào controller hoặc adapter của infrastructure, rule layering có thể báo lỗi tùy theo cách các class được đánh dấu.

### Onion architecture

Với onion architecture, các ring thường được biểu diễn bằng `@DomainRing`, `@ApplicationRing` và `@InfrastructureRing` (hoặc các stereotype tương ứng của classical onion). `ensureOnionSimple()` và `ensureOnionClassical()` kiểm tra quy tắc dependency giữa các ring và ranh giới của architectural unit.

Mô hình onion hướng dependency từ vòng ngoài vào lõi: infrastructure có thể phụ thuộc application, application có thể phụ thuộc domain; domain không nên phụ thuộc ngược vào infrastructure.

### Hexagonal architecture

Với hexagonal architecture, jMolecules cung cấp các stereotype như `@Application`, `@Port`, `@PrimaryPort`, `@SecondaryPort`, `@Adapter`, `@PrimaryAdapter` và `@SecondaryAdapter`. `ensureHexagonal()` kiểm tra cách application, port và adapter tham chiếu nhau, bao gồm các quy tắc exposure/referrer giữa những hexagon được đánh dấu.

Các rule này trả lời câu hỏi về **cấu trúc bên trong một module hoặc một architectural unit**. Spring Modulith không thể tự suy ra dự án muốn áp dụng layered, onion hay hexagonal chỉ từ package module, nên những rule đó cần được chọn và đăng ký tường minh.

## 5. Điều gì được Spring Modulith tự động tích hợp từ jMolecules?

Spring Modulith có tích hợp tùy chọn với thư viện `jmolecules-archunit`. Khi thư viện phù hợp có mặt trên classpath, `VerificationOptions.defaults()` đưa các **DDD verification rules** của jMolecules vào nhóm kiểm tra bổ sung mặc định.

Điểm cần nhớ: tích hợp mặc định này không có nghĩa Spring Modulith tự chạy mọi phương thức của `JMoleculesArchitectureRules`. Các rule như `ensureLayering()`, `ensureOnionSimple()` hoặc `ensureHexagonal()` là lựa chọn kiến trúc cụ thể của dự án và phải được đăng ký riêng.

Có thể tóm tắt:

| Rule | Được chạy bởi `ApplicationModules.verify()` mặc định? | Cách bật |
|---|---|---|
| Module graph không chu kỳ | Có | Quy tắc cốt lõi Spring Modulith |
| Không truy cập internal package của closed module | Có | Quy tắc cốt lõi Spring Modulith |
| `allowedDependencies` | Có, nếu module khai báo allow-list | `@ApplicationModule(allowedDependencies = …)` |
| jMolecules DDD rules | Có, nếu tích hợp `jmolecules-archunit` có mặt và được nhận diện trên classpath | `VerificationOptions.defaults()` |
| jMolecules layered rules | Không tự động | Đăng ký `JMoleculesArchitectureRules.ensureLayering()` hoặc biến thể strict |
| jMolecules onion rules | Không tự động | Đăng ký `ensureOnionSimple()` hoặc `ensureOnionClassical()` |
| jMolecules hexagonal rules | Không tự động | Đăng ký `ensureHexagonal()` |

Vì vậy, một dự án dùng `@DomainLayer` hoặc `@Hexagon` không nên cho rằng chỉ gọi `ApplicationModules.verify()` là các quan hệ layer/port/adapter đã được kiểm tra. Hãy thêm rule kiến trúc tương ứng vào `VerificationOptions`.

## 6. Kết hợp rule Modulith và jMolecules trong một lần kiểm tra

Giả sử dự án muốn kiểm tra module boundary của Spring Modulith và đồng thời áp dụng onion architecture. Ta có thể thêm onion rule vào các verification mặc định:

```java
package com.example.shop;

import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ArchitectureTests {

    @Test
    void verifiesModulesAndOnionArchitecture() {
        VerificationOptions options = VerificationOptions.defaults()
                .andAdditionalVerifications(
                        JMoleculesArchitectureRules.ensureOnionSimple());

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
```

Kết quả bao gồm:

- Quy tắc module của Spring Modulith: DAG, API/internal package và allow-list.
- jMolecules DDD rules mặc định nếu tích hợp có mặt trên classpath.
- Onion architecture rule do dự án chủ động đăng ký.

Nếu dự án theo layered architecture, có thể thay `ensureOnionSimple()` bằng `ensureLayering()` hoặc `ensureLayeringStrict()`. Nếu theo hexagonal architecture, hãy dùng `ensureHexagonal()` và khai báo các stereotype port/adapter phù hợp. Chỉ chọn rule phản ánh kiến trúc mà nhóm thực sự muốn duy trì; không cần bật đồng thời các kiểu kiến trúc có quy tắc xung đột.

## 7. Cẩn thận với andAdditionalVerifications và withAdditionalVerifications

Hai phương thức này ảnh hưởng trực tiếp đến các rule jMolecules mặc định:

```java
VerificationOptions options = VerificationOptions.defaults()
        .andAdditionalVerifications(
                JMoleculesArchitectureRules.ensureLayering());
```

`andAdditionalVerifications(...)` thêm rule mới trên tập kiểm tra bổ sung mặc định. Đây là cách phù hợp nếu muốn giữ DDD rules được Spring Modulith tích hợp và bổ sung layered/onion/hexagonal rule.

Ngược lại:

```java
VerificationOptions options = VerificationOptions.defaults()
        .withAdditionalVerifications(
                JMoleculesArchitectureRules.ensureLayering());
```

`withAdditionalVerifications(...)` thay thế tập kiểm tra bổ sung mặc định bằng rule được truyền vào. Nếu jMolecules DDD rules đang được tự động đưa vào từ classpath, cách này có thể làm chúng không còn được chạy trong lần verification đó.

Nếu chỉ muốn tắt nhóm kiểm tra bổ sung mặc định, `withoutAdditionalVerifications()` sẽ làm việc đó; các quy tắc cốt lõi của Spring Modulith vẫn được thực thi. Không dùng phương thức này nếu mục tiêu là bỏ kiểm tra module cycle hoặc internal package, vì nó không tắt những quy tắc cốt lõi đó.

## 8. Dependency cần thiết và phạm vi classpath

Để Spring Modulith tích hợp jMolecules DDD rules, `jmolecules-archunit` cần có trên classpath kiểm tra. Khi dùng DDD rules, hãy bảo đảm các annotation/type DDD tương ứng như `jmolecules-ddd` cũng có mặt. Các artifact architecture như layered, onion hoặc hexagonal cần được thêm tương ứng nếu dự án sử dụng rule của kiểu kiến trúc đó.

Ví dụ Gradle cho một test suite dùng DDD và onion:

```kotlin
dependencies {
    testImplementation("org.jmolecules.integrations:jmolecules-archunit")
    testImplementation("org.jmolecules:jmolecules-ddd")
    testImplementation("org.jmolecules:jmolecules-onion-architecture")
}
```

Hãy quản lý phiên bản thông qua BOM tương thích của Spring Modulith/jMolecules hoặc dependency management hiện có. Không thêm artifact chỉ để làm cho test chạy qua nếu dự án không sử dụng các annotation và mô hình tương ứng.

Nếu rule không xuất hiện như mong đợi, hãy kiểm tra test runtime classpath, phiên bản `jmolecules-archunit`, artifact chứa annotation DDD/architecture và cách tạo `VerificationOptions`. Annotation có trong source code nhưng thiếu thư viện ArchUnit tích hợp sẽ không tự tạo ra một lần kiểm tra.

## 9. Ví dụ: một lỗi, hai góc nhìn

Giả sử `orders` dùng `catalog.ProductCatalog` ở API công khai và tuân thủ allow-list. Tuy nhiên, trong domain model, `Order` giữ trực tiếp một tham chiếu tới aggregate `Customer`.

Kết quả có thể là:

| Kiểm tra | Kết quả | Lý do |
|---|---|---|
| Spring Modulith module boundary | PASS | `orders` truy cập API hợp lệ của module được cho phép |
| jMolecules DDD | FAIL | `Order` tham chiếu trực tiếp aggregate khác thay vì identifier/`Association` |
| jMolecules layered/onion | Tùy cấu trúc | Phụ thuộc vào stereotype layer/ring và hướng dependency thực tế |

Chiều ngược lại cũng có thể xảy ra. Domain model tuân thủ các DDD rule, nhưng module `orders` import `catalog.internal.ProductRepository`. jMolecules DDD có thể không phát hiện vi phạm đó, trong khi Spring Modulith báo lỗi internal package access.

Đây là lý do cần kết hợp các nhóm rule theo mục tiêu: không có một bộ rule đơn lẻ nào thay thế được các phạm vi còn lại.

## 10. Cách đọc và xử lý violation

Khi verification thất bại, hãy xác định rule nào phát hiện vấn đề trước khi sửa code:

| Dấu hiệu violation | Nhóm rule cần xem | Hướng xử lý |
|---|---|---|
| Dependency cycle giữa `orders` và `inventory` | Spring Modulith | Phá chu trình, xem lại quyền sở hữu use case và hướng event/call |
| Import `catalog.internal.*` | Spring Modulith | Dùng base package API hoặc named interface được công khai |
| Dependency tới module không có trong allow-list | Spring Modulith | Điều chỉnh hướng phụ thuộc hoặc khai báo quyền cần thiết một cách có chủ đích |
| Aggregate thiếu identity | jMolecules DDD | Khai báo identity đúng theo mô hình domain |
| Aggregate tham chiếu trực tiếp aggregate khác | jMolecules DDD | Dùng identifier hoặc `Association` |
| Domain layer phụ thuộc infrastructure | jMolecules layered/onion | Đảo chiều phụ thuộc qua port/interface hoặc chuyển trách nhiệm về đúng layer |
| Primary/secondary adapter dùng sai vai trò | jMolecules hexagonal | Sửa stereotype và quan hệ port/adapter theo use case |

Nếu dùng `ApplicationModules.detectViolations(options)`, có thể lấy kết quả violation để phân tích trước khi gọi `throwIfPresent()`. Tuy nhiên, việc lọc bỏ violation chỉ nên dùng khi có lý do và phạm vi ngoại lệ rõ ràng; nó không sửa nguyên nhân kiến trúc.

## 11. Quy trình lựa chọn rule cho dự án

1. Xác định ranh giới nghiệp vụ và package của application module.
2. Dùng `ApplicationModules.verify()` để bảo vệ DAG, API/internal package và allow-list.
3. Nếu domain dùng jMolecules, thêm `jmolecules-archunit` cùng artifact DDD cần thiết để chạy DDD rules mặc định.
4. Chọn kiểu kiến trúc bên trong module: layered, onion hoặc hexagonal.
5. Đăng ký rule tương ứng bằng `andAdditionalVerifications(...)` để giữ các kiểm tra bổ sung mặc định.
6. Chỉ dùng `withAdditionalVerifications(...)` khi chủ ý thay thế toàn bộ nhóm kiểm tra bổ sung mặc định.
7. Đọc violation theo đúng nhóm rule và sửa boundary, domain model hoặc hướng dependency ở nơi sở hữu trách nhiệm.

Spring Modulith bảo vệ cách các module cộng tác với nhau. jMolecules DDD giúp giữ mô hình miền nhất quán, còn jMolecules Architecture rules bảo vệ cấu trúc layer/ring/port-adapter mà nhóm đã lựa chọn. Kết hợp đúng ba phạm vi này giúp kiểm tra kiến trúc từ ranh giới modular monolith đến cấu trúc bên trong từng module.

Tài liệu tham khảo: [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html), [VerificationOptions Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html), [Issue làm rõ phạm vi tích hợp jMolecules DDD của Spring Modulith](https://github.com/spring-projects/spring-modulith/issues/228), [jMolecules README](https://github.com/xmolecules/jmolecules), [JMoleculesArchitectureRules source](https://github.com/xmolecules/jmolecules-integrations/blob/main/jmolecules-archunit/src/main/java/org/jmolecules/archunit/JMoleculesArchitectureRules.java).
