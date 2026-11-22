# DSL là gì và giải quyết bài toán nào?

DSL là viết tắt của **Domain-Specific Language**, thường được dịch là **ngôn ngữ chuyên biệt theo miền**. Đây là ngôn ngữ được thiết kế để mô tả một nhóm vấn đề tương đối hẹp bằng những khái niệm gần với lĩnh vực đó. SQL tập trung vào truy vấn dữ liệu quan hệ, regular expression tập trung vào mô tả mẫu văn bản, còn CSS tập trung vào cách trình bày giao diện.

Ý tưởng cốt lõi của DSL là giúp người viết diễn đạt trực tiếp điều họ muốn làm trong một miền cụ thể. Thay vì phải mô tả mọi bước bằng các cấu trúc lập trình tổng quát, người viết có thể dùng những từ khóa, quy tắc và cấu trúc được thiết kế riêng cho công việc đó.

## 1. Vì sao cần ngôn ngữ chuyên biệt?

Các ngôn ngữ mục đích tổng quát như Python, Java, C# hay JavaScript có thể giải quyết rất nhiều loại bài toán. Chúng cung cấp biến, kiểu dữ liệu, hàm, vòng lặp, điều kiện, cấu trúc dữ liệu và nhiều cơ chế khác. Tính linh hoạt này rất hữu ích khi xây dựng ứng dụng, nhưng đôi khi khiến một quy tắc nghiệp vụ đơn giản phải được diễn đạt qua nhiều chi tiết kỹ thuật.

Ví dụ, một cửa hàng có chính sách tính phí giao hàng:

- Đơn hàng từ 1.000.000 đồng được miễn phí giao hàng.
- Đơn hàng thấp hơn mức đó có phí cơ bản 30.000 đồng.
- Địa chỉ thuộc khu vực xa được cộng thêm 15.000 đồng.

Trong một ngôn ngữ mục đích tổng quát, lập trình viên có thể viết các câu lệnh điều kiện để tính khoản phí. Cách làm này hoàn toàn hợp lệ. Tuy nhiên, khi có nhiều chính sách, các điều kiện có thể nằm rải rác trong nhiều hàm hoặc dịch vụ. Người phụ trách nghiệp vụ phải hiểu cách tổ chức mã nguồn mới có thể kiểm tra một thay đổi. Những quy tắc tương tự cũng có nguy cơ được viết lại ở nhiều nơi và dần cho kết quả không nhất quán.

Vấn đề nằm ở khoảng cách giữa cách chuyên gia miền mô tả công việc và cách chương trình tổng quát phải biểu diễn công việc đó. DSL được tạo ra để thu hẹp khoảng cách này.

## 2. DSL là gì?

DSL là một ngôn ngữ có **phạm vi sử dụng được giới hạn có chủ đích**. Từ vựng, cấu trúc và quy tắc của nó xoay quanh một miền, chẳng hạn truy vấn dữ liệu, mô tả giao diện, cấu hình hạ tầng, định tuyến mạng, tính giá hoặc kiểm tra quyền truy cập.

Một DSL thường có những đặc điểm sau:

1. **Có miền mục tiêu rõ ràng.** Người thiết kế có thể nói DSL dùng để truy vấn dữ liệu, mô tả quy tắc tính phí hay định nghĩa quy trình triển khai.
2. **Dùng khái niệm của miền.** Cú pháp có thể chứa các từ khóa và tên gọi gần với nghiệp vụ, chẳng hạn `SELECT`, `FROM`, `WHERE`, `margin`, `route`, `resource` hoặc `permission`, tùy lĩnh vực.
3. **Có cú pháp và ngữ nghĩa xác định.** Cú pháp quy định biểu thức nào hợp lệ; ngữ nghĩa quy định một biểu thức hợp lệ có ý nghĩa gì và được xử lý ra sao.
4. **Có cách kiểm tra hoặc thực thi.** Một công cụ có thể phân tích, xác thực, diễn giải, biên dịch hoặc chuyển DSL thành dạng mà hệ thống khác xử lý được.

Không có một danh sách tính năng bắt buộc để một ngôn ngữ được gọi là DSL. Điểm quan trọng nhất là nó được tối ưu cho một miền cụ thể, thay vì hướng tới mọi loại bài toán.

### DSL và ngôn ngữ mục đích tổng quát

| Khía cạnh | Ngôn ngữ mục đích tổng quát | DSL |
|---|---|---|
| Phạm vi | Có thể dùng cho nhiều loại bài toán | Tập trung vào một miền hoặc một nhóm tác vụ |
| Khái niệm | Cung cấp các cấu trúc lập trình tổng quát | Cung cấp khái niệm gần với nghiệp vụ của miền |
| Người dùng chính | Thường là lập trình viên | Có thể gồm lập trình viên và chuyên gia miền, tùy thiết kế |
| Mức độ linh hoạt | Rộng, có thể biểu đạt nhiều kiểu thuật toán | Hẹp hơn, ưu tiên cách diễn đạt phù hợp với miền |
| Ví dụ | Python, Java, C# | SQL, regular expressions, CSS, HCL dùng trong Terraform |

DSL không nhất thiết phải ngắn hơn trong mọi trường hợp. Giá trị của nó nằm ở việc biểu thức trở nên phù hợp và dễ hiểu hơn đối với công việc cụ thể.

## 3. Những ví dụ quen thuộc về DSL

| DSL | Miền sử dụng | Điều người viết mô tả |
|---|---|---|
| SQL | Cơ sở dữ liệu quan hệ | Dữ liệu cần đọc, lọc, kết hợp, nhóm hoặc cập nhật |
| Regular expressions (regex) | Xử lý văn bản | Mẫu ký tự cần tìm hoặc kiểm tra |
| CSS | Trình bày giao diện web | Quy tắc về màu sắc, bố cục, phông chữ và trạng thái hiển thị |
| HCL trong Terraform | Hạ tầng dưới dạng mã | Tài nguyên hạ tầng, thuộc tính và quan hệ giữa chúng |
| Ngôn ngữ công thức bảng tính | Tính toán trên bảng | Công thức và quan hệ giữa các ô dữ liệu |
| Cú pháp workflow của GitHub Actions | Tự động hóa quy trình phát triển phần mềm | Sự kiện kích hoạt, công việc và các bước trong quy trình |

Ví dụ một truy vấn SQL:

```sql
SELECT customer_id, SUM(total) AS revenue
FROM orders
WHERE status = 'paid'
GROUP BY customer_id
ORDER BY revenue DESC;
```

Đoạn SQL trên diễn đạt trực tiếp các ý niệm của miền dữ liệu: chọn cột, lấy dữ liệu từ bảng, lọc đơn hàng đã thanh toán, nhóm theo khách hàng và sắp xếp doanh thu. Người viết không phải tự mô tả cách duyệt từng bản ghi, tổ chức bộ nhớ hay triển khai thuật toán nhóm. Hệ quản trị cơ sở dữ liệu đảm nhận các chi tiết thực thi.

Với CSS, người viết khai báo phần tử nào cần có kiểu trình bày nào. Với regex, người viết mô tả cấu trúc của chuỗi cần khớp. Mỗi ngôn ngữ đều thu hẹp cách diễn đạt để tập trung vào một nhiệm vụ.

**Lưu ý:** YAML và JSON tự thân chủ yếu là định dạng biểu diễn dữ liệu, không tự động trở thành DSL. Tuy nhiên, khi một hệ thống quy định một tập trường, cấu trúc, kiểu giá trị và ý nghĩa nghiệp vụ cụ thể trên YAML hoặc JSON, tài liệu cấu hình đó có thể đóng vai trò như một DSL. Chẳng hạn, cú pháp workflow của GitHub Actions được biểu diễn bằng YAML, nhưng ý nghĩa của `jobs`, `steps` và `on` đến từ mô hình workflow mà nền tảng định nghĩa.

## 4. DSL giải quyết những bài toán nào?

### 4.1. Thu hẹp khoảng cách giữa nghiệp vụ và mã nguồn

DSL có thể dùng từ vựng mà người trong lĩnh vực đã quen thuộc. Một chuyên gia dữ liệu thường hiểu `SELECT`, `JOIN` và `GROUP BY`; người làm giao diện hiểu selector và thuộc tính CSS; người vận hành hạ tầng hiểu tài nguyên máy chủ, mạng và lưu trữ.

Khi quy tắc được viết bằng các khái niệm này, người đọc có thể tập trung vào ý nghĩa của quy tắc thay vì phải giải mã nhiều chi tiết triển khai. Điều đó giúp trao đổi giữa chuyên gia miền và lập trình viên rõ ràng hơn. Mức độ dễ tiếp cận còn phụ thuộc vào cách thiết kế cú pháp và công cụ hỗ trợ; không phải DSL nào cũng phù hợp với người không lập trình.

### 4.2. Giảm phần mã lặp lại cho một loại công việc

Nếu một nhóm tác vụ xuất hiện thường xuyên, DSL có thể cung cấp sẵn các cấu trúc biểu đạt đúng với tác vụ đó. Người viết chỉ nêu thông tin hoặc quy tắc cần thiết, còn bộ xử lý DSL đảm nhận phần công việc chung.

Ví dụ, thay vì mỗi nhóm tự viết mã để lọc, sắp xếp và phân trang dữ liệu theo cùng một mẫu, một hệ thống có thể cung cấp DSL truy vấn với các toán tử đã được định nghĩa. Cách này giảm mã lặp và giúp các truy vấn có cấu trúc nhất quán.

### 4.3. Giới hạn những gì người dùng có thể yêu cầu

Vì DSL chỉ hỗ trợ một tập cú pháp và thao tác nhất định, hệ thống có thể từ chối các biểu thức nằm ngoài phạm vi. Một DSL tính giá có thể cho phép so sánh số tiền, kiểm tra khu vực và cộng phụ phí, nhưng không cần cho phép người viết mở tệp tùy ý hoặc truy cập mạng.

Giới hạn này giúp xác thực quy tắc sớm hơn và giảm những hành động ngoài ý muốn. Nó cũng có thể tạo ranh giới an toàn tốt hơn khi DSL được dùng để nhận biểu thức từ người dùng hoặc hệ thống bên ngoài. Dù vậy, một DSL vẫn cần được kiểm soát quyền, giới hạn tài nguyên và kiểm tra đầu vào phù hợp; cú pháp hẹp không tự động bảo đảm an toàn.

### 4.4. Tách quy tắc miền khỏi chương trình xử lý

Một ứng dụng có thể cung cấp bộ máy thực thi ổn định, trong khi các quy tắc thay đổi thường xuyên được lưu dưới dạng DSL. Ví dụ, dịch vụ tính phí giao hàng đọc các quy tắc về mức phí, ngưỡng miễn phí và khu vực phụ thu. Khi chính sách thay đổi, người quản trị có thể cập nhật quy tắc theo quy trình được kiểm soát mà không phải sửa trực tiếp thuật toán nền tảng.

Việc tách này có ích khi quy tắc thay đổi độc lập với mã chương trình. Nó không có nghĩa mọi thay đổi đều không cần lập trình viên: nếu miền nghiệp vụ thay đổi căn bản hoặc DSL chưa hỗ trợ một loại quy tắc mới, bộ xử lý DSL vẫn cần được mở rộng.

### 4.5. Tăng tính nhất quán và khả năng kiểm tra

Khi mọi quy tắc được viết theo cùng một ngôn ngữ, hệ thống có thể áp dụng cùng cách xác thực kiểu dữ liệu, kiểm tra trường bắt buộc, phát hiện tên không hợp lệ và báo lỗi theo vị trí. Các quy tắc cũng dễ được lưu phiên bản, xem xét, kiểm thử và so sánh hơn nếu DSL có công cụ hỗ trợ phù hợp.

## 5. Ví dụ: mô tả chính sách giao hàng bằng DSL

Giả sử ứng dụng cần áp dụng ba quy tắc đã nêu: phí cơ bản 30.000 đồng cho đơn hàng dưới 1.000.000 đồng, miễn phí cho đơn hàng đạt ngưỡng, và cộng 15.000 đồng nếu địa chỉ ở khu vực xa.

Một DSL minh họa có thể viết như sau:

```text
RULE standard_shipping
  WHEN order.subtotal < 1_000_000
  SET shipping.fee = 30_000

RULE free_shipping
  WHEN order.subtotal >= 1_000_000
  SET shipping.fee = 0

RULE remote_area_surcharge
  WHEN destination.zone == "remote"
  ADD 15_000 TO shipping.fee
```

Đây là cú pháp giả định để minh họa ý tưởng, không phải ngôn ngữ có sẵn. Để đoạn DSL có thể thực thi đúng, hệ thống phải định nghĩa rõ ngữ nghĩa của nó. Trong ví dụ này, ta giả định các quy tắc được đánh giá theo thứ tự xuất hiện; mọi quy tắc có điều kiện đúng đều được áp dụng; `SET` gán giá trị và `ADD` cộng vào giá trị hiện tại. Hai quy tắc đầu thiết lập phí cơ bản, còn quy tắc cuối cộng phụ phí nếu phù hợp.

Cùng chính sách đó có thể được viết bằng Python:

```python
def calculate_shipping_fee(order, destination):
    if order.subtotal >= 1_000_000:
        fee = 0
    else:
        fee = 30_000

    if destination.zone == "remote":
        fee += 15_000

    return fee
```

Cả hai cách đều có thể biểu đạt cùng kết quả. Điểm khác biệt là đoạn Python mô tả trực tiếp các bước điều khiển chương trình, còn DSL dùng các khái niệm `RULE`, `WHEN`, `SET` và `ADD` của miền chính sách giao hàng. Nếu nhân viên nghiệp vụ thường xuyên xem xét hoặc chỉnh sửa các quy tắc, cách biểu đạt DSL có thể dễ trao đổi hơn.

Để xử lý đoạn DSL, một hệ thống thường thực hiện các bước như sau:

1. **Phân tích cú pháp:** đọc văn bản và kiểm tra cấu trúc có đúng ngữ pháp hay không.
2. **Kiểm tra ngữ nghĩa:** xác nhận các tên như `order.subtotal` và `shipping.fee` tồn tại, kiểu dữ liệu phù hợp, toán tử được phép dùng và quy tắc không mâu thuẫn với các ràng buộc đã định nghĩa.
3. **Tạo biểu diễn trung gian:** chuyển biểu thức thành cấu trúc dữ liệu, chẳng hạn cây cú pháp trừu tượng (AST), để chương trình có thể xử lý.
4. **Đánh giá hoặc chuyển đổi:** chạy các điều kiện và hành động theo ngữ nghĩa đã quy định, hoặc biên dịch chúng sang một dạng khác.
5. **Trả kết quả và thông tin lỗi:** cung cấp kết quả tính phí hoặc chỉ ra quy tắc nào sai, sai ở đâu và vì sao.

Ví dụ này cho thấy DSL không tự hoạt động chỉ vì cú pháp trông giống ngôn ngữ tự nhiên. Cần có một bộ phân tích và bộ xử lý hiểu chính xác các cấu trúc của nó.

## 6. Các cách phân loại DSL

Có hai cách phân loại thường gặp. Chúng mô tả hai khía cạnh khác nhau nên không loại trừ lẫn nhau.

### 6.1. DSL bên ngoài và DSL nhúng

- **DSL bên ngoài (external DSL):** có cú pháp riêng, thường được phân tích bởi parser hoặc công cụ chuyên dụng. SQL và regex là những ví dụ quen thuộc. Cú pháp của chúng không cần tuân theo cú pháp của một ngôn ngữ lập trình chủ.
- **DSL nhúng (embedded hoặc internal DSL):** được biểu đạt bên trong một ngôn ngữ chủ, tận dụng cú pháp và cơ chế của ngôn ngữ đó. Một DSL nhúng có thể dùng chuỗi lời gọi hàm, toán tử hoặc cấu trúc khối để tạo cách viết gần với ngôn ngữ riêng.

DSL bên ngoài cho phép kiểm soát cú pháp độc lập nhưng thường cần xây dựng parser, trình soạn thảo và công cụ gỡ lỗi. DSL nhúng có thể tận dụng hệ sinh thái của ngôn ngữ chủ, nhưng cú pháp và trải nghiệm viết bị giới hạn phần nào bởi ngôn ngữ đó.

### 6.2. DSL khai báo và DSL mệnh lệnh

- **Khai báo (declarative):** mô tả kết quả, trạng thái hoặc điều kiện mong muốn; bộ xử lý quyết định cách đạt được chúng. SQL thường được xem là khai báo vì truy vấn nêu dữ liệu cần lấy mà không yêu cầu người viết chỉ rõ từng bước duyệt dữ liệu.
- **Mệnh lệnh (imperative):** mô tả các bước hoặc hành động theo trình tự. Một DSL tự động hóa có thể cung cấp các lệnh để thực hiện từng bước của quy trình.

Không nên đồng nhất hai cặp khái niệm. “Bên ngoài hay nhúng” nói về cách DSL được tích hợp và viết; “khai báo hay mệnh lệnh” nói về cách mô tả hành vi. Một DSL bên ngoài có thể mang tính khai báo hoặc mệnh lệnh.

## 7. DSL khác gì tệp cấu hình, API và framework?

Các khái niệm này có thể liên quan nhưng không đồng nghĩa:

| Khái niệm | Vai trò | Quan hệ với DSL |
|---|---|---|
| Tệp cấu hình | Lưu các giá trị và lựa chọn để điều chỉnh một chương trình | Có thể chỉ là dữ liệu đơn giản; nếu có cú pháp và ngữ nghĩa chuyên biệt để mô tả quy tắc miền, nó có thể hoạt động như DSL |
| API | Cung cấp thao tác hoặc điểm truy cập để phần mềm khác sử dụng | Một API dạng fluent có thể tạo thành DSL nhúng, nhưng mọi API không phải DSL |
| Framework | Cung cấp cấu trúc và cơ chế để xây dựng ứng dụng | Framework có thể đi kèm DSL, nhưng bản thân framework không nhất thiết là ngôn ngữ |
| Ngôn ngữ mục đích tổng quát | Cung cấp công cụ để xây dựng nhiều loại chương trình | Có thể được dùng để triển khai DSL hoặc nhúng DSL, nhưng phạm vi của nó rộng hơn |

Vì vậy, không nên gọi mọi tệp YAML, JSON hay mọi đoạn cấu hình là DSL. Cần xem cấu trúc đó có một mô hình miền, các quy tắc hợp lệ và ngữ nghĩa được định nghĩa hay không.

## 8. Khi nào nên xây dựng hoặc sử dụng DSL?

DSL thường đáng cân nhắc khi:

- Một nhóm quy tắc hoặc tác vụ thuộc cùng miền xuất hiện lặp đi lặp lại.
- Người dùng cần diễn đạt quy tắc bằng khái niệm nghiệp vụ thay vì chi tiết triển khai.
- Có một tập thao tác tương đối ổn định và có thể xác định rõ biểu thức hợp lệ.
- Nhiều người hoặc nhiều hệ thống cần đọc, kiểm tra hay chia sẻ cùng một quy tắc.
- Việc giới hạn quyền biểu đạt giúp giảm lỗi hoặc kiểm soát các hành động mà người dùng được phép yêu cầu.

Ngược lại, DSL có thể không phù hợp khi bài toán chỉ có một vài quy tắc đơn giản, khi yêu cầu thay đổi liên tục đến mức ngôn ngữ phải sửa thường xuyên, hoặc khi ngôn ngữ mục đích tổng quát đã diễn đạt rõ ràng và dễ bảo trì. Nếu phải xây dựng parser, trình gỡ lỗi, tài liệu và công cụ triển khai phức tạp chỉ để thay thế vài câu lệnh thông thường, chi phí có thể lớn hơn lợi ích.

### Một số câu hỏi trước khi chọn DSL

1. Miền bài toán có đủ rõ để xác định từ vựng và các thao tác hợp lệ không?
2. Những người cần đọc hoặc chỉnh sửa quy tắc có hiểu được các khái niệm mà DSL cung cấp không?
3. DSL có giúp giảm lỗi, giảm lặp lại hoặc tăng khả năng kiểm tra một cách đo lường được không?
4. Ai chịu trách nhiệm phát triển, bảo trì, kiểm thử và quản lý phiên bản của DSL?
5. Khi cú pháp sai hoặc quy tắc xung đột, hệ thống có thể giải thích lỗi đủ rõ để người dùng sửa không?

## 9. Những chi phí và giới hạn cần tính đến

DSL làm cho một miền dễ diễn đạt hơn, nhưng việc tạo ra ngôn ngữ cũng tạo thêm một lớp phần mềm cần duy trì.

- **Chi phí thiết kế:** phải chọn từ vựng, cú pháp, kiểu dữ liệu, thứ tự ưu tiên và ngữ nghĩa cho từng cấu trúc. Một cú pháp dễ đọc nhưng ngữ nghĩa mơ hồ sẽ gây lỗi khó tìm.
- **Chi phí công cụ:** parser, bộ kiểm tra, trình định dạng, tô màu cú pháp, tự động hoàn thành, tài liệu và công cụ gỡ lỗi đều có thể cần thiết khi DSL được sử dụng rộng rãi.
- **Khả năng biểu đạt có giới hạn:** thao tác nằm ngoài phạm vi DSL có thể cần mở rộng ngôn ngữ hoặc gọi đến chương trình chủ. Nếu liên tục thêm tính năng tổng quát, DSL có thể trở nên khó hiểu và mất lợi thế ban đầu.
- **Quản lý thay đổi:** thay đổi cú pháp hoặc ngữ nghĩa có thể làm hỏng các quy tắc cũ. Cần có phiên bản, quy tắc tương thích và lộ trình chuyển đổi khi DSL được dùng trong nhiều hệ thống.
- **Kiểm soát thực thi:** cần giới hạn quyền truy cập, thời gian chạy và tài nguyên nếu biểu thức có thể kích hoạt hành động hoặc xử lý dữ liệu lớn.

Khi thiết kế DSL, nên bắt đầu từ các tình huống thực tế trong miền và chỉ đưa vào những cấu trúc cần thiết. Mỗi cấu trúc cần có ý nghĩa nhất quán, thông báo lỗi dễ hiểu và ví dụ kiểm thử. Một ngôn ngữ nhỏ nhưng có quy tắc rõ ràng thường hữu ích hơn một ngôn ngữ có quá nhiều tính năng mà người dùng khó dự đoán.

## 10. Kết luận

DSL là ngôn ngữ được thiết kế để giải quyết hiệu quả một nhóm bài toán thuộc miền cụ thể. Nó giúp diễn đạt quy tắc bằng khái niệm gần với lĩnh vực, giảm phần chi tiết lập trình lặp lại, giới hạn các thao tác được phép và tạo điều kiện để kiểm tra quy tắc nhất quán.

DSL phù hợp khi lợi ích của cách diễn đạt chuyên biệt lớn hơn chi phí thiết kế và duy trì ngôn ngữ cùng bộ công cụ của nó. Khi đánh giá một DSL, hãy bắt đầu từ câu hỏi: **ngôn ngữ này giúp ai diễn đạt công việc nào rõ ràng hơn, và bộ xử lý sẽ bảo đảm ý nghĩa của biểu thức đó ra sao?**
