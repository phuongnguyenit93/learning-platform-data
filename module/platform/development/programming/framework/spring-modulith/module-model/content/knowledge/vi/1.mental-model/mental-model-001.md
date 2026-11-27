# Spring Modulith mô hình hóa phần nào của ứng dụng Spring Boot?

Bài này thuộc chương **Mô hình tư duy** của module **SPRING_MODULITH_MODULE_MODEL**. Module hướng tới việc học mô hình mô-đun của Spring Modulith để xác định ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package trong một ứng dụng Spring Boot. Câu hỏi trung tâm là: Spring Modulith nhìn ứng dụng như một tập hợp những phần nào, và mô hình đó giúp ta kiểm soát kiến trúc ra sao?

## Câu trả lời cốt lõi

Spring Modulith mô hình hóa một ứng dụng Spring Boot thành **các application module có ranh giới package rõ ràng và các quan hệ phụ thuộc giữa chúng**.

Mỗi module thường đại diện cho một năng lực nghiệp vụ, chẳng hạn đơn hàng, kho hàng, khách hàng hoặc thanh toán. Mô hình ghi nhận:

- Module nằm ở package nào và bao gồm những kiểu Java nào.
- Phần nào của module được công khai để module khác sử dụng.
- Module đang phụ thuộc vào module nào.
- Những quy tắc phụ thuộc nào được cho phép hoặc bị vi phạm.

Có thể hình dung mô hình như một đồ thị có hướng: mỗi application module là một nút, còn việc một module sử dụng kiểu được cung cấp bởi module khác tạo nên quan hệ phụ thuộc. Ranh giới công khai quyết định cạnh đó có hợp lệ hay không.

Đây là mô hình kiến trúc ở cấp package trong **một ứng dụng**. Spring Modulith không tự biến các package thành tiến trình độc lập, không tự chia ứng dụng thành microservice và cũng không tự quyết định ranh giới nghiệp vụ thay cho nhóm phát triển.

## 1. Điểm bắt đầu: package gốc của ứng dụng Spring Boot

Spring Modulith dùng package chứa lớp cấu hình ứng dụng Spring Boot làm điểm bắt đầu để khám phá application module. Thông thường, đó là package chứa lớp có annotation **@SpringBootApplication**.

Ví dụ, ứng dụng bán hàng có cấu trúc:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
├── inventory
│   ├── StockQuery.java
│   └── api
│       └── StockAvailability.java
├── customer
│   └── CustomerProfile.java
└── payment
    └── PaymentService.java
~~~

Nếu **ShopApplication** nằm trong package **com.acme.shop**, các package con trực tiếp như **order**, **inventory**, **customer** và **payment** là những ứng viên application module. Các package con sâu hơn thuộc cấu trúc bên trong module tương ứng; chúng không tự động trở thành các module cấp cao ngang hàng chỉ vì có thư mục riêng.

Có thể yêu cầu Spring Modulith xây dựng mô hình từ lớp ứng dụng:

~~~java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
~~~

Đối số là lớp ứng dụng làm mốc khám phá. Vì vậy, chọn đúng lớp ứng dụng và tổ chức package bên dưới nó là điều kiện quan trọng. Nếu một phần mã nằm ngoài cây package gốc, đừng mặc định rằng nó sẽ được nhận diện như module của ứng dụng.

Tên module được suy ra từ cấu trúc package. Do đó, package là một phần của thiết kế kiến trúc, không chỉ là nơi đặt file cho tiện.

## 2. Application module đại diện cho một ranh giới nghiệp vụ

Một application module nên gom những thành phần cùng phục vụ một phần trách nhiệm nghiệp vụ. Ví dụ:

- **order** quản lý vòng đời đơn hàng.
- **inventory** quản lý tồn kho và khả năng giữ hàng.
- **customer** quản lý hồ sơ khách hàng.
- **payment** xử lý nghiệp vụ thanh toán.

Ranh giới này giúp trả lời hai câu hỏi thiết kế quan trọng:

1. Thành phần nào nên thuộc cùng một khu vực trách nhiệm?
2. Thành phần ở module khác cần biết điều gì để phối hợp với khu vực đó?

Module không đồng nghĩa với một Maven module hoặc Gradle subproject. Nhiều application module có thể cùng nằm trong một project build và cùng chạy trong một tiến trình Spring Boot. Việc chia package thành application module tạo ra ranh giới kiến trúc ở cấp mã nguồn; việc tách thành project hoặc dịch vụ triển khai độc lập là quyết định khác.

Một module thường có các thành phần nội bộ như service, repository, entity, adapter và các lớp hỗ trợ. Không phải mọi lớp trong số đó đều nên trở thành API cho module khác.

## 3. API công khai và phần nội bộ của module

Một ranh giới module chỉ hữu ích khi ta xác định được phần nào bên ngoài được phép sử dụng.

Theo quy ước mặc định, package gốc của module là API công khai của module. Ví dụ, các kiểu được đặt trong **com.acme.shop.order** có thể được module khác tham chiếu như phần giao diện mặc định. Những package con như **com.acme.shop.order.internal** thuộc phần triển khai nội bộ và không nên bị module khác truy cập trực tiếp.

Nếu cần công khai thêm một phần nằm trong package con, Spring Modulith hỗ trợ **named interface**. Ta đánh dấu package đó bằng annotation **@NamedInterface** trong file **package-info.java**.

Ví dụ, module kho hàng muốn cung cấp một giao diện có tên **api**:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
~~~

Một kiểu được cung cấp qua package này có thể được module đơn hàng sử dụng:

~~~java
package com.acme.shop.inventory.api;

public interface StockAvailability {

    boolean hasAvailableStock(String productId, int quantity);
}
~~~

Module đơn hàng gọi qua giao diện đã công khai:

~~~java
package com.acme.shop.order;

import com.acme.shop.inventory.api.StockAvailability;

public class OrderManagement {

    private final StockAvailability stockAvailability;

    public OrderManagement(StockAvailability stockAvailability) {
        this.stockAvailability = stockAvailability;
    }

    public boolean canPlaceOrder(String productId, int quantity) {
        return stockAvailability.hasAvailableStock(productId, quantity);
    }
}
~~~

Điểm quan trọng là module đơn hàng phụ thuộc vào hợp đồng mà module kho hàng công khai. Nó không cần biết module kho hàng dùng repository, entity hay thuật toán nội bộ nào để tính tồn kho.

Named interface có tên giúp mô tả rõ mục đích của phần API được mở ra. Một module có thể công khai nhiều named interface nếu có những nhóm hợp đồng khác nhau dành cho các bên sử dụng khác nhau.

## 4. Quan hệ phụ thuộc giữa các module

Khi một kiểu trong module A tham chiếu đến kiểu thuộc module B, mô hình có thể ghi nhận module A phụ thuộc vào module B. Quan hệ này có hướng: nếu **order** sử dụng API của **inventory**, ta có phụ thuộc **order → inventory**; điều đó không tự động cho phép **inventory** sử dụng ngược lại **order**.

Một đồ thị phụ thuộc dễ hiểu thường có các đặc điểm:

- Phụ thuộc đi theo hướng trách nhiệm nghiệp vụ rõ ràng.
- Module sử dụng API đã công khai của module khác.
- Các module không tạo thành vòng phụ thuộc.
- Những phụ thuộc được phép có thể được khai báo tường minh để người đọc hiểu chủ đích kiến trúc.

Có thể dùng **@ApplicationModule** trong **package-info.java** của module để khai báo những phụ thuộc được phép. Ví dụ, module đơn hàng được phép sử dụng named interface **api** của kho hàng và API mặc định của khách hàng:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"inventory::api", "customer"}
)
package com.acme.shop.order;
~~~

Tên **inventory::api** biểu thị named interface **api** của module **inventory**. Tên **customer** biểu thị API mặc định của module khách hàng. Cách khai báo cụ thể cần khớp với tên module và named interface thực tế trong ứng dụng.

Khai báo danh sách phụ thuộc được phép làm cho ý định kiến trúc trở nên rõ ràng. Khi module đơn hàng bắt đầu sử dụng một package nội bộ của kho hàng hoặc phụ thuộc vào một module chưa được cho phép, việc kiểm tra kiến trúc có thể phát hiện sai lệch đó.

## 5. Spring Modulith kiểm chứng mô hình như thế nào?

Mô hình chỉ có giá trị thực tế khi nhóm phát triển có thể kiểm tra nó thường xuyên. Spring Modulith cung cấp **ApplicationModules.verify()** để xác minh các quy tắc cấu trúc module đã được mô hình hóa.

Một bài kiểm tra JUnit có thể viết như sau:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đặt kiểm tra này trong bộ test chạy ở CI giúp phát hiện thay đổi làm hỏng ranh giới module ngay trong quá trình phát triển. Chẳng hạn:

- Một module tham chiếu trực tiếp đến kiểu thuộc package nội bộ của module khác.
- Một module tạo ra phụ thuộc chưa được cho phép theo cấu hình.
- Các module tạo thành chu trình phụ thuộc.

Khi kiểm tra thất bại, hãy xem đó là tín hiệu để xem lại hướng phụ thuộc hoặc hợp đồng công khai. Có thể chuyển kiểu cần dùng vào API phù hợp, tạo named interface có chủ đích, thay đổi hướng phối hợp giữa các module hoặc điều chỉnh quy tắc cho phép nếu phụ thuộc đó thực sự thuộc thiết kế.

**verify()** kiểm tra những quy tắc kiến trúc mà mô hình Spring Modulith biểu diễn. Nó không chứng minh rằng mọi ranh giới nghiệp vụ đều đúng, rằng API đã thiết kế tốt, hay rằng toàn bộ hệ thống không có lỗi nghiệp vụ. Chất lượng của kết quả vẫn phụ thuộc vào cách nhóm tổ chức package và khai báo hợp đồng.

## 6. Những điều mô hình này không tự quyết định

Để tránh kỳ vọng sai, cần phân biệt mô hình application module với một số khái niệm gần giống:

| Khái niệm | Spring Modulith mô hình hóa điều gì? |
|---|---|
| Application module | Một phần chức năng của ứng dụng được nhận diện qua cấu trúc package và quy ước module. |
| API công khai | Các kiểu ở package gốc và những named interface được công khai. |
| Phụ thuộc module | Quan hệ sử dụng giữa các module, có thể được đối chiếu với quy tắc phụ thuộc đã khai báo. |
| Maven/Gradle module | Đơn vị cấu hình và xây dựng của hệ thống build; không đồng nhất với application module. |
| Microservice | Đơn vị có ranh giới triển khai và vận hành độc lập; application module không tự trở thành microservice. |
| Ranh giới nghiệp vụ đúng | Quyết định thiết kế cần kiến thức miền và sự đánh giá của nhóm; công cụ không tự suy ra đầy đủ. |

Một package có thể được đặt tên là **payment** nhưng vẫn chứa trách nhiệm không thuộc thanh toán. Ngược lại, nhiều package có thể đang trộn lẫn các năng lực nghiệp vụ khác nhau. Spring Modulith giúp làm rõ và kiểm chứng cấu trúc mà nhóm đã chọn; nó không thể thay thế việc phân tích nghiệp vụ.

Tương tự, việc một lớp có modifier **public** trong Java không có nghĩa mọi module đều nên phụ thuộc vào lớp đó. API kiến trúc được xác định bằng quy ước package và named interface của Spring Modulith. Vì vậy, hãy giữ phần nội bộ ở đúng package và chỉ mở những hợp đồng mà module khác thực sự cần.

## 7. Cách dùng mô hình khi thiết kế ứng dụng

Có thể áp dụng mô hình theo một quy trình ngắn:

1. **Nhận diện năng lực nghiệp vụ.** Chia ứng dụng thành các phần có trách nhiệm dễ giải thích, chẳng hạn đơn hàng, kho hàng và khách hàng.
2. **Tổ chức package theo module.** Đặt các package module trực tiếp dưới package gốc của ứng dụng.
3. **Chọn API công khai.** Đặt hợp đồng ổn định trong package gốc hoặc tạo named interface cho nhóm hợp đồng cần công khai.
4. **Định hướng phụ thuộc.** Để module sử dụng hợp đồng của module cung cấp, tránh tham chiếu vào chi tiết triển khai.
5. **Khai báo quy tắc và kiểm chứng.** Dùng **@ApplicationModule** khi cần giới hạn phụ thuộc và gọi **verify()** trong bài kiểm tra kiến trúc.
6. **Điều chỉnh khi nghiệp vụ thay đổi.** Khi một module có quá nhiều trách nhiệm hoặc nhiều module phụ thuộc chặt vào nhau, xem lại ranh giới và hợp đồng.

Ví dụ, nếu **order** cần kiểm tra tồn kho, nó có thể phụ thuộc vào **StockAvailability** do **inventory** công khai. Nếu **inventory** lại cần gọi trực tiếp **OrderManagement** để báo thay đổi tồn kho, đồ thị phụ thuộc có thể hình thành vòng. Khi đó, nhóm nên xem lại cách phối hợp: xác định bên sở hữu sự kiện hoặc hợp đồng phù hợp, rồi tổ chức lại hướng phụ thuộc để các module không phải biết chi tiết nội bộ của nhau.

## Ghi nhớ

Spring Modulith mô hình hóa **cấu trúc mô-đun bên trong một ứng dụng Spring Boot**: module được nhận diện từ package, API công khai xác định bề mặt giao tiếp, và các tham chiếu giữa module tạo nên đồ thị phụ thuộc. **ApplicationModules** cho phép khám phá mô hình, còn **verify()** giúp kiểm chứng những quy tắc kiến trúc đã đặt ra.

Khi đọc một ứng dụng Spring Modulith, hãy lần lượt hỏi: module nào chịu trách nhiệm cho năng lực nghiệp vụ này, module đó công khai những hợp đồng nào, và các module khác đang phụ thuộc vào nó theo hướng nào? Trả lời được ba câu hỏi này là đã nắm được phần cốt lõi mà mô hình Spring Modulith biểu diễn.
