# Mô hình hóa ví dụ

## 1. Vai trò của ví dụ trong mô hình hóa miền

Khi thiết kế ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL), nhóm phát triển cần hiểu cách người dùng thực hiện công việc trong miền trước khi quyết định ngôn ngữ sẽ có những khái niệm, quy tắc và cấu trúc nào. Tài liệu mô tả quy trình hoặc danh sách thuật ngữ thường cung cấp cái nhìn tổng quát, nhưng chúng có thể chưa thể hiện đầy đủ cách các khái niệm phối hợp trong một tình huống cụ thể.

**Ví dụ miền** mô tả một tình huống có thật hoặc có thể xảy ra, gồm bối cảnh, dữ liệu, thao tác, quy tắc và kết quả mong muốn. Khi tập hợp và phân tích các ví dụ, nhóm có thể nhận ra:

- Những đối tượng và khái niệm xuất hiện thường xuyên.
- Các thuộc tính và quan hệ có ý nghĩa đối với công việc.
- Những thao tác người dùng thực hiện và thứ tự của chúng.
- Điều kiện khiến một thao tác hợp lệ hoặc không hợp lệ.
- Những trường hợp khác nhau nhưng cùng tuân theo một quy tắc chung.
- Ngoại lệ, giới hạn và điểm chưa thống nhất trong cách hiểu của người dùng.

Mô hình hóa ví dụ là quá trình chuyển những tình huống cụ thể thành một mô hình miền có cấu trúc. Mô hình này giúp nhóm thiết kế DSL biết ngôn ngữ cần biểu đạt điều gì và công cụ phải hiểu các biểu thức như thế nào.

Ví dụ không phải là mô hình hoàn chỉnh của cả miền. Một ví dụ đơn lẻ chỉ phản ánh một trường hợp. Cần nhiều ví dụ được chọn có chủ đích để phân biệt quy tắc chung với chi tiết ngẫu nhiên, đồng thời kiểm tra xem mô hình đề xuất có giải thích được các tình huống khác nhau hay không.

## 2. Ví dụ miền khác gì với mô hình miền?

Hai khái niệm liên quan nhưng không giống nhau:

- **Ví dụ miền (domain example):** mô tả một trường hợp cụ thể, chẳng hạn một pipeline đọc tệp đơn hàng, lọc đơn đã thanh toán, nhóm theo khách hàng và tính tổng tiền.
- **Mô hình miền (domain model):** biểu diễn các khái niệm, thuộc tính, quan hệ, quy tắc và hành vi chung có thể giải thích nhiều trường hợp, chẳng hạn nguồn dữ liệu, trường dữ liệu, phép lọc, phép nhóm, phép tổng hợp và đích xuất.

Ví dụ cung cấp dữ liệu và tình huống để suy ra mô hình. Mô hình lại giúp giải thích ví dụ và dự đoán cách xử lý các trường hợp mới.

| Khía cạnh | Ví dụ cụ thể | Mô hình miền rút ra |
|---|---|---|
| Nguồn dữ liệu | Tệp `orders.csv` | Một nguồn dữ liệu có tên, định dạng và lược đồ |
| Trường dữ liệu | `status`, `customer_id`, `amount` | Trường có tên và kiểu dữ liệu |
| Điều kiện | Chỉ lấy bản ghi có `status = PAID` | Biểu thức điều kiện tham chiếu trường và giá trị |
| Nhóm | Nhóm theo `customer_id` | Phép nhóm nhận một hoặc nhiều khóa |
| Tổng hợp | Tính tổng `amount` | Phép tổng hợp áp dụng hàm lên trường phù hợp |
| Đầu ra | Tệp `customer-revenue.csv` | Một đích xuất có định dạng và vị trí |

Nếu chỉ lưu nguyên ví dụ, nhóm có thể biết cách xử lý đúng một tệp cụ thể nhưng chưa biết cách mô tả một pipeline khác. Nếu chỉ xây dựng mô hình trừu tượng mà không đối chiếu với ví dụ, mô hình có nguy cơ quá lý thuyết hoặc bỏ sót nhu cầu thực tế.

## 3. Chọn ví dụ để khám phá miền

Chất lượng mô hình phụ thuộc đáng kể vào chất lượng và độ đa dạng của ví dụ. Không nên chỉ chọn những tình huống dễ nhất hoặc những ví dụ do nhóm thiết kế ngôn ngữ tự nghĩ ra. Hãy thu thập tình huống từ người dùng, quy trình hiện có, dữ liệu mẫu, cấu hình, mã nguồn và các lỗi đã gặp.

### 3.1. Các loại ví dụ nên có

Một tập ví dụ hữu ích thường bao gồm:

| Loại ví dụ | Mục đích | Ví dụ với DSL xử lý dữ liệu |
|---|---|---|
| Trường hợp thông thường (happy path) | Xác định luồng chính và cách dùng phổ biến | Đọc tệp CSV hợp lệ, lọc, nhóm, tổng hợp và xuất kết quả |
| Biến thể phổ biến | Tìm phần thay đổi giữa các trường hợp | Thay đổi điều kiện lọc hoặc khóa nhóm |
| Trường hợp biên | Làm rõ giới hạn và cách xử lý dữ liệu đặc biệt | Tệp rỗng, giá trị `null`, số âm hoặc tên trường có ký tự đặc biệt |
| Trường hợp không hợp lệ | Xác định quy tắc từ chối và thông báo lỗi | Tổng hợp một trường kiểu chuỗi bằng hàm `sum` |
| Trường hợp ngoại lệ | Tìm hiểu cách xử lý sự cố hoặc gián đoạn | Một tệp đầu vào không đọc được hoặc thiếu trường bắt buộc |
| Trường hợp quy mô lớn | Làm rõ yêu cầu hiệu năng và tài nguyên | Tập dữ liệu có hàng chục triệu bản ghi |
| Trường hợp thay đổi theo ngữ cảnh | Phát hiện quy tắc phụ thuộc vai trò hoặc môi trường | Chỉ một nhóm người dùng được đọc nguồn dữ liệu nhạy cảm |

Không phải mọi DSL đều cần mọi loại ví dụ. Hãy chọn loại phù hợp với miền và hậu quả của lỗi. Một DSL chỉ dùng để định dạng tài liệu có thể không cần mô hình hóa quyền thực thi như một DSL điều khiển hạ tầng.

### 3.2. Chọn ví dụ có tính đại diện

Ví dụ đại diện phải phản ánh công việc mà người dùng thực sự làm. Khi chọn, cần xem xét:

- Tần suất xuất hiện của tình huống.
- Mức độ quan trọng đối với kết quả công việc.
- Sự khác nhau về dữ liệu, quy trình và người dùng.
- Các điều kiện hoặc ràng buộc thường gây lỗi.
- Khả năng quan sát được đầu vào và kết quả mong đợi.

Một tập ví dụ chỉ gồm những trường hợp giống nhau có thể khiến nhóm kết luận sai rằng một khái niệm luôn có cùng cấu trúc. Ngược lại, tập ví dụ chỉ gồm ngoại lệ hiếm gặp có thể làm mô hình trở nên quá phức tạp. Nên bắt đầu từ các tình huống phổ biến, sau đó bổ sung các biến thể và trường hợp biên có ảnh hưởng lớn.

### 3.3. Ghi lại ví dụ có cấu trúc

Mỗi ví dụ nên có đủ thông tin để người khác hiểu và kiểm chứng. Có thể dùng mẫu sau:

| Trường | Nội dung cần ghi |
|---|---|
| Mã ví dụ | Mã định danh duy nhất, ví dụ `EX-PIPE-001` |
| Tên tình huống | Mô tả ngắn, dễ nhận biết |
| Người dùng và mục tiêu | Ai thực hiện, muốn đạt kết quả gì |
| Bối cảnh | Điều kiện hoặc quy trình dẫn đến tình huống |
| Đầu vào | Dữ liệu, tài nguyên hoặc cấu hình được sử dụng |
| Các bước | Những thao tác theo đúng thứ tự nghiệp vụ |
| Quy tắc | Điều kiện, giới hạn và ràng buộc áp dụng |
| Kết quả mong đợi | Đầu ra hoặc trạng thái sau khi hoàn thành |
| Trường hợp lỗi | Hành vi cần có khi đầu vào hoặc thao tác không hợp lệ |
| Nguồn và độ tin cậy | Người cung cấp, tài liệu hoặc dữ liệu xác nhận |

Ghi rõ nguồn giúp phân biệt ví dụ được quan sát từ quy trình thật với ví dụ giả định do nhóm tạo ra để kiểm tra mô hình.

## 4. Ví dụ xuyên suốt: mô hình hóa một pipeline báo cáo doanh thu

Giả sử nhóm phân tích dữ liệu thường xuyên tạo báo cáo doanh thu theo khách hàng. Quy trình hiện tại gồm đọc tệp đơn hàng, giữ các đơn đã thanh toán, nhóm theo mã khách hàng, tính tổng tiền và ghi kết quả ra tệp mới.

### 4.1. Mô tả tình huống bằng ngôn ngữ tự nhiên

Người dùng cung cấp yêu cầu:

> Đọc dữ liệu đơn hàng từ `orders.csv`. Chỉ giữ các đơn có trạng thái `PAID`. Nhóm những đơn còn lại theo `customer_id`, tính tổng `amount` cho mỗi khách hàng và ghi kết quả vào `customer-revenue.csv`.

Ở giai đoạn này, chưa cần chuyển yêu cầu thành cú pháp DSL. Trước tiên hãy xác định mục tiêu, đầu vào, các bước và kết quả.

| Thành phần | Giá trị trong tình huống |
|---|---|
| Người dùng | Nhân viên phân tích dữ liệu |
| Mục tiêu | Tạo tổng doanh thu theo khách hàng |
| Nguồn | `orders.csv` |
| Điều kiện lọc | `status` bằng `PAID` |
| Khóa nhóm | `customer_id` |
| Phép tổng hợp | Tính tổng `amount` |
| Đầu ra | `customer-revenue.csv` |

### 4.2. Xác định dữ liệu đầu vào

Giả sử tệp đầu vào có cấu trúc như sau:

```csv
order_id,customer_id,status,amount
O-1001,C-01,PAID,120.50
O-1002,C-02,PENDING,80.00
O-1003,C-01,PAID,35.00
O-1004,C-03,PAID,210.00
O-1005,C-02,PAID,45.00
```

Từ dữ liệu này, nhóm nhận diện các trường và kiểu dữ liệu:

| Trường | Kiểu dữ liệu dự kiến | Vai trò |
|---|---|---|
| `order_id` | Chuỗi | Định danh đơn hàng |
| `customer_id` | Chuỗi | Khóa khách hàng dùng để nhóm |
| `status` | Chuỗi hoặc kiểu trạng thái | Điều kiện lọc |
| `amount` | Số thập phân | Giá trị được tổng hợp |

Đây là một lược đồ minh họa. Trong hệ thống thật, kiểu dữ liệu phải được xác định từ hợp đồng dữ liệu hoặc nguồn có thẩm quyền. Chỉ nhìn vào vài dòng dữ liệu không đủ để khẳng định mọi bản ghi đều tuân theo cùng kiểu và ràng buộc.

### 4.3. Mô tả các bước và kết quả

Sau khi lọc, các bản ghi còn lại là O-1001, O-1003, O-1004 và O-1005. Khi nhóm theo `customer_id`, kết quả tổng hợp là:

| customer_id | Tổng amount |
|---|---:|
| C-01 | 155.50 |
| C-02 | 45.00 |
| C-03 | 210.00 |

Kết quả này giúp xác nhận cách hiểu của người dùng. Nếu người dùng mong đợi số tiền đã bao gồm thuế, quy đổi tiền tệ hoặc loại trừ đơn hoàn tiền, các quy tắc đó phải được hỏi và ghi nhận. Không được tự suy ra từ tên trường `amount`.

### 4.4. Từ ví dụ cụ thể đến các khái niệm miền

Phân tích tình huống cho thấy các khái niệm sau:

| Khái niệm miền | Ý nghĩa | Thuộc tính hoặc thông tin liên quan |
|---|---|---|
| Data source (nguồn dữ liệu) | Nơi cung cấp các bản ghi | Vị trí, định dạng, lược đồ |
| Field (trường) | Một thuộc tính trong bản ghi | Tên, kiểu dữ liệu, khả năng rỗng |
| Record (bản ghi) | Một đơn vị dữ liệu đầu vào | Tập giá trị theo lược đồ |
| Predicate (điều kiện) | Biểu thức quyết định bản ghi có được giữ lại không | Trường, toán tử, giá trị |
| Filter (phép lọc) | Chọn các bản ghi thỏa điều kiện | Nguồn đầu vào và điều kiện |
| Group key (khóa nhóm) | Xác định nhóm mà bản ghi thuộc về | Một hoặc nhiều trường |
| Aggregate (phép tổng hợp) | Tính giá trị từ các bản ghi trong nhóm | Hàm, trường đầu vào, kiểu kết quả |
| Output (đầu ra) | Nơi nhận kết quả | Vị trí, định dạng, lược đồ kết quả |

Những tên gọi này tạo thành từ vựng ban đầu của miền. Cần xác minh với người dùng rằng chúng phản ánh đúng cách họ hiểu công việc. Ví dụ, một nhóm có thể gọi thao tác là “tổng hợp”, trong khi nhóm khác phân biệt “tính chỉ số” và “tổng hợp”. Sự khác nhau về từ vựng có thể cho thấy mô hình cần làm rõ thêm.

## 5. Xây dựng mô hình khái niệm từ ví dụ

Sau khi có một số ví dụ, hãy xác định các khái niệm ổn định và mối quan hệ giữa chúng. Mô hình khái niệm mô tả miền ở mức đủ để người dùng và nhóm phát triển cùng hiểu, chưa bị ràng buộc bởi cú pháp hay cấu trúc lớp của một ngôn ngữ lập trình cụ thể.

### 5.1. Phân loại khái niệm

Một cách hữu ích là phân loại các thành phần được tìm thấy:

- **Thực thể (entity):** đối tượng có danh tính và vòng đời riêng trong miền. Ví dụ, một pipeline đã lưu có mã định danh và có thể được cập nhật qua nhiều phiên bản.
- **Giá trị (value):** dữ liệu được xác định bởi giá trị của nó, không cần danh tính độc lập. Ví dụ, tên trường, đường dẫn tệp hoặc một biểu thức điều kiện.
- **Tập hợp (collection):** nhóm các phần tử có cùng vai trò. Ví dụ, danh sách các bước trong pipeline hoặc danh sách khóa nhóm.
- **Hành động (operation):** thao tác làm thay đổi dữ liệu hoặc tạo kết quả. Ví dụ, lọc, nhóm, tổng hợp và xuất.
- **Quy tắc (rule):** điều kiện phải được thỏa mãn. Ví dụ, hàm `sum` chỉ áp dụng cho kiểu dữ liệu số được hỗ trợ.
- **Trạng thái (state):** tình trạng của một đối tượng trong vòng đời. Ví dụ, một lần chạy pipeline có thể ở trạng thái đang chờ, đang chạy, thành công hoặc thất bại.

Không nên mặc định mọi danh từ trong ví dụ đều phải trở thành một thực thể hoặc một lớp trong mô hình. Hãy xem xét vai trò, vòng đời, danh tính và cách người dùng thao tác với khái niệm đó.

### 5.2. Xác định quan hệ và số lượng

Ví dụ pipeline có thể được mô hình hóa bằng các quan hệ:

- Một pipeline có một hoặc nhiều bước xử lý theo thứ tự.
- Một bước lọc tham chiếu đến một biểu thức điều kiện.
- Một biểu thức điều kiện tham chiếu đến trường và giá trị so sánh.
- Một bước nhóm có một hoặc nhiều khóa nhóm.
- Một bước tổng hợp có một hoặc nhiều phép tính.
- Một pipeline có một đích đầu ra.

Biểu diễn khái niệm đơn giản:

```text
Pipeline
  ├── Source
  ├── Step (1..n)
  │     ├── Filter
  │     │     └── Predicate
  │     │           ├── Field
  │     │           └── Value
  │     ├── GroupBy
  │     │     └── Field (1..n)
  │     └── Aggregate
  │           └── AggregateExpression (1..n)
  └── Output
```

Sơ đồ này là mô hình khái niệm minh họa, không phải cấu trúc lớp bắt buộc. Trong mô hình chi tiết hơn, `Step` có thể là kiểu tổng quát với các dạng cụ thể như `FilterStep`, `GroupStep` và `AggregateStep`. Cách biểu diễn nên phụ thuộc vào ngữ nghĩa và nhu cầu mở rộng.

### 5.3. Mô tả thuộc tính và kiểu dữ liệu

Mỗi khái niệm cần có các thuộc tính đủ để phân biệt và kiểm tra. Ví dụ:

| Khái niệm | Thuộc tính | Kiểu hoặc miền giá trị | Ràng buộc minh họa |
|---|---|---|---|
| Source | `path` | Chuỗi đường dẫn | Không được rỗng |
| Source | `format` | CSV, JSON, Parquet... | Phải là định dạng được hỗ trợ |
| Field | `name` | Chuỗi | Phải tồn tại trong lược đồ nguồn |
| Field | `type` | Kiểu dữ liệu | Dùng để kiểm tra toán tử và phép tổng hợp |
| Predicate | `operator` | `=`, `!=`, `>`, `<`, `in`... | Toán tử phải tương thích với kiểu trường |
| GroupBy | `keys` | Danh sách trường | Có ít nhất một trường hợp lệ |
| AggregateExpression | `function` | `sum`, `count`, `min`, `max`... | Hàm phải được hỗ trợ |
| Output | `path` | Chuỗi đường dẫn | Không được xung đột với đầu vào nếu miền cấm ghi đè |

Các ràng buộc trong bảng là ví dụ. Quy tắc chính xác phải được xác định theo miền, hệ thống và yêu cầu của người dùng.

## 6. Mô hình hóa quy tắc và ngữ nghĩa

Mô hình miền không chỉ liệt kê danh từ và quan hệ. Nó còn phải giải thích một thao tác có ý nghĩa gì, khi nào được phép thực hiện và kết quả ra sao.

### 6.1. Quy tắc hợp lệ

Với pipeline báo cáo doanh thu, có thể xác định một số quy tắc:

1. Nguồn dữ liệu phải được khai báo trước khi tham chiếu đến trường của nguồn.
2. Tên trường trong điều kiện lọc phải tồn tại trong lược đồ nguồn.
3. Toán tử so sánh phải tương thích với kiểu của trường và giá trị so sánh.
4. Khóa nhóm phải tham chiếu đến trường hợp lệ.
5. Hàm `sum` chỉ áp dụng cho kiểu số mà runtime hỗ trợ.
6. Mỗi tên cột đầu ra phải duy nhất trong kết quả.
7. Đích xuất phải được xác định và người chạy phải có quyền ghi vào vị trí đó.

Các quy tắc nên được viết rõ, tránh chỉ mô tả bằng những cụm từ mơ hồ như “dữ liệu hợp lệ” hoặc “đầu vào phù hợp”.

### 6.2. Quy tắc xử lý giá trị đặc biệt

Ví dụ ban đầu có thể chưa chứa giá trị rỗng, số âm hoặc dữ liệu sai định dạng. Khi mở rộng tập ví dụ, nhóm phải xác định hành vi mong muốn:

| Tình huống | Câu hỏi cần làm rõ |
|---|---|
| Trường `amount` có giá trị `null` | Bỏ qua, coi là 0, giữ nhóm riêng hay báo lỗi? |
| `amount` là số âm | Có hợp lệ với khoản hoàn tiền hoặc điều chỉnh không? |
| `status` có chữ thường như `paid` | So sánh có phân biệt hoa thường không? |
| `customer_id` bị thiếu | Bản ghi bị loại, đưa vào nhóm không xác định hay làm pipeline thất bại? |
| Tệp rỗng | Trả kết quả rỗng hay báo lỗi? |
| Có hai trường cùng tên sau phép biến đổi | Có quy tắc đổi tên hoặc phát hiện xung đột không? |

Không có đáp án mặc định đúng cho mọi miền. Quyết định phải dựa trên ý nghĩa dữ liệu và kỳ vọng của người dùng. Nếu chưa có câu trả lời, hãy ghi nhận là điểm cần xác minh thay vì tự chọn một hành vi.

### 6.3. Quy tắc thứ tự thao tác

Thứ tự các bước có thể ảnh hưởng đến kết quả. Ví dụ, lọc trước khi nhóm có thể tạo kết quả khác với nhóm trước rồi lọc trên kết quả tổng hợp. Vì vậy, mô hình cần xác định thao tác nào được phép đứng ở vị trí nào và mỗi thao tác nhận loại dữ liệu gì.

Với pipeline đơn giản, có thể quy định luồng dữ liệu tuyến tính:

```text
Source -> Filter -> GroupBy -> Aggregate -> Output
```

Nếu DSL hỗ trợ nhiều nhánh, kết hợp dữ liệu hoặc thao tác song song, mô hình cần biểu diễn đồ thị phụ thuộc thay vì giả định mọi bước chỉ có một bước trước và một bước sau.

## 7. Từ mô hình miền đến ví dụ DSL

Khi khái niệm và quy tắc đã đủ rõ, nhóm có thể thử biểu đạt tình huống bằng một cú pháp DSL giả định. Mục đích là kiểm tra xem mô hình có thể được diễn đạt tự nhiên và nhất quán hay không.

Ví dụ:

```text
pipeline "customer-revenue" {
    source "orders.csv" format csv

    filter status == "PAID"

    group_by customer_id

    aggregate total_amount = sum(amount)

    output "customer-revenue.csv" format csv
}
```

Đây là cú pháp minh họa, không đại diện cho một DSL hoặc công cụ cụ thể. Có thể truy vết từng phần về mô hình miền:

| Thành phần DSL | Khái niệm miền được biểu đạt | Điều cần kiểm tra |
|---|---|---|
| `pipeline` | Pipeline | Tên và phạm vi của quy trình |
| `source` | Nguồn dữ liệu | Định dạng và lược đồ nguồn |
| `filter` | Phép lọc | Trường, toán tử, giá trị và kiểu dữ liệu |
| `group_by` | Phép nhóm | Các khóa nhóm tồn tại và hợp lệ |
| `aggregate` | Phép tổng hợp | Hàm, kiểu đầu vào và tên kết quả |
| `output` | Đích xuất | Đường dẫn, định dạng và quyền ghi |

Mỗi cấu trúc cú pháp phải có ngữ nghĩa tương ứng. Chẳng hạn, `filter status == "PAID"` cần được hiểu là giữ lại những bản ghi có giá trị trường `status` bằng chuỗi `PAID` theo quy tắc so sánh đã định nghĩa. Nếu DSL không xác định cách xử lý `null` hoặc khác biệt chữ hoa thường, kết quả có thể không rõ ràng.

### 7.1. Phân biệt mô hình miền và cú pháp DSL

Mô hình miền trả lời câu hỏi “những khái niệm nào tồn tại và chúng liên hệ ra sao?”. Cú pháp DSL trả lời câu hỏi “người dùng viết những khái niệm đó bằng cách nào?”. Hai phần liên quan nhưng không nên bị đồng nhất.

Ví dụ, khái niệm phép lọc có thể được viết bằng nhiều cú pháp:

```text
filter status == "PAID"
```

Hoặc:

```text
where(status, equals, "PAID")
```

Hoặc dạng cấu hình:

```yaml
filter:
  field: status
  operator: equals
  value: PAID
```

Các cách viết có thể khác nhau nhưng cùng biểu đạt một khái niệm nếu ngữ nghĩa được định nghĩa thống nhất. Một mô hình miền tốt giúp thay đổi cú pháp mà không phải thay đổi tùy tiện ý nghĩa của miền.

## 8. Dùng ví dụ để phát hiện điểm thiếu trong mô hình

Sau khi xây dựng mô hình ban đầu, hãy đối chiếu lần lượt với từng ví dụ. Với mỗi trường hợp, cần hỏi:

- Mô hình có biểu diễn được toàn bộ đầu vào và kết quả không?
- Có khái niệm nào đang bị dùng sai hoặc có tên không rõ nghĩa không?
- Có quy tắc nào được giả định nhưng chưa được xác nhận không?
- Có hai ví dụ cùng tên thao tác nhưng khác ngữ nghĩa không?
- Mô hình có phải thêm ngoại lệ riêng cho một trường hợp hay không?
- Nếu thêm một ví dụ mới, mô hình có cần thay đổi cấu trúc cơ bản không?

Nếu một ví dụ không thể biểu diễn bằng mô hình, có thể có ba nguyên nhân:

1. Ví dụ nằm ngoài phạm vi DSL đã xác định.
2. Mô hình còn thiếu một khái niệm hoặc quy tắc quan trọng.
3. Cách mô tả ví dụ chưa đủ rõ hoặc dữ liệu nguồn có vấn đề.

Không nên thêm ngay một trường hoặc từ khóa mới chỉ để xử lý một ví dụ. Trước tiên cần xác định đó là nhu cầu phổ biến, một biến thể có ý nghĩa, hay một ngoại lệ nên được xử lý bên ngoài DSL.

## 9. Chuyển ví dụ thành ca kiểm thử

Ví dụ miền có thể trở thành cơ sở cho kiểm thử ngôn ngữ và công cụ thực thi. Khi một ví dụ có đầu vào và kết quả mong đợi rõ ràng, nhóm có thể kiểm tra liệu parser, bộ kiểm tra ngữ nghĩa và runtime có xử lý đúng hay không.

### 9.1. Kiểm thử trường hợp hợp lệ

Với ví dụ pipeline báo cáo doanh thu, có thể xác định:

- DSL đầu vào phải được phân tích thành cấu trúc pipeline tương ứng.
- Tên nguồn, trường, khóa nhóm và hàm tổng hợp phải được nhận diện đúng.
- Kết quả sau khi chạy phải khớp với bảng tổng doanh thu mong đợi.
- Định dạng và vị trí đầu ra phải tuân theo khai báo.

### 9.2. Kiểm thử trường hợp không hợp lệ

Các ví dụ lỗi giúp kiểm tra khả năng phát hiện và giải thích vấn đề:

| DSL hoặc tình huống lỗi | Kết quả kiểm tra mong đợi |
|---|---|
| `filter unknown_field == "PAID"` | Báo trường không tồn tại trong lược đồ nguồn |
| `aggregate total = sum(status)` | Báo kiểu trường không phù hợp với hàm `sum` |
| `group_by` không có khóa | Báo thiếu khóa nhóm nếu ngữ nghĩa yêu cầu ít nhất một khóa |
| Đầu ra không có đường dẫn | Báo thiếu thông tin đầu ra |
| Nguồn có định dạng không được hỗ trợ | Báo định dạng không hợp lệ hoặc không được hỗ trợ |

Thông báo lỗi nên chỉ ra vị trí hoặc thành phần liên quan, nêu rõ điều kiện bị vi phạm và gợi ý cách khắc phục khi có thể.

### 9.3. Tách kiểm thử cú pháp, ngữ nghĩa và kết quả

Một ví dụ có thể được dùng ở nhiều tầng kiểm thử:

| Tầng kiểm thử | Điều cần xác nhận | Ví dụ |
|---|---|---|
| Phân tích cú pháp | Cấu trúc được viết có đúng ngữ pháp không? | Thiếu dấu ngoặc đóng phải tạo lỗi cú pháp |
| Kiểm tra ngữ nghĩa | Các tham chiếu và thao tác có hợp lệ không? | `sum` không nhận trường kiểu chuỗi |
| Thực thi | Kết quả tính toán có đúng không? | Tổng doanh thu của C-01 bằng 155.50 |
| Tích hợp | Công cụ làm việc đúng với nguồn và đích thật không? | Đọc CSV và ghi CSV theo cấu hình |

Phân biệt các tầng này giúp xác định lỗi xuất phát từ cú pháp, mô hình, quy tắc hay cơ chế thực thi.

## 10. Mô hình hóa biến thể và điểm chung

Khi có nhiều ví dụ, hãy so sánh chúng để tìm phần giống nhau và khác nhau. Phần giống nhau có thể trở thành cấu trúc chung của DSL; phần khác nhau có thể là tham số, lựa chọn hoặc một khái niệm riêng.

Ví dụ ba yêu cầu:

1. Tính doanh thu theo khách hàng từ các đơn đã thanh toán.
2. Tính số đơn hàng theo trạng thái.
3. Tính giá trị đơn hàng lớn nhất theo từng khu vực.

Các ví dụ có thể dùng chung một số khái niệm: nguồn dữ liệu, điều kiện lọc, khóa nhóm, hàm tổng hợp và đầu ra. Chúng khác nhau ở điều kiện, trường nhóm và phép tổng hợp.

| Thành phần | Ví dụ 1 | Ví dụ 2 | Ví dụ 3 |
|---|---|---|---|
| Nguồn | `orders.csv` | `orders.csv` | `orders.csv` |
| Lọc | `status == PAID` | Không bắt buộc | Có thể lọc theo thời gian |
| Nhóm | `customer_id` | `status` | `region` |
| Tổng hợp | `sum(amount)` | `count(order_id)` | `max(amount)` |
| Kết quả | Doanh thu theo khách hàng | Số đơn theo trạng thái | Đơn hàng lớn nhất theo khu vực |

Từ đó, DSL có thể cung cấp một cấu trúc pipeline chung với các tham số thay đổi. Tuy nhiên, không nên khái quát hóa quá sớm. Nếu hai thao tác có ngữ nghĩa khác nhau đáng kể, ép chúng vào cùng một cấu trúc có thể khiến ngôn ngữ khó hiểu.

### 10.1. Phân biệt điểm chung thực sự với sự giống nhau bề ngoài

Hai ví dụ có thể dùng cùng từ “nhóm” nhưng mang ý nghĩa khác nhau. Ví dụ, nhóm bản ghi theo khóa dữ liệu không nhất thiết giống nhóm người dùng theo quyền truy cập. Không nên hợp nhất khái niệm chỉ vì chúng có tên giống nhau hoặc cùng được biểu diễn bằng một danh sách.

Hãy so sánh:

- Mục tiêu nghiệp vụ của thao tác.
- Đầu vào và đầu ra.
- Các quy tắc hợp lệ.
- Vòng đời và quan hệ với các khái niệm khác.
- Những thay đổi có thể xảy ra trong tương lai.

Nếu các yếu tố này khác nhau, nên giữ hai khái niệm riêng và chỉ dùng chung cơ chế triển khai ở tầng kỹ thuật khi phù hợp.

## 11. Ví dụ về mô hình hóa trạng thái và chuyển đổi

Không phải miền nào cũng chỉ gồm dữ liệu và phép biến đổi. Một số DSL mô tả quy trình có trạng thái, chẳng hạn phê duyệt yêu cầu, triển khai dịch vụ hoặc xử lý đơn hàng. Khi đó, ví dụ cần làm rõ trạng thái, sự kiện, điều kiện chuyển và hành động đi kèm.

Ví dụ một yêu cầu triển khai có các trạng thái:

```text
Draft -> Validated -> Approved -> Deployed
                    \-> Rejected
```

Mô hình có thể gồm:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| State | Trạng thái hiện tại | `Draft`, `Approved`, `Deployed` |
| Event | Sự kiện kích hoạt xử lý | `Submit`, `Approve`, `Reject`, `Deploy` |
| Guard | Điều kiện để chuyển trạng thái | Chỉ được duyệt khi kiểm tra cấu hình thành công |
| Action | Hành động khi chuyển trạng thái | Tạo bản ghi triển khai hoặc gửi thông báo |
| Transition | Quy tắc chuyển trạng thái | `Approved` chuyển sang `Deployed` khi triển khai thành công |

Một ví dụ cần thể hiện cả chuyển đổi hợp lệ và không hợp lệ. Chẳng hạn, yêu cầu đang ở trạng thái `Draft` không thể được triển khai trực tiếp nếu quy trình bắt buộc phải qua bước kiểm tra và phê duyệt.

Từ các ví dụ, nhóm có thể rút ra bất biến: một yêu cầu chỉ được triển khai khi đã được phê duyệt; trạng thái cuối không được quay lại trạng thái nháp nếu miền không cho phép. Những quy tắc này có thể được DSL kiểm tra hoặc runtime thực thi.

## 12. Quy trình thực hành mô hình hóa ví dụ

Có thể áp dụng quy trình sau trong một buổi khám phá miền hoặc khi xây dựng nguyên mẫu DSL:

1. **Xác định mục tiêu khảo sát.** Nêu rõ nhóm muốn hiểu công việc, dữ liệu, quy tắc hay ngoại lệ nào.
2. **Thu thập tình huống.** Lấy ví dụ từ người dùng, tài liệu, cấu hình và quy trình hiện có.
3. **Ghi lại đầu vào, thao tác và kết quả.** Không bỏ qua các điều kiện, giả định và lỗi đã gặp.
4. **Đánh dấu thuật ngữ miền.** Ghi lại danh từ, động từ, trạng thái và quy tắc được người dùng nhắc đến.
5. **Phân loại khái niệm.** Xác định thực thể, giá trị, hành động, quan hệ và trạng thái khi có căn cứ.
6. **Tìm quy tắc chung.** So sánh nhiều ví dụ để nhận ra điểm chung và biến thể.
7. **Lập mô hình khái niệm.** Biểu diễn khái niệm, thuộc tính, quan hệ và ràng buộc.
8. **Thử diễn đạt bằng DSL.** Viết một vài biểu thức giả định để xem mô hình có thể được sử dụng rõ ràng không.
9. **Đối chiếu với ví dụ.** Kiểm tra cả trường hợp thông thường, biến thể, biên và không hợp lệ.
10. **Cập nhật mô hình và ghi quyết định.** Lưu phần đã xác nhận, giả định còn mở và lý do của các thay đổi.

Quy trình này có tính lặp. Khi mô hình được thử với ví dụ mới, nhóm có thể phát hiện thiếu khái niệm, quy tắc không rõ hoặc phạm vi quá rộng. Khi đó cần quay lại bước phân tích thay vì cố ép ví dụ vào mô hình hiện tại.

## 13. Những sai lầm thường gặp khi mô hình hóa ví dụ

### 13.1. Chỉ dùng một ví dụ

Một ví dụ không thể hiện hết biến thể và ngoại lệ. Mô hình suy ra từ một trường hợp dễ bị gắn chặt với dữ liệu hoặc quy trình cụ thể. Hãy thu thập các ví dụ khác nhau trước khi khái quát hóa.

### 13.2. Nhầm dữ liệu mẫu với quy tắc miền

Một tệp mẫu có thể chứa năm trường, nhưng điều đó không chứng minh miền luôn chỉ có năm trường. Một trạng thái xuất hiện trong dữ liệu không có nghĩa đó là trạng thái duy nhất. Hãy phân biệt điều quan sát được với quy tắc được xác nhận.

### 13.3. Biến mọi danh từ thành lớp

Không phải mọi từ xuất hiện trong mô tả đều cần trở thành thực thể hoặc kiểu riêng. Chỉ tạo khái niệm khi nó có ý nghĩa rõ trong miền, có thuộc tính hoặc quy tắc riêng, hoặc cần được tham chiếu độc lập.

### 13.4. Bỏ qua kết quả mong đợi

Nếu ví dụ không có đầu ra hoặc trạng thái mong đợi, nhóm khó xác định ngữ nghĩa của thao tác và khó kiểm thử. Hãy ghi rõ kết quả trước khi dùng ví dụ để đánh giá mô hình.

### 13.5. Đưa cú pháp vào quá sớm

Viết từ khóa và dấu ngoặc trước khi thống nhất khái niệm có thể khiến nhóm điều chỉnh mô hình để phù hợp với cú pháp đã chọn. Hãy xác định ý nghĩa và quy tắc trước, rồi thử nhiều cách biểu đạt.

### 13.6. Bỏ qua trường hợp lỗi và ranh giới

Chỉ mô hình hóa đường đi thành công khiến DSL có thể chấp nhận cấu hình sai hoặc tạo kết quả khó dự đoán. Hãy bổ sung ví dụ không hợp lệ, dữ liệu rỗng, thiếu trường và điều kiện xung đột.

### 13.7. Khái quát hóa quá mức

Không phải mọi khác biệt đều nên được xử lý bằng một tham số chung. Một mô hình quá tổng quát có thể làm cú pháp phức tạp và che khuất ý nghĩa miền. Chỉ hợp nhất khi các ví dụ thực sự chia sẻ ngữ nghĩa.

### 13.8. Không ghi lại giả định

Những quyết định như “giá trị rỗng được bỏ qua” hoặc “so sánh không phân biệt chữ hoa thường” có thể ảnh hưởng lớn đến kết quả. Nếu chưa được người dùng xác nhận, phải ghi là giả định và xác định cách kiểm chứng.

## 14. Mẫu ghi chép để thực hành

### 14.1. Mẫu mô tả một ví dụ

```text
Mã ví dụ:
Tên tình huống:
Nguồn ví dụ: (người dùng / tài liệu / dữ liệu / giả định)

Người dùng:
Mục tiêu:
Bối cảnh:

Đầu vào:
  - ...

Các bước:
  1. ...
  2. ...

Quy tắc và ràng buộc:
  - ...

Kết quả mong đợi:
  - ...

Trường hợp lỗi hoặc biên:
  - ...

Giả định cần xác minh:
  - ...
```

### 14.2. Mẫu rút trích mô hình miền

| Nhóm | Khái niệm | Định nghĩa | Thuộc tính / quan hệ | Quy tắc | Ví dụ tham chiếu |
|---|---|---|---|---|---|
| Thực thể | [Tên] | [Ý nghĩa] | [Thông tin] | [Ràng buộc] | [Mã ví dụ] |
| Giá trị | [Tên] | [Ý nghĩa] | [Kiểu] | [Ràng buộc] | [Mã ví dụ] |
| Hành động | [Tên] | [Ý nghĩa] | [Đầu vào / đầu ra] | [Điều kiện] | [Mã ví dụ] |
| Trạng thái | [Tên] | [Ý nghĩa] | [Chuyển đổi] | [Điều kiện] | [Mã ví dụ] |

### 14.3. Mẫu đối chiếu ví dụ với DSL

| Ý định trong ví dụ | Khái niệm miền | Cấu trúc DSL dự kiến | Quy tắc ngữ nghĩa | Kết quả kiểm thử |
|---|---|---|---|---|
| [Mô tả] | [Khái niệm] | [Biểu thức] | [Quy tắc] | [Đạt / lỗi / chưa xác minh] |

Mẫu này tạo liên kết giữa nhu cầu người dùng, mô hình, cú pháp và hành vi. Khi có thay đổi, nhóm có thể truy vết xem thay đổi đó ảnh hưởng đến ví dụ hoặc quy tắc nào.

## 15. Câu hỏi tự kiểm tra

1. Phân biệt một ví dụ miền với mô hình miền. Vì sao cần cả hai trong quá trình thiết kế DSL?
2. Nêu ít nhất bốn loại ví dụ nên thu thập để mô hình hóa một miền và giải thích mục đích của từng loại.
3. Với ví dụ pipeline báo cáo doanh thu, hãy xác định nguồn dữ liệu, trường, phép lọc, khóa nhóm, phép tổng hợp và đầu ra.
4. Phân biệt thực thể, giá trị, hành động và quy tắc bằng ví dụ thuộc một miền bạn biết.
5. Vì sao cần xác định hành vi đối với `null`, trường thiếu và kiểu dữ liệu không tương thích?
6. Mô hình miền và cú pháp DSL khác nhau như thế nào? Một khái niệm miền có thể được biểu đạt bằng nhiều cú pháp ra sao?
7. Hãy tạo hai ví dụ có cùng mục tiêu nhưng khác dữ liệu hoặc điều kiện, sau đó chỉ ra phần chung và phần biến thể trong mô hình.
8. Chọn một ví dụ không hợp lệ và mô tả cách DSL cần phát hiện, giải thích lỗi đó.
