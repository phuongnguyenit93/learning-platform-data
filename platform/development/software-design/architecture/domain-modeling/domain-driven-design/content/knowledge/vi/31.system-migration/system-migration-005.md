# Thiết lập ranh giới ngữ cảnh và lớp chống xâm lấn quanh hệ thống cũ

Chuyển đổi một hệ thống cũ (legacy system) theo Domain-Driven Design (DDD) không chỉ là thay framework, database hoặc viết lại màn hình. Mục tiêu là tách dần năng lực nghiệp vụ thành những Bounded Context có mô hình, ngôn ngữ và quyền sở hữu dữ liệu rõ ràng. Trong thời gian chuyển đổi, hệ thống mới vẫn phải giao tiếp với hệ thống cũ. Nếu để mô hình legacy lan trực tiếp vào domain model mới, nhóm sẽ mang theo tên gọi, trạng thái, cấu trúc dữ liệu và giới hạn cũ sang kiến trúc mới.

Anti-Corruption Layer (ACL) tạo một ranh giới dịch thuật giữa hai mô hình. Nó chuyển request, response, event, mã trạng thái và ý nghĩa dữ liệu của hệ thống cũ thành ngôn ngữ của Bounded Context mới; đồng thời chuyển lệnh của context mới thành hợp đồng mà legacy có thể hiểu. ACL giúp mô hình mới bảo vệ invariant và thuật ngữ của chính nó trong khi hai hệ thống cùng tồn tại.

Bài học này trình bày cách xác định ranh giới cần tách, áp dụng chiến lược Strangler Fig, thiết kế ACL quanh legacy, quản lý quyền sở hữu dữ liệu trong giai đoạn song hành, chuyển dữ liệu và lưu lượng an toàn, kiểm thử tương thích, cutover và chuẩn bị rollback. Ví dụ xuyên suốt dùng một hệ thống bán hàng cũ đang quản lý đơn hàng, tồn kho và thanh toán trong một ứng dụng nguyên khối.

## 1. Vì sao cần ranh giới khi chuyển đổi legacy?

Hệ thống cũ thường tích lũy nhiều năm quyết định kỹ thuật và nghiệp vụ:

- Một bảng hoặc class được nhiều module dùng chung.
- Một trường trạng thái có nhiều ý nghĩa tùy màn hình hoặc quy trình.
- Mã sản phẩm, mã khách hàng hoặc mã lỗi được dùng như quy ước ngầm.
- Quy tắc nghiệp vụ nằm rải rác trong stored procedure, batch job, trigger và ứng dụng.
- Một thay đổi ở module này có thể làm hỏng module khác vì phụ thuộc schema.
- Các hệ thống tích hợp hiểu cấu trúc dữ liệu nội bộ thay vì hợp đồng ổn định.

Viết một hệ thống mới mà không nhận diện những phụ thuộc này có thể tạo ra một phiên bản mới của chính các vấn đề cũ. Đặc biệt, nếu domain model mới dùng trực tiếp DTO, enum, bảng hoặc thuật ngữ legacy, mô hình mới sẽ khó thay đổi độc lập.

### 1.1. Ví dụ: một trạng thái có nhiều nghĩa

Giả sử legacy có cột ORDER_STATUS với các giá trị:

| Giá trị cũ | Cách các màn hình legacy đang diễn giải |
|---|---|
| N | Đơn mới tạo, chưa gửi |
| P | Đã gửi yêu cầu đặt hàng |
| A | Đã được chấp nhận hoặc đã giữ hàng, tùy luồng |
| C | Hoàn tất hoặc đã đóng |
| X | Hủy hoặc từ chối |

Context Ordering mới có thể cần các trạng thái rõ hơn như DRAFT, PLACED, AWAITING_CONFIRMATION, CONFIRMED, FULFILLED, CANCELLED và REJECTED.

Không nên đổi tên enum cũ rồi dùng nó làm enum mới. Cần tìm hiểu sự kiện nào làm trạng thái thay đổi, ý nghĩa của từng mã trong từng quy trình, và cách xử lý trường hợp một mã cũ đại diện cho nhiều tình huống. ACL là nơi chuyển đổi những khác biệt đã được xác minh.

### 1.2. Legacy không nhất thiết là một ứng dụng duy nhất

Một “hệ thống cũ” có thể gồm ứng dụng monolith, database, batch, file trao đổi, job scheduler, báo cáo và các consumer bên ngoài. Trước khi thay thế một capability, cần biết ai đang đọc và ghi dữ liệu, ai phụ thuộc vào hành vi hiện tại, và quy trình nào sẽ bị ảnh hưởng.

## 2. Xác định Bounded Context trước khi chọn cách di trú

Không nên bắt đầu bằng câu hỏi “Tách service nào trước?” mà nên hỏi “Năng lực nghiệp vụ nào cần có mô hình và quyền sở hữu riêng?”. Bounded Context xác định phạm vi mà một mô hình và Ubiquitous Language có ý nghĩa nhất quán.

Với hệ thống bán hàng minh họa, có thể khám phá các context:

| Context ứng viên | Trách nhiệm nghiệp vụ | Dữ liệu có thẩm quyền |
|---|---|---|
| Ordering | Đặt hàng, xác nhận, hủy đơn | Đơn hàng và vòng đời đơn |
| Inventory | Quản lý tồn kho và giữ hàng | Số lượng, reservation |
| Payment | Ủy quyền, thu, hoàn tiền | Giao dịch thanh toán |
| Catalog | Thông tin sản phẩm và giá niêm yết | Danh mục sản phẩm |
| Shipping | Lập lệnh giao và theo dõi vận chuyển | Shipment và trạng thái giao |

Đây là các ranh giới ứng viên, cần được kiểm chứng với chuyên gia và luồng thực tế. Một module trong legacy không tự động tương ứng với một Bounded Context. Ngược lại, một Bounded Context mới có thể thay thế dần một phần logic đang nằm trong nhiều module cũ.

### 2.1. Tìm ranh giới từ quy tắc và quyền sở hữu

Với mỗi capability, hãy xác định:

1. Ai chịu trách nhiệm về kết quả nghiệp vụ?
2. Những invariant nào phải được bảo vệ?
3. Dữ liệu nào cần được thay đổi nguyên tử cùng nhau?
4. Thuật ngữ nào có ý nghĩa riêng trong capability?
5. Hệ thống nào hiện là nguồn có thẩm quyền?
6. Những consumer nào phụ thuộc vào dữ liệu hoặc hành vi hiện tại?
7. Có thể chuyển quyền sở hữu mà không cần di trú toàn bộ hệ thống không?

Ví dụ, Ordering có thể tham chiếu Sku và CustomerId nhưng không nên sở hữu số lượng tồn kho hoặc trạng thái thanh toán. Khi tách Inventory, context mới phải có quyền quyết định việc giữ hàng. Ordering chỉ gửi command và xử lý kết quả theo hợp đồng.

### 2.2. Dùng Context Map để nhìn thấy quan hệ

Context Map mô tả cách các Bounded Context kết nối. Trong giai đoạn di trú, một context mới thường là downstream của legacy cho tới khi nó tự sở hữu dữ liệu và quy tắc.

~~~mermaid
flowchart LR
    L[Legacy Sales System] -->|Legacy order API / tables| A[ACL]
    A --> O[New Ordering Context]
    O -->|Reserve command| I[New Inventory Context]
    I -->|Inventory events| O
    O -->|Payment request| P[Payment Context]
    P -->|Payment result| O
    O -->|Published order event| R[Reporting / Other Consumers]
~~~

Sơ đồ cần thể hiện rõ chiều dữ liệu và quyền sở hữu. Nếu legacy vẫn là upstream của một dữ liệu, context mới không nên tự ý cập nhật trực tiếp bảng nguồn. Nếu context mới đã trở thành owner, các consumer cũ cần được chuyển sang hợp đồng do context mới cung cấp hoặc qua một adapter tương thích.

## 3. Chiến lược Strangler Fig

Strangler Fig là chiến lược thay thế hệ thống theo từng phần. Một lớp định tuyến hoặc façade nhận request và chuyển từng capability sang hệ thống mới khi phần đó đã sẵn sàng. Các chức năng chưa chuyển tiếp tục chạy trên legacy.

Thay vì triển khai một dự án rewrite lớn rồi đổi toàn bộ lưu lượng trong một lần, nhóm chọn một lát cắt nghiệp vụ có phạm vi rõ, xây context mới, kiểm chứng, chuyển lưu lượng và lặp lại.

~~~mermaid
flowchart TD
    C[Clients / Channels] --> R[Routing Facade]
    R -->|Capability chưa chuyển| L[Legacy System]
    R -->|Capability đã chuyển| N[New Bounded Context]
    N --> A[ACL / Legacy Adapter]
    A --> L
    N --> D[(New Context Data)]
~~~

Trong giai đoạn đầu, context mới có thể vẫn gọi legacy qua ACL để lấy dữ liệu hoặc thực hiện một số hành động. Theo thời gian, từng hành vi và quyền sở hữu được chuyển sang context mới. Khi không còn consumer phụ thuộc, phần legacy tương ứng có thể được ngừng hoạt động.

### 3.1. Chọn lát cắt đầu tiên

Một lát cắt phù hợp thường:

- Có giá trị nghiệp vụ nhìn thấy được.
- Có ranh giới và consumer tương đối rõ.
- Có thể triển khai độc lập hoặc cô lập qua adapter.
- Có dữ liệu và quy tắc đủ hiểu để kiểm thử.
- Có phương án chuyển lưu lượng và phục hồi.
- Không buộc phải thay đổi đồng thời quá nhiều capability khác.

Ví dụ, chuyển chức năng tra cứu lịch sử đơn hàng sang một read model mới có thể ít rủi ro hơn việc chuyển đồng thời đặt hàng, tồn kho, thanh toán và giao hàng. Tuy nhiên, nếu read model mới phụ thuộc dữ liệu chưa đáng tin cậy hoặc không có quyền truy cập ổn định, lát cắt đó chưa chắc là lựa chọn tốt.

### 3.2. Không đồng nhất Strangler với proxy đơn giản

Routing façade chỉ là một phần. Di trú thực sự còn cần:

- Phân định capability nào thuộc legacy và capability nào thuộc context mới.
- ACL để chuyển đổi mô hình và hợp đồng.
- Quyền sở hữu dữ liệu rõ ràng.
- Cơ chế đồng bộ và đối soát.
- Kiểm thử hành vi cũ và mới.
- Kế hoạch chuyển consumer, cutover và retire.

Nếu chỉ thêm proxy nhưng mọi service mới vẫn truy vấn bảng legacy trực tiếp, phụ thuộc cũ chưa được tháo gỡ.

## 4. ACL bảo vệ mô hình mới như thế nào?

Anti-Corruption Layer là một lớp dịch thuật và cách ly giữa hai mô hình. Nó chuyển dữ liệu và hành động từ ngôn ngữ legacy sang ngôn ngữ của context mới, đồng thời che giấu chi tiết giao tiếp với hệ thống cũ.

ACL có thể gồm:

- **Legacy Gateway/Port:** giao diện nội bộ mô tả khả năng cần dùng từ legacy.
- **Adapter:** thực hiện giao tiếp HTTP, SOAP, file, message hoặc database view.
- **Translator/Mapper:** chuyển cấu trúc, mã, đơn vị và trạng thái.
- **Policy:** quyết định cách xử lý giá trị thiếu, mã không biết hoặc dữ liệu mâu thuẫn.
- **Error Translator:** chuyển lỗi kỹ thuật hoặc lỗi legacy thành kết quả có ý nghĩa trong context mới.
- **Anti-corruption façade:** cung cấp một điểm vào/ra ổn định cho domain/application layer.

ACL không chỉ đổi tên field. Nó phải giữ đúng ý nghĩa nghiệp vụ, phát hiện dữ liệu không thể dịch an toàn và ngăn model legacy xâm nhập domain model mới.

### 4.1. ACL ở chiều gọi legacy

Khi context mới cần lấy dữ liệu từ legacy:

1. Application Layer gọi một port có tên theo ngôn ngữ mới.
2. Adapter gọi API hoặc truy vấn được cho phép của legacy.
3. Translator chuyển payload cũ thành Value Object hoặc DTO nội bộ.
4. Domain/Application Layer nhận dữ liệu đã được diễn giải.

Ví dụ, Ordering cần một bản chụp sản phẩm tại thời điểm đặt. Nó gọi LegacyCatalogPort, không nhận trực tiếp LegacyProductRow.

### 4.2. ACL ở chiều gửi lệnh

Khi context mới cần yêu cầu legacy thực hiện hành động:

1. Application Layer tạo command theo ngôn ngữ nội bộ.
2. ACL xác định operation tương ứng trong legacy.
3. Adapter chuyển command thành request, mã trạng thái và định dạng legacy.
4. ACL chuyển response/lỗi về kết quả nội bộ.

Ví dụ, CancelOrder trong Ordering có thể phải chuyển thành SOAP operation UpdateSalesDoc với mã X. Mapping này cần được xác nhận từ hành vi thật, không suy ra chỉ từ tên mã.

### 4.3. ACL không nên biến thành một domain model thứ hai

ACL cần đủ logic để dịch và bảo vệ ranh giới. Nó không nên sở hữu lại toàn bộ quy tắc đặt hàng, giá hoặc tồn kho. Quy tắc của Ordering thuộc Ordering; quy tắc giao tiếp và mapping legacy thuộc ACL/adapter.

Nếu ACL ngày càng có nhiều điều kiện nghiệp vụ, hãy xác định xem đó là:

- Một quy tắc thực sự thuộc context mới nhưng đang bị đặt sai chỗ.
- Một quy tắc chỉ có ý nghĩa để tương thích legacy.
- Một quy tắc chưa được hiểu rõ và cần trao đổi thêm với chuyên gia.

## 5. Thiết kế port và translator theo ngôn ngữ context mới

Ví dụ, Ordering cần một bản chụp sản phẩm tại thời điểm đặt:

~~~java
public interface ProductCatalog {
    Optional<ProductSnapshot> findForOrdering(Sku sku);
}

public record ProductSnapshot(
    Sku sku,
    ProductName name,
    Money unitPrice
) {}
~~~

Interface không nhắc đến bảng PRD_MST, mã ACTIVE_FLG hoặc kiểu dữ liệu của SOAP. Đó là chi tiết của legacy adapter.

Adapter có thể nhận response cũ:

~~~java
public record LegacyProductResponse(
    String productCode,
    String productName,
    String priceText,
    String currency,
    String activeFlag
) {}
~~~

Translator chuyển response:

~~~java
public final class LegacyProductTranslator {
    public ProductSnapshot toProductSnapshot(LegacyProductResponse source) {
        if (!"Y".equals(source.activeFlag())) {
            throw new ProductNotAvailable(source.productCode());
        }

        Sku sku = new Sku(source.productCode());
        ProductName name = new ProductName(source.productName());
        Currency currency = Currency.getInstance(source.currency());
        Money price = new Money(
            new BigDecimal(source.priceText()),
            currency
        );

        return new ProductSnapshot(sku, name, price);
    }
}
~~~

Đây là ví dụ rút gọn. Trong ứng dụng thật, translator cần xử lý field thiếu, định dạng số, mã tiền tệ chưa hỗ trợ, khoảng trắng, dữ liệu lỗi và version payload. Không nên tự thay giá trị không hợp lệ bằng 0 hoặc giá mặc định nếu điều đó làm sai quyết định đặt hàng.

### 5.1. Mapping trạng thái phải có ngữ nghĩa

Ví dụ bảng mapping:

| Legacy code | Ý nghĩa đã xác nhận | Trạng thái Ordering |
|---|---|---|
| N | Bản nháp, chưa gửi | DRAFT |
| P | Đã gửi yêu cầu đặt | PLACED |
| A | Đã chấp nhận và đủ điều kiện tiếp tục | CONFIRMED |
| C | Đã hoàn tất fulfillment | FULFILLED |
| X | Hủy theo yêu cầu | CANCELLED |

Nếu mã A trong một số luồng có nghĩa là chỉ giữ hàng, không thể map tất cả trường hợp thành CONFIRMED. Có thể cần gọi thêm API, đọc lịch sử sự kiện hoặc trả kết quả UNKNOWN_LEGACY_STATE để điều tra. Mapping phải dựa trên semantics, không dựa trên sự giống nhau của tên.

### 5.2. Xử lý mã không biết

Khi legacy thêm mã mới, translator có thể gặp một giá trị chưa hỗ trợ. Có ba cách thường cân nhắc:

- Từ chối và đưa vào luồng xử lý lỗi có quan sát được.
- Ánh xạ thành trạng thái nội bộ UNKNOWN nếu use case có thể tiếp tục an toàn.
- Cách ly record và yêu cầu điều tra trước khi cho phép hành động.

Không nên mặc định mọi mã lạ là trạng thái thành công hoặc bỏ qua silently. Với quyết định tài chính, tồn kho hoặc quyền truy cập, unknown state thường cần fail closed.

### 5.3. Chuyển đổi lỗi

Lỗi legacy cần được dịch theo ý nghĩa:

| Legacy/transport error | Cách diễn giải trong context mới |
|---|---|
| HTTP 404 hoặc mã “không tồn tại” | Không tìm thấy đối tượng nếu hợp đồng xác nhận đúng nghĩa |
| HTTP 409 hoặc mã “đã xử lý” | Xung đột hoặc request đã được xử lý; cần truy vấn kết quả |
| HTTP 429 / rate limit | Giới hạn tạm thời; có thể retry theo policy |
| Timeout | Kết quả chưa xác định; không được kết luận thao tác thất bại |
| Mã nghiệp vụ “không đủ tồn kho” | InsufficientStock nếu Inventory/legacy xác nhận ý nghĩa |
| Payload sai schema | Lỗi hợp đồng tích hợp; cần log và cách ly |

Không nên chuyển mọi lỗi thành NotFound hoặc BusinessRejected. Timeout có thể xảy ra sau khi legacy đã commit; cần idempotency key hoặc API truy vấn kết quả để xác định trạng thái.

## 6. Xác định quyền sở hữu dữ liệu trong giai đoạn cùng tồn tại

Đây thường là phần khó nhất của di trú. Khi hai hệ thống cùng chạy, cần biết hệ thống nào có quyền ghi chính thức cho từng loại dữ liệu và hành vi.

Một bảng ownership tạm thời có thể như sau:

| Capability / dữ liệu | Trước di trú | Giai đoạn chuyển tiếp | Sau di trú |
|---|---|---|---|
| Đơn hàng mới | Legacy | Ordering mới theo lát cắt đã bật | Ordering mới |
| Đơn lịch sử | Legacy | Legacy là nguồn lịch sử, bản sao mới phục vụ query | Kho lịch sử hoặc Ordering theo chính sách |
| Tồn kho | Legacy | Inventory mới hoặc legacy, chỉ một writer có thẩm quyền | Inventory mới |
| Thanh toán | Nhà cung cấp/legacy | Payment owner hiện tại | Payment context/provider contract |
| Báo cáo | Legacy database | Read model hợp nhất có checkpoint | Read model từ nguồn mới |

Ownership có thể khác nhau theo capability, tenant, vùng, loại đơn hoặc khoảng thời gian. Cần ghi rõ phạm vi và thời điểm chuyển quyền, không chỉ ghi tên hệ thống.

### 6.1. Một nguồn ghi có thẩm quyền cho mỗi dữ liệu

Trong mỗi giai đoạn, hãy xác định một writer có thẩm quyền cho từng invariant/dữ liệu. Nếu cả legacy và context mới đều có thể cập nhật độc lập cùng một đơn hàng, hệ thống dễ gặp:

- Lost update.
- Hai trạng thái mâu thuẫn.
- Event được phát hai lần.
- Không biết dữ liệu nào là sự thật.
- Không thể xác định rollback nên khôi phục từ đâu.

Có thể có bản sao đọc ở nhiều nơi, nhưng bản sao không đồng nghĩa với quyền ghi. Khi chuyển quyền sở hữu, cần một mốc cutover rõ và cơ chế ngăn writer cũ tiếp tục nhận thay đổi.

### 6.2. Tránh dual write trực tiếp

Dual write là việc một request ghi vào hai hệ thống độc lập. Ví dụ ứng dụng lưu đơn vào database mới rồi gọi API legacy để lưu bản sao. Nếu lần ghi đầu thành công nhưng lần thứ hai thất bại, hai hệ thống lệch nhau. Nếu retry thiếu idempotency, có thể tạo bản ghi trùng.

Thay vì dual write tùy tiện, hãy chọn một nguồn có thẩm quyền và đồng bộ bản sao qua outbox, CDC hoặc cơ chế phát sự kiện có thể phục hồi. Nếu bắt buộc phải có hai lần ghi trong một use case, cần thiết kế quy trình trạng thái, retry, đối soát và compensation rõ ràng.

## 7. Các giai đoạn di trú dữ liệu

Di trú dữ liệu không chỉ là copy bảng. Cần chuyển đổi cấu trúc, ngữ nghĩa, identity, lịch sử và quan hệ sao cho context mới có thể bảo vệ invariant của nó.

Một quy trình thường gồm:

1. **Inventory dữ liệu:** xác định bảng, view, file, batch, trigger, consumer và owner.
2. **Profiling:** đo null, duplicate, mã không biết, dữ liệu sai định dạng và quan hệ mồ côi.
3. **Mapping:** định nghĩa source-to-target theo ngôn ngữ context mới.
4. **Bulk load:** chuyển dữ liệu lịch sử theo batch có checkpoint.
5. **CDC hoặc incremental sync:** lấy thay đổi phát sinh trong lúc bulk load.
6. **Validation/reconciliation:** so sánh số lượng, tổng tiền, trạng thái và quan hệ.
7. **Cutover:** chuyển writer/reader theo một mốc đã xác định.
8. **Retain/retire:** giữ legacy read-only theo thời hạn cần thiết rồi ngừng dần.

### 7.1. Data profiling trước khi viết migration

Ví dụ các kiểm tra ban đầu:

~~~sql
-- Số trạng thái legacy đang tồn tại
SELECT ORDER_STATUS, COUNT(*)
FROM LEGACY_ORDER
GROUP BY ORDER_STATUS;

-- Bản ghi thiếu mã khách hàng
SELECT COUNT(*)
FROM LEGACY_ORDER
WHERE CUSTOMER_CODE IS NULL;

-- Mã đơn bị trùng
SELECT ORDER_NO, COUNT(*)
FROM LEGACY_ORDER
GROUP BY ORDER_NO
HAVING COUNT(*) > 1;
~~~

Các truy vấn chỉ minh họa. Cần điều chỉnh theo schema và quyền truy cập thực tế. Mục tiêu là hiểu chất lượng dữ liệu và phát hiện các trường hợp mapping không thể làm tự động.

### 7.2. Mapping phải lưu dấu nguồn gốc

Khi chuyển identity, nên lưu mapping từ ID cũ sang ID mới:

| Legacy ID | New ID | Migration batch | Trạng thái |
|---|---|---|---|
| SO-001 | ORD-1001 | batch-2026-01 | Verified |
| SO-002 | ORD-1002 | batch-2026-01 | Verified |

Mapping hỗ trợ truy vết, xử lý callback cũ, đối soát và điều tra lỗi. Không nên suy ra ID mới bằng cách cắt chuỗi ID cũ nếu quy tắc identity không đảm bảo điều đó.

### 7.3. Bulk load kết hợp CDC

Khi hệ thống cũ vẫn tiếp tục nhận ghi, bulk load đơn thuần có thể bị lạc hậu ngay khi hoàn tất. Một cách phổ biến:

1. Chọn watermark hoặc log position L0.
2. Bắt đầu đọc thay đổi từ L0.
3. Bulk load dữ liệu nền.
4. Áp dụng các thay đổi sau L0 theo thứ tự/sequence mà CDC cung cấp.
5. Theo dõi lag cho đến khi bắt kịp.
6. Đối soát và chuyển quyền ghi tại một watermark được xác nhận.

CDC phụ thuộc khả năng của database và cách capture transaction log. Cần hiểu semantics của delete, update, transaction ordering, schema changes và retention. Không phải mọi giải pháp CDC đều cung cấp cùng bảo đảm.

### 7.4. Idempotency và checkpoint

Migration job phải có thể chạy lại sau lỗi mà không tạo duplicate hoặc làm sai trạng thái. Hãy dùng:

- Khóa nguồn ổn định hoặc mapping ID.
- Unique constraint ở target.
- Checkpoint/batch ID.
- Upsert có điều kiện.
- Version hoặc source sequence để bỏ qua bản cập nhật cũ.
- Ghi nhận record lỗi để xử lý riêng.

Một thao tác migration lặp lại cần tạo cùng kết quả như thao tác đầu tiên, hoặc được phát hiện là đã xử lý. Không nên chỉ dựa vào số dòng đã đọc trong file nếu nguồn dữ liệu có thể thay đổi thứ tự.

### 7.5. Xử lý delete và dữ liệu lịch sử

CDC cần phân biệt delete thật với record bị ẩn hoặc đánh dấu ngừng hoạt động. Nếu context mới cần audit, có thể không xóa cứng mà lưu tombstone hoặc trạng thái đã xóa theo mô hình mới. Quyết định này cần tuân theo yêu cầu nghiệp vụ, retention và quy định dữ liệu.

## 8. Chuyển quyền sở hữu bằng từng bước nhỏ

Chuyển dữ liệu và chuyển quyền xử lý nghiệp vụ là hai việc liên quan nhưng không giống nhau. Một context mới có thể đã chứa bản sao dữ liệu mà chưa được quyền ghi. Ngược lại, một capability có thể bắt đầu nhận lệnh mới trong khi dữ liệu lịch sử vẫn được đọc từ legacy qua ACL.

Một lộ trình ví dụ:

| Giai đoạn | Hệ thống xử lý lệnh mới | Nguồn dữ liệu có thẩm quyền | Mục tiêu |
|---|---|---|---|
| 0. Baseline | Legacy | Legacy | Đo hành vi và lỗi hiện tại |
| 1. Shadow read | Legacy | Legacy | So sánh kết quả query mới với legacy |
| 2. New read model | Legacy ghi; projection mới đọc | Legacy | Kiểm chứng mapping và dữ liệu |
| 3. Canary write | Một nhóm traffic ở context mới | New context cho phạm vi canary | Kiểm chứng ghi và vận hành giới hạn |
| 4. Expand ownership | Context mới theo từng nhóm | Ownership chuyển theo phạm vi | Tăng dần traffic và consumer |
| 5. Retire legacy capability | Context mới | New context | Ngừng code/bảng legacy đã thay thế |

Phạm vi canary cần được định nghĩa bằng khóa ổn định như tenant, region hoặc nhóm khách hàng để cùng một thực thể không bị route ngẫu nhiên qua hai writer.

### 8.1. Shadow traffic

Shadow traffic gửi một bản sao request tới hệ thống mới để so sánh kết quả, trong khi chỉ legacy trả lời người dùng và có quyền tạo side effect. Shadow request phải tránh ghi thật, gửi email, thu tiền hoặc giữ tồn kho lần thứ hai.

Với command, có thể chạy chế độ evaluate-only hoặc dùng dữ liệu cô lập. Không được gửi cùng một lệnh thanh toán/đặt hàng tới cả hai hệ thống rồi giả định có thể bỏ một kết quả.

### 8.2. Dual read

Trong giai đoạn so sánh, ứng dụng có thể đọc cả legacy và read model mới, sau đó so sánh các field nghiệp vụ đã chuẩn hóa. Cần xác định cách xử lý chênh lệch và nguồn nào trả lời người dùng.

So sánh nên bỏ qua các field kỹ thuật như timestamp khác định dạng nếu không ảnh hưởng ngữ nghĩa, nhưng không được bỏ qua chênh lệch trạng thái, tổng tiền hoặc identity. Mọi normalization phải được ghi rõ.

### 8.3. Canary release

Canary chuyển một tỷ lệ hoặc nhóm traffic nhỏ sang context mới. Chọn chỉ số giám sát trước khi mở rộng:

- Tỷ lệ thành công của command.
- Tỷ lệ lỗi miền và lỗi kỹ thuật.
- Độ trễ p95/p99.
- Số lượng request retry hoặc timeout.
- Chênh lệch dữ liệu khi đối soát.
- Tỷ lệ quy trình bị treo hoặc compensation thất bại.
- Tác động tới các hệ thống upstream/downstream.

Nếu chỉ số vượt ngưỡng đã thống nhất, dừng mở rộng và kích hoạt quy trình điều tra/rollback phù hợp.

## 9. ACL và tích hợp trong thời gian coexistence

Khi cả hai hệ thống cùng chạy, ACL thường cần hỗ trợ nhiều chiều:

- New context gọi legacy API.
- Legacy gọi API façade của context mới.
- Legacy phát event/file và ACL dịch sang event nội bộ.
- Context mới phát integration event theo contract mà consumer cũ hiểu.
- Data migration đọc legacy schema và ghi target schema.

Không phải mọi luồng đều nên dùng cùng một translator. Hãy tách theo hợp đồng và mục đích để mapping dễ kiểm thử, có version và có owner.

### 9.1. Dùng Published Language khi nhiều consumer cần hợp đồng ổn định

Nếu context mới công bố event cho nhiều consumer, có thể định nghĩa Published Language hoặc integration contract ổn định. Consumer cũ nhận event mới thông qua adapter nếu cần format cũ.

Ví dụ, context mới phát OrderConfirmed với orderId, confirmedAt và total. Adapter tương thích có thể chuyển nó thành file fixed-width hoặc message có mã A cho hệ thống cũ. Không nên để domain event nội bộ phụ thuộc format file legacy.

### 9.2. Chống phụ thuộc schema database

Tránh để ứng dụng mới truy vấn trực tiếp bảng legacy bằng cách dùng chung schema hoặc ORM entity. Nếu cần đọc tạm thời, hãy đặt một read adapter có hợp đồng, quyền truy cập read-only và kế hoạch loại bỏ rõ ràng.

Việc chia sẻ database trong giai đoạn chuyển tiếp có thể là một ràng buộc thực tế, nhưng cần hạn chế phạm vi, không cho phép ghi tùy tiện và theo dõi consumer còn phụ thuộc. Mục tiêu là giảm dần sự phụ thuộc, không biến nó thành kiến trúc lâu dài.

## 10. Quản lý thay đổi schema theo Expand–Migrate–Contract

Khi cả legacy và context mới cùng sử dụng một contract hoặc database, thay đổi không tương thích có thể làm một phía ngừng hoạt động.

Một cách an toàn là:

1. **Expand:** thêm field/API/event mới theo cách tương thích ngược; consumer cũ vẫn hoạt động.
2. **Migrate:** cập nhật consumer, backfill dữ liệu và chuyển dần sang field/contract mới.
3. **Contract:** chỉ xóa field hoặc operation cũ sau khi xác nhận không còn consumer phụ thuộc.

Ví dụ, nếu legacy dùng CUSTOMER_CODE còn context mới dùng customerId, có thể thêm trường mapping và hỗ trợ song song trong thời gian chuyển đổi. Sau khi mọi consumer đã chuyển, field cũ mới được retire theo quy trình riêng.

Không nên đổi tên hoặc xóa field ngay trong một lần deploy khi chưa biết tất cả consumer. Hãy đo và kiểm tra mức sử dụng trước bước contract.

## 11. Kiểm thử trước và trong khi chuyển đổi

Di trú cần kiểm thử cả hành vi legacy, mapping ACL và hành vi domain model mới. Không thể chỉ viết unit test cho service mới rồi cho rằng cutover an toàn.

| Loại test | Mục tiêu | Ví dụ |
|---|---|---|
| Characterization test | Ghi lại hành vi legacy đang thực sự xảy ra | Cùng input, legacy trả status/amount nào |
| Golden master test | Lưu và so sánh kết quả đã biết của một tập input | Output báo cáo hoặc phép tính cũ |
| ACL mapping test | Xác nhận chuyển đổi hai chiều | Legacy A thành CONFIRMED theo đúng điều kiện |
| Contract test | Bảo đảm API/event/file không phá consumer | Field bắt buộc, schema version, mã lỗi |
| Domain unit test | Kiểm tra quy tắc của context mới | Không xác nhận đơn rỗng |
| Integration test | Kiểm tra database, transaction, outbox, CDC | Append event và checkpoint cùng nhau |
| Migration validation | So sánh dữ liệu source-target | Số đơn, tổng tiền, trạng thái, quan hệ |
| Shadow comparison | So sánh kết quả mới và cũ trên input giống nhau | Giá, trạng thái, phí giao hàng |
| End-to-end test | Kiểm tra hành trình qua routing và hệ thống liên quan | Đặt đơn từ API tới trạng thái cuối |

### 11.1. Characterization test cho legacy

Khi tài liệu cũ thiếu hoặc hành vi không rõ, hãy tạo test ghi nhận hành vi quan sát được. Test này giúp phát hiện thay đổi ngoài ý muốn trong lúc thay adapter hoặc refactor legacy.

Characterization test không khẳng định hành vi hiện tại là đúng nghiệp vụ. Nó ghi nhận “hệ thống đang làm gì”. Sau đó chuyên gia quyết định hành vi nào cần giữ, hành vi nào là bug cần sửa trong context mới.

### 11.2. Golden master và dữ liệu nhạy cảm

Golden master hữu ích với output phức tạp nhưng cần ẩn hoặc thay dữ liệu cá nhân, thông tin thanh toán và bí mật. Bộ dữ liệu so sánh phải được kiểm soát version và có nguồn gốc rõ.

### 11.3. Test mapping các giá trị chưa biết

Không chỉ test những mã legacy đã biết. Hãy test:

- Mã trạng thái mới chưa được hỗ trợ.
- Field null hoặc chuỗi rỗng.
- Số tiền sai định dạng hoặc currency không biết.
- Ngày sai timezone/format.
- ID trùng hoặc không tồn tại.
- Response thiếu field bắt buộc.
- Timeout sau khi gửi command.

Test phải xác nhận hệ thống xử lý an toàn và có thể quan sát, không tự tạo dữ liệu nghiệp vụ mặc định.

## 12. Cutover: chuyển lưu lượng và quyền ghi

Cutover là thời điểm một capability chuyển từ legacy sang context mới. Cần chuẩn bị trước, diễn tập và có điều kiện dừng rõ ràng.

Một checklist cutover có thể gồm:

1. Xác nhận phiên bản ứng dụng và ACL đã triển khai.
2. Kiểm tra backup/restore và khả năng truy xuất dữ liệu nguồn.
3. Xác nhận bulk load và CDC đã bắt kịp watermark.
4. Chạy reconciliation cuối và xử lý chênh lệch chưa giải quyết.
5. Xác nhận consumer, batch và integration đã được route đúng.
6. Dừng hoặc khóa writer cũ cho phạm vi chuyển đổi.
7. Drain message đang xử lý và ghi nhận watermark cuối.
8. Chuyển routing sang context mới.
9. Kiểm tra health, latency, error rate và dữ liệu ghi mới.
10. Theo dõi sát trong thời gian hypercare.

~~~mermaid
sequenceDiagram
    participant Ops as Operations
    participant Route as Routing Facade
    participant Old as Legacy
    participant New as New Context
    participant Data as Migration / CDC
    Ops->>Data: Verify final watermark and reconciliation
    Data-->>Ops: Ready
    Ops->>Old: Stop writes for migrated capability
    Old-->>Ops: Writer fenced / queues drained
    Ops->>Route: Switch capability route
    Route->>New: Send new commands
    New-->>Route: New context response
    Ops->>New: Verify health and business invariants
~~~

### 12.1. Fencing writer cũ

Chỉ đổi routing ở API gateway chưa đủ nếu batch job, admin tool hoặc integration khác vẫn ghi vào legacy. Cần fencing: thu hồi quyền ghi, tắt job, thay credential, hoặc dùng cơ chế version/lease để writer cũ không thể tiếp tục cập nhật dữ liệu đã chuyển.

Fencing cần được kiểm chứng. Nếu một batch cũ chạy sau cutover và ghi trạng thái cũ, context mới có thể bị ghi đè hoặc reconciliation trở nên phức tạp.

### 12.2. Chuyển theo cohort

Có thể cutover theo tenant, region, loại đơn hoặc nhóm khách hàng. Cohort cần ổn định và có identity rõ. Một thực thể không nên bị định tuyến sang hai writer khác nhau giữa các request.

### 12.3. Hypercare

Sau cutover, theo dõi một giai đoạn tăng cường:

- Lỗi mapping và mã trạng thái unknown.
- Chênh lệch dữ liệu và số record chưa migrate.
- Message backlog, retry và dead-letter.
- Quy trình pending quá lâu.
- Lỗi từ consumer cũ.
- Hiệu năng và tải database.
- Phản hồi từ vận hành và người dùng.

Chỉ kết thúc hypercare khi chỉ số ổn định và các chênh lệch quan trọng đã được xử lý.

## 13. Rollback và Forward Recovery

Rollback không phải lúc nào cũng là “đổi route về legacy”. Sau khi context mới đã nhận lệnh và ghi dữ liệu mới, legacy có thể không biết các thay đổi đó. Nếu quay lại mà không đồng bộ ngược, hệ thống có thể mất giao dịch hoặc tạo trạng thái sai.

Trước cutover, hãy phân loại khả năng phục hồi:

| Tình huống | Cách phục hồi có thể phù hợp |
|---|---|
| Chưa có write nào vào context mới | Có thể chuyển route về legacy nếu dữ liệu chưa thay đổi |
| Context mới chỉ phục vụ read | Chuyển read route về legacy hoặc read model cũ |
| Context mới đã nhận write nhưng có reverse sync đáng tin cậy | Đồng bộ ngược theo watermark rồi mới route lại |
| Context mới đã thực hiện side effect bên ngoài | Cần đối soát và compensation/forward recovery theo nghiệp vụ |
| Hai hệ thống có dữ liệu không thể hợp nhất tự động | Dừng cohort, khóa ghi và xử lý thủ công có audit |

### 13.1. Định nghĩa rollback trigger trước

Ví dụ trigger:

- Tỷ lệ command thất bại vượt ngưỡng trong một khoảng thời gian.
- Sai lệch tổng tiền hoặc trạng thái vượt ngưỡng cho phép.
- Message backlog tăng liên tục.
- Không bảo vệ được invariant quan trọng.
- Lỗi dữ liệu không thể khắc phục bằng retry.

Ngưỡng phải dựa trên SLA, rủi ro và khả năng vận hành của hệ thống. Đừng chờ sự cố lớn mới thống nhất ai có quyền dừng cutover.

### 13.2. Reverse sync không đơn giản là copy bảng ngược

Schema và semantics của hai hệ thống có thể khác nhau. Khi đồng bộ ngược, cần translator theo chiều ngược, mapping ID, xử lý version và quy tắc xung đột. Một trạng thái mới có thể không có biểu diễn tương ứng trong legacy.

Nếu không thể biểu diễn an toàn, cần forward recovery: sửa lỗi trong context mới, phát command bù trừ hoặc hoàn tất quy trình bằng một hành động nghiệp vụ khác. Không nên ép trạng thái mới vào một mã legacy gần giống.

### 13.3. Rollback khác compensation

Rollback khôi phục một thay đổi chưa commit trong transaction hoặc quay lại một phiên bản triển khai. Compensation là hành động nghiệp vụ mới nhằm bù trừ một tác động đã commit, ví dụ giải phóng hàng đã giữ hoặc hoàn tiền. Một cutover plan có thể cần cả hai, nhưng chúng không thay thế nhau.

## 14. Reconciliation và quan sát sai lệch

Trong giai đoạn song hành, hệ thống cần phát hiện sai lệch có thể xảy ra giữa nguồn và bản sao. Reconciliation không nên ghi đè tùy tiện dữ liệu của context khác; nó cần yêu cầu owner thực hiện hành động qua hợp đồng.

Các phép đối soát có thể gồm:

- Số lượng record theo cohort và trạng thái.
- Tổng tiền theo currency, ngày hoặc nhóm đơn.
- Số lượng dòng hàng và tổng số lượng.
- Mapping ID nguồn-target.
- Số lượng event đã phát/đã xử lý.
- Checkpoint CDC và độ trễ.
- Các record không thể dịch hoặc có trạng thái unknown.

Ví dụ, so sánh tổng tiền cần nhóm theo currency. Cộng VND và USD thành một tổng số không có ý nghĩa nếu chưa có quy tắc quy đổi và tỷ giá được chốt.

### 14.1. Dùng correlation ID và migration batch ID

Mỗi request hoặc record chuyển đổi nên có metadata để truy vết:

- correlationId: nhóm các thao tác của cùng use case.
- legacyId và newId: liên kết identity cũ/mới.
- migrationBatchId: xác định đợt di trú.
- sourceVersion hoặc log position: xác định phiên bản dữ liệu nguồn.
- eventId và causationId: truy vết event và nguyên nhân.

Không ghi payload nhạy cảm vào log chỉ để tiện đối soát. Có thể log định danh đã được kiểm soát và số liệu tổng hợp.

### 14.2. Dashboard vận hành

Các metric hữu ích:

- Số request route qua legacy và context mới.
- Tỷ lệ lỗi ACL theo operation và mã lỗi.
- Số record chờ mapping hoặc bị cách ly.
- CDC lag và tuổi event chưa xử lý.
- Chênh lệch reconciliation theo cohort.
- Tỷ lệ retry, dead-letter và unknown state.
- Số writer cũ còn hoạt động sau fencing.

Dashboard phải cho biết capability và cohort nào đang có vấn đề, để nhóm dừng đúng phạm vi thay vì tắt toàn hệ thống.

## 15. Bảo vệ domain model mới trong suốt quá trình di trú

Một context mới chỉ thực sự độc lập khi nó có thể diễn đạt và bảo vệ quy tắc của mình mà không phụ thuộc trực tiếp vào cách legacy lưu dữ liệu.

Các nguyên tắc:

1. Domain model dùng thuật ngữ của Bounded Context mới.
2. Không đưa legacy DTO, enum hoặc ORM entity vào Aggregate.
3. Giao tiếp với legacy qua port và ACL.
4. Mapping giữ ngữ nghĩa, không chỉ chuyển kiểu dữ liệu.
5. Invariant được kiểm tra tại Aggregate/Policy sở hữu nó.
6. Dữ liệu legacy được xem là input ngoài; cần validate và xử lý unknown.
7. Không chia sẻ database write quyền tự do giữa hai context.
8. Integration contract có version và được kiểm thử.
9. Quy tắc tạm thời phục vụ migration cần có owner và ngày retire.

### 15.1. ACL là ranh giới có thể loại bỏ hoặc giữ lại

Khi legacy capability được retire, adapter chỉ dùng để giao tiếp với legacy có thể được xóa. Nhưng nếu context mới vẫn tích hợp với một hệ thống bên ngoài có mô hình khác, một ACL tương tự vẫn có giá trị lâu dài.

Không nên xóa ACL chỉ vì đã hoàn tất migration khỏi monolith. Câu hỏi là còn hệ thống nào có mô hình cần được dịch và cách ly hay không.

### 15.2. Tránh migration code trở thành domain code vĩnh viễn

Mapping tạm thời, fallback legacy, dual-read và feature flag có thể cần trong quá trình chuyển đổi. Hãy ghi rõ mục đích, điều kiện gỡ bỏ và người chịu trách nhiệm. Nếu không, các nhánh migration sẽ tồn tại mãi, làm domain model mới phụ thuộc vào lịch sử chuyển đổi.

## 16. Những sai lầm thường gặp

- **Big-bang rewrite:** thay toàn bộ hệ thống cùng lúc, tích lũy rủi ro và trì hoãn phản hồi thực tế.
- **Tách service theo module cũ:** sao chép ranh giới kỹ thuật thay vì tìm ranh giới nghiệp vụ.
- **Không có Context Map:** không rõ ai là upstream, downstream và owner dữ liệu.
- **Đưa schema legacy vào domain model mới:** thuật ngữ và cấu trúc cũ tiếp tục chi phối mô hình mới.
- **ACL chỉ đổi tên field:** bỏ qua khác biệt về semantics, trạng thái và lỗi.
- **Không xử lý mã không biết:** dữ liệu mới từ legacy có thể bị map sai hoặc silently accepted.
- **Hai hệ thống cùng ghi một dữ liệu:** tạo lost update, xung đột và không rõ nguồn sự thật.
- **Dual write không có phục hồi:** một lần ghi thành công, lần kia thất bại.
- **Copy dữ liệu một lần rồi cutover:** thay đổi phát sinh trong lúc copy bị bỏ sót.
- **Không có checkpoint/idempotency:** job chạy lại tạo dữ liệu trùng hoặc bỏ qua record.
- **Chỉ so sánh số lượng record:** không phát hiện tổng tiền, trạng thái hoặc quan hệ bị sai.
- **Shadow traffic tạo side effect:** gửi lệnh thanh toán/đặt hàng hai lần.
- **Chỉ đổi route khi rollback:** bỏ qua các write đã xảy ra ở hệ thống mới.
- **Không fencing writer cũ:** batch hoặc admin tool tiếp tục ghi sau cutover.
- **Giữ feature flag và fallback vĩnh viễn:** làm tăng nhánh code và khó biết nguồn nào có thẩm quyền.
- **Retire legacy quá sớm:** vẫn còn consumer, báo cáo hoặc job phụ thuộc.
- **Không diễn tập cutover:** kế hoạch chỉ tồn tại trên tài liệu và chưa được chứng minh.

## 17. Quy trình triển khai một lát cắt di trú

Có thể áp dụng trình tự sau cho từng capability:

1. **Khảo sát legacy:** xác định hành vi, schema, consumer, batch, side effect và rủi ro.
2. **Làm rõ domain:** trao đổi với chuyên gia, thống nhất thuật ngữ và invariant.
3. **Xác định Bounded Context:** chọn phạm vi và quyền sở hữu dữ liệu mới.
4. **Lập Context Map:** xác định upstream/downstream và hợp đồng cần dịch.
5. **Thiết kế ACL:** định nghĩa port, adapter, translator, error mapping và unknown handling.
6. **Ghi characterization tests:** đóng băng hành vi legacy cần hiểu hoặc cần giữ.
7. **Xây context mới:** domain model, repository, application use case và test.
8. **Chuẩn bị dữ liệu:** profiling, mapping ID, bulk load, CDC và reconciliation.
9. **Chạy shadow/dual read:** so sánh kết quả mà không nhân đôi side effect.
10. **Canary và chuyển ownership:** route cohort nhỏ, fencing writer cũ và tăng dần phạm vi.
11. **Cutover/hypercare:** kiểm tra watermark, health, invariant và chỉ số vận hành.
12. **Retire:** gỡ route, adapter, batch, quyền truy cập và schema legacy khi không còn consumer.
13. **Review:** cập nhật Context Map, tài liệu ownership và bài học cho lát cắt tiếp theo.

~~~mermaid
flowchart TD
    A[Khảo sát legacy] --> B[Khám phá domain và invariant]
    B --> C[Chọn Bounded Context]
    C --> D[Thiết kế ACL và contract]
    D --> E[Characterization + domain tests]
    E --> F[Bulk load + CDC]
    F --> G[Shadow / dual read]
    G --> H[Canary với ownership rõ]
    H --> I{Chỉ số và reconciliation đạt?}
    I -->|Không| J[Stop / recover / investigate]
    J --> G
    I -->|Có| K[Expand cutover]
    K --> L[Hypercare]
    L --> M[Retire legacy capability]
~~~

## 18. Checklist trước cutover

- [ ] Capability và Bounded Context đã được xác định bằng quy tắc nghiệp vụ.
- [ ] Ubiquitous Language và invariant đã được chuyên gia xác nhận.
- [ ] Context Map thể hiện rõ các quan hệ tích hợp.
- [ ] ACL có port, adapter và translator theo hợp đồng.
- [ ] Mapping trạng thái, mã lỗi, đơn vị và tiền tệ đã được kiểm chứng.
- [ ] Mã không biết và payload không hợp lệ có cách xử lý an toàn.
- [ ] Có một writer có thẩm quyền cho từng dữ liệu trong từng cohort.
- [ ] Không còn dual write tùy tiện.
- [ ] Bulk load, CDC, checkpoint và idempotency đã được diễn tập.
- [ ] Reconciliation kiểm tra số lượng, tổng tiền, trạng thái và quan hệ.
- [ ] Shadow traffic không tạo side effect trùng.
- [ ] Consumer, batch, admin tool và integration cũ đã được kiểm kê.
- [ ] Có fencing để writer cũ không thể tiếp tục ghi sau cutover.
- [ ] Routing và feature flag có thể chuyển theo cohort.
- [ ] Rollback trigger và người có quyền quyết định đã rõ.
- [ ] Có phương án reverse sync hoặc forward recovery cho write mới.
- [ ] Backup/restore, monitoring, alert và hypercare đã sẵn sàng.
- [ ] Điều kiện retire legacy được xác định và có người chịu trách nhiệm.

## 19. Câu hỏi tự kiểm tra

1. Vì sao di trú DDD cần xác định Bounded Context thay vì tách service theo module legacy?
2. Strangler Fig giúp giảm rủi ro thay thế hệ thống theo từng phần như thế nào?
3. ACL bảo vệ domain model mới khỏi những loại phụ thuộc legacy nào?
4. Translator khác mapper đơn giản ở điểm nào?
5. Làm sao xử lý một mã trạng thái legacy có nhiều ý nghĩa tùy quy trình?
6. Vì sao mỗi dữ liệu cần một writer có thẩm quyền trong giai đoạn chuyển tiếp?
7. Dual write có thể gây ra những trạng thái lỗi nào?
8. Bulk load kết hợp CDC giải quyết vấn đề thay đổi phát sinh trong lúc di trú ra sao?
9. Vì sao migration job cần checkpoint, idempotency và mapping ID?
10. Shadow traffic khác canary write như thế nào?
11. Expand–Migrate–Contract giúp duy trì tương thích ra sao?
12. Những gì cần được kiểm tra trước cutover?
13. Vì sao rollback sau khi hệ thống mới đã nhận write không đơn giản là đổi route?
14. Khi nào cần forward recovery hoặc compensation?
15. Khi nào có thể retire ACL và capability legacy?

## Kết luận

Di trú hệ thống cũ theo DDD là quá trình chuyển dần quyền sở hữu nghiệp vụ và dữ liệu sang những Bounded Context có mô hình rõ ràng. Strangler Fig cho phép thay thế theo từng capability; ACL dịch thuật ngữ, trạng thái, dữ liệu và lỗi để bảo vệ mô hình mới trong thời gian hai hệ thống cùng tồn tại. Ownership, migration data, CDC, idempotency, reconciliation và cutover phải được thiết kế như một phần của thay đổi, không phải công việc phụ sau khi code đã xong.

Hãy bắt đầu từ ranh giới nghiệp vụ và một lát cắt có thể kiểm chứng. Giữ một nguồn ghi có thẩm quyền cho mỗi dữ liệu, chuyển đổi hợp đồng qua ACL, đo chênh lệch và chuẩn bị cách phục hồi trước khi mở rộng lưu lượng. Khi một capability mới đã tự sở hữu quy tắc, dữ liệu và consumer, phần legacy tương ứng mới thực sự có thể được retire an toàn.
