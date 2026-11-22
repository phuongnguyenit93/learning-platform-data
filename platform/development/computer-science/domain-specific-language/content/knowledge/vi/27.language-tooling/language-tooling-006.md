# Trình trực quan hóa

## 1. Trình trực quan hóa trong công cụ DSL

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường biểu diễn những khái niệm như quy trình, luồng dữ liệu, tài nguyên, chính sách, quan hệ phụ thuộc hoặc cấu hình hệ thống. Khi chương trình DSL lớn dần, chỉ đọc văn bản nguồn có thể không đủ để hiểu cấu trúc, luồng điều khiển và cách các thành phần liên kết với nhau.

**Trình trực quan hóa (visualizer)** là công cụ chuyển thông tin của DSL hoặc các biểu diễn nội bộ của nó thành hình ảnh có cấu trúc để người dùng quan sát, khám phá và phân tích. Tùy mục tiêu, visualizer có thể hiển thị cây cú pháp, đồ thị phụ thuộc, sơ đồ luồng dữ liệu, kế hoạch thực thi, schema, trạng thái runtime hoặc lịch sử biến đổi.

Ví dụ, một workflow DSL:

~~~text
workflow "daily-report" {
    task load_orders {
        read "orders.csv"
    }

    task load_customers {
        read "customers.csv"
    }

    task build_report {
        depends_on load_orders
        depends_on load_customers
        join_data
        write "report.csv"
    }
}
~~~

Văn bản cho biết build_report phụ thuộc vào hai tác vụ đọc dữ liệu. Visualizer có thể trình bày quan hệ đó thành đồ thị:

~~~text
Load Orders --------\
                     > Build Report
Load Customers -----/
~~~

Người dùng có thể nhanh chóng nhận ra hai tác vụ đầu độc lập và tác vụ cuối chỉ chạy khi cả hai hoàn tất. Nếu sơ đồ cho phép chọn node để mở vị trí nguồn, người dùng còn có thể đi từ hình ảnh về đúng câu lệnh DSL.

Visualizer không chỉ nhằm làm giao diện đẹp hơn. Nó là một cách biểu diễn khác của cùng mô hình ngôn ngữ, giúp người dùng hiểu cấu trúc phức tạp, tìm lỗi, giải thích quyết định của compiler và quan sát hành vi thực thi.

## 2. Mục tiêu và người dùng

Visualizer có thể phục vụ nhiều nhóm người dùng:

- Người viết DSL muốn hiểu chương trình và phát hiện cấu trúc sai.
- Kỹ sư compiler muốn xem AST, IR, CFG và kết quả tối ưu hóa.
- Người vận hành muốn quan sát task, trạng thái và tài nguyên khi chạy.
- Người thiết kế workflow muốn xem dependency và critical path.
- Người quản trị muốn xem policy, quyền truy cập và quan hệ tài nguyên.
- Người hỗ trợ muốn giải thích một cấu hình hoặc lỗi cho người khác.

Các mục tiêu thường gặp:

1. **Hiểu cấu trúc:** trình bày cây, block, module hoặc thành phần lồng nhau.
2. **Hiểu quan hệ:** thể hiện dependency, reference, data flow hoặc control flow.
3. **Tìm vấn đề:** làm nổi bật node lỗi, đường đi không hợp lệ hoặc tài nguyên chưa được resolve.
4. **Giải thích quyết định:** cho biết compiler hoặc optimizer đã chọn kế hoạch nào và vì sao.
5. **Theo dõi thực thi:** biểu diễn tiến trình, thời gian, trạng thái và sự kiện runtime.
6. **Điều hướng:** kết nối hình ảnh với đoạn DSL, diagnostics và tài liệu liên quan.
7. **So sánh:** cho thấy khác biệt giữa hai phiên bản nguồn, IR hoặc execution plan.

Một visualizer nên bắt đầu từ câu hỏi mà người dùng cần trả lời. Cây AST phù hợp để hiểu cấu trúc cú pháp; đồ thị dependency phù hợp để xem thứ tự công việc; timeline phù hợp để tìm tác vụ chậm. Dùng cùng một loại sơ đồ cho mọi vấn đề thường khiến thông tin khó đọc.

## 3. Các loại biểu diễn có thể trực quan hóa

Một hệ thống DSL có thể cung cấp nhiều góc nhìn, mỗi góc nhìn tập trung vào một loại thông tin.

### 3.1. Concrete syntax tree và abstract syntax tree

Concrete Syntax Tree (CST) giữ nhiều chi tiết cú pháp hơn, chẳng hạn dấu ngoặc, dấu phân cách và token. Abstract Syntax Tree (AST) tập trung vào cấu trúc có ý nghĩa của chương trình.

Ví dụ:

~~~text
let total = price * quantity
~~~

AST giản lược:

~~~text
VariableDeclaration: total
└── Multiply
    ├── Name: price
    └── Name: quantity
~~~

Visualizer cây AST hữu ích để kiểm tra parser đã hiểu biểu thức như thế nào, nhất là khi grammar có precedence, associativity hoặc cú pháp lồng nhau.

### 3.2. Symbol và reference graph

Một DSL có thể khai báo symbol rồi tham chiếu đến chúng ở nhiều nơi. Reference graph thể hiện quan hệ giữa khai báo và nơi sử dụng.

~~~text
Declaration: customer_id
       |
       +----> Filter expression
       |
       +----> Join condition
       |
       +----> Output mapping
~~~

Góc nhìn này giúp tìm symbol không được dùng, tham chiếu chưa resolve, tên trùng hoặc thay đổi có ảnh hưởng rộng.

### 3.3. Schema và cấu trúc dữ liệu

Visualizer schema có thể hiển thị:

- Object và field.
- Kiểu dữ liệu.
- Thuộc tính required hoặc optional.
- Default value.
- Ràng buộc và quan hệ.
- Nguồn gốc hoặc phiên bản schema.

Ví dụ một node field có thể cho biết amount có kiểu Decimal, không nullable và có constraint lớn hơn hoặc bằng 0.

### 3.4. Control-flow graph

Control-flow graph (CFG) biểu diễn các basic block và cạnh chuyển tiếp. Nó phù hợp để hiểu nhánh, vòng lặp, điểm hợp nhất và đường thoát.

~~~text
             [Entry]
                |
          [Check condition]
             /       \
          true       false
           /           \
       [Block A]     [Block B]
           \           /
             [Merge]
                |
              [Exit]
~~~

### 3.5. Data-flow graph

Data-flow graph cho biết giá trị được tạo từ đâu và được sử dụng ở đâu.

~~~text
price ----\
           > Multiply ----> total
quantity -/
~~~

Nó hữu ích khi giải thích biểu thức, dependency dữ liệu, phép biến đổi hoặc nguồn gốc của một kết quả.

### 3.6. Dependency graph

Dependency graph thể hiện quan hệ phụ thuộc giữa module, task, resource hoặc stage. Nó thường dùng cho workflow, build system, pipeline và cấu hình triển khai.

### 3.7. Intermediate Representation

Visualizer IR có thể hiển thị module, function, block, instruction, operand, type và metadata. Kỹ sư compiler dùng góc nhìn này để quan sát lowering và optimization.

### 3.8. Execution plan

Execution plan mô tả cách runtime hoặc backend dự định thực hiện chương trình: đọc nguồn, lọc, join, aggregate, ghi kết quả hoặc gọi dịch vụ.

### 3.9. Runtime timeline

Timeline thể hiện thời điểm task bắt đầu, chờ, tiếp tục, hoàn tất hoặc thất bại. Nó phù hợp để phân tích độ trễ, contention và hoạt động đồng thời.

### 3.10. Diagnostics và transformation history

Visualizer có thể làm nổi bật vị trí lỗi trên AST hoặc đồ thị, và cho phép xem node đã thay đổi qua những compiler pass nào. Các góc nhìn này kết nối cấu trúc với lịch sử xử lý.

## 4. Chọn hình thức trực quan phù hợp

Không phải dữ liệu nào cũng nên biểu diễn bằng graph. Hình thức cần phản ánh bản chất thông tin.

| Loại dữ liệu | Hình thức thường phù hợp | Câu hỏi hỗ trợ |
|---|---|---|
| Cấu trúc lồng nhau | Tree view | Thành phần nào nằm trong thành phần nào? |
| Quan hệ nhiều-nhiều | Node-link graph | Thành phần nào liên kết với thành phần nào? |
| Luồng điều khiển | CFG | Chương trình có thể đi theo nhánh nào? |
| Phụ thuộc tác vụ | DAG | Việc nào cần hoàn thành trước? |
| Trình tự theo thời gian | Timeline hoặc sequence diagram | Điều gì xảy ra trước và sau? |
| Giá trị và phép tính | Data-flow graph | Kết quả được tạo từ dữ liệu nào? |
| Cấu hình có trường | Table hoặc property panel | Thuộc tính và giá trị hiện tại là gì? |
| Khác biệt phiên bản | Diff view | Nội dung nào đã thay đổi? |
| Phân bố số liệu | Chart | Số lượng hoặc thời lượng thay đổi ra sao? |

### 4.1. Tree view

Tree view phù hợp khi mỗi phần tử có quan hệ cha-con rõ ràng. Nó có thể hỗ trợ expand/collapse, tìm kiếm, chọn node và hiển thị metadata.

### 4.2. Graph view

Graph view phù hợp với quan hệ nhiều-nhiều hoặc cấu trúc có chu trình. Cần có layout dễ đọc, mũi tên có hướng khi quan hệ có chiều và nhãn cạnh rõ ràng.

### 4.3. Timeline

Timeline đặt sự kiện trên trục thời gian. Có thể có swimlane theo task, thread, service hoặc worker. Nó giúp nhìn ra khoảng chờ và phần việc chạy chồng lấp.

### 4.4. Sequence diagram

Sequence diagram thể hiện message hoặc lời gọi giữa các participant theo thời gian. Nó phù hợp để xem giao tiếp giữa language server, compiler, plugin và runtime service.

### 4.5. Table và property inspector

Table phù hợp với danh sách lớn có thuộc tính đồng nhất. Property inspector phù hợp để xem chi tiết node đang chọn mà không làm sơ đồ chính quá tải.

## 5. Kiến trúc của một visualizer

Visualizer nên tách dữ liệu ngôn ngữ khỏi cách trình bày. Compiler hoặc language server tạo model có cấu trúc; lớp visualization chuyển model thành view model; renderer hiển thị node, cạnh, nhãn và tương tác.

~~~text
DSL Source / Runtime Events
          |
          v
Parser / Compiler / Runtime
          |
          v
AST / IR / Plan / Trace Model
          |
          v
Visualization Adapter
          |
          v
View Model
          |
          v
Layout Engine
          |
          v
Renderer and Interaction
          |
          v
Editor / Webview / Desktop UI
~~~

### 5.1. Data provider

Data provider lấy dữ liệu từ parser, compiler, language server, runtime hoặc artifact đã lưu. Nó nên cung cấp API có kiểu thay vì để giao diện tự phân tích lại DSL.

### 5.2. Visualization adapter

Adapter chuyển mô hình nội bộ thành mô hình trực quan. Ví dụ, AST node có thể thành tree item; CFG block thành graph node; dependency reference thành edge.

### 5.3. View model

View model chứa những gì renderer cần:

- ID node.
- Loại node.
- Nhãn hiển thị.
- Các thuộc tính tóm tắt.
- Danh sách cạnh.
- Source location.
- Trạng thái hoặc severity.
- Metadata để mở inspector.

View model nên giữ ID ổn định trong phạm vi phiên bản dữ liệu để hỗ trợ chọn node và cập nhật gia tăng.

### 5.4. Layout engine

Layout engine quyết định vị trí node và đường đi của cạnh. Nó có thể dùng tree layout, layered layout, force-directed layout hoặc timeline layout tùy loại sơ đồ.

### 5.5. Renderer

Renderer chuyển view model và layout thành SVG, Canvas, HTML hoặc giao diện native. Lựa chọn phụ thuộc số lượng phần tử, khả năng tương tác, accessibility và nền tảng.

### 5.6. Interaction controller

Controller xử lý chọn node, zoom, pan, expand/collapse, lọc, điều hướng về nguồn và yêu cầu chi tiết. Tách controller khỏi renderer giúp kiểm thử và thay đổi giao diện dễ hơn.

## 6. Mô hình dữ liệu cho visualization

Một graph view thường cần node và edge có định danh.

Ví dụ model khái niệm:

~~~json
{
  "nodes": [
    {
      "id": "load-orders",
      "kind": "task",
      "label": "Load Orders",
      "source": {
        "uri": "file:///workspace/report.dsl",
        "startLine": 2,
        "startCharacter": 4
      },
      "state": "ready"
    },
    {
      "id": "build-report",
      "kind": "task",
      "label": "Build Report",
      "state": "blocked"
    }
  ],
  "edges": [
    {
      "id": "edge-orders-report",
      "from": "load-orders",
      "to": "build-report",
      "kind": "dependency"
    }
  ]
}
~~~

Đây là schema minh họa. Một triển khai cần xác định kiểu và quy tắc cho từng trường.

### 6.1. Node identity

ID cần ổn định đủ để giữ selection và mapping khi dữ liệu được cập nhật. Không nên dùng vị trí node trên màn hình làm identity vì layout có thể thay đổi.

### 6.2. Edge identity

Một cặp node có thể có nhiều quan hệ khác nhau. Ví dụ A vừa cung cấp dữ liệu cho B, vừa là dependency về thứ tự. Edge cần ID và kind riêng để renderer không gộp nhầm.

### 6.3. Source location

Node có thể liên kết đến URI, range và document version. Nếu nguồn thay đổi, vị trí cũ có thể không còn đúng; cần cập nhật mapping hoặc đánh dấu source reference stale.

### 6.4. Metadata

Metadata có thể chứa type, cost estimate, runtime state, diagnostic code hoặc provenance. Không nên nhồi mọi metadata vào nhãn node; dùng inspector hoặc tooltip để trình bày chi tiết theo nhu cầu.

### 6.5. Schema version

View model nên có version để client biết cách diễn giải. Nếu adapter thay đổi cấu trúc dữ liệu, version giúp xử lý tương thích giữa server và UI.

## 7. Layout cho cây và đồ thị

Layout ảnh hưởng trực tiếp đến khả năng đọc. Một graph đúng dữ liệu nhưng cạnh chồng chéo và node đặt lộn xộn vẫn khó sử dụng.

### 7.1. Tree layout

Tree layout đặt node cha ở trên hoặc bên trái, node con ở tầng tiếp theo. Nó phù hợp AST và cấu trúc lồng nhau.

### 7.2. Layered layout

Layered layout đặt node theo các tầng, thường theo hướng luồng từ trái sang phải hoặc từ trên xuống. Nó phù hợp DAG và workflow.

### 7.3. Force-directed layout

Force-directed layout mô phỏng lực hút giữa node liên kết và lực đẩy giữa các node. Nó có thể hữu ích với graph tổng quát, nhưng vị trí có thể thay đổi giữa các lần chạy nếu không cố định seed và tham số.

### 7.4. Orthogonal routing

Orthogonal routing dùng các đoạn cạnh ngang và dọc, phù hợp sơ đồ kỹ thuật hoặc workflow có nhiều node. Cần tránh đường đi quá vòng vèo và cạnh cắt qua node.

### 7.5. Swimlane

Swimlane chia không gian theo task, service, thread hoặc nhóm. Nó phù hợp timeline và sequence-like view, giúp nhận biết chủ thể chịu trách nhiệm.

### 7.6. Giữ layout ổn định

Khi chỉ một node thay đổi, việc sắp xếp lại toàn bộ graph có thể khiến người dùng mất định hướng. Có thể giữ vị trí node không đổi nếu có thể, chỉ layout lại vùng bị ảnh hưởng hoặc dùng anchor cho node đang được chọn.

### 7.7. Layout deterministic

Layout xác định giúp screenshot, diff và kiểm thử ổn định. Có thể sắp xếp node theo ID hoặc thứ tự nguồn, cố định seed và dùng quy tắc tie-break nhất quán.

## 8. Trực quan hóa AST và CST

Visualizer cây cú pháp hỗ trợ hiểu cách parser diễn giải nguồn.

### 8.1. Hiển thị node và token

CST có thể hiển thị token, dấu ngoặc và dấu phân cách. AST có thể ẩn chi tiết không quan trọng để tập trung vào cấu trúc ý nghĩa.

### 8.2. Expand và collapse

Một chương trình lớn có thể có hàng nghìn node. Ban đầu chỉ nên hiển thị các node cấp cao; người dùng mở rộng nhánh cần xem.

### 8.3. Node lỗi

Parser recovery có thể tạo error node hoặc missing token. Visualizer nên đánh dấu rõ để người dùng phân biệt cấu trúc hợp lệ với phần parser suy đoán nhằm tiếp tục phân tích.

### 8.4. Liên kết hai chiều với nguồn

Chọn node trong cây có thể highlight đoạn nguồn. Ngược lại, chọn một đoạn DSL có thể làm nổi node tương ứng. Nếu nhiều node cùng ánh xạ đến một source span, UI có thể hiển thị danh sách kết quả thay vì chọn tùy tiện.

### 8.5. Hiển thị kiểu và symbol

AST viewer có thể bật lớp metadata để xem inferred type, resolved symbol, scope hoặc constant value. Đây là thông tin hữu ích cho người phát triển DSL nhưng có thể làm rối giao diện cơ bản, nên cần tùy chọn bật/tắt.

## 9. Trực quan hóa dependency graph và workflow

Dependency graph cho thấy thứ tự và quan hệ giữa các task.

### 9.1. Node và cạnh

Node có thể đại diện task, module, resource hoặc stage. Cạnh có thể biểu diễn:

- Data dependency.
- Execution dependency.
- Import/reference.
- Resource ownership.
- Trigger hoặc event subscription.

Nên phân biệt loại cạnh bằng nhãn hoặc kiểu nét, không chỉ dựa vào màu.

### 9.2. Topological order

Với DAG, visualizer có thể sắp xếp các node theo topological layers. Những node cùng tầng có thể chạy đồng thời nếu không có giới hạn tài nguyên khác.

### 9.3. Critical path

Nếu có duration estimate hoặc runtime measurements, có thể làm nổi bật critical path. Cần ghi rõ dữ liệu là estimated hay actual.

### 9.4. Phát hiện chu trình

Nếu graph có chu trình dependency không được DSL cho phép, visualizer có thể tô cạnh tạo chu trình và hiển thị diagnostic tương ứng.

### 9.5. Group và subgraph

Workflow lớn có thể nhóm theo module, stage, environment hoặc loại task. Người dùng mở group để xem chi tiết.

### 9.6. Trạng thái task

Trong runtime view, node có thể có trạng thái queued, ready, running, waiting, succeeded, failed, cancelled hoặc skipped. Trạng thái nên được mã hóa bằng nhãn hoặc icon kèm màu, để người dùng không phải dựa vào màu sắc duy nhất.

## 10. Trực quan hóa control flow và data flow

Control flow và data flow trả lời hai câu hỏi khác nhau: chương trình có thể thực thi theo đường nào và giá trị được truyền qua những phép tính nào.

### 10.1. CFG viewer

CFG viewer hiển thị:

- Basic block.
- Instruction trong từng block.
- Branch condition.
- Predecessor và successor.
- Loop back-edge.
- Entry và exit.
- Exception edge nếu IR hỗ trợ.

Có thể chọn block để xem instruction, dominator hoặc reachability metadata.

### 10.2. Data-flow viewer

Data-flow viewer hiển thị value, operation và use. Với SSA, mỗi value có một definition; phi node hoặc block argument thể hiện nơi hợp nhất giá trị từ nhiều đường đi.

### 10.3. Def-use navigation

Chọn một value có thể làm nổi definition và mọi use. Điều này hữu ích khi tìm nơi một giá trị bị ghi đè, không được sử dụng hoặc lan truyền sai.

### 10.4. Memory effects

Load, store và call có side effect nên được đánh dấu khác với phép tính thuần. Visualizer có thể hiển thị vùng nhớ hoặc resource mà instruction đọc/ghi nếu compiler có alias/effect metadata.

### 10.5. Giới hạn của đồ thị

Một graph data flow có thể rất dày. Không nên hiển thị tất cả cạnh cùng lúc. Có thể lọc theo value đang chọn, loại operation hoặc phạm vi block.

## 11. Trực quan hóa IR và các compiler pass

Visualizer IR hỗ trợ kỹ sư compiler theo dõi lowering và optimization.

### 11.1. Hiển thị nhiều tầng IR

Có thể cung cấp các tab hoặc panel:

- AST.
- High-level IR.
- Mid-level IR.
- Low-level IR.
- Bytecode.

Mỗi tầng có mục đích riêng. Không nên giả định node ở hai tầng có quan hệ một-một.

### 11.2. So sánh trước và sau pass

Một diff view có thể làm nổi:

- Node được thêm.
- Node bị loại.
- Node được thay thế.
- Cạnh hoặc block được thay đổi.
- Kiểu hoặc metadata được cập nhật.

### 11.3. Transformation lineage

Node hiện tại có thể được liên kết với node nguồn đã tạo ra nó. Nếu một node được gộp từ nhiều node hoặc một node được tách thành nhiều instruction, UI cần thể hiện quan hệ nhiều-nhiều.

### 11.4. Pass timeline

Có thể hiển thị danh sách pass cùng thời lượng, số node trước/sau và trạng thái. Chọn pass sẽ mở IR snapshot hoặc diff liên quan.

### 11.5. Explain optimization

Visualizer có thể hiển thị rule đã áp dụng và điều kiện dẫn đến quyết định. Nếu optimizer từ chối một phép biến đổi, lý do từ chối có thể được trình bày trong explain panel.

## 12. Trực quan hóa execution plan

Execution plan thể hiện cách backend dự định thực hiện chương trình DSL.

Ví dụ plan truy vấn:

~~~text
Read Orders
     |
     v
Filter status = PAID
     |
     v
Project customer_id, amount
     |
     v
Group by customer_id
     |
     v
Write Summary
~~~

Visualizer có thể hiển thị:

- Operation type.
- Input và output.
- Estimated rows hoặc cost.
- Actual rows hoặc duration nếu có runtime data.
- Partition hoặc parallelism.
- Index, join strategy hoặc source capability.

### 12.1. Estimated và actual

Ước lượng trước khi chạy khác với số đo sau khi chạy. UI cần phân biệt rõ để người dùng không nhầm estimated cost với actual duration.

### 12.2. Plan comparison

So sánh hai plan có thể cho thấy optimizer đổi join order, đẩy filter xuống nguồn hoặc thay cách scan. Cần gắn plan với cùng input snapshot hoặc ghi rõ điều kiện khác nhau.

### 12.3. Plan và semantics

Một plan đẹp hoặc có cost thấp không chứng minh kết quả đúng. Visualizer giúp giải thích cấu trúc; tính đúng vẫn cần kiểm tra semantics và kết quả thực thi.

## 13. Trực quan hóa runtime và concurrency

Runtime visualizer cho thấy điều gì thực sự xảy ra khi chương trình chạy.

### 13.1. Timeline

Timeline có thể có một lane cho mỗi task hoặc worker:

~~~text
Time  ---------------------------------------------------->
Worker 1 |---- Load Orders ----|--- Transform ---|
Worker 2 |--- Load Customers ---|------ Wait -----|
Worker 3 |------ Idle ----------|--- Build Report |
~~~

Nó giúp phân biệt thời gian chạy với thời gian chờ và nhận ra worker idle hoặc task bị chặn.

### 13.2. Event stream

Các sự kiện như task.created, task.started, task.waiting, task.completed và task.failed có thể được biểu diễn trên timeline hoặc event list.

### 13.3. Causal links

Một task có thể được khởi chạy do task khác hoàn tất hoặc gửi message. Cạnh nhân quả giúp giải thích vì sao sự kiện xuất hiện.

### 13.4. Lock và resource contention

Nếu runtime phát telemetry phù hợp, visualizer có thể hiển thị thời gian chờ lock, semaphore, connection pool hoặc queue. Cần phân biệt thời gian chờ tài nguyên với thời gian CPU.

### 13.5. Distributed trace

Task có thể chạy trên nhiều process hoặc service. Trace context và span ID cho phép kết nối sự kiện xuyên hệ thống. Visualizer cần xử lý clock skew nếu so sánh timestamp từ nhiều máy.

### 13.6. Dữ liệu runtime nhạy cảm

Timeline không nên hiển thị payload hoặc secret chỉ để giải thích luồng. Thường chỉ cần ID, loại sự kiện, thời gian và metadata đã được phép.

## 14. Tương tác với visualizer

Visualizer có giá trị khi người dùng có thể khám phá dữ liệu thay vì chỉ nhìn ảnh tĩnh.

### 14.1. Select

Chọn node hoặc cạnh để xem thuộc tính, source location và các quan hệ liên quan.

### 14.2. Hover

Hover có thể hiển thị tooltip ngắn như loại node, kiểu dữ liệu, trạng thái hoặc thời lượng. Tooltip không nên chứa toàn bộ nội dung lớn.

### 14.3. Zoom và pan

Zoom thay đổi mức phóng đại; pan di chuyển vùng nhìn. Cần có nút fit-to-view và reset zoom để người dùng không bị lạc khỏi sơ đồ.

### 14.4. Expand và collapse

Cho phép mở rộng module, subtree hoặc group. Khi collapse, có thể hiển thị số node con và trạng thái tổng hợp.

### 14.5. Search và filter

Người dùng có thể tìm theo tên task, symbol, operation, diagnostic code hoặc trạng thái. Filter giúp ẩn các node không liên quan.

### 14.6. Focus mode

Focus mode giữ node đang chọn và các node lân cận, làm mờ hoặc ẩn phần còn lại. Đây là cách giảm độ phức tạp của graph lớn.

### 14.7. Navigate to source

Chọn node có source mapping có thể yêu cầu editor mở tài liệu và đặt con trỏ tại range tương ứng. Nếu document version đã thay đổi, server cần resolve vị trí lại hoặc cảnh báo mapping cũ.

### 14.8. Navigate to related node

Các lệnh như show dependencies, show uses, show callers hoặc show provenance giúp người dùng khám phá quan hệ theo từng hướng.

## 15. Liên kết visualizer với Language Server

Language Server Protocol chuẩn hóa nhiều tính năng ngôn ngữ như diagnostics, hover, definition, references và code actions. LSP không định nghĩa một chuẩn tổng quát cho mọi loại sơ đồ DSL. Vì vậy, visualizer thường kết hợp tính năng LSP tiêu chuẩn với extension hoặc giao diện riêng của client.

### 15.1. Source mapping

Dù sơ đồ được dựng trong webview hay giao diện native, mỗi node có thể giữ URI và range. Khi người dùng chọn node, extension gọi editor API để điều hướng về nguồn.

### 15.2. Definition và references

Visualizer có thể dùng thông tin resolve symbol để nối node đến declaration và các references. Các thao tác điều hướng có thể tận dụng request LSP tương ứng.

### 15.3. Code lens và commands

Code lens hoặc command có thể mở một góc nhìn, ví dụ View Dependency Graph hoặc Show Execution Plan. Đây là cách đưa visualizer vào workflow editor mà không nhúng sơ đồ vào văn bản nguồn.

### 15.4. Custom request

Nếu cần dữ liệu đặc thù như AST graph hoặc runtime plan, client và server có thể định nghĩa custom request/notification. Cần version hóa schema và kiểm tra capability để tránh lỗi với client không hỗ trợ.

### 15.5. Webview hoặc panel

Một extension có thể mở webview/panel riêng để render sơ đồ. Cần kiểm soát message giữa webview và extension, xác thực dữ liệu nhận được và giới hạn quyền của nội dung web.

### 15.6. Không làm chậm request ngôn ngữ

Tạo graph lớn hoặc tính layout có thể tốn thời gian. Nên chạy trên worker phù hợp, cache layout khi có thể và không chặn các request cơ bản như hover hoặc completion.

## 16. Cập nhật trực quan theo thay đổi nguồn

Visualizer có thể phản ánh nội dung mới ngay khi tài liệu thay đổi.

### 16.1. Rebuild toàn bộ

Với tài liệu nhỏ, tạo lại toàn bộ view model và layout sau mỗi lần phân tích có thể đủ đơn giản và đáng tin cậy.

### 16.2. Incremental update

Với graph lớn, có thể chỉ cập nhật node và edge bị ảnh hưởng. Điều này yêu cầu ID ổn định và dependency mapping chính xác.

### 16.3. Preserve selection

Nếu node được chọn vẫn tồn tại sau update, giữ selection. Nếu node bị thay thế, có thể chuyển selection sang node mới có lineage tương ứng.

### 16.4. Stale view

Nếu visualization được tạo từ document version cũ, cần hiển thị version hoặc trạng thái stale. Không nên để người dùng tưởng sơ đồ phản ánh nội dung mới nhất.

### 16.5. Debounce và cancellation

Các yêu cầu dựng graph có thể dùng debounce và cancellation tương tự diagnostics. Khi dữ liệu mới đến, hủy layout cũ nếu kết quả đó không còn cần.

### 16.6. Đồng bộ nhiều panel

Nếu editor có source view, AST view và runtime view, một selection có thể đồng bộ giữa các panel. Cần tránh vòng lặp sự kiện khi panel A chọn node làm panel B cập nhật rồi B lại phát selection ngược.

## 17. Trực quan hóa khác biệt phiên bản

Diff view giúp so sánh hai trạng thái của DSL hoặc biểu diễn nội bộ.

### 17.1. Source diff

So sánh văn bản nguồn theo dòng hoặc token. Phù hợp với thay đổi cú pháp trực tiếp.

### 17.2. Structural diff

So sánh AST hoặc schema theo cấu trúc thay vì chỉ theo văn bản. Ví dụ đổi thứ tự thuộc tính không có ý nghĩa có thể không tạo khác biệt cấu trúc, nếu DSL quy định thứ tự đó không quan trọng.

### 17.3. Graph diff

So sánh node và edge:

- Node mới.
- Node bị xóa.
- Node thay đổi thuộc tính.
- Edge được thêm hoặc loại.
- Thay đổi dependency.

### 17.4. Semantic diff

Semantic diff cố gắng cho biết ý nghĩa thay đổi, chẳng hạn timeout tăng từ 10 giây lên 30 giây hoặc task B giờ phụ thuộc task A. Nó cần schema và ngữ nghĩa DSL, không thể chỉ dựa vào text diff.

### 17.5. Mapping node giữa phiên bản

Node ID có thể thay đổi sau parse hoặc lowering. Để so sánh, có thể ghép theo stable symbol ID, source lineage, node kind và cấu trúc lân cận. Ghép heuristic cần được xem là có thể không chắc chắn.

## 18. Khả năng đọc và thiết kế trực quan

Một visualizer tốt cần ưu tiên khả năng đọc hơn trang trí.

### 18.1. Hierarchy

Dùng kích thước, vị trí và nhóm để thể hiện cấp bậc. Không nên làm mọi node nổi bật như nhau.

### 18.2. Color semantics

Màu nên có ý nghĩa ổn định, ví dụ error, warning, success hoặc loại operation. Cần kèm nhãn, icon hoặc kiểu nét để người dùng không phụ thuộc riêng vào màu.

### 18.3. Labels

Nhãn node nên ngắn, dùng tên hoặc loại operation dễ nhận diện. Nội dung dài đưa vào tooltip hoặc inspector.

### 18.4. Edge labels

Nếu hai node có nhiều quan hệ, edge label giúp phân biệt data dependency với execution dependency. Tránh để nhãn cạnh chồng lên nhau.

### 18.5. Legend

Sơ đồ có nhiều loại node hoặc edge cần legend giải thích biểu tượng, màu và kiểu đường.

### 18.6. Layout density

Node quá dày hoặc cạnh chồng chéo làm sơ đồ khó đọc. Có thể nhóm node, collapse subtree hoặc chỉ hiển thị vùng liên quan.

### 18.7. Không dùng hình dạng làm ngữ nghĩa duy nhất

Nếu hình thoi có nghĩa decision, hình chữ nhật có nghĩa task, hãy kèm text hoặc legend. Khi export sang định dạng khác, hình dạng có thể bị mất.

## 19. Accessibility

Visualizer cần sử dụng được bằng bàn phím và công nghệ hỗ trợ.

Một số nguyên tắc:

- Mọi thao tác quan trọng có thể thực hiện bằng bàn phím.
- Node và cạnh có tên truy cập được.
- Focus indicator rõ ràng.
- Màu sắc có độ tương phản phù hợp.
- Không chỉ dùng màu để biểu thị trạng thái.
- Có tree/table hoặc textual representation thay thế cho graph phức tạp.
- Tooltip không phải nơi duy nhất chứa thông tin thiết yếu.
- Hỗ trợ phóng to và giảm chuyển động nếu phù hợp.

Với graph, keyboard navigation có thể cho phép di chuyển giữa node theo cạnh, mở inspector và điều hướng về source.

## 20. Hiệu năng với dữ liệu lớn

AST hoặc dependency graph có thể chứa hàng chục nghìn node. Render toàn bộ cùng lúc có thể làm UI chậm hoặc hết bộ nhớ.

### 20.1. Virtualization

Chỉ render các node đang nằm trong vùng nhìn hoặc các hàng đang hiển thị trong tree/table. Điều này giảm số phần tử giao diện.

### 20.2. Level of detail

Ở mức zoom xa, hiển thị nhóm hoặc node tổng hợp. Khi zoom gần, hiển thị chi tiết instruction và label.

### 20.3. Clustering

Nhóm node theo module, function, task group hoặc schema namespace. Người dùng mở rộng nhóm khi cần.

### 20.4. Lazy loading

Chỉ tải subtree hoặc metadata khi người dùng mở rộng node. Server có thể cung cấp children theo request.

### 20.5. Layout worker

Tính layout có thể chạy ngoài UI thread. UI nhận kết quả khi hoàn tất và kiểm tra graph version trước khi áp dụng.

### 20.6. Incremental layout

Nếu chỉ một vùng graph thay đổi, có thể tính lại vùng đó và giữ phần còn lại. Tuy nhiên, cạnh mới có thể ảnh hưởng layout lân cận; cần cân bằng giữa độ ổn định và chất lượng bố cục.

### 20.7. Giới hạn dữ liệu

Server có thể giới hạn số node hoặc cạnh trong một response, cung cấp pagination hoặc yêu cầu người dùng chọn scope nhỏ hơn. Nếu dữ liệu bị cắt, UI cần nói rõ để tránh hiểu graph là đầy đủ.

## 21. Bảo mật khi trực quan hóa

Visualizer có thể hiển thị nội dung nguồn, đường dẫn, tên tài nguyên, endpoint, secret reference hoặc runtime metadata.

Các nguyên tắc:

1. Chỉ tải dữ liệu mà người dùng được phép truy cập.
2. Không hiển thị secret value trong node label hoặc tooltip.
3. Redact đường dẫn và endpoint nhạy cảm khi cần.
4. Xác thực URI và source range trước khi điều hướng.
5. Kiểm tra message từ webview hoặc plugin như dữ liệu không tin cậy.
6. Không thực thi nội dung DSL chỉ vì người dùng mở visualizer.
7. Giới hạn kích thước graph và payload.
8. Tránh đưa dữ liệu nhạy cảm vào telemetry hoặc ảnh export.
9. Áp dụng CSP và giới hạn quyền cho webview nếu nền tảng hỗ trợ.
10. Kiểm tra quyền khi mở lại artifact đã lưu hoặc chia sẻ.

Visualizer là lớp trình bày. Việc hiển thị một resource không có nghĩa người dùng có quyền thực thi hoặc sửa resource đó.

## 22. Export và chia sẻ sơ đồ

Người dùng có thể cần đưa sơ đồ vào tài liệu, issue hoặc buổi review.

Các định dạng thường gặp:

- SVG: vector, phù hợp tài liệu và zoom.
- PNG: ảnh raster, tương thích rộng.
- PDF: tài liệu có thể in hoặc lưu trữ.
- JSON: dữ liệu có cấu trúc để công cụ khác xử lý.
- DOT/Graphviz: mô tả graph có thể render bằng công cụ tương ứng.
- Mermaid: sơ đồ văn bản phù hợp tài liệu hỗ trợ Mermaid.

### 22.1. Export giữ ngữ nghĩa

Nên giữ title, legend, nhãn node, hướng cạnh và trạng thái. Nếu export không hỗ trợ tương tác, có thể thêm source reference dưới dạng text hoặc link.

### 22.2. Export có chọn lọc

Người dùng có thể export toàn bộ graph hoặc chỉ vùng đang chọn. Cần hiển thị rõ nếu export là subset.

### 22.3. Snapshot và provenance

Ảnh export có thể ghi tên artifact, phiên bản DSL, thời điểm và compiler version nếu phù hợp. Không nên nhúng thông tin nhạy cảm mặc định.

### 22.4. Khả năng tái dựng

Nếu muốn mở lại visualization sau này, lưu view model hoặc tham chiếu đến artifact và phiên bản tương ứng. Chỉ lưu ảnh sẽ không giữ được tương tác hoặc source navigation.

## 23. Triển khai view model trong Java

Một backend Java có thể tạo model trung gian để UI render.

### 23.1. Node và edge

~~~java
import java.util.List;

record SourceRange(
    String uri,
    int startLine,
    int startCharacter,
    int endLine,
    int endCharacter
) {
}

record VisualNode(
    String id,
    String kind,
    String label,
    String state,
    SourceRange source,
    List<String> tags
) {
}

record VisualEdge(
    String id,
    String from,
    String to,
    String kind,
    String label
) {
}
~~~

Record có sẵn từ Java 16. Nếu dùng phiên bản cũ hơn, có thể dùng class bất biến thông thường.

### 23.2. Graph model

~~~java
import java.util.List;

record VisualGraph(
    String graphId,
    String version,
    List<VisualNode> nodes,
    List<VisualEdge> edges
) {
}
~~~

Graph model nên được tạo từ AST, IR hoặc execution plan đã có, không nên phân tích lại source trong UI.

### 23.3. Adapter từ dependency graph

~~~java
VisualGraph toVisualGraph(Workflow workflow) {
    List<VisualNode> nodes = workflow.tasks().stream()
        .map(task -> new VisualNode(
            task.id(),
            "task",
            task.name(),
            task.state(),
            task.sourceRange(),
            List.of()
        ))
        .toList();

    List<VisualEdge> edges = workflow.dependencies().stream()
        .map(dependency -> new VisualEdge(
            dependency.id(),
            dependency.fromTaskId(),
            dependency.toTaskId(),
            "dependency",
            "depends on"
        ))
        .toList();

    return new VisualGraph(
        workflow.id(),
        workflow.version(),
        nodes,
        edges
    );
}
~~~

Đây là pseudocode dựa trên các kiểu Workflow giả định. Adapter giữ logic ánh xạ ở phía server; renderer có thể thay đổi mà không cần sửa mô hình miền.

### 23.4. Kiểm tra graph trước khi gửi

Trước khi gửi view model, server nên xác nhận:

- ID node là duy nhất trong graph.
- Mọi endpoint của edge đều tham chiếu node tồn tại.
- Source range nằm trong giới hạn tài liệu hoặc được đánh dấu không có nguồn.
- Kind và state thuộc tập giá trị được hỗ trợ.
- Payload nằm trong giới hạn cho phép.

Đây là kiểm tra cấu trúc dữ liệu của visualization, không thay thế kiểm tra ngữ nghĩa DSL.

## 24. Tích hợp visualization với compiler và runtime

Visualizer cần lấy dữ liệu từ các nguồn có thẩm quyền.

### 24.1. AST provider

Parser có thể cung cấp AST snapshot sau mỗi document version. Visualizer dùng snapshot đó để tạo tree view.

### 24.2. IR provider

Compiler có thể cung cấp IR snapshot trước và sau một pass. Kèm theo node ID, source provenance và pass metadata để hỗ trợ diff.

### 24.3. Plan provider

Backend cung cấp execution plan cùng estimates và capability metadata. Runtime có thể bổ sung actual metrics sau khi chạy.

### 24.4. Runtime event provider

Runtime phát event có task ID, timestamp, state và trace context. Visualizer gom chúng thành timeline hoặc trạng thái graph.

### 24.5. Version consistency

Mọi response nên gắn version hoặc snapshot ID. Không ghép AST của version mới với diagnostics hoặc source mapping của version cũ mà không có quy tắc rõ.

### 24.6. Không phụ thuộc trực tiếp vào cấu trúc nội bộ không ổn định

Nếu UI truy cập trực tiếp class nội bộ của compiler, thay đổi implementation có thể làm vỡ visualizer. Adapter và schema view model tạo ranh giới ổn định hơn.

## 25. Kiểm thử visualizer

Visualizer cần kiểm thử cả dữ liệu, tương tác và cách trình bày.

### 25.1. Kiểm thử adapter

Cho AST, IR hoặc workflow mẫu và xác nhận node/edge được tạo đúng, ID ổn định trong phạm vi yêu cầu và source mapping được giữ.

### 25.2. Kiểm thử graph invariants

Kiểm tra ID trùng, edge tham chiếu node không tồn tại, source range sai và trạng thái không được hỗ trợ.

### 25.3. Kiểm thử layout

Với graph mẫu, kiểm tra node không chồng lấn nghiêm trọng, cạnh có hướng đúng và layout deterministic khi cấu hình yêu cầu.

### 25.4. Kiểm thử tương tác

Bao phủ select, hover, expand/collapse, search, filter, zoom, pan và navigate to source.

### 25.5. Kiểm thử version

Tạo graph cho version cũ, cập nhật nguồn rồi trả kết quả theo thứ tự ngược. UI không được thay graph mới bằng graph cũ.

### 25.6. Kiểm thử graph lớn

Đo thời gian tạo view model, layout và render với graph lớn. Kiểm tra virtualization, lazy loading và giới hạn payload.

### 25.7. Kiểm thử accessibility

Kiểm tra keyboard navigation, focus order, screen reader labels, contrast và biểu diễn thay thế.

### 25.8. Kiểm thử export

Xác nhận SVG/PNG/PDF hoặc JSON giữ đúng nhãn, cạnh, legend và source metadata cần thiết. Kiểm tra nội dung nhạy cảm đã được lọc theo chính sách.

### 25.9. Kiểm thử bảo mật

Thử payload không hợp lệ từ webview, URI ngoài workspace, graph quá lớn và metadata có nội dung không tin cậy. UI không nên diễn giải dữ liệu như HTML hoặc script có thể thực thi.

## 26. Những sai lầm thường gặp

### 26.1. Dùng một loại sơ đồ cho mọi dữ liệu

Cây AST, dependency DAG và runtime timeline trả lời các câu hỏi khác nhau. Chọn hình thức theo quan hệ cần giải thích.

### 26.2. Đưa quá nhiều thông tin vào node

Node với nhãn dài, type, source, cost và mọi metadata sẽ khó đọc. Chỉ hiển thị thông tin cốt lõi; phần còn lại đặt trong inspector hoặc tooltip.

### 26.3. Không có source mapping

Người dùng thấy node sai nhưng không biết sửa dòng nào. Giữ URI, range và version để điều hướng về DSL.

### 26.4. ID phụ thuộc vị trí layout

Khi layout thay đổi, node bị xem như node mới và selection mất. Dùng ID dựa trên identity của dữ liệu, không dựa vào tọa độ.

### 26.5. Sắp xếp lại toàn bộ graph sau mỗi thay đổi

Người dùng mất định hướng và khó theo dõi thay đổi. Ưu tiên layout ổn định hoặc cập nhật gia tăng khi khả thi.

### 26.6. Không phân biệt estimated với actual

Cost estimate không phải thời gian thực tế. Gắn nhãn rõ và hiển thị nguồn số liệu.

### 26.7. Không đánh dấu dữ liệu stale

Sơ đồ cũ có thể dẫn đến quyết định sai. Gắn document version hoặc snapshot ID và cập nhật khi nguồn thay đổi.

### 26.8. Chỉ dùng màu để biểu thị trạng thái

Người dùng mù màu hoặc màn hình không hiển thị màu tốt có thể không phân biệt được. Kèm icon, nhãn hoặc kiểu nét.

### 26.9. Render toàn bộ graph lớn

Render hàng chục nghìn node cùng lúc có thể làm UI treo. Dùng virtualization, grouping, lazy loading và focus mode.

### 26.10. Để UI tự phân tích DSL

Parser trong UI có thể khác parser compiler, dẫn đến hai cách hiểu. Tạo view model từ mô hình ngôn ngữ có thẩm quyền ở server hoặc compiler.

### 26.11. Tin dữ liệu từ webview

Message từ UI có thể bị giả mạo hoặc sai định dạng. Xác thực command, ID, URI và quyền trước khi thực hiện.

### 26.12. Xem visualization như bằng chứng tính đúng

Sơ đồ giúp hiểu chương trình nhưng không chứng minh chương trình đúng. Cần compiler validation, tests và runtime guarantees tương ứng.

## 27. Quy trình xây dựng visualizer cho DSL

Một quy trình triển khai có thể gồm:

1. **Xác định người dùng và câu hỏi.** Làm rõ visualizer phục vụ người viết DSL, compiler engineer hay operator.
2. **Chọn mô hình cần hiển thị.** AST, symbol graph, dependency graph, CFG, data flow, IR, plan hoặc timeline.
3. **Xác định nguồn dữ liệu.** Parser, compiler, language server, runtime hoặc artifact đã lưu.
4. **Thiết kế view model.** Định nghĩa node, edge, ID, source mapping, metadata và version.
5. **Chọn hình thức sơ đồ.** Tree, graph, layered DAG, timeline, table hoặc sequence diagram.
6. **Chọn layout và renderer.** Cân nhắc quy mô, nền tảng, tương tác và accessibility.
7. **Tích hợp điều hướng.** Liên kết node với source, definition, references, diagnostics và runtime events.
8. **Thiết kế cập nhật.** Snapshot, incremental update, debounce, cancellation và stale state.
9. **Thêm tương tác.** Search, filter, select, inspector, expand/collapse, zoom và export.
10. **Kiểm soát dữ liệu lớn.** Virtualization, grouping, lazy loading và payload limits.
11. **Bảo vệ thông tin.** Authorization, redaction, URI validation và webview security.
12. **Kiểm thử.** Adapter, graph invariants, layout, interaction, version, performance và accessibility.
13. **Đo lường sử dụng.** Quan sát độ trễ, kích thước graph và thao tác người dùng cần thiết để cải thiện công cụ.

Một visualizer có thể bắt đầu từ một góc nhìn nhỏ, chẳng hạn dependency graph có source navigation. Khi nhu cầu rõ hơn, có thể bổ sung AST, plan, runtime timeline hoặc transformation diff mà vẫn dùng chung view model và cơ chế điều hướng.

## 28. Câu hỏi tự kiểm tra

1. Trình trực quan hóa là gì và nó hỗ trợ người dùng DSL như thế nào?
2. Phân biệt CST và AST; trường hợp nào nên hiển thị từng loại?
3. Khi nào nên dùng tree view, graph view, timeline, sequence diagram và table?
4. Dependency graph, control-flow graph và data-flow graph thể hiện những quan hệ nào?
5. Một kiến trúc visualizer thường gồm những thành phần nào?
6. Vì sao view model nên tách khỏi cấu trúc nội bộ của compiler?
7. Node ID và edge ID cần đáp ứng yêu cầu gì để hỗ trợ cập nhật?
8. Tree layout, layered layout và force-directed layout phù hợp với dữ liệu nào?
9. Visualizer AST có thể hỗ trợ parser debugging và source navigation ra sao?
10. Visualizer IR giúp theo dõi compiler pass và transformation lineage như thế nào?
11. Estimated cost và actual runtime metrics cần được trình bày ra sao?
12. Timeline có thể giúp phát hiện task waiting hoặc resource contention như thế nào?
13. LSP cung cấp những khả năng nào có thể kết hợp với visualizer, và vì sao sơ đồ thường cần custom UI hoặc extension?
14. Vì sao cần gắn graph với document version hoặc snapshot ID?
15. Virtualization, clustering và lazy loading giải quyết vấn đề gì?
16. Nêu các nguyên tắc accessibility cho graph tương tác.
17. Những rủi ro bảo mật nào xuất hiện khi visualizer hiển thị source và runtime metadata?
18. Hãy đề xuất một visualizer cho workflow DSL gồm task, dependency, trạng thái runtime và source mapping; mô tả view model, layout và các thao tác người dùng.
