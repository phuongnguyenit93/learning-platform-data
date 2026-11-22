# Xtext

**Xtext** là một framework mã nguồn mở thuộc hệ sinh thái Eclipse, dùng để xây dựng ngôn ngữ văn bản chuyên biệt theo miền (Domain-Specific Language — DSL). Thay vì tự viết lexer, parser, mô hình dữ liệu, bộ phân giải tham chiếu và plugin editor từ đầu, người phát triển mô tả grammar của ngôn ngữ rồi cấu hình hoặc mở rộng các dịch vụ mà Xtext cung cấp.

Xtext không chỉ tạo parser. Từ grammar và cấu hình dự án, framework có thể sinh mô hình dựa trên EMF, parser, serializer, cơ chế linking, hạ tầng validation và các thành phần hỗ trợ IDE. Người phát triển có thể bổ sung quy tắc scope, kiểm tra ngữ nghĩa, content assist, formatter, quick fix, code generator và tích hợp runtime. Vì vậy, Xtext phù hợp khi cần một DSL có cú pháp rõ ràng, mô hình dữ liệu có cấu trúc và trải nghiệm phát triển tương đối hoàn chỉnh.

## 1. Xtext giải quyết bài toán gì?

Giả sử một nhóm muốn tạo DSL mô tả quy tắc vận chuyển:

```text
entity Order {
    total: Money
    status: OrderStatus
}

rule freeShipping {
    when order.total >= 1000000 and order.status == PAID
    then set order.shippingFee = 0
}
```

Để hỗ trợ ngôn ngữ này, nhóm cần xử lý nhiều công việc:

- Định nghĩa cú pháp và nhận diện token.
- Phân tích văn bản thành cấu trúc có thể truy cập bằng code.
- Tạo mô hình cho entity, rule, expression và action.
- Phân giải tên `Order`, `Money`, `order.total` và `PAID`.
- Kiểm tra kiểu và quy tắc nghiệp vụ.
- Hiển thị lỗi tại đúng vị trí trong editor.
- Cung cấp autocomplete, outline, hover và điều hướng symbol.
- Tuần tự hóa mô hình trở lại văn bản khi cần.
- Sinh mã hoặc cấu hình để chương trình có thể chạy.

Xtext cung cấp một nền tảng thống nhất cho các phần đó. Người phát triển tập trung mô tả semantics và quy tắc miền thay vì phải tự xây toàn bộ hạ tầng ngôn ngữ.

### 1.1. DSL văn bản và DSL đồ họa

Xtext chủ yếu hướng đến DSL văn bản. Người dùng viết cấu trúc bằng ký tự, từ khóa, tên và biểu thức trong editor. Mô hình kết quả thường là các đối tượng EMF có liên kết và source information.

DSL đồ họa có thể dùng những công cụ khác trong hệ sinh thái Eclipse Modeling. Tuy nhiên, một mô hình được tạo bởi Xtext vẫn có thể được hiển thị trong view, diagram hoặc công cụ đồ họa do nhóm phát triển xây dựng.

### 1.2. Xtext và parser generator

Parser generator thường tập trung vào việc chuyển grammar thành parser. Xtext bao quanh parser bằng mô hình EMF, linking, validation, serialization và tích hợp IDE. Đây là khác biệt quan trọng khi xây một DSL cần được sử dụng và bảo trì lâu dài.

## 2. Kiến trúc tổng quan

Một dự án Xtext thường có các thành phần sau:

```text
              Grammar (.xtext)
                     |
                     v
             MWE2 Generator
                     |
          +----------+-----------+
          |          |           |
          v          v           v
       Ecore      Parser      Runtime services
       model                  (linking, scope,
                              serializer, ...)
          |          |           |
          +----------+-----------+
                     |
                     v
              Semantic model
                     |
          +----------+-----------+
          |          |           |
          v          v           v
       Validation  IDE/LSP    Code generation
          |          |           |
          +----------+-----------+
                     |
                     v
              DSL Workbench
```

Các phần thường được chia thành runtime language project, IDE integration project và test project. Một số cấu hình còn có web editor hoặc language server để hỗ trợ những môi trường không dùng Eclipse desktop.

### 2.1. Grammar là điểm bắt đầu

Grammar mô tả cách văn bản được cấu trúc thành các quy tắc và thành phần mô hình. Từ grammar, Xtext tạo parser và có thể suy ra Ecore metamodel nếu dự án không cung cấp metamodel riêng.

### 2.2. EMF là nền tảng mô hình

EMF (Eclipse Modeling Framework) cung cấp cách biểu diễn mô hình dưới dạng EClass, EAttribute, EReference, EObject và Resource. Mô hình này trở thành dữ liệu trung tâm mà validation, generator và editor cùng sử dụng.

### 2.3. Dịch vụ ngôn ngữ

Xtext tạo hạ tầng để phân giải tham chiếu, tính scope, xác thực mô hình, serialize và hỗ trợ các chức năng editor. Các dịch vụ này có thể được thay thế hoặc mở rộng bằng dependency injection.

## 3. Grammar của Xtext

Grammar Xtext được viết trong tệp `.xtext`. Nó mô tả parser rules, terminal rules, datatype rules, keyword, cross-reference và cách các phần văn bản tạo thành mô hình.

Một grammar thường bắt đầu bằng tên ngôn ngữ và khai báo terminal grammar dùng chung:

```text
grammar org.example.workflow.Workflow
    with org.eclipse.xtext.common.Terminals

generate workflow "https://example.org/workflow"

Model:
    (elements += Element)*;

Element:
    Entity | TypeDecl | Rule;

Entity:
    "entity" name = QualifiedName "{"
        (features += Feature)*
    "}";

Feature:
    name = ID ":" type = [TypeDecl | QualifiedName];

TypeDecl:
    "type" name = QualifiedName;

Rule:
    "rule" name = ID
    "when" condition = Expression
    "then" action = Action;

Action:
    "set" target = [Feature | QualifiedName]
    "=" value = Expression;

QualifiedName:
    ID ("." ID)*;
```

Đây là grammar minh họa cho các khái niệm chính. Một dự án thực tế cần bổ sung các quy tắc biểu thức, kiểu, import, comment, dấu phân cách và kiểm tra cú pháp phù hợp với ngôn ngữ của mình.

### 3.1. Parser rules

Parser rule bắt đầu bằng tên quy tắc viết hoa và mô tả cấu trúc cú pháp. Ví dụ `Entity`, `Feature` và `Rule` là các parser rules. Các assignment như `name = ID` cho biết token hoặc kết quả quy tắc con được gán vào feature của mô hình.

Các toán tử grammar thường dùng:

| Cú pháp | Ý nghĩa |
|---|---|
| `A B` | A theo sau bởi B |
| `A | B` | Chọn A hoặc B |
| `A?` | A có thể xuất hiện không hoặc một lần |
| `A*` | A lặp không hoặc nhiều lần |
| `A+` | A lặp một hoặc nhiều lần |
| `items += A` | Thêm kết quả A vào feature dạng nhiều giá trị |
| `name = ID` | Gán kết quả vào feature name |
| `returns Type` | Quy định kiểu mô hình mà rule trả về |

### 3.2. Keywords và terminals

Chuỗi trong dấu nháy như `"entity"`, `"rule"` hoặc `"when"` là keyword cụ thể của DSL. `ID`, `INT`, `STRING` thường đến từ terminal grammar dùng chung.

Terminal rule xác định cách lexer nhận diện token ở mức ký tự. Parser rule kết hợp các token thành cấu trúc lớn hơn. Nên tận dụng các terminal phổ biến trước khi định nghĩa terminal riêng để tránh xung đột token và hành vi khó dự đoán.

### 3.3. Hidden tokens

Whitespace và comment thường không cần xuất hiện trong AST nghiệp vụ, nhưng vẫn cần được parser chấp nhận. Xtext cho phép khai báo hidden tokens ở mức grammar hoặc rule để khoảng trắng/comment không làm thay đổi cấu trúc mô hình.

Ví dụ, ngôn ngữ có thể cho phép `WS`, comment một dòng và comment nhiều dòng xuất hiện giữa các thành phần cú pháp. Cần xác định comment có được giữ trong node model để formatter hoặc công cụ tài liệu sử dụng hay không.

### 3.4. Datatype rules

Datatype rule tạo giá trị dữ liệu đơn giản như tên đầy đủ, version hoặc literal đã được chuyển đổi. Ví dụ `QualifiedName` trong grammar trên có thể được chuyển thành một chuỗi tên theo quy tắc chuyển đổi của Xtext.

### 3.5. Cross-references

Cú pháp `[TypeDecl | QualifiedName]` biểu thị một tham chiếu đến đối tượng mô hình thuộc kiểu `TypeDecl`, được viết trong văn bản dưới dạng `QualifiedName`. Xtext phân tích văn bản tham chiếu trước; linking sẽ tìm đối tượng đích trong scope phù hợp.

Điểm quan trọng là cross-reference khác với string attribute. Nó tạo liên kết mô hình giữa hai EObject, giúp validator, editor và generator truy cập trực tiếp đối tượng đích sau khi resolve.

## 4. Mô hình EMF được sinh từ grammar

Khi dùng Ecore inference, Xtext suy ra metamodel từ parser rules và assignment. Mỗi parser rule tạo hoặc sử dụng một EClass; assignment tạo EAttribute hoặc EReference tùy kiểu kết quả.

Ví dụ:

```text
Entity:
    "entity" name = QualifiedName "{"
        (features += Feature)*
    "}";
```

Có thể tạo mô hình khái niệm:

```text
Entity
├── name: EString
└── features: Feature[*]

Feature
├── name: EString
└── type: TypeDecl [reference]
```

### 4.1. EClass

EClass mô tả một loại đối tượng mô hình, tương tự class trong mô hình hướng đối tượng. Ví dụ `Entity`, `Feature`, `Rule` và `TypeDecl` có thể là các EClass.

### 4.2. EAttribute

EAttribute lưu dữ liệu đơn giản như tên, số, Boolean hoặc chuỗi. Ví dụ `name: EString` là attribute chứa tên khai báo.

### 4.3. EReference

EReference biểu diễn quan hệ giữa các EObject. Feature `features` của `Entity` là containment reference đến các `Feature`; `type` của `Feature` là non-containment cross-reference đến `TypeDecl`.

### 4.4. Containment

Containment xác định đối tượng con thuộc về đối tượng cha trong mô hình. Khi xóa hoặc serialize container, các phần tử con được quản lý theo quan hệ containment. Ví dụ một `Entity` chứa danh sách `Feature`.

### 4.5. Cross-reference và containment khác nhau

Containment thể hiện cấu trúc sở hữu. Cross-reference thể hiện liên kết đến đối tượng có thể được định nghĩa ở nơi khác. Một `Feature` thuộc một `Entity`, nhưng kiểu của feature có thể tham chiếu đến `TypeDecl` nằm ở module khác.

### 4.6. Tự định nghĩa Ecore hay dùng inference?

Ecore inference tiện cho DSL mới và mô hình đơn giản. Nếu dự án đã có metamodel hoặc cần kiểm soát inheritance, package URI, cardinality và kiểu tham chiếu chi tiết, có thể định nghĩa Ecore trước rồi ánh xạ grammar vào mô hình đó.

Không nên sửa trực tiếp các tệp generated Ecore hoặc mã nguồn sinh ra. Thay đổi cần thực hiện ở grammar, metamodel gốc hoặc cấu hình generator rồi chạy lại workflow.

## 5. Parser và node model

Parser chuyển văn bản DSL thành mô hình EMF. Bên cạnh semantic model, Xtext còn duy trì node model mô tả cấu trúc cú pháp và vị trí các đoạn văn bản.

### 5.1. Semantic model

Semantic model chứa các EObject mà ứng dụng quan tâm: entity, field, rule, expression và các liên kết. Code generator hoặc validator thường làm việc chủ yếu trên mô hình này.

### 5.2. Node model

Node model giữ thông tin về cách văn bản được parse, bao gồm token, khoảng trắng, comment và source offset. Nó hữu ích cho diagnostics, hover, formatter, serializer và các công cụ cần biết vị trí văn bản gốc.

### 5.3. Vì sao cần cả hai?

Semantic model thuận tiện cho xử lý ngữ nghĩa vì không phải thao tác trực tiếp trên token. Node model giữ thông tin cú pháp mà semantic model có thể không lưu, như comment và whitespace. Xtext kết hợp hai mô hình để vừa xử lý logic ngôn ngữ vừa hỗ trợ editor.

### 5.4. Parse lỗi một phần

Trong lúc người dùng gõ, văn bản thường chưa hoàn chỉnh. Xtext cần hỗ trợ trạng thái parse có lỗi để editor vẫn hiển thị mô hình phần nào và đưa ra diagnostic. Các dịch vụ tùy chỉnh nên xử lý null hoặc EObject chưa hoàn chỉnh thay vì giả định mọi feature đều có giá trị.

## 6. Linking và scoping

Parsing xác định cấu trúc và tạo các node cross-reference. Linking tìm đối tượng mà mỗi cross-reference trỏ đến. Scoping xác định tập symbol có thể được nhìn thấy tại một vị trí.

Ví dụ:

```text
module sales

type Money

entity Order {
    total: Money
}
```

Parser nhận `Money` là văn bản tham chiếu. Linker dùng scope để tìm `TypeDecl` có tên phù hợp. Khi resolve thành công, feature `type` của `Feature` trỏ đến EObject `Money`.

### 6.1. Qualified name provider

`IQualifiedNameProvider` xác định tên đầy đủ của một EObject. Ví dụ entity `Order` trong module `sales` có thể có qualified name `sales.Order`; field có thể là `sales.Order.total` nếu DSL chọn quy ước đó.

Qualified name là cơ sở cho import, cross-reference, index và tìm kiếm symbol.

### 6.2. Scope provider

`IScopeProvider` xác định các description/symbol có thể được resolve tại vị trí tham chiếu. Có thể cung cấp scope cục bộ, scope của module, scope từ import hoặc scope toàn cục.

Ví dụ, một field access `order.total` chỉ nên thấy các field thuộc kiểu của `order`, chứ không phải mọi field `total` trong workspace.

### 6.3. Import và namespace

DSL nhiều module thường cần import. Scope provider có thể đọc import declaration, resolve module được nhập rồi đưa các export hợp lệ vào scope hiện tại. Alias import cần ánh xạ tên cục bộ về symbol gốc.

### 6.4. Lazy linking

Xtext hỗ trợ liên kết tham chiếu theo cơ chế lazy trong nhiều luồng xử lý. Việc resolve có thể được trì hoãn đến khi một thành phần mô hình được truy cập. Điều này giúp quản lý dự án lớn nhưng cũng có nghĩa lỗi linking có thể xuất hiện ở bước validation hoặc khi editor yêu cầu thông tin symbol.

### 6.5. Linking diagnostics

Khi không tìm thấy đối tượng đích, Xtext có thể tạo linking error. Validator hoặc editor cần hiển thị lỗi với tên chưa resolve, vị trí và gợi ý kiểm tra import, scope hoặc tên symbol.

## 7. Kiểm tra ngữ nghĩa và validation

Grammar chỉ mô tả cấu trúc cú pháp. Nhiều quy tắc miền cần được kiểm tra sau khi mô hình đã được tạo và các tham chiếu được resolve.

Ví dụ:

- Tên entity phải duy nhất trong module.
- Một rule phải tham chiếu đến field tồn tại.
- Field `total` phải có kiểu `Money`.
- Biểu thức điều kiện phải trả về Boolean.
- Không được gán vào thuộc tính chỉ đọc.
- Một workflow không được có transition đến step không tồn tại.

### 7.1. AbstractDeclarativeValidator

Xtext cung cấp cơ chế validator khai báo, thường được triển khai bằng cách mở rộng `AbstractDeclarativeValidator`. Các phương thức validation được gắn với EClass hoặc feature và có thể phát ra diagnostic.

Ví dụ minh họa bằng Xtend:

```xtend
class WorkflowValidator extends AbstractDeclarativeValidator {

    @Check
    def checkUniqueFeatureNames(Entity entity) {
        val names = entity.features.map[name]
        if (names.size != names.toSet.size) {
            error(
                "Feature names must be unique",
                entity,
                null,
                "duplicate-feature-name"
            )
        }
    }
}
```

Đây là ví dụ khái niệm; chữ ký API và cách chọn feature cần điều chỉnh theo phiên bản Xtext và metamodel thực tế.

### 7.2. Phân loại lỗi

Có thể chia kiểm tra thành:

- Syntax errors: văn bản không tuân grammar.
- Linking errors: cross-reference không tìm thấy symbol.
- Semantic errors: mô hình parse được nhưng vi phạm quy tắc miền.
- Warnings: cấu trúc hợp lệ nhưng có thể gây vấn đề.
- Infos: thông tin hỗ trợ người dùng.

### 7.3. Diagnostic location

Validator nên gắn lỗi vào feature hoặc EObject liên quan để editor đánh dấu đúng vùng văn bản. Có thể cung cấp mã lỗi ổn định để quick fix hoặc công cụ CI nhận diện.

### 7.4. Kiểm tra phụ thuộc

Validation có thể cần đọc nhiều resource. Cần tránh resolve toàn bộ workspace không kiểm soát hoặc tạo vòng lặp validation. Nên dùng resource set và index phù hợp, đồng thời xác định rõ lỗi nào thuộc file hiện tại và lỗi nào đến từ dependency.

## 8. Serialization và formatting

Serializer chuyển mô hình EMF trở lại văn bản DSL. Nó hữu ích khi công cụ chỉnh sửa mô hình trực tiếp, refactoring hoặc generator cập nhật một phần file.

### 8.1. Serializer

Xtext có thể serialize semantic model thành cú pháp hợp lệ theo grammar. Serializer cần biết cross-reference được biểu diễn bằng tên nào, thứ tự feature và cách tạo keyword/dấu phân cách.

### 8.2. Node model và round-trip

Trong trường hợp chỉ đọc và phân tích, node model giúp giữ lại thông tin văn bản gốc. Khi chỉnh sửa mô hình rồi serialize, kết quả có thể chuẩn hóa cách viết hoặc format tùy cấu hình.

### 8.3. Formatter

Formatter quy định indentation, khoảng trắng, dòng trống và cách xuống dòng. Một formatter tốt cải thiện khả năng đọc mà không thay đổi semantics.

### 8.4. Partial serialization

Khi chỉ thay đổi một phần mô hình, serializer có thể cần cập nhật đoạn tương ứng trong văn bản. Điều này phức tạp hơn serialize toàn bộ vì phải giữ các comment hoặc vùng không liên quan. Nên kiểm tra rõ hành vi đối với comment và whitespace.

## 9. Code generation

Xtext cung cấp mô hình đã parse và resolve để nhóm phát triển sinh mã nguồn, cấu hình hoặc artifact khác. Code generation thường được triển khai như một dịch vụ riêng chạy trên Resource hoặc mô hình DSL.

Ví dụ DSL:

```text
rule freeShipping {
    when order.total >= 1000000
    then set order.shippingFee = 0
}
```

Generator có thể tạo Java, Kotlin, SQL, JSON hoặc một IR riêng. Nên tách semantics DSL khỏi chi tiết target để có thể hỗ trợ nhiều backend.

### 9.1. IGenerator2

Trong các phiên bản Xtext hiện đại, generator thường triển khai `IGenerator2`. Nó nhận resource và file system access, sau đó ghi các artifact vào vị trí được build system quản lý.

### 9.2. Sinh nhiều file

Một resource DSL có thể sinh nhiều file, ví dụ một class cho mỗi entity, một registry cho các rule và metadata cho runtime. Generator cần đặt tên file ổn định và tránh xung đột giữa module.

### 9.3. Idempotent generation

Cùng source, dependency và cấu hình nên tạo output xác định. Generator không nên phụ thuộc timestamp hoặc thứ tự duyệt map ngẫu nhiên nếu điều đó làm output thay đổi không cần thiết.

### 9.4. Generated source không chỉnh sửa thủ công

Các file sinh ra nên được xem là artifact có thể tái tạo. Thay đổi thủ công sẽ bị ghi đè ở lần generate tiếp theo. Logic cần sửa nên nằm trong generator, template hoặc runtime library.

### 9.5. Source mapping

Nếu output được biên dịch hoặc debug, nên giữ mapping từ generated code về source DSL. Xtext có node model và source information làm nền tảng để ghi nhận nguồn gốc của artifact.

## 10. MWE2 và quá trình sinh hạ tầng ngôn ngữ

Xtext sử dụng MWE2 (Modeling Workflow Engine 2) để cấu hình và chạy workflow sinh mã cho language infrastructure.

Một dự án thường có file workflow như `GenerateWorkflow.mwe2`. Workflow cấu hình Xtext generator, grammar, project layout và các thành phần cần sinh.

### 10.1. Vai trò của MWE2

MWE2 mô tả chuỗi component và cấu hình cho quá trình sinh. Nó không phải grammar của DSL và cũng không phải chương trình DSL cuối cùng. Đây là công cụ phát triển để tạo các thành phần của ngôn ngữ.

### 10.2. Khi nào chạy lại workflow?

Khi grammar, Ecore hoặc cấu hình generator thay đổi, cần chạy workflow để cập nhật các artifact generated. Không nên sửa tay mã nguồn được sinh rồi bỏ qua nguyên nhân gốc.

### 10.3. Generated code và handwritten code

Xtext thường phân biệt thư mục generated với thư mục source do người phát triển quản lý. Cần giữ ranh giới này để workflow có thể chạy lặp lại mà không xóa logic tùy chỉnh.

### 10.4. Tái lập build

Workflow, phiên bản Xtext, EMF, MWE2 và dependency cần được quản lý trong build. Điều này giúp các thành viên nhóm và CI tạo cùng bộ language infrastructure.

## 11. Cấu trúc một dự án Xtext

Project layout thay đổi theo phiên bản và lựa chọn tích hợp, nhưng một bộ dự án phổ biến có thể gồm:

```text
workflow-language/
├── org.example.workflow/
│   ├── src/
│   │   └── ...
│   ├── src-gen/
│   │   └── ...
│   ├── src/main/resources/
│   └── GenerateWorkflow.mwe2
├── org.example.workflow.ide/
│   └── IDE language services
├── org.example.workflow.ui/
│   └── Eclipse UI integration
├── org.example.workflow.tests/
│   └── parser and validation tests
└── build configuration
```

### 11.1. Runtime project

Runtime project chứa grammar, mô hình, parser và các dịch vụ cần để nạp/phân tích DSL. Nó nên tránh phụ thuộc vào UI để có thể chạy trong command line, build server hoặc ứng dụng độc lập.

### 11.2. IDE project

IDE project tích hợp các dịch vụ ngôn ngữ với môi trường phát triển. Tùy template và phiên bản, nó có thể chứa content assist, hover, outline, label provider, quick fix và các binding phục vụ editor.

### 11.3. UI project

UI project chứa tích hợp riêng với Eclipse desktop như editor plugin, preference page, wizard hoặc UI-specific behavior. Không nên đặt logic ngữ nghĩa cốt lõi ở đây nếu runtime hoặc LSP cũng cần sử dụng.

### 11.4. Test project

Test project kiểm tra parser, linking, validation, serializer và các dịch vụ IDE. Test giúp thay đổi grammar không âm thầm phá mô hình hoặc trải nghiệm editor.

## 12. Dependency injection và customization

Xtext sử dụng Google Guice cho dependency injection. Các dịch vụ như scope provider, validator, generator và formatter được cung cấp qua binding, cho phép thay implementation mặc định bằng implementation của dự án.

### 12.1. Runtime module

Runtime module cấu hình các dịch vụ không phụ thuộc UI. Ví dụ có thể bind custom scope provider, qualified name provider hoặc validator.

### 12.2. UI/IDE module

IDE module cấu hình dịch vụ liên quan editor như content assist, hover, outline, quick fix hoặc semantic highlighting.

### 12.3. Không sửa generated binding trực tiếp

Các binding được sinh có thể bị thay thế khi workflow chạy lại. Cách đúng là khai báo customization trong module mở rộng hoặc cơ chế override được Xtext hỗ trợ.

### 12.4. Dependency boundaries

Giữ runtime độc lập với Eclipse UI giúp DSL có thể được dùng trong nhiều môi trường. Logic semantic nên nằm ở lớp dùng chung; UI chỉ chịu trách nhiệm trình bày và tương tác.

## 13. Tạo trải nghiệm editor/workbench

Xtext có thể tạo nền tảng editor cho DSL trong Eclipse và tích hợp các dịch vụ ngôn ngữ với môi trường khác.

Các tính năng thường gặp:

- Syntax highlighting: tô màu keyword, string, comment và token.
- Content assist: đề xuất keyword, symbol và member hợp lệ.
- Validation markers: hiển thị lỗi và cảnh báo tại source range.
- Hover: hiển thị kiểu, chữ ký hoặc documentation.
- Outline: hiển thị cấu trúc entity, rule, workflow và function.
- Go to Definition: điều hướng đến khai báo symbol.
- Find References: tìm nơi sử dụng symbol.
- Rename: đổi tên symbol và cập nhật references.
- Quick fixes: đề xuất sửa lỗi.
- Formatting: chuẩn hóa khoảng trắng và bố cục.

### 13.1. Syntax highlighting

Editor cần phân biệt keyword, identifier, string, comment và các thành phần đặc biệt. Semantic highlighting có thể dùng thông tin symbol/type để tô màu khác nhau cho field, parameter, function hoặc deprecated element.

### 13.2. Content assist

Content assist nên dựa trên grammar và scope. Khi người dùng nhập sau `entity`, editor có thể đề xuất identifier; khi nhập sau dấu `:`, có thể đề xuất các kiểu nhìn thấy trong scope.

### 13.3. Hover

Hover có thể hiển thị qualified name, type, signature, documentation hoặc diagnostic. Dữ liệu nên lấy từ semantic model thay vì chỉ hiển thị token text.

### 13.4. Outline

Outline cho phép xem cấu trúc file và điều hướng đến các khai báo lớn. Label provider có thể hiển thị tên, loại và thông tin quan trọng của từng node.

### 13.5. Quick fixes

Quick fix có thể sửa import thiếu, thêm trường bắt buộc hoặc thay tên symbol. Chỉ nên tự động áp dụng khi phép sửa có cơ sở rõ; những thay đổi có nhiều cách hiểu cần cho người dùng lựa chọn.

## 14. Language Server Protocol và Xtext

Ngoài Eclipse desktop, Xtext có thể cung cấp dịch vụ ngôn ngữ qua Language Server Protocol (LSP) để tích hợp với các editor hỗ trợ giao thức này.

LSP chuẩn hóa request/response cho các chức năng như:

- `textDocument/completion` cho content assist.
- `textDocument/hover` cho hover information.
- `textDocument/definition` cho Go to Definition.
- `textDocument/references` cho Find All References.
- `textDocument/rename` cho Rename Symbol.
- `textDocument/formatting` cho formatting.
- `textDocument/publishDiagnostics` cho diagnostics.

### 14.1. Runtime dùng chung

Điểm quan trọng là parser, linker, scope provider và validator có thể được dùng chung giữa Eclipse UI và LSP. Nhờ đó, semantics không bị nhân đôi trong từng editor.

### 14.2. Position và source range

LSP dùng URI và position. Language server phải chuyển đổi đúng giữa offset nội bộ, dòng/cột và position encoding mà client đã thương lượng. Unicode có thể khiến byte offset và character offset khác nhau.

### 14.3. Cancellation và incremental document sync

Editor gửi nội dung tài liệu thay đổi liên tục. Language server cần cập nhật document snapshot, hủy request cũ khi cần và tránh trả kết quả từ phiên bản tài liệu đã lỗi thời.

### 14.4. Chọn môi trường tích hợp

Eclipse plugin phù hợp khi nhóm dùng Eclipse Modeling và cần workbench sâu. LSP phù hợp khi muốn hỗ trợ nhiều editor. Xtext Web có thể phù hợp với trải nghiệm chỉnh sửa DSL trong trình duyệt. Lựa chọn phụ thuộc môi trường người dùng và yêu cầu triển khai.

## 15. Xtext Web và editor trên trình duyệt

Xtext Web cung cấp hạ tầng để nhúng editor DSL vào ứng dụng web. Nó hữu ích khi người dùng nghiệp vụ không làm việc trong IDE desktop nhưng cần chỉnh sửa cấu hình hoặc rule trực tiếp trên một portal.

### 15.1. Browser editor

Editor web có thể cung cấp syntax highlighting, content assist và validation thông qua giao tiếp với dịch vụ phía server.

### 15.2. Server-side language services

Parser và validator có thể chạy phía server. Ứng dụng web gửi nội dung và nhận kết quả phân tích hoặc đề xuất hoàn thành.

### 15.3. Bảo mật và multi-tenant

Khi nhiều người dùng cùng truy cập editor web, cần cô lập session, workspace và dữ liệu. Không được để resource set hoặc state của một phiên người dùng rò sang phiên khác.

### 15.4. Lựa chọn giữa Web và LSP

Xtext Web phù hợp với editor được nhúng trong ứng dụng web có UI tùy biến. LSP phù hợp với editor bên ngoài sử dụng giao thức chuẩn. Hai hướng có thể chia sẻ runtime language services nhưng khác cách tích hợp.

## 16. Xây dựng DSL hoàn chỉnh với Xtext

Một quy trình phát triển có thể gồm các bước:

1. Xác định người dùng, bài toán miền và các cấu trúc DSL cần biểu đạt.
2. Thiết kế cú pháp bằng ví dụ thực tế trước khi viết grammar.
3. Viết grammar Xtext và chọn terminal grammar phù hợp.
4. Xác định Ecore inference hay metamodel có sẵn.
5. Chạy MWE2 để sinh parser, model và language infrastructure.
6. Kiểm tra parse tree và semantic model bằng các fixture.
7. Cài đặt qualified name provider, scope provider và linking rules.
8. Viết validator cho quy tắc kiểu và nghiệp vụ.
9. Tùy biến content assist, formatter, hover, outline và quick fixes.
10. Viết serializer hoặc code generator nếu cần output.
11. Tích hợp Eclipse, LSP hoặc web editor.
12. Thêm build, test, dependency versioning và packaging.

### 16.1. Thiết kế grammar từ ví dụ

Trước khi tạo grammar lớn, nên thu thập các file DSL mẫu: trường hợp thông thường, trường hợp lồng nhau, tên trùng, lỗi cú pháp và cấu trúc biên. Ví dụ giúp xác định grammar có dễ viết và dễ đọc không.

### 16.2. Giữ grammar dễ bảo trì

Không nên nhồi mọi quy tắc ngữ nghĩa vào grammar. Grammar nên mô tả cấu trúc cú pháp; quy tắc như “field phải thuộc entity này” hoặc “đơn hàng không thể có tổng âm” thường thuộc linking/validation.

### 16.3. Xác định phần nào là syntax sugar

Các cú pháp tiện dụng có thể được chuyển về một core model thống nhất. Điều này làm generator và validator đơn giản hơn, đồng thời giảm số dạng AST cần xử lý.

## 17. Kiểm thử dự án Xtext

Xtext có các tiện ích test giúp parse DSL, lấy EObject, kiểm tra diagnostic và thử dịch vụ ngôn ngữ.

Các lớp kiểm thử nên bao gồm:

- Grammar/parser tests: input hợp lệ tạo đúng model; input sai tạo syntax diagnostic.
- Linking tests: cross-reference resolve đúng symbol và báo lỗi khi thiếu.
- Scope tests: import, alias, visibility và shadowing hoạt động đúng.
- Validation tests: lỗi và warning gắn đúng EObject/feature.
- Serialization tests: model serialize thành văn bản hợp lệ.
- Generator tests: output đúng, ổn định và có thể build/run.
- Content assist tests: proposal phù hợp vị trí và scope.
- LSP/IDE tests: definition, references, rename, hover và diagnostics.
- Regression tests: grammar thay đổi không làm hỏng các file DSL hiện có.

### 17.1. ParseHelper

Xtext test framework thường cung cấp `ParseHelper` để parse chuỗi DSL thành EObject hoặc Resource. Test có thể kiểm tra model, số lượng phần tử và cross-reference.

Ví dụ khái niệm:

```xtend
val model = parseHelper.parse("""
    entity Order {
        total: Money
    }
""")

model.elements.head.name.toString shouldBe "Order"
```

Cú pháp test cụ thể phụ thuộc test framework và phiên bản. Mục tiêu là xác nhận parser tạo mô hình đúng theo grammar.

### 17.2. ValidationTestHelper

`ValidationTestHelper` hỗ trợ kiểm tra diagnostic trên Resource hoặc EObject. Test nên xác nhận error code, severity, message và feature/range nếu phù hợp.

### 17.3. Test nhiều resource

Để kiểm tra linking và import, cần load nhiều resource trong cùng ResourceSet hoặc workspace fixture. Chỉ parse một chuỗi độc lập không thể chứng minh scope provider hoạt động đúng với module khác.

### 17.4. Test generated output

Nếu DSL sinh mã, nên compile hoặc chạy output bằng toolchain target. Golden test chỉ kiểm tra văn bản; execution test mới xác nhận hành vi ở một số trường hợp.

## 18. Build, packaging và triển khai

Xtext language infrastructure cần được build và đóng gói cùng dependency phù hợp.

### 18.1. Version compatibility

Xtext, EMF, Guice, MWE2, Eclipse Platform và plugin liên quan có quan hệ phiên bản. Cần khóa và kiểm tra compatibility thay vì trộn dependency từ các release khác nhau.

### 18.2. Maven và Gradle

Dự án có thể tích hợp Xtext generation và test vào Maven hoặc Gradle. Cách cấu hình plugin và task phụ thuộc phiên bản Xtext và project template. Nên dùng cấu hình do phiên bản framework hướng dẫn và bảo đảm CI chạy cùng workflow generation như môi trường phát triển.

### 18.3. Eclipse plugin packaging

Nếu phân phối editor cho Eclipse, cần đóng gói runtime, UI/IDE plugin và dependency cần thiết. Target platform và version Eclipse cần được xác định để người dùng cài đặt nhất quán.

### 18.4. Language server packaging

Với LSP, cần đóng gói server executable hoặc launcher, runtime dependencies và cấu hình khởi động. Editor client phải biết command, arguments và cách đồng bộ document.

### 18.5. Standalone execution

Ứng dụng command line hoặc server có thể dùng injector và ResourceSet của Xtext để parse/validate/generate mà không khởi chạy Eclipse UI. Đây là lý do nên giữ runtime project độc lập với UI.

### 18.6. CI

CI nên tái tạo generated infrastructure, chạy test và xác nhận các file generated không bị lệch khỏi grammar/configuration. Không nên dựa vào artifact generated chỉ tồn tại trên máy của một developer.

## 19. Mở rộng Xtext bằng Xtend hoặc Java

Xtext thường được sử dụng cùng Xtend, một ngôn ngữ JVM có cú pháp gọn và tích hợp tốt với Java. Các service như validator, generator, scope provider hoặc formatter có thể được viết bằng Xtend hoặc Java.

### 19.1. Chọn Xtend hay Java

Xtend có cú pháp ngắn cho xử lý model và template; Java quen thuộc với nhiều nhóm và có thể phù hợp khi dự án đã có codebase Java lớn. Hai ngôn ngữ có thể tương tác qua JVM.

### 19.2. Template generation

Xtend hỗ trợ template giúp sinh văn bản có cấu trúc. Dù dùng template, vẫn cần tách dữ liệu khỏi code output, escape literal đúng target và kiểm soát tên file.

### 19.3. Không phụ thuộc UI trong service ngữ nghĩa

Validator, resolver và generator nên dùng runtime services. Nếu một service cần hoạt động trong command line hoặc LSP, không nên phụ thuộc vào SWT hoặc Eclipse UI classes.

## 20. Các điểm mạnh và giới hạn của Xtext

### 20.1. Điểm mạnh

- Grammar mô tả cú pháp tập trung và có thể sinh parser.
- Mô hình EMF tích hợp tốt với hệ sinh thái modeling.
- Có linking, scoping và validation infrastructure.
- Có serializer và hỗ trợ source-aware tooling.
- Tích hợp editor, content assist, outline, hover và quick fix.
- Có thể mở rộng bằng Java/Xtend và dependency injection.
- Hỗ trợ nhiều hướng tích hợp như Eclipse, LSP và web.
- Phù hợp với DSL có nhiều file, symbol và quan hệ mô hình.

### 20.2. Giới hạn và chi phí

- Cần hiểu Xtext, EMF, MWE2 và dependency injection.
- Grammar phức tạp có thể khó thiết kế và debug.
- Việc sinh nhiều project/plugin làm cấu hình ban đầu khá lớn.
- Thay đổi grammar có thể ảnh hưởng metamodel và dữ liệu đã lưu.
- Tối ưu hiệu năng workspace lớn cần chú ý indexing và resource lifecycle.
- Tích hợp với phiên bản IDE, Java và dependency cần được quản lý.
- Một DSL rất nhỏ có thể không cần toàn bộ framework.

### 20.3. Khi nào nên chọn Xtext?

Xtext phù hợp khi DSL cần grammar văn bản, mô hình có cấu trúc, tham chiếu giữa nhiều file và trải nghiệm IDE tương đối đầy đủ. Nếu chỉ cần một file cấu hình đơn giản, parser nhỏ hoặc schema validator có thể đủ. Nếu trọng tâm là cú pháp đồ họa, cần đánh giá công cụ modeling phù hợp hơn.

## 21. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Đưa mọi quy tắc miền vào grammar | Grammar phức tạp và khó đọc | Tách syntax khỏi semantic validation |
| Không thiết kế Ecore model | Model khó mở rộng hoặc serialize | Xác định EClass, containment và reference từ đầu |
| Nhầm attribute với cross-reference | Không thể điều hướng hoặc resolve symbol đúng | Dùng cross-reference cho liên kết đến EObject |
| Scope provider quá rộng | Tên resolve nhầm symbol cùng tên | Giới hạn scope theo module, type và import |
| Không có qualified name convention | Import và index thiếu nhất quán | Định nghĩa qualified name ổn định |
| Sửa file generated trực tiếp | Thay đổi bị mất khi chạy workflow | Sửa grammar, metamodel hoặc customization source |
| Đặt logic ngữ nghĩa trong UI project | CLI/LSP không dùng lại được | Đưa logic vào runtime services |
| Không xử lý model chưa hoàn chỉnh | Editor crash khi người dùng đang gõ | Viết service chịu được partial parse và null |
| Bỏ qua serialization | Model editor không thể ghi lại DSL ổn định | Kiểm tra serializer và round-trip |
| Chỉ test parser một file | Linking nhiều module không được kiểm tra | Test nhiều Resource trong cùng ResourceSet |
| Không khóa version dependencies | Build khác nhau giữa máy và CI | Quản lý version Xtext/EMF/MWE2 thống nhất |

## 22. Quy trình phát triển và bảo trì Xtext

Một quy trình bền vững có thể tổ chức như sau:

1. **Thiết kế ngôn ngữ:** xác định khái niệm miền, ví dụ hợp lệ và các trường hợp lỗi.
2. **Thiết kế grammar:** viết parser rules, datatype rules, terminals và cross-references.
3. **Thiết kế metamodel:** chọn Ecore inference hoặc Ecore có sẵn; xác định containment và reference.
4. **Sinh hạ tầng:** chạy MWE2 để tạo parser, model và project services.
5. **Cài đặt linking:** định nghĩa qualified names, scope, import và visibility.
6. **Cài đặt validation:** kiểm tra kiểu, quan hệ và invariant miền.
7. **Hoàn thiện editor:** content assist, hover, outline, formatting, quick fixes và navigation.
8. **Thêm serialization/generation:** ghi lại model hoặc sinh artifact target khi cần.
9. **Kiểm thử:** parser, linking, validation, serializer, generator và IDE/LSP.
10. **Tích hợp build:** khóa dependency, chạy workflow và test trong CI.
11. **Quản lý version:** xử lý thay đổi grammar, Ecore và dữ liệu DSL đã lưu.
12. **Theo dõi runtime:** đo hiệu năng, indexing và xử lý resource trong workspace lớn.

### 22.1. Thay đổi grammar có thể là thay đổi schema

Vì grammar có thể sinh Ecore model, thay đổi assignment hoặc parser rule có thể thay đổi metamodel. Nếu mô hình được serialize thành XMI hoặc được các công cụ khác tiêu thụ, cần xem xét migration và tương thích dữ liệu.

### 22.2. Giữ ví dụ DSL làm tài liệu sống

Các file DSL mẫu vừa giúp onboarding vừa có thể được dùng trong parser/validation tests. Khi grammar thay đổi, ví dụ cho thấy cú pháp người dùng thực sự viết có còn hợp lệ không.

### 22.3. Tách public API và implementation detail

Qualified names, metamodel, runtime API và grammar public có thể trở thành hợp đồng mà người dùng DSL phụ thuộc. Nên version và thay đổi có kiểm soát; tránh để chi tiết nội bộ generated trở thành API ngoài ý muốn.

## 23. Ví dụ tổng hợp: từ grammar đến workbench

Giả sử DSL quản lý workflow đơn giản. Người dùng viết:

```text
workflow fulfillOrder {
    step validateOrder
    step chargePayment
    step dispatchShipment
}
```

Các thành phần Xtext có thể đảm nhiệm:

| Thành phần | Vai trò trong ví dụ |
|---|---|
| Grammar | Nhận `workflow`, tên và danh sách `step` |
| Ecore model | Tạo `Workflow` và các `Step` |
| Parser | Chuyển văn bản thành EObject |
| Scope/linker | Resolve tên step hoặc action nếu chúng tham chiếu declaration khác |
| Validator | Phát hiện step trùng hoặc step target không tồn tại |
| Content assist | Đề xuất tên step/action hợp lệ |
| Outline | Hiển thị workflow và các bước |
| Formatter | Chuẩn hóa indentation và dòng |
| Serializer | Chuyển mô hình đã chỉnh sửa về văn bản |
| Generator | Sinh workflow definition cho runtime đích |
| LSP/Eclipse integration | Cung cấp diagnostics, navigation và completion |

Khi người dùng nhập một tên step chưa tồn tại, parser vẫn có thể tạo mô hình với cross-reference chưa resolve; linker/validator sẽ đưa ra diagnostic. Content assist có thể đề xuất những step được phép trong scope. Khi build, generator chỉ nên tạo artifact sau khi mô hình đã vượt qua các kiểm tra cần thiết.

## 24. Nguyên tắc lựa chọn và sử dụng Xtext

Khi quyết định dùng Xtext, nên xem xét:

1. **Độ phức tạp của DSL:** có nhiều loại declaration, biểu thức và quan hệ cross-file không?
2. **Mô hình dữ liệu:** có cần EMF, serialization hoặc tích hợp modeling không?
3. **Trải nghiệm editor:** người dùng có cần completion, navigation, validation và quick fix không?
4. **Môi trường tích hợp:** Eclipse desktop, LSP editor, browser hay command line?
5. **Khả năng mở rộng:** grammar, metamodel và service có thể phát triển theo version không?
6. **Hiệu năng:** workspace có nhiều resource và dependency không?
7. **Build và dependency:** nhóm có thể quản lý phiên bản Xtext/EMF/MWE2 trong CI không?
8. **Runtime semantics:** interpreter hoặc generated target có thể dùng chung model và validation không?
9. **Đội ngũ:** nhóm có kinh nghiệm JVM, EMF, Xtend/Java và hệ sinh thái Eclipse không?
10. **Chi phí vận hành:** có cần duy trì plugin, language server hoặc web service lâu dài không?

## 25. Kết luận

Xtext là framework để xây dựng DSL văn bản với một hệ sinh thái đầy đủ hơn parser đơn thuần. Grammar mô tả cú pháp; Ecore/EMF biểu diễn mô hình; parser tạo EObject; linker và scope provider giải quyết tham chiếu; validator kiểm tra ngữ nghĩa; serializer và generator chuyển mô hình thành văn bản hoặc artifact; IDE/LSP/Web tích hợp các dịch vụ đó vào môi trường làm việc.

Điểm mạnh của Xtext nằm ở việc kết nối các thành phần ngôn ngữ thành một nền tảng thống nhất. Tuy nhiên, người phát triển vẫn phải thiết kế semantics, metamodel, scope, validation và trải nghiệm editor một cách có chủ đích. Việc tách runtime logic khỏi UI, quản lý generated code đúng cách, kiểm thử nhiều resource và khóa dependency giúp dự án DSL dễ mở rộng và tái lập.

Khi DSL có nhiều khai báo, tham chiếu, quy tắc miền và nhu cầu tooling, Xtext có thể giảm đáng kể công sức xây hạ tầng. Khi cú pháp rất nhỏ hoặc chỉ cần đọc một cấu hình đơn giản, cần cân nhắc xem toàn bộ workbench có thực sự cần thiết hay không. Lựa chọn phù hợp phụ thuộc vào quy mô ngôn ngữ, trải nghiệm người dùng và vòng đời bảo trì của DSL.
