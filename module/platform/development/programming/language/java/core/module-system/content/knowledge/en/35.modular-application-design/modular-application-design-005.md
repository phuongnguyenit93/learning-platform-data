# Tránh module graph quá sâu hoặc quá nhiều cạnh

## Mục tiêu

Sau bài này, bạn có thể đọc module graph của một ứng dụng JPMS, nhận ra chuỗi phụ thuộc quá dài và module có quá nhiều quan hệ requires, hiểu tác động đến khả năng thay đổi và bảo trì, rồi tổ chức module theo ranh giới API, domain và service hợp lý.

## 1. Module graph là gì?

Module graph là đồ thị có hướng mô tả các module và quan hệ phụ thuộc giữa chúng. Mỗi module là một đỉnh (node). Một cạnh có hướng từ A tới B biểu thị module A khai báo requires B, tức A cần đọc module B.

Ví dụ:

~~~text
com.acme.app
    |
    v
com.acme.orders
    |
    v
com.acme.customers
    |
    v
com.acme.database
~~~

Trong sơ đồ này, app phụ thuộc orders, orders phụ thuộc customers, và customers phụ thuộc database. Khi một module được phân giải, JPMS tiếp tục phân giải các dependency mà nó yêu cầu để tạo graph nhất quán.

Một graph tốt thể hiện rõ ranh giới kiến trúc: module ở tầng trên sử dụng API của tầng dưới, các module cùng tầng có mức phụ thuộc hợp lý, và chi tiết triển khai không lan rộng ra toàn hệ thống.

Hai đặc điểm cần chú ý:

- **Độ sâu (depth):** số bước phụ thuộc trên một đường đi dài trong graph. Chuỗi A -> B -> C -> D -> E sâu hơn A -> B -> C.
- **Số cạnh (edges):** số quan hệ phụ thuộc giữa các module. Module có quá nhiều cạnh đi ra thường biết hoặc phụ thuộc vào nhiều thành phần; module có quá nhiều cạnh đi vào có thể đang trở thành điểm nền tảng mà nhiều module phải dùng.

Độ sâu và số cạnh không phải chỉ số chất lượng độc lập. Graph nhỏ nhưng có ranh giới sai vẫn khó bảo trì. Hãy dùng chúng như tín hiệu để điều tra, kết hợp với độ gắn kết, phạm vi API và lý do thay đổi của từng module.

## 2. Vì sao graph quá sâu gây khó bảo trì?

Chuỗi phụ thuộc dài làm kiến trúc khó hiểu và khiến thay đổi ở tầng thấp có thể lan qua nhiều tầng.

~~~text
app -> workflow -> order-service -> customer-service -> persistence -> database-driver
~~~

Khi app cần một thao tác đơn giản, đường đi qua nhiều module khiến người đọc phải hiểu nhiều lớp trung gian. Nếu mỗi module chỉ chuyển tiếp lời gọi mà không sở hữu trách nhiệm riêng, các module đó tạo ra chi phí điều hướng mà không đem lại ranh giới hữu ích.

Graph sâu có thể dẫn đến:

- Khó lần theo nguồn gốc của API hoặc dependency.
- Thay đổi chữ ký ở module thấp buộc nhiều module trung gian phải sửa.
- Khó kiểm thử một phần chức năng vì phải dựng nhiều module theo chuỗi.
- Module trung gian trở thành lớp chuyển tiếp mỏng, chỉ chuyển lời gọi hoặc kiểu dữ liệu.
- Khó tái sử dụng một module riêng lẻ vì nó kéo theo cả chuỗi dependency.

Không phải mọi chuỗi nhiều tầng đều xấu. Domain, application, adapter và infrastructure có thể là các tầng cần thiết. Vấn đề xuất hiện khi tầng trung gian không có trách nhiệm riêng, hoặc API tầng dưới bị truyền xuyên qua nhiều tầng mà không tạo thêm giá trị.

## 3. Vì sao graph có quá nhiều cạnh gây khó bảo trì?

Module có nhiều requires trực tiếp thường phải biết nhiều module khác. Điều này làm tăng coupling và khiến thay đổi ở một module ảnh hưởng đến nhiều nơi.

Ví dụ:

~~~text
             +--> customer
             +--> order
app ---------+--> inventory
             +--> payment
             +--> shipping
             +--> reporting
             +--> notification
~~~

Nếu app trực tiếp gọi mọi module chức năng, nó có thể là composition root hợp lý ở tầng khởi động. Nhưng nếu mọi logic nghiệp vụ đều tập trung trong app, module này sẽ biết quá nhiều và trở thành nơi điều phối, chuyển đổi và phụ thuộc của toàn hệ thống.

Graph có nhiều cạnh cũng có thể xuất hiện khi:

- Các module cùng dùng một module tiện ích quá rộng.
- Module API export quá nhiều package và bị nhiều module sử dụng.
- Nhiều module phụ thuộc vào module trung tâm chứa đủ loại kiểu dữ liệu.
- Dùng requires transitive để truyền dependency dù API không cần công khai dependency đó.
- Chia module quá nhỏ, mỗi thao tác hoặc lớp lại thành một module riêng.

Hệ quả là thay đổi nhỏ có thể đòi hỏi cập nhật nhiều module, việc phân giải và kiểm thử phức tạp hơn, và ranh giới sở hữu mã nguồn khó xác định.

## 4. Chia module theo trách nhiệm, không theo từng class

Module là đơn vị đóng gói, phân giải và kiểm soát truy cập ở cấp kiến trúc. Không nên biến mỗi class thành một module chỉ vì JPMS cho phép.

Một module nên chứa nhóm package có trách nhiệm liên quan chặt chẽ và có lý do thay đổi tương đối giống nhau. Hãy tự hỏi:

- Các kiểu nào thường thay đổi cùng nhau?
- Nhóm chức năng nào có thể được mô tả bằng một API rõ ràng?
- Module nào thực sự cần dùng API của nhóm đó?
- Có thể giữ phần triển khai nội bộ trong cùng module không?
- Module có thể được kiểm thử hoặc tái sử dụng độc lập không?

Ví dụ, module orders có thể chứa các package domain, application và adapter nội bộ của phạm vi đơn hàng nếu chúng cùng thuộc một đơn vị triển khai:

~~~text
com.acme.orders
  com.acme.orders.api
  com.acme.orders.domain
  com.acme.orders.application
  com.acme.orders.internal
~~~

Chỉ tách orders.api thành module riêng khi có nhu cầu thực tế: nhiều module khác cần hợp đồng ổn định, implementation có thể thay thế độc lập, hoặc API cần được phát hành và quản lý phiên bản riêng.

Chia quá nhỏ tạo thêm descriptor, build configuration và dependency declaration. Chia quá lớn làm module có quá nhiều trách nhiệm và export quá nhiều API. Mục tiêu là module có độ gắn kết cao và số dependency vừa đủ.

## 5. Thiết kế hướng phụ thuộc rõ ràng

Một cách tổ chức dễ hiểu là chia thành các tầng có trách nhiệm khác nhau:

~~~text
             com.acme.app
                  |
                  v
        com.acme.orders.application
             /           \
            v             v
  com.acme.orders.domain  com.acme.orders.spi
            ^                    ^
            |                    |
  com.acme.orders.adapter  com.acme.shipping.provider
~~~

Sơ đồ minh họa ý tưởng: application điều phối use case; domain chứa quy tắc nghiệp vụ; adapter kết nối hệ thống ngoài; provider triển khai hợp đồng service. Hãy chọn hướng requires sao cho API ổn định không phụ thuộc ngược vào chi tiết triển khai.

Ví dụ với API và implementation:

~~~text
com.acme.app ----requires----> com.acme.orders.api
com.acme.orders.impl ----requires----> com.acme.orders.api
~~~

Descriptor của implementation:

~~~java
module com.acme.orders.impl {
    requires com.acme.orders.api;
}
~~~

Descriptor của consumer:

~~~java
module com.acme.app {
    requires com.acme.orders.api;
}
~~~

Nếu app phải khởi tạo implementation trực tiếp, nó cần biết module implementation hoặc class triển khai. Có thể tránh dependency đó bằng ServiceLoader: app khai báo uses trên service API, còn implementation khai báo provides. Consumer chỉ phụ thuộc vào hợp đồng và không cần requires trực tiếp provider.

Không cần ép mọi dự án vào cùng một sơ đồ tầng. Điều quan trọng là các dependency có hướng giải thích được và chi tiết triển khai không bị đẩy ngược vào API.

## 6. Giữ API nhỏ và dùng exports có chủ đích

Package được export trở thành bề mặt API mà module khác có thể sử dụng. Export quá nhiều package khiến module dễ bị phụ thuộc vào chi tiết nội bộ.

Ví dụ:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Các package domain hoặc internal không được export sẽ không thể được module khác truy cập theo cách thông thường, dù lớp bên trong khai báo public.

Nếu chỉ một module cụ thể cần truy cập một package, có thể dùng qualified export:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.orders.adapter;
}
~~~

Cách này giữ phạm vi API hẹp. Tuy nhiên, qualified export cũng tạo quan hệ gắn kết cụ thể giữa hai module; chỉ dùng khi đó là ranh giới kiến trúc có chủ đích.

Tránh tạo module common hoặc shared chứa mọi kiểu dùng chung. Module như vậy dễ trở thành điểm tập trung của nhiều cạnh. Hãy chia API theo domain hoặc capability ổn định, và chỉ đưa kiểu dùng chung vào module riêng khi nó thực sự có ngữ nghĩa độc lập.

## 7. Dùng requires transitive đúng lúc

requires transitive truyền readability của dependency tới module phụ thuộc vào module hiện tại. Nó hữu ích khi API công khai làm lộ kiểu từ module khác và người dùng API cần đọc kiểu đó.

Ví dụ:

~~~java
module com.acme.orders.api {
    requires transitive com.acme.money;
    exports com.acme.orders.api;
}
~~~

Nếu một kiểu public trong orders API có phương thức trả về Money, module sử dụng API có thể cần đọc com.acme.money để biên dịch và sử dụng chữ ký đó.

Ngược lại, nếu orders.api chỉ dùng logging ở phần triển khai nội bộ, không nên dùng requires transitive cho logging. Hãy dùng requires thông thường ở module thực sự cần dependency đó.

Dùng transitive quá rộng khiến module ở tầng trên vô tình đọc nhiều module mà nó không trực tiếp cần. Khi API thay đổi, phạm vi ảnh hưởng cũng rộng hơn.

Nguyên tắc thực hành:

- Dùng requires khi chỉ module hiện tại cần dependency.
- Dùng requires transitive khi dependency là phần cần thiết của API công khai mà người dùng module phải đọc.
- Tránh biến module tiện ích hoặc implementation detail thành dependency truyền qua nhiều tầng.
- Xem lại transitive khi API thay đổi.

## 8. Tránh vòng phụ thuộc và phụ thuộc ngược

JPMS yêu cầu module graph hợp lệ và không cho phép chu trình trong quan hệ requires. Nếu A requires B và B requires A, việc phân giải sẽ thất bại.

Ví dụ quan hệ không hợp lệ:

~~~text
com.acme.orders  ----requires----> com.acme.customers
      ^                                  |
      |                                  |
      +-------------requires-------------+
~~~

Vòng phụ thuộc thường cho thấy hai module chưa được chia theo ranh giới phù hợp hoặc hợp đồng chung đang nằm sai chỗ.

Một cách xử lý là trích xuất API hoặc service contract ổn định:

~~~text
com.acme.orders ----requires----> com.acme.customer.spi
com.acme.customers --requires--> com.acme.customer.spi
~~~

Nếu orders cần thông báo cho customers, có thể khai báo service interface hoặc event contract ở module API độc lập. Module triển khai đăng ký provider, consumer sử dụng ServiceLoader hoặc cơ chế điều phối phù hợp.

Không nên tạo module contract chỉ để phá vòng nếu nó gom các kiểu không liên quan. Hợp đồng cần có ngữ nghĩa rõ ràng và thuộc quyền sở hữu của một capability hoặc nhóm chức năng xác định.

## 9. Dùng ServiceLoader để giảm cạnh giữa consumer và provider

Consumer khai báo uses cho service API:

~~~java
module com.acme.app {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentGateway;
}
~~~

Provider khai báo:

~~~java
module com.acme.payment.stripe {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentGateway
        with com.acme.payment.stripe.StripeGateway;
}
~~~

Consumer không cần requires com.acme.payment.stripe. Nó chỉ biết hợp đồng PaymentGateway. Khi chạy, ServiceLoader có thể tìm provider trong module layer thích hợp.

Mô hình này giảm dependency trực tiếp giữa consumer và từng implementation, thuận lợi khi thay provider hoặc nạp plugin. Tuy nhiên, service API vẫn là dependency thực sự; không nên biến mọi lời gọi nội bộ thành service chỉ để giảm số cạnh trên sơ đồ.

Service boundary phù hợp khi có khả năng thay thế implementation, plugin discovery, hoặc cần giữ consumer độc lập với provider. Với lời gọi nội bộ đơn giản giữa hai phần luôn được triển khai cùng nhau, dependency module trực tiếp có thể dễ hiểu hơn.

## 10. Nhận diện module có quá nhiều cạnh

Khi xem descriptor hoặc sơ đồ graph, hãy hỏi:

- Module này requires bao nhiêu module khác?
- Có dependency nào chỉ được dùng trong một class hoặc package nội bộ?
- Nhiều module có cùng phụ thuộc vào một module common rất rộng không?
- Có requires transitive mà API không thực sự để lộ kiểu của dependency không?
- Module có export package mà không module nào cần dùng không?
- Có dependency ngược chiều giữa các tầng hoặc trách nhiệm không?
- Một thay đổi ở module này thường buộc bao nhiêu module khác phải sửa?
- Có module chỉ tồn tại để chuyển tiếp lời gọi hoặc kiểu dữ liệu không?

Không có ngưỡng số cạnh cố định cho mọi dự án. Module app ở composition root có thể có nhiều cạnh vì nhiệm vụ của nó là lắp ghép thành phần. Module domain cốt lõi có quá nhiều dependency ra ngoài lại đáng xem xét kỹ hơn.

Hãy đánh giá cạnh theo ý nghĩa: dependency có cần thiết, ổn định, có hướng đúng và được thể hiện qua API nhỏ hay không.

## 11. Quan sát graph bằng công cụ JDK

Trước khi thay đổi kiến trúc, hãy thu thập thông tin từ các công cụ hiện có.

**jar --describe-module**

Kiểm tra module descriptor:

~~~bash
jar --describe-module --file mods/com.acme.orders.jar
~~~

Lệnh này hiển thị tên module, package export, requires và khai báo service. Nó giúp phát hiện module export quá rộng hoặc khai báo dependency không cần thiết.

**jdeps --check**

Kiểm tra dependency và cảnh báo liên quan đến module:

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

Xem dependency của ứng dụng:

~~~bash
jdeps --module-path mods --list-deps --module com.acme.app
~~~

Đầu ra giúp nhận ra module mà ứng dụng cần trực tiếp hoặc gián tiếp. Hãy so sánh với module-info.java để xem dependency nào nên được khai báo trực tiếp, dependency nào đã được truyền qua API.

**jdeps --dot-output**

Xuất thông tin dependency thành file DOT:

~~~bash
jdeps --module-path mods \
      --dot-output build/module-graph \
      --module com.acme.app
~~~

Có thể mở file DOT bằng công cụ hỗ trợ Graphviz để xem các đỉnh và cạnh. Khi graph lớn, hãy lọc theo module hoặc nhóm chức năng để tập trung vào vùng có nhiều cạnh.

**java --show-module-resolution**

Khi khởi động ứng dụng, tùy chọn này hiển thị thông tin phân giải module:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Nó giúp hiểu module nào được phân giải và quan hệ nào đưa module đó vào graph. Đây là thông tin runtime, bổ sung cho việc đọc descriptor và kết quả jdeps.

## 12. Quy trình refactor graph

Khi phát hiện graph quá sâu hoặc có quá nhiều cạnh, không nên tách hoặc gộp module chỉ dựa trên hình dạng sơ đồ. Hãy làm theo từng bước:

1. Xác định module có vấn đề và các dependency trực tiếp.
2. Xem package export và API public để biết dependency nào thực sự xuất hiện trong hợp đồng.
3. Tìm các module chỉ được dùng để chuyển tiếp lời gọi hoặc kiểu dữ liệu.
4. Xác định ranh giới domain/capability và nhóm mã thay đổi cùng nhau.
5. Nếu có vòng hoặc phụ thuộc ngược, xác định hợp đồng ổn định có thể đặt ở vị trí phù hợp.
6. Loại bỏ requires không dùng và thu hẹp exports khi không còn consumer cần đến.
7. Chỉ thêm requires transitive khi chữ ký API công khai yêu cầu.
8. Cập nhật build, kiểm thử module graph và chạy lại ứng dụng.
9. So sánh graph trước và sau để xác nhận số cạnh giảm vì dependency không cần thiết đã được loại bỏ, không phải vì API bị che giấu hoặc chuyển thành phụ thuộc ngầm.

Refactor nên giữ hành vi ứng dụng ổn định. Mỗi lần thay đổi nhỏ giúp xác định chính xác module descriptor, package access hoặc build configuration gây lỗi.

## 13. Những lỗi thiết kế thường gặp

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Module common có hàng chục dependency ngược về nhiều domain | Module dùng chung đang chứa nhiều trách nhiệm | Chia theo capability và đưa hợp đồng về module sở hữu đúng ngữ nghĩa |
| Một thay đổi nhỏ làm nhiều module phải sửa | API công khai quá rộng hoặc dependency truyền qua nhiều tầng | Thu hẹp API, giảm requires transitive và ổn định hợp đồng |
| Chuỗi module chỉ chuyển tiếp lời gọi | Tầng trung gian không có trách nhiệm riêng | Gộp phần chuyển tiếp hoặc xác định trách nhiệm thực sự của tầng |
| Hai module không thể phân giải vì requires vòng | Ranh giới module sai hoặc hợp đồng bị đặt sai nơi | Trích xuất SPI/API ổn định hoặc đảo chiều dependency qua abstraction |
| Mọi module đều phụ thuộc vào module tiện ích lớn | Tiện ích đang trở thành module trung tâm | Chia thành các API nhỏ, có ngữ nghĩa rõ ràng |
| Module provider bị consumer tham chiếu trực tiếp | Consumer biết implementation cụ thể | Cân nhắc service contract và ServiceLoader nếu cần thay thế provider |
| Quá nhiều module nhỏ gây khó build | Phân rã theo class/package thay vì trách nhiệm | Gộp các phần có độ gắn kết cao và vòng đời thay đổi giống nhau |

## Ghi nhớ

Module graph mô tả hướng requires giữa các module. Graph quá sâu làm tăng số tầng phải hiểu và khiến thay đổi lan qua nhiều lớp; graph quá nhiều cạnh làm tăng coupling và phạm vi ảnh hưởng. Hãy tổ chức module theo capability có độ gắn kết cao, giữ API và exports nhỏ, dùng requires transitive đúng lúc, tránh vòng phụ thuộc, và dùng ServiceLoader khi cần tách consumer khỏi provider. Các công cụ jar --describe-module, jdeps và java --show-module-resolution giúp quan sát graph trước khi refactor.