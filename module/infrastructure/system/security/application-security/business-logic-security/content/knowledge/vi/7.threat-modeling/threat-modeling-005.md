# Lựa chọn biện pháp kiểm soát — Control selection

## 1. Chọn kiểm soát từ kết quả cần ngăn

Trong chương **Threat Modeling** của học phần **Business Logic Security**, lựa chọn kiểm soát là bước chuyển một mô hình đe dọa thành cơ chế có thể triển khai và kiểm chứng.

Một danh sách như “thêm xác thực, validation, rate limit và log” chưa cho biết hệ thống sẽ ngăn được điều gì. Mỗi biện pháp cần nối được với actor, đường lạm dụng, tài sản và business invariant cụ thể.

Ví dụ, nếu hai yêu cầu hoàn tiền cùng vượt ngân sách, xác thực tốt hơn không tự giải quyết cạnh tranh. Nếu khách hàng có thể chọn đơn của người khác, một transaction nguyên tử cũng không tự tạo quyền truy cập đúng. Nếu worker gửi lại lệnh tài chính, ẩn nút trên giao diện không ngăn tác động trùng.

**Một kiểm soát phù hợp phải chặn, giới hạn, phát hiện hoặc hỗ trợ phục hồi một phần xác định của chuỗi lạm dụng, tại nơi có đủ thẩm quyền và dữ kiện.**

Sau bài này, bạn cần có khả năng:

- Chuyển threat và invariant thành yêu cầu kiểm soát có thể kiểm chứng.
- Phân biệt kiểm soát phòng ngừa, phát hiện, giới hạn tác động và phục hồi.
- So sánh các phương án thay vì chọn theo tên công nghệ.
- Đặt kiểm soát đúng ranh giới dữ liệu, quyền và transaction.
- Xác định bằng chứng hiệu lực, hành vi khi lỗi và phần rủi ro còn lại.

## 2. Đầu vào cần có trước khi chọn giải pháp

Không cần hoàn thành một tài liệu rất lớn trước khi bắt đầu. Tuy nhiên, phải biết ít nhất những dữ kiện sau.

| Đầu vào | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Tài sản | Điều gì có thể bị mất, tạo sai hoặc sử dụng ngoài quyền? | Tiền, tồn kho, dữ liệu, thẩm quyền phê duyệt |
| Actor | Ai bắt đầu với quyền và khả năng nào? | Khách đã đăng nhập, nhân viên, service account |
| Luồng hợp lệ | Các bước và quyết định cần có là gì? | Gửi hồ sơ, duyệt, giữ ngân sách, hoàn tiền |
| Đường lạm dụng | Actor thay đổi gì trong giá trị, đối tượng, thứ tự hoặc số lần? | Đổi payment, bỏ duyệt, gửi song song, retry |
| Invariant | Điều kiện nào phải luôn đúng tại các mốc được chấp nhận? | Tổng đã hoàn và đang giữ không vượt ngân sách |
| Ranh giới tin cậy | Dữ kiện đi từ đâu tới đâu và ai có thẩm quyền quyết định? | Browser vào API, worker vào nhà cung cấp |
| Kiểm soát hiện hữu | Cái gì đã thực sự chặn hoặc giới hạn? | Khóa duy nhất, kiểm tra quan hệ, ngân sách cứng |
| Ràng buộc triển khai | Kiến trúc và điều kiện vận hành là gì? | Nhiều instance, queue, cơ sở dữ liệu chung, dịch vụ ngoài |

Một đề xuất “dùng khóa” chưa đủ nếu không biết cần khóa hồ sơ nào, có đường ghi nào không dùng khóa và liệu tài nguyên bị tranh chấp có nằm trong cùng cơ sở dữ liệu hay không.

Một đề xuất “dùng idempotency” cũng chưa đủ nếu chưa biết ý định nghiệp vụ được định danh bằng gì và khóa mới có tạo lại cùng quyền lợi hay không.

### 2.1. Viết yêu cầu kiểm soát trước tên công nghệ

Thay vì bắt đầu bằng:

~~~text
Dùng Redis.
Thêm annotation transaction.
Dùng CAPTCHA.
~~~

Hãy viết:

~~~text
Hai request không được cùng tiêu thụ phần ngân sách còn lại.
Một quyết định hoàn chỉ được tạo một lệnh tài chính.
Actor không có quan hệ hợp lệ không được tác động lên hồ sơ.
Quyết định duyệt phải khớp nội dung được thực thi.
~~~

Sau đó mới chọn primitive phù hợp. Một yêu cầu có thể có nhiều cách hiện thực; một công nghệ có thể không đáp ứng đủ yêu cầu nếu đặt sai chỗ.

### 2.2. Phân biệt điều chưa biết về nghiệp vụ và điều chưa biết về kỹ thuật

Nếu chưa rõ người mua có được hoàn phí giao hàng hay không, cần làm rõ chính sách. Không thể chọn một phép tính đúng khi chưa biết quyền lợi được phép.

Nếu chính sách đã rõ nhưng chưa biết mức cô lập hiện tại có giữ invariant dưới cạnh tranh hay không, cần kiểm chứng kỹ thuật. Không tự đổi chính sách để né một hạn chế triển khai mà chưa có quyết định của người sở hữu nghiệp vụ.

## 3. Bốn vai trò của kiểm soát

| Vai trò | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Phòng ngừa | Chặn đường tạo kết quả bị cấm | Quyền theo đối tượng, chuyển trạng thái có điều kiện, giữ ngân sách nguyên tử |
| Giới hạn tác động | Giảm phạm vi hoặc mức tổn thất khi một phần bị vượt qua | Hạn mức giá trị, phạm vi tenant, ngân sách chiến dịch |
| Phát hiện | Nhận biết dấu hiệu hoặc sai lệch | Cảnh báo số dư không khớp sổ, tác vụ dùng quyết định hết hiệu lực |
| Phục hồi | Đưa dữ liệu và quy trình về trạng thái được giải thích và xử lý đúng | Đối soát, giao dịch điều chỉnh, xử lý lệnh chưa rõ kết quả |

Một kiểm soát có thể có nhiều vai trò. Cần nói rõ phần hiệu lực được kỳ vọng, không coi mọi lợi ích là chặn hoàn toàn.

Ví dụ:

- Log có thể chứng minh ai đã thay đổi số tiền, nhưng không tự ngăn tiền rời hệ thống.
- Rate limit có thể làm chậm việc tạo hồ sơ, nhưng không bảo đảm tổng tiền đúng.
- Phê duyệt thủ công có thể đánh giá điều kiện kinh doanh, nhưng không tự ngăn hai worker thực thi cùng quyết định.
- Đối soát có thể tìm sai lệch tiền, nhưng không thu hồi được mọi dữ liệu đã tiết lộ.

### 3.1. Một bộ kiểm soát cần đóng được chuỗi lạm dụng

Có thể biểu diễn chuỗi như sau:

~~~text
actor có khả năng gọi
  -> chọn đối tượng hoặc dữ kiện
  -> vượt một điều kiện
  -> hệ thống tạo quyết định sai
  -> quyết định tạo tác động
~~~

Một kiểm soát có thể cắt chuỗi ở nhiều điểm. Tuy nhiên, phải kiểm tra các đường thay thế: API cũ, batch, job nền, công cụ quản trị và cập nhật trực tiếp.

Nếu chỉ một controller kiểm tra ngân sách nhưng worker khác ghi trực tiếp, chuỗi vẫn có đường đi. Tạo một hàm dùng chung không chứng minh mọi caller đã sử dụng nó.

### 3.2. Nhiều lớp chỉ có giá trị khi có mục tiêu rõ

Không cần thêm mọi kiểm soát có thể nghĩ ra. Mỗi lớp nên giảm một đường bỏ qua, giới hạn một tác động hoặc cung cấp bằng chứng cần thiết.

Hai hàm cùng đọc một cờ sai từ cache không tạo hai lớp độc lập. Một kiểm tra ở API và một ràng buộc tại dữ liệu có thể bổ sung cho nhau nếu ràng buộc thật sự giữ được thuộc tính quan trọng.

Sự độc lập cần xét theo nguồn dữ liệu, quyền sửa và kiểu lỗi. Nếu cùng một tham số `force` có thể tắt cả hai lớp, lợi ích chống bỏ qua sẽ thấp hơn dự kiến.

## 4. Tình huống xuyên suốt: lựa chọn kiểm soát cho hoàn tiền

Xét một hệ thống giả định:

- Khách hàng thuộc tenant T1 tạo hồ sơ đề nghị hoàn.
- Một bước phê duyệt xác nhận hồ sơ đủ điều kiện theo chính sách.
- Phê duyệt chưa tự giữ ngân sách tài chính; khi tiếp nhận thực thi vẫn phải kiểm tra ngân sách hiện tại.
- Có nhiều instance ứng dụng và nhiều worker.
- Hồ sơ, ngân sách, lệnh hoàn và outbox nằm trong cùng cơ sở dữ liệu hỗ trợ transaction.
- Lệnh hoàn được gửi tới một nhà cung cấp bên ngoài.

Giả sử một khoản thanh toán có:

~~~text
Ngân sách được hoàn C:       1.000.000 VND
Đã hoàn thành công S:          200.000 VND
Đang giữ cho lệnh chờ P:       300.000 VND
Còn có thể giữ mới:            500.000 VND
~~~

Hai hồ sơ đã qua bước đánh giá điều kiện, mỗi hồ sơ đề nghị thực thi 450.000 VND. Chúng không được mặc nhiên cùng thắng: việc đủ điều kiện riêng không cấp quyền vượt ngân sách chung.

Với khoản mới R:

~~~text
R > 0
S >= 0
P >= 0
S + P + R <= C
~~~

Đây là invariant cấp thanh toán, chưa thay thế giới hạn theo dòng hàng, số lượng, phân bổ giảm giá hoặc người nhận.

### 4.1. Các threat cần được phân biệt

| ID | Threat | Kết quả bị cấm |
| --- | --- | --- |
| T1 | Caller thay hồ sơ hoặc khoản thanh toán | Tác động lên đối tượng ngoài quyền hoặc sai quan hệ |
| T2 | Caller tự đặt số tiền hoặc sửa nội dung sau duyệt | Thực thi quyền lợi chưa được cho phép |
| T3 | Gọi bước thực thi khi chưa đủ phê duyệt | Bỏ qua quy trình có thẩm quyền |
| T4 | Hai request cùng thấy còn 500.000 và cùng giữ 450.000 | Tổng quyền hoàn vượt ngân sách |
| T5 | Retry hoặc worker xử lý lại tạo lệnh mới | Một ý định hoặc quyết định tạo nhiều tác động tài chính |
| T6 | Timeout bị coi là thất bại chắc chắn | Giải phóng tiền trong khi nhà cung cấp có thể đã hoàn |
| T7 | Đường quản trị hoặc job bỏ qua cơ chế chính | Kiểm soát chỉ có hiệu lực trên một đường vào |

Một biện pháp đơn lẻ thường không bao phủ cả bảy threat. Mục tiêu là chọn một tập đủ để giữ các invariant, cùng cơ chế phát hiện và phục hồi cần thiết.

### 4.2. Xác định nguồn có thẩm quyền

| Dữ kiện | Nguồn cần dùng |
| --- | --- |
| Actor và tenant hiệu lực | Ngữ cảnh xác thực và quan hệ đã kiểm chứng |
| Hồ sơ, dòng hàng, payment liên quan | Dữ liệu máy chủ với kiểm tra quan hệ |
| Số tiền đủ điều kiện | Giao dịch đã chốt, phân bổ và chính sách tương ứng |
| Nội dung đã được duyệt | Quyết định hoặc snapshot có binding rõ ràng |
| Ngân sách còn lại | Sổ và khoản giữ tại nguồn ghi có thẩm quyền |
| Kết quả hoàn bên ngoài | Phản hồi đã xác minh hoặc đối soát theo hợp đồng |
| Thời gian xét hiệu lực | Thời gian máy chủ và quy tắc đã xác định |

Không chọn kiểm soát chỉ kiểm tra dữ kiện mà caller tự khai rồi coi đó là một rào cản. Ví dụ, so sánh `amount` với `refundableAmount` khi cả hai đều đến từ client không giữ được ngân sách.

## 5. Chọn nơi thực thi trước khi so sánh chi tiết phương án

~~~mermaid
flowchart LR
    A[Client hoặc công cụ quản trị] --> B[Biên xác thực]
    B --> C[Dịch vụ nghiệp vụ]
    C --> D[Dữ liệu và ràng buộc nhất quán]
    D --> E[Outbox và worker]
    E --> F[Nhà cung cấp bên ngoài]
~~~

Ở mỗi điểm, câu hỏi kiểm soát khác nhau:

- Biên xác thực xác định caller và context.
- Dịch vụ nghiệp vụ kiểm tra hành động, quan hệ, chính sách và binding.
- Nơi ghi giữ invariant dưới cạnh tranh và lưu tính duy nhất.
- Worker giữ ý nghĩa lệnh khi nhận trùng hoặc lỗi.
- Tích hợp bên ngoài có hợp đồng idempotency, truy vấn và đối soát riêng.

Validation trên giao diện có ích cho trải nghiệm nhưng không thay thế các điểm thực thi này.

Nếu invariant liên quan nhiều bản ghi, kiểm soát phải bao phủ các bản ghi đó. Khóa một hồ sơ hoàn không tự khóa hồ sơ khác cùng dùng ngân sách payment. Nếu invariant đi qua nhiều dịch vụ, một transaction cục bộ không tự tạo tính nguyên tử cho toàn chuỗi.

## 6. So sánh các phương án theo yêu cầu bắt buộc

Trước khi so chi phí hoặc độ tiện, cần loại phương án không đáp ứng điều kiện bắt buộc. Một phương án dễ triển khai nhưng không giữ invariant không trở thành phù hợp chỉ vì có tổng điểm thuận lợi ở các tiêu chí khác.

### 6.1. Ví dụ với threat cạnh tranh ngân sách T4

| Phương án | Có thể giữ ngân sách khi nào? | Giới hạn hoặc chi phí cần xét |
| --- | --- | --- |
| Vô hiệu hóa nút và chống double click | Không đủ để bảo vệ trước nhiều caller | Chỉ hỗ trợ trải nghiệm |
| Đọc số dư rồi ghi trong transaction thông thường | Chỉ đủ nếu cơ chế cô lập và tranh chấp thực sự bảo vệ điều kiện | Không thể suy ra chỉ từ việc có transaction |
| Khóa trong bộ nhớ một tiến trình | Chỉ phối hợp các luồng dùng đúng khóa trong tiến trình đó | Không đủ cho nhiều instance và đường ghi khác |
| Khóa hàng ngân sách trong transaction | Khi mọi luồng liên quan khóa đúng bản ghi, kiểm tra dưới khóa và ghi nhất quán | Chờ khóa, deadlock, thứ tự khóa và transaction dài |
| Cập nhật có điều kiện | Khi điều kiện và thay đổi ngân sách được thực hiện nguyên tử tại dữ liệu có thẩm quyền | Phải kiểm tra số hàng cập nhật và bảo vệ các bước liên quan |
| Optimistic locking theo phiên bản | Khi cập nhật phát hiện thay đổi cạnh tranh và caller đánh giá lại dữ kiện | Xung đột, retry có giới hạn, không dùng lại kết luận cũ |
| Transaction mức serializable phù hợp | Khi toàn bộ thao tác liên quan tham gia mô hình đó và xử lý lỗi cần retry | Chi phí và hành vi phụ thuộc hệ quản trị, workload |
| Idempotency key | Chặn gửi lại cùng khóa theo hợp đồng | Hai khóa hoặc hai hồ sơ khác nhau vẫn có thể cạnh tranh |
| Rate limiting | Giảm một phần tần suất | Hai request vẫn có thể đủ để phá invariant |

Khóa phân tán cũng cần được đánh giá bằng cùng yêu cầu: điều gì xảy ra khi mất quyền giữ khóa, tiến trình dừng hoặc một đường ghi không dùng khóa? Chỉ có một dịch vụ khóa không tự chứng minh dữ liệu không bị ghi sai.

### 6.2. Một lựa chọn cho kiến trúc minh họa

Giả sử ngân sách được biểu diễn bằng một bản ghi cho mỗi tenant, payment và tiền tệ. Nhóm chọn **cập nhật có điều kiện** để giữ tiền, vì điều kiện nằm trên một bản ghi và có thể kiểm tra số hàng cập nhật.

Ví dụ SQL trong PostgreSQL:

~~~sql
UPDATE refund_budget
SET pending_minor = pending_minor + :amount_minor
WHERE tenant_id = :tenant_id
  AND payment_id = :payment_id
  AND currency = :currency
  AND :amount_minor > 0
  AND :amount_minor <= refundable_minor - refunded_minor - pending_minor;
~~~

Chỉ tiếp tục khi số hàng cập nhật bằng 1. Các placeholder biểu diễn tham số bind, không phải nội suy chuỗi SQL.

Với dữ kiện ví dụ:

~~~text
C = 1.000.000
S =   200.000
P =   300.000
R =   450.000
~~~

Một request giữ thành công làm P thành 750.000, còn 50.000 cho khoản mới. Request cạnh tranh 450.000 phải không được chấp nhận từ cùng phần ngân sách đó.

Để kết luận phương án phù hợp, cần cả các điều kiện:

- Khóa duy nhất xác định đúng bản ghi ngân sách theo tenant, payment và tiền tệ.
- Miền giá trị, giới hạn kiểu số và các ràng buộc phù hợp được giữ.
- Mọi đường tăng, giảm hoặc sử dụng ngân sách tuân thủ cùng mô hình.
- Bản ghi khoản giữ, lệnh hoàn và thay đổi bộ đếm nằm trong cùng transaction.
- Thất bại ở bước sau rollback được thay đổi cục bộ.
- Các ngân sách khác, như quyền theo dòng hàng, được bảo vệ tương ứng.

Nếu invariant nằm trên nhiều bản ghi hoặc điều kiện phức tạp hơn, khóa hàng hoặc một thiết kế transaction khác có thể phù hợp hơn. Không cố áp một câu UPDATE vào mọi trường hợp.

### 6.3. Vì sao không thêm mọi cơ chế cạnh tranh cùng lúc?

Khóa hàng, phiên bản và cập nhật có điều kiện có thể phối hợp khi mỗi cơ chế có mục tiêu rõ. Nhưng thêm tất cả mà không xác định hợp đồng có thể tạo nhiều đường lỗi, thứ tự khóa phức tạp và retry khó hiểu.

Nên chọn một cơ chế chính giữ invariant tại nơi có thẩm quyền, sau đó bổ sung ràng buộc hoặc kiểm tra có giá trị riêng. Ví dụ, unique constraint cho một quyết định một lệnh giải quyết tính duy nhất; nó không trùng chức năng với điều kiện ngân sách tổng.

## 7. Chọn một tổ hợp bao phủ các threat còn lại

Trong kiến trúc minh họa, cập nhật ngân sách giải quyết một phần trọng yếu của T4. Các threat khác cần kiểm soát tương ứng.

| Threat | Kiểm soát được chọn | Điểm thực thi |
| --- | --- | --- |
| T1: sai đối tượng | Kiểm tra actor, tenant và quan hệ hồ sơ–payment–giao dịch | Dịch vụ nghiệp vụ và truy vấn có phạm vi |
| T2: sai số tiền hoặc nội dung | Số tiền do máy chủ xác định; phê duyệt gắn snapshot hoặc revision | Nơi tạo quyết định và trước thực thi |
| T3: bỏ quy trình | Chuyển trạng thái có điều kiện, kiểm tra quyết định còn hiệu lực | Thao tác giành quyền thực thi |
| T4: vượt ngân sách | Giữ nguyên tử trên ngân sách dùng chung | Cơ sở dữ liệu có thẩm quyền |
| T5: tác động trùng | Idempotency request, unique theo quyết định, mã lệnh ngoài ổn định | API, dữ liệu, worker và tích hợp |
| T6: kết quả chưa rõ | Trạng thái chờ, bảo toàn khoản giữ, truy vấn và đối soát | Điều phối lệnh bên ngoài |
| T7: đường bỏ qua | Hạn chế quyền ghi, dùng cùng primitive và kiểm thử các đường | API, job, batch và công cụ quản trị |

Đây là một tổ hợp cho các giả định đã nêu. Không phải mọi hệ thống đều cần cấu trúc thành phần giống nhau, nhưng phải giải thích được thuộc tính nào được giữ ở đâu.

### 7.1. Quyền theo đối tượng và state machine giải quyết các câu hỏi khác nhau

Quyền theo đối tượng trả lời actor có được thao tác trên hồ sơ đó không. State machine trả lời hành động có hợp lệ ở thời điểm và trạng thái đó không.

Một chủ hồ sơ hợp lệ vẫn không được thực thi khi chưa duyệt. Một hồ sơ đã duyệt vẫn không được caller bất kỳ thực thi hoặc đọc kết quả nếu không có quyền tương ứng.

Nếu có quy tắc tách biệt người đề nghị và người duyệt, cần kiểm tra danh tính và quan hệ theo chính sách. Không chỉ kiểm tra một vai trò chung.

### 7.2. Binding giữ nguyên ý nghĩa quyết định

Quyết định duyệt nên bao phủ tenant, đối tượng, nội dung tiền tệ và phiên bản có ảnh hưởng. Khi thay số tiền, payment, người nhận hoặc dòng hàng, phải xác định cần duyệt lại hay không theo chính sách.

Một cờ `approved=true` không đủ nếu nội dung có thể đổi sau đó. Hash chỉ hữu ích khi tham chiếu được bảo vệ và schema bao phủ đúng dữ kiện; nó không tự tạo thẩm quyền phê duyệt.

### 7.3. Idempotency và tính duy nhất cùng cần hợp đồng rõ

Khóa idempotency cần phạm vi actor hoặc bên gọi, tenant, loại thao tác và fingerprint nội dung. Cùng khóa khác nội dung phải được xử lý như xung đột.

Unique constraint theo quyết định bảo vệ trước khóa mới. Nếu nghiệp vụ cho một quyết định dùng nhiều lần trong hạn mức, cần mô hình phần đã dùng và đang giữ thay vì áp đặt một lần duy nhất.

Thời gian lưu khóa request không nên là giới hạn duy nhất của tác động tài chính. Quyền lợi tồn tại lâu hơn cache vẫn cần ràng buộc nghiệp vụ tồn tại tương ứng.

## 8. Minh họa Java: đặt các kiểm soát ở ranh giới nghiệp vụ

Đoạn mã sau là **mã khung**, chưa phải ứng dụng chạy độc lập. Các repository, transaction và primitive giữ ngân sách phải được hiện thực theo hợp đồng đã chọn.

~~~java
record ExecuteRefundCommand(
        String returnCaseId,
        String idempotencyKey) {}

record RefundReceipt(
        String executionId,
        String status) {}

public RefundReceipt executeRefund(
        ActorContext actor,
        ExecuteRefundCommand command) {

    validateCommand(command);

    return transactions.required(() -> {
        var returnCase = returns.lockByTenantAndId(
                actor.tenantId(), command.returnCaseId());

        permissions.requireCurrentRefundCapability(actor, returnCase);

        var scope = operationScopes.forRefund(actor, returnCase);
        var replay = idempotency.claimOrReplay(
                scope,
                command.idempotencyKey(),
                fingerprints.forRefund(command));

        if (replay.isPresent()) {
            return replay.get();
        }

        var approval = approvals.loadFor(returnCase);
        approval.requireValidAndBoundTo(returnCase, serverClock.instant());
        returnCase.requireReadyForExecution();

        var allocation = refundPolicy.resolveApprovedAllocation(
                returnCase, approval);

        refundRights.reserveOrThrow(returnCase, allocation);
        refundBudgets.reserveOrThrow(
                actor.tenantId(), returnCase.paymentId(), allocation);

        var execution = refunds.createUniqueForDecision(
                approval.id(), allocation);

        returns.markExecutionPending(returnCase, execution.id());
        outbox.appendRefundRequested(execution.id());

        var result = new RefundReceipt(
                execution.id(), "REFUND_PENDING");

        idempotency.complete(scope, command.idempotencyKey(), result);
        return result;
    });
}
~~~

Các điểm cần chứng minh trong triển khai:

1. Actor được xác thực và có quan hệ phù hợp với đối tượng; client không tự truyền context đáng tin cậy.
2. Khoản tiền được lấy từ dữ kiện máy chủ và quyền lợi đã chốt, không nhận như một quyết định cuối cùng từ request.
3. Khóa hồ sơ giữ việc kiểm tra binding và đổi trạng thái nhất quán. Nó không thay thế primitive ngân sách chung cho các hồ sơ khác.
4. Giữ quyền theo dòng hoặc số lượng và giữ tiền đều nguyên tử theo thiết kế. Mọi thay đổi liên quan rollback khi bước sau thất bại.
5. Unique theo quyết định và state machine ngăn tạo thêm lệnh bằng khóa request mới.
6. Idempotency dùng lưu trữ có ràng buộc duy nhất, xử lý cùng khóa khác nội dung và request đang cạnh tranh.
7. Nếu xung đột làm transaction bị hủy, tầng ngoài phải kết thúc transaction đó trước khi đọc lại hoặc retry.
8. Kiểm tra quyền trước replay không bị trộn với điều kiện trạng thái chỉ dành cho tạo tác động mới; lần gửi lại hợp lệ không bị từ chối chỉ vì lần đầu đã đổi trạng thái.
9. Outbox, lệnh hoàn, khoản giữ và kết quả cục bộ cùng commit.
10. Kết quả `REFUND_PENDING` phản ánh trạng thái chờ, không khẳng định nhà cung cấp đã hoàn thành.

Tên các phương thức không phải bằng chứng hiệu lực. Cần kiểm thử và kiểm tra hợp đồng của phần lưu trữ, đặc biệt dưới nhiều instance và đường ghi khác nhau.

## 9. Chọn hành vi khi lỗi cũng là chọn kiểm soát

“Fail closed” cần được cụ thể hóa theo từng hành động, không chỉ là ném lỗi cho mọi tình huống.

| Tình huống lỗi | Hành vi cần xác định |
| --- | --- |
| Không kiểm chứng được quyền bắt buộc | Không tạo tác động mới dựa trên mặc định cho phép |
| Không tải được phê duyệt | Chờ hoặc từ chối theo hợp đồng, không coi như đã duyệt |
| Giữ ngân sách không thành công | Không tạo lệnh hoàn và không để lại khoản giữ dở dang |
| Worker nhận lại message | Tiếp tục cùng lệnh theo trạng thái, không tạo lệnh mới |
| Gọi ngoài timeout | Giữ kết quả chưa rõ và đối soát, không tự giải phóng tiền |
| Consumer cập nhật chậm | Áp dụng quy tắc phiên bản hoặc chờ theo yêu cầu hiệu lực |
| Transaction bị xung đột | Retry có giới hạn với dữ kiện được đánh giá lại |

Từ chối mọi tác vụ khi có lỗi cũng có thể gây hại. Ví dụ, hệ thống có thể ngừng tạo lệnh mới nhưng vẫn cần đọc trạng thái và đối soát các lệnh đã gửi.

Một đường xử lý thủ công chỉ là phương án hợp lệ nếu có thẩm quyền, dữ kiện, lịch sử và giới hạn riêng. Không dùng nó làm nhánh mặc định bỏ mọi kiểm tra khi hệ thống chính lỗi.

## 10. Bên ngoài transaction cần một bộ kiểm soát khác

Nhà cung cấp thanh toán không tham gia transaction cục bộ trong ví dụ. Do đó, cần bảo vệ khoảng cách giữa ý định đã lưu và tác động bên ngoài.

Một luồng minh họa:

1. Transaction tạo lệnh và giữ ngân sách, sau đó ghi outbox.
2. Worker đọc lệnh có thẩm quyền và dùng mã ngoài ổn định.
3. Nếu nhà cung cấp có hỗ trợ idempotency phù hợp, mọi lần gửi lại cùng lệnh dùng cùng khóa theo hợp đồng đó.
4. Thành công được xác nhận chuyển khoản giữ sang đã hoàn, đúng một lần trong sổ nội bộ.
5. Thất bại cuối cùng được xác nhận mới giải phóng khoản giữ theo chính sách.
6. Kết quả chưa rõ tiếp tục được truy vấn hoặc đối soát.

Outbox không tự tạo ngữ nghĩa tác động đúng một lần. Nếu nhà cung cấp không hỗ trợ một khả năng cần thiết, phải điều chỉnh cơ chế điều phối, xác minh hoặc xử lý ngoại lệ; không coi retry luôn an toàn.

Khi thành công với số tiền R:

~~~text
P' = P - R
S' = S + R
~~~

Tổng ngân sách đã sử dụng và đang giữ không đổi tại bước này. Khi thất bại cuối cùng được xác nhận, giảm khoản giữ đúng một lần. Webhook trùng hoặc đến lệch thứ tự không được làm giảm, cộng hoặc giải phóng lại cùng khoản tiền.

## 11. So sánh các phương án đã đáp ứng invariant

Sau khi loại phương án không đáp ứng yêu cầu bắt buộc, mới so các phương án còn lại theo bối cảnh.

| Tiêu chí | Câu hỏi thực tế |
| --- | --- |
| Phạm vi bảo vệ | Có bao phủ mọi đường tạo cùng tác động không? |
| Giả định | Cần những dữ kiện, quyền ghi hoặc điều kiện kiến trúc nào luôn đúng? |
| Nhất quán | Giữ được thuộc tính khi đồng thời, retry và lỗi từng phần không? |
| Hiệu năng | Có gây tranh chấp trên bản ghi nóng, transaction dài hoặc nhiều retry không? |
| Trải nghiệm | Có chặn nhầm, buộc duyệt không cần thiết hoặc làm người dùng không hiểu trạng thái không? |
| Vận hành | Ai quan sát, xử lý cảnh báo, đối soát và giải quyết ngoại lệ? |
| Triển khai | Có tương thích dữ liệu cũ và giai đoạn chuyển tiếp không? |
| Khả năng kiểm chứng | Có ca kiểm thử hoặc bằng chứng đủ mạnh cho thuộc tính cần giữ không? |

Không nên dùng một tổng điểm thuận tiện để bù trừ một điều kiện bảo mật bắt buộc. Một phương án rẻ và nhanh nhưng vẫn cho chi vượt ngân sách không tương đương một phương án đáp ứng invariant.

### 11.1. Ví dụ so khóa hàng với cập nhật có điều kiện

Nếu mọi điều kiện ngân sách nằm trên một hàng, cập nhật có điều kiện thường tạo một hợp đồng dễ kiểm tra: cập nhật đúng một hàng hoặc không giữ tiền.

Nếu quyết định cần đọc và thay đổi nhiều đối tượng liên quan, khóa theo một thứ tự rõ có thể giúp diễn đạt thao tác dễ hơn. Đổi lại, phải kiểm soát thời gian transaction và xử lý deadlock.

Optimistic locking có thể phù hợp khi xung đột đủ thấp và caller đánh giá lại an toàn. Khi có nhiều xung đột, retry có thể tạo tải hoặc trải nghiệm kém; cần đo trong workload đại diện.

Không có một lựa chọn mặc định cho mọi hệ thống. Điều bắt buộc là chứng minh phương án đáp ứng cùng thuộc tính, rồi chọn theo chi phí và điều kiện vận hành thực tế.

### 11.2. Kiểm soát làm tăng ma sát cần có lý do

Một bước xác nhận hoặc phê duyệt bổ sung có thể phù hợp với quyền lợi lớn, thay người nhận tiền hoặc thay chính sách. Áp dụng cho mọi thao tác không có căn cứ có thể tăng tải hỗ trợ mà không chặn lỗi cạnh tranh.

Tương tự, rate limit có ích nếu threat bao gồm tiêu thụ tài nguyên hoặc tăng tốc tổn thất. Nó không nên được thêm như cách thay thế primitive ngân sách.

Nếu phải chọn một ngưỡng, cần biết mục tiêu bảo vệ và dữ liệu hiệu chỉnh. Ngưỡng tùy ý dễ chặn người dùng hợp lệ mà vẫn cho một lần tác động sai nghiêm trọng.

## 12. Ghi một quyết định kiểm soát có thể kiểm chứng

Một mẫu ngắn giúp tránh quyết định chỉ tồn tại trong trao đổi miệng.

### 12.1. Ví dụ thẻ kiểm soát ngân sách

~~~text
ID:
  C-BUDGET-01

Threat:
  Nhiều yêu cầu hợp lệ khi đứng riêng cùng vượt ngân sách hoàn.

Thuộc tính:
  Không chấp nhận khoản giữ mới R nếu S + P + R > C.

Phạm vi:
  Mọi đường thực thi hoàn dùng cùng payment, tenant và tiền tệ.

Điểm thực thi:
  Bản ghi ngân sách có thẩm quyền trong transaction cục bộ.

Cơ chế được chọn:
  Cập nhật có điều kiện, kiểm tra số hàng cập nhật,
  cùng transaction với khoản giữ và lệnh hoàn.

Khi thất bại:
  Không tạo lệnh mới; rollback thay đổi cục bộ liên quan.

Phụ thuộc:
  Khóa duy nhất đúng, miền số hợp lệ, mọi đường ghi tuân thủ mô hình.

Bằng chứng:
  Kiểm thử cạnh tranh, rollback, retry và kiểm tra sổ sau commit.

Không bao phủ:
  Quyền theo đối tượng, sự đúng đắn của nguồn tiền,
  phê duyệt và tác động ngoài transaction.

Phần bổ sung:
  Các kiểm soát riêng cho quyền, binding, tính duy nhất và đối soát.
~~~

Một thẻ như vậy giúp reviewer hỏi đúng câu: nếu một job quản trị có thể sửa `pending` trực tiếp mà không giữ mô hình, giả định của C-BUDGET-01 không còn đúng.

### 12.2. Lưu cả phương án không được chọn khi có giá trị giải thích

Không cần kể toàn bộ lịch sử thảo luận. Chỉ ghi các lựa chọn khác giải thích một tradeoff quan trọng.

Ví dụ:

~~~text
Không chọn khóa trong một tiến trình:
  Có nhiều instance và worker cùng ghi.

Không dùng idempotency làm kiểm soát ngân sách duy nhất:
  Hai hồ sơ khác nhau vẫn dùng chung ngân sách.

Chọn cập nhật có điều kiện:
  Invariant chính nằm trên một hàng có thẩm quyền.

Điều kiện cần xem lại:
  Ngân sách chuyển sang nhiều dịch vụ hoặc thêm điều kiện đa bản ghi.
~~~

Việc ghi điều kiện xem lại giúp quyết định không trở thành một quy tắc tồn tại mãi sau khi kiến trúc đã thay đổi.

## 13. Bằng chứng hiệu lực cần gắn với từng threat

| Threat | Kiểm thử hoặc bằng chứng cần có | Kết quả cần quan sát |
| --- | --- | --- |
| T1: sai đối tượng | Actor khác khách hàng, tenant hoặc quan hệ; ghép sai các ID | Không ghi dữ liệu và không trả dữ liệu trái quyền |
| T2: nội dung thay đổi | Sửa số tiền, payment hoặc trường có ảnh hưởng sau duyệt | Không thực thi bằng phê duyệt cũ |
| T3: bỏ bước | Gọi thẳng từ trạng thái chưa đủ điều kiện | Không có lệnh tài chính hoặc khoản giữ mới |
| T4: cạnh tranh | Đồng bộ hai request tại điểm giữ cùng ngân sách | Tổng quyền được chấp nhận không vượt giới hạn |
| T5: gửi lại | Cùng khóa, khác khóa, message trùng và hai worker | Đúng số lệnh và tác động nghiệp vụ được phép |
| T6: chưa rõ kết quả | Nhà cung cấp thực hiện nhưng phản hồi bị mất | Khoản giữ còn đúng và không có lệnh mới ngoài ý định |
| T7: đường bỏ qua | Gọi API cũ, batch, job và công cụ quản trị liên quan | Cùng invariant hoặc một quy trình ngoại lệ có kiểm soát |

Các kiểm thử bổ sung thường cần:

- Gây lỗi sau giữ ngân sách nhưng trước tạo lệnh để kiểm tra rollback.
- Gây lỗi sau commit nhưng trước gửi outbox để kiểm tra không mất ý định.
- Nhận webhook trùng hoặc lệch thứ tự để kiểm tra chuyển trạng thái.
- Cho hai hồ sơ khác nhau dùng cùng payment, thay vì chỉ retry cùng hồ sơ.
- Kiểm tra giới hạn số, tiền tệ, số lượng và phần làm tròn.
- Kiểm tra quyền bị thu hồi hoặc quyết định hết hiệu lực theo chính sách.

Đối với Java, unit test với mock có thể xác minh một số nhánh gọi. Nó không chứng minh cơ sở dữ liệu khóa đúng hoặc unique constraint hoạt động khi tranh chấp. Những thuộc tính đó cần kiểm thử tích hợp với ngữ nghĩa lưu trữ đại diện.

Không chỉ xem response. Cần xem số lệnh, khoản giữ, trạng thái, mục sổ, outbox và số tác động tại nhà cung cấp mô phỏng.

### 13.1. Tiêu chí hoàn tất nên được viết trước

Một phát biểu như “đã thêm validation” không phải tiêu chí hoàn tất cho threat chi trùng.

Có thể viết:

~~~text
Với ngân sách còn 500.000 và hai khoản 450.000 cạnh tranh,
không thể commit hai khoản giữ thành công.

Nếu một bước cục bộ sau giữ thất bại,
không còn khoản giữ hoặc lệnh dở dang đã commit.

Nếu cùng quyết định được gửi lại bằng khóa request mới,
không tạo thêm lệnh tài chính.

Nếu tác động ngoài chưa rõ kết quả,
không giải phóng ngân sách để tạo một lệnh khác trái chính sách.
~~~

Các tiêu chí này chỉ rõ điều cần chứng minh mà không buộc kiểm thử phải sao chép cấu trúc triển khai.

## 14. Triển khai, quan sát và xem lại lựa chọn

Một kiểm soát đã được chọn chưa làm rủi ro giảm. Cần phân biệt:

~~~text
được chọn
  -> được hiện thực
  -> được triển khai
  -> được xác minh trong phạm vi
  -> được quan sát và duy trì
~~~

### 14.1. Dữ liệu cũ và giai đoạn chuyển tiếp

Trước khi thêm unique constraint hoặc chuyển mô hình ngân sách, có thể đã tồn tại:

- Lệnh trùng.
- Khoản giữ không khớp tổng.
- Trạng thái chưa rõ từ nhà cung cấp.
- Dữ liệu không có revision hoặc binding.
- Đường ghi cũ vẫn hoạt động trong giai đoạn rollout.

Cần một kế hoạch xử lý và chuyển tiếp giữ được ý nghĩa dữ liệu. Không xóa lịch sử tài chính hoặc bỏ constraint chỉ để migration chạy qua mà chưa giải thích sai lệch.

Nếu cả đường cũ và mới cùng hoạt động, phải biết invariant được giữ ở đâu trong khoảng chuyển tiếp. Một kiểm soát chỉ có hiệu lực sau khi mọi instance cập nhật chưa đủ bảo vệ giai đoạn triển khai từng phần.

Rollback cũng cần được đánh giá: quay về mã cũ có thể làm mất rào cản ngân sách hoặc không hiểu dữ liệu mới.

### 14.2. Quan sát đúng thuộc tính

Các tín hiệu có ích cho ví dụ:

- Số lần giữ ngân sách bị từ chối và nguyên nhân.
- Xung đột phiên bản, chờ khóa, deadlock và số lần retry.
- Lệnh chưa rõ kết quả quá lâu.
- Khoản giữ không khớp lệnh đang chờ.
- Một quyết định gắn với nhiều lệnh ngoài chính sách.
- Tác động không nối được tới phê duyệt hợp lệ.
- Đường quản trị tạo thay đổi không qua primitive được chọn.

Không ghi credential, token đầy đủ hoặc dữ liệu nhạy cảm không cần thiết vào log. Dùng định danh và tham chiếu có kiểm soát để truy nguyên.

Một lượng lớn từ chối có thể là lạm dụng, retry lỗi hoặc thiết kế gây chặn nhầm. Cần điều tra ngữ cảnh trước khi kết luận.

### 14.3. Khi nào phải chọn lại hoặc điều chỉnh?

- Tài sản, quyền lợi hoặc actor mới xuất hiện.
- Hạn mức hoặc giá trị giao dịch tăng.
- Chuyển từ một instance sang nhiều instance.
- Tách dữ liệu sang dịch vụ khác.
- Thêm batch, job hoặc công cụ quản trị.
- Nhà cung cấp đổi khả năng idempotency hoặc truy vấn theo hợp đồng.
- Có bằng chứng kiểm soát bị bỏ qua hoặc gây lỗi vận hành.
- Giả định trong thẻ kiểm soát không còn đúng.

Không giữ một giải pháp chỉ vì trước đây nó từng phù hợp. Cũng không thay toàn bộ cơ chế khi dữ kiện mới chỉ ảnh hưởng một phần nhỏ; cập nhật đúng phạm vi và kiểm chứng lại các thuộc tính bị tác động.

## 15. Những lựa chọn dễ tạo cảm giác được bảo vệ

| Lựa chọn | Vì sao chưa đủ? | Câu hỏi cần bổ sung |
| --- | --- | --- |
| Thêm xác thực cho mọi endpoint | Actor hợp lệ vẫn có thể lạm dụng | Quyền theo đối tượng và invariant nào được giữ? |
| Chỉ kiểm tra dữ liệu không âm | Giá trị dương vẫn có thể sai chính sách | Ai quyết định giá trị có thẩm quyền? |
| Thêm annotation transaction | Không tự xác định cơ chế tranh chấp | Điều kiện được kiểm tra và cập nhật nguyên tử thế nào? |
| Dùng idempotency key | Chỉ bao phủ cùng khóa theo hợp đồng | Khóa mới hoặc hồ sơ khác dùng cùng quyền lợi ra sao? |
| Thêm rate limit | Không chứng minh đúng tiền hoặc trạng thái | Có một ngân sách hoặc ràng buộc cứng không? |
| Bắt duyệt thủ công mọi trường hợp | Không ngăn worker thực thi trùng | Quyết định được ràng buộc và tiêu thụ thế nào? |
| Thêm log và cảnh báo | Có thể chỉ phát hiện sau tác động | Điều gì ngăn hoặc giới hạn trước đó? |
| Khóa trong JVM | Không bao phủ nhiều instance | Nguồn dữ liệu dùng chung được bảo vệ ở đâu? |
| Tin hệ thống nội bộ | Job và quản trị có thể có đường ghi khác | Mọi đường tạo tác động có cùng hợp đồng không? |
| Thêm nhiều lớp giống nhau | Có thể cùng hỏng vì một dữ kiện hoặc cờ bỏ qua | Mỗi lớp giảm thêm đường lạm dụng nào? |

## 16. Bài tập tự kiểm tra

### Bài 1: một threat, nhiều phương án

Ngân sách của mỗi payment nằm trên một hàng. Hai request khác hồ sơ có thể cùng giữ vượt phần còn lại. Nhóm đề nghị thêm CAPTCHA hoặc idempotency key.

**Gợi ý trả lời:** hai biện pháp đó không trực tiếp giữ invariant tổng. Cần primitive nguyên tử tại ngân sách dùng chung. Idempotency vẫn có giá trị cho retry nhưng là một phần bổ sung, không phải kiểm soát ngân sách duy nhất.

### Bài 2: khóa hồ sơ đã đủ chưa?

Dịch vụ khóa từng hồ sơ hoàn trước khi xử lý. Hai hồ sơ khác nhau cùng tham chiếu một payment.

**Gợi ý trả lời:** khóa hai hồ sơ khác nhau không tạo tranh chấp trên ngân sách chung. Cần giữ hoặc khóa đúng payment budget, đồng thời giữ các giới hạn theo dòng và quyết định nếu có.

### Bài 3: phê duyệt thủ công có ngăn hoàn hai lần không?

Một quản lý duyệt đúng hồ sơ. Do mất phản hồi, hai worker cùng gửi lệnh tới nhà cung cấp bằng hai mã mới.

**Gợi ý trả lời:** phê duyệt giải quyết điều kiện cho phép, không tự giải quyết tính duy nhất thực thi. Cần một lệnh nghiệp vụ ổn định, unique theo quyết định, điều kiện trạng thái và khả năng chống trùng hoặc đối soát theo hợp đồng bên ngoài.

### Bài 4: giải pháp cũ sau khi tách dịch vụ

Trước đây ngân sách và lệnh cùng một cơ sở dữ liệu. Sau khi tách dịch vụ, nhóm giữ nguyên mô tả “mọi thứ được bảo vệ bởi transaction”.

**Gợi ý trả lời:** giả định ranh giới transaction đã đổi. Cần chọn lại cơ chế giữ, xác nhận, message, xử lý lỗi từng phần và đối soát. Transaction cục bộ vẫn có giá trị trong từng phạm vi nhưng không tự bảo vệ toàn chuỗi.

## 17. Các điểm cần ghi nhớ

Lựa chọn kiểm soát bắt đầu từ một kết quả bị cấm và invariant cần giữ, rồi xác định actor, dữ kiện có thẩm quyền và nơi thực thi. Tên công nghệ hoặc số lớp kiểm tra không tự chứng minh hiệu quả.

Một tập kiểm soát đủ cần bao phủ quyền, nội dung quyết định, trạng thái, cạnh tranh, tác động trùng và lỗi ngoài transaction trong phạm vi threat model. Mỗi phần phải có hợp đồng khi lỗi và bằng chứng kiểm thử tương ứng.

Câu hỏi cốt lõi là: **Kiểm soát này giữ thuộc tính nào, tại đâu, dưới những giả định gì, và bằng chứng nào cho thấy đường lạm dụng thật sự đã bị chặn hoặc giảm tác động?**
