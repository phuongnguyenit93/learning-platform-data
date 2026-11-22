# Phân biệt bounded context với đơn vị triển khai dịch vụ

## Mục tiêu bài học

Khi phân rã một hệ thống thành Microservices, rất dễ nghe quy tắc “mỗi bounded context là một microservice”. Quy tắc này có thể là **điểm khởi đầu để suy nghĩ**, nhưng không phải định nghĩa hay bắt buộc của Domain-Driven Design (DDD). Hai khái niệm trả lời **hai câu hỏi khác nhau**:

- **Bounded context:** Trong phạm vi nào một mô hình nghiệp vụ, thuật ngữ và các quy tắc của nó có ý nghĩa nhất quán?
- **Đơn vị triển khai dịch vụ:** Phần mềm nào có thể được đóng gói, phát hành, chạy, mở rộng, giám sát và khôi phục như một đơn vị vận hành?

Một bounded context là **ranh giới ngữ nghĩa và mô hình**. Một đơn vị triển khai là **ranh giới kỹ thuật và vận hành**. Chúng thường nên được điều chỉnh để hỗ trợ nhau, nhưng không đương nhiên trùng nhau theo tỷ lệ 1:1.

Sau bài này, bạn có thể:
- Định nghĩa bounded context và phân biệt nó với subdomain, aggregate, module và microservice.
- Giải thích vì sao một bounded context có thể được triển khai cùng các context khác hoặc bởi nhiều tiến trình/thành phần.
- Nhận diện ranh giới nghiệp vụ trước khi chọn hình thức đóng gói, repository và triển khai.
- Đánh giá một quyết định tách dịch vụ dựa trên tính tự chủ, quyền sở hữu dữ liệu, nhu cầu scale, giao dịch và chi phí phân tán.
- Tránh biến một mô hình nghiệp vụ chưa rõ ranh giới thành hệ thống phân tán phụ thuộc chặt.

## 1. Hai loại ranh giới cùng xuất hiện trong kiến trúc

Hãy tưởng tượng một nền tảng thương mại có chức năng sản phẩm, đặt hàng, kho, thanh toán và vận chuyển.

Ở mức nghiệp vụ, từ “sản phẩm” có thể mang nhiều nghĩa:

- Bộ phận quản lý danh mục xem sản phẩm như thông tin mô tả, hình ảnh, thuộc tính, trạng thái xuất bản.
- Bộ phận bán hàng quan tâm sản phẩm nào được phép đặt, giá đã chốt, các điều kiện khuyến mại.
- Bộ phận kho quan tâm SKU, vị trí lưu trữ, tồn khả dụng, số lượng đã giữ.
- Bộ phận vận chuyển quan tâm trọng lượng, kích thước và điều kiện giao hàng.

Nếu ép tất cả vào một lớp Product chung cho mọi chức năng, trường dữ liệu và quy tắc sẽ nhanh chóng xung đột. Đây là vấn đề về **mô hình nghiệp vụ**. DDD giúp xác định các bounded context như Catalog, Ordering, Inventory, Shipping; mỗi context có mô hình đúng với nhu cầu của nó.

Sau khi xác định ranh giới này, đội ngũ mới cân nhắc **triển khai**:

- Có thể đóng gói cả bốn context trong một ứng dụng modular monolith.
- Có thể triển khai từng context thành dịch vụ độc lập.
- Có thể tạm triển khai Catalog và Pricing cùng một đơn vị, còn Ordering và Inventory thành đơn vị khác.
- Có thể triển khai một context qua API, worker và bộ xử lý sự kiện riêng nhưng vẫn quản lý cùng một mô hình, trách nhiệm nghiệp vụ và quy tắc nhất quán.

Các phương án triển khai khác nhau không tự đổi nghĩa của thuật ngữ “sản phẩm” trong từng context.

~~~text
GÓC NHÌN MÔ HÌNH NGHIỆP VỤ
+----------------+  +----------------+  +----------------+
| Catalog        |  | Ordering       |  | Inventory      |
| Product        |  | OrderLine      |  | StockItem      |
| attributes     |  | price snapshot |  | available qty  |
+----------------+  +----------------+  +----------------+
           Ranh giới bounded context

GÓC NHÌN TRIỂN KHAI (một phương án)
+---------------------------------------------------------+
| Ứng dụng Spring Boot: modular monolith                   |
| [Catalog module] [Ordering module] [Inventory module]   |
+---------------------------------------------------------+
            Một artifact / một lịch deploy

GÓC NHÌN TRIỂN KHAI (phương án khác)
+----------------+  +----------------+  +----------------+
| Catalog API    |  | Ordering API   |  | Inventory API  |
| Deploy A       |  | Deploy B       |  | Deploy C       |
+----------------+  +----------------+  +----------------+
      Các đơn vị có thể triển khai độc lập
~~~

**Điểm cốt lõi:** số bounded context phản ánh sự khác biệt mô hình nghiệp vụ; số đơn vị triển khai phản ánh lựa chọn tổ chức mã, runtime, ownership và vận hành. Không nên dùng một con số để suy ra con số kia.

## 2. Bounded context là gì?

Trong Domain-Driven Design, **bounded context** xác định phạm vi mà một mô hình miền (domain model) và ngôn ngữ chung (ubiquitous language) được dùng với ý nghĩa nhất quán. Bên trong context, các từ, quy tắc, quan hệ và bất biến nghiệp vụ phải được hiểu theo một mô hình được thống nhất giữa người làm nghiệp vụ và người phát triển.

Ví dụ “Order”:
- Trong Ordering, Order là yêu cầu mua hàng của khách, chứa dòng hàng, giá đã chốt và trạng thái đặt.
- Trong Fulfillment, Order có thể được biểu diễn như yêu cầu chuẩn bị giao hàng, ưu tiên phân bổ kiện và tiến độ xử lý.
- Trong Billing, một đơn được quan tâm ở góc độ nghĩa vụ thanh toán, hóa đơn và đối soát.

Cùng một danh từ ngoài đời, nhưng các context có thể có **entity, value object, hành vi, trạng thái và vòng đời** khác nhau. Ranh giới này giúp từng mô hình không phải gánh mọi nghĩa của cùng một thuật ngữ.

### 2.1. Bounded context bao gồm những gì?

Một bounded context có thể xác định:
1. **Ngôn ngữ chung:** thuật ngữ nào được sử dụng và được định nghĩa thế nào.
2. **Mô hình và quy tắc:** entity, value object, aggregate, domain service, invariant thuộc phạm vi nào.
3. **Trách nhiệm:** hành vi nghiệp vụ nào context thực hiện và quyết định.
4. **Hợp đồng với context khác:** dữ liệu, command, event, API và phép chuyển đổi ngữ nghĩa.
5. **Quyền sở hữu mô hình:** nhóm hoặc người nào chịu trách nhiệm giải thích và phát triển quy tắc.

Một bounded context **không được định nghĩa** bởi tên thư mục, hostname, bảng database, repository Git, container Docker hay số lượng pod Kubernetes. Chúng là cách triển khai có thể giúp bảo vệ ranh giới, nhưng không tạo ra ranh giới ngữ nghĩa nếu mô hình vẫn trộn lẫn.

### 2.2. Bounded context không đồng nghĩa subdomain

**Subdomain** là một phần của không gian vấn đề kinh doanh: ví dụ quản lý danh mục, quản lý tồn kho, vận hành thanh toán. Nó trả lời: tổ chức cần giải quyết loại vấn đề gì?

**Bounded context** là ranh giới áp dụng một mô hình để giải quyết một phạm vi vấn đề: nó trả lời mô hình nào được dùng, với ngữ nghĩa và hợp đồng nào.

Một subdomain có thể dẫn đến một bounded context, nhiều bounded context, hoặc được mô hình hóa theo cách khác tùy độ phức tạp và nhu cầu. Ngược lại, một bounded context có thể hỗ trợ nhiều hoạt động liên quan của một subdomain khi chúng chia sẻ ngôn ngữ và mô hình đủ nhất quán.

Không nên coi danh sách phòng ban hoặc menu chức năng là sơ đồ bounded context hoàn chỉnh.

### 2.3. Bounded context không đồng nghĩa aggregate

**Aggregate** là ranh giới nhất quán và truy cập dữ liệu bên trong một domain model, thường tập trung quanh aggregate root. Ví dụ trong Ordering có thể có Order aggregate bảo vệ quy tắc chuyển trạng thái đơn hàng.

Một bounded context thường chứa nhiều aggregate, service và value object. Quy tắc “mỗi aggregate thành một microservice” thường tạo các dịch vụ quá nhỏ, làm các luồng nghiệp vụ trở thành chuỗi request mạng và transaction phân tán.

### 2.4. Bounded context không đồng nghĩa một nhóm phát triển

Ranh giới mô hình thường cần ownership rõ ràng; một nhóm có thể sở hữu một hoặc vài context. Nhưng số context không bắt buộc bằng số team. Cấu trúc tổ chức giúp vận hành ranh giới, không thay thế việc tìm hiểu nghiệp vụ.

## 3. Đơn vị triển khai dịch vụ là gì?

Một **đơn vị triển khai** là phần mềm có vòng đời phát hành và vận hành xác định: xây dựng artifact, cấu hình, release, rollback, restart, scale và theo dõi.

Trong Microservices, mỗi dịch vụ thường có khả năng triển khai độc lập tương đối và có trách nhiệm nghiệp vụ rõ. Ví dụ:
- ordering-service được build thành một container image.
- Có pipeline CI/CD và lịch phát hành riêng.
- Có cấu hình, health check, metrics, logs và cảnh báo riêng.
- Có chính sách scale, rollback và giới hạn tài nguyên riêng.
- Cung cấp API hoặc event contract để các dịch vụ khác tương tác.

Một đơn vị triển khai có thể là JAR Spring Boot, container image, serverless function, worker hoặc bộ tiến trình có bản phát hành được điều phối. Khi thảo luận phải nói rõ **đơn vị nào được phát hành độc lập**.

### 3.1. Một deployment không phải một runtime instance

Giả sử một Spring Boot service chạy thành 5 pod:

~~~text
               Load Balancer
                    |
            +-------+-------+
            |       |       |
          Pod 1   Pod 2   Pod 3
          Pod 4   Pod 5
           Cùng image, cùng service identity
~~~

Năm pod là năm instance, không phải năm bounded context. Việc scale nhiều replica cùng một artifact cũng không tạo thêm năm microservice khác nhau.

Tương tự, một Kubernetes Deployment hoặc một executable là công cụ vận hành; nó không tự cho biết giới hạn nghiệp vụ của mô hình bên trong.

### 3.2. Triển khai độc lập có nghĩa gì?

Một dịch vụ được coi là có khả năng triển khai độc lập khi thay đổi của nó không thường xuyên buộc các đơn vị khác phát hành đồng thời để giữ hệ thống hoạt động đúng. Để đạt điều đó cần:
- Hợp đồng API/event tương thích giữa phiên bản cũ và mới.
- Ranh giới và quyền sở hữu dữ liệu đủ độc lập.
- Quy trình database migration an toàn, ví dụ expand/contract khi thay schema.
- Observability, rollback và xử lý lỗi khi đối tác chậm hoặc không khả dụng.
- Tránh chia sẻ mô hình domain nội bộ thành thư viện bắt mọi service cập nhật đồng loạt.

Chia một chương trình thành ba JAR nhưng luôn deploy cả ba cùng lúc **chưa chắc** mang lại lợi ích độc lập của Microservices.

## 4. So sánh trực tiếp hai khái niệm

| Câu hỏi | Bounded context | Đơn vị triển khai dịch vụ |
| --- | --- | --- |
| Thuộc lớp nào? | Thiết kế miền, mô hình và ngữ nghĩa | Runtime, đóng gói và vận hành |
| Mục đích chính | Tránh xung đột ý nghĩa; bảo vệ quy tắc miền | Phát hành, scale, cô lập và quản lý vòng đời |
| Ranh giới được phát hiện bằng | Khác biệt từ vựng, trách nhiệm, quy tắc, invariant và tương tác | Nhu cầu release, tải, độ sẵn sàng, team, hạ tầng và chi phí |
| Ví dụ về thành phần | Catalog, Ordering, Inventory với mô hình riêng | catalog-api.jar, ordering-worker image, payment-service |
| Cần mạng để tương tác không? | Không: context có thể ở cùng process | Có nếu các deploy nói chuyện với nhau qua mạng; nội bộ deploy không cần |
| Một bên đổi thì bên kia bắt buộc đổi? | Không | Không |
| Có bắt buộc sở hữu DB độc lập? | Cần sở hữu logic và dữ liệu được quy định rõ; không nhất thiết DB vật lý riêng | Có thể chọn database riêng để tự chủ; chi tiết tùy kiến trúc |
| Bao nhiêu là “đúng”? | Số lượng được tìm ra từ mô hình miền | Số lượng được chọn từ nhu cầu vận hành |
| Sai lầm điển hình | Dùng một domain model chung cho mọi nghĩa | Tách rất nhiều service nhưng phải deploy đồng loạt |

Hai ranh giới tạo thành **hai trục thiết kế tương đối độc lập**. Căn chỉnh chúng giúp giảm coupling; ép chúng trùng nhau bất kể bối cảnh có thể tạo ra hệ thống tốn kém.

## 5. Các cách ánh xạ bounded context vào đơn vị triển khai

### 5.1. Một bounded context → một dịch vụ độc lập

Đây là mô hình thường được đề xuất khi ranh giới miền rõ, nhóm sở hữu đủ năng lực, dữ liệu có thể quản lý độc lập và các bên cần vòng đời phát hành khác nhau.

~~~text
[Catalog BC]  ----> [catalog-service]
[Ordering BC] ----> [ordering-service]
[Inventory BC]----> [inventory-service]
~~~

**Thuận lợi:**
- Dễ gắn một model owner với một service owner.
- Quy tắc và dữ liệu của một miền ít bị can thiệp trực tiếp từ nơi khác.
- Có thể version, deploy, scale và quan sát theo từng năng lực.
- Dễ phân tích điều gì thuộc về ai khi xảy ra sự cố.

**Chi phí và giới hạn:**
- Tương tác xuyên context thường là tương tác mạng.
- Giao dịch liên miền cần thiết kế nhất quán, idempotency và xử lý lỗi từng phần.
- Tăng số pipeline, cấu hình, cảnh báo và hạ tầng.
- Có nguy cơ tách quá sớm khi hiểu biết về mô hình còn đang thay đổi.

**Kết luận cho trường hợp này:** ánh xạ 1:1 là một lựa chọn thuận tiện nếu điều kiện phù hợp, **không phải điều kiện để một context được công nhận là bounded context**.

### 5.2. Nhiều bounded context → một đơn vị triển khai

Một ứng dụng modular monolith có thể chứa nhiều context với package/module và API rõ ràng:

~~~text
                    One deployable
+----------------------------------------------------+
| shop-application.jar                               |
|                                                    |
| +----------------+ +----------------+             |
| | Catalog BC     | | Pricing BC     |             |
| | own model      | | own model      |             |
| +----------------+ +----------------+             |
|                                                    |
| +----------------+ +----------------+             |
| | Ordering BC    | | Inventory BC   |             |
| | own model      | | own model      |             |
| +----------------+ +----------------+             |
+----------------------------------------------------+
                     Một pipeline
~~~

Điều kiện để cách này có giá trị:
- Các context không dùng chung bừa bãi entity và bảng dữ liệu.
- Module có API công khai rõ; các module khác không truy cập trực tiếp repository nội bộ.
- Có kiểm thử bảo vệ ranh giới phụ thuộc.
- Có ownership cho quy tắc và dữ liệu dù cùng repository.
- Các context có nhịp release tương tự nên một deployment chưa gây cản trở lớn.

**Ưu điểm:** giao tiếp nội bộ nhanh; giao dịch cục bộ có thể đơn giản hơn khi phạm vi nghiệp vụ cho phép; chi phí vận hành thấp; dễ refactor ranh giới khi sản phẩm còn biến động.

**Nhược điểm:** release, resource envelope và mức cô lập lỗi bị chia sẻ. Nếu một context cần phát hành hàng giờ hoặc chịu tải rất khác, phải cân nhắc tách deploy.

**Quan trọng:** gom nhiều context vào một deployment không có nghĩa gộp chúng thành một mô hình duy nhất. Chúng vẫn là các bounded context khác nhau nếu có ngôn ngữ và luật riêng được bảo vệ thực tế.

### 5.3. Một bounded context → nhiều thành phần triển khai

Đôi khi một mô hình nghiệp vụ cần nhiều quá trình chạy hoặc chu kỳ mở rộng khác nhau:

~~~text
                     Ordering BC
               Một mô hình và một owner
                          |
        +-----------------+-------------------+
        |                 |                   |
  ordering-api      order-worker        order-projector
  tiếp nhận lệnh    xử lý tác vụ nền     cập nhật read model
  Deploy A          Deploy B            Deploy C
~~~

Ba thành phần có thể phục vụ **cùng bounded context Ordering** nhưng khác nhu cầu tài nguyên, độ trễ hoặc cách kích hoạt công việc. Chúng cần thỏa thuận rõ về ownership của domain rule, trạng thái và sơ đồ dữ liệu.

Có hai trường hợp cần phân biệt:

1. **Nhiều replica/thành phần của một dịch vụ logic:** ví dụ API và worker cùng dùng một mô hình do một đội sở hữu, có thể được phát hành điều phối. Đây không đương nhiên là nhiều microservice độc lập.
2. **Nhiều microservice thực sự trong một context:** có thể tách đơn vị deploy vì tải hoặc công nghệ, nhưng vẫn cần tránh tách một bất biến phải giao dịch nguyên tử qua ranh giới mạng khi không cần thiết. Cách chia đó phải được biện minh bằng nhu cầu vận hành và hợp đồng rõ ràng.

Nếu các nhóm bắt đầu có ngôn ngữ, quy tắc và dữ liệu độc lập thật sự, đó có thể là tín hiệu mô hình cần được nhận diện thành nhiều bounded context mới. Không mặc định điều này chỉ từ số container.

### 5.4. Ánh xạ nhiều-nhiều và thay đổi theo thời gian

Trong một hệ thống lớn, mapping có thể thay đổi qua từng giai đoạn: ban đầu nhiều context trong một monolith, sau đó tách một context có yêu cầu scale đặc thù, trong khi context khác vẫn chung deployment. Một context có thể có nhiều worker hoặc projector nhưng không cần phát triển thành hàng chục microservice nghiệp vụ.

Sơ đồ ranh giới nghiệp vụ vì vậy nên được duy trì **riêng** với sơ đồ runtime/deployment. Khi chuyển cách triển khai, không được ngầm đổi semantic contract.

## 6. Ví dụ xuyên suốt: nền tảng thương mại điện tử

Giả sử doanh nghiệp có các nhu cầu:
- Tạo và xuất bản danh mục sản phẩm.
- Tính giá theo chính sách khuyến mại và vùng bán.
- Nhận và xác nhận đơn hàng.
- Giữ tồn kho, điều chỉnh số lượng khả dụng.
- Thu tiền, hoàn tiền và đối soát.
- Xếp kiện và theo dõi vận chuyển.

### 6.1. Tách ngữ nghĩa trước

| Context | Khái niệm nổi bật | Quy tắc sở hữu | Không nên nhầm với |
| --- | --- | --- | --- |
| Catalog | Product, Category, Publication | Điều kiện sản phẩm được hiển thị | SKU tồn kho |
| Pricing | PriceQuote, DiscountPolicy | Tính báo giá theo chính sách | Giá đã chốt của dòng đơn |
| Ordering | Order, OrderLine, OrderStatus | Quy tắc đặt/chuyển trạng thái đơn | Đơn giao hàng |
| Inventory | StockItem, Reservation | Không giữ quá số tồn khả dụng | Product description |
| Payments | PaymentAttempt, Settlement, Refund | Trạng thái thu tiền và hoàn tiền | Trạng thái đơn mua hàng |
| Shipping | Shipment, Parcel, TrackingEvent | Quy trình giao và theo dõi | Trạng thái thanh toán |

Tên trong bảng là **một mô hình minh họa**, không phải mẫu bắt buộc của mọi tổ chức. Cần xác minh qua nghiệp vụ thật, event storming, phản hồi từ domain expert và lịch sử thay đổi.

Chẳng hạn Catalog có Product với trường title, description, categories. Ordering có OrderLine với productId, displayNameSnapshot và agreedPrice. Chúng cùng tham chiếu một hàng hóa ngoài đời nhưng phục vụ những sự thật nghiệp vụ khác nhau.

**Vì sao snapshot giá ở Ordering?** Nếu Catalog hoặc Pricing cập nhật giá sau khi khách đặt hàng, OrderLine không được lặng lẽ thay giá đã cam kết. Ordering cần lưu giá và quy tắc áp dụng tại thời điểm chốt.

### 6.2. Tương tác giữa các context

Một luồng đặt hàng có thể diễn ra:

~~~text
Khách hàng
    |
    v
Ordering  --(yêu cầu báo giá)------> Pricing
    |                                  |
    |<--- PriceQuote (hợp đồng rõ)------+
    |
    +----(reserve SKU, quantity)-----> Inventory
    |<--- reservation result ----------+
    |
    +---- OrderPlaced event ----------> Payments / Shipping
    |
    +---- trạng thái đơn có thẩm quyền
~~~

Đây là sơ đồ nghiệp vụ ở mức khái niệm. Khi triển khai trong một monolith, các lời gọi có thể là lời gọi API nội bộ hoặc service method. Khi triển khai Microservices, chúng có thể là HTTP/gRPC và message. **Ranh giới context vẫn có ý nghĩa** trong cả hai trường hợp.

Không nên dùng một object entity chung chuyển thẳng giữa Ordering và Payments; nên xác định public contract phản ánh thông tin tối thiểu mỗi bên cần.

### 6.3. Hai phương án triển khai cùng một mô hình

**Phương án A — modular monolith**

~~~text
commerce-app.jar
  catalog/
  pricing/
  ordering/
  inventory/
  payments/
  shipping/
~~~

Tất cả chạy một ứng dụng; vẫn có code ownership theo context và giao tiếp qua interface/event nội bộ. Phù hợp nếu team nhỏ, thay đổi liên miền thường xuyên và một pipeline vẫn đáp ứng nhịp giao hàng.

**Phương án B — tách một số dịch vụ**

~~~text
catalog-app.jar    → Catalog BC
commerce-app.jar   → Pricing + Ordering BC
stock-app.jar      → Inventory BC
payment-app.jar    → Payments BC
shipping-worker    → Shipping BC
~~~

Ví dụ này cho thấy có thể tách Inventory và Payments do yêu cầu scale, bảo mật, tích hợp hoặc release riêng, trong khi Pricing và Ordering vẫn cùng một deploy. Dù gộp deploy, hai context bên trong commerce-app vẫn phải giữ semantic boundary.

Không thể kết luận phương án B tốt hơn A chỉ vì có nhiều executable.

## 7. Context map: Ranh giới ngữ nghĩa được kết nối ra sao?

Một **context map** mô tả quan hệ giữa các bounded context và cách dịch ngôn ngữ/mô hình khi chúng tương tác. Nó khác với sơ đồ topology hạ tầng.

Ví dụ:

~~~text
[Catalog Context] --Published Product Contract--> [Ordering Context]
[Pricing Context] --Quote API-------------------> [Ordering Context]
[Ordering Context] --OrderConfirmed Event-------> [Shipping Context]
[External PSP] ----Anti-Corruption Adapter------> [Payments Context]
~~~

Mỗi mũi tên thể hiện quan hệ giữa **mô hình và hợp đồng**. Về triển khai, hai đầu mũi tên có thể ở cùng process hoặc ở hai dịch vụ khác nhau.

Một số mẫu quan hệ DDD cần nhận biết:

- **Upstream / Downstream:** context upstream công bố thông tin hoặc hành vi mà downstream sử dụng. Trách nhiệm tương thích và mức độ ảnh hưởng cần được thỏa thuận.
- **Published Language:** sử dụng schema công khai được thống nhất để trao đổi, thường là DTO hoặc event contract có version.
- **Open Host Service:** upstream cung cấp giao diện tương đối ổn định cho nhiều consumer thay vì kết nối tùy biến riêng lẻ.
- **Anti-Corruption Layer (ACL):** downstream chuyển đổi mô hình bên ngoài sang mô hình nội bộ, tránh cho từ ngữ và cấu trúc của hệ thống khác xâm nhập domain model.
- **Conformist:** downstream chấp nhận model của upstream khi không thể hoặc không cần chủ động chuyển đổi, hiểu rõ coupling đi kèm.
- **Shared Kernel:** hai context chia sẻ một phần mô hình được đồng thuận và đồng sở hữu; cần rất thận trọng vì dễ tạo phụ thuộc thay đổi.

Không cần dùng mọi pattern trong một hệ thống. Điều quan trọng là **giao tiếp xuyên context phải có ý nghĩa nghiệp vụ được định nghĩa rõ**, ngay cả khi chỉ là một lời gọi method trong cùng ứng dụng.

## 8. Vì sao không nên chọn service boundary chỉ từ sơ đồ bounded context?

Có ít nhất năm lý do.

### 8.1. Semantic boundary không tự tạo nhu cầu deploy độc lập

Catalog và Ordering có mô hình khác nhau, nhưng nếu cùng một nhóm phát triển, phát hành đồng thời, cùng mục tiêu SLA và cùng tải vừa phải thì tách service có thể chỉ phát sinh thêm networking, observability và dữ liệu phân tán.

DDD giúp tìm ranh giới **đúng về mặt ngữ nghĩa**. Quyết định Microservices còn cần chứng minh lợi ích vận hành đủ lớn.

### 8.2. Giao dịch và bất biến có thể bị chia cắt

Ví dụ cập nhật trạng thái đơn hàng và giữ tồn cần bảo đảm một số invariant. Nếu split service trước khi làm rõ invariant, có thể buộc luồng nghiệp vụ chuyển sang saga, outbox, retry, idempotency và compensation.

Giữ hai context trong một deploy có thể làm các tương tác kỹ thuật đơn giản hơn, nhưng **không được tự động coi một transaction cơ sở dữ liệu xuyên context là thiết kế nghiệp vụ tốt**. Cần cân nhắc quyền sở hữu dữ liệu và mức kết dính thực sự. Nếu tách sau này, phải có contract và migration strategy.

### 8.3. Đội ngũ và trách nhiệm còn tập trung

Một số tổ chức có ít kỹ sư. Tách hàng chục service khiến mỗi kỹ sư phải lo thêm alert, deploy, schema migrations, bảo mật, vận hành và phân tích distributed traces mà chưa có nhóm đủ năng lực trực.

Có thể tiếp tục modular monolith, duy trì module owner và dùng kiến thức về bounded context để giảm nợ thiết kế.

### 8.4. Khác biệt tải có thể xuất hiện bên trong một context

Trong Ordering, API xác nhận đơn có thể nhạy với latency, còn worker xuất báo cáo hoạt động nền tốn CPU. Nếu hai workload xung đột tài nguyên, đội ngũ có thể tách worker thành deployment riêng **dù vẫn thuộc Ordering context**.

Như vậy **workload boundary** và **model boundary** không bắt buộc trùng nhau.

### 8.5. Ranh giới mô hình có thể đang biến động

Trong giai đoạn khám phá sản phẩm, thuật ngữ và business invariant còn thay đổi. Tách thành nhiều service sớm có thể đóng cứng một phân chia chưa ổn định thành API và dữ liệu khó thay đổi.

Có thể làm rõ bounded context ở mức code và giao tiếp nội bộ trước khi trả chi phí phân tán.

## 9. Tìm ranh giới bounded context theo nghiệp vụ

Trước khi bàn cần bao nhiêu service, hãy lập bản đồ miền.

### Bước 1 — Thu thập ngôn ngữ và quy trình

Phỏng vấn domain expert, phân tích use case, quy trình và các sự kiện nghiệp vụ. Chú ý từ nào có nghĩa khác nhau giữa những nhóm người.

Ví dụ từ “đơn hàng hoàn tất” có thể nghĩa là đã chốt đơn trong Ordering, đã trả tiền trong Payments hoặc đã giao tới khách trong Shipping. Nếu buộc một trạng thái DONE chung, hệ thống dễ xuất hiện logic phụ thuộc và mơ hồ.

### Bước 2 — Liệt kê quy tắc và người có thẩm quyền quyết định

Với mỗi quy tắc, hỏi:
- Ai chịu trách nhiệm thay đổi quy tắc này?
- Dữ liệu nào được dùng để quyết định?
- Điều gì phải đúng đồng thời trong một transaction?
- Ngữ nghĩa trạng thái nào được chấp nhận?
- Nếu context khác cần dữ liệu, nó đang cần sự thật nào: trạng thái mới nhất, snapshot đã chốt hay một event?

Ví dụ Pricing quyết định giá chào bán, Ordering chịu trách nhiệm giữ **agreed price** trên đơn. Chúng trao đổi PriceQuote, nhưng không nên dùng chung một MutablePrice entity.

### Bước 3 — Nhóm các quy tắc thành mô hình nhất quán

Tập hợp những hành vi chia sẻ thuật ngữ, vòng đời, invariant và ownership. Đánh dấu nơi xuất hiện xung đột ngôn ngữ hoặc các quy tắc không còn phù hợp với cùng một model.

Không suy ra rằng một trang UI, một API endpoint, một database table hay một aggregate bằng một bounded context.

### Bước 4 — Vẽ context map

Chỉ rõ context nào phụ thuộc context nào; phía nào phát hành contract; dữ liệu nào là snapshot, reference hay bản sao; ai xử lý phiên bản và lỗi tích hợp.

### Bước 5 — Kiểm chứng bằng thay đổi thực tế

Quan sát commit, yêu cầu và luồng làm việc:
- Hai phần có thường phải thay đổi cùng lúc do cùng quy tắc không?
- Một thuật ngữ có bị hiểu sai hoặc kéo vào không đúng model không?
- Một thay đổi của Catalog có làm hỏng invariant của Ordering không?
- Hai nhóm nghiệp vụ có các định nghĩa trạng thái trái nhau không?

Nếu phải đổi cả hai context, điều đó không tự chứng minh ranh giới sai: các context khác nhau vẫn có tích hợp. Cần phân biệt **phụ thuộc hợp đồng hợp lệ** với **rò rỉ mô hình nội bộ**.

## 10. Sau đó mới chọn ranh giới triển khai

Bảng dưới giúp đánh giá có nên biến một context (hoặc nhóm context) thành dịch vụ độc lập.

| Tiêu chí | Giữ chung deployment thường thuận lợi khi | Tách deployment có thể đáng cân nhắc khi |
| --- | --- | --- |
| Nhịp phát hành | Các phần phát hành đồng bộ, ít chặn nhau | Nhóm độc lập thường xuyên chờ release chung |
| Ownership | Cùng nhóm dễ phối hợp và kiểm thử | Có nhóm sở hữu độc lập, hợp đồng ổn định |
| Tải và tài nguyên | Nhu cầu scale tương đối giống nhau | Một workload cần CPU/RAM/IO hoặc scale khác biệt rõ |
| Độ tin cậy | Có thể cô lập tài nguyên trong cùng process ở mức chấp nhận được | Sự cố ở một vùng liên tục làm ảnh hưởng luồng trọng yếu |
| Dữ liệu và giao dịch | Luồng đồng bộ và invariant còn cần phối hợp chặt | Dữ liệu có ownership rõ, chấp nhận mô hình consistency phù hợp |
| Bảo mật | Cùng mức kiểm soát dữ liệu/chính sách | Cần ranh giới quyền hoặc hạ tầng đặc thù |
| Công nghệ | Một stack giải quyết tốt mọi workload | Có yêu cầu công nghệ vận hành khác thực sự |
| Chi phí | Pipeline và giám sát đơn giản đem lại lợi ích lớn | Lợi ích tự chủ/scale vượt overhead network, vận hành, CI/CD |

Một quyết định kiến trúc tốt cần **bằng chứng đo được**: lead time, release coupling, change failure rate, p95/p99 latency, tải CPU/RAM, DB contention, chi phí cloud, sự cố và thời gian khôi phục.

Không có ngưỡng phổ quát như “đủ 10 endpoint” hoặc “đủ 5 bảng thì tách service”.

## 11. Thiết kế modular monolith để bảo vệ bounded context

Trong Java/Spring Boot, có thể bắt đầu bằng các package theo context và kiểm soát dependency.

~~~text
src/main/java/com/example/commerce/
  catalog/
    api/
    application/
    domain/
    infrastructure/
  pricing/
    api/
    application/
    domain/
    infrastructure/
  ordering/
    api/
    application/
    domain/
    infrastructure/
  inventory/
    api/
    application/
    domain/
    infrastructure/
  boot/
    CommerceApplication.java
~~~

Trong cấu trúc này:
- Phần domain của Catalog không nên import entity/repository nội bộ của Ordering.
- Ordering chỉ sử dụng API hoặc sự kiện công khai mà Catalog/Pricing cung cấp.
- Các DTO dùng để tích hợp có thể khác hẳn entity domain.
- Dữ liệu do một context sở hữu cần được chỉ rõ ngay cả khi dùng chung database server.
- Những luật nghiệp vụ quan trọng phải có test ở context sở hữu.

Ví dụ public contract giữa Pricing và Ordering:

~~~java
// Contract công khai của Pricing context.
// Đây là DTO trao đổi, không phải entity persistence nội bộ.
public record PriceQuote(
        String productId,
        String currency,
        long amountMinor,
        String quoteId) {}

// Port được Ordering sử dụng.
public interface PriceQuotation {
    PriceQuote quoteFor(String productId, String customerId);
}

// Ordering chuyển kết quả báo giá thành snapshot của mình.
public record OrderLine(
        String productId,
        int quantity,
        long agreedUnitPriceMinor,
        String currency) {}

public final class OrderPlacement {
    private final PriceQuotation quotation;

    public OrderPlacement(PriceQuotation quotation) {
        this.quotation = quotation;
    }

    public OrderLine prepareLine(
            String productId, String customerId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        PriceQuote quote =
                quotation.quoteFor(productId, customerId);

        return new OrderLine(
                productId,
                quantity,
                quote.amountMinor(),
                quote.currency());
    }
}
~~~

Đây là ví dụ **về biên giới mô hình và phép chuyển dữ liệu**. Hệ thống thực còn phải thiết kế hạn hiệu lực quote, xác thực currency, tính tiền an toàn, transaction, idempotency, đồng thời và các trường hợp giá thay đổi. Không nên kết luận rằng một DTO hay interface tự động bảo đảm đúng toàn bộ quy tắc đặt hàng.

### 11.1. Khi còn cùng database

Có thể dùng một DB instance cho nhiều context nhưng quy định quyền sở hữu logic:

~~~text
Database server
  catalog_schema.products      ← Catalog sở hữu
  pricing_schema.price_rules   ← Pricing sở hữu
  ordering_schema.orders       ← Ordering sở hữu
  inventory_schema.stock       ← Inventory sở hữu
~~~

Các schema chỉ minh họa cách biểu diễn ownership. Một database instance không có nghĩa mọi module được đọc/ghi tùy ý bảng của nhau. Có thể dùng schema riêng, account quyền hạn hoặc kiểm thử kiến trúc để kiểm soát đường truy cập.

Lúc tách deployment, việc một service trực tiếp truy vấn bảng do service khác sở hữu sẽ cản trở phát hành độc lập. Vì vậy, **quyền sở hữu dữ liệu nên được làm rõ trước khi tách vật lý**.

### 11.2. Bảo vệ ranh giới bằng kiểm thử kiến trúc

Có thể dùng ArchUnit hoặc các cơ chế kiểm tra dependency để ngăn package ordering.domain phụ thuộc catalog.infrastructure; dùng integration test kiểm tra public contract và bất biến của từng context.

Những công cụ này chỉ giúp thực thi quy tắc đã thống nhất; chúng không tự quyết định domain boundary cho đội ngũ.

## 12. Chuyển từ một deployment sang nhiều deployment

Giả sử lúc đầu Catalog và Ordering cùng một Spring Boot application. Về sau Catalog phải phát hành thường xuyên, có tải đọc tăng lớn và nhóm độc lập vận hành.

Có thể tiến hành theo chuỗi:

### Giai đoạn A — Làm sạch ranh giới ngữ nghĩa

- Xác định Catalog sở hữu ProductPublication, Ordering sở hữu Order và snapshot của sản phẩm đã đặt.
- Dùng public contract để Ordering lấy dữ liệu Catalog.
- Loại bỏ truy cập trực tiếp vào entity và bảng nội bộ không được phép.
- Làm rõ hành vi khi Catalog không trả lời, khi dữ liệu cũ và khi sản phẩm bị ngừng bán.

### Giai đoạn B — Thay kết nối nội bộ bằng adapter có thể tách

Ban đầu:
~~~text
Ordering module → Catalog Java interface → Catalog module
~~~

Sau khi tách:
~~~text
Ordering service → Catalog client adapter → Catalog HTTP/gRPC API
~~~

Ordering vẫn dùng cùng **ý nghĩa nghiệp vụ** của hợp đồng. Phần transport và xử lý lỗi thay đổi, nhưng domain model của Ordering không nên bị ép thành entity của Catalog.

### Giai đoạn C — Tách dữ liệu và quyền ghi

- Xác định catalog data owner duy nhất trong quá trình migration.
- Có kế hoạch chuyển dữ liệu, đồng bộ tạm thời hoặc chuyển quyền đọc/ghi có kiểm soát.
- Tránh dual-write không có cơ chế nhất quán; nếu có phát event, cân nhắc transactional outbox và idempotent consumer.
- Thiết kế versioning, cache invalidation và fallback cho người dùng.
- Xác minh phiên bản mới/cũ của hợp đồng còn tương thích trong giai đoạn chuyển tiếp.

### Giai đoạn D — Triển khai độc lập và đo lợi ích

Catalog có pipeline, config, giám sát, rollback và scale riêng; Ordering không phải deploy cùng lúc cho mỗi lần sửa Catalog. Đo release lead time, lỗi liên dịch vụ, p95/p99 và chi phí vận hành.

**Chỉ tách deploy khi động lực này đủ rõ**. Không phải mọi bounded context trong monolith đều cần đi qua các giai đoạn trên.

## 13. Bẫy thiết kế thường gặp

### Bẫy 1 — “Một bounded context bắt buộc bằng một microservice”

Không chính xác. Boundaries miền và boundaries vận hành không phải cùng một loại. Một context có thể nằm trong modular monolith; một context cũng có thể cần nhiều loại process phục vụ cùng mô hình.

### Bẫy 2 — “Mỗi bảng dữ liệu thành một service”

Bảng là cấu trúc lưu trữ, không nói đủ về bất biến và ngôn ngữ nghiệp vụ. Tách một bảng thành service có thể khiến luồng nghiệp vụ cần gọi mạng liên tục và mất transaction cục bộ.

### Bẫy 3 — “Một REST controller là một bounded context”

Controller phản ánh giao diện kỹ thuật và cách tổ chức API; một controller có thể cung cấp nhiều use case, còn một context có thể có nhiều controller, message handler và worker. Ranh giới nghiệp vụ không hình thành từ việc đếm endpoint.

### Bẫy 4 — “Tách service rồi sẽ tự có boundary đúng”

Nếu mọi service dùng chung một domain model package, một database schema và phải deploy đồng loạt, đó là coupling phân tán. Network boundary có thể làm lỗi và chi phí tăng lên mà không cải thiện tính tự chủ.

### Bẫy 5 — “Các context có cùng tên entity thì phải dùng cùng class”

Trong Catalog, Product là đối tượng xuất bản; trong Ordering, một dòng đơn cần snapshot tên và giá đã chốt; trong Inventory, SKU là đối tượng quản lý tồn. Chia sẻ tên không đồng nghĩa chia sẻ mô hình hoặc vòng đời.

### Bẫy 6 — “Bị tách deployment thì context cũng phải tách”

Tách worker vì tải CPU không nhất thiết thay đổi ngữ nghĩa Ordering. Ngược lại, hai nhóm đã có ngôn ngữ và quy tắc nghiệp vụ khác nhau vẫn có thể là hai context dù deploy cùng một ứng dụng.

### Bẫy 7 — “Dùng chung database đồng nghĩa một bounded context”

Một DB có thể chứa nhiều context với ownership logic. Nhưng dùng chung DB dễ làm rò rỉ quyền truy cập; cần có quy tắc và đường chuyển đổi rõ nếu mục tiêu là độc lập hóa deployment.

### Bẫy 8 — “Số service càng lớn thì kiến trúc càng trưởng thành”

Độ trưởng thành thể hiện ở tính đúng của mô hình, mức tự chủ có ích, khả năng phát hành và vận hành đáp ứng mục tiêu. Thêm service không phải thành tích nếu chưa giải quyết vấn đề đo được.

## 14. Bài tập nhận diện và ra quyết định

### Bài tập 1 — Một monolith, ba ngôn ngữ

Một ứng dụng Spring Boot duy nhất có ba module:
- Catalog gọi “Product” là thông tin xuất bản.
- Ordering gọi “OrderLine” là giá và hàng hóa đã chốt.
- Inventory gọi “StockItem” là SKU và tồn khả dụng.

Cả ba có API nội bộ và model riêng, nhưng deploy bằng một JAR.

**Câu hỏi:** Có bao nhiêu bounded context và bao nhiêu đơn vị triển khai?

**Gợi ý trả lời:** Theo cách mô tả, có ba bounded context được chủ đích thiết kế và một đơn vị triển khai. Việc xác nhận context trên hệ thống thật còn phụ thuộc ranh giới quy tắc, ngôn ngữ và ownership, không chỉ tên package.

### Bài tập 2 — Một context, nhiều worker

Ordering có một API tiếp nhận đặt hàng và ba worker xử lý hàng đợi, đều cùng model và owner. Các worker scale độc lập.

**Câu hỏi:** Có buộc phải có bốn bounded context không?

**Gợi ý trả lời:** Không. Số tiến trình là lựa chọn vận hành. Hãy xem các thành phần có mô hình/ngôn ngữ/quy tắc độc lập hay chỉ là những executor khác nhau trong cùng Ordering context.

### Bài tập 3 — Các service vẫn deploy đồng loạt

Bốn service riêng chia sẻ chung thư viện JPA entity và cùng sửa bảng orders. Mỗi lần đổi trạng thái đơn đều phải sửa và deploy cả bốn.

**Câu hỏi:** Kiến trúc này đã có độc lập triển khai chưa? Đâu là bước cải thiện phù hợp?

**Gợi ý trả lời:** Tính độc lập còn yếu; cần làm rõ ownership nghiệp vụ, data owner, public contract, versioning và phép chuyển đổi model. Tránh đặt mục tiêu tạo thêm service trước khi giải quyết coupling.

### Bài tập 4 — Quyết định tách Inventory

Inventory xử lý cập nhật tồn kho với mức tải rất cao, có team vận hành riêng, cần scale khác Ordering. Luồng checkout phụ thuộc kết quả giữ tồn.

**Câu hỏi:** Những điều kiện nào phải có trước khi tách Inventory thành deploy độc lập?

**Gợi ý trả lời:** Bounded context Inventory phải có invariant và quyền ghi rõ; cần giao thức reserve/release, transaction boundary, timeout/retry/idempotency, observability, SLA của checkout, khả năng rollback và kế hoạch migration. Lợi ích scale/ownership cần được đo để so với chi phí phân tán.

## 15. Mẫu ghi lại quyết định kiến trúc

Khi thống nhất mapping giữa context và deployment, nên ghi một Architecture Decision Record (ADR) ngắn:

~~~text
Decision: Giữ Catalog và Pricing là hai bounded context
          trong cùng một commerce application.
Business semantics:
  Catalog  → xuất bản và mô tả sản phẩm
  Pricing  → chính sách và phiên bản báo giá
Ownership:
  Mỗi context có mô hình và hợp đồng công khai riêng.
Deployment:
  Một JAR, một CI/CD pipeline, scale cùng ứng dụng.
Rationale:
  Cùng nhóm vận hành; release chung chưa làm chậm nghiệp vụ;
  chi phí phân tán chưa mang lại lợi ích tương xứng.
Guardrails:
  Không chia sẻ entity domain/repository; tránh đọc trực tiếp
  dữ liệu nội bộ; có contract test và architecture test.
Revisit when:
  Lead time do release coupling tăng đáng kể, hoặc một context
  có nhu cầu scale/safety/reliability riêng vượt mức chấp nhận.
~~~

Một ADR khác có thể chọn triển khai 1:1 nếu có đủ căn cứ. Giá trị của ADR là làm rõ **vì sao các ranh giới được ánh xạ như vậy**, những giới hạn được chấp nhận và điều kiện thay đổi sau này.

## 16. Câu hỏi tự kiểm tra khi thiết kế Microservices

Khi nhìn vào một sơ đồ mới, hãy tự hỏi:

- [ ] Từng bounded context có ngôn ngữ và quy tắc nghiệp vụ riêng được mô tả rõ chưa?
- [ ] Có đang nhầm subdomain, aggregate, module, API endpoint hoặc bảng DB với bounded context không?
- [ ] Các hệ thống dùng cùng thuật ngữ có thực sự cùng ý nghĩa và vòng đời dữ liệu không?
- [ ] Context map đã chỉ rõ upstream, downstream, contract và phép chuyển đổi ngữ nghĩa chưa?
- [ ] Sơ đồ deployment được lập riêng với sơ đồ domain chưa?
- [ ] Nếu gom nhiều context cùng deploy, ranh giới model và ownership có còn được bảo vệ không?
- [ ] Nếu tách một context thành nhiều process, đã xác định rõ owner và invariant xuyên process chưa?
- [ ] Service được coi là độc lập có thật sự deploy/rollback mà không phải cập nhật hàng loạt service khác không?
- [ ] Quyết định tách dựa trên dữ liệu về release, tải, độ tin cậy hoặc chi phí vận hành chưa?
- [ ] Có ADR và tiêu chí xét lại khi nghiệp vụ hoặc quy mô thay đổi chưa?

## 17. Kết luận

**Bounded context là ranh giới của ý nghĩa nghiệp vụ**: một mô hình, từ vựng và tập quy tắc có tính nhất quán trong một phạm vi được xác định. **Đơn vị triển khai dịch vụ là ranh giới của phần mềm trong vận hành**: nơi đóng gói, phát hành, scale, quan sát và khôi phục.

Chúng có thể ánh xạ **một-một, nhiều-một hoặc một-nhiều** tùy năng lực nghiệp vụ, nhu cầu đội ngũ và đặc tính tải. Việc tìm bounded context thường nên đi trước quyết định cắt deployment: thiết kế đúng mô hình, bảo vệ API và ownership, sau đó chọn mức phân tán mang lại lợi ích thực. Trong một hệ thống Microservices tốt, service boundary hỗ trợ domain boundary; nó không thay thế quá trình khám phá miền.
