# Gợi ý hoàn thành

Trong một trình soạn thảo dành cho ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), **gợi ý hoàn thành (code completion)** là tính năng đề xuất những từ khóa, tên, biểu thức, giá trị hoặc đoạn mã phù hợp với vị trí con trỏ. Khi người dùng đang nhập, editor phân tích nội dung hiện tại và đưa ra danh sách lựa chọn có thể chèn vào tài liệu. Người dùng có thể chọn một gợi ý, tiếp tục gõ để lọc danh sách hoặc dùng phím điều hướng để chấp nhận mục phù hợp.

Ví dụ, một DSL mô tả chính sách giao hàng có thể có:

~~~text
policy giao_hang {
    area =
}
~~~

Khi con trỏ đứng sau dấu bằng, editor có thể gợi ý các giá trị hợp lệ của kiểu DeliveryArea như NOI_THANH và NGOAI_THANH. Nếu người dùng gõ dấu chấm sau một đối tượng đơn hàng, editor có thể gợi ý các thuộc tính của đối tượng đó, chẳng hạn tong_tien, trang_thai hoặc ngay_tao.

Gợi ý hoàn thành giúp người dùng khám phá cú pháp và mô hình miền ngay trong lúc viết. Nó giảm lỗi chính tả, tránh phải nhớ mọi tên thuộc tính và giúp người mới học DSL hiểu được những lựa chọn có thể dùng tại từng vị trí. Để hữu ích, danh sách gợi ý phải dựa trên ngữ cảnh cú pháp và ngữ nghĩa, có thứ tự hợp lý, chèn văn bản đúng phạm vi và cập nhật đủ nhanh để không làm gián đoạn thao tác nhập.

## 1. Gợi ý hoàn thành trong DSL editor là gì?

Code completion là dịch vụ phân tích vị trí con trỏ và đề xuất những nội dung có thể xuất hiện tại vị trí đó. Nó thường được gọi là autocomplete hoặc IntelliSense, nhưng trong một editor hoàn chỉnh, tính năng này có thể bao gồm nhiều loại đề xuất khác nhau.

Một danh sách gợi ý có thể chứa:

- Từ khóa và toán tử được grammar cho phép.
- Tên biến, thuộc tính, hàm, lớp, enum hoặc tài nguyên trong scope hiện tại.
- Thành viên của một đối tượng sau phép truy cập thành viên.
- Giá trị enum hoặc literal phù hợp với kiểu đang mong đợi.
- Tên module, package hoặc symbol cần import.
- Snippet tạo sẵn một cấu trúc DSL có nhiều dòng.
- Tên trường hoặc giá trị phù hợp với một schema.
- Các hành động như thêm import hoặc tạo khai báo còn thiếu.

### 1.1. Completion khác với gợi ý sửa lỗi

Completion đề xuất nội dung có thể được viết tiếp tại vị trí hiện tại. Quick fix đề xuất hành động sửa một vấn đề đã được phát hiện. Hai tính năng có thể dùng chung symbol index hoặc semantic model, nhưng mục đích khác nhau.

Ví dụ, khi người dùng gõ một tên chưa tồn tại, completion có thể gợi ý các tên gần giống. Một quick fix có thể thay thế tên sai bằng tên đã chọn. Completion bổ sung nội dung; quick fix thay đổi nội dung để khắc phục chẩn đoán.

### 1.2. Completion khác với tìm kiếm toàn văn

Tìm kiếm toàn văn trả về những chuỗi khớp trong tài liệu hoặc workspace. Completion lọc theo những gì có thể hợp lệ tại vị trí con trỏ. Nếu người dùng đang khai báo kiểu, editor nên ưu tiên các kiểu hợp lệ thay vì mọi chuỗi có tên giống nhau trong project.

### 1.3. Completion khác với sinh mã

Sinh mã tạo artifact từ model hoặc template. Completion tạo một đề xuất tương tác ngay trong tài liệu đang chỉnh sửa. Một completion item có thể chèn snippet nhiều dòng, nhưng nó vẫn là lựa chọn cục bộ trong editor, không phải quy trình sinh toàn bộ project.

## 2. Mục tiêu của gợi ý hoàn thành

Một tính năng completion tốt cần phục vụ cả tốc độ nhập và khả năng hiểu ngôn ngữ.

### 2.1. Giảm ghi nhớ cú pháp

Người dùng không cần nhớ chính xác tên mọi keyword hoặc thứ tự tham số. Khi nhập một phần từ khóa, editor hiển thị những lựa chọn phù hợp để người dùng chọn.

### 2.2. Khám phá mô hình miền

Completion có thể giới thiệu những thuộc tính, hành động và giá trị mà người dùng chưa biết. Khi viết một đối tượng, danh sách thành viên cho biết mô hình đang cung cấp những thao tác nào.

### 2.3. Giảm lỗi nhập liệu

Đề xuất tên đã được phân giải giúp tránh lỗi chính tả, sai chữ hoa/thường và tham chiếu đến symbol không tồn tại.

### 2.4. Hướng dẫn theo ngữ cảnh

Ở mỗi vị trí, editor chỉ nên đưa ra nhóm lựa chọn có ý nghĩa. Sau từ khóa khai báo, có thể gợi ý identifier; sau dấu hai chấm, có thể gợi ý kiểu; sau dấu bằng, có thể gợi ý biểu thức hoặc literal theo kiểu mong đợi.

### 2.5. Tăng khả năng tiếp cận DSL

Người dùng chuyên môn miền có thể không quen với cú pháp lập trình. Completion giúp họ làm việc bằng các khái niệm nghiệp vụ quen thuộc và học cấu trúc DSL thông qua ví dụ nhỏ ngay tại vị trí cần thiết.

### 2.6. Hỗ trợ mã chưa hoàn chỉnh

Trong lúc gõ, tài liệu thường ở trạng thái chưa hợp lệ. Completion cần hoạt động ngay cả khi thiếu dấu ngoặc, thiếu biểu thức hoặc đang nhập dở một từ khóa. Đây là yêu cầu quan trọng của editor tương tác.

## 3. Phân loại gợi ý hoàn thành

Các loại completion khác nhau cần nguồn dữ liệu và cách xếp hạng khác nhau.

| Loại gợi ý | Ví dụ | Nguồn thường dùng |
|---|---|---|
| Keyword completion | policy, workflow, task | Grammar và danh sách keyword |
| Symbol completion | ten_bien, DonHang | Scope và symbol table |
| Member completion | don_hang.tong_tien | Kiểu của receiver |
| Type completion | Money, Duration, OrderId | Type registry |
| Enum completion | NOI_THANH, NGOAI_THANH | Enum definition |
| Function completion | round(), contains() | Function registry |
| Named argument | timeout, retries | Chữ ký hàm hoặc task |
| Path completion | modules/orders.dsl | Workspace và filesystem policy |
| Snippet completion | khai báo policy hoàn chỉnh | Snippet catalog |
| Import completion | module hoặc symbol cần import | Module index |

### 3.1. Keyword completion

Keyword completion đưa ra từ khóa hợp lệ tại vị trí hiện tại. Danh sách có thể phụ thuộc parser state. Ví dụ, ở cấp file có thể gợi ý service, policy hoặc workflow; bên trong một biểu thức có thể gợi ý toán tử hoặc literal Boolean.

### 3.2. Symbol completion

Symbol completion tìm biến, hàm, lớp, tài nguyên và khai báo trong scope hiện tại. Nó cần tôn trọng visibility, namespace, import và shadowing.

### 3.3. Member completion

Sau dấu chấm, editor xác định kiểu của biểu thức bên trái rồi liệt kê thành viên có thể truy cập. Nếu receiver là Order, editor có thể gợi ý id, tong_tien và trang_thai.

### 3.4. Type-directed completion

Nếu vị trí đang mong kiểu Money, completion có thể ưu tiên literal tiền tệ, biến có kiểu Money hoặc lời gọi hàm trả về Money. Type-directed completion hữu ích khi DSL có hệ thống kiểu phong phú.

### 3.5. Snippet completion

Snippet là đoạn mẫu có placeholder hoặc tab stop. Ví dụ khi chọn snippet policy, editor chèn khung khai báo có sẵn và đưa con trỏ lần lượt đến tên policy, điều kiện và nội dung.

### 3.6. Contextual value completion

Một trường có thể lấy giá trị từ danh mục miền hoặc dữ liệu cấu hình. Ví dụ thuộc tính country có thể gợi ý mã quốc gia; thuộc tính status có thể gợi ý các trạng thái được khai báo trong schema.

## 4. Ngữ cảnh tại vị trí con trỏ

Completion phụ thuộc rất lớn vào thông tin editor thu thập được tại vị trí con trỏ.

### 4.1. Cursor position

Editor cần biết offset hoặc vị trí dòng/cột chính xác. Vị trí này xác định token hiện tại, biểu thức đang nhập và vùng văn bản sẽ được thay thế khi người dùng chấp nhận gợi ý.

### 4.2. Lexical context

Lexer có thể cho biết con trỏ đang ở identifier, string literal, comment, number hay khoảng trắng. Nếu con trỏ ở trong comment, completion keyword thông thường có thể không phù hợp; nếu ở trong string, cần dùng quy tắc riêng cho nội dung chuỗi.

### 4.3. Syntactic context

Parser hoặc parser state giúp xác định nonterminal hiện tại. Ví dụ editor có thể biết đang ở:

- Cấp khai báo module.
- Bên trong một policy block.
- Danh sách tham số.
- Vị trí cần một identifier.
- Vị trí cần một expression.
- Phần khai báo kiểu hoặc annotation.

### 4.4. Semantic context

Semantic model cung cấp symbol, type, scope, import và quan hệ đã phân giải. Nó giúp editor biết tên nào tồn tại, thành viên nào truy cập được và biểu thức nào phù hợp.

### 4.5. Expected token và expected type

Parser có thể suy ra tập token có thể xuất hiện tiếp theo. Type checker hoặc expression analyzer có thể suy ra kiểu kết quả mong đợi. Hai thông tin này giúp lọc candidate trước khi xếp hạng.

### 4.6. Prefix đang nhập

Editor thường xác định một prefix nằm trước con trỏ để lọc gợi ý. Ví dụ với NO, candidate NOI_THANH có thể khớp. Prefix có thể là identifier một phần, tên qualified hoặc một đoạn path.

### 4.7. Selection và replacement range

Người dùng có thể chọn sẵn một đoạn văn bản. Completion item cần xác định vùng thay thế chính xác để chấp nhận gợi ý không làm mất phần văn bản lân cận.

## 5. Dùng grammar để lọc gợi ý

Grammar mô tả những cấu trúc cú pháp được phép. Completion có thể khai thác grammar để xác định loại token hoặc production phù hợp tại vị trí hiện tại.

### 5.1. Expected token set

Với parser dự đoán, tập token mong đợi có thể được suy ra từ trạng thái parser, FIRST/FOLLOW hoặc thông tin parser state. Editor dùng tập đó để lọc keyword và dấu phân cách.

Ví dụ:

~~~text
policy giao_hang {
    <cursor>
}
~~~

Ở vị trí này, grammar có thể cho phép một khai báo thành viên, dấu đóng block hoặc một comment. Danh sách gợi ý nên phản ánh các lựa chọn đó.

### 5.2. Completion trong danh sách

Sau dấu phẩy trong danh sách tham số, parser có thể tiếp tục mong một tham số khác. Trước dấu đóng ngoặc, danh sách có thể đã hoàn tất. Completion nên tránh gợi ý một tham số mới khi vị trí hiện tại đã là vị trí kết thúc hợp lệ, trừ khi người dùng chủ động yêu cầu.

### 5.3. Completion trong biểu thức

Trong biểu thức, candidate phụ thuộc toán hạng đã có và vị trí toán tử. Sau một toán tử so sánh, editor có thể gợi ý biểu thức cùng kiểu tương thích; sau một biểu thức Boolean hoàn chỉnh, editor có thể gợi ý toán tử logic hoặc dấu kết thúc theo grammar.

### 5.4. Grammar và parser recovery

Editor thường parse tài liệu chưa hoàn chỉnh bằng recovery. Completion không nên phụ thuộc vào việc toàn bộ AST hợp lệ. Nó có thể dùng parser state gần con trỏ, partial tree hoặc một completion parser riêng để xác định context.

### 5.5. Không chỉ dựa vào từ khóa gần nhất

Chọn gợi ý chỉ dựa trên token ngay trước con trỏ dễ sai khi có biểu thức lồng nhau hoặc cú pháp multiline. Parser state và delimiter stack cung cấp ngữ cảnh đáng tin cậy hơn.

## 6. Completion dựa trên scope và symbol table

Scope xác định những symbol nào có thể được tham chiếu tại vị trí hiện tại.

### 6.1. Lexical scope

Trong scope lồng nhau, khai báo ở scope gần có thể che khuất khai báo ở scope ngoài. Completion nên ưu tiên symbol gần nhất theo quy tắc name resolution.

~~~text
let trang_thai = "MOI_TAO"

workflow xu_ly {
    let trang_thai = "DANG_XU_LY"
    log(trang_thai)
}
~~~

Trong lời gọi log bên trong workflow, completion nên đưa ra biến trang_thai cục bộ trước biến cùng tên ở scope ngoài.

### 6.2. Visibility

Symbol private hoặc internal không nên được gợi ý từ module không có quyền truy cập. Public API có thể được đề xuất qua import hoặc namespace phù hợp.

### 6.3. Imports và namespaces

Completion có thể gợi ý symbol đã import, symbol trong namespace hiện tại hoặc symbol có thể được import. Nếu chọn symbol chưa import, editor có thể thêm import tự động như một phần của completion edit.

### 6.4. Shadowing

Khi nhiều symbol cùng tên tồn tại, editor cần áp dụng đúng quy tắc phân giải. Có thể hiển thị thông tin phân biệt như module, loại symbol hoặc scope để người dùng chọn đúng.

### 6.5. Workspace index

Để gợi ý symbol từ file khác, language server có thể xây dựng index của project. Index cần được cập nhật khi file thay đổi và chỉ chứa symbol thuộc workspace hoặc dependency được phép.

### 6.6. Symbol chưa được phân giải

Nếu tài liệu chưa hoàn chỉnh hoặc dependency chưa được tải, một số symbol có thể ở trạng thái unknown. Completion có thể đưa ra gợi ý hạn chế nhưng cần phân biệt candidate đã xác thực với candidate chỉ được suy đoán từ tên.

## 7. Completion dựa trên kiểu dữ liệu

Type-aware completion dùng hệ thống kiểu để đề xuất giá trị phù hợp.

### 7.1. Expected type

Khi gán giá trị cho thuộc tính:

~~~text
base_fee: Money = <cursor>
~~~

Editor biết biểu thức bên phải cần kiểu Money. Candidate có thể gồm biến kiểu Money, literal tiền tệ, constructor Money hoặc hàm trả về Money.

### 7.2. Member access

Với:

~~~text
don_hang.<cursor>
~~~

Nếu don_hang có kiểu Order, completion liệt kê các thành viên public của Order. Nó có thể nhóm field, method và computed property.

### 7.3. Function arguments

Khi nhập đối số, editor có thể dùng chữ ký hàm để gợi ý tham số tiếp theo, kiểu giá trị và tên tham số:

~~~text
round(value = <cursor>, scale = 2)
~~~

Nếu value mong Decimal, completion ưu tiên biểu thức Decimal.

### 7.4. Generic type

Với kiểu generic như List<Order>, completion trong dấu ngoặc nhọn hoặc vị trí type argument cần gợi ý các kiểu phù hợp với constraint của type parameter.

### 7.5. Union và nullable type

Nếu expected type là một union, candidate có thể thuộc bất kỳ nhánh hợp lệ nào. Nếu kiểu nullable, editor có thể gợi ý null hoặc toán tử xử lý null khi DSL hỗ trợ.

### 7.6. Type inference chưa hoàn tất

Trong lúc gõ, kiểu của biểu thức có thể chưa xác định. Completion nên có fallback dựa trên syntax và scope, rồi cập nhật khi semantic analysis hoàn tất. Không nên loại bỏ mọi gợi ý chỉ vì một phần biểu thức đang thiếu.

## 8. Completion cho các giá trị miền

DSL thường có vocabulary cụ thể của miền như trạng thái, loại giao dịch, vùng, đơn vị, quyền hoặc tên tài nguyên.

### 8.1. Enum

~~~text
enum DeliveryArea {
    NOI_THANH
    NGOAI_THANH
}

policy giao_hang {
    area: DeliveryArea = <cursor>
}
~~~

Completion có thể gợi ý hai giá trị enum đã khai báo. Khi người dùng nhập prefix NGO, candidate NGOAI_THANH được ưu tiên.

### 8.2. Literal có đơn vị

Với kiểu Duration, editor có thể gợi ý literal theo đơn vị hợp lệ như milliseconds, seconds, minutes hoặc hours. Nếu kiểu yêu cầu Money<VND>, completion có thể đưa ví dụ literal có currency tương ứng.

### 8.3. Registry và catalog

Một số giá trị đến từ registry bên ngoài như tên queue, cloud region, database schema hoặc loại thiết bị. Completion cần truy cập catalog qua một abstraction có cache và quyền rõ ràng.

### 8.4. Giá trị động

Nếu danh sách giá trị thay đổi theo dữ liệu runtime, editor có thể gợi ý giá trị gần đây hoặc giá trị mẫu. Cần phân biệt dữ liệu mẫu với tập giá trị được bảo đảm hợp lệ.

### 8.5. Filter theo điều kiện miền

Một trạng thái có thể chỉ hợp lệ khi đối tượng ở một trạng thái trước đó. Completion có thể lọc theo trạng thái hiện tại nếu thông tin này có sẵn và đáng tin cậy. Nếu không, nên hiển thị candidate cùng điều kiện áp dụng thay vì giả định trạng thái.

## 9. Ranking và sắp xếp candidate

Một vị trí có thể có hàng chục hoặc hàng nghìn candidate. Ranking quyết định mục nào xuất hiện ở đầu danh sách.

### 9.1. Exact prefix match

Candidate bắt đầu bằng prefix thường được ưu tiên hơn candidate chỉ chứa chuỗi đó ở giữa tên. Exact match và case-sensitive match có thể được xếp cao hơn fuzzy match.

### 9.2. Context relevance

Candidate đúng kiểu, đúng scope và đúng grammar cần được ưu tiên. Một hàm cùng tên nhưng không khả dụng tại vị trí hiện tại không nên đứng đầu chỉ vì tên khớp.

### 9.3. Recency và frequency

Editor có thể cân nhắc symbol được dùng gần đây hoặc thường xuyên. Tuy nhiên, recency không nên vượt qua ràng buộc cú pháp, kiểu hoặc quyền truy cập.

### 9.4. Proximity

Symbol trong scope gần có thể được ưu tiên hơn symbol từ module xa. Candidate cùng file hoặc cùng block thường dễ hiểu hơn candidate ở nơi khác.

### 9.5. Relevance score

Một hệ thống có thể tính điểm tổng hợp:

~~~text
score =
    prefix_match_weight
  + syntax_context_weight
  + type_match_weight
  + scope_proximity_weight
  + usage_frequency_weight
~~~

Đây là mô hình khái niệm. Trọng số và cách kết hợp phải được hiệu chỉnh bằng hành vi thực tế, không nên coi công thức minh họa là chuẩn bắt buộc.

### 9.6. Stable ordering

Nếu nhiều candidate có điểm tương đương, nên dùng tie-breaker ổn định như loại symbol, tên hoặc vị trí khai báo. Danh sách nhảy thứ tự liên tục khi người dùng gõ sẽ gây khó chọn.

### 9.7. Không quá ưu tiên popularity

Candidate phổ biến có thể không phù hợp với project hiện tại. Context và tính hợp lệ luôn quan trọng hơn số lần sử dụng toàn cục.

## 10. Fuzzy matching và lọc theo prefix

Người dùng có thể nhập thiếu ký tự, sai một chữ hoặc dùng kiểu chữ khác. Fuzzy matching giúp tìm candidate gần đúng.

### 10.1. Prefix matching

Nếu prefix là don, candidate DonHang hoặc don_hang có thể được tìm thấy tùy quy tắc case và naming convention.

### 10.2. Subsequence matching

Subsequence matching cho phép các ký tự prefix xuất hiện theo đúng thứ tự nhưng không cần liền nhau. Ví dụ dHg có thể khớp DonHang. Cách này hữu ích khi tên dài nhưng có thể tạo nhiều kết quả bất ngờ.

### 10.3. Camel-case matching

Với tên camelCase hoặc PascalCase, editor có thể khớp chữ cái đầu của từng thành phần. Ví dụ dH có thể tìm DonHang.

### 10.4. Typo tolerance

Edit distance hoặc thuật toán gần đúng có thể gợi ý tên khi người dùng nhập sai một ký tự. Candidate typo nên được xếp sau các kết quả khớp chính xác.

### 10.5. Case sensitivity

DSL có thể phân biệt hoặc không phân biệt chữ hoa/thường. Completion phải tuân theo semantics của language, đồng thời có thể tìm kiếm không phân biệt case nếu việc đó chỉ ảnh hưởng đến lọc danh sách chứ không thay đổi tên được chèn.

### 10.6. Giới hạn kết quả

Fuzzy matching trên workspace lớn có thể tốn tài nguyên. Nên giới hạn candidate, dùng index và trì hoãn tìm kiếm rộng khi prefix còn quá ngắn.

## 11. Snippet và placeholder

Snippet giúp chèn cấu trúc nhiều phần với các vị trí cần người dùng điền.

### 11.1. Snippet khai báo

Một snippet policy có thể chèn:

~~~text
policy $1:ten_policy {
    area = $2:NOI_THANH
    base_fee = $3:30000 VND
    $0
}
~~~

Ký hiệu tab stop ở trên minh họa ý tưởng; cú pháp thật phụ thuộc editor hoặc giao thức. Người dùng có thể nhảy từ tên policy sang area, base_fee rồi đến vị trí cuối.

### 11.2. Placeholder và tab order

Placeholder nên có thứ tự hợp lý theo cách người dùng hoàn thành cấu trúc. Giá trị mặc định cần hợp lệ theo grammar và kiểu nếu có thể.

### 11.3. Snippet có nhiều dòng

Snippet nhiều dòng cần indentation phù hợp với vị trí chèn. Nếu chèn trong block đã thụt lề, editor nên tính indentation cơ sở để không làm lệch cấu trúc.

### 11.4. Snippet theo context

Một snippet có thể khác nhau tùy loại model. Ví dụ task đồng bộ dữ liệu có thể cần timeout và retry; task tính toán có thể cần input/output type. Completion nên chỉ đưa snippet khi context phù hợp.

### 11.5. Snippet và format-on-type

Sau khi chèn snippet, formatter hoặc indentation engine có thể chuẩn hóa khoảng trắng. Cần bảo đảm tab stop vẫn trỏ đúng vị trí sau khi định dạng.

## 12. Trigger và cách yêu cầu completion

Completion có thể được gọi thủ công hoặc tự động.

### 12.1. Manual invocation

Người dùng nhấn tổ hợp phím completion để yêu cầu danh sách tại vị trí hiện tại. Manual invocation hữu ích khi editor không tự mở danh sách hoặc khi người dùng muốn xem mọi lựa chọn.

### 12.2. Automatic trigger

Editor có thể tự gọi completion sau khi nhập:

- Một phần identifier.
- Dấu chấm để truy cập member.
- Dấu hai chấm sau khai báo kiểu.
- Dấu mở ngoặc khi nhập tham số.
- Một ký tự đặc biệt của DSL.

### 12.3. Trigger characters

Mỗi language server có thể khai báo trigger character. Khi người dùng gõ ký tự đó, client gửi yêu cầu completion. Không nên đăng ký mọi dấu câu làm trigger vì sẽ tạo quá nhiều request và popup gây nhiễu.

### 12.4. Retrigger

Khi danh sách đang mở, một số ký tự tiếp theo có thể khiến server tính lại candidate. Ví dụ người dùng nhập thêm prefix hoặc dấu chấm mở một truy cập thành viên mới.

### 12.5. Debounce

Debounce trì hoãn request trong một khoảng rất ngắn để gom các lần gõ liên tiếp. Khoảng chờ quá dài làm completion chậm; quá ngắn có thể tạo nhiều request dư thừa.

### 12.6. Tôn trọng lựa chọn người dùng

Một số người dùng không muốn popup tự mở liên tục. Editor nên cho phép cấu hình automatic completion, manual invocation và loại trigger.

## 13. Chèn completion item vào tài liệu

Candidate chỉ hữu ích khi được chèn đúng vị trí và đúng nội dung.

### 13.1. Insert text

Một completion item có thể chèn một chuỗi đơn giản như tên symbol hoặc keyword.

### 13.2. Text edit range

Nếu người dùng đã gõ một phần tên, item nên thay thế đúng prefix hiện tại. Ví dụ tài liệu chứa donH và item DonHang; editor thay vùng donH bằng DonHang thay vì nối thêm phần còn lại.

### 13.3. Insert và replace range

Một số giao thức cho phép chỉ định vùng insert khi tiếp tục gõ và vùng replace khi chấp nhận item. Điều này giúp xử lý trường hợp con trỏ nằm giữa identifier hoặc có suffix phía sau.

### 13.4. Commit characters

Commit character là ký tự khiến item đang chọn được chấp nhận và ký tự đó tiếp tục được chèn hoặc xử lý. Ví dụ dấu chấm có thể chấp nhận một tên biến rồi mở completion member tiếp theo. Cần tránh nuốt hoặc nhân đôi ký tự.

### 13.5. Additional text edits

Chọn một symbol có thể cần thêm import hoặc sửa namespace. Completion item có thể chứa các text edit bổ sung ở vị trí khác trong file. Những edit này cần tránh chồng lấn và được áp dụng như một thao tác nhất quán.

### 13.6. Không sửa ngoài phạm vi dự kiến

Completion nên thay đúng đoạn prefix hoặc vùng được chỉ định. Việc xóa thêm whitespace, comment hoặc nội dung bên cạnh có thể làm mất dữ liệu người dùng.

## 14. Thông tin hiển thị cho từng gợi ý

Danh sách chỉ có tên đôi khi không đủ để phân biệt candidate.

### 14.1. Label

Label là tên chính hiển thị trong danh sách, ví dụ tong_tien hoặc retry_count.

### 14.2. Kind

Kind cho biết candidate là keyword, variable, function, class, enum member, property, module hoặc snippet. Icon hoặc nhóm hiển thị có thể dựa trên kind.

### 14.3. Detail

Detail cung cấp thông tin ngắn như kiểu hoặc chữ ký:

~~~text
tong_tien    Money<VND>
round        (value: Decimal, scale: Integer) -> Decimal
~~~

### 14.4. Documentation

Documentation giải thích ý nghĩa, đơn vị, giá trị mặc định hoặc ví dụ sử dụng. Có thể tải tài liệu chi tiết khi người dùng chọn hoặc rê chuột lên candidate để tránh làm chậm danh sách ban đầu.

### 14.5. Sort text và filter text

Sort text cho phép engine sắp xếp candidate theo tiêu chí riêng; filter text cho phép một candidate khớp với nhiều dạng tìm kiếm. Hai trường này có thể khác label hiển thị.

### 14.6. Deprecated và unavailable

Symbol deprecated có thể vẫn xuất hiện để hỗ trợ mã cũ, nhưng cần được đánh dấu và xếp thấp hơn lựa chọn hiện hành. Candidate không truy cập được không nên được trình bày như lựa chọn hợp lệ.

## 15. Tích hợp Language Server Protocol

Language Server Protocol (LSP) chuẩn hóa cách editor client trao đổi với language server. Completion là một trong những dịch vụ chính.

### 15.1. Completion request

Client gửi yêu cầu completion kèm text document URI, vị trí con trỏ và thông tin context. Server trả danh sách completion items hoặc một CompletionList.

### 15.2. Completion item

Một CompletionItem có thể chứa label, kind, detail, documentation, sortText, filterText, insertText, textEdit, additionalTextEdits, commitCharacters và command.

### 15.3. Snippet format

LSP hỗ trợ định dạng snippet trong insertText khi client quảng bá capability tương ứng. Server cần kiểm tra client support trước khi trả snippet syntax.

### 15.4. Resolve completion item

Server có thể trả danh sách gọn trước, rồi bổ sung documentation hoặc detail khi client gọi completionItem/resolve. Cách này giảm chi phí ban đầu với candidate lớn.

### 15.5. Incomplete result

CompletionList có thể đánh dấu isIncomplete để báo danh sách chưa đầy đủ và cần request lại khi prefix thay đổi. Điều này hữu ích khi symbol index lớn hoặc truy vấn từ xa.

### 15.6. Client capabilities

Server cần kiểm tra khả năng client hỗ trợ như snippet, markdown documentation, insert/replace edit và completion item tag. Không nên gửi tính năng mà client không hiểu.

### 15.7. Synchronization và document version

Completion phải dựa trên nội dung tài liệu mới nhất mà server đã nhận. Nếu request cũ hoàn tất sau request mới, client hoặc server cần tránh hiển thị kết quả stale.

## 16. Kiến trúc completion engine

Một completion engine có thể được chia thành các bước độc lập để dễ mở rộng và kiểm thử.

~~~mermaid
flowchart TD
    A[Editor request and cursor] --> B[Document snapshot]
    B --> C[Lexical and parser context]
    C --> D[Semantic scope and expected type]
    D --> E[Candidate providers]
    E --> F[Filter and validate]
    F --> G[Rank and deduplicate]
    G --> H[Build completion items]
    H --> I[Return to editor]
~~~

### 16.1. Document snapshot

Engine cần một snapshot nhất quán của tài liệu tại thời điểm request. Nếu document thay đổi trong lúc phân tích, kết quả phải gắn version để biết có còn áp dụng được hay không.

### 16.2. Context analyzer

Context analyzer xác định lexical, syntactic và semantic context tại cursor. Nó có thể dùng parser state, partial AST, symbol table và type inference.

### 16.3. Candidate providers

Mỗi provider cung cấp một nhóm candidate: keyword provider, scope symbol provider, member provider, type provider, enum provider, snippet provider hoặc import provider.

### 16.4. Filter và validate

Bộ lọc loại candidate không hợp lệ theo grammar, visibility, type hoặc quyền. Có thể áp dụng prefix matching và fuzzy matching ở bước này hoặc trong ranking.

### 16.5. Rank và deduplicate

Các provider có thể trả cùng một symbol. Engine cần loại bản trùng và chọn thông tin hiển thị tốt nhất. Ranking kết hợp độ khớp, context và tính hữu ích.

### 16.6. Completion item builder

Builder chuyển candidate nội bộ thành item theo editor API hoặc LSP. Nó xác định label, kind, documentation, insertion edit và commit characters.

### 16.7. Cache

Candidate hoặc symbol index có thể được cache. Cache cần invalidation khi file, dependency, import hoặc model thay đổi; cache cũ có thể gợi ý tên đã bị xóa hoặc kiểu đã đổi.

## 17. Cập nhật tăng dần và hiệu năng

Completion thường được gọi nhiều lần trong lúc người dùng gõ, vì vậy độ trễ và chi phí tính toán có ảnh hưởng trực tiếp đến trải nghiệm.

### 17.1. Incremental parsing

Thay vì parse lại toàn bộ project sau mỗi ký tự, editor có thể cập nhật cây cú pháp từ vùng thay đổi và tái sử dụng phần không bị ảnh hưởng. Completion cần truy cập được parse state đủ mới tại cursor.

### 17.2. Incremental semantic analysis

Thay đổi một khai báo có thể ảnh hưởng scope hoặc type của những vùng phụ thuộc. Semantic engine nên tính lại phần bị ảnh hưởng và cập nhật symbol index.

### 17.3. Cache theo document version

Kết quả cache cần gắn document version hoặc dependency generation. Khi version thay đổi, không sử dụng kết quả không còn tương ứng với snapshot.

### 17.4. Giới hạn candidate

Không cần gửi hàng chục nghìn candidate cho editor. Có thể giới hạn số mục, phân trang hoặc trả kết quả incomplete để tiếp tục truy vấn khi prefix dài hơn.

### 17.5. Tránh truy vấn đồng bộ chậm

Completion không nên chờ mạng hoặc database lâu trên luồng UI. Dữ liệu từ xa cần cache, timeout và fallback. Nếu chưa có kết quả, server có thể trả candidate cục bộ rồi cập nhật sau nếu giao thức hỗ trợ.

### 17.6. Hủy request cũ

Khi người dùng tiếp tục gõ, request trước có thể không còn cần thiết. Server nên hỗ trợ cancellation hoặc bỏ qua kết quả cũ để tránh tốn tài nguyên.

### 17.7. Đo độ trễ

Theo dõi thời gian từ request đến response, percentile latency, số candidate và cache hit rate. Một completion engine hữu ích cần phản hồi nhanh ở các thao tác phổ biến, kể cả khi workspace lớn.

## 18. Xử lý tài liệu chưa hoàn chỉnh

Completion phải hoạt động trong lúc người dùng đang nhập, kể cả khi parser chưa thể tạo AST hoàn chỉnh.

### 18.1. Partial syntax tree

Parser recovery có thể tạo node incomplete hoặc error node. Context analyzer sử dụng những node còn xác định được để tiếp tục cung cấp gợi ý.

### 18.2. Cursor trong identifier

Khi cursor nằm giữa một identifier, engine cần xác định prefix và suffix để tạo replacement range chính xác. Không nên mặc định cursor luôn ở cuối từ.

### 18.3. Cursor sau delimiter

Sau dấu chấm, dấu phẩy, dấu hai chấm hoặc dấu mở ngoặc, parser state có thể thay đổi. Trigger completion nên dựa trên loại delimiter và grammar tương ứng.

### 18.4. Cursor trong string

Trong string literal, gợi ý có thể gồm giá trị enum dạng chuỗi, đường dẫn hoặc key của một schema. Cần áp dụng escaping cho nội dung chèn và không gợi ý keyword bên ngoài chuỗi.

### 18.5. Cursor trong comment

Thông thường completion ngôn ngữ không hoạt động trong comment. Tuy nhiên, một số DSL hỗ trợ directive trong comment như TODO, suppression hoặc tài liệu tham chiếu; những trường hợp này cần provider riêng.

### 18.6. Thiếu dấu ngoặc hoặc block chưa đóng

Parser có thể dùng recovery để xác định block gần nhất. Completion không nên mất toàn bộ context chỉ vì thiếu dấu đóng ở cuối file.

### 18.7. Incomplete semantic model

Khi một khai báo đang được nhập dở, symbol có thể chưa có type hoặc name đầy đủ. Engine nên đánh dấu độ tin cậy và tránh đưa ra đề xuất quá chắc chắn từ dữ liệu chưa hoàn tất.

## 19. Import và completion từ nhiều file

Trong DSL modular, symbol có thể được định nghĩa ở file hoặc package khác.

### 19.1. Qualified name

Người dùng có thể nhập namespace hoặc module rồi chọn symbol:

~~~text
use inventory.<cursor>
~~~

Completion có thể liệt kê module hoặc symbol con theo namespace.

### 19.2. Auto-import

Nếu chọn một type chưa import, editor có thể chèn tên ngắn tại cursor và thêm import ở đầu file. Cần xử lý import trùng, alias, namespace collision và thứ tự import.

### 19.3. Workspace symbol index

Index cần lưu tên, kind, type, visibility, module, source location và metadata. Khi file được đổi tên hoặc xóa, index phải cập nhật để không đề xuất symbol cũ.

### 19.4. Dependency packages

Completion có thể lấy symbol từ package dependency. Cần giới hạn theo phiên bản dependency và visibility công khai, không quét mọi class nội bộ của thư viện.

### 19.5. Lazy loading

Với workspace lớn, có thể tải index theo module hoặc namespace khi người dùng bắt đầu nhập. Điều này giảm thời gian khởi động và bộ nhớ.

## 20. Completion cho hàm, tham số và biểu thức

DSL có thể có hàm miền, built-in function và thao tác biểu thức.

### 20.1. Function completion

Khi người dùng nhập tên hàm, completion có thể hiển thị chữ ký, kiểu trả về và mô tả.

~~~text
contains(collection: List<T>, value: T) -> Boolean
round(value: Decimal, scale: Integer) -> Decimal
~~~

### 20.2. Parameter name completion

Trong lời gọi có named arguments, editor có thể gợi ý những tham số chưa được cung cấp. Nếu tham số đã có, nó nên được loại khỏi danh sách trừ khi DSL cho phép lặp.

### 20.3. Parameter hints

Parameter hints hiển thị tên và kiểu tham số khi con trỏ ở trong lời gọi hàm. Đây là tính năng liên quan nhưng khác completion: nó giải thích vị trí đối số hiện tại thay vì đề xuất nội dung.

### 20.4. Overload resolution

Nếu hàm có nhiều overload, editor có thể dùng các đối số đã nhập để xác định overload phù hợp. Nếu chưa đủ thông tin, hiển thị các chữ ký có thể và xếp hạng theo mức tương thích.

### 20.5. Expected expression

Sau toán tử, completion có thể đề xuất biến, literal, function call hoặc ngoặc nhóm. Candidate cần tuân theo precedence và kiểu của biểu thức.

### 20.6. Operator completion

Một DSL có thể có toán tử miền như in, contains, matches hoặc within. Completion nên gợi ý toán tử dựa trên kiểu trái và grammar, tránh đưa toán tử không áp dụng được.

## 21. Completion cho schema, path và tài nguyên ngoài

Một số DSL tham chiếu đến file, schema hoặc tài nguyên do hệ thống bên ngoài quản lý.

### 21.1. Path completion

Khi cursor ở vị trí path, editor có thể liệt kê thư mục và file trong phạm vi project được phép. Path nên được chuẩn hóa theo quy tắc của DSL và không tiết lộ thư mục ngoài workspace.

### 21.2. Schema key completion

Trong cấu hình có schema, completion có thể gợi ý key hợp lệ, kiểu giá trị, trường bắt buộc và mô tả. Nếu schema có version, candidate phải tương ứng đúng version đang khai báo.

### 21.3. Resource catalog

DSL hạ tầng có thể gợi ý resource type, region hoặc tên cluster từ catalog. Kết quả cần phản ánh quyền hiện tại và có timestamp/cache policy nếu dữ liệu thay đổi.

### 21.4. Database schema

Trong DSL truy vấn, completion có thể gợi ý table, column và relation. Cần phân biệt schema đang chọn, alias, quyền truy cập và trạng thái metadata cache.

### 21.5. Không thực thi truy vấn tùy tiện

Completion không nên thực thi DSL hoặc query chưa tin cậy chỉ để lấy gợi ý. Nguồn dữ liệu cần có API đọc metadata giới hạn và quyền riêng.

## 22. Tích hợp formatter và các tính năng editor khác

Completion thường hoạt động cùng hover, signature help, diagnostics, rename và formatting.

### 22.1. Hover

Hover giải thích symbol dưới con trỏ. Completion documentation có thể tái sử dụng cùng nguồn mô tả để bảo đảm nội dung nhất quán.

### 22.2. Diagnostics

Completion có thể dùng kết quả semantic analysis để loại symbol không hợp lệ hoặc gợi ý tên gần giống. Tuy nhiên, completion cần vẫn hoạt động khi diagnostics đang cập nhật.

### 22.3. Rename

Rename symbol đổi mọi tham chiếu đã được phân giải. Completion nên dùng cùng symbol identity để tránh đề xuất một tên đã đổi hoặc nhầm giữa hai symbol cùng label.

### 22.4. Formatting

Formatter có thể chạy sau khi chèn snippet hoặc hoàn thành cấu trúc. Completion edit cần tương thích với quy tắc indentation và không làm formatter thay đổi nội dung ngoài ý muốn.

### 22.5. Signature help

Signature help hiển thị chữ ký hàm và tham số đang được nhập. Completion có thể đề xuất tên tham số; signature help giải thích vị trí và kiểu của tham số hiện tại.

### 22.6. Code action

Một completion item có thể đi kèm command hoặc edit bổ sung, nhưng hành động thay đổi rộng nên được trình bày rõ. Không nên thực hiện thao tác có tác động lớn chỉ vì người dùng chọn một tên gợi ý.

## 23. Trải nghiệm người dùng và khả năng tiếp cận

Danh sách completion phải dễ đọc, dễ điều khiển và không che khuất nội dung đang nhập.

### 23.1. Hiển thị có phân nhóm

Có thể nhóm keyword, variable, function, type và snippet. Nhóm giúp người dùng hiểu loại candidate, nhưng không nên tạo quá nhiều nhóm nhỏ khiến việc tìm kiếm khó hơn.

### 23.2. Keyboard navigation

Người dùng cần di chuyển bằng phím lên/xuống, chấp nhận bằng Enter hoặc Tab theo cấu hình, đóng popup bằng Escape và tiếp tục gõ để lọc.

### 23.3. Không tự chèn quá sớm

Tự động chấp nhận candidate đầu tiên khi người dùng gõ dấu phân cách có thể gây thay đổi bất ngờ. Commit character và auto-insert cần được thiết kế cẩn thận.

### 23.4. Mô tả dễ hiểu

Label nên ngắn; detail nêu kiểu hoặc nguồn; documentation giải thích ý nghĩa. Tránh hiển thị stack trace hoặc tên class nội bộ của compiler trong popup.

### 23.5. Screen reader

Candidate cần có tên và loại có thể đọc được bằng công nghệ hỗ trợ. Không nên chỉ dùng màu hoặc icon để phân biệt keyword với function.

### 23.6. Điều khiển kích thước và độ trễ

Popup không nên chiếm quá nhiều màn hình. Cần giữ vị trí gần con trỏ, cập nhật nhanh và tránh nhấp nháy khi danh sách thay đổi.

### 23.7. Cấu hình cá nhân

Cho phép bật/tắt automatic completion, thay đổi trigger, giới hạn candidate hoặc chọn cách chấp nhận. Người dùng có kinh nghiệm có thể muốn ít popup hơn người mới học DSL.

## 24. Bảo mật và quyền riêng tư

Completion có thể truy cập workspace, dependency và catalog bên ngoài. Nó cần tuân thủ cùng chính sách bảo mật như các tính năng phân tích khác.

### 24.1. Workspace boundaries

Index không nên đọc hoặc đề xuất file ngoài phạm vi project và quyền đã cấp. Path completion cần chặn path traversal và không tiết lộ vị trí nhạy cảm.

### 24.2. Access control

Không đề xuất symbol hoặc resource mà người dùng không có quyền nhìn thấy. Nếu quyền thay đổi, cache cần được invalidation.

### 24.3. Không gửi source tùy tiện ra ngoài

Completion request có thể chứa đoạn code đang viết. Nếu dùng dịch vụ từ xa, cần có chính sách rõ về dữ liệu gửi đi, lưu trữ và quyền truy cập. Tính năng cục bộ nên được ưu tiên khi đáp ứng yêu cầu.

### 24.4. Không thực thi candidate

Việc tạo candidate nên dựa trên metadata và phân tích tĩnh. Không thực thi hàm hoặc script tùy ý từ project chỉ để lấy danh sách gợi ý.

### 24.5. Secret filtering

Không nên đề xuất hoặc hiển thị giá trị secret trong documentation hoặc completion detail. Nếu DSL tham chiếu secret store, có thể gợi ý tên secret được phép truy cập nhưng không tiết lộ nội dung.

### 24.6. Audit và telemetry

Nếu thu thập telemetry về candidate được chọn, cần giới hạn dữ liệu để không ghi nội dung nhạy cảm hoặc source code. Có thể thu số liệu tổng hợp về latency và loại candidate thay vì toàn bộ prefix.

## 25. Kiểm thử gợi ý hoàn thành

Completion cần được kiểm thử theo vị trí cursor, nội dung tài liệu, context semantic và hành vi chèn.

### 25.1. Test theo cursor marker

Fixture có thể dùng marker đặc biệt để chỉ vị trí yêu cầu completion:

~~~text
policy giao_hang {
    area = <|>
}
~~~

Test runner loại marker khỏi nội dung, gửi request tại offset tương ứng và so sánh candidate mong đợi.

### 25.2. Kiểm thử context cú pháp

Kiểm tra cấp file, block, danh sách, biểu thức, string, comment và vị trí sau delimiter. Mỗi context cần tập candidate phù hợp.

### 25.3. Kiểm thử scope và visibility

Tạo biến lồng nhau, symbol bị shadow, private member, import và module khác. Xác minh candidate được lọc theo đúng name resolution.

### 25.4. Kiểm thử kiểu

Kiểm tra expected type, member access, overload, generic, nullable và biểu thức chưa đủ thông tin.

### 25.5. Kiểm thử prefix và ranking

Kiểm tra exact match, case-insensitive match, camel-case, fuzzy match và tie-breaking. Danh sách cần ổn định khi input không đổi.

### 25.6. Kiểm thử insertion

Chấp nhận candidate và xác minh text edit, replacement range, commit character, additional import edit, snippet tab stop và indentation.

### 25.7. Kiểm thử tài liệu chưa hoàn chỉnh

Thử thiếu dấu đóng, identifier đang gõ dở, expression lỗi và document rỗng. Completion cần tiếp tục cung cấp candidate hữu ích.

### 25.8. Kiểm thử LSP capabilities

Kiểm tra client có hoặc không hỗ trợ snippet, markdown documentation, resolve và insert/replace edit. Server phải trả nội dung tương thích.

### 25.9. Kiểm thử hiệu năng

Đo latency ở workspace nhỏ và lớn, số symbol lớn, request liên tiếp và cancellation. Kiểm tra cache invalidation sau khi file hoặc dependency thay đổi.

### 25.10. Kiểm thử bảo mật

Kiểm tra path ngoài workspace, symbol không có quyền, secret, dữ liệu độc hại và template/helper có thể thực thi. Completion không được tiết lộ hoặc chạy nội dung ngoài phạm vi.

## 26. Ví dụ tổng hợp: completion cho DSL giao hàng

Giả sử mô hình miền khai báo:

~~~text
enum DeliveryArea {
    NOI_THANH
    NGOAI_THANH
}

class DonHang {
    id: OrderId
    tong_tien: Money<VND>
    ngay_tao: Date
    trang_thai: OrderStatus
}

enum OrderStatus {
    MOI_TAO
    DA_XAC_NHAN
    DANG_GIAO
    DA_HUY
}
~~~

Người dùng đang viết:

~~~text
policy giao_hang {
    area: DeliveryArea = <cursor>
    when don_hang.<cursor>
}
~~~

### 26.1. Gợi ý tại thuộc tính area

Expected type là DeliveryArea. Completion provider truy vấn enum members và trả:

- NOI_THANH
- NGOAI_THANH

Candidate có kind enum member, detail cho biết enum nguồn và documentation mô tả phạm vi áp dụng nếu có.

### 26.2. Gợi ý sau don_hang.

Semantic analyzer xác định don_hang có kiểu DonHang. Member provider liệt kê id, tong_tien, ngay_tao và trang_thai theo visibility. Nếu người dùng đã nhập prefix tong, ranking đưa tong_tien lên đầu.

### 26.3. Gợi ý sau dấu so sánh

Với biểu thức:

~~~text
when don_hang.tong_tien >= <cursor>
~~~

Expected type là Money<VND>. Completion có thể gợi ý biến cùng kiểu, literal tiền tệ và hàm trả về Money<VND>. Giá trị Date hoặc OrderStatus bị loại.

### 26.4. Gợi ý snippet

Khi người dùng nhập prefix pol ở cấp file, editor có thể đề xuất snippet policy gồm tên, điều kiện và block. Chọn snippet đưa con trỏ đến từng placeholder để người dùng hoàn thiện.

### 26.5. Auto-import

Nếu type OrderStatus nằm trong module khác, completion có thể đề xuất symbol và thêm import tương ứng. Nếu nhiều module có type cùng tên, detail hiển thị module để người dùng phân biệt.

### 26.6. Tài liệu chưa hoàn chỉnh

Nếu thiếu dấu đóng block ở cuối file, parser recovery vẫn giữ được context policy. Completion tiếp tục gợi ý thuộc tính và biểu thức thay vì coi toàn bộ tài liệu là không thể phân tích.

## 27. Những sai lầm thường gặp

### 27.1. Gợi ý mọi symbol trong project

Danh sách quá rộng làm người dùng khó tìm và có thể đưa ra symbol không hợp lệ. Cần lọc theo grammar, scope, type và visibility.

### 27.2. Chỉ dùng keyword tĩnh

Completion chỉ liệt kê từ khóa không thể hỗ trợ tên miền, member access, enum, import hoặc kiểu dữ liệu. DSL editor cần tận dụng semantic model.

### 27.3. Chỉ hoạt động khi file parse hoàn chỉnh

Người dùng thường gõ trong trạng thái lỗi tạm thời. Completion cần dựa trên partial parse và parser recovery.

### 27.4. Ranking không ổn định

Danh sách thay đổi thứ tự liên tục khiến người dùng dễ chọn nhầm. Cần tie-breaker ổn định và không để điểm popularity lấn át context.

### 27.5. Chèn sai replacement range

Nếu chỉ nối chuỗi thay vì thay prefix đúng cách, editor có thể tạo identifier lặp hoặc làm mất suffix. Cần kiểm thử cursor ở giữa từ.

### 27.6. Auto-import gây xung đột

Thêm import mà không kiểm tra tên trùng hoặc alias có thể làm chương trình mơ hồ. Import edit cần được xác thực với symbol resolver.

### 27.7. Completion quá chậm

Truy vấn mạng hoặc phân tích toàn project đồng bộ trong mỗi lần gõ làm editor đơ. Cần incremental analysis, cache, cancellation và giới hạn thời gian.

### 27.8. Dùng dữ liệu stale

Candidate từ symbol index cũ có thể trỏ đến symbol đã bị xóa hoặc đổi kiểu. Cache phải gắn version và được invalidation đúng.

### 27.9. Không tôn trọng capability của client

Gửi snippet hoặc edit format mà client không hỗ trợ có thể chèn văn bản sai. Language server cần kiểm tra client capabilities.

### 27.10. Tiết lộ thông tin nhạy cảm

Gợi ý path, secret hoặc resource không có quyền có thể làm lộ thông tin. Completion phải tuân thủ workspace boundary và access control.

## 28. Nguyên tắc thiết kế completion cho DSL

Một completion engine tốt cần cân bằng độ chính xác, tốc độ và tính dễ hiểu.

### 28.1. Context trước độ rộng danh sách

Ưu tiên ít candidate nhưng đúng vị trí. Grammar, scope, type và visibility nên được dùng trước khi ranking.

### 28.2. Dùng chung semantic model

Completion nên dùng cùng symbol identity, type system và name resolution với compiler để tránh đề xuất nội dung mà compiler không chấp nhận.

### 28.3. Hỗ trợ partial document

Parser recovery và incremental analysis giúp completion hoạt động khi tài liệu đang gõ dở.

### 28.4. Chèn có thể dự đoán

Mỗi item cần label rõ, kind phù hợp, insertion range chính xác và hành vi commit nhất quán.

### 28.5. Tách provider

Keyword, symbol, member, type, enum, snippet và import provider có thể phát triển độc lập nhưng dùng chung filter, ranking và item builder.

### 28.6. Tối ưu theo tương tác

Cache, debounce, cancellation, giới hạn candidate và resolve lười giúp giảm độ trễ. Kết quả phải gắn với document version.

### 28.7. Tôn trọng quyền và dữ liệu

Không gợi ý symbol ngoài phạm vi, không tiết lộ secret và không thực thi code tùy ý để tạo candidate.

### 28.8. Kiểm thử hành vi người dùng

Test không chỉ kiểm tra candidate có xuất hiện mà còn kiểm tra thứ tự, insertion, snippet, import, cursor position và khả năng hoạt động trong tài liệu lỗi.

## 29. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Code Completion | Đề xuất nội dung có thể nhập tiếp tại vị trí con trỏ |
| Autocomplete | Tên thường dùng cho tính năng tự động hoàn thành |
| IntelliSense | Nhóm tính năng hỗ trợ nhập mã theo ngữ cảnh |
| Completion Item | Một candidate được hiển thị và có thể chấp nhận |
| Prefix Matching | Lọc candidate bắt đầu bằng chuỗi đang nhập |
| Fuzzy Matching | Tìm candidate gần đúng dù không khớp hoàn toàn |
| Ranking | Xếp thứ tự candidate theo mức độ phù hợp |
| Scope | Phạm vi quyết định symbol nào có thể truy cập |
| Symbol Table | Cấu trúc lưu thông tin các symbol đã khai báo |
| Expected Type | Kiểu mà biểu thức tại vị trí hiện tại cần đáp ứng |
| Member Completion | Gợi ý thành viên sau phép truy cập đối tượng |
| Snippet | Đoạn mã mẫu có placeholder hoặc tab stop |
| Trigger Character | Ký tự làm editor tự yêu cầu completion |
| Commit Character | Ký tự chấp nhận candidate và tiếp tục nhập |
| Replacement Range | Vùng văn bản sẽ bị thay thế khi chấp nhận gợi ý |
| Auto-import | Tự thêm import khi chọn symbol từ module khác |
| Partial Parse Tree | Cây cú pháp một phần dùng khi tài liệu chưa hoàn chỉnh |
| Incremental Parsing | Cập nhật kết quả parse theo vùng thay đổi |
| Completion Provider | Thành phần cung cấp một nhóm candidate |
| Completion Resolve | Bổ sung detail hoặc documentation cho candidate đã trả |
| LSP | Giao thức trao đổi giữa editor và language server |
| Client Capabilities | Những tính năng mà editor client hỗ trợ |
| Cache Invalidation | Loại bỏ cache khi nguồn dữ liệu thay đổi |
| Signature Help | Hiển thị chữ ký và tham số của lời gọi hàm |

Gợi ý hoàn thành là một phần thiết yếu của trải nghiệm viết DSL trong editor. Nó kết hợp parser context, scope, type information và dữ liệu miền để đề xuất những lựa chọn hợp lệ ngay tại vị trí con trỏ. Một completion engine hữu ích cần xếp hạng theo ngữ cảnh, chèn văn bản đúng phạm vi, hỗ trợ snippet và import, hoạt động trên tài liệu chưa hoàn chỉnh, đồng thời phản hồi nhanh và tôn trọng quyền truy cập. Khi dùng chung semantic model với compiler và được kiểm thử qua cả candidate lẫn thao tác chèn, completion giúp người dùng viết DSL nhanh hơn, ít lỗi hơn và hiểu rõ hơn những khả năng mà ngôn ngữ cung cấp.
