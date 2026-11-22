# So sánh và diff trong DSL

Trong quá trình lưu trữ và trao đổi các mô hình của ngôn ngữ đặc tả miền (Domain-Specific Language, DSL), một hệ thống thường cần biết hai phiên bản khác nhau ở đâu. Mô hình có thể được lưu dưới dạng văn bản DSL, JSON, YAML, XML, AST đã tuần tự hóa hoặc một định dạng trung gian. Khi người dùng sửa một quy tắc, nâng cấp schema, nhập một bản cấu hình mới hoặc đồng bộ dữ liệu giữa các dịch vụ, việc so sánh giúp xác định chính xác điều gì đã thay đổi.

**So sánh** (*comparison*) là quá trình xác định mức độ giống và khác nhau giữa hai tài liệu hoặc hai mô hình. **Diff** là biểu diễn những khác biệt đó dưới dạng có thể đọc, lưu trữ, áp dụng hoặc trao đổi. Diff có thể chỉ ra dòng văn bản được thêm và xóa, hoặc mô tả thay đổi ở cấp cấu trúc như thêm một trường, đổi kiểu thuộc tính, sửa điều kiện của rule hay xóa một bước workflow.

Với DSL, so sánh văn bản thường chưa đủ. Hai file có thể khác khoảng trắng nhưng mang cùng ý nghĩa; ngược lại, một thay đổi nhỏ trong biểu thức có thể làm hành vi nghiệp vụ thay đổi đáng kể. Vì vậy, hệ thống cần chọn đúng mức so sánh: văn bản, cấu trúc, kiểu dữ liệu hoặc ngữ nghĩa miền. Cần hiểu rõ sự khác nhau này để review, đồng bộ, merge và kiểm soát phiên bản mô hình một cách an toàn.

## 1. So sánh và diff là gì?

### 1.1. So sánh hai phiên bản

Giả sử một rule được lưu ở hai phiên bản:

~~~text
rule MemberDiscount {
    when customer.tier == GOLD
    then applyDiscount(order, 0.10)
}
~~~

Phiên bản sau:

~~~text
rule MemberDiscount {
    when customer.tier == GOLD
         and order.total >= 1000000 VND
    then applyDiscount(order, 0.15)
}
~~~

Một phép so sánh có thể cho biết:

- Điều kiện mới được thêm vào.
- Giá trị tỷ lệ giảm giá thay đổi từ 0.10 thành 0.15.
- Tên rule và hành động vẫn giữ nguyên.

Thông tin này có ích hơn việc chỉ biết hai file có hash khác nhau.

### 1.2. Diff là đầu ra của phép so sánh

Diff thường biểu diễn các thay đổi bằng thao tác:

- Add: thêm một phần tử hoặc đoạn nội dung.
- Remove: xóa một phần tử hoặc đoạn nội dung.
- Replace: thay một giá trị bằng giá trị khác.
- Move: di chuyển phần tử nếu định dạng và thuật toán hỗ trợ nhận diện.
- Rename: đổi tên định danh hoặc tài nguyên.
- Change: thay đổi một thuộc tính hoặc metadata.

Với diff văn bản, các thao tác thường được thể hiện thành dòng thêm và dòng xóa. Với diff cấu trúc, chúng có thể được biểu diễn bằng đường dẫn đến node hoặc thuộc tính.

### 1.3. So sánh bằng nhau không chỉ có một nghĩa

Hai tài liệu có thể được xem là bằng nhau theo nhiều tiêu chí:

| Mức so sánh | Câu hỏi | Ví dụ |
|---|---|---|
| Byte | Nội dung byte có giống hệt không? | Khác kiểu xuống dòng làm byte khác nhau |
| Văn bản | Chuỗi ký tự có giống nhau không? | Khác khoảng trắng hoặc comment |
| Cấu trúc | Cây cú pháp hoặc dữ liệu có cùng cấu trúc không? | JSON có thứ tự key khác nhưng cùng object |
| Kiểu | Các kiểu, trường và chữ ký có giống nhau không? | Đổi Integer thành Decimal |
| Ngữ nghĩa | Chương trình có hành vi tương đương theo mô hình được xét không? | Hai biểu thức khác cú pháp nhưng cho cùng kết quả |
| Miền nghiệp vụ | Các quy tắc nghiệp vụ có cùng tác động không? | Tăng mức chiết khấu làm thay đổi quyền lợi |

Không có một phép so sánh duy nhất phù hợp cho mọi mục đích. Công cụ cần nói rõ nó đang so sánh ở mức nào.

## 2. Vì sao cần diff cho DSL?

### 2.1. Review thay đổi mô hình

Khi một nhóm sửa DSL, reviewer cần hiểu thay đổi ảnh hưởng đến rule, schema, workflow hoặc query nào. Diff giúp tập trung vào phần thay đổi và giảm nhu cầu đọc lại toàn bộ tài liệu.

### 2.2. Theo dõi lịch sử

Lịch sử diff cho phép trả lời:

- Ai đã thay đổi quy tắc?
- Thay đổi diễn ra khi nào?
- Giá trị cũ và mới là gì?
- Thay đổi nào đã được phê duyệt?
- Phiên bản nào đang được triển khai?

### 2.3. Đồng bộ giữa môi trường

Một mô hình có thể được phát triển ở local, kiểm thử ở staging và triển khai ở production. Diff giúp so sánh cấu hình giữa các môi trường để phát hiện sai lệch.

### 2.4. Phát hiện thay đổi ngoài ý muốn

Một lần tái sinh mã hoặc nâng cấp generator có thể tạo ra diff lớn. So sánh cấu trúc giúp phân biệt thay đổi thực sự của mô hình với thay đổi do formatter, serializer hoặc phiên bản công cụ.

### 2.5. Hỗ trợ migration

Khi schema thay đổi, hệ thống cần biết trường nào được thêm, xóa, đổi kiểu hoặc đổi tên. Diff cấu trúc có thể cung cấp dữ liệu đầu vào cho migration planner.

### 2.6. Kiểm soát tương thích

Diff API hoặc schema giúp nhận diện thay đổi có thể phá vỡ consumer, chẳng hạn xóa trường bắt buộc, đổi kiểu kết quả hoặc thay đổi ý nghĩa của enum.

### 2.7. Hỗ trợ merge và cộng tác

Nhiều người có thể chỉnh sửa cùng một tài liệu DSL. Diff và merge giúp xác định những vùng thay đổi độc lập và những nơi cần giải quyết xung đột.

## 3. Các loại diff

### 3.1. Text diff

Text diff so sánh nội dung văn bản theo dòng hoặc theo ký tự. Nó phù hợp với:

- Review file DSL trong Git.
- Kiểm tra thay đổi template.
- So sánh log hoặc tài liệu.
- Xem khác biệt định dạng và comment.

Ví dụ:

~~~diff
 rule MemberDiscount {
     when customer.tier == GOLD
-    then applyDiscount(order, 0.10)
+    then applyDiscount(order, 0.15)
 }
~~~

Text diff không cần hiểu grammar của DSL. Tuy nhiên, nó có thể tạo nhiều khác biệt gây nhiễu nếu formatter thay đổi hoặc các phần tử được sắp xếp lại.

### 3.2. Line diff

Line diff xem mỗi dòng là một đơn vị. Nó dễ đọc và phổ biến trong hệ thống version control. Điểm yếu là một dòng dài chứa nhiều biểu thức có thể chỉ ra thay đổi quá rộng.

### 3.3. Word hoặc token diff

Token diff chia dòng thành từ, token hoặc ký hiệu. Nó có thể làm nổi bật phần thay đổi nhỏ bên trong một dòng:

~~~text
applyDiscount(order, [-0.10-]{+0.15+})
~~~

Token diff hữu ích khi DSL có cú pháp ổn định và tên, literal được nhận diện rõ.

### 3.4. AST diff

AST diff so sánh hai cây cú pháp trừu tượng. Nó có thể nhận diện:

- Thêm hoặc xóa khai báo.
- Thay literal.
- Thêm điều kiện.
- Đổi toán tử.
- Thay đổi lời gọi hàm.
- Di chuyển node trong cấu trúc.

AST diff bỏ qua những khác biệt không ảnh hưởng cấu trúc như khoảng trắng hoặc comment nếu parser không giữ chúng trong AST.

### 3.5. Model diff

Model diff so sánh các đối tượng miền đã được phân giải, chẳng hạn entity, field, rule, action, workflow state hoặc API operation.

Ví dụ:

~~~text
Entity: Customer
  Field added:
    loyaltyLevel: LoyaltyLevel
  Field changed:
    email: String -> Optional<String>
~~~

Model diff có thể dễ hiểu với chuyên gia miền hơn AST diff vì nó dùng tên khái niệm của mô hình.

### 3.6. Semantic diff

Semantic diff cố gắng mô tả sự thay đổi về ý nghĩa hoặc hành vi. Ví dụ:

- Điều kiện áp dụng rule trở nên chặt hơn.
- Mức giảm giá tăng.
- Workflow cho phép thêm một đường chuyển trạng thái.
- Một API không còn chấp nhận một loại đầu vào.

Semantic diff đòi hỏi kiến thức về ngôn ngữ và miền. Nó không thể luôn chứng minh hai chương trình tương đương trong mọi trường hợp.

### 3.7. Binary diff

Binary diff so sánh các artifact nhị phân như bytecode, file nén hoặc gói đã biên dịch. Nó hữu ích cho phân phối artifact nhưng thường khó giải thích thay đổi ở cấp DSL.

Một hệ thống có thể dùng binary diff để truyền dữ liệu tiết kiệm, đồng thời cung cấp model diff để reviewer hiểu nội dung.

## 4. Chọn đúng mức so sánh

### 4.1. Mục đích quyết định loại diff

| Mục đích | Loại diff phù hợp |
|---|---|
| Kiểm tra thay đổi ký tự | Byte hoặc text diff |
| Review DSL trong pull request | Text diff kết hợp token diff |
| Xác định thay đổi schema | Structural hoặc model diff |
| Tạo migration | Schema-aware diff |
| Đánh giá tác động nghiệp vụ | Semantic diff |
| Kiểm tra artifact phát hành | Binary hash hoặc binary diff |
| Merge chỉnh sửa đồng thời | Three-way structural diff khi có thể |

### 4.2. Không nên bỏ text diff

Structural diff không thay thế hoàn toàn text diff. Comment, tài liệu nội tuyến, format hoặc annotation có thể quan trọng với người viết nhưng không nằm trong mô hình ngữ nghĩa.

Một công cụ review tốt có thể hiển thị nhiều lớp: thay đổi cấu trúc ở một panel và thay đổi văn bản ở panel khác.

### 4.3. Diff phải công bố giới hạn

Nếu semantic diff chỉ nhận diện được một số loại thay đổi, giao diện cần thể hiện rõ. Không nên trình bày một kết quả phân tích hạn chế như bằng chứng rằng hai chương trình tương đương hoàn toàn.

## 5. Chuẩn hóa trước khi so sánh

### 5.1. Vì sao cần chuẩn hóa?

Hai tài liệu có thể khác hình thức nhưng giống cấu trúc:

~~~text
{"name":"Customer","active":true}
~~~

~~~text
{
  "active": true,
  "name": "Customer"
}
~~~

Nếu định dạng là JSON object, thứ tự key không mang ý nghĩa. Text diff sẽ báo nhiều thay đổi, trong khi structural diff có thể kết luận hai object giống nhau.

### 5.2. Canonicalization

Canonicalization chuyển tài liệu về một dạng chuẩn trước khi so sánh. Các bước có thể gồm:

- Chuẩn hóa encoding.
- Chuẩn hóa xuống dòng.
- Chuẩn hóa khoảng trắng không có ý nghĩa.
- Sắp xếp key của map nếu thứ tự không quan trọng.
- Chuẩn hóa cách biểu diễn số hoặc ngày theo quy tắc.
- Chuẩn hóa tên hoặc Unicode theo chính sách.
- Chuẩn hóa thứ tự các phần tử không có ngữ nghĩa thứ tự.

Canonicalization phải dựa trên đặc tả. Không được sắp xếp một danh sách nếu thứ tự phần tử có ý nghĩa.

### 5.3. Formatter và canonical serializer

Formatter trình bày nội dung cho con người. Canonical serializer tạo biểu diễn ổn định cho so sánh, hash hoặc trao đổi. Hai công cụ có thể dùng chung một số quy tắc nhưng mục tiêu không hoàn toàn giống nhau.

Formatter có thể ưu tiên dễ đọc; canonical serializer ưu tiên tính xác định và không mơ hồ.

### 5.4. Chuẩn hóa comment

Comment có thể:

- Không ảnh hưởng ngữ nghĩa.
- Chứa metadata như owner, issue hoặc deprecation.
- Là một phần tài liệu cần review.
- Được công cụ dùng để điều khiển generator.

Không nên loại bỏ comment trước khi diff nếu comment có metadata hoặc ý nghĩa đối với quy trình.

### 5.5. Chuẩn hóa số và đơn vị

Các biểu diễn 1.0 và 1.00 có thể cùng giá trị số nhưng khác độ chính xác được khai báo. 1000 ms và 1 s có thể tương đương về lượng nhưng khác đơn vị gốc. Việc chuẩn hóa phải biết DSL có xem scale và đơn vị là metadata hay không.

### 5.6. Unicode và tên

Hai chuỗi tên có thể có biểu diễn Unicode khác nhau nhưng nhìn giống nhau. Canonicalization có thể chuẩn hóa theo một dạng Unicode đã chọn, nhưng cần bảo toàn chính sách phân biệt tên và không làm nhập nhằng các định danh mà DSL coi là khác nhau.

## 6. So sánh cấu trúc AST

### 6.1. AST là cây

AST biểu diễn chương trình bằng các node có quan hệ cha-con. Ví dụ:

~~~text
Rule
  name: MemberDiscount
  condition:
    And
      Equals
        MemberAccess(customer, tier)
        EnumValue(GOLD)
      GreaterOrEqual
        MemberAccess(order, total)
        MoneyLiteral(1000000, VND)
  action:
    Call(applyDiscount)
      Argument(order)
      Argument(DecimalLiteral(0.15))
~~~

AST diff so sánh loại node, thuộc tính và các node con. Nó có thể chỉ ra một điều kiện mới được thêm thay vì chỉ hiển thị các dòng bị thay đổi.

### 6.2. Node identity

Để nhận diện một node giữa hai phiên bản, hệ thống cần xác định node nào tương ứng với node nào. Dựa vào vị trí trong cây có thể không ổn định khi một node được chèn phía trước.

Các chiến lược có thể gồm:

- ID ổn định được lưu trong mô hình.
- Tên định danh và namespace.
- Loại node cùng thuộc tính khóa.
- Đường dẫn cấu trúc.
- So khớp nội dung và ngữ cảnh.

Không có chiến lược nào luôn đúng. Với entity có tên duy nhất, tên có thể là khóa tốt. Với biểu thức vô danh, cần kết hợp cấu trúc và vị trí.

### 6.3. Structural matching

Thuật toán matching tìm node tương ứng dựa trên:

- Loại node.
- Tên và thuộc tính.
- Kiểu.
- Quan hệ cha-con.
- Các node lân cận.
- Nội dung biểu thức.

Một thuật toán tốt hạn chế việc xem một node đã di chuyển là node bị xóa rồi thêm lại.

### 6.4. Thêm, xóa và thay đổi

Ví dụ model diff:

~~~text
Rule MemberDiscount
  + condition: order.total >= 1000000 VND
  ~ action.rate: 0.10 -> 0.15
~~~

Ký hiệu + biểu thị thêm; ~ biểu thị thay đổi. Định dạng cụ thể tùy công cụ.

### 6.5. Di chuyển node

Nếu một trường được chuyển từ vị trí này sang vị trí khác nhưng giữ cùng ID, diff có thể nhận diện là move. Nếu không có ID, thuật toán có thể không phân biệt được move với remove và add.

### 6.6. Đổi tên

Đổi tên một entity hoặc field có thể được hiểu là:

- Xóa tên cũ và thêm tên mới.
- Rename một node có identity ổn định.

Nhận diện rename rất quan trọng vì migration cần biết liệu dữ liệu cũ có cần chuyển tên hay không.

## 7. Identity và khóa ổn định của mô hình

### 7.1. Vì sao tên không phải lúc nào cũng đủ?

Tên có thể thay đổi, trùng trong các namespace khác nhau hoặc được tái sử dụng sau khi xóa. Nếu tên là định danh duy nhất duy nhất, một lần rename có thể khiến hệ thống coi đối tượng cũ đã biến mất và đối tượng mới vừa được tạo.

### 7.2. Stable ID

Một mô hình có thể lưu ID độc lập với tên:

~~~yaml
id: customer-field-42
name: loyaltyLevel
type: LoyaltyLevel
~~~

Khi đổi tên:

~~~yaml
id: customer-field-42
name: membershipLevel
type: LoyaltyLevel
~~~

Diff có thể nhận ra cùng một field được rename.

### 7.3. ID trong mô hình trao đổi

Stable ID cần:

- Duy nhất trong phạm vi đã định nghĩa.
- Không thay đổi khi rename nếu vẫn là cùng đối tượng.
- Không được tái sử dụng tùy tiện sau khi xóa.
- Có quy tắc tạo khi import tài liệu không có ID.
- Có cách xử lý khi hai nhánh tạo cùng ID độc lập.

### 7.4. ID sinh tự động

UUID hoặc ID ngẫu nhiên có thể bảo đảm tính duy nhất nhưng làm diff khó đọc nếu được tạo lại mỗi lần parse. ID nên được lưu trong nguồn hoặc được tạo bằng một quy tắc ổn định khi phù hợp.

### 7.5. Composite key

Một số mô hình dùng tổ hợp module, loại đối tượng và tên làm khóa. Cách này dễ đọc nhưng rename làm thay đổi khóa. Nếu cần theo dõi identity qua rename, nên có ID riêng.

## 8. So sánh schema và dữ liệu có kiểu

### 8.1. Schema diff

Schema diff tập trung vào cấu trúc dữ liệu:

- Thêm hoặc xóa entity.
- Thêm hoặc xóa field.
- Đổi kiểu.
- Đổi nullable hoặc required.
- Đổi default.
- Đổi constraint.
- Đổi khóa chính hoặc quan hệ.

Ví dụ:

~~~text
Customer
  + loyaltyLevel: LoyaltyLevel
  ~ email: String -> Optional<String>
  - legacyCode: String
~~~

### 8.2. Thay đổi tương thích và phá vỡ tương thích

Không phải mọi thay đổi schema đều có tác động giống nhau:

| Thay đổi | Khả năng tương thích thường gặp |
|---|---|
| Thêm field optional có default | Thường tương thích với reader cũ nếu định dạng hỗ trợ |
| Thêm field bắt buộc không default | Có thể phá vỡ producer cũ |
| Xóa field | Có thể phá vỡ consumer đang đọc field |
| Đổi tên field | Thường phá vỡ nếu không có alias |
| Đổi kiểu sang kiểu rộng hơn | Có thể tương thích tùy hệ kiểu và serializer |
| Đổi nullable thành required | Có thể phá vỡ dữ liệu cũ |
| Thay enum bằng tập giá trị khác | Có thể phá vỡ consumer xử lý exhaustively |

Khả năng tương thích cần xét cả producer, consumer, dữ liệu đang lưu và phiên bản runtime.

### 8.3. Schema evolution

Schema evolution là quá trình thay đổi schema theo thời gian mà vẫn quản lý được dữ liệu và consumer hiện có. Diff là đầu vào để xác định migration cần thiết.

Ví dụ, đổi email từ String bắt buộc thành Optional<String> có thể cần:

- Cập nhật generated model.
- Cập nhật validation.
- Cập nhật consumer.
- Quy định cách đọc dữ liệu cũ.
- Cập nhật tài liệu API.

### 8.4. Default value

Thêm default có thể giúp dữ liệu cũ được đọc theo schema mới. Tuy nhiên, default cần có ngữ nghĩa ổn định. Một default phụ thuộc thời gian hiện tại hoặc người dùng hiện tại không phải lúc nào cũng an toàn để áp dụng khi đọc lại dữ liệu cũ.

### 8.5. Enum diff

Thêm enum value có thể làm consumer cũ gặp giá trị chưa biết. Xóa enum value có thể làm dữ liệu đã lưu trở nên không hợp lệ. Diff nên liệt kê từng giá trị được thêm, xóa hoặc đổi tên.

## 9. So sánh ngữ nghĩa

### 9.1. Cú pháp khác nhưng ý nghĩa có thể giống

Hai biểu thức:

~~~text
amount >= 100
~~~

~~~text
not (amount < 100)
~~~

có thể tương đương nếu hệ kiểu và semantics của phép so sánh là hai giá trị thông thường, không có null hoặc unknown. Nếu DSL có ba giá trị logic, chúng có thể không tương đương trong mọi trường hợp.

### 9.2. Chuẩn hóa biểu thức

Một semantic diff có thể chuẩn hóa biểu thức về dạng IR hoặc dạng logic trung gian trước khi so sánh. Ví dụ, bỏ ngoặc dư hoặc chuẩn hóa literal.

Tuy nhiên, việc biến đổi biểu thức phải được chứng minh là bảo toàn semantics trong phạm vi hệ kiểu của DSL.

### 9.3. Tương đương ngữ nghĩa khó chứng minh

Việc xác định hai chương trình bất kỳ có cùng hành vi trong mọi đầu vào có thể rất khó, thậm chí không quyết định được với ngôn ngữ đủ mạnh.

Vì vậy, semantic diff thực tế thường dùng các quy tắc cục bộ và heuristic:

- So sánh AST sau normalization.
- So sánh IR.
- Nhận diện thay đổi toán tử hoặc literal.
- Phân tích điều kiện và luồng điều khiển.
- Đánh giá trên một tập test hoặc mẫu dữ liệu.

Kết quả nên được trình bày như mức độ hoặc nhóm thay đổi được nhận diện, không phải lời khẳng định tuyệt đối về tương đương.

### 9.4. Thay đổi hành vi nghiệp vụ

Ví dụ:

~~~text
when order.total >= 1000000 VND
then freeShipping()
~~~

đổi thành:

~~~text
when order.total >= 500000 VND
then freeShipping()
~~~

Structural diff cho biết literal threshold thay đổi. Semantic diff có thể diễn giải rằng phạm vi đơn hàng đủ điều kiện miễn phí vận chuyển được mở rộng.

### 9.5. Độ nhạy theo context

Một rule có thể có cùng văn bản nhưng cho kết quả khác khi:

- Schema thay đổi.
- Built-in function thay đổi.
- Currency hoặc timezone mặc định thay đổi.
- Quyền hoặc context runtime thay đổi.
- Phiên bản engine thay đổi.

Do đó, semantic comparison nên ghi nhận phiên bản dependency và context liên quan.

## 10. Diff dạng operation và patch

### 10.1. Diff và patch khác nhau

Diff mô tả sự khác biệt. Patch là tập thao tác có thể áp dụng lên tài liệu hoặc mô hình để biến phiên bản cũ thành phiên bản mới.

Một patch có thể chứa:

~~~text
ADD    /rules/MemberDiscount/condition/and
REPLACE /rules/MemberDiscount/action/rate 0.10 -> 0.15
~~~

Đường dẫn phải được định nghĩa theo định dạng dữ liệu hoặc mô hình.

### 10.2. JSON Patch

JSON Patch là định dạng chuẩn biểu diễn các thao tác trên JSON document, thường gồm add, remove, replace, move, copy và test.

Ví dụ minh họa:

~~~json
[
  {
    "op": "replace",
    "path": "/rules/MemberDiscount/rate",
    "value": 0.15
  },
  {
    "op": "add",
    "path": "/rules/MemberDiscount/conditions/1",
    "value": {
      "field": "order.total",
      "operator": ">=",
      "value": 1000000
    }
  }
]
~~~

JSON Patch thao tác trên cấu trúc JSON. Nếu DSL có semantics riêng, hệ thống vẫn cần validate patch sau khi áp dụng.

### 10.3. JSON Merge Patch

JSON Merge Patch là một cách biểu diễn cập nhật JSON theo cấu trúc object. Nó có thể đơn giản cho những thay đổi thuộc tính, nhưng việc biểu diễn xóa giá trị null và thao tác với array có giới hạn cần được hiểu đúng theo đặc tả.

Không nên chọn Merge Patch nếu cần thao tác chính xác với từng phần tử mảng hoặc cần biểu diễn move.

### 10.4. Patch có điều kiện

Một patch có thể yêu cầu giá trị cũ đúng như mong đợi trước khi thay:

~~~text
TEST /rules/MemberDiscount/rate == 0.10
REPLACE /rules/MemberDiscount/rate = 0.15
~~~

Điều này ngăn patch áp dụng nhầm lên một phiên bản đã thay đổi.

### 10.5. Atomic patch

Nếu patch có nhiều thao tác, hệ thống cần quyết định áp dụng tất cả hoặc không áp dụng thao tác nào. Với mô hình có quan hệ phụ thuộc, cập nhật từng phần có thể để lại trạng thái không hợp lệ.

### 10.6. Patch idempotent

Một patch idempotent khi áp dụng lặp lại vẫn tạo cùng trạng thái cuối. Không phải mọi thao tác add đều idempotent. Nếu cần retry qua mạng, nên có version check hoặc operation ID để tránh thêm phần tử hai lần.

## 11. Merge và three-way diff

### 11.1. Two-way diff

Two-way diff so sánh hai phiên bản A và B. Nó cho biết điểm khác nhau nhưng không nhất thiết xác định ai đã thay đổi hoặc thay đổi dựa trên phiên bản gốc nào.

### 11.2. Three-way merge

Three-way merge dùng:

- Base: phiên bản chung ban đầu.
- Ours: phiên bản được chỉnh ở nhánh hiện tại.
- Theirs: phiên bản được chỉnh ở nhánh khác.

Mục tiêu là kết hợp các thay đổi độc lập và phát hiện xung đột khi cả hai phía cùng sửa một phần không thể tự động hợp nhất.

~~~mermaid
flowchart TD
    A["Base"] --> B["Ours"]
    A --> C["Theirs"]
    B --> D["Three-way merge"]
    C --> D
    D --> E["Merged result"]
    D --> F["Conflict report"]
~~~

### 11.3. Thay đổi độc lập

Base có hai field name và email. Ours đổi name; Theirs đổi email. Nếu hai thay đổi không phụ thuộc nhau, merge có thể giữ cả hai.

### 11.4. Xung đột cùng thuộc tính

Nếu Ours đổi rate từ 0.10 thành 0.15 và Theirs đổi từ 0.10 thành 0.20, hệ thống không thể tự chọn kết quả nếu không có chính sách nghiệp vụ. Đây là conflict cần người dùng giải quyết.

### 11.5. Xung đột cấu trúc

Một nhánh xóa field trong khi nhánh kia đổi kiểu field đó. Đây là delete-modify conflict. Structural merge cần nhận diện node identity và trình bày đủ ngữ cảnh.

### 11.6. Xung đột rename

Hai nhánh có thể đổi cùng một entity sang hai tên khác nhau. Nếu có stable ID, hệ thống biết đây là cùng một entity và có thể báo rename conflict. Nếu chỉ dựa trên tên, hệ thống có thể nhầm thành xóa và thêm.

### 11.7. Không tự merge khi semantics không rõ

Nếu hai thay đổi riêng rẽ tạo ra mô hình vi phạm bất biến khi kết hợp, merge cần chạy semantic validation trên kết quả. Một phép merge cấu trúc thành công chưa chắc tạo ra mô hình hợp lệ.

## 12. Diff theo đường dẫn và định dạng trao đổi

### 12.1. Path-based diff

Diff cấu trúc thường chỉ rõ đường dẫn đến phần thay đổi:

~~~text
/entities/Customer/fields/email/type
/rules/MemberDiscount/action/rate
/workflows/Order/states/PAID/transitions
~~~

Đường dẫn giúp công cụ điều hướng đến node và áp dụng patch.

### 12.2. JSON Pointer

Nếu mô hình được tuần tự hóa thành JSON, JSON Pointer có thể dùng để chỉ vị trí trong cấu trúc. Đường dẫn cần escape đúng các ký tự đặc biệt theo chuẩn.

### 12.3. XML và XPath

Với XML, công cụ có thể dùng XPath hoặc ID của element để xác định node. Namespace XML cần được xử lý chính xác khi so sánh.

### 12.4. YAML

YAML có cú pháp và kiểu dữ liệu riêng. Một parser có thể chuyển YAML thành object model rồi so sánh cấu trúc. Cần chú ý anchor, alias, scalar typing và cách serializer biểu diễn giá trị.

### 12.5. DSL văn bản

Với DSL có grammar riêng, nên parse thành AST hoặc model trước khi tạo structural diff. Không nên cố xử lý mọi thay đổi bằng regex vì cấu trúc lồng nhau và literal có thể làm quy tắc văn bản trở nên mong manh.

### 12.6. Định dạng diff cần có version

Nếu diff được lưu hoặc gửi qua API, schema của diff cần có phiên bản. Consumer phải biết ý nghĩa operation, path, ID và metadata tương ứng.

## 13. Định dạng diff dễ đọc cho con người

### 13.1. Hiển thị theo nhóm

Một báo cáo có thể nhóm thay đổi:

~~~text
Model: Customer
  Added
    loyaltyLevel: LoyaltyLevel
  Modified
    email: String -> Optional<String>
  Removed
    legacyCode: String

Rule: MemberDiscount
  Modified
    condition: added order.total >= 1000000 VND
    action.rate: 0.10 -> 0.15
~~~

### 13.2. Mức độ tác động

Diff có thể phân loại thay đổi theo tác động:

- Informational: thay đổi comment hoặc format.
- Compatible: thay đổi không phá vỡ consumer theo quy tắc đã chọn.
- Potentially breaking: cần kiểm tra consumer hoặc dữ liệu cũ.
- Breaking: thay đổi chắc chắn làm mất khả năng tương thích theo hợp đồng.

Mức độ này phụ thuộc vào phiên bản producer/consumer và chính sách hệ thống. Không nên gắn nhãn breaking chỉ dựa vào tên thao tác mà không xét ngữ cảnh.

### 13.3. Tóm tắt và chi tiết

Giao diện có thể hiển thị số lượng node thêm, xóa, sửa ở đầu báo cáo, sau đó cho phép mở từng thay đổi. Tóm tắt không nên thay thế danh sách chi tiết hoặc che giấu những thay đổi quan trọng.

### 13.4. Hiển thị giá trị nhạy cảm

Nếu mô hình chứa secret hoặc dữ liệu cá nhân, diff cần che giá trị hoặc chỉ hiển thị trạng thái thay đổi. Không nên đưa secret cũ và mới vào log hoặc báo cáo rộng rãi.

## 14. Thuật toán diff văn bản

### 14.1. Longest Common Subsequence

Một thuật toán kinh điển để so sánh hai chuỗi dòng là tìm dãy con chung dài nhất (Longest Common Subsequence, LCS). Những dòng nằm trong LCS được xem là không đổi; các dòng còn lại được phân loại thành thêm hoặc xóa.

### 14.2. Myers diff

Thuật toán Myers tìm edit script ngắn theo số thao tác thêm và xóa cho hai chuỗi. Nó được dùng rộng rãi trong các công cụ diff văn bản.

### 14.3. Diff theo token

Đối với một dòng dài, công cụ có thể tokenize thành từ hoặc ký hiệu rồi chạy thuật toán so sánh trên chuỗi token. Điều này giúp highlight vùng thay đổi chính xác hơn.

### 14.4. Heuristic

Một số công cụ dùng heuristic để cân bằng chất lượng và tốc độ, ví dụ ưu tiên những dòng có cấu trúc giống nhau hoặc những đoạn gần vị trí tương ứng.

Heuristic có thể tạo kết quả khác nhau trong các trường hợp mơ hồ. Diff hiển thị không nhất thiết là một phép biến đổi duy nhất có thể chứng minh là tối ưu.

### 14.5. Chi phí tính toán

Với tài liệu rất lớn, so sánh toàn bộ có thể tốn thời gian và bộ nhớ. Có thể:

- Chia tài liệu theo module hoặc section.
- Dùng hash để bỏ qua phần giống hệt.
- Dùng stable ID để tìm node tương ứng.
- Chỉ diff các vùng đã thay đổi.
- Giới hạn số lượng chi tiết hiển thị.

## 15. Thuật toán structural diff

### 15.1. So sánh node theo loại và thuộc tính

Với mỗi node tương ứng, thuật toán so sánh:

- Loại node.
- ID hoặc key.
- Tên.
- Kiểu.
- Thuộc tính scalar.
- Danh sách node con.

Nếu loại node khác nhau, có thể xem là replace. Nếu cùng loại nhưng thuộc tính khác, tạo operation change cho thuộc tính.

### 15.2. So sánh danh sách

Danh sách có thể:

- Có thứ tự quan trọng, như thứ tự bước workflow.
- Không có thứ tự, như tập permission.
- Có key riêng, như danh sách field theo ID.

Thuật toán cần biết semantics collection để quyết định so sánh theo index, key hoặc nội dung.

### 15.3. Sequence alignment

Với danh sách có thứ tự, sequence alignment tìm cách ghép phần tử cũ và mới. Chèn một phần tử ở đầu không nên khiến mọi phần tử phía sau bị báo là thay thế nếu chúng vẫn tương ứng.

### 15.4. Tree edit distance

Tree edit distance là nhóm thuật toán tính chi phí biến đổi giữa hai cây thông qua thêm, xóa và sửa node. Nó có thể hữu ích cho AST diff nhưng chi phí phụ thuộc kích thước cây và thuật toán được chọn.

### 15.5. Hash theo node

Có thể tính hash nội dung chuẩn hóa của node và các node con. Nếu hash giống nhau, subtree có thể được bỏ qua nhanh. Hash là bộ lọc hiệu quả nhưng không nên thay thế so sánh chính xác khi cần bảo đảm không có va chạm.

### 15.6. Kết hợp ID và cấu trúc

Stable ID giúp nhận diện đối tượng; cấu trúc giúp xác nhận nội dung. Kết hợp cả hai thường bền hơn chỉ dựa vào vị trí hoặc tên.

## 16. So sánh và diff trong Git

### 16.1. Git diff ở cấp văn bản

Git lưu snapshot của file và hiển thị diff văn bản theo dòng. Nó rất phù hợp để review DSL dưới dạng text.

### 16.2. File được sinh tự động

Nếu DSL hoặc schema sinh ra nhiều artifact, repository có thể lưu:

- Chỉ nguồn DSL.
- Nguồn DSL và generated source.
- Nguồn cùng artifact đã biên dịch.

Mỗi lựa chọn có trade-off. Nếu commit mã sinh, diff có thể lớn nhưng reviewer thấy rõ output. Nếu không commit, build cần tái tạo artifact đúng phiên bản.

### 16.3. Custom diff driver

Git cho phép cấu hình công cụ diff riêng cho một số loại file. Một DSL có thể dùng formatter hoặc structural diff tool để hiển thị khác biệt theo cú pháp.

### 16.4. Merge driver

Một định dạng có thể dùng merge driver chuyên biệt để hợp nhất cấu trúc. Driver cần xử lý conflict và không được tự chọn dữ liệu khi hai thay đổi xung đột về ý nghĩa.

### 16.5. Review semantic change

Pull request có thể trình bày text diff và báo cáo model diff. Reviewer có thể xem cả cách viết và tác động cấu trúc.

## 17. So sánh phiên bản và quản lý lịch sử

### 17.1. Snapshot

Snapshot lưu trạng thái đầy đủ của mô hình tại một thời điểm. So sánh hai snapshot cho biết khác biệt, nhưng cần metadata để xác định nguồn và phiên bản.

### 17.2. Change log

Change log lưu các sự kiện hoặc thao tác đã xảy ra:

~~~text
2026-11-01: Added Customer.loyaltyLevel
2026-11-03: Changed MemberDiscount.rate to 0.15
2026-11-05: Removed legacyCode
~~~

Change log dễ đọc nhưng không nhất thiết đủ để tái tạo trạng thái nếu thiếu operation chính xác hoặc thứ tự.

### 17.3. Event sourcing và model snapshot

Một hệ thống có thể lưu event thay đổi mô hình và định kỳ tạo snapshot. Khi khôi phục, nó tải snapshot rồi áp dụng các event tiếp theo.

Event cần có version, thứ tự, định danh và chính sách replay. Diff giữa snapshot vẫn hữu ích để xác nhận kết quả sau replay.

### 17.4. Provenance

Diff nên có thể ghi nhận:

- Phiên bản nguồn.
- Tác giả hoặc actor.
- Thời điểm.
- Công cụ tạo diff.
- Phiên bản schema.
- Commit hoặc revision ID.
- Môi trường và context liên quan.

Metadata giúp điều tra khi một thay đổi được tạo tự động hoặc đồng bộ qua nhiều hệ thống.

### 17.5. Lưu trữ diff hay snapshot?

Snapshot giúp đọc trực tiếp trạng thái hiện tại. Diff tiết kiệm hơn khi thay đổi nhỏ nhưng cần base chính xác để áp dụng. Nhiều hệ thống kết hợp cả hai.

## 18. Đồng bộ và phát hiện xung đột

### 18.1. Optimistic concurrency

Khi một client đọc mô hình ở version 12 rồi gửi patch, server có thể yêu cầu version hiện tại vẫn là 12. Nếu mô hình đã lên version 13, server từ chối patch hoặc yêu cầu client merge lại.

### 18.2. ETag hoặc revision

Một tài liệu có thể mang ETag, hash hoặc revision number. Client gửi điều kiện cập nhật dựa trên revision đã đọc để tránh ghi đè thay đổi mới hơn.

### 18.3. Đồng bộ hai chiều

Khi local và remote đều có thay đổi, cần base chung để phân biệt:

- Thay đổi chỉ có ở local.
- Thay đổi chỉ có ở remote.
- Thay đổi cùng nội dung ở cả hai.
- Thay đổi xung đột.

### 18.4. Last-write-wins

Chính sách lấy bản ghi mới nhất có thể đơn giản nhưng dễ làm mất thay đổi hợp lệ nếu hai người sửa độc lập. Nó chỉ phù hợp khi domain chấp nhận semantics đó hoặc dữ liệu có thể được tái tạo.

### 18.5. Conflict resolution

Xung đột có thể được giải quyết bằng:

- Chọn một phía.
- Kết hợp thủ công.
- Áp dụng quy tắc miền.
- Chạy merge tool.
- Yêu cầu người có quyền phê duyệt.

Với thay đổi rule hoặc quyền truy cập, tự động chọn một phía có thể gây hậu quả lớn; cần policy và audit trail.

## 19. Diff và migration

### 19.1. Từ schema diff đến migration plan

Schema diff có thể được chuyển thành kế hoạch migration:

~~~text
ADD COLUMN customers.loyalty_level
RENAME COLUMN customers.legacy_code TO customers.external_code
ALTER COLUMN customers.email DROP NOT NULL
~~~

Các câu lệnh trên chỉ minh họa. Migration thực tế cần theo hệ quản trị dữ liệu và chính sách dữ liệu.

### 19.2. Thay đổi cần migration dữ liệu

Đổi tên field có thể yêu cầu di chuyển dữ liệu. Đổi kiểu có thể cần chuyển đổi giá trị. Xóa field có thể cần xác nhận dữ liệu không còn được sử dụng.

### 19.3. Migration tự động và thủ công

Một số thay đổi có thể tạo migration tự động, ví dụ thêm field nullable. Những thay đổi khác cần logic thủ công, ví dụ tách fullName thành firstName và lastName.

Diff tool nên phân loại mức độ tự động hóa và không tự tạo migration phá hủy nếu chưa có chính sách.

### 19.4. Dry run migration

Dry run có thể báo:

- Số bản ghi bị ảnh hưởng.
- Giá trị không chuyển đổi được.
- Dữ liệu sẽ bị xóa hoặc biến đổi.
- Thao tác cần downtime.
- Rollback có khả thi không.

### 19.5. Rollback

Không phải mọi migration đều đảo ngược được. Nếu một field bị xóa hoặc giá trị bị làm tròn, dữ liệu gốc có thể mất. Migration plan cần mô tả khả năng rollback và yêu cầu backup.

## 20. Bảo mật khi tạo và áp dụng diff

### 20.1. Diff có thể làm lộ dữ liệu

Một báo cáo diff có thể hiển thị secret cũ và mới, token, thông tin cá nhân hoặc cấu hình nội bộ. Cần áp dụng masking theo loại trường và quyền người xem.

### 20.2. Kiểm tra quyền truy cập

Không phải ai đọc được tài liệu cũng có quyền xem mọi trường. Structural diff phải áp dụng quyền ở cả node và giá trị, tránh rò rỉ qua báo cáo thay đổi.

### 20.3. Patch không đáng tin cậy

Patch nhận từ client hoặc hệ thống ngoài cần được validate:

- Đường dẫn có nằm trong phạm vi cho phép không?
- Operation có hợp lệ không?
- Kiểu giá trị có phù hợp không?
- Có thể thay đổi trường protected không?
- Patch có tạo chu trình hoặc trạng thái không hợp lệ không?

### 20.4. Chống replay và áp dụng nhầm phiên bản

Patch nên gắn với base revision hoặc hash. Nếu áp dụng lên một base khác, hệ thống cần từ chối hoặc yêu cầu merge lại.

### 20.5. Giới hạn tài nguyên

Tài liệu có thể rất lớn hoặc được tạo có chủ đích để khiến diff tốn thời gian. Cần giới hạn kích thước, độ sâu, số node và thời gian xử lý.

### 20.6. Audit

Việc áp dụng patch nên ghi lại actor, thời điểm, base revision, kết quả và operation. Audit log cần bảo vệ khỏi sửa đổi trái phép.

## 21. Hiệu năng và khả năng mở rộng

### 21.1. Bỏ qua nội dung không đổi bằng hash

Hash nội dung chuẩn hóa có thể giúp xác định nhanh những phần không thay đổi. Nếu hash giống nhau, có thể bỏ qua so sánh sâu theo cấu trúc trong phạm vi giả định hash đáng tin cậy và collision được xử lý phù hợp.

### 21.2. Chia theo module hoặc subtree

Một mô hình lớn có thể được chia thành module, entity hoặc rule. Diff từng phần giúp giới hạn vùng tính toán và dễ hiển thị.

### 21.3. Incremental diff

Nếu hệ thống đã biết vùng nào thay đổi, có thể chỉ tính diff cho subtree bị ảnh hưởng. Điều này hữu ích trong IDE và hệ thống đồng bộ thường xuyên.

### 21.4. Lazy rendering

Một báo cáo có hàng nghìn thay đổi không cần render tất cả ngay lập tức. Có thể hiển thị summary và tải chi tiết khi người dùng mở từng nhóm.

### 21.5. Giới hạn heuristic

Structural matching phức tạp có thể tốn CPU. Có thể đặt ngưỡng để chuyển sang diff đơn giản hơn và thông báo rằng kết quả matching có thể kém chính xác hơn.

### 21.6. Đo lường

Nên đo:

- Thời gian parse hai phiên bản.
- Thời gian canonicalization.
- Thời gian matching.
- Số node được so sánh.
- Số operation tạo ra.
- Bộ nhớ dùng.
- Thời gian serialize và render.

Những số liệu này giúp tìm đúng nút thắt thay vì tối ưu toàn bộ thuật toán một cách mù quáng.

## 22. Kiểm thử công cụ so sánh và diff

### 22.1. Test bằng nhau

Tài liệu giống hệt, tài liệu khác format nhưng cùng cấu trúc và tài liệu có comment khác nhau cần cho kết quả theo đúng mức so sánh được chọn.

### 22.2. Test thêm, xóa và sửa

Tạo các fixture có:

- Thêm một field.
- Xóa một rule.
- Đổi kiểu.
- Sửa literal.
- Thêm node con.
- Di chuyển phần tử.
- Đổi tên có stable ID.

### 22.3. Test thứ tự collection

Xác nhận collection có thứ tự được diff theo vị trí, còn set hoặc map được so sánh theo key nếu semantics quy định như vậy.

### 22.4. Test patch round trip

Với tài liệu A và B:

1. Tạo diff hoặc patch từ A sang B.
2. Áp dụng patch lên bản sao A.
3. Chuẩn hóa kết quả.
4. So sánh với B.

Kết quả cần tương đương theo tiêu chí đã chọn.

### 22.5. Test three-way merge

Kiểm tra thay đổi độc lập được kết hợp, thay đổi cùng field được báo conflict, delete-modify được nhận diện và kết quả merge vượt qua semantic validation.

### 22.6. Test tương thích

Các schema version khác nhau cần được so sánh theo đúng quy tắc compatibility. Kiểm thử cả producer cũ với consumer mới và producer mới với consumer cũ nếu hệ thống yêu cầu.

### 22.7. Test dữ liệu nhạy cảm

Xác nhận secret và trường protected không xuất hiện trong diff cho người không có quyền.

### 22.8. Test tài liệu lớn và lỗi định dạng

Kiểm tra giới hạn kích thước, độ sâu, node lỗi, Unicode, encoding và file bị cắt cụt.

## 23. Ví dụ tổng hợp: so sánh hai phiên bản mô hình đơn hàng

Phiên bản cũ:

~~~yaml
entity: Order
fields:
  - name: id
    type: OrderId
    required: true
  - name: total
    type: Money
    required: true
  - name: note
    type: String
    required: false
rules:
  - id: free-shipping
    condition: total >= 1000000 VND
    action: freeShipping
~~~

Phiên bản mới:

~~~yaml
entity: Order
fields:
  - name: id
    type: OrderId
    required: true
  - name: total
    type: Money
    required: true
  - name: note
    type: Optional<String>
    required: false
  - name: channel
    type: SalesChannel
    required: true
rules:
  - id: free-shipping
    condition: total >= 750000 VND and channel == ONLINE
    action: freeShipping
~~~

### 23.1. Text diff

Text diff cho thấy dòng type của note thay đổi, một field channel được thêm và điều kiện rule được sửa. Nếu serializer sắp xếp lại key, text diff có thể lớn hơn thay đổi thực tế.

### 23.2. Structural diff

~~~text
Entity Order
  Modified field:
    note:
      type: String -> Optional<String>
  Added field:
    channel: SalesChannel
  Modified rule:
    free-shipping.condition:
      added predicate: channel == ONLINE
      threshold: 1000000 VND -> 750000 VND
~~~

### 23.3. Đánh giá tương thích

Thay đổi note từ String thành Optional<String> có thể yêu cầu cập nhật consumer. Thêm channel bắt buộc có thể phá vỡ dữ liệu cũ nếu không có default hoặc migration. Hạ ngưỡng miễn phí vận chuyển có thể thay đổi kết quả nghiệp vụ.

### 23.4. Migration plan

Một kế hoạch có thể:

1. Thêm cột channel.
2. Gán giá trị cho các bản ghi hiện có hoặc cho phép trạng thái chưa xác định trong giai đoạn chuyển tiếp.
3. Cập nhật consumer đọc note theo Optional.
4. Triển khai rule mới.
5. Kiểm tra kết quả trên dữ liệu thử nghiệm.

### 23.5. Merge hai thay đổi độc lập

Giả sử một nhánh thêm field channel, nhánh khác sửa threshold. Structural three-way merge có thể kết hợp hai thay đổi nếu chúng không xung đột, sau đó chạy semantic validation trên mô hình kết quả.

## 24. Những sai lầm thường gặp

### 24.1. Dùng text diff cho mọi mục đích

Text diff có thể báo nhiều khác biệt hình thức và bỏ qua ý nghĩa cấu trúc. Với schema hoặc mô hình miền, nên bổ sung structural diff.

### 24.2. Chuẩn hóa quá mức

Sắp xếp lại list hoặc loại bỏ comment có ý nghĩa có thể làm mất thông tin. Chỉ chuẩn hóa những gì đặc tả xác định là không quan trọng.

### 24.3. Dựa hoàn toàn vào tên để matching

Rename có thể bị hiểu thành xóa và thêm. Stable ID hoặc matching theo cấu trúc giúp giữ identity.

### 24.4. Xem mọi thay đổi kiểu là tương thích

Một kiểu rộng hơn về mặt số học chưa chắc tương thích với consumer, serializer hoặc hệ thống lưu trữ. Cần xét toàn bộ hợp đồng.

### 24.5. Coi structural diff là semantic proof

AST giống nhau không đảm bảo hành vi giống nhau nếu schema, built-in hoặc runtime khác phiên bản. Ngược lại, AST khác nhau không có nghĩa hành vi luôn khác.

### 24.6. Áp dụng patch không kiểm tra base

Patch được tạo từ revision cũ có thể ghi đè thay đổi mới. Cần version check, hash hoặc precondition.

### 24.7. Merge thành công nhưng mô hình không hợp lệ

Kết quả merge cấu trúc vẫn có thể vi phạm kiểu, reference hoặc invariant. Phải validate mô hình sau merge.

### 24.8. Hiển thị secret trong diff

Diff có thể vô tình đưa giá trị nhạy cảm vào log, pull request hoặc email. Cần masking và kiểm soát quyền.

### 24.9. Không version hóa định dạng diff

Nếu operation hoặc path semantics thay đổi, consumer cũ có thể áp dụng sai patch. Định dạng trao đổi cần version.

## 25. Quy trình xây dựng chức năng so sánh và diff

Một quy trình triển khai có thể gồm:

1. **Xác định mục đích:** review văn bản, so sánh cấu trúc, đánh giá tương thích hay tạo migration.
2. **Chọn biểu diễn đầu vào:** text, AST, model, schema hoặc artifact.
3. **Xác định equality:** byte, text, structural, type hay semantic.
4. **Định nghĩa canonicalization:** encoding, thứ tự, literal, Unicode và comment.
5. **Thiết kế identity:** stable ID, key hoặc matching heuristic.
6. **Triển khai matching:** node, list, map và rename.
7. **Tạo operation:** add, remove, replace, move và metadata.
8. **Thiết kế patch:** path, precondition, version và atomicity.
9. **Xử lý merge:** base, hai nhánh, conflict và validation sau merge.
10. **Đánh giá compatibility:** producer, consumer, dữ liệu và runtime.
11. **Thiết kế hiển thị:** summary, detail, severity và masking.
12. **Kiểm thử:** round trip, conflict, dữ liệu lớn và bảo mật.
13. **Theo dõi hiệu năng:** parse, match, diff và render.
14. **Version hóa:** schema diff, patch format và metadata nguồn.

## 26. Câu hỏi tự đánh giá

1. Phân biệt so sánh và diff.
2. Text diff khác structural diff và semantic diff như thế nào?
3. Vì sao cần canonicalization trước khi so sánh một số định dạng?
4. Stable ID giúp nhận diện rename ra sao?
5. Vì sao thứ tự list và thứ tự key map cần được xử lý khác nhau?
6. Structural diff có thể tạo ra migration plan như thế nào?
7. JSON Patch khác JSON Merge Patch ở mục đích và khả năng biểu diễn ra sao?
8. Three-way merge cần những phiên bản nào?
9. Vì sao kết quả merge vẫn cần semantic validation?
10. Optimistic concurrency giúp tránh ghi đè thay đổi như thế nào?
11. Những thông tin nhạy cảm nào có thể bị lộ qua diff?
12. Làm thế nào để kiểm tra patch round trip?

## Kết luận

So sánh và diff giúp theo dõi sự thay đổi của tài liệu, schema và mô hình DSL trong quá trình lưu trữ, review, đồng bộ và triển khai. Text diff phù hợp với thay đổi văn bản; AST và model diff mô tả thay đổi cấu trúc; semantic diff cố gắng giải thích tác động đến hành vi. Mỗi mức có mục đích và giới hạn riêng.

Một hệ thống diff đáng tin cậy cần xác định tiêu chí equality, chuẩn hóa đúng những khác biệt không có ý nghĩa, nhận diện node bằng identity ổn định, tạo operation có đường dẫn rõ và kiểm tra patch trên đúng base revision. Three-way merge cần phát hiện xung đột và xác thực kết quả sau khi hợp nhất. Khi kết hợp diff với versioning, migration, quyền truy cập và source metadata, nhóm phát triển có thể hiểu và kiểm soát thay đổi DSL một cách chính xác hơn.
