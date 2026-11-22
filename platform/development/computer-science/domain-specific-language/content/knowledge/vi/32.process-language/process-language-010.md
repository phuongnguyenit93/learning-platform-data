# Trực quan hóa quy trình

## 1. Trực quan hóa quy trình trong DSL là gì?

Trong DSL quy trình (*process-specific language*), người thiết kế mô tả cách một công việc đi qua các bước, điều kiện, sự kiện, nhánh quyết định và trạng thái. Source DSL có thể rất chính xác nhưng khó hình dung khi quy trình có nhiều nhánh, vòng lặp, tác vụ song song hoặc tương tác giữa nhiều vai trò.

**Trực quan hóa quy trình (*process visualization*)** là việc chuyển mô hình quy trình thành biểu diễn đồ họa để người dùng hiểu cấu trúc, đường đi, điều kiện và quan hệ giữa các thành phần. Sơ đồ có thể được tạo tự động từ source DSL, chỉnh sửa bằng giao diện trực quan hoặc đồng bộ hai chiều với mô hình nguồn.

Ví dụ source:

~~~text
process "OrderFulfillment" {
    start
    task "Validate order"
    decision "Payment valid?"
        yes -> task "Reserve stock"
        no  -> task "Reject order"
    task "Ship order"
    end
}
~~~

Có thể biểu diễn thành sơ đồ:

~~~text
          +-------+
          | Start |
          +---+---+
              |
              v
      +---------------+
      | Validate order|
      +-------+-------+
              |
              v
       +--------------+
       |Payment valid?|
       +---+------+---+
          yes     no
           |       |
           v       v
    +-----------+ +-------------+
    |Reserve    | |Reject order |
    |stock      | +------+------+
    +-----+-----+        |
          |              |
          v              v
       +-------------------+
       |     Ship order    |
       +---------+---------+
                 |
                 v
              +-----+
              | End |
              +-----+
~~~

Sơ đồ trên chỉ minh họa cấu trúc. Nếu nhánh no kết thúc quy trình ngay thì nó không được nối tiếp đến Ship order; nếu hai nhánh cùng hội tụ thì mô hình phải thể hiện điểm merge rõ ràng. Diagram cần phản ánh đúng semantics của DSL thay vì chỉ làm đẹp source.

Trực quan hóa giúp:
- Nắm nhanh luồng công việc và các điểm quyết định.
- Nhận biết nhánh, vòng lặp, song song và điểm kết thúc.
- Trao đổi quy trình với người không đọc DSL.
- Phát hiện bước bị cô lập hoặc đường đi không thể tới.
- Điều hướng từ node trên sơ đồ về source.
- Theo dõi execution đang chạy hoặc bị lỗi.
- So sánh các phiên bản quy trình.
- Hỗ trợ tài liệu hóa, review và onboarding.

## 2. Mô hình quy trình và sơ đồ là hai lớp khác nhau

Một quy trình có semantics độc lập với cách nó được vẽ. Mô hình quy trình mô tả điều gì xảy ra và trong điều kiện nào; sơ đồ mô tả cách trình bày các thành phần đó trên mặt phẳng.

Ví dụ, hai sơ đồ có thể sắp xếp node khác nhau nhưng biểu diễn cùng một graph. Ngược lại, hai sơ đồ nhìn gần giống nhau có thể có semantics khác nếu một mũi tên biểu diễn sequence flow còn mũi tên kia biểu diễn data dependency.

Nên phân biệt:

| Lớp | Nội dung |
|---|---|
| Source DSL | Cú pháp người dùng viết |
| Process model | Task, event, gateway, transition và quan hệ |
| Semantic graph | Control flow, data flow, dependency và state transitions |
| Diagram model | Node, edge, label, group, lane và metadata hiển thị |
| Layout | Tọa độ, kích thước, hướng và cách đi dây |
| Renderer | Vẽ diagram thành SVG, canvas hoặc giao diện editor |

Diagram không nên trở thành nguồn duy nhất của semantics nếu DSL source là artifact có thẩm quyền. Tọa độ node có thể được lưu như presentation metadata, nhưng không được nhầm với thứ tự thực thi.

## 3. Các loại quy trình có thể trực quan hóa

### 3.1. Workflow tuần tự

Workflow tuần tự gồm các task được thực hiện theo thứ tự:

~~~text
Start -> Validate -> Approve -> Notify -> End
~~~

Loại này phù hợp với flowchart đơn giản hoặc activity diagram.

### 3.2. Quy trình có điều kiện

Một decision node chọn đường đi theo điều kiện:

~~~text
          +-----------+
          | Check age |
          +-----+-----+
                |
           +----+----+
           | >= 18 ? |
           +----+----+
              /  \
            yes  no
             |    |
             v    v
          Allow  Deny
~~~

Diagram cần thể hiện nhãn trên từng outgoing edge để người đọc hiểu điều kiện nào chọn nhánh.

### 3.3. Quy trình có vòng lặp

Một workflow có thể lặp cho đến khi điều kiện hoàn tất:

~~~text
      +---------+
      | Process |
      +----+----+
           |
           v
      +---------+
      | Done?   |
      +----+----+
        no | yes
           |
       +---+
       |
       +------> Process
~~~

Cần phân biệt vòng lặp có điều kiện, retry khi lỗi và vòng lặp qua nhiều phần tử trong collection. Chúng có thể được vẽ giống nhau nhưng có semantics và giới hạn khác nhau.

### 3.4. Quy trình song song

Một bước có thể tách thành nhiều nhánh đồng thời:

~~~text
             +----------+
             | Start    |
             +----+-----+
                  |
             +----+----+
             | Fork    |
             +--+---+--+
                |   |
          +-----+   +------+
          v                v
     +---------+      +---------+
     | Check   |      | Reserve |
     | credit  |      | stock   |
     +----+----+      +----+----+
          |                |
          +-------+--------+
                  |
             +----+----+
             | Join    |
             +----+----+
                  |
                  v
                End
~~~

Diagram phải thể hiện fork/join semantics. Hai mũi tên đi ra từ một node không tự động có nghĩa là chạy song song; trong DSL, chúng có thể là các lựa chọn thay thế.

### 3.5. State machine

State machine tập trung vào trạng thái và sự kiện chuyển trạng thái:

~~~text
[DRAFT] --submit--> [PENDING]
[PENDING] --approve--> [APPROVED]
[PENDING] --reject--> [REJECTED]
[APPROVED] --ship--> [SHIPPED]
~~~

State diagram phù hợp khi đối tượng nghiệp vụ có lifecycle rõ ràng như đơn hàng, ticket, hợp đồng hoặc yêu cầu phê duyệt.

### 3.6. Quy trình tương tác nhiều vai trò

Khi nhiều bộ phận hoặc hệ thống tham gia, swimlane diagram giúp thể hiện ai chịu trách nhiệm cho mỗi task. Các lane có thể đại diện cho:
- Người dùng.
- Nhân viên vận hành.
- Service backend.
- Hệ thống thanh toán.
- Hệ thống kho.
- Hệ thống bên ngoài.

## 4. Chọn notation phù hợp

Không phải quy trình nào cũng nên dùng cùng một loại diagram.

| Notation | Trọng tâm | Khi phù hợp |
|---|---|---|
| Flowchart | Bước và nhánh điều khiển | Quy trình nhỏ, giải thích nhanh |
| BPMN | Event, task, gateway, participant và message flow | Business process có nhiều vai trò |
| UML Activity Diagram | Activity, control flow, fork/join và partition | Mô tả hoạt động của hệ thống |
| State Machine Diagram | State, event, guard và transition | Lifecycle của một entity |
| Sequence Diagram | Message theo thời gian giữa participant | Tương tác service hoặc actor |
| Data Flow Diagram | Dữ liệu di chuyển và biến đổi | Pipeline hoặc luồng dữ liệu |
| Petri Net | Place, transition và token | Concurrency, synchronization và resource constraints |

### 4.1. Flowchart

Flowchart đơn giản, dễ đọc và thường phù hợp để hiển thị overview. Tuy nhiên, khi có nhiều participant, message event hoặc compensation, flowchart có thể không đủ biểu đạt.

### 4.2. BPMN

BPMN (*Business Process Model and Notation*) cung cấp các khái niệm như:
- Event: start, intermediate và end.
- Activity: task và subprocess.
- Gateway: exclusive, inclusive và parallel.
- Sequence flow.
- Message flow.
- Pool và lane.
- Boundary event.
- Timer, error và compensation.

Nếu DSL dùng semantics gần BPMN, có thể ánh xạ trực tiếp các construct tương ứng. Nếu DSL có semantics riêng, không nên gán tên BPMN cho node chỉ vì hình dạng giống nhau.

### 4.3. UML Activity Diagram

Activity diagram phù hợp để mô tả control flow, object flow, partition, decision/merge và fork/join. Nó thường được dùng cho quy trình ở cấp hệ thống hoặc thuật toán.

### 4.4. State machine diagram

State machine nhấn mạnh trạng thái của một đối tượng, trigger, guard, transition action và entry/exit action. Nó không thay thế workflow diagram nếu mục tiêu là mô tả thứ tự các công việc giữa nhiều actor.

### 4.5. Sequence diagram

Sequence diagram mô tả thông điệp giữa participant theo trục thời gian. Nó hữu ích khi quy trình DSL gọi nhiều service hoặc API và cần thấy thứ tự request/response.

### 4.6. Data flow diagram

Data flow diagram nhấn mạnh nguồn dữ liệu, process, store và sink. Một quy trình có thể có control flow hợp lệ nhưng data flow thiếu input hoặc tạo output không được dùng; hai góc nhìn cần được phân biệt.

### 4.7. Petri net

Petri net biểu diễn trạng thái bằng place, hành động bằng transition và token biểu diễn điều kiện hiện có. Nó có thể mô tả concurrency, synchronization, deadlock và resource sharing. Đây là notation chuyên biệt hơn flowchart và cần giải thích cho người dùng chưa quen.

## 5. Ánh xạ DSL thành diagram

### 5.1. Model-to-view pipeline

Một pipeline thường gồm:

~~~text
DSL Source
    |
    v
Parser / Semantic Analyzer
    |
    v
Process Model
    |
    v
Normalized Semantic Graph
    |
    v
Diagram Projection
    |
    v
Layout Engine
    |
    v
Renderer
    |
    v
Interactive Diagram
~~~

- Parser nhận diện cấu trúc source.
- Semantic analyzer resolve tên, điều kiện và reference.
- Process model biểu diễn các phần tử nghiệp vụ.
- Semantic graph chuẩn hóa quan hệ giữa chúng.
- Diagram projection chọn notation và chuyển semantic element thành diagram element.
- Layout engine tính vị trí và đường nối.
- Renderer hiển thị kết quả.

Tách các bước này giúp thay đổi giao diện mà không phải thay đổi semantics của quy trình.

### 5.2. Node mapping

Mỗi node trong process model có thể ánh xạ thành một hoặc nhiều diagram nodes.

Ví dụ:

| DSL construct | Diagram element |
|---|---|
| start | Start event |
| end | End event |
| task | Task/activity |
| decision | Exclusive gateway |
| parallel | Parallel gateway hoặc fork |
| wait | Timer/intermediate event |
| call process | Subprocess/call activity |
| state | State node |
| transition | Directed edge |
| participant | Pool hoặc lane |

Mapping cần được định nghĩa theo semantics của DSL. Một construct có thể không có hình tương đương trực tiếp trong notation được chọn; khi đó cần custom shape hoặc annotation.

### 5.3. Edge mapping

Các quan hệ thường cần phân biệt:
- Sequence flow: thứ tự điều khiển.
- Conditional flow: cạnh có guard.
- Message flow: trao đổi giữa participant.
- Data dependency: một bước dùng output của bước khác.
- State transition: chuyển từ state này sang state khác.
- Association: liên kết annotation hoặc artifact.

Không nên vẽ tất cả bằng cùng một loại mũi tên vì người đọc có thể hiểu sai ý nghĩa.

### 5.4. Stable element identity

Node và edge cần ID ổn định để:
- Liên kết diagram với source.
- Giữ layout sau khi source đổi.
- Đồng bộ selection.
- Gắn runtime state.
- So sánh phiên bản.
- Lưu comment hoặc review annotation.

Không nên dùng line number làm ID vì việc chèn dòng sẽ làm identity thay đổi. Có thể dùng explicit ID trong DSL, generated stable ID hoặc identity dựa trên model element có quy tắc migration rõ ràng.

## 6. Control flow và data flow

### 6.1. Control flow

Control flow cho biết bước nào có thể thực hiện tiếp theo. Ví dụ task A hoàn tất thì task B bắt đầu, hoặc decision chọn một trong hai nhánh.

Control flow thường được biểu diễn bằng directed edges.

### 6.2. Data flow

Data flow cho biết dữ liệu được tạo, đọc, biến đổi và truyền giữa các bước:

~~~text
[Read Order] --order--> [Validate]
[Validate] --validOrder--> [Approve]
[Approve] --approvalResult--> [Notify]
~~~

Data flow có thể là một graph riêng hoặc được hiển thị như overlay trên process diagram.

### 6.3. Phân biệt control edge và data edge

Một bước có thể gửi dữ liệu đến bước khác nhưng không quyết định thứ tự thực thi; ngược lại, control flow có thể nối hai bước không chia sẻ output trực tiếp.

Diagram cần phân biệt bằng kiểu đường, màu, nhãn hoặc layer. Không chỉ dựa vào màu vì người dùng có thể không phân biệt được màu hoặc in đen trắng.

### 6.4. Data mapping

Với task có input/output mapping, có thể hiển thị:
- Input parameters.
- Output variables.
- Data transformation.
- Data store read/write.
- Schema/type information.

Ở mức overview, chỉ hiển thị tên dữ liệu chính; chi tiết mapping có thể nằm trong properties panel để tránh làm diagram quá tải.

## 7. Decision gateway và điều kiện nhánh

Decision node thể hiện nơi quy trình chọn đường đi.

Ví dụ:

~~~text
decision "Payment status"
    when payment.status == "PAID" -> ship
    when payment.status == "FAILED" -> reject
    otherwise -> retry
~~~

Diagram có thể hiển thị gateway cùng label trên mỗi edge.

### 7.1. Exclusive gateway

Exclusive gateway chọn đúng một nhánh trong số các nhánh hợp lệ. Cần có:
- Điều kiện rõ ràng.
- Quy tắc ưu tiên nếu điều kiện có thể overlap.
- Default branch hoặc hành vi khi không nhánh nào match.

### 7.2. Inclusive gateway

Inclusive gateway có thể chọn một hoặc nhiều nhánh. Nó khác exclusive gateway vì nhiều nhánh có thể cùng được thực hiện. Join tương ứng cần chờ đúng tập nhánh đã được kích hoạt theo semantics của process.

### 7.3. Parallel gateway

Parallel gateway kích hoạt nhiều nhánh đồng thời hoặc đồng bộ các nhánh tại điểm join. Cần biểu diễn fork và join rõ ràng, tránh người đọc hiểu nhầm thành lựa chọn.

### 7.4. Default flow

Một cạnh default có thể được dùng khi không điều kiện nào khác thỏa. Diagram nên đánh dấu cạnh default để người đọc biết đây là fallback.

### 7.5. Guard expression

Điều kiện có thể dài hoặc chứa nhiều predicate. Diagram nên hiển thị label rút gọn và cho phép mở expression đầy đủ trong panel hoặc tooltip. Không nên cắt bỏ nội dung mà không có cách xem chi tiết.

## 8. Event, timer, error và compensation

Quy trình thực tế thường có sự kiện ngoài task thông thường.

### 8.1. Start và end events

Start event xác định điểm bắt đầu một instance. End event xác định cách kết thúc. Có thể có nhiều loại kết thúc:
- Hoàn tất bình thường.
- Kết thúc lỗi.
- Hủy.
- Kết thúc nhánh hoặc subprocess.

Nếu semantics khác nhau, diagram cần dùng icon/shape và label khác nhau.

### 8.2. Intermediate events

Intermediate event xuất hiện giữa quá trình:
- Message received.
- Timer elapsed.
- Signal received.
- Condition became true.
- Error caught.

Chúng giúp thể hiện thời gian chờ và tương tác với hệ thống bên ngoài.

### 8.3. Boundary events

Boundary event gắn với một activity, chẳng hạn timeout hoặc error xảy ra trong lúc task đang chạy. Diagram cần cho biết event interrupting task hay non-interrupting.

### 8.4. Compensation

Compensation mô tả hành động bù trừ khi quy trình đã thực hiện một side effect nhưng sau đó thất bại. Ví dụ đã reserve stock thì khi payment thất bại cần release stock.

Compensation không phải rollback database tự động. Nó là một hành động nghiệp vụ riêng và nên được thể hiện bằng quan hệ hoặc ký hiệu khác với sequence flow thông thường.

### 8.5. Retry

Retry có thể được vẽ như loop, nhưng cần thể hiện:
- Retry trigger.
- Maximum attempts.
- Delay/backoff.
- Retryable error categories.
- Hành động sau khi hết retry.

Một loop vô hạn và retry có giới hạn không nên trông giống nhau mà không có annotation.

## 9. Swimlane, pool và participant

Swimlane diagram phân chia quy trình theo trách nhiệm.

Ví dụ:

~~~text
+----------------------+----------------------+----------------------+
| Customer             | Order Service        | Payment Service      |
+----------------------+----------------------+----------------------+
| Submit order         |                      |                      |
|--------------------->| Validate order       |                      |
|                      | Request payment      |--------------------->|
|                      |                      | Authorize payment    |
|                      |<---------------------| Payment result       |
| Receive confirmation | Complete order       |                      |
+----------------------+----------------------+----------------------+
~~~

### 9.1. Pool và lane

Pool thường đại diện một participant độc lập như tổ chức hoặc process participant. Lane chia trách nhiệm bên trong participant, ví dụ team hoặc service.

### 9.2. Assignment

Mỗi task có thể được gán cho:
- Role.
- User group.
- Department.
- Service.
- External participant.

Diagram cần phân biệt owner, executor và initiator nếu DSL mô hình hóa riêng các vai trò này.

### 9.3. Message flow

Message flow thể hiện trao đổi giữa participant. Nó không giống sequence flow trong cùng một process. Với BPMN-like notation, cần giữ quy tắc nối giữa pool và lane phù hợp.

### 9.4. Lane không đồng nghĩa với thread

Lane biểu diễn trách nhiệm hoặc participant ở mức mô hình. Nó không tự động có nghĩa task chạy trên một thread hoặc process OS riêng. Concurrency phải đến từ semantics của DSL.

## 10. Subprocess và phân cấp quy trình

Quy trình lớn có thể được chia thành subprocess hoặc reusable process.

Diagram overview có thể hiển thị một collapsed subprocess:

~~~text
+--------------------------+
| Process payment          |
|       +-------------+    |
|       | 3 steps ... |    |
|       +-------------+    |
+--------------------------+
~~~

Khi mở rộng, người dùng thấy các bước bên trong.

### 10.1. Collapsed và expanded view

Collapsed view giúp giữ diagram tổng quan dễ đọc. Expanded view cho phép xem chi tiết. Cần giữ cùng process identity giữa hai chế độ.

### 10.2. Call activity

Một process có thể gọi reusable process khác. Diagram cần phân biệt:
- Subprocess inline.
- Call đến process dùng chung.
- Event subprocess.
- Embedded workflow.

### 10.3. Boundary và scope

Subprocess có thể có variable scope, error boundary và transaction boundary riêng. Khi hiển thị chi tiết, cần thể hiện scope để người dùng hiểu dữ liệu và lỗi được xử lý ở đâu.

## 11. Layout engine và bố cục sơ đồ

Sau khi có diagram graph, layout engine tính tọa độ node và đường nối.

### 11.1. Các kiểu layout

| Layout | Đặc điểm | Phù hợp |
|---|---|---|
| Hierarchical / layered | Sắp node theo tầng | Flow từ trái sang phải hoặc trên xuống |
| Tree | Một gốc, nhiều nhánh | Decision tree hoặc phân cấp |
| Force-directed | Node phân tán theo lực | Dependency graph, mạng quan hệ |
| Orthogonal | Edge đi ngang/dọc, góc vuông | Workflow nghiệp vụ |
| Circular | Node theo vòng tròn | Quan hệ tuần hoàn hoặc state overview |
| Manual | Người dùng tự đặt vị trí | Diagram cần bố cục biên tập riêng |

Flowchart thường hợp với hierarchical layout. Dependency graph có thể phù hợp force-directed, nhưng không phải lựa chọn tốt cho mọi workflow vì thứ tự thực thi có thể khó đọc.

### 11.2. Direction

Layout có thể theo:
- Left-to-right.
- Top-to-bottom.
- Right-to-left.
- Bottom-to-top.

Direction nên là cấu hình trình bày. Thay đổi hướng không được làm thay đổi control flow.

### 11.3. Node sizing

Kích thước node có thể phụ thuộc:
- Loại node.
- Label.
- Nội dung annotation.
- Số lượng input/output.
- Expanded/collapsed state.

Nên có min/max size để một label rất dài không làm sơ đồ mất cân đối.

### 11.4. Edge routing

Edge có thể dùng:
- Straight line.
- Orthogonal routing.
- Curved routing.
- Self-loop.
- Bus hoặc shared segment nếu notation hỗ trợ.

Edge routing nên hạn chế giao cắt và tránh đi qua node. Tuy nhiên, không nên làm đường đi phức tạp đến mức người đọc khó lần theo hướng mũi tên.

### 11.5. Crossing reduction

Khi graph lớn, edge có thể giao nhau. Layout engine có thể sắp xếp node và lane để giảm crossing. Không phải mọi crossing đều có thể loại bỏ; cần ưu tiên giữ semantics và thứ tự quan trọng.

### 11.6. Cycles

Workflow có loop nên layout thể hiện rõ cạnh quay lại. Không nên cố ép graph thành DAG nếu chu trình là một phần semantics. Có thể dùng routing riêng cho back-edge hoặc vùng loop.

### 11.7. Deterministic layout

Cùng process model và cùng layout options nên tạo bố cục ổn định nếu có thể. Layout thay đổi ngẫu nhiên gây diff khó review và làm người dùng mất vị trí node sau mỗi lần reload.

## 12. Diagram model và metadata trình bày

Một diagram model có thể chứa:

~~~json
{
  "diagramId": "order-flow",
  "notation": "workflow",
  "direction": "LR",
  "nodes": [
    {
      "id": "validate",
      "semanticId": "task-validate",
      "kind": "task",
      "label": "Validate order",
      "bounds": {"x": 120, "y": 80, "width": 150, "height": 60}
    }
  ],
  "edges": [
    {
      "id": "edge-validate-approve",
      "source": "validate",
      "target": "approve",
      "kind": "sequence",
      "label": "valid"
    }
  ]
}
~~~

Các trường có thể chia thành hai nhóm:

**Semantic metadata**
- Semantic element ID.
- Element kind.
- Source/target reference.
- Guard hoặc event reference.
- Participant/role.
- Data dependency.

**Presentation metadata**
- Bounds và position.
- Label placement.
- Color/theme.
- Collapsed state.
- Routing points.
- Viewport và zoom.

Presentation metadata có thể lưu riêng với process source để người dùng chỉnh bố cục mà không thay đổi hành vi quy trình.

## 13. Tương tác trong DSL editor

Trực quan hóa hữu ích nhất khi người dùng có thể tương tác với diagram.

### 13.1. Selection đồng bộ với source

Khi chọn node trên diagram, editor có thể:
- Mở file DSL tương ứng.
- Đặt cursor tại source range.
- Highlight declaration hoặc block.
- Hiển thị properties của node.

Khi đặt cursor trong source, diagram có thể highlight node tương ứng.

### 13.2. Source mapping

Mỗi semantic element nên giữ source URI và range. Với element sinh ra từ macro hoặc generated process, cần source map về construct gốc.

Một node có thể tương ứng với nhiều source ranges nếu DSL dùng composite construct. Ví dụ một gateway được tạo từ cả declaration và các branch clauses.

### 13.3. Hover và properties panel

Hover có thể hiển thị:
- Tên node.
- Loại task/event/gateway.
- Guard condition.
- Input/output variables.
- Owner hoặc participant.
- Retry/timeout policy.
- Diagnostics.

Properties panel có thể hiển thị đầy đủ và cho phép chỉnh sửa thuộc tính nếu editor hỗ trợ visual editing.

### 13.4. Navigation

Các thao tác hữu ích:
- Go to source.
- Go to called subprocess.
- Find incoming/outgoing flows.
- Highlight path to selected node.
- Show dependencies.
- Open referenced rule hoặc schema.

### 13.5. Zoom, pan và minimap

Với diagram lớn, cần:
- Zoom in/out.
- Pan.
- Fit to screen.
- Zoom to selection.
- Minimap.
- Search node.
- Collapse/expand group.
- Focus mode.

Không nên tự động thay đổi viewport quá mạnh khi người dùng đang chỉnh sửa thủ công.

## 14. Visual editing và đồng bộ hai chiều

Một số editor chỉ render diagram từ DSL source. Một số khác cho phép người dùng kéo thả node và sửa thuộc tính trực tiếp trên diagram.

### 14.1. Text-first

DSL source là nguồn chính. Diagram được tạo từ source và mọi thay đổi semantics phải được thực hiện trong DSL. Cách này dễ bảo đảm tính nhất quán nhưng không phù hợp với người dùng muốn thiết kế bằng kéo thả.

### 14.2. Diagram-first

Diagram model là nguồn chính và DSL có thể được sinh ra. Cần bảo đảm generator tạo source ổn định, có thể round-trip và không làm mất construct mà diagram không biểu diễn.

### 14.3. Dual editing

Người dùng có thể sửa cả source và diagram. Khi đó cần quy tắc đồng bộ:
- Mỗi semantic element có stable identity.
- Diagram edit tạo source edit hoặc model update.
- Source edit cập nhật diagram.
- Xử lý conflict khi hai bên cùng sửa.
- Giữ layout khi graph không thay đổi đáng kể.
- Báo rõ khi một construct không thể biểu diễn trực quan.

### 14.4. Round-trip fidelity

Round-trip là khả năng chuyển từ source sang diagram rồi quay lại mà không làm mất semantics.

Cần phân biệt:
- Semantic round-trip: model vẫn giữ cùng meaning.
- Syntactic round-trip: source có thể thay đổi formatting nhưng parse ra model tương đương.
- Presentation round-trip: vị trí và layout được giữ.
- Lossless round-trip: mọi thông tin source và annotation được giữ.

Không phải notation nào cũng biểu diễn đầy đủ mọi construct của DSL. Nếu có construct không được hỗ trợ, editor cần hiển thị opaque/custom node hoặc cảnh báo thay vì bỏ qua.

### 14.5. Conflict khi chỉnh sửa hai phía

Nếu source và diagram thay đổi cùng lúc:
1. Ghi nhận document/model version.
2. Xác định semantic element bị sửa.
3. Tính phần thay đổi độc lập.
4. Merge nếu không xung đột.
5. Đánh dấu conflict nếu cùng field hoặc relation bị thay đổi khác nhau.
6. Cho người dùng chọn hoặc hợp nhất có kiểm soát.

Không nên âm thầm ghi đè thay đổi của một phía.

## 15. Validation và diagnostics trên diagram

Diagram có thể là bề mặt hiển thị diagnostics từ parser và semantic analyzer.

Một số lỗi có thể biểu diễn trực quan:
- Node không có incoming flow.
- Node không thể tới từ start.
- End event không thể tới được.
- Gateway thiếu default branch.
- Branch condition overlap.
- Join không khớp với fork.
- Deadlock hoặc state không có transition ra.
- Subprocess reference không tồn tại.
- Data input không được tạo.
- Task output không được dùng.

### 15.1. Syntax diagnostics

Lỗi cú pháp thường gắn với source range. Diagram có thể đánh dấu node hoặc vùng chứa construct bị lỗi nếu parser recovery tạo được model tạm.

### 15.2. Semantic diagnostics

Ví dụ task tham chiếu service không tồn tại, transition đi đến state chưa khai báo hoặc gateway thiếu nhánh mặc định. Diagnostic nên gắn với element và source range.

### 15.3. Graph validation

Một số kiểm tra cần toàn graph:
- Reachability từ start.
- Dead-end.
- Unreachable task.
- Cycle không có exit.
- Gateway degree constraints.
- Join/fork balance.
- Missing start/end.
- Unused node.
- Data dependency cycle.

Không phải mọi cycle đều sai; vòng lặp có thể hợp lệ nếu có điều kiện thoát. Validation cần hiểu loại node và semantics.

### 15.4. Diagnostic presentation

Có thể dùng:
- Error/warning icon trên node.
- Edge highlight.
- Marker trong minimap.
- Problems panel.
- Tooltip với message và quick navigation.

Màu sắc nên đi kèm icon hoặc label để người dùng không phụ thuộc riêng vào màu.

## 16. Trực quan hóa execution tại runtime

Ngoài static diagram, editor có thể hiển thị execution overlay để thấy quy trình đang chạy đến đâu.

Ví dụ:
- Node đã hoàn tất.
- Node đang chạy.
- Node đang chờ.
- Node bị bỏ qua.
- Node thất bại.
- Edge đã được đi qua.
- Nhánh được chọn.
- Thời gian thực thi.
- Retry count.

### 16.1. Runtime event mapping

Runtime event cần chứa process ID, process version, instance ID và semantic node ID. Diagram renderer dùng các ID đó để highlight đúng node.

Nếu chỉ dựa trên node label, hai task cùng tên có thể bị highlight nhầm.

### 16.2. Execution state

Một state model có thể gồm:

| State | Hiển thị |
|---|---|
| Pending | Chưa được kích hoạt |
| Ready | Đủ điều kiện chạy |
| Running | Đang thực thi |
| Completed | Hoàn tất |
| Failed | Thất bại |
| Skipped | Bị bỏ qua |
| Cancelled | Bị hủy |
| Waiting | Đang chờ event hoặc timer |
| Compensating | Đang chạy hành động bù |

State cụ thể phụ thuộc runtime. Không nên ánh xạ mọi trạng thái về chỉ hai màu success/failure vì sẽ mất thông tin quan trọng.

### 16.3. Path highlighting

Có thể highlight đường đi thực tế qua diagram:
- Edge đã đi qua.
- Gateway branch đã chọn.
- Node đang chờ.
- Nhánh không được chọn.

Với parallel flow, nhiều path có thể hoạt động đồng thời. Renderer cần thể hiện concurrency thay vì ép thành một đường tuần tự.

### 16.4. Timeline và duration

Kết hợp diagram với timeline giúp thấy:
- Thời điểm node bắt đầu/kết thúc.
- Thời gian chờ.
- Task chạy lâu.
- Retry.
- Overlap giữa các nhánh song song.

Duration nên phân biệt execution time và waiting time nếu runtime cung cấp cả hai.

### 16.5. Historical execution

Khi xem execution cũ, diagram phải dùng đúng process version đã chạy. Nếu source hiện tại đã đổi, không được gắn trace cũ lên graph mới mà không có version mapping.

## 17. Collaboration, review và version comparison

Diagram hỗ trợ trao đổi và review quy trình.

### 17.1. Review annotation

Người review có thể gắn comment vào:
- Node.
- Edge.
- Gateway condition.
- Lane.
- Subprocess.
- Vùng diagram.

Annotation nên gắn với stable semantic ID thay vì chỉ tọa độ màn hình.

### 17.2. Version diff

So sánh hai phiên bản có thể highlight:
- Node được thêm hoặc xóa.
- Edge được thêm hoặc xóa.
- Guard condition thay đổi.
- Task được chuyển lane.
- Timeout/retry policy đổi.
- Subprocess reference đổi.
- Layout chỉ thay đổi.

Nên phân biệt semantic diff với layout-only diff. Di chuyển node trên canvas không nhất thiết là thay đổi logic.

### 17.3. Concurrent editing

Nếu nhiều người chỉnh sửa cùng diagram, cần versioning hoặc collaboration protocol. Có thể dùng optimistic locking, operation transformation hoặc CRDT tùy mô hình dữ liệu.

Các operation cần giữ semantics như add node, connect edge, update guard và move node. Không phải mọi thao tác hình học đều có thể merge đơn giản.

### 17.4. Reviewability

Một diagram diff tốt nên cho biết vì sao thay đổi ảnh hưởng đến đường đi hoặc trạng thái. Ví dụ thêm một branch mới vào gateway cần được thể hiện cùng guard và target, không chỉ một node mới.

## 18. Accessibility và khả năng đọc

Diagram không nên chỉ truyền thông tin qua màu sắc hoặc vị trí.

Các nguyên tắc:
- Có text label cho node và edge quan trọng.
- Dùng icon kèm chữ cho event/state.
- Tương phản đủ giữa text và background.
- Hỗ trợ keyboard navigation.
- Có accessible name cho node và control.
- Có alternative textual representation.
- Không dùng màu duy nhất để biểu thị trạng thái.
- Cho phép zoom và scale text.
- Đảm bảo thứ tự focus hợp lý.
- Có chế độ high contrast nếu editor hỗ trợ.

Một process có thể cung cấp outline dạng cây hoặc danh sách bước để người dùng screen reader truy cập nội dung mà không cần đọc canvas trực quan.

## 19. Security và giới hạn hiển thị

Diagram có thể tiết lộ tên service, endpoint, participant, business rule hoặc thông tin vận hành.

Cần:
- Áp dụng quyền truy cập cho từng process và subprocess.
- Không render secret raw trong label hoặc tooltip.
- Redact dữ liệu runtime nhạy cảm.
- Kiểm soát export và chia sẻ diagram.
- Kiểm tra quyền khi mở referenced subprocess.
- Không để source mapping tiết lộ file ngoài workspace.
- Escape label do người dùng cung cấp.
- Giới hạn graph size và nested depth khi render dữ liệu không tin cậy.

Nếu một user không có quyền xem subprocess, diagram có thể hiển thị node placeholder theo policy thay vì tiết lộ tên và nội dung bên trong.

## 20. Hiệu năng và diagram lớn

Diagram có hàng nghìn node cần chiến lược hiển thị riêng.

Các kỹ thuật:
- Virtualization: chỉ render node trong viewport và vùng lân cận.
- Collapsed subprocess: ẩn chi tiết không cần thiết.
- Lazy loading: chỉ tải subgraph khi mở rộng.
- Incremental layout: chỉ bố trí phần graph thay đổi.
- Caching: cache layout theo model version và options.
- Search/index: tìm node theo ID, label hoặc type.
- Edge bundling: gom cạnh khi phù hợp và không làm mất semantics.
- Level of detail: giảm chi tiết khi zoom out.
- Cancellation: hủy layout/render job cũ khi model thay đổi.

### 20.1. Layout latency

Nên đo thời gian:
- Parse và semantic analysis.
- Graph projection.
- Layout computation.
- SVG/canvas rendering.
- Runtime overlay update.

Tách các giai đoạn giúp xác định bottleneck. Một layout algorithm tốt nhưng renderer vẽ quá nhiều DOM node vẫn có thể làm editor chậm.

### 20.2. Incremental update

Khi một task được đổi label, có thể chỉ cần update node bounds và layout cục bộ. Khi một gateway hoặc edge thay đổi topology, có thể cần chạy layout lại trên vùng lớn hơn.

Cần có invalidation policy để cache không giữ diagram cũ.

### 20.3. Graph complexity

Một số graph có nhiều crossing, nested loops hoặc edge dài có thể khiến layout khó. Có thể cho phép người dùng chuyển sang overview, focus subgraph hoặc dùng layout thủ công.

## 21. Export và tài liệu hóa

Diagram có thể được xuất để review, chia sẻ hoặc lưu hồ sơ.

Định dạng thường gặp:
- SVG: vector, phù hợp hiển thị web và phóng to.
- PNG: ảnh raster dễ nhúng vào tài liệu.
- PDF: tài liệu in hoặc lưu trữ.
- BPMN XML: trao đổi với công cụ hỗ trợ BPMN.
- Graph/JSON model: tích hợp với tool khác.
- Mermaid hoặc PlantUML text: tài liệu kỹ thuật khi semantics phù hợp.

### 21.1. Export fidelity

Cần xác định:
- Export toàn diagram hay viewport.
- Có bao gồm lane, legend và annotations không.
- Font có được embed hoặc thay thế không.
- Link và metadata có được giữ không.
- Có redaction theo quyền người xuất không.

### 21.2. Interchange format

Không phải mọi DSL đều có thể chuyển lossless sang BPMN hoặc UML. Khi export, cần báo construct nào được ánh xạ trực tiếp, construct nào thành extension/custom element và construct nào không được hỗ trợ.

### 21.3. Print layout

Diagram lớn có thể cần:
- Chia trang.
- Scale-to-fit.
- Page orientation.
- Header/footer.
- Legend.
- Process version và timestamp.
- Chú thích trạng thái.

## 22. Kiến trúc thành phần trực quan hóa

Một kiến trúc khái niệm:

~~~text
DSL Editor
    |
    v
Document / Semantic Model
    |
    v
Process Graph Service
    |
    +----> Validation and Diagnostics
    |
    +----> Source Mapping
    |
    +----> Runtime Event Adapter
    |
    v
Diagram Projection
    |
    v
Layout Engine
    |
    v
Renderer / Interaction Layer
    |
    +----> Selection and Navigation
    +----> Properties Panel
    +----> Execution Overlay
    +----> Export
~~~

### 22.1. Process graph service

Chuyển domain model thành graph chuẩn hóa gồm node, edge, participant, data dependency và metadata. Graph service không nên phụ thuộc vào SVG hoặc canvas.

### 22.2. Diagram projection

Chọn phần tử nào hiển thị, loại notation và cách nhóm node. Một semantic model có thể có nhiều projection:
- Overview flowchart.
- BPMN view.
- State view.
- Data flow view.
- Runtime execution view.

### 22.3. Layout engine

Nhận graph và layout options, trả bounds và edge routes. Engine không được tự thay đổi graph semantics.

### 22.4. Renderer

Vẽ diagram và quản lý hit testing, selection, zoom, pan và accessibility. Có thể dùng SVG, canvas hoặc WebGL tùy kích thước và yêu cầu tương tác.

### 22.5. Runtime adapter

Chuyển runtime events thành trạng thái node/edge dựa trên semantic IDs và process version.

## 23. Kiểm thử trực quan hóa quy trình

### 23.1. Semantic mapping tests

Với mỗi DSL construct, xác nhận mapping đúng:
- Task thành activity.
- Decision thành gateway.
- Branch thành edge có guard.
- Parallel construct thành fork/join phù hợp.
- State transition thành directed transition.
- Subprocess thành node có reference đúng.

### 23.2. Graph integrity tests

Kiểm tra:
- Edge source và target tồn tại.
- ID không trùng.
- Không có reference dangling.
- Start/end semantics hợp lệ.
- Gateway constraints được thỏa.
- Source mapping trỏ đúng node.
- Data dependency không bị nhầm với control flow.

### 23.3. Layout tests

Kiểm tra:
- Node bounds không bị NaN hoặc âm.
- Node không chồng lấn ngoài policy.
- Edge có endpoint đúng.
- Layout ổn định cho cùng input/options.
- Cycles vẫn được biểu diễn.
- Text không bị cắt không có cách xem đầy đủ.

Có thể dùng snapshot tests cho renderer, nhưng cần tránh để test phụ thuộc quá mức vào pixel khi layout engine có thay đổi hợp lệ.

### 23.4. Interaction tests

Kiểm tra:
- Chọn node mở đúng source.
- Cursor trong source highlight đúng node.
- Hover hiển thị properties đúng.
- Zoom/pan không làm mất selection.
- Collapse/expand giữ semantic identity.
- Search đưa đến node đúng.
- Keyboard navigation hoạt động.

### 23.5. Runtime overlay tests

Kiểm tra event mapping theo:
- Process version.
- Instance ID.
- Node ID.
- Retry attempt.
- Parallel branches.
- Failed/cancelled/waiting states.

Execution cũ không được gắn nhầm lên process version mới.

### 23.6. Round-trip tests

Nếu hỗ trợ visual editing, kiểm tra:
1. Parse DSL thành model.
2. Render diagram.
3. Chỉnh sửa node/edge.
4. Sinh hoặc cập nhật source.
5. Parse lại source.
6. So sánh semantics và stable IDs.

### 23.7. Accessibility và security tests

Kiểm tra accessible labels, keyboard navigation, contrast policy, redaction và quyền truy cập subprocess. Export cũng phải tuân thủ cùng access policy.

## 24. Những sai lầm thường gặp

1. **Vẽ trực tiếp từ text bằng regex:** không hiểu semantics và dễ tạo edge sai.
2. **Đồng nhất diagram với process model:** layout change vô tình làm thay đổi logic.
3. **Dùng một loại edge cho mọi quan hệ:** nhầm control flow với data/message flow.
4. **Không có stable IDs:** source mapping và runtime highlighting bị mất sau khi sửa file.
5. **Bỏ qua branch conditions:** sơ đồ cho thấy nhánh nhưng không giải thích khi nào được chọn.
6. **Vẽ song song như lựa chọn:** người đọc hiểu sai fork/join.
7. **Không thể hiện loop exit:** khó biết quy trình có thể kết thúc hay không.
8. **Dùng notation không đủ semantics:** construct bị mất hoặc bị diễn giải sai.
9. **Layout không ổn định:** diagram nhảy vị trí sau mỗi lần reload.
10. **Không hỗ trợ source navigation:** diagram tách rời DSL source.
11. **Gắn runtime trace theo label:** task trùng tên bị highlight nhầm.
12. **Coi lane là thread:** nhầm trách nhiệm với concurrency.
13. **Không phân biệt semantic diff và layout diff:** review bị nhiễu.
14. **Không xử lý access control khi export:** diagram tiết lộ thông tin nội bộ.
15. **Không hỗ trợ keyboard/screen reader:** một nhóm người dùng không thể truy cập diagram.
16. **Render toàn bộ graph lớn:** editor chậm và khó điều hướng.

## 25. Quy trình triển khai trực quan hóa quy trình

Có thể triển khai theo các bước:

1. **Xác định use case:** overview, thiết kế quy trình, review, debugging hay theo dõi runtime.
2. **Định nghĩa process metamodel:** task, event, gateway, transition, participant, data và subprocess.
3. **Xác định semantics của edge:** sequence, conditional, message, data dependency và state transition.
4. **Xây parser/semantic model:** tạo graph từ DSL source và resolve reference.
5. **Thiết kế notation mapping:** chọn flowchart, BPMN, activity, state hoặc sequence view.
6. **Tạo stable identity và source mapping:** liên kết node/edge với source range và runtime ID.
7. **Xây diagram projection:** chọn phần tử hiển thị và group/lane.
8. **Tích hợp layout engine:** direction, routing, crossing reduction và deterministic output.
9. **Xây renderer:** node, edge, labels, zoom, pan, minimap và selection.
10. **Tích hợp editor:** source navigation, properties, hover và visual editing nếu cần.
11. **Hiển thị diagnostics:** graph validation, unreachable node, invalid gateway và data dependency.
12. **Tích hợp runtime overlay:** execution state, path, timing và retry.
13. **Thiết kế version diff và collaboration:** semantic changes, layout changes và annotation.
14. **Áp dụng accessibility/security:** keyboard, labels, redaction và access control.
15. **Hỗ trợ export:** SVG, PNG, PDF và interchange format theo khả năng semantics.
16. **Kiểm thử:** mapping, graph integrity, layout, interaction, runtime overlay và round-trip.
17. **Đo hiệu năng:** graph lớn, incremental layout, rendering và memory.

Nên bắt đầu với một notation đơn giản phản ánh đúng construct cốt lõi của DSL, rồi mở rộng khi có nhu cầu cụ thể. Một sơ đồ ít chi tiết nhưng đúng semantics có giá trị hơn một sơ đồ đẹp nhưng làm người dùng hiểu sai quy trình.

## 26. Kết luận

Trực quan hóa quy trình chuyển process model của DSL thành sơ đồ giúp người dùng hiểu các task, event, gateway, nhánh, vòng lặp, participant và quan hệ dữ liệu. Chất lượng của diagram phụ thuộc vào việc giữ đúng semantics, phân biệt control flow với data/message flow và chọn notation phù hợp với mục tiêu.

Một triển khai tốt tách process model khỏi diagram layout, dùng stable IDs và source mapping, hỗ trợ navigation hai chiều, validation, runtime highlighting, version diff, accessibility và access control. Layout cần ổn định và có thể mở rộng cho graph lớn; visual editing cần có quy tắc đồng bộ và round-trip rõ ràng. Khi diagram phản ánh chính xác source và runtime, nó trở thành công cụ thiết kế, giao tiếp và vận hành quy trình thay vì chỉ là hình minh họa.

