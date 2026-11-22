# Xử lý dữ liệu tham chiếu và bản sao cục bộ của thông tin bên ngoài

Trong Domain-Driven Design (DDD), mỗi Bounded Context sở hữu mô hình và các quy tắc nghiệp vụ của chính nó. Một context có thể cần dùng thông tin do context hoặc hệ thống khác quản lý: tên và trạng thái khách hàng, mô tả sản phẩm, khu vực giao hàng, loại tiền, mã thuế hoặc trạng thái vận chuyển. Câu hỏi thiết kế không chỉ là lấy dữ liệu đó bằng cách nào, mà còn là **context nào có quyền quyết định, context nào chỉ tiêu thụ, và bản sao được dùng với mức độ tin cậy nào**.

Một context có thể giữ dữ liệu tham chiếu hoặc bản sao cục bộ để phục vụ nhu cầu riêng. Bản sao giúp giảm phụ thuộc vào thời gian phản hồi và tính sẵn sàng của hệ thống bên ngoài, đồng thời cho phép mô hình hóa dữ liệu theo ngôn ngữ nội bộ. Tuy nhiên, bản sao không tự trở thành nguồn dữ liệu có thẩm quyền. Nếu một quy tắc nghiệp vụ cần quyết định trên dữ liệu mới nhất, context tiêu thụ phải hỏi context sở hữu hoặc gửi một command để context sở hữu thực hiện quyết định.

Bài học này tập trung vào quyền sở hữu dữ liệu giữa các Bounded Context, tham chiếu bằng identity, local replica/projection, snapshot lịch sử, các cách đồng bộ, freshness, xử lý event trùng hoặc sai thứ tự và chính sách khi dữ liệu bên ngoài không sẵn sàng.

## 1. Vì sao một context cần dữ liệu từ bên ngoài?

Một Bounded Context có thể cần biết một phần thông tin do context khác sở hữu để hoàn thành use case của mình.

Ví dụ trong hệ thống thương mại điện tử:

- Sales cần tên hiển thị và trạng thái tài khoản của khách hàng.
- Order cần mô tả sản phẩm và giá tại thời điểm đặt.
- Shipping cần địa chỉ nhận hàng và khu vực phục vụ.
- Billing cần mã số thuế và thông tin xuất hóa đơn.
- Customer Management sở hữu hồ sơ và trạng thái khách hàng.
- Product Catalog sở hữu thông tin danh mục sản phẩm.
- Inventory sở hữu số lượng có thể giữ.
- Shipping sở hữu tiến trình giao hàng.

Không phải mọi context đều cần tải toàn bộ mô hình của context khác. Shipping không cần biết toàn bộ lịch sử mua hàng của Customer; Order không cần biết cách Product Catalog tổ chức cây danh mục nội bộ.

Mỗi context chỉ nên nhận phần dữ liệu cần thiết cho quyết định hoặc trải nghiệm mà nó chịu trách nhiệm.

### Ví dụ về ranh giới sở hữu

| Dữ liệu | Context có thẩm quyền | Context có thể tiêu thụ |
|---|---|---|
| Hồ sơ khách hàng | Customer Management | Sales, Order, Support |
| Mô tả và phân loại sản phẩm | Product Catalog | Sales, Order, Search |
| Giá bán hiện hành | Pricing | Sales, Quotation |
| Tồn kho và reservation | Inventory | Order, Fulfillment |
| Địa chỉ và tiến trình giao | Shipping | Order, Customer Support |
| Hóa đơn và nghĩa vụ thanh toán | Billing | Order, Finance |

Bảng này là ví dụ. Trong một hệ thống khác, ownership có thể được phân chia khác nhau. Điều quan trọng là đội ngũ phải thống nhất ai có quyền thay đổi dữ liệu và ai chỉ sử dụng nó.

## 2. Phân biệt nguồn có thẩm quyền, tham chiếu và bản sao cục bộ

Ba khái niệm thường bị trộn lẫn:

- **Authoritative source / System of Record:** nơi có quyền quyết định giá trị chính thức của dữ liệu.
- **Reference:** identity hoặc mã được dùng để chỉ đến một khái niệm do context khác quản lý.
- **Local copy / Replica / Projection:** một phần dữ liệu được sao chép sang context tiêu thụ để phục vụ truy vấn hoặc xử lý cục bộ.

Ví dụ, Customer Management là nguồn có thẩm quyền cho trạng thái tài khoản. Order có thể giữ CustomerId để biết đơn thuộc về khách hàng nào. Sales có thể giữ một bản sao tên hiển thị và hạng thành viên để tìm kiếm nhanh.

Việc Sales giữ bản sao tên và hạng không trao cho Sales quyền đổi hạng thành viên. Khi khách hàng được nâng hạng, Customer Management vẫn là nơi quyết định; Sales nhận thay đổi và cập nhật projection của mình.

### Ownership không chuyển theo bản sao

Một lỗi thiết kế thường gặp là cho rằng context nào lưu dữ liệu thì context đó sở hữu dữ liệu. Thực tế, quyền sở hữu được xác định bởi ngữ nghĩa nghiệp vụ và trách nhiệm ra quyết định, không phải bởi vị trí vật lý của bản ghi.

    Customer Management
       owns Customer status
              |
              | publishes changes
              v
       Sales local projection
       - customerId
       - displayName
       - membershipTier
       - sourceVersion

Sales có thể đọc projection để hiển thị danh sách khách hàng. Nhưng nếu muốn khóa tài khoản, Sales phải gửi yêu cầu đến Customer Management. Sales không tự cập nhật cột status trong bản sao rồi coi đó là quyết định chính thức.

## 3. Bốn loại dữ liệu cần phân biệt

Không phải mọi dữ liệu bên ngoài đều có cùng yêu cầu về freshness và lịch sử. Có thể chia thành các nhóm sau.

| Loại dữ liệu | Ví dụ | Cách dùng thường gặp | Yêu cầu chính |
|---|---|---|---|
| Reference data ít thay đổi | Quốc gia, đơn vị đo, mã tiền tệ | Tra cứu, validation cấu trúc | Tính ổn định, phiên bản |
| External master/profile data | Tên khách hàng, mô tả sản phẩm | Hiển thị, tìm kiếm, lọc | Freshness phù hợp |
| Decision-critical data | Hạn mức tín dụng, tồn kho có thể giữ | Quyết định giao dịch | Phải được xác nhận tại nơi có thẩm quyền |
| Historical snapshot | Đơn giá lúc đặt, địa chỉ lúc giao | Tái hiện giao dịch quá khứ | Bất biến theo thời điểm ghi nhận |

Một trường hợp có thể thuộc nhiều nhóm tùy ngữ nghĩa. Ví dụ địa chỉ hiện tại của khách hàng là profile data; địa chỉ được chốt trên đơn hàng là historical snapshot.

### Reference data

Reference data thường có tập giá trị được quản lý tương đối ổn định, chẳng hạn mã quốc gia, loại tiền, đơn vị đo hoặc mã trạng thái chuẩn. Nó có thể được tải theo lịch hoặc đóng gói theo phiên bản.

### External master/profile data

Đây là dữ liệu thuộc quyền sở hữu của một context khác nhưng context hiện tại cần dùng một phần. Ví dụ Sales giữ tên hiển thị và membership tier của khách hàng.

### Decision-critical data

Đây là dữ liệu ảnh hưởng trực tiếp đến quyết định nghiệp vụ có rủi ro nếu bị cũ. Ví dụ số lượng hàng còn có thể giữ, hạn mức tín dụng còn lại hoặc trạng thái thanh toán. Bản sao có thể hỗ trợ hiển thị hoặc sàng lọc sơ bộ, nhưng không nên tự quyết định thay nguồn có thẩm quyền.

### Historical snapshot

Snapshot lưu giá trị đã được chấp nhận tại thời điểm một nghiệp vụ xảy ra. Nó không phải cache để tự động refresh. Ví dụ, đơn hàng đã đặt cần giữ đơn giá và địa chỉ giao tại thời điểm đặt ngay cả khi giá sản phẩm hoặc địa chỉ hồ sơ thay đổi sau đó.

## 4. Khi nào chỉ cần tham chiếu bằng ID?

Nếu context chỉ cần biết một đối tượng liên quan là đối tượng nào, có thể lưu identity của Aggregate Root bên ngoài thay vì sao chép toàn bộ object.

Ví dụ:

    public final class Order {
        private final OrderId id;
        private final CustomerId customerId;
    }

Order giữ CustomerId để xác định khách hàng sở hữu đơn. Nó không cần nhúng Customer entity đầy đủ vào Aggregate Order.

Ưu điểm:

- Giữ ranh giới Aggregate rõ.
- Tránh sao chép dữ liệu không cần thiết.
- Tránh giữ object graph mutable thuộc context khác.
- Giảm phụ thuộc vào cấu trúc mô hình của context sở hữu.
- Dễ phối hợp khi cần gọi API hoặc gửi command đến context sở hữu.

Tuy nhiên, chỉ giữ ID có thể không đủ cho use case cần hiển thị hoặc ra quyết định khi context sở hữu đang tạm thời không sẵn sàng. Khi đó có thể cần một bản sao cục bộ tối thiểu.

### Không dùng ID như một lời gọi truy cập tự động

Một CustomerId không có nghĩa Order có thể tự tải Customer bằng cách gọi network từ bên trong Aggregate. Nếu cần dữ liệu, Application Service hoặc domain service được điều phối ở đúng tầng sẽ lấy dữ liệu qua port phù hợp rồi truyền vào hành vi domain.

Domain Entity không nên tự phụ thuộc HTTP client, message broker hoặc repository của context khác.

## 5. Khi nào nên tạo bản sao cục bộ?

Local copy hữu ích khi context tiêu thụ cần dữ liệu bên ngoài cho một hoặc nhiều mục đích:

- Hiển thị và tìm kiếm mà không gọi hệ thống sở hữu trên từng request.
- Tạo báo cáo hoặc projection có cấu trúc phù hợp với nhu cầu nội bộ.
- Giảm độ trễ của màn hình hoặc truy vấn.
- Tiếp tục phục vụ một số chức năng khi hệ thống nguồn tạm thời gián đoạn.
- Giảm số lượng lời gọi đồng bộ giữa các bounded context.
- Giữ một phần dữ liệu để xử lý bất đồng bộ.

Ví dụ, Sales có thể cần tìm khách hàng theo tên, email và hạng thành viên. Gọi Customer Management cho từng dòng trong kết quả tìm kiếm có thể gây N+1 network calls. Một projection cục bộ giúp truy vấn hiệu quả hơn.

Nhưng local copy chỉ nên chứa các field thực sự cần thiết. Sao chép toàn bộ Customer aggregate sang Sales làm tăng coupling, rủi ro lộ dữ liệu và chi phí đồng bộ.

### Bản sao phục vụ đọc và bản sao phục vụ quyết định

Cần xác định bản sao được dùng cho mục đích gì:

- **Read projection:** hiển thị, tìm kiếm, lọc, báo cáo.
- **Decision support:** hỗ trợ đánh giá sơ bộ một điều kiện.
- **Operational replica:** giúp xử lý cục bộ trong khi nguồn có thể tạm thời không sẵn sàng.
- **Historical snapshot:** ghi nhận dữ liệu đã được chốt cho một giao dịch.

Không nên dùng read projection như bằng chứng cuối cùng cho một invariant mà context khác sở hữu.

## 6. Không sao chép dữ liệu chỉ vì có thể

Mỗi field được sao chép đều tạo thêm trách nhiệm:

- Ai cập nhật nó?
- Bao lâu thì bản sao phải mới?
- Điều gì xảy ra khi event đến trễ?
- Có cần giữ lịch sử không?
- Khi dữ liệu bị xóa ở nguồn, bản sao xử lý thế nào?
- Có dữ liệu nhạy cảm nào không nên lưu?
- Nếu đồng bộ thất bại, use case nào bị ảnh hưởng?

Một bản sao không có chính sách đồng bộ và xử lý lỗi rõ ràng sẽ trở thành dữ liệu sai lệch theo thời gian.

Trước khi sao chép, hãy hỏi:

1. Use case có thực sự cần giá trị này không?
2. Có thể chỉ lưu ID và lấy dữ liệu khi cần không?
3. Có cần dữ liệu mới nhất hay chỉ cần dữ liệu tại thời điểm giao dịch?
4. Độ trễ đồng bộ tối đa chấp nhận được là bao lâu?
5. Nếu nguồn không sẵn sàng, có thể tiếp tục không?
6. Bản sao có thể được dùng để quyết định nghiệp vụ hay chỉ để đọc?
7. Ai chịu trách nhiệm sửa sai lệch?

## 7. Chọn cơ chế đồng bộ phù hợp

Có nhiều cách đưa dữ liệu từ nguồn có thẩm quyền sang context tiêu thụ. Không có một cơ chế duy nhất phù hợp cho mọi dữ liệu.

| Cơ chế | Cách hoạt động | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Synchronous API lookup | Gọi nguồn khi cần dữ liệu | Có thể nhận giá trị mới tại thời điểm gọi | Phụ thuộc latency và availability |
| Asynchronous integration event | Nguồn phát event, consumer cập nhật bản sao | Giảm coupling thời gian, mở rộng tốt | Eventual consistency |
| Scheduled batch sync | Tải thay đổi theo lịch | Đơn giản với dữ liệu ít thay đổi | Bản sao có thể cũ giữa hai lần chạy |
| Change Data Capture (CDC) | Đọc thay đổi từ log database | Có thể bắt thay đổi gần thời gian thực | Dễ coupling vào schema/storage nếu không có contract |
| Cache with TTL | Lưu kết quả đọc tạm thời | Giảm tải và latency | Phải chấp nhận hoặc xử lý dữ liệu cũ |

### Synchronous API lookup

Phù hợp khi:

- Dữ liệu ít được gọi.
- Cần câu trả lời mới tại thời điểm xử lý.
- Nguồn có SLA đủ tốt.
- Use case có thể chấp nhận phụ thuộc thời gian phản hồi.

Ví dụ, trước khi phê duyệt một giao dịch tín dụng, Billing gọi Credit Management để yêu cầu quyết định hạn mức. Nếu không nhận được câu trả lời, Billing có thể phải dừng giao dịch theo chính sách.

Không nên gọi synchronous API cho mọi field của mọi màn hình nếu dữ liệu có thể được đồng bộ trước.

### Asynchronous integration event

Nguồn phát event khi dữ liệu thay đổi. Consumer nhận event, ánh xạ sang mô hình cục bộ và cập nhật projection.

Phù hợp khi:

- Context tiêu thụ cần truy vấn dữ liệu thường xuyên.
- Độ trễ vài giây hoặc vài phút được chấp nhận.
- Có thể xử lý eventual consistency.
- Muốn tránh gọi trực tiếp nguồn trên mọi request.

### Scheduled batch sync

Phù hợp với dữ liệu ít thay đổi, khối lượng lớn hoặc nguồn chỉ cung cấp file export theo lịch. Ví dụ, danh mục vùng địa lý có thể được đồng bộ mỗi đêm.

Batch cần có checkpoint, version hoặc watermark để không bỏ sót thay đổi. Nếu một lần chạy thất bại, lần chạy sau cần tiếp tục hoặc đối soát lại được.

### CDC

CDC có thể hữu ích khi cần bắt thay đổi gần thời gian thực từ hệ thống legacy. Tuy nhiên, đọc trực tiếp database log của context khác dễ khiến consumer phụ thuộc vào bảng, cột và schema nội bộ. Nếu dùng CDC, nên chuyển đổi thay đổi thành contract ổn định ở adapter thay vì để schema database lan sang domain tiêu thụ.

### Cache

Cache phù hợp để tối ưu truy cập, nhưng cache không tự giải quyết ownership hoặc consistency. Cần xác định TTL, invalidation, stale fallback và cách xử lý khi nguồn thay đổi.

## 8. Synchronous lookup hay local replica?

Có thể chọn bằng cách xét mức độ quan trọng của freshness và khả năng chấp nhận phụ thuộc nguồn.

| Câu hỏi | Nghiêng về lookup đồng bộ | Nghiêng về local replica |
|---|---|---|
| Có cần giá trị mới nhất ngay lúc quyết định? | Có | Không, chấp nhận độ trễ |
| Tần suất đọc cao? | Thấp hoặc vừa | Cao |
| Nguồn có SLA và latency tốt? | Có | Không bắt buộc |
| Có cần tìm kiếm/lọc hàng loạt? | Không thuận lợi | Phù hợp |
| Có thể tiếp tục khi nguồn gián đoạn? | Thường không | Có thể theo policy |
| Dữ liệu có thay đổi thường xuyên? | Có thể phù hợp | Cần event và freshness SLA |
| Quyết định có rủi ro cao? | Có thể yêu cầu xác nhận nguồn | Replica chỉ hỗ trợ, không tự quyết định |

Một kiến trúc có thể kết hợp cả hai. Ví dụ, Sales dùng local projection để hiển thị và lọc khách hàng, nhưng gửi command tới Customer Management khi cần thay đổi trạng thái tài khoản.

## 9. Integration Event và local projection

Giả sử Customer Management sở hữu hồ sơ khách hàng. Khi tên hiển thị hoặc hạng thành viên thay đổi, context này phát integration event:

    CustomerProfileChanged

Payload có thể gồm:

    eventId
    customerId
    sourceVersion
    displayName
    membershipTier
    occurredAt

Sales nhận event và cập nhật projection:

    CustomerReference
      customerId
      displayName
      membershipTier
      sourceVersion
      sourceUpdatedAt
      receivedAt

Projection chỉ chứa dữ liệu Sales cần. Nó có thể dùng tên field hoặc enum riêng theo ngôn ngữ của Sales.

### Không phát tán domain object nội bộ

Không nên serialize trực tiếp JPA entity hoặc Aggregate Customer ra message broker. Điều đó làm contract bên ngoài phụ thuộc cấu trúc persistence và mô hình nội bộ của Customer Management.

Thay vào đó, nguồn tạo integration event có schema ổn định, chỉ chứa dữ liệu cần chia sẻ. Consumer dùng Anti-Corruption Layer để chuyển event thành mô hình cục bộ.

### Event phải có identity và version

Một event nên có metadata đủ để consumer:

- Nhận diện event đã xử lý.
- Biết aggregate hoặc entity nguồn.
- Phân biệt phiên bản thay đổi.
- Theo dõi thời điểm xảy ra.
- Correlate với một workflow nếu cần.

Ví dụ:

    public record CustomerProfileChangedV1(
            UUID eventId,
            String customerId,
            long sourceVersion,
            String displayName,
            String membershipTier,
            Instant occurredAt
    ) {}

Version cần tăng đơn điệu theo từng entity nguồn nếu consumer dùng nó để loại bỏ update cũ. Event version không nhất thiết là global sequence cho toàn hệ thống.

## 10. Xử lý event trùng lặp và đến sai thứ tự

Message broker thường cung cấp delivery at-least-once trong nhiều cấu hình. Consumer có thể nhận cùng một event nhiều lần, hoặc event phiên bản mới đến trước event cũ.

Không nên giả định mỗi event chỉ được giao đúng một lần và theo đúng thứ tự.

### Idempotent consumer

Consumer nên có thể xử lý cùng một event nhiều lần mà kết quả cuối không bị nhân đôi.

Một cách làm là lưu eventId đã xử lý trong inbox table, cùng transaction với việc cập nhật local projection.

    @Transactional
    public void handle(CustomerProfileChangedV1 event) {
        if (inboxRepository.exists(event.eventId())) {
            return;
        }

        CustomerId id = new CustomerId(event.customerId());
        CustomerReference current =
                customerReferenceRepository.findById(id).orElse(null);

        if (current != null
                && current.sourceVersion() >= event.sourceVersion()) {
            inboxRepository.markProcessed(event.eventId());
            return;
        }

        CustomerReference reference = new CustomerReference(
                id,
                event.displayName(),
                event.membershipTier(),
                event.sourceVersion(),
                event.occurredAt(),
                clock.instant()
        );

        customerReferenceRepository.upsert(reference);
        inboxRepository.markProcessed(event.eventId());
    }

Trong thực tế, inbox insert cần unique constraint để xử lý hai delivery đồng thời. Việc ghi inbox và projection phải nằm trong cùng local transaction. Nếu transaction rollback, cả hai thao tác cùng rollback để event có thể được thử lại.

### Bỏ qua event cũ

Giả sử consumer nhận version 12 rồi mới nhận version 11. Nếu event chứa snapshot đầy đủ của entity, consumer có thể bỏ qua version 11 khi local projection đã có version 12.

    if (event.sourceVersion() <= current.sourceVersion()) {
        return;
    }

Điều kiện này chỉ an toàn khi version có ý nghĩa so sánh trên cùng một entity và event biểu diễn đủ state cần cập nhật.

### Event delta và event snapshot khác nhau

- **Snapshot event:** chứa trạng thái cần thiết tại version N. Có thể áp dụng version mới hơn và bỏ qua version cũ nếu contract cho phép.
- **Delta event:** chỉ mô tả một thay đổi, ví dụ điểm thành viên tăng 100. Bỏ qua một event trung gian có thể làm mất dữ liệu. Consumer cần thứ tự, sequence hoặc cơ chế phát hiện gap và lấy lại state.

Ví dụ, event CustomerProfileChanged có thể mang displayName và membershipTier đầy đủ. Nhưng event LoyaltyPointsEarned chỉ mang delta điểm; nếu bỏ qua một event, tổng điểm sẽ sai.

Khi phát hiện gap với delta event, consumer nên tạm dừng xử lý entity đó, lấy snapshot mới từ nguồn hoặc yêu cầu replay từ offset phù hợp. Không được âm thầm tiếp tục như thể dữ liệu đã đầy đủ.

## 11. Freshness: bản sao cũ đến mức nào là chấp nhận được?

Một local copy luôn có khả năng chậm hơn nguồn. Điều quan trọng là xác định độ trễ có thể chấp nhận theo từng use case.

Có thể theo dõi ít nhất ba thời điểm:

- sourceUpdatedAt: nguồn cho biết dữ liệu được cập nhật khi nào.
- occurredAt: event nghiệp vụ xảy ra khi nào.
- receivedAt: consumer nhận được event khi nào.

Từ đó có thể tính event lag hoặc age của bản sao. Không nên chỉ dùng thời điểm consumer nhận event làm bằng chứng dữ liệu mới, vì event có thể đã nằm trong queue lâu trước khi được nhận.

### Freshness SLA

Ví dụ:

| Use case | Độ mới có thể chấp nhận | Hành vi khi vượt ngưỡng |
|---|---|---|
| Tìm kiếm tên khách hàng | Vài phút | Hiển thị dữ liệu hiện có, có thể báo đang cập nhật |
| Hiển thị mô tả sản phẩm | Vài phút | Dùng bản sao gần nhất |
| Kiểm tra tồn kho để hiển thị | Vài giây | Hiển thị số liệu kèm thời điểm cập nhật |
| Giữ tồn kho thực tế | Phải xác nhận tại Inventory | Gửi command reserve |
| Kiểm tra hạn mức tín dụng | Theo chính sách rủi ro | Gọi nguồn có thẩm quyền hoặc từ chối tạm thời |
| Đơn giá đã chốt trên đơn | Theo thời điểm đặt | Giữ snapshot, không refresh |

Không có một TTL hoặc freshness SLA chung cho toàn bộ dữ liệu. Mức chấp nhận phải xuất phát từ hậu quả nếu quyết định dùng dữ liệu cũ.

### Stale data policy

Khi bản sao quá cũ, use case có thể:

- Tiếp tục dùng bản sao và ghi rõ đây là dữ liệu tham khảo.
- Gọi nguồn có thẩm quyền để xác minh.
- Tạm dừng hành động nhạy cảm.
- Từ chối yêu cầu và yêu cầu thử lại.
- Chuyển sang quy trình xử lý thủ công.

Không nên tự động chọn fail-open hoặc fail-closed cho mọi trường hợp. Quyết định phụ thuộc mức độ rủi ro của nghiệp vụ.

## 12. Không dùng bản sao để bảo vệ invariant thuộc context khác

Giả sử Sales có bản sao tồn kho cho biết còn 5 sản phẩm. Hai khách hàng đồng thời đặt 4 sản phẩm.

Cả hai request có thể đọc cùng một bản sao và đều thấy đủ hàng. Nếu Sales tự trừ bản sao rồi xác nhận đơn, hệ thống có thể hứa 8 sản phẩm trong khi kho chỉ có 5.

Inventory mới là context sở hữu số lượng và reservation. Sales hoặc Order cần gửi command:

    ReserveStock(productId, quantity, reservationId)

Inventory kiểm tra state hiện tại và quyết định reservation có hợp lệ không. Kết quả được trả về đồng bộ hoặc qua event tùy thiết kế.

Local stock projection vẫn hữu ích để hiển thị số lượng ước tính, sắp xếp sản phẩm hoặc cảnh báo. Nhưng nó không thay thế thao tác reserve có thẩm quyền.

Nguyên tắc tương tự áp dụng cho:

- Credit limit.
- Payment status.
- Membership eligibility.
- Shipping capacity.
- Unique account name.
- Quota hoặc tài nguyên có cạnh tranh.

Nếu context khác sở hữu invariant, hãy để context đó thực thi quyết định.

## 13. Historical snapshot khác với local replica

Local replica được cập nhật khi nguồn thay đổi. Historical snapshot ghi nhận giá trị tại một thời điểm nghiệp vụ và thường không được cập nhật theo thay đổi sau này.

Ví dụ khi đặt hàng:

    OrderLine
      productId
      productNameAtPurchase
      unitPriceAtPurchase
      currency

    Order
      customerId
      deliveryAddressAtConfirmation
      placedAt

Product Catalog có thể đổi tên sản phẩm và Pricing có thể đổi giá vào ngày hôm sau. Đơn đã đặt vẫn cần hiển thị tên và giá đã chốt lúc khách mua.

Tương tự, Order có thể lưu địa chỉ giao hàng đã xác nhận. Nếu Customer cập nhật địa chỉ hồ sơ sau đó, địa chỉ của đơn cũ không tự đổi theo.

### Chọn dữ liệu nào là reference, dữ liệu nào là snapshot?

| Câu hỏi | Reference bằng ID | Local replica | Historical snapshot |
|---|---|---|---|
| Có cần nhận diện đối tượng nguồn? | Có | Thường có | Có thể có |
| Có cần hiển thị thông tin hiện tại? | Phải tra cứu | Có | Không nhất thiết |
| Có cập nhật khi nguồn đổi? | Không lưu giá trị | Có, theo sync policy | Không |
| Mục tiêu | Liên kết identity | Tối ưu đọc và xử lý | Tái hiện quyết định lịch sử |
| Ví dụ | CustomerId trên Order | Customer search projection | Customer name và address lúc đặt đơn |

Một Aggregate có thể giữ cả CustomerId và snapshot các giá trị đã được chốt. ID cho biết nguồn gốc; snapshot bảo toàn ý nghĩa lịch sử.

## 14. Đồng bộ dữ liệu theo batch và checkpoint

Với reference data hoặc hệ thống legacy, có thể không có event stream. Một job đồng bộ định kỳ sẽ tải các bản ghi thay đổi.

Một quy trình batch nên có:

1. Xác định phạm vi dữ liệu cần đồng bộ.
2. Lấy watermark hoặc cursor của lần chạy trước.
3. Tải các bản ghi thay đổi sau watermark.
4. Chuẩn hóa dữ liệu qua adapter.
5. Upsert vào local projection.
6. Ghi checkpoint sau khi xử lý thành công.
7. Ghi nhận lỗi và cho phép retry.
8. Chạy reconciliation để phát hiện sai lệch.

Checkpoint chỉ nên tiến lên sau khi các bản ghi tương ứng đã được lưu thành công. Nếu checkpoint được cập nhật trước dữ liệu, job có thể bỏ qua các bản ghi khi chạy lại.

### Full sync và incremental sync

- **Full sync:** tải toàn bộ dataset và thay thế hoặc đối soát projection. Phù hợp với dataset nhỏ hoặc khi cần phục hồi.
- **Incremental sync:** chỉ tải thay đổi kể từ watermark. Hiệu quả hơn với dataset lớn.
- **Hybrid:** incremental hằng ngày và full reconciliation theo lịch dài hơn.

Cần xử lý trường hợp bản ghi bị xóa ở nguồn. Nếu nguồn chỉ trả danh sách hiện có, consumer không thể biết một bản ghi biến mất là bị xóa hay bị bỏ khỏi trang kết quả. Contract cần có tombstone, deleted flag hoặc cơ chế snapshot đầy đủ để đối soát.

## 15. Xóa dữ liệu và tombstone

Khi một dữ liệu nguồn bị xóa, bản sao cục bộ cần có chính sách rõ ràng.

Có thể gặp các tình huống:

- Entity bị xóa vật lý.
- Entity bị vô hiệu hóa nhưng vẫn cần tham chiếu.
- Dữ liệu cá nhân cần được xóa hoặc ẩn theo chính sách.
- Entity được merge vào một identity khác.
- Bản ghi bị xóa nhầm và cần phục hồi.

Tombstone là một thông điệp hoặc marker cho biết identity đã bị xóa/vô hiệu hóa. Nó giúp consumer cập nhật bản sao mà không cần suy luận từ việc một bản ghi không còn xuất hiện trong batch.

Ví dụ:

    CustomerDeactivated
    CustomerDeleted
    CustomerMerged

Các event này không nhất thiết mang toàn bộ dữ liệu cá nhân. Consumer chỉ nhận thông tin cần thiết để xử lý projection và các tham chiếu liên quan.

Không nên xóa mọi bản sao ngay lập tức nếu dữ liệu đó phải được giữ vì nghĩa vụ lưu trữ hoặc audit. Ngược lại, cũng không nên giữ dữ liệu cá nhân vô thời hạn chỉ vì thuận tiện cho báo cáo. Cần có retention và deletion policy phù hợp với domain và quy định áp dụng.

## 16. Schema evolution và hợp đồng tích hợp

Integration event hoặc API contract là một phần của ranh giới giữa các context. Khi nguồn thay đổi schema, consumer cũ có thể không hiểu payload mới.

Một contract ổn định cần:

- Event name hoặc type rõ ràng.
- Schema version.
- Event ID.
- Aggregate/entity source ID.
- Source version hoặc sequence nếu cần.
- Timestamp có ngữ nghĩa rõ.
- Field bắt buộc và field tùy chọn được định nghĩa.
- Chính sách cho enum hoặc giá trị chưa biết.
- Quy tắc tương thích ngược.

### Không giả định enum luôn đóng

Nguồn có thể bổ sung membership tier mới như DIAMOND. Consumer cũ chỉ biết BASIC, SILVER, GOLD và PLATINUM.

Nếu mapper dùng enum parsing trực tiếp rồi ném exception, một event mới có thể làm consumer dừng liên tục.

Có thể:

- Dùng unknown value có chủ đích.
- Lưu raw code ở integration layer rồi ánh xạ theo policy.
- Đưa event không hỗ trợ vào dead-letter queue nếu không thể xử lý an toàn.
- Cập nhật contract và consumer trước khi nguồn phát giá trị mới.

Không nên âm thầm ánh xạ một trạng thái không biết thành trạng thái có ý nghĩa khác. Nếu không thể hiểu semantics, cần từ chối hoặc quarantine event và báo vận hành.

### Anti-Corruption Layer

ACL chuyển mô hình bên ngoài thành ngôn ngữ nội bộ:

    External Contract
          |
          v
    Integration Adapter
          |
          | validate, normalize, translate
          v
    Local Reference Model
          |
          v
    Local Application / Domain

ACL có thể đổi tên field, chuẩn hóa mã, ánh xạ enum, xử lý version và loại bỏ dữ liệu không cần thiết. Nó giúp thay đổi từ hệ thống nguồn không lan sâu vào domain tiêu thụ.

## 17. Không chia sẻ database hoặc Entity class giữa các context

Một shortcut thường gặp là cho hai bounded context cùng đọc/ghi một database table hoặc dùng chung một JPA Entity class.

Cách này tạo coupling:

- Một context đổi cột có thể làm context khác hỏng.
- Quy tắc validation của context này ảnh hưởng context kia.
- Hai context có thể cùng ghi một dữ liệu nhưng không thống nhất quyền sở hữu.
- Migration trở nên khó phối hợp.
- Mô hình domain của hai context bị ép giống nhau.

Nếu cần chia sẻ dữ liệu, hãy chia sẻ contract hoặc integration event. Mỗi context map sang mô hình cục bộ phù hợp với ngôn ngữ và use case của nó.

Có thể dùng chung thư viện kỹ thuật như serializer, client hoặc schema tooling, nhưng không nên dùng một shared domain model để giả định hai context có cùng semantics.

## 18. Xử lý khi nguồn dữ liệu không sẵn sàng

Một context phụ thuộc vào API hoặc event stream bên ngoài cần định nghĩa hành vi khi nguồn gặp sự cố.

### Với synchronous lookup

Cần có:

- Timeout ngắn và phù hợp use case.
- Retry có giới hạn cho lỗi transient.
- Circuit breaker để tránh tạo tải dây chuyền.
- Fallback nếu nghiệp vụ cho phép.
- Telemetry và correlation ID.
- Phân biệt timeout với business rejection.

Không retry mọi lỗi. HTTP 400 hoặc business rejection thường không trở nên thành công chỉ bằng cách gửi lại. Timeout cũng có thể xảy ra sau khi nguồn đã xử lý command; với thao tác ghi cần idempotency key.

### Với asynchronous replica

Cần có:

- Retry khi consumer gặp lỗi tạm thời.
- Dead-letter queue hoặc quarantine cho message không xử lý được.
- Cơ chế replay.
- Idempotent consumer.
- Version/gap detection.
- Reconciliation định kỳ.
- Alert khi consumer lag vượt SLA.

### Quyết định fallback theo use case

Ví dụ:

| Use case | Nguồn gián đoạn | Hành vi có thể chọn |
|---|---|---|
| Hiển thị tên khách hàng | Customer API không phản hồi | Dùng local copy gần nhất và đánh dấu dữ liệu cũ |
| Đặt hàng | Pricing không xác nhận được giá | Tạm dừng hoặc yêu cầu thử lại |
| Giữ hàng | Inventory không phản hồi | Không tự coi bản sao tồn kho là reservation thành công |
| Tra cứu mã quốc gia | Reference dataset có sẵn | Tiếp tục dùng dataset đã version |
| Phê duyệt tín dụng | Credit service không phản hồi | Từ chối tạm thời hoặc đưa vào quy trình chờ theo policy |

Fallback phải được chuyên gia nghiệp vụ chấp nhận. Không nên để một catch-all exception âm thầm dùng dữ liệu cũ cho mọi quyết định.

## 19. Reconciliation: phát hiện và sửa sai lệch

Ngay cả khi dùng event, dữ liệu có thể lệch do lỗi consumer, bug mapping, mất message hoặc migration không đồng nhất. Reconciliation giúp so sánh bản sao với nguồn có thẩm quyền và phát hiện chênh lệch.

Một quy trình reconciliation có thể:

1. Chọn một tập identity hoặc partition.
2. Lấy snapshot từ nguồn.
3. So sánh sourceVersion và localVersion.
4. Phát hiện bản ghi thiếu, cũ hoặc đã bị xóa.
5. Cập nhật bản sao theo quy tắc an toàn.
6. Ghi audit và metric.
7. Tạo danh sách trường hợp cần xử lý thủ công.

Reconciliation không nên ghi ngược dữ liệu từ bản sao về nguồn một cách tự động. Nếu bản sao khác nguồn, nguồn có thẩm quyền thường là nơi quyết định. Nếu phát hiện nguồn sai, cần một use case sửa dữ liệu ở context sở hữu.

## 20. Quan sát sức khỏe của quá trình đồng bộ

Một local replica có thể tồn tại nhưng đã cũ hoặc thiếu dữ liệu. Vì vậy cần quan sát cả dữ liệu lẫn pipeline đồng bộ.

Một số metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| Consumer lag | Message còn chờ xử lý |
| Oldest event age | Tuổi của event cũ nhất chưa xử lý |
| Last successful sync | Lần đồng bộ thành công gần nhất |
| Source/local version gap | Chênh lệch version giữa nguồn và bản sao |
| Duplicate event count | Số event bị nhận lại |
| Out-of-order event count | Số event đến sai thứ tự |
| Dead-letter count | Số message không xử lý được |
| Reconciliation mismatch | Số bản ghi khác nguồn |
| Projection update latency | Thời gian từ source change đến local update |

Log nên có source entity ID, event ID, source version, correlation ID và kết quả xử lý. Tránh ghi toàn bộ payload chứa dữ liệu cá nhân nếu không cần thiết.

Alert nên gắn với freshness SLA của use case. Consumer lag 5 phút có thể không đáng lo với danh mục quốc gia, nhưng không chấp nhận được với dữ liệu cần cập nhật gần thời gian thực.

## 21. Ví dụ Java: cập nhật Customer reference projection

Sales cần giữ một phần thông tin khách hàng để tìm kiếm. Customer Management phát event chứa snapshot profile cần chia sẻ.

Model cục bộ:

    public record CustomerReference(
            CustomerId customerId,
            String displayName,
            String membershipTier,
            long sourceVersion,
            Instant sourceUpdatedAt,
            Instant receivedAt
    ) {}

Integration event:

    public record CustomerProfileChangedV1(
            UUID eventId,
            String customerId,
            String displayName,
            String membershipTier,
            long sourceVersion,
            Instant occurredAt
    ) {}

Consumer:

    @Transactional
    public void handle(CustomerProfileChangedV1 event) {
        if (inboxRepository.exists(event.eventId())) {
            return;
        }

        CustomerId id = new CustomerId(event.customerId());
        CustomerReference current =
                customerReferenceRepository.findById(id).orElse(null);

        if (current != null
                && current.sourceVersion() >= event.sourceVersion()) {
            inboxRepository.markProcessed(event.eventId());
            return;
        }

        CustomerReference reference = new CustomerReference(
                id,
                event.displayName(),
                event.membershipTier(),
                event.sourceVersion(),
                event.occurredAt(),
                clock.instant()
        );

        customerReferenceRepository.upsertIfNewer(reference);
        inboxRepository.markProcessed(event.eventId());
    }

Ví dụ trên minh họa ý tưởng. Inbox cần unique constraint cho event ID. Phương thức upsertIfNewer phải thực hiện phép so sánh version và cập nhật trong một thao tác nguyên tử ở database, chẳng hạn conditional upsert với điều kiện sourceVersion hiện tại nhỏ hơn version nhận vào. Chỉ đọc version rồi ghi ở hai thao tác riêng vẫn có race condition nếu hai consumer cập nhật cùng customer đồng thời. Với event snapshot, version thấp hơn hoặc bằng bản sao hiện tại có thể được bỏ qua. Với event delta, consumer cần phát hiện gap và không được bỏ qua thay đổi trung gian.

Projection này chỉ phục vụ nhu cầu của Sales. Nếu Sales muốn thay đổi membership tier, nó phải gửi command đến Customer Management thay vì cập nhật CustomerReference như một nguồn chính thức.

## 22. Ví dụ: Order giữ snapshot từ các context khác

Khi khách hàng đặt hàng, Order có thể cần thông tin từ Product Catalog, Pricing và Customer Management.

Trước khi tạo Order, Application có thể lấy dữ liệu cần thiết:

    productId
    productName
    unitPrice
    currency
    customerId
    deliveryAddress

Sau khi các thông tin được xác nhận, Order lưu snapshot:

    OrderLine
      productId
      productNameAtPurchase
      unitPriceAtPurchase
      currency

    Order
      customerId
      deliveryAddressAtConfirmation
      placedAt

Các snapshot này phục vụ lịch sử giao dịch. Nếu Product Catalog đổi tên sản phẩm hoặc khách hàng đổi địa chỉ sau khi đặt, Order cũ vẫn phản ánh đúng thông tin đã được chốt.

Tuy nhiên, nếu giá cần được bảo đảm trong một khoảng thời gian hoặc phải xác nhận với Pricing tại thời điểm đặt, application cần dùng một quote hoặc pricing decision có version/expiry rõ ràng. Không nên chỉ đọc một local copy cũ rồi coi giá đó là giá đã được chấp thuận.

## 23. Những sai lầm thường gặp

### Coi local copy là nguồn có thẩm quyền

Context tiêu thụ tự sửa bản sao rồi dùng nó để quyết định dữ liệu mà context khác sở hữu. Điều này tạo ra nhiều nguồn sự thật.

### Sao chép toàn bộ Aggregate bên ngoài

Tăng coupling, lưu dư dữ liệu và khiến mô hình của context tiêu thụ phụ thuộc cấu trúc nội bộ của nguồn.

### Dùng bản sao cũ cho quyết định quan trọng

Tồn kho, hạn mức hoặc trạng thái thanh toán có thể thay đổi đồng thời. Cần xác nhận tại context sở hữu.

### Không phân biệt snapshot với replica

Snapshot lịch sử bị refresh theo dữ liệu hiện tại sẽ làm sai ý nghĩa giao dịch quá khứ.

### Không xử lý event trùng

Consumer có thể cộng điểm, gửi thông báo hoặc tạo bản ghi nhiều lần.

### Không xử lý event sai thứ tự

Bản sao có thể bị ghi đè bởi một event cũ. Cần version hoặc sequence.

### Bỏ qua event delta bị thiếu

Một thay đổi trung gian bị bỏ qua có thể làm state sai vĩnh viễn. Phải phát hiện gap và replay/reconcile.

### Chia sẻ database hoặc JPA Entity

Một context thay đổi schema có thể làm context khác hỏng và quyền sở hữu không còn rõ.

### Không có freshness SLA

Không ai biết bản sao được phép cũ bao lâu và khi nào cần cảnh báo.

### Đồng bộ không có checkpoint hoặc tombstone

Batch có thể bỏ sót thay đổi hoặc không nhận ra bản ghi đã bị xóa.

### Retry command ghi mà không có idempotency

Timeout có thể khiến cùng một yêu cầu được xử lý hai lần.

### Không có reconciliation

Một pipeline có vẻ hoạt động nhưng bản sao vẫn có thể thiếu hoặc sai dữ liệu trong thời gian dài.

## 24. Quy trình thiết kế bản sao cục bộ

Khi một context cần dữ liệu từ bên ngoài, có thể đi theo các bước:

1. **Xác định owner:** context nào có quyền quyết định và thay đổi dữ liệu?
2. **Xác định use case tiêu thụ:** cần dữ liệu để hiển thị, tìm kiếm, quyết định hay lưu lịch sử?
3. **Chọn hình thức:** ID reference, local replica, read projection hay historical snapshot?
4. **Chọn field tối thiểu:** chỉ sao chép dữ liệu cần thiết cho use case.
5. **Xác định freshness:** bản sao được phép cũ bao lâu?
6. **Chọn cơ chế sync:** synchronous API, event, batch, CDC hoặc cache.
7. **Định nghĩa contract:** identity, version, timestamp, schema evolution và unknown values.
8. **Thiết kế consumer:** idempotency, ordering, gap detection, retry và dead-letter.
9. **Xác định stale policy:** tiếp tục, gọi nguồn, tạm dừng hay yêu cầu xử lý thủ công.
10. **Thiết kế xóa và retention:** tombstone, merge, deletion và dữ liệu nhạy cảm.
11. **Thiết kế reconciliation:** phát hiện và sửa sai lệch theo nguồn có thẩm quyền.
12. **Quan sát vận hành:** freshness, lag, lỗi, version gap và mismatch.
13. **Kiểm thử:** duplicate, out-of-order, replay, source unavailable và schema compatibility.

## 25. Checklist tích hợp dữ liệu tham chiếu

Trước khi đưa local copy vào một Bounded Context, hãy kiểm tra:

- Nguồn có thẩm quyền đã được xác định chưa?
- Context tiêu thụ có biết mình chỉ là consumer không?
- Có thể chỉ lưu ID thay vì sao chép dữ liệu không?
- Dữ liệu cần dùng là reference, profile copy, decision input hay historical snapshot?
- Chỉ những field cần thiết mới được sao chép chưa?
- Local model có độc lập với Entity/schema nội bộ của nguồn không?
- Cơ chế đồng bộ có phù hợp với freshness requirement không?
- Source version và timestamp có đủ để nhận biết dữ liệu cũ không?
- Consumer có idempotent không?
- Event đến sai thứ tự hoặc bị thiếu có được phát hiện không?
- Delta event có cơ chế sequence/gap recovery không?
- Bản ghi bị xóa hoặc merge có tombstone không?
- Stale data policy đã được định nghĩa cho từng use case chưa?
- Quyết định quan trọng có được xác nhận tại context sở hữu không?
- Có retry, dead-letter, replay và reconciliation không?
- Có metric và alert cho freshness/consumer lag không?
- Dữ liệu nhạy cảm có được tối thiểu hóa và có retention policy không?
- Contract có versioning và kiểm thử tương thích không?

## 26. Kết luận

Dữ liệu tham chiếu và bản sao cục bộ giúp một Bounded Context sử dụng thông tin bên ngoài mà không phải phụ thuộc vào mọi lời gọi trực tiếp. Nhưng bản sao chỉ là biểu diễn phục vụ nhu cầu của context tiêu thụ; quyền sở hữu và quyền quyết định vẫn thuộc context có thẩm quyền.

Hãy chọn giữa tham chiếu bằng ID, local replica, read projection và historical snapshot theo mục tiêu của use case. Với dữ liệu thay đổi, xác định freshness SLA và cơ chế đồng bộ; với event, xử lý trùng lặp, sai thứ tự và gap; với quyết định quan trọng, xác nhận tại nguồn sở hữu; với giao dịch quá khứ, giữ snapshot theo thời điểm đã chốt.

Khi ranh giới ownership, contract và chính sách đồng bộ được làm rõ, các context có thể trao đổi dữ liệu mà không chia sẻ mô hình nội bộ, đồng thời giữ được tính độc lập và ý nghĩa nghiệp vụ của từng bounded context.
