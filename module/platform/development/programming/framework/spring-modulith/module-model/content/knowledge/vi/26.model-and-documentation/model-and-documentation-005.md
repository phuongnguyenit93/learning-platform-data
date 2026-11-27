# systemName giúp tài liệu dễ hiểu

## Tên hệ thống trong mô hình Spring Modulith

Spring Modulith có thể tạo tài liệu mô tả cấu trúc module của một ứng dụng Spring Boot. Tài liệu đó có thể bao gồm sơ đồ thành phần, quan hệ phụ thuộc và bảng thông tin cho từng module. Khi sơ đồ được chia sẻ cho người mới tham gia dự án, nhóm vận hành hoặc nhóm nghiệp vụ, một tên hệ thống dễ hiểu giúp người đọc nhận ra họ đang xem kiến trúc của sản phẩm nào.

Thuộc tính systemName trong annotation Modulithic cung cấp tên logic, dễ đọc của toàn bộ ứng dụng cho mục đích tài liệu. Ví dụ, package gốc có thể là com.acme.shop, nhưng tên hệ thống hiển thị trong tài liệu có thể là Acme Commerce Platform.

systemName mô tả tên của toàn hệ thống. Nó không đổi tên package Java, không đổi tên từng application module, không thay đổi đồ thị phụ thuộc và không thay thế cấu hình spring.application.name của Spring Boot.

## Khai báo systemName trên lớp ứng dụng

Đặt Modulithic trên lớp Spring Boot application và truyền tên hệ thống:

~~~java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(systemName = "Acme Commerce Platform")
@SpringBootApplication
public class ShopApplication {
}
~~~

Trong ví dụ này:

- com.acme.shop vẫn là package gốc để Spring Modulith phát hiện các application module theo cấu trúc package.
- Acme Commerce Platform là tên logic của toàn bộ hệ thống được dùng trong tài liệu được tạo.
- Các module như orders, inventory và catalog vẫn giữ tên theo mô hình module được phát hiện từ mã nguồn.

Nếu ứng dụng đã dùng @Modulithic, chỉ cần bổ sung thuộc tính systemName vào annotation hiện có. Không cần tạo thêm một lớp cấu hình riêng chỉ để đặt tên.

Thuộc tính này có giá trị mặc định là chuỗi rỗng. Nếu không khai báo, Spring Modulith không có tên hệ thống do ứng dụng cung cấp để đưa vào tài liệu. Vì vậy, nên đặt một tên rõ ràng khi nhóm muốn dùng tài liệu sinh tự động như tài liệu kiến trúc chính thức.

## systemName xuất hiện ở đâu?

systemName dành cho tài liệu do Spring Modulith tạo. Nó cung cấp ngữ cảnh cấp ứng dụng cho các tài liệu mô tả module. Các nội dung chính mà Documenter có thể sinh gồm:

- Sơ đồ thành phần C4 thể hiện toàn bộ module và quan hệ giữa chúng.
- Sơ đồ riêng cho từng module và các module liên quan trực tiếp.
- Application Module Canvas, bảng tóm tắt package gốc, Spring beans, aggregate roots, event được phát hoặc lắng nghe và configuration properties.
- Tài liệu Asciidoc tổng hợp liên kết đến các sơ đồ và canvas đã tạo.

Ví dụ, nếu một repository có nhiều ứng dụng hoặc tài liệu được lưu cùng nhau, tên Acme Commerce Platform giúp người đọc nhận ra sơ đồ thuộc hệ thống thương mại điện tử. Họ không phải suy luận từ tên package hay từ tên của một module đầu tiên trong sơ đồ.

systemName không tự sinh tài liệu. Nhóm vẫn cần gọi Documenter trong một test hoặc quy trình tạo tài liệu đã cấu hình.

## Tạo tài liệu module bằng Documenter

Có thể tạo tài liệu từ mô hình ApplicationModules:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {

    @Test
    void writeModuleDocumentation() {
        var modules = ApplicationModules.of(ShopApplication.class);

        var documenter = new Documenter(modules);
        documenter.writeDocumentation();
        documenter.writeAggregatingDocument();
    }
}
~~~

writeDocumentation() tạo bộ tài liệu gồm sơ đồ tổng quan, sơ đồ từng module và các module canvas. writeAggregatingDocument() tạo file all-docs.adoc liên kết đến những tài liệu đã có.

Theo cấu hình mặc định, Documenter ghi các file vào thư mục spring-modulith-docs trong thư mục build của hệ thống build. Nhóm có thể đưa các file được sinh vào tài liệu dành cho developer, ví dụ trang kiến trúc trong repository hoặc tài liệu onboarding.

Trình tự khái quát:

~~~mermaid
flowchart TD
    A["ShopApplication<br/>@Modulithic(systemName = ...)"] --> B["ApplicationModules.of(...)"]
    B --> C["Documenter"]
    C --> D["Sơ đồ module"]
    C --> E["Module Canvas"]
    C --> F["all-docs.adoc"]
    A -. "Tên hệ thống dùng trong tài liệu" .-> C
~~~

Mô hình module vẫn được suy ra từ package và metadata kiến trúc. systemName bổ sung ngữ cảnh để người đọc nhận diện hệ thống trong tài liệu được sinh.

## Chọn một systemName tốt

Tên hệ thống nên giúp người đọc nhận ra sản phẩm hoặc ứng dụng ở cấp tổng thể. Một số nguyên tắc hữu ích:

- Dùng tên mà nhóm phát triển và người đọc tài liệu cùng hiểu, chẳng hạn Acme Commerce Platform hoặc Customer Service Portal.
- Ưu tiên tên nghiệp vụ hoặc tên sản phẩm ổn định thay vì tên kỹ thuật của package.
- Tránh dùng tên module như orders hoặc inventory vì đó chỉ là một phần của ứng dụng.
- Không đưa hostname, tên namespace Kubernetes, tên máy chủ hoặc môi trường triển khai như dev, staging, production vào systemName. Đây là metadata nhận diện hệ thống trong tài liệu, không phải cấu hình định tuyến hay môi trường.
- Dùng cùng một tên trong các tài liệu kiến trúc được tạo từ cùng ứng dụng để người đọc nhận ra chúng thuộc cùng một hệ thống.

| Giá trị | Đánh giá | Lý do |
|---|---|---|
| Acme Commerce Platform | Phù hợp | Tên sản phẩm ở cấp hệ thống, dễ nhận diện |
| Customer Service Portal | Phù hợp | Diễn đạt rõ mục đích ứng dụng |
| com.acme.shop | Kém rõ nghĩa | Là package kỹ thuật, không phải tên thân thiện |
| orders | Không phù hợp | Là tên một module, không phải toàn hệ thống |
| shop-prod-vm-03 | Không phù hợp | Là tên môi trường hoặc hạ tầng triển khai |

Nếu tên sản phẩm thay đổi, hãy cập nhật systemName để tài liệu mới phản ánh tên mà tổ chức đang sử dụng. Việc đổi tên này không đòi hỏi đổi package hoặc tên module.

## Phân biệt systemName với các cấu hình khác

Có nhiều loại tên trong một ứng dụng Spring Boot và Spring Modulith. Chúng có mục đích khác nhau:

| Cấu hình | Phạm vi | Mục đích |
|---|---|---|
| systemName trên @Modulithic | Toàn ứng dụng | Tên logic dùng trong tài liệu sinh tự động |
| Package gốc | Cấu trúc mã nguồn | Điểm bắt đầu để phát hiện application module |
| Tên application module | Một module | Định danh module trong mô hình và sơ đồ |
| spring.application.name | Ứng dụng Spring Boot | Tên ứng dụng trong cấu hình và tích hợp Spring |
| Tên artifact hoặc image | Đóng gói, triển khai | Định danh artifact hoặc image được build |

Không nên dùng systemName để giải quyết xung đột tên module hoặc thay đổi cách phát hiện module. Nếu cần bổ sung package gốc, khai báo additionalPackages; nếu cần đánh dấu module dùng chung trong kiểm thử tích hợp, cấu hình sharedModules. Những thuộc tính đó giải quyết các nhu cầu kiến trúc khác với việc đặt tên hệ thống cho tài liệu.

## Kiểm tra tên hệ thống đã được cấu hình

Có thể tạo mô hình từ lớp ứng dụng và đọc metadata systemName:

~~~java
var modules = ApplicationModules.of(ShopApplication.class);

modules.getSystemName().ifPresent(System.out::println);
~~~

ApplicationModules cung cấp tên hệ thống dưới dạng Optional vì thuộc tính này có thể không được khai báo. Trong test, nhóm có thể xác nhận tên mong muốn đã được nạp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithMetadataTests {

    @Test
    void exposesLogicalSystemName() {
        var modules = ApplicationModules.of(ShopApplication.class);

        assertThat(modules.getSystemName())
            .contains("Acme Commerce Platform");
    }
}
~~~

Kiểm tra metadata này xác nhận tên logic đã được đọc từ cấu hình Modulith. Nó không thay thế việc tạo tài liệu và mở file kết quả để xác nhận nội dung hiển thị như mong muốn.

## Những nhầm lẫn thường gặp

**Cho rằng systemName đổi tên application module.** systemName là tên của toàn hệ thống trong ngữ cảnh tài liệu. Tên module vẫn được xác định từ cấu trúc và metadata module.

**Cho rằng systemName giống spring.application.name.** Hai thuộc tính phục vụ hai mục đích. systemName dành cho tài liệu Spring Modulith; spring.application.name thuộc cấu hình ứng dụng Spring Boot.

**Cho rằng chỉ cần khai báo systemName là tài liệu tự xuất hiện.** Thuộc tính này cung cấp metadata. Nhóm cần chạy Documenter để tạo sơ đồ, canvas hoặc tài liệu tổng hợp.

**Đặt tên theo môi trường triển khai.** Tên như shop-prod hoặc shop-staging làm tài liệu gắn với một môi trường cụ thể. Nên dùng tên logic của hệ thống và quản lý môi trường bằng cấu hình triển khai.

**Dùng tên module đầu tiên làm tên hệ thống.** Một ứng dụng có nhiều module. Tên tổng thể cần đại diện cho toàn bộ sản phẩm, không đại diện cho một phần chức năng.

## Bài tập vận dụng

Một ứng dụng Spring Boot có package gốc com.acme.booking và ba module bookings, payments, notifications. Nhóm muốn sinh sơ đồ kiến trúc để đưa vào tài liệu onboarding. Hiện tại tài liệu chỉ hiển thị tên package nên người mới khó nhận ra sản phẩm.

Hãy thực hiện các bước sau:

1. Chọn tên logic cho toàn ứng dụng, ví dụ Acme Booking Platform.
2. Khai báo systemName trên @Modulithic ở lớp ứng dụng.
3. Tạo ApplicationModules từ lớp ứng dụng.
4. Dùng Documenter để sinh sơ đồ module và Application Module Canvas.
5. Mở tài liệu được sinh và kiểm tra tên hệ thống có giúp người đọc nhận diện đúng ứng dụng hay không.
6. Xác nhận các tên bookings, payments và notifications vẫn là tên module riêng.

Kết quả mong đợi: tài liệu có ngữ cảnh tên hệ thống Acme Booking Platform; cấu trúc package, tên module và quan hệ phụ thuộc được giữ theo mô hình mã nguồn hiện tại.

## Tiêu chí hoàn tất

Bạn đã nắm được chủ đề khi có thể giải thích vai trò của systemName, khai báo tên logic trên @Modulithic, tạo tài liệu bằng Documenter, và phân biệt tên hệ thống với package gốc, tên module, spring.application.name và tên artifact triển khai.

Tài liệu tham khảo:

- [Spring Modulith — Fundamentals: Customizing the Application Modules Arrangement](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Modulithic API — systemName](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [ApplicationModules API — getSystemName](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Documenter API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.html)
