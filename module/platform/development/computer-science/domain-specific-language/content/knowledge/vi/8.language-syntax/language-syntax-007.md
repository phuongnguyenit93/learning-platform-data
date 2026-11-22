# Dấu phân cách và khối

## 1. Vai trò của dấu phân cách và khối trong cú pháp DSL

Ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) cần một cách biểu diễn rõ ràng để người viết và công cụ cùng nhận biết đâu là tên, giá trị, biểu thức, câu lệnh và nhóm câu lệnh. Từ khóa và tên định danh cho biết các thành phần có ý nghĩa gì; **dấu phân cách (delimiter)** cho biết ranh giới giữa chúng; **khối (block)** gom các thành phần có quan hệ với nhau thành một đơn vị cú pháp.

Ví dụ, trong một DSL giả định dùng để mô tả pipeline:

~~~text
pipeline "daily-revenue" {
    source "orders.csv"
    filter status == "PAID"
    group_by customer_id
    aggregate total = sum(amount)
    output "daily-revenue.csv"
}
~~~

Dấu ngoặc nhọn `{` và `}` đánh dấu phần nội dung thuộc pipeline. Dấu ngoặc kép xác định ranh giới chuỗi. Dấu ngoặc tròn trong `sum(amount)` xác định danh sách đối số của lời gọi hàm. Xuống dòng phân tách các khai báo theo quy ước của ví dụ này.

Những dấu hiệu đó giúp parser xác định cấu trúc mà không phải đoán ý định từ văn bản tự do. Nếu thiếu dấu đóng, đặt dấu phân cách sai vị trí hoặc lồng khối không hợp lệ, công cụ có thể phát hiện lỗi và chỉ ra vị trí cần sửa.

Trong thiết kế DSL, dấu phân cách và khối ảnh hưởng đến:

- Khả năng đọc và nhận biết cấu trúc của người dùng.
- Cách viết ngữ pháp và độ phức tạp của parser.
- Quy tắc lồng nhau, phạm vi tên và quan hệ giữa các câu lệnh.
- Khả năng định dạng tự động, tô màu cú pháp và hỗ trợ IDE.
- Cách phát hiện, phục hồi và báo lỗi khi cấu trúc không hoàn chỉnh.
- Khả năng mở rộng cú pháp mà không làm thay đổi cách hiểu các tệp cũ.

Một thiết kế tốt chọn dấu phân cách nhất quán, có vai trò rõ ràng và phù hợp với người dùng của miền. Việc thêm nhiều loại dấu hoặc nhiều kiểu khối không tự làm ngôn ngữ mạnh hơn; mỗi cấu trúc nên giải quyết một nhu cầu biểu đạt cụ thể.

## 2. Dấu phân cách là gì?

Dấu phân cách là ký hiệu hoặc chuỗi ký hiệu được ngôn ngữ dùng để đánh dấu ranh giới, tách thành phần hoặc bao quanh một cấu trúc. Dấu phân cách có thể gồm một ký tự như dấu phẩy, dấu chấm phẩy, dấu hai chấm, hoặc một cặp ký hiệu như ngoặc tròn, ngoặc vuông và ngoặc nhọn.

Không phải mọi ký hiệu đặc biệt đều là dấu phân cách. Chẳng hạn, toán tử cộng thường là `+`, toán tử so sánh bằng là `==`, còn `{` và `}` có thể là dấu mở và đóng khối. Vai trò cụ thể phụ thuộc vào ngữ pháp của DSL.

### 2.1. Các nhóm dấu phân cách thường gặp

| Dấu hoặc cặp dấu | Vai trò thường gặp | Ví dụ |
|---|---|---|
| `{` và `}` | Mở và đóng khối | `pipeline { ... }` |
| `(` và `)` | Gom nhóm biểu thức hoặc đối số | `sum(amount)` |
| `[` và `]` | Danh sách, chỉ mục hoặc phần tử tùy chọn | `fields[0]`, `[a, b, c]` |
| `,` | Tách phần tử trong danh sách | `group_by region, customer_id` |
| `;` | Kết thúc câu lệnh hoặc phân tách mục | `set x = 1;` |
| `:` | Tách khóa và giá trị hoặc mở khối theo thụt lề | `timeout: 30` |
| `.` | Truy cập thành viên hoặc phân cấp tên | `order.customer.id` |
| `->` | Chỉ quan hệ hoặc chuyển tiếp | `Draft -> Approved` |
| `"` hoặc `'` | Bao quanh chuỗi ký tự | `"orders.csv"` |

Bảng trên mô tả các quy ước phổ biến, không phải quy định bắt buộc cho mọi DSL. Cùng một dấu có thể có vai trò khác nhau trong các ngôn ngữ khác nhau. Ví dụ, dấu hai chấm có thể mở một khối theo thụt lề, tách khóa và giá trị, hoặc giới thiệu kiểu dữ liệu.

### 2.2. Dấu mở và dấu đóng

Một số dấu phân cách xuất hiện theo cặp:

- Dấu mở bắt đầu một vùng cấu trúc.
- Dấu đóng kết thúc vùng cấu trúc tương ứng.

Ví dụ:

~~~text
pipeline {
    filter (amount > 100 and status == "PAID")
}
~~~

Ở đây, ngoặc nhọn bao quanh khối pipeline, còn ngoặc tròn bao quanh biểu thức điều kiện. Mỗi dấu đóng phải tương ứng với đúng dấu mở theo quy tắc ngữ pháp.

Parser thường dùng một ngăn xếp (stack) để theo dõi các dấu mở chưa được đóng. Khi gặp dấu mở, parser ghi nhận loại dấu và vị trí của nó. Khi gặp dấu đóng, parser kiểm tra xem nó có khớp với dấu mở gần nhất chưa được đóng hay không.

Ví dụ:

~~~text
call([1, 2, 3)
~~~

Biểu thức trên có dấu `(` và dấu `[` nhưng thứ tự đóng không khớp. Dấu `)` không thể đóng dấu `[` còn đang mở. Một thông báo lỗi hữu ích nên chỉ ra vị trí dấu `)` và có thể nhắc vị trí dấu `[` cần được đóng trước.

### 2.3. Dấu phân cách không phải nội dung dữ liệu

Trong nhiều cú pháp, dấu phân cách có vai trò cấu trúc và không trở thành giá trị dữ liệu. Ví dụ, dấu phẩy giữa các phần tử trong `[10, 20, 30]` dùng để tách phần tử; nó không phải một phần của số `10` hay `20`.

Ngược lại, ký tự giống dấu phân cách có thể xuất hiện bên trong chuỗi hoặc chú thích mà không mang vai trò cấu trúc:

~~~text
message = "Use { and } in the template"
# Ví dụ về dấu phẩy: a, b, c
~~~

Lexer cần nhận biết ngữ cảnh chuỗi và chú thích để không hiểu nhầm dấu ngoặc hoặc dấu phẩy bên trong chúng là dấu cấu trúc. Đây là lý do parser không nên chỉ đếm ký tự ngoặc trên văn bản thô.

## 3. Khối là gì?

**Khối (block)** là một nhóm khai báo, câu lệnh hoặc biểu thức được xem như một đơn vị cú pháp. Khối thường có một cấu trúc mở đầu, phần nội dung và một ranh giới kết thúc. Tùy DSL, ranh giới có thể được đánh dấu bằng cặp dấu ngoặc, thụt lề, từ khóa kết thúc hoặc quy tắc kết thúc câu lệnh.

Ví dụ một khối có dấu ngoặc nhọn:

~~~text
service "billing" {
    replicas 3
    image "billing:1.2"
    health_check {
        path "/health"
        interval 10s
    }
}
~~~

Khối `service` chứa các thuộc tính `replicas`, `image` và một khối con `health_check`. Khối con chứa các khai báo riêng. Cấu trúc lồng nhau thể hiện quan hệ bao chứa giữa dịch vụ và cấu hình kiểm tra sức khỏe.

### 3.1. Khối cú pháp và phạm vi ngữ nghĩa

Khối cú pháp xác định phần văn bản thuộc về một cấu trúc. Phạm vi ngữ nghĩa (scope) xác định tên, biến hoặc khai báo nào có thể được tham chiếu tại một vị trí. Hai khái niệm thường liên quan nhưng không đồng nhất.

Ví dụ:

~~~text
pipeline "report" {
    let region = "north"

    step "summary" {
        use region
    }
}
~~~

Nếu DSL quy định khai báo `region` có phạm vi trong toàn bộ pipeline, khối `step` có thể tham chiếu đến nó. Nếu DSL quy định mỗi khối là một phạm vi riêng và không kế thừa tên từ khối cha, lời gọi `use region` có thể không hợp lệ. Cặp ngoặc nhọn chỉ xác định cấu trúc; quy tắc phân giải tên phải được đặc tả riêng.

Không nên mặc định mọi dấu ngoặc tạo ra một scope mới. Trong nhiều ngôn ngữ, ngoặc tròn chỉ nhóm biểu thức và không tạo phạm vi tên. Một danh sách trong ngoặc vuông cũng thường không tạo scope.

### 3.2. Các kiểu khối thường gặp

| Kiểu khối | Mục đích | Ví dụ miền |
|---|---|---|
| Khối khai báo | Gom cấu hình thuộc một đối tượng | Khối `service` chứa image và replicas |
| Khối điều kiện | Gom các thao tác chỉ chạy khi điều kiện đúng | `if`, `when`, `otherwise` |
| Khối lặp | Gom thao tác lặp lại | `for each customer { ... }` |
| Khối quy trình | Gom các bước thuộc một pipeline hoặc workflow | `pipeline { ... }` |
| Khối định nghĩa | Gom thành phần được đặt tên và tái sử dụng | `rule`, `template`, `module` |
| Khối giao dịch | Gom các thao tác có quy tắc commit hoặc rollback | `transaction { ... }` |

Một DSL cấu hình có thể chỉ cần khối khai báo. DSL mô tả workflow có thể cần khối điều kiện, lặp và quy trình. Chỉ nên hỗ trợ các kiểu khối có ý nghĩa trong miền.

## 4. Những cách biểu diễn ranh giới khối

Có nhiều chiến lược đánh dấu phần đầu và cuối của một khối. Mỗi cách có lợi ích và chi phí riêng.

### 4.1. Dùng ngoặc nhọn

~~~text
pipeline "daily" {
    source "orders.csv"
    filter status == "PAID"
}
~~~

Ưu điểm:

- Ranh giới mở và đóng thể hiện rõ.
- Có thể lồng nhiều khối.
- Parser dễ xác định điểm kết thúc của khối khi dấu ngoặc cân bằng.
- Việc định dạng và di chuyển đoạn mã ít phụ thuộc vào khoảng trắng.

Hạn chế:

- Người dùng phải viết đủ dấu đóng.
- Nhiều cấp lồng nhau có thể làm mã có nhiều dấu ngoặc.
- Thiếu hoặc đặt sai dấu ngoặc có thể gây lỗi cú pháp và làm parser khó phục hồi.

### 4.2. Dùng từ khóa mở và kết thúc

Một DSL có thể dùng từ khóa để đánh dấu khối:

~~~text
PIPELINE daily
    SOURCE orders.csv
    FILTER status == "PAID"
END PIPELINE
~~~

Hoặc:

~~~text
begin pipeline "daily"
    source "orders.csv"
    filter status == "PAID"
end pipeline
~~~

Từ khóa kết thúc có thể giúp khối dễ nhận biết trong tài liệu dài. Tuy nhiên, người viết phải ghi từ khóa kết thúc tương ứng; việc lồng nhiều khối có thể tạo ra nhiều cặp `begin/end`. Parser cũng cần kiểm tra loại khối ở phần kết thúc có khớp với phần mở đầu không.

### 4.3. Dùng thụt lề

Một số DSL hoặc ngôn ngữ cấu hình dùng mức thụt lề để biểu diễn cấu trúc:

~~~yaml
pipeline:
  name: daily
  source:
    path: orders.csv
  filter:
    field: status
    equals: PAID
~~~

Ở đây, mức thụt lề cho biết phần tử nào thuộc về khóa hoặc cấu trúc cha. Cú pháp YAML là một ví dụ về định dạng dữ liệu có cấu trúc; khi dùng YAML làm bề mặt cho DSL, ngữ nghĩa pipeline vẫn do ứng dụng định nghĩa.

Ưu điểm:

- Cấu trúc lồng nhau có thể dễ nhìn.
- Không cần lặp lại dấu ngoặc đóng.
- Phù hợp với tệp cấu hình có nhiều thuộc tính.

Hạn chế:

- Khoảng trắng đầu dòng trở thành một phần quan trọng của cú pháp.
- Tab và dấu cách có thể gây khác biệt nếu quy tắc không rõ.
- Sao chép hoặc di chuyển khối có thể vô tình làm thay đổi cấu trúc.
- Parser cần xác định quy tắc thụt lề và báo lỗi cho mức thụt không hợp lệ.

### 4.4. Dùng dấu phân cách kết thúc câu lệnh

Một DSL có thể yêu cầu dấu chấm phẩy để kết thúc từng câu lệnh:

~~~text
pipeline "daily" {
    source "orders.csv";
    filter status == "PAID";
    output "paid.csv";
}
~~~

Dấu chấm phẩy giúp phân biệt ranh giới câu lệnh ngay cả khi chúng nằm trên cùng một dòng. Nếu DSL cho phép bỏ dấu chấm phẩy ở cuối dòng, phải định nghĩa rõ khi nào xuống dòng được xem là kết thúc câu lệnh.

### 4.5. Kết hợp nhiều chiến lược

Một DSL có thể dùng ngoặc nhọn để xác định khối, ngoặc tròn để nhóm biểu thức, ngoặc vuông để tạo danh sách và dấu chấm phẩy để kết thúc câu lệnh:

~~~text
workflow "monthly-report" {
    let regions = ["north", "south", "west"];

    for each region in regions {
        run_report(
            region,
            period("2026-11")
        );
    }
}
~~~

Việc kết hợp là bình thường nếu mỗi dấu có vai trò riêng, nhất quán và có quy tắc lồng nhau rõ ràng.

## 5. Dấu ngoặc và chức năng của chúng

### 5.1. Ngoặc nhọn: `{ }`

Ngoặc nhọn thường bao quanh khối khai báo hoặc khối điều khiển:

~~~text
rule "eligible-customer" {
    when customer.total >= 1000
    then customer.setTier("GOLD")
}
~~~

Các câu lệnh giữa `{` và `}` thuộc khối `rule`. Khi cho phép lồng nhau, parser cần ghép đúng cặp ngoặc và xác định loại câu lệnh nào được phép xuất hiện trong từng loại khối.

Một khối có thể rỗng nếu ngữ pháp cho phép:

~~~text
on_success {}
~~~

Nếu khối rỗng không có ý nghĩa trong miền, grammar có thể yêu cầu ít nhất một câu lệnh. Quyết định này cần nhất quán và có thông báo lỗi rõ.

### 5.2. Ngoặc tròn: `( )`

Ngoặc tròn thường dùng để:

- Gom nhóm biểu thức.
- Bao quanh đối số hàm.
- Xác định điều kiện.
- Thể hiện thứ tự ưu tiên.

Ví dụ:

~~~text
filter (amount > 100 and status == "PAID")
aggregate total = sum(amount)
~~~

Ngoặc tròn không nhất thiết biểu thị một block. Trong hai ví dụ trên, chúng nhóm biểu thức hoặc đối số. Ngữ nghĩa của biểu thức vẫn phụ thuộc vào toán tử và hàm bên trong.

### 5.3. Ngoặc vuông: `[ ]`

Ngoặc vuông thường bao quanh danh sách hoặc truy cập phần tử:

~~~text
columns = ["order_id", "customer_id", "amount"]
first_column = columns[0]
~~~

DSL cần quy định danh sách có cho phép rỗng không, phần tử có cùng kiểu không, dấu phẩy cuối danh sách có hợp lệ không và chỉ mục bắt đầu từ 0 hay 1 nếu có truy cập theo vị trí.

### 5.4. Dấu nhọn góc: `< >`

Dấu `<` và `>` thường được dùng làm toán tử so sánh. Một số ngôn ngữ cũng dùng chúng cho kiểu generic hoặc tham số kiểu:

~~~text
filter amount < 100
list<Customer>
~~~

Việc dùng cùng ký hiệu cho so sánh và kiểu có thể tạo ra sự mơ hồ nếu ngữ pháp không đủ rõ. Ví dụ, parser phải phân biệt `a < b` là biểu thức so sánh hay `Map<String, Integer>` là kiểu tham số hóa. DSL nhỏ có thể tránh dùng dấu nhọn cho generic nếu không cần tính năng đó.

## 6. Dấu phân cách giữa các thành phần

### 6.1. Dấu phẩy

Dấu phẩy thường phân tách phần tử danh sách, tham số hoặc thuộc tính:

~~~text
group_by region, customer_id, month
call("report", "csv", true)
~~~

Ngữ pháp phải xác định dấu phẩy có bắt buộc hay không, có cho phép dấu phẩy cuối (trailing comma) không và có thể bỏ qua phần tử hay không.

Ví dụ danh sách có trailing comma:

~~~text
columns = [
    "order_id",
    "customer_id",
    "amount",
]
~~~

Cho phép dấu phẩy cuối có thể giúp thêm hoặc xóa phần tử thuận tiện trong code review. Tuy nhiên, lexer/parser và formatter phải cùng tuân theo một quy tắc.

### 6.2. Dấu chấm phẩy

Dấu chấm phẩy có thể kết thúc câu lệnh:

~~~text
let limit = 100;
let status = "PAID";
filter amount >= limit;
~~~

Một DSL có thể yêu cầu dấu chấm phẩy ở mọi câu lệnh, chỉ yêu cầu khi nhiều câu lệnh nằm trên một dòng, hoặc không dùng dấu chấm phẩy. Không nên để hành vi thay đổi tùy tiện giữa các loại câu lệnh.

### 6.3. Dấu hai chấm

Dấu hai chấm thường tách khóa và giá trị trong cấu hình:

~~~text
service:
  name: billing
  replicas: 3
~~~

Nó cũng có thể phân tách nhãn với nội dung hoặc mở một khối theo thụt lề. Nếu dùng dấu hai chấm cho nhiều mục đích, ngữ pháp phải cho phép xác định vai trò dựa trên vị trí và ngữ cảnh.

### 6.4. Dấu chấm

Dấu chấm có thể dùng để truy cập thuộc tính hoặc biểu diễn tên phân cấp:

~~~text
customer.address.city
module.submodule.operation
~~~

Cần xác định cách xử lý khi một tên chứa dấu chấm, cách phân biệt dấu chấm truy cập thuộc tính với dấu chấm trong số thập phân, và có cho phép chuỗi truy cập lồng nhau hay không.

## 7. Quy tắc khoảng trắng và xuống dòng

Khoảng trắng có thể chỉ phục vụ trình bày hoặc có thể mang ý nghĩa cú pháp. Đây là một quyết định quan trọng của thiết kế DSL.

### 7.1. Khoảng trắng không có ý nghĩa cấu trúc

Trong một ngôn ngữ bỏ qua khoảng trắng giữa token, các cách viết sau có thể tương đương:

~~~text
filter status=="PAID"
filter    status ==    "PAID"
filter
    status == "PAID"
~~~

Điều này giúp formatter có thể thay đổi cách xuống dòng và căn lề mà không thay đổi cấu trúc. Tuy nhiên, khoảng trắng vẫn có thể cần thiết để phân tách token. Ví dụ `filterstatus` có thể là một định danh duy nhất chứ không phải hai token `filter` và `status`.

### 7.2. Xuống dòng có ý nghĩa kết thúc câu lệnh

Một DSL có thể xem mỗi dòng là một câu lệnh:

~~~text
source "orders.csv"
filter status == "PAID"
output "paid.csv"
~~~

Nếu chọn quy tắc này, cần định nghĩa cách viết biểu thức nhiều dòng:

~~~text
filter
    amount > 100
    and status == "PAID"
~~~

Parser phải biết biểu thức vẫn tiếp tục qua dòng tiếp theo hay dòng mới đã kết thúc câu lệnh. Có thể dùng dấu mở ngoặc chưa được đóng, toán tử ở cuối dòng hoặc quy tắc continuation để nhận biết.

### 7.3. Thụt lề có ý nghĩa cấu trúc

Trong DSL layout-sensitive, thay đổi mức thụt lề có thể mở hoặc đóng một khối:

~~~text
pipeline daily:
    source orders.csv
    filter status == "PAID"
    output paid.csv
~~~

Parser có thể tạo các token ảo như `INDENT` và `DEDENT` khi mức thụt lề tăng hoặc giảm. Nhờ đó, parser xử lý cấu trúc khối tương tự như khi có dấu ngoặc tường minh.

Nếu dùng cách này, đặc tả cần nêu:

- Tab có được phép không, hay chỉ dùng dấu cách.
- Mức thụt lề phải là bội số bao nhiêu.
- Có cho phép dòng trống giữa các câu lệnh không.
- Chú thích có ảnh hưởng đến mức thụt lề không.
- Điều gì xảy ra khi mức thụt lề giảm về một cột không từng xuất hiện.

### 7.4. Không trộn quy tắc tùy tiện

Một DSL có thể bỏ qua khoảng trắng ở phần lớn biểu thức nhưng dùng thụt lề để xác định khối. Cách đó vẫn hợp lý nếu được mô tả rõ. Vấn đề xuất hiện khi cùng một vị trí có lúc phụ thuộc dấu ngoặc, lúc phụ thuộc dòng mới, lúc phụ thuộc thụt lề mà không có quy tắc ưu tiên.

Người dùng cần có thể dự đoán việc thêm một dòng trống hoặc thay đổi căn lề có làm thay đổi ý nghĩa chương trình hay không.

## 8. Khối lồng nhau

Khối lồng nhau xuất hiện khi một khối chứa một hoặc nhiều khối con. Đây là cách phổ biến để biểu diễn cấu hình phân cấp, điều kiện, vòng lặp và quy trình nhiều bước.

Ví dụ:

~~~text
workflow "monthly-close" {
    source "transactions.csv"

    if period == "MONTH_END" {
        validate {
            require field("account_id")
            require field("amount")
        }

        for each account in accounts {
            summarize account
        }
    }
}
~~~

Có ba cấp khối trong ví dụ: `workflow`, `if`, và `validate` hoặc `for each`. Khi phân tích, parser cần nhận biết khối nào đang mở và câu lệnh tiếp theo thuộc cấp nào.

### 8.1. Quy tắc lồng nhau

Ngữ pháp cần xác định:

- Loại khối nào có thể chứa loại khối nào.
- Có cho phép khối rỗng không.
- Có giới hạn độ sâu lồng nhau không.
- Một khối có thể chứa nhiều câu lệnh cùng loại không.
- Câu lệnh nào chỉ hợp lệ ở cấp cao nhất.
- Khối có bắt buộc kết thúc trước khi khai báo tiếp theo bắt đầu không.

Ví dụ, `output` có thể chỉ hợp lệ ở cấp pipeline, không hợp lệ bên trong khối `filter`. Nếu DSL không kiểm tra ràng buộc này, một cấu trúc có thể parse được nhưng không có ý nghĩa trong miền.

### 8.2. Giới hạn độ sâu

Lồng quá sâu làm mã khó đọc và có thể làm tăng độ phức tạp xử lý. Với DSL cho phép người dùng cung cấp tệp không tin cậy, nên cân nhắc giới hạn độ sâu parser chấp nhận để tránh tiêu thụ tài nguyên quá mức.

Giới hạn cần phản ánh nhu cầu thực tế. Không nên chọn một con số tùy tiện nếu miền có các cấu trúc phân cấp sâu hợp lệ.

## 9. Thiết kế ngữ pháp cho dấu phân cách và khối

Ngữ pháp xác định vị trí dấu mở, dấu đóng, dấu phân tách và nội dung được phép xuất hiện giữa chúng. Có thể dùng EBNF để diễn đạt một phần ngữ pháp:

~~~ebnf
program       = { declaration } ;
declaration   = pipeline | rule ;
pipeline      = "pipeline", string, block ;
rule          = "rule", string, block ;
block         = "{", { statement }, "}" ;
statement     = source
              | filter
              | group_by
              | aggregate
              | output ;
source        = "source", string, [ "format", identifier ], terminator ;
filter        = "filter", expression, terminator ;
group_by      = "group_by", identifier, { ",", identifier }, terminator ;
aggregate     = "aggregate", identifier, "=", expression, terminator ;
output        = "output", string, terminator ;
terminator    = ";" | newline ;
~~~

Ngữ pháp trên chỉ minh họa một số quyết định. Nếu DSL không yêu cầu dấu kết thúc câu lệnh, `terminator` có thể được bỏ khỏi quy tắc. Nếu DSL dùng thụt lề, `block` sẽ được định nghĩa dựa trên token `INDENT` và `DEDENT` thay vì `{` và `}`.

### 9.1. Danh sách và phần tử lồng nhau

Một ngữ pháp danh sách có thể được viết:

~~~ebnf
list          = "[", [ expression, { ",", expression } ], "]" ;
~~~

Quy tắc này cho phép danh sách rỗng hoặc một hay nhiều biểu thức. Nếu muốn cho phép dấu phẩy cuối, có thể điều chỉnh grammar để chấp nhận dấu phẩy tùy chọn trước dấu đóng. Mọi lựa chọn nên được kiểm thử bằng ví dụ.

### 9.2. Phân biệt dấu phân cách với toán tử

Một ký hiệu có thể có nhiều vai trò nếu ngữ cảnh cho phép. Dấu `<` có thể là toán tử so sánh hoặc một phần của cú pháp kiểu generic. Dấu `:` có thể tách khóa-giá trị hoặc biểu thị kiểu. Ngữ pháp cần tránh sự mơ hồ hoặc định nghĩa cách phân giải rõ ràng.

Một số chiến lược:

- Chọn ký hiệu khác nhau cho hai vai trò nếu có thể.
- Dùng từ khóa hoặc ngữ cảnh để phân biệt.
- Định nghĩa ưu tiên và tính kết hợp cho toán tử.
- Dùng dấu ngoặc để người viết thể hiện rõ ý định.
- Thiết kế grammar sao cho parser có thể phân biệt mà không phải đoán.

### 9.3. Ngữ pháp không thay thế kiểm tra ngữ nghĩa

Grammar có thể cho phép một khối chứa các câu lệnh `source`, `filter` và `output`, nhưng điều đó chưa xác định nguồn phải được khai báo trước filter hay một pipeline có thể có bao nhiêu output. Các ràng buộc này có thể được kiểm tra ở tầng ngữ nghĩa.

Tách cú pháp khỏi ngữ nghĩa giúp grammar tập trung mô tả hình dạng cấu trúc, còn semantic analyzer tập trung vào quy tắc của miền.

## 10. Xử lý dấu phân cách trong lexer và parser

### 10.1. Lexer nhận diện token dấu phân cách

Lexer thường nhận diện các ký hiệu như `{`, `}`, `(`, `)`, `[`, `]`, `,`, `:`, `;` thành các loại token riêng. Parser sử dụng loại token để kiểm tra cấu trúc.

Ví dụ:

~~~text
filter (amount >= 100)
~~~

Có thể tạo token:

~~~text
FILTER
LPAREN
IDENTIFIER("amount")
GREATER_EQUAL
NUMBER(100)
RPAREN
~~~

Việc phân loại token rõ ràng giúp parser không phải xử lý từng ký tự tùy tiện ở mọi quy tắc.

### 10.2. Theo dõi dấu mở và dấu đóng

Với dấu phân cách dạng cặp, parser có thể duy trì stack. Mỗi dấu mở được đẩy vào stack; khi gặp dấu đóng, parser so sánh với dấu mở trên đỉnh stack.

~~~text
Đọc token:
    gặp dấu mở -> push loại dấu và vị trí
    gặp dấu đóng:
        nếu stack rỗng -> báo dấu đóng không có dấu mở
        nếu loại dấu không khớp -> báo sai cặp dấu
        nếu khớp -> pop
Kết thúc đầu vào:
    nếu stack còn phần tử -> báo thiếu dấu đóng tương ứng
~~~

Đây là mô tả khái quát. Parser thực tế có thể xử lý dấu ngoặc trực tiếp trong các quy tắc grammar thay vì dùng một bước kiểm tra riêng. Dù dùng cách nào, công cụ vẫn cần giữ thông tin vị trí nguồn để chẩn đoán.

### 10.3. Chuỗi và chú thích

Lexer phải xử lý trạng thái chuỗi và chú thích. Ví dụ:

~~~text
template = "A brace } is just text"
# Dấu ngoặc } trong chú thích không đóng khối
pipeline "demo" {
    output template
}
~~~

Dấu `}` trong chuỗi và chú thích không được xem là dấu đóng khối. Tương tự, dấu ngoặc kép đã được escape bên trong chuỗi không kết thúc chuỗi.

Nếu DSL hỗ trợ chuỗi nhiều dòng, cần định nghĩa cách nhận diện dấu kết thúc và cách xử lý ký tự xuống dòng. Nếu hỗ trợ raw string hoặc template string, lexer cần phân biệt từng chế độ.

## 11. Thông báo lỗi và phục hồi cú pháp

Lỗi dấu phân cách và khối là nhóm lỗi phổ biến khi người dùng viết DSL. Thông báo lỗi cần chỉ ra vấn đề cụ thể thay vì chỉ báo “syntax error”.

### 11.1. Các dạng lỗi thường gặp

| Lỗi | Ví dụ | Thông báo có ích |
|---|---|---|
| Thiếu dấu đóng | `pipeline { source "a.csv"` | Thiếu `}` để đóng khối `pipeline` đã mở tại dòng 1 |
| Dấu đóng thừa | `filter status == "PAID" }` | Gặp `}` nhưng không có khối tương ứng đang mở |
| Sai cặp dấu | `call([1, 2)` | Cần `]` trước `)` để đóng danh sách |
| Thiếu dấu phân tách | `call(a b)` | Thiếu dấu phẩy giữa các đối số |
| Khối lồng sai | `if ready { output "a" } }` | Dấu `}` cuối không đóng khối nào |
| Thụt lề không hợp lệ | Mức thụt lề giảm về vị trí chưa từng mở | Mức thụt lề không khớp với cấu trúc khối |

### 11.2. Báo lỗi bằng vị trí nguồn

Chẩn đoán nên bao gồm:

- Tên tệp hoặc nguồn đầu vào.
- Số dòng và cột.
- Token hoặc dấu phân cách gây lỗi.
- Cấu trúc parser đang mong đợi.
- Vị trí dấu mở tương ứng nếu có thể.
- Gợi ý sửa ngắn gọn, không suy đoán quá mức.

Ví dụ:

~~~text
daily.pipe:8:1: error: expected '}' to close block 'pipeline'
Block opened at daily.pipe:1:24
~~~

### 11.3. Phục hồi để báo nhiều lỗi

Nếu parser dừng ngay ở lỗi đầu tiên, người dùng có thể phải sửa và chạy lại nhiều lần. Parser có thể cố gắng phục hồi bằng cách bỏ qua token đến điểm đồng bộ như dấu chấm phẩy, dấu đóng khối hoặc từ khóa bắt đầu câu lệnh.

Ví dụ, nếu một câu lệnh trong khối bị lỗi, parser có thể bỏ qua đến dấu `;` tiếp theo rồi tiếp tục phân tích câu lệnh kế tiếp. Tuy nhiên, phục hồi cần thận trọng: nếu bỏ qua sai ranh giới, các lỗi sau có thể chỉ là lỗi dây chuyền do cấu trúc đã mất đồng bộ.

Không nên báo quá nhiều lỗi suy diễn từ cùng một dấu ngoặc bị thiếu. Chẩn đoán nên ưu tiên nguyên nhân gốc và tránh làm người dùng khó xác định lỗi cần sửa đầu tiên.

## 12. Định dạng và quy ước trình bày khối

Formatter tự động có thể chuẩn hóa cách viết dấu phân cách, thụt lề và xuống dòng mà không thay đổi ý nghĩa DSL. Để formatter hoạt động nhất quán, ngôn ngữ cần có quy tắc trình bày rõ.

Ví dụ trước định dạng:

~~~text
pipeline "daily"{source "orders.csv";filter status=="PAID";group_by customer_id;output "paid.csv";}
~~~

Sau định dạng:

~~~text
pipeline "daily" {
    source "orders.csv";
    filter status == "PAID";
    group_by customer_id;
    output "paid.csv";
}
~~~

Một quy ước formatter có thể xác định:

- Dấu mở khối nằm cùng dòng với khai báo hay ở dòng tiếp theo.
- Dấu đóng khối thẳng hàng với từ khóa mở khối.
- Mỗi cấp lồng nhau tăng bao nhiêu dấu cách.
- Có đặt khoảng trắng quanh toán tử hay không.
- Có khoảng trắng sau dấu phẩy hay không.
- Danh sách dài có được xuống dòng từng phần tử không.
- Dấu chấm phẩy có được giữ lại hay tự thêm/bỏ không.
- Dòng trống được dùng để phân nhóm nội dung ra sao.

Formatter chỉ nên thay đổi cách trình bày. Nếu một thao tác format làm thay đổi cấu trúc hoặc ý nghĩa, cần xem lại thiết kế grammar hoặc logic formatter.

## 13. Những nguyên tắc thiết kế dấu phân cách và khối

Khi thiết kế cú pháp tổng thể, có thể áp dụng các nguyên tắc sau:

1. **Mỗi dấu có vai trò dễ giải thích.** Tránh dùng cùng một ký hiệu cho quá nhiều mục đích nếu gây mơ hồ.
2. **Cặp dấu phải cân bằng và nhất quán.** Dấu mở và đóng cần được xác định rõ, kể cả khi có lồng nhau.
3. **Khối thể hiện quan hệ miền.** Cách lồng khối nên phản ánh quan hệ bao chứa thực tế, không chỉ phục vụ hình thức.
4. **Không đồng nhất block với scope.** Nếu khối tạo phạm vi tên, hãy đặc tả rõ; nếu không, đừng để người dùng phải đoán.
5. **Quy tắc khoảng trắng phải dự đoán được.** Nêu rõ khoảng trắng, xuống dòng và thụt lề có ảnh hưởng đến cú pháp không.
6. **Có quy tắc kết thúc câu lệnh nhất quán.** Nếu dùng dấu chấm phẩy hoặc newline, hãy định nghĩa các trường hợp ngoại lệ.
7. **Hạn chế độ lồng không cần thiết.** Cấu trúc sâu làm giảm khả năng đọc và có thể tăng chi phí phân tích.
8. **Chú ý ký tự trong chuỗi và chú thích.** Lexer phải phân biệt nội dung văn bản với dấu cấu trúc.
9. **Thiết kế chẩn đoán ngay từ đầu.** Lưu vị trí dấu mở, dấu đóng và token để báo lỗi hữu ích.
10. **Kiểm chứng bằng ví dụ thật.** Thử các trường hợp hợp lệ, không hợp lệ, lồng nhau và nhiều dòng trước khi chốt cú pháp.

## 14. Những sai lầm thường gặp

### 14.1. Dùng dấu phân cách không nhất quán

Nếu danh sách lúc dùng dấu phẩy, lúc dùng dấu chấm phẩy mà không có lý do, người dùng phải ghi nhớ quá nhiều ngoại lệ. Hãy chọn một quy ước cho mỗi loại cấu trúc và áp dụng nhất quán.

### 14.2. Dùng một loại ngoặc cho nhiều cấu trúc khác nhau

Nếu `{}` vừa mở khối, vừa bao quanh literal, vừa biểu diễn tập hợp mà không có quy tắc phân biệt rõ, parser và người đọc dễ nhầm. Có thể dùng các dấu khác nhau hoặc định nghĩa ngữ cảnh chặt chẽ.

### 14.3. Không định nghĩa rõ ý nghĩa xuống dòng

Nếu newline đôi khi kết thúc câu lệnh, đôi khi chỉ là khoảng trắng, người dùng khó dự đoán cấu trúc. Cần quy định khi nào biểu thức được phép tiếp tục qua dòng.

### 14.4. Cho phép lồng khối tùy ý

Không phải mọi khối đều nên chứa mọi loại câu lệnh hoặc khối con. Grammar và semantic analyzer cần giới hạn cấu trúc theo mô hình miền.

### 14.5. Chỉ báo lỗi tại vị trí dấu đóng

Khi thiếu dấu đóng, vị trí lỗi thực tế có thể là cuối tệp, nhưng người dùng cần biết khối nào đã mở từ trước. Hãy lưu vị trí mở để chỉ ra nguồn gốc.

### 14.6. Coi định dạng là ngữ nghĩa

Thụt lề có thể chỉ phục vụ trình bày hoặc có thể mang ý nghĩa cấu trúc. Đặc tả phải nói rõ. Nếu DSL dùng dấu ngoặc tường minh và bỏ qua thụt lề, formatter không được tự thay đổi cấu trúc khi căn chỉnh.

## 15. Quy trình thiết kế và kiểm chứng

Một quy trình thực tế để thiết kế dấu phân cách và khối:

1. **Liệt kê cấu trúc miền.** Xác định những đối tượng, quy trình, điều kiện và danh sách cần được biểu đạt.
2. **Chọn loại khối cần có.** Ví dụ khối khai báo, khối điều kiện, khối lặp hoặc khối quy trình.
3. **Chọn chiến lược ranh giới.** Dùng ngoặc, từ khóa kết thúc hay thụt lề dựa trên người dùng và công cụ dự kiến.
4. **Định nghĩa dấu phân cách.** Nêu vai trò của từng dấu, cách ghép cặp và các ngữ cảnh hợp lệ.
5. **Định nghĩa khoảng trắng và newline.** Xác định cách phân tách câu lệnh và biểu thức nhiều dòng.
6. **Viết grammar.** Mô tả khối, danh sách, đối số, biểu thức và câu lệnh bằng EBNF hoặc định dạng tương đương.
7. **Xác định quy tắc ngữ nghĩa.** Làm rõ loại câu lệnh được phép trong từng khối, phạm vi tên và thứ tự thao tác.
8. **Tạo ví dụ hợp lệ và không hợp lệ.** Bao gồm khối rỗng, khối lồng nhau, dấu đóng thừa, dấu đóng thiếu và dấu trong chuỗi.
9. **Kiểm thử parser và thông báo lỗi.** Xác nhận cấu trúc AST, vị trí lỗi và khả năng phục hồi.
10. **Thử formatter và người dùng.** Kiểm tra mã sau định dạng có giữ nguyên ý nghĩa và người dùng có dễ đọc không.

Các bước có thể lặp lại khi xuất hiện tình huống mới. Nếu một dấu phân cách liên tục tạo ra mơ hồ hoặc một kiểu khối khó hiểu, hãy xem lại lựa chọn cú pháp thay vì chỉ thêm ngoại lệ vào parser.

## 16. Câu hỏi tự kiểm tra

1. Dấu phân cách và khối có vai trò gì trong cú pháp của DSL? Nêu một ví dụ có cả hai.
2. Phân biệt dấu phân cách cấu trúc với ký tự giống dấu phân cách nằm bên trong chuỗi hoặc chú thích.
3. So sánh cách xác định khối bằng ngoặc nhọn, từ khóa kết thúc và thụt lề.
4. Vì sao không nên mặc định mỗi khối cú pháp đều tạo một phạm vi tên mới?
5. Trình bày vai trò của ngoặc nhọn, ngoặc tròn và ngoặc vuông bằng ví dụ.
6. Khi DSL cho phép biểu thức nhiều dòng, cần định nghĩa những quy tắc nào về newline và khoảng trắng?
7. Parser có thể phát hiện cặp dấu ngoặc không khớp như thế nào? Vì sao cần lưu vị trí dấu mở?
8. Một khối có thể đúng cú pháp nhưng sai ngữ nghĩa ra sao? Hãy đưa ra ví dụ về câu lệnh đặt sai loại khối.
9. Hãy viết một đoạn DSL có ít nhất hai cấp khối lồng nhau, sau đó nêu các quy tắc về dấu phân cách và phạm vi áp dụng.
10. Đề xuất thông báo lỗi hữu ích cho trường hợp thiếu dấu đóng khối ở cuối tệp.
