# Biểu đồ không thay thế hợp đồng access

Biểu đồ module giúp nhóm nhìn thấy cấu trúc ứng dụng, các module và quan hệ phụ thuộc giữa chúng. Spring Modulith có thể sinh những biểu đồ này từ mô hình `ApplicationModules` bằng `Documenter`. Tuy nhiên, biểu đồ là tài liệu mô tả cấu trúc được phát hiện tại thời điểm sinh; nó không tự định nghĩa package nào được phép truy cập hoặc ngăn mã nguồn tạo ra phụ thuộc mới.

Hợp đồng truy cập phải được thể hiện trong cấu trúc package và metadata của module, chẳng hạn API package mặc định, `@NamedInterface` và `@ApplicationModule(allowedDependencies = …)`. Bài kiểm tra `ApplicationModules.verify()` mới là bước kiểm chứng mã nguồn có tuân thủ các quy tắc đó hay không. Bài học này hướng dẫn cách kết hợp biểu đồ, hợp đồng access và kiểm tra kiến trúc để tài liệu luôn có ý nghĩa với người phát triển.

## 1. Biểu đồ module trả lời câu hỏi gì?

Một ứng dụng modular monolith có thể chứa nhiều module nghiệp vụ như `order`, `inventory`, `billing` và `notification`. Khi số lượng module tăng lên, việc chỉ đọc package hoặc lần theo các câu lệnh `import` trở nên khó khăn. Một biểu đồ tổng quan giúp trả lời các câu hỏi:

- Ứng dụng hiện có những module nào?
- Module nào đang phụ thuộc vào module nào?
- Một module cụ thể phụ thuộc trực tiếp vào những module nào?
- Thành phần Spring, aggregate root, event được phát hoặc lắng nghe và cấu hình nào thuộc module đó?

Spring Modulith cung cấp `Documenter` để sinh các tài liệu dựa trên mô hình `ApplicationModules`. Tùy lựa chọn, tài liệu có thể bao gồm:

- Biểu đồ component theo phong cách C4 cho toàn bộ ứng dụng.
- Biểu đồ component riêng cho từng module và các module mà nó phụ thuộc trực tiếp.
- Module Canvas dạng bảng, tóm tắt các thành phần đáng chú ý của module như Spring beans được expose, aggregate roots, event được phát và lắng nghe, cùng configuration properties.
- Tài liệu AsciiDoc tổng hợp để liên kết các biểu đồ và canvas đã tạo.

Các biểu đồ giúp người đọc hiểu quan hệ ở cấp module. Module Canvas bổ sung thông tin về thành phần bên trong. Cả hai hữu ích cho onboarding, review kiến trúc và trao đổi về thay đổi cấu trúc.

Lưu ý rằng danh sách event được phát trong Module Canvas cần event type được nhận diện theo quy ước jMolecules, chẳng hạn gắn `@DomainEvent` hoặc triển khai `DomainEvent`. Danh sách event được lắng nghe được suy ra từ các listener mà Spring Modulith nhận diện, như phương thức dùng `@EventListener`, `@TransactionalEventListener` hoặc bean triển khai `ApplicationListener`. Vì vậy, Canvas là bản tóm tắt theo metadata và các cấu trúc mà công cụ nhận diện được; nó không thay thế việc đọc code xử lý nghiệp vụ.

## 2. Sinh tài liệu bằng `Documenter`

Để dùng `Documenter`, dự án cần dependency tài liệu Spring Modulith tương ứng, thường là `spring-modulith-docs`, cùng phiên bản tương thích với Spring Modulith đang dùng. Có thể gọi nó trong một bài test tài liệu:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {

    @Test
    void generateModuleDocumentation() {
        var modules = ApplicationModules.of(ShopApplication.class);

        modules.verify();

        new Documenter(modules).writeDocumentation();
    }
}
```

`ApplicationModules.of(ShopApplication.class)` tạo mô hình module từ package của ứng dụng. Lời gọi `verify()` kiểm tra các ràng buộc kiến trúc trước khi nhóm xuất tài liệu. Sau đó, `writeDocumentation()` sinh bộ tài liệu mặc định, gồm biểu đồ tổng quan, biểu đồ từng module và Module Canvas.

Nếu chỉ cần biểu đồ component, có thể gọi các phương thức cụ thể:

```java
new Documenter(modules)
        .writeModulesAsPlantUml()
        .writeIndividualModulesAsPlantUml();
```

Nếu muốn sinh riêng Module Canvas:

```java
new Documenter(modules).writeModuleCanvases();
```

Theo cấu hình mặc định, `Documenter` ghi kết quả vào thư mục `spring-modulith-docs` bên trong thư mục build của dự án. Hãy xem phiên bản Spring Modulith của dự án để chọn đúng API và dependency; các phương thức và tùy chọn tài liệu có thể được bổ sung giữa các phiên bản.

## 3. Tùy chỉnh kiểu biểu đồ

Spring Modulith hỗ trợ biểu đồ component theo phong cách C4 và UML. Nếu nhóm muốn dùng UML truyền thống, có thể cấu hình `DiagramOptions`:

```java
import org.springframework.modulith.docs.Documenter;
import org.springframework.modulith.docs.Documenter.DiagramOptions;
import org.springframework.modulith.docs.Documenter.DiagramOptions.DiagramStyle;

var options = DiagramOptions.defaults()
        .withStyle(DiagramStyle.UML);

new Documenter(modules)
        .writeModulesAsPlantUml(options)
        .writeIndividualModulesAsPlantUml(options);
```

Hãy chọn kiểu thể hiện phù hợp với người đọc và quy ước tài liệu của nhóm. C4 có thể dễ tiếp cận khi trình bày kiến trúc module ở mức khái quát; UML component phù hợp với nhóm đã quen cách biểu diễn component và dependency. Việc đổi kiểu biểu đồ chỉ thay đổi cách trình bày mô hình.

## 4. Biểu đồ thể hiện dependency, không định nghĩa quyền truy cập

Giả sử biểu đồ thể hiện `inventory` phụ thuộc `order`. Mũi tên cho biết mô hình phát hiện một quan hệ phụ thuộc. Nó không tự trả lời đầy đủ các câu hỏi sau:

- `inventory` được phép truy cập mọi package của `order` hay chỉ một phần API?
- `inventory` có được phép phụ thuộc thêm `billing` không?
- Một thay đổi trong code có vô tình import kiểu thuộc package `order.internal` không?
- Một dependency mới có làm vi phạm chiều phụ thuộc đã thống nhất không?

Những câu hỏi đó thuộc hợp đồng access của module. Trong Spring Modulith, package gốc của module là API package mặc định. Các package con được xem là nội bộ đối với module khác, trừ khi được công khai rõ ràng qua named interface hoặc module được khai báo là open. Nhóm có thể giới hạn các module mà một module được phép phụ thuộc bằng `allowedDependencies`.

Do đó, một biểu đồ có thể giúp người đọc phát hiện một quan hệ đáng chú ý, nhưng quy tắc cho phép hay từ chối quan hệ phải nằm trong metadata module và được xác minh tự động.

## 5. Khai báo named interface để công khai một phần API

Giả sử module `order` muốn công khai một SPI trong package `order.spi`, trong khi vẫn giữ các package triển khai khác ở trạng thái nội bộ. Khai báo named interface trong `package-info.java` của package đó:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.order.spi;
```

Các kiểu public trong `com.acme.shop.order.spi` trở thành một phần giao diện có tên `spi` mà module khác có thể tham chiếu. Ví dụ, `OrderLookup` là một contract thuộc SPI:

```java
package com.acme.shop.order.spi;

import java.util.Optional;
import java.util.UUID;

public interface OrderLookup {

    Optional<OrderSummary> findById(UUID orderId);
}
```

Module `inventory` có thể giới hạn dependency chỉ tới named interface này bằng `@ApplicationModule` trên package gốc:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "order::spi"
)
package com.acme.shop.inventory;
```

Ký hiệu `order::spi` có nghĩa module `inventory` được phép tham chiếu named interface `spi` của module `order`. Nếu module `inventory` cần cả API ở package gốc của `order`, hãy khai báo rõ cả hai dependency theo quy tắc của dự án. Không nên mở rộng quyền truy cập chỉ vì một biểu đồ đang hiển thị quan hệ giữa hai module.

Named interface là một hợp đồng package thực sự. Biểu đồ có thể hỗ trợ giải thích quan hệ, nhưng chính `@NamedInterface` và khai báo `allowedDependencies` mới mô tả phần API được công khai và chiều phụ thuộc được cho phép.

## 6. Giới hạn dependency của một module

Nếu module `inventory` chỉ được phép phụ thuộc vào `order` và `catalog`, nhóm có thể khai báo:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {"order", "catalog"}
)
package com.acme.shop.inventory;
```

Khi một module có khai báo `allowedDependencies`, những dependency tới module khác ngoài danh sách cho phép sẽ bị từ chối trong quá trình kiểm chứng. Nếu không khai báo `allowedDependencies`, Spring Modulith vẫn kiểm tra quyền truy cập API package và các ràng buộc cấu trúc mặc định; việc không khai báo danh sách không có nghĩa mọi package nội bộ đều trở thành API.

Để duy trì hợp đồng ổn định, hãy giới hạn danh sách theo nhu cầu nghiệp vụ thực tế. Khi một dependency mới xuất hiện, nhóm nên xem xét liệu đó là quan hệ cần thiết hay dấu hiệu module đang biết quá nhiều về module khác.

## 7. Dùng `verify()` để biến hợp đồng thành kiểm tra tự động

Biểu đồ và annotation chỉ hữu ích khi thay đổi code được kiểm tra theo các quy tắc đã khai báo. Spring Modulith cung cấp `ApplicationModules.verify()` để kiểm tra ít nhất các nhóm ràng buộc sau:

- Đồ thị dependency giữa application module không có chu trình.
- Module chỉ tham chiếu kiểu thuộc API package được phép; tham chiếu tới package nội bộ của module khác bị từ chối, trừ trường hợp module được khai báo open.
- Nếu module khai báo `allowedDependencies`, các dependency phải nằm trong danh sách được phép.

Tạo một bài kiểm tra kiến trúc và chạy nó trong CI:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void moduleAccessShouldRespectTheDeclaredContracts() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu một lớp trong `inventory` import `com.acme.shop.order.internal.OrderRepository`, bài kiểm tra có thể báo vi phạm vì module đang truy cập package nội bộ. Nếu `inventory` tham chiếu một module không nằm trong `allowedDependencies`, bài kiểm tra cũng báo vi phạm. Khi đó, nhóm phải sửa dependency hoặc điều chỉnh hợp đồng module sau khi review quyết định kiến trúc.

`verify()` ném ngoại lệ khi phát hiện vi phạm, vì vậy bài test thất bại và CI có thể chặn thay đổi. Đây là cơ chế thực thi ở cấp kiểm tra kiến trúc; bản thân biểu đồ không có khả năng chặn một câu lệnh `import` trong lúc biên dịch.

## 8. Đọc biểu đồ cùng với hợp đồng access

Khi review một thay đổi, hãy đọc biểu đồ và metadata theo trình tự:

1. Xác định module nguồn và module đích của mỗi dependency trên biểu đồ.
2. Xem module nguồn có khai báo `allowedDependencies` hay không.
3. Xác định kiểu được tham chiếu thuộc package gốc, named interface hay package nội bộ.
4. Chạy `ApplicationModules.verify()` để kiểm tra dependency thực tế có tuân thủ quy tắc hay không.
5. Sinh lại tài liệu sau khi cấu trúc thay đổi và cập nhật biểu đồ trong tài liệu phát triển của dự án.

Ví dụ, biểu đồ cho thấy `inventory → order`. Nếu `inventory` chỉ được phép truy cập `order::spi`, một import từ `order.spi.OrderLookup` là phù hợp. Import từ `order.internal.OrderRepository` vi phạm hợp đồng dù biểu đồ tổng quan vẫn chỉ hiển thị cùng một mũi tên `inventory → order`.

```mermaid
flowchart TD
    A[Đọc dependency trên biểu đồ] --> B[Kiểm tra allowedDependencies]
    B --> C[Kiểm tra package hoặc named interface được tham chiếu]
    C --> D[Chạy ApplicationModules.verify()]
    D --> E{Hợp đồng được tuân thủ?}
    E -->|Có| F[Cập nhật tài liệu biểu đồ]
    E -->|Không| G[Sửa code hoặc review lại hợp đồng]
    G --> D
```

## 9. Giữ tài liệu đồng bộ với code

Biểu đồ được sinh từ mô hình module tại thời điểm chạy `Documenter`. Nếu nhóm thay đổi package, thêm module, khai báo named interface hoặc thêm dependency, biểu đồ cũ có thể không còn phản ánh cấu trúc hiện tại.

Một quy trình tài liệu phù hợp có thể gồm:

- Chạy bài test kiến trúc để xác minh các hợp đồng access.
- Sinh lại component diagram và Module Canvas khi có thay đổi cấu trúc module.
- Review diff của PlantUML hoặc AsciiDoc cùng với thay đổi source code.
- Lưu tài liệu được sinh vào vị trí mà nhóm thống nhất để người phát triển dễ tìm.
- Đưa bước sinh tài liệu vào quy trình build hoặc tài liệu CI khi dự án cần tài liệu luôn được cập nhật.

Không nên xem việc biểu đồ không thay đổi là bằng chứng rằng hợp đồng access không thay đổi. Một thay đổi import từ package này sang package khác trong cùng module dependency có thể làm vi phạm hợp đồng mà biểu đồ tổng quan vẫn giữ nguyên. Vì vậy, luôn chạy kiểm tra kiến trúc sau thay đổi source code.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
|---|---|---|
| Biểu đồ có mũi tên nghĩa là module được phép truy cập mọi kiểu của module đích | Có thể dẫn tới import package nội bộ | Kiểm tra API package, named interface và `allowedDependencies`. |
| Biểu đồ không có mũi tên nghĩa là code chắc chắn không có dependency | Có thể đọc nhầm hoặc dùng tài liệu cũ | Sinh lại biểu đồ từ `ApplicationModules` và chạy `verify()`. |
| Chỉ cần sinh tài liệu là đã kiểm chứng kiến trúc | Dependency sai vẫn có thể xuất hiện trong mô hình được tài liệu hóa | Gọi `verify()` trong test để làm thất bại build khi vi phạm. |
| `public` trong Java đồng nghĩa với public API của module | Kiểu public trong package con vẫn có thể là nội bộ | Dùng package gốc hoặc `@NamedInterface` để xác định API module. |
| `allowedDependencies` công khai mọi package của module đích | Bên gọi có thể tham chiếu quá nhiều chi tiết | Dùng cú pháp `module::namedInterface` khi chỉ cần một named interface. |
| Tài liệu sinh một lần có thể dùng mãi | Biểu đồ nhanh chóng lỗi thời | Sinh lại và review diff khi cấu trúc thay đổi. |

## 11. Ghi nhớ khi thiết kế tài liệu kiến trúc

`Documenter` giúp tạo ra hình ảnh dễ đọc về module và dependency hiện có. Hợp đồng access được định nghĩa bằng ranh giới package, named interface và `allowedDependencies`. `ApplicationModules.verify()` kiểm tra code có tuân thủ hợp đồng đó hay không.

Hãy dùng cả ba trong cùng quy trình: biểu đồ để trao đổi, metadata để khai báo quyền truy cập và bài kiểm tra kiến trúc để phát hiện vi phạm. Như vậy, tài liệu giải thích được cấu trúc, còn hợp đồng vẫn được kiểm soát khi code thay đổi.

## Tài liệu tham khảo

- [Spring Modulith – Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Spring Modulith – Fundamentals: Application Modules, Named Interfaces and Allowed Dependencies](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith Javadoc – Documenter](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.html)
- [Spring Modulith Javadoc – ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
