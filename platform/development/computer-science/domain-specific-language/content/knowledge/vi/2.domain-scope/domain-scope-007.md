# Thuật ngữ miền

## Thuật ngữ miền là gì?

Một miền (domain) là phạm vi kiến thức và hoạt động mà một hệ thống phần mềm cần hỗ trợ. Miền có thể là thương mại điện tử, ngân hàng, vận tải, quản lý bệnh viện, xây dựng phần mềm hoặc một lĩnh vực kỹ thuật hẹp hơn. Mỗi miền có các đối tượng, hoạt động, trạng thái, quy tắc và cách gọi riêng.

**Thuật ngữ miền (domain terms)** là những từ và cụm từ mà người làm trong miền sử dụng để gọi tên các khái niệm đó. Trong miền thương mại điện tử, các thuật ngữ có thể gồm *khách hàng*, *giỏ hàng*, *đơn hàng*, *dòng hàng*, *thanh toán*, *hoàn tiền* và *vận chuyển*. Trong miền vận tải, người dùng có thể nói đến *chuyến*, *điểm nhận*, *điểm giao*, *tải trọng*, *tuyến đường* và *biên bản bàn giao*.

Thuật ngữ miền mang theo ý nghĩa nghiệp vụ. Chẳng hạn, từ “đơn hàng” không chỉ là một đối tượng có mã định danh trong chương trình. Nó còn gắn với quy tắc về người đặt, mặt hàng, số lượng, giá, trạng thái, thanh toán, hủy và giao hàng. Muốn mô hình hóa đúng miền, người thiết kế cần hiểu ý nghĩa và quan hệ của thuật ngữ, chứ không chỉ chọn tên biến dễ đọc.

Trong thiết kế ngôn ngữ chuyên miền (domain-specific language, DSL), thuật ngữ miền là nền tảng để xây dựng từ vựng của ngôn ngữ. DSL tốt cho phép người dùng diễn đạt vấn đề bằng những từ mà họ hiểu và đang sử dụng trong công việc. Vì vậy, việc thu thập, định nghĩa và thống nhất thuật ngữ là một phần quan trọng của quá trình thiết kế DSL.

## Phân biệt thuật ngữ miền với từ khóa và cú pháp của DSL

Ba khái niệm này có liên quan nhưng không đồng nhất:

| Khái niệm | Ý nghĩa | Ví dụ trong DSL giả định về đơn hàng |
|---|---|---|
| Thuật ngữ miền | Từ gọi tên một khái niệm, hoạt động hoặc quy tắc nghiệp vụ | `customer`, `order`, `shipment`, `refund` |
| Từ khóa của DSL | Từ được ngôn ngữ dành riêng để tạo cấu trúc hoặc chỉ định thao tác | `CREATE`, `WHEN`, `THEN`, `WHERE` |
| Cú pháp (syntax) | Quy tắc kết hợp từ khóa, tên miền, toán tử và giá trị thành biểu thức hợp lệ | `WHEN order.status IS "PAID" THEN shipment.create()` |

Một thuật ngữ miền có thể được dùng làm tên trong DSL, nhưng không nhất thiết phải là từ khóa. Ví dụ, `order` có thể là tên một loại đối tượng miền; `WHEN` là từ khóa điều khiển cấu trúc; dấu `.` và toán tử `IS` góp phần tạo nên cú pháp. Tách bạch các khái niệm giúp người thiết kế biết phần nào phản ánh nghiệp vụ và phần nào chỉ phục vụ việc viết, phân tích hoặc thực thi chương trình.

Ngữ nghĩa (semantics) cũng cần được phân biệt với cú pháp. Cú pháp xác định biểu thức nào được viết đúng cấu trúc; ngữ nghĩa xác định biểu thức đó có ý nghĩa gì và có hợp lệ trong miền hay không. Chẳng hạn, `refund.create(order)` có thể đúng cú pháp nhưng vẫn không hợp lệ về nghiệp vụ nếu đơn hàng chưa được thanh toán hoặc đã bị hoàn tiền toàn bộ. Bộ kiểm tra của DSL cần hiểu quy tắc này nếu muốn phát hiện lỗi sớm.

## Những loại thuật ngữ thường gặp trong một miền

Thuật ngữ miền không chỉ là danh từ. Khi khảo sát một lĩnh vực, cần ghi nhận nhiều loại từ khác nhau vì mỗi loại thể hiện một phần của mô hình.

### Đối tượng và khái niệm

Danh từ thường gọi tên những đối tượng hoặc khái niệm mà hệ thống cần quản lý, ví dụ `Customer`, `Order`, `Product`, `Invoice` hoặc `Shipment`. Một số khái niệm có vòng đời và danh tính riêng; một số khác chỉ biểu diễn giá trị hoặc đặc tính.

Trong mô hình hướng đối tượng hoặc thiết kế miền, có thể gặp các cách phân loại như:

- **Thực thể (entity):** đối tượng có danh tính ổn định trong miền, chẳng hạn một khách hàng hoặc một đơn hàng. Thuộc tính của nó có thể thay đổi trong suốt vòng đời nhưng vẫn là cùng một thực thể.
- **Đối tượng giá trị (value object):** khái niệm được xác định bởi giá trị của nó, chẳng hạn địa chỉ giao hàng, khoảng thời gian hoặc số tiền. Hai đối tượng có cùng giá trị theo quy tắc của miền có thể được xem là tương đương.
- **Tập hợp hoặc nhóm (collection):** một tập các đối tượng được xét cùng nhau, chẳng hạn các dòng hàng trong đơn hàng hoặc danh sách điểm giao của một chuyến.

Đây là những cách phân loại hữu ích khi xây dựng mô hình miền, nhưng không phải mọi DSL đều phải biểu diễn chúng bằng lớp hoặc kiểu dữ liệu có cùng tên. Điều quan trọng là hiểu mỗi thuật ngữ đại diện cho điều gì và những thao tác nào có ý nghĩa với nó.

### Hoạt động và hành động

Động từ thường diễn tả việc người dùng hoặc hệ thống thực hiện, ví dụ `placeOrder`, `cancelOrder`, `capturePayment`, `dispatchShipment` hoặc `issueRefund`. Động từ cần được định nghĩa chính xác vì các từ gần nghĩa có thể biểu thị những hành động khác nhau.

Ví dụ, *đặt hàng* là hành động tạo yêu cầu mua hàng; *xác nhận đơn hàng* có thể là bước kiểm tra và chấp nhận yêu cầu; *thanh toán* là quá trình xử lý nghĩa vụ tiền; *ghi nhận thanh toán* có thể chỉ là lưu kết quả từ một cổng thanh toán. Nếu dùng các từ này thay thế cho nhau, DSL có nguy cơ tạo ra hành vi sai.

### Trạng thái và vòng đời

Tính từ hoặc cụm từ mô tả trạng thái thường cho biết một đối tượng đang ở giai đoạn nào, chẳng hạn `DRAFT`, `PENDING_PAYMENT`, `PAID`, `CANCELLED` hoặc `SHIPPED`. Các trạng thái thường có quan hệ chuyển tiếp: một đơn hàng đang ở trạng thái nháp có thể được gửi đi, nhưng một đơn đã giao có thể không được phép hủy theo cùng quy tắc.

Khi định nghĩa thuật ngữ trạng thái, cần làm rõ:

- Điều kiện để một đối tượng đi vào trạng thái đó.
- Những hành động nào được phép hoặc bị cấm trong trạng thái đó.
- Những trạng thái nào có thể chuyển đến tiếp theo.
- Sự kiện hoặc tác nhân nào làm thay đổi trạng thái.

Không nên chỉ liệt kê tên trạng thái mà bỏ qua ý nghĩa và quy tắc chuyển trạng thái của chúng.

### Thuộc tính, đơn vị và giới hạn

Một số thuật ngữ mô tả thuộc tính của đối tượng, ví dụ `quantity`, `unitPrice`, `weight`, `currency`, `deliveryDate` hoặc `capacity`. Định nghĩa cần chỉ rõ kiểu dữ liệu, đơn vị đo, miền giá trị và cách xử lý giá trị không hợp lệ.

Ví dụ, `weight` có thể được hiểu là gram, kilogram hoặc pound. `amount` có thể là số tiền trước thuế, sau thuế hoặc số tiền đã thanh toán. Nếu không ghi rõ, cùng một biểu thức DSL có thể bị diễn giải khác nhau giữa các nhóm hoặc hệ thống.

### Vai trò và tác nhân

Các thuật ngữ như `buyer`, `seller`, `approver`, `operator` hoặc `carrier` chỉ vai trò của người hay hệ thống tham gia vào quy trình. Một người có thể giữ nhiều vai trò trong các ngữ cảnh khác nhau. Định nghĩa vai trò cần chỉ rõ quyền, trách nhiệm và phạm vi hành động liên quan.

### Quy tắc và điều kiện nghiệp vụ

Các cụm từ như *đơn hàng hợp lệ*, *khách hàng ưu tiên*, *giao hàng miễn phí* hoặc *hạn mức tín dụng* thường là tên gọi ngắn cho một nhóm quy tắc. Ví dụ, “khách hàng ưu tiên” có thể dựa trên hạng thành viên, doanh thu trong một khoảng thời gian hoặc quyết định của bộ phận chăm sóc khách hàng. Khi dùng cụm từ đó trong DSL, cần mô tả tiêu chí xác định thay vì để ý nghĩa phụ thuộc vào suy đoán của người đọc.

## Xây dựng bảng thuật ngữ miền

Bảng thuật ngữ (glossary) là nơi ghi lại cách gọi thống nhất và ý nghĩa của từng khái niệm. Đây có thể là tài liệu riêng, một phần của đặc tả DSL hoặc dữ liệu có cấu trúc được dùng trong công cụ phát triển.

Một mục thuật ngữ nên có những thông tin phù hợp với miền và quy mô dự án:

| Trường thông tin | Nội dung cần ghi |
|---|---|
| Thuật ngữ chuẩn | Tên được thống nhất để dùng trong tài liệu và DSL |
| Định nghĩa | Ý nghĩa chính xác trong phạm vi miền đang xét |
| Loại khái niệm | Đối tượng, hành động, trạng thái, thuộc tính, vai trò hoặc quy tắc |
| Thuật ngữ liên quan | Các khái niệm có quan hệ trực tiếp với thuật ngữ này |
| Thuật ngữ đồng nghĩa hoặc tên cũ | Những cách gọi khác cần nhận diện và quy tắc chuyển đổi sang tên chuẩn |
| Ví dụ và phản ví dụ | Trường hợp minh họa việc dùng đúng hoặc sai thuật ngữ |
| Ràng buộc | Điều kiện, đơn vị, phạm vi giá trị hoặc quy tắc liên quan |
| Nguồn xác nhận | Vai trò hoặc tài liệu nghiệp vụ xác nhận định nghĩa |

Ví dụ rút gọn cho miền thương mại điện tử:

| Thuật ngữ chuẩn | Định nghĩa trong miền | Quan hệ hoặc lưu ý |
|---|---|---|
| Khách hàng (`Customer`) | Chủ thể tạo và quản lý yêu cầu mua hàng | Có thể sở hữu nhiều đơn hàng |
| Đơn hàng (`Order`) | Yêu cầu mua một hoặc nhiều sản phẩm của khách hàng | Có trạng thái, dòng hàng và thông tin thanh toán |
| Dòng hàng (`OrderLine`) | Một mục sản phẩm cùng số lượng trong đơn hàng | Thuộc về một đơn hàng; số lượng phải thỏa quy tắc miền |
| Thanh toán (`Payment`) | Giao dịch dùng để thanh toán một nghĩa vụ của đơn hàng | Có số tiền, phương thức và trạng thái xử lý |
| Hoàn tiền (`Refund`) | Giao dịch trả lại một phần hoặc toàn bộ số tiền đã thu | Phải tham chiếu khoản thanh toán hoặc đơn hàng liên quan |
| Vận đơn (`Shipment`) | Thông tin về việc chuyển hàng đến địa chỉ nhận | Có thể liên quan đến một hoặc nhiều dòng hàng tùy mô hình giao nhận |

Định nghĩa trong bảng chỉ là ví dụ. Mỗi tổ chức cần xác nhận thuật ngữ dựa trên quy trình và chính sách thực tế của mình. Ví dụ, một doanh nghiệp có thể gọi một yêu cầu mua hàng là “đơn đặt hàng” trước khi chấp nhận, trong khi doanh nghiệp khác chỉ dùng “đơn hàng” sau khi đã xác nhận. Sự khác biệt đó ảnh hưởng trực tiếp đến trạng thái và hành động mà DSL cần hỗ trợ.

## Phát hiện và xử lý sự mơ hồ trong thuật ngữ

Một từ trong ngôn ngữ tự nhiên có thể mang nhiều nghĩa. Ngược lại, một khái niệm có thể được gọi bằng nhiều từ khác nhau. Đây là nguồn gây nhầm lẫn phổ biến khi biến ngôn ngữ nghiệp vụ thành từ vựng của DSL.

### Một từ có nhiều nghĩa

Ví dụ, từ “tài khoản” có thể chỉ tài khoản đăng nhập, tài khoản khách hàng hoặc tài khoản kế toán. Nếu DSL dùng `account` mà không xác định ngữ cảnh, biểu thức có thể khó hiểu hoặc dẫn đến truy cập nhầm loại dữ liệu.

Có thể giải quyết bằng cách:

- Dùng tên cụ thể hơn như `UserAccount`, `CustomerAccount` và `LedgerAccount`.
- Đặt thuật ngữ trong ngữ cảnh rõ ràng, chẳng hạn `customer.account` và `ledger.account`.
- Định nghĩa riêng từng nghĩa trong bảng thuật ngữ và chỉ rõ phạm vi sử dụng.

### Một khái niệm có nhiều tên

Các nhóm có thể gọi cùng một khái niệm là “người mua”, “khách mua” hoặc “khách hàng”. Cần xác định các từ đó thực sự đồng nghĩa trong miền hay chỉ gần nghĩa. Nếu là một khái niệm, chọn một tên chuẩn cho DSL và ghi lại các tên khác để hỗ trợ tài liệu, chuyển đổi dữ liệu hoặc tương thích với hệ thống cũ.

### Một từ gần nghĩa nhưng khác quy tắc

“Hủy đơn” và “từ chối đơn” có thể tạo ra kết quả giống nhau ở giao diện, nhưng chủ thể thực hiện và hệ quả nghiệp vụ có thể khác nhau. Người mua có thể hủy yêu cầu của mình; người bán có thể từ chối một yêu cầu chưa được chấp nhận. Nếu gộp cả hai thành `cancel`, hệ thống có thể mất thông tin quan trọng về trách nhiệm và lịch sử xử lý.

### Thuật ngữ phụ thuộc ngữ cảnh

Một thuật ngữ có thể có ý nghĩa khác nhau giữa các bộ phận hoặc các phạm vi nghiệp vụ. Chẳng hạn, “khách hàng đang hoạt động” trong bộ phận bán hàng có thể là người có giao dịch gần đây, còn trong hệ thống xác thực có thể là tài khoản chưa bị khóa. Cần ghi rõ ngữ cảnh áp dụng, tiêu chí và chủ thể chịu trách nhiệm xác nhận định nghĩa.

## Thuật ngữ và ranh giới miền

Không phải mọi thuật ngữ đều có một định nghĩa duy nhất trên toàn bộ tổ chức. Khi nhiều nhóm nghiệp vụ sử dụng cùng một từ với ý nghĩa khác nhau, việc ép họ dùng chung một định nghĩa có thể làm mô hình trở nên thiếu chính xác.

Trong thiết kế hướng miền (Domain-Driven Design), **ngữ cảnh giới hạn (bounded context)** là ranh giới trong đó một mô hình và cách dùng thuật ngữ nhất quán. Ví dụ, từ “sản phẩm” trong danh mục hàng hóa có thể nhấn mạnh tên, mô tả và thuộc tính hiển thị; trong kho vận, mô hình có thể quan tâm đến mã lưu kho, kích thước và trọng lượng; trong kế toán, trọng tâm có thể là cách ghi nhận giá trị và thuế.

Các ngữ cảnh có thể trao đổi dữ liệu với nhau, nhưng không nên mặc định rằng cùng tên có nghĩa là cùng mô hình. Khi DSL phục vụ một ngữ cảnh cụ thể, từ vựng của nó nên phản ánh đúng ngữ cảnh đó. Nếu DSL kết nối nhiều ngữ cảnh, cần xác định rõ cách ánh xạ thuật ngữ và chuyển đổi ý nghĩa giữa chúng.

Sơ đồ khái quát:

```text
Ngữ cảnh Bán hàng                 Ngữ cảnh Kho vận
------------------                -----------------
Product                           StockItem
  - tên hiển thị                    - mã lưu kho
  - giá bán                         - vị trí lưu trữ
  - mô tả                           - số lượng tồn
       |                                  |
       +------ mã sản phẩm / ánh xạ ------+
```

Trong ví dụ, `Product` và `StockItem` có thể liên quan đến cùng một mặt hàng nhưng phục vụ những mô hình và quy tắc khác nhau. Việc ánh xạ giữa chúng cần được định nghĩa rõ, thay vì chỉ đổi tên hai đối tượng cho giống nhau.

## Từ thuật ngữ miền đến mô hình và biểu thức DSL

Thu thập từ ngữ mới chỉ là bước đầu. Để tạo ra DSL có thể phân tích và thực thi, cần xác định mối liên hệ giữa thuật ngữ, cấu trúc dữ liệu, hành động và quy tắc.

Một quy trình thực hiện có thể gồm:

1. **Thu thập cách gọi thực tế:** phỏng vấn chuyên gia, quan sát quy trình, đọc biểu mẫu, báo cáo, hợp đồng và tài liệu đang được sử dụng.
2. **Ghi lại định nghĩa và ngữ cảnh:** với mỗi từ, hỏi nó chỉ đối tượng nào, ai sử dụng, khi nào được dùng và có trường hợp nào mang nghĩa khác không.
3. **Nhóm các thuật ngữ liên quan:** xác định đối tượng, thuộc tính, hành động, trạng thái, vai trò và quy tắc; làm rõ quan hệ giữa chúng.
4. **Tìm điểm mơ hồ:** ghi nhận từ đồng nghĩa, từ đồng âm khác nghĩa, tên viết tắt và những khác biệt giữa các nhóm.
5. **Thống nhất tên chuẩn:** cùng chuyên gia miền chọn từ dễ hiểu, đủ cụ thể và ổn định trong phạm vi đã xác định.
6. **Chuyển thành mô hình:** xác định kiểu dữ liệu, quan hệ, thao tác, trạng thái và điều kiện hợp lệ tương ứng.
7. **Thử diễn đạt bằng DSL:** viết các biểu thức đại diện cho tác vụ thông thường và tình huống biên, sau đó nhờ người dùng miền đọc và xác nhận.
8. **Duy trì bảng thuật ngữ:** quản lý người chịu trách nhiệm, lịch sử thay đổi, thuật ngữ cũ và ảnh hưởng của mỗi lần đổi tên hoặc đổi nghĩa.

Ví dụ, sau khi thống nhất thuật ngữ “đơn hàng”, “thanh toán” và “hoàn tiền”, DSL giả định có thể biểu đạt:

```text
WHEN order.status IS "CONFIRMED"
  AND payment.status IS "CAPTURED"
THEN refund.create(
  order = order,
  amount = 500000,
  reason = "DAMAGED_ITEM"
)
```

Đoạn mã chỉ minh họa cách dùng thuật ngữ. Một DSL thực tế còn phải quy định `CAPTURED` nghĩa là gì, số tiền hoàn có vượt quá số tiền đã thu hay không, đơn vị tiền tệ được xác định ở đâu và ai có quyền tạo yêu cầu hoàn tiền. Những chi tiết này thuộc ngữ nghĩa và quy tắc của miền.

## Nguyên tắc đặt tên thuật ngữ cho DSL

Tên gọi trong DSL cần vừa gần với ngôn ngữ của người dùng miền, vừa đủ rõ để công cụ xử lý nhất quán. Một số nguyên tắc hữu ích:

- **Ưu tiên từ đang được dùng trong công việc:** tên gọi quen thuộc giúp người dùng đọc và xác nhận biểu thức dễ hơn. Tránh tự tạo thuật ngữ kỹ thuật nếu miền đã có từ rõ nghĩa.
- **Một tên chuẩn cho một khái niệm trong cùng ngữ cảnh:** hạn chế việc cùng một khái niệm xuất hiện dưới nhiều tên trong DSL. Có thể lưu bí danh ở lớp chuyển đổi nếu cần tương thích.
- **Tên phải phân biệt được các khái niệm gần nhau:** nếu “người dùng” và “khách hàng” có vai trò khác nhau, không nên đặt cả hai thành `user`.
- **Thể hiện đúng loại ý nghĩa:** tên hành động nên là động từ; tên đối tượng nên là danh từ; trạng thái nên diễn đạt một tình trạng có thể kiểm tra.
- **Tránh tên quá rộng hoặc phụ thuộc cách triển khai:** các từ như `data`, `item`, `process` thường không đủ thông tin nếu không có ngữ cảnh cụ thể.
- **Quy định cách viết nhất quán:** thống nhất chữ hoa, chữ thường, dấu gạch nối, dạng số ít/số nhiều và cách viết tên viết tắt.
- **Cân nhắc ngôn ngữ và bản địa hóa:** nếu người dùng làm việc bằng tiếng Việt nhưng mã nguồn dùng tiếng Anh, cần xác định rõ tên hiển thị, tên trong DSL và quy tắc ánh xạ; không để hai bộ thuật ngữ phát triển lệch nhau.
- **Kiểm tra khả năng đọc thành câu:** thử đọc biểu thức như một yêu cầu nghiệp vụ. Nếu người dùng miền hiểu sai, tên hoặc cấu trúc cần được điều chỉnh.

Tên rõ ràng vẫn cần định nghĩa chính xác. Một thuật ngữ nghe quen thuộc không có nghĩa mọi người đều hiểu giống nhau; bảng thuật ngữ và ví dụ sử dụng mới là căn cứ thống nhất.

## Duy trì thuật ngữ khi miền thay đổi

Miền nghiệp vụ không đứng yên. Sản phẩm mới, quy định mới, quy trình mới hoặc việc sáp nhập hệ thống có thể làm xuất hiện khái niệm mới và thay đổi ý nghĩa của khái niệm cũ. Vì DSL dựa trên từ vựng miền, những thay đổi này cần được quản lý có chủ đích.

Khi thay đổi một thuật ngữ, cần xác định đó là:

- **Đổi tên:** khái niệm và quy tắc giữ nguyên, chỉ thay cách gọi. Có thể hỗ trợ tên cũ trong một khoảng thời gian và thông báo cách chuyển đổi.
- **Tách khái niệm:** một thuật ngữ cũ được chia thành nhiều khái niệm cụ thể hơn. Cần xác định dữ liệu và biểu thức cũ ánh xạ sang khái niệm mới ra sao.
- **Gộp khái niệm:** nhiều thuật ngữ được xác định là cùng một khái niệm trong ngữ cảnh mới. Cần kiểm tra các quy tắc cũ có thực sự tương đương không.
- **Thay đổi định nghĩa:** tên giữ nguyên nhưng điều kiện hoặc ý nghĩa thay đổi. Đây thường là thay đổi có ảnh hưởng lớn vì biểu thức cũ vẫn có thể hợp cú pháp nhưng cho kết quả khác.
- **Loại bỏ thuật ngữ:** khái niệm không còn được sử dụng. Cần xác định thời điểm ngừng hỗ trợ và cách xử lý tài liệu hoặc cấu hình cũ.

Quản lý phiên bản bảng thuật ngữ, đặc tả DSL và bộ thực thi giúp nhóm biết một biểu thức được hiểu theo bộ quy tắc nào. Với thay đổi có ảnh hưởng đến kết quả nghiệp vụ, cần có tài liệu chuyển đổi và kiểm thử các trường hợp sử dụng hiện có.

## Kết luận

Thuật ngữ miền là vốn từ vựng phản ánh cách một lĩnh vực gọi tên đối tượng, hoạt động, trạng thái, thuộc tính, vai trò và quy tắc của nó. Trong DSL, những thuật ngữ này tạo nên lớp ngôn ngữ gần với công việc thực tế của người dùng. Chúng chỉ phát huy tác dụng khi được định nghĩa rõ, đặt trong đúng ranh giới ngữ cảnh, phân biệt với từ khóa và cú pháp, đồng thời được duy trì khi nghiệp vụ thay đổi.

Một bảng thuật ngữ tốt giúp chuyên gia miền và người phát triển cùng hiểu một khái niệm theo một cách thống nhất. Từ nền tảng đó, nhóm có thể xây dựng mô hình, cú pháp và ngữ nghĩa DSL sao cho biểu thức vừa dễ đọc đối với con người vừa đủ chính xác để công cụ kiểm tra và thực thi.
