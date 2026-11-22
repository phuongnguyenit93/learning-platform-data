# JetBrains MPS

**JetBrains MPS** là một language workbench dùng để thiết kế, phát triển và sử dụng các ngôn ngữ miền đặc thù (Domain-Specific Languages — DSL). Thay vì chỉ cung cấp parser cho một cú pháp văn bản, MPS cho phép người phát triển định nghĩa trực tiếp mô hình ngôn ngữ: những khái niệm nào tồn tại, cấu trúc của chúng ra sao, người dùng chỉnh sửa chúng bằng giao diện nào, các quy tắc ngữ nghĩa được kiểm tra thế nào và mô hình sẽ được sinh thành mã hoặc artifact nào.

Điểm đặc trưng của MPS là **projectional editing**. Trong một editor dựa trên parser truyền thống, người dùng nhập văn bản rồi parser chuyển văn bản thành cây cú pháp. Trong MPS, mô hình có cấu trúc là dữ liệu gốc; editor chiếu (*project*) mô hình đó thành một cách trình bày để người dùng thao tác. Cách trình bày có thể trông giống văn bản, bảng, biểu đồ hoặc một cấu trúc trực quan khác. Khi người dùng sửa nội dung trong projectional editor, MPS cập nhật model node trực tiếp mà không cần phân tích lại toàn bộ văn bản như một parser thông thường.

Ví dụ, một DSL nghiệp vụ có thể mô tả quy trình xử lý đơn hàng:

~~~text
workflow FulfillOrder(order: Order) {
    validate order;
    if order.paymentStatus == ACCEPTED {
        reserve inventory;
        create shipment;
    }
}
~~~

Với MPS, người thiết kế ngôn ngữ có thể định nghĩa `Workflow`, `Action`, `Condition` và `Order` thành các concept; mô tả quan hệ cha–con và reference giữa chúng; thiết kế editor cho từng concept; kiểm tra kiểu và quy tắc nghiệp vụ; rồi tạo generator chuyển mô hình thành Java, mã thực thi hoặc một dạng biểu diễn khác. Người dùng DSL chỉnh sửa các node qua editor được định nghĩa, còn MPS duy trì cấu trúc model ở bên dưới.

MPS phù hợp khi một tổ chức cần ngôn ngữ chuyên biệt, có cấu trúc và có thể tiến hóa cùng quy trình nghiệp vụ. Nó đặc biệt hữu ích khi cú pháp văn bản thuần không đủ diễn đạt mô hình, khi cần nhiều notation cho cùng dữ liệu hoặc khi muốn kết hợp nhiều ngôn ngữ trong một mô hình. Đổi lại, projectional editing có cách tương tác khác editor text thông thường; nhóm phát triển cần đầu tư thiết kế concept, editor, generator và quy trình quản trị ngôn ngữ.

## 1. JetBrains MPS là gì?

MPS là một môi trường phát triển ngôn ngữ (language workbench) và một nền tảng modeling. Nó cung cấp công cụ để định nghĩa language, tạo model sử dụng language đó, kiểm tra mô hình, sinh mã và tích hợp các language với nhau.

Một language trong MPS không chỉ là danh sách từ khóa và grammar. Nó có thể gồm nhiều khía cạnh (*language aspects*):

- **Structure:** định nghĩa concept, property, child role và reference role.
- **Editor:** định nghĩa cách mỗi concept được trình bày và chỉnh sửa.
- **Constraints:** định nghĩa điều kiện tạo node, chọn node tham chiếu và quy tắc cấu trúc bổ sung.
- **Behavior:** định nghĩa hành vi hoặc thao tác hỗ trợ cho concept.
- **Typesystem:** định nghĩa kiểu, suy luận kiểu và quy tắc kiểm tra ngữ nghĩa.
- **Intentions và quick fixes:** cung cấp hành động chuyển đổi hoặc sửa mô hình trong editor.
- **Actions:** tích hợp thao tác menu, context action hoặc công cụ hỗ trợ.
- **Generator:** chuyển model của language nguồn thành model của language đích.
- **Text generation:** tạo văn bản hoặc artifact từ model khi phù hợp.

Không phải language nào cũng cần tất cả các aspect. Một DSL cấu hình nhỏ có thể chỉ cần structure, editor và generator. Một DSL nghiệp vụ phức tạp có thể cần typesystem, constraints, behavior, intentions và nhiều bước generator.

### MPS khác gì một parser generator?

Parser generator tập trung vào việc mô tả grammar và sinh parser để chuyển source text thành parse tree. MPS tập trung vào việc định nghĩa mô hình có cấu trúc và projectional editor để người dùng thao tác trực tiếp trên mô hình đó. MPS vẫn có thể làm việc với văn bản và tích hợp các công cụ text-based, nhưng cách authoring cốt lõi không dựa trên việc parse mọi ký tự thành AST sau mỗi lần nhập.

### MPS khác gì một UML modeling tool?

Một công cụ UML thường cung cấp một tập metamodel và notation đã được xác định cho modeling. MPS là workbench để người phát triển tạo ra language riêng, bao gồm metamodel, editor, kiểm tra và generator. Người dùng MPS có thể xây một language có notation đồ họa, dạng bảng hoặc dạng text-like, nhưng phạm vi không bị giới hạn ở một ngôn ngữ mô hình hóa dựng sẵn.

### MPS khác gì IDE thông thường?

IDE thông thường chủ yếu hỗ trợ viết mã theo một số language đã có. MPS cung cấp môi trường để tạo language mới và sau đó dùng language đó trong cùng workbench. Người phát triển language và người viết model có thể cùng làm việc trong MPS nhưng dùng những perspective và module khác nhau.

## 2. Projectional editing – nguyên lý cốt lõi

Trong editor text truyền thống, source text là dữ liệu gốc. Người dùng nhập ký tự, parser đọc văn bản, sau đó tạo AST hoặc CST. Khi cú pháp chưa hoàn chỉnh, parser cần error recovery để tạo một cây tạm.

Trong projectional editing, model có cấu trúc là dữ liệu gốc. Editor hiển thị model bằng các cell hoặc projection. Người dùng thao tác trên những thành phần có kiểu và quan hệ rõ ràng; editor chuyển thao tác thành thay đổi model.

~~~mermaid
flowchart TD
    A[Traditional text editor] --> B[Source text]
    B --> C[Parser]
    C --> D[AST / semantic model]
    D --> E[Analysis and generation]

    F[MPS projectional editor] --> G[Structured model]
    G --> H[Editor projection]
    H --> I[User edits model nodes]
    I --> G
    G --> J[Checking and generation]
~~~

### Không có văn bản tự do ở mọi vị trí

Vì model node có concept và role cụ thể, editor biết vị trí hiện tại đang cần một kiểu node nào. Người dùng có thể được gợi ý các node hợp lệ thay vì nhập bất kỳ chuỗi nào rồi chờ parser báo lỗi.

Ví dụ, trong một vị trí yêu cầu `Expression`, editor có thể cung cấp literal, reference, phép toán hoặc function call phù hợp. Trong vị trí yêu cầu `Action`, editor không cần chấp nhận một `Entity` tùy ý.

### Editor là projection của model

Một concept có thể được trình bày bằng một dòng giống văn bản, một bảng có nhiều cột hoặc một cấu trúc nhiều hàng. Cách trình bày không nhất thiết trùng với cách model được lưu nội bộ.

### Copy, paste và nhập liệu

Projectional editor có thể cung cấp thao tác nhập và copy/paste theo cấu trúc. Việc dán văn bản thông thường có thể cần parser hoặc importer để chuyển text thành node hợp lệ. Đây là một điểm cần cân nhắc khi người dùng quen làm việc với editor text-based.

### Ưu điểm

- Tránh nhiều trạng thái cú pháp không hợp lệ vì node được tạo theo concept.
- Có thể cung cấp nhiều notation cho cùng một model.
- Hỗ trợ language composition mà không phải ghép nhiều grammar text có thể xung đột.
- Reference có thể trỏ đến node identity thay vì chỉ tên văn bản.
- Editor có thể đưa ra completion theo loại node và role hiện tại.
- Mô hình có cấu trúc thuận lợi cho transformation và code generation.

### Đánh đổi

- Người dùng phải học cách điều hướng và chỉnh sửa theo cell/node.
- Các thao tác text thuần như chọn một đoạn tùy ý, sửa dấu câu hoặc dùng mọi phím tắt quen thuộc có thể khác editor thông thường.
- Trao đổi với công cụ text-based có thể cần import/export hoặc text generation.
- Thiết kế editor cần được đầu tư để projection dễ hiểu và không gây khó khăn khi nhập liệu.

## 3. Các khái niệm nền tảng: node, concept, model và module

MPS sử dụng mô hình dựa trên concept và node.

### Concept

Concept định nghĩa một loại phần tử trong language, tương tự một kiểu hoặc một lớp trong metamodel. Ví dụ `Entity`, `Property`, `Workflow`, `ActionCall` hoặc `Condition` có thể là các concept.

Concept định nghĩa những property, child role và reference role mà instance của nó có thể có. Nó cũng có thể kế thừa concept khác để chia sẻ cấu trúc hoặc hành vi.

### Node

Node là một instance của concept trong model. Một node `Order` có thể là instance của concept `Entity`; node `total` có thể là instance của concept `Property` và là child của `Order` theo một role được định nghĩa.

### Model

Model là tập hợp các root node và các node liên quan, được tổ chức theo cấu trúc của language. Model có thể chứa các khai báo, biểu thức, reference và metadata cần thiết.

### Module

Module là đơn vị tổ chức lớn hơn, có thể chứa hoặc cung cấp model, language, generator, solution hoặc devkit. Dependency giữa module xác định những language và model nào có thể được sử dụng.

### Quan hệ khái quát

~~~text
Project
  Module
    Model
      Root node
        Child node
          Child node
        Reference -> node ở model khác
~~~

Node có thể có child theo containment và reference đến node khác. Hai loại quan hệ này khác nhau: child thường thuộc cấu trúc sở hữu của node cha, còn reference liên kết đến một node có identity độc lập.

## 4. Project và module trong MPS

Một MPS project thường chứa các module có vai trò khác nhau. Việc chia module giúp tổ chức language definition, model sử dụng language, generator và các dependency.

Các loại module thường gặp gồm:

| Loại module | Vai trò |
|---|---|
| Solution | Chứa model hoặc ứng dụng sử dụng các language đã có. |
| Language | Định nghĩa language và các aspect của nó. |
| Generator | Chứa quy tắc chuyển đổi model nguồn sang model đích. Trong MPS, generator thường gắn với language module. |
| DevKit | Gom các language và solution dependency để tái sử dụng thuận tiện. |
| Language runtime hoặc runtime solution | Cung cấp mã runtime mà model sinh ra cần dùng, tùy cách tổ chức dự án. |

Tên và chi tiết UI có thể thay đổi theo phiên bản MPS, nhưng ý tưởng tổ chức module theo vai trò vẫn là nền tảng.

### Solution

Solution thường chứa model ứng dụng hoặc ví dụ sử dụng language. Chẳng hạn, language `OrderDSL` được định nghĩa trong một language module, còn model `SalesProcess` được lưu trong một solution dùng language đó.

### Language module

Language module chứa cấu trúc và các aspect của language. Nó xác định concept, editor, typesystem, constraints, generator và các phần mở rộng liên quan.

### DevKit

DevKit có thể gom các language mà một module khác cần sử dụng. Điều này giúp giảm việc khai báo từng dependency riêng lẻ và tạo một tập language dùng chung.

### Dependency

Module cần khai báo dependency để sử dụng language, model hoặc runtime từ module khác. Dependency graph ảnh hưởng đến khả năng resolve reference, build và generation. Thiếu dependency có thể khiến editor không nhận ra concept hoặc generator không tìm thấy target language.

## 5. Structure aspect – định nghĩa cấu trúc language

Structure aspect mô tả các concept tạo nên language. Đây là nền tảng của model vì mọi node phải thuộc một concept.

Ví dụ, một DSL mô tả entity có thể định nghĩa:

~~~text
Concept Entity
  property name: Identifier
  child properties: Property [0..*]

Concept Property
  property name: Identifier
  property type: TypeReference
~~~

Trong MPS, cấu trúc được định nghĩa qua các concept declaration và role cụ thể trong language structure model.

### Properties

Property lưu giá trị đơn giản gắn với node, ví dụ tên, nhãn, số lượng hoặc một cờ boolean. Property thường là giá trị dữ liệu chứ không phải node con.

Ví dụ:

- `Entity.name` lưu tên entity.
- `Property.isRequired` lưu trạng thái bắt buộc.
- `Workflow.timeout` lưu thời gian chờ.

### Child roles

Child role định nghĩa node con được containment bởi node cha. Role có thể có cardinality như một child bắt buộc, child tùy chọn hoặc danh sách child.

Ví dụ:

- `Entity.properties` chứa nhiều `Property`.
- `Function.body` chứa một `StatementList`.
- `IfStatement.condition` chứa một `Expression`.
- `IfStatement.thenBranch` và `elseBranch` chứa các statement block.

### Reference roles

Reference role liên kết một node với node khác mà không biến target thành child. Ví dụ `Property.type` có thể tham chiếu đến một `Type` được khai báo ở model khác; `ActionCall.action` có thể trỏ đến một `ActionDeclaration`.

### Cardinality

Structure cần xác định số lượng child hợp lệ. Một `Function` có thể yêu cầu đúng một return type hoặc một body; một `Entity` có thể có từ không đến nhiều property. Cardinality là một phần của metamodel và ảnh hưởng cách editor cho phép tạo node.

### Inheritance giữa concept

Concept có thể kế thừa concept cơ sở để chia sẻ property, role hoặc hành vi. Ví dụ `PublicEntity` và `InternalEntity` có thể kế thừa `Entity` nếu language cần phân biệt visibility nhưng giữ cấu trúc chung.

### Abstract concept

Concept trừu tượng có thể dùng làm kiểu chung cho các node con mà người dùng không tạo trực tiếp. Ví dụ `Expression` có thể là abstract concept với các subtype `Literal`, `ReferenceExpression` và `BinaryExpression`.

## 6. Thiết kế metamodel tốt

Metamodel quyết định những cấu trúc nào language có thể biểu diễn. Một metamodel khó hiểu sẽ dẫn đến editor phức tạp, constraints rối và generator khó bảo trì.

Các nguyên tắc hữu ích:

- Mỗi concept nên đại diện một khái niệm có ý nghĩa trong miền hoặc trong cấu trúc ngôn ngữ.
- Phân biệt property, child và reference theo ownership và identity.
- Đặt tên role theo ý nghĩa miền, tránh tên chung chung như `child1` hoặc `data`.
- Định nghĩa cardinality phù hợp với trạng thái hợp lệ của model.
- Dùng abstract concept khi nhiều node có chung semantics.
- Tránh tạo quá nhiều concept chỉ để thay đổi cách trình bày nếu chúng không khác về cấu trúc hoặc ngữ nghĩa.
- Để ý khả năng tiến hóa: thêm property, role hoặc subtype có ảnh hưởng đến model cũ thế nào.

### Ví dụ metamodel cho workflow

~~~text
Workflow
  name: Identifier
  parameters: Parameter [0..*]
  steps: Step [1..*]

Step (abstract)
  id: StableId

ActionStep extends Step
  action: ActionReference

IfStep extends Step
  condition: Expression
  thenSteps: Step [0..*]
  elseSteps: Step [0..*]

WaitStep extends Step
  event: EventReference
  timeout: Duration?
~~~

Mô hình này thể hiện một workflow gồm các bước, trong đó step có thể là action, điều kiện hoặc chờ sự kiện. Generator có thể xử lý từng subtype của `Step` theo semantics riêng.

## 7. Editor aspect – thiết kế projectional editor

Editor aspect định nghĩa cách một concept được hiển thị và chỉnh sửa. Trong projectional editor, editor không đơn thuần là một template in ra text; nó là giao diện thao tác trên các cell liên kết với property, child hoặc reference của node.

Ví dụ một editor cho `Property` có thể hiển thị:

~~~text
<name> : <type> [required]
~~~

Các vùng trong projection tương ứng với property hoặc reference của node. Người dùng có thể đặt caret vào cell tên, cell type hoặc cell cờ required để chỉnh sửa phần dữ liệu tương ứng.

### Cells

Editor được tổ chức từ các cell. Một cell có thể hiển thị property, child node, reference, constant text hoặc một collection. Cell có thể chứa cell con để tạo projection phức tạp.

### Constant text

Constant cell hiển thị từ khóa hoặc dấu phân cách cố định, ví dụ `entity`, `if`, `then`, `:` hoặc dấu ngoặc. Người dùng không sửa constant text như một property thông thường; nó thể hiện cấu trúc của concept.

### Property cell

Property cell cho phép chỉnh sửa giá trị property, chẳng hạn identifier hoặc số. Editor có thể gắn validator, completion hoặc cách trình bày phù hợp với kiểu dữ liệu.

### Reference cell

Reference cell hiển thị target của reference role. Người dùng có thể nhập hoặc chọn target theo scope và constraints. MPS lưu liên kết đến node đích, vì vậy rename target không nhất thiết làm hỏng reference như một chuỗi tên tự do.

### Child cell

Child cell chiếu node con tại vị trí tương ứng. Nó có thể hiển thị một expression, statement hoặc một danh sách node. Người dùng tạo hoặc thay đổi child bằng thao tác được editor hỗ trợ.

### Collection editor

Một role nhiều phần tử có thể được trình bày thành danh sách, bảng hoặc nhóm cell. Cần định nghĩa cách thêm, xóa, di chuyển và chọn phần tử.

## 8. Thiết kế editor dễ sử dụng

Projectional editor cần có quy tắc nhập liệu nhất quán. Người dùng không nên phải đoán phím nào tạo node, di chuyển qua cell hoặc thoát khỏi một cấu trúc lồng.

### Placeholder và empty cell

Khi child bắt buộc chưa được tạo, editor có thể hiển thị placeholder để người dùng biết vị trí cần nhập. Placeholder nên phân biệt rõ với dữ liệu thực và không được bị hiểu nhầm là giá trị đã có.

### Keyboard navigation

Các thao tác như Tab, Enter, Escape, Backspace, Delete và phím mũi tên có thể được dùng để di chuyển hoặc thay đổi cấu trúc. Cần tránh xung đột với thói quen nhập text và công bố hành vi nhất quán.

### Completion

Khi nhập reference hoặc node có nhiều subtype, editor có thể cung cấp completion theo concept, scope, kiểu và constraints. Gợi ý cần phản ánh các target hợp lệ trong ngữ cảnh hiện tại.

### Error indication

Editor có thể đánh dấu cell hoặc node có lỗi từ typesystem hoặc validation. Diagnostic cần gắn với node/range phù hợp để người dùng biết vị trí và nguyên nhân.

### Formatting và readability

Một projection tốt cần phân cấp rõ, dùng khoảng trắng và căn chỉnh ổn định, không hiển thị quá nhiều metadata. Với DSL lớn, có thể cung cấp editor compact và editor expanded cho cùng concept.

### Tránh editor quá thông minh

Tự động tạo quá nhiều node, chuyển đổi cấu trúc hoặc thay đổi thứ tự có thể khiến người dùng mất kiểm soát. Intention hoặc action nên giải thích được tác động và hỗ trợ undo.

## 9. Constraints aspect – kiểm soát node và reference

Constraints định nghĩa điều kiện bổ sung cho việc tạo node, truy cập child hoặc chọn target reference. Nó giúp model không chỉ đúng cấu trúc cơ bản mà còn phù hợp ngữ cảnh.

Ví dụ, một `ActionCall` chỉ được tham chiếu đến action có chữ ký tương thích với đối số hiện tại. Một `Property` trong entity chỉ được dùng kiểu hợp lệ. Một workflow chỉ được gọi action có capability phù hợp.

### Can be child

Một số constraint xác định node concept nào được phép xuất hiện trong child role cụ thể. Ví dụ `Workflow.steps` chỉ chấp nhận subtype của `Step`, không chấp nhận `Entity`.

### Can be referent

Constraint có thể lọc danh sách node được chọn làm target reference. Ví dụ `ActionCall.action` chỉ tham chiếu đến action trong dependency scope hoặc module được phép.

### Default behavior

Khi tạo node mới, language có thể thiết lập giá trị mặc định hoặc tạo các child bắt buộc. Cần tránh tạo cấu trúc không hợp lệ hoặc khó hiểu khi người dùng hủy thao tác.

### Context-sensitive constraint

Một lựa chọn hợp lệ có thể phụ thuộc node cha, kiểu biểu thức, module hoặc capability. Constraint nên dùng ngữ cảnh model hiện tại và tránh truy cập trạng thái ngoài không ổn định nếu không cần.

### Constraint không thay thế typesystem

Constraint chủ yếu giới hạn cấu trúc, lựa chọn node và điều kiện hợp lệ trong model. Type checking và các quy tắc suy luận phức tạp nên được mô hình hóa trong typesystem aspect để kết quả kiểm tra có thể được tổng hợp và giải thích nhất quán.

## 10. Behavior aspect – hành vi của concept

Behavior aspect cho phép định nghĩa các phương thức hoặc thao tác gắn với concept. Nó có thể cung cấp logic truy vấn, tính toán hoặc helper method để các aspect khác sử dụng.

Ví dụ, một `Workflow` có thể có behavior method tính danh sách action được gọi trực tiếp; một `Entity` có thể cung cấp danh sách property theo thứ tự; một expression có thể cung cấp kiểu hoặc biểu diễn phụ trợ.

### Behavior và semantics

Behavior nên diễn đạt logic thuộc về concept. Không nên biến nó thành nơi chứa mọi logic của editor, generator hoặc runtime. Tách trách nhiệm giúp language dễ kiểm thử và bảo trì.

### Recursive traversal

Một method có thể duyệt node con để tìm tất cả action trong workflow. Cần chú ý reference cycle: traversal theo containment thường có cấu trúc cây, còn traversal theo reference có thể tạo vòng lặp.

### Truy cập model và side effects

Các thao tác thay đổi model cần được thực hiện trong command/transaction phù hợp với môi trường MPS. Helper method chỉ đọc dữ liệu nên tách khỏi action chỉnh sửa để tránh tác dụng phụ bất ngờ khi editor hoặc generator gọi.

## 11. Typesystem aspect – kiểm tra ngữ nghĩa và kiểu

Typesystem aspect định nghĩa quy tắc kiểu cho language. Nó giúp kiểm tra expression, reference, function call và quan hệ giữa các giá trị trước khi generation hoặc execution.

Ví dụ DSL:

~~~text
let total: Money = order.total;
let count: Integer = order.items.size;
~~~

Typesystem có thể xác nhận `order.total` có kiểu `Money`, `order.items.size` có kiểu `Integer` và phép gán phù hợp.

### Type inference

Không phải mọi biểu thức đều cần khai báo kiểu tường minh. Typesystem có thể suy luận kiểu từ literal, reference, function signature và toán tử.

### Type equation và rule

Một cách tiếp cận là tạo các quy tắc quan hệ kiểu giữa expression và expected type. Ví dụ phép cộng yêu cầu hai toán hạng có kiểu tương thích và trả về kiểu theo quy tắc của language.

### Subtyping

Nếu DSL hỗ trợ kiểu con, typesystem cần quy định assignment compatibility, variance, method lookup và cách xử lý ambiguity.

### Overloading

Nếu nhiều function có cùng tên, engine kiểm tra candidate dựa trên kiểu và số lượng đối số. Nếu có nhiều candidate phù hợp ngang nhau, cần diagnostic ambiguity thay vì chọn tùy tiện.

### Error reporting

Typesystem cần cung cấp diagnostic gắn với node nguồn, kiểu mong đợi, kiểu thực tế và có thể chỉ ra declaration liên quan. Không nên chỉ báo một lỗi chung “type mismatch” nếu có thể cung cấp ngữ cảnh cụ thể.

### Kiểm tra gia tăng

Thay đổi type của một declaration có thể ảnh hưởng expression phụ thuộc. Typesystem cần tích hợp với dependency/invalidation của MPS để các node liên quan được tính lại.

## 12. Scoping và reference resolution

Một language thường cần quy tắc phạm vi: tên nào được nhìn thấy ở đâu, import hoạt động thế nào và reference được resolve ra sao.

Ví dụ:

~~~text
module Sales {
    entity Customer;
    workflow FulfillOrder {
        use Customer;
    }
}
~~~

Reference `Customer` trong workflow cần được resolve đến declaration phù hợp trong scope.

Các quyết định quan trọng:

- Scope lexical hay scope theo module/package.
- Khai báo có được forward reference không.
- Import có alias hay wildcard không.
- Tên có phân biệt hoa thường không.
- Có hỗ trợ shadowing không.
- Visibility `public`, `internal`, `private` được áp dụng thế nào.
- Reference đến model hoặc module bên ngoài được quản lý ra sao.

MPS lưu reference như quan hệ giữa node, nhưng language designer vẫn phải xác định quy tắc resolve và cách editor cho phép người dùng chọn target.

## 13. Language composition – kết hợp nhiều language

Một ưu điểm quan trọng của MPS là khả năng kết hợp các language trong cùng một model. Một concept có thể chứa node từ language khác nếu cấu trúc và dependency cho phép.

Ví dụ, một workflow DSL có thể dùng expression language để viết điều kiện, một language kiểu dữ liệu để khai báo schema và một language truy vấn để đọc dữ liệu.

~~~text
workflow ApproveOrder(order: Order) {
    if order.total > 1000 && customer.isTrusted(order.customer) {
        requireManagerApproval(order);
    }
}
~~~

Trong mô hình, điều kiện có thể dùng các concept expression từ một language khác, còn action thuộc workflow language.

### Tái sử dụng language có sẵn

MPS có các language nền tảng và hệ sinh thái language có thể tái sử dụng. BaseLanguage là một ví dụ về language kiểu Java được dùng trong môi trường MPS để viết một số logic hoặc tích hợp với hệ sinh thái Java.

### Không cần ghép grammar bằng text

Vì model node có concept identity, composition không phụ thuộc vào việc ghép hai grammar text có cùng token hoặc precedence. Tuy vậy, language composition vẫn cần giải quyết scope, typesystem, editor, dependency và generator.

### Editor composition

Một editor có thể chứa cell hiển thị node từ language khác. Cần bảo đảm projection của các language lồng nhau dễ hiểu và thao tác điều hướng không gây xung đột.

### Type-system composition

Expression từ language này có thể cần type được định nghĩa trong language khác. Cần thiết kế type rules và dependency rõ ràng để tránh vòng phụ thuộc hoặc kết quả không nhất quán.

### Generator composition

Generator của nhiều language có thể tham gia pipeline. Thứ tự và target của các generator phải được xác định để model cuối cùng có thể được hạ cấp hoặc sinh thành artifact mong muốn.

## 14. Generator – chuyển model thành model hoặc mã đích

Generator chuyển model của một language nguồn thành model của language đích. Đây là bước quan trọng để biến DSL cấp cao thành chương trình có thể build hoặc chạy.

Ví dụ:

~~~text
OrderWorkflow DSL
        |
        v
Workflow intermediate model
        |
        v
BaseLanguage / Java model
        |
        v
Java source / executable artifact
~~~

### Mapping rules

Generator thường sử dụng mapping rules để xác định node nguồn được chuyển thành node đích nào. Một `ActionCall` có thể trở thành method invocation; một `IfStep` trở thành cấu trúc `if`; một `Workflow` trở thành class hoặc method.

### Reduction và template

Generator có thể dùng template hoặc quy tắc giảm dần để chuyển concept cấp cao thành các concept đơn giản hơn. Sau nhiều bước, model có thể được đưa về language đích mà compiler hoặc text generator hiểu.

### Template model

Template có thể chứa node đích làm khuôn, với macro hoặc placeholder lấy dữ liệu từ node nguồn. Cách này giúp code generation có cấu trúc và kiểm tra được thay vì ghép chuỗi tùy ý.

### Mapping labels

Khi generator tạo node mới, mapping label có thể giúp theo dõi quan hệ giữa node nguồn và node đích. Điều này hữu ích cho debug, traceability và các bước generation tiếp theo.

### Generator priority và dependencies

Nếu có nhiều generator hoặc mapping rule cùng xử lý một phần model, cần xác định thứ tự và dependency. Generator không nên phụ thuộc vào thứ tự tình cờ của các module.

### Generator không phải formatter

Generator tạo một mô hình đích hoặc artifact có semantics tương ứng. Formatter chỉ thay đổi cách trình bày. Một generator có thể biến đổi cấu trúc đáng kể, ví dụ chuyển workflow thành state machine hoặc Java control flow.

## 15. Text generation

Sau khi model được chuyển về language đích hoặc một model phù hợp, text generation có thể tạo source file, cấu hình hoặc tài liệu.

Ví dụ, Java model có thể được chuyển thành `.java` source; một model cấu hình có thể được chuyển thành JSON, YAML hoặc XML; một DSL báo cáo có thể tạo SQL.

### TextGen aspect

MPS có cơ chế text generation để định nghĩa cách node được render thành văn bản. Nó thường được dùng khi model đã ở dạng phù hợp với output format.

### Line mapping

Khi sinh mã, source mapping có thể liên kết đoạn output với node nguồn. Điều này giúp compiler error ở mã đích được ánh xạ ngược về DSL.

### Generated output

Output cần được quản lý như artifact sinh ra, có thể build lại từ model. Không nên chỉnh sửa thủ công file generated nếu lần generation sau sẽ ghi đè.

### Deterministic generation

Nếu cùng model và cùng toolchain cần tạo output giống nhau, generator nên tránh phụ thuộc timestamp, thứ tự collection không xác định hoặc dữ liệu môi trường ẩn. Tính xác định giúp review diff, cache và tái lập build.

## 16. Intentions, quick fixes và refactoring

Intentions cung cấp thao tác chuyển đổi có ngữ cảnh mà người dùng có thể chủ động gọi trong editor. Quick fix thường gắn với diagnostic để đề xuất cách sửa.

Ví dụ:

- Tạo property còn thiếu.
- Chuyển literal sang constant.
- Thêm import cho reference chưa resolve.
- Đổi một action thành subtype phù hợp.
- Sinh nhánh `else` còn thiếu.
- Chuyển biểu thức sang dạng chuẩn theo quy tắc language.

### Intention

Intention thường được cung cấp khi caret nằm trên node phù hợp. Nó có thể kiểm tra điều kiện khả dụng và áp dụng model transformation khi người dùng chọn.

### Quick fix

Quick fix liên kết với lỗi hoặc warning. Ví dụ unresolved reference có thể đề xuất tạo declaration hoặc import module tương ứng.

### Refactoring

Refactoring như rename, move hoặc extract cần dựa trên node identity, reference graph và transaction của model. Không nên chỉ sửa chuỗi tên hiển thị vì reference trong MPS là quan hệ model.

### Undo/redo

Các thao tác intention/refactoring nên chạy trong command phù hợp để người dùng có thể undo/redo nhất quán. Một thao tác nhiều node cần được xử lý như một đơn vị thay đổi logic.

## 17. Kiểm tra model và validation

MPS cung cấp các cơ chế kiểm tra model thông qua typesystem, constraints và các kiểm tra bổ sung của language. Mục tiêu là phát hiện mô hình không hợp lệ trước khi generator hoặc runtime sử dụng.

Các nhóm kiểm tra có thể gồm:

- Cấu trúc: child bắt buộc có tồn tại, cardinality đúng.
- Reference: target tồn tại, đúng loại và trong scope.
- Kiểu: expression tương thích với expected type.
- Ngữ nghĩa miền: trạng thái và quan hệ đáp ứng quy tắc nghiệp vụ.
- Generator readiness: node có đủ dữ liệu để được chuyển đổi.
- Dependency: language/model cần thiết đã được khai báo.

### Error, warning và informational message

Không phải mọi vấn đề đều ngăn generation. Một warning có thể báo deprecated concept; error có thể ngăn model được xem là hợp lệ; informational message có thể gợi ý tối ưu hoặc convention.

### Validation theo giai đoạn

Một số quy tắc có thể kiểm tra ngay khi người dùng sửa node; một số cần toàn model hoặc nhiều module. Cần tránh chạy kiểm tra toàn workspace quá thường xuyên nếu nó làm editor chậm.

### Kiểm tra trước generation

Generator nên được chạy trên model đã đáp ứng các invariant cần thiết. Nếu vẫn cho phép node lỗi đi vào generator, phải có chính sách rõ ràng về fallback hoặc diagnostic generation.

## 18. Models, roots và persistence

Model trong MPS lưu các root node và cấu trúc node liên quan. Model có thể có reference đến model khác và metadata về language hoặc import.

### Root node

Root node là điểm bắt đầu của một cấu trúc trong model. Ví dụ một model có thể chứa root `Entity`, `Workflow` hoặc `Policy`.

### Model reference

Reference giữa model cần xác định model đích và node đích. MPS quản lý model identity và node identity để reference không chỉ dựa trên vị trí hoặc tên văn bản.

### Persistence

MPS có định dạng persistence riêng cho model. Người dùng thường thao tác qua workbench và không cần chỉnh trực tiếp file lưu trữ nội bộ. Nếu cần tích hợp ngoài, nên dùng API hoặc cơ chế export/import được hỗ trợ thay vì phụ thuộc vào chi tiết serialization nội bộ có thể thay đổi giữa phiên bản.

### Model import và language dependency

Một model sử dụng concept từ language khác cần khai báo language dependency phù hợp. Model reference đến dữ liệu bên ngoài cũng cần import hoặc dependency được quản lý rõ.

### Version control

Model và language definition có thể được quản lý trong hệ thống version control. Team cần thống nhất cách commit, merge và xử lý xung đột model; tránh sửa trực tiếp file persistence khi không hiểu cấu trúc và invariant của nó.

## 19. Generator và runtime dependency

Model được sinh thành Java hoặc ngôn ngữ đích khác thường phụ thuộc vào runtime library. Ví dụ DSL workflow có thể sinh code gọi `WorkflowRuntime`, `ActionRegistry` hoặc `TransactionManager`.

### Runtime contract

Generator và runtime cần thống nhất API. Nếu runtime đổi chữ ký, generator hoặc generated code cần được cập nhật tương ứng.

### Runtime module

Có thể tổ chức runtime trong solution/module riêng để language generator thêm dependency cho output. Điều này giúp model DSL không cần biết chi tiết implementation của service host.

### Generated code ownership

Generated code thường là derived artifact. Người dùng nên chỉnh sửa model nguồn hoặc runtime library thay vì sửa output thủ công, trừ khi quy trình có vùng code extension được thiết kế riêng.

### Build integration

Build cần chạy generation trước compile output. Dependency graph phải đảm bảo model/language/generator được build theo đúng thứ tự. CI nên dùng cùng toolchain và cấu hình đã pin để output có thể tái lập.

## 20. BaseLanguage và tích hợp Java

BaseLanguage là một language trong hệ sinh thái MPS có cú pháp và khái niệm gần với Java. Nó cho phép xây dựng một số logic trong môi trường MPS và là target phổ biến cho generator.

### Dùng BaseLanguage làm target

Một DSL nghiệp vụ có thể sinh model BaseLanguage, sau đó text generation tạo Java source. Điều này cho phép tái sử dụng type system, cấu trúc chương trình và hệ sinh thái Java.

### Dùng Java code trong language implementation

Một số phần triển khai language hoặc runtime có thể tích hợp Java. Cần phân biệt code dùng để triển khai language với model DSL mà người dùng cuối tạo.

### Interoperability

Generated Java có thể gọi thư viện Java thông thường. Ngược lại, MPS model có thể tham chiếu đến class hoặc API đã được import vào project. Cần quản lý classpath và dependency để editor, generator và build nhìn thấy cùng API.

### Không để DSL phụ thuộc quá sâu vào Java

Nếu mục tiêu là language đa nền tảng, nên giữ semantic model độc lập với Java và chỉ đặt Java-specific logic ở generator/runtime adapter. Nếu không, language có thể trở thành wrapper cho Java thay vì một DSL có semantics miền rõ ràng.

## 21. Quy trình phát triển một language trong MPS

Một quy trình phát triển thường đi từ metamodel đến editor, kiểm tra và generation.

~~~mermaid
flowchart TD
    A[Define domain concepts] --> B[Create language module]
    B --> C[Define Structure]
    C --> D[Design Editor]
    D --> E[Add Constraints and Behavior]
    E --> F[Define Typesystem]
    F --> G[Create Generator]
    G --> H[Create sample Solution models]
    H --> I[Validate and generate]
    I --> J[Build runtime output]
    J --> K[Iterate on language design]
~~~

### Bước 1: Xác định miền và use case

Xác định người dùng, khái niệm nghiệp vụ, loại tài liệu, hành vi cần biểu diễn và output mong muốn. Không nên bắt đầu bằng việc tạo nhiều concept trước khi hiểu các use case chính.

### Bước 2: Tạo language module

Tạo module language để chứa định nghĩa language. Xác định dependency tới language nền tảng, runtime hoặc các language khác.

### Bước 3: Định nghĩa structure

Tạo concept, property, child role, reference role, cardinality và inheritance. Kiểm tra metamodel bằng các ví dụ nhỏ.

### Bước 4: Thiết kế editor

Tạo projection dễ đọc và dễ thao tác. Xác định constant text, property cell, reference cell, child cell, placeholder và keyboard navigation.

### Bước 5: Thêm constraints và behavior

Giới hạn node hợp lệ, lựa chọn reference và cung cấp các method hỗ trợ cho concept.

### Bước 6: Định nghĩa typesystem

Thêm type inference, compatibility và diagnostic cho biểu thức hoặc quan hệ cần kiểm tra.

### Bước 7: Xây generator

Chọn target language, tạo mapping rules và template model, xác định thứ tự generator và runtime dependency.

### Bước 8: Tạo solution mẫu

Tạo model thực tế sử dụng language. Model mẫu giúp kiểm tra xem concept và editor có diễn đạt được use case không.

### Bước 9: Kiểm tra và generation

Chạy validation, sửa lỗi và kiểm tra generated model/source. Kiểm thử hành vi output thay vì chỉ xác nhận generation không báo lỗi.

### Bước 10: Tiến hóa language

Khi use case mới xuất hiện, đánh giá tác động đến metamodel, editor, type rules, generator và model đã tồn tại. Có thể cần migration hoặc compatibility strategy.

## 22. Ví dụ thiết kế DSL đơn hàng với MPS

Giả sử cần một DSL để mô tả quy trình phê duyệt và hoàn tất đơn hàng.

### Khái niệm miền

- `Order`: đơn hàng có mã, khách hàng và tổng tiền.
- `ApprovalPolicy`: tập quy tắc quyết định cần phê duyệt.
- `Workflow`: chuỗi bước xử lý.
- `Action`: thao tác như giữ hàng hoặc tạo vận đơn.
- `Condition`: điều kiện rẽ nhánh.

### Structure

~~~text
Order
  id: Identifier
  customer: CustomerReference
  total: Money

ApprovalPolicy
  rules: ApprovalRule [1..*]

ApprovalRule
  condition: Expression
  decision: ApprovalDecision

Workflow
  steps: WorkflowStep [1..*]

WorkflowStep (abstract)
  ActionStep
  IfStep
  WaitStep
~~~

### Editor projection

Một `ApprovalRule` có thể hiển thị:

~~~text
when <condition> then <decision>
~~~

Một `ActionStep` có thể hiển thị:

~~~text
perform <action reference> with <arguments>
~~~

Một `IfStep` có thể hiển thị condition ở dòng đầu, sau đó là hai vùng `then` và `else`.

### Constraints

- `ApprovalPolicy.rules` phải có ít nhất một rule.
- `ActionStep.action` chỉ tham chiếu action có capability phù hợp.
- `Order.total` phải là kiểu `Money`.
- `IfStep.condition` phải có kiểu boolean.
- `WaitStep.timeout` nếu có phải là duration dương.

### Typesystem

Typesystem xác nhận phép so sánh `Money` với `Money`, không cho phép cộng `Money` với `Customer`, và yêu cầu condition có kiểu boolean.

### Generator

Generator có thể chuyển:

- `Workflow` thành Java class hoặc method.
- `IfStep` thành Java `if` statement.
- `ActionStep` thành lời gọi runtime action registry.
- `ApprovalRule` thành rule representation hoặc decision table.

### Runtime

Generated code có thể gọi `OrderRepository`, `InventoryService`, `PaymentService` và `WorkflowRuntime`. Các service này nằm ngoài language model và được cung cấp bởi ứng dụng host.

Ví dụ cho thấy MPS hỗ trợ một language xuyên suốt từ metamodel, editor và validation đến generation và runtime integration.

## 23. Kiểm thử language và generator

Một language không thể chỉ được đánh giá bằng việc editor hiển thị đẹp. Cần kiểm thử cấu trúc, ngữ nghĩa và output.

### Structure tests

Kiểm tra concept, inheritance, role cardinality, reference và model constraints.

### Editor tests

Kiểm tra projection hiển thị đúng property/child/reference, nhập liệu, completion, navigation và thao tác cấu trúc.

### Typesystem tests

Kiểm tra expression hợp lệ, lỗi kiểu, overload, reference resolution và diagnostic.

### Generator tests

Tạo model fixture, chạy generator và so sánh generated model hoặc output với expected result. Khi có source mapping, kiểm tra mapping từ output về source node.

### End-to-end tests

Build model được sinh, chạy chương trình hoặc kiểm tra artifact cuối. Điều này xác nhận generator và runtime contract tương thích.

### Regression tests

Khi thay đổi structure hoặc generator, chạy lại các model mẫu cũ để phát hiện breaking change. Cần lưu ý model có thể được serialize theo format/version khác với language version.

### Test migration

Nếu language evolution thay đổi concept hoặc role, kiểm tra model cũ có được migrate đúng và reference vẫn trỏ đúng node.

## 24. Debugging và quan sát quá trình generation

Khi output không đúng, cần biết lỗi nằm ở model nguồn, type rules, generator mapping hay runtime.

### Kiểm tra model nguồn

Xác nhận node có concept và property đúng, reference trỏ đúng target và model không chứa lỗi validation.

### Kiểm tra generator trace

Theo dõi mapping rule nào đã được áp dụng, node nguồn nào tạo node đích nào và bước reduction tiếp theo.

### Kiểm tra generated model

Nếu generator tạo một intermediate model, mở và kiểm tra model đó trước khi text generation. Điều này giúp phân biệt lỗi mapping với lỗi render text.

### Source mapping

Mapping từ node nguồn đến generated code giúp điều hướng lỗi compiler hoặc runtime về đúng phần DSL. Nếu không có mapping, người dùng có thể chỉ thấy lỗi ở Java output mà không biết sửa node nào.

### Build logs

Build log cần phân biệt lỗi language module, generator, dependency, text generation và compile target. Một lỗi dependency có thể khiến concept không được resolve dù editor vẫn mở được model cũ.

## 25. Quản lý language version và model evolution

Language được dùng trong nhiều model có thể cần tiến hóa trong thời gian dài. Thay đổi metamodel có thể ảnh hưởng model đã lưu, editor, constraints và generator.

### Thêm concept hoặc property

Thêm một concept hoặc property mới có thể tương thích nếu có default hoặc migration rõ ràng. Cần xem model cũ có thể được đọc và chỉnh sửa không.

### Đổi hoặc xóa role

Đổi tên child/reference role hoặc thay cardinality có thể làm persistence và generator cũ không còn phù hợp. Cần migration và regression test.

### Thay đổi semantics

Một property giữ nguyên tên nhưng thay meaning là breaking change về ngữ nghĩa. Có thể cần tăng language version hoặc cung cấp migration có chủ đích.

### Generator version

Generator mới có thể sinh output khác từ cùng model. Nên ghi nhận toolchain version trong build để tái lập output.

### Model migration

Migration có thể chuyển node concept, property, role và reference. Phải bảo toàn node identity khi phù hợp hoặc cập nhật mọi reference đến node được thay thế.

## 26. Làm việc nhóm và version control

Language definition và model thường được phát triển bởi nhiều người. Team cần quy ước ownership và workflow để tránh xung đột.

### Tách language và solution

Nhóm language platform có thể sở hữu language module, còn nhóm nghiệp vụ sở hữu solution chứa model. Điều này giúp quản lý release và dependency rõ ràng.

### Commit theo đơn vị logic

Commit nên chứa thay đổi có thể hiểu được: concept mới cùng editor, type rules và generator tương ứng; hoặc model được cập nhật theo language version mới.

### Merge model

Merge file model có thể phức tạp nếu hai người cùng sửa node hoặc reference. Cần dùng quy trình merge được hỗ trợ và kiểm tra model sau merge, không xử lý file persistence như văn bản tùy ý.

### Shared language release

Language được dùng bởi nhiều project nên có version và release note. Thay đổi breaking cần được thông báo và có kế hoạch migration.

### CI

CI có thể build language module, kiểm tra generator, build solution mẫu và chạy regression test. Nên pin MPS version và dependency để kết quả nhất quán giữa máy phát triển và CI.

## 27. Tích hợp với công cụ và hệ sinh thái bên ngoài

MPS có thể tham gia một quy trình phát triển lớn hơn, nơi source, generated code và dữ liệu được trao đổi với công cụ khác.

### Import từ text DSL

Nếu tổ chức đã có source text, có thể xây importer hoặc parser chuyển text thành MPS model. Cần định nghĩa grammar, mapping và cách xử lý cấu trúc không biểu diễn được trong metamodel.

### Export sang text

Text generation có thể tạo cú pháp DSL chuẩn, JSON, XML, SQL hoặc mã đích. Cần xác định output là canonical representation hay chỉ là artifact trình bày.

### API và automation

Các tác vụ tạo model, chạy generator hoặc kiểm tra model có thể được tích hợp vào build/automation theo API và công cụ được MPS hỗ trợ. Cần tránh phụ thuộc vào internal implementation không ổn định.

### IDE và plugin

MPS có thể mở rộng qua plugin hoặc tích hợp với các công cụ trong hệ sinh thái JetBrains. Khi phát triển plugin, cần kiểm tra API compatibility với phiên bản MPS/IDE mục tiêu.

### Interchange format

Nếu nhiều hệ thống cần trao đổi model, nên định nghĩa format trung gian có schema và version thay vì phụ thuộc vào file persistence nội bộ. Import/export phải bảo toàn ID, reference và semantics cần thiết.

## 28. Khi nào nên chọn MPS?

MPS phù hợp khi lợi ích của structured modeling và language composition lớn hơn chi phí học projectional editing và phát triển language workbench.

Các tình huống phù hợp:

- DSL có cấu trúc phong phú và nhiều loại node.
- Cần kết hợp nhiều language trong cùng model.
- Cần notation không thuần văn bản như bảng, form hoặc diagram.
- Muốn reference có identity và navigation chính xác.
- Cần typesystem và validation riêng cho miền nghiệp vụ.
- Muốn sinh code hoặc artifact từ model có cấu trúc.
- Language được dùng lâu dài bởi nhiều nhóm và cần quản trị evolution.
- Người dùng cuối có thể hưởng lợi từ editor được giới hạn theo concept và context.

### Khi nào có thể chọn công cụ text-based?

Nếu DSL rất nhỏ, cú pháp gần JSON/YAML, người dùng chủ yếu chỉnh sửa bằng text editor và không cần language composition phức tạp, một parser truyền thống cùng schema validator có thể đơn giản hơn.

Nếu mục tiêu chính là cấu hình ngắn, dễ diff và chỉnh sửa bằng bất kỳ editor nào, projectional workbench có thể là quá nặng. Nếu người dùng cần thao tác text tự do hoặc quy trình tích hợp Git dựa nhiều vào line-oriented diff, cần đánh giá trải nghiệm projectional editor trước khi quyết định.

### Các tiêu chí lựa chọn

| Tiêu chí | MPS có lợi thế khi... | Cần cân nhắc khi... |
|---|---|---|
| Cấu trúc language | Metamodel nhiều concept và quan hệ. | Cú pháp đơn giản, schema tĩnh. |
| Editor | Cần projection nhiều dạng. | Người dùng chỉ muốn text editor. |
| Composition | Nhiều language cần lồng ghép. | Một grammar đơn giản là đủ. |
| Validation | Có type rules và constraints miền. | Kiểm tra JSON Schema hoặc lint đơn giản là đủ. |
| Generation | Cần nhiều bước model transformation. | Chỉ cần template text nhỏ. |
| Adoption | Có thể đào tạo người dùng và chuẩn hóa workbench. | Người dùng phân tán, không thể thay đổi thói quen editor. |
| Governance | Language là tài sản nền tảng dài hạn. | Nhu cầu chỉ mang tính tạm thời hoặc thử nghiệm nhỏ. |

## 29. Các hạn chế và rủi ro khi sử dụng MPS

### Đường cong học tập

Người phát triển cần học concept, model, editor cells, typesystem, generator và cách MPS quản lý project. Người dùng cuối cũng cần làm quen với projectional editing.

### Thiết kế editor tốn công

Editor khó sử dụng có thể khiến người dùng mất nhiều thời gian hơn so với text editor. Cần thử nghiệm với người dùng thực tế, đặc biệt với thao tác nhập liệu, copy/paste và navigation.

### Interoperability

Các công cụ text-based không thể luôn chỉnh sửa trực tiếp model MPS. Cần importer/exporter hoặc canonical interchange format nếu hệ sinh thái yêu cầu.

### Generator complexity

Generator nhiều bước có thể khó debug nếu mapping và dependency không được tổ chức rõ. Cần chia generator thành các transformation có mục tiêu cụ thể và test từng bước.

### Language evolution

Thay đổi metamodel có thể ảnh hưởng nhiều model đã tồn tại. Cần versioning và migration strategy từ đầu, không đợi đến khi có breaking change.

### Dependency và version compatibility

Language, plugin, generator và MPS platform cần tương thích. Việc nâng cấp nền tảng cần được kiểm thử với project và model quan trọng.

### Hiệu năng

Model lớn, nhiều reference và typesystem rule phức tạp có thể làm editor hoặc validation chậm. Cần thiết kế dependency và kiểm tra gia tăng, tránh truy vấn toàn workspace không cần thiết trong mỗi thao tác.

## 30. Những lỗi thiết kế language thường gặp

**Bắt đầu từ editor trước metamodel.** Nếu concept và quan hệ chưa rõ, editor sẽ chứa nhiều workaround và khó tiến hóa.

**Tạo concept quá nhỏ hoặc quá nhiều.** Mô hình trở nên phức tạp nhưng không tăng giá trị ngữ nghĩa. Chỉ tạo concept riêng khi nó có cấu trúc, hành vi hoặc semantics đáng kể.

**Dùng property cho dữ liệu cần identity/reference.** Một tên kiểu lưu dưới dạng chuỗi khó bảo đảm resolve, rename và navigation. Nếu nó đại diện một node trong model, cân nhắc reference role.

**Nhầm child với reference.** Containment và cross-reference có vòng đời khác nhau. Chọn sai có thể gây lỗi khi xóa, copy hoặc migrate node.

**Editor projection quá khác tư duy miền.** Người dùng phải hiểu cách MPS tổ chức node thay vì cách nghiệp vụ diễn đạt. Projection nên ưu tiên ngôn ngữ của người dùng.

**Constraints chứa logic ngữ nghĩa quá lớn.** Quy tắc type và semantics nên đặt đúng aspect để dễ kiểm tra và tái sử dụng.

**Generator làm quá nhiều việc trong một bước.** Transformation lớn khó debug và khó kiểm thử. Nên chia thành các giai đoạn có intermediate model rõ.

**Không kiểm thử generated output.** Generation thành công không chứng minh chương trình đích đúng. Cần build hoặc thực thi output trong test.

**Không có migration cho model cũ.** Một thay đổi structure có thể làm project cũ không mở hoặc không generate được.

**Phụ thuộc vào file persistence nội bộ.** Tích hợp ngoài dựa vào chi tiết lưu trữ không công bố có thể hỏng khi nâng cấp MPS.

**Không kiểm tra trải nghiệm người dùng.** Projectional editor cần được thử nghiệm với người viết model, không chỉ với người phát triển language.

## 31. Quy trình triển khai một dự án DSL bằng MPS

Một quy trình dự án có thể được tổ chức như sau:

1. **Khám phá miền:** phỏng vấn người dùng, thu thập thuật ngữ, quy trình, dữ liệu và ví dụ.
2. **Xác định phạm vi DSL:** chọn use case quan trọng và ranh giới với hệ thống host.
3. **Thiết kế metamodel:** concept, property, child, reference, cardinality và inheritance.
4. **Thiết kế projection:** tạo editor cho các thao tác thường dùng và thử với người dùng.
5. **Định nghĩa semantics:** constraints, scope, behavior và typesystem.
6. **Xây language composition:** chọn language nền tảng và dependency cần tái sử dụng.
7. **Thiết kế generator:** xác định target model, transformation stages, runtime contract và mapping.
8. **Tạo sample models:** dùng ví dụ thực tế để kiểm chứng language có diễn đạt đủ miền không.
9. **Kiểm thử:** structure, editor, typesystem, generator, runtime và migration.
10. **Đóng gói và phát hành:** quản lý module, dependency, version và tài liệu sử dụng.
11. **Tích hợp CI:** build language, generate model và kiểm thử output trên toolchain đã pin.
12. **Thu thập phản hồi:** cải thiện editor, semantics và migration theo nhu cầu thực tế.

## 32. Checklist trước khi phát hành một language MPS

Trước khi cung cấp language cho người dùng, cần xác nhận:

- Metamodel có phản ánh đúng khái niệm và quan hệ miền không?
- Concept, property, child role và reference role được phân biệt rõ không?
- Cardinality và inheritance có hợp lý không?
- Editor có dễ nhập liệu, điều hướng và hiểu không?
- Projection có hỗ trợ completion và placeholder phù hợp không?
- Constraints có lọc node/reference theo context đúng không?
- Typesystem có kiểm tra các biểu thức và kiểu quan trọng không?
- Diagnostic có chỉ ra vị trí và nguyên nhân đủ rõ không?
- Language composition và dependency có được khai báo đầy đủ không?
- Generator có output ổn định và mapping có thể truy vết không?
- Runtime dependency có version và contract rõ không?
- Model cũ có thể được đọc hoặc migrate khi language thay đổi không?
- CI có build language và kiểm thử generated artifact không?
- Import/export có bảo toàn identity và reference cần thiết không?
- Người dùng cuối đã thử projectional editing trên use case thực tế chưa?
- Có tài liệu về version, limitation và quy trình hỗ trợ không?

## 33. Kết quả cần có sau khi thiết kế DSL bằng MPS

Một dự án language workbench hoàn chỉnh thường tạo ra:

- **Language metamodel:** concept, property, child role, reference role, cardinality và inheritance.
- **Projectional editor:** editor cells, placeholder, navigation, completion và presentation cho từng concept.
- **Constraints:** quy tắc tạo node, chọn reference và điều kiện cấu trúc theo context.
- **Behavior:** helper method và hành vi gắn với concept.
- **Typesystem:** type inference, compatibility và semantic diagnostics.
- **Language composition:** dependency và cách sử dụng các language khác.
- **Generator:** mapping rules, template model, transformation pipeline và source mapping.
- **Text generation/runtime:** output format, runtime contract và generated artifact.
- **Sample solutions:** model thực tế chứng minh language diễn đạt được use case.
- **Test suite:** structure, editor, type, generator, runtime và migration tests.
- **Release strategy:** module ownership, versioning, compatibility và migration.
- **User documentation:** cách tạo, chỉnh sửa, kiểm tra, generate và tích hợp model.

JetBrains MPS là một language workbench giúp xây dựng DSL dựa trên mô hình có cấu trúc và projectional editor. Người phát triển định nghĩa concept và quan hệ trong structure aspect, thiết kế cách trình bày trong editor aspect, bổ sung constraints, behavior và typesystem, rồi dùng generator để chuyển model sang language hoặc artifact đích. Cách tiếp cận này tạo điều kiện cho language composition, reference có identity và nhiều notation trên cùng một mô hình. Để dự án thành công, cần đầu tư vào metamodel dễ hiểu, editor phù hợp với người dùng, generator có thể truy vết, kiểm thử output và chiến lược tiến hóa model. MPS đặc biệt có giá trị khi DSL là một tài sản dài hạn của tổ chức và cần một workbench thống nhất từ định nghĩa language đến sử dụng và sinh mã.
