# Biến đổi mô hình

## 1. Biến đổi mô hình trong DSL là gì?

Trong phát triển ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*), mô hình thường được tạo từ văn bản nguồn sau các bước lexing, parsing và semantic analysis. Mô hình biểu diễn các khái niệm miền, thuộc tính và quan hệ ở mức trừu tượng hơn cú pháp văn bản.

**Biến đổi mô hình (*model transformation*)** là quá trình nhận một mô hình đầu vào, áp dụng một tập quy tắc hoặc thuật toán để tạo ra mô hình khác, cập nhật mô hình hiện tại hoặc chuyển mô hình sang một biểu diễn mới. Mô hình nguồn và mô hình đích có thể tuân theo cùng một meta-model hoặc hai meta-model khác nhau.

Ví dụ, một DSL mô tả workflow:

~~~text
workflow "order-fulfillment" {
    start validateOrder
    then reserveStock
    then capturePayment
    then shipOrder
}
~~~

Sau khi parser tạo workflow model, một phép biến đổi có thể chuyển mô hình này thành execution plan:

~~~text
ExecutionPlan {
    entry: "validateOrder"
    nodes: [
        Invoke("validateOrder"),
        Invoke("reserveStock"),
        Invoke("capturePayment"),
        Invoke("shipOrder")
    ]
}
~~~

Mục tiêu của phép biến đổi là bảo toàn ý nghĩa cần thiết của workflow trong biểu diễn đích. Execution plan phải thể hiện đúng thứ tự bước, điều kiện, dependency và các hành vi được quy định bởi DSL.

Biến đổi mô hình là một phần quan trọng của model-driven engineering. Nó giúp tách mô hình miền khỏi chi tiết nền tảng thực thi, hỗ trợ sinh code, chuyển đổi phiên bản, đồng bộ các biểu diễn và tái sử dụng mô hình ở nhiều giai đoạn của toolchain.

## 2. Những khái niệm nền tảng

### 2.1. Model và metamodel

**Model** là một biểu diễn cụ thể của hệ thống hoặc miền. Ví dụ một workflow, sơ đồ lớp, cấu hình triển khai hoặc mô hình dữ liệu là một model.

**Metamodel** định nghĩa cấu trúc mà model được phép có: các loại phần tử, thuộc tính, quan hệ, kiểu và ràng buộc. Có thể hiểu model là một instance tuân theo metamodel.

Ví dụ metamodel rút gọn cho workflow:

~~~text
Workflow
- name: String
- steps: Step [1..*]
- startStep: Step [1]

Step
- id: String
- action: Action
- next: Step [0..*]
~~~

Một model workflow cụ thể là tập instance của Workflow và Step tuân theo cấu trúc trên.

### 2.2. Source model và target model

- **Source model:** mô hình đầu vào của phép biến đổi.
- **Target model:** mô hình được tạo ra hoặc cập nhật.
- **Source metamodel:** định nghĩa cấu trúc hợp lệ của source model.
- **Target metamodel:** định nghĩa cấu trúc hợp lệ của target model.

Nếu hai metamodel giống nhau, phép biến đổi có thể chuẩn hóa hoặc tái cấu trúc mô hình. Nếu chúng khác nhau, phép biến đổi cần ánh xạ khái niệm giữa hai ngôn ngữ mô hình.

### 2.3. Transformation rule

Transformation rule mô tả cách nhận diện một phần của source model và tạo hoặc thay đổi phần tương ứng trong target model.

Một rule thường gồm:
- **Source pattern:** mẫu node và quan hệ cần tìm.
- **Guard:** điều kiện để rule được áp dụng.
- **Target pattern:** node và quan hệ cần tạo hoặc cập nhật.
- **Binding:** cách gán thuộc tính và liên kết từ nguồn sang đích.
- **Trace:** thông tin liên hệ giữa phần tử nguồn và phần tử đích.

### 2.4. Mapping

Mapping mô tả quan hệ tương ứng giữa phần tử nguồn và phần tử đích. Ví dụ:
- Workflow tương ứng với ExecutionPlan.
- Workflow Step tương ứng với ExecutionNode.
- Action trong source tương ứng với Operation trong target.
- Quan hệ next trong source tương ứng với cạnh điều khiển trong target.

Mapping có thể là một-một, một-nhiều, nhiều-một hoặc phụ thuộc ngữ cảnh. Không nên giả định mỗi source node luôn tạo đúng một target node.

## 3. Vì sao cần biến đổi mô hình?

Một mô hình miền thường dễ hiểu với chuyên gia nghiệp vụ nhưng chưa đủ chi tiết để thực thi trực tiếp. Biến đổi mô hình giúp chuyển từ cách diễn đạt gần miền sang biểu diễn phù hợp cho một mục tiêu kỹ thuật.

Các mục đích phổ biến:

1. **Sinh mã:** chuyển mô hình thiết kế thành code, schema, cấu hình hoặc artifact.
2. **Chuyển mức trừu tượng:** chuyển mô hình độc lập nền tảng thành mô hình phụ thuộc nền tảng.
3. **Chuyển ngôn ngữ mô hình:** ánh xạ từ DSL này sang DSL khác.
4. **Chuẩn hóa:** làm mô hình nhất quán theo một cấu trúc chuẩn.
5. **Tối ưu:** biến đổi mô hình để cải thiện hiệu năng hoặc khả năng triển khai.
6. **Di trú:** chuyển model từ metamodel hoặc phiên bản DSL cũ sang phiên bản mới.
7. **Đồng bộ:** giữ nhiều biểu diễn liên quan nhất quán với nhau.
8. **Phân tích:** tạo graph, dependency model hoặc biểu diễn trung gian để kiểm tra.
9. **Tái sử dụng:** chuyển một mô hình miền sang nhiều nền tảng hoặc runtime khác nhau.

Ví dụ, cùng một workflow model có thể được biến đổi thành:
- Execution plan cho runtime nội bộ.
- Kubernetes workflow hoặc cấu hình orchestration.
- Sơ đồ trực quan cho người vận hành.
- Bộ test scenario.
- Tài liệu mô tả quy trình.

Một source model có thể có nhiều target model nếu mỗi target phục vụ một mục đích riêng.

## 4. Phân loại phép biến đổi mô hình

### 4.1. Endogenous và exogenous transformation

**Endogenous transformation** biến đổi một mô hình sang mô hình khác tuân theo cùng metamodel. Ví dụ chuẩn hóa AST hoặc đổi tên và tái cấu trúc các phần tử trong cùng DSL.

**Exogenous transformation** chuyển từ một metamodel sang metamodel khác. Ví dụ chuyển workflow DSL thành execution model hoặc chuyển class model thành relational schema.

| Loại | Source metamodel | Target metamodel | Ví dụ |
|---|---|---|---|
| Endogenous | Giống target | Giống source | Chuẩn hóa, refactoring |
| Exogenous | Khác target | Khác source | DSL sang code model, UML sang database model |

Phân loại này nói về quan hệ metamodel, không nói phép biến đổi có cập nhật tại chỗ hay tạo model mới.

### 4.2. In-place và out-of-place transformation

- **In-place:** thay đổi trực tiếp source model.
- **Out-of-place:** tạo target model riêng, source vẫn được giữ lại.

In-place phù hợp với refactoring hoặc cập nhật một mô hình đang sở hữu. Out-of-place phù hợp khi cần giữ source làm dữ liệu gốc, tạo nhiều target hoặc so sánh kết quả trước khi thay thế.

### 4.3. Horizontal và vertical transformation

- **Horizontal transformation:** chuyển đổi giữa các mô hình ở mức trừu tượng tương đương, ví dụ từ một DSL nghiệp vụ sang DSL nghiệp vụ khác.
- **Vertical transformation:** chuyển giữa các mức trừu tượng khác nhau, ví dụ từ mô hình phân tích sang mô hình thiết kế, rồi sang code hoặc deployment model.

### 4.4. Unidirectional và bidirectional transformation

**Unidirectional transformation** có một chiều chính từ source sang target. Target được tạo hoặc cập nhật theo source.

**Bidirectional transformation** duy trì quan hệ giữa hai mô hình theo cả hai hướng. Thay đổi ở một phía có thể được truyền sang phía còn lại theo quy tắc đồng bộ.

Biến đổi hai chiều khó hơn vì cần xác định cách xử lý thay đổi xung đột, thông tin bị mất và nhiều trạng thái có thể tương ứng với cùng một kết quả.

### 4.5. Model-to-model, model-to-text và text-to-model

| Dạng | Đầu vào | Đầu ra | Ví dụ |
|---|---|---|---|
| Model-to-model (M2M) | Model | Model | Workflow model sang execution model |
| Model-to-text (M2T) | Model | Văn bản/code | Class model sang Java |
| Text-to-model (T2M) | Văn bản | Model | DSL source sang AST/model |
| Model-to-graph | Model | Graph | Model sang dependency graph |

Model-to-text thường được gọi là code generation khi target là mã nguồn hoặc cấu hình văn bản. Parser của DSL là một dạng chuyển từ văn bản sang model, nhưng thường được xem là front-end parsing hơn là transformation nghiệp vụ.

## 5. Quy trình tổng quát của model transformation

Một pipeline biến đổi mô hình có thể gồm các bước:

~~~text
Source DSL
    |
    v
Parsing
    |
    v
Source model
    |
    v
Source validation
    |
    v
Source-to-target transformation
    |
    v
Target model
    |
    v
Target validation
    |
    v
Serialization / code generation / execution
~~~

### 5.1. Nạp source model

Source model có thể được tạo từ parser, nạp từ file model hoặc nhận từ một repository. Trước khi biến đổi, cần biết:
- Metamodel và version của source.
- Root model và phạm vi được biến đổi.
- Các module hoặc model phụ thuộc.
- Các reference đã được resolve hay chưa.
- Source có hợp lệ theo những ràng buộc bắt buộc không.

### 5.2. Kiểm tra source

Không phải mọi model đều có thể biến đổi an toàn. Source validation có thể kiểm tra:
- Cấu trúc và multiplicity.
- Reference integrity.
- Kiểu và constraint.
- Những thuộc tính bắt buộc cho target.
- Các điều kiện tiền đề của transformation.

Nếu source vi phạm precondition, engine nên phát diagnostic và quyết định rõ có dừng, bỏ qua phần tử hay tiếp tục với phần độc lập.

### 5.3. Áp dụng transformation rules

Engine tìm các source pattern, kiểm tra guard, rồi tạo hoặc cập nhật target elements. Quy tắc có thể được áp dụng một lần, theo thứ tự hoặc lặp đến khi không còn thay đổi.

### 5.4. Kiểm tra target

Target model cần được validate theo target metamodel và các invariant riêng. Một phép biến đổi hoàn tất về mặt thuật toán nhưng tạo ra target model không hợp lệ vẫn là thất bại.

### 5.5. Lưu kết quả

Target có thể được:
- Lưu thành model file.
- Chuyển thành AST hoặc IR.
- Sinh code hoặc cấu hình.
- Gửi đến compiler/runtime khác.
- So sánh với target trước đó để tạo delta.

Nên lưu metadata về source version, transformation version và target metamodel version để có thể tái tạo kết quả.

## 6. Thiết kế transformation rules

### 6.1. Mẫu rule cơ bản

Một rule có thể được mô tả khái niệm như sau:

~~~text
rule StepToExecutionNode {
    from source: WorkflowStep
    where source.enabled == true

    to target: ExecutionNode {
        id = source.id
        operation = mapAction(source.action)
    }
}
~~~

Rule tìm các WorkflowStep được bật, tạo ExecutionNode tương ứng, sao chép ID và ánh xạ action.

Cú pháp trên là pseudocode minh họa, không phải cú pháp bắt buộc của một framework cụ thể.

### 6.2. Source pattern

Source pattern xác định loại node, thuộc tính và quan hệ cần khớp. Pattern càng cụ thể thì rule càng dễ hiểu, nhưng quá nhiều điều kiện có thể làm rule khó tái sử dụng.

Ví dụ:
- Một Workflow có Step.
- Step có action thuộc loại ServiceCall.
- Step có thuộc tính retryCount lớn hơn 0.
- Step có dependency đến một Step khác.

### 6.3. Guard condition

Guard là điều kiện Boolean quyết định rule có được áp dụng cho một match hay không.

Ví dụ:
- Chỉ biến đổi step có enabled = true.
- Chỉ tạo database index nếu thuộc tính được đánh dấu indexed.
- Chỉ sinh transaction wrapper khi operation có side effect.

Guard nên thuần nếu có thể. Nếu guard thay đổi source hoặc gọi dịch vụ ngoài, kết quả match có thể phụ thuộc thứ tự thực thi và khó tái lập.

### 6.4. Target pattern và binding

Target pattern định nghĩa node cần tạo. Binding gán giá trị từ source hoặc từ context:

~~~text
target.id = source.id
target.timeout = source.timeout ?? defaultTimeout
target.kind = mapKind(source.kind)
~~~

Cần quy định cách xử lý:
- Thuộc tính thiếu hoặc null.
- Giá trị mặc định.
- Chuyển kiểu.
- Collection và thứ tự phần tử.
- Reference đến target element khác.
- Giá trị không thể biểu diễn trong target metamodel.

### 6.5. Mapping quan hệ

Biến đổi không chỉ tạo node mà còn phải tái tạo quan hệ. Nếu source có hai step A và B với A.next = B, target cần có cạnh tương ứng sau khi cả hai target node được tạo.

Điều này tạo ra dependency giữa các rule. Có thể dùng hai phase:
1. Tạo target node và ghi trace mapping.
2. Tạo edge/reference dựa trên mapping đã có.

Cách này tránh yêu cầu target node phải tồn tại trước khi source relation được xử lý.

## 7. Ví dụ: biến đổi Workflow DSL thành Execution Model

### 7.1. Source metamodel

Giả sử source metamodel gồm:

~~~text
Workflow
- name: String
- steps: Step [1..*]
- start: Step [1]

Step
- id: String
- action: Action
- next: Step [0..*]
- enabled: Boolean

Action
- kind: ActionKind
- parameters: Map<String, Value>
~~~

### 7.2. Target metamodel

Target execution model:

~~~text
ExecutionPlan
- name: String
- entryNode: ExecutionNode
- nodes: ExecutionNode [1..*]

ExecutionNode
- id: String
- operation: Operation
- successors: ExecutionNode [0..*]

Operation
- opcode: String
- arguments: Map<String, Value>
~~~

### 7.3. Mapping table

| Source | Target | Quy tắc |
|---|---|---|
| Workflow | ExecutionPlan | Tạo một plan cùng tên |
| Step | ExecutionNode | Tạo node cho mỗi step được bật |
| Step.id | ExecutionNode.id | Sao chép ID |
| Step.action | ExecutionNode.operation | Ánh xạ action sang operation |
| Step.next | ExecutionNode.successors | Ánh xạ qua trace map |
| Workflow.start | ExecutionPlan.entryNode | Resolve node đích tương ứng |

### 7.4. Transformation rules

~~~text
rule WorkflowToPlan:
    from w: Workflow
    to p: ExecutionPlan {
        name = w.name
    }

rule EnabledStepToNode:
    from s: Step
    where s.enabled
    to n: ExecutionNode {
        id = s.id
        operation = mapAction(s.action)
    }

rule StepEdges:
    for each sourceStep in workflow.steps:
        for each nextStep in sourceStep.next:
            connect(
                trace[sourceStep],
                trace[nextStep]
            )

rule EntryPoint:
    p.entryNode = trace[workflow.start]
~~~

### 7.5. Điều kiện hợp lệ và lỗi

Nếu Workflow.start trỏ đến một Step bị disabled và target không cho phép entry node bị thiếu, transformation phải báo lỗi. Nếu Step A.next trỏ đến Step B bị disabled, cần có chính sách rõ:
- Báo lỗi vì cạnh đích không tồn tại.
- Bỏ cạnh nếu semantics cho phép bỏ qua step.
- Nối A đến successor kế tiếp của B nếu DSL định nghĩa cách rút gọn.
- Tạo một node no-op thay thế.

Không nên tự chọn một trong các hành vi trên nếu đặc tả DSL chưa quy định. Mỗi lựa chọn có thể làm thay đổi ý nghĩa workflow.

### 7.6. Kết quả mẫu

Source:

~~~text
workflow "checkout" {
    start validate
    step validate action ValidateOrder next reserve
    step reserve action ReserveStock next charge
    step charge action CapturePayment next ship
    step ship action ShipOrder
}
~~~

Target:

~~~text
ExecutionPlan("checkout") {
    entryNode = "validate"

    node "validate" {
        operation = ValidateOrder
        successors = ["reserve"]
    }

    node "reserve" {
        operation = ReserveStock
        successors = ["charge"]
    }

    node "charge" {
        operation = CapturePayment
        successors = ["ship"]
    }

    node "ship" {
        operation = ShipOrder
        successors = []
    }
}
~~~

Target model cần giữ đúng thứ tự điều khiển và các tham số action được ánh xạ. Ví dụ minh họa bỏ qua chi tiết serialization và kiểu tham số cụ thể.

## 8. Traceability giữa source và target

### 8.1. Trace link

Traceability là khả năng truy ngược quan hệ giữa phần tử nguồn và phần tử đích. Một trace link có thể lưu:
- Source element ID.
- Target element ID.
- Transformation rule đã tạo liên kết.
- Mapping version.
- Source location.
- Các tham số hoặc quyết định liên quan.

Ví dụ:

~~~text
TraceLink {
    sourceId: "workflow.step.reserve"
    targetId: "execution.node.reserve"
    ruleId: "EnabledStepToNode"
}
~~~

### 8.2. Vì sao traceability quan trọng?

Traceability hỗ trợ:
- Giải thích target node được sinh từ đâu.
- Hiển thị source khi debug execution model.
- Cập nhật target khi source thay đổi.
- Xác định phần target bị ảnh hưởng bởi một thay đổi.
- Hỗ trợ audit và migration.
- Báo lỗi target validation tại vị trí source có liên quan.

### 8.3. Mapping cardinality

Một source node có thể tạo nhiều target node. Ví dụ một transaction block có thể tạo:
- BeginTransaction node.
- Các operation node.
- Commit node.
- Rollback handler.

Ngược lại, nhiều source node có thể được gộp thành một target node, ví dụ nhiều khai báo cấu hình cùng nhóm thành một deployment resource.

Trace model cần hỗ trợ một-nhiều và nhiều-một, không nên chỉ lưu một target ID cho mỗi source ID.

### 8.4. Traceability không phải source code generation mapping

Trace link giữa model elements có thể tồn tại ngay cả khi chưa sinh code. Khi tiếp tục model-to-text, cần thêm mapping từ target model node đến đoạn code hoặc artifact tương ứng. Hai lớp mapping này có thể được nối với nhau để truy từ code về source DSL.

## 9. Các chiến lược thực thi transformation

### 9.1. Declarative transformation

Cách khai báo mô tả quan hệ giữa source pattern và target pattern, để engine tìm match và áp dụng rule.

Ưu điểm:
- Rule gần với mapping cần thể hiện.
- Có thể tách khỏi thuật toán duyệt.
- Phù hợp với nhiều mapping độc lập.
- Có thể phân tích hoặc kiểm tra rule ở mức khai báo.

Hạn chế:
- Khó biểu diễn một số thuật toán phức tạp.
- Thứ tự áp dụng và conflict resolution cần được định nghĩa.
- Debug có thể khó nếu engine tự động tìm nhiều match.

### 9.2. Imperative transformation

Cách mệnh lệnh dùng code hoặc thao tác tuần tự:

~~~java
ExecutionPlan transform(Workflow workflow) {
    ExecutionPlan plan = new ExecutionPlan(workflow.name());

    Map<Step, ExecutionNode> mapping = new HashMap<>();

    for (Step step : workflow.steps()) {
        if (!step.enabled()) {
            continue;
        }

        ExecutionNode node = new ExecutionNode(step.id());
        node.setOperation(mapAction(step.action()));
        plan.addNode(node);
        mapping.put(step, node);
    }

    for (Step step : workflow.steps()) {
        ExecutionNode source = mapping.get(step);
        if (source == null) {
            continue;
        }

        for (Step next : step.next()) {
            ExecutionNode target = mapping.get(next);
            if (target == null) {
                throw new TransformationException(
                    "Target step is missing: " + next.id()
                );
            }
            source.addSuccessor(target);
        }
    }

    plan.setEntryNode(mapping.get(workflow.start()));
    return plan;
}
~~~

Đây là mã Java minh họa. Nó thể hiện hai lượt: tạo node và sau đó nối cạnh. Một triển khai thực tế cần diagnostics có source location, validation, transaction và chính sách xử lý step bị disabled.

Ưu điểm:
- Dễ dùng thuật toán tổng quát và logic điều kiện phức tạp.
- Dễ tích hợp thư viện host.
- Luồng xử lý tường minh.

Hạn chế:
- Logic mapping có thể bị trộn với code điều khiển.
- Khó phân tích mapping tự động.
- Dễ tạo phụ thuộc thứ tự nếu không thiết kế phase cẩn thận.

### 9.3. Hybrid transformation

Một hệ thống có thể khai báo mapping cơ bản và dùng code cho các bước đặc biệt. Ví dụ:
- Rule declarative tạo node.
- Helper imperative chuyển kiểu hoặc chuẩn hóa dữ liệu.
- Graph pass nối reference.
- Validation pass xác nhận target.

Hybrid thường phù hợp với DSL transformation có cả mapping lặp lại và logic miền phức tạp.

## 10. Phân loại và áp dụng transformation rules

### 10.1. One-to-one mapping

Một source element tạo một target element.

Ví dụ mỗi Step tạo một ExecutionNode. Đây là mapping đơn giản nhất, nhưng vẫn cần trace link và xử lý duplicate ID.

### 10.2. One-to-many mapping

Một source element tạo nhiều target elements.

Ví dụ một transaction trong source tạo begin, body, commit và rollback nodes trong target.

### 10.3. Many-to-one mapping

Nhiều source elements được gộp thành một target element.

Ví dụ các property trong source được gom thành một target configuration object.

### 10.4. Many-to-many mapping

Một nhóm source node có thể tạo một nhóm target node. Ví dụ class model với inheritance, association và method có thể được chuyển thành nhiều bảng, khóa ngoại và constraint.

Mapping phức tạp thường cần match pattern trên cả nhóm node, không thể chỉ viết một rule độc lập cho từng node.

### 10.5. Rule ordering

Nếu nhiều rule cùng match một phần tử, cần quy định:
- Có áp dụng tất cả rule không?
- Có priority không?
- Rule nào tạo node trước?
- Rule sau có nhìn thấy kết quả của rule trước không?
- Có thể áp dụng lại một rule không?
- Điều gì xảy ra nếu hai rule ghi cùng target property?

Không có chính sách ordering rõ ràng, kết quả có thể phụ thuộc thứ tự duyệt hoặc implementation.

## 11. Match, guard và conflict resolution

### 11.1. Pattern matching

Engine tìm các tập node phù hợp source pattern. Một match có thể bao gồm một node hoặc một tuple node cùng quan hệ.

Ví dụ pattern:
- Một Step.
- Step có action kiểu ServiceCall.
- Step có next đến một Step khác.
- Hai step thuộc cùng Workflow.

### 11.2. Guard

Sau khi tìm match, engine đánh giá guard để quyết định áp dụng rule. Guard nên:
- Có kết quả xác định.
- Không thay đổi model nếu có thể.
- Có diagnostics khi thiếu dữ liệu bắt buộc.
- Được đánh giá trong context đã xác định.

### 11.3. Conflict

Hai rule có thể cùng tạo hoặc cập nhật một target element. Các chiến lược thường gặp:
- Từ chối conflict và phát lỗi.
- Dùng priority.
- Gộp thay đổi nếu các binding tương thích.
- Chọn một rule theo chính sách rõ ràng.
- Yêu cầu người dùng giải quyết.

Không nên giải quyết conflict bằng cách tùy tiện lấy rule chạy cuối cùng nếu điều đó không được đặc tả.

## 12. Tính kết thúc, tính xác định và tính hợp lưu

### 12.1. Termination

Một transformation kết thúc nếu engine hoàn thành sau số bước hữu hạn. Nếu rule được áp dụng lặp đến khi không còn match, có thể xảy ra vòng lặp vô hạn.

Ví dụ rule liên tục thêm một node mới mà node đó lại thỏa điều kiện để thêm node khác. Cần bảo đảm một trong các điều kiện:
- Mỗi rule chỉ áp dụng một lần trên mỗi match.
- Có measure giảm nghiêm ngặt sau mỗi lần áp dụng.
- Có giới hạn số lượt hoặc số node.
- Có cơ chế phát hiện trạng thái lặp.
- Transformation được chứng minh kết thúc theo semantics của nó.

### 12.2. Determinism

Transformation có tính xác định nếu cùng source model, cùng context và cùng version rules tạo cùng target model quan sát được.

Nguồn gây không xác định:
- Duyệt collection không có thứ tự.
- Nhiều rule có thể áp dụng theo thứ tự khác nhau.
- Giá trị thời gian hoặc random.
- Truy vấn dữ liệu ngoài thay đổi.
- Conflict được giải quyết không ổn định.
- Sinh ID dựa trên thời điểm hoặc số ngẫu nhiên.

Nếu cần reproducibility, hãy quy định thứ tự, cố định input ngoài, dùng ID ổn định và lưu transformation version.

### 12.3. Confluence

Một hệ thống rule có tính hợp lưu (*confluence*) nếu các thứ tự áp dụng khác nhau vẫn có thể dẫn đến cùng một kết quả chuẩn hóa hoặc kết quả tương đương theo định nghĩa.

Confluence giúp giảm phụ thuộc vào scheduling của engine. Tuy nhiên, không phải transformation nào cũng cần confluence; có thể thay bằng thứ tự rule xác định và công bố rõ.

### 12.4. Idempotence

Transformation T là idempotent nếu áp dụng nhiều lần không làm thay đổi kết quả sau lần đầu:

~~~text
T(T(M)) = T(M)
~~~

Tính chất này hữu ích khi pipeline có thể retry hoặc chạy lại sau lỗi. Một transformation tạo thêm node mới mỗi lần chạy mà không nhận diện node đã tồn tại sẽ không idempotent và có thể làm target bị nhân đôi.

Để đạt idempotence, có thể dùng stable IDs, trace map, upsert theo khóa hoặc so sánh target hiện tại trước khi tạo phần tử mới.

## 13. Bảo toàn ngữ nghĩa và consistency

### 13.1. Semantic preservation

Một phép biến đổi đúng cần bảo toàn những hành vi mà đặc tả yêu cầu. Ví dụ, chuyển workflow DSL sang execution model phải giữ:
- Điểm bắt đầu.
- Quan hệ thứ tự.
- Điều kiện chuyển tiếp.
- Tham số hành động.
- Hành vi lỗi và retry.
- Các side effect quan sát được.

Không nhất thiết mọi chi tiết source đều xuất hiện nguyên dạng trong target. Một số thông tin có thể được loại bỏ nếu không cần cho mục tiêu đích, nhưng việc mất thông tin phải được xác định.

### 13.2. Preconditions và postconditions

Có thể mô tả transformation bằng hợp đồng:

~~~text
Precondition:
    source conforms to WorkflowMetamodel
    all referenced steps are resolvable

Transformation:
    transformWorkflow(source)

Postcondition:
    target conforms to ExecutionMetamodel
    each enabled source step has a trace mapping
    all target edges reference existing target nodes
~~~

Precondition xác định source cần thỏa điều gì. Postcondition xác định target và trace cần thỏa điều gì sau biến đổi.

### 13.3. Consistency giữa nhiều model

Một source model và target model có thể phải duy trì quan hệ consistency. Ví dụ, nếu source step được bật thì target execution node tương ứng phải tồn tại; nếu source action đổi loại, target operation phải được cập nhật.

Consistency rule có thể được đánh giá:
- Sau mỗi transformation.
- Sau mỗi thay đổi source.
- Trước khi publish target.
- Theo chu kỳ trong hệ thống đồng bộ.

### 13.4. Lossy transformation

Một phép biến đổi có thể làm mất thông tin. Ví dụ target SQL schema không có khái niệm tương ứng với một số constraint nghiệp vụ trong source DSL.

Cần:
- Ghi rõ thông tin nào bị loại bỏ.
- Phát warning hoặc error khi mất thông tin quan trọng.
- Lưu trace hoặc annotation nếu cần truy ngược.
- Không tuyên bố hai mô hình tương đương nếu chỉ bảo toàn một phần semantics.

## 14. Bidirectional transformation và model synchronization

### 14.1. Bài toán hai chiều

Giả sử một DSL có model nghiệp vụ và model triển khai. Người dùng có thể sửa source hoặc target. Hệ thống cần cập nhật phía còn lại để duy trì consistency.

Ví dụ:
- Source định nghĩa timeout là 5 giây.
- Target deployment model cũng lưu timeout 5 giây.
- Người dùng đổi timeout trong target thành 10 giây.
- Hệ thống cần quyết định có cập nhật source, từ chối thay đổi hay tạo conflict.

### 14.2. View và source

Một cách mô hình hóa là xem target như view được tạo từ source. Bidirectional transformation thường có hai thao tác khái niệm:
- **Get:** tạo view từ source.
- **Put:** cập nhật source dựa trên source cũ và view đã chỉnh sửa.

Để tránh thay đổi không mong muốn, Put cần biết source trước đó, view cũ và view mới. Nếu chỉ có view mới, có thể không đủ thông tin để suy ra thay đổi cần áp dụng.

### 14.3. Lens laws

Trong lý thuyết bidirectional transformation, một số luật thường được dùng để mô tả tính nhất quán của get/put. Hai luật trực giác:

- **Get-Put:** nếu tạo view rồi ghi lại chính view đó, source không nên thay đổi.
- **Put-Get:** nếu cập nhật source bằng view mới, tạo view lại phải cho kết quả view mới theo phạm vi được hỗ trợ.

Các luật cụ thể phụ thuộc mô hình lens và cách xử lý phần thông tin không xuất hiện trong view.

### 14.4. Conflict resolution

Khi source và target cùng thay đổi, có thể:
- Ưu tiên source.
- Ưu tiên target.
- Từ chối tự động và yêu cầu giải quyết.
- Merge nếu các thay đổi độc lập.
- Áp dụng policy theo thuộc tính hoặc loại node.

Cần lưu provenance và version để xác định thay đổi nào xảy ra trước và phần nào do người dùng sửa.

## 15. Incremental model transformation

Với model lớn, chạy lại toàn bộ transformation sau mỗi thay đổi có thể tốn kém. Incremental transformation chỉ cập nhật phần target bị ảnh hưởng.

### 15.1. Dependency tracking

Engine cần biết:
- Target element được tạo từ source element nào.
- Rule nào đã tạo hoặc cập nhật element.
- Guard phụ thuộc vào thuộc tính source nào.
- Relation nào ảnh hưởng mapping.
- Thay đổi metamodel hoặc rule version làm mất hiệu lực phần nào.

Trace links là một phần quan trọng của dependency tracking.

### 15.2. Quy trình cập nhật incremental

1. Nhận source change event.
2. Xác định source node và thuộc tính bị thay đổi.
3. Tìm transformation rules phụ thuộc vào thay đổi.
4. Tìm target elements liên quan qua trace map.
5. Tính toán phần target cần xóa, cập nhật hoặc tạo mới.
6. Kiểm tra các reference và invariant bị ảnh hưởng.
7. Commit target delta nếu hợp lệ.
8. Cập nhật trace và dependency index.

### 15.3. Invalidation

Nếu đổi tên một Step, có thể cần cập nhật:
- Target node ID.
- Các edge trỏ đến node đó.
- Entry point nếu step là start.
- Trace mapping.
- Diagnostics và source mapping.

Không chỉ cập nhật target node mang tên cũ. Cần invalidation các phụ thuộc có thể bị ảnh hưởng.

### 15.4. Khi nào nên dùng incremental transformation?

Nó phù hợp với editor, model repository lớn hoặc hệ thống đồng bộ liên tục. Với model nhỏ hoặc transformation chạy ít lần, chạy lại toàn bộ có thể đơn giản và đáng tin cậy hơn.

Incremental transformation làm tăng độ phức tạp cache và dependency. Nên có full transformation làm cách tham chiếu để so sánh kết quả incremental khi cần.

## 16. Validation và diagnostics trong transformation

### 16.1. Source validation

Kiểm tra:
- Source model conforms to metamodel.
- Reference đã resolve.
- Các constraint cần thiết được thỏa.
- Các thuộc tính bắt buộc cho target có giá trị.
- Transformation preconditions đúng.

### 16.2. Transformation diagnostics

Lỗi có thể xảy ra khi:
- Không tìm thấy mapping cho source node.
- Hai rule tạo cùng target key.
- Guard thiếu dữ liệu.
- Một source value không chuyển được sang target type.
- Target reference trỏ đến phần tử chưa tạo.
- Transformation gặp cycle hoặc không kết thúc.
- Một quan hệ source không có biểu diễn trong target.

Diagnostic nên chứa:
- Transformation rule ID.
- Source element và source location.
- Target element nếu đã được tạo.
- Mã lỗi và severity.
- Nguyên nhân và gợi ý sửa.
- Trace link hoặc match context liên quan.

### 16.3. Target validation

Sau khi biến đổi, target cần được kiểm tra độc lập:
- Đúng metamodel.
- Reference target tồn tại.
- Cardinality hợp lệ.
- Constraint và invariant được thỏa.
- Không còn node hoặc edge dở dang.
- Entry point và dependency graph hợp lệ.

### 16.4. Partial result

Một engine có thể hỗ trợ partial result để hiển thị phần đã biến đổi thành công dù một số rule thất bại. Tuy nhiên, partial target không nên được publish hoặc thực thi như target hoàn chỉnh nếu chưa thỏa các điều kiện cần thiết.

Cần đánh dấu rõ trạng thái partial và các vùng bị ảnh hưởng bởi lỗi.

## 17. Tổ chức kiến trúc transformation engine

Một kiến trúc khái niệm:

~~~text
Transformation Request
        |
        v
Source Model Loader
        |
        v
Source Validator
        |
        v
Rule Registry / Transformation Plan
        |
        v
Matcher
        |
        v
Rule Executor
        |
        +------> Trace Store
        |
        v
Target Model Builder
        |
        v
Target Validator
        |
        v
Serializer / Next Tool
~~~

Các thành phần có thể gồm:

- **Model loader:** đọc model và metamodel.
- **Validator:** kiểm tra source và target.
- **Rule registry:** quản lý rule và version.
- **Matcher:** tìm các match trong source graph.
- **Executor:** áp dụng rule.
- **Trace store:** lưu quan hệ source-target.
- **Target builder:** tạo và cập nhật target.
- **Diagnostic collector:** thu thập lỗi và warning.
- **Serializer:** lưu hoặc chuyển model sang công cụ tiếp theo.

Không nhất thiết mỗi thành phần phải là service riêng. Một thư viện nhỏ có thể triển khai tất cả trong một process nhưng vẫn nên giữ trách nhiệm rõ.

## 18. Các công nghệ và ngôn ngữ transformation

### 18.1. ATL

ATL (*Atlas Transformation Language*) là một ngôn ngữ dùng cho model-to-model transformation trong hệ sinh thái model-driven engineering. Cách tiếp cận ATL thường mô tả source và target metamodel, rule ánh xạ và các binding tạo target elements.

Khi tìm hiểu hoặc sử dụng ATL, cần xác định phiên bản, runtime và môi trường metamodel cụ thể. Ví dụ và cú pháp phải khớp toolchain đang dùng.

### 18.2. QVT

QVT (*Query/View/Transformation*) là họ đặc tả của OMG cho truy vấn, view và biến đổi mô hình. Các hướng như Relations, Core và Operational có mục tiêu và phong cách khác nhau.

QVT có thể hỗ trợ cách tiếp cận declarative hoặc operational tùy ngôn ngữ con. Việc lựa chọn cần cân nhắc khả năng tool, mức hỗ trợ metamodel và yêu cầu transformation cụ thể.

### 18.3. ETL và transformation framework

Một số framework cung cấp ngôn ngữ hoặc API để:
- Khai báo source/target model.
- Viết rule.
- Duyệt graph.
- Tạo target element.
- Quản lý trace.
- Chạy validation.

Có thể dùng framework có sẵn hoặc viết transformation bằng Java, Kotlin, Python hay ngôn ngữ host. Lựa chọn phụ thuộc hệ sinh thái metamodel, hiệu năng và khả năng bảo trì.

### 18.4. Code generation templates

Nếu target là văn bản hoặc code, template engine có thể sinh output từ model. Tuy nhiên, template generation thường là model-to-text. Khi cần biến đổi cấu trúc model trước khi sinh code, nên có bước model-to-model riêng để logic không bị rải trong template.

## 19. Hiệu năng và khả năng mở rộng

Chi phí transformation phụ thuộc số node, số edge, số rule, số match và cách lookup.

Các điểm thiết kế:
- Dùng index theo ID hoặc tên để resolve nhanh.
- Tránh quét toàn bộ model cho từng source node nếu có thể index.
- Dùng adjacency list cho graph thưa.
- Cache match khi dependency không thay đổi.
- Tách tạo node và nối reference nếu target dependency phức tạp.
- Dùng batch creation khi model API hỗ trợ.
- Giới hạn số match hoặc độ sâu đệ quy khi input không tin cậy.
- Đo memory của source, target và trace store.

Với N node và E edge, một số bước graph traversal có thể chạy O(N + E). Tuy nhiên, pattern matching phức tạp có thể có số match tăng rất nhanh; không nên mặc định toàn bộ transformation là tuyến tính.

## 20. Tính nguyên tử và quản lý lỗi

Nếu transformation cập nhật model tại chỗ, lỗi giữa chừng có thể để lại trạng thái dở dang.

Các chiến lược:
- Tạo target mới rồi chỉ thay thế khi validation thành công.
- Dùng transaction nếu model repository hỗ trợ.
- Ghi thay đổi vào staging area rồi commit.
- Dùng immutable model và tạo phiên bản mới.
- Có rollback hoặc compensation cho các side effect ngoài model.

Với out-of-place transformation, có thể xây target tạm và chỉ publish khi hoàn tất. Với in-place transformation, cần xác định rõ ranh giới transaction và hành vi khi một rule thất bại.

Transformation nên tách các side effect như ghi file, gọi API hoặc cập nhật database khỏi phần tạo model nếu có thể. Điều này giúp chạy thử, kiểm thử và rollback dễ hơn.

## 21. Versioning và migration metamodel

Khi DSL thay đổi, source metamodel hoặc target metamodel có thể thay đổi theo.

Ví dụ:
- Field timeout được đổi tên thành executionTimeout.
- Step được tách thành Action và Trigger.
- Một trạng thái mới được thêm.
- Cardinality từ 0..1 thành 1.
- Một kiểu cũ bị loại bỏ.

Migration transformation cần:
1. Nhận diện metamodel version nguồn.
2. Chọn transformation tương ứng.
3. Ánh xạ các field cũ sang cấu trúc mới.
4. Xử lý dữ liệu không còn tương thích.
5. Giữ trace hoặc migration report.
6. Validate model sau migration.
7. Lưu version đích.

Không nên chạy migration không xác định version vì cùng một tên field có thể mang ý nghĩa khác nhau giữa các phiên bản.

## 22. Kiểm thử model transformation

### 22.1. Unit tests cho rule

Mỗi rule cần test:
- Source match hợp lệ.
- Guard đúng và sai.
- Target element tạo đúng.
- Binding và chuyển kiểu chính xác.
- Trace link được tạo.
- Lỗi khi thiếu thuộc tính hoặc reference.

### 22.2. Integration tests

Kiểm tra toàn pipeline:
- Load source.
- Validate.
- Chạy transformation.
- Validate target.
- Serialize và nạp lại nếu cần.

### 22.3. Golden model tests

Lưu source model và target model kỳ vọng. Sau khi chạy transformation, so sánh cấu trúc model thay vì chỉ so sánh chuỗi serialization nếu thứ tự hoặc formatting không mang ý nghĩa.

### 22.4. Property-based tests

Có thể kiểm tra các thuộc tính chung:
- Mọi target reference đều trỏ đến target element tồn tại.
- Mọi enabled source step có mapping nếu rule quy định.
- ID target là duy nhất.
- Source không bị thay đổi với out-of-place transformation.
- Chạy lại transformation idempotent không tạo node trùng nếu contract yêu cầu.
- Target luôn conforms to target metamodel khi transformation báo thành công.

### 22.5. Round-trip và bidirectional tests

Với transformation hai chiều, kiểm tra các luật consistency như Get-Put và Put-Get theo phạm vi được hỗ trợ. Cần có test cho thay đổi xung đột, phần thông tin không được biểu diễn và merge.

### 22.6. Performance tests

Dùng model nhỏ, trung bình và lớn. Đo:
- Thời gian match.
- Thời gian tạo target.
- Thời gian trace.
- Thời gian validation.
- Peak memory.
- Chi phí incremental update.

## 23. Những sai lầm thường gặp

1. **Bỏ qua metamodel:** rule được viết mà không xác định rõ cấu trúc và version source/target.
2. **Chỉ ánh xạ node, quên edge:** target có đủ phần tử nhưng quan hệ bị mất hoặc trỏ sai.
3. **Không lưu traceability:** khó cập nhật incremental và truy nguồn target.
4. **Không kiểm tra target:** transformation chạy xong nhưng target vi phạm metamodel.
5. **Rule phụ thuộc thứ tự ngầm:** kết quả khác nhau theo thứ tự duyệt.
6. **Không xử lý conflict:** nhiều rule ghi cùng target property.
7. **Transformation không idempotent:** chạy lại tạo node hoặc edge trùng.
8. **Không xác định thông tin mất:** source semantics bị loại bỏ âm thầm.
9. **Trộn mapping với side effect:** khó test và rollback.
10. **Không version transformation:** cùng source model nhưng runtime rule mới tạo kết quả khác mà không truy vết được.
11. **Incremental cache sai:** source thay đổi nhưng target phụ thuộc không được cập nhật.
12. **Coi mọi cycle là lỗi:** một số state machine và workflow cần vòng lặp hợp lệ.

## 24. Quy trình thiết kế và triển khai biến đổi mô hình

Có thể áp dụng quy trình sau:

1. **Xác định mục tiêu:** sinh code, chuyển metamodel, chuẩn hóa, tối ưu, migration hay đồng bộ.
2. **Chọn source và target metamodel:** xác định version và phạm vi model.
3. **Xác định mapping:** liệt kê node, thuộc tính, quan hệ và cardinality tương ứng.
4. **Viết preconditions:** source cần hợp lệ theo điều kiện nào.
5. **Thiết kế transformation rules:** source pattern, guard, target pattern và binding.
6. **Quy định rule ordering và conflict:** bảo đảm kết quả xác định.
7. **Thiết kế traceability:** lưu source-target mapping và transformation version.
8. **Xác định semantics preservation:** hành vi nào phải được giữ, thông tin nào có thể mất.
9. **Chọn execution strategy:** declarative, imperative hoặc hybrid.
10. **Xây target và validate:** kiểm tra metamodel, reference và invariant.
11. **Quản lý transaction và lỗi:** xác định rollback, partial result và publish boundary.
12. **Viết kiểm thử:** unit, integration, golden, property-based, round-trip và performance.
13. **Quản lý version:** version metamodel, transformation rules và target artifacts.
14. **Đo hiệu năng và vận hành:** theo dõi thời gian, bộ nhớ, trace và diagnostics.

Một transformation tốt có mapping dễ giải thích, quy tắc xác định, traceability đầy đủ, target hợp lệ và hành vi có thể tái lập.

## 25. Kết luận

Biến đổi mô hình chuyển một model thành model khác hoặc cập nhật model hiện tại bằng cách áp dụng các quy tắc ánh xạ. Trong DSL, nó thường nối mô hình miền với biểu diễn phục vụ phân tích, sinh code, thực thi, triển khai hoặc migration.

Thiết kế transformation cần xác định source/target metamodel, mapping node và quan hệ, guard, thứ tự rule, traceability, precondition và postcondition. Các thuộc tính như termination, determinism, idempotence, semantic preservation và consistency giúp bảo đảm kết quả đáng tin cậy. Khi kết hợp validation, diagnostics, transaction, versioning và kiểm thử phù hợp, model transformation trở thành một phần có thể kiểm soát và bảo trì của toolchain DSL.

