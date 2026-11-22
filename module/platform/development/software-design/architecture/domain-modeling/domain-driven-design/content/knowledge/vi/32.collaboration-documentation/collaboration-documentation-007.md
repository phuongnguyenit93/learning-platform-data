# Lập lộ trình học nghiệp vụ và cải tiến mô hình liên tục

Domain-Driven Design (DDD) xem việc xây dựng phần mềm là một quá trình học về
nghiệp vụ. Mô hình miền không xuất hiện đầy đủ ngay từ đầu; nó được hình thành
từ những cuộc trao đổi với chuyên gia nghiệp vụ, được kiểm chứng bằng ví dụ,
được đưa vào code và tiếp tục thay đổi khi đội phát hiện ra điều mình hiểu
chưa đúng.

Vì vậy, lộ trình học DDD cần có hai nhịp chạy song song. Một nhịp giúp đội
hiểu miền: khám phá domain, xác định subdomain, bounded context, ubiquitous
language và các quy tắc nghiệp vụ. Nhịp còn lại giúp đội biến hiểu biết đó
thành mô hình có thể sử dụng: entity, value object, aggregate, repository,
domain service, domain event, application service và các kiểm thử bảo vệ
quy tắc.

Tài liệu này trình bày cách lập lộ trình học nghiệp vụ, cách ghi lại những gì
đội đã học và cách tổ chức vòng cải tiến để mô hình không tách khỏi thực tế.
Mục tiêu không phải là tạo thật nhiều tài liệu. Mục tiêu là để mọi người có
thể trả lời rõ ba câu hỏi:

1. Chúng ta đang hiểu nghiệp vụ như thế nào?
2. Phần hiểu biết nào đã được chuyển thành mô hình và code?
3. Bằng chứng nào cho thấy mô hình hiện tại còn đúng hoặc cần thay đổi?

## 1. Lộ trình DDD bắt đầu từ việc học, không bắt đầu từ cấu trúc package

Một sai lầm phổ biến là bắt đầu bằng việc tạo các lớp Entity, Service,
Repository rồi tìm nghiệp vụ để đặt vào đó. Cách này khiến kiến trúc kỹ thuật
dẫn dắt mô hình thay vì mô hình phản ánh nghiệp vụ.

Lộ trình tốt bắt đầu bằng một giả thuyết về vấn đề kinh doanh và một nhóm
người cần cùng nhau hiểu vấn đề đó. Sau mỗi vòng khám phá, đội bổ sung bằng
chứng mới, điều chỉnh thuật ngữ, thay đổi ranh giới hoặc làm rõ quy tắc.

Có thể hình dung vòng học như sau:

~~~mermaid
flowchart LR
    A[Quan sát nghiệp vụ] --> B[Đặt câu hỏi]
    B --> C[Thu thập ví dụ]
    C --> D[Đề xuất mô hình]
    D --> E[Đưa vào code và test]
    E --> F[Đưa vào sử dụng]
    F --> G[Quan sát phản hồi]
    G --> A
~~~

Mỗi vòng không cần thay đổi lớn. Một thay đổi nhỏ trong thuật ngữ hoặc một
quy tắc mới được phát hiện cũng là đầu vào hợp lệ cho vòng học tiếp theo.

## 2. Xác định phạm vi học trước khi lập backlog

DDD có phạm vi rộng. Nếu cố tìm hiểu toàn bộ domain cùng lúc, đội dễ tạo ra
một mô hình lớn nhưng không có đủ kiến thức để bảo vệ các quyết định trong
mô hình đó.

Trước khi lập backlog học tập, hãy xác định:

| Câu hỏi | Kết quả cần ghi lại |
|---|---|
| Người dùng hoặc tổ chức đang cố đạt mục tiêu gì? | Business outcome |
| Quy trình nào tạo ra hoặc bảo vệ giá trị? | Business capability/process |
| Những ai hiểu quy trình đó sâu nhất? | Domain experts |
| Quyết định nào có chi phí sai cao? | Critical business rules |
| Phần nào đang gây nhiều tranh luận hoặc lỗi? | Discovery hotspot |
| Phần nào cần mô hình hóa trước? | Learning scope |

Phạm vi học nên đủ nhỏ để có thể tổ chức một vòng discovery và kiểm chứng
trong thời gian hữu hạn. Khi có bằng chứng mới, phạm vi có thể mở rộng.

Ví dụ, với hệ thống thương mại điện tử, đội có thể bắt đầu bằng quy trình
đặt hàng thay vì cố mô hình hóa toàn bộ thương mại điện tử. Trong quá trình
khám phá, đội có thể phát hiện rằng giữ chỗ tồn kho, thanh toán và giao hàng
có luật riêng. Những phát hiện đó là dữ liệu để xác định các ranh giới tiếp
theo.

## 3. Chia lộ trình thành các lớp học tập

Một lộ trình DDD thực dụng có thể đi qua các lớp sau:

| Lớp | Câu hỏi chính | Artifact tiêu biểu |
|---|---|---|
| Domain discovery | Doanh nghiệp thực sự làm gì? | Event Storming, use case, ví dụ |
| Domain classification | Phần nào tạo giá trị và phần nào hỗ trợ? | Core/supporting/generic subdomain |
| Context discovery | Thuật ngữ và mô hình nào có cùng ý nghĩa? | Bounded Context, Context Map |
| Shared language | Đội gọi sự vật và hành động bằng từ nào? | Ubiquitous Language |
| Tactical modeling | Quy tắc nằm ở đâu? | Entity, Value Object, Aggregate |
| Application flow | Use case điều phối thế nào? | Command, Application Service |
| Integration | Context trao đổi gì? | Domain Event, Integration Event, ACL |
| Verification | Mô hình có bảo vệ đúng luật không? | Unit, contract, acceptance tests |
| Documentation | Quyết định và hiểu biết được lưu thế nào? | Model docs, ADR, examples |
| Continuous learning | Điều gì đã thay đổi trong domain? | Review log, model change |

Không nên xem các lớp này là một chuỗi khóa học phải hoàn thành một lần rồi
đóng lại. Một team có thể quay từ tactical modeling về domain discovery khi
code làm lộ ra một khái niệm chưa được hiểu đủ.

## 4. Đặt mục tiêu học bằng câu hỏi có thể kiểm chứng

Mục tiêu như “hiểu bounded context” quá rộng để đánh giá. Mục tiêu tốt hơn
là một câu hỏi gắn với tình huống cụ thể:

> Khi một đơn hàng bị hủy sau khi đã thanh toán, context nào quyết định việc
> hoàn tiền và context nào chỉ phản ứng với kết quả đó?

Một câu hỏi tốt tạo ra nhu cầu thu thập ví dụ. Sau buổi trao đổi, đội phải có
thể trả lời câu hỏi bằng thuật ngữ và quy tắc cụ thể.

Có thể dùng mẫu sau cho learning backlog:

~~~text
Learning item:
  Question:
  Business situation:
  Domain expert:
  Examples needed:
  Hypothesis:
  Evidence:
  Model affected:
  Code/test affected:
  Open questions:
  Next review:
~~~

Evidence quan trọng vì nó phân biệt điều đội biết với điều đội đang đoán.
Một giả thuyết không có bằng chứng nên được ghi rõ là giả thuyết, thay vì
được viết trong tài liệu như một sự thật.

## 5. Dùng Event Storming để tạo điểm chung cho discovery

Event Storming giúp nhóm nhìn domain qua các sự kiện nghiệp vụ đã xảy ra.
Thay vì bắt đầu bằng bảng dữ liệu hoặc class diagram, nhóm đặt câu hỏi:

- Điều gì đã xảy ra?
- Ai hoặc cái gì làm điều đó xảy ra?
- Điều kiện nào phải đúng trước đó?
- Ai quan tâm đến kết quả?
- Có chính sách nào được kích hoạt?

Một event nên được đặt tên bằng ngôn ngữ nghiệp vụ, thường ở dạng quá khứ:
OrderPlaced, PaymentAuthorized, ReservationExpired.

Sau khi có chuỗi sự kiện, nhóm tìm command, actor, policy, read model và các
quy tắc. Những điểm có nhiều tranh luận là discovery hotspot rất có giá trị.
Không nên cố giải quyết mọi tranh luận ngay tại bảng. Hãy ghi lại câu hỏi và
đưa nó vào learning backlog nếu cần thêm bằng chứng.

## 6. Chuyển từ discovery sang Ubiquitous Language

Ubiquitous Language là ngôn ngữ chung được dùng trong hội thoại, tài liệu,
test và code trong một bounded context. Nó không phải là một glossary tĩnh
được viết một lần.

Một mục từ nên có:

| Thành phần | Nội dung |
|---|---|
| Term | Tên được thống nhất |
| Meaning | Ý nghĩa trong context |
| Example | Một hoặc nhiều tình huống thật |
| Rules | Quy tắc liên quan |
| Related terms | Các khái niệm gần |
| Avoid | Từ đồng nghĩa dễ gây nhầm |
| Owner/context | Context nơi ý nghĩa này có hiệu lực |

Ví dụ, Customer trong context bán hàng có thể là người đặt đơn; trong
context hỗ trợ, Customer có thể là hồ sơ người đang nhận hỗ trợ. Nếu hai
khái niệm có hành vi và vòng đời khác nhau, việc ép chúng dùng cùng một
model chỉ vì tên giống nhau sẽ tạo coupling không cần thiết.

Khi thuật ngữ thay đổi, đội cần kiểm tra cả code, test, API, message và tài
liệu có dùng thuật ngữ cũ hay không. Đây là một dạng refactoring của domain
model.

## 7. Xác định Subdomain để ưu tiên thời gian học

Không phải phần nào của domain cũng đáng đầu tư cùng một mức độ.

| Loại | Đặc điểm | Cách tiếp cận |
|---|---|---|
| Core subdomain | Tạo lợi thế cạnh tranh hoặc quyết định giá trị chính | Đầu tư discovery và modeling sâu |
| Supporting subdomain | Cần cho hoạt động nhưng không phải lợi thế chính | Mô hình vừa đủ |
| Generic subdomain | Năng lực phổ biến, ít khác biệt | Có thể mua hoặc dùng giải pháp chuẩn |

Phân loại này là giả thuyết chiến lược. Khi chiến lược kinh doanh thay đổi,
phân loại cũng có thể thay đổi.

Ví dụ, một công ty trước đây xem tối ưu giá là generic nhưng sau đó biến
pricing thành lợi thế cạnh tranh. Khi đó pricing có thể trở thành core
subdomain và cần một vòng học sâu hơn.

## 8. Xác định Bounded Context từ sự khác biệt về mô hình

Bounded Context đặt ranh giới nơi một model và một Ubiquitous Language có ý
nghĩa nhất quán. Ranh giới không nên chỉ được quyết định bởi team hoặc
microservice.

Dấu hiệu một ranh giới có thể cần tách:

- Một từ có nghĩa khác nhau trong hai nhóm nghiệp vụ.
- Một quy tắc thay đổi độc lập với quy tắc ở khu vực khác.
- Hai nhóm có các invariant khác nhau.
- Hai mô hình cần tốc độ thay đổi khác nhau.
- Việc chia sẻ model làm một bên phải phụ thuộc vào quyết định của bên kia.
- Một context có thể giao tiếp bằng contract rõ ràng thay vì chia sẻ cấu trúc
  nội bộ.

Context Map sau đó mô tả mối quan hệ giữa các context: upstream/downstream,
customer-supplier, conformist, anti-corruption layer, shared kernel hoặc các
quan hệ phù hợp với hệ thống thực tế.

~~~mermaid
flowchart LR
    Catalog[Catalog Context] -->|ProductPublished| Sales[Sales Context]
    Sales -->|OrderPlaced| Fulfillment[Fulfillment Context]
    Sales -->|PaymentRequest| Payment[Payment Context]
    Payment -->|PaymentAuthorized| Sales
~~~

Điều quan trọng là ghi lại ý nghĩa của mối quan hệ và contract, thay vì chỉ
vẽ mũi tên.

## 9. Ghi lại quyết định mô hình bằng ADR

Architecture Decision Record (ADR) hữu ích khi đội phải lựa chọn giữa nhiều
phương án. Một ADR tốt ghi lại bối cảnh tại thời điểm quyết định để người
đọc sau này hiểu tại sao mô hình có hình dạng hiện tại.

~~~markdown
# ADR-012: Tách Pricing khỏi Sales Order

## Context
Quy tắc tính giá thay đổi độc lập với vòng đời đơn hàng.

## Decision
Pricing là một bounded context riêng và cung cấp quote cho Sales.

## Consequences
- Sales không sở hữu thuật toán pricing.
- Contract quote phải được version hóa.
- Có eventual consistency ở một số read model.

## Evidence
- Ba nhóm nghiệp vụ sử dụng quy tắc giá khác nhau.
- Pricing thay đổi hàng tuần, Order thay đổi theo chu kỳ phát hành khác.
~~~

ADR không thay thế model. Nó giải thích một quyết định quan trọng của model.
Khi quyết định bị thay thế, ADR cũ nên được đánh dấu superseded và liên kết
đến quyết định mới.

## 10. Ghi lại model bằng ví dụ thay vì chỉ bằng định nghĩa

Một quy tắc nghiệp vụ thường dễ hiểu hơn qua ví dụ.

Thay vì chỉ ghi:

> Đơn hàng không được chuyển sang Confirmed nếu thanh toán chưa được xác
> nhận.

hãy thêm ví dụ:

| Trạng thái đơn | Trạng thái thanh toán | Hành động | Kết quả |
|---|---|---|---|
| Draft | Pending | Xác nhận đơn | Bị từ chối |
| Draft | Authorized | Xác nhận đơn | Confirmed |
| Confirmed | Authorized | Hủy đơn | Tạo yêu cầu hoàn tiền |
| Confirmed | Captured | Hủy đơn | Áp dụng chính sách hoàn tiền |

Các ví dụ này có thể trở thành acceptance test hoặc specification. Khi test
và tài liệu dùng cùng ví dụ, khoảng cách giữa “điều được nói” và “điều được
code” giảm xuống.

## 11. Liên kết model với tactical design

Sau discovery, tactical design biến khái niệm nghiệp vụ thành cấu trúc code.
Không nên tạo class chỉ để minh họa thuật ngữ DDD. Mỗi building block cần
giúp bảo vệ một quy tắc hoặc biểu đạt một khái niệm có ý nghĩa.

| Khái niệm | Câu hỏi |
|---|---|
| Entity | Đối tượng có identity ổn định nào cần theo dõi? |
| Value Object | Giá trị nào được xác định bởi thuộc tính và có thể bất biến? |
| Aggregate | Invariant nào phải được bảo vệ cùng một transaction boundary? |
| Repository | Aggregate nào cần được load/save như một đơn vị? |
| Domain Service | Quy tắc nào không tự nhiên thuộc về một entity/value object? |
| Domain Event | Sự kiện nghiệp vụ nào cần biểu đạt cho phần khác của domain? |

Ví dụ:

~~~java
public final class Order {
    private final OrderId id;
    private OrderStatus status;

    public void confirm(PaymentStatus paymentStatus) {
        if (paymentStatus != PaymentStatus.AUTHORIZED) {
            throw new DomainRuleViolation("Payment must be authorized");
        }
        status = OrderStatus.CONFIRMED;
    }
}
~~~

Điểm quan trọng của ví dụ là invariant nằm gần nơi nó được bảo vệ. Tên
confirm và PaymentStatus.AUTHORIZED cũng phải khớp với ngôn ngữ mà domain
expert sử dụng trong context đó.

## 12. Dùng test như tài liệu thực thi của mô hình

Test là một phần của documentation khi nó mô tả hành vi nghiệp vụ bằng
ngôn ngữ rõ ràng.

~~~java
@Test
void cannot_confirm_order_when_payment_is_pending() {
    Order order = anOrderInDraft();

    assertThatThrownBy(() -> order.confirm(PaymentStatus.PENDING))
        .isInstanceOf(DomainRuleViolation.class);
}
~~~

Một test tốt cho model trả lời được:

1. Điều kiện ban đầu là gì?
2. Hành động nghiệp vụ nào xảy ra?
3. Quy tắc nào được áp dụng?
4. Kết quả quan sát được là gì?

Nếu tên test chỉ nói về implementation như shouldSetStatus2, tài liệu thực
thi hành bị mất ngữ nghĩa. Khi refactor model, đội nên giữ nguyên ý nghĩa
nghiệp vụ của test và chỉ thay đổi chi tiết kỹ thuật cần thiết.

## 13. Lập learning backlog theo độ bất định

Backlog học tập nên ưu tiên những câu hỏi có khả năng làm thay đổi mô hình.
Một cách đơn giản là đánh giá mỗi item theo:

~~~text
Impact = mức ảnh hưởng nếu hiểu sai
Uncertainty = mức chưa chắc chắn hiện tại
Cost = chi phí để thu thập thêm bằng chứng
~~~

Ưu tiên cao thường là item có Impact và Uncertainty lớn nhưng Cost không quá
cao.

Ví dụ:

| Learning item | Impact | Uncertainty | Hành động |
|---|---:|---:|---|
| Khi nào hoàn tiền được phép? | Cao | Cao | Workshop với chuyên gia |
| Tên field của audit log | Thấp | Thấp | Ghi nhận sau |
| Ai sở hữu trạng thái shipment? | Cao | Cao | Event Storming + Context Mapping |
| Màu nút trên màn hình | Thấp | Thấp | UI backlog |

Đây là cách tránh dành phần lớn thời gian cho những chi tiết không ảnh hưởng
đến domain model.

## 14. Thiết lập nhịp collaboration cố định

DDD cần collaboration liên tục. Một lịch thực dụng có thể gồm:

| Nhịp | Mục đích | Người tham gia | Đầu ra |
|---|---|---|---|
| Hằng ngày | Làm rõ câu hỏi nhỏ | Developer + người hiểu domain | Cập nhật model/test |
| Hằng tuần | Review learning backlog | Developer + domain expert | Quyết định ưu tiên |
| Theo feature | Discovery workshop | Cross-functional | Examples, events, rules |
| Theo release | Model review | Team + stakeholder | Model changes |
| Theo quý hoặc khi chiến lược đổi | Strategic review | Business + architecture | Subdomain/context review |

Không phải cuộc họp nào cũng cần đông người. Mục tiêu là đưa đúng người vào
đúng thời điểm, đặc biệt là người có quyền quyết định hoặc có kinh nghiệm
thực tế về quy trình.

## 15. Tạo vòng Model Review

Một Model Review nên kiểm tra bốn lớp:

~~~text
Business reality
      ↓
Ubiquitous Language
      ↓
Domain Model
      ↓
Code + Tests
~~~

Ở mỗi lớp, đặt câu hỏi:

- Có tình huống thực tế nào mô hình chưa giải thích được?
- Có thuật ngữ nào trong cuộc họp khác với thuật ngữ trong code?
- Có invariant nào đang nằm ngoài aggregate?
- Có test nào bảo vệ một quy tắc không còn đúng?
- Có API hoặc event nào đang để lộ model nội bộ của context?

Model Review không phải buổi chấm điểm đội phát triển. Nó là một cơ chế phát
hiện model drift trước khi drift trở thành chi phí lớn.

## 16. Nhận diện Model Drift

Model drift xảy ra khi model và thực tế nghiệp vụ dần tách nhau. Một số dấu
hiệu:

- Domain expert dùng một từ nhưng code dùng từ khác.
- Một rule quan trọng chỉ tồn tại trong tài liệu hoặc trong đầu một người.
- Developer không giải thích được tại sao aggregate có invariant hiện tại.
- Nhiều điều kiện kiểm tra cùng một quy tắc ở nhiều application service.
- Integration event chứa cấu trúc database nội bộ.
- Test vẫn pass nhưng người dùng mô tả một quy trình khác.

Khi phát hiện drift, đừng chỉ sửa tài liệu. Hãy tìm nguồn gây lệch: quy trình
kinh doanh đã đổi, model cũ chưa được cập nhật, hay team đang dùng hai ngôn
ngữ khác nhau.

## 17. Quản lý thay đổi mô hình như một thay đổi nghiệp vụ

Một thay đổi domain model nên có một chuỗi traceable:

~~~text
Business change
    ↓
New/changed example
    ↓
Language change
    ↓
Model decision
    ↓
Code + test
    ↓
Integration contract
    ↓
Documentation update
~~~

Ví dụ, doanh nghiệp thay đổi chính sách “đơn đã giao không thể hoàn tiền”.
Đội cần xác định:

1. Thuật ngữ Delivered có nghĩa gì?
2. Context nào sở hữu trạng thái giao hàng?
3. Context nào quyết định refund?
4. Rule được bảo vệ ở aggregate nào?
5. Event nào thông báo trạng thái?
6. Các consumer cũ có bị ảnh hưởng không?
7. Acceptance test nào cần thay đổi?

Nhờ vậy, một thay đổi nghiệp vụ không bị giới hạn thành một ticket “sửa một
if” trong code.

## 18. Documentation nên có nhiều lớp

Một hệ thống DDD thường cần nhiều loại tài liệu, mỗi loại trả lời một câu
hỏi khác nhau:

| Tài liệu | Trả lời |
|---|---|
| Context Map | Các context liên hệ với nhau thế nào? |
| Ubiquitous Language | Từ này nghĩa gì trong context? |
| Use Case | Người dùng hoặc actor đạt mục tiêu bằng cách nào? |
| Model example | Quy tắc hoạt động trong tình huống cụ thể ra sao? |
| ADR | Vì sao đội chọn thiết kế này? |
| Code | Quy tắc được thực thi thế nào? |
| Test | Hành vi nào phải luôn đúng? |
| Integration contract | Context trao đổi dữ liệu và semantics gì? |
| Review log | Điều gì đã được học và thay đổi? |

Không nên đưa mọi thông tin vào một tài liệu duy nhất. Một tài liệu quá lớn
sẽ khó cập nhật và khó xác định phần nào còn đúng.

## 19. Giữ documentation gần nơi thay đổi

Nếu một thay đổi model yêu cầu sửa code, test và tài liệu ở ba hệ thống
không liên quan, khả năng tài liệu bị quên sẽ tăng.

Có thể thiết lập quy tắc:

~~~text
Model change checklist
  [ ] Ubiquitous Language
  [ ] Example / use case
  [ ] Domain model
  [ ] Unit / acceptance test
  [ ] ADR nếu là quyết định kiến trúc
  [ ] Integration contract nếu có cross-context change
  [ ] Context Map nếu boundary hoặc relationship thay đổi
  [ ] Operational documentation nếu behavior quan sát được thay đổi
~~~

Không phải thay đổi nào cũng cần tick tất cả. Checklist giúp đội hỏi đúng
câu hỏi trước khi đóng một thay đổi.

## 20. Thiết kế Workshop theo mục tiêu

Một workshop hiệu quả không bắt đầu bằng “hãy vẽ class diagram”. Hãy bắt đầu
bằng một business scenario.

Ví dụ agenda 90 phút:

| Thời lượng | Hoạt động |
|---:|---|
| 10 phút | Xác định scenario và outcome |
| 20 phút | Liệt kê events và commands |
| 15 phút | Tìm rules, policies và exceptions |
| 15 phút | Xác định thuật ngữ gây tranh luận |
| 15 phút | Phác thảo context/boundary |
| 10 phút | Chọn một vài examples để kiểm chứng |
| 5 phút | Ghi open questions và owner |

Người điều phối cần bảo vệ mục tiêu học. Nếu cuộc thảo luận chuyển sang
chi tiết framework hoặc database quá sớm, hãy ghi câu hỏi kỹ thuật vào
backlog và quay lại business behavior.

## 21. Ghi nhận bất đồng thay vì che giấu

Trong domain phức tạp, việc hai chuyên gia mô tả cùng một quy trình khác nhau
là dữ liệu quan trọng. Đừng chọn một cách hiểu chỉ vì người nói to hơn.

Có thể ghi:

~~~text
Open question:
  "Order can be cancelled after shipment?"

View A:
  Customer Support: yes, support can request cancellation.

View B:
  Fulfillment: no, shipment is irreversible.

Evidence needed:
  - current policy
  - two recent real cases
  - owner of cancellation policy

Decision owner:
  Operations
~~~

Khi có quyết định, cập nhật model và ghi nguồn bằng chứng. Nếu chưa có quyết
định, giữ trạng thái open để tránh biến giả định thành business rule.

## 22. Từ Model Canvas đến Implementation Slice

Khi đã có đủ hiểu biết cho một capability, nên chọn một vertical slice nhỏ
để kiểm chứng model.

~~~mermaid
flowchart TB
    U[Use case] --> L[Language]
    L --> R[Business rules]
    R --> M[Domain model]
    M --> A[Application flow]
    A --> I[Integration]
    I --> T[Tests]
    T --> F[Feedback]
    F --> L
~~~

Một slice tốt đi xuyên từ business scenario tới code và test. Nó cho phép
đội phát hiện sớm rằng một aggregate, event hoặc context boundary đang không
phù hợp.

Ví dụ thay vì xây toàn bộ Order context, có thể chọn slice:

> “Khách hàng xác nhận đơn khi thanh toán đã được authorize.”

Slice này đủ nhỏ để kiểm chứng thuật ngữ authorize, trạng thái Order,
invariant xác nhận và event OrderConfirmed.

## 23. Review Context Map theo thay đổi của tổ chức

Context Map không chỉ phản ánh kiến trúc runtime. Nó cũng phản ánh cách các
nhóm tổ chức công việc và trao đổi thông tin.

Khi team ownership thay đổi, hãy hỏi:

- Upstream/downstream relationship còn đúng không?
- Có context nào trở thành bottleneck không?
- Có shared model nào đang làm chậm deployment?
- Có contract nào không còn phù hợp?
- Có context nào đang dần trở thành core capability?

Điều này giúp tránh việc giữ nguyên context boundary chỉ vì nó từng được vẽ
trên một sơ đồ cũ.

## 24. Dùng Event Storming và Context Map cùng nhau

Hai công cụ trả lời hai câu hỏi khác nhau:

| Công cụ | Câu hỏi |
|---|---|
| Event Storming | Domain behavior diễn ra như thế nào? |
| Context Map | Các model và team boundary liên hệ thế nào? |

Có thể đi từ event storming đến context mapping bằng cách đánh dấu nơi một
thuật ngữ hoặc rule thay đổi ý nghĩa. Những điểm đó thường là ứng viên để
khảo sát bounded context.

Không nên suy ra rằng mỗi nhóm event là một microservice. Boundary của
domain model cần được xác định bằng semantics và consistency requirements;
quyết định deploy là bước kiến trúc tiếp theo.

## 25. Đánh giá tiến bộ bằng bằng chứng thay vì số lượng tài liệu

Một team không trở nên tốt hơn chỉ vì có thêm nhiều sơ đồ.

Các tín hiệu hữu ích hơn:

| Tín hiệu | Ý nghĩa |
|---|---|
| Domain expert sửa thuật ngữ sớm | Collaboration đang tạo learning |
| Rule được biểu diễn bằng test | Model có executable feedback |
| Boundary tranh luận ít hơn | Context semantics rõ hơn |
| Thay đổi business có trace rõ | Documentation có giá trị |
| Ít logic domain nằm trong controller | Model đang giữ đúng behavior |
| Integration contract rõ | Context coupling có kiểm soát |
| Team phát hiện giả định sai trước production | Feedback loop hiệu quả |

Metric nên giúp đội học tốt hơn, không trở thành mục tiêu để tối ưu hình thức.

## 26. Definition of Done cho một learning item

Một learning item có thể xem là hoàn thành khi:

~~~text
[ ] Câu hỏi nghiệp vụ đã được trả lời hoặc được xác định là chưa thể trả lời.
[ ] Ví dụ thực tế đã được ghi nhận.
[ ] Thuật ngữ liên quan đã được thống nhất trong context.
[ ] Quy tắc quan trọng đã được biểu diễn rõ.
[ ] Model đã được cập nhật nếu cần.
[ ] Test hoặc bằng chứng khác bảo vệ hành vi đã học.
[ ] Quyết định quan trọng có ADR hoặc ghi chú tương ứng.
[ ] Open questions còn lại có owner.
[ ] Next review được xác định khi cần.
~~~

Điều này giúp “học xong” có nghĩa cụ thể. Nếu câu hỏi chưa có bằng chứng,
đừng đánh dấu hoàn thành chỉ vì workshop đã diễn ra.

## 27. Definition of Done cho một thay đổi model

Một model change nên được xem xét qua các lớp:

1. Business behavior đã được xác nhận.
2. Ubiquitous Language đã được cập nhật.
3. Model và invariant đã được điều chỉnh.
4. Test mô tả behavior mới.
5. Integration contract được kiểm tra nếu có.
6. ADR hoặc decision log được cập nhật nếu đây là quyết định đáng kể.
7. Context Map được cập nhật nếu boundary hoặc relationship thay đổi.
8. Người sở hữu domain đã xác nhận ý nghĩa.

Không phải mọi thay đổi đều cần một workshop lớn. Mức độ collaboration nên
tương xứng với mức độ bất định và tác động của thay đổi.

## 28. Một ví dụ đầy đủ về vòng cải tiến

Giả sử team ban đầu mô hình hóa:

~~~text
Order
  status: CONFIRMED
  confirm()
~~~

Sau khi nói chuyện với bộ phận vận hành, team phát hiện Confirmed chỉ có
nghĩa là đơn được xác nhận về mặt thương mại; fulfillment có một trạng thái
riêng.

Vòng cải tiến có thể diễn ra như sau:

~~~text
Discovery:
  "Confirmed" có hai cách hiểu.

Language:
  Sales dùng OrderConfirmed.
  Fulfillment dùng FulfillmentAccepted.

Context:
  Sales Order và Fulfillment Model giữ hai state machine riêng.

Integration:
  Sales phát OrderConfirmed.
  Fulfillment quyết định có thể nhận xử lý hay không.

Model:
  Không dùng chung một Order aggregate giữa hai context.

Tests:
  Sales kiểm tra invariant xác nhận đơn.
  Fulfillment kiểm tra rule tiếp nhận fulfillment.

Documentation:
  Context Map + contract + ADR được cập nhật.
~~~

Điểm quan trọng là team đã học được điều mới và để kiến thức đó thay đổi
model. Đây chính là mục tiêu của continuous modeling.

## 29. Khi nào nên refactor mô hình

Refactor model khi:

- Một thuật ngữ mới phản ánh chính xác hơn business concept.
- Một aggregate có quá nhiều invariant không cùng thuộc một consistency
  boundary.
- Một domain service chỉ tồn tại vì behavior đang đặt sai chỗ.
- Một context phải hiểu quá nhiều chi tiết của context khác.
- Một event không còn phản ánh business fact.
- Code và tài liệu dùng hai mô hình khác nhau.

Refactor không nhất thiết đồng nghĩa với thay đổi database ngay lập tức.
Có thể thay đổi domain model trước, sau đó dùng application/infrastructure
mechanisms để chuyển đổi dữ liệu và contract theo từng bước.

## 30. Khi nào không nên mở rộng model

Không phải mọi yêu cầu đều cần một abstraction mới.

Nếu một khái niệm:

- chưa có behavior hoặc rule riêng,
- không giúp diễn đạt business language,
- chỉ tồn tại để phục vụ một framework,
- hoặc chỉ làm code “trông giống DDD” hơn,

thì chưa có đủ lý do để đưa nó thành một building block riêng.

Mô hình tốt có đủ khái niệm để biểu đạt domain nhưng vẫn giữ được khả năng
thay đổi. Lộ trình học giúp đội biết khi nào mình có đủ bằng chứng để thêm
khái niệm.

## 31. Mẫu Model Learning Log

Đội có thể dùng một mẫu ngắn để ghi lại vòng học:

~~~markdown
## Model Learning Log

Date:
Scenario:
Participants:

### What we believed
- ...

### What we learned
- ...

### Language changes
- Old:
- New:

### Model changes
- ...

### Evidence
- Example:
- Policy:
- Test:

### Open questions
- ...

### Decisions
- ...

### Follow-up
- Owner:
- Review date:
~~~

Mẫu này có giá trị nhất khi chỉ ghi những thay đổi thực sự quan trọng. Nếu
log trở thành một bản ghi hành chính dài, đội sẽ ngừng cập nhật nó.

## 32. Mẫu lộ trình học cho một capability

Một roadmap có thể được khởi tạo như sau:

~~~text
Capability: Order Management

Phase 1 — Discovery
  - Identify business outcome
  - Run event storming
  - Collect real examples

Phase 2 — Language
  - Define key terms
  - Resolve synonyms
  - Record unresolved meanings

Phase 3 — Strategic design
  - Identify subdomain type
  - Propose bounded context
  - Map upstream/downstream relationships

Phase 4 — Tactical model
  - Identify aggregates
  - Define invariants
  - Model value objects and domain services

Phase 5 — Verification
  - Write behavior-focused tests
  - Validate application flow
  - Check integration contracts

Phase 6 — Production feedback
  - Observe real behavior
  - Review incidents and support cases
  - Update model and learning backlog
~~~

Roadmap này không phải một quy trình tuyến tính bất biến. Production feedback
có thể đưa team quay về bất kỳ phase nào.

## 33. Vai trò của Domain Expert và Developer

Domain expert cung cấp kiến thức về business behavior, constraints, exceptions
và mục tiêu. Developer giúp biến kiến thức đó thành mô hình có thể thực thi,
kiểm thử và tích hợp.

Không nên chia thành hai bên “người biết nghiệp vụ” và “người biết code” rồi
chuyển tài liệu qua lại. Collaboration hiệu quả hơn khi hai bên cùng xem một
scenario và cùng điều chỉnh ngôn ngữ.

Một câu hỏi của developer như “điều kiện nào làm giao dịch này không hợp lệ?”
có thể giúp domain expert phát hiện một rule chưa từng được nói rõ. Ngược
lại, một domain expert sửa tên event có thể làm developer nhận ra rằng model
đang mô tả implementation thay vì business fact.

## 34. Tổ chức knowledge ownership

Không nên để một cá nhân trở thành “database sống” của domain. Khi một quy tắc
chỉ tồn tại trong trí nhớ của một người, team có bus factor cao và khó review.

Hãy phân tán kiến thức qua:

- Ubiquitous Language.
- Ví dụ và acceptance tests.
- ADR.
- Context Map.
- Domain model trong code.
- Workshop notes có chọn lọc.

Domain expert vẫn là nguồn xác nhận quan trọng, nhưng kiến thức đã được ghi
lại phải đủ rõ để người mới có thể đặt câu hỏi và tiếp tục học.

## 35. Cách onboarding thành viên mới vào domain

Onboarding DDD nên bắt đầu từ behavior, không bắt đầu từ package tree.

Một trình tự hữu ích:

1. Đọc domain glossary của context.
2. Đọc một vài use case quan trọng.
3. Xem Context Map liên quan.
4. Đọc các examples và acceptance tests.
5. Chạy một scenario nhỏ qua code.
6. Tham gia một session với domain expert.
7. Tự giải thích lại một rule bằng ngôn ngữ của context.
8. Nhận một learning item nhỏ và cập nhật model.

Bước “giải thích lại” rất quan trọng. Nó biến onboarding thành một vòng kiểm
chứng hiểu biết thay vì chỉ đọc tài liệu.

## 36. Continuous Modeling trong thực tế

Continuous modeling không có nghĩa là liên tục vẽ lại sơ đồ. Nó có nghĩa là
team luôn sẵn sàng cập nhật model khi bằng chứng mới xuất hiện.

Một vòng thực tế có thể là:

~~~mermaid
flowchart LR
    A[Business change] --> B[Discovery]
    B --> C[Examples]
    C --> D[Language]
    D --> E[Model]
    E --> F[Code and tests]
    F --> G[Deploy]
    G --> H[Production feedback]
    H --> B
~~~

Nếu vòng này chạy đều, tài liệu, model và code có xu hướng cùng tiến hóa.
Nếu một mắt xích bị bỏ qua, drift có thể tích lũy.

## 37. Checklist cuối mỗi vòng học

~~~text
Domain
  [ ] Business outcome rõ
  [ ] Scenario thực tế được chọn
  [ ] Domain expert phù hợp tham gia
  [ ] Rules và exceptions được xác nhận

Language
  [ ] Terms được thống nhất
  [ ] Synonyms/conflicts được xử lý
  [ ] Context của từng nghĩa rõ

Strategic design
  [ ] Subdomain classification có lý do
  [ ] Bounded Context có boundary rõ
  [ ] Context relationship có contract/meaning rõ

Tactical design
  [ ] Entity/Value Object có lý do
  [ ] Aggregate bảo vệ invariant
  [ ] Repository phục vụ aggregate boundary
  [ ] Domain Service chỉ dùng khi behavior không tự nhiên thuộc object

Verification
  [ ] Examples được chuyển thành tests khi phù hợp
  [ ] Cross-context contract được kiểm tra
  [ ] Regression được cập nhật

Documentation
  [ ] Ubiquitous Language cập nhật
  [ ] ADR cập nhật nếu cần
  [ ] Open questions có owner
  [ ] Learning log ghi lại insight quan trọng

Feedback
  [ ] Có cách quan sát behavior thực tế
  [ ] Next review được xác định
~~~

## 38. Nguyên tắc giữ lộ trình học hữu ích

Một lộ trình DDD có thể được giữ gọn bằng vài nguyên tắc:

1. Học từ business scenario cụ thể.
2. Ghi lại bằng chứng, không biến giả định thành sự thật.
3. Dùng một ngôn ngữ nhất quán trong một bounded context.
4. Để model phản ánh behavior và invariant.
5. Dùng code và test để kiểm chứng model.
6. Ghi quyết định quan trọng để giải thích lịch sử của model.
7. Review context boundary khi domain hoặc tổ chức thay đổi.
8. Ưu tiên câu hỏi có tác động cao và bất định cao.
9. Giữ tài liệu ngắn, gần nơi thay đổi và có owner.
10. Xem production feedback là một phần của quá trình học.

Khi áp dụng các nguyên tắc này, documentation trở thành một phần của vòng
học DDD. Event Storming giúp khám phá behavior, Ubiquitous Language giúp
thống nhất cách gọi, Context Map giúp làm rõ ranh giới và quan hệ, tactical
model giúp bảo vệ rule trong code, còn test và production feedback cung cấp
bằng chứng cho vòng cải tiến tiếp theo.
