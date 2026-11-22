# Thu gọn mã

## Thu gọn mã trong trình soạn thảo DSL là gì?

Trong trình soạn thảo ngôn ngữ chuyên miền (domain-specific language, DSL), một tài liệu có thể chứa nhiều khai báo, rule, block, biểu thức lồng nhau, comment hoặc phần cấu hình dài. Khi làm việc với tài liệu lớn, người dùng thường chỉ muốn tập trung vào một phần tại một thời điểm. **Thu gọn mã (code folding)** là tính năng cho phép ẩn tạm thời nội dung của một vùng văn bản và thay vùng đó bằng một dấu hiệu thu gọn, thường là một dòng hoặc placeholder ngắn.

Ví dụ, một rule DSL có thể gồm điều kiện và nhiều hành động:

~~~text
RULE "VIP discount"
WHEN customer.segment IS "VIP"
  AND order.total >= 1000000
THEN
  validateCustomer()
  calculateDiscount()
  applyDiscount()
ELSE
  applyStandardPrice()
~~~

Khi thu gọn phần thân rule, editor có thể hiển thị:

~~~text
RULE "VIP discount"  ...
~~~

Nội dung bên trong vẫn tồn tại trong tài liệu. Folding chỉ thay đổi cách hiển thị và vùng tương tác trong editor; nó không xóa source text, không thay đổi AST và không làm thay đổi chương trình được biên dịch hoặc thực thi.

Trong DSL editor, code folding có thể áp dụng cho:

- Khai báo module, package, namespace hoặc schema.
- Rule, function, procedure và declaration.
- Block điều kiện, vòng lặp, transaction hoặc workflow.
- Biểu thức nhiều dòng và danh sách dài.
- Comment nhiều dòng hoặc documentation block.
- Vùng được đánh dấu bằng marker do người dùng viết.
- Vùng import, metadata hoặc cấu hình lồng nhau.
- Các phần tử được tạo bởi grammar đặc thù của DSL.

Mục tiêu là giúp người dùng điều hướng và đọc cấu trúc chương trình dễ hơn, đặc biệt khi tài liệu có nhiều tầng. Một folding system tốt cần xác định vùng có thể thu gọn, xử lý vùng lồng nhau, cập nhật đúng khi văn bản thay đổi và giữ trạng thái hiển thị ổn định trong quá trình chỉnh sửa.

## Phân biệt folding với các tính năng editor khác

Folding thường được đặt cạnh outline, code navigation, syntax highlighting và code hiding, nhưng chúng có mục đích khác nhau.

| Tính năng | Mục đích |
|---|---|
| Code folding | Ẩn tạm thời nội dung một vùng văn bản |
| Outline / document symbols | Hiển thị cấu trúc tài liệu dưới dạng danh sách điều hướng |
| Syntax highlighting | Tô màu token theo loại cú pháp |
| Code navigation | Di chuyển đến khai báo hoặc tham chiếu |
| Code selection | Chọn một vùng văn bản |
| Code formatting | Thay đổi cách trình bày văn bản theo quy tắc |
| Code hiding | Ẩn nội dung theo policy hoặc trạng thái riêng của sản phẩm |

Folding có thể dùng cùng dữ liệu cấu trúc với outline, nhưng hai tính năng không đồng nhất. Outline có thể hiển thị mọi declaration, kể cả declaration một dòng không có phần thân để thu gọn. Ngược lại, một comment block có thể fold được dù không xuất hiện trong outline.

Folding cũng không phải là một phép biến đổi ngôn ngữ. Khi một block bị thu gọn, lexer và parser vẫn phân tích toàn bộ nội dung. Diagnostics, semantic analysis và code generation tiếp tục làm việc trên tài liệu đầy đủ.

## Lợi ích của code folding đối với DSL

### Giảm độ dài hiển thị

Một file có hàng trăm rule có thể được hiển thị dưới dạng danh sách tên rule và các dòng cấu trúc chính. Người dùng có thể thu gọn rule không cần xem và mở rule đang chỉnh sửa.

### Giữ ngữ cảnh khi đọc

Khi một workflow có nhiều bước lồng nhau, folding cho phép ẩn phần chi tiết nhưng vẫn giữ các tiêu đề block. Người dùng nhìn thấy cấu trúc tổng thể mà không phải cuộn qua mọi dòng.

### Hỗ trợ khám phá cấu trúc

Các fold range có thể phản ánh hierarchy của DSL. Người dùng nhanh chóng nhận ra module nào chứa rule nào, rule nào có nhánh ELSE và phần nào là comment documentation.

### Giảm nhiễu trong tài liệu dài

Comment dài, schema lớn, danh sách mapping hoặc phần literal nhiều dòng có thể được thu gọn để nội dung chính nổi bật hơn.

### Tăng hiệu quả điều hướng

Các thao tác fold all, unfold all, fold level và fold current region giúp người dùng thay đổi mức chi tiết nhanh chóng mà không phải chọn thủ công từng dòng.

### Hỗ trợ nhiều loại tài liệu

Một DSL editor có thể mở file nguồn, file schema, file query, file rule, file workflow hoặc file cấu hình. Folding giúp các loại tài liệu có cấu trúc lồng nhau đều dễ đọc.

## Các khái niệm cơ bản của folding

### Fold range

Một fold range là vùng văn bản mà editor cho phép thu gọn. Nó thường được biểu diễn bằng vị trí bắt đầu và kết thúc, có thể kèm loại vùng và metadata.

Ví dụ mô hình:

~~~text
FoldRange
  startLine
  startColumn
  endLine
  endColumn
  kind
  collapsedText
  source
~~~

Trong nhiều editor, range được biểu diễn theo vị trí bắt đầu và kết thúc của dòng. Một số editor cho phép range bắt đầu hoặc kết thúc giữa dòng. Hợp đồng của editor cần xác định rõ đơn vị vị trí và việc dòng kết thúc có được bao gồm hay không.

### Foldable region

Foldable region là một phần cấu trúc có thể thu gọn, ví dụ body của rule hoặc comment block. Region là khái niệm ngữ nghĩa hoặc cú pháp; fold range là vùng vị trí cụ thể mà editor dùng để hiển thị.

Một region có thể sinh một hoặc nhiều range tùy cách trình bày. Ngược lại, một fold range có thể được tạo từ marker hoặc heuristic mà không tương ứng với một AST node cụ thể.

### Folding marker hoặc gutter control

Nhiều editor hiển thị biểu tượng ở lề dòng để báo vùng có thể thu gọn. Người dùng nhấn biểu tượng để thu gọn hoặc mở rộng. Một số editor hỗ trợ thao tác bằng bàn phím, command palette hoặc context menu.

Biểu tượng gutter là giao diện của folding, không phải chính dữ liệu range. Range có thể tồn tại mà không được hiển thị nếu đang bị che bởi một vùng cha đã thu gọn.

### Collapsed placeholder

Khi vùng bị thu gọn, editor có thể hiển thị một placeholder như dấu ba chấm hoặc nội dung tóm tắt:

~~~text
RULE "VIP discount"  { ... }
~~~

Placeholder có thể là mặc định hoặc được tạo từ tên khai báo, số lượng phần tử hoặc comment đầu tiên. Nó chỉ phục vụ hiển thị. Không nên ghi placeholder vào source file trừ khi DSL định nghĩa một cú pháp riêng cho việc đó.

### Folding state

Folding state lưu việc một range đang mở hay đang đóng. State có thể được quản lý theo phiên editor, theo document hoặc được lưu giữa các lần mở file.

Cần phân biệt:

- Range có thể thu gọn.
- Range hiện đang thu gọn.
- Range đang bị ẩn vì một ancestor đã thu gọn.
- Range không còn hợp lệ sau chỉnh sửa.
- Range tạm thời chưa xác định do parser đang xử lý nội dung chưa hoàn chỉnh.

## Các cách xác định vùng có thể thu gọn

Không có một chiến lược duy nhất phù hợp với mọi DSL. Editor có thể dùng cấu trúc cú pháp, indentation, marker hoặc kết hợp nhiều nguồn.

### Folding dựa trên cú pháp (syntax-aware folding)

Syntax-aware folding sử dụng parser hoặc AST/CST để tìm những node có phần thân nhiều dòng. Đây thường là cách chính xác nhất khi DSL có grammar rõ.

Ví dụ:

~~~text
RULE "Shipping policy"
WHEN order.total >= 500000
THEN
  validateAddress()
  calculateShipping()
  setDeliveryOption()
END
~~~

Parser có thể xác định RuleDeclaration bắt đầu tại dòng RULE và kết thúc tại END. Folding provider có thể tạo range cho phần thân hoặc toàn bộ declaration tùy UX.

Các loại node thường fold được:

- ModuleDeclaration.
- RuleDeclaration.
- FunctionDeclaration.
- Class hoặc TypeDeclaration.
- BlockStatement.
- IfExpression hoặc IfStatement.
- LoopStatement.
- Workflow.
- Multi-line collection.
- Multi-line expression.
- Documentation comment.

Ưu điểm là range phản ánh cấu trúc thật và ít nhầm lẫn với dấu ngoặc nằm trong string hoặc comment. Hạn chế là cần parser hoặc parser state đủ tốt. Khi source đang chưa hoàn chỉnh, parser có thể chỉ tạo cây một phần.

### Folding dựa trên indentation

Một số DSL dùng indentation để xác định block:

~~~text
RULE "Shipping policy"
  WHEN order.total >= 500000
  THEN
    validateAddress()
    calculateShipping()
    setDeliveryOption()
~~~

Editor có thể tạo range từ một dòng đến hết nhóm dòng có indentation sâu hơn. Chiến lược này đơn giản và có thể hoạt động ngay cả khi chưa có parser đầy đủ.

Tuy nhiên, indentation folding chỉ nên áp dụng khi quy tắc thụt lề của DSL rõ ràng. Nếu indentation chỉ dùng để trình bày, một dòng được thụt sâu có thể không phải con của block trước đó. Tab, spaces, blank lines và comment cũng cần được xử lý nhất quán.

### Folding dựa trên delimiter

Nếu DSL dùng dấu ngoặc hoặc delimiter rõ ràng, editor có thể tạo fold range từ cặp mở/đóng:

~~~text
condition = (
  customer.active
  AND order.total >= 500000
  AND shipment.country == "VN"
)
~~~

Các cặp thường gặp:

- { và }.
- ( và ).
- [ và ].
- Từ khóa mở và đóng như BEGIN/END.
- Các tag mở và đóng nếu DSL có cấu trúc dạng tag.

Delimiter folding có thể được triển khai bằng lexer hoặc bracket matcher. Cần tránh nhận diện delimiter bên trong string literal, raw string hoặc comment như delimiter cấu trúc.

### Folding dựa trên marker do người dùng định nghĩa

Một số editor cho phép người dùng đánh dấu vùng bằng comment:

~~~text
// #region Pricing rules
RULE "VIP discount"
  ...
RULE "Seasonal discount"
  ...
// #endregion
~~~

Hoặc:

~~~text
/* region generated mappings */
...
/* endregion */
~~~

Marker giúp thu gọn vùng logic không được grammar mô tả như một block. Ví dụ, nhóm nhiều khai báo liên quan nhưng không có container chung.

Editor cần quy định marker có phân biệt chữ hoa/thường không, có lồng nhau không, marker không đóng được xử lý thế nào và marker có thể xuất hiện trong string hay không. Marker chỉ nên được nhận diện trong comment token, không nên quét chuỗi ký tự thuần túy trên toàn file.

### Folding dựa trên heuristic

Heuristic có thể tạo range từ các mẫu như nhiều dòng liên tiếp, comment dài hoặc danh sách lớn. Nó hữu ích khi không có parser hoặc để bổ sung trải nghiệm.

Tuy nhiên, heuristic dễ tạo range sai và khó dự đoán. Nên ưu tiên grammar, delimiter hoặc indentation đã được đặc tả. Nếu dùng heuristic, cần giới hạn phạm vi và cung cấp hành vi ổn định để người dùng không bị mất nội dung bất ngờ.

### Kết hợp nhiều provider

Một DSL editor có thể kết hợp:

1. AST provider cho declaration và block.
2. Comment provider cho documentation.
3. Delimiter provider cho biểu thức lồng.
4. Marker provider cho region thủ công.
5. Indentation provider cho tài liệu hoặc cấu trúc chưa parse được.

Khi nhiều provider tạo range trùng hoặc chồng lấn, editor cần quy tắc ưu tiên và loại bỏ duplicate. Không nên để cùng một vùng xuất hiện nhiều marker cạnh nhau.

## Thiết kế fold range và quy tắc lồng nhau

Một tài liệu DSL thường có nhiều vùng fold lồng nhau. Ví dụ, module chứa rule, rule chứa condition và action block, action block lại chứa một if block.

~~~text
MODULE pricing
  RULE "VIP discount"
    WHEN customer.segment IS "VIP"
    THEN
      IF order.total >= 1000000
        applyLargeDiscount()
      ELSE
        applyStandardDiscount()
      END
  END
END
~~~

Cấu trúc fold có thể là:

~~~text
Module
  Rule
    ThenBlock
      IfBlock
        ThenBranch
        ElseBranch
~~~

### Quan hệ chứa nhau

Range cha bao phủ range con. Khi thu gọn Module, các range con vẫn tồn tại trong model nhưng không hiển thị độc lập vì toàn bộ vùng con đang bị ẩn.

Khi mở Module, editor có thể khôi phục trạng thái riêng của Rule và IfBlock. Một số editor chỉ lưu trạng thái range đang hiển thị; số khác giữ state cho cả range bị ancestor che khuất.

Cần xác định hành vi mong đợi khi người dùng:

- Thu gọn range cha.
- Mở range cha.
- Thu gọn một range con.
- Mở tất cả range.
- Thu gọn theo level.
- Thay đổi nội dung khiến range cha biến mất.

### Range chồng lấn nhưng không chứa nhau

Hai range có thể giao nhau mà không có quan hệ chứa, ví dụ một marker region bắt đầu giữa một declaration và kết thúc sau declaration đó. Cấu trúc này có thể gây khó cho editor vì việc ẩn một vùng có thể cắt qua cấu trúc khác.

Nên thiết kế quy tắc để fold range tạo ra một hierarchy hợp lệ. Nếu hai provider tạo range giao nhau nhưng không chứa nhau, editor có thể:

- Ưu tiên provider có độ tin cậy cao hơn.
- Cắt hoặc loại range không hợp lệ theo quy tắc rõ.
- Báo lỗi cấu trúc nếu marker do người dùng viết bị sai.
- Từ chối range để giữ trải nghiệm nhất quán.

Không nên âm thầm thay đổi source để làm range khớp nhau.

### Vùng một dòng

Một block một dòng thường không có lợi ích khi thu gọn:

~~~text
RULE "Default" THEN applyDefault()
~~~

Editor có thể chỉ cung cấp folding khi range bao phủ ít nhất hai dòng hiển thị. Một số editor vẫn cho phép fold expression nhiều dòng trong cùng một dòng logic nếu range có cột bắt đầu và kết thúc, nhưng đây là trường hợp cần UX rõ ràng.

### Dòng bắt đầu và dòng kết thúc

Có nhiều quy ước về việc range có bao gồm dòng mở và dòng đóng hay không. Ví dụ, khi fold block:

~~~text
IF condition THEN
  actionA()
  actionB()
END
~~~

Editor có thể giữ dòng IF và END, chỉ ẩn nội dung ở giữa. Hoặc có thể ẩn từ sau IF đến trước END rồi hiển thị placeholder ở dòng mở.

Cần xác định:

- Dòng nào giữ lại khi thu gọn.
- Placeholder nằm ở dòng mở hay cuối vùng.
- Có cho phép fold chỉ phần body không.
- Dòng trống đầu/cuối có bị ẩn không.
- Comment gắn với declaration có nằm trong range không.
- Source span có dùng end-exclusive hay end-inclusive.

Các quy tắc này cần thống nhất với API editor để tránh off-by-one errors.

## Folding theo cấu trúc của DSL

Một DSL editor nên xác định rõ những construct nào có thể thu gọn. Cùng một loại AST node có thể có cách trình bày khác nhau tùy ngôn ngữ.

### Module và namespace

~~~text
MODULE billing
  IMPORT common.money
  TYPE Invoice
    ...
  END
  RULE "Late fee"
    ...
  END
END
~~~

Module và namespace thường là fold region tự nhiên. Khi thu gọn, có thể hiển thị tên module và số phần tử con nếu thông tin đó hữu ích.

### Rule và function

~~~text
RULE "VIP discount"
WHEN ...
THEN
  ...
END

FUNCTION calculateTax(order)
  ...
END
~~~

Rule và function có thể fold theo toàn bộ declaration hoặc riêng phần body. Nếu người dùng thường xuyên so sánh condition với action, việc giữ header và ẩn body có thể hữu ích.

### Nhánh điều kiện

~~~text
IF customer.isVip THEN
  applyVipPolicy()
ELSE IF order.isInternational THEN
  applyInternationalPolicy()
ELSE
  applyDefaultPolicy()
END
~~~

Editor có thể cung cấp range cho toàn bộ IF hoặc từng branch. Nếu chỉ fold từng branch, cần giữ cấu trúc ELSE để người dùng vẫn hiểu luồng điều khiển.

### Vòng lặp và block

~~~text
FOR item IN order.items
  validate(item)
  total = total + item.price
END
~~~

Vòng lặp có thể fold như một block. Với nested loop, range cần giữ quan hệ cha-con để fold level hoạt động đúng.

### Collection và object literal

~~~text
shippingZones = [
  "north",
  "central",
  "south",
  "islands"
]
~~~

Danh sách dài, map hoặc object literal có thể fold. Placeholder có thể hiển thị số phần tử, ví dụ [ ... 4 items ... ], nếu editor hỗ trợ custom collapsed text.

### Biểu thức nhiều dòng

~~~text
eligible =
  customer.active
  AND customer.segment IN [
    "GOLD",
    "PLATINUM",
    "DIAMOND"
  ]
  AND order.total >= minimumTotal
~~~

Không phải mọi biểu thức nhiều dòng đều nên có folding. Nếu range quá nhỏ hoặc fold làm mất ngữ cảnh cần thiết, editor có thể chỉ cung cấp fold cho collection bên trong.

### Comment và documentation

~~~text
/**
 * Applies a discount based on customer segment,
 * order value and current promotion policy.
 *
 * The function does not modify the original order.
 */
FUNCTION calculateDiscount(order)
  ...
END
~~~

Documentation block thường là fold region hữu ích. Editor cần phân biệt comment đứng riêng với comment cuối dòng và comment nằm trong string hoặc template literal.

### String và template nhiều dòng

~~~text
message = """
  Your order is eligible for free shipping.
  Estimated delivery: {deliveryDate}
"""
~~~

Một multiline string có thể dài nhưng không phải block cú pháp. Editor có thể hỗ trợ folding như một loại literal riêng, miễn là placeholder không làm thay đổi source text và syntax highlighting vẫn đúng.

Nếu DSL có template interpolation, parser cần biết vùng text và vùng expression. Folding provider nên sử dụng node literal hoặc token channel thay vì dò dấu nháy thủ công.

## Fold provider và tích hợp với parser

Trong kiến trúc editor, fold provider là thành phần cung cấp danh sách fold range cho một document hoặc vùng tài liệu.

Một interface khái quát:

~~~text
FoldingProvider
  provideFoldingRanges(document, context)
    -> List<FoldRange>
~~~

Context có thể chứa:

- Document version.
- AST hoặc CST hiện có.
- Lexer state.
- Language configuration.
- Marker configuration.
- Cancellation token.
- Giới hạn số range.
- Thông tin incremental parse.

Provider có thể chạy đồng bộ hoặc bất đồng bộ. Với file lớn, cần tránh chặn UI thread trong lúc parse hoặc tính fold range.

### Tạo range từ AST

Mỗi AST node có source span. Provider có thể chọn các loại node phù hợp:

~~~text
for node in ast:
  if node.kind in foldableKinds:
    if node.startLine < node.endLine:
      emit FoldRange(node.startLine, node.endLine, node.kind)
~~~

Trong triển khai thật, cần xử lý span chưa đầy đủ, node lỗi, node synthetic và vị trí được ánh xạ qua macro hoặc include.

### Tạo range từ CST hoặc token stream

CST giữ delimiter và token cụ thể nên phù hợp với folding theo cặp ngoặc hoặc comment. Lexer có thể đánh dấu comment block và multiline string bằng channel hoặc token kind riêng.

Nếu parser chưa hoàn thành, token stream vẫn có thể cung cấp một số range an toàn. Ví dụ, một cặp ngoặc đã đóng có thể fold được dù phần khai báo bao quanh còn lỗi.

### Tạo range từ syntax tree một phần

Trong editor, người dùng có thể đang nhập:

~~~text
RULE "New rule"
WHEN customer.active
THEN
  applyDiscount()
~~~

Nguồn chưa có END. Parser recovery có thể tạo node incomplete. Provider cần quyết định có tạo fold range tạm từ THEN đến EOF hay không.

Một số chính sách:

- Chỉ fold node đã có delimiter đóng.
- Fold block incomplete đến EOF trong editor mode.
- Không fold vùng có parse error nếu ranh giới không đáng tin cậy.
- Dùng indentation fallback khi AST không có node hoàn chỉnh.

Điều quan trọng là không tạo range vượt ngoài nội dung document hoặc làm ẩn phần văn bản mà người dùng cần để sửa lỗi.

### Ưu tiên và hợp nhất nhiều provider

Nếu AST provider và marker provider cùng tạo range tương đương, cần deduplicate theo vị trí và loại. Nếu hai provider tạo range lồng nhau, có thể giữ cả hai. Nếu range giao nhau không hợp lệ, cần quy tắc giải quyết xác định.

Có thể gắn nguồn tạo range:

~~~text
FoldRange
  start
  end
  kind
  providerId
  priority
~~~

Priority hữu ích khi cần quyết định range nào được giữ. Không nên dùng thứ tự chạy provider ngẫu nhiên làm quy tắc ưu tiên.

## Folding trong Language Server Protocol

Trong hệ sinh thái editor hỗ trợ Language Server Protocol (LSP), folding range có thể được cung cấp bởi language server thông qua yêu cầu textDocument/foldingRange.

Một folding range trong LSP thường chứa:

- startLine.
- endLine.
- Có thể có startCharacter và endCharacter.
- kind, thường là comment, imports hoặc region.
- collapsedText trong các phiên bản hỗ trợ thuộc tính này.

Language server phân tích document rồi trả về danh sách range. Client editor quyết định cách hiển thị gutter marker và placeholder.

### Vị trí theo LSP

LSP sử dụng vị trí dòng và ký tự với quy ước encoding được đàm phán trong phiên bản giao thức. Trong nhiều triển khai cũ, character offset mặc định là UTF-16 code units. Server cần tuân theo encoding đã thương lượng và không tự trộn byte offset, Unicode code point và UTF-16 code unit.

Nếu parser nội bộ dùng byte offset hoặc code point, cần một lớp chuyển đổi từ source span nội bộ sang LSP Position.

### Giới hạn số lượng range

Client có thể cung cấp giới hạn folding range. Server nên tôn trọng giới hạn đó và chọn range có giá trị nhất, thường ưu tiên cấu trúc cấp cao hoặc region quan trọng.

Không nên trả hàng trăm nghìn range cho một tài liệu lớn nếu client chỉ hiển thị được một số lượng giới hạn. Cần xác định chiến lược chọn range có tính ổn định để người dùng không thấy marker thay đổi ngẫu nhiên sau mỗi lần cập nhật.

### Đồng bộ với document version

Folding ranges được tính trên một phiên bản document. Nếu document thay đổi trong lúc server đang tính, kết quả cũ có thể đến sau kết quả mới.

Server hoặc client cần kiểm soát document version và hủy công việc đã lỗi thời. Không nên áp dụng range được tính trên văn bản cũ vào document mới vì vị trí dòng có thể đã dịch chuyển.

### Capability và fallback

Không phải client nào cũng hỗ trợ mọi khả năng folding giống nhau. Language server nên kiểm tra capability và trả dữ liệu theo giao thức được client hỗ trợ. Nếu client không hỗ trợ custom collapsed text, server vẫn có thể cung cấp range cơ bản.

## Tương tác người dùng trong editor

Folding cần có thao tác rõ ràng và nhất quán. Người dùng thường thao tác bằng gutter, bàn phím, menu hoặc command palette.

### Gutter marker

Marker thường xuất hiện ở dòng bắt đầu fold range. Các trạng thái phổ biến:

- Expanded: vùng đang mở, marker chỉ khả năng thu gọn.
- Collapsed: vùng đã thu gọn, marker chỉ khả năng mở rộng.
- Hidden by ancestor: range con bị ẩn vì range cha đã đóng.
- Not foldable: không có marker.

Marker nên có hit target đủ lớn và trạng thái trực quan rõ ràng. Không nên chỉ dựa vào màu sắc để phân biệt trạng thái.

### Các lệnh folding phổ biến

| Lệnh | Hành vi |
|---|---|
| Fold | Thu gọn range tại con trỏ |
| Unfold | Mở range chứa hoặc bắt đầu tại con trỏ |
| Fold All | Thu gọn tất cả range |
| Unfold All | Mở tất cả range |
| Fold Level N | Thu gọn range ở một cấp nhất định |
| Fold Recursively | Thu gọn range con trong một vùng |
| Unfold Recursively | Mở vùng và các vùng con |
| Toggle Fold | Đảo trạng thái range hiện tại |
| Fold Comments | Thu gọn comment block |
| Fold Imports | Thu gọn vùng import nếu được hỗ trợ |

Tên lệnh có thể khác nhau giữa editor, nhưng semantics nên nhất quán trong cùng sản phẩm.

### Phím tắt và command palette

Phím tắt cần tránh xung đột với lệnh phổ biến của hệ điều hành và editor. Người dùng nên có thể tìm lệnh qua command palette hoặc menu để không phải nhớ mọi tổ hợp phím.

Một editor có thể cung cấp phím tắt mặc định cho Fold, Unfold, Fold All và Unfold All, đồng thời cho phép tùy chỉnh.

### Con trỏ và selection khi fold

Nếu con trỏ nằm trong vùng sắp bị thu gọn, editor cần quyết định vị trí mới. Một số lựa chọn:

- Đưa con trỏ đến dòng mở vùng.
- Giữ logical cursor position và khôi phục khi unfold.
- Đưa focus đến placeholder.
- Không cho fold nếu selection sẽ bị ẩn trong một thao tác đặc biệt.

Selection cắt qua ranh giới vùng cũng cần được xử lý. Nếu người dùng chọn một phần văn bản rồi fold, editor phải giữ selection hoặc điều chỉnh theo quy tắc rõ ràng.

### Click vào placeholder

Placeholder có thể cho phép click để mở vùng. Một số editor hiển thị nội dung đầu hoặc cuối của vùng ngay trên placeholder. Nếu custom collapsed text có action, cần tránh biến nó thành nội dung có thể thực thi hoặc chỉnh sửa nhầm source.

## Folding state và lưu trạng thái

Một người dùng thường muốn mở lại file và thấy các vùng đã thu gọn giống lần trước. Folding state có thể được lưu trong bộ nhớ phiên, workspace state hoặc editor state persistence.

### Lưu theo vị trí

Cách đơn giản là lưu startLine và endLine. Tuy nhiên, khi người dùng chèn hoặc xóa dòng phía trên, vị trí thay đổi và state có thể áp dụng nhầm sang vùng khác.

### Lưu theo cấu trúc hoặc identity

Một cách bền hơn là gắn state với stable identity của declaration hoặc node. Ví dụ, Rule có ID rule-17 có thể giữ trạng thái folded ngay cả khi các dòng phía trên thay đổi.

Nếu DSL không có stable ID, editor có thể dùng fingerprint gồm loại node, tên khai báo, một phần nội dung hoặc anchor gần đó. Fingerprint chỉ là heuristic và có thể xung đột nếu hai vùng giống nhau.

### Lưu theo document version

Folding state có thể gắn với URI và version của document. Khi nội dung thay đổi, editor tính lại range và ánh xạ state cũ sang range mới bằng anchor hoặc edit mapping.

### Workspace và user preference

Cần phân biệt trạng thái của một tài liệu với preference chung:

- User preference: có bật folding, hiện marker, dùng placeholder kiểu nào.
- Document state: vùng nào đang đóng.
- Workspace state: cách khôi phục state khi mở lại project.
- Session state: trạng thái tạm thời chưa được lưu.

Không nên ghi trạng thái folding vào nội dung DSL trừ khi ngôn ngữ có directive riêng và người dùng chủ động yêu cầu.

## Cập nhật folding khi tài liệu thay đổi

Trong editor, document thay đổi liên tục. Fold ranges cần được cập nhật cùng lexer, parser và các dịch vụ ngôn ngữ khác.

Các thao tác có thể ảnh hưởng range:

- Chèn dòng trước một declaration.
- Xóa dòng mở hoặc đóng block.
- Đổi keyword khiến node đổi loại.
- Chèn dấu ngoặc làm thay đổi nesting.
- Di chuyển một block.
- Thay indentation.
- Chỉnh sửa comment marker.
- Đổi tên declaration.
- Thay đổi nội dung multiline string.

### Recompute toàn bộ

Với file nhỏ, có thể tính lại toàn bộ folding ranges sau mỗi thay đổi. Cách này đơn giản và ít lỗi state hơn.

### Incremental update

Với file lớn, editor có thể tính lại vùng bị ảnh hưởng. Parser incremental hoặc syntax tree incremental cung cấp node đã thay đổi để fold provider chỉ cập nhật range liên quan.

Một chiến lược:

~~~text
Document edit
    |
    v
Update text snapshot
    |
    v
Incremental lex / parse
    |
    v
Find changed syntax nodes
    |
    v
Recompute affected fold ranges
    |
    v
Map previous folding state
    |
    v
Publish ranges for current version
~~~

Incremental update cần xử lý thay đổi làm ảnh hưởng cấu trúc ở xa vị trí sửa. Ví dụ, xóa một END có thể khiến nhiều block phía sau trở thành con của block trước. Chỉ cập nhật một vài dòng gần edit sẽ không đủ nếu grammar có cấu trúc lồng.

### Giữ trạng thái khi range thay đổi

Nếu một range đổi từ dòng 10-20 thành 10-22, editor có thể giữ trạng thái folded nếu identity của node vẫn giống. Nếu node bị thay thế hoặc mất, state cũ cần được loại bỏ.

Không nên giữ folded state chỉ dựa trên vị trí cũ khi cấu trúc đã đổi hoàn toàn. Điều đó có thể khiến một vùng không liên quan bị ẩn.

### Đồng bộ với diagnostics và outline

Fold ranges, diagnostics và outline thường được tạo từ cùng document snapshot. Cần đảm bảo chúng tham chiếu cùng version để không xuất hiện marker ở vị trí sai hoặc outline trỏ đến declaration đã bị xóa.

## Hiệu năng và khả năng mở rộng

Folding thường nhẹ hơn parsing, nhưng một provider kém hiệu quả có thể làm editor chậm, đặc biệt với file lớn hoặc DSL có nhiều node lồng nhau.

### Giảm công việc trên UI thread

Không nên chạy parse toàn bộ hoặc duyệt graph lớn trên UI thread khi người dùng đang gõ. Có thể dùng language server hoặc worker background, cancellation và debounce phù hợp.

### Giới hạn số range

Một document có thể có hàng trăm nghìn block nhỏ. Editor nên có giới hạn số range được công bố hoặc chiến lược chỉ tạo range cho những construct hữu ích.

### Tránh quét văn bản lặp lại

Nếu parser hoặc syntax tree đã có source span, fold provider nên tái sử dụng chúng thay vì quét lại toàn bộ document để tìm keyword và delimiter.

### Cache theo document snapshot

Kết quả folding có thể được cache theo document version và language configuration. Cache phải invalidation khi nội dung, grammar, marker config hoặc parser state thay đổi.

### Cancellation và stale result

Nếu người dùng gõ nhanh, request folding cũ có thể trở nên vô ích. Provider nên hỗ trợ cancellation hoặc kiểm tra version trước khi publish. Kết quả stale không được ghi đè kết quả mới.

### Tránh range quá nhỏ

Các range chỉ 2 dòng hoặc một biểu thức ngắn có thể tạo quá nhiều marker mà ít giá trị. Có thể đặt ngưỡng tối thiểu theo loại construct, nhưng cần cho phép override khi người dùng có nhu cầu.

## Trải nghiệm người dùng và khả năng tiếp cận

Folding là một thay đổi trực quan có thể ảnh hưởng khả năng định hướng trong tài liệu. Thiết kế cần làm cho trạng thái rõ ràng và không làm người dùng mất thông tin.

### Thể hiện trạng thái rõ

Người dùng cần nhận ra vùng nào đang đóng, vùng nào có thể mở và nội dung nào bị ẩn. Placeholder nên đủ rõ, ví dụ dấu ba chấm, số lượng action hoặc số rule lồng nhau.

### Không phụ thuộc màu sắc

Marker nên dùng hình dạng hoặc biểu tượng khác nhau cho trạng thái expanded và collapsed. Theme sáng/tối và độ tương phản cao cần hiển thị được.

### Hỗ trợ bàn phím

Mọi thao tác quan trọng cần có thể truy cập bằng bàn phím. Người dùng cần có thể di chuyển đến fold range, toggle và mở lại mà không cần chuột.

### Screen reader

Gutter marker và placeholder nên có accessible label, chẳng hạn "Collapse rule VIP discount" hoặc "Expand rule VIP discount". Trạng thái expanded/collapsed cần được thông báo qua accessibility API của editor.

### Giữ dòng và cột có ý nghĩa

Sau khi fold, số dòng có thể thay đổi theo cách hiển thị. Cần phân biệt document line number với visual line number. Diagnostics và source location vẫn phải dựa trên vị trí trong document gốc.

### Không che lỗi cần sửa

Nếu diagnostics nằm trong vùng đang thu gọn, editor có thể hiển thị badge hoặc marker cảnh báo ở dòng mở. Người dùng nên biết vùng đang đóng có lỗi bên trong và có thể mở nhanh để xem.

### Placeholder không làm sai source

Placeholder chỉ là presentation layer. Copy, save, search và compiler phải dùng source text đầy đủ theo semantics editor. Khi copy vùng đã fold, sản phẩm cần có hành vi nhất quán: thường là copy toàn bộ source được chọn, không copy dấu ba chấm hiển thị.

## Folding trong tài liệu lớn và nhiều file

Một project DSL có thể gồm nhiều module và file. Folding state nên được quản lý theo từng document, còn navigation giữa file được xử lý bởi workspace services.

Một số vấn đề:

- Một file được mở ở nhiều editor view.
- Một document được chỉnh sửa từ nhiều client.
- File được reload từ disk.
- Module được sinh tự động.
- Một file chứa generated region.
- Include hoặc macro tạo nội dung từ file khác.

Nếu một source file được include vào nhiều nơi, fold state nên gắn với document nguồn chứ không phải vị trí expanded của nó trong từng consumer. Nếu editor hiển thị virtual document sau expansion, cần source mapping để folding có thể trỏ về đúng tài liệu.

Với generated code, editor có thể cho phép fold nhưng khóa chỉnh sửa hoặc hiển thị cảnh báo. Không nên nhầm folding với read-only hoặc generated-region protection.

## Tương tác với formatter, search và selection

Folding phải phối hợp với các tính năng editor khác.

### Formatter

Formatter có thể thay đổi indentation và số dòng. Sau format, fold ranges cần được tính lại và state cũ được ánh xạ sang node tương ứng.

Nếu formatter chỉ thay whitespace nhưng AST identity giữ nguyên, folding state có thể được bảo toàn theo node identity.

### Search và replace

Search có thể tìm thấy nội dung bên trong vùng đã thu gọn. Editor cần quyết định khi người dùng chọn kết quả:

- Tự động mở vùng chứa kết quả.
- Hiển thị highlight trong vùng đóng.
- Đưa con trỏ đến vị trí và mở ancestor cần thiết.

Replace có thể thay đổi cấu trúc hoặc số dòng, vì vậy cần cập nhật range sau khi áp dụng edit.

### Selection và copy

Selection có thể đi qua vùng folded. Editor nên xác định selection là theo document text hay theo phần hiển thị. Copy cần có semantics ổn định và không làm mất nội dung bị ẩn.

### Diff và merge

Diff view có thể fold các block không thay đổi để tập trung vào phần khác biệt. Trong trường hợp này, folding có thể dựa trên diff region hoặc AST structure. Cần phân biệt fold state của editor thông thường với collapsed unchanged regions trong diff view.

## Folding cho comment marker và generated region

Một số DSL project dùng marker để nhóm vùng code hoặc đánh dấu nội dung được sinh.

Ví dụ:

~~~text
// <editor-fold desc="Generated mappings">
MAP Customer to CustomerRecord
  ...
END

MAP Order to OrderRecord
  ...
END
// </editor-fold>
~~~

Editor cần quy định marker syntax theo language configuration. Marker có thể hỗ trợ nested regions, nhưng phải xác định cách xử lý marker mở không có marker đóng, marker đóng không có marker mở và marker lồng sai thứ tự.

Với generated region, folding chỉ làm vùng ngắn hơn trên màn hình. Nếu sản phẩm cần ngăn sửa vùng generated, đó là một tính năng riêng với policy rõ ràng.

## Các lỗi thường gặp khi triển khai folding

### Dùng regex trên toàn bộ văn bản

Regex đơn giản có thể nhận nhầm keyword trong string, comment hoặc multiline literal. Nên dùng lexer, parser hoặc state machine hiểu trạng thái ngôn ngữ.

### Không xử lý vùng lồng nhau

Nếu provider chỉ tạo range ngoài cùng, người dùng không thể fold sâu theo từng block. Nếu range con bị mất khi cha đóng, trạng thái con có thể không được khôi phục khi mở cha.

### Tạo range chồng lấn không hợp lệ

Các provider có thể tạo range giao nhau mà không chứa nhau. Điều này gây marker sai, placeholder bất thường hoặc thao tác fold không đoán được. Cần chuẩn hóa và kiểm tra range theo một quy tắc xác định.

### Không cập nhật sau edit

Range dựa trên dòng cũ có thể trỏ đến nội dung khác sau khi chèn hoặc xóa dòng. Cần gắn range với document version và tính lại hoặc ánh xạ state có kiểm soát.

### Làm mất folding state sau formatter

Nếu chỉ lưu line number, format có thể làm trạng thái fold nhảy sang block khác. Dùng node identity hoặc anchor khi có thể.

### Fold cả vùng một dòng

Marker dư thừa làm gutter rối và tăng thao tác. Thường chỉ tạo range khi có phần nội dung nhiều dòng có thể ẩn.

### Bỏ qua lỗi trong vùng folded

Người dùng có thể không biết một block đã đóng đang chứa lỗi. Có thể hiển thị diagnostic badge hoặc thông tin lỗi ở header.

### Trộn vị trí byte và vị trí editor

Unicode có thể làm byte offset khác code point và UTF-16 code unit. Cần chuyển đổi đúng giữa source span và API editor.

### Chặn giao diện khi tính range

Parse hoặc duyệt cây lớn trên UI thread có thể làm editor giật. Dùng background computation, cancellation và cache theo version.

### Ghi placeholder vào file nguồn

Dấu ba chấm hiển thị không phải nội dung nguồn. Nếu ghi placeholder vào file, chương trình có thể bị thay đổi hoặc hỏng. Folding phải là presentation state.

## Ví dụ thiết kế fold provider cho DSL

Giả sử DSL có các construct:

~~~text
MODULE name
  RULE "name"
    WHEN expression
    THEN
      actions
    END
  END

  FUNCTION name(args)
    statements
  END
END
~~~

Một provider có thể chọn các node:

- ModuleDeclaration.
- RuleDeclaration.
- FunctionDeclaration.
- ActionBlock.
- IfBlock.
- MultiLineComment.
- MultiLineCollection.

Pseudocode:

~~~text
function provideFoldingRanges(document, syntaxTree):
    ranges = []

    for node in syntaxTree.walk():
        if node.kind not in foldableKinds:
            continue

        if node.isIncomplete and not allowIncompleteFolds:
            continue

        start = node.foldStart
        end = node.foldEnd

        if end.line <= start.line:
            continue

        ranges.add(
            FoldRange(
                start = start,
                end = end,
                kind = classify(node),
                source = "syntax"
            )
        )

    ranges.addAll(commentProvider(document))
    ranges.addAll(regionMarkerProvider(document))

    return normalizeAndDeduplicate(ranges)
~~~

Hàm normalizeAndDeduplicate có thể:

1. Loại range ngoài document.
2. Chuẩn hóa quy ước end-exclusive/end-inclusive.
3. Loại range một dòng nếu không hỗ trợ.
4. Sắp xếp theo start rồi end.
5. Loại duplicate.
6. Xử lý overlap không hợp lệ.
7. Giữ hierarchy cha-con.
8. Áp dụng giới hạn số range của client.

Pseudocode này mô tả kiến trúc; implementation thực tế cần tuân theo API editor hoặc LSP được sử dụng.

### Kiểm tra marker region

Một provider marker có thể nhận comment token từ lexer:

~~~text
for token in commentTokens:
    if token.matchesRegionStart():
        pushRegion(token.position)

    if token.matchesRegionEnd():
        if stack is empty:
            reportUnmatchedEnd(token)
        else:
            start = stack.pop()
            emitRange(start, token.position)

for start in stack:
    reportUnclosedRegion(start)
~~~

Stack hỗ trợ region lồng nhau. Nếu DSL không cho phép nested region, provider có thể báo marker lồng là không hợp lệ hoặc áp dụng quy tắc ưu tiên được công bố.

## Kiểm thử code folding

Folding cần được kiểm tra ở nhiều cấp: xác định range, state, cập nhật theo edit và tương tác editor.

### Unit test cho fold provider

Test các trường hợp:

- Declaration nhiều dòng tạo range.
- Declaration một dòng không tạo range nếu policy loại bỏ.
- Block lồng tạo range cha và con.
- Comment nhiều dòng được nhận diện.
- String chứa từ khóa không tạo range giả.
- Marker region tạo range đúng.
- Marker không đóng tạo diagnostic hoặc fallback đúng.
- Range không vượt document boundary.
- Duplicate range được loại bỏ.
- Overlap được xử lý theo policy.

### Test với cú pháp không hoàn chỉnh

Editor thường nhận source đang nhập dở. Cần test:

~~~text
RULE "Incomplete"
WHEN customer.active
THEN
  applyDiscount()
~~~

và các trường hợp:

- Thiếu END.
- Thiếu dấu đóng ngoặc.
- Comment block chưa đóng.
- String multiline chưa kết thúc.
- Marker region chỉ có phần mở.
- Parser recovery tạo node synthetic.

Provider cần tạo range an toàn hoặc bỏ range theo policy; không được tạo vùng vượt ngoài document.

### Test incremental update

Tạo range ban đầu, sau đó:

- Chèn dòng trước range.
- Xóa dòng bên trong range.
- Thêm hoặc xóa delimiter.
- Di chuyển declaration.
- Đổi tên node.
- Thay marker.
- Xóa phần tử cha.

So sánh kết quả folding mới với full recomputation trên cùng document. Folding state nên được giữ cho node còn identity và loại bỏ cho node đã biến mất.

### Test giao diện và accessibility

Kiểm tra:

- Gutter marker có đúng trạng thái.
- Click toggle đúng vùng.
- Fold All và Unfold All hoạt động.
- Fold Level không làm mất state ngoài dự kiến.
- Keyboard command có thể dùng.
- Screen reader nhận label và trạng thái.
- Diagnostics bên trong vùng folded vẫn được biểu thị.
- Copy và search không làm mất nội dung nguồn.

### Test hiệu năng

Dùng tài liệu có số lượng declaration và block lồng khác nhau. Đo thời gian tạo range, thời gian cập nhật incremental, số range trả về và mức sử dụng bộ nhớ.

Nên có trường hợp xấu như hàng nghìn region, nesting sâu, comment dài, marker sai và nhiều edit liên tục. Kiểm tra cancellation và bảo đảm kết quả cũ không ghi đè kết quả mới.

## Quy trình triển khai folding cho một DSL editor

Một quy trình có thể đi theo các bước:

1. **Đọc grammar và cấu trúc tài liệu:** xác định declaration, block, comment, delimiter và vùng nhiều dòng.
2. **Xác định trải nghiệm:** chọn construct nào có thể fold, có giữ header/footer không và placeholder hiển thị gì.
3. **Chọn nguồn range:** AST/CST, indentation, delimiter, marker hoặc kết hợp.
4. **Định nghĩa fold range contract:** start/end, line/column, end convention, kind và collapsed text.
5. **Xây provider:** tạo range từ syntax tree hoặc token stream, hợp nhất provider và loại duplicate.
6. **Xử lý nesting:** bảo đảm hierarchy cha-con và chính sách overlap rõ ràng.
7. **Tích hợp editor hoặc LSP:** publish range theo document version và capability.
8. **Quản lý state:** lưu expanded/collapsed state và ánh xạ sau edit hoặc format.
9. **Tối ưu:** background work, cache, cancellation và giới hạn range.
10. **Hỗ trợ accessibility:** keyboard, labels, screen reader và trạng thái trực quan.
11. **Kiểm thử:** syntax, marker, incomplete source, incremental edit, UX và hiệu năng.
12. **Theo dõi và điều chỉnh:** thu thập lỗi range và phản hồi sử dụng để cải thiện các construct được hỗ trợ.

Cần bắt đầu từ những vùng có cấu trúc rõ như module, rule, function và block. Sau đó có thể bổ sung comment, collection, multiline expression và region marker dựa trên nhu cầu thực tế.

## Kết luận

Thu gọn mã là tính năng trình bày cho phép ẩn tạm thời các vùng văn bản trong DSL editor để người dùng tập trung vào cấu trúc quan trọng. Fold range có thể được xác định từ AST/CST, indentation, delimiter, comment marker hoặc heuristic; với DSL có grammar rõ, syntax-aware folding thường cung cấp kết quả chính xác và ổn định hơn.

Một triển khai tốt cần mô hình hóa range và hierarchy lồng nhau, tách folding state khỏi source text, cập nhật range theo document version, giữ trạng thái khi chỉnh sửa, hỗ trợ lệnh và accessibility, đồng thời không làm mất diagnostics bên trong vùng đã đóng. Khi tích hợp với parser hoặc language server, cần quản lý source position, cancellation, stale result và giới hạn số range.

Folding chỉ thay đổi cách editor hiển thị nội dung. Source đầy đủ vẫn được lưu, phân tích và biên dịch như bình thường. Với fold provider có hợp đồng rõ, xử lý range nhất quán và kiểm thử incremental phù hợp, tính năng này giúp tài liệu DSL lớn dễ đọc, dễ điều hướng và thuận tiện hơn khi bảo trì.
