# RuntimeApplicationModuleVerifier

Spring Modulith có thể kiểm tra cấu trúc application module ngay trong quá trình khởi động ứng dụng bằng `RuntimeApplicationModuleVerifier`. Cơ chế này đưa các quy tắc kiến trúc vào startup của môi trường chạy: nếu module có chu trình phụ thuộc, truy cập package nội bộ không được công khai hoặc vi phạm `allowedDependencies`, ứng dụng không hoàn tất khởi động bình thường.

Runtime verifier phù hợp khi nhóm muốn phát hiện vi phạm kiến trúc trong chính artifact được triển khai, kể cả khi một môi trường không chạy đầy đủ architecture test ở bước build. Nó bổ sung cho kiểm thử kiến trúc trong test suite; hai cơ chế cùng kiểm tra module model nhưng được kích hoạt ở hai thời điểm khác nhau.

## 1. RuntimeApplicationModuleVerifier làm nhiệm vụ gì?

`RuntimeApplicationModuleVerifier` thuộc runtime support của Spring Modulith. Khi được kích hoạt, nó xác minh module arrangement trong lúc ứng dụng Spring Boot khởi động. Việc xác minh dựa trên mô hình module mà Spring Modulith suy ra từ package, type và metadata như `@ApplicationModule`, `@NamedInterface` và `allowedDependencies`.

Các quy tắc được kiểm tra tương ứng với verification cốt lõi của Spring Modulith:

- Không có chu trình phụ thuộc giữa các application module.
- Module chỉ truy cập API được công khai của module khác; package nội bộ của module `CLOSED` được bảo vệ.
- Các phụ thuộc giữa module tuân thủ `allowedDependencies` khi allowlist được khai báo.

Nếu phát hiện vi phạm, quá trình verification phát sinh `Violations`. Vì verifier chạy trong startup, lỗi này khiến ứng dụng không khởi động thành công. Nhờ vậy, một artifact chứa cấu trúc module không hợp lệ có thể bị phát hiện ngay khi được đưa vào môi trường chạy.

Runtime verifier kiểm tra **module arrangement tĩnh tại startup**. Nó không theo dõi từng lời gọi phương thức, không đo thứ tự event thực tế, không kiểm tra kết quả nghiệp vụ và không thay thế health check, integration test hay runtime observability.

## 2. Thêm runtime support vào ứng dụng

Để sử dụng verifier, thêm artifact `spring-modulith-runtime` vào ứng dụng. Artifact này cung cấp runtime integration cần thiết để Spring Modulith có thể thực hiện hỗ trợ ở thời điểm chạy.

Gradle:

```groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-runtime'
}
```

Maven:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-runtime</artifactId>
    <scope>runtime</scope>
</dependency>
```

Nếu dự án đã quản lý phiên bản bằng Spring Modulith BOM tương thích với Spring Boot của ứng dụng, không cần khai báo version riêng cho dependency này. Hãy giữ các artifact Spring Modulith trên cùng một release train để tránh khác biệt API hoặc auto-configuration giữa các module.

## 3. Bật RuntimeApplicationModuleVerifier

Runtime verification là tính năng opt-in. Sau khi thêm runtime dependency, bật thuộc tính `spring.modulith.runtime.verification-enabled`:

```properties
spring.modulith.runtime.verification-enabled=true
```

Có thể đặt thuộc tính trong `application.yml`:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Khi thuộc tính được bật, runtime support đăng ký và thực thi verifier trong quá trình khởi động ứng dụng. Khi không bật, ứng dụng không chạy startup verification chỉ vì dependency runtime đã có mặt.

Ví dụ cấu hình tối thiểu:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Không cần tự tạo `RuntimeApplicationModuleVerifier` trong `main()` hoặc gọi một phương thức verify thủ công. Runtime support quản lý việc kích hoạt verifier theo cấu hình. Trong test kiến trúc, vẫn có thể gọi `ApplicationModules.of(ShopApplication.class).verify()` trực tiếp để phát hiện lỗi sớm hơn trong vòng đời phát triển.

## 4. Điều gì xảy ra trong startup?

Luồng xử lý ở mức khái niệm:

```text
Spring Boot bắt đầu khởi động
          │
          ▼
Runtime support được nạp
          │
          ▼
Kiểm tra verification-enabled
          │
          ├── false ──> Bỏ qua runtime module verification
          │
          └── true
                │
                ▼
       Tạo module model từ ứng dụng
                │
                ▼
       RuntimeApplicationModuleVerifier
                │
                ▼
       Kiểm tra quy tắc module
                │
          ┌─────┴─────┐
          ▼           ▼
      Không lỗi    Có Violations
          │           │
          ▼           ▼
     Startup tiếp   Startup thất bại
```

Khi không có vi phạm, startup tiếp tục theo quy trình bình thường. Khi có vi phạm, verifier làm lộ lỗi kiến trúc ngay trong log khởi động và ứng dụng không được xem là đã sẵn sàng phục vụ traffic.

Không nên phụ thuộc vào một thứ tự nội bộ cụ thể giữa verifier và mọi bean initializer của ứng dụng. Điều cần dựa vào là hợp đồng ở cấp framework: runtime verification được thực hiện trong startup và lỗi kiến trúc làm startup thất bại.

## 5. Ví dụ một vi phạm khiến startup thất bại

Giả sử module `orders` chỉ công khai API ở package gốc và module có kiểu `CLOSED`. Một class của module `inventory` lại import trực tiếp repository nội bộ:

```java
package com.acme.shop.inventory;

import com.acme.shop.orders.internal.OrderRepository;
import org.springframework.stereotype.Service;

@Service
class InventoryOrderLookup {

    private final OrderRepository orders;

    InventoryOrderLookup(OrderRepository orders) {
        this.orders = orders;
    }
}
```

Java có thể biên dịch nếu `OrderRepository` có modifier và chữ ký cho phép truy cập. Tuy nhiên, điều đó không có nghĩa module `inventory` được phép sử dụng package `orders.internal`.

Khi bật runtime verification, Spring Modulith phát hiện dependency vượt ranh giới API. `RuntimeApplicationModuleVerifier` làm startup thất bại với thông tin `Violations` cho biết module và type liên quan. Tên module, package và nội dung exception thực tế phụ thuộc cấu trúc code của ứng dụng.

Để sửa, module `orders` nên công khai một hợp đồng ổn định, ví dụ `OrderLookup`, trong package gốc hoặc named interface. Module `inventory` phụ thuộc hợp đồng đó và khai báo `allowedDependencies` phù hợp nếu dự án dùng allowlist. Không nên đổi `orders` thành `OPEN` chỉ để che lỗi truy cập internal, trừ khi việc mở toàn bộ phần nội bộ là một quyết định migration có chủ đích.

## 6. Đọc log và xử lý lỗi startup

Khi ứng dụng dừng trong startup do verifier, hãy tìm phần exception gốc thay vì chỉ đọc dòng thông báo cuối cùng của Spring Boot. Các bước điều tra:

1. Tìm `Violations` trong stack trace và đọc toàn bộ thông điệp được tổng hợp.
2. Xác định module nguồn và module đích của từng dependency vi phạm.
3. Tìm source type và target type được nhắc đến trong thông báo.
4. Phân loại nguyên nhân: chu trình module, truy cập package nội bộ hoặc dependency ngoài allowlist.
5. Mở source code tạo quan hệ và quyết định hợp đồng module nên được điều chỉnh như thế nào.
6. Chạy architecture test ở bước build để xác nhận lỗi đã được sửa trước khi triển khai lại.

Ví dụ, nếu log cho biết `inventory` phụ thuộc một type không được expose trong `orders`, hãy kiểm tra import hoặc chữ ký phương thức trong `inventory` trước. Nếu log cho biết có dependency cycle, hãy xem toàn bộ các cạnh tạo thành chu trình thay vì chỉ sửa cạnh đầu tiên được in ra.

Không nên bắt `Violations` rồi bỏ qua để ứng dụng tiếp tục khởi động. Làm như vậy vô hiệu hóa mục đích của runtime verifier và cho phép artifact vi phạm kiến trúc đi vào trạng thái phục vụ traffic.

## 7. Runtime verification khác architecture test như thế nào?

Hai cách kiểm tra sử dụng cùng khái niệm module model nhưng khác thời điểm, chi phí và mục đích vận hành:

| Khía cạnh | Architecture test | RuntimeApplicationModuleVerifier |
|---|---|---|
| Thời điểm | Trong test/build pipeline | Khi ứng dụng khởi động |
| Cách kích hoạt | Test gọi `ApplicationModules.verify()` | Thêm `spring-modulith-runtime` và bật property |
| Phạm vi | Module model được test tạo ra, có thể tùy chỉnh import option | Module arrangement được runtime support kiểm tra khi startup |
| Phản hồi khi lỗi | Test thất bại và CI có thể chặn build | Startup thất bại và ứng dụng không sẵn sàng |
| Mục tiêu | Phát hiện sớm trong phát triển và review | Bảo vệ môi trường chạy khỏi artifact có cấu trúc module vi phạm |

Nên giữ architecture test làm lớp kiểm tra chính vì developer nhận phản hồi sớm và có thể điều tra trong môi trường phát triển. Runtime verifier là lớp bảo vệ bổ sung cho artifact đã đóng gói và cấu hình triển khai.

Ví dụ architecture test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Test này không cần khởi động toàn bộ ứng dụng. Nó phân tích module model và làm test thất bại nếu cấu trúc vi phạm quy tắc. Runtime verifier kiểm tra lại ở startup theo cấu hình runtime, nên hai lớp có thể cùng tồn tại mà không thay thế nhau.

## 8. Runtime verifier không phải runtime behavior monitor

Tên gọi “runtime verification” dễ gây hiểu nhầm rằng verifier quan sát mọi hành vi khi ứng dụng đang chạy. Trên thực tế, `RuntimeApplicationModuleVerifier` xác minh cấu trúc module ở thời điểm startup.

Nó không chứng minh rằng:

- Mọi Spring bean được tạo thành công trong mọi profile hoặc mọi tổ hợp property.
- Mọi request đi qua đúng use case hoặc đúng module.
- Event listener xử lý thành công, không bị retry hoặc không có lỗi bất đồng bộ.
- Database, message broker và HTTP service bên ngoài đang hoạt động.
- Không có tương tác động qua reflection, tên bean, message broker hoặc hệ thống ngoài vượt khỏi dependency model tĩnh.

Để kiểm tra những điều đó, cần dùng Spring integration test, module integration test, contract test, health indicator, log, metric và distributed tracing phù hợp. Runtime verifier bảo vệ cấu trúc module; các công cụ khác kiểm tra khả năng hoạt động và quan sát hành vi thực tế.

## 9. Cấu hình theo môi trường triển khai

Có thể bật thuộc tính trong cấu hình chung để mọi môi trường đều xác minh module arrangement:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Nếu tổ chức quản lý cấu hình bằng profile, cần đảm bảo profile triển khai thực tế có thuộc tính này. Ví dụ:

```yaml
# application-production.yml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Không nên chỉ bật trong profile local rồi cho rằng production cũng được bảo vệ. Ngược lại, nếu tắt ở một môi trường để phục vụ chẩn đoán, cần ghi nhận lý do và tránh biến ngoại lệ tạm thời thành cấu hình lâu dài.

Runtime verifier kiểm tra module arrangement từ artifact và metadata có trên classpath. Vì vậy, cùng một artifact với cùng module metadata thường cho cùng kết quả kiến trúc ở các môi trường; thay đổi profile không biến một dependency package trái phép thành hợp lệ. Profile có thể ảnh hưởng tới bean wiring và behavior runtime, nhưng đó là phạm vi kiểm thử khác.

## 10. Phân biệt RuntimeApplicationModuleVerifier với ApplicationModuleInitializer

Spring Modulith runtime support còn có `ApplicationModuleInitializer`. Hai thành phần có tên gần nhau nhưng nhiệm vụ khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `RuntimeApplicationModuleVerifier` | Kiểm tra module arrangement trong startup và làm startup thất bại khi có vi phạm |
| `ApplicationModuleInitializer` | Cung cấp callback khởi tạo module; Spring Modulith sắp xếp initializer theo dependency giữa các module |

Verifier trả lời câu hỏi cấu trúc module có tuân thủ quy tắc hay không. Initializer phục vụ việc thực hiện công việc khởi tạo thuộc một module theo thứ tự phụ thuộc. Không dùng initializer để thay thế architecture verification, và không coi thứ tự initializer là thứ tự xử lý request hoặc event trong suốt vòng đời ứng dụng.

## 11. Checklist triển khai runtime verification

- [ ] Ứng dụng đã thêm `spring-modulith-runtime` với phiên bản tương thích cùng release train.
- [ ] Đã bật `spring.modulith.runtime.verification-enabled=true` ở môi trường cần bảo vệ.
- [ ] Module model được phát hiện đúng từ package và metadata của ứng dụng.
- [ ] Architecture test `ApplicationModules.of(...).verify()` vẫn chạy trong build pipeline.
- [ ] Đã thử nghiệm cách ứng dụng phản ứng khi có vi phạm trong môi trường phát triển hoặc test deployment.
- [ ] Log startup được thu thập để có thể đọc đầy đủ `Violations`.
- [ ] Quy trình triển khai coi lỗi verifier là startup failure và không đưa instance đó vào traffic.
- [ ] Không bắt và bỏ qua lỗi kiến trúc để ép ứng dụng tiếp tục chạy.
- [ ] Đã có integration test và monitoring riêng cho bean wiring, event, database và dịch vụ ngoài.
- [ ] Đã phân biệt runtime verifier với `ApplicationModuleInitializer`.

`RuntimeApplicationModuleVerifier` đưa kiểm tra module arrangement vào startup của ứng dụng. Khi kết hợp architecture test ở build time với runtime verification trong môi trường triển khai, nhóm có hai điểm kiểm soát: phát hiện sớm trong quá trình phát triển và xác nhận artifact không vi phạm ranh giới module trước khi ứng dụng phục vụ traffic.

## Tài liệu tham khảo

- [Spring Modulith – Runtime Support](https://docs.spring.io/spring-modulith/reference/runtime.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [RuntimeApplicationModuleVerifier API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/runtime/RuntimeApplicationModuleVerifier.html)
- [ApplicationModuleInitializer API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/runtime/ApplicationModuleInitializer.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
