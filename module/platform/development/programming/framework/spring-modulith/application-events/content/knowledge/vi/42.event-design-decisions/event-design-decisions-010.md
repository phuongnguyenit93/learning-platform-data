# Ghi lại quyết định

Trong module SPRING_MODULITH_APPLICATION_EVENTS, application events tạo ra các ranh giới giao tiếp giữa module phát và module nhận. Những lựa chọn như event nào được công bố, payload chứa dữ liệu gì, listener chạy khi nào, có externalize hay không, retry ra sao và ai sở hữu contract đều ảnh hưởng tới khả năng bảo trì của hệ thống. Khi chỉ lưu code mà không ghi lại lý do, người phát triển sau này khó biết lựa chọn nào là chủ ý kiến trúc, lựa chọn nào chỉ là chi tiết triển khai tạm thời.

Ghi lại quyết định bằng Architecture Decision Record (ADR) giúp lưu bối cảnh, lựa chọn đã cân nhắc, quyết định được chấp nhận và hệ quả của nó. ADR tạo ra lịch sử có thể tra cứu để nhóm phát triển hiểu vì sao event được thiết kế theo cách hiện tại, biết giới hạn cần giữ và có cơ sở đánh giá khi bối cảnh thay đổi.

## 1. ADR là gì?

Architecture Decision Record là tài liệu ngắn ghi lại một quyết định kiến trúc quan trọng tại thời điểm quyết định được đưa ra. ADR tập trung vào một câu hỏi cụ thể, ví dụ:

- Module Orders phát `OrderConfirmed` sau khi transaction commit hay trước commit?
- Event contract dùng immutable DTO hay truyền JPA entity?
- Consumer nhận snapshot dữ liệu hay chỉ nhận aggregate ID?
- Event nội bộ có được externalize sang broker không?
- Hệ thống xử lý publication chưa hoàn tất bằng retry, resubmit hay quy trình vận hành?
- Event version được biểu diễn trong type name hay schema metadata?

ADR không phải tài liệu mô tả toàn bộ hệ thống, không phải biên bản họp theo trình tự thời gian và cũng không phải event payload được gửi tới listener. Nó lưu lại lý do và hệ quả của một quyết định để người đọc có thể hiểu, áp dụng và xem xét lại quyết định đó.

## 2. Vì sao cần ghi lại quyết định về application events?

Event-driven design có nhiều lựa chọn liên quan chặt chẽ với nhau. Một thay đổi nhỏ ở publisher có thể ảnh hưởng listener, transaction boundary, Event Publication Registry, externalization, broker và consumer.

ADR giúp:

- **Giữ bối cảnh:** giải thích vấn đề nghiệp vụ hoặc kỹ thuật khiến nhóm cần quyết định.
- **Làm rõ trade-off:** ghi cả lợi ích, chi phí và rủi ro của lựa chọn được chọn.
- **Giảm tranh luận lặp lại:** người mới có thể đọc lý do đã được cân nhắc thay vì suy đoán.
- **Giữ ranh giới module:** chỉ rõ module nào sở hữu event contract và consumer được phép phụ thuộc vào phần nào.
- **Hỗ trợ vận hành:** lưu các giả định về retry, idempotency, retention, ordering và phục hồi.
- **Hỗ trợ migration:** biết consumer nào bị ảnh hưởng khi contract hoặc cơ chế giao event thay đổi.

Một ADR tốt giúp trả lời câu hỏi “Vì sao hệ thống làm như vậy?” và “Điều gì sẽ bị ảnh hưởng nếu thay đổi?”.

## 3. Khi nào nên tạo ADR?

Không cần tạo ADR cho mọi thay đổi code. Hãy ghi lại khi quyết định có tác động lâu dài, ảnh hưởng nhiều module hoặc khó đảo ngược.

| Tình huống | Có nên ghi ADR? | Lý do |
| --- | --- | --- |
| Chọn event DTO làm contract giữa hai module | Nên | Ảnh hưởng coupling và cách consumer sử dụng dữ liệu |
| Chọn xử lý listener sau commit và bất đồng bộ | Nên | Ảnh hưởng transaction, độ trễ và cách kiểm thử |
| Chọn Event Publication Registry có persistence | Nên | Ảnh hưởng khả năng phục hồi publication sau restart |
| Chọn externalize event sang Kafka hoặc broker khác | Nên | Ảnh hưởng topology, contract, bảo mật và vận hành |
| Chọn chính sách retry, idempotency và dead-letter | Nên | Ảnh hưởng độ tin cậy và side effect |
| Thay tên biến cục bộ trong listener | Thường không | Không làm thay đổi kiến trúc hoặc contract |
| Chỉnh format log theo convention đã thống nhất | Thường không | Có thể theo coding guideline thông thường |
| Thay serializer hoặc schema theo cách ảnh hưởng consumer | Nên | Có thể phá vỡ tương thích và replay |

Quyết định nhỏ vẫn có thể được ghi trong một ADR hiện có nếu nó là hệ quả của quyết định đó. Tránh tạo quá nhiều tài liệu cho các lựa chọn không có tác động kiến trúc.

## 4. Nguyên tắc viết ADR

Một ADR hữu ích nên tuân theo các nguyên tắc:

1. **Một quyết định chính:** mỗi ADR giải quyết một câu hỏi có phạm vi rõ ràng. Nếu có hai quyết định độc lập, tách thành hai ADR và liên kết chúng.
2. **Ghi tại thời điểm quyết định:** lưu bối cảnh và các phương án khi nhóm còn nhớ vì sao chúng được cân nhắc.
3. **Nêu lựa chọn thay thế:** ghi phương án đã xem xét và lý do không chọn, tránh chỉ ghi kết quả cuối cùng.
4. **Ghi hệ quả thực tế:** bao gồm cả chi phí, giới hạn, công việc vận hành và rủi ro.
5. **Dùng ngôn ngữ cụ thể:** nêu module, event type, transaction boundary, consumer và điều kiện áp dụng.
6. **Giữ lịch sử:** khi quyết định thay đổi, tạo ADR mới supersede ADR cũ thay vì viết lại quá khứ.
7. **Có thể truy vết:** liên kết ADR với code, schema, test, dashboard hoặc issue liên quan.

ADR không cần dài. Một quyết định đơn giản có thể chỉ cần một trang, nhưng phải đủ thông tin để người đọc hiểu bối cảnh và hệ quả.

## 5. Cấu trúc chuẩn của một ADR

Một cấu trúc thực tế có thể gồm:

| Phần | Câu hỏi cần trả lời |
| --- | --- |
| ID và tiêu đề | Đây là quyết định nào? |
| Status | Đề xuất, đã chấp nhận, bị từ chối hay đã được thay thế? |
| Date và deciders | Quyết định được ghi khi nào và ai chịu trách nhiệm? |
| Context | Vấn đề và bối cảnh hiện tại là gì? |
| Decision drivers | Những tiêu chí nào quan trọng? |
| Options considered | Các phương án nào đã được cân nhắc? |
| Decision | Nhóm chọn phương án nào và phạm vi áp dụng ra sao? |
| Consequences | Lợi ích, chi phí, rủi ro và công việc tiếp theo là gì? |
| Validation | Làm sao xác minh quyết định được triển khai đúng? |
| References | Code, schema, test, dashboard hoặc ADR liên quan nằm ở đâu? |

Không bắt buộc mọi ADR phải có cùng độ dài. Có thể bỏ phần không liên quan, nhưng Context, Decision, Consequences và Status nên luôn rõ ràng.

## 6. Vòng đời và trạng thái ADR

Trạng thái giúp người đọc biết quyết định đang ở giai đoạn nào:

| Status | Ý nghĩa |
| --- | --- |
| Proposed | Đang được đề xuất và chờ xem xét |
| Accepted | Đã được chấp nhận và là hướng triển khai hiện hành |
| Rejected | Đã xem xét nhưng không chọn |
| Deprecated | Không còn khuyến nghị áp dụng cho phần mới, nhưng vẫn có thể tồn tại trong hệ thống |
| Superseded | Đã được thay thế bởi một ADR khác |

Một luồng thông thường:

~~~mermaid
stateDiagram-v2
    [*] --> Proposed
    Proposed --> Accepted
    Proposed --> Rejected
    Accepted --> Deprecated
    Accepted --> Superseded
    Deprecated --> Superseded
~~~

Không dùng `Accepted` chỉ vì code đã được merge nếu quyết định chưa được người có trách nhiệm xem xét. Ngược lại, nếu quyết định đã được chấp nhận nhưng triển khai chưa hoàn tất, ADR vẫn có thể là Accepted và ghi rõ implementation status hoặc follow-up.

Khi ADR cũ bị thay thế, cập nhật trạng thái của ADR cũ và thêm liên kết tới ADR mới. Giữ nguyên phần Context, Decision và Consequences lịch sử để người đọc biết hệ thống đã đi qua những lựa chọn nào.

## 7. Ghi bối cảnh và tiêu chí quyết định

Context cần mô tả tình huống đủ cụ thể để người đọc hiểu vì sao cần quyết định. Với application events, có thể nêu:

- Module phát và các module hoặc service tiêu thụ.
- Luồng nghiệp vụ và invariant cần bảo vệ.
- Event hiện tại, payload và transaction boundary.
- Lưu lượng, độ trễ và yêu cầu phục hồi.
- Hạn chế về bảo mật, dữ liệu cá nhân và retention.
- Những consumer hoặc phiên bản đang tồn tại.

Decision drivers là tiêu chí dùng để so sánh phương án. Ví dụ:

- Giữ ranh giới module và giảm compile-time coupling.
- Không phát event cho transaction đã rollback.
- Có thể phục hồi listener sau khi ứng dụng restart.
- Consumer không tạo side effect trùng khi retry.
- Hỗ trợ thay đổi schema mà không buộc mọi consumer deploy đồng thời.
- Có thể quan sát backlog và điều tra event lỗi.

Tránh ghi Context chung chung như “cần hệ thống linh hoạt hơn”. Hãy mô tả vấn đề quan sát được và tác động nếu không giải quyết.

## 8. So sánh phương án và ghi trade-off

ADR cần cho thấy nhóm đã cân nhắc những lựa chọn thực tế. Ví dụ khi thiết kế payload event:

| Phương án | Lợi ích | Chi phí hoặc rủi ro |
| --- | --- | --- |
| Publish trực tiếp JPA entity | Ít code chuyển đổi ban đầu | Rò rỉ persistence model, lazy loading, serialization và coupling |
| Chỉ publish aggregate ID | Payload nhỏ, ít lộ dữ liệu | Consumer phải query lại; dữ liệu đọc có thể đã thay đổi so với thời điểm event |
| Publish immutable DTO với snapshot tối thiểu | Contract rõ, consumer có dữ liệu tại thời điểm event | Cần quản lý schema/version và chọn field cẩn thận |

Đừng chỉ liệt kê ưu điểm của phương án được chọn. Ghi cả điều phải đánh đổi, ví dụ DTO cần được duy trì khi nghiệp vụ thay đổi hoặc snapshot có thể chứa dữ liệu nhạy cảm cần bảo vệ.

## 9. Các quyết định event thường cần ghi lại

Trong module Spring Modulith, những chủ đề sau thường đáng có ADR riêng khi chúng ảnh hưởng nhiều thành phần:

### 9.1. Ranh giới và quyền sở hữu event

Ghi rõ module nào sở hữu sự thật nghiệp vụ và contract nào được công bố. Consumer nên phụ thuộc vào event DTO hoặc API công khai; không phụ thuộc entity, repository hay implementation nội bộ của module phát.

### 9.2. Thời điểm publish và transaction

Ghi rõ event được publish trong transaction nào, listener chạy đồng bộ hay bất đồng bộ, có yêu cầu sau commit hay không và điều gì xảy ra khi transaction rollback. Với listener dùng `@ApplicationModuleListener`, cần mô tả hành vi sau commit và transaction xử lý listener theo cấu hình Spring Modulith đang áp dụng.

### 9.3. Payload và schema

Ghi lý do chọn ID hay snapshot, các field được công bố, đơn vị, timezone, nullability, dữ liệu nhạy cảm và quy tắc versioning. Nếu có integration event, ghi type identifier và serialization contract.

### 9.4. Độ tin cậy và phục hồi

Ghi cơ chế publication tracking, persistence, retry budget, backoff, idempotency, ordering, quarantine và cách resubmit. Phân biệt retry lời gọi dependency bên trong listener với phục hồi publication của registry.

### 9.5. Externalization và routing

Ghi event nào được externalize, destination logic, broker/topic, partition key hoặc routing key, consumer sở hữu và cách xử lý message không hỗ trợ version.

### 9.6. Bảo mật và retention

Ghi dữ liệu nào được phép xuất khỏi module, cách mã hóa, quyền truy cập, retention của publication/message/DLT và cách loại bỏ dữ liệu nhạy cảm khỏi log.

### 9.7. Observability

Ghi các metric, log field, trace context, SLO và alert cần có. Xác định ai theo dõi pending publication, oldest pending age, listener failure và consumer lag.

## 10. Ví dụ ADR: công bố OrderConfirmed dưới dạng DTO bất biến

Ví dụ sau minh họa một ADR hoàn chỉnh cho quyết định payload. ID, ngày và tên nhóm chỉ là dữ liệu mẫu; dự án thực tế cần dùng quy ước và người chịu trách nhiệm của mình.

### ADR-017 — Dùng immutable DTO cho event OrderConfirmed

**Status:** Accepted  
**Date:** 2026-11-25  
**Deciders:** Nhóm Orders và nhóm Inventory  
**Scope:** Contract event giữa module Orders và các consumer nội bộ cần biết đơn hàng đã được xác nhận

#### Context

Module Orders phát event khi đơn hàng chuyển sang trạng thái CONFIRMED. Module Inventory và một số projection cần biết mã đơn hàng, thời điểm xác nhận và số tiền tại thời điểm đó. Trước đây, listener nhận trực tiếp JPA entity `Order`, khiến consumer phụ thuộc association `Customer` và `OrderLine`, đồng thời có nguy cơ lazy loading sau khi transaction nguồn kết thúc.

#### Decision drivers

- Consumer không phụ thuộc persistence model của Orders.
- Event có thể được xử lý bất đồng bộ và retry.
- Consumer cần snapshot số tiền tại thời điểm xác nhận.
- Payload chỉ chứa dữ liệu cần thiết và không đưa thông tin cá nhân không liên quan.

#### Options considered

1. Publish JPA entity `Order`: ít code mapping nhưng tạo coupling và rủi ro lazy loading/serialization.
2. Publish riêng `orderId`: payload nhỏ nhưng consumer cần query lại; kết quả có thể phản ánh trạng thái mới hơn thời điểm event phát.
3. Publish immutable DTO với ID và snapshot tối thiểu: cần duy trì contract nhưng giữ được ý nghĩa sự kiện tại thời điểm phát.

#### Decision

Chọn phương án 3. Event contract V1 dùng immutable record:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmedV1(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        Instant occurredAt,
        BigDecimal totalAmount,
        String currency) {
}
~~~

Publisher tạo DTO từ aggregate trong transaction sau khi xác nhận đơn hàng. Listener nhận DTO và không truy cập entity hoặc repository nội bộ của Orders. Nếu một consumer cần trạng thái hiện tại, nó sử dụng query API công khai của Orders; nếu cần giá trị tại thời điểm event, nó dùng snapshot trong payload.

#### Consequences

**Tích cực:**

- Consumer không phụ thuộc entity hoặc quan hệ JPA của Orders.
- Payload độc lập với persistence context và có thể serialize.
- Snapshot giữ đúng số tiền tại thời điểm xác nhận.
- Event ID và aggregate version hỗ trợ idempotency và phát hiện thứ tự.

**Đánh đổi và trách nhiệm:**

- Nhóm Orders phải duy trì contract và quản lý version khi thay đổi không tương thích.
- Consumer cần xác định rõ field nào dùng snapshot, field nào cần query trạng thái hiện tại.
- Payload vẫn cần được kiểm soát quyền truy cập và retention.
- Listener phải xử lý event trùng một cách idempotent.

#### Validation

- Module test xác minh publisher tạo đúng DTO và không publish entity.
- Serialization contract test xác minh payload V1 có thể đọc lại.
- Listener test xác minh xử lý DTO sau commit.
- Retry test xác minh event ID không tạo side effect trùng.
- Module boundary test xác minh consumer không phụ thuộc repository nội bộ của Orders.

#### References

- Event type: `OrderConfirmedV1`.
- Publisher: use case xác nhận đơn hàng trong module Orders.
- Consumer: projection/listener thuộc module Inventory.
- Contract test và module boundary test của event.

ADR này quyết định hình dạng contract. Các quyết định độc lập như externalize sang broker nào, retry policy bao nhiêu lần hoặc retention bao lâu có thể được ghi ở ADR riêng và liên kết với ADR-017.

## 11. Mẫu ADR để tái sử dụng

Có thể dùng mẫu sau cho quyết định event tiếp theo:

~~~markdown
# ADR-NNN — <Tiêu đề quyết định>

**Status:** Proposed | Accepted | Rejected | Deprecated | Superseded
**Date:** YYYY-MM-DD
**Deciders:** <Vai trò hoặc nhóm chịu trách nhiệm>
**Scope:** <Module, event hoặc consumer bị ảnh hưởng>

## Context

<Vấn đề, bối cảnh hiện tại và lý do cần quyết định.>

## Decision drivers

- <Tiêu chí 1>
- <Tiêu chí 2>

## Options considered

1. <Phương án A>: lợi ích và hạn chế.
2. <Phương án B>: lợi ích và hạn chế.

## Decision

<Phương án được chọn, phạm vi áp dụng và quy tắc cụ thể.>

## Consequences

### Positive
- <Lợi ích>

### Negative / trade-offs
- <Chi phí, giới hạn hoặc rủi ro>

### Operational impact
- <Metrics, retry, retention, runbook hoặc migration>

## Validation

- <Test hoặc tiêu chí xác minh>

## References

- <Code, contract, schema, dashboard hoặc ADR liên quan>
~~~

Mẫu là điểm bắt đầu, không phải biểu mẫu bắt buộc. Hãy điều chỉnh các mục để phù hợp với quyết định, nhưng không bỏ qua bối cảnh, phương án thay thế và hệ quả.

## 12. Tổ chức ADR trong repository

Đặt ADR ở vị trí dễ tìm và có lịch sử version control. Ví dụ:

~~~text
docs/
  decisions/
    README.md
    ADR-001-event-contract-ownership.md
    ADR-002-async-listener-after-commit.md
    ADR-003-event-publication-persistence.md
    ADR-017-order-confirmed-immutable-dto.md
~~~

Index `README.md` có thể liệt kê ID, tiêu đề, status và liên kết tới ADR. Tên file và ID nên ổn định; không đổi ID chỉ vì tiêu đề được chỉnh sửa.

Với module lớn, có thể đặt ADR gần tài liệu kiến trúc của module hoặc dùng thư mục ADR chung cho toàn repository. Điều quan trọng là nhóm biết một quyết định được lưu ở đâu và có thể tìm theo event type, module hoặc chủ đề.

Không lưu ADR chỉ trong chat, email hoặc biên bản họp không được quản lý version. Những nơi đó có thể hỗ trợ thảo luận, nhưng bản quyết định được chấp nhận cần có một nguồn chuẩn.

## 13. Liên kết ADR với code và vận hành

ADR chỉ có giá trị khi có thể đối chiếu với hệ thống thực tế. Hãy liên kết tới:

- Event record hoặc schema được quyết định.
- Publisher và listener có liên quan.
- Cấu hình `@ApplicationModuleListener`, `@Externalized` hoặc adapter tương ứng.
- Module boundary test và contract test.
- Dashboard, metric, alert và runbook.
- ADR trước đó hoặc ADR thay thế.

Khi triển khai khác với quyết định, cần làm rõ đó là sai lệch tạm thời, implementation chưa hoàn tất hay một quyết định mới. Không để ADR Accepted mô tả một hệ thống đã thay đổi mà không có liên kết cập nhật.

## 14. Xem xét lại và thay thế quyết định

Quyết định có thể cần xem xét lại khi:

- Lưu lượng hoặc yêu cầu độ trễ thay đổi đáng kể.
- Xuất hiện consumer mới hoặc hệ thống bên ngoài mới.
- Event contract cần version mới.
- Chính sách bảo mật hoặc retention thay đổi.
- Một dependency hoặc broker không còn phù hợp.
- Retry/backlog thường xuyên vượt SLO.
- Framework hoặc persistence adapter thay đổi cách xử lý publication.

Khi xem xét lại, dùng ADR cũ làm bối cảnh. Nếu giữ quyết định, ghi nhận lý do tiếp tục giữ khi cần. Nếu thay đổi, tạo ADR mới, giải thích yếu tố mới và đánh dấu ADR trước là Superseded. Cập nhật liên kết từ ADR cũ sang ADR mới.

Không sửa nội dung lịch sử để khiến quyết định cũ trông như đã chọn phương án hiện tại ngay từ đầu. Lịch sử trung thực giúp nhóm hiểu vì sao kiến trúc thay đổi.

## 15. Những sai lầm cần tránh

- Ghi quyết định mà không ghi bối cảnh hoặc vấn đề cần giải quyết.
- Chỉ ghi phương án được chọn, bỏ qua lựa chọn thay thế.
- Không ghi trade-off, chi phí vận hành hoặc rủi ro.
- Gộp nhiều quyết định độc lập vào một ADR quá lớn.
- Tạo ADR cho mọi thay đổi code nhỏ khiến tài liệu khó tìm.
- Để ADR Proposed nhưng người đọc tưởng đó là quyết định đã được chấp nhận.
- Viết lại ADR cũ khi kiến trúc thay đổi, làm mất lịch sử.
- Không liên kết ADR với code, schema, test và runbook.
- Ghi lựa chọn như `@ApplicationModuleListener` mà không nêu lý do, transaction boundary và hệ quả.
- Nhầm ADR với event log hoặc payload application event.

## 16. Checklist trước khi chấp nhận ADR

Trước khi chuyển ADR sang Accepted, hãy xác nhận:

- Vấn đề và phạm vi quyết định được mô tả cụ thể.
- Module sở hữu event và các consumer bị ảnh hưởng được xác định.
- Tiêu chí quyết định phản ánh yêu cầu nghiệp vụ và vận hành.
- Các phương án thực tế đã được cân nhắc.
- Lý do chọn và trade-off được ghi rõ.
- Hệ quả với transaction, listener, registry, externalization hoặc broker đã được đánh giá nếu liên quan.
- Retry, idempotency, ordering, versioning và bảo mật được đề cập khi có ảnh hưởng.
- Có cách xác minh bằng test, metric hoặc tiêu chí vận hành.
- Có owner và liên kết tới tài liệu/code liên quan.
- Người chịu trách nhiệm đã xem xét và chấp nhận quyết định.

## Kết luận

Ghi lại quyết định giúp kiến trúc application events giữ được bối cảnh và lý do qua nhiều lần thay đổi. Dùng ADR để mô tả một quyết định có phạm vi rõ, nêu bối cảnh, tiêu chí, phương án thay thế, lựa chọn và hệ quả. Với Spring Modulith, ưu tiên ghi các quyết định ảnh hưởng tới ranh giới module, transaction, listener, payload, publication registry, externalization, retry, versioning và vận hành. Giữ ADR trong repository, liên kết với code và test, đồng thời tạo ADR mới khi quyết định cũ bị thay thế. Nhờ đó, nhóm có thể hiểu không chỉ hệ thống đang làm gì mà còn vì sao nó được thiết kế như vậy.
