# Tiến hóa schema trong mô hình trừu tượng

Một ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường biểu diễn chương trình hoặc quy tắc bằng một mô hình có cấu trúc. Sau khi phân tích cú pháp, văn bản DSL có thể được chuyển thành cây cú pháp trừu tượng (AST), mô hình miền, biểu diễn trung gian (IR) hoặc tài liệu có thể lưu trữ và trao đổi giữa các thành phần. Schema mô tả cấu trúc của những mô hình đó: có những loại phần tử nào, mỗi phần tử có thuộc tính gì, kiểu dữ liệu ra sao, quan hệ giữa các phần tử được tổ chức như thế nào và những ràng buộc nào phải được thỏa mãn.

Theo thời gian, DSL và miền bài toán sẽ thay đổi. Một loại nút mới có thể được thêm vào AST; một thuộc tính có thể được đổi tên; một trường trước đây tùy chọn có thể trở thành bắt buộc; một kiểu dữ liệu có thể được thay thế bằng cấu trúc phong phú hơn. Những thay đổi đó được gọi chung là **tiến hóa schema** (*schema evolution*).

Tiến hóa schema giúp mô hình trừu tượng đáp ứng yêu cầu mới mà vẫn quản lý được các chương trình, cấu hình và dữ liệu đã được tạo bằng phiên bản cũ. Công việc này cần xem xét cả cấu trúc, ngữ nghĩa, khả năng tương thích, chuyển đổi dữ liệu và quá trình triển khai. Một schema mới có thể hợp lệ về mặt cấu trúc nhưng vẫn làm thay đổi ý nghĩa của quy tắc cũ, vì vậy không thể chỉ kiểm tra xem tài liệu có parse được hay không.

## 1. Schema trong mô hình trừu tượng là gì?

### 1.1. Schema mô tả cấu trúc của mô hình

Schema là tập quy tắc mô tả hình dạng và những ràng buộc của dữ liệu có cấu trúc. Trong một DSL, schema có thể định nghĩa:

- Các loại node hoặc thực thể được phép xuất hiện.
- Các trường và kiểu dữ liệu của từng loại.
- Trường bắt buộc, trường tùy chọn và giá trị mặc định.
- Quan hệ cha-con, tham chiếu và danh sách phần tử.
- Các giá trị enum hoặc tập lựa chọn hợp lệ.
- Ràng buộc miền và quy tắc nhất quán.
- Phiên bản cấu trúc mà một tài liệu tuân theo.

Ví dụ, một schema đơn giản cho quy tắc có thể mô tả một node Rule gồm tên, điều kiện và hành động:

~~~text
Rule
  name: String
  condition: Expression
  actions: List<Action>
~~~

Một tài liệu theo schema này có thể được lưu dưới dạng JSON, YAML, đối tượng Java hoặc AST trong bộ nhớ. Định dạng lưu trữ và schema có liên quan nhưng không phải một khái niệm: JSON là một định dạng biểu diễn dữ liệu, còn schema quy định dữ liệu JSON nào được chấp nhận và có ý nghĩa gì.

### 1.2. Schema của AST và mô hình miền

Trong kiến trúc DSL, có thể tồn tại nhiều schema ở các lớp khác nhau:

| Lớp mô hình | Schema mô tả | Ví dụ |
|---|---|---|
| Cú pháp trừu tượng (AST) | Các node và quan hệ phản ánh cấu trúc chương trình | BinaryExpression, FunctionCall, RuleDeclaration |
| Mô hình miền | Các thực thể và khái niệm nghiệp vụ | Order, Customer, DiscountPolicy |
| Biểu diễn trung gian (IR) | Cấu trúc đã chuẩn hóa để phân tích, tối ưu hoặc thực thi | Compare, And, InvokeFunction |
| Tài liệu trao đổi hoặc lưu trữ | Cấu trúc dữ liệu được ghi ra file, database hoặc API | JSON document có schemaVersion |

Một thay đổi ở schema AST không nhất thiết phải làm thay đổi schema lưu trữ. Parser có thể chuyển nhiều dạng cú pháp về cùng một AST chuẩn. Tương tự, schema IR có thể thay đổi để hỗ trợ tối ưu mà không cần buộc người dùng viết lại DSL.

Điều quan trọng là xác định rõ schema nào đang tiến hóa và những thành phần nào phụ thuộc vào nó.

### 1.3. Phân biệt schema, dữ liệu và ngữ nghĩa

Ba lớp này cần được xem xét riêng:

- **Schema** xác định cấu trúc và ràng buộc: node Rule có trường condition kiểu Expression.
- **Dữ liệu** là một thể hiện cụ thể: quy tắc WeekendDiscount với điều kiện khách hàng thuộc hạng GOLD.
- **Ngữ nghĩa** xác định ý nghĩa và hành vi: điều kiện được đánh giá thế nào, hành động được áp dụng khi nào.

Ví dụ, đổi trường discountRate từ số nguyên sang số thập phân là thay đổi cấu trúc. Đổi cách hiểu 10 từ “10 phần trăm” thành “hệ số 10” là thay đổi ngữ nghĩa. Hai việc có thể xảy ra cùng lúc nhưng cần được quản lý rõ ràng.

## 2. Vì sao schema cần tiến hóa?

### 2.1. Mô hình miền thay đổi

Khi hiểu biết về miền sâu hơn, mô hình ban đầu có thể thiếu khái niệm hoặc gộp nhiều khái niệm khác nhau. Ví dụ, một quy tắc ưu đãi ban đầu chỉ có một trường discount. Sau này, nghiệp vụ cần phân biệt giảm theo phần trăm, giảm số tiền cố định và miễn phí vận chuyển.

Schema cần được mở rộng để mô tả các loại ưu đãi riêng, có trường và quy tắc kiểm tra phù hợp.

### 2.2. DSL có thêm khả năng

DSL có thể bổ sung cấu trúc mới như nhóm điều kiện, vòng lặp, tham chiếu kiểu miền hoặc metadata phục vụ kiểm toán. AST và IR cần có node tương ứng để biểu diễn những khả năng đó.

### 2.3. Tích hợp với hệ thống khác

Một mô hình ban đầu có thể chỉ được dùng trong một ứng dụng. Khi cần trao đổi qua API, lưu trong kho dữ liệu hoặc được nhiều dịch vụ cùng đọc, schema cần xác định rõ kiểu dữ liệu, định danh, phiên bản và quy tắc tương thích.

### 2.4. Sửa mô hình chưa chính xác

Một số trường có thể được đặt tên chưa rõ, có kiểu dữ liệu quá tổng quát hoặc không thể biểu diễn ràng buộc miền. Tiến hóa schema giúp sửa những hạn chế đó, nhưng việc sửa cần có lộ trình để dữ liệu cũ vẫn được xử lý đúng.

### 2.5. Hỗ trợ vòng đời dài của tài liệu

Quy tắc DSL có thể được lưu nhiều năm, trong khi parser, runtime và ứng dụng đã nâng cấp nhiều lần. Schema cần có cách nhận diện phiên bản và chuyển đổi tài liệu cũ sang mô hình hiện tại.

## 3. Những loại thay đổi schema thường gặp

### 3.1. Thêm trường tùy chọn

Giả sử schema cũ:

~~~json
{
  "type": "Rule",
  "name": "WeekendDiscount",
  "condition": { "type": "Equals", "left": "day", "right": "Saturday" }
}
~~~

Phiên bản mới thêm trường description tùy chọn:

~~~json
{
  "type": "Rule",
  "name": "WeekendDiscount",
  "description": "Ưu đãi cuối tuần",
  "condition": { "type": "Equals", "left": "day", "right": "Saturday" }
}
~~~

Nếu bộ đọc cũ bỏ qua trường không biết, tài liệu mới có thể vẫn đọc được. Nếu bộ đọc cũ từ chối trường lạ, thay đổi này có thể phá vỡ tương thích ngược.

Thêm trường tùy chọn thường ít rủi ro hơn thêm trường bắt buộc, nhưng vẫn cần xác định cách bộ đọc cũ và mới xử lý nó.

### 3.2. Thêm trường bắt buộc

Nếu phiên bản mới yêu cầu priority, tài liệu cũ không có trường này sẽ không hợp lệ theo schema mới.

Cần chọn một cách chuyển đổi:

- Gán giá trị mặc định có ý nghĩa nghiệp vụ.
- Suy ra giá trị từ dữ liệu hiện có.
- Đưa tài liệu vào trạng thái cần người dùng bổ sung.
- Giữ hỗ trợ schema cũ trong một giai đoạn.

Không nên tự chọn giá trị mặc định nếu giá trị đó ảnh hưởng đến thứ tự thực thi hoặc kết quả nghiệp vụ mà không có quyết định từ miền.

### 3.3. Đổi tên trường

Đổi discount thành discountPolicy có thể làm parser hoặc bộ đọc mới không nhận ra tài liệu cũ.

Trong giai đoạn chuyển tiếp, có thể đọc cả tên cũ và tên mới nhưng chỉ ghi tên mới. Nếu cả hai cùng xuất hiện, schema cần quy định cách xử lý: từ chối vì mơ hồ, hoặc chấp nhận khi hai giá trị tương đương.

Sau khi di chuyển dữ liệu và các client đã nâng cấp, trường cũ mới có thể bị loại bỏ.

### 3.4. Đổi kiểu dữ liệu

Giả sử discountRate trước đây là số nguyên:

~~~json
{ "discountRate": 10 }
~~~

Phiên bản mới dùng số thập phân:

~~~json
{ "discountRate": 0.10 }
~~~

Việc đổi kiểu có thể cần chuyển đổi giá trị. Tuy nhiên, cần hiểu rõ ý nghĩa cũ: 10 là 10%, 0.10 hay một đơn vị khác? Chỉ khi ngữ nghĩa cũ được xác định, migration mới có thể tính toán chính xác.

### 3.5. Thay đổi cardinality

Một trường đơn có thể trở thành danh sách:

~~~text
// Schema cũ
Rule.action: Action

// Schema mới
Rule.actions: List<Action>
~~~

Migration có thể bọc hành động cũ vào danh sách một phần tử. Nhưng nếu schema mới cho phép nhiều hành động, cần xác định thứ tự thực hiện, cách xử lý lỗi giữa các hành động và ý nghĩa khi danh sách rỗng.

### 3.6. Thay đổi tập giá trị enum

Một trường status có thể bổ sung giá trị SUSPENDED. Bộ đọc cũ có thể không biết giá trị mới và không thể quyết định hành vi.

Thêm giá trị enum thường dễ hơn xóa hoặc đổi nghĩa một giá trị cũ. Nếu hệ thống dùng enum trong nhiều ngôn ngữ, database hoặc API, cần kiểm tra khả năng xử lý giá trị chưa biết ở từng nơi.

### 3.7. Tách hoặc gộp cấu trúc

Một trường address có thể được tách thành shippingAddress và billingAddress. Ngược lại, nhiều trường có thể được gộp thành một cấu trúc Money hoặc DateRange.

Những thay đổi này thường cần migration có logic, vì dữ liệu cũ có thể không chứa đủ thông tin để tạo ra cấu trúc mới một cách duy nhất.

### 3.8. Thay đổi quan hệ và định danh

Mô hình có thể chuyển từ quan hệ nhúng sang tham chiếu bằng ID, hoặc ngược lại. Cần xác định tính duy nhất, phạm vi của ID, vòng đời đối tượng được tham chiếu và cách xử lý tham chiếu bị thiếu.

Đổi cách định danh một node có thể ảnh hưởng đến tham chiếu từ tài liệu khác, lịch sử phiên bản, cache và công cụ so sánh.

## 4. Tương thích schema

### 4.1. Tương thích ngược (backward compatibility)

Một phiên bản phần mềm mới có khả năng đọc hoặc xử lý dữ liệu được tạo theo schema cũ.

Ví dụ, parser phiên bản 3 có thể đọc tài liệu schema phiên bản 2 và chuyển nó thành mô hình nội bộ phiên bản 3.

Tương thích ngược rất hữu ích khi nâng cấp ứng dụng nhưng dữ liệu đã lưu chưa được di chuyển đồng loạt.

### 4.2. Tương thích xuôi (forward compatibility)

Một bộ đọc cũ có thể tiếp nhận dữ liệu được tạo theo schema mới ở mức độ nào đó, thường bằng cách bỏ qua trường hoặc cấu trúc chưa biết.

Khả năng này chỉ an toàn nếu dữ liệu mới không chứa thông tin bắt buộc để hiểu đúng hành vi cũ. Nếu trường mới làm thay đổi ngữ nghĩa thực thi, bộ đọc cũ không nên bỏ qua nó rồi tiếp tục chạy như thể không có thay đổi.

### 4.3. Tương thích hai chiều và giới hạn thực tế

Một schema không thể mặc nhiên bảo đảm cả reader cũ đọc writer mới và reader mới đọc writer cũ. Mỗi thay đổi cần được đánh giá theo hướng tương thích.

Ví dụ:

| Thay đổi | Reader mới đọc dữ liệu cũ | Reader cũ đọc dữ liệu mới |
|---|---|---|
| Thêm trường tùy chọn, có mặc định | Thường có thể | Có thể nếu bỏ qua trường lạ |
| Thêm trường bắt buộc | Cần migration hoặc mặc định | Thường không liên quan đến reader cũ nếu writer mới luôn ghi trường |
| Đổi tên trường | Cần hỗ trợ tên cũ hoặc migration | Có thể thất bại nếu reader cũ chỉ biết tên cũ |
| Đổi kiểu dữ liệu | Cần chuyển đổi | Có thể thất bại khi gặp kiểu mới |
| Thêm giá trị enum | Reader mới thường đọc được giá trị cũ | Reader cũ có thể không biết giá trị mới |
| Xóa trường | Reader mới cần xử lý tài liệu cũ | Reader cũ có thể yêu cầu trường đã bị xóa |

Đây là xu hướng phổ biến, không phải bảo đảm tuyệt đối. Kết quả thực tế phụ thuộc vào định dạng, parser, chính sách xử lý trường lạ và ngữ nghĩa của từng trường.

### 4.4. Tương thích cấu trúc và tương thích ngữ nghĩa

Hai tài liệu có thể cùng vượt qua kiểm tra schema nhưng vẫn có hành vi khác nhau. Ví dụ, một giá trị số vẫn có kiểu Number, nhưng đơn vị hoặc cách làm tròn đã đổi.

Do đó, cần phân biệt:

- **Tương thích cấu trúc:** dữ liệu có đúng hình dạng và kiểu mà bộ đọc chấp nhận không?
- **Tương thích ngữ nghĩa:** dữ liệu có giữ nguyên ý nghĩa và hành vi theo hợp đồng miền không?

Với DSL thực thi quy tắc, tương thích ngữ nghĩa thường quan trọng hơn việc chỉ parse thành công.

## 5. Phiên bản schema

### 5.1. Vì sao cần phiên bản riêng?

Phiên bản ứng dụng và phiên bản schema không nhất thiết giống nhau. Một bản phát hành ứng dụng có thể thay đổi giao diện mà không đổi schema; ngược lại, schema có thể tiến hóa độc lập với runtime.

Nên quản lý phiên bản schema như một hợp đồng riêng, đặc biệt khi tài liệu được lưu trữ hoặc trao đổi giữa nhiều thành phần.

### 5.2. Gắn phiên bản vào tài liệu

Một tài liệu có thể ghi rõ phiên bản:

~~~json
{
  "schemaVersion": 2,
  "type": "Rule",
  "name": "WeekendDiscount",
  "condition": {
    "type": "Equals",
    "left": "order.day",
    "right": "Saturday"
  }
}
~~~

schemaVersion cho bộ đọc biết nên áp dụng quy tắc nào. Có thể dùng một trường version ở cấp tài liệu, metadata bên ngoài hoặc version trong envelope của thông điệp.

Nếu schema có nhiều module độc lập, một phiên bản tổng thể có thể chưa đủ. Khi đó, cần xác định phiên bản cho từng namespace hoặc schema con.

### 5.3. Quy tắc đánh số phiên bản

Có thể dùng phiên bản số nguyên tăng dần, hoặc quy ước dạng major/minor:

- **Major:** có thay đổi không tương thích cần migration hoặc reader mới.
- **Minor:** bổ sung có thể tương thích theo hợp đồng đã định nghĩa.
- **Patch:** sửa mô tả, ràng buộc hoặc lỗi triển khai mà không đổi cấu trúc/ngữ nghĩa công khai.

Đây là một quy ước quản lý, không phải luật bắt buộc. Điều quan trọng là tổ chức phải định nghĩa rõ thay đổi nào làm tăng phiên bản nào và không dùng cùng một số version cho những schema có nội dung khác nhau.

### 5.4. Phiên bản ngữ nghĩa

Trong một số DSL, cú pháp và schema có thể giữ nguyên nhưng cách đánh giá biểu thức thay đổi. Ví dụ, quy tắc xử lý giá trị null hoặc độ ưu tiên toán tử được sửa.

Khi đó, chỉ schemaVersion có thể chưa đủ. Có thể cần languageVersion hoặc semanticVersion để runtime biết phải diễn giải chương trình theo hợp đồng nào.

Không nên gộp mọi phiên bản vào một trường nếu các vòng đời thay đổi độc lập và cần được quản lý riêng.

## 6. Chiến lược tiến hóa schema

### 6.1. Ưu tiên thay đổi bổ sung có kiểm soát

Khi có thể, thêm trường tùy chọn hoặc node mới thường ít phá vỡ dữ liệu cũ hơn việc đổi kiểu hoặc đổi nghĩa trường hiện có.

Một trường mới nên có:

- Tên ổn định và ý nghĩa rõ ràng.
- Kiểu dữ liệu cụ thể.
- Quy tắc mặc định nếu được phép.
- Hành vi khi bộ đọc cũ không biết trường đó.
- Quy tắc validation và tài liệu.

### 6.2. Deprecation trước khi loại bỏ

Nếu một trường hoặc node không còn được khuyến nghị, có thể đánh dấu deprecated trước khi xóa.

Quy trình thường gồm:

1. Công bố phần tử mới thay thế.
2. Tiếp tục đọc phần tử cũ.
3. Có thể ngừng ghi phần tử cũ trong writer mới.
4. Cảnh báo khi gặp dữ liệu cũ.
5. Cung cấp migration.
6. Loại bỏ sau thời gian chuyển tiếp đã công bố.

Deprecation giúp người dùng có thời gian nâng cấp và giảm rủi ro làm hỏng dữ liệu đang vận hành.

### 6.3. Expand–migrate–contract

Với hệ thống đang hoạt động, một cách triển khai hữu ích là chia thay đổi thành ba giai đoạn:

1. **Expand:** mở rộng schema và reader để chấp nhận cả dạng cũ lẫn dạng mới.
2. **Migrate:** chuyển dữ liệu cũ sang dạng mới theo lô hoặc theo nhu cầu đọc.
3. **Contract:** sau khi xác nhận không còn dữ liệu hoặc client cũ, loại bỏ hỗ trợ dạng cũ.

Ví dụ, khi đổi discount thành discountPolicy, reader giai đoạn đầu hiểu cả hai trường. Writer mới ghi discountPolicy. Một job migration chuyển các tài liệu cũ. Khi quá trình hoàn tất, phiên bản sau có thể ngừng đọc discount.

Không nên bỏ reader cũ trước khi writer và dữ liệu đã chuyển đổi, vì các phiên bản ứng dụng có thể cùng hoạt động trong một khoảng thời gian.

### 6.4. Dual read và dual write

Trong giai đoạn chuyển tiếp, hệ thống có thể đọc cả hai dạng schema. Việc ghi đồng thời cả trường cũ và mới đôi khi được dùng để hỗ trợ client cũ, nhưng làm phát sinh nguy cơ hai giá trị không đồng bộ.

Nếu dùng dual write, cần xác định một nguồn dữ liệu có thẩm quyền, kiểm tra hai giá trị nhất quán và có kế hoạch kết thúc rõ ràng. Không nên duy trì dual write lâu dài như một giải pháp mặc định.

### 6.5. Migration tại thời điểm đọc hoặc theo lô

Hai cách phổ biến:

- **Migration theo lô:** chuyển toàn bộ dữ liệu cũ trước hoặc trong một cửa sổ triển khai.
- **Migration khi đọc:** khi một tài liệu cũ được mở, chuyển nó sang mô hình hiện tại và có thể lưu lại dạng mới.

Migration theo lô dễ thống kê tiến độ nhưng cần tài nguyên và thời gian. Migration khi đọc phân tán chi phí nhưng khiến nhiều phiên bản schema có thể tồn tại lâu hơn.

Có thể kết hợp hai cách: migration theo lô cho dữ liệu thường dùng và migration khi đọc như cơ chế dự phòng.

## 7. Thiết kế migration

### 7.1. Migration là phép chuyển đổi có quy tắc

Migration biến một tài liệu hoặc mô hình theo schema cũ thành mô hình theo schema mới.

Ví dụ, schema cũ có một hành động:

~~~json
{
  "type": "Rule",
  "name": "WeekendDiscount",
  "action": {
    "type": "ApplyDiscount",
    "percent": 10
  }
}
~~~

Schema mới hỗ trợ danh sách hành động:

~~~json
{
  "type": "Rule",
  "name": "WeekendDiscount",
  "actions": [
    {
      "type": "ApplyDiscount",
      "percent": 10
    }
  ]
}
~~~

Migration có thể bọc action cũ vào danh sách actions mới. Đây là phép chuyển đổi có thể xác định nếu schema cũ chỉ cho phép một hành động.

### 7.2. Migration có thể mất thông tin

Không phải mọi thay đổi đều có thể chuyển đổi hoàn toàn. Nếu schema cũ gộp shippingAddress và billingAddress thành một trường address, không thể khôi phục hai địa chỉ riêng biệt nếu dữ liệu cũ không lưu chúng.

Trong trường hợp đó, migration cần:

- Đặt một giá trị theo quy tắc nghiệp vụ đã được xác nhận.
- Đánh dấu dữ liệu cần bổ sung.
- Giữ lại dữ liệu gốc trong metadata hoặc lịch sử.
- Từ chối chuyển đổi tự động khi không đủ thông tin.

Không nên tạo dữ liệu giả để làm cho migration thành công về mặt kỹ thuật.

### 7.3. Migration nên xác định và có thể kiểm soát

Với cùng một đầu vào và cùng một phiên bản migration, kết quả nên nhất quán. Nếu migration phụ thuộc thời gian hiện tại, dữ liệu bên ngoài hoặc cấu hình môi trường, các đầu vào đó cần được truyền rõ ràng và ghi nhận.

Migration nên hạn chế tác động phụ. Nếu cần truy vấn dữ liệu ngoài, cần xác định cách xử lý lỗi, timeout và thử lại.

### 7.4. Idempotency

Một migration idempotent có thể chạy lại mà không làm dữ liệu thay đổi thêm ngoài kết quả đã đạt được.

Ví dụ, khi chuyển action thành actions, migration nên kiểm tra xem actions đã tồn tại chưa. Nếu tài liệu đã được chuyển đổi, chạy lại không được bọc danh sách thêm một lần nữa.

Idempotency hữu ích khi job bị dừng giữa chừng, được chạy lại hoặc cần xử lý lại một nhóm dữ liệu sau sự cố.

### 7.5. Ghi nhận lịch sử migration

Hệ thống có thể lưu:

- Phiên bản schema nguồn.
- Phiên bản schema đích.
- ID hoặc phiên bản migration đã chạy.
- Thời điểm và tác nhân thực hiện.
- Kết quả, lỗi và số lượng tài liệu được chuyển đổi.
- Liên kết đến bản sao lưu hoặc lịch sử phiên bản nếu có.

Thông tin này hỗ trợ kiểm toán, điều tra lỗi và xác định tài liệu nào cần được xử lý lại.

## 8. Pipeline đọc và chuyển đổi schema

Một kiến trúc có thể tách bước đọc dữ liệu, nhận diện phiên bản, migration, validation và tạo mô hình nội bộ:

~~~mermaid
flowchart TD
    A["Tài liệu lưu trữ"] --> B["Đọc metadata phiên bản"]
    B --> C{"Phiên bản schema"}
    C -->|"Hiện tại"| E["Parse và tạo mô hình"]
    C -->|"Cũ"| D["Chuỗi migration"]
    C -->|"Mới hơn runtime"| X["Từ chối hoặc chế độ chỉ đọc"]
    D --> E
    E --> F["Validation cấu trúc"]
    F --> G["Validation ngữ nghĩa"]
    G --> H["Mô hình nội bộ hiện tại"]
~~~

Pipeline này giúp các thành phần phía sau làm việc với một mô hình nội bộ thống nhất. Parser hoặc runtime không cần rải điều kiện xử lý mọi phiên bản schema trong toàn bộ mã nguồn.

Nếu tài liệu có phiên bản mới hơn runtime đang chạy, không nên tự động hạ cấp bằng cách bỏ trường chưa biết. Hệ thống cần từ chối, mở chế độ chỉ đọc hoặc dùng một reader tương thích đã được thiết kế rõ.

### 8.1. Migration chain

Có thể định nghĩa các bước chuyển đổi nhỏ:

~~~text
Schema 1 -> Migration 1to2 -> Schema 2
Schema 2 -> Migration 2to3 -> Schema 3
Schema 3 -> Migration 3to4 -> Schema 4
~~~

Khi đọc tài liệu phiên bản 1, hệ thống chạy lần lượt các migration để đạt phiên bản 4. Cách này dễ kiểm tra từng bước, nhưng chuỗi quá dài có thể làm thời gian đọc tăng và tạo gánh nặng duy trì.

### 8.2. Migration trực tiếp

Một hệ thống có thể cung cấp migration trực tiếp từ nhiều phiên bản cũ đến phiên bản hiện tại. Cách này giảm số bước khi có nhiều phiên bản, nhưng số đường chuyển đổi tăng và dễ tạo logic trùng lặp.

Có thể kết hợp:

- Giữ migration tuần tự làm đường chuẩn.
- Cung cấp một số migration trực tiếp cho phiên bản cũ được sử dụng nhiều.
- Kiểm thử kết quả trực tiếp tương đương với kết quả đi qua chuỗi chuẩn.

## 9. Schema registry và quản lý hợp đồng

### 9.1. Schema registry

Trong hệ thống có nhiều dịch vụ hoặc nhiều loại tài liệu, schema registry là nơi lưu trữ và công bố các định nghĩa schema cùng phiên bản.

Registry có thể hỗ trợ:

- Đăng ký schema mới.
- Định danh schema và phiên bản.
- Kiểm tra tương thích trước khi phát hành.
- Tìm schema phù hợp khi đọc tài liệu.
- Lưu metadata và trạng thái hỗ trợ.

Không phải DSL nào cũng cần một dịch vụ registry riêng. Với dự án nhỏ, schema có thể được quản lý cùng mã nguồn và phát hành như một thư viện. Registry trở nên hữu ích khi nhiều producer và consumer cần phối hợp độc lập.

### 9.2. Kiểm tra tương thích trong quy trình phát triển

Trước khi phát hành schema mới, có thể so sánh với phiên bản đang dùng và chạy kiểm tra tự động:

- Consumer cũ có đọc được dữ liệu mới không?
- Consumer mới có đọc được dữ liệu cũ không?
- Có trường bắt buộc mới mà tài liệu cũ thiếu không?
- Có giá trị enum mới chưa được xử lý không?
- Ngữ nghĩa của biểu thức có thay đổi không?

Kiểm tra tự động giúp phát hiện thay đổi phá vỡ hợp đồng trước khi triển khai.

### 9.3. Hợp đồng giữa producer và consumer

Producer tạo tài liệu theo một schema; consumer đọc và xử lý tài liệu đó. Trong một hệ thống phân tán, hai bên có thể nâng cấp ở thời điểm khác nhau.

Do đó, schema phải xác định rõ:

- Producer được phép phát phiên bản nào.
- Consumer hỗ trợ những phiên bản nào.
- Trường không biết được xử lý ra sao.
- Consumer có thể từ chối tài liệu trong trường hợp nào.
- Thời hạn hỗ trợ phiên bản cũ.

Một thay đổi schema chỉ an toàn khi toàn bộ đường đi producer-consumer có kế hoạch tương thích.

## 10. Tiến hóa schema cho AST và IR

### 10.1. Thêm loại node AST

Giả sử AST ban đầu chỉ có:

~~~text
Expression
  Literal
  Reference
  BinaryExpression
~~~

Sau này DSL cần lời gọi hàm:

~~~text
Expression
  Literal
  Reference
  BinaryExpression
  FunctionCall
~~~

Các thành phần xử lý AST cần được cập nhật:

- Parser tạo node FunctionCall.
- Semantic analyzer kiểm tra tên hàm và kiểu tham số.
- Visitor hoặc transformer biết cách duyệt node mới.
- Formatter hoặc pretty printer hiển thị node.
- Interpreter hoặc backend thực thi lời gọi.
- Serializer có thể ghi node mới vào tài liệu.

Nếu một visitor cũ không biết node mới, cần xác định có thể bỏ qua, từ chối hay xử lý qua một node tổng quát. Với node ảnh hưởng đến hành vi, bỏ qua thường không an toàn.

### 10.2. Thay đổi trường của node

Một BinaryExpression có thể lưu toán tử bằng chuỗi:

~~~text
BinaryExpression
  operator: String
  left: Expression
  right: Expression
~~~

Sau này, schema có thể thay operator bằng enum hoặc kiểu node riêng:

~~~text
BinaryExpression
  operator: BinaryOperator
  left: Expression
  right: Expression
~~~

Việc chuyển đổi cần xác định tập giá trị chuỗi cũ có tương ứng một-một với enum mới không. Nếu có giá trị cũ không được biết, migration phải báo lỗi hoặc đưa vào một dạng UnknownOperator có chính sách rõ.

### 10.3. AST nội bộ và AST lưu trữ

Không nhất thiết phải lưu AST nội bộ trực tiếp. Có thể định nghĩa một định dạng tài liệu ổn định hơn để trao đổi, rồi chuyển đổi sang AST hiện tại khi đọc.

Tách schema lưu trữ khỏi schema nội bộ giúp nhóm refactor cấu trúc AST mà không buộc mọi tài liệu cũ phải thay đổi ngay. Đổi lại, cần duy trì adapter và migration giữa hai lớp.

### 10.4. IR có thể tiến hóa độc lập

IR thường phục vụ tối ưu và thực thi. Nó có thể thay đổi thường xuyên hơn cú pháp DSL hoặc mô hình lưu trữ.

Nếu IR chỉ tồn tại trong bộ nhớ và được tạo lại từ DSL mỗi lần, không nhất thiết phải hỗ trợ đọc IR cũ. Nếu IR được cache hoặc lưu lâu dài, cần có version và quy tắc invalidation hoặc migration tương ứng.

## 11. Tiến hóa schema của mô hình miền

### 11.1. Tách khái niệm đang bị gộp

Ví dụ, mô hình cũ dùng:

~~~text
Customer.address: Address
~~~

Sau này, miền cần phân biệt địa chỉ giao hàng và địa chỉ thanh toán:

~~~text
Customer.shippingAddress: Address
Customer.billingAddress: Address
~~~

Migration có thể sao chép địa chỉ cũ vào cả hai trường nếu quy tắc nghiệp vụ xác nhận rằng trước đây chúng luôn giống nhau. Nếu dữ liệu cũ không bảo đảm điều đó, cần yêu cầu bổ sung hoặc đánh dấu chưa xác định.

### 11.2. Gộp các trường thành value object

Một mô hình cũ lưu:

~~~text
amount: Decimal
currencyCode: String
~~~

Mô hình mới có thể dùng:

~~~text
amount: Money
~~~

Value object Money giúp gắn số tiền với đơn vị và các phép toán hợp lệ. Migration cần kiểm tra mã tiền tệ, độ chính xác và quy tắc làm tròn.

### 11.3. Thay đổi quan hệ tham chiếu

Một mô hình có thể chuyển từ nhúng toàn bộ đối tượng sang lưu ID tham chiếu. Cần xem xét:

- ID có duy nhất trong phạm vi nào?
- Đối tượng được tham chiếu có thể bị xóa không?
- Khi tham chiếu không còn tồn tại, tài liệu được xử lý thế nào?
- Có cần snapshot để giữ ngữ nghĩa lịch sử không?

Với quy tắc cần tái hiện hành vi trong quá khứ, chỉ lưu ID có thể chưa đủ nếu đối tượng được tham chiếu thay đổi theo thời gian.

## 12. Triển khai thay đổi schema trong hệ thống đang chạy

### 12.1. Xác định thứ tự nâng cấp

Khi nhiều dịch vụ cùng đọc và ghi mô hình, thứ tự nâng cấp ảnh hưởng đến khả năng tương thích. Cần biết producer nào được triển khai trước, consumer nào còn chạy phiên bản cũ và dữ liệu nào được tạo trong giai đoạn chuyển tiếp.

### 12.2. Dùng reader tương thích trước

Một cách an toàn thường là triển khai reader có thể hiểu cả dạng cũ và mới trước khi writer bắt đầu ghi dạng mới. Sau đó mới chuyển writer và thực hiện migration.

### 12.3. Theo dõi tiến độ dữ liệu

Trong khi migration chạy, cần thống kê:

- Tổng số tài liệu theo phiên bản.
- Số tài liệu đã chuyển đổi.
- Số tài liệu thất bại và nguyên nhân.
- Tài liệu cần xử lý thủ công.
- Tỷ lệ consumer còn sử dụng schema cũ.

Không nên xóa hỗ trợ cũ chỉ dựa trên việc migration job đã kết thúc. Cần xác nhận cả dữ liệu, cache, bản sao lưu và client còn hoạt động.

### 12.4. Rollback và phục hồi

Trước khi migration lớn, cần xác định cách phục hồi:

- Có bản sao lưu hoặc snapshot không?
- Có thể chạy migration ngược không?
- Migration có làm mất thông tin không?
- Có thể giữ dữ liệu gốc trong thời gian chuyển tiếp không?
- Nếu job dừng giữa chừng, có thể chạy lại an toàn không?

Migration ngược không phải lúc nào cũng khả thi. Nếu schema mới thêm thông tin mà schema cũ không biểu diễn được, chuyển ngược có thể mất dữ liệu. Trong trường hợp đó, rollback ứng dụng và rollback dữ liệu phải được thiết kế riêng.

## 13. Kiểm thử tiến hóa schema

### 13.1. Fixture cho từng phiên bản

Lưu một số tài liệu mẫu đại diện cho các phiên bản schema đã phát hành. Khi có phiên bản mới, dùng chúng để kiểm tra parser, reader và migration.

Fixture nên bao gồm:

- Tài liệu tối thiểu hợp lệ.
- Tài liệu có đủ trường tùy chọn.
- Tài liệu có cấu trúc lồng nhau.
- Giá trị enum hoặc kiểu miền quan trọng.
- Trường hợp biên và dữ liệu không hợp lệ.

### 13.2. Kiểm thử migration

Với mỗi migration, kiểm tra:

- Đầu vào theo schema nguồn.
- Đầu ra theo schema đích.
- Giá trị và ngữ nghĩa được giữ lại.
- Trường hợp thiếu hoặc dữ liệu không hợp lệ.
- Chạy lại migration có an toàn không.
- Lỗi có chỉ ra tài liệu và trường liên quan không.

### 13.3. Kiểm thử tương thích reader-writer

Mô phỏng các tổ hợp phiên bản:

| Writer | Reader | Mục tiêu kiểm tra |
|---|---|---|
| Cũ | Mới | Reader mới xử lý dữ liệu cũ |
| Mới | Mới | Đường đi chuẩn của phiên bản hiện tại |
| Mới | Cũ | Xác định mức hỗ trợ hoặc cách từ chối an toàn |
| Cũ đã migration | Mới | Xác nhận dữ liệu sau migration được đọc đúng |

Không phải tổ hợp nào cũng cần được hỗ trợ, nhưng cần có quyết định rõ và kiểm thử cho các tổ hợp nằm trong phạm vi hỗ trợ.

### 13.4. Kiểm thử ngữ nghĩa

Sau migration, chạy cùng một bộ ví dụ hoặc quy tắc nghiệp vụ trên mô hình cũ và mô hình mới khi hai phiên bản được kỳ vọng tương đương.

So sánh kết quả thực thi, sự kiện phát ra hoặc quyết định của rule engine. Việc parse thành công chỉ chứng minh cấu trúc được chấp nhận, không chứng minh hành vi được bảo toàn.

### 13.5. Kiểm thử serializer và round-trip

Nếu hệ thống có serializer, kiểm tra:

1. Tạo mô hình nội bộ.
2. Serialize theo schema hiện tại.
3. Parse lại tài liệu.
4. So sánh mô hình và ngữ nghĩa.

Nếu serializer có hỗ trợ nhiều phiên bản, cần kiểm tra từng định dạng đầu ra và giới hạn mất thông tin khi ghi về schema cũ.

## 14. Những sai lầm thường gặp

### 14.1. Thay đổi schema mà không gắn phiên bản

Nếu tài liệu không cho biết nó được tạo theo schema nào, reader phải đoán dựa trên trường xuất hiện hoặc cấu trúc. Cách đoán này dễ sai khi các phiên bản có cấu trúc gần giống nhau.

### 14.2. Coi mọi thay đổi bổ sung là tương thích

Thêm một trường mới có thể làm reader cũ bỏ qua thông tin quan trọng. Nếu trường đó thay đổi kết quả thực thi, việc bỏ qua có thể gây lỗi nghiệp vụ dù parser vẫn chạy.

### 14.3. Đổi nghĩa trường nhưng giữ nguyên tên

Đây là một dạng thay đổi khó phát hiện. Tài liệu vẫn hợp lệ theo schema nhưng giá trị mang nghĩa khác. Nên tạo trường hoặc phiên bản mới và migration tường minh.

### 14.4. Dùng giá trị mặc định tùy tiện

Giá trị mặc định có thể làm tài liệu cũ trở nên hợp lệ nhưng cũng có thể thay đổi kết quả. Mặc định cần dựa trên quy tắc miền và được công bố.

### 14.5. Migration không thể chạy lại

Job bị dừng giữa chừng rồi chạy lại có thể bọc danh sách hai lần, nhân đôi dữ liệu hoặc ghi đè giá trị đã được cập nhật. Nên thiết kế idempotency và lưu trạng thái xử lý.

### 14.6. Loại bỏ reader cũ quá sớm

Dữ liệu cũ có thể còn trong bản sao lưu, cache, môi trường thử nghiệm hoặc client chưa nâng cấp. Cần có số liệu và mốc hỗ trợ rõ ràng trước khi loại bỏ.

### 14.7. Chỉ kiểm tra cấu trúc

Schema validation không phát hiện mọi thay đổi ngữ nghĩa. Cần kiểm thử hành vi và những quy tắc nghiệp vụ quan trọng.

### 14.8. Gộp phiên bản schema với phiên bản ứng dụng

Hai vòng đời này có thể thay đổi độc lập. Gắn chúng làm một khiến việc hỗ trợ nhiều producer và consumer trở nên khó khăn.

## 15. Quy trình quản lý một thay đổi schema

Một thay đổi schema có thể được triển khai theo các bước:

1. **Mô tả nhu cầu miền:** vấn đề nào yêu cầu thay đổi mô hình?
2. **Xác định phạm vi schema:** AST, mô hình miền, IR hay định dạng lưu trữ?
3. **Định nghĩa schema mới:** trường, kiểu, cardinality, quan hệ và ràng buộc.
4. **Phân loại mức tương thích:** bổ sung, phá vỡ cấu trúc hay thay đổi ngữ nghĩa?
5. **Thiết kế reader và writer:** những phiên bản nào được đọc và ghi?
6. **Thiết kế migration:** quy tắc chuyển đổi, dữ liệu thiếu và trường hợp không thể tự động.
7. **Cập nhật công cụ:** parser, serializer, validator, formatter, visitor và backend liên quan.
8. **Kiểm thử fixture và hành vi:** dữ liệu cũ, dữ liệu mới và các đường đi quan trọng.
9. **Triển khai theo giai đoạn:** reader tương thích, writer mới, migration và loại bỏ dạng cũ.
10. **Theo dõi và tài liệu hóa:** ghi nhận phiên bản, tiến độ, lỗi và chính sách hỗ trợ.

## 16. Ví dụ tổng hợp: tiến hóa schema của quy tắc ưu đãi

Giả sử phiên bản đầu tiên có schema:

~~~json
{
  "schemaVersion": 1,
  "type": "DiscountRule",
  "name": "MemberOffer",
  "discount": 10
}
~~~

Trong phiên bản 1, discount có nghĩa là phần trăm giảm giá. Sau này, miền cần hỗ trợ nhiều loại ưu đãi.

Schema phiên bản 2:

~~~json
{
  "schemaVersion": 2,
  "type": "DiscountRule",
  "name": "MemberOffer",
  "benefit": {
    "kind": "PercentageDiscount",
    "value": 10
  },
  "conditions": []
}
~~~

### 16.1. Phân tích thay đổi

- discount được thay bằng đối tượng benefit.
- benefit.kind xác định loại ưu đãi.
- benefit.value chứa giá trị theo ngữ nghĩa của loại.
- conditions cho phép bổ sung các điều kiện áp dụng.
- schemaVersion xác định định dạng tài liệu.

### 16.2. Migration từ phiên bản 1 sang 2

Vì discount cũ luôn là phần trăm theo hợp đồng phiên bản 1, migration có thể tạo:

~~~json
{
  "schemaVersion": 2,
  "type": "DiscountRule",
  "name": "MemberOffer",
  "benefit": {
    "kind": "PercentageDiscount",
    "value": 10
  },
  "conditions": []
}
~~~

Nếu dữ liệu cũ không ghi rõ đơn vị hoặc có nhiều cách hiểu, migration cần dừng hoặc yêu cầu xác nhận thay vì tự đoán.

### 16.3. Reader tương thích

Trong giai đoạn chuyển tiếp, reader có thể:

- Đọc schemaVersion: 1 và chuyển đổi vào mô hình nội bộ phiên bản 2.
- Đọc schemaVersion: 2 trực tiếp.
- Từ chối phiên bản cao hơn mà runtime chưa hỗ trợ.
- Báo lỗi nếu tài liệu không có version và không thể xác định dạng một cách chắc chắn.

### 16.4. Hành vi phải được bảo toàn

Với mọi tài liệu phiên bản 1 hợp lệ, sau migration, quy tắc giảm giá phần trăm phải cho cùng kết quả như trước. Cần kiểm thử giá trị ở biên, quy tắc làm tròn, tiền tệ và cách kết hợp với các ưu đãi khác.

Sau khi dữ liệu đã chuyển đổi và các client cũ không còn được hỗ trợ, hệ thống có thể ngừng ghi và cuối cùng ngừng đọc trường discount cũ.

## 17. Câu hỏi tự đánh giá

1. Schema trong mô hình trừu tượng mô tả những thành phần nào?
2. Phân biệt schema, dữ liệu và ngữ nghĩa.
3. Vì sao thêm trường tùy chọn thường ít rủi ro hơn thêm trường bắt buộc?
4. Tương thích ngược và tương thích xuôi khác nhau như thế nào?
5. Vì sao tương thích cấu trúc chưa bảo đảm tương thích ngữ nghĩa?
6. Khi nào cần phiên bản schema riêng với phiên bản ứng dụng?
7. Chiến lược expand–migrate–contract hoạt động ra sao?
8. Vì sao migration nên idempotent và có lịch sử thực thi?
9. Thêm một node AST mới ảnh hưởng đến những thành phần nào?
10. Vì sao cần kiểm thử hành vi sau migration thay vì chỉ kiểm tra schema?

## Kết luận

Tiến hóa schema là quá trình thay đổi cấu trúc mô hình để theo kịp DSL và miền bài toán. Thay đổi có thể liên quan đến trường, kiểu dữ liệu, cardinality, enum, quan hệ, node AST hoặc cấu trúc lưu trữ. Mỗi thay đổi cần được đánh giá về tương thích cấu trúc và tương thích ngữ nghĩa.

Một chiến lược bền vững xác định phiên bản schema, giữ reader tương thích trong giai đoạn chuyển tiếp, thiết kế migration có thể kiểm soát, kiểm thử dữ liệu cũ và mới, đồng thời triển khai theo từng bước. Với mô hình trừu tượng của DSL, cần xác định rõ schema nào đang tiến hóa để thay đổi AST, IR hoặc định dạng lưu trữ không vô tình buộc mọi thành phần và mọi tài liệu phải thay đổi cùng lúc.
