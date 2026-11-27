# Shared kernel và phạm vi nên được kiểm soát

Bài này thuộc chương **Module boundary** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp xác định ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package trong một ứng dụng Spring Boot. Khi nhiều application module cần dùng chung một khái niệm nghiệp vụ, nhóm có thể cân nhắc mô hình **shared kernel** — một phần nhỏ của mô hình miền được các bên cùng thống nhất và chia sẻ.

Shared kernel hữu ích khi các module thực sự dùng chung một ý nghĩa nghiệp vụ và cần giữ các quy tắc đó nhất quán. Tuy nhiên, mỗi kiểu dữ liệu được dùng ở nhiều nơi không tự động nên đưa vào một package dùng chung. Nếu phạm vi shared kernel mở rộng tùy tiện, nó có thể trở thành điểm liên kết khiến các module khó thay đổi độc lập.

## 1. Shared kernel là gì?

Trong Domain-Driven Design (DDD), shared kernel là một phần nhỏ của mô hình miền được hai hoặc nhiều bounded context cùng chia sẻ. Các bên thống nhất rằng một số khái niệm, quy tắc hoặc kiểu dữ liệu có cùng ý nghĩa trong những ngữ cảnh đó, và cùng chịu trách nhiệm khi phần được chia sẻ thay đổi.

Ví dụ trong hệ thống thương mại điện tử:

- Module **order** cần biểu diễn số tiền của đơn hàng.
- Module **payment** cần biểu diễn số tiền được yêu cầu thanh toán.
- Cả hai cùng tuân theo một quy tắc về số tiền và loại tiền tệ.

Nếu hai module thực sự có cùng ngữ nghĩa về số tiền, một value object nhỏ như Money có thể là thành phần của shared kernel. Cả hai dùng chung quy tắc biểu diễn và so sánh số tiền, thay vì tự tạo hai kiểu có hành vi khác nhau.

Shared kernel không có nghĩa là gom tất cả các lớp được nhiều module import vào một package. Nó chỉ bao gồm những khái niệm miền mà các bên chủ động thống nhất là giống nhau và cần được duy trì nhất quán.

## 2. Shared kernel khác package common như thế nào?

Tên package không quyết định nó có phải shared kernel hay không. Điều quan trọng là nội dung và trách nhiệm của phần được chia sẻ.

| Khái niệm | Mục đích |
|---|---|
| **Shared kernel** | Chia sẻ một phần nhỏ của mô hình miền có cùng ý nghĩa và quy tắc giữa các bounded context. |
| **Common utilities** | Chứa hàm hoặc tiện ích kỹ thuật dùng lại, ví dụ xử lý chuỗi, định dạng ngày hoặc helper chung. |
| **Shared DTO** | Chia sẻ cấu trúc dữ liệu trao đổi; DTO không nhất thiết thể hiện mô hình miền hoặc quy tắc nghiệp vụ. |
| **Shared persistence model** | Chia sẻ entity, schema hoặc cách truy cập dữ liệu; việc này tạo liên kết ở tầng lưu trữ và thường cần cân nhắc riêng. |

Ví dụ, một hàm chuyển chuỗi thành chữ thường là tiện ích kỹ thuật, không phải shared kernel. Một kiểu Money chứa quy tắc về số tiền và loại tiền tệ có thể là shared kernel nếu order và payment thật sự thống nhất ngữ nghĩa của nó.

Tương tự, không nên đưa toàn bộ JPA entity của đơn hàng vào shared kernel chỉ vì payment cần đọc một vài trường. Payment nên nhận hợp đồng hoặc dữ liệu cần thiết từ module order, thay vì phụ thuộc vào cách order lưu trữ dữ liệu.

## 3. Khi nào nên tạo shared kernel?

Shared kernel phù hợp khi có đủ các điều kiện sau:

- Hai hoặc nhiều module thực sự dùng chung một khái niệm nghiệp vụ với cùng ngữ nghĩa.
- Quy tắc của khái niệm đó cần nhất quán giữa các module.
- Các bên có thể phối hợp khi thay đổi mô hình được chia sẻ.
- Phạm vi chia sẻ đủ nhỏ để hiểu, kiểm tra và duy trì.
- Việc chia sẻ giúp giảm sai lệch mô hình mà không buộc các module phụ thuộc vào chi tiết nội bộ của nhau.

Hãy kiểm tra ý nghĩa nghiệp vụ trước khi chia sẻ một kiểu. Chẳng hạn, **Customer** trong module order có thể chỉ là thông tin người mua tại thời điểm đặt hàng, còn **Customer** trong module loyalty có thể là hồ sơ thành viên với trạng thái và điểm thưởng. Dù cùng tên, hai khái niệm có thể có vòng đời và quy tắc khác nhau. Nếu ép chúng dùng chung một entity, thay đổi của loyalty có thể ảnh hưởng không cần thiết đến order.

Khi ngữ nghĩa khác nhau, mỗi module nên sở hữu mô hình riêng và chuyển đổi tại ranh giới tích hợp. Trùng tên không chứng minh hai khái niệm là một.

## 4. Giới hạn shared kernel ở những khái niệm thực sự ổn định

Một shared kernel tốt thường có phạm vi nhỏ và ít thay đổi hơn các quy trình nghiệp vụ cụ thể. Có thể cân nhắc chia sẻ:

- Value object có ý nghĩa nhất quán, ví dụ Money hoặc một kiểu đo lường có quy tắc rõ ràng.
- Kiểu định danh có ngữ nghĩa chung và được các module thống nhất sử dụng.
- Một số quy tắc miền nền tảng mà các bounded context cùng cam kết duy trì.

Cần thận trọng khi chia sẻ:

- Aggregate hoặc entity có vòng đời riêng trong một bounded context.
- Repository interface gắn với cách lưu trữ của một module.
- JPA entity, quan hệ ORM hoặc bảng dữ liệu nội bộ.
- Service điều phối quy trình chỉ có ý nghĩa trong một module.
- DTO quá rộng, chứa trường riêng của nhiều capability.
- Các lớp tiện ích không mang ngữ nghĩa miền nhưng được đưa vào kernel chỉ vì có nhiều nơi gọi.

Không có danh sách kiểu dữ liệu nào tự động phù hợp với mọi hệ thống. Một kiểu chỉ nên được chia sẻ khi các bên thống nhất ý nghĩa và trách nhiệm của nó. Nếu việc chia sẻ buộc một module phải hiểu vòng đời hoặc chi tiết triển khai của module khác, phạm vi đó có thể đã quá rộng.

## 5. Biểu diễn shared kernel trong Spring Modulith

Spring Modulith không định nghĩa shared kernel như một loại application module đặc biệt và không tự suy luận rằng một package là shared kernel. Shared kernel là quyết định thiết kế theo DDD. Trong ứng dụng Spring Modulith, nhóm có thể biểu diễn phần được chia sẻ thành một application module thông thường, có package gốc và API công khai rõ ràng.

Ví dụ, package gốc của ứng dụng là **com.acme.shop**:

~~~text
com.acme.shop
├── ShopApplication.java
├── sharedkernel
│   └── Money.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       └── PlaceOrderHandler.java
└── payment
    ├── PaymentUseCases.java
    └── internal
        └── RequestPaymentHandler.java
~~~

Vì **sharedkernel**, **order** và **payment** là các package con trực tiếp của package ứng dụng, chúng có thể được Spring Modulith khám phá thành các application module theo quy ước mặc định.

Package gốc của sharedkernel cung cấp API mặc định. Các module order và payment có thể phụ thuộc vào kiểu được công khai ở đó. Những package con bên trong sharedkernel, nếu có, vẫn là nội bộ trừ khi được công khai có chủ đích bằng named interface.

## 6. Ví dụ: chia sẻ value object Money

Giả sử order và payment cùng thống nhất cách biểu diễn số tiền. Shared kernel cung cấp một value object nhỏ:

~~~java
package com.acme.shop.sharedkernel;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {

    public Money {
        Objects.requireNonNull(amount, "amount must not be null");
        Objects.requireNonNull(currency, "currency must not be null");
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException(
                "Cannot add amounts in different currencies"
            );
        }

        return new Money(amount.add(other.amount()), currency);
    }
}
~~~

Kiểu Money thể hiện một quy tắc chung: chỉ cộng hai số tiền khi chúng có cùng loại tiền tệ. Ví dụ này cố ý giữ phạm vi nhỏ; một hệ thống thực tế có thể cần thêm quy tắc làm tròn, độ chính xác, thuế hoặc chuyển đổi tiền tệ theo chính sách riêng.

Module order sử dụng kiểu được chia sẻ để biểu diễn tổng tiền:

~~~java
package com.acme.shop.order;

import com.acme.shop.sharedkernel.Money;

public record OrderTotal(Money value) {
}
~~~

Module payment cũng dùng Money để biểu diễn số tiền cần thu:

~~~java
package com.acme.shop.payment;

import com.acme.shop.sharedkernel.Money;

public record PaymentRequest(Money amount) {
}
~~~

Cả hai module phụ thuộc vào hợp đồng Money. Shared kernel không cần biết order có những trạng thái nào hoặc payment gọi cổng thanh toán nào. Điều đó giữ hướng phụ thuộc từ các capability về phần mô hình chung nhỏ và ổn định.

Ví dụ trên chỉ minh họa cấu trúc kiểu dữ liệu. Trong ứng dụng thực tế, các module vẫn cần xác định ai tạo ra Money, ai chịu trách nhiệm kiểm tra quy tắc nghiệp vụ riêng và cách xử lý các chính sách khác nhau của từng bounded context.

## 7. Kiểm soát hướng phụ thuộc

Một shared kernel chỉ hữu ích nếu các module phụ thuộc vào nó theo hướng rõ ràng. Ví dụ:

~~~text
order ───────┐
             ├──────> sharedkernel
payment ─────┘
~~~

Order và payment có thể phụ thuộc vào sharedkernel. Sharedkernel không nên phụ thuộc ngược lại vào order hoặc payment, bởi khi đó phần dùng chung sẽ bị kéo vào chi tiết của những capability cụ thể và có nguy cơ tạo vòng phụ thuộc.

Có thể khai báo các phụ thuộc được phép trên package gốc của module sử dụng bằng annotation **@ApplicationModule** trong file package-info.java.

Ví dụ, order được phép phụ thuộc vào sharedkernel và inventory:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"sharedkernel", "inventory"}
)
package com.acme.shop.order;
~~~

Payment có thể khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"sharedkernel"}
)
package com.acme.shop.payment;
~~~

Các tên trong allowedDependencies phải khớp với tên module thực tế được khám phá từ package. Đây là ví dụ minh họa; khi áp dụng vào ứng dụng, cần liệt kê đầy đủ những module mà từng module được phép phụ thuộc theo thiết kế.

Nếu chỉ muốn công khai một phần API có tên của sharedkernel, có thể đặt phần đó trong package con và đánh dấu bằng **@NamedInterface**. Khi đó, module sử dụng có thể giới hạn phụ thuộc đến named interface thay vì toàn bộ API mặc định. Chỉ nên tạo named interface khi có ranh giới hợp đồng thực sự cần phân biệt.

## 8. Kiểm soát thay đổi của shared kernel

Vì nhiều module cùng phụ thuộc vào shared kernel, một thay đổi ở đó có thể ảnh hưởng đến nhiều capability. Do vậy, nhóm cần có cách kiểm soát thay đổi rõ ràng.

Một số thực hành hữu ích:

1. **Chỉ định người hoặc nhóm sở hữu.** Có người chịu trách nhiệm xem xét ngữ nghĩa, chất lượng và phạm vi của phần được chia sẻ.
2. **Thống nhất trước khi thay đổi hợp đồng.** Các module sử dụng cần được xem xét tác động khi đổi tên, xóa hoặc thay đổi hành vi của kiểu dùng chung.
3. **Giữ tương thích khi có thể.** Ưu tiên thay đổi bổ sung theo cách không làm hỏng các bên sử dụng; nếu cần thay đổi không tương thích, lập kế hoạch cập nhật đồng bộ.
4. **Kiểm tra hành vi miền.** Test các bất biến và quy tắc của value object, không chỉ kiểm tra rằng mã nguồn biên dịch.
5. **Theo dõi phạm vi phụ thuộc.** Khi một module mới muốn dùng kernel, hãy hỏi liệu nó có thật sự cần cùng khái niệm và quy tắc hay chỉ cần một vài trường dữ liệu.
6. **Định kỳ xem lại nội dung.** Loại bỏ những thành phần không còn được dùng chung hoặc đã có ý nghĩa khác nhau giữa các bounded context.

Trong một modular monolith, các module thường được build và triển khai cùng nhau, nhưng điều đó không làm mất nhu cầu kiểm soát API. Thay đổi một value object dùng chung vẫn có thể ảnh hưởng đến nhiều luồng nghiệp vụ và nhiều nhóm phát triển.

## 9. Khi nào nên chọn cách khác?

Shared kernel không phải lựa chọn mặc định cho mọi tương tác giữa các module.

| Tình huống | Hướng thiết kế nên cân nhắc |
|---|---|
| Hai module dùng cùng một khái niệm miền, cùng quy tắc và có thể phối hợp thay đổi. | Shared kernel nhỏ, có chủ sở hữu rõ ràng. |
| Hai module dùng từ giống nhau nhưng ý nghĩa hoặc vòng đời khác nhau. | Mỗi module sở hữu mô hình riêng; chuyển đổi tại ranh giới. |
| Một module chỉ cần một hành vi từ module khác. | Gọi API công khai của module sở hữu hành vi. |
| Một module cần phản ứng với sự kiện nghiệp vụ mà không cần dùng chung mô hình nội bộ. | Công bố và tiêu thụ application event hoặc hợp đồng sự kiện phù hợp. |
| Nhiều module cần một tiện ích kỹ thuật thuần túy. | Thư viện hoặc package tiện ích phù hợp; không gọi nó là shared kernel nếu không có mô hình miền chung. |

Ví dụ, payment cần biết đơn hàng đã được xác nhận. Điều đó không nhất thiết yêu cầu payment và order chia sẻ entity Order. Order có thể công bố một sự kiện nghiệp vụ như OrderConfirmed, còn payment phản ứng với sự kiện và sử dụng mô hình riêng của mình.

Chọn cách tích hợp dựa trên loại phụ thuộc cần thiết: chia sẻ mô hình chỉ khi ngữ nghĩa thực sự chung; gọi API khi cần yêu cầu một hành vi; dùng sự kiện khi cần thông báo một điều đã xảy ra.

## 10. Kiểm chứng kiến trúc bằng Spring Modulith

Sau khi tổ chức sharedkernel thành application module và khai báo các phụ thuộc được phép, có thể kiểm tra cấu trúc bằng **ApplicationModules.verify()**:

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

Đặt bài kiểm tra này trong bộ test chạy thường xuyên và CI để phát hiện module phụ thuộc vào package nội bộ hoặc tạo ra quan hệ phụ thuộc trái với quy tắc kiến trúc.

Kiểm tra kiến trúc giúp bảo vệ ranh giới package và các quy tắc phụ thuộc đã khai báo. Nó không thể tự xác nhận rằng Money có đúng ngữ nghĩa với mọi bounded context, rằng phạm vi shared kernel đủ nhỏ hay rằng các nhóm đã thống nhất quy trình thay đổi. Những quyết định đó vẫn cần được đánh giá về nghiệp vụ và được quản trị trong quá trình phát triển.

## Ghi nhớ

Shared kernel là phần nhỏ của mô hình miền được nhiều bounded context chủ động chia sẻ vì có cùng ngữ nghĩa và quy tắc. Trong Spring Modulith, nhóm có thể biểu diễn nó thành một application module thông thường, công khai một API nhỏ và để các module nghiệp vụ phụ thuộc vào nó theo hướng một chiều.

Hãy giữ shared kernel nhỏ, ổn định, có chủ sở hữu và có quy trình kiểm soát thay đổi. Nếu một khái niệm có ý nghĩa khác nhau giữa các module, hãy để từng module sở hữu mô hình riêng. Mục tiêu là chia sẻ đúng phần thực sự chung mà vẫn giữ được quyền tự chủ và ranh giới của từng capability.
