# Cây phác thảo

Trong trình soạn thảo cho một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), người dùng thường làm việc với tài liệu dài gồm nhiều khai báo, kiểu, quy tắc, workflow, hàm và cấu trúc lồng nhau. Khi chỉ nhìn vào văn bản từ trên xuống dưới, việc tìm một thành phần, hiểu quan hệ cha–con hoặc chuyển nhanh đến một khai báo có thể mất thời gian. **Cây phác thảo** (*outline tree* hoặc *document outline*) là thành phần giao diện trình bày cấu trúc logic của tài liệu dưới dạng cây để người dùng quan sát, điều hướng và thao tác với các thành phần đó.

Ví dụ, một tài liệu DSL mô tả đơn hàng có thể chứa:

~~~text
module Sales {
    entity Customer {
        id: CustomerId;
        email: EmailAddress;
    }

    entity Order {
        customer: Customer;
        total: Money;
    }

    policy OrderApproval {
        when order.total >= 1000 then ManagerApproval;
    }

    workflow FulfillOrder {
        validateOrder;
        reserveInventory;
        createShipment;
    }
}
~~~

Cây phác thảo có thể hiển thị `Sales` ở cấp cao nhất, bên dưới là `Customer`, `Order`, `OrderApproval` và `FulfillOrder`. Mỗi phần tử có thể mở rộng để xem các thuộc tính, điều kiện hoặc bước con. Khi người dùng chọn `OrderApproval`, editor đưa con trỏ đến khai báo tương ứng; khi con trỏ đang ở trong `createShipment`, cây có thể tự chọn node `FulfillOrder` hoặc node hành động đó.

Cây phác thảo giúp người dùng hiểu cấu trúc của tài liệu mà không phải đọc toàn bộ nội dung. Nó thường được xây dựng từ AST, semantic model hoặc symbol information do language service cung cấp. Một outline tốt phải phản ánh đúng cấu trúc mà DSL công bố, cập nhật khi tài liệu thay đổi, giữ vị trí điều hướng chính xác và hỗ trợ tài liệu chưa hoàn chỉnh trong lúc người dùng đang gõ.

## 1. Cây phác thảo là gì?

Cây phác thảo là một biểu diễn phân cấp của các phần tử có ý nghĩa trong tài liệu. Mỗi node thường đại diện cho một khai báo hoặc cấu trúc có thể được đặt tên, chẳng hạn module, namespace, entity, type, function, policy, rule, workflow, task hoặc section.

Một node outline thường có:

- Tên hiển thị.
- Loại phần tử hoặc biểu tượng phân biệt.
- Vị trí nguồn để điều hướng đến khai báo.
- Quan hệ cha–con với các node khác.
- Thông tin phụ như kiểu, tham số, trạng thái hoặc phạm vi.
- Khả năng mở rộng và thu gọn.
- Có thể có range bao trùm để hỗ trợ folding hoặc chọn node theo con trỏ.

Ví dụ cây phác thảo:

~~~text
Sales
├── Customer
│   ├── id: CustomerId
│   └── email: EmailAddress
├── Order
│   ├── customer: Customer
│   └── total: Money
├── OrderApproval
│   └── rule: when order.total >= 1000
└── FulfillOrder
    ├── validateOrder
    ├── reserveInventory
    └── createShipment
~~~

Đây là cách trình bày cấu trúc, không phải bản sao nguyên văn của tài liệu. Một số chi tiết cú pháp như dấu ngoặc, dấu chấm phẩy hoặc comment có thể không xuất hiện trong outline vì chúng không tạo thành node cấu trúc độc lập.

### Cây phác thảo khác gì Project Explorer?

Project Explorer thường trình bày cấu trúc file và thư mục của workspace. Cây phác thảo trình bày cấu trúc logic bên trong một tài liệu hoặc một mô hình.

| Thành phần | Cấu trúc hiển thị | Ví dụ node |
|---|---|---|
| Project Explorer | Workspace, folder, file | `models/`, `order.dsl` |
| Document Outline | Khai báo và cấu trúc trong tài liệu hiện tại | `Order`, `OrderApproval` |
| Symbol Browser | Symbol trên nhiều file/module | `Sales.Order`, `Finance.Invoice` |
| Call Hierarchy | Quan hệ gọi hàm hoặc action | `FulfillOrder` gọi `reserveInventory` |
| Type Hierarchy | Quan hệ kế thừa hoặc triển khai | `PreferredCustomer extends Customer` |

Các thành phần này có thể dùng chung symbol index nhưng phục vụ những câu hỏi khác nhau. Không nên biến document outline thành một bản sao của toàn bộ cây thư mục hoặc toàn bộ symbol graph.

### Cây phác thảo khác gì AST Viewer?

AST Viewer thường hiển thị chi tiết node cú pháp phục vụ developer compiler: `IfExpression`, `IdentifierToken`, `BlockNode`, source span và các node trung gian. Outline hướng đến người viết DSL nên chọn các cấu trúc có ý nghĩa điều hướng và trình bày tên dễ hiểu.

Một `BinaryExpression` thường không cần xuất hiện như một node riêng trong outline, nhưng `Policy`, `Rule` hoặc `Workflow` có thể cần. Một DSL đồ họa hoặc DSL mô hình có thể có outline dựa trên semantic model thay vì AST văn bản.

## 2. Mục đích của cây phác thảo trong editor

### Điều hướng nhanh

Người dùng có thể chọn một khai báo trong outline để đi đến vị trí nguồn, thay vì tìm thủ công bằng cuộn trang hoặc tìm chuỗi.

### Hiểu cấu trúc tổng thể

Outline cho thấy tài liệu chứa những module, entity, policy hoặc workflow nào và các thành phần được lồng nhau ra sao. Đây là cách nhanh để nắm bố cục của một tài liệu chưa quen thuộc.

### Nhận biết vị trí hiện tại

Khi con trỏ di chuyển, editor có thể đồng bộ lựa chọn trong outline để người dùng biết mình đang ở trong module, function hoặc rule nào.

### Thu gọn và mở rộng

Người dùng có thể thu gọn các nhóm không cần xem, giữ tập trung vào phần đang chỉnh sửa và giảm nhiễu trong tài liệu lớn.

### Khám phá symbol

Outline có thể hiển thị loại, visibility, tham số, kiểu trả về hoặc trạng thái của phần tử để người dùng hiểu nhanh nội dung mà không phải mở từng khai báo.

### Hỗ trợ các thao tác biên tập

Một số editor cho phép đổi tên, di chuyển, tạo phần tử con hoặc xóa node từ outline. Các thao tác này phải dựa trên semantic identity và áp dụng thay đổi vào nguồn theo quy tắc DSL.

## 3. Những phần tử nào nên xuất hiện trong outline?

Không phải mọi node AST đều nên trở thành node outline. Một phần tử phù hợp thường có tên hoặc vai trò rõ ràng, có thể điều hướng đến, và có ý nghĩa với người viết DSL.

Các phần tử thường xuất hiện:

- Module, package và namespace.
- Entity, record, class, type hoặc schema.
- Field, property và association.
- Function, procedure và action.
- Policy, rule và constraint.
- Workflow, state machine và task.
- Event, command và query.
- Section hoặc block có tên.
- Test case hoặc scenario nếu DSL hỗ trợ.
- Resource, connector hoặc declaration có định danh.

Các phần tử thường không cần hiển thị riêng:

- Dấu ngoặc và dấu phân cách.
- Token punctuation.
- Literal đơn lẻ bên trong biểu thức.
- Node biểu thức trung gian không có tên.
- Comment thông thường, trừ khi comment được dùng làm documentation node.
- Node lỗi tạm thời không có cấu trúc ổn định.

### Outline theo ngữ nghĩa của DSL

Một DSL workflow có thể ưu tiên workflow và các bước; DSL mô hình dữ liệu ưu tiên entity, field và relation; DSL quy tắc ưu tiên policy và rule. Không nên áp dụng cùng một cây cho mọi loại DSL nếu cấu trúc miền khác nhau.

Ví dụ outline cho DSL truy vấn:

~~~text
CustomerReport
├── Source: Customers
├── Join: Orders
├── Filter: status == ACTIVE
├── Group By: region
└── Select
    ├── customerCount
    └── totalRevenue
~~~

Ví dụ outline cho DSL workflow:

~~~text
OrderFulfillment
├── ValidateOrder
├── ReserveInventory
├── CapturePayment
├── On PaymentDeclined
│   ├── ReleaseInventory
│   └── RejectOrder
└── CreateShipment
~~~

## 4. Mô hình dữ liệu của một outline node

Outline nên dùng một mô hình dữ liệu ổn định, không phụ thuộc trực tiếp vào widget giao diện hoặc class AST nội bộ.

Một node có thể gồm:

~~~text
OutlineNode
  id
  name
  kind
  detail
  parentId
  children
  selectionRange
  fullRange
  sourceId
  version
  tags
~~~

Ý nghĩa các trường:

| Trường | Vai trò |
|---|---|
| `id` | Identity ổn định trong snapshot hoặc symbol index. |
| `name` | Tên chính hiển thị trong cây. |
| `kind` | Loại phần tử như module, entity, action hoặc rule. |
| `detail` | Thông tin phụ như kiểu, tham số hoặc signature. |
| `parentId` | Node cha trong outline. |
| `children` | Các node con theo cấu trúc DSL. |
| `selectionRange` | Range nhỏ dùng khi chọn node hoặc điều hướng. |
| `fullRange` | Range bao trùm node và nội dung con. |
| `sourceId` | Tài liệu hoặc nguồn chứa phần tử. |
| `version` | Phiên bản nguồn mà vị trí và node tham chiếu. |
| `tags` | Trạng thái phụ như deprecated, private hoặc generated. |

### Selection range và full range

Hai range này phục vụ mục đích khác nhau. `selectionRange` thường bao trùm tên khai báo để khi chọn node, editor đặt con trỏ vào đúng tên. `fullRange` bao trùm toàn bộ cấu trúc để xác định node chứa con trỏ hoặc hỗ trợ folding.

Ví dụ:

~~~text
entity Order {
       ^^^^^
    customer: Customer;
    total: Money;
}
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
~~~

Range tên `Order` có thể là selection range; range từ `entity` đến dấu `}` là full range. Cách chọn range cần nhất quán giữa provider, editor và các thao tác điều hướng.

### ID và tên hiển thị

Không nên dùng tên hiển thị làm identity duy nhất. Hai function có thể cùng tên trong hai namespace khác nhau; rename cũng làm tên thay đổi nhưng node vẫn là cùng một symbol. ID có thể là symbol identity, node ID trong document hoặc khóa kết hợp với source identity.

### Node có thể không có tên

Một số cấu trúc có vai trò nhưng không có identifier, chẳng hạn nhánh `else`, khối `catch` hoặc section ẩn danh. Có thể hiển thị nhãn suy ra như `Else branch` hoặc `Catch PaymentError`, nhưng ID và source range vẫn phải phân biệt được.

## 5. Xây dựng cây từ AST hoặc semantic model

Parser tạo AST phản ánh cú pháp. Semantic analysis bổ sung symbol, kiểu và reference. Outline provider chuyển những dữ liệu đó thành một cây gọn dành cho giao diện.

Quy trình khái quát:

~~~mermaid
flowchart TD
    A[Document text] --> B[Lexer and parser]
    B --> C[AST / CST]
    C --> D[Semantic analysis]
    D --> E[Outline provider]
    E --> F[Outline node model]
    F --> G[Tree view]
    G --> H[Navigation / reveal / folding]
~~~

### Dùng AST

Nếu outline chỉ cần khai báo cú pháp, AST có thể đủ. Provider duyệt các node như `ModuleDeclaration`, `EntityDeclaration`, `FunctionDeclaration` và tạo node outline.

### Dùng semantic model

Nếu outline cần symbol đã resolve, loại, visibility hoặc quan hệ cross-file, semantic model phù hợp hơn. Ví dụ, một node action có thể hiển thị signature sau khi type resolution hoàn tất.

### Kết hợp AST và semantic metadata

Một lựa chọn phổ biến là dùng AST để xác định vị trí và cấu trúc, sau đó bổ sung metadata từ semantic model. Cách này giữ được source range chính xác và cung cấp thông tin ngữ nghĩa phong phú.

### Không để UI tự phân tích DSL

Widget outline không nên tự dùng regex để tìm `entity`, `workflow` hoặc `policy`. Regex dễ sai với comment, string, nested block, escaped identifier và cấu trúc chưa hoàn chỉnh. Parsing nên thuộc language service; UI chỉ trình bày model đã được cung cấp.

## 6. Quy tắc phân cấp cha–con

Quan hệ cha–con trong outline phải phản ánh cấu trúc logic được DSL định nghĩa.

Ví dụ:

~~~text
module Sales {
    entity Order {
        id: OrderId;
        total: Money;
    }
}
~~~

Cây có thể là:

~~~text
Sales
└── Order
    ├── id
    └── total
~~~

Một số quyết định cần được quy định:

- Field là con trực tiếp của entity hay gom trong nhóm `Properties`?
- Rule nằm dưới policy hay hiển thị cùng cấp với policy?
- Workflow step lồng theo block hay chỉ hiển thị bước cấp cao?
- Local function nằm dưới function chứa nó hay ở cấp module?
- Import và reference có phải node outline hay chỉ là metadata?
- Anonymous block có được hiển thị hay được làm phẳng?

### Cây cấu trúc và cây tham chiếu

Outline thường biểu diễn containment hoặc lexical nesting. Một symbol có thể tham chiếu đến symbol khác mà không trở thành con của nó. Ví dụ `Order.customer` tham chiếu đến `Customer`, nhưng `Customer` không nên xuất hiện như node con của `Order` chỉ vì có quan hệ tham chiếu.

Nếu cần xem quan hệ tham chiếu, có thể cung cấp panel riêng như References, Call Hierarchy hoặc Dependency Graph. Trộn mọi reference vào outline có thể tạo vòng lặp hoặc cây khó hiểu.

### Flattening

Một số node cú pháp chỉ làm cây sâu hơn nhưng không giúp điều hướng. Provider có thể bỏ qua node wrapper và đưa con lên cấp cha, miễn là không làm mất ngữ nghĩa hoặc khiến tên node trở nên mơ hồ.

## 7. Sắp xếp node trong cây

Thứ tự node có ảnh hưởng đến khả năng hiểu và điều hướng.

Các chiến lược phổ biến:

- **Source order:** giữ đúng thứ tự khai báo trong tài liệu.
- **Alphabetical:** sắp xếp theo tên.
- **Kind grouping:** nhóm entity, function, rule hoặc workflow theo loại.
- **Custom order:** theo quy tắc miền hoặc metadata do người dùng khai báo.

### Source order

Đây thường là mặc định dễ hiểu nhất cho document outline vì người dùng nhìn thấy cây tương ứng với thứ tự văn bản. Nó cũng giúp so sánh outline với tài liệu nguồn.

### Alphabetical order

Sắp xếp theo tên giúp tìm symbol trong tài liệu có nhiều khai báo, nhưng vị trí cây không còn phản ánh thứ tự thực thi hoặc thứ tự khai báo. Có thể cung cấp như một chế độ tùy chọn.

### Kind grouping

Có thể nhóm thành:

~~~text
Sales
├── Entities
│   ├── Customer
│   └── Order
├── Policies
│   └── OrderApproval
└── Workflows
    └── FulfillOrder
~~~

Nhóm tổng hợp như `Entities` có thể là node ảo do UI tạo, không có source range. Cần phân biệt node ảo với node nguồn thật để thao tác điều hướng và selection không bị nhầm.

### Thứ tự ngữ nghĩa

Với DSL workflow, thứ tự step thường quan trọng. Không được sắp xếp các step theo tên nếu điều đó làm người dùng hiểu sai thứ tự thực thi. Nếu cung cấp sort mode, cần biểu thị rõ đó là cách trình bày và giữ khả năng quay về source order.

## 8. Nhãn, biểu tượng và thông tin phụ

Node outline cần đủ thông tin để phân biệt các phần tử mà không làm cây quá rộng.

### Label

Label thường gồm tên khai báo. Nếu có overload, có thể thêm signature:

~~~text
calculateTotal(items: List<Item>): Money
calculateTotal(order: Order): Money
~~~

### Detail

Detail là thông tin phụ hiển thị sau tên, ví dụ `: Money`, `public`, `deprecated` hoặc số lượng rule. Không nên đưa toàn bộ source text vào detail.

### Icon

Icon có thể phân biệt loại node:

| Loại | Ý nghĩa biểu tượng |
|---|---|
| Module | Nhóm namespace hoặc package. |
| Entity | Mô hình dữ liệu. |
| Field | Thuộc tính. |
| Function | Hàm có giá trị trả về. |
| Action | Hành động có thể được gọi. |
| Policy | Tập quy tắc. |
| Rule | Một quy tắc cụ thể. |
| Workflow | Quy trình nhiều bước. |
| Event | Sự kiện. |
| Type | Kiểu dữ liệu. |

Icon nên có tooltip hoặc nhãn trợ năng để người dùng không phải dựa vào màu hoặc hình dạng đơn thuần.

### Trạng thái node

Outline có thể hiển thị badge hoặc decoration cho deprecated, private, abstract, generated, unresolved hoặc có diagnostic. Cần tránh quá nhiều màu và biểu tượng làm cây khó đọc.

### Không làm lộ dữ liệu nhạy cảm

Nếu label hoặc detail được suy ra từ giá trị dữ liệu runtime, không nên hiển thị thông tin nhạy cảm trong outline. Outline nên chủ yếu hiển thị cấu trúc và metadata khai báo.

## 9. Điều hướng từ outline đến editor

Chọn một node outline thường đưa người dùng đến vị trí khai báo trong editor.

Quy trình:

1. Người dùng chọn node.
2. UI lấy source ID và selection range của node.
3. Editor xác định đúng tài liệu hoặc tab.
4. Editor chuyển con trỏ đến range.
5. Editor cuộn để range hiển thị.
6. Có thể chọn tên khai báo hoặc highlight tạm thời.

### Điều hướng đến selection range

Thông thường, chọn node `Order` nên đưa con trỏ đến tên `Order`, không nhất thiết đến đầu file hoặc toàn block. Đây là lý do selection range cần được lưu riêng.

### Tài liệu chưa mở

Nếu node đến từ tài liệu khác, editor cần mở đúng URI hoặc resource. Nếu tài liệu không còn tồn tại, UI nên báo trạng thái không thể điều hướng thay vì nhảy đến một offset trong file hiện tại.

### Nhiều editor group

Trong IDE có nhiều tab hoặc editor group, cần quy định mở trong editor đang hoạt động, mở tab mới hay chuyển sang editor đã có. Việc chọn node không nên vô tình thay đổi layout theo cách bất ngờ.

### Điều hướng lịch sử

Outline navigation có thể được tích hợp với back/forward navigation. Người dùng có thể quay lại vị trí trước khi chọn node. History cần lưu document identity và range, không chỉ một số dòng.

## 10. Đồng bộ con trỏ và lựa chọn node hiện tại

Khi con trỏ di chuyển trong tài liệu, outline có thể tự chọn node chứa vị trí đó. Tính năng này thường được gọi là *follow cursor*, *reveal active symbol* hoặc *synchronize outline*.

### Tìm node chứa vị trí

Giả sử con trỏ đang ở offset `p`. Provider có thể tìm node có `fullRange` chứa `p`, rồi chọn node cụ thể nhất theo quy tắc ưu tiên.

Ví dụ:

~~~text
Workflow FulfillOrder {
    if order.isPaid {
        createShipment(order);
    }
}
~~~

Nếu con trỏ nằm trong lời gọi `createShipment`, node active có thể là `FulfillOrder` nếu outline chỉ hiển thị workflow. Nếu outline hiển thị từng step, node active có thể là `createShipment` và cha của nó là workflow.

### Chọn node sâu nhất

Khi nhiều range lồng nhau chứa vị trí, thường chọn node có range nhỏ nhất hoặc node sâu nhất trong cây. Tuy nhiên, nếu một node không được hiển thị, cần tìm ancestor gần nhất đang có trong outline.

### Tránh nhảy lựa chọn liên tục

Khi người dùng gõ gần ranh giới hai node, active selection có thể thay đổi nhanh. Có thể dùng debounce nhẹ hoặc chỉ cập nhật khi caret ổn định, nhưng phải giữ cảm giác phản hồi nhanh.

### Không cuộn outline ngoài ý muốn

Việc đồng bộ node active không nhất thiết phải mở mọi ancestor hoặc cuộn outline mỗi lần caret di chuyển. Người dùng có thể đang duyệt cây ở một vị trí khác. Nên có tùy chọn theo dõi con trỏ và hành vi reveal được kiểm soát.

## 11. Mở rộng, thu gọn và folding

Outline tree có thể mở rộng hoặc thu gọn node để kiểm soát lượng thông tin hiển thị.

### Expand và collapse

- Expand hiển thị các node con.
- Collapse ẩn node con nhưng giữ node cha.
- Expand all mở mọi cấp.
- Collapse all thu gọn về cấp gốc hoặc cấp đã định nghĩa.

### Giữ trạng thái mở rộng

Trạng thái mở rộng có thể được giữ khi tài liệu cập nhật. Nếu chỉ dùng vị trí dòng làm khóa, chèn dòng ở đầu có thể làm trạng thái gắn nhầm node. Nên dùng stable node ID hoặc symbol identity khi có thể.

### Folding trong editor

Outline collapse và code folding là hai tính năng liên quan nhưng khác nhau. Collapse outline chỉ ẩn node trong cây; folding ẩn một đoạn văn bản trong editor. Cùng `fullRange` có thể hỗ trợ cả hai, nhưng thao tác và trạng thái phải độc lập.

### Folding range

Một khai báo có thể tạo folding range từ dòng mở đến dòng đóng. DSL có thể có folding cho module, entity, function, policy, workflow, comment nhiều dòng hoặc region đặc biệt.

### Range lồng nhau

Khi các folding range lồng nhau, editor cần xử lý thứ tự và quy tắc overlap. Parser nên cung cấp range hợp lệ; UI không nên tự suy đoán dấu ngoặc bằng tìm kiếm chuỗi.

## 12. Tìm kiếm và lọc trong cây phác thảo

Với tài liệu có nhiều khai báo, tìm kiếm outline giúp thu hẹp danh sách node.

Các cách lọc phổ biến:

- Theo tên hoặc prefix.
- Theo loại node như entity, function, policy hoặc workflow.
- Theo visibility hoặc trạng thái deprecated.
- Theo phạm vi namespace.
- Chỉ hiển thị node cấp cao hoặc tất cả node.

### Fuzzy search

Fuzzy search cho phép gõ một phần tên hoặc ký tự đầu để tìm node. Ví dụ gõ `fo` có thể tìm `FulfillOrder`. Kết quả nên hiển thị breadcrumb hoặc tên cha để phân biệt các symbol trùng tên.

### Filter không thay đổi dữ liệu nguồn

Lọc chỉ ảnh hưởng cách trình bày cây. Không nên làm mất node khỏi semantic model hoặc thay đổi thứ tự source. Khi bỏ filter, cây phải khôi phục được trạng thái phù hợp.

### Search result và navigation

Khi chọn kết quả, editor điều hướng đến đúng source range. Nếu có nhiều kết quả trùng tên, hiển thị namespace, signature hoặc parent path.

## 13. Cây phác thảo cho tài liệu nhiều file

Document outline thường chỉ hiển thị file hiện tại. Một số IDE có thể cung cấp workspace symbol tree hoặc module outline trên nhiều file.

### Document scope

Chỉ hiển thị phần tử được khai báo trong tài liệu đang mở. Đây là phạm vi đơn giản và phù hợp với panel Outline thông thường.

### Workspace symbol tree

Hiển thị symbol trên nhiều file và module. Cần có source identity, project boundary, dependency và khả năng tải/lập chỉ mục.

### Imports

Import có thể xuất hiện như node trong outline của file, nhưng symbol được import không nhất thiết là con của file. Nếu muốn hiển thị, cần phân biệt imported symbol với declaration local.

### External symbol

Một symbol từ dependency ngoài có thể được hiển thị trong browser riêng. Document outline không nên tự động mở rộng toàn bộ dependency graph vì có thể rất lớn.

### Namespace và module

Với DSL có module lồng nhau, outline cần hiển thị đường dẫn đủ rõ để phân biệt `Sales.Order` và `Warehouse.Order`.

## 14. Cây phác thảo cho DSL đồ họa và model-driven

Không phải DSL nào cũng có source text. Trong DSL đồ họa, outline có thể trình bày node, edge, layer, group hoặc state machine.

Ví dụ workflow graph:

~~~text
OrderProcess
├── Start: OrderReceived
├── ValidateOrder
├── Decision: PaymentAccepted?
│   ├── Yes
│   │   ├── ReserveInventory
│   │   └── CreateShipment
│   └── No
│       └── RequestPayment
└── End: Completed
~~~

### Node và edge

Outline có thể hiển thị node theo containment hoặc theo graph traversal. Edge thường không phải con của node nguồn theo nghĩa ownership; có thể nhóm trong `Connections` hoặc hiển thị dưới node như một mục điều hướng riêng.

### Group và layer

Một diagram có thể có group hoặc layer. Cây có thể phản ánh cấu trúc group, trong khi edge cross-link được biểu diễn riêng để tránh tạo cây giả từ graph.

### Selection đồng bộ canvas

Chọn node trong outline có thể highlight node trên canvas; chọn node trên canvas có thể reveal node trong outline. Cả hai hướng cần dùng cùng stable element ID.

### Phần tử bị ẩn hoặc lọc trên canvas

Nếu layer đang ẩn, chọn node trong outline có thể tạm thời reveal hoặc thông báo node đang ẩn. Không nên âm thầm bỏ chọn hoặc thay đổi model chỉ vì canvas filter.

## 15. Cây phác thảo và symbol hierarchy

Outline có thể tận dụng symbol table để hiển thị các khai báo và quan hệ lexical nesting. Tuy nhiên, symbol hierarchy và outline tree không hoàn toàn giống nhau.

### Symbol identity

Symbol có identity độc lập với tên. Rename có thể giữ symbol ID; overload có thể tạo nhiều symbol cùng tên; namespace xác định phạm vi tên.

### Overload

Ví dụ:

~~~text
function calculateTotal(items: List<Item>): Money;
function calculateTotal(order: Order): Money;
~~~

Outline có thể hiển thị hai node cùng tên nhưng detail khác nhau. Dùng ID riêng để lựa chọn và điều hướng chính xác.

### Inheritance

Một type có thể kế thừa type khác. Đây là quan hệ tham chiếu chứ không nhất thiết là containment. Có thể cung cấp Type Hierarchy riêng thay vì đưa type cha thành node con hoặc node cha trong document outline.

### References và usages

Outline tập trung vào khai báo. Find References tập trung vào nơi sử dụng. Hai view có thể dùng chung symbol index nhưng không nên nhập nhằng mục tiêu.

## 16. Outline cho tài liệu chưa hoàn chỉnh

Trong editor, parser thường được gọi khi người dùng đang gõ. Tài liệu có thể thiếu dấu ngoặc, thiếu tên, có node chưa hoàn tất hoặc có lỗi cú pháp tạm thời. Outline cần giữ các phần cấu trúc còn nhận diện được.

Ví dụ người dùng đang nhập:

~~~text
entity Order {
    id: OrderId;
    total:
~~~

Parser có thể tạo node `Order` và field `total` chưa có type hoàn chỉnh. Outline vẫn nên hiển thị `Order` và có thể hiển thị field `total` với trạng thái incomplete.

### Error-tolerant parsing

Parser phục hồi lỗi có thể tạo AST một phần. Outline provider nên bỏ qua node không có identity hoặc range đáng tin cậy, hoặc hiển thị node tạm với trạng thái lỗi nếu có ích.

### Giữ node ổn định khi gõ

Nếu người dùng sửa một ký tự trong tên `Order`, UI không nên xóa toàn bộ cây rồi tạo lại khiến selection và expansion state mất. Incremental parse hoặc reconciliation theo ID/range có thể giữ node ổn định.

### Node thiếu tên

Nếu người dùng mới gõ `function (` và chưa nhập tên, provider có thể không tạo node cho function đó cho đến khi cấu trúc đủ nhận diện. Không nên tạo label rỗng hoặc node trùng lặp.

### Diagnostic trong outline

Node có thể hiển thị trạng thái error/warning nếu diagnostic giao với range của nó hoặc node con. Cần quy định lỗi được gắn lên node gần nhất, node cha hay cả hai để tránh lặp badge quá nhiều.

## 17. Cập nhật outline theo thay đổi tài liệu

Khi văn bản thay đổi, outline cần được cập nhật để phản ánh cấu trúc mới.

### Full refresh

Provider phân tích lại toàn bộ tài liệu và tạo cây mới. Cách này đơn giản, phù hợp với tài liệu nhỏ hoặc DSL ít thay đổi. Nhưng có thể tốn thời gian và làm mất trạng thái UI nếu cây bị thay hoàn toàn.

### Incremental update

Provider nhận token/AST delta và chỉ cập nhật các node bị ảnh hưởng. Cách này phù hợp với tài liệu lớn hoặc editor có yêu cầu phản hồi nhanh.

### Reconciliation

Sau khi có cây mới, UI có thể so sánh với cây cũ theo stable ID, symbol identity hoặc một khóa tạm ổn định. Node không đổi giữ expansion state; node đổi tên có thể giữ identity nếu parser/semantic model xác định được.

### Debounce và cancellation

Nhiều edit liên tiếp có thể được gộp trước khi yêu cầu outline mới. Nếu tác vụ cũ chưa hoàn tất và document version đã tăng, kết quả cũ cần bị bỏ qua. Debounce không nên khiến outline chậm rõ rệt khi người dùng dừng gõ.

### Version consistency

Mỗi outline result phải gắn với document version. Khi áp dụng range, editor cần chắc chắn range thuộc đúng version hoặc đã được ánh xạ sang version hiện tại.

## 18. Đồng bộ với Language Server Protocol

Với IDE sử dụng Language Server Protocol (LSP), outline thường được cung cấp qua document symbols.

LSP định nghĩa hai dạng phổ biến:

- `DocumentSymbol`: biểu diễn phân cấp, có `range`, `selectionRange` và `children`.
- `SymbolInformation`: biểu diễn symbol phẳng với location và container name.

DocumentSymbol phù hợp hơn khi editor cần cây cha–con trực tiếp. SymbolInformation hữu ích cho một số client hoặc provider chỉ cung cấp danh sách symbol.

### Các trường của DocumentSymbol

Một document symbol có thể gồm:

- `name`: tên hiển thị.
- `kind`: loại symbol như class, function, property hoặc namespace.
- `detail`: thông tin phụ.
- `range`: phạm vi toàn node.
- `selectionRange`: phạm vi chọn node.
- `children`: các symbol con.
- `tags`: metadata như deprecated.
- `deprecated`: trường legacy ở một số phiên bản giao thức.

### Đồng bộ version

LSP document change notification mang version của tài liệu. Language server cần gắn outline result với snapshot đã phân tích và không công bố kết quả lỗi thời sau khi document đã thay đổi.

### Dynamic registration và client capability

Server cần kiểm tra capability của client và phiên bản giao thức. Không phải client nào cũng hỗ trợ mọi symbol kind hoặc mọi metadata. Provider nên gửi loại symbol phù hợp và có fallback hợp lý.

### Source URI

Document symbols thường thuộc document URI đang được yêu cầu. Với workspace symbol hoặc cross-file outline, mỗi location cần URI riêng. Không nên suy ra URI từ tên file hiển thị.

## 19. Tích hợp với các tính năng editor khác

Outline có thể chia sẻ dữ liệu với nhiều tính năng nhưng mỗi tính năng có hợp đồng riêng.

### Go to Definition

Chọn node trong outline điều hướng đến declaration. Go to Definition từ một reference đi theo symbol binding và có thể mở file khác.

### Breadcrumbs

Breadcrumbs hiển thị đường dẫn cấu trúc từ root đến vị trí hiện tại, chẳng hạn `Sales > OrderApproval > Rule 1`. Breadcrumbs thường dùng cùng symbol hierarchy nhưng trình bày theo một dòng.

### Code folding

Full range của node có thể hỗ trợ folding. Tuy nhiên, outline expand/collapse không nhất thiết đồng bộ trực tiếp với folding state trong editor.

### Rename symbol

Rename cần semantic identity và reference index. Chọn node trong outline có thể mở rename action, nhưng không nên chỉ thay text trong label mà không cập nhật source và references.

### Find References

Từ một node outline, người dùng có thể mở danh sách references. Danh sách này có thể được nhóm theo file và hiển thị vị trí sử dụng.

### Diagnostics

Outline có thể hiển thị node có lỗi bằng icon hoặc decoration. Chọn diagnostic trong Problems panel có thể reveal node tương ứng trong outline.

### Documentation hover

Hover lên node có thể hiển thị documentation comment, signature, type hoặc metadata. Nội dung nên được cung cấp bởi language service thay vì tự suy ra từ tên.

## 20. Thao tác chỉnh sửa từ outline

Một số editor cho phép thao tác trực tiếp trên cây.

### Rename

Rename thay đổi tên khai báo và các reference theo symbol identity. Nếu DSL có overload hoặc shadowing, cần xác định đúng symbol được chọn.

### Create child

Tạo field trong entity, rule trong policy hoặc step trong workflow. Editor cần sinh cú pháp đúng vị trí, indent, separator và version của DSL.

### Delete

Xóa node cần xác định source range và tác động đến reference. Nếu xóa một declaration còn được sử dụng, IDE có thể cảnh báo hoặc cung cấp refactoring xử lý references.

### Move hoặc reorder

Di chuyển node có thể thay đổi lexical scope, execution order hoặc dependency. Không phải loại node nào cũng được di chuyển tự do. Editor cần kiểm tra ràng buộc ngữ nghĩa trước khi áp dụng.

### Drag and drop

Drag-and-drop trực quan nhưng cần xác định rõ vùng thả, quan hệ cha–con được phép và semantics reorder. Với workflow, di chuyển step có thể thay đổi hành vi thực thi nên cần preview hoặc undo rõ ràng.

### Undo và redo

Mọi thao tác từ outline nên đi qua edit transaction của editor để undo/redo khôi phục đúng source, selection và metadata liên quan.

## 21. Cây phác thảo và documentation comments

DSL có thể hỗ trợ comment tài liệu gắn với khai báo.

~~~text
/// Tạo một đơn hàng mới từ yêu cầu hợp lệ.
action CreateOrder(request: OrderRequest): Order;
~~~

Outline có thể hiển thị documentation trong tooltip hoặc panel detail khi node được chọn.

### Documentation không phải label

Tên node nên ngắn và ổn định. Documentation có thể dài, chứa Markdown hoặc liên kết. Không nên đưa toàn bộ comment vào cây vì làm node cao và khó quét.

### Inherited documentation

Một method hoặc action có thể kế thừa documentation từ interface hoặc type cha. Nếu hiển thị, cần phân biệt nội dung khai báo trực tiếp với nội dung kế thừa.

### Documentation lỗi thời

Nếu symbol bị deprecated hoặc documentation chứa reference không còn hợp lệ, có thể hiển thị metadata phù hợp. Outline không nên trở thành nơi thực hiện toàn bộ kiểm tra tài liệu; đó là nhiệm vụ của documentation validator.

## 22. Accessibility và khả năng sử dụng

Cây phác thảo cần hoạt động tốt với bàn phím, screen reader và nhiều chế độ hiển thị.

### Điều hướng bàn phím

Các thao tác thường cần hỗ trợ:

- Up/Down để chuyển node.
- Left để collapse hoặc chuyển đến parent.
- Right để expand hoặc chuyển đến child.
- Enter để điều hướng đến source.
- Home/End để đến đầu/cuối danh sách.
- Phím gõ để tìm node nếu UI hỗ trợ type-ahead.

### Screen reader

Node cần có role treeitem, level, expanded/collapsed state và accessible name. Nếu node có detail hoặc trạng thái lỗi, thông tin này cần được đọc theo cách có thể hiểu.

### Không chỉ dựa vào màu

Deprecated, error hoặc unresolved không nên chỉ được biểu thị bằng màu đỏ hoặc xám. Cần icon, text label hoặc accessibility description.

### Focus management

Khi chọn node và điều hướng sang editor, focus có thể chuyển sang editor. Khi quay lại outline, cần khôi phục focus hợp lý. Không nên làm người dùng bàn phím mất vị trí đang duyệt.

### Cây lớn

Với hàng nghìn node, cần hỗ trợ tìm kiếm, virtual scrolling hoặc lazy expansion. Screen reader vẫn phải nhận được cấu trúc và số cấp hợp lý.

## 23. Hiệu năng và khả năng mở rộng

Một outline cho tài liệu lớn cần tránh tạo object và render quá nhiều node không cần thiết.

### Lazy expansion

Node con có thể chỉ được tạo hoặc nạp khi người dùng mở rộng node cha. Điều này giảm chi phí khởi tạo nếu tài liệu có nhiều cấu trúc lồng sâu.

### Virtualization

UI chỉ render các node đang nằm trong vùng nhìn thấy. Virtualization giúp cây lớn không tạo hàng nghìn DOM/widget cùng lúc.

### Index theo range

Để đồng bộ caret, provider cần tìm node chứa offset nhanh. Có thể dùng interval tree, range index hoặc cấu trúc tương đương thay vì duyệt toàn bộ cây mỗi lần caret di chuyển.

### Incremental reconciliation

Giữ node không đổi theo identity và chỉ thay phần bị ảnh hưởng giúp giảm render, giữ selection và expansion state.

### Cache outline model

Có thể cache outline theo document version và semantic fingerprint. Khi dependency thay đổi, chỉ invalidate metadata cần thiết. Không nên dùng outline cache từ version cũ để điều hướng với source range đã lỗi thời.

### Đo lường

Các chỉ số hữu ích:

- Thời gian từ document change đến outline update.
- Thời gian tìm node chứa caret.
- Số node được tạo và render.
- Số lần refresh bị hủy do version mới.
- Bộ nhớ của tree model và range index.
- Độ trễ khi expand/collapse và fuzzy search.

## 24. Xử lý lỗi và trạng thái không đầy đủ

Outline có thể gặp lỗi khi parser thất bại, language server mất kết nối hoặc tài liệu bị xóa.

Các trạng thái có thể gồm:

- Loading: đang tạo outline.
- Ready: outline hiện tại đã đồng bộ với document version.
- Partial: chỉ nhận diện được một phần cấu trúc.
- Empty: tài liệu không có phần tử outline.
- Stale: kết quả thuộc version cũ và đang chờ cập nhật.
- Error: không thể lấy outline do lỗi provider hoặc server.

### Không đồng nhất empty với error

Tài liệu chỉ có biểu thức hoặc comment có thể hợp lệ nhưng không có node outline. Đây là empty state, không phải lỗi.

### Partial outline

Parser phục hồi có thể cung cấp một phần node. UI nên cho biết dữ liệu chưa đầy đủ nếu cần, nhưng vẫn cho phép điều hướng đến các khai báo hợp lệ đã nhận diện.

### Server disconnect

Nếu language server mất kết nối, editor có thể giữ cây gần nhất nhưng đánh dấu stale. Khi kết nối lại, yêu cầu outline mới và xác minh document version.

### Node không còn tồn tại

Nếu node được chọn bị xóa trong lúc người dùng đang tương tác, UI cần loại bỏ selection hoặc chuyển đến ancestor hợp lệ. Không nên giữ một node mồ côi với range không còn đúng.

## 25. Bảo đảm tính nhất quán giữa outline và source

Outline là view được suy ra từ tài liệu. Source hoặc canonical model thường là nguồn sự thật; outline phải phản ánh đúng version tương ứng.

### Versioned snapshot

Mỗi lần phân tích tài liệu tạo snapshot có version. Outline node giữ version đó. Khi source thay đổi, range cũ chỉ được dùng nếu có mapping hợp lệ.

### Race condition

Ví dụ:

1. Editor ở version 10, yêu cầu outline A.
2. Người dùng sửa tài liệu, editor chuyển version 11.
3. Editor yêu cầu outline B.
4. Outline B hoàn tất trước.
5. Outline A hoàn tất sau.

Nếu UI áp dụng A sau B, cây sẽ lùi về cấu trúc cũ. Cần kiểm tra version trước khi publish result và bỏ kết quả cũ.

### Source mapping sau edit

Nếu hệ thống muốn giữ selection trong outline sau edit, cần ánh xạ symbol identity hoặc source range. Không nên chỉ giữ offset tuyệt đối vì chèn/xóa phía trước có thể làm offset dịch chuyển.

### Undo/redo

Undo/redo tạo version mới dù nội dung có thể giống một version trước. Outline cần cập nhật theo version hiện tại và không dùng nhầm range của snapshot khác.

## 26. Ví dụ outline cho một DSL hoàn chỉnh

Giả sử tài liệu:

~~~text
module Commerce {
    entity Customer {
        id: CustomerId;
        status: CustomerStatus;
    }

    entity Order {
        id: OrderId;
        customer: Customer;
        total: Money;
    }

    policy ApprovalPolicy {
        rule HighValueOrder {
            when order.total >= 1000;
            then requireRole(Manager);
        }
        rule TrustedCustomer {
            when order.customer.status == TRUSTED;
            then approve;
        }
    }

    workflow FulfillOrder(order: Order) {
        validateOrder(order);
        if order.isApproved {
            reserveInventory(order);
            createShipment(order);
        }
    }
}
~~~

Outline có thể là:

~~~text
Commerce
├── Customer : Entity
│   ├── id : CustomerId
│   └── status : CustomerStatus
├── Order : Entity
│   ├── id : OrderId
│   ├── customer : Customer
│   └── total : Money
├── ApprovalPolicy : Policy
│   ├── HighValueOrder : Rule
│   └── TrustedCustomer : Rule
└── FulfillOrder(order: Order) : Workflow
    ├── validateOrder
    └── If order.isApproved
        ├── reserveInventory
        └── createShipment
~~~

Khi chọn `TrustedCustomer`, editor đưa con trỏ đến tên rule. Khi caret nằm trong `createShipment`, outline có thể mở `Commerce` và `FulfillOrder`, đồng thời chọn node step tương ứng nếu provider hiển thị các statement con.

## 27. Quy trình triển khai outline provider

Một quy trình thực tế có thể gồm:

1. **Xác định mục tiêu view:** document outline, workspace symbols hay outline cho mô hình đồ họa.
2. **Liệt kê phần tử:** xác định declaration/node nào có giá trị điều hướng với người viết DSL.
3. **Định nghĩa hierarchy:** quy tắc cha–con, flattening và nhóm ảo.
4. **Định nghĩa node model:** ID, label, kind, detail, source identity, selection range và full range.
5. **Chọn nguồn dữ liệu:** AST, semantic model hoặc kết hợp cả hai.
6. **Xây dựng provider:** chuyển cấu trúc ngôn ngữ thành outline node theo source order hoặc sort policy.
7. **Tích hợp editor/LSP:** trả document symbols, điều hướng, reveal và active-node synchronization.
8. **Cập nhật theo version:** full refresh hoặc incremental reconciliation; bỏ kết quả lỗi thời.
9. **Tích hợp thao tác:** folding, rename, find references, diagnostics và documentation hover.
10. **Thiết kế UX:** expand/collapse, search, filter, icon, detail và accessibility.
11. **Tối ưu:** lazy expansion, virtualization, range index và cache theo version.
12. **Kiểm thử:** nesting, overload, duplicate names, incomplete source, multi-file, Unicode và race condition.

## 28. Kiểm thử cây phác thảo

Outline cần được kiểm thử cả dữ liệu cấu trúc lẫn hành vi điều hướng.

| Nhóm kiểm thử | Trường hợp |
|---|---|
| Cấu trúc cơ bản | Một module, entity, field, function và workflow. |
| Nesting | Module lồng, function lồng hoặc rule trong policy. |
| Symbol trùng tên | Cùng tên ở namespace khác nhau hoặc overload. |
| Source range | Selection range bao tên; full range bao cấu trúc. |
| Source order | Node xuất hiện đúng thứ tự khai báo. |
| Sorting | Alphabetical hoặc kind grouping không làm đổi semantics. |
| Caret sync | Node sâu nhất hoặc ancestor phù hợp được chọn. |
| Navigation | Chọn node mở đúng file và đúng range. |
| Incomplete source | Thiếu dấu ngoặc, thiếu type hoặc khai báo đang gõ. |
| Incremental update | Rename, insert, delete và move node. |
| Version race | Kết quả parse cũ đến sau kết quả mới. |
| Multi-file | Symbol local, import và external reference. |
| Folding | Range lồng nhau và comment nhiều dòng. |
| Accessibility | Keyboard, screen reader và focus restore. |
| Large document | Hàng nghìn node, lazy expand và virtual render. |
| Error state | Empty, partial, stale và server unavailable. |

### Kiểm thử provider độc lập UI

Có thể tạo AST fixture và xác nhận provider tạo đúng cây node, label, kind và range. Điều này giúp tách lỗi chuyển đổi cấu trúc khỏi lỗi render giao diện.

### Kiểm thử điều hướng

Với mỗi node, xác nhận chọn node đưa editor đến selection range đúng trong document version tương ứng. Kiểm thử cần có Unicode, CRLF và tài liệu nhiều file nếu hệ thống hỗ trợ.

### Kiểm thử incremental

Tạo outline ở version đầu, sửa một khai báo rồi cập nhật. Xác nhận node bị xóa biến mất, node mới xuất hiện, node không đổi giữ identity và expansion state được bảo toàn theo chính sách.

## 29. Những lỗi thiết kế thường gặp

**Dùng regex để xây outline.** Regex không hiểu nested syntax, comment, string, escape và cấu trúc chưa hoàn chỉnh. Nên lấy cấu trúc từ parser hoặc language service.

**Hiển thị mọi AST node.** Cây quá chi tiết khiến người dùng khó tìm khai báo quan trọng. Outline cần lọc theo semantics và mục đích điều hướng.

**Dùng tên làm ID.** Rename hoặc overload có thể khiến selection và expansion state gắn sai node.

**Nhầm containment với reference.** Đưa mọi symbol được tham chiếu thành node con có thể tạo cây sai nghĩa hoặc chu kỳ.

**Dùng một range cho mọi thao tác.** Selection range và full range phục vụ điều hướng và containment khác nhau.

**Không gắn document version.** Kết quả cũ có thể đưa con trỏ đến offset sai sau khi người dùng sửa tài liệu.

**Refresh toàn bộ cây sau mỗi phím.** Có thể gây giật, mất expansion state và làm UI chậm trên tài liệu lớn.

**Đồng bộ caret gây cuộn ngoài ý muốn.** Tự động reveal liên tục có thể làm người dùng mất vị trí đang duyệt cây.

**Sắp xếp sai semantics.** Sắp xếp workflow step theo alphabet có thể khiến thứ tự thực thi bị hiểu sai.

**Không hỗ trợ tài liệu lỗi một phần.** Outline biến mất hoàn toàn khi người dùng đang gõ một cấu trúc chưa hoàn chỉnh.

**Trộn document outline với workspace symbol browser.** Cây có thể quá lớn và khó hiểu; cần phân biệt phạm vi.

**Chỉ dùng màu để thể hiện trạng thái.** Người dùng screen reader hoặc người khó phân biệt màu có thể bỏ lỡ thông tin.

**Không xử lý symbol trùng tên.** Node cùng tên cần detail, namespace hoặc breadcrumb để phân biệt.

## 30. Checklist cho một cây phác thảo mới

Khi thêm outline cho một DSL, cần xác định:

- View là document outline, workspace symbols hay model outline?
- Những loại declaration nào cần xuất hiện?
- Node nào là cấu trúc cha–con, node nào chỉ là reference?
- Có node ảo để nhóm theo kind không?
- Thứ tự mặc định là source order hay thứ tự khác?
- Node có stable ID và source identity không?
- Selection range và full range được xác định thế nào?
- Label, detail, icon và trạng thái phụ gồm những gì?
- Chọn node có mở đúng document và vị trí không?
- Caret sync chọn node sâu nhất hay ancestor gần nhất?
- Có thể tắt tự động reveal hoặc giữ selection thủ công không?
- Outline cập nhật full hay incremental?
- Kết quả có gắn document version và bỏ kết quả stale không?
- Tài liệu chưa hoàn chỉnh được trình bày thế nào?
- Search, filter, expand/collapse và folding hoạt động ra sao?
- Có hỗ trợ keyboard, screen reader và cây lớn không?
- Multi-file, import và external symbol được phân biệt thế nào?
- Rename, delete, move và reorder có semantic validation không?
- Có kiểm thử range, version race, Unicode và accessibility không?

## 31. Kết quả cần có sau khi thiết kế cây phác thảo

Một thiết kế outline hoàn chỉnh thường cung cấp:

- **Danh sách node được hỗ trợ:** module, entity, field, function, action, policy, rule, workflow và cấu trúc miền khác.
- **Hierarchy contract:** quy tắc cha–con, flattening, grouping và phân biệt containment/reference.
- **Outline node model:** ID, label, kind, detail, source ID, selection range, full range, version và metadata.
- **Provider:** chuyển AST/semantic model thành cây có thứ tự xác định.
- **Navigation contract:** chọn node, reveal, active-node synchronization và history.
- **Update strategy:** full refresh hoặc incremental reconciliation, cancellation và version check.
- **Editor integration:** folding, breadcrumbs, rename, find references, diagnostics và documentation.
- **UX/accessibility:** expand/collapse, search/filter, keyboard, screen reader và focus management.
- **Performance strategy:** lazy expansion, virtualization, range index và cache.
- **Test suite:** cấu trúc, range, navigation, incomplete source, multi-file, incremental update, accessibility và tài liệu lớn.

Cây phác thảo giúp người viết DSL nhìn thấy cấu trúc logic của tài liệu và điều hướng trực tiếp đến phần cần chỉnh sửa. Để hữu ích và đáng tin cậy, nó cần được xây dựng từ AST hoặc semantic model, phân biệt rõ containment với reference, sử dụng identity và source range ổn định, đồng thời đồng bộ theo đúng document version. Một outline tốt giữ được node hữu ích ngay cả khi tài liệu đang viết dở, hỗ trợ tìm kiếm và điều hướng bàn phím, và cập nhật đủ nhanh trên tài liệu lớn. Khi được tích hợp đúng với language service, editor, folding, diagnostics và symbol navigation, cây phác thảo trở thành một công cụ quan trọng giúp người dùng hiểu và quản lý các DSL có cấu trúc phức tạp.
