# Chỉ bật rule phù hợp với mô hình ứng dụng

Spring Modulith kiểm tra ranh giới giữa các Application Module, nhưng một ứng dụng còn có thể cần những quy tắc kiến trúc bên trong từng module. Ví dụ, nhóm có thể tổ chức code theo Layered Architecture, Hexagonal Architecture hoặc Onion Architecture. Mỗi mô hình có hướng phụ thuộc và cách nhận diện thành phần khác nhau; bật đồng thời mọi bộ rule có sẵn có thể tạo ra những ràng buộc mâu thuẫn với thiết kế thực tế.

Nguyên tắc là chọn **rule mô tả đúng kiến trúc mà ứng dụng đang áp dụng**. Giữ verification cốt lõi của Spring Modulith để bảo vệ module boundary, sau đó thêm jMolecules hoặc ArchUnit cho các quy tắc nội bộ cần thiết. Bài học này giúp phân biệt các lớp kiểm tra, chọn bộ rule theo mô hình và giới hạn phạm vi để tránh áp đặt kiến trúc không phù hợp.

## 1. Tách module verification khỏi architecture-style verification

Spring Modulith và jMolecules giải quyết hai phạm vi có liên quan nhưng khác nhau.

**Spring Modulith** kiểm tra cấu trúc ở cấp Application Module:

- Dependency graph giữa các module không có chu trình.
- Module chỉ tham chiếu type thuộc API package hoặc Named Interface được công bố.
- Nếu module khai báo **allowedDependencies**, dependency thực tế phải nằm trong allowlist.

**Architecture-style rules** kiểm tra cách tổ chức type và dependency bên trong phạm vi code được phân tích, ví dụ:

- Controller/interface layer chỉ gọi application layer.
- Domain code không phụ thuộc adapter hoặc framework infrastructure.
- Port và adapter tuân thủ vai trò của Hexagonal Architecture.
- Các ring của Onion Architecture chỉ tham chiếu theo hướng cho phép.

Vì vậy, một ứng dụng có thể vượt qua **ApplicationModules.verify()** nhưng vẫn vi phạm Layered hoặc Hexagonal Architecture. Ngược lại, một bộ rule nội bộ có thể PASS trong khi dependency graph giữa Application Module vẫn có chu trình hoặc truy cập package nội bộ.

Hãy giữ hai lớp kiểm tra riêng trong cách thiết kế test:

~~~text
ApplicationModules.verify()
        |
        +-- Module boundaries
        |     +-- Acyclic module dependencies
        |     +-- API / Named Interface access
        |     +-- allowedDependencies
        |
        +-- Additional architecture rules
              +-- DDD rules
              +-- Layered OR Hexagonal OR Onion
              +-- Team-specific ArchRules
~~~

## 2. Xác định mô hình kiến trúc đang được dùng

Trước khi thêm rule, hãy mô tả kiến trúc thực tế của codebase. Không nên chọn rule chỉ vì tên mô hình phổ biến hoặc vì thư viện có sẵn một phương thức kiểm tra.

| Dấu hiệu trong ứng dụng | Mô hình có thể phù hợp | Điều cần kiểm tra |
|---|---|---|
| Code được phân thành interface, application, domain và infrastructure layer | Layered Architecture | Hướng phụ thuộc giữa các layer |
| Use case ở trung tâm, giao tiếp qua port; adapter kết nối HTTP, database hoặc hệ thống ngoài | Hexagonal Architecture | Adapter, port và application code tham chiếu đúng vai trò |
| Domain model ở trung tâm, application/service ring bao quanh và infrastructure ở vòng ngoài | Onion Architecture | Dependency hướng vào trong theo các ring |
| Dùng aggregate, entity, value object, repository và domain event theo DDD | DDD building blocks | Quan hệ và cách sử dụng các khái niệm domain |
| Có quy ước riêng ngoài các mô hình trên | Custom architecture | Các package/type nào được phép phụ thuộc nhau |

Một ứng dụng modular monolith vẫn có thể dùng một trong các mô hình trên bên trong từng module. Module boundary trả lời câu hỏi phần nghiệp vụ nào sở hữu type; architecture-style rule trả lời các type bên trong phần đó được phép phụ thuộc theo hướng nào.

Nếu ứng dụng đang ở giai đoạn chuyển đổi, hãy chọn một phạm vi nhỏ đã tuân thủ mô hình trước. Đừng áp rule nghiêm ngặt lên toàn bộ codebase legacy khi phần lớn package chưa được gắn metadata hoặc chưa có ranh giới ổn định.

Spring Modulith có tích hợp tùy chọn với jMolecules ArchUnit. Khi thư viện tương ứng có trên classpath, Spring Modulith tự động chạy các verification DDD và kiến trúc mà tích hợp cung cấp. Ví dụ dependency Maven:

~~~xml
<dependency>
    <groupId>org.jmolecules.integrations</groupId>
    <artifactId>jmolecules-archunit</artifactId>
    <scope>test</scope>
</dependency>
~~~

Quản lý version bằng dependency management hoặc khai báo version phù hợp với Spring Modulith và jMolecules của dự án. Nếu chỉ viết custom ArchRule, cần có ArchUnit trên test compile classpath.

## 3. Layered Architecture: chọn rule khi ứng dụng thực sự có các layer

Layered Architecture phù hợp khi ứng dụng phân chia trách nhiệm thành các tầng có thứ tự rõ ràng. jMolecules cung cấp các annotation để đánh dấu layer:

| Annotation | Vai trò |
|---|---|
| **@InterfaceLayer** | Giao tiếp với bên ngoài, ví dụ web hoặc API |
| **@ApplicationLayer** | Điều phối use case |
| **@DomainLayer** | Quy tắc và mô hình nghiệp vụ |
| **@InfrastructureLayer** | Chi tiết kỹ thuật như persistence hoặc tích hợp |

Ví dụ:

~~~java
import org.jmolecules.architecture.layered.InterfaceLayer;
import org.springframework.web.bind.annotation.RestController;

@InterfaceLayer
@RestController
class OrderController {
}
~~~

~~~java
import org.jmolecules.architecture.layered.ApplicationLayer;
import org.springframework.stereotype.Service;

@ApplicationLayer
@Service
class PlaceOrderService {
}
~~~

~~~java
import org.jmolecules.architecture.layered.DomainLayer;

@DomainLayer
class Order {
}
~~~

~~~java
import org.jmolecules.architecture.layered.InfrastructureLayer;
import org.springframework.stereotype.Repository;

@InfrastructureLayer
@Repository
class JpaOrderRepository {
}
~~~

Sau khi type được gắn đúng stereotype, có thể dùng rule Layered của jMolecules:

~~~java
import org.jmolecules.archunit.JMoleculesArchitectureRules;

var layered = JMoleculesArchitectureRules.ensureLayering();
~~~

**ensureLayering()** cho phép một layer truy cập các layer thấp hơn theo mô hình Layered Architecture của jMolecules. Nếu ứng dụng yêu cầu quy tắc nghiêm ngặt hơn, **ensureLayeringStrict()** chỉ cho phép truy cập layer kế tiếp theo thứ tự.

~~~java
var layeredStrict = JMoleculesArchitectureRules.ensureLayeringStrict();
~~~

Chọn mức strict dựa trên cấu trúc thực tế. Nếu ứng dụng chủ đích cho application layer truy cập trực tiếp repository/infrastructure, rule strict có thể báo lỗi dù đó là lựa chọn đã được thiết kế. Nếu muốn buộc mọi lời gọi đi qua tầng liền kề, strict phù hợp hơn.

## 4. Hexagonal Architecture: chọn rule khi port và adapter là ranh giới chính

Hexagonal Architecture phù hợp khi use case không phụ thuộc trực tiếp vào cách giao tiếp hoặc lưu trữ. Application code định nghĩa port; adapter hiện thực hoặc gọi các port đó ở ranh giới bên ngoài.

Các stereotype thường dùng:

| Annotation | Vai trò |
|---|---|
| **@Application** | Logic ứng dụng/use case |
| **@Port** | Hợp đồng giao tiếp |
| **@PrimaryPort** | Port được actor bên ngoài gọi vào |
| **@SecondaryPort** | Port mà application code dùng để gọi ra ngoài |
| **@Adapter** | Adapter ở ranh giới |
| **@PrimaryAdapter** | Adapter nhận yêu cầu từ actor, ví dụ REST controller |
| **@SecondaryAdapter** | Adapter kết nối hệ thống ngoài, ví dụ database hoặc payment gateway |

Ví dụ minh họa:

~~~java
import org.jmolecules.architecture.hexagonal.Application;

@Application
class PlaceOrderUseCase {
    // Điều phối nghiệp vụ đặt hàng.
}
~~~

~~~java
import org.jmolecules.architecture.hexagonal.SecondaryPort;

@SecondaryPort
interface InventoryPort {
    boolean reserve(String orderId);
}
~~~

~~~java
import org.jmolecules.architecture.hexagonal.SecondaryAdapter;
import org.springframework.stereotype.Component;

@SecondaryAdapter
@Component
class InventoryHttpAdapter implements InventoryPort {

    @Override
    public boolean reserve(String orderId) {
        return true;
    }
}
~~~

Rule Hexagonal của jMolecules:

~~~java
import org.jmolecules.archunit.JMoleculesArchitectureRules;

var hexagonal = JMoleculesArchitectureRules.ensureHexagonal();
~~~

Với jMolecules mới, có thể cấu hình mức kiểm tra qua **HexagonalVerificationOptions**:

~~~java
import org.jmolecules.archunit.HexagonalVerificationOptions;
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.jmolecules.archunit.VerificationDepth;

var hexagonalStrict = JMoleculesArchitectureRules.ensureHexagonal(
    HexagonalVerificationOptions.defaults()
        .withDepth(VerificationDepth.STRICT)
);
~~~

Rule này phù hợp khi ứng dụng thực sự định nghĩa port, adapter và application code theo Hexagonal Architecture. Nếu codebase chỉ dùng service/repository theo kiểu layered và không phân biệt primary/secondary port, việc bật Hexagonal strict có thể buộc nhóm thêm stereotype không phản ánh thiết kế.

## 5. Onion Architecture: chọn rule khi ứng dụng tổ chức theo các ring

Onion Architecture đặt domain ở trung tâm và tổ chức các trách nhiệm xung quanh theo các ring. Các dependency nên hướng về phía trong; infrastructure nằm ở vòng ngoài và không nên trở thành điều kiện để domain model hoạt động.

jMolecules cung cấp hai biến thể rule:

- **ensureOnionSimple()** cho cách mô hình hóa Onion đơn giản.
- **ensureOnionClassical()** cho cấu trúc Onion cổ điển với các ring chi tiết hơn.

Các ring được nhận diện qua stereotype tương ứng. Biến thể đơn giản dùng **@DomainRing**, **@ApplicationRing** và **@InfrastructureRing**; biến thể cổ điển dùng các annotation như **@DomainModelRing**, **@DomainServiceRing**, **@ApplicationServiceRing** và ring infrastructure cổ điển. Chỉ đánh dấu type theo đúng vai trò của nó trong thiết kế hiện tại.

Ví dụ dùng rule đơn giản:

~~~java
import org.jmolecules.archunit.JMoleculesArchitectureRules;

var onion = JMoleculesArchitectureRules.ensureOnionSimple();
~~~

Nếu codebase sử dụng các ring cổ điển như domain model, domain service, application service và infrastructure, có thể chọn:

~~~java
var onionClassical = JMoleculesArchitectureRules.ensureOnionClassical();
~~~

Các rule này dựa vào stereotype/annotation của jMolecules để nhận diện ring. Hãy kiểm tra type đã được đánh dấu đúng trước khi bật rule; nếu không, kết quả có thể không phản ánh cấu trúc mà nhóm muốn bảo vệ.

## 6. DDD rules không đồng nghĩa với một architecture style

Domain-Driven Design cung cấp ngôn ngữ và building blocks như aggregate, entity, value object, repository, domain event và domain service. DDD không bắt buộc ứng dụng phải dùng Layered, Hexagonal hay Onion Architecture.

jMolecules cung cấp **JMoleculesDddRules** để kiểm tra tính nhất quán của các khái niệm DDD được biểu diễn bằng annotation hoặc type:

~~~java
import org.jmolecules.archunit.JMoleculesDddRules;

var dddRules = JMoleculesDddRules.all();
~~~

Chọn DDD rules khi ứng dụng thực sự sử dụng stereotype hoặc abstraction DDD và nhóm muốn kiểm tra cách chúng được kết hợp. Có thể dùng DDD rules cùng một architecture style phù hợp, nhưng không nên coi chúng là bằng chứng rằng ứng dụng đã tuân thủ Hexagonal hoặc Onion.

Ví dụ, một module có aggregate và value object vẫn có thể được tổ chức theo layered architecture. Một module khác có thể dùng port/adapter. Điều quan trọng là mỗi rule phải được áp dụng đúng phạm vi và đúng cách nhóm mô hình hóa.

## 7. Tự định nghĩa ArchRule cho quy ước riêng

Nếu ứng dụng không theo trọn vẹn một mô hình chuẩn, hãy chỉ kiểm tra những nguyên tắc cụ thể thực sự cần thiết bằng ArchUnit.

Ví dụ, domain package không được phụ thuộc trực tiếp vào adapter:

~~~java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;

ArchRule domainMustNotDependOnAdapters = noClasses()
    .that().resideInAPackage("..domain..")
    .should().dependOnClassesThat()
    .resideInAnyPackage("..adapter..")
    .because("domain logic phải độc lập với adapter bên ngoài");
~~~

Hoặc chỉ cấm module orders phụ thuộc vào package web của inventory:

~~~java
ArchRule ordersMustNotDependOnInventoryWeb = noClasses()
    .that().resideInAPackage("..orders..")
    .should().dependOnClassesThat()
    .resideInAnyPackage("..inventory.web..");
~~~

Custom rule phù hợp khi:

- Kiến trúc thực tế là biến thể riêng, không khớp hoàn toàn Layered/Hexagonal/Onion.
- Chỉ một số module áp dụng một quy ước nhất định.
- Nhóm muốn kiểm tra một dependency cụ thể mà không gắn stereotype toàn bộ codebase.
- Rule chuẩn quá nghiêm hoặc quá rộng so với phạm vi cần bảo vệ.

Matcher nên giới hạn theo package và trách nhiệm rõ ràng. Tránh rule kiểu **..service..** hoặc **..common..** nếu các package cùng tên ở nhiều bounded context có ý nghĩa khác nhau.

## 8. Đăng ký đúng tập rule trong VerificationOptions

Sau khi chọn rule, có thể truyền nó vào Spring Modulith bằng **VerificationOptions**.

Nếu muốn thêm rule riêng và giữ các additional verifications mặc định:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

var options = VerificationOptions.defaults()
    .andAdditionalVerifications(domainMustNotDependOnAdapters);

ApplicationModules.of(ShopApplication.class).verify(options);
~~~

Nếu muốn thay thế tập additional verifications mặc định bằng chính xác những rule đã chọn:

~~~java
var options = VerificationOptions.defaults()
    .withAdditionalVerifications(
        JMoleculesDddRules.all(),
        hexagonal
    );

ApplicationModules.of(ShopApplication.class).verify(options);
~~~

Hai phương thức có ngữ nghĩa khác nhau:

| Phương thức | Kết quả |
|---|---|
| **andAdditionalVerifications(rule)** | Giữ các additional verifications mặc định và thêm rule mới |
| **withAdditionalVerifications(rule)** | Thay tập additional verifications mặc định bằng tập rule được truyền vào |
| **withoutAdditionalVerifications()** | Tắt các additional verifications mặc định |

Các quy tắc cốt lõi của Spring Modulith vẫn được chạy. Nếu jMolecules đã có trên classpath và Spring Modulith tự động đăng ký kiểm tra bổ sung, hãy quyết định rõ có muốn giữ các kiểm tra đó hay thay bằng tập rule được chọn. Không dùng **withAdditionalVerifications()** chỉ vì muốn thêm một rule; trong trường hợp đó, dùng **andAdditionalVerifications()**.

## 9. Không bật Layered, Hexagonal và Onion chỉ vì đều có sẵn

Mỗi architecture style mô tả một cách tổ chức và hướng dependency khác nhau:

| Bộ rule | Khi nào phù hợp | Rủi ro khi áp dụng sai |
|---|---|---|
| Layered | Code có các tầng interface, application, domain, infrastructure rõ ràng | Có thể cấm đường phụ thuộc mà ứng dụng đang chủ đích dùng |
| Hexagonal | Application code giao tiếp qua port và adapter | Có thể yêu cầu stereotype port/adapter không phản ánh codebase |
| Onion | Domain nằm trong các ring và dependency hướng vào trong | Có thể không phù hợp với cấu trúc layer hoặc adapter hiện tại |
| DDD rules | Dự án dùng DDD building blocks và stereotype tương ứng | Có thể báo lỗi nếu annotation không phản ánh cách mô hình hóa thực tế |
| Custom ArchRule | Có một quy ước cụ thể của dự án | Rule quá rộng có thể cấm dependency hợp lệ |

Không nên bật cả ba style rule trên cùng một package chỉ để “kiểm tra kỹ hơn”. Chúng có thể áp đặt những kỳ vọng khác nhau về layer, port, adapter và ring. Nếu ứng dụng có kiến trúc hỗn hợp, hãy tách phạm vi:

- Dùng rule Layered cho package hoặc module thực sự theo layered.
- Dùng rule Hexagonal cho bounded context được tổ chức theo port/adapter.
- Dùng rule Onion cho vùng domain được tổ chức theo ring.
- Dùng custom ArchRule cho phần còn lại hoặc cho quy ước xuyên suốt.

Nếu thư viện rule hỗ trợ scope, cấu hình scope theo package hoặc architectural unit thay vì chạy một rule toàn cục lên mọi type.

## 10. Chọn rule theo mức trưởng thành của codebase

Không phải ứng dụng nào cũng sẵn sàng cho strict verification ngay từ đầu.

| Trạng thái codebase | Cách bắt đầu |
|---|---|
| Chưa có layer/stereotype rõ | Chỉ chạy Spring Modulith core rules; xác định boundary trước |
| Đã có package layer nhưng metadata chưa đầy đủ | Bổ sung stereotype theo từng vùng, chạy rule ở phạm vi nhỏ |
| Đã thống nhất Layered hoặc Hexagonal | Chạy rule tương ứng; chọn strictness phù hợp |
| Có legacy code và module mới | Bảo vệ module mới bằng rule rõ; không áp global rule chưa thể tuân thủ |
| Kiến trúc ổn định và được ghi nhận | Đưa rule phù hợp vào CI và xem vi phạm là lỗi cần xử lý |

Một cách triển khai an toàn là bật rule ở một bounded context, xử lý vi phạm, rồi mở rộng phạm vi khi các package còn lại đã được tổ chức tương ứng. Điều này giúp rule trở thành mô tả thực tế của kiến trúc thay vì danh sách mong muốn không khớp với code.

## 11. Kiểm tra rule có đang kiểm tra đúng phạm vi không

Sau khi đăng ký verification, giữ architecture test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ArchitectureTests {

    @Test
    void verifiesModulesAndSelectedArchitectureRules() {
        var options = VerificationOptions.defaults()
            .andAdditionalVerifications(domainMustNotDependOnAdapters);

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
~~~

Khi rule thất bại, đọc vi phạm và kiểm tra:

1. Type nguồn và type đích có thuộc đúng package scope không?
2. Các stereotype/annotation có mô tả đúng vai trò thực tế không?
3. Rule có đang áp một mô hình kiến trúc khác với mô hình của package đó không?
4. Dependency có thật sự sai hay chỉ là ngoại lệ cần biểu diễn bằng port, interface hoặc một rule khác?
5. Có thể thu hẹp scope để rule chỉ kiểm tra đúng bounded context không?

Đừng xóa rule hoặc tắt toàn bộ additional verification chỉ để làm test PASS. Nếu rule không phù hợp, thay nó bằng rule mô tả chính xác hơn và ghi rõ lý do.

## 12. Checklist trước khi bật additional architecture rule

- [ ] Đã xác định mô hình thực tế của package/module được kiểm tra.
- [ ] Đã phân biệt module boundary với layer, port, adapter hoặc ring bên trong module.
- [ ] Chỉ chọn Layered, Hexagonal hoặc Onion khi codebase có cấu trúc tương ứng.
- [ ] Đã đánh dấu stereotype để jMolecules nhận diện đúng thành phần.
- [ ] Đã quyết định có giữ DDD verification tự động theo classpath hay không.
- [ ] Đã dùng **andAdditionalVerifications()** để append hoặc **withAdditionalVerifications()** để replace đúng chủ đích.
- [ ] Custom ArchRule có scope rõ và thông điệp vi phạm dễ hiểu.
- [ ] Đã chạy **ApplicationModules.verify(options)** cùng các test hành vi cần thiết.
- [ ] Rule được đưa vào CI ở phạm vi mà nhóm có thể duy trì.

Chỉ bật rule phù hợp với mô hình ứng dụng giúp verification bảo vệ đúng kiến trúc mà nhóm đang xây dựng. Spring Modulith giữ các module độc lập và kiểm soát API liên module; jMolecules và ArchUnit bổ sung các ràng buộc về DDD, layer, port, adapter, ring hoặc quy ước riêng. Khi chọn đúng phạm vi và đúng rule, kết quả kiểm tra trở thành một hợp đồng kiến trúc rõ ràng, có thể duy trì qua các lần thay đổi.

## Tài liệu tham khảo

- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): các quy tắc module cốt lõi, tích hợp jMolecules và cấu hình additional verifications.
- [jMolecules ArchUnit — README](https://github.com/xmolecules/jmolecules-integrations/tree/main/jmolecules-archunit): cách dùng DDD và architecture rules trong ArchUnit.
- [JMoleculesArchitectureRules source](https://github.com/xmolecules/jmolecules-integrations/blob/main/jmolecules-archunit/src/main/java/org/jmolecules/archunit/JMoleculesArchitectureRules.java): các rule Layered, Hexagonal và Onion cùng options tương ứng.
- [ArchUnit User Guide](https://www.archunit.org/userguide/html/000_Index.html): cách viết và đánh giá custom ArchRule.
