# Lỗi trong quá trình thực thi

## 1. Lỗi thực thi trong ngữ nghĩa của DSL

Ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) mô tả các thao tác, quy tắc hoặc trạng thái thuộc một miền xác định. Sau khi văn bản DSL được phân tích cú pháp và kiểm tra các quy tắc có thể xác minh trước khi chạy, công cụ có thể bắt đầu thực thi chương trình. Trong giai đoạn này, hệ thống tương tác với dữ liệu thật, tài nguyên, dịch vụ bên ngoài và môi trường đang hoạt động. Những điều kiện chỉ xuất hiện tại thời điểm đó có thể khiến một thao tác không hoàn thành như dự kiến.

**Lỗi trong quá trình thực thi (runtime error)** là lỗi được phát hiện khi DSL đang được diễn giải, thực thi hoặc chuyển một thao tác đến hệ thống đích. Lỗi có thể phát sinh do dữ liệu thực tế, trạng thái môi trường, giới hạn tài nguyên, quyền truy cập, sự cố mạng hoặc một quy tắc miền không thể thỏa mãn tại thời điểm chạy.

Ví dụ, một pipeline có cú pháp hợp lệ:

~~~text
pipeline "daily-revenue" {
    source "orders.csv"
    filter status == "PAID"
    aggregate total = sum(amount)
    output "daily-revenue.csv"
}
~~~

Parser có thể chấp nhận cấu trúc này. Bộ kiểm tra ngữ nghĩa cũng có thể xác nhận các trường đã được khai báo trong schema dự kiến. Nhưng khi chạy, tệp orders.csv có thể không tồn tại, người chạy có thể không có quyền đọc tệp, hoặc một bản ghi thực tế có giá trị amount không thể chuyển thành số. Đây là những tình huống có thể chỉ được phát hiện khi thực thi.

Ngữ nghĩa của DSL không chỉ định nghĩa kết quả của trường hợp thành công. Nó còn cần xác định khi thao tác thất bại thì hệ thống phải làm gì: dừng toàn bộ chương trình, bỏ qua một bản ghi, thử lại, chuyển sang nhánh xử lý lỗi, hoàn tác tác dụng phụ hay trả về kết quả một phần.

## 2. Phân biệt lỗi cú pháp, lỗi ngữ nghĩa tĩnh và lỗi thực thi

Ba nhóm lỗi này xuất hiện ở các giai đoạn khác nhau và cần được chẩn đoán theo cách khác nhau.

| Nhóm lỗi | Thời điểm phát hiện | Ví dụ | Cách xử lý thường gặp |
|---|---|---|---|
| Lỗi cú pháp (syntax error) | Khi lexer hoặc parser đọc nguồn | Thiếu dấu đóng khối, viết sai cấu trúc câu lệnh | Sửa văn bản DSL |
| Lỗi ngữ nghĩa tĩnh (static semantic error) | Sau khi parse, trước khi chạy | Tham chiếu tên không tồn tại, kiểu đối số không phù hợp | Sửa khai báo, kiểu hoặc ràng buộc |
| Lỗi thực thi (runtime error) | Khi diễn giải hoặc thực hiện thao tác | Tệp không tồn tại, hết thời gian chờ, dịch vụ từ chối yêu cầu | Xử lý dữ liệu hoặc môi trường, thử lại khi phù hợp, hoặc dừng có kiểm soát |

Ví dụ:

~~~text
aggregate total = sum(amount)
~~~

- Nếu thiếu dấu ngoặc đóng của lời gọi hàm, parser báo lỗi cú pháp.
- Nếu schema đã biết và amount là trường kiểu chuỗi không được sum hỗ trợ, bộ kiểm tra tĩnh có thể báo lỗi ngữ nghĩa trước khi chạy.
- Nếu schema khai báo amount là số nhưng dữ liệu thực tế chứa chuỗi không hợp lệ, lỗi chuyển đổi có thể xuất hiện khi xử lý bản ghi.

Ranh giới giữa các nhóm phụ thuộc vào thông tin mà công cụ có sẵn. Nếu DSL có schema đầy đủ và dữ liệu được kiểm tra trước, nhiều lỗi dữ liệu có thể phát hiện sớm. Nếu dữ liệu chỉ được đọc từ nguồn động tại thời điểm chạy, cùng một vấn đề có thể trở thành lỗi thực thi.

Một lỗi runtime cũng không nhất thiết là lỗi lập trình của engine. Cần phân biệt **lỗi miền hoặc lỗi vận hành có thể dự kiến** (ví dụ dữ liệu không hợp lệ, quyền bị từ chối) với **lỗi nội bộ ngoài dự kiến** (ví dụ NullPointerException do bug trong interpreter). Người dùng DSL cần thông tin có thể hành động; nhóm phát triển engine cần dấu vết kỹ thuật để sửa lỗi nội bộ.

## 3. Các nhóm nguyên nhân gây lỗi thực thi

Không có một danh sách duy nhất áp dụng cho mọi DSL. Tuy nhiên, các nguyên nhân sau thường gặp trong ngôn ngữ mô tả pipeline, truy vấn, build, triển khai và workflow.

### 3.1. Lỗi dữ liệu đầu vào

Dữ liệu thực tế có thể khác với schema hoặc giả định được dùng khi thiết kế DSL:

- Tệp rỗng hoặc thiếu bản ghi bắt buộc.
- Giá trị không thể chuyển đổi sang kiểu mong đợi.
- Trường có giá trị null trong khi phép toán không hỗ trợ null.
- Bản ghi bị thiếu trường hoặc chứa giá trị ngoài miền cho phép.
- Dữ liệu bị cắt cụt, sai encoding hoặc sai định dạng.
- Dữ liệu trùng lặp làm vi phạm ràng buộc duy nhất.

Ví dụ:

~~~text
amount = "one hundred"
total = sum(amount)
~~~

Nếu dữ liệu chỉ được kiểm tra khi đọc, engine có thể phát hiện rằng chuỗi one hundred không thể chuyển thành số. DSL cần xác định lỗi được gắn với bản ghi, trường dữ liệu hay toàn bộ phép tổng hợp.

### 3.2. Lỗi tài nguyên và hệ thống tệp

Thao tác có thể thất bại vì tài nguyên không sẵn có:

- Tệp nguồn hoặc thư mục đích không tồn tại.
- Ổ đĩa hết dung lượng.
- Tệp bị khóa hoặc đang được tiến trình khác sử dụng.
- Hệ thống tệp chỉ đọc.
- Bộ nhớ hoặc số lượng file descriptor vượt giới hạn.
- Tên đường dẫn không hợp lệ trên hệ điều hành hiện tại.

Một DSL khai báo output hợp lệ không thể bảo đảm rằng hệ thống sẽ ghi được kết quả. Khả năng ghi còn phụ thuộc trạng thái thiết bị lưu trữ và quyền tại thời điểm chạy.

### 3.3. Lỗi quyền truy cập

Một thao tác có thể đúng về cú pháp và ngữ nghĩa nhưng người thực thi không có quyền:

- Đọc nguồn dữ liệu.
- Ghi tệp kết quả.
- Truy cập bảng hoặc schema trong cơ sở dữ liệu.
- Gọi một dịch vụ.
- Tạo, cập nhật hoặc xóa tài nguyên hạ tầng.
- Đọc secret hoặc thông tin cấu hình được bảo vệ.

Lỗi quyền nên được báo rõ là thao tác nào bị từ chối và tài nguyên nào liên quan. Không nên đưa thông tin xác thực hoặc dữ liệu bí mật vào thông báo lỗi.

### 3.4. Lỗi mạng và dịch vụ bên ngoài

DSL có thể gọi API, truy vấn cơ sở dữ liệu hoặc gửi công việc đến một engine khác. Các nguyên nhân thường gặp gồm:

- Không phân giải được tên máy chủ.
- Không thiết lập được kết nối.
- Kết nối bị đóng giữa chừng.
- Dịch vụ trả về mã lỗi.
- Dịch vụ quá tải hoặc giới hạn tần suất.
- Phản hồi không đúng định dạng hoặc không đáp ứng schema.
- Dịch vụ hoàn thành thao tác nhưng phản hồi bị mất trên đường truyền.

Trường hợp cuối đặc biệt quan trọng: timeout không chứng minh thao tác ở hệ thống đích chưa xảy ra. Nếu engine gửi yêu cầu tạo tài nguyên rồi mất kết nối trước khi nhận phản hồi, thử lại mù quáng có thể tạo tài nguyên trùng lặp.

### 3.5. Lỗi quy tắc miền tại thời điểm chạy

Một số quy tắc chỉ có thể kiểm tra khi biết trạng thái hiện tại:

- Số dư không đủ để thực hiện giao dịch.
- Đơn hàng đã bị hủy trước khi bước xử lý bắt đầu.
- Tài nguyên đã được một tiến trình khác thay đổi.
- Một trạng thái không cho phép chuyển sang trạng thái tiếp theo.
- Hạn mức đã bị sử dụng hết.
- Điều kiện nghiệp vụ thay đổi giữa lúc lập kế hoạch và lúc thực thi.

Đây có thể là kết quả thất bại được dự kiến trong miền, không nhất thiết là bug. DSL cần phân biệt từ chối nghiệp vụ với sự cố hạ tầng để người dùng chọn cách xử lý phù hợp.

### 3.6. Lỗi tài nguyên thực thi

Ngay cả khi đầu vào hợp lệ, tác vụ có thể không hoàn thành do:

- Hết bộ nhớ.
- Hết thời gian thực thi.
- Bị hủy bởi người dùng hoặc hệ thống điều phối.
- Quá nhiều tác vụ đồng thời.
- Vượt giới hạn số bản ghi, kích thước dữ liệu hoặc độ sâu đệ quy.
- Deadlock hoặc tranh chấp khóa.

Các giới hạn này nên được biểu diễn trong cấu hình runtime hoặc chính sách của DSL khi chúng là một phần của hợp đồng thực thi.

### 3.7. Lỗi nội bộ của engine

Lỗi nội bộ là những tình huống công cụ không dự kiến hoặc không xử lý đúng, chẳng hạn:

- Bug trong interpreter hoặc code generator.
- Trạng thái AST/IR không hợp lệ lọt qua bước kiểm tra.
- Lỗi chuyển đổi kiểu do triển khai sai.
- Vi phạm bất biến trong runtime.
- Thư viện phụ thuộc phát sinh exception không được ánh xạ.

Engine nên ghi stack trace và thông tin chẩn đoán dành cho người phát triển ở log phù hợp, đồng thời hiển thị cho người dùng mã lỗi ổn định và thông báo không tiết lộ chi tiết nhạy cảm.

## 4. Mô hình lỗi và chẩn đoán

Một thông báo lỗi hữu ích cần cung cấp đủ thông tin để người dùng hiểu chuyện gì đã xảy ra và quyết định bước tiếp theo. Chỉ hiển thị tên exception hoặc dòng chữ Failed thường không đủ.

### 4.1. Các trường thông tin của lỗi

Một mô hình chẩn đoán có thể gồm:

| Trường | Mục đích | Ví dụ |
|---|---|---|
| Error code | Mã ổn định để tra cứu và xử lý tự động | DSL-IO-004 |
| Category | Nhóm nguyên nhân | DATA, PERMISSION, NETWORK, RESOURCE |
| Message | Mô tả ngắn cho người dùng | Không thể đọc nguồn dữ liệu |
| Source location | Vị trí câu lệnh DSL liên quan | daily.pipe, dòng 2, cột 5 |
| Operation | Thao tác đang thực hiện | Đọc orders.csv |
| Resource | Tài nguyên liên quan | /data/orders.csv |
| Retryability | Có thể thử lại hay không | TRANSIENT, NON_RETRYABLE, UNKNOWN |
| Execution ID | Mã lần chạy để truy vết | run-2026-11-15-001 |
| Cause | Nguyên nhân kỹ thuật hoặc lỗi gốc | Permission denied |
| Context | Bối cảnh an toàn để hỗ trợ xử lý | Bước source, partition 3 |

Không phải mọi lỗi đều có đầy đủ các trường. Ví dụ, lỗi quy tắc miền có thể không có resource path; lỗi timeout có thể không biết trạng thái cuối cùng của thao tác bên ngoài.

### 4.2. Mã lỗi ổn định

Mã lỗi giúp tài liệu, log, dashboard và chương trình gọi DSL nhận diện lỗi mà không phải phân tích chuỗi thông báo. Nội dung message có thể được cải thiện hoặc dịch sang ngôn ngữ khác, trong khi error code nên giữ ổn định trong phạm vi tương thích đã công bố.

Ví dụ nhóm mã:

| Tiền tố | Nhóm lỗi |
|---|---|
| DSL-SYNTAX | Lỗi phân tích cú pháp |
| DSL-STATIC | Lỗi kiểm tra ngữ nghĩa tĩnh |
| DSL-DATA | Dữ liệu không hợp lệ khi chạy |
| DSL-IO | Đọc hoặc ghi tài nguyên |
| DSL-AUTH | Xác thực hoặc quyền truy cập |
| DSL-NET | Kết nối hoặc dịch vụ bên ngoài |
| DSL-RESOURCE | Giới hạn tài nguyên, timeout hoặc hủy |
| DSL-DOMAIN | Quy tắc nghiệp vụ không thỏa mãn |
| DSL-INTERNAL | Lỗi nội bộ của engine |

Đây là quy ước minh họa. Dự án nên định nghĩa registry mã lỗi và tài liệu cho từng mã.

### 4.3. Liên kết lỗi với nguồn DSL

Lỗi runtime nên được ánh xạ về câu lệnh, biểu thức hoặc khai báo DSL đã tạo ra thao tác. Điều này cần thông tin source span hoặc source map từ các giai đoạn parser và sinh mã.

Ví dụ:

~~~text
daily.pipe:2:5: DSL-IO-004
Không thể đọc nguồn "orders.csv".
Nguyên nhân: Không tìm thấy tệp tại vị trí đã cấu hình.
Execution: run-2026-11-15-001
~~~

Thông báo chỉ ra câu lệnh nguồn, nguyên nhân có thể xử lý và mã lần chạy để tra cứu log. Nếu DSL sinh SQL hoặc mã Java, công cụ nên ánh xạ lỗi từ backend trở lại đoạn DSL tương ứng.

### 4.4. Lỗi gốc và chuỗi nguyên nhân

Một lỗi có thể được bọc qua nhiều tầng:

~~~text
PipelineExecutionError
  caused by DataReadError
    caused by FileSystemException
~~~

Lớp ngoài cung cấp ngữ cảnh miền; lớp trong giữ nguyên nguyên nhân kỹ thuật. Việc bọc lỗi nên bảo toàn cause và stack trace cho log nội bộ. Không nên thay thế mọi nguyên nhân bằng một exception chung khiến việc điều tra không thể truy vết.

## 5. Lỗi miền và lỗi hạ tầng

Phân biệt hai nhóm này giúp quyết định cách xử lý:

- **Lỗi miền (domain failure):** một điều kiện của nghiệp vụ hoặc mô hình miền không được thỏa mãn. Ví dụ đơn hàng đã bị hủy nên không thể thanh toán.
- **Lỗi hạ tầng (infrastructure failure):** thao tác không thể hoàn thành do hệ thống hỗ trợ. Ví dụ cơ sở dữ liệu không kết nối được hoặc ổ đĩa đầy.

Một lỗi miền thường cần thay đổi dữ liệu đầu vào, trạng thái hoặc quyết định nghiệp vụ. Một lỗi hạ tầng có thể tạm thời và đôi khi có thể thử lại.

Ví dụ:

~~~text
workflow "approve-order" {
    load order "ORD-1042"
    require order.status == "PENDING"
    approve order
}
~~~

Nếu trạng thái đơn là CANCELLED, điều kiện require không thỏa mãn. Đây là lỗi miền hoặc kết quả từ chối nghiệp vụ. Nếu dịch vụ đơn hàng không phản hồi, đó là lỗi hạ tầng. Không nên báo cả hai bằng một message chung “Approval failed” nếu người dùng cần biết cách xử lý.

Một số hệ thống chọn biểu diễn lỗi miền như kết quả bình thường của một nhánh điều khiển, chẳng hạn Rejected hoặc NotEligible, thay vì exception. Lựa chọn này phụ thuộc vào việc kết quả đó có phải một khả năng thường gặp trong luồng nghiệp vụ hay là tình huống bất thường cần làm gián đoạn tác vụ.

## 6. Cách lỗi lan truyền qua các bước

Một DSL có thể thực hiện một câu lệnh đơn, một pipeline tuần tự hoặc một đồ thị workflow. Khi một bước thất bại, engine cần xác định phạm vi ảnh hưởng.

### 6.1. Dừng ngay khi có lỗi (fail-fast)

Với fail-fast, lỗi không được xử lý tại bước hiện tại sẽ làm dừng đơn vị thực thi đang chứa bước đó.

~~~text
pipeline "report" {
    source "orders.csv"
    filter status == "PAID"
    aggregate total = sum(amount)
    output "report.csv"
}
~~~

Nếu bước source thất bại, các bước filter, aggregate và output không chạy. Cách này dễ hiểu và phù hợp khi kết quả chỉ có ý nghĩa nếu toàn bộ đầu vào được xử lý thành công.

### 6.2. Tiếp tục khi lỗi được cô lập

Một số tác vụ xử lý từng bản ghi có thể bỏ qua bản ghi lỗi và tiếp tục:

~~~text
for each row in source("orders.csv") {
    on_error skip_record {
        transform row
    }
}
~~~

Đây là cú pháp giả định. Nếu DSL hỗ trợ bỏ qua bản ghi, nó cần định nghĩa rõ lỗi nào được phép bỏ qua, số lượng lỗi tối đa, cách ghi lại bản ghi lỗi và cách xác định kết quả cuối cùng có phải partial success hay không.

Không nên bỏ qua mọi exception. Lỗi mất kết nối nguồn, hết dung lượng hoặc vi phạm bất biến có thể khiến tiếp tục xử lý không còn an toàn.

### 6.3. Phạm vi lỗi

Lỗi có thể được xử lý ở nhiều cấp:

- **Biểu thức:** một phép chuyển đổi hoặc hàm thất bại.
- **Bản ghi:** một phần tử dữ liệu không xử lý được.
- **Bước:** một câu lệnh trong pipeline không hoàn thành.
- **Khối:** một nhóm thao tác cần được xem như đơn vị.
- **Workflow:** toàn bộ quy trình bị dừng hoặc chuyển trạng thái lỗi.
- **Lần chạy:** execution kết thúc với trạng thái thất bại, bị hủy hoặc hoàn thành một phần.

Phạm vi xử lý nên được quy định rõ. Ví dụ, bắt lỗi tại một biểu thức không có nghĩa là có thể bỏ qua lỗi của cả workflow.

### 6.4. Phụ thuộc giữa các bước

Trong workflow dạng đồ thị, lỗi của một bước có thể làm các bước phụ thuộc không thể chạy:

~~~text
       Read source
        /      \
       v        v
   Validate   Enrich
       \        /
        v      v
       Combine
          |
          v
        Output
~~~

Nếu Read source thất bại, các bước Validate và Enrich không có đầu vào. Engine cần đánh dấu các bước đó là skipped hoặc blocked, đồng thời phân biệt chúng với bước thực sự chạy và thất bại.

## 7. Các chiến lược xử lý lỗi trong DSL

DSL có thể cung cấp cấu trúc để người viết chỉ định cách xử lý một số lỗi dự kiến. Những cấu trúc này phải có ngữ nghĩa rõ ràng và không nên biến mọi thao tác thành một khối try/catch phức tạp.

### 7.1. Truyền lỗi lên cấp gọi (propagation)

Đây là cách đơn giản: thao tác phát sinh lỗi, nếu không có handler phù hợp thì lỗi truyền lên khối hoặc workflow gọi nó. Runtime giữ nguyên nguyên nhân và gắn thêm ngữ cảnh.

~~~text
pipeline "daily" {
    source "orders.csv"
    transform records
    output "daily.csv"
}
~~~

Nếu không khai báo xử lý lỗi riêng, pipeline có thể dừng khi một bước thất bại. Đây thường là mặc định dễ dự đoán cho các thao tác có phụ thuộc tuần tự.

### 7.2. Bắt lỗi và xử lý thay thế

Một DSL có thể cung cấp cấu trúc tương tự try/catch:

~~~text
try {
    read source "orders.csv"
} catch DATA_SOURCE_NOT_FOUND as error {
    use fallback_source "archive/orders.csv"
}
~~~

Cú pháp trên chỉ minh họa. Ngữ nghĩa cần xác định:

- Handler bắt theo mã lỗi, nhóm lỗi hay kiểu lỗi?
- Handler có bắt cả lỗi nội bộ không?
- Biến error chứa trường thông tin nào?
- Nếu handler cũng thất bại thì lỗi nào được truyền lên?
- Có cho phép handler tiếp tục từ bước lỗi hay phải bắt đầu lại một đơn vị?

Nên ưu tiên bắt các nhóm lỗi cụ thể. Bắt mọi lỗi rồi tiếp tục có thể che giấu bug hoặc làm hệ thống tạo ra kết quả sai.

### 7.3. Nhánh thành công và thất bại

Một số DSL biểu diễn kết quả bằng hai nhánh:

~~~text
result = execute_payment(order)

match result {
    success payment {
        record payment
    }
    failure reason {
        notify_operator(reason)
    }
}
~~~

Mô hình này phù hợp khi thất bại là một kết quả nghiệp vụ có thể dự kiến và cần được xử lý tường minh. Các kiểu kết quả có thể được kiểm tra tĩnh để bảo đảm người dùng xử lý đủ các trường hợp quan trọng.

### 7.4. Giá trị mặc định hoặc fallback

Một phép đọc cấu hình có thể cho phép giá trị mặc định:

~~~text
timeout = config("service.timeout") default 30s
~~~

Fallback phù hợp khi giá trị thay thế có ý nghĩa rõ và an toàn. Không nên dùng giá trị mặc định để che giấu lỗi nghiêm trọng, ví dụ thay dữ liệu tài chính bị lỗi bằng số 0 mà không ghi nhận.

### 7.5. Bỏ qua hoặc cách ly phần tử lỗi

Trong xử lý batch, DSL có thể đưa bản ghi lỗi vào vùng cách ly:

~~~text
process source "orders.csv" {
    on_invalid_record {
        write rejected_record to "rejected.csv"
    }
}
~~~

Kết quả cần ghi nhận số bản ghi thành công, số bản ghi bị từ chối và nguyên nhân. Nếu có dữ liệu bị loại, trạng thái cuối không nên được báo là hoàn toàn thành công mà không có thông tin bổ sung.

## 8. Thử lại (retry) và lỗi tạm thời

Retry là việc thực hiện lại một thao tác sau khi nó thất bại. Retry có ích với một số lỗi tạm thời như timeout, mất kết nối ngắn hạn hoặc dịch vụ trả về trạng thái quá tải. Retry không phải giải pháp chung cho mọi lỗi.

### 8.1. Phân loại khả năng thử lại

| Loại lỗi | Có nên retry? | Lý do |
|---|---|---|
| DNS hoặc kết nối tạm thời | Có thể | Sự cố có thể tự hết |
| HTTP 429 hoặc 503 | Có thể, theo hướng dẫn dịch vụ | Cần tôn trọng Retry-After và giới hạn tần suất |
| Timeout không rõ trạng thái | Chỉ khi có cơ chế an toàn | Thao tác có thể đã hoàn thành ở hệ thống đích |
| Sai dữ liệu đầu vào | Thường không | Chạy lại cùng dữ liệu không sửa được nguyên nhân |
| Quyền bị từ chối | Thường không | Cần thay đổi quyền hoặc cấu hình |
| Thiếu tài nguyên kéo dài | Không nên retry liên tục | Có thể làm hệ thống quá tải hơn |
| Lỗi nội bộ không xác định | Không tự động retry mặc định | Có thể lặp lại bug hoặc tác dụng phụ |

### 8.2. Backoff và giới hạn thử lại

Nếu thử lại ngay liên tục, nhiều tiến trình có thể cùng gây tải lớn lên một dịch vụ đang gặp sự cố. Exponential backoff tăng khoảng chờ giữa các lần thử:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt)
~~~

Có thể thêm jitter (độ lệch ngẫu nhiên) để các tiến trình không đồng loạt thử lại cùng thời điểm. DSL hoặc runtime cần giới hạn số lần thử, tổng thời gian chờ và thời gian thực thi tối đa.

Ví dụ cú pháp giả định:

~~~text
retry 3 times {
    call service "inventory"
}
~~~

Ngữ nghĩa cần nói rõ con số 3 là tổng số lần gọi hay số lần thử lại sau lần đầu, lỗi nào được retry, và khi nào dừng.

### 8.3. Idempotency

Một thao tác là idempotent nếu thực hiện nhiều lần với cùng đầu vào và điều kiện tương ứng tạo ra cùng trạng thái cuối như thực hiện một lần. Đọc dữ liệu thường có tính chất gần như vậy; tạo thanh toán hoặc gửi email thường không tự động idempotent.

Nếu retry một yêu cầu tạo giao dịch sau timeout, có thể giao dịch đầu đã thành công nhưng phản hồi bị mất. Gửi lại yêu cầu có thể tạo giao dịch thứ hai. Để retry an toàn, hệ thống đích có thể hỗ trợ idempotency key hoặc cơ chế tra cứu trạng thái trước khi gửi lại.

Không nên cho phép retry tự động đối với thao tác có tác dụng phụ không idempotent nếu không có cơ chế bảo vệ hoặc quy tắc bù trừ phù hợp.

## 9. Timeout, hủy và giới hạn tài nguyên

Một thao tác có thể không thất bại ngay mà kéo dài quá lâu. Timeout giới hạn thời gian chờ; cancellation cho phép yêu cầu dừng công việc đang chạy.

### 9.1. Timeout

~~~text
call service "shipping" with timeout 5s
~~~

Khi hết thời gian, runtime cần xác định:

- Hủy yêu cầu ở phía client có khả thi không?
- Hệ thống đích có thể vẫn tiếp tục xử lý không?
- Kết quả cuối cùng có thể được truy vấn lại không?
- Tài nguyên hoặc khóa nào cần được giải phóng?
- Lỗi được xem là timeout hay trạng thái không xác định?

Timeout phía client không đồng nghĩa thao tác ở phía server đã bị hủy. Với thao tác có tác dụng phụ, cần có cách xác nhận trạng thái hoặc idempotency.

### 9.2. Hủy

Một lần chạy có thể bị hủy bởi người dùng, scheduler hoặc chính sách hệ thống. Engine nên truyền tín hiệu hủy đến các bước có hỗ trợ, dừng khởi tạo công việc mới và giải phóng tài nguyên trong phạm vi an toàn.

Trạng thái CANCELLED nên được phân biệt với FAILED. Hủy có thể là hành động chủ động, không phải sự cố.

### 9.3. Giới hạn tài nguyên

DSL hoặc runtime có thể đặt giới hạn:

~~~text
execution {
    timeout 10m
    memory_limit 2GB
    max_parallelism 4
}
~~~

Đây là ví dụ cú pháp. Khi vượt giới hạn, engine cần báo loại tài nguyên, giới hạn áp dụng và bước đang tiêu thụ. Không nên tự động tăng giới hạn vô hạn hoặc tiếp tục retry một tác vụ đã bị chặn vì vượt quota.

## 10. Tính nhất quán, giao dịch và tác dụng phụ

Xử lý lỗi trở nên phức tạp khi DSL có thao tác thay đổi trạng thái bên ngoài, như ghi cơ sở dữ liệu, tạo tài nguyên, gửi thông báo hoặc cập nhật hệ thống khác.

### 10.1. Giao dịch nguyên tử

Trong một giao dịch nguyên tử, các thao tác thuộc giao dịch được cam kết cùng nhau hoặc không có thay đổi nào được giữ lại, theo bảo đảm của hệ thống giao dịch.

~~~text
transaction {
    debit account "A" amount 50
    credit account "B" amount 50
}
~~~

Nếu debit thành công nhưng credit thất bại, giao dịch có thể rollback để tránh mất cân bằng. Tuy nhiên, rollback chỉ khả thi khi backend hỗ trợ giao dịch và mọi thao tác nằm trong cùng phạm vi giao dịch được quản lý.

Không nên giả định một khối DSL có từ khóa transaction sẽ tự tạo được tính nguyên tử nếu các thao tác đi qua nhiều dịch vụ độc lập.

### 10.2. Bù trừ (compensation)

Với workflow phân tán, không phải thao tác nào cũng có thể rollback. Khi đó, hệ thống có thể dùng hành động bù trừ:

~~~text
workflow "book-trip" {
    reserve_flight
    reserve_hotel
    on_failure {
        cancel_flight_reservation
    }
}
~~~

Ví dụ này giản lược: nếu đặt khách sạn thất bại sau khi đặt vé máy bay, hệ thống gọi thao tác hủy đặt vé để bù lại. Hành động bù trừ không phải lúc nào cũng khôi phục chính xác trạng thái trước đó; nó là một thao tác nghiệp vụ mới và cũng có thể thất bại.

### 10.3. Kết quả một phần

Một pipeline có thể hoàn thành một số bước rồi thất bại ở bước cuối. Engine cần lưu trạng thái từng bước và cho biết tác dụng phụ nào đã xảy ra.

Ví dụ, ba tệp kết quả đã ghi thành công nhưng tệp thứ tư không ghi được vì hết dung lượng. Trạng thái lần chạy có thể là PARTIAL_FAILURE, kèm danh sách đầu ra đã tạo và bước thất bại.

Nếu không ghi lại trạng thái từng bước, người vận hành khó biết có nên chạy lại toàn bộ pipeline hay chỉ tiếp tục từ bước lỗi.

### 10.4. Checkpoint và resume

Checkpoint lưu trạng thái đủ để tiếp tục một công việc từ điểm đã hoàn thành. Khi resume, engine cần xác định:

- Bước nào đã hoàn thành và kết quả còn hợp lệ không?
- Đầu vào có thay đổi từ lần chạy trước không?
- Có tác dụng phụ nào cần tránh lặp lại không?
- Phiên bản DSL, runtime và cấu hình có giống lần chạy trước không?
- Có thể khôi phục trạng thái sau khi engine hoặc máy chủ khởi động lại không?

Resume cần được thiết kế cùng với tính idempotent và tính nhất quán. Chỉ lưu số thứ tự bước là chưa đủ nếu các bước có tác dụng phụ hoặc phụ thuộc dữ liệu thay đổi.

## 11. Lỗi trong xử lý dữ liệu theo bản ghi

DSL xử lý batch thường phải lựa chọn giữa dừng toàn bộ, bỏ qua bản ghi hoặc cách ly bản ghi lỗi.

Giả sử nguồn có các bản ghi:

| order_id | amount | status |
|---|---:|---|
| O-01 | 120.00 | PAID |
| O-02 | abc | PAID |
| O-03 | 75.00 | PENDING |
| O-04 | 50.00 | PAID |

Nếu phép tổng hợp yêu cầu amount là số, bản ghi O-02 không hợp lệ. Các chính sách có thể gồm:

| Chính sách | Hành vi | Hệ quả |
|---|---|---|
| Fail batch | Dừng toàn bộ khi gặp O-02 | Bảo đảm không phát hành kết quả thiếu nhưng một bản ghi lỗi chặn cả batch |
| Skip record | Bỏ O-02 và tiếp tục | Có kết quả một phần; cần thống kê số bản ghi bị bỏ |
| Quarantine | Chuyển O-02 sang tệp hoặc hàng đợi lỗi | Có thể sửa và xử lý lại riêng |
| Coerce | Thử chuyển giá trị theo quy tắc được định nghĩa | Chỉ an toàn nếu chuyển đổi có ý nghĩa miền |
| Default | Dùng giá trị thay thế | Có nguy cơ làm sai số liệu nếu mặc định không có căn cứ |

Một DSL có thể cho phép khai báo chính sách:

~~~text
read "orders.csv" {
    on_invalid_record quarantine to "rejected-orders.csv"
    max_rejected 10
}
~~~

Nếu số bản ghi lỗi vượt max_rejected, engine có thể dừng batch. Cần định nghĩa cách đếm, thời điểm kiểm tra và liệu các bản ghi đã xử lý trước đó có được ghi ra output hay không.

## 12. Trạng thái thực thi

Không nên biểu diễn toàn bộ kết quả bằng một cờ Boolean success/failure. Một workflow có thể đang chạy, chờ, bị hủy, hoàn thành một phần hoặc thất bại ở một bước.

Một mô hình trạng thái minh họa:

~~~text
PENDING
   |
   v
RUNNING ---------> CANCELLING
   |                    |
   |                    v
   |                 CANCELLED
   |
   +----> SUCCEEDED
   |
   +----> FAILED
   |
   +----> PARTIAL_FAILURE
~~~

Ý nghĩa trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| PENDING | Đã được tạo nhưng chưa bắt đầu |
| RUNNING | Đang thực thi |
| SUCCEEDED | Hoàn thành theo chính sách đã định nghĩa |
| FAILED | Thất bại, không đạt điều kiện hoàn thành |
| PARTIAL_FAILURE | Có phần công việc hoàn thành nhưng một phần thất bại |
| CANCELLING | Đang xử lý yêu cầu hủy |
| CANCELLED | Đã dừng theo yêu cầu hủy |

Một hệ thống có thể có thêm RETRYING, WAITING hoặc BLOCKED. Cần định nghĩa chuyển trạng thái hợp lệ và ghi lại lý do mỗi lần chuyển.

Nếu chính sách cho phép bỏ qua một số bản ghi lỗi, trạng thái cuối có thể vẫn là SUCCEEDED_WITH_WARNINGS hoặc PARTIAL_SUCCESS. Tên trạng thái không quan trọng bằng việc ý nghĩa được công bố và người dùng không bị hiểu nhầm rằng toàn bộ dữ liệu đã được xử lý.

## 13. Log, trace và quan sát lỗi

Một thông báo lỗi tại giao diện không thay thế được khả năng quan sát của hệ thống. Với DSL chạy trong môi trường tự động, cần ghi log và trace để tìm nguyên nhân sau khi lần chạy kết thúc.

### 13.1. Log theo sự kiện

Log nên ghi các sự kiện có cấu trúc:

~~~text
execution.started
step.started
step.retry_scheduled
step.failed
execution.partial_failure
~~~

Mỗi sự kiện có thể chứa execution ID, step ID, thời điểm, error code, thời lượng, nguồn DSL và thông tin tài nguyên phù hợp. Dùng log có cấu trúc giúp tìm kiếm và tổng hợp dễ hơn so với chỉ ghi chuỗi văn bản tự do.

### 13.2. Trace theo bước

Trace liên kết các bước trong một lần chạy, đặc biệt khi workflow phân tán qua nhiều dịch vụ. Một trace có thể cho biết bước nào chờ lâu, bước nào retry, lỗi bắt đầu ở đâu và thời gian được tiêu thụ tại thành phần nào.

### 13.3. Metrics

Một số chỉ số có ích:

- Số lần chạy thành công, thất bại, bị hủy và hoàn thành một phần.
- Tỷ lệ lỗi theo mã lỗi hoặc loại bước.
- Số lần retry trung bình.
- Thời gian thực thi theo bước và toàn workflow.
- Số bản ghi bị từ chối hoặc cách ly.
- Số lần timeout hoặc vượt giới hạn tài nguyên.

Metrics giúp nhận biết xu hướng. Chúng không thay thế log chi tiết của một execution cụ thể.

### 13.4. Bảo vệ dữ liệu nhạy cảm

Không nên ghi mật khẩu, token, secret hoặc toàn bộ bản ghi nhạy cảm vào thông báo lỗi. Log chỉ nên chứa dữ liệu tối thiểu cần thiết để điều tra. Nếu cần tham chiếu bản ghi, có thể dùng ID hoặc mã định danh đã được kiểm soát quyền truy cập.

## 14. Thiết kế API lỗi trong runtime

Runtime có thể dùng exception, kiểu kết quả hoặc kết hợp cả hai để biểu diễn thất bại.

### 14.1. Exception cho tình huống bất thường

Exception phù hợp khi thao tác không thể tiếp tục theo luồng thông thường và lỗi cần truyền lên tầng gọi. Ví dụ:

~~~java
try {
    executionEngine.run(program);
} catch (DslExecutionException error) {
    diagnosticReporter.report(error.diagnostic());
}
~~~

Exception của DSL nên mang mã lỗi, vị trí nguồn, execution context và cause. Không nên chỉ mang một message không cấu trúc.

### 14.2. Kiểu kết quả cho thất bại dự kiến

Nếu thất bại là một kết quả nghiệp vụ thường gặp, có thể dùng kiểu kết quả tường minh:

~~~java
sealed interface PaymentResult {
    record Success(String paymentId) implements PaymentResult {}
    record Rejected(String reason) implements PaymentResult {}
}
~~~

Người gọi phải xử lý các trường hợp theo kiểu dữ liệu. Cách này phù hợp với các kết quả như từ chối, không đủ điều kiện hoặc không tìm thấy, nếu đó là kết quả bình thường của miền.

### 14.3. Không dùng exception cho mọi nhánh điều khiển

Nếu một workflow thường xuyên nhận kết quả NotFound hoặc NotEligible, việc ném và bắt exception cho mọi trường hợp có thể làm luồng xử lý khó đọc và tốn chi phí. Ngược lại, không nên trả về một giá trị null chung cho mọi lỗi vì mất thông tin nguyên nhân.

Quy ước thực tế:

- Dùng kết quả có kiểu cho các trạng thái nghiệp vụ dự kiến.
- Dùng exception có cấu trúc cho lỗi làm gián đoạn thao tác.
- Giữ nguyên nguyên nhân kỹ thuật khi bọc lỗi.
- Không để exception nội bộ rò rỉ như hợp đồng công khai của DSL.

## 15. Bảo đảm an toàn khi xử lý lỗi

Xử lý lỗi có thể tạo ra rủi ro nếu handler quá rộng hoặc thực hiện hành động thay thế thiếu kiểm soát.

Những nguyên tắc cần xem xét:

1. **Không nuốt lỗi âm thầm.** Nếu bỏ qua, phải ghi nhận số lượng, phạm vi và lý do.
2. **Không retry vô hạn.** Mọi chính sách retry cần có giới hạn lần thử và thời gian.
3. **Không retry thao tác có tác dụng phụ một cách mù quáng.** Cần idempotency hoặc cơ chế xác nhận trạng thái.
4. **Không dùng fallback làm sai dữ liệu.** Giá trị thay thế phải có ý nghĩa nghiệp vụ rõ ràng.
5. **Không bắt mọi lỗi rồi đánh dấu thành công.** Trạng thái cuối phải phản ánh đúng kết quả.
6. **Giải phóng tài nguyên.** Đóng file, kết nối, transaction và lock trong cả đường thành công lẫn thất bại.
7. **Giới hạn thông tin lỗi hiển thị.** Không để lộ secret, dữ liệu nhạy cảm hoặc chi tiết nội bộ không cần thiết.
8. **Giữ dấu vết nguyên nhân.** Bảo toàn cause, execution ID và source location.
9. **Phân biệt hủy với thất bại.** Hủy có thể là kết quả điều khiển hợp lệ.
10. **Không thực thi tiếp trên trạng thái không nhất quán.** Nếu không thể xác định trạng thái sau lỗi, cần dừng hoặc chuyển sang quy trình khôi phục an toàn.

## 16. Kiểm thử hành vi lỗi

Kiểm thử DSL không chỉ xác nhận trường hợp thành công. Cần kiểm tra các lỗi dự kiến và hành vi sau lỗi.

### 16.1. Kiểm thử theo loại lỗi

| Tình huống | Điều cần xác nhận |
|---|---|
| Nguồn không tồn tại | Error code và source location chính xác |
| Thiếu quyền đọc | Không đọc dữ liệu; log không làm lộ thông tin xác thực |
| Dữ liệu sai kiểu | Bản ghi hoặc bước được xác định đúng theo chính sách |
| Timeout | Thời gian chờ được giới hạn và trạng thái không bị hiểu sai |
| Dịch vụ trả lỗi tạm thời | Retry theo số lần và backoff đã khai báo |
| Retry thao tác tạo tài nguyên | Không tạo trùng khi có idempotency key |
| Bước giữa workflow thất bại | Các bước phụ thuộc được đánh dấu đúng |
| Hủy trong khi chạy | Công việc dừng có kiểm soát và tài nguyên được giải phóng |
| Handler cũng thất bại | Lỗi gốc và lỗi handler được giữ trong chẩn đoán |
| Engine phát sinh lỗi nội bộ | Người dùng nhận mã lỗi phù hợp; log có thông tin kỹ thuật để điều tra |

### 16.2. Fault injection

Fault injection là cách chủ động tạo sự cố trong môi trường kiểm thử, chẳng hạn làm dịch vụ trả timeout, ngắt kết nối, giới hạn dung lượng hoặc trả dữ liệu sai định dạng. Cách này giúp xác nhận engine thực sự tuân theo chính sách lỗi thay vì chỉ hoạt động tốt khi mọi hệ thống đều ổn định.

### 16.3. Kiểm thử tính nhất quán sau lỗi

Với thao tác có tác dụng phụ, cần xác nhận trạng thái sau lỗi:

- Transaction có rollback như dự kiến không?
- File tạm có được dọn dẹp không?
- Tài nguyên tạo dở có được ghi nhận không?
- Retry có tạo bản ghi trùng không?
- Resume có bỏ qua đúng các bước đã hoàn thành không?
- Trạng thái execution có phản ánh partial failure không?

Kiểm thử chỉ xác nhận exception được ném ra là chưa đủ. Cần kiểm tra cả trạng thái dữ liệu và tác dụng phụ còn lại.

## 17. Quy trình thiết kế chính sách lỗi cho một DSL

Có thể dùng quy trình sau khi đặc tả ngữ nghĩa thực thi:

1. **Liệt kê thao tác có thể thất bại.** Ví dụ đọc, ghi, truy vấn, gọi dịch vụ, chuyển đổi dữ liệu và cập nhật trạng thái.
2. **Xác định nguyên nhân và khả năng quan sát.** Phân biệt lỗi dữ liệu, miền, quyền, hạ tầng, tài nguyên và nội bộ.
3. **Chọn phạm vi lỗi.** Xác định lỗi ảnh hưởng đến biểu thức, bản ghi, bước, khối hay toàn workflow.
4. **Đặt chính sách mặc định.** Quy định fail-fast, tiếp tục, rollback hoặc trạng thái partial success khi không có handler.
5. **Xác định lỗi có thể xử lý.** Chọn mã lỗi hoặc nhóm lỗi mà người dùng được phép bắt.
6. **Định nghĩa retry và timeout.** Ghi rõ số lần, backoff, giới hạn thời gian và điều kiện idempotency.
7. **Định nghĩa hành vi khôi phục.** Quy định transaction, compensation, checkpoint và resume khi có tác dụng phụ.
8. **Thiết kế mô hình chẩn đoán.** Bao gồm error code, source location, execution ID và cause.
9. **Thiết kế trạng thái lần chạy.** Phân biệt thành công, thất bại, hủy và kết quả một phần.
10. **Kiểm thử fault path.** Tạo dữ liệu lỗi và sự cố môi trường để xác minh hành vi.
11. **Tài liệu hóa cho người dùng.** Giải thích lỗi nào có thể bắt, lỗi nào nên truyền lên và cách đọc chẩn đoán.

Các chính sách cần được kiểm tra với người dùng miền và người vận hành. Một mặc định hợp lý cho DSL cấu hình có thể không phù hợp với DSL giao dịch hoặc workflow phân tán.

## 18. Những sai lầm thường gặp

### 18.1. Xem mọi lỗi là một loại exception chung

Nếu mọi tình huống đều thành ExecutionFailed, người dùng không thể phân biệt dữ liệu sai với dịch vụ tạm thời không sẵn sàng. Hãy dùng mã lỗi và nhóm nguyên nhân ổn định.

### 18.2. Chỉ thiết kế đường chạy thành công

Một DSL có thể thực thi tốt với dữ liệu mẫu nhưng thất bại khó dự đoán khi gặp tệp thiếu, quyền bị từ chối hoặc dịch vụ timeout. Hãy đặc tả lỗi ngay khi xác định ngữ nghĩa của từng thao tác.

### 18.3. Bắt lỗi quá rộng

Handler bắt mọi lỗi rồi tiếp tục có thể che giấu lỗi nội bộ hoặc làm kết quả sai. Chỉ xử lý các nhóm lỗi mà người viết DSL có đủ thông tin để phục hồi.

### 18.4. Retry không giới hạn

Retry liên tục có thể làm tăng tải lên hệ thống đang gặp sự cố và khiến workflow không bao giờ kết thúc. Cần giới hạn số lần, thời gian và loại lỗi được thử lại.

### 18.5. Không tính đến tác dụng phụ

Chạy lại một thao tác tạo giao dịch, gửi email hoặc tạo tài nguyên có thể lặp tác dụng phụ. Cần idempotency key, kiểm tra trạng thái hoặc thao tác bù trừ.

### 18.6. Báo thành công khi đã bỏ qua dữ liệu

Nếu một số bản ghi bị bỏ qua, kết quả có thể không đầy đủ. Trạng thái và thống kê phải thể hiện điều đó.

### 18.7. Mất vị trí nguồn khi sinh mã

Nếu lỗi backend không thể ánh xạ về DSL, người dùng phải đọc SQL hoặc mã được sinh để tìm nguyên nhân. Hãy duy trì source span hoặc source map.

### 18.8. Ghi log quá nhiều thông tin nhạy cảm

Log đầy đủ không có nghĩa là log mọi dữ liệu. Cần giới hạn nội dung, che thông tin xác thực và kiểm soát quyền truy cập log.

## 19. Câu hỏi tự kiểm tra

1. Phân biệt lỗi cú pháp, lỗi ngữ nghĩa tĩnh và lỗi trong quá trình thực thi bằng ví dụ.
2. Nêu ít nhất năm nhóm nguyên nhân có thể gây runtime error trong một DSL.
3. Vì sao lỗi miền cần được phân biệt với lỗi hạ tầng?
4. Một thông báo lỗi runtime hữu ích nên có những trường thông tin nào?
5. Giải thích fail-fast, xử lý lỗi ở cấp bản ghi và xử lý lỗi ở cấp workflow.
6. Khi nào nên retry? Vì sao timeout không chứng minh thao tác ở hệ thống đích chưa hoàn thành?
7. Idempotency giúp retry an toàn như thế nào? Nêu một thao tác có thể tạo tác dụng phụ trùng lặp.
8. Phân biệt rollback với compensation trong workflow phân tán.
9. Vì sao trạng thái PARTIAL_FAILURE cần được phân biệt với SUCCEEDED?
10. Hãy đề xuất chính sách lỗi cho một DSL xử lý dữ liệu batch, gồm lỗi dữ liệu, giới hạn số bản ghi lỗi, retry và kết quả đầu ra.
11. Một handler bắt mọi lỗi rồi tiếp tục có thể gây ra những vấn đề gì?
12. Hãy mô tả cách kiểm thử runtime khi dịch vụ bên ngoài timeout sau khi đã nhận yêu cầu tạo tài nguyên.
