# Tài liệu hóa ngữ nghĩa

## 1. Ngữ nghĩa DSL là gì?

Ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*) cung cấp cú pháp để người dùng diễn đạt khái niệm và hành động trong một lĩnh vực cụ thể. Grammar cho biết một đoạn văn bản có được viết đúng cấu trúc hay không; **ngữ nghĩa (*semantics*)** giải thích đoạn văn bản hợp lệ đó có nghĩa gì và hệ thống phải xử lý nó như thế nào.

**Tài liệu hóa ngữ nghĩa** là việc mô tả có hệ thống ý nghĩa của các cấu trúc trong DSL, điều kiện sử dụng, kết quả, tác dụng phụ, lỗi và những quy tắc mà mọi implementation cần tuân theo. Tài liệu này đóng vai trò như hợp đồng giữa người thiết kế ngôn ngữ, người viết DSL, nhóm triển khai runtime và các công cụ hỗ trợ như editor, validator, compiler hoặc interpreter.

Ví dụ một DSL tính giá:

~~~text
price = item.unitPrice * item.quantity
if customer.tier == "GOLD" then
    discount = price * 0.10
end
total = price - discount
~~~

Grammar có thể xác nhận rằng phép nhân, phép so sánh, câu lệnh điều kiện và phép gán được viết đúng cú pháp. Nhưng chỉ grammar chưa trả lời được:

- Phép nhân giữa tiền và số lượng trả về kiểu gì?
- So sánh chuỗi có phân biệt hoa thường không?
- Điều kiện có thực hiện đánh giá ngắn mạch không?
- Nếu customer không tồn tại hoặc tier là null thì sao?
- discount chưa được gán trước đó có giá trị mặc định nào?
- Việc tính giá có làm thay đổi dữ liệu đơn hàng hay chỉ tạo kết quả tạm?
- Khi một biểu thức lỗi, runtime dừng ngay hay thu thập nhiều lỗi?

Đây là những câu hỏi thuộc ngữ nghĩa. Nếu không được tài liệu hóa, người dùng có thể hiểu cùng một biểu thức theo nhiều cách, còn các implementation khác nhau có thể cho kết quả không nhất quán.

## 2. Phân biệt cú pháp, ngữ nghĩa và triển khai

Ba khái niệm này có liên quan nhưng giải quyết những câu hỏi khác nhau.

| Lớp | Câu hỏi chính | Ví dụ |
|---|---|---|
| Cú pháp (*syntax*) | Cấu trúc văn bản nào được chấp nhận? | Một câu lệnh gán có dạng `name = expression` |
| Ngữ nghĩa (*semantics*) | Cấu trúc hợp lệ biểu đạt điều gì? | Câu lệnh gán đánh giá biểu thức rồi cập nhật biến trong môi trường hiện tại |
| Triển khai (*implementation*) | Hệ thống thực hiện ngữ nghĩa bằng cách nào? | Interpreter dùng bảng biến trong bộ nhớ; compiler sinh bytecode |

Ví dụ, DSL quy định toán tử cộng trên số nguyên có nghĩa là cộng số học. Một implementation có thể dùng phép cộng CPU, implementation khác có thể dùng bytecode hoặc tối ưu biểu thức. Miễn kết quả và hành vi quan sát được đáp ứng đặc tả, các cách triển khai đều phù hợp.

Tài liệu ngữ nghĩa cần mô tả hành vi có thể quan sát từ phía người dùng DSL. Không nên biến chi tiết nội bộ như tên class, cấu trúc package hay thuật toán tối ưu thành quy tắc ngôn ngữ, trừ khi chúng ảnh hưởng trực tiếp đến kết quả hoặc được công bố như một phần API.

## 3. Vì sao cần tài liệu hóa ngữ nghĩa?

Một đặc tả ngữ nghĩa rõ ràng mang lại nhiều lợi ích:

- **Giảm nhập nhằng:** người viết biết chính xác mỗi biểu thức, câu lệnh và cấu hình có ý nghĩa gì.
- **Giữ tính nhất quán giữa implementation:** interpreter, compiler, validator và công cụ khác có chung chuẩn hành vi.
- **Hỗ trợ học và sử dụng DSL:** người dùng có thể tra cứu cách hoạt động của từng cấu trúc mà không cần đọc mã nguồn runtime.
- **Làm cơ sở kiểm thử:** mỗi quy tắc ngữ nghĩa có thể chuyển thành ví dụ và ca kiểm thử conformance.
- **Hỗ trợ nâng cấp:** nhóm có thể đánh giá thay đổi ngữ nghĩa ảnh hưởng đến tài liệu DSL cũ ra sao.
- **Giúp điều tra lỗi:** người dùng và nhóm vận hành có cùng cách hiểu về kết quả, lỗi và tác dụng phụ.
- **Tách hợp đồng khỏi kỹ thuật triển khai:** nhóm có thể thay đổi parser, runtime hoặc ngôn ngữ chủ mà vẫn giữ hành vi đã công bố.

Nếu một DSL chỉ có một prototype, nhóm có thể bắt đầu bằng mô tả ngắn và ví dụ. Khi DSL được nhiều nhóm sử dụng, có dữ liệu lưu lâu dài hoặc nhiều runtime, cần một đặc tả chặt chẽ hơn.

## 4. Những nội dung cần có trong đặc tả ngữ nghĩa

Tùy quy mô DSL, tài liệu có thể gồm các phần sau:

1. Mục tiêu, phạm vi và đối tượng sử dụng.
2. Mô hình khái niệm và thuật ngữ.
3. Kiểu dữ liệu và giá trị.
4. Ý nghĩa của từng biểu thức và toán tử.
5. Ý nghĩa của từng câu lệnh, declaration và cấu trúc điều khiển.
6. Quy tắc đánh giá, thứ tự thực thi và phạm vi.
7. Quy tắc chuyển đổi kiểu, null và giá trị mặc định.
8. Trạng thái, môi trường và tác dụng phụ.
9. Lỗi, ngoại lệ và cơ chế xử lý.
10. Quyền truy cập và giới hạn thực thi.
11. Ví dụ có kết quả kỳ vọng.
12. Quy tắc tương thích, phiên bản và thay đổi ngữ nghĩa.
13. Bộ kiểm thử tham chiếu hoặc conformance suite.

Không phải DSL nào cũng cần mọi mục. Một DSL khai báo cấu hình tĩnh có thể tập trung vào giá trị, quan hệ và validation. Một DSL workflow hoặc quy tắc có thể cần mô tả rõ thứ tự thực thi, trạng thái, retry, timeout và tác dụng phụ.

## 5. Bắt đầu từ mô hình khái niệm và thuật ngữ

### 5.1. Xác định khái niệm miền

Trước khi viết ý nghĩa từng cú pháp, hãy xác định những khái niệm cốt lõi của miền. Ví dụ DSL đơn hàng có thể có:

- Customer: khách hàng.
- Product: sản phẩm.
- Order: đơn hàng.
- OrderLine: dòng hàng.
- Money: giá trị tiền tệ.
- Discount: khoản giảm giá.
- OrderStatus: trạng thái đơn hàng.

Các thuật ngữ cần có định nghĩa ổn định. Nếu tài liệu dùng lẫn lộn "đơn", "đơn hàng", "giao dịch" để chỉ cùng một khái niệm, người đọc khó xác định các quy tắc có áp dụng cùng đối tượng hay không.

### 5.2. Tạo glossary

Một bảng thuật ngữ giúp người đọc hiểu cùng một ngôn ngữ:

| Thuật ngữ | Định nghĩa | Ghi chú |
|---|---|---|
| Rule | Một quy tắc gồm điều kiện và hành động | Có thể được đánh giá theo context |
| Context | Tập dữ liệu và capability được cung cấp khi đánh giá rule | Không đồng nghĩa với biến toàn cục |
| Evaluation | Quá trình tính giá trị của biểu thức | Có thể thuần hoặc có tác dụng phụ |
| Validation | Kiểm tra cấu trúc và điều kiện hợp lệ | Không nhất thiết thực thi hành động |
| Diagnostic | Thông tin mô tả lỗi hoặc cảnh báo | Có mã, mức độ và vị trí |
| Runtime | Thành phần thực thi chương trình DSL | Có thể là interpreter hoặc engine |

Nên định nghĩa thuật ngữ một lần rồi sử dụng nhất quán trong toàn bộ đặc tả.

### 5.3. Phân biệt từ khóa với khái niệm miền

Một từ khóa như `when` là thành phần cú pháp. "Điều kiện" là khái niệm miền hoặc khái niệm ngôn ngữ mà từ khóa đó biểu đạt. Tài liệu cần nói rõ cả hai: cấu trúc viết ra sao và điều kiện được đánh giá như thế nào.

## 6. Mô tả ngữ nghĩa của từng cấu trúc DSL

Một cách thực tế là dùng cùng một mẫu tài liệu cho mỗi construct. Ví dụ, với câu lệnh điều kiện:

### 6.1. Mẫu mô tả một construct

**Tên:** Câu lệnh điều kiện `if`.

**Cú pháp:**

~~~text
if BooleanExpression then
    Statement*
else
    Statement*
end
~~~

**Ý nghĩa:** Đánh giá biểu thức điều kiện. Nếu kết quả là true, thực hiện nhánh then; nếu false, thực hiện nhánh else. Nếu không có nhánh else, không thực hiện câu lệnh nào trong trường hợp điều kiện false.

**Điều kiện hợp lệ:**

- Biểu thức điều kiện phải có kiểu Boolean.
- Các câu lệnh bên trong phải hợp lệ trong scope hiện tại.
- Mỗi nhánh phải kết thúc theo quy tắc block của DSL.

**Thứ tự đánh giá:**

1. Đánh giá biểu thức điều kiện đúng một lần.
2. Chọn một nhánh dựa trên kết quả.
3. Thực hiện các câu lệnh trong nhánh được chọn theo thứ tự từ trên xuống.
4. Bỏ qua nhánh còn lại.

**Kết quả:** Câu lệnh không tạo giá trị trả về; nó có thể làm thay đổi trạng thái nếu các câu lệnh bên trong có tác dụng phụ.

**Lỗi:** Nếu điều kiện trả về kiểu không phải Boolean, phát sinh lỗi kiểu trước khi thực thi nhánh. Nếu đánh giá điều kiện gặp lỗi runtime, lỗi được truyền theo chính sách lỗi của DSL.

**Ví dụ:**

~~~text
if order.total >= 1000000 then
    discount = 0.10
else
    discount = 0
end
~~~

Với cùng một mẫu, người viết tài liệu có thể mô tả phép toán, lời gọi hàm, khai báo, rule, workflow step và cấu hình.

### 6.2. Mẫu bảng cho toán tử

| Thuộc tính | Nội dung cần mô tả |
|---|---|
| Ký hiệu | Cách viết toán tử |
| Số toán hạng | Unary, binary hoặc nhiều toán hạng |
| Kiểu được hỗ trợ | Các kiểu đầu vào hợp lệ |
| Kết quả | Kiểu và miền giá trị đầu ra |
| Thứ tự đánh giá | Trái trước phải trước hay có quy tắc khác |
| Tác dụng phụ | Có thay đổi trạng thái hoặc gọi dịch vụ không |
| Lỗi | Điều kiện gây lỗi và loại lỗi |
| Ví dụ | Đầu vào và kết quả kỳ vọng |

Đặc tả theo mẫu giúp người đọc so sánh các construct và giúp nhóm triển khai không bỏ quên các khía cạnh quan trọng.

## 7. Các cách hình thức hóa ngữ nghĩa

Không phải DSL nào cũng cần ký hiệu toán học. Tuy nhiên, biết các cách hình thức hóa giúp lựa chọn mức độ chính xác phù hợp.

### 7.1. Ngữ nghĩa vận hành (*operational semantics*)

Ngữ nghĩa vận hành mô tả cách chương trình thực hiện qua các bước hoặc trạng thái chuyển tiếp. Nó trả lời câu hỏi "khi chạy cấu trúc này, trạng thái tiếp theo là gì?".

Ví dụ, môi trường thực thi được ký hiệu là `σ`, ánh xạ tên biến đến giá trị. Câu lệnh gán:

~~~text
x = e
~~~

có thể được mô tả bằng quy tắc:

~~~text
⟨e, σ⟩ ⇓ v
────────────────────────────
⟨x = e, σ⟩ → σ[x ↦ v]
~~~

Ý nghĩa:

1. Đánh giá biểu thức `e` trong môi trường `σ` để thu được giá trị `v`.
2. Tạo trạng thái mới trong đó `x` được gán giá trị `v`.
3. Các biến khác giữ nguyên.

Ký hiệu chỉ là một cách mô tả. Đặc tả thực tế cần định nghĩa rõ `σ`, miền giá trị, lỗi và cách xử lý biến chưa khai báo.

Ngữ nghĩa vận hành hữu ích cho DSL có thứ tự thực thi quan trọng, như ngôn ngữ biểu thức, workflow, scripting hoặc quy tắc có tác dụng phụ.

### 7.2. Ngữ nghĩa chỉ định (*denotational semantics*)

Ngữ nghĩa chỉ định ánh xạ một cấu trúc DSL sang một ý nghĩa toán học hoặc một miền giá trị trừu tượng.

Ví dụ, biểu thức số học có thể được ánh xạ thành hàm từ môi trường sang giá trị:

~~~text
⟦expression⟧ : Environment → Value
~~~

Với biến:

~~~text
⟦x⟧(ρ) = ρ(x)
~~~

Với phép cộng:

~~~text
⟦e1 + e2⟧(ρ) = ⟦e1⟧(ρ) + ⟦e2⟧(ρ)
~~~

Trong đó `ρ` là môi trường ánh xạ tên biến sang giá trị. Với ngôn ngữ có lỗi, hàm có thể trả về một kiểu kết quả như `Result<Value, Error>` thay vì chỉ trả về `Value`.

Cách tiếp cận này hữu ích khi muốn định nghĩa ý nghĩa của biểu thức một cách độc lập với thuật toán thực thi cụ thể.

### 7.3. Ngữ nghĩa tiên đề (*axiomatic semantics*)

Ngữ nghĩa tiên đề mô tả hành vi bằng các điều kiện logic trước và sau thao tác, thường dùng Hoare triple:

~~~text
{P} C {Q}
~~~

Trong đó:

- `P` là precondition, điều kiện trước khi chạy.
- `C` là câu lệnh hoặc chương trình.
- `Q` là postcondition, điều kiện cần đúng sau khi chạy nếu thao tác kết thúc theo giả định của đặc tả.

Ví dụ:

~~~text
{x >= 0} x = x + 1 {x > 0}
~~~

Đặc tả này nói rằng nếu trước khi gán `x` không âm, sau khi gán `x + 1` thì `x` dương.

Ngữ nghĩa tiên đề phù hợp để tài liệu hóa invariant, thao tác miền quan trọng, quyền và điều kiện an toàn.

### 7.4. Mô tả bằng văn xuôi có cấu trúc

Với nhiều DSL nghiệp vụ, mô tả bằng văn xuôi kết hợp bảng, ví dụ và kết quả kỳ vọng là đủ. Điều quan trọng là văn xuôi phải cụ thể, tránh các câu như "hệ thống xử lý phù hợp" hoặc "giá trị được tính như bình thường".

Thay vào đó, hãy nêu rõ thứ tự, kiểu, điều kiện, kết quả và lỗi. Ký hiệu hình thức nên được dùng khi nó làm giảm nhập nhằng, không phải để trang trí tài liệu.

## 8. Mô tả môi trường và mô hình đánh giá

Một biểu thức không chỉ có ý nghĩa dựa trên văn bản; nó còn phụ thuộc môi trường đánh giá.

### 8.1. Environment

Environment là ánh xạ từ tên định danh đến giá trị hoặc ký hiệu. Ví dụ:

~~~text
customer.age = 25
order.total = 1200000
discountRate = 0.10
~~~

Một context có thể cung cấp các biến `customer`, `order` và `discountRate`. Đặc tả cần nói:

- Những tên nào được cung cấp sẵn?
- Người dùng có được khai báo thêm biến không?
- Scope của biến là module, rule, block hay lần thực thi?
- Biến chưa khai báo gây lỗi hay nhận giá trị mặc định?
- Biến có thể bị ghi đè không?
- Tên có phân biệt chữ hoa thường không?

### 8.2. Store và trạng thái

Với DSL có biến thay đổi được, có thể phân biệt environment và store:

- Environment ánh xạ tên đến vị trí hoặc binding.
- Store ánh xạ vị trí đến giá trị hiện tại.

Sự phân biệt này hữu ích khi có tham chiếu, closure hoặc biến có thể thay đổi. DSL đơn giản có thể gộp hai khái niệm thành một bảng biến, nhưng tài liệu vẫn cần nói rõ hành vi quan sát được.

### 8.3. Context và capability

Trong DSL nghiệp vụ, context có thể chứa dữ liệu và các thao tác được phép:

~~~text
context:
    customer: Customer
    order: Order
    services:
        inventory: InventoryService
        mailer: MailService
~~~

Tài liệu cần phân biệt dữ liệu có thể đọc với capability có thể gọi. Ví dụ rule được phép đọc `order.total` nhưng chỉ một số vai trò mới được gọi `mailer.send`. Điều này vừa là ngữ nghĩa vừa là hợp đồng bảo mật.

### 8.4. Giá trị mặc định

Nếu DSL cho phép bỏ qua thuộc tính, phải quy định rõ giá trị mặc định và thời điểm áp dụng.

Ví dụ:

~~~text
task "backup" {
    command = "backup-data"
}
~~~

Nếu `timeout` không được khai báo, nó có thể nhận mặc định 30 giây, không giới hạn hoặc một giá trị được kế thừa từ project. Những lựa chọn này ảnh hưởng trực tiếp đến hành vi, nên phải được công bố rõ.

## 9. Ngữ nghĩa kiểu dữ liệu và chuyển đổi kiểu

### 9.1. Kiểu nguyên thủy và kiểu miền

Tài liệu cần định nghĩa các kiểu DSL hỗ trợ, chẳng hạn:

| Kiểu | Ý nghĩa | Ví dụ |
|---|---|---|
| Boolean | Giá trị đúng/sai | `true`, `false` |
| Integer | Số nguyên | `42` |
| Decimal | Số thập phân chính xác theo quy tắc DSL | `12.50` |
| String | Chuỗi ký tự | `"hello"` |
| Date | Ngày lịch | `2026-11-15` |
| DateTime | Thời điểm có quy tắc múi giờ rõ | `2026-11-15T10:00:00Z` |
| Duration | Khoảng thời gian | `5 minutes` |
| Money | Giá trị tiền và đơn vị tiền tệ | `100000 VND` |
| List | Tập giá trị có thứ tự | `[1, 2, 3]` |

Kiểu miền như `Money`, `EmailAddress`, `OrderStatus` có thể mang quy tắc bổ sung ngoài kiểu cơ sở.

### 9.2. Type checking

Tài liệu nên nêu các toán tử và hàm chấp nhận kiểu nào.

Ví dụ:

| Biểu thức | Hợp lệ? | Lý do |
|---|---|---|
| `3 + 4` | Có | Cộng hai số nguyên |
| `"a" + "b"` | Theo đặc tả | Có thể là nối chuỗi nếu DSL hỗ trợ |
| `3 + "4"` | Thường không | Hai kiểu không tương thích nếu không có coercion |
| `true and false` | Có | Toán tử logic nhận Boolean |
| `order.total > 0` | Có nếu total là kiểu số hoặc Money hỗ trợ so sánh | Phụ thuộc kiểu miền |

Không nên để người dùng tự đoán hệ kiểu từ implementation. Hãy mô tả kiểu đầu vào, kiểu đầu ra và quy tắc lỗi.

### 9.3. Coercion và conversion

Nếu DSL cho phép chuyển kiểu tự động (*implicit coercion*), cần nêu:

- Những cặp kiểu nào có thể chuyển.
- Chuyển đổi có mất dữ liệu không.
- Chuyển đổi có phụ thuộc locale không.
- Chuyển đổi thất bại gây lỗi hay trả null.
- Thứ tự ưu tiên khi có nhiều cách chuyển.

Ví dụ, chuyển Integer sang Decimal có thể an toàn; chuyển Decimal sang Integer có thể cần quy tắc làm tròn hoặc từ chối phần thập phân. Chuyển String sang Date cần định dạng rõ ràng và không nên phụ thuộc locale của máy chạy.

### 9.4. Null, missing và optional

Ba trạng thái này không phải lúc nào cũng giống nhau:

- **Missing:** trường không được khai báo trong tài liệu.
- **Null:** trường được khai báo nhưng có giá trị null.
- **Optional:** kiểu hoặc schema cho phép không có giá trị.

Đặc tả cần xác định cách truy cập trường thiếu, so sánh với null, áp dụng giá trị mặc định và lan truyền null trong biểu thức. Nếu DSL có kiểu optional, cần mô tả thao tác unwrap hoặc kiểm tra sự tồn tại.

## 10. Thứ tự đánh giá và tính chất biểu thức

### 10.1. Precedence và associativity

Ngữ nghĩa biểu thức phụ thuộc cách nhóm toán tử. Ví dụ:

~~~text
2 + 3 * 4
~~~

thường có nghĩa là `2 + (3 * 4)` vì phép nhân có độ ưu tiên cao hơn phép cộng.

Đặc tả cần có bảng precedence và associativity:

| Mức | Toán tử | Associativity |
|---:|---|---|
| Cao | `()` | Nhóm biểu thức |
| 1 | `*`, `/` | Trái |
| 2 | `+`, `-` | Trái |
| 3 | `<`, `<=`, `>`, `>=` | Theo đặc tả |
| 4 | `==`, `!=` | Theo đặc tả |
| 5 | `and` | Trái hoặc theo quy tắc Boolean |
| 6 | `or` | Trái hoặc theo quy tắc Boolean |

Thứ tự cụ thể phải khớp grammar và đặc tả của DSL. Nếu phép so sánh không được nối chuỗi, cần ghi rõ `a < b < c` bị từ chối hay có ý nghĩa riêng.

### 10.2. Evaluation order

Với biểu thức có nhiều toán hạng, phải xác định thứ tự đánh giá. Ví dụ `f() + g()` có gọi `f` trước `g` không? Nếu hai hàm có tác dụng phụ, kết quả có thể phụ thuộc thứ tự.

Các lựa chọn phổ biến:

- Đánh giá từ trái sang phải.
- Đánh giá từ phải sang trái.
- Không đảm bảo thứ tự nếu biểu thức thuần và không quan sát được khác biệt.

Đối với DSL nghiệp vụ có lời gọi dịch vụ hoặc hành động, nên quy định thứ tự rõ ràng.

### 10.3. Short-circuit evaluation

Với toán tử Boolean `and` và `or`, DSL có thể dùng đánh giá ngắn mạch:

- `false and e2`: không đánh giá `e2`.
- `true or e2`: không đánh giá `e2`.

Điều này quan trọng nếu `e2` có thể lỗi hoặc có tác dụng phụ. Ví dụ:

~~~text
customer != null and customer.age >= 18
~~~

Nếu `and` đánh giá ngắn mạch, vế phải không được thực hiện khi customer là null. Nếu DSL không đảm bảo short-circuit, biểu thức trên có thể không an toàn.

### 10.4. Pure expression và side effect

Một biểu thức thuần (*pure expression*) chỉ phụ thuộc đầu vào và trả kết quả, không làm thay đổi trạng thái quan sát được. Biểu thức có tác dụng phụ có thể ghi dữ liệu, gửi thông báo, gọi dịch vụ hoặc thay đổi context.

Tài liệu cần cho biết construct nào thuần và construct nào có side effect. Điều này ảnh hưởng đến tối ưu hóa, caching, đánh giá lặp và khả năng chạy song song.

## 11. Ngữ nghĩa câu lệnh, rule và workflow

### 11.1. Câu lệnh gán

Với cú pháp:

~~~text
name = expression
~~~

cần định nghĩa:

- Biểu thức được đánh giá trước hay sau khi xác định biến đích.
- Biến phải được khai báo trước không.
- Gán có tạo biến mới hay chỉ cập nhật biến đã tồn tại.
- Kiểu kết quả có cần tương thích kiểu biến không.
- Nếu đánh giá biểu thức lỗi, biến đích có giữ giá trị cũ không.
- Gán có trả về giá trị hay không.

### 11.2. Rule điều kiện và hành động

Ví dụ:

~~~text
rule "vip-discount" {
    when customer.tier == "GOLD"
    then applyDiscount(10)
}
~~~

Tài liệu cần xác định:

- Rule được đánh giá một lần hay nhiều lần.
- Điều kiện có được đánh giá trong snapshot dữ liệu hay đọc trạng thái mới nhất.
- Nếu điều kiện đúng, hành động được gọi bao nhiêu lần.
- Nhiều rule được thực hiện theo thứ tự nào.
- Nếu một hành động lỗi, các rule còn lại có tiếp tục không.
- Rule có thể thay đổi dữ liệu dùng bởi rule tiếp theo không.
- Có cơ chế ưu tiên, nhóm hoặc dừng sau rule đầu tiên không.

Nếu DSL hỗ trợ priority, cần định nghĩa thứ tự khi hai rule có cùng mức ưu tiên và liệu thứ tự khai báo có ảnh hưởng hay không.

### 11.3. Workflow

Workflow thường có trạng thái và chuyển tiếp. Đặc tả nên mô tả:

- Trạng thái ban đầu.
- Điều kiện bắt đầu và kết thúc.
- Quy tắc chọn transition.
- Hành vi khi nhiều transition cùng hợp lệ.
- Timeout, retry và cancellation.
- Xử lý lỗi và compensation.
- Cách lưu trạng thái để tiếp tục sau khi tiến trình bị dừng.

Ví dụ:

~~~text
workflow "order-fulfillment" {
    start validateOrder
    then reserveInventory
    then capturePayment
    then shipOrder
    onError compensateReservation
}
~~~

Nếu `capturePayment` thất bại sau khi đã giữ hàng, workflow có thể cần gọi compensation để giải phóng tồn kho. Hành vi này phải được mô tả rõ, vì thứ tự và tác dụng phụ là một phần ngữ nghĩa của workflow.

## 12. Lỗi và cách xử lý

Đặc tả cần phân biệt lỗi theo giai đoạn và xác định lỗi nào có thể phục hồi.

| Loại lỗi | Ví dụ | Thời điểm |
|---|---|---|
| Lexical error | Ký tự không hợp lệ | Lexing |
| Syntax error | Thiếu dấu đóng hoặc token | Parsing |
| Type error | Cộng chuỗi với số khi không hỗ trợ | Static semantic analysis |
| Name resolution error | Identifier chưa khai báo | Semantic analysis |
| Constraint violation | Quantity bằng 0 | Model validation hoặc runtime |
| Runtime error | Chia cho 0, timeout | Execution |
| External failure | API hoặc database không sẵn sàng | Runtime integration |
| Permission error | Capability không được cấp | Validation hoặc runtime |

Tài liệu nên xác định:

- Lỗi có dừng toàn bộ chương trình hay chỉ dừng rule hiện tại?
- Có rollback thay đổi trước đó không?
- Có thể retry không, và retry có an toàn không?
- Diagnostic có mã ổn định không?
- Có thể tiếp tục sau lỗi không?
- Người dùng có thể xử lý lỗi bằng construct trong DSL không?

Không nên gộp mọi lỗi thành một thông báo "execution failed". Mỗi lỗi cần đủ ngữ cảnh để người dùng hiểu nguyên nhân và cách khắc phục.

## 13. Thời gian, tiền tệ và tính xác định

Một số lĩnh vực có những quy tắc dễ bị bỏ sót nhưng ảnh hưởng lớn đến kết quả.

### 13.1. Ngày giờ và múi giờ

Nếu DSL xử lý lịch hoặc thời hạn, phải định nghĩa:

- Date có phải ngày lịch không gắn múi giờ không?
- DateTime biểu diễn instant UTC hay local date-time?
- Múi giờ mặc định lấy từ đâu?
- Cách xử lý thời điểm không tồn tại hoặc bị lặp khi chuyển giờ mùa hè.
- Định dạng ngày có phụ thuộc locale không?

Không nên để cùng một tài liệu DSL cho kết quả khác nhau chỉ vì chạy trên máy có timezone hoặc locale khác nhau, trừ khi đó là hành vi được chủ ý công bố.

### 13.2. Tiền tệ và làm tròn

Với Money, cần xác định:

- Giá trị lưu bằng Decimal hay kiểu số khác.
- Mã tiền tệ đi cùng giá trị hay được lấy từ context.
- Cách cộng hai khoản khác tiền tệ.
- Độ chính xác và số chữ số thập phân.
- Quy tắc làm tròn tại từng bước hay chỉ khi xuất kết quả.
- Thứ tự áp dụng thuế và chiết khấu.

Ví dụ, làm tròn từng dòng rồi cộng có thể khác với cộng toàn bộ rồi làm tròn. Đặc tả phải chỉ rõ chính sách mà runtime phải tuân theo.

### 13.3. Tính xác định (*determinism*)

Một chương trình DSL có tính xác định nếu cùng đầu vào và cùng môi trường được quy định sẽ tạo cùng kết quả quan sát được.

Các nguồn gây không xác định có thể gồm:

- Thời gian hiện tại.
- Số ngẫu nhiên.
- Dữ liệu bên ngoài thay đổi.
- Thứ tự duyệt collection không được đảm bảo.
- Các rule chạy song song.
- Thứ tự sự kiện đến từ hệ thống khác.

Nếu DSL cho phép những yếu tố này, cần mô tả cách chúng được cung cấp hoặc kiểm soát, ví dụ truyền clock và random seed qua context, quy định thứ tự collection hoặc công bố các thao tác không xác định.

## 14. Tác dụng phụ, quyền và giới hạn thực thi

Ngữ nghĩa không chỉ nói biểu thức trả về gì mà còn phải nói nó có thể làm gì.

### 14.1. Phân loại tác dụng phụ

| Tác động | Ví dụ | Câu hỏi cần tài liệu hóa |
|---|---|---|
| Đọc dữ liệu | `customer.balance` | Dữ liệu lấy từ snapshot hay trạng thái mới nhất? |
| Ghi dữ liệu | `order.status = "PAID"` | Có transaction và rollback không? |
| Gọi dịch vụ | `sendEmail(...)` | Timeout, retry và lỗi ra sao? |
| Phát sự kiện | `emit OrderPlaced` | Sự kiện được gửi khi nào và có đảm bảo giao nhận không? |
| Đọc thời gian | `now()` | Clock và timezone lấy từ đâu? |
| Ngẫu nhiên | `random()` | Có seed để tái lập kết quả không? |

### 14.2. Capability model

Một DSL an toàn có thể cấp cho mỗi lần thực thi một tập capability rõ ràng. Ví dụ rule được quyền đọc đơn hàng và tồn kho, nhưng không được xóa tài khoản hoặc truy cập filesystem tùy ý.

Tài liệu nên mô tả:

- Danh sách capability có sẵn.
- Quyền mặc định.
- Cách cấp hoặc thu hồi quyền.
- Lỗi khi gọi capability không được phép.
- Việc kiểm tra quyền ở lúc validate và lúc thực thi.
- Cách ghi audit log cho hành động nhạy cảm.

### 14.3. Resource limits

Với DSL do người dùng cung cấp, cần công bố các giới hạn như:

- Thời gian chạy tối đa.
- Số bước hoặc số lần lặp.
- Độ sâu đệ quy.
- Bộ nhớ hoặc kích thước dữ liệu.
- Số lần gọi dịch vụ.
- Kích thước output.

Giới hạn có thể thay đổi theo cấu hình runtime, nhưng tài liệu cần nói rõ giá trị mặc định và cách hệ thống phản hồi khi vượt giới hạn.

## 15. Ví dụ đặc tả ngữ nghĩa hoàn chỉnh cho một construct

Xét hàm `coalesce`, trả về giá trị đầu tiên không null.

**Tên:** `coalesce`.

**Cú pháp:**

~~~text
coalesce(expression1, expression2, ...)
~~~

**Số đối số:** Ít nhất một đối số.

**Kiểu:**

- Các đối số phải có kiểu tương thích.
- Kết quả có kiểu chung của các đối số sau khi áp dụng quy tắc type inference.
- Nếu DSL dùng kiểu optional, kết quả có thể là kiểu không optional nếu có ít nhất một nhánh chắc chắn không null; điều này phụ thuộc chính sách type system.

**Ngữ nghĩa:**

1. Đánh giá các đối số từ trái sang phải.
2. Trả về giá trị đầu tiên không null.
3. Không đánh giá các đối số còn lại sau khi tìm được giá trị phù hợp.
4. Nếu tất cả đối số đều null, trả null hoặc phát lỗi theo chính sách được công bố.

**Tác dụng phụ:** Các đối số có thể chứa biểu thức có side effect nếu DSL cho phép. Do đánh giá ngắn mạch, các đối số phía sau có thể không được thực hiện.

**Ví dụ:**

~~~text
displayName = coalesce(customer.nickname, customer.fullName, "Guest")
~~~

Nếu nickname là null và fullName là "An Nguyen", kết quả là "An Nguyen"; literal "Guest" không được đánh giá nếu đã có giá trị trước đó.

Ví dụ này cho thấy chỉ ghi "coalesce trả về giá trị đầu tiên khác null" là chưa đủ. Tài liệu cần nêu thứ tự đánh giá, short-circuit, kiểu kết quả và trường hợp tất cả đối số đều null.

## 16. Ví dụ tài liệu hóa ngữ nghĩa cho một DSL quy tắc

Giả sử DSL hỗ trợ:

~~~text
rule "large-order" priority 10 {
    when order.total >= 1000000
    then applyDiscount(order, 0.05)
}
~~~

Một phần đặc tả có thể viết:

### 16.1. Rule declaration

- Mỗi rule có một tên duy nhất trong module.
- `priority` là số nguyên; giá trị lớn hơn được đánh giá trước.
- Nếu không khai báo priority, giá trị mặc định là 0.
- Các rule có cùng priority được đánh giá theo thứ tự khai báo trong module.
- Rule không được tham chiếu đến context ngoài danh sách được cấp.

### 16.2. Điều kiện

- Biểu thức sau `when` phải trả về Boolean.
- Điều kiện được đánh giá một lần trong mỗi lượt đánh giá rule.
- Nếu điều kiện false, hành động không được thực hiện.
- Nếu điều kiện phát sinh runtime error, rule chuyển sang trạng thái failed và engine áp dụng chính sách lỗi của module.

### 16.3. Hành động

- `applyDiscount` phải được đăng ký trong capability của runtime.
- Giá trị phần trăm phải nằm trong khoảng được quy định.
- Hành động chỉ được gọi khi điều kiện true.
- Nếu thao tác cập nhật đơn hàng lỗi, engine phải trả diagnostic và thực hiện rollback theo transaction policy đã cấu hình.

### 16.4. Thứ tự giữa các rule

Nếu một rule thay đổi dữ liệu được rule sau sử dụng, đặc tả cần xác định rule sau đọc dữ liệu trước hay sau thay đổi. Nếu engine dùng snapshot, mọi rule có thể nhìn thấy cùng trạng thái ban đầu. Nếu engine dùng trạng thái tuần tự, rule sau nhìn thấy cập nhật của rule trước. Hai mô hình này có thể tạo kết quả khác nhau.

### 16.5. Kết quả kỳ vọng

Với order.total bằng 1.200.000 và capability applyDiscount được cấp, điều kiện true và hành động được gọi. Với order.total bằng 500.000, hành động không được gọi. Nếu capability không được cấp, engine báo permission error theo quy tắc đã công bố.

Một ví dụ có đầu vào và kết quả cụ thể giúp người đọc hiểu cách các quy tắc kết hợp với nhau.

## 17. Ví dụ và bảng kết quả kỳ vọng

Ví dụ tốt nên thể hiện cả trường hợp thành công, biên và lỗi.

| Đầu vào | Điều kiện môi trường | Kết quả kỳ vọng |
|---|---|---|
| `3 + 4` | Số nguyên | `7` |
| `3 + "4"` | Không có coercion số-chuỗi | Type error |
| `false and expensiveCheck()` | `and` short-circuit | Không gọi expensiveCheck |
| `coalesce(null, "A")` | Null được hỗ trợ | `"A"` |
| `order.total > 0` | total là Money có cùng currency context | Boolean |
| `unknownField` | Không có binding | Name resolution error |
| `sendEmail(...)` | Capability mailer không được cấp | Permission error |

Mỗi ví dụ cần nói rõ môi trường và giả định. Nếu kết quả phụ thuộc vào kiểu dữ liệu, trạng thái hoặc capability, đừng chỉ đưa đoạn mã mà không mô tả context.

## 18. Tài liệu hóa lỗi và diagnostics

Một diagnostic có cấu trúc thường gồm:

- Mã lỗi ổn định.
- Loại lỗi và severity.
- Vị trí nguồn.
- Construct hoặc ký hiệu liên quan.
- Nguyên nhân.
- Gợi ý khắc phục nếu có.

Ví dụ:

~~~text
rules.dsl:8:12: error DSL-TYPE-004
Expected Boolean condition after 'when', but found Decimal.
Use a comparison or a Boolean expression.
~~~

Tài liệu cần giải thích mã lỗi có ổn định giữa các phiên bản không, warning có ngăn thực thi không và runtime có thể trả nhiều diagnostic trong một lần kiểm tra hay không.

Thông báo lỗi không nên chỉ lặp lại tên lớp hoặc exception nội bộ. Người viết DSL cần nhận được giải thích bằng thuật ngữ của ngôn ngữ.

## 19. Tổ chức tài liệu ngữ nghĩa cho người đọc

Một tài liệu tốt cần phục vụ nhiều nhóm người dùng:

| Đối tượng | Điều họ cần |
|---|---|
| Người mới học DSL | Khái niệm, ví dụ ngắn, quy tắc cơ bản |
| Người viết rule/workflow | Ý nghĩa từng construct, thứ tự chạy, lỗi và side effect |
| Người tích hợp DSL | Kiểu dữ liệu, context, API, capability và runtime contract |
| Người xây compiler/interpreter | Quy tắc đánh giá chính xác, type rules và conformance cases |
| Người vận hành | Giới hạn, lỗi, retry, logging và tính xác định |
| Người bảo trì ngôn ngữ | Phiên bản, tương thích và lịch sử thay đổi |

Có thể tổ chức tài liệu thành:

1. **Language overview:** mục tiêu, đối tượng sử dụng, mô hình khái niệm.
2. **Syntax reference:** grammar, từ khóa và cấu trúc.
3. **Semantic reference:** ý nghĩa của biểu thức, câu lệnh, kiểu và hành động.
4. **Runtime model:** context, state, thứ tự thực thi, lỗi và capability.
5. **Examples and recipes:** tình huống nghiệp vụ có đầu vào và kết quả.
6. **Compatibility guide:** phiên bản, thay đổi và migration.

Không nên trộn tài liệu hướng dẫn nhập môn với mọi chi tiết hình thức trong cùng một đoạn dài. Người mới cần ví dụ và giải thích theo nhiệm vụ; người triển khai cần quy tắc chính xác có thể tra cứu.

## 20. Kiểm thử đặc tả ngữ nghĩa

Tài liệu ngữ nghĩa cần được gắn với kiểm thử để ví dụ không chỉ mang tính minh họa.

### 20.1. Executable examples

Nếu có thể, hãy lưu ví dụ cùng input và output kỳ vọng để CI chạy trực tiếp bằng interpreter hoặc compiler. Khi runtime thay đổi, ví dụ phát hiện sớm trường hợp hành vi khác với tài liệu.

### 20.2. Conformance tests

Một conformance suite là tập kiểm thử xác định implementation có tuân thủ đặc tả hay không. Mỗi quy tắc ngữ nghĩa quan trọng nên có:

- Trường hợp hợp lệ.
- Trường hợp không hợp lệ.
- Giá trị biên.
- Trường hợp lỗi.
- Kết quả và trạng thái sau thực thi.
- Tác dụng phụ quan sát được nếu có.

Nếu có nhiều implementation, cùng một bộ test có thể chạy trên tất cả để phát hiện khác biệt.

### 20.3. Golden tests

Golden tests lưu đầu vào và kết quả kỳ vọng như giá trị trả về, diagnostics, event log hoặc trạng thái cuối. Khi thay đổi đặc tả, nhóm review sự khác biệt trước khi cập nhật golden output.

### 20.4. Kiểm thử tính xác định

Với các construct được công bố là deterministic, chạy cùng đầu vào và context phải cho kết quả tương đương. Nếu có thời gian, random hoặc dữ liệu ngoài, test nên cố định clock, seed hoặc dependency giả lập.

### 20.5. Trace và giải thích thực thi

Với DSL rule hoặc workflow, execution trace có thể ghi:

- Rule nào được xét.
- Điều kiện cho kết quả gì.
- Nhánh nào được chọn.
- Hành động nào được gọi.
- Trạng thái nào thay đổi.
- Lỗi nào xảy ra.

Trace giúp kiểm chứng cách diễn giải của người dùng và hỗ trợ giải thích vì sao DSL tạo ra một kết quả.

## 21. Quản lý phiên bản và thay đổi ngữ nghĩa

Thay đổi ngữ nghĩa có thể phá vỡ chương trình DSL ngay cả khi grammar không đổi.

Ví dụ, phiên bản mới thay đổi `and` từ đánh giá đầy đủ hai vế sang short-circuit. Cú pháp vẫn giống nhau, nhưng biểu thức có side effect có thể cho kết quả khác. Đây là thay đổi ngữ nghĩa và cần được công bố.

### 21.1. Semantic versioning cho ngôn ngữ

Có thể áp dụng một chính sách phiên bản cho DSL:

- **Patch:** sửa lỗi implementation nhưng giữ hành vi được đặc tả.
- **Minor:** thêm construct hoặc khả năng mới theo cách tương thích.
- **Major:** thay đổi hoặc loại bỏ hành vi có thể làm tài liệu cũ hoạt động khác.

Không phải mọi dự án đều cần đúng mô hình SemVer, nhưng cần có quy tắc rõ về cách đánh version của ngôn ngữ, runtime và thư viện miền.

### 21.2. Compatibility policy

Tài liệu cần nêu:

- Phiên bản runtime hỗ trợ phiên bản DSL nào.
- Cú pháp cũ được duy trì bao lâu.
- Thay đổi nào là breaking change.
- Cảnh báo deprecation xuất hiện khi nào.
- Migration tool có sẵn không.
- Cách xử lý tài liệu không khai báo version.

### 21.3. Ghi lại quyết định ngữ nghĩa

Khi nhóm thay đổi quy tắc, nên lưu quyết định cùng lý do và tác động. Ví dụ:

~~~text
Decision: Logical AND uses short-circuit evaluation.
Reason: Avoid evaluating the right operand when the left operand is false.
Compatibility impact: Expressions with side effects in the right operand may execute fewer operations.
Version: DSL 2.0
~~~

Decision record giúp người bảo trì hiểu vì sao quy tắc được chọn và đánh giá ảnh hưởng trong tương lai.

## 22. Những lỗi thường gặp khi tài liệu hóa ngữ nghĩa

1. **Chỉ mô tả cú pháp:** người dùng biết viết thế nào nhưng không biết biểu thức có nghĩa gì.
2. **Dùng từ mơ hồ:** các từ như "thường", "tùy hệ thống" hoặc "xử lý phù hợp" không xác định được hành vi.
3. **Bỏ qua thứ tự đánh giá:** hai implementation có thể tạo kết quả khác nhau khi biểu thức có side effect.
4. **Không nói rõ kiểu và null:** lỗi chỉ xuất hiện khi runtime xử lý dữ liệu thực.
5. **Không mô tả lỗi:** người dùng không biết lỗi có dừng chương trình, rollback hay cho phép tiếp tục.
6. **Không phân biệt validation với execution:** kiểm tra mô hình không đồng nghĩa hành động đã được thực hiện.
7. **Không công bố giá trị mặc định:** cấu hình thiếu trường có thể cho kết quả khó dự đoán.
8. **Không xác định capability:** DSL có thể vô tình cấp quyền vượt quá nhu cầu.
9. **Ví dụ không có context:** người đọc không biết dữ liệu đầu vào hoặc giả định kiểu.
10. **Tài liệu lệch runtime:** ví dụ không được chạy hoặc kiểm thử nên dần không còn đúng.
11. **Không quản lý thay đổi:** thay đổi semantics âm thầm làm hỏng rule và workflow đã lưu.
12. **Đặc tả quá phụ thuộc implementation:** chi tiết nội bộ thay đổi làm tài liệu trở nên sai dù hành vi người dùng không đổi.

## 23. Quy trình tài liệu hóa ngữ nghĩa cho một DSL

Có thể triển khai theo các bước sau:

1. **Xác định phạm vi:** liệt kê các construct, kiểu, thao tác và đối tượng miền mà DSL hỗ trợ.
2. **Xây glossary:** thống nhất thuật ngữ và khái niệm.
3. **Lập danh mục construct:** mỗi từ khóa, toán tử, declaration, function và cấu trúc điều khiển cần một mục mô tả.
4. **Định nghĩa kiểu và giá trị:** nêu miền giá trị, null, missing, conversion và default.
5. **Đặc tả evaluation model:** môi trường, scope, thứ tự đánh giá, trạng thái và side effect.
6. **Định nghĩa lỗi và quyền:** phân loại lỗi, rollback, retry, capability và resource limits.
7. **Chọn mức hình thức:** văn xuôi có cấu trúc, bảng quy tắc, operational/denotational/axiomatic semantics hoặc kết hợp.
8. **Viết ví dụ có kết quả:** ghi rõ input, context, output, trạng thái và diagnostic.
9. **Liên kết với test:** biến quy tắc quan trọng thành conformance test và executable example.
10. **Quản lý version:** ghi nhận thay đổi, tương thích và migration.
11. **Review cùng các vai trò liên quan:** người dùng DSL, người triển khai runtime và người vận hành cần hiểu cùng một hợp đồng.

Một construct chỉ nên được xem là được đặc tả đầy đủ khi người đọc có thể xác định cách viết, điều kiện hợp lệ, ý nghĩa, kiểu kết quả, thứ tự đánh giá, tác dụng phụ và cách xử lý lỗi mà không phải suy đoán từ mã nguồn.

## 24. Kết luận

Tài liệu hóa ngữ nghĩa xác định ý nghĩa và hành vi của các cấu trúc DSL sau khi chúng được viết đúng cú pháp. Nó giải thích kiểu dữ liệu, quy tắc đánh giá, thứ tự thực thi, trạng thái, tác dụng phụ, lỗi, quyền và các điều kiện môi trường. Tài liệu có thể dùng văn xuôi có cấu trúc, bảng, ví dụ, quy tắc hình thức hoặc kết hợp nhiều cách tùy mức độ phức tạp của ngôn ngữ.

Một đặc tả ngữ nghĩa tốt là hợp đồng có thể tra cứu và kiểm chứng giữa người dùng DSL với implementation. Khi được liên kết với ví dụ thực thi, conformance tests và chính sách phiên bản, tài liệu giúp các công cụ hoạt động nhất quán, giảm hiểu nhầm và cho phép DSL phát triển mà vẫn giữ được hành vi đáng tin cậy.

