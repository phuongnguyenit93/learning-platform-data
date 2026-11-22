# Tính nhất quán

Tính nhất quán là một nguyên tắc thiết kế quan trọng của ngôn ngữ chuyên biệt theo miền (Domain-Specific Language — DSL). Một DSL nhất quán giúp người dùng dự đoán cách viết biểu thức, hiểu ý nghĩa của cấu trúc và áp dụng điều đã học ở phần này sang phần khác. Khi một quy tắc cú pháp hoặc ngữ nghĩa đã được sử dụng, người dùng có thể dựa vào nó để đọc và viết các biểu thức mới mà không phải học lại một ngoại lệ cho mỗi tính năng.

Tính nhất quán không chỉ là làm cho mã có vẻ đẹp hoặc định dạng giống nhau. Nó bao gồm sự thống nhất giữa từ vựng, cấu trúc cú pháp, ý nghĩa, kiểu dữ liệu, thông báo lỗi, tài liệu và cách ngôn ngữ thay đổi theo thời gian. Nếu cùng một từ khóa mang hai ý nghĩa không liên quan, hoặc hai cấu trúc trông giống nhau nhưng được xử lý khác nhau mà không có lý do rõ ràng, người dùng sẽ khó dự đoán hành vi của DSL.

## 1. Tính nhất quán trong DSL là gì?

Một DSL nhất quán là ngôn ngữ mà các quy tắc thiết kế được áp dụng có hệ thống trên toàn bộ phạm vi của nó. Người dùng có thể nhận ra những mẫu quen thuộc và suy luận từ chúng. Ví dụ, nếu mọi điều kiện đều dùng `when`, mọi hành động đều dùng `then`, và mọi phép so sánh đều có cùng quy tắc kiểu, người đọc sẽ dễ hiểu một quy tắc mới hơn.

Có thể xem tính nhất quán qua các câu hỏi:

- Cùng một khái niệm miền có được gọi bằng cùng một thuật ngữ ở mọi nơi không?
- Những cấu trúc có cùng vai trò có dùng cùng hình thức cú pháp không?
- Một toán tử có giữ nguyên ý nghĩa giữa các kiểu dữ liệu và ngữ cảnh không?
- Quy tắc về kiểu, giá trị thiếu, phạm vi và thứ tự ưu tiên có thống nhất không?
- Cùng một loại lỗi có được phát hiện và giải thích theo cách tương tự không?
- Tài liệu, ví dụ và công cụ có phản ánh đúng cùng một quy tắc không?

Tính nhất quán làm giảm số lượng quy tắc người dùng phải ghi nhớ. Thay vì học từng tính năng như một trường hợp riêng, người dùng học được một số mẫu chung và áp dụng chúng trong nhiều tình huống.

## 2. Vì sao tính nhất quán quan trọng?

### 2.1. Giảm gánh nặng học tập

Người mới học DSL thường bắt đầu bằng một vài cấu trúc cơ bản. Nếu các cấu trúc khác tuân theo cùng mẫu, kiến thức ban đầu có thể được tái sử dụng. Ví dụ, khi đã hiểu cách viết điều kiện trong một quy tắc, người dùng có thể nhận ra cách viết điều kiện tương tự trong bộ lọc hoặc chính sách.

Ngược lại, nếu mỗi phần của ngôn ngữ dùng một từ khóa và cách đặt dấu khác nhau cho cùng một ý niệm, người dùng phải ghi nhớ nhiều quy tắc rời rạc. Việc học trở nên chậm và dễ nhầm lẫn.

### 2.2. Giúp dự đoán hành vi

Người dùng không thể biết trước mọi tính năng của DSL. Nhưng nếu các tính năng tuân theo nguyên tắc chung, họ có thể dự đoán cách một biểu thức mới hoạt động. Chẳng hạn, nếu `==` luôn biểu thị so sánh bằng và `and` luôn kết hợp điều kiện theo logic Boolean, người dùng không phải tra cứu lại ý nghĩa của chúng trong từng loại quy tắc.

### 2.3. Giảm lỗi và chi phí bảo trì

Những cấu trúc không nhất quán thường tạo ra lỗi khó nhận ra: biểu thức vẫn hợp lệ nhưng mang ý nghĩa khác với dự định. Quy ước thống nhất giúp người viết, người xem xét và công cụ phát hiện điểm bất thường dễ hơn.

Khi nhóm phát triển bổ sung tính năng, một hệ thống quy tắc rõ ràng cũng giúp họ biết nên mở rộng theo mẫu nào. Điều này hạn chế việc mỗi tính năng mới tự tạo cú pháp, kiểu dữ liệu hoặc thông báo lỗi riêng.

### 2.4. Hỗ trợ công cụ và tự động hóa

Formatter, parser, trình soạn thảo, bộ kiểm tra và trình sinh tài liệu đều dựa vào các quy tắc của DSL. Nếu quy tắc thống nhất, các công cụ có thể hoạt động nhất quán và ít cần ngoại lệ. Ví dụ, một formatter có thể áp dụng cùng quy tắc xuống dòng cho tất cả khối `rule`, `entity` và `workflow` nếu chúng dùng một cấu trúc khai báo tương tự.

## 3. Các lớp tính nhất quán

Tính nhất quán nên được xem xét ở nhiều lớp liên kết với nhau.

| Lớp | Nội dung cần thống nhất | Ví dụ vấn đề khi thiếu nhất quán |
|---|---|---|
| Từ vựng | Tên khái niệm, từ khóa, cách viết tên | Cùng một khái niệm lúc gọi `customer`, lúc gọi `client` mà không phân biệt |
| Cú pháp | Cấu trúc câu lệnh, dấu phân cách, cách lồng khối | Một loại khai báo dùng `{}`, loại khác dùng `begin/end` không có lý do |
| Ngữ nghĩa | Ý nghĩa của từ khóa, toán tử và biểu thức | `and` có lúc là logic AND, lúc lại ghép chuỗi |
| Kiểu dữ liệu | Chuyển kiểu, so sánh, đơn vị và giá trị thiếu | Hai kiểu tiền tệ được cộng trực tiếp dù khác mã tiền |
| Phạm vi và thứ tự | Scope, precedence, ưu tiên quy tắc | Cùng biểu thức có kết quả khác nhau vì thứ tự đánh giá không rõ |
| Định dạng | Thụt lề, xuống dòng, dấu cách và quy ước trình bày | Formatter và tài liệu dùng hai phong cách khác nhau |
| Lỗi và chẩn đoán | Phân loại lỗi, vị trí và cách diễn giải | Cùng một lỗi kiểu lúc báo lỗi biên dịch, lúc âm thầm chuyển kiểu |
| Tài liệu và công cụ | Ví dụ, hướng dẫn, formatter, IDE và phiên bản | Tài liệu dùng cú pháp đã bị loại bỏ |

Các lớp này không tách rời. Ví dụ, một thuật ngữ không nhất quán trong từ vựng có thể dẫn đến hai tên thuộc tính khác nhau, khiến hệ thống kiểu và thông báo lỗi cũng trở nên khó hiểu.

## 4. Nhất quán về từ vựng và cách đặt tên

Từ vựng là phần người dùng nhìn thấy đầu tiên. Một DSL nên có bảng thuật ngữ chuẩn cho khái niệm miền, từ khóa, kiểu dữ liệu và thao tác.

### 4.1. Một khái niệm, một tên gọi rõ ràng

Giả sử miền bán hàng dùng khái niệm khách hàng. Nếu DSL lúc dùng `customer`, lúc dùng `client`, lúc dùng `buyer` cho cùng một khái niệm mà không phân biệt vai trò, người đọc có thể tưởng rằng đây là ba loại đối tượng khác nhau.

```text
// Không rõ các tên có cùng ý nghĩa hay không
customer.email
client.email
buyer.email
```

Nên chọn một tên chuẩn, ví dụ `customer`, và dùng nhất quán. Nếu miền thực sự có `buyer` khác `customer` — chẳng hạn người mua và chủ tài khoản là hai vai trò riêng — mô hình phải định nghĩa sự khác biệt thay vì ép chúng thành một thuật ngữ.

### 4.2. Thống nhất quy tắc đặt tên

Quy ước đặt tên có thể quy định:

- Kiểu và khái niệm dùng `PascalCase`, ví dụ `Order`, `CustomerId`.
- Thuộc tính và biến dùng `camelCase`, ví dụ `orderDate`, `totalAmount`.
- Hằng số hoặc giá trị enum dùng một kiểu viết thống nhất, ví dụ `PENDING`, `APPROVED`.
- Từ khóa của ngôn ngữ dùng một dạng viết thống nhất, tránh trộn `when`, `WHEN` và `When` nếu không có mục đích.
- Tên đơn vị, tiền tệ và thời gian dùng ký hiệu hoặc kiểu miền đã được định nghĩa.

Đây là ví dụ về một quy ước có thể chọn; không có một kiểu chữ bắt buộc cho mọi DSL. Điều quan trọng là lựa chọn được ghi lại, áp dụng đều và phù hợp với người dùng.

### 4.3. Phân biệt từ đồng nghĩa và khái niệm khác nhau

Trong ngôn ngữ tự nhiên, nhiều từ có thể gần nghĩa. Trong DSL, mỗi tên cần có phạm vi ý nghĩa rõ. Nếu hai thuật ngữ thật sự khác nhau, hãy giữ hai tên và định nghĩa quan hệ. Nếu chúng là từ đồng nghĩa trong nghiệp vụ, hãy chọn tên chuẩn và có thể ghi tên thay thế trong tài liệu hoặc metadata.

## 5. Nhất quán về cú pháp

Cú pháp quy định cách kết hợp từ khóa, tên, biểu thức, dấu phân cách và khối lệnh. Một DSL có thể chọn phong cách khai báo, phong cách giống biểu thức hoặc phong cách gần với ngôn ngữ tự nhiên. Sau khi chọn, cần áp dụng có hệ thống.

### 5.1. Cùng loại cấu trúc nên có cùng hình thức

Ví dụ, DSL có thể dùng mẫu `rule ... { ... }` cho mọi quy tắc:

```text
rule freeShipping {
    when order.total >= 1_000_000
    then shipping.fee = 0
}

rule remoteSurcharge {
    when destination.zone == "remote"
    then shipping.fee += 15_000
}
```

Cả hai quy tắc dùng cùng cách khai báo tên, mở khối, viết điều kiện và hành động. Người đọc học mẫu một lần rồi áp dụng cho các quy tắc khác.

Nếu một cấu trúc khác biệt về bản chất, cú pháp có thể khác. Ví dụ, khai báo kiểu dữ liệu và khai báo một quy tắc có mục tiêu khác nhau, nên không cần ép chúng dùng cùng từ khóa. Tính nhất quán không đồng nghĩa với việc mọi thứ phải có hình thức giống hệt nhau.

### 5.2. Thống nhất dấu phân cách và cách lồng khối

Một DSL nên xác định rõ:

- Khối được mở và đóng bằng `{}` hay bằng từ khóa như `begin` và `end`.
- Có cần dấu chấm phẩy cuối câu lệnh hay không.
- Dấu phẩy dùng để phân tách tham số, phần tử hoặc thuộc tính ở đâu.
- Cách lồng danh sách, biểu thức và khối con.
- Cách xuống dòng khi biểu thức dài.

Ví dụ, nếu DSL chọn `{}` cho các khối, hãy dùng nó thống nhất trong `entity`, `rule` và `workflow`. Nếu một cấu trúc cần dạng đặc biệt, tài liệu phải giải thích lý do.

### 5.3. Nhất quán trong cách biểu đạt biểu thức

Giả sử DSL hỗ trợ điều kiện lọc. Nên chọn một cách viết chuẩn:

```text
where order.status == PAID
where order.total >= 500_000
where customer.region in ["north", "central"]
```

Không nên trộn nhiều mẫu không cần thiết cho cùng mục đích:

```text
where order.status == PAID
filter order.total >= 500_000
only customer.region in ["north", "central"]
```

`where`, `filter` và `only` có thể là ba từ khóa khác nhau nếu DSL định nghĩa ba loại thao tác khác nhau. Nhưng nếu chúng chỉ là ba cách viết cho cùng một bộ lọc, sự đa dạng đó làm tăng gánh nặng học tập.

## 6. Nhất quán về ngữ nghĩa

Ngữ nghĩa xác định một biểu thức hợp lệ có ý nghĩa gì và được xử lý ra sao. Cú pháp giống nhau nhưng ngữ nghĩa thay đổi tùy ngữ cảnh có thể nguy hiểm hơn cú pháp khác nhau, vì người dùng dễ nghĩ rằng hai biểu thức có cùng hành vi.

### 6.1. Một toán tử, một ý nghĩa có thể dự đoán

Nếu `==` biểu thị so sánh bằng, nó nên giữ ý nghĩa đó trong các ngữ cảnh được hỗ trợ. Với các kiểu khác nhau, DSL có thể từ chối phép so sánh hoặc định nghĩa cách so sánh cụ thể, nhưng không nên âm thầm thay đổi `==` thành phép gán hay so khớp mẫu.

| Toán tử | Ý nghĩa đề xuất |
|---|---|
| `==` | So sánh bằng |
| `!=` | So sánh khác |
| `<`, `<=` | So sánh thứ tự |
| `>`, `>=` | So sánh thứ tự |
| `and` | Kết hợp hai điều kiện Boolean |
| `or` | Tuyển giữa hai điều kiện Boolean |
| `not` | Phủ định điều kiện Boolean |

Nếu DSL dùng từ khóa thay cho ký hiệu, vẫn cần giữ một ngữ nghĩa thống nhất. Cùng một toán tử không nhất thiết phải áp dụng được cho mọi kiểu; tính nhất quán nằm ở việc quy tắc áp dụng và ngoại lệ được xác định rõ.

### 6.2. Không thay đổi ý nghĩa ngầm theo ngữ cảnh

Ví dụ, `+` có thể được dùng để cộng số, cộng tiền cùng loại tiền tệ hoặc nối chuỗi nếu ngôn ngữ hỗ trợ các phép toán đó. Nhưng nếu cùng cú pháp `+` ở một ngữ cảnh khác lại có nghĩa “thêm điều kiện” hoặc “kích hoạt quy tắc”, người dùng sẽ khó dự đoán.

Khi cần overload toán tử, phải xác định các kiểu được hỗ trợ và bảo đảm ý nghĩa gần với kỳ vọng thông thường. Nếu ý nghĩa khác biệt nhiều, một hàm có tên rõ ràng thường tốt hơn.

### 6.3. Nhất quán về thứ tự ưu tiên

DSL phải quy định thứ tự ưu tiên của toán tử và cách nhóm biểu thức. Ví dụ, với điều kiện:

```text
not A or B and C
```

Người dùng cần biết `and` được tính trước `or` hay biểu thức được đánh giá từ trái sang phải. Một cách an toàn là định nghĩa bảng precedence rõ ràng và khuyến khích dùng ngoặc khi biểu thức phức tạp:

```text
(not A) or (B and C)
```

Không nên để thứ tự ưu tiên khác nhau giữa biểu thức điều kiện của `rule` và biểu thức lọc của `query`, trừ khi có lý do chuyên biệt được giải thích rõ.

### 6.4. Nhất quán về giá trị thiếu và Boolean

Khi dữ liệu thiếu, biểu thức Boolean có thể cần xử lý trạng thái chưa biết. DSL phải xác định một phép so sánh với giá trị thiếu trả về `false`, `null`, `unknown` hay phát sinh lỗi. Nếu dùng logic ba giá trị, cần giải thích cách `and`, `or` và `not` hoạt động với `unknown`.

Ví dụ, `customer.email == "a@example.com"` khi email chưa được cung cấp cần có kết quả rõ ràng. Nếu một phần của DSL coi điều kiện thiếu là `false` còn phần khác coi là lỗi, người dùng có thể nhận kết quả không nhất quán.

## 7. Nhất quán về kiểu dữ liệu và đơn vị

Kiểu dữ liệu là một phần của ngữ nghĩa. Một DSL nên áp dụng cùng quy tắc kiểu ở mọi nơi, bao gồm khai báo thuộc tính, biểu thức, tham số hàm và giá trị trả về.

### 7.1. Tránh chuyển kiểu ngầm không rõ ràng

Ví dụ, không nên tự động coi chuỗi `"100"` là số nguyên trong một phép so sánh số mà không có quy tắc chuyển đổi rõ ràng. Chuyển đổi ngầm có thể khiến dữ liệu sai định dạng đi qua kiểm tra hoặc cho kết quả khác nhau tùy ngữ cảnh.

```text
// Rõ ràng hơn nếu DSL yêu cầu kiểu số
order.total >= 100

// Không nên âm thầm diễn giải chuỗi thành số
order.total >= "100"
```

Nếu hỗ trợ ép kiểu, DSL nên cung cấp hàm chuyển đổi tường minh và xác định cách xử lý khi chuyển đổi thất bại.

### 7.2. Nhất quán về đơn vị

Các giá trị số có đơn vị không thể được xem như những con số thuần túy. `5 kg` và `500 g` có thể so sánh sau khi quy đổi; `5 USD` và `500 VND` cần tỷ giá và thời điểm quy đổi.

DSL nên dùng kiểu miền hoặc metadata đơn vị để ngăn phép toán không hợp lệ. Quy tắc so sánh, cộng, trừ và làm tròn cần nhất quán trong mọi biểu thức.

### 7.3. Nhất quán về ngày giờ

Phân biệt ngày lịch, thời điểm tuyệt đối và giờ địa phương. Nếu một thuộc tính là `Date`, không nên tự động so sánh với `Instant` mà không có quy tắc chuyển đổi. Múi giờ, độ chính xác và quy tắc làm tròn thời gian cần được xác định thống nhất.

## 8. Nhất quán về phạm vi và quy tắc áp dụng

Phạm vi (scope) xác định tên hoặc biến nào có thể được tham chiếu tại một vị trí. Một DSL cần có quy tắc rõ về phạm vi module, entity, rule, lambda và khối lồng nhau.

Ví dụ:

```text
entity Order {
    status: OrderStatus

    rule canShip {
        when status == PAID
        then shippingAllowed = true
    }
}
```

Trong khối `rule`, `status` có thể được hiểu là `Order.status` do phạm vi của entity. Nếu cùng tên xuất hiện trong một khối lồng khác, DSL cần quy định rõ cách phân giải tên và cách tham chiếu tường minh khi có xung đột.

Quy tắc ưu tiên cũng cần nhất quán. Nếu nhiều rule cùng áp dụng, DSL phải xác định chúng chạy theo thứ tự khai báo, theo độ ưu tiên, theo nhóm hay độc lập. Không nên để thứ tự thực thi phụ thuộc ngẫu nhiên vào thứ tự duyệt cấu trúc nội bộ.

## 9. Nhất quán về định dạng và phong cách trình bày

Định dạng không thay thế ngữ nghĩa, nhưng ảnh hưởng lớn đến khả năng đọc. DSL nên có quy ước chuẩn cho thụt lề, khoảng trắng, xuống dòng, dấu phẩy và cách trình bày biểu thức dài.

Ví dụ phong cách định dạng:

```text
rule freeShipping {
    when order.total >= 1_000_000
         and order.status == PAID
    then shipping.fee = 0
}
```

Các quy ước có thể bao gồm:

- Một mức thụt lề cố định cho mỗi cấp khối.
- Một cách thống nhất để xuống dòng giữa điều kiện và hành động.
- Khoảng trắng nhất quán quanh toán tử nhị phân.
- Cách viết danh sách nhiều phần tử, dấu phẩy cuối và biểu thức nhiều dòng.
- Cách sắp xếp thuộc tính trong khai báo khi thứ tự có ý nghĩa hoặc không có ý nghĩa.
- Cách đặt chú thích và tài liệu ngay cạnh phần tử liên quan.

Nên có formatter tự động nếu DSL được sử dụng thường xuyên. Formatter cần tạo ra một dạng chuẩn (canonical format), để cùng một biểu thức không bị trình bày thành nhiều phong cách khác nhau trong kho mã.

## 10. Nhất quán trong thông báo lỗi

Người dùng cần nhận được thông tin lỗi có cấu trúc và có thể hành động. Một DSL nhất quán nên phân loại lỗi theo nhóm, chỉ rõ vị trí, biểu thức gây lỗi và cách sửa nếu có thể.

| Nhóm lỗi | Ví dụ | Thông tin nên cung cấp |
|---|---|---|
| Lỗi cú pháp | Thiếu `}` hoặc thiếu toán hạng | Vị trí lỗi, cấu trúc đang chờ |
| Lỗi tên | Tham chiếu `order.staus` không tồn tại | Tên sai, tên hợp lệ gần giống nếu có |
| Lỗi kiểu | So sánh `Money` với `Date` | Kiểu thực tế và kiểu được yêu cầu |
| Lỗi ngữ nghĩa | Hai trạng thái chuyển đổi không hợp lệ | Quy tắc bị vi phạm và ngữ cảnh |
| Lỗi cấu hình | Thiếu thuộc tính bắt buộc | Thuộc tính và cách cung cấp giá trị |
| Lỗi thực thi | Không truy cập được nguồn dữ liệu | Thao tác thất bại và mã lỗi liên quan |

Ví dụ thông báo lỗi tốt:

```text
row: 12, column: 18
Unknown property: order.staus
Did you mean: order.status?
```

Thông báo lỗi nên dùng thuật ngữ thống nhất với tài liệu. Nếu tài liệu gọi một khái niệm là `OrderStatus`, lỗi cũng nên dùng đúng tên đó, thay vì gọi lúc là “state”, lúc là “phase” mà không phân biệt.

## 11. Nhất quán giữa cú pháp, ngữ nghĩa và tài liệu

Một DSL có thể được định nghĩa tốt trong mã nguồn nhưng vẫn gây khó hiểu nếu tài liệu dùng ví dụ khác, hoặc công cụ xử lý không thực hiện đúng quy tắc đã công bố.

Để duy trì sự thống nhất:

1. Có tài liệu từ vựng và thuật ngữ chuẩn.
2. Định nghĩa ngữ pháp hoặc cấu trúc hợp lệ cho từng thành phần.
3. Mô tả ngữ nghĩa của từ khóa, toán tử, kiểu, scope và thứ tự thực thi.
4. Dùng cùng ví dụ trong tài liệu, hướng dẫn, test và thông báo lỗi.
5. Để formatter và validator dựa trên cùng một định nghĩa ngôn ngữ.
6. Cập nhật tài liệu và ví dụ khi thay đổi cú pháp hoặc ngữ nghĩa.

Ví dụ, nếu `optional` có nghĩa là thuộc tính có thể vắng mặt trong khai báo entity, tài liệu, parser, bộ kiểm tra kiểu và công cụ sinh schema phải hiểu nó theo cùng một cách.

## 12. Tính nhất quán và khả năng mở rộng

DSL thường phát triển bằng cách bổ sung kiểu, từ khóa, toán tử và cấu trúc mới. Mỗi phần mở rộng đều có nguy cơ tạo ra ngoại lệ làm giảm tính nhất quán.

Khi thêm tính năng, nên đặt câu hỏi:

- Tính năng mới có thể dùng lại một cấu trúc đã tồn tại không?
- Nó có giới thiệu từ khóa trùng hoặc gần nghĩa với từ khóa hiện có không?
- Ngữ nghĩa có phù hợp với quy tắc chung của toán tử và kiểu dữ liệu không?
- Có tạo ra ngoại lệ trong precedence, scope hoặc cách xử lý lỗi không?
- Tính năng có làm cú pháp trở nên khó dự đoán hoặc có nhiều cách viết tương đương không?

Không phải mọi ngoại lệ đều xấu. Một miền có thể cần cấu trúc đặc biệt để mô tả một khái niệm thật sự khác biệt. Nhưng ngoại lệ cần có lý do rõ, phạm vi hẹp và được ghi trong tài liệu.

### 12.1. Tránh nhiều cách viết tương đương không cần thiết

Giả sử DSL cho phép ba cách viết cùng một điều kiện:

```text
where order.total > 100
filter order.total > 100
only order.total > 100
```

Nếu cả ba có cùng ngữ nghĩa, người dùng phải nhớ ba từ khóa mà không nhận được lợi ích. Nên chọn một dạng chuẩn, hoặc định nghĩa rõ các dạng này khác nhau ở đâu.

### 12.2. Quản lý thay đổi phá vỡ tương thích

Khi thay đổi cú pháp hoặc ngữ nghĩa, cần xác định ảnh hưởng đến các biểu thức đã tồn tại. Có thể dùng version của DSL, cảnh báo deprecated, công cụ migration hoặc hỗ trợ song song hai phiên bản trong một khoảng thời gian.

Ví dụ, nếu phiên bản mới thay đổi cách `and` và `or` được nhóm, biểu thức cũ có thể cho kết quả khác dù vẫn phân tích được. Thay đổi ngữ nghĩa như vậy cần được xem là thay đổi tương thích nghiêm trọng và có kế hoạch chuyển đổi rõ ràng.

## 13. Cách xây dựng và duy trì tính nhất quán

### 13.1. Tạo bộ quy ước ngôn ngữ

Trước khi triển khai nhiều tính năng, nhóm nên lập một tài liệu quy ước ngôn ngữ gồm:

- Bảng thuật ngữ và tên chuẩn của các khái niệm miền.
- Quy tắc đặt tên và viết từ khóa.
- Mẫu cú pháp cho entity, rule, query, workflow hoặc cấu trúc tương ứng.
- Bảng toán tử, precedence và associativity.
- Quy tắc kiểu dữ liệu, ép kiểu, đơn vị và giá trị thiếu.
- Quy tắc scope, tham chiếu tên và thứ tự thực thi.
- Quy ước định dạng, chú thích và thông báo lỗi.
- Chính sách versioning, deprecation và migration.

### 13.2. Tạo ví dụ chuẩn và bộ kiểm thử conformance

Mỗi quy tắc quan trọng nên có ví dụ hợp lệ và không hợp lệ. Bộ kiểm thử conformance giúp bảo đảm parser, validator, interpreter và formatter cùng tuân theo một định nghĩa.

Ví dụ, nếu DSL định nghĩa `and` có precedence cao hơn `or`, cần có test chứng minh biểu thức không có ngoặc được phân tích theo đúng quy tắc. Nếu thuộc tính `Money` chỉ so sánh với `Money` cùng currency, cần có test cho trường hợp cùng tiền tệ và khác tiền tệ.

### 13.3. Dùng formatter và validator chung

Formatter chuẩn hóa cách trình bày. Validator kiểm tra cấu trúc, tên, kiểu và ràng buộc. Hai công cụ nên dùng cùng nguồn định nghĩa hoặc cùng thư viện lõi để tránh trường hợp formatter chấp nhận biểu thức mà validator từ chối, hoặc ngược lại.

### 13.4. Review tính năng theo nguyên tắc hiện có

Khi thêm một từ khóa hoặc cấu trúc mới, người thiết kế cần xem xét nó trong toàn bộ hệ thống quy tắc. Một tính năng có thể hợp lệ riêng lẻ nhưng phá vỡ sự nhất quán chung nếu dùng thuật ngữ khác, precedence khác hoặc thông báo lỗi khác.

### 13.5. Thu thập phản hồi từ người dùng

Quan sát cách người dùng viết và đọc DSL để tìm những điểm họ thường hỏi lại, viết sai hoặc hiểu khác nhau. Nếu một cấu trúc liên tục gây nhầm lẫn, có thể vấn đề nằm ở tên gọi, cú pháp, ngữ nghĩa hoặc tài liệu. Thay đổi cần được cân nhắc cùng khả năng tương thích của biểu thức cũ.

## 14. Ví dụ tổng hợp: một DSL nhất quán và không nhất quán

Giả sử DSL mô tả quy tắc vận chuyển đơn hàng. Một thiết kế thiếu nhất quán có thể trông như sau:

```text
rule freeShipping {
    when order.total >= 1_000_000
    then shipping.fee = 0
}

policy remoteArea:
    if destination.zone == "remote"
    do shipping.fee += 15_000

filter paidOrders where order.status == PAID
```

Các cấu trúc dùng `rule`, `policy`, `filter`, `when`, `if`, `then`, `do` và dấu phân cách khác nhau. Nếu chúng đại diện cho các khái niệm khác nhau thì cần định nghĩa; nếu chỉ là các cách viết tùy tiện cho cùng một loại quy tắc thì thiết kế này làm tăng số quy ước phải học.

Một cách thống nhất hơn có thể là:

```text
rule freeShipping {
    when order.total >= 1_000_000
    then shipping.fee = 0
}

rule remoteAreaSurcharge {
    when destination.zone == "remote"
    then shipping.fee += 15_000
}

rule paidOrder {
    when order.status == PAID
    then order.isEligibleForShipping = true
}
```

Cả ba quy tắc đều dùng một cấu trúc khai báo. Nếu DSL cần truy vấn hoặc lọc dữ liệu, có thể có một cấu trúc riêng vì mục đích của nó khác với khai báo hành động. Tính nhất quán yêu cầu phân biệt rõ vai trò, không ép mọi tác vụ vào một mẫu duy nhất.

## 15. Cân bằng tính nhất quán với sự linh hoạt

Thiết kế quá cứng nhắc có thể làm DSL khó biểu đạt những khái niệm thực sự khác biệt. Ngược lại, cho phép quá nhiều cách viết khiến ngôn ngữ trở nên khó học và khó duy trì.

Có thể áp dụng nguyên tắc:

- Thống nhất mạnh đối với các khái niệm và thao tác phổ biến.
- Cho phép khác biệt khi miền có ý nghĩa hoặc cấu trúc thực sự khác.
- Không thêm cú pháp chỉ để tạo phong cách riêng nếu một cấu trúc hiện có đã diễn đạt rõ.
- Nếu cần ngoại lệ, giải thích rõ lý do và phạm vi.
- Ưu tiên khả năng dự đoán hơn sự ngắn gọn nhất thời.

Ví dụ, một DSL có thể dùng `rule` cho quy tắc điều kiện-hành động, `entity` cho cấu trúc dữ liệu và `workflow` cho quy trình nhiều bước. Ba từ khóa khác nhau là hợp lý vì chúng đại diện cho ba loại khái niệm khác nhau. Nhưng tất cả vẫn có thể dùng cùng quy tắc tên, dấu ngoặc khối, thụt lề, chú thích và thông báo lỗi.

## 16. Kết luận

Tính nhất quán giúp DSL có một hệ thống quy tắc dễ học, dễ dự đoán và dễ bảo trì. Nó cần được bảo đảm xuyên suốt từ vựng, cú pháp, ngữ nghĩa, kiểu dữ liệu, scope, định dạng, thông báo lỗi, tài liệu và cách mở rộng ngôn ngữ.

Một DSL nhất quán không buộc mọi cấu trúc phải giống nhau. Nó bảo đảm rằng những cấu trúc có cùng vai trò tuân theo cùng nguyên tắc, còn những khác biệt thật sự của miền được biểu đạt rõ ràng và có lý do. Khi thiết kế hoặc mở rộng DSL, hãy ưu tiên các mẫu có thể tái sử dụng, quy tắc ngữ nghĩa ổn định, công cụ dùng chung và khả năng tương thích có kiểm soát.
