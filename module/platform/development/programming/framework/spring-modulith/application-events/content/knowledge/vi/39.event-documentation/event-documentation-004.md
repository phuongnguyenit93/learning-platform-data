# Sơ đồ event flow

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module trao đổi thông tin nghiệp vụ mà không cần phụ thuộc trực tiếp vào implementation của nhau. Khi hệ thống có nhiều producer, listener, transaction, publication registry và broker, chỉ đọc code từng class sẽ khó thấy toàn bộ đường đi của một event. **Sơ đồ event flow** mô tả event được tạo ở đâu, đi qua những boundary nào, ai xử lý, khi nào dữ liệu được commit và điều gì xảy ra khi một bước thất bại.

Một sơ đồ tốt giúp developer, reviewer và người vận hành trả lời nhanh các câu hỏi: ai phát event, ai nhận event, listener chạy đồng bộ hay bất đồng bộ, event có chỉ được xử lý sau commit không, publication được lưu ở đâu, message có đi qua broker không, retry được thực hiện ở lớp nào và làm sao nhận biết một lần giao bị lặp.

Sơ đồ phải thể hiện đúng kiến trúc đang chạy. Nó là tài liệu về luồng và trách nhiệm, không phải hình minh họa chung cho mọi hệ thống event-driven. Hãy bắt đầu từ một use case cụ thể, vẽ các boundary có ý nghĩa và bổ sung các nhánh lỗi ảnh hưởng tới tính đúng đắn của nghiệp vụ.

## 1. Sơ đồ event flow trả lời những câu hỏi nào?

Một event flow thường cần thể hiện sáu nhóm thông tin:

1. **Nguồn phát:** use case, domain operation hoặc adapter nào tạo event?
2. **Đường đi:** event được publish trong application context, qua registry hay được externalize tới broker?
3. **Thời điểm:** listener chạy ngay, sau commit hay trên executor riêng?
4. **Người nhận:** module, listener hoặc consumer nào sở hữu xử lý?
5. **Độ tin cậy:** lỗi được retry, lưu publication, redeliver hay chuyển DLQ thế nào?
6. **Quan sát:** eventId, correlationId, trace và trạng thái nào giúp lần theo luồng?

Không phải sơ đồ nào cũng cần tất cả chi tiết. Sơ đồ tổng quan có thể chỉ nêu module và hướng event. Sơ đồ sequence cho một use case cần thể hiện thứ tự tương tác. Sơ đồ vận hành cần tập trung vào retry, acknowledgement, backlog và điểm phục hồi.

Trước khi vẽ, hãy viết một câu mô tả mục tiêu. Ví dụ: “Mô tả cách OrderConfirmed được phát sau khi đơn hàng commit, Inventory giữ hàng và Notification gửi thông báo qua broker.” Câu này xác định phạm vi và ngăn sơ đồ biến thành bản đồ của toàn bộ hệ thống.

## 2. Phân biệt event, command và message

Sơ đồ phải dùng đúng thuật ngữ vì chúng đại diện cho trách nhiệm khác nhau:

| Thành phần | Ý nghĩa | Câu hỏi chính |
|---|---|---|
| Command | Yêu cầu một thành phần thực hiện hành động | Ai được yêu cầu làm gì? |
| Domain event | Sự kiện đã xảy ra trong domain | Điều gì đã xảy ra? |
| Application event | Thông báo trong application context | Thành phần nào trong ứng dụng cần biết? |
| Integration event | Hợp đồng event được công bố qua boundary | Consumer độc lập nhận dữ liệu gì? |
| Message | Đơn vị dữ liệu được transport giao nhận | Message đang ở queue/topic nào? |
| Publication | Một lần giao event tới một listener hoặc adapter | Listener đã hoàn tất chưa? |

Một domain event không nhất thiết được gửi ra broker. Một application event có thể chỉ được các listener nội bộ nhận. Một integration event có thể được tạo từ domain event thông qua mapper để tránh công bố entity hoặc dữ liệu nội bộ.

Trong sơ đồ, hãy ghi rõ khi nào event được chuyển thành integration message. Không gộp publisher, event bus, externalization adapter và broker thành một khối duy nhất nếu chúng có transaction hoặc failure semantics khác nhau.

## 3. Chọn loại sơ đồ theo mục đích

Mỗi loại sơ đồ trả lời một câu hỏi khác nhau:

| Loại sơ đồ | Dùng để mô tả | Khi nên dùng |
|---|---|---|
| Context/flowchart | Module và boundary trao đổi event | Giới thiệu kiến trúc hoặc ownership |
| Sequence diagram | Thứ tự publish, commit, listener, ACK | Giải thích một use case cụ thể |
| State diagram | Vòng đời publication/message | Retry, incomplete, DLQ và recovery |
| Deployment/topology | Broker, exchange, queue, topic, consumer group | Vận hành và triển khai |
| Data flow | Payload đi qua đâu, được lưu ở đâu | Bảo mật, retention và data lineage |

Đừng dùng một flowchart để diễn tả mọi thứ. Nếu thứ tự thời gian quan trọng, sequence diagram thường rõ hơn. Nếu trạng thái có thể chuyển qua retry hoặc quarantine, state diagram phù hợp hơn. Nếu cần mô tả exchange, queue và routing key, hãy thêm topology view.

Có thể dùng một sơ đồ tổng quan và một hoặc hai sơ đồ chi tiết cho luồng quan trọng. Mỗi sơ đồ nên có tiêu đề, phạm vi, giả định và legend ngắn.

## 4. Các thành phần cơ bản trong event flow của Spring Modulith

Một luồng event nội bộ có thể gồm các thành phần:

- **Producer module:** module sở hữu use case và phát domain/application event.
- **Application event publisher:** điểm publish event vào Spring application context.
- **Event multicaster:** phân phối event tới các listener đã đăng ký.
- **Transactional listener:** nhận event theo transaction phase được cấu hình.
- **Application module listener:** listener theo cơ chế Spring Modulith, thường kết hợp xử lý bất đồng bộ và sau commit theo cấu hình/version.
- **Event Publication Registry:** theo dõi publication tới transactional listeners và trạng thái hoàn tất.
- **Externalization adapter:** chuyển event nội bộ thành message có contract và destination phù hợp.
- **Broker:** transport như RabbitMQ hoặc Kafka.
- **Consumer module/service:** nhận message và thực hiện use case thuộc ownership của nó.
- **Observability:** log, metric và trace liên kết các bước.

Sơ đồ tổng quan:

~~~mermaid
flowchart LR
    subgraph Order["Module Order"]
        U["Confirm order use case"]
        P["Publish OrderConfirmed"]
    end
    subgraph Spring["Spring application context"]
        M["Event multicaster"]
        R["Publication registry"]
        L1["Inventory listener"]
        L2["Externalization listener"]
    end
    subgraph Transport["Messaging boundary"]
        B["Broker"]
        C["Remote consumer"]
    end
    U --> P
    P --> M
    M --> R
    M --> L1
    M --> L2
    L2 --> B
    B --> C
~~~

Đây là sơ đồ khái niệm. Trong ứng dụng thực tế, registry theo dõi các publication thuộc listener phù hợp; không nhất thiết mọi listener hoặc mọi event đều được lưu theo cùng cách. Hãy điều chỉnh các khối theo loại listener, adapter và persistence đang dùng.

## 5. Luồng publish và listener đồng bộ trong cùng application context

Khi listener thông thường được đăng ký với Spring event multicaster mặc định, listener có thể được gọi đồng bộ trong luồng publish. Điều này có nghĩa lời gọi publisher có thể chỉ hoàn tất sau khi listener trả về. Nếu listener ném exception, exception có thể lan ngược tới caller tùy cơ chế dispatch và cấu hình.

~~~mermaid
sequenceDiagram
    participant U as Use case Order
    participant P as ApplicationEventPublisher
    participant M as Event multicaster
    participant L as Inventory listener
    participant D as Inventory database
    U->>P: publish(OrderConfirmed)
    P->>M: Dispatch event
    M->>L: Invoke listener
    L->>D: Reserve inventory
    D-->>L: Result
    L-->>M: Return
    M-->>P: Dispatch complete
    P-->>U: Return
~~~

Trong luồng đồng bộ, thời gian xử lý listener ảnh hưởng trực tiếp tới latency của use case. Một listener chậm có thể kéo dài request hoặc transaction. Nếu listener thất bại, cần hiểu exception có làm transaction của producer rollback hay không; điều đó phụ thuộc vị trí publish, transaction boundary và listener semantics.

Sơ đồ cần ghi rõ listener đồng bộ nếu đây là giả định quan trọng. Không suy luận rằng mọi application event đều đồng bộ; executor hoặc cấu hình multicaster có thể thay đổi hành vi.

## 6. Luồng event sau khi transaction commit

Với transactional event listener ở phase AFTER_COMMIT, event được publish trong transaction nhưng listener chỉ đủ điều kiện xử lý sau khi transaction commit thành công. Nếu transaction rollback, callback AFTER_COMMIT không được thực hiện.

~~~mermaid
sequenceDiagram
    participant U as Order service
    participant DB as Order database
    participant E as Event publisher
    participant R as Publication registry
    participant L as Inventory listener
    participant I as Inventory database
    U->>DB: Begin transaction
    U->>DB: Save confirmed order
    U->>E: Publish OrderConfirmed
    E->>R: Register listener publication
    U->>DB: Commit
    DB-->>U: Commit success
    R-->>L: Trigger eligible publication
    L->>I: Reserve inventory
    I-->>L: Commit inventory result
    L-->>R: Mark publication complete
~~~

Sơ đồ này mô tả ý tưởng của transactional publication. Thứ tự và chi tiết persistence thực tế phụ thuộc cấu hình Spring Modulith, transaction manager và loại listener. Khi viết tài liệu cho ứng dụng cụ thể, hãy đối chiếu cấu hình thật thay vì giả định mọi listener đều dùng cùng phase.

Điểm cần làm rõ:

- Event được publish trước hay sau khi dữ liệu nguồn commit?
- Publication có được lưu bền vững cùng transaction không?
- Listener chạy sau commit trên thread hiện tại hay executor khác?
- Listener thất bại thì publication được đánh dấu thế nào?
- Có cơ chế resubmit publication incomplete không?
- Consumer có idempotent khi publication được giao lại không?

Không mô tả listener AFTER_COMMIT như một phần của transaction nguồn. Khi transaction nguồn đã commit, lỗi ở listener không thể tự động rollback dữ liệu nguồn đã commit.

## 7. Luồng rollback

Một sơ đồ event flow cần thể hiện nhánh transaction rollback, đặc biệt khi event chỉ được xử lý sau commit.

~~~mermaid
sequenceDiagram
    participant U as Order service
    participant DB as Order database
    participant E as Event publisher
    participant L as AFTER_COMMIT listener
    U->>DB: Begin transaction
    U->>DB: Save order
    U->>E: Publish OrderConfirmed
    U->>DB: Commit attempt
    DB-->>U: Rollback
    Note over L: AFTER_COMMIT listener không chạy
    Note over DB: Order change không được commit
~~~

Nếu test hoặc tài liệu chỉ vẽ đường thành công, người đọc có thể hiểu nhầm event luôn dẫn tới listener. Hãy thêm nhánh rollback khi nó ảnh hưởng tới invariant hoặc là một câu hỏi vận hành quan trọng.

Cũng cần phân biệt rollback với listener failure sau commit. Rollback nghĩa transaction nguồn không commit; listener failure nghĩa dữ liệu nguồn đã commit nhưng publication chưa hoàn tất hoặc consumer chưa thực hiện xong.

## 8. Event Publication Registry trong sơ đồ

Event Publication Registry giúp theo dõi publication tới transactional listeners và xác định publication đã hoàn tất hay còn incomplete. Sơ đồ nên biểu diễn registry ở đúng boundary và gắn nó với listener publication, không vẽ như một broker trung gian cho mọi event.

Một vòng đời khái quát:

~~~mermaid
stateDiagram-v2
    [*] --> Registered: Event published
    Registered --> Processing: Listener eligible
    Processing --> Completed: Listener succeeds
    Processing --> Incomplete: Listener fails
    Incomplete --> Processing: Resubmit/retry
    Completed --> Retained: Keep for operational window
    Retained --> Purged: Cleanup policy
    Purged --> [*]
~~~

Trạng thái trong sơ đồ là mô hình giải thích. Tên trạng thái, API quản lý, điều kiện resubmit và cleanup phụ thuộc phiên bản Spring Modulith cùng persistence adapter. Không gắn tên state minh họa vào database schema nếu ứng dụng không thực sự có các state đó.

Khi vẽ registry, thể hiện ít nhất:

- Publication được tạo cho listener nào.
- Thời điểm listener đủ điều kiện nhận event.
- Kết quả listener và cách publication được đánh dấu hoàn tất.
- Nhánh incomplete khi listener ném exception hoặc process dừng.
- Cơ chế quan sát và phục hồi publication chưa hoàn tất.
- Retention và cleanup publication đã hoàn tất.

## 9. Luồng externalization qua broker

Khi event cần tới hệ thống hoặc service độc lập, externalization adapter chuyển event nội bộ thành integration message. Message được gửi tới broker, sau đó consumer nhận, deserialize và gọi use case của nó.

~~~mermaid
sequenceDiagram
    participant O as Order module
    participant A as Externalization adapter
    participant B as Broker
    participant C as Inventory consumer
    participant D as Inventory database
    O->>A: OrderConfirmed
    A->>A: Map to integration envelope
    A->>B: Publish message
    B-->>A: Broker confirmation
    B->>C: Deliver message
    C->>C: Validate and deserialize
    C->>D: Apply reservation
    D-->>C: Commit
    C-->>B: ACK/commit offset
~~~

Đây là luồng khái quát. Với RabbitMQ, consumer thường ACK/NACK delivery theo cơ chế channel. Với Kafka, consumer thường quản lý offset commit; không nên dùng một ký hiệu ACK chung mà bỏ qua khác biệt semantics nếu tài liệu tập trung vào broker cụ thể.

Nếu ứng dụng dùng transactional outbox, hãy thêm outbox store và dispatcher vào sơ đồ. Nếu dùng externalization listener được registry quản lý, thể hiện publication registry ở phía ứng dụng. Không gộp hai cơ chế thành một khối nếu implementation chỉ dùng một trong hai hoặc nếu chúng có transaction boundary khác nhau.

## 10. Luồng transactional outbox

Transactional outbox lưu message cần gửi trong cùng transaction với thay đổi nghiệp vụ. Dispatcher gửi message sau commit. Cách này tránh tình huống database commit thành công nhưng process dừng trước khi publish message.

~~~mermaid
sequenceDiagram
    participant S as Order service
    participant DB as Database
    participant O as Outbox table
    participant W as Dispatcher
    participant B as Broker
    S->>DB: Begin transaction
    S->>DB: Save order
    S->>O: Insert OrderConfirmed
    S->>DB: Commit
    DB-->>S: Commit success
    W->>O: Read pending message
    W->>B: Publish message
    B-->>W: Confirm
    W->>O: Mark sent
~~~

Có một khoảng lỗi quan trọng: broker có thể đã nhận message nhưng dispatcher dừng trước khi đánh dấu outbox là SENT. Khi chạy lại, dispatcher có thể gửi lại cùng message. Vì vậy, outbox thường hỗ trợ giao ít nhất một lần và consumer cần deduplication/idempotency.

Nếu sơ đồ không dùng outbox, không thêm outbox table chỉ vì đó là pattern phổ biến. Hãy mô tả đúng cơ chế persistence thực tế của module.

## 11. Luồng retry, duplicate và phục hồi

Retry có thể xuất hiện ở nhiều lớp: listener invocation, publication resubmission, outbox dispatcher, broker redelivery hoặc consumer retry policy. Sơ đồ phải ghi rõ ai sở hữu retry và điều kiện dừng.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant I as Inbox store
    participant D as Business database
    B->>C: Deliver event E-42
    C->>I: Claim event identity
    I-->>C: First delivery
    C->>D: Apply business change
    D-->>C: Commit
    Note over C,B: ACK bị mất hoặc process dừng
    B->>C: Redeliver event E-42
    C->>I: Check event identity
    I-->>C: Already completed
    C-->>B: ACK duplicate
~~~

Khi duplicate delivery xảy ra, consumer dùng event identity và inbox/dedup store để tránh lặp tác dụng nghiệp vụ. Nếu không có inbox, cần một invariant hoặc idempotency key khác bảo vệ tác dụng phụ.

Một sơ đồ retry nên thể hiện:

- Nguyên nhân retry: timeout, exception tạm thời, broker redelivery hoặc publication incomplete.
- Backoff và giới hạn số lần thử nếu có.
- Điểm lưu trạng thái attempt.
- Điều kiện chuyển DLQ/quarantine/manual review.
- Cách operator replay message.
- Cơ chế idempotency ở consumer.

Không vẽ một vòng retry vô hạn mà không có chính sách dừng. Poison message hoặc lỗi contract không thể tự hết khi retry liên tục.

## 12. State diagram cho message và publication

Message transport và publication registry có vòng đời khác nhau. Nên dùng hai state diagram nếu cần giải thích cả hai.

Vòng đời message ở một consumer có thể được mô hình hóa:

~~~mermaid
stateDiagram-v2
    [*] --> Received
    Received --> Validating
    Validating --> Processing: Contract valid
    Validating --> Quarantined: Invalid payload
    Processing --> Completed: Business transaction committed
    Processing --> Retryable: Transient failure
    Processing --> Failed: Permanent failure
    Retryable --> Received: Retry/redelivery
    Failed --> Quarantined: Retry exhausted
    Completed --> [*]
    Quarantined --> [*]
~~~

Đây là trạng thái nghiệp vụ/consumer minh họa, không phải trạng thái chuẩn của RabbitMQ, Kafka hoặc Spring Modulith. Hãy đổi tên theo store và retry policy thực tế.

Không gộp message ACK với trạng thái Completed nếu hai bước có thể tách rời. Consumer có thể commit nghiệp vụ rồi ACK bị mất; khi đó message bị giao lại dù tác dụng nghiệp vụ đã hoàn tất. Đây là lý do deduplication cần được thể hiện riêng trong flow.

## 13. Phân biệt các điểm commit và acknowledgement

Trong sơ đồ event flow, các điểm commit cần được ghi rõ vì chúng quyết định dữ liệu nào đã bền vững khi lỗi xảy ra.

| Điểm | Điều được xác nhận | Điều chưa được bảo đảm |
|---|---|---|
| Producer DB commit | Thay đổi nghiệp vụ nguồn đã commit | Listener hoặc broker đã xử lý |
| Publication persisted | Publication state đã được ghi theo cơ chế registry | Consumer đã hoàn tất tác dụng nghiệp vụ |
| Outbox commit | Message cần gửi được lưu cùng nghiệp vụ | Broker đã nhận message |
| Broker confirm | Broker đã xác nhận publish theo semantics của transport | Consumer đã xử lý |
| Consumer DB commit | Tác dụng nghiệp vụ consumer đã commit | ACK/offset đã được broker ghi nhận |
| ACK/offset commit | Broker có thể tiến tới message tiếp theo theo semantics transport | Mọi downstream consumer khác đã hoàn tất |

Sơ đồ nên dùng các nhãn như “DB commit”, “broker confirm”, “consumer commit” và “ACK/offset commit” thay vì một nhãn chung “success”. Điều đó giúp người đọc xác định chính xác cửa sổ lỗi.

## 14. Vẽ failure path theo từng boundary

Mỗi boundary có kiểu lỗi và cách phục hồi khác nhau. Bảng dưới đây giúp xác định nhánh cần đưa vào sơ đồ chi tiết:

| Boundary | Failure ví dụ | Hành động hoặc trạng thái cần thể hiện |
|---|---|---|
| Producer → database | Transaction rollback | Không phát sinh thay đổi đã commit |
| Publisher → listener | Listener exception | Exception propagation hoặc publication incomplete |
| Registry → listener | Process dừng trước xử lý | Publication cần phục hồi theo cấu hình |
| Outbox → broker | Broker unavailable | Giữ pending, retry dispatcher |
| Broker → consumer | Consumer offline | Message còn trong queue/topic theo retention |
| Deserialize | Schema không tương thích | Reject, quarantine hoặc DLQ |
| Consumer → database | Constraint/deadlock | Rollback, retry nếu phù hợp |
| Consumer commit → ACK | ACK mất | Redelivery và deduplication |
| Consumer → external API | Timeout không rõ kết quả | Idempotency key và reconciliation |

Không cần đưa mọi lỗi hiếm vào sơ đồ tổng quan. Hãy chọn failure có ảnh hưởng tới dữ liệu, duplicate, mất message hoặc khả năng phục hồi. Những lỗi chi tiết có thể được ghi trong sơ đồ failure handling riêng.

## 15. Event identity, correlation và trace

Một luồng có nhiều module hoặc service cần định danh để nối các bước trong log và trace.

- **eventId:** định danh duy nhất của một event.
- **correlationId:** liên kết các thao tác thuộc cùng một business flow.
- **causationId:** chỉ ra message hoặc command gây ra event hiện tại.
- **aggregateId:** đối tượng nghiệp vụ liên quan.
- **aggregateVersion:** phiên bản aggregate tại thời điểm event.
- **traceId/spanId:** liên kết các span trong distributed tracing.

Ví dụ OrderConfirmed tạo InventoryReserved, sau đó ReservationFailed. Các event có eventId riêng nhưng có thể dùng chung correlationId. CausationId của InventoryReserved có thể tham chiếu OrderConfirmed nếu contract và tracing policy quy định như vậy.

Trong sequence diagram, có thể ghi eventId và correlationId ở các message quan trọng. Không đưa customer email, token hoặc payload nhạy cảm vào label. Sơ đồ nên giúp truy vết bằng metadata ổn định mà không làm lộ dữ liệu.

## 16. Vẽ module ownership và dependency direction

Sơ đồ event flow phải cho thấy module nào sở hữu dữ liệu và use case. Producer không nên thao tác trực tiếp repository nội bộ của consumer. Consumer nhận event rồi gọi application service của chính module mình.

Ví dụ:

~~~mermaid
flowchart LR
    subgraph Order["Module Order"]
        O1["Confirm order"]
        O2["Order repository"]
        O3["OrderConfirmed"]
        O1 --> O2
        O1 --> O3
    end
    subgraph Inventory["Module Inventory"]
        I1["Inventory event listener"]
        I2["Reserve inventory use case"]
        I3["Inventory repository"]
        I1 --> I2
        I2 --> I3
    end
    O3 -. "Published event contract" .-> I1
~~~

Mũi tên nét đứt thể hiện event contract, không phải lời gọi trực tiếp tới implementation. Sơ đồ này nhấn mạnh Inventory tự sở hữu quyết định giữ hàng và dữ liệu tồn kho.

Nếu module có dependency trực tiếp qua API công khai, hãy vẽ khác với event publication. Không dùng cùng một loại mũi tên cho method call, event và broker delivery mà không có legend.

## 17. Security và data flow trên sơ đồ

Event có thể đi qua nhiều boundary tin cậy. Sơ đồ nên đánh dấu khi payload rời application context, đi qua network, vào broker hoặc tới service khác.

Thể hiện các thông tin cần thiết:

- Vùng trust boundary và network boundary.
- Producer identity và consumer authorization.
- Event type hoặc destination được phép publish/subscribe.
- Payload field nhạy cảm và cơ chế minimization.
- Encryption in transit/at rest nếu có.
- Quy trình redaction, retention và deletion.
- Secret hoặc credential được quản lý ngoài payload.

Không vẽ token hoặc secret thật vào sơ đồ. Nếu consumer cần truy cập object storage, thể hiện service identity hoặc authorization boundary, không đưa signed URL dài hạn vào ví dụ.

Một sơ đồ security/data flow có thể tách riêng khỏi sequence nghiệp vụ để không quá tải. Tuy nhiên, nếu event rời khỏi module hoặc ứng dụng, ít nhất cần đánh dấu điểm externalization và consumer boundary.

## 18. Observability gắn với từng bước trong flow

Sơ đồ vận hành nên cho biết mỗi bước phát ra tín hiệu nào để người trực hệ thống lần theo event.

| Bước | Log/trace/metric nên có |
|---|---|
| Producer tạo event | eventType, eventId, aggregateId, schemaVersion |
| Publish vào context | publisher outcome, correlationId, trace context |
| Registry ghi publication | listener identifier, publication age/state |
| Externalization | destination, payload bytes, publish latency |
| Broker nhận message | confirm/return, queue/topic, partition |
| Consumer nhận message | delivery attempt, consumer version |
| Consumer xử lý | handler duration, result, exception category |
| Consumer hoàn tất | DB commit, ACK/offset outcome |
| Retry/DLQ | attempt, delay, reason, quarantine count |

Metrics nên dùng tag cardinality thấp như eventType, destination logic và consumerName đã kiểm soát. eventId và aggregateId phù hợp với log/trace, không phù hợp làm tag metric có cardinality cao.

Khi vẽ sequence diagram, có thể thêm một participant Observability ở cạnh để thể hiện trace span hoặc log correlation. Không để observability thành một bước nghiệp vụ làm thay đổi thứ tự xử lý; nó là tín hiệu đi kèm các boundary.

## 19. Kiểm thử để xác nhận sơ đồ đúng

Sơ đồ là một giả thuyết có thể kiểm chứng. Mỗi mũi tên hoặc transition quan trọng nên liên hệ được với một test hoặc bằng chứng vận hành.

| Phần sơ đồ | Test phù hợp |
|---|---|
| Domain tạo event | Unit test hoặc application service test |
| Event dispatch tới listener | Module test với Spring context |
| Module dependency | Spring Modulith architecture verification |
| AFTER_COMMIT | Transaction integration test có commit/rollback |
| Publication registry | Test persistence và listener completion/recovery |
| Externalization adapter | Component/adapter test |
| Broker routing/ACK/redelivery | Broker integration test |
| Inbox/idempotency | Integration test với database constraint |
| Retry và DLQ | Test retry policy và transport topology |
| End-to-end flow | Một số scenario test cho hành trình trọng yếu |

Không lấy sơ đồ làm bằng chứng duy nhất rằng hệ thống đang chạy như vậy. Đối chiếu annotation listener, cấu hình executor, transaction manager, registry persistence, adapter và broker topology. Nếu implementation thay đổi, cập nhật sơ đồ cùng pull request hoặc thay đổi contract.

## 20. Quy ước trình bày Mermaid

Mermaid giúp sơ đồ nằm cùng tài liệu Markdown và dễ review qua Git. Dùng một số quy ước nhất quán:

- Flowchart: dùng khối cho module, database, broker và adapter; dùng mũi tên có nhãn cho loại tương tác.
- Sequence diagram: participant là thành phần có trách nhiệm; message label bắt đầu bằng động từ rõ ràng.
- State diagram: chỉ dùng cho trạng thái có chuyển đổi và điều kiện cụ thể.
- Subgraph: nhóm theo module hoặc trust boundary.
- Màu sắc: chỉ dùng khi có legend và có ý nghĩa ổn định.
- Tên: dùng tên event contract hoặc use case, không dùng tên class implementation tạm thời.
- Scope: một sơ đồ chỉ giải thích một use case hoặc một góc nhìn.
- Failure path: dùng alt/opt hoặc nhánh có nhãn để phân biệt success, rollback, retry và DLQ.

Ví dụ sequence diagram với nhánh thành công và lỗi:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Registry
    participant L as Listener
    participant DB as Consumer DB
    P->>R: Publish Event
    alt Listener succeeds
        R->>L: Invoke listener
        L->>DB: Apply business change
        DB-->>L: Commit
        L-->>R: Complete publication
    else Listener fails
        R->>L: Invoke listener
        L-->>R: Exception
        Note over R: Publication remains incomplete per configuration
    end
~~~

Dùng label có nghĩa nghiệp vụ. Tránh đặt tên participant như Service1, Handler2 hoặc QueueA nếu không có legend giải thích. Nếu sơ đồ dài, chia thành context view và sequence view thay vì thu nhỏ font hoặc nhồi nhiều participant.

## 21. Ví dụ hoàn chỉnh: OrderConfirmed tới Inventory và Notification

Giả sử module Order xác nhận đơn hàng trong transaction. Sau commit, module Inventory nhận OrderConfirmed để giữ hàng; một externalization adapter gửi integration event tới Notification service.

Luồng nghiệp vụ:

1. Order service kiểm tra điều kiện và lưu trạng thái CONFIRMED.
2. Order publish OrderConfirmed trong transaction.
3. Transaction commit thành công.
4. Inventory listener xử lý event theo module boundary và ghi reservation.
5. Externalization adapter chuyển event sang integration envelope.
6. Broker nhận message và consumer Notification gửi thông báo.
7. Mỗi consumer ghi nhận kết quả theo cơ chế idempotency phù hợp.

~~~mermaid
sequenceDiagram
    participant U as Order use case
    participant ODB as Order DB
    participant E as Application event
    participant R as Publication registry
    participant I as Inventory listener
    participant IDB as Inventory DB
    participant X as Externalization adapter
    participant B as Broker
    participant N as Notification consumer
    U->>ODB: Save CONFIRMED
    U->>E: Publish OrderConfirmed
    E->>R: Register transactional publications
    U->>ODB: Commit
    R->>I: Invoke after commit
    I->>IDB: Reserve items
    IDB-->>I: Commit reservation
    I-->>R: Mark complete
    R->>X: Invoke externalization
    X->>B: Publish integration message
    B-->>X: Confirm
    B->>N: Deliver message
    N->>N: Send notification idempotently
    N-->>B: ACK/commit offset
~~~

Sơ đồ trên giả định Inventory listener và externalization publication được quản lý theo cấu hình transactional listener phù hợp. Nếu externalization thực tế dùng outbox riêng, thay participant Registry/Externalization bằng Outbox table và Dispatcher. Nếu Notification chỉ là listener nội bộ, bỏ broker khỏi sơ đồ.

Cũng cần vẽ failure path riêng: Inventory reservation có thể thất bại sau khi Order đã commit; Notification có thể được giao lại; broker confirm có thể mất; listener có thể được resubmit. Những tình huống đó không được giải quyết chỉ bằng sơ đồ success.

## 22. Checklist review sơ đồ event flow

Trước khi đưa sơ đồ vào tài liệu hoặc pull request, kiểm tra:

- [ ] Tên event và module owner khớp với contract.
- [ ] Producer, listener, adapter, registry và broker được phân biệt rõ.
- [ ] Mũi tên thể hiện đúng loại tương tác: method call, event publish hay message delivery.
- [ ] Transaction begin, commit và rollback được ghi đúng vị trí.
- [ ] Listener sync/async và transaction phase được mô tả chính xác.
- [ ] Publication registry chỉ xuất hiện ở những luồng thực sự sử dụng nó.
- [ ] Outbox được vẽ khi implementation có outbox.
- [ ] Broker-specific ACK/offset semantics không bị gộp làm một.
- [ ] Retry, duplicate, DLQ hoặc recovery được thể hiện khi có liên quan.
- [ ] eventId/correlationId/trace context đủ để truy vết.
- [ ] Trust boundary và dữ liệu nhạy cảm được thể hiện phù hợp.
- [ ] Sơ đồ có liên kết tới test hoặc cấu hình xác minh.
- [ ] Phạm vi sơ đồ vừa đủ để người đọc theo dõi được.

## 23. Duy trì sơ đồ cùng thay đổi kiến trúc

Sơ đồ sẽ nhanh chóng mất giá trị nếu chỉ được tạo một lần. Mỗi thay đổi về event contract, listener phase, module ownership, registry persistence, externalization adapter, broker topology hoặc retry policy đều có thể làm luồng thay đổi.

Hãy cập nhật sơ đồ khi:

- Thêm hoặc bỏ producer/consumer.
- Đổi event type, schema version hoặc routing destination.
- Chuyển listener từ đồng bộ sang bất đồng bộ.
- Thay đổi transaction phase hoặc transaction manager.
- Thêm outbox, inbox, deduplication hoặc DLQ.
- Thay đổi broker, exchange, queue, topic hoặc consumer group.
- Thay đổi cách retry, resubmit hoặc replay.
- Bổ sung trust boundary hoặc thay đổi payload nhạy cảm.

Đặt sơ đồ gần phần mô tả contract hoặc use case mà nó giải thích. Ghi owner, ngày cập nhật và phiên bản event nếu cần. Tránh tạo một tài liệu sơ đồ tách rời không có liên kết tới event definition, listener hoặc test.

Sơ đồ event flow có giá trị khi người đọc nhìn thấy đúng đường đi, boundary, transaction và cách phục hồi của một event. Hãy phân biệt event nội bộ với integration message, thể hiện rõ commit và listener phase, đặt registry/outbox/broker đúng nơi chúng thực sự hoạt động, rồi bổ sung nhánh lỗi và metadata truy vết. Khi sơ đồ được kiểm chứng bằng test và cập nhật cùng contract, nó trở thành tài liệu kỹ thuật đáng tin cậy để phát triển, review và vận hành Spring Modulith application events.

