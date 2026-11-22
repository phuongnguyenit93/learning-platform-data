# Xác định module boundary theo capability

Khi thiết kế ứng dụng modular, một câu hỏi quan trọng là nên chia hệ thống thành những module nào. Cách chia theo layer kỹ thuật như controller, service, repository thường khiến module phụ thuộc chéo rộng và khó thay đổi. Một hướng phù hợp hơn là xác định module boundary theo **business capability**: mỗi module chịu trách nhiệm cho một năng lực nghiệp vụ có ý nghĩa, sở hữu quy tắc và dữ liệu của năng lực đó, đồng thời cung cấp một API rõ ràng cho phần còn lại của hệ thống.

Capability là điều hệ thống cần làm cho người dùng hoặc tổ chức, chẳng hạn quản lý khách hàng, xử lý thanh toán, quản lý đơn hàng, lập hóa đơn hoặc gửi thông báo. Module boundary được đặt quanh capability giúp gom những quyết định thường thay đổi cùng nhau vào một đơn vị và giới hạn những chi tiết mà module khác được phép biết.

## 1. Module boundary theo capability là gì?

Một module boundary xác định:

- Những class, package và resource nào thuộc quyền sở hữu của module.
- Những API nào module công khai để module khác sử dụng.
- Những dependency nào module được phép khai báo.
- Dữ liệu và quy tắc nghiệp vụ nào module tự quản lý.
- Những tương tác nào phải đi qua contract thay vì truy cập implementation trực tiếp.

Ví dụ một hệ thống thương mại điện tử có thể được chia thành:

~~~text
com.example.shop
|-- customer
|   |-- api
|   |-- internal
|-- catalog
|   |-- api
|   |-- internal
|-- order
|   |-- api
|   |-- internal
|-- payment
|   |-- api
|   |-- internal
|-- shipping
|   |-- api
|   |-- internal
|-- notification
    |-- api
    |-- internal
~~~

Mỗi capability sở hữu các quy tắc và model riêng. Order quản lý vòng đời đơn hàng; Payment quản lý việc authorize, capture và refund; Shipping quản lý việc tạo và theo dõi vận chuyển.

Một module không cần biết cách module khác lưu dữ liệu. Order có thể yêu cầu Payment xử lý thanh toán qua API, nhưng không truy cập trực tiếp PaymentRepository hoặc bảng dữ liệu nội bộ của Payment.

## 2. Bắt đầu từ business capability, không bắt đầu từ framework layer

Một cách chia theo layer kỹ thuật thường có cấu trúc:

~~~text
application
|-- controllers
|-- services
|-- repositories
|-- entities
|-- clients
~~~

Cách này gom class theo loại công nghệ. Một thay đổi trong capability Order có thể buộc sửa nhiều package hoặc module khác nhau. Ngược lại, một capability thường trải qua nhiều layer: API, application logic, persistence, integration và domain model.

Chia theo capability:

~~~text
application
|-- order
|   |-- api
|   |-- domain
|   |-- application
|   |-- persistence
|-- payment
|   |-- api
|   |-- domain
|   |-- application
|   |-- integration
|-- shipping
    |-- api
    |-- domain
    |-- application
    |-- integration
~~~

Layer kỹ thuật vẫn có thể tồn tại bên trong module. Điểm khác biệt là chúng nằm trong phạm vi ownership của capability, không trở thành các module dùng chung mà mọi capability đều phụ thuộc.

Hãy bắt đầu bằng câu hỏi: “Năng lực nghiệp vụ nào có thể được mô tả, phát triển và thay đổi tương đối độc lập?”. Sau đó mới quyết định package, module-info.java và cấu trúc build.

## 3. Tìm capability và ranh giới trách nhiệm

Có thể dùng các nguồn sau để xác định capability:

1. **Ngôn ngữ nghiệp vụ:** các danh từ, động từ và quy tắc được chuyên gia nghiệp vụ sử dụng.
2. **Quy trình nghiệp vụ:** các bước có đầu vào, đầu ra và trạng thái riêng.
3. **Quyền sở hữu dữ liệu:** bộ phận hoặc nhóm chịu trách nhiệm về tính đúng đắn của dữ liệu.
4. **Lý do thay đổi:** những quy tắc thường thay đổi cùng nhau.
5. **Tác nhân và hệ thống bên ngoài:** những tương tác có contract riêng như payment gateway, tax service hoặc shipping provider.

Ví dụ, “đặt hàng” có thể bao gồm xác thực giỏ hàng, kiểm tra giá, giữ tồn kho, thanh toán và tạo vận đơn. Không nhất thiết tất cả các bước đó thuộc một module Order. Hãy xác định capability sở hữu từng quy tắc:

| Quy tắc hoặc dữ liệu | Capability có thể sở hữu |
|---|---|
| Trạng thái đơn hàng, tổng tiền đơn | Order |
| Giá bán, mô tả sản phẩm | Catalog |
| Số lượng tồn và giữ hàng | Inventory |
| Authorization, capture, refund | Payment |
| Địa chỉ giao hàng, trạng thái vận chuyển | Shipping |

Một use case có thể điều phối nhiều capability. Module điều phối không nên lấy quyền sở hữu tất cả dữ liệu và quy tắc của những module mà nó gọi.

## 4. Dùng cohesion và coupling để kiểm tra boundary

Một boundary hợp lý có cohesion cao và coupling có kiểm soát.

**Cohesion cao** nghĩa là các class trong module cùng phục vụ một capability và thay đổi vì những lý do nghiệp vụ liên quan. Module Payment có thể chứa payment policy, payment transaction, gateway adapter và API payment nếu chúng cùng phục vụ năng lực thanh toán.

**Coupling thấp** nghĩa là module khác chỉ phụ thuộc vào contract cần thiết. Nếu Order phải biết tên bảng, entity persistence, implementation class và cấu hình nội bộ của Payment thì boundary đang bị rò rỉ.

Một số dấu hiệu boundary chưa tốt:

- Nhiều module phải import package internal của nhau.
- Thay đổi một quy tắc trong capability buộc sửa nhiều module không sở hữu quy tắc đó.
- Module A và B có dependency vòng.
- Một module chỉ chứa một vài class nhưng không có trách nhiệm nghiệp vụ rõ ràng.
- Một module dùng chung trở thành nơi tập trung mọi model và tiện ích.
- Nhiều capability cùng ghi trực tiếp vào dữ liệu do capability khác sở hữu.

Không có số lượng class hay package tối ưu cho mọi module. Kích thước không phải tiêu chí duy nhất. Một module nhỏ vẫn hợp lý nếu nó có contract và lý do thay đổi độc lập; một module lớn có thể hợp lý nếu các phần bên trong cùng một capability và không tạo coupling khó kiểm soát.

## 5. Thiết kế API công khai của module

Module descriptor là nơi thể hiện một phần boundary bằng cơ chế của Java Module System. Chỉ export package chứa contract cần thiết.

Ví dụ:

~~~java
module com.example.payment {
    exports com.example.payment.api;

    requires java.logging;
}
~~~

Cấu trúc package:

~~~text
com.example.payment
|-- api
|   |-- PaymentService.java
|   |-- PaymentRequest.java
|   |-- PaymentResult.java
|-- internal
    |-- DefaultPaymentService.java
    |-- PaymentRepository.java
    |-- GatewayClient.java
~~~

Module Order có thể khai báo:

~~~java
module com.example.order {
    requires com.example.payment;
}
~~~

Và sử dụng contract:

~~~java
package com.example.payment.api;

public interface PaymentService {
    PaymentResult authorize(PaymentRequest request);
}
~~~

Implementation ở package internal không được export. Module khác không thể truy cập trực tiếp các kiểu public nằm trong package không export theo quy tắc truy cập thông thường của named module.

Đừng export toàn bộ package chỉ để sửa một lỗi biên dịch. Mỗi export là một phần contract mà module phải cân nhắc duy trì. Khi cần mở package cho reflection, hãy phân biệt opens với exports và chỉ mở đúng package cho framework hoặc module cần thiết.

## 6. Sở hữu model và dữ liệu theo capability

Một boundary không chỉ giới hạn class access mà còn xác định ai sở hữu dữ liệu và quy tắc của dữ liệu đó.

Ví dụ, Order cần thông tin thanh toán nhưng không nên phụ thuộc vào entity Payment được ánh xạ trực tiếp từ database. Payment nên trả về một contract phù hợp với nhu cầu của Order:

~~~java
public record PaymentResult(
        String transactionId,
        PaymentStatus status
) {
}
~~~

Order giữ dữ liệu đơn hàng của mình và lưu tham chiếu tới transaction ID hoặc kết quả cần thiết. Payment vẫn sở hữu chi tiết gateway, token, trạng thái đối soát và quy tắc retry.

Tránh tạo một module common chứa tất cả entity dùng chung. Một model dùng chung có thể khiến nhiều capability phải thay đổi cùng lúc và làm mờ quyền sở hữu. Chỉ chia sẻ kiểu dữ liệu khi nó thực sự là contract ổn định, có ý nghĩa ở ranh giới giữa các capability.

Nếu hai capability cần cùng một khái niệm nhưng có ngữ nghĩa khác nhau, hãy cân nhắc định nghĩa model riêng ở mỗi boundary và chuyển đổi qua adapter. Ví dụ Customer trong Order có thể chỉ là snapshot tên và địa chỉ tại thời điểm đặt hàng; Customer trong Customer Management có thể chứa hồ sơ và trạng thái hiện tại. Hai model cùng nhắc tới khách hàng nhưng phục vụ hai quy tắc khác nhau.

## 7. Dùng service interface để giảm phụ thuộc implementation

Một module có thể cung cấp API trực tiếp qua interface được export. Khi cần khả năng thay thế implementation hoặc plugin, Java ServiceLoader là một lựa chọn.

Module định nghĩa service contract:

~~~java
module com.example.tax.api {
    exports com.example.tax.api;
}
~~~

~~~java
package com.example.tax.api;

public interface TaxCalculator {
    TaxResult calculate(TaxRequest request);
}
~~~

Module consumer khai báo uses:

~~~java
module com.example.invoice {
    requires com.example.tax.api;
    uses com.example.tax.api.TaxCalculator;
}
~~~

Module provider khai báo provides:

~~~java
module com.example.tax.provider {
    requires com.example.tax.api;

    provides com.example.tax.api.TaxCalculator
        with com.example.tax.provider.DefaultTaxCalculator;
}
~~~

Consumer tìm implementation:

~~~java
TaxCalculator calculator = ServiceLoader
        .load(TaxCalculator.class)
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException("No tax provider available"));
~~~

Service contract nên thuộc một module API ổn định. Provider module phụ thuộc vào API; consumer cũng phụ thuộc vào API. Consumer không cần phụ thuộc vào package implementation của provider.

ServiceLoader phù hợp khi cần chọn provider theo runtime hoặc mở rộng hệ thống bằng plugin. Nếu chỉ có một dependency cố định và không cần discovery, một interface được inject qua constructor có thể đơn giản hơn.

## 8. Quản lý dependency giữa các capability

Vẽ dependency graph trước khi hoàn thiện module descriptor. Ví dụ:

~~~text
                  application
                 /     |      \
                v      v       v
              order  catalog  customer
                |
                v
              payment
                |
                v
           payment-api

shipping  <--- order-api hoặc event contract
~~~

Sơ đồ thực tế cần phản ánh hướng dependency của contract. Một module nên phụ thuộc vào API mà nó cần, không phụ thuộc ngược vào implementation của module cung cấp API.

Các nguyên tắc hữu ích:

- Dependency hướng vào contract ổn định.
- Tránh dependency vòng giữa các capability.
- Không tạo một module common làm trung tâm của mọi module.
- Dùng adapter để cô lập thư viện hoặc hệ thống bên ngoài.
- Dùng event hoặc service contract khi cần giảm coupling giữa các capability.
- Chỉ dùng requires transitive khi module consumer thực sự cần readability được truyền tiếp qua API công khai.

Nếu module A cần kiểu public từ module B, A có thể khai báo requires B. Nếu B chỉ là dependency implementation, không nên tự động dùng requires transitive. Modifier transitive làm dependency được truyền tới module đọc A, nên chỉ dùng khi contract công khai của A thực sự làm lộ kiểu thuộc B.

## 9. Tách module theo capability nhưng không tách quá mức

Một số dấu hiệu nên gộp module:

- Hai module luôn được triển khai và thay đổi cùng nhau.
- Một module không có contract độc lập.
- Các class liên tục gọi qua lại và dependency vòng khó loại bỏ.
- Boundary chỉ phản ánh package kỹ thuật, không phản ánh quyền sở hữu nghiệp vụ.

Một số dấu hiệu nên tách module:

- Một phần có quy tắc nghiệp vụ và nhịp thay đổi riêng.
- Một phần cần được dùng bởi nhiều capability qua API ổn định.
- Một phần có thể thay thế hoặc mở rộng độc lập.
- Một phần cần được giới hạn quyền truy cập hoặc dependency rõ ràng.
- Việc thay đổi một phần hiện buộc các capability không liên quan phải biết implementation của nó.

Đừng chia module chỉ vì một package đã có nhiều class. Cũng đừng giữ tất cả trong một module chỉ vì ứng dụng hiện đang được build thành một artifact. Boundary là quyết định về ownership và dependency; số file JAR có thể được quyết định riêng theo cách triển khai.

## 10. Kiểm thử boundary bằng Java Module System

Module system có thể giúp biến boundary thành quy tắc mà compiler và runtime thực thi.

### Kiểm tra exports

Đảm bảo module chỉ export package API:

~~~java
module com.example.payment {
    exports com.example.payment.api;
}
~~~

Các package internal không được export. Một module khác thử import kiểu trong package internal sẽ gặp lỗi truy cập khi biên dịch theo module path.

### Kiểm tra dependency graph

Dùng jdeps để xem dependency:

~~~bash
jdeps --module-path mods --module com.example.order
~~~

Dùng Java launcher để kiểm tra cấu hình module:

~~~bash
java --module-path mods --validate-modules
~~~

Có thể xem module được resolve khi chạy:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Các công cụ này giúp phát hiện dependency không mong muốn, module thiếu và một số xung đột cấu hình. Chúng không thay thế test nghiệp vụ hoặc kiểm tra quyền sở hữu dữ liệu.

### Kiểm thử API contract

Viết test cho API công khai của module, không kiểm thử implementation qua reflection vào package internal. Test consumer nên biên dịch như một module riêng trên module path để xác nhận contract thực sự sử dụng được từ bên ngoài.

Nếu test cần truy cập package internal, hãy cân nhắc liệu đó có phải test nội bộ của module hay đang kiểm tra một implementation detail không nên trở thành contract.

## 11. Ví dụ quy trình thiết kế từ use case

Giả sử use case “đặt hàng” gồm:

1. Khách hàng gửi yêu cầu tạo đơn.
2. Order kiểm tra thông tin và giá trị đơn.
3. Inventory giữ hàng.
4. Payment authorize thanh toán.
5. Order chuyển trạng thái sang đã xác nhận.
6. Shipping nhận yêu cầu tạo vận đơn.

Có thể phân trách nhiệm:

| Capability | Trách nhiệm sở hữu | Contract cung cấp |
|---|---|---|
| Customer | Hồ sơ và trạng thái khách hàng | CustomerLookup |
| Catalog | Sản phẩm, giá và thông tin bán | ProductQuery |
| Inventory | Tồn kho và reservation | InventoryReservation |
| Order | Đơn hàng và trạng thái vòng đời | OrderService |
| Payment | Transaction, authorization, refund | PaymentService |
| Shipping | Shipment và tracking | ShippingService |

Order điều phối use case nhưng không tự cập nhật bảng Inventory hoặc Payment. Mỗi capability thay đổi trạng thái nội bộ thông qua API của chính nó.

Trong hệ thống modular đơn tiến trình, các module có thể giao tiếp bằng Java interface và lời gọi trực tiếp. Nếu sau này một capability được triển khai thành service riêng, contract có thể được chuyển qua HTTP, messaging hoặc RPC. Boundary rõ ràng giúp thay đổi cách giao tiếp dễ hơn, nhưng module boundary không tự động biến module thành microservice.

## 12. Checklist xác định module boundary

Trước khi tạo hoặc tách module, trả lời các câu hỏi:

- Capability này chịu trách nhiệm cho kết quả nghiệp vụ nào?
- Quy tắc và dữ liệu nào thuộc quyền sở hữu của nó?
- Những class nào thay đổi cùng nhau vì cùng một lý do?
- Module khác cần biết chính xác những API nào?
- Có package internal nào đang bị export không cần thiết?
- Có dependency vòng hoặc dependency tới implementation của module khác không?
- Có model dùng chung nào đang làm mờ ownership không?
- Contract có thể được kiểm thử độc lập không?
- Có cần ServiceLoader, hay dependency injection trực tiếp đã đủ?
- Có thể thay đổi implementation bên trong mà không buộc consumer sửa code không?

Nếu chưa trả lời được các câu hỏi về ownership và contract, chưa nên quyết định module chỉ dựa trên tên package hoặc framework.

## 13. Ghi nhớ

Xác định module boundary theo capability nghĩa là tổ chức module quanh năng lực nghiệp vụ và quyền sở hữu của nó. Module giữ domain rule, dữ liệu và implementation riêng; chỉ export contract mà capability khác thực sự cần. Module khác tương tác qua API hoặc service contract, thay vì truy cập repository, entity và package internal.

Hãy dùng cohesion, coupling, dependency graph và module descriptor để kiểm tra boundary. Chia theo capability giúp hệ thống dễ thay đổi độc lập và giữ ranh giới rõ ràng, nhưng không có nghĩa mỗi capability phải trở thành một microservice hoặc một JAR riêng. Mục tiêu là quyền sở hữu rõ, contract nhỏ và dependency có hướng.

## Tài liệu tham khảo

- Java Language Specification — Modules: https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html
- Java Platform Module System — Module API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html
- Oracle JDK — jdeps: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html
- Oracle JDK — Java Launcher: https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html
