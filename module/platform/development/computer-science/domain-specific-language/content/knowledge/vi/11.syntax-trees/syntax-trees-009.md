# Biến đổi cây

Trong quá trình xây dựng một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), chương trình thường được chuyển từ văn bản hoặc giao diện đồ họa thành một cấu trúc cây để công cụ có thể phân tích và xử lý. Cây này có thể là cây phân tích cú pháp, cây cú pháp trừu tượng (Abstract Syntax Tree — AST), hoặc một mô hình cây đã được bổ sung thông tin kiểu và ngữ nghĩa. **Biến đổi cây** (*tree transformation* hoặc *AST transformation*) là hoạt động tạo ra một cấu trúc cây mới từ cây hiện có theo một quy tắc xác định.

Biến đổi cây được dùng ở nhiều giai đoạn của pipeline DSL: chuẩn hóa cú pháp, mở rộng cú pháp rút gọn, kiểm tra và làm rõ cấu trúc, hạ cấp về một mô hình đơn giản hơn, tối ưu biểu thức, bổ sung thông tin phục vụ thực thi hoặc chuyển chương trình sang dạng trung gian và mã đích. Mỗi biến đổi cần có mục tiêu rõ ràng và phải giữ đúng ý nghĩa của chương trình theo ngữ nghĩa DSL.

Ví dụ, DSL cho phép người dùng viết:

~~~text
unless order.isCancelled then approveOrder;
~~~

Đây là cú pháp rút gọn tương đương với:

~~~text
if not order.isCancelled then approveOrder;
~~~

Một phép biến đổi *desugaring* có thể thay nút `UnlessRule` bằng nút `ConditionalRule` có điều kiện `Not(PropertyAccess(order, isCancelled))`. Sau biến đổi, các bước kiểm tra và thực thi chỉ cần xử lý một dạng điều kiện chuẩn.

## 1. Cây cú pháp và nhu cầu biến đổi

### Cây biểu diễn chương trình

Một DSL dạng văn bản thường đi qua các bước phân tích từ vựng và cú pháp để tạo cây. Với DSL đồ họa, công cụ có thể tạo cây từ các khối, nút và kết nối trên giao diện. Cấu trúc cây thể hiện các thành phần và quan hệ cha–con của chương trình.

Ví dụ biểu thức:

~~~text
total + tax * rate
~~~

có thể được biểu diễn thành AST:

~~~text
Add
├── Name(total)
└── Multiply
    ├── Name(tax)
    └── Name(rate)
~~~

Cấu trúc này cho biết phép nhân nằm trong vế phải của phép cộng. Một công cụ có thể duyệt cây để kiểm tra kiểu, tính toán hằng, sinh mã hoặc chuyển biểu thức sang dạng khác.

### Biến đổi cây là gì?

Biến đổi cây là thao tác nhận một cây hoặc một nút cây làm đầu vào, áp dụng một hoặc nhiều quy tắc, rồi tạo ra cây kết quả. Tùy mục đích, phép biến đổi có thể:

- Thay một nút bằng nút khác.
- Thay đổi một thuộc tính hoặc giá trị literal.
- Thêm, xóa, sắp xếp lại hoặc gộp các nút con.
- Thay một cấu trúc phức tạp bằng cấu trúc đơn giản hơn.
- Mở rộng cú pháp rút gọn thành các cấu trúc chuẩn.
- Chuyển cây từ mô hình trừu tượng này sang mô hình trung gian khác.

Một phép biến đổi có thể chỉ tác động đến một phần cây hoặc tạo lại toàn bộ cây. Kết quả có thể cùng loại AST với đầu vào, hoặc thuộc một mô hình cây khác phù hợp với giai đoạn tiếp theo.

### Phân biệt biến đổi cây với duyệt cây

**Duyệt cây** (*tree traversal*) là quá trình đi qua các nút theo một thứ tự nhất định. **Biến đổi cây** sử dụng việc duyệt để tìm và thay đổi cấu trúc. Một lượt duyệt có thể chỉ thu thập thông tin, chẳng hạn đếm số nút hoặc tìm định danh; nó chưa chắc tạo cây mới.

Ví dụ:

- Duyệt để đếm số lần dùng `order.total`: thao tác phân tích, không nhất thiết thay đổi cây.
- Duyệt để thay `2 + 3` bằng `5`: thao tác biến đổi cây.
- Duyệt để gắn kiểu `Money` cho biểu thức: có thể là cập nhật metadata hoặc tạo cây đã phân giải, tùy thiết kế.

Phân biệt hai hoạt động này giúp API rõ ràng: visitor thường dùng để quan sát hoặc tính kết quả; transformer thường dùng để tạo cấu trúc mới.

## 2. Vì sao DSL cần biến đổi cây?

Biến đổi cây không chỉ là kỹ thuật tối ưu. Nó là cơ chế quan trọng để tổ chức ngữ nghĩa và tách cách người dùng viết chương trình khỏi cách hệ thống xử lý chương trình.

### Chuẩn hóa nhiều cách viết

Một DSL có thể hỗ trợ nhiều cú pháp tương đương để người dùng dễ viết. Ví dụ, `isPaid` có thể là cú pháp rút gọn cho `payment.status == ACCEPTED`. Parser hoặc một pass chuẩn hóa có thể chuyển các dạng này về một biểu diễn chung.

### Mở rộng cú pháp thuận tiện

Các cấu trúc như `unless`, `between`, `within`, `for each` hoặc biểu thức miền đặc thù có thể được chuyển thành những cấu trúc cơ bản hơn. Người dùng có cú pháp giàu ý nghĩa; trình thực thi chỉ cần hỗ trợ một tập cấu trúc cốt lõi.

### Tách mô hình cấp cao và cấp thấp

Mô hình cấp cao thường gần với thuật ngữ nghiệp vụ, chẳng hạn `ReserveInventory` hoặc `ApproveOrder`. Khi hạ cấp (*lowering*), các nút này có thể được chuyển thành lời gọi dịch vụ, điều kiện, thao tác dữ liệu hoặc cấu trúc điều khiển cụ thể.

### Tối ưu chương trình

Biến đổi có thể rút gọn biểu thức, loại bỏ phép tính thừa, hợp nhất điều kiện hoặc tạo cấu trúc thuận lợi cho trình thực thi. Ví dụ, `x * 1` có thể được rút gọn thành `x` nếu kiểu và ngữ nghĩa phép nhân cho phép.

### Tạo mã cho nền tảng đích

Một DSL có thể chạy trên nhiều nền tảng. Các pass biến đổi AST thành mô hình trung gian hoặc cây của nền tảng đích, sau đó trình sinh mã chuyển cây đó thành Java, SQL, cấu hình workflow hoặc định dạng khác.

### Bổ sung thông tin phục vụ công cụ

Một pass có thể gắn kiểu, tham chiếu đã phân giải, metadata, thông tin kiểm toán hoặc vị trí nguồn vào các nút. Đây là dạng làm giàu mô hình (*model enrichment*). Có hệ thống xem đây là biến đổi cây; hệ thống khác giữ AST bất biến và lưu kết quả trong các bảng phụ trợ.

## 3. Các loại biến đổi cây thường gặp

| Loại biến đổi | Mục đích | Ví dụ |
|---|---|---|
| Desugaring | Mở rộng cú pháp rút gọn thành cấu trúc cơ bản. | `unless c then a` thành `if not c then a`. |
| Normalization | Đưa các cách biểu diễn tương đương về dạng chuẩn. | Chuẩn hóa alias trạng thái hoặc biểu thức điều kiện. |
| Constant folding | Tính trước biểu thức chỉ chứa hằng. | `2 + 3` thành `5`. |
| Simplification | Loại bỏ thành phần dư thừa theo quy tắc an toàn. | `x and true` thành `x`. |
| Lowering | Chuyển cấu trúc cấp cao thành cấu trúc cấp thấp hơn. | `ReserveInventory(order)` thành kiểm tra tồn và lời gọi kho. |
| Inlining | Thay lời gọi hoặc tham chiếu bằng nội dung tương ứng. | Mở rộng macro hoặc quy tắc dùng chung. |
| Dead-code elimination | Loại bỏ cấu trúc không thể ảnh hưởng kết quả. | Xóa nhánh `if false` nếu không có tác dụng phụ. |
| Instrumentation | Bổ sung thao tác theo dõi hoặc kiểm toán. | Chèn ghi log trước và sau một hành động. |
| Code generation preparation | Chuyển AST sang mô hình thuận tiện cho backend. | Chuyển biểu thức miền thành biểu thức của IR. |

Không phải mọi pass đều nên gộp vào một bước. Tách các mục tiêu độc lập giúp dễ kiểm tra, đo hiệu năng và xác định lỗi phát sinh ở giai đoạn nào.

## 4. Các chiến lược duyệt cây

Để biến đổi cây, công cụ phải quyết định thứ tự đi qua các nút. Thứ tự này có thể ảnh hưởng đến kết quả, nhất là khi phép biến đổi của nút cha phụ thuộc vào kết quả đã biến đổi của nút con.

### Pre-order: duyệt từ cha xuống con

Pre-order xử lý nút hiện tại trước, sau đó mới đi xuống các nút con.

~~~text
visit(node):
    process(node)
    for child in node.children:
        visit(child)
~~~

Chiến lược này phù hợp khi cần quyết định có thay thế toàn bộ một nhánh trước khi đi sâu hay không, hoặc khi thông tin từ nút cha xác định ngữ cảnh của các nút con.

Ví dụ, nếu gặp nút `UnlessRule`, transformer có thể thay toàn bộ nút bằng cấu trúc `ConditionalRule` rồi tiếp tục biến đổi cây mới. Tuy nhiên, cần xác định rõ liệu các nút con mới có được duyệt trong cùng pass hay được xử lý ở pass kế tiếp.

### Post-order: duyệt từ con lên cha

Post-order xử lý các nút con trước, sau đó mới xử lý nút cha.

~~~text
visit(node):
    for child in node.children:
        visit(child)
    process(node)
~~~

Chiến lược này phù hợp với constant folding và simplification. Khi xử lý nút `Add`, các biểu thức con đã được biến đổi nên công cụ có thể biết liệu cả hai vế đã trở thành literal hay chưa.

Ví dụ:

~~~text
Add
├── Number(2)
└── Multiply
    ├── Number(3)
    └── Number(4)
~~~

Sau khi biến đổi nút con, cây có thể trở thành:

~~~text
Add(Number(2), Number(12))
~~~

Sau đó nút cha được rút gọn thành `Number(14)`.

### Duyệt theo chiều rộng (breadth-first)

Breadth-first xử lý các nút theo từng tầng: gốc, các con trực tiếp, rồi đến các tầng sâu hơn. Nó hữu ích khi cần phân tích cấu trúc theo mức, tìm nút gần gốc nhất hoặc xử lý các phần tử cùng cấp. Tuy nhiên, với nhiều phép biến đổi đệ quy phụ thuộc kết quả con, post-order thường tự nhiên hơn.

### Duyệt có chọn lọc

Không phải pass nào cũng cần đi qua mọi loại nút. Một transformer có thể chỉ xử lý biểu thức, chỉ xử lý khai báo, hoặc bỏ qua các nhánh đã được đánh dấu là không cần phân tích. Duyệt có chọn lọc giúp giảm công việc và thể hiện rõ phạm vi của pass.

### Sơ đồ thứ tự duyệt

~~~mermaid
flowchart TD
    A[Root] --> B[Child A]
    A --> C[Child B]
    B --> D[Leaf A1]
    B --> E[Leaf A2]
    C --> F[Leaf B1]
~~~

Với cây trên, pre-order thăm `Root, Child A, Leaf A1, Leaf A2, Child B, Leaf B1`; post-order thăm `Leaf A1, Leaf A2, Child A, Leaf B1, Child B, Root`; breadth-first thăm `Root, Child A, Child B, Leaf A1, Leaf A2, Leaf B1`.

## 5. Visitor và Transformer

Visitor và Transformer là hai mẫu thiết kế thường dùng để tổ chức thao tác trên AST.

### Visitor: duyệt và thu thập kết quả

Visitor thường định nghĩa một phương thức cho từng loại nút. Nó cho phép thêm các thao tác như kiểm tra, in cây, đếm phần tử hoặc phân tích mà không cần đặt tất cả logic vào các lớp AST.

Ví dụ khái niệm:

~~~java
interface ExprVisitor<R> {
    R visitNumber(NumberExpr expr);
    R visitName(NameExpr expr);
    R visitAdd(AddExpr expr);
}

interface Expr {
    <R> R accept(ExprVisitor<R> visitor);
}
~~~

Một visitor tính giá trị biểu thức có thể trả về `BigDecimal`; visitor in cây có thể trả về `String`; visitor đếm nút có thể trả về `Integer`.

Visitor không nhất thiết tạo cây mới. Nó có thể chỉ đọc cấu trúc và trả về kết quả tổng hợp.

### Transformer: tạo cấu trúc mới

Transformer thường trả về một nút hoặc cây mới. Mỗi phương thức nhận một nút, biến đổi các nút con rồi quyết định giữ nguyên hay tạo nút thay thế.

~~~java
interface ExprTransformer {
    Expr transform(NumberExpr expr);
    Expr transform(NameExpr expr);
    Expr transform(AddExpr expr);
}
~~~

Với AST bất biến, transformer tạo nút mới khi có thay đổi. Nếu cây con không đổi, nó có thể tái sử dụng nút cũ. Cách làm này giảm việc cấp phát không cần thiết và giữ được cấu trúc chia sẻ.

### So sánh

| Tiêu chí | Visitor | Transformer |
|---|---|---|
| Mục tiêu | Quan sát, phân tích hoặc tính kết quả trên cây. | Tạo cây mới hoặc thay đổi cấu trúc cây. |
| Giá trị trả về | Có thể là số liệu, kết quả kiểm tra, chuỗi hoặc không có. | Thường là nút hoặc cây sau biến đổi. |
| Thay đổi AST | Thường không. | Có. |
| Ví dụ | Đếm biểu thức, kiểm tra tên, in cây. | Desugaring, constant folding, lowering. |

Một số thư viện gọi cả hai là visitor và dùng kiểu trả về để biểu diễn biến đổi. Điều quan trọng là hợp đồng của API phải nói rõ phương thức có tạo cấu trúc mới hay chỉ quan sát.

## 6. Quy tắc viết lại cây (tree rewriting)

Biến đổi cây thường được diễn đạt bằng các quy tắc viết lại (*rewrite rules*). Mỗi quy tắc xác định một mẫu cấu trúc cần tìm và cấu trúc thay thế.

Ví dụ:

~~~text
Add(Number(a), Number(b))  -> Number(a + b)
Multiply(x, Number(1))      -> x
And(x, Boolean(true))       -> x
Not(Not(x))                 -> x
~~~

Vế trái là mẫu cần khớp; vế phải là cấu trúc thay thế. Các biến như `a`, `b`, `x` đại diện cho các nút hoặc giá trị phù hợp.

### Khớp mẫu

Một quy tắc chỉ áp dụng khi nút hiện tại có cấu trúc tương ứng. Ví dụ, quy tắc `Add(Number(a), Number(b))` chỉ khớp khi cả hai con trực tiếp của `Add` là số literal. Nó không khớp với `Add(Name(x), Number(2))`.

Khớp mẫu có thể xét thêm kiểu và metadata. Chẳng hạn, `Multiply(x, Number(1)) -> x` chỉ an toàn nếu `1` là đơn vị nhân của kiểu dữ liệu đang xét và phép nhân không có tác dụng phụ.

### Điều kiện áp dụng (side condition)

Một rewrite rule có thể cần điều kiện bổ sung. Ví dụ, phép cộng hai literal tiền chỉ được gộp khi cùng loại tiền:

~~~text
Add(Money(a, USD), Money(b, USD))
    -> Money(a + b, USD)
~~~

Nếu hai giá trị khác đơn vị tiền tệ, quy tắc không được áp dụng trừ khi DSL có quy định chuyển đổi tỷ giá. Side condition ngăn phép biến đổi làm mất ý nghĩa miền.

### Một quy tắc có thể áp dụng ở nhiều vị trí

Với cây lớn, quy tắc có thể khớp ở nút gốc hoặc ở bất kỳ nút con nào. Một chiến lược rewrite cần xác định thứ tự tìm vị trí và thứ tự áp dụng quy tắc. Ví dụ, nếu cả `Not(Not(x))` và `Not(Boolean(true))` đều có thể được rút gọn, thứ tự áp dụng có thể ảnh hưởng đến số lượt cần thiết, dù kết quả cuối cùng có thể giống nhau.

## 7. Ví dụ biến đổi AST bằng Java

Giả sử DSL hỗ trợ biểu thức số học đơn giản. AST được mô hình hóa bằng các kiểu bất biến:

~~~java
import java.math.BigDecimal;

sealed interface Expr
    permits NumberExpr, NameExpr, AddExpr, MultiplyExpr {}

record NumberExpr(BigDecimal value) implements Expr {}

record NameExpr(String name) implements Expr {}

record AddExpr(Expr left, Expr right) implements Expr {}

record MultiplyExpr(Expr left, Expr right) implements Expr {}
~~~

### Transformer tính hằng

Một transformer post-order có thể biến đổi các con trước, sau đó xử lý nút cha:

~~~java
final class ConstantFolder {
    Expr transform(Expr expr) {
        return switch (expr) {
            case NumberExpr number -> number;
            case NameExpr name -> name;
            case AddExpr add -> foldAdd(
                transform(add.left()),
                transform(add.right())
            );
            case MultiplyExpr multiply -> foldMultiply(
                transform(multiply.left()),
                transform(multiply.right())
            );
        };
    }

    private Expr foldAdd(Expr left, Expr right) {
        if (left instanceof NumberExpr a
                && right instanceof NumberExpr b) {
            return new NumberExpr(a.value().add(b.value()));
        }
        if (left == right) {
            return new AddExpr(left, right);
        }
        return new AddExpr(left, right);
    }

    private Expr foldMultiply(Expr left, Expr right) {
        if (left instanceof NumberExpr a
                && right instanceof NumberExpr b) {
            return new NumberExpr(a.value().multiply(b.value()));
        }
        return new MultiplyExpr(left, right);
    }
}
~~~

Đây là ví dụ minh họa cho Java hiện đại có hỗ trợ pattern matching trong `switch`; cú pháp cụ thể phụ thuộc phiên bản Java. Trong triển khai thực tế, nhánh `left == right` không cần thiết cho phép cộng ở ví dụ này và có thể bỏ; transformer chỉ nên giữ logic phục vụ quy tắc đã định nghĩa. Khi cây có vị trí nguồn hoặc kiểu đã phân giải, các thông tin đó cũng cần được giữ hoặc tính lại theo chính sách của pass.

Đầu vào:

~~~text
Add(
    Number(2),
    Multiply(Number(3), Number(4))
)
~~~

Kết quả sau post-order constant folding:

~~~text
Number(14)
~~~

Các nút `Multiply` được xử lý trước, tạo `Number(12)`. Sau đó nút `Add` nhận hai literal `2` và `12`, rồi tạo `Number(14)`.

### Transformer giữ lại nhánh không đổi

Với AST bất biến, có thể tạo lại nút chỉ khi một trong các con đã thay đổi:

~~~java
private Expr transformAdd(AddExpr add) {
    Expr newLeft = transform(add.left());
    Expr newRight = transform(add.right());

    if (newLeft == add.left() && newRight == add.right()) {
        return add;
    }

    return new AddExpr(newLeft, newRight);
}
~~~

Cách này cho phép chia sẻ lại các nút không đổi. So sánh bằng tham chiếu chỉ phù hợp nếu transformer giữ lại đúng đối tượng cũ khi không có thay đổi. Với mô hình có equality theo giá trị, cần cân nhắc chi phí so sánh và cách nhận biết thay đổi.

## 8. Desugaring: mở rộng cú pháp rút gọn

Desugaring là phép biến đổi một cấu trúc cú pháp thuận tiện hoặc giàu ý nghĩa thành một cấu trúc cơ bản hơn mà DSL đã định nghĩa ngữ nghĩa rõ ràng.

### Ví dụ `unless`

DSL cho phép:

~~~text
unless order.isCancelled then approveOrder;
~~~

AST trước biến đổi:

~~~text
UnlessRule
├── condition: PropertyCall(order, isCancelled)
└── action: ActionCall(approveOrder)
~~~

AST sau desugaring:

~~~text
ConditionalRule
├── condition: Not(PropertyCall(order, isCancelled))
└── action: ActionCall(approveOrder)
~~~

Sau pass này, các bước kiểm tra và thực thi không cần biết `UnlessRule` tồn tại. Chúng chỉ xử lý `ConditionalRule` và `Not`.

### Ví dụ cú pháp `between`

DSL cho phép:

~~~text
when age between 18 and 65 then allow;
~~~

Có thể được mở rộng thành:

~~~text
when age >= 18 and age <= 65 then allow;
~~~

AST sau biến đổi:

~~~text
And
├── GreaterThanOrEqual(Name(age), Number(18))
└── LessThanOrEqual(Name(age), Number(65))
~~~

Khi mở rộng, cần xác định cận có bao gồm hay không, cách xử lý giá trị null, kiểu dữ liệu và trường hợp biên. Từ `between` trong một miền có thể mang nghĩa khác nhau; không được tự suy luận ngữ nghĩa chỉ từ tên cú pháp.

### Giữ nguồn gốc của cú pháp rút gọn

Sau desugaring, lỗi có thể phát sinh trong nút được tạo ra. Công cụ nên giữ thông tin nguồn gốc (*source origin*) để thông báo lỗi trỏ về câu lệnh `unless` hoặc `between` ban đầu, thay vì hiển thị một cấu trúc nội bộ mà người dùng chưa từng viết.

## 9. Normalization: đưa cây về dạng chuẩn

Normalization chuyển các biểu diễn tương đương hoặc gần tương đương về một dạng thống nhất. Nó giúp các bước sau đơn giản hơn vì không cần xử lý nhiều biến thể.

Ví dụ, nếu DSL cho phép:

~~~text
order.paid
order.paymentAccepted
order.payment.status == ACCEPTED
~~~

và cả ba được định nghĩa cùng ý nghĩa, normalization có thể đưa chúng về một biểu thức chuẩn như:

~~~text
PaymentAccepted(order)
~~~

Hoặc chuẩn hóa thành một nút `PaymentStatusCheck` có tham chiếu rõ ràng đến đơn hàng.

### Các dạng chuẩn hóa phổ biến

- Chuẩn hóa tên alias thành định danh chuẩn.
- Chuẩn hóa biểu thức điều kiện về dạng có cấu trúc nhất quán.
- Chuẩn hóa đơn vị đo hoặc literal theo quy ước miền.
- Chuẩn hóa cấu trúc danh sách và thứ tự khai báo khi thứ tự không có ý nghĩa.
- Mở rộng cú pháp viết tắt.
- Chuẩn hóa tham chiếu tên thành symbol ID hoặc đối tượng đã phân giải.

### Không phải mọi cách viết tương tự đều tương đương

Ví dụ, `a + b` và `b + a` có thể tương đương với số học thông thường, nhưng chưa chắc tương đương với kiểu có phép cộng quá tải, chuỗi, số dấu phẩy động hoặc phép toán có tác dụng phụ. Normalization chỉ được áp dụng khi ngữ nghĩa của DSL bảo đảm phép biến đổi hợp lệ.

## 10. Constant folding và simplification

Constant folding tính trước các biểu thức chỉ phụ thuộc vào giá trị hằng. Simplification áp dụng các đồng nhất thức để rút gọn cấu trúc.

### Constant folding

Ví dụ:

~~~text
2 + 3 * 4
~~~

AST ban đầu:

~~~text
Add(Number(2), Multiply(Number(3), Number(4)))
~~~

Sau folding:

~~~text
Number(14)
~~~

### Simplification biểu thức logic

Một số quy tắc logic cơ bản:

~~~text
And(x, true)       -> x
And(x, false)      -> false
Or(x, false)       -> x
Or(x, true)        -> true
Not(Not(x))        -> x
If(true, a, b)     -> a
If(false, a, b)    -> b
~~~

Những quy tắc này chỉ an toàn khi logic DSL có ngữ nghĩa boolean hai giá trị và việc đánh giá biểu thức không gây tác dụng phụ. Nếu DSL có giá trị `unknown`, `null`, logic ba giá trị hoặc short-circuit có thể quan sát được, cần điều chỉnh quy tắc.

### Phép biến đổi có thể làm thay đổi hành vi nếu không cẩn thận

Xét:

~~~text
checkA() and checkB()
~~~

Nếu `and` dùng short-circuit, `checkB()` chỉ được gọi khi `checkA()` trả về true. Việc sắp xếp lại thành `checkB() and checkA()` có thể làm thay đổi tác dụng phụ hoặc ngoại lệ. Do đó, luật giao hoán của logic không tự động áp dụng cho mọi biểu thức DSL.

Tương tự, `x * 0 -> 0` có thể không an toàn nếu `x` có thể gây lỗi khi đánh giá hoặc có tác dụng phụ. Cần xác định ngữ nghĩa đánh giá và loại biểu thức trước khi áp dụng luật tối ưu.

## 11. Lowering: chuyển cấu trúc cấp cao thành cấp thấp

Lowering là biến đổi cây từ một mô hình trừu tượng giàu ý nghĩa sang mô hình có cấu trúc đơn giản hơn, gần với cách thực thi hoặc nền tảng đích.

Ví dụ DSL cấp cao:

~~~text
reserveInventory for order;
~~~

AST cấp cao:

~~~text
ReserveInventory(order)
~~~

AST sau lowering có thể gồm:

~~~text
Sequence
├── ReadAvailableQuantity(order.items)
├── CompareAvailableWithRequested
├── Conditional
│   ├── condition: EnoughInventory
│   ├── then: CallInventoryService.reserve(order)
│   └── else: RaiseDomainError(InsufficientInventory)
└── RecordReservationResult
~~~

Ở cấp cao, người dùng chỉ cần khai báo mục tiêu giữ hàng. Ở cấp thấp, mô hình thể hiện các bước kiểm tra, gọi dịch vụ, xử lý lỗi và ghi nhận kết quả.

### Lợi ích của lowering

- Giảm số cấu trúc đặc thù cần hỗ trợ trong backend.
- Tách mô hình nghiệp vụ khỏi nền tảng thực thi.
- Cho phép nhiều backend dùng chung frontend và các pass cấp cao.
- Tạo cơ hội kiểm tra các ràng buộc trước khi sinh mã.
- Làm rõ tác dụng phụ, luồng điều khiển và dữ liệu cần truyền.

### Nhiều tầng IR

Một hệ thống có thể dùng nhiều biểu diễn trung gian (*Intermediate Representation — IR*):

~~~mermaid
flowchart LR
    A[AST cấp cao] --> B[AST đã chuẩn hóa]
    B --> C[Domain IR]
    C --> D[Control-flow IR]
    D --> E[Java / SQL / Workflow backend]
~~~

Mỗi IR nên có mục đích và tập cấu trúc được hỗ trợ rõ ràng. Không nên tạo quá nhiều tầng nếu chúng không đem lại lợi ích về kiểm tra, tái sử dụng hoặc sinh mã.

## 12. Các phép biến đổi tối ưu thường gặp

Sau khi chương trình được kiểm tra và hạ cấp đến mức phù hợp, công cụ có thể áp dụng các phép tối ưu. Một số kỹ thuật thường gặp trong compiler cũng có thể hữu ích cho DSL.

### Dead-code elimination

Loại bỏ cấu trúc không thể được thực thi hoặc không ảnh hưởng đến kết quả theo ngữ nghĩa DSL.

Ví dụ:

~~~text
if false then approveOrder;
~~~

có thể được thay bằng cấu trúc rỗng nếu điều kiện là hằng và việc đánh giá điều kiện không có tác dụng phụ.

### Common subexpression elimination

Nếu cùng một biểu thức được tính nhiều lần và việc tính có tính thuần (*pure*), công cụ có thể tính một lần rồi dùng lại kết quả.

~~~text
if order.total > threshold and order.total > minimum then ...
~~~

Hai truy cập `order.total` có thể được dùng chung nếu dữ liệu không thay đổi giữa các lần đánh giá và truy cập không có tác dụng phụ. Trong DSL có trạng thái biến đổi hoặc truy cập dữ liệu động, điều kiện này cần được chứng minh.

### Inlining

Một lời gọi đến quy tắc hoặc macro có thể được thay bằng nội dung của nó. Inlining giảm chi phí gọi hoặc giúp tối ưu liên tục, nhưng có thể làm cây lớn hơn và khiến thông tin nguồn phức tạp hơn.

### Loop unrolling

Với vòng lặp có số lần lặp nhỏ và biết tĩnh, công cụ có thể thay vòng lặp bằng các bản sao của thân vòng lặp. Điều này có thể giúp backend nhưng làm tăng kích thước mã và cần giữ đúng thứ tự tác dụng phụ.

### Strength reduction

Thay phép toán tốn kém bằng phép toán đơn giản hơn khi có điều kiện phù hợp. Ví dụ, phép nhân với lũy thừa của hai có thể được chuyển thành phép dịch bit trong một số kiểu số nguyên và backend nhất định. Với DSL nghiệp vụ, chỉ áp dụng khi mô hình kiểu và ngữ nghĩa số học bảo đảm tương đương.

## 13. Thiết kế một pipeline gồm nhiều pass

Một compiler hoặc interpreter DSL thường tổ chức biến đổi thành các **pass** riêng. Mỗi pass có đầu vào, đầu ra và điều kiện áp dụng rõ ràng.

Ví dụ pipeline:

~~~mermaid
flowchart TD
    A[Source DSL] --> B[Lexer và Parser]
    B --> C[AST thô]
    C --> D[Desugaring]
    D --> E[AST chuẩn hóa]
    E --> F[Phân giải tên và kiểm tra kiểu]
    F --> G[AST đã phân giải]
    G --> H[Kiểm tra quy tắc miền]
    H --> I[Lowering]
    I --> J[IR]
    J --> K[Optimization passes]
    K --> L[Code generation hoặc Interpreter]
~~~

Thứ tự chính xác phụ thuộc DSL. Ví dụ, một số cú pháp rút gọn cần thông tin kiểu để mở rộng chính xác; khi đó desugaring có thể cần diễn ra sau một phần phân tích ngữ nghĩa. Pipeline không phải công thức cố định cho mọi ngôn ngữ.

### Hợp đồng của một pass

Một pass nên mô tả:

- Loại cây đầu vào mà pass chấp nhận.
- Loại cây đầu ra và các bất biến được bảo đảm.
- Những loại nút pass có thể tạo, xóa hoặc thay đổi.
- Pass có cần symbol table, kiểu hoặc metadata không.
- Pass có thể phát sinh diagnostic hay không.
- Pass có bảo toàn source span hoặc origin theo cách nào.
- Pass có thể thất bại và cách báo lỗi.

Ví dụ, `DesugaringPass` có thể cam kết rằng đầu ra không còn `UnlessRule` hoặc `BetweenExpr`, trong khi `TypeCheckingPass` có thể cam kết mọi biểu thức đã được gắn kiểu hợp lệ hoặc có diagnostic tương ứng.

### Điều kiện đầu vào và đầu ra

Không nên chạy một pass trên cây chưa thỏa các điều kiện mà nó giả định. Ví dụ, pass tối ưu phép toán số học cần biết kiểu của toán hạng; nếu chưa phân giải kiểu, phép biến đổi có thể chọn sai quy tắc.

Có thể mô hình hóa các trạng thái cây khác nhau bằng kiểu riêng, chẳng hạn `ParsedAst`, `ResolvedAst`, `TypedAst` và `LoweredIr`. Cách này giúp trình biên dịch phát hiện việc gọi pass sai giai đoạn ngay từ lúc biên dịch nếu ngôn ngữ triển khai hỗ trợ kiểu phù hợp.

## 14. Thứ tự pass và tương tác giữa các phép biến đổi

Thứ tự pass có thể ảnh hưởng đến tính đúng đắn và hiệu quả.

Ví dụ, nếu một pass chuẩn hóa biến `order.paid` thành `PaymentAccepted(order)`, pass kiểm tra kiểu có thể chỉ cần xử lý dạng chuẩn. Ngược lại, nếu việc chuẩn hóa cần biết kiểu của `order`, kiểm tra tên và kiểu phải chạy trước.

Một số câu hỏi cần đặt ra:

- Pass nào tạo ra loại nút mà pass tiếp theo xử lý?
- Pass nào cần symbol table hoặc thông tin kiểu?
- Pass nào có thể loại bỏ thông tin nguồn mà pass sau còn cần?
- Pass nào có thể tạo cấu trúc mới cần được kiểm tra lại?
- Hai pass có thể đổi thứ tự mà vẫn giữ kết quả không?
- Có pass nào cần chạy lặp đến khi không còn thay đổi không?

### Phụ thuộc giữa pass

Có thể mô tả phụ thuộc như một đồ thị có hướng. Nếu `TypeCheck` cần AST đã được `NameResolution` xử lý, cạnh phụ thuộc là `NameResolution -> TypeCheck`. Pipeline phải tôn trọng thứ tự topo của đồ thị này.

Không nên sắp xếp pass chỉ theo tên hoặc theo tiện ích triển khai. Thứ tự phải xuất phát từ điều kiện đầu vào và đầu ra của chúng.

### Chạy lại pass

Một số pass chỉ cần chạy một lần. Một số phép rewrite có thể tạo cơ hội cho quy tắc khác áp dụng, vì vậy cần chạy lặp đến khi cây ổn định. Nếu chạy lặp, cần có điều kiện dừng rõ ràng và giới hạn an toàn.

## 15. Fixed point và hệ thống viết lại

Một phép biến đổi có thể được áp dụng lặp đi lặp lại cho đến khi không còn quy tắc nào thay đổi cây. Kết quả khi đó được gọi là **điểm bất động** (*fixed point*) của phép biến đổi.

Ví dụ, bộ rút gọn biểu thức:

~~~text
Add(Number(0), x) -> x
Multiply(Number(1), x) -> x
Not(Not(x)) -> x
~~~

Một lượt biến đổi có thể làm lộ ra cơ hội rút gọn ở nút cha hoặc nút con. Công cụ có thể tiếp tục chạy đến khi cây không đổi.

### Điều kiện dừng

Có thể dừng khi:

- Pass không tạo ra thay đổi nào.
- Cấu trúc cây mới bằng cấu trúc cây cũ theo phép so sánh đã chọn.
- Không còn rule nào khớp.
- Đạt giới hạn số lượt hoặc ngân sách thời gian.

Giới hạn số lượt là biện pháp bảo vệ khi hệ thống rewrite không bảo đảm hội tụ. Nếu đạt giới hạn, công cụ cần báo trạng thái phù hợp thay vì giả vờ đã chuẩn hóa hoàn toàn.

### Nguy cơ vòng lặp vô hạn

Nếu có hai quy tắc:

~~~text
Add(x, 0) -> x
x -> Add(x, 0)
~~~

thì hệ thống có thể thay đổi qua lại vô hạn. Quy tắc thứ hai quá rộng và làm mất tính kết thúc.

Để tránh vòng lặp:

- Chỉ định hướng rewrite về một dạng chuẩn có độ phức tạp giảm.
- Định nghĩa thứ tự ưu tiên và phạm vi quy tắc.
- Kiểm tra cây có thay đổi thật sự trước khi lặp.
- Dùng giới hạn lượt hoặc phát hiện chu kỳ khi hệ thống phức tạp.
- Kiểm thử các nhóm rule có khả năng tương tác.

### Termination và confluence

Hai thuộc tính lý thuyết quan trọng của hệ thống rewrite là:

- **Termination:** mọi chuỗi áp dụng quy tắc đều kết thúc.
- **Confluence:** nếu một cấu trúc có thể được biến đổi theo nhiều đường khác nhau, các đường đó có thể hội tụ về cùng một dạng kết quả (sau các bước rewrite tiếp theo).

Nếu hệ thống có cả termination và confluence, dạng chuẩn đạt được thường không phụ thuộc thứ tự áp dụng quy tắc. Trong thực tế, không phải DSL nào cũng cần chứng minh đầy đủ hai thuộc tính này, nhưng cần hiểu nguy cơ khi nhiều rule chồng lấn hoặc xung đột.

## 16. Bảo toàn ngữ nghĩa khi biến đổi

Một phép biến đổi đúng cần giữ hành vi quan sát được của chương trình theo ngữ nghĩa DSL, trừ khi mục tiêu của pass là thay đổi hành vi theo một đặc tả đã được phê duyệt.

### Semantic preservation

Hai cây được xem là tương đương ngữ nghĩa nếu chúng tạo ra cùng kết quả quan sát được trong mọi ngữ cảnh được DSL cho phép. “Kết quả” không chỉ là giá trị cuối; có thể bao gồm:

- Thứ tự tác dụng phụ.
- Sự kiện được phát ra.
- Trạng thái miền được cập nhật.
- Ngoại lệ hoặc lỗi nghiệp vụ.
- Quyền truy cập và hành vi kiểm toán.
- Tương tác với hệ thống bên ngoài.

Ví dụ, biến đổi:

~~~text
logOrder();
approveOrder();
~~~

thành:

~~~text
approveOrder();
logOrder();
~~~

có thể giữ trạng thái cuối của đơn nhưng thay đổi thứ tự log và phê duyệt. Nếu log được dùng cho kiểm toán hoặc phê duyệt có thể thất bại, hai chương trình không tương đương.

### Các giả định cần làm rõ

Trước khi áp dụng một luật, cần xác định:

- Biểu thức có thuần hay có tác dụng phụ?
- Đánh giá có short-circuit không?
- Giá trị có thể là null hoặc unknown không?
- Phép toán có thể ném lỗi không?
- Dữ liệu có thể thay đổi giữa hai lần đọc không?
- Có ràng buộc về thứ tự sự kiện hoặc giao dịch không?
- Kiểu dữ liệu có quy tắc làm tròn, tràn số hoặc đơn vị riêng không?

Các giả định này quyết định phép biến đổi nào là an toàn.

### Ví dụ với số học và kiểu miền

Với số nguyên không giới hạn, `x + 0 -> x` thường hợp lệ. Với kiểu số nguyên có tràn số, phép toán vẫn có thể tương đương tùy quy tắc tràn. Với kiểu `Money`, phép cộng có thể yêu cầu cùng đơn vị tiền. Với `Duration`, phép cộng có thể có quy tắc riêng về múi giờ hoặc lịch làm việc. Không nên áp dụng các luật số học tổng quát nếu DSL định nghĩa phép toán miền khác.

## 17. Bất biến của cây trước và sau biến đổi

Mỗi mô hình cây thường có các bất biến cấu trúc. Pass phải giữ các bất biến đó hoặc chuyển cây sang một mô hình mới có bất biến riêng.

Ví dụ với AST chính sách:

- Mỗi `Rule` phải có đúng một điều kiện và một hành động.
- Điều kiện phải trả về boolean sau kiểm tra kiểu.
- Mọi `Reference` phải trỏ đến một khai báo hoặc thành phần miền hợp lệ.
- Mỗi `Policy` có tên hợp lệ và danh sách quy tắc.
- Không có nút `UnlessRule` sau desugaring.
- Không có biểu thức hằng chưa được folding nếu pass constant folding cam kết xử lý hết phạm vi hỗ trợ.

Có thể mô tả hợp đồng pass bằng bảng:

| Pass | Điều kiện đầu vào | Bất biến đầu ra |
|---|---|---|
| Desugaring | AST parse hợp lệ, các cú pháp mở rộng đã được nhận diện. | Không còn cú pháp rút gọn thuộc phạm vi pass. |
| Name resolution | Khai báo và phạm vi đã được xây dựng. | Tham chiếu hợp lệ được liên kết đến symbol. |
| Type checking | Tên và kiểu miền có thể được tra cứu. | Biểu thức được gắn kiểu hoặc có diagnostic. |
| Normalization | AST có đủ thông tin cần cho quy tắc chuẩn hóa. | Cấu trúc thuộc phạm vi pass ở dạng chuẩn. |
| Lowering | AST cấp cao đã qua kiểm tra cần thiết. | Chỉ còn các cấu trúc được IR đích hỗ trợ. |
| Code generation | IR hợp lệ và đã được hạ cấp đầy đủ. | Mã đích tuân theo hợp đồng backend. |

Nếu một pass tạo ra AST vi phạm bất biến, lỗi có thể chỉ xuất hiện ở pass sau và rất khó truy tìm nguyên nhân. Có thể dùng assertion hoặc validator nội bộ trong môi trường phát triển để phát hiện sớm.

## 18. AST bất biến và AST có thể thay đổi

Có hai cách tổ chức cây thường gặp.

### AST mutable

AST mutable cho phép thay trực tiếp thuộc tính hoặc danh sách con của nút. Cách này có thể đơn giản và hiệu quả trong một số trình biên dịch, nhưng dễ tạo trạng thái trung gian không hợp lệ nếu nhiều pass cùng truy cập hoặc một phép biến đổi thất bại giữa chừng.

Ví dụ:

~~~java
class AddNode {
    Expr left;
    Expr right;
}

add.left = new NumberNode(5);
~~~

Thay đổi trực tiếp có thể làm các tham chiếu khác đến cùng nút nhìn thấy kết quả mới. Điều này cần được kiểm soát nếu cây được chia sẻ.

### AST immutable

AST immutable không cho phép thay đổi nút sau khi tạo. Transformer tạo nút mới khi cần thay đổi và có thể tái sử dụng các nhánh không đổi.

~~~java
record AddNode(Expr left, Expr right) implements Expr {}

Expr rewritten = new AddNode(newLeft, newRight);
~~~

Ưu điểm:

- Dễ suy luận vì nút không đổi sau khi tạo.
- Có thể chia sẻ cấu trúc giữa các phiên bản cây.
- Hạn chế lỗi do cập nhật một phần.
- Phù hợp với xử lý song song nếu dữ liệu phụ trợ cũng an toàn luồng.

Chi phí là phải cấp phát nút mới khi có thay đổi. Kỹ thuật structural sharing giúp giảm chi phí bằng cách giữ lại các nhánh không đổi.

### Chọn cách nào?

AST mutable có thể phù hợp với compiler truyền thống cần hiệu năng và kiểm soát bộ nhớ chặt. AST immutable thường phù hợp với thư viện phân tích, công cụ IDE, xử lý đồng thời và pipeline cần lưu nhiều phiên bản cây. Có thể kết hợp: AST đầu vào bất biến, IR nội bộ mutable trong pass tối ưu, rồi xuất ra mô hình bất biến ở ranh giới.

## 19. Vị trí nguồn và nguồn gốc sau biến đổi

Biến đổi cây có thể tạo nút không xuất hiện trực tiếp trong văn bản ban đầu. Nếu không giữ liên kết nguồn, lỗi ở giai đoạn sau khó được giải thích cho người dùng.

### Kế thừa span

Khi một nút được thay bằng một nút tương đương, nút mới có thể kế thừa span của nút cũ. Ví dụ, `UnlessRule` được thay bằng `ConditionalRule`; toàn bộ cấu trúc mới có thể mang span của câu lệnh `unless` ban đầu.

### Span của nút tổng hợp

Một cú pháp rút gọn có thể tạo nhiều nút mới. Những nút này có thể cùng tham chiếu đến span của cú pháp gốc hoặc giữ origin riêng để phân biệt.

### Nguồn gốc của mã được sinh

Khi lowering tạo các nút gọi dịch vụ hoặc kiểm tra điều kiện, chúng có thể mang metadata liên kết đến hành động DSL ban đầu. Trình sinh mã có thể dùng metadata đó để tạo source map.

### Không gán vị trí giả

Nếu một nút được tạo ra hoàn toàn bởi tối ưu hóa và không tương ứng với một đoạn nguồn cụ thể, không nên tùy tiện gán vị trí đầu tệp. Có thể dùng origin của nút cha, đánh dấu là generated hoặc lưu nhiều nguồn liên quan.

## 20. Biến đổi cây và symbol table

Một số phép biến đổi cần biết định danh đang tham chiếu đến khai báo nào. Khi đó, AST thường được liên kết với **symbol table** hoặc mô hình ngữ nghĩa đã phân giải.

Ví dụ:

~~~text
let threshold = 100;
when order.total > threshold then approveOrder;
~~~

Tên `threshold` cần được phân giải đến khai báo cụ thể. Nếu transformer inline hằng, nó có thể thay tham chiếu bằng literal `100`, nhưng chỉ khi biết khai báo đó bất biến và giá trị không thay đổi.

### Tránh thay tên theo văn bản

Không nên biến đổi tên chỉ bằng cách tìm và thay chuỗi. Hai định danh cùng văn bản có thể thuộc hai phạm vi khác nhau. Một phép rename hoặc inline phải dựa trên symbol identity và phạm vi, không chỉ dựa trên lexeme.

### Capture và phạm vi tên

Khi biến đổi cấu trúc có binding, chẳng hạn lambda, biểu thức `let` hoặc macro, cần tránh làm thay đổi cách các tên được liên kết. Nếu một biến được đưa vào phạm vi có cùng tên với biến hiện có, có thể xảy ra variable capture.

Ví dụ:

~~~text
let x = 10 in
    map(items, item -> item.price + x)
~~~

Nếu inline hoặc di chuyển biểu thức vào một phạm vi có biến `x` khác, tham chiếu có thể bị đổi nghĩa. Transformer cần dùng symbol ID, đổi tên alpha hoặc cơ chế capture-avoiding substitution khi cần.

## 21. Phân biệt biến đổi cú pháp với biến đổi mô hình miền

Trong DSL, không phải mọi thay đổi cây đều là phép biến đổi cú pháp. Một số thao tác thay đổi cấu trúc biểu diễn; một số khác thay đổi mô hình miền hoặc nội dung nghiệp vụ.

- **Biến đổi cú pháp:** đổi `unless` thành `if not`, hoặc chuẩn hóa cách viết biểu thức.
- **Biến đổi mô hình:** thêm một trạng thái, quan hệ hoặc thuộc tính vào mô hình miền.
- **Biến đổi ngữ nghĩa:** thay đổi cách một cấu trúc được diễn giải hoặc thực thi.
- **Biến đổi triển khai:** hạ cấp nút miền thành lời gọi API hoặc cấu trúc backend.

Ví dụ, đổi `PaymentAccepted` thành `PaymentSettled` chỉ là rename nếu hai thuật ngữ được xác định tương đương. Nếu `settled` có nghĩa thanh toán đã đối soát hoàn tất, còn `accepted` chỉ là cổng thanh toán chấp nhận giao dịch, đây là thay đổi ngữ nghĩa nghiệp vụ. Không thể coi đó là một phép đổi tên cây đơn giản.

## 22. Kiểm thử biến đổi cây

Một pass cần được kiểm thử cả cấu trúc đầu ra lẫn ngữ nghĩa. Chỉ kiểm tra rằng pass không ném exception là chưa đủ.

### Kiểm thử ví dụ đầu vào–đầu ra

Cho một AST đầu vào xác định, kiểm tra AST sau biến đổi có cấu trúc mong đợi.

~~~text
Input:
Add(Number(2), Number(3))

Expected:
Number(5)
~~~

### Kiểm thử trường hợp không áp dụng

Đưa vào cấu trúc không khớp quy tắc và xác nhận transformer giữ nguyên cây hoặc chỉ biến đổi các nhánh con hợp lệ.

~~~text
Input:
Add(Name(x), Number(3))

Expected:
Add(Name(x), Number(3))
~~~

### Kiểm thử ngữ nghĩa tương đương

Với các đầu vào mẫu, thực thi chương trình trước và sau biến đổi trong cùng ngữ cảnh rồi so sánh kết quả quan sát được. Với các DSL có tác dụng phụ, cần so sánh cả thứ tự sự kiện, lỗi và thay đổi trạng thái.

### Kiểm thử tính ổn định

Nếu pass được kỳ vọng là idempotent, áp dụng hai lần phải cho kết quả tương đương với áp dụng một lần:

~~~text
T(T(tree)) == T(tree)
~~~

### Kiểm thử property-based

Sinh nhiều cây ngẫu nhiên theo metamodel, áp dụng pass và kiểm tra các thuộc tính như:

- Cây đầu ra vẫn hợp lệ theo metamodel.
- Không còn loại nút mà pass cam kết loại bỏ.
- Các span hợp lệ hoặc có origin được quy định.
- Không có tham chiếu bị mất hoặc trỏ đến symbol không hợp lệ.
- Hành vi được bảo toàn trong các trường hợp có thể thực thi.

### Kiểm thử hồi quy

Lưu các chương trình DSL đại diện và kết quả AST/IR mong đợi. Khi thay đổi rule hoặc pass, chạy lại bộ ví dụ để phát hiện khác biệt ngoài ý muốn.

## 23. Đo lường và gỡ lỗi pipeline biến đổi

Khi một chương trình cho kết quả sai, cần biết pass nào đã tạo ra cấu trúc gây lỗi. Có thể hỗ trợ gỡ lỗi bằng cách:

- Lưu hoặc in cây sau mỗi pass trong chế độ debug.
- Ghi tên pass, thời gian chạy và số nút được thay đổi.
- Gắn ID hoặc origin cho các nút quan trọng.
- Tạo diff giữa AST trước và sau biến đổi.
- Cho phép tắt từng pass để khoanh vùng nguyên nhân.
- Lưu diagnostic của từng pass cùng source span.

Ví dụ log:

~~~text
Pass: Desugaring
  Nodes visited: 124
  Nodes replaced: 3
  Output contains UnlessRule: false

Pass: ConstantFolding
  Nodes visited: 121
  Expressions folded: 8
  Output contains constant arithmetic: 0
~~~

Các số chỉ minh họa. Thông tin đo lường giúp phát hiện pass quá chậm, không có tác dụng hoặc tạo quá nhiều nút mới.

## 24. Hiệu năng và khả năng mở rộng

Với AST lớn, cách duyệt và tạo cây có ảnh hưởng đáng kể đến hiệu năng.

### Độ phức tạp

Một lượt duyệt qua toàn bộ cây thường có độ phức tạp (O(n)), với `n` là số nút. Nếu mỗi nút tạo một bản sao sâu của toàn bộ cây con, tổng chi phí có thể lớn hơn nhiều. Nên tạo lại đúng các nhánh bị ảnh hưởng và tái sử dụng phần còn lại khi có thể.

### Tránh duyệt lặp không cần thiết

Nếu nhiều pass chỉ cần thu thập thông tin tương tự, có thể kết hợp chúng trong một lượt phân tích. Tuy nhiên, không nên gộp các pass có phụ thuộc hoặc mục tiêu khác nhau chỉ để giảm số lần duyệt; tính rõ ràng và khả năng kiểm tra cũng quan trọng.

### Structural sharing

Với cây bất biến, các nhánh không đổi có thể được chia sẻ giữa cây cũ và cây mới. Cách này tiết kiệm bộ nhớ và hữu ích khi IDE cần giữ nhiều phiên bản AST.

### Tránh đệ quy quá sâu

Một DSL cho phép biểu thức lồng rất sâu có thể gây tràn stack nếu transformer dùng đệ quy. Có thể dùng stack tường minh hoặc giới hạn độ sâu đầu vào. Nếu DSL nhận chương trình không đáng tin cậy, cần xem xét giới hạn tài nguyên và cách xử lý cây cực lớn.

## 25. Ví dụ tổng hợp: biến đổi chính sách đơn hàng

Giả sử DSL cho phép mô tả:

~~~text
policy OrderPolicy {
    unless order.isCancelled then
        when order.payment.status == ACCEPTED
             and order.items.count > 0
        then approveOrder;
}
~~~

Một pipeline có thể thực hiện:

1. Parser tạo AST có `Policy`, `UnlessRule`, `ConditionalRule`, `And`, `Equal`, `PropertyAccess` và `ActionCall`.
2. Desugaring chuyển `UnlessRule` thành `ConditionalRule` với điều kiện `Not(...)`.
3. Normalization chuẩn hóa alias `ACCEPTED` về enum symbol đã phân giải.
4. Name resolution liên kết `order`, các thuộc tính và `approveOrder` đến định nghĩa tương ứng.
5. Type checking xác nhận các biểu thức điều kiện trả về boolean và hành động phù hợp ngữ cảnh.
6. Domain validation kiểm tra chính sách có đáp ứng quy tắc xác nhận đơn.
7. Lowering chuyển `approveOrder` thành các bước kiểm tra và cập nhật trạng thái cụ thể.
8. Optimization có thể rút gọn biểu thức hoặc loại bỏ cấu trúc thừa nếu điều kiện cho phép.
9. Backend sinh mã hoặc interpreter thực thi IR.

Sơ đồ:

~~~mermaid
flowchart TD
    A[AST có UnlessRule] --> B[Desugaring]
    B --> C[AST chỉ còn ConditionalRule]
    C --> D[Resolve names và types]
    D --> E[Typed AST]
    E --> F[Domain validation]
    F --> G[Lowering]
    G --> H[Order workflow IR]
    H --> I[Optimization]
    I --> J[Interpreter hoặc Code Generator]
~~~

Mỗi pass cần giữ thông tin nguồn để nếu lỗi xảy ra ở bước kiểm tra kiểu, lowering hoặc thực thi, công cụ vẫn có thể dẫn người dùng về câu lệnh DSL ban đầu. Đồng thời, mỗi pass cần giữ bất biến đầu ra để bước tiếp theo có thể dựa vào hợp đồng rõ ràng.

## 26. Những lỗi thiết kế thường gặp

**Dùng một pass làm quá nhiều việc.** Một pass vừa desugar, kiểm tra kiểu, tối ưu và sinh mã khiến khó xác định lỗi và khó kiểm thử. Nên tách theo mục tiêu và hợp đồng.

**Không xác định thứ tự duyệt.** Biến đổi nút cha trước hay sau nút con có thể tạo kết quả khác nhau. Cần chọn pre-order, post-order hoặc chiến lược khác theo yêu cầu.

**Áp dụng rewrite rule quá rộng.** Một quy tắc tổng quát có thể khớp cả trường hợp có tác dụng phụ hoặc kiểu dữ liệu đặc biệt. Cần side condition dựa trên kiểu và ngữ nghĩa.

**Không kiểm soát việc lặp pass.** Các rule có thể tạo vòng lặp hoặc không hội tụ. Cần điều kiện dừng, giới hạn và kiểm thử tương tác giữa các rule.

**Làm mất source span.** Cây mới không còn liên kết với văn bản gốc khiến thông báo lỗi và gỡ lỗi khó sử dụng.

**Biến đổi định danh theo chuỗi.** Rename hoặc inline chỉ dựa vào tên văn bản có thể thay nhầm tham chiếu ở phạm vi khác. Cần dùng symbol identity và hiểu phạm vi.

**Không bảo toàn tác dụng phụ.** Sắp xếp lại điều kiện hoặc hành động có thể đổi thứ tự sự kiện, ngoại lệ và trạng thái miền.

**Tối ưu trước khi biết kiểu.** Phép biến đổi số học hoặc logic có thể sai khi kiểu có quy tắc đặc biệt. Cần chạy sau các bước cung cấp thông tin cần thiết.

**Tạo quá nhiều bản sao cây.** Sao chép sâu ở mọi pass có thể làm tăng thời gian và bộ nhớ. Cân nhắc AST bất biến với structural sharing hoặc cập nhật có kiểm soát.

**Không xác minh bất biến đầu ra.** Một pass có thể tạo AST không hợp lệ nhưng lỗi chỉ xuất hiện ở backend. Nên có validator hoặc assertion trong giai đoạn phát triển.

## 27. Quy trình thiết kế một phép biến đổi cây

Trước khi triển khai một pass, hãy xác định:

1. **Mục tiêu:** vấn đề nào cần giải quyết — chuẩn hóa, mở rộng cú pháp, tối ưu hay lowering?
2. **Phạm vi nút:** những loại nút nào có thể được đọc, thay thế, tạo hoặc xóa?
3. **Điều kiện đầu vào:** cần AST đã parse, đã resolve tên, đã gắn kiểu hay đã kiểm tra quy tắc miền?
4. **Quy tắc rewrite:** mẫu nào được khớp và cấu trúc nào thay thế?
5. **Điều kiện phụ:** kiểu, tác dụng phụ, quyền hoặc dữ liệu nào phải được xác nhận?
6. **Chiến lược duyệt:** pre-order, post-order, breadth-first hoặc chọn lọc?
7. **Chính sách lặp:** chạy một lần hay đến fixed point? Điều kiện dừng là gì?
8. **Bất biến đầu ra:** những cấu trúc nào phải còn hoặc không còn sau pass?
9. **Nguồn gốc:** span, symbol reference và metadata được giữ hoặc tạo như thế nào?
10. **Kiểm thử:** có ví dụ đúng, sai, biên, tác dụng phụ và kiểm thử tương đương ngữ nghĩa không?
11. **Hiệu năng:** độ phức tạp, số lần duyệt, cấp phát và giới hạn độ sâu ra sao?

Một pass được thiết kế tốt có thể được hiểu và kiểm tra độc lập. Khi có nhiều pass, các hợp đồng rõ ràng giúp nhóm ghép chúng thành pipeline mà không phải dựa vào những giả định ngầm.

## 28. Kết quả cần có sau khi thiết kế biến đổi cây

Một thiết kế biến đổi cây cho DSL thường cần các đầu ra sau:

- **Đặc tả các pass:** mục tiêu, đầu vào, đầu ra và thứ tự phụ thuộc.
- **Bộ quy tắc viết lại:** mẫu khớp, cấu trúc thay thế và điều kiện áp dụng.
- **Chiến lược duyệt:** quy tắc xử lý cha/con và cách xử lý nút mới được tạo.
- **Bất biến của từng giai đoạn:** các cấu trúc được phép và các cấu trúc phải được loại bỏ.
- **Chính sách bảo toàn ngữ nghĩa:** điều kiện bảo đảm kết quả và tác dụng phụ không thay đổi.
- **Chính sách source origin:** cách giữ vị trí nguồn, tham chiếu và nguồn gốc của nút sinh.
- **Bộ kiểm thử:** ví dụ AST trước/sau, kiểm thử biên, kiểm thử idempotence và kiểm thử ngữ nghĩa.
- **Công cụ quan sát:** khả năng in cây, so sánh cây và ghi nhận thống kê từng pass.

Biến đổi cây là cầu nối giữa cấu trúc người dùng viết và biểu diễn mà DSL có thể kiểm tra, tối ưu hoặc thực thi. Khi quy tắc rewrite, thứ tự duyệt, bất biến và yêu cầu bảo toàn ngữ nghĩa được xác định rõ, pipeline có thể mở rộng mà vẫn dễ hiểu và dễ kiểm soát.
