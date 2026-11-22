# Tham chiếu và containment

## Vai trò của quan hệ trong mô hình trừu tượng

Một ngôn ngữ chuyên miền (domain-specific language, DSL) không chỉ có từ khóa và quy tắc cú pháp. Để phân tích, kiểm tra và thực thi chương trình, hệ thống thường chuyển văn bản nguồn thành một mô hình trừu tượng gồm các đối tượng có cấu trúc và các quan hệ giữa chúng. Mô hình này có thể là Abstract Syntax Tree (AST), mô hình miền, mô hình đối tượng hoặc một dạng biểu diễn trung gian.

Khi xây dựng mô hình, hai loại quan hệ xuất hiện thường xuyên là **containment** và **reference**:

- **Containment (quan hệ chứa hoặc sở hữu)** biểu thị một phần tử là thành phần cấu trúc của một phần tử khác. Phần tử chứa quản lý cấu trúc và thường quản lý vòng đời của phần tử được chứa.
- **Reference (quan hệ tham chiếu)** biểu thị một phần tử liên kết đến một phần tử khác có danh tính trong mô hình. Tham chiếu tạo kết nối giữa các phần tử nhưng không nhất thiết sở hữu hoặc quản lý vòng đời của phần tử đích.

Hai quan hệ này có thể cùng xuất hiện trong một mô hình. Chẳng hạn, một module chứa các khai báo rule; một biểu thức điều kiện chứa các node toán tử và literal; một lời gọi hàm chứa danh sách đối số nhưng tham chiếu đến khai báo hàm được định nghĩa ở nơi khác.

Phân biệt đúng containment và reference rất quan trọng. Nó ảnh hưởng đến cách xây AST, quản lý danh tính, điều hướng mô hình, kiểm tra tính hợp lệ, tuần tự hóa, tải và lưu tài nguyên, phát hiện chu trình, tái sử dụng thành phần và tạo thông báo lỗi.

## Containment là gì?

Containment là quan hệ cấu trúc trong đó một phần tử đóng vai trò container và một hoặc nhiều phần tử khác là nội dung của nó. Phần tử con tồn tại như một phần của cấu trúc cha trong mô hình.

Ví dụ trong một AST:

    Rule
      condition
        AndExpression
          GreaterThanExpression
            PropertyAccess(order.total)
            NumberLiteral(1000000)
          IsExpression
            PropertyAccess(customer.segment)
            StringLiteral("VIP")
      action
        Assignment
          PropertyAccess(shipment.fee)
          NumberLiteral(0)

Trong mô hình này, node Rule chứa node điều kiện và hành động. AndExpression chứa hai biểu thức con. GreaterThanExpression chứa toán hạng trái và phải. Các node con là thành phần cấu trúc của biểu thức cha.

Một quan hệ containment thường có các đặc điểm:

- Phần tử con thuộc về một container xác định trong mô hình.
- Container chịu trách nhiệm tổ chức phần tử con trong cấu trúc của nó.
- Phần tử con thường không được chia sẻ trực tiếp bởi nhiều container.
- Khi container bị loại bỏ khỏi mô hình, phần tử con thường cũng bị loại bỏ khỏi cấu trúc đó.
- Có thể điều hướng từ container đến các phần tử con và thường có thể truy ngược từ con đến container.
- Cấu trúc containment thường tạo thành một cây hoặc một rừng cây, dù mô hình tổng thể có thể chứa thêm các reference tạo thành đồ thị.

Containment là một quan hệ về cấu trúc và quyền sở hữu trong mô hình. Nó không nhất thiết có nghĩa đối tượng con phải được cấp phát hoặc giải phóng bộ nhớ cùng thời điểm trong mọi ngôn ngữ lập trình. Ý nghĩa vòng đời cụ thể phụ thuộc framework và cách triển khai.

## Reference là gì?

Reference là liên kết từ một phần tử nguồn đến một phần tử đích. Phần tử nguồn lưu thông tin đủ để xác định hoặc tìm ra đích, nhưng không sở hữu đích theo nghĩa containment.

Ví dụ, một rule có thể gọi một hàm được khai báo trong module khác:

    Module "orders"
      FunctionDeclaration "calculateDiscount"

    Module "checkout"
      Rule "VIP discount"
        Action
          FunctionCall
            name: "calculateDiscount"
            targetReference: FunctionDeclaration "calculateDiscount"

FunctionCall thuộc containment của Action hoặc Rule. Nhưng tham chiếu từ FunctionCall đến FunctionDeclaration là reference. Khai báo hàm không trở thành con của lời gọi hàm; nó vẫn thuộc module nơi nó được định nghĩa.

Reference thường có các đặc điểm:

- Đích có thể nằm ở nơi khác trong cùng mô hình hoặc trong một tài nguyên khác.
- Nhiều phần tử nguồn có thể tham chiếu cùng một đích.
- Xóa phần tử nguồn không nhất thiết xóa đích.
- Di chuyển phần tử đích có thể không làm thay đổi danh tính của nó, nếu hệ thống dùng ID ổn định.
- Reference có thể tạo quan hệ nhiều-nhiều và chu trình trong đồ thị mô hình.
- Reference có thể cần được phân giải (resolve) trước khi dùng để kiểm tra kiểu hoặc thực thi.

Reference có thể được biểu diễn bằng con trỏ đối tượng, ID, URI, tên có namespace, khóa trong cơ sở dữ liệu hoặc một đối tượng proxy. Cách biểu diễn phụ thuộc yêu cầu lưu trữ, tải lười, phân tán và quản lý phiên bản.

## So sánh containment và reference

| Khía cạnh | Containment | Reference |
|---|---|---|
| Ý nghĩa | Quan hệ cấu trúc, chứa và sở hữu | Quan hệ liên kết đến phần tử khác |
| Vòng đời | Thường gắn với container | Độc lập với phần tử nguồn |
| Chia sẻ đích | Thông thường một phần tử con có một container | Nhiều nguồn có thể cùng tham chiếu một đích |
| Điều hướng | Từ cha đến con, thường có đường đi ngược | Từ nguồn đến đích; có thể có nhiều đường liên kết |
| Hình dạng mô hình | Tạo cấu trúc cây hoặc rừng cây | Tạo đồ thị liên kết |
| Xóa phần tử nguồn | Xóa container thường loại bỏ các phần tử con | Xóa nguồn không xóa đích |
| Di chuyển phần tử | Là thay đổi vị trí cấu trúc và container | Có thể giữ nguyên reference nếu danh tính đích ổn định |
| Tuần tự hóa | Thường ghi lồng nhau trong container | Thường ghi ID, URI hoặc khóa tham chiếu |
| Ví dụ DSL | Rule chứa condition và action | FunctionCall tham chiếu FunctionDeclaration |

Một cách ghi nhớ là: containment trả lời câu hỏi “phần tử này nằm trong cấu trúc nào và ai sở hữu nó?”, còn reference trả lời “phần tử này liên kết đến đối tượng nào?”.

Không nên chỉ dựa vào hình thức dữ liệu để phân loại. Một thuộc tính có kiểu đối tượng chưa chắc là containment; nó có thể là reference. Cần xác định ý nghĩa miền và vòng đời của quan hệ.

## Mô hình ví dụ cho DSL quy tắc

Giả sử DSL hỗ trợ module, rule, biểu thức, khai báo hàm và lời gọi hàm. Một mô hình trừu tượng có thể được tổ chức như sau:

    Model
      modules: Module[*]

    Module
      name: String
      declarations: Declaration[*]

    Rule extends Declaration
      name: String
      condition: Expression
      actions: Action[*]

    FunctionDeclaration extends Declaration
      name: String
      parameters: Parameter[*]
      body: Expression

    FunctionCall extends Expression
      arguments: Expression[*]
      target: FunctionDeclaration [reference]

Trong ví dụ:

- Model chứa các Module.
- Module chứa các Declaration.
- Rule chứa Expression điều kiện và các Action.
- FunctionDeclaration chứa Parameter và biểu thức thân hàm.
- FunctionCall chứa các biểu thức đối số.
- FunctionCall tham chiếu đến FunctionDeclaration.

Các quan hệ đầu tiên là containment. Quan hệ target từ FunctionCall đến FunctionDeclaration là reference.

Một mô hình như vậy giúp tách hai câu hỏi: “cấu trúc chương trình được tổ chức ra sao?” và “các phần tử trong chương trình liên kết với nhau như thế nào?”.

## Vì sao không thể biểu diễn mọi quan hệ bằng containment?

Nếu mọi liên kết đều được mô hình hóa thành containment, một phần tử sẽ bị sao chép hoặc bị đặt sai vị trí cấu trúc khi được dùng ở nhiều nơi.

Giả sử hai rule cùng gọi một hàm:

    Module "shared"
      FunctionDeclaration "isEligible"

    Module "sales"
      Rule "Discount"
        FunctionCall "isEligible"

    Module "shipping"
      Rule "Free shipping"
        FunctionCall "isEligible"

FunctionDeclaration chỉ nên được khai báo một lần trong module shared. Hai FunctionCall có thể tham chiếu đến cùng khai báo đó. Nếu coi khai báo hàm là containment của từng lời gọi, mô hình phải tạo bản sao của FunctionDeclaration dưới mỗi FunctionCall. Khi sửa hàm, các bản sao có thể lệch nhau; danh tính của khai báo cũng bị mất.

Reference giải quyết vấn đề này bằng cách giữ một đích dùng chung. Nó cho phép nhiều nguồn liên kết đến một đối tượng duy nhất mà không thay đổi quyền sở hữu cấu trúc.

## Vì sao không thể biểu diễn mọi quan hệ bằng reference?

Nếu mọi quan hệ đều là reference, mô hình sẽ mất cấu trúc sở hữu rõ ràng. Các node AST có thể tồn tại rời rạc, khó xác định một phần tử thuộc rule, biểu thức hay module nào.

Ví dụ, nếu Rule chỉ tham chiếu đến condition và action mà không chứa chúng, hệ thống phải tìm một nơi khác để quản lý vòng đời và vị trí của các node đó. Việc xóa rule, sao chép rule hoặc tuần tự hóa rule trở nên phức tạp vì không có quan hệ cấu trúc rõ.

Containment cho biết thành phần nào tạo nên một đối tượng lớn hơn. Nó hỗ trợ duyệt cây, sao chép nhánh, xóa nhánh, định dạng và tuần tự hóa cấu trúc theo cách tự nhiên.

Do đó, mô hình thường dùng containment cho cấu trúc sở hữu và reference cho liên kết giữa các cấu trúc độc lập.

## Quan hệ một-một, một-nhiều và nhiều-nhiều

Containment và reference đều có thể có bội số (multiplicity) khác nhau. Bội số mô tả số lượng phần tử có thể tham gia vào một quan hệ.

Một số ký hiệu thường gặp:

| Ký hiệu | Ý nghĩa |
|---|---|
| 1 | Chính xác một |
| 0..1 | Không hoặc một |
| 0..* | Không hoặc nhiều |
| 1..* | Ít nhất một |
| m..n | Từ m đến n phần tử |

Ví dụ:

    Rule
      condition: Expression [1]
      actions: Action [1..*]
      parentGroup: RuleGroup [0..1 reference]

Một Rule phải có đúng một condition, có ít nhất một action và có thể tham chiếu đến một RuleGroup. Quan hệ condition và actions là containment; parentGroup là reference nếu RuleGroup quản lý rule theo một cấu trúc độc lập.

Bội số phải được xác định theo nghiệp vụ. Nếu một rule có thể không có action trong lúc người dùng đang soạn thảo nhưng phải có action trước khi chạy, mô hình có thể cho phép trạng thái chưa hoàn chỉnh và semantic validation sẽ báo lỗi ở giai đoạn phù hợp. Không nên nhầm bội số trong mô hình chỉnh sửa với điều kiện hợp lệ khi thực thi.

## Quy tắc sở hữu và tính duy nhất của containment

Trong nhiều mô hình đối tượng, một phần tử chỉ có một container trực tiếp tại một thời điểm. Điều này giúp cấu trúc containment không có nhiều cha và giữ được một đường đi duy nhất từ gốc đến node.

Ví dụ, một NumberLiteral không nên đồng thời là con của hai biểu thức khác nhau nếu mô hình coi mỗi node AST là một vị trí cú pháp cụ thể. Nếu cùng một giá trị xuất hiện trong hai biểu thức, parser nên tạo hai node literal riêng hoặc dùng một đối tượng giá trị bất biến được chia sẻ theo một cơ chế khác.

Khi di chuyển node từ container này sang container khác, framework có thể tự động gỡ node khỏi container cũ hoặc từ chối thao tác. Cần quy định hành vi này để tránh một node xuất hiện hai lần trong cấu trúc.

Một số mô hình cho phép chia sẻ các đối tượng bất biến, chẳng hạn kiểu dữ liệu hoặc metadata. Những đối tượng đó thường được liên kết bằng reference thay vì containment. Việc chia sẻ cần được phân biệt với quyền sở hữu cấu trúc.

## Reference có thể tạo chu trình

Containment thường được thiết kế để tạo cây không chu trình. Reference thì có thể tạo chu trình vì các phần tử độc lập có thể liên kết lẫn nhau.

Ví dụ, hai khai báo hàm có thể tham chiếu qua lại:

    Function A
      calls -> Function B

    Function B
      calls -> Function A

Đây có thể là đệ quy hợp lệ nếu DSL cho phép. Một chu trình khác có thể là lỗi, chẳng hạn hai module import nhau trong khi ngữ nghĩa module không cho phép phụ thuộc vòng.

Vì reference có thể tạo đồ thị, các thuật toán xử lý cần lưu ý:

- Duyệt đồ thị cần tập hợp visited để tránh lặp vô hạn.
- Phát hiện chu trình cần thuật toán đồ thị phù hợp.
- Tuần tự hóa phải tránh mở rộng đệ quy vô hạn.
- Xóa đích cần xác định cách xử lý các reference đang trỏ đến nó.
- Phân giải reference cần xử lý trường hợp phụ thuộc chưa được tải.
- Trình bày mô hình cần tránh lặp lại toàn bộ đối tượng đích ở mọi vị trí tham chiếu.

Không phải chu trình nào cũng sai. Cần xác định chu trình nào được phép theo ngữ nghĩa DSL và chu trình nào phải báo lỗi.

## Reference theo tên, ID và URI

Một reference cần cách xác định đích. Có một số chiến lược phổ biến.

### Reference theo tên

Một phần tử nguồn lưu tên của phần tử đích:

    CALL calculateDiscount(order)

Ưu điểm là dễ đọc và gần với cú pháp DSL. Tuy nhiên, tên có thể trùng trong các module khác nhau, đổi tên có thể làm reference bị hỏng và việc phân giải cần biết scope hoặc namespace.

### Reference theo tên có namespace

Có thể thêm đường dẫn namespace để làm rõ đích:

    CALL shared.discount.calculateDiscount(order)

Cách này giảm mơ hồ nhưng phụ thuộc quy tắc namespace và import. Khi module được di chuyển hoặc đổi tên, reference có thể cần cập nhật.

### Reference theo ID ổn định

Mô hình có thể lưu ID duy nhất:

    targetId: "fn-7d2a..."

ID ổn định giúp đổi tên hoặc di chuyển phần tử mà không nhất thiết làm hỏng liên kết. Nhược điểm là ID không thân thiện khi đọc bằng mắt; công cụ thường cần hiển thị tên đã resolve thay cho ID.

### Reference theo URI hoặc đường dẫn tài nguyên

Khi mô hình được chia thành nhiều tệp hoặc tài nguyên, reference có thể dùng URI:

    targetURI: "project:/modules/shared.dsl#calculateDiscount"

URI cho phép tham chiếu xuyên tệp hoặc xuyên tài nguyên. Cần quy định cách phân giải URI, thư mục gốc, phiên bản tài nguyên, quyền truy cập và hành vi khi đích không tồn tại.

### Kết hợp tên và ID

Một mô hình có thể lưu ID làm định danh chính và tên làm thông tin hiển thị. Khi tải tài nguyên, hệ thống tìm đích bằng ID rồi kiểm tra tên hoặc metadata nếu cần. Cách này hỗ trợ đổi tên mà vẫn giữ được khả năng đọc và chẩn đoán.

## Phân giải reference (reference resolution)

Trong văn bản DSL, người dùng thường viết tên thay vì một con trỏ trực tiếp đến đối tượng trong bộ nhớ. Frontend cần phân giải tên đó thành phần tử đích trong mô hình.

Ví dụ:

    MODULE checkout

    RULE "VIP discount"
    WHEN customer.segment IS VIP
    THEN applyDiscount(order)

    MODULE shared

    FUNCTION applyDiscount(order)
      ...

Khi parser gặp applyDiscount, nó có thể tạo một node FunctionCall chứa tên chưa được phân giải. Semantic analyzer tìm khai báo phù hợp dựa trên scope, namespace và các module được import.

Quá trình phân giải thường gồm:

1. Xác định phạm vi hiện tại của tham chiếu.
2. Tìm các khai báo có tên phù hợp trong scope.
3. Áp dụng quy tắc namespace, import và visibility.
4. Kiểm tra overload hoặc kiểu tham số nếu có nhiều ứng viên.
5. Gắn reference đến đích nếu tìm được duy nhất một ứng viên.
6. Báo lỗi nếu không tìm thấy hoặc có nhiều ứng viên không phân biệt được.

Một reference chưa resolve có thể được giữ lại trong mô hình chỉnh sửa, chẳng hạn khi người dùng đang gõ dở hoặc module đích chưa tải. Trước khi thực thi hoặc triển khai, hệ thống thường phải xác nhận mọi reference bắt buộc đã được resolve.

## Reference tĩnh và reference động

**Reference tĩnh** được xác định trong quá trình phân tích hoặc biên dịch. Ví dụ, lời gọi hàm trong DSL được liên kết với một FunctionDeclaration cụ thể. Việc kiểm tra chữ ký và kiểu có thể thực hiện trước khi chạy.

**Reference động** được xác định khi thực thi dựa trên dữ liệu hoặc môi trường hiện tại. Ví dụ, tên workflow được lấy từ cấu hình runtime rồi tra cứu trong registry.

Reference tĩnh hỗ trợ kiểm tra sớm và điều hướng mã nguồn tốt hơn. Reference động linh hoạt khi hệ thống cần chọn đối tượng theo dữ liệu, nhưng lỗi thiếu đích có thể chỉ xuất hiện lúc chạy.

Một DSL có thể kết hợp cả hai. Ví dụ, tên hàm được resolve tĩnh, còn một resource key được tra cứu động từ môi trường triển khai. Đặc tả cần chỉ rõ reference nào phải resolve ở giai đoạn nào.

## Scope và namespace ảnh hưởng đến reference

Reference theo tên chỉ có thể được resolve đúng khi ngôn ngữ định nghĩa rõ phạm vi tên.

Các mô hình scope thường gặp:

- Global scope: tên có thể được nhìn thấy từ toàn bộ chương trình.
- Module scope: tên chỉ được nhìn thấy trong module hoặc qua import.
- Rule scope: biến và alias chỉ có hiệu lực trong một rule.
- Block scope: tên được khai báo trong một khối chỉ có hiệu lực trong khối đó và các khối con theo quy tắc.
- Local scope: tham số và biến cục bộ trong một biểu thức hoặc hàm.

Ví dụ:

    MODULE sales
      FUNCTION calculateTax(amount)
        ...

    MODULE checkout
      IMPORT sales

      RULE "Checkout"
      THEN sales.calculateTax(order.total)

Reference đến calculateTax có thể được resolve qua namespace sales nếu module checkout import hoặc có quyền truy cập module đó.

Nếu hai module cùng định nghĩa calculateTax, tên không có namespace có thể mơ hồ. DSL cần quy định cách ưu tiên: local trước imported, explicit namespace bắt buộc, hoặc báo lỗi khi có nhiều ứng viên.

Không nên để thứ tự tải tệp hoặc thứ tự duyệt danh sách quyết định reference được resolve đến đâu. Quy tắc scope phải ổn định và có thể dự đoán.

## Quan hệ containment và reference trong AST

AST thường sử dụng containment cho các node biểu diễn vị trí cú pháp. Mỗi node có thể chứa các node con theo cấu trúc của biểu thức hoặc câu lệnh.

Ví dụ:

    BinaryExpression
      operator: AND
      left
        ComparisonExpression
          left
            PropertyAccess(order.total)
          right
            NumberLiteral(1000000)
      right
        ComparisonExpression
          left
            PropertyAccess(customer.segment)
          right
            EnumLiteral(VIP)

Trong AST này, BinaryExpression chứa hai biểu thức con. PropertyAccess có thể chứa một chuỗi thành phần tên hoặc một node receiver. Những quan hệ đó là containment vì chúng tạo nên cấu trúc của biểu thức.

Tuy nhiên, khi PropertyAccess(customer.segment) được resolve đến thuộc tính segment của kiểu Customer, liên kết đến khai báo thuộc tính là reference. Node truy cập thuộc tính vẫn nằm ở vị trí cú pháp ban đầu; khai báo thuộc tính có thể được định nghĩa trong mô hình kiểu hoặc module khác.

Một node AST sau semantic analysis có thể chứa cả:

- Node con qua containment.
- Thông tin kiểu đã suy ra.
- Reference đến symbol hoặc declaration.
- Source span trỏ về văn bản gốc.
- Metadata phục vụ tối ưu hóa hoặc backend.

Cần tránh đặt reference và containment chung vào một danh sách con mà không phân biệt. Nếu traversal coi mọi reference là con, nó có thể đi ra ngoài cây AST và duyệt lặp nhiều lần qua các khai báo dùng chung.

## Mô hình miền và quan hệ giữa thực thể

Trong mô hình miền (domain model), containment và reference giúp thể hiện quan hệ giữa các khái niệm nghiệp vụ.

Ví dụ trong thương mại điện tử:

    Order
      lines: OrderLine[*] [containment]
      payment: Payment [reference]
      customer: Customer [reference]

    Customer
      id
      name

    Payment
      id
      amount

Order chứa các OrderLine vì dòng hàng là thành phần cấu trúc của đơn hàng. Order tham chiếu Customer và Payment vì khách hàng và khoản thanh toán có danh tính, vòng đời và khả năng được dùng bởi nhiều đối tượng khác.

Tuy nhiên, đây không phải quy tắc cố định cho mọi miền. Một hệ thống có thể coi Payment là thành phần sở hữu của Order nếu khoản thanh toán chỉ tồn tại trong phạm vi đơn hàng và không được quản lý độc lập. Một hệ thống kế toán có thể quản lý Payment như một thực thể độc lập, còn Order chỉ tham chiếu đến nó. Cần dựa vào ý nghĩa nghiệp vụ và vòng đời thực tế để chọn quan hệ.

### Aggregate và ranh giới sở hữu

Trong Domain-Driven Design, aggregate là một nhóm đối tượng được quản lý thông qua một aggregate root. Các đối tượng bên trong aggregate thường được truy cập qua root và tuân theo các invariant chung.

Containment có thể phù hợp để biểu diễn cấu trúc nội bộ của aggregate, nhưng containment không đồng nghĩa hoàn toàn với aggregate boundary. Một framework mô hình hóa có thể có quan hệ containment trong khi nghiệp vụ vẫn cần xác định ranh giới giao dịch và quyền cập nhật.

Ví dụ:

    Order (aggregate root)
      OrderLine[*] (owned parts)

    Customer (aggregate root)
      ...

    Order.customer -> Customer (reference)

Order sở hữu các OrderLine nhưng tham chiếu Customer. Thao tác cập nhật OrderLine có thể đi qua Order root để giữ các quy tắc nhất quán. Việc thay đổi Customer được quản lý trong ranh giới riêng.

## Xóa, di chuyển và sao chép phần tử

Các thao tác chỉnh sửa mô hình cần có quy tắc rõ cho cả hai loại quan hệ.

### Xóa container

Khi xóa một container, các phần tử containment thường bị xóa khỏi cấu trúc cùng với container. Ví dụ xóa Rule khỏi Module sẽ loại bỏ condition và action thuộc rule đó.

Nhưng các đối tượng được Rule tham chiếu, chẳng hạn FunctionDeclaration hoặc CustomerType, không bị xóa theo. Chúng có thể vẫn được dùng ở nơi khác.

Nếu xóa một phần tử đích đang có reference, hệ thống cần chính sách:

- Từ chối xóa khi còn reference bắt buộc.
- Cho phép xóa nhưng đánh dấu reference là unresolved.
- Tìm và cập nhật các nguồn tham chiếu.
- Thay thế đích bằng một phần tử khác tương thích.
- Giữ tombstone hoặc định danh đã xóa để phục vụ đồng bộ và chẩn đoán.

Lựa chọn phụ thuộc môi trường chỉnh sửa và yêu cầu dữ liệu. Trong công cụ IDE, cho phép trạng thái chưa hoàn chỉnh có thể hữu ích; trong pipeline triển khai, reference bắt buộc thường phải hợp lệ.

### Di chuyển phần tử

Di chuyển một node containment từ container này sang container khác thay đổi vị trí cấu trúc. Nếu reference đến node đó dựa trên ID ổn định, các liên kết có thể tiếp tục hợp lệ. Nếu reference dựa trên đường dẫn hoặc tên có namespace, việc di chuyển có thể yêu cầu resolve lại.

Một công cụ refactoring cần phân biệt đổi vị trí cấu trúc với đổi danh tính. Di chuyển một khai báo giữa các module có thể giữ ID nhưng làm thay đổi visibility và namespace.

### Sao chép phần tử

Sao chép một container thường tạo bản sao mới của các phần tử containment bên dưới. Các reference trong bản sao cần chính sách riêng:

- Giữ reference đến cùng các đích bên ngoài.
- Chuyển reference nội bộ sang bản sao tương ứng.
- Tạo bản sao độc lập của một số đích nếu ngữ nghĩa yêu cầu.
- Yêu cầu người dùng chọn cách xử lý khi có mơ hồ.

Ví dụ, sao chép một Rule có thể tạo condition và action mới nhưng vẫn tham chiếu đến cùng FunctionDeclaration. Nếu rule chứa một khai báo cục bộ được tham chiếu bởi node khác trong cùng rule, reference nội bộ nên được ánh xạ sang khai báo bản sao để tránh trỏ ngược về bản gốc.

## Tuần tự hóa mô hình

Tuần tự hóa (serialization) chuyển mô hình trong bộ nhớ thành dạng lưu trữ như JSON, XML, YAML hoặc định dạng nhị phân. Containment và reference thường được tuần tự hóa khác nhau.

### Tuần tự hóa containment

Containment có thể được ghi lồng nhau:

    {
      "type": "Rule",
      "name": "VIP discount",
      "condition": {
        "type": "Comparison",
        "operator": ">=",
        "left": {
          "type": "PropertyAccess",
          "name": "order.total"
        },
        "right": {
          "type": "NumberLiteral",
          "value": 1000000
        }
      }
    }

Cấu trúc lồng nhau thể hiện rõ cây sở hữu. Khi đọc lại, deserializer tạo các node con và gắn chúng vào container tương ứng.

### Tuần tự hóa reference

Reference thường được ghi dưới dạng ID hoặc URI thay vì mở rộng toàn bộ đối tượng đích:

    {
      "type": "FunctionCall",
      "name": "calculateDiscount",
      "targetId": "function-42"
    }

Deserializer cần một bước liên kết sau khi các đối tượng có danh tính đã được tạo. Nếu đích chưa được tải, reference có thể được giữ dưới dạng proxy hoặc unresolved handle.

### Tránh vòng lặp tuần tự hóa

Nếu serializer đi theo cả containment lẫn reference và mở rộng toàn bộ đối tượng đích, reference vòng có thể gây đệ quy vô hạn hoặc lặp dữ liệu. Một chiến lược phổ biến là:

1. Ghi cấu trúc containment lồng nhau.
2. Ghi danh tính ổn định cho các phần tử có thể được tham chiếu.
3. Ghi reference bằng ID/URI.
4. Khi đọc, tạo các đối tượng trước rồi resolve reference sau.

Cách này giúp tách cấu trúc sở hữu khỏi đồ thị liên kết.

## Tải lười và proxy reference

Với mô hình lớn được chia thành nhiều tài nguyên, không phải lúc nào cũng cần tải toàn bộ đích tham chiếu vào bộ nhớ. Hệ thống có thể dùng proxy chứa URI hoặc ID. Khi người dùng truy cập reference, hệ thống mới tải tài nguyên đích.

Lợi ích:

- Giảm lượng dữ liệu tải ban đầu.
- Hỗ trợ mô hình phân tán hoặc nhiều tệp.
- Cho phép duyệt một phần mô hình.
- Giữ ranh giới giữa tài nguyên và tránh nhân bản dữ liệu.

Các vấn đề cần xử lý:

- URI không tồn tại hoặc không truy cập được.
- Đích đã bị đổi tên hoặc di chuyển.
- Phiên bản tài nguyên không tương thích.
- Nhiều yêu cầu cùng tải một đích.
- Reference chưa resolve nhưng giao diện cần hiển thị.
- Quyền truy cập đích khác với quyền truy cập nguồn.

Proxy cần thể hiện trạng thái rõ ràng: chưa tải, đang tải, đã resolve hoặc lỗi. Không nên âm thầm trả về giá trị null cho mọi trường hợp vì null có thể mang ý nghĩa nghiệp vụ khác.

## Tích hợp với framework mô hình hóa

Một số framework mô hình hóa cung cấp khái niệm containment và reference trực tiếp. Ví dụ, trong Eclipse Modeling Framework (EMF), EReference có thể được đánh dấu containment để biểu thị quan hệ sở hữu; EReference thông thường biểu diễn liên kết. Framework có thể cung cấp container/opposite, notification, resource URI, proxy resolution và serialization thông qua XMI.

Khi dùng framework, cần hiểu đúng metadata của quan hệ:

- EReference nào có cờ containment.
- Bội số và tính tùy chọn của mỗi reference.
- Quan hệ ngược (opposite) có được khai báo không.
- Phần tử có container trực tiếp nào.
- Reference có được resolve tự động không.
- Resource nào sở hữu phần tử gốc.
- Xóa hoặc di chuyển phần tử tác động đến liên kết ra sao.

Không nên chỉ dựa vào tên thuộc tính để đoán framework xem đó là containment hay reference. Metadata mô hình mới là căn cứ.

Trong một mô hình tự xây bằng Java, các khái niệm này vẫn có thể được thể hiện bằng API rõ ràng, dù không dùng framework chuyên biệt:

    class Rule {
        private Expression condition;        // containment
        private List<Action> actions;        // containment
        private FunctionDeclaration target; // reference
    }

Đây là cách minh họa. Nếu cần hỗ trợ di chuyển, xóa, tuần tự hóa và truy vết, implementation có thể cần thêm parent/container link, stable ID, source span và cơ chế resolve reference.

## Điều hướng và truy vấn mô hình

Containment hỗ trợ duyệt cấu trúc theo chiều sâu hoặc chiều rộng. Reference hỗ trợ đi theo các liên kết ngữ nghĩa.

Ví dụ:

- Từ Model, duyệt containment để lấy tất cả Rule.
- Từ Rule, đi theo containment để lấy các biểu thức và action.
- Từ FunctionCall, đi theo reference để tìm FunctionDeclaration.
- Từ FunctionDeclaration, tìm các nguồn đang tham chiếu đến nó bằng một chỉ mục ngược (cross-reference index).

Hai kiểu traversal cần được tách biệt. Một hàm duyệt toàn bộ nội dung (all contents) có thể chỉ duyệt containment để trả về mọi phần tử thuộc cấu trúc. Một hàm duyệt mọi phần tử có thể tiếp cận (all reachable) có thể đi theo cả reference, nhưng phải xử lý visited set và chu trình.

Chỉ mục ngược có ích khi cần:

- Tìm mọi nơi sử dụng một khai báo.
- Cảnh báo khai báo không được tham chiếu.
- Ngăn xóa phần tử đang được dùng.
- Cập nhật reference khi đổi tên hoặc di chuyển.
- Hiển thị call hierarchy hoặc dependency graph.

Không nên tính chỉ mục ngược bằng cách quét toàn bộ mô hình ở mọi thao tác nếu mô hình lớn. Có thể xây và cập nhật index khi mô hình thay đổi.

## Ảnh hưởng đến refactoring và chỉnh sửa mô hình

Refactoring là thay đổi cấu trúc mà vẫn giữ ý nghĩa chương trình theo một mục tiêu đã xác định. Containment và reference cung cấp thông tin cần thiết để thực hiện refactoring an toàn.

### Đổi tên phần tử được tham chiếu

Nếu một FunctionDeclaration đổi tên, các FunctionCall tham chiếu đến nó cần được cập nhật khi cú pháp dùng tên. Nếu reference được lưu bằng ID, liên kết trong mô hình có thể không đổi nhưng văn bản nguồn vẫn cần được sinh lại hoặc cập nhật.

### Di chuyển khai báo

Di chuyển khai báo sang module khác có thể thay đổi scope và visibility. Công cụ cần resolve lại reference, thêm import hoặc báo lỗi nếu nguồn không còn quyền truy cập.

### Trích xuất biểu thức

Một biểu thức containment có thể được chuyển thành một FunctionDeclaration mới. Các vị trí sử dụng có thể được thay bằng FunctionCall reference đến khai báo vừa tạo. Thao tác này thay đổi cấu trúc containment và tạo reference mới.

### Xóa mã không dùng

Một khai báo không có reference ngược có thể là ứng viên xóa, nhưng không nên kết luận chỉ dựa trên số lượng reference. Một DSL có thể hỗ trợ entry point được gọi từ cấu hình ngoài, plugin hoặc hệ thống runtime. Công cụ cần tính đến các điểm vào động.

## Ràng buộc và kiểm tra tính hợp lệ

Mô hình nên định nghĩa invariant cho containment và reference.

Các invariant containment có thể gồm:

- Mỗi node con chỉ có tối đa một container trực tiếp.
- Không có chu trình containment.
- Node con có đúng loại mà thuộc tính container yêu cầu.
- Bội số của quan hệ được thỏa mãn khi mô hình ở trạng thái hoàn chỉnh.
- Node không bị gắn đồng thời vào hai vị trí trong cùng cây AST.

Các invariant reference có thể gồm:

- Reference bắt buộc phải resolve trước khi thực thi.
- Đích có đúng kiểu hoặc thuộc lớp tương thích.
- Đích nằm trong phạm vi truy cập được phép.
- Reference không trỏ đến tài nguyên đã xóa hoặc phiên bản không tương thích.
- Các chu trình reference tuân theo chính sách của DSL.
- Reference không tạo ra phụ thuộc module bị cấm.

Có thể chia kiểm tra thành các giai đoạn:

| Giai đoạn | Kiểm tra điển hình |
|---|---|
| Parse | Cấu trúc containment được tạo theo grammar |
| Model validation | Bội số, loại node và quy tắc container |
| Name resolution | Resolve tên và reference |
| Semantic validation | Kiểu, scope, visibility và invariant miền |
| Deployment/runtime | Reference bên ngoài, quyền, tài nguyên và trạng thái thực tế |

Một mô hình có thể tạm thời không hợp lệ trong lúc người dùng chỉnh sửa. Ví dụ, FunctionCall có tên nhưng chưa tìm thấy khai báo vì người dùng chưa hoàn tất tệp. IDE có thể hiển thị unresolved diagnostic mà vẫn giữ node để tiếp tục chỉnh sửa. Khi build hoặc triển khai, chính sách có thể yêu cầu mọi reference bắt buộc phải hợp lệ.

## Ví dụ xuyên suốt: module, rule và hàm dùng chung

Giả sử có ba module:

    MODULE common
      FUNCTION isVip(customer)
        ...

      FUNCTION calculateDiscount(order)
        ...

    MODULE sales
      IMPORT common

      RULE "VIP discount"
        WHEN common.isVip(customer)
        THEN common.calculateDiscount(order)

    MODULE shipping
      IMPORT common

      RULE "VIP shipping"
        WHEN common.isVip(customer)
        THEN shipment.setFee(0)

Containment:

- Model chứa ba Module.
- Module common chứa hai FunctionDeclaration.
- Module sales và shipping mỗi module chứa một Rule.
- Mỗi Rule chứa condition và action.
- FunctionCall chứa các đối số của lời gọi.

Reference:

- Module sales và shipping tham chiếu module common thông qua import.
- FunctionCall trong hai rule tham chiếu đến FunctionDeclaration tương ứng.
- Các tham chiếu đến kiểu Customer, Order hoặc Shipment có thể trỏ đến khai báo kiểu trong một module khác.

Khi xóa Rule VIP discount, các node condition, action và FunctionCall thuộc rule bị xóa theo containment. Các FunctionDeclaration trong common vẫn tồn tại vì chúng không thuộc rule. Rule VIP shipping tiếp tục sử dụng isVip và calculateDiscount nếu có reference đến chúng.

Nếu đổi tên calculateDiscount thành computeDiscount, hệ thống có thể cập nhật các reference và biểu thức nguồn. Nếu chuyển hàm sang module khác, hệ thống cần kiểm tra import và visibility. Ví dụ này cho thấy containment quản lý cấu trúc nội bộ, còn reference kết nối các phần độc lập của mô hình.

## Những lỗi thiết kế thường gặp

### Dùng containment cho đối tượng dùng chung

Khi một khai báo được nhiều phần tử sử dụng, đặt nó làm con của từng phần tử nguồn có thể tạo bản sao và làm mất danh tính. Hãy cân nhắc reference đến một khai báo có vòng đời độc lập.

### Dùng reference cho cấu trúc con thông thường

Nếu condition và action của Rule chỉ được tạo để thuộc Rule đó, dùng reference có thể khiến chúng bị rời khỏi cây cấu trúc. Hãy dùng containment để mô tả thành phần sở hữu.

### Không định nghĩa chính sách khi xóa đích

Xóa một khai báo đang được tham chiếu có thể để lại reference hỏng. Cần quy định từ chối, cập nhật, unresolved state hoặc thay thế.

### Đi theo reference trong mọi phép duyệt cây

Traversal không phân biệt containment và reference có thể lặp vô hạn khi gặp chu trình hoặc xử lý cùng một phần tử nhiều lần. Cần tách duyệt cây containment và duyệt đồ thị reference.

### Dùng tên làm định danh duy nhất ở mọi nơi

Tên có thể trùng trong các module hoặc thay đổi khi refactoring. Với mô hình lớn, stable ID kết hợp scope và namespace thường đáng tin cậy hơn.

### Tuần tự hóa bằng cách mở rộng mọi liên kết

Mở rộng cả containment lẫn reference có thể lặp dữ liệu và gây đệ quy vô hạn. Nên serialize containment theo cấu trúc và reference theo ID/URI.

### Nhầm unresolved với null

Một reference chưa được resolve, một reference tùy chọn không có giá trị và một reference bị hỏng là ba trạng thái khác nhau. Mô hình nên biểu diễn đủ rõ để diagnostics và runtime xử lý đúng.

## Quy trình thiết kế quan hệ cho mô hình DSL

Khi xây dựng một mô hình trừu tượng, có thể xác định containment và reference theo trình tự sau:

1. **Liệt kê các khái niệm:** xác định node, thực thể, giá trị, khai báo, biểu thức và hành động của miền.
2. **Xác định cấu trúc sở hữu:** hỏi phần tử nào là thành phần cấu trúc của phần tử nào; phần tử nào có vòng đời gắn với container.
3. **Xác định liên kết ngữ nghĩa:** tìm các quan hệ dùng chung, lời gọi, import, kiểu, kế thừa hoặc phụ thuộc giữa các phần tử độc lập.
4. **Đặt bội số:** xác định quan hệ bắt buộc, tùy chọn, một-nhiều hoặc nhiều-nhiều.
5. **Xác định danh tính:** quyết định phần tử nào cần ID ổn định và phạm vi duy nhất của ID.
6. **Thiết kế resolve:** quy định scope, namespace, import, overload và cách xử lý reference chưa tìm thấy.
7. **Định nghĩa vòng đời:** xác định hành vi xóa, di chuyển, sao chép và thay thế đích.
8. **Định nghĩa lưu trữ:** chọn cách serialize containment và reference, xử lý proxy và chu trình.
9. **Thiết kế traversal:** tách duyệt cây containment khỏi duyệt đồ thị reference và xây cross-reference index khi cần.
10. **Kiểm tra invariant:** xác nhận mô hình hợp lệ trước khi thực thi hoặc triển khai.

Với mỗi quan hệ, nên ghi lại tên, kiểu nguồn, kiểu đích, loại quan hệ, bội số, khả năng điều hướng ngược, quy tắc resolve và chính sách vòng đời. Bảng quan hệ này giúp nhóm thống nhất mô hình trước khi triển khai class hoặc schema.

## Kết luận

Containment và reference là hai loại quan hệ nền tảng trong mô hình trừu tượng DSL. Containment thể hiện cấu trúc và quyền sở hữu: một phần tử chứa các thành phần tạo nên nó. Reference thể hiện liên kết: một phần tử trỏ đến đối tượng có danh tính và vòng đời riêng.

Mô hình thường dùng containment để tạo cây cấu trúc như Model, Module, Rule và các node biểu thức; dùng reference cho lời gọi hàm, import, kiểu dữ liệu, khai báo và các quan hệ giữa những phần độc lập. Phân biệt hai loại quan hệ giúp quản lý vòng đời, resolve tên, kiểm tra tính hợp lệ, tuần tự hóa, điều hướng, refactoring và xử lý chu trình chính xác hơn.

Khi thiết kế, hãy bắt đầu từ ý nghĩa miền và quyền sở hữu thực tế, sau đó xác định bội số, danh tính, scope, chính sách xóa và cách lưu trữ. Một mô hình rõ ràng về containment và reference tạo nền tảng ổn định cho frontend, semantic analyzer, công cụ phát triển và backend của DSL.
