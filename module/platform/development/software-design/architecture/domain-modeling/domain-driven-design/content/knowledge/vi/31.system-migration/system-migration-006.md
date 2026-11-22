# Thay thế từng phần theo cách tiếp cận Strangler khi phù hợp

Khi một hệ thống cũ vẫn đang phục vụ hoạt động kinh doanh, thay thế toàn bộ trong một lần thường có rủi ro lớn. Hệ thống có thể chứa nhiều quy tắc ngầm, dữ liệu lịch sử, tích hợp bên ngoài và quy trình mà tài liệu không mô tả đầy đủ. Một dự án viết lại toàn bộ có thể kéo dài trong khi hệ thống cũ vẫn phải được duy trì; đến ngày chuyển đổi, phần mới có thể chưa bao phủ hết hành vi thực tế.

**Strangler Pattern** là cách hiện đại hóa theo từng phần: xây dựng một lớp định tuyến hoặc điểm vào có thể đưa từng năng lực nghiệp vụ sang phần mới, trong khi các năng lực chưa chuyển đổi tiếp tục chạy trên hệ thống cũ. Theo thời gian, phần mới đảm nhận ngày càng nhiều trách nhiệm; hệ thống cũ được thu hẹp và cuối cùng có thể ngừng hoạt động.

Trong Domain-Driven Design (DDD), cách tiếp cận này hữu ích khi nhóm đã xác định được các Bounded Context hoặc năng lực có thể tách dần khỏi hệ thống cũ. Mỗi phần mới cần có mô hình, hợp đồng và quyền sở hữu dữ liệu rõ ràng. Strangler không chỉ là đặt một reverse proxy trước hai ứng dụng; nó là chiến lược chuyển giao trách nhiệm nghiệp vụ và dữ liệu có kiểm soát.

## 1. Strangler Pattern giải quyết vấn đề gì?

Một hệ thống cũ có thể đang vận hành ổn định nhưng khó thay đổi vì:

- Nhiều nghiệp vụ khác nhau dùng chung một mô hình dữ liệu và một codebase.
- Một thay đổi nhỏ gây ảnh hưởng đến nhiều chức năng.
- Công nghệ, thư viện hoặc nền tảng đã khó bảo trì.
- Quy tắc nghiệp vụ nằm rải rác trong stored procedure, batch job, UI và service.
- Không có kiểm thử đủ tốt để biết hành vi nào cần được giữ nguyên.
- Việc dừng hệ thống để chuyển đổi gây gián đoạn kinh doanh.
- Dữ liệu và tích hợp bên ngoài khiến việc thay thế đồng loạt có rủi ro cao.

Strangler cho phép nhóm thay đổi từng lát cắt có giá trị. Hệ thống cũ và phần mới cùng tồn tại trong một giai đoạn; một điểm định tuyến quyết định yêu cầu nào đi đến đâu. Khi một năng lực đã được chuyển giao và xác minh, lưu lượng của năng lực đó được chuyển sang phần mới.

Mục tiêu là giảm dần phạm vi trách nhiệm của hệ thống cũ mà vẫn duy trì hoạt động. Việc chuyển đổi phải có tiến trình, tiêu chí hoàn thành và kế hoạch xử lý khi phần mới gặp sự cố.

## 2. Ý tưởng cốt lõi: bọc, chuyển giao, loại bỏ

Strangler thường có ba hoạt động lớn:

1. **Bọc hệ thống hiện tại:** tạo một điểm vào hoặc lớp facade để kiểm soát cách client truy cập các năng lực đang có.
2. **Chuyển giao từng phần:** triển khai năng lực mới, xác minh kết quả rồi định tuyến các yêu cầu tương ứng sang phần mới.
3. **Loại bỏ phần cũ:** khi không còn consumer, dữ liệu và job nào phụ thuộc vào năng lực cũ, ngừng và xóa phần implementation đó.

~~~mermaid
flowchart TD
    C["Client / Consumer"] --> F["Facade / Router"]
    F --> L["Legacy System"]
    F --> N["New System"]
    L --> D[("Legacy Data")]
    N --> ND[("New Data")]
    F -. "Chuyển dần route theo capability" .-> N
~~~

Ban đầu, phần lớn yêu cầu vẫn đi đến hệ thống cũ. Sau mỗi đợt chuyển đổi, router đưa thêm một năng lực sang phần mới. Cuối cùng, các route cũ không còn được sử dụng và hệ thống legacy có thể được ngừng.

Không phải mọi dự án đều cần một facade mới hoàn toàn. Có thể dùng API gateway, reverse proxy, load balancer, router trong ứng dụng hoặc một adapter ở tầng application. Điểm quan trọng là có một nơi kiểm soát việc phân luồng và có thể thay đổi đích đến mà không buộc mọi client tự biết hai hệ thống.

## 3. Strangler không đồng nghĩa với viết lại toàn bộ

Viết lại toàn bộ thường cố xây một hệ thống thay thế có phạm vi lớn rồi chuyển tất cả người dùng tại một thời điểm. Strangler chia phạm vi thành các năng lực có thể triển khai và kiểm chứng độc lập.

| Tiêu chí | Thay thế đồng loạt | Strangler |
| --- | --- | --- |
| Phạm vi mỗi lần phát hành | Phần lớn hoặc toàn bộ hệ thống | Một năng lực hoặc lát cắt |
| Thời điểm chuyển đổi | Một lần cutover lớn | Nhiều lần chuyển giao |
| Hệ thống cũ | Tiếp tục phục vụ đến ngày chuyển đổi | Cùng tồn tại và thu hẹp dần |
| Rủi ro | Tập trung ở lần cutover lớn | Chia nhỏ nhưng cần quản lý trạng thái hai hệ thống |
| Kiểm chứng | Khó có phản hồi thực tế cho đến khi tích hợp lớn | Có thể kiểm chứng từng phần với người dùng và dữ liệu thực |
| Chi phí tạm thời | Có thể phải duy trì nhánh viết lại lâu dài | Phải vận hành hai implementation và lớp tương thích |

Strangler vẫn cần thiết kế đích đến rõ ràng. Nếu chỉ thêm route mới mà không xác định quyền sở hữu dữ liệu, hợp đồng và tiêu chí xóa code cũ, hệ thống có thể mắc kẹt ở trạng thái hai implementation tồn tại mãi mãi.

## 4. Chọn lát cắt chuyển đổi theo năng lực nghiệp vụ

Không nên chọn lát cắt chỉ dựa trên package, bảng hoặc số lượng class. Hãy bắt đầu từ một năng lực nghiệp vụ có thể mô tả bằng ngôn ngữ của người dùng và chuyên gia.

Ví dụ trong hệ thống bán hàng:

| Năng lực | Phạm vi có thể chuyển đổi |
| --- | --- |
| Tra cứu giá | Tính và trả giá bán cho một sản phẩm |
| Quản lý khách hàng | Tạo, cập nhật và tra cứu hồ sơ khách hàng |
| Giữ hàng | Kiểm tra và tạo reservation cho đơn |
| Thanh toán | Cấp phép, thu tiền và hoàn tiền |
| Theo dõi đơn | Trả trạng thái và lịch sử đơn hàng |

Một lát cắt tốt thường:

- Có giá trị nghiệp vụ đủ rõ để ưu tiên.
- Có đầu vào, đầu ra và consumer xác định.
- Có thể đặt một ranh giới sở hữu dữ liệu.
- Có thể chuyển giao mà không phải thay đổi quá nhiều năng lực khác.
- Có thể kiểm thử và quan sát độc lập.
- Có cách xử lý khi phần mới chưa sẵn sàng.

Nếu một năng lực phụ thuộc sâu vào nhiều chức năng legacy, hãy tìm seam nhỏ hơn hoặc tách phần phụ thuộc thành hợp đồng rõ trước khi chuyển.

## 5. Dùng Bounded Context để xác định ranh giới đích

DDD giúp nhóm nhận ra rằng một hệ thống legacy có thể chứa nhiều mô hình nghiệp vụ bị trộn lẫn. Strangler có thể chuyển từng Bounded Context hoặc một phần năng lực trong context đó sang implementation mới.

Ví dụ, một ứng dụng ERP cũ có class Customer dùng chung cho bán hàng, hóa đơn và hỗ trợ. Trong mô hình mới:

- Sales sở hữu dữ liệu khách mua và thông tin cần để lập giao dịch.
- Billing sở hữu dữ liệu pháp lý và thông tin xuất hóa đơn.
- Support sở hữu thông tin liên hệ phục vụ xử lý yêu cầu hỗ trợ.

Không nên chuyển nguyên class Customer của legacy sang một service mới rồi tiếp tục dùng chung. Hãy xác định mô hình đích và hợp đồng giữa các context. Dữ liệu cũ có thể cần mapping sang nhiều mô hình khác nhau.

Một Bounded Context không bắt buộc phải trở thành một microservice ngay. Nó có thể được chuyển vào module mới trong cùng modular monolith trước, rồi tách deployment sau nếu có lý do vận hành.

## 6. Tìm seam: nơi có thể cắt mà không làm hỏng hệ thống

Seam là điểm mà nhóm có thể thay đổi hành vi hoặc đích xử lý mà không phải sửa toàn bộ consumer. Seam có thể nằm ở:

- API endpoint hoặc controller.
- Application service mà nhiều màn hình đang gọi.
- Interface hoặc adapter giữa module.
- Message handler hoặc event consumer.
- Batch job hoặc lịch chạy tác vụ.
- Một lớp truy cập dữ liệu được nhiều chức năng sử dụng.
- API gateway hoặc reverse proxy trước ứng dụng.

Ví dụ, nếu tất cả client gọi trực tiếp database hoặc endpoint nội bộ của legacy, việc chuyển một năng lực sẽ khó vì không có một điểm định tuyến tập trung. Nhóm có thể tạo API facade trước, chuyển client sang facade, sau đó mới thay implementation phía sau.

Không phải mọi seam đều phải là HTTP. Trong một monolith, có thể dùng interface Java; trong hệ thống tích hợp, có thể dùng message contract. Hãy chọn seam theo cách consumer đang tương tác và khả năng thay thế implementation.

## 7. Strangler Facade và Router

Facade cung cấp một hợp đồng ổn định cho consumer trong khi implementation phía sau thay đổi. Router quyết định yêu cầu được xử lý bởi legacy hay phần mới.

Ví dụ hợp đồng:

~~~java
public interface PriceQuote {
    QuoteResult calculate(QuoteRequest request);
}
~~~

Trong giai đoạn chuyển đổi, có thể có hai implementation:

~~~java
public final class LegacyPriceQuote implements PriceQuote {
    private final LegacyPricingClient legacy;

    public LegacyPriceQuote(LegacyPricingClient legacy) {
        this.legacy = legacy;
    }

    @Override
    public QuoteResult calculate(QuoteRequest request) {
        return legacy.calculate(request);
    }
}

public final class NewPriceQuote implements PriceQuote {
    private final PricingApplication pricing;

    public NewPriceQuote(PricingApplication pricing) {
        this.pricing = pricing;
    }

    @Override
    public QuoteResult calculate(QuoteRequest request) {
        return pricing.calculate(request);
    }
}
~~~

Router có thể chọn implementation theo cấu hình:

~~~java
public final class RoutingPriceQuote implements PriceQuote {
    private final PriceQuote legacy;
    private final PriceQuote modern;
    private final MigrationRoutingPolicy routing;

    public RoutingPriceQuote(
        PriceQuote legacy,
        PriceQuote modern,
        MigrationRoutingPolicy routing
    ) {
        this.legacy = legacy;
        this.modern = modern;
        this.routing = routing;
    }

    @Override
    public QuoteResult calculate(QuoteRequest request) {
        return routing.useNewImplementation(request)
            ? modern.calculate(request)
            : legacy.calculate(request);
    }
}
~~~

Đây là ví dụ cấu trúc. Trong triển khai thực tế, routing policy cần ổn định theo một khóa nghiệp vụ, có thể cấu hình theo tenant, nhóm người dùng hoặc capability. Không nên để cùng một giao dịch lúc đọc từ legacy, lúc ghi sang hệ thống mới một cách tùy tiện.

## 8. Chuyển route theo capability, tenant hoặc nhóm người dùng

Có nhiều cách bật dần phần mới:

| Chiến lược | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| Theo capability | Toàn bộ yêu cầu của một năng lực chuyển sang implementation mới | Năng lực có ranh giới rõ |
| Theo tenant | Một nhóm khách hàng/đơn vị dùng hệ thống mới | B2B hoặc hệ thống nhiều tenant |
| Theo nhóm người dùng | Nhóm nội bộ hoặc beta user dùng phần mới trước | Cần thử nghiệm thực tế có kiểm soát |
| Theo tỷ lệ | Một tỷ lệ request được đưa sang phần mới | Phù hợp với traffic có thể phân chia và dữ liệu nhất quán |
| Theo vùng hoặc kênh | Một khu vực hoặc kênh bán hàng chuyển trước | Hệ thống có khác biệt vận hành theo vùng/kênh |

Chuyển theo capability thường dễ hiểu hơn vì một năng lực có một owner và một implementation chính tại một thời điểm. Chuyển theo tỷ lệ chỉ phù hợp khi có thể bảo đảm một thực thể nghiệp vụ không bị ghi bởi hai implementation cạnh tranh. Ví dụ, không nên định tuyến mỗi request cập nhật của cùng một đơn hàng ngẫu nhiên sang hai hệ thống.

Routing key cần ổn định và có thể quan sát. Nếu dùng tenant, hãy bảo đảm mọi request liên quan cùng tenant đi đến cùng implementation trong giai đoạn chuyển giao, trừ khi mô hình dữ liệu đã hỗ trợ rõ trạng thái coexistence.

## 9. Quyền sở hữu dữ liệu trong giai đoạn cùng tồn tại

Đây thường là phần khó nhất của Strangler. Khi legacy và hệ thống mới cùng chạy, cần biết nơi nào là nguồn chính thức của từng dữ liệu.

Một quy tắc an toàn là xác định **một owner có quyền ghi chính thức cho mỗi tập dữ liệu nghiệp vụ tại một thời điểm**. Hệ thống khác có thể giữ bản sao phục vụ đọc hoặc chuyển đổi, nhưng phải biết bản sao đó được cập nhật như thế nào.

Ví dụ:

| Dữ liệu | Owner trong giai đoạn đầu | Owner sau khi chuyển |
| --- | --- | --- |
| Hồ sơ khách hàng | Legacy CRM | Customer Management mới |
| Báo giá | Legacy Sales | Pricing/Sales mới |
| Reservation tồn kho | Legacy Inventory | Inventory mới |
| Giao dịch thanh toán | Payment provider hoặc module legacy | Payment context mới, tùy quyền sở hữu |

Không nên để cả legacy và phần mới cùng ghi vào một dữ liệu chủ mà không có cơ chế phân xử. Hai nguồn ghi có thể tạo ra trạng thái không thể hòa giải.

Hãy ghi rõ owner theo từng capability hoặc aggregate, không chỉ theo database. Một database có thể chứa nhiều schema nhưng ownership vẫn phải rõ.

## 10. Các chiến lược chuyển dữ liệu

Tùy khả năng của legacy và yêu cầu nghiệp vụ, có thể chọn một trong các cách:

**Chuyển dữ liệu một lần theo lát cắt**

Đóng băng hoặc giới hạn cập nhật trong một khoảng ngắn, chuyển dữ liệu, đối soát rồi đổi owner và route. Cách này phù hợp khi có thể tạo cửa sổ bảo trì nhỏ.

**Backfill rồi đồng bộ thay đổi**

Sao chép dữ liệu lịch sử trước, sau đó ghi nhận các thay đổi phát sinh trong khi backfill. Khi độ trễ đồng bộ bằng không hoặc nằm trong ngưỡng chấp nhận, chuyển owner.

**Đọc từ nguồn cũ, ghi vào nguồn mới**

Trong một giai đoạn, hệ thống mới có thể đọc dữ liệu từ legacy qua adapter nhưng chỉ ghi thay đổi mới vào kho của nó. Cần có quy tắc rõ về việc dữ liệu nào được phép đọc và khi nào kết thúc phụ thuộc.

**Projection hoặc bản sao phục vụ đọc**

Consumer duy trì read model cục bộ từ event hoặc change feed. Bản sao cần có version/checkpoint và cơ chế rebuild.

Không có chiến lược nào phù hợp mọi trường hợp. Cần đánh giá khối lượng dữ liệu, khả năng ghi nhận thay đổi, yêu cầu downtime, độ trễ chấp nhận được và khả năng rollback.

## 11. Tránh dual-write không có kiểm soát

Một anti-pattern phổ biến là ghi cùng một thay đổi vào cả legacy database và new database trong một request:

~~~text
Request
  -> write Legacy DB
  -> write New DB
  -> return success
~~~

Nếu lần ghi đầu thành công nhưng lần thứ hai thất bại, hai hệ thống không còn đồng nhất. Nếu retry, thao tác có thể bị thực hiện lặp. Một transaction thông thường không thể tự bảo đảm nguyên tử trên hai database độc lập.

Các cách giảm rủi ro:

- Chọn một write owner duy nhất trong từng giai đoạn.
- Dùng transactional outbox ở hệ thống sở hữu để công bố thay đổi đáng tin cậy.
- Dùng CDC/change data capture khi phù hợp với nền tảng legacy.
- Consumer xử lý idempotent và lưu checkpoint.
- Đối soát dữ liệu theo khóa và version.
- Dùng saga hoặc quy trình bù trừ khi nghiệp vụ cần phối hợp nhiều hệ thống.

Dual-write chỉ nên được dùng khi có thiết kế rõ cho lỗi từng phần, retry, deduplication và reconciliation. Không nên xem việc gọi hai repository liên tiếp là cơ chế đồng bộ dữ liệu.

## 12. Expand-and-Contract cho schema và hợp đồng

Trong thời gian coexistence, legacy và phần mới có thể cần cùng sử dụng một hợp đồng hoặc schema. Thay đổi phá vỡ tương thích có thể khiến một phía hỏng.

Expand-and-Contract chia thay đổi thành các bước:

1. **Expand:** thêm trường, endpoint hoặc event version mới theo cách tương thích ngược.
2. Triển khai consumer có thể đọc cả dạng cũ và mới.
3. Chuyển producer sang phát dạng mới hoặc ghi dữ liệu mới.
4. Backfill dữ liệu cũ và xác minh.
5. Theo dõi để bảo đảm không còn consumer dùng dạng cũ.
6. **Contract:** xóa trường, endpoint hoặc schema cũ sau khi mọi consumer đã chuyển.

Ví dụ, khi thay customer_code bằng customer_id:

- Thêm customer_id nhưng vẫn giữ customer_code.
- Backfill customer_id từ dữ liệu hiện có.
- Consumer mới đọc customer_id và có fallback trong giai đoạn chuyển.
- Producer ghi customer_id.
- Xác nhận mọi consumer đã dùng ID mới.
- Xóa customer_code khi không còn phụ thuộc.

Không nên xóa cột hoặc đổi ý nghĩa field ngay khi phần mới đã được triển khai. Các phiên bản ứng dụng có thể chạy đồng thời trong rolling deployment.

## 13. Chuyển một năng lực theo từng giai đoạn

Một quy trình chuyển đổi capability có thể gồm:

~~~mermaid
flowchart TD
    A["Khảo sát capability và consumer"] --> B["Đặt facade / seam"]
    B --> C["Đặc tả hành vi và dữ liệu"]
    C --> D["Xây implementation mới"]
    D --> E["Backfill / đồng bộ dữ liệu"]
    E --> F["So sánh kết quả và kiểm thử"]
    F --> G{"Đạt tiêu chí cutover?"}
    G -->|Không| D
    G -->|Có| H["Chuyển route sang phần mới"]
    H --> I["Theo dõi và giữ rollback window"]
    I --> J{"Ổn định và không còn phụ thuộc cũ?"}
    J -->|Chưa| I
    J -->|Rồi| K["Ngừng capability legacy"]
~~~

Không phải mọi capability cần đầy đủ tất cả bước giống nhau. Một API chỉ đọc có thể chuyển đơn giản hơn một nghiệp vụ cập nhật tài chính. Với dữ liệu quan trọng, cần bổ sung đối soát và kế hoạch khôi phục.

## 14. Xác minh hành vi tương đương trước khi cutover

Phần mới cần đáp ứng các hành vi nghiệp vụ đã được xác nhận. Không nên chỉ so sánh response HTTP hoặc số lượng bản ghi.

Các cách xác minh:

- **Characterization tests:** ghi lại hành vi hiện tại của legacy qua các tình huống đại diện.
- **Contract tests:** xác minh consumer và provider tuân thủ hợp đồng.
- **Golden master:** lưu kết quả chuẩn cho bộ đầu vào xác định, dùng so sánh khi có thể.
- **Shadow traffic:** gửi bản sao request đến implementation mới để so sánh, nhưng chỉ một phía được phép tạo side effect.
- **Data reconciliation:** đối chiếu số lượng, tổng tiền, trạng thái và các quan hệ dữ liệu.
- **Business acceptance:** chuyên gia xác nhận kết quả và các trường hợp ngoại lệ.

Không phải kết quả nào cũng cần giống từng byte. Phần mới có thể trả lỗi rõ hơn hoặc dùng mô hình dữ liệu khác, nhưng các kết quả nghiệp vụ cần được xác nhận. Nếu có khác biệt có chủ đích, phải ghi lại và được owner nghiệp vụ chấp thuận.

## 15. Shadow Traffic và giới hạn side effect

Shadow traffic giúp kiểm tra implementation mới trên request thực tế mà chưa chuyển quyền xử lý chính thức.

~~~mermaid
flowchart LR
    C["Client Request"] --> R["Router"]
    R --> L["Legacy: trả kết quả chính"]
    R -. "Bản sao chỉ đọc / shadow" .-> N["New: tính kết quả so sánh"]
    L --> O["Response cho client"]
    N --> M["Metrics / Diff"]
~~~

Shadow implementation không được gửi email, thu tiền, tạo reservation, phát lệnh giao hàng hoặc thực hiện side effect thật nếu mục tiêu chỉ là so sánh. Có thể dùng dữ liệu test, sandbox hoặc chế độ dry-run.

Nếu implementation mới cần đọc trạng thái mà chỉ legacy có, hãy dùng bản sao hoặc adapter đọc được kiểm soát. Không nên để shadow traffic ghi ngược vào nguồn dữ liệu chính.

Kết quả so sánh cần được phân loại:

- Khác biệt do lỗi trong implementation mới.
- Khác biệt do dữ liệu không đồng bộ.
- Khác biệt do thời gian hoặc trạng thái thay đổi giữa hai lần xử lý.
- Khác biệt có chủ đích do quy tắc mới.

Chỉ số khác biệt không giải thích được phải được xử lý trước cutover.

## 16. Cutover: chuyển quyền xử lý sang hệ thống mới

Cutover là thời điểm router chuyển một capability hoặc nhóm dữ liệu sang implementation mới. Trước khi chuyển, cần xác định:

- Route và routing key chính xác.
- Owner ghi dữ liệu sau cutover.
- Trạng thái đồng bộ cuối cùng và checkpoint.
- Consumer, job và tích hợp nào cần chuyển theo.
- Điều kiện dừng hoặc hủy cutover.
- Cách rollback và dữ liệu phát sinh sau cutover sẽ được xử lý ra sao.

Một cutover có thể diễn ra theo các bước:

1. Dừng hoặc hạn chế ghi trong phạm vi chuyển nếu cần.
2. Chờ event/change feed xử lý đến checkpoint đã thống nhất.
3. Đối soát dữ liệu và xác nhận không còn sai lệch nghiêm trọng.
4. Chuyển route và write ownership.
5. Chạy smoke test với một số giao dịch kiểm soát.
6. Theo dõi error rate, latency, business metrics và dữ liệu.
7. Mở rộng lưu lượng hoặc tenant theo kế hoạch.

Nếu hệ thống hỗ trợ chuyển không downtime, có thể không cần dừng ghi toàn bộ. Nhưng vẫn phải có quy tắc xử lý request đang bay, event đến trễ và transaction chưa hoàn tất tại thời điểm chuyển.

## 17. Rollback không chỉ là đổi route về legacy

Rollback đơn giản nếu phần mới chưa ghi dữ liệu hoặc dữ liệu mới chưa được coi là nguồn chính thức. Khi phần mới đã nhận write, đổi route về legacy có thể làm mất hoặc bỏ qua thay đổi mới.

Trước cutover, hãy phân loại:

- **Rollback kỹ thuật:** chuyển route về legacy khi phần mới lỗi, dữ liệu chưa thay đổi hoặc có thể bỏ phần thay đổi.
- **Roll-forward:** sửa lỗi trên hệ thống mới và tiếp tục, khi dữ liệu đã được ghi theo mô hình mới.
- **Reverse migration:** chuyển dữ liệu phát sinh sau cutover trở lại legacy, nếu có mapping hai chiều an toàn.
- **Compensation:** ghi hành động nghiệp vụ bù trừ thay vì khôi phục trạng thái bằng cách sửa dữ liệu trực tiếp.

Một kế hoạch rollback cần trả lời: những giao dịch nào đã commit ở hệ thống mới, ai là owner của chúng, legacy có thể đọc được không, event nào đã phát, và có side effect bên ngoài nào không thể đảo ngược?

Với thanh toán, vận chuyển hoặc hóa đơn, rollback có thể cần refund, cancel shipment hoặc credit note thay vì chỉ đổi trạng thái.

## 18. Chuyển đổi dữ liệu lịch sử và định danh

Legacy và mô hình mới có thể dùng định danh, mã trạng thái hoặc cấu trúc khác nhau. Cần có mapping rõ:

| Dữ liệu legacy | Mô hình mới | Việc cần xác minh |
| --- | --- | --- |
| customer_code | CustomerId | Duy nhất, quy tắc chuẩn hóa và dữ liệu trùng |
| order_status | OrderStatus | Mapping trạng thái cũ, trạng thái không nhận diện |
| amount + currency_code | Money | Độ chính xác, làm tròn và tiền tệ |
| created_date | occurredAt | Múi giờ và ý nghĩa thời điểm |
| deleted_flag | Lifecycle state | Phân biệt xóa mềm, hủy và lưu trữ |

Không nên coi dữ liệu legacy là đúng tuyệt đối. Trong quá trình migration có thể phát hiện bản ghi trùng, thiếu quan hệ, giá trị không hợp lệ hoặc trạng thái không còn được dùng.

Hãy xác định:

- Quy tắc làm sạch và xử lý dữ liệu lỗi.
- Khóa mapping giữa ID cũ và ID mới.
- Cách giữ lại tham chiếu để tra cứu lịch sử.
- Cách xử lý record được tạo hoặc cập nhật trong lúc backfill.
- Cách đối soát sau chuyển.
- Chính sách lưu trữ hoặc xóa dữ liệu cũ.

Việc chuyển dữ liệu cần có log và khả năng chạy lại an toàn. Migration script nên idempotent hoặc có checkpoint để không tạo bản ghi trùng khi retry.

## 19. Xử lý consumer và tích hợp chưa được chuyển

Một capability có thể đã chuyển sang hệ thống mới nhưng vẫn còn consumer cũ gọi trực tiếp legacy. Ví dụ, màn hình mới dùng API mới trong khi batch job ban đêm vẫn truy cập bảng cũ.

Hãy lập inventory consumer:

- Web/mobile client.
- Admin tool.
- Batch job và scheduler.
- Report/BI.
- External partner.
- Message producer/consumer.
- Stored procedure và trigger.
- Data export/import.
- Script vận hành hoặc hỗ trợ.

Không nên ngừng endpoint hoặc bảng cũ chỉ vì luồng chính đã chuyển. Cần xác minh toàn bộ consumer, chuyển chúng sang contract mới hoặc có kế hoạch retire rõ ràng.

Một cách hữu ích là theo dõi access log theo route, client identity và thời gian. Trước khi xóa một API cũ, cần chứng minh nó không còn được gọi trong một khoảng thời gian đại diện cho chu kỳ nghiệp vụ.

## 20. Observability trong giai đoạn coexistence

Khi hai implementation cùng tồn tại, cần biết request nào được xử lý ở đâu và kết quả ra sao.

Các tín hiệu cần theo dõi:

- Route được chọn và phiên bản implementation.
- Request count theo capability, tenant hoặc nhóm người dùng.
- Error rate và latency của legacy/new.
- Số lượng event chờ, độ trễ đồng bộ và dead-letter.
- Kết quả shadow comparison.
- Data reconciliation mismatch.
- Số giao dịch rollback hoặc compensation.
- Tỷ lệ request còn gọi endpoint legacy.

Dùng correlation ID xuyên facade, application service, message và adapter để truy vết một quy trình. Log cần tránh chứa thông tin cá nhân hoặc dữ liệu nhạy cảm không cần thiết.

Dashboard nên hiển thị rõ tỷ lệ lưu lượng ở mỗi implementation và các cảnh báo cutover. Nếu router chuyển lưu lượng mà nhóm không thể biết request đã đi đâu, việc vận hành và rollback sẽ khó khăn.

## 21. Feature Flag và cấu hình routing

Feature flag có thể kiểm soát việc bật implementation mới:

~~~java
public interface MigrationRoutingPolicy {
    boolean useNewImplementation(QuoteRequest request);
}
~~~

Policy có thể đọc cấu hình hoặc một dịch vụ flag:

~~~text
pricing.new.enabled = true
pricing.new.tenants = tenant-12, tenant-18
pricing.new.percentage = 0
~~~

Đây là ví dụ cấu hình minh họa. Hệ thống cần quy định thứ tự ưu tiên giữa kill switch, allowlist, tenant và percentage; cấu hình phải được audit và thay đổi an toàn.

Feature flag phục vụ chuyển đổi cần có owner, ngày hết hạn và tiêu chí xóa. Nếu giữ vô thời hạn, code routing và hai implementation sẽ trở thành nợ kỹ thuật mới.

## 22. Strangler với hệ thống có database dùng chung

Đôi khi legacy và phần mới dùng cùng database trong thời gian đầu. Điều này có thể giúp giảm công sức migration, nhưng cũng dễ tạo phụ thuộc schema.

Nếu buộc phải dùng chung:

- Xác định bảng hoặc schema nào thuộc owner nào.
- Chỉ owner được ghi dữ liệu chủ.
- Consumer dùng API hoặc view/projection được công bố.
- Không chia sẻ ORM entity giữa codebase cũ và mới.
- Thay đổi schema theo expand-and-contract.
- Theo dõi truy vấn từ legacy để biết khi nào có thể tách.
- Có kế hoạch đưa dữ liệu sang schema/database riêng khi cần.

Một database vật lý chung không có nghĩa là quyền sở hữu chung. Nếu cả hai implementation cùng cập nhật cùng một bảng mà không có cơ chế concurrency và migration rõ, Strangler sẽ làm tăng coupling thay vì giảm nó.

## 23. Strangler cho read path và write path

Đọc và ghi có thể được chuyển ở các thời điểm khác nhau, nhưng cần xác định rõ nguồn dữ liệu và tính nhất quán.

**Read path chuyển trước**

Phần mới có thể xây read model hoặc API truy vấn mới trong khi write vẫn thuộc legacy. Cách này phù hợp để kiểm tra mô hình đọc, hiệu năng hoặc trải nghiệm người dùng. Read model cần được cập nhật từ nguồn chính thức.

**Write path chuyển trước**

Phần mới trở thành owner của ghi; đọc có thể tạm thời qua legacy hoặc projection. Cách này khó hơn vì dữ liệu mới phải được phản ánh cho consumer còn ở hệ thống cũ. Cần đồng bộ một chiều có kiểm soát hoặc chuyển read path cùng lúc.

**Chuyển read và write cùng nhau**

Phù hợp khi capability có ranh giới dữ liệu gọn và có thể cutover nhất quán. Cần chuẩn bị backfill, route, consumer và rollback.

Không nên định tuyến read và write độc lập mà không hiểu consistency model. Người dùng có thể ghi thành công ở hệ thống mới nhưng đọc lại từ legacy và thấy dữ liệu cũ.

## 24. Khi nào Strangler phù hợp?

Strangler thường phù hợp khi:

- Hệ thống legacy vẫn phải hoạt động trong quá trình hiện đại hóa.
- Có thể xác định các capability hoặc Bounded Context tương đối độc lập.
- Có seam để đặt facade hoặc router.
- Nhóm có thể chuyển dữ liệu và consumer theo từng phần.
- Cần giảm rủi ro của một lần cutover lớn.
- Có thể duy trì hai implementation trong một khoảng thời gian có giới hạn.
- Có đủ observability và năng lực vận hành để theo dõi coexistence.

Ví dụ phù hợp có thể là chuyển module tra cứu giá, quản lý khách hàng hoặc inventory ra khỏi ứng dụng ERP cũ theo từng năng lực, trong khi các phần khác tiếp tục chạy.

## 25. Khi nào Strangler không phù hợp hoặc cần thận trọng?

Hãy cân nhắc cách khác hoặc giảm phạm vi nếu:

- Không có ranh giới nghiệp vụ đủ rõ và các chức năng thay đổi cùng nhau.
- Hệ thống cũ không có seam để định tuyến, mọi chức năng phụ thuộc trực tiếp vào database.
- Dữ liệu dùng chung có nhiều writer và không thể xác định owner.
- Hai implementation không thể cùng tồn tại vì phụ thuộc nền tảng hoặc dữ liệu không tương thích.
- Chi phí vận hành hai hệ thống lớn hơn lợi ích của chuyển đổi dần.
- Có thể thay thế toàn bộ trong một cửa sổ bảo trì nhỏ với rủi ro thấp.
- Không có khả năng quan sát, đối soát hoặc rollback.

Strangler không tự giải quyết coupling. Nếu nhóm chuyển từng package nhưng vẫn chia sẻ database, schema và mô hình mutable, hệ thống mới có thể tiếp tục phụ thuộc vào legacy. Cần đầu tư vào boundary và ownership trước khi mở rộng chuyển đổi.

## 26. Các lỗi thường gặp khi áp dụng Strangler

**Chuyển code trước khi xác định capability.** Nhóm có thể chỉ di chuyển class nhưng không chuyển được trách nhiệm nghiệp vụ. Hãy chọn lát cắt theo hành vi và owner.

**Đặt facade nhưng để client tiếp tục gọi legacy trực tiếp.** Router không kiểm soát được lưu lượng. Hãy chuyển consumer sang một điểm vào có thể quản lý.

**Cả hai hệ thống cùng ghi dữ liệu chủ.** Dẫn đến xung đột và khó đối soát. Xác định write owner theo giai đoạn.

**Dual-write mà không có outbox hoặc reconciliation.** Một phía có thể commit trong khi phía kia thất bại. Thiết kế đồng bộ và xử lý lặp rõ ràng.

**Shadow traffic tạo side effect.** Có thể thu tiền hoặc giữ hàng hai lần. Chỉ dùng chế độ dry-run/sandbox cho bản sao request.

**Cutover không có rollback plan.** Đổi route về legacy không khôi phục các giao dịch đã ghi ở hệ thống mới. Xác định roll-forward, reverse migration hoặc compensation.

**Không chuyển batch job và consumer phụ.** Luồng chính hoạt động nhưng dữ liệu vẫn bị legacy ghi lại. Lập danh sách mọi consumer.

**Giữ hai implementation mãi mãi.** Feature flag và adapter trở thành nợ kỹ thuật. Đặt tiêu chí và thời hạn loại bỏ phần cũ.

**Chọn tỷ lệ traffic ngẫu nhiên cho dữ liệu có trạng thái.** Các request của cùng một Aggregate có thể đi hai nơi. Dùng routing key ổn định và ownership rõ.

**Không đối soát dữ liệu.** Hệ thống có thể trả response thành công nhưng dữ liệu lịch sử thiếu hoặc sai. Xây reconciliation và xử lý mismatch.

## 27. Quy trình thực hiện một đợt Strangler

1. **Khảo sát hệ thống hiện tại:** lập danh sách capability, consumer, database, batch job, tích hợp và hành vi quan trọng.
2. **Chọn lát cắt:** ưu tiên capability có giá trị, seam rõ và phạm vi dữ liệu có thể sở hữu.
3. **Xác định mô hình đích:** làm rõ Bounded Context, Aggregate, ngôn ngữ và quy tắc.
4. **Đặc tả contract:** định nghĩa API, command, query, event và lỗi mà consumer cần.
5. **Tạo facade/router:** chuyển client qua một điểm định tuyến có thể cấu hình và quan sát.
6. **Xác định data owner:** quy định nguồn ghi chính thức, dữ liệu sao chép và consistency.
7. **Xây implementation mới:** triển khai hành vi, persistence adapter và test theo tình huống.
8. **Chuyển dữ liệu:** backfill, CDC/outbox hoặc migration theo cửa sổ đã thống nhất.
9. **Kiểm chứng:** characterization, contract, shadow, reconciliation và business acceptance.
10. **Cutover có kiểm soát:** chuyển route và write ownership theo kế hoạch.
11. **Theo dõi và xử lý:** quan sát lỗi, latency, mismatch, consumer cũ và yêu cầu rollback.
12. **Retire legacy capability:** chuyển mọi consumer, dừng job, thu hồi quyền ghi và xóa implementation cũ khi đủ bằng chứng.
13. **Lặp lại:** chọn capability tiếp theo và cập nhật kế hoạch tổng thể.

## 28. Checklist trước khi chuyển route

- Capability đã có phạm vi và owner nghiệp vụ rõ chưa?
- Mọi consumer và job liên quan đã được nhận diện chưa?
- Có facade hoặc seam kiểm soát mọi request không?
- Contract mới có tương thích với consumer không?
- Implementation mới đã vượt qua characterization và acceptance test chưa?
- Dữ liệu đã backfill và đối soát chưa?
- Có một write owner rõ ràng sau cutover không?
- Event/change feed có checkpoint và idempotency không?
- Shadow mode có chặn side effect không?
- Routing key có ổn định cho cùng một Aggregate/tenant không?
- Có dashboard và correlation ID để truy vết không?
- Có tiêu chí dừng, rollback, roll-forward hoặc compensation không?
- Có danh sách consumer legacy cần chuyển tiếp không?
- Có điều kiện retire code và schema cũ không?

## 29. Nguyên tắc cần ghi nhớ

Strangler Pattern hiện đại hóa hệ thống bằng cách chuyển giao từng năng lực nghiệp vụ từ legacy sang implementation mới thông qua một điểm định tuyến có kiểm soát. DDD giúp chọn lát cắt dựa trên Bounded Context, mô hình và quyền sở hữu dữ liệu; facade và router giúp thay implementation mà không buộc mọi consumer biết quá trình chuyển đổi.

Trong giai đoạn coexistence, hãy xác định một write owner cho từng dữ liệu chủ, quản lý backfill và đồng bộ thay đổi, tránh dual-write thiếu kiểm soát, kiểm chứng hành vi trước cutover và chuẩn bị phương án rollback phù hợp với dữ liệu đã phát sinh. Sau khi mọi consumer đã chuyển và không còn phụ thuộc vào implementation cũ, hãy retire capability legacy. Chuyển đổi thành công khi trách nhiệm nghiệp vụ và dữ liệu thực sự được chuyển giao, không chỉ khi code mới đã được triển khai.
