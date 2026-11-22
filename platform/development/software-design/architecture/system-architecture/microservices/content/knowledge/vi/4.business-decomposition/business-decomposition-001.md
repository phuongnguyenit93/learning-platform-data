# Phân rã theo năng lực nghiệp vụ thay vì theo lớp kỹ thuật

## 1. Mục tiêu của bài học

Khi thiết kế microservices, câu hỏi quan trọng đầu tiên không phải là “chia code thành bao nhiêu repository?” mà là **“mỗi phần của hệ thống chịu trách nhiệm thực hiện năng lực nghiệp vụ nào?”**. Một hệ thống có nhiều tiến trình và nhiều API chưa chắc có ranh giới dịch vụ tốt. Nếu một thay đổi nhỏ của nghiệp vụ vẫn phải sửa, kiểm thử và phát hành đồng thời nhiều dịch vụ, hệ thống có thể đã trở thành *distributed monolith* (ứng dụng nguyên khối phân tán).

Sau bài học, người đọc có thể:

- Phân biệt phân rã theo lớp kỹ thuật với phân rã theo năng lực nghiệp vụ (*business capability*).
- Hiểu quan hệ giữa business capability, subdomain, bounded context và ứng viên microservice.
- Phác thảo bản đồ năng lực nghiệp vụ từ các luồng công việc thực tế.
- Đặt ranh giới dữ liệu, hành vi, trách nhiệm nhóm và hợp đồng giao tiếp.
- Nhận biết dấu hiệu một ranh giới gây coupling cao và cách thử nghiệm, điều chỉnh ranh giới trước khi tách hệ thống.

**Nguyên tắc cốt lõi:** một dịch vụ nên sở hữu một nhóm trách nhiệm nghiệp vụ gắn kết, có lý do thay đổi tương đối độc lập, cùng các quy tắc và dữ liệu cần thiết để thực hiện trách nhiệm ấy.

## 2. Hai cách chia hệ thống rất khác nhau

### 2.1. Phân rã theo lớp kỹ thuật: chia ngang

Giả sử có ứng dụng bán hàng với chức năng đặt hàng, thanh toán, quản lý sản phẩm.

Một cách chia sai hướng thường gặp là tạo các dịch vụ theo cấu trúc code hiện hữu:

```text
Ứng dụng web/mobile
        |
        v
+------------------------+
| Controller/API Service |
+------------------------+
        |
        v
+------------------------+
| Business Logic Service |
+------------------------+
        |
        v
+------------------------+
| Data Access Service    |
+------------------------+
        |
        v
    Shared Database
```

Ở đây ranh giới mạng chạy dọc theo tầng giao diện, xử lý nghiệp vụ và truy cập dữ liệu. Để hoàn thành bất kỳ tác vụ nào, yêu cầu thường phải đi qua cả ba dịch vụ. Thêm quy tắc “không cho đặt hàng vượt số lượng tồn kho” có thể buộc chỉnh sửa API, tầng logic và tầng dữ liệu ở ba hệ thống khác nhau. Các thành phần có thể có repository và pipeline riêng nhưng **không có khả năng thay đổi nghiệp vụ độc lập**.

Hệ quả thường gặp:

- Một luồng nghiệp vụ tạo nhiều lời gọi mạng liên tiếp, tăng độ trễ và điểm lỗi.
- Mỗi dịch vụ trở thành điểm phụ thuộc chung của nhiều miền nghiệp vụ; sửa một lớp có thể ảnh hưởng hàng loạt chức năng.
- Nhóm khó xác định ai sở hữu trọn vẹn hành vi “đặt hàng thành công”.
- Thay đổi schema hoặc contract kỹ thuật lan qua nhiều dịch vụ.
- Khi một tầng chung gặp lỗi, phần lớn hệ thống mất khả năng phục vụ.
- Việc tách tiến trình làm tăng chi phí phân tán mà không tạo ra quyền tự chủ tương ứng.

**Lưu ý quan trọng:** controller, application service, domain model và repository vẫn là các lớp hữu ích **bên trong** một dịch vụ. Vấn đề nằm ở việc biến mỗi lớp kỹ thuật thành một microservice chung cho nhiều nghiệp vụ.

### 2.2. Phân rã theo năng lực nghiệp vụ: chia dọc

Một thiết kế khác gom hành vi, dữ liệu và trách nhiệm theo chức năng mà doanh nghiệp phải thực hiện:

```text
                   Web / Mobile
                        |
                   API Gateway/BFF
                        |
        +---------------+---------------+
        |               |               |
        v               v               v
+---------------+ +---------------+ +---------------+
| Catalog       | | Order         | | Payment       |
| - API         | | - API         | | - API         |
| - Rules       | | - Rules       | | - Rules       |
| - Data access | | - Data access | | - Data access |
| - Own data    | | - Own data    | | - Own data    |
+---------------+ +---------------+ +---------------+
        |                |                 |
        +---------- contract/API/event ---+
```

Mỗi khối tập trung vào một năng lực như quản lý danh mục, vòng đời đơn hàng hay xử lý thanh toán. Ở bên trong khối vẫn có thể áp dụng kiến trúc nhiều lớp, Clean Architecture hoặc Hexagonal Architecture. Điểm khác biệt là **ranh giới triển khai và sở hữu chạy quanh năng lực nghiệp vụ**, thay vì chạy ngang theo lớp code.

Phân rã theo năng lực không loại bỏ việc phối hợp giữa các dịch vụ. Một đơn hàng vẫn cần thông tin sản phẩm, tồn kho và thanh toán. Mục tiêu là khiến **phần lớn thay đổi và quy tắc cốt lõi của từng miền nằm trong một ranh giới rõ ràng**, còn giao tiếp xuyên ranh giới được thiết kế, đo lường và quản lý có chủ đích.

## 3. Business capability là gì?

*Business capability* mô tả **doanh nghiệp cần có khả năng làm điều gì** để tạo ra hoặc hỗ trợ giá trị. Nó tương đối ổn định so với tên team, công nghệ và sơ đồ tổ chức.

Ví dụ trong thương mại điện tử:

| Năng lực nghiệp vụ | Câu hỏi nó giải quyết | Quy tắc/dữ liệu thường liên quan |
|---|---|---|
| Quản lý danh mục | Sản phẩm nào có thể được giới thiệu và bán? | Mô tả, phân loại, trạng thái hiển thị |
| Định giá và khuyến mãi | Một mặt hàng có giá bán nào trong bối cảnh cụ thể? | Bảng giá, thời gian hiệu lực, điều kiện ưu đãi |
| Quản lý tồn kho | Có thể cam kết bao nhiêu hàng và giữ hàng cho ai? | Số lượng khả dụng, đặt giữ, giải phóng giữ hàng |
| Quản lý đơn hàng | Một yêu cầu mua hàng đang ở trạng thái nào? | Dòng hàng, trạng thái, chính sách hủy, lịch sử |
| Thu và hoàn tiền | Giao dịch tiền được ủy quyền, thu và hoàn ra sao? | Trạng thái giao dịch, idempotency, đối soát |
| Hoàn tất giao hàng | Đơn nào cần đóng gói, vận chuyển, bàn giao? | Lệnh giao hàng, kiện hàng, tracking |
| Hỗ trợ khách hàng | Yêu cầu hỗ trợ được tiếp nhận và xử lý thế nào? | Case, SLA, kết quả xử lý |

Đây là **bản đồ ứng viên**, không phải lời khuyên mặc định tạo đúng bảy dịch vụ. Một tổ chức nhỏ có thể gộp nhiều năng lực vào một deployable; một hệ thống lớn có thể tách sâu một năng lực thành nhiều bounded context vì mô hình hoặc nhu cầu vận hành khác biệt.

Không nên dùng “Java”, “REST”, “database”, “caching”, “controller” hoặc “repository” làm tên business capability: đó là công nghệ/cơ chế xây dựng hệ thống. Ngược lại, các năng lực hỗ trợ như quản lý danh tính, tìm kiếm hoặc gửi thông báo *có thể* cần dịch vụ riêng nếu chúng sở hữu quy tắc, SLA và vòng đời rõ ràng; đừng mặc nhiên phân loại tất cả là dịch vụ nghiệp vụ độc lập.

## 4. Phân biệt capability, subdomain, bounded context và microservice

Các khái niệm liên quan nhưng không đồng nhất:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Business capability** | Doanh nghiệp cần làm được gì | Xử lý thanh toán |
| **Subdomain** | Một phần không gian vấn đề nghiệp vụ, có kiến thức và quy tắc riêng | Thu tiền, hoàn tiền, đối soát |
| **Bounded context** | Ranh giới mà một mô hình, ngôn ngữ và quy tắc nhất quán có hiệu lực | Payment Context với mô hình Payment/Refund/Settlement rõ nghĩa |
| **Microservice** | Đơn vị phần mềm có hợp đồng, trách nhiệm vận hành và khả năng triển khai độc lập | Payment Service triển khai và lưu dữ liệu thuộc Payment Context |
| **Team ownership** | Nhóm chịu trách nhiệm quyết định, vận hành và chất lượng một ranh giới | Nhóm Payments quản lý Payment Service |

Một capability có thể gồm nhiều subdomain; một bounded context có thể hiện thực một hoặc một phần capability; một microservice có thể bao phủ một bounded context hoặc một phạm vi nhỏ hơn khi có lý do rõ. Quan hệ **không bắt buộc 1:1**.

Ví dụ, “đơn hàng” trong Order Context là cam kết mua hàng và vòng đời đơn; “đơn hàng” trong Shipping Context có thể chỉ là yêu cầu giao hàng cùng địa chỉ nhận và mã tham chiếu. Việc hai context đều dùng từ *Order* không buộc chúng cùng truy cập một bảng hoặc dùng chung một class `Order`. Mỗi context sở hữu cách diễn giải cần cho trách nhiệm của mình.

**Bằng chứng tốt cho một bounded context** là ranh giới ngôn ngữ và quy tắc: chuyên gia nghiệp vụ ở hai miền định nghĩa một khái niệm khác nhau, thay đổi theo nhịp khác nhau, hoặc cần bảo vệ bất biến dữ liệu riêng. Việc có hai bảng hoặc hai package khác nhau chưa đủ để chứng minh cần hai context.

## 5. Cách tìm ranh giới từ hoạt động nghiệp vụ

### Bước 1 — Chọn hành trình tạo giá trị

Bắt đầu bằng luồng người dùng hoặc tác vụ kinh doanh, chẳng hạn:

- Khách tìm sản phẩm và xem giá.
- Khách tạo đơn và giữ hàng.
- Khách thanh toán, nhận xác nhận.
- Nhân viên kho đóng gói và giao hàng.
- Khách yêu cầu hủy, hoàn tiền hoặc trả hàng.

Mô tả **người thực hiện, mục đích, điều kiện bắt đầu, kết quả và trường hợp thất bại**. Tránh bắt đầu bằng danh sách class, endpoint hoặc bảng dữ liệu.

### Bước 2 — Tìm hành vi và quyết định nghiệp vụ

Với mỗi hành trình, hỏi:

- Quy tắc nào quyết định một yêu cầu được chấp nhận/từ chối?
- Ai là nguồn xác thực cuối cùng cho một trạng thái?
- Điều gì thay đổi khi chính sách kinh doanh thay đổi?
- Dữ liệu nào cần được cập nhật nhất quán trong một giao dịch?
- Hệ thống nào khác cần biết kết quả, nhưng không cần sở hữu nó?

Ví dụ, “không bán quá tồn kho khả dụng” thuộc năng lực quản lý tồn kho; “đơn hàng được phép hủy đến giai đoạn nào” thuộc quản lý đơn; “không ghi nhận thu tiền hai lần cho cùng một yêu cầu” thuộc xử lý thanh toán.

### Bước 3 — Lập bản đồ năng lực

Vẽ các năng lực ở cấp lớn trước, rồi chia nhỏ nếu có sự khác biệt thực sự về luật, dữ liệu, ownership hoặc nhịp thay đổi. Dùng tên mang nghĩa nghiệp vụ: `OrderManagement`, `InventoryManagement`, `PaymentProcessing`. Tránh `ControllerService`, `DatabaseService`, `CommonBusinessService`.

Bản đồ nên phân biệt **năng lực cốt lõi** tạo khác biệt cạnh tranh, **năng lực hỗ trợ** và **năng lực phổ biến**. Việc phân loại này giúp quyết định nơi nên đầu tư custom logic và nơi có thể dùng nền tảng hoặc sản phẩm sẵn có.

### Bước 4 — Dùng workshop sự kiện nghiệp vụ

Có thể dùng *event storming* cùng product owner, người vận hành và kỹ sư để tìm chuỗi:

```text
[Khách đặt hàng]
      ↓ command
(Tạo đơn hàng)
      ↓ business event
<Đơn hàng đã được tạo>
      ↓ policy
(Kiểm tra/giữ tồn kho)
      ↓ event
<Hàng đã được giữ> hoặc <Giữ hàng thất bại>
      ↓ ...
```

Các sự kiện theo ngôn ngữ quá khứ như “Đơn đã được tạo”, “Thanh toán được ủy quyền” thể hiện sự thật đã xảy ra. Command như “Tạo đơn”, “Giữ hàng” là yêu cầu hành động, có thể bị từ chối. Sự khác biệt này hữu ích khi thiết kế hợp đồng giữa các miền.

Chú ý những vùng xuất hiện **từ ngữ, quy tắc, chủ sở hữu và bất biến riêng**. Đó là đầu mối tìm bounded context; chưa cần biến mỗi sự kiện, bước xử lý hoặc aggregate thành một dịch vụ.

### Bước 5 — Kiểm tra mức độ kết dính và phụ thuộc

Nhóm các hành vi thường cần thay đổi cùng nhau (*high cohesion*), và xem xét tách các nhóm có thể phát triển độc lập (*low coupling*). Thu thập dữ liệu từ công việc thực tế: ticket, lịch sử commit, các lần release đồng bộ, lỗi do thay đổi contract, thời gian chờ nhóm khác.

Ví dụ: nếu 80% thay đổi chính sách giảm giá luôn yêu cầu cập nhật cả `PromotionService` và `PricingService`, cần tìm hiểu hai phần đang thuộc cùng một năng lực hay hợp đồng bị thiết kế sai. Không tự động gộp chúng: có thể vấn đề nằm ở logic trùng lặp hoặc thiếu mô hình giá thống nhất.

### Bước 6 — Quyết định ranh giới nhất quán dữ liệu

Các quy tắc bắt buộc đúng **ngay trong một giao dịch** nên được đặt gần nhau về ownership và dữ liệu. Đừng tách hai thao tác cần cùng một invariant chỉ vì chúng dùng hai bảng.

Ví dụ “không để một giao dịch thu tiền được ghi nhận hai lần” nên được đảm bảo trong phạm vi Payment bằng khóa idempotency và transaction phù hợp; không dựa vào lời gọi đồng bộ sang ba dịch vụ để giữ invariant đó. Những quy trình nhiều miền như đặt hàng → giữ tồn → thanh toán thường được mô hình hóa bằng trạng thái tiến trình và cơ chế phối hợp, chứ không kỳ vọng một giao dịch database ACID bao trùm mọi dịch vụ.

### Bước 7 — Đánh giá khả năng vận hành

Một ranh giới nghiệp vụ hợp lý vẫn có thể **chưa nên triển khai thành microservice** nếu tổ chức thiếu năng lực giám sát, tự động hóa triển khai, quản lý hợp đồng hoặc đội ngũ sở hữu rõ. Bắt đầu bằng module tách biệt trong modular monolith là bước hợp lý để kiểm chứng mô hình.

## 6. Ví dụ đối chiếu: thay đổi chính sách hoàn tiền

Yêu cầu mới: “Cho phép hoàn một phần tiền cho đơn đủ điều kiện, đồng thời cập nhật trạng thái đơn và gửi thông báo”.

**Nếu chia theo lớp kỹ thuật:**

1. `ApiService` phải thêm endpoint.
2. `BusinessLogicService` phải thêm điều kiện tính hoàn tiền.
3. `DatabaseService` phải thêm truy vấn/cập nhật.
4. Có thể còn phải đồng bộ schema chung và phát hành cả ba thành phần.

Trách nhiệm nghiệp vụ bị dàn ngang; khó phân biệt lỗi do rule, hợp đồng hay truy cập dữ liệu.

**Nếu chia theo năng lực:**

1. `Order` xác định trạng thái đơn và điều kiện nghiệp vụ để yêu cầu hoàn, có thể phát ra một yêu cầu hoàn tiền qua contract chính thức.
2. `Payment` sở hữu hành vi hoàn tiền, tương tác với cổng thanh toán, trạng thái hoàn, idempotency và đối soát.
3. `Order` ghi nhận kết quả hoàn vào trạng thái đơn phù hợp sau khi nhận kết quả tin cậy.
4. `Notification` chỉ nhận sự kiện đã được công bố và gửi thông báo, không tự quyết định số tiền được hoàn.

Thay đổi sâu trong xử lý gateway có thể chỉ cần phát hành Payment; thay đổi quy tắc cho phép hủy/hoàn có thể tập trung ở Order hoặc context chính sách được xác định rõ. Contract giữa các miền vẫn có thể thay đổi, nhưng sự phụ thuộc được **chủ động thiết kế và có chủ sở hữu**.

Không nên bắt đầu bằng cách áp đặt rằng mọi nghiệp vụ liên quan hoàn tiền đều phải nằm ở Payment. Quy tắc “đơn có đủ điều kiện được hoàn?” và “thực thi chuyển tiền hoàn như thế nào?” có thể thuộc các context khác nhau. Nên quyết định bằng ngôn ngữ chuyên gia và quyền sở hữu invariant.

## 7. Dữ liệu thuộc về năng lực nào?

Quyền sở hữu dữ liệu là một phép thử ranh giới rất quan trọng.

Một thiết kế điển hình:

| Context | Sở hữu dữ liệu | Context khác cần thông tin thì làm gì? |
|---|---|---|
| Catalog | Sản phẩm, mô tả, phân loại | Gọi API công khai hoặc giữ bản sao chỉ đọc theo sự kiện |
| Order | Đơn hàng, dòng hàng, trạng thái, lịch sử đơn | Gọi Order API hoặc tiêu thụ `OrderPlaced`, `OrderCancelled` |
| Inventory | Tồn khả dụng, reservation | Gọi contract giữ/trả hàng hoặc nhận `InventoryReserved` |
| Payment | Payment attempt, authorization, refund | Nhận event kết quả và dùng ID tham chiếu; không đọc trực tiếp bảng Payment |
| Fulfillment | Lệnh xử lý kho, vận đơn | Tiêu thụ trạng thái đơn được xác nhận theo hợp đồng |

**Nguyên tắc:** một dịch vụ sở hữu schema và quy tắc ghi dữ liệu của mình; dịch vụ khác không ghi trực tiếp vào bảng thuộc sở hữu ấy. Có thể chia sẻ cùng hạ tầng database trong giai đoạn chuyển tiếp, nhưng cần giữ quyền sở hữu logic, tài khoản/truy cập và kế hoạch giảm phụ thuộc rõ ràng. “Database per service” là một mục tiêu về **quyền sở hữu và cô lập**, không nhất thiết bắt buộc ngay lập tức mỗi dịch vụ chạy trên một máy database vật lý khác nhau.

Tránh tạo một `SharedDataService` phục vụ CRUD chung cho mọi miền: nó dễ tái tạo lớp dữ liệu tập trung và khiến mọi chức năng phụ thuộc vào contract kỹ thuật dùng chung.

Khi cần báo cáo nhiều miền, cân nhắc read model/projection cập nhật từ event, API composition giới hạn số lần gọi hoặc kho dữ liệu phân tích. Cần công khai độ trễ cập nhật và hành vi nhất quán của từng lựa chọn. Không ngầm dùng truy vấn JOIN trực tiếp xuyên schema do các dịch vụ khác sở hữu.

## 8. Luồng đặt hàng đi qua nhiều năng lực như thế nào?

Tách theo capability **không có nghĩa** một hành trình phải thuộc duy nhất một dịch vụ. Một giao dịch thương mại có thể cần nhiều năng lực phối hợp:

```text
Khách hàng
   |
   v
Order: tạo đơn PENDING
   |
   v
Inventory: yêu cầu giữ hàng
   | thành công / thất bại
   v
Payment: yêu cầu ủy quyền thanh toán
   | thành công / thất bại
   v
Order: CONFIRMED hoặc CANCELED
   |
   v
Notification: thông báo kết quả
```

Đây là luồng đơn giản hóa để giải thích ranh giới. Trong thực tế cần xác định thứ tự phù hợp với nghiệp vụ (giữ hàng trước hay sau ủy quyền), timeout, tồn kho hết hạn giữ, cách hủy/hoàn và khả năng lỗi ở mọi bước.

Một cách triển khai là *saga*: mỗi dịch vụ thực hiện transaction cục bộ của mình; khi bước sau thất bại, tiến trình thực hiện hành động bù trừ phù hợp (thí dụ giải phóng reservation, hủy authorization). Có thể dùng **orchestration** khi một điều phối viên quản lý trạng thái toàn luồng, hoặc **choreography** khi các context phản ứng theo event. Không có cách nào tự động bảo đảm nhất quán tuyệt đối; cần chính sách rõ cho trạng thái đang xử lý và những lỗi có thể khôi phục.

Những yêu cầu kỹ thuật tối thiểu cần tính đến:

- **Idempotency:** cùng command/event được xử lý lặp lại không gây tác động nghiệp vụ lặp (chẳng hạn thu tiền hai lần).
- **Retry và timeout có giới hạn:** retry an toàn, có backoff; phân biệt lỗi tạm thời và lỗi nghiệp vụ vĩnh viễn.
- **Reliable event publishing:** cân nhắc transactional outbox để tránh ghi database thành công nhưng sự kiện không được phát.
- **Inbox/deduplication:** người tiêu thụ xử lý sự kiện lặp do cơ chế giao nhận ít nhất một lần.
- **Correlation/tracing:** truyền correlation ID để theo dõi toàn bộ tiến trình.
- **State reconciliation:** có khả năng đối soát giao dịch treo giữa các context.

Một event contract minh họa:

```json
{
  "eventId": "evt-2026-000184",
  "eventType": "PaymentAuthorized",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T10:00:00Z",
  "correlationId": "checkout-abc123",
  "payload": {
    "orderId": "ord-981",
    "paymentId": "pay-407",
    "amount": 125000,
    "currency": "VND"
  }
}
```

Đây là **dữ liệu ví dụ**, không phải schema bắt buộc. Trường `eventId` hỗ trợ chống xử lý lặp, `correlationId` hỗ trợ quan sát luồng, `schemaVersion` giúp quản lý tương thích. Chỉ phát dữ liệu cần thiết cho hợp đồng, tránh gửi toàn bộ entity hoặc thông tin nhạy cảm không phục vụ người nhận.

## 9. Khi nào tách thành hai microservices, khi nào giữ cùng một ranh giới?

Để tránh “một microservice cho mỗi bảng”, đánh giá các tín hiệu sau:

| Tín hiệu | Thiên về giữ cùng ranh giới | Thiên về cân nhắc tách |
|---|---|---|
| Quy tắc và invariant | Nhiều thao tác cần transaction tức thời | Quy tắc tách biệt, chỉ trao đổi kết quả rõ nghĩa |
| Lịch sử thay đổi | Thường phải sửa và release cùng nhau vì cùng một chính sách | Có nhu cầu thay đổi/phát hành độc lập thực sự |
| Mô hình ngôn ngữ | Thuật ngữ và ý nghĩa thống nhất | Cùng thuật ngữ có ý nghĩa khác, nhiều rule xung đột |
| Ownership | Cùng một nhóm chịu trách nhiệm toàn bộ, không có nhu cầu tách | Nhóm/domain owner riêng với trách nhiệm vận hành rõ |
| Hiệu năng và tải | Mọi phần có tải tương tự, tương tác rất thường xuyên | Một phần có tải hoặc yêu cầu cô lập rất khác |
| Tương tác dữ liệu | Nhiều JOIN và transaction xuyên ranh giới | Giao tiếp qua hợp đồng nhỏ, ít yêu cầu đồng bộ |
| Vận hành | Năng lực monitor/release/incident còn hạn chế | Có automation, observability và on-call phù hợp |

Không chấm điểm cơ học theo số dấu tick. Quy tắc nhất quán dữ liệu, yêu cầu pháp lý, chi phí mạng hoặc khả năng hỗ trợ sản xuất có thể quan trọng hơn lợi ích phát hành độc lập.

**Độ lớn dịch vụ (granularity)** là một quyết định cần điều chỉnh qua thực nghiệm. Một dịch vụ quá lớn có thể cản trở quyền tự chủ; quá nhỏ tạo giao tiếp dày đặc, nhiều contract và sự cố liên miền. Ranh giới tốt là ranh giới phù hợp với quy tắc, vòng đời và khả năng vận hành hiện tại.

## 10. Định lượng mức độ kết dính và liên kết

Phân rã theo business capability không chỉ dựa vào sơ đồ đẹp. Có thể thu thập chỉ số trong vài chu kỳ thay đổi:

**Change coupling.** Trong 90 ngày giả định, có bao nhiêu yêu cầu nghiệp vụ buộc sửa đồng thời cả Order và Payment? Phân biệt “cùng một tính năng lớn” với “sửa một rule nhỏ nhưng bắt buộc sửa contract nhiều nơi”. Tỷ lệ thay đổi đồng thời cao liên tục là tín hiệu cần khảo sát ranh giới.

**Deployment coupling.** Bao nhiêu lần một service phải chờ service khác được phát hành đúng version? Mục tiêu triển khai độc lập bị suy yếu khi từng release cần đồng bộ nhiều nhóm.

**Runtime coupling.** Đếm số lời gọi đồng bộ, fan-out, vòng phụ thuộc, timeout và p95/p99 của một hành trình. Nếu mỗi request làm phát sinh hàng chục lời gọi giữa các dịch vụ cho cùng một tác vụ, cần xem lại nơi đặt hành vi hoặc xây dựng read model.

**Data coupling.** Tìm các SQL JOIN xuyên schema, cập nhật dữ liệu chéo, direct table reads, transaction phân tán và các field bị sao chép mà không có owner rõ.

**Incident coupling.** Một lỗi ở một dịch vụ khiến bao nhiêu năng lực khác ngừng hoạt động? Kiểm tra deadline, circuit breaker, bulkhead, fallback và khả năng phục vụ suy giảm có kiểm soát.

**Team coupling.** Bao nhiêu nhóm phải họp/phê duyệt để hoàn thành một thay đổi trong một capability? Ownership không rõ khiến boundary kỹ thuật thiếu hiệu quả.

Ví dụ giả định: sau khi tách Payment, lead time Payment giảm từ 6 ngày còn 2 ngày, nhưng p95 checkout tăng từ 500 ms lên 1.600 ms và 30% giao dịch phát sinh retry. Đây là kết quả có đánh đổi; cần xem lại contract, giao tiếp đồng bộ, tính nhất quán và chi phí trước khi coi việc tách là thành công. Không dùng số lượng microservices làm KPI kết quả.

## 11. Lộ trình phân rã an toàn từ monolith

Không cần tách toàn bộ hệ thống trong một lần. Một lộ trình có thể tiến hành như sau:

### Giai đoạn A — Xác lập ranh giới trong code

Từ monolith, tạo các module nghiệp vụ tách biệt như `catalog`, `orders`, `inventory`, `payments`, mỗi module có API nội bộ rõ và quy tắc không truy cập thẳng private package hoặc bảng dữ liệu của module khác. Giữ các transaction cần nhất quán trong phạm vi thích hợp.

Sơ đồ:

```text
Monolith deployable
├── Catalog module
├── Order module
├── Inventory module
└── Payment module
    ├── Application
    ├── Domain
    └── Infrastructure
```

Đây là **modular monolith**: phân rã ở mức tổ chức mã nguồn và mô hình, chưa chịu toàn bộ chi phí mạng. Có thể đo mức độ phụ thuộc module và mức độc lập của thay đổi trước khi quyết định tách tiến trình.

### Giai đoạn B — Xác định hợp đồng và ownership

Chỉ ra API/command/event được phép gọi, hệ thống sở hữu từng dữ liệu, mức nhất quán, phiên bản contract và chiến lược xử lý lỗi. Với dữ liệu đang ở một schema chung, giảm dần truy cập chéo và thay bằng interface công khai trong code trước.

### Giai đoạn C — Chọn một năng lực để tách thử

Ưu tiên capability có ranh giới rõ, tác động kiểm soát được, lợi ích vận hành đo được, có owner và khả năng rollback. Các chức năng tương đối độc lập có thể dễ thử hơn một quy trình tiền tệ liên quan nhiều invariant. Tuy nhiên đừng chọn thứ “dễ tách” nếu hoàn toàn không kiểm chứng được giả thuyết giá trị.

Có thể áp dụng *Strangler Fig Pattern*: chuyển dần một nhóm request qua route/gateway đến hệ thống mới, giữ đường cũ trong giai đoạn chuyển tiếp. Đồng bộ dữ liệu cần thiết kế rõ nguồn sự thật; tránh **dual write không điều phối** khiến dữ liệu mới/cũ lệch nhau khi một bên ghi thất bại.

### Giai đoạn D — Đo, mở rộng hoặc dừng

So sánh cùng điều kiện trước/sau: lead time, deployment independence, p95 giao dịch, error rate, sự cố, chi phí và công sức phối hợp. Nếu tách dịch vụ không cải thiện vấn đề đã xác định hoặc làm hệ thống thiếu ổn định, có thể giữ modular monolith và điều chỉnh boundary.

### Giai đoạn E — Lặp có chọn lọc

Khi ranh giới đầu tiên hoạt động ổn định, cập nhật bản đồ capability và tiếp tục với ứng viên tiếp theo. Tránh giả định rằng tất cả module nội bộ cuối cùng đều phải trở thành microservice.

## 12. Những sai lầm thường gặp

**Một service cho mỗi entity hoặc bảng.** `ProductService`, `ProductPriceService`, `ProductTagService` có thể là những service hợp lý trong bối cảnh đặc biệt, nhưng nếu hầu hết use case cần sửa/đọc tất cả để có một đối tượng có nghĩa, granularity có thể quá nhỏ.

**Dùng tên team hoặc sơ đồ tổ chức làm domain map.** Sơ đồ phòng ban có thể đổi thường xuyên; capability nên dựa trên trách nhiệm nghiệp vụ. Team ownership vẫn quan trọng, nhưng cần làm rõ sau khi hiểu domain.

**Xem CRUD là năng lực nghiệp vụ.** Một service “tạo/sửa/xóa bản ghi” chưa cho biết nó bảo vệ quy tắc nào. Tên service và API nên phản ánh hành vi như `reserveStock`, `authorizePayment`, `cancelOrder` khi chúng thực sự là command nghiệp vụ.

**Các dịch vụ cùng thao tác một database.** Việc chia API mà giữ mọi bảng và transaction chung khiến ownership mơ hồ, schema biến thành hợp đồng không chính thức. Cần quy định nguồn sự thật và giảm direct access.

**Dùng một mô hình dữ liệu chung cho mọi context.** Shared library chứa toàn bộ domain entities làm thay đổi nội bộ lan truyền. Chỉ chia sẻ những thành phần thật sự ổn định, có phiên bản và không chiếm quyền sở hữu mô hình của các miền khác.

**Tách vì khả năng scale mà chưa đo tải.** Có thể điểm nghẽn nằm ở index, cache, query hoặc pipeline, không phải ranh giới deploy. Microservices không tự làm yêu cầu nhanh hơn.

**Coi mọi giao tiếp là đồng bộ.** Chuỗi gọi từ Order → Inventory → Payment → Notification tạo độ trễ và lỗi dây chuyền. Chọn đồng bộ khi cần kết quả ngay; chọn event/asynchronous khi quy trình cho phép và có thiết kế trạng thái rõ.

**Lạm dụng event.** Không phải mọi cập nhật trường là một business event cần phát. Công bố sự kiện có ý nghĩa nghiệp vụ, định nghĩa người phát/người tiêu thụ, khả năng lặp và thay đổi schema.

**Tách trước khi hiểu quy tắc thất bại.** Các trường hợp thất bại, timeout, bù trừ và đối soát mới là phép thử khó nhất của ranh giới liên miền. Cần mô hình hóa sớm, nhất là thanh toán và tồn kho.

## 13. Checklist thiết kế ranh giới capability

- [ ] Tên ranh giới mô tả hành vi/năng lực nghiệp vụ, không chỉ lớp kỹ thuật hoặc CRUD.
- [ ] Có người chịu trách nhiệm nghiệp vụ và kỹ thuật cho ranh giới này.
- [ ] Có mô hình, thuật ngữ và quy tắc nhất quán trong phạm vi bounded context.
- [ ] Biết dữ liệu nào thuộc ownership của ranh giới và hệ thống khác được phép truy cập thế nào.
- [ ] Các invariant quan trọng có thể được bảo vệ mà không phụ thuộc vào transaction phân tán tùy tiện.
- [ ] Contract giữa các ranh giới có nghĩa nghiệp vụ, có phiên bản và chính sách lỗi.
- [ ] Đã xem xét coupling ở thay đổi code, triển khai, runtime, dữ liệu và tổ chức.
- [ ] Kích thước deployable phù hợp nhu cầu và năng lực vận hành, không chạy theo số lượng service.
- [ ] Có đường thử nghiệm từ modular monolith, chỉ số đo và chiến lược rollback khi tách.
- [ ] Luồng liên miền có idempotency, tracing, timeout và trạng thái thất bại rõ ràng.

## 14. Bài tập thực hành

Một nền tảng đặt lịch khám đang vận hành monolith với các bảng `Patient`, `Doctor`, `Appointment`, `Invoice`, `Notification`. Nhóm đề xuất tách thành năm microservices tương ứng năm bảng. Hệ thống phải xử lý những tác vụ sau:

1. Bệnh nhân tìm lịch trống và đặt hẹn.
2. Phòng khám đổi giờ làm việc của bác sĩ, các lịch hẹn bị ảnh hưởng cần được xử lý.
3. Bệnh nhân thanh toán hoặc hủy lịch, có thể phát sinh hoàn tiền.
4. Nhân viên gửi nhắc lịch và theo dõi trường hợp bệnh nhân vắng mặt.

Yêu cầu:

- Liệt kê các **business capabilities** có thể có, giải thích vì sao chúng không nhất thiết trùng với năm bảng.
- Đề xuất một bản đồ bounded context ở mức khái niệm, chỉ ra owner của quy tắc “không đặt hai người vào cùng một khung giờ”.
- Chọn một use case có **invariant cần nhất quán tức thời**, và một quy trình có thể phối hợp **bất đồng bộ**.
- Phác thảo API hoặc event giữa ít nhất hai context, nêu cách xử lý retry/idempotency.
- Nêu hai lý do nên **giữ modular monolith** trước, và điều kiện thực tế khiến việc tách một context thành microservice đáng giá.
- Đề xuất ít nhất ba phép đo trước/sau để xem ranh giới có làm giảm coupling và cải thiện giá trị hay không.

Không có một đáp án duy nhất: ưu tiên quyết định có cơ sở từ quy tắc nghiệp vụ, dữ liệu, tải và tổ chức. Không đánh giá thiết kế chỉ bằng việc có bao nhiêu dịch vụ.

## 15. Ghi nhớ

- **Ranh giới nghiệp vụ** gom hành vi, quy tắc và dữ liệu có ý nghĩa chung; **lớp kỹ thuật** là cách tổ chức triển khai bên trong ranh giới đó.
- Business capability, subdomain, bounded context và microservice có liên hệ nhưng không đồng nghĩa và không bắt buộc ánh xạ 1:1.
- Chọn boundary dựa trên sự kết dính, tính độc lập thay đổi, nhất quán dữ liệu và khả năng vận hành.
- Luồng nghiệp vụ có thể đi qua nhiều service, nhưng mỗi service phải có ownership rõ và contract có nghĩa; các bước xuyên ranh giới cần thiết kế trạng thái, lỗi và bù trừ.
- Modular monolith là môi trường hữu ích để xác thực ranh giới trước khi nhận thêm độ phức tạp phân tán.

**Mục tiêu của phân rã là giảm sự phụ thuộc không cần thiết giữa các thay đổi nghiệp vụ, chứ không phải tối đa hóa số dịch vụ được tạo ra.**
