# Thiết kế một mô hình dùng chung cho mọi ngữ cảnh

Trong Domain-Driven Design (DDD), một trong những sai lầm thiết kế phổ biến là cố tạo một mô hình domain duy nhất rồi dùng nó cho mọi bộ phận, mọi quy trình và mọi bounded context. Ý định ban đầu thường có vẻ hợp lý: nếu toàn doanh nghiệp cùng nói về Customer, Order, Product hay Account thì tại sao không định nghĩa một lớp Customer, một lớp Order và một bộ schema chung để tất cả hệ thống sử dụng?

Vấn đề nằm ở chỗ cùng một từ trong doanh nghiệp không nhất thiết mang cùng ý nghĩa, trách nhiệm và vòng đời trong mọi ngữ cảnh. Bộ phận bán hàng quan tâm đến khách hàng tiềm năng, quan hệ thương mại và điều kiện mua. Bộ phận hỗ trợ quan tâm đến danh tính liên hệ, lịch sử tương tác và quyền truy cập hỗ trợ. Bộ phận thanh toán quan tâm đến chủ thể chịu trách nhiệm thanh toán, phương thức thanh toán và rủi ro. Những góc nhìn đó có thể cùng nói về một người hoặc tổ chức, nhưng chúng phục vụ các quy tắc nghiệp vụ khác nhau.

DDD khuyến khích một mô hình rõ ràng bên trong từng bounded context. Mỗi context có ubiquitous language, trách nhiệm và ranh giới nhất quán riêng. Các context hợp tác thông qua contract và cơ chế tích hợp được thiết kế có chủ đích. Mục tiêu là giữ mô hình đủ sát với nghiệp vụ của context, đồng thời kiểm soát việc dịch và trao đổi thông tin giữa các context.

## 1. Vì sao một mô hình toàn cục nghe có vẻ hấp dẫn?

Một mô hình dùng chung thường được đề xuất để giải quyết những vấn đề thực tế:

- Tránh định nghĩa lặp lại Customer, Product hoặc Address.
- Dùng chung một schema database và API.
- Giảm số lượng DTO và mapping.
- Giữ dữ liệu đồng nhất giữa các hệ thống.
- Cho phép một thay đổi được triển khai một lần rồi mọi nơi cùng sử dụng.
- Tạo cảm giác rằng toàn doanh nghiệp có một nguồn sự thật duy nhất cho mọi khái niệm.

Những mục tiêu này có giá trị, nhưng giải pháp “một mô hình cho tất cả” thường trộn lẫn hai vấn đề khác nhau: chia sẻ dữ liệu và chia sẻ ý nghĩa nghiệp vụ. Hai context có thể cần trao đổi cùng một định danh hoặc một số thuộc tính, nhưng không nhất thiết phải dùng chung object model hay cùng chịu một quy tắc.

Ví dụ, Sales và Customer Support đều cần biết tên khách hàng và mã khách hàng. Điều đó không có nghĩa Sales phải dùng trạng thái ticket, mức độ ưu tiên hỗ trợ hoặc chính sách SLA trong domain model của mình. Tương tự, Support không cần hiểu toàn bộ scoring, pipeline hay điều kiện chiết khấu mà Sales dùng để quản lý cơ hội bán hàng.

## 2. Cùng một thuật ngữ không đảm bảo cùng một khái niệm

Ubiquitous Language là ngôn ngữ chung giữa chuyên gia nghiệp vụ và đội phát triển trong một model. Nó không có nghĩa mọi phòng ban phải ép mọi cách dùng từ vào cùng một định nghĩa toàn cục.

Một từ có thể có nhiều nghĩa hợp lệ:

| Thuật ngữ | Sales | Customer Support | Billing |
|---|---|---|---|
| Customer | Người mua hoặc tổ chức có quan hệ thương mại | Người liên hệ cần hỗ trợ | Chủ thể chịu trách nhiệm thanh toán |
| Account | Hồ sơ khách hàng/cơ hội bán hàng | Hồ sơ truy cập hoặc hồ sơ hỗ trợ | Tài khoản công nợ hoặc tài khoản thanh toán |
| Order | Yêu cầu mua hàng và trạng thái thương mại | Đối tượng được tham chiếu trong khi xử lý khiếu nại | Căn cứ tính tiền và đối soát |
| Product | Mặt hàng được chào bán | Sản phẩm khách đang sử dụng và cần trợ giúp | Mã hàng dùng để lập hóa đơn |
| Address | Địa chỉ giao hàng hoặc liên hệ bán hàng | Địa chỉ liên hệ được xác minh | Địa chỉ lập hóa đơn theo quy định |

Các định nghĩa này không nhất thiết mâu thuẫn. Chúng mô tả những khía cạnh khác nhau của cùng thế giới nghiệp vụ. Khi ép chúng thành một class dùng chung, class đó dễ trở thành tập hợp field và trạng thái không phải context nào cũng hiểu hoặc có quyền thay đổi.

## 3. Bounded Context cho phép mô hình có ranh giới rõ

Bounded Context là ranh giới trong đó một domain model và ngôn ngữ của nó có ý nghĩa nhất quán. Bên trong context, một thuật ngữ nên có định nghĩa rõ và các quy tắc phải phối hợp với nhau.

Ví dụ:

~~~mermaid
flowchart LR
    subgraph Sales["Sales Context"]
        SC[Sales Customer]
        SO[Sales Order]
        OP[Opportunity]
    end
    subgraph Support["Support Context"]
        UC[Support Contact]
        TK[Support Ticket]
        SLA[SLA Policy]
    end
    subgraph Billing["Billing Context"]
        BP[Billing Party]
        INV[Invoice]
        PAY[Payment]
    end
    Sales -->|Customer reference / sales facts| Support
    Sales -->|Order submitted contract| Billing
~~~

Mỗi context có thể định nghĩa kiểu Customer hoặc Order riêng, vì mỗi kiểu phục vụ một model khác nhau. Khi dữ liệu cần được trao đổi, context gửi một contract có ý nghĩa rõ ràng thay vì chia sẻ toàn bộ domain object.

Điều này không có nghĩa phải tạo một microservice cho mỗi bounded context. Bounded context là ranh giới mô hình và ngôn ngữ. Nó có thể được triển khai trong một module, một ứng dụng modular monolith hoặc một nhóm service tùy nhu cầu vận hành.

## 4. Mô hình dùng chung biến thành nơi thỏa hiệp

Khi một class phải phục vụ nhiều context, nó thường tích lũy thuộc tính và trạng thái:

~~~java
public class Customer {
    private UUID id;
    private String name;
    private String email;

    // Sales
    private String leadSource;
    private String salesOwner;
    private String customerTier;

    // Support
    private boolean supportEnabled;
    private String supportSegment;
    private Integer priorityLevel;

    // Billing
    private String taxNumber;
    private String billingStatus;
    private String creditTerm;

    // Identity / access
    private String loginName;
    private boolean locked;
}
~~~

Class này trông tiện lợi nhưng không trả lời được:

- Context nào sở hữu từng thuộc tính?
- Ai có quyền thay đổi field?
- Field nào bắt buộc trong từng quy trình?
- Trạng thái nào hợp lệ đối với Sales nhưng vô nghĩa với Billing?
- Một thay đổi về Support có buộc Sales phải cập nhật dependency không?
- Hai context có dùng cùng một định nghĩa về active customer không?

Khi các câu hỏi này không có câu trả lời rõ, shared model trở thành nơi chứa các thỏa hiệp. Nó có thể có rất nhiều field nullable, boolean điều khiển hành vi, enum có giá trị chỉ một vài context hiểu và validation phụ thuộc vào caller.

## 5. Ví dụ: Customer trong nhiều bounded context

Giả sử một doanh nghiệp có ba nhu cầu:

**Sales** quản lý khách hàng tiềm năng, tài khoản thương mại, phân khúc, owner và điều kiện bán hàng.

**Support** quản lý người liên hệ, kênh liên hệ, xác minh danh tính, ticket và mức độ ưu tiên hỗ trợ.

**Billing** quản lý bên chịu trách nhiệm thanh toán, thông tin hóa đơn, mã số thuế, hạn mức và trạng thái công nợ.

Thay vì một Customer class toàn cục, mỗi context có model riêng:

~~~java
// Sales context
public record SalesCustomer(
        SalesCustomerId id,
        String displayName,
        SalesSegment segment,
        SalesOwnerId owner,
        SalesRelationshipStatus relationshipStatus
) {}

// Support context
public record SupportContact(
        SupportContactId id,
        ExternalCustomerRef customerRef,
        String preferredName,
        VerifiedContactChannel contactChannel,
        SupportEligibility eligibility
) {}

// Billing context
public record BillingParty(
        BillingPartyId id,
        LegalName legalName,
        TaxIdentifier taxIdentifier,
        BillingAddress billingAddress,
        CreditStatus creditStatus
) {}
~~~

Các model này có thể liên kết qua một định danh tham chiếu hoặc một contract tích hợp. Chúng không cần có cùng field, cùng lifecycle hay cùng validation.

Một người hoặc tổ chức trong thế giới thực có thể tương ứng với một SalesCustomer, nhiều SupportContact và một BillingParty. Quan hệ đó cần được diễn đạt theo nghiệp vụ và identity strategy, thay vì giả định luôn là một-một.

## 6. Không phải mọi dữ liệu trùng lặp đều là lỗi

Trong thiết kế database truyền thống, duplicate data thường được xem là điều cần tránh. Trong DDD, cần phân biệt:

- Dữ liệu bị nhân bản mà không có quy tắc đồng bộ rõ ràng.
- Dữ liệu được sao chép có chủ đích để một context sở hữu model riêng.
- Snapshot dữ liệu cần thiết để bảo toàn ý nghĩa của một giao dịch lịch sử.

Ví dụ, khi Order được xác nhận, hệ thống có thể lưu snapshot tên sản phẩm, đơn giá và địa chỉ giao hàng tại thời điểm đặt. Nếu catalog thay đổi sau đó, hóa đơn lịch sử vẫn cần phản ánh điều kiện tại thời điểm giao dịch.

Snapshot này không phải bản sao vô nghĩa. Nó bảo vệ ý nghĩa lịch sử của Order. Tuy nhiên, phải xác định rõ dữ liệu nào là snapshot, dữ liệu nào là reference đến nguồn hiện tại và dữ liệu nào cần được đồng bộ.

## 7. Phân biệt shared model với shared contract

Hai context cần tích hợp không có nghĩa chúng phải import cùng domain class.

**Shared domain model** thường làm consumer phụ thuộc vào cấu trúc và khái niệm nội bộ của provider.

**Shared contract** định nghĩa thông tin được trao đổi và ý nghĩa của thông tin đó. Contract có thể là API request/response, event schema, message hoặc file exchange.

Ví dụ, Billing chỉ cần nhận thông tin đơn đã xác nhận:

~~~java
public record OrderSubmittedV1(
        UUID eventId,
        UUID orderId,
        String customerReference,
        BigDecimal totalAmount,
        String currency,
        Instant submittedAt
) {}
~~~

Billing có thể chuyển contract này thành model của mình:

~~~java
public final class InvoiceDraft {
    private final InvoiceId id;
    private final BillingPartyId billTo;
    private final Money amountDue;
    private InvoiceStatus status;

    // constructor và hành vi thuộc Billing context
}
~~~

Contract mô tả dữ liệu có ý nghĩa tại ranh giới. InvoiceDraft là domain model riêng của Billing. Consumer không cần biết Order aggregate được lưu bằng bảng nào, có bao nhiêu OrderLine object hay tên method nội bộ là gì.

## 8. Context Map giúp mô tả quan hệ giữa các model

Context Map thể hiện cách các bounded context liên hệ và tích hợp. Nó giúp trả lời context nào cung cấp thông tin, context nào tiêu thụ, hai bên phối hợp bằng contract nào và có cần lớp dịch hay không.

Một sơ đồ đơn giản:

~~~mermaid
flowchart LR
    S[Sales Context] -->|OrderSubmitted event| B[Billing Context]
    S -->|Customer reference| C[Support Context]
    B -->|InvoiceIssued event| S
    C -->|Support case outcome| S
~~~

Sơ đồ này chưa chỉ rõ mọi chi tiết kỹ thuật, nhưng giúp đội ngũ thảo luận:

- Ai là upstream và ai là downstream?
- Consumer có phụ thuộc vào model nội bộ của provider không?
- Contract có versioning và compatibility rule không?
- Có cần Anti-Corruption Layer để dịch khái niệm không?
- Có phần model nào hai bên thực sự cần phát triển chung không?

Context Map nên được duy trì cùng kiến trúc thực tế. Một sơ đồ cũ hoặc chỉ phản ánh tổ chức dự kiến có thể làm người đọc hiểu sai ownership.

## 9. Anti-Corruption Layer bảo vệ model của consumer

Anti-Corruption Layer (ACL) là lớp dịch giúp một context chuyển đổi contract hoặc model bên ngoài thành khái niệm phù hợp với model nội bộ. Nó ngăn cách biệt ngữ, cấu trúc và quy tắc của upstream lan vào domain model của downstream.

Ví dụ, hệ thống CRM bên ngoài phát ra:

~~~json
{
  "partyCode": "P-1007",
  "lifeCycle": "A",
  "segmentCode": "ENT",
  "primaryContact": {
    "fullName": "Nguyen Van A",
    "mobile": "0900000000"
  }
}
~~~

Support context có thể không dùng khái niệm segment hoặc lifecycle theo nghĩa của CRM. ACL sẽ ánh xạ dữ liệu sang model riêng:

~~~java
public final class CrmContactTranslator {
    public SupportContact translate(CrmPartyDto source) {
        return SupportContact.imported(
                new ExternalCustomerRef(source.partyCode()),
                source.primaryContact().fullName(),
                VerifiedContactChannel.unverifiedMobile(
                        source.primaryContact().mobile()
                )
        );
    }
}
~~~

Ví dụ trên mang tính minh họa; trong hệ thống thật, việc xác minh contact, xử lý trạng thái không nhận diện được và lỗi mapping cần được định nghĩa theo policy của Support.

ACL không chỉ đổi tên field. Nó chuyển đổi ý nghĩa và có thể từ chối hoặc cách ly dữ liệu không thể biểu diễn hợp lệ trong model nội bộ.

## 10. Khi nào nên dùng Shared Kernel?

DDD có pattern Shared Kernel cho phép hai context chia sẻ một phần model hoặc code được thống nhất cùng phát triển. Pattern này không phải lời khuyên tạo một thư viện domain dùng chung cho toàn doanh nghiệp.

Shared Kernel chỉ phù hợp khi:

- Phần được chia sẻ nhỏ và có ý nghĩa ổn định.
- Hai nhóm có quyền quyết định và quy trình thay đổi phối hợp rõ.
- Mọi thay đổi đều được cả hai bên hiểu và chấp thuận.
- Phần chia sẻ không kéo theo dependency vào model nội bộ của một context.
- Lợi ích phối hợp lớn hơn chi phí đồng bộ.

Ví dụ, hai context có thể cùng thống nhất một định dạng định danh hoặc một thư viện giá trị kỹ thuật nhỏ. Nhưng việc dùng chung toàn bộ Customer aggregate, Order lifecycle hoặc Pricing policy thường tạo coupling lớn.

Shared Kernel cần được xem là một cam kết phối hợp. Nếu một team thay đổi code và team kia bị ảnh hưởng bất ngờ, phần chia sẻ đang trở thành dependency không được quản lý.

## 11. Shared database không đồng nghĩa shared domain model

Hai bounded context có thể tạm thời dùng chung một database vật lý vì lý do vận hành, nhưng điều đó không có nghĩa chúng nên cùng sửa một bảng hoặc cùng import một entity.

Ví dụ một modular monolith có thể dùng chung PostgreSQL nhưng chia schema hoặc module ownership:

~~~text
Database
 ├── sales schema
 │    ├── sales_customer
 │    └── sales_order
 ├── support schema
 │    ├── support_contact
 │    └── support_ticket
 └── billing schema
      ├── billing_party
      ├── invoice
      └── payment
~~~

Điều quan trọng là quyền ghi và trách nhiệm nghiệp vụ. Một context không nên cập nhật trực tiếp bảng nội bộ của context khác chỉ vì cùng kết nối được database. Nếu cần trao đổi, hãy dùng application interface, event, view được công bố có chủ đích hoặc một contract dữ liệu được quản lý.

Một shared database có thể tạo coupling ở mức schema và deployment. Bounded context vẫn cần ownership rõ để tránh việc database chung làm mất ranh giới mô hình.

## 12. Shared DTO không phải lúc nào cũng là vấn đề

Không nên cực đoan rằng mọi class dùng chung đều sai. Một DTO thuần túy ở ranh giới kỹ thuật có thể được chia sẻ nếu nó thật sự là contract ổn định và không chứa behavior/domain policy.

Tuy nhiên, cần phân biệt:

- Domain entity/value object có identity, invariant và behavior.
- API DTO dùng để nhận hoặc trả dữ liệu.
- Integration event dùng để thông báo sự kiện đã xảy ra.
- Persistence record dùng để lưu trữ.
- Read model dùng để phục vụ truy vấn.

Các loại này có mục đích và vòng đời khác nhau. Dùng một class cho tất cả các mục đích khiến thay đổi ở một tầng lan sang tầng khác.

Ví dụ, một API response có thể có field phục vụ UI mà domain không cần. Một domain value object có thể kiểm tra invariant nhưng JSON DTO chỉ cần biểu diễn dữ liệu. Tách chúng giúp mỗi tầng tiến hóa theo nhu cầu riêng.

## 13. Shared model làm tăng coupling theo thời gian

Giả sử Billing muốn bổ sung trạng thái công nợ bị tranh chấp. Nếu Billing dùng một Customer model toàn cục, thay đổi có thể dẫn đến:

1. Thêm field hoặc enum vào shared Customer.
2. Cập nhật package chung và version.
3. Build lại các consumer.
4. Sửa mapping hoặc validation ở Sales và Support.
5. Phân tích những nơi có thể hiểu sai trạng thái mới.
6. Triển khai theo thứ tự tương thích.

Một thay đổi cục bộ trở thành thay đổi nhiều context. Chi phí không chỉ là số dòng code; nó còn là điều tra, phối hợp, kiểm thử và phát hành.

Nếu Billing sở hữu BillingParty riêng, trạng thái tranh chấp có thể được thêm vào model Billing mà không buộc Sales hoặc Support thay đổi. Chỉ khi thông tin đó cần được trao đổi, Billing mới công bố một contract phù hợp.

## 14. Mô hình dùng chung thường dẫn đến enum và field nullable

Khi nhiều context dùng chung một model, các trạng thái riêng của từng context thường được dồn vào cùng enum:

~~~java
public enum CustomerStatus {
    LEAD,
    PROSPECT,
    ACTIVE,
    DORMANT,
    SUPPORT_BLOCKED,
    PAYMENT_OVERDUE,
    UNDER_REVIEW,
    DELETED
}
~~~

Không phải trạng thái nào cũng có cùng chủ sở hữu hoặc cùng ý nghĩa. Sales có thể hiểu ACTIVE là quan hệ thương mại đang hoạt động. Support có thể cần biết contact còn được phép hỗ trợ. Billing có thể cần phân biệt tài khoản quá hạn.

Một enum toàn cục khiến mọi context phải biết những trạng thái mà họ không sở hữu. Tương tự, một class có nhiều field nullable làm cho validation phụ thuộc vào ngữ cảnh gọi:

~~~java
if (customer.getTaxNumber() != null
        && customer.getSupportEnabled() != null
        && customer.getSalesOwner() != null) {
    // Không rõ đây là một Customer hợp lệ trong context nào.
}
~~~

Model riêng cho phép mỗi context biểu diễn những trạng thái hợp lệ của mình bằng kiểu dữ liệu và behavior phù hợp.

## 15. Tách mô hình không có nghĩa tách identity một cách tùy tiện

Khi mỗi context có model riêng, cần quyết định cách nhận diện và liên kết các đối tượng.

Một chiến lược phổ biến là:

- Context có identity nội bộ của riêng mình.
- Context lưu external reference hoặc business identifier để liên kết.
- Một identity mapping service hoặc integration process quản lý quan hệ khi cần.
- Contract công bố định danh ổn định mà consumer được phép sử dụng.

Ví dụ:

~~~java
public record SalesCustomerId(UUID value) {}
public record SupportContactId(UUID value) {}
public record BillingPartyId(UUID value) {}
public record EnterprisePartyRef(String value) {}
~~~

Không nên mặc định các ID nội bộ phải giống nhau chỉ vì chúng mô tả cùng một khách hàng ngoài đời. Quan hệ một-một, một-nhiều hoặc nhiều-một cần được xác định theo nghiệp vụ, hợp đồng pháp lý và quy trình hợp nhất dữ liệu.

## 16. Dữ liệu thay đổi giữa các context được đồng bộ thế nào?

Tách model có nghĩa mỗi context có thể sở hữu bản biểu diễn riêng. Khi một sự kiện cần được chia sẻ, provider phát hành contract:

~~~text
Sales Customer Updated
          |
          v
CustomerProfileChanged
          |
          +--> Support updates its contact projection
          |
          +--> Billing updates its billing reference
~~~

Consumer quyết định cách diễn giải và cập nhật model của mình. Không phải mọi field thay đổi ở provider đều phải được sao chép sang consumer.

Cần xác định:

- Event có ý nghĩa nghiệp vụ gì?
- Field nào là bắt buộc?
- Event là fact đã xảy ra hay command yêu cầu làm việc?
- Consumer có cần xử lý theo thứ tự không?
- Duplicate delivery được xử lý thế nào?
- Event cũ có thể được replay không?
- Dữ liệu nào nhạy cảm và không được chia sẻ?
- Consumer phản ứng thế nào khi nhận phiên bản schema chưa hỗ trợ?

Một event tốt công bố fact có ý nghĩa trong ngôn ngữ của provider. Consumer không nên phải suy ra ý nghĩa từ việc một bảng database vừa được cập nhật.

## 17. Eventual consistency phải phù hợp với nghiệp vụ

Khi mỗi context sở hữu model và transaction riêng, dữ liệu giữa chúng có thể cập nhật không đồng thời. Đây là eventual consistency.

Ví dụ, sau khi Sales xác nhận Order, Billing nhận event và tạo InvoiceDraft. Trong một khoảng thời gian ngắn, Order đã ở trạng thái submitted nhưng InvoiceDraft chưa tồn tại.

Điều này có thể chấp nhận nếu nghiệp vụ cho phép quy trình tạo hóa đơn diễn ra sau. Nếu người dùng cần biết chắc chắn invoice đã được tạo trước khi xác nhận một hành động khác, use case cần có workflow và phản hồi rõ.

Không nên tách model chỉ vì muốn giảm coupling rồi bỏ qua trạng thái trung gian. Cần xác định:

- Trạng thái nào là pending?
- Ai sở hữu quyết định retry?
- Điều gì xảy ra nếu consumer lỗi lâu dài?
- Có cần compensation không?
- Khi nào quy trình được xem là hoàn tất?
- Người dùng nhìn thấy trạng thái chưa đồng bộ như thế nào?

Tách bounded context là quyết định về ownership; eventual consistency là quyết định về thời điểm đồng bộ. Hai việc liên quan nhưng không thể đánh đồng.

## 18. Application Service điều phối, không chia sẻ domain object

Một use case có thể cần dữ liệu từ nhiều context. Application layer hoặc process manager có thể điều phối mà không buộc domain model của các context phụ thuộc trực tiếp vào nhau.

Ví dụ:

~~~java
public final class SubmitOrderHandler {
    private final OrderRepository orders;
    private final CustomerEligibilityPort eligibility;
    private final EventPublisher events;

    public void handle(SubmitOrder command) {
        Order order = orders.getRequired(command.orderId());
        CustomerEligibility result =
                eligibility.check(order.customerReference());

        order.submit(result);
        orders.save(order);
        events.publishAll(order.pullDomainEvents());
    }
}
~~~

Ví dụ này minh họa cách orchestration dùng port để lấy một quyết định hoặc dữ liệu từ context khác. Trong triển khai thật, cần xác định timeout, lỗi upstream, idempotency, transaction/outbox và semantics của eligibility result.

Điểm chính là application service phối hợp use case; mỗi aggregate vẫn bảo vệ invariant trong model của chính nó. Không cần truyền một Customer aggregate toàn cục vào Order.

## 19. Phân biệt Domain Model, Read Model và API Model

Một nguyên nhân khác dẫn đến mô hình toàn cục là dùng cùng một object cho mọi nhu cầu đọc và ghi.

Trong một hệ thống DDD:

| Model | Mục đích | Đặc điểm |
|---|---|---|
| Domain model | Bảo vệ invariant và biểu diễn behavior | Entity, Value Object, Aggregate, policy |
| Read model | Trả lời truy vấn và hiển thị | Có thể denormalize, tối ưu theo màn hình/báo cáo |
| API model | Contract với client | Theo version và nhu cầu giao tiếp |
| Integration model | Trao đổi giữa bounded context | Event/message/DTO có semantics rõ |
| Persistence model | Lưu và khôi phục dữ liệu | Theo mapping và chiến lược lưu trữ |

Một màn hình có thể cần tên khách hàng, tổng doanh thu, ticket gần nhất và trạng thái thanh toán. Không có nghĩa một Customer aggregate phải chứa toàn bộ những dữ liệu đó. Read model có thể tổng hợp dữ liệu từ nhiều context mà không biến chúng thành một domain model dùng chung.

## 20. Những dấu hiệu shared model đã trở thành anti-pattern

Hãy xem xét lại thiết kế khi có nhiều dấu hiệu:

- Một package common/domain được mọi bounded context import.
- Một entity có nhiều field chỉ một context sử dụng.
- Một enum chứa trạng thái thuộc các lifecycle khác nhau.
- Validation thay đổi theo caller hoặc theo cờ boolean.
- Một context phải deploy chỉ vì context khác thêm field không liên quan.
- Consumer đọc trực tiếp bảng nội bộ của provider.
- ORM entity đồng thời là API DTO, event schema và domain object.
- Mọi context phải thống nhất cùng một lịch release cho model chung.
- Một thay đổi nhỏ gây ra nhiều pull request ở các context không liên quan.
- Tên class giống nhau nhưng các team tranh luận về ý nghĩa khác nhau.
- Không xác định được owner cho một field hoặc behavior.
- Các model context-specific chỉ là wrapper quanh một shared object lớn.

Một thư viện common nhỏ chứa kiểu kỹ thuật ổn định không tự động là anti-pattern. Vấn đề là chia sẻ domain semantics và quyền thay đổi mà không có ownership rõ.

## 21. Quy trình thoát khỏi mô hình dùng chung

Không nên tách tất cả class cùng lúc. Hãy bắt đầu từ một khái niệm đang gây coupling và một thay đổi nghiệp vụ thực tế.

### Bước 1: Xác định các context đang dùng model

Tìm consumer của class, schema hoặc package. Ghi lại context nào đọc, context nào ghi và use case nào phụ thuộc.

### Bước 2: Thu thập cách dùng từ chuyên gia

Phỏng vấn người làm Sales, Support, Billing hoặc Fulfillment. Hỏi họ định nghĩa Customer, Account, Order như thế nào và quyết định nghiệp vụ nào được đưa ra từ khái niệm đó.

### Bước 3: Ghi nhận sự khác biệt về behavior

Liệt kê field, state, validation, lifecycle và invariant theo từng context. Đừng chỉ so sánh tên thuộc tính.

### Bước 4: Xác định ownership

Mỗi quy tắc và dữ liệu có một context chịu trách nhiệm. Nếu nhiều context cần cùng thông tin, xác định provider và contract được công bố.

### Bước 5: Thiết kế model riêng

Tạo Entity, Value Object và Aggregate phù hợp với ngôn ngữ và invariant của từng context. Không sao chép toàn bộ shared class rồi chỉ đổi tên.

### Bước 6: Thiết kế contract

Chỉ công bố dữ liệu consumer thực sự cần. Xác định semantics, version, compatibility, identity và lỗi.

### Bước 7: Xây dựng ACL hoặc translator

Dịch contract sang model nội bộ. Đưa logic mapping có ý nghĩa nghiệp vụ vào nơi phù hợp và xử lý rõ dữ liệu không hợp lệ.

### Bước 8: Chuyển đổi dần consumer

Chọn một use case, chuyển sang model mới, kiểm thử và triển khai. Có thể duy trì adapter tạm thời trong giai đoạn migration, nhưng cần đặt mục tiêu loại bỏ đường đi cũ.

### Bước 9: Thu hẹp quyền truy cập shared model

Khi consumer đã chuyển, giảm API công khai của shared model. Ngăn context mới phụ thuộc thêm vào nó.

### Bước 10: Xác minh và loại bỏ model cũ

Kiểm tra ownership, dữ liệu, contract, test và deployment. Chỉ loại bỏ shared model khi không còn consumer cần nó.

## 22. Ví dụ refactor: từ Customer toàn cục sang model riêng

Thiết kế ban đầu:

~~~text
common-domain
  └── Customer
       ├── sales fields
       ├── support fields
       ├── billing fields
       └── access fields

Sales ---------+
Support -------+----> common-domain.Customer
Billing -------+
Identity ------+
~~~

Thiết kế mục tiêu:

~~~text
Sales Context
  └── SalesCustomer

Support Context
  └── SupportContact

Billing Context
  └── BillingParty

Identity Context
  └── UserIdentity

Integration Contracts
  ├── CustomerReference
  ├── CustomerProfileChanged
  └── BillingPartyRegistered
~~~

Lộ trình chuyển đổi có thể gồm:

1. Giữ nguyên identifier đang được công bố để không phá consumer.
2. Tạo model riêng và mapper cho một context.
3. Chuyển read path trước nếu rủi ro thấp.
4. Chuyển write ownership và đảm bảo một nguồn ghi có thẩm quyền.
5. Phát event hoặc cung cấp API contract cho consumer.
6. Chuyển consumer còn lại theo từng đợt.
7. Theo dõi dữ liệu lệch, duplicate event và lỗi mapping.
8. Ngừng cập nhật shared model khi không còn writer.
9. Xóa package hoặc schema chung sau khi xác minh không còn dependency.

Nếu phải duy trì dual write trong giai đoạn chuyển tiếp, cần có cơ chế đối soát, idempotency và kế hoạch kết thúc rõ ràng. Dual write kéo dài không nên trở thành trạng thái kiến trúc mặc định.

## 23. Các pattern tích hợp và cách chọn

| Pattern | Khi phù hợp | Điều cần lưu ý |
|---|---|---|
| Customer/Supplier | Upstream có thể đáp ứng nhu cầu contract của downstream | Hai bên cần thống nhất quyền ưu tiên và lịch thay đổi |
| Conformist | Downstream chấp nhận model upstream vì chi phí dịch quá cao hoặc provider có quyền quyết định | Model upstream có thể lan vào consumer |
| Anti-Corruption Layer | Consumer cần bảo vệ model khỏi semantics bên ngoài | Có chi phí mapping và bảo trì |
| Open Host Service | Provider công bố interface ổn định cho nhiều consumer | Phải quản lý version và compatibility |
| Published Language | Nhiều context cần cùng hiểu một contract công khai | Contract không nên trở thành domain model toàn cục |
| Shared Kernel | Một phần nhỏ thực sự cần được phát triển chung | Cần ownership và phối hợp thay đổi chặt chẽ |
| Separate Ways | Chi phí tích hợp lớn hơn giá trị trao đổi | Có thể trùng lặp dữ liệu hoặc chức năng có chủ đích |

Không có pattern nào luôn tốt nhất. Lựa chọn phụ thuộc quyền kiểm soát upstream, nhu cầu consumer, tần suất thay đổi, chi phí dịch và mức độ khác biệt giữa các model.

## 24. Một số hiểu nhầm cần tránh

**“Một doanh nghiệp chỉ nên có một Customer.”** Một thế giới thực có thể có một người hoặc tổ chức, nhưng các context có thể cần nhiều model để diễn đạt các quan hệ và trách nhiệm khác nhau.

**“Có nhiều model thì dữ liệu chắc chắn không nhất quán.”** Dữ liệu có thể được đồng bộ bằng contract, event, reference hoặc snapshot. Điều cần thiết là ownership và semantics rõ, không phải object class giống nhau.

**“Context nào cũng phải tự xây lại mọi thứ.”** Có thể chia sẻ contract, thư viện kỹ thuật hoặc Shared Kernel có kiểm soát. Chỉ nên tránh chia sẻ model domain khi semantics và lifecycle khác nhau.

**“Bounded Context phải là một microservice.”** Bounded context là ranh giới model. Có thể triển khai bằng module trong một ứng dụng hoặc nhiều service.

**“Tách model đồng nghĩa duplicate mọi field.”** Mỗi context chỉ cần dữ liệu phục vụ use case và invariant của nó. Có thể dùng projection, reference và snapshot theo mục đích.

**“ACL chỉ là mapper.”** ACL còn bảo vệ semantics và quyết định cách xử lý dữ liệu không tương thích, trạng thái không biết hoặc quy tắc từ upstream.

**“Một schema dùng chung luôn giúp giảm chi phí.”** Chi phí ban đầu có thể thấp nhưng coupling và chi phí phối hợp có thể tăng theo thời gian.

## 25. Đo hiệu quả sau khi tách model

Sau khi thay shared model bằng các model theo context, hãy đo kết quả thay vì chỉ đếm số class mới:

- Số thay đổi có thể thực hiện trong một context mà không sửa context khác.
- Thời gian tìm đúng owner của một quy tắc.
- Số consumer bị ảnh hưởng khi provider thay đổi implementation nội bộ.
- Số breaking contract change và thời gian xử lý chúng.
- Effort mapping và xử lý dữ liệu không tương thích.
- Tỷ lệ lỗi do hiểu sai semantics giữa các context.
- Khả năng onboarding một developer vào một context.
- Số lần cần phối hợp release đồng bộ.
- Tính chính xác của dữ liệu được đồng bộ và khả năng đối soát.

Việc tách model có thể làm tăng số mapping hoặc contract, nhưng vẫn giảm tổng chi phí nếu các context thay đổi độc lập hơn. Cần đánh giá cả chi phí tích hợp mới và chi phí coupling cũ.

## 26. Checklist review mô hình dùng chung

- [ ] Mỗi bounded context có ubiquitous language và định nghĩa khái niệm rõ.
- [ ] Mỗi domain rule có context sở hữu.
- [ ] Shared class không tích lũy field chỉ một vài context sử dụng.
- [ ] Enum và trạng thái không trộn lifecycle khác nhau.
- [ ] Domain model tách khỏi API DTO, integration event và persistence record.
- [ ] Consumer chỉ nhận dữ liệu cần thiết qua contract rõ nghĩa.
- [ ] Contract có owner, version và compatibility rule.
- [ ] ACL được dùng khi semantics upstream khác model nội bộ.
- [ ] Shared Kernel nhỏ, có chủ sở hữu và quy trình phối hợp thay đổi.
- [ ] Shared database không cho context khác ghi trực tiếp dữ liệu nội bộ.
- [ ] Identity và mapping giữa các context được xác định rõ.
- [ ] Eventual consistency được nghiệp vụ chấp nhận và có quy trình xử lý lỗi.
- [ ] Read model được thiết kế theo nhu cầu truy vấn thay vì ép vào domain aggregate.
- [ ] Có lộ trình chuyển đổi và loại bỏ shared model cũ.
- [ ] Đã đo coupling, effort tích hợp và lỗi mapping sau thay đổi.

## 27. Kết nối với các khái niệm DDD khác

Sai lầm dùng một mô hình cho mọi ngữ cảnh thường bắt nguồn từ việc chưa phân biệt strategic design và tactical design. Strategic design xác định subdomain, bounded context và quan hệ giữa các context qua Context Map. Tactical design xây dựng Entity, Value Object, Aggregate, Repository và Domain Event bên trong một model cụ thể.

Ubiquitous Language cần nhất quán trong một context; cùng một thuật ngữ có thể được dịch sang khái niệm khác ở context khác. Aggregate bảo vệ invariant nội bộ, còn contract và domain event cho phép các aggregate/context hợp tác mà không chia sẻ toàn bộ object graph. ACL bảo vệ model của consumer khi upstream dùng một ngôn ngữ hoặc cấu trúc khác.

Thiết kế tốt không đòi hỏi mọi context có dữ liệu hoàn toàn khác nhau. Nó đòi hỏi mỗi context sở hữu một model phù hợp với trách nhiệm và quy tắc của mình, đồng thời công bố những thông tin cần thiết qua ranh giới có chủ đích. Khi đó, đội phát triển có thể thay đổi một phần nghiệp vụ mà không phải kéo toàn doanh nghiệp vào cùng một lần sửa model.

## 28. Kết luận

Một mô hình domain dùng chung cho mọi ngữ cảnh thường làm mất đi sự khác biệt có ý nghĩa giữa các bộ phận và quy trình. Nó tạo ra class quá lớn, field nullable, enum hỗn hợp, validation phụ thuộc caller và coupling khiến một thay đổi cục bộ lan sang nhiều context.

DDD giải quyết vấn đề bằng cách đặt model trong bounded context, dùng ubiquitous language phù hợp với ngữ cảnh và xác định ownership rõ. Các context tích hợp qua contract, event, API, ACL hoặc Shared Kernel được quản lý có chủ đích. Chúng có thể chia sẻ identity, dữ liệu hoặc một số kiểu kỹ thuật mà không cần chia sẻ domain object và invariant.

Hãy bắt đầu từ câu hỏi “context này cần hiểu và quyết định điều gì?” thay vì “làm sao để mọi nơi dùng cùng một class?”. Khi model phản ánh đúng trách nhiệm của từng context và việc trao đổi qua ranh giới được thiết kế rõ, hệ thống sẽ dễ hiểu hơn, thay đổi ít lan truyền hơn và ngôn ngữ nghiệp vụ trở nên hữu ích trong công việc hàng ngày.
