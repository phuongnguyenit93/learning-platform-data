# Đánh giá khi nào nên hợp nhất lại dịch vụ

> **Chủ đề:** Software Design · System Architecture · Microservices  
> **Nhóm kiến thức:** Chuyển đổi kiến trúc  
> **Mục tiêu:** Xác định khi nào nên hợp nhất các microservices thành một đơn vị triển khai lớn hơn hoặc một modular monolith, cách đánh giá lợi ích và rủi ro, và cách chuyển đổi an toàn mà vẫn giữ ranh giới domain, quyền sở hữu dữ liệu và khả năng phục hồi cần thiết.

## 1. Vì sao đôi khi cần hợp nhất lại dịch vụ?

Microservices thường được tách ra để các nhóm có thể phát triển, triển khai và mở rộng độc lập. Tuy nhiên, theo thời gian, ranh giới ban đầu có thể không còn phù hợp:

- Một nhóm tạo quá nhiều service nhỏ, mỗi service chỉ có vài endpoint và một ít logic.
- Các service thường xuyên gọi nhau qua mạng để hoàn thành một thao tác đơn giản.
- Một thay đổi nghiệp vụ phải sửa và phát hành cùng lúc nhiều service.
- Các service dùng chung database hoặc cùng thay đổi một tập dữ liệu, khiến quyền sở hữu mơ hồ.
- Một service không thể chạy thử nếu thiếu bốn hoặc năm service khác.
- Chi phí CI/CD, dashboards, secrets, certificates, deployment manifests và on-call tăng nhanh hơn giá trị độc lập.
- Các service có cùng owner, cùng nhịp release, cùng SLO và cùng quy mô tải.
- Đội ngũ dành nhiều thời gian điều tra lỗi mạng, version mismatch và distributed tracing hơn là phát triển nghiệp vụ.

Ví dụ một luồng tạo đơn:

~~~text
Checkout API
    |
    v
Order Validation Service
    |
    v
Order Pricing Service
    |
    v
Order Rules Service
    |
    v
Order Persistence Service
    |
    v
Order Event Service
~~~

Nếu năm service trên đều thuộc cùng một bounded context, cùng nhóm phát triển, thường xuyên deploy cùng nhau và gọi nhau trong cùng một request, việc tách chúng thành năm process có thể tạo nhiều chi phí hơn lợi ích.

Một cách tổ chức khác có thể là:

~~~text
Order Module
  ├── Validation
  ├── Pricing orchestration
  ├── Business rules
  ├── Persistence
  └── Outbox/event publishing
          |
          v
     Other bounded contexts
~~~

Order Module có thể nằm trong một modular monolith hoặc một service triển khai thống nhất, nhưng các module nội bộ vẫn giữ trách nhiệm và API rõ ràng.

**Hợp nhất lại dịch vụ là một quyết định thiết kế ranh giới và vận hành.** Nó có thể giảm giao tiếp phân tán, giảm số deployment units và giúp giao dịch nghiệp vụ đơn giản hơn. Nếu làm sai, nó có thể tạo một service quá lớn, một blast radius rộng hoặc làm mất khả năng scale và release độc lập.

## 2. Phân biệt hợp nhất deployment với hợp nhất domain

Có ít nhất ba mức thay đổi thường bị gọi chung là “merge services”:

| Mức | Thay đổi | Kết quả |
|---|---|---|
| **Hợp nhất triển khai** | Nhiều process/container được đóng gói và phát hành cùng một đơn vị | Giảm deployment/operational overhead; module có thể vẫn tách |
| **Hợp nhất runtime và giao tiếp** | Logic được chuyển vào cùng process, thay network calls bằng in-process calls | Giảm network hops và distributed failure points |
| **Hợp nhất domain/data ownership** | Gộp trách nhiệm nghiệp vụ, mô hình dữ liệu hoặc nguồn sự thật | Thay đổi bounded context, quyền sở hữu và semantics |

Ba mức này không bắt buộc xảy ra cùng lúc.

Ví dụ, hai module cùng bounded context có thể được deploy trong một container nhưng vẫn giữ package/API boundary. Một service có thể được hợp nhất runtime với service khác nhưng vẫn giữ hai schema hoặc hai module dữ liệu cho tới khi migration hoàn tất.

Ngược lại, gộp hai database vào cùng một cluster không tự động có nghĩa hai domain đã được hợp nhất. Cần phân biệt **hạ tầng vật lý**, **ranh giới logic** và **quyền sở hữu nghiệp vụ**.

## 3. Microservice, modular monolith và distributed monolith

**Microservice có ranh giới tốt** thường có domain ownership rõ, giao tiếp qua contract, dữ liệu được sở hữu và thay đổi có kiểm soát, có thể triển khai độc lập khi cần.

**Modular monolith** là một đơn vị triển khai nhưng bên trong có các module với trách nhiệm, dependency và API nội bộ rõ ràng. Nó có thể giảm chi phí mạng và triển khai mà vẫn giữ cấu trúc domain.

**Distributed monolith** là nhiều service/process nhưng phụ thuộc chặt chẽ: phải deploy đồng thời, thay đổi schema đồng thời, gọi nhau đồng bộ dày đặc và không thể hoạt động độc lập. Nó chịu cả chi phí phân tán lẫn sự phụ thuộc của monolith.

~~~text
Well-bounded microservices:
  Order  ---- contract ----> Payment
    |                         |
  own data                  own data
  deploy independently     deploy independently

Modular monolith:
  Application
    ├── Order module
    ├── Inventory module
    └── Reporting module
  Explicit module APIs and ownership

Distributed monolith:
  Service A <---- synchronous dependency ----> Service B
       ^                                         |
       +------------- lockstep release ----------+
~~~

Mục tiêu của việc hợp nhất thường là chuyển một cụm service đang hoạt động như distributed monolith sang **một runtime có module boundary tốt**, hoặc tái thiết kế thành những service có ranh giới thực sự độc lập.

Không nên mặc định modular monolith là bước lùi. Đây là một lựa chọn kiến trúc hợp lệ, đặc biệt khi quy mô đội ngũ, workload và domain chưa cần phân tán.

## 4. Những tín hiệu cho thấy nên đánh giá việc hợp nhất

### 4.1. Service quá nhỏ và ít trách nhiệm độc lập

Một service có thể chỉ:

- Chuyển tiếp request sang service khác.
- Ánh xạ một vài field mà không có logic domain riêng.
- Đọc cùng database với service gọi nó.
- Chỉ được deploy khi service cha thay đổi.
- Không có owner hoặc SLO riêng.
- Không có nhu cầu scale hay bảo mật riêng.

Một service nhỏ không tự động là sai. Điều cần đánh giá là **chi phí tạo một ranh giới mạng có tương xứng với giá trị độc lập mà ranh giới đó mang lại không**.

### 4.2. Giao tiếp nội bộ quá dày

Dấu hiệu:

- Một request cần nhiều HTTP/gRPC hops trong cùng một domain workflow.
- Các service gọi nhau tuần tự, khiến latency cộng dồn.
- Nhiều RPC chỉ để lấy dữ liệu mà cùng một transaction đã có thể truy cập.
- Retry và timeout ở nhiều tầng làm luồng khó dự đoán.
- Trace cho thấy một phần lớn thời gian nằm ở network overhead hoặc queueing giữa các service.

Ví dụ:

~~~text
A → B → C → D
~~~

Nếu A, B, C, D cùng thuộc một domain và mọi request đều đi qua đủ bốn bước, chuyển một số lời gọi thành in-process module calls có thể giảm latency và failure points.

### 4.3. Thường xuyên phải phát hành đồng bộ

Nếu một thay đổi đơn giản buộc phải:

1. Phát hành service A.
2. Chờ service B tương thích.
3. Phát hành service B.
4. Chờ service C.
5. Cập nhật config của cả ba.
6. Rollback cùng lúc khi một bước thất bại.

thì ranh giới hiện tại có thể không tạo được deployment independence như mong đợi.

Tuy nhiên, **một lần deploy phối hợp vì migration lớn** chưa đủ kết luận nên merge. Hãy xem tần suất, nguyên nhân và thời gian coupling tồn tại.

### 4.4. Dữ liệu và transaction thường xuyên bị chia cắt

Các dấu hiệu:

- Hai service cùng ghi các bảng thuộc một nghiệp vụ.
- Một thao tác cần distributed transaction hoặc saga phức tạp dù logic thực chất rất cục bộ.
- Các service liên tục đọc dữ liệu nội bộ của nhau qua API.
- Không xác định được service nào là source of truth.
- Mỗi thay đổi schema buộc nhiều team sửa đồng thời.

Nếu dữ liệu thuộc cùng một bounded context và cần atomicity thường xuyên, hợp nhất runtime hoặc quyền sở hữu có thể đơn giản hóa mô hình. Nhưng nếu dữ liệu đại diện cho hai domain độc lập, chỉ vì muốn dùng một transaction SQL không đủ lý do để gộp domain.

### 4.5. Chi phí vận hành vượt giá trị độc lập

Đo các chi phí:

- Số deployment units, pipelines, manifests và secrets.
- Số dashboards, alerts, certificates, service accounts.
- Số on-call handoffs và incident tickets do inter-service failures.
- Chi phí compute tối thiểu của các service ít tải.
- Chi phí observability và network transfer.
- Thời gian build, test, release và troubleshoot.
- Thời gian đội ngũ dành cho coordination thay vì domain work.

Một service có ít traffic vẫn có thể xứng đáng tồn tại nếu nó giữ một trust boundary hoặc failure domain quan trọng. Cost thấp không phải tiêu chí duy nhất.

## 5. Những tín hiệu cho thấy không nên hợp nhất

Có những ranh giới cần giữ dù việc vận hành nhiều service tốn thêm chi phí.

### 5.1. Khác bounded context và ngôn ngữ nghiệp vụ

Payment, Order và Inventory có những khái niệm, trạng thái và invariants khác nhau. Gộp chúng chỉ vì một màn hình cần đọc dữ liệu từ cả ba có thể làm mờ ownership và tạo một mô hình domain khổng lồ.

### 5.2. Khác yêu cầu bảo mật hoặc compliance

Một service xử lý thông tin thanh toán, dữ liệu định danh nhạy cảm hoặc tác vụ quản trị đặc quyền có thể cần:

- Quyền truy cập riêng.
- Network isolation riêng.
- Audit và retention khác.
- Quy trình release/approval khác.
- Giới hạn truy cập production riêng.

Hợp nhất có thể làm trust boundary rộng hơn và tăng blast radius khi credential hoặc process bị xâm nhập.

### 5.3. Khác SLO, tải và khả năng scale

Ví dụ Notification worker xử lý hàng triệu message nền trong khi Order API cần latency thấp. Nếu gộp cùng process và resource pool, batch workload có thể chiếm CPU, memory, connections hoặc threads của request-serving path.

### 5.4. Cần fault isolation

Một service có thể cố ý được tách để lỗi của nó không làm sập luồng khác. Nếu gộp runtime mà không có bulkhead, resource limits và failure isolation, một lỗi cục bộ có thể ảnh hưởng toàn bộ ứng dụng.

### 5.5. Khác ownership và nhịp phát triển

Hai nhóm có lịch phát hành, kỹ năng, mục tiêu và trách nhiệm khác nhau có thể cần ranh giới triển khai độc lập. Gộp codebase mà không giải quyết ownership dễ tạo tranh chấp và tăng coordination.

**Không merge chỉ vì service ít traffic.** Hãy xác định service đó đang bảo vệ một ranh giới có giá trị nào.

## 6. Decision criteria: Đánh giá theo nhiều chiều

Một quyết định hợp nhất nên xem xét ít nhất các chiều sau:

| Tiêu chí | Nghiêng về hợp nhất khi | Nghiêng về giữ riêng khi |
|---|---|---|
| Domain | Cùng bounded context, cùng invariants | Khác ngôn ngữ/nghiệp vụ |
| Cohesion | Logic thường xuyên thay đổi cùng nhau | Thay đổi độc lập |
| Coupling | Gọi đồng bộ dày, lockstep release | Contract ổn định, ít phụ thuộc |
| Data ownership | Cùng owner và cần atomicity | Mỗi service có source of truth riêng |
| Scaling | Tải và resource profile gần nhau | Một bên cần scale khác hẳn |
| Availability | Có thể cùng failure domain | Cần fault isolation riêng |
| Security | Cùng trust level | Khác dữ liệu/quyền/compliance |
| Team | Cùng team, cùng lifecycle | Khác owner, release autonomy quan trọng |
| Operations | Nhiều overhead không đem lại giá trị | Tách giúp on-call/rollout độc lập |
| Cost | Tiết kiệm đo được sau khi tính migration | Chi phí hợp nhất và coupling cao hơn |
| Latency | Network hops tạo bottleneck | Boundary network có giá trị và ít tốn kém |
| Evolution | Thường xuyên đổi cùng contract | Contract cần ổn định lâu dài |

Không dùng một tiêu chí đơn lẻ. Ví dụ cùng team và cùng database là tín hiệu, nhưng không đủ chứng minh cùng domain.

## 7. Đo cohesion và coupling trước khi quyết định

**Cohesion** phản ánh các phần trong một service/module có cùng phục vụ một mục đích nghiệp vụ hay không.

**Coupling** phản ánh mức độ một phần phụ thuộc vào thay đổi hoặc trạng thái của phần khác.

Có thể thu thập:

- Số lần service A gọi service B trên mỗi business transaction.
- Tỷ lệ request phải đi qua nhiều service cùng bounded context.
- Số lần hai service cùng được sửa trong một change set.
- Số lần phải deploy phối hợp.
- Số shared database tables hoặc cross-service writes.
- Số contract changes tạo consumer failures.
- Tỷ lệ incident có nguyên nhân từ dependency chain.
- Số service owners phải tham gia một thay đổi đơn giản.

Một biểu đồ dependency:

~~~text
Checkout
  ├── Order Validation
  ├── Pricing Rules
  ├── Tax Calculation
  ├── Order Persistence
  └── Event Publisher
~~~

Nếu mọi node luôn được thay đổi cùng nhau và không có nhu cầu scaling/security độc lập, cụm này là ứng viên đánh giá hợp nhất. Nếu Tax Calculation được nhiều domain khác sử dụng với semantics/ownership riêng, nó có thể cần giữ boundary.

**Đừng đếm số HTTP calls rồi merge theo ngưỡng cứng.** Một call cross-domain có thể là ranh giới tốt; một trăm calls giữa các module cùng domain có thể là thiết kế chưa tốt.

## 8. Dùng dữ liệu vận hành thay cho cảm giác

Trước khi quyết định, lấy baseline trong một khoảng thời gian đại diện:

- Request rate, peak và seasonality.
- p50/p95/p99 latency theo dependency.
- Số network hops và bytes per transaction.
- Retry, timeout, circuit-breaker và bulkhead rejections.
- CPU/memory/GC và connection pool usage.
- Queue lag và background workload.
- Deployment frequency và lead time.
- Change failure rate và rollback frequency.
- Incident count, MTTR và dependency-related incidents.
- Chi phí compute, network, broker, storage và observability.
- Team coordination và on-call burden.

So sánh **chi phí hiện tại** với **chi phí mục tiêu sau hợp nhất**, có tính cả:

1. Runtime tiết kiệm được.
2. Network calls và transfer giảm.
3. Pipelines/monitoring/secrets giảm.
4. Resource pooling có hiệu quả hơn hay gây contention.
5. Migration và data movement.
6. Test/release coordination.
7. Rủi ro blast radius và downtime.
8. Chi phí quay lại hoặc tách ra nếu quyết định sai.

Nếu không có baseline, không thể chứng minh hợp nhất đã cải thiện kiến trúc.

## 9. Mô hình đánh giá định lượng

Có thể chấm mỗi chiều theo thang 1–5, nhưng điểm số chỉ hỗ trợ thảo luận, không thay quyết định kỹ thuật:

| Chiều đánh giá | Điểm 1 | Điểm 5 |
|---|---|---|
| Cùng bounded context | Domain độc lập rõ | Cùng một domain/invariants |
| Thay đổi cùng nhau | Hiếm khi | Gần như luôn |
| Giao tiếp nội bộ | Ít, async/contract ổn định | Dày, synchronous, chatty |
| Data ownership | Ranh giới rõ | Shared writes/ownership mơ hồ |
| Scaling profile | Rất khác nhau | Gần như giống nhau |
| Release independence | Rất cần | Không có giá trị đáng kể |
| Security boundary | Cần cô lập | Cùng trust level |
| Operational overhead | Thấp | Cao so với giá trị nhận được |

Có thể dùng một bảng trọng số theo criticality của tổ chức, nhưng không nên cộng cơ học thành một “merge score” rồi tự động hợp nhất. Một điều kiện hard-stop như **khác trust boundary** hoặc **cần fault isolation** có thể quan trọng hơn tổng điểm.

Một mẫu decision record:

~~~text
Candidate services:
  order-validation
  order-pricing
  order-persistence

Evidence:
  Same bounded context: yes
  Shared owner: yes
  Lockstep releases: frequent
  Internal synchronous calls: high
  Independent scaling: no
  Separate security boundary: no

Potential benefits:
  fewer network hops
  simpler transaction handling
  fewer deployment units

Risks:
  larger process blast radius
  shared resource contention
  larger build/test scope

Decision:
  consolidate runtime into order-api
  preserve module interfaces and data ownership rules
  keep payment as independent domain service

Review after:
  two release cycles and one peak-load test
~~~

Các giá trị là minh họa. Quyết định thật phải kèm trace, deployment history, cost data và owner.

## 10. Phân biệt service boundary với code module boundary

Khi hợp nhất runtime, vẫn nên giữ module boundary:

~~~text
order-api/
  order-domain/
    model/
    application/
    ports/
  pricing-module/
    api/
    model/
    application/
  persistence-adapter/
  event-publishing/
~~~

Các nguyên tắc:

- Module chỉ truy cập dữ liệu module khác qua interface được công bố.
- Không truy cập repository/private tables xuyên module tùy tiện.
- Domain types không bị chia sẻ toàn cục thành một model khổng lồ.
- Dependency direction rõ: application/domain không phụ thuộc infrastructure cụ thể.
- Không circular dependencies.
- Có module-level tests và contract tests nội bộ.
- Package/module ownership được phân công rõ.
- Việc tách lại thành service sau này có thể dựa vào interface đã có.

**Hợp nhất process không phải giấy phép bỏ encapsulation.** Nếu mọi module cùng sửa mọi bảng và gọi mọi class, modular monolith sẽ nhanh chóng trở thành big ball of mud.

## 11. Chọn mục tiêu: Modular monolith hay một service lớn hơn?

### Modular monolith

Phù hợp khi:

- Nhiều capability cùng bounded context.
- Một team hoặc nhóm phối hợp chặt chẽ sở hữu.
- Cần transaction nội bộ thường xuyên.
- Tải chưa đòi hỏi scale độc lập.
- Một release unit là chấp nhận được.
- Muốn giảm distributed operations nhưng vẫn giữ module boundaries.

### Consolidated service

Phù hợp khi:

- Vẫn cần service boundary và network API với các domain khác.
- Một số service nhỏ cùng một domain có thể thành một process/deployment.
- Muốn giữ API/service identity ở cấp domain nhưng giảm số process.
- Có nhu cầu triển khai độc lập với các domain khác.

### Giữ microservices riêng

Phù hợp khi:

- Có bounded context và ownership độc lập.
- Scaling profiles khác nhau rõ.
- Security/compliance/fault isolation yêu cầu tách.
- Contract ổn định, ít lockstep changes.
- Team có năng lực vận hành độc lập và lợi ích đã được chứng minh.

Có thể có cấu trúc lai: một modular monolith cho Order domain, một Payment service riêng, một Inventory service riêng và Notification workers bất đồng bộ.

## 12. Chi phí cần tính khi hợp nhất

Hợp nhất có thể giảm:

- Số Pod tối thiểu và tài nguyên idle.
- Load balancers, service discovery records và certificates.
- Network transfer và proxy hops.
- Số pipelines, manifests, secrets.
- Broker messages dùng chỉ để giao tiếp nội bộ không cần thiết.
- Logs/traces và operational overhead của service-to-service calls.
- Coordination và release management.

Nhưng có thể tăng:

- CPU/RAM do process lớn hơn.
- Build time và test scope.
- Shared runtime contention.
- Blast radius khi memory leak hoặc process crash.
- Rollout duration và risk.
- Khó scale một module nặng độc lập.
- Khó tách quyền truy cập nội bộ.
- Chi phí tổ chức nếu team ownership không được thiết kế lại.

Mô hình:

~~~text
Net value of consolidation
  = avoidable infrastructure cost
  + avoidable operational cost
  + value of simpler transactions/latency
  - migration cost
  - additional shared-runtime cost
  - added failure/blast-radius risk
  - lost independent scaling/release value
~~~

Không nên chỉ so tổng số Pod trước và sau. Một service gộp cần 8 CPU/16 GB và phải scale theo peak của một module có thể đắt hơn ba service nhỏ có resource profiles khác nhau.

## 13. Transaction boundary là một lý do mạnh, nhưng không phải lý do duy nhất

Giả sử Order Validation, Pricing và Persistence đều thuộc một transaction nghiệp vụ:

~~~text
BEGIN
  validate order
  calculate final amount
  reserve order record
COMMIT
~~~

Nếu chúng nằm trong các process khác nhau, có thể phải dùng saga hoặc nhiều bước ghi bù dù tất cả đều thuộc một domain và không có nhu cầu độc lập.

Đưa chúng về cùng runtime có thể:

- Dùng một transaction database phù hợp.
- Giảm network timeouts giữa các bước.
- Đơn giản hóa rollback và exception handling.
- Giảm trạng thái trung gian và reconciliation nội bộ.

Nhưng **không nên gộp Payment vào Order chỉ để có một database transaction** nếu Payment có ledger, provider side effects và yêu cầu audit độc lập. Giao dịch với external provider vẫn không thể được bảo đảm atomic chỉ bằng local DB transaction.

Cần phân biệt:

- Transaction nội bộ trong một bounded context.
- Transaction phân tán giữa nhiều bounded contexts.
- External side effects như charge, email, shipment.
- Eventual consistency có chủ đích.

Hợp nhất giúp đơn giản transaction khi ranh giới cũ chia cắt một nghiệp vụ thực sự thuộc cùng owner; nó không loại bỏ nhu cầu saga ở ranh giới domain thực.

## 14. Data ownership và database sau khi hợp nhất

Có ba lựa chọn thường gặp:

1. **Giữ schema/tables tách theo module:** ít migration rủi ro hơn, dễ nhận diện ownership, có thể dùng chung DB engine/cluster.
2. **Gộp schema và model dữ liệu:** phù hợp nếu domain thực sự thống nhất, nhưng cần migration và quyền sở hữu mới.
3. **Cùng runtime, vẫn giữ database riêng:** giảm network giữa một số logic nhưng giữ persistence/failure boundaries riêng; có thể vẫn cần network tới DB.

~~~text
Consolidated application
  ├── Order module ----> order schema
  ├── Pricing module --> pricing schema
  └── Rules module ----> rules schema
~~~

Dù dùng chung một database instance, nên giữ:

- Table/schema ownership.
- Migration ownership.
- Access policies.
- Naming conventions.
- Data retention và classification.
- Query boundaries.
- Audit semantics.

Không cho module A tự join/update tables của module B chỉ vì cùng process. Nếu một module cần dữ liệu khác, dùng module API hoặc query/read model được công bố.

## 15. API và event contracts sau khi hợp nhất

Khi hai service trở thành một process, các internal HTTP APIs có thể được thay bằng module interfaces. Tuy nhiên, những contracts được external consumers sử dụng phải được giữ ổn định hoặc có migration rõ.

~~~text
Before:
  Checkout → Pricing HTTP API → Pricing DB

After:
  Checkout application
      |
      v
  Pricing module interface
      |
      v
  Pricing repository
~~~

Các điều kiện:

- Xác định API nào public, internal và deprecated.
- Giữ behavior của external API trong giai đoạn chuyển tiếp.
- Chuyển consumer nội bộ theo từng bước.
- Không xóa event contracts nếu consumers bên ngoài vẫn cần.
- Giữ event IDs, ordering và idempotency semantics.
- Không phát cùng một event từ cả service cũ và module mới nếu chưa có dedup/ownership rõ.
- Version schema và data transformations theo contract.
- Cập nhật service catalog, dependency graph và runbooks.

**Giảm một network hop không có nghĩa bỏ contract.** Module boundary vẫn cần một interface có semantics và test.

## 16. Quyền sở hữu và tổ chức đội ngũ

Một cụm service cùng thuộc một team thường dễ hợp nhất hơn nếu lifecycle cũng trùng nhau. Nhưng cấu trúc team không phải bằng chứng duy nhất về bounded context.

Trước khi merge, làm rõ:

- Ai sở hữu code/module sau hợp nhất?
- Ai review thay đổi từng module?
- Ai on-call cho lỗi runtime chung?
- Ai phê duyệt schema và migration?
- Ai có quyền truy cập production data?
- Một team có thể phát hành phần module khác mà không cần review không?
- Có thể phân chia code ownership và CODEOWNERS theo module không?
- Khi một module cần scale riêng, ai quyết định tách lại?

Nếu hai team có trách nhiệm nghiệp vụ khác nhau, cần thống nhất ownership trước khi gom deployment. Nếu không, một runtime lớn sẽ trở thành điểm tranh chấp chung.

## 17. Scaling: Hợp nhất có thể làm tăng chi phí

Giả sử:

- Pricing module cần 1 CPU.
- Reporting module cần 8 CPU.
- Cả hai chạy riêng, Pricing có thể giữ 2 replicas và Reporting scale theo batch.
- Sau hợp nhất, mọi replica đều chứa cả hai module.

Nếu Reporting cần 10 replicas vào giờ cao điểm, có thể phải chạy 10 bản Pricing dù Pricing không cần scale. Nếu batch workload dùng nhiều memory, Order API có thể chịu GC pressure.

Giải pháp nếu vẫn muốn hợp nhất:

- Tách worker workload khỏi request-serving process.
- Dùng resource pools/bulkheads và bounded concurrency.
- Không chạy batch nặng trên cùng executor với request path.
- Dùng feature flags hoặc deployment profiles có kiểm soát nếu module không cần chạy ở mọi replica.
- Theo dõi cost per request và saturation sau merge.
- Giữ khả năng tách runtime nếu scaling divergence tăng.

**Scaling independence là một giá trị kiến trúc thật.** Đừng loại bỏ nó nếu tiết kiệm service count nhưng phải nhân tài nguyên cho mọi module theo peak của module nặng nhất.

## 18. Fault isolation và blast radius

Khi nhiều service được gộp vào cùng process:

- Một crash có thể làm tất cả module ngừng phục vụ.
- Memory leak trong một module có thể ảnh hưởng toàn process.
- Deadlock hoặc thread starvation có thể chặn nhiều endpoint.
- Một deploy lỗi có thể tác động toàn bộ capability.
- Một credential bị lộ có thể truy cập rộng hơn nếu quyền không được tách.

Có thể giảm rủi ro bằng:

- Bounded thread/connection pools.
- Bulkheads cho workload nặng.
- Timeouts và cancellation.
- Resource limits/quotas.
- Separate worker deployments cho jobs dài.
- Feature flags/canary và rollback.
- Process-level isolation cho module có risk khác biệt.
- Least privilege ở DB/schema/secret và API boundaries.

Tuy nhiên, bulkhead trong cùng process không tương đương hoàn toàn process isolation. Nếu một module có yêu cầu fault containment mạnh, giữ nó ở service riêng có thể hợp lý.

## 19. Security boundary khi hợp nhất

Trước khi merge, xem xét:

- Có dữ liệu nhạy cảm chỉ một service được phép truy cập?
- Có workload identity riêng với scope nhỏ?
- Có network policy hoặc egress restriction riêng?
- Có audit trail theo actor/domain không?
- Có secrets/certificates riêng cần giữ?
- Có yêu cầu data residency hoặc compliance khác nhau?
- Có một module được phép thao tác admin mà module khác không?
- Có thể giữ authorization checks ở module boundary?

Một process chung có thể làm tăng quyền mặc định của mọi code trong process nếu tất cả dùng chung credentials. Có thể dùng DB roles/schema permissions và service-level policy, nhưng không phải mọi ngôn ngữ/runtime đều cung cấp sandbox mạnh giữa các module.

**Nếu hợp nhất làm giảm khả năng tách quyền hoặc audit, chi phí đó phải được coi là rủi ro kiến trúc.**

## 20. Latency và network: Lợi ích cần đo

Giả sử một request hiện đi qua ba service tuần tự:

~~~text
A → B: 25 ms
B → C: 30 ms
C → D: 20 ms
Processing: 40 ms
Total: khoảng 115 ms chưa tính queue/retry
~~~

Nếu B, C và D cùng domain và được chuyển vào một process, có thể giảm network hops và connection management. Tuy nhiên, tổng thời gian vẫn phụ thuộc database queries, locks, CPU và thuật toán.

Không lấy tổng p95 của từng hop để suy ra p95 end-to-end bằng phép cộng đơn giản nếu các phân phối và tương quan khác nhau. Dùng distributed traces để xác định critical path.

Sau merge, đo:

- p50/p95/p99 end-to-end.
- CPU time và DB time.
- Network calls/bytes.
- GC pauses và thread contention.
- Lock wait và connection pool saturation.
- Error rate và rollback frequency.

Nếu latency không cải thiện đáng kể, lý do merge có thể nằm ở giảm operational cost hoặc đơn giản hóa ownership. Ghi nhận đúng mục tiêu thay vì tuyên bố performance đã tốt hơn khi chưa có bằng chứng.

## 21. Migration strategy: Hợp nhất theo từng bước

Không cần chuyển mọi service trong một lần. Một lộ trình:

1. **Baseline:** đo dependency, traffic, deploy history, cost và SLO.
2. **Target boundary:** xác định modules, public contracts, data ownership và failure boundaries.
3. **Create target module:** đưa code vào module mới nhưng chưa thay traffic.
4. **Characterization tests:** ghi nhận behavior hiện tại, gồm lỗi và edge cases.
5. **Compatibility adapter:** giữ API hiện tại trong lúc chuyển consumers.
6. **Data plan:** giữ schema, migrate hoặc consolidate có checkpoint.
7. **Shadow validation:** chạy logic mới trên input đại diện và so output, không phát side effects.
8. **Canary routing:** chuyển một phần traffic hoặc một nhóm use cases.
9. **Expand:** chuyển dần consumers, workers và scheduled jobs.
10. **Decommission:** dừng service cũ sau khi chứng minh không còn traffic/dependency.
11. **Observe:** đo SLO, cost, incidents và resource contention sau merge.
12. **Review:** quyết định giữ cấu trúc, điều chỉnh module hoặc tách lại nếu evidence cho thấy cần.

Cần chọn bước chuyển có thể rollback và không tạo hai nơi cùng có quyền ghi source of truth.

## 22. Strangler pattern khi đưa logic về service hợp nhất

Có thể dùng façade/router để chuyển từng capability:

~~~text
External API
     |
     v
Compatibility Facade
     |
     +---- old route ----> Legacy Service
     |
     +---- new route ----> Consolidated Module
~~~

Theo thời gian, traffic chuyển sang module mới. Facade giữ contract bên ngoài trong giai đoạn migration.

Cần lưu ý:

- Routing phải ổn định theo request/tenant/operation, không chia ngẫu nhiên khi consistency cần.
- Không cho hai implementation cùng ghi cùng source of truth.
- Có correlation ID để đối chiếu.
- Shadow mode không được gọi external side effects.
- Rollback route phải hiểu dữ liệu đã được ghi bởi phiên bản nào.
- Giữ compatibility đủ lâu cho consumers cũ.
- Xóa facade chỉ sau khi usage telemetry xác nhận không còn consumers.

## 23. Data migration: Tránh dual-write không kiểm soát

Nếu hợp nhất database/schema, rủi ro lớn nhất thường là dữ liệu thay đổi trong khi chuyển.

Một quy trình an toàn có thể là:

~~~text
Old source of truth
       |
       | snapshot + CDC/change log
       v
New target schema
       |
       v
Backfill historical data
       |
       v
Catch up incremental changes
       |
       v
Compare counts, keys, sums, invariants
       |
       v
Controlled write cutover
       |
       v
Verify and retire old writer
~~~

Các nguyên tắc:

- Có stable keys, mapping và version.
- Backfill có checkpoint, retry và idempotency.
- So sánh count, aggregate totals, keyed records và business invariants.
- Chốt write authority tại một thời điểm rõ.
- Có cách xử lý events/transactions đến trong cutover window.
- Có backup và rollback/compensation plan.
- Không giữ hai nguồn ghi song song vô hạn.

**Dual-write** tới hai database độc lập dễ tạo trạng thái một bên thành công, bên kia thất bại. Nếu cần dual-write trong thời gian chuyển, phải có outbox/change log, retry, reconciliation và cơ chế chọn nguồn có thẩm quyền.

## 24. Event migration và consumer safety

Khi hai service cũ phát event, sau merge có thể một module mới đảm nhiệm publish. Cần tránh:

- Event bị phát hai lần từ cả old và new service.
- Event mất do outbox chưa được chuyển.
- Thứ tự event thay đổi theo partition key.
- Consumer không đọc được schema mới.
- Replay từ offset cũ tạo side effects trùng.
- Trace/correlation context bị mất.

Một kế hoạch:

1. Chỉ định publisher authority theo từng event type.
2. Giữ eventId và aggregateId semantics.
3. Dùng outbox của target runtime hoặc cơ chế delivery đã kiểm chứng.
4. Chuyển consumer contract độc lập với internal module calls.
5. Theo dõi old/new publisher metrics.
6. Có cutover watermark và reconciliation.
7. Chỉ tắt publisher cũ sau khi xác nhận target đã phát đủ event.
8. Kiểm tra consumer lag và DLQ sau chuyển đổi.

Không xóa topic hoặc giảm retention trước khi xác nhận consumers và DR/replay requirements.

## 25. Compatibility và versioning trong giai đoạn chuyển

External consumers có thể vẫn gọi endpoint cũ sau khi logic được chuyển vào module mới. Hãy giữ facade/adapters tương thích:

- Giữ method/path và response shape.
- Giữ error code/status behavior.
- Giữ authorization/audience và tenant semantics.
- Giữ idempotency keys và retry behavior.
- Giữ pagination/order guarantees.
- Giữ event schema và delivery semantics.
- Có deprecation schedule cho endpoint không còn cần.
- Track consumer versions và actual traffic.

Internal APIs có thể dần trở thành module interfaces, nhưng **consumer-facing contracts** chỉ nên thay đổi theo policy versioning và migration.

## 26. Test strategy cho hợp nhất

Cần kiểm tra nhiều cấp:

### Unit/module tests

- Domain invariants và state transitions.
- Module interfaces và dependency direction.
- Data access ownership.
- Validation và error mapping.

### Contract tests

- External APIs vẫn tương thích.
- Events có schema/semantics đúng.
- Consumers hiện hành vẫn hoạt động.
- Idempotency và retry behavior giữ nguyên.

### Integration tests

- Database transactions và migrations.
- Outbox/consumer flow.
- Authentication/authorization.
- Cấu hình, secrets và external adapters.

### Performance/load tests

- Peak traffic và burst.
- Resource contention giữa modules.
- DB connection pool và thread pool.
- GC/heap và startup time.
- Latency so với baseline.
- Scale-up/scale-down behavior.

### Resilience tests

- Database/network timeout.
- Broker outage và backlog.
- Một module nặng hoặc lỗi.
- Process restart và deployment rollback.
- Dependency unavailable.
- Failover/restore nếu phạm vi bị ảnh hưởng.

**Test không chỉ chứng minh app mới chạy.** Nó phải chứng minh các behavior và SLO quan trọng vẫn đạt sau khi ranh giới runtime thay đổi.

## 27. Rollout và rollback

Một rollout có kiểm soát:

~~~text
Build target application
       |
       v
Deploy dark / no production traffic
       |
       v
Smoke + contract + integration tests
       |
       v
Shadow traffic (read-only / side-effect disabled)
       |
       v
Canary small traffic slice
       |
       v
Compare SLO and business outcomes
       |
       +---- bad --> route back / rollback
       |
       +---- good --> gradually expand
                       |
                       v
                  full cutover
                       |
                       v
                  decommission old units
~~~

Rollback cần trả lời:

- Database đã được migrate hoặc ghi bằng schema mới chưa?
- Phiên bản cũ còn đọc được dữ liệu mới không?
- Events đã phát ra có consumer cũ hiểu không?
- Có side effects bên ngoài đã xảy ra không?
- Có thể route lại traffic mà không duplicate writes?
- Cần forward-fix hoặc compensating transaction thay vì restore DB không?

Một deployment rollback không tự đảo ngược data migration. **Rollback code và rollback dữ liệu là hai kế hoạch khác nhau.**

## 28. Các dấu hiệu hợp nhất thành công

Sau khi merge, kiểm tra:

- Network hops và internal RPC calls giảm như dự kiến.
- p95/p99 latency có cải thiện hoặc ít nhất không xấu đi ngoài SLO.
- Deployment units/pipelines/secrets/alerts giảm thực chất.
- Team release coordination đơn giản hơn.
- Data ownership và module APIs rõ hơn.
- Không tăng incident do process chung hoặc resource contention.
- Module tests và contract tests vẫn dễ chạy.
- Một module có thể thay đổi mà không sửa mọi module khác.
- Chi phí compute/network/observability giảm hoặc có lợi ích rõ.
- Rollback và recovery vẫn khả thi.
- Không có consumer hoặc job cũ âm thầm gọi service đã decommission.

Không đánh giá thành công chỉ bằng việc số service giảm từ 8 xuống 3. Số service là một chỉ số cấu trúc, không phải business outcome.

## 29. Ví dụ: Hợp nhất các service nhỏ trong Order domain

Giả sử có bốn service:

| Service | Trách nhiệm hiện tại | Quan sát |
|---|---|---|
| Order Validation | Kiểm tra input và trạng thái | Chỉ dùng trong Order |
| Order Pricing Adapter | Điều phối tính giá | Gọi Pricing Rules qua mạng |
| Order Persistence | Ghi Order DB | Chỉ phục vụ Order |
| Order Event Publisher | Đọc outbox và phát event | Cùng owner/lifecycle |

Chúng có cùng team, cùng deploy cadence, cùng SLO và thường xuyên thay đổi cùng nhau. Luồng checkout gọi tuần tự qua các service này.

Một quyết định có thể là hợp nhất thành **Order API** với các module:

~~~text
Order API
  ├── Validation module
  ├── Pricing orchestration module
  ├── Order repository module
  └── Outbox publisher module
~~~

Lợi ích dự kiến:

- Bớt network hops trong cùng domain.
- Có thể dùng local transaction cho order state + outbox.
- Ít deployment units và secrets.
- Dễ chạy integration tests.
- Một nhóm chịu trách nhiệm end-to-end.

Điều kiện giữ:

- Pricing Rules có thể vẫn là domain service riêng nếu nhiều domain khác sử dụng.
- Payment vẫn độc lập vì ledger/provider side effects và security boundary.
- Outbox publisher vẫn có worker/process riêng nếu tải nền cần scale khác.
- Module APIs và table ownership vẫn rõ.
- Không gộp mọi schema thành một bảng chung.

## 30. Ví dụ: Không nên hợp nhất Payment và Order chỉ vì cùng một màn hình

Checkout cần biết trạng thái Payment để hiển thị đơn hàng. Điều đó không có nghĩa Order và Payment cùng domain.

Payment có thể cần:

- Ledger append-only.
- Reconciliation với provider.
- PCI/security controls tùy phạm vi xử lý.
- Quyền và audit riêng.
- Idempotency cho charge/refund.
- SLO và incident response khác.
- Tích hợp nhiều payment providers.
- Independent release cho compliance/security patches.

Order có thể sở hữu lifecycle đơn hàng và giữ một **projection/reference** của trạng thái thanh toán. Hai service giao tiếp qua contract/event phù hợp.

Hợp nhất chỉ để tránh một HTTP call có thể làm mất boundary bảo vệ tiền và tăng blast radius. Có thể cải thiện latency bằng read model hoặc API composition mà vẫn giữ Payment độc lập.

## 31. Ví dụ: Hợp nhất service nhưng giữ worker riêng

Giả sử Order Validation và Order Calculation cùng được hợp nhất vào Order API, nhưng PDF generation chạy nhiều CPU và mất vài giây.

~~~text
Order Application
   |
   +--> Synchronous request modules
   |
   +--> Durable job queue
             |
             v
        PDF Worker Deployment
          - separate concurrency
          - CPU optimized
          - bounded queue
~~~

Cùng domain không bắt buộc cùng process. Workload có resource profile khác nhau có thể giữ deployment riêng, trong khi code/domain modules vẫn nằm trong cùng repository hoặc cùng bounded context.

**Ranh giới runtime nên phản ánh nhu cầu scaling và fault isolation**, không chỉ ranh giới source code.

## 32. Rủi ro khi tạo một service quá lớn

Sau hợp nhất, cần theo dõi:

- Build/test time tăng.
- Startup và readiness chậm.
- Heap/GC pressure tăng.
- Một lỗi làm nhiều capability ngừng.
- Resource pools dùng chung và starvation.
- Deploy cần nhiều nhóm phối hợp.
- Security permissions rộng.
- Code ownership không rõ.
- Module dependency bị phá vỡ.
- Scaling toàn bộ app theo workload lớn nhất.
- Rollback phức tạp vì nhiều schema và consumers.

Nếu các dấu hiệu này xuất hiện, có thể cần tách một phần trở lại. Mục tiêu không phải giảm service count bằng mọi giá; mục tiêu là có ranh giới phù hợp với domain, team, scaling và failure model.

## 33. Khi nào nên tách lại sau khi đã hợp nhất?

Quyết định hợp nhất có thể đúng ở thời điểm hiện tại và không còn đúng khi hệ thống phát triển.

Nên đánh giá tách lại khi:

- Một module cần scale độc lập rõ rệt.
- Một module có SLO hoặc availability requirement khác.
- Một team/domain cần release cadence riêng.
- Security/compliance yêu cầu trust boundary riêng.
- Module có dependency graph đủ độc lập và contract ổn định.
- Shared runtime gây contention hoặc blast radius không chấp nhận được.
- Module cần ngôn ngữ/runtime/platform khác vì lý do kỹ thuật có bằng chứng.

Quy trình tách lại tương tự migration ngược: xác định module boundary, tạo API/event contract, chuyển data ownership, instrument, canary và decommission code nội bộ cũ.

**Đừng coi việc tách lại là thất bại.** Kiến trúc nên thay đổi khi workload, team và yêu cầu nghiệp vụ thay đổi.

## 34. Architecture Decision Record mẫu

~~~text
Title:
  Consolidate order-validation and order-persistence

Status:
  Proposed / Accepted / Superseded

Context:
  Current deployment units, dependencies, incidents and cost.
  Business capability and bounded context.

Evidence:
  Calls per transaction
  p95/p99 latency
  Co-change and lockstep deploy frequency
  Shared data/transaction needs
  Scaling and resource profiles
  Security/failure boundaries
  Current and forecast costs

Options:
  A. Keep services independent
  B. Consolidate runtime, preserve modules
  C. Modular monolith
  D. Redesign contracts without consolidation

Decision:
  Selected option and rationale.

Consequences:
  Expected savings and benefits
  Lost independence and new risks
  Ownership and SLO changes

Migration:
  Steps, data plan, compatibility, canary, rollback

Guardrails:
  Performance, security, availability and cost limits

Review:
  Date or trigger after peak-load / release cycles
~~~

ADR phải ghi bằng chứng và trade-offs thực tế, không chỉ “đội ngũ thấy đơn giản hơn”.

## 35. Những anti-pattern cần tránh

**1. Merge vì muốn giảm số service.** Service count thấp hơn không tự động làm kiến trúc tốt hơn.

**2. Merge theo team ownership mà bỏ qua bounded contexts.** Một team có thể sở hữu nhiều domain cần tách.

**3. Gộp Payment vào Order để tránh network call.** Có thể phá ledger ownership, audit và security boundary.

**4. Hợp nhất mọi module vào một process nhưng dùng chung mọi thread/connection pool.** Một workload nặng có thể làm đói các request khác.

**5. Gộp deployment rồi bỏ module boundaries.** Code nhanh chóng thành một khối khó thay đổi.

**6. Hợp nhất database trước khi xác định source of truth.** Có thể tạo duplicate writes và semantics mâu thuẫn.

**7. Dual-write vô thời hạn.** Một phía thành công, phía kia thất bại và không có cơ chế reconcile rõ.

**8. Chuyển traffic toàn bộ trong một lần.** Khó xác định lỗi và rollback.

**9. Chạy shadow traffic có side effects.** Có thể tạo charge, email hoặc shipment trùng.

**10. Decommission service trước khi kiểm tra consumers.** Một job hoặc client cũ có thể âm thầm phụ thuộc.

**11. Bỏ contract tests sau khi chuyển sang in-process calls.** Module boundary vẫn cần kiểm chứng.

**12. Chỉ benchmark happy path.** Không thấy queueing, GC, DB locks và peak traffic.

**13. Bỏ qua resource profile khác nhau.** Một module batch có thể kéo cả API phải scale.

**14. Giữ secrets và permissions rộng hơn sau merge.** Tăng blast radius của credential.

**15. Rollback code nhưng quên data migration.** Version cũ có thể không đọc được schema mới.

**16. Coi shared database là bằng chứng domain đã hợp nhất.** Physical co-location không xác định ownership.

**17. Đưa mọi module vào một repository rồi gọi đó là modular monolith.** Monolith cần dependency rules và boundaries thực.

**18. Không có owner sau merge.** Incident và migration bị đẩy qua lại giữa các nhóm.

## 36. Checklist quyết định có nên hợp nhất không

1. Các service có thuộc cùng bounded context và cùng business invariants không?
2. Có một owner chịu trách nhiệm end-to-end không?
3. Các service thường xuyên thay đổi và release cùng nhau đến mức nào?
4. Có nhiều synchronous network calls không cần thiết giữa chúng?
5. Có transaction nội bộ thường xuyên bị chia cắt?
6. Có shared writes hoặc source of truth mơ hồ?
7. Các workload có cùng scaling profile và resource needs?
8. Có cần security, compliance hoặc fault isolation riêng?
9. Team có thực sự cần release/deploy independence?
10. Chi phí compute/network/broker/observability hiện tại đã đo?
11. Chi phí migration, test và vận hành sau merge đã ước lượng?
12. Module boundaries sau hợp nhất có thể giữ rõ?
13. API/event contracts bên ngoài có được bảo toàn?
14. Data migration có checkpoint, idempotency, reconciliation và rollback?
15. Có kế hoạch không tạo hai nơi cùng phát side effects?
16. Có test peak load, dependency failure và resource contention?
17. Có canary và traffic rollback?
18. Có owner/approver cho thay đổi dữ liệu và security?
19. Có tiêu chí thành công và thời điểm review sau merge?
20. Có khả năng tách lại nếu scaling, team hoặc security requirements thay đổi?

## 37. Checklist sau khi hợp nhất

- [ ] Module boundaries và dependency rules được enforce.
- [ ] Không còn internal traffic gọi nhầm service cũ.
- [ ] External API/event contracts vẫn tương thích.
- [ ] Database/table ownership rõ và không có cross-module writes trái policy.
- [ ] Outbox, event delivery và idempotency được xác nhận.
- [ ] Secrets, workload identity và authorization vẫn least privilege.
- [ ] p95/p99, throughput và error rates trong SLO.
- [ ] CPU, memory, GC, threads và DB connections không bão hòa.
- [ ] Batch/background workloads không ảnh hưởng request path.
- [ ] Deployment, canary và rollback được thử.
- [ ] Dashboards, alerts, service catalog và runbooks cập nhật.
- [ ] Owners và on-call rotations đã nhận trách nhiệm.
- [ ] Old services không còn traffic và có thể decommission an toàn.
- [ ] Cost before/after được đối chiếu với baseline.
- [ ] ADR có review trigger và lessons learned.

## 38. Câu hỏi tự kiểm tra

**Tình huống:** Một hệ thống có bốn service nhỏ trong Order domain. Mỗi checkout gọi cả bốn service tuần tự. Chúng có cùng owner, cùng database cluster, thường xuyên release cùng nhau và không cần scale độc lập. Payment Service lại có ledger, external provider integrations và audit riêng.

Hãy trả lời:

1. Bốn service Order có nên trở thành một modular monolith hoặc một deployment unit không? Bằng chứng nào cần thu thập?
2. Module boundary nào cần giữ để tránh shared code/data coupling?
3. Payment có nên được hợp nhất chỉ để giảm một network hop? Vì sao?
4. Nếu chuyển Order data sang schema mới, làm sao giữ một write authority và tránh dual-write?
5. Contract/API nào phải tiếp tục tương thích với clients hiện tại?
6. Cần test gì để chứng minh latency, cost và fault isolation sau merge?
7. Điều kiện nào sẽ khiến team quyết định tách một module trở lại?

Một câu trả lời tốt phải chỉ rõ **domain ownership, operational evidence, failure/security boundaries, data migration và rollback**, không chỉ dựa trên số lượng service.

## 39. Kết luận

**Hợp nhất lại dịch vụ là lựa chọn hợp lý khi ranh giới phân tán hiện tại tạo nhiều chi phí hơn giá trị độc lập mà nó mang lại.** Các tín hiệu mạnh thường là cùng bounded context, thay đổi cùng nhau, giao tiếp nội bộ dày, transaction bị chia cắt và không có nhu cầu scale/security/release độc lập.

Một quyết định bền vững cần:

- **Bằng chứng:** traces, deployment history, data ownership, cost và workload measurements.
- **Ranh giới đúng:** giữ module APIs, domain semantics và security boundaries có giá trị.
- **Migration an toàn:** compatibility, checkpoint, idempotency, reconciliation, canary và rollback.
- **Kiểm chứng:** SLO, performance, resilience, cost và developer workflow sau hợp nhất.
- **Khả năng thay đổi:** theo dõi tín hiệu để tách lại khi nhu cầu độc lập xuất hiện.

**Câu hỏi cốt lõi:** *Nếu hai service thường xuyên thay đổi cùng nhau, gọi nhau trong mọi request và không cần scale độc lập, việc giữ chúng ở hai process còn đem lại lợi ích nào có thể đo được; và nếu gộp, ranh giới dữ liệu, quyền truy cập, fault isolation và khả năng tách lại được bảo vệ ra sao?*

Một kiến trúc tốt không tối đa hóa số microservices. Nó chọn **ranh giới phù hợp với domain, team, workload và failure model ở thời điểm hiện tại**, đồng thời giữ khả năng điều chỉnh khi các điều kiện đó thay đổi.
