# Tách mô tả và thực thi

## 1. Tách mô tả và thực thi là gì?

Tách mô tả và thực thi (separation of description and execution) là mẫu thiết kế trong đó DSL mô tả ý định, cấu trúc hoặc quy tắc cần thực hiện, còn một thành phần riêng chịu trách nhiệm diễn giải mô tả đó và thực thi hành vi tương ứng.

Phần mô tả thường được viết bằng DSL và biểu diễn các khái niệm ở mức miền. Phần thực thi có thể là interpreter, compiler, query engine, workflow engine hoặc adapter kết nối tới hệ thống bên ngoài.

Ví dụ, một workflow DSL có thể khai báo:

~~~text
workflow approveOrder {
    step validate {
        call orderService.validate(orderId)
    }

    step reserve {
        call inventory.reserve(orderId)
    }

    step confirm {
        call orderService.confirm(orderId)
    }
}
~~~

Source mô tả các bước nghiệp vụ và quan hệ giữa chúng. Workflow engine quyết định cách schedule step, lưu trạng thái, retry, xử lý timeout và gọi service. Người viết workflow không cần tự quản lý thread, queue hoặc network connection trong từng dòng DSL.

Tách biệt này cho phép cùng một mô tả được kiểm tra, tối ưu, mô phỏng, chạy trên nhiều runtime hoặc chuyển sang backend khác. Nó cũng tạo ra một hợp đồng rõ ràng giữa tác giả DSL và execution engine.

## 2. Vì sao nên tách mô tả khỏi thực thi?

Nếu DSL trộn cú pháp nghiệp vụ với chi tiết thực thi, source dễ phụ thuộc vào framework, database, thread model hoặc API cụ thể. Khi hạ tầng thay đổi, người dùng có thể phải sửa nhiều chương trình dù ý định nghiệp vụ không đổi.

Tách mô tả và thực thi giúp:

1. Giữ source tập trung vào ý định và quy tắc của miền.
2. Thay đổi backend mà không phải viết lại toàn bộ DSL.
3. Kiểm tra cú pháp, kiểu và policy trước khi thực thi.
4. Tạo nhiều execution mode từ cùng một mô tả.
5. Tối ưu plan mà không thay đổi source.
6. Dễ mô phỏng và test bằng fake executor.
7. Tách quyền authoring khỏi quyền thực thi.
8. Lưu và version hóa định nghĩa một cách độc lập.
9. Hỗ trợ audit, explain và visualization.
10. Tạo ranh giới rõ giữa language model và infrastructure.

Ví dụ, cùng một query DSL có thể được thực thi bằng SQL database trong production, in-memory engine trong test và mock repository trong unit test. Source mô tả dữ liệu cần lấy; executor quyết định cách truy cập dữ liệu.

## 3. Mô tả, mô hình trung gian và executor

Một kiến trúc điển hình có ba phần:

1. **Description:** DSL source hoặc cấu hình khai báo.
2. **Model:** AST, typed AST, IR hoặc execution plan biểu diễn mô tả theo cấu trúc.
3. **Execution:** engine hoặc adapter thực hiện model trên môi trường đích.

~~~mermaid
flowchart TD
    A["DSL source"] --> B["Parser"]
    B --> C["AST"]
    C --> D["Semantic analysis"]
    D --> E["Typed model / IR"]
    E --> F["Planner"]
    F --> G["Execution plan"]
    G --> H["Executor"]
    H --> I["Database / Services / Runtime"]
~~~

Mỗi phần có trách nhiệm riêng:

- Parser xác định cấu trúc source.
- Semantic analyzer resolve tên, type và constraint.
- IR lưu mô hình đã chuẩn hóa.
- Planner quyết định cách thực hiện.
- Executor chạy plan.
- Adapter kết nối tới API, database hoặc runtime cụ thể.

Không phải DSL nào cũng cần mọi tầng. DSL nhỏ có thể diễn giải AST trực tiếp. Khi ngôn ngữ lớn hoặc có nhiều backend, mô hình trung gian giúp giảm sự phụ thuộc giữa parser và executor.

## 4. Description là hợp đồng khai báo

Description nên mô tả những gì người dùng muốn đạt được, các ràng buộc và dữ liệu cần thiết.

Ví dụ:

~~~text
query highValueOrders {
    from Orders
    where status == APPROVED
      and total > money(1000000, VND)
    select orderId, total
}
~~~

Mô tả không nhất thiết phải chỉ định:

- SQL dialect.
- Index cụ thể.
- Connection pool.
- Thread hoặc worker nào chạy.
- Retry implementation.
- Cách phân vùng dữ liệu vật lý.

Các chi tiết này thuộc planner, executor hoặc deployment configuration, trừ khi chúng là một phần có chủ đích của DSL contract.

### 4.1. Declarative description

Declarative DSL nói kết quả hoặc quan hệ cần có. Engine có quyền chọn cách thực hiện miễn là giữ semantics.

Ví dụ:

~~~text
from Orders
where total > threshold
order by createdAt descending
limit 100
~~~

Engine có thể dùng index, push filter xuống backend hoặc chọn execution strategy khác.

### 4.2. Imperative description

Imperative DSL mô tả trình tự thao tác:

~~~text
open connection
read records
filter records
write report
close connection
~~~

Ngay cả khi DSL imperative, vẫn có thể tách mô tả thành command model rồi để runtime quyết định cách schedule và quản lý tài nguyên.

### 4.3. Không để description giả vờ là configuration thực thi

Nếu source khai báo timeout, consistency hoặc retry, cần xác định đó là semantics của DSL hay hint cho runtime. Ví dụ, timeout là một giới hạn có thể được bảo đảm; còn preferredWorker có thể chỉ là hint.

Tài liệu cần phân biệt constraint bắt buộc, preference và implementation detail.

## 5. AST và intermediate representation

AST là mô hình cấu trúc được tạo từ source. IR là mô hình trung gian đã chuẩn hóa hoặc bổ sung thông tin để compiler/planner xử lý thuận tiện hơn.

Ví dụ source:

~~~text
from Orders
where status == APPROVED
select orderId, total
~~~

AST khái niệm:

~~~text
Query
  Source(Orders)
  Filter
    Equal
      Field(status)
      EnumValue(APPROVED)
  Projection
    Field(orderId)
    Field(total)
~~~

Typed IR có thể bổ sung:

~~~text
QueryPlanInput
  source: Orders
  filter:
    Equal
      left: Field(status, type=OrderStatus)
      right: EnumValue(APPROVED, type=OrderStatus)
  projection:
    - Field(orderId, type=OrderId)
    - Field(total, type=Money)
~~~

IR giữ thông tin ngữ nghĩa mà executor cần, đồng thời loại bỏ một số chi tiết cú pháp như dấu ngoặc hoặc cách viết alias.

### 5.1. Vì sao cần IR?

- Parser không phải biết backend.
- Nhiều executor có thể dùng cùng một model.
- Optimizer có thể biến đổi cấu trúc có kiểu.
- Có thể serialize hoặc cache plan.
- Dễ tạo explain output và diagnostics.

### 5.2. IR không phải public source format

IR có thể thay đổi giữa các compiler version. Nếu lưu IR lâu dài hoặc trao đổi giữa service, cần version format và compatibility policy. Không nên mặc định IR nội bộ là artifact ổn định.

### 5.3. Preserve source mapping

IR node nên giữ source span hoặc reference về AST để runtime error, diagnostics và debugger có thể trỏ về dòng DSL gốc.

## 6. Semantic analysis trước khi thực thi

Tách mô tả và thực thi cho phép kiểm tra mô tả trước khi thực hiện side effect.

Semantic analysis có thể:

- Resolve symbol và module.
- Kiểm tra type.
- Kiểm tra field tồn tại.
- Kiểm tra function và capability.
- Kiểm tra quyền trên source.
- Kiểm tra constraint của workflow.
- Xác nhận backend có capability cần thiết.
- Phát hiện cấu trúc không thể thực thi.

Ví dụ:

~~~text
from Orders
where total > "large"
~~~

Nếu total là Money, validator có thể báo type mismatch trước khi gửi query tới database.

### 6.1. Validation và execution là hai thời điểm khác nhau

Một mô tả hợp lệ vẫn có thể thất bại lúc chạy do network, dữ liệu hoặc dependency. Validation xác nhận các điều kiện có thể kiểm tra trước; executor vẫn cần xử lý runtime failure.

### 6.2. Validation không tạo side effect

Thông thường, validate hoặc explain không nên gọi function có side effect. Nếu compile-time hook được phép thực thi code, nó cần được xem là một capability riêng và giới hạn quyền.

## 7. Planner và execution strategy

Planner chuyển mô tả hoặc IR thành plan phù hợp với môi trường thực thi.

Ví dụ một query plan:

~~~text
Scan Orders
  -> Filter status == APPROVED
  -> Project orderId, total
  -> Return rows
~~~

Planner có thể cân nhắc:

- Backend capability.
- Index và statistics.
- Cost estimate.
- Data locality.
- Parallelism.
- Memory budget.
- Security policy.
- Consistency requirement.

Một workflow planner có thể tạo dependency graph, xác định step song song, queue và retry policy. Một compiler planner có thể chọn bytecode hoặc native target.

### 7.1. Logical plan và physical plan

Logical plan mô tả phép toán cần thực hiện. Physical plan mô tả cách triển khai chúng trên backend cụ thể.

Ví dụ:

~~~text
Logical:
  Filter(Orders, status == APPROVED)

Physical A:
  SQL index scan on orders_status_idx

Physical B:
  Document collection scan with predicate
~~~

Tách hai plan giúp cùng một query logic có thể chạy trên nhiều backend.

### 7.2. Explain plan

Executor hoặc planner có thể cung cấp explain để người dùng xem cách mô tả sẽ được thực hiện. Explain giúp kiểm tra cost và hiểu backend choice mà không cần chạy query đầy đủ.

## 8. Executor và adapter

Executor nhận plan đã được kiểm tra và điều phối việc thực thi. Adapter ánh xạ operation của DSL sang API hoặc protocol cụ thể.

Ví dụ:

~~~text
QueryExecutor
  execute(plan, context)

SqlAdapter
  executeSql(statement, parameters)

DocumentAdapter
  aggregate(collection, pipeline)

InMemoryAdapter
  evaluate(records, expression)
~~~

Executor nên chịu trách nhiệm:

- Nhận execution context.
- Kiểm tra deadline và cancellation.
- Gọi adapter.
- Quản lý resource.
- Chuẩn hóa result/error.
- Ghi trace và metrics.

Adapter nên chịu trách nhiệm ánh xạ operation sang backend và xử lý chi tiết giao thức.

### 8.1. Adapter không được tự đổi semantics

Nếu SQL backend và document backend xử lý null khác nhau, adapter cần chuyển đổi hoặc từ chối operation không tương đương. Không nên âm thầm trả kết quả khác chỉ vì backend có behavior mặc định riêng.

### 8.2. Capability declaration

Backend có thể công bố:

~~~text
SqlAdapter:
  supports:
    joins
    transactions
    windowFunctions

DocumentAdapter:
  supports:
    nestedFields
    aggregation
  doesNotSupport:
    recursiveJoin
~~~

Planner dùng capability để chọn plan hoặc báo unsupported feature trước khi execute.

## 9. Ports and Adapters và Dependency Inversion

Mẫu Ports and Adapters (Hexagonal Architecture) giúp tách core language model khỏi infrastructure.

- Core định nghĩa port hoặc interface mà nó cần.
- Adapter hiện thực interface cho database, filesystem, queue hoặc service.
- Dependency hướng vào abstraction, không hướng trực tiếp vào implementation cụ thể.

Ví dụ:

~~~text
interface OrderRepository {
    findById(orderId): Order
    save(order): Unit
}

Workflow engine depends on OrderRepository

SqlOrderRepository implements OrderRepository
InMemoryOrderRepository implements OrderRepository
~~~

Workflow source hoặc execution logic dùng OrderRepository. Test có thể inject InMemoryOrderRepository; production inject SQL adapter.

### 9.1. Lợi ích

- Test không cần database thật.
- Thay backend ít ảnh hưởng core.
- Có thể cung cấp adapter cho nhiều môi trường.
- Domain logic không phụ thuộc framework.

### 9.2. Giới hạn

Interface quá tổng quát có thể che mất capability riêng của backend. Nếu abstraction cố giả vờ mọi database đều giống nhau, nó có thể giới hạn tính năng hoặc tạo semantics không chính xác.

Nên giữ core contract nhỏ và công bố capability extension khi cần.

## 10. Command model và Query model

Một cách tách khác là phân biệt mô tả đọc dữ liệu và mô tả thay đổi trạng thái:

- Query mô tả dữ liệu cần đọc, không thay đổi state quan sát được.
- Command mô tả hành động hoặc thay đổi state.

Ví dụ:

~~~text
query findOrder(orderId) {
    from Orders
    where id == orderId
}

command approveOrder(orderId) {
    update Orders
    set status = APPROVED
    where id == orderId
}
~~~

Query executor có thể tối ưu read path và cache phù hợp. Command executor cần authorization, transaction, idempotency và audit.

### 10.1. CQRS

Command Query Responsibility Segregation (CQRS) tách model xử lý command khỏi model phục vụ query. Đây là một lựa chọn kiến trúc, không phải yêu cầu bắt buộc của mọi DSL.

Nếu dùng CQRS, tài liệu cần mô tả consistency giữa write model và read model, đặc biệt khi read model được cập nhật bất đồng bộ.

## 11. Separation of concerns trong workflow DSL

Workflow description nên mô tả:

- Step và dependency.
- Condition và branch.
- Retry/timeout policy.
- Input/output mapping.
- Compensation nếu có.

Workflow engine xử lý:

- Scheduling.
- Durable state.
- Worker assignment.
- Timer.
- Retry.
- Event correlation.
- Cancellation.
- Recovery.

Ví dụ:

~~~text
workflow shipOrder {
    step reserve {
        call inventory.reserve(orderId)
    }

    step arrangeShipment {
        call shipping.createLabel(orderId)
        after reserve
    }

    step notify {
        call notification.send(orderId)
        after arrangeShipment
    }
}
~~~

Source không cần biết queue implementation, worker thread hoặc database table dùng để lưu workflow state. Những chi tiết đó thuộc runtime.

### 11.1. Workflow versioning

Definition có thể được compile hoặc lưu thành artifact. Instance đang chạy cần biết nó thuộc definition version nào. Nếu runtime thay đổi, engine cần policy để tiếp tục instance cũ hoặc migrate có kiểm soát.

### 11.2. Durable execution

Engine có thể persist state và event history để khôi phục sau restart. Description không nên phụ thuộc vào biến process-local nếu workflow có thể tồn tại lâu.

## 12. Separation trong query DSL

Query DSL mô tả dữ liệu và phép biến đổi. Query planner/executor quyết định cách đọc dữ liệu:

~~~text
from Orders
where region == "NORTH"
  and status == APPROVED
select orderId, total
order by total descending
limit 50
~~~

Một engine có thể:

- Dịch sang SQL.
- Tạo document aggregation pipeline.
- Chạy trên in-memory collection.
- Gọi data service có query API.

### 12.1. Logical semantics phải ổn định

Cùng query nên giữ semantics đã công bố khi backend thay đổi. Các khác biệt như null, collation, timezone, ordering và numeric precision cần được xử lý rõ.

### 12.2. Parameter binding

Parameter được truyền riêng với query structure. Điều này tách mô tả khỏi dữ liệu đầu vào và giúp executor dùng prepared statement hoặc cơ chế tương đương.

### 12.3. Security policy

Executor hoặc trusted data adapter áp dụng authorization và row policy. Người viết query không được tự xóa security predicate bắt buộc.

## 13. Separation trong build và deployment DSL

Một deployment DSL có thể mô tả:

~~~text
service pricing {
    image pricing-bundle
    replicas 3
    expose port 8080
}
~~~

Deployment engine quyết định cách tạo resource trên Kubernetes, VM hoặc môi trường khác. Description có thể giữ ở mức service, replica và port; adapter ánh xạ sang API nền tảng.

Tách biệt giúp:

- Review desired state trước khi apply.
- Tạo plan/diff.
- Dry-run.
- Chọn provider.
- Test bằng mock infrastructure.
- Lưu deployment definition có version.

Tuy nhiên, abstraction không nên che các khác biệt quan trọng như network policy, storage class hoặc availability guarantee. Các capability-specific setting cần được thể hiện rõ.

## 14. Dry-run, simulation và preview

Khi description tách khỏi execution, hệ thống có thể hỗ trợ mode không tạo side effect:

- Validate: kiểm tra mô tả.
- Explain: hiển thị plan.
- Dry-run: mô phỏng thay đổi hoặc kiểm tra khả năng thực thi.
- Preview: trả sample result hoặc diff.
- Execute: thực hiện thật.

Ví dụ:

~~~text
deploy plan pricing --dry-run
~~~

Dry-run cần có contract rõ. Một số hệ thống có thể đọc metadata hoặc gọi API kiểm tra, nhưng không commit thay đổi. Không nên gọi một operation là dry-run nếu nó vẫn tạo side effect không thể đảo ngược.

## 15. Testability nhờ tách mô tả và thực thi

Khi core logic phụ thuộc interface thay vì database hoặc network thật, có thể thay executor trong test.

Các loại test:

- Parser test: source tạo AST đúng.
- Semantic test: AST hợp lệ theo type và rule.
- Planner test: logical plan được tạo đúng.
- Executor unit test: gọi adapter đúng.
- Adapter integration test: protocol với backend đúng.
- End-to-end test: toàn bộ source tới kết quả.
- Contract test: nhiều adapter giữ cùng semantics.

Ví dụ:

~~~text
fakeRepository = InMemoryOrderRepository(fixtures)
executor = WorkflowExecutor(fakeRepository)

result = executor.run(approveOrder(orderId))

assert result.status == APPROVED
~~~

Test có thể kiểm tra logic workflow mà không cần khởi tạo database production-like.

### 15.1. Fake và mock

Fake là implementation đơn giản có hành vi thật trong phạm vi test. Mock xác minh interaction hoặc call expectation. Không nên mock mọi thứ nếu test chỉ xác nhận mock được gọi; cần integration test để kiểm tra adapter thật.

### 15.2. Contract test

Nếu có SQL adapter và in-memory adapter, chạy cùng contract suite trên cả hai để xác nhận semantics giống nhau trong phần capability chung.

## 16. Security boundary và quyền thực thi

Tách description khỏi execution giúp đặt authorization tại một nơi có thẩm quyền.

Các câu hỏi:

- Ai được tạo hoặc sửa description?
- Ai được approve và deploy?
- Executor chạy bằng identity nào?
- Function nào được phép gọi?
- Connector nào được phép truy cập?
- Secret được resolve ở đâu?
- Resource limit được áp dụng thế nào?

Ví dụ:

~~~text
workflow refund {
    call payment.refund(orderId)
}
~~~

Việc source có thể parse không có nghĩa caller được phép refund. Executor cần kiểm tra capability và policy trước side effect.

### 16.1. Least privilege

Parser không cần credential production. Planner thường không cần quyền ghi dữ liệu. Executor chỉ nên nhận capability cần thiết cho action đang chạy.

### 16.2. Untrusted description

Description gửi từ người dùng cần được validate và giới hạn. Không deserialize object tùy ý hoặc chạy macro/plugin không tin cậy trong process có quyền rộng.

### 16.3. Secret reference

Source nên tham chiếu secret bằng ID hoặc logical name. Executor lấy secret từ secret manager theo workload identity thay vì lưu literal trong DSL.

## 17. Versioning của description và execution engine

Description có thể được lưu lâu hơn một phiên bản executor. Vì vậy cần version hóa:

- Language version.
- AST/IR format.
- Workflow/query definition version.
- Adapter contract.
- Runtime API.
- Execution plan format.

Ví dụ:

~~~yaml
definition:
  languageVersion: 3
  modelFormat: 2
  executorContract: 5
~~~

Khi load definition, engine kiểm tra version và chuyển đổi hoặc từ chối với lỗi rõ ràng. Không nên âm thầm diễn giải source cũ theo semantics mới nếu behavior đã thay đổi.

### 17.1. Recompile hay lưu plan?

Có thể lưu source và compile lại khi deploy, hoặc lưu compiled model/plan. Lưu plan giúp giảm startup nhưng tạo phụ thuộc vào format và compiler version. Lưu source linh hoạt hơn nhưng cần compiler tương thích và build reproducibility.

### 17.2. Adapter contract

Adapter contract nên được version hóa độc lập nếu method signature, error mapping hoặc capability thay đổi. Test contract giúp bảo đảm adapter cũ và mới thực hiện đúng behavior được yêu cầu.

## 18. Serialization và persistence của mô tả

Description có thể được lưu dưới dạng:

- Source DSL.
- AST/IR serialization.
- Workflow definition record.
- Query template.
- Deployment manifest.

Lưu source thường dễ review và di trú hơn. Lưu IR có thể load nhanh nhưng cần quản lý schema version.

Nếu serialized model được dùng qua network hoặc lưu từ nguồn không tin cậy, cần:

- Schema validation.
- Version check.
- Size/depth limits.
- Integrity verification nếu phù hợp.
- Tránh native object deserialization không an toàn.

Không nên coi serialized AST là trusted chỉ vì nó được tạo từ một compiler ở thời điểm trước.

## 19. Error handling và observability

Tách biệt giúp phân loại lỗi theo tầng:

| Tầng | Ví dụ lỗi |
|---|---|
| Parse | Syntax error |
| Semantic analysis | Unknown symbol, type mismatch |
| Planning | Backend không hỗ trợ capability |
| Authorization | Caller không có quyền |
| Execution | Timeout, database unavailable |
| Adapter | Protocol hoặc serialization error |
| Domain operation | Order không thể approve |

Diagnostic nên chỉ rõ lỗi thuộc tầng nào và trỏ về source location nếu có thể.

### 19.1. Explainability

Engine có thể hiển thị:

- Description đã resolve.
- Logical plan.
- Physical plan.
- Adapter/backend được chọn.
- Policy được áp dụng.
- Thời gian từng phase.

### 19.2. Correlation

Request ID, definition version, plan ID và execution ID giúp liên kết source với lần chạy cụ thể.

### 19.3. Không làm lộ secret

Trace và error message không nên chứa credential hoặc payload nhạy cảm. Source mapping và observability cần tuân theo data classification.

## 20. Trade-off của việc tách mô tả và thực thi

Tách biệt mang lại khả năng mở rộng nhưng cũng tạo thêm abstraction.

| Lợi ích | Chi phí hoặc rủi ro |
|---|---|
| Thay backend dễ hơn | Cần adapter và contract |
| Test core không cần infrastructure | Cần integration test để xác nhận adapter thật |
| Có thể optimize plan | Planner phức tạp hơn |
| Description dễ review | Một số chi tiết backend phải được biểu diễn qua extension |
| Có thể dry-run/explain | Cần định nghĩa chính xác mode không side effect |
| Version hóa độc lập | Cần migration cho model và plan |
| Security tập trung ở executor | Executor trở thành thành phần trọng yếu cần bảo vệ |
| Reuse cùng description | Backend capability có thể khác nhau |

### 20.1. Abstraction leak

Abstraction leak xảy ra khi chi tiết backend ảnh hưởng kết quả dù DSL cố che giấu nó. Ví dụ, database A phân biệt null với missing, còn database B không. Nếu DSL không định nghĩa semantics chung, người dùng sẽ thấy behavior khác nhau.

Giải pháp là xác định portable core và công bố extension hoặc limitation.

### 20.2. Overengineering

DSL nhỏ chỉ có một executor có thể không cần nhiều tầng IR, planner và adapter. Chọn mức tách phù hợp với số backend, độ phức tạp và vòng đời sản phẩm.

### 20.3. Hidden execution cost

Description cấp cao có thể che chi phí lớn như full scan hoặc workflow fan-out. Cần explain plan, cost budget và profile để người dùng hiểu tác động.

## 21. Khi nào nên dùng mẫu thiết kế này?

Tách mô tả và thực thi đặc biệt hữu ích khi:

- Cùng một DSL chạy trên nhiều backend.
- Source cần được lưu, review và thực thi sau.
- Có nhiều execution mode như test, dry-run và production.
- Cần validate trước khi side effect xảy ra.
- Muốn tối ưu plan độc lập với syntax.
- Có plugin hoặc adapter do bên khác triển khai.
- Workflow/query cần durable execution.
- Cần audit và version hóa definition.

Ít cần thiết hơn khi:

- DSL chỉ là wrapper mỏng quanh một function.
- Không có nhu cầu đổi backend hoặc test executor riêng.
- Mô hình trung gian tạo nhiều chi phí hơn lợi ích.
- Ngôn ngữ chủ yếu là imperative code và không có lợi ích rõ từ declarative model.

Quyết định nên dựa trên nhu cầu thực tế, không phải vì kiến trúc nhiều tầng luôn tốt hơn.

## 22. Những lỗi thiết kế thường gặp

### Trộn domain logic với database API

Source DSL phụ thuộc trực tiếp vào SQL connection hoặc ORM. Tách query model khỏi adapter nếu cần nhiều backend hoặc test độc lập.

### Để executor tự suy diễn semantics

Mỗi adapter diễn giải null, ordering hoặc error khác nhau. Định nghĩa semantics ở core và yêu cầu adapter tuân thủ.

### IR không có version

Artifact cũ không load được sau nâng compiler. Version hóa serialized model và cung cấp migration hoặc compatibility policy.

### Cho phép side effect trong validation

Một lần kiểm tra source có thể vô tình ghi dữ liệu. Giữ validation thuần hoặc cô lập compile-time capability.

### Abstraction quá tổng quát

Core API không thể biểu đạt capability riêng và buộc backend giả vờ hỗ trợ. Dùng portable core cộng capability extension.

### Bỏ qua authorization ở executor

Source đã validate nhưng caller không có quyền thực hiện. Kiểm tra policy tại execution boundary.

### Chỉ test mock

Mock pass nhưng adapter thật sai protocol. Bổ sung contract và integration test.

### Không quản lý lifecycle

Connection, transaction hoặc cancellation không được đóng đúng. Executor cần ownership và cleanup contract rõ.

### Không quan sát physical plan

Query hoặc workflow có chi phí lớn bị che giấu. Cung cấp explain và runtime metrics.

## 23. Quy trình thiết kế và triển khai

Một quy trình thực tế:

1. **Xác định domain description.** Người dùng cần mô tả ý định và constraint nào?
2. **Định nghĩa semantics.** Quy tắc kiểu, thứ tự, lỗi, side effect và consistency.
3. **Thiết kế AST/IR.** Biểu diễn cấu trúc độc lập với backend.
4. **Tạo validation pipeline.** Parse, resolve, type-check và authorize.
5. **Tạo planner nếu cần.** Chuyển logical model thành physical plan.
6. **Định nghĩa executor contract.** Input, output, error, cancellation và resource ownership.
7. **Xây adapter.** Ánh xạ operation tới backend.
8. **Quản lý capability.** Công bố phần backend hỗ trợ.
9. **Version hóa model và contract.** Xử lý definition cũ.
10. **Bổ sung explain/observability.** Liên kết source, plan và execution.
11. **Kiểm thử nhiều tầng.** Unit, contract, integration và end-to-end.
12. **Đo overhead.** Chỉ giữ tầng abstraction có lợi ích tương xứng.

## 24. Ví dụ end-to-end: cùng query description, nhiều executor

Giả sử DSL mô tả:

~~~text
query activeCustomers {
    from Customers
    where status == ACTIVE
    select customerId, name
}
~~~

### 24.1. Parse và typed model

Parser tạo AST. Semantic analyzer resolve Customers, status, ACTIVE, customerId và name theo schema. Typed model xác nhận status là CustomerStatus và projection có hai field.

### 24.2. Logical plan

~~~text
Scan(Customers)
  -> Filter(status == ACTIVE)
  -> Project(customerId, name)
~~~

### 24.3. SQL executor

~~~sql
SELECT customer_id, name
FROM customers
WHERE status = :active_status
~~~

### 24.4. In-memory executor

~~~text
for customer in customers:
    if customer.status == ACTIVE:
        emit customer.customerId, customer.name
~~~

### 24.5. Contract

Cả hai executor cần giữ semantics về:

- ACTIVE comparison.
- Null status.
- Projection type.
- Ordering nếu DSL có yêu cầu ordering.
- Authorization và tenant policy.

Nếu một backend không hỗ trợ semantics cần thiết, planner phải từ chối hoặc dùng strategy khác đã được kiểm chứng.

### 24.6. Test

Chạy cùng fixture qua SQL adapter và in-memory adapter, so sánh kết quả theo contract. Integration test xác nhận SQL parameter binding và schema mapping thực tế.

## 25. Kết luận

Tách mô tả và thực thi là mẫu thiết kế giúp DSL biểu đạt ý định bằng mô hình ổn định, trong khi compiler, planner, executor và adapter chịu trách nhiệm biến mô tả thành hành vi trên môi trường cụ thể. Nó tạo điều kiện cho nhiều backend, dry-run, explain, test độc lập, authorization tập trung và version hóa definition.

Một kiến trúc phù hợp thường có source DSL, AST/IR, semantic validation, planner và execution adapter. Không phải mọi DSL đều cần đầy đủ các tầng; mức tách nên dựa trên số backend, độ phức tạp, yêu cầu kiểm thử và vòng đời definition.

Điều quan trọng nhất là giữ semantics ở một nơi có thẩm quyền và yêu cầu mọi executor tuân thủ cùng contract. Khi có capability khác nhau, hãy công bố giới hạn thay vì che giấu khác biệt. Kết hợp contract test, integration test, versioning và observability giúp mô tả vẫn dễ đọc trong khi execution có thể thay đổi theo nhu cầu của hệ thống.
