# Một Bounded Context có thể tồn tại trong ứng dụng nguyên khối

Trong Domain-Driven Design (DDD), **Bounded Context** là ranh giới mà bên trong đó một mô hình miền và ngôn ngữ chung có ý nghĩa nhất quán. Ranh giới này xác định khái niệm nào được dùng, quy tắc nào áp dụng và nhóm nào chịu trách nhiệm duy trì mô hình. Nó không bắt buộc phải trùng với ranh giới tiến trình, máy chủ hay đơn vị triển khai.

Vì vậy, một hệ thống có thể chứa nhiều Bounded Context trong cùng một ứng dụng nguyên khối (monolith). Mỗi context vẫn có mô hình, thuật ngữ, hành vi, quyền sở hữu dữ liệu và giao diện tích hợp riêng. Ứng dụng chỉ được đóng gói và triển khai như một đơn vị. Cách tổ chức này thường được gọi là **Modular Monolith** khi các module được tách ranh giới rõ ràng.

Điểm quan trọng là tách biệt hai quyết định: chia hệ thống theo mô hình nghiệp vụ và chia hệ thống thành các tiến trình triển khai. DDD giúp xác định ranh giới mô hình; kiến trúc triển khai quyết định các ranh giới runtime phù hợp với nhu cầu vận hành.

## 1. Bounded Context là ranh giới mô hình, không phải ranh giới máy chủ

Bounded Context trả lời câu hỏi: “Mô hình và ngôn ngữ nào có hiệu lực trong phạm vi này?” Nó không tự trả lời câu hỏi: “Phạm vi này chạy trên máy chủ nào?”

Ví dụ, từ Customer có thể mang ý nghĩa khác nhau:

- Trong Customer Management, Customer là hồ sơ khách hàng, thông tin liên hệ và trạng thái hồ sơ.
- Trong Sales, Customer có thể là bên mua gắn với báo giá hoặc đơn hàng.
- Trong Support, Customer có thể là chủ thể của yêu cầu hỗ trợ và lịch sử trao đổi.

Các context có thể cùng nằm trong một JVM, nhưng không nhất thiết phải chia sẻ một class Customer duy nhất. Mỗi context duy trì mô hình phù hợp với trách nhiệm của mình.

Một Bounded Context thường xác định:

- Ngôn ngữ chung và ý nghĩa của các thuật ngữ.
- Mô hình domain và các quy tắc nghiệp vụ.
- Aggregate, Entity, Value Object và Domain Service thuộc phạm vi.
- Quyền sở hữu dữ liệu và vòng đời dữ liệu.
- Hợp đồng công khai để context khác tương tác.
- Nhóm hoặc vai trò chịu trách nhiệm phát triển mô hình.

Ranh giới này tồn tại ở mức tư duy và thiết kế ngay cả khi toàn bộ ứng dụng được biên dịch thành một artifact.

## 2. Phân biệt ba loại ranh giới

Khi thiết kế hệ thống, cần phân biệt ranh giới mô hình, ranh giới module code và ranh giới triển khai.

| Loại ranh giới | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Bounded Context | Mô hình và ngôn ngữ nào có ý nghĩa trong phạm vi này? | Sales, Inventory, Payment |
| Module code | Mã nguồn nào được phép truy cập trực tiếp mã nguồn nào? | Package sales chỉ dùng API công khai của inventory |
| Deployment unit | Thành phần nào được build, phát hành và chạy cùng nhau? | Một ứng dụng Spring Boot duy nhất |

Ba ranh giới có thể trùng nhau, nhưng không bắt buộc. Một Bounded Context có thể gồm nhiều module kỹ thuật; nhiều context có thể được triển khai trong một ứng dụng; hoặc một context có thể được tách thành nhiều tiến trình vì lý do mở rộng và vận hành.

Không nên suy ra số microservice từ số Bounded Context. Nếu có tám context, điều đó không có nghĩa hệ thống phải có tám dịch vụ độc lập.

## 3. Ví dụ: nhiều Bounded Context trong hệ thống thương mại điện tử

Giả sử một cửa hàng trực tuyến cần quản lý khách hàng, đơn hàng, tồn kho, thanh toán và giao hàng. Sau khi phân tích nghiệp vụ, nhóm xác định các context:

| Bounded Context | Trách nhiệm chính | Mô hình tiêu biểu |
| --- | --- | --- |
| Customer Management | Hồ sơ và trạng thái khách hàng | CustomerProfile, ContactInformation |
| Sales | Báo giá, giỏ hàng và đơn hàng | Quote, SalesOrder, OrderLine |
| Inventory | Tồn kho và giữ hàng | StockItem, Reservation, AvailableQuantity |
| Payment | Cấp phép, thu tiền và hoàn tiền | Payment, Authorization, Refund |
| Fulfillment | Lấy hàng, đóng gói và vận chuyển | Shipment, Package, Delivery |

Tất cả có thể chạy trong một ứng dụng:

~~~mermaid
flowchart TB
    UI["Web / Mobile / Admin"] --> APP["Một ứng dụng nguyên khối"]
    subgraph MONO["Một deployment unit"]
        C["Customer Management"]
        S["Sales"]
        I["Inventory"]
        P["Payment"]
        F["Fulfillment"]
        S -->|"API nội bộ / command"| I
        S -->|"API nội bộ / command"| P
        P -->|"event nội bộ"| S
        I -->|"event nội bộ"| S
        S -->|"event nội bộ"| F
        C -->|"contract / query"| S
    end
    APP --> MONO
~~~

Các module có thể được đóng gói trong cùng file JAR và cùng tiến trình Java. Tuy vậy, Sales không nên thay đổi trực tiếp bảng hoặc Aggregate nội bộ của Inventory. Nó gửi yêu cầu qua hợp đồng mà Inventory công bố.

## 4. Một ứng dụng nguyên khối không đồng nghĩa với một mô hình miền duy nhất

Monolith truyền thống thường được tổ chức theo tầng kỹ thuật dùng chung:

~~~text
controllers/
services/
repositories/
entities/
~~~

Cấu trúc này có thể khiến các khái niệm từ nhiều nghiệp vụ bị đặt chung trong một mô hình. Một class Customer hoặc Order dùng chung dễ tích tụ trường và hành vi từ nhiều nơi, trong khi mỗi context có ý nghĩa khác nhau.

Một modular monolith tổ chức mã nguồn theo năng lực hoặc Bounded Context:

~~~text
application/
  customer/
    api/
    application/
    domain/
    infrastructure/
  sales/
    api/
    application/
    domain/
    infrastructure/
  inventory/
    api/
    application/
    domain/
    infrastructure/
  payment/
    api/
    application/
    domain/
    infrastructure/
  fulfillment/
    api/
    application/
    domain/
    infrastructure/
~~~

Mỗi context có thể có controller, application service, domain model và persistence adapter riêng. Cấu trúc cụ thể tùy dự án; mục đích là làm cho ranh giới nghiệp vụ nhìn thấy được trong code.

## 5. Mỗi context có mô hình riêng dù dùng chung một ngôn ngữ lập trình

Các module có thể cùng dùng Java, Spring và một số thư viện kỹ thuật, nhưng không vì thế mà phải chia sẻ mô hình nghiệp vụ.

Ví dụ:

~~~java
// Trong Sales context
public record BuyerReference(UUID customerId, String displayName) {}

// Trong Customer Management context
public final class CustomerProfile {
    private CustomerId id;
    private ContactInformation contactInformation;
    private CustomerStatus status;
}
~~~

BuyerReference là dữ kiện mà Sales cần để xử lý giao dịch bán hàng. CustomerProfile là mô hình quản lý hồ sơ thuộc Customer Management. Chúng có thể liên quan đến cùng một khách hàng nhưng có trách nhiệm và vòng đời khác nhau.

Nếu Sales cần tên hiển thị tại thời điểm đặt hàng, nó có thể lưu snapshot phù hợp. Khi hồ sơ khách hàng thay đổi, snapshot của đơn cũ không nhất thiết phải thay đổi theo. Đây là lựa chọn nghiệp vụ của Sales, không phải bản sao toàn bộ Customer Profile.

## 6. Thiết kế module API và phần nội bộ

Mỗi context nên công bố một bề mặt API nhỏ, ổn định và đủ để context khác thực hiện nhu cầu của mình. Các class còn lại nên được xem là chi tiết nội bộ.

Ví dụ cấu trúc:

~~~text
inventory/
  api/
    InventoryReservation.java
    ReserveStock.java
    ReservationResult.java
  application/
    ReserveStockHandler.java
  domain/
    StockItem.java
    Reservation.java
    StockRepository.java
  infrastructure/
    JpaStockRepository.java
~~~

API công khai có thể gồm:

~~~java
public interface InventoryReservation {
    ReservationResult reserve(ReserveStock command);
}

public record ReserveStock(
    UUID orderId,
    List<RequestedItem> items
) {}

public record ReservationResult(
    UUID reservationId,
    ReservationStatus status
) {}
~~~

Sales phụ thuộc vào inventory.api. Nó không cần biết Inventory dùng JPA, có bao nhiêu bảng, Aggregate được đặt tên gì hoặc cách tính tồn kho nội bộ.

Không nên đưa Entity, repository implementation hoặc persistence record vào API công khai. Hợp đồng nên phản ánh hành vi và dữ kiện được phép chia sẻ.

## 7. Ngăn truy cập xuyên module vào chi tiết nội bộ

Ranh giới chỉ có ý nghĩa khi code thực sự tôn trọng nó. Nếu mọi package đều public và mọi module đều có thể import bất kỳ class nào, modular monolith có thể nhanh chóng trở thành một monolith liên kết chặt.

Có thể áp dụng một số quy tắc:

- Chỉ package api hoặc module contract được công khai cho context khác.
- Đặt implementation và domain object nội bộ ở package không public khi phù hợp.
- Dùng Java module system hoặc build module để giới hạn visibility nếu dự án cần ranh giới mạnh.
- Đặt architecture test để phát hiện dependency không hợp lệ.
- Tránh import repository, ORM entity và internal service của context khác.
- Xem mọi API công khai là hợp đồng cần được quản lý tương thích.

Java package-private hữu ích để giới hạn class trong package. Với ranh giới giữa các module lớn, có thể tách Gradle/Maven module hoặc dùng JPMS. Không cần áp dụng mọi cơ chế cùng lúc; chọn mức bảo vệ phù hợp quy mô và rủi ro.

## 8. Tương tác giữa các context trong cùng tiến trình

Khi các context cùng chạy trong một process, chúng có thể tương tác mà không cần HTTP hoặc network broker. Một module có thể gọi interface công khai của module khác hoặc phát sự kiện nội bộ.

Hai kiểu tương tác thường gặp:

**Gọi đồng bộ qua API nội bộ**

Sales gọi InventoryReservation.reserve() và nhận kết quả ngay. Cách này phù hợp khi use case cần biết kết quả để tiếp tục hoặc từ chối thao tác.

**Thông báo bất đồng bộ qua event**

Payment phát PaymentAuthorized; Sales nhận sự kiện và cập nhật tiến trình đơn hàng. Cách này giảm phụ thuộc thời điểm gọi nhưng cần xử lý event trùng, thứ tự và lỗi handler.

Việc cùng process chỉ làm giảm chi phí giao tiếp. Nó không xóa bỏ ranh giới mô hình. Không nên gọi trực tiếp method nội bộ hoặc chia sẻ object mutable xuyên context chỉ vì chúng nằm cùng JVM.

## 9. Gọi API nội bộ khác với gọi microservice

Một interface nội bộ trong modular monolith có thể được gọi trực tiếp bằng Java:

~~~java
public final class PlaceOrderHandler {
    private final InventoryReservation inventory;

    public PlaceOrderHandler(InventoryReservation inventory) {
        this.inventory = inventory;
    }

    public PlaceOrderResult handle(PlaceOrder command) {
        ReservationResult result = inventory.reserve(
            new ReserveStock(command.orderId(), command.items())
        );

        if (result.status() != ReservationStatus.RESERVED) {
            return PlaceOrderResult.rejected("INVENTORY_UNAVAILABLE");
        }

        return PlaceOrderResult.accepted(result.reservationId());
    }
}
~~~

Đây là lời gọi trong cùng tiến trình, không có network timeout hoặc serialization. Tuy nhiên, API vẫn cần rõ nghĩa và ổn định. Khi sau này Inventory được tách thành dịch vụ riêng, adapter có thể thay lời gọi trực tiếp bằng HTTP hoặc messaging mà Sales giữ nguyên cách sử dụng contract nếu hợp đồng được thiết kế tốt.

Không nên cố mô phỏng toàn bộ microservice infrastructure trong một monolith. Không cần thêm REST, retry qua network hoặc broker nếu lời gọi nội bộ đồng bộ đáp ứng yêu cầu. Hãy giữ abstraction vừa đủ để bảo vệ ranh giới.

## 10. Domain Event và event nội bộ giữa các module

Một context có thể công bố event khi một sự thật nghiệp vụ xảy ra:

~~~java
public record InventoryReserved(
    UUID reservationId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Sales có thể nhận event này để tiếp tục xác nhận đơn. Trong monolith, event có thể được dispatch trong process. Nếu event chỉ được phát sau khi transaction lưu trữ commit, cần xác định rõ cơ chế bảo đảm thứ tự và lỗi.

Phân biệt:

- Domain Event nội bộ: sự thật trong mô hình của chính context.
- Integration Event: hợp đồng công bố cho context hoặc hệ thống khác.
- Application Event: cơ chế kỹ thuật chuyển thông báo trong cùng ứng dụng.

Một Domain Event có thể được chuyển thành Integration Event, nhưng không nhất thiết phải công bố nguyên xi object nội bộ. Adapter nên chọn payload và thuật ngữ phù hợp với consumer.

## 11. Quyền sở hữu dữ liệu khi cùng dùng một database

Các context trong monolith có thể dùng chung một database vật lý vì lý do vận hành. Điều đó không có nghĩa tất cả cùng sở hữu mọi bảng.

Ví dụ:

| Bảng hoặc dữ liệu | Context sở hữu | Context khác được phép |
| --- | --- | --- |
| customer_profiles | Customer Management | Đọc qua API hoặc projection được công bố |
| sales_orders | Sales | Dùng API/query contract của Sales |
| stock_items, reservations | Inventory | Gửi command và nhận kết quả/event |
| payments, refunds | Payment | Dùng hợp đồng thanh toán |
| shipments | Fulfillment | Gửi yêu cầu và nhận trạng thái công bố |

Quy tắc quan trọng là chỉ owner được thay đổi dữ liệu chủ và bảo vệ bất biến của nó. Nếu Sales cập nhật trực tiếp bảng reservations, nó bỏ qua hành vi và quy tắc của Inventory dù database nằm cùng máy.

Có thể bắt đầu với một database và schema riêng theo context. Khi hệ thống phát triển, owner có thể tách schema hoặc database mà không phải thay đổi mọi consumer nếu API đã được giữ ổn định.

## 12. Chia sẻ database vật lý có những trade-off gì?

Một database dùng chung có thể giúp:

- Triển khai và vận hành ban đầu đơn giản.
- Dùng chung hạ tầng backup, monitoring và connection pool.
- Thực hiện một số transaction ACID trong cùng database khi nghiệp vụ thực sự yêu cầu.
- Giảm chi phí vận hành so với nhiều database độc lập.

Nhưng cũng có rủi ro:

- Module truy vấn trực tiếp bảng của context khác.
- Migration của một context vô tình làm hỏng context khác.
- Một transaction lớn cập nhật nhiều vùng dữ liệu làm mờ quyền sở hữu.
- Index, lock và tải truy vấn của một context ảnh hưởng context khác.
- Dữ liệu dùng chung tạo phụ thuộc schema và cản trở tách module.

Biện pháp giảm rủi ro gồm schema riêng, quyền truy cập DB theo owner nếu có thể, migration do owner quản lý, không export persistence entity và kiểm tra dependency ở cấp code.

## 13. Có thể dùng transaction chung giữa nhiều context không?

Vì các context nằm trong cùng ứng dụng và có thể dùng cùng database, về mặt kỹ thuật một transaction có thể cập nhật dữ liệu của nhiều module. Tuy nhiên, không nên mặc định mọi use case liên context đều cần một transaction chung.

Trước hết hãy hỏi:

- Có bất biến nghiệp vụ nào bắt buộc phải đúng ngay trên toàn bộ các context không?
- Dữ liệu nào thực sự cần được ghi nguyên tử?
- Quy tắc có thể được sở hữu bởi một context duy nhất không?
- Có thể chấp nhận trạng thái trung gian và hoàn tất bằng event/process manager không?
- Transaction chung có làm các module phụ thuộc chặt vào schema của nhau không?

Nếu nghiệp vụ yêu cầu một quyết định nguyên tử trên cùng database, một transaction chung có thể là lựa chọn hợp lý. Nhưng application service điều phối vẫn nên gọi các API/port công khai; nó không nên tự sửa bảng nội bộ để đạt tính nguyên tử.

Nếu quy trình có thể chấp nhận eventual consistency, hãy dùng command/event và process manager. Khi đó mỗi context commit thay đổi của mình, còn quy trình tổng thể xử lý retry hoặc compensation.

## 14. Ví dụ quy trình đặt hàng trong modular monolith

Giả sử người mua đặt hàng. Sales cần giữ hàng ở Inventory và yêu cầu Payment cấp phép thanh toán. Cả ba context chạy trong một ứng dụng:

~~~mermaid
sequenceDiagram
    participant U as User
    participant S as Sales
    participant I as Inventory
    participant P as Payment
    U->>S: PlaceOrder
    S->>I: reserve(order, items)
    I-->>S: ReservationResult
    alt Inventory available
        S->>P: authorize(order, amount)
        P-->>S: PaymentResult
        alt Payment authorized
            S->>S: Confirm order
            S-->>U: Order confirmed
        else Payment declined
            S->>I: release reservation
            S-->>U: Order rejected
        end
    else Inventory unavailable
        S-->>U: Order rejected
    end
~~~

Sơ đồ mô tả một luồng đơn giản. Nếu các bước phải bất đồng bộ hoặc tích hợp với nhà cung cấp bên ngoài, Sales có thể duy trì Process Manager và trạng thái trung gian. Dù các context nằm trong cùng process, mỗi context vẫn tự bảo vệ Aggregate của mình.

## 15. Không chia sẻ Aggregate hoặc transaction object xuyên context

Một cách làm nguy hiểm là Sales nhận object StockItem nội bộ của Inventory rồi sửa trực tiếp:

~~~java
// Không nên: Sales thao tác trên Aggregate nội bộ của Inventory.
StockItem item = inventoryRepository.findBySku(sku);
item.decreaseAvailableQuantity(quantity);
inventoryRepository.save(item);
~~~

Sales lúc này biết cấu trúc và quy tắc nội bộ của Inventory. Khi Inventory thay đổi cách tính available quantity hoặc cách giữ chỗ, Sales phải thay đổi theo.

Hãy yêu cầu owner thực hiện hành vi qua API:

~~~java
ReservationResult result = inventoryReservation.reserve(
    new ReserveStock(orderId, requestedItems)
);
~~~

Không truyền JPA entity, Hibernate proxy, Aggregate Root mutable hoặc transaction-bound object qua ranh giới. Hãy dùng command, query result, ID hoặc event contract có ý nghĩa rõ ràng.

## 16. Khi nào nên dùng API đồng bộ và khi nào dùng event?

| Nhu cầu | Cách tương tác có thể phù hợp | Lưu ý |
| --- | --- | --- |
| Cần quyết định ngay để trả kết quả use case | API/query/command đồng bộ | Có phụ thuộc trực tiếp về thời gian và lỗi |
| Thông báo một sự thật đã xảy ra | Domain/Integration Event | Consumer cần xử lý trùng và lỗi |
| Cập nhật read model hoặc projection | Event handler | Có thể có độ trễ |
| Quy trình kéo dài qua nhiều bước | Process Manager/Saga | Cần lưu trạng thái, retry và compensation |
| Chia sẻ dữ liệu tra cứu ổn định | Query contract hoặc projection | Cần xác định owner và độ tươi dữ liệu |

Không nên chọn event chỉ vì hệ thống có nhiều module. Lời gọi đồng bộ đơn giản có thể dễ hiểu hơn nếu quy trình cần kết quả ngay và không tạo phụ thuộc khó kiểm soát. Ngược lại, event phù hợp khi consumer không cần phản hồi ngay hoặc cần phản ứng độc lập.

## 17. Modular Monolith vẫn cần quản lý dependency

Một ứng dụng nguyên khối có thể trở thành “big ball of mud” nếu mọi module gọi lẫn nhau. Hãy xác định dependency direction và kiểm tra nó.

Ví dụ:

~~~text
sales
  -> customer.api
  -> inventory.api
  -> payment.api

inventory
  -> inventory.domain
  -> inventory.infrastructure

payment
  -> payment.domain
  -> payment.infrastructure
~~~

Sales không được import inventory.domain hoặc inventory.infrastructure. Nó chỉ phụ thuộc inventory.api. Inventory không cần biết class SalesOrder nội bộ; nó nhận ReserveStock contract chứa các dữ kiện cần thiết.

Nếu dependency hai chiều xuất hiện, hãy xem lại trách nhiệm và hướng điều phối. Có thể một context đang làm quá nhiều việc hoặc hợp đồng tích hợp đang bị đặt sai chỗ.

## 18. Kiểm thử ranh giới module

Một modular monolith cần kiểm tra cả hành vi và cấu trúc phụ thuộc:

- Unit test domain của từng context.
- Application test xác nhận use case và hợp đồng công khai.
- Integration test cho adapter persistence và event handler.
- Contract test để bảo đảm consumer sử dụng API đúng cách.
- Architecture test để phát hiện import từ package nội bộ của context khác.
- End-to-end test cho các quy trình đi qua nhiều context.

Ví dụ quy tắc kiến trúc cần kiểm tra:

~~~text
sales.* chỉ được phụ thuộc customer.api, inventory.api và payment.api.
sales.* không được phụ thuộc inventory.domain hoặc inventory.infrastructure.
Mọi module không được phụ thuộc persistence record của module khác.
~~~

Có thể dùng công cụ kiểm tra kiến trúc hoặc test dependency tùy dự án. Điều quan trọng là quy tắc module được tự động hóa để tránh ranh giới chỉ tồn tại trong tài liệu.

## 19. Lợi ích của nhiều Bounded Context trong một Monolith

Kết hợp ranh giới DDD với một deployment unit có thể mang lại:

- Mô hình nghiệp vụ tách biệt mà không cần vận hành nhiều dịch vụ.
- Gọi nội bộ nhanh, không có network hop cho các tương tác trong process.
- Một quy trình build/deploy và quan sát vận hành đơn giản hơn.
- Dễ tái cấu trúc và thử nghiệm ranh giới trước khi quyết định tách service.
- Có thể dùng transaction ACID trong cùng database khi thực sự phù hợp.
- Đội ngũ có thể phát triển theo module và trách nhiệm nghiệp vụ.

Đây là lựa chọn hữu ích khi domain đã có nhiều mô hình khác nhau nhưng tổ chức chưa cần hoặc chưa sẵn sàng vận hành distributed system.

## 20. Giới hạn và chi phí của Modular Monolith

Modular monolith vẫn có những giới hạn:

- Các module cùng chia sẻ tài nguyên process và có thể ảnh hưởng hiệu năng của nhau.
- Một lỗi nghiêm trọng trong process có thể làm toàn bộ ứng dụng dừng.
- Không thể scale riêng Inventory mà không scale toàn bộ deployment unit.
- Release một module thường kéo theo phát hành toàn ứng dụng.
- Dùng chung database dễ tạo phụ thuộc nếu không bảo vệ ownership.
- Quy tắc module có thể bị phá vỡ nếu codebase không có cơ chế kiểm tra.

Những giới hạn này không làm modular monolith trở thành lựa chọn kém. Chúng chỉ cho biết khi nào cần cân nhắc tách tiến trình hoặc dịch vụ.

## 21. Từ Modular Monolith đến Microservices

Một modular monolith được thiết kế tốt có thể tạo nền tảng để tách một Bounded Context thành service khi có lý do thực tế:

- Context cần scale độc lập vì tải khác biệt đáng kể.
- Nhóm cần triển khai độc lập với nhịp release riêng.
- Context có yêu cầu bảo mật, tuân thủ hoặc vùng dữ liệu riêng.
- Cần cô lập lỗi hoặc công nghệ vận hành khác nhau.
- Một phần hệ thống cần mức sẵn sàng hoặc mô hình vận hành riêng.

Quy trình tách có thể gồm:

1. Xác nhận context có mô hình và trách nhiệm rõ.
2. Xác định API/event contract mà consumer đang dùng.
3. Bảo đảm consumer không truy cập database hoặc class nội bộ.
4. Tách quyền sở hữu dữ liệu và quy trình migration.
5. Chuyển adapter gọi trực tiếp thành HTTP hoặc messaging adapter.
6. Xác định timeout, retry, idempotency, observability và failure handling.
7. Chuyển deployment và kiểm thử contract/end-to-end.

Khi tách, lời gọi Java trong process trở thành giao tiếp qua network. Điều đó thêm latency, timeout, lỗi kết nối, serialization, versioning và eventual consistency. Vì vậy, không nên tách service chỉ vì module đã có package riêng.

## 22. Khi nào nên giữ nhiều context trong một ứng dụng nguyên khối?

Đây có thể là lựa chọn phù hợp khi:

- Hệ thống còn nhỏ hoặc vừa và một deployment unit đáp ứng tải.
- Các context có thể được phân chia logic nhưng chưa cần scale độc lập.
- Nhóm muốn tránh chi phí vận hành distributed system.
- Nhiều use case cần transaction chung trên cùng database và nghiệp vụ cho phép thiết kế như vậy.
- Tổ chức chưa có năng lực quan sát, triển khai và xử lý sự cố cho nhiều service.
- Ranh giới nghiệp vụ đã rõ nhưng ranh giới vận hành chưa cần tách.

Hãy giữ module độc lập ở mức code, contract và data ownership. Có thể bắt đầu với một process, rồi tách khi các yêu cầu vận hành thực sự xuất hiện.

## 23. Những dấu hiệu modular monolith đang mất ranh giới

Hãy xem xét lại thiết kế nếu:

- Nhiều context dùng chung một Entity có quá nhiều trường và trạng thái.
- Module gọi repository hoặc truy cập bảng nội bộ của nhau.
- Một thay đổi nhỏ ở Inventory buộc Sales, Payment và Fulfillment sửa code không liên quan.
- Package common chứa nhiều khái niệm nghiệp vụ dùng chung không có cùng ngữ nghĩa.
- Module phụ thuộc vòng tròn hoặc phải khởi tạo lẫn nhau.
- Một transaction điều phối cập nhật nhiều bảng nội bộ mà không có owner rõ ràng.
- Không thể kiểm thử một module mà phải khởi động toàn bộ hệ thống.
- Không thể thay implementation nội bộ mà không sửa consumer.

Giải pháp thường là làm rõ API, ownership, dependency direction và mô hình riêng; không nhất thiết phải chuyển ngay sang microservices.

## 24. Những lỗi thường gặp

**Cho rằng mỗi Bounded Context phải là một microservice.** Bounded Context là ranh giới mô hình. Nó có thể được triển khai trong cùng một ứng dụng.

**Coi monolith là một Bounded Context duy nhất.** Một process có thể chứa nhiều mô hình và ngôn ngữ nghiệp vụ. Hãy phân chia theo ngữ nghĩa và trách nhiệm.

**Chia package theo tầng kỹ thuật dùng chung.** Cách này có thể làm mờ ranh giới nghiệp vụ. Hãy tổ chức theo context rồi chia tầng bên trong.

**Chia sẻ Entity để tránh mapping.** Hai context có thể có cách hiểu và vòng đời khác nhau. Dùng contract, ID, snapshot hoặc projection.

**Gọi trực tiếp class nội bộ vì cùng JVM.** Điều này tạo phụ thuộc vào implementation. Hãy dùng API công khai.

**Cho nhiều context ghi cùng một bảng.** Quyền sở hữu và bất biến bị phân tán. Chỉ owner được ghi dữ liệu chủ.

**Dùng transaction chung cho mọi quy trình.** Có thể tạo coupling và transaction lớn. Chỉ dùng khi yêu cầu nhất quán nghiệp vụ thực sự cần.

**Dùng event cho mọi tương tác.** Event làm tăng yêu cầu xử lý trùng, thứ tự và quan sát. Gọi đồng bộ khi đó là cách đơn giản và phù hợp.

**Tách microservice quá sớm.** Tổ chức phải gánh network failure, deploy, monitoring và data consistency trước khi có nhu cầu. Bắt đầu bằng module rõ ràng nếu một process đã đủ.

## 25. Quy trình thiết kế Bounded Context trong Monolith

1. **Khám phá mô hình nghiệp vụ:** dùng ngôn ngữ chuyên gia, quy trình và quy tắc để xác định các vùng mô hình.
2. **Xác định Bounded Context:** mô tả trách nhiệm, thuật ngữ, Aggregate và dữ liệu owner của từng context.
3. **Lập Context Map:** xác định context nào cung cấp dữ kiện hoặc dịch vụ cho context nào và kiểu quan hệ tương ứng.
4. **Tổ chức module theo context:** đặt domain, application, API và infrastructure bên trong module.
5. **Thiết kế API công khai:** chỉ công bố command, query, result hoặc event cần thiết.
6. **Giới hạn truy cập nội bộ:** dùng visibility, module boundary và architecture test.
7. **Quy định ownership dữ liệu:** chỉ owner được ghi dữ liệu chủ; xác định snapshot và projection ở consumer.
8. **Chọn cách tương tác:** gọi đồng bộ, event nội bộ hoặc process manager theo yêu cầu use case.
9. **Xác định transaction boundary:** bảo vệ bất biến tại owner và chỉ điều phối transaction chung khi có lý do nghiệp vụ.
10. **Kiểm thử module và quy trình:** unit, contract, integration, architecture và end-to-end test.
11. **Triển khai như một đơn vị:** dùng chung pipeline và runtime nhưng giữ trách nhiệm module rõ.
12. **Đánh giá nhu cầu tách service:** chỉ tách khi scale, release, bảo mật, tuân thủ hoặc vận hành tạo ra lý do cụ thể.

## 26. Checklist rà soát

- Bounded Context đã có mô hình và ngôn ngữ riêng chưa?
- Mọi người có phân biệt ranh giới mô hình với ranh giới deployment không?
- Module được tổ chức theo context hay chỉ theo tầng kỹ thuật?
- Context khác chỉ dùng API công khai hay vẫn import class nội bộ?
- Aggregate và persistence record có bị chia sẻ xuyên context không?
- Mỗi dữ liệu chủ có một owner rõ ràng không?
- Consumer có lưu snapshot/projection với ý nghĩa và độ tươi dữ liệu rõ không?
- Tương tác đồng bộ và bất đồng bộ có được chọn theo nhu cầu nghiệp vụ không?
- Event có xử lý trùng, lỗi và thứ tự không?
- Transaction chung có lý do nghiệp vụ rõ ràng không?
- Có architecture test để ngăn dependency sai không?
- Có thể thay đổi implementation nội bộ mà không làm consumer sửa theo không?
- Có lý do vận hành cụ thể trước khi tách thành microservice không?

## 27. Nguyên tắc cần ghi nhớ

Bounded Context xác định ranh giới của mô hình và ngôn ngữ nghiệp vụ; nó không bắt buộc phải là một tiến trình hoặc deployment unit riêng. Một ứng dụng nguyên khối có thể chứa nhiều context nếu mỗi context giữ mô hình, hành vi, quyền sở hữu dữ liệu và API công khai rõ ràng.

Hãy tổ chức code theo Bounded Context, giới hạn phụ thuộc vào API công khai, tránh chia sẻ Aggregate hoặc persistence model và để mỗi context sở hữu dữ liệu của mình. Modular Monolith cho phép tận dụng sự đơn giản của một deployment unit trong khi vẫn giữ ranh giới DDD. Khi nhu cầu scale, release, bảo mật hoặc vận hành độc lập xuất hiện, các module đã có contract và ownership rõ sẽ là điểm xuất phát tốt để tách dịch vụ.
