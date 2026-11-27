# Hexagonal architecture rules và verification depth

Spring Modulith có thể kết hợp với jMolecules ArchUnit để kiểm tra thêm các quy ước kiến trúc ngoài ranh giới application module. Một ví dụ là Hexagonal Architecture (Ports and Adapters): code nghiệp vụ giao tiếp với thế giới bên ngoài qua port, còn adapter đảm nhiệm việc chuyển đổi giữa port và công nghệ như HTTP, database hoặc message broker.

jMolecules biểu diễn các vai trò đó bằng annotation và cung cấp `JMoleculesArchitectureRules.ensureHexagonal(...)` để tạo một `ArchRule`. Có thể chọn `VerificationDepth` để điều chỉnh mức nghiêm ngặt của quy tắc, sau đó đưa rule vào `VerificationOptions` và chạy cùng `ApplicationModules.verify()`.

## 1. Hai lớp kiểm tra có mục đích khác nhau

Spring Modulith và jMolecules giải quyết hai phạm vi kiến trúc bổ sung cho nhau:

| Công cụ | Điều được kiểm tra |
|---|---|
| Spring Modulith `ApplicationModules.verify()` | Ranh giới application module, chu trình phụ thuộc, truy cập API/internal và `allowedDependencies` |
| jMolecules Hexagonal `ArchRule` | Vai trò Application, Port, Adapter và hướng phụ thuộc giữa các vai trò trong Hexagonal Architecture |

Ví dụ, Spring Modulith có thể xác nhận `orders` không truy cập package nội bộ của `inventory`. jMolecules có thể kiểm tra sâu hơn rằng application logic không gọi trực tiếp adapter HTTP hoặc database mà phải đi qua port.

Một kiến trúc có thể vượt qua kiểm tra module nhưng vẫn vi phạm quy tắc Ports and Adapters bên trong một module. Kết hợp hai bộ quy tắc giúp kiểm tra cả ranh giới module lẫn cấu trúc bên trong module.

## 2. Nhận diện các vai trò trong Hexagonal Architecture

Trong Hexagonal Architecture, application core chứa logic nghiệp vụ và định nghĩa các port cần thiết. Adapter nằm ở rìa hệ thống, chuyển đổi giao thức hoặc công nghệ bên ngoài thành lời gọi port, và chuyển kết quả từ port trở lại hệ thống ngoài.

| Vai trò jMolecules | Ý nghĩa | Ví dụ |
|---|---|---|
| `@Application` | Logic ứng dụng nằm trong core | Use case xử lý đặt hàng |
| `@Port` | Port tổng quát, biểu diễn một điểm giao tiếp | Interface giao tiếp với một vai trò khác |
| `@PrimaryPort` | Port đầu vào để kích hoạt use case | `PlaceOrderUseCase` |
| `@SecondaryPort` | Port đầu ra mà application cần để gọi hệ thống ngoài | `InventoryPort`, `OrderRepository` |
| `@Adapter` | Adapter tổng quát ở rìa hệ thống | Adapter tích hợp |
| `@PrimaryAdapter` | Adapter đưa yêu cầu từ bên ngoài vào application | REST controller, message consumer |
| `@SecondaryAdapter` | Adapter triển khai port đầu ra bằng công nghệ cụ thể | JPA repository adapter, HTTP client |

`Primary` và `Secondary` mô tả hướng tương tác với application core:

- Primary adapter nhận yêu cầu từ actor hoặc hệ thống bên ngoài và gọi primary port.
- Application thực hiện use case, có thể sử dụng secondary port để yêu cầu khả năng từ bên ngoài.
- Secondary adapter triển khai secondary port bằng database, HTTP API, filesystem hoặc message broker.

```text
Actor / HTTP / Message
        │
        ▼
  Primary Adapter
        │ gọi
        ▼
    Primary Port
        │
        ▼
    Application
        │ gọi
        ▼
   Secondary Port
        ▲
        │ triển khai
  Secondary Adapter
        │
        ▼
Database / HTTP / Broker
```

Điều quan trọng là application core phụ thuộc vào abstraction của port. Adapter phụ thuộc vào port để cung cấp hoặc sử dụng khả năng đó. Application không cần biết controller, JDBC driver hay HTTP client cụ thể nào đang thực hiện giao tiếp.

## 3. Gắn stereotype bằng annotation jMolecules

jMolecules cung cấp annotation trong package `org.jmolecules.architecture.hexagonal`. Có thể đánh dấu các interface và class trực tiếp trong code.

Ví dụ use case đặt hàng:

```java
package com.acme.shop.orders;

import org.jmolecules.architecture.hexagonal.PrimaryPort;

@PrimaryPort
public interface PlaceOrderUseCase {

    OrderId place(PlaceOrderCommand command);
}
```

Application service thực hiện use case và sử dụng secondary port:

```java
package com.acme.shop.orders;

import org.jmolecules.architecture.hexagonal.Application;

@Application
class PlaceOrderService implements PlaceOrderUseCase {

    private final InventoryPort inventory;

    PlaceOrderService(InventoryPort inventory) {
        this.inventory = inventory;
    }

    @Override
    public OrderId place(PlaceOrderCommand command) {
        inventory.reserve(command.productId(), command.quantity());
        // Tạo và lưu đơn hàng thông qua các port cần thiết.
        return OrderId.newId();
    }
}
```

Secondary port mô tả khả năng mà application cần:

```java
package com.acme.shop.orders;

import org.jmolecules.architecture.hexagonal.SecondaryPort;

@SecondaryPort
public interface InventoryPort {

    void reserve(ProductId productId, int quantity);
}
```

REST controller là primary adapter:

```java
package com.acme.shop.orders.web;

import org.jmolecules.architecture.hexagonal.PrimaryAdapter;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@PrimaryAdapter
@RestController
class OrderController {

    private final PlaceOrderUseCase useCase;

    OrderController(PlaceOrderUseCase useCase) {
        this.useCase = useCase;
    }

    @PostMapping("/orders")
    OrderId place(PlaceOrderCommand command) {
        return useCase.place(command);
    }
}
```

HTTP client hoặc adapter tích hợp kho hàng triển khai secondary port:

```java
package com.acme.shop.orders.inventory;

import org.jmolecules.architecture.hexagonal.SecondaryAdapter;
import org.springframework.stereotype.Component;

@SecondaryAdapter
@Component
class InventoryHttpAdapter implements InventoryPort {

    @Override
    public void reserve(ProductId productId, int quantity) {
        // Gọi API kho hàng và chuyển đổi request/response.
    }
}
```

Các type `OrderId`, `PlaceOrderCommand` và `ProductId` trong ví dụ là kiểu miền của ứng dụng. Một dự án thực tế cần định nghĩa chúng trong source code của mình. Các annotation jMolecules là metadata kiến trúc; chúng không tự tạo bean Spring, không thay thế `@Service`, `@Component` hoặc cấu hình dependency injection.

## 4. Hexagonal verification kiểm tra điều gì?

`JMoleculesArchitectureRules.ensureHexagonal(...)` tạo một ArchUnit rule kiểm tra quan hệ phụ thuộc giữa các vai trò Hexagonal. Những ràng buộc chính gồm:

- Application code chỉ truy cập các port phù hợp, không phụ thuộc trực tiếp vào adapter cụ thể.
- Primary adapter và secondary adapter được kiểm tra theo vai trò của chúng.
- Primary port và secondary port được kiểm tra theo hướng truy cập tương ứng.
- Các type không có stereotype vẫn được tính đến theo `VerificationDepth` và phạm vi kiểm tra đã cấu hình.
- Nếu package được đánh dấu thành một `ArchitecturalUnit` như `@Hexagon`, jMolecules kiểm tra các vai trò trong từng unit và quan hệ giữa các unit theo exposure/referrer policy.

Các quy tắc này không chỉ kiểm tra tên package. jMolecules sử dụng annotation stereotype để phân loại type và ArchUnit để phân tích tham chiếu giữa chúng. Vì vậy, đặt annotation đúng vai trò là điều kiện quan trọng để kết quả có ý nghĩa.

Có thể đánh dấu một package là một Hexagon riêng:

```java
@org.jmolecules.architecture.hexagonal.Hexagon
package com.acme.shop.orders;
```

`@Hexagon` giúp jMolecules coi package như một architectural unit và kiểm tra các quan hệ giữa unit. Nếu không có unit được đánh dấu, các quy tắc layer vẫn được áp dụng trên toàn bộ tập type được phân tích.

## 5. VerificationDepth điều chỉnh mức nghiêm ngặt

`VerificationDepth` thuộc jMolecules ArchUnit và được dùng khi tạo Hexagonal rule. Nó điều chỉnh cách các ràng buộc layer xử lý những type chưa được phân loại đầy đủ bằng stereotype. Đây không phải độ sâu duyệt package, số tầng module hoặc số cấp gọi phương thức.

Hai mức thường được sử dụng là:

| Mức | Cách sử dụng |
|---|---|
| `LENIENT` | Phù hợp khi đưa stereotype vào codebase hiện hữu theo từng bước; cho phép phạm vi tương tác rộng hơn trong một số quan hệ layer |
| `STRICT` | Phù hợp khi vai trò Application, Port và Adapter đã được khai báo rõ; áp dụng ràng buộc layer chặt hơn |

Ví dụ Spring Modulith 1.4 sử dụng `VerificationDepth.LENIENT`, trong khi tài liệu hiện hành có ví dụ `VerificationDepth.STRICT`. Hãy chọn mức dựa trên độ hoàn chỉnh của metadata kiến trúc và mục tiêu kiểm tra của dự án, không chỉ dựa vào việc muốn test chạy qua.

Một cách triển khai thực tế là bắt đầu với `LENIENT` trong giai đoạn migration, bổ sung stereotype cho các type quan trọng, xử lý các vi phạm và chuyển sang `STRICT` khi ranh giới đã được mô tả đầy đủ. Nếu dùng `LENIENT` lâu dài, hãy ghi lại những khu vực chưa được phân loại và kế hoạch hoàn thiện chúng.

## 6. Tạo Hexagonal ArchRule và đưa vào Spring Modulith

Spring Modulith reference minh họa cách tạo rule với `JMoleculesArchitectureRules.ensureHexagonal(VerificationDepth.STRICT)`, sau đó truyền vào `VerificationOptions`:

```java
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.jmolecules.archunit.VerificationDepth;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

var hexagonal = JMoleculesArchitectureRules.ensureHexagonal(
        VerificationDepth.STRICT);

var options = VerificationOptions.defaults()
        .withAdditionalVerifications(hexagonal);

ApplicationModules.of(ShopApplication.class).verify(options);
```

Trong ví dụ này:

1. `ensureHexagonal(...)` tạo một `ArchRule` áp dụng Hexagonal Architecture với mức nghiêm ngặt đã chọn.
2. `VerificationOptions.defaults()` tạo options xác minh mặc định.
3. `withAdditionalVerifications(hexagonal)` đặt Hexagonal rule làm tập additional verification cần chạy.
4. `verify(options)` chạy quy tắc cấu trúc module của Spring Modulith cùng additional verification được chỉ định.

Lưu ý: `withAdditionalVerifications()` thay thế các additional verification mặc định được tự động đăng ký theo classpath. Các quy tắc cốt lõi của Spring Modulith vẫn được thực thi. Nếu muốn **giữ** các additional verification mặc định rồi thêm một rule riêng, dùng `andAdditionalVerifications()` thay vì `withAdditionalVerifications()`.

## 7. API mới của jMolecules và khả năng tương thích

Trong jMolecules ArchUnit từ phiên bản 0.34, overload `ensureHexagonal(VerificationDepth)` đã bị deprecated để chuyển sang `HexagonalVerificationOptions`. Với phiên bản này, có thể cấu hình tương đương như sau:

```java
import org.jmolecules.archunit.HexagonalVerificationOptions;
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.jmolecules.archunit.VerificationDepth;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

var hexagonalOptions = HexagonalVerificationOptions.defaults()
        .withDepth(VerificationDepth.STRICT);

var hexagonal = JMoleculesArchitectureRules.ensureHexagonal(hexagonalOptions);

var options = VerificationOptions.defaults()
        .withAdditionalVerifications(hexagonal);

ApplicationModules.of(ShopApplication.class).verify(options);
```

Hai dạng API cùng thể hiện ý định chọn verification depth, nhưng dạng options mới cho phép cấu hình thêm stereotype lookup, scope, exposure và referrer policy. Hãy kiểm tra phiên bản `jmolecules-archunit` được quản lý trong dependency management của ứng dụng trước khi chọn cú pháp. Không nên nâng riêng jMolecules mà bỏ qua khả năng tương thích với Spring Modulith đang dùng.

## 8. Tích hợp vào architecture test

Đặt kiểm tra trong JUnit test để CI phát hiện vi phạm ngay khi code thay đổi:

```java
import org.jmolecules.archunit.HexagonalVerificationOptions;
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.jmolecules.archunit.VerificationDepth;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class HexagonalArchitectureTests {

    @Test
    void verifiesModuleAndHexagonalBoundaries() {
        var hexagonal = JMoleculesArchitectureRules.ensureHexagonal(
                HexagonalVerificationOptions.defaults()
                        .withDepth(VerificationDepth.STRICT));

        var options = VerificationOptions.defaults()
                .withAdditionalVerifications(hexagonal);

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
```

Ví dụ này dùng API options mới của jMolecules. Nếu dự án đang dùng phiên bản cũ chưa có `HexagonalVerificationOptions`, dùng overload `ensureHexagonal(VerificationDepth.STRICT)` được Spring Modulith reference minh họa.

Khi rule thất bại, Spring Modulith ném `Violations`. Đọc toàn bộ thông điệp để xác định type nguồn, type đích và vai trò gây vi phạm. Một lỗi thường gặp là application service tham chiếu trực tiếp `InventoryHttpAdapter` thay vì `InventoryPort`. Cách sửa thường là đưa interface port về phía application core và để adapter triển khai interface đó.

## 9. Phân biệt các loại vi phạm

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Application service phụ thuộc `@SecondaryAdapter` | Core đang phụ thuộc công nghệ cụ thể | Định nghĩa `@SecondaryPort` và inject abstraction |
| REST controller gọi thẳng repository hoặc adapter ngoài | Primary adapter đang bỏ qua use case/port đầu vào | Đưa thao tác qua `@PrimaryPort` |
| Secondary adapter tham chiếu trực tiếp implementation application | Hướng phụ thuộc bị đảo | Để adapter triển khai port do application định nghĩa |
| Type không có stereotype tạo ra vi phạm khó hiểu | Metadata vai trò chưa đầy đủ hoặc verification depth quá chặt với code hiện tại | Bổ sung stereotype, xem lại phạm vi hoặc dùng mức chuyển tiếp có chủ đích |
| Hexagonal rule pass nhưng Modulith fail | Ranh giới module vẫn bị vi phạm | Sửa `allowedDependencies`, API package hoặc chu trình module |
| Modulith pass nhưng Hexagonal rule fail | Quan hệ trong module hợp lệ theo package nhưng sai vai trò Ports and Adapters | Sửa hướng phụ thuộc giữa Application, Port và Adapter |

Verification depth không nên được hạ xuống chỉ để che một phụ thuộc sai. Hãy kiểm tra annotation trước, sau đó xác nhận rule đang phân loại đúng type. Chỉ thay đổi depth khi đó là lựa chọn migration có chủ đích và nhóm hiểu rõ phạm vi ràng buộc được nới lỏng.

## 10. Quy trình áp dụng theo từng giai đoạn

1. **Vẽ ranh giới use case:** xác định application core, các đầu vào và các khả năng bên ngoài mà core cần.
2. **Đánh dấu stereotype:** dùng `@Application`, `@PrimaryPort`, `@SecondaryPort`, `@PrimaryAdapter` và `@SecondaryAdapter` ở đúng vai trò.
3. **Đánh dấu architectural unit nếu cần:** dùng `@Hexagon` trên package đại diện cho một đơn vị kiến trúc.
4. **Chạy LENIENT trong migration:** phát hiện các quan hệ sai mà vẫn cho phép nhóm hoàn thiện metadata theo từng bước.
5. **Xử lý violations:** chuyển dependency trực tiếp sang port, đưa interface về phía application core hoặc điều chỉnh adapter.
6. **Chuyển sang STRICT:** khi vai trò đã được mô tả rõ và các ngoại lệ migration đã được xử lý.
7. **Kết hợp Modulith verification:** chạy `ApplicationModules.verify(options)` để xác minh cả module boundary và Hexagonal rules.
8. **Đưa vào CI:** bảo đảm architecture test chạy cùng các test khác trên mỗi thay đổi code.

## 11. Checklist Hexagonal verification

- [ ] Các application service quan trọng đã được đánh dấu `@Application`.
- [ ] Use case đầu vào được biểu diễn bằng `@PrimaryPort`.
- [ ] Các abstraction mà application cần được biểu diễn bằng `@SecondaryPort`.
- [ ] REST, CLI hoặc message entrypoint được đánh dấu `@PrimaryAdapter`.
- [ ] Adapter kết nối database hoặc dịch vụ ngoài được đánh dấu `@SecondaryAdapter`.
- [ ] Các package cần kiểm tra độc lập đã được đánh dấu `@Hexagon` khi phù hợp.
- [ ] Đã chọn `LENIENT` hay `STRICT` theo giai đoạn và độ đầy đủ của stereotype.
- [ ] Đã xác nhận API `ensureHexagonal` tương thích với phiên bản jMolecules đang dùng.
- [ ] Đã quyết định rõ dùng `withAdditionalVerifications()` hay `andAdditionalVerifications()`.
- [ ] Architecture test gọi `ApplicationModules.verify(options)` trong CI.
- [ ] Không hạ verification depth chỉ để bỏ qua dependency sai.

Hexagonal rule bổ sung một lớp kiểm tra vai trò bên trong module: application phụ thuộc vào port, adapter hiện thực hoặc gọi port tại rìa hệ thống. Khi kết hợp đúng `VerificationDepth` với module verification, nhóm có thể phát hiện cả dependency vượt ranh giới module lẫn dependency đi sai hướng trong application core.

## Tài liệu tham khảo

- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [jMolecules – JMoleculesArchitectureRules source](https://github.com/xmolecules/jmolecules-integrations/blob/main/jmolecules-archunit/src/main/java/org/jmolecules/archunit/JMoleculesArchitectureRules.java)
- [jMolecules – HexagonalVerificationOptions API](https://javadoc.io/doc/org.jmolecules.integrations/jmolecules-archunit/latest/org/jmolecules/archunit/HexagonalVerificationOptions.html)
- [jMolecules – Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
