# Bảng ký hiệu

Trong quá trình phân tích một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), parser có thể nhận diện một đoạn văn bản là tên của thực thể, thuộc tính, biến, kiểu dữ liệu hay hành động. Tuy nhiên, nhận diện được một tên chưa đủ để biết tên đó đang tham chiếu đến khai báo nào, có tồn tại trong phạm vi hiện tại hay có được phép sử dụng ở vị trí đó hay không.

**Bảng ký hiệu (symbol table)** là cấu trúc dữ liệu mà trình biên dịch hoặc bộ phân tích DSL dùng để lưu thông tin về các tên đã khai báo và tra cứu chúng khi gặp một tham chiếu. Bảng ký hiệu hỗ trợ phân giải tên (name resolution), kiểm tra phạm vi, phát hiện khai báo trùng, xác định kiểu và kiểm tra các quy tắc ngữ nghĩa.

Ví dụ, trong một DSL mô hình miền:

~~~text
entity Customer {
  property id: CustomerId
  property name: String
}

query activeCustomers {
  from Customer
  where Customer.active == true
}
~~~

Khi xử lý đoạn này, hệ thống cần biết Customer là thực thể nào, id và name là các thuộc tính được khai báo bên trong thực thể đó, String và CustomerId là kiểu nào, và Customer.active có trỏ đến một thuộc tính tồn tại hay không. Bảng ký hiệu lưu thông tin khai báo và cung cấp quy tắc tra cứu để trả lời những câu hỏi đó.

Bảng ký hiệu là một thành phần của quá trình phân tích ngữ nghĩa. Cách tổ chức nó phụ thuộc vào cú pháp, mô hình phạm vi và yêu cầu của DSL; không có một cấu trúc duy nhất phù hợp với mọi ngôn ngữ.

## 1. Bảng ký hiệu là gì?

Bảng ký hiệu là một cấu trúc ánh xạ tên (name) đến thông tin mô tả ký hiệu (symbol) tương ứng. Ký hiệu có thể đại diện cho:

- Thực thể, lớp hoặc kiểu dữ liệu.
- Thuộc tính, trường hoặc biến.
- Hàm, thao tác hoặc hành động.
- Tham số của hàm hay bước quy trình.
- Bí danh (alias) trong truy vấn.
- Không gian tên, mô-đun hoặc tài nguyên được nhập vào.

Một bản ghi ký hiệu thường chứa tên và loại khai báo, đồng thời có thể lưu kiểu dữ liệu, phạm vi, vị trí khai báo, quyền truy cập và các metadata khác.

Ví dụ, sau khi phân tích khai báo:

~~~text
entity Customer {
  property id: CustomerId
  property name: String
}
~~~

hệ thống có thể lưu thông tin khái quát:

| Tên | Loại ký hiệu | Kiểu hoặc thông tin liên quan | Phạm vi |
| --- | --- | --- | --- |
| Customer | Entity | Kiểu thực thể Customer | Mô-đun hiện tại |
| id | Property | CustomerId | Bên trong Customer |
| name | Property | String | Bên trong Customer |
| CustomerId | Type | Kiểu định danh | Mô-đun hoặc namespace được khai báo |

Bảng trên chỉ minh họa. Một triển khai có thể lưu ký hiệu thuộc tính trong bảng con của Customer, hoặc dùng một bảng chung với khóa phạm vi. Điều quan trọng là hệ thống giữ được mối quan hệ giữa khai báo và phạm vi mà khai báo có hiệu lực.

### 1.1. Symbol và identifier không giống nhau

**Identifier (định danh)** là chuỗi token dùng để đặt tên trong văn bản DSL. **Symbol (ký hiệu)** là đối tượng ngữ nghĩa đại diện cho một khai báo sau khi hệ thống đã nhận diện và xử lý nó.

Ví dụ, hai lần xuất hiện của Customer trong:

~~~text
entity Customer {
  property name: String
}

query customers {
  from Customer
}
~~~

là hai token định danh ở hai vị trí văn bản. Trong quá trình phân giải tên, tham chiếu Customer trong truy vấn được liên kết với ký hiệu của khai báo entity Customer.

Parser có thể tạo node AST chứa tên Customer dưới dạng chuỗi, nhưng bước name resolution cần tìm ký hiệu tương ứng và gắn tham chiếu đó vào node. Từ đó, các bước sau có thể dùng cùng một danh tính ký hiệu thay vì liên tục so sánh chuỗi.

### 1.2. Bảng ký hiệu không chỉ lưu tên

Nếu bảng chỉ lưu rằng Customer tồn tại, hệ thống vẫn chưa đủ thông tin để kiểm tra các thao tác. Nó thường cần biết Customer là entity hay hàm, thuộc tính name có kiểu gì, ký hiệu có truy cập được ở vị trí hiện tại không và khai báo nằm ở đâu.

Một cấu trúc ký hiệu tổng quát có thể gồm:

~~~text
Symbol
  name
  kind
  declaredType
  scope
  visibility
  declarationLocation
  metadata
~~~

Không phải mọi ký hiệu đều có mọi trường. Ví dụ, một alias trong truy vấn có thể có kiểu suy ra từ nguồn dữ liệu; một hàm có thể có danh sách kiểu tham số và kiểu trả về; một entity có thể trỏ đến danh sách thuộc tính.

## 2. Vai trò của bảng ký hiệu trong phân giải tên

Phân giải tên là quá trình xác định một tên được dùng trong chương trình tham chiếu đến khai báo nào. Bảng ký hiệu là cơ chế tra cứu trung tâm của quá trình này.

Xét ví dụ:

~~~text
entity Product {
  property price: Decimal
}

query expensiveProducts {
  from Product
  where price > 100
}
~~~

Parser có thể nhận diện Product và price là identifier. Name resolver cần thực hiện các bước:

1. Tra cứu Product trong phạm vi có thể truy cập.
2. Xác nhận ký hiệu tìm được là một entity hoặc kiểu dữ liệu có thể dùng sau from.
3. Tạo phạm vi truy vấn với các thuộc tính có thể truy cập từ nguồn Product.
4. Tra cứu price trong phạm vi truy vấn.
5. Liên kết tham chiếu price với thuộc tính Product.price.
6. Chuyển thông tin kiểu Decimal cho bước kiểm tra biểu thức price > 100.

Nếu không tìm thấy Product, hệ thống báo tên chưa được khai báo hoặc không thể truy cập. Nếu tìm thấy Product nhưng không có price, hệ thống báo thuộc tính không tồn tại. Nếu price có kiểu không hỗ trợ phép so sánh với 100, đó là lỗi kiểu sau khi tên đã được phân giải.

### 2.1. Quy trình từ văn bản đến ký hiệu

Một pipeline đơn giản:

~~~text
Văn bản DSL
    |
    v
Lexer
    |
    v
Token
    |
    v
Parser
    |
    v
AST (tên vẫn có thể là chuỗi)
    |
    v
Thu thập khai báo
    |
    v
Bảng ký hiệu / Scope
    |
    v
Phân giải tham chiếu
    |
    v
Kiểm tra kiểu và ngữ nghĩa
    |
    v
Mô hình đã liên kết
~~~

Thứ tự chính xác có thể khác. Một parser có thể đồng thời xây dựng bảng ký hiệu đối với ngôn ngữ đơn giản; một compiler khác tách hoàn toàn parsing và semantic analysis. Dù tổ chức thế nào, cần phân biệt việc nhận diện cú pháp với việc xác định một tên tham chiếu đến khai báo nào.

### 2.2. Phân giải tên và kiểm tra kiểu

Hai công việc này thường diễn ra gần nhau nhưng không đồng nghĩa:

- **Name resolution:** xác định tên nào liên kết với khai báo nào.
- **Type checking:** xác định kiểu của ký hiệu và kiểm tra cách sử dụng có phù hợp hay không.

Ví dụ:

~~~text
property retryCount: Integer
retryCount = "many"
~~~

Nếu retryCount đã được phân giải thành thuộc tính có kiểu Integer, phép gán chuỗi many là lỗi kiểu. Nếu retryCount chưa được khai báo, lỗi xảy ra ở bước phân giải tên trước đó.

Bảng ký hiệu cung cấp thông tin để cả hai bước sử dụng, nhưng việc tra cứu tên thành công không có nghĩa biểu thức đã hợp lệ về kiểu.

## 3. Phạm vi (scope) và các bảng ký hiệu lồng nhau

Một DSL thường có nhiều phạm vi. Tên được khai báo trong một phạm vi có thể chỉ dùng được bên trong phạm vi đó, trong khi một số tên khác có thể truy cập từ nhiều nơi.

Ví dụ:

~~~text
entity Order {
  property id: OrderId

  operation calculateTotal {
    variable taxRate: Decimal
  }
}
~~~

Order có phạm vi ở cấp mô-đun. id thuộc phạm vi của entity Order. taxRate chỉ có thể được dùng trong operation calculateTotal, nếu DSL áp dụng quy tắc phạm vi lồng nhau thông thường.

Có thể hình dung cấu trúc:

~~~text
ModuleScope
  └── OrderScope
        └── calculateTotalScope
              └── taxRate
~~~

Mỗi phạm vi có thể có bảng ký hiệu riêng và một liên kết đến phạm vi cha.

### 3.1. Phạm vi toàn cục hoặc mô-đun

Phạm vi cấp cao nhất thường chứa các khai báo có thể được tham chiếu từ những phần khác trong cùng mô-đun:

- Entity và type.
- Query hoặc workflow được đặt tên.
- Hằng số.
- Hàm hoặc action được công bố.
- Namespace và import.

Ví dụ:

~~~text
constant DEFAULT_CURRENCY = "VND"

entity Customer { ... }
entity Order { ... }

workflow processOrder { ... }
~~~

Khi một query tham chiếu Order, resolver tra cứu trong phạm vi mô-đun hoặc phạm vi được nhập.

### 3.2. Phạm vi của kiểu hoặc entity

Một entity có thể tạo phạm vi chứa các thuộc tính và operation của nó:

~~~text
entity Customer {
  property id: CustomerId
  property name: String

  operation displayName {
    ...
  }
}
~~~

Tên id, name và displayName được tra cứu trong phạm vi Customer, tùy quy tắc truy cập của DSL.

Cần phân biệt thành viên của entity với tên ở cấp mô-đun. Một thuộc tính name trong Customer không tự động trở thành tên toàn cục có thể dùng ở mọi nơi.

### 3.3. Phạm vi khối và phạm vi cục bộ

Một workflow hoặc biểu thức có thể tạo phạm vi riêng cho biến, tham số và alias:

~~~text
workflow processOrder {
  step validate {
    variable isValid: Boolean
  }

  step charge {
    variable paymentId: PaymentId
  }
}
~~~

Nếu mỗi step là một scope riêng, isValid không thể được tham chiếu trực tiếp trong charge. Muốn truyền dữ liệu giữa các bước, DSL cần cú pháp output/input hoặc một cơ chế chia sẻ được định nghĩa rõ.

Phạm vi là quy tắc ngôn ngữ, không phải hệ quả tự động của cách thụt lề hoặc cách viết dấu ngoặc. Cần ghi rõ cấu trúc nào tạo scope mới.

### 3.4. Tra cứu từ phạm vi trong ra ngoài

Một quy tắc phổ biến là tra cứu tên trong phạm vi hiện tại trước, rồi lần lượt tìm ở phạm vi cha cho đến khi tìm thấy hoặc hết phạm vi.

Ví dụ:

~~~text
ModuleScope:
  timeout = 30

WorkflowScope:
  timeout = 10

StepScope:
  action = "send"
~~~

Trong StepScope:

- action được tìm thấy ở StepScope.
- timeout không có trong StepScope nên được tìm ở WorkflowScope; kết quả là 10.
- Nếu WorkflowScope không khai báo timeout, resolver tiếp tục tìm ở ModuleScope; kết quả là 30.

Quy tắc này thường được gọi là lexical scope lookup hoặc lexical name resolution khi phạm vi được xác định bởi cấu trúc văn bản.

## 4. Shadowing và khai báo trùng

Khi phạm vi lồng nhau, một tên trong phạm vi con có thể che khuất tên cùng tên ở phạm vi cha. Hiện tượng này được gọi là **shadowing**.

Ví dụ:

~~~text
constant timeout = 30

workflow processOrder {
  variable timeout = 10

  step send {
    use timeout
  }
}
~~~

Nếu DSL cho phép shadowing, timeout bên trong workflow tham chiếu đến biến cục bộ có giá trị 10. Hằng số cấp mô-đun có giá trị 30 vẫn tồn tại nhưng bị che khuất trong phạm vi đó.

### 4.1. Shadowing khác với khai báo trùng

- **Shadowing:** hai khai báo cùng tên nằm trong các phạm vi lồng nhau khác nhau; khai báo gần hơn được chọn theo quy tắc lookup.
- **Duplicate declaration:** hai khai báo cùng tên xuất hiện trong cùng một phạm vi mà DSL không cho phép.

Ví dụ khai báo trùng:

~~~text
entity Customer {
  property id: CustomerId
  property id: Integer
}
~~~

Nếu một entity không cho phép hai thuộc tính cùng tên, resolver hoặc declaration checker phải báo lỗi tại khai báo thứ hai.

Một DSL có thể cho phép overload hoặc nhiều namespace riêng, vì vậy “trùng tên” phải được xác định theo loại ký hiệu và không gian tên. Hai hàm cùng tên nhưng khác danh sách tham số có thể hợp lệ nếu ngôn ngữ hỗ trợ overload; hai thuộc tính cùng tên trong một entity thường không hợp lệ.

### 4.2. Có nên cho phép shadowing?

Shadowing có thể giúp đặt tên cục bộ tự nhiên hơn, nhưng cũng có thể làm người đọc khó biết một tên đang tham chiếu đến khai báo nào.

DSL có thể chọn một trong các chính sách:

- Cấm shadowing hoàn toàn.
- Cho phép shadowing giữa các scope lồng nhau.
- Chỉ cho phép shadowing với một số loại ký hiệu.
- Cho phép nhưng phát cảnh báo khi tên cục bộ che khuất tên quan trọng.

Dù chọn chính sách nào, thông báo lỗi và công cụ editor nên giúp người dùng xác định khai báo được tham chiếu.

## 5. Nội dung của một symbol record

Một bảng ký hiệu hữu ích cần lưu đủ thông tin để thực hiện các bước phân tích tiếp theo. Cấu trúc cụ thể nên phản ánh những khái niệm mà DSL hỗ trợ.

Ví dụ, một symbol record tổng quát:

~~~java
record Symbol(
    String name,
    SymbolKind kind,
    TypeRef type,
    Scope declaringScope,
    SourceLocation location,
    Visibility visibility
) {}
~~~

Các trường có thể được hiểu như sau:

| Trường | Vai trò |
| --- | --- |
| name | Tên khai báo |
| kind | Loại ký hiệu: entity, property, variable, function... |
| type | Kiểu dữ liệu hoặc kiểu trả về, nếu có |
| declaringScope | Phạm vi chứa khai báo |
| location | Vị trí nguồn để báo lỗi hoặc điều hướng |
| visibility | Quy tắc truy cập nếu DSL hỗ trợ |

Một số ký hiệu cần thêm metadata:

- Hàm: danh sách kiểu tham số, kiểu trả về, thông tin overload.
- Entity: danh sách thành viên, kiểu cha, khóa định danh.
- Property: multiplicity, default value, constraint, khả năng ghi.
- Action: quyền thực thi, schema tham số, tác động phụ.
- Alias: nguồn dữ liệu hoặc biểu thức được đặt tên.
- Module: namespace, đường dẫn nguồn và các import.

Không nên ép mọi metadata vào một bản ghi lớn với nhiều trường null. Có thể dùng kiểu symbol riêng theo từng loại hoặc một cấu trúc chung kết hợp dữ liệu chuyên biệt.

### 5.1. Loại ký hiệu (symbol kind)

Loại ký hiệu giúp resolver và checker biết một tên được phép xuất hiện ở vị trí nào.

| Loại ký hiệu | Có thể xuất hiện ở vị trí |
| --- | --- |
| Entity | Nguồn dữ liệu, kiểu tham chiếu, quan hệ |
| Property | Biểu thức truy cập thuộc tính |
| Type | Khai báo kiểu và chú thích kiểu |
| Function | Biểu thức gọi hàm |
| Workflow | Tham chiếu đến quy trình |
| Action | Bước thực thi hoặc lời gọi action |
| Variable | Biểu thức trong phạm vi khai báo |
| Constant | Biểu thức giá trị |

Nếu DSL gặp Customer ở vị trí yêu cầu một entity nhưng tra cứu được một function tên Customer, hệ thống cần báo sai loại ký hiệu thay vì coi như tên không tồn tại.

### 5.2. Vị trí khai báo

Lưu vị trí nguồn của khai báo giúp thông báo lỗi có ích:

~~~text
entity Customer {
  property id: CustomerId
  property id: Integer
}
~~~

Thông báo có thể chỉ ra dòng khai báo thứ hai là trùng và liên kết đến khai báo đầu tiên. Vị trí có thể gồm tệp, dòng, cột hoặc khoảng ký tự trong nguồn.

Khi DSL hỗ trợ nhiều tệp, vị trí nguồn còn giúp điều hướng từ một tham chiếu đến định nghĩa tương ứng.

## 6. Cấu trúc dữ liệu để triển khai bảng ký hiệu

Bảng ký hiệu có thể được triển khai bằng nhiều cấu trúc. Lựa chọn phụ thuộc kích thước mô hình, yêu cầu tra cứu, phạm vi và khả năng cập nhật.

### 6.1. Hash map

Một lựa chọn phổ biến là ánh xạ từ tên sang symbol bằng hash map:

~~~java
Map<String, Symbol> symbols = new HashMap<>();
~~~

Tra cứu trung bình thường có độ phức tạp gần O(1), phù hợp cho phần lớn DSL có tập tên tương đối lớn.

Ưu điểm:

- Cài đặt đơn giản.
- Tra cứu nhanh trong trường hợp thông thường.
- Dễ kiểm tra tên đã tồn tại trước khi khai báo mới.

Hạn chế:

- Không tự biểu diễn scope lồng nhau.
- Không lưu được nhiều ký hiệu cùng tên nếu không thiết kế thêm namespace hoặc overload set.
- Không tự cung cấp thứ tự ưu tiên tra cứu.

Vì vậy, hash map thường là thành phần bên trong một Scope thay vì toàn bộ giải pháp.

### 6.2. Stack các scope

Một cách triển khai đơn giản là giữ stack các bảng ký hiệu. Khi vào block, tạo scope mới và đẩy lên stack; khi rời block, loại scope đó ra.

~~~text
push ModuleScope
  declare Customer

  push EntityScope(Customer)
    declare id
    declare name
  pop EntityScope(Customer)

  push WorkflowScope
    declare orderId
  pop WorkflowScope
pop ModuleScope
~~~

Tra cứu bắt đầu ở scope trên cùng rồi đi xuống các scope bên dưới theo thứ tự gần đến xa.

Cách này phù hợp với parser một lượt và ngôn ngữ có phạm vi lồng nhau theo cấu trúc. Tuy nhiên, nếu cần phân giải tham chiếu đến khai báo xuất hiện phía sau hoặc cần giữ nhiều scope cho editor, có thể cần cấu trúc bền vững hơn.

### 6.3. Scope có liên kết đến scope cha

Một mô hình phổ biến là mỗi scope giữ một map cục bộ và một tham chiếu đến scope cha:

~~~text
Scope
  parent: Scope?
  symbols: Map<Name, Symbol>
~~~

Phương thức lookup:

1. Tìm tên trong map của scope hiện tại.
2. Nếu tìm thấy, trả về symbol.
3. Nếu không, gọi lookup trên scope cha.
4. Nếu không còn scope cha, báo không tìm thấy.

Cấu trúc này thể hiện rõ lexical scope và dễ tạo scope con độc lập.

### 6.4. Cây hoặc đồ thị namespace

Khi DSL hỗ trợ namespace, package hoặc module lồng nhau, có thể tổ chức các phạm vi thành cây:

~~~text
root
 ├── sales
 │    ├── Customer
 │    └── Order
 └── billing
      ├── Invoice
      └── Payment
~~~

Tên đầy đủ của một ký hiệu có thể là sales.Customer hoặc billing.Payment. Cấu trúc namespace giúp tránh xung đột tên giữa các mô-đun.

Một hệ thống có dependency giữa module có thể có đồ thị tham chiếu thay vì cây thuần túy. Khi đó, quy tắc import, visibility và phát hiện chu trình phụ thuộc cần được định nghĩa riêng.

## 7. Phân giải tên theo phạm vi

Một resolver cần có quy tắc xác định nơi bắt đầu tra cứu, thứ tự tra cứu và cách xử lý khi có nhiều kết quả.

### 7.1. Tra cứu tên đơn giản

Với tên không có qualifier, quy tắc phổ biến là tìm từ phạm vi gần nhất ra ngoài:

~~~text
Module
  constant region = "VN"

Workflow
  variable region = "APAC"

Step
  use region
~~~

Trong Step, region được phân giải thành biến của Workflow nếu không có khai báo cùng tên trong Step.

### 7.2. Tra cứu tên có qualifier

Một tên có qualifier chỉ rõ đường dẫn đến thành viên:

~~~text
Customer.address.city
sales.Order.status
~~~

Resolver có thể xử lý từng phần:

1. Phân giải Customer hoặc namespace sales.
2. Kiểm tra ký hiệu đó có cho phép truy cập thành viên hay không.
3. Tra cứu address hoặc Order.
4. Tiếp tục phân giải city hoặc status trong kiểu của thành phần trước.

Với Customer.address.city, nếu address có kiểu Address, bước tiếp theo tra cứu city trong phạm vi thành viên của Address.

Nếu một thành phần không tồn tại hoặc không phải loại có thành viên, báo lỗi tại đúng đoạn tham chiếu. Không nên chỉ trả về lỗi “không tìm thấy toàn bộ tên” vì điều đó làm khó xác định nguyên nhân.

### 7.3. Tên tương đối và tên đầy đủ

DSL có thể cho phép dùng tên tương đối trong namespace hiện tại và tên đầy đủ khi cần tránh mơ hồ.

Ví dụ:

~~~text
namespace sales {
  entity Customer { ... }
}

namespace support {
  entity Customer { ... }

  query allSalesCustomers {
    from sales.Customer
  }
}
~~~

Customer có thể mơ hồ trong namespace gốc hoặc trong một phạm vi nhập nhiều module. Tên đầy đủ sales.Customer chỉ rõ ký hiệu cần tham chiếu.

Cần quy định dấu phân cách namespace, quy tắc alias và việc tên đầy đủ có bỏ qua import hay không.

## 8. Import, namespace và visibility

DSL nhiều mô-đun cần cách sử dụng khai báo từ nơi khác. Bảng ký hiệu thường phối hợp với hệ thống import và namespace để phân giải tên xuyên tệp.

Ví dụ:

~~~text
import sales.Customer
import billing.Payment as PaymentRecord

workflow registerPayment {
  step verifyCustomer {
    action = sales.verifyCustomer
  }
}
~~~

Các câu lệnh trên là cú pháp giả định. Hệ thống cần xác định:

- Import một ký hiệu hay toàn bộ namespace.
- Alias được thêm vào scope nào.
- Import trùng tên được xử lý ra sao.
- Có import vòng giữa các module không.
- Ký hiệu có được export hoặc public không.
- Tên private có thể được tham chiếu từ module khác không.

### 8.1. Visibility

Visibility (phạm vi truy cập) quy định nơi một ký hiệu được phép sử dụng:

- Public: có thể được module khác truy cập nếu đã import.
- Internal hoặc module-private: chỉ dùng trong module.
- Private: chỉ dùng trong phạm vi khai báo hoặc kiểu chứa nó.
- Protected: có thể dùng trong một phạm vi kế thừa nếu DSL hỗ trợ.

Không phải DSL nào cũng cần mọi mức visibility. Nếu DSL mô tả cấu hình đơn giản, có thể chỉ cần phạm vi mô-đun và phạm vi khối.

Resolver cần phân biệt ký hiệu tồn tại nhưng không truy cập được với ký hiệu hoàn toàn không tồn tại. Thông báo phù hợp giúp người dùng biết cần export hoặc import thay vì đổi tên.

### 8.2. Alias và xung đột import

Giả sử hai module đều có entity Customer:

~~~text
import retail.Customer
import crm.Customer
~~~

Nếu DSL đưa cả hai vào cùng namespace, tên Customer trở nên mơ hồ. Có thể yêu cầu tên đầy đủ hoặc alias:

~~~text
import retail.Customer as RetailCustomer
import crm.Customer as CRMCustomer
~~~

Khi đó, bảng ký hiệu trong scope hiện tại có thể chứa RetailCustomer và CRMCustomer, mỗi tên liên kết đến symbol gốc tương ứng.

Alias thường không tạo một khai báo miền mới. Nó tạo một tên bổ sung trỏ đến ký hiệu đã có. Cần giữ được danh tính gốc để báo lỗi và điều hướng đến đúng định nghĩa.

## 9. Forward reference và nhiều lượt phân tích

Một câu hỏi quan trọng là DSL có cho phép tham chiếu đến khai báo xuất hiện phía sau hay không.

Ví dụ:

~~~text
relation places {
  from Customer
  to Order
}

entity Customer { ... }
entity Order { ... }
~~~

Nếu DSL cho phép forward reference, resolver không thể chỉ tra cứu các khai báo đã gặp trước đó trong một lượt đơn giản. Có thể dùng quy trình nhiều lượt.

### 9.1. Hai lượt cơ bản

**Lượt 1 — Thu thập khai báo:** duyệt các khai báo cấp cao nhất, tạo symbol cho entity, type, workflow và module. Chưa cần phân giải toàn bộ tham chiếu thành viên.

**Lượt 2 — Phân giải và kiểm tra:** xử lý các tham chiếu trong quan hệ, thuộc tính, biểu thức và thân workflow bằng bảng ký hiệu đã có.

Luồng:

~~~text
Source files
    |
    v
Parse AST
    |
    v
Pass 1: Collect declarations
    |
    v
Module / scope symbol tables
    |
    v
Pass 2: Resolve references
    |
    v
Type checking and validation
~~~

Cách này hỗ trợ forward reference và giúp phát hiện khai báo trùng trước khi kiểm tra các tham chiếu.

### 9.2. Chu trình phụ thuộc

Nếu các khai báo tham chiếu lẫn nhau, chẳng hạn hai kiểu có quan hệ qua lại, DSL cần quyết định chu trình nào được phép.

Ví dụ:

~~~text
entity Employee {
  property manager: Employee?
}

entity Department {
  property head: Employee
}
~~~

Đây có thể là các tham chiếu hợp lệ vì kiểu đã được thu thập trước. Nhưng nếu giá trị mặc định hoặc biểu thức khởi tạo của hai thuộc tính phụ thuộc vòng nhau, runtime có thể không đánh giá được.

Cần phân biệt chu trình tham chiếu kiểu với chu trình phụ thuộc tính toán. Bảng ký hiệu giúp nhận diện các liên kết; bước kiểm tra đồ thị phụ thuộc xác định chu trình nào hợp lệ.

## 10. Overloading và nhiều ký hiệu cùng tên

Một số DSL cho phép nhiều hàm hoặc action cùng tên nhưng khác chữ ký. Đây là overloading.

Ví dụ:

~~~text
function format(value: Date): String
function format(value: Decimal): String
~~~

Một bảng ký hiệu đơn giản ánh xạ tên format đến đúng một symbol sẽ không đủ. Thay vào đó, symbol table có thể lưu một overload set gồm nhiều hàm.

Khi gặp lời gọi:

~~~text
format(order.total)
~~~

resolver trước tiên tìm tập hàm format, sau đó dùng kiểu của đối số để chọn overload phù hợp. Đây là quá trình phân giải overload, có thể kết hợp với type inference và type checking.

Cần định nghĩa:

- Hai hàm được xem là khác nhau dựa trên tên, số lượng tham số hay kiểu tham số?
- Có hỗ trợ tham số mặc định hoặc tham số có tên không?
- Có chuyển kiểu ngầm định không?
- Nếu nhiều overload cùng phù hợp, chọn theo quy tắc nào?
- Nếu không có overload phù hợp, thông báo lỗi cần liệt kê những chữ ký nào?

Không nên nhầm overload với shadowing. Overload thường là nhiều khai báo hợp lệ trong cùng một tập tên; shadowing là khai báo trong scope gần hơn che khuất khai báo ở scope ngoài.

## 11. Ví dụ triển khai bảng ký hiệu với Java

Một cách triển khai đơn giản là tạo lớp Scope chứa map cục bộ và tham chiếu đến scope cha.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

record Symbol(String name, String kind, String type) {}

final class Scope {
    private final Scope parent;
    private final Map<String, Symbol> symbols = new HashMap<>();

    Scope(Scope parent) {
        this.parent = parent;
    }

    boolean define(Symbol symbol) {
        if (symbols.containsKey(symbol.name())) {
            return false;
        }
        symbols.put(symbol.name(), symbol);
        return true;
    }

    Optional<Symbol> lookup(String name) {
        Symbol local = symbols.get(name);

        if (local != null) {
            return Optional.of(local);
        }

        if (parent != null) {
            return parent.lookup(name);
        }

        return Optional.empty();
    }
}
~~~

Ví dụ sử dụng:

~~~java
Scope moduleScope = new Scope(null);
moduleScope.define(new Symbol("Customer", "ENTITY", "Customer"));

Scope queryScope = new Scope(moduleScope);
queryScope.define(new Symbol("customer", "ALIAS", "Customer"));

Optional<Symbol> result = queryScope.lookup("Customer");
~~~

lookup("Customer") không tìm thấy tên trong queryScope, nên tiếp tục tra cứu ở moduleScope và nhận symbol của entity Customer.

Đây là ví dụ nền tảng. Một triển khai thực tế cần bổ sung source location, namespace, visibility, loại ký hiệu có kiểu cụ thể, overload, import và thông báo khai báo trùng. Ngoài ra, tên có thể cần được chuẩn hóa theo quy tắc phân biệt hoa thường của DSL.

### 11.1. Phát hiện khai báo trùng

Phương thức define ở trên chỉ kiểm tra map cục bộ. Đây thường là hành vi mong muốn nếu DSL cho phép một scope con che khuất scope cha.

Nếu DSL cấm shadowing, trước khi thêm ký hiệu mới cần tra cứu cả chuỗi scope cha. Nếu tìm thấy tên đã tồn tại, hệ thống có thể từ chối khai báo hoặc phát cảnh báo theo chính sách.

Cần giữ vị trí khai báo đầu tiên để thông báo có thể chỉ ra cả hai nơi:

~~~text
Duplicate property 'id'.
First declared at Customer.dsl:4:12.
Declared again at Customer.dsl:7:12.
~~~

### 11.2. Không dùng chuỗi làm danh tính lâu dài

Ví dụ trên dùng tên làm khóa tra cứu cho dễ hiểu. Trong compiler lớn hơn, nên tạo Symbol ID hoặc giữ object reference đến symbol đã phân giải. Điều này giúp xử lý đổi tên, nhiều module, overload và các tên trùng ở scope khác nhau.

Sau khi resolver liên kết một node AST với symbol, các bước sau nên sử dụng liên kết đó thay vì tra cứu lại bằng chuỗi.

## 12. Bảng ký hiệu trong DSL mô hình miền

Đối với DSL mô hình miền, bảng ký hiệu thường cần hỗ trợ nhiều loại khai báo và quan hệ giữa chúng.

Ví dụ:

~~~text
entity Customer {
  property id: CustomerId
  property name: String
}

entity Order {
  property id: OrderId
  property customer: Customer
  property total: Decimal
}

relation places {
  from Customer [1]
  to Order [0..*]
}
~~~

Bảng ký hiệu có thể tổ chức theo các phạm vi:

- Module scope chứa Customer, Order và places.
- Customer scope chứa id và name.
- Order scope chứa id, customer và total.
- Relation scope hoặc record quan hệ chứa hai đầu from và to.

Khi kiểm tra property customer: Customer, resolver tìm Customer trong type namespace. Khi kiểm tra quan hệ places, resolver xác nhận hai đầu trỏ đến entity hợp lệ và multiplicity đúng cú pháp.

### 12.1. Namespace theo loại ký hiệu

Một DSL có thể có namespace riêng cho kiểu, biến và action. Khi đó cùng tên có thể xuất hiện ở nhiều namespace:

~~~text
entity Report { ... }
function Report() { ... }
~~~

Có hợp lệ hay không phụ thuộc quy tắc ngôn ngữ. Nếu tách namespace, lookup cần biết vị trí đang yêu cầu loại ký hiệu nào:

- Type lookup tìm entity hoặc type.
- Value lookup tìm biến, constant hoặc property.
- Callable lookup tìm function hoặc action.

Cách này có thể giảm xung đột, nhưng tăng độ phức tạp. Chỉ nên dùng khi có nhu cầu rõ ràng và tài liệu hóa cách phân giải.

### 12.2. Alias trong truy vấn

Một truy vấn có thể đặt alias cho nguồn dữ liệu:

~~~text
query orderCustomers {
  from Order as o
  join Customer as c on o.customerId == c.id
  select c.name, o.total
}
~~~

Trong phạm vi truy vấn, o và c là các alias. Symbol table cần liên kết chúng với nguồn dữ liệu tương ứng và kiểu của nguồn. Khi phân giải o.total, resolver tra cứu total trong kiểu Order; khi phân giải c.name, resolver tra cứu name trong kiểu Customer.

Nếu hai alias trùng tên trong cùng scope, hệ thống phải báo lỗi. Nếu alias nằm trong các subquery có scope riêng, tên có thể được che khuất theo quy tắc đã định nghĩa.

## 13. Chẩn đoán lỗi từ bảng ký hiệu

Bảng ký hiệu hỗ trợ tạo ra nhiều loại chẩn đoán ngữ nghĩa.

### 13.1. Tên chưa được khai báo

~~~text
query orders {
  from Order
  select customerName
}
~~~

Nếu customerName không tồn tại trong scope truy vấn, resolver báo tên không được khai báo hoặc thuộc tính không tồn tại trong kiểu nguồn.

### 13.2. Khai báo trùng

~~~text
entity Customer {
  property id: CustomerId
  property id: Integer
}
~~~

Resolver phát hiện id đã có trong cùng scope và báo vị trí của khai báo đầu tiên.

### 13.3. Sai loại ký hiệu

~~~text
function calculateTotal() { ... }

entity Order {
  property customer: calculateTotal
}
~~~

Nếu vị trí kiểu yêu cầu một Type nhưng tên được phân giải thành Function, hệ thống nên báo sai loại ký hiệu. Đây không phải trường hợp đơn giản là tên không tồn tại.

### 13.4. Không đủ quyền truy cập

Nếu một property là private nhưng được tham chiếu từ module khác, resolver có thể tìm thấy symbol nhưng từ chối truy cập. Thông báo nên nói rõ tên tồn tại nhưng không khả dụng trong phạm vi hiện tại.

### 13.5. Tên mơ hồ

Nếu hai import đưa vào cùng một tên Customer, resolver có thể tìm thấy nhiều ứng viên. Hệ thống cần báo mơ hồ và gợi ý tên đầy đủ hoặc alias.

Thông báo lỗi hữu ích nên chứa vị trí tham chiếu, tên đã tra cứu, phạm vi đang xét và các khai báo liên quan khi có thể.

## 14. Bảng ký hiệu và công cụ IDE

Bảng ký hiệu không chỉ hữu ích khi biên dịch. Editor và Language Server có thể dùng cùng thông tin để cung cấp trải nghiệm hỗ trợ người viết DSL.

Một số tính năng:

- **Go to definition:** từ một tham chiếu, điều hướng đến khai báo được resolver liên kết.
- **Find references:** tìm mọi nơi đang tham chiếu một symbol.
- **Rename:** đổi tên khai báo và cập nhật các tham chiếu đúng symbol.
- **Autocomplete:** gợi ý tên có thể truy cập trong scope hiện tại.
- **Hover information:** hiển thị loại, kiểu và tài liệu của symbol.
- **Diagnostics:** gạch chân tên chưa khai báo, trùng tên hoặc không đủ quyền.
- **Refactoring:** di chuyển khai báo, đổi namespace hoặc trích xuất thành module.

Để hỗ trợ những tính năng này, hệ thống cần giữ vị trí nguồn và liên kết AST-to-symbol. Nếu chỉ lưu tên dưới dạng chuỗi mà không giữ danh tính và nguồn gốc, thao tác rename có thể sửa nhầm các tên trùng ở phạm vi khác.

### 14.1. Cập nhật gia tăng

Trong editor, người dùng có thể sửa một dòng trong tệp lớn. Phân tích lại toàn bộ dự án sau mỗi ký tự có thể tốn kém.

Một hệ thống phân tích gia tăng (incremental analysis) có thể:

1. Xác định module hoặc phạm vi bị ảnh hưởng.
2. Cập nhật các khai báo thay đổi trong bảng ký hiệu.
3. Tái phân giải những tham chiếu phụ thuộc.
4. Giữ lại kết quả phân tích không bị ảnh hưởng.
5. Cập nhật diagnostics và gợi ý trong editor.

Đây là yêu cầu nâng cao; DSL nhỏ chạy theo batch có thể không cần tối ưu này. Tuy nhiên, thiết kế symbol identity và dependency ngay từ đầu sẽ giúp mở rộng công cụ về sau.

## 15. Những vấn đề cần chú ý khi thiết kế bảng ký hiệu

**Phân biệt scope với namespace.** Scope quy định nơi một tên có hiệu lực; namespace tổ chức và định danh nhóm tên. Chúng có thể liên quan nhưng không nhất thiết là một khái niệm.

**Không đồng nhất tên với symbol.** Hai khai báo có thể cùng tên trong hai scope khác nhau. Mỗi khai báo cần danh tính riêng.

**Xác định rõ quy tắc shadowing.** Nếu không có quy tắc, resolver có thể chọn một khai báo không như người dùng mong đợi.

**Xử lý forward reference có chủ đích.** Nếu cho phép tham chiếu phía trước, cần thu thập khai báo trước khi phân giải tham chiếu hoặc dùng cơ chế trì hoãn phù hợp.

**Phân biệt tên không tồn tại với tên không truy cập được.** Hai lỗi có nguyên nhân và cách sửa khác nhau.

**Xử lý overload riêng.** Một tên có thể ánh xạ đến một nhóm callable thay vì một symbol đơn.

**Giữ source location.** Thông tin vị trí giúp báo lỗi, điều hướng và refactoring.

**Không để thứ tự duyệt tệp quyết định ngữ nghĩa ngoài đặc tả.** Nếu nhiều module khai báo cùng tên, quy tắc import và namespace phải xác định kết quả một cách ổn định.

**Giới hạn phạm vi lookup.** Không nên tìm kiếm toàn bộ mọi symbol khi DSL yêu cầu tên chỉ có hiệu lực trong một scope. Lookup quá rộng có thể vô tình cho phép tham chiếu ngoài ý muốn.

## 16. Quy trình xây dựng và sử dụng bảng ký hiệu

Khi triển khai name resolution cho DSL, có thể thực hiện theo trình tự sau:

### Bước 1: Xác định các loại khai báo

Liệt kê entity, type, property, variable, function, action, workflow, alias và các loại tên khác mà DSL hỗ trợ.

### Bước 2: Xác định quy tắc phạm vi

Quyết định cấu trúc nào tạo scope mới, phạm vi nào lồng nhau, khai báo nào được export và cách import hoạt động.

### Bước 3: Thiết kế bản ghi symbol

Chọn thông tin cần lưu như tên, loại, kiểu, vị trí khai báo, phạm vi và metadata riêng của từng loại ký hiệu.

### Bước 4: Chọn cấu trúc lưu trữ

Dùng map cho lookup cục bộ; kết hợp scope cha, stack hoặc namespace tree tùy yêu cầu. Nếu cần overload, lưu tập ứng viên cho cùng một tên.

### Bước 5: Thu thập khai báo

Duyệt AST, tạo symbol và phát hiện khai báo trùng trong phạm vi. Nếu hỗ trợ forward reference, thu thập đủ khai báo trước khi phân giải tham chiếu.

### Bước 6: Phân giải tham chiếu

Với mỗi identifier trong vị trí tham chiếu, tra cứu theo quy tắc scope, namespace, import và visibility. Gắn tham chiếu AST với symbol đã tìm được.

### Bước 7: Kiểm tra loại và kiểu

Xác minh symbol phù hợp với vị trí sử dụng; sau đó kiểm tra kiểu, tham số, quan hệ và ràng buộc miền.

### Bước 8: Báo lỗi và lưu liên kết

Giữ vị trí nguồn, thông tin khai báo và ứng viên liên quan để tạo diagnostics có thể hành động. Lưu liên kết symbol cho các bước sinh mã, thực thi và công cụ IDE.

## 17. Ví dụ tổng hợp: phân giải tên trong DSL đơn hàng

Xét DSL:

~~~text
namespace sales {
  entity Customer {
    property id: CustomerId
    property name: String
  }

  entity Order {
    property id: OrderId
    property customer: Customer
    property total: Decimal
  }

  workflow createOrder {
    variable currency: String

    step validate {
      action = validateCustomer
    }

    step calculate {
      variable taxRate: Decimal
      action = calculateTotal
    }
  }
}
~~~

Khi xây dựng bảng ký hiệu, có thể có các scope:

~~~text
RootScope
  └── sales
       ├── Customer
       │    ├── id
       │    └── name
       ├── Order
       │    ├── id
       │    ├── customer
       │    └── total
       └── createOrder
            ├── currency
            ├── validate
            └── calculate
                 └── taxRate
~~~

Khi phân giải Customer trong kiểu của Order.customer, resolver tra cứu trong namespace sales và tìm entity Customer.

Khi xử lý taxRate trong step calculate, tên chỉ được tìm thấy trong scope của step đó. Nếu step validate tham chiếu taxRate, resolver không tìm thấy nó trong phạm vi hợp lệ, trừ khi DSL định nghĩa một cơ chế truyền dữ liệu riêng.

Nếu hai entity cùng namespace đều khai báo id, điều đó hợp lệ vì mỗi id thuộc một entity scope riêng. Nếu Order khai báo property id hai lần, đó là duplicate declaration trong cùng scope và cần báo lỗi.

Nếu một action validateCustomer được import từ module khác, resolver cần xác minh import đã tạo alias hoặc đưa action đó vào phạm vi truy cập. Nếu tên tồn tại nhưng action không được export, lỗi là visibility chứ không phải tên chưa khai báo.

Ví dụ này cho thấy bảng ký hiệu kết nối tên với cấu trúc mô hình miền, hỗ trợ kiểm tra quan hệ và giữ ranh giới giữa các phạm vi.

## 18. Kết luận

Bảng ký hiệu là cấu trúc lưu thông tin về các khai báo để hệ thống phân giải tên và kiểm tra ngữ nghĩa của DSL. Nó thường lưu tên, loại ký hiệu, kiểu, phạm vi, vị trí khai báo và metadata cần thiết cho các bước sau.

Một bảng ký hiệu hữu ích phải làm việc cùng mô hình scope, namespace, import và quy tắc visibility. Với phạm vi lồng nhau, resolver thường tra cứu từ scope gần nhất ra ngoài; với forward reference, có thể cần thu thập khai báo trước rồi mới phân giải tham chiếu. Shadowing, khai báo trùng, overload và tên mơ hồ cần được xử lý theo quy tắc được đặc tả rõ ràng.

Khi thiết kế DSL, hãy bắt đầu từ các loại tên mà ngôn ngữ hỗ trợ và xác định chính xác nơi mỗi tên có hiệu lực. Sau đó chọn cấu trúc lưu trữ phù hợp, giữ liên kết giữa AST và symbol, đồng thời cung cấp thông báo lỗi có vị trí và nguyên nhân. Bảng ký hiệu được thiết kế tốt giúp parser, bộ kiểm tra kiểu, runtime và công cụ IDE cùng hiểu một tên theo một ý nghĩa nhất quán.

