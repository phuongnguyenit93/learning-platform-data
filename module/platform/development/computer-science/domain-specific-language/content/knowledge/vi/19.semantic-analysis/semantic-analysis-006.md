# Kiểm tra nhiều tệp

Trong một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), chương trình có thể được chia thành nhiều tệp để tổ chức module, tái sử dụng định nghĩa và quản lý các phần của một hệ thống lớn. Một tệp có thể khai báo kiểu dữ liệu, tệp khác định nghĩa tài nguyên, quy tắc hoặc workflow sử dụng những kiểu đó. Vì vậy, việc phân tích một tệp riêng lẻ thường chưa đủ để xác định chương trình có hợp lệ hay không.

**Kiểm tra nhiều tệp** (*multi-file semantic analysis*) là quá trình phân tích ngữ nghĩa có xét đến các khai báo, tham chiếu và phụ thuộc giữa nhiều tệp trong cùng một dự án hoặc workspace. Công cụ cần biết tệp nào thuộc module nào, symbol được khai báo ở đâu, tệp nào phụ thuộc tệp nào, thành phần nào được phép truy cập và thay đổi ở một tệp ảnh hưởng đến những tệp nào.

Ví dụ, một DSL triển khai dịch vụ có thể có ba tệp:

```text
project/
├── models.dsl
├── database.dsl
└── service.dsl
```

`models.dsl` khai báo kiểu `Customer`; `database.dsl` định nghĩa tài nguyên lưu trữ dùng kiểu đó; `service.dsl` khai báo dịch vụ và tham chiếu đến tài nguyên database. Mỗi tệp có thể hợp lệ về cú pháp khi đọc riêng, nhưng dự án vẫn sai ngữ nghĩa nếu `service.dsl` tham chiếu một tài nguyên không tồn tại hoặc dùng kiểu không tương thích.

Kiểm tra nhiều tệp giúp phát hiện những vấn đề chỉ xuất hiện khi kết hợp các định nghĩa, đồng thời cung cấp thông tin để IDE, compiler và công cụ triển khai hiểu toàn bộ dự án.

## 1. Vì sao cần kiểm tra nhiều tệp?

Một tệp riêng lẻ chỉ thể hiện một phần chương trình. Khi DSL hỗ trợ module, import, tham chiếu chéo hoặc schema dùng chung, công cụ phải tổng hợp thông tin từ nhiều nguồn.

Những vấn đề thường chỉ phát hiện được ở cấp nhiều tệp gồm:

- Một tên được tham chiếu nhưng chỉ được khai báo trong tệp khác mà chưa import.
- Hai tệp khai báo trùng tên trong cùng namespace.
- Một kiểu được dùng sai ở một tệp khác.
- Một module phụ thuộc vào module không tồn tại hoặc không được khai báo.
- Hai module tạo thành chu trình phụ thuộc bị cấm.
- Một thành phần được khai báo là nội bộ nhưng bị truy cập từ module bên ngoài.
- Một thay đổi schema làm các tệp tiêu thụ schema không còn hợp lệ.
- Các phiên bản dependency không tương thích.

Ví dụ:

```text
# models.dsl
namespace acme.crm {
    model Customer {
        id: String
        name: String
    }
}
```

```text
# service.dsl
namespace acme.api {
    model Registration {
        customer: acme.crm.Customer
    }
}
```

Để kiểm tra kiểu của thuộc tính `customer`, analyzer cần biết `acme.crm.Customer` được định nghĩa trong `models.dsl` và định nghĩa đó có thể truy cập được từ `service.dsl`.

## 2. Phân biệt kiểm tra một tệp và kiểm tra nhiều tệp

Kiểm tra một tệp thường tập trung vào nội dung của chính tệp đó. Kiểm tra nhiều tệp cần thêm thông tin về project, module và các quan hệ giữa nguồn.

| Nội dung kiểm tra | Một tệp | Nhiều tệp |
|---|---|---|
| Cú pháp | Kiểm tra grammar của tệp hiện tại | Kiểm tra cú pháp từng tệp trong tập nguồn |
| Khai báo cục bộ | Phát hiện khai báo trùng trong phạm vi tệp | Phát hiện xung đột giữa các tệp cùng namespace hoặc module |
| Tham chiếu tên | Có thể chỉ phân giải tên cục bộ và import đã biết | Phân giải tham chiếu đến symbol ở tệp hoặc module khác |
| Kiểu dữ liệu | Kiểm tra kiểu trong phạm vi có sẵn | Kiểm tra tương thích kiểu giữa các định nghĩa liên tệp |
| Phụ thuộc | Ít hoặc không có thông tin về đồ thị project | Xây dựng và kiểm tra đồ thị phụ thuộc |
| Visibility | Kiểm tra phạm vi hiện tại | Kiểm tra quyền truy cập qua ranh giới module |
| Thay đổi nguồn | Phân tích lại tệp hiện tại | Xác định các tệp phụ thuộc cần phân tích lại |
| Diagnostic | Gắn lỗi vào tệp đang kiểm tra | Có thể trỏ đến nhiều tệp liên quan |

Kiểm tra nhiều tệp không thay thế lexer và parser của từng tệp. Thông thường, công cụ vẫn phân tích từ vựng và cú pháp từng tệp trước, sau đó kết hợp các kết quả để thực hiện semantic analysis ở cấp project.

## 3. Đơn vị tổ chức: tệp, module, package và project

Muốn phân tích nhiều tệp chính xác, DSL cần định nghĩa rõ các đơn vị tổ chức nguồn.

### 3.1. Tệp nguồn

Tệp nguồn là đơn vị lưu trữ văn bản. Mỗi tệp nên có định danh ổn định như URI hoặc đường dẫn chuẩn hóa để diagnostic có thể chỉ đúng vị trí.

Một tệp có thể chứa một hoặc nhiều namespace, module hoặc declaration tùy quy tắc DSL. Không nên mặc định một tệp luôn tương ứng với đúng một module nếu ngôn ngữ không quy định điều đó.

### 3.2. Module

Module là đơn vị tổ chức logic và thường là đơn vị phụ thuộc. Module có thể công bố API, che giấu chi tiết nội bộ và khai báo dependency đến module khác.

Ví dụ:

```text
module crm {
    public model Customer { }
    internal model CustomerIndex { }
}
```

Module `crm` có thể gồm nhiều tệp. Nếu DSL cho phép chia module thành nhiều tệp, analyzer cần hợp nhất các khai báo thuộc cùng module trước khi kiểm tra tham chiếu liên tệp.

### 3.3. Package và namespace

Namespace tạo không gian tên cho symbol. Package có thể là đơn vị nhóm mã hoặc thư viện. Quan hệ giữa package, module và namespace khác nhau theo DSL, vì vậy đặc tả phải xác định cách ánh xạ từ tệp đến từng phạm vi.

### 3.4. Project hoặc workspace

Project/workspace là tập hợp các module, tệp cấu hình, dependency và tài nguyên mà công cụ xem là một đơn vị phân tích. Kiểm tra nhiều tệp thường cần một project context để xác định nguồn nào thuộc cùng chương trình.

## 4. Pipeline phân tích ngữ nghĩa nhiều tệp

Một pipeline tổng quát có thể gồm các bước sau:

```text
Project configuration
        |
        v
Discover source files
        |
        v
Lex and parse each file
        |
        v
Collect declarations
        |
        v
Build module and dependency graph
        |
        v
Create project-wide symbol index
        |
        v
Resolve imports and references
        |
        v
Check types, visibility and domain rules
        |
        v
Publish diagnostics and semantic results
```

Các bước có thể được tổ chức khác nhau tùy compiler, nhưng việc tách nhiệm vụ giúp tránh phân giải tham chiếu khi symbol index chưa hoàn chỉnh.

### 4.1. Khám phá tệp nguồn

Công cụ xác định tập tệp thuộc project dựa trên cấu hình, thư mục nguồn, danh sách module hoặc quy tắc include. Cần xác định rõ:

- Thư mục nào được xem là source root.
- Phần mở rộng tệp DSL được hỗ trợ.
- Tệp sinh tự động có được đưa vào phân tích không.
- Tệp bị loại trừ hoặc nằm ngoài workspace được xử lý thế nào.
- Import có thể tham chiếu ra ngoài project hay không.

Không nên quét toàn bộ hệ thống tệp một cách tùy tiện. Tập nguồn cần có phạm vi và quy tắc xác định để kết quả phân tích có thể lặp lại.

### 4.2. Phân tích cú pháp từng tệp

Lexer và parser xử lý từng tệp, tạo token, AST và diagnostic cú pháp. AST nên giữ source span và định danh tệp để những bước tiếp theo có thể truy ngược về nguồn.

Một tệp có lỗi cú pháp vẫn có thể tạo AST một phần nếu parser hỗ trợ phục hồi. Analyzer cần biết phần nào đáng tin cậy để tránh phát quá nhiều lỗi dây chuyền.

### 4.3. Thu thập khai báo

Sau khi parse, công cụ duyệt AST để thu thập symbol như model, function, resource, rule, workflow và constant. Mỗi symbol cần được gắn với module, namespace, visibility, loại symbol và vị trí khai báo.

### 4.4. Xây dựng chỉ mục toàn project

Các symbol được đưa vào symbol index hoặc symbol table dùng chung. Chỉ mục này cho phép tra cứu symbol từ nhiều tệp mà không cần đọc lại toàn bộ AST mỗi lần.

### 4.5. Phân giải tham chiếu và kiểm tra ngữ nghĩa

Khi chỉ mục đã có các khai báo cần thiết, analyzer xử lý import, tên đầy đủ, tham chiếu kiểu, lời gọi hàm và ràng buộc miền. Sau đó, công cụ tổng hợp diagnostic và kết quả semantic.

## 5. Thu thập symbol từ nhiều tệp

**Symbol** là đại diện nội bộ cho một khai báo có thể được tham chiếu. Ví dụ, khai báo `model Customer` tạo một symbol có tên, loại, phạm vi và vị trí nguồn.

Một cấu trúc symbol minh họa:

```text
Symbol {
    id: SymbolId
    name: "Customer"
    qualifiedName: "acme.crm.Customer"
    kind: Model
    module: "crm"
    visibility: Public
    source: "src/crm/models.dsl"
    declarationSpan: [120, 248)
}
```

Các trường trên là mô hình khái niệm. Compiler thực tế có thể lưu thêm kiểu, generic parameters, documentation, modifiers, version và quan hệ kế thừa.

### 5.1. Vì sao cần hai lượt xử lý?

Nếu analyzer phân giải tên ngay khi đang đọc tệp đầu tiên, nó có thể gặp tham chiếu đến một symbol được khai báo ở tệp chưa được đọc. Điều đó dễ dẫn đến kết quả phụ thuộc thứ tự duyệt tệp.

Một chiến lược phổ biến là:

1. **Declaration pass:** đọc AST của các tệp và thu thập khai báo vào chỉ mục.
2. **Reference pass:** sau khi chỉ mục đã có các khai báo, phân giải tham chiếu và kiểm tra ngữ nghĩa.

Ví dụ, `service.dsl` có thể được parse trước `models.dsl`, nhưng `service.dsl` vẫn phân giải được `Customer` sau khi declaration pass hoàn tất.

### 5.2. Khai báo trùng

Hai tệp có thể vô tình khai báo cùng symbol trong một namespace:

```text
# customer-a.dsl
namespace acme.crm {
    model Customer { id: String }
}
```

```text
# customer-b.dsl
namespace acme.crm {
    model Customer { name: String }
}
```

Nếu DSL không hỗ trợ partial declaration hoặc extension, đây là lỗi khai báo trùng. Diagnostic nên chỉ ra cả vị trí khai báo hiện tại và khai báo trước đó.

### 5.3. Khai báo một phần

Một số DSL cho phép chia một định nghĩa thành nhiều phần bằng từ khóa như `partial` hoặc `extend`:

```text
# customer-core.dsl
partial model Customer {
    id: String
}
```

```text
# customer-contact.dsl
partial model Customer {
    email: String
}
```

Nếu hỗ trợ, analyzer phải hợp nhất các phần theo quy tắc rõ ràng và phát hiện xung đột giữa các thành phần. Không nên coi mọi khai báo trùng tên là hợp lệ chỉ vì chúng ở các tệp khác nhau.

## 6. Import và đồ thị phụ thuộc

Import thể hiện một tệp hoặc module cần sử dụng định nghĩa từ nơi khác. Các import tạo thành **đồ thị phụ thuộc** (*dependency graph*).

Ví dụ:

```text
# service.dsl
import acme.crm.Customer
import acme.storage.Database
```

`service.dsl` phụ thuộc vào module CRM và storage. Nếu `Database` lại phụ thuộc module `config`, đồ thị có thêm cạnh tương ứng.

### 6.1. Đồ thị có hướng

Có thể biểu diễn mỗi module là một đỉnh và mỗi dependency là một cạnh có hướng:

```text
service ---> crm
    |
    +------> storage ---> config
```

Hướng cạnh có thể được định nghĩa là “module sử dụng trỏ đến module được sử dụng”. Điều quan trọng là chọn một quy ước và dùng nhất quán trong thuật toán, thông báo lỗi và tài liệu.

### 6.2. Xác thực dependency

Với mỗi import hoặc dependency, analyzer cần kiểm tra:

- Module đích có tồn tại không?
- Tên module có được viết đúng namespace không?
- Dependency có được khai báo trong project configuration không?
- Phiên bản module có đáp ứng ràng buộc không?
- Symbol được import có được export không?
- Module đích có bị loại trừ hoặc không tương thích với target hiện tại không?

Một module tồn tại trên đĩa nhưng không nằm trong dependency graph được phép chưa chắc có thể được import. Quyền sử dụng phải theo quy tắc project, không chỉ theo khả năng tìm thấy tệp.

### 6.3. Dependency trực tiếp và gián tiếp

Nếu `A` phụ thuộc `B`, và `B` phụ thuộc `C`, thì `A` có dependency gián tiếp đến `C`. Một DSL có thể yêu cầu khai báo dependency trực tiếp trước khi tham chiếu symbol của `C`, hoặc cho phép dùng dependency bắc cầu.

Quy tắc này ảnh hưởng đến tính ổn định: nếu `A` chỉ hoạt động vì `B` tình cờ kéo `C` vào, thay đổi dependency của `B` có thể làm `A` hỏng. Nhiều hệ thống yêu cầu khai báo trực tiếp những module mà mã nguồn sử dụng.

## 7. Phát hiện chu trình phụ thuộc

Một chu trình phụ thuộc xuất hiện khi một module phụ thuộc trực tiếp hoặc gián tiếp vào chính nó.

Ví dụ:

```text
module A imports B
module B imports C
module C imports A
```

Đồ thị có chu trình `A -> B -> C -> A`.

### 7.1. Vì sao chu trình có thể là vấn đề?

Chu trình có thể khiến việc xác định thứ tự khởi tạo, biên dịch hoặc nạp module trở nên khó khăn. Nếu các module cần symbol của nhau ngay trong giai đoạn khởi tạo, compiler có thể không biết định nghĩa nào cần hoàn tất trước.

Không phải mọi DSL đều cấm mọi loại chu trình. Một số hệ thống hỗ trợ tham chiếu kiểu vòng hoặc module có khai báo trước. Tuy nhiên, chúng vẫn cần quy tắc rõ về phần nào được phép tham chiếu trước và phần nào phải được khởi tạo sau.

### 7.2. Phát hiện bằng DFS

Một cách phổ biến là duyệt đồ thị bằng DFS và dùng ba trạng thái:

- `UNVISITED`: chưa duyệt.
- `VISITING`: đang nằm trên đường duyệt hiện tại.
- `VISITED`: đã duyệt xong.

Nếu gặp một đỉnh đang ở trạng thái `VISITING`, đã tìm thấy cạnh quay về một node trong đường đi hiện tại, tức là có chu trình.

Mã giả:

```text
visit(module):
    if state[module] == VISITING:
        reportCycle(currentPath + module)
        return

    if state[module] == VISITED:
        return

    state[module] = VISITING
    currentPath.push(module)

    for dependency in dependencies[module]:
        visit(dependency)

    currentPath.pop()
    state[module] = VISITED
```

Đây là mã giả minh họa. Triển khai thực tế cần tránh báo lặp cùng một chu trình và xử lý module không thể tải được.

### 7.3. Sắp xếp topo

Nếu đồ thị không có chu trình, có thể tạo thứ tự topo (*topological order*) để xử lý dependency trước module phụ thuộc.

Ví dụ:

```text
config -> storage -> service
```

Theo quy ước cạnh “phụ thuộc trỏ đến dependency”, thứ tự xử lý hợp lý là `config`, rồi `storage`, rồi `service`. Nếu dùng hướng cạnh ngược, thứ tự kết quả cần được đảo phù hợp.

## 8. Phân giải tên giữa các tệp

Sau khi thu thập symbol và xác định import, analyzer có thể phân giải các tham chiếu trong AST.

Ví dụ:

```text
# models.dsl
namespace acme.crm {
    public model Customer { id: String }
}
```

```text
# service.dsl
namespace acme.api {
    import acme.crm.Customer

    model Registration {
        customer: Customer
    }
}
```

Analyzer xử lý tham chiếu `Customer` theo ngữ cảnh của `service.dsl`, tìm symbol đã import và gắn symbol reference đến khai báo trong `models.dsl`.

### 8.1. Tên đơn giản

Tên đơn giản như `Customer` có thể được tìm trong phạm vi cục bộ, namespace hiện tại, import tường minh hoặc các phạm vi khác theo thứ tự do DSL quy định.

### 8.2. Tên đầy đủ

Tên đầy đủ như `acme.crm.Customer` giảm phụ thuộc vào import và thường chỉ rõ namespace chứa symbol. Analyzer vẫn phải kiểm tra module tồn tại và symbol có thể truy cập được.

### 8.3. Tên mơ hồ

Nếu hai module cùng export `Customer` và cả hai được import không alias, tên đơn giản có thể mơ hồ. Analyzer nên báo các ứng viên và yêu cầu người dùng dùng alias hoặc tên đầy đủ.

### 8.4. Tham chiếu chưa phân giải

Nếu không tìm thấy symbol, diagnostic nên chỉ đến vị trí tham chiếu và có thể gợi ý:

- Kiểm tra chính tả.
- Thêm import.
- Khai báo dependency.
- Dùng tên đầy đủ.
- Kiểm tra visibility hoặc phiên bản module.

Không nên báo một lỗi chung “unknown symbol” nếu analyzer có đủ thông tin để phân biệt symbol không tồn tại với symbol tồn tại nhưng không được phép truy cập.

## 9. Kiểm tra visibility qua ranh giới tệp và module

Visibility xác định phạm vi có thể sử dụng một khai báo. Các mức phổ biến có thể gồm public, internal, protected hoặc private, nhưng ý nghĩa cụ thể phụ thuộc DSL.

Ví dụ:

```text
# crm.dsl
module crm {
    public model Customer { }
    internal model CustomerIndex { }
}
```

```text
# api.dsl
module api {
    import crm.Customer
    import crm.CustomerIndex
}
```

`Customer` có thể được truy cập nếu module `crm` export nó. `CustomerIndex` không được truy cập từ module `api` nếu `internal` giới hạn symbol trong module `crm`.

### 9.1. File-private và module-private

Một DSL cần phân biệt phạm vi chỉ trong tệp với phạm vi trong toàn module. Nếu `private` có nghĩa chỉ tệp hiện tại, một tệp khác trong cùng module cũng không được truy cập. Nếu `internal` có nghĩa toàn module, các tệp cùng module có thể sử dụng.

### 9.2. Export tường minh

Một module có thể yêu cầu khai báo export:

```text
module crm {
    export Customer
}
```

Export tường minh tạo API công khai có kiểm soát. Analyzer cần kiểm tra symbol được export thực sự tồn tại và không vi phạm quy tắc visibility.

### 9.3. Kiểm tra quyền ở cả hai phía

Để cho phép tham chiếu liên module, thông thường cần cả:

- Project/module hiện tại có dependency đến module đích.
- Symbol đích được export hoặc có visibility cho phép.

Chỉ có một trong hai điều kiện là chưa đủ.

## 10. Kiểm tra kiểu dữ liệu liên tệp

Khi một tệp dùng kiểu được định nghĩa ở tệp khác, analyzer phải kiểm tra kiểu đó và áp dụng các quy tắc tương thích.

Ví dụ:

```text
# types.dsl
namespace acme.shared {
    type CustomerId = String
}
```

```text
# service.dsl
namespace acme.api {
    import acme.shared.CustomerId

    model Registration {
        customerId: CustomerId
    }
}
```

Analyzer cần xác định `CustomerId` là alias của `String` hay một kiểu danh nghĩa riêng, rồi kiểm tra các giá trị được gán hoặc truyền vào thuộc tính.

### 10.1. Kiểm tra tương thích kiểu

Giả sử một hàm được khai báo ở module khác:

```text
# billing.dsl
public function charge(amount: Money): Receipt
```

Tệp gọi:

```text
# checkout.dsl
receipt = billing.charge(order.total)
```

Analyzer cần kiểm tra:

- `billing.charge` có tồn tại và được export không.
- `order.total` có kiểu tương thích với `Money` không.
- Các tham số có đúng số lượng và thứ tự không.
- Kiểu trả về `Receipt` có được sử dụng hợp lệ không.

### 10.2. Alias kiểu và kiểu danh nghĩa

Nếu hai tệp định nghĩa:

```text
type CustomerId = String
type OrderId = String
```

DSL có thể xem cả hai tương đương `String` hoặc là hai kiểu danh nghĩa khác nhau. Trong trường hợp kiểu danh nghĩa, không thể truyền `OrderId` vào vị trí cần `CustomerId` chỉ vì cả hai có cùng kiểu nền.

Quy tắc này phải nhất quán trên toàn project để tránh một module kiểm tra kiểu khác module khác.

### 10.3. Generic và ràng buộc kiểu

Nếu module công bố kiểu generic:

```text
public model Repository<T> {
    get(id: Identifier): T
}
```

module sử dụng cần kiểm tra tham số kiểu và các constraint. Nếu `Repository<T>` yêu cầu `T` phải là `Persistable`, kiểu được truyền từ tệp khác cũng phải thỏa ràng buộc đó.

## 11. Kiểm tra kế thừa và interface liên tệp

Quan hệ kế thừa hoặc triển khai interface có thể vượt qua ranh giới tệp và module.

Ví dụ:

```text
# contracts.dsl
public interface Serializable {
    serialize(): String
}
```

```text
# models.dsl
import acme.contracts.Serializable

public model Customer implements Serializable {
    serialize(): String = ...
}
```

Analyzer cần kiểm tra:

- Interface tồn tại và có thể truy cập.
- Model triển khai đủ các thao tác bắt buộc.
- Chữ ký thao tác tương thích.
- Kiểu trả về và tham số đáp ứng hợp đồng.
- Không có chu trình kế thừa bị cấm.
- Các bất biến và quy tắc thay thế kiểu được giữ.

Nếu interface thay đổi, những model triển khai nó ở tệp khác có thể cần được phân tích lại.

## 12. Kiểm tra ràng buộc miền xuyên nhiều tệp

DSL thường biểu diễn các quy tắc nghiệp vụ không nằm gọn trong một tệp. Ví dụ, một workflow có thể tham chiếu schema, resource và policy được khai báo ở những module khác nhau.

```text
# schema.dsl
model Order {
    customerId: CustomerId
    total: Money
}
```

```text
# policy.dsl
rule positiveOrderTotal(order: Order) {
    order.total > 0
}
```

```text
# workflow.dsl
workflow submitOrder(order: Order) {
    validate positiveOrderTotal(order)
    persist order
}
```

Semantic analyzer cần kiểm tra cả symbol, kiểu và quan hệ giữa các thành phần. Nếu `Order.total` đổi kiểu hoặc policy đổi chữ ký, workflow có thể không còn hợp lệ.

### 12.1. Ràng buộc tham chiếu chéo

Một số quy tắc có thể yêu cầu:

- Mọi resource được tham chiếu phải tồn tại.
- Mọi workflow gọi phải được export.
- Các tên cột trong query phải có trong schema.
- Quan hệ giữa hai model phải tương thích về kiểu khóa.
- Các rule được gọi phải nhận đúng kiểu đầu vào.

### 12.2. Quy tắc toàn cục

Một số kiểm tra chỉ có thể thực hiện sau khi đã thu thập toàn bộ project, ví dụ tên resource phải duy nhất trong một namespace toàn cục hoặc mọi endpoint công khai phải có định danh duy nhất.

Các quy tắc này cần được xác định phạm vi: toàn tệp, module, project, workspace hay môi trường triển khai. Phạm vi càng rộng, công cụ càng cần quản lý tập nguồn và cache cẩn thận.

## 13. Phiên bản dependency và tương thích

Một project có thể phụ thuộc nhiều module hoặc package với các phiên bản khác nhau.

Ví dụ:

```text
dependencies {
    acme.crm = "2.1"
    acme.billing = "1.4"
}
```

Analyzer hoặc dependency resolver cần xác định phiên bản thực tế của từng module, sau đó phân tích symbol dựa trên đúng API của phiên bản đã chọn.

### 13.1. Dependency không tồn tại

Nếu module được yêu cầu không có trong registry hoặc cache hợp lệ, công cụ cần báo lỗi ở khai báo dependency, đồng thời tránh tạo hàng loạt lỗi “unknown symbol” không cần thiết cho mọi tham chiếu phụ thuộc module đó.

### 13.2. Xung đột phiên bản

Nếu hai module yêu cầu các phiên bản không tương thích của cùng một dependency, resolver cần áp dụng chính sách version constraint hoặc báo xung đột.

### 13.3. API tương thích

Một dependency mới có thể giữ tên module nhưng xóa hoặc đổi kiểu một symbol. Analyzer cần dùng metadata của phiên bản đã resolve, không chỉ dựa vào tên module.

### 13.4. Reproducible analysis

Để kết quả phân tích có thể lặp lại, project nên khóa hoặc ghi rõ phiên bản dependency đã chọn. Nếu mỗi lần chạy tự lấy phiên bản mới nhất, cùng một source có thể cho kết quả khác nhau theo thời gian.

## 14. Diagnostic xuyên nhiều tệp

Lỗi liên tệp thường cần thông tin từ nhiều vị trí. Một diagnostic có thể có vị trí chính ở nơi tham chiếu sai và related information ở nơi khai báo hoặc định nghĩa liên quan.

Ví dụ, khai báo trùng:

```text
# a.dsl
namespace acme.crm {
    model Customer { }
}
```

```text
# b.dsl
namespace acme.crm {
    model Customer { }
}
```

Diagnostic có thể hiển thị:

```text
b.dsl:2:11: error DSL-NAME-0012: duplicate model 'Customer'
Related location: a.dsl:2:11: previous declaration is here
```

### 14.1. Vị trí chính và vị trí liên quan

Vị trí chính thường là nơi người dùng cần hành động, còn vị trí liên quan giải thích nguồn gốc hoặc nguyên nhân. Với lỗi tham chiếu chưa khai báo, vị trí chính là nơi sử dụng tên. Với lỗi khai báo trùng, vị trí chính thường là khai báo mới và vị trí liên quan là khai báo trước.

### 14.2. Diagnostic khi dependency thiếu

Nếu `service.dsl` import module `crm` nhưng module không được resolve, công cụ nên báo lỗi tại import hoặc dependency declaration. Những tham chiếu tiếp theo đến `crm.Customer` có thể được đánh dấu là phụ thuộc chưa phân giải, nhưng nên tránh phát một diagnostic lặp lại cho mọi node nếu không cung cấp thông tin mới.

### 14.3. Diagnostic ổn định trong IDE

Khi nhiều tệp được phân tích cùng lúc, IDE cần gắn diagnostic với URI và phiên bản tài liệu tương ứng. Nếu một tệp thay đổi trong lúc phân tích, kết quả cũ không nên được áp dụng lên nội dung mới.

## 15. Phân tích tăng dần nhiều tệp

Trong một project lớn, phân tích lại mọi tệp sau mỗi lần chỉnh sửa có thể tốn thời gian. **Phân tích tăng dần** (*incremental analysis*) chỉ cập nhật những phần bị ảnh hưởng bởi thay đổi.

Ví dụ, nếu người dùng sửa một biểu thức cục bộ trong `service.dsl`, công cụ có thể chỉ cần phân tích lại tệp đó. Nếu người dùng thay đổi chữ ký hàm công khai trong `billing.dsl`, các tệp đang gọi hàm đó có thể cần được kiểm tra lại.

### 15.1. Dependency graph ở mức tệp và symbol

Đồ thị module có thể quá thô để xác định chính xác phần cần phân tích lại. Một công cụ có thể lưu thêm dependency ở mức tệp hoặc symbol:

```text
checkout.dsl -> billing.charge
report.dsl   -> billing.Receipt
admin.dsl    -> crm.Customer
```

Nếu chỉ `billing.charge` thay đổi, analyzer có thể ưu tiên `checkout.dsl` và những nơi sử dụng chữ ký đó, thay vì phân tích lại mọi tệp trong project.

### 15.2. Invalidation

Khi một symbol thay đổi, công cụ cần xác định cache hoặc kết quả nào đã lỗi thời. Những thay đổi có thể gây invalidation gồm:

- Thêm hoặc xóa khai báo.
- Đổi tên symbol hoặc namespace.
- Thay đổi kiểu hoặc chữ ký.
- Thay đổi visibility hoặc export.
- Thay đổi inheritance/interface.
- Thay đổi import hoặc dependency version.
- Thay đổi quy tắc miền được dùng bởi module khác.

### 15.3. Phân biệt thay đổi nội dung và thay đổi giao diện symbol

Một thay đổi trong phần thân hàm riêng tư có thể không ảnh hưởng các module khác nếu chữ ký và hợp đồng công khai không đổi. Ngược lại, đổi kiểu trả về của hàm công khai có thể ảnh hưởng mọi nơi gọi hàm.

Compiler có thể dùng API fingerprint hoặc semantic hash để phát hiện thay đổi có ảnh hưởng đến người tiêu thụ. Cách này giúp giảm phạm vi phân tích lại.

### 15.4. Kết quả phân tích nhất quán

Trong môi trường IDE, nhiều tệp có thể thay đổi gần như đồng thời. Analyzer cần tránh kết hợp AST của phiên bản mới ở một tệp với symbol index cũ ở tệp khác nếu điều đó tạo kết quả không nhất quán.

Một chiến lược là gắn version hoặc snapshot ID cho từng lần phân tích project. Chỉ công bố kết quả khi các thành phần thuộc cùng snapshot hoặc khi công cụ đã xác nhận các dependency liên quan vẫn hợp lệ.

## 16. Cache và hiệu năng

Phân tích nhiều tệp thường cần cache để tránh parse và kiểm tra lặp lại.

### 16.1. Cache AST

Nếu nội dung tệp và phiên bản grammar không đổi, AST có thể được tái sử dụng. Cache cần xét cả encoding, cấu hình parser và các tùy chọn ảnh hưởng kết quả.

### 16.2. Cache symbol index

Symbol index có thể được cache theo module hoặc project. Khi một khai báo thay đổi, chỉ phần index liên quan cần cập nhật nếu hệ thống hỗ trợ cập nhật tăng dần.

### 16.3. Cache dependency resolution

Kết quả resolve module và version có thể được cache, nhưng cần invalidation khi project configuration, lockfile hoặc registry thay đổi.

### 16.4. Cache semantic result

Kết quả kiểm tra kiểu và ràng buộc có thể được tái sử dụng nếu đầu vào và mọi dependency ngữ nghĩa không đổi. Chỉ hash nội dung của một tệp là chưa đủ nếu tệp phụ thuộc vào symbol ở nơi khác.

### 16.5. Tránh cache lỗi thời

Cache lỗi thời có thể tạo lỗi khó hiểu: người dùng đã sửa khai báo nhưng analyzer vẫn báo tên cũ hoặc kiểu cũ. Mỗi cache entry nên có khóa phản ánh các dependency có ảnh hưởng, và công cụ cần có cách xóa hoặc làm mới cache khi cần.

## 17. Kiểm tra nhiều tệp trong IDE và Language Server

IDE thường cần phân tích project trong khi người dùng đang chỉnh sửa. Mỗi tệp có thể ở một phiên bản chưa lưu khác với nội dung trên đĩa.

Một Language Server có thể quản lý:

- Danh sách tài liệu đang mở.
- Nội dung mới nhất trong bộ nhớ của editor.
- Phiên bản tài liệu.
- AST và symbol index tương ứng.
- Dependency graph.
- Diagnostics theo tệp.

### 17.1. Tệp chưa lưu

Nếu `models.dsl` đang mở và có thay đổi chưa lưu, `service.dsl` nên được phân giải theo nội dung mới trong editor nếu hai tệp thuộc cùng workspace snapshot. Dùng nội dung trên đĩa cũ có thể làm IDE báo lỗi sai.

### 17.2. Cập nhật tham chiếu

Khi người dùng đổi tên một symbol, IDE cần tìm các tham chiếu đã được semantic analyzer liên kết với symbol identity đó. Chỉ tìm chuỗi trùng tên có thể sửa nhầm tham chiếu đến symbol khác.

### 17.3. Go to definition và find references

Các tính năng này dựa trên symbol index liên tệp:

- Go to definition từ tham chiếu trong `service.dsl` đến khai báo ở `models.dsl`.
- Find references từ một khai báo đến các tệp sử dụng symbol đó.
- Rename cập nhật khai báo và các tham chiếu thực sự liên kết với symbol.

### 17.4. Diagnostic theo phiên bản tài liệu

Kết quả phân tích bất đồng bộ có thể đến sau khi người dùng đã sửa thêm nội dung. Server cần kiểm tra version trước khi gửi diagnostic để không gạch chân sai vị trí.

## 18. Tích hợp với build và CI

Kiểm tra nhiều tệp thường là bước trong quá trình build hoặc kiểm tra dự án. Công cụ CLI có thể cung cấp các chế độ:

```text
dsl check-file service.dsl
dsl check-project project.dslproj
dsl build project.dslproj
```

`check-file` có thể dùng các dependency đã resolve hoặc giới hạn phạm vi. `check-project` kiểm tra toàn bộ module và tham chiếu liên tệp. `build` có thể tiếp tục sinh mã hoặc artifact sau khi semantic analysis thành công.

### 18.1. Kiểm tra cục bộ và kiểm tra toàn project

Một công cụ có thể hỗ trợ chế độ nhanh để kiểm tra tệp đang mở và chế độ đầy đủ để kiểm tra mọi dependency. Cần hiển thị rõ chế độ nào đã chạy để người dùng không hiểu nhầm rằng một tệp đã hợp lệ đồng nghĩa cả project hợp lệ.

### 18.2. Build reproducible

CI nên dùng cùng cấu hình project và dependency lock như môi trường phát triển. Nếu dependency được resolve khác nhau giữa máy local và CI, semantic analysis có thể cho kết quả khác.

### 18.3. Diagnostic machine-readable

Định dạng JSON hoặc SARIF có thể giúp CI tổng hợp lỗi từ nhiều tệp, gắn vị trí chính xác và liên kết với hệ thống review. Mỗi diagnostic cần giữ file URI, range, code, severity và thông tin liên quan nếu có.

## 19. Ví dụ tổng hợp: kiểm tra một project gồm nhiều module

Giả sử project có cấu trúc:

```text
shop/
├── project.dslproj
├── shared/
│   └── types.dsl
├── crm/
│   └── customer.dsl
├── billing/
│   └── invoice.dsl
└── api/
    └── registration.dsl
```

Các nội dung:

```text
# shared/types.dsl
module shared {
    public type CustomerId = String
    public type Money = Decimal
}
```

```text
# crm/customer.dsl
module crm {
    import shared.CustomerId

    public model Customer {
        id: CustomerId
        name: String
    }
}
```

```text
# billing/invoice.dsl
module billing {
    import shared.Money
    import crm.Customer

    public model Invoice {
        customer: Customer
        total: Money
    }
}
```

```text
# api/registration.dsl
module api {
    import crm.Customer
    import billing.Invoice

    workflow register(customer: Customer): Invoice {
        ...
    }
}
```

Analyzer có thể thực hiện:

1. Đọc `project.dslproj` để xác định bốn module và dependency.
2. Parse từng tệp, tạo AST cùng source span.
3. Thu thập `CustomerId`, `Money`, `Customer`, `Invoice` và `register` vào symbol index.
4. Xây dependency graph: `crm` phụ thuộc `shared`; `billing` phụ thuộc `shared` và `crm`; `api` phụ thuộc `crm` và `billing`.
5. Kiểm tra graph không có chu trình theo chính sách của DSL.
6. Resolve từng import và kiểm tra visibility.
7. Kiểm tra kiểu của `Customer.id`, `Invoice.total` và tham số workflow.
8. Phát diagnostics tại đúng tệp nếu một symbol thiếu hoặc kiểu không tương thích.

Nếu `shared.Money` bị đổi từ `Decimal` sang một kiểu danh nghĩa khác, analyzer cần xác định các tệp tiêu thụ có còn tương thích không. `billing/invoice.dsl` và những tệp sử dụng `Invoice.total` có thể cần được kiểm tra lại.

## 20. Những sai lầm thường gặp

**Phân giải tham chiếu ngay khi đọc từng tệp.** Nếu tệp khai báo symbol chưa được đọc, kết quả có thể phụ thuộc thứ tự duyệt tệp. Nên có bước thu thập khai báo trước khi phân giải tham chiếu liên tệp.

**Coi tệp và module là một.** Một module có thể gồm nhiều tệp hoặc một tệp có thể chứa nhiều namespace tùy DSL. Cần dùng đúng mô hình tổ chức của ngôn ngữ.

**Chỉ kiểm tra tên tồn tại mà không kiểm tra visibility.** Symbol có thể tồn tại nhưng không được export hoặc không nằm trong dependency được phép.

**Không phát hiện khai báo trùng giữa các tệp.** Symbol index cần kiểm tra xung đột trên phạm vi đúng, đồng thời tôn trọng quy tắc partial/extension nếu DSL hỗ trợ.

**Bỏ qua chu trình phụ thuộc.** Chu trình có thể làm việc nạp, khởi tạo hoặc biên dịch module không xác định. Cần phát hiện và báo đường đi tạo chu trình.

**Báo hàng loạt lỗi thứ cấp khi dependency thiếu.** Khi module chưa resolve, các tham chiếu bên trong module đó có thể chỉ là hậu quả. Diagnostic nên tập trung vào nguyên nhân gốc và hạn chế nhiễu.

**Cache semantic result chỉ theo nội dung một tệp.** Kết quả còn phụ thuộc symbol, module version và cấu hình ở các tệp khác. Cache key cần phản ánh dependency ngữ nghĩa.

**Dùng AST của các phiên bản tài liệu không đồng bộ.** IDE cần gắn kết quả với snapshot hoặc document version để tránh trộn nội dung cũ và mới.

**Giả định dependency bắc cầu luôn được phép.** Một symbol có thể đến từ module gián tiếp, nhưng project có thể yêu cầu khai báo dependency trực tiếp.

## 21. Ghi nhớ

- Kiểm tra nhiều tệp phân tích ngữ nghĩa trong bối cảnh project, module và dependency thay vì chỉ một tệp riêng lẻ.
- Pipeline thường gồm khám phá nguồn, parse từng tệp, thu thập khai báo, xây symbol index, resolve tham chiếu và kiểm tra kiểu/quy tắc miền.
- Declaration pass giúp kết quả không phụ thuộc thứ tự đọc tệp; reference pass dùng chỉ mục đã hoàn thiện để phân giải tên.
- Import tạo quan hệ phụ thuộc; analyzer cần kiểm tra module tồn tại, phiên bản, visibility và quyền truy cập.
- Dependency graph giúp phát hiện chu trình và xác định thứ tự xử lý module.
- Kiểm tra liên tệp bao gồm tên, kiểu, kế thừa, interface, ràng buộc miền và tính duy nhất của khai báo.
- Diagnostic có thể chỉ đến nhiều tệp, với một vị trí chính và thông tin liên quan.
- Incremental analysis dùng dependency graph và invalidation để chỉ phân tích lại phần bị ảnh hưởng.
- Cache phải tính đến dependency ngữ nghĩa và phiên bản module, không chỉ nội dung của một tệp.
- IDE và CI cần kết quả nhất quán theo workspace snapshot, dependency lock và document version.

## 22. Câu hỏi tự kiểm tra

1. Vì sao một tệp có thể hợp lệ về cú pháp nhưng toàn project vẫn sai ngữ nghĩa?
2. Phân biệt kiểm tra một tệp với kiểm tra nhiều tệp.
3. Declaration pass và reference pass có nhiệm vụ gì?
4. Symbol index giúp analyzer giải quyết vấn đề nào?
5. Import tạo ra quan hệ gì trong dependency graph?
6. Vì sao cần phát hiện chu trình phụ thuộc? Nêu một cách phát hiện bằng DFS.
7. Phân biệt symbol tồn tại nhưng không được truy cập với symbol không tồn tại.
8. Khi một kiểu được đổi trong tệp dùng chung, những tệp tiêu thụ nào có thể cần phân tích lại?
9. Diagnostic liên tệp nên sử dụng vị trí chính và related information như thế nào?
10. Incremental analysis dùng dependency graph để giảm công việc ra sao?
11. Vì sao cache kết quả ngữ nghĩa cần xét đến phiên bản module và các symbol phụ thuộc?
12. Trong ví dụ project shop, hãy mô tả thứ tự phân tích hợp lý và những kiểm tra cần thực hiện trước khi build.
