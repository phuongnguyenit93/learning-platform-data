# Định dạng mã sinh

## 1. Định dạng mã sinh là gì?

Trong quy trình sinh mã (code generation), một DSL được phân tích và chuyển thành mã của ngôn ngữ đích như Java, Kotlin, TypeScript, SQL hoặc một định dạng cấu hình. **Định dạng mã sinh** (generated-code formatting) là bước tổ chức phần mã đầu ra sao cho dễ đọc, nhất quán, dễ review và thuận tiện cho các công cụ phát triển.

Ví dụ, một DSL mô tả phép tính:

~~~text
rule discount { when order.total > 1000000 then applyDiscount(order, 10) }
~~~

có thể sinh ra Java. Dạng đầu ra tối giản:

~~~java
public boolean apply(Order order){if(order.getTotal().compareTo(Money.of(1000000))>0){discountService.apply(order,10);return true;}return false;}
~~~

Dạng được định dạng:

~~~java
public boolean apply(Order order) {
    if (order.getTotal().compareTo(Money.of(1_000_000)) > 0) {
        discountService.apply(order, 10);
        return true;
    }

    return false;
}
~~~

Hai đoạn mã có thể biểu diễn cùng logic. Định dạng tốt làm rõ cấu trúc điều kiện, khối lệnh và luồng trả về, nhờ đó người phát triển dễ kiểm tra và bảo trì mã được sinh.

Định dạng là một phần của chất lượng artifact. Mã sinh thường được đọc trong pull request, dùng để debug, lưu trong repository hoặc tiếp tục được compiler và formatter khác xử lý. Vì vậy, code generator cần có quy tắc định dạng rõ ràng và tạo đầu ra ổn định.

## 2. Định dạng không được thay đổi ngữ nghĩa

Mục tiêu đầu tiên của formatter là thay đổi cách trình bày mà giữ nguyên ý nghĩa chương trình. Các thay đổi định dạng thường gồm:

- Thêm hoặc bỏ khoảng trắng không có ý nghĩa cú pháp.
- Xuống dòng tại ranh giới biểu thức hoặc câu lệnh.
- Thụt lề các block.
- Đặt dấu ngoặc và dấu phẩy theo quy ước.
- Sắp xếp hoặc nhóm import khi ngôn ngữ cho phép và quy tắc được xác định.
- Chuẩn hóa cách viết literal hoặc dấu kết thúc câu lệnh khi việc chuẩn hóa được bảo đảm tương đương.

Một formatter không được tùy tiện:

- Đổi thứ tự các biểu thức có side effect.
- Đổi thứ tự câu lệnh hoặc nhánh điều kiện.
- Thêm, xóa hoặc di chuyển dấu ngoặc theo cách làm đổi precedence.
- Thay kiểu dữ liệu hoặc giá trị literal.
- Xóa comment có ý nghĩa đối với công cụ.
- Viết lại API hoặc logic nghiệp vụ.

Ví dụ, biểu thức:

~~~java
calculateFirst() + calculateSecond()
~~~

có thể có side effect trong cả hai lời gọi. Đổi thành:

~~~java
calculateSecond() + calculateFirst()
~~~

không còn là thay đổi định dạng vì thứ tự đánh giá có thể ảnh hưởng trạng thái và kết quả.

Định dạng cũng cần bảo toàn precedence. Biểu thức:

~~~java
a + b * c
~~~

không tương đương với:

~~~java
(a + b) * c
~~~

Nếu formatter tái tạo biểu thức từ AST, nó phải thêm ngoặc ở những vị trí cần thiết để giữ nguyên cây biểu thức.

## 3. Formatter nằm ở đâu trong pipeline sinh mã?

Một pipeline phổ biến:

~~~mermaid
flowchart TD
    A["DSL source"] --> B["Lexer and parser"]
    B --> C["AST"]
    C --> D["Semantic analysis"]
    D --> E["IR / code model"]
    E --> F["Code emitter"]
    F --> G["Generated source"]
    G --> H["Formatter / pretty printer"]
    H --> I["Formatted artifact"]
    I --> J["Compiler, tests or packaging"]
~~~

Formatter có thể được tích hợp trực tiếp vào code emitter hoặc chạy như một bước riêng sau khi sinh mã. Mỗi lựa chọn có ưu điểm:

| Cách tổ chức | Đặc điểm | Khi phù hợp |
|---|---|---|
| Emitter tự định dạng | Emitter quyết định khoảng trắng, xuống dòng và thụt lề khi ghi node | Generator nhỏ, target grammar đơn giản |
| Pretty printer dùng chung | AST hoặc code model được chuyển thành cấu trúc tài liệu rồi renderer quyết định layout | Generator có nhiều node và cần quy tắc bố cục nhất quán |
| Formatter bên ngoài | Sinh mã trước, sau đó gọi formatter của ngôn ngữ đích | Cần tuân thủ style guide hoặc formatter chuẩn của hệ sinh thái |
| Kết hợp | Emitter tạo source hợp lệ, formatter chuẩn hóa phần trình bày | Nhiều target hoặc cần tận dụng formatter sẵn có |

Một kiến trúc tốt phân biệt **sinh cấu trúc mã** với **trình bày mã**. Emitter chịu trách nhiệm phát ra đúng cấu trúc và token; pretty printer chịu trách nhiệm chọn cách bố trí trong giới hạn cú pháp và style.

## 4. Sinh mã trực tiếp và sinh từ code model

### 4.1. Nối chuỗi trực tiếp

Generator đơn giản có thể tạo mã bằng cách nối chuỗi:

~~~java
String source = "if (" + condition + ") {"
        + action + "}";
~~~

Cách này dễ bắt đầu nhưng nhanh chóng khó quản lý khi có block lồng nhau, comment, import, biểu thức nhiều dòng hoặc nhiều target language. Các đoạn nối chuỗi riêng lẻ dễ tạo ra khoảng trắng không nhất quán và lỗi dấu phân cách.

### 4.2. Sinh từ AST hoặc code model

Một cách bền vững hơn là tạo các node mô tả cấu trúc mã đích:

~~~text
MethodDeclaration
  modifiers: public
  returnType: boolean
  name: apply
  parameters:
    - Order order
  body:
    - IfStatement
        condition: order.total > threshold
        then:
          - ExpressionStatement(applyDiscount(order, 10))
          - ReturnStatement(true)
    - ReturnStatement(false)
~~~

Code model có thể là AST riêng của generator hoặc API của thư viện sinh mã. Emitter duyệt model và tạo cấu trúc tài liệu. Formatter sau đó bố trí cấu trúc này thành source text.

Ưu điểm của code model:

- Các loại node và vị trí hợp lệ được thể hiện rõ.
- Dễ kiểm tra thiếu thành phần bắt buộc trước khi ghi.
- Có thể dùng chung quy tắc thụt lề và xuống dòng.
- Có thể giữ metadata, comment và source mapping.
- Giảm việc tự ghép dấu ngoặc và dấu phân cách trong nhiều nơi.

## 5. Pretty printing và mô hình tài liệu

Pretty printing là kỹ thuật chuyển một cấu trúc chương trình thành văn bản dễ đọc theo một tập quy tắc trình bày. Một pretty printer thường không quyết định ngữ nghĩa; nó nhận cấu trúc đã có và chọn cách hiển thị.

Một mô hình tài liệu (document model) có thể gồm các thành phần:

- Text: một đoạn văn bản không cần thay đổi.
- Line: vị trí có thể xuống dòng.
- Soft line: có thể là dấu cách khi vừa dòng hoặc newline khi cần.
- Hard line: luôn xuống dòng.
- Concat: nối các tài liệu.
- Indent/Nest: tăng mức thụt lề của nội dung.
- Group: thử trình bày một nhóm trên một dòng; nếu không vừa thì mở các điểm xuống dòng.

Ví dụ mô tả một lời gọi hàm:

~~~text
Group(
  Concat(
    Text("calculate("),
    Nest(4, SoftLine + Join(SoftLine, arguments)),
    SoftLine,
    Text(")")
  )
)
~~~

Nếu danh sách đối số ngắn, renderer có thể tạo:

~~~java
calculate(order, tax, discount)
~~~

Nếu danh sách dài, cùng một cấu trúc document có thể được trình bày:

~~~java
calculate(
    order,
    tax,
    discount
)
~~~

Điểm quan trọng là emitter tạo một mô tả bố cục, còn renderer chọn cách ngắt dòng dựa trên chiều rộng và quy tắc định dạng.

## 6. Chiều rộng dòng và quy tắc ngắt dòng

Formatter thường có giới hạn chiều rộng dòng (line width), ví dụ 100 hoặc 120 cột. Đây là mục tiêu bố cục chứ không phải giới hạn cú pháp. Khi một biểu thức vượt chiều rộng, formatter tìm điểm ngắt hợp lệ.

Ví dụ:

~~~java
registerRule("large-order", order -> order.total() > threshold, requireManualReview());
~~~

Có thể được trình bày thành:

~~~java
registerRule(
    "large-order",
    order -> order.total() > threshold,
    requireManualReview()
);
~~~

Các điểm ngắt thường phù hợp:

- Sau dấu phẩy trong danh sách tham số hoặc đối số.
- Trước hoặc sau toán tử theo style guide.
- Giữa các phần của biểu thức chuỗi.
- Giữa các import hoặc khai báo.
- Trước block hoặc nhánh điều khiển.

Không phải mọi vị trí giữa token đều là điểm ngắt hợp lệ. Formatter phải hiểu cấu trúc hoặc dựa trên tokenization để không tách identifier, literal hay toán tử nhiều ký tự.

### 6.1. Group và lựa chọn bố cục

Một group có thể có hai dạng:

- Flat: các soft line được chuyển thành dấu cách nếu toàn bộ group vừa chiều rộng.
- Broken: các soft line trở thành newline khi group không vừa.

Thuật toán renderer ước lượng xem group có vừa phần chiều rộng còn lại trên dòng hay không. Nếu vừa, chọn flat; nếu không, chọn broken. Với tài liệu lồng nhau, quyết định có thể được thực hiện độc lập ở từng group.

### 6.2. Indentation và nesting

Thụt lề biểu thị cấu trúc block:

~~~java
if (condition) {
    if (nestedCondition) {
        execute();
    }
}
~~~

Formatter cần định nghĩa:

- Số space cho mỗi mức indent.
- Có dùng tab hay space.
- Cách căn lề continuation line.
- Cách căn lề tham số khi danh sách nhiều dòng.
- Cách căn lề chain method hoặc biểu thức nhiều dòng.

Quy tắc cần nhất quán giữa các node, không phụ thuộc vào thứ tự emitter được gọi.

## 7. Dấu ngoặc và precedence của biểu thức

Khi in biểu thức từ AST, formatter cần giữ nguyên cấu trúc ưu tiên. Mỗi node biểu thức có thể có precedence và associativity.

Ví dụ:

~~~text
a + b * c
(a + b) * c
a - (b - c)
~~~

Hai biểu thức đầu khác nhau do precedence. Biểu thức thứ ba cần ngoặc vì phép trừ không có tính kết hợp theo cách có thể bỏ ngoặc tùy tiện.

Một thuật toán in biểu thức thường nhận precedence của ngữ cảnh cha:

1. Xác định precedence của node hiện tại.
2. So sánh với precedence của vị trí mà node được in.
3. Thêm ngoặc nếu bỏ ngoặc sẽ làm parser tạo cây khác.
4. Xử lý associativity trái/phải để giữ đúng nhóm toán hạng.

Ví dụ pseudocode:

~~~text
printExpression(node, parentPrecedence):
    own = precedence(node)
    needsParens = own < parentPrecedence
    if needsParens:
        emit("(")
    print node according to its kind
    if needsParens:
        emit(")")
~~~

Trong implementation thật, điều kiện ngoặc còn phụ thuộc associativity và vị trí toán hạng trái/phải. Không nên chỉ so sánh một con số precedence mà bỏ qua các trường hợp như a - (b - c).

## 8. Định dạng các cấu trúc mã phổ biến

### 8.1. Khai báo và import

Các import thường được đặt ở đầu tệp, mỗi import một dòng:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;
~~~

Nếu formatter sắp xếp import, cần có quy tắc rõ ràng về nhóm package, static import, alias, wildcard và comment gắn với import. Sắp xếp chỉ an toàn khi ngôn ngữ không quy định thứ tự import có ý nghĩa và không có side effect khi nạp module.

### 8.2. Khai báo hàm hoặc method

~~~java
public Money calculateTotal(
        Order order,
        TaxPolicy taxPolicy,
        DiscountPolicy discountPolicy) {
    Money subtotal = order.subtotal();
    Money tax = taxPolicy.calculate(subtotal);
    Money discount = discountPolicy.calculate(subtotal);

    return subtotal.add(tax).subtract(discount);
}
~~~

Formatter cần quy định cách xuống dòng chữ ký, căn lề tham số, vị trí dấu ngoặc mở block và khoảng trắng giữa các câu lệnh.

### 8.3. Điều kiện và vòng lặp

~~~java
if (order.isEligible() && order.total().isPositive()) {
    approve(order);
} else {
    requestReview(order);
}
~~~

Các nhánh điều khiển nên có bố cục dễ quét. Formatter cần xử lý nhất quán dấu ngoặc block, khoảng trắng quanh toán tử và cách xuống dòng với điều kiện dài.

### 8.4. Collection và object literal

~~~java
List<String> supportedRegions = List.of(
    "NORTH",
    "CENTRAL",
    "SOUTH"
);
~~~

Với object literal hoặc map nhiều trường:

~~~text
shippingPolicy = {
    method: "STANDARD",
    maxWeight: 25,
    requiresSignature: true
}
~~~

Formatter có thể đặt mỗi phần tử trên một dòng nếu collection dài hoặc có comment. Dấu phẩy cuối (trailing comma) chỉ được thêm nếu target language cho phép.

### 8.5. Chuỗi dài

Chuỗi không thể được xuống dòng tùy tiện vì newline có thể thay đổi giá trị. Nếu target language hỗ trợ string concatenation hoặc text block, formatter có thể dùng cách trình bày tương ứng, nhưng phải giữ chính xác nội dung.

Ví dụ:

~~~java
String message = "The order requires manual review because "
        + "its total exceeds the configured threshold.";
~~~

Nếu dùng text block, cần kiểm tra quy tắc indentation và newline của ngôn ngữ đích để tránh thay đổi nội dung chuỗi.

## 9. Comment và metadata trong mã sinh

Comment có thể được sinh từ mô tả DSL, tài liệu rule hoặc metadata:

~~~java
/**
 * Routes high-value orders to manual review.
 *
 * Source rule: large-order
 */
public boolean reviewLargeOrder(Order order) {
    ...
}
~~~

Formatter cần xác định comment gắn với node nào:

- Comment đầu tệp.
- Comment trước khai báo.
- Comment cuối dòng.
- Comment bên trong block.
- Comment tài liệu.
- Comment marker do generator tạo.

Nếu comment được gắn với AST node, khi node được di chuyển hoặc định dạng lại, comment cần đi cùng node theo chính sách. Nếu comment chỉ được nối vào output như chuỗi tự do, formatter có thể đặt sai vị trí hoặc làm mất liên kết.

Một số công cụ dùng marker để nhận biết vùng mã sinh:

~~~java
// Generated by RuleCompiler. Do not edit this section.
~~~

Marker chỉ là thông tin cho người đọc hoặc công cụ; nó không tự bảo vệ nội dung khỏi chỉnh sửa. Nếu generator cần bảo toàn vùng do người dùng tự quản lý, nên có mô hình region rõ ràng và quy tắc merge thay đổi.

## 10. Định dạng xác định và đầu ra có thể tái lập

Một code generator tốt nên tạo cùng một chuỗi đầu ra khi đầu vào và cấu hình giống nhau. Tính chất này gọi là deterministic output.

Đầu ra xác định giúp:

- Git diff ổn định giữa các lần build.
- Cache artifact theo hash đáng tin cậy hơn.
- Review chỉ hiển thị thay đổi thực sự.
- Build tái lập trong CI và môi trường developer.
- Kiểm tra hồi quy bằng golden files.

Các yếu tố có thể làm output không xác định:

- Duyệt map hoặc set không có thứ tự ổn định.
- Import được sắp xếp theo locale hoặc môi trường.
- Timestamp hiện tại được chèn vào đầu tệp.
- Đường dẫn tuyệt đối của máy build được sinh vào comment.
- Line ending khác nhau giữa hệ điều hành.
- Phiên bản formatter hoặc cấu hình style không được khóa.

Nên:

1. Sắp xếp dữ liệu theo khóa xác định khi thứ tự không mang ý nghĩa.
2. Không đưa timestamp hoặc đường dẫn máy cục bộ vào output nếu không cần.
3. Khóa phiên bản formatter và cấu hình.
4. Chuẩn hóa encoding và line ending.
5. Đảm bảo thứ tự node, import và metadata ổn định.

## 11. Idempotence: định dạng nhiều lần không đổi

Một formatter nên có tính idempotent:

\[
F(F(source)) = F(source)
\]

Nghĩa là sau khi định dạng một lần, định dạng lại lần nữa không làm thay đổi output.

Tính chất này quan trọng khi pipeline vừa có code generator vừa có formatter ngoài. Nếu formatter mỗi lần chạy lại thay đổi thêm khoảng trắng hoặc vị trí dòng, repository sẽ luôn có diff dù logic không đổi.

Một quy trình thường dùng:

1. Sinh mã từ DSL.
2. Chạy formatter.
3. Lưu artifact.
4. Trong CI, chạy lại formatter ở chế độ kiểm tra.
5. Báo lỗi nếu formatter tạo diff.

Idempotence cần được kiểm tra trên nhiều cấu trúc: biểu thức lồng nhau, import, comment, chuỗi nhiều dòng, generic, annotation và block rỗng.

## 12. Canonical formatting và style configuration

Canonical formatting là một cách trình bày chuẩn được chọn làm dạng chính thức cho mã sinh. Thay vì để mỗi emitter hoặc developer tự chọn style, toàn bộ generator dùng cùng bộ quy tắc.

Một style configuration có thể bao gồm:

| Cấu hình | Ví dụ |
|---|---|
| Indent size | 4 spaces |
| Line width | 100 columns |
| Line ending | LF |
| Encoding | UTF-8 |
| Brace style | K&R hoặc Allman |
| Trailing comma | Khi target language hỗ trợ |
| Blank lines | Giữa import, field và method |
| Import ordering | Theo nhóm package và tên |
| Final newline | Có newline ở cuối tệp |

Không nên để các giá trị này rải rác trong nhiều emitter. Một cấu hình tập trung giúp mọi file được sinh theo cùng một chính sách và dễ thay đổi khi style guide cập nhật.

### 12.1. Cấu hình theo target language

Một DSL có thể sinh nhiều ngôn ngữ. Quy tắc định dạng Java không thể áp dụng nguyên xi cho SQL hoặc TypeScript. Có thể chia cấu hình thành:

- Quy tắc chung: encoding, line ending, final newline, line width.
- Quy tắc target-specific: dấu ngoặc, import, type annotation, semicolon, comment syntax.
- Quy tắc dự án: nhóm import, tên file, header và vùng mã được bảo vệ.

Target profile cần được version hóa cùng code generator để một lần nâng cấp không âm thầm thay đổi toàn bộ style của artifact.

## 13. Dùng formatter của ngôn ngữ đích

Thay vì tự viết mọi quy tắc, generator có thể gọi formatter có sẵn:

| Target | Công cụ có thể tích hợp |
|---|---|
| Java | google-java-format, Eclipse formatter |
| Kotlin | ktfmt, ktlint |
| TypeScript/JavaScript | Prettier |
| Python | Black, Ruff formatter |
| SQL | sqlfluff hoặc formatter theo dialect |
| XML | XML formatter của toolchain |
| JSON | Formatter tuân theo JSON hoặc dialect được chọn |

Việc chọn công cụ cần dựa trên phiên bản target language, license, khả năng chạy trong CI, tốc độ và mức độ cấu hình.

### 13.1. Formatter như một bước hậu xử lý

Pipeline có thể chạy formatter sau khi emitter tạo source:

~~~text
AST / IR
   |
   v
Code emitter
   |
   v
Raw generated source
   |
   v
Target formatter
   |
   v
Formatted source
~~~

Ưu điểm là formatter hiểu grammar thật của ngôn ngữ đích, có thể chuẩn hóa các cấu trúc mà generator chưa xử lý đẹp. Nhược điểm là cần cài đặt và quản lý tool riêng, có thể tăng thời gian build và làm thay đổi style khi nâng cấp formatter.

### 13.2. Formatter không sửa được mã sai cú pháp

Formatter thường yêu cầu đầu vào parse được. Nếu emitter tạo source không hợp lệ, formatter có thể thất bại hoặc tạo diagnostic khó hiểu. Vì vậy, generator vẫn phải đảm bảo cấu trúc mã đúng trước khi gọi formatter.

Nếu formatter hỗ trợ partial formatting hoặc error recovery, không nên xem đó là bằng chứng rằng artifact hợp lệ. Cần chạy compiler hoặc parser của target language để xác nhận tính hợp lệ trong pipeline phù hợp.

## 14. Source map và ánh xạ về DSL gốc

Sau khi định dạng, vị trí trong mã đích có thể khác vị trí trong mã thô hoặc DSL nguồn. Khi debug, người dùng thường cần biết đoạn Java hoặc SQL được sinh từ rule nào trong DSL.

Source map lưu quan hệ giữa:

- Source span trong DSL.
- Node AST hoặc IR.
- Source span trong mã đích.
- File hoặc artifact được sinh.

Ví dụ:

~~~text
DSL source:
  rules/pricing.dsl:12:5-12:48

Generated source:
  build/generated/PricingRules.java:38:9-40:10
~~~

Formatter có thể thêm dòng, thay đổi khoảng trắng và di chuyển token. Nếu source map được tạo trước formatter, cần cập nhật mapping hoặc dùng formatter có khả năng bảo toàn/biến đổi source map.

Các cách tiếp cận:

1. Formatter trả về mapping từ offset cũ sang offset mới.
2. Gắn source metadata vào document node rồi renderer tạo span mới.
3. Định dạng trước khi tạo source map cuối cùng.
4. Dùng marker hoặc metadata bên ngoài source để liên kết generated region với DSL node.

Không nên giả định line number sau định dạng bằng line number trước định dạng. Điều đó làm debugger và diagnostic trỏ sai vị trí.

## 15. Bảo toàn comment, vùng chỉnh sửa thủ công và generated marker

Trong một số dự án, mã sinh được đưa vào repository và developer có thể thêm phần tùy chỉnh. Nếu generator ghi đè toàn bộ tệp mỗi lần chạy, thay đổi thủ công có thể bị mất.

Các chiến lược thường dùng:

- Tách mã sinh và mã tùy chỉnh thành file riêng.
- Sinh interface hoặc base class, để người dùng triển khai phần mở rộng.
- Đánh dấu vùng generated và vùng user-owned bằng marker ổn định.
- Merge theo AST hoặc theo region thay vì thay toàn bộ file.
- Không chỉnh sửa file generated trực tiếp; sửa DSL hoặc template nguồn.

Ví dụ marker:

~~~java
// <generated id="pricing-rules">
public final class PricingRules {
    ...
}
// </generated>

// User-owned extension point
final class CustomPricingHooks {
    ...
}
~~~

Marker cần có quy tắc parsing và validation. Nếu marker bị xóa hoặc lồng sai, generator nên báo lỗi thay vì âm thầm ghi đè nội dung không rõ quyền sở hữu.

Formatter cũng cần biết vùng nào được phép định dạng. Nếu vùng user-owned không thuộc phạm vi generator, formatter không nên thay đổi nó trừ khi dự án có chính sách chung áp dụng cho toàn file.

## 16. Định dạng file và quy tắc văn bản

Ngoài bố cục cú pháp, generator cần chuẩn hóa các thuộc tính vật lý của file:

### 16.1. Encoding

UTF-8 thường là lựa chọn phù hợp cho source code hiện đại. Generator cần ghi encoding nhất quán và chỉ thêm byte order mark nếu target toolchain yêu cầu.

### 16.2. Line ending

Hai kiểu phổ biến:

- LF: newline dạng Unix.
- CRLF: newline dạng Windows.

Nếu developer và CI dùng line ending khác nhau, Git có thể hiển thị toàn bộ file như đã thay đổi. Nên chọn một chuẩn ở repository và cấu hình generator, formatter cùng Git attributes đồng bộ.

### 16.3. Final newline

Nhiều style guide yêu cầu đúng một newline ở cuối file. Điều này giúp công cụ dòng lệnh, diff và một số compiler xử lý nhất quán.

### 16.4. Whitespace cuối dòng

Formatter nên loại bỏ trailing whitespace nếu nó không có ý nghĩa với target format. Tuy nhiên, không nên xóa khoảng trắng bên trong literal hoặc nội dung raw text.

### 16.5. Tên file và thứ tự artifact

Tên file sinh nên ổn định theo quy tắc từ DSL hoặc module. Nếu generator tạo nhiều file, thứ tự ghi và manifest cũng nên xác định để build tái lập.

## 17. Định dạng mã sinh từ template

Một số generator dùng template engine để trộn dữ liệu với mẫu văn bản:

~~~text
public class {{className}} {
{{#each methods}}
    {{signature}} {
        {{body}}
    }
{{/each}}
}
~~~

Template giúp tách nội dung tĩnh khỏi dữ liệu sinh. Tuy nhiên, khoảng trắng và newline trong template có thể tạo output không nhất quán nếu mỗi nhánh điều kiện hoặc vòng lặp tự quản lý indentation.

Các nguyên tắc:

- Dùng helper thống nhất cho indentation.
- Không để mỗi template tự định nghĩa quy tắc line ending.
- Xác định cách xử lý block rỗng.
- Giữ comment và source metadata qua quá trình render.
- Kiểm tra output bằng parser hoặc formatter của target language.
- Hạn chế lồng logic điều kiện phức tạp trong template; chuyển logic sang model hoặc emitter.

Với template sinh code, một lựa chọn là dùng template tạo AST/code model thay vì tạo source trực tiếp. Cách này giảm lỗi định dạng và giúp compiler kiểm tra cấu trúc sớm.

## 18. Tối ưu hiệu năng của formatter

Với hàng nghìn file được sinh, định dạng có thể chiếm đáng kể thời gian build. Một số cách tối ưu:

- Dùng renderer tuyến tính hoặc thuật toán có giới hạn rõ.
- Tái sử dụng style configuration và cấu trúc bất biến.
- Chỉ định dạng artifact đã thay đổi.
- Cache kết quả theo source hash, generator version và formatter version.
- Chạy formatter song song khi các file độc lập và tool hỗ trợ an toàn.
- Tránh khởi động process formatter riêng cho từng file nếu có thể xử lý theo batch.

Cache key cần bao gồm mọi yếu tố có thể ảnh hưởng output. Nếu chỉ dùng hash DSL mà bỏ formatter version, nâng cấp formatter có thể vẫn trả artifact cũ không đúng style mới.

Không nên tối ưu bằng cách bỏ qua formatter cho các file khó hoặc file lớn mà không có quy tắc rõ. Hãy đo thời gian và xác định nút thắt trước khi thay đổi kiến trúc.

## 19. Kiểm thử định dạng mã sinh

Định dạng cần được kiểm thử độc lập với tính đúng đắn ngữ nghĩa của generator.

### 19.1. Golden-file test

Mỗi trường hợp đầu vào có file output mong đợi. Test sinh mã rồi so sánh chính xác với golden file. Khi style thay đổi có chủ đích, cập nhật golden file trong cùng thay đổi để reviewer thấy diff.

### 19.2. Idempotence test

Định dạng output một lần rồi chạy formatter lần nữa. Hai kết quả phải giống nhau:

~~~text
formattedOnce  = format(source)
formattedTwice = format(formattedOnce)

assert formattedOnce == formattedTwice
~~~

### 19.3. Parse/compile test

Mã sau khi định dạng phải được parser hoặc compiler của ngôn ngữ đích chấp nhận. Test này phát hiện formatter làm mất token hoặc emitter tạo cấu trúc sai.

### 19.4. Semantic equivalence test

Với các thay đổi formatter phức tạp, có thể so sánh AST trước và sau formatting hoặc chạy cùng bộ test hành vi. Nếu formatter chỉ thay đổi whitespace, AST phải tương đương.

### 19.5. Snapshot source map

Kiểm tra source map sau định dạng vẫn trỏ đúng về rule hoặc node DSL nguồn. Test nên bao gồm nhiều dòng, comment, biểu thức lồng và nhiều file.

### 19.6. Test nền tảng văn bản

Kiểm tra encoding, LF/CRLF, final newline, trailing whitespace và Unicode. Các test này giúp tránh diff không cần thiết giữa môi trường developer và CI.

## 20. Tích hợp định dạng vào CI và quy trình phát triển

Một pipeline CI có thể:

1. Biên dịch hoặc chạy code generator từ DSL.
2. Chạy formatter với phiên bản đã khóa.
3. Kiểm tra formatter không tạo thay đổi ngoài dự kiến.
4. Biên dịch mã sinh bằng target compiler.
5. Chạy unit test hoặc integration test liên quan.
6. Lưu artifact và metadata phục vụ traceability.

Có hai chế độ formatter thường dùng:

- **Write mode:** tự ghi lại file theo style chuẩn.
- **Check mode:** chỉ kiểm tra file đã đúng style chưa và trả lỗi nếu cần thay đổi.

Trong CI, check mode giúp phát hiện artifact không được tạo qua pipeline chuẩn hoặc bị chỉnh sửa thủ công. Trong local development, write mode thuận tiện để chuẩn hóa file.

Nếu output được sinh hoàn toàn từ DSL, quy trình review nên hướng developer sửa DSL hoặc template nguồn. Sửa trực tiếp generated file thường không bền vì lần build tiếp theo có thể ghi đè.

## 21. Ví dụ end-to-end: sinh và định dạng Java từ DSL

DSL đầu vào:

~~~text
rule high-value-order {
    when order.total > money(10000000, VND)
    then requireManualReview(order.id)
}
~~~

Code model:

~~~text
ClassDeclaration("HighValueOrderRule")
  MethodDeclaration("matches", returnType = boolean)
    Parameter("order", "Order")
    Return(
      GreaterThan(
        Call(Member(order, "total")),
        Call("Money.of", 10000000, "VND")
      )
    )
  MethodDeclaration("execute", returnType = void)
    Parameter("order", "Order")
    ExpressionStatement(
      Call("reviewService.requireManualReview", Member(order, "id"))
    )
~~~

Java output sau định dạng:

~~~java
public final class HighValueOrderRule {
    public boolean matches(Order order) {
        return order.total().compareTo(Money.of(10_000_000, Currency.VND)) > 0;
    }

    public void execute(Order order) {
        reviewService.requireManualReview(order.id());
    }
}
~~~

Pipeline có thể thực hiện:

1. Parse DSL và tạo AST.
2. Kiểm tra order.total, money literal và action có kiểu hợp lệ.
3. Tạo code model Java.
4. Pretty print code model theo Java style profile.
5. Chạy formatter Java nếu dự án yêu cầu.
6. Ghi UTF-8 với LF và final newline.
7. Biên dịch Java output.
8. Lưu source map từ method matches và execute về rule gốc.

Ví dụ cho thấy định dạng không thay đổi quy tắc high-value-order. Nó chỉ trình bày class, method, biểu thức và block theo bố cục dễ đọc.

## 22. Những lỗi thiết kế thường gặp

### Ghép chuỗi ở nhiều nơi

Mỗi emitter tự thêm khoảng trắng và newline dẫn đến style không nhất quán. Dùng document model hoặc helper chung cho token, block và indentation.

### Dùng formatter như cách sửa code sai

Formatter không thay thế parser hoặc semantic checker. Hãy bảo đảm code model hợp lệ trước khi định dạng.

### Ngắt dòng làm đổi literal

Chuỗi, raw text và template có thể chứa newline có ý nghĩa. Chỉ ngắt ở vị trí được target language cho phép.

### Thêm hoặc bỏ ngoặc sai

Formatter không xét precedence có thể thay đổi cây biểu thức. In biểu thức phải dựa trên precedence và associativity.

### Output không xác định

Thứ tự collection, timestamp, line ending và formatter version không ổn định làm Git diff thay đổi giữa các lần build. Chuẩn hóa nguồn tạo output và khóa cấu hình.

### Formatter không idempotent

Chạy nhiều lần vẫn tạo diff cho thấy quy tắc bố cục không ổn định hoặc có nhiều formatter xung đột. Chọn một style chuẩn và kiểm tra idempotence.

### Mất comment hoặc source mapping

Pretty printer chỉ biết AST có thể làm mất comment và vị trí DSL gốc. Giữ trivia, metadata và source span trong pipeline.

### Sửa trực tiếp file generated

Thay đổi thủ công bị ghi đè ở lần sinh sau. Tách phần tùy chỉnh hoặc thay đổi DSL/template nguồn.

### Khóa formatter không đầy đủ

Khác phiên bản formatter giữa local và CI có thể tạo output khác. Quản lý phiên bản tool và cấu hình như một phần của build input.

## 23. Quy trình thiết kế định dạng mã sinh

Khi xây dựng code generator cho một DSL, có thể thực hiện theo các bước:

1. **Xác định target language và style guide.** Ghi rõ formatter, phiên bản và cấu hình cần tuân theo.
2. **Chọn code representation.** Quyết định emitter tạo source trực tiếp, AST đích hay document model.
3. **Định nghĩa cấu trúc document.** Cung cấp Text, Line, Group, Concat và Indent hoặc cơ chế tương đương.
4. **Quy định bố cục.** Chọn line width, indentation, brace style, blank line, import order và final newline.
5. **Bảo toàn ngữ nghĩa.** Xử lý precedence, associativity, literal và thứ tự đánh giá.
6. **Bảo toàn metadata.** Gắn comment, generated marker và source span với node phù hợp.
7. **Chuẩn hóa file.** Chọn UTF-8, line ending và chính sách whitespace.
8. **Tạo output xác định.** Ổn định thứ tự dữ liệu, khóa formatter version và loại thông tin phụ thuộc máy.
9. **Tích hợp kiểm tra.** Dùng golden test, idempotence, parse/compile và source-map test.
10. **Đưa vào CI.** Chạy write/check mode theo quy trình và lưu artifact có thể truy nguyên.

## 24. Kết luận

Định dạng mã sinh là bước trình bày artifact được tạo từ DSL theo quy tắc dễ đọc và nhất quán. Formatter cần hiểu cấu trúc hoặc làm việc trên code model để quyết định khoảng trắng, thụt lề, dấu ngoặc và điểm ngắt dòng mà vẫn giữ nguyên ngữ nghĩa. Pretty printing dựa trên document model giúp tách logic sinh cấu trúc khỏi quyết định bố cục.

Một pipeline tốt cần tạo output xác định, formatter có tính idempotent, bảo toàn comment và source map, chuẩn hóa encoding cùng line ending, và tích hợp kiểm tra với compiler của ngôn ngữ đích. Có thể tự triển khai pretty printer hoặc dùng formatter chuẩn của target language, tùy độ phức tạp và yêu cầu dự án.

Khi thiết kế, hãy xem định dạng là một phần của hợp đồng artifact: cùng đầu vào và cấu hình cần tạo cùng kết quả; chạy formatter nhiều lần không tạo diff; và người đọc có thể truy ngược mã sinh về DSL nguồn. Những nguyên tắc đó giúp mã được sinh dễ review, debug, tái lập và bảo trì lâu dài.
