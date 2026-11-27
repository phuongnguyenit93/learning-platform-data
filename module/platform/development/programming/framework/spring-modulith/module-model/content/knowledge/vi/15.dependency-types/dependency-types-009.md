# Giới hạn của static inspection

Static inspection của Spring Modulith giúp phân tích cấu trúc module và các quan hệ phụ thuộc có thể suy ra từ codebase. `ApplicationModules.of(ShopApplication.class)` tạo một mô hình module trong bộ nhớ dựa trên package, metadata và các tham chiếu được phân tích; `verify()` dùng mô hình đó để kiểm tra những quy tắc kiến trúc đã định nghĩa.

Đây là một lớp kiểm soát quan trọng, nhưng kết quả của nó không phải bằng chứng rằng mọi hành vi runtime đều đúng. Static inspection có thể phát hiện chu trình module, truy cập kiểu nội bộ hoặc phụ thuộc vượt allowlist. Nó không thực thi toàn bộ ứng dụng để chứng minh mọi bean đều được khởi tạo, mọi event đều được xử lý hay mọi tương tác với database và hệ thống ngoài đều tuân thủ kiến trúc.

Sau bài học, bạn có thể:

- Giải thích static inspection của Spring Modulith phân tích những gì.
- Phân biệt quy tắc cấu trúc được `verify()` kiểm tra với hành vi chỉ xuất hiện khi runtime.
- Nhận diện các phụ thuộc động hoặc hạ tầng mà dependency graph có thể không mô tả đầy đủ.
- Hiểu ảnh hưởng của `OPEN` module, exclusion predicate và cấu hình detection đến phạm vi kiểm tra.
- Kết hợp architecture test, module integration test, runtime verification và observability để kiểm tra nhiều khía cạnh của ứng dụng.

## 1. Static inspection thực sự làm gì?

Spring Modulith cho phép tạo mô hình từ lớp ứng dụng Spring Boot:

```java
import org.springframework.modulith.core.ApplicationModules;

var modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

Mô hình được suy ra từ cách tổ chức package và codebase cùng metadata cấu hình. Spring Modulith sử dụng ArchUnit để thực hiện việc phân tích và xác minh cấu trúc module. Kết quả là một biểu diễn trong bộ nhớ về application module arrangement, gồm module, package cơ sở, Spring component và các quan hệ phụ thuộc có thể nhận diện.

Lời gọi sau kiểm tra những quy tắc kiến trúc mặc định:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Các kiểm tra chính gồm:

- Không có chu trình phụ thuộc ở cấp application module.
- Module chỉ tham chiếu kiểu được công khai qua API package; truy cập package nội bộ của module đóng bị từ chối.
- Nếu module khai báo `allowedDependencies`, phụ thuộc phải nằm trong danh sách được phép.
- Các quy tắc kiến trúc bổ sung của jMolecules có thể được chạy tự động nếu thư viện tương ứng có trên classpath.

```mermaid
flowchart TD
    app["Lớp Spring Boot chính"] --> model["ApplicationModules.of(...)"]
    model --> scan["Phân tích package, metadata và type references"]
    scan --> graph["Mô hình module trong bộ nhớ"]
    graph --> verify["verify() / detectViolations()"]
    verify --> rules["Chu trình · API công khai · allowedDependencies"]
    rules --> result["Báo cáo vi phạm kiến trúc"]
```

Điều quan trọng là phạm vi của kết quả: `verify()` trả lời câu hỏi cấu trúc code có tuân thủ những quy tắc module đã cấu hình hay không. Nó không tự động kiểm tra mọi yêu cầu chức năng và vận hành của ứng dụng.

## 2. Không chứng minh được mọi tương tác động

Static inspection chủ yếu suy luận quan hệ từ kiểu và cấu trúc có thể phân tích trong codebase. Một số phụ thuộc chỉ được quyết định khi chương trình chạy, nên có thể không xuất hiện đầy đủ trong dependency graph.

Ví dụ, module `reporting` tải lớp theo tên cấu hình:

```java
package com.acme.shop.reporting;

public class ReportExporterFactory {

    public Object create(String implementationClass) throws Exception {
        Class<?> type = Class.forName(implementationClass);
        return type.getDeclaredConstructor().newInstance();
    }
}
```

Tên lớp được truyền qua cấu hình hoặc database. Nếu giá trị đó trỏ đến một lớp thuộc module khác, tham chiếu thực tế không thể được suy ra đầy đủ chỉ từ một type reference tĩnh trong mã nguồn. Cùng vấn đề có thể xuất hiện với reflection, plugin registry, service locator, `ServiceLoader`, tên bean hoặc tên lớp được ghép từ chuỗi.

Các trường hợp cần chú ý:

- **Reflection và dynamic class loading:** lớp đích được xác định từ tên chuỗi, metadata hoặc dữ liệu runtime.
- **Service locator hoặc registry:** module tra cứu component bằng khóa, tên hoặc loại được cấu hình tại runtime.
- **Plugin và extension:** implementation được nạp từ module hoặc JAR bổ sung khi chạy.
- **Proxy và adapter được tạo động:** quan hệ thực tế phụ thuộc vào cấu hình hoặc cơ chế tạo đối tượng lúc runtime.

Điều này không có nghĩa mọi trường hợp reflection đều bị bỏ sót. Nếu code vẫn tham chiếu một kiểu trực tiếp ở nơi khác, công cụ có thể nhìn thấy tham chiếu đó. Giới hạn nằm ở quan hệ chỉ được xác định bằng dữ liệu hoặc quyết định động mà phân tích tĩnh không thể suy ra.

Với các đường tích hợp này, hãy bổ sung kiểm thử cấu hình và integration test để xác minh implementation thực tế được nạp và sử dụng đúng module.

## 3. Không mô tả đầy đủ phụ thuộc vào hạ tầng bên ngoài

Dependency graph của Spring Modulith tập trung vào application module trong cùng ứng dụng. Các quan hệ được biểu diễn rõ nhất khi module sử dụng kiểu Java, Spring component hoặc hợp đồng event do module khác công khai.

Một số quan hệ hạ tầng có thể không tạo ra type reference giữa hai application module:

| Quan hệ thực tế | Vì sao có thể không xuất hiện thành cạnh module |
|---|---|
| Hai module đọc và ghi cùng một bảng database bằng SQL | Tên bảng hoặc câu SQL có thể chỉ là chuỗi, không phải type reference đến module sở hữu dữ liệu |
| Hai module dùng chung Redis key | Khóa được cấu hình bằng chuỗi và không thể hiện quyền sở hữu module trong Java type graph |
| Gọi REST endpoint bằng URL | URL và HTTP contract có thể không tham chiếu một kiểu thuộc application module đích |
| Gửi message bằng topic hoặc routing key | Tên topic có thể được cấu hình riêng, không nhất thiết tham chiếu event type của module khác |
| Chia sẻ file, thư mục hoặc object storage | Đường dẫn và quyền truy cập dữ liệu không tự tạo ra quan hệ Java module |

Ví dụ, `billing` và `reporting` cùng truy vấn bảng `customer_account`. Nếu hai module chỉ dùng câu SQL hoặc tên bảng, static inspection có thể không biểu diễn được coupling dữ liệu này như một cạnh module. Đồ thị có thể trông độc lập dù hai module vẫn phụ thuộc vào schema và quy ước dữ liệu chung.

Hãy bổ sung tài liệu ownership dữ liệu, kiểm tra schema, contract test hoặc quy tắc kiến trúc riêng khi các quan hệ này quan trọng. Đối với giao tiếp qua event, dùng event type được công khai và listener có kiểu rõ ràng giúp quan hệ giữa các module dễ được nhận diện hơn.

## 4. Không xác nhận Spring context hoạt động đúng

Static inspection có thể nhận ra quan hệ component từ các type và metadata trong code. Tuy nhiên, nó không thay thế việc khởi tạo Spring `ApplicationContext` trong một môi trường cụ thể.

Các vấn đề chỉ lộ ra khi khởi tạo hoặc chạy ứng dụng có thể gồm:

- Không có bean phù hợp cho constructor injection.
- Hai bean cùng thỏa điều kiện và gây xung đột lựa chọn.
- `@Profile`, `@Conditional` hoặc cấu hình môi trường làm bean chỉ tồn tại trong một số deployment.
- Property bắt buộc bị thiếu hoặc giá trị cấu hình không hợp lệ.
- Kết nối database, broker hoặc HTTP client thất bại.
- Proxy, transaction manager hoặc security configuration không hoạt động như mong đợi.

Ví dụ, một module có constructor dependency hợp lệ về mặt kiểu nhưng bean implementation chỉ được tạo khi profile `production` bật. `ApplicationModules.verify()` không chứng minh rằng context sẽ khởi động thành công với mọi tổ hợp profile và property.

Hãy chạy context test với những cấu hình quan trọng, kiểm tra profile triển khai và xác minh các adapter hạ tầng bằng integration test. `@ApplicationModuleTest` giúp khởi tạo module riêng lẻ hoặc cùng các dependency của nó để kiểm tra Spring beans thực tế.

## 5. Không kiểm tra hành vi nghiệp vụ và độ tin cậy của event

Một listener được phát hiện trong static model không chứng minh event thực sự được publish trong luồng nghiệp vụ, listener được gọi đúng thời điểm hay side effect được ghi nhận chính xác.

Static inspection không chứng minh được các thuộc tính runtime như:

- Event có được publish khi nghiệp vụ hoàn tất hay không.
- Listener có xử lý thành công, retry hoặc xử lý duplicate đúng cách hay không.
- Transaction có commit trước khi listener transactional được gọi hay không.
- Các event bất đồng bộ có đến theo thứ tự mà nghiệp vụ yêu cầu hay không.
- Một lần gọi component có tạo đúng thay đổi trong database hay không.
- Hệ thống có đáp ứng timeout, throughput hoặc tải đồng thời hay không.

Hãy dùng module integration test để kích hoạt hành vi thật và xác minh kết quả. Ví dụ với `@ApplicationModuleTest` và `Scenario`:

```java
package com.acme.shop.inventory;

import com.acme.shop.order.OrderCompleted;
import org.springframework.beans.factory.annotation.Autowired;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class InventoryIntegrationTests {

    @Autowired InventoryQuery inventoryQuery;

    @Test
    void handlesOrderCompletion(Scenario scenario) {
        scenario.publish(new OrderCompleted("order-42"))
                .andWaitForStateChange(() -> inventoryQuery.findReservation("order-42"))
                .andVerify(reservation -> {
                    // Kiểm tra kết quả nghiệp vụ sau khi listener xử lý.
                });
    }
}
```

Ví dụ minh họa cách kiểm tra một stimulus và trạng thái sau xử lý; `OrderCompleted` và `inventoryQuery` cần được định nghĩa theo hợp đồng của ứng dụng. Với event publication, abstraction `PublishedEvents` cũng có thể xác minh một lời gọi nghiệp vụ đã phát ra event mong đợi.

## 6. Cấu hình có thể làm thay đổi phạm vi kiểm tra

Kết quả static inspection phụ thuộc vào cách Spring Modulith nhận diện module và các ngoại lệ được cấu hình. Vì vậy, một lần `verify()` thành công cần được đọc cùng với cấu hình đang dùng.

### Module kiểu `OPEN`

Với module `OPEN`, truy cập đến kiểu nội bộ của module nhìn chung được cho phép. Các type trong package con cũng được gom vào unnamed named interface, trừ khi được gán vào named interface tường minh. Vì vậy, `verify()` có thể chấp nhận một tham chiếu mà module `CLOSED` sẽ từ chối.

### Exclusion predicate

Overload `ApplicationModules.of(ShopApplication.class, ignored)` bỏ qua các Java type khớp predicate. Những type bị loại sẽ không tham gia lần inspection đó. Nếu predicate quá rộng, vi phạm ở vùng bị bỏ qua sẽ không được phát hiện.

### Detection strategy và custom module detection

Chiến lược phát hiện quyết định package nào được đưa vào module model. Nếu một package nghiệp vụ không được chọn, `verify()` không thể kiểm tra ranh giới module mà mô hình không nhận diện. Custom detection chỉ có trong test source set cũng không tự động có mặt ở runtime; các tùy chỉnh dùng cho runtime support cần được đưa vào production sources.

Trước khi dựa vào kết quả kiểm tra, hãy rà soát:

1. Lớp Spring Boot chính được truyền vào `ApplicationModules.of()` có đúng không.
2. Detection strategy có chọn đủ các package nghiệp vụ không.
3. Có module `OPEN` nào làm nới lỏng kiểm tra package nội bộ không.
4. Predicate exclusion có bỏ qua type hoặc package quan trọng không.
5. `allowedDependencies` và named interface có phản ánh đúng ý định kiến trúc không.

## 7. Kết hợp static inspection với các lớp kiểm tra khác

Không có một loại kiểm tra duy nhất bao phủ mọi khía cạnh của modular monolith. Hãy ghép các công cụ theo loại câu hỏi cần trả lời:

| Lớp kiểm tra | Công cụ Spring Modulith hoặc cách thực hiện | Câu hỏi được trả lời |
|---|---|---|
| Cấu trúc tĩnh | `ApplicationModules.of(...).verify()` | Module có tuân thủ ranh giới package, dependency cycle và allowlist không? |
| Kiểm thử module | `@ApplicationModuleTest` | Các bean và cấu hình của module có khởi tạo và phối hợp đúng trong test context không? |
| Kiểm thử kịch bản | `Scenario`, `PublishedEvents` | Khi kích hoạt hành vi, event và trạng thái nghiệp vụ mong đợi có xuất hiện không? |
| Kiểm tra lúc startup | `spring-modulith-runtime` cùng `spring.modulith.runtime.verification-enabled=true` | Ứng dụng có vi phạm cấu trúc module đã cấu hình khi khởi động không? |
| Quan sát runtime | Modulith Actuator và observability | Các module thực sự tương tác ra sao trong các request và event đã chạy? |
| Kiểm thử hạ tầng | Database, broker, HTTP và contract integration tests | Giao tiếp với hệ thống ngoài và hợp đồng dữ liệu có hoạt động đúng không? |

Ví dụ, architecture test vẫn nên nằm trong test suite:

```java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu cần kiểm tra cấu trúc ngay khi ứng dụng khởi động, thêm `spring-modulith-runtime` và bật:

```properties
spring.modulith.runtime.verification-enabled=true
```

Runtime verifier vẫn kiểm tra module arrangement đã được mô hình hóa. Nó không thay thế integration test hoặc theo dõi mọi tương tác động. Để quan sát tương tác thực tế, Spring Modulith cung cấp Actuator và observability hỗ trợ metrics/traces cho các Spring component thuộc API module và event publication.

## 8. Ghi nhớ

Static inspection của Spring Modulith phân tích cấu trúc package, metadata và các quan hệ type có thể nhận diện để xây dựng module model. `verify()` kiểm tra những quy tắc kiến trúc đã định nghĩa như chu trình phụ thuộc, truy cập API công khai và `allowedDependencies`. Nó không chứng minh mọi đường gọi động, tương tác database/REST/broker, cấu hình Spring runtime hay hành vi nghiệp vụ đều đúng. Module `OPEN`, exclusion predicate và detection strategy còn có thể thay đổi phạm vi kiểm tra. Hãy kết hợp architecture test với `@ApplicationModuleTest`, `Scenario`, runtime verification, observability và integration test cho hạ tầng để có cái nhìn đầy đủ hơn.

## Tài liệu tham khảo

- [Spring Modulith Fundamentals – The `ApplicationModules` Type và Excluding Packages](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith – Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith – Runtime Support and Runtime Verification](https://docs.spring.io/spring-modulith/reference/runtime.html)
- [Spring Modulith – Production-ready Features and Observability](https://docs.spring.io/spring-modulith/reference/production-ready.html)
- [Introducing Spring Modulith – Analysis based on ArchUnit](https://spring.io/blog/2022/10/21/introducing-spring-modulith/)
